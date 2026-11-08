"""Conservative static routing over a real DEM candidate.

Unknown DEM cells are barriers, never ocean and never certified outlets.  The
result is a routing candidate for review; it is not a natural-mouth proof.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from terrain_pipeline.irregular_grid import grid_mesh, strict_receivers, masked_mesh


ALGORITHM = "real-dem-irregular-strict-metric-graph-v2"


@dataclass(frozen=True)
class RealDemNetwork:
    receiver: np.ndarray
    order: np.ndarray
    accumulation_cells: np.ndarray
    boundary_outlet: np.ndarray
    unknown_adjacent_terminal: np.ndarray
    mesh: object = None


def build_real_dem_network(height_m, valid_mask, *, origin_xz_m=(0., 0.), spacing_m=90., world_seed=20261020, mesh=None):
    height = np.asarray(height_m, dtype=np.float64)
    valid = np.asarray(valid_mask, dtype=bool)
    if height.ndim != 2 or valid.shape != height.shape:
        raise ValueError("height and valid_mask shape mismatch")
    if np.any(valid & ~np.isfinite(height)):
        raise ValueError("valid DEM cells must be finite")
    if not valid.any():
        raise ValueError("DEM has no valid cells")
    if mesh is None:
        mesh = grid_mesh(height.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1],
                         dx_m=spacing_m, world_seed=world_seed)
    rows, cols = height.shape
    flat_height = height.ravel()
    flat_valid = valid.ravel()
    receiver, _, _ = strict_receivers(height, masked_mesh(mesh, valid), valid_mask=valid)
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
    unknown_adjacent = np.zeros((rows, cols), dtype=bool)
    for node in np.flatnonzero(flat_valid):
        neighbors = mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]
        unknown_adjacent.ravel()[node] = np.any(~flat_valid[neighbors])
    return RealDemNetwork(receiver.reshape(height.shape), order,
                           accumulation.reshape(height.shape),
                           boundary & valid & (receiver.reshape(height.shape) < 0),
                           valid & unknown_adjacent & (receiver.reshape(height.shape) < 0), mesh)


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
    mesh = network.mesh if network.mesh is not None else grid_mesh(height.shape, dx_m=90.)
    expected, _, _ = strict_receivers(height, masked_mesh(mesh, valid), valid_mask=valid)
    if not np.array_equal(flat_receiver, expected):
        raise ValueError("receiver must follow the irregular steepest metric edge")
    if np.unique(network.order).size != valid_ids.size or set(network.order.tolist()) != set(valid_ids.tolist()):
        raise ValueError("topological order does not cover valid cells")
    return {
        "verified": True,
        "algorithm": ALGORITHM,
        "valid_cells": int(valid.sum()),
        "unknown_cells": int((~valid).sum()),
        "downhill_edges": int(routed.sum()),
        "terminal_cells": int(np.count_nonzero(valid & (receiver < 0))),
        "boundary_outlet_candidates": int(network.boundary_outlet.sum()),
        "unknown_adjacent_terminals": int(network.unknown_adjacent_terminal.sum()),
        "natural_outlet_verified": False,
        "status": "real_dem_candidate_not_publishable",
    }
