"""Conservative static routing over a real DEM candidate.

Unknown DEM cells are barriers, never ocean and never certified outlets.  The
result is a routing candidate for review; it is not a natural-mouth proof.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RealDemNetwork:
    receiver: np.ndarray
    order: np.ndarray
    accumulation_cells: np.ndarray
    boundary_outlet: np.ndarray
    unknown_adjacent_terminal: np.ndarray


def build_real_dem_network(height_m, valid_mask, *, connectivity=8):
    height = np.asarray(height_m, dtype=np.float64)
    valid = np.asarray(valid_mask, dtype=bool)
    if height.ndim != 2 or valid.shape != height.shape:
        raise ValueError("height and valid_mask shape mismatch")
    if connectivity not in (4, 8):
        raise ValueError("connectivity must be 4 or 8")
    if np.any(valid & ~np.isfinite(height)):
        raise ValueError("valid DEM cells must be finite")
    if not valid.any():
        raise ValueError("DEM has no valid cells")
    directions = ((-1, 0), (0, -1), (0, 1), (1, 0))
    if connectivity == 8:
        directions = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1),
                      (1, -1), (1, 0), (1, 1))
    rows, cols = height.shape
    receiver = np.full(height.size, -1, dtype=np.int64)
    flat_height = height.ravel()
    flat_valid = valid.ravel()
    for row, col in zip(*np.nonzero(valid)):
        source_id = int(row * cols + col)
        best = float(height[row, col])
        target_id = -1
        for delta_row, delta_col in directions:
            target_row, target_col = row + delta_row, col + delta_col
            if not (0 <= target_row < rows and 0 <= target_col < cols):
                continue
            candidate_id = target_row * cols + target_col
            if flat_valid[candidate_id] and flat_height[candidate_id] < best:
                best = float(flat_height[candidate_id])
                target_id = candidate_id
        receiver[source_id] = target_id
    valid_ids = np.flatnonzero(flat_valid)
    order = valid_ids[np.argsort(-flat_height[valid_ids], kind="stable")]
    accumulation = np.zeros(height.size, dtype=np.float64)
    accumulation[valid_ids] = 1.0
    for source_id in order:
        target_id = receiver[source_id]
        if target_id >= 0:
            accumulation[target_id] += accumulation[source_id]
    boundary = np.zeros((rows, cols), dtype=bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    unknown = ~valid
    unknown_adjacent = np.zeros((rows, cols), dtype=bool)
    for delta_row, delta_col in directions:
        shifted = np.zeros_like(unknown)
        source_rows = slice(max(0, delta_row), min(rows, rows + delta_row))
        source_cols = slice(max(0, delta_col), min(cols, cols + delta_col))
        target_rows = slice(max(0, -delta_row), min(rows, rows - delta_row))
        target_cols = slice(max(0, -delta_col), min(cols, cols - delta_col))
        shifted[target_rows, target_cols] = unknown[source_rows, source_cols]
        unknown_adjacent |= shifted
    return RealDemNetwork(receiver.reshape(height.shape), order,
                           accumulation.reshape(height.shape),
                           boundary & valid & (receiver.reshape(height.shape) < 0),
                           valid & unknown_adjacent & (receiver.reshape(height.shape) < 0))


def validate_real_dem_network(network: RealDemNetwork, height_m, valid_mask):
    height = np.asarray(height_m, dtype=np.float64)
    valid = np.asarray(valid_mask, dtype=bool)
    receiver = np.asarray(network.receiver)
    if receiver.shape != height.shape or valid.shape != height.shape:
        raise ValueError("network shape mismatch")
    flat_receiver = receiver.ravel()
    flat_height = height.ravel()
    valid_ids = np.flatnonzero(valid.ravel())
    targets = flat_receiver[valid_ids]
    if np.any((targets < -1) | (targets >= height.size)):
        raise ValueError("receiver outside grid")
    routed = targets >= 0
    if np.any(~valid.ravel()[targets[routed]]):
        raise ValueError("receiver points into unknown DEM")
    if np.any(flat_height[targets[routed]] >= flat_height[valid_ids[routed]]):
        raise ValueError("receiver is not strictly downhill")
    if np.unique(network.order).size != valid_ids.size or set(network.order.tolist()) != set(valid_ids.tolist()):
        raise ValueError("topological order does not cover valid cells")
    return {
        "verified": True,
        "valid_cells": int(valid.sum()),
        "unknown_cells": int((~valid).sum()),
        "downhill_edges": int(routed.sum()),
        "terminal_cells": int(np.count_nonzero(valid & (receiver < 0))),
        "boundary_outlet_candidates": int(network.boundary_outlet.sum()),
        "unknown_adjacent_terminals": int(network.unknown_adjacent_terminal.sum()),
        "natural_outlet_verified": False,
        "status": "real_dem_candidate_not_publishable",
    }
