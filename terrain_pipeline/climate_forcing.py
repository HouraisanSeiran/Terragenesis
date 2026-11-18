"""Consolidated climate_forcing implementations; numeric expressions preserved."""
from __future__ import annotations
from dataclasses import asdict as _i20_asdict
from dataclasses import dataclass as _i20_dataclass
import math as _i20_math
import numpy as _i20_np
from diffusion.geographic_noise import field as _i20_field
from dataclasses import asdict as _i16_asdict
from dataclasses import dataclass as _i16_dataclass
import math as _i16_math
import numpy as _i16_np
import hashlib as _i15_hashlib
import importlib as _i15_importlib
import math as _i15_math
import os as _i15_os
import time as _i15_time
import numpy as _i15_np
from dataclasses import asdict as _i17_asdict
from dataclasses import dataclass as _i17_dataclass
import math as _i17_math
import numpy as _i17_np
from scipy.special import erf as _i17_erf
from dataclasses import asdict as _i18_asdict
import io as _i18_io
import json as _i18_json
import os as _i18_os
import tempfile as _i18_tempfile
from pathlib import Path as _i18_Path
import numpy as _i18_np
import hashlib as _i19_hashlib
import math as _i19_math
import numpy as _i19_np
import numpy as _i21_np
from dataclasses import asdict as _i22_asdict
from dataclasses import dataclass as _i22_dataclass
import hashlib as _i22_hashlib
import json as _i22_json
import math as _i22_math
import numpy as _i22_np
from diffusion.geographic_noise import field as _i22_field
from dataclasses import asdict as _i23_asdict
import math as _i23_math
import re as _i23_re
import numpy as _i23_np
import numpy as _i24_np
from dataclasses import asdict as _i25_asdict
import json as _i25_json
import os as _i25_os
from pathlib import Path as _i25_Path
import time as _i25_time
import numpy as _i25_np
from numba import njit as _i25_njit
from scipy.ndimage import map_coordinates as _i25_map_coordinates
CATEGORY = 'D'
MONTH_DAYS = _i20_np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], _i20_np.float64)
MONTH_EDGES_S = _i20_np.r_[0.0, _i20_np.cumsum(MONTH_DAYS) * 86400.0]
YEAR_S = float(MONTH_EDGES_S[-1])
MONTH_CENTERS_S = 0.5 * (MONTH_EDGES_S[:-1] + MONTH_EDGES_S[1:])

@_i20_dataclass(frozen=True)
class NoiseStormParameters:
    """One bounded candidate pulse per absolute spatial cell and daily slot."""
    cell_spacing_m: float = 48000.0
    max_radius_m: float = 22000.0
    slot_seconds: float = 86400.0
    min_duration_s: float = 21600.0
    max_duration_s: float = 43200.0
    max_intensity_mm_h: float = 18.0
    occurrence_probability: float = 0.4

    def __post_init__(self):
        values = _i20_asdict(self)
        if any((type(v) not in (int, float) or not _i20_math.isfinite(v) for v in values.values())):
            raise ValueError('finite storm parameters required')
        if self.cell_spacing_m <= 0.0 or not 0.0 < self.max_radius_m <= self.cell_spacing_m or (not 0.0 < self.min_duration_s <= self.max_duration_s <= self.slot_seconds) or (self.max_intensity_mm_h < 0.0) or (not 0.0 <= self.occurrence_probability <= 1.0):
            raise ValueError('bounded storm support and positive physical scales required')

    @property
    def identity_sha256(self):
        from terrain_pipeline.common_infra import identity as _i20_identity
        return _i20_identity({}, {'schema': 'metric-bounded-storm-v1', 'parameters': _i20_asdict(self)})

def _storm_random(seed, cell_x, cell_z, slot, stream):
    with _i20_np.errstate(over='ignore'):
        value = _i20_np.asarray(cell_x, _i20_np.int64).astype(_i20_np.uint64) * _i20_np.uint64(11400714785074694791) ^ _i20_np.asarray(cell_z, _i20_np.int64).astype(_i20_np.uint64) * _i20_np.uint64(14029467366897019727) ^ _i20_np.uint64(seed) ^ _i20_np.uint64(slot) * _i20_np.uint64(1609587929392839161) ^ _i20_np.uint64(stream) * _i20_np.uint64(9650029242287828579)
        value = (value ^ value >> _i20_np.uint64(30)) * _i20_np.uint64(13787848793156543929)
        value = (value ^ value >> _i20_np.uint64(27)) * _i20_np.uint64(10723151780598845931)
        value ^= value >> _i20_np.uint64(31)
    return (value >> _i20_np.uint64(11)).astype(_i20_np.float64) / float(2 ** 53)

def _triangle_integral(fraction):
    value = _i20_np.clip(fraction, 0.0, 1.0)
    return _i20_np.where(value <= 0.5, value ** 2, 0.5 - (1.0 - value) ** 2)

def interval_seasonal_storm_rain_mm(seed, x_m, z_m, start_s, end_s, *, monthly_precipitation_mm=None, storm_parameters=None):
    """Integrated depths for a periodic climate baseline plus compact storms.

    Monthly precipitation is converted to mm/s at month centers and linearly
    interpolated, including across the year boundary, and scaled by their
    analytic annual integral to preserve the supplied annual climate target.
    Storms use a fixed world lattice, compact radial support and triangular
    time pulses; their added rain is not part of that target. Neither field is
    normalized to request bounds. At most 32 storm slots per call.
    """
    x, z = _coordinates(seed, x_m, z_m)
    parameters = NoiseStormParameters() if storm_parameters is None else storm_parameters
    if not isinstance(parameters, NoiseStormParameters):
        raise ValueError('StormParameters required')
    if not all((type(v) in (int, float) and _i20_math.isfinite(v) for v in (start_s, end_s))) or not 0.0 <= start_s < end_s <= 1000000000000.0 or end_s / parameters.slot_seconds >= 2 ** 63 or (_i20_math.ceil(end_s / parameters.slot_seconds) - _i20_math.floor(start_s / parameters.slot_seconds) > 32):
        raise ValueError('bounded positive absolute weather interval required')
    precipitation = sample_climate(seed, x, z)['monthly_precipitation_mm'] if monthly_precipitation_mm is None else _i20_np.asarray(monthly_precipitation_mm, _i20_np.float64)
    if precipitation.shape != (12, *x.shape) or not _i20_np.isfinite(precipitation).all() or _i20_np.any(precipitation < 0.0):
        raise ValueError('12 finite nonnegative monthly precipitation grids required')
    with _i20_np.errstate(over='ignore'):
        annual_target = precipitation.sum(axis=0)
    if not _i20_np.isfinite(annual_target).all():
        raise ValueError('finite annual precipitation target required')
    rates = precipitation / (MONTH_DAYS * 86400.0).reshape((12,) + (1,) * x.ndim)
    center_gaps = _i20_np.diff(_i20_np.r_[MONTH_CENTERS_S, MONTH_CENTERS_S[0] + YEAR_S])
    annual_weights = 0.5 * (center_gaps + _i20_np.roll(center_gaps, 1))
    annual_integral = _i20_np.sum(rates * annual_weights.reshape((12,) + (1,) * x.ndim), axis=0)
    normalization = _i20_np.divide(annual_target, annual_integral, out=_i20_np.zeros(x.shape), where=annual_integral > 0.0)
    rates *= normalization
    baseline = _i20_np.zeros(x.shape, _i20_np.float64)
    lower = float(start_s)
    while lower < end_s:
        year = _i20_math.floor(lower / YEAR_S)
        position = lower - year * YEAR_S
        index = int(_i20_np.searchsorted(MONTH_CENTERS_S, position, side='right')) - 1
        if index < 0:
            first_time = (year - 1) * YEAR_S + MONTH_CENTERS_S[-1]
            last_time = year * YEAR_S + MONTH_CENTERS_S[0]
        elif index == 11:
            first_time = year * YEAR_S + MONTH_CENTERS_S[-1]
            last_time = (year + 1) * YEAR_S + MONTH_CENTERS_S[0]
        else:
            first_time = year * YEAR_S + MONTH_CENTERS_S[index]
            last_time = year * YEAR_S + MONTH_CENTERS_S[index + 1]
        upper = min(float(end_s), last_time)
        average_fraction = (0.5 * (lower + upper) - first_time) / (last_time - first_time)
        baseline += (rates[index % 12] + average_fraction * (rates[(index + 1) % 12] - rates[index % 12])) * (upper - lower)
        lower = upper
    storm = _i20_np.zeros(x.shape, _i20_np.float64)
    if parameters.occurrence_probability == 0.0 or parameters.max_intensity_mm_h == 0.0:
        return dict(seasonal_depth_mm=baseline, storm_depth_mm=storm, total_depth_mm=baseline.copy())
    base_x = _i20_np.floor(x / parameters.cell_spacing_m).astype(_i20_np.int64)
    base_z = _i20_np.floor(z / parameters.cell_spacing_m).astype(_i20_np.int64)
    for slot in range(_i20_math.floor(start_s / parameters.slot_seconds), _i20_math.ceil(end_s / parameters.slot_seconds)):
        for dz in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cell_x, cell_z = (base_x + dx, base_z + dz)
                active = _storm_random(seed, cell_x, cell_z, slot, 1) < parameters.occurrence_probability
                center_x = (cell_x + _storm_random(seed, cell_x, cell_z, slot, 2)) * parameters.cell_spacing_m
                center_z = (cell_z + _storm_random(seed, cell_x, cell_z, slot, 3)) * parameters.cell_spacing_m
                radius = parameters.max_radius_m * (0.5 + 0.5 * _storm_random(seed, cell_x, cell_z, slot, 4))
                radial = _i20_np.maximum(0.0, 1.0 - ((x - center_x) ** 2 + (z - center_z) ** 2) / radius ** 2) ** 2
                duration = parameters.min_duration_s + (parameters.max_duration_s - parameters.min_duration_s) * _storm_random(seed, cell_x, cell_z, slot, 5)
                pulse_start = slot * parameters.slot_seconds + (parameters.slot_seconds - duration) * _storm_random(seed, cell_x, cell_z, slot, 6)
                integral_s = duration * (_triangle_integral((end_s - pulse_start) / duration) - _triangle_integral((start_s - pulse_start) / duration))
                intensity = parameters.max_intensity_mm_h * (0.35 + 0.65 * _storm_random(seed, cell_x, cell_z, slot, 7))
                storm += active * radial * intensity * integral_s / 3600.0
    return dict(seasonal_depth_mm=baseline, storm_depth_mm=storm, total_depth_mm=baseline + storm)

@_i20_dataclass(frozen=True)
class NoiseClimateParameters:
    climate_scale_m: float = 240000.0
    regional_scale_m: float = 60000.0
    lapse_rate_c_per_m: float = -0.0065
    weather_scale_m: float = 12000.0
    weather_detail_scale_m: float = 3000.0
    velocity_x_m_s: float = 8.0
    velocity_z_m_s: float = 2.0
    absolute_weather_step_s: float = 900.0

    def __post_init__(self):
        values = _i20_asdict(self)
        if any((type(value) not in (int, float) or not _i20_math.isfinite(value) for value in values.values())):
            raise ValueError('finite physical noise climate parameters required')
        if any((values[name] <= 0.0 for name in ('climate_scale_m', 'regional_scale_m', 'weather_scale_m', 'weather_detail_scale_m', 'absolute_weather_step_s'))):
            raise ValueError('positive meter scales and physical time step required')
        if not -0.012 <= self.lapse_rate_c_per_m <= 0.0:
            raise ValueError('lapse rate must be -0.012..0 Celsius per meter')

    @property
    def identity_sha256(self):
        from terrain_pipeline.common_infra import identity as _i20_identity
        return _i20_identity({}, {'schema': 'metric-noise-climate-v1', 'parameters': _i20_asdict(self)})

def _coordinates(seed, x_m, z_m):
    if type(seed) is not int or not 0 <= seed < 2 ** 64:
        raise ValueError('uint64 world seed required')
    x, z = _i20_np.broadcast_arrays(_i20_np.asarray(x_m, _i20_np.float64), _i20_np.asarray(z_m, _i20_np.float64))
    if not 1 <= x.size <= 1048576 or not _i20_np.isfinite(x).all() or (not _i20_np.isfinite(z).all()) or (max(float(_i20_np.max(_i20_np.abs(x))), float(_i20_np.max(_i20_np.abs(z)))) > 1000000000000.0):
        raise ValueError('bounded finite absolute meter coordinates required')
    return (x, z)

def sample_climate(seed, x_m, z_m, elevation_m=0.0, *, parameters=None):
    """Generate monthly Celsius/mm, then derive BIO1/4/12/15 from those months."""
    parameters = parameters or NoiseClimateParameters()
    x, z = _coordinates(seed, x_m, z_m)
    elevation = _i20_np.broadcast_to(_i20_np.asarray(elevation_m, _i20_np.float64), x.shape)
    if not _i20_np.isfinite(elevation).all():
        raise ValueError('finite physical elevation required')
    scales = ((parameters.climate_scale_m, 1.0), (parameters.regional_scale_m, 0.25))
    thermal = 0.5 * (1.0 + _i20_field(x, z, seed, 1401, scales))
    moisture = 0.5 * (1.0 + _i20_field(x, z, seed, 1503, scales))
    continentality = 0.8 * (1.0 - moisture) + 0.2 * 0.5 * (1.0 + _i20_field(x, z, seed, 1607, scales))
    annual_temperature = -8.0 + 38.0 * thermal + parameters.lapse_rate_c_per_m * _i20_np.maximum(elevation, 0.0)
    temperature_amplitude = (2.0 + 20.0 * continentality) * (1.0 - 0.45 * thermal)
    annual_precipitation = 120.0 + 3000.0 * moisture ** 2 * (0.65 + 0.35 * thermal)
    rain_seasonality = 0.4 + 1.8 * (1.0 - moisture) * thermal
    phase = _i20_np.pi * _i20_field(x, z, seed, 1709, scales)
    month_shape = (12,) + (1,) * x.ndim
    angles = (_i20_np.arange(12) * (2.0 * _i20_np.pi / 12.0)).reshape(month_shape)
    seasonal_cycle = _i20_np.cos(angles - phase)
    temperature = annual_temperature + temperature_amplitude * seasonal_cycle
    weights = _i20_np.exp(rain_seasonality * seasonal_cycle)
    precipitation = annual_precipitation * weights / _i20_np.sum(weights, axis=0)
    bioclim = _i20_np.stack((_i20_np.mean(temperature, axis=0), _i20_np.std(temperature, axis=0) * 100.0, _i20_np.sum(precipitation, axis=0), _i20_np.std(precipitation, axis=0) / _i20_np.mean(precipitation, axis=0) * 100.0))
    return {'monthly_temperature_c': temperature, 'monthly_precipitation_mm': precipitation, 'BIO1_4_12_15': bioclim, 'thermal_strength': thermal, 'moisture_strength': moisture, 'continentality_strength': continentality, 'parameter_identity_sha256': parameters.identity_sha256, 'semantics': 'synthetic_monthly_climate_targets_not_measured_weather'}

def _weather_node(seed, x, z, time_s, parameters):
    weather = _i20_field(x - parameters.velocity_x_m_s * time_s, z - parameters.velocity_z_m_s * time_s, seed, 1801, ((parameters.weather_scale_m, 1.0), (parameters.weather_detail_scale_m, 0.3)))
    return 1.0 + 0.95 * weather

def interval_mean_rain_mm_h(seed, x_m, z_m, start_s, end_s, *, parameters=None):
    """Integrate fixed absolute-time linear weather nodes and monthly climate rates."""
    parameters = parameters or NoiseClimateParameters()
    x, z = _coordinates(seed, x_m, z_m)
    if not all((type(value) in (int, float) and _i20_math.isfinite(value) for value in (start_s, end_s))) or not 0 <= start_s < end_s:
        raise ValueError('finite positive physical time interval required')
    step = parameters.absolute_weather_step_s
    if (end_s - start_s) / step > 4096.0:
        raise ValueError('rain interval exceeds fixed integration work budget')
    climate = sample_climate(seed, x, z, parameters=parameters)
    precipitation = climate['monthly_precipitation_mm']
    volume_mm = _i20_np.zeros(x.shape, _i20_np.float64)
    lower = float(start_s)
    while lower < end_s:
        year = _i20_math.floor(lower / YEAR_S)
        in_year = lower - year * YEAR_S
        month = min(11, int(_i20_np.searchsorted(MONTH_EDGES_S, in_year, side='right') - 1))
        node = _i20_math.floor(lower / step)
        node_start = node * step
        upper = min(float(end_s), (node + 1) * step, year * YEAR_S + MONTH_EDGES_S[month + 1])
        first = _weather_node(seed, x, z, node_start, parameters)
        last = _weather_node(seed, x, z, node_start + step, parameters)
        fraction0, fraction1 = ((lower - node_start) / step, (upper - node_start) / step)
        average = first + 0.5 * (fraction0 + fraction1) * (last - first)
        monthly_rate_mm_h = precipitation[month] / (MONTH_DAYS[month] * 24.0)
        volume_mm += monthly_rate_mm_h * average * ((upper - lower) / 3600.0)
        lower = upper
    return volume_mm * 3600.0 / (end_s - start_s)

def grid_rainfall(seed, *, origin_xz_m, shape_zx, spacing_m, time_edges_s, parameters=None, spatial_subsamples=2):
    """Equal-area midpoint subcells provide an explicit numerical cell-average."""
    from terrain_pipeline.common_infra import RainfallForcing as _i20_RainfallForcing
    from terrain_pipeline.common_infra import identity as _i20_identity
    parameters = parameters or NoiseClimateParameters()
    edges = _i20_np.asarray(time_edges_s, _i20_np.float64)
    if edges.ndim != 1 or edges.size < 2 or (not _i20_np.isfinite(edges).all()) or _i20_np.any(_i20_np.diff(edges) <= 0.0) or (edges[0] < 0.0):
        raise ValueError('increasing finite physical time edges required')
    if spatial_subsamples not in (1, 2, 4) or len(shape_zx) != 2 or any((type(side) is not int or side <= 0 for side in shape_zx)):
        raise ValueError('positive grid shape and 1/2/4 midpoint subdivisions required')
    if type(spacing_m) not in (int, float) or not _i20_math.isfinite(spacing_m) or spacing_m <= 0.0:
        raise ValueError('positive physical grid spacing required')
    if _i20_np.prod(shape_zx) * (edges.size - 1) * spatial_subsamples ** 2 > 50000000:
        raise ValueError('noise rainfall resource dimensions exceeded')
    rows, columns = _i20_np.indices(shape_zx)
    offsets = (_i20_np.arange(spatial_subsamples) + 0.5) / spatial_subsamples - 0.5
    intensity = _i20_np.zeros((edges.size - 1,) + tuple(shape_zx), _i20_np.float64)
    for delta_z in offsets:
        for delta_x in offsets:
            x = origin_xz_m[0] + (columns + delta_x) * spacing_m
            z = origin_xz_m[1] + (rows + delta_z) * spacing_m
            for index, (start, end) in enumerate(zip(edges, edges[1:])):
                intensity[index] += interval_mean_rain_mm_h(seed, x, z, float(start), float(end), parameters=parameters) / spatial_subsamples ** 2
    metadata = {'schema': 'metric-noise-rainfall-v1', 'seed': seed, 'origin_xz_m': list(origin_xz_m), 'shape_zx': list(shape_zx), 'spacing_m': float(spacing_m), 'time_edges_s': edges.tolist(), 'parameters': _i20_asdict(parameters), 'parameter_identity_sha256': parameters.identity_sha256, 'spatial_mean': 'equal_area_midpoint_subcells', 'spatial_subsamples': spatial_subsamples, 'cell_boundary_convention': 'origin_is_center;subcells_cover_center_plus_minus_half_spacing', 'absolute_weather_step_s': parameters.absolute_weather_step_s, 'monthly_target_is_not_realized_annual_forcing': True}
    metadata['source_identity_sha256'] = _i20_identity({}, metadata)
    forcing = _i20_RainfallForcing(edges, intensity, 'synthetic_noise_climate', metadata['source_identity_sha256'])
    return (forcing, metadata)
CLIMATE_SCHEMA = 'metric-noise-climate-v2'
RAINFALL_SCHEMA = 'metric-noise-rainfall-v2'
REFINED_SEMANTICS = 'synthetic_monthly_climate_targets_not_measured_weather; orographic_and_normalized_band_modifiers'
BAND_STRUCTURE_SEMANTICS = 'synthetic band structure, not a measured climatology'
LATITUDE_PERIOD_M = 1920000.0
WIND_TRADE_BAND_LIMIT = 0.3
WIND_POLAR_BAND_LIMIT = 0.7
WIND_BAND_UNITS = ((-1, 0), (1, 0), (-1, 0))
WIND_BAND_NAMES = ('equator_side_trades_east_to_west', 'mid_latitude_westerlies_west_to_east', 'pole_side_trades_east_to_west')
DEFAULT_OROGRAPHIC_SCALE_M = 15000.0
DEFAULT_LATITUDE_TEMPERATURE_RANGE_C = -12.0
DEFAULT_LATITUDE_PRECIPITATION_GAIN = 0.0
SNOW_LINE_SCHEMA = 'metric-noise-snow-line-v2'
SNOW_LINE_CRITERION = 'monthly_mean_temperature_below_zero_celsius'

def _refined_wind_band_index(norm):
    """Finite band index from the normalized band coordinate; the only bearing rule."""
    magnitude = _i16_np.abs(norm)
    return _i16_np.where(magnitude < WIND_TRADE_BAND_LIMIT, 0, _i16_np.where(magnitude < WIND_POLAR_BAND_LIMIT, 1, 2))

def latitude_norm(seed, z_m, period_m=LATITUDE_PERIOD_M):
    """§3.1 normalized climate band `sin(2*pi*z_m/period_m)` in [-1, +1].

    `+1` is the pole side, `-1` is the equator side (artificial convention). Only
    `z_m` matters, so bands are east-west, periodically repeat and are window free.
    The seed is validated for contract consistency but does not enter the value: the
    band coordinate is a pure function of `z_m`. Scalars and arrays are accepted; a
    0-d result is returned as a Python float. The name carries `norm` on purpose:
    this is not a real latitude and is never converted to degrees.
    """
    if type(seed) is not int or not 0 <= seed < 2 ** 64:
        raise ValueError('uint64 world seed required')
    if type(period_m) not in (int, float) or not _i16_math.isfinite(period_m) or period_m <= 0.0:
        raise ValueError('positive finite latitude period required')
    z = _i16_np.asarray(z_m, _i16_np.float64)
    if not _i16_np.isfinite(z).all():
        raise ValueError('finite absolute metre coordinates required')
    phase = _i16_np.remainder(z / float(period_m), 1.0)
    value = _i16_np.sin(2.0 * _i16_np.pi * phase)
    return float(value) if _i16_np.ndim(value) == 0 else value

def wind_unit(latitude_norm_value):
    """§4.1 prevailing bearing `(wx, wz)` from the normalized band coordinate only.

    Returned components are exactly `0` or `+-1` and the pair is a unit vector; the
    set of reachable values is finite, so all places on one band share one bearing.
    """
    try:
        value = float(latitude_norm_value)
    except (TypeError, ValueError):
        raise ValueError('finite scalar latitude band norm required')
    if not _i16_math.isfinite(value) or not -1.0 <= value <= 1.0:
        raise ValueError('finite latitude band norm in [-1, 1] required')
    return WIND_BAND_UNITS[int(_refined_wind_band_index(value))]

def _wind_unit_arrays(norm):
    """Array form of `wind_unit`, sharing the single band rule and the single table."""
    units = _i16_np.asarray(WIND_BAND_UNITS, _i16_np.int64)
    index = _refined_wind_band_index(norm)
    return (units[index, 0], units[index, 1])

@_i16_dataclass(frozen=True)
class RefinedClimateParameters:
    """v1 base scales plus the v2 refinement parameters; both enter the identity."""
    base: NoiseClimateParameters = NoiseClimateParameters()
    latitude_period_m: float = LATITUDE_PERIOD_M
    latitude_temperature_range_c: float = DEFAULT_LATITUDE_TEMPERATURE_RANGE_C
    latitude_precipitation_gain: float = DEFAULT_LATITUDE_PRECIPITATION_GAIN
    orographic_scale_m: float = DEFAULT_OROGRAPHIC_SCALE_M
    ridge_smoothing_taps: int = 3
    windward_gain_m: float = 5.0
    lee_loss_m: float = 5.0
    max_windward_gain: float = 1.0
    min_lee_retention: float = 0.35
    annual_precipitation_min_mm: float = 100.0
    annual_precipitation_max_mm: float = 3200.0

    def __post_init__(self):
        if not isinstance(self.base, NoiseClimateParameters):
            raise ValueError('v1 NoiseClimateParameters base layer required')
        scalars = {name: getattr(self, name) for name in ('latitude_period_m', 'latitude_temperature_range_c', 'latitude_precipitation_gain', 'orographic_scale_m', 'windward_gain_m', 'lee_loss_m', 'max_windward_gain', 'min_lee_retention', 'annual_precipitation_min_mm', 'annual_precipitation_max_mm')}
        if any((type(value) not in (int, float) or not _i16_math.isfinite(value) for value in scalars.values())):
            raise ValueError('finite refinement parameters required')
        if type(self.ridge_smoothing_taps) is not int or not 1 <= self.ridge_smoothing_taps <= 9 or self.ridge_smoothing_taps % 2 == 0:
            raise ValueError('odd ridge smoothing tap count in 1..9 required')
        if self.latitude_period_m <= 0.0:
            raise ValueError('positive latitude period required')
        if not -60.0 <= self.latitude_temperature_range_c <= 60.0:
            raise ValueError('latitude temperature range must be within +-60 Celsius')
        if not 0.0 <= self.latitude_precipitation_gain <= 1.0:
            raise ValueError('latitude precipitation gain must be in [0, 1]')
        if self.orographic_scale_m <= 0.0:
            raise ValueError('positive orographic scale required')
        if self.windward_gain_m < 0.0 or self.lee_loss_m < 0.0:
            raise ValueError('nonnegative windward gain and lee loss required')
        if self.max_windward_gain < 0.0:
            raise ValueError('nonnegative windward gain ceiling required')
        if not 0.0 < self.min_lee_retention <= 1.0:
            raise ValueError('lee retention must be in (0, 1]')
        if not 0.0 < self.annual_precipitation_min_mm < self.annual_precipitation_max_mm:
            raise ValueError('increasing positive precipitation bounds required')

    @property
    def identity_sha256(self):
        from terrain_pipeline.common_infra import identity as _i16_identity
        return _i16_identity({}, {'schema': CLIMATE_SCHEMA, 'parameters': _i16_asdict(self)})

    @property
    def base_parameter_identity_sha256(self):
        """The reused v1 identity, reported as-is and never disguised as the v2 one."""
        return self.base.identity_sha256

    @property
    def wind_bearing_bands(self):
        """Bearing-band definition, reported so a drift is visible in every output."""
        return {'equator_side_below_norm': WIND_TRADE_BAND_LIMIT, 'pole_side_at_or_above_norm': WIND_POLAR_BAND_LIMIT, 'units': [list(unit) for unit in WIND_BAND_UNITS], 'names': list(WIND_BAND_NAMES), 'semantics': BAND_STRUCTURE_SEMANTICS}

    @property
    def ridge_offsets_m(self):
        """Odd tap offsets of the ridge smoother; a pure function of the parameters."""
        taps = self.ridge_smoothing_taps
        step = 0.0 if taps == 1 else self.orographic_scale_m / (taps - 1)
        return tuple((_i16_np.arange(taps) - (taps - 1) / 2.0) * step)

def _resolve_elevation_sampler(seed, elevation_sampler):
    """Default sampler = the height component of `coarse_condition_field` (§4.3)."""
    from terrain_pipeline.hydrology_planning import coarse_condition_field as _i16_coarse_condition_field
    if elevation_sampler is None:

        def elevation_sampler(x_m, z_m):
            return _i16_coarse_condition_field(seed, x_m, z_m)[0]
    elif not callable(elevation_sampler):
        raise ValueError('callable pure elevation sampler required')
    return elevation_sampler

def _sample_elevation(sampler, x_m, z_m):
    height = _i16_np.asarray(sampler(x_m, z_m), _i16_np.float64)
    try:
        return _i16_np.asarray(_i16_np.broadcast_to(height, _i16_np.broadcast(_i16_np.asarray(x_m), _i16_np.asarray(z_m)).shape), _i16_np.float64)
    except ValueError:
        raise ValueError('elevation sampler heights must broadcast to the query shape')

def _canonical_query(seed, x_m, z_m):
    """Flatten the query to a 1-D array query of at least two points.

    Why: the base layer is evaluated on arrays, and two numpy paths are not bit-equal at a
    single point. `diffusion.geographic_noise.field` takes a different arithmetic path for
    0-d input, and `np.sum(weights, axis=0)` reduces a length-1 free axis pairwise instead
    of sequentially. Measured consequence in v1 itself: the same world point queried alone
    (scalar or length-1) differs from the same point queried inside any array query by at
    most one unit in the last place. Flattening to 1-D and duplicating a single point onto
    the array path makes every v2 output a function of the world point alone, so no query
    window, shape, rank or call order can move a bit (§7.2).

    Returns `(flat_x, flat_z, shape, duplicated)`.
    """
    x, z = _coordinates(seed, x_m, z_m)
    shape = x.shape
    flat_x = _i16_np.ascontiguousarray(x.reshape(-1))
    flat_z = _i16_np.ascontiguousarray(z.reshape(-1))
    if flat_x.size == 1:
        return (_i16_np.ascontiguousarray(_i16_np.repeat(flat_x, 2)), _i16_np.ascontiguousarray(_i16_np.repeat(flat_z, 2)), shape, True)
    return (flat_x, flat_z, shape, False)

def _restore(value, shape, duplicated, dtype=_i16_np.float64):
    """Return a canonical-query result in the caller's own shape."""
    array = _i16_np.asarray(value, dtype).reshape(-1)
    if duplicated:
        array = array[:1]
    return array.reshape(shape)

def _restore_months(value, shape, duplicated):
    """Return a (k, ...) canonical-query result in the caller's own shape."""
    array = _i16_np.asarray(value, _i16_np.float64).reshape((_i16_np.shape(value)[0], -1))
    if duplicated:
        array = array[:, :1]
    return array.reshape((array.shape[0],) + shape)

def ridge_height(seed, x_m, z_m, *, parameters=None, elevation_sampler=None):
    """§4.2 smoothed terrain ridge (scale = `orographic_scale_m`), pure in (seed, x, z).

    The smoother is a finite odd-tap box over offsets `ridge_offsets_m`; it reads only
    the sampler at absolute world coordinates, so no query window, array shape or call
    order can influence a value. No cache and no state are kept.
    """
    parameters = parameters or RefinedClimateParameters()
    if not isinstance(parameters, RefinedClimateParameters):
        raise ValueError('RefinedClimateParameters required')
    sampler = _resolve_elevation_sampler(seed, elevation_sampler)
    flat_x, flat_z, shape, duplicated = _canonical_query(seed, x_m, z_m)
    offsets = parameters.ridge_offsets_m
    total = _i16_np.zeros(flat_x.shape, _i16_np.float64)
    for offset_z in offsets:
        for offset_x in offsets:
            height = _sample_elevation(sampler, flat_x + offset_x, flat_z + offset_z)
            if not _i16_np.isfinite(height).all():
                raise ValueError('finite elevation sampler heights required')
            total += height
    return _restore(total / len(offsets) ** 2, shape, duplicated)

def _orographic_gradient(seed, x, z, parameters, elevation_sampler):
    """The single upwind difference of §4.2; its only degree of freedom is the bearing."""
    bearing = latitude_norm(seed, z, parameters.latitude_period_m)
    wind_x, wind_z = _wind_unit_arrays(_i16_np.asarray(bearing, _i16_np.float64))
    scale = float(parameters.orographic_scale_m)
    here = ridge_height(seed, x, z, parameters=parameters, elevation_sampler=elevation_sampler)
    upwind = ridge_height(seed, x - wind_x * scale, z - wind_z * scale, parameters=parameters, elevation_sampler=elevation_sampler)
    return (here - upwind) / scale

def _precipitation_multiplier(parameters, gradient):
    """§4.2 multi-branch-free multiplier plus its two geometry diagnostics.

    `shelter` is the negative part of the very same `gradient`, so there is one
    criterion and one place where a threshold could drift.
    """
    lift = _i16_np.maximum(gradient, 0.0)
    shelter = _i16_np.maximum(-gradient, 0.0)
    windward = _i16_np.clip(1.0 + parameters.windward_gain_m * lift, 0.0, 1.0 + parameters.max_windward_gain)
    lee = _i16_np.clip(1.0 - parameters.lee_loss_m * shelter, parameters.min_lee_retention, 1.0)
    return (windward * lee, lift, shelter)

def _refined_monthly_temperature(monthly_temperature, band, parameters):
    """§3.2 row 1: one band offset added to all twelve months.

    A structural short circuit at `latitude_temperature_range_c == 0.` returns the base
    months themselves, so the §7.1 bit-for-bit replay never pays for a redundant
    addition (and a `-0.0` base value can never be normalized to `+0.0`).
    """
    offset = parameters.latitude_temperature_range_c
    if offset == 0.0:
        return monthly_temperature
    return monthly_temperature + offset * band

def _latitude_band_multiplier(parameters, band):
    """§3.2 row 2 synthetic three-band precipitation multiplier (dry-wet-dry; see the docstring).

    Exactly `1.` everywhere -- by construction, not by rounding -- while the row is
    switched off (`latitude_precipitation_gain = 0.`, contract §3.3), so the
    precipitation identity path of §7.1 stays bit for bit.
    """
    gain = parameters.latitude_precipitation_gain
    if gain == 0.0:
        return _i16_np.ones_like(band)
    return 1.0 + gain * _i16_np.cos(_i16_np.pi * band)

def _apply_precipitation_multiplier(monthly, annual_base, multiplier, parameters):
    """Clamped annual target plus the v1 rescaling of the twelve months.

    Returns `(monthly, annual, target, applied)`.

    When every multiplier is exactly `1.` the v1 months are returned *untouched* and
    both annuals are the v1 annual sum (the §7.1 identity path, bit for bit).
    Otherwise the annual target is clamped to the declared interval (§4.4) and the
    months keep their v1 seasonal shape through one scalar ratio per point.

    Two annual numbers are deliberately reported because no float64 pair of twelve
    months can in general carry one exact clamped total *and* an exact sum:

    - `target` is the clamped, post-multiplier annual of §4.4 and always lies inside
      `[min, max]` exactly;
    - `annual` is the realized `sum(monthly)`, so the §4.4 requirement that the
      annual sum of the months equal the refined annual and the §7.7 relation
      `BIO12 == sum(months)` both hold *bit for bit*.

    The two differ by at most one unit in the last place of the target
    (`spacing(3200) = 4.5e-13` mm), which is what the single residual repair below
    bounds.
    """
    if bool(_i16_np.all(multiplier == 1.0)):
        return (monthly, annual_base, annual_base, False)
    target = _i16_np.clip(annual_base * multiplier, parameters.annual_precipitation_min_mm, parameters.annual_precipitation_max_mm)
    ratio = _i16_np.divide(target, annual_base, out=_i16_np.ones_like(annual_base), where=annual_base > 0.0)
    scaled = monthly * ratio
    residual = target - scaled.sum(axis=0)
    flat = scaled.reshape(monthly.shape[0], -1)
    index = _i16_np.argmax(flat, axis=0)
    flat[index, _i16_np.arange(flat.shape[1])] += residual.reshape(-1)
    months = flat.reshape(monthly.shape)
    return (months, months.sum(axis=0), target, True)

def snow_line(seed, x_m, z_m, *, parameters=None):
    """§6 derived snow-line diagnostic: the elevation at which the monthly mean crosses 0 C.

    Derived **only** from the refined monthly temperatures this module already produces at
    zero elevation, and never fed back into precipitation (no precipitation term here, no
    change to `sample_climate_v2`). The base layer's only elevation dependence is the lapse
    rate and it is linear, so each month's crossing is solved in closed form
    (`h = -T / lapse_rate_c_per_m` for the freezing direction, clamped at `0` when the month
    is already below zero at sea level). A non-negative lapse rate makes the threshold
    infinite, meaning "this month never freezes at any elevation".

    Reported keys: `monthly_first_freezing_elevation_m` (12 months, the elevation where that
    month's mean starts dropping below zero), `seasonal_snow_line_m` (the lowest such
    elevation over the year: the first month to freeze defines the seasonal snow line) and
    `perennial_snow_line_m` (the highest such elevation: every month is below zero there),
    plus the criterion wording, the lapse rate used, and the schema/identity of the used
    parameters.
    """
    parameters = parameters or RefinedClimateParameters()
    if not isinstance(parameters, RefinedClimateParameters):
        raise ValueError('RefinedClimateParameters required')
    flat_x, flat_z, shape, duplicated = _canonical_query(seed, x_m, z_m)
    base = sample_climate(seed, flat_x, flat_z, 0.0, parameters=parameters.base)
    band = _i16_np.asarray(latitude_norm(seed, flat_z, parameters.latitude_period_m), _i16_np.float64)
    temperature = _refined_monthly_temperature(base['monthly_temperature_c'], band, parameters)
    lapse = parameters.base.lapse_rate_c_per_m
    if lapse < 0.0:
        freezing = _i16_np.where(temperature > 0.0, -temperature / lapse, 0.0)
    else:
        freezing = _i16_np.full(temperature.shape, _i16_np.inf, _i16_np.float64)
    return {'monthly_first_freezing_elevation_m': _restore_months(freezing, shape, duplicated), 'seasonal_snow_line_m': _restore(freezing.min(axis=0), shape, duplicated), 'perennial_snow_line_m': _restore(freezing.max(axis=0), shape, duplicated), 'snow_line_criterion': SNOW_LINE_CRITERION, 'lapse_rate_c_per_m': lapse, 'latitude_temperature_range_c': parameters.latitude_temperature_range_c, 'latitude_band_norm': _restore(band, shape, duplicated), 'base_parameter_identity_sha256': parameters.base_parameter_identity_sha256, 'parameter_identity_sha256': parameters.identity_sha256, 'schema': SNOW_LINE_SCHEMA, 'semantics': REFINED_SEMANTICS, 'band_structure_semantics': BAND_STRUCTURE_SEMANTICS}

def sample_climate_v2(seed, x_m, z_m, elevation_m=None, *, parameters=None, elevation_sampler=None):
    """§4.3 v1 base climate plus the normalized band and orographic refinements.

    The v1 layer is called, not copied, and its identity is reported as
    `base_parameter_identity_sha256` next to the v2 `parameter_identity_sha256`.
    Returned keys: the v1 monthly/BIO/strength keys unchanged, plus
    `latitude_band_norm`, `latitude_temperature_offset_c`, `latitude_precipitation_multiplier`,
    `wind_unit`, `orographic_lift`, `orographic_shelter`, `precipitation_multiplier`,
    `annual_precipitation_mm` (the realized monthly sum,
    so `BIO12 == sum(months)` is exact), `annual_precipitation_target_mm` (the clamped
    post-multiplier annual of §4.4, always inside the declared interval), `elevation_m`
    (the value actually used), `elevation_source`, `orographic_applied`,
    `wind_bearing_bands`, `schema`, `semantics` and `band_structure_semantics`.

    The temperature row of §3.2 shifts all twelve months by one band offset, so `BIO1` and
    `BIO4` still describe the returned months; the snow line of that row is reported
    separately by `snow_line` and is never a precipitation term (§6).
    """
    parameters = parameters or RefinedClimateParameters()
    if not isinstance(parameters, RefinedClimateParameters):
        raise ValueError('RefinedClimateParameters required')
    flat_x, flat_z, shape, duplicated = _canonical_query(seed, x_m, z_m)
    if elevation_m is None:
        elevation = _sample_elevation(_resolve_elevation_sampler(seed, elevation_sampler), flat_x, flat_z)
        if not _i16_np.isfinite(elevation).all():
            raise ValueError('finite elevation sampler heights required')
        elevation_source = 'coarse_condition_field_height_m' if elevation_sampler is None else 'caller_supplied_pure_sampler'
    else:
        elevation = _i16_np.broadcast_to(_i16_np.asarray(elevation_m, _i16_np.float64), shape).reshape(-1)
        if duplicated:
            elevation = _i16_np.repeat(elevation, 2)
        if not _i16_np.isfinite(elevation).all():
            raise ValueError('finite physical elevation required')
        elevation_source = 'explicit_elevation_m'
    base = sample_climate(seed, flat_x, flat_z, elevation, parameters=parameters.base)
    base_monthly = base['monthly_precipitation_mm']
    annual_base = base_monthly.sum(axis=0)
    band = _i16_np.asarray(latitude_norm(seed, flat_z, parameters.latitude_period_m), _i16_np.float64)
    gradient = _orographic_gradient(seed, flat_x, flat_z, parameters, elevation_sampler)
    orographic_multiplier, lift, shelter = _precipitation_multiplier(parameters, gradient)
    band_multiplier = _latitude_band_multiplier(parameters, band)
    multiplier = orographic_multiplier * band_multiplier
    monthly, annual, annual_target, applied = _apply_precipitation_multiplier(base_monthly, annual_base, multiplier, parameters)
    base_temperature = base['monthly_temperature_c']
    temperature = _refined_monthly_temperature(base_temperature, band, parameters)
    if applied or temperature is not base_temperature:
        bioclim = _i16_np.stack((_i16_np.mean(temperature, axis=0), _i16_np.std(temperature, axis=0) * 100.0, _i16_np.sum(monthly, axis=0), _i16_np.std(monthly, axis=0) / _i16_np.mean(monthly, axis=0) * 100.0))
    else:
        bioclim = base['BIO1_4_12_15']
    wind_x, wind_z = _wind_unit_arrays(band)
    return {'monthly_temperature_c': _restore_months(temperature, shape, duplicated), 'monthly_precipitation_mm': _restore_months(monthly, shape, duplicated), 'BIO1_4_12_15': _restore_months(bioclim, shape, duplicated), 'thermal_strength': _restore(base['thermal_strength'], shape, duplicated), 'moisture_strength': _restore(base['moisture_strength'], shape, duplicated), 'continentality_strength': _restore(base['continentality_strength'], shape, duplicated), 'latitude_band_norm': _restore(band, shape, duplicated), 'latitude_temperature_offset_c': _restore(band * parameters.latitude_temperature_range_c, shape, duplicated), 'latitude_precipitation_multiplier': _restore(band_multiplier, shape, duplicated), 'wind_unit': (_restore(wind_x, shape, duplicated, _i16_np.int64), _restore(wind_z, shape, duplicated, _i16_np.int64)), 'orographic_lift': _restore(lift, shape, duplicated), 'orographic_shelter': _restore(shelter, shape, duplicated), 'precipitation_multiplier': _restore(multiplier, shape, duplicated), 'annual_precipitation_mm': _restore(annual, shape, duplicated), 'annual_precipitation_target_mm': _restore(annual_target, shape, duplicated), 'elevation_m': _restore(elevation, shape, duplicated), 'elevation_source': elevation_source, 'orographic_applied': applied, 'base_parameter_identity_sha256': parameters.base_parameter_identity_sha256, 'parameter_identity_sha256': parameters.identity_sha256, 'schema': CLIMATE_SCHEMA, 'semantics': REFINED_SEMANTICS, 'band_structure_semantics': BAND_STRUCTURE_SEMANTICS, 'wind_bearing_bands': parameters.wind_bearing_bands}

def grid_rainfall_v2(seed, *, origin_xz_m, shape_zx, spacing_m, time_edges_s, elevation_sampler=None, parameters=None, spatial_subsamples=2):
    """§4.3 terrain-aware rainfall grid, the v2 counterpart of `grid_rainfall`.

    Spatial averaging is v1's equal-area midpoint subcell quadrature with the same
    origin-is-center convention. Per subcell the v2 rainfall is the v1 interval
    integral of the base monthly climate scaled by the v2 precipitation multiplier;
    the v1 interval integral is exactly linear in the monthly rates and v1's
    precipitation is elevation independent, so this is the same field as integrating
    the refined monthly values directly, while keeping a single integration truth in
    v1. Both the orographic term of §4.2 and the band multiplier of §3.2 row 2 enter here
    through the same product used by `sample_climate_v2`, so the grid and the point query
    cannot drift apart. With every refinement switched off both factors are exactly `1.`
    and the result equals `grid_rainfall` bit for bit.
    """
    from terrain_pipeline.common_infra import RainfallForcing as _i16_RainfallForcing
    from terrain_pipeline.common_infra import identity as _i16_identity
    parameters = parameters or RefinedClimateParameters()
    if not isinstance(parameters, RefinedClimateParameters):
        raise ValueError('RefinedClimateParameters required')
    edges = _i16_np.asarray(time_edges_s, _i16_np.float64)
    if edges.ndim != 1 or edges.size < 2 or (not _i16_np.isfinite(edges).all()) or _i16_np.any(_i16_np.diff(edges) <= 0.0) or (edges[0] < 0.0):
        raise ValueError('increasing finite physical time edges required')
    if spatial_subsamples not in (1, 2, 4) or len(shape_zx) != 2 or any((type(side) is not int or side <= 0 for side in shape_zx)):
        raise ValueError('positive grid shape and 1/2/4 midpoint subdivisions required')
    if type(spacing_m) not in (int, float) or not _i16_math.isfinite(spacing_m) or spacing_m <= 0.0:
        raise ValueError('positive physical grid spacing required')
    if _i16_np.prod(shape_zx) * (edges.size - 1) * spatial_subsamples ** 2 > 50000000:
        raise ValueError('noise rainfall resource dimensions exceeded')
    rows, columns = _i16_np.indices(shape_zx)
    offsets = (_i16_np.arange(spatial_subsamples) + 0.5) / spatial_subsamples - 0.5
    intensity = _i16_np.zeros((edges.size - 1,) + tuple(shape_zx), _i16_np.float64)
    for delta_z in offsets:
        for delta_x in offsets:
            x = origin_xz_m[0] + (columns + delta_x) * spacing_m
            z = origin_xz_m[1] + (rows + delta_z) * spacing_m
            flat_x = _i16_np.ascontiguousarray(_i16_np.asarray(x, _i16_np.float64).reshape(-1))
            flat_z = _i16_np.ascontiguousarray(_i16_np.asarray(z, _i16_np.float64).reshape(-1))
            gradient = _orographic_gradient(seed, flat_x, flat_z, parameters, elevation_sampler)
            orographic_multiplier = _precipitation_multiplier(parameters, gradient)[0]
            band = _i16_np.asarray(latitude_norm(seed, flat_z, parameters.latitude_period_m), _i16_np.float64)
            multiplier = orographic_multiplier * _latitude_band_multiplier(parameters, band)
            for index, (start, end) in enumerate(zip(edges, edges[1:])):
                intensity[index] += (multiplier * interval_mean_rain_mm_h(seed, flat_x, flat_z, float(start), float(end), parameters=parameters.base)).reshape(tuple(shape_zx)) / spatial_subsamples ** 2
    metadata = {'schema': RAINFALL_SCHEMA, 'seed': seed, 'origin_xz_m': list(origin_xz_m), 'shape_zx': list(shape_zx), 'spacing_m': float(spacing_m), 'time_edges_s': edges.tolist(), 'parameters': _i16_asdict(parameters), 'latitude_precipitation_gain': parameters.latitude_precipitation_gain, 'base_parameter_identity_sha256': parameters.base_parameter_identity_sha256, 'parameter_identity_sha256': parameters.identity_sha256, 'spatial_mean': 'equal_area_midpoint_subcells', 'spatial_subsamples': spatial_subsamples, 'cell_boundary_convention': 'origin_is_center;subcells_cover_center_plus_minus_half_spacing', 'absolute_weather_step_s': parameters.base.absolute_weather_step_s, 'elevation_source': 'coarse_condition_field_height_m' if elevation_sampler is None else 'caller_supplied_pure_sampler', 'rainfall_composition': 'v1_interval_mean_rain_mm_h_times_v2_annual_precipitation_multiplier', 'monthly_target_is_not_realized_annual_forcing': True, 'semantics': REFINED_SEMANTICS, 'band_structure_semantics': BAND_STRUCTURE_SEMANTICS, 'wind_bearing_bands': parameters.wind_bearing_bands}
    metadata['source_identity_sha256'] = _i16_identity({}, metadata)
    forcing = _i16_RainfallForcing(edges, intensity, 'synthetic_noise_terrain_climate_v2', metadata['source_identity_sha256'])
    return (forcing, metadata)
SEASONAL_AIR_SCHEMA = 'environment-seasonal-air-v1'
CALENDAR_ALGORITHM = 'fixed-365-day-month-table-v1'
INTERVAL_ALGORITHM = 'whole_year_closed_form_plus_bounded_remainder_v2'
MAX_POINTS = 8192
MAX_PERIOD_BYTES = 8 * 1024 * 1024
MAX_PERIOD_ENTRIES = MAX_PERIOD_BYTES // 16
MAX_SECONDS = 60.0
GRID_SPACING_M = 30.0
GRID_ALIGN_ATOL = 1e-06
MAX_TIME_S = 1000000000000.0
MIN_INTERVAL_ULPS = 8.0
MAX_REMAINDER_SEGMENTS = 14
NOT_RETURNED = ('potential_et', 'actual_et', 'available_water', 'snowpack', 'snow_water_equivalent', 'glacier', 'melt', 'land_cover', 'latitude_deg', 'diurnal_temperature_range')
SEASONAL_AIR_SEMANTICS = 'synthetic_monthly_mean_temperature_adapter_not_measured_weather; reuses_metric_climate_refinement_sample_climate_v2_without_new_formula'
SEASONAL_AIR_DECLARED_LIMITS = ('monthly mean temperature is not a daily maximum, a daily minimum or a diurnal range', 'monthly_temperature_c <= 0 is a threshold diagnostic, not snowpack and not glacier mass balance', 'temperature and prevailing wind share one synthetic band coordinate (latitude_norm); that is a declared synthetic compatibility assumption, not a dynamically consistent atmospheric circulation', 'annual_mean_temperature_c is the unweighted mean of twelve monthly means (v2 BIO1), not a day-weighted annual mean', "the snow_line block has no elevation argument: it is solved from zero-elevation monthly means and the lapse rate, so it is not driven by the caller's elevation sampler", 'MAX_SECONDS is a post-stage soft check that cannot interrupt a running kernel; bounded loops and the pre-materialisation byte budget are the real protection')
_DEPENDENCY_MODULES = ('terrain_pipeline.climate_forcing', 'terrain_pipeline.hydrology_planning')
UNITS = {'x_m': 'm_easting', 'z_m': 'm_southing', 'elevation_m': 'm', 'monthly_temperature_c': 'degC_monthly_mean', 'annual_mean_temperature_c': 'degC_unweighted_mean_of_12_monthly_means', 'period_mean_temperature_c': 'degC_interval_mean_month_center_piecewise_linear', 'seasonal_temperature_amplitude_c': 'degC_monthly_max_minus_monthly_min', 'latitude_band_norm': '1', 'latitude_temperature_offset_c': 'degC', 'coldest_month_index': 'month_ordinal_0_to_11', 'warmest_month_index': 'month_ordinal_0_to_11', 'monthly_at_or_below_freezing': 'bool', 'freezing_month_count': 'month_count_0_to_12', 'has_freezing_month': 'bool', 'all_months_freezing': 'bool', 'wind_bearing_x': '1_east_positive', 'wind_bearing_z': '1_south_positive', 'wind_band_index': 'ordinal_0_to_2', 'wind_band_name': 'label', 'time_edges_s': 's_since_declared_epoch', 'monthly_first_freezing_elevation_m': 'm', 'seasonal_snow_line_m': 'm', 'perennial_snow_line_m': 'm'}
SOURCE_OF = {'x_m': 'caller_supplied', 'z_m': 'caller_supplied', 'elevation_m': 'metric_climate_refinement sample_climate_v2 elevation_m', 'monthly_temperature_c': 'metric_climate_refinement.sample_climate_v2', 'annual_mean_temperature_c': 'derived: unweighted mean of the twelve monthly means', 'period_mean_temperature_c': 'derived: ' + INTERVAL_ALGORITHM, 'seasonal_temperature_amplitude_c': 'derived: max minus min over the twelve months', 'latitude_band_norm': 'metric_climate_refinement.latitude_norm', 'latitude_temperature_offset_c': 'metric_climate_refinement sample_climate_v2 latitude_temperature_offset_c', 'coldest_month_index': 'derived: argmin over monthly_temperature_c', 'warmest_month_index': 'derived: argmax over monthly_temperature_c', 'monthly_at_or_below_freezing': 'derived: monthly_temperature_c <= 0', 'freezing_month_count': 'derived: count of monthly_temperature_c <= 0', 'has_freezing_month': 'derived: freezing_month_count > 0', 'all_months_freezing': 'derived: freezing_month_count == 12', 'wind_bearing_x': 'metric_climate_refinement sample_climate_v2 wind_unit', 'wind_bearing_z': 'metric_climate_refinement sample_climate_v2 wind_unit', 'wind_band_index': 'derived: latitude_norm against the imported band limits', 'wind_band_name': 'derived: WIND_BAND_NAMES at wind_band_index', 'time_edges_s': 'caller_supplied', 'monthly_first_freezing_elevation_m': 'metric_climate_refinement.snow_line (pass-through)', 'seasonal_snow_line_m': 'metric_climate_refinement.snow_line (pass-through)', 'perennial_snow_line_m': 'metric_climate_refinement.snow_line (pass-through)'}

def calendar():
    """The physical calendar these months refer to, as a plain declaration.

    Returned as data (not as prose only) so a consumer can bind it into its own
    identity instead of assuming a year length.
    """
    return {'algorithm': CALENDAR_ALGORITHM, 'interval_algorithm': INTERVAL_ALGORITHM, 'month_days': [int(value) for value in MONTH_DAYS], 'month_edges_s': [float(value) for value in MONTH_EDGES_S], 'month_centers_s': [float(value) for value in MONTH_CENTERS_S], 'days_per_year': int(MONTH_DAYS.sum()), 'year_seconds': float(YEAR_S), 'epoch_seconds': 0.0, 'time_index': 'physical seconds since the declared epoch; never a step counter', 'declaration': 'fixed 365-day year taken from the v1 month-day table; no leap day, no epoch offset, no timezone and no latitude-dependent day length; month identity repeats every year_seconds', 'leap_day_handled': False, 'day_length_varies_with_latitude': False}

def _code_identities():
    """Source-byte identity of every kernel this adapter reuses, including itself.

    Purpose: the same parameters evaluated against a changed kernel must not yield
    the same composite identity. This is a binding, not an anti-tamper signature.
    """
    record = {}
    for name in _DEPENDENCY_MODULES:
        module = _i15_importlib.import_module(name)
        path = getattr(module, '__file__', None)
        if not path or not _i15_os.path.exists(path):
            raise ValueError('cannot locate source file for %s' % name)
        with open(path, 'rb') as handle:
            digest = _i15_hashlib.sha256(handle.read()).hexdigest()
        record[name] = {'source_sha256': digest, 'basename': _i15_os.path.basename(path)}
    return record

def _validate_seed(seed):
    if isinstance(seed, bool) or not isinstance(seed, (int, _i15_np.integer)):
        raise ValueError('seed must be a non-boolean integer')
    value = int(seed)
    if not 0 <= value < 2 ** 64:
        raise ValueError('seed must satisfy 0 <= seed < 2**64')
    return value

def _broadcast_points(x_m, z_m):
    """Broadcast the request, then check the point budget **before** materialising.

    `broadcast_arrays` does not allocate; the size check therefore rejects a huge
    broadcast shape before any array is built from it.
    """
    try:
        x, z = _i15_np.broadcast_arrays(_i15_np.asarray(x_m, _i15_np.float64), _i15_np.asarray(z_m, _i15_np.float64))
    except ValueError:
        raise ValueError('x_m and z_m must broadcast to a common shape')
    if x.size < 1 or x.size > MAX_POINTS:
        raise ValueError('point count %d outside 1..%d' % (x.size, MAX_POINTS))
    if not _i15_np.isfinite(x).all() or not _i15_np.isfinite(z).all():
        raise ValueError('finite absolute world coordinates required')
    if max(float(_i15_np.abs(x).max()), float(_i15_np.abs(z).max())) > 1000000000000.0:
        raise ValueError('bounded absolute meter coordinates required')
    return (x, z)

def _require_grid_aligned(values, name):
    """30 m grid reference points only; never snap, round or interpolate."""
    quotient = values / GRID_SPACING_M
    if not _i15_np.allclose(quotient, _i15_np.rint(quotient), rtol=0.0, atol=1e-08):
        raise ValueError('%s must be an integer multiple of %.1f m (30 m grid reference points); this entry point never snaps or interpolates' % (name, GRID_SPACING_M))

def _validate_time_edges(time_edges_s, points):
    """Validate physical time edges and pre-check the period byte budget."""
    if time_edges_s is None:
        return None
    edges = _i15_np.asarray(time_edges_s, _i15_np.float64)
    if edges.ndim != 1 or edges.size < 2 or (not _i15_np.isfinite(edges).all()) or _i15_np.any(_i15_np.diff(edges) <= 0.0) or (edges[0] < 0.0):
        raise ValueError('increasing finite nonnegative physical time edges required')
    if float(edges[-1]) > MAX_TIME_S:
        raise ValueError('time edge %r s exceeds the declared domain %.0e s: beyond it double precision cannot resolve a one-day interval and an interval mean would be cancellation noise' % (float(edges[-1]), MAX_TIME_S))
    entries = int(edges.size - 1) * int(points)
    if entries > MAX_PERIOD_ENTRIES:
        raise ValueError('period temperature entries %d exceed the budget %d (peak about %.1f MiB counting the list plus the stacked array, not just the payload)' % (entries, MAX_PERIOD_ENTRIES, 16.0 * entries / 2 ** 20))
    return edges

def _unresolvable_interval(start_s, end_s):
    """True when `I(end) - I(start)` would be cancellation noise rather than a mean."""
    span = float(end_s) - float(start_s)
    if span <= 0.0:
        return True
    magnitude = max(abs(float(start_s)), abs(float(end_s)))
    if magnitude == 0.0:
        return False
    return span < MIN_INTERVAL_ULPS * float(_i15_np.spacing(magnitude))

def _seasonal_air_wind_band_index(norm):
    """Band ordinal from the band coordinate, using the v2 public band limits.

    This repeats the *rule* only so it can be **cross-checked** against the
    `wind_unit` that v2 actually returned. A mismatch is raised as drift; it is
    never silently preferred over the v2 answer.
    """
    magnitude = _i15_np.abs(norm)
    return _i15_np.where(magnitude < WIND_TRADE_BAND_LIMIT, 0, _i15_np.where(magnitude < WIND_POLAR_BAND_LIMIT, 1, 2))

def _annual_weights():
    """Trapezoid weights over month centers, wrapping across the year boundary."""
    gaps = _i15_np.diff(_i15_np.r_[MONTH_CENTERS_S, MONTH_CENTERS_S[0] + YEAR_S])
    return 0.5 * (gaps + _i15_np.roll(gaps, 1))

def _within_year_integral(monthly_flat, start_offset_s, end_offset_s):
    """Integral of the month-center piecewise-linear series over one sub-year window.

    Both offsets lie in `[0, year_seconds]` and are measured from a year boundary.
    At most `MAX_REMAINDER_SEGMENTS` month-center segments are touched, so the cost
    never depends on the physical span.

    `monthly_flat` is `(12, n)`; the result has shape `(n,)`.
    """
    total = _i15_np.zeros(monthly_flat.shape[1:], _i15_np.float64)
    lower = float(start_offset_s)
    target = float(end_offset_s)
    segments = 0
    while lower < target:
        segments += 1
        if segments > MAX_REMAINDER_SEGMENTS + 2:
            raise ValueError('within-year integration exceeded %d month-center segments; this indicates a calendar defect rather than a large request' % (MAX_REMAINDER_SEGMENTS + 2))
        index = int(_i15_np.searchsorted(MONTH_CENTERS_S, lower, side='right')) - 1
        if index < 0:
            first_time = MONTH_CENTERS_S[-1] - YEAR_S
            last_time = MONTH_CENTERS_S[0]
        elif index == 11:
            first_time = MONTH_CENTERS_S[-1]
            last_time = MONTH_CENTERS_S[0] + YEAR_S
        else:
            first_time = MONTH_CENTERS_S[index]
            last_time = MONTH_CENTERS_S[index + 1]
        upper = min(target, last_time)
        if not upper > lower:
            raise ValueError('month-center integration made no progress at offset %r s (upper %r <= lower %r); refusing to spin instead of returning a corrupted mean' % (lower, upper, lower))
        fraction = (0.5 * (lower + upper) - first_time) / (last_time - first_time)
        first = monthly_flat[index % 12]
        total = total + (first + fraction * (monthly_flat[(index + 1) % 12] - first)) * (upper - lower)
        lower = upper
    return total

def _year_index_and_offset(moment_s):
    """Split an absolute physical time into `(year_index, offset_within_year)`.

    `math.fmod` is exact by definition: `fmod(x, y)` is `x - n*y` with no rounding,
    so `moment - offset` is an exact integer multiple of the year length (every
    such multiple stays below 2**53 for the declared time domain, so it is exactly
    representable). Dividing that exact multiple by the year length therefore
    recovers the year index exactly, and `round` is used instead of `floor` so a
    quotient that lands a hair either side of an integer cannot shift the index by
    one. `moment_s` is always non-negative here, so the offset is non-negative too.
    """
    moment = float(moment_s)
    offset = _i15_math.fmod(moment, YEAR_S)
    years = int(round((moment - offset) / YEAR_S))
    return (years, offset)

def _interval_mean_monthly(monthly_flat, start_s, end_s):
    """Time-weighted mean of a monthly series over one physical interval.

    Same convention as `metric_noise_forcing.interval_mean_rain_mm_h`: values sit
    at month centers, are linearly interpolated, and wrap across the year
    boundary. The integral of a linear function is exact under the trapezoid, so
    no discretisation error is introduced beyond floating point.

    **No large-magnitude subtraction.** The integral is assembled from short pieces
    on purpose:

    * the tail of the start year, measured from the start's own year offset;
    * `whole_years * annual_integral` in closed form;
    * the head of the end year, measured from zero.

    Computing a single antiderivative at both endpoints and then subtracting it
    would cancel badly at large epochs: with a start near 1e9 s the difference of
    two ~1e10-sized antiderivatives loses about 1e-10 relative accuracy, which is
    larger than any honest tolerance for a mean. Splitting the interval keeps every
    arithmetic step local, so the same phase at any epoch gives the same mean to
    within floating-point summation order rather than to within a cancellation
    error.

    Offsets use `math.fmod`, which is exact by definition (`fmod(x, y)` is
    `x - n*y` with no rounding), so the split itself introduces no error.
    """
    start = float(start_s)
    end = float(end_s)
    if not (_i15_math.isfinite(start) and _i15_math.isfinite(end)) or end <= start:
        raise ValueError('increasing finite physical interval required')
    if _unresolvable_interval(start, end):
        raise ValueError('interval [%r, %r] s is narrower than %.0f ulps of its own magnitude (%r): the interval mean would be cancellation noise, so none is returned' % (start, end, MIN_INTERVAL_ULPS, float(_i15_np.spacing(max(abs(start), abs(end))))))
    span = end - start
    start_years, start_offset = _year_index_and_offset(start)
    end_years, end_offset = _year_index_and_offset(end)
    if start_years == end_years:
        integral = _within_year_integral(monthly_flat, start_offset, end_offset)
    else:
        annual_integral = _annual_weights() @ monthly_flat
        integral = _within_year_integral(monthly_flat, start_offset, YEAR_S)
        whole_years = end_years - start_years - 1
        if whole_years > 0:
            integral = integral + float(whole_years) * annual_integral
        if end_offset > 0.0:
            integral = integral + _within_year_integral(monthly_flat, 0.0, end_offset)
    return integral / span

def _canonical_order(x, z):
    """Stable `(x, z)` ordering so identity is a property of the point set.

    The returned arrays keep the caller's own order; only the digest sees this one.
    """
    return _i15_np.lexsort((z, x))

def _points_digest(x, z):
    order = _canonical_order(x, z)
    canonical = _i15_np.stack((_i15_np.ascontiguousarray(x[order]), _i15_np.ascontiguousarray(z[order])), axis=1)
    return _i15_hashlib.sha256(_i15_np.ascontiguousarray(canonical).tobytes()).hexdigest()

def period_peak_bytes(points, intervals):
    """Peak period-related bytes, stated honestly (list plus stacked array)."""
    intervals = 0 if intervals is None else int(intervals)
    return int(16 * intervals * int(points))

def describe():
    """Static declaration for reviewers and downstream consumers; no numbers."""
    return {'schema': SEASONAL_AIR_SCHEMA, 'calendar': calendar(), 'grid_spacing_m': GRID_SPACING_M, 'max_points': MAX_POINTS, 'max_period_entries': MAX_PERIOD_ENTRIES, 'max_period_bytes': MAX_PERIOD_BYTES, 'max_period_bytes_note': 'peak period block; each interval is materialised once as a vector, collected in a list, then stacked', 'max_time_s': MAX_TIME_S, 'min_interval_ulps': MIN_INTERVAL_ULPS, 'max_remainder_segments': MAX_REMAINDER_SEGMENTS, 'max_seconds': MAX_SECONDS, 'max_seconds_semantics': 'post-stage soft check; it cannot interrupt a running kernel. Bounded loops plus the pre-materialisation byte budget are the real protection', 'interval_algorithm': INTERVAL_ALGORITHM, 'interval_algorithm_note': 'assembled from the start-year tail, closed-form whole years and the end-year head; never a difference of two large antiderivatives', 'units': dict(UNITS), 'source_of': dict(SOURCE_OF), 'semantics': SEASONAL_AIR_SEMANTICS, 'declared_limits': list(SEASONAL_AIR_DECLARED_LIMITS), 'not_returned': list(NOT_RETURNED), 'identity_binds': ['canonically sorted (x, z) coordinates', 'query shape', 'the elevation values actually used and their declared source', 'all twelve monthly temperatures', 'latitude band and band temperature offset', 'wind bearing and band index', 'annual mean, amplitude, freezing count', 'period means when time edges are given', 'calendar, parameters, wind rule', 'source bytes of every dependency kernel, including this module'], 'identity_order_contract': "the digest is computed over arrays sorted by (x, z), so permuting the request arrays does not change the identity; the returned arrays keep the caller's order", 'sampler_identity_contract': 'an elevation sampler is bound by the values it returned, never by its function name; two samplers returning identical heights are the same product by construction', 'reused_entries': ['terrain_pipeline.climate_forcing.sample_climate_v2', 'terrain_pipeline.climate_forcing.snow_line (optional pass-through only, with its own elevation semantics)'], 'wind_rule_source': 'metric_climate_refinement.latitude_norm -> WIND_BAND_UNITS; the rule and the three-band table are imported, never re-derived here', 'never': ['temperature-index PET or actual ET (owned by S5)', 'snowpack, snow-water equivalent, glacier or melt', 'a real latitude, a Koeppen class or a measured climatology', 'a moisture or vapour budget (G4 scope, separate module)', 'silently preferring a locally re-derived wind band over the v2 answer', 'calling MAX_SECONDS a hard interrupt', 'calling annual_mean_temperature_c a day-weighted annual mean', 'labelling the snow-line block as sampler-driven']}

def sample_seasonal_air(seed, x_m, z_m, *, elevation_m=None, elevation_sampler=None, parameters=None, time_edges_s=None, include_snow_line=False):
    """Monthly temperature, wind and calendar on absolute world 30 m points.

    Parameters
    ----------
    seed : int
        World seed, `0 <= seed < 2**64`. Passed straight to the v2 layer; this
        adapter derives no sub-seed of its own.
    x_m, z_m : array_like
        Absolute world metres, broadcast to one shape. Must lie on 30 m reference
        points; an off-grid request is rejected, never snapped.
    elevation_m, elevation_sampler, parameters :
        Passed through unchanged to `sample_climate_v2`. `parameters` must be
        `None` (use the v2 default) or a `RefinedClimateParameters`; any other
        value, including a falsy one such as `{}` or `0`, is rejected rather than
        quietly replaced by the default.
    time_edges_s : array_like, optional
        Physical time edges (seconds since the declared epoch). When given,
        `period_mean_temperature_c` is returned with shape `(intervals,) + shape`.
    include_snow_line : bool
        When true, the existing `snow_line` diagnostic is passed through under
        `snow_line`. It carries its own zero-elevation semantics and is never
        folded into temperature, precipitation or the freezing count.

    Returns
    -------
    dict
        Declared fields plus `calendar`, `wind`, `sources`, `units`, `identity`,
        `code_identities` and `declared_limits`. See `describe()`.
    """
    from terrain_pipeline.common_infra import identity as _i15_identity
    seed = _validate_seed(seed)
    if parameters is None:
        parameters = RefinedClimateParameters()
    elif not isinstance(parameters, RefinedClimateParameters):
        raise ValueError('parameters must be None or a RefinedClimateParameters instance, got %r; a falsy non-None value is rejected instead of silently defaulting' % type(parameters).__name__)
    if not isinstance(include_snow_line, bool):
        raise ValueError('include_snow_line must be a bool')
    started = _i15_time.perf_counter()

    def check_time(stage):
        """Post-stage soft check: reports lateness, cannot interrupt a kernel."""
        elapsed = _i15_time.perf_counter() - started
        if elapsed > MAX_SECONDS:
            raise ValueError('single call passed the %.0f s soft budget after stage %r (%.3f s); this check cannot interrupt a running kernel, it only falsifies the result' % (MAX_SECONDS, stage, elapsed))
        return elapsed
    x, z = _broadcast_points(x_m, z_m)
    _require_grid_aligned(x, 'x_m')
    _require_grid_aligned(z, 'z_m')
    edges = _validate_time_edges(time_edges_s, x.size)
    shape = x.shape
    flat_x = _i15_np.ascontiguousarray(x.reshape(-1))
    flat_z = _i15_np.ascontiguousarray(z.reshape(-1))
    air = sample_climate_v2(seed, x, z, elevation_m, parameters=parameters, elevation_sampler=elevation_sampler)
    temperature = _i15_np.asarray(air['monthly_temperature_c'], _i15_np.float64)
    if temperature.shape != (12,) + shape:
        raise ValueError('v2 monthly temperature shape drift')
    if not _i15_np.isfinite(temperature).all():
        raise ValueError('v2 returned a non-finite monthly temperature')
    band = _i15_np.asarray(air['latitude_band_norm'], _i15_np.float64)
    if band.shape != shape or not _i15_np.isfinite(band).all():
        raise ValueError('v2 latitude band shape or finiteness drift')
    elevation = _i15_np.asarray(air['elevation_m'], _i15_np.float64).reshape(shape)
    if not _i15_np.isfinite(elevation).all():
        raise ValueError('non-finite elevation reached this layer; a sampler returning NaN or inf is rejected here as well as in the v2 kernel')
    elevation_source = air['elevation_source']
    check_time('climate')
    at_or_below_freezing = temperature <= 0.0
    freezing_month_count = _i15_np.count_nonzero(at_or_below_freezing, axis=0).astype(_i15_np.int64)
    has_freezing_month = freezing_month_count > 0
    all_months_freezing = freezing_month_count == 12
    coldest = _i15_np.argmin(temperature, axis=0).astype(_i15_np.int64)
    warmest = _i15_np.argmax(temperature, axis=0).astype(_i15_np.int64)
    annual_mean = _i15_np.mean(temperature, axis=0)
    amplitude = _i15_np.max(temperature, axis=0) - _i15_np.min(temperature, axis=0)
    offset = _i15_np.asarray(air['latitude_temperature_offset_c'], _i15_np.float64).reshape(shape)
    if not _i15_np.isfinite(offset).all():
        raise ValueError('non-finite band temperature offset')
    wind_x, wind_z = air['wind_unit']
    wind_x = _i15_np.asarray(wind_x, _i15_np.int64).reshape(shape)
    wind_z = _i15_np.asarray(wind_z, _i15_np.int64).reshape(shape)
    band_index = _i15_np.asarray(_seasonal_air_wind_band_index(band), _i15_np.int64).reshape(shape)
    expected = _i15_np.asarray(WIND_BAND_UNITS, _i15_np.int64)
    if not (_i15_np.array_equal(expected[band_index, 0], wind_x) and _i15_np.array_equal(expected[band_index, 1], wind_z)):
        raise ValueError('wind band rule drift: the v2 returned wind_unit does not match WIND_BAND_UNITS at the declared band limits; refusing to guess which answer is authoritative')
    band_names = _i15_np.asarray(WIND_BAND_NAMES, dtype=object)[band_index]
    check_time('wind')
    period = None
    if edges is not None:
        flat = _i15_np.ascontiguousarray(temperature.reshape(12, -1))
        intervals = [_interval_mean_monthly(flat, float(start), float(end)) for start, end in zip(edges, edges[1:])]
        period = _i15_np.stack(intervals).reshape((edges.size - 1,) + shape)
        if not _i15_np.isfinite(period).all():
            raise ValueError('non-finite period mean temperature')
    check_time('period')
    snow = None
    if include_snow_line:
        snow = snow_line(seed, x, z, parameters=parameters)
        for key in ('seasonal_snow_line_m', 'perennial_snow_line_m'):
            values = _i15_np.asarray(snow[key], _i15_np.float64)
            if values.size == 0:
                raise ValueError('empty snow-line diagnostic')
    check_time('snow_line')
    code_identities = _code_identities()
    order = _canonical_order(flat_x, flat_z)
    arrays = {'canonical_x_m': _i15_np.ascontiguousarray(flat_x[order]), 'canonical_z_m': _i15_np.ascontiguousarray(flat_z[order]), 'canonical_elevation_m': _i15_np.ascontiguousarray(elevation.reshape(-1)[order]), 'canonical_monthly_temperature_c': _i15_np.ascontiguousarray(temperature.reshape(12, -1)[:, order].T), 'canonical_latitude_band_norm': _i15_np.ascontiguousarray(band.reshape(-1)[order]), 'canonical_latitude_temperature_offset_c': _i15_np.ascontiguousarray(offset.reshape(-1)[order]), 'canonical_wind_bearing': _i15_np.ascontiguousarray(_i15_np.stack((wind_x.reshape(-1)[order], wind_z.reshape(-1)[order]), axis=1)), 'canonical_annual_mean_temperature_c': _i15_np.ascontiguousarray(annual_mean.reshape(-1)[order]), 'canonical_seasonal_temperature_amplitude_c': _i15_np.ascontiguousarray(amplitude.reshape(-1)[order]), 'canonical_freezing_month_count': _i15_np.ascontiguousarray(freezing_month_count.reshape(-1)[order])}
    if period is not None:
        arrays['canonical_period_mean_temperature_c'] = _i15_np.ascontiguousarray(period.reshape(period.shape[0], -1)[:, order])
    record = {'schema': SEASONAL_AIR_SCHEMA, 'world_seed': seed, 'grid_spacing_m': GRID_SPACING_M, 'point_count': int(x.size), 'query_shape': [int(value) for value in shape], 'query_rank': int(len(shape)), 'points_digest': _points_digest(flat_x, flat_z), 'canonical_order': 'lexsort by (x, z); canonical for the digest only, never for the returned arrays', 'calendar': calendar(), 'climate_schema': CLIMATE_SCHEMA, 'v2_parameter_identity_sha256': parameters.identity_sha256, 'v1_base_parameter_identity_sha256': parameters.base_parameter_identity_sha256, 'latitude_period_m': float(LATITUDE_PERIOD_M), 'latitude_temperature_range_c': float(parameters.latitude_temperature_range_c), 'elevation_source': elevation_source, 'elevation_sampler_identity': "bound by the values returned, not by the callable's name", 'wind': {'rule': 'latitude_norm -> _wind_band_index(WIND_TRADE_BAND_LIMIT, WIND_POLAR_BAND_LIMIT) -> WIND_BAND_UNITS', 'trade_band_limit': float(WIND_TRADE_BAND_LIMIT), 'polar_band_limit': float(WIND_POLAR_BAND_LIMIT), 'units': [list(unit) for unit in WIND_BAND_UNITS], 'names': list(WIND_BAND_NAMES), 'parameter_identity_sha256': parameters.identity_sha256, 'consistency_check': 'returned v2 wind_unit re-verified against the imported table; drift raises instead of guessing'}, 'period': None if edges is None else {'algorithm': INTERVAL_ALGORITHM, 'time_edges_s': [float(value) for value in edges], 'declaration': 'start-year tail, closed-form whole years and end-year head over month centers, wrapping at the year boundary; same convention as the v1 interval rain integral, applied to temperature; never a difference of two large antiderivatives', 'cost_bound': 'bounded by MAX_REMAINDER_SEGMENTS per piece, not by the physical span'}, 'snow_line_requested': bool(include_snow_line), 'snow_line_elevation_semantics': "snow_line has no elevation argument: it is solved from zero-elevation monthly means and the lapse rate, so it is NOT driven by the caller's elevation sampler and is not labelled DEM-driven", 'annual_mean_semantics': 'unweighted arithmetic mean of the twelve monthly means (equals v2 BIO1); not day-weighted', 'declared_limits': list(SEASONAL_AIR_DECLARED_LIMITS), 'code_identities': code_identities, 'semantics': SEASONAL_AIR_SEMANTICS}
    identity_sha256 = _i15_identity(arrays, record)
    return {'schema': SEASONAL_AIR_SCHEMA, 'shape': [int(value) for value in shape], 'x_m': x, 'z_m': z, 'calendar': calendar(), 'monthly_temperature_c': temperature, 'annual_mean_temperature_c': annual_mean, 'seasonal_temperature_amplitude_c': amplitude, 'coldest_month_index': coldest, 'warmest_month_index': warmest, 'monthly_at_or_below_freezing': at_or_below_freezing, 'freezing_month_count': freezing_month_count, 'has_freezing_month': has_freezing_month, 'all_months_freezing': all_months_freezing, 'latitude_band_norm': band, 'latitude_temperature_offset_c': offset, 'wind_bearing_x': wind_x, 'wind_bearing_z': wind_z, 'wind_band_index': band_index, 'wind_band_name': band_names, 'elevation_m': elevation, 'elevation_source': elevation_source, 'period_mean_temperature_c': period, 'time_edges_s': None if edges is None else edges, 'snow_line': snow, 'sources': {'x_m': {'source': SOURCE_OF['x_m'], 'units': UNITS['x_m'], 'note': 'absolute world metres, 30 m grid reference points; never snapped or interpolated'}, 'z_m': {'source': SOURCE_OF['z_m'], 'units': UNITS['z_m'], 'note': 'absolute world metres, 30 m grid reference points'}, 'monthly_temperature_c': {'source': SOURCE_OF['monthly_temperature_c'], 'units': UNITS['monthly_temperature_c'], 'note': 'monthly mean; not a daily maximum, minimum or diurnal range'}, 'annual_mean_temperature_c': {'source': SOURCE_OF['annual_mean_temperature_c'], 'units': UNITS['annual_mean_temperature_c'], 'note': 'equals the v2 BIO1 of the same months; NOT day-weighted, because month lengths differ'}, 'period_mean_temperature_c': {'source': SOURCE_OF['period_mean_temperature_c'], 'units': UNITS['period_mean_temperature_c'], 'note': 'month-center piecewise linear, wrapping at the year boundary; a full-year interval reproduces the annual_weights-weighted mean, which is a third value distinct from both annual_mean_temperature_c and the day-weighted mean'}, 'seasonal_temperature_amplitude_c': {'source': SOURCE_OF['seasonal_temperature_amplitude_c'], 'units': UNITS['seasonal_temperature_amplitude_c']}, 'latitude_band_norm': {'source': SOURCE_OF['latitude_band_norm'], 'units': UNITS['latitude_band_norm'], 'note': 'synthetic east-west band; not a real latitude and never converted to degrees'}, 'latitude_temperature_offset_c': {'source': SOURCE_OF['latitude_temperature_offset_c'], 'units': UNITS['latitude_temperature_offset_c'], 'note': 'one band offset applied to all twelve months'}, 'coldest_month_index': {'source': SOURCE_OF['coldest_month_index'], 'units': UNITS['coldest_month_index']}, 'warmest_month_index': {'source': SOURCE_OF['warmest_month_index'], 'units': UNITS['warmest_month_index']}, 'monthly_at_or_below_freezing': {'source': SOURCE_OF['monthly_at_or_below_freezing'], 'units': UNITS['monthly_at_or_below_freezing'], 'note': 'threshold diagnostic per month; not a phase state'}, 'freezing_month_count': {'source': SOURCE_OF['freezing_month_count'], 'units': UNITS['freezing_month_count'], 'note': 'a threshold diagnostic; not snowpack, snow-water equivalent, glacier or melt', 'inversion_avoided': 'per-month snow-line elevations are not inverted into a month count'}, 'has_freezing_month': {'source': SOURCE_OF['has_freezing_month'], 'units': UNITS['has_freezing_month']}, 'all_months_freezing': {'source': SOURCE_OF['all_months_freezing'], 'units': UNITS['all_months_freezing']}, 'wind_bearing_x': {'source': SOURCE_OF['wind_bearing_x'], 'units': UNITS['wind_bearing_x'], 'note': 'axial unit vector from the synthetic band; not a measured wind and not a continuous stress'}, 'wind_bearing_z': {'source': SOURCE_OF['wind_bearing_z'], 'units': UNITS['wind_bearing_z']}, 'wind_band_index': {'source': SOURCE_OF['wind_band_index'], 'units': UNITS['wind_band_index']}, 'wind_band_name': {'source': SOURCE_OF['wind_band_name'], 'units': UNITS['wind_band_name'], 'note': 'synthetic band label; not a climatological zone name'}, 'elevation_m': {'source': SOURCE_OF['elevation_m'], 'units': UNITS['elevation_m'], 'note': 'the value v2 actually used for the lapse rate; elevation_source says where it came from'}, 'time_edges_s': {'source': SOURCE_OF['time_edges_s'], 'units': UNITS['time_edges_s'], 'note': 'none when no period was requested'}, 'monthly_first_freezing_elevation_m': {'source': SOURCE_OF['monthly_first_freezing_elevation_m'], 'units': UNITS['monthly_first_freezing_elevation_m'], 'note': "per month; the elevation where that month's mean starts dropping below zero"}, 'seasonal_snow_line_m': {'source': SOURCE_OF['seasonal_snow_line_m'], 'units': UNITS['seasonal_snow_line_m'], 'note': 'the lowest monthly first-freezing elevation of the year'}, 'perennial_snow_line_m': {'source': SOURCE_OF['perennial_snow_line_m'], 'units': UNITS['perennial_snow_line_m'], 'note': 'the highest monthly first-freezing elevation of the year'}, 'snow_line': {'source': 'metric_climate_refinement.snow_line (pass-through)', 'units': 'm', 'note': "solved from zero-elevation monthly means and the lapse rate; NOT driven by the caller's elevation sampler; never a precipitation term and never snowpack"}}, 'units': dict(UNITS), 'identity': {'identity_sha256': identity_sha256, 'parameter_identity_sha256': parameters.identity_sha256, 'base_parameter_identity_sha256': parameters.base_parameter_identity_sha256, 'points_digest': record['points_digest'], 'record': record}, 'code_identities': code_identities, 'cost': {'seconds': round(check_time('identity'), 3), 'max_seconds': MAX_SECONDS, 'max_seconds_semantics': 'post-stage soft check; cannot interrupt a running kernel', 'period_peak_bytes': period_peak_bytes(x.size, None if edges is None else edges.size - 1), 'rss_note': 'do not read this as tree RSS; process RSS is measured by the caller/driver'}, 'semantics': SEASONAL_AIR_SEMANTICS, 'declared_limits': list(SEASONAL_AIR_DECLARED_LIMITS), 'not_returned': list(NOT_RETURNED), 'notes': ['adapter only: every physical quantity comes from sample_climate_v2 or from a declared derivation over its output', 'no PET, no actual ET, no snowpack, no glacier, no land cover are returned; those belong to S5, S7 and later cards', 'the vapour budget (boundary supply, depletion, recycling) is G4 scope and is deliberately absent here', 'does not feed the default world, the M1-M4 finite-river product or any seasonal hydrology run; wiring is a separate card']}
STORM_SCHEMA = 'mountain-moving-storm-v1'
STORM_MAX_CELLS = 250000
MAX_HRUS = 256
STORM_MAX_STEPS = 1344
MAX_WORK = 50000000
STORM_MAX_BYTES = 128 * 1024 * 1024

@_i17_dataclass(frozen=True)
class StormParameters:
    center_x_m: float
    center_z_m: float
    velocity_x_m_s: float
    velocity_z_m_s: float
    sigma_m: float
    peak_mm_h: float
    start_s: float
    end_s: float
    spatial_mode: str = 'gaussian'

    def __post_init__(self):
        for key, value in _i17_asdict(self).items():
            if key != 'spatial_mode' and (type(value) not in (int, float) or not _i17_math.isfinite(value)):
                raise ValueError('finite storm parameter required: ' + key)
        if not 1 <= self.sigma_m <= 10000000.0 or not 0 <= self.peak_mm_h <= 1000 or (not 0 <= self.start_s < self.end_s <= 1000000000.0) or (_i17_math.hypot(self.velocity_x_m_s, self.velocity_z_m_s) > 100) or (self.spatial_mode not in {'gaussian', 'uniform'}) or (max(abs(self.center_x_m), abs(self.center_z_m)) > 1000000000000.0):
            raise ValueError('storm outside supported parameter bounds')

def interval_mean_mm_h(east_m, south_m, start_s, end_s, parameters):
    """Analytic Gaussian time integral; center is specified at storm start_s."""
    if not isinstance(parameters, StormParameters):
        raise ValueError('StormParameters required')
    parameters.__post_init__()
    if type(start_s) not in (int, float) or type(end_s) not in (int, float) or (not _i17_math.isfinite(start_s)) or (not _i17_math.isfinite(end_s)) or (not 0 <= start_s < end_s <= 1000000000.0):
        raise ValueError('bounded positive physical time interval required')
    east, south = _i17_np.broadcast_arrays(_i17_np.asarray(east_m), _i17_np.asarray(south_m))
    if east.size > STORM_MAX_CELLS or east.dtype.kind not in 'fiu' or south.dtype.kind not in 'fiu' or (not _i17_np.isfinite(east).all()) or (not _i17_np.isfinite(south).all()):
        raise ValueError('bounded finite absolute coordinates required')
    lower = max(start_s, parameters.start_s)
    upper = min(end_s, parameters.end_s)
    if upper <= lower:
        return _i17_np.zeros(east.shape, _i17_np.float64)
    duration = end_s - start_s
    if parameters.spatial_mode == 'uniform':
        return _i17_np.full(east.shape, parameters.peak_mm_h * (upper - lower) / duration, _i17_np.float64)
    offset_x = east - parameters.center_x_m
    offset_z = south - parameters.center_z_m
    velocity_squared = parameters.velocity_x_m_s ** 2 + parameters.velocity_z_m_s ** 2
    sigma_squared = parameters.sigma_m ** 2
    if velocity_squared == 0:
        return parameters.peak_mm_h * _i17_np.exp(-(offset_x ** 2 + offset_z ** 2) / (2 * sigma_squared)) * (upper - lower) / duration
    speed = _i17_math.sqrt(velocity_squared)
    if speed * (upper - lower) / parameters.sigma_m < 1e-05:
        nodes, weights = _i17_np.polynomial.legendre.leggauss(4)
        midpoint = (lower + upper) / 2
        half_width = (upper - lower) / 2
        average = _i17_np.zeros(east.shape, _i17_np.float64)
        for node, weight in zip(nodes, weights):
            elapsed = midpoint + half_width * node - parameters.start_s
            distance_x = offset_x - parameters.velocity_x_m_s * elapsed
            distance_z = offset_z - parameters.velocity_z_m_s * elapsed
            average += weight * _i17_np.exp(-(distance_x ** 2 + distance_z ** 2) / (2 * sigma_squared)) / 2
        return parameters.peak_mm_h * average * (upper - lower) / duration
    along_m = (offset_x * parameters.velocity_x_m_s + offset_z * parameters.velocity_z_m_s) / speed
    across_m = (offset_x * parameters.velocity_z_m_s - offset_z * parameters.velocity_x_m_s) / speed
    lower_arg = (speed * (lower - parameters.start_s) - along_m) / (_i17_math.sqrt(2) * parameters.sigma_m)
    upper_arg = (speed * (upper - parameters.start_s) - along_m) / (_i17_math.sqrt(2) * parameters.sigma_m)
    from scipy.special import erfc
    difference = _i17_erf(upper_arg) - _i17_erf(lower_arg)
    positive = lower_arg > 0
    negative = upper_arg < 0
    difference = _i17_np.where(positive, erfc(lower_arg) - erfc(upper_arg), difference)
    difference = _i17_np.where(negative, erfc(-upper_arg) - erfc(-lower_arg), difference)
    integral = _i17_np.exp(-across_m ** 2 / (2 * sigma_squared)) * parameters.sigma_m * _i17_math.sqrt(_i17_math.pi / 2) / speed * difference
    return parameters.peak_mm_h * _i17_np.maximum(integral, 0.0) / duration

def storm_preflight(cells, active_cells, steps, hrus, spatial_subsamples):
    values = (cells, active_cells, steps, hrus, spatial_subsamples)
    if any((type(value) is not int for value in values)) or not 1 <= active_cells <= cells <= STORM_MAX_CELLS or (not 1 <= steps <= STORM_MAX_STEPS) or (not 1 <= hrus <= MAX_HRUS) or (spatial_subsamples not in {1, 2, 4}):
        raise ValueError('storm resource dimensions exceeded')
    work = active_cells * steps * spatial_subsamples ** 2
    estimated_bytes = 64 * cells + 32 * active_cells + 16 * steps * hrus
    if work > MAX_WORK or estimated_bytes > STORM_MAX_BYTES:
        raise ValueError('storm work/byte budget exceeded before allocation')
    return {'spatial_evaluations': work, 'estimated_peak_bytes': estimated_bytes, 'max_evaluations': MAX_WORK, 'max_bytes': STORM_MAX_BYTES}

def storm_generate_forcing(cell_owner, *, origin_m_xz, spacing_m, steps, dt_s, start_s, parameters, source_identity, selection_identity, spatial_subsamples=1):
    from terrain_pipeline.common_infra import identity as _i17_identity
    from terrain_pipeline.common_infra import readonly as _i17_readonly
    if not isinstance(cell_owner, _i17_np.ndarray) or cell_owner.ndim != 2 or cell_owner.dtype != _i17_np.int64 or (not 1 <= cell_owner.size <= STORM_MAX_CELLS) or (cell_owner < -1).any():
        raise ValueError('typed bounded unique HRU ownership required')
    active = cell_owner >= 0
    hrus = int(cell_owner.max()) + 1
    resources = storm_preflight(int(cell_owner.size), int(active.sum()), steps, hrus, spatial_subsamples)
    if not isinstance(origin_m_xz, (list, tuple)) or len(origin_m_xz) != 2 or any((type(value) not in (float, int) or not _i17_math.isfinite(value) or abs(value) > 1000000000000.0 for value in origin_m_xz)) or (type(spacing_m) not in (int, float)) or (not _i17_math.isfinite(spacing_m)) or (not 0 < spacing_m <= 100000) or (type(dt_s) not in (int, float)) or (not _i17_math.isfinite(dt_s)) or (not 0.001 <= dt_s <= 10000000.0) or (type(start_s) not in (int, float)) or (not _i17_math.isfinite(start_s)) or (start_s < 0) or (start_s + steps * dt_s > 1000000000.0):
        raise ValueError('invalid absolute metre grid/time')
    for token in (source_identity, selection_identity):
        if not isinstance(token, str) or len(token) != 64:
            raise ValueError('external source and selection identities required')
    if not isinstance(parameters, StormParameters):
        raise ValueError('StormParameters required')
    parameters.__post_init__()
    rows, columns = _i17_np.nonzero(active)
    labels = cell_owner[active]
    counts = _i17_np.bincount(labels, minlength=hrus)
    if (counts == 0).any():
        raise ValueError('HRU labels must be contiguous and nonempty')
    rain = _i17_np.zeros((steps, hrus), _i17_np.float64)
    offsets = (_i17_np.arange(spatial_subsamples) + 0.5) / spatial_subsamples - 0.5
    for step in range(steps):
        lower = start_s + step * dt_s
        values = _i17_np.zeros(labels.size, _i17_np.float64)
        for delta_z in offsets:
            for delta_x in offsets:
                east = origin_m_xz[0] + (columns + delta_x) * spacing_m
                south = origin_m_xz[1] + (rows + delta_z) * spacing_m
                values += interval_mean_mm_h(east, south, lower, lower + dt_s, parameters) / spatial_subsamples ** 2
        rain[step] = _i17_np.bincount(labels, weights=values, minlength=hrus) / counts
    arrays = {'cell_owner': cell_owner.copy(), 'counts': counts, 'area_m2': counts.astype(_i17_np.float64) * spacing_m ** 2, 'rain_mm_h': rain, 'time_edges_s': start_s + _i17_np.arange(steps + 1) * dt_s}
    metadata = {'schema': STORM_SCHEMA, 'parameters': _i17_asdict(parameters), 'origin_m_xz': list(origin_m_xz), 'spacing_m': float(spacing_m), 'dt_s': float(dt_s), 'start_s': float(start_s), 'spatial_subsamples': spatial_subsamples, 'source_identity': source_identity, 'selection_identity': selection_identity, 'temporal_integration': 'analytic_gaussian_erfc_with_4point_gauss_small_displacement', 'spatial_integration': 'equal_area_midpoint_subcells_no_window_normalization', 'units': 'coordinates m; physical time s; rain mm/h; area m2', 'status': 'parameterized_weather_scenario_not_forecast', 'resources': resources}
    result = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i17_identity(arrays, metadata)}
    validate_forcing(result)
    result['arrays'] = {key: _i17_readonly(value) for key, value in arrays.items()}
    return result

def _storm_headers(headers):
    keys = {'cell_owner', 'counts', 'area_m2', 'rain_mm_h', 'time_edges_s', 'manifest'}
    if set(headers) != keys:
        raise ValueError('weather archive member schema mismatch')
    shape, dtype = headers['cell_owner']
    rain_shape, rain_dtype = headers['rain_mm_h']
    if len(shape) != 2 or not 1 <= _i17_math.prod(shape) <= STORM_MAX_CELLS or dtype != _i17_np.int64 or (len(rain_shape) != 2) or (rain_dtype != _i17_np.float64):
        raise ValueError('weather typed grid/rain allocation rejected')
    steps, hrus = rain_shape
    if not 1 <= steps <= STORM_MAX_STEPS or not 1 <= hrus <= MAX_HRUS:
        raise ValueError('weather dimensions exceeded')
    for key, expected_shape, expected_dtype in (('counts', (hrus,), 'int64'), ('area_m2', (hrus,), 'float64'), ('time_edges_s', (steps + 1,), 'float64')):
        if headers[key] != (expected_shape, _i17_np.dtype(expected_dtype)):
            raise ValueError('weather vector header mismatch')
    manifest_shape, manifest_dtype = headers['manifest']
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= 65536 or manifest_dtype != _i17_np.uint8:
        raise ValueError('weather metadata header rejected')

def validate_forcing(result, *, cell_owner=None, source_identity=None, selection_identity=None):
    from terrain_pipeline.runoff import _hash as _i17__hash
    from terrain_pipeline.common_infra import identity as _i17_identity
    arrays, meta = (result['arrays'], result['metadata'])
    expected_meta = {'schema', 'parameters', 'origin_m_xz', 'spacing_m', 'dt_s', 'start_s', 'spatial_subsamples', 'source_identity', 'selection_identity', 'temporal_integration', 'spatial_integration', 'units', 'status', 'resources'}
    if set(meta) != expected_meta or meta['schema'] != STORM_SCHEMA or result['identity_sha256'] != _i17_identity(arrays, meta):
        raise ValueError('weather metadata/identity mismatch')
    _storm_headers(dict({key: (value.shape, value.dtype) for key, value in arrays.items()}, manifest=((1,), _i17_np.dtype('uint8'))))
    parameters = StormParameters(**meta['parameters'])
    origin = meta['origin_m_xz']
    if not isinstance(origin, list) or len(origin) != 2 or any((type(value) not in (int, float) or not _i17_math.isfinite(value) or abs(value) > 1000000000000.0 for value in origin)):
        raise ValueError('invalid saved absolute origin')
    for key, lower, upper in (('spacing_m', 0.0, 100000.0), ('dt_s', 0.0, 10000000.0), ('start_s', -1.0, 1000000000.0)):
        value = meta[key]
        if type(value) not in (int, float) or not _i17_math.isfinite(value) or (not lower < value <= upper):
            raise ValueError('invalid saved positive grid/time: ' + key)
    if meta['dt_s'] < 0.001 or meta['start_s'] < 0 or type(meta['spatial_subsamples']) is not int:
        raise ValueError('invalid saved timestep/subsampling')
    for key in ('source_identity', 'selection_identity'):
        if not isinstance(meta[key], str) or len(meta[key]) != 64:
            raise ValueError('invalid saved external identity')
    if meta['temporal_integration'] != 'analytic_gaussian_erfc_with_4point_gauss_small_displacement' or meta['spatial_integration'] != 'equal_area_midpoint_subcells_no_window_normalization' or meta['units'] != 'coordinates m; physical time s; rain mm/h; area m2' or (meta['status'] != 'parameterized_weather_scenario_not_forecast'):
        raise ValueError('weather semantic metadata mismatch')
    owner = arrays['cell_owner']
    rain = arrays['rain_mm_h']
    if meta['start_s'] + rain.shape[0] * meta['dt_s'] > 1000000000.0:
        raise ValueError('saved weather time range exceeded')
    if (owner < -1).any() or (owner >= rain.shape[1]).any() or (not (owner >= 0).any()):
        raise ValueError('invalid saved unique HRU ownership')
    counts = _i17_np.bincount(owner[owner >= 0], minlength=rain.shape[1])
    resources = storm_preflight(int(owner.size), int(counts.sum()), rain.shape[0], rain.shape[1], meta['spatial_subsamples'])
    if resources != meta['resources'] or (counts == 0).any() or (not _i17_np.array_equal(counts, arrays['counts'])):
        raise ValueError('weather area counts/resource certificate mismatch')
    if not _i17_np.array_equal(arrays['area_m2'], counts * meta['spacing_m'] ** 2):
        raise ValueError('weather unique area mismatch')
    if not _i17_np.array_equal(arrays['time_edges_s'], meta['start_s'] + _i17_np.arange(rain.shape[0] + 1) * meta['dt_s']):
        raise ValueError('weather physical time edges mismatch')
    if not _i17_np.isfinite(rain).all() or (rain < 0).any() or (rain > parameters.peak_mm_h + 1e-10).any():
        raise ValueError('invalid bounded saved weather rain')
    if cell_owner is not None and _i17__hash(owner) != _i17__hash(cell_owner):
        raise ValueError('external unique HRU ownership mismatch')
    if source_identity is not None and source_identity != meta['source_identity']:
        raise ValueError('external weather source mismatch')
    if selection_identity is not None and selection_identity != meta['selection_identity']:
        raise ValueError('external weather selection mismatch')
    return {'total_rain_m3': float((rain * arrays['area_m2']).sum() * meta['dt_s'] / 3600 / 1000), 'area_m2': float(arrays['area_m2'].sum()), 'max_rain_mm_h': float(rain.max())}

def save_forcing(path, result):
    from terrain_pipeline.common_infra import save_bundle as _i17_save_bundle
    _i17_save_bundle(path, result, validator=validate_forcing)

def storm_load_forcing(path, *, expected_sha256, cell_owner, source_identity, selection_identity):
    """Read saved forcing with external trust; never regenerate weather at load time."""
    from terrain_pipeline.common_infra import load_bundle as _i17_load_bundle
    return _i17_load_bundle(path, expected_sha256=expected_sha256, max_bytes=STORM_MAX_BYTES, header_validator=_storm_headers, validator=lambda result: validate_forcing(result, cell_owner=cell_owner, source_identity=source_identity, selection_identity=selection_identity))
REGIONAL_MAX_CELLS = 65536
REGIONAL_MAX_STEPS = 288
MAX_CELL_STEPS = 25000000
MAX_MEMORY_BYTES = 128 * 1024 * 1024
MAX_OUTPUT_BYTES = 512 * 1024 * 1024

def regional_preflight(cells, steps, block_cells, dt_s):
    if any((type(value) is not int for value in (cells, steps, block_cells))) or not 1 <= cells <= REGIONAL_MAX_CELLS or (not 1 <= steps <= REGIONAL_MAX_STEPS) or (not 1 <= block_cells <= 4096):
        raise ValueError('independent regional forcing dimensions exceeded')
    if not isinstance(dt_s, (int, float)) or isinstance(dt_s, bool) or (not _i18_np.isfinite(dt_s)) or (not 0 < dt_s <= 3600):
        raise ValueError('finite positive physical timestep required')
    work = cells * steps
    memory = 8 * cells * 24 + 8 * block_cells * 24
    output = 8 * cells * (steps + 6) + 65536
    if work > MAX_CELL_STEPS or memory > MAX_MEMORY_BYTES or output > MAX_OUTPUT_BYTES:
        raise ValueError('independent regional forcing work/bytes exceeded')
    return {'cell_steps': work, 'estimated_memory_bytes': memory, 'estimated_uncompressed_output_bytes': output, 'max_cell_steps': MAX_CELL_STEPS, 'max_memory_bytes': MAX_MEMORY_BYTES, 'max_output_bytes': MAX_OUTPUT_BYTES}

def advance_soil(rain_mm_h, states, *, dt_s, parameters, return_fluxes=False):
    from terrain_pipeline.runoff import RunoffParameters as _i18_RunoffParameters
    from terrain_pipeline.runoff import _release as _i18__release
    if not isinstance(parameters, _i18_RunoffParameters):
        raise ValueError('explicit runoff parameters required')
    parameters.__post_init__()
    if not isinstance(states, _i18_np.ndarray) or states.ndim != 2 or states.shape[0] != 3 or (states.dtype != _i18_np.float64) or (not _i18_np.isfinite(states).all()) or (states < 0).any():
        raise ValueError('soil/fast/slow finite nonnegative current states required')
    rain = _i18_np.asarray(rain_mm_h)
    if rain.shape != (states.shape[1],) or not _i18_np.isfinite(rain).all() or (rain < 0).any() or (rain > 1000).any():
        raise ValueError('bounded unique-cell rainfall required')
    if (states[0] > parameters.soil_capacity_mm).any():
        raise ValueError('soil above prescribed capacity')
    if isinstance(dt_s, bool) or not isinstance(dt_s, (int, float)) or (not _i18_np.isfinite(dt_s)) or (not 0 < dt_s <= 3600):
        raise ValueError('positive timestep required')
    hours = dt_s / 3600.0
    soil_before, fast_before, slow_before = states
    depth = rain * hours
    infiltration = _i18_np.minimum(_i18_np.minimum(depth, parameters.infiltration_capacity_mm_h * hours), _i18_np.maximum(parameters.soil_capacity_mm - soil_before, 0))
    soil = soil_before + infiltration
    et = _i18_np.minimum(soil, parameters.potential_et_mm_h * hours)
    soil -= et
    percolation = _i18_np.minimum(soil, parameters.percolation_mm_h * hours)
    soil -= percolation
    fast, fast_release = _i18__release(fast_before, depth - infiltration, dt_s, parameters.fast_tau_s)
    slow, slow_release = _i18__release(slow_before, percolation, dt_s, parameters.slow_tau_s)
    next_states = _i18_np.stack((soil, fast, slow))
    release = fast_release + slow_release
    change = (next_states - states).sum(axis=0)
    if _i18_np.abs(depth - et - release - change).max() > 1e-10:
        raise ValueError('cell-local rain/soil/release balance failed')
    result = (next_states, release, et, change)
    if return_fluxes:
        return result + ({'infiltration_mm': infiltration, 'percolation_mm': percolation, 'fast_release_mm': fast_release, 'slow_release_mm': slow_release, 'excess_mm': depth - infiltration},)
    return result

def regional_generate_forcing(source, destination, *, steps=288, dt_s=900.0, parameters=None, storm=None, block_cells=4096):
    from terrain_pipeline.runoff import RunoffParameters as _i18_RunoffParameters
    from terrain_pipeline.common_infra import file_sha256 as _i18_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i18_publish_bytes
    from terrain_pipeline.regional_surface_source import validate_source as _i18_validate_source
    _i18_validate_source(source)
    destination = _i18_Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    parameters = _i18_RunoffParameters() if parameters is None else parameters
    parameters.__post_init__()
    resources = regional_preflight(65536, steps, block_cells, dt_s)
    meta = {'schema': 'regional-surface-forcing-v1', 'source_identity': source['identity_sha256'], 'steps': steps, 'dt_s': float(dt_s), 'shape': [256, 256], 'cell_area_m2': 900.0, 'parameters': _i18_asdict(parameters), 'storm': None if storm is None else _i18_asdict(storm), 'resources': resources, 'block_cells': block_cells, 'origin_m_xz': source['metadata']['origin_m_xz'], 'rain_support': 'all-grid conceptual terrestrial soil; includes temporarily wet/depression cells; no lake direct rain', 'B_input': 'runoff_volume_m3 exactly once; never add full rainfall again', 'trust': 'external trusted manifest SHA and payload SHA; balances are not resigned physical-model authentication', 'coordinates': 'origin+index*30m cell centers; footprint center +/-15m', 'surface_initial_storage_m3': 0.0}
    _i18_publish_bytes(destination / 'predeclared.json', _i18_json.dumps(meta, allow_nan=False, indent=2).encode())
    descriptor, temporary = _i18_tempfile.mkstemp(dir=destination, prefix='.forcing-', suffix='.npy')
    _i18_os.close(descriptor)
    output = None
    try:
        output = _i18_np.lib.format.open_memmap(temporary, mode='w+', dtype=_i18_np.float64, shape=(steps, 256, 256))
        states = _i18_np.tile(_i18_np.array([parameters.initial_soil_mm, parameters.initial_fast_mm, parameters.initial_slow_mm])[:, None], (1, 65536))
        initial = states.copy()
        flat = _i18_np.arange(65536)
        origin = meta['origin_m_xz']
        east = origin[0] + flat % 256 * 30.0
        south = origin[1] + flat // 256 * 30.0
        ledger = {key: [] for key in ('rain_m3', 'et_m3', 'runoff_m3', 'storage_change_m3', 'residual_m3')}
        storage = [float(states.sum() * 0.9)]
        soil_storage = [float(states[0].sum() * 0.9)]
        maximum = 0.0
        for step in range(steps):
            totals = _i18_np.zeros(5)
            for lower in range(0, 65536, block_cells):
                upper = min(lower + block_cells, 65536)
                rain = _i18_np.zeros(upper - lower) if storm is None else interval_mean_mm_h(east[lower:upper], south[lower:upper], float(step * dt_s), float((step + 1) * dt_s), storm)
                updated, release, et, change = advance_soil(rain, states[:, lower:upper], dt_s=dt_s, parameters=parameters)
                states[:, lower:upper] = updated
                runoff = release * 0.9
                rain_volume = rain * dt_s / 3600.0 * 0.9
                residual = rain_volume - et * 0.9 - runoff - change * 0.9
                maximum = max(maximum, float(_i18_np.abs(residual).max()))
                output[step].ravel()[lower:upper] = runoff
                totals += _i18_np.array([rain_volume.sum(), et.sum() * 0.9, runoff.sum(), change.sum() * 0.9, residual.sum()])
            for key, value in zip(ledger, totals):
                ledger[key].append(float(value))
            storage.append(float(states.sum() * 0.9))
            soil_storage.append(float(states[0].sum() * 0.9))
            output.flush()
            output._mmap.close()
            output = _i18_np.lib.format.open_memmap(temporary, mode='r+', dtype=_i18_np.float64, shape=(steps, 256, 256))
        output._mmap.close()
        output = None
        _i18_os.link(temporary, destination / 'runoff_volume_m3.npy')
        buffer = _i18_io.BytesIO()
        _i18_np.savez_compressed(buffer, initial_states_mm=initial.reshape(3, 256, 256), final_states_mm=states.reshape(3, 256, 256), seconds_edges=_i18_np.arange(steps + 1, dtype=_i18_np.float64) * dt_s)
        _i18_publish_bytes(destination / 'soil-final-and-time.npz', buffer.getvalue())
        report = {**meta, 'runoff_path': 'runoff_volume_m3.npy', 'runoff_sha256': _i18_file_sha256(destination / 'runoff_volume_m3.npy'), 'soil_time_path': 'soil-final-and-time.npz', 'soil_time_sha256': _i18_file_sha256(destination / 'soil-final-and-time.npz'), 'ledger': ledger, 'total_soil_fast_slow_storage_m3': storage, 'soil_storage_m3': soil_storage, 'max_cell_residual_m3': maximum, 'total_rain_m3': sum(ledger['rain_m3']), 'total_et_m3': sum(ledger['et_m3']), 'total_runoff_to_B_m3': sum(ledger['runoff_m3']), 'whole_account_residual_m3': sum(ledger['rain_m3']) - sum(ledger['et_m3']) - sum(ledger['runoff_m3']) - storage[-1] + storage[0]}
        _i18_publish_bytes(destination / 'manifest.json', _i18_json.dumps(report, allow_nan=False, indent=2).encode())
        return report
    except BaseException as error:
        _i18_publish_bytes(destination / 'failure.json', _i18_json.dumps({'type': type(error).__name__, 'message': str(error)}).encode())
        raise
    finally:
        if output is not None:
            output._mmap.close()
        if _i18_os.path.exists(temporary):
            _i18_os.unlink(temporary)

def soil_headers(headers, steps):
    if set(headers) != {'initial_states_mm', 'final_states_mm', 'seconds_edges'}:
        raise ValueError('exact soil/time members required')
    for key in ('initial_states_mm', 'final_states_mm'):
        if headers[key] != ((3, 256, 256), _i18_np.dtype(_i18_np.float64)):
            raise ValueError('typed soil header rejected')
    if headers['seconds_edges'] != ((steps + 1,), _i18_np.dtype(_i18_np.float64)):
        raise ValueError('typed time header rejected')

def regional_load_forcing(directory, *, expected_manifest_sha256, source_identity):
    from terrain_pipeline.runoff import RunoffParameters as _i18_RunoffParameters
    from terrain_pipeline.common_infra import checked_archive as _i18_checked_archive
    from terrain_pipeline.common_infra import file_sha256 as _i18_file_sha256
    directory = _i18_Path(directory)
    manifest = directory / 'manifest.json'
    if manifest.stat().st_size > 262144 or _i18_file_sha256(manifest) != expected_manifest_sha256:
        raise ValueError('external trusted manifest SHA/budget required')
    from terrain_pipeline.runoff import _strict_json as _strict_json
    meta = _strict_json(manifest.read_text(encoding='utf-8'))
    keys = {'schema', 'source_identity', 'steps', 'dt_s', 'shape', 'cell_area_m2', 'parameters', 'storm', 'resources', 'block_cells', 'origin_m_xz', 'rain_support', 'B_input', 'trust', 'coordinates', 'surface_initial_storage_m3', 'runoff_path', 'runoff_sha256', 'soil_time_path', 'soil_time_sha256', 'ledger', 'total_soil_fast_slow_storage_m3', 'soil_storage_m3', 'max_cell_residual_m3', 'total_rain_m3', 'total_et_m3', 'total_runoff_to_B_m3', 'whole_account_residual_m3'}
    if set(meta) != keys or meta['schema'] != 'regional-surface-forcing-v1' or meta['source_identity'] != source_identity:
        raise ValueError('forcing schema/source binding mismatch')
    if meta['resources'] != regional_preflight(65536, meta['steps'], meta['block_cells'], meta['dt_s']) or meta['shape'] != [256, 256] or meta['cell_area_m2'] != 900.0:
        raise ValueError('full-grid resource metadata mismatch')
    if len(meta['origin_m_xz']) != 2 or not _i18_np.isfinite(meta['origin_m_xz']).all():
        raise ValueError('finite origin required')
    if meta['origin_m_xz'] != [-184320.0, 61440.0] or meta['surface_initial_storage_m3'] != 0.0:
        raise ValueError('fixed source origin and initial surface contract required')
    for key, value in {'rain_support': 'all-grid conceptual terrestrial soil; includes temporarily wet/depression cells; no lake direct rain', 'B_input': 'runoff_volume_m3 exactly once; never add full rainfall again', 'trust': 'external trusted manifest SHA and payload SHA; balances are not resigned physical-model authentication', 'coordinates': 'origin+index*30m cell centers; footprint center +/-15m'}.items():
        if meta[key] != value:
            raise ValueError('forcing water support/semantics mismatch')
    if meta['storm'] is not None:
        pass  # Reference the existing consolidated global directly.
        StormParameters(**meta['storm'])
    parameters = _i18_RunoffParameters(**meta['parameters'])
    if meta['runoff_path'] != 'runoff_volume_m3.npy' or meta['soil_time_path'] != 'soil-final-and-time.npz':
        raise ValueError('fixed safe basenames required')
    path = directory / meta['runoff_path']
    if path.stat().st_size > MAX_OUTPUT_BYTES or _i18_file_sha256(path) != meta['runoff_sha256']:
        raise ValueError('runoff payload SHA mismatch')
    with open(path, 'rb') as stream:
        if _i18_np.lib.format.read_magic(stream) != (1, 0):
            raise ValueError('fixed NPY v1 required')
        shape, fortran, dtype = _i18_np.lib.format.read_array_header_1_0(stream, max_header_size=4096)
        if shape != (meta['steps'], 256, 256) or fortran or dtype != _i18_np.float64 or (stream.tell() + int(_i18_np.prod(shape)) * 8 != path.stat().st_size):
            raise ValueError('typed NPY rejected before np.load')
    soil = _i18_checked_archive(directory / meta['soil_time_path'], expected_sha256=meta['soil_time_sha256'], max_bytes=4 * 1024 * 1024, header_validator=lambda h: soil_headers(h, meta['steps']))
    if not _i18_np.array_equal(soil['seconds_edges'], _i18_np.arange(meta['steps'] + 1) * meta['dt_s']):
        raise ValueError('exact T+1 time edges required')
    initial = _i18_np.array([parameters.initial_soil_mm, parameters.initial_fast_mm, parameters.initial_slow_mm])[:, None, None]
    if not _i18_np.array_equal(soil['initial_states_mm'], _i18_np.broadcast_to(initial, (3, 256, 256))):
        raise ValueError('initial state must equal parameters')
    for key in ('initial_states_mm', 'final_states_mm'):
        if not _i18_np.isfinite(soil[key]).all() or (soil[key] < 0).any():
            raise ValueError('finite nonnegative soil required')
        soil[key].flags.writeable = False
    ledger = meta['ledger']
    if set(ledger) != {'rain_m3', 'et_m3', 'runoff_m3', 'storage_change_m3', 'residual_m3'}:
        raise ValueError('known T ledger columns required')
    for key, values in ledger.items():
        if len(values) != meta['steps'] or not _i18_np.isfinite(values).all() or (key in {'rain_m3', 'et_m3', 'runoff_m3'} and min(values) < 0):
            raise ValueError('finite T ledger required')
    storage = _i18_np.asarray(meta['total_soil_fast_slow_storage_m3'])
    soil_storage = _i18_np.asarray(meta['soil_storage_m3'])
    if storage.shape != (meta['steps'] + 1,) or soil_storage.shape != storage.shape or (not _i18_np.isfinite(storage).all()) or (not _i18_np.isfinite(soil_storage).all()):
        raise ValueError('finite T+1 storage required')
    if (storage < 0).any() or (soil_storage < 0).any() or (soil_storage > storage + 1e-07).any():
        raise ValueError('nonnegative consistent soil/component storage required')
    if not _i18_np.allclose(_i18_np.diff(storage), ledger['storage_change_m3'], rtol=0, atol=1e-06):
        raise ValueError('storage recurrence fails')
    residual = _i18_np.asarray(ledger['rain_m3']) - ledger['et_m3'] - _i18_np.asarray(ledger['runoff_m3']) - _i18_np.diff(storage)
    if _i18_np.abs(residual).max() > 1e-06 or not _i18_np.allclose(residual, ledger['residual_m3'], rtol=0, atol=1e-06):
        raise ValueError('regional water account fails')
    if not _i18_np.allclose([storage[0], storage[-1]], [soil['initial_states_mm'].sum() * 0.9, soil['final_states_mm'].sum() * 0.9], rtol=0, atol=1e-06):
        raise ValueError('initial/final storage mismatch')
    for column, total in (('rain_m3', 'total_rain_m3'), ('et_m3', 'total_et_m3'), ('runoff_m3', 'total_runoff_to_B_m3')):
        if not _i18_np.isclose(sum(ledger[column]), meta[total], rtol=0, atol=1e-07):
            raise ValueError('manifest total ledger mismatch')
    whole = sum(ledger['rain_m3']) - sum(ledger['et_m3']) - sum(ledger['runoff_m3']) - storage[-1] + storage[0]
    if not _i18_np.isfinite(meta['whole_account_residual_m3']) or not _i18_np.isclose(whole, meta['whole_account_residual_m3'], rtol=0, atol=1e-07) or (not _i18_np.isfinite(meta['max_cell_residual_m3'])) or (not 0 <= meta['max_cell_residual_m3'] <= 1e-09):
        raise ValueError('finite cumulative account summary required')
    runoff = _i18_np.load(path, allow_pickle=False, mmap_mode='r')
    try:
        for step in range(meta['steps']):
            if not _i18_np.isfinite(runoff[step]).all() or (runoff[step] < 0).any() or (not _i18_np.isclose(runoff[step].sum(), ledger['runoff_m3'][step], rtol=0, atol=1e-07)):
                raise ValueError('saved grid runoff ledger mismatch')
            if (step + 1) % 16 == 0:
                runoff._mmap.close()
                runoff = _i18_np.load(path, allow_pickle=False, mmap_mode='r')
        runoff._mmap.close()
        runoff = _i18_np.load(path, allow_pickle=False, mmap_mode='r')
    except BaseException:
        runoff._mmap.close()
        raise
    return {'metadata': meta, 'runoff_volume_m3': runoff, 'seconds_edges': soil['seconds_edges'], 'initial_states_mm': soil['initial_states_mm'], 'final_states_mm': soil['final_states_mm']}

def iter_intervals(directory, *, expected_manifest_sha256, source_identity):
    loaded = regional_load_forcing(directory, expected_manifest_sha256=expected_manifest_sha256, source_identity=source_identity)
    try:
        for index, values in enumerate(loaded['runoff_volume_m3']):
            yield (index, values)
    finally:
        loaded['runoff_volume_m3']._mmap.close()
CLIMATE_TRANSPORT_SCHEMA = 'climate-transport-v1'
MODEL = 'explicit_finite_volume_constant_axial_vapour_v1'
WATER_DENSITY_KG_M3 = 1000.0
CELL_SPACING_M = 30.0
CELL_AREA_M2 = CELL_SPACING_M ** 2
LEDGER_RTOL = 1e-09
EXPLICIT_ZERO = 'explicit_zero'
CLOSED_NO_FLUX = 'closed_no_flux'
OPEN_BOUNDARY = 'open_boundary'
UNRESOLVED = 'unresolved'
AXIAL_STEPS = {(1, 0): 'east', (-1, 0): 'west', (0, 1): 'south', (0, -1): 'north'}
CLIMATE_TRANSPORT_DECLARED_LIMITS = ('bounded single-domain explicit finite volume on a constant axial wind; not a global atmospheric model and not a continuous wind or pressure field', 'vapour inventory is a per-cell mass in kg; depth is only a reporting conversion', 'the time layer is a DAG and a recirculating wind field is supported; only a synchronous dependency cycle is refused', 'precipitation cannot exceed the vapour present; that is the only depletion constraint, and background condensation is drawn from the same inventory', 'undeclared inflow is never treated as zero; only explicit zero and a declared closed wall are legitimate zeros', 'recycled evapotranspiration is an external declared input; this module never computes ET itself')

def depth_mm(mass_kg):
    """Report a per-cell mass as an equivalent water depth in mm.

    This is the **only** place area and density appear together, and it is a
    reporting conversion: `mm = kg / A_cell / ρ × 1000`.
    """
    return _i19_np.asarray(mass_kg, _i19_np.float64) / CELL_AREA_M2 / WATER_DENSITY_KG_M3 * 1000.0

def et_volume_to_mass_kg(et_m3):
    """Convert an ET volume in m³ per interval to a mass in kg.

    Multiply by density **only**: the inventory is a per-cell kg mass, so dividing
    by area would give `kg/m²`, a different quantity.
    """
    volume = _i19_np.asarray(et_m3, _i19_np.float64)
    if not _i19_np.isfinite(volume).all() or _i19_np.any(volume < 0.0):
        raise ValueError('finite nonnegative ET volumes required')
    return volume * WATER_DENSITY_KG_M3

def _validate_axial(wind_bearing):
    pair = (int(wind_bearing[0]), int(wind_bearing[1]))
    if pair not in AXIAL_STEPS:
        raise ValueError('wind_bearing must be one of the axial pairs %r; this limited solver does not accept a continuous or diagonal wind' % (sorted(AXIAL_STEPS),))
    return pair

def _validate_speed(wind_speed_m_s, dt_s):
    if isinstance(wind_speed_m_s, bool) or not isinstance(wind_speed_m_s, (int, float, _i19_np.floating)):
        raise ValueError('wind_speed_m_s must be a finite nonnegative number')
    speed = float(wind_speed_m_s)
    if not _i19_math.isfinite(speed) or speed < 0.0:
        raise ValueError('wind_speed_m_s must be a finite nonnegative number')
    cfl = speed * float(dt_s) / CELL_SPACING_M
    if cfl > 1.0 + 1e-12:
        raise ValueError('CFL %.6f exceeds 1 at wind_speed %.3f m/s, dt %.3f s, dx %.1f m; the step is refused rather than silently reduced' % (cfl, speed, float(dt_s), CELL_SPACING_M))
    return (speed, cfl)

def _upwind_partner(wind_bearing, shape):
    """Index of each cell's upwind neighbour, plus the mask of upstream-inflow cells.

    `partner` holds the flat index of the cell the wind comes *from*; cells with no
    upwind neighbour inside the domain are marked in `is_inflow`, meaning they draw
    from the declared upstream boundary rather than from a neighbour.
    """
    rows, columns = shape
    step_x, step_z = wind_bearing
    row = _i19_np.arange(rows)[:, None]
    column = _i19_np.arange(columns)[None, :]
    from_row = row - step_z
    from_column = column - step_x
    inside = (from_row >= 0) & (from_row < rows) & (from_column >= 0) & (from_column < columns)
    partner = _i19_np.where(inside, from_row * columns + from_column, -1).astype(_i19_np.int64)
    return (partner.reshape(-1), ~inside.reshape(-1))

def _boundary_declaration(shape, wind_bearing, boundary):
    """Resolve each upstream-inflow cell's boundary status without inventing zeros.

    `boundary` maps a side name (`north`/`south`/`east`/`west`) to one of
    ``EXPLICIT_ZERO``, ``CLOSED_NO_FLUX``, ``UNRESOLVED`` or a numeric influx in
    kg/interval. A side that is simply absent is **pending**, never zero.
    """
    if boundary is None:
        boundary = {}
    if not isinstance(boundary, dict):
        raise ValueError('boundary must be a mapping of side name to declaration')
    allowed = {'north', 'south', 'east', 'west'}
    unknown = sorted(set(boundary) - allowed)
    if unknown:
        raise ValueError('unsupported boundary sides %r; expected a subset of %r' % (unknown, sorted(allowed)))
    upstream_side = {(1, 0): 'west', (-1, 0): 'east', (0, 1): 'north', (0, -1): 'south'}[wind_bearing]
    partner, _is_inflow = _upwind_partner(wind_bearing, shape)
    declaration = boundary.get(upstream_side, 'pending')
    return (upstream_side, declaration, partner)

def _downwind_exit_mask(wind_bearing, shape):
    """Cells whose downwind neighbour lies outside the domain, i.e. true outflow.

    Distinct from the *upstream* inflow mask: with an eastward wind the mass leaves
    through the last column and enters through the first, and confusing the two
    silently drops the outflow term from the ledger.
    """
    rows, columns = shape
    step_x, step_z = wind_bearing
    row = _i19_np.arange(rows)[:, None]
    column = _i19_np.arange(columns)[None, :]
    to_row = row + step_z
    to_column = column + step_x
    inside = (to_row >= 0) & (to_row < rows) & (to_column >= 0) & (to_column < columns)
    return ~inside.reshape(-1)

def climate_transport_step(vapour_kg, *, wind_bearing, wind_speed_m_s, dt_s, uplift_gain, gradient, inflow_kg=None, recycle_kg=None, boundary=None):
    """Advance one bounded explicit finite-volume step.

    Parameters
    ----------
    vapour_kg : array_like
        Per-cell vapour mass in **kg**, `(rows, columns)`. This is the sole state.
    wind_bearing : (int, int)
        Axial direction the air moves toward; a member of `AXIAL_STEPS`.
    wind_speed_m_s : float
        Face speed in m/s. CFL is `speed·dt/dx`, refused above 1.
    dt_s : float
        Physical step in seconds.
    uplift_gain : float
        Coefficient `k` in `P = k·max(gradient,0)·V·dt`.
    gradient : array_like
        Dimensionless upslope gradient per cell (positive on windward slopes).
    inflow_kg : array_like or None
        Per-cell boundary influx in **kg per interval** for cells that draw from
        upstream of the domain. Shape `(n_inflow_cells,)` or the full grid.
    recycle_kg : array_like or None
        Per-cell recycled ET in **kg per interval**. Convert a volume with
        `et_volume_to_mass_kg`.
    boundary : dict or None
        Side declarations, see `_boundary_declaration`. Missing side means pending.

    Returns
    -------
    dict with the new state, per-step fluxes, the five-term ledger and the boundary
    status. A `conserved` flag is only true when every term is resolved.
    """
    state = _i19_np.asarray(vapour_kg, _i19_np.float64)
    if state.ndim != 2 or state.size == 0:
        raise ValueError('vapour_kg must be a nonempty 2-D per-cell mass')
    if not _i19_np.isfinite(state).all() or _i19_np.any(state < 0.0):
        raise ValueError('finite nonnegative per-cell vapour mass required')
    if isinstance(dt_s, bool) or not isinstance(dt_s, (int, float, _i19_np.floating)):
        raise ValueError('dt_s must be a finite positive number')
    dt_s = float(dt_s)
    if not _i19_math.isfinite(dt_s) or dt_s <= 0.0:
        raise ValueError('dt_s must be a finite positive number')
    direction = _validate_axial(wind_bearing)
    speed, cfl = _validate_speed(wind_speed_m_s, dt_s)
    gain = float(uplift_gain)
    if not _i19_math.isfinite(gain) or gain < 0.0:
        raise ValueError('uplift_gain must be a finite nonnegative number')
    upslope = _i19_np.asarray(gradient, _i19_np.float64)
    if upslope.shape != state.shape or not _i19_np.isfinite(upslope).all():
        raise ValueError('gradient must be a finite array matching the vapour grid')
    shape = state.shape
    upstream_side, declaration, partner = _boundary_declaration(shape, direction, boundary)
    if inflow_kg is not None and declaration == 'pending':
        declaration = 'declared_influx'
    flat = state.reshape(-1)
    has_partner = partner >= 0
    inflow_cells = ~has_partner
    if speed > 0.0:
        shared_kg = speed * flat * dt_s / CELL_SPACING_M
    else:
        shared_kg = _i19_np.zeros(flat.size, _i19_np.float64)
    after_transport = flat - shared_kg + _i19_np.where(has_partner, shared_kg[_i19_np.where(has_partner, partner, 0)], 0.0)
    exit_cells = _downwind_exit_mask(direction, shape)
    downstream_outflow_kg = float(shared_kg[exit_cells].sum())
    inflow_status = _i19_np.full(flat.size, '', dtype=object)
    certified = True
    inflow_mass_kg = _i19_np.zeros(flat.size, _i19_np.float64)
    if inflow_cells.any():
        count = int(inflow_cells.sum())
        if inflow_kg is not None:
            supplied = _i19_np.asarray(inflow_kg, _i19_np.float64)
            if supplied.size == count:
                supplied = supplied.reshape(-1)
            elif supplied.size == flat.size:
                supplied = supplied.reshape(-1)[inflow_cells]
            else:
                raise ValueError('inflow_kg must supply one value per upstream-inflow cell (%d) or the full grid' % (count,))
            if not _i19_np.isfinite(supplied).all() or _i19_np.any(supplied < 0.0):
                raise ValueError('finite nonnegative inflow masses required')
            inflow_mass_kg[inflow_cells] = supplied
            inflow_status[inflow_cells] = 'declared_influx'
        elif isinstance(declaration, str):
            if declaration == EXPLICIT_ZERO:
                inflow_status[inflow_cells] = EXPLICIT_ZERO
            elif declaration == CLOSED_NO_FLUX:
                inflow_status[inflow_cells] = CLOSED_NO_FLUX
            elif declaration == UNRESOLVED:
                inflow_status[inflow_cells] = UNRESOLVED
                certified = False
            elif declaration == 'pending':
                raise ValueError('upstream boundary %r is unresolved: supply an explicit zero, a closed no-flux declaration, or an influx; an undeclared inflow is never treated as zero' % (upstream_side,))
            elif declaration == 'declared_influx':
                raise ValueError('inflow_kg was declared as a side but no per-cell mass array was supplied; pass inflow_kg or use an explicit zero/closed side')
            else:
                raise ValueError('unknown boundary declaration %r' % (declaration,))
        after_transport = after_transport + inflow_mass_kg
    recycle = _i19_np.zeros(flat.size, _i19_np.float64) if recycle_kg is None else _i19_np.asarray(recycle_kg, _i19_np.float64).reshape(-1)
    if recycle.size != flat.size:
        raise ValueError('recycle_kg must match the vapour grid')
    if not _i19_np.isfinite(recycle).all() or _i19_np.any(recycle < 0.0):
        raise ValueError('finite nonnegative recycled masses required')
    after_recycle = after_transport + recycle
    available = _i19_np.maximum(after_recycle, 0.0)
    potential = gain * _i19_np.maximum(upslope.reshape(-1), 0.0) * available * dt_s
    precipitation = _i19_np.minimum(potential, available)
    new_state = available - precipitation
    ledger = {'inflow_kg': float(inflow_mass_kg.sum()), 'recycle_kg': float(recycle.sum()), 'precipitation_kg': float(precipitation.sum()), 'outflow_kg': downstream_outflow_kg, 'nondepositing_kg': 0.0, 'storage_change_kg': float(new_state.sum() - flat.sum())}
    expected_change = ledger['inflow_kg'] + ledger['recycle_kg'] - ledger['precipitation_kg'] - ledger['outflow_kg'] - ledger['nondepositing_kg']
    scale = max(abs(ledger['inflow_kg']) + abs(ledger['recycle_kg']), abs(ledger['precipitation_kg']), abs(ledger['outflow_kg']), 1.0)
    ledger['closure_residual_kg'] = ledger['storage_change_kg'] - expected_change
    ledger['closure_tolerance_kg'] = LEDGER_RTOL * scale
    ledger['closure_ok'] = abs(ledger['closure_residual_kg']) <= ledger['closure_tolerance_kg']
    return {'schema': CLIMATE_TRANSPORT_SCHEMA, 'model': MODEL, 'vapour_kg': new_state.reshape(shape), 'precipitation_kg': precipitation.reshape(shape), 'recycle_kg': recycle.reshape(shape), 'inflow_kg': inflow_mass_kg.reshape(shape), 'ledger': ledger, 'boundary': {'upstream_side': upstream_side, 'declaration': declaration if isinstance(declaration, str) else 'declared_influx', 'certified': bool(certified), 'status_per_inflow_cell': inflow_status.tolist()}, 'diagnostics': {'wind_bearing': list(direction), 'wind_speed_m_s': speed, 'cfl': cfl, 'dt_s': dt_s, 'cell_spacing_m': CELL_SPACING_M, 'cell_area_m2': CELL_AREA_M2, 'uplift_gain': gain, 'shared_face_count': int(has_partner.sum()), 'units': 'per-cell mass in kg; depths only via depth_mm()'}, 'declared_limits': list(CLIMATE_TRANSPORT_DECLARED_LIMITS)}

def identity_of(result):
    """Digest of the state and the declared inputs actually used.

    Binds the realised per-cell masses, not just the arguments, so two runs that
    differ only in their result cannot share an identity.
    """
    diagnostics = result['diagnostics']
    record = {'schema': result['schema'], 'model': result['model'], 'wind_bearing': diagnostics['wind_bearing'], 'wind_speed_m_s': diagnostics['wind_speed_m_s'], 'dt_s': diagnostics['dt_s'], 'uplift_gain': diagnostics['uplift_gain'], 'boundary': {key: value for key, value in result['boundary'].items() if key != 'status_per_inflow_cell'}, 'arrays': {'vapour_kg': _i19_hashlib.sha256(_i19_np.ascontiguousarray(result['vapour_kg'], _i19_np.float64).tobytes()).hexdigest(), 'precipitation_kg': _i19_hashlib.sha256(_i19_np.ascontiguousarray(result['precipitation_kg'], _i19_np.float64).tobytes()).hexdigest()}}
    import json
    return _i19_hashlib.sha256(json.dumps(record, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
TEMPERATURE_OFFSET_C = 12.0
TEMPERATURE_SPAN_C = 45.0
PRECIPITATION_SPAN_MM = 2200.0
TEMPERATURE_LOW = 0.28
RAIN_DRY = 0.34
RAIN_WET = 0.64
VARIANT_COLD = 0
VARIANT_DRY = 1
VARIANT_TEMPERATE = 2
VARIANT_WET = 3
VARIANT_COUNT = 4
INSELBERG = 0
RIFT = 1
KARST = 2
PILLARS = 3
LANDFORM_COUNT = 4
LANDFORM_ORDINALS = {'inselberg': INSELBERG, 'rift': RIFT, 'karst': KARST, 'pillars': PILLARS}
LANDFORM_NAMES = ('inselberg', 'rift', 'karst', 'pillars')
VARIANT_NAMES = ('snowy', 'arid', 'temperate', 'humid')
BIOME_PALETTE = ('inselberg_snowy', 'inselberg_arid', 'inselberg_temperate', 'inselberg_humid', 'rift_snowy', 'rift_arid', 'rift_temperate', 'rift_humid', 'karst_snowy', 'karst_arid', 'karst_temperate', 'karst_humid', 'pillars_snowy', 'pillars_arid', 'pillars_temperate', 'pillars_humid')
PALETTE_SIZE = 16
assert LANDFORM_COUNT * VARIANT_COUNT == PALETTE_SIZE, 'four climates for each of four landforms'
assert len(BIOME_PALETTE) == PALETTE_SIZE, 'Expected 16 climate/landform biomes'

def _broadcast_pair(first, second):
    """Put two climate arguments on one common float64 grid (single code path)."""
    try:
        return _i21_np.broadcast_arrays(_i21_np.asarray(first, _i21_np.float64), _i21_np.asarray(second, _i21_np.float64))
    except ValueError:
        raise ValueError('the two climate arguments must broadcast to a common shape')

def variant(temperature, rain):
    """§1.1 / §4 item 1: the climate band of one normalized `(temperature, rain)`.

    Literally equivalent to `Landscape.java:8`
    (`temperature<.28?0:rain<.34?1:rain>.64?3:2`), keeping the Java comparison
    order and all three of its boundary behaviours: the temperature band vetoes
    (`(.1, .9)` is 0, never 3), `.34 <= rain <= .64` is 2, and the three
    comparisons are strict, so `temperature == .28` is not 0 while `rain == .34`
    and `rain == .64` are 2.

    The method is the Java ternary chain read as an assignment sequence: start at
    the `else` value 2, let `rain < .34` set 1, let `rain > .64` set 3, and let
    `temperature < .28` overwrite the result with 0 last, which is exactly the
    veto the Java expression performs by testing temperature first.

    Both arguments accept scalars or numpy arrays and broadcast onto a common
    grid; a 0-d query returns an `int64` scalar, an array query an `int64` array.
    Non-finite input is not rejected, so `NaN` lands in band 2 exactly as Java's
    comparisons would (declared in the module docstring).
    """
    t, r = _broadcast_pair(temperature, rain)
    band = _i21_np.full(t.shape, VARIANT_TEMPERATE, _i21_np.int64)
    band = _i21_np.where(r < RAIN_DRY, VARIANT_DRY, band)
    band = _i21_np.where(r > RAIN_WET, VARIANT_WET, band)
    band = _i21_np.where(t < TEMPERATURE_LOW, VARIANT_COLD, band)
    return band[()] if band.ndim == 0 else band

def climate_coordinates(BIO1_c, BIO12_mm):
    """§2.1 / §4 item 4: normalized `(temperature, rain)` from BIO1 and BIO12.

        temperature = clip((BIO1_c + 12) / 45, 0., 1.)
        rain        = clip( BIO12_mm     / 2200, 0., 1.)

    The three constants are the module-level ones above, which are the live Java
    adapter numbers (`DiffusionTerrainSource.java:18`), and `clip` mirrors
    `Noise.clamp` (`Noise.java:16`). Both ends of the clip are reachable: every
    `BIO1 <= -12 C` gives `0.` and every `BIO1 >= 33 C` gives `1.`, likewise for
    BIO12 at `0.` / `2200 mm` and above.

    Neither returned number is a physical quantity — together they are a
    normalized biome-selection coordinate (module docstring, contract §3.1).
    Scalars or arrays are accepted on one path: a 0-d query returns a pair of
    Python floats, an array query a pair of `float64` arrays. The §3.3 saturation
    seam above 2200 mm is documented, not hidden.
    """
    t, p = _broadcast_pair(BIO1_c, BIO12_mm)
    temperature = _i21_np.clip((t + TEMPERATURE_OFFSET_C) / TEMPERATURE_SPAN_C, 0.0, 1.0)
    rain = _i21_np.clip(p / PRECIPITATION_SPAN_MM, 0.0, 1.0)
    if temperature.ndim == 0:
        return (float(temperature), float(rain))
    return (temperature, rain)

def _integer_index(value, name, upper):
    """Validate one integer index argument and return it as an `int64` array.

    Integer dtype is required (a float index would silently truncate) and the
    value must already be inside `0..upper`: out of range raises instead of being
    clamped, the same way Java's `palette.get(...)` throws and the 16-item
    assertion at `TerrainBiomeSource.java:20` guards the palette.
    """
    array = _i21_np.asarray(value)
    if array.dtype == _i21_np.bool_ or not _i21_np.issubdtype(array.dtype, _i21_np.integer):
        raise ValueError('integer %s required (got dtype %s)' % (name, array.dtype))
    if array.size and (array.min() < 0 or array.max() > upper):
        raise ValueError('%s outside the frozen 0..%d range' % (name, upper))
    return array.astype(_i21_np.int64)

def palette_index(landform_ordinal, variant):
    """§1.3 / §4 item 3: the palette index `landform_ordinal * 4 + variant`.

    `index` lies in `[0, 15]` (`PALETTE_SIZE` = 16 = 4 landforms x 4 variants) and
    indexes `BIOME_PALETTE`. Out-of-range input raises `ValueError` and is never
    clamped, matching the Java gate (`palette.get` throws, `TerrainBiomeSource.java:20`
    asserts 16 entries). Integer dtype is required for both arguments; scalars are
    validated directly, arrays elementwise, and the result is `int64` on both
    paths.

    The second parameter carries the contract's name and shadows this module's
    `variant()` function inside the body only, where it is used as a value.
    """
    ordinal = _integer_index(landform_ordinal, 'landform ordinal', LANDFORM_COUNT - 1)
    band = _integer_index(variant, 'variant', VARIANT_COUNT - 1)
    try:
        index = ordinal * VARIANT_COUNT + band
    except ValueError:
        raise ValueError('landform ordinal and variant must broadcast to a common shape')
    return index[()] if index.ndim == 0 else index
SPATIAL_FORCING_SCHEMA = 'metric-spatial-rain-v1'
SPATIAL_FORCING_MAX_BYTES = 1024 * 1024 * 1024
CALIBRATION = 'fixed_reference_mean_affine_then_bounded_clip; target_mean_not_guaranteed_if_clipped'

@_i22_dataclass(frozen=True)
class SpatialRainRecipe:
    seed: int = 20261002
    scales: tuple = ((3840.0, 0.55), (960.0, 0.3), (240.0, 0.15))
    amplitude: float = 0.35
    multiplier_min: float = 0.6
    multiplier_max: float = 1.4
    reference_origin_m_xz: tuple = (-184320.0, 61440.0)
    reference_spacing_m: float = 30.0
    reference_shape_zx: tuple = (1024, 1024)

    def __post_init__(self):
        if type(self.seed) is not int or not 0 <= self.seed < 2 ** 64:
            raise ValueError('seed must be uint64')
        if not isinstance(self.scales, (tuple, list)) or not 1 <= len(self.scales) <= 8:
            raise ValueError('one to eight noise scales required')
        weights = []
        for pair in self.scales:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError('scale is (spacing_m, weight)')
            spacing, weight = pair
            if type(spacing) not in (int, float) or type(weight) not in (int, float) or (not _i22_math.isfinite(spacing)) or (not _i22_math.isfinite(weight)) or (not 1.0 <= spacing <= 100000000.0) or (not 1e-12 <= weight <= 1.0):
                raise ValueError('invalid bounded noise scale/weight')
            weights.append(weight)
        if not _i22_math.isfinite(sum(weights)) or sum(weights) < 1e-12:
            raise ValueError('invalid total noise weight')
        if type(self.amplitude) not in (int, float) or not _i22_math.isfinite(self.amplitude) or (not 0.0 <= self.amplitude <= 0.9):
            raise ValueError('amplitude must be finite in [0,.9]')
        if any((type(value) not in (int, float) or not _i22_math.isfinite(value) for value in (self.multiplier_min, self.multiplier_max, self.reference_spacing_m))) or not 0.0 < self.multiplier_min <= 1.0 <= self.multiplier_max <= 2.0 or (not 1.0 <= self.reference_spacing_m <= 100000.0):
            raise ValueError('invalid positive multiplier bounds or reference spacing')
        if not isinstance(self.reference_origin_m_xz, (tuple, list)) or len(self.reference_origin_m_xz) != 2 or any((type(value) not in (int, float) or not _i22_math.isfinite(value) or abs(value) > 1000000000000.0 for value in self.reference_origin_m_xz)):
            raise ValueError('finite bounded reference origin required')
        shape = self.reference_shape_zx
        if not isinstance(shape, (tuple, list)) or len(shape) != 2 or any((type(value) is not int or not 1 <= value <= 1024 for value in shape)) or (shape[0] * shape[1] > 1024 * 1024):
            raise ValueError('bounded reference shape required')
        minimum_scale = min((pair[0] for pair in self.scales))
        limit = max((abs(value) for value in self.reference_origin_m_xz)) + max(shape) * self.reference_spacing_m
        if limit / minimum_scale > 2 ** 52:
            raise ValueError('noise coordinate precision budget exceeded')
        object.__setattr__(self, 'scales', tuple((tuple(pair) for pair in self.scales)))
        object.__setattr__(self, 'reference_origin_m_xz', tuple(self.reference_origin_m_xz))
        object.__setattr__(self, 'reference_shape_zx', tuple(self.reference_shape_zx))

def _noise(x0, z0, dx, dz, shape, recipe):
    z, x = _i22_np.indices(shape, dtype=_i22_np.float64)
    x = x0 + x * dx
    z = z0 + z * dz
    if not _i22_np.isfinite(x).all() or not _i22_np.isfinite(z).all():
        raise ValueError('nonfinite rain coordinates')
    minimum_scale = min((pair[0] for pair in recipe.scales))
    if max(_i22_np.max(_i22_np.abs(x)), _i22_np.max(_i22_np.abs(z))) / minimum_scale > 2 ** 52:
        raise ValueError('noise coordinate precision budget exceeded')
    return _i22_field(x, z, recipe.seed, 971, recipe.scales)

def build_spatial_forcing(terrain, time_seconds, base_storm_mm_h, recipe):
    from terrain_pipeline.common_infra import RainfallForcing as _i22_RainfallForcing
    from terrain_pipeline.common_infra import TerrainGrid as _i22_TerrainGrid
    from terrain_pipeline.common_infra import identity as _i22_identity
    from terrain_pipeline.common_infra import readonly as _i22_readonly
    if not isinstance(terrain, _i22_TerrainGrid) or not isinstance(recipe, SpatialRainRecipe):
        raise ValueError('TerrainGrid and SpatialRainRecipe required')
    times = _i22_np.asarray(time_seconds)
    base = _i22_np.asarray(base_storm_mm_h)
    if times.dtype != _i22_np.float64 or times.ndim != 1 or base.dtype != _i22_np.float64 or (base.ndim != 1) or (base.size != times.size - 1) or (not _i22_np.isfinite(base).all()) or _i22_np.any(base < 0.0) or _i22_np.any(base > 1000000.0):
        raise ValueError('float64 interval-average base storm required')
    if times.size < 2 or _i22_np.any(_i22_np.diff(times) != _i22_np.diff(times)[0]):
        raise ValueError('uniform physical forcing intervals required')
    reference = _noise(recipe.reference_origin_m_xz[0], recipe.reference_origin_m_xz[1], recipe.reference_spacing_m, recipe.reference_spacing_m, recipe.reference_shape_zx, recipe)
    reference_mean = float(_i22_np.mean(reference, dtype=_i22_np.float64))
    local_noise = _noise(terrain.x0_m, terrain.z0_m, terrain.dx_m, terrain.dz_m, terrain.valid_mask.shape, recipe)
    multiplier = _i22_np.clip(1.0 + recipe.amplitude * (local_noise - reference_mean) / (1.0 + abs(reference_mean)), recipe.multiplier_min, recipe.multiplier_max)
    multiplier = _i22_np.where(terrain.valid_mask, multiplier, 0.0)
    rain = base[:, None, None] * multiplier[None, :, :]
    if not _i22_np.isfinite(rain).all() or _i22_np.any(rain > 1000000.0):
        raise ValueError('spatial rain outside forcing bounds')
    record = _i22_asdict(recipe)
    recipe_hash = _i22_hashlib.sha256(_i22_json.dumps(record, sort_keys=True).encode('utf-8')).hexdigest()
    forcing = _i22_RainfallForcing(times.copy(), rain, source_id='spatial-rain-' + recipe_hash, source_sha256=recipe_hash)
    arrays = {'multiplier': _i22_readonly(multiplier), 'valid_mask': terrain.valid_mask, 'time_seconds': forcing.time_seconds, 'base_storm_mm_h': _i22_readonly(base), 'rain_mm_h': forcing.rain_mm_h}
    metadata = {'schema': SPATIAL_FORCING_SCHEMA, 'recipe': record, 'recipe_sha256': recipe_hash, 'terrain_identity_sha256': terrain.identity_sha256, 'forcing_identity_sha256': forcing.identity_sha256, 'target_origin_m_xz': [float(terrain.x0_m), float(terrain.z0_m)], 'target_spacing_m_xz': [float(terrain.dx_m), float(terrain.dz_m)], 'target_shape_zx': list(terrain.valid_mask.shape), 'noise_algorithm': 'diffusion.geographic_noise.field_absolute_metre_v1', 'reference_noise_mean': reference_mean, 'valid_multiplier_mean': float(_i22_np.mean(multiplier[terrain.valid_mask])), 'valid_multiplier_min': float(_i22_np.min(multiplier[terrain.valid_mask])), 'valid_multiplier_max': float(_i22_np.max(multiplier[terrain.valid_mask])), 'calibration': CALIBRATION, 'temporal_semantics': 'interval_average', 'hydraulic_ready': False}
    package = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i22_identity(arrays, metadata)}
    validate_spatial_forcing_package(package)
    return (forcing, package)

def validate_spatial_forcing_package(package):
    from terrain_pipeline.common_infra import RainfallForcing as _i22_RainfallForcing
    from terrain_pipeline.common_infra import identity as _i22_identity
    arrays, meta = (package['arrays'], package['metadata'])
    if set(arrays) != {'multiplier', 'valid_mask', 'time_seconds', 'base_storm_mm_h', 'rain_mm_h'} or set(meta) != {'schema', 'recipe', 'recipe_sha256', 'terrain_identity_sha256', 'forcing_identity_sha256', 'reference_noise_mean', 'valid_multiplier_mean', 'valid_multiplier_min', 'valid_multiplier_max', 'target_origin_m_xz', 'target_spacing_m_xz', 'target_shape_zx', 'noise_algorithm', 'calibration', 'temporal_semantics', 'hydraulic_ready'} or meta.get('schema') != SPATIAL_FORCING_SCHEMA or (meta.get('hydraulic_ready') is not False) or (meta.get('calibration') != CALIBRATION) or (meta.get('temporal_semantics') != 'interval_average') or (meta.get('noise_algorithm') != 'diffusion.geographic_noise.field_absolute_metre_v1') or (package['identity_sha256'] != _i22_identity(arrays, meta)):
        raise ValueError('spatial forcing identity/schema mismatch')
    for key in ('recipe_sha256', 'terrain_identity_sha256', 'forcing_identity_sha256'):
        value = meta[key]
        if not isinstance(value, str) or len(value) != 64 or any((char not in '0123456789abcdef' for char in value)):
            raise ValueError('invalid forcing identity: ' + key)
    reference_mean = meta['reference_noise_mean']
    if type(reference_mean) not in (int, float) or not _i22_math.isfinite(reference_mean) or (not -1.0 <= reference_mean <= 1.0):
        raise ValueError('invalid reference noise mean')
    recipe = SpatialRainRecipe(**meta['recipe'])
    expected_recipe_hash = _i22_hashlib.sha256(_i22_json.dumps(_i22_asdict(recipe), sort_keys=True).encode('utf-8')).hexdigest()
    if expected_recipe_hash != meta['recipe_sha256']:
        raise ValueError('spatial recipe identity mismatch')
    mask, multiplier = (arrays['valid_mask'], arrays['multiplier'])
    origin, spacing, shape = (meta[key] for key in ('target_origin_m_xz', 'target_spacing_m_xz', 'target_shape_zx'))
    if not isinstance(origin, list) or len(origin) != 2 or any((type(value) not in (int, float) or not _i22_math.isfinite(value) or abs(value) > 1000000000000.0 for value in origin)) or (not isinstance(spacing, list)) or (len(spacing) != 2) or any((type(value) not in (int, float) or not _i22_math.isfinite(value) or (not 0.0 < value <= 100000.0) for value in spacing)) or (not isinstance(shape, list)) or (len(shape) != 2) or any((type(value) is not int or value <= 0 for value in shape)) or (shape != list(mask.shape)):
        raise ValueError('invalid target coordinate metadata')
    if mask.dtype != bool or mask.ndim != 2 or multiplier.shape != mask.shape or (multiplier.dtype != _i22_np.float64) or (not mask.any()) or (not _i22_np.isfinite(multiplier).all()) or _i22_np.any(multiplier[~mask] != 0.0) or _i22_np.any(multiplier[mask] < recipe.multiplier_min) or _i22_np.any(multiplier[mask] > recipe.multiplier_max):
        raise ValueError('invalid saved rainfall multiplier')
    forcing = _i22_RainfallForcing(arrays['time_seconds'], arrays['rain_mm_h'], source_id='spatial-rain-' + expected_recipe_hash, source_sha256=expected_recipe_hash)
    if forcing.identity_sha256 != meta['forcing_identity_sha256']:
        raise ValueError('saved forcing identity mismatch')
    if _i22_np.any(forcing.interval_seconds != forcing.interval_seconds[0]):
        raise ValueError('uniform forcing intervals required')
    base = arrays['base_storm_mm_h']
    if base.dtype != _i22_np.float64 or base.shape != (forcing.rain_mm_h.shape[0],) or (not _i22_np.isfinite(base).all()) or _i22_np.any(base < 0.0) or (not _i22_np.array_equal(forcing.rain_mm_h, base[:, None, None] * multiplier[None, :, :])):
        raise ValueError('saved base storm linkage mismatch')
    for key, expected in (('valid_multiplier_mean', _i22_np.mean(multiplier[mask])), ('valid_multiplier_min', _i22_np.min(multiplier[mask])), ('valid_multiplier_max', _i22_np.max(multiplier[mask]))):
        if meta[key] != float(expected):
            raise ValueError('saved multiplier statistic mismatch')
    return True

def save_spatial_forcing_package(path, package):
    from terrain_pipeline.common_infra import save_bundle as _i22_save_bundle
    _i22_save_bundle(path, package, validator=validate_spatial_forcing_package)

def load_spatial_forcing_package(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _i22_load_bundle
    package = _i22_load_bundle(path, expected_sha256=expected_sha256, validator=validate_spatial_forcing_package, max_bytes=SPATIAL_FORCING_MAX_BYTES)
    if package['identity_sha256'] != expected_identity:
        raise ValueError('external spatial forcing identity mismatch')
    return package
NATIVE_STORM_SCHEMA = 'td-native-moving-storm-v1'
MAX_SAMPLES = 4000000
MAX_EVALUATIONS = 50000000
SOURCE_RECORD = {'path': 'verification/td-basin-generation/A-20261001T184113155960Z/source.npz', 'expected_sha256': 'd09d2df4df86423547f5aa8e04efa14e98a285b0873124dd82982040434f7697', 'expected_identity': '8600fde239cc5b8d83a0f66c0eaa7974e2f68badc14dee341a9656d6911f199c'}

def native_storm_preflight(shape, steps, spatial_subsamples):
    if len(shape) != 2 or any((type(size) is not int or size < 1 for size in shape)) or type(steps) is not int or (steps < 1) or (type(spatial_subsamples) is not int) or (spatial_subsamples not in (1, 2, 4)):
        raise ValueError('invalid bounded dimensions/subsampling')
    cells = _i23_math.prod(shape)
    samples = cells * steps
    evaluations = samples * spatial_subsamples ** 2
    workspace = 40 * samples + 256 * cells + 65536
    if cells > 250000 or samples > MAX_SAMPLES or evaluations > MAX_EVALUATIONS or (workspace > STORM_MAX_BYTES):
        raise ValueError('native storm preallocation resource budget exceeded')
    return dict(samples=samples, evaluations=evaluations, workspace_bytes=workspace)

def _sha(value):
    if not isinstance(value, str) or _i23_re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('external SHA256/identity required')
    return value

def _source(record):
    from terrain_pipeline.basin_storage import load_td_source_bundle as _i23_load_td_source_bundle
    if not isinstance(record, dict) or set(record) != {'path', 'expected_sha256', 'expected_identity'}:
        raise ValueError('source external dual-pin record required')
    _sha(record['expected_sha256'])
    _sha(record['expected_identity'])
    return _i23_load_td_source_bundle(**record)

def fixed_storm(source, direction):
    if direction not in ('eastward', 'westward'):
        raise ValueError('unknown moving storm direction')
    spacing = source['metadata']['spacing_m']
    rows, columns = source['arrays']['height_m'].shape
    origin_x, origin_z = source['metadata']['origin_m_xz']
    span = max(spacing, (columns - 1) * spacing)
    center_x = origin_x if direction == 'eastward' else origin_x + (columns - 1) * spacing
    velocity = span / 21600 if direction == 'eastward' else -span / 21600
    return StormParameters(center_x, origin_z + (rows - 1) * spacing / 2, velocity, 0.0, max(1.0, span / 4), 30.0, 0.0, 21600.0)

def _plan(source, source_record, parameters, steps, dt_s, start_s, spatial_subsamples, window):
    shape = source['arrays']['height_m'].shape
    if window is None:
        window = [0, shape[0], 0, shape[1]]
    if not isinstance(window, (list, tuple)) or len(window) != 4 or any((type(value) is not int for value in window)) or (not 0 <= window[0] < window[1] <= shape[0]) or (not 0 <= window[2] < window[3] <= shape[1]):
        raise ValueError('invalid source-index window')
    resources = native_storm_preflight((window[1] - window[0], window[3] - window[2]), steps, spatial_subsamples)
    if any((type(value) not in (int, float) or not _i23_math.isfinite(value) for value in (dt_s, start_s))) or not 0.001 <= dt_s <= 10000000.0 or start_s < 0 or (start_s + steps * dt_s > 1000000000.0):
        raise ValueError('invalid physical time coverage')
    if not isinstance(parameters, StormParameters):
        raise ValueError('StormParameters required')
    parameters.__post_init__()
    metadata = dict(schema=NATIVE_STORM_SCHEMA, source_sha256=source_record['expected_sha256'], source_identity=source_record['expected_identity'], source_shape=list(shape), origin_m_xz=source['metadata']['origin_m_xz'], spacing_m=source['metadata']['spacing_m'], window=list(window), parameters=_i23_asdict(parameters), steps=steps, dt_s=float(dt_s), start_s=float(start_s), spatial_subsamples=spatial_subsamples, resources=resources, coordinates='x east, z south; source cell centers; rain [time,z,x]', spatial_integration='equal_area_midpoint_subcells_no_window_normalization', temporal_integration='mountain_storm_forcing.interval_mean_mm_h', unknown_policy='zero', protection_policy='preserved_not_hydrology_permission', water_solved=False, hydraulic_ready=False, publishable=False, status='parameterized_weather_scenario_not_forecast')
    return metadata

def _volumes(rain, spacing, dt_s):
    factor = dt_s / 3600 * spacing ** 2 / 1000
    return _i23_np.array([_i23_math.fsum((float(value) * factor for value in frame.flat)) for frame in rain], _i23_np.float64)

def generate_native_storm(source_record, *, parameters, steps=24, dt_s=3600.0, start_s=0.0, spatial_subsamples=2, window=None):
    from terrain_pipeline.common_infra import identity as _i23_identity
    from terrain_pipeline.common_infra import readonly as _i23_readonly
    source = _source(source_record)
    plan = _plan(source, source_record, parameters, steps, dt_s, start_s, spatial_subsamples, window)
    row0, row1, col0, col1 = plan['window']
    valid = source['arrays']['valid_mask'][row0:row1, col0:col1]
    protected = source['arrays']['protected_mask'][row0:row1, col0:col1]
    rain = _i23_np.zeros((steps, *valid.shape), _i23_np.float64)
    offsets = (_i23_np.arange(spatial_subsamples) + 0.5) / spatial_subsamples - 0.5
    origin_x, origin_z = plan['origin_m_xz']
    spacing = plan['spacing_m']
    columns = _i23_np.arange(col0, col1)[None, :]
    rows = _i23_np.arange(row0, row1)[:, None]
    for step in range(steps):
        lower = start_s + step * dt_s
        for delta_z in offsets:
            for delta_x in offsets:
                rain[step] += interval_mean_mm_h(origin_x + (columns + delta_x) * spacing, origin_z + (rows + delta_z) * spacing, lower, lower + dt_s, parameters) / spatial_subsamples ** 2
        rain[step, ~valid] = 0.0
    arrays = dict(rain_mm_h=rain, time_edges_s=start_s + _i23_np.arange(steps + 1) * dt_s, valid_mask=valid.copy(), protected_mask=protected.copy(), interval_rain_m3=_volumes(rain, spacing, dt_s))
    metadata = dict(plan=plan, plan_identity=_i23_identity({}, plan), forcing_identity=_i23_identity({'rain_mm_h': rain}, {'dt_s': float(dt_s)}))
    result = dict(arrays=arrays, metadata=metadata, identity_sha256=_i23_identity(arrays, metadata))
    validate_native_storm(result, source_record=source_record, expected_plan=plan)
    result['arrays'] = {name: _i23_readonly(values) for name, values in arrays.items()}
    return result

def _native_storm_headers(headers):
    if set(headers) != {'rain_mm_h', 'time_edges_s', 'valid_mask', 'protected_mask', 'interval_rain_m3', 'manifest'}:
        raise ValueError('native weather archive layout mismatch')
    shape, dtype = headers['rain_mm_h']
    if len(shape) != 3 or dtype != _i23_np.float64:
        raise ValueError('native weather rain header mismatch')
    native_storm_preflight(tuple(shape[1:]), shape[0], 1)
    for name, expected_shape, expected_dtype in (('time_edges_s', (shape[0] + 1,), _i23_np.float64), ('interval_rain_m3', (shape[0],), _i23_np.float64), ('valid_mask', shape[1:], bool), ('protected_mask', shape[1:], bool)):
        if headers[name] != (expected_shape, _i23_np.dtype(expected_dtype)):
            raise ValueError('native weather vector/mask header mismatch')
    manifest_shape, manifest_dtype = headers['manifest']
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= 65536 or manifest_dtype != _i23_np.uint8:
        raise ValueError('native weather manifest budget mismatch')

def validate_native_storm(result, *, source_record=None, expected_plan=None):
    from terrain_pipeline.common_infra import identity as _i23_identity
    arrays, metadata = (result['arrays'], result['metadata'])
    _native_storm_headers({**{name: (values.shape, values.dtype) for name, values in arrays.items()}, 'manifest': ((1,), _i23_np.dtype('uint8'))})
    if set(metadata) != {'plan', 'plan_identity', 'forcing_identity'} or result['identity_sha256'] != _i23_identity(arrays, metadata):
        raise ValueError('weather bundle identity/schema mismatch')
    plan = metadata['plan']
    if source_record is not None:
        source = _source(source_record)
        canonical = _plan(source, source_record, StormParameters(**plan['parameters']), plan['steps'], plan['dt_s'], plan['start_s'], plan['spatial_subsamples'], plan['window'])
        if plan != canonical:
            raise ValueError('weather source/plan semantic mismatch')
        row0, row1, col0, col1 = plan['window']
        for name in ('valid_mask', 'protected_mask'):
            if not _i23_np.array_equal(arrays[name], source['arrays'][name][row0:row1, col0:col1]):
                raise ValueError('weather source mask mismatch')
    if expected_plan is not None and plan != expected_plan:
        raise ValueError('external predeclared weather plan mismatch')
    if plan['schema'] != NATIVE_STORM_SCHEMA or metadata['plan_identity'] != _i23_identity({}, plan):
        raise ValueError('weather plan identity mismatch')
    resources = native_storm_preflight(tuple(arrays['valid_mask'].shape), plan['steps'], plan['spatial_subsamples'])
    if resources != plan['resources']:
        raise ValueError('weather resource metadata mismatch')
    parameters = StormParameters(**plan['parameters'])
    rain = arrays['rain_mm_h']
    edges = plan['start_s'] + _i23_np.arange(plan['steps'] + 1) * plan['dt_s']
    if rain.shape[0] != plan['steps'] or not _i23_np.array_equal(edges, arrays['time_edges_s']):
        raise ValueError('weather time coverage mismatch')
    if not _i23_np.isfinite(rain).all() or (rain < 0).any() or (rain > parameters.peak_mm_h + 1e-10).any() or (rain[:, ~arrays['valid_mask']] != 0).any():
        raise ValueError('invalid native rainfall')
    inactive = (edges[1:] <= parameters.start_s) | (edges[:-1] >= parameters.end_s)
    if (rain[inactive] != 0).any():
        raise ValueError('rain outside declared active interval')
    if metadata['forcing_identity'] != _i23_identity({'rain_mm_h': rain}, {'dt_s': float(plan['dt_s'])}):
        raise ValueError('full numerical forcing identity mismatch')
    if not _i23_np.array_equal(_volumes(rain, plan['spacing_m'], plan['dt_s']), arrays['interval_rain_m3']):
        raise ValueError('native interval rain volume mismatch')
    return dict(total_rain_m3=_i23_math.fsum(arrays['interval_rain_m3']), max_rain_mm_h=float(rain.max()))

def save_native_storm(path, result):
    from terrain_pipeline.common_infra import save_bundle as _i23_save_bundle
    _i23_save_bundle(path, result, validator=validate_native_storm)

def load_native_storm(path, *, expected_sha256, expected_identity, source_record, expected_plan):
    from terrain_pipeline.common_infra import load_bundle as _i23_load_bundle
    _sha(expected_sha256)
    _sha(expected_identity)
    if not isinstance(expected_plan, dict):
        raise ValueError('external predeclared weather plan required')
    result = _i23_load_bundle(path, expected_sha256=expected_sha256, max_bytes=STORM_MAX_BYTES, header_validator=_native_storm_headers, validator=lambda bundle: validate_native_storm(bundle, source_record=source_record, expected_plan=expected_plan))
    if result['identity_sha256'] != expected_identity:
        raise ValueError('external weather identity mismatch')
    return result

def physical_bio_context(values, real_reference):
    values = _i24_np.asarray(values, _i24_np.float64)
    if values.shape[0] != 4 or not _i24_np.isfinite(values).all():
        raise ValueError('four finite BIO physical channels required')
    reference = real_reference['physical_reference']
    observations = values.reshape(4, -1)
    names = ('BIO1', 'BIO4', 'BIO12', 'BIO15')
    context = {}
    for index, name in enumerate(names):
        lower, upper = (reference['quantiles'][name][0], reference['quantiles'][name][-1])
        sample = observations[index]
        context[name] = {'observed_range': [float(sample.min()), float(sample.max())], 'real_product_range': [lower, upper], 'outside_real_product_range_count': int(((sample < lower) | (sample > upper)).sum())}
    bins = _i24_np.searchsorted([0.0, 10.0, 20.0, 30.0], observations[0], side='right')
    conditioned = []
    for envelope in reference['temperature_conditioned_joint_envelopes']:
        selected = bins == envelope['BIO1_bin']
        if not selected.any():
            continue
        departures = {}
        for index, name in enumerate(names[1:], 1):
            lower, upper = (envelope['quantiles'][name][0], envelope['quantiles'][name][-1])
            sample = observations[index, selected]
            departures[name] = int(((sample < lower) | (sample > upper)).sum())
        conditioned.append({'temperature_class': envelope['BIO1_bin'], 'sample_count': int(selected.sum()), 'outside_temperature_conditioned_real_range': departures})
    return {'univariate': context, 'temperature_conditioned_joint_context': conditioned, 'role': 'observed_product_descriptive_context_not_universal_physical_impossibility_or_geographic_match', 'real_product_weighting': reference['statistical_weighting']}

def audit_noise_climate(seed, x_m, z_m, elevation_m, real_reference, *, parameters=None):
    climate = sample_climate(seed, x_m, z_m, elevation_m, parameters=parameters)
    temperature, precipitation = (climate['monthly_temperature_c'], climate['monthly_precipitation_mm'])
    expected = _i24_np.stack((temperature.mean(axis=0), temperature.std(axis=0) * 100.0, precipitation.sum(axis=0), precipitation.std(axis=0) / precipitation.mean(axis=0) * 100.0))
    checks = {'monthly_finite': bool(_i24_np.isfinite(temperature).all() and _i24_np.isfinite(precipitation).all()), 'monthly_precipitation_nonnegative': bool((precipitation >= 0.0).all()), 'BIO_from_same_months': bool(_i24_np.array_equal(expected, climate['BIO1_4_12_15']))}
    return {'schema': 'metric-noise-climate-physical-audit-v1', 'seed': seed, 'parameter_identity_sha256': climate['parameter_identity_sha256'], 'checks': checks, 'physical_model_status': 'pass' if all(checks.values()) else 'fail', 'real_context': physical_bio_context(climate['BIO1_4_12_15'], real_reference), 'forcing_semantics': 'synthetic_weather;monthly_targets_are_not_realized_annual_rainfall_or_observations', 'natural_certification': False}
TD_CLIMATE_CHANNELS = ['temperature_mean_c', 'temperature_std_c_times_100', 'precipitation_mean_mm_year', 'precipitation_cv_times_100', 'temperature_elevation_beta_c_per_m']

def couple_td_climate(climate_base, raw_td_m, composed_m, refined_climate):
    """Retain actual TD conditioned means/variability and existing seasonal phase.

    TD's first channel is already temperature at raw TD elevation. Only the
    composed-minus-raw positive-elevation difference receives its lapse rate.
    """
    base = _i25_np.asarray(climate_base, _i25_np.float64)
    raw, composed = _i25_np.broadcast_arrays(_i25_np.asarray(raw_td_m, _i25_np.float64), _i25_np.asarray(composed_m, _i25_np.float64))
    if base.shape != (5, *raw.shape) or not _i25_np.isfinite(base).all() or (not _i25_np.isfinite(raw).all()) or (not _i25_np.isfinite(composed).all()) or _i25_np.any(base[1:4] < 0.0):
        raise ValueError('Actual five-channel finite TD climate and matching terrain fields required')
    mean_temperature = base[0] + base[4] * (_i25_np.maximum(composed, 0.0) - _i25_np.maximum(raw, 0.0))
    reference_temperature = _i25_np.asarray(refined_climate['monthly_temperature_c'], _i25_np.float64)
    reference_rain = _i25_np.asarray(refined_climate['monthly_precipitation_mm'], _i25_np.float64)
    if reference_temperature.shape != (12, *raw.shape) or reference_rain.shape != reference_temperature.shape:
        raise ValueError('Existing monthly phase must match TD climate coordinates')
    anomaly = reference_temperature - reference_temperature.mean(axis=0)
    standard_deviation = anomaly.std(axis=0)
    standardized = _i25_np.divide(anomaly, standard_deviation, out=_i25_np.zeros_like(anomaly), where=standard_deviation > 0.0)
    temperature = mean_temperature + standardized * (base[1] / 100.0)
    temperature += mean_temperature - temperature.mean(axis=0)
    target_annual = _i25_np.clip(base[2] * refined_climate['precipitation_multiplier'], 100.0, 3200.0)
    weights = reference_rain / reference_rain.mean(axis=0)
    rain_anomaly = weights - 1.0
    reference_cv = rain_anomaly.std(axis=0)
    requested_cv = base[3] / 100.0
    ratio = _i25_np.divide(requested_cv, reference_cv, out=_i25_np.zeros_like(reference_cv), where=reference_cv > 0.0)
    rescaled = 1.0 + rain_anomaly * ratio
    fallback = _i25_np.any(rescaled <= 0.0, axis=0) | (reference_cv == 0.0) & (requested_cv > 0.0)
    weights = _i25_np.where(fallback[None], weights, rescaled)
    precipitation = weights / weights.sum(axis=0) * target_annual
    precipitation[-1] += target_annual - precipitation.sum(axis=0)
    return dict(monthly_temperature_c=temperature, monthly_precipitation_mm=precipitation, temperature_target_c=mean_temperature, annual_precipitation_target_mm=target_annual, precipitation_cv_fallback=fallback, realized_precipitation_cv=precipitation.std(axis=0) / precipitation.mean(axis=0))

def native_climate_sampler(metadata):
    """Read the genuine composed 30 m source and reject unsupported queries."""
    source_record = metadata['native_source_paths']['composed_30m']
    source_path = _i25_Path(source_record['path'])
    native = _i25_np.load(source_path, mmap_mode='r', allow_pickle=False)
    origin = _i25_np.asarray(metadata['native_source_origin_xz_m'], _i25_np.float64)
    if native.ndim != 2 or origin.shape != (2,) or (not _i25_np.isfinite(origin).all()):
        raise ValueError('2D composed native source and centre origin required')
    support = metadata.get('source_support', {})
    margin = int(metadata.get('composition', {}).get('filter_radius_native_cells', 0))
    minimum = origin + margin * 30.0
    maximum = origin + (_i25_np.array(native.shape[::-1]) - 1 - margin) * 30.0

    def sample(x_m, z_m):
        sx, sz = _i25_np.broadcast_arrays(x_m, z_m)
        if _i25_np.any(sx < minimum[0]) or _i25_np.any(sx > maximum[0]) or _i25_np.any(sz < minimum[1]) or _i25_np.any(sz > maximum[1]):
            raise ValueError('Native terrain lacks unfiltered climate query support')
        values = _i25_map_coordinates(native, [(sz - origin[1]) / 30.0, (sx - origin[0]) / 30.0], order=1, mode='constant', cval=_i25_np.nan)
        if not _i25_np.isfinite(values).all():
            raise ValueError('Native climate sampler encountered nonfinite terrain')
        return values
    return (sample, dict(path=str(source_path.resolve()), source=source_record, origin_xz_m=origin.tolist(), spacing_m=30.0, shape=list(native.shape), filter_margin_native_cells=margin, valid_minimum_xz_m=minimum.tolist(), valid_maximum_xz_m=maximum.tolist(), source_support=support))

def boundary_influence_mask(shape, ocean, width=8):
    rows, cols = _i25_np.indices(shape)
    return ((rows < width) | (cols < width) | (rows >= shape[0] - width) | (cols >= shape[1] - width)) & ~ocean
