"""Strict external-pin acceptance of final v8 hour pages, without solver imports."""

import math
from pathlib import Path
import re

import numpy as np
import psutil

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, file_sha256
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_storage_dispatch_io import _storage_headers
from terrain_pipeline.td_basin_spill_network import _read_json
from terrain_pipeline.td_surface_reaches import _freeze
from terrain_pipeline.rainfall_runoff import RunoffParameters

STATES = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
FLUXES = ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s", "routed_volume_m3", "wet_duration_s")
PROFILE = "v8-hour-pages-v7-SSPRK2"
TIME_SEMANTICS = "state0 is checkpoint time; state[k] at chunk_start_s+k*dt_s; ledger[k] covers local hour k"


def _memory():
    info = psutil.Process().memory_info()
    rss = int(getattr(info, "peak_wset", info.rss))
    private = getattr(info, "peak_pagefile", None)
    if max(rss, private or 0) > 1073741824:
        raise MemoryError("acceptance process peak RSS/private exceeds 1GiB")
    return rss, private


def _config(config, step):
    limits = {"substep_s": 86400, "face_conductance_m_s": 1000,
              "surface_evaporation_mm_h": 1e6, "wet_threshold_m": 1000,
              "max_substeps": 10000000, "max_work_face_steps": 6000000000}
    if set(config) != set(limits):
        raise ValueError("unknown configuration fields")
    for name, maximum in limits.items():
        value = config[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= maximum:
            raise ValueError("invalid configuration value")
        if name.startswith("max_") and (type(value) is not int or value < 1):
            raise ValueError("invalid integer work budget")
    if config["substep_s"] != step:
        raise ValueError("configuration differs from predeclared step")


def _sha(value):
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("external SHA/identity required")
    return value


def _json(record, max_bytes=16 * 1024 * 1024):
    path = Path(record["path"])
    if not path.is_file() or path.stat().st_size > max_bytes or file_sha256(path) != _sha(record["expected_sha256"]):
        raise ValueError("missing final input or external JSON SHA/budget mismatch")
    return _read_json(path)


def _layout(record, expected):
    path = Path(record["path"])
    if any(parent.is_symlink() for parent in (path, *path.parents)) or path.absolute() != expected.absolute() or path.resolve(strict=True) != expected.resolve(strict=True):
        raise ValueError("page artifact must match declared canonical run layout")
    return path


def _identity_check(result):
    if identity(result["arrays"], result["metadata"]) != result["identity_sha256"]:
        raise ValueError("saved page/checkpoint content identity mismatch")


def _checkpoint_headers(headers):
    shape, dtype = headers.get("depth_m", ((), np.dtype("O")))
    if len(shape) != 1 or not 1 <= shape[0] <= 250000 or dtype != np.float64:
        raise ValueError("checkpoint state allocation rejection")
    faces, face_dtype = headers.get("cumulative_face_forward_m3", ((), np.dtype("O")))
    if len(faces) != 1 or faces[0] > 2 * shape[0] or face_dtype != np.float64:
        raise ValueError("checkpoint face allocation rejection")
    expected = {name: (shape, np.dtype("float64")) for name in STATES + ("error_depth", "error_soil", "error_fast", "error_slow")}
    for name in FLUXES:
        expected["cumulative_" + name] = (shape if name in ("routed_volume_m3", "wet_duration_s") else faces, np.dtype("float64"))
    if set(headers) != set(expected) | {"manifest"} or any(headers.get(name) != value for name, value in expected.items()):
        raise ValueError("checkpoint exact header layout mismatch")


def _load(record, checkpoint=False):
    result = load_bundle(record["path"], expected_sha256=_sha(record["expected_sha256"]), validator=_identity_check,
                         max_bytes=(128 if checkpoint else 256) * 1024 * 1024,
                         header_validator=_checkpoint_headers if checkpoint else _storage_headers)
    if result["identity_sha256"] != _sha(record["expected_identity"]):
        raise ValueError("external saved content identity mismatch")
    _memory()
    return result


def _flags(metadata):
    for name in ("hydraulic_ready", "transient_converged"):
        if metadata.get(name) is not False:
            raise ValueError("unsupported page/checkpoint certification")
    for name in ("natural_outlet_verified", "publishable", "morphology_flux_ready"):
        if name in metadata and metadata[name] is not False:
            raise ValueError("unsupported certification")


def _near(actual, expected, *, allowed=None):
    actual, expected = np.asarray(actual), np.asarray(expected)
    tolerance = 1e-6 + 1e-10 * abs(expected) if allowed is None else allowed
    if not np.isfinite(actual).all() or not np.isfinite(expected).all() or np.any(abs(actual - expected) > tolerance):
        raise ValueError("original saved water budget/ledger gate failed")


def _hour(storage, hierarchy, hour, step, rain, forcing_id, dt, config, runoff):
    arrays, metadata = storage["arrays"], storage["metadata"]
    topology = hierarchy["arrays"]
    if metadata.get("schema") != "td-basin-storage-v1" or metadata.get("algorithm") != "D4-threshold-checkpoint-SSPRK2-v8" or metadata.get("work_profile") != PROFILE:
        raise ValueError("unknown hour page version/profile")
    _flags(metadata)
    expected = {"hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": hierarchy["metadata"]["spacing_m"],
                "origin_m_xz": hierarchy["metadata"]["origin_m_xz"], "dt_s": dt, "substep_s": step,
                "chunk_start_s": hour * dt, "chunk_end_s": (hour + 1) * dt,
                "forcing_identity": forcing_id, "forcing_hour_offset": hour, "substeps": int(dt / step),
                "parameters": config, "runoff_parameters": runoff, "saved_time_semantics": TIME_SEMANTICS}
    if any(metadata.get(name) != value for name, value in expected.items()) or type(metadata["substeps"]) is not int or type(metadata["forcing_hour_offset"]) is not int:
        raise ValueError("hour page forcing/time/config/hierarchy mismatch")
    semantics = {
        "forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
        "activity_semantics": "RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity",
        "compensation_semantics": "soil/fast/slow increments and forcing ledgers compensated; ledger errors reset hourly; depth error reset after transport replacement; exact full-inventory removal retires compensation"}
    if any(metadata.get(name) != value for name, value in semantics.items()):
        raise ValueError("unknown v8 numerical semantics")
    if metadata["substeps"] > config["max_substeps"] or metadata["substeps"] * len(topology["face_cells"]) > config["max_work_face_steps"]:
        raise ValueError("hour page actual work exceeds declared budget")
    for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
        if not np.array_equal(arrays[name], topology[name]):
            raise ValueError("page original geometry/coverage mismatch")
    valid = topology["valid_mask"].ravel()
    cells = len(valid)
    if arrays["wet_pool_count"].dtype != np.int64 or arrays["wet_pool_count"].shape != (2,) or np.any(arrays["wet_pool_count"] > valid.sum()):
        raise ValueError("invalid wet pool counts")
    area = metadata["spacing_m"] ** 2
    for name, values in arrays.items():
        if not np.isfinite(values).all() or name not in ("height_m", "receiver", "internal_net_m3", "storage_change_m3", "balance_residual_m3") and np.any(values < 0):
            raise ValueError("negative/nonfinite saved state or account")
    for name in STATES:
        if arrays[name].shape != (2, cells) or arrays[name].dtype != np.float64 or np.any(arrays[name][:, ~valid] != 0):
            raise ValueError("hour state shape/unknown inventory mismatch")
    if arrays["rain_mm_h"].shape != (1, cells) or not np.array_equal(arrays["rain_mm_h"][0], np.where(valid, rain, 0)):
        raise ValueError("hour complete-forcing slice mismatch")
    boundary = arrays["boundary_cells"]
    rows, columns = topology["height_m"].shape
    boundary_rows, boundary_columns = np.divmod(boundary, columns)
    widths = metadata["spacing_m"] * ((boundary_rows == 0).astype(int) + (boundary_rows == rows - 1) + (boundary_columns == 0) + (boundary_columns == columns - 1))
    if not np.array_equal(arrays["boundary_width_m"], widths):
        raise ValueError("page exterior width mismatch")
    declared = np.zeros(cells, bool)
    declared[boundary] = True
    if np.any(arrays["boundary_outflow_m3"][:, ~declared] != 0):
        raise ValueError("undeclared page exterior export")
    degree = np.bincount(arrays["face_cells"].ravel(), minlength=cells).astype(float)
    np.add.at(degree, boundary, widths / metadata["spacing_m"])
    cfl = float(degree.max(initial=0)) * config["face_conductance_m_s"] * step / metadata["spacing_m"]
    if cfl > 1 or metadata.get("positivity_cfl") != cfl:
        raise ValueError("hour actual CFL mismatch")
    stores = arrays["depth_m"] + sum(arrays[name] for name in ("soil_mm", "fast_mm", "slow_mm")) / 1000
    changes = np.diff(stores, axis=0) * area
    rain_volume = arrays["rain_mm_h"] * (dt / 3600) * area / 1000
    _near(arrays["rain_volume_m3"], rain_volume)
    _near(arrays["lake_rain_m3"] + arrays["land_rain_m3"], rain_volume)
    _near(arrays["storage_change_m3"], changes)
    expected_change = rain_volume + arrays["internal_net_m3"] - arrays["soil_et_m3"] - arrays["surface_et_m3"] - arrays["boundary_outflow_m3"]
    _near(changes, expected_change)
    _near(arrays["balance_residual_m3"], expected_change - changes)
    forward, reverse = arrays["face_forward_m3"], arrays["face_reverse_m3"]
    first, second = arrays["face_cells"].T
    net = forward - reverse
    divergence = np.bincount(second, weights=net, minlength=cells) - np.bincount(first, weights=net, minlength=cells)
    _near(arrays["internal_net_m3"].sum(axis=0), divergence)
    expected_routed, expected_duration = np.zeros(cells), np.zeros(cells)
    receiver = arrays["receiver"]
    for source, target, flow, duration in ((first, second, forward, arrays["active_forward_s"]), (second, first, reverse, arrays["active_reverse_s"])):
        np.add.at(expected_routed, source, np.where(receiver[source] == target, flow, 0))
        np.add.at(expected_duration, source, np.where(receiver[source] == target, duration, 0))
        if np.any((flow == 0) & (duration != 0)):
            raise ValueError("duration without directional volume")
    _near(arrays["routed_volume_m3"], expected_routed)
    _near(arrays["wet_duration_s"], expected_duration)
    if np.any(arrays["active_forward_s"] + arrays["active_reverse_s"] > dt + 1e-8) or np.any(arrays["wet_duration_s"] > dt + 1e-8):
        raise ValueError("hour activity exceeds actual physical interval")
    rain_total = math.fsum(rain_volume[0].tolist())
    losses = math.fsum((arrays["soil_et_m3"][0] + arrays["surface_et_m3"][0]).tolist())
    external = math.fsum(arrays["boundary_outflow_m3"][0].tolist())
    change = math.fsum(changes[0].tolist())
    _near(rain_total, losses + external + change)
    _near(math.fsum(arrays["internal_net_m3"][0].tolist()), 0, allowed=1e-6 + rain_total * 1e-10)
    return {"rain_m3": rain_total, "loss_m3": losses, "external_m3": external,
            "change_m3": change, "residual_m3": rain_total - losses - external - change,
            "initial_water_m3": math.fsum(stores[0].tolist()) * area,
            "final_water_m3": math.fsum(stores[-1].tolist()) * area}


def load_hour_pages_index(path, *, expected_sha256, forcing_records, run_inputs_record, hierarchy_record,
                          execution_resource_record, declared_steps_s=(2.5, 1.25), code_root=None):
    """Accept only complete 24-hour, externally pinned v8 records; stream one page."""
    path = Path(path)
    if path.name != "index.json":
        raise ValueError("final index.json required")
    index = _json({"path": str(path), "expected_sha256": expected_sha256})
    resource = _json(execution_resource_record)
    if resource.get("index_sha256") != expected_sha256 or resource.get("scope") != "complete ordinary+strong both steps execution" or resource.get("complete") is not True:
        raise ValueError("complete external execution resource evidence required")
    for name in ("peak_rss_bytes", "peak_private_bytes"):
        if type(resource.get(name)) is not int or not 0 < resource[name] <= 1073741824:
            raise ValueError("execution peak RSS/private exceeds or lacks 1GiB evidence")
    if index.get("schema") != "td-storage-hour-pages-index-v1" or tuple(declared_steps_s) != (2.5, 1.25):
        raise ValueError("unknown final schema or undeclared exact step pair")
    _flags(index)
    root = path.parent.resolve()
    inputs = _json(run_inputs_record)
    _layout(run_inputs_record, root / "run-inputs.json")
    if inputs.get("profile") != PROFILE or inputs.get("steps_s") != [2.5, 1.25] or inputs.get("depth_gate_m") != .001 or inputs.get("receiver_gate") != .01:
        raise ValueError("run-inputs profile/schedule/gates mismatch")
    hierarchy = load_basin_hierarchy(**hierarchy_record)
    if inputs["hierarchy"] != {"path": hierarchy_record["path"], "sha256": hierarchy_record["expected_sha256"], "identity": hierarchy_record["expected_identity"]}:
        raise ValueError("external hierarchy differs from run declaration")
    if index.get("code_sha256") != inputs.get("code_sha256") or not index.get("code_sha256"):
        raise ValueError("final frozen code identity mismatch")
    if code_root is not None:
        code_root = Path(code_root).resolve()
        for name, digest in index["code_sha256"].items():
            target = (code_root / name).resolve()
            if not target.is_relative_to(code_root) or file_sha256(target) != _sha(digest):
                raise ValueError("frozen code changed or invalid layout")
    scenarios = index["scenarios"]
    if set(scenarios) != {"ordinary", "strong"} or set(forcing_records) != set(scenarios):
        raise ValueError("complete ordinary/strong forcing records required")
    summaries = {}
    shared_parameters = None
    shared_runoff = None
    face_count = len(hierarchy["arrays"]["face_cells"])
    expected_budgets = {str(step): {"chunk_face_steps": int(3600 / step) * face_count,
        "global_face_steps_per_scenario": 24 * int(3600 / step) * face_count} for step in declared_steps_s}
    if inputs.get("budgets") != expected_budgets or index.get("budgets") != expected_budgets or inputs.get("chunk_max_work_face_steps") != 6000000000 or inputs.get("job_max_bytes") != 1073741824 or any(item["chunk_face_steps"] > 6000000000 for item in expected_budgets.values()):
        raise ValueError("actual chunk/global/resource declaration mismatch")
    for scenario, comparison in scenarios.items():
        _flags(comparison)
        forcing = _json(forcing_records[scenario], 1024 * 1024)
        _layout(forcing_records[scenario], root / (scenario + "-forcing.json"))
        rain = np.asarray(forcing["rain_mm_h"], np.float64)
        dt = forcing["dt_s"]
        if rain.shape != (24,) or not np.isfinite(rain).all() or np.any((rain < 0) | (rain > 1e6)) or dt != 3600.:
            raise ValueError("full forcing 24-hour/time coverage mismatch")
        forcing_id = identity({"rain_mm_h": rain}, {"dt_s": dt})
        if forcing_id != forcing.get("identity") or forcing_id != forcing_records[scenario].get("expected_identity"):
            raise ValueError("external complete forcing content identity mismatch")
        groups = comparison["pages"]
        if set(groups) != {"2.5", "1.25"}:
            raise ValueError("exact caller-declared step groups required")
        step_summaries = {}
        final_routed = {}
        for step in declared_steps_s:
            pages = groups[str(step)]
            if len(pages) != 24 or [page["hour"] for page in pages] != list(range(24)):
                raise ValueError("24 hour coverage/order mismatch")
            group_directory = root / f"{scenario}-{step:g}s"
            if {item.name for item in group_directory.iterdir() if item.is_dir()} != {f"hour-{hour:02d}" for hour in range(24)}:
                raise ValueError("missing/extra hour directory coverage")
            previous = None
            budgets = []
            config = runoff = None
            for hour, page in enumerate(pages):
                if type(page["hour"]) is not int or page.get("forcing_identity") != forcing_id or page.get("chunk_work_face_steps") != expected_budgets[str(step)]["chunk_face_steps"] or not 0 <= page.get("peak_bytes", -1) <= 1073741824:
                    raise ValueError("page record forcing/work/resource mismatch")
                directory = root / f"{scenario}-{step:g}s" / f"hour-{hour:02d}"
                _layout(page["storage"], directory / "storage.npz")
                _layout(page["checkpoint"], directory / "checkpoint.npz")
                storage, checkpoint = _load(page["storage"]), _load(page["checkpoint"], True)
                arrays, metadata = storage["arrays"], storage["metadata"]
                saved, cp_metadata = checkpoint["arrays"], checkpoint["metadata"]
                if hour == 0:
                    config, runoff = dict(metadata["parameters"]), dict(metadata["runoff_parameters"])
                    RunoffParameters(**runoff)
                    _config(config, step)
                    physical_parameters = {name: value for name, value in config.items() if name != "substep_s"}
                    if shared_parameters is None:
                        shared_parameters, shared_runoff = physical_parameters, runoff
                    elif physical_parameters != shared_parameters or runoff != shared_runoff:
                        raise ValueError("refinement/scenario physical parameters or runoff differ")
                    if np.any(arrays["depth_m"][0] != 0):
                        raise ValueError("first page violates declared zero depth")
                    for name, key in (("soil_mm", "initial_soil_mm"), ("fast_mm", "initial_fast_mm"), ("slow_mm", "initial_slow_mm")):
                        if not np.array_equal(arrays[name][0], np.where(hierarchy["arrays"]["valid_mask"].ravel(), runoff[key], 0)):
                            raise ValueError("first page initial runoff stores mismatch")
                budgets.append(_hour(storage, hierarchy, hour, step, rain[hour], forcing_id, dt, config, runoff))
                _flags(cp_metadata)
                expected_cp = {"schema": "td-storage-continuation-v1", "execution_profile": PROFILE,
                    "hierarchy_identity_sha256": hierarchy["identity_sha256"], "parameters": config, "runoff_parameters": runoff,
                    "forcing_identity": forcing_id, "dt_s": dt, "substep_s": step, "elapsed_s": (hour + 1) * dt,
                    "substeps": (hour + 1) * int(dt / step), "work_face_steps": (hour + 1) * int(dt / step) * face_count,
                    "cells": hierarchy["arrays"]["height_m"].size, "faces": face_count,
                    "last_page_storage_identity": storage["identity_sha256"]}
                if any(cp_metadata.get(name) != value for name, value in expected_cp.items()):
                    raise ValueError("checkpoint real page/config/time/work identity chain mismatch")
                if any(type(cp_metadata[name]) is not int for name in ("substeps", "work_face_steps", "cells", "faces")):
                    raise ValueError("checkpoint integer counts required")
                for name, values in saved.items():
                    if not np.isfinite(values).all() or not name.startswith("error_") and np.any(values < 0):
                        raise ValueError("negative/nonfinite checkpoint inventory/account")
                for name in STATES:
                    if not np.array_equal(saved[name], arrays[name][-1]) or previous is not None and not np.array_equal(arrays[name][0], previous[name]):
                        raise ValueError("checkpoint endpoint or previous complete inventory mismatch")
                for name in ("error_depth", "error_soil", "error_fast", "error_slow"):
                    if np.any(saved[name][~hierarchy["arrays"]["valid_mask"].ravel()] != 0):
                        raise ValueError("checkpoint unknown compensation inventory")
                for name in FLUXES:
                    expected_sum = arrays[name] if previous is None else previous["cumulative_" + name] + arrays[name]
                    if not np.array_equal(saved["cumulative_" + name], expected_sum):
                        raise ValueError("checkpoint cumulative physical face/receiver chain mismatch")
                if np.any(saved["cumulative_active_forward_s"] + saved["cumulative_active_reverse_s"] > (hour + 1) * dt + 1e-8) or np.any(saved["cumulative_wet_duration_s"] > (hour + 1) * dt + 1e-8):
                    raise ValueError("checkpoint cumulative activity exceeds elapsed time")
                previous = saved
                del storage, arrays, checkpoint, expected_sum
            rain_total = math.fsum(item["rain_m3"] for item in budgets)
            residual = math.fsum([budgets[0]["initial_water_m3"], rain_total, -math.fsum(item["loss_m3"] for item in budgets),
                                  -math.fsum(item["external_m3"] for item in budgets), -budgets[-1]["final_water_m3"]])
            _near(residual, 0, allowed=1e-6 + rain_total * 1e-10)
            step_summaries[str(step)] = {"hours": 24, "whole_residual_m3": residual, "whole_allowed_m3": 1e-6 + rain_total * 1e-10,
                                       "forcing_identity": forcing_id, "checkpoint_chain_accepted": True}
            final_routed[step] = previous["cumulative_routed_volume_m3"].copy()
            del previous
        receiver = float(abs(final_routed[2.5] - final_routed[1.25]).sum() / max(1e-12, final_routed[1.25].sum()))
        maximum = 0.
        for coarse, fine in zip(groups["2.5"], groups["1.25"]):
            first, second = _load(coarse["storage"]), _load(fine["storage"])
            maximum = max(maximum, float(abs(first["arrays"]["depth_m"] - second["arrays"]["depth_m"]).max(initial=0)))
            del first, second
        gate = maximum <= .001 and receiver <= .01
        if comparison.get("max_saved_depth_difference_m") != maximum or comparison.get("cumulative_receiver_relative_l1") != receiver or comparison.get("gate_passed") is not gate:
            raise ValueError("final numerical comparison differs from actual pages")
        summaries[scenario] = {"steps": step_summaries, "depth_difference_m": maximum, "receiver_relative_l1": receiver, "numerical_gate_passed": gate}
    if index.get("all_numerical_gates_passed") is not all(value["numerical_gate_passed"] for value in summaries.values()):
        raise ValueError("final numerical summary claim mismatch")
    peak_rss, peak_private = _memory()
    return _freeze({"schema": "td-hour-pages-acceptance-v1", "index_sha256": expected_sha256, "scenarios": summaries,
                    "resource": {"peak_rss_bytes": peak_rss, "peak_private_bytes": peak_private,
                        "loader_within_1GiB": peak_private is not None,
                        "execution_private_budget_verified": True,
                        "execution_resource_sha256": execution_resource_record["expected_sha256"]},
                    "io_chain_accepted": True, "solver_advanced": False, "hydraulic_ready": False,
                    "transient_converged": False, "natural_outlet_verified": False, "publishable": False,
                    "limitations": "Saved endpoint and cumulative evidence verified, not solver reexecution. Compensation arrays are finite signed opaque state; no page-start compensation witness exists in v8. IO acceptance never certifies physics or natural outlets."})
