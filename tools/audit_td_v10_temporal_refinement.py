"""Independent and cold-IO verification of separately resourced v10 time refinement."""

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
from terrain_pipeline.td_basin_storage_v10_io import PROFILE, validate_storage, validate_checkpoint
from terrain_pipeline.td_native_weather_storage_v10_io import PHYSICS, PHYSICS_SEMANTICS, validate_native_v10_accounts
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256
from dataclasses import asdict
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_native_weather_v10 import audit_accounts, STATES, FLUX
from tools.audit_td_native_storm import numerical_identity

MAX_BYTES = 1073741824
STEPS = (1.25, .625)


def pinned_json(record, max_bytes=8 * 1024 ** 2):
    path = Path(record["path"]).resolve(strict=True)
    if path.stat().st_size > max_bytes or file_sha256(path) != record["expected_sha256"]:
        raise ValueError("temporal audit JSON external pin/budget mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def check_resource(resource, index_sha, scope):
    if (resource.get("complete") is not True or resource.get("index_sha256") != index_sha or
            resource.get("scope") != scope or resource.get("monitor_error") is not None or
            any(type(resource.get(name)) is not int or not 0 < resource[name] <= MAX_BYTES
                for name in ("peak_rss_bytes", "peak_private_bytes", "sample_count"))):
        raise ValueError("temporal audit complete resource evidence invalid")


def audit_sequence(pages, *, topology, geometry, rain, forcing_identity, step, run_root, hierarchy_identity):
    if step not in STEPS or len(pages) != 24 or [item.get("hour") for item in pages] != list(range(24)):
        raise ValueError("temporal audit complete 24-hour sequence required")
    if rain.shape != (24, *topology["height_m"].shape) or rain.dtype != np.float64:
        raise ValueError("temporal audit rain shape/type mismatch")
    hierarchy = dict(arrays=topology, metadata=geometry, identity_sha256=hierarchy_identity)
    previous = None
    cumulative = None
    frames, hourly, records = [], [], []
    valid = topology["valid_mask"].ravel()
    faces = len(topology["face_cells"])
    cells = topology["height_m"].size
    for hour, page in enumerate(pages):
        if page.get("forcing_identity") != forcing_identity:
            raise ValueError("temporal audit hourly forcing mismatch")
        for role in ("storage", "checkpoint"):
            if not Path(page[role]["path"]).resolve(strict=True).is_relative_to(Path(run_root).resolve(strict=True)):
                raise ValueError("temporal audit saved artifact escaped its run")
        arrays, metadata = read_record(page["storage"])
        checkpoint, checkpoint_metadata = read_record(page["checkpoint"])
        records.extend((page["storage"], page["checkpoint"]))
        expected = dict(profile=PROFILE, cells=cells, faces=faces, substep_s=step,
                        substeps=int(3600 / step), forcing_hour_offset=hour, dt_s=3600.,
                        start_s=hour * 3600., end_s=(hour + 1) * 3600.,
                        hierarchy_identity=hierarchy_identity, forcing_identity=forcing_identity,
                        spacing_m=geometry["spacing_m"], origin_m_xz=geometry["origin_m_xz"],
                        parameters=dict(PHYSICS, substep_s=step), runoff_parameters=asdict(RunoffParameters()),
                        physics=PHYSICS_SEMANTICS,
                        permanent_lake_impermeability="not modelled; requires independent material mask",
                        activity_semantics="SSP-RK2 stage quadrature of actual signed exchange; not exact event duration")
        for current, schema in ((metadata, "td-v10-hour-page-v1"), (checkpoint_metadata, "td-v10-hour-checkpoint-v1")):
            if current.get("schema") != schema or any(current.get(name) != value for name, value in expected.items()):
                raise ValueError("temporal audit predeclared time/grid/physics mismatch")
            if any(current.get(name) is not False for name in ("hydraulic_ready", "transient_converged", "publishable")):
                raise ValueError("temporal audit unsupported readiness flags")
        if page.get("chunk_work_face_steps") != int(3600 / step) * faces or int(3600 / step) * faces > 6000000000:
            raise ValueError("temporal audit hourly work declaration/cap mismatch")
        storage = dict(arrays=arrays, metadata=metadata, identity_sha256=page["storage"]["expected_identity"])
        saved_checkpoint = dict(arrays=checkpoint, metadata=checkpoint_metadata,
                                identity_sha256=page["checkpoint"]["expected_identity"])
        validate_storage(storage)
        validate_checkpoint(saved_checkpoint)
        validate_native_v10_accounts(storage, hierarchy=hierarchy, rain_mm_h=rain[hour])
        if checkpoint_metadata["last_page_identity"] != page["storage"]["expected_identity"]:
            raise ValueError("temporal audit last-page checkpoint mismatch")
        if hour == 0:
            cumulative = {name:np.zeros_like(arrays[name]) for name in FLUX}
            frames.append(arrays["depth_m"][0].copy())
        for name in STATES:
            initial = np.where(valid, 30. if name == "soil_mm" else 0., 0.) if previous is None else previous[name]
            np.testing.assert_array_equal(arrays[name][0], initial)
            np.testing.assert_array_equal(arrays[name][-1], checkpoint[name])
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
        raise ValueError("temporal audit whole period water budget failed")
    return dict(frames=np.asarray(frames), cumulative=cumulative, records=records,
                budget=dict(hours=hourly, whole_period_residual_m3=residual, whole_period_passed=True,
                            total_rain_m3=total_rain, total_loss_m3=loss, total_boundary_export_m3=export))


def compare(first, second):
    if first["frames"].shape != second["frames"].shape or first["frames"].shape[0] != 25:
        raise ValueError("temporal compare requires 25 complete frames")
    difference = abs(first["frames"] - second["frames"])
    if not np.isfinite(difference).all():
        raise ValueError("temporal compare nonfinite frame")
    frame, cell = np.unravel_index(difference.argmax(), difference.shape)
    receiver0 = first["cumulative"]["routed_volume_m3"]
    receiver1 = second["cumulative"]["routed_volume_m3"]
    if receiver0.shape != receiver1.shape or not np.isfinite(receiver0).all() or not np.isfinite(receiver1).all() or np.any(receiver0 < 0) or np.any(receiver1 < 0):
        raise ValueError("temporal compare invalid receiver inventory")
    relative = float(abs(receiver0 - receiver1).sum() / max(1e-12, receiver1.sum()))
    maximum = float(difference.max())
    return dict(max_saved_depth_difference_m=maximum, max_frame=int(frame), max_cell=int(cell),
                cumulative_receiver_relative_l1=relative, gate_passed=maximum <= .001 and relative <= .01,
                saved_frames=25, substeps_s=list(STEPS), depth_gate_m=.001, receiver_gate=.01)


def audit(run, index_sha256, inputs_sha256, resource_sha256):
    run = Path(run).resolve(strict=True)
    external = {name:dict(path=str(run / filename), expected_sha256=digest) for name, filename, digest in
                (("index", "index.json", index_sha256), ("inputs", "run-inputs.json", inputs_sha256),
                 ("resource", "resource.json", resource_sha256))}
    index, plan, resource = (pinned_json(external[name]) for name in ("index", "inputs", "resource"))
    if (index.get("schema") != "td-v10-temporal-refinement-index-v1" or
            plan.get("schema") != "td-v10-temporal-refinement-plan-v1" or
            index.get("new_step_s") != .625 or plan.get("new_step_s") != .625 or
            index.get("reference_step_s") != 1.25 or plan.get("reference_step_s") != 1.25 or
            plan.get("depth_gate_m") != .001 or plan.get("receiver_gate") != .01 or
            plan.get("job_max_bytes") != MAX_BYTES or plan.get("chunk_max_face_steps") != 6000000000 or
            plan.get("expected_new_pages") != 48 or plan.get("expected_reference_pages") != 48 or
            plan.get("expected_baseline_pages") != 96 or
            index.get("baseline_records") != plan.get("baseline_records") or
            index.get("source_records") != plan.get("source_records") or
            index.get("code_sha256") != plan.get("baseline_code_sha256") or
            index.get("run_inputs_record") != external["inputs"] or
            set(index.get("scenarios", {})) != {"eastward", "westward"}):
        raise ValueError("temporal audit index/plan source/step predeclaration mismatch")
    for metadata in (index, plan):
        if any(metadata.get(name) is not False for name in ("hydraulic_ready", "transient_converged", "publishable")):
            raise ValueError("temporal refinement unsupported readiness claim")
    status = pinned_json(plan["pipeline_status_record"])
    if (status.get("schema") != "td-ten-hour-pipeline-status-v1" or status.get("state") != "diagnostic_stop" or
            datetime.fromisoformat(plan["deadline_utc"]) > datetime.fromisoformat(status["deadline_utc"])):
        raise ValueError("temporal refinement original stop/deadline mismatch")
    check_resource(resource, index_sha256, "complete new eastward+westward 0.625s 48 pages only")
    if (resource.get("schema") != "td-v10-temporal-refinement-resource-v1" or
            resource.get("code_sha256") != plan["baseline_code_sha256"] or
            resource.get("within_1GiB") is not True or resource.get("job_max_bytes") != MAX_BYTES):
        raise ValueError("new temporal resource schema/code mismatch")
    baseline = plan["baseline_records"]
    old_index, old_inputs, old_resource, accepted = (pinned_json(baseline[name]) for name in ("index", "inputs", "resource", "acceptance"))
    old_run = Path(baseline["index"]["path"]).parent.resolve(strict=True)
    check_resource(old_resource, baseline["index"]["expected_sha256"], "complete eastward+westward both steps execution")
    if (accepted.get("schema") != "td-independent-final-spatial-weather-v10-v1" or
            accepted.get("io_chain_accepted") is not True or
            Path(accepted.get("index_path", "")).resolve() != Path(baseline["index"]["path"]).resolve() or
            accepted.get("index_sha256") != baseline["index"]["expected_sha256"] or
            accepted.get("resource_sha256") != baseline["resource"]["expected_sha256"] or
            accepted.get("cold_acceptance", {}).get("io_chain_accepted") is not True or
            old_index.get("schema") != "td-v10-spatial-weather-hour-pages-index-v1" or
            old_index.get("steps_s") != [2.5, 1.25] or old_inputs.get("steps_s") != [2.5, 1.25] or
            old_inputs.get("code_sha256") != plan["baseline_code_sha256"] or
            old_index.get("code_sha256") != plan["baseline_code_sha256"] or
            old_inputs.get("depth_gate_m") != .001 or old_inputs.get("receiver_gate") != .01 or
            old_inputs.get("job_max_bytes") != MAX_BYTES or
            old_inputs.get("primary_sha256") != PRIMARY_SHA256 or file_sha256(PRIMARY_PATH) != PRIMARY_SHA256):
        raise ValueError("historical complete baseline acceptance does not bind refinement")
    for name, role in (("run_inputs_record", "inputs"), ("execution_resource_record", "resource")):
        record = accepted["acceptance_arguments"][name]
        if (Path(record["path"]).resolve() != Path(baseline[role]["path"]).resolve() or
                record["expected_sha256"] != baseline[role]["expected_sha256"]):
            raise ValueError("historical full acceptance path/sha changed")
    if status.get("baseline_acceptance_record") != baseline["acceptance"]:
        raise ValueError("refinement baseline differs from original stopped pipeline")
    if set(entry.name for entry in run.iterdir() if entry.is_dir()) != {"eastward-0.625s", "westward-0.625s"}:
        raise ValueError("refinement directory coverage mismatch")
    sources = plan["source_records"]
    if any(sources[name] != old_inputs[name] for name in ("hierarchy", "weather_index", "weather_records")):
        raise ValueError("time refinement changed source or weather")
    weather_index_record = dict(path=sources["weather_index"]["path"], expected_sha256=sources["weather_index"]["sha256"])
    weather_index = pinned_json(weather_index_record)
    source_pin = weather_index["source"]
    if (weather_index.get("schema") != "td-native-storm-forcing-index-v1" or
            set(weather_index.get("cases", {})) != {"eastward", "westward"} or
            any(weather_index["cases"][direction]["record"] != sources["weather_records"][direction]
                for direction in ("eastward", "westward"))):
        raise ValueError("time refinement weather index does not bind full forcing")
    read_record(source_pin)
    codes = plan["baseline_code_sha256"]
    if len(codes) != 15:
        raise ValueError("time refinement requires original complete 15 code pins")
    for name, digest in codes.items():
        target = (ROOT / name).resolve(strict=True)
        if not target.is_relative_to(ROOT) or file_sha256(target) != digest:
            raise ValueError("time refinement original frozen code changed")
    if file_sha256(ROOT / "tools/run_td_v10_temporal_refinement.py") != plan["runner_sha256"]:
        raise ValueError("time refinement execution runner changed")
    execution = pinned_json(dict(path=str(run / "execution-code.json"), expected_sha256=file_sha256(run / "execution-code.json")))
    if execution.get("baseline_code_sha256") != codes or execution.get("runner_sha256") != plan["runner_sha256"]:
        raise ValueError("time refinement execution snapshot pins changed")
    import hashlib
    if hashlib.sha256(execution["runner_source"].encode("utf-8")).hexdigest() != plan["runner_sha256"]:
        raise ValueError("time refinement saved runner text mismatch")
    topology, geometry = read_record(sources["hierarchy"])
    reports, saved_pins = {}, []
    for direction in ("eastward", "westward"):
        weather_record = sources["weather_records"][direction]
        weather, weather_metadata = read_record(weather_record)
        rain = weather["rain_mm_h"]
        forcing_id = numerical_identity(rain, 3600.)
        weather_plan = weather_metadata["plan"]
        if (rain.dtype != np.float64 or rain.shape != (24, *topology["height_m"].shape) or
                not np.isfinite(rain).all() or np.any(rain < 0) or np.any(rain[:, ~topology["valid_mask"]] != 0) or
                weather_plan["dt_s"] != 3600. or weather_plan["start_s"] != 0. or
                weather_plan["spacing_m"] != geometry["spacing_m"] or
                weather_plan["origin_m_xz"] != geometry["origin_m_xz"] or
                weather_plan["source_identity"] != geometry["source_identity_sha256"] or
                forcing_id != weather_metadata["forcing_identity"] or forcing_id != old_inputs["forcing_identities"][direction]):
            raise ValueError("time refinement full weather geometry/identity mismatch")
        np.testing.assert_array_equal(weather["valid_mask"], topology["valid_mask"])
        np.testing.assert_array_equal(weather["protected_mask"], topology["protected_mask"])
        np.testing.assert_array_equal(weather["time_edges_s"], np.arange(25) * 3600.)
        new = index["scenarios"][direction]
        old = old_index["scenarios"][direction]
        if any(case.get("weather_record") != weather_record or case.get("forcing_identity") != forcing_id for case in (new, old)):
            raise ValueError("time refinement directional forcing changed")
        reference = audit_sequence(old["pages"]["1.25"], topology=topology, geometry=geometry, rain=rain,
                                   forcing_identity=forcing_id, step=1.25, run_root=old_run,
                                   hierarchy_identity=sources["hierarchy"]["expected_identity"])
        fine = audit_sequence(new["pages"], topology=topology, geometry=geometry, rain=rain,
                              forcing_identity=forcing_id, step=.625, run_root=run,
                              hierarchy_identity=sources["hierarchy"]["expected_identity"])
        saved_pins.extend((*reference["records"], *fine["records"], weather_record))
        reports[direction] = dict(**compare(reference, fine), page_budget_audits={"1.25":reference["budget"], ".625":fine["budget"]},
                                  full_spatial_rain_checked=True, compartment_ledgers_checked=True, checkpoint_chain_checked=True,
                                  cold_schema_checked=True)
    for record in (*external.values(), *baseline.values(), sources["hierarchy"], weather_index_record,
                   source_pin, plan["pipeline_status_record"], *saved_pins):
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("time refinement saved evidence changed during audit")
    for name, digest in codes.items():
        if file_sha256(ROOT / name) != digest:
            raise ValueError("time refinement original code changed during audit")
    memory = psutil.Process().memory_info()
    peak_rss = int(getattr(memory, "peak_wset", memory.rss))
    peak_private = int(getattr(memory, "peak_pagefile", 0))
    if not 0 < peak_private <= MAX_BYTES or not 0 < peak_rss <= MAX_BYTES:
        raise MemoryError("time refinement audit requires measured <=1GiB RSS/private")
    return dict(schema="td-independent-final-temporal-refinement-v1", run_records=external,
                baseline_records=baseline, source_records=sources, directions=reports,
                all_saved_numerical_gates_passed=all(report["gate_passed"] for report in reports.values()),
                io_chain_accepted=True, separate_execution_resources_authenticated=True,
                new_execution_resource=resource, historical_execution_resource=old_resource,
                audit_resource=dict(peak_rss_bytes=peak_rss, peak_private_bytes=peak_private),
                depth_gate_m=.001, receiver_gate=.01, physics_changed=False,
                solver_advanced=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                limitations="two separately monitored complete executions; temporal saved-frame acceptance only, no natural outlet, spatial fine-bed convergence or complete 3D network")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--inputs-sha256", required=True)
    parser.add_argument("--resource-sha256", required=True)
    args = parser.parse_args()
    result = audit(args.run, args.index_sha256, args.inputs_sha256, args.resource_sha256)
    destination = ROOT / "verification/td-weather-refinement" / ("independent-final-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "acceptance-index.json"
    publish_bytes(destination, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(destination), expected_sha256=file_sha256(destination),
                         all_saved_numerical_gates_passed=result["all_saved_numerical_gates_passed"])))


if __name__ == "__main__":
    main()
