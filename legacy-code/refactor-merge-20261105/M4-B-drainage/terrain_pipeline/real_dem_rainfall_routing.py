"""Batched independent runoff and one-edge-per-step linear reservoir routing.

Resident global graph/storage, not Saint-Venant, backwater or natural outlets.
Infiltration/percolation are internal transfers, not system water losses.
"""

from dataclasses import asdict
import math

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, canonical_json, digest
from terrain_pipeline.rainfall_runoff import RunoffParameters, simulate_rainfall_runoff
from terrain_pipeline.real_dem_flat_routing import validate_flat_routing
from terrain_pipeline.real_dem_tiled_network import _arrays, candidate_mesh


ALGORITHM = "real-dem-irregular-metric-delayed-linear-storage-v2"
MAX_BYTES = 512 * 1024 * 1024
MAX_STEPS = 96
MAX_ENTRIES = 24_000_000
RUNOFF_KEYS = ("rain_volume_m3", "et_volume_m3", "local_runoff_m3", "soil_change_m3",
               "fast_change_m3", "slow_change_m3", "runoff_residual_m3")
ROUTING_KEYS = ("channel_storage_change_m3", "engineering_discharge_m3", "verified_external_m3",
                "unknown_retained_m3", "internal_retained_m3", "whole_system_residual_m3")
ARRAY_KEYS = {"valid_cell_ids", "rain_mm_h", "local_volume", "channel_storage",
              "final_soil_mm", "final_fast_mm", "final_slow_mm"}


def _scalar(value, name, minimum, maximum):
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating))
            or not math.isfinite(value) or not minimum <= value <= maximum):
        raise ValueError(f"invalid finite {name} range")
    return float(value)


def _flat_digest(flat_result):
    network = flat_result["network"]
    return digest({"arrays": {name: array_hash(getattr(network, name)) for name in
                              ("receiver", "order", "accumulation_cells", "boundary_outlet", "unknown_adjacent_terminal")},
                   "component_id": array_hash(flat_result["component_id"]),
                   "distance_to_exit": array_hash(flat_result["distance_to_exit"]),
                   "components": flat_result["components"], "summary": flat_result["summary"]})


def _inputs(candidate, flat_result, rain, dt_s, parameters, batch_cells, speed, engineering):
    height, valid = _arrays(candidate)
    if type(batch_cells) is not int or batch_cells <= 0:
        raise ValueError("batch_cells must be a positive integer, not bool")
    dt_s = _scalar(dt_s, "dt_s", 1e-6, 1e7)
    speed = _scalar(speed, "speed_m_s", 1e-9, 1e6)
    if parameters is None:
        parameters = RunoffParameters()
    if not isinstance(parameters, RunoffParameters):
        raise ValueError("parameters must be RunoffParameters")
    parameters.__post_init__()
    ids = np.flatnonzero(valid.ravel())
    if (not isinstance(rain, np.ndarray) or rain.ndim not in (1, 2) or rain.dtype.kind not in "fiu"
            or (rain.ndim == 2 and rain.shape[1] != len(ids))):
        raise ValueError("rain_mm_h requires numeric [T] or [T,N] valid-ID order")
    steps = rain.shape[0]
    if not 1 <= steps <= MAX_STEPS or steps * len(ids) > MAX_ENTRIES:
        raise ValueError("rainfall graph/step entry budget exceeded")
    retained_bytes = 8 * ((2 * steps + 5) * len(ids) + rain.size + (len(RUNOFF_KEYS) + len(ROUTING_KEYS)) * steps)
    if retained_bytes > MAX_BYTES:
        raise ValueError("rainfall retained array budget exceeds 512MiB")
    if not np.isfinite(rain).all() or np.any(rain < 0) or np.any(rain > 1e6):
        raise ValueError("rain must be finite nonnegative <= 1e6 mm/h")
    validate_flat_routing(candidate, flat_result)
    if "manifest" in candidate:
        grid = candidate["manifest"]["identity"]["grid"]
    else:
        grid = candidate.get("grid")
    if (not isinstance(grid, dict) or "spacing_x_m" not in grid or "spacing_z_m" not in grid
            or ("manifest" not in candidate and (grid.get("crs") != "EPSG:32651" or grid.get("units") != "metres"))):
        raise ValueError("explicit metric grid spacing_x_m/spacing_z_m required; no implicit 90m")
    spacing_x, spacing_z = grid["spacing_x_m"], grid["spacing_z_m"]
    spacing_x = _scalar(spacing_x, "spacing_x_m", 1e-6, 1e6)
    spacing_z = _scalar(spacing_z, "spacing_z_m", 1e-6, 1e6)
    if not isinstance(engineering, (tuple, list)):
        raise ValueError("engineering_terminal_ids must be explicit list/tuple")
    if any(type(cell) is not int or cell < 0 or cell >= height.size for cell in engineering) or len(set(engineering)) != len(engineering):
        raise ValueError("invalid or duplicate engineering terminal IDs")
    receiver = flat_result["network"].receiver.ravel()
    component = flat_result["component_id"].ravel()
    records = {record["component_id"]: record for record in flat_result["components"]}
    for cell in engineering:
        if not valid.ravel()[cell] or receiver[cell] != -1:
            raise ValueError("engineering discharge requires valid terminal")
        record = records[int(component[cell])]
        if (record["touches_unknown"] or not record["touches_boundary"]
                or record["classification"] != "closed_flat_retention" or record["root_cell_id"] != cell):
            raise ValueError("engineering discharge requires closed boundary component without unknown risk")
    mapping = np.full(height.size, -1, np.int64)
    mapping[ids] = np.arange(len(ids))
    global_targets = receiver[ids]
    local_targets = np.full(len(ids), -1, np.int64)
    routed = global_targets >= 0
    local_targets[routed] = mapping[global_targets[routed]]
    mesh = candidate_mesh(candidate)
    lengths = np.full(len(ids), spacing_x)
    lengths[routed] = np.hypot(mesh.node_x_m[ids[routed]] - mesh.node_x_m[global_targets[routed]],
                               mesh.node_z_m[ids[routed]] - mesh.node_z_m[global_targets[routed]])
    fraction = -np.expm1(-dt_s * speed / lengths)
    external = np.isin(ids, np.asarray(engineering, np.int64))
    fraction[~routed & ~external] = 0.
    terminal_unknown = np.array([records[int(component[cell])]["touches_unknown"] for cell in ids], bool) & ~routed
    internal = ~routed & ~terminal_unknown & ~external
    metadata = {"algorithm": ALGORITHM, "runoff_algorithm": "rainfall-runoff-v1", "dt_s": dt_s,
                "parameters": asdict(parameters), "parameter_sha256": digest(asdict(parameters)),
                "speed_m_s": speed, "batch_cells": batch_cells,
                "effective_batch_cells": min(batch_cells, 100000, 1000000 // steps),
                "spacing_x_m": spacing_x, "spacing_z_m": spacing_z, "projected_crs": "EPSG:32651", "spacing_units": "metres",
                "engineering_terminal_ids": sorted(engineering), "cell_order": "ascending_valid_global_cell_id",
                "candidate_height_sha256": array_hash(height), "valid_mask_sha256": array_hash(valid),
                "candidate_content_sha256": candidate.get("manifest", {}).get("content_sha256"),
                "flat_result_sha256": _flat_digest(flat_result), "rain_sha256": array_hash(rain),
                "rain_shape": list(rain.shape), "retained_array_budget_bytes": retained_bytes,
                "model": "one_way_linear_reservoir_not_Saint_Venant_no_backwater",
                "release": "old_storage*(-expm1(-dt_s/(edge_length_m/speed_m_s)))",
                "length_coordinates": "absolute_world_irregular_graph_nodes",
                "terminal_release_length": "declared_native_spacing_x_for_explicit_engineering_terminal",
                "arrival": "local_and_upstream_release_stored_until_next_step",
                "engineering_assumption": "explicit_closed_boundary_terminal_no_unknown_component",
                "global_graph_state": True, "natural_outlet_verified": False, "ocean_outlet_certified": False}
    return ids, local_targets, fraction, external, terminal_unknown, internal, parameters, metadata


def _runoff(rain, ids, metadata, parameters, local=None, finals=None):
    steps, cells = rain.shape[0], len(ids)
    ledger = {key: np.zeros(steps) for key in RUNOFF_KEYS}
    area = metadata["spacing_x_m"] * metadata["spacing_z_m"]
    for start in range(0, cells, metadata["effective_batch_cells"]):
        stop = min(cells, start + metadata["effective_batch_cells"])
        batch_rain = np.broadcast_to(rain[:, None], (steps, stop - start)) if rain.ndim == 1 else rain[:, start:stop]
        batch = simulate_rainfall_runoff(batch_rain, np.full(stop - start, area), dt_s=metadata["dt_s"],
                                         source_id="real-dem-valid-global-id-batch", parameters=parameters)
        volume = batch["outflow_volume_m3"]
        if local is not None:
            _equal(local[:, start:stop], volume, "local runoff batch equations")
        else:
            yield start, stop, volume, {key: batch[key][-1].copy() for key in ("soil_mm", "fast_mm", "slow_mm")}
        for output, field in (("rain_volume_m3", "rain_volume_m3"), ("et_volume_m3", "et_volume_m3"),
                              ("local_runoff_m3", "outflow_volume_m3"), ("runoff_residual_m3", "balance_residual_m3")):
            ledger[output] += batch[field].sum(axis=1)
        for name in ("soil", "fast", "slow"):
            ledger[name + "_change_m3"] += (np.diff(batch[name + "_mm"], axis=0) * (area / 1000.)).sum(axis=1)
            if finals is not None:
                _equal(finals["final_" + name + "_mm"][start:stop], batch[name + "_mm"][-1], name + " final runoff state")
        del batch
    yield ledger


def _equal(actual, expected, label):
    if not np.allclose(actual, expected, rtol=1e-10, atol=1e-8):
        raise ValueError(f"rainfall equation/ledger mismatch: {label}")


def _routing_ledger(storage, local, targets, fraction, external, unknown, internal, runoff):
    steps, cells = local.shape
    ledger = {key: np.zeros(steps) for key in ROUTING_KEYS}
    routed = targets >= 0
    for step in range(steps):
        release = storage[step] * fraction
        incoming = np.bincount(targets[routed], weights=release[routed], minlength=cells)
        expected = storage[step] - release + incoming + local[step]
        _equal(storage[step + 1], expected, "channel storage one-edge delayed propagation")
        ledger["channel_storage_change_m3"][step] = (storage[step + 1] - storage[step]).sum()
        ledger["engineering_discharge_m3"][step] = release[external].sum()
        ledger["unknown_retained_m3"][step] = storage[step + 1, unknown].sum()
        ledger["internal_retained_m3"][step] = storage[step + 1, internal].sum()
    ledger["whole_system_residual_m3"] = (runoff["rain_volume_m3"] - runoff["et_volume_m3"]
        - runoff["soil_change_m3"] - runoff["fast_change_m3"] - runoff["slow_change_m3"]
        - ledger["channel_storage_change_m3"] - ledger["engineering_discharge_m3"])
    scale = runoff["rain_volume_m3"] + runoff["et_volume_m3"] + np.abs(ledger["channel_storage_change_m3"])
    if np.any(abs(ledger["whole_system_residual_m3"]) > 1e-7 + 1e-10 * scale):
        raise ValueError("whole system water balance failed")
    return ledger


def _summary(result):
    ledger = result["ledger"]
    return {"steps": result["local_volume"].shape[0], "valid_cells": len(result["valid_cell_ids"]),
            "rain_volume_m3": float(ledger["rain_volume_m3"].sum()),
            "local_runoff_m3": float(ledger["local_runoff_m3"].sum()),
            "et_volume_m3": float(ledger["et_volume_m3"].sum()),
            "engineering_discharge_m3": float(ledger["engineering_discharge_m3"].sum()),
            "verified_external_m3": 0., "final_channel_storage_m3": float(result["channel_storage"][-1].sum()),
            "max_abs_whole_system_residual_m3": float(abs(ledger["whole_system_residual_m3"]).max()),
            "retained_array_nbytes": sum(result[key].nbytes for key in ARRAY_KEYS) + sum(value.nbytes for value in ledger.values()),
            "retention_semantics": "unknown/internal_retained are end-step inventories, not repeated losses",
            "memory_scope": "retained arrays only; candidate/flat graph/runoff batch/temporaries excluded",
            "natural_outlet_verified": False, "ocean_outlet_certified": False}


def simulate_dem_rainfall(candidate, flat_result, rain_mm_h, *, dt_s, parameters=None,
                          batch_cells=100000, speed_m_s=1.0, engineering_terminal_ids=()) -> dict:
    ids, targets, fraction, external, unknown, internal, parameters, metadata = _inputs(
        candidate, flat_result, rain_mm_h, dt_s, parameters, batch_cells, speed_m_s, engineering_terminal_ids)
    rain = rain_mm_h.astype(np.float64, copy=True)
    metadata["rain_sha256"] = array_hash(rain)
    steps, cells = rain.shape[0], len(ids)
    local = np.zeros((steps, cells))
    result = {"valid_cell_ids": ids, "rain_mm_h": rain, "local_volume": local,
              "channel_storage": np.zeros((steps + 1, cells)), "metadata": metadata,
              **{"final_" + name + "_mm": np.zeros(cells) for name in ("soil", "fast", "slow")}}
    for item in _runoff(rain, ids, metadata, parameters):
        if isinstance(item, dict):
            runoff = item
        else:
            start, stop, volume, final = item
            local[:, start:stop] = volume
            for name in ("soil", "fast", "slow"):
                result["final_" + name + "_mm"][start:stop] = final[name + "_mm"]
    storage = result["channel_storage"]
    routed = targets >= 0
    for step in range(steps):
        release = storage[step] * fraction
        storage[step + 1] = storage[step] - release + local[step]
        storage[step + 1] += np.bincount(targets[routed], weights=release[routed], minlength=cells)
    result["ledger"] = {**runoff, **_routing_ledger(storage, local, targets, fraction, external, unknown, internal, runoff)}
    result["summary"] = _summary(result)
    return result


def validate_dem_rainfall(candidate, flat_result, result) -> dict:
    """Replay bounded runoff batches, then audit saved propagation equations."""
    if not isinstance(result, dict) or set(result) != ARRAY_KEYS | {"metadata", "ledger", "summary"}:
        raise ValueError("invalid rainfall result schema")
    metadata = result["metadata"]
    try:
        parameters = RunoffParameters(**metadata["parameters"])
        ids, targets, fraction, external, unknown, internal, parameters, expected_metadata = _inputs(
            candidate, flat_result, result["rain_mm_h"], metadata["dt_s"], parameters,
            metadata["batch_cells"], metadata["speed_m_s"], metadata["engineering_terminal_ids"])
    except (KeyError, TypeError) as error:
        raise ValueError("invalid rainfall metadata") from error
    if canonical_json(metadata) != canonical_json(expected_metadata):
        raise ValueError("rainfall source/parameter/rain/risk binding mismatch")
    if not np.array_equal(result["valid_cell_ids"], ids) or result["valid_cell_ids"].dtype != np.dtype(np.int64):
        raise ValueError("valid ID order mismatch")
    steps, cells = result["rain_mm_h"].shape[0], len(ids)
    for key in ARRAY_KEYS - {"valid_cell_ids"}:
        values = result[key]
        shape = (steps, cells) if key == "local_volume" else (steps + 1, cells) if key == "channel_storage" else (cells,)
        if key == "rain_mm_h":
            shape = tuple(metadata["rain_shape"])
        if (not isinstance(values, np.ndarray) or values.dtype != np.dtype(np.float64) or values.shape != shape
                or not np.isfinite(values).all() or np.any(values < 0)):
            raise ValueError(f"invalid rainfall array {key}")
    if np.any(result["channel_storage"][0] != 0):
        raise ValueError("initial channel storage must be zero")
    for runoff in _runoff(result["rain_mm_h"], ids, metadata, parameters, local=result["local_volume"], finals=result):
        pass
    expected_ledger = {**runoff, **_routing_ledger(result["channel_storage"], result["local_volume"], targets,
                                                 fraction, external, unknown, internal, runoff)}
    if set(result["ledger"]) != set(expected_ledger):
        raise ValueError("invalid rainfall ledger keys")
    for key, expected in expected_ledger.items():
        values = result["ledger"][key]
        if (not isinstance(values, np.ndarray) or values.dtype != np.dtype(np.float64)
                or values.shape != (steps,) or not np.isfinite(values).all()):
            raise ValueError("invalid ledger array")
        _equal(values, expected, key)
    if canonical_json(result["summary"]) != canonical_json(_summary(result)):
        raise ValueError("rainfall summary mismatch")
    return {"verified": True, "summary": dict(result["summary"]), "verified_external_m3": 0.,
            "natural_outlet_verified": False, "ocean_outlet_certified": False}
