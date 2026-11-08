"""Independent saved-array execution equivalence on externally pinned v9 probes."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_basin_generation import audit_storage
from tools.publish_td_accepted_review import accepted_inputs


def compare_fields(actual, expected):
    if set(actual) != set(expected):
        raise ValueError("execution changes saved field coverage")
    differences = {}
    for name, values in actual.items():
        reference = expected[name]
        if values.shape != reference.shape or values.dtype != reference.dtype:
            raise ValueError("execution changes field shape/dtype")
        if not np.isfinite(values).all() or not np.isfinite(reference).all():
            raise ValueError("nonfinite saved execution evidence")
        difference = np.abs(values.astype(float) - reference.astype(float))
        maximum = float(difference.max(initial=0))
        if name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells", "boundary_width_m", "rain_mm_h") or values.dtype.kind in "biu":
            passed = np.array_equal(values, reference)
        elif "duration" in name or name.startswith("active_"):
            passed = maximum <= 1e-8
        elif name in ("soil_mm", "fast_mm", "slow_mm", "error_soil", "error_fast", "error_slow"):
            passed = maximum <= 1e-9
        elif name == "depth_m" or name.startswith("error_"):
            passed = maximum <= 1e-12
        else:
            passed = bool(np.all(difference <= 1e-6 + 1e-10 * (np.abs(values) + np.abs(reference))))
        if not passed:
            raise ValueError("independent execution equivalence failed for " + name)
        differences[name] = dict(max_difference=maximum, bit_equal=bool(np.array_equal(values, reference)))
    return differences


def audit(report_path, expected_sha256, acceptance_path, acceptance_sha256):
    report_path = Path(report_path).resolve(strict=True)
    if file_sha256(report_path) != expected_sha256:
        raise ValueError("external compiled probe report pin mismatch")
    accepted = accepted_inputs(acceptance_path, acceptance_sha256)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    inputs = json.loads((report_path.parent / "run-inputs.json").read_text(encoding="utf-8"))
    if (inputs["external_acceptance"]["sha256"] != acceptance_sha256 or
            Path(inputs["external_acceptance"]["path"]).resolve() != Path(acceptance_path).resolve() or
            inputs["reference_index_sha256"] != accepted["input_index_sha256"] or report["all_passed"] is not True):
        raise ValueError("probe does not bind independent continuation acceptance")
    baseline = json.loads(Path(accepted["input_index"]).read_text(encoding="utf-8"))
    stage_probe = "hours only" in inputs["scope"]
    expected_labels = {"5-2.5", "5-1.25", "23-2.5", "23-1.25"} if stage_probe else {"2.5", "1.25"}
    if set(inputs["references"]) != expected_labels or set(report["runs"]) != expected_labels:
        raise ValueError("compiled probe temporal/step coverage mismatch")
    results = {}
    for label, reference in inputs["references"].items():
        hour, step = (reference["hour"], reference["step"]) if stage_probe else (0, float(label))
        expected_page = baseline["scenarios"]["strong"]["pages"][str(step)][hour]
        folder = report_path.parent / (f"strong-hour{hour + 1}-{step:g}s" if stage_probe else f"strong-{step:g}s")
        stored_report = report["runs"][label]
        resources = stored_report["resource"]
        if any(type(resources.get(name)) is not int or not 0 < resources[name] <= 1073741824
               for name in ("peak_rss_bytes", "peak_private_bytes")):
            raise ValueError("compiled probe resource evidence missing/excessive")
        fields = {}
        for role in ("storage", "checkpoint"):
            if reference["report"][role] != expected_page[role]:
                raise ValueError("probe reference differs from independently accepted original page")
            actual_record = dict(path=str(folder / (role + ".npz")),
                expected_sha256=stored_report[role + "_sha256"], expected_identity=stored_report[role + "_identity"])
            actual, actual_metadata = read_record(actual_record)
            expected, expected_metadata = read_record(expected_page[role])
            fields[role] = compare_fields(actual, expected)
            if role == "storage":
                if (actual_metadata["algorithm"] != "D4-threshold-compiled-hour-SSPRK2-v9" or
                        actual_metadata["work_profile"] != inputs["profile"]):
                    raise ValueError("unexpected compiled execution identity")
                for name in ("chunk_start_s", "chunk_end_s", "forcing_identity", "parameters", "runoff_parameters", "substeps", "substep_s"):
                    if actual_metadata[name] != expected_metadata[name]:
                        raise ValueError("compiled execution changes physical storage metadata")
                water = audit_storage(actual, actual_metadata)
                if stage_probe:
                    previous, unused = read_record(reference["previous_checkpoint"])
                    if reference["previous_checkpoint"] != baseline["scenarios"]["strong"]["pages"][str(step)][hour - 1]["checkpoint"]:
                        raise ValueError("probe start checkpoint differs from accepted previous page")
                    for name in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
                        np.testing.assert_array_equal(actual[name][0], previous[name])
            else:
                if actual_metadata["execution_profile"] != inputs["profile"]:
                    raise ValueError("compiled checkpoint profile mismatch")
                for name in ("elapsed_s", "substeps", "work_face_steps", "forcing_identity", "parameters", "runoff_parameters"):
                    if actual_metadata[name] != expected_metadata[name]:
                        raise ValueError("compiled execution changes checkpoint time/physical configuration")
        results[label] = dict(hour=hour, step_s=step, fields=fields, water_audit=water,
                             elapsed_s=stored_report["elapsed_s"], reference_elapsed_s=stored_report["reference_elapsed_s"])
    if file_sha256(report_path) != expected_sha256 or file_sha256(acceptance_path) != acceptance_sha256:
        raise ValueError("independent execution audit inputs changed")
    info = psutil.Process().memory_info()
    resource = dict(peak_rss_bytes=int(getattr(info, "peak_wset", info.rss)),
                    peak_private_bytes=getattr(info, "peak_pagefile", None))
    if resource["peak_private_bytes"] is None or max(resource.values()) > 1073741824:
        raise MemoryError("independent compiled audit requires bounded RSS/private evidence")
    return dict(schema="td-independent-compiled-probes-v1", input_report=str(report_path),
        input_sha256=expected_sha256, acceptance_sha256=acceptance_sha256, all_saved_execution_fields_passed=True,
        results=results, resource=resource, scenario="strong", full_day_execution_checked=False,
        solver_advanced=False, hydraulic_ready=False, publishable=False, auditor_sha256=file_sha256(__file__))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--acceptance-sha256", required=True)
    args = parser.parse_args()
    result = audit(args.report, args.report_sha256, args.acceptance, args.acceptance_sha256)
    output = ROOT / "verification/td-basin-generation" / ("independent-compiled-probes-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(result, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(output), sha256=file_sha256(output)), ensure_ascii=False))
