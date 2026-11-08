"""Compensated floating-point updates for the unchanged ordered runoff forcing."""

import numpy as np
from terrain_pipeline.rainfall_runoff import _release


def add(values, increment, compensation):
    exhausted = (increment < 0) & (increment == -values)
    adjusted = increment - compensation
    updated = values + adjusted
    updated[exhausted] = 0
    compensation[:] = (updated - values) - adjusted
    compensation[exhausted] = 0
    if np.any(updated < 0) or not np.isfinite(updated).all():
        raise ValueError("negative/nonfinite compensated inventory; clamp forbidden")
    values[:] = updated


def reset_transport_compensation(errors):
    errors["depth"][:] = 0


def reset_hourly_ledger_compensation(errors, keys):
    for key in keys:
        errors[key][:] = 0


def forcing(depth, soil, fast, slow, rain_rate, sub_dt, runoff, config, area, ledgers, step, errors):
    hours = sub_dt / 3600
    rainfall = rain_rate * hours
    wet = depth > config["wet_threshold_m"]
    lake_rain = np.where(wet, rainfall, 0)
    land_rain = rainfall - lake_rain
    infiltration = np.minimum(np.minimum(land_rain, runoff.infiltration_capacity_mm_h * hours),
                              np.maximum(0, runoff.soil_capacity_mm - soil))
    add(soil, infiltration, errors["soil"])
    soil_et = np.minimum(soil, runoff.potential_et_mm_h * hours)
    add(soil, -soil_et, errors["soil"])
    percolation = np.minimum(soil, runoff.percolation_mm_h * hours)
    add(soil, -percolation, errors["soil"])
    unused_fast, fast_release = _release(fast, land_rain - infiltration, sub_dt, runoff.fast_tau_s)
    unused_slow, slow_release = _release(slow, percolation, sub_dt, runoff.slow_tau_s)
    add(fast, land_rain - infiltration - fast_release, errors["fast"])
    add(slow, percolation - slow_release, errors["slow"])
    release = fast_release + slow_release
    add(depth, (lake_rain + release) / 1000, errors["depth"])
    surface_et = np.minimum(depth, config["surface_evaporation_mm_h"] * hours / 1000)
    add(depth, -surface_et, errors["depth"])
    for key, values in (("rain_volume_m3", rainfall), ("lake_rain_m3", lake_rain), ("land_rain_m3", land_rain),
                        ("soil_et_m3", soil_et), ("local_release_m3", release)):
        add(ledgers[key][step], values * area / 1000, errors[key])
    add(ledgers["surface_et_m3"][step], surface_et * area, errors["surface_et_m3"])
    return depth, soil, fast, slow
