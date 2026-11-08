"""Deterministic 1024+ cell surface-network partition and one-step benchmark."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np


SCHEMA = "surface-network-large-benchmark-v1"
STATIC_SCHEMA = "surface-network-large-static-D4-v1"
DYNAMIC_SCHEMA = "surface-network-large-one-step-storage-v1"


@dataclass(frozen=True)
class LargeBenchmarkBudget:
    tile_cells: int = 256
    max_cells: int = 16_777_216
    max_resident_bytes: int = 256 * 1024 * 1024
    max_tiles: int = 256
    forcing_interval_s: float = 900.0


def _finite_positive(value, name):
    if type(value) not in (int, float) or not np.isfinite(value) or value <= 0:
        raise ValueError(name + " must be finite and positive")


def validate_budget(budget):
    if not isinstance(budget, LargeBenchmarkBudget):
        raise ValueError("LargeBenchmarkBudget required")
    for name in ("tile_cells", "max_cells", "max_resident_bytes", "max_tiles"):
        value = getattr(budget, name)
        if type(value) is not int or value <= 0:
            raise ValueError("positive integer budget: " + name)
    _finite_positive(budget.forcing_interval_s, "forcing_interval_s")
    if budget.tile_cells < 16 or budget.tile_cells > 1024:
        raise ValueError("tile span outside bounded range")


def _load_npz(path):
    with np.load(path, mmap_mode="r", allow_pickle=False) as archive:
        keys = set(archive.files)
        if keys != {"elevation_m"}:
            raise ValueError("Terrain Diffusion NPZ must contain elevation_m only")
        return np.asarray(archive["elevation_m"])


def load_terrain_diffusion_height(path, *, expected_sha256=None):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 2 * 1024**3:
        raise ValueError("missing or oversized Terrain Diffusion height input")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("Terrain Diffusion height hash mismatch")
    if path.suffix == ".npy":
        height = np.load(path, mmap_mode="r", allow_pickle=False)
    elif path.suffix == ".npz":
        height = _load_npz(path)
    else:
        raise ValueError("only .npy or .npz Terrain Diffusion height inputs are supported")
    if not isinstance(height, np.ndarray) or height.ndim != 2 or height.shape[0] != height.shape[1] or height.shape[0] < 1024:
        raise ValueError("square Terrain Diffusion height grid of at least 1024 cells required")
    if height.dtype not in (np.dtype("float32"), np.dtype("float64")) or not np.isfinite(height).all():
        raise ValueError("Terrain Diffusion height must be finite float32/float64")
    return {"height_m": height, "source_sha256": digest, "shape": list(height.shape),
        "source_format": "terrain_diffusion_height_m_raw_no_fill_no_route"}


def _tile_records(shape, tile_cells):
    rows, columns = shape
    records = []
    tile_id = 0
    for row0 in range(0, rows, tile_cells):
        for column0 in range(0, columns, tile_cells):
            row1, column1 = min(row0 + tile_cells, rows), min(column0 + tile_cells, columns)
            records.append({"tile_id": tile_id, "row0": row0, "row1": row1,
                "column0": column0, "column1": column1,
                "owner_key": [row0 // tile_cells, column0 // tile_cells]})
            tile_id += 1
    return records


def _deterministic_receiver(height):
    rows, columns = height.shape
    receiver = np.full(height.size, -1, np.int64)
    grid = np.arange(height.size, dtype=np.int64).reshape(height.shape)
    # N, W, E, S is the fixed tie order; strict descent prevents cycles.
    candidates = ((-1, 0), (0, -1), (0, 1), (1, 0))
    for row in range(1, rows - 1):
        for column in range(1, columns - 1):
            current = height[row, column]
            best = None
            for delta_row, delta_column in candidates:
                target_row, target_column = row + delta_row, column + delta_column
                target_height = height[target_row, target_column]
                if target_height < current and (best is None or target_height < best[0]):
                    best = (target_height, grid[target_row, target_column])
            if best is not None:
                receiver[grid[row, column]] = best[1]
    return receiver


def prepare_large_static(height_m, *, spacing_m=30.0, origin_m_xz=(0.0, 0.0), budget=LargeBenchmarkBudget()):
    validate_budget(budget)
    if not isinstance(height_m, np.ndarray) or height_m.ndim != 2 or height_m.shape[0] != height_m.shape[1] or height_m.shape[0] < 1024:
        raise ValueError("large square height grid required")
    if height_m.dtype not in (np.dtype("float32"), np.dtype("float64")) or not np.isfinite(height_m).all():
        raise ValueError("height must be finite Terrain Diffusion float data")
    if height_m.size > budget.max_cells:
        raise ValueError("large static cell budget exceeded")
    _finite_positive(spacing_m, "spacing_m")
    origin = np.asarray(origin_m_xz, dtype=np.float64)
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("origin must contain two finite coordinates")
    records = _tile_records(height_m.shape, budget.tile_cells)
    if len(records) > budget.max_tiles:
        raise ValueError("tile count budget exceeded")
    receiver = _deterministic_receiver(height_m)
    rows, columns = height_m.shape
    tile_id = np.empty(height_m.size, np.int32)
    for record in records:
        tile_id.reshape(height_m.shape)[record["row0"]:record["row1"], record["column0"]:record["column1"]] = record["tile_id"]
    receiver_tile = np.where(receiver >= 0, tile_id[receiver], -1).astype(np.int32)
    crossings = np.flatnonzero((receiver >= 0) & (tile_id != receiver_tile))
    tile_pairs = sorted({(int(tile_id[index]), int(receiver_tile[index])) for index in crossings})
    outlets = np.flatnonzero(receiver < 0).astype(np.int64)
    edge_faces = []
    for record in records:
        tile = record["tile_id"]
        for other in records:
            if other["tile_id"] <= tile:
                continue
            row_touch = record["row1"] == other["row0"] and max(record["column0"], other["column0"]) < min(record["column1"], other["column1"])
            column_touch = record["column1"] == other["column0"] and max(record["row0"], other["row0"]) < min(record["row1"], other["row1"])
            if row_touch or column_touch:
                edge_faces.append((tile, other["tile_id"]))
    return {"arrays": {"height_m": np.asarray(height_m), "receiver": receiver,
        "tile_id": tile_id, "receiver_tile_id": receiver_tile, "outlet_cell": outlets,
        "crossing_donor": crossings.astype(np.int64)},
        "metadata": {"schema": STATIC_SCHEMA, "shape": [rows, columns], "spacing_m": float(spacing_m),
            "origin_m_xz": origin.tolist(), "tile_cells": budget.tile_cells, "tile_count": len(records),
            "tiles": records, "shared_tile_edges": [list(pair) for pair in edge_faces],
            "cross_tile_receiver_pairs": [list(pair) for pair in tile_pairs],
            "outlet_definition": "receiver=-1: boundary or deterministic local terminal; not natural outlet certification",
            "memory_model": "full receiver/tile ownership arrays plus one-step tile working set",
            "source_evolution": "raw Terrain Diffusion H0 only; no fill/cut/reassembled regional surface"}}


def validate_large_static(static):
    arrays, meta = static["arrays"], static["metadata"]
    if meta["schema"] != STATIC_SCHEMA or set(arrays) != {"height_m", "receiver", "tile_id", "receiver_tile_id", "outlet_cell", "crossing_donor"}:
        raise ValueError("large static schema")
    shape = tuple(meta["shape"])
    height, receiver, tile_id, receiver_tile = (arrays[key] for key in ("height_m", "receiver", "tile_id", "receiver_tile_id"))
    if height.shape != shape or receiver.shape != (height.size,) or tile_id.shape != receiver.shape or receiver_tile.shape != receiver.shape:
        raise ValueError("large static shapes")
    if not np.isfinite(height).all() or receiver.dtype != np.int64 or tile_id.dtype != np.int32 or receiver_tile.dtype != np.int32:
        raise ValueError("large static dtypes/finite")
    if np.any((receiver < -1) | (receiver >= height.size)) or not np.array_equal(receiver_tile, np.where(receiver >= 0, tile_id[np.maximum(receiver, 0)], -1)):
        raise ValueError("receiver tile ownership mismatch")
    donors = np.flatnonzero(receiver >= 0)
    if donors.size and not np.all(height.ravel()[receiver[donors]] < height.ravel()[donors]):
        raise ValueError("receiver must be strict downhill")
    if not np.array_equal(arrays["outlet_cell"], np.flatnonzero(receiver < 0)) or not np.array_equal(arrays["crossing_donor"], np.flatnonzero((receiver >= 0) & (tile_id != receiver_tile))):
        raise ValueError("large outlet/crossing audit")
    return {"cells": int(height.size), "tile_count": meta["tile_count"], "outlet_count": int(arrays["outlet_cell"].size),
        "cross_tile_edge_count": int(arrays["crossing_donor"].size), "verified": True}


def run_one_step_storage(static, *, forcing_m3_s=0.0, duration_s=None):
    """Light benchmark: storage and per-tile input only; no 72h routing claim."""
    arrays, meta = static["arrays"], static["metadata"]
    duration = meta.get("forcing_interval_s", 900.0) if duration_s is None else duration_s
    _finite_positive(forcing_m3_s, "forcing_m3_s")
    _finite_positive(duration, "duration_s")
    height = arrays["height_m"]
    tile_ids = arrays["tile_id"]
    count = meta["tile_count"]
    volumes = np.bincount(tile_ids, minlength=count).astype(np.float64) * forcing_m3_s * duration
    return {"metadata": {"schema": DYNAMIC_SCHEMA, "duration_s": float(duration), "forcing_m3_s": float(forcing_m3_s),
        "input_scope": "uniform source into flat cells; no momentum, no channel cross-section, no long-run routing"},
        "arrays": {"tile_input_volume_m3": volumes, "total_input_volume_m3": np.asarray(volumes.sum())}}
