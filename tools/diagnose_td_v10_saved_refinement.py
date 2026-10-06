"""Pinned saved-page attribution of v10 temporal differences; no causal replay."""

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
from tools.audit_td_native_weather_v10 import audit_accounts, close

TERMS = (("local_release_m3", 1), ("surface_infiltration_m3", -1),
         ("surface_et_m3", -1), ("internal_net_m3", 1), ("boundary_outflow_m3", -1))


def attribute(first, second, *, spacing_m, hour, top_cells=4):
    if type(top_cells) is not int or not 1 <= top_cells <= 16 or spacing_m <= 0:
        raise ValueError("saved attribution budget invalid")
    for name in ("height_m", "valid_mask", "face_cells", "receiver", "rain_mm_h"):
        np.testing.assert_array_equal(first[name], second[name])
    area = spacing_m ** 2
    difference = first["depth_m"][-1] - second["depth_m"][-1]
    inherited = first["depth_m"][0] - second["depth_m"][0]
    terms = {name: sign * (first[name][0] - second[name][0]) / area for name, sign in TERMS}
    explained = inherited + sum(terms.values())
    close(difference, explained, "saved coarse/fine difference attribution")
    cells = np.argsort(abs(difference), kind="stable")[-top_cells:][::-1]
    rows = []
    faces = first["face_cells"]
    for cell in cells:
        incident = np.flatnonzero((faces[:, 0] == cell) | (faces[:, 1] == cell))
        sign = np.where(faces[incident, 1] == cell, 1, -1)
        flux_delta = ((first["face_forward_m3"][incident] - first["face_reverse_m3"][incident]) -
                      (second["face_forward_m3"][incident] - second["face_reverse_m3"][incident]))
        contribution = sign * flux_delta / area * 1000
        rows.append(dict(cell=int(cell), coarse_depth_end_m=float(first["depth_m"][-1, cell]),
                         fine_depth_end_m=float(second["depth_m"][-1, cell]),
                         signed_depth_difference_mm=float(difference[cell] * 1000),
                         inherited_signed_difference_mm=float(inherited[cell] * 1000),
                         signed_account_contributions_mm={name:float(value[cell] * 1000) for name, value in terms.items()},
                         explanation_residual_mm=float((difference[cell] - explained[cell]) * 1000),
                         coarse_minus_fine_rain_infiltration_mm=float((first["rain_infiltration_m3"][0, cell] - second["rain_infiltration_m3"][0, cell]) / area * 1000),
                         coarse_minus_fine_soil_mm=float(first["soil_mm"][-1, cell] - second["soil_mm"][-1, cell]),
                         incident_faces=[dict(face_index=int(face), first_cell=int(faces[face, 0]), second_cell=int(faces[face, 1]),
                                              signed_contribution_mm=float(value)) for face, value in zip(incident, contribution)]))
    return dict(hour=hour, max_saved_depth_difference_mm=float(abs(difference).max() * 1000),
                numerical_depth_gate_passed=bool(abs(difference).max() <= .001),
                maximum_account_explanation_residual_mm=float(abs(difference - explained).max() * 1000),
                hotspot_rows=rows)


def diagnose(run, inputs_sha256, direction, hours):
    run = Path(run).resolve(strict=True)
    inputs_path = run / "run-inputs.json"
    if file_sha256(inputs_path) != inputs_sha256 or inputs_path.stat().st_size > 1024 ** 2:
        raise ValueError("v10 attribution input pin/budget mismatch")
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    if inputs.get("schema") != "td-v10-spatial-weather-run-inputs-v1" or inputs.get("steps_s") != [2.5, 1.25]:
        raise ValueError("v10 attribution run profile mismatch")
    if direction not in ("eastward", "westward") or type(hours) is not int or not 1 <= hours <= 24:
        raise ValueError("attribution explicit direction/hour range required")
    topology, grid = read_record(inputs["hierarchy"])
    weather, _ = read_record(inputs["weather_records"][direction])
    pins = [inputs["hierarchy"], inputs["weather_records"][direction]]
    previous = {2.5:None, 1.25:None}
    summaries = []
    for hour in range(hours):
        pages = []
        for step in (2.5, 1.25):
            report_path = run / f"{direction}-{step:g}s" / f"hour-{hour:02d}" / "report.json"
            if not report_path.is_file():
                raise ValueError("requested saved prefix is incomplete")
            report_sha = file_sha256(report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if report["hour"] != hour:
                raise ValueError("saved prefix hour identity mismatch")
            arrays, metadata = read_record(report["storage"])
            if (metadata["substep_s"] != step or metadata["start_s"] != hour * 3600 or
                    metadata["end_s"] != (hour + 1) * 3600 or
                    metadata["hierarchy_identity"] != inputs["hierarchy"]["expected_identity"] or
                    metadata["forcing_identity"] != inputs["forcing_identities"][direction]):
                raise ValueError("saved attribution source/time/profile mismatch")
            for name in ("height_m", "valid_mask", "face_cells", "receiver"):
                np.testing.assert_array_equal(arrays[name], topology[name])
            for name in ("depth_m", "soil_mm", "fast_mm", "slow_mm"):
                if previous[step] is not None:
                    np.testing.assert_array_equal(arrays[name][0], previous[step][name][-1])
            audit_accounts(arrays, grid["spacing_m"], weather["rain_mm_h"][hour])
            pins.extend((report["storage"], dict(path=str(report_path), expected_sha256=report_sha)))
            previous[step] = arrays
            pages.append(arrays)
        summaries.append(attribute(*pages, spacing_m=grid["spacing_m"], hour=hour + 1))
    if file_sha256(inputs_path) != inputs_sha256 or any(file_sha256(record["path"]) != record["expected_sha256"] for record in pins):
        raise ValueError("saved attribution evidence changed during read")
    return dict(schema="td-v10-pinned-saved-refinement-attribution-v1", direction=direction,
                explicit_hours=hours, source_run_inputs=dict(path=str(inputs_path), expected_sha256=inputs_sha256),
                source_records=pins, summaries=summaries,
                maximum_saved_depth_difference_mm=max(item["max_saved_depth_difference_mm"] for item in summaries),
                method="coarse minus fine saved end depth = inherited depth + signed release/infiltration/evaporation/divergence/export ledger differences",
                inference="ledger localization is not causal proof or a common-state replay",
                complete_run_accepted=False, resource_authenticated=False, solver_advanced=False,
                hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                scope="explicit saved direction prefix only; no full run/resource or checkpoint certification")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--inputs-sha256", required=True)
    parser.add_argument("--direction", choices=("eastward", "westward"), required=True)
    parser.add_argument("--hours", type=int, required=True)
    args = parser.parse_args()
    result = diagnose(args.run, args.inputs_sha256, args.direction, args.hours)
    destination = ROOT / "verification/td-weather-diagnostics" / ("saved-attribution-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(destination, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(destination), expected_sha256=file_sha256(destination), direction=args.direction,
                         hours=args.hours, maximum_saved_depth_difference_mm=result["maximum_saved_depth_difference_mm"])))


if __name__ == "__main__":
    main()
