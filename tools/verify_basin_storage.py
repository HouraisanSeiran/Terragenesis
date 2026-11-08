"""M4 tools.verify_basin_storage; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from datetime import datetime as _m4_verify_td_basin_storage_datetime
from datetime import datetime as _m4_verify_td_basin_storage_v4_datetime
from datetime import datetime as _m4_verify_td_basin_storage_v4_matching_datetime
from datetime import datetime as _m4_verify_td_basin_storage_v5_datetime
from datetime import datetime as _m4_verify_td_basin_storage_v6_datetime
from datetime import datetime as _m4_verify_td_basin_storage_v7_datetime
from datetime import datetime as _m4_verify_td_basin_storage_v7_first_hour_datetime
from datetime import timezone as _m4_verify_td_basin_storage_timezone
from datetime import timezone as _m4_verify_td_basin_storage_v4_matching_timezone
from datetime import timezone as _m4_verify_td_basin_storage_v4_timezone
from datetime import timezone as _m4_verify_td_basin_storage_v5_timezone
from datetime import timezone as _m4_verify_td_basin_storage_v6_timezone
from datetime import timezone as _m4_verify_td_basin_storage_v7_first_hour_timezone
from datetime import timezone as _m4_verify_td_basin_storage_v7_timezone
from importlib.metadata import version as _m4_verify_td_basin_storage_v4_version
from importlib.metadata import version as _m4_verify_td_basin_storage_v5_version
from importlib.metadata import version as _m4_verify_td_basin_storage_v6_version
from importlib.metadata import version as _m4_verify_td_basin_storage_v7_first_hour_version
from importlib.metadata import version as _m4_verify_td_basin_storage_v7_version
from pathlib import Path as _m4_verify_td_basin_storage_Path
from pathlib import Path as _m4_verify_td_basin_storage_v4_Path
from pathlib import Path as _m4_verify_td_basin_storage_v4_matching_Path
from pathlib import Path as _m4_verify_td_basin_storage_v5_Path
from pathlib import Path as _m4_verify_td_basin_storage_v6_Path
from pathlib import Path as _m4_verify_td_basin_storage_v7_Path
from pathlib import Path as _m4_verify_td_basin_storage_v7_first_hour_Path
import argparse as _m4_verify_td_basin_storage_argparse
import json as _m4_verify_td_basin_storage_json
import json as _m4_verify_td_basin_storage_v4_json
import json as _m4_verify_td_basin_storage_v4_matching_json
import json as _m4_verify_td_basin_storage_v5_json
import json as _m4_verify_td_basin_storage_v6_json
import json as _m4_verify_td_basin_storage_v7_first_hour_json
import json as _m4_verify_td_basin_storage_v7_json
import numpy as _m4_verify_td_basin_storage_np
import numpy as _m4_verify_td_basin_storage_v4_matching_np
import numpy as _m4_verify_td_basin_storage_v4_np
import numpy as _m4_verify_td_basin_storage_v5_np
import numpy as _m4_verify_td_basin_storage_v6_np
import numpy as _m4_verify_td_basin_storage_v7_first_hour_np
import numpy as _m4_verify_td_basin_storage_v7_np
import psutil as _m4_verify_td_basin_storage_v4_psutil
import psutil as _m4_verify_td_basin_storage_v5_psutil
import psutil as _m4_verify_td_basin_storage_v6_psutil
import psutil as _m4_verify_td_basin_storage_v7_first_hour_psutil
import psutil as _m4_verify_td_basin_storage_v7_psutil
import sys as _m4_verify_td_basin_storage_sys
import sys as _m4_verify_td_basin_storage_v4_matching_sys
import sys as _m4_verify_td_basin_storage_v4_sys
import sys as _m4_verify_td_basin_storage_v5_sys
import sys as _m4_verify_td_basin_storage_v6_sys
import sys as _m4_verify_td_basin_storage_v7_first_hour_sys
import sys as _m4_verify_td_basin_storage_v7_sys
import time as _m4_verify_td_basin_storage_time
import time as _m4_verify_td_basin_storage_v4_time
import time as _m4_verify_td_basin_storage_v5_time
import time as _m4_verify_td_basin_storage_v6_time
import time as _m4_verify_td_basin_storage_v7_first_hour_time
import time as _m4_verify_td_basin_storage_v7_time

# --- tools/verify_td_basin_storage.py:10 ---
threshold_storage_ROOT = _m4_verify_td_basin_storage_Path(__file__).resolve().parents[1]

# --- tools/verify_td_basin_storage.py:11 ---
_m4_verify_td_basin_storage_sys.path.insert(0, str(threshold_storage_ROOT))

# --- tools/verify_td_basin_storage.py:26 ---
threshold_storage_HIERARCHY = threshold_storage_ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"

# --- tools/verify_td_basin_storage.py:27 ---
threshold_storage_HIERARCHY_SHA256 = "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422"

# --- tools/verify_td_basin_storage.py:28 ---
threshold_storage_HIERARCHY_IDENTITY = "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"

# --- tools/verify_td_basin_storage.py:31 ---
def threshold_storage_write_json(path, record):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_basin_storage_publish_bytes
    _m4_verify_td_basin_storage_publish_bytes(path, _m4_verify_td_basin_storage_json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))

# --- tools/verify_td_basin_storage.py:35 ---
def threshold_storage_summary(result):
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

# --- tools/verify_td_basin_storage.py:66 ---
def threshold_storage_verify_sensitivity(destination, *, v2=False, sensitivity_steps=(60, 30, 15)):
    from terrain_pipeline.basin_storage import PRIMARY_SHA256 as _m4_verify_td_basin_storage_PRIMARY_SHA256
    from terrain_pipeline.basin_storage import make_td_source as _m4_verify_td_basin_storage_make_td_source
    from terrain_pipeline.basin_storage import save_basin_storage as _m4_verify_td_basin_storage_save_basin_storage
    from terrain_pipeline.basin_storage import simulate_threshold_storage as _m4_verify_td_basin_storage_simulate_basin_storage
    from terrain_pipeline.basin_topology import build_basin_hierarchy as _m4_verify_td_basin_storage_build_basin_hierarchy
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_basin_storage_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_file_sha256
    destination = _m4_verify_td_basin_storage_Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    hierarchy = _m4_verify_td_basin_storage_load_basin_hierarchy(threshold_storage_HIERARCHY, expected_sha256=threshold_storage_HIERARCHY_SHA256, expected_identity=threshold_storage_HIERARCHY_IDENTITY)
    solver = _m4_verify_td_basin_storage_simulate_basin_storage
    if v2:
        from terrain_pipeline.basin_storage import storageimplicit_simulate as solver
    arrays = hierarchy["arrays"]
    parent = arrays["node_parent"]
    candidates = _m4_verify_td_basin_storage_np.flatnonzero((arrays["node_cell_count"] >= 100) & (arrays["node_cell_count"] <= 500)
        & ~arrays["node_unknown_contact"] & ~arrays["node_open_boundary"] & _m4_verify_td_basin_storage_np.isfinite(arrays["node_upper_m"]))
    if not len(candidates):
        raise ValueError("no complete covered representative subtree")
    node = int(candidates[len(candidates) // 2])
    descendant = _m4_verify_td_basin_storage_np.zeros(len(parent), bool)
    descendant[node] = True
    for candidate in range(node - 1, -1, -1):
        if parent[candidate] >= 0:
            descendant[candidate] = descendant[parent[candidate]]
    mask = descendant[arrays["cell_owner"]]
    rows, columns = _m4_verify_td_basin_storage_np.where(mask)
    row_start, row_stop = int(rows.min()), int(rows.max() + 1)
    column_start, column_stop = int(columns.min()), int(columns.max() + 1)
    window = _m4_verify_td_basin_storage_np.s_[row_start:row_stop, column_start:column_stop]
    spacing = hierarchy["metadata"]["spacing_m"]
    origin = hierarchy["metadata"]["origin_m_xz"]
    source = _m4_verify_td_basin_storage_make_td_source(arrays["height_m"][window], spacing_m=spacing,
        origin_m_xz=[origin[0] + column_start * spacing, origin[1] + row_start * spacing], valid_mask=mask[window],
        source_sha256=_m4_verify_td_basin_storage_PRIMARY_SHA256)
    local = _m4_verify_td_basin_storage_build_basin_hierarchy(source)
    threshold_storage_write_json(destination / "sensitivity-inputs.json", {"source_hierarchy_sha256": threshold_storage_HIERARCHY_SHA256,
        "selected_node": node, "subtree_cells": int(mask.sum()), "crop": [row_start, row_stop, column_start, column_stop],
        "boundary": "all source subtree cells retained; artificial sealed divide, no external contributing inflow",
        "sill_m": float(arrays["node_upper_m"][node]), "conductance_m_s": 0.6,
        "tests": "ordinary and strong 24h; no rerun full domain", "substeps_s": list(sensitivity_steps), "v2": v2,
        "declared_gates": {"head_max_difference_m": 0.001, "receiver_volume_relative_l1": 0.01},
        "code_sha256": {name: _m4_verify_td_basin_storage_file_sha256(threshold_storage_ROOT / name) for name in (
            'terrain_pipeline/basin_storage.py', 'tools/verify_basin_storage.py')}})
    report = {"selected_node": node, "scenarios": {}, "full_domain_transient_converged": False,
        "morphology_flux_ready": False, "scope": "complete covered subtree; sealed boundary sensitivity only"}
    for scenario, rate in (("ordinary", 10), ("strong", 30)):
        rain = _m4_verify_td_basin_storage_np.zeros(24)
        rain[:6] = rate
        snapshots = []
        records = []
        for substep in sensitivity_steps:
            print("sensitivity " + scenario + " " + str(substep), flush=True)
            result = solver(local, rain, parameters={"substep_s": substep})
            path = destination / (scenario + "-" + str(substep) + ".npz")
            _m4_verify_td_basin_storage_save_basin_storage(path, result)
            values = result["arrays"]
            active = int(values["proposed_active_count"].sum())
            record = threshold_storage_summary(result)
            record.update({"archive_sha256": _m4_verify_td_basin_storage_file_sha256(path), "substep_s": substep,
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
    threshold_storage_write_json(destination / "report.json", report)
    print(_m4_verify_td_basin_storage_json.dumps({"output": str(destination), "selected_node": node,
        "comparisons": {key: value["comparisons"] for key, value in report["scenarios"].items()}}, ensure_ascii=False), flush=True)
    return report

# --- tools/verify_td_basin_storage.py:145 ---
def threshold_storage_verify(destination, *, resume=False, resume_dry_sha256=None, resume_dry_identity=None, v2=False, v3=False, substep_s=60, refinement=False, scenarios=("dry", "wet", "ordinary", "strong")):
    from terrain_pipeline.basin_storage import PRIMARY_PATH as _m4_verify_td_basin_storage_PRIMARY_PATH
    from terrain_pipeline.basin_storage import PRIMARY_SHA256 as _m4_verify_td_basin_storage_PRIMARY_SHA256
    from terrain_pipeline.basin_storage import load_basin_storage as _m4_verify_td_basin_storage_load_basin_storage
    from terrain_pipeline.basin_storage import save_basin_storage as _m4_verify_td_basin_storage_save_basin_storage
    from terrain_pipeline.basin_storage import simulate_threshold_storage as _m4_verify_td_basin_storage_simulate_basin_storage
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_basin_storage_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_file_sha256
    from terrain_pipeline.runoff import RunoffParameters as _m4_verify_td_basin_storage_RunoffParameters
    destination = _m4_verify_td_basin_storage_Path(destination)
    if destination.exists() and not resume:
        raise FileExistsError(destination)
    hierarchy = _m4_verify_td_basin_storage_load_basin_hierarchy(threshold_storage_HIERARCHY, expected_sha256=threshold_storage_HIERARCHY_SHA256, expected_identity=threshold_storage_HIERARCHY_IDENTITY)
    if sum(bool(value) for value in (v2, v3, refinement)) > 1:
        raise ValueError("storage solver versions are mutually exclusive")
    solver = _m4_verify_td_basin_storage_simulate_basin_storage
    if v2:
        from terrain_pipeline.basin_storage import storageimplicit_simulate as solver
    if refinement:
        from terrain_pipeline.basin_storage import storagerefined_simulate as solver
    if v3:
        from terrain_pipeline.basin_storage import storagev3_simulate as solver
    bed = hierarchy["arrays"]["height_m"]
    source_before = _m4_verify_td_basin_storage_file_sha256(_m4_verify_td_basin_storage_PRIMARY_PATH)
    if source_before != _m4_verify_td_basin_storage_PRIMARY_SHA256:
        raise ValueError("original TD hash changed")
    inputs_path = destination / ("resume-inputs.json" if resume else "run-inputs.json")
    inputs = {"hierarchy_path": str(threshold_storage_HIERARCHY), "hierarchy_sha256": threshold_storage_HIERARCHY_SHA256,
        "hierarchy_identity_sha256": threshold_storage_HIERARCHY_IDENTITY, "source_sha256": source_before,
        "forcing": "24 hourly steps; ordinary first6 10mm/h; strong first6 30mm/h; rest zero",
        "parameters": "linear D4 threshold conductance; soil default except dry initial soil=0", "substep_s": substep_s,
        "v2": v2, "v3": v3, "refinement": refinement, "scenarios": list(scenarios),
        "wet_initial": "first merge subtree initialized to birth+0.00005m; dry soil; no rain",
        "memory_budget_bytes": 1024 ** 3,
        "code_sha256": {name: _m4_verify_td_basin_storage_file_sha256(threshold_storage_ROOT / name) for name in (
            'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
            'tests/test_basin_storage.py', 'tools/verify_basin_storage.py')}}
    if v3:
        inputs["code_sha256"]['terrain_pipeline/basin_storage.py'] = _m4_verify_td_basin_storage_file_sha256(threshold_storage_ROOT / 'terrain_pipeline/basin_storage.py')
    threshold_storage_write_json(inputs_path, inputs)
    records = {}
    start = _m4_verify_td_basin_storage_time.perf_counter()
    for scenario in scenarios:
        rain = _m4_verify_td_basin_storage_np.zeros(24)
        if scenario in ("ordinary", "strong"):
            rain[:6] = 10 if scenario == "ordinary" else 30
        initial = _m4_verify_td_basin_storage_np.zeros(bed.shape)
        if scenario == "wet":
            arrays = hierarchy["arrays"]
            parent = arrays["node_parent"]
            owner = arrays["cell_owner"].ravel()
            merged = _m4_verify_td_basin_storage_np.flatnonzero(_m4_verify_td_basin_storage_np.bincount(parent[parent >= 0], minlength=len(parent)) > 0)
            node = int(merged[0])
            membership = owner == node
            for candidate in range(node):
                ancestor = candidate
                while ancestor >= 0 and ancestor != node:
                    ancestor = int(parent[ancestor])
                if ancestor == node:
                    membership |= owner == candidate
            level = arrays["node_birth_m"][node] + 0.00005
            initial.ravel()[membership] = _m4_verify_td_basin_storage_np.maximum(0, level - bed.ravel()[membership])
            threshold_storage_write_json(destination / "wet-initial.json", {"merge_node": node, "level_m": float(level),
                "initial_surface_m3": float(initial.sum() * hierarchy["metadata"]["spacing_m"] ** 2),
                "purpose": "no-rain merged wet state recession/splitting; no soil water supply"})
        parameters = _m4_verify_td_basin_storage_RunoffParameters(initial_soil_mm=0) if scenario in ("dry", "wet") else _m4_verify_td_basin_storage_RunoffParameters()
        scenario_start = _m4_verify_td_basin_storage_time.perf_counter()
        print("starting " + scenario, flush=True)
        path = destination / (scenario + ".npz")
        if resume and path.exists():
            if scenario != "dry" or resume_dry_sha256 is None or resume_dry_identity is None:
                raise ValueError("resume existing archive requires external dry pins; other partial runs not supported")
            result = _m4_verify_td_basin_storage_load_basin_storage(path, expected_sha256=resume_dry_sha256, expected_identity=resume_dry_identity)
        else:
            result = solver(hierarchy, rain, initial_depth_m=initial, runoff_parameters=parameters,
                            parameters={"substep_s": substep_s})
            _m4_verify_td_basin_storage_save_basin_storage(path, result)
        sha = _m4_verify_td_basin_storage_file_sha256(path)
        loaded = _m4_verify_td_basin_storage_load_basin_storage(path, expected_sha256=sha, expected_identity=result["identity_sha256"])
        record = threshold_storage_summary(loaded)
        record.update({"archive_path": str(path), "archive_sha256": sha, "elapsed_s": _m4_verify_td_basin_storage_time.perf_counter() - scenario_start})
        records[scenario] = record
        threshold_storage_write_json(destination / (scenario + "-report.json"), record)
        print(scenario + " complete: " + _m4_verify_td_basin_storage_json.dumps({key: record[key] for key in (
            "rain_m3", "final_surface_m3", "boundary_export_m3", "elapsed_s", "max_cell_residual_m3")}), flush=True)
        del result, loaded
    if _m4_verify_td_basin_storage_file_sha256(_m4_verify_td_basin_storage_PRIMARY_PATH) != source_before or _m4_verify_td_basin_storage_file_sha256(threshold_storage_HIERARCHY) != threshold_storage_HIERARCHY_SHA256:
        raise ValueError("source/hierarchy modified during storage run")
    report = {"status": "53_finite_time_baseline_ready_for_independent_audit", "scenarios": records,
        "elapsed_s": _m4_verify_td_basin_storage_time.perf_counter() - start, "original_bed_unchanged": True,
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
    threshold_storage_write_json(destination / "report.json", report)
    print(_m4_verify_td_basin_storage_json.dumps({"output": str(destination), "elapsed_s": report["elapsed_s"]}, ensure_ascii=False), flush=True)
    return report

def run_threshold_storage_cli():
    parser = _m4_verify_td_basin_storage_argparse.ArgumentParser()
    parser.add_argument("--output", type=_m4_verify_td_basin_storage_Path)
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
    destination = arguments.output or threshold_storage_ROOT / "verification/td-basin-generation" / ("A-storage-" + _m4_verify_td_basin_storage_datetime.now(_m4_verify_td_basin_storage_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    if arguments.sensitivity:
        threshold_storage_verify_sensitivity(destination, v2=arguments.v2, sensitivity_steps=arguments.sensitivity_steps)
    else:
        threshold_storage_verify(destination, resume=arguments.resume, resume_dry_sha256=arguments.resume_dry_sha256,
               resume_dry_identity=arguments.resume_dry_identity, v2=arguments.v2, v3=arguments.v3, substep_s=arguments.substep_s,
               refinement=arguments.refinement, scenarios=arguments.scenarios)

# --- tools/verify_td_basin_storage_v4.py:10 ---
threshold_pair_ROOT = _m4_verify_td_basin_storage_v4_Path(__file__).resolve().parents[1]

# --- tools/verify_td_basin_storage_v4.py:11 ---
_m4_verify_td_basin_storage_v4_sys.path.insert(0, str(threshold_pair_ROOT))

# --- tools/verify_td_basin_storage_v4.py:28 ---
def threshold_pair_write(path, record):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_basin_storage_v4_publish_bytes
    _m4_verify_td_basin_storage_v4_publish_bytes(path, _m4_verify_td_basin_storage_v4_json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))

# --- tools/verify_td_basin_storage_v4.py:32 ---
def threshold_pair_compare(coarse, fine):
    difference = abs(coarse["depth_m"] - fine["depth_m"])
    step, cell = _m4_verify_td_basin_storage_v4_np.unravel_index(_m4_verify_td_basin_storage_v4_np.argmax(difference), difference.shape)
    receiver_error = float(abs(coarse["routed_volume_m3"] - fine["routed_volume_m3"]).sum() /
                           max(1e-12, fine["routed_volume_m3"].sum()))
    head_error = float(difference[step, cell])
    diagnostics = {}
    for name in ("lake_rain_m3", "land_rain_m3", "local_release_m3", "internal_net_m3", "surface_et_m3"):
        delta = coarse[name][:step].sum(axis=0) - fine[name][:step].sum(axis=0)
        diagnostics[name] = {"at_max_depth_cell_m3": float(delta[cell]), "global_l1_m3": float(abs(delta).sum())}
    for name in ("soil_mm", "fast_mm", "slow_mm"):
        diagnostics[name] = {"at_max_depth_cell_mm": float(coarse[name][step, cell] - fine[name][step, cell]),
                             "max_saved_difference_mm": float(abs(coarse[name] - fine[name]).max())}
    return {"max_saved_depth_difference_m": head_error, "receiver_volume_relative_l1": receiver_error,
            "depth_gate_m": .001, "receiver_gate": .01, "gate_passed": head_error <= .001 and receiver_error <= .01,
            "max_difference_step": int(step), "max_difference_cell": int(cell),
            "max_difference_zx": list(map(int, divmod(cell, coarse["height_m"].shape[1]))),
            "coarse_depth_m": float(coarse["depth_m"][step, cell]), "fine_depth_m": float(fine["depth_m"][step, cell]),
            "forcing_partition_and_exchange_diagnostics": diagnostics,
            "failure_reason": None if head_error <= .001 and receiver_error <= .01 else "full-domain saved transient difference exceeds fixed gate"}

# --- tools/verify_td_basin_storage_v4.py:54 ---
def threshold_pair_verify(destination):
    from terrain_pipeline.basin_storage import PRIMARY_PATH as _m4_verify_td_basin_storage_v4_PRIMARY_PATH
    from terrain_pipeline.basin_storage import PRIMARY_SHA256 as _m4_verify_td_basin_storage_v4_PRIMARY_SHA256
    from terrain_pipeline.basin_storage import THRESHOLD_PAIR_PROFILE as _m4_verify_td_basin_storage_v4_PROFILE
    from terrain_pipeline.basin_storage import load_basin_storage as _m4_verify_td_basin_storage_v4_load_basin_storage
    from terrain_pipeline.basin_storage import save_basin_storage as _m4_verify_td_basin_storage_v4_save_basin_storage
    from terrain_pipeline.basin_storage import storagev4_simulate as _m4_verify_td_basin_storage_v4_simulate_basin_storage
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_basin_storage_v4_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_v4_file_sha256
    from tools.audit_td_basin_generation import audit_storage as _m4_verify_td_basin_storage_v4_audit_storage
    from tools.audit_td_basin_generation import read_saved as _m4_verify_td_basin_storage_v4_read_saved
    destination = _m4_verify_td_basin_storage_v4_Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if _m4_verify_td_basin_storage_v4_file_sha256(_m4_verify_td_basin_storage_v4_PRIMARY_PATH) != _m4_verify_td_basin_storage_v4_PRIMARY_SHA256:
        raise ValueError("primary source changed")
    code_names = ('terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'tools/verify_basin_storage.py',
                  "tools/audit_td_basin_generation.py")
    code = {name: _m4_verify_td_basin_storage_v4_file_sha256(threshold_pair_ROOT / name) for name in code_names}
    hierarchy = _m4_verify_td_basin_storage_v4_load_basin_hierarchy(threshold_storage_HIERARCHY, expected_sha256=threshold_storage_HIERARCHY_SHA256, expected_identity=threshold_storage_HIERARCHY_IDENTITY)
    cells = hierarchy["arrays"]["height_m"].size
    faces = len(hierarchy["arrays"]["face_cells"])
    inputs = {"primary": {"path": str(_m4_verify_td_basin_storage_v4_PRIMARY_PATH), "sha256": _m4_verify_td_basin_storage_v4_PRIMARY_SHA256},
              "hierarchy": {"path": str(threshold_storage_HIERARCHY), "sha256": threshold_storage_HIERARCHY_SHA256, "identity": threshold_storage_HIERARCHY_IDENTITY},
              "source_identity": hierarchy["metadata"]["source_identity_sha256"],
              "forcing": "24 hourly states; first6 ordinary10mm/h or strong30mm/h; remaining18 zero",
              "initial_state": "depth0; frozen default RunoffParameters soil/fast/slow; identical across refinements",
              "steps_s": [5., 2.5], "face_conductance_m_s": .6, "wet_threshold_m": 1e-9,
              "profile": _m4_verify_td_basin_storage_v4_PROFILE, "max_work_face_steps": 6000000000, "job_memory_budget_bytes": 1073741824,
              "work_by_step": {str(step): int(86400 / step * faces) for step in (5., 2.5)},
              "saved_cells_time": 24 * cells, "code_sha256": code}
    threshold_pair_write(destination / "run-inputs.json", inputs)
    execution = {"schema": "td-v4-execution-code-v1", "profile": _m4_verify_td_basin_storage_v4_PROFILE, "numba": _m4_verify_td_basin_storage_v4_version("numba"),
                 "numpy": _m4_verify_td_basin_storage_v4_version("numpy"), "python": _m4_verify_td_basin_storage_v4_sys.version, "fastmath": False, "code_sha256": code,
                 "solver_source_utf8": (threshold_pair_ROOT / code_names[0]).read_text(encoding="utf-8"),
                 "cold_read": "v4 validation uses v2 parameter schema only; no import of compiled v4, JIT, or advancement",
                 "v3_correctness_evidence_invalidated": True,
                 "v2_equivalence": "same independently verified threshold pair law; full-domain strong splitting error may persist"}
    threshold_pair_write(destination / "execution-code.json", execution)
    results = {}
    comparisons = {}
    process = _m4_verify_td_basin_storage_v4_psutil.Process()
    start = _m4_verify_td_basin_storage_v4_time.perf_counter()
    for scenario in ("ordinary", "strong"):
        pins = {}
        for step in (5., 2.5):
            print(f"starting {scenario} {step}s compiled v4", flush=True)
            began = _m4_verify_td_basin_storage_v4_time.perf_counter()
            rain = _m4_verify_td_basin_storage_v4_np.zeros(24)
            rain[:6] = 10 if scenario == "ordinary" else 30
            result = _m4_verify_td_basin_storage_v4_simulate_basin_storage(hierarchy, rain, parameters={"substep_s": step})
            directory = destination / f"{scenario}-{step:g}s"
            path = directory / "storage.npz"
            memory = process.memory_info()
            peak = int(getattr(memory, "peak_wset", memory.rss))
            if peak > 1073741824:
                threshold_pair_write(directory / "failure.json", {"reason": "process memory exceeded declared1GiB", "peak_bytes": peak})
                raise MemoryError("v4 job budget")
            _m4_verify_td_basin_storage_v4_save_basin_storage(path, result)
            pin = {"path": str(path), "expected_sha256": _m4_verify_td_basin_storage_v4_file_sha256(path), "expected_identity": result["identity_sha256"]}
            record = threshold_storage_summary(result)
            record.update({"pin": pin, "elapsed_s": _m4_verify_td_basin_storage_v4_time.perf_counter() - began, "peak_process_bytes": peak,
                           "code_sha256": code, "profile": _m4_verify_td_basin_storage_v4_PROFILE, "hydraulic_ready": False, "publishable": False})
            threshold_pair_write(directory / "report.json", record)
            del result
            arrays, metadata = _m4_verify_td_basin_storage_v4_read_saved(path, pin["expected_sha256"])
            audit = _m4_verify_td_basin_storage_v4_audit_storage(arrays, metadata)
            threshold_pair_write(directory / "independent-audit.json", {"pin": pin, "checks": audit, "solver_advanced": False,
                  "auditor_sha256": code["tools/audit_td_basin_generation.py"], "hydraulic_ready": False})
            del arrays
            results[f"{scenario}-{step:g}s"] = record
            pins[str(step)] = pin
            print(f"complete {scenario} {step}s elapsed {record['elapsed_s']:.2f}s peak {peak}", flush=True)
        coarse = _m4_verify_td_basin_storage_v4_load_basin_storage(**pins["5.0"])
        fine = _m4_verify_td_basin_storage_v4_load_basin_storage(**pins["2.5"])
        comparisons[scenario] = {**threshold_pair_compare(coarse["arrays"], fine["arrays"]), "coarse": pins["5.0"], "fine": pins["2.5"]}
        threshold_pair_write(destination / (scenario + "-comparison.json"), comparisons[scenario])
        print(_m4_verify_td_basin_storage_v4_json.dumps({scenario: comparisons[scenario]}, ensure_ascii=True), flush=True)
        del coarse, fine
    if _m4_verify_td_basin_storage_v4_file_sha256(_m4_verify_td_basin_storage_v4_PRIMARY_PATH) != _m4_verify_td_basin_storage_v4_PRIMARY_SHA256 or _m4_verify_td_basin_storage_v4_file_sha256(threshold_storage_HIERARCHY) != threshold_storage_HIERARCHY_SHA256:
        raise ValueError("input changed")
    if any(_m4_verify_td_basin_storage_v4_file_sha256(threshold_pair_ROOT / name) != sha for name, sha in code.items()):
        raise ValueError("frozen execution source changed")
    report = {"schema": "td-v4-full-domain-refinement-v1", "scope": "entire baseline calculation domain",
              "comparisons": comparisons, "runs": results, "elapsed_s": _m4_verify_td_basin_storage_v4_time.perf_counter() - start,
              "all_numerical_gates_passed": all(item["gate_passed"] for item in comparisons.values()),
              "hydraulic_ready": False, "publishable": False, "transient_converged": False,
              "next_repair_if_failed": "Separate runoff/rain wet-mask partition time error from face splitting via frozen hourly partition and diagnostic forcing replay on the maximal-error catchment; maintain same g/rain and gate.",
              "old_packages_unchanged": True, "execution_sha256": _m4_verify_td_basin_storage_v4_file_sha256(destination / "execution-code.json")}
    threshold_pair_write(destination / "report.json", report)
    print(_m4_verify_td_basin_storage_v4_json.dumps({"output": str(destination), "report_sha256": _m4_verify_td_basin_storage_v4_file_sha256(destination / "report.json"),
                      "gates": report["all_numerical_gates_passed"]}), flush=True)

def run_threshold_pair_cli():
    threshold_pair_verify(threshold_pair_ROOT / "verification/td-basin-generation" / ("A-storage-v4-full-" + _m4_verify_td_basin_storage_v4_datetime.now(_m4_verify_td_basin_storage_v4_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")))

# --- tools/verify_td_basin_storage_v4_matching.py:8 ---
threshold_matching_ROOT = _m4_verify_td_basin_storage_v4_matching_Path(__file__).resolve().parents[1]

# --- tools/verify_td_basin_storage_v4_matching.py:9 ---
_m4_verify_td_basin_storage_v4_matching_sys.path.insert(0, str(threshold_matching_ROOT))

# --- tools/verify_td_basin_storage_v4_matching.py:19 ---
def threshold_matching_verify():
    from terrain_pipeline.basin_storage import exchange_strang_two_sweep as _m4_verify_td_basin_storage_v4_matching_numpy_exchange
    from terrain_pipeline.basin_storage import exchange_threshold_pair as _m4_verify_td_basin_storage_v4_matching_exchange
    from terrain_pipeline.basin_storage import parameters_threshold_pair as _m4_verify_td_basin_storage_v4_matching_parameters
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_v4_matching_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_basin_storage_v4_matching_publish_bytes
    random = _m4_verify_td_basin_storage_v4_matching_np.random.default_rng(2026100209)
    records = []
    for case in range(80):
        rows, columns = int(random.integers(2, 6)), int(random.integers(3, 8))
        grid = _m4_verify_td_basin_storage_v4_matching_np.arange(rows * columns).reshape(rows, columns)
        valid = random.random(rows * columns) > .2
        faces = _m4_verify_td_basin_storage_v4_matching_np.vstack((_m4_verify_td_basin_storage_v4_matching_np.column_stack((grid[:, :-1].ravel(), grid[:, 1:].ravel())),
                           _m4_verify_td_basin_storage_v4_matching_np.column_stack((grid[:-1].ravel(), grid[1:].ravel())))).astype(_m4_verify_td_basin_storage_v4_matching_np.int64)
        faces = faces[valid[faces].all(axis=1)]
        bed = random.uniform(1300, 1400, valid.size)
        depth = random.uniform(0, 8, valid.size)
        depth[~valid] = 0
        boundary = _m4_verify_td_basin_storage_v4_matching_np.flatnonzero(valid & ((grid.ravel() // columns == 0) | (grid.ravel() % columns == 0)))
        width = _m4_verify_td_basin_storage_v4_matching_np.full(len(boundary), 30.)
        duration = (60., 5., 2.5, 1.25)[case % 4]
        arguments = (depth, bed, faces, boundary, width, 30., duration, _m4_verify_td_basin_storage_v4_matching_parameters(None), columns)
        compiled = _m4_verify_td_basin_storage_v4_matching_exchange(*arguments)
        reference = _m4_verify_td_basin_storage_v4_matching_numpy_exchange(*arguments)
        error = max(float(abs(actual - expected).max(initial=0)) for actual, expected in zip(compiled, reference))
        final, forward, reverse, exported, forward_s, reverse_s = compiled
        net = forward - reverse
        divergence = _m4_verify_td_basin_storage_v4_matching_np.bincount(faces[:, 1], weights=net, minlength=valid.size) - _m4_verify_td_basin_storage_v4_matching_np.bincount(
            faces[:, 0], weights=net, minlength=valid.size)
        _m4_verify_td_basin_storage_v4_matching_np.add.at(divergence, boundary, -exported)
        divergence_error = float(abs((final - depth) * 900 - divergence).max())
        mass_error = float(abs(final.sum() * 900 + exported.sum() - depth.sum() * 900))
        activity_equal = _m4_verify_td_basin_storage_v4_matching_np.array_equal(forward_s, reference[4]) and _m4_verify_td_basin_storage_v4_matching_np.array_equal(reverse_s, reference[5])
        passed = error < 1e-8 and divergence_error < 1e-8 and mass_error < 1e-8 and activity_equal and _m4_verify_td_basin_storage_v4_matching_np.all(final >= 0)
        records.append({"case": case, "shape": [rows, columns], "unknown_cells": int((~valid).sum()),
                        "faces": len(faces), "dt_s": duration, "max_differential": error,
                        "divergence_error_m3": divergence_error, "mass_error_m3": mass_error,
                        "activity_equal": activity_equal, "passed": bool(passed)})
    report = {"schema": "td-v4-masked-matching-differential-v1", "cases": records,
              "all_passed": all(record["passed"] for record in records), "seed": 2026100209,
              "max_differential": max(record["max_differential"] for record in records),
              "code_sha256": {name: _m4_verify_td_basin_storage_v4_matching_file_sha256(threshold_matching_ROOT / name) for name in (
                  'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'tools/verify_basin_storage.py')},
              "hydraulic_ready": False, "publishable": False,
              "scope": "unforced masked D4 matching and engineered boundary kernels; not full-domain convergence"}
    path = threshold_matching_ROOT / "verification/td-basin-generation" / ("A-v4-matching-" + _m4_verify_td_basin_storage_v4_matching_datetime.now(_m4_verify_td_basin_storage_v4_matching_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    _m4_verify_td_basin_storage_v4_matching_publish_bytes(path, _m4_verify_td_basin_storage_v4_matching_json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(_m4_verify_td_basin_storage_v4_matching_json.dumps({"path": str(path), "sha256": _m4_verify_td_basin_storage_v4_matching_file_sha256(path), "all_passed": report["all_passed"],
                      "max_differential": report["max_differential"]}))
    if not report["all_passed"]:
        raise AssertionError("v4 masked matching differential failed")

def run_threshold_matching_cli():
    threshold_matching_verify()

# --- tools/verify_td_basin_storage_v5.py:10 ---
symmetric_forcing_ROOT = _m4_verify_td_basin_storage_v5_Path(__file__).resolve().parents[1]

# --- tools/verify_td_basin_storage_v5.py:11 ---
_m4_verify_td_basin_storage_v5_sys.path.insert(0, str(symmetric_forcing_ROOT))

# --- tools/verify_td_basin_storage_v5.py:28 ---
def symmetric_forcing_write(path, record):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_basin_storage_v5_publish_bytes
    _m4_verify_td_basin_storage_v5_publish_bytes(path, _m4_verify_td_basin_storage_v5_json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))

# --- tools/verify_td_basin_storage_v5.py:32 ---
def symmetric_forcing_compare(coarse, fine):
    difference = abs(coarse["depth_m"] - fine["depth_m"])
    step, cell = _m4_verify_td_basin_storage_v5_np.unravel_index(_m4_verify_td_basin_storage_v5_np.argmax(difference), difference.shape)
    receiver_error = float(abs(coarse["routed_volume_m3"] - fine["routed_volume_m3"]).sum() /
                           max(1e-12, fine["routed_volume_m3"].sum()))
    head_error = float(difference[step, cell])
    diagnostics = {}
    for name in ("lake_rain_m3", "land_rain_m3", "local_release_m3", "internal_net_m3", "surface_et_m3"):
        delta = coarse[name][:step].sum(axis=0) - fine[name][:step].sum(axis=0)
        diagnostics[name] = {"at_max_depth_cell_m3": float(delta[cell]), "global_l1_m3": float(abs(delta).sum())}
    for name in ("soil_mm", "fast_mm", "slow_mm"):
        diagnostics[name] = {"at_max_depth_cell_mm": float(coarse[name][step, cell] - fine[name][step, cell]),
                             "max_saved_difference_mm": float(abs(coarse[name] - fine[name]).max())}
    return {"max_saved_depth_difference_m": head_error, "receiver_volume_relative_l1": receiver_error,
            "depth_gate_m": .001, "receiver_gate": .01, "gate_passed": head_error <= .001 and receiver_error <= .01,
            "max_difference_step": int(step), "max_difference_cell": int(cell),
            "max_difference_zx": list(map(int, divmod(cell, coarse["height_m"].shape[1]))),
            "coarse_depth_m": float(coarse["depth_m"][step, cell]), "fine_depth_m": float(fine["depth_m"][step, cell]),
            "forcing_partition_and_exchange_diagnostics": diagnostics,
            "failure_reason": None if head_error <= .001 and receiver_error <= .01 else "full-domain saved transient difference exceeds fixed gate"}

# --- tools/verify_td_basin_storage_v5.py:54 ---
def symmetric_forcing_verify(destination):
    from terrain_pipeline.basin_storage import PRIMARY_PATH as _m4_verify_td_basin_storage_v5_PRIMARY_PATH
    from terrain_pipeline.basin_storage import PRIMARY_SHA256 as _m4_verify_td_basin_storage_v5_PRIMARY_SHA256
    from terrain_pipeline.basin_storage import SYMMETRIC_FORCING_PROFILE as _m4_verify_td_basin_storage_v5_PROFILE
    from terrain_pipeline.basin_storage import storagev5_load_storage as _m4_verify_td_basin_storage_v5_load_basin_storage
    from terrain_pipeline.basin_storage import storagev5_save_storage as _m4_verify_td_basin_storage_v5_save_basin_storage
    from terrain_pipeline.basin_storage import storagev5_simulate as _m4_verify_td_basin_storage_v5_simulate_basin_storage
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_basin_storage_v5_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_v5_file_sha256
    from tools.audit_td_basin_generation import audit_storage as _m4_verify_td_basin_storage_v5_audit_storage
    from tools.audit_td_basin_generation import read_saved as _m4_verify_td_basin_storage_v5_read_saved
    destination = _m4_verify_td_basin_storage_v5_Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if _m4_verify_td_basin_storage_v5_file_sha256(_m4_verify_td_basin_storage_v5_PRIMARY_PATH) != _m4_verify_td_basin_storage_v5_PRIMARY_SHA256:
        raise ValueError("primary source changed")
    code_names = ('terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'tools/verify_basin_storage.py',
                  "tools/audit_td_basin_generation.py", 'terrain_pipeline/runoff.py',
                  'terrain_pipeline/common_infra.py', 'terrain_pipeline/basin_topology.py',
                  'terrain_pipeline/basin_storage.py', 'tools/verify_basin_storage.py', 'terrain_pipeline/basin_storage.py')
    code = {name: _m4_verify_td_basin_storage_v5_file_sha256(symmetric_forcing_ROOT / name) for name in code_names}
    hierarchy = _m4_verify_td_basin_storage_v5_load_basin_hierarchy(threshold_storage_HIERARCHY, expected_sha256=threshold_storage_HIERARCHY_SHA256, expected_identity=threshold_storage_HIERARCHY_IDENTITY)
    cells = hierarchy["arrays"]["height_m"].size
    faces = len(hierarchy["arrays"]["face_cells"])
    inputs = {"primary": {"path": str(_m4_verify_td_basin_storage_v5_PRIMARY_PATH), "sha256": _m4_verify_td_basin_storage_v5_PRIMARY_SHA256},
              "hierarchy": {"path": str(threshold_storage_HIERARCHY), "sha256": threshold_storage_HIERARCHY_SHA256, "identity": threshold_storage_HIERARCHY_IDENTITY},
              "source_identity": hierarchy["metadata"]["source_identity_sha256"],
              "forcing": "24 hourly states; first6 ordinary10mm/h or strong30mm/h; remaining18 zero",
              "initial_state": "depth0; frozen default RunoffParameters soil/fast/slow; identical across refinements",
              "steps_s": [5., 2.5], "face_conductance_m_s": .6, "wet_threshold_m": 1e-9,
              "profile": _m4_verify_td_basin_storage_v5_PROFILE, "max_work_face_steps": 6000000000, "job_memory_budget_bytes": 1073741824,
              "work_by_step": {str(step): int(86400 / step * faces) for step in (5., 2.5)},
              "saved_cells_time": 24 * cells, "code_sha256": code}
    symmetric_forcing_write(destination / "run-inputs.json", inputs)
    execution = {"schema": "td-v5-execution-code-v1", "profile": _m4_verify_td_basin_storage_v5_PROFILE, "numba": _m4_verify_td_basin_storage_v5_version("numba"),
                 "numpy": _m4_verify_td_basin_storage_v5_version("numpy"), "python": _m4_verify_td_basin_storage_v5_sys.version, "fastmath": False, "code_sha256": code,
                 "solver_source_utf8": (symmetric_forcing_ROOT / code_names[0]).read_text(encoding="utf-8"),
                 "cold_read": "v4 validation uses v2 parameter schema only; no import of symmetric forcing compiled v5, JIT, or advancement",
                 "v3_correctness_evidence_invalidated": True,
                 "forcing_correction": "half runoff/rain/ET, full compiled transport, half runoff/rain/ET; same g/rain/wet threshold",
                 "transport_source_utf8": (symmetric_forcing_ROOT / 'terrain_pipeline/basin_storage.py').read_text(encoding="utf-8")}
    symmetric_forcing_write(destination / "execution-code.json", execution)
    results = {}
    comparisons = {}
    process = _m4_verify_td_basin_storage_v5_psutil.Process()
    start = _m4_verify_td_basin_storage_v5_time.perf_counter()
    for scenario in ("strong", "ordinary"):
        pins = {}
        for step in (5., 2.5):
            print(f"starting {scenario} {step}s symmetric forcing compiled v5", flush=True)
            began = _m4_verify_td_basin_storage_v5_time.perf_counter()
            rain = _m4_verify_td_basin_storage_v5_np.zeros(24)
            rain[:6] = 10 if scenario == "ordinary" else 30
            result = _m4_verify_td_basin_storage_v5_simulate_basin_storage(hierarchy, rain, parameters={"substep_s": step})
            directory = destination / f"{scenario}-{step:g}s"
            path = directory / "storage.npz"
            memory = process.memory_info()
            peak = int(getattr(memory, "peak_wset", memory.rss))
            if peak > 1073741824:
                symmetric_forcing_write(directory / "failure.json", {"reason": "process memory exceeded declared1GiB", "peak_bytes": peak})
                raise MemoryError("v5 job budget")
            _m4_verify_td_basin_storage_v5_save_basin_storage(path, result)
            pin = {"path": str(path), "expected_sha256": _m4_verify_td_basin_storage_v5_file_sha256(path), "expected_identity": result["identity_sha256"]}
            record = threshold_storage_summary(result)
            record.update({"pin": pin, "elapsed_s": _m4_verify_td_basin_storage_v5_time.perf_counter() - began, "peak_process_bytes": peak,
                           "code_sha256": code, "profile": _m4_verify_td_basin_storage_v5_PROFILE, "hydraulic_ready": False, "publishable": False})
            symmetric_forcing_write(directory / "report.json", record)
            del result
            arrays, metadata = _m4_verify_td_basin_storage_v5_read_saved(path, pin["expected_sha256"])
            audit = _m4_verify_td_basin_storage_v5_audit_storage(arrays, metadata)
            symmetric_forcing_write(directory / "independent-audit.json", {"pin": pin, "checks": audit, "solver_advanced": False,
                  "auditor_sha256": code["tools/audit_td_basin_generation.py"], "hydraulic_ready": False})
            del arrays
            results[f"{scenario}-{step:g}s"] = record
            pins[str(step)] = pin
            print(f"complete {scenario} {step}s elapsed {record['elapsed_s']:.2f}s peak {peak}", flush=True)
        coarse = _m4_verify_td_basin_storage_v5_load_basin_storage(**pins["5.0"])
        fine = _m4_verify_td_basin_storage_v5_load_basin_storage(**pins["2.5"])
        comparisons[scenario] = {**symmetric_forcing_compare(coarse["arrays"], fine["arrays"]), "coarse": pins["5.0"], "fine": pins["2.5"]}
        symmetric_forcing_write(destination / (scenario + "-comparison.json"), comparisons[scenario])
        print(_m4_verify_td_basin_storage_v5_json.dumps({scenario: comparisons[scenario]}, ensure_ascii=True), flush=True)
        del coarse, fine
    if _m4_verify_td_basin_storage_v5_file_sha256(_m4_verify_td_basin_storage_v5_PRIMARY_PATH) != _m4_verify_td_basin_storage_v5_PRIMARY_SHA256 or _m4_verify_td_basin_storage_v5_file_sha256(threshold_storage_HIERARCHY) != threshold_storage_HIERARCHY_SHA256:
        raise ValueError("input changed")
    if any(_m4_verify_td_basin_storage_v5_file_sha256(symmetric_forcing_ROOT / name) != sha for name, sha in code.items()):
        raise ValueError("frozen execution source changed")
    report = {"schema": "td-v5-full-domain-refinement-v1", "scope": "entire baseline calculation domain",
              "comparisons": comparisons, "runs": results, "elapsed_s": _m4_verify_td_basin_storage_v5_time.perf_counter() - start,
              "all_numerical_gates_passed": all(item["gate_passed"] for item in comparisons.values()),
              "hydraulic_ready": False, "publishable": False, "transient_converged": False,
              "next_repair_if_failed": "Separate runoff/rain wet-mask partition time error from face splitting via frozen hourly partition and diagnostic forcing replay on the maximal-error catchment; maintain same g/rain and gate.",
              "old_packages_unchanged": True, "execution_sha256": _m4_verify_td_basin_storage_v5_file_sha256(destination / "execution-code.json")}
    symmetric_forcing_write(destination / "report.json", report)
    print(_m4_verify_td_basin_storage_v5_json.dumps({"output": str(destination), "report_sha256": _m4_verify_td_basin_storage_v5_file_sha256(destination / "report.json"),
                      "gates": report["all_numerical_gates_passed"]}), flush=True)

def run_symmetric_forcing_cli():
    symmetric_forcing_verify(symmetric_forcing_ROOT / "verification/td-basin-generation" / ("A-storage-v5-full-" + _m4_verify_td_basin_storage_v5_datetime.now(_m4_verify_td_basin_storage_v5_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")))

# --- tools/verify_td_basin_storage_v6.py:10 ---
symmetric_ssprk2_ROOT = _m4_verify_td_basin_storage_v6_Path(__file__).resolve().parents[1]

# --- tools/verify_td_basin_storage_v6.py:11 ---
_m4_verify_td_basin_storage_v6_sys.path.insert(0, str(symmetric_ssprk2_ROOT))

# --- tools/verify_td_basin_storage_v6.py:29 ---
def symmetric_ssprk2_write(path, record):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_basin_storage_v6_publish_bytes
    _m4_verify_td_basin_storage_v6_publish_bytes(path, _m4_verify_td_basin_storage_v6_json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))

# --- tools/verify_td_basin_storage_v6.py:33 ---
def symmetric_ssprk2_compare(coarse, fine):
    difference = abs(coarse["depth_m"] - fine["depth_m"])
    step, cell = _m4_verify_td_basin_storage_v6_np.unravel_index(_m4_verify_td_basin_storage_v6_np.argmax(difference), difference.shape)
    receiver_error = float(abs(coarse["routed_volume_m3"] - fine["routed_volume_m3"]).sum() /
                           max(1e-12, fine["routed_volume_m3"].sum()))
    head_error = float(difference[step, cell])
    diagnostics = {}
    for name in ("lake_rain_m3", "land_rain_m3", "local_release_m3", "internal_net_m3", "surface_et_m3"):
        delta = coarse[name][:step].sum(axis=0) - fine[name][:step].sum(axis=0)
        diagnostics[name] = {"at_max_depth_cell_m3": float(delta[cell]), "global_l1_m3": float(abs(delta).sum())}
    for name in ("soil_mm", "fast_mm", "slow_mm"):
        diagnostics[name] = {"at_max_depth_cell_mm": float(coarse[name][step, cell] - fine[name][step, cell]),
                             "max_saved_difference_mm": float(abs(coarse[name] - fine[name]).max())}
    return {"max_saved_depth_difference_m": head_error, "receiver_volume_relative_l1": receiver_error,
            "depth_gate_m": .001, "receiver_gate": .01, "gate_passed": head_error <= .001 and receiver_error <= .01,
            "max_difference_step": int(step), "max_difference_cell": int(cell),
            "max_difference_zx": list(map(int, divmod(cell, coarse["height_m"].shape[1]))),
            "coarse_depth_m": float(coarse["depth_m"][step, cell]), "fine_depth_m": float(fine["depth_m"][step, cell]),
            "forcing_partition_and_exchange_diagnostics": diagnostics,
            "failure_reason": None if head_error <= .001 and receiver_error <= .01 else "full-domain saved transient difference exceeds fixed gate"}

# --- tools/verify_td_basin_storage_v6.py:55 ---
def symmetric_ssprk2_verify(destination):
    from terrain_pipeline.basin_storage import PRIMARY_PATH as _m4_verify_td_basin_storage_v6_PRIMARY_PATH
    from terrain_pipeline.basin_storage import PRIMARY_SHA256 as _m4_verify_td_basin_storage_v6_PRIMARY_SHA256
    from terrain_pipeline.basin_storage import SYMMETRIC_SSPRK2_PROFILE as _m4_verify_td_basin_storage_v6_PROFILE
    from terrain_pipeline.basin_storage import storagev6_load_storage as _m4_verify_td_basin_storage_v6_load_basin_storage
    from terrain_pipeline.basin_storage import storagev6_save_storage as _m4_verify_td_basin_storage_v6_save_basin_storage
    from terrain_pipeline.basin_storage import storagev6_simulate as _m4_verify_td_basin_storage_v6_simulate_basin_storage
    from terrain_pipeline.basin_storage import validate_cfl as _m4_verify_td_basin_storage_v6_validate_cfl
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_basin_storage_v6_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_v6_file_sha256
    from tools.audit_td_basin_generation import audit_storage as _m4_verify_td_basin_storage_v6_audit_storage
    from tools.audit_td_basin_generation import read_saved as _m4_verify_td_basin_storage_v6_read_saved
    destination = _m4_verify_td_basin_storage_v6_Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if _m4_verify_td_basin_storage_v6_file_sha256(_m4_verify_td_basin_storage_v6_PRIMARY_PATH) != _m4_verify_td_basin_storage_v6_PRIMARY_SHA256:
        raise ValueError("primary source changed")
    code_names = ('terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'tools/verify_basin_storage.py',
                  "tools/audit_td_basin_generation.py", 'terrain_pipeline/runoff.py',
                  'terrain_pipeline/common_infra.py', 'terrain_pipeline/basin_topology.py',
                  'terrain_pipeline/basin_storage.py', 'tools/verify_basin_storage.py', 'terrain_pipeline/basin_storage.py')
    code = {name: _m4_verify_td_basin_storage_v6_file_sha256(symmetric_ssprk2_ROOT / name) for name in code_names}
    hierarchy = _m4_verify_td_basin_storage_v6_load_basin_hierarchy(threshold_storage_HIERARCHY, expected_sha256=threshold_storage_HIERARCHY_SHA256, expected_identity=threshold_storage_HIERARCHY_IDENTITY)
    cells = hierarchy["arrays"]["height_m"].size
    faces = len(hierarchy["arrays"]["face_cells"])
    topology = hierarchy["arrays"]
    spacing = hierarchy["metadata"]["spacing_m"]
    boundary = topology["boundary_cells"]
    rows, columns = _m4_verify_td_basin_storage_v6_np.divmod(boundary, topology["height_m"].shape[1])
    widths = spacing * ((rows == 0).astype(int) + (rows == topology["height_m"].shape[0] - 1)
                        + (columns == 0) + (columns == topology["height_m"].shape[1] - 1))
    cfl = {str(step): _m4_verify_td_basin_storage_v6_validate_cfl(topology["face_cells"], boundary, widths, spacing, step, .6, cells)
           for step in (5., 2.5)}
    inputs = {"primary": {"path": str(_m4_verify_td_basin_storage_v6_PRIMARY_PATH), "sha256": _m4_verify_td_basin_storage_v6_PRIMARY_SHA256},
              "hierarchy": {"path": str(threshold_storage_HIERARCHY), "sha256": threshold_storage_HIERARCHY_SHA256, "identity": threshold_storage_HIERARCHY_IDENTITY},
              "source_identity": hierarchy["metadata"]["source_identity_sha256"],
              "forcing": "24 hourly states; first6 ordinary10mm/h or strong30mm/h; remaining18 zero",
              "initial_state": "depth0; frozen default RunoffParameters soil/fast/slow; identical across refinements",
              "steps_s": [5., 2.5], "face_conductance_m_s": .6, "wet_threshold_m": 1e-9,
              "profile": _m4_verify_td_basin_storage_v6_PROFILE, "max_work_face_steps": 6000000000, "job_memory_budget_bytes": 1073741824,
              "work_by_step": {str(step): int(86400 / step * faces) for step in (5., 2.5)},
              "saved_cells_time": 24 * cells, "code_sha256": code}
    inputs["positivity_cfl_by_step"] = cfl
    inputs["v5_strong_reference"] = {"path": str(symmetric_ssprk2_ROOT / "verification/td-basin-generation/A-storage-v5-full-20261002T094535898252Z/strong-comparison.json"),
                                     "max_saved_depth_difference_m": .036112752799497105, "gate_passed": False}
    symmetric_ssprk2_write(destination / "run-inputs.json", inputs)
    execution = {"schema": "td-v6-execution-code-v1", "profile": _m4_verify_td_basin_storage_v6_PROFILE, "numba": _m4_verify_td_basin_storage_v6_version("numba"),
                 "numpy": _m4_verify_td_basin_storage_v6_version("numpy"), "python": _m4_verify_td_basin_storage_v6_sys.version, "fastmath": False, "code_sha256": code,
                 "solver_source_utf8": (symmetric_ssprk2_ROOT / code_names[0]).read_text(encoding="utf-8"),
                 "cold_read": "v4 validation uses v2 parameter schema only; no import of symmetric forcing compiled v6, JIT, or advancement",
                 "v3_correctness_evidence_invalidated": True,
                 "forcing_correction": "half runoff/rain/ET, full compiled transport, half runoff/rain/ET; same g/rain/wet threshold",
                 "transport_source_utf8": (symmetric_ssprk2_ROOT / 'terrain_pipeline/basin_storage.py').read_text(encoding="utf-8")}
    symmetric_ssprk2_write(destination / "execution-code.json", execution)
    results = {}
    comparisons = {}
    process = _m4_verify_td_basin_storage_v6_psutil.Process()
    start = _m4_verify_td_basin_storage_v6_time.perf_counter()
    for scenario in ("strong", "ordinary"):
        pins = {}
        for step in (5., 2.5):
            print(f"starting {scenario} {step}s symmetric forcing compiled v6", flush=True)
            began = _m4_verify_td_basin_storage_v6_time.perf_counter()
            rain = _m4_verify_td_basin_storage_v6_np.zeros(24)
            rain[:6] = 10 if scenario == "ordinary" else 30
            result = _m4_verify_td_basin_storage_v6_simulate_basin_storage(hierarchy, rain, parameters={"substep_s": step})
            directory = destination / f"{scenario}-{step:g}s"
            path = directory / "storage.npz"
            memory = process.memory_info()
            peak = int(getattr(memory, "peak_wset", memory.rss))
            if peak > 1073741824:
                symmetric_ssprk2_write(directory / "failure.json", {"reason": "process memory exceeded declared1GiB", "peak_bytes": peak})
                raise MemoryError("v6 job budget")
            _m4_verify_td_basin_storage_v6_save_basin_storage(path, result)
            pin = {"path": str(path), "expected_sha256": _m4_verify_td_basin_storage_v6_file_sha256(path), "expected_identity": result["identity_sha256"]}
            record = threshold_storage_summary(result)
            record.update({"pin": pin, "elapsed_s": _m4_verify_td_basin_storage_v6_time.perf_counter() - began, "peak_process_bytes": peak,
                           "code_sha256": code, "profile": _m4_verify_td_basin_storage_v6_PROFILE, "hydraulic_ready": False, "publishable": False})
            symmetric_ssprk2_write(directory / "report.json", record)
            del result
            arrays, metadata = _m4_verify_td_basin_storage_v6_read_saved(path, pin["expected_sha256"])
            audit = _m4_verify_td_basin_storage_v6_audit_storage(arrays, metadata)
            symmetric_ssprk2_write(directory / "independent-audit.json", {"pin": pin, "checks": audit, "solver_advanced": False,
                  "auditor_sha256": code["tools/audit_td_basin_generation.py"], "hydraulic_ready": False})
            del arrays
            results[f"{scenario}-{step:g}s"] = record
            pins[str(step)] = pin
            print(f"complete {scenario} {step}s elapsed {record['elapsed_s']:.2f}s peak {peak}", flush=True)
        coarse = _m4_verify_td_basin_storage_v6_load_basin_storage(**pins["5.0"])
        fine = _m4_verify_td_basin_storage_v6_load_basin_storage(**pins["2.5"])
        comparisons[scenario] = {**symmetric_ssprk2_compare(coarse["arrays"], fine["arrays"]), "coarse": pins["5.0"], "fine": pins["2.5"]}
        symmetric_ssprk2_write(destination / (scenario + "-comparison.json"), comparisons[scenario])
        print(_m4_verify_td_basin_storage_v6_json.dumps({scenario: comparisons[scenario]}, ensure_ascii=True), flush=True)
        del coarse, fine
    if _m4_verify_td_basin_storage_v6_file_sha256(_m4_verify_td_basin_storage_v6_PRIMARY_PATH) != _m4_verify_td_basin_storage_v6_PRIMARY_SHA256 or _m4_verify_td_basin_storage_v6_file_sha256(threshold_storage_HIERARCHY) != threshold_storage_HIERARCHY_SHA256:
        raise ValueError("input changed")
    if any(_m4_verify_td_basin_storage_v6_file_sha256(symmetric_ssprk2_ROOT / name) != sha for name, sha in code.items()):
        raise ValueError("frozen execution source changed")
    report = {"schema": "td-v6-full-domain-refinement-v1", "scope": "entire baseline calculation domain",
              "comparisons": comparisons, "runs": results, "elapsed_s": _m4_verify_td_basin_storage_v6_time.perf_counter() - start,
              "all_numerical_gates_passed": all(item["gate_passed"] for item in comparisons.values()),
              "hydraulic_ready": False, "publishable": False, "transient_converged": False,
              "next_repair_if_failed": "Diagnose simultaneous transport versus ordered soil/wet-front time integration using saved first-error ledgers; keep conductance, rain and gates fixed.",
              "old_packages_unchanged": True, "execution_sha256": _m4_verify_td_basin_storage_v6_file_sha256(destination / "execution-code.json")}
    symmetric_ssprk2_write(destination / "report.json", report)
    print(_m4_verify_td_basin_storage_v6_json.dumps({"output": str(destination), "report_sha256": _m4_verify_td_basin_storage_v6_file_sha256(destination / "report.json"),
                      "gates": report["all_numerical_gates_passed"]}), flush=True)

def run_symmetric_ssprk2_cli():
    symmetric_ssprk2_verify(symmetric_ssprk2_ROOT / "verification/td-basin-generation" / ("A-storage-v6-full-" + _m4_verify_td_basin_storage_v6_datetime.now(_m4_verify_td_basin_storage_v6_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")))

# --- tools/verify_td_basin_storage_v7.py:10 ---
compensated_ssprk2_ROOT = _m4_verify_td_basin_storage_v7_Path(__file__).resolve().parents[1]

# --- tools/verify_td_basin_storage_v7.py:11 ---
_m4_verify_td_basin_storage_v7_sys.path.insert(0, str(compensated_ssprk2_ROOT))

# --- tools/verify_td_basin_storage_v7.py:29 ---
def compensated_ssprk2_write(path, record):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_basin_storage_v7_publish_bytes
    _m4_verify_td_basin_storage_v7_publish_bytes(path, _m4_verify_td_basin_storage_v7_json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))

# --- tools/verify_td_basin_storage_v7.py:33 ---
def compensated_ssprk2_compare(coarse, fine):
    difference = abs(coarse["depth_m"] - fine["depth_m"])
    step, cell = _m4_verify_td_basin_storage_v7_np.unravel_index(_m4_verify_td_basin_storage_v7_np.argmax(difference), difference.shape)
    receiver_error = float(abs(coarse["routed_volume_m3"] - fine["routed_volume_m3"]).sum() /
                           max(1e-12, fine["routed_volume_m3"].sum()))
    head_error = float(difference[step, cell])
    diagnostics = {}
    for name in ("lake_rain_m3", "land_rain_m3", "local_release_m3", "internal_net_m3", "surface_et_m3"):
        delta = coarse[name][:step].sum(axis=0) - fine[name][:step].sum(axis=0)
        diagnostics[name] = {"at_max_depth_cell_m3": float(delta[cell]), "global_l1_m3": float(abs(delta).sum())}
    for name in ("soil_mm", "fast_mm", "slow_mm"):
        diagnostics[name] = {"at_max_depth_cell_mm": float(coarse[name][step, cell] - fine[name][step, cell]),
                             "max_saved_difference_mm": float(abs(coarse[name] - fine[name]).max())}
    return {"max_saved_depth_difference_m": head_error, "receiver_volume_relative_l1": receiver_error,
            "depth_gate_m": .001, "receiver_gate": .01, "gate_passed": head_error <= .001 and receiver_error <= .01,
            "max_difference_step": int(step), "max_difference_cell": int(cell),
            "max_difference_zx": list(map(int, divmod(cell, coarse["height_m"].shape[1]))),
            "coarse_depth_m": float(coarse["depth_m"][step, cell]), "fine_depth_m": float(fine["depth_m"][step, cell]),
            "forcing_partition_and_exchange_diagnostics": diagnostics,
            "failure_reason": None if head_error <= .001 and receiver_error <= .01 else "full-domain saved transient difference exceeds fixed gate"}

# --- tools/verify_td_basin_storage_v7.py:55 ---
def compensated_ssprk2_verify(destination):
    from terrain_pipeline.basin_storage import COMPENSATED_SSPRK2_PROFILE as _m4_verify_td_basin_storage_v7_PROFILE
    from terrain_pipeline.basin_storage import PRIMARY_PATH as _m4_verify_td_basin_storage_v7_PRIMARY_PATH
    from terrain_pipeline.basin_storage import PRIMARY_SHA256 as _m4_verify_td_basin_storage_v7_PRIMARY_SHA256
    from terrain_pipeline.basin_storage import storagev7_load_storage as _m4_verify_td_basin_storage_v7_load_basin_storage
    from terrain_pipeline.basin_storage import storagev7_save_storage as _m4_verify_td_basin_storage_v7_save_basin_storage
    from terrain_pipeline.basin_storage import storagev7_simulate as _m4_verify_td_basin_storage_v7_simulate_basin_storage
    from terrain_pipeline.basin_storage import validate_cfl as _m4_verify_td_basin_storage_v7_validate_cfl
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_basin_storage_v7_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_v7_file_sha256
    from tools.audit_td_basin_generation import audit_storage as _m4_verify_td_basin_storage_v7_audit_storage
    from tools.audit_td_basin_generation import read_saved as _m4_verify_td_basin_storage_v7_read_saved
    destination = _m4_verify_td_basin_storage_v7_Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if _m4_verify_td_basin_storage_v7_file_sha256(_m4_verify_td_basin_storage_v7_PRIMARY_PATH) != _m4_verify_td_basin_storage_v7_PRIMARY_SHA256:
        raise ValueError("primary source changed")
    code_names = ('terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'tools/verify_basin_storage.py',
                  "tools/audit_td_basin_generation.py", 'terrain_pipeline/runoff.py',
                  'terrain_pipeline/common_infra.py', 'terrain_pipeline/basin_topology.py',
                  'terrain_pipeline/basin_storage.py', 'tools/verify_basin_storage.py', 'terrain_pipeline/basin_storage.py')
    code = {name: _m4_verify_td_basin_storage_v7_file_sha256(compensated_ssprk2_ROOT / name) for name in code_names}
    hierarchy = _m4_verify_td_basin_storage_v7_load_basin_hierarchy(threshold_storage_HIERARCHY, expected_sha256=threshold_storage_HIERARCHY_SHA256, expected_identity=threshold_storage_HIERARCHY_IDENTITY)
    cells = hierarchy["arrays"]["height_m"].size
    faces = len(hierarchy["arrays"]["face_cells"])
    topology = hierarchy["arrays"]
    spacing = hierarchy["metadata"]["spacing_m"]
    boundary = topology["boundary_cells"]
    rows, columns = _m4_verify_td_basin_storage_v7_np.divmod(boundary, topology["height_m"].shape[1])
    widths = spacing * ((rows == 0).astype(int) + (rows == topology["height_m"].shape[0] - 1)
                        + (columns == 0) + (columns == topology["height_m"].shape[1] - 1))
    cfl = {str(step): _m4_verify_td_basin_storage_v7_validate_cfl(topology["face_cells"], boundary, widths, spacing, step, .6, cells)
           for step in (5., 2.5)}
    inputs = {"primary": {"path": str(_m4_verify_td_basin_storage_v7_PRIMARY_PATH), "sha256": _m4_verify_td_basin_storage_v7_PRIMARY_SHA256},
              "hierarchy": {"path": str(threshold_storage_HIERARCHY), "sha256": threshold_storage_HIERARCHY_SHA256, "identity": threshold_storage_HIERARCHY_IDENTITY},
              "source_identity": hierarchy["metadata"]["source_identity_sha256"],
              "forcing": "24 hourly states; first6 ordinary10mm/h or strong30mm/h; remaining18 zero",
              "initial_state": "depth0; frozen default RunoffParameters soil/fast/slow; identical across refinements",
              "steps_s": [5., 2.5], "face_conductance_m_s": .6, "wet_threshold_m": 1e-9,
              "profile": _m4_verify_td_basin_storage_v7_PROFILE, "max_work_face_steps": 6000000000, "job_memory_budget_bytes": 1073741824,
              "work_by_step": {str(step): int(86400 / step * faces) for step in (5., 2.5)},
              "saved_cells_time": 24 * cells, "code_sha256": code}
    inputs["positivity_cfl_by_step"] = cfl
    inputs["v5_strong_reference"] = {"path": str(compensated_ssprk2_ROOT / "verification/td-basin-generation/A-storage-v5-full-20261002T094535898252Z/strong-comparison.json"),
                                     "max_saved_depth_difference_m": .036112752799497105, "gate_passed": False}
    compensated_ssprk2_write(destination / "run-inputs.json", inputs)
    execution = {"schema": "td-v7-execution-code-v1", "profile": _m4_verify_td_basin_storage_v7_PROFILE, "numba": _m4_verify_td_basin_storage_v7_version("numba"),
                 "numpy": _m4_verify_td_basin_storage_v7_version("numpy"), "python": _m4_verify_td_basin_storage_v7_sys.version, "fastmath": False, "code_sha256": code,
                 "solver_source_utf8": (compensated_ssprk2_ROOT / code_names[0]).read_text(encoding="utf-8"),
                 "cold_read": "v4 validation uses v2 parameter schema only; no import of symmetric forcing compiled v7, JIT, or advancement",
                 "v3_correctness_evidence_invalidated": True,
                 "forcing_correction": "half runoff/rain/ET, full compiled transport, half runoff/rain/ET; same g/rain/wet threshold",
                 "transport_source_utf8": (compensated_ssprk2_ROOT / 'terrain_pipeline/basin_storage.py').read_text(encoding="utf-8")}
    compensated_ssprk2_write(destination / "execution-code.json", execution)
    results = {}
    comparisons = {}
    process = _m4_verify_td_basin_storage_v7_psutil.Process()
    start = _m4_verify_td_basin_storage_v7_time.perf_counter()
    for scenario in ("strong", "ordinary"):
        pins = {}
        for step in (5., 2.5):
            print(f"starting {scenario} {step}s symmetric forcing compiled v7", flush=True)
            began = _m4_verify_td_basin_storage_v7_time.perf_counter()
            rain = _m4_verify_td_basin_storage_v7_np.zeros(24)
            rain[:6] = 10 if scenario == "ordinary" else 30
            result = _m4_verify_td_basin_storage_v7_simulate_basin_storage(hierarchy, rain, parameters={"substep_s": step})
            directory = destination / f"{scenario}-{step:g}s"
            path = directory / "storage.npz"
            memory = process.memory_info()
            peak = int(getattr(memory, "peak_wset", memory.rss))
            if peak > 1073741824:
                compensated_ssprk2_write(directory / "failure.json", {"reason": "process memory exceeded declared1GiB", "peak_bytes": peak})
                raise MemoryError("v6 job budget")
            _m4_verify_td_basin_storage_v7_save_basin_storage(path, result)
            pin = {"path": str(path), "expected_sha256": _m4_verify_td_basin_storage_v7_file_sha256(path), "expected_identity": result["identity_sha256"]}
            record = threshold_storage_summary(result)
            record.update({"pin": pin, "elapsed_s": _m4_verify_td_basin_storage_v7_time.perf_counter() - began, "peak_process_bytes": peak,
                           "code_sha256": code, "profile": _m4_verify_td_basin_storage_v7_PROFILE, "hydraulic_ready": False, "publishable": False})
            compensated_ssprk2_write(directory / "report.json", record)
            del result
            arrays, metadata = _m4_verify_td_basin_storage_v7_read_saved(path, pin["expected_sha256"])
            audit = _m4_verify_td_basin_storage_v7_audit_storage(arrays, metadata)
            compensated_ssprk2_write(directory / "independent-audit.json", {"pin": pin, "checks": audit, "solver_advanced": False,
                  "auditor_sha256": code["tools/audit_td_basin_generation.py"], "hydraulic_ready": False})
            del arrays
            results[f"{scenario}-{step:g}s"] = record
            pins[str(step)] = pin
            print(f"complete {scenario} {step}s elapsed {record['elapsed_s']:.2f}s peak {peak}", flush=True)
        coarse = _m4_verify_td_basin_storage_v7_load_basin_storage(**pins["5.0"])
        fine = _m4_verify_td_basin_storage_v7_load_basin_storage(**pins["2.5"])
        comparisons[scenario] = {**compensated_ssprk2_compare(coarse["arrays"], fine["arrays"]), "coarse": pins["5.0"], "fine": pins["2.5"]}
        compensated_ssprk2_write(destination / (scenario + "-comparison.json"), comparisons[scenario])
        print(_m4_verify_td_basin_storage_v7_json.dumps({scenario: comparisons[scenario]}, ensure_ascii=True), flush=True)
        del coarse, fine
    if _m4_verify_td_basin_storage_v7_file_sha256(_m4_verify_td_basin_storage_v7_PRIMARY_PATH) != _m4_verify_td_basin_storage_v7_PRIMARY_SHA256 or _m4_verify_td_basin_storage_v7_file_sha256(threshold_storage_HIERARCHY) != threshold_storage_HIERARCHY_SHA256:
        raise ValueError("input changed")
    if any(_m4_verify_td_basin_storage_v7_file_sha256(compensated_ssprk2_ROOT / name) != sha for name, sha in code.items()):
        raise ValueError("frozen execution source changed")
    report = {"schema": "td-v7-full-domain-refinement-v1", "scope": "entire baseline calculation domain",
              "comparisons": comparisons, "runs": results, "elapsed_s": _m4_verify_td_basin_storage_v7_time.perf_counter() - start,
              "all_numerical_gates_passed": all(item["gate_passed"] for item in comparisons.values()),
              "hydraulic_ready": False, "publishable": False, "transient_converged": False,
              "next_repair_if_failed": "Diagnose simultaneous transport versus ordered soil/wet-front time integration using saved first-error ledgers; keep conductance, rain and gates fixed.",
              "old_packages_unchanged": True, "execution_sha256": _m4_verify_td_basin_storage_v7_file_sha256(destination / "execution-code.json")}
    compensated_ssprk2_write(destination / "report.json", report)
    print(_m4_verify_td_basin_storage_v7_json.dumps({"output": str(destination), "report_sha256": _m4_verify_td_basin_storage_v7_file_sha256(destination / "report.json"),
                      "gates": report["all_numerical_gates_passed"]}), flush=True)

def run_compensated_ssprk2_cli():
    compensated_ssprk2_verify(compensated_ssprk2_ROOT / "verification/td-basin-generation" / ("A-storage-v7-full-" + _m4_verify_td_basin_storage_v7_datetime.now(_m4_verify_td_basin_storage_v7_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")))

# --- tools/verify_td_basin_storage_v7_first_hour.py:10 ---
compensated_first_hour_ROOT = _m4_verify_td_basin_storage_v7_first_hour_Path(__file__).resolve().parents[1]

# --- tools/verify_td_basin_storage_v7_first_hour.py:11 ---
_m4_verify_td_basin_storage_v7_first_hour_sys.path.insert(0, str(compensated_first_hour_ROOT))

# --- tools/verify_td_basin_storage_v7_first_hour.py:29 ---
def compensated_first_hour_write(path, record):
    from terrain_pipeline.common_infra import publish_bytes as _m4_verify_td_basin_storage_v7_first_hour_publish_bytes
    _m4_verify_td_basin_storage_v7_first_hour_publish_bytes(path, _m4_verify_td_basin_storage_v7_first_hour_json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))

# --- tools/verify_td_basin_storage_v7_first_hour.py:33 ---
def compensated_first_hour_compare(coarse, fine):
    difference = abs(coarse["depth_m"] - fine["depth_m"])
    step, cell = _m4_verify_td_basin_storage_v7_first_hour_np.unravel_index(_m4_verify_td_basin_storage_v7_first_hour_np.argmax(difference), difference.shape)
    receiver_error = float(abs(coarse["routed_volume_m3"] - fine["routed_volume_m3"]).sum() /
                           max(1e-12, fine["routed_volume_m3"].sum()))
    head_error = float(difference[step, cell])
    diagnostics = {}
    for name in ("lake_rain_m3", "land_rain_m3", "local_release_m3", "internal_net_m3", "surface_et_m3"):
        delta = coarse[name][:step].sum(axis=0) - fine[name][:step].sum(axis=0)
        diagnostics[name] = {"at_max_depth_cell_m3": float(delta[cell]), "global_l1_m3": float(abs(delta).sum())}
    for name in ("soil_mm", "fast_mm", "slow_mm"):
        diagnostics[name] = {"at_max_depth_cell_mm": float(coarse[name][step, cell] - fine[name][step, cell]),
                             "max_saved_difference_mm": float(abs(coarse[name] - fine[name]).max())}
    return {"max_saved_depth_difference_m": head_error, "receiver_volume_relative_l1": receiver_error,
            "depth_gate_m": .001, "receiver_gate": .01, "gate_passed": head_error <= .001 and receiver_error <= .01,
            "max_difference_step": int(step), "max_difference_cell": int(cell),
            "max_difference_zx": list(map(int, divmod(cell, coarse["height_m"].shape[1]))),
            "coarse_depth_m": float(coarse["depth_m"][step, cell]), "fine_depth_m": float(fine["depth_m"][step, cell]),
            "forcing_partition_and_exchange_diagnostics": diagnostics,
            "failure_reason": None if head_error <= .001 and receiver_error <= .01 else "full-domain saved transient difference exceeds fixed gate"}

# --- tools/verify_td_basin_storage_v7_first_hour.py:55 ---
def compensated_first_hour_verify(destination):
    from terrain_pipeline.basin_storage import COMPENSATED_SSPRK2_PROFILE as _m4_verify_td_basin_storage_v7_first_hour_PROFILE
    from terrain_pipeline.basin_storage import PRIMARY_PATH as _m4_verify_td_basin_storage_v7_first_hour_PRIMARY_PATH
    from terrain_pipeline.basin_storage import PRIMARY_SHA256 as _m4_verify_td_basin_storage_v7_first_hour_PRIMARY_SHA256
    from terrain_pipeline.basin_storage import storagev7_load_storage as _m4_verify_td_basin_storage_v7_first_hour_load_basin_storage
    from terrain_pipeline.basin_storage import storagev7_save_storage as _m4_verify_td_basin_storage_v7_first_hour_save_basin_storage
    from terrain_pipeline.basin_storage import storagev7_simulate as _m4_verify_td_basin_storage_v7_first_hour_simulate_basin_storage
    from terrain_pipeline.basin_storage import validate_cfl as _m4_verify_td_basin_storage_v7_first_hour_validate_cfl
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _m4_verify_td_basin_storage_v7_first_hour_load_basin_hierarchy
    from terrain_pipeline.common_infra import file_sha256 as _m4_verify_td_basin_storage_v7_first_hour_file_sha256
    from tools.audit_td_basin_generation import audit_storage as _m4_verify_td_basin_storage_v7_first_hour_audit_storage
    from tools.audit_td_basin_generation import read_saved as _m4_verify_td_basin_storage_v7_first_hour_read_saved
    destination = _m4_verify_td_basin_storage_v7_first_hour_Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if _m4_verify_td_basin_storage_v7_first_hour_file_sha256(_m4_verify_td_basin_storage_v7_first_hour_PRIMARY_PATH) != _m4_verify_td_basin_storage_v7_first_hour_PRIMARY_SHA256:
        raise ValueError("primary source changed")
    code_names = ('terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                  'terrain_pipeline/basin_storage.py', 'tools/verify_basin_storage.py',
                  "tools/audit_td_basin_generation.py", 'terrain_pipeline/runoff.py',
                  'terrain_pipeline/common_infra.py', 'terrain_pipeline/basin_topology.py',
                  'terrain_pipeline/basin_storage.py', 'tools/verify_basin_storage.py', 'terrain_pipeline/basin_storage.py')
    code = {name: _m4_verify_td_basin_storage_v7_first_hour_file_sha256(compensated_first_hour_ROOT / name) for name in code_names}
    hierarchy = _m4_verify_td_basin_storage_v7_first_hour_load_basin_hierarchy(threshold_storage_HIERARCHY, expected_sha256=threshold_storage_HIERARCHY_SHA256, expected_identity=threshold_storage_HIERARCHY_IDENTITY)
    cells = hierarchy["arrays"]["height_m"].size
    faces = len(hierarchy["arrays"]["face_cells"])
    topology = hierarchy["arrays"]
    spacing = hierarchy["metadata"]["spacing_m"]
    boundary = topology["boundary_cells"]
    rows, columns = _m4_verify_td_basin_storage_v7_first_hour_np.divmod(boundary, topology["height_m"].shape[1])
    widths = spacing * ((rows == 0).astype(int) + (rows == topology["height_m"].shape[0] - 1)
                        + (columns == 0) + (columns == topology["height_m"].shape[1] - 1))
    cfl = {str(step): _m4_verify_td_basin_storage_v7_first_hour_validate_cfl(topology["face_cells"], boundary, widths, spacing, step, .6, cells)
           for step in (5., 2.5, 1.25, .625)}
    inputs = {"primary": {"path": str(_m4_verify_td_basin_storage_v7_first_hour_PRIMARY_PATH), "sha256": _m4_verify_td_basin_storage_v7_first_hour_PRIMARY_SHA256},
              "hierarchy": {"path": str(threshold_storage_HIERARCHY), "sha256": threshold_storage_HIERARCHY_SHA256, "identity": threshold_storage_HIERARCHY_IDENTITY},
              "source_identity": hierarchy["metadata"]["source_identity_sha256"],
              "forcing": "one hour strong30mm/h; original full TD; identical zero initial depth and default soil/fast/slow",
              "initial_state": "depth0; frozen default RunoffParameters soil/fast/slow; identical across refinements",
              "steps_s": [5., 2.5, 1.25, .625], "face_conductance_m_s": .6, "wet_threshold_m": 1e-9,
              "profile": _m4_verify_td_basin_storage_v7_first_hour_PROFILE, "max_work_face_steps": 6000000000, "job_memory_budget_bytes": 1073741824,
              "work_by_step": {str(step): int(3600 / step * faces) for step in (5., 2.5, 1.25, .625)},
              "saved_cells_time": cells, "code_sha256": code}
    inputs["positivity_cfl_by_step"] = cfl
    inputs["v5_strong_reference"] = {"path": str(compensated_first_hour_ROOT / "verification/td-basin-generation/A-storage-v5-full-20261002T094535898252Z/strong-comparison.json"),
                                     "max_saved_depth_difference_m": .036112752799497105, "gate_passed": False}
    compensated_first_hour_write(destination / "run-inputs.json", inputs)
    execution = {"schema": "td-v7-execution-code-v1", "profile": _m4_verify_td_basin_storage_v7_first_hour_PROFILE, "numba": _m4_verify_td_basin_storage_v7_first_hour_version("numba"),
                 "numpy": _m4_verify_td_basin_storage_v7_first_hour_version("numpy"), "python": _m4_verify_td_basin_storage_v7_first_hour_sys.version, "fastmath": False, "code_sha256": code,
                 "solver_source_utf8": (compensated_first_hour_ROOT / code_names[0]).read_text(encoding="utf-8"),
                 "cold_read": "v4 validation uses v2 parameter schema only; no import of symmetric forcing compiled v7, JIT, or advancement",
                 "v3_correctness_evidence_invalidated": True,
                 "forcing_correction": "half runoff/rain/ET, full compiled transport, half runoff/rain/ET; same g/rain/wet threshold",
                 "transport_source_utf8": (compensated_first_hour_ROOT / 'terrain_pipeline/basin_storage.py').read_text(encoding="utf-8")}
    compensated_first_hour_write(destination / "execution-code.json", execution)
    results = {}
    comparisons = {}
    process = _m4_verify_td_basin_storage_v7_first_hour_psutil.Process()
    start = _m4_verify_td_basin_storage_v7_first_hour_time.perf_counter()
    for scenario in ("strong",):
        pins = {}
        for step in (5., 2.5, 1.25, .625):
            print(f"starting {scenario} {step}s symmetric forcing compiled v7", flush=True)
            began = _m4_verify_td_basin_storage_v7_first_hour_time.perf_counter()
            rain = _m4_verify_td_basin_storage_v7_first_hour_np.array([30.])
            result = _m4_verify_td_basin_storage_v7_first_hour_simulate_basin_storage(hierarchy, rain, parameters={"substep_s": step})
            directory = destination / f"{scenario}-{step:g}s"
            path = directory / "storage.npz"
            memory = process.memory_info()
            peak = int(getattr(memory, "peak_wset", memory.rss))
            if peak > 1073741824:
                compensated_first_hour_write(directory / "failure.json", {"reason": "process memory exceeded declared1GiB", "peak_bytes": peak})
                raise MemoryError("v7 first-hour job budget")
            _m4_verify_td_basin_storage_v7_first_hour_save_basin_storage(path, result)
            pin = {"path": str(path), "expected_sha256": _m4_verify_td_basin_storage_v7_first_hour_file_sha256(path), "expected_identity": result["identity_sha256"]}
            record = threshold_storage_summary(result)
            record.update({"pin": pin, "elapsed_s": _m4_verify_td_basin_storage_v7_first_hour_time.perf_counter() - began, "peak_process_bytes": peak,
                           "code_sha256": code, "profile": _m4_verify_td_basin_storage_v7_first_hour_PROFILE, "hydraulic_ready": False, "publishable": False})
            compensated_first_hour_write(directory / "report.json", record)
            del result
            arrays, metadata = _m4_verify_td_basin_storage_v7_first_hour_read_saved(path, pin["expected_sha256"])
            audit = _m4_verify_td_basin_storage_v7_first_hour_audit_storage(arrays, metadata)
            compensated_first_hour_write(directory / "independent-audit.json", {"pin": pin, "checks": audit, "solver_advanced": False,
                  "auditor_sha256": code["tools/audit_td_basin_generation.py"], "hydraulic_ready": False})
            del arrays
            results[f"{scenario}-{step:g}s"] = record
            pins[str(step)] = pin
            print(f"complete {scenario} {step}s elapsed {record['elapsed_s']:.2f}s peak {peak}", flush=True)
        for coarse_step, fine_step in ((5.,2.5),(2.5,1.25),(1.25,.625)):
            coarse = _m4_verify_td_basin_storage_v7_first_hour_load_basin_storage(**pins[str(coarse_step)])
            fine = _m4_verify_td_basin_storage_v7_first_hour_load_basin_storage(**pins[str(fine_step)])
            label = f"strong-{coarse_step:g}-{fine_step:g}"
            comparisons[label] = {**compensated_first_hour_compare(coarse["arrays"],fine["arrays"]),"coarse":pins[str(coarse_step)],"fine":pins[str(fine_step)]}
            compensated_first_hour_write(destination/(label+"-comparison.json"),comparisons[label])
            print(_m4_verify_td_basin_storage_v7_first_hour_json.dumps({label:comparisons[label]},ensure_ascii=True),flush=True)
            del coarse,fine
    if _m4_verify_td_basin_storage_v7_first_hour_file_sha256(_m4_verify_td_basin_storage_v7_first_hour_PRIMARY_PATH) != _m4_verify_td_basin_storage_v7_first_hour_PRIMARY_SHA256 or _m4_verify_td_basin_storage_v7_first_hour_file_sha256(threshold_storage_HIERARCHY) != threshold_storage_HIERARCHY_SHA256:
        raise ValueError("input changed")
    if any(_m4_verify_td_basin_storage_v7_first_hour_file_sha256(compensated_first_hour_ROOT / name) != sha for name, sha in code.items()):
        raise ValueError("frozen execution source changed")
    report = {"schema": "td-v7-first-hour-refinement-v1", "scope": "entire original TD domain, first hour only; not 24h certification",
              "comparisons": comparisons, "runs": results, "elapsed_s": _m4_verify_td_basin_storage_v7_first_hour_time.perf_counter() - start,
              "all_numerical_gates_passed": all(item["gate_passed"] for item in comparisons.values()),
              "hydraulic_ready": False, "publishable": False, "transient_converged": False,
              "next_repair_if_failed": "Diagnose simultaneous transport versus ordered soil/wet-front time integration using saved first-error ledgers; keep conductance, rain and gates fixed.",
              "old_packages_unchanged": True, "execution_sha256": _m4_verify_td_basin_storage_v7_first_hour_file_sha256(destination / "execution-code.json")}
    compensated_first_hour_write(destination / "report.json", report)
    print(_m4_verify_td_basin_storage_v7_first_hour_json.dumps({"output": str(destination), "report_sha256": _m4_verify_td_basin_storage_v7_first_hour_file_sha256(destination / "report.json"),
                      "gates": report["all_numerical_gates_passed"]}), flush=True)

def run_compensated_first_hour_cli():
    compensated_first_hour_verify(compensated_first_hour_ROOT / "verification/td-basin-generation" / ("A-storage-v7-first-hour-" + _m4_verify_td_basin_storage_v7_first_hour_datetime.now(_m4_verify_td_basin_storage_v7_first_hour_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")))

PROFILES = {
    'threshold_storage': run_threshold_storage_cli,
    'threshold_pair': run_threshold_pair_cli,
    'threshold_matching': run_threshold_matching_cli,
    'symmetric_forcing': run_symmetric_forcing_cli,
    'symmetric_ssprk2': run_symmetric_ssprk2_cli,
    'compensated_ssprk2': run_compensated_ssprk2_cli,
    'compensated_first_hour': run_compensated_first_hour_cli,
}

def main(argv=None):
    """Select a preserved M4 validator; remaining options go to that validator."""
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=tuple(PROFILES),default=next(iter(PROFILES)))
    selected,remaining=parser.parse_known_args(argv)
    previous=_m4_tail_sys.argv
    try:
        _m4_tail_sys.argv=[previous[0],*remaining]
        return PROFILES[selected.profile]()
    finally:
        _m4_tail_sys.argv=previous

if __name__ == '__main__':
    main()
