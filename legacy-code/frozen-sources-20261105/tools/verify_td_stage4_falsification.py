"""Bounded multi-source falsification and actual component ablations."""

import argparse
import ctypes
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_naturalness_audit import compare_frozen_samples
from tools.verify_td_natural_river_baseline import boundary_for, diagnose, grid_reference_conditions_match


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "verification/td-natural-river-stages/stage1-reference-20261011-04.json"
BUDGET = {"worker_timeout_seconds": 180, "peak_rss_limit_bytes": 1073741824,
          "max_terrain_cells": 16384, "max_channel_nodes": 16,
          "max_physical_seconds": 900, "water_scaled_residual": 1e-8,
          "naturalness_intervals": "unchanged_stage1_reference"}


def peak_rss_bytes():
    if os.name != "nt":
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    process = ctypes.windll.kernel32.GetCurrentProcess
    process.restype = ctypes.c_void_p
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(process()), ctypes.byref(counters), counters.cb):
        raise OSError("cannot measure Windows process working set")
    return int(counters.PeakWorkingSetSize)


def terrain_matrix(output):
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    inventory_path = ROOT / "verification/td-natural-river-stages/reference-baseline-02/td-source-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    holdout_dir = ROOT / "verification/height-budget-v5/run-20260929T103819083596Z/holdout"
    holdout_report = json.loads((holdout_dir / "report.json").read_text(encoding="utf-8"))
    record = next(entry for entry in holdout_report["samples"] if entry["raw_npz"] == "seed20261004-x0-z0.npz")
    holdout_path = holdout_dir / record["raw_npz"]
    with np.load(holdout_path, allow_pickle=False) as archive:
        holdout_meta = json.loads(str(archive["metadata"].item()))
        holdout_config = json.loads(str(archive["generation_config"].item()))
    inventory = inventory[:2] + [{"path": str(holdout_path), "sha256": record["raw_sha256"],
                                 "metadata": holdout_meta, "generation_config": holdout_config}]
    cases = []
    for pin in inventory:
        path = Path(pin["path"])
        if file_sha256(path) != pin["sha256"]:
            raise ValueError("TD source differs from inventory")
        with np.load(path, allow_pickle=False) as archive:
            full = archive["elevation"].astype(np.float64)
        for row, col in ((0, 0), (192, 192)):
            for stride, side in ((1, 96), (3, 32), (3, 96), (1, 128)):
                window = full[row:row + side * stride:stride, col:col + side * stride:stride]
                spacing = 30. * stride
                terrain = TerrainGrid(window, np.isfinite(window), col * 30., row * 30., spacing, spacing,
                                      "generated_terrain", pin["metadata"]["identity"], pin["sha256"],
                                      generation_seed=int(pin["metadata"]["seed"]), source_path=str(path),
                                      condition_summary=identity({}, pin["generation_config"]))
                graph, stats = diagnose(terrain, boundary_for(terrain, "unknown_boundary"))
                relief = float(np.ptp(window))
                case = {"seed": terrain.generation_seed, "window_origin_zx": [row, col],
                        "sample_stride": stride, "grid_shape_zx": [side, side],
                        "spacing_m": spacing, "physical_extent_m_xz": [side * spacing] * 2,
                        "support_area_m2": stats["valid_area_m2"],
                        "source_sha256": pin["sha256"], "graph_identity_sha256": graph.identity_sha256,
                        "terrain_conditions": {"climate": "unknown", "relief_m": relief,
                                               "classification": "measured_relief_only_not_biome_or_geology"},
                        "scale_semantics": "same_extent_96native_vs32_subsample;128native_is_separate_finite_domain",
                        "statistics": stats,
                        "reference_comparison": compare_frozen_samples(stats["geometry_observations"], reference,
                                                                         conditions_match=grid_reference_conditions_match(reference, terrain)),
                        "reference_scope": "same_spacing_diagnostic_only;extent_and_climate_terrain_mismatch_not_natural_certification"}
                cases.append(case)
    return {"cases": cases, "reference_sha256": file_sha256(REFERENCE),
            "inventory_sha256": file_sha256(inventory_path)}


def lake_ablation(output):
    from tools.verify_td_water_cycle import select_domain, budget
    from terrain_pipeline.surface_rivers.metric_runoff import runoff_from_forcing
    from terrain_pipeline.surface_rivers.metric_contracts import RainfallForcing
    from terrain_pipeline.surface_rivers.metric_channel_state import ChannelNetwork, ChannelConfig, ChannelForcing
    from terrain_pipeline.surface_rivers.metric_channel_solver import solve_channel
    from terrain_pipeline.surface_rivers.metric_channel_product import make_channel_product, save_channel_product, load_channel_product
    from terrain_pipeline.surface_rivers.metric_lake_storage import LakeStorage, LakeOutlet
    from terrain_pipeline.surface_rivers.metric_boundary_coupling import BoundarySeries, CoupledForcing, solve_coupled
    from terrain_pipeline.surface_rivers.metric_coupled_product import make_coupled_product, save_coupled_product, load_coupled_product
    source, terrain, graph, owner, upstream, terminal, raw = select_domain()
    active = owner.reshape(terrain.valid_mask.shape) >= 0
    runoff_terrain = replace(terrain, valid_mask=active)
    times = np.array([0., 300., 600., 900.])
    heights = terrain.elevation_m.ravel()
    distance = float(np.linalg.norm(np.subtract(terrain.world_xz(int(upstream)), terrain.world_xz(int(terminal)))))
    slope = (heights[upstream] - heights[terminal]) / distance
    network = ChannelNetwork(np.array([-1]), np.array([distance]), np.array([5.]), np.array([heights[upstream]]),
                             np.array([slope]), np.array([.05]), np.array([100.]), np.array(["open_outflow"]),
                             terrain.identity_sha256, "same explicit section as stage2 finite TD domain", "n=.05 assumed")
    lake = LakeStorage(np.array([terminal]), np.array([heights[terminal]]), np.array([terrain.cell_area_m2]),
                       terminal, float(heights[terminal] + 100.), terrain.identity_sha256, "same native terminal support as stage2")
    boundary = BoundarySeries(np.empty(0, np.int64), np.empty(0, "U24"), np.empty(0, bool), times,
                              np.empty((3, 0)), np.empty((3, 0)), np.empty(0), source["identity_sha256"])
    cases = []
    for weather, rates in (("dry", [0., 0., 0.]), ("rain", [10., 10., 0.]), ("storm", [0., 120., 120.])):
        rain = np.asarray(rates)[:, None, None] * active[None]
        rf = RainfallForcing(times, rain, weather, terrain.source_sha256)
        native = runoff_from_forcing(runoff_terrain, rf)
        ids = native["valid_cell_ids"]
        q = native["native_result"]["local_q_m3_s"]
        cq = q[:, owner[ids] == 0].sum(axis=1)[:, None]
        lq = q[:, owner[ids] == 1].sum(axis=1)[:, None]
        paired = {}
        for policy in ("closed", "open"):
            outlets = () if policy == "closed" else (LakeOutlet(0, -1, float(heights[terminal] + .001), .5, "explicit one-way spill"),)
            forcing = CoupledForcing(times, cq, lq, rf.identity_sha256)
            result = solve_coupled(network, (lake,), outlets, np.array([0]), forcing, boundary,
                                   config=ChannelConfig(max_dt_seconds=15., max_steps=10000))
            product = make_coupled_product(network, (lake,), outlets, np.array([0]), forcing, boundary, result)
            saved_path = output / (weather + "-lake-on-" + policy + ".npz")
            save_coupled_product(saved_path, product)
            product = load_coupled_product(saved_path, expected_sha256=file_sha256(saved_path), expected_identity=product["identity_sha256"])
            paired["lake_on_" + policy] = {"status": result["metadata"]["status"], "ledger": budget(product),
                                          "identity_sha256": product["identity_sha256"], "path": str(saved_path),
                                          "sha256": file_sha256(saved_path), "cold_read_verified": True}
        # Removing lake storage and port is a model ablation, not a renamed coefficient.
        # Its native terminal area is retained as a rectangular channel control volume.
        off_network = ChannelNetwork(np.array([1, -1]), np.array([distance, terrain.cell_area_m2 / 5.]),
            np.full(2, 5.), np.array([heights[upstream], heights[terminal]]), np.array([slope, slope]),
            np.full(2, .05), np.full(2, 100.), np.array(["interior", "open_outflow"]), terrain.identity_sha256,
            "lake removed; terminal native area retained as channel inventory; no new bed interpretation", "n=.05 assumed",
            receiver_distance_m=np.array([distance, 0.]))
        off_forcing = ChannelForcing(times, np.hstack((cq, lq)), rf.identity_sha256)
        off = make_channel_product(off_network, off_forcing,
            solve_channel(off_network, off_forcing, config=ChannelConfig(max_dt_seconds=15., max_steps=10000)))
        saved_path = output / (weather + "-lake-off-open.npz")
        save_channel_product(saved_path, off)
        off = load_channel_product(saved_path, expected_sha256=file_sha256(saved_path), expected_identity=off["identity_sha256"])
        a = off["arrays"]
        final = float(a["trace_volume_m3"][-1].sum())
        external = float(a["trace_boundary_outflow_volume_m3"].sum())
        local = float((np.diff(a["trace_time_seconds"])[:, None] * a["trace_local_q_m3_s"]).sum())
        if off["metadata"]["status"] != "complete" or abs(local - external - final) > 1e-8 * max(1., local):
            raise ValueError("lake-off failed or unclosed native release inventory")
        paired["lake_off_open"] = {"status": off["metadata"]["status"],
            "path": str(saved_path), "sha256": file_sha256(saved_path), "identity_sha256": off["identity_sha256"],
            "cold_read_verified": True, "ledger": {
            "local_m3": local, "external_m3": external, "final_m3": final, "residual_m3": local - external - final}}
        native_budget = native["ledger"]["totals_m3"]
        for variant in paired.values():
            ledger = variant["ledger"]
            residual = (native_budget["rain_volume_m3"] - native_budget["et_volume_m3"]
                        - native_budget["storage_change_m3"] - ledger["external_m3"] - ledger["final_m3"])
            variant["native_combined_residual_m3"] = residual
            if abs(residual) > 1e-8 * max(1., native_budget["rain_volume_m3"]):
                raise ValueError("ablation failed native rain/runoff/channel/lake inventory linkage")
        cases.append({"weather": weather, "forcing_identity_sha256": rf.identity_sha256,
                      "native_runoff_budget": native["ledger"]["totals_m3"], "cases": paired,
                      "lake_removal_effect_m3": final - paired["lake_on_open"]["ledger"]["final_m3"],
                      "outlet_disabled_effect_m3": paired["lake_on_closed"]["ledger"]["final_m3"] - paired["lake_on_open"]["ledger"]["final_m3"]})
    from terrain_pipeline.surface_rivers.metric_water_cycle import load_water_cycle
    previous_dir = ROOT / "verification/td-natural-river-stages/water-cycle-20261011-final-bound"
    previous_report = json.loads((previous_dir / "report.json").read_text(encoding="utf-8"))
    previous = []
    for weather in ("dry", "rain", "storm"):
        pin = previous_report["artifacts"][weather + "-failed-prefix"]
        bundle = load_water_cycle(previous_dir / pin["path"], expected_sha256=pin["sha256"])
        previous.append({"case": weather + "-failed-prefix", "path": str(previous_dir / pin["path"]),
                         "sha256": pin["sha256"], "identity_sha256": bundle["identity_sha256"],
                         "cold_read_verified": True, "ledger": previous_report["cases"][weather + "-failed-prefix"]})
    return {"source_sha256": terrain.source_sha256, "cases": cases, "stage2_failed_prefixes": previous,
            "scope": "actual component removal; results not assumed worse; native inventories unchanged"}


def morphology_ablation(output):
    from terrain_pipeline.surface_rivers.metric_morphology_coupling import load_morphology_coupling, _unpack
    from terrain_pipeline.surface_rivers.metric_channel_state import ChannelNetwork, ChannelForcing, ChannelConfig
    from terrain_pipeline.surface_rivers.metric_channel_solver import solve_channel
    from terrain_pipeline.surface_rivers.metric_channel_product import make_channel_product, save_channel_product, load_channel_product, NETWORK_FIELDS
    directory = ROOT / "verification/td-natural-river-stages/water-morphology-20261011-fixed"
    report = json.loads((directory / "acceptance.json").read_text(encoding="utf-8"))
    pin = report["artifacts"]["td-feedback-native-intervals"]
    coupled = load_morphology_coupling(directory / pin["path"], expected_sha256=pin["sha256"])
    a, m = coupled["arrays"], coupled["metadata"]
    geometry = _unpack(a, m, "geometry")
    ga = geometry["arrays"]
    from tools.verify_td_river_sediment import sample_saved_mesh
    bed = sample_saved_mesh(geometry, ga["node_xz_m"])
    receiver = ga["receiver"]
    distance = np.zeros(len(receiver))
    for node, target in enumerate(receiver):
        if target >= 0:
            distance[node] = np.linalg.norm(ga["node_xz_m"][node] - ga["node_xz_m"][target])
    # The feedback product freezes original forcing in its packed forcing parent.
    first_water = _unpack(a, m, "water_0")
    wa, wm = first_water["arrays"], first_water["metadata"]
    network_values = {key: wa["network_" + key] for key in NETWORK_FIELDS if "network_" + key in wa}
    network_values.setdefault("receiver_distance_m", distance)
    network = ChannelNetwork(**network_values, source_identity_sha256=wm["network_source_identity_sha256"],
                             section_source=wm["section_source"], roughness_source=wm["roughness_source"])
    forcing = ChannelForcing(a["forcing_time_seconds"], a["forcing_local_q_m3_s"],
                             first_water["metadata"]["forcing_source_identity_sha256"])
    off_result = solve_channel(network, forcing, initial_volume_m3=a["water_volume_m3"][0].copy(),
                               config=ChannelConfig(**m["channel_config"]))
    off = make_channel_product(network, forcing, off_result)
    off_path = output / "feedback-off-channel.npz"
    save_channel_product(off_path, off)
    off = load_channel_product(off_path, expected_sha256=file_sha256(off_path), expected_identity=off["identity_sha256"])
    from terrain_pipeline.surface_rivers.metric_resolution_exchange import run_resolution_comparison, audit_comparison
    from terrain_pipeline.surface_rivers.metric_sediment import (MaterialParameters, SedimentConfig, SedimentDomain,
        SedimentForcing, DOMAIN_FIELDS, solve_sediment, save_sediment, load_sediment)
    sediment_parent = _unpack(a, m, "sediment_0")
    sa, sm = sediment_parent["arrays"], sediment_parent["metadata"]
    domain = SedimentDomain(**{key: sa["domain_" + key] for key in DOMAIN_FIELDS},
                           geometry_identity_sha256=sm["geometry_identity_sha256"], provenance=sm["domain_provenance"])
    oa = off["arrays"]
    interval = np.minimum(np.searchsorted(a["forcing_time_seconds"], oa["trace_time_seconds"][:-1], side="right") - 1,
                          len(a["forcing_external_solid_m3_s"]) - 1)
    frozen_forcing = SedimentForcing(oa["trace_time_seconds"].copy(), oa["trace_volume_m3"][:-1].copy(),
        oa["trace_depth_m"][:-1].copy(), oa["trace_outflow_q_m3_s"].copy(),
        np.broadcast_to(network.bed_slope, oa["trace_local_q_m3_s"].shape).copy(),
        a["forcing_external_solid_m3_s"][interval].copy(), off["identity_sha256"], domain.geometry_identity_sha256,
        "same material/source/initial solids; frozen water without bed-to-water feedback")
    frozen_solid = solve_sediment(domain, frozen_forcing, MaterialParameters(**m["material"]),
        initial_mobile_solid_m3=a["mobile_solid_m3"][0].copy(), config=SedimentConfig(**m["sediment_config"]))
    solid_path = output / "feedback-off-sediment.npz"
    save_sediment(solid_path, frozen_solid)
    frozen_solid = load_sediment(solid_path, expected_sha256=file_sha256(solid_path))
    counts = np.ones(len(receiver), np.int64)
    counts[len(receiver) // 2] = 2
    comparison_path = output / "resolution" / "comparison.json"
    resolution = run_resolution_comparison(network, forcing, local_counts=counts,
        output_path=comparison_path, source_manifest={"feedback_parent_sha256": pin["sha256"]},
        config=ChannelConfig(max_dt_seconds=.5, max_steps=5000),
        sediment_config=SedimentConfig(max_dt_seconds=.5, max_steps=5000),
        material=MaterialParameters(settling_velocity_m_s=1e-6, provenance="stage4 existing homogeneous refinement scenario"))
    resolution_audit = audit_comparison(comparison_path)
    return {"parent_sha256": pin["sha256"], "feedback_on": report["cases"]["td-feedback-native-intervals"],
            "feedback_off": {"status": off["metadata"]["status"], "final_bed_m": bed.tolist(),
                             "path": str(off_path), "sha256": file_sha256(off_path), "cold_read_verified": True,
                             "final_water_volume_m3": off["arrays"]["trace_volume_m3"][-1].tolist()},
            "bed_feedback_effect_m": (a["node_bed_m"][-1] - bed).tolist(),
            "water_feedback_effect_m3": (a["water_volume_m3"][-1] - off["arrays"]["trace_volume_m3"][-1]).tolist(),
            "feedback_off_sediment": {"path": str(solid_path), "sha256": file_sha256(solid_path),
                "status": frozen_solid["metadata"]["status"], "cold_read_verified": True,
                "exported_solid_m3": float(frozen_solid["arrays"]["step_exported_solid_m3"].sum()),
                "max_solid_residual_m3": float(np.abs(frozen_solid["arrays"]["step_balance_residual_m3"]).max()),
                "bed_evolution_without_hydraulic_feedback_m": (frozen_solid["arrays"]["trace_bed_elevation_m"][-1] - bed).tolist()},
            "solid_export_feedback_effect_m3": report["cases"]["td-feedback-native-intervals"]["solid_export_m3"] - float(frozen_solid["arrays"]["step_exported_solid_m3"].sum()),
            "local_refinement_on_off_uniform": resolution,
            "resolution_cold_audit": resolution_audit,
            "scope": "feedback omitted by frozen-bed channel solve; not zero erosion parameter"}


def worker(name, output):
    started = time.perf_counter()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    functions = {"terrain": terrain_matrix, "lake": lake_ablation, "morphology": morphology_ablation}
    try:
        result = functions[name](output)
        result.update(status="completed", elapsed_seconds=time.perf_counter() - started,
                      peak_rss_bytes=peak_rss_bytes())
    except Exception as error:
        result = {"status": "failed", "reason": type(error).__name__ + ": " + str(error),
                  "elapsed_seconds": time.perf_counter() - started, "peak_rss_bytes": peak_rss_bytes()}
    (output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")


def prepare(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    config = {"schema": "td-stage4-frozen-plan-v1", "budget": BUDGET,
              "workers": ["terrain", "lake", "morphology"], "reference_sha256": file_sha256(REFERENCE),
              "terrain_cases": {"seeds": [20260930, 20260931, 20261004], "window_origins_zx": [[0, 0], [192, 192]],
                                "stride_side": [[1, 96], [3, 32], [3, 96], [1, 128]],
                                "boundary_policy": "unknown_boundary", "held_out_seed": 20261004},
              "process_cases": {"lake_weather_mm_h": [[0, 0, 0], [10, 10, 0], [0, 120, 120]],
                                "lake_variants": ["lake_on_closed", "lake_on_open", "lake_off_open"],
                                "morphology_variants": ["coupled_feedback_parent", "same_physical_network_frozen_bed"],
                                "resolution": ["native", "uniform_2", "local_one_reach_2"]},
              "input_pins": {str(path.relative_to(ROOT)): file_sha256(path) for path in (
                  ROOT / "verification/td-natural-river-stages/reference-baseline-02/td-source-inventory.json",
                  ROOT / "verification/height-budget-v5/run-20260929T103819083596Z/holdout/report.json",
                  ROOT / "verification/td-natural-river-stages/water-morphology-20261011-fixed/acceptance.json",
                  ROOT / "verification/td-natural-river-stages/water-cycle-20261011-final-bound/report.json",
                  ROOT / "verification/td-natural-river-stages/baseline-20261011-06/report.json")},
              "code_sha256": file_sha256(__file__), "publishable": False}
    (output / "frozen-plan.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    cases = {}
    for name in config["workers"]:
        case_dir = output / name
        try:
            completed = subprocess.run([sys.executable, "-B", "-m", "tools.verify_td_stage4_falsification", "--worker", name,
                                        "--output", str(case_dir)], cwd=ROOT, timeout=BUDGET["worker_timeout_seconds"],
                                       capture_output=True, text=True)
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr[-2000:])
            cases[name] = json.loads((case_dir / "result.json").read_text(encoding="utf-8"))
            cases[name]["resource_pass"] = cases[name]["peak_rss_bytes"] <= BUDGET["peak_rss_limit_bytes"]
        except (subprocess.TimeoutExpired, RuntimeError) as error:
            cases[name] = {"status": "failed", "reason": str(error), "resource_pass": False}
    report = {"schema": "td-stage4-falsification-v1", "status": "incomplete_tool_failure" if any(case["status"] == "failed" for case in cases.values()) else "completed_bounded_with_observed_naturalness_failures",
              "frozen_plan_sha256": file_sha256(output / "frozen-plan.json"), "cases": cases,
              "natural_credible": False, "publishable": False,
              "coverage": "fixed seeds/regions/bounded domains/actual component ablations",
              "seam_evidence": {"path": "verification/td-natural-river-stages/baseline-20261011-06/report.json",
                                "scope": "native shared strips exact match and 1m shifted failure; not hydrologic seam certification"},
              "uncovered": ["2D_AMR", "climate_matched_naturalness", "certified_sea_outlets"]}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--worker", choices=("terrain", "lake", "morphology"))
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.output)
    else:
        result = prepare(args.output)
        print(json.dumps({"status": result["status"], "cases": {key: value["status"] for key, value in result["cases"].items()}}))
