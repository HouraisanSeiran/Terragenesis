"""Masked matching differential, divergence and mass checks without a TD solve."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_storage import exchange_threshold_pair as exchange
from terrain_pipeline.basin_storage import parameters_threshold_pair as parameters
from terrain_pipeline.basin_storage import exchange_strang_two_sweep as numpy_exchange


def verify():
    random = np.random.default_rng(2026100209)
    records = []
    for case in range(80):
        rows, columns = int(random.integers(2, 6)), int(random.integers(3, 8))
        grid = np.arange(rows * columns).reshape(rows, columns)
        valid = random.random(rows * columns) > .2
        faces = np.vstack((np.column_stack((grid[:, :-1].ravel(), grid[:, 1:].ravel())),
                           np.column_stack((grid[:-1].ravel(), grid[1:].ravel())))).astype(np.int64)
        faces = faces[valid[faces].all(axis=1)]
        bed = random.uniform(1300, 1400, valid.size)
        depth = random.uniform(0, 8, valid.size)
        depth[~valid] = 0
        boundary = np.flatnonzero(valid & ((grid.ravel() // columns == 0) | (grid.ravel() % columns == 0)))
        width = np.full(len(boundary), 30.)
        duration = (60., 5., 2.5, 1.25)[case % 4]
        arguments = (depth, bed, faces, boundary, width, 30., duration, parameters(None), columns)
        compiled = exchange(*arguments)
        reference = numpy_exchange(*arguments)
        error = max(float(abs(actual - expected).max(initial=0)) for actual, expected in zip(compiled, reference))
        final, forward, reverse, exported, forward_s, reverse_s = compiled
        net = forward - reverse
        divergence = np.bincount(faces[:, 1], weights=net, minlength=valid.size) - np.bincount(
            faces[:, 0], weights=net, minlength=valid.size)
        np.add.at(divergence, boundary, -exported)
        divergence_error = float(abs((final - depth) * 900 - divergence).max())
        mass_error = float(abs(final.sum() * 900 + exported.sum() - depth.sum() * 900))
        activity_equal = np.array_equal(forward_s, reference[4]) and np.array_equal(reverse_s, reference[5])
        passed = error < 1e-8 and divergence_error < 1e-8 and mass_error < 1e-8 and activity_equal and np.all(final >= 0)
        records.append({"case": case, "shape": [rows, columns], "unknown_cells": int((~valid).sum()),
                        "faces": len(faces), "dt_s": duration, "max_differential": error,
                        "divergence_error_m3": divergence_error, "mass_error_m3": mass_error,
                        "activity_equal": activity_equal, "passed": bool(passed)})
    report = {"schema": "td-v4-masked-matching-differential-v1", "cases": records,
              "all_passed": all(record["passed"] for record in records), "seed": 2026100209,
              "max_differential": max(record["max_differential"] for record in records),
              "code_sha256": {name: file_sha256(ROOT / name) for name in (
                  "terrain_pipeline/td_basin_storage_v4.py", "terrain_pipeline/td_basin_storage_implicit.py",
                  "tools/verify_td_basin_storage_v4_matching.py")},
              "hydraulic_ready": False, "publishable": False,
              "scope": "unforced masked D4 matching and engineered boundary kernels; not full-domain convergence"}
    path = ROOT / "verification/td-basin-generation" / ("A-v4-matching-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(path, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({"path": str(path), "sha256": file_sha256(path), "all_passed": report["all_passed"],
                      "max_differential": report["max_differential"]}))
    if not report["all_passed"]:
        raise AssertionError("v4 masked matching differential failed")


if __name__ == "__main__":
    verify()
