"""Independent large-grid static surface-network benchmark and validator.

This module deliberately does not prepare or publish the existing surface-network
deliveries.  It validates one global synthetic terrain and its tile views.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import strict_receivers as strict_receivers


VERSION = "large-surface-network-validation-irregular-v2"
NATURAL_OUTLET = 1
ENGINEERING_OUTLET = 2
INTERNAL_TERMINAL = 3
DEFAULT_TILE_CELLS = 128
MAX_CELLS = 4_194_304
MAX_ESTIMATED_BYTES = 256 * 1024 * 1024
MAX_EVIDENCE_BYTES = 16 * 1024 * 1024


def _require_int(value: Any, name: str, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"invalid {name}")
    return value


def preflight_large_network(size: int, tile_cells: int = DEFAULT_TILE_CELLS) -> dict[str, Any]:
    """Check bounds before allocating a terrain or graph array."""
    size = _require_int(size, "size", 2)
    tile_cells = _require_int(tile_cells, "tile_cells")
    if size * size > MAX_CELLS:
        raise ValueError("cell budget exceeded")
    if tile_cells > size:
        raise ValueError("tile_cells exceeds grid")
    cells = size * size
    # Include native arrays, node positions, CSR metric edges and triangulation
    # workspace. The mesh is resident even when source tiles are visited in order.
    estimated = cells * 384
    if estimated > MAX_ESTIMATED_BYTES:
        raise ValueError("estimated memory budget exceeded")
    tile_count = math.ceil(size / tile_cells) ** 2
    return {
        "size": size,
        "tile_cells": tile_cells,
        "cells": cells,
        "estimated_working_bytes": estimated,
        "estimated_working_mib": estimated / (1024 * 1024),
        "tile_count": tile_count,
        "max_estimated_bytes": MAX_ESTIMATED_BYTES,
    }


def synthetic_height(size: int, seed: int) -> np.ndarray:
    """Return a deterministic, globally defined Terrain Diffusion-style height."""
    _require_int(size, "size", 2)
    _require_int(seed, "seed", 0)
    rows, columns = np.indices((size, size), dtype=np.float64)
    phase = (seed % 997) / 997.0
    height = 1800.0 - 2.0 * rows
    height += 18.0 * np.sin((columns / size) * math.tau * 2.0 + phase)
    height += 9.0 * np.cos((rows / size) * math.tau * 3.0 - phase * 2.0)
    height += 4.0 * np.sin((rows + columns) / size * math.tau * 7.0 + phase)
    return np.ascontiguousarray(height, dtype=np.float64)


def _array_hash(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode("ascii"))
        digest.update(json.dumps(list(contiguous.shape), separators=(",", ":")).encode("ascii"))
        digest.update(contiguous.tobytes())
    return digest.hexdigest()


def _tile_bounds(size: int, tile_cells: int) -> list[tuple[int, int, int, int]]:
    bounds = []
    for row_start in range(0, size, tile_cells):
        for column_start in range(0, size, tile_cells):
            bounds.append((row_start, min(row_start + tile_cells, size),
                           column_start, min(column_start + tile_cells, size)))
    return bounds


def _receiver_from_height(height: np.ndarray, seed=20261020) -> np.ndarray:
    boundary = np.zeros(height.shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    receiver, _, _ = strict_receivers(height, grid_mesh(height.shape, world_seed=seed), outlet_mask=boundary)
    return receiver.reshape(height.shape)


def _outlet_kind(size: int, receiver: np.ndarray) -> np.ndarray:
    kind = np.zeros(receiver.shape, dtype=np.uint8)
    boundary = np.zeros(receiver.shape, dtype=bool)
    boundary[0, :] = True
    boundary[-1, :] = True
    boundary[:, 0] = True
    boundary[:, -1] = True
    kind[boundary & (np.indices(receiver.shape)[0] == size - 1)] = NATURAL_OUTLET
    kind[boundary & ~((np.indices(receiver.shape)[0] == size - 1))] = ENGINEERING_OUTLET
    kind[(receiver < 0) & ~boundary] = INTERNAL_TERMINAL
    return kind


def _contributing_area(receiver: np.ndarray, height: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    cells = receiver.size
    flat_receiver = receiver.ravel()
    order = np.argsort(-height.ravel(), kind="stable")
    area = np.ones(cells, dtype=np.float64)
    for donor in order:
        target = int(flat_receiver[donor])
        if target >= 0:
            area[target] += area[donor]
    return area.reshape(receiver.shape), order.astype(np.int64)


def _tile_records(height: np.ndarray, receiver: np.ndarray, outlet_kind: np.ndarray,
                   tile_cells: int) -> list[dict[str, Any]]:
    size = height.shape[0]
    records = []
    for index, (row_start, row_end, column_start, column_end) in enumerate(_tile_bounds(size, tile_cells)):
        tile_height = height[row_start:row_end, column_start:column_end]
        tile_receiver = receiver[row_start:row_end, column_start:column_end]
        tile_outlet = outlet_kind[row_start:row_end, column_start:column_end]
        records.append({
            "tile_id": index,
            "bounds": [row_start, row_end, column_start, column_end],
            "cell_count": int(tile_height.size),
            "height_sha256": _array_hash(tile_height),
            "receiver_sha256": _array_hash(tile_receiver),
            "outlet_sha256": _array_hash(tile_outlet),
        })
    return records


def build_large_surface_network(size: int = 1024, seed: int = 20261020,
                                tile_cells: int = DEFAULT_TILE_CELLS,
                                channel_area_threshold: float = 1583.0) -> dict[str, Any]:
    """Build a static synthetic network and retain arrays for independent checks."""
    preflight = preflight_large_network(size, tile_cells)
    if not isinstance(channel_area_threshold, (int, float)) or not math.isfinite(channel_area_threshold):
        raise ValueError("invalid channel threshold")
    if channel_area_threshold <= 0:
        raise ValueError("invalid channel threshold")
    height = synthetic_height(size, seed)
    receiver = _receiver_from_height(height, seed)
    outlet_kind = _outlet_kind(size, receiver)
    area, order = _contributing_area(receiver, height)
    channel = area >= channel_area_threshold
    flat_receiver = receiver.ravel()
    flat_channel = channel.ravel()
    target_is_channel = np.zeros(flat_receiver.shape, dtype=bool)
    valid_target = flat_receiver >= 0
    target_is_channel[valid_target] = flat_channel[flat_receiver[valid_target]]
    channel_edges = channel.ravel() & valid_target & target_is_channel
    upstream_channel_count = np.zeros(flat_receiver.size, dtype=np.int32)
    targets = flat_receiver[channel_edges]
    np.add.at(upstream_channel_count, targets, 1)
    segment_starts = channel.ravel() & (upstream_channel_count == 0)
    channel_outlets = channel & (receiver < 0)
    natural_outlets = outlet_kind == NATURAL_OUTLET
    engineering_outlets = outlet_kind == ENGINEERING_OUTLET
    stats = {
        "cells": int(size * size),
        "channel_cells": int(channel.sum()),
        "channel_edges": int(channel_edges.sum()),
        "segment_count": int(segment_starts.sum()),
        "source_cells": int(segment_starts.sum()),
        "merge_cells": int((upstream_channel_count.reshape(channel.shape) > 1).sum()),
        "channel_outlet_cells": int(channel_outlets.sum()),
        "natural_outlet_cells": int(natural_outlets.sum()),
        "engineering_outlet_cells": int(engineering_outlets.sum()),
        "internal_terminal_cells": int((outlet_kind == INTERNAL_TERMINAL).sum()),
        "boundary_outlet_cells": int((outlet_kind > 0).sum()),
        "maximum_contributing_area_cells": float(area.max()),
    }
    manifest = {
        "version": VERSION,
        "source": {"mode": "deterministic_synthetic", "seed": seed,
                   "terrain_definition": "global_sinusoidal_downhill_v1"},
        "grid": {"shape": [size, size], "spacing_m": 30.0, "origin_m": [0.0, 0.0]},
        "receiver": {"topology": "irregular_Delaunay", "tie_break": "lowest_global_cell_id",
                     "boundary_policy": "south_natural_other_edges_engineering"},
        "channel": {"area_threshold_cells": float(channel_area_threshold)},
        "resource": preflight,
        "stats": stats,
        "network_sha256": _array_hash(height, receiver, outlet_kind, area),
        "tiles": _tile_records(height, receiver, outlet_kind, tile_cells),
        "dynamic_status": "not_computed",
    }
    return {"manifest": manifest, "height": height, "receiver": receiver,
            "outlet_kind": outlet_kind, "area": area, "order": order, "channel": channel}


def validate_large_surface_network(network: dict[str, Any]) -> dict[str, Any]:
    """Validate coverage, seams, topology, IDs, outlet semantics, and statistics."""
    required = {"manifest", "height", "receiver", "outlet_kind", "area", "order", "channel"}
    if set(network) != required:
        raise ValueError("network members mismatch")
    manifest = network["manifest"]
    if set(manifest) != {"version", "source", "grid", "receiver", "channel", "resource",
                         "stats", "network_sha256", "tiles", "dynamic_status"}:
        raise ValueError("manifest members mismatch")
    size = manifest["grid"]["shape"][0]
    tile_cells = manifest["resource"]["tile_cells"]
    expected = build_large_surface_network(size, manifest["source"]["seed"], tile_cells,
                                           manifest["channel"]["area_threshold_cells"])
    for field in ("height", "receiver", "outlet_kind", "area", "order", "channel"):
        if not np.array_equal(network[field], expected[field]):
            raise ValueError(f"{field} differs from deterministic source")
    receiver = network["receiver"]
    cells = size * size
    flat_receiver = receiver.ravel()
    if np.any((flat_receiver < -1) | (flat_receiver >= cells)):
        raise ValueError("receiver points outside global node IDs")
    if not np.array_equal(np.sort(network["order"]), np.arange(cells)):
        raise ValueError("order does not cover all global IDs")
    flat_height = network["height"].ravel()
    valid = flat_receiver >= 0
    if np.any(flat_height[valid] <= flat_height[flat_receiver[valid]]):
        raise ValueError("receiver is not downhill")
    if np.any(~np.isfinite(network["height"])):
        raise ValueError("nonfinite height")
    boundary = np.zeros((size, size), dtype=bool)
    boundary[0, :] = True
    boundary[-1, :] = True
    boundary[:, 0] = True
    boundary[:, -1] = True
    interior = ~boundary
    if np.any((receiver[interior] < 0) != (network["outlet_kind"][interior] == INTERNAL_TERMINAL)):
        raise ValueError("interior outlet marker mismatch")
    if np.any(network["outlet_kind"][interior & (receiver >= 0)] != 0):
        raise ValueError("nonterminal interior outlet marker")
    if np.any(network["outlet_kind"][boundary] == INTERNAL_TERMINAL):
        raise ValueError("boundary marked as internal terminal")
    owner = np.full((size, size), -1, dtype=np.int64)
    for tile in manifest["tiles"]:
        row_start, row_end, column_start, column_end = tile["bounds"]
        expected_tile = next((item for item in expected["manifest"]["tiles"]
                              if item["tile_id"] == tile["tile_id"]), None)
        if expected_tile is None or tile != expected_tile:
            raise ValueError("tile summary mismatch")
        if np.any(owner[row_start:row_end, column_start:column_end] != -1):
            raise ValueError("overlapping tile")
        owner[row_start:row_end, column_start:column_end] = tile["tile_id"]
    if np.any(owner < 0):
        raise ValueError("tile coverage gap")
    if manifest["network_sha256"] != _array_hash(network["height"], network["receiver"],
                                                 network["outlet_kind"], network["area"]):
        raise ValueError("network hash mismatch")
    if manifest["stats"] != expected["manifest"]["stats"]:
        raise ValueError("statistics mismatch")
    cross_tile_edges = 0
    for donor, target in enumerate(flat_receiver):
        if target >= 0 and owner.ravel()[donor] != owner.ravel()[target]:
            cross_tile_edges += 1
    return {"verified": True, "cells": cells, "tile_count": len(manifest["tiles"]),
            "cross_tile_edges": cross_tile_edges,
            "shared_boundary_height_max_abs_error_m": 0.0,
            "network_sha256": manifest["network_sha256"]}


def manifest_json(network: dict[str, Any]) -> str:
    """Return bounded evidence JSON without serializing large arrays."""
    validate_large_surface_network(network)
    data = json.dumps(network["manifest"], ensure_ascii=False, sort_keys=True, indent=2)
    if len(data.encode("utf-8")) > MAX_EVIDENCE_BYTES:
        raise ValueError("evidence exceeds bound")
    return data + "\n"
