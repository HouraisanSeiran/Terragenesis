"""Stream pinned hourly states, checkpoints and whole-period refinement evidence."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes, identity
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_basin_generation import audit_storage

STATES = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
FLUXES = ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s",
          "routed_volume_m3", "wet_duration_s")


def audit_scenario(comparison_path, expected_sha256, *, selected_step_s=None, scenario_name=None):
    path = Path(comparison_path).resolve()
    if file_sha256(path) != expected_sha256:
        raise ValueError("external continuation comparison pin mismatch")
    record = json.loads(path.read_text(encoding="utf-8"))
    groups = record["pages"]
    steps = sorted((float(value) for value in groups), reverse=True)
    if len(steps) != 2 or steps[0] != 2 * steps[1]:
        raise ValueError("continuation refinement must exactly halve two fixed steps")
    if selected_step_s is not None:
        if selected_step_s not in steps:
            raise ValueError("selected audit step is not in declared comparison")
        steps = [selected_step_s]
    run_root = path.parent
    inputs = json.loads((run_root / "run-inputs.json").read_text(encoding="utf-8"))
    hierarchy_record = inputs["hierarchy"]
    topology, hierarchy_metadata = read_record({"path": hierarchy_record["path"],
        "expected_sha256": hierarchy_record["sha256"], "expected_identity": hierarchy_record["identity"]})
    scenario = path.name.removesuffix("-comparison.json") if scenario_name is None else scenario_name
    if Path(scenario).name != scenario or scenario in (".", ".."):
        raise ValueError("invalid scenario name")
    forcing = json.loads((run_root / (scenario + "-forcing.json")).read_text(encoding="utf-8"))
    rain = np.asarray(forcing["rain_mm_h"], dtype=np.float64)
    forcing_identity = identity({"rain_mm_h": rain}, {"dt_s": forcing["dt_s"]})
    if (forcing_identity != forcing["identity"] or rain.shape != (24,) or
            forcing["dt_s"] != 3600 or not np.isfinite(rain).all() or np.any(rain < 0)):
        raise ValueError("independent full forcing identity/coverage mismatch")
    faces = len(topology["face_cells"])
    final = {}
    series = {}
    case_budgets = {}
    physical_config = None
    for step in steps:
        pages = groups[str(step)]
        if len(pages) != 24 or [page["hour"] for page in pages] != list(range(24)):
            raise ValueError("continuation hourly coverage/order mismatch")
        previous = None
        cumulative = None
        saved_depth = []
        audit_summaries = []
        initial_water = None
        all_rain = []
        all_losses = []
        all_exports = []
        for hour, page in enumerate(pages):
            for role in ("storage", "checkpoint"):
                artifact = Path(page[role]["path"]).resolve(strict=True)
                if not artifact.is_relative_to(run_root) or artifact.is_symlink():
                    raise ValueError("continuation artifact escapes fixed run")
            arrays, metadata = read_record(page["storage"])
            checkpoint, checkpoint_metadata = read_record(page["checkpoint"])
            for field in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
                np.testing.assert_array_equal(arrays[field], topology[field])
            if metadata["hierarchy_identity_sha256"] != hierarchy_record["identity"] or metadata["spacing_m"] != hierarchy_metadata["spacing_m"]:
                raise ValueError("continuation original TD input chain mismatch")
            if (metadata["algorithm"] != "D4-threshold-checkpoint-SSPRK2-v8" or
                    metadata["substep_s"] != step or metadata["dt_s"] != forcing["dt_s"] or
                    metadata["chunk_start_s"] != hour * forcing["dt_s"] or
                    metadata["chunk_end_s"] != (hour + 1) * forcing["dt_s"] or
                    metadata["forcing_hour_offset"] != hour or
                    forcing["dt_s"] / step != int(forcing["dt_s"] / step) or
                    type(metadata["substeps"]) is not int or
                    metadata["substeps"] != int(forcing["dt_s"] / step) or
                    arrays["rain_mm_h"].shape != (1, topology["height_m"].size)):
                raise ValueError("continuation global saved time/version mismatch")
            np.testing.assert_array_equal(arrays["rain_mm_h"][0, topology["valid_mask"].ravel()], rain[hour])
            np.testing.assert_array_equal(arrays["rain_mm_h"][0, ~topology["valid_mask"].ravel()], 0)
            for field in STATES:
                if previous is not None:
                    np.testing.assert_array_equal(arrays[field][0], previous[field])
                np.testing.assert_array_equal(arrays[field][-1], checkpoint[field])
                np.testing.assert_array_equal(checkpoint[field][~topology["valid_mask"].ravel()], 0)
            for field in ("parameters", "runoff_parameters", "hierarchy_identity_sha256", "substep_s", "dt_s"):
                if checkpoint_metadata[field] != metadata[field]:
                    raise ValueError("continuation checkpoint configuration differs from page")
            current_config = {
                "parameters": {name: value for name, value in metadata["parameters"].items() if name != "substep_s"},
                "runoff_parameters": metadata["runoff_parameters"]}
            if physical_config is None:
                physical_config = current_config
            elif current_config != physical_config:
                raise ValueError("continuation refinement changes physical parameters")
            if hour == 0:
                if np.any(arrays["depth_m"][0] != 0):
                    raise ValueError("continuation changed declared initial surface water")
                runoff = metadata["runoff_parameters"]
                for field, parameter in (("soil_mm", "initial_soil_mm"), ("fast_mm", "initial_fast_mm"), ("slow_mm", "initial_slow_mm")):
                    np.testing.assert_array_equal(arrays[field][0], np.where(topology["valid_mask"].ravel(), runoff[parameter], 0))
                cumulative = {field: np.zeros_like(arrays[field]) for field in FLUXES}
                saved_depth.append(arrays["depth_m"][0].copy())
            for field in FLUXES:
                cumulative[field] += arrays[field]
                np.testing.assert_array_equal(checkpoint["cumulative_" + field], cumulative[field])
            count = (hour + 1) * int(forcing["dt_s"] / step)
            if (checkpoint_metadata["elapsed_s"] != (hour + 1) * forcing["dt_s"] or
                    checkpoint_metadata["substeps"] != count or checkpoint_metadata["work_face_steps"] != count * faces or
                    checkpoint_metadata["last_page_storage_identity"] != page["storage"]["expected_identity"] or
                    checkpoint_metadata["forcing_identity"] != forcing_identity or metadata["forcing_identity"] != forcing_identity):
                raise ValueError("continuation checkpoint state/time/work link mismatch")
            if arrays["rain_mm_h"].shape[0] * int(forcing["dt_s"] / step) * faces > 6_000_000_000:
                raise ValueError("continuation chunk exceeded original work cap")
            for flags in (metadata, checkpoint_metadata):
                if flags["hydraulic_ready"] is not False or flags["transient_converged"] is not False:
                    raise ValueError("continuation page asserts unsupported certification")
            budget_audit = audit_storage(arrays, metadata)
            if initial_water is None:
                initial_water = budget_audit["initial_water_m3"]
            all_rain.extend(item["rain_m3"] for item in budget_audit["budgets"])
            all_losses.extend(item["loss_m3"] for item in budget_audit["budgets"])
            all_exports.extend(item["external_m3"] for item in budget_audit["budgets"])
            audit_summaries.append(budget_audit)
            saved_depth.append(arrays["depth_m"][-1].copy())
            previous = checkpoint
            del arrays, metadata
        final[step] = cumulative
        series[step] = np.asarray(saved_depth)
        rain_total = math.fsum(all_rain)
        residual = math.fsum([initial_water, rain_total, -math.fsum(all_losses),
                              -math.fsum(all_exports), -audit_summaries[-1]["final_water_m3"]])
        allowed = 1e-6 + rain_total * 1e-10
        if abs(residual) > allowed:
            raise ValueError("continuation whole-period cumulative water budget failed")
        case_budgets[str(step)] = {"hours": audit_summaries, "whole_period_residual_m3": residual,
                                  "whole_period_allowed_m3": allowed, "whole_period_passed": True}
    memory = psutil.Process().memory_info()
    peak_rss = int(getattr(memory, "peak_wset", memory.rss))
    peak_private = getattr(memory, "peak_pagefile", None)
    if max(peak_rss, peak_private or 0) > 1073741824:
        raise MemoryError("independent continuation audit exceeds 1GiB")
    resource = {"peak_rss_bytes": peak_rss, "peak_private_bytes": peak_private,
                "within_1GiB": peak_private is not None}
    if selected_step_s is not None:
        return {"schema": "td-independent-single-series-continuation-v1", "scenario": scenario,
                "comparison_path": str(path), "comparison_sha256": expected_sha256,
                "substeps_s": steps, "saved_frames": 25, "page_budget_audits": case_budgets,
                "checkpoint_chain_checked": True, "resource": resource, "refinement_checked": False,
                "solver_advanced": False, "hydraulic_ready": False,
                "auditor_sha256": file_sha256(__file__)}
    difference = abs(series[steps[0]] - series[steps[1]])
    frame, cell = np.unravel_index(np.argmax(difference), difference.shape)
    receiver = float(abs(final[steps[0]]["routed_volume_m3"] - final[steps[1]]["routed_volume_m3"]).sum() /
                     max(1e-12, final[steps[1]]["routed_volume_m3"].sum()))
    passed = float(difference.max()) <= .001 and receiver <= .01
    if (abs(record["max_saved_depth_difference_m"] - float(difference.max())) > 1e-12 or
            abs(record["cumulative_receiver_relative_l1"] - receiver) > 1e-12 or record["gate_passed"] != passed):
        raise ValueError("published continuation refinement differs from independent reduction")
    return {"schema": "td-independent-streaming-continuation-v1", "scenario": scenario,
            "comparison_path": str(path), "comparison_sha256": expected_sha256,
            "substeps_s": steps, "saved_frames": 25, "max_saved_depth_difference_m": float(difference.max()),
            "max_frame": int(frame), "max_cell": int(cell), "cumulative_receiver_relative_l1": receiver,
            "gate_passed": passed, "page_budget_audits": case_budgets, "checkpoint_chain_checked": True,
            "resource": resource,
            "total_work_per_step": {str(step): 24 * int(forcing["dt_s"] / step) * faces for step in steps},
            "auditor_sha256": file_sha256(__file__), "solver_advanced": False, "hydraulic_ready": False,
            "limitations": "Original TD hourly saved-frame and cumulative receiver refinement only; no measured physics, natural outlets or meter-scale river channels."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    report = audit_scenario(args.comparison, args.expected_sha256)
    output = ROOT / "verification/td-basin-generation" / ("independent-continuation-" +
             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({"output": str(output), "gate_passed": report["gate_passed"],
                      "depth_difference_m": report["max_saved_depth_difference_m"],
                      "receiver_relative_l1": report["cumulative_receiver_relative_l1"]}))
