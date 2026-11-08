"""Refusal-rate and cost census for the sediment and coupled ledgers.

`census_domain_closures.py` surveys the **closure** half: accepted / refused / ocean
split with the contract's own five-word vocabulary, domain sizes, and build time.
Phase-1 completion also asks for the refusal rate and the cost **of the sediment and
coupled chains**, and that has no counterpart yet -- so this tool walks the same tile
grid, with the same vocabulary and the same tile geometry, and records what the two
sediment ledgers cost and what they had to work with.

Read-only. It publishes nothing, certifies nothing and writes no verification
evidence; it makes the trade-off visible.

What it adds over the closure census, and why each is needed:

* **sediment timing and saturation**: `slope_gain` saturates on most cells, so the
  saturated fraction is the honest measure of how much signal the slope law carries;
* **coupled timing and capacity**: the coupled ledger's extra cost over sediment is
  the price of the hydraulic chain, and `capacity_utilisation` / `zero_capacity_cells`
  say whether the capacity gate had room to act on that tile;
* **the same refusal tally**, so a reader can put the two censuses side by side
  without reconciling two vocabularies.

```
python tools/census_domain_coupled.py --seed 20261020 --radius 1 --intervals 2 \\
    --report .scratch/terrain-four-stage-review-20261021/coupled-census.json
```
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from terrain_pipeline.hydrology_planning import PlanningConfig  # noqa: E402
from terrain_pipeline.surface_rivers.metric_domain_closure import (  # noqa: E402
    clear_cache, domain_topology,
)
from terrain_pipeline.surface_rivers.metric_domain_coupled import (  # noqa: E402
    MAX_INTERVALS as COUPLED_MAX_INTERVALS,
    solve_domain_coupled,
)
from terrain_pipeline.surface_rivers.metric_domain_sediment import (  # noqa: E402
    solve_domain_sediment,
)

CENSUS_SCHEMA = "domain-coupled-census-v1"


def _percentiles(values):
    if not values:
        return None
    ordered = sorted(values)
    def at(q):
        index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
        return float(ordered[index])
    return {"min": float(ordered[0]), "p25": at(0.25), "median": at(0.5),
            "p75": at(0.75), "max": float(ordered[-1]),
            "mean": float(statistics.fmean(ordered))}


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--radius", type=int, default=1,
                        help="tiles span -radius..radius in each axis, (2r+1)^2 tiles")
    parser.add_argument("--intervals", type=int, default=2,
                        help="physical intervals per ledger (kept small: this is a cost census)")
    parser.add_argument("--rain-mm-h", type=float, default=4.0)
    parser.add_argument("--center", nargs=2, type=float, default=None, metavar=("X", "Z"),
                        help="world x z the tile family is centred on. Default centres it on the "
                             "ORIGIN, which at a fine lattice lands the whole family in whatever "
                             "terrain happens to sit near (0,0) -- measured: at 30 m all nine tiles "
                             "anchor to heights -136..-254 m, i.e. open ocean, producing a degenerate "
                             "100%-ocean census that cannot measure a land refusal rate.")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    if args.radius < 0 or args.radius > 6:
        print("FAILED: --radius must be 0..6", file=sys.stderr)
        return 2
    if not 1 <= args.intervals <= COUPLED_MAX_INTERVALS:
        print("FAILED: --intervals must be 1..%d" % COUPLED_MAX_INTERVALS, file=sys.stderr)
        return 2
    if args.rain_mm_h < 0:
        print("FAILED: --rain-mm-h must be nonnegative", file=sys.stderr)
        return 2

    # The closure lattice is NOT the terrain grid. This census runs on the 7680 m
    # conditioning lattice and takes no scale knob: forcing its node spacing to
    # 30 m was measured to refuse 100% of cells, because DEFAULT_MARGIN_NODES is a
    # NODE count (48 nodes = 1.44 km at 30 m, not the 480 km it means at 10 km).
    # A 30 m refusal census must use the native-page mechanism in
    # `metric_cross_region`, not this coarse lattice.
    config = PlanningConfig()
    config.validate()
    spacing = config.macro_span_m / config.samples_per_span
    core_span_m = 4 * config.samples_per_span * spacing  # DEFAULT_CORE_SPANS * L
    core_cells = 4 * config.samples_per_span
    margin = 48

    reports = []
    every_reason = set()
    all_domain_sizes = []
    utilisation = []
    saturated = []

    try:
        clear_cache()
        for row in range(-args.radius, args.radius + 1):
            for column in range(-args.radius, args.radius + 1):
                # Tile family is anchored around `--center`, never implicitly at the
                # origin: at a fine lattice the origin happens to be open ocean, and a
                # 100%-ocean census reports a refusal rate that means nothing.
                center_x, center_z = ((0.0, 0.0) if args.center is None
                                      else (float(args.center[0]), float(args.center[1])))
                x_m = center_x + (column + 0.5) * core_span_m
                z_m = center_z + (row + 0.5) * core_span_m
                points = [(x_m, z_m)]

                started = time.perf_counter()
                topology = domain_topology(args.seed, x_m, z_m, config)
                ocean = topology["ocean"]
                accepted_mask = topology["accepted"]
                unresolved = topology["unresolved"]
                in_core = topology["in_core"]
                core_accepted = accepted_mask & in_core
                core_unresolved = unresolved & in_core
                core_ocean = ocean & in_core
                closure_seconds = time.perf_counter() - started

                # Domain size distribution from the closure module's own owner
                # identity, grouped on the PAIR (grouping on x alone merges domains
                # that share x and hides single-cell domains -- the closure census
                # records that mistake; it is not repeated here).
                core_flat_mask = core_accepted.reshape(-1)
                owner_x = topology["owner_outlet_x_m"].reshape(-1)[core_flat_mask]
                owner_z = topology["owner_outlet_z_m"].reshape(-1)[core_flat_mask]
                sizes = []
                if owner_x.size:
                    keys = np.stack([owner_x, owner_z], axis=1)
                    _, counts = np.unique(keys, axis=0, return_counts=True)
                    sizes = counts.tolist()
                    all_domain_sizes.extend(sizes)

                ocean_terminal = topology["ocean_terminal"].reshape(-1)
                core_flat = core_accepted.reshape(-1)
                coastal = int(np.count_nonzero(ocean_terminal[core_flat])) if core_flat.any() else 0
                inland = int(np.count_nonzero(core_flat)) - coastal
                tally = {"coastal": coastal, "closed_basin": inland,
                         "ocean": int(np.count_nonzero(core_ocean))
                         - int(np.count_nonzero(core_ocean & core_unresolved)),
                         "unresolved_border": int(np.count_nonzero(core_unresolved)),
                         "out_of_tile": 0}
                every_reason.update(key for key, value in tally.items() if value)

                # ---- sediment ledger ------------------------------------------
                started = time.perf_counter()
                sediment = solve_domain_sediment(args.seed, points, config=config,
                                                 intervals=args.intervals)
                sediment_seconds = time.perf_counter() - started
                sediment_totals = sediment["metadata"]["totals"]

                # ---- coupled ledger -------------------------------------------
                started = time.perf_counter()
                coupled = solve_domain_coupled(args.seed, points, args.rain_mm_h,
                                               config=config, intervals=args.intervals)
                coupled_seconds = time.perf_counter() - started
                coupled_totals = coupled["metadata"]["totals"]

                utilisation.append(float(coupled_totals["capacity_utilisation"]))
                saturated.append(float(sediment_totals["entrainment_saturated_fraction"]))

                reports.append({
                    "tile_row": row,
                    "tile_column": column,
                    "anchor_x_m": x_m,
                    "anchor_z_m": z_m,
                    "probed": int(np.count_nonzero(in_core)),
                    "accepted": int(np.count_nonzero(core_accepted)),
                    "refused": int(np.count_nonzero(core_unresolved)),
                    "reason_tally": tally,
                    "domain_count": int(len(sizes)),
                    "domain_size_median": (float(statistics.median(sizes)) if sizes else None),
                    "domain_size_max": (int(max(sizes)) if sizes else None),
                    "seconds_closure": closure_seconds,
                    "seconds_sediment": sediment_seconds,
                    "seconds_coupled": coupled_seconds,
                    "sediment": {
                        "weathered_m3": sediment_totals["weathered_total_m3"],
                        "entrained_m3": sediment_totals["entrained_total_m3"],
                        "delivered_m3": sediment_totals["delivered_total_m3"],
                        "entrainment_saturated_fraction":
                            sediment_totals["entrainment_saturated_fraction"],
                    },
                    "coupled": {
                        "water_release_m3": coupled_totals["water_release_total_m3"],
                        "entrained_m3": coupled_totals["entrained_total_m3"],
                        "capacity_m3": coupled_totals["capacity_volume_total_m3"],
                        "capacity_utilisation": coupled_totals["capacity_utilisation"],
                        "capacity_violation_m3": coupled_totals["capacity_violation_m3"],
                        "zero_capacity_cells": coupled_totals["zero_capacity_cells"],
                        "mean_channel_width_m": coupled_totals["mean_channel_width_m"],
                        "max_channel_width_m": coupled_totals["max_channel_width_m"],
                        "mean_excess_shear_pa": coupled_totals["mean_excess_shear_pa"],
                    },
                })
                print("tile (%d,%d) core=%d accepted=%d refused=%d domains=%d "
                      "closure=%.2fs sediment=%.2fs coupled=%.2fs util=%.3f sat=%.3f"
                      % (row, column, int(np.count_nonzero(in_core)),
                         int(np.count_nonzero(core_accepted)),
                         int(np.count_nonzero(core_unresolved)), len(sizes),
                         closure_seconds, sediment_seconds, coupled_seconds,
                         coupled_totals["capacity_utilisation"],
                         sediment_totals["entrainment_saturated_fraction"]))
    finally:
        clear_cache()

    probed = sum(item["probed"] for item in reports)
    accepted = sum(item["accepted"] for item in reports)
    refused = sum(item["refused"] for item in reports)
    total_reasons = {}
    for item in reports:
        for key, value in item["reason_tally"].items():
            total_reasons[key] = total_reasons.get(key, 0) + value
    size_stats = None
    if all_domain_sizes:
        size_stats = {
            "domains": len(all_domain_sizes),
            "median_cells": float(statistics.median(all_domain_sizes)),
            "mean_cells": float(statistics.fmean(all_domain_sizes)),
            "max_cells": int(max(all_domain_sizes)),
            "single_cell_share": float(
                sum(1 for value in all_domain_sizes if value == 1) / len(all_domain_sizes)),
        }
    closure_seconds = [item["seconds_closure"] for item in reports]
    sediment_seconds = [item["seconds_sediment"] for item in reports]
    coupled_seconds = [item["seconds_coupled"] for item in reports]
    worst_violation = max((item["coupled"]["capacity_violation_m3"] for item in reports),
                          default=0.0)

    report = {
        "schema": CENSUS_SCHEMA,
        "seed": int(args.seed),
        "radius": int(args.radius),
        "intervals": int(args.intervals),
        "rain_mm_h": float(args.rain_mm_h),
        "center_xz_m": [float(args.center[0]) if args.center else 0.0,
                        float(args.center[1]) if args.center else 0.0],
        "config": {"macro_span_m": config.macro_span_m,
                   "samples_per_span": config.samples_per_span,
                   "spacing_m": spacing,
                   "core_span_m": core_span_m,
                   "core_cells": core_cells,
                   "margin_nodes": margin,
                   "margin_km": margin * spacing / 1000.0,
                   "tile_nodes": (core_cells + 1 + 2 * margin) ** 2},
        "tiles": reports,
        "summary": {
            "tiles": len(reports),
            "probed_points": probed,
            "accepted": accepted,
            "refused": refused,
            "acceptance_rate": (accepted / probed) if probed else None,
            "refusal_rate": (refused / probed) if probed else None,
            "reason_tally": total_reasons,
            "vocabulary_observed": sorted(every_reason),
            "domain_size": size_stats,
            "seconds_closure": {"total": float(sum(closure_seconds)),
                                "mean": _percentiles(closure_seconds)["mean"] if closure_seconds else None,
                                "max": max(closure_seconds) if closure_seconds else None},
            "seconds_sediment": {"total": float(sum(sediment_seconds)),
                                 "mean": _percentiles(sediment_seconds)["mean"] if sediment_seconds else None,
                                 "max": max(sediment_seconds) if sediment_seconds else None},
            "seconds_coupled": {"total": float(sum(coupled_seconds)),
                                "mean": _percentiles(coupled_seconds)["mean"] if coupled_seconds else None,
                                "max": max(coupled_seconds) if coupled_seconds else None},
            "capacity_utilisation": _percentiles(utilisation),
            "sediment_saturated_fraction": _percentiles(saturated),
            "worst_capacity_violation_m3": worst_violation,
            "total_entrained_coupled_m3": float(sum(item["coupled"]["entrained_m3"]
                                                    for item in reports)),
            "total_capacity_coupled_m3": float(sum(item["coupled"]["capacity_m3"]
                                                   for item in reports)),
        },
        "scope": {
            "certifies": "nothing; a read-only refusal-rate, saturation and timing survey",
            "not_covered": ["cross-tile seam agreement", "default consumer",
                            "channel hydraulics", "terrain diffusion detail",
                            "calibration of the declared coefficients"],
        },
    }
    path = Path(args.report)
    if path.exists():
        print("FAILED: --report refuses to overwrite: %s" % path, file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
    print("summary: tiles=%d probed=%d accepted=%d refused=%d acceptance=%.3f"
          % (len(reports), probed, accepted, refused,
             report["summary"]["acceptance_rate"] or 0.0))
    print("time: closure mean=%.2fs sediment mean=%.2fs coupled mean=%.2fs"
          % (report["summary"]["seconds_closure"]["mean"] or 0.0,
             report["summary"]["seconds_sediment"]["mean"] or 0.0,
             report["summary"]["seconds_coupled"]["mean"] or 0.0))
    print("capacity utilisation: %s" % json.dumps(report["summary"]["capacity_utilisation"]))
    print("reasons: %s" % json.dumps(total_reasons, ensure_ascii=False))
    print("report: %s" % path)
    return 0


def main(argv=None):
    return run(argv)


if __name__ == "__main__":
    sys.exit(run())
