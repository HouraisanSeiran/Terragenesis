"""Bounded column batching for native-grid independent-cell hydrology."""

import numpy as np

from terrain_pipeline.rainfall_runoff import (
    ARRAY_KEYS, MAX_BYTES as SMALL_MAX_BYTES, MAX_CELLS as SMALL_MAX_CELLS,
    MAX_ENTRIES as SMALL_MAX_ENTRIES, STATE_KEYS, STEP_KEYS, RunoffParameters,
    simulate_rainfall_runoff, validate_rainfall_runoff_result,
)
from terrain_pipeline.surface_rivers.metric_contracts import RainfallForcing, TerrainGrid
from terrain_pipeline.surface_rivers.metric_runoff import LEDGER_KEYS, _output_state_indices


MAX_LARGE_CELLS = 1024 * 1024
MAX_LARGE_STEPS = 3
MAX_LARGE_BYTES = 1024 * 1024 * 1024


def _batch_size(steps, requested):
    limit = min(SMALL_MAX_CELLS, SMALL_MAX_ENTRIES // steps,
                SMALL_MAX_BYTES // (24 * 8 * (steps + 1)))
    if requested is None:
        return limit
    if type(requested) is not int or not 1 <= requested <= limit:
        raise ValueError("chunk_size exceeds fixed-dt solver budget")
    return requested


def _large_budget(steps, cells, grid_cells, sampled_states, batch_size):
    if not 1 <= steps <= MAX_LARGE_STEPS or not 1 <= cells <= grid_cells <= MAX_LARGE_CELLS:
        raise ValueError("large runoff cells/steps budget exceeded")
    native_bytes = 8 * cells * (len(STEP_KEYS) * steps + len(STATE_KEYS) * (steps + 1) + 1)
    chunk_bytes = 8 * min(cells, batch_size) * (len(STEP_KEYS) * steps + len(STATE_KEYS) * (steps + 1) + 1)
    estimated_peak = (native_bytes + 8 * grid_cells * (steps + 2)
                      + 8 * cells * (len(STATE_KEYS) * sampled_states + 1)
                      + 2 * chunk_bytes)
    if estimated_peak > MAX_LARGE_BYTES:
        raise ValueError("large runoff estimated memory budget exceeded")


def validate_large_rainfall_runoff_result(native, *, chunk_size=None):
    """Validate a full native result with the frozen validator in bounded columns."""
    if not isinstance(native, dict) or set(native) != set(ARRAY_KEYS) | {"metadata"}:
        raise ValueError("unexpected large native result keys")
    rain = native["rain_mm_h"]
    if not isinstance(rain, np.ndarray) or rain.ndim != 2:
        raise ValueError("invalid large native rain shape")
    steps, cells = rain.shape
    batch_size = _batch_size(steps, chunk_size) if steps > 0 else 0
    _large_budget(steps, cells, cells, 0, batch_size)
    for key in ARRAY_KEYS:
        expected = (cells,) if key == "area_m2" else (
            (steps + 1, cells) if key in STATE_KEYS else (steps, cells))
        value = native[key]
        if not isinstance(value, np.ndarray) or value.dtype != np.float64 or value.shape != expected:
            raise ValueError("invalid large native shape/dtype: " + key)
    maximum_residual = 0.
    for start in range(0, cells, batch_size):
        stop = min(start + batch_size, cells)
        subset = {key: (native[key][start:stop] if key == "area_m2"
                        else native[key][:, start:stop]) for key in ARRAY_KEYS}
        subset["metadata"] = native["metadata"]
        report = validate_rainfall_runoff_result(subset)
        maximum_residual = max(maximum_residual, report["max_abs_balance_residual_m3"])
    return {"valid": True, "max_abs_balance_residual_m3": maximum_residual}


def runoff_from_forcing_large(terrain, forcing, *, parameters=None,
                              output_indices=None, chunk_size=None):
    """Return the regular adapter shape while solving bounded valid-cell batches."""
    if not isinstance(terrain, TerrainGrid) or not isinstance(forcing, RainfallForcing):
        raise ValueError("TerrainGrid and RainfallForcing required")
    if parameters is not None and not isinstance(parameters, RunoffParameters):
        raise ValueError("parameters must be RunoffParameters")
    if forcing.rain_mm_h.shape[1:] != terrain.valid_mask.shape:
        raise ValueError("forcing grid shape must match terrain")
    if np.any(forcing.rain_mm_h[:, ~terrain.valid_mask] != 0.):
        raise ValueError("rain on invalid terrain cells is unsupported")
    intervals = forcing.interval_seconds
    if np.any(intervals != intervals[0]):
        raise ValueError("uniform forcing intervals required by fixed-dt solver")
    indices = _output_state_indices(output_indices, intervals.size)
    batch_size = _batch_size(intervals.size, chunk_size)
    cell_ids = np.flatnonzero(terrain.valid_mask).astype(np.int64)
    steps, cells = intervals.size, cell_ids.size
    _large_budget(steps, cells, terrain.elevation_m.size, indices.size, batch_size)
    native = {key: np.empty((steps, cells), dtype=np.float64) for key in STEP_KEYS}
    native.update({key: np.empty((steps + 1, cells), dtype=np.float64) for key in STATE_KEYS})
    native["area_m2"] = np.empty(cells, dtype=np.float64)
    flattened_rain = forcing.rain_mm_h.reshape(steps, -1)
    for start in range(0, cells, batch_size):
        stop = min(start + batch_size, cells)
        batch_rain = flattened_rain[:, cell_ids[start:stop]]
        batch_area = np.full(stop - start, terrain.cell_area_m2, dtype=np.float64)
        batch = simulate_rainfall_runoff(batch_rain, batch_area, dt_s=float(intervals[0]),
                                        source_id=forcing.source_id, parameters=parameters)
        for key in ARRAY_KEYS:
            if key == "area_m2":
                native[key][start:stop] = batch[key]
            else:
                native[key][:, start:stop] = batch[key]
        if start == 0:
            native["metadata"] = batch["metadata"]
        del batch
    with np.errstate(over="ignore", invalid="ignore"):
        per_step = {key: np.sum(native[key], axis=1, dtype=np.float64) for key in LEDGER_KEYS}
        totals = {key: float(np.sum(values, dtype=np.float64)) for key, values in per_step.items()}
    if any(not np.isfinite(values).all() for values in per_step.values()) or any(
            not np.isfinite(value) for value in totals.values()):
        raise ValueError("runoff ledger overflow: finite totals required")
    output_times = forcing.time_seconds[indices].copy()
    return {
        "native_result": native,
        "valid_cell_ids": cell_ids,
        "state_time_seconds": forcing.time_seconds.copy(),
        "output_time_seconds": output_times,
        "output_state_indices": indices,
        "output_states_mm": {key: native[key][indices].copy() for key in STATE_KEYS},
        "ledger": per_step | {"totals_m3": totals},
        "metadata": {
            "terrain_identity_sha256": terrain.identity_sha256,
            "forcing_identity_sha256": forcing.identity_sha256,
            "dt_solver_seconds": float(intervals[0]),
            "solver_role": "independent_cell_hydrology_no_channel_hydraulics",
            "dt_output_seconds": np.diff(output_times),
            "q_semantics": "interval_average_local_release_not_river_routed",
            "state_semantics": "end_of_interval", "status": "diagnostic_runoff",
            "hydraulic_ready": False, "natural_outlet_verified": False,
            "publishable": False,
        },
    }
