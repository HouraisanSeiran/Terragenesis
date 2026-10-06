"""Explicit, checked snapshot for the read-only Minecraft surface adapter."""

import hashlib
import math
import os
from pathlib import Path
import struct
import tempfile

import numpy as np

from .metric_region_storage import load_metric_region


MAGIC = b"TGMCMT01"
VERSION = 1
MAX_SAMPLES = 16_000_000
SOFT_TARGET_SURFACE_Y = 800
MAX_BUILD_SURFACE_Y = 1022
MIN_BUILD_SURFACE_Y = -64


def validate_minecraft_surface_heights(elevation_m: np.ndarray,
                                       sea_level_elevation_m: float) -> np.ndarray:
    """Check the full metre-scale surface against Minecraft publication limits."""
    elevation = np.asarray(elevation_m, dtype=np.float64)
    if elevation.size == 0 or not np.isfinite(elevation).all():
        raise ValueError("Minecraft surface elevations must be finite and nonempty")
    game_height = elevation - sea_level_elevation_m + 62
    if not np.isfinite(game_height).all():
        raise ValueError("Minecraft surface heights must be finite")
    if game_height.min() < MIN_BUILD_SURFACE_Y or game_height.max() > MAX_BUILD_SURFACE_Y:
        raise ValueError("1 metre per block terrain exceeds Minecraft build height")
    return game_height


def export_metric_minecraft(region_path: str | Path, destination: str | Path) -> Path:
    region = load_metric_region(region_path)
    base, derived = region.base, region.derived
    if base.water is not None or derived.water is not None:
        raise ValueError("surface water is not supported by this consumer version")
    if derived.displacement_type != "vertical":
        raise ValueError("Minecraft height adapter requires vertical displacement")
    elevation = np.asarray(region.reconstructed_elevation_m(), dtype=">f8")
    rows, columns = elevation.shape
    if rows * columns > MAX_SAMPLES:
        raise ValueError("consumer grid exceeds sample budget")
    origin_x, origin_z = base.origin_x_m, base.origin_z_m
    spacing_x, spacing_z = base.spacing_x_m, base.spacing_z_m
    min_x = math.ceil(origin_x / 64) * 64
    min_z = math.ceil(origin_z / 64) * 64
    max_x = math.floor((origin_x + (columns - 1) * spacing_x) / 64) * 64
    max_z = math.floor((origin_z + (rows - 1) * spacing_z) / 64) * 64
    if min_x >= max_x or min_z >= max_z or any(abs(v) > 2_147_483_647 for v in (min_x, min_z, max_x, max_z)):
        raise ValueError("grid does not contain a 64-block-aligned finite world")
    validate_minecraft_surface_heights(elevation, base.sea_level_elevation_m)
    payload = bytearray()
    payload += MAGIC
    payload += struct.pack(">iq", VERSION, base.identity.seed)
    payload += b"0" * 64
    payload += derived.content_id.encode("ascii")
    payload += struct.pack(">5d4i2i", origin_x, origin_z, spacing_x, spacing_z,
                           base.sea_level_elevation_m, columns, rows,
                           min_x, min_z, max_x, max_z)
    payload += elevation.tobytes(order="C")
    payload += region.dominant_type.tobytes(order="C")
    payload[20:84] = hashlib.sha256(payload[:20] + payload[84:]).hexdigest().encode("ascii")
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    part = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{destination.name}-", suffix=".part",
                                         dir=destination.parent, delete=False) as temporary:
            part = Path(temporary.name)
            temporary.write(payload)
            temporary.write(hashlib.sha256(payload).digest())
            temporary.flush()
            os.fsync(temporary.fileno())
        if destination.exists():
            raise FileExistsError(destination)
        os.rename(part, destination)
    finally:
        if part is not None:
            part.unlink(missing_ok=True)
    return destination
