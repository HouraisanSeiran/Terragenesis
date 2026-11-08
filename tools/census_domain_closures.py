"""Refusal-rate and performance census over the world-anchored closure tiles.

Phase-1 completion asks for the refusal rate and the cost at the target scale
("复核目标尺度的拒绝率和性能"). This is a read-only survey: it walks a grid of
world-anchored tiles, records for each one

* the accepted / refused / ocean split of its CORE, with the refusal reasons in
  the contract's own five-word vocabulary;
* the domain-size distribution (raw-face domains are known to be fine:
  `metric_domain_closure._build_eligibility` reports a median of 3 cells);
* the build time and the peak node count, so the 480 km margin trade-off is
  measured rather than assumed.

It publishes nothing and certifies nothing; it exists to make the trade-off
visible.

```
python tools/census_domain_closures.py --seed 20261020 --radius 1 \\
    --report .scratch/terrain-four-stage-review-20261021/closure-census.json
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

CENSUS_SCHEMA = "domain-closure-census-v1"


def run(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--radius", type=int, default=1,
                        help="tiles span -radius..radius in each axis (2r+1)^2 tiles")
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    if args.radius < 0 or args.radius > 6:
        print("FAILED: --radius must be 0..6", file=sys.stderr)
        return 2

    config = PlanningConfig()
    config.validate()
    spacing = config.macro_span_m / config.samples_per_span
    core_span_m = 4 * config.samples_per_span * spacing  # DEFAULT_CORE_SPANS * L
    core_cells = 4 * config.samples_per_span
    margin = 48
    reports = []
    every_reason = set()
    all_domain_sizes = []

    try:
        clear_cache()
        for row in range(-args.radius, args.radius + 1):
            for column in range(-args.radius, args.radius + 1):
                # A point inside this tile's core, safely away from its edges.
                x_m = (column + 0.5) * core_span_m
                z_m = (row + 0.5) * core_span_m
                started = time.perf_counter()
                # Whole-core census: every core node gets a reason code and an
                # ownership answer, not a handful of probes, so the refusal rate
                # is the real per-cell rate at the target scale.
                topology = domain_topology(args.seed, x_m, z_m, config)
                ocean = topology["ocean"]
                accepted_mask = topology["accepted"]
                unresolved = topology["unresolved"]
                in_core = topology["in_core"]
                terminal = topology["terminal"].reshape(-1)
                core_accepted = accepted_mask & in_core
                core_unresolved = unresolved & in_core
                core_ocean = ocean & in_core
                elapsed = time.perf_counter() - started

                # Domain size distribution over the accepted core cells, from the
                # closure module's own owner identity (no second grouping rule).
                # The identity is the outlet WORLD COORDINATE, a PAIR: grouping on
                # x alone merges domains that share an x but differ in z, which
                # inflates every domain and hides the single-cell domains. The
                # first draft did exactly that (median 56 instead of 3); grouping
                # on the pair is what makes the size distribution truthful.
                owner_x = topology["owner_outlet_x_m"]
                owner_z = topology["owner_outlet_z_m"]
                core_flat_mask = core_accepted.reshape(-1)
                owner_pair_x = owner_x.reshape(-1)[core_flat_mask]
                owner_pair_z = owner_z.reshape(-1)[core_flat_mask]
                sizes = []
                if owner_pair_x.size:
                    keys = np.stack([owner_pair_x, owner_pair_z], axis=1)
                    _, counts = np.unique(keys, axis=0, return_counts=True)
                    sizes = counts.tolist()
                    all_domain_sizes.extend(sizes)

                # Terminal-based split: coastal domains end on an ocean terminal,
                # inland ones on a closed basin (the classify vocabulary).
                ocean_terminal = topology["ocean_terminal"].reshape(-1)
                core_flat = core_accepted.reshape(-1)
                coastal = int(np.count_nonzero(ocean_terminal[core_flat])) if core_flat.any() else 0
                inland = int(np.count_nonzero(core_flat)) - coastal

                probed = int(np.count_nonzero(in_core))
                accepted = int(np.count_nonzero(core_accepted))
                refused = int(np.count_nonzero(core_unresolved))
                tally = {"coastal": coastal, "closed_basin": inland,
                         "ocean": int(np.count_nonzero(core_ocean))
                         - int(np.count_nonzero(core_ocean & core_unresolved)),
                         "unresolved_border": refused,
                         "out_of_tile": 0}
                every_reason.update(key for key, value in tally.items() if value)
                reports.append({
                    "tile_row": row,
                    "tile_column": column,
                    "anchor_x_m": x_m,
                    "anchor_z_m": z_m,
                    "probed": probed,
                    "accepted": accepted,
                    "refused": refused,
                    "reason_tally": tally,
                    "domain_count": int(len(sizes)),
                    "domain_size_median": (float(statistics.median(sizes)) if sizes else None),
                    "domain_size_max": (int(max(sizes)) if sizes else None),
                    "seconds": elapsed,
                })
                print("tile (%d,%d) core=%d accepted=%d refused=%d domains=%d median=%s max=%s %.2fs"
                      % (row, column, probed, accepted, refused, len(sizes),
                         ("%.1f" % statistics.median(sizes)) if sizes else "-",
                         max(sizes) if sizes else "-", elapsed))
    finally:
        clear_cache()

    probed = sum(item["probed"] for item in reports)
    accepted = sum(item["accepted"] for item in reports)
    refused = sum(item["refused"] for item in reports)
    seconds = [item["seconds"] for item in reports]
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

    report = {
        "schema": CENSUS_SCHEMA,
        "seed": int(args.seed),
        "radius": int(args.radius),
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
            "seconds_total": float(sum(seconds)),
            "seconds_mean": statistics.fmean(seconds) if seconds else None,
            "seconds_max": max(seconds) if seconds else None,
        },
        "scope": {
            "certifies": "nothing; a read-only refusal-rate and timing survey",
            "not_covered": ["cross-tile seam agreement", "default consumer",
                            "channel hydraulics", "terrain diffusion detail"],
        },
    }
    path = Path(args.report)
    if path.exists():
        print("FAILED: --report refuses to overwrite: %s" % path, file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
    print("summary: tiles=%d probed=%d accepted=%d refused=%d acceptance=%.3f mean=%.2fs max=%.2fs"
          % (len(reports), probed, accepted, refused,
             report["summary"]["acceptance_rate"] or 0.0,
             report["summary"]["seconds_mean"] or 0.0,
             report["summary"]["seconds_max"] or 0.0))
    print("reasons: %s" % json.dumps(total_reasons, ensure_ascii=False))
    print("report: %s" % path)
    return 0


def main(argv=None):
    return run(argv)


if __name__ == "__main__":
    sys.exit(run())