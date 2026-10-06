"""Versioned symmetric forcing/transport split with compiled conservative D4 exchange."""

from dataclasses import asdict
import math
import numpy as np
from terrain_pipeline.mountain_source_adapter import identity, readonly
from terrain_pipeline.rainfall_runoff import RunoffParameters, _release
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy
from terrain_pipeline.td_basin_storage import _pool_count
from terrain_pipeline.td_basin_storage_v5_io import save_storage, load_storage, validate_saved_storage

PROFILE = "v5-symmetric-forcing-6e9-v1"


def _forcing(depth, soil, fast, slow, rain_rate, sub_dt, runoff, config, area, ledgers, step):
    hours = sub_dt / 3600
    wet = depth > config["wet_threshold_m"]
    rainfall = rain_rate * hours
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
    return depth, soil, fast, slow

def simulate_basin_storage(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None,
                           runoff_parameters=None, parameters=None):
    from terrain_pipeline import td_basin_storage_v4 as transport

    validate_basin_hierarchy(hierarchy)
    config = transport.parameters(parameters)
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
    horizontal = first_cells // shape[1] == second_cells // shape[1]
    groups = np.where(horizontal, first_cells % shape[1] % 2, 2 + first_cells // shape[1] % 2)
    prepared = tuple(np.flatnonzero(groups == group) for group in range(4))
    ordered = np.concatenate(prepared)
    offsets = np.concatenate(([0], np.cumsum([len(values) for values in prepared])))
    for step in range(len(rain)):
        before = area * (depth + (soil + fast + slow) / 1000)
        for substep in range(subdivisions):
            depth, soil, fast, slow = _forcing(depth, soil, fast, slow, rain[step], sub_dt / 2,
                runoff, config, area, ledgers, step)
            depth, sub_forward, sub_reverse, exported, sub_forward_duration, sub_reverse_duration = transport._compiled_exchange(
                depth, bed, faces, boundary, boundary_width, spacing, sub_dt,
                config["face_conductance_m_s"], ordered, offsets)
            signed_exchange = sub_forward - sub_reverse
            delta = np.bincount(second_cells, weights=signed_exchange, minlength=bed.size) - np.bincount(first_cells, weights=signed_exchange, minlength=bed.size)
            if np.any(depth < -1e-12) or not np.isfinite(depth).all():
                raise ValueError("unstable/nonfinite water state")
            depth = np.maximum(depth, 0)
            ledgers["internal_net_m3"][step] += delta
            np.add.at(ledgers["boundary_outflow_m3"][step], boundary, exported)
            forward += sub_forward
            reverse += sub_reverse
            forward_duration += sub_forward_duration
            reverse_duration += sub_reverse_duration
            receiver_forward = receiver[first_cells] == second_cells
            receiver_reverse = receiver[second_cells] == first_cells
            np.add.at(routed, first_cells, np.where(receiver_forward, sub_forward, 0))
            np.add.at(routed, second_cells, np.where(receiver_reverse, sub_reverse, 0))
            np.add.at(duration, first_cells, np.where(receiver_forward, sub_forward_duration, 0))
            np.add.at(duration, second_cells, np.where(receiver_reverse, sub_reverse_duration, 0))
            depth, soil, fast, slow = _forcing(depth, soil, fast, slow, rain[step], sub_dt / 2,
                runoff, config, area, ledgers, step)
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
    metadata = {"schema": "td-basin-storage-v1", "algorithm": "D4-threshold-symmetric-forcing-Strang-v5", "work_profile": "v5-symmetric-forcing-6e9-v1",
        "hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": spacing,
        "origin_m_xz": hierarchy["metadata"]["origin_m_xz"], "dt_s": float(dt_s), "substep_s": sub_dt,
        "parameters": config, "runoff_parameters": asdict(runoff), "substeps": substeps,
        "routed_semantics": "actual positive cell-to-static-receiver D4 face flux integral; duration counts active substeps",
        "pool_semantics": "both cell heads above shared sill; no equal-level projection; conservative separation on recession",
        "boundary_semantics": "all exterior D4 sides of each declared open perimeter cell; corner has two widths",
        "limiter_semantics": "no quarter cap; exact compiled threshold pair",
        "forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
        "forcing_accuracy_limit": "soil infiltration/ET/percolation remain ordered discrete updates; no full rain-soil ODE second-order claim",
        "saved_time_semantics": "state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
        "activity_semantics": "each face visited twice for substep_s/2 within transport; sum directional activity<=substep_s; forcing halves add no activity",
        "execution": "Numba v4 pair kernel float64 no fastmath",
        "transient_converged": False, "morphology_flux_ready": False,
        "hydraulic_ready": False, "natural_outlet_verified": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
