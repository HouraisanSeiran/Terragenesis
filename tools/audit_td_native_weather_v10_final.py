"""Bind complete v10 cold IO to independently reduced numerical evidence."""

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
from terrain_pipeline.td_native_weather_storage_v10_io import load_native_weather_storage_v10_index


def pinned_json(record):
    path = Path(record["path"]).resolve(strict=True)
    if path.stat().st_size > 8 * 1024 * 1024 or file_sha256(path) != record["expected_sha256"]:
        raise ValueError("v10 final external JSON pin/budget mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def bind_numerical(index, inputs, run, records, cold):
    if set(records) != {"eastward", "westward"}:
        raise ValueError("v10 final needs both independent directional reports")
    summaries = {}
    for direction, pin in records.items():
        report = pinned_json(pin)
        path = run / (direction + "-comparison.json")
        comparison = pinned_json(dict(path=str(path), expected_sha256=file_sha256(path)))
        if (report.get("schema") != "td-independent-spatial-weather-v10-v1" or
                report.get("comparison_path") != str(path) or report.get("comparison_sha256") != file_sha256(path) or
                report.get("weather_record") != inputs["weather_records"][direction] or
                report.get("hierarchy_record") != inputs["hierarchy"] or
                report.get("forcing_identity") != inputs["forcing_identities"][direction] or
                report.get("substeps_s") != [2.5, 1.25] or report.get("saved_frames") != 25 or
                comparison != index["scenarios"][direction]):
            raise ValueError("v10 final independent report does not bind execution")
        for name in ("full_spatial_rain_checked", "compartment_ledgers_checked", "checkpoint_chain_checked"):
            if report.get(name) is not True:
                raise ValueError("v10 final independent physical/chain audit missing")
        if report.get("solver_advanced") is not False:
            raise ValueError("v10 final requires read-only independent evidence")
        if any(report.get(name) is not False for name in ("hydraulic_ready", "natural_outlet_verified", "publishable")):
            raise ValueError("v10 final unsupported independent readiness flags")
        if set(report["page_budget_audits"]) != {"2.5", "1.25"}:
            raise ValueError("v10 final both period budget audits required")
        if any(item.get("whole_period_passed") is not True for item in report["page_budget_audits"].values()):
            raise ValueError("v10 final complete period budgets missing")
        for name in ("max_saved_depth_difference_m", "cumulative_receiver_relative_l1", "gate_passed"):
            if report[name] != comparison[name]:
                raise ValueError("v10 final independent reduction disagreement")
        if report["gate_passed"] is not cold["cases"][direction]["numerical_gate_passed"]:
            raise ValueError("v10 final cold numerical gate disagreement")
        summaries[direction] = dict(record=pin, max_saved_depth_difference_m=report["max_saved_depth_difference_m"],
                                    cumulative_receiver_relative_l1=report["cumulative_receiver_relative_l1"],
                                    gate_passed=report["gate_passed"], max_frame=report["max_frame"], max_cell=report["max_cell"])
    return summaries


def accept(run, index_sha256, resource_sha256, numerical_records):
    run = Path(run).resolve(strict=True)
    index_pin = dict(path=str(run / "index.json"), expected_sha256=index_sha256)
    resource_pin = dict(path=str(run / "resource.json"), expected_sha256=resource_sha256)
    inputs_pin = dict(path=str(run / "run-inputs.json"), expected_sha256=file_sha256(run / "run-inputs.json"))
    index, inputs = pinned_json(index_pin), pinned_json(inputs_pin)
    pinned_json(resource_pin)
    weather = inputs["weather_index"]
    weather_pin = dict(path=weather["path"], expected_sha256=weather["sha256"])
    source_pin = pinned_json(weather_pin)["source"]
    arguments = dict(expected_sha256=index_sha256, weather_index_record=weather_pin,
                     hierarchy_record=inputs["hierarchy"], source_record=source_pin, run_inputs_record=inputs_pin,
                     execution_resource_record=resource_pin, code_root=str(ROOT))
    cold = load_native_weather_storage_v10_index(run / "index.json", **arguments)
    reports = bind_numerical(index, inputs, run, numerical_records, cold)
    pins = [index_pin, resource_pin, inputs_pin, weather_pin, source_pin, inputs["hierarchy"], *numerical_records.values()]
    if any(file_sha256(pin["path"]) != pin["expected_sha256"] for pin in pins) or file_sha256(PRIMARY_PATH) != PRIMARY_SHA256:
        raise ValueError("v10 final frozen input/report changed")
    if any(file_sha256(ROOT / name) != digest for name, digest in inputs["code_sha256"].items()):
        raise ValueError("v10 final frozen execution code changed")
    return dict(schema="td-independent-final-spatial-weather-v10-v1", index_path=str(run / "index.json"),
                index_sha256=index_sha256, resource_sha256=resource_sha256, acceptance_arguments=arguments,
                cold_acceptance=cold, numerical_reports=reports, io_chain_accepted=True,
                all_saved_numerical_gates_passed=all(item["gate_passed"] for item in reports.values()),
                original_inputs_and_frozen_code_unchanged=True, solver_advanced=False,
                hydraulic_ready=False, natural_outlet_verified=False, publishable=False, auditor_sha256=file_sha256(__file__),
                limitations="New forcing hypothesis; temporal and accounting acceptance does not establish natural outlets, spatial convergence or 3D channels.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--resource-sha256", required=True)
    for direction in ("eastward", "westward"):
        parser.add_argument("--" + direction + "-audit", type=Path, required=True)
        parser.add_argument("--" + direction + "-audit-sha256", required=True)
    args = parser.parse_args()
    result = accept(args.run, args.index_sha256, args.resource_sha256,
                    {direction:dict(path=str(getattr(args, direction + "_audit").resolve()),
                                    expected_sha256=getattr(args, direction + "_audit_sha256"))
                     for direction in ("eastward", "westward")})
    destination = ROOT / "verification/td-basin-generation" / ("independent-final-spatial-weather-v10-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "acceptance-index.json"
    publish_bytes(destination, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(destination), sha256=file_sha256(destination),
                         all_saved_numerical_gates_passed=result["all_saved_numerical_gates_passed"])))
