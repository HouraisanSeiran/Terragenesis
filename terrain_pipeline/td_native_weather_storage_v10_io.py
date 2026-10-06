"""Pinned v10 native-weather page and checkpoint acceptance without execution."""

import math
from dataclasses import asdict
from pathlib import Path

import numpy as np
import psutil

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.td_basin_storage_v10_io import PROFILE, STATES, ERRORS, FLUX, load_storage, load_checkpoint
from terrain_pipeline.td_native_weather_storage_io import _json, _layout, _sha
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from terrain_pipeline.td_basin_source import load_td_source_bundle, PRIMARY_PATH, PRIMARY_SHA256
from terrain_pipeline.td_native_storm_forcing import load_native_storm
from terrain_pipeline.rainfall_runoff import RunoffParameters

MAX_BYTES = 1073741824
STEPS = (2.5, 1.25)
PHYSICS = dict(runoff=[15.,150.,.15,1.,3600.,259200.], face_conductance_m_s=.6,
               surface_evaporation_mm_h=.15, forcing_profile="v10-unified-rain-surface-infiltration-experimental-v1")
PHYSICS_SEMANTICS = "all valid cells experimentally permeable; rain first accesses finite capacity, remaining capacity draws surface water; rain excess enters unchanged fast store; ordered ET/percolation; no wet bypass"


def _flags(metadata, require_transient=True):
    for name in ("hydraulic_ready", "publishable", "transient_converged", "natural_outlet_verified", "morphology_flux_ready"):
        if (name in ("hydraulic_ready", "publishable") or name == "transient_converged" and require_transient or name in metadata) and metadata.get(name) is not False:
            raise ValueError("v10 certification flag must remain false: " + name)


def _equal(actual, expected, label):
    actual, expected = np.asarray(actual), np.asarray(expected)
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError("v10 " + label + " shape/nonfinite mismatch")
    if np.any(abs(actual - expected) > 1e-6 + abs(expected) * 1e-10):
        raise ValueError("v10 " + label + " mismatch")


def validate_native_v10_accounts(storage, *, hierarchy, rain_mm_h):
    arrays, metadata = storage["arrays"], storage["metadata"]
    topology = hierarchy["arrays"]
    if metadata.get("profile") != PROFILE or metadata.get("hierarchy_identity") != hierarchy["identity_sha256"]:
        raise ValueError("v10 profile/hierarchy mismatch")
    if metadata.get("spacing_m") != hierarchy["metadata"]["spacing_m"] or metadata.get("origin_m_xz") != hierarchy["metadata"]["origin_m_xz"]:
        raise ValueError("v10 hierarchy grid mismatch")
    if topology["protected_mask"].any():
        raise ValueError("v10 fresh protected domain rejected")
    for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
        if arrays[name].dtype != topology[name].dtype or not np.array_equal(arrays[name], topology[name]):
            raise ValueError("v10 original topology mismatch: " + name)
    valid = topology["valid_mask"].ravel()
    cells = len(valid)
    rain = np.asarray(rain_mm_h)
    if rain.dtype != np.float64 or rain.shape != topology["height_m"].shape or not np.isfinite(rain).all() or np.any(rain < 0) or np.any(rain.ravel()[~valid] != 0):
        raise ValueError("v10 native forcing shape/unknown rejected")
    if not np.array_equal(arrays["rain_mm_h"], rain.reshape(1, cells)):
        raise ValueError("v10 full forcing hour slice mismatch")
    for name in STATES:
        if arrays[name].dtype != np.float64:
            raise ValueError("v10 state dtype mismatch")
    for name, values in arrays.items():
        if name not in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells") and values.dtype != np.float64:
            raise ValueError("v10 numeric account dtype mismatch")
    area = metadata["spacing_m"] ** 2
    _equal(arrays["rain_volume_m3"], rain.reshape(1, cells) * area / 1000., "native rain volume")
    _equal(arrays["rain_volume_m3"], arrays["rain_infiltration_m3"] + arrays["rain_excess_m3"], "rain allocation")
    infiltration = arrays["rain_infiltration_m3"] + arrays["surface_infiltration_m3"]
    capacity = arrays["infiltration_capacity_m3"]
    cap_upper = metadata["runoff_parameters"]["infiltration_capacity_mm_h"] * area / 1000.
    if np.any(infiltration > capacity + 1e-8) or np.any(capacity > cap_upper + 1e-8):
        raise ValueError("v10 infiltration capacity mismatch")
    if np.any(arrays["soil_mm"] > metadata["runoff_parameters"]["soil_capacity_mm"] + 1e-8):
        raise ValueError("v10 soil capacity exceeded")
    soil_change = np.diff(arrays["soil_mm"], axis=0) * area / 1000.
    pool_change = np.diff(arrays["fast_mm"] + arrays["slow_mm"], axis=0) * area / 1000.
    surface_change = np.diff(arrays["depth_m"], axis=0) * area
    _equal(soil_change, infiltration - arrays["soil_et_m3"] - arrays["percolation_m3"], "soil compartment")
    _equal(pool_change, arrays["rain_excess_m3"] + arrays["percolation_m3"] - arrays["local_release_m3"], "fast slow compartments")
    _equal(surface_change, arrays["local_release_m3"] - arrays["surface_infiltration_m3"] - arrays["surface_et_m3"] + arrays["internal_net_m3"] - arrays["boundary_outflow_m3"], "surface compartment")
    boundary = arrays["boundary_cells"]
    rows, columns = np.divmod(boundary, topology["height_m"].shape[1])
    widths = metadata["spacing_m"] * ((rows == 0).astype(int) + (rows == topology["height_m"].shape[0]-1) + (columns == 0) + (columns == topology["height_m"].shape[1]-1))
    if not np.array_equal(arrays["boundary_width_m"], widths):
        raise ValueError("v10 boundary physical widths mismatch")
    declared = np.zeros(cells, bool)
    declared[boundary] = True
    if np.any(arrays["boundary_outflow_m3"][:, ~declared] != 0):
        raise ValueError("v10 undeclared boundary outflow")
    first, second = arrays["face_cells"].T
    net = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    divergence = np.bincount(second, weights=net, minlength=cells) - np.bincount(first, weights=net, minlength=cells)
    _equal(arrays["internal_net_m3"][0], divergence, "face divergence")
    routed, duration = np.zeros(cells), np.zeros(cells)
    for source, target, volume, activity in ((first, second, arrays["face_forward_m3"], arrays["active_forward_s"]), (second, first, arrays["face_reverse_m3"], arrays["active_reverse_s"])):
        follows = arrays["receiver"][source] == target
        np.add.at(routed, source, np.where(follows, volume, 0.))
        np.add.at(duration, source, np.where(follows, activity, 0.))
        if np.any((volume == 0) & (activity != 0)):
            raise ValueError("v10 activity without directional volume")
    _equal(arrays["routed_volume_m3"], routed, "receiver volume")
    _equal(arrays["wet_duration_s"], duration, "receiver activity")
    if np.any(arrays["active_forward_s"] + arrays["active_reverse_s"] > 3600. + 1e-8):
        raise ValueError("v10 combined directional activity exceeds hour")
    stores = arrays["depth_m"] + sum(arrays[name] for name in STATES[1:]) / 1000.
    actual_change = np.diff(stores, axis=0) * area
    _equal(arrays["storage_change_m3"], actual_change, "actual inventory change")
    residual = arrays["rain_volume_m3"] + arrays["internal_net_m3"] - arrays["soil_et_m3"] - arrays["surface_et_m3"] - arrays["boundary_outflow_m3"] - actual_change
    _equal(arrays["balance_residual_m3"], residual, "saved residual")
    _equal(residual, np.zeros_like(residual), "cell budget")
    rain_total = math.fsum(arrays["rain_volume_m3"][0].tolist())
    loss = math.fsum((arrays["soil_et_m3"][0] + arrays["surface_et_m3"][0]).tolist())
    external = math.fsum(arrays["boundary_outflow_m3"][0].tolist())
    change = math.fsum(actual_change[0].tolist())
    total = loss + external + change
    allowed = 1e-6 + abs(total) * 1e-10
    if abs(rain_total - total) > allowed:
        raise ValueError("v10 independent whole hour budget failed")
    return dict(rain_m3=rain_total, loss_m3=loss, external_m3=external, change_m3=change,
                residual_m3=rain_total-total, allowed_m3=allowed, budget_passed=True,
                initial_water_m3=math.fsum(stores[0].tolist())*area,
                final_water_m3=math.fsum(stores[1].tolist())*area)


def load_native_weather_v10_hour(storage_record, checkpoint_record, *, hierarchy, rain_mm_h,
                                forcing_identity, hour, step_s, parameters, runoff_parameters,
                                previous_checkpoint_record=None):
    if type(hour) is not int or not 0 <= hour < 24 or step_s not in (2.5, 1.25):
        raise ValueError("v10 explicit hour/step predeclaration required")
    if "substep_s" in parameters:
        raise ValueError("v10 shared parameters exclude substep_s")
    if parameters != PHYSICS or runoff_parameters != asdict(RunoffParameters()):
        raise ValueError("v10 fixed physics/runoff predeclaration mismatch")
    storage = load_storage(**storage_record)
    checkpoint = load_checkpoint(**checkpoint_record)
    config = dict(parameters, substep_s=step_s)
    expected = dict(profile=PROFILE, hierarchy_identity=hierarchy["identity_sha256"], forcing_identity=forcing_identity,
                    forcing_hour_offset=hour, start_s=hour*3600., end_s=(hour+1)*3600., dt_s=3600.,
                    substep_s=3600./math.ceil(3600./step_s), substeps=math.ceil(3600./step_s),
                    parameters=config, runoff_parameters=runoff_parameters,
                    cells=hierarchy["arrays"]["height_m"].size, faces=len(hierarchy["arrays"]["face_cells"]))
    for result in (storage, checkpoint):
        if any(result["metadata"].get(name) != value for name, value in expected.items()):
            raise ValueError("v10 predeclared time/forcing/config mismatch")
        _flags(result["metadata"])
        semantics = dict(physics=PHYSICS_SEMANTICS,
                         permanent_lake_impermeability="not modelled; requires independent material mask",
                         activity_semantics="SSP-RK2 stage quadrature of actual signed exchange; not exact event duration")
        if any(result["metadata"].get(name) != value for name, value in semantics.items()):
            raise ValueError("v10 declared numerical/physics semantics mismatch")
    budget = validate_native_v10_accounts(storage, hierarchy=hierarchy, rain_mm_h=rain_mm_h)
    arrays, saved = storage["arrays"], checkpoint["arrays"]
    valid = hierarchy["arrays"]["valid_mask"].ravel()
    if checkpoint["metadata"].get("last_page_identity") != storage["identity_sha256"]:
        raise ValueError("v10 checkpoint last-page link mismatch")
    if (hour == 0) != (previous_checkpoint_record is None):
        raise ValueError("v10 previous checkpoint coverage mismatch")
    previous = None if hour == 0 else load_checkpoint(**previous_checkpoint_record)
    if previous is not None:
        previous_expected = dict(expected, forcing_hour_offset=hour-1, start_s=(hour-1)*3600., end_s=hour*3600.)
        if any(previous["metadata"].get(name) != value for name, value in previous_expected.items()):
            raise ValueError("v10 previous checkpoint time/config mismatch")
    for name in STATES:
        initial = 0. if name == "depth_m" else runoff_parameters["initial_"+name]
        expected_initial = np.where(valid, initial, 0.) if previous is None else previous["arrays"][name]
        if not np.array_equal(arrays[name][0], expected_initial) or not np.array_equal(arrays[name][1], saved[name]):
            raise ValueError("v10 checkpoint four-state chain mismatch")
    for name in ERRORS:
        if saved[name].dtype != np.float64 or np.any(saved[name][~valid] != 0):
            raise ValueError("v10 unknown compensation mismatch")
    for name in FLUX:
        expected_sum = arrays[name] if previous is None else previous["arrays"]["cumulative_"+name] + arrays[name]
        if not np.array_equal(saved["cumulative_"+name], expected_sum):
            raise ValueError("v10 exact cumulative checkpoint chain mismatch")
        if name in ("routed_volume_m3", "wet_duration_s") and np.any(saved["cumulative_"+name][~valid] != 0):
            raise ValueError("v10 unknown cumulative receiver mismatch")
    if np.any(saved["cumulative_active_forward_s"] + saved["cumulative_active_reverse_s"] > (hour+1)*3600. + 1e-8):
        raise ValueError("v10 cumulative combined activity exceeded")
    records = [storage_record, checkpoint_record] + ([] if previous_checkpoint_record is None else [previous_checkpoint_record])
    for record in records:
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("v10 external page pin changed during cold read")
    return dict(storage=storage, checkpoint=checkpoint, budget=budget, hour_io_accepted=True,
                complete_index_accepted=False, solver_advanced=False)


def load_native_weather_storage_v10_index(path, *, expected_sha256, weather_index_record,
                                         hierarchy_record, source_record, run_inputs_record,
                                         execution_resource_record, declared_steps_s=STEPS,
                                         scope="original_td", code_root=None):
    path = Path(path).absolute()
    if path.name != "index.json":
        raise ValueError("v10 complete final index.json required")
    index = _json(dict(path=str(path), expected_sha256=expected_sha256))
    if index.get("schema") != "td-v10-spatial-weather-hour-pages-index-v1" or index.get("steps_s") != list(STEPS) or tuple(declared_steps_s) != STEPS:
        raise ValueError("v10 final schema/predeclared steps rejected")
    _flags(index)
    root = path.parent
    _layout(run_inputs_record, root / "run-inputs.json")
    _layout(execution_resource_record, root / "resource.json")
    inputs, resource = _json(run_inputs_record), _json(execution_resource_record)
    if (inputs.get("schema") != "td-v10-spatial-weather-run-inputs-v1" or inputs.get("steps_s") != list(STEPS)
            or inputs.get("physics_version") != "v10-unified-infiltration; not execution-equivalence"
            or inputs.get("depth_gate_m") != .001 or inputs.get("receiver_gate") != .01
            or inputs.get("chunk_max_face_steps") != 6000000000 or inputs.get("job_max_bytes") != MAX_BYTES):
        raise ValueError("v10 run inputs contract rejected")
    if (resource.get("schema") != "td-v10-spatial-weather-resource-v1" or resource.get("index_sha256") != expected_sha256
            or resource.get("scope") != "complete eastward+westward both steps execution" or resource.get("complete") is not True
            or type(resource.get("sample_count")) is not int or resource["sample_count"] < 1
            or resource.get("sampling_interval_s") != 2 or resource.get("monitor_error") is not None):
        raise ValueError("v10 complete external execution resource rejected")
    for name in ("peak_rss_bytes", "peak_private_bytes"):
        if type(resource.get(name)) is not int or not 0 < resource[name] <= MAX_BYTES:
            raise ValueError("v10 execution resource exceeded or missing")
    source = load_td_source_bundle(**source_record)
    hierarchy = load_basin_hierarchy(**hierarchy_record)
    if inputs.get("hierarchy") != hierarchy_record or hierarchy["metadata"]["source_identity_sha256"] != source["identity_sha256"] or hierarchy["metadata"]["source_metadata"] != source["metadata"]:
        raise ValueError("v10 source/hierarchy external chain rejected")
    for name in ("height_m", "valid_mask", "protected_mask", "open_boundary_mask"):
        if not np.array_equal(source["arrays"][name], hierarchy["arrays"][name]):
            raise ValueError("v10 source/hierarchy actual geometry mismatch")
    if source["arrays"]["protected_mask"].any():
        raise ValueError("v10 fresh protected domain rejected")
    base = Path(__file__).resolve().parents[1] if code_root is None else Path(code_root).resolve()
    if scope == "original_td":
        if (inputs.get("primary_sha256") != PRIMARY_SHA256 or source["metadata"]["source_sha256"] != PRIMARY_SHA256
                or weather_index_record["expected_sha256"] != "333046a82778411b95bcb691988a7b016347de1ad288ad2d841cc6a089bb1271"):
            raise ValueError("v10 original source/weather predeclaration mismatch")
    elif scope != "synthetic_fixture" or source["arrays"]["height_m"].size > 4096:
        raise ValueError("v10 explicit original/tiny scope required")
    codes = index.get("code_sha256")
    if not isinstance(codes, dict) or not codes or codes != inputs.get("code_sha256"):
        raise ValueError("v10 frozen dependencies missing/mismatched")
    def check_codes():
        for name, digest in codes.items():
            target = (base / name).resolve()
            if not target.is_relative_to(base) or file_sha256(target) != _sha(digest):
                raise ValueError("v10 frozen dependency changed")
        if scope == "original_td" and file_sha256(PRIMARY_PATH) != PRIMARY_SHA256:
            raise ValueError("v10 actual primary pin changed")
    check_codes()
    weather = _json(weather_index_record, 8*1024*1024)
    weather_pin = dict(path=weather_index_record["path"], sha256=weather_index_record["expected_sha256"])
    if (weather.get("schema") != "td-native-storm-forcing-index-v1" or weather.get("source") != source_record
            or set(weather.get("cases", {})) != {"eastward", "westward"}
            or index.get("weather_index") != weather_pin or inputs.get("weather_index") != weather_pin):
        raise ValueError("v10 external weather/source index mismatch")
    faces = len(hierarchy["arrays"]["face_cells"])
    budgets = {str(step):dict(chunk_face_steps=math.ceil(3600/step)*faces,
                           global_face_steps_per_direction=24*math.ceil(3600/step)*faces) for step in STEPS}
    if inputs.get("budgets") != budgets or index.get("budgets") != budgets or any(item["chunk_face_steps"] > 6000000000 for item in budgets.values()):
        raise ValueError("v10 chunk/global work declaration mismatch")
    scenarios = index.get("scenarios", {})
    if set(scenarios) != {"eastward", "westward"}:
        raise ValueError("v10 complete two-direction coverage required")
    if {entry.name for entry in root.iterdir() if entry.is_dir()} != {f"{direction}-{step:g}s" for direction in scenarios for step in STEPS}:
        raise ValueError("v10 root group coverage mismatch")
    records = [weather_index_record, hierarchy_record, source_record, run_inputs_record, execution_resource_record]
    summaries = {}
    for direction in ("eastward", "westward"):
        case, comparison = weather["cases"][direction], scenarios[direction]
        _flags(comparison, require_transient=False)
        artifact = load_native_storm(**case["record"], source_record=source_record, expected_plan=case["plan"])
        rain = artifact["arrays"]["rain_mm_h"]
        plan = artifact["metadata"]["plan"]
        if rain.shape != (24, *hierarchy["arrays"]["height_m"].shape) or plan["start_s"] != 0. or plan["dt_s"] != 3600. or plan["window"] != [0,rain.shape[1],0,rain.shape[2]]:
            raise ValueError("v10 complete native weather shape/time rejected")
        forcing = identity({"rain_mm_h":rain}, {"dt_s":3600.})
        if (forcing != case["forcing_identity"] or inputs.get("weather_records", {}).get(direction) != case["record"]
                or inputs.get("forcing_identities", {}).get(direction) != forcing
                or comparison.get("schema") != "td-v10-spatial-weather-comparison-v1"
                or comparison.get("weather_record") != case["record"] or comparison.get("forcing_identity") != forcing
                or comparison.get("steps_s") != list(STEPS)):
            raise ValueError("v10 complete weather/comparison identity rejected")
        records.append(case["record"])
        pages = comparison.get("pages", {})
        if set(pages) != {"2.5", "1.25"}:
            raise ValueError("v10 step coverage rejected")
        summaries[direction] = {}
        final_receiver = {}
        for step in STEPS:
            group = root / f"{direction}-{step:g}s"
            if {entry.name for entry in group.iterdir() if entry.is_dir()} != {f"hour-{hour:02d}" for hour in range(24)}:
                raise ValueError("v10 hour directory coverage rejected")
            listed = pages[str(step)]
            if len(listed) != 24 or [item.get("hour") for item in listed] != list(range(24)) or any(type(item.get("hour")) is not int for item in listed):
                raise ValueError("v10 ordered 24-hour coverage rejected")
            previous = None
            intervals = []
            for hour, page in enumerate(listed):
                _layout(page["storage"], group / f"hour-{hour:02d}" / "storage.npz")
                _layout(page["checkpoint"], group / f"hour-{hour:02d}" / "checkpoint.npz")
                if page.get("forcing_identity") != forcing or page.get("chunk_work_face_steps") != budgets[str(step)]["chunk_face_steps"]:
                    raise ValueError("v10 page forcing/work declaration mismatch")
                result = load_native_weather_v10_hour(page["storage"], page["checkpoint"], hierarchy=hierarchy,
                    rain_mm_h=rain[hour], forcing_identity=forcing, hour=hour, step_s=step,
                    parameters=PHYSICS, runoff_parameters=asdict(RunoffParameters()), previous_checkpoint_record=previous)
                intervals.append(result["budget"])
                final_receiver[step] = result["checkpoint"]["arrays"]["cumulative_routed_volume_m3"]
                records.extend((page["storage"], page["checkpoint"]))
                previous = page["checkpoint"]
                del result
            rain_sum = math.fsum(item["rain_m3"] for item in intervals)
            residual = math.fsum([intervals[0]["initial_water_m3"],rain_sum,-math.fsum(item["loss_m3"] for item in intervals),
                                 -math.fsum(item["external_m3"] for item in intervals),-intervals[-1]["final_water_m3"]])
            allowed = 1e-6 + rain_sum*1e-10
            if abs(residual) > allowed:
                raise ValueError("v10 cumulative actual inventory budget failed")
            summaries[direction][str(step)] = dict(hours=24, interval_budgets=intervals,
                cumulative_residual_m3=residual, cumulative_allowed_m3=allowed, budget_passed=True)
        maximum = 0.
        hourly_differences = []
        for coarse, fine in zip(pages["2.5"],pages["1.25"]):
            first, second = load_storage(**coarse["storage"]), load_storage(**fine["storage"])
            difference = abs(first["arrays"]["depth_m"]-second["arrays"]["depth_m"])
            value = float(difference.max())
            frame, cell = np.unravel_index(difference.argmax(), difference.shape)
            hourly_differences.append(dict(hour=coarse["hour"],max_depth_difference_m=value,frame=int(frame),cell=int(cell)))
            maximum = max(maximum,value)
            del first, second
        relative = float(abs(final_receiver[2.5]-final_receiver[1.25]).sum()/max(1e-12,final_receiver[1.25].sum()))
        gate = maximum <= .001 and relative <= .01
        if (comparison.get("max_saved_depth_difference_m") != maximum or comparison.get("cumulative_receiver_relative_l1") != relative
                or comparison.get("gate_passed") is not gate or comparison.get("hour_comparisons") != hourly_differences):
            raise ValueError("v10 actual numerical comparison mismatch")
        summaries[direction].update(numerical_gate_passed=gate,max_saved_depth_difference_m=maximum,cumulative_receiver_relative_l1=relative)
        del artifact, rain
    numerical = all(item["numerical_gate_passed"] for item in summaries.values())
    if index.get("all_numerical_gates_passed") is not numerical:
        raise ValueError("v10 overall numerical gate mismatch")
    for record in records:
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("v10 external input pin changed during complete cold read")
    check_codes()
    memory = psutil.Process().memory_info()
    rss, private = int(getattr(memory,"peak_wset",memory.rss)), getattr(memory,"peak_pagefile",None)
    if type(private) is not int or max(rss,private) > MAX_BYTES:
        raise MemoryError("v10 cold resource peak missing/exceeds1GiB")
    if file_sha256(path) != expected_sha256:
        raise ValueError("v10 final index changed during cold read")
    return dict(schema="td-v10-spatial-weather-hour-pages-acceptance-v1", index_sha256=expected_sha256,
                cases=summaries, io_chain_accepted=True, IO_accepted=True, numerical_gate_passed=numerical,
                resource=dict(peak_rss_bytes=rss,peak_private_bytes=private),solver_advanced=False,
                hydraulic_ready=False,transient_converged=False,publishable=False)
