"""Independently inspect candidate-bed weather pages against unchanged source rain."""

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
from terrain_pipeline.td_surface_reaches import _hash
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_native_storm import numerical_identity
from tools.audit_td_native_weather_v10 import audit_accounts, STATES, FLUX


def read_json(record, limit=8 * 1024 ** 2):
    path = Path(record["path"]).resolve(strict=True)
    if path.stat().st_size > limit or file_sha256(path) != record["expected_sha256"]:
        raise ValueError("independent candidate JSON pin/budget mismatch")
    result = json.loads(path.read_text(encoding="utf-8"))
    if "expected_identity" in record:
        unsigned = {name: value for name, value in result.items() if name != "identity_sha256"}
        if result.get("identity_sha256") != record["expected_identity"] or _hash(unsigned) != record["expected_identity"]:
            raise ValueError("independent candidate JSON identity mismatch")
    return result


def audit_execution(execution_record, direction):
    if direction not in ("eastward", "westward"):
        raise ValueError("explicit weather direction required")
    execution = read_json(execution_record)
    if execution.get("schema") != "td-candidate-native-weather-execution-v1":
        raise ValueError("independent candidate execution schema mismatch")
    plan = read_json(execution["plan_record"])
    candidate_id = execution["candidate_id"]
    if candidate_id not in ("valley_incision", "source_deposition"):
        raise ValueError("independent candidate identity unsupported")
    if (plan.get("execution_ready") is not True or plan.get("baseline_numerical_gate_passed") is not True or
            execution["candidates"] != plan["candidates"][candidate_id] or
            execution["forcing_identities"] != plan["forcing_identities"] or execution["steps_s"] != [2.5, 1.25] or
            any(value is not False for value in execution["flags"].values())):
        raise ValueError("independent candidate execution plan/certification mismatch")
    hierarchy_record = execution["candidates"]["hierarchy_record"]
    source_record = execution["candidates"]["source_record"]
    topology, hierarchy_metadata = read_record(hierarchy_record)
    source, source_metadata = read_record(source_record)
    original, original_metadata = read_record(plan["original_weather_source_record"])
    weather_index = read_json(plan["weather_index_record"])
    weather_record = weather_index["cases"][direction]["record"]
    weather, weather_metadata = read_record(weather_record)
    pins = [execution_record, execution["plan_record"], hierarchy_record, source_record,
            plan["original_weather_source_record"], plan["weather_index_record"], weather_record]
    if hierarchy_metadata["source_identity_sha256"] != source_record["expected_identity"]:
        raise ValueError("independent candidate new source/hierarchy mismatch")
    for metadata in (source_metadata, original_metadata):
        if any(metadata[name] != hierarchy_metadata[name] for name in ("spacing_m", "origin_m_xz")):
            raise ValueError("independent candidate world grid mismatch")
    for name in ("valid_mask", "protected_mask", "open_boundary_mask"):
        np.testing.assert_array_equal(source[name], original[name])
        np.testing.assert_array_equal(source[name], topology[name])
    np.testing.assert_array_equal(source["height_m"], topology["height_m"])
    rain = weather["rain_mm_h"]
    weather_plan = weather_metadata["plan"]
    if (rain.shape != (24, *topology["height_m"].shape) or rain.dtype != np.float64 or
            not np.isfinite(rain).all() or np.any(rain < 0) or
            np.any(rain[:, ~topology["valid_mask"]] != 0) or
            weather_plan["source_identity"] != plan["original_weather_source_record"]["expected_identity"] or
            weather_plan["origin_m_xz"] != hierarchy_metadata["origin_m_xz"] or
            weather_plan["spacing_m"] != hierarchy_metadata["spacing_m"] or
            weather_plan["start_s"] != 0 or weather_plan["dt_s"] != 3600. or
            weather_plan["spatial_integration"] != "equal_area_midpoint_subcells_no_window_normalization"):
        raise ValueError("independent candidate original spatial weather mapping mismatch")
    for name in ("valid_mask", "protected_mask"):
        np.testing.assert_array_equal(weather[name], topology[name])
    np.testing.assert_array_equal(weather["time_edges_s"], np.arange(25) * 3600.)
    forcing_id = numerical_identity(rain, 3600.)
    if forcing_id != weather_metadata["forcing_identity"] or forcing_id != plan["forcing_identities"][direction]:
        raise ValueError("independent candidate full forcing identity mismatch")
    run = Path(execution_record["path"]).resolve().parent
    groups = execution["pages"][direction]
    if set(groups) != {"2.5", "1.25"}:
        raise ValueError("independent candidate both time steps required")
    physical = dict(runoff=[15., 150., .15, 1., 3600., 259200.], face_conductance_m_s=.6,
                    surface_evaporation_mm_h=.15,
                    forcing_profile="v10-unified-rain-surface-infiltration-experimental-v1")
    runoff = dict(infiltration_capacity_mm_h=15., soil_capacity_mm=150., potential_et_mm_h=.15,
                  percolation_mm_h=1., fast_tau_s=3600., slow_tau_s=259200.,
                  initial_soil_mm=30., initial_fast_mm=0., initial_slow_mm=0.)
    frames, final_receiver, budgets = {}, {}, {}
    for step in (2.5, 1.25):
        pages = groups[str(step)]
        if len(pages) != 24 or [page["hour"] for page in pages] != list(range(24)):
            raise ValueError("independent candidate full hour coverage mismatch")
        previous, cumulative, depths, hours = None, None, [], []
        for hour, page in enumerate(pages):
            for role, filename in (("storage", "storage.npz"), ("checkpoint", "checkpoint.npz")):
                expected_path = run / f"{direction}-{step:g}s" / f"hour-{hour:02d}" / filename
                if Path(page[role]["path"]).resolve(strict=True) != expected_path:
                    raise ValueError("independent candidate page escaped declared layout")
            arrays, metadata = read_record(page["storage"])
            checkpoint, checkpoint_metadata = read_record(page["checkpoint"])
            pins.extend((page["storage"], page["checkpoint"]))
            expected = dict(profile="v10-unified-infiltration-SSPRK2-hour-pages-v1", dt_s=3600.,
                            substep_s=step, substeps=int(3600 / step), forcing_hour_offset=hour,
                            start_s=hour * 3600., end_s=(hour + 1) * 3600., forcing_identity=forcing_id,
                            hierarchy_identity=hierarchy_record["expected_identity"],
                            origin_m_xz=hierarchy_metadata["origin_m_xz"], spacing_m=hierarchy_metadata["spacing_m"],
                            cells=topology["height_m"].size, faces=len(topology["face_cells"]),
                            parameters=dict(physical, substep_s=step), runoff_parameters=runoff)
            for values, schema in ((metadata, "td-v10-hour-page-v1"), (checkpoint_metadata, "td-v10-hour-checkpoint-v1")):
                if values["schema"] != schema or any(values.get(name) != value for name, value in expected.items()):
                    raise ValueError("independent candidate page time/physics/new hierarchy mismatch")
            for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
                np.testing.assert_array_equal(arrays[name], topology[name])
            if checkpoint_metadata["last_page_identity"] != page["storage"]["expected_identity"]:
                raise ValueError("independent candidate checkpoint page link mismatch")
            if hour == 0:
                for name, value in (("depth_m", 0.), ("soil_mm", 30.), ("fast_mm", 0.), ("slow_mm", 0.)):
                    np.testing.assert_array_equal(arrays[name][0], np.where(topology["valid_mask"].ravel(), value, 0.))
                cumulative = {name: np.zeros_like(arrays[name]) for name in FLUX}
                depths.append(arrays["depth_m"][0].copy())
            for name in STATES:
                if previous is not None:
                    np.testing.assert_array_equal(arrays[name][0], previous[name])
                np.testing.assert_array_equal(arrays[name][-1], checkpoint[name])
            for name in FLUX:
                cumulative[name] += arrays[name]
                np.testing.assert_array_equal(cumulative[name], checkpoint["cumulative_" + name])
            for name in ("error_depth", "error_soil", "error_fast", "error_slow"):
                values = checkpoint[name]
                if values.shape != (topology["height_m"].size,) or not np.isfinite(values).all() or np.any(values[~topology["valid_mask"].ravel()] != 0):
                    raise ValueError("independent candidate invalid compensation state")
            hours.append(audit_accounts(arrays, hierarchy_metadata["spacing_m"], rain[hour]))
            depths.append(arrays["depth_m"][-1].copy())
            previous = checkpoint
        total_rain = math.fsum(item["rain_m3"] for item in hours)
        residual = math.fsum([hours[0]["initial_water_m3"], total_rain,
                             -math.fsum(item["loss_m3"] for item in hours),
                             -math.fsum(item["external_m3"] for item in hours), -hours[-1]["final_water_m3"]])
        if abs(residual) > 1e-6 + total_rain * 1e-10:
            raise ValueError("independent candidate full period water budget failed")
        frames[step] = np.asarray(depths)
        final_receiver[step] = cumulative["routed_volume_m3"]
        budgets[str(step)] = dict(hours=hours, whole_period_residual_m3=residual, whole_period_passed=True)
    difference = np.abs(frames[2.5] - frames[1.25])
    frame, cell = np.unravel_index(difference.argmax(), difference.shape)
    maximum = float(difference.max())
    relative = float(np.abs(final_receiver[2.5] - final_receiver[1.25]).sum() / max(1e-12, final_receiver[1.25].sum()))
    if any(file_sha256(pin["path"]) != pin["expected_sha256"] for pin in pins):
        raise ValueError("independent candidate inputs changed during audit")
    memory = psutil.Process().memory_info()
    rss, private = getattr(memory, "peak_wset", memory.rss), getattr(memory, "peak_pagefile", None)
    if private is None or max(rss, private) > 1024 ** 3:
        raise MemoryError("independent candidate audit requires <=1GiB RSS/private")
    return dict(schema="td-independent-candidate-weather-v1", candidate_final_record=execution_record,
                candidate_id=candidate_id, direction=direction, hierarchy_record=hierarchy_record,
                original_weather_source_record=plan["original_weather_source_record"], weather_record=weather_record,
                forcing_identity=forcing_id, max_saved_depth_difference_m=maximum,
                cumulative_receiver_relative_l1=relative, gate_passed=maximum <= .001 and relative <= .01,
                max_frame=int(frame), max_cell=int(cell), page_budget_audits=budgets,
                full_spatial_rain_checked=True, compartment_ledgers_checked=True,
                checkpoint_chain_checked=True, whole_period_budget_passed=True,
                solver_advanced=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                resource=dict(peak_rss_bytes=int(rss), peak_private_bytes=int(private)),
                auditor_sha256=file_sha256(__file__),
                scope="saved candidate-bed temporal/accounting audit; unchanged source weather; no natural outlet or fine hydraulics certification")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-record", type=Path, required=True)
    parser.add_argument("--direction", choices=("eastward", "westward"), required=True)
    arguments = parser.parse_args()
    record = json.loads(arguments.execution_record.read_text(encoding="utf-8"))
    result = audit_execution(record, arguments.direction)
    directory = ROOT / "verification/td-basin-generation" / ("independent-candidate-weather-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    path = directory / "report.json"
    publish_bytes(path, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(path), expected_sha256=file_sha256(path), gate_passed=result["gate_passed"])))


if __name__ == "__main__":
    main()
