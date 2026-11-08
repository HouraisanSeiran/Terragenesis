"""Seeded metric climate and rain fields; synthetic physical inputs, not observations."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from diffusion.geographic_noise import field
from terrain_pipeline.common_infra import identity
from terrain_pipeline.common_infra import RainfallForcing


MONTH_DAYS = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], np.float64)
MONTH_EDGES_S = np.r_[0., np.cumsum(MONTH_DAYS) * 86400.]
YEAR_S = float(MONTH_EDGES_S[-1])
MONTH_CENTERS_S = .5 * (MONTH_EDGES_S[:-1] + MONTH_EDGES_S[1:])


@dataclass(frozen=True)
class StormParameters:
    """One bounded candidate pulse per absolute spatial cell and daily slot."""

    cell_spacing_m: float = 48000.
    max_radius_m: float = 22000.
    slot_seconds: float = 86400.
    min_duration_s: float = 21600.
    max_duration_s: float = 43200.
    max_intensity_mm_h: float = 18.
    occurrence_probability: float = .4

    def __post_init__(self):
        values = asdict(self)
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values.values()):
            raise ValueError("finite storm parameters required")
        if (self.cell_spacing_m <= 0. or not 0. < self.max_radius_m <= self.cell_spacing_m
                or not 0. < self.min_duration_s <= self.max_duration_s <= self.slot_seconds
                or self.max_intensity_mm_h < 0.
                or not 0. <= self.occurrence_probability <= 1.):
            raise ValueError("bounded storm support and positive physical scales required")

    @property
    def identity_sha256(self):
        return identity({}, {"schema": "metric-bounded-storm-v1", "parameters": asdict(self)})


def _storm_random(seed, cell_x, cell_z, slot, stream):
    # Integer hashing is independent of request bounds and sampling order.
    with np.errstate(over="ignore"):
        value = (np.asarray(cell_x, np.int64).astype(np.uint64) * np.uint64(0x9E3779B185EBCA87)
                 ^ np.asarray(cell_z, np.int64).astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
                 ^ np.uint64(seed) ^ np.uint64(slot) * np.uint64(0x165667B19E3779F9)
                 ^ np.uint64(stream) * np.uint64(0x85EBCA77C2B2AE63))
        value = (value ^ (value >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        value = (value ^ (value >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        value ^= value >> np.uint64(31)
    return (value >> np.uint64(11)).astype(np.float64) / float(2 ** 53)


def _triangle_integral(fraction):
    value = np.clip(fraction, 0., 1.)
    return np.where(value <= .5, value ** 2, .5 - (1. - value) ** 2)


def interval_seasonal_storm_rain_mm(seed, x_m, z_m, start_s, end_s, *,
                                   monthly_precipitation_mm=None, storm_parameters=None):
    """Integrated depths for a periodic climate baseline plus compact storms.

    Monthly precipitation is converted to mm/s at month centers and linearly
    interpolated, including across the year boundary, and scaled by their
    analytic annual integral to preserve the supplied annual climate target.
    Storms use a fixed world lattice, compact radial support and triangular
    time pulses; their added rain is not part of that target. Neither field is
    normalized to request bounds. At most 32 storm slots per call.
    """
    x, z = _coordinates(seed, x_m, z_m)
    parameters = StormParameters() if storm_parameters is None else storm_parameters
    if not isinstance(parameters, StormParameters):
        raise ValueError("StormParameters required")
    if (not all(type(v) in (int, float) and math.isfinite(v) for v in (start_s, end_s))
            or not 0. <= start_s < end_s <= 1e12
            or end_s / parameters.slot_seconds >= 2 ** 63
            or math.ceil(end_s / parameters.slot_seconds) - math.floor(start_s / parameters.slot_seconds) > 32):
        raise ValueError("bounded positive absolute weather interval required")
    precipitation = (sample_climate(seed, x, z)["monthly_precipitation_mm"]
                     if monthly_precipitation_mm is None
                     else np.asarray(monthly_precipitation_mm, np.float64))
    if (precipitation.shape != (12, *x.shape) or not np.isfinite(precipitation).all()
            or np.any(precipitation < 0.)):
        raise ValueError("12 finite nonnegative monthly precipitation grids required")
    with np.errstate(over="ignore"):
        annual_target = precipitation.sum(axis=0)
    if not np.isfinite(annual_target).all():
        raise ValueError("finite annual precipitation target required")
    rates = precipitation / (MONTH_DAYS * 86400.).reshape((12,) + (1,) * x.ndim)
    center_gaps = np.diff(np.r_[MONTH_CENTERS_S, MONTH_CENTERS_S[0] + YEAR_S])
    annual_weights = .5 * (center_gaps + np.roll(center_gaps, 1))
    annual_integral = np.sum(rates * annual_weights.reshape((12,) + (1,) * x.ndim), axis=0)
    normalization = np.divide(annual_target, annual_integral,
                              out=np.zeros(x.shape), where=annual_integral > 0.)
    rates *= normalization
    baseline = np.zeros(x.shape, np.float64)
    lower = float(start_s)
    while lower < end_s:
        year = math.floor(lower / YEAR_S)
        position = lower - year * YEAR_S
        index = int(np.searchsorted(MONTH_CENTERS_S, position, side="right")) - 1
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
        average_fraction = (.5 * (lower + upper) - first_time) / (last_time - first_time)
        baseline += (rates[index % 12] + average_fraction * (
            rates[(index + 1) % 12] - rates[index % 12])) * (upper - lower)
        lower = upper
    storm = np.zeros(x.shape, np.float64)
    if parameters.occurrence_probability == 0. or parameters.max_intensity_mm_h == 0.:
        return dict(seasonal_depth_mm=baseline, storm_depth_mm=storm,
                    total_depth_mm=baseline.copy())
    base_x = np.floor(x / parameters.cell_spacing_m).astype(np.int64)
    base_z = np.floor(z / parameters.cell_spacing_m).astype(np.int64)
    for slot in range(math.floor(start_s / parameters.slot_seconds), math.ceil(end_s / parameters.slot_seconds)):
        for dz in (-1, 0, 1):
            for dx in (-1, 0, 1):
                cell_x, cell_z = base_x + dx, base_z + dz
                active = _storm_random(seed, cell_x, cell_z, slot, 1) < parameters.occurrence_probability
                center_x = (cell_x + _storm_random(seed, cell_x, cell_z, slot, 2)) * parameters.cell_spacing_m
                center_z = (cell_z + _storm_random(seed, cell_x, cell_z, slot, 3)) * parameters.cell_spacing_m
                radius = parameters.max_radius_m * (.5 + .5 * _storm_random(seed, cell_x, cell_z, slot, 4))
                radial = np.maximum(0., 1. - ((x - center_x) ** 2 + (z - center_z) ** 2) / radius ** 2) ** 2
                duration = parameters.min_duration_s + (parameters.max_duration_s - parameters.min_duration_s) * _storm_random(seed, cell_x, cell_z, slot, 5)
                pulse_start = slot * parameters.slot_seconds + (parameters.slot_seconds - duration) * _storm_random(seed, cell_x, cell_z, slot, 6)
                integral_s = duration * (_triangle_integral((end_s - pulse_start) / duration)
                                        - _triangle_integral((start_s - pulse_start) / duration))
                intensity = parameters.max_intensity_mm_h * (.35 + .65 * _storm_random(seed, cell_x, cell_z, slot, 7))
                storm += active * radial * intensity * integral_s / 3600.
    return dict(seasonal_depth_mm=baseline, storm_depth_mm=storm,
                total_depth_mm=baseline + storm)


@dataclass(frozen=True)
class NoiseClimateParameters:
    climate_scale_m: float = 240000.
    regional_scale_m: float = 60000.
    lapse_rate_c_per_m: float = -.0065
    weather_scale_m: float = 12000.
    weather_detail_scale_m: float = 3000.
    velocity_x_m_s: float = 8.
    velocity_z_m_s: float = 2.
    absolute_weather_step_s: float = 900.

    def __post_init__(self):
        values = asdict(self)
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in values.values()):
            raise ValueError("finite physical noise climate parameters required")
        if any(values[name] <= 0. for name in ("climate_scale_m", "regional_scale_m", "weather_scale_m", "weather_detail_scale_m", "absolute_weather_step_s")):
            raise ValueError("positive meter scales and physical time step required")
        if not -.012 <= self.lapse_rate_c_per_m <= 0.:
            raise ValueError("lapse rate must be -0.012..0 Celsius per meter")

    @property
    def identity_sha256(self):
        return identity({}, {"schema": "metric-noise-climate-v1", "parameters": asdict(self)})


def _coordinates(seed, x_m, z_m):
    if type(seed) is not int or not 0 <= seed < 2 ** 64:
        raise ValueError("uint64 world seed required")
    x, z = np.broadcast_arrays(np.asarray(x_m, np.float64), np.asarray(z_m, np.float64))
    if not 1 <= x.size <= 1048576 or not np.isfinite(x).all() or not np.isfinite(z).all() or max(float(np.max(np.abs(x))), float(np.max(np.abs(z)))) > 1e12:
        raise ValueError("bounded finite absolute meter coordinates required")
    return x, z


def sample_climate(seed, x_m, z_m, elevation_m=0., *, parameters=None):
    """Generate monthly Celsius/mm, then derive BIO1/4/12/15 from those months."""
    parameters = parameters or NoiseClimateParameters()
    x, z = _coordinates(seed, x_m, z_m)
    elevation = np.broadcast_to(np.asarray(elevation_m, np.float64), x.shape)
    if not np.isfinite(elevation).all():
        raise ValueError("finite physical elevation required")
    scales = ((parameters.climate_scale_m, 1.), (parameters.regional_scale_m, .25))
    thermal = .5 * (1. + field(x, z, seed, 1401, scales))
    moisture = .5 * (1. + field(x, z, seed, 1503, scales))
    continentality = .8 * (1. - moisture) + .2 * .5 * (1. + field(x, z, seed, 1607, scales))
    annual_temperature = -8. + 38. * thermal + parameters.lapse_rate_c_per_m * np.maximum(elevation, 0.)
    temperature_amplitude = (2. + 20. * continentality) * (1. - .45 * thermal)
    annual_precipitation = 120. + 3000. * moisture ** 2 * (.65 + .35 * thermal)
    rain_seasonality = .4 + 1.8 * (1. - moisture) * thermal
    phase = np.pi * field(x, z, seed, 1709, scales)
    month_shape = (12,) + (1,) * x.ndim
    angles = (np.arange(12) * (2. * np.pi / 12.)).reshape(month_shape)
    seasonal_cycle = np.cos(angles - phase)
    temperature = annual_temperature + temperature_amplitude * seasonal_cycle
    weights = np.exp(rain_seasonality * seasonal_cycle)
    precipitation = annual_precipitation * weights / np.sum(weights, axis=0)
    bioclim = np.stack((np.mean(temperature, axis=0), np.std(temperature, axis=0) * 100.,
                       np.sum(precipitation, axis=0), np.std(precipitation, axis=0) / np.mean(precipitation, axis=0) * 100.))
    return {"monthly_temperature_c": temperature, "monthly_precipitation_mm": precipitation,
            "BIO1_4_12_15": bioclim, "thermal_strength": thermal, "moisture_strength": moisture,
            "continentality_strength": continentality, "parameter_identity_sha256": parameters.identity_sha256,
            "semantics": "synthetic_monthly_climate_targets_not_measured_weather"}


def _weather_node(seed, x, z, time_s, parameters):
    weather = field(x - parameters.velocity_x_m_s * time_s, z - parameters.velocity_z_m_s * time_s,
                    seed, 1801, ((parameters.weather_scale_m, 1.), (parameters.weather_detail_scale_m, .3)))
    # Symmetric zero-mean noise gives unit expected multiplier; no local normalization.
    return 1. + .95 * weather


def interval_mean_rain_mm_h(seed, x_m, z_m, start_s, end_s, *, parameters=None):
    """Integrate fixed absolute-time linear weather nodes and monthly climate rates."""
    parameters = parameters or NoiseClimateParameters()
    x, z = _coordinates(seed, x_m, z_m)
    if not all(type(value) in (int, float) and math.isfinite(value) for value in (start_s, end_s)) or not 0 <= start_s < end_s:
        raise ValueError("finite positive physical time interval required")
    step = parameters.absolute_weather_step_s
    if (end_s - start_s) / step > 4096.:
        raise ValueError("rain interval exceeds fixed integration work budget")
    climate = sample_climate(seed, x, z, parameters=parameters)
    precipitation = climate["monthly_precipitation_mm"]
    volume_mm = np.zeros(x.shape, np.float64)
    lower = float(start_s)
    while lower < end_s:
        year = math.floor(lower / YEAR_S)
        in_year = lower - year * YEAR_S
        month = min(11, int(np.searchsorted(MONTH_EDGES_S, in_year, side="right") - 1))
        node = math.floor(lower / step)
        node_start = node * step
        upper = min(float(end_s), (node + 1) * step, year * YEAR_S + MONTH_EDGES_S[month + 1])
        first = _weather_node(seed, x, z, node_start, parameters)
        last = _weather_node(seed, x, z, node_start + step, parameters)
        fraction0, fraction1 = (lower - node_start) / step, (upper - node_start) / step
        average = first + .5 * (fraction0 + fraction1) * (last - first)
        monthly_rate_mm_h = precipitation[month] / (MONTH_DAYS[month] * 24.)
        volume_mm += monthly_rate_mm_h * average * ((upper - lower) / 3600.)
        lower = upper
    return volume_mm * 3600. / (end_s - start_s)


def grid_rainfall(seed, *, origin_xz_m, shape_zx, spacing_m, time_edges_s, parameters=None, spatial_subsamples=2):
    """Equal-area midpoint subcells provide an explicit numerical cell-average."""
    parameters = parameters or NoiseClimateParameters()
    edges = np.asarray(time_edges_s, np.float64)
    if edges.ndim != 1 or edges.size < 2 or not np.isfinite(edges).all() or np.any(np.diff(edges) <= 0.) or edges[0] < 0.:
        raise ValueError("increasing finite physical time edges required")
    if spatial_subsamples not in (1, 2, 4) or len(shape_zx) != 2 or any(type(side) is not int or side <= 0 for side in shape_zx):
        raise ValueError("positive grid shape and 1/2/4 midpoint subdivisions required")
    if type(spacing_m) not in (int, float) or not math.isfinite(spacing_m) or spacing_m <= 0.:
        raise ValueError("positive physical grid spacing required")
    if np.prod(shape_zx) * (edges.size - 1) * spatial_subsamples ** 2 > 50000000:
        raise ValueError("noise rainfall resource dimensions exceeded")
    rows, columns = np.indices(shape_zx)
    offsets = (np.arange(spatial_subsamples) + .5) / spatial_subsamples - .5
    intensity = np.zeros((edges.size - 1,) + tuple(shape_zx), np.float64)
    for delta_z in offsets:
        for delta_x in offsets:
            x = origin_xz_m[0] + (columns + delta_x) * spacing_m
            z = origin_xz_m[1] + (rows + delta_z) * spacing_m
            for index, (start, end) in enumerate(zip(edges, edges[1:])):
                intensity[index] += interval_mean_rain_mm_h(seed, x, z, float(start), float(end), parameters=parameters) / spatial_subsamples ** 2
    metadata = {"schema": "metric-noise-rainfall-v1", "seed": seed,
        "origin_xz_m": list(origin_xz_m), "shape_zx": list(shape_zx), "spacing_m": float(spacing_m),
        "time_edges_s": edges.tolist(), "parameters": asdict(parameters),
        "parameter_identity_sha256": parameters.identity_sha256,
        "spatial_mean": "equal_area_midpoint_subcells", "spatial_subsamples": spatial_subsamples,
        "cell_boundary_convention": "origin_is_center;subcells_cover_center_plus_minus_half_spacing",
        "absolute_weather_step_s": parameters.absolute_weather_step_s,
        "monthly_target_is_not_realized_annual_forcing": True}
    metadata["source_identity_sha256"] = identity({}, metadata)
    forcing = RainfallForcing(edges, intensity, "synthetic_noise_climate", metadata["source_identity_sha256"])
    return forcing, metadata
