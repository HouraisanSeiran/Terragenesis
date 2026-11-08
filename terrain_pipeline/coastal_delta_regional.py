"""Bounded regional construction calls on the existing integrated delta ledger.

All volumes are solid cubic metres; geological years are equivalent forcing
time, distinct from the physical seconds in MarineState.time_s.
"""
import math

from .coastal_delta_evolution import advance_years, load, save

SECONDS_PER_YEAR = 365.25 * 86400.0


def estimate_cost(*, shape, area_km2, mean_raise_m, porosity,
                  solid_rate_m3_s, years, array_count=20):
    """Estimate ideal solid demand, requested supply and array memory lower bound.

    The memory figure covers only the specified number of float64 grids, not
    sparse solvers, copies, Python objects, or the process baseline.
    """
    if (len(shape) != 2 or any(not isinstance(n, int) or isinstance(n, bool) or n <= 0 for n in shape)
            or not isinstance(array_count, int) or isinstance(array_count, bool) or array_count <= 0):
        raise ValueError('invalid grid size')
    values = (area_km2, mean_raise_m, porosity, solid_rate_m3_s, years)
    if (not all(math.isfinite(v) for v in values) or area_km2 <= 0 or mean_raise_m < 0
            or not 0 <= porosity < 1 or solid_rate_m3_s < 0 or years <= 0):
        raise ValueError('invalid budget assumptions')
    demand = area_km2 * 1e6 * mean_raise_m * (1 - porosity)
    supply = solid_rate_m3_s * years * SECONDS_PER_YEAR
    return {'ideal_demand_solid_m3': demand, 'requested_supply_solid_m3': supply,
            'supply_to_demand': supply / demand if demand else None,
            'float64_grid_bytes_lower_bound': shape[0] * shape[1] * 8 * array_count,
            'array_count': array_count}


def advance_interval(state, progress, years, *, source_identity, input_id,
                     hydraulic_config, marine_config, **kwargs):
    """Advance at most one equivalent year with the existing physical feedback.

    Callers save each returned state before further work. No elapsed-time limit
    is implied: run a small probe before scheduling a larger grid.
    """
    if (not isinstance(source_identity, str) or not source_identity.strip()
            or state.source_identity != source_identity
            or progress.get('integrated', {}).get('source_identity') != source_identity):
        raise ValueError('source identity mismatch')
    if not isinstance(input_id, str) or not input_id.strip():
        raise ValueError('input ID required')
    if not math.isfinite(years) or not 0 < years <= 1:
        raise ValueError('interval must be positive and at most one year')
    return advance_years(state, progress, years, input_id=input_id,
                         hydraulic_config=hydraulic_config, marine_config=marine_config,
                         **kwargs)


__all__ = ['advance_interval', 'estimate_cost', 'load', 'save']
