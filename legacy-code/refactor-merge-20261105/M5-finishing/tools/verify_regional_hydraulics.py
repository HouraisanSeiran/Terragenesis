"""CPU-only full-region short performance gate before long hydraulic runs."""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.surface_hydraulics import SurfaceBudget, prepare_surface_geometry, advance_inertial_surface
from terrain_pipeline.common_infra import file_sha256, publish_bytes


RAW = ROOT / "verification/mountain-real-td/mountain-run-20261001T080705728662Z/primary-td-output.npz"
RAW_SHA = "e1dc646b990388af3bf284b614b10c2a834d0259429539d2a7d3d2cc844712ae"


def benchmark():
    if file_sha256(RAW) != RAW_SHA:
        raise ValueError("pinned primary TD raw hash mismatch")
    with np.load(RAW, allow_pickle=False) as archive:
        height = archive["elevation_m"].astype(np.float64)
    if height.shape != (256, 256):
        raise ValueError("full primary region required")
    output = ROOT / "verification/regional-hydraulics" / ("benchmark-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    geometry = prepare_surface_geometry(height, spacing_m=30., origin_m_xz=[-184320., 61440.], source_identity=RAW_SHA)
    budget = replace(SurfaceBudget(), max_wall_s=120., max_substeps=10000)
    report = {"schema": "regional-hydraulics-short-preflight-v1", "raw_sha256": RAW_SHA,
        "full_cells": 65536, "area_m2": 58982400., "budget": vars(budget), "cases": {},
        "source_hashes": {"terrain_pipeline/regional_surface_hydraulics.py": file_sha256(ROOT / "terrain_pipeline/regional_surface_hydraulics.py"),
                          "tools/verify_regional_hydraulics.py": file_sha256(Path(__file__))}}
    publish_bytes(output / "predeclared.json", json.dumps(report, indent=2).encode("ascii"))
    for name, depth in (("dry_zero_input", 0.), ("uniform_005m_closed", .05)):
        result = advance_inertial_surface(geometry, initial_depth_m=np.full(height.shape, depth),
            forcing_interval_s=900., intervals=1, forcing_provider=lambda index: np.zeros(height.shape),
            boundary_stage_provider=lambda index: np.zeros(1024), source_identity=RAW_SHA,
            forcing_identity="benchmark_no_rain_not_A_hydrology", budget=budget, snapshot_interval_s=900.)
        meta = result["metadata"]
        physical = meta["committed_time_s"]
        cost = meta["wall_s"] / max(physical, 1e-30)
        steps_rate = meta["substeps"] / max(physical, 1e-30)
        report["cases"][name] = {"metadata": meta, "diagnostics": result["diagnostics"],
            "linear_cost_projection_not_guarantee": {"24h_wall_s": cost * 86400, "72h_wall_s": cost * 259200,
                "24h_substeps": steps_rate * 86400, "72h_substeps": steps_rate * 259200},
            "max_depth_m": float(result["arrays"]["depth_m"].max()),
            "volume_balance_error_m3": meta["final_volume_m3"] - meta["initial_volume_m3"]}
        print(name, json.dumps(report["cases"][name]), flush=True)
    report["source_unchanged"] = all(file_sha256(ROOT / key) == value for key, value in report["source_hashes"].items())
    publish_bytes(output / "report.json", json.dumps(report, indent=2).encode("ascii"))
    print("BENCHMARK", output)


def forcing_benchmark():
    from terrain_pipeline.regional_surface_source import load_source
    from terrain_pipeline.climate_forcing import regional_load_forcing as load_forcing
    source_dir = ROOT / "verification/regional-source/run-20261001T095258008789Z"
    forcing_dir = ROOT / "verification/regional-forcing/run-20261001T095608600719Z"
    source_meta = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    handoff = json.loads((forcing_dir / "handoff-manifest.json").read_text(encoding="utf-8"))
    source = load_source(source_dir / "source.npz", expected_sha256=source_meta["source_sha256"])
    loaded = load_forcing(forcing_dir / "uniform_heavy", expected_manifest_sha256=handoff["cases"]["uniform_heavy"]["manifest_sha256"], source_identity=source["identity_sha256"])
    height = source["arrays"]["height_m"]
    geometry = prepare_surface_geometry(height, spacing_m=30., origin_m_xz=source["metadata"]["origin_m_xz"],
        source_identity=source["identity_sha256"], boundary_kind=np.ones(1024, np.int64))
    output = ROOT / "verification/regional-hydraulics" / ("forcing-benchmark-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    budget = replace(SurfaceBudget(), max_wall_s=120., max_substeps=10000)
    peak = int(np.asarray(loaded["metadata"]["ledger"]["runoff_m3"]).argmax())
    report = {"source_identity": source["identity_sha256"], "height_source_identity": source["metadata"]["height_source_identity"],
        "forcing_manifest_sha256": handoff["cases"]["uniform_heavy"]["manifest_sha256"], "budget": vars(budget),
        "scope": "full_grid_900s_performance_probes_not_continuous_storm", "cases": {}}
    publish_bytes(output / "predeclared.json", json.dumps(report, indent=2).encode("ascii"))
    probes = [(peak, cap) for cap in (30., 3., .3)] if "--drag-sensitivity" in sys.argv else [(0, 30.), (peak, 30.)]
    report["probes"] = probes
    report["discretization"] = "local_inertia_analytic_implicit_new_q_Manning_drag"
    publish_bytes(output / "probe-declaration.json", json.dumps(report, indent=2).encode("ascii"))
    for index, cap in probes:
        forcing = loaded["runoff_volume_m3"][index].copy() / 900.
        result = advance_inertial_surface(geometry, initial_depth_m=np.zeros(height.shape), forcing_interval_s=900., intervals=1,
            forcing_provider=lambda step: forcing, boundary_stage_provider=lambda step: np.zeros(1024),
            source_identity=source["identity_sha256"], forcing_identity=report["forcing_manifest_sha256"], budget=replace(budget, max_dt_s=cap))
        key = str(index) + "_dt" + str(cap)
        report["cases"][key] = {"metadata": result["metadata"], "diagnostics": result["diagnostics"],
            "projection_24h_wall_s": result["metadata"]["wall_s"] * 86400 / max(result["metadata"]["committed_time_s"], 1e-30)}
        np.save(output / (key + "-final-depth.npy"), result["arrays"]["depth_m"][-1], allow_pickle=False)
        print("A_FORCING", key, json.dumps(report["cases"][key]), flush=True)
    loaded["runoff_volume_m3"]._mmap.close()
    publish_bytes(output / "report.json", json.dumps(report, indent=2).encode("ascii"))
    print("FORCING_BENCHMARK", output)


def continuous_probe():
    from terrain_pipeline.regional_surface_source import load_source
    from terrain_pipeline.climate_forcing import regional_load_forcing as load_forcing
    source_dir = ROOT / "verification/regional-source/run-20261001T095258008789Z"
    forcing_dir = ROOT / "verification/regional-forcing/run-20261001T095608600719Z"
    source_meta = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    handoff = json.loads((forcing_dir / "handoff-manifest.json").read_text(encoding="utf-8"))
    source = load_source(source_dir / "source.npz", expected_sha256=source_meta["source_sha256"])
    forcing_sha = handoff["cases"]["uniform_heavy"]["manifest_sha256"]
    loaded = load_forcing(forcing_dir / "uniform_heavy", expected_manifest_sha256=forcing_sha, source_identity=source["identity_sha256"])
    height = source["arrays"]["height_m"]
    geometry = prepare_surface_geometry(height, spacing_m=30., origin_m_xz=source["metadata"]["origin_m_xz"],
        source_identity=source["identity_sha256"], boundary_kind=np.ones(1024, np.int64))
    output = ROOT / "verification/regional-hydraulics" / ("continuous-probe-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    budget = SurfaceBudget()
    intervals = 28
    declaration = {"model": "local_inertia_analytic_implicit_new_q_drag", "budget": vars(budget),
        "intervals": intervals, "duration_s": intervals * 900, "source_identity": source["identity_sha256"],
        "height_source_identity": source["metadata"]["height_source_identity"], "forcing_manifest_sha256": forcing_sha,
        "source_hashes": {str(path.relative_to(ROOT)): file_sha256(path) for path in
            (ROOT / "terrain_pipeline/regional_surface_hydraulics.py", Path(__file__))}}
    publish_bytes(output / "predeclared.json", json.dumps(declaration, indent=2).encode("ascii"))
    def observe(certificate):
        index = certificate["interval"]
        print("INTERVAL", index, certificate["time_end_s"], float(certificate["depth_after_m"].max()), flush=True)
    result = advance_inertial_surface(geometry, initial_depth_m=np.zeros(height.shape),
        forcing_interval_s=900., intervals=intervals, forcing_provider=lambda index: loaded["runoff_volume_m3"][index].astype(np.float64) / 900.,
        boundary_stage_provider=lambda index: np.zeros(1024), source_identity=source["identity_sha256"],
        forcing_identity=forcing_sha, budget=budget, interval_observer=observe)
    with (output / "states.npz").open("xb") as stream:
        np.savez_compressed(stream, **result["arrays"])
    declaration["result"] = {"metadata": result["metadata"], "diagnostics": result["diagnostics"]}
    declaration["source_unchanged"] = all(file_sha256(ROOT / key) == value for key, value in declaration["source_hashes"].items())
    publish_bytes(output / "report.json", json.dumps(declaration, indent=2).encode("ascii"))
    loaded["runoff_volume_m3"]._mmap.close()
    print("CONTINUOUS_PROBE", output, json.dumps(declaration["result"]), flush=True)


if __name__ == "__main__":
    if "--continuous-probe" in sys.argv:
        continuous_probe()
    elif "--forcing-benchmark" in sys.argv:
        forcing_benchmark()
    else:
        benchmark()
