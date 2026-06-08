"""
G1 Glasses API — thin HTTP layer over protocol package.

All BLE communication, packet building, and image processing is in protocol/.
This file: FastAPI endpoints only.
"""

import asyncio
import json
import logging
import uvicorn

from fastapi import FastAPI, HTTPException
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

class TextBlock(BaseModel):
    text: str
    position: str = "bottom-left"
    size: int = 14
    color: str = "light"
    padding: int = 14
    z: int = 0


class ImageLayer(BaseModel):
    imageData: str
    position: str = "middle-center"
    z: float = 1


class ComposePayload(BaseModel):
    backgroundData: str = ""
    blocks: list[TextBlock] = []
    imageLayers: list[ImageLayer] = []


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

    _targets = [logging.getLogger("bleak")]
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
async def send_text_endpoint(text: str):
    """Send text in manual-page mode (tap to advance)."""
    if not manager.left_glass and not manager.right_glass:
        raise HTTPException(status_code=503, detail="Not connected to glasses")
    try:
        await send_text(manager, text)
        return {"status": "sent"}
    except Exception as e:
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


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
