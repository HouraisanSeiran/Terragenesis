"""Fixed finite-time 24h TD baseline runs; sequential CPU-only publication."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy, load_basin_hierarchy
from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256, make_td_source
from terrain_pipeline.td_basin_storage import load_basin_storage, save_basin_storage, simulate_basin_storage

HIERARCHY = ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"
HIERARCHY_SHA256 = "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422"
HIERARCHY_IDENTITY = "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"


def write_json(path, record):
    publish_bytes(path, json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))


def summary(result):
    arrays, metadata = result["arrays"], result["metadata"]
    area = metadata["spacing_m"] ** 2
    storage = area * (arrays["depth_m"] + sum(arrays[key] for key in ("soil_mm", "fast_mm", "slow_mm")) / 1000)
    return {"identity_sha256": result["identity_sha256"], "metadata": metadata,
        "rain_m3": float(arrays["rain_volume_m3"].sum()),
        "lake_rain_m3": float(arrays["lake_rain_m3"].sum()), "land_rain_m3": float(arrays["land_rain_m3"].sum()),
        "initial_total_water_m3": float(storage[0].sum()), "final_total_water_m3": float(storage[-1].sum()),
        "final_surface_m3": float(arrays["depth_m"][-1].sum() * area),
        "soil_et_m3": float(arrays["soil_et_m3"].sum()), "surface_et_m3": float(arrays["surface_et_m3"].sum()),
        "boundary_export_m3": float(arrays["boundary_outflow_m3"].sum()),
        "face_forward_m3": float(arrays["face_forward_m3"].sum()), "face_reverse_m3": float(arrays["face_reverse_m3"].sum()),
        "receiver_positive_volume_m3": float(arrays["routed_volume_m3"].sum()),
        "active_receiver_cells": int((arrays["routed_volume_m3"] > 0).sum()),
        "active_forward_faces": int((arrays["face_forward_m3"] > 0).sum()),
        "active_reverse_faces": int((arrays["face_reverse_m3"] > 0).sum()),
        "max_final_depth_m": float(arrays["depth_m"][-1].max()),
        "wet_pool_counts": arrays["wet_pool_count"].tolist(),
        "step_total_rain_m3": arrays["rain_volume_m3"].sum(axis=1).tolist(),
        "step_export_m3": arrays["boundary_outflow_m3"].sum(axis=1).tolist(),
        "step_max_depth_m": arrays["depth_m"].max(axis=1).tolist(),
        "step_min_depth_m": arrays["depth_m"].min(axis=1).tolist(),
        "negative_directional_volume_count": int((arrays["face_forward_m3"] < 0).sum() + (arrays["face_reverse_m3"] < 0).sum()),
        "saved_array_bytes": sum(value.nbytes for value in arrays.values()),
        "limiter_active_count": arrays["limiter_active_count"].tolist() if "limiter_active_count" in arrays else None,
        "donor_limited_count": arrays["donor_limited_count"].tolist() if "donor_limited_count" in arrays else None,
        "activity_caveat": "positive float64 flux including machine-small flows counts active half-sweep; no hidden flux cutoff",
        "max_cell_residual_m3": float(abs(arrays["balance_residual_m3"]).max()),
        "step_total_residual_m3": arrays["balance_residual_m3"].sum(axis=1).tolist()}


def verify_sensitivity(destination, *, v2=False, sensitivity_steps=(60, 30, 15)):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    hierarchy = load_basin_hierarchy(HIERARCHY, expected_sha256=HIERARCHY_SHA256, expected_identity=HIERARCHY_IDENTITY)
    solver = simulate_basin_storage
    if v2:
        from terrain_pipeline.td_basin_storage_implicit import simulate_basin_storage as solver
    arrays = hierarchy["arrays"]
    parent = arrays["node_parent"]
    candidates = np.flatnonzero((arrays["node_cell_count"] >= 100) & (arrays["node_cell_count"] <= 500)
        & ~arrays["node_unknown_contact"] & ~arrays["node_open_boundary"] & np.isfinite(arrays["node_upper_m"]))
    if not len(candidates):
        raise ValueError("no complete covered representative subtree")
    node = int(candidates[len(candidates) // 2])
    descendant = np.zeros(len(parent), bool)
    descendant[node] = True
    for candidate in range(node - 1, -1, -1):
        if parent[candidate] >= 0:
            descendant[candidate] = descendant[parent[candidate]]
    mask = descendant[arrays["cell_owner"]]
    rows, columns = np.where(mask)
    row_start, row_stop = int(rows.min()), int(rows.max() + 1)
    column_start, column_stop = int(columns.min()), int(columns.max() + 1)
    window = np.s_[row_start:row_stop, column_start:column_stop]
    spacing = hierarchy["metadata"]["spacing_m"]
    origin = hierarchy["metadata"]["origin_m_xz"]
    source = make_td_source(arrays["height_m"][window], spacing_m=spacing,
        origin_m_xz=[origin[0] + column_start * spacing, origin[1] + row_start * spacing], valid_mask=mask[window],
        source_sha256=PRIMARY_SHA256)
    local = build_basin_hierarchy(source)
    write_json(destination / "sensitivity-inputs.json", {"source_hierarchy_sha256": HIERARCHY_SHA256,
        "selected_node": node, "subtree_cells": int(mask.sum()), "crop": [row_start, row_stop, column_start, column_stop],
        "boundary": "all source subtree cells retained; artificial sealed divide, no external contributing inflow",
        "sill_m": float(arrays["node_upper_m"][node]), "conductance_m_s": 0.6,
        "tests": "ordinary and strong 24h; no rerun full domain", "substeps_s": list(sensitivity_steps), "v2": v2,
        "declared_gates": {"head_max_difference_m": 0.001, "receiver_volume_relative_l1": 0.01},
        "code_sha256": {name: file_sha256(ROOT / name) for name in (
            "terrain_pipeline/td_basin_storage.py", "tools/verify_td_basin_storage.py")}})
    report = {"selected_node": node, "scenarios": {}, "full_domain_transient_converged": False,
        "morphology_flux_ready": False, "scope": "complete covered subtree; sealed boundary sensitivity only"}
    for scenario, rate in (("ordinary", 10), ("strong", 30)):
        rain = np.zeros(24)
        rain[:6] = rate
        snapshots = []
        records = []
        for substep in sensitivity_steps:
            print("sensitivity " + scenario + " " + str(substep), flush=True)
            result = solver(local, rain, parameters={"substep_s": substep})
            path = destination / (scenario + "-" + str(substep) + ".npz")
            save_basin_storage(path, result)
            values = result["arrays"]
            active = int(values["proposed_active_count"].sum())
            record = summary(result)
            record.update({"archive_sha256": file_sha256(path), "substep_s": substep,
                "limiter_active_fraction": float(values["limiter_active_count"].sum() / max(1, active)),
                "proposed_active_count": active, "donor_limited_count": int(values["donor_limited_count"].sum())})
            records.append(record)
            snapshots.append((values["depth_m"].copy(), values["routed_volume_m3"].copy(),
                values["face_forward_m3"].copy(), values["face_reverse_m3"].copy()))
            del result
        comparisons = []
        for index in (0, 1):
            coarse, fine = snapshots[index], snapshots[index + 1]
            head_error = float(abs(coarse[0] - fine[0]).max())
            volume_error = float(abs(coarse[1] - fine[1]).sum() / max(1e-12, fine[1].sum()))
            comparisons.append({"substeps_s": [records[index]["substep_s"], records[index + 1]["substep_s"]],
                "max_saved_depth_difference_m": head_error, "receiver_volume_relative_l1": volume_error,
                "forward_volume_relative_l1": float(abs(coarse[2] - fine[2]).sum() / max(1e-12, fine[2].sum())),
                "reverse_volume_relative_l1": float(abs(coarse[3] - fine[3]).sum() / max(1e-12, fine[3].sum())),
                "gate_passed": head_error <= 0.001 and volume_error <= 0.01})
        report["scenarios"][scenario] = {"runs": records, "comparisons": comparisons,
            "transient_converged": all(value["gate_passed"] for value in comparisons)}
    write_json(destination / "report.json", report)
    print(json.dumps({"output": str(destination), "selected_node": node,
        "comparisons": {key: value["comparisons"] for key, value in report["scenarios"].items()}}, ensure_ascii=False), flush=True)
    return report


def verify(destination, *, resume=False, resume_dry_sha256=None, resume_dry_identity=None, v2=False, v3=False, substep_s=60, refinement=False, scenarios=("dry", "wet", "ordinary", "strong")):
    destination = Path(destination)
    if destination.exists() and not resume:
        raise FileExistsError(destination)
    hierarchy = load_basin_hierarchy(HIERARCHY, expected_sha256=HIERARCHY_SHA256, expected_identity=HIERARCHY_IDENTITY)
    if sum(bool(value) for value in (v2, v3, refinement)) > 1:
        raise ValueError("storage solver versions are mutually exclusive")
    solver = simulate_basin_storage
    if v2:
        from terrain_pipeline.td_basin_storage_implicit import simulate_basin_storage as solver
    if refinement:
        from terrain_pipeline.td_basin_storage_refinement import simulate_basin_storage as solver
    if v3:
        from terrain_pipeline.td_basin_storage_v3 import simulate_basin_storage as solver
    bed = hierarchy["arrays"]["height_m"]
    source_before = file_sha256(PRIMARY_PATH)
    if source_before != PRIMARY_SHA256:
        raise ValueError("original TD hash changed")
    inputs_path = destination / ("resume-inputs.json" if resume else "run-inputs.json")
    inputs = {"hierarchy_path": str(HIERARCHY), "hierarchy_sha256": HIERARCHY_SHA256,
        "hierarchy_identity_sha256": HIERARCHY_IDENTITY, "source_sha256": source_before,
        "forcing": "24 hourly steps; ordinary first6 10mm/h; strong first6 30mm/h; rest zero",
        "parameters": "linear D4 threshold conductance; soil default except dry initial soil=0", "substep_s": substep_s,
        "v2": v2, "v3": v3, "refinement": refinement, "scenarios": list(scenarios),
        "wet_initial": "first merge subtree initialized to birth+0.00005m; dry soil; no rain",
        "memory_budget_bytes": 1024 ** 3,
        "code_sha256": {name: file_sha256(ROOT / name) for name in (
            "terrain_pipeline/td_basin_storage.py", "terrain_pipeline/td_basin_storage_implicit.py",
            "tests/test_td_basin_storage.py", "tools/verify_td_basin_storage.py")}}
    if v3:
        inputs["code_sha256"]["terrain_pipeline/td_basin_storage_v3.py"] = file_sha256(ROOT / "terrain_pipeline/td_basin_storage_v3.py")
    write_json(inputs_path, inputs)
    records = {}
    start = time.perf_counter()
    for scenario in scenarios:
        rain = np.zeros(24)
        if scenario in ("ordinary", "strong"):
            rain[:6] = 10 if scenario == "ordinary" else 30
        initial = np.zeros(bed.shape)
        if scenario == "wet":
            arrays = hierarchy["arrays"]
            parent = arrays["node_parent"]
            owner = arrays["cell_owner"].ravel()
            merged = np.flatnonzero(np.bincount(parent[parent >= 0], minlength=len(parent)) > 0)
            node = int(merged[0])
            membership = owner == node
            for candidate in range(node):
                ancestor = candidate
                while ancestor >= 0 and ancestor != node:
                    ancestor = int(parent[ancestor])
                if ancestor == node:
                    membership |= owner == candidate
            level = arrays["node_birth_m"][node] + 0.00005
            initial.ravel()[membership] = np.maximum(0, level - bed.ravel()[membership])
            write_json(destination / "wet-initial.json", {"merge_node": node, "level_m": float(level),
                "initial_surface_m3": float(initial.sum() * hierarchy["metadata"]["spacing_m"] ** 2),
                "purpose": "no-rain merged wet state recession/splitting; no soil water supply"})
        parameters = RunoffParameters(initial_soil_mm=0) if scenario in ("dry", "wet") else RunoffParameters()
        scenario_start = time.perf_counter()
        print("starting " + scenario, flush=True)
        path = destination / (scenario + ".npz")
        if resume and path.exists():
            if scenario != "dry" or resume_dry_sha256 is None or resume_dry_identity is None:
                raise ValueError("resume existing archive requires external dry pins; other partial runs not supported")
            result = load_basin_storage(path, expected_sha256=resume_dry_sha256, expected_identity=resume_dry_identity)
        else:
            result = solver(hierarchy, rain, initial_depth_m=initial, runoff_parameters=parameters,
                            parameters={"substep_s": substep_s})
            save_basin_storage(path, result)
        sha = file_sha256(path)
        loaded = load_basin_storage(path, expected_sha256=sha, expected_identity=result["identity_sha256"])
        record = summary(loaded)
        record.update({"archive_path": str(path), "archive_sha256": sha, "elapsed_s": time.perf_counter() - scenario_start})
        records[scenario] = record
        write_json(destination / (scenario + "-report.json"), record)
        print(scenario + " complete: " + json.dumps({key: record[key] for key in (
            "rain_m3", "final_surface_m3", "boundary_export_m3", "elapsed_s", "max_cell_residual_m3")}), flush=True)
        del result, loaded
    if file_sha256(PRIMARY_PATH) != source_before or file_sha256(HIERARCHY) != HIERARCHY_SHA256:
        raise ValueError("source/hierarchy modified during storage run")
    report = {"status": "53_finite_time_baseline_ready_for_independent_audit", "scenarios": records,
        "elapsed_s": time.perf_counter() - start, "original_bed_unchanged": True,
        "input_corrections": {"wet_initial_description": "birth+0.00005m level over first merge subtree, not 0.2m; wet-initial.json authoritative",
            "flux_law": "linear conductance0.6m/s; supersedes early delivery weir draft before first main run",
            "linear_reason": "linear near-sill exchange relaxes exponentially with explicit bounded timescale; uncalibrated alternative, not numerical proof of physical accuracy",
            "resume_reason": "dry computed and saved; initial cold load rejected old128MiB archive budget; new storage256MiB loader/header policy only"},
        "limitations": ["linear conductance uncalibrated; substep/operator splitting influence transient timing",
            "cell heads can differ inside connected wet pools; not instantaneous FSM or uniform-level reservoir solver",
            "no momentum/dynamic-wave solution or calibrated channel propagation",
            "D4 static receiver volume includes only measured positive exchange toward that receiver",
            "reverse/other saddle exchange and durations retained per face for separate morphology path use",
            "wet pool connectivity uses 1e-9m sill threshold and is diagnostic", "natural outlets unverified"]}
    write_json(destination / "report.json", report)
    print(json.dumps({"output": str(destination), "elapsed_s": report["elapsed_s"]}, ensure_ascii=False), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--resume-dry-sha256")
    parser.add_argument("--resume-dry-identity")
    parser.add_argument("--sensitivity", action="store_true")
    parser.add_argument("--v2", action="store_true")
    parser.add_argument("--v3", action="store_true")
    parser.add_argument("--substep-s", type=float, default=60)
    parser.add_argument("--sensitivity-steps", type=float, nargs=3, default=(60, 30, 15))
    parser.add_argument("--refinement", action="store_true")
    parser.add_argument("--scenarios", nargs="+", choices=("dry", "wet", "ordinary", "strong"), default=("dry", "wet", "ordinary", "strong"))
    arguments = parser.parse_args()
    destination = arguments.output or ROOT / "verification/td-basin-generation" / ("A-storage-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    if arguments.sensitivity:
        verify_sensitivity(destination, v2=arguments.v2, sensitivity_steps=arguments.sensitivity_steps)
    else:
        verify(destination, resume=arguments.resume, resume_dry_sha256=arguments.resume_dry_sha256,
               resume_dry_identity=arguments.resume_dry_identity, v2=arguments.v2, v3=arguments.v3, substep_s=arguments.substep_s,
               refinement=arguments.refinement, scenarios=arguments.scenarios)
