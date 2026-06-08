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
"""

import io
import zlib
from PIL import Image, ImageOps

from .constants import BMP_WIDTH, BMP_HEIGHT, BMP_PACKET_SIZE, BMP_ADDR, BMP_END_CMD
from .commands import build_display_complete


# Re-export so callers can do: from protocol.bmp import ...
__all__ = [
    "to_bmp_bytes",
    "to_bmp_bytes_inverted",
    "build_frames",
    "build_crc_cmd",
    "BMP_END_CMD",
    "DISPLAY_COMPLETE",
    "compute_depth",
    "compose_layers",
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
