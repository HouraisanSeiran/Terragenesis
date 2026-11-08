"""Physical-time adapter for independent-cell runoff and boundary proposals."""

import numpy as np

from terrain_pipeline.rainfall_runoff import RunoffParameters, simulate_rainfall_runoff
from terrain_pipeline.common_infra import BoundaryGrid, RainfallForcing, TerrainGrid


LEDGER_KEYS = ("rain_volume_m3", "et_volume_m3", "outflow_volume_m3",
               "storage_change_m3", "balance_residual_m3")
STATE_KEYS = ("soil_mm", "fast_mm", "slow_mm")


def _output_state_indices(output_indices, steps):
    if output_indices is None:
        return np.arange(steps + 1, dtype=np.int64)
    if not isinstance(output_indices, (list, tuple, np.ndarray)):
        raise ValueError("output_indices must be increasing end-state indices")
    indices = np.asarray(output_indices)
    if indices.ndim != 1 or indices.dtype.kind not in "iu" or indices.size == 0:
        raise ValueError("output_indices must be nonempty integer end-state indices")
    if np.any(indices < 1) or np.any(indices > steps) or np.any(indices[1:] <= indices[:-1]):
        raise ValueError("output_indices must be strictly increasing in 1..T")
    return indices.astype(np.int64, copy=True)


def runoff_from_forcing(terrain, forcing, *, parameters=None, output_indices=None):
    """Run every forcing interval; optionally sample state frames after solving."""
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
    cell_ids = np.flatnonzero(terrain.valid_mask).astype(np.int64)
    rain = forcing.rain_mm_h.reshape(intervals.size, -1)[:, cell_ids]
    area = np.full(cell_ids.size, terrain.cell_area_m2, dtype=np.float64)
    native = simulate_rainfall_runoff(rain, area, dt_s=float(intervals[0]),
                                     source_id=forcing.source_id, parameters=parameters)
    with np.errstate(over="ignore", invalid="ignore"):
        per_step = {key: np.sum(native[key], axis=1, dtype=np.float64) for key in LEDGER_KEYS}
        totals = {key: float(np.sum(values, dtype=np.float64))
                  for key, values in per_step.items()}
    if any(not np.isfinite(values).all() for values in per_step.values()) or any(
            not np.isfinite(value) for value in totals.values()):
        raise ValueError("runoff ledger overflow: finite totals required")
    ledger = per_step | {"totals_m3": totals}
    output_times = forcing.time_seconds[indices].copy()
    return {
        "native_result": native,
        "valid_cell_ids": cell_ids,
        "state_time_seconds": forcing.time_seconds.copy(),
        "output_time_seconds": output_times,
        "output_state_indices": indices,
        "output_states_mm": {key: native[key][indices].copy() for key in STATE_KEYS},
        "ledger": ledger,
        "metadata": {
            "terrain_identity_sha256": terrain.identity_sha256,
            "forcing_identity_sha256": forcing.identity_sha256,
            "dt_solver_seconds": float(intervals[0]),
            "solver_role": "independent_cell_hydrology_no_channel_hydraulics",
            "dt_output_seconds": np.diff(output_times),
            "q_semantics": "interval_average_local_release_not_river_routed",
            "state_semantics": "end_of_interval",
            "status": "diagnostic_runoff",
            "hydraulic_ready": False,
            "natural_outlet_verified": False,
            "publishable": False,
        },
    }


def boundary_flux(boundary, proposed_q_m3_s):
    """Apply outward-positive boundary conditions to proposed cell fluxes.

    This filters proposals only; it does not solve for a physical boundary flux.
    """
    if not isinstance(boundary, BoundaryGrid):
        raise ValueError("BoundaryGrid required")
    proposal = np.asarray(proposed_q_m3_s)
    if (proposal.shape != boundary.kind.shape or proposal.dtype.kind not in "fiu"
            or not np.isfinite(proposal).all()):
        raise ValueError("finite numeric proposed_q_m3_s matching boundary shape required")
    if np.any((boundary.kind == "unknown_boundary") & (proposal != 0.)):
        raise ValueError("nonzero flux on unknown boundary is unresolved")
    result = np.zeros(boundary.kind.shape, dtype=np.float64)
    open_mask = boundary.kind == "open_outflow"
    result[open_mask] = np.maximum(proposal[open_mask], 0.)
    stage_mask = boundary.kind == "prescribed_stage"
    result[stage_mask] = np.where(boundary.allow_inflow[stage_mask], proposal[stage_mask],
                                  np.maximum(proposal[stage_mask], 0.))
    discharge_mask = boundary.kind == "prescribed_discharge"
    if boundary.discharge_m3_s is not None:
        result[discharge_mask] = boundary.discharge_m3_s[discharge_mask]
    return result
