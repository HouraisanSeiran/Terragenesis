"""Experimental unified rain/surface infiltration, without a wet-bypass branch."""

import numpy as np

from terrain_pipeline.td_basin_storage_compiled import _add, _release
from numba import njit


PROFILE = "v10-unified-rain-surface-infiltration-experimental-v1"


@njit(cache=True)
def advance_forcing(states, errors, rain_mm_h, seconds, subdivisions, runoff, evaporation_mm_h):
    ledger = np.zeros((8, states.shape[1]))
    compensation = np.zeros_like(ledger)
    hours = seconds / 3600
    for substep in range(subdivisions):
        for cell in range(states.shape[1]):
            rainfall = rain_mm_h[cell] * hours
            capacity = min(runoff[0] * hours, max(0., runoff[1] - states[1, cell]))
            rain_infiltration = min(rainfall, capacity)
            surface_infiltration = min(states[0, cell] * 1000, capacity - rain_infiltration)
            infiltration = rain_infiltration + surface_infiltration
            surface_decrement = -states[0, cell] if surface_infiltration == states[0, cell]*1000 else -surface_infiltration/1000
            states[0, cell], errors[0, cell] = _add(states[0, cell], surface_decrement, errors[0, cell])
            states[1, cell], errors[1, cell] = _add(states[1, cell], infiltration, errors[1, cell])
            soil_et = min(states[1, cell], runoff[2] * hours)
            states[1, cell], errors[1, cell] = _add(states[1, cell], -soil_et, errors[1, cell])
            percolation = min(states[1, cell], runoff[3] * hours)
            states[1, cell], errors[1, cell] = _add(states[1, cell], -percolation, errors[1, cell])
            excess = rainfall - rain_infiltration
            fast_release = _release(states[2, cell], excess, seconds, runoff[4])
            slow_release = _release(states[3, cell], percolation, seconds, runoff[5])
            states[2, cell], errors[2, cell] = _add(states[2, cell], excess - fast_release, errors[2, cell])
            states[3, cell], errors[3, cell] = _add(states[3, cell], percolation - slow_release, errors[3, cell])
            release = fast_release + slow_release
            states[0, cell], errors[0, cell] = _add(states[0, cell], release / 1000, errors[0, cell])
            surface_et = min(states[0, cell], evaporation_mm_h * hours / 1000)
            states[0, cell], errors[0, cell] = _add(states[0, cell], -surface_et, errors[0, cell])
            increments = (rainfall, rain_infiltration, surface_infiltration, excess,
                          soil_et, surface_et * 1000, release, percolation)
            for index in range(8):
                ledger[index, cell], compensation[index, cell] = _add(
                    ledger[index, cell], increments[index], compensation[index, cell])
    return states, errors, ledger


def simulate_forcing(states, rain_mm_h, *, duration_s=3600., substep_s=1.25,
                     runoff=None, evaporation_mm_h=.15):
    initial = np.asarray(states, dtype=np.float64)
    rain = np.asarray(rain_mm_h, dtype=np.float64)
    parameters = np.array([15., 150., .15, 1., 3600., 259200.]) if runoff is None else np.asarray(runoff, dtype=np.float64)
    scalars = np.array([duration_s, substep_s, evaporation_mm_h])
    if (initial.ndim != 2 or initial.shape[0] != 4 or not 1 <= initial.shape[1] <= 1000
            or rain.shape != (initial.shape[1],) or parameters.shape != (6,)
            or not np.isfinite(initial).all() or not np.isfinite(rain).all()
            or not np.isfinite(parameters).all() or not np.isfinite(scalars).all()
            or np.any(initial < 0) or np.any(rain < 0) or np.any(parameters < 0)
            or np.any(parameters[4:] <= 0) or np.any(initial[1] > parameters[1])
            or duration_s <= 0 or substep_s <= 0 or evaporation_mm_h < 0):
        raise ValueError("invalid bounded v10 forcing inputs")
    count = int(np.ceil(duration_s / substep_s))
    if count > 100000 or count * initial.shape[1] > 10000000:
        raise ValueError("v10 forcing experiment budget exceeded")
    result = advance_forcing(initial.copy(), np.zeros_like(initial), rain,
                             duration_s / count, count, parameters, evaporation_mm_h)
    before = initial[0] * 1000 + initial[1:].sum(axis=0)
    after = result[0][0] * 1000 + result[0][1:].sum(axis=0)
    residual = after - before - result[2][0] + result[2][4] + result[2][5]
    if np.any(np.abs(residual) > 1e-9):
        raise ValueError("v10 forcing water budget failed")
    return {"states": result[0], "errors": result[1], "ledger_mm": result[2],
            "balance_residual_mm": residual, "profile": PROFILE,
            "ledger_order": ["rain", "rain_infiltration", "surface_infiltration", "rain_excess",
                             "soil_et", "surface_et", "release", "percolation"],
            "semantics": "rain has first access to finite infiltration capacity; remaining capacity draws available surface water; rain excess enters unchanged fast store; ordered soil ET/percolation retained",
            "hydraulic_ready": False, "publishable": False}
