"""Finite-time D4 storage/threshold exchange with cell-exclusive water accounts."""

from dataclasses import asdict
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.rainfall_runoff import RunoffParameters, _release
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy

DEFAULT_PARAMETERS = {"substep_s": 60.0, "face_conductance_m_s": 0.6, "surface_evaporation_mm_h": 0.15,
    "wet_threshold_m": 1e-9, "max_substeps": 20000, "max_work_face_steps": 500000000}
MAX_STORAGE_BYTES = 256 * 1024 * 1024


def _parameters(supplied):
    supplied = {} if supplied is None else dict(supplied)
    if set(supplied) - set(DEFAULT_PARAMETERS):
        raise ValueError("unknown storage parameters")
    values = {**DEFAULT_PARAMETERS, **supplied}
    for key in ("substep_s", "face_conductance_m_s", "surface_evaporation_mm_h", "wet_threshold_m"):
        if type(values[key]) not in (int, float) or not math.isfinite(values[key]) or values[key] < 0:
            raise ValueError("invalid finite storage coefficient")
    if values["substep_s"] <= 0 or values["wet_threshold_m"] <= 0:
        raise ValueError("positive substep and wet threshold required")
    for key in ("max_substeps", "max_work_face_steps"):
        if type(values[key]) is not int or not 1 <= values[key] <= DEFAULT_PARAMETERS[key]:
            raise ValueError("invalid work budget")
    return values


def _pool_count(depth, bed, valid, faces, threshold):
    wet = (depth > threshold) & valid
    parent = np.arange(depth.size)

    def find(cell):
        while parent[cell] != cell:
            parent[cell] = parent[parent[cell]]
            cell = parent[cell]
        return cell

    head = bed + depth
    connected = wet[faces[:, 0]] & wet[faces[:, 1]] & (np.minimum(head[faces[:, 0]], head[faces[:, 1]]) > np.max(bed[faces], axis=1) + threshold)
    for first, second in faces[connected]:
        first_root, second_root = find(first), find(second)
        parent[max(first_root, second_root)] = min(first_root, second_root)
    return len({find(cell) for cell in np.flatnonzero(wet)})


def simulate_basin_storage(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None,
                           runoff_parameters=None, parameters=None, _face_solver=None):
    validate_basin_hierarchy(hierarchy)
    config = _parameters(parameters) if _face_solver is None else _face_solver.parameters(parameters)
    runoff = RunoffParameters() if runoff_parameters is None else runoff_parameters
    if not isinstance(runoff, RunoffParameters):
        raise ValueError("RunoffParameters required")
    runoff.__post_init__()
    if type(dt_s) not in (int, float) or not math.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("positive finite physical timestep required")
    topology = hierarchy["arrays"]
    shape = topology["height_m"].shape
    bed = topology["height_m"].ravel()
    valid = topology["valid_mask"].ravel()
    rain = np.asarray(rain_mm_h, dtype=np.float64)
    if rain.ndim == 1:
        rain = np.broadcast_to(rain[:, None], (len(rain), bed.size)).copy()
    elif rain.ndim == 3 and rain.shape[1:] == shape:
        rain = rain.reshape(len(rain), -1).copy()
    else:
        raise ValueError("rain must be [T] or [T,z,x]")
    if not 1 <= len(rain) <= 1000 or not np.isfinite(rain).all() or np.any((rain < 0) | (rain > 1e6)):
        raise ValueError("invalid bounded rainfall")
    rain[:, ~valid] = 0
    depth = np.zeros(bed.size) if initial_depth_m is None else np.asarray(initial_depth_m, dtype=np.float64).reshape(-1).copy()
    if depth.shape != bed.shape or not np.isfinite(depth).all() or np.any(depth < 0) or np.any(depth[~valid] != 0):
        raise ValueError("invalid initial wet state")
    subdivisions = int(math.ceil(dt_s / config["substep_s"]))
    substeps = len(rain) * subdivisions
    faces = topology["face_cells"]
    if substeps > config["max_substeps"] or substeps * len(faces) > config["max_work_face_steps"] or len(rain) * bed.size > 4_000_000:
        raise ValueError("storage work/memory budget exceeded")
    spacing = hierarchy["metadata"]["spacing_m"]
    area = spacing ** 2
    sub_dt = dt_s / subdivisions
    hours = sub_dt / 3600
    soil = np.where(valid, runoff.initial_soil_mm, 0.0)
    fast = np.where(valid, runoff.initial_fast_mm, 0.0)
    slow = np.where(valid, runoff.initial_slow_mm, 0.0)
    states = {key: np.zeros((len(rain) + 1, bed.size)) for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm")}
    for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
        states[key][0] = value
    ledger_keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
    ledgers = {key: np.zeros((len(rain), bed.size)) for key in ledger_keys}
    forward = np.zeros(len(faces))
    reverse = np.zeros(len(faces))
    forward_duration = np.zeros(len(faces))
    reverse_duration = np.zeros(len(faces))
    routed = np.zeros(bed.size)
    duration = np.zeros(bed.size)
    pools = np.zeros(len(rain) + 1, np.int64)
    limiter_active = np.zeros(len(rain), np.int64)
    proposed_active = np.zeros(len(rain), np.int64)
    donor_limited = np.zeros(len(rain), np.int64)
    pools[0] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    first_cells, second_cells = faces[:, 0], faces[:, 1]
    sills = topology["face_level_m"]
    boundary = topology["boundary_cells"]
    boundary_rows, boundary_columns = np.divmod(boundary, shape[1])
    boundary_width = spacing * ((boundary_rows == 0).astype(int) + (boundary_rows == shape[0] - 1)
        + (boundary_columns == 0) + (boundary_columns == shape[1] - 1))
    receiver = topology["receiver"]
    for step in range(len(rain)):
        before = area * (depth + (soil + fast + slow) / 1000)
        for substep in range(subdivisions):
            wet = depth > config["wet_threshold_m"]
            rainfall = rain[step] * hours
            lake_rain = np.where(wet, rainfall, 0)
            land_rain = rainfall - lake_rain
            infiltration = np.minimum(np.minimum(land_rain, runoff.infiltration_capacity_mm_h * hours), np.maximum(0, runoff.soil_capacity_mm - soil))
            soil += infiltration
            soil_et = np.minimum(soil, runoff.potential_et_mm_h * hours)
            soil -= soil_et
            percolation = np.minimum(soil, runoff.percolation_mm_h * hours)
            soil -= percolation
            fast, fast_release = _release(fast, land_rain - infiltration, sub_dt, runoff.fast_tau_s)
            slow, slow_release = _release(slow, percolation, sub_dt, runoff.slow_tau_s)
            release = fast_release + slow_release
            depth += (lake_rain + release) / 1000
            surface_et = np.minimum(depth, config["surface_evaporation_mm_h"] * hours / 1000)
            depth -= surface_et
            for key, values in (("rain_volume_m3", rainfall), ("lake_rain_m3", lake_rain), ("land_rain_m3", land_rain),
                                ("soil_et_m3", soil_et), ("local_release_m3", release)):
                ledgers[key][step] += values * area / 1000
            ledgers["surface_et_m3"][step] += surface_et * area
            if _face_solver is not None and not depth.any():
                continue
            head = bed + depth
            difference = head[first_cells] - head[second_cells]
            donors = np.where(difference >= 0, first_cells, second_cells)
            recipients = np.where(difference >= 0, second_cells, first_cells)
            excess_head = np.maximum(0, head[donors] - np.maximum(sills, head[recipients]))
            proposed = config["face_conductance_m_s"] * spacing * excess_head * sub_dt
            proposed_active[step] += np.count_nonzero(proposed > 0)
            limiter_active[step] += np.count_nonzero(proposed > excess_head * area * 0.25)
            proposed = np.minimum(proposed, excess_head * area * 0.25)
            boundary_proposed = np.minimum(config["face_conductance_m_s"] * boundary_width * depth[boundary] * sub_dt,
                                           depth[boundary] * area * 0.25)
            demand = np.bincount(donors, weights=proposed, minlength=bed.size)
            np.add.at(demand, boundary, boundary_proposed)
            scale = np.minimum(1, np.divide(depth * area, demand, out=np.ones_like(depth), where=demand > 0))
            donor_limited[step] += np.count_nonzero(scale < 1)
            if _face_solver is None:
                exchange = proposed * scale[donors]
                exported = boundary_proposed * scale[boundary]
                delta = np.bincount(recipients, weights=exchange, minlength=bed.size) - np.bincount(donors, weights=exchange, minlength=bed.size)
                depth += delta / area
                depth[boundary] -= exported / area
                signed_exchange = np.where(difference >= 0, exchange, -exchange)
                sub_forward_duration = ((difference >= 0) & (exchange > 0)) * sub_dt
                sub_reverse_duration = ((difference < 0) & (exchange > 0)) * sub_dt
            else:
                depth, sub_forward, sub_reverse, exported, sub_forward_duration, sub_reverse_duration = _face_solver.exchange(
                    depth, bed, faces, boundary, boundary_width, spacing, sub_dt, config, shape[1])
                signed_exchange = sub_forward - sub_reverse
                exchange = abs(signed_exchange)
                donors = np.where(signed_exchange >= 0, first_cells, second_cells)
                recipients = np.where(signed_exchange >= 0, second_cells, first_cells)
                delta = np.bincount(second_cells, weights=signed_exchange, minlength=bed.size) - np.bincount(first_cells, weights=signed_exchange, minlength=bed.size)
                limiter_active[step] = 0
                donor_limited[step] = 0
            if np.any(depth < -1e-12) or not np.isfinite(depth).all():
                raise ValueError("unstable/nonfinite water state")
            depth = np.maximum(depth, 0)
            ledgers["internal_net_m3"][step] += delta
            np.add.at(ledgers["boundary_outflow_m3"][step], boundary, exported)
            forward += np.maximum(signed_exchange, 0) if _face_solver is None else sub_forward
            reverse += np.maximum(-signed_exchange, 0) if _face_solver is None else sub_reverse
            forward_duration += sub_forward_duration
            reverse_duration += sub_reverse_duration
            selected = (receiver[donors] == recipients) & (exchange > 0)
            active_donors = np.unique(donors[selected])
            if _face_solver is None:
                np.add.at(routed, donors[selected], exchange[selected])
                duration[active_donors] += sub_dt
            else:
                receiver_forward = receiver[first_cells] == second_cells
                receiver_reverse = receiver[second_cells] == first_cells
                np.add.at(routed, first_cells, np.where(receiver_forward, sub_forward, 0))
                np.add.at(routed, second_cells, np.where(receiver_reverse, sub_reverse, 0))
                np.add.at(duration, first_cells, np.where(receiver_forward, sub_forward_duration, 0))
                np.add.at(duration, second_cells, np.where(receiver_reverse, sub_reverse_duration, 0))
        after = area * (depth + (soil + fast + slow) / 1000)
        ledgers["storage_change_m3"][step] = after - before
        residual = (ledgers["rain_volume_m3"][step] + ledgers["internal_net_m3"][step] - ledgers["soil_et_m3"][step]
                    - ledgers["surface_et_m3"][step] - ledgers["boundary_outflow_m3"][step] - (after - before))
        if np.any(abs(residual) > 1e-6 + 1e-10 * (abs(before) + abs(after) + ledgers["rain_volume_m3"][step])):
            raise ValueError("water ledger not conservative")
        ledgers["balance_residual_m3"][step] = residual
        for key, value in (("depth_m", depth), ("soil_mm", soil), ("fast_mm", fast), ("slow_mm", slow)):
            states[key][step + 1] = value
        pools[step + 1] = _pool_count(depth, bed, valid, faces, config["wet_threshold_m"])
    arrays = {key: readonly(value) for key, value in {**states, **ledgers, "rain_mm_h": rain,
        "height_m": topology["height_m"], "valid_mask": topology["valid_mask"], "face_cells": faces,
        "receiver": receiver, "boundary_cells": boundary, "face_forward_m3": forward, "face_reverse_m3": reverse,
        "active_forward_s": forward_duration, "active_reverse_s": reverse_duration, "boundary_width_m": boundary_width,
        "routed_volume_m3": routed, "wet_duration_s": duration, "wet_pool_count": pools}.items()}
    arrays.update({"limiter_active_count": readonly(limiter_active), "proposed_active_count": readonly(proposed_active),
                   "donor_limited_count": readonly(donor_limited)})
    metadata = {"schema": "td-basin-storage-v1", "algorithm": "finite-time-D4-threshold-storage-v1",
        "hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": spacing,
        "origin_m_xz": hierarchy["metadata"]["origin_m_xz"], "dt_s": float(dt_s), "substep_s": sub_dt,
        "parameters": config, "runoff_parameters": asdict(runoff), "substeps": substeps,
        "routed_semantics": "actual positive cell-to-static-receiver D4 face flux integral; duration counts active substeps",
        "pool_semantics": "both cell heads above shared sill; no equal-level projection; conservative separation on recession",
        "boundary_semantics": "all exterior D4 sides of each declared open perimeter cell; corner has two widths",
        "limiter_semantics": "each proposed face <=0.25*area*excess_head; donor-total <=available volume; timestep dependent",
        "transient_converged": False, "morphology_flux_ready": False,
        "hydraulic_ready": False, "natural_outlet_verified": False}
    if _face_solver is not None:
        metadata.update(_face_solver.metadata(config))
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}


def validate_basin_storage(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if metadata["schema"] != "td-basin-storage-v1" or identity(arrays, metadata) != result["identity_sha256"]:
        raise ValueError("storage schema/identity mismatch")
    if metadata["algorithm"] in ("D4-analytic-face-Strang-splitting-v2", "D4-analytic-face-event-Strang-v3", "D4-threshold-exact-Strang-v4"):
        if metadata["algorithm"] == "D4-threshold-exact-Strang-v4":
            from terrain_pipeline.td_basin_storage_implicit import parameters as base_parameters

            def v2_parameters(supplied):
                if metadata.get("work_profile") != "v4-threshold-pair-compiled-6e9-v1":
                    raise ValueError("unknown v4 execution profile")
                supplied = dict(supplied)
                budget = supplied.pop("max_work_face_steps")
                if type(budget) is not int or not 1 <= budget <= 6_000_000_000:
                    raise ValueError("v4 independent work budget exceeded")
                config = base_parameters(supplied)
                config["max_work_face_steps"] = budget
                return config
        elif metadata.get("work_profile") == "v2-full-refinement-6e9-v1":
            from terrain_pipeline.td_basin_storage_refinement import parameters as v2_parameters
        elif metadata["algorithm"] == "D4-analytic-face-event-Strang-v3":
            from terrain_pipeline.td_basin_storage_v3 import parameters as v2_parameters
        else:
            from terrain_pipeline.td_basin_storage_implicit import parameters as v2_parameters
        config = v2_parameters(metadata["parameters"])
    else:
        config = _parameters(metadata["parameters"])
    RunoffParameters(**metadata["runoff_parameters"])
    bed, valid = arrays["height_m"], arrays["valid_mask"]
    cells = bed.size
    rain = arrays["rain_mm_h"]
    if rain.ndim != 2 or rain.shape[1] != cells or not 1 <= len(rain) <= 1000:
        raise ValueError("invalid forcing shape")
    states = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
    ledgers = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3")
    required = set(states + ledgers) | {"rain_mm_h", "height_m", "valid_mask", "face_cells", "receiver",
        "boundary_cells", "boundary_width_m", "face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s",
        "routed_volume_m3", "wet_duration_s", "wet_pool_count"}
    diagnostic_keys = {"limiter_active_count", "proposed_active_count", "donor_limited_count"}
    if set(arrays) not in (required, required | diagnostic_keys) or bed.ndim != 2 or valid.shape != bed.shape or valid.dtype != bool:
        raise ValueError("unexpected storage arrays/coverage")
    for key in states + ledgers:
        shape = (len(rain) + 1, cells) if key in states else rain.shape
        if arrays[key].shape != shape or arrays[key].dtype != np.float64:
            raise ValueError("invalid state/ledger shape or dtype")
    for key, value in arrays.items():
        if not np.isfinite(value).all():
            raise ValueError("nonfinite storage array")
        if key not in ("height_m", "receiver", "internal_net_m3", "storage_change_m3", "balance_residual_m3") and np.any(value < 0):
            raise ValueError("negative water account")
    for key in states + ledgers + ("rain_mm_h",):
        if np.any(arrays[key][:, ~valid.ravel()] != 0):
            raise ValueError("water state/forcing on unknown cells")
    area = metadata["spacing_m"] ** 2
    volume = area * (arrays["depth_m"] + sum(arrays[key] for key in ("soil_mm", "fast_mm", "slow_mm")) / 1000)

    def near(actual, expected):
        if np.any(abs(actual - expected) > 1e-6 + 1e-10 * (abs(actual) + abs(expected))):
            raise ValueError("nonconservative saved water ledger")

    near(arrays["storage_change_m3"], np.diff(volume, axis=0))
    near(arrays["rain_volume_m3"], rain * metadata["dt_s"] / 3600 * area / 1000)
    near(arrays["rain_volume_m3"], arrays["lake_rain_m3"] + arrays["land_rain_m3"])
    residual = (arrays["rain_volume_m3"] + arrays["internal_net_m3"] - arrays["soil_et_m3"]
                - arrays["surface_et_m3"] - arrays["boundary_outflow_m3"] - np.diff(volume, axis=0))
    near(arrays["balance_residual_m3"], residual)
    near(residual, np.zeros_like(residual))
    near(arrays["internal_net_m3"].sum(axis=1), np.zeros(len(rain)))
    faces = arrays["face_cells"]
    if faces.dtype != np.int64 or faces.ndim != 2 or faces.shape[1] != 2 or np.any((faces < 0) | (faces >= cells)):
        raise ValueError("invalid saved D4 face")
    first, second = faces[:, 0], faces[:, 1]
    columns = bed.shape[1]
    if np.any(abs(first // columns - second // columns) + abs(first % columns - second % columns) != 1) or not valid.ravel()[faces].all():
        raise ValueError("unknown/non-D4 exchange")
    for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        if arrays[key].shape != (len(faces),):
            raise ValueError("invalid face ledger")
    for flow, duration_key in (("face_forward_m3", "active_forward_s"), ("face_reverse_m3", "active_reverse_s")):
        if np.any(arrays[duration_key] > len(rain) * metadata["dt_s"] + 1e-8) or np.any(
                (arrays[flow] == 0) & (arrays[duration_key] != 0)):
            raise ValueError("invalid directional face activity duration")
    net = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    net_cells = np.bincount(second, weights=net, minlength=cells) - np.bincount(first, weights=net, minlength=cells)
    near(arrays["internal_net_m3"].sum(axis=0), net_cells)
    receiver = arrays["receiver"]
    if receiver.shape != (cells,) or np.any((receiver < -1) | (receiver >= cells)):
        raise ValueError("invalid receiver")
    expected_routed = np.zeros(cells)
    np.add.at(expected_routed, first, np.where(receiver[first] == second, arrays["face_forward_m3"], 0))
    np.add.at(expected_routed, second, np.where(receiver[second] == first, arrays["face_reverse_m3"], 0))
    near(arrays["routed_volume_m3"], expected_routed)
    if arrays["wet_duration_s"].shape != (cells,) or np.any(arrays["wet_duration_s"] > len(rain) * metadata["dt_s"] + 1e-8):
        raise ValueError("invalid positive receiver flow duration")
    if np.any((arrays["routed_volume_m3"] == 0) & (arrays["wet_duration_s"] != 0)):
        raise ValueError("duration without actual routed flux")
    if metadata["substeps"] > config["max_substeps"] or metadata["substeps"] * len(faces) > config["max_work_face_steps"]:
        raise ValueError("saved work budget exceeded")
    if diagnostic_keys <= set(arrays):
        for key in diagnostic_keys:
            if arrays[key].shape != (len(rain),) or arrays[key].dtype != np.int64:
                raise ValueError("invalid limiter diagnostic")
        if np.any(arrays["limiter_active_count"] > arrays["proposed_active_count"]):
            raise ValueError("invalid limiter count")
    return True


def save_basin_storage(path, result):
    save_bundle(path, result, validator=validate_basin_storage)


def load_basin_storage(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_basin_storage,
                         max_bytes=MAX_STORAGE_BYTES, header_validator=_storage_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external storage identity mismatch")
    return result


def _storage_headers(headers):
    height_shape, height_dtype = headers.get("height_m", ((), np.dtype("O")))
    rain_shape, rain_dtype = headers.get("rain_mm_h", ((), np.dtype("O")))
    if (len(height_shape) != 2 or not 1 <= math.prod(height_shape) <= 250000 or height_dtype != np.float64 or
            len(rain_shape) != 2 or rain_shape[1] != math.prod(height_shape) or not 1 <= rain_shape[0] <= 1000 or
            math.prod(rain_shape) > 4_000_000 or rain_dtype != np.float64):
        raise ValueError("storage header grid/time allocation rejection")
    states = {"depth_m", "soil_mm", "fast_mm", "slow_mm"}
    ledgers = {"rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "surface_et_m3",
        "boundary_outflow_m3", "internal_net_m3", "local_release_m3", "storage_change_m3", "balance_residual_m3", "rain_mm_h"}
    for key in states | ledgers:
        expected_shape = (rain_shape[0] + 1, rain_shape[1]) if key in states else rain_shape
        if headers.get(key) != (expected_shape, np.dtype("float64")):
            raise ValueError("storage state/ledger header mismatch")
    if headers.get("valid_mask") != (height_shape, np.dtype(bool)):
        raise ValueError("storage mask header mismatch")
    face_shape, face_dtype = headers.get("face_cells", ((), np.dtype("O")))
    if len(face_shape) != 2 or face_shape[1] != 2 or face_shape[0] > 2 * rain_shape[1] or face_dtype != np.int64:
        raise ValueError("storage face allocation rejection")
    for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
        if headers.get(key) != ((face_shape[0],), np.dtype("float64")):
            raise ValueError("storage directional header mismatch")
    for key, dtype in (("receiver", np.int64), ("routed_volume_m3", np.float64), ("wet_duration_s", np.float64)):
        if headers.get(key) != ((rain_shape[1],), np.dtype(dtype)):
            raise ValueError("storage receiver output header mismatch")
    if headers.get("wet_pool_count") != ((rain_shape[0] + 1,), np.dtype("int64")):
        raise ValueError("storage pool count header mismatch")
    boundary_shape, boundary_dtype = headers.get("boundary_cells", ((), np.dtype("O")))
    if len(boundary_shape) != 1 or boundary_shape[0] > rain_shape[1] or boundary_dtype != np.int64 or headers.get("boundary_width_m") != (boundary_shape, np.dtype("float64")):
        raise ValueError("storage boundary header mismatch")
    manifest_shape, manifest_dtype = headers.get("manifest", ((), np.dtype("O")))
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= 1048576 or manifest_dtype != np.uint8:
        raise ValueError("storage manifest header mismatch")
    required = states | ledgers | {"height_m", "valid_mask", "face_cells", "face_forward_m3", "face_reverse_m3",
        "active_forward_s", "active_reverse_s", "receiver", "routed_volume_m3", "wet_duration_s", "wet_pool_count",
        "boundary_cells", "boundary_width_m", "manifest"}
    diagnostic_keys = {"limiter_active_count", "proposed_active_count", "donor_limited_count"}
    if set(headers) not in (required, required | diagnostic_keys):
        raise ValueError("unexpected storage archive headers")
    if diagnostic_keys <= set(headers):
        for key in diagnostic_keys:
            if headers[key] != ((rain_shape[0],), np.dtype("int64")):
                raise ValueError("invalid limiter diagnostic header")
