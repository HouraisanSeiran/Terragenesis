"""Independent execution comparisons against unchanged v8 on bounded small fixtures."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, identity, publish_bytes
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_storage import advance_hour_compensated as advance_hour
from terrain_pipeline.basin_storage import COMPILED_HOUR_PROFILE as PROFILE
from terrain_pipeline.basin_storage import continuation_simulate as simulate_basin_storage

STATES = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
ERRORS = ("error_depth", "error_soil", "error_fast", "error_slow")
LEDGERS = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3",
           "local_release_m3", "surface_et_m3", "internal_net_m3", "boundary_outflow_m3")
FLUXES = ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s",
          "routed_volume_m3", "wet_duration_s")


def compare(actual, expected, allowed):
    if actual.shape != expected.shape or not np.isfinite(actual).all():
        raise ValueError("compiled execution invalid array")
    difference = np.logical_xor(actual, expected).astype(float) if actual.dtype.kind == "b" else abs(actual - expected)
    return {"max_difference": float(difference.max(initial=0)),
            "bitwise_equal": bool(np.array_equal(actual, expected)),
            "passed": bool(np.all(difference <= allowed))}


def audit():
    generator = np.random.default_rng(20261002)
    runoff = RunoffParameters()
    runoff_array = np.array([runoff.infiltration_capacity_mm_h, runoff.soil_capacity_mm,
                            runoff.potential_et_mm_h, runoff.percolation_mm_h,
                            runoff.fast_tau_s, runoff.slow_tau_s])
    config = np.array([.6, 1e-9, .15])
    duration = 60.
    cases = []
    for case_id in range(12):
        bed = np.round(generator.uniform(0, 3, (3, 4)), 1)
        if case_id == 0:
            bed[:] = 0
        opened = np.zeros(bed.shape, dtype=bool)
        if case_id % 2:
            opened[0] = True
        hierarchy = build_basin_hierarchy(make_td_source(bed, spacing_m=30, open_boundary_mask=opened))
        topology = hierarchy["arrays"]
        initial = np.zeros(bed.shape) if case_id % 3 == 0 else generator.uniform(0, 2, bed.shape)
        rain = np.array([0., 10., 30., 0.])
        forcing_id = identity({"rain_mm_h": rain}, {"dt_s": duration})
        for step in (5., 2.5, 1.25):
            checkpoint = None
            optimized_state = np.vstack((initial.ravel(), np.full(bed.size, 30.), np.zeros(bed.size), np.zeros(bed.size)))
            errors = np.zeros_like(optimized_state)
            cumulative = None
            hours = []
            for frame in range(len(rain)):
                began = time.perf_counter()
                reference = simulate_basin_storage(hierarchy, rain[frame:frame + 1], dt_s=duration,
                    initial_depth_m=initial if checkpoint is None else None,
                    checkpoint=checkpoint, parameters={"substep_s": step},
                    forcing_identity=forcing_id, full_rain_mm_h=rain)
                reference_seconds = time.perf_counter() - began
                reference_arrays = reference["storage"]["arrays"]
                before = optimized_state[0].copy() + optimized_state[1:].sum(axis=0) / 1000
                began = time.perf_counter()
                optimized = advance_hour(optimized_state, errors, np.full(bed.size, rain[frame]),
                    bed.ravel(), topology["face_cells"], topology["boundary_cells"],
                    reference_arrays["boundary_width_m"], topology["receiver"], 30., step,
                    int(duration / step), runoff_array, config)
                compiled_seconds = time.perf_counter() - began
                optimized_state, errors = optimized[:2]
                checkpoint = reference["checkpoint"]
                comparisons = {}
                for index, name in enumerate(STATES):
                    scale = 1 if name == "depth_m" else .001
                    comparisons[name] = compare(optimized_state[index] * scale,
                                                reference_arrays[name][-1] * scale, 1e-12)
                    comparisons[ERRORS[index]] = compare(errors[index] * scale,
                                                checkpoint["arrays"][ERRORS[index]] * scale, 1e-12)
                for index, name in enumerate(LEDGERS):
                    expected = reference_arrays[name][0]
                    comparisons[name] = compare(optimized[2][index], expected, 1e-6 + 1e-10 * abs(expected))
                if cumulative is None:
                    cumulative = {name: np.zeros_like(optimized[index + 3]) for index, name in enumerate(FLUXES)}
                for index, name in enumerate(FLUXES):
                    allowed = 1e-8 if name.endswith("_s") else 1e-6 + 1e-10 * abs(reference_arrays[name])
                    comparisons[name] = compare(optimized[index + 3], reference_arrays[name], allowed)
                    cumulative[name] += optimized[index + 3]
                    expected = checkpoint["arrays"]["cumulative_" + name]
                    allowed = 1e-8 if name.endswith("_s") else 1e-6 + 1e-10 * abs(expected)
                    comparisons["cumulative_" + name] = compare(cumulative[name], expected, allowed)
                after = optimized_state[0] + optimized_state[1:].sum(axis=0) / 1000
                change = (after - before) * 900
                expected = reference_arrays["storage_change_m3"][0]
                comparisons["storage_change_m3"] = compare(change, expected, 1e-6 + 1e-10 * abs(expected))
                residual = optimized[2][0] + optimized[2][6] - optimized[2][3] - optimized[2][5] - optimized[2][7] - change
                expected = reference_arrays["balance_residual_m3"][0]
                comparisons["balance_residual_m3"] = compare(residual, expected, 1e-6 + 1e-10 * abs(expected))
                hours.append({"frame": frame, "reference_seconds": reference_seconds,
                              "compiled_seconds": compiled_seconds, "fields": comparisons,
                              "passed": all(value["passed"] for value in comparisons.values())})
            cases.append({"case_id": case_id, "step_s": step, "frames": hours,
                          "passed": all(value["passed"] for value in hours)})
    memory = psutil.Process().memory_info()
    resource = {"peak_rss_bytes": int(getattr(memory, "peak_wset", memory.rss)),
                "peak_private_bytes": getattr(memory, "peak_pagefile", None)}
    return {"schema": "td-independent-compiled-execution-v1", "profile": PROFILE,
            "scope": "12 tiny beds, three exact steps and four forcing intervals, complete continuation inventory and ledger comparisons",
            "cases": cases, "passed": all(value["passed"] for value in cases), "resource": resource,
            "kernel_sha256": file_sha256(ROOT / 'terrain_pipeline/basin_storage.py'),
            "auditor_sha256": file_sha256(__file__), "original_TD_verified": False,
            "hydraulic_ready": False, "publishable": False,
            "limitations": "Raw kernel controlled-input equivalence only; public validation, cold IO, physical timestep refinement and large domain are separate gates."}


if __name__ == "__main__":
    result = audit()
    output = ROOT / "verification/td-basin-generation" / ("independent-compiled-execution-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({"output": str(output), "passed": result["passed"], "cases": len(result["cases"]), "resource": result["resource"]}))
    if not result["passed"]:
        raise SystemExit(1)
