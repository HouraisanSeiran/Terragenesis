"""Independent whole-domain refinement gates from pinned saved arrays, without solving."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_basin_generation import audit_storage
from tools.audit_td_candidate_coupling import read_record


def compare(coarse_record, fine_record):
    coarse, coarse_metadata = read_record(coarse_record)
    fine, fine_metadata = read_record(fine_record)
    for field in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells", "boundary_width_m", "rain_mm_h"):
        np.testing.assert_array_equal(coarse[field], fine[field])
    for field in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
        np.testing.assert_array_equal(coarse[field][0], fine[field][0])
    for field in ("spacing_m", "origin_m_xz", "hierarchy_identity_sha256", "dt_s", "runoff_parameters", "algorithm"):
        if coarse_metadata[field] != fine_metadata[field]:
            raise ValueError("whole-domain refinement changed provenance, initial state, formula or forcing")
    for field in ("face_conductance_m_s", "surface_evaporation_mm_h", "wet_threshold_m"):
        if coarse_metadata["parameters"][field] != fine_metadata["parameters"][field]:
            raise ValueError("refinement changed a physical/partition coefficient")
    if fine_metadata["substep_s"] * 2 != coarse_metadata["substep_s"]:
        raise ValueError("refinement is not an exact timestep halving")
    audits = {"coarse": audit_storage(coarse, coarse_metadata), "fine": audit_storage(fine, fine_metadata)}
    difference = abs(coarse["depth_m"] - fine["depth_m"])
    frame, cell = np.unravel_index(np.argmax(difference), difference.shape)
    depth_error = float(difference[frame, cell])
    volumes = {}
    for field in ("routed_volume_m3", "face_forward_m3", "face_reverse_m3"):
        volumes[field] = float(abs(coarse[field] - fine[field]).sum() / max(1e-12, fine[field].sum()))
    area = coarse_metadata["spacing_m"] ** 2
    total_changes = {field: float((fine[field].sum() - coarse[field].sum())) for field in (
        "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3", "boundary_outflow_m3")}
    for field in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
        total_changes["final_" + field + "_volume_m3"] = float((fine[field][-1].sum() - coarse[field][-1].sum()) * area / (1 if field == "depth_m" else 1000))
    durations = {field: {"max_absolute_difference_s": float(abs(coarse[field] - fine[field]).max()),
                         "relative_l1": float(abs(coarse[field] - fine[field]).sum() / max(1e-12, fine[field].sum()))}
                 for field in ("wet_duration_s", "active_forward_s", "active_reverse_s")}
    return {"scope": "entire saved domain including declared engineering boundaries", "valid_cells": int(fine["valid_mask"].sum()),
            "substeps_s": [coarse_metadata["substep_s"], fine_metadata["substep_s"]],
            "coarse": coarse_record, "fine": fine_record,
            "max_saved_depth_difference_m": depth_error, "max_difference_frame": int(frame),
            "max_difference_cell": int(cell), "max_difference_time_s": int(frame) * coarse_metadata["dt_s"],
            "receiver_volume_relative_l1": volumes["routed_volume_m3"], "directional_volume_relative_l1": volumes,
            "duration_differences": durations, "whole_budget_checks": audits, "fine_minus_coarse": total_changes,
            "declared_gates": {"head_max_difference_m": .001, "receiver_volume_relative_l1": .01},
            "gate_passed": depth_error <= .001 and volumes["routed_volume_m3"] <= .01,
            "physical_calibration_verified": False, "hydraulic_ready": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--inputs-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if file_sha256(args.inputs) != args.inputs_sha256:
        raise ValueError("external refinement inputs pin mismatch")
    inputs = json.loads(args.inputs.read_text(encoding="utf-8"))
    if set(inputs) - {"candidate_id", "cases"} or set(inputs.get("cases", {})) != {"ordinary", "strong"}:
        raise ValueError("both ordinary and strong external refinement records required")
    comparisons = {}
    for scenario, records in inputs["cases"].items():
        if set(records) != {"coarse", "fine"}:
            raise ValueError("exact coarse and fine pins required")
        comparisons[scenario] = compare(records["coarse"], records["fine"])
    report = {"schema": "td-independent-full-refinement-v1", "utc": datetime.now(timezone.utc).isoformat(),
              "candidate_id": inputs.get("candidate_id", "baseline"), "input_path": str(args.inputs.resolve()),
              "input_sha256": args.inputs_sha256, "auditor_sha256": file_sha256(__file__),
              "comparisons": comparisons, "all_gates_passed": all(case["gate_passed"] for case in comparisons.values()),
              "limitations": "Numerical saved-frame halving gate for this exact grid/forcing; no momentum, measured physics or general forcing certification."}
    publish_bytes(args.output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({name: {field: case[field] for field in ("max_saved_depth_difference_m", "receiver_volume_relative_l1", "gate_passed")}
                      for name, case in comparisons.items()}))


if __name__ == "__main__":
    main()
