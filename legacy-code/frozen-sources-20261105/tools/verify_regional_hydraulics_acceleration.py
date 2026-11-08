"""Real-state differential hot-path performance gate, excluding JIT warmup."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from dataclasses import replace
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline import regional_surface_hydraulics as base
from terrain_pipeline import regional_surface_hydraulics_accelerated as accelerated
from terrain_pipeline.mountain_source_adapter import publish_bytes, file_sha256


def main():
    case = ROOT / "verification/regional-hydraulics/full-20261001T110401380014Z/uniform_heavy_half_cfl"
    packet_path = sorted(case.glob("interval-*.npz"))[-1]
    with np.load(case / "geometry.npz", allow_pickle=False) as archive:
        geometry = {"arrays": {key: archive[key] for key in archive.files}, "metadata": json.loads((case / "geometry.json").read_text())}
    with np.load(packet_path, allow_pickle=False) as archive:
        packet = {key: archive[key] for key in archive.files}
    arguments = (geometry, packet["depth_before_m"], packet["internal_q_before_m3_s"], packet["boundary_q_before_m3_s"],
        geometry["arrays"]["boundary_crest_m"], packet["forcing_volume_m3"] / 900., .5, base.SurfaceBudget())
    outputs = {}
    timings = {}
    for name, function in (("numpy", base.limited_inertial_fluxes), ("numba", accelerated.limited_inertial_fluxes)):
        outputs[name] = function(*arguments)
        start = time.perf_counter()
        for index in range(200):
            function(*arguments)
        timings[name] = time.perf_counter() - start
    errors = []
    for index in (0, 1):
        expected, actual = outputs["numpy"][index], outputs["numba"][index]
        if not np.allclose(actual, expected, rtol=2e-13, atol=1e-12):
            raise ValueError("accelerated real-state flux mismatch")
        errors.append(float(abs(actual-expected).max(initial=0)))
    report = {"packet": str(packet_path.relative_to(ROOT)), "packet_sha256": file_sha256(packet_path),
        "timing_200_calls_s": timings, "speedup": timings["numpy"] / timings["numba"],
        "max_flux_absolute_error_m3_s": errors, "reference_limiter": outputs["numpy"][2], "accelerated_limiter": outputs["numba"][2],
        "warmup_excluded": True, "fastmath": False,
        "hashes": {str(path.relative_to(ROOT)): file_sha256(path) for path in (ROOT / "terrain_pipeline/regional_surface_hydraulics.py", ROOT / "terrain_pipeline/regional_surface_hydraulics_accelerated.py", Path(__file__))}}
    output = ROOT / "verification/regional-hydraulics" / ("acceleration-probe-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir()
    publish_bytes(output / "predeclared.json", json.dumps({"scope": "full_grid_900s_from_saved_depth_zero_Q_not_resume",
        "budget": vars(replace(base.SurfaceBudget(), max_dt_s=15., inertial_cfl=.225, max_wall_s=300.)),
        "source_packet_sha256": report["packet_sha256"], "hashes": report["hashes"]}, indent=2).encode("ascii"))
    trajectories = {}
    for name, function in (("numpy", base.advance_inertial_surface), ("numba", accelerated.advance_accelerated_surface)):
        trajectories[name] = function(geometry, initial_depth_m=packet["depth_before_m"].reshape(256, 256).copy(),
            forcing_interval_s=900., intervals=1, forcing_provider=lambda index: (packet["forcing_volume_m3"] / 900.).reshape(256, 256),
            boundary_stage_provider=lambda index: geometry["arrays"]["boundary_crest_m"].copy(),
            source_identity=geometry["metadata"]["source_identity"], forcing_identity="saved_interval_constant_probe_not_resume",
            budget=replace(base.SurfaceBudget(), max_dt_s=15., inertial_cfl=.225, max_wall_s=300.))
    report["full_step_900s"] = {name: {"metadata": result["metadata"], "diagnostics": result["diagnostics"]} for name, result in trajectories.items()}
    report["trajectory_max_errors"] = {}
    for key in trajectories["numpy"]["arrays"]:
        expected, actual = trajectories["numpy"]["arrays"][key], trajectories["numba"]["arrays"][key]
        if expected.shape != actual.shape or not np.allclose(actual, expected, rtol=2e-10, atol=1e-8):
            raise ValueError("900s full-step trajectory mismatch: " + key)
        report["trajectory_max_errors"][key] = float(abs(actual-expected).max(initial=0))
    report["full_step_speedup"] = trajectories["numpy"]["metadata"]["wall_s"] / trajectories["numba"]["metadata"]["wall_s"]
    publish_bytes(output / "report.json", json.dumps(report, indent=2).encode("ascii"))
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
