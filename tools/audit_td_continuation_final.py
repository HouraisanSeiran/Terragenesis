"""Explicit final v8 cold acceptance plus independent numerical reductions."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_storage import PRIMARY_PATH as PRIMARY_PATH
from terrain_pipeline.basin_storage import PRIMARY_SHA256 as PRIMARY_SHA256
from terrain_pipeline.td_hour_pages_acceptance_io import load_hour_pages_index
from terrain_pipeline.td_surface_reaches import _plain
from tools.audit_td_storage_continuation import audit_scenario


def json_record(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "expected_sha256": file_sha256(path)}


def accept(run, index_sha256, resource_record):
    run = Path(run).resolve(strict=True)
    index_path = run / "index.json"
    if file_sha256(index_path) != index_sha256:
        raise ValueError("final index external pin mismatch")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    inputs_record = json_record(run / "run-inputs.json")
    inputs = json.loads(Path(inputs_record["path"]).read_text(encoding="utf-8"))
    hierarchy = inputs["hierarchy"]
    forcing_records = {}
    for scenario in ("ordinary", "strong"):
        record = json_record(run / (scenario + "-forcing.json"))
        record["expected_identity"] = json.loads(Path(record["path"]).read_text(encoding="utf-8"))["identity"]
        forcing_records[scenario] = record
    arguments = {"expected_sha256": index_sha256, "forcing_records": forcing_records,
                 "run_inputs_record": inputs_record, "hierarchy_record": {
                     "path": hierarchy["path"], "expected_sha256": hierarchy["sha256"],
                     "expected_identity": hierarchy["identity"]},
                 "execution_resource_record": resource_record, "declared_steps_s": (2.5, 1.25),
                 "code_root": str(ROOT)}
    accepted = load_hour_pages_index(index_path, **arguments)
    numerical_reports = {}
    comparison_records = {}
    for scenario in ("ordinary", "strong"):
        comparison_path = run / (scenario + "-comparison.json")
        pin = json_record(comparison_path)
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        if comparison != index["scenarios"][scenario]:
            raise ValueError("standalone comparison differs from externally pinned final index")
        report = audit_scenario(comparison_path, pin["expected_sha256"])
        published = accepted["scenarios"][scenario]
        if (report["max_saved_depth_difference_m"] != published["depth_difference_m"] or
                report["cumulative_receiver_relative_l1"] != published["receiver_relative_l1"] or
                report["gate_passed"] is not published["numerical_gate_passed"]):
            raise ValueError("independent reductions differ from final cold acceptance")
        numerical_reports[scenario] = report
        comparison_records[scenario] = pin
    for record in [inputs_record, resource_record, *forcing_records.values(), *comparison_records.values()]:
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("pinned final audit inputs changed during acceptance")
    if (file_sha256(index_path) != index_sha256 or file_sha256(hierarchy["path"]) != hierarchy["sha256"] or
            file_sha256(PRIMARY_PATH) != PRIMARY_SHA256 or
            any(file_sha256(ROOT / name) != digest for name, digest in inputs["code_sha256"].items())):
        raise ValueError("frozen final source or execution dependencies changed")
    numerical_passed = all(report["gate_passed"] for report in numerical_reports.values())
    return {"schema": "td-independent-final-continuation-acceptance-v1", "input_index": str(index_path),
            "input_index_sha256": index_sha256, "acceptance_arguments": arguments,
            "cold_acceptance": _plain(accepted), "numerical_reports": numerical_reports,
            "comparison_records": comparison_records, "all_saved_numerical_gates_passed": numerical_passed,
            "original_inputs_and_frozen_code_unchanged": True,
            "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
            "auditor_sha256": file_sha256(__file__),
            "limitations": "Saved hourly temporal refinement and storage accounting only; no spatial refinement, real channel geometry, momentum calibration or natural outlet certification."}


def write_result(result):
    output = ROOT / "verification/td-basin-generation" / ("independent-final-continuation-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    records = {}
    for scenario, report in result["numerical_reports"].items():
        path = output / (scenario + "-report.json")
        publish_bytes(path, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
        records[scenario] = json_record(path)
    summary = {name: value for name, value in result.items() if name != "numerical_reports"}
    summary["numerical_reports"] = records
    index_path = output / "acceptance-index.json"
    publish_bytes(index_path, json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    publish_bytes(output / "final-pin.json", json.dumps(json_record(index_path), indent=2).encode())
    return index_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--resource", type=Path, required=True)
    parser.add_argument("--resource-sha256", required=True)
    args = parser.parse_args()
    resource = {"path": str(args.resource.resolve(strict=True)), "expected_sha256": args.resource_sha256}
    result = accept(args.run, args.index_sha256, resource)
    path = write_result(result)
    print(json.dumps({"output": str(path), "sha256": file_sha256(path),
                      "all_saved_numerical_gates_passed": result["all_saved_numerical_gates_passed"]}))
