"""Terrain-refined climate (v2): normalized climate bands plus orographic rainfall.

This module is the refinement layer of the `climate-refinement-spec` contract. It
sits **on top of** the frozen `metric-noise-climate-v1` base layer in
`terrain_pipeline.surface_rivers.metric_noise_forcing` and reuses that layer by
calling it (`_v1_sample_climate`), never by copying its formulas. Consequences:

- v1 is not modified in any way (no new parameters, no new return keys, same
  `NoiseClimateParameters.identity_sha256`).
- With every refinement parameter switched off, `sample_climate_v2` returns the v1
  `monthly_temperature_c` / `monthly_precipitation_mm` / `BIO1_4_12_15` arrays
  **bit for bit** (`np.array_equal`, not `allclose`). The identity path is a
  structural short circuit, not an approximation: a precipitation multiplier of
  exactly `1.` leaves the v1 monthly values untouched.

What is implemented here (contract sections):

- §3.1 `latitude_norm(seed, z_m, period_m=LATITUDE_PERIOD_M)`: a normalized,
  dimensionless climate band coordinate. `+1` is the **pole** side and `-1` is the
  **equator** side (an artificial convention, declared verbatim here). It depends on
  `z_m` alone, so bands run east-west, repeat with `latitude_period_m` and are
  well defined in an infinite world. It is **not a real latitude**: no degrees, no
  real coordinate system, no real climate classification (Koppen/Holdridge unused).
  The returned key is `latitude_band_norm` and never `latitude_deg`.
- §3.2 row 1 (temperature): every month is shifted by the same band offset
  `latitude_temperature_range_c * latitude_norm`, so a **negative** value makes the pole
  side colder (the direction the contract names) and the equator side warmer. The offset
  is constant across the twelve months, so it moves the annual mean and `BIO1` while
  leaving the seasonal amplitude alone. With the switch at exactly `0.` the base months
  are returned unmodified (the §7.1 identity path).
- §3.2 row 2 (synthetic precipitation band):
  `band_multiplier = 1 + latitude_precipitation_gain * cos(pi * latitude_norm)`, the
  shape named in the contract. In the declared `+1` pole / `-1` equator convention this
  is a **dry-wet-dry** three-band shape: the multiplier peaks at `1 + gain` where the
  band coordinate crosses zero, falls to exactly `1 - gain` at both extremes
  (`latitude_norm = +-1`), and is `1` at `|latitude_norm| = .5`. It is an engineering
  assumption with no observational source and no claim that a band means a real
  climatological zone. The row exists as a parameter, is validated and enters the
  identity, but its default keeps it switched off (`latitude_precipitation_gain = 0.`,
  the whole-row-off option of contract §3.3); tests exercise it with a positive gain.
  With the switch at exactly `0.` the multiplier is exactly `1.` everywhere, so the
  precipitation identity path is untouched.
- §4.1 `wind_unit(latitude_norm_value)`: a prevailing bearing taken from the band
  only, so every place on the same band shares one bearing. The value is one of a
  finite set of 0/+-1 axial unit vectors (zonal: east-to-west in the trade and
  polar bands, west-to-east in the mid-latitude band). No local, per-x bearing is
  introduced, because that would reintroduce sampling-path dependence.
- §4.2 one single upwind difference of a smoothed ridge drives both sides:
  `grad = (ridge(x,z) - ridge(x - wx*scale, z - wz*scale)) / scale`,
  `lift = max(grad, 0)`, `shelter = max(-grad, 0)` (the negative part of the *same*
  quantity, never a second criterion or a second drifting threshold), and
  `multiplier = clip(1 + windward_gain_m*lift, 0, 1 + max_windward_gain)
  * clip(1 - lee_loss_m*shelter, min_lee_retention, 1)`.
- §4.3 elevation is connected end to end through an injectable, **pure**
  `elevation_sampler(x_m, z_m) -> height_m`, defaulting to the height component of
  `terrain_pipeline.hydrology_planning.coarse_condition_field` (already a pure
  function of `(seed, x, z)`). A sampler must be window-free and order-free; this
  module keeps no cache and no per-call state, so identical inputs give identical
  bits in any window and any call order. An explicit `elevation_m` takes priority
  for the *elevation used by the v1 base layer* (lapse rate); the orographic ridge
  is always built from `elevation_sampler`, because a ridge needs the surface at
  arbitrary surrounding world coordinates. A caller holding its own DEM must pass
  it as a pure `elevation_sampler` to steer the orographic term.
- §4.4 the annual precipitation is clamped to
  `[annual_precipitation_min_mm, annual_precipitation_max_mm]` (default
  `[100, 3200]` mm/yr, the same order as the old `geography_v5` clip) *after* the
  terrain multiplier is applied, and the monthly values are rescaled to that
  clamped annual value (v1's normalization step, preserved). The monthly-sum
  closure is exact to at most one unit in the last place (see below).
- §5 identity and naming: schema `metric-noise-climate-v2` / `metric-noise-rainfall-v2`,
  class `RefinedClimateParameters` (base scales **and** refinement parameters both
  inside `asdict`), return keys `base_parameter_identity_sha256` (the reused v1
  identity, never overwritten or disguised) and `parameter_identity_sha256` (v2).

Declared engineering assumptions (the same kind of disclosure duty as the three
thresholds of `Landscape.variant()`), stated verbatim: the banded prevailing wind
and any band structure here are **synthetic band structure, not a measured
climatology**. This is an engineering assumption with no observational source. The
gains, losses, scales, the band temperature range and the band precipitation gain are
likewise synthetic scenario coefficients, not fitted climatology or orographic physics.

Snow line (§6) is a **derived diagnostic only** and never feeds back into
precipitation: `snow_line` reports the elevation at which each monthly mean crosses `0`
Celsius, derived from the same monthly temperatures this module returns at zero
elevation, plus the seasonal (any freezing month) and perennial (every month freezing)
envelopes. The column is linear in elevation because the base layer's only elevation
dependence is the lapse rate, so the thresholds are solved in closed form instead of
sampled; with a zero lapse rate the threshold is infinite, meaning "never freezes at any
elevation".

Still out of scope: real latitude/longitude or real climate classes, maritime or
coast-distance terms, snow line as a precipitation term, the Java/Mod/default world, and
`diffusion/geography_v1..v5.py` (the old duplicated windward/lee formulas are reference
material only).

Documented arithmetic limits (stated rather than hidden):

- Periodicity of `latitude_norm` holds in floating point, not bit for bit: for a
  query `z` and `z + k*period`, the input sum itself already loses low bits, so
  agreement is at the few-ulp level (asserted with a tight absolute tolerance).
- The clamped annual target cannot in general be reproduced bit for bit by summing
  twelve float64 months. One exact residual repair is applied afterwards, which
  bounds the residual by one unit in the last place (`spacing(3200) = 4.5e-13` mm).
  Therefore `annual_precipitation_mm` reports the realized monthly sum (exact closure
  with the months and with `BIO12`) while `annual_precipitation_target_mm` reports the
  clamped post-multiplier annual of §4.4 itself; the two agree to that one last place.
- `windward_gain_m` / `lee_loss_m` are validated as finite and **nonnegative**
  (contract §4.4 asks for `> 0`): `0.` is the documented off switch that makes the
  multiplier exactly `1.`, which §7.1's bit-for-bit v1 replay requires. The same
  off behaviour is also reachable with positive gains via `max_windward_gain = 0.`
  and `min_lee_retention = 1.`, so no effect is unreachable either way.
"""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.hydrology_planning import coarse_condition_field
from terrain_pipeline.common_infra import identity
from terrain_pipeline.common_infra import RainfallForcing
from .metric_noise_forcing import (
    NoiseClimateParameters,
    _coordinates as _v1_coordinates,
    interval_mean_rain_mm_h as _v1_interval_mean_rain_mm_h,
    sample_climate as _v1_sample_climate,
)


CLIMATE_SCHEMA = "metric-noise-climate-v2"
RAINFALL_SCHEMA = "metric-noise-rainfall-v2"
SEMANTICS = ("synthetic_monthly_climate_targets_not_measured_weather; "
             "orographic_and_normalized_band_modifiers")
BAND_STRUCTURE_SEMANTICS = "synthetic band structure, not a measured climatology"

# Normalized climate band geometry (§3.1). One period covers pole -> equator -> pole.
LATITUDE_PERIOD_M = 1_920_000.
# Prevailing-bearing bands in normalized units (§4.1). Same band, same bearing.
WIND_TRADE_BAND_LIMIT = .30
WIND_POLAR_BAND_LIMIT = .70
# WIND_BAND_UNITS[i] = (wx, wz) = direction the air moves toward; +x east, +z south.
WIND_BAND_UNITS = ((-1, 0), (1, 0), (-1, 0))
WIND_BAND_NAMES = ("equator_side_trades_east_to_west", "mid_latitude_westerlies_west_to_east",
                   "pole_side_trades_east_to_west")
DEFAULT_OROGRAPHIC_SCALE_M = 15_000.
# §3.2 row 1: signed temperature offset applied at the pole side of the band; negative
# means the pole side is colder, the direction the contract names. A 12 C half-range
# spans 24 C from equator to pole: visible against the v1 base range (38 C) without
# masking it. Synthetic scenario value, not a measured pole-to-equator contrast.
DEFAULT_LATITUDE_TEMPERATURE_RANGE_C = -12.
# §3.2 row 2: synthetic three-band precipitation gain, off by default (contract §3.3).
# The multiplier is `1 + gain*cos(pi*norm)`: `1+gain` where the band coordinate crosses
# zero, `1-gain` at both extremes. Off by default, which contract §3.3 allows.
DEFAULT_LATITUDE_PRECIPITATION_GAIN = 0.
SNOW_LINE_SCHEMA = "metric-noise-snow-line-v2"
SNOW_LINE_CRITERION = "monthly_mean_temperature_below_zero_celsius"


def _wind_band_index(norm):
    """Finite band index from the normalized band coordinate; the only bearing rule."""
    magnitude = np.abs(norm)
    return np.where(magnitude < WIND_TRADE_BAND_LIMIT, 0,
                    np.where(magnitude < WIND_POLAR_BAND_LIMIT, 1, 2))


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
        raise ValueError("uint64 world seed required")
    if type(period_m) not in (int, float) or not math.isfinite(period_m) or period_m <= 0.:
        raise ValueError("positive finite latitude period required")
    z = np.asarray(z_m, np.float64)
    if not np.isfinite(z).all():
        raise ValueError("finite absolute metre coordinates required")
    # Phase reduction first: the periodic value of a huge coordinate stays accurate.
    phase = np.remainder(z / float(period_m), 1.)
    value = np.sin(2. * np.pi * phase)
    return float(value) if np.ndim(value) == 0 else value


def wind_unit(latitude_norm_value):
    """§4.1 prevailing bearing `(wx, wz)` from the normalized band coordinate only.

    Returned components are exactly `0` or `+-1` and the pair is a unit vector; the
    set of reachable values is finite, so all places on one band share one bearing.
    """
    try:
        value = float(latitude_norm_value)
    except (TypeError, ValueError):
        raise ValueError("finite scalar latitude band norm required")
    if not math.isfinite(value) or not -1. <= value <= 1.:
        raise ValueError("finite latitude band norm in [-1, 1] required")
    return WIND_BAND_UNITS[int(_wind_band_index(value))]


def _wind_unit_arrays(norm):
    """Array form of `wind_unit`, sharing the single band rule and the single table."""
    units = np.asarray(WIND_BAND_UNITS, np.int64)
    index = _wind_band_index(norm)
    return units[index, 0], units[index, 1]


@dataclass(frozen=True)
class RefinedClimateParameters:
    """v1 base scales plus the v2 refinement parameters; both enter the identity."""

    base: NoiseClimateParameters = NoiseClimateParameters()
    latitude_period_m: float = LATITUDE_PERIOD_M
    latitude_temperature_range_c: float = DEFAULT_LATITUDE_TEMPERATURE_RANGE_C
    latitude_precipitation_gain: float = DEFAULT_LATITUDE_PRECIPITATION_GAIN
    orographic_scale_m: float = DEFAULT_OROGRAPHIC_SCALE_M
    ridge_smoothing_taps: int = 3
    windward_gain_m: float = 5.
    lee_loss_m: float = 5.
    max_windward_gain: float = 1.
    min_lee_retention: float = .35
    annual_precipitation_min_mm: float = 100.
    annual_precipitation_max_mm: float = 3200.

    def __post_init__(self):
        if not isinstance(self.base, NoiseClimateParameters):
            raise ValueError("v1 NoiseClimateParameters base layer required")
        scalars = {name: getattr(self, name) for name in (
            "latitude_period_m", "latitude_temperature_range_c", "latitude_precipitation_gain",
            "orographic_scale_m", "windward_gain_m", "lee_loss_m",
            "max_windward_gain", "min_lee_retention",
            "annual_precipitation_min_mm", "annual_precipitation_max_mm")}
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in scalars.values()):
            raise ValueError("finite refinement parameters required")
        if (type(self.ridge_smoothing_taps) is not int or not 1 <= self.ridge_smoothing_taps <= 9
                or self.ridge_smoothing_taps % 2 == 0):
            raise ValueError("odd ridge smoothing tap count in 1..9 required")
        if self.latitude_period_m <= 0.:
            raise ValueError("positive latitude period required")
        if not -60. <= self.latitude_temperature_range_c <= 60.:
            raise ValueError("latitude temperature range must be within +-60 Celsius")
        if not 0. <= self.latitude_precipitation_gain <= 1.:
            raise ValueError("latitude precipitation gain must be in [0, 1]")
        if self.orographic_scale_m <= 0.:
            raise ValueError("positive orographic scale required")
        if self.windward_gain_m < 0. or self.lee_loss_m < 0.:
            raise ValueError("nonnegative windward gain and lee loss required")
        if self.max_windward_gain < 0.:
            raise ValueError("nonnegative windward gain ceiling required")
        if not 0. < self.min_lee_retention <= 1.:
            raise ValueError("lee retention must be in (0, 1]")
        if not 0. < self.annual_precipitation_min_mm < self.annual_precipitation_max_mm:
            raise ValueError("increasing positive precipitation bounds required")

    @property
    def identity_sha256(self):
        return identity({}, {"schema": CLIMATE_SCHEMA, "parameters": asdict(self)})

    @property
    def base_parameter_identity_sha256(self):
        """The reused v1 identity, reported as-is and never disguised as the v2 one."""
        return self.base.identity_sha256

    @property
    def wind_bearing_bands(self):
        """Bearing-band definition, reported so a drift is visible in every output."""
        return {"equator_side_below_norm": WIND_TRADE_BAND_LIMIT,
                "pole_side_at_or_above_norm": WIND_POLAR_BAND_LIMIT,
                "units": [list(unit) for unit in WIND_BAND_UNITS],
                "names": list(WIND_BAND_NAMES),
                "semantics": BAND_STRUCTURE_SEMANTICS}

    @property
    def ridge_offsets_m(self):
        """Odd tap offsets of the ridge smoother; a pure function of the parameters."""
        taps = self.ridge_smoothing_taps
        step = 0. if taps == 1 else self.orographic_scale_m / (taps - 1)
        return tuple((np.arange(taps) - (taps - 1) / 2.) * step)


def _resolve_elevation_sampler(seed, elevation_sampler):
    """Default sampler = the height component of `coarse_condition_field` (§4.3)."""
    if elevation_sampler is None:
        def elevation_sampler(x_m, z_m):
            return coarse_condition_field(seed, x_m, z_m)[0]
    elif not callable(elevation_sampler):
        raise ValueError("callable pure elevation sampler required")
    return elevation_sampler


def _sample_elevation(sampler, x_m, z_m):
    height = np.asarray(sampler(x_m, z_m), np.float64)
    try:
        return np.asarray(np.broadcast_to(height, np.broadcast(np.asarray(x_m), np.asarray(z_m)).shape), np.float64)
    except ValueError:
        raise ValueError("elevation sampler heights must broadcast to the query shape")


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
    x, z = _v1_coordinates(seed, x_m, z_m)
    shape = x.shape
    flat_x = np.ascontiguousarray(x.reshape(-1))
    flat_z = np.ascontiguousarray(z.reshape(-1))
    if flat_x.size == 1:
        return (np.ascontiguousarray(np.repeat(flat_x, 2)),
                np.ascontiguousarray(np.repeat(flat_z, 2)), shape, True)
    return flat_x, flat_z, shape, False


def _restore(value, shape, duplicated, dtype=np.float64):
    """Return a canonical-query result in the caller's own shape."""
    array = np.asarray(value, dtype).reshape(-1)
    if duplicated:
        array = array[:1]
    return array.reshape(shape)


def _restore_months(value, shape, duplicated):
    """Return a (k, ...) canonical-query result in the caller's own shape."""
    array = np.asarray(value, np.float64).reshape((np.shape(value)[0], -1))
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
        raise ValueError("RefinedClimateParameters required")
    sampler = _resolve_elevation_sampler(seed, elevation_sampler)
    flat_x, flat_z, shape, duplicated = _canonical_query(seed, x_m, z_m)
    offsets = parameters.ridge_offsets_m
    total = np.zeros(flat_x.shape, np.float64)
    for offset_z in offsets:
        for offset_x in offsets:
            height = _sample_elevation(sampler, flat_x + offset_x, flat_z + offset_z)
            if not np.isfinite(height).all():
                raise ValueError("finite elevation sampler heights required")
            total += height
    return _restore(total / len(offsets) ** 2, shape, duplicated)


def _orographic_gradient(seed, x, z, parameters, elevation_sampler):
    """The single upwind difference of §4.2; its only degree of freedom is the bearing."""
    bearing = latitude_norm(seed, z, parameters.latitude_period_m)
    wind_x, wind_z = _wind_unit_arrays(np.asarray(bearing, np.float64))
    scale = float(parameters.orographic_scale_m)
    here = ridge_height(seed, x, z, parameters=parameters, elevation_sampler=elevation_sampler)
    upwind = ridge_height(seed, x - wind_x * scale, z - wind_z * scale,
                          parameters=parameters, elevation_sampler=elevation_sampler)
    return (here - upwind) / scale


def _precipitation_multiplier(parameters, gradient):
    """§4.2 multi-branch-free multiplier plus its two geometry diagnostics.

    `shelter` is the negative part of the very same `gradient`, so there is one
    criterion and one place where a threshold could drift.
    """
    lift = np.maximum(gradient, 0.)
    shelter = np.maximum(-gradient, 0.)
    windward = np.clip(1. + parameters.windward_gain_m * lift, 0.,
                       1. + parameters.max_windward_gain)
    lee = np.clip(1. - parameters.lee_loss_m * shelter, parameters.min_lee_retention, 1.)
    return windward * lee, lift, shelter


def _refined_monthly_temperature(monthly_temperature, band, parameters):
    """§3.2 row 1: one band offset added to all twelve months.

    A structural short circuit at `latitude_temperature_range_c == 0.` returns the base
    months themselves, so the §7.1 bit-for-bit replay never pays for a redundant
    addition (and a `-0.0` base value can never be normalized to `+0.0`).
    """
    offset = parameters.latitude_temperature_range_c
    if offset == 0.:
        return monthly_temperature
    return monthly_temperature + offset * band


def _latitude_band_multiplier(parameters, band):
    """§3.2 row 2 synthetic three-band precipitation multiplier (dry-wet-dry; see the docstring).

    Exactly `1.` everywhere -- by construction, not by rounding -- while the row is
    switched off (`latitude_precipitation_gain = 0.`, contract §3.3), so the
    precipitation identity path of §7.1 stays bit for bit.
    """
    gain = parameters.latitude_precipitation_gain
    if gain == 0.:
        return np.ones_like(band)
    return 1. + gain * np.cos(np.pi * band)


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
    if bool(np.all(multiplier == 1.)):
        return monthly, annual_base, annual_base, False
    target = np.clip(annual_base * multiplier, parameters.annual_precipitation_min_mm,
                     parameters.annual_precipitation_max_mm)
    ratio = np.divide(target, annual_base, out=np.ones_like(annual_base), where=annual_base > 0.)
    scaled = monthly * ratio
    residual = target - scaled.sum(axis=0)
    # One exact repair into the wettest month of each point; no second threshold, no loop.
    flat = scaled.reshape(monthly.shape[0], -1)
    index = np.argmax(flat, axis=0)
    flat[index, np.arange(flat.shape[1])] += residual.reshape(-1)
    months = flat.reshape(monthly.shape)
    return months, months.sum(axis=0), target, True


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
        raise ValueError("RefinedClimateParameters required")
    flat_x, flat_z, shape, duplicated = _canonical_query(seed, x_m, z_m)
    base = _v1_sample_climate(seed, flat_x, flat_z, 0., parameters=parameters.base)
    band = np.asarray(latitude_norm(seed, flat_z, parameters.latitude_period_m), np.float64)
    temperature = _refined_monthly_temperature(base["monthly_temperature_c"], band, parameters)
    lapse = parameters.base.lapse_rate_c_per_m
    if lapse < 0.:
        freezing = np.where(temperature > 0., -temperature / lapse, 0.)
    else:
        freezing = np.full(temperature.shape, np.inf, np.float64)
    return {"monthly_first_freezing_elevation_m": _restore_months(freezing, shape, duplicated),
            "seasonal_snow_line_m": _restore(freezing.min(axis=0), shape, duplicated),
            "perennial_snow_line_m": _restore(freezing.max(axis=0), shape, duplicated),
            "snow_line_criterion": SNOW_LINE_CRITERION,
            "lapse_rate_c_per_m": lapse,
            "latitude_temperature_range_c": parameters.latitude_temperature_range_c,
            "latitude_band_norm": _restore(band, shape, duplicated),
            "base_parameter_identity_sha256": parameters.base_parameter_identity_sha256,
            "parameter_identity_sha256": parameters.identity_sha256,
            "schema": SNOW_LINE_SCHEMA, "semantics": SEMANTICS,
            "band_structure_semantics": BAND_STRUCTURE_SEMANTICS}


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
        raise ValueError("RefinedClimateParameters required")
    flat_x, flat_z, shape, duplicated = _canonical_query(seed, x_m, z_m)
    if elevation_m is None:
        elevation = _sample_elevation(_resolve_elevation_sampler(seed, elevation_sampler), flat_x, flat_z)
        if not np.isfinite(elevation).all():
            raise ValueError("finite elevation sampler heights required")
        elevation_source = ("coarse_condition_field_height_m" if elevation_sampler is None
                            else "caller_supplied_pure_sampler")
    else:
        elevation = np.broadcast_to(np.asarray(elevation_m, np.float64), shape).reshape(-1)
        if duplicated:
            elevation = np.repeat(elevation, 2)
        if not np.isfinite(elevation).all():
            raise ValueError("finite physical elevation required")
        elevation_source = "explicit_elevation_m"
    base = _v1_sample_climate(seed, flat_x, flat_z, elevation, parameters=parameters.base)
    base_monthly = base["monthly_precipitation_mm"]
    annual_base = base_monthly.sum(axis=0)
    band = np.asarray(latitude_norm(seed, flat_z, parameters.latitude_period_m), np.float64)
    gradient = _orographic_gradient(seed, flat_x, flat_z, parameters, elevation_sampler)
    orographic_multiplier, lift, shelter = _precipitation_multiplier(parameters, gradient)
    # Both multipliers are exactly 1. in their off position, and a product with an exact
    # 1. is exact, so the precipitation identity path of §7.1 is untouched by §3.2 row 2.
    band_multiplier = _latitude_band_multiplier(parameters, band)
    multiplier = orographic_multiplier * band_multiplier
    monthly, annual, annual_target, applied = _apply_precipitation_multiplier(
        base_monthly, annual_base, multiplier, parameters)
    base_temperature = base["monthly_temperature_c"]
    temperature = _refined_monthly_temperature(base_temperature, band, parameters)
    if applied or temperature is not base_temperature:
        # BIO definition of v1 (BIO1 mean, BIO4 sd*100, BIO12 sum, BIO15 CV*100) recomputed
        # on the refined months, so the §7.7 relations stay true in the modified state.
        bioclim = np.stack((np.mean(temperature, axis=0), np.std(temperature, axis=0) * 100.,
                            np.sum(monthly, axis=0),
                            np.std(monthly, axis=0) / np.mean(monthly, axis=0) * 100.))
    else:
        bioclim = base["BIO1_4_12_15"]
    wind_x, wind_z = _wind_unit_arrays(band)
    return {"monthly_temperature_c": _restore_months(temperature, shape, duplicated),
            "monthly_precipitation_mm": _restore_months(monthly, shape, duplicated),
            "BIO1_4_12_15": _restore_months(bioclim, shape, duplicated),
            "thermal_strength": _restore(base["thermal_strength"], shape, duplicated),
            "moisture_strength": _restore(base["moisture_strength"], shape, duplicated),
            "continentality_strength": _restore(base["continentality_strength"], shape, duplicated),
            "latitude_band_norm": _restore(band, shape, duplicated),
            "latitude_temperature_offset_c": _restore(
                band * parameters.latitude_temperature_range_c, shape, duplicated),
            "latitude_precipitation_multiplier": _restore(band_multiplier, shape, duplicated),
            "wind_unit": (_restore(wind_x, shape, duplicated, np.int64),
                          _restore(wind_z, shape, duplicated, np.int64)),
            "orographic_lift": _restore(lift, shape, duplicated),
            "orographic_shelter": _restore(shelter, shape, duplicated),
            "precipitation_multiplier": _restore(multiplier, shape, duplicated),
            "annual_precipitation_mm": _restore(annual, shape, duplicated),
            "annual_precipitation_target_mm": _restore(annual_target, shape, duplicated),
            "elevation_m": _restore(elevation, shape, duplicated),
            "elevation_source": elevation_source,
            "orographic_applied": applied,
            "base_parameter_identity_sha256": parameters.base_parameter_identity_sha256,
            "parameter_identity_sha256": parameters.identity_sha256,
            "schema": CLIMATE_SCHEMA, "semantics": SEMANTICS,
            "band_structure_semantics": BAND_STRUCTURE_SEMANTICS,
            "wind_bearing_bands": parameters.wind_bearing_bands}


def grid_rainfall_v2(seed, *, origin_xz_m, shape_zx, spacing_m, time_edges_s, elevation_sampler=None,
                     parameters=None, spatial_subsamples=2):
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
    parameters = parameters or RefinedClimateParameters()
    if not isinstance(parameters, RefinedClimateParameters):
        raise ValueError("RefinedClimateParameters required")
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
            flat_x = np.ascontiguousarray(np.asarray(x, np.float64).reshape(-1))
            flat_z = np.ascontiguousarray(np.asarray(z, np.float64).reshape(-1))
            gradient = _orographic_gradient(seed, flat_x, flat_z, parameters, elevation_sampler)
            orographic_multiplier = _precipitation_multiplier(parameters, gradient)[0]
            band = np.asarray(latitude_norm(seed, flat_z, parameters.latitude_period_m), np.float64)
            multiplier = orographic_multiplier * _latitude_band_multiplier(parameters, band)
            for index, (start, end) in enumerate(zip(edges, edges[1:])):
                intensity[index] += (multiplier * _v1_interval_mean_rain_mm_h(
                    seed, flat_x, flat_z, float(start), float(end), parameters=parameters.base)
                    ).reshape(tuple(shape_zx)) / spatial_subsamples ** 2
    metadata = {"schema": RAINFALL_SCHEMA, "seed": seed,
        "origin_xz_m": list(origin_xz_m), "shape_zx": list(shape_zx), "spacing_m": float(spacing_m),
        "time_edges_s": edges.tolist(), "parameters": asdict(parameters),
        "latitude_precipitation_gain": parameters.latitude_precipitation_gain,
        "base_parameter_identity_sha256": parameters.base_parameter_identity_sha256,
        "parameter_identity_sha256": parameters.identity_sha256,
        "spatial_mean": "equal_area_midpoint_subcells", "spatial_subsamples": spatial_subsamples,
        "cell_boundary_convention": "origin_is_center;subcells_cover_center_plus_minus_half_spacing",
        "absolute_weather_step_s": parameters.base.absolute_weather_step_s,
        "elevation_source": ("coarse_condition_field_height_m" if elevation_sampler is None
                             else "caller_supplied_pure_sampler"),
        "rainfall_composition": "v1_interval_mean_rain_mm_h_times_v2_annual_precipitation_multiplier",
        "monthly_target_is_not_realized_annual_forcing": True,
        "semantics": SEMANTICS, "band_structure_semantics": BAND_STRUCTURE_SEMANTICS,
        "wind_bearing_bands": parameters.wind_bearing_bands}
    metadata["source_identity_sha256"] = identity({}, metadata)
    forcing = RainfallForcing(edges, intensity, "synthetic_noise_terrain_climate_v2",
                              metadata["source_identity_sha256"])
    return forcing, metadata
