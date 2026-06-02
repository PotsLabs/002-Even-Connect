"""
G1 BMP image pipeline — conversion, framing, CRC, and stereo depth.

Sources:
  - eveng1_python_sdk/services/display.py (_build_image_frames, _crc_command)
  - even_glasses/utils.py (construct_bmp_data_packet, construct_crc_check_command)
  - api.py (_to_bmp_bytes, _to_stereo_bmp_pair, _compose_bmp)
  - g1-sample G1BluetoothManager.swift (sendTextPacket dual-packet insight)

Usage:
    bmp  = to_bmp_bytes(image_bytes)            # any format → 1-bit 576×136 BMP
    frames = build_frames(bmp)                  # list of 0x15 packets
    end    = BMP_END_CMD                        # [0x20, 0x0D, 0x0E]
    crc    = build_crc_cmd(bmp)                 # [0x16, crc32be...]
    finish = DISPLAY_COMPLETE                   # send after CRC ack to clear overlay
"""

import io
import zlib
from PIL import Image, ImageOps

from .constants import BMP_WIDTH, BMP_HEIGHT, BMP_PACKET_SIZE, BMP_ADDR, BMP_END_CMD
from .commands import build_display_complete


# Re-export so callers can do: from protocol.bmp import BMP_END_CMD, DISPLAY_COMPLETE
__all__ = [
    "to_bmp_bytes",
    "to_bmp_bytes_inverted",
    "build_frames",
    "build_crc_cmd",
    "BMP_END_CMD",
    "DISPLAY_COMPLETE",
    "to_stereo_pair",
    "compose_bmp",
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


def to_bmp_bytes(image_bytes: bytes, invert: bool = True) -> bytes:
    """
    Convert any image format to a 1-bit 576×136 BMP ready for the glasses.
    invert=True: bright pixels → white on display (standard for photos/art).
    invert=False: dark pixels → white on display (standard for text/UI).
    """
    canvas = _letterbox(Image.open(io.BytesIO(image_bytes)))
    if invert:
        canvas = ImageOps.invert(canvas)
    bmp = canvas.point(lambda p: 255 if p > 64 else 0).convert("1")
    buf = io.BytesIO()
    bmp.save(buf, format="BMP")
    return buf.getvalue()


def to_bmp_bytes_inverted(image_bytes: bytes) -> bytes:
    """Alias: dark-on-light source (text, UI) → correct polarity for glasses."""
    return to_bmp_bytes(image_bytes, invert=False)


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


# ── Stereo depth ───────────────────────────────────────────────────────────────

def to_stereo_pair(
    image_bytes: bytes,
    max_disparity: int = 6,
    blur_radius: float = 3.0,
    invert_depth: bool = False,
    z_shift: float = 0.0,
) -> tuple[bytes, bytes]:
    """
    Generate left/right 1-bit BMP pair using luminance as a depth proxy.

    Bright pixels = near (large outward shift), dark pixels = far (no shift).
    Set invert_depth=True for dark-on-light content (point clouds, line art).
    z_shift: global depth offset in the range [-1.0, 1.0], mapped to ±max_disparity pixels.
    Source: api.py _to_stereo_bmp_pair (extended with z_shift support).
    """
    from PIL import ImageFilter
    import numpy as np

    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img.thumbnail((BMP_WIDTH, BMP_HEIGHT), Image.LANCZOS)
    canvas = Image.new("L", (BMP_WIDTH, BMP_HEIGHT), 0)
    canvas.paste(img, ((BMP_WIDTH - img.width) // 2, (BMP_HEIGHT - img.height) // 2))

    depth = canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    depth_arr = np.array(depth, dtype=np.float32) / 255.0

    if invert_depth:
        depth_arr = 1.0 - depth_arr

    global_shift = int(round(z_shift * max_disparity))

    def _make_eye(direction: int) -> bytes:
        shift_map = np.round(depth_arr * max_disparity).astype(int) + global_shift * direction
        src = np.array(canvas, dtype=np.uint8)
        out = np.zeros_like(src)
        for col in range(BMP_WIDTH):
            shifted = col + shift_map[:, col] * direction
            shifted = np.clip(shifted, 0, BMP_WIDTH - 1)
            out[:, col] = src[np.arange(BMP_HEIGHT), shifted]

        shifted_img = Image.fromarray(out, mode="L")
        bmp = shifted_img.point(lambda p: 0 if p > 64 else 255).convert("1")
        buf = io.BytesIO()
        bmp.save(buf, format="BMP")
        return buf.getvalue()

    return _make_eye(-1), _make_eye(+1)   # left eye, right eye


# ── Compose (background + layers) ─────────────────────────────────────────────

def compose_bmp(
    background_bytes: bytes | None,
    text_blocks: list[dict],
    image_layers: list[dict] | None = None,
) -> bytes:
    """
    Compose a 576×136 1-bit BMP from optional background + text/image layers.

    text_blocks: list of dicts with keys:
        text, size (px), align_h ('left'|'center'|'right'),
        align_v ('top'|'middle'|'bottom'), color ('white'|'black'), z (float)

    image_layers: list of dicts with keys:
        image_bytes (bytes), z (float), x_offset (int), y_offset (int)

    Source: api.py _compose_bmp (restructured for reuse).
    """
    from PIL import ImageDraw, ImageFont

    canvas = Image.new("L", (BMP_WIDTH, BMP_HEIGHT), 0)

    if background_bytes:
        bg = Image.open(io.BytesIO(background_bytes)).convert("L")
        bg = bg.resize((BMP_WIDTH, BMP_HEIGHT), Image.LANCZOS)
        canvas.paste(bg)

    if image_layers:
        for layer in image_layers:
            raw = Image.open(io.BytesIO(layer["image_bytes"])).convert("L")
            x = layer.get("x_offset", 0)
            y = layer.get("y_offset", 0)
            canvas.paste(raw, (x, y))

    draw = ImageDraw.Draw(canvas)
    for block in text_blocks:
        text  = block.get("text", "")
        size  = block.get("size", 14)
        color = 255 if block.get("color", "white") == "white" else 0
        h_al  = block.get("align_h", "left")
        v_al  = block.get("align_v", "top")

        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        x = {"left": 4, "center": (BMP_WIDTH - tw) // 2, "right": BMP_WIDTH - tw - 4}.get(h_al, 4)
        y = {"top": 2, "middle": (BMP_HEIGHT - th) // 2, "bottom": BMP_HEIGHT - th - 2}.get(v_al, 2)

        draw.text((x, y), text, fill=color, font=font)

    bmp = canvas.point(lambda p: 0 if p > 64 else 255).convert("1")
    buf = io.BytesIO()
    bmp.save(buf, format="BMP")
    return buf.getvalue()
