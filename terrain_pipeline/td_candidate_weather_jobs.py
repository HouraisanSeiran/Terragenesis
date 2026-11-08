"""Serial candidate weather plans and externally pinned cold execution evidence."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import math
import ast
import time

import numpy as np
import psutil

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.td_native_weather_storage_io import _json
from terrain_pipeline.td_native_weather_storage_v10_io import (
    PHYSICS, STEPS, load_native_weather_storage_v10_index, load_native_weather_v10_hour)
from terrain_pipeline.basin_storage import load_td_source_bundle as load_td_source_bundle
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.climate_forcing import load_native_storm
from terrain_pipeline.basin_storage import storagev10_load_storage as load_storage
from terrain_pipeline.basin_storage import storagev10_load_checkpoint as load_checkpoint
from terrain_pipeline.td_surface_reaches import _hash, _plain
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ("valley_incision", "source_deposition")
MAX_BYTES = 1073741824
SCHEMA = "td-candidate-native-weather-plan-v1"
FLAGS = dict(hydraulic_ready=False, transient_converged=False, publishable=False, natural_outlet_verified=False)
DEPENDENCY_ROOTS = (
    "terrain_pipeline/td_candidate_weather_jobs.py",
    "tools/run_td_candidate_weather_jobs.py",
    'terrain_pipeline/basin_storage.py',
    "terrain_pipeline/td_native_weather_storage_v10_io.py",
    "terrain_pipeline/td_native_weather_v10_review.py",
    'tools/verify_basin_storage_execution.py',
    'tools/verify_basin_storage_execution.py',
    "tools/rebuild_td_accepted_candidate_topology.py",
    "tools/audit_td_native_weather_v10_final.py",
    'terrain_pipeline/basin_storage.py',
    'terrain_pipeline/basin_storage.py',
    'terrain_pipeline/basin_storage.py',
    'terrain_pipeline/basin_storage.py',
)


def execution_dependency_names():
    pending = list(DEPENDENCY_ROOTS)
    discovered = set()
    while pending:
        name = pending.pop()
        if name in discovered:
            continue
        target = ROOT / name
        if not target.is_file():
            raise ValueError("candidate dependency source missing: " + name)
        discovered.add(name)
        tree = ast.parse(target.read_text(encoding="utf-8-sig"), filename=name)
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
                modules.extend(node.module + "." + alias.name for alias in node.names)
            for module in modules:
                if module.startswith(("terrain_pipeline.", "tools.")):
                    relative = module.replace(".", "/") + ".py"
                    if (ROOT / relative).is_file() and relative not in discovered:
                        pending.append(relative)
    return tuple(sorted(discovered))


def _check_execution_dependencies(codes):
    if set(codes) != set(execution_dependency_names()):
        raise ValueError("candidate complete recursive dependency set mismatch")
    for name, digest in codes.items():
        if file_sha256(ROOT / name) != digest:
            raise ValueError("candidate frozen dependency changed: " + name)


def _recheck_publication(plan, records, groups=None):
    _check_execution_dependencies(plan["code_sha256"])
    pinned = list(records)
    pinned.extend((plan["baseline_acceptance_record"], plan["weather_index_record"], plan["original_weather_source_record"]))
    pinned.extend(plan["weather_records"].values())
    baseline = _json(plan["baseline_acceptance_record"])
    pinned.extend(item["record"] for item in baseline["numerical_reports"].values())
    arguments = baseline["acceptance_arguments"]
    pinned.append(dict(path=baseline["index_path"], expected_sha256=arguments["expected_sha256"]))
    pinned.extend(arguments[name] for name in ("run_inputs_record", "execution_resource_record", "hierarchy_record", "source_record", "weather_index_record"))
    for candidate in plan["candidates"].values():
        pinned.extend(candidate[name] for name in ("topology_record", "source_record", "hierarchy_record", "material_record", "geometry_parent_record", "original_source_record"))
    if groups is not None:
        for direction in groups.values():
            for pages in direction.values():
                for page in pages:
                    pinned.extend((page["storage"], page["checkpoint"]))
    for record in pinned:
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("candidate critical publication pin changed: " + record["path"])


def _write(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf8"))


def _pin(path, value=None):
    record = dict(path=str(Path(path).absolute()), expected_sha256=file_sha256(path))
    if value is not None:
        record["expected_identity"] = value["identity_sha256"]
    return record


def _memory():
    memory = psutil.Process().memory_info()
    rss, private = int(getattr(memory, "peak_wset", memory.rss)), getattr(memory, "peak_pagefile", None)
    if type(private) is not int or max(rss, private) > MAX_BYTES:
        raise MemoryError("candidate job private/RSS resource missing/exceeded")
    return dict(peak_rss_bytes=rss, peak_private_bytes=private)


def _baseline(record):
    from tools.audit_td_native_weather_v10_final import bind_numerical
    acceptance = _json(record)
    if acceptance.get("schema") != "td-independent-final-spatial-weather-v10-v1" or acceptance.get("io_chain_accepted") is not True or acceptance.get("original_inputs_and_frozen_code_unchanged") is not True:
        raise ValueError("candidate jobs require full independent v10 baseline acceptance")
    arguments = acceptance["acceptance_arguments"]
    index_path = acceptance["index_path"]
    if acceptance.get("index_sha256") != arguments["expected_sha256"] or acceptance.get("resource_sha256") != arguments["execution_resource_record"]["expected_sha256"]:
        raise ValueError("baseline acceptance input pin mismatch")
    cold = load_native_weather_storage_v10_index(index_path, **arguments)
    if acceptance["cold_acceptance"] != cold:
        first = {name:value for name, value in acceptance["cold_acceptance"].items() if name != "resource"}
        second = {name:value for name, value in cold.items() if name != "resource"}
        if first != second:
            raise ValueError("baseline accepted cold summary mismatch")
    index = _json(dict(path=index_path, expected_sha256=arguments["expected_sha256"]))
    inputs = _json(arguments["run_inputs_record"])
    reports = bind_numerical(index, inputs, Path(index_path).parent,
        {direction:value["record"] for direction, value in acceptance["numerical_reports"].items()}, cold)
    ready = all(value["gate_passed"] for value in reports.values())
    if acceptance.get("all_saved_numerical_gates_passed") is not ready:
        raise ValueError("baseline numerical readiness mismatch")
    return acceptance, cold, ready


def _candidate(record, candidate_id, baseline):
    from tools.rebuild_td_accepted_candidate_topology import load_topology_index
    from terrain_pipeline.td_accepted_water_morphology import load_accepted_water_morphology
    raw = _json(record)
    candidate = load_topology_index(record["path"], expected_sha256=record["expected_sha256"], expected_identity=record["expected_identity"],
        parent_record=raw["parent_manifest"], source_record=raw["source"])
    if candidate["candidate_id"] != candidate_id or candidate["original_source_record"] != baseline["acceptance_arguments"]["source_record"]:
        raise ValueError("candidate original source/candidate identity mismatch")
    parent_record = candidate["parent_manifest"]
    parent_raw = _json(parent_record)
    parent = _plain(load_accepted_water_morphology(parent_record["path"], expected_sha256=parent_record["expected_sha256"],
        expected_identity=parent_record["expected_identity"], **parent_raw["inputs"]))
    source = load_td_source_bundle(**candidate["source"])
    original = load_td_source_bundle(**candidate["original_source_record"])
    hierarchy = load_basin_hierarchy(**candidate["hierarchy"])
    if source["metadata"]["spacing_m"] != original["metadata"]["spacing_m"] or source["metadata"]["origin_m_xz"] != original["metadata"]["origin_m_xz"]:
        raise ValueError("candidate weather world grid mismatch")
    for name in ("valid_mask", "protected_mask", "open_boundary_mask"):
        if not np.array_equal(source["arrays"][name], original["arrays"][name]):
            raise ValueError("candidate weather domain isolation mismatch")
    if hierarchy["metadata"]["source_identity_sha256"] != source["identity_sha256"]:
        raise ValueError("candidate hierarchy/source chain mismatch")
    return dict(topology_record=record, source_record=candidate["source"], hierarchy_record=candidate["hierarchy"],
        geometry_parent_record=parent_record, material_record=parent["inputs"]["material_record"],
        original_source_record=candidate["original_source_record"], morphology_source_scope="previous accepted v8 geometry; recoupled under new v10 physics")


def _plan(baseline_record, topology_records, declared_steps_s):
    if tuple(declared_steps_s) != STEPS or set(topology_records) != set(CANDIDATES):
        raise ValueError("explicit two saved candidates and2.5/1.25 required")
    baseline, cold, ready = _baseline(baseline_record)
    candidates = {name:_candidate(topology_records[name], name, baseline) for name in CANDIDATES}
    arguments = baseline["acceptance_arguments"]
    weather = _json(arguments["weather_index_record"])
    records = {name:case["record"] for name, case in weather["cases"].items()}
    job_order = [dict(candidate_id=name, direction=direction, step_s=step, hours=24)
                 for name in CANDIDATES for direction in ("eastward", "westward") for step in STEPS]
    code_names = execution_dependency_names()
    result = dict(schema=SCHEMA, baseline_acceptance_record=baseline_record, candidate_topology_records=topology_records,
        candidates=candidates, weather_index_record=arguments["weather_index_record"], weather_records=records,
        original_weather_source_record=arguments["source_record"], forcing_identities={name:case["forcing_identity"] for name, case in weather["cases"].items()},
        declared_steps_s=list(STEPS), initial_states=dict(depth_m=0., soil_mm=30., fast_mm=0., slow_mm=0.),
        parameters=PHYSICS, runoff_parameters=asdict(RunoffParameters()), job_order=job_order, total_hour_pages=192,
        baseline_numerical_gate_passed=ready, execution_ready=ready, blocked_reason=None if ready else "baseline numerical gates failed",
        chunk_max_face_steps=6000000000, job_max_bytes=MAX_BYTES, selection="baseline pending", recoupling_required=True,
        flags=FLAGS, code_sha256={name:file_sha256(ROOT/name) for name in code_names}, solver_advanced=False)
    result["identity_sha256"] = _hash(result)
    return result


def prepare_candidate_weather_jobs(baseline_acceptance_record, candidate_topology_records, directory, *, declared_steps_s=STEPS):
    result = _plan(baseline_acceptance_record, candidate_topology_records, declared_steps_s)
    directory = Path(directory).absolute()
    if directory.exists():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".candidate-weather-plan-", dir=directory.parent))
    try:
        _write(staging/"index.json", result)
        _memory()
        for record in [baseline_acceptance_record, *candidate_topology_records.values()]:
            if file_sha256(record["path"]) != record["expected_sha256"]:
                raise ValueError("candidate plan primary input changed")
        _recheck_publication(result, [])
        staging.rename(directory)
        return result
    except BaseException:
        shutil.rmtree(staging)
        raise


def load_candidate_weather_plan(record):
    result = _json(record)
    unsigned = {name:value for name, value in result.items() if name != "identity_sha256"}
    if result.get("schema") != SCHEMA or result.get("identity_sha256") != record.get("expected_identity") or _hash(unsigned) != record.get("expected_identity"):
        raise ValueError("candidate plan external identity rejected")
    expected = _plan(result["baseline_acceptance_record"], result["candidate_topology_records"], result["declared_steps_s"])
    if result != expected:
        raise ValueError("candidate plan semantic readiness/input mismatch")
    _check_execution_dependencies(result["code_sha256"])
    return result


def run_candidate_weather_job(plan_record, directory, *, candidate_id, execute=False):
    plan = load_candidate_weather_plan(plan_record)
    if candidate_id not in CANDIDATES or type(execute) is not bool:
        raise ValueError("explicit saved candidate and execute boolean required")
    if not execute:
        return dict(candidate_id=candidate_id, execution_ready=plan["execution_ready"], solver_advanced=False, selection="baseline pending")
    if plan["execution_ready"] is not True:
        raise ValueError("candidate execution requires baseline all numerical gates passed")
    import os
    if any(os.environ.get(name) != "1" for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")):
        raise ValueError("candidate execution requires predeclared single-thread environment")
    directory = Path(directory).absolute()
    if directory.exists():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    lock = directory.parent/".td-candidate-weather-execution.lock"
    with lock.open("x", encoding="utf8") as stream:
        stream.write(json.dumps(dict(candidate_id=candidate_id, pid=os.getpid(), created_utc=datetime.now(timezone.utc).isoformat())))
    monitor = None
    try:
        from terrain_pipeline.basin_storage import simulate_hour as simulate_hour
        from terrain_pipeline.basin_storage import storagev10_save_storage as save_storage
        from terrain_pipeline.basin_storage import save_checkpoint as save_checkpoint
        from tools.verify_basin_storage_execution import NativeWeatherResourceMonitor as ResourceMonitor
        hierarchy = load_basin_hierarchy(**plan["candidates"][candidate_id]["hierarchy_record"])
        source = plan["original_weather_source_record"]
        weather = _json(plan["weather_index_record"])
        directory.mkdir()
        _write(directory/"run-inputs.json", dict(plan_record=plan_record, candidate_id=candidate_id, plan=plan))
        monitor = ResourceMonitor(psutil.Process())
        monitor.start()
        groups = {}
        for direction in ("eastward", "westward"):
            case = weather["cases"][direction]
            rain = load_native_storm(**case["record"], source_record=source, expected_plan=case["plan"])["arrays"]["rain_mm_h"]
            groups[direction] = {}
            for step in STEPS:
                previous, previous_record, pages = None, None, []
                for hour in range(24):
                    began = time.perf_counter()
                    result = simulate_hour(hierarchy, rain, substep_s=step, checkpoint=previous)
                    page_directory = directory/f"{direction}-{step:g}s"/f"hour-{hour:02d}"
                    save_storage(page_directory/"storage.npz", result["storage"])
                    save_checkpoint(page_directory/"checkpoint.npz", result["checkpoint"])
                    storage_record, checkpoint_record = _pin(page_directory/"storage.npz", result["storage"]), _pin(page_directory/"checkpoint.npz", result["checkpoint"])
                    checked = load_native_weather_v10_hour(storage_record, checkpoint_record, hierarchy=hierarchy, rain_mm_h=rain[hour],
                        forcing_identity=plan["forcing_identities"][direction], hour=hour, step_s=step,
                        parameters=PHYSICS, runoff_parameters=plan["runoff_parameters"], previous_checkpoint_record=previous_record)
                    previous, previous_record = checked["checkpoint"], checkpoint_record
                    elapsed = time.perf_counter() - began
                    pages.append(dict(hour=hour, storage=storage_record, checkpoint=checkpoint_record, forcing_identity=plan["forcing_identities"][direction], budget=checked["budget"], elapsed_s=elapsed))
                    monitor.check()
                    print(f"{directory.name} {candidate_id} {direction} {step:g}s hour{hour + 1}/24 elapsed{elapsed:.3f}s", flush=True)
                    del result, checked
                groups[direction][str(step)] = pages
        for direction in groups.values():
            for pages in direction.values():
                for page in pages:
                    for role in ("storage", "checkpoint"):
                        record = page[role]
                        if file_sha256(record["path"]) != record["expected_sha256"]:
                            raise ValueError("candidate saved page changed before final publication")
        for record in [plan["weather_index_record"], plan["original_weather_source_record"],
                       *plan["weather_records"].values(),
                       *[plan["candidates"][candidate_id][name] for name in ("source_record", "hierarchy_record", "material_record", "geometry_parent_record")]]:
            if file_sha256(record["path"]) != record["expected_sha256"]:
                raise ValueError("candidate external geometry/material/weather changed")
        monitor.stop()
        monitor.check()
        for name, digest in plan["code_sha256"].items():
            if file_sha256(ROOT/name) != digest:
                raise ValueError("candidate execution dependency changed")
        if file_sha256(plan_record["path"]) != plan_record["expected_sha256"]:
            raise ValueError("candidate execution plan changed")
        resource = dict(schema="td-candidate-weather-execution-resource-v1", complete=True, **monitor.record())
        _write(directory/"resource.json", resource)
        result = dict(schema="td-candidate-native-weather-execution-v1", plan_record=plan_record, candidate_id=candidate_id,
            candidates=plan["candidates"][candidate_id], pages=groups, steps_s=list(STEPS), forcing_identities=plan["forcing_identities"],
            resource_record=_pin(directory/"resource.json"), selection="baseline pending", recoupling_required=True,
            flags=FLAGS, code_sha256=plan["code_sha256"], solver_advanced=True)
        result["identity_sha256"] = _hash(result)
        _recheck_publication(plan, [plan_record, result["resource_record"]], groups)
        _write(directory/"index.json", result)
        return result
    except BaseException as error:
        if monitor is not None:
            monitor.stop()
        if directory.exists():
            _write(directory/"failure.json", dict(error=str(error), complete=False, selection="baseline pending", flags=FLAGS))
        raise
    finally:
        lock.unlink()


def _selection_cases(result, baseline_acceptance_record, candidate_final_records, independent_numerical_records):
    if result.get("selection") != "baseline pending" or result.get("flags") != FLAGS or result.get("baseline_acceptance_record") != baseline_acceptance_record:
        raise ValueError("candidate selection claims rejected")
    baseline, cold, ready = _baseline(baseline_acceptance_record)
    if not ready:
        raise ValueError("candidate selection requires numerically passed baseline")
    if set(candidate_final_records) != set(CANDIDATES) or set(independent_numerical_records) != set(CANDIDATES):
        raise ValueError("complete two candidate independent evidence required")
    if result.get("candidate_final_records") != candidate_final_records or result.get("independent_numerical_records") != independent_numerical_records:
        raise ValueError("candidate selection external evidence mismatch")
    summaries = {}
    for candidate_id in CANDIDATES:
        final_record = candidate_final_records[candidate_id]
        execution = _json(final_record)
        signed = {name:value for name, value in execution.items() if name != "identity_sha256"}
        if execution.get("schema") != "td-candidate-native-weather-execution-v1" or execution.get("identity_sha256") != final_record.get("expected_identity") or _hash(signed) != final_record.get("expected_identity"):
            raise ValueError("candidate execution identity rejected")
        plan = load_candidate_weather_plan(execution["plan_record"])
        _check_execution_dependencies(plan["code_sha256"])
        if plan["execution_ready"] is not True or plan["baseline_acceptance_record"] != baseline_acceptance_record or execution.get("candidate_id") != candidate_id or execution.get("candidates") != plan["candidates"][candidate_id] or execution.get("flags") != FLAGS or execution.get("forcing_identities") != plan["forcing_identities"] or execution.get("steps_s") != list(STEPS) or execution.get("code_sha256") != plan["code_sha256"]:
            raise ValueError("candidate execution baseline/geometry claims rejected")
        resource = _json(execution["resource_record"])
        if resource.get("schema") != "td-candidate-weather-execution-resource-v1" or resource.get("complete") is not True or resource.get("monitor_error") is not None or resource.get("sampling_interval_s") != 2 or type(resource.get("sample_count")) is not int or resource["sample_count"] < 1:
            raise ValueError("candidate complete execution resource rejected")
        if any(type(resource.get(name)) is not int or not 0 < resource[name] <= MAX_BYTES for name in ("peak_rss_bytes", "peak_private_bytes")):
            raise ValueError("candidate execution resource exceeded")
        hierarchy = load_basin_hierarchy(**execution["candidates"]["hierarchy_record"])
        weather = _json(plan["weather_index_record"])
        reports = independent_numerical_records[candidate_id]
        if set(reports) != {"eastward", "westward"} or set(execution.get("pages", {})) != {"eastward", "westward"}:
            raise ValueError("candidate directional coverage missing")
        summaries[candidate_id] = {}
        for direction in ("eastward", "westward"):
            case = weather["cases"][direction]
            rain = load_native_storm(**case["record"], source_record=plan["original_weather_source_record"], expected_plan=case["plan"])["arrays"]["rain_mm_h"]
            final_receiver = {}
            groups = execution["pages"][direction]
            if set(groups) != {"2.5", "1.25"}:
                raise ValueError("candidate step coverage missing")
            for step in STEPS:
                pages = groups[str(step)]
                if len(pages) != 24 or [page.get("hour") for page in pages] != list(range(24)):
                    raise ValueError("candidate complete24hour evidence required")
                previous = None
                budgets = []
                for hour, page in enumerate(pages):
                    from terrain_pipeline.td_native_weather_storage_io import _layout
                    group = Path(final_record["path"]).parent/f"{direction}-{step:g}s"
                    _layout(page["storage"], group/f"hour-{hour:02d}"/"storage.npz")
                    _layout(page["checkpoint"], group/f"hour-{hour:02d}"/"checkpoint.npz")
                    checked = load_native_weather_v10_hour(page["storage"], page["checkpoint"], hierarchy=hierarchy, rain_mm_h=rain[hour],
                        forcing_identity=plan["forcing_identities"][direction], hour=hour, step_s=step, parameters=PHYSICS,
                        runoff_parameters=plan["runoff_parameters"], previous_checkpoint_record=previous)
                    previous = page["checkpoint"]
                    budgets.append(checked["budget"])
                    final_receiver[step] = checked["checkpoint"]["arrays"]["cumulative_routed_volume_m3"]
                rain_sum = math.fsum(item["rain_m3"] for item in budgets)
                residual = math.fsum([budgets[0]["initial_water_m3"], rain_sum, -math.fsum(item["loss_m3"] for item in budgets),
                                     -math.fsum(item["external_m3"] for item in budgets), -budgets[-1]["final_water_m3"]])
                if abs(residual) > 1e-6+rain_sum*1e-10:
                    raise ValueError("candidate cumulative whole budget failed")
            maximum = 0.
            for first, second in zip(groups["2.5"], groups["1.25"]):
                coarse, fine = load_storage(**first["storage"]), load_storage(**second["storage"])
                maximum = max(maximum, float(abs(coarse["arrays"]["depth_m"]-fine["arrays"]["depth_m"]).max()))
                del coarse, fine
            relative = float(abs(final_receiver[2.5]-final_receiver[1.25]).sum()/max(1e-12, final_receiver[1.25].sum()))
            gate = maximum <= .001 and relative <= .01
            report = _json(reports[direction])
            if (report.get("schema") != "td-independent-candidate-weather-v1" or report.get("candidate_final_record") != final_record
                    or report.get("candidate_id") != candidate_id or report.get("direction") != direction
                    or report.get("hierarchy_record") != execution["candidates"]["hierarchy_record"]
                    or report.get("forcing_identity") != plan["forcing_identities"][direction]
                    or report.get("max_saved_depth_difference_m") != maximum or report.get("cumulative_receiver_relative_l1") != relative
                    or report.get("gate_passed") is not gate or report.get("solver_advanced") is not False
                    or any(report.get(name) is not True for name in ("full_spatial_rain_checked", "compartment_ledgers_checked", "checkpoint_chain_checked", "whole_period_budget_passed"))):
                raise ValueError("candidate independent raw report binding rejected")
            summaries[candidate_id][direction] = dict(numerical_gate_passed=gate, max_saved_depth_difference_m=maximum, cumulative_receiver_relative_l1=relative)
            if file_sha256(reports[direction]["path"]) != reports[direction]["expected_sha256"]:
                raise ValueError("candidate independent report changed")
        if file_sha256(final_record["path"]) != final_record["expected_sha256"]:
            raise ValueError("candidate complete index changed")
        _recheck_publication(plan, [final_record, execution["plan_record"], execution["resource_record"], *reports.values()], execution["pages"])
    _memory()
    return summaries


def load_candidate_weather_selection(path, *, expected_sha256, expected_identity, baseline_acceptance_record,
                                     candidate_final_records, independent_numerical_records):
    result = _json(dict(path=str(path), expected_sha256=expected_sha256))
    unsigned = {name:value for name, value in result.items() if name != "identity_sha256"}
    if result.get("schema") != "td-candidate-weather-selection-v1" or _hash(unsigned) != expected_identity or result.get("identity_sha256") != expected_identity:
        raise ValueError("candidate selection external identity/schema rejected")
    summaries = _selection_cases(result, baseline_acceptance_record, candidate_final_records, independent_numerical_records)
    if result.get("cases") != summaries:
        raise ValueError("candidate selection numerical summary mismatch")
    if file_sha256(path) != expected_sha256:
        raise ValueError("candidate selection pin changed")
    return result


def publish_candidate_weather_selection(directory, *, baseline_acceptance_record, candidate_final_records,
                                       independent_numerical_records):
    result = dict(schema="td-candidate-weather-selection-v1", baseline_acceptance_record=baseline_acceptance_record,
        candidate_final_records=candidate_final_records, independent_numerical_records=independent_numerical_records,
        selection="baseline pending", recoupling_required=True, flags=FLAGS)
    result["cases"] = _selection_cases(result, baseline_acceptance_record, candidate_final_records, independent_numerical_records)
    result["identity_sha256"] = _hash(result)
    directory = Path(directory).absolute()
    if directory.exists():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".candidate-selection-", dir=directory.parent))
    try:
        _write(staging/"index.json", result)
        _memory()
        staging.rename(directory)
        return result
    except BaseException:
        shutil.rmtree(staging)
        raise


def export_candidate_weather_review(selection_record, directory, *, output_budget_bytes=512*1024*1024,
                                    include_hour_flux=False):
    from terrain_pipeline.td_native_weather_v10_review import _payloads, estimate_native_weather_v10_review
    from terrain_pipeline.td_hour_pages_review import _artifact
    raw = _json(selection_record)
    selection = load_candidate_weather_selection(selection_record["path"], expected_sha256=selection_record["expected_sha256"],
        expected_identity=selection_record["expected_identity"], baseline_acceptance_record=raw["baseline_acceptance_record"],
        candidate_final_records=raw["candidate_final_records"], independent_numerical_records=raw["independent_numerical_records"])
    if type(output_budget_bytes) is not int or not 0 < output_budget_bytes <= MAX_BYTES or type(include_hour_flux) is not bool:
        raise ValueError("candidate review explicit bounded output selection required")
    executions, hierarchies = {}, {}
    for candidate_id, record in selection["candidate_final_records"].items():
        executions[candidate_id] = _json(record)
        hierarchies[candidate_id] = load_basin_hierarchy(**executions[candidate_id]["candidates"]["hierarchy_record"])
    estimate = sum(estimate_native_weather_v10_review(value, include_hour_flux=include_hour_flux)["estimated_output_upper_bytes"] for value in hierarchies.values())
    if estimate > output_budget_bytes:
        raise ValueError("candidate combined review output estimate exceeds budget")
    directory = Path(directory).absolute()
    if directory.exists():
        raise FileExistsError(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".candidate-review-", dir=directory.parent))
    try:
        pages, written = [], 0
        for candidate_id in CANDIDATES:
            target = staging/candidate_id
            target.mkdir()
            index = dict(scenarios={direction:dict(pages=groups) for direction, groups in executions[candidate_id]["pages"].items()})
            for number, value in enumerate(_payloads(hierarchies[candidate_id], index, include_hour_flux)):
                record, payload = _artifact(value, number)
                written += len(payload)
                if written > output_budget_bytes:
                    raise ValueError("candidate actual review output budget exceeded")
                publish_bytes(target/record["file"], payload)
                if file_sha256(target/record["file"]) != record["expected_sha256"]:
                    raise ValueError("candidate review saved byte verification failed")
                record = dict(record, candidate_id=candidate_id, file=candidate_id+"/"+record["file"])
                pages.append(record)
        result = dict(schema="td-candidate-weather-native-review-v1", selection_record=selection_record, cases=selection["cases"],
            pages=pages, frames=25, selected_steps_s=[1.25], include_hour_flux=include_hour_flux, artifact_bytes=written,
            output_budget_bytes=output_budget_bytes, estimated_output_upper_bytes=estimate,
            hierarchy_records={name:value["candidates"]["hierarchy_record"] for name, value in executions.items()},
            candidate_final_records=selection["candidate_final_records"], flags=FLAGS, water_interpolation=False,
            selection="baseline pending", semantics="Native derived-bed plus saved depth samples; no uniform lake stage, width or natural outlet certification")
        result["identity_sha256"] = _hash(result)
        payload = json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf8")
        if len(payload) > 8*1024*1024 or written+len(payload) > output_budget_bytes:
            raise ValueError("candidate final review root bytes exceeded")
        publish_bytes(staging/"index.json", payload)
        _memory()
        if file_sha256(selection_record["path"]) != selection_record["expected_sha256"]:
            raise ValueError("candidate review external selection changed")
        staging.rename(directory)
        return result
    except BaseException:
        shutil.rmtree(staging)
        raise
