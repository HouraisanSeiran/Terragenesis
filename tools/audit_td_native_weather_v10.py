"""Independently reduce v10 spatial rain, compartment accounts and refinement."""

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
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_native_storm import numerical_identity

STATES = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
FLUX = ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s",
        "routed_volume_m3", "wet_duration_s")


def close(actual, expected, label):
    actual, expected = np.asarray(actual), np.asarray(expected)
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError("independent v10 " + label + " shape/nonfinite mismatch")
    if np.any(abs(actual - expected) > 1e-6 + 1e-10 * (abs(actual) + abs(expected))):
        raise ValueError("independent v10 " + label + " mismatch")


def audit_accounts(arrays, spacing, rain):
    cells = arrays["height_m"].size
    valid = arrays["valid_mask"].ravel()
    area = spacing ** 2
    for name in STATES:
        values = arrays[name]
        if values.shape != (2, cells) or not np.isfinite(values).all() or np.any(values < 0) or np.any(values[:, ~valid] != 0):
            raise ValueError("independent v10 invalid inventory")
    names = ("rain_volume_m3", "rain_infiltration_m3", "surface_infiltration_m3", "rain_excess_m3",
             "soil_et_m3", "surface_et_m3", "local_release_m3", "percolation_m3", "internal_net_m3",
             "boundary_outflow_m3", "storage_change_m3", "balance_residual_m3", "infiltration_capacity_m3")
    for name in names:
        values = arrays[name]
        if values.shape != (1, cells) or not np.isfinite(values).all() or np.any(values[:, ~valid] != 0):
            raise ValueError("independent v10 invalid compartment ledger")
        if name not in ("internal_net_m3", "storage_change_m3", "balance_residual_m3") and np.any(values < 0):
            raise ValueError("independent v10 negative gross ledger")
    if not np.array_equal(arrays["rain_mm_h"], np.asarray(rain).reshape(1, cells)):
        raise ValueError("independent v10 spatial rainfall slice mismatch")
    close(arrays["rain_volume_m3"], np.asarray(rain).reshape(1, cells) * area / 1000., "rain volume")
    close(arrays["rain_volume_m3"], arrays["rain_infiltration_m3"] + arrays["rain_excess_m3"], "rain allocation")
    infiltration = arrays["rain_infiltration_m3"] + arrays["surface_infiltration_m3"]
    if (np.any(infiltration > arrays["infiltration_capacity_m3"] + 1e-8) or
            np.any(arrays["infiltration_capacity_m3"] > 15. * area / 1000. + 1e-8) or
            np.any(arrays["soil_mm"] > 150.)):
        raise ValueError("independent v10 rate/soil capacity exceeded")
    close(np.diff(arrays["soil_mm"], axis=0) * area / 1000.,
          infiltration - arrays["soil_et_m3"] - arrays["percolation_m3"], "soil water account")
    close(np.diff(arrays["fast_mm"] + arrays["slow_mm"], axis=0) * area / 1000.,
          arrays["rain_excess_m3"] + arrays["percolation_m3"] - arrays["local_release_m3"], "reservoir water account")
    faces = arrays["face_cells"]
    signed = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    net = np.bincount(faces[:, 1], weights=signed, minlength=cells) - np.bincount(faces[:, 0], weights=signed, minlength=cells)
    close(arrays["internal_net_m3"][0], net, "face divergence")
    close(np.diff(arrays["depth_m"], axis=0) * area,
          arrays["local_release_m3"] - arrays["surface_infiltration_m3"] - arrays["surface_et_m3"] + net - arrays["boundary_outflow_m3"], "surface water account")
    declared = np.zeros(cells, bool)
    declared[arrays["boundary_cells"]] = True
    if np.any(arrays["boundary_outflow_m3"][:, ~declared] != 0):
        raise ValueError("independent v10 undeclared export")
    routed, duration = np.zeros(cells), np.zeros(cells)
    for source, target, volume, activity in ((faces[:, 0], faces[:, 1], arrays["face_forward_m3"], arrays["active_forward_s"]),
                                            (faces[:, 1], faces[:, 0], arrays["face_reverse_m3"], arrays["active_reverse_s"])):
        if not np.isfinite(volume).all() or not np.isfinite(activity).all() or np.any(volume < 0) or np.any(activity < 0) or np.any((volume == 0) & (activity != 0)):
            raise ValueError("independent v10 signed evidence invalid")
        follows = arrays["receiver"][source] == target
        np.add.at(routed, source[follows], volume[follows])
        np.add.at(duration, source[follows], activity[follows])
    close(arrays["routed_volume_m3"], routed, "receiver actual volume")
    close(arrays["wet_duration_s"], duration, "receiver actual activity")
    if np.any(arrays["active_forward_s"] + arrays["active_reverse_s"] > 3600. + 1e-8):
        raise ValueError("independent v10 combined activity exceeded hour")
    water = area * (arrays["depth_m"] + sum(arrays[name] for name in STATES[1:]) / 1000.)
    change = np.diff(water, axis=0)
    residual = arrays["rain_volume_m3"] + net - arrays["soil_et_m3"] - arrays["surface_et_m3"] - arrays["boundary_outflow_m3"] - change
    close(arrays["storage_change_m3"], change, "saved inventory change")
    close(arrays["balance_residual_m3"], residual, "saved cell residual")
    close(residual, np.zeros_like(residual), "cell conservation")
    total_rain = math.fsum(arrays["rain_volume_m3"].ravel().tolist())
    losses = math.fsum((arrays["soil_et_m3"] + arrays["surface_et_m3"]).ravel().tolist())
    export = math.fsum(arrays["boundary_outflow_m3"].ravel().tolist())
    before, after = (math.fsum(values.tolist()) for values in water)
    whole = math.fsum([before, total_rain, -losses, -export, -after])
    allowed = 1e-6 + 1e-10 * total_rain
    if abs(whole) > allowed:
        raise ValueError("independent v10 hour water budget failed")
    return dict(initial_water_m3=before, final_water_m3=after, rain_m3=total_rain,
                loss_m3=losses, external_m3=export, residual_m3=whole, allowed_m3=allowed, budget_passed=True)


def audit_scenario(comparison_path, expected_sha256, *, weather_record, hierarchy_record):
    path = Path(comparison_path).resolve(strict=True)
    if path.stat().st_size > 8 * 1024 * 1024 or file_sha256(path) != expected_sha256:
        raise ValueError("independent v10 comparison pin/budget mismatch")
    record = json.loads(path.read_text(encoding="utf-8"))
    topology, geometry = read_record(hierarchy_record)
    weather, weather_metadata = read_record(weather_record)
    rain = weather["rain_mm_h"]
    plan = weather_metadata["plan"]
    if (rain.shape != (24, *topology["height_m"].shape) or rain.dtype != np.float64 or
            not np.isfinite(rain).all() or np.any(rain < 0) or np.any(rain[:, ~topology["valid_mask"]] != 0) or
            plan["dt_s"] != 3600. or plan["start_s"] != 0 or
            plan["spacing_m"] != geometry["spacing_m"] or plan["origin_m_xz"] != geometry["origin_m_xz"] or
            plan["source_identity"] != geometry["source_identity_sha256"] or
            plan["spatial_integration"] != "equal_area_midpoint_subcells_no_window_normalization"):
        raise ValueError("independent v10 weather geometry/physics mismatch")
    for name in ("valid_mask", "protected_mask"):
        np.testing.assert_array_equal(weather[name], topology[name])
    np.testing.assert_array_equal(weather["time_edges_s"], np.arange(25) * 3600.)
    forcing_id = numerical_identity(rain, 3600.)
    if forcing_id != weather_metadata["forcing_identity"] or record["forcing_identity"] != forcing_id:
        raise ValueError("independent v10 full forcing identity mismatch")
    if record["schema"] != "td-v10-spatial-weather-comparison-v1" or set(record["pages"]) != {"2.5", "1.25"}:
        raise ValueError("independent v10 schema/refinement mismatch")
    depths, cumulative_final, budgets = {}, {}, {}
    pins = [weather_record, hierarchy_record]
    physical = None
    expected_physical = dict(parameters=dict(runoff=[15., 150., .15, 1., 3600., 259200.],
        face_conductance_m_s=.6, surface_evaporation_mm_h=.15,
        forcing_profile="v10-unified-rain-surface-infiltration-experimental-v1"),
        runoff_parameters=dict(infiltration_capacity_mm_h=15., soil_capacity_mm=150.,
        potential_et_mm_h=.15, percolation_mm_h=1., fast_tau_s=3600., slow_tau_s=259200.,
        initial_soil_mm=30., initial_fast_mm=0., initial_slow_mm=0.))
    for step in (2.5, 1.25):
        pages = record["pages"][str(step)]
        if len(pages) != 24 or [page["hour"] for page in pages] != list(range(24)):
            raise ValueError("independent v10 full coverage mismatch")
        previous, cumulative, frames, hourly = None, None, [], []
        for hour, page in enumerate(pages):
            for role in ("storage", "checkpoint"):
                if not Path(page[role]["path"]).resolve(strict=True).is_relative_to(path.parent):
                    raise ValueError("independent v10 artifact path escaped run")
            arrays, metadata = read_record(page["storage"])
            checkpoint, checkpoint_metadata = read_record(page["checkpoint"])
            pins.extend((page["storage"], page["checkpoint"]))
            expected = dict(profile="v10-unified-infiltration-SSPRK2-hour-pages-v1", dt_s=3600.,
                            substep_s=step, substeps=int(3600 / step), forcing_hour_offset=hour,
                            start_s=hour * 3600., end_s=(hour + 1) * 3600., forcing_identity=forcing_id,
                            hierarchy_identity=hierarchy_record["expected_identity"], spacing_m=geometry["spacing_m"],
                            origin_m_xz=geometry["origin_m_xz"], cells=topology["height_m"].size,
                            faces=len(topology["face_cells"]))
            for values, schema in ((metadata, "td-v10-hour-page-v1"), (checkpoint_metadata, "td-v10-hour-checkpoint-v1")):
                if values.get("schema") != schema or any(values.get(name) != value for name, value in expected.items()):
                    raise ValueError("independent v10 page/checkpoint geometry/time/profile mismatch")
                if any(values.get(name) is not False for name in ("hydraulic_ready", "transient_converged", "publishable")):
                    raise ValueError("independent v10 unsupported readiness flags")
            if checkpoint_metadata["last_page_identity"] != page["storage"]["expected_identity"]:
                raise ValueError("independent v10 page checkpoint link mismatch")
            current = dict(parameters={name: value for name, value in metadata["parameters"].items() if name != "substep_s"},
                           runoff_parameters=metadata["runoff_parameters"])
            if physical is None:
                physical = current
            if current != expected_physical or physical != current or metadata["parameters"] != checkpoint_metadata["parameters"] or metadata["runoff_parameters"] != checkpoint_metadata["runoff_parameters"]:
                raise ValueError("independent v10 physical parameters changed")
            if int(3600 / step) * len(topology["face_cells"]) > 6000000000:
                raise ValueError("independent v10 original hourly work cap exceeded")
            for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
                np.testing.assert_array_equal(arrays[name], topology[name])
            if hour == 0:
                np.testing.assert_array_equal(arrays["depth_m"][0], 0.)
                for name, value in (("soil_mm", 30.), ("fast_mm", 0.), ("slow_mm", 0.)):
                    np.testing.assert_array_equal(arrays[name][0], np.where(topology["valid_mask"].ravel(), value, 0.))
                cumulative = {name: np.zeros_like(arrays[name]) for name in FLUX}
                frames.append(arrays["depth_m"][0].copy())
            for name in STATES:
                if previous is not None:
                    np.testing.assert_array_equal(arrays[name][0], previous[name])
                np.testing.assert_array_equal(arrays[name][-1], checkpoint[name])
            for name in ("error_depth", "error_soil", "error_fast", "error_slow"):
                if checkpoint[name].shape != (topology["height_m"].size,) or not np.isfinite(checkpoint[name]).all() or np.any(checkpoint[name][~topology["valid_mask"].ravel()] != 0):
                    raise ValueError("independent v10 checkpoint compensation invalid")
            for name in FLUX:
                cumulative[name] += arrays[name]
                np.testing.assert_array_equal(checkpoint["cumulative_" + name], cumulative[name])
            hourly.append(audit_accounts(arrays, geometry["spacing_m"], rain[hour]))
            frames.append(arrays["depth_m"][-1].copy())
            previous = checkpoint
        total_rain = math.fsum(item["rain_m3"] for item in hourly)
        loss = math.fsum(item["loss_m3"] for item in hourly)
        export = math.fsum(item["external_m3"] for item in hourly)
        residual = math.fsum([hourly[0]["initial_water_m3"], total_rain, -loss, -export, -hourly[-1]["final_water_m3"]])
        if abs(residual) > 1e-6 + total_rain * 1e-10:
            raise ValueError("independent v10 whole period budget failed")
        budgets[str(step)] = dict(hours=hourly, whole_period_residual_m3=residual, whole_period_passed=True,
                                 total_rain_m3=total_rain, total_loss_m3=loss, total_boundary_export_m3=export)
        depths[step], cumulative_final[step] = np.asarray(frames), cumulative
    difference = abs(depths[2.5] - depths[1.25])
    frame, cell = np.unravel_index(difference.argmax(), difference.shape)
    maximum = float(difference.max())
    first = cumulative_final[2.5]["routed_volume_m3"]
    second = cumulative_final[1.25]["routed_volume_m3"]
    receiver = float(abs(first - second).sum() / max(1e-12, second.sum()))
    passed = maximum <= .001 and receiver <= .01
    if record["max_saved_depth_difference_m"] != maximum or record["cumulative_receiver_relative_l1"] != receiver or record["gate_passed"] is not passed:
        raise ValueError("independent v10 published gate reduction mismatch")
    if file_sha256(path) != expected_sha256 or any(file_sha256(pin["path"]) != pin["expected_sha256"] for pin in pins):
        raise ValueError("independent v10 inputs changed during audit")
    memory = psutil.Process().memory_info()
    rss, private = getattr(memory, "peak_wset", memory.rss), getattr(memory, "peak_pagefile", None)
    if private is None or max(rss, private) > 1073741824:
        raise MemoryError("independent v10 audit peak RSS/private requires <=1GiB")
    return dict(schema="td-independent-spatial-weather-v10-v1", comparison_path=str(path), comparison_sha256=expected_sha256,
                weather_record=weather_record, hierarchy_record=hierarchy_record, forcing_identity=forcing_id,
                substeps_s=[2.5, 1.25], saved_frames=25, physical_configuration=physical,
                max_saved_depth_difference_m=maximum, max_frame=int(frame), max_cell=int(cell),
                cumulative_receiver_relative_l1=receiver, gate_passed=passed, page_budget_audits=budgets,
                full_spatial_rain_checked=True, compartment_ledgers_checked=True, checkpoint_chain_checked=True,
                solver_advanced=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                resource=dict(peak_rss_bytes=int(rss), peak_private_bytes=int(private), within_1GiB=True),
                auditor_sha256=file_sha256(__file__), limitations="New permeable-surface hypothesis on 30m TD grid; saved hourly temporal check only; no natural outlet, spatial convergence or metre channels certified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--inputs-sha256", required=True)
    parser.add_argument("--direction", choices=("eastward", "westward"), required=True)
    parser.add_argument("--comparison-sha256", required=True)
    arguments = parser.parse_args()
    inputs_path = arguments.run / "run-inputs.json"
    if file_sha256(inputs_path) != arguments.inputs_sha256:
        raise ValueError("independent v10 external run inputs pin mismatch")
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    report = audit_scenario(arguments.run / (arguments.direction + "-comparison.json"), arguments.comparison_sha256,
                            weather_record=inputs["weather_records"][arguments.direction], hierarchy_record=inputs["hierarchy"])
    if file_sha256(inputs_path) != arguments.inputs_sha256:
        raise ValueError("independent v10 run inputs changed during audit")
    destination = ROOT / "verification/td-basin-generation" / ("independent-spatial-weather-v10-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(destination, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(destination), sha256=file_sha256(destination), gate_passed=report["gate_passed"])))
