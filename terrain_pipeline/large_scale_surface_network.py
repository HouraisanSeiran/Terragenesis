"""Deterministic, tiled D4 surface-network validation for large synthetic DEMs.

This module is deliberately independent from the production regional hydraulics
and routing modules.  It validates the static Terrain Diffusion style contract:
every cell has one D4 receiver or an explicit outlet, and tile seams are
computed with a one-cell halo.
"""

from dataclasses import dataclass
import hashlib
import math

import numpy as np


SCHEMA = "large-scale-surface-network-D4-tiled-v1"
_DIRECTIONS = ((-1, 0), (0, -1), (0, 1), (1, 0))


@dataclass(frozen=True)
class LargeScaleBudget:
    tile_size: int = 256
    max_cells: int = 16_777_216
    max_resident_bytes: int = 512 * 1024 * 1024

    def validate(self):
        if type(self.tile_size) is not int or not 16 <= self.tile_size <= 1024:
            raise ValueError("tile_size must be an integer in 16..1024")
        if type(self.max_cells) is not int or self.max_cells <= 0:
            raise ValueError("max_cells must be positive")
        if type(self.max_resident_bytes) is not int or self.max_resident_bytes <= 0:
            raise ValueError("max_resident_bytes must be positive")


def synthetic_terrain_diffusion_height(size, seed=20261001):
    """Return a reproducible mountain DEM with broad and fine terrain scales."""
    if type(size) is not int or size < 2:
        raise ValueError("size must be an integer >= 2")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    rows, columns = np.indices((size, size), dtype=np.float64)
    y = rows / max(size - 1, 1)
    x = columns / max(size - 1, 1)
    # Broad ridges and deterministic valleys resemble a diffusion height field.
    height = 900.0 + 560.0 * (1.0 - y) + 75.0 * np.sin(2.0 * np.pi * (x * 1.7 + seed * 1e-5))
    height += 48.0 * np.sin(2.0 * np.pi * (x * 5.0 + y * 2.0))
    height += 22.0 * np.cos(2.0 * np.pi * (x * 13.0 - y * 7.0))
    for center_x, center_y, amplitude, width in ((.23, .28, 180., .16), (.72, .38, 140., .20),
                                                  (.47, .72, -110., .13)):
        distance = ((x - center_x) ** 2 + (y - center_y) ** 2) / (width * width)
        height += amplitude * np.exp(-distance)
    return height.astype(np.float32)


def _validate_height(height_m, budget):
    budget.validate()
    height = np.asarray(height_m)
    if height.ndim != 2 or height.shape[0] != height.shape[1] or height.shape[0] < 1024:
        raise ValueError("height must be a square grid of at least 1024 cells")
    if height.dtype not in (np.dtype("float32"), np.dtype("float64")):
        raise ValueError("height must be float32 or float64")
    if not np.isfinite(height).all():
        raise ValueError("height must be finite")
    if height.size > budget.max_cells:
        raise ValueError("cell budget exceeded")
    return height


def estimate_resident_bytes(size, tile_size=256):
    """Conservative resident estimate for canonical arrays and one tile working set."""
    cells = int(size) * int(size)
    tile_cells = (min(int(size), int(tile_size)) + 2) ** 2
    return cells * (4 + 8 + 4 + 8) + tile_cells * (4 + 8 + 8) + 4096


def _tile_records(size, tile_size):
    records = []
    for row0 in range(0, size, tile_size):
        for column0 in range(0, size, tile_size):
            records.append((row0, min(row0 + tile_size, size), column0,
                            min(column0 + tile_size, size)))
    return records


def _route_tile(height, receiver, row0, row1, column0, column1):
    """Route a tile while reading one-cell neighbor halo from the shared DEM."""
    current = height[row0:row1, column0:column1]
    best_height = current.copy()
    best_receiver = np.full(current.shape, -1, dtype=np.int64)
    rows, columns = height.shape
    local_rows, local_columns = current.shape
    local_r, local_c = np.indices(current.shape)
    global_r = local_r + row0
    global_c = local_c + column0
    for delta_row, delta_column in _DIRECTIONS:
        target_r = global_r + delta_row
        target_c = global_c + delta_column
        inside = ((target_r >= 0) & (target_r < rows) & (target_c >= 0) & (target_c < columns))
        candidate = np.full(current.shape, np.inf, dtype=height.dtype)
        candidate[inside] = height[target_r[inside], target_c[inside]]
        lower = inside & (candidate < current) & (candidate < best_height)
        best_height[lower] = candidate[lower]
        best_receiver[lower] = (target_r[lower] * columns + target_c[lower]).astype(np.int64)
    receiver[row0:row1, column0:column1] = best_receiver


def _sha256_arrays(height, receiver, tile_id):
    digest = hashlib.sha256()
    for array in (height, receiver, tile_id):
        digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def build_large_scale_network(height_m, *, budget=LargeScaleBudget(), spacing_m=30.0):
    """Build and audit a tiled D4 receiver graph for a square large DEM."""
    height = _validate_height(height_m, budget)
    if not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("spacing_m must be finite and positive")
    estimated = estimate_resident_bytes(height.shape[0], budget.tile_size)
    if estimated > budget.max_resident_bytes:
        raise MemoryError(f"estimated resident bytes {estimated} exceed budget")
    size = height.shape[0]
    records = _tile_records(size, budget.tile_size)
    receiver = np.full((size, size), -1, dtype=np.int64)
    tile_id = np.empty((size, size), dtype=np.int32)
    for index, (row0, row1, column0, column1) in enumerate(records):
        tile_id[row0:row1, column0:column1] = index
        _route_tile(height, receiver, row0, row1, column0, column1)
    flat_receiver = receiver.ravel()
    flat_tile = tile_id.ravel()
    flat_height = height.ravel()
    donors = np.flatnonzero(flat_receiver >= 0)
    target = flat_receiver[donors]
    cross_tile = donors[flat_tile[donors] != flat_tile[target]]
    boundary = np.zeros((size, size), dtype=bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    outlet = receiver < 0
    boundary_outlet = outlet & boundary
    accumulation = np.ones(flat_receiver.size, dtype=np.float64)
    order = np.argsort(-flat_height, kind="stable")
    for donor in order[flat_receiver[order] >= 0]:
        accumulation[flat_receiver[donor]] += accumulation[donor]
    side_counts = {
        "north": int(np.count_nonzero(boundary_outlet[0, :])),
        "south": int(np.count_nonzero(boundary_outlet[-1, :])),
        "west": int(np.count_nonzero(boundary_outlet[:, 0])),
        "east": int(np.count_nonzero(boundary_outlet[:, -1])),
    }
    arrays = {"height_m": height.copy(), "receiver": receiver, "tile_id": tile_id,
              "accumulation_cells": accumulation.reshape(size, size),
              "topological_order": order.astype(np.int64)}
    return {"schema": SCHEMA, "arrays": arrays, "metadata": {
        "shape": [size, size], "spacing_m": float(spacing_m), "tile_size": budget.tile_size,
        "tile_count": len(records), "tiles": [list(record) for record in records],
        "halo_cells": 1, "cross_tile_receiver_count": int(cross_tile.size),
        "outlet_count": int(np.count_nonzero(outlet)),
        "boundary_outlet_count": int(np.count_nonzero(boundary_outlet)),
        "interior_sink_count": int(np.count_nonzero(outlet & ~boundary)),
        "outlet_counts_by_side": side_counts,
        "estimated_resident_bytes": int(estimated),
        "identity_sha256": _sha256_arrays(height, receiver, tile_id),
    }}


def validate_large_scale_network(network, *, budget=None):
    """Independently verify coverage, D4 acyclicity, seams, outlets and memory."""
    if not isinstance(network, dict) or network.get("schema") != SCHEMA:
        raise ValueError("invalid large-scale schema")
    arrays, metadata = network["arrays"], network["metadata"]
    height = np.asarray(arrays["height_m"])
    receiver = np.asarray(arrays["receiver"])
    tile_id = np.asarray(arrays["tile_id"])
    if height.ndim != 2 or receiver.shape != height.shape or tile_id.shape != height.shape:
        raise ValueError("array shape mismatch")
    if np.any((receiver < -1) | (receiver >= height.size)):
        raise ValueError("receiver outside full-grid coverage")
    flat = receiver.ravel()
    cells = np.arange(height.size).reshape(height.shape)
    donors = np.flatnonzero(flat >= 0)
    target = flat[donors]
    donor_rows, donor_columns = np.divmod(donors, height.shape[1])
    target_rows, target_columns = np.divmod(target, height.shape[1])
    if np.any(np.maximum(np.abs(donor_rows - target_rows), np.abs(donor_columns - target_columns)) != 1):
        raise ValueError("receiver is not D4 adjacent")
    if np.any(height.ravel()[target] >= height.ravel()[donors]):
        raise ValueError("receiver is not strictly downhill")
    expected_crossing_count = int(np.count_nonzero((flat >= 0) & (tile_id.ravel() != tile_id.ravel()[np.maximum(flat, 0)])))
    order = np.asarray(arrays["topological_order"])
    if order.shape != (height.size,) or np.unique(order).size != height.size:
        raise ValueError("topological coverage is incomplete")
    rank = np.empty(height.size, dtype=np.int64); rank[order] = np.arange(height.size)
    if donors.size and np.any(rank[target] <= rank[donors]):
        raise ValueError("receiver graph contains a cycle or invalid order")
    estimated = estimate_resident_bytes(height.shape[0], int(metadata["tile_size"]))
    if budget is not None and estimated > budget.max_resident_bytes:
        raise MemoryError("network exceeds resident memory budget")
    boundary = np.zeros(height.shape, bool); boundary[[0, -1], :] = True; boundary[:, [0, -1]] = True
    outlets = flat < 0
    boundary_outlets = outlets.reshape(height.shape) & boundary
    sides = {"north": int(boundary_outlets[0].sum()), "south": int(boundary_outlets[-1].sum()),
             "west": int(boundary_outlets[:, 0].sum()), "east": int(boundary_outlets[:, -1].sum())}
    if sum(sides.values()) < int(metadata["boundary_outlet_count"]):
        raise ValueError("outlet side statistics disagree")
    return {"verified": True, "cells": int(height.size), "tile_count": int(metadata["tile_count"]),
            "coverage_fraction": 1.0, "d4_edges": int(donors.size),
            "cross_tile_receiver_count": expected_crossing_count, "outlet_count": int(outlets.sum()),
            "boundary_outlet_count": int(boundary_outlets.sum()), "outlet_counts_by_side": sides,
            "estimated_resident_bytes": estimated, "identity_sha256": metadata["identity_sha256"]}
