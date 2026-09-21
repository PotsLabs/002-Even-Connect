"""
3D OBJ file rendering for glasses display.

Renders 3D wireframe models (OBJ format) to 1-bit BMPs with z-depth for stereo.
Usage:
    obj = load_obj_bytes(file_bytes)
    bmp = render_wireframe(obj, rotation=(0, 45, 0), position=(288, 68), scale=1.5, z=0)
    frames = build_frames(bmp)
"""

import io
import math
import numpy as np
from dataclasses import dataclass
from PIL import Image, ImageDraw

from .constants import BMP_WIDTH, BMP_HEIGHT


@dataclass
class OBJModel:
    """Parsed OBJ model."""
    vertices: list[tuple[float, float, float]]  # (x, y, z)
    edges: list[tuple[int, int]]  # (v1_idx, v2_idx)
    name: str = "Model"


def load_obj_bytes(obj_bytes: bytes) -> OBJModel:
    """
    Parse OBJ file from bytes.
    Supports: v (vertices), l (lines/edges), f (faces rendered as wireframe).
    """
    lines = obj_bytes.decode('utf-8', errors='ignore').split('\n')
    vertices = []
    edges = set()  # Use set to avoid duplicates

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        parts = line.split()
        if not parts:
            continue

        if parts[0] == 'v':
            # Vertex: v x y z [w]
            try:
                x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                vertices.append((x, y, z))
            except (ValueError, IndexError):
                continue

        elif parts[0] == 'l':
            # Line/edge: l v1 v2 [v3 ...]
            try:
                indices = [int(p) - 1 for p in parts[1:]]  # OBJ indices are 1-based
                for i in range(len(indices) - 1):
                    v1, v2 = indices[i], indices[i + 1]
                    edge = tuple(sorted([v1, v2]))
                    edges.add(edge)
            except (ValueError, IndexError):
                continue

        elif parts[0] == 'f':
            # Face: f v1 v2 v3 ... (render as wireframe edges)
            try:
                indices = []
                for p in parts[1:]:
                    # Handle v, v/vt, v/vt/vn, v//vn formats
                    idx = int(p.split('/')[0]) - 1
                    indices.append(idx)
                # Create edges around the face perimeter
                for i in range(len(indices)):
                    v1 = indices[i]
                    v2 = indices[(i + 1) % len(indices)]
                    edge = tuple(sorted([v1, v2]))
                    edges.add(edge)
            except (ValueError, IndexError):
                continue

    return OBJModel(
        vertices=vertices,
        edges=list(edges),
        name="OBJ Model"
    )


def _rotation_matrix(rx: float, ry: float, rz: float) -> np.ndarray:
    """Build 3D rotation matrix (degrees, applied as Rz * Ry * Rx)."""
    rx_rad = math.radians(rx)
    ry_rad = math.radians(ry)
    rz_rad = math.radians(rz)

    # Rotation matrices
    Rx = np.array([
        [1, 0, 0],
        [0, math.cos(rx_rad), -math.sin(rx_rad)],
        [0, math.sin(rx_rad), math.cos(rx_rad)]
    ])

    Ry = np.array([
        [math.cos(ry_rad), 0, math.sin(ry_rad)],
        [0, 1, 0],
        [-math.sin(ry_rad), 0, math.cos(ry_rad)]
    ])

    Rz = np.array([
        [math.cos(rz_rad), -math.sin(rz_rad), 0],
        [math.sin(rz_rad), math.cos(rz_rad), 0],
        [0, 0, 1]
    ])

    return Rz @ Ry @ Rx


def _project_3d_to_2d(vertex_3d: tuple[float, float, float],
                      fov: float = 60.0,
                      distance: float = 300.0) -> tuple[float, float]:
    """
    Perspective projection: 3D → 2D screen coordinates.
    fov: field of view in degrees
    distance: camera distance from origin
    Returns: (screen_x, screen_y) where (0, 0) is top-left
    """
    x, y, z = vertex_3d
    # Perspective: divide by (z + distance) for depth effect
    scale = distance / (z + distance)

    screen_x = (x * scale) + BMP_WIDTH / 2
    screen_y = (y * scale) + BMP_HEIGHT / 2

    return (screen_x, screen_y)


def _get_model_bounds(vertices: list[tuple[float, float, float]]) -> tuple[float, float, float, tuple[float, float, float]]:
    """Calculate bounding box of model and its center.

    Returns: (width, height, depth, center_point)
    """
    if not vertices:
        return 1.0, 1.0, 1.0, (0.0, 0.0, 0.0)

    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)

    width = max_x - min_x or 1.0
    height = max_y - min_y or 1.0
    depth = max_z - min_z or 1.0

    # Center of bounding box
    center = (
        (min_x + max_x) / 2.0,
        (min_y + max_y) / 2.0,
        (min_z + max_z) / 2.0,
    )

    return width, height, depth, center


def _auto_scale_for_display(model: OBJModel, padding: float = 0.8) -> float:
    """Calculate scale factor to fit model in 576×136 display with padding."""
    width, height, _, _ = _get_model_bounds(model.vertices)
    # Fit to 80% of smaller dimension
    max_display_dim = min(BMP_WIDTH, BMP_HEIGHT) * padding
    max_model_dim = max(width, height)
    return max_display_dim / max_model_dim if max_model_dim > 0 else 1.0


def render_wireframe(
    model: OBJModel,
    rotation: tuple[float, float, float] = (0, 0, 0),  # (rx, ry, rz) degrees
    position: tuple[float, float] | None = None,  # Auto-center if None
    scale: float | None = None,  # Auto-scale if None
    z_depth: float = 0.0,  # Stereo z-depth (-1 to +1)
    fov: float = 60.0,
    distance: float = 300.0
) -> bytes:
    """
    Render OBJ model wireframe to 1-bit BMP.

    Args:
        model: Parsed OBJ model
        rotation: (rx, ry, rz) in degrees
        position: (x, y) center on screen — auto-centers to (288, 68) if None
        scale: Model scale multiplier — auto-scales to fit if None
        z_depth: Stereo depth adjustment (for compute_depth)
        fov: Camera field of view (degrees)
        distance: Camera distance from origin

    Returns: BMP bytes (576×136 1-bit)
    """
    # Auto-center and auto-scale if not specified
    if scale is None:
        scale = _auto_scale_for_display(model, padding=0.8)
    if position is None:
        position = (BMP_WIDTH // 2, BMP_HEIGHT // 2)

    # Create white canvas
    canvas = Image.new("L", (BMP_WIDTH, BMP_HEIGHT), 255)
    draw = ImageDraw.Draw(canvas)

    # Get model's bounding box center to translate model to origin
    _, _, _, model_center = _get_model_bounds(model.vertices)

    # Build rotation matrix
    R = _rotation_matrix(*rotation)

    # Transform and project vertices
    projected = []
    for vx, vy, vz in model.vertices:
        # Translate to origin (center model at 0, 0, 0)
        vx -= model_center[0]
        vy -= model_center[1]
        vz -= model_center[2]

        # Scale
        v = np.array([vx * scale, vy * scale, vz * scale])

        # Rotate
        v = R @ v

        # Project to 2D
        sx, sy = _project_3d_to_2d(tuple(v), fov=fov, distance=distance)

        # Center on position
        sx += position[0]
        sy += position[1]
        projected.append((sx, sy))

    # Draw edges
    for v1_idx, v2_idx in model.edges:
        if 0 <= v1_idx < len(projected) and 0 <= v2_idx < len(projected):
            x1, y1 = projected[v1_idx]
            x2, y2 = projected[v2_idx]
            # Clip to canvas bounds
            if (0 <= x1 < BMP_WIDTH and 0 <= y1 < BMP_HEIGHT) or \
               (0 <= x2 < BMP_WIDTH and 0 <= y2 < BMP_HEIGHT):
                draw.line([(x1, y1), (x2, y2)], fill=0, width=1)

    # Threshold and convert to 1-bit
    bmp = canvas.point(lambda p: 255 if p > 64 else 0).convert("1")

    buf = io.BytesIO()
    bmp.save(buf, format="BMP")
    return buf.getvalue()
