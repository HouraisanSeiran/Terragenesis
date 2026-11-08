"""Versioned symmetric forcing/transport split with compiled conservative D4 exchange."""

from dataclasses import asdict
import math
import numpy as np
from terrain_pipeline.common_infra import identity, readonly
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy
from terrain_pipeline.td_basin_storage import _pool_count
from terrain_pipeline.td_basin_forcing_compensated import forcing, reset_transport_compensation, reset_hourly_ledger_compensation
from terrain_pipeline.td_basin_storage_compiled import advance_hour
from terrain_pipeline.td_basin_storage_compiled_io import save_storage, load_storage, validate_saved_storage

PROFILE = "v9-compiled-hour-loop-v8-equivalent-v1"


def simulate_basin_storage(hierarchy, rain_mm_h, *, dt_s=3600, initial_depth_m=None,
                           runoff_parameters=None, parameters=None, checkpoint=None, forcing_identity=None, full_rain_mm_h=None):
    from terrain_pipeline import td_basin_transport_v6 as transport

    validate_basin_hierarchy(hierarchy)
    if np.any(hierarchy["arrays"]["protected_mask"]):
        raise ValueError("protected cells not supported by compiled execution")
    from terrain_pipeline.td_basin_storage_v4 import parameters as parse_parameters
    config = parse_parameters({"substep_s": 5.0, **({} if parameters is None else parameters)})
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
    if rain.ndim not in (1,3) or not 1<=len(rain)<=1000 or len(rain)*bed.size>4_000_000:
        raise ValueError("rain time/cell allocation budget exceeded before broadcast")
    if rain.ndim == 1:
        rain = np.broadcast_to(rain[:, None], (len(rain), bed.size)).copy()
    elif rain.ndim == 3 and rain.shape[1:] == shape:
        rain = rain.reshape(len(rain), -1).copy()
    else:
        raise ValueError("rain must be [T] or [T,z,x]")
    if not 1 <= len(rain) <= 1000 or not np.isfinite(rain).all() or np.any((rain < 0) | (rain > 1e6)):
        raise ValueError("invalid bounded rainfall")
    rain[:, ~valid] = 0
    if full_rain_mm_h is None:
        raise ValueError("fixed complete forcing required for continuation")
    if checkpoint is not None:
        from terrain_pipeline.td_basin_storage_compiled_io import validate_checkpoint
        validate_checkpoint(checkpoint)
    full_rain = np.asarray(full_rain_mm_h,dtype=np.float64)
    if full_rain.ndim not in (1,3) or not 1<=len(full_rain)<=1000 or len(full_rain)*bed.size>4_000_000 or not np.isfinite(full_rain).all() or np.any((full_rain<0)|(full_rain>1e6)) or (full_rain.ndim==3 and full_rain.shape[1:]!=shape):
        raise ValueError("invalid complete forcing shape/values")
    if full_rain.ndim==3:
        full_rain=full_rain.copy()
        full_rain[:,~topology["valid_mask"]]=0
    expected_forcing = identity({"rain_mm_h":full_rain},{"dt_s":float(dt_s)})
    if forcing_identity != expected_forcing:
        raise ValueError("complete forcing identity mismatch")
    offset = 0 if checkpoint is None else int(checkpoint["metadata"]["elapsed_s"] / dt_s)
    if offset+len(rain)>len(full_rain):
        raise ValueError("forcing slice beyond complete plan")
    expected_rain = full_rain[offset:offset+len(rain)]
    if expected_rain.ndim == 1:
        expected_rain = np.broadcast_to(expected_rain[:,None],rain.shape).copy()
    else:
        expected_rain = expected_rain.reshape(rain.shape).copy()
    expected_rain[:,~valid] = 0
    if not np.array_equal(expected_rain,rain):
        raise ValueError("checkpoint hour/forcing slice mismatch")
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
    soil = np.where(valid, runoff.initial_soil_mm, 0.0)
    fast = np.where(valid, runoff.initial_fast_mm, 0.0)
    slow = np.where(valid, runoff.initial_slow_mm, 0.0)
    if checkpoint is not None:
        if initial_depth_m is not None:
            raise ValueError("initial depth and checkpoint are mutually exclusive")
        from terrain_pipeline.td_basin_storage_compiled_io import validate_checkpoint
        validate_checkpoint(checkpoint)
        if checkpoint["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or checkpoint["metadata"]["parameters"] != config or checkpoint["metadata"]["runoff_parameters"] != asdict(runoff) or checkpoint["metadata"]["forcing_identity"] != forcing_identity:
            raise ValueError("checkpoint hierarchy/config/forcing mismatch")
        if checkpoint["metadata"]["cells"] != bed.size or checkpoint["metadata"]["faces"] != len(faces) or checkpoint["metadata"]["dt_s"] != float(dt_s) or checkpoint["metadata"]["substep_s"] != sub_dt:
            raise ValueError("checkpoint geometry/time mismatch")
        expected_count = int(checkpoint["metadata"]["elapsed_s"] / dt_s) * subdivisions
        if checkpoint["metadata"]["substeps"] != expected_count:
            raise ValueError("checkpoint actual derived count mismatch")
        depth, soil, fast, slow = (checkpoint["arrays"][key].copy() for key in ("depth_m", "soil_mm", "fast_mm", "slow_mm"))
        if any(np.any(values[~valid] != 0) for values in (depth,soil,fast,slow)) or np.any(topology["protected_mask"]):
            raise ValueError("checkpoint unknown/protected inventory unsupported")
        if any(np.any(checkpoint["arrays"]["error_"+key][~valid] != 0) for key in ("depth","soil","fast","slow")):
            raise ValueError("checkpoint compensation on unknown cells forbidden")
        if any(np.any(checkpoint["arrays"]["cumulative_"+key][~valid]!=0) for key in ("routed_volume_m3","wet_duration_s")):
            raise ValueError("checkpoint cumulative receiver evidence on unknown cells forbidden")
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
    boundary = topology["boundary_cells"]
    boundary_rows, boundary_columns = np.divmod(boundary, shape[1])
    boundary_width = spacing * ((boundary_rows == 0).astype(int) + (boundary_rows == shape[0] - 1)
        + (boundary_columns == 0) + (boundary_columns == shape[1] - 1))
    receiver = topology["receiver"]
    unused_indices = np.array([], dtype=np.int64)
    cfl = transport.validate_cfl(faces, boundary, boundary_width, spacing, sub_dt, config["face_conductance_m_s"], bed.size)
    forcing_keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "local_release_m3", "surface_et_m3")
    errors = {key: np.zeros(bed.size) for key in ("depth", "soil", "fast", "slow") + forcing_keys}
    if checkpoint is not None:
        for key in ("depth", "soil", "fast", "slow"):
            errors[key][:] = checkpoint["arrays"]["error_" + key]
    for step in range(len(rain)):
        reset_hourly_ledger_compensation(errors, forcing_keys)
        before = area * (depth + (soil + fast + slow) / 1000)
        states_buffer = np.vstack((depth,soil,fast,slow))
        errors_buffer = np.vstack(tuple(errors[key] for key in ("depth","soil","fast","slow")))
        runoff_buffer = np.array([runoff.infiltration_capacity_mm_h,runoff.soil_capacity_mm,runoff.potential_et_mm_h,
                                  runoff.percolation_mm_h,runoff.fast_tau_s,runoff.slow_tau_s])
        config_buffer = np.array([config["face_conductance_m_s"],config["wet_threshold_m"],config["surface_evaporation_mm_h"]])
        output = advance_hour(states_buffer,errors_buffer,rain[step],bed,faces,boundary,boundary_width,receiver,
                              spacing,sub_dt,subdivisions,runoff_buffer,config_buffer)
        depth,soil,fast,slow = output[0]
        for index,key in enumerate(("depth","soil","fast","slow")):
            errors[key][:] = output[1][index]
        for index,key in enumerate(("rain_volume_m3","lake_rain_m3","land_rain_m3","soil_et_m3","local_release_m3","surface_et_m3","internal_net_m3","boundary_outflow_m3")):
            ledgers[key][step] = output[2][index]
        forward += output[3]
        reverse += output[4]
        forward_duration += output[5]
        reverse_duration += output[6]
        routed += output[7]
        duration += output[8]
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
    metadata = {"schema": "td-basin-storage-v1", "algorithm": "D4-threshold-compensated-forcing-SSPRK2-v7", "work_profile": "v7-compensated-forcing-SSPRK2-6e9-v1",
        "hierarchy_identity_sha256": hierarchy["identity_sha256"], "spacing_m": spacing,
        "origin_m_xz": hierarchy["metadata"]["origin_m_xz"], "dt_s": float(dt_s), "substep_s": sub_dt,
        "parameters": config, "runoff_parameters": asdict(runoff), "substeps": substeps,
        "routed_semantics": "actual positive cell-to-static-receiver D4 face flux integral; duration counts active substeps",
        "pool_semantics": "both cell heads above shared sill; no equal-level projection; conservative separation on recession",
        "boundary_semantics": "all exterior D4 sides of each declared open perimeter cell; corner has two widths",
        "limiter_semantics": "no cap or clamp; positivity CFL for simultaneous Euler stages",
        "forcing_semantics": "runoff/rain/ET half-step, transport full step, runoff/rain/ET half-step; wet classification at each half",
        "forcing_accuracy_limit": "soil infiltration/ET/percolation remain ordered discrete updates; no full rain-soil ODE second-order claim",
        "saved_time_semantics": "state0 is t0; state[k] at k*dt_s; ledger[k] covers [k*dt_s,(k+1)*dt_s]",
        "activity_semantics": "RK stage quadrature dt/2 per positive directional stage; not exact continuous active interval; forcing halves add no activity",
        "compensation_semantics": "soil/fast/slow increments and forcing ledgers compensated; ledger errors reset hourly; depth error reset after transport replacement; exact full-inventory removal retires compensation",
        "positivity_cfl": cfl, "execution": "Numba full hourly forcing/SSPRK2 loop float64 no fastmath; execution equivalence pending",
        "transient_converged": False, "morphology_flux_ready": False,
        "hydraulic_ready": False, "natural_outlet_verified": False}
    start_time = 0 if checkpoint is None else checkpoint["metadata"]["elapsed_s"]
    metadata.update({"algorithm":"D4-threshold-compiled-hour-SSPRK2-v9", "work_profile":PROFILE,
        "chunk_start_s":start_time,"chunk_end_s":start_time+len(rain)*dt_s,"forcing_identity":forcing_identity,"forcing_hour_offset":offset,
        "saved_time_semantics":"state0 is checkpoint time; state[k] at chunk_start_s+k*dt_s; ledger[k] covers local hour k",
        "initialization_semantics":"first page default runoff initial stores; subsequent pages restore all checkpoint stores and compensation"})
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    checkpoint_arrays = {key: readonly(value) for key, value in (("depth_m",depth),("soil_mm",soil),("fast_mm",fast),("slow_mm",slow))}
    for key in ("depth", "soil", "fast", "slow"):
        checkpoint_arrays["error_" + key] = readonly(errors[key])
    for key in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s", "routed_volume_m3", "wet_duration_s"):
        previous = 0 if checkpoint is None else checkpoint["arrays"]["cumulative_" + key]
        checkpoint_arrays["cumulative_" + key] = readonly(previous + arrays[key])
    elapsed = 0 if checkpoint is None else checkpoint["metadata"]["elapsed_s"]
    count = 0 if checkpoint is None else checkpoint["metadata"]["substeps"]
    work = 0 if checkpoint is None else checkpoint["metadata"]["work_face_steps"]
    checkpoint_metadata = {"schema":"td-storage-continuation-v1", "execution_profile":"v9-compiled-hour-loop-v8-equivalent-v1",
        "hierarchy_identity_sha256":hierarchy["identity_sha256"], "parameters":config, "runoff_parameters":asdict(runoff),
        "forcing_identity":forcing_identity, "dt_s":float(dt_s),"substep_s":sub_dt,"elapsed_s":elapsed+len(rain)*dt_s, "substeps":count+substeps,
        "work_face_steps":work+substeps*len(faces), "cells":bed.size,"faces":len(faces),
        "last_page_storage_identity":result["identity_sha256"], "hydraulic_ready":False,"transient_converged":False}
    saved_checkpoint = {"arrays":checkpoint_arrays,"metadata":checkpoint_metadata,"identity_sha256":identity(checkpoint_arrays,checkpoint_metadata)}
    return {"storage":result,"checkpoint":saved_checkpoint}
