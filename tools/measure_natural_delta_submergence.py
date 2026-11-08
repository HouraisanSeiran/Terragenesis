"""Measure actual saved FV water over above-datum deposited marine cells."""
import argparse
import json
from pathlib import Path

import numpy as np


def run(directory, output):
    with np.load(directory / "result.npz") as a:
        bed = a["bed_m"]
        depth = a["depth_m"][-1]
        stage = a["stage_m"][-1]
        bar = (a["initial_bed_m"] < 0.) & (a["cell_type"] == 0) & (bed >= 0.)
        np.testing.assert_array_equal(stage, bed + depth)
        indices = np.argwhere(bar)
        highest = tuple(indices[np.argmax(bed[bar])])
        stats = lambda field: {"min": float(field[bar].min()), "median": float(np.median(field[bar])), "max": float(field[bar].max())}
        report = {"water_run": str(directory), "time_s": float(a["time_s"][-1]), "above_zero_original_marine_cell_count": int(bar.sum()),
            "final_actual_depth_over_above_zero_marine_bed_m": stats(depth), "final_actual_stage_over_above_zero_marine_bed_m": stats(stage),
            "above_zero_marine_bed_range_m": [float(bed[bar].min()), float(bed[bar].max())],
            "highest_original_marine_bed_cell": {"row_column": list(map(int, highest)), "bed_m": float(bed[highest]),
                "actual_depth_m": float(depth[highest]), "actual_stage_m": float(stage[highest])},
            "actual_dry_above_zero_marine_cells": int(np.sum(bar & (depth <= 2.e-6))),
            "interpretation": "positive bed elevation is a datum comparison; these deposited marine cells remain below their actual local FV water surface"}
    (output / "final-bed-submergence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--water-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.water_run, args.output), indent=2))
