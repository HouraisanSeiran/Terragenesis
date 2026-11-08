"""Pinned completed-hour diagnostics; never treat a prefix as full refinement."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record


def audit(run, scenario):
    run = Path(run).resolve(strict=True)
    if scenario not in ("ordinary", "strong"):
        raise ValueError("explicit declared rain scenario required")
    inputs_path = run / "run-inputs.json"
    inputs_sha = file_sha256(inputs_path)
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    steps = inputs["steps_s"]
    if steps != [2.5, 1.25]:
        raise ValueError("declared v8 exact step pair required")
    frames = []
    for hour in range(24):
        report_paths = [run / f"{scenario}-{step:g}s" / f"hour-{hour:02d}" / "report.json" for step in steps]
        if not all(path.is_file() for path in report_paths):
            break
        pinned_reports = []
        arrays = []
        metadata = []
        for step, path in zip(steps, report_paths):
            digest = file_sha256(path)
            report = json.loads(path.read_text(encoding="utf-8"))
            if report["hour"] != hour:
                raise ValueError("prefix hour order differs from declared layout")
            saved, header = read_record(report["storage"])
            if (header["substep_s"] != step or header["chunk_start_s"] != hour * 3600 or
                    header["chunk_end_s"] != (hour + 1) * 3600 or
                    header["hierarchy_identity_sha256"] != inputs["hierarchy"]["identity"]):
                raise ValueError("prefix step/time/source mismatch")
            pinned_reports.append({"path": str(path), "sha256": digest, "storage": report["storage"]})
            arrays.append(saved)
            metadata.append(header)
        for name in ("height_m", "valid_mask", "face_cells", "receiver", "rain_mm_h"):
            np.testing.assert_array_equal(arrays[0][name], arrays[1][name])
        for name in ("parameters", "runoff_parameters"):
            first = {key: value for key, value in metadata[0][name].items() if key != "substep_s"}
            second = {key: value for key, value in metadata[1][name].items() if key != "substep_s"}
            if first != second:
                raise ValueError("prefix physical parameters differ")
        difference = abs(arrays[0]["depth_m"][-1] - arrays[1]["depth_m"][-1])
        frames.append({"frame": hour + 1, "time_s": (hour + 1) * 3600,
                       "max_depth_difference_m": float(difference.max()), "max_cell": int(np.argmax(difference)),
                       "cells_over_1mm": int(np.count_nonzero(difference > .001)),
                       "input_reports": pinned_reports})
        del arrays
    if not frames:
        raise ValueError("no common saved hours to diagnose")
    if file_sha256(inputs_path) != inputs_sha:
        raise ValueError("prefix run declaration changed during audit")
    return {"schema": "td-independent-refinement-prefix-v1", "scenario": scenario,
            "run": str(run), "run_inputs_sha256": inputs_sha, "common_saved_hours": len(frames),
            "frames": frames, "prefix_max_depth_difference_m": max(frame["max_depth_difference_m"] for frame in frames),
            "complete_refinement_checked": False, "whole_period_budget_checked": False,
            "hydraulic_ready": False, "solver_advanced": False, "auditor_sha256": file_sha256(__file__)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--scenario", choices=("ordinary", "strong"), required=True)
    arguments = parser.parse_args()
    result = audit(arguments.run, arguments.scenario)
    output = ROOT / "verification/td-basin-generation" / ("independent-refinement-prefix-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(result, indent=2, allow_nan=False).encode())
    print(json.dumps({"output": str(output), "hours": result["common_saved_hours"], "difference_m": result["prefix_max_depth_difference_m"], "complete_refinement_checked": False}))
