"""Independent nonlinear ODE check of simultaneous SSP-RK2 transport."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
import terrain_pipeline.basin_storage as transport


def audit():
    random = np.random.default_rng(20261002)
    cases = []
    grid = np.arange(12).reshape(3, 4)
    faces = np.vstack((np.column_stack((grid[:, :-1].ravel(), grid[:, 1:].ravel())),
                       np.column_stack((grid[:-1].ravel(), grid[1:].ravel())))).astype(np.int64)
    first, second = faces[:, 0], faces[:, 1]
    for case in range(16):
        bed = random.uniform(0, 4, 12)
        initial = random.uniform(0, 3, 12)
        initial[random.random(12) < .25] = 0
        boundary = np.array([0, 3, 8, 11], np.int64) if case % 2 else np.array([], np.int64)
        widths = np.ones(len(boundary)) * 2
        sill = np.maximum(bed[first], bed[second])

        def derivative(time, depth):
            head = bed + depth
            positive = head[first] >= head[second]
            signed = .6 * np.where(positive, np.maximum(head[first] - np.maximum(sill, head[second]), 0),
                                  -np.maximum(head[second] - np.maximum(sill, head[first]), 0))
            result = np.bincount(second, weights=signed, minlength=12) - np.bincount(first, weights=signed, minlength=12)
            result[boundary] -= .6 * widths * depth[boundary]
            return result

        duration = 4.
        reference = solve_ivp(derivative, (0, duration), initial, method="DOP853", rtol=1e-11, atol=1e-12)
        tighter = solve_ivp(derivative, (0, duration), initial, method="DOP853", rtol=1e-12, atol=1e-13)
        if not reference.success or not tighter.success or abs(reference.y[:, -1] - tighter.y[:, -1]).max() > 1e-8:
            raise ValueError("nonlinear reference insufficiently resolved")
        errors, ledger_errors = [], []
        for step in (.1, .05, .025, .0125):
            transport.validate_cfl(faces, boundary, widths, 1., step, .6, 12)
            depth = initial.copy()
            net = np.zeros(len(faces))
            exported = np.zeros(len(boundary))
            for iteration in range(round(duration / step)):
                depth, forward, reverse, boundary_out, active_forward, active_reverse = transport._compiled_exchange(
                    depth, bed, faces, boundary, widths, 1., step, .6, np.array([], np.int64), np.array([], np.int64))
                if np.any(depth < 0) or np.any(active_forward + active_reverse > step + 1e-12):
                    raise ValueError("RK positivity/activity failed")
                net += forward - reverse
                exported += boundary_out
            divergence = np.bincount(second, weights=net, minlength=12) - np.bincount(first, weights=net, minlength=12)
            divergence[boundary] -= exported
            ledger_error = float(abs(depth - initial - divergence).max())
            if ledger_error > 1e-10 or abs(depth.sum() + exported.sum() - initial.sum()) > 1e-10:
                raise ValueError("RK cell/global conservation failed")
            errors.append(float(abs(depth - tighter.y[:, -1]).max()))
            ledger_errors.append(ledger_error)
        passed = errors[-1] <= 1e-4 and errors[-1] < errors[0] / 4
        cases.append({"case": case, "bed_m": bed.tolist(), "initial_depth_m": initial.tolist(),
                      "boundary_cells": boundary.tolist(), "depth_errors_m": errors,
                      "max_divergence_error_m3": max(ledger_errors), "passed": passed})
    return {"schema": "td-v6-independent-nonlinear-transport-v1", "utc": datetime.now(timezone.utc).isoformat(),
            "seed": 20261002, "cases": cases, "all_passed": all(case["passed"] for case in cases),
            "reference": "independent NumPy threshold ODE integrated with DOP853; never calls production stage derivative",
            "substeps_s": [.1, .05, .025, .0125], "duration_s": 4., "hydraulic_ready": False,
            "solver_sha256": file_sha256(ROOT / 'terrain_pipeline/basin_storage.py'), "auditor_sha256": file_sha256(__file__),
            "limitations": "Unforced nonlinear 3x4 wet/dry, saddle and open-boundary transport. Does not verify full-domain forcing or actual momentum."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = audit()
    publish_bytes(arguments.output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode())
    print(json.dumps({"all_passed": report["all_passed"], "max_fine_error_m": max(case["depth_errors_m"][-1] for case in report["cases"])}))
    if not report["all_passed"]:
        raise AssertionError("nonlinear RK audit failed")
