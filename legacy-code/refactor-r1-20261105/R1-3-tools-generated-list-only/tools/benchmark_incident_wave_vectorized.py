"""Read-only wave equivalence/timing on a real checkpoint and dry coast."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig, incident_wave_field as reference
from terrain_pipeline.surface_rivers.metric_fv_incident_wave_vectorized import incident_wave_field
from tools.run_natural_delta_fv_water import make_geometry


def benchmark(depth, geometry, config, repeats):
    expected = reference(depth, geometry, config)
    actual = incident_wave_field(depth, geometry, config)
    errors = {}
    for key in expected:
        np.testing.assert_allclose(actual[key], expected[key], rtol=2.e-14, atol=2.e-15)
        errors[key] = {"max_abs": float(abs(actual[key] - expected[key]).max()),
            "bitwise_equal": bool(np.array_equal(actual[key], expected[key]))}
    elapsed = {"reference": [], "vectorized": []}
    for repeat in range(repeats):
        # Alternate order to reduce interference from the concurrent simulation.
        functions = [("reference", reference), ("vectorized", incident_wave_field)]
        for name, function in functions[::1 if repeat % 2 == 0 else -1]:
            started = time.perf_counter()
            function(depth, geometry, config)
            elapsed[name].append(time.perf_counter() - started)
    medians = {name: statistics.median(values) for name, values in elapsed.items()}
    return {"direction": config.wave_direction_xz, "shape": depth.shape,
        "nonzero_wave_cells": int(np.count_nonzero(expected["wave_height_m"])), "errors": errors,
        "elapsed_s": elapsed, "median_s": medians, "speedup": medians["reference"] / medians["vectorized"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--wave-height", type=float, default=.3)
    parser.add_argument("--wave-period", type=float, default=5.)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    with np.load(args.checkpoint, allow_pickle=False) as saved:
        depth = saved["depth_m"].copy()
        geometry = make_geometry(saved["bed_m"].copy(), saved["cell_type"], 5.)
        meta = json.loads(str(saved["metadata_json"]))
    rng = np.random.default_rng(732)
    coast = rng.uniform(.02, 8., (73, 119))
    coast[15, :] = 0.
    coast[:, 41] = 0.
    coast[22, 41] = 1.e-5
    kinds = np.full(coast.shape, -1)
    kinds[::3, 0] = 0
    kinds[-1, ::4] = 0
    coast_geometry = make_geometry(np.zeros_like(coast), kinds, 5.)
    results = []
    for name, field, domain in [("checkpoint", depth, geometry), ("dry_coast", coast, coast_geometry)]:
        for direction in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            config = replace(BedloadConfig(), wave_direction_xz=direction,
                wave_height_m=args.wave_height, wave_period_s=args.wave_period)
            result = benchmark(field, domain, config, args.repeats)
            if name == "dry_coast" and args.wave_height > 0.:
                assert result["nonzero_wave_cells"] > 0
            result["scene"] = name
            results.append(result)
            print(name, direction, "speedup", round(result["speedup"], 3), "max_abs",
                max(row["max_abs"] for row in result["errors"].values()), flush=True)
    report = {"checkpoint": str(args.checkpoint), "checkpoint_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        "physical_time_s": meta["physical_time_s"], "repeats": args.repeats,
        "wave_height_m": args.wave_height, "wave_period_s": args.wave_period, "results": results,
        "tolerance": {"rtol": 2.e-14, "atol": 2.e-15},
        "scope": "wave helper only; concurrent production simulation may affect timings; no integration or simulation"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
