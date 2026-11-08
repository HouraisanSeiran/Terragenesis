"""Independently reduce saved spatial rainfall, hourly water and checkpoint chains."""

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

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_basin_generation import audit_storage
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_native_storm import numerical_identity

STATES = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
FLUXES = ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s",
          "routed_volume_m3", "wet_duration_s")


def check_page(arrays, metadata, checkpoint, checkpoint_metadata, topology, geometry,
               rain, forcing_identity, hour, step, hierarchy_identity):
    cells = topology["height_m"].size
    faces = len(topology["face_cells"])
    for field in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
        np.testing.assert_array_equal(arrays[field], topology[field])
    if (metadata["algorithm"] != "D4-threshold-compiled-hour-SSPRK2-v9" or
            metadata["work_profile"] != "v9-compiled-hour-loop-v8-equivalent-v1" or
            metadata["dt_s"] != 3600 or metadata["substep_s"] != step or
            metadata["chunk_start_s"] != hour * 3600 or
            metadata["chunk_end_s"] != (hour + 1) * 3600 or
            type(metadata["forcing_hour_offset"]) is not int or metadata["forcing_hour_offset"] != hour or
            type(metadata["substeps"]) is not int or metadata["substeps"] != int(3600 / step) or
            metadata["hierarchy_identity_sha256"] != hierarchy_identity or
            metadata["spacing_m"] != geometry["spacing_m"] or
            metadata["origin_m_xz"] != geometry["origin_m_xz"] or
            metadata["forcing_identity"] != forcing_identity):
        raise ValueError("spatial page geometry/time/forcing profile mismatch")
    np.testing.assert_array_equal(arrays["rain_mm_h"], rain[hour:hour + 1].reshape(1, cells))
    if metadata["substeps"] * faces > 6_000_000_000:
        raise ValueError("spatial page exceeds original chunk work cap")
    for field in ("parameters", "runoff_parameters", "hierarchy_identity_sha256", "dt_s", "substep_s", "forcing_identity"):
        if checkpoint_metadata[field] != metadata[field]:
            raise ValueError("spatial checkpoint configuration mismatch")
    count = (hour + 1) * int(3600 / step)
    if (checkpoint_metadata["execution_profile"] != metadata["work_profile"] or
            checkpoint_metadata["elapsed_s"] != (hour + 1) * 3600 or
            type(checkpoint_metadata["substeps"]) is not int or checkpoint_metadata["substeps"] != count or
            type(checkpoint_metadata["work_face_steps"]) is not int or
            checkpoint_metadata["work_face_steps"] != count * faces or
            checkpoint_metadata["cells"] != cells or checkpoint_metadata["faces"] != faces):
        raise ValueError("spatial checkpoint actual time/work mismatch")
    for values in (metadata, checkpoint_metadata):
        if values["hydraulic_ready"] is not False or values["transient_converged"] is not False:
            raise ValueError("unsupported spatial water certification")
    valid = topology["valid_mask"].ravel()
    for field in STATES:
        if (arrays[field].shape != (2, cells) or checkpoint[field].shape != (cells,) or
                not np.isfinite(arrays[field]).all() or np.any(arrays[field] < 0) or
                np.any(arrays[field][:, ~valid] != 0)):
            raise ValueError("spatial four-store state invalid")
        np.testing.assert_array_equal(arrays[field][-1], checkpoint[field])
    for field in ("depth", "soil", "fast", "slow"):
        error = checkpoint["error_" + field]
        if error.shape != (cells,) or not np.isfinite(error).all() or np.any(error[~valid] != 0):
            raise ValueError("spatial compensation state invalid")
    for field in FLUXES:
        values = arrays[field]
        if not np.isfinite(values).all() or np.any(values < 0):
            raise ValueError("invalid spatial directional evidence")
    return audit_storage(arrays, metadata)


def audit_scenario(comparison_path, expected_sha256, *, weather_record, hierarchy_record,
                   expected_physics=None):
    path = Path(comparison_path).resolve(strict=True)
    if path.stat().st_size > 8 * 1024 * 1024 or file_sha256(path) != expected_sha256:
        raise ValueError("spatial comparison external pin/budget mismatch")
    record = json.loads(path.read_text(encoding="utf-8"))
    topology, geometry = read_record(hierarchy_record)
    weather, weather_metadata = read_record(weather_record)
    rain = weather["rain_mm_h"]
    plan = weather_metadata["plan"]
    if (rain.shape != (24, *topology["height_m"].shape) or rain.dtype != np.float64 or
            not np.isfinite(rain).all() or np.any(rain < 0) or
            np.any(rain[:, ~topology["valid_mask"]] != 0) or
            plan["dt_s"] != 3600 or plan["start_s"] != 0 or
            plan["spacing_m"] != geometry["spacing_m"] or
            plan["origin_m_xz"] != geometry["origin_m_xz"] or
            plan["source_identity"] != geometry["source_identity_sha256"] or
            plan["spatial_integration"] != "equal_area_midpoint_subcells_no_window_normalization"):
        raise ValueError("spatial full weather grid/normalization mismatch")
    np.testing.assert_array_equal(weather["valid_mask"], topology["valid_mask"])
    np.testing.assert_array_equal(weather["protected_mask"], topology["protected_mask"])
    np.testing.assert_array_equal(weather["time_edges_s"], np.arange(25) * 3600.)
    forcing_identity = numerical_identity(rain, 3600.)
    if weather_metadata["forcing_identity"] != forcing_identity:
        raise ValueError("independent full spatial forcing identity mismatch")
    steps = sorted((float(value) for value in record["pages"]), reverse=True)
    if (len(steps) != 2 or any(not math.isfinite(step) or step <= 0 or 3600 / step != int(3600 / step)
                               for step in steps) or steps[0] != 2 * steps[1]):
        raise ValueError("spatial refinement requires exact two-step halving")
    series = {}
    final = {}
    budgets = {}
    physical = expected_physics
    pins = [weather_record, hierarchy_record]
    for step in steps:
        pages = record["pages"][str(step)]
        if len(pages) != 24 or [page["hour"] for page in pages] != list(range(24)):
            raise ValueError("spatial hourly coverage/order mismatch")
        previous = None
        cumulative = None
        depths = []
        hourly = []
        for hour, page in enumerate(pages):
            for role in ("storage", "checkpoint"):
                artifact = Path(page[role]["path"]).resolve(strict=True)
                if not artifact.is_relative_to(path.parent):
                    raise ValueError("spatial artifact escapes pinned run")
            arrays, metadata = read_record(page["storage"])
            checkpoint, checkpoint_metadata = read_record(page["checkpoint"])
            pins.extend((page["storage"], page["checkpoint"]))
            if checkpoint_metadata["last_page_storage_identity"] != page["storage"]["expected_identity"]:
                raise ValueError("spatial checkpoint last-page link mismatch")
            current = {"parameters": {name: value for name, value in metadata["parameters"].items() if name != "substep_s"},
                       "runoff_parameters": metadata["runoff_parameters"]}
            if physical is None:
                physical = current
            elif current != physical:
                raise ValueError("spatial physical parameters changed")
            budget = check_page(arrays, metadata, checkpoint, checkpoint_metadata, topology, geometry,
                                rain, forcing_identity, hour, step, hierarchy_record["expected_identity"])
            if hour == 0:
                np.testing.assert_array_equal(arrays["depth_m"][0], 0)
                for field, parameter in (("soil_mm", "initial_soil_mm"), ("fast_mm", "initial_fast_mm"),
                                         ("slow_mm", "initial_slow_mm")):
                    np.testing.assert_array_equal(arrays[field][0], np.where(topology["valid_mask"].ravel(),
                        metadata["runoff_parameters"][parameter], 0))
                depths.append(arrays["depth_m"][0].copy())
                cumulative = {field: np.zeros_like(arrays[field]) for field in FLUXES}
            else:
                for field in STATES:
                    np.testing.assert_array_equal(arrays[field][0], previous[field])
            for field in FLUXES:
                cumulative[field] += arrays[field]
                np.testing.assert_array_equal(checkpoint["cumulative_" + field], cumulative[field])
            depths.append(arrays["depth_m"][-1].copy())
            hourly.append(budget)
            previous = checkpoint
            del arrays
        total_rain = math.fsum(item["rain_m3"] for hour in hourly for item in hour["budgets"])
        total_loss = math.fsum(item["loss_m3"] for hour in hourly for item in hour["budgets"])
        total_export = math.fsum(item["external_m3"] for hour in hourly for item in hour["budgets"])
        residual = math.fsum([hourly[0]["initial_water_m3"], total_rain, -total_loss, -total_export,
                              -hourly[-1]["final_water_m3"]])
        if abs(residual) > 1e-6 + total_rain * 1e-10:
            raise ValueError("spatial whole-period water budget failed")
        final[step] = cumulative
        series[step] = np.asarray(depths)
        budgets[str(step)] = {"hours": hourly, "whole_period_residual_m3": residual,
                             "whole_period_allowed_m3": 1e-6 + total_rain * 1e-10,
                             "whole_period_passed": True, "total_rain_m3": total_rain,
                             "total_loss_m3": total_loss, "total_boundary_export_m3": total_export}
    difference = abs(series[steps[0]] - series[steps[1]])
    frame, cell = np.unravel_index(np.argmax(difference), difference.shape)
    receiver = float(abs(final[steps[0]]["routed_volume_m3"] - final[steps[1]]["routed_volume_m3"]).sum() /
                     max(1e-12, final[steps[1]]["routed_volume_m3"].sum()))
    maximum = float(difference.max())
    passed = maximum <= .001 and receiver <= .01
    if (abs(record["max_saved_depth_difference_m"] - maximum) > 1e-12 or
            abs(record["cumulative_receiver_relative_l1"] - receiver) > 1e-12 or
            record["gate_passed"] is not passed):
        raise ValueError("spatial published temporal reductions mismatch")
    if file_sha256(path) != expected_sha256 or any(file_sha256(pin["path"]) != pin["expected_sha256"] for pin in pins):
        raise ValueError("spatial audit input changed during reduction")
    memory = psutil.Process().memory_info()
    peak_private = getattr(memory, "peak_pagefile", None)
    peak_rss = int(getattr(memory, "peak_wset", memory.rss))
    if peak_private is None or max(peak_private, peak_rss) > 1073741824:
        raise MemoryError("spatial independent audit requires measured private/RSS within1GiB")
    return {"schema": "td-independent-spatial-weather-continuation-v1", "comparison_path": str(path),
            "comparison_sha256": expected_sha256, "weather_record": weather_record,
            "hierarchy_record": hierarchy_record, "forcing_identity": forcing_identity,
            "substeps_s": steps, "saved_frames": 25, "physical_configuration": physical,
            "max_saved_depth_difference_m": maximum, "max_frame": int(frame), "max_cell": int(cell),
            "cumulative_receiver_relative_l1": receiver, "gate_passed": passed,
            "page_budget_audits": budgets, "full_spatial_rain_checked": True,
            "checkpoint_chain_checked": True, "solver_advanced": False,
            "resource": {"peak_rss_bytes": peak_rss, "peak_private_bytes": peak_private, "within_1GiB": True},
            "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
            "auditor_sha256": file_sha256(__file__),
            "limitations": "Original 30m grid, hourly saved temporal refinement and water budgets; no spatial convergence, observed outlet or metre-scale river channel certification."}


def write_report(report):
    output = ROOT / "verification/td-basin-generation" / ("independent-spatial-weather-" +
             datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--weather-record", type=Path)
    parser.add_argument("--hierarchy-record", type=Path)
    parser.add_argument("--run-inputs", type=Path)
    parser.add_argument("--inputs-sha256")
    parser.add_argument("--direction", choices=("eastward", "westward"))
    arguments = parser.parse_args()
    if arguments.run_inputs is not None:
        if file_sha256(arguments.run_inputs) != arguments.inputs_sha256 or arguments.direction is None:
            raise ValueError("externally pinned run inputs and direction required")
        inputs = json.loads(arguments.run_inputs.read_text(encoding="utf-8"))
        hierarchy = inputs["hierarchy"]
        hierarchy_pin = {"path": hierarchy["path"], "expected_sha256": hierarchy["sha256"],
                         "expected_identity": hierarchy["identity"]}
        weather_pin = inputs["weather_records"][arguments.direction]
    else:
        if arguments.weather_record is None or arguments.hierarchy_record is None:
            raise ValueError("external weather and hierarchy records required")
        weather_pin = json.loads(arguments.weather_record.read_text(encoding="utf-8"))
        hierarchy_pin = json.loads(arguments.hierarchy_record.read_text(encoding="utf-8"))
    result = audit_scenario(arguments.comparison, arguments.expected_sha256,
                           weather_record=weather_pin, hierarchy_record=hierarchy_pin)
    if arguments.run_inputs is not None and file_sha256(arguments.run_inputs) != arguments.inputs_sha256:
        raise ValueError("run inputs changed during independent spatial audit")
    destination = write_report(result)
    print(json.dumps({"path": str(destination), "sha256": file_sha256(destination), "gate_passed": result["gate_passed"]}))
