import asyncio
import base64
import io
import json
import logging
import sys
import os
import zlib
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "even_glasses"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
import numpy as np
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from even_glasses.bluetooth_manager import GlassesManager
from even_glasses.commands import format_text_lines, send_text_packet

# ── Image transmission (eveng1_python_sdk protocol) ────────────────────────
_IMG_W       = 576
_IMG_H       = 136
_PACKET_SIZE = 194
_BMP_ADDR    = bytes([0x00, 0x1C, 0x00, 0x00])
_UART_TX     = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"


def _to_bmp_bytes(image_bytes: bytes) -> bytes:
    """Convert raw image bytes → 1-bit 576×136 BMP, letterboxed on a black canvas."""
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img.thumbnail((_IMG_W, _IMG_H), Image.LANCZOS)
    canvas = Image.new("L", (_IMG_W, _IMG_H), 0)
    canvas.paste(img, ((_IMG_W - img.width) // 2, (_IMG_H - img.height) // 2))
    bmp_img = canvas.point(lambda p: 255 if p > 64 else 0).convert("1")
    buf = io.BytesIO()
    bmp_img.save(buf, format="BMP")
    return buf.getvalue()


def _invert_bmp(bmp_data: bytes) -> bytes:
    """Invert the pixels of a 1-bit BMP (required by the glasses display protocol)."""
    img = ImageOps.invert(Image.open(io.BytesIO(bmp_data)).convert("L"))
    buf = io.BytesIO()
    img.convert("1").save(buf, format="BMP")
    return buf.getvalue()


def _to_ready_bmp(image_bytes: bytes) -> bytes:
    """Single-pass: resize, threshold, and invert — skips the double PIL round-trip."""
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img.thumbnail((_IMG_W, _IMG_H), Image.LANCZOS)
    canvas = Image.new("L", (_IMG_W, _IMG_H), 0)
    canvas.paste(img, ((_IMG_W - img.width) // 2, (_IMG_H - img.height) // 2))
    # Invert threshold inline: dark where bright → matches glasses display polarity
    bmp_img = canvas.point(lambda p: 0 if p > 64 else 255).convert("1")
    buf = io.BytesIO()
    bmp_img.save(buf, format="BMP")
    return buf.getvalue()


# ── Precomputed frame cache ────────────────────────────────────────────────
# Stores ready-to-transmit frames keyed by client-provided ID.
# Shape: {id: {"mode": str, "frames": list[bytes], "crc": bytes}
#              or {"mode": "stereo", "left_frames": ..., "right_frames": ...,
#                  "left_crc": ..., "right_crc": ...}}
_frame_cache: dict[str, dict] = {}

# ── Font utilities for compose ─────────────────────────────────────────────
_FONT_PATHS = [
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
]

_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if size in _font_cache:
        return _font_cache[size]
    for path in _FONT_PATHS:
        if not os.path.exists(path):
            continue
        try:
            kw = {"index": 0} if path.endswith(".ttc") else {}
            font = ImageFont.truetype(path, size, **kw)
            _font_cache[size] = font
            return font
        except Exception:
            continue
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:
        font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def _compose_bmp(background_b64: str, blocks: list) -> bytes:
    """Composite a background image + text layers into a 576×136 ready-to-transmit BMP."""
    if background_b64:
        img = Image.open(io.BytesIO(base64.b64decode(background_b64))).convert("L")
        img.thumbnail((_IMG_W, _IMG_H), Image.LANCZOS)
        canvas = Image.new("L", (_IMG_W, _IMG_H), 0)
        canvas.paste(img, ((_IMG_W - img.width) // 2, (_IMG_H - img.height) // 2))
    else:
        canvas = Image.new("L", (_IMG_W, _IMG_H), 0)

    draw = ImageDraw.Draw(canvas)

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        font = _get_font(block.size)
        fill = 255 if block.color == "light" else 0

        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=2)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        v, _, h = block.position.partition("-")
        pad = block.padding

        if h == "left":    x = pad
        elif h == "center": x = max(0, (_IMG_W - tw) // 2)
        else:              x = max(0, _IMG_W - tw - pad)

        if v == "top":     y = pad
        elif v == "middle": y = max(0, (_IMG_H - th) // 2)
        else:              y = max(0, _IMG_H - th - pad)

        draw.multiline_text((x, y), text, font=font, fill=fill, spacing=2)

    bmp_img = canvas.point(lambda p: 0 if p > 64 else 255).convert("1")
    buf = io.BytesIO()
    bmp_img.save(buf, format="BMP")
    return buf.getvalue()


def _build_image_frames(bmp_data: bytes) -> list[bytes]:
    """Wrap 194-byte BMP chunks in the 0x15 protocol frame."""
    frames, offset, seq = [], 0, 0
    while offset < len(bmp_data):
        chunk = bmp_data[offset : offset + _PACKET_SIZE]
        header = bytes([0x15, seq & 0xFF]) + (_BMP_ADDR if seq == 0 else b"")
        frames.append(header + chunk)
        offset += _PACKET_SIZE
        seq += 1
    return frames


def _crc_command(bmp_data: bytes) -> bytes:
    """CRC32 (big-endian) over storage address + BMP data, prefixed with 0x16."""
    crc = zlib.crc32(_BMP_ADDR + bmp_data) & 0xFFFFFFFF
    return bytes([0x16, (crc >> 24) & 0xFF, (crc >> 16) & 0xFF,
                  (crc >> 8) & 0xFF, crc & 0xFF])


def _to_stereo_bmp_pair(
    image_bytes: bytes,
    max_disparity: int = 6,
    blur_radius: float = 3.0,
    invert_depth: bool = False,
) -> tuple[bytes, bytes]:
    """Generate a left/right 1-bit BMP stereo pair using luminance as a depth proxy.

    Bright pixels are treated as near (large shift), dark as far (no shift) by default.
    Set invert_depth=True to flip this, useful for dark-on-light content like point clouds.
    blur_radius controls depth map smoothing — higher values reduce edge fringing but
    bleed depth across object boundaries.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img.thumbnail((_IMG_W, _IMG_H), Image.LANCZOS)
    canvas = Image.new("L", (_IMG_W, _IMG_H), 0)
    canvas.paste(img, ((_IMG_W - img.width) // 2, (_IMG_H - img.height) // 2))

    depth_img = canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius)) if blur_radius > 0 else canvas

    arr   = np.array(canvas,    dtype=np.float32) / 255.0
    depth = np.array(depth_img, dtype=np.float32) / 255.0

    if invert_depth:
        depth = 1.0 - depth

    shift_map = np.round(depth * max_disparity).astype(np.int32)

    h, w = arr.shape
    y_idx, x_idx = np.mgrid[0:h, 0:w]

    # Left eye: sample from x - shift → foreground appears displaced right → in front
    left_arr  = arr[y_idx, np.clip(x_idx - shift_map, 0, w - 1)]
    # Right eye: sample from x + shift → foreground appears displaced left → in front
    right_arr = arr[y_idx, np.clip(x_idx + shift_map, 0, w - 1)]

    def _finalize(a: np.ndarray) -> bytes:
        img_l = Image.fromarray((a * 255).astype(np.uint8), mode="L")
        img_1bit = img_l.point(lambda p: 255 if p > 64 else 0).convert("1")
        buf = io.BytesIO()
        ImageOps.invert(img_1bit.convert("L")).convert("1").save(buf, format="BMP")
        return buf.getvalue()

    return _finalize(left_arr), _finalize(right_arr)


_TEXT_SHOW = 0x71  # 0x70 (Text Show) | 0x01 (New Content)

# Weekday mapping: Python's weekday() is 0=Mon…6=Sun; glasses expect 0=Sun…6=Sat
_PY_TO_GLASS_WEEKDAY = [1, 2, 3, 4, 5, 6, 0]


def _construct_time_sync() -> bytes:
    """Build the Even G1 INIT (0x4D) time-sync packet from the current system time."""
    now = datetime.now()
    year = now.year
    return bytes([
        0x4D,                    # Command: INIT / time sync
        0x0B, 0x00,              # Payload length: 11 bytes, little-endian
        year & 0xFF,             # Year low byte
        (year >> 8) & 0xFF,      # Year high byte
        now.month,
        now.day,
        now.hour,
        now.minute,
        now.second,
        _PY_TO_GLASS_WEEKDAY[now.weekday()],
        0x00, 0x00,              # Reserved
    ])


async def _sync_time(manager) -> None:
    """Send the current system time to both glasses."""
    cmd = _construct_time_sync()
    if manager.left_glass and manager.left_glass.client.is_connected:
        await manager.left_glass.send(cmd)
    if manager.right_glass and manager.right_glass.client.is_connected:
        await manager.right_glass.send(cmd)


# ── Touchpad / state event broadcast ──────────────────────────────────────
# All 0xF5 subcommand codes the glasses can send.
_INTERACTION_LABELS: dict[int, str] = {
    0x00: "Double Tap",
    0x01: "Single Tap",
    0x02: "Dashboard Open",
    0x03: "Dashboard Close",
    0x04: "Silent Mode On",
    0x05: "Silent Mode Off",
    0x06: "Worn",
    0x07: "Taken Off",
    0x08: "Cradle Open",
    0x09: "Cradle Charged",
    0x0B: "Cradle Closed",
    0x11: "Device Connected",
    0x17: "Long Press",
    0x18: "Long Press Released",
    0x1E: "Dashboard Confirmed Open",
    0x1F: "Dashboard Confirmed Close",
}

# One asyncio.Queue per active SSE subscriber — broadcasts to all open tabs.
_event_subscribers: list[asyncio.Queue] = []


def _broadcast(line: str) -> None:
    for q in _event_subscribers:
        try:
            q.put_nowait(line)
        except asyncio.QueueFull:
            pass


_KNOWN_SILENT = {0x25}  # heartbeat ack — too noisy to show


async def _glass_event_handler(glass, sender, data: bytes) -> None:
    """Log every inbound BLE notification so we can observe what the firmware actually sends."""
    if not data:
        return
    cmd = data[0]

    # Skip known high-frequency noise
    if cmd in _KNOWN_SILENT:
        return

    # Named interpretation if we recognise it
    if cmd == 0xF5 and len(data) >= 2:
        code = data[1]
        label = _INTERACTION_LABELS.get(code, f"unknown sub 0x{code:02x}")
        _broadcast(f"INFO:touchpad:{glass.side} — {label}  raw={data.hex()}")
    elif cmd == 0x27 and len(data) >= 2:
        status_byte = data[1]
        label = "Worn" if status_byte == 0x01 else "Taken Off"
        _broadcast(f"INFO:wear:{glass.side} — {label}  raw={data.hex()}")
    else:
        # Unknown — show raw bytes so we can map new events
        _broadcast(f"DEBUG:ble:{glass.side} cmd=0x{cmd:02x}  raw={data.hex()}")


def _install_event_handlers(mgr) -> None:
    """Attach the event handler to both glasses after a successful connect."""
    if mgr.left_glass:
        mgr.left_glass.notification_handler = _glass_event_handler
    if mgr.right_glass:
        mgr.right_glass.notification_handler = _glass_event_handler


async def _send_text(manager, text_message: str, duration: float = 5) -> None:
    """Send text using the correct 0x70 Text Show status, not the EvenAI 0x30 status."""
    lines = format_text_lines(text_message)
    total_pages = max(1, (len(lines) + 4) // 5)

    for pn, page_start in enumerate(range(0, len(lines), 5), start=1):
        page_lines = lines[page_start : page_start + 5]
        if len(page_lines) < 5:
            padding = (5 - len(page_lines)) // 2
            page_lines = (
                [""] * padding + page_lines + [""] * (5 - len(page_lines) - padding)
            )
        await send_text_packet(
            manager=manager,
            text_message="\n".join(page_lines),
            page_number=pn,
            max_pages=total_pages,
            screen_status=_TEXT_SHOW,
        )
        if pn != total_pages:
            await asyncio.sleep(duration)


async def _glass_request(glass, cmd: bytes, resp_byte_idx: int, timeout: float = 3.0) -> bool:
    """Write cmd to a glass and verify the protocol response has 0xC9 at resp_byte_idx."""
    q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
    original_handler = glass.notification_handler

    async def _capture(g, sender, data: bytes) -> None:
        if q.empty():
            await q.put(data)

    glass.notification_handler = _capture
    try:
        await glass.client.write_gatt_char(_UART_TX, cmd, response=True)
        data = await asyncio.wait_for(q.get(), timeout=timeout)
        return len(data) > resp_byte_idx and data[resp_byte_idx] == 0xC9
    except (asyncio.TimeoutError, Exception):
        return False
    finally:
        glass.notification_handler = original_handler


async def _send_image_to_glass(glass, frames: list[bytes], end_cmd: bytes, crc_cmd: bytes) -> bool:
    """Send BMP data to one glass with end-of-transfer and CRC verification."""
    for frame in frames:
        await glass.client.write_gatt_char(_UART_TX, frame, response=False)
        await asyncio.sleep(0.002)

    # End command: glasses respond with 0xC9 at byte index 1 on success
    if not await _glass_request(glass, end_cmd, resp_byte_idx=1):
        return False

    # CRC command: glasses respond with 0xC9 at byte index 5 on success
    return await _glass_request(glass, crc_cmd, resp_byte_idx=5)


async def _transmit_image(left_glass, right_glass, bmp_data: bytes) -> dict:
    """Send BMP to both glasses concurrently and return per-side success."""
    frames  = _build_image_frames(bmp_data)
    end_cmd = bytes([0x20, 0x0D, 0x0E])
    crc_cmd = _crc_command(bmp_data)

    left_ok, right_ok = await asyncio.gather(
        _send_image_to_glass(left_glass, frames, end_cmd, crc_cmd),
        _send_image_to_glass(right_glass, frames, end_cmd, crc_cmd),
    )
    return {"left": left_ok, "right": right_ok}

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager: GlassesManager = GlassesManager()
is_connecting = False


def _connection_status() -> dict:
    left_ok = bool(manager.left_glass and manager.left_glass.client.is_connected)
    right_ok = bool(manager.right_glass and manager.right_glass.client.is_connected)
    return {
        "connected": left_ok or right_ok,
        "left": left_ok,
        "right": right_ok,
        "leftName": manager.left_glass.name if manager.left_glass else None,
        "rightName": manager.right_glass.name if manager.right_glass else None,
    }


@app.get("/api/status")
async def get_status():
    return _connection_status()


@app.post("/api/connect")
async def connect():
    global is_connecting, manager
    if is_connecting:
        raise HTTPException(status_code=409, detail="Already connecting")
    is_connecting = True
    try:
        manager = GlassesManager()
        connected = await manager.scan_and_connect(timeout=12)
        if not connected:
            raise HTTPException(status_code=503, detail="No glasses found during scan")
        await _sync_time(manager)
        _install_event_handlers(manager)
        return _connection_status()
    finally:
        is_connecting = False


@app.post("/api/connect-stream")
async def connect_stream():
    """SSE endpoint that runs scan_and_connect and streams captured SDK logs in real time."""
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

    # Attach to the SDK and BLE library loggers, save their previous levels
    _targets = [logging.getLogger("even_glasses"), logging.getLogger("bleak")]
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
                await _sync_time(manager)
                _install_event_handlers(manager)
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
            # drain anything logged right at completion
            while not queue.empty():
                yield f"data: {queue.get_nowait()}\n\n"
            # terminal signal
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


@app.post("/api/disconnect")
async def disconnect():
    await manager.disconnect_all()
    return {"connected": False}


@app.get("/api/events/stream")
async def events_stream():
    """SSE stream of touchpad and wear events from the glasses."""
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


class TextPayload(BaseModel):
    text: str


@app.post("/api/send-text")
async def send_text_endpoint(payload: TextPayload):
    status = _connection_status()
    if not status["connected"]:
        raise HTTPException(status_code=503, detail="Glasses not connected")
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text is empty")
    await _send_text(manager, payload.text)
    return {"success": True}


class ImagePayload(BaseModel):
    imageData: str  # base64-encoded image (any format)


@app.post("/api/send-image")
async def send_image_endpoint(payload: ImagePayload):
    status = _connection_status()
    if not status["connected"]:
        raise HTTPException(status_code=503, detail="Glasses not connected")

    left_glass  = manager.left_glass  if manager.left_glass  else None
    right_glass = manager.right_glass if manager.right_glass else None
    if not left_glass or not right_glass:
        raise HTTPException(status_code=503, detail="Both glasses must be connected to send an image")

    try:
        bmp_data = _invert_bmp(_to_bmp_bytes(base64.b64decode(payload.imageData)))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Image processing failed: {e}")

    result = await _transmit_image(left_glass, right_glass, bmp_data)
    if not all(result.values()):
        failed = [side for side, ok in result.items() if not ok]
        raise HTTPException(status_code=502, detail=f"Image transfer failed on: {', '.join(failed)}")

    return {"success": True}


# ── Precompute endpoints ───────────────────────────────────────────────────

class PrecomputeItem(BaseModel):
    id: str
    imageData: str
    mode: str = "standard"
    maxDisparity: int   = 6
    blurRadius:   float = 3.0
    invertDepth:  bool  = False

class PrecomputePayload(BaseModel):
    images: list[PrecomputeItem]


@app.post("/api/queue/precompute")
async def precompute_queue(payload: PrecomputePayload):
    """Convert images to transmit-ready frames in a thread pool and cache them."""
    loop = asyncio.get_running_loop()
    results, errors = [], []

    for item in payload.images:
        try:
            img_bytes = base64.b64decode(item.imageData)
            if item.mode == "stereo":
                left_bmp, right_bmp = await loop.run_in_executor(
                    None, _to_stereo_bmp_pair,
                    img_bytes, item.maxDisparity, item.blurRadius, item.invertDepth,
                )
                _frame_cache[item.id] = {
                    "mode": "stereo",
                    "left_frames":  _build_image_frames(left_bmp),
                    "right_frames": _build_image_frames(right_bmp),
                    "left_crc":     _crc_command(left_bmp),
                    "right_crc":    _crc_command(right_bmp),
                }
            else:
                bmp_data = await loop.run_in_executor(None, _to_ready_bmp, img_bytes)
                _frame_cache[item.id] = {
                    "mode":   "standard",
                    "frames": _build_image_frames(bmp_data),
                    "crc":    _crc_command(bmp_data),
                }
            results.append(item.id)
        except Exception as e:
            errors.append({"id": item.id, "error": str(e)})

    return {"precomputed": results, "errors": errors}


@app.post("/api/send-precomputed/{image_id}")
async def send_precomputed(image_id: str):
    """Transmit a previously precomputed image — no PIL work on the hot path."""
    if image_id not in _frame_cache:
        raise HTTPException(status_code=404, detail="Image not precomputed — add it via /api/queue/precompute first")

    status = _connection_status()
    if not status["connected"]:
        raise HTTPException(status_code=503, detail="Glasses not connected")

    left_glass  = manager.left_glass
    right_glass = manager.right_glass
    if not left_glass or not right_glass:
        raise HTTPException(status_code=503, detail="Both glasses must be connected")

    cached  = _frame_cache[image_id]
    end_cmd = bytes([0x20, 0x0D, 0x0E])

    if cached["mode"] == "stereo":
        left_ok, right_ok = await asyncio.gather(
            _send_image_to_glass(left_glass,  cached["left_frames"],  end_cmd, cached["left_crc"]),
            _send_image_to_glass(right_glass, cached["right_frames"], end_cmd, cached["right_crc"]),
        )
    else:
        left_ok, right_ok = await asyncio.gather(
            _send_image_to_glass(left_glass,  cached["frames"], end_cmd, cached["crc"]),
            _send_image_to_glass(right_glass, cached["frames"], end_cmd, cached["crc"]),
        )

    if not (left_ok and right_ok):
        failed = (["left"] if not left_ok else []) + (["right"] if not right_ok else [])
        raise HTTPException(status_code=502, detail=f"Transfer failed on: {', '.join(failed)}")

    return {"success": True}


@app.delete("/api/queue/precomputed/{image_id}")
async def delete_precomputed(image_id: str):
    _frame_cache.pop(image_id, None)
    return {"deleted": image_id}


# ── Compose endpoints ──────────────────────────────────────────────────────

class TextBlock(BaseModel):
    text:     str
    position: str = "bottom-left"
    size:     int = 18
    color:    str = "light"   # "light" → fill=255 in canvas; "dark" → fill=0
    padding:  int = 6

class ComposePayload(BaseModel):
    backgroundData: str = ""
    blocks: list[TextBlock]


def _bmp_to_preview_png(bmp_data: bytes) -> str:
    img = Image.open(io.BytesIO(bmp_data)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@app.post("/api/preview-compose")
async def preview_compose(payload: ComposePayload):
    try:
        loop = asyncio.get_running_loop()
        bmp = await loop.run_in_executor(None, _compose_bmp, payload.backgroundData, payload.blocks)
        return {"preview": _bmp_to_preview_png(bmp)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Compose failed: {e}")


@app.post("/api/send-compose")
async def send_compose(payload: ComposePayload):
    status = _connection_status()
    if not status["connected"]:
        raise HTTPException(status_code=503, detail="Glasses not connected")
    left_glass  = manager.left_glass
    right_glass = manager.right_glass
    if not left_glass or not right_glass:
        raise HTTPException(status_code=503, detail="Both glasses must be connected")
    try:
        loop = asyncio.get_running_loop()
        bmp = await loop.run_in_executor(None, _compose_bmp, payload.backgroundData, payload.blocks)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Compose failed: {e}")
    result = await _transmit_image(left_glass, right_glass, bmp)
    if not all(result.values()):
        failed = [s for s, ok in result.items() if not ok]
        raise HTTPException(status_code=502, detail=f"Transfer failed on: {', '.join(failed)}")
    return {"success": True}


@app.post("/api/precompute-compose")
async def precompute_compose(payload: ComposePayload):
    """Compose, cache frames, and return an ID + PNG thumbnail for the queue."""
    import uuid as _uuid
    try:
        loop = asyncio.get_running_loop()
        bmp = await loop.run_in_executor(None, _compose_bmp, payload.backgroundData, payload.blocks)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Compose failed: {e}")
    image_id = str(_uuid.uuid4())
    _frame_cache[image_id] = {
        "mode":   "standard",
        "frames": _build_image_frames(bmp),
        "crc":    _crc_command(bmp),
    }
    return {"id": image_id, "preview": _bmp_to_preview_png(bmp)}


@app.post("/api/preview-bmp")
async def preview_bmp(payload: ImagePayload):
    """Return a PNG preview of what the image looks like after BMP conversion."""
    try:
        bmp_data = _to_bmp_bytes(base64.b64decode(payload.imageData))
        # Re-open the BMP bytes and convert to RGB for PNG export
        preview_img = Image.open(io.BytesIO(bmp_data)).convert("RGB")
        png_buf = io.BytesIO()
        preview_img.save(png_buf, format="PNG")
        png_b64 = base64.b64encode(png_buf.getvalue()).decode()
        return {"preview": f"data:image/png;base64,{png_b64}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Preview failed: {e}")


class StereoImagePayload(BaseModel):
    imageData: str
    maxDisparity: int   = 6    # max horizontal pixel shift; 4–10 is comfortable for most displays
    blurRadius:   float = 3.0  # depth map Gaussian blur radius; higher = smoother transitions, more bleed
    invertDepth:  bool  = False # flip depth map; use for dark-on-light content (e.g. point clouds)


@app.post("/api/send-stereo-image")
async def send_stereo_image_endpoint(payload: StereoImagePayload):
    status = _connection_status()
    if not status["connected"]:
        raise HTTPException(status_code=503, detail="Glasses not connected")

    left_glass  = manager.left_glass  if manager.left_glass  else None
    right_glass = manager.right_glass if manager.right_glass else None
    if not left_glass or not right_glass:
        raise HTTPException(status_code=503, detail="Both glasses must be connected for stereo")

    try:
        left_bmp, right_bmp = _to_stereo_bmp_pair(
            base64.b64decode(payload.imageData),
            max_disparity=max(1, min(payload.maxDisparity, 20)),
            blur_radius=max(0.0, min(payload.blurRadius, 15.0)),
            invert_depth=payload.invertDepth,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stereo processing failed: {e}")

    end_cmd = bytes([0x20, 0x0D, 0x0E])
    left_ok, right_ok = await asyncio.gather(
        _send_image_to_glass(left_glass,  _build_image_frames(left_bmp),  end_cmd, _crc_command(left_bmp)),
        _send_image_to_glass(right_glass, _build_image_frames(right_bmp), end_cmd, _crc_command(right_bmp)),
    )

    if not (left_ok and right_ok):
        failed = (["left"] if not left_ok else []) + (["right"] if not right_ok else [])
        raise HTTPException(status_code=502, detail=f"Stereo transfer failed on: {', '.join(failed)}")

    return {"success": True}


@app.post("/api/preview-stereo-bmp")
async def preview_stereo_bmp(payload: StereoImagePayload):
    """Return PNG previews of both stereo halves after depth-shift processing."""
    try:
        left_bmp, right_bmp = _to_stereo_bmp_pair(
            base64.b64decode(payload.imageData),
            max_disparity=max(1, min(payload.maxDisparity, 20)),
            blur_radius=max(0.0, min(payload.blurRadius, 15.0)),
            invert_depth=payload.invertDepth,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Stereo preview failed: {e}")

    def _to_preview_png(bmp: bytes) -> str:
        img = Image.open(io.BytesIO(bmp)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    return {"left": _to_preview_png(left_bmp), "right": _to_preview_png(right_bmp)}


# Serve React build if it exists
_frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
