"""Independent continuous threshold ODE checks for versioned TD face solvers."""

import argparse
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes


def reference_depth(bed, initial, spacing, duration, conductance):
    def derivative(time_s, depth):
        head = bed + depth
        donor = 0 if head[0] >= head[1] else 1
        recipient = 1 - donor
        sill = max(bed)
        release = conductance / spacing * max(0.0, head[donor] - max(sill, head[recipient]))
        result = np.zeros(2)
        result[donor] = -release
        result[recipient] = release
        return result

    solution = solve_ivp(derivative, (0.0, duration), initial, method="DOP853",
                         rtol=2e-12, atol=2e-13, max_step=duration / 80)
    if not solution.success:
        raise ValueError("independent threshold ODE reference failed")
    return solution.y[:, -1]


def audit():
    cases = [
        ([2.0, 0.0], [1.0, 0.0], 1.0, 1.0),
        ([0.0, 2.0], [0.0, 1.0], 1.0, 1.0),
        ([2.0, 0.0], [5.0, 0.0], 1.0, 5.0),
        ([0.0, 2.0], [0.0, 5.0], 1.0, 5.0),
        ([0.0, 2.0], [4.0, 0.0], 1.0, 1.0),
        ([2.0, 0.0], [0.0, 4.0], 1.0, 1.0),
        ([1300.0, 1300.0], [1.0, 0.0], 30.0, 60.0),
        ([0.0, 2.0], [2.0, 0.0], 1.0, 5.0),
        ([2.0, 0.0], [0.0, 0.0], 1.0, 5.0),
        ([2.0, 0.0], [3.0, 3.0], 30.0, 5.0),
    ]
    random = np.random.default_rng(20261002)
    for index in range(40):
        cases.append((random.uniform(0, 6, 2).tolist(), random.uniform(0, 8, 2).tolist(),
                      1.0 if index % 2 else 30.0, float(random.uniform(0.1, 30))))
    references = [reference_depth(np.array(bed), np.array(initial), spacing, duration, 0.6)
                  for bed, initial, spacing, duration in cases]
    summaries = {}
    for version, name in (("v2", "td_basin_storage_implicit"), ("v3", "td_basin_storage_v3"),
                          ("v4", "td_basin_storage_v4")):
        module_path = ROOT / "terrain_pipeline" / (name + ".py")
        if not module_path.exists():
            summaries[version] = {"status": "unavailable"}
            continue
        solver = importlib.import_module("terrain_pipeline." + name)
        records = []
        for index, (bed, initial, spacing, duration) in enumerate(cases):
            actual, forward, reverse, exported, forward_s, reverse_s = solver.exchange(
                np.array(initial), np.array(bed), np.array([[0, 1]], dtype=np.int64),
                np.array([], dtype=np.int64), np.array([], dtype=float),
                spacing, duration, solver.parameters(None), 2)
            error = float(np.max(abs(actual - references[index])))
            mass_error = float(abs(actual.sum() - sum(initial)))
            valid = bool(np.isfinite(actual).all() and np.min(actual) >= -1e-12)
            duration_valid = bool(np.all(forward_s + reverse_s <= duration + 1e-10))
            records.append({"case": index, "bed_m": bed, "initial_depth_m": initial,
                            "spacing_m": spacing, "duration_s": duration,
                            "reference_depth_m": references[index].tolist(), "actual_depth_m": actual.tolist(),
                            "max_depth_error_m": error, "mass_error_m": mass_error,
                            "positive_finite": valid, "duration_valid": duration_valid,
                            "passed": error <= 1e-8 and mass_error <= 1e-11 and valid and duration_valid})
        summaries[version] = {"status": "passed" if all(item["passed"] for item in records) else "failed",
                              "solver_sha256": file_sha256(module_path), "cases": records,
                              "max_depth_error_m": max(item["max_depth_error_m"] for item in records)}
    return {"schema": "td-independent-threshold-pair-v1", "utc": datetime.now(timezone.utc).isoformat(),
            "reference": "DOP853 integration of g/dx*(head_donor-max(sill,head_recipient))",
            "seed": 20261002, "case_count": len(cases), "versions": summaries,
            "hydraulic_ready": False, "publishable": False,
            "limitations": "Unforced two-cell threshold model correctness; not whole-domain convergence or momentum validation."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = audit()
    report["auditor_sha256"] = file_sha256(__file__)
    publish_bytes(arguments.output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({version: {key: record[key] for key in ("status", "max_depth_error_m") if key in record}
                      for version, record in report["versions"].items()}))
