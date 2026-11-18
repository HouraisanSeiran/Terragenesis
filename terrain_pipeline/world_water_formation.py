"""Finite water formation sharing the production irregular-graph solver."""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.drainage import solve_disk_region as solve_disk_region


def form_water_and_rivers(height, ocean_mask, origin_native_xz, world_seed, source, *,
                          runoff_m_per_year, duration_seconds, channel_threshold_m3_s,
                          sea_level_m=0., min_lake_area_m2=10000.):
    bed = np.asarray(height, dtype=np.float64)
    ocean = np.asarray(ocean_mask)
    if (bed.ndim != 2 or min(bed.shape) < 4 or not np.isfinite(bed).all()
            or ocean.dtype != np.bool_ or ocean.shape != bed.shape):
        raise ValueError("finite 2D terrain and matching boolean ocean mask required")
    if (not isinstance(origin_native_xz, (list, tuple)) or len(origin_native_xz) != 2
            or any(type(v) is not int for v in origin_native_xz)
            or type(world_seed) is not int or world_seed < 0 or not isinstance(source, dict)):
        raise ValueError("native integer origin, world seed and source metadata required")
    if not math.isfinite(runoff_m_per_year) or runoff_m_per_year < 0.:
        raise ValueError("finite nonnegative runoff required")
    for value in (duration_seconds, channel_threshold_m3_s, min_lake_area_m2):
        if not math.isfinite(value) or value <= 0.:
            raise ValueError("positive finite runoff, duration, threshold and minimum lake area required")
    if not math.isfinite(sea_level_m):
        raise ValueError("finite sea level required")
    if np.any(bed[ocean] > sea_level_m):
        raise ValueError("ocean bed must not exceed declared sea level")
    with tempfile.TemporaryDirectory(prefix="terragenesis-water-") as directory:
        root = Path(directory)
        np.save(root / "height.npy", bed)
        np.save(root / "ocean.npy", ocean)
        product = solve_disk_region(root / "height.npy", root / "ocean.npy", root / "water",
            origin_native_xz=origin_native_xz, world_seed=world_seed,
            runoff_m_per_year=runoff_m_per_year, duration_seconds=duration_seconds,
            channel_threshold_m3_s=channel_threshold_m3_s,
            min_lake_area_m2=min_lake_area_m2, sea_level_m=sea_level_m)
        arrays = {name: np.load(root / "water" / relative, allow_pickle=False)
                  for name, relative in product["fields"].items()}
        with np.load(root / "water" / product["network"]["file"], allow_pickle=False) as archive:
            network = {name: archive[name].copy() for name in archive.files}
    receiver = arrays["receiver"]
    spill_receiver = arrays["spill_receiver"]
    terminal = np.full(bed.shape, "interior", dtype="U24")
    terminal[ocean] = "inactive"
    land = ~ocean
    terminal[land & (receiver < 0)] = "retained"
    targets = spill_receiver.ravel()
    coastal = ((receiver.ravel() < 0) & (targets >= 0)
               & ocean.ravel()[np.maximum(targets, 0)] & land.ravel())
    terminal.ravel()[coastal] = "open_outflow"
    border = np.zeros(bed.shape, bool)
    border[[0, -1], :] = True
    border[:, [0, -1]] = True
    terminal[land & border] = "unknown_boundary"
    arrays["terminal_kind"] = terminal
    metadata = dict(product["metadata"])
    metadata.update(schema="world-water-formation-v2",
        source=source, spacing_m=30.,
        source_identity_sha256=identity({"bed_before_m": bed},
            {"source": source, "origin_native_xz": list(origin_native_xz)}),
        produced_depth_m=float(runoff_m_per_year) * float(duration_seconds) / (365.25 * 86400.),
        network=product["network"]["metadata"])
    return {"arrays": arrays, "metadata": metadata, "network": network,
            "identity_sha256": identity(arrays, metadata)}
