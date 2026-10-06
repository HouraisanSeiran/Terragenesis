"""Bind independent spatial-weather reductions to a complete frozen execution and cold IO."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256
from terrain_pipeline.td_native_weather_storage_io import load_native_weather_storage_index


def pin_json(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "expected_sha256": file_sha256(path)}


def accept(run, index_sha256, resource_sha256, numerical_records):
    run = Path(run).resolve(strict=True)
    index_path = run / "index.json"
    resource_path = run / "resource.json"
    if file_sha256(index_path) != index_sha256 or file_sha256(resource_path) != resource_sha256:
        raise ValueError("final weather execution external index/resource pins mismatch")
    inputs_pin = pin_json(run / "run-inputs.json")
    inputs = json.loads(Path(inputs_pin["path"]).read_text(encoding="utf-8"))
    index = json.loads(index_path.read_text(encoding="utf-8"))
    hierarchy = inputs["hierarchy"]
    hierarchy_pin = {"path": hierarchy["path"], "expected_sha256": hierarchy["sha256"],
                     "expected_identity": hierarchy["identity"]}
    weather = inputs["weather_index"]
    weather_path = Path(weather["path"])
    weather_pin = {"path": weather["path"], "expected_sha256": weather["sha256"]}
    weather_index = json.loads(weather_path.read_text(encoding="utf-8"))
    source_pin = weather_index["source"]
    arguments = {"expected_sha256": index_sha256, "weather_index_record": weather_pin,
        "hierarchy_record": hierarchy_pin, "source_record": source_pin, "run_inputs_record": inputs_pin,
        "execution_resource_record": {"path": str(resource_path), "expected_sha256": resource_sha256},
        "code_root": str(ROOT)}
    cold = load_native_weather_storage_index(index_path, **arguments)
    if set(numerical_records) != {"eastward", "westward"}:
        raise ValueError("both independently pinned spatial numerical reports required")
    reports = {}
    for direction in ("eastward", "westward"):
        report_pin = numerical_records[direction]
        if file_sha256(report_pin["path"]) != report_pin["expected_sha256"]:
            raise ValueError("independent spatial numerical report pin mismatch")
        report = json.loads(Path(report_pin["path"]).read_text(encoding="utf-8"))
        comparison_path = run / (direction + "-comparison.json")
        comparison_pin = pin_json(comparison_path)
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        if (report["schema"] != "td-independent-spatial-weather-continuation-v1" or
                report["comparison_path"] != str(comparison_path) or
                report["comparison_sha256"] != comparison_pin["expected_sha256"] or
                report["weather_record"] != inputs["weather_records"][direction] or
                report["hierarchy_record"] != hierarchy_pin or
                report["forcing_identity"] != inputs["forcing_identities"][direction] or
                report["substeps_s"] != [2.5, 1.25] or report["saved_frames"] != 25 or
                report["full_spatial_rain_checked"] is not True or report["checkpoint_chain_checked"] is not True or
                report["solver_advanced"] is not False or comparison != index["scenarios"][direction]):
            raise ValueError("independent spatial report does not bind final execution")
        for name in ("max_saved_depth_difference_m", "cumulative_receiver_relative_l1", "gate_passed"):
            if report[name] != comparison[name]:
                raise ValueError("independent numerical reductions disagree with final execution")
        if report["gate_passed"] is not cold["cases"][direction]["numerical_gate_passed"]:
            raise ValueError("cold numerical gate disagrees with independent audit")
        if any(budget["whole_period_passed"] is not True for budget in report["page_budget_audits"].values()):
            raise ValueError("independent whole-period spatial budget missing")
        reports[direction] = {"record": report_pin, "max_saved_depth_difference_m": report["max_saved_depth_difference_m"],
                              "cumulative_receiver_relative_l1": report["cumulative_receiver_relative_l1"],
                              "gate_passed": report["gate_passed"], "max_frame": report["max_frame"],
                              "max_cell": report["max_cell"]}
    all_pins = [inputs_pin, source_pin, hierarchy_pin, weather_pin,
                arguments["execution_resource_record"], *numerical_records.values()]
    if (file_sha256(index_path) != index_sha256 or file_sha256(PRIMARY_PATH) != PRIMARY_SHA256 or
            any(file_sha256(record["path"]) != record["expected_sha256"] for record in all_pins) or
            any(file_sha256(ROOT / name) != digest for name, digest in inputs["code_sha256"].items())):
        raise ValueError("final weather sources or frozen code changed")
    return {"schema": "td-independent-final-spatial-weather-acceptance-v1", "index_path": str(index_path),
        "index_sha256": index_sha256, "resource_sha256": resource_sha256, "acceptance_arguments": arguments,
        "cold_acceptance": cold, "numerical_reports": reports,
        "all_saved_numerical_gates_passed": all(report["gate_passed"] for report in reports.values()),
        "io_chain_accepted": True, "original_inputs_and_frozen_code_unchanged": True,
        "solver_advanced": False, "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
        "auditor_sha256": file_sha256(__file__),
        "limitations": "IO and accounting acceptance can coexist with failed temporal refinement; this record never certifies an unstable river solution."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--resource-sha256", required=True)
    parser.add_argument("--eastward-audit", type=Path, required=True)
    parser.add_argument("--eastward-audit-sha256", required=True)
    parser.add_argument("--westward-audit", type=Path, required=True)
    parser.add_argument("--westward-audit-sha256", required=True)
    args = parser.parse_args()
    report = accept(args.run, args.index_sha256, args.resource_sha256,
        {"eastward": {"path": str(args.eastward_audit.resolve()), "expected_sha256": args.eastward_audit_sha256},
         "westward": {"path": str(args.westward_audit.resolve()), "expected_sha256": args.westward_audit_sha256}})
    output = ROOT / "verification/td-basin-generation" / ("independent-final-spatial-weather-" +
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "acceptance-index.json"
    publish_bytes(output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({"path": str(output), "sha256": file_sha256(output),
                      "all_saved_numerical_gates_passed": report["all_saved_numerical_gates_passed"]}))
