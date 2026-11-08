"""Manufactured wet-domain solutions for versioned complete rain/transport solvers."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
from scipy.linalg import expm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from tools.audit_td_basin_generation import audit_storage


def audit(version):
    if version == "v5":
        from terrain_pipeline.basin_storage import storagev5_simulate as simulate_basin_storage
    elif version == "v6":
        from terrain_pipeline.basin_storage import storagev6_simulate as simulate_basin_storage
    elif version == "v7":
        from terrain_pipeline.basin_storage import storagev7_simulate as simulate_basin_storage
    else:
        raise ValueError("known solver version required")
    random = np.random.default_rng(20261002)
    cases = []
    substeps = (5., 2.5, 1.25, .625, .3125) if version == "v5" else (2.5, 1.25, .625, .3125)
    runoff = RunoffParameters(initial_soil_mm=0, initial_fast_mm=0, initial_slow_mm=0,
                              potential_et_mm_h=0, percolation_mm_h=0, infiltration_capacity_mm_h=0)
    for case in range(12):
        shape = ((2, 3), (3, 4), (1, 4))[case % 3]
        spacing = (10., 30., 100.)[case % 3]
        initial = random.uniform(.2, 2., shape)
        rain = random.uniform(0, 60., (2,) + shape)
        opened = np.zeros(shape, bool)
        if case >= 6:
            opened[:, 0] = True
        source = make_td_source(np.zeros(shape), spacing_m=spacing, open_boundary_mask=opened)
        hierarchy = build_basin_hierarchy(source)
        arrays = hierarchy["arrays"]
        cells = initial.size
        matrix = np.zeros((cells + 1, cells + 1))
        for first, second in arrays["face_cells"]:
            matrix[first, first] -= .6 / spacing
            matrix[second, second] -= .6 / spacing
            matrix[first, second] += .6 / spacing
            matrix[second, first] += .6 / spacing
        for cell in arrays["boundary_cells"]:
            row, column = divmod(int(cell), shape[1])
            sides = int(row == 0) + int(row == shape[0] - 1) + int(column == 0) + int(column == shape[1] - 1)
            matrix[cell, cell] -= sides * .6 / spacing
        duration = 300.
        reference = np.concatenate((initial.ravel(), [1.]))
        for rates in rain:
            matrix[:-1, -1] = rates.ravel() / 1000 / 3600
            reference = expm(matrix * duration) @ reference
        errors = []
        ledgers = []
        for step in substeps:
            result = simulate_basin_storage(hierarchy, rain, dt_s=duration, initial_depth_m=initial,
                runoff_parameters=runoff, parameters={"substep_s": step, "surface_evaporation_mm_h": 0})
            error = float(abs(result["arrays"]["depth_m"][-1] - reference[:-1]).max())
            errors.append(error)
            ledgers.append(audit_storage(result["arrays"], result["metadata"])["max_step_global_residual_m3"])
            if result["arrays"]["depth_m"].min() <= 1e-9:
                raise ValueError("manufactured wet assumption invalid")
        ratio = [errors[index] / max(errors[index + 1], 1e-15) for index in range(len(errors) - 1)]
        passed = errors[-1] <= 1e-5 and all(value >= 3.8 for value in ratio) and max(ledgers) <= 1e-6
        cases.append({"case": case, "shape": list(shape), "spacing_m": spacing,
                      "engineered_open_cells": int(opened.sum()), "timestep_errors_m": errors,
                      "refinement_error_ratios": ratio, "max_global_balance_residual_m3": max(ledgers), "passed": passed})
    code_names = [f"terrain_pipeline/td_basin_storage_{version}.py", f"terrain_pipeline/td_basin_storage_{version}_io.py",
                  'terrain_pipeline/basin_storage.py' if version == "v5" else 'terrain_pipeline/basin_storage.py']
    if version == "v7":
        code_names.append('terrain_pipeline/basin_storage.py')
    return {"schema": "td-independent-manufactured-forcing-v1", "version": version, "utc": datetime.now(timezone.utc).isoformat(),
            "seed": 20261002, "cases": cases, "all_passed": all(case["passed"] for case in cases),
            "reference": "matrix exponential of wet equal-bed graph diffusion, constant surface rainfall and optional engineered boundary loss",
            "substeps_s": list(substeps), "full_solver_exercised": True, "hydraulic_ready": False,
            "implementation_sha256": {name: file_sha256(ROOT / name) for name in code_names},
            "auditor_sha256": file_sha256(__file__),
            "limitations": "Full wet-state forcing/transport and boundary verification only. No soil saturation transitions, wet/dry events or nonlinear saddle transitions; not whole TD convergence."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", choices=("v5", "v6", "v7"), default="v5")
    arguments = parser.parse_args()
    report = audit(arguments.version)
    publish_bytes(arguments.output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode())
    print(json.dumps({"all_passed": report["all_passed"], "max_fine_error_m": max(case["timestep_errors_m"][-1] for case in report["cases"]),
                      "min_error_ratio": min(min(case["refinement_error_ratios"]) for case in report["cases"])}))
    if not report["all_passed"]:
        raise AssertionError("manufactured forcing audit failed")
