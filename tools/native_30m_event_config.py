"""Validate declared event inputs for the existing soil-bucket implementation."""
from dataclasses import asdict, fields
import math
import numpy as np
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters


def event_configuration(rain_mm_h=None, runoff_parameters=None):
    from tools.native_30m_sources import STORM
    if rain_mm_h is None:
        rain_mm_h = STORM
    if isinstance(rain_mm_h, np.ndarray):
        if rain_mm_h.dtype != np.float64 or rain_mm_h.shape != (72,):
            raise ValueError('declared_storm_shape_dtype')
        rain = rain_mm_h.copy()
    else:
        if (not isinstance(rain_mm_h, (list, tuple)) or len(rain_mm_h) != 72 or
                any(type(v) not in (int, float) for v in rain_mm_h)):
            raise ValueError('declared_storm_requires_72_rates')
        rain = np.array(rain_mm_h, np.float64)
    if not np.isfinite(rain).all() or np.any(rain < 0):
        raise ValueError('declared_storm_finite_nonnegative')
    defaults = RunoffParameters(infiltration_capacity_mm_h=2.0)
    if runoff_parameters is None:
        parameters = defaults
    elif isinstance(runoff_parameters, RunoffParameters):
        parameters = runoff_parameters
    else:
        if not isinstance(runoff_parameters, dict) or not set(runoff_parameters).issubset({f.name for f in fields(defaults)}):
            raise ValueError('runoff_parameter_fields')
        merged = asdict(defaults)
        merged.update(runoff_parameters)
        parameters = RunoffParameters(**merged)
    if parameters.initial_soil_mm > parameters.soil_capacity_mm:
        raise ValueError('initial_soil_exceeds_soil_capacity')
    return rain, parameters


def uses_custom_event(parameters):
    from tools.native_30m_sources import STORM
    return ('runoff_parameters' in parameters or parameters['storm_rain_mm_h'] != STORM or
            parameters['infiltration_capacity_mm_h'] != 2.)
