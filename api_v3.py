"""
G1 Glasses API — thin HTTP layer over protocol package.

All BLE communication, packet building, and image processing is in protocol/.
This file: FastAPI endpoints only.
"""

import asyncio
import base64
import json
import logging
import shutil
import sys
import uvicorn
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from protocol.connect import (
    GlassesManager,
    send_text,
    send_page,
    step_text_page,
    stereo_pair,
    send_bmp_to_glass,
)
from protocol.bmp import compose_text_blocks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Module-level state ─────────────────────────────────────────────────────────

manager: GlassesManager = GlassesManager()
is_connecting: bool = False
_event_subscribers: list[asyncio.Queue] = []

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _broadcast(line: str) -> None:
    """Send event to all SSE subscribers."""
    for q in _event_subscribers:
        try:
            q.put_nowait(line)
        except asyncio.QueueFull:
            pass


def _connection_status() -> dict:
    """Return current connection state."""
    return manager.connection_status()


# ── Event Handlers ────────────────────────────────────────────────────────────

async def _on_glass_event(glass, sender, data: bytes) -> None:
    """Route notifications from glasses."""
    if not data:
        return
    cmd = data[0]

    from protocol.constants import Cmd, DeviceOrder, SILENT_CMDS, F5_EVENTS

    if cmd in SILENT_CMDS:
        return

    if cmd == Cmd.DEVICE_ORDER and len(data) >= 2:
        code = data[1]
        label = F5_EVENTS.get(code, f"unknown 0x{code:02x}")
        _broadcast(f"INFO:touchpad:{glass.side} — {label} raw={data.hex()}")

        if code == DeviceOrder.TRIGGER_CHANGE_PAGE:
            await step_text_page(manager, forward=(glass.side == "right"))
        elif code == DeviceOrder.DISPLAY_READY:
            from protocol.connect import _text_session
            _text_session.pages = []
            _text_session.current = 0
            _text_session.total = 0

    elif cmd == Cmd.GLASSES_WEAR and len(data) >= 2:
        label = "Worn" if data[1] == 0x01 else "Taken Off"
        _broadcast(f"INFO:wear:{glass.side} — {label} raw={data.hex()}")

    elif cmd != Cmd.HEARTBEAT:
        _broadcast(f"DEBUG:ble:{glass.side} cmd=0x{cmd:02x} raw={data.hex()}")


# ── Pydantic Models ───────────────────────────────────────────────────────────

class TextPayload(BaseModel):
    text: str


class ComposePayload(BaseModel):
    layers: list[dict] = []


class SaveLayoutPayload(BaseModel):
    name: str
    layers: list[dict] = []


class BlockPayload(BaseModel):
    name: str = ""
    start: str = ""
    end: str = ""


class BriefPayload(BaseModel):
    """Mirrors the morning-card.html form."""
    energy: int = 7
    focus: int = 7
    tStart: str = "06:00"
    tEnd: str = "21:00"
    weekPriority: str = ""
    oneThing: str = ""
    domain: str = "vision"
    stopCriteria: str = ""
    checks: dict[str, bool] = {}
    blocks: list[BlockPayload] = []
    screens: list[str] = ["brief", "blocks", "power"]
    mode: str = "text"  # "text" = paginated raw text, tap to page; "image" = stereo BMP
    dwellSeconds: float = 6.0
    maxDisparity: int = 10  # MAX_DISPARITY is defined below the models


class Render3DPayload(BaseModel):
    offsetX: float = 0.0  # Translation X (pixels)
    offsetY: float = 0.0  # Translation Y (pixels)
    z: float = 0.0       # Stereo z-depth
    fov: float = 60.0
    distance: float = 300.0


MAX_DISPARITY = 10
BRIEF_SETTLE = 0.6   # seconds to let the BLE link settle before the first screen
BRIEF_EYE_GAP = 0.15  # seconds between the left and right eye of one screen


def _bundle_dir() -> Path:
    """Read-only resources shipped with the app.

    PyInstaller unpacks a one-file build into sys._MEIPASS; running from
    source it is just the repo root.
    """
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent))


def _data_dir() -> Path:
    """Writable storage for layouts and models.

    A frozen build unpacks into a temp dir that is wiped when the process
    exits, so anything the user creates has to live outside the bundle.
    """
    if getattr(sys, "frozen", False):
        d = Path.home() / "Library" / "Application Support" / "KiroshiOS"
    else:
        d = Path(__file__).parent
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_DIR = _data_dir()
LAYOUTS_FILE = DATA_DIR / "layouts.json"
MODELS_DIR = DATA_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)


def _seed_bundled_resources() -> None:
    """Copy starter models and layouts out of the bundle on first run.

    No-op when running from source, and never overwrites what is already
    in the data dir.
    """
    if not getattr(sys, "frozen", False):
        return

    src_models = _bundle_dir() / "models"
    if src_models.is_dir():
        for obj_file in src_models.glob("*.obj"):
            dest = MODELS_DIR / obj_file.name
            if not dest.exists():
                shutil.copy2(obj_file, dest)

    src_layouts = _bundle_dir() / "layouts.json"
    if src_layouts.is_file() and not LAYOUTS_FILE.exists():
        shutil.copy2(src_layouts, LAYOUTS_FILE)


_seed_bundled_resources()
logger.info("Data dir: %s", DATA_DIR)


# ── Layout Storage ────────────────────────────────────────────────────────────

def _load_layouts() -> list[dict]:
    """Load all saved layouts from disk."""
    if not LAYOUTS_FILE.exists():
        return []
    try:
        with open(LAYOUTS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_layouts(layouts: list[dict]) -> None:
    """Save layouts to disk."""
    with open(LAYOUTS_FILE, 'w') as f:
        json.dump(layouts, f, indent=2)


def _get_layout_by_id(layout_id: str) -> dict | None:
    """Get a single layout by ID."""
    for layout in _load_layouts():
        if layout.get("id") == layout_id:
            return layout
    return None


# ── API Endpoints ──────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """Get current connection status for both glasses."""
    return _connection_status()


@app.post("/api/disconnect")
async def disconnect():
    """Disconnect from all glasses."""
    await manager.disconnect_all()
    return {"connected": False}


@app.post("/api/sync-time")
async def sync_time_endpoint():
    """Sync system time to connected glasses."""
    if not manager.left_glass and not manager.right_glass:
        raise HTTPException(status_code=503, detail="Not connected to glasses")
    try:
        await manager.sync_time()
        return {"status": "time synced"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/layouts")
async def list_layouts():
    """Get all saved composition layouts."""
    layouts = _load_layouts()
    return {"layouts": layouts}


@app.post("/api/layouts")
async def save_layout(payload: SaveLayoutPayload):
    """Save a new composition layout."""
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Layout name required")

    layouts = _load_layouts()
    layout_id = datetime.now().isoformat()
    new_layout = {
        "id": layout_id,
        "name": payload.name,
        "layers": payload.layers,
        "created": layout_id,
    }
    layouts.append(new_layout)
    _save_layouts(layouts)
    return {"id": layout_id, "name": payload.name}


@app.get("/api/layouts/{layout_id}")
async def get_layout(layout_id: str):
    """Load a specific layout by ID."""
    layout = _get_layout_by_id(layout_id)
    if not layout:
        raise HTTPException(status_code=404, detail="Layout not found")
    return layout


@app.delete("/api/layouts/{layout_id}")
async def delete_layout(layout_id: str):
    """Delete a layout by ID."""
    layouts = _load_layouts()
    filtered = [l for l in layouts if l.get("id") != layout_id]
    if len(filtered) == len(layouts):
        raise HTTPException(status_code=404, detail="Layout not found")
    _save_layouts(filtered)
    return {"status": "deleted"}


# ── 3D Model Management ────────────────────────────────────────────────────────

@app.get("/api/models")
async def list_models():
    """List all uploaded 3D OBJ models."""
    if not MODELS_DIR.exists():
        return {"models": []}

    models = []
    for obj_file in MODELS_DIR.glob("*.obj"):
        models.append({
            "id": obj_file.stem,
            "name": obj_file.stem,
            "size": obj_file.stat().st_size,
        })
    return {"models": models}


@app.post("/api/models")
async def upload_model(file: UploadFile = File(...)):
    """Upload a 3D OBJ model file."""
    if not file.filename.endswith(".obj"):
        raise HTTPException(status_code=400, detail="OBJ files only")

    try:
        from protocol.obj3d import load_obj_bytes

        obj_bytes = await file.read()
        model = load_obj_bytes(obj_bytes)

        # Save to disk
        model_path = MODELS_DIR / file.filename
        with open(model_path, "wb") as f:
            f.write(obj_bytes)

        return {
            "id": model_path.stem,
            "name": file.filename,
            "vertices": len(model.vertices),
            "edges": len(model.edges),
        }
    except Exception as e:
        logger.exception("Model upload error")
        raise HTTPException(status_code=400, detail=f"Invalid OBJ: {str(e)}")


@app.post("/api/models/{model_id}/preview")
async def preview_3d_model(model_id: str, payload: Render3DPayload):
    """Render 3D model to preview (left/right stereo pair)."""
    try:
        from protocol.obj3d import load_obj_bytes, render_wireframe
        from protocol.bmp import compose_layers, compute_depth

        model_path = MODELS_DIR / f"{model_id}.obj"
        if not model_path.exists():
            raise HTTPException(status_code=404, detail="Model not found")

        with open(model_path, "rb") as f:
            obj_bytes = f.read()

        model = load_obj_bytes(obj_bytes)
        # Fixed view angle: 20° top-down perspective
        # Apply offset to auto-centered position
        position = (288 + payload.offsetX, 68 + payload.offsetY)
        bmp = render_wireframe(
            model,
            rotation=(20, 0, 0),  # Fixed: top-down 3D view
            position=position,
            scale=None,           # Auto-scale to fit
            z_depth=payload.z,
            fov=payload.fov,
            distance=payload.distance,
        )

        # Apply stereo depth
        left_layers, right_layers = compute_depth([(bmp, (payload.z + 5) / 10.0)], MAX_DISPARITY)
        left_bmp = compose_layers(left_layers)
        right_bmp = compose_layers(right_layers)

        left_b64 = base64.b64encode(left_bmp).decode('utf-8')
        right_b64 = base64.b64encode(right_bmp).decode('utf-8')

        return {
            "left": f"data:image/bmp;base64,{left_b64}",
            "right": f"data:image/bmp;base64,{right_b64}",
        }
    except Exception as e:
        logger.exception("3D preview error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/models/{model_id}/send")
async def send_3d_model(model_id: str, payload: Render3DPayload):
    """Render and send 3D model to glasses."""
    if not manager.left_glass and not manager.right_glass:
        raise HTTPException(status_code=503, detail="Not connected to glasses")

    try:
        from protocol.obj3d import load_obj_bytes, render_wireframe
        from protocol.bmp import compose_layers, compute_depth

        model_path = MODELS_DIR / f"{model_id}.obj"
        if not model_path.exists():
            raise HTTPException(status_code=404, detail="Model not found")

        with open(model_path, "rb") as f:
            obj_bytes = f.read()

        model = load_obj_bytes(obj_bytes)
        # Fixed view angle: 20° top-down perspective
        # Apply offset to auto-centered position
        position = (288 + payload.offsetX, 68 + payload.offsetY)
        bmp = render_wireframe(
            model,
            rotation=(20, 0, 0),  # Fixed: top-down 3D view
            position=position,
            scale=None,           # Auto-scale to fit
            z_depth=payload.z,
            fov=payload.fov,
            distance=payload.distance,
        )

        # Apply stereo depth
        left_layers, right_layers = compute_depth([(bmp, (payload.z + 5) / 10.0)], MAX_DISPARITY)
        left_bmp = compose_layers(left_layers)
        right_bmp = compose_layers(right_layers)

        left_ok, right_ok = await asyncio.gather(
            send_bmp_to_glass(manager.left_glass, left_bmp),
            send_bmp_to_glass(manager.right_glass, right_bmp),
        )

        return {"method": "3d_model", "left": left_ok, "right": right_ok}
    except Exception as e:
        logger.exception("3D send error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/events/stream")
async def events_stream():
    """SSE stream of BLE events (taps, wear, debug)."""
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
    _event_subscribers.append(q)

    async def _generate():
        try:
            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield f"data: {line}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            try:
                _event_subscribers.remove(q)
            except ValueError:
                pass

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/connect-stream")
async def connect_stream():
    """
    SSE stream: scan, connect, time sync, and install event handlers.
    Yields log lines, then __DONE__{status_json} or __FAIL__{error}.
    """
    global is_connecting, manager
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=500)
    loop = asyncio.get_running_loop()

    class _QueueHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                msg = self.format(record)
                loop.call_soon_threadsafe(queue.put_nowait, msg)
            except Exception:
                pass

    handler = _QueueHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))

    # "protocol" is the parent of protocol.connect, so its records propagate
    # up to this handler. Without it the stream carries only bleak's own
    # output and the activity log stays empty through the whole scan.
    _targets = [
        logging.getLogger("bleak"),
        logging.getLogger("protocol"),
        logger,
    ]
    _prev_levels = [(lg, lg.level) for lg in _targets]
    for lg in _targets:
        lg.addHandler(handler)
        if lg.level == logging.NOTSET or lg.level > logging.INFO:
            lg.setLevel(logging.INFO)

    done = asyncio.Event()
    result: dict = {}

    async def _do_connect() -> None:
        global is_connecting, manager
        if is_connecting:
            result["error"] = "Already connecting"
            done.set()
            return

        is_connecting = True
        try:
            manager = GlassesManager()
            connected = await manager.scan_and_connect(timeout=12)

            if connected:
                await manager.sync_time()
                manager.set_event_handler(_on_glass_event)

            result["status"] = _connection_status()
            result["success"] = connected
        except Exception as exc:
            result["error"] = str(exc)
            result["success"] = False
        finally:
            is_connecting = False
            done.set()

    async def _generate():
        try:
            asyncio.create_task(_do_connect())
            while not done.is_set():
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=0.2)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
            while not queue.empty():
                yield f"data: {queue.get_nowait()}\n\n"
            if result.get("success"):
                yield f"data: __DONE__{json.dumps(result['status'])}\n\n"
            else:
                err = result.get("error", "No glasses found during scan")
                yield f"data: __FAIL__{err}\n\n"
        finally:
            for lg in _targets:
                lg.removeHandler(handler)
            for lg, lvl in _prev_levels:
                lg.setLevel(lvl)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/send-text")
async def send_text_endpoint(payload: TextPayload):
    """Send text in manual-page mode (tap to advance)."""
    if not manager.left_glass and not manager.right_glass:
        raise HTTPException(status_code=503, detail="Not connected to glasses")
    try:
        await send_text(manager, payload.text)
        return {"status": "sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/preview-compose")
async def preview_compose(payload: ComposePayload):
    """
    Preview composition without sending to glasses.
    Returns base64-encoded left and right eye stereo BMPs.
    """
    try:
        from protocol.bmp import render_text_block, compose_layers, compute_depth, to_bmp_bytes
        import base64

        if not payload.layers:
            raise ValueError("No layers to compose")

        layers = []
        for layer in payload.layers:
            bmp = None

            if layer.get("type") == "text":
                text = layer.get("text", "").strip()
                if text:
                    bmp = render_text_block(
                        text,
                        position=layer.get("position", "bottom-left"),
                        size=layer.get("size", 14),
                        padding=layer.get("padding", 14)
                    )
            elif layer.get("type") == "image":
                image_data = layer.get("imageData")
                if image_data:
                    try:
                        image_bytes = base64.b64decode(image_data)
                        bmp = to_bmp_bytes(image_bytes)
                    except Exception as e:
                        logger.error(f"Failed to decode image layer: {e}")
                        continue

            if bmp:
                z_norm = (layer.get("z", 0) + 5) / 10.0
                layers.append((bmp, z_norm))

        if not layers:
            raise ValueError("No valid text or image layers to compose")

        left_layers, right_layers = compute_depth(layers, MAX_DISPARITY)
        left_bmp = compose_layers(left_layers)
        right_bmp = compose_layers(right_layers)

        left_b64 = base64.b64encode(left_bmp).decode('utf-8')
        right_b64 = base64.b64encode(right_bmp).decode('utf-8')

        return {
            "left": f"data:image/bmp;base64,{left_b64}",
            "right": f"data:image/bmp;base64,{right_b64}",
            "layers": len(layers)
        }
    except Exception as e:
        logger.exception("Preview error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/send-compose")
async def send_compose(payload: ComposePayload):
    """
    Unified composition pipeline: all layers (text + image) through same processing.
    Pipeline: Load bytes → Threshold to mono → Composite with depth → Send stereo pair.
    """
    if not manager.left_glass and not manager.right_glass:
        raise HTTPException(status_code=503, detail="Not connected to glasses")

    try:
        from protocol.bmp import render_text_block, compose_layers, compute_depth, to_bmp_bytes
        import base64

        if not payload.layers:
            raise ValueError("No layers to compose")

        is_simple_text = (
            len(payload.layers) == 1 and
            payload.layers[0].get("type") == "text" and
            payload.layers[0].get("position") == "bottom-left" and
            payload.layers[0].get("z") == 0
        )

        if is_simple_text:
            await send_text(manager, payload.layers[0]["text"])
            return {"method": "native_text", "layers": 1}

        layers = []
        for layer in payload.layers:
            bmp = None

            if layer.get("type") == "text":
                text = layer.get("text", "").strip()
                if text:
                    bmp = render_text_block(
                        text,
                        position=layer.get("position", "bottom-left"),
                        size=layer.get("size", 14),
                        padding=layer.get("padding", 14)
                    )
            elif layer.get("type") == "image":
                image_data = layer.get("imageData")
                if image_data:
                    try:
                        image_bytes = base64.b64decode(image_data)
                        bmp = to_bmp_bytes(image_bytes)
                    except Exception as e:
                        logger.error(f"Failed to decode image layer: {e}")
                        continue

            if bmp:
                z_norm = (layer.get("z", 0) + 5) / 10.0
                layers.append((bmp, z_norm))

        if not layers:
            raise ValueError("No valid text or image layers to compose")

        left_layers, right_layers = compute_depth(layers, MAX_DISPARITY)
        left_bmp = compose_layers(left_layers)
        right_bmp = compose_layers(right_layers)

        left_ok, right_ok = await asyncio.gather(
            send_bmp_to_glass(manager.left_glass, left_bmp),
            send_bmp_to_glass(manager.right_glass, right_bmp),
        )

        return {"method": "stereo_bmp", "left": left_ok, "right": right_ok, "layers": len(layers)}
    except Exception as e:
        logger.exception("Compose error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/send-stereo-compose")
async def send_stereo_compose(layers: list[tuple[bytes, float]], max_disparity: int = 10):
    """
    Send stereo image pair with depth.
    Layers: list of (image_bytes, z_depth) where z ∈ [0.0, 1.0].
    """
    if not manager.left_glass and not manager.right_glass:
        raise HTTPException(status_code=503, detail="Not connected to glasses")

    try:
        left_bmp, right_bmp = stereo_pair(layers, max_disparity)

        left_ok, right_ok = await asyncio.gather(
            send_bmp_to_glass(manager.left_glass, left_bmp),
            send_bmp_to_glass(manager.right_glass, right_bmp),
        )

        return {"left": left_ok, "right": right_ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/send-brief")
async def send_brief(payload: BriefPayload):
    """Render the morning brief and push each screen straight to the glasses.

    No preview step: screens are composed as stereo depth planes and sent in
    sequence, holding each for dwellSeconds.
    """
    if not manager.left_glass and not manager.right_glass:
        raise HTTPException(status_code=503, detail="Not connected to glasses")

    try:
        from protocol.brief import BriefInput, Block, render_brief, calc_power, calc_tier
        from protocol.bmp import compute_depth, compose_layers

        data = BriefInput(
            energy=payload.energy,
            focus=payload.focus,
            t_start=payload.tStart,
            t_end=payload.tEnd,
            week_priority=payload.weekPriority,
            one_thing=payload.oneThing,
            domain=payload.domain,
            stop_criteria=payload.stopCriteria,
            checks=payload.checks,
            blocks=[Block(b.name, b.start, b.end) for b in payload.blocks],
        )

        if not payload.screens:
            raise ValueError("No screens selected")

        # ── Text mode ────────────────────────────────────────────────────────
        # Goes through send_text() -> send_page(), which renders with
        # DisplayStatus.SIMPLE_TEXT (0x70): the direct path, no Even AI chrome.
        # Explicitly NOT MANUAL_PAGE (0x50) or NORMAL_TEXT (0x30), which route
        # through Even AI and bring the recording overlay. Paging is handled by
        # the touchpads via _on_glass_event -> step_text_page.
        if payload.mode == "text":
            from protocol.brief import render_brief_text

            body = render_brief_text(data, payload.screens)
            await send_text(manager, body)

            pages = len(body.split("\n")) // 5
            tier, _ = calc_tier(data.energy, data.focus, data.window_minutes)
            logger.info("Brief sent as raw text: %d page(s)", pages)
            return {
                "mode": "text",
                "pages": pages,
                "tier": tier,
                "power": calc_power(data.energy, data.focus, data.checks_done),
            }

        # ── Image mode ───────────────────────────────────────────────────────
        screens = render_brief(data, payload.screens)
        if not screens:
            raise ValueError("No screens selected")

        # The first BMP transfer after a fresh connect tends to miss its ACK;
        # give the link a moment to settle before the first screen.
        await asyncio.sleep(BRIEF_SETTLE)

        sent = []
        for i, screen in enumerate(screens):
            # brief.py emits z on the -5..+5 UI scale; compute_depth wants 0..1.
            # Composing directly rather than via stereo_pair(): the planes are
            # already display-ready BMPs, and stereo_pair calls to_bmp_bytes()
            # with an invert= kwarg that function does not accept.
            layers = [(bmp, (z + 5) / 10.0) for bmp, z in screen["layers"]]
            left_layers, right_layers = compute_depth(layers, payload.maxDisparity)
            left_bmp = compose_layers(left_layers)
            right_bmp = compose_layers(right_layers)

            # Sequential, not asyncio.gather: the G1 wire protocol is
            # send-left / wait-ACK / send-right. Sending both eyes at once
            # makes the end-of-transfer ACK fail intermittently.
            left_ok = await send_bmp_to_glass(manager.left_glass, left_bmp)
            await asyncio.sleep(BRIEF_EYE_GAP)
            right_ok = await send_bmp_to_glass(manager.right_glass, right_bmp)
            logger.info("Brief screen '%s' sent (L=%s R=%s)", screen["name"], left_ok, right_ok)
            sent.append({"screen": screen["name"], "left": left_ok, "right": right_ok})

            if i < len(screens) - 1:
                await asyncio.sleep(payload.dwellSeconds)

        tier, _ = calc_tier(data.energy, data.focus, data.window_minutes)
        return {
            "mode": "image",
            "sent": sent,
            "tier": tier,
            "power": calc_power(data.energy, data.focus, data.checks_done),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("send-brief error")
        raise HTTPException(status_code=500, detail=str(e))


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
