"""Recompute saved TD refinement gates without advancing the simulation."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_basin_generation import audit_storage, read_saved


def audit_sensitivity(directory, report_sha256, output):
    directory = Path(directory).resolve(strict=True)
    if file_sha256(directory / "report.json") != report_sha256:
        raise ValueError("external sensitivity report pin mismatch")
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    settings = json.loads((directory / "sensitivity-inputs.json").read_text(encoding="utf-8"))
    original, original_metadata = read_saved(
        ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz",
        settings["source_hierarchy_sha256"])
    row_start, row_stop, column_start, column_stop = settings["crop"]
    window = np.s_[row_start:row_stop, column_start:column_stop]
    parent = original["node_parent"]
    selected = settings["selected_node"]
    descendants = np.zeros(len(parent), bool)
    for node in range(len(parent)):
        ancestor = node
        while ancestor >= 0 and ancestor != selected:
            ancestor = int(parent[ancestor])
        descendants[node] = ancestor == selected
    covered = original["valid_mask"] & descendants[np.maximum(0, original["cell_owner"])]
    comparisons = {}
    audits = {}
    for scenario, saved in report["scenarios"].items():
        previous = None
        scenario_comparisons = []
        scenario_audits = []
        for index, record in enumerate(saved["runs"]):
            candidates = [path for path in directory.glob(scenario + "-*.npz")
                          if file_sha256(path) == record["archive_sha256"]]
            if len(candidates) != 1:
                raise ValueError("sensitivity run archive missing or ambiguous")
            arrays, metadata = read_saved(candidates[0], record["archive_sha256"])
            np.testing.assert_array_equal(arrays["valid_mask"], covered[window])
            np.testing.assert_array_equal(arrays["height_m"][arrays["valid_mask"]], original["height_m"][window][arrays["valid_mask"]])
            if len(arrays["boundary_cells"]):
                raise ValueError("sealed sensitivity basin has external boundary")
            if metadata["substep_s"] != record["substep_s"]:
                raise ValueError("saved refinement timestep mismatch")
            check = audit_storage(arrays, metadata)
            scenario_audits.append({"archive_sha256": record["archive_sha256"], "substep_s": metadata["substep_s"],
                                    "max_step_global_residual_m3": check["max_step_global_residual_m3"],
                                    "whole_water_budget_passed": True})
            snapshot = {name: arrays[name].copy() for name in ("depth_m", "routed_volume_m3", "face_forward_m3", "face_reverse_m3")}
            if previous is not None:
                depth_error = float(np.max(abs(previous["depth_m"] - snapshot["depth_m"])))
                volume_error = float(np.sum(abs(previous["routed_volume_m3"] - snapshot["routed_volume_m3"])) / max(1e-12, snapshot["routed_volume_m3"].sum()))
                gates = settings["declared_gates"]
                gate_passed = depth_error <= gates["head_max_difference_m"] and volume_error <= gates["receiver_volume_relative_l1"]
                expected = saved["comparisons"][index - 1]
                if abs(depth_error - expected["max_saved_depth_difference_m"]) > 1e-12 or abs(volume_error - expected["receiver_volume_relative_l1"]) > 1e-12 or gate_passed != expected["gate_passed"]:
                    raise ValueError("reported sensitivity gate differs from independent arrays")
                scenario_comparisons.append({"substeps_s": expected["substeps_s"], "max_depth_difference_m": depth_error,
                                             "receiver_relative_l1": volume_error, "passed": gate_passed})
            previous = snapshot
            del arrays
        comparisons[scenario] = scenario_comparisons
        audits[scenario] = scenario_audits
    result = {"schema": "td-basin-independent-sensitivity-audit-v1", "utc": datetime.now(timezone.utc).isoformat(),
              "directory": str(directory), "report_sha256": report_sha256,
              "settings_sha256": file_sha256(directory / "sensitivity-inputs.json"),
              "auditor_sha256": file_sha256(__file__), "subtree_node": selected,
              "original_subtree_cells": int(covered.sum()), "comparisons": comparisons, "water_audits": audits,
              "local_all_gates_passed": all(item["passed"] for values in comparisons.values() for item in values),
              "full_domain_transient_converged": False,
              "scope": "complete original merge subtree, artificial closed divide, no external inflow; saved-array checks only"}
    publish_bytes(output, json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_sensitivity(args.directory, args.report_sha256, args.output)
    print(json.dumps(report["comparisons"]))


if __name__ == "__main__":
    main()
