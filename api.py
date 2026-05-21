import asyncio
import base64
import io
import json
import logging
import sys
import os
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "even_glasses"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
import numpy as np
from pydantic import BaseModel
from PIL import Image, ImageFilter, ImageOps

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
