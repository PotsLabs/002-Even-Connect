"""
G1 BMP image pipeline — encoding, framing, CRC, and layer composition with z-depth.

Sources:
  - eveng1_python_sdk/services/display.py (_build_image_frames, _crc_command)
  - even_glasses/utils.py (construct_bmp_data_packet, construct_crc_check_command)
  - api_v2.py (_img_bmp_bytes, _compute_depth, _compose_bmp)
  - g1-sample G1BluetoothManager.swift

Depth control:
  Single depth mapping function: z ∈ [0.0, 1.0] → pixel shift via compute_depth().
  No point-cloud depth maps — use explicit z-values for all layers.

Usage:
    bmp = to_bmp_bytes(image_bytes)                  # any format → 1-bit 576×136 BMP
    left, right = compute_depth([(bmp, 0.5)], max_disparity=10)
    left_final = compose_layers(left)                # blend layers with AND logic
    frames = build_frames(left_final)                # list of 0x15 packets
    crc = build_crc_cmd(left_final)                  # [0x16, crc32be...]

Text composition:
    blocks = [{"text": "hello", "position": "bottom-left", "size": 14, ...}]
    bmp = compose_text_blocks(blocks)                # render text blocks to BMP
"""

import io
import zlib
from PIL import Image, ImageOps, ImageDraw, ImageFont

from .constants import BMP_WIDTH, BMP_HEIGHT, BMP_PACKET_SIZE, BMP_ADDR, BMP_END_CMD
from .commands import build_display_complete


# Re-export so callers can do: from protocol.bmp import ...
__all__ = [
    "to_bmp_bytes",
    "build_frames",
    "build_crc_cmd",
    "BMP_END_CMD",
    "DISPLAY_COMPLETE",
    "compute_depth",
    "compose_layers",
    "compose_text_blocks",
    "render_text_block",
]

DISPLAY_COMPLETE = build_display_complete()


# ── Image conversion ───────────────────────────────────────────────────────────

def _letterbox(img: Image.Image) -> Image.Image:
    """Fit image into 576×136 on a black canvas, preserving aspect ratio."""
    img = img.convert("L")
    img.thumbnail((BMP_WIDTH, BMP_HEIGHT), Image.LANCZOS)
    canvas = Image.new("L", (BMP_WIDTH, BMP_HEIGHT), 0)
    canvas.paste(img, ((BMP_WIDTH - img.width) // 2, (BMP_HEIGHT - img.height) // 2))
    return canvas


def to_bmp_bytes(image_bytes: bytes) -> bytes:
    """
    Convert any image format to a 1-bit 576×136 BMP ready for the glasses.
    No inversion applied - send image as-is to glasses.
    """
    canvas = _letterbox(Image.open(io.BytesIO(image_bytes)))
    bmp = canvas.point(lambda p: 255 if p > 64 else 0).convert("1")
    buf = io.BytesIO()
    bmp.save(buf, format="BMP")
    return buf.getvalue()


# ── Frame building ─────────────────────────────────────────────────────────────

def build_frames(bmp_data: bytes) -> list[bytes]:
    """
    Wrap BMP data in 0x15 protocol frames (194 bytes each).
    First frame includes the 4-byte BMP_ADDR; subsequent frames do not.
    Source: eveng1_python_sdk display.py _build_image_frames.
    """
    frames, offset, seq = [], 0, 0
    while offset < len(bmp_data):
        chunk = bmp_data[offset:offset + BMP_PACKET_SIZE]
        header = bytes([0x15, seq & 0xFF]) + (BMP_ADDR if seq == 0 else b"")
        frames.append(header + chunk)
        offset += BMP_PACKET_SIZE
        seq += 1
    return frames


def build_crc_cmd(bmp_data: bytes) -> bytes:
    """
    [0x16, crc32_big_endian(addr + bmp_data)] — CRC verification command.
    CRC input includes the 4-byte BMP_ADDR prefix, matching glasses firmware.
    """
    crc = zlib.crc32(BMP_ADDR + bmp_data) & 0xFFFFFFFF
    return bytes([
        0x16,
        (crc >> 24) & 0xFF,
        (crc >> 16) & 0xFF,
        (crc >> 8)  & 0xFF,
        crc         & 0xFF,
    ])


# ── Layer blending with z-depth ───────────────────────────────────────────────

def compute_depth(layers: list[tuple[bytes, float]], max_disparity: int) -> tuple[list, list]:
    """
    Split layers into left/right eyes based on depth (z-value).
    z=0.0 → no shift, z=1.0 → full disparity shift.
    Returns (left_layers, right_layers), each as list of (bmp_bytes, x_shift).
    """
    left_layers, right_layers = [], []
    for bmp_bytes, z in layers:
        shift = int(round(z * max_disparity))
        left_layers.append((bmp_bytes, -shift))
        right_layers.append((bmp_bytes, +shift))
    return left_layers, right_layers


def compose_layers(layers: list[tuple[bytes, int]]) -> bytes:
    """
    Blend inverted BMPs with AND logic (np.minimum).
    Each layer is (bmp_bytes, x_shift): negative shift = left, positive = right.
    Returns single 1-bit BMP with all layers composited.
    """
    import numpy as np

    canvas = np.full((BMP_HEIGHT, BMP_WIDTH), 255, dtype=np.uint8)
    for bmp_bytes, x_shift in layers:
        layer = np.array(Image.open(io.BytesIO(bmp_bytes)).convert("L"), dtype=np.uint8)

        if x_shift > 0:
            shifted = np.full_like(layer, 255)
            shifted[:, x_shift:] = layer[:, :BMP_WIDTH - x_shift]
        elif x_shift < 0:
            shifted = np.full_like(layer, 255)
            shifted[:, :BMP_WIDTH + x_shift] = layer[:, -x_shift:]
        else:
            shifted = layer

        canvas = np.minimum(canvas, shifted)

    buf = io.BytesIO()
    Image.fromarray(canvas).convert("1").save(buf, format="BMP")
    return buf.getvalue()


# ── Text rendering ───────────────────────────────────────────────────────────

def _load_font(size: int = 14):
    """Load a font with size support. Defaults to system font or PIL's default."""
    try:
        # PIL 10.0.0+ supports size on load_default
        return ImageFont.load_default(size=size)
    except (TypeError, AttributeError):
        # Fallback for older PIL or if size not supported
        try:
            # Try to load a common system font with size
            import pathlib
            for path_str in [
                "/System/Library/Fonts/Monaco.ttf",        # macOS
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Linux
                "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",  # Linux
            ]:
                path = pathlib.Path(path_str)
                if path.exists():
                    return ImageFont.truetype(str(path), size=size)
        except Exception:
            pass
        # Ultimate fallback
        return ImageFont.load_default()


def _get_position_xy(text_bbox, position: str, canvas_w: int, canvas_h: int, padding: int = 0):
    """Calculate (x, y) for text given position name and padding."""
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]

    pos_map = {
        'top-left': (padding, padding),
        'top-center': ((canvas_w - text_w) // 2, padding),
        'top-right': (canvas_w - text_w - padding, padding),
        'middle-left': (padding, (canvas_h - text_h) // 2),
        'middle-center': ((canvas_w - text_w) // 2, (canvas_h - text_h) // 2),
        'middle-right': (canvas_w - text_w - padding, (canvas_h - text_h) // 2),
        'bottom-left': (padding, canvas_h - text_h - padding),
        'bottom-center': ((canvas_w - text_w) // 2, canvas_h - text_h - padding),
        'bottom-right': (canvas_w - text_w - padding, canvas_h - text_h - padding),
    }
    return pos_map.get(position, pos_map['bottom-left'])


def render_text_block(text: str, position: str = "bottom-left", size: int = 14, padding: int = 0) -> bytes:
    """
    Render a single text block to 1-bit BMP (dark mode: black text on white).
    Size parameter controls font size (14px default).
    """
    canvas = Image.new("L", (BMP_WIDTH, BMP_HEIGHT), 255)
    draw = ImageDraw.Draw(canvas)
    font = _load_font(size)

    bbox = draw.textbbox((0, 0), text, font=font)
    x, y = _get_position_xy(bbox, position, BMP_WIDTH, BMP_HEIGHT, padding)
    draw.text((x, y), text, fill=0, font=font)

    bmp = canvas.point(lambda p: 255 if p > 64 else 0).convert("1")
    buf = io.BytesIO()
    bmp.save(buf, format="BMP")
    return buf.getvalue()


def compose_text_blocks(blocks: list[dict], background_bytes: bytes | None = None) -> bytes:
    """
    Render text blocks onto optional background image (dark mode: black text on white).
    Each block: {"text": str, "position": str, "size": int, "padding": int}
    Size defaults to 14 if not specified. Returns final composed BMP ready to send.
    """
    if background_bytes:
        canvas = _letterbox(Image.open(io.BytesIO(background_bytes)))
        canvas = canvas.convert("L")
    else:
        canvas = Image.new("L", (BMP_WIDTH, BMP_HEIGHT), 255)

    draw = ImageDraw.Draw(canvas)

    for block in blocks:
        text = block.get("text", "")
        if not text.strip():
            continue

        position = block.get("position", "bottom-left")
        padding = block.get("padding", 0)
        size = block.get("size", 14)
        font = _load_font(size)

        bbox = draw.textbbox((0, 0), text, font=font)
        x, y = _get_position_xy(bbox, position, BMP_WIDTH, BMP_HEIGHT, padding)
        draw.text((x, y), text, fill=0, font=font)

    bmp = canvas.point(lambda p: 255 if p > 64 else 0).convert("1")
    buf = io.BytesIO()
    bmp.save(buf, format="BMP")
    return buf.getvalue()
