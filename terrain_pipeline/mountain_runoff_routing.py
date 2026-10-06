"""Experimental conservative reach routing of immutable, local HRU discharge."""

from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from terrain_pipeline.rainfall_runoff import _hash, _json, _strict_json


ALGORITHM = "mountain-reach-backward-euler-v1"
SCHEMA = "mountain-reach-routing-npz-v1"
MAX_CELLS = 250_000
MAX_HRUS = 256
MAX_REACHES = 2048
MAX_STEPS = 3000
MAX_ENTRIES = 8_000_000
MAX_WORK = 30_000_000
MAX_BYTES = 768 * 1024 * 1024
INPUT_KEYS = ("height_m", "receiver", "flowline_mask", "outlet_mask", "cell_owner",
              "area_m2", "local_q_m3_s")
MAP_KEYS = ("river_reach", "cell_reach", "reach_downstream", "reach_order",
            "reach_length_m", "allocation_counts", "tau_s")
FLUX_KEYS = ("lateral_volume_m3", "upstream_volume_m3", "outflow_volume_m3",
             "storage_change_m3", "balance_residual_m3")
ARRAY_KEYS = INPUT_KEYS + MAP_KEYS + FLUX_KEYS + ("storage_m3", "outlet_q_m3_s")
INT_KEYS = {"receiver", "cell_owner", "river_reach", "cell_reach",
            "reach_downstream", "reach_order", "allocation_counts"}
BOOL_KEYS = {"flowline_mask", "outlet_mask"}
META_KEYS = {"algorithm", "schema", "dt_s", "spacing_m", "speed_m_s",
             "minimum_length_m", "source_binding", "input_hashes", "parameter_sha256"}


def _positive(value, name, maximum):
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number))
            or not math.isfinite(value) or not 0 < value <= maximum):
        raise ValueError(f"invalid {name}")


def preflight(steps, cells, hrus, reaches):
    """New routing-specific limits; not the obsolete 2M surface work ceiling."""
    if (not all(isinstance(value, (int, np.integer)) and not isinstance(value, bool)
                for value in (steps, cells, hrus, reaches))
            or not 1 <= steps <= MAX_STEPS or not 1 <= cells <= MAX_CELLS
            or not 1 <= hrus <= MAX_HRUS or not 1 <= reaches <= MAX_REACHES
            or steps * reaches > MAX_ENTRIES
            or steps * reaches * (hrus + 1) + cells * 8 > MAX_WORK):
        raise ValueError("routing resource budget exceeded")
    estimated_bytes = 8 * (12 * cells + steps * hrus + 8 * (steps + 1) * reaches)
    if estimated_bytes > MAX_BYTES:
        raise ValueError("routing byte budget exceeded")
    return {"steps": int(steps), "cells": int(cells), "hrus": int(hrus),
            "reaches": int(reaches), "estimated_bytes": int(estimated_bytes),
            "work_units": int(steps * reaches * (hrus + 1) + cells * 8),
            "max_work_units": MAX_WORK, "max_bytes": MAX_BYTES}


def _order(receiver):
    if (receiver.ndim != 1 or receiver.dtype != np.dtype("int64")
            or (receiver < -1).any() or (receiver >= receiver.size).any()):
        raise ValueError("invalid receiver indices/type")
    donors = np.bincount(receiver[receiver >= 0], minlength=receiver.size)
    queue = deque(np.flatnonzero(donors == 0).tolist())
    order = []
    while queue:
        current = queue.popleft()
        order.append(current)
        downstream = int(receiver[current])
        if downstream >= 0:
            donors[downstream] -= 1
            if donors[downstream] == 0:
                queue.append(downstream)
    if len(order) != receiver.size:
        raise ValueError("cyclic receiver graph")
    return np.asarray(order, dtype=np.int64)


def build_reaches(height_m, receiver, flowline_mask, outlet_mask, cell_owner,
                  area_m2, *, spacing_m, speed_m_s=1.0, minimum_length_m=30.0):
    """Vertex-disjoint maximal reaches; junction cell belongs to downstream reach."""
    _positive(spacing_m, "spacing_m", 1e5)
    _positive(speed_m_s, "speed_m_s", 100)
    _positive(minimum_length_m, "minimum_length_m", 1e6)
    height = np.asarray(height_m)
    if (height.ndim != 2 or height.dtype != np.dtype("float64")
            or not 1 <= height.size <= MAX_CELLS or not np.isfinite(height).all()):
        raise ValueError("invalid height grid")
    for array, dtype in ((receiver, "int64"), (cell_owner, "int64"),
                         (flowline_mask, "bool"), (outlet_mask, "bool")):
        if not isinstance(array, np.ndarray) or array.shape != height.shape or array.dtype != np.dtype(dtype):
            raise ValueError("invalid typed grid")
    if (not isinstance(area_m2, np.ndarray) or area_m2.ndim != 1
            or area_m2.dtype != np.dtype("float64") or not 1 <= area_m2.size <= MAX_HRUS
            or not np.isfinite(area_m2).all() or (area_m2 <= 0).any()):
        raise ValueError("invalid HRU areas")
    land = height.ravel() > 0
    owner = cell_owner.ravel()
    if (not land.any() or (owner[~land] != -1).any() or (owner[land] < 0).any()
            or (owner[land] >= area_m2.size).any()):
        raise ValueError("every land cell must have exactly one HRU")
    counts = np.bincount(owner[land], minlength=area_m2.size)
    if not np.array_equal(counts * spacing_m ** 2, area_m2):
        raise ValueError("HRU area/count mismatch")
    flat_receiver = receiver.ravel()
    order = _order(flat_receiver)
    outlets = outlet_mask.ravel()
    if not np.array_equal(flat_receiver == -1, outlets):
        raise ValueError("receiver/outlet mismatch")
    river = flowline_mask.ravel() | outlets
    river_receivers = flat_receiver[river & ~outlets]
    if not river[river_receivers].all():
        raise ValueError("legacy river not downstream closed")
    moving = np.flatnonzero(flat_receiver >= 0)
    downstream = flat_receiver[moving]
    width = height.shape[1]
    delta_row = np.abs(moving // width - downstream // width)
    delta_col = np.abs(moving % width - downstream % width)
    if ((delta_row > 1) | (delta_col > 1) | ((delta_row + delta_col) == 0)).any():
        raise ValueError("receiver is not a neighboring D8 cell")
    river_donors = np.bincount(river_receivers, minlength=height.size)
    starts = np.flatnonzero(river & ((river_donors != 1) | outlets))
    if not 1 <= starts.size <= MAX_REACHES:
        raise ValueError("reach count exceeds budget")
    river_reach = np.full(height.size, -1, dtype=np.int64)
    lengths = np.zeros(starts.size, dtype=np.float64)
    ends = np.empty(starts.size, dtype=np.int64)
    for reach, start in enumerate(starts):
        current = int(start)
        while True:
            river_reach[current] = reach
            target = int(flat_receiver[current])
            if target >= 0:
                lengths[reach] += spacing_m * math.hypot(
                    current // width - target // width, current % width - target % width)
            if target < 0 or river_donors[target] != 1 or outlets[target]:
                ends[reach] = target
                break
            current = target
    reach_downstream = np.full(starts.size, -1, dtype=np.int64)
    reach_downstream[ends >= 0] = river_reach[ends[ends >= 0]]
    reach_order = _order(reach_downstream)
    cell_reach = river_reach.copy()
    for current in order[::-1]:
        if cell_reach[current] < 0:
            cell_reach[current] = cell_reach[flat_receiver[current]]
    if (cell_reach[land] < 0).any():
        raise ValueError("unmapped land cell")
    allocation = np.bincount(cell_reach[land] * area_m2.size + owner[land],
                             minlength=starts.size * area_m2.size).reshape(starts.size, area_m2.size)
    return {"river_reach": river_reach.reshape(height.shape),
            "cell_reach": cell_reach.reshape(height.shape),
            "reach_downstream": reach_downstream, "reach_order": reach_order,
            "reach_length_m": lengths, "allocation_counts": allocation,
            "tau_s": np.maximum(lengths, minimum_length_m) / speed_m_s}


def route_local_discharge(inputs, *, dt_s, spacing_m, source_binding,
                          speed_m_s=1.0, minimum_length_m=30.0):
    """Route interval volumes once, never instantaneous accumulated discharge."""
    _positive(dt_s, "dt_s", 1e7)
    if set(inputs) != set(INPUT_KEYS):
        raise ValueError("invalid input keys")
    local = inputs["local_q_m3_s"]
    if (not isinstance(local, np.ndarray) or local.ndim != 2 or local.dtype != np.dtype("float64")
            or local.shape[1] != inputs["area_m2"].size
            or not np.isfinite(local).all() or (local < 0).any() or (local > 1e9).any()):
        raise ValueError("invalid local discharge")
    steps, hrus = local.shape
    preflight(steps, inputs["height_m"].size, hrus, 1)
    mapping = build_reaches(**{key: inputs[key] for key in INPUT_KEYS if key != "local_q_m3_s"},
                            spacing_m=spacing_m, speed_m_s=speed_m_s,
                            minimum_length_m=minimum_length_m)
    reaches = mapping["tau_s"].size
    preflight(steps, inputs["height_m"].size, hrus, reaches)
    if not isinstance(source_binding, dict) or not source_binding:
        raise ValueError("explicit source binding required")
    parameters = {"dt_s": float(dt_s), "spacing_m": float(spacing_m),
                  "speed_m_s": float(speed_m_s), "minimum_length_m": float(minimum_length_m)}
    result = {key: value.copy() for key, value in inputs.items()}
    result.update(mapping)
    result["metadata"] = dict(parameters, algorithm=ALGORITHM, schema=SCHEMA,
        source_binding=_strict_json(_json(source_binding)),
        input_hashes={key: _hash(inputs[key]) for key in INPUT_KEYS},
        parameter_sha256=hashlib.sha256(_json(parameters).encode("ascii")).hexdigest())
    fractions = mapping["allocation_counts"] * spacing_m ** 2 / inputs["area_m2"][None, :]
    result.update({key: np.zeros((steps, reaches), dtype=np.float64) for key in FLUX_KEYS})
    result["lateral_volume_m3"] = (local @ fractions.T) * dt_s
    result["storage_m3"] = np.zeros((steps + 1, reaches), dtype=np.float64)
    result["outlet_q_m3_s"] = np.zeros(steps, dtype=np.float64)
    for reach in mapping["reach_order"]:
        tau = mapping["tau_s"][reach]
        for step in range(steps):
            incoming = result["lateral_volume_m3"][step, reach] + result["upstream_volume_m3"][step, reach]
            before = result["storage_m3"][step, reach]
            after = (before + incoming) / (1 + dt_s / tau)
            released = dt_s / tau * after
            result["storage_m3"][step + 1, reach] = after
            result["outflow_volume_m3"][step, reach] = released
        target = mapping["reach_downstream"][reach]
        if target >= 0:
            result["upstream_volume_m3"][:, target] += result["outflow_volume_m3"][:, reach]
        else:
            result["outlet_q_m3_s"] += result["outflow_volume_m3"][:, reach] / dt_s
    result["storage_change_m3"] = np.diff(result["storage_m3"], axis=0)
    result["balance_residual_m3"] = (result["lateral_volume_m3"] + result["upstream_volume_m3"]
        - result["outflow_volume_m3"] - result["storage_change_m3"])
    validate_routing_result(result)
    return result


def _equal(actual, expected, name):
    if not np.allclose(actual, expected, rtol=2e-11, atol=1e-8):
        raise ValueError(f"saved equation mismatch: {name}")


def _validate_saved_map(result, meta):
    height = result["height_m"]
    shape = height.shape
    for key in ("receiver", "cell_owner", "flowline_mask", "outlet_mask", "river_reach", "cell_reach"):
        if result[key].shape != shape:
            raise ValueError("saved grid shape mismatch")
    receiver = result["receiver"].ravel()
    _order(receiver)
    outlets = result["outlet_mask"].ravel()
    if not np.array_equal(receiver == -1, outlets):
        raise ValueError("saved outlet mismatch")
    river = result["flowline_mask"].ravel() | outlets
    moving = np.flatnonzero(receiver >= 0)
    target = receiver[moving]
    width = shape[1]
    row_delta = np.abs(moving // width - target // width)
    col_delta = np.abs(moving % width - target % width)
    if ((row_delta > 1) | (col_delta > 1) | (row_delta + col_delta == 0)).any():
        raise ValueError("saved non-D8 receiver")
    if not river[receiver[river & ~outlets]].all():
        raise ValueError("saved river not closed")
    donors = np.bincount(receiver[river & ~outlets], minlength=height.size)
    starts = np.flatnonzero(river & ((donors != 1) | outlets))
    reaches = result["tau_s"].size
    if starts.size != reaches:
        raise ValueError("saved reach count mismatch")
    river_reach = result["river_reach"].ravel()
    cell_reach = result["cell_reach"].ravel()
    if ((river_reach[~river] != -1).any() or (river_reach[river] < 0).any()
            or (river_reach[river] >= reaches).any()
            or not np.array_equal(river_reach[starts], np.arange(reaches))
            or (cell_reach < 0).any() or (cell_reach >= reaches).any()
            or not np.array_equal(cell_reach[river], river_reach[river])
            or not np.array_equal(cell_reach[~river], cell_reach[receiver[~river]])):
        raise ValueError("saved first-downstream mapping mismatch")
    edges = np.flatnonzero(river & ~outlets)
    destinations = receiver[edges]
    boundaries = (donors[destinations] != 1) | outlets[destinations]
    if not np.array_equal(river_reach[edges[~boundaries]], river_reach[destinations[~boundaries]]):
        raise ValueError("saved maximal path ownership mismatch")
    ends = np.concatenate((edges[boundaries], np.flatnonzero(outlets)))
    if not np.array_equal(np.sort(river_reach[ends]), np.arange(reaches)):
        raise ValueError("saved reach endpoints mismatch")
    downstream = result["reach_downstream"]
    order = result["reach_order"]
    if (downstream.shape != (reaches,) or order.shape != (reaches,)
            or (downstream < -1).any() or (downstream >= reaches).any()
            or not np.array_equal(np.sort(order), np.arange(reaches))):
        raise ValueError("saved reach topology shape")
    endpoint_target = receiver[ends]
    expected_targets = np.full(reaches, -1, dtype=np.int64)
    valid = endpoint_target >= 0
    expected_targets[river_reach[ends[valid]]] = river_reach[endpoint_target[valid]]
    if not np.array_equal(downstream, expected_targets):
        raise ValueError("saved reach links mismatch")
    position = np.argsort(order)
    if (position[np.flatnonzero(downstream >= 0)] >= position[downstream[downstream >= 0]]).any():
        raise ValueError("saved order not topological")
    lengths = np.bincount(river_reach[edges], weights=meta["spacing_m"] * np.hypot(
        edges // width - destinations // width, edges % width - destinations % width), minlength=reaches)
    for key in ("reach_length_m", "tau_s"):
        if result[key].shape != (reaches,):
            raise ValueError("saved length shape")
    _equal(result["reach_length_m"], lengths, "original edge lengths")
    _equal(result["tau_s"], np.maximum(lengths, meta["minimum_length_m"]) / meta["speed_m_s"], "residence time")
    owner = result["cell_owner"].ravel()
    land = height.ravel() > 0
    area = result["area_m2"]
    hrus = result["local_q_m3_s"].shape[1]
    if (area.shape != (hrus,) or (area <= 0).any() or not land.any()
            or (owner[~land] != -1).any() or (owner[land] < 0).any() or (owner[land] >= hrus).any()):
        raise ValueError("saved HRU ownership")
    counts = np.bincount(cell_reach[land] * hrus + owner[land], minlength=reaches * hrus).reshape(reaches, hrus)
    if (not np.array_equal(counts, result["allocation_counts"])
            or not np.array_equal(counts.sum(axis=0) * meta["spacing_m"] ** 2, area)):
        raise ValueError("saved allocation count/area mismatch")


def validate_routing_result(result, *, trusted_inputs=None, source_binding=None):
    """Static vectorized equation replay, not prepare, runoff or time advancement."""
    if set(result) != set(ARRAY_KEYS) | {"metadata"}:
        raise ValueError("invalid result keys")
    meta = result["metadata"]
    if (not isinstance(meta, dict) or set(meta) != META_KEYS or meta["algorithm"] != ALGORITHM
            or meta["schema"] != SCHEMA or not isinstance(meta["source_binding"], dict)
            or not meta["source_binding"] or set(meta["input_hashes"]) != set(INPUT_KEYS)):
        raise ValueError("invalid metadata")
    for key in ("dt_s", "spacing_m", "speed_m_s", "minimum_length_m"):
        _positive(meta[key], key, {"dt_s": 1e7, "spacing_m": 1e5,
                                 "speed_m_s": 100, "minimum_length_m": 1e6}[key])
    parameter_hash = hashlib.sha256(_json({key: meta[key] for key in
        ("dt_s", "spacing_m", "speed_m_s", "minimum_length_m")}).encode("ascii")).hexdigest()
    if parameter_hash != meta["parameter_sha256"]:
        raise ValueError("parameter identity mismatch")
    if trusted_inputs is not None:
        if source_binding != meta["source_binding"] or set(trusted_inputs) != set(INPUT_KEYS):
            raise ValueError("trusted source binding mismatch")
        for key in INPUT_KEYS:
            if _hash(trusted_inputs[key]) != meta["input_hashes"][key]:
                raise ValueError("external input identity mismatch")
    for key in ARRAY_KEYS:
        value = result[key]
        dtype = "int64" if key in INT_KEYS else "bool" if key in BOOL_KEYS else "float64"
        if (not isinstance(value, np.ndarray) or value.dtype != np.dtype(dtype)
                or not np.isfinite(value).all()):
            raise ValueError(f"invalid typed array: {key}")
    local = result["local_q_m3_s"]
    if local.ndim != 2 or result["height_m"].ndim != 2 or result["tau_s"].ndim != 1:
        raise ValueError("invalid dimensions")
    steps, hrus = local.shape
    reaches = result["tau_s"].size
    preflight(steps, result["height_m"].size, hrus, reaches)
    for key in INPUT_KEYS:
        if _hash(result[key]) != meta["input_hashes"][key]:
            raise ValueError("input hash mismatch")
    _validate_saved_map(result, meta)
    for key in FLUX_KEYS + ("storage_m3", "outlet_q_m3_s"):
        shape = (steps + 1, reaches) if key == "storage_m3" else (steps,) if key == "outlet_q_m3_s" else (steps, reaches)
        if result[key].shape != shape:
            raise ValueError(f"invalid shape: {key}")
        if key not in ("storage_change_m3", "balance_residual_m3") and (result[key] < 0).any():
            raise ValueError(f"negative saved water: {key}")
    if (local < 0).any() or (local > 1e9).any() or hrus != result["area_m2"].size:
        raise ValueError("invalid local input")
    _equal(result["storage_m3"][0], 0.0, "initial zero storage")
    dt = meta["dt_s"]
    lateral = local @ (result["allocation_counts"] * meta["spacing_m"] ** 2 / result["area_m2"]).T * dt
    _equal(result["lateral_volume_m3"], lateral, "complete area allocation")
    upstream = np.zeros((steps, reaches), dtype=np.float64)
    for reach, target in enumerate(result["reach_downstream"]):
        if target >= 0:
            upstream[:, target] += result["outflow_volume_m3"][:, reach]
    _equal(result["upstream_volume_m3"], upstream, "upstream transfers")
    storage = result["storage_m3"]
    expected_after = (storage[:-1] + lateral + upstream) / (1 + dt / result["tau_s"])
    _equal(storage[1:], expected_after, "backward Euler storage")
    _equal(result["outflow_volume_m3"], storage[1:] * dt / result["tau_s"], "reservoir release")
    change = np.diff(storage, axis=0)
    _equal(result["storage_change_m3"], change, "storage ledger")
    residual = lateral + upstream - result["outflow_volume_m3"] - change
    _equal(result["balance_residual_m3"], residual, "reach residual ledger")
    outlet = result["outflow_volume_m3"][:, result["reach_downstream"] < 0].sum(axis=1)
    _equal(result["outlet_q_m3_s"], outlet / dt, "outlet")
    global_residual = local.sum(axis=1) * dt - outlet - change.sum(axis=1)
    _equal(global_residual, 0.0, "global interval volume")
    _equal(residual, 0.0, "reach interval volume")
    return {"max_reach_residual_m3": float(np.abs(residual).max()),
            "max_global_interval_residual_m3": float(np.abs(global_residual).max()),
            "global_residual_m3": float(local.sum() * dt - outlet.sum() - storage[-1].sum())}


def save_routing_npz(path, result):
    """Atomic same-filesystem hard-link publication, no overwrite even in a race."""
    validate_routing_result(result)
    manifest = {"metadata": result["metadata"], "hashes": {key: _hash(result[key]) for key in ARRAY_KEYS}}
    payload = _json(manifest).encode("utf-8")
    if len(payload) > 65536:
        raise ValueError("manifest exceeds budget")
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    descriptor, temporary = tempfile.mkstemp(prefix=".reach-", suffix=".npz", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            np.savez_compressed(stream, manifest=np.frombuffer(payload, dtype=np.uint8),
                                **{key: result[key] for key in ARRAY_KEYS})
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def load_routing_npz(path, *, trusted_inputs, source_binding):
    """Require external trusted input; hashes alone do not authenticate a forgery."""
    names = {key + ".npy" for key in ARRAY_KEYS} | {"manifest.npy"}
    with open(path, "rb") as stream:
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            if len(members) != len(names) or {member.filename for member in members} != names:
                raise ValueError("unexpected/duplicate archive members")
            if sum(member.file_size for member in members) > MAX_BYTES:
                raise ValueError("archive byte budget exceeded")
            shapes = {}
            for member in members:
                key = member.filename[:-4]
                with archive.open(member) as array_stream:
                    if np.lib.format.read_magic(array_stream) != (1, 0):
                        raise ValueError("unsupported NPY version")
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(array_stream, max_header_size=4096)
                    expected_dtype = "uint8" if key == "manifest" else "int64" if key in INT_KEYS else "bool" if key in BOOL_KEYS else "float64"
                    if (dtype != np.dtype(expected_dtype) or fortran or len(shape) not in (1, 2)
                            or any(size < 1 or size > MAX_CELLS for size in shape)
                            or math.prod(shape) * dtype.itemsize + array_stream.tell() != member.file_size):
                        raise ValueError("invalid typed NPY header/size")
                    if key == "manifest" and (len(shape) != 1 or shape[0] > 65536):
                        raise ValueError("invalid manifest header")
                    shapes[key] = shape
            if len(shapes["local_q_m3_s"]) != 2 or len(shapes["tau_s"]) != 1:
                raise ValueError("invalid preflight dimensions")
            steps, hrus = shapes["local_q_m3_s"]
            reaches = shapes["tau_s"][0]
            grid = shapes["height_m"]
            if len(grid) != 2:
                raise ValueError("invalid grid header")
            preflight(steps, math.prod(grid), hrus, reaches)
            grid_keys = {"height_m", "receiver", "cell_owner", "flowline_mask", "outlet_mask", "river_reach", "cell_reach"}
            for key in ARRAY_KEYS:
                if key in grid_keys:
                    expected_shape = grid
                elif key == "area_m2":
                    expected_shape = (hrus,)
                elif key == "local_q_m3_s":
                    expected_shape = (steps, hrus)
                elif key == "allocation_counts":
                    expected_shape = (reaches, hrus)
                elif key in FLUX_KEYS:
                    expected_shape = (steps, reaches)
                elif key == "storage_m3":
                    expected_shape = (steps + 1, reaches)
                elif key == "outlet_q_m3_s":
                    expected_shape = (steps,)
                else:
                    expected_shape = (reaches,)
                if shapes[key] != expected_shape:
                    raise ValueError(f"inconsistent header shape: {key}")
        stream.seek(0)
        with np.load(stream, allow_pickle=False) as archive:
            manifest = _strict_json(archive["manifest"].tobytes().decode("utf-8"))
            if set(manifest) != {"metadata", "hashes"} or set(manifest["hashes"]) != set(ARRAY_KEYS):
                raise ValueError("invalid manifest schema")
            result = {key: archive[key] for key in ARRAY_KEYS}
            result["metadata"] = manifest["metadata"]
            if any(_hash(result[key]) != manifest["hashes"][key] for key in ARRAY_KEYS):
                raise ValueError("array hash mismatch")
    validate_routing_result(result, trusted_inputs=trusted_inputs, source_binding=source_binding)
    return result
