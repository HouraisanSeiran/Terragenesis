"""What a 10 km base costs the river network, measured on one identical lattice.

`floodplain-2d-01` and `td-detail-01` both worked on the 10 km planning page. This
tool answers one question the reports could not: if the base field is the 10 km
interpolation instead of the direct 30 m sampling, **how different is the river
network** built on it?

The comparison holds everything else fixed:

* same window, same 30 m lattice, same D8 code, same fill, same boundary;
* the only difference is the elevation field (`analytic 30 m` vs `10 km page
  bilinearly sampled onto that lattice`).

Reported per field: slope distribution, drainage-area distribution (as quantiles
over the basin), the number and position of terminals, main-stem length and
relief, and the design discharge at the basin outlet. Differences are quoted both
absolutely and as a fraction of the fine-field value, because "how much must be
re-run" depends on which of those the old result depended on.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.hydrology_planning import coarse_condition_field, PlanningConfig  # noqa: E402
from terrain_pipeline.surface_rivers.metric_contracts import BoundaryGrid, TerrainGrid  # noqa: E402
from terrain_pipeline.surface_rivers.metric_drainage import route_diagnostic  # noqa: E402
from terrain_pipeline.surface_rivers.metric_fine_terrain import (  # noqa: E402
    FINE_SPACING_M, analytic_fine_field, bilinear_sample, fine_axes,
)

WORLD_SEED = 20261020
COARSE_PAGE_ORIGIN_M = (1_250_000.0, 1_200_000.0)
COARSE_PAGE_SHAPE = (12, 12)
DESIGN_RUNOFF_MM_H = 1.0


def terrain_grid(height, origin_xz_m, label):
    return TerrainGrid(np.ascontiguousarray(height, np.float64), np.ones(height.shape, bool),
                       origin_xz_m[0], origin_xz_m[1], FINE_SPACING_M, FINE_SPACING_M,
                       "conditioned_terrain", label, "0" * 64,
                       model_version="fine-terrain-01", generation_seed=WORLD_SEED,
                       condition_summary="base comparison on one identical lattice")


def closed_boundary(terrain):
    perimeter = np.zeros(terrain.valid_mask.shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    return BoundaryGrid.from_outlet_mask(terrain, perimeter, source_id="fine-terrain-01",
                                         source_sha256="0" * 64)


def describe(height, origin_xz_m, label):
    terrain = terrain_grid(height, origin_xz_m, label)
    boundary = closed_boundary(terrain)
    graph = route_diagnostic(terrain, boundary)
    area = np.zeros(height.size, np.float64)
    cell_area = FINE_SPACING_M ** 2
    flow = np.where(graph.valid_mask, cell_area, 0.).astype(np.float64).ravel()
    for cell in graph.order_downstream_first[::-1]:
        target = int(graph.receiver[cell])
        if target >= 0:
            flow[target] += flow[cell]
    area = flow.reshape(height.shape)
    slope = graph.edge_slope
    donor = graph.receiver >= 0
    discharge = area.ravel() * DESIGN_RUNOFF_MM_H / 1000. / 3600.
    terminals = np.flatnonzero((graph.receiver < 0) & graph.valid_mask.ravel())
    longest = int(np.argmax(np.where(graph.receiver < 0, area.ravel(), 0.)))
    return {
        "label": label,
        "height_range_m": [float(height.min()), float(height.max())],
        "mean_slope": float(slope[donor].mean()),
        "median_slope": float(np.median(slope[donor])),
        "slope_p10_p90": [float(np.percentile(slope[donor], 10)),
                          float(np.percentile(slope[donor], 90))],
        "terminals": int(terminals.size),
        "total_area_km2": float(graph.valid_mask.sum() * cell_area / 1e6),
        "drainage_area_quantiles_m2": {
            str(q): float(np.percentile(area.ravel(), q)) for q in (10, 50, 90, 99, 100)},
        "largest_basin_area_km2": float(area.ravel()[longest] / 1e6),
        "largest_basin_terminal_cell": int(longest),
        "max_discharge_m3_s": float(discharge.max()),
        "cells_with_slope_zero": int(np.count_nonzero(slope[donor] == 0.)),
        "graph_identity_sha256": graph.identity_sha256,
    }


def main():
    parser = argparse.ArgumentParser(description="10 km base vs 30 m base: river-network cost")
    parser.add_argument("--output", default=".scratch/fine-terrain-01/coarse-vs-fine-routing.json")
    parser.add_argument("--native-origin", type=int, nargs=2, default=(43234, 42560))
    parser.add_argument("--size", type=int, default=513)
    args = parser.parse_args()

    origin = (args.native_origin[0] * FINE_SPACING_M, args.native_origin[1] * FINE_SPACING_M)
    shape = (int(args.size), int(args.size))
    fine, _ = analytic_fine_field(WORLD_SEED, origin, shape)

    config = PlanningConfig()
    step = config.macro_span_m / config.samples_per_span
    gx = COARSE_PAGE_ORIGIN_M[0] + np.arange(COARSE_PAGE_SHAPE[1]) * step
    gz = COARSE_PAGE_ORIGIN_M[1] + np.arange(COARSE_PAGE_SHAPE[0]) * step
    east, south = np.meshgrid(gx, gz)
    page = np.asarray(coarse_condition_field(WORLD_SEED, east, south, config)[0], np.float64)
    xs, zs = fine_axes(origin, shape)
    coarse = bilinear_sample(page, COARSE_PAGE_ORIGIN_M, step, xs, zs)

    fine_report = describe(fine, origin, "analytic_30m")
    coarse_report = describe(coarse, origin, "coarse_10km_bilinear_on_30m")

    def ratio(key, sub=None):
        a = fine_report[key] if sub is None else fine_report[key][sub]
        b = coarse_report[key] if sub is None else coarse_report[key][sub]
        return {"fine": a, "coarse": b, "difference": b - a,
                "relative": (b - a) / a if a not in (0, 0.0) else None}

    report = {
        "schema": "coarse-vs-fine-routing-v1", "world_seed": WORLD_SEED,
        "window": {"native_origin": list(args.native_origin),
                   "origin_xz_m": list(origin), "shape": list(shape),
                   "spacing_m": FINE_SPACING_M,
                   "only_difference": ("the elevation field: direct 30 m sampling of the "
                                       "conditioning function vs the 10 km planning page "
                                       "bilinearly sampled onto the same lattice")},
        "finer": fine_report, "coarser": coarse_report,
        "comparison": {
            "mean_slope": ratio("mean_slope"),
            "median_slope": ratio("median_slope"),
            "terminals": ratio("terminals"),
            "largest_basin_area_km2": ratio("largest_basin_area_km2"),
            "max_discharge_m3_s": ratio("max_discharge_m3_s"),
            "area_p99": ratio("drainage_area_quantiles_m2", "99"),
            "same_largest_basin_terminal": bool(
                fine_report["largest_basin_terminal_cell"] == coarse_report["largest_basin_terminal_cell"]),
            "same_network": bool(fine_report["graph_identity_sha256"] ==
                                 coarse_report["graph_identity_sha256"])},
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=1, sort_keys=True))
    print(json.dumps(report["comparison"], indent=1))


if __name__ == "__main__":
    main()
