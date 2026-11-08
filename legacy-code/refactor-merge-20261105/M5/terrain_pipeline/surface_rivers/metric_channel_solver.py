"""Explicit finite-volume Manning routing with committed-prefix failure results."""

from dataclasses import asdict

import numpy as np

from terrain_pipeline.surface_rivers.metric_channel_state import (
    ChannelConfig, ChannelForcing, ChannelNetwork, _float_array, validate_channel_geometry_identity,
)


ALGORITHM = "manning-rectangular-explicit-v2"
MAX_TRACE_BYTES = 128 * 1024 * 1024


def _hydraulics(network, volume):
    area = volume / network.length_m
    depth = area / network.width_m
    perimeter = network.width_m + 2. * depth
    q = np.zeros_like(volume)
    wave = np.zeros_like(volume)
    active = (volume > 0.) & np.isin(network.terminal_kind, ("interior", "open_outflow"))
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        q[active] = (area[active] * (area[active] / perimeter[active]) ** (2. / 3.)
                     * np.sqrt(network.bed_slope[active]) / network.roughness[active])
        wave[active] = q[active] / area[active] * (5. / 3. - 4. * depth[active] / (3. * perimeter[active]))
    return area, depth, q, wave


def solve_channel(network, forcing, initial_volume_m3=None, config=None):
    """Route local inputs on a DAG; return complete or committed failed-prefix trace."""
    if not isinstance(network, ChannelNetwork) or not isinstance(forcing, ChannelForcing):
        raise ValueError("ChannelNetwork and ChannelForcing required")
    validate_channel_geometry_identity(network.receiver, network.bed_elevation_m,
                                      network.bed_slope, network.receiver_distance_m)
    if config is None:
        config = ChannelConfig()
    if not isinstance(config, ChannelConfig):
        raise ValueError("ChannelConfig required")
    n = network.receiver.size
    if forcing.local_q_m3_s.shape[1] != n:
        raise ValueError("forcing node count does not match network")
    if initial_volume_m3 is None:
        volume = np.zeros(n, dtype=np.float64)
    else:
        volume = _float_array(initial_volume_m3, (n,), "initial_volume_m3", nonnegative=True).copy()
    capacity = network.length_m * network.width_m * network.max_depth_m
    if not np.isfinite(capacity).all() or np.any(volume > capacity):
        raise ValueError("initial volume or channel capacity outside depth limit")

    times = [float(forcing.time_seconds[0])]
    volumes = [volume.copy()]
    inflows, outflows, locals_, boundaries, residuals, cfls = [], [], [], [], [], []
    state_area, state_depth, state_q, state_wave = _hydraulics(network, volume)
    initial_stage = network.bed_elevation_m + state_depth
    if not all(np.isfinite(value).all() for value in (state_area, state_depth, state_q, state_wave, initial_stage)):
        raise ValueError("initial hydraulic state must be finite")
    areas = [state_area]
    depths = [state_depth]
    end_q = [state_q]
    stage = [initial_stage]
    failure = None
    interval = 0
    receiver = network.receiver
    interior = receiver >= 0
    outlet = network.terminal_kind == "open_outflow"
    end_time = float(forcing.time_seconds[-1])
    trace_limit = MAX_TRACE_BYTES // (8 * (28 * n + 4))

    while times[-1] < end_time:
        if len(inflows) >= config.max_steps:
            failure = "maximum step count exceeded"
            break
        if len(inflows) >= trace_limit:
            failure = "trace byte budget exceeded"
            break
        now = times[-1]
        while interval + 1 < forcing.time_seconds.size - 1 and now >= forcing.time_seconds[interval + 1]:
            interval += 1
        segment_end = float(forcing.time_seconds[interval + 1])
        local = forcing.local_q_m3_s[interval]
        q = end_q[-1]
        wave = state_wave
        dt = min(config.max_dt_seconds, segment_end - now)
        moving = wave > 0.
        if np.any(moving):
            dt = min(dt, float(np.min(config.cfl * network.length_m[moving] / wave[moving])))
        draining = q > 0.
        if np.any(draining):
            dt = min(dt, float(np.min(config.cfl * volume[draining] / q[draining])))
        if not np.isfinite(dt) or dt <= 0. or (dt < config.min_dt_seconds and segment_end - now > config.min_dt_seconds):
            failure = "minimum internal step required or nonfinite time step"
            break
        if now + dt == now:
            failure = "time resolution exhausted"
            break
        next_time = segment_end if now + dt >= segment_end else now + dt
        if next_time - now > dt:
            next_time = float(np.nextafter(next_time, now))
        if next_time <= now:
            failure = "time resolution exhausted"
            break
        actual_dt = next_time - now
        if actual_dt > config.max_dt_seconds * (1. + 1e-12):
            failure = "maximum internal step exceeded at time resolution"
            break
        donor = np.zeros(n, dtype=np.float64)
        np.add.at(donor, receiver[interior], q[interior])
        with np.errstate(over="ignore", invalid="ignore"):
            next_volume = volume + actual_dt * (local + donor - q)
        if not np.isfinite(next_volume).all() or np.any(next_volume < -1e-12 * np.maximum(1., capacity)):
            failure = "nonfinite or negative volume"
            break
        next_volume = np.maximum(next_volume, 0.)
        if np.any(next_volume > capacity + 1e-12 * np.maximum(1., capacity)):
            failure = "depth limit exceeded"
            break
        next_area, next_depth, next_q, next_wave = _hydraulics(network, next_volume)
        next_stage = network.bed_elevation_m + next_depth
        if not all(np.isfinite(value).all() for value in (next_area, next_depth, next_q, next_wave, next_stage)):
            failure = "nonfinite hydraulic state"
            break
        boundary = actual_dt * np.where(outlet, q, 0.)
        residual = next_volume - volume - actual_dt * (local + donor - q)
        cfl_number = float(np.max(wave * actual_dt / network.length_m))
        if not np.isfinite(boundary).all() or not np.isfinite(residual).all():
            failure = "nonfinite water ledger"
            break
        if not np.isfinite(cfl_number) or cfl_number > config.cfl * (1. + 1e-12):
            failure = "CFL bound exceeded at time resolution"
            break
        times.append(next_time)
        volumes.append(next_volume.copy())
        inflows.append(donor.copy())
        outflows.append(q.copy())
        locals_.append(local.copy())
        boundaries.append(boundary)
        residuals.append(residual)
        cfls.append(cfl_number)
        areas.append(next_area)
        depths.append(next_depth)
        stage.append(next_stage)
        end_q.append(next_q)
        volume = next_volume
        state_wave = next_wave

    step_shape = (len(inflows), n)
    result = {"arrays": {
        "time_seconds": np.asarray(times, np.float64),
        "volume_m3": np.stack(volumes),
        "inflow_q_m3_s": np.stack(inflows) if inflows else np.empty(step_shape),
        "outflow_q_m3_s": np.stack(outflows) if outflows else np.empty(step_shape),
        "local_q_m3_s": np.stack(locals_) if locals_ else np.empty(step_shape),
        "outflow_end_q_m3_s": np.stack(end_q),
        "depth_m": np.stack(depths), "stage_m": np.stack(stage),
        "area_m2": np.stack(areas),
        "boundary_outflow_volume_m3": np.stack(boundaries) if boundaries else np.empty(step_shape),
        "balance_residual_m3": np.stack(residuals) if residuals else np.empty(step_shape),
        "cfl_number": np.asarray(cfls, np.float64),
    }, "metadata": {
        "algorithm": ALGORITHM, "status": "failed_prefix" if failure else "complete",
        "failure_reason": failure, "requested_end_time_seconds": end_time,
        "last_time_seconds": times[-1], "config": asdict(config),
    }}
    return result
