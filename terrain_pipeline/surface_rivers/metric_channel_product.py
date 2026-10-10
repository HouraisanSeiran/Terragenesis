"""Cold-verifiable M3 channel trace and output sampling."""

import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle


SCHEMA = "terragenesis-channel-diagnostic-v1"
OUTPUT_SCHEMA = "terragenesis-channel-output-v1"
ALGORITHM = "manning-rectangular-explicit-v1"
MAX_BYTES = 128 * 1024 * 1024
NETWORK_FIELDS = ("receiver", "length_m", "width_m", "bed_elevation_m", "bed_slope",
                  "roughness", "max_depth_m", "terminal_kind")
STATE_FIELDS = ("volume_m3", "outflow_end_q_m3_s", "depth_m", "stage_m", "area_m2")
STEP_FIELDS = ("inflow_q_m3_s", "outflow_q_m3_s", "local_q_m3_s",
               "boundary_outflow_volume_m3", "balance_residual_m3")
SEMANTICS = {"time_seconds": "committed_numerical_step_endpoints",
             "volume_m3": "state_at_time_seconds",
             "outflow_q_m3_s": "pre_step_manning_interval_average",
             "outflow_end_q_m3_s": "instantaneous_manning_from_state",
             "inflow_q_m3_s": "same_step_donor_outflow_only",
             "local_q_m3_s": "piecewise_constant_external_input",
             "positive_direction": "downstream_out_of_domain_at_open_terminal"}


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _manning(volume, length, width, slope, roughness, active):
    area = volume / length
    depth = area / width
    perimeter = width + 2. * depth
    radius = np.divide(area, perimeter, out=np.zeros_like(area), where=perimeter > 0.)
    q = area * np.power(radius, 2. / 3.) * np.sqrt(slope) / roughness
    q = np.where(active, q, 0.)
    derivative = (np.sqrt(slope) / roughness * np.power(radius, 2. / 3.)
                  * (5. / 3. - 4. * area / (3. * width * perimeter)))
    derivative = np.where(active & (area > 0.), derivative, 0.)
    return area, depth, q, derivative


def _network_arrays(network):
    return {"network_" + name: np.asarray(getattr(network, name)).copy() for name in NETWORK_FIELDS}


def _next_failure_reason(arrays, config):
    """Re-evaluate one candidate after the committed prefix, without calling the solver."""
    times = arrays["trace_time_seconds"]
    steps = times.size - 1
    n = arrays["network_receiver"].size
    if steps >= config["max_steps"]:
        return "maximum step count exceeded"
    if steps >= MAX_BYTES // (8 * (28 * n + 4)):
        return "trace byte budget exceeded"
    forcing_time = arrays["forcing_time_seconds"]
    now = float(times[-1])
    interval = min(int(np.searchsorted(forcing_time, now, side="right") - 1), forcing_time.size - 2)
    segment_end = float(forcing_time[interval + 1])
    volume = arrays["trace_volume_m3"][-1]
    length = arrays["network_length_m"]
    width = arrays["network_width_m"]
    slope = arrays["network_bed_slope"]
    roughness = arrays["network_roughness"]
    kind = arrays["network_terminal_kind"]
    active = np.isin(kind, ("interior", "open_outflow"))
    _, _, q, wave = _manning(volume, length, width, slope, roughness, active)
    dt = min(config["max_dt_seconds"], segment_end - now)
    moving = wave > 0.
    if np.any(moving):
        dt = min(dt, float(np.min(config["cfl"] * length[moving] / wave[moving])))
    draining = q > 0.
    if np.any(draining):
        dt = min(dt, float(np.min(config["cfl"] * volume[draining] / q[draining])))
    if (not np.isfinite(dt) or dt <= 0. or
            (dt < config["min_dt_seconds"] and segment_end - now > config["min_dt_seconds"])):
        return "minimum internal step required or nonfinite time step"
    if now + dt == now:
        return "time resolution exhausted"
    next_time = segment_end if now + dt >= segment_end else now + dt
    actual_dt = next_time - now
    if actual_dt > config["max_dt_seconds"] * (1. + 1e-12):
        return "maximum internal step exceeded at time resolution"
    donor = np.zeros(n, np.float64)
    receiver = arrays["network_receiver"]
    interior = receiver >= 0
    np.add.at(donor, receiver[interior], q[interior])
    local = arrays["forcing_local_q_m3_s"][interval]
    capacity = length * width * arrays["network_max_depth_m"]
    with np.errstate(over="ignore", invalid="ignore"):
        next_volume = volume + actual_dt * (local + donor - q)
    if not np.isfinite(next_volume).all() or np.any(next_volume < -1e-12 * np.maximum(1., capacity)):
        return "nonfinite or negative volume"
    next_volume = np.maximum(next_volume, 0.)
    if np.any(next_volume > capacity + 1e-12 * np.maximum(1., capacity)):
        return "depth limit exceeded"
    next_area, next_depth, next_q, next_wave = _manning(next_volume, length, width, slope, roughness, active)
    next_stage = arrays["network_bed_elevation_m"] + next_depth
    if not all(np.isfinite(value).all() for value in (next_area, next_depth, next_q, next_wave, next_stage)):
        return "nonfinite hydraulic state"
    boundary = actual_dt * np.where(kind == "open_outflow", q, 0.)
    residual = next_volume - volume - actual_dt * (local + donor - q)
    cfl_number = float(np.max(wave * actual_dt / length))
    if not np.isfinite(boundary).all() or not np.isfinite(residual).all():
        return "nonfinite water ledger"
    if not np.isfinite(cfl_number) or cfl_number > config["cfl"] * (1. + 1e-12):
        return "CFL bound exceeded at time resolution"
    return None


def make_channel_product(network, forcing, result):
    if result["metadata"].get("algorithm") != ALGORITHM:
        raise ValueError("unsupported channel solver algorithm")
    arrays = _network_arrays(network)
    arrays["forcing_time_seconds"] = forcing.time_seconds.copy()
    arrays["forcing_local_q_m3_s"] = forcing.local_q_m3_s.copy()
    arrays.update({"trace_" + key: value.copy() for key, value in result["arrays"].items()})
    trace_time = arrays["trace_time_seconds"]
    status = result["metadata"]["status"]
    unfinished = None if status == "complete" else [float(trace_time[-1]), float(forcing.time_seconds[-1])]
    dt = np.diff(trace_time)
    local_volume = float(np.sum(arrays["trace_local_q_m3_s"] * dt[:, None], dtype=np.float64))
    boundary_volume = float(np.sum(arrays["trace_boundary_outflow_volume_m3"], dtype=np.float64))
    initial = float(np.sum(arrays["trace_volume_m3"][0], dtype=np.float64))
    final = float(np.sum(arrays["trace_volume_m3"][-1], dtype=np.float64))
    metadata = {"schema": SCHEMA, "algorithm": ALGORITHM, "status": status,
                "failure_reason": result["metadata"]["failure_reason"],
                "requested_end_time_seconds": result["metadata"]["requested_end_time_seconds"],
                "last_time_seconds": result["metadata"]["last_time_seconds"],
                "unfinished_time_seconds": unfinished,
                "config": dict(result["metadata"]["config"]),
                "network_source_identity_sha256": network.source_identity_sha256,
                "section_source": network.section_source,
                "roughness_source": network.roughness_source,
                "forcing_source_identity_sha256": forcing.source_identity_sha256,
                "semantics": dict(SEMANTICS),
                "water_budget_m3": {"initial_storage": initial, "local_input": local_volume,
                                    "boundary_outflow": boundary_volume, "final_storage": final,
                                    "residual": initial + local_volume - boundary_volume - final},
                "hydraulic_ready": False, "natural_outlet_verified": False,
                "publishable": False}
    arrays = {name: readonly(value) for name, value in arrays.items()}
    product = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_channel_product(product)
    return product


def validate_channel_product(product):
    if not isinstance(product, dict) or set(product) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid channel product")
    arrays, meta = product["arrays"], product["metadata"]
    expected = {"network_" + name for name in NETWORK_FIELDS} | {"forcing_time_seconds", "forcing_local_q_m3_s"}
    expected |= {"trace_time_seconds", "trace_cfl_number"}
    expected |= {"trace_" + name for name in STATE_FIELDS + STEP_FIELDS}
    if (set(arrays) != expected or set(meta) != {"schema", "algorithm", "status", "failure_reason",
            "requested_end_time_seconds", "last_time_seconds", "unfinished_time_seconds", "config",
            "network_source_identity_sha256", "section_source", "roughness_source",
            "forcing_source_identity_sha256", "semantics", "water_budget_m3",
            "hydraulic_ready", "natural_outlet_verified", "publishable"}
            or meta["schema"] != SCHEMA or meta["algorithm"] != ALGORITHM
            or meta["semantics"] != SEMANTICS
            or any(meta[key] is not False for key in
                   ("hydraulic_ready", "natural_outlet_verified", "publishable"))
            or product["identity_sha256"] != identity(arrays, meta)):
        raise ValueError("channel identity/schema/scope mismatch")
    if not all(_sha(meta[key]) for key in ("network_source_identity_sha256",
                                             "forcing_source_identity_sha256")):
        raise ValueError("channel source SHA256 required")
    if any(not isinstance(meta[key], str) or not meta[key].strip() for key in
           ("section_source", "roughness_source")):
        raise ValueError("channel section/roughness provenance required")
    receiver = arrays["network_receiver"]
    if receiver.dtype != np.int64 or receiver.ndim != 1 or not 1 <= receiver.size <= 4096:
        raise ValueError("bounded channel receiver required")
    n = receiver.size
    kind = arrays["network_terminal_kind"]
    if (kind.shape != (n,) or kind.dtype.kind != "U"
            or not np.isin(kind, ("interior", "open_outflow", "closed_wall", "unknown_boundary")).all()
            or np.any((receiver == -1) != (kind != "interior"))
            or np.any((receiver >= 0) & (receiver >= n)) or np.any(receiver < -1)):
        raise ValueError("invalid channel terminal graph")
    for node in range(n):
        seen = set()
        current = node
        while current >= 0:
            if current in seen:
                raise ValueError("cyclic channel graph")
            seen.add(current)
            current = int(receiver[current])
    parameters = {}
    for name in NETWORK_FIELDS[1:-1]:
        value = arrays["network_" + name]
        if value.dtype != np.float64 or value.shape != (n,) or not np.isfinite(value).all():
            raise ValueError("invalid channel geometry: " + name)
        parameters[name] = value
    length, width, bed, slope, roughness, max_depth = (parameters[name] for name in
        ("length_m", "width_m", "bed_elevation_m", "bed_slope", "roughness", "max_depth_m"))
    if (np.any(length <= 0.) or np.any(width <= 0.) or np.any(roughness <= 0.)
            or np.any(max_depth <= 0.) or np.any(slope < 0.)
            or np.any(slope[np.isin(kind, ("interior", "open_outflow"))] <= 0.)):
        raise ValueError("invalid channel physical bounds")
    force_time, force_q = arrays["forcing_time_seconds"], arrays["forcing_local_q_m3_s"]
    if (force_time.dtype != np.float64 or force_time.ndim != 1 or not 2 <= force_time.size <= 100001
            or not np.isfinite(force_time).all() or np.any(force_time < 0.)
            or not np.isfinite(np.diff(force_time)).all()
            or np.any(np.diff(force_time) <= 0.) or force_q.dtype != np.float64
            or force_q.shape != (force_time.size - 1, n)
            or not np.isfinite(force_q).all() or np.any(force_q < 0.)):
        raise ValueError("invalid channel forcing")
    times = arrays["trace_time_seconds"]
    if (times.dtype != np.float64 or times.ndim != 1 or not 1 <= times.size <= 1000001
            or not np.isfinite(times).all() or times[0] != force_time[0]
            or not np.isfinite(np.diff(times)).all()
            or np.any(np.diff(times) <= 0.) or times[-1] > force_time[-1]):
        raise ValueError("invalid committed channel chronology")
    steps = times.size - 1
    config = meta["config"]
    if (not isinstance(config, dict) or set(config) !=
            {"max_dt_seconds", "cfl", "max_steps", "min_dt_seconds"}
            or any(type(config[key]) not in (int, float) or not math.isfinite(config[key]) or config[key] <= 0.
                   for key in ("max_dt_seconds", "cfl", "min_dt_seconds"))
            or config["cfl"] > 1. or config["min_dt_seconds"] > config["max_dt_seconds"]
            or type(config["max_steps"]) is not int or not 1 <= config["max_steps"] <= 1000000
            or steps > config["max_steps"]):
        raise ValueError("invalid channel config or resource budget")
    if sum(value.nbytes for value in arrays.values()) > MAX_BYTES:
        raise ValueError("channel trace byte budget exceeded")
    dt = np.diff(times)
    ends_at_forcing_boundary = np.isin(times[1:], force_time[1:])
    if (np.any(dt > config["max_dt_seconds"] * (1. + 1e-12))
            or np.any((dt < config["min_dt_seconds"] * (1. - 1e-12)) & ~ends_at_forcing_boundary)):
        raise ValueError("channel numerical step outside configured bounds")
    for name in STATE_FIELDS:
        value = arrays["trace_" + name]
        if value.dtype != np.float64 or value.shape != (steps + 1, n) or not np.isfinite(value).all():
            raise ValueError("invalid channel state array: " + name)
    for name in STEP_FIELDS:
        value = arrays["trace_" + name]
        if value.dtype != np.float64 or value.shape != (steps, n) or not np.isfinite(value).all():
            raise ValueError("invalid channel step array: " + name)
    cfl = arrays["trace_cfl_number"]
    if cfl.dtype != np.float64 or cfl.shape != (steps,) or not np.isfinite(cfl).all():
        raise ValueError("invalid channel CFL trace")
    volume = arrays["trace_volume_m3"]
    capacity = length * width * max_depth
    if not np.isfinite(capacity).all() or np.any(volume > capacity):
        raise ValueError("invalid finite channel capacity or storage")
    if np.any(volume < 0.):
        raise ValueError("negative channel volume")
    active = np.isin(kind, ("interior", "open_outflow"))
    area, depth, end_q, derivative = _manning(volume, length, width, slope, roughness, active)
    if np.any(depth > max_depth + 1e-10):
        raise ValueError("channel depth limit exceeded")
    for name, computed in (("area_m2", area), ("depth_m", depth),
                           ("stage_m", bed + depth), ("outflow_end_q_m3_s", end_q)):
        if not np.allclose(arrays["trace_" + name], computed, rtol=1e-10, atol=1e-10):
            raise ValueError("channel Manning state mismatch: " + name)
    if steps:
        forcing_step = np.searchsorted(force_time, times[:-1], side="right") - 1
        if np.any(forcing_step < 0) or np.any(forcing_step >= force_q.shape[0]) or np.any(times[1:] > force_time[forcing_step + 1] + 1e-12):
            raise ValueError("channel step straddles forcing discontinuity")
        if not np.allclose(arrays["trace_local_q_m3_s"], force_q[forcing_step], rtol=0., atol=1e-12):
            raise ValueError("channel local forcing mismatch")
        step_q = arrays["trace_outflow_q_m3_s"]
        if not np.allclose(step_q, end_q[:-1], rtol=1e-10, atol=1e-10):
            raise ValueError("channel pre-step Manning Q mismatch")
        donor = np.zeros_like(step_q)
        for node, target in enumerate(receiver):
            if target >= 0:
                donor[:, target] += step_q[:, node]
        if not np.allclose(arrays["trace_inflow_q_m3_s"], donor, rtol=1e-10, atol=1e-10):
            raise ValueError("channel donor flux mismatch")
        expected_boundary = np.where(kind == "open_outflow", step_q * dt[:, None], 0.)
        if not np.allclose(arrays["trace_boundary_outflow_volume_m3"], expected_boundary, rtol=1e-10, atol=1e-10):
            raise ValueError("channel terminal flux mismatch")
        expected_delta = dt[:, None] * (arrays["trace_local_q_m3_s"] + donor - step_q)
        residual = np.diff(volume, axis=0) - expected_delta
        scale = np.maximum(1., np.abs(volume[:-1]) + np.abs(expected_delta))
        if (not np.allclose(arrays["trace_balance_residual_m3"], residual, rtol=1e-10, atol=1e-10)
                or np.any(np.abs(residual) > 1e-8 * scale)):
            raise ValueError("channel continuity mismatch")
        expected_cfl = np.max(dt[:, None] * derivative[:-1] / length, axis=1)
        if (not np.allclose(cfl, expected_cfl, rtol=1e-9, atol=1e-10)
                or np.any(cfl > config["cfl"] * (1. + 1e-9))):
            raise ValueError("channel CFL mismatch")
    status = meta["status"]
    if (status not in ("complete", "failed_prefix") or
            meta["requested_end_time_seconds"] != float(force_time[-1]) or
            meta["last_time_seconds"] != float(times[-1])):
        raise ValueError("channel prefix chronology mismatch")
    if status == "complete":
        if times[-1] != force_time[-1] or meta["failure_reason"] is not None or meta["unfinished_time_seconds"] is not None:
            raise ValueError("incomplete channel trace claimed complete")
    elif (times[-1] >= force_time[-1] or not isinstance(meta["failure_reason"], str)
          or not meta["failure_reason"].strip() or
          meta["unfinished_time_seconds"] != [float(times[-1]), float(force_time[-1])]):
        raise ValueError("invalid channel failure prefix")
    if status == "failed_prefix" and meta["failure_reason"] != _next_failure_reason(arrays, config):
        raise ValueError("channel failure reason does not match next numerical candidate")
    budget = meta["water_budget_m3"]
    actual = {"initial_storage": float(np.sum(volume[0])),
              "local_input": float(np.sum(arrays["trace_local_q_m3_s"] * dt[:, None])),
              "boundary_outflow": float(np.sum(arrays["trace_boundary_outflow_volume_m3"])),
              "final_storage": float(np.sum(volume[-1]))}
    actual["residual"] = actual["initial_storage"] + actual["local_input"] - actual["boundary_outflow"] - actual["final_storage"]
    if (not isinstance(budget, dict) or set(budget) != set(actual)
            or any(not np.isfinite(value) or not np.isclose(budget[key], value, rtol=1e-10, atol=1e-8)
                   for key, value in actual.items())
            or abs(actual["residual"]) > 1e-8 * max(1., actual["local_input"], actual["initial_storage"])):
        raise ValueError("channel global water budget mismatch")
    return True


def save_channel_product(path, product):
    save_bundle(path, product, validator=validate_channel_product)


def load_channel_product(path, *, expected_sha256, expected_identity):
    product = load_bundle(path, expected_sha256=expected_sha256,
                          validator=validate_channel_product, max_bytes=MAX_BYTES)
    if product["identity_sha256"] != expected_identity:
        raise ValueError("external channel identity mismatch")
    return product


def sample_channel_output(product, state_time_seconds):
    validate_channel_product(product)
    source = product["arrays"]
    trace_times = source["trace_time_seconds"]
    requested = np.asarray(state_time_seconds)
    if (requested.dtype != np.float64 or requested.ndim != 1 or requested.size < 1
            or not np.isfinite(requested).all() or requested[0] != trace_times[0]
            or requested[-1] != trace_times[-1] or np.any(np.diff(requested) <= 0.)):
        raise ValueError("sample times must include actual first/last state")
    if trace_times.size > 1 and requested.size < 2:
        raise ValueError("nonempty trace needs first and last output states")
    volume = source["trace_volume_m3"]
    n = volume.shape[1]
    states = requested.size
    groups = states - 1
    network_bytes = sum(source["network_" + name].nbytes for name in NETWORK_FIELDS)
    output_bytes = 8 * (5 * states * n + 3 * groups * n + 2 * states) + network_bytes
    if states > 1_000_001 or output_bytes > MAX_BYTES:
        raise ValueError("sampled channel output resource budget exceeded")
    sampled_volume = np.empty((requested.size, n), np.float64)
    for index, time in enumerate(requested):
        step = min(np.searchsorted(trace_times, time, side="right") - 1, trace_times.size - 2)
        if trace_times.size == 1:
            sampled_volume[index] = volume[0]
        else:
            ratio = (time - trace_times[step]) / (trace_times[step + 1] - trace_times[step])
            sampled_volume[index] = volume[step] + ratio * (volume[step + 1] - volume[step])
    length, width = source["network_length_m"], source["network_width_m"]
    slope, roughness = source["network_bed_slope"], source["network_roughness"]
    active = np.isin(source["network_terminal_kind"], ("interior", "open_outflow"))
    area, depth, end_q, _ = _manning(sampled_volume, length, width, slope, roughness, active)
    groups = requested.size - 1
    local = np.zeros((groups, n), np.float64)
    outflow = np.zeros_like(local)
    boundary = np.zeros_like(local)
    for index in range(groups):
        left = np.maximum(trace_times[:-1], requested[index])
        right = np.minimum(trace_times[1:], requested[index + 1])
        overlap = np.maximum(right - left, 0.)
        duration = requested[index + 1] - requested[index]
        local[index] = np.sum(source["trace_local_q_m3_s"] * overlap[:, None], axis=0) / duration
        outflow[index] = np.sum(source["trace_outflow_q_m3_s"] * overlap[:, None], axis=0) / duration
        boundary[index] = np.where(source["network_terminal_kind"] == "open_outflow",
                                   outflow[index] * duration, 0.)
    arrays = {"time_seconds": readonly(requested.copy()), "volume_m3": readonly(sampled_volume),
              "area_m2": readonly(area), "depth_m": readonly(depth),
              "stage_m": readonly(source["network_bed_elevation_m"] + depth),
              "outflow_end_q_m3_s": readonly(end_q),
              "local_q_m3_s": readonly(local), "outflow_q_m3_s": readonly(outflow),
              "boundary_outflow_volume_m3": readonly(boundary),
              "cumulative_boundary_outflow_volume_m3": readonly(np.r_[0., np.cumsum(np.sum(boundary, axis=1))])}
    arrays.update({name: source[name] for name in ("network_receiver", "network_length_m",
                  "network_width_m", "network_bed_elevation_m", "network_bed_slope",
                  "network_roughness", "network_max_depth_m", "network_terminal_kind")})
    metadata = {"schema": OUTPUT_SCHEMA, "source_product_identity_sha256": product["identity_sha256"],
                "source_status": product["metadata"]["status"],
                "source_water_budget_m3": dict(product["metadata"]["water_budget_m3"]),
                "state_semantics": "sampled_initial_and_numerical_state_interpolation",
                "q_semantics": "overlap_integrated_interval_average",
                "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
    sampled = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_channel_output(sampled)
    return sampled


def validate_channel_output(sampled):
    if not isinstance(sampled, dict) or set(sampled) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid sampled channel bundle")
    arrays, meta = sampled["arrays"], sampled["metadata"]
    expected = {"time_seconds", "volume_m3", "area_m2", "depth_m", "stage_m",
                "outflow_end_q_m3_s", "local_q_m3_s", "outflow_q_m3_s",
                "boundary_outflow_volume_m3", "cumulative_boundary_outflow_volume_m3"}
    expected |= {"network_" + name for name in NETWORK_FIELDS}
    if (set(arrays) != expected or set(meta) != {"schema", "source_product_identity_sha256",
            "source_status", "source_water_budget_m3", "state_semantics", "q_semantics",
            "hydraulic_ready", "natural_outlet_verified", "publishable"}
            or meta["schema"] != OUTPUT_SCHEMA or not _sha(meta["source_product_identity_sha256"])
            or meta["source_status"] not in ("complete", "failed_prefix")
            or meta["state_semantics"] != "sampled_initial_and_numerical_state_interpolation"
            or meta["q_semantics"] != "overlap_integrated_interval_average"
            or any(meta[name] is not False for name in
                   ("hydraulic_ready", "natural_outlet_verified", "publishable"))
            or sampled["identity_sha256"] != identity(arrays, meta)):
        raise ValueError("sampled channel identity/schema mismatch")
    times = arrays["time_seconds"]
    receiver = arrays["network_receiver"]
    if (times.dtype != np.float64 or times.ndim != 1 or not 1 <= times.size <= 1000001
            or not np.isfinite(times).all() or np.any(np.diff(times) <= 0.)
            or receiver.dtype != np.int64 or receiver.ndim != 1 or not 1 <= receiver.size <= 4096):
        raise ValueError("invalid sampled channel times/nodes")
    n, states, groups = receiver.size, times.size, times.size - 1
    if sum(value.nbytes for value in arrays.values()) > MAX_BYTES:
        raise ValueError("sampled channel byte budget exceeded")
    for name in NETWORK_FIELDS[1:-1]:
        value = arrays["network_" + name]
        if value.dtype != np.float64 or value.shape != (n,) or not np.isfinite(value).all():
            raise ValueError("invalid sampled geometry: " + name)
    kind = arrays["network_terminal_kind"]
    if kind.dtype.kind != "U" or kind.shape != (n,) or not np.isin(kind, ("interior", "open_outflow", "closed_wall", "unknown_boundary")).all():
        raise ValueError("invalid sampled terminal kind")
    if (np.any((receiver < -1) | (receiver >= n) | (receiver == np.arange(n)))
            or np.any((receiver == -1) != (kind != "interior"))):
        raise ValueError("invalid sampled channel receiver")
    for start in range(n):
        seen = set()
        node = start
        while node >= 0:
            if node in seen:
                raise ValueError("cyclic sampled channel graph")
            seen.add(node)
            node = int(receiver[node])
    for name in ("volume_m3", "area_m2", "depth_m", "stage_m", "outflow_end_q_m3_s"):
        value = arrays[name]
        if value.dtype != np.float64 or value.shape != (states, n) or not np.isfinite(value).all():
            raise ValueError("invalid sampled state: " + name)
    for name in ("local_q_m3_s", "outflow_q_m3_s", "boundary_outflow_volume_m3"):
        value = arrays[name]
        if value.dtype != np.float64 or value.shape != (groups, n) or not np.isfinite(value).all() or np.any(value < 0.):
            raise ValueError("invalid sampled interval: " + name)
    volume = arrays["volume_m3"]
    if np.any(volume < 0.):
        raise ValueError("negative sampled channel volume")
    length, width, bed, slope, roughness, limit = (arrays["network_" + name] for name in
        ("length_m", "width_m", "bed_elevation_m", "bed_slope", "roughness", "max_depth_m"))
    if (np.any(length <= 0.) or np.any(width <= 0.) or np.any(roughness <= 0.)
            or np.any(limit <= 0.) or np.any(slope < 0.)
            or np.any(slope[np.isin(kind, ("interior", "open_outflow"))] <= 0.)
            or not np.isfinite(length * width * limit).all()):
        raise ValueError("invalid sampled physical geometry")
    active = np.isin(kind, ("interior", "open_outflow"))
    area, depth, end_q, _ = _manning(volume, length, width, slope, roughness, active)
    if (np.any(depth > limit + 1e-10) or
            any(not np.allclose(arrays[key], expected_value, rtol=1e-10, atol=1e-10)
                for key, expected_value in (("area_m2", area), ("depth_m", depth),
                    ("stage_m", bed + depth), ("outflow_end_q_m3_s", end_q)))):
        raise ValueError("sampled Manning state mismatch")
    duration = np.diff(times)
    expected_boundary = np.where(kind == "open_outflow", arrays["outflow_q_m3_s"] * duration[:, None], 0.)
    if not np.allclose(arrays["boundary_outflow_volume_m3"], expected_boundary, rtol=1e-10, atol=1e-10):
        raise ValueError("sampled boundary integral mismatch")
    if np.any(arrays["outflow_q_m3_s"][:, np.isin(kind, ("closed_wall", "unknown_boundary"))] != 0.):
        raise ValueError("closed or unknown sampled terminal outflow")
    donor = np.zeros_like(arrays["outflow_q_m3_s"])
    for node, target in enumerate(receiver):
        if target >= 0:
            donor[:, target] += arrays["outflow_q_m3_s"][:, node]
    expected_delta = duration[:, None] * (arrays["local_q_m3_s"] + donor - arrays["outflow_q_m3_s"])
    per_node_residual = np.diff(volume, axis=0) - expected_delta
    scale = np.maximum(1., np.abs(volume[:-1]) + np.abs(expected_delta))
    if np.any(np.abs(per_node_residual) > 1e-8 * scale):
        raise ValueError("sampled per-node continuity mismatch")
    cumulative = arrays["cumulative_boundary_outflow_volume_m3"]
    expected_cumulative = np.r_[0., np.cumsum(np.sum(expected_boundary, axis=1, dtype=np.float64))]
    if cumulative.dtype != np.float64 or cumulative.shape != (states,) or not np.allclose(cumulative, expected_cumulative, rtol=1e-10, atol=1e-10):
        raise ValueError("sampled cumulative boundary mismatch")
    initial = float(np.sum(volume[0], dtype=np.float64))
    final = float(np.sum(volume[-1], dtype=np.float64))
    local_total = float(np.sum(arrays["local_q_m3_s"] * duration[:, None], dtype=np.float64))
    boundary_total = float(cumulative[-1])
    budget = meta["source_water_budget_m3"]
    actual = {"initial_storage": initial, "local_input": local_total,
              "boundary_outflow": boundary_total, "final_storage": final,
              "residual": initial + local_total - boundary_total - final}
    if (not isinstance(budget, dict) or set(budget) != set(actual)
            or any(not np.isfinite(value) or not np.isclose(budget[key], value, rtol=1e-10, atol=1e-8)
                   for key, value in actual.items())
            or abs(actual["residual"]) > 1e-8 * max(1., initial, local_total)):
        raise ValueError("sampled channel global budget mismatch")
    return True


def save_channel_output(path, sampled):
    save_bundle(path, sampled, validator=validate_channel_output)


def load_channel_output(path, *, expected_sha256, expected_identity, expected_product_identity):
    sampled = load_bundle(path, expected_sha256=expected_sha256,
                          validator=validate_channel_output, max_bytes=MAX_BYTES)
    if (sampled["identity_sha256"] != expected_identity
            or sampled["metadata"]["source_product_identity_sha256"] != expected_product_identity):
        raise ValueError("external channel output identity mismatch")
    return sampled
