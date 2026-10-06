"""Bounded hydraulic adapter for one derived fine-bed candidate window.

The adapter consumes only ``derived_bed_m`` from an accepted fine window and
uses the existing conservative storage/conductance graph.  It never mutates
the candidate package or treats the result as a natural outlet or publishable
river network.
"""

from __future__ import annotations

import numpy as np

from terrain_pipeline.dynamic_surface_hydraulics import (
    HydraulicsInput, ResourceLimits, evaluate, validate,
)


def _grid_edges(shape):
    rows, columns = shape
    edges = []
    for row in range(rows):
        for column in range(columns):
            cell = row * columns + column
            if column + 1 < columns:
                edges.append((cell, cell + 1))
            if row + 1 < rows:
                edges.append((cell, cell + columns))
    return np.asarray(edges, dtype=np.int64).reshape((-1, 2))


def run_fine_bed_hydraulics(window, *, local_q_m3_s, boundary_stage_m,
                            dt_s, conductance_m2_s=1.0,
                            initial_depth_m=0.05, max_depth_m=20.0,
                            source="td-fine-bed-material-candidate",
                            datum="model_vertical_datum_m",
                            limits=None):
    """Solve a bounded candidate window and return a static-auditable result.

    ``boundary_stage_m`` is a complete ``(steps + 1, node_count)`` array;
    only nodes marked as boundaries are read.  This explicit boundary is an
    engineering tailwater input, not natural-mouth evidence.
    """
    if window.get("status") != "candidate":
        raise ValueError("only an accepted fine window can be solved")
    grid = window["grid"]
    shape = tuple(int(value) for value in grid["shape"])
    if len(shape) != 2 or min(shape) < 2:
        raise ValueError("fine window grid must be at least 2 by 2")
    bed = np.asarray(window["derived_bed_m"], dtype=np.float64)
    if bed.shape != shape or not np.isfinite(bed).all():
        raise ValueError("derived fine bed shape/finite contract failed")
    node_count = bed.size
    local = np.asarray(local_q_m3_s, dtype=np.float64)
    if local.ndim != 2 or local.shape[1] != node_count or not np.isfinite(local).all():
        raise ValueError("complete finite fine-bed forcing required")
    steps = local.shape[0]
    boundary_grid = np.zeros(shape, dtype=bool)
    boundary_grid[0, :] = True
    boundary_grid[-1, :] = True
    boundary_grid[:, 0] = True
    boundary_grid[:, -1] = True
    boundaries = boundary_grid.ravel()
    stage = np.asarray(boundary_stage_m, dtype=np.float64)
    if stage.shape != (steps + 1, node_count) or not np.isfinite(stage).all():
        raise ValueError("complete fine-bed boundary stage required")
    initial = bed.ravel() + float(initial_depth_m)
    initial[boundaries] = stage[0, boundaries]
    spacing = float(grid["spacing_m"])
    edges = _grid_edges(shape)
    conductance = np.full(len(edges), float(conductance_m2_s), dtype=np.float64)
    inputs = HydraulicsInput(
        bed_m=bed.ravel(), area_m2=np.full(node_count, spacing * spacing),
        initial_stage_m=initial.ravel(), edges=edges,
        conductance_m2_s=conductance, local_q_m3_s=local,
        boundary_mask=boundaries, boundary_stage_m=stage,
        dt_s=float(dt_s), max_depth_m=float(max_depth_m),
        valid_mask=np.ones(node_count, dtype=bool),
        protected_mask=np.zeros(node_count, dtype=bool),
        coords_m=np.array([[column * spacing, row * spacing]
                           for row in range(shape[0])
                           for column in range(shape[1])], dtype=np.float64),
        source=source, datum=datum, coords="window_local_xz_m",
        limits=limits or ResourceLimits(max_nodes=min(4096, node_count),
                                        max_edges=min(16384, len(edges)),
                                        max_steps=min(4096, steps),
                                        max_work=2_000_000),
    )
    result = evaluate(inputs)
    audit = validate(result)
    return {"algorithm": "td-derived-fine-bed-storage-conductance-v1",
            "bed_semantics": "derived_fine_bed_candidate",
            "source_window_id": window["window_id"],
            "source_fine_identity": window.get("window_identity_sha256"),
            "engineering_boundary": True,
            "natural_outlet_verified": False,
            "publishable": False,
            "result": result,
            "audit": audit}
