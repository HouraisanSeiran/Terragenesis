"""G3 seasonal air adapter: periodic monthly temperature and its declared calendar.

Role boundary (this module is an **adapter**, not a climate model)
------------------------------------------------------------------
Every physical number here comes from the existing v2 layer
(`terrain_pipeline.surface_rivers.metric_climate_refinement.sample_climate_v2`,
itself built on the frozen v1 `metric_noise_forcing.sample_climate`). This module
does **not** re-derive a single climatological formula: no new band rule, no new
lapse rate, no new wind table. It re-packages the v2 result as an explicit
**G3 exchange contract** so that S5 (PET/ET) and later G4/G7 can consume it
without guessing what a field means.

What this module answers
------------------------
* monthly and annual **temperature** on absolute world 30 m reference points;
* the **physical calendar** the months refer to (fixed 365-day year, explicit
  month edges in seconds, physical-time index, never a step counter);
* the **prevailing wind** and the exact rule and parameter identity it came from;
* the freezing month count derived **directly** from `monthly_temperature_c <= 0`
  (not from an inverted per-month elevation threshold, see below);
* optionally the existing snow-line diagnostic, passed through unchanged **and
  with its own elevation semantics stated** (it is not computed from the caller's
  elevation sampler, see "Snow line" below).

What this module explicitly does **not** answer (declared, never implied)
------------------------------------------------------------------------
* **No PET and no actual ET.** Temperature-index PET belongs to S5
  (`hydrology_seasonal.SeasonalConfig`), and `available_water` in A1 is a
  relative proxy, not ET. Copying either here would create a second truth.
* **No snowpack, no glacier, no melt.** A monthly-mean temperature crossing zero
  is a threshold diagnostic; it is not accumulation, not snow-water equivalent and
  not ice.
* **No real latitude** and no real climate class. `latitude_band_norm` is a
  synthetic east-west band coordinate (v2 §3.1); there is no degrees value here
  and no `latitude_deg` key is ever emitted.
* **No diurnal range.** A monthly mean is never a daily maximum or minimum.
* **No moisture budget.** Vapour inventory, boundary supply, depletion and
  recycling are G4 scope in a separate module; nothing here closes a water budget.

Why the freezing count is derived from temperature, not from the snow line
-------------------------------------------------------------------------
`metric_climate_refinement.snow_line` solves, per month, the elevation at which
that month's mean crosses 0 C (`h = -T / lapse_rate`). Those per-month thresholds
are only monotone in elevation if the lapse rate is strictly negative and the
month temperature is above zero at sea level; inverting them into a "how many
frozen months at this point" count is therefore not well defined for every point.
Counting `monthly_temperature_c <= 0` at the queried point needs no inversion and
cannot disagree with the temperature it is derived from. The snow-line diagnostic
is still available, but only as an optional pass-through field.

Snow line: its own elevation semantics, not the caller's
--------------------------------------------------------
`sample_climate_v2` and `snow_line` are two different calls with two different
elevation contracts. `snow_line(seed, x, z, parameters=...)` has **no** elevation
argument at all: it solves the crossing from the zero-elevation monthly means and
the lapse rate. Therefore:

* the returned `snow_line` block is **not** driven by the caller's
  `elevation_sampler` or `elevation_m`, and this module never labels it as
  "DEM-driven" or as sharing the elevation source of `monthly_temperature_c`;
* it is reported under its own key with its own declared source, and
  `snow_line_elevation_semantics` says so verbatim;
* it is never used to derive `freezing_month_count` or any temperature field.

Calendar, annual mean and period integration (three different averages)
----------------------------------------------------------------------
The calendar is the v1 month-day table: a fixed 365-day year, no leap day, no
epoch offset and no timezone; month identity repeats every `year_seconds`.

Three distinct quantities are reported and must not be conflated:

* `annual_mean_temperature_c` — the **unweighted arithmetic mean of the twelve
  monthly means**, which is exactly what v2 reports as `BIO1`. It is *not* a
  day-weighted annual mean; month lengths differ by up to three days, so this
  value can differ from a day-weighted mean by a small but real amount.
* `period_mean_temperature_c` — the interval mean over `time_edges_s` under the
  **month-center piecewise-linear convention** that
  `metric_noise_forcing.interval_mean_rain_mm_h` already uses for rain rates.
  A full-year interval therefore reproduces the `annual_weights`-weighted mean
  (trapezoid over month centers), which is a third, different number.
* the per-month values themselves.

None of the three is renamed into another's slot, and each carries its own
declared source note.

Period integration is bounded and free of large-magnitude cancellation
-------------------------------------------------------------------
The interval is assembled from short, local pieces instead of being computed as
`I(end) - I(start)` for one big antiderivative `I`:

* the tail of the start year, measured from the start's own within-year offset;
* `whole_years * annual_integral` in closed form;
* the head of the end year, measured from zero.

Work is therefore bounded by the *number of points and intervals*, never by the
*physical span*: a request covering thirty thousand years costs the same as one
covering a day. Avoiding the antiderivative difference matters numerically, not
just stylistically — near 1e12 s the two antiderivatives are ~1e12 in size, so
their difference loses roughly 1e-10 relative accuracy, which is far larger than
the tolerance any honest interval mean deserves.

Two guards keep that honest rather than merely fast:

* every segment must make progress (`upper > lower`); if floating point collapses
  the step to zero the call raises instead of spinning;
* an interval whose width is not resolvable at the magnitude of its endpoints
  (fewer than `MIN_INTERVAL_ULPS` units in the last place) is rejected, because
  the interval mean would be cancellation noise rather than a measurement.

Budget honesty
--------------
`MAX_SECONDS` is a **post-stage soft check**, not a hard interrupt: it can only
falsify a call after a stage returns, and it cannot interrupt a kernel that is
already stuck. The real protection is structural — bounded loops, a bounded
point count, and a byte budget checked **before** materialisation. Both facts are
stated in `describe()` so no reviewer can mistake one for the other.

Determinism and identity
------------------------
Identical inputs give identical bits in any window, array shape or call order
(guaranteed by v2's canonical query path); this module adds no cache and no
state.

The composite identity binds the **actual request and the actual output**, not
just the arguments: canonicalised coordinates, query shape, the elevation values
that were really used and their declared source, the twelve monthly temperatures,
the band coordinate, the wind bearing, the annual and period means, the calendar,
the parameters, and the source bytes of every kernel involved **including this
module**. Consequences, each covered by a test:

* a different point set, or the same point count at a different place, changes it;
* changing `elevation_m` (or the values a sampler returns) changes it;
* changing the query shape changes it, even for the same point set;
* a sampler is bound by the **values it returned**, never by its function name —
  two differently-named samplers returning identical heights are correctly the
  same product;
* permuting the request arrays does **not** change it: the arrays are canonically
  sorted by `(x, z)` before hashing, so identity is a property of the point set,
  not of request order. The returned arrays keep the caller's own order.
"""

from __future__ import annotations

import hashlib
import importlib
import math
import os
import time

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.surface_rivers.metric_climate_refinement import (
    CLIMATE_SCHEMA,
    LATITUDE_PERIOD_M,
    WIND_BAND_NAMES,
    WIND_BAND_UNITS,
    WIND_POLAR_BAND_LIMIT,
    WIND_TRADE_BAND_LIMIT,
    RefinedClimateParameters,
    sample_climate_v2,
    snow_line,
)
from terrain_pipeline.surface_rivers.metric_noise_forcing import (
    MONTH_CENTERS_S,
    MONTH_DAYS,
    MONTH_EDGES_S,
    YEAR_S,
)


SCHEMA = "environment-seasonal-air-v1"
CALENDAR_ALGORITHM = "fixed-365-day-month-table-v1"
INTERVAL_ALGORITHM = "whole_year_closed_form_plus_bounded_remainder_v2"

MAX_POINTS = 8192
#: Peak bytes for the period block, counted honestly: each interval result is
#: materialised once as a 1-D vector, collected in a list, then stacked into a
#: contiguous `(intervals, points)` array, so the peak is about twice the payload.
MAX_PERIOD_BYTES = 8 * 1024 * 1024
MAX_PERIOD_ENTRIES = MAX_PERIOD_BYTES // 16
#: Post-stage soft check only. It cannot interrupt a running kernel; the real
#: protection is the bounded loop and the byte budget. See the module docstring.
MAX_SECONDS = 60.0
GRID_SPACING_M = 30.0
GRID_ALIGN_ATOL = 1e-6

#: Largest physical time this entry point accepts, in seconds (~31 700 years).
#: Beyond it, double precision cannot resolve a one-day interval, so a "mean"
#: would be arithmetic noise. This is a declared domain, not a tuning knob.
MAX_TIME_S = 1.0e12
#: A sub-interval narrower than this many ulps of its endpoints is pure
#: cancellation after `I(end) - I(start)` and is rejected instead of returned.
MIN_INTERVAL_ULPS = 8.0
#: Maximum month-center segments a single remainder can touch (12 months, plus
#: the wrap segment, plus the segment containing the start).
MAX_REMAINDER_SEGMENTS = 14

#: Fields a caller must never expect from this entry point. Listed so that an
#: absence is a declared answer, not an accident.
NOT_RETURNED = (
    "potential_et",
    "actual_et",
    "available_water",
    "snowpack",
    "snow_water_equivalent",
    "glacier",
    "melt",
    "land_cover",
    "latitude_deg",
    "diurnal_temperature_range",
)

SEMANTICS = (
    "synthetic_monthly_mean_temperature_adapter_not_measured_weather; "
    "reuses_metric_climate_refinement_sample_climate_v2_without_new_formula"
)

#: The things this module refuses to overclaim, stated verbatim.
DECLARED_LIMITS = (
    "monthly mean temperature is not a daily maximum, a daily minimum or a "
    "diurnal range",
    "monthly_temperature_c <= 0 is a threshold diagnostic, not snowpack and not "
    "glacier mass balance",
    "temperature and prevailing wind share one synthetic band coordinate "
    "(latitude_norm); that is a declared synthetic compatibility assumption, not a "
    "dynamically consistent atmospheric circulation",
    "annual_mean_temperature_c is the unweighted mean of twelve monthly means (v2 "
    "BIO1), not a day-weighted annual mean",
    "the snow_line block has no elevation argument: it is solved from "
    "zero-elevation monthly means and the lapse rate, so it is not driven by the "
    "caller's elevation sampler",
    "MAX_SECONDS is a post-stage soft check that cannot interrupt a running "
    "kernel; bounded loops and the pre-materialisation byte budget are the real "
    "protection",
)

_DEPENDENCY_MODULES = (
    "terrain_pipeline.environment_seasonal_air",
    "terrain_pipeline.surface_rivers.metric_climate_refinement",
    "terrain_pipeline.surface_rivers.metric_noise_forcing",
    "terrain_pipeline.hydrology_planning",
)

UNITS = {
    "x_m": "m_easting",
    "z_m": "m_southing",
    "elevation_m": "m",
    "monthly_temperature_c": "degC_monthly_mean",
    "annual_mean_temperature_c": "degC_unweighted_mean_of_12_monthly_means",
    "period_mean_temperature_c": "degC_interval_mean_month_center_piecewise_linear",
    "seasonal_temperature_amplitude_c": "degC_monthly_max_minus_monthly_min",
    "latitude_band_norm": "1",
    "latitude_temperature_offset_c": "degC",
    "coldest_month_index": "month_ordinal_0_to_11",
    "warmest_month_index": "month_ordinal_0_to_11",
    "monthly_at_or_below_freezing": "bool",
    "freezing_month_count": "month_count_0_to_12",
    "has_freezing_month": "bool",
    "all_months_freezing": "bool",
    "wind_bearing_x": "1_east_positive",
    "wind_bearing_z": "1_south_positive",
    "wind_band_index": "ordinal_0_to_2",
    "wind_band_name": "label",
    "time_edges_s": "s_since_declared_epoch",
    "monthly_first_freezing_elevation_m": "m",
    "seasonal_snow_line_m": "m",
    "perennial_snow_line_m": "m",
}

#: Where each returned field comes from. Kept next to `UNITS` so a missing entry
#: is a test failure rather than a silent gap; no placeholder strings are allowed.
SOURCE_OF = {
    "x_m": "caller_supplied",
    "z_m": "caller_supplied",
    "elevation_m": "metric_climate_refinement sample_climate_v2 elevation_m",
    "monthly_temperature_c": "metric_climate_refinement.sample_climate_v2",
    "annual_mean_temperature_c": "derived: unweighted mean of the twelve monthly means",
    "period_mean_temperature_c": "derived: " + INTERVAL_ALGORITHM,
    "seasonal_temperature_amplitude_c": "derived: max minus min over the twelve months",
    "latitude_band_norm": "metric_climate_refinement.latitude_norm",
    "latitude_temperature_offset_c":
        "metric_climate_refinement sample_climate_v2 "
        "latitude_temperature_offset_c",
    "coldest_month_index": "derived: argmin over monthly_temperature_c",
    "warmest_month_index": "derived: argmax over monthly_temperature_c",
    "monthly_at_or_below_freezing": "derived: monthly_temperature_c <= 0",
    "freezing_month_count": "derived: count of monthly_temperature_c <= 0",
    "has_freezing_month": "derived: freezing_month_count > 0",
    "all_months_freezing": "derived: freezing_month_count == 12",
    "wind_bearing_x": "metric_climate_refinement sample_climate_v2 wind_unit",
    "wind_bearing_z": "metric_climate_refinement sample_climate_v2 wind_unit",
    "wind_band_index": "derived: latitude_norm against the imported band limits",
    "wind_band_name": "derived: WIND_BAND_NAMES at wind_band_index",
    "time_edges_s": "caller_supplied",
    "monthly_first_freezing_elevation_m":
        "metric_climate_refinement.snow_line (pass-through)",
    "seasonal_snow_line_m": "metric_climate_refinement.snow_line (pass-through)",
    "perennial_snow_line_m": "metric_climate_refinement.snow_line (pass-through)",
}


def calendar():
    """The physical calendar these months refer to, as a plain declaration.

    Returned as data (not as prose only) so a consumer can bind it into its own
    identity instead of assuming a year length.
    """
    return {
        "algorithm": CALENDAR_ALGORITHM,
        "interval_algorithm": INTERVAL_ALGORITHM,
        "month_days": [int(value) for value in MONTH_DAYS],
        "month_edges_s": [float(value) for value in MONTH_EDGES_S],
        "month_centers_s": [float(value) for value in MONTH_CENTERS_S],
        "days_per_year": int(MONTH_DAYS.sum()),
        "year_seconds": float(YEAR_S),
        "epoch_seconds": 0.0,
        "time_index": "physical seconds since the declared epoch; never a step counter",
        "declaration": (
            "fixed 365-day year taken from the v1 month-day table; no leap day, no "
            "epoch offset, no timezone and no latitude-dependent day length; month "
            "identity repeats every year_seconds"),
        "leap_day_handled": False,
        "day_length_varies_with_latitude": False,
    }


def _code_identities():
    """Source-byte identity of every kernel this adapter reuses, including itself.

    Purpose: the same parameters evaluated against a changed kernel must not yield
    the same composite identity. This is a binding, not an anti-tamper signature.
    """
    record = {}
    for name in _DEPENDENCY_MODULES:
        module = importlib.import_module(name)
        path = getattr(module, "__file__", None)
        if not path or not os.path.exists(path):
            raise ValueError("cannot locate source file for %s" % name)
        with open(path, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        record[name] = {"source_sha256": digest, "basename": os.path.basename(path)}
    return record


def _validate_seed(seed):
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError("seed must be a non-boolean integer")
    value = int(seed)
    if not 0 <= value < 2 ** 64:
        raise ValueError("seed must satisfy 0 <= seed < 2**64")
    return value


def _broadcast_points(x_m, z_m):
    """Broadcast the request, then check the point budget **before** materialising.

    `broadcast_arrays` does not allocate; the size check therefore rejects a huge
    broadcast shape before any array is built from it.
    """
    try:
        x, z = np.broadcast_arrays(np.asarray(x_m, np.float64), np.asarray(z_m, np.float64))
    except ValueError:
        raise ValueError("x_m and z_m must broadcast to a common shape")
    if x.size < 1 or x.size > MAX_POINTS:
        raise ValueError("point count %d outside 1..%d" % (x.size, MAX_POINTS))
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("finite absolute world coordinates required")
    if max(float(np.abs(x).max()), float(np.abs(z).max())) > 1e12:
        raise ValueError("bounded absolute meter coordinates required")
    return x, z


def _require_grid_aligned(values, name):
    """30 m grid reference points only; never snap, round or interpolate."""
    quotient = values / GRID_SPACING_M
    if not np.allclose(quotient, np.rint(quotient), rtol=0.0, atol=1e-8):
        raise ValueError(
            "%s must be an integer multiple of %.1f m (30 m grid reference points); "
            "this entry point never snaps or interpolates" % (name, GRID_SPACING_M))


def _validate_time_edges(time_edges_s, points):
    """Validate physical time edges and pre-check the period byte budget."""
    if time_edges_s is None:
        return None
    edges = np.asarray(time_edges_s, np.float64)
    if (edges.ndim != 1 or edges.size < 2 or not np.isfinite(edges).all()
            or np.any(np.diff(edges) <= 0.) or edges[0] < 0.):
        raise ValueError("increasing finite nonnegative physical time edges required")
    if float(edges[-1]) > MAX_TIME_S:
        raise ValueError(
            "time edge %r s exceeds the declared domain %.0e s: beyond it double "
            "precision cannot resolve a one-day interval and an interval mean would "
            "be cancellation noise" % (float(edges[-1]), MAX_TIME_S))
    entries = int(edges.size - 1) * int(points)
    if entries > MAX_PERIOD_ENTRIES:
        raise ValueError(
            "period temperature entries %d exceed the budget %d "
            "(peak about %.1f MiB counting the list plus the stacked array, not just "
            "the payload)" % (entries, MAX_PERIOD_ENTRIES, 16.0 * entries / 2 ** 20))
    return edges


def _unresolvable_interval(start_s, end_s):
    """True when `I(end) - I(start)` would be cancellation noise rather than a mean."""
    span = float(end_s) - float(start_s)
    if span <= 0.:
        return True
    magnitude = max(abs(float(start_s)), abs(float(end_s)))
    if magnitude == 0.:
        return False
    return span < MIN_INTERVAL_ULPS * float(np.spacing(magnitude))


def _wind_band_index(norm):
    """Band ordinal from the band coordinate, using the v2 public band limits.

    This repeats the *rule* only so it can be **cross-checked** against the
    `wind_unit` that v2 actually returned. A mismatch is raised as drift; it is
    never silently preferred over the v2 answer.
    """
    magnitude = np.abs(norm)
    return np.where(magnitude < WIND_TRADE_BAND_LIMIT, 0,
                    np.where(magnitude < WIND_POLAR_BAND_LIMIT, 1, 2))


def _annual_weights():
    """Trapezoid weights over month centers, wrapping across the year boundary."""
    gaps = np.diff(np.r_[MONTH_CENTERS_S, MONTH_CENTERS_S[0] + YEAR_S])
    return .5 * (gaps + np.roll(gaps, 1))


def _within_year_integral(monthly_flat, start_offset_s, end_offset_s):
    """Integral of the month-center piecewise-linear series over one sub-year window.

    Both offsets lie in `[0, year_seconds]` and are measured from a year boundary.
    At most `MAX_REMAINDER_SEGMENTS` month-center segments are touched, so the cost
    never depends on the physical span.

    `monthly_flat` is `(12, n)`; the result has shape `(n,)`.
    """
    total = np.zeros(monthly_flat.shape[1:], np.float64)
    lower = float(start_offset_s)
    target = float(end_offset_s)
    segments = 0
    while lower < target:
        segments += 1
        if segments > MAX_REMAINDER_SEGMENTS + 2:
            raise ValueError(
                "within-year integration exceeded %d month-center segments; this "
                "indicates a calendar defect rather than a large request"
                % (MAX_REMAINDER_SEGMENTS + 2))
        index = int(np.searchsorted(MONTH_CENTERS_S, lower, side="right")) - 1
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
            raise ValueError(
                "month-center integration made no progress at offset %r s (upper %r "
                "<= lower %r); refusing to spin instead of returning a corrupted mean"
                % (lower, upper, lower))
        fraction = (.5 * (lower + upper) - first_time) / (last_time - first_time)
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
    offset = math.fmod(moment, YEAR_S)
    years = int(round((moment - offset) / YEAR_S))
    return years, offset


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
    if not (math.isfinite(start) and math.isfinite(end)) or end <= start:
        raise ValueError("increasing finite physical interval required")
    if _unresolvable_interval(start, end):
        raise ValueError(
            "interval [%r, %r] s is narrower than %.0f ulps of its own magnitude "
            "(%r): the interval mean would be cancellation noise, so none is "
            "returned" % (start, end, MIN_INTERVAL_ULPS,
                          float(np.spacing(max(abs(start), abs(end))))))
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
        if end_offset > 0.:
            integral = integral + _within_year_integral(monthly_flat, 0., end_offset)
    return integral / span


def _canonical_order(x, z):
    """Stable `(x, z)` ordering so identity is a property of the point set.

    The returned arrays keep the caller's own order; only the digest sees this one.
    """
    return np.lexsort((z, x))


def _points_digest(x, z):
    order = _canonical_order(x, z)
    canonical = np.stack((np.ascontiguousarray(x[order]),
                          np.ascontiguousarray(z[order])), axis=1)
    return hashlib.sha256(np.ascontiguousarray(canonical).tobytes()).hexdigest()


def period_peak_bytes(points, intervals):
    """Peak period-related bytes, stated honestly (list plus stacked array)."""
    intervals = 0 if intervals is None else int(intervals)
    return int(16 * intervals * int(points))


def describe():
    """Static declaration for reviewers and downstream consumers; no numbers."""
    return {
        "schema": SCHEMA,
        "calendar": calendar(),
        "grid_spacing_m": GRID_SPACING_M,
        "max_points": MAX_POINTS,
        "max_period_entries": MAX_PERIOD_ENTRIES,
        "max_period_bytes": MAX_PERIOD_BYTES,
        "max_period_bytes_note": "peak period block; each interval is materialised "
                                 "once as a vector, collected in a list, then stacked",
        "max_time_s": MAX_TIME_S,
        "min_interval_ulps": MIN_INTERVAL_ULPS,
        "max_remainder_segments": MAX_REMAINDER_SEGMENTS,
        "max_seconds": MAX_SECONDS,
        "max_seconds_semantics": "post-stage soft check; it cannot interrupt a "
                                 "running kernel. Bounded loops plus the "
                                 "pre-materialisation byte budget are the real "
                                 "protection",
        "interval_algorithm": INTERVAL_ALGORITHM,
        "interval_algorithm_note": (
            "assembled from the start-year tail, closed-form whole years and the "
            "end-year head; never a difference of two large antiderivatives"),
        "units": dict(UNITS),
        "source_of": dict(SOURCE_OF),
        "semantics": SEMANTICS,
        "declared_limits": list(DECLARED_LIMITS),
        "not_returned": list(NOT_RETURNED),
        "identity_binds": [
            "canonically sorted (x, z) coordinates",
            "query shape",
            "the elevation values actually used and their declared source",
            "all twelve monthly temperatures",
            "latitude band and band temperature offset",
            "wind bearing and band index",
            "annual mean, amplitude, freezing count",
            "period means when time edges are given",
            "calendar, parameters, wind rule",
            "source bytes of every dependency kernel, including this module",
        ],
        "identity_order_contract": (
            "the digest is computed over arrays sorted by (x, z), so permuting the "
            "request arrays does not change the identity; the returned arrays keep "
            "the caller's order"),
        "sampler_identity_contract": (
            "an elevation sampler is bound by the values it returned, never by its "
            "function name; two samplers returning identical heights are the same "
            "product by construction"),
        "reused_entries": [
            "terrain_pipeline.surface_rivers.metric_climate_refinement.sample_climate_v2",
            "terrain_pipeline.surface_rivers.metric_climate_refinement.snow_line "
            "(optional pass-through only, with its own elevation semantics)",
        ],
        "wind_rule_source": (
            "metric_climate_refinement.latitude_norm -> WIND_BAND_UNITS; the rule and "
            "the three-band table are imported, never re-derived here"),
        "never": [
            "temperature-index PET or actual ET (owned by S5)",
            "snowpack, snow-water equivalent, glacier or melt",
            "a real latitude, a Koeppen class or a measured climatology",
            "a moisture or vapour budget (G4 scope, separate module)",
            "silently preferring a locally re-derived wind band over the v2 answer",
            "calling MAX_SECONDS a hard interrupt",
            "calling annual_mean_temperature_c a day-weighted annual mean",
            "labelling the snow-line block as sampler-driven",
        ],
    }


def sample_seasonal_air(seed, x_m, z_m, *, elevation_m=None, elevation_sampler=None,
                        parameters=None, time_edges_s=None, include_snow_line=False):
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
    seed = _validate_seed(seed)
    if parameters is None:
        parameters = RefinedClimateParameters()
    elif not isinstance(parameters, RefinedClimateParameters):
        raise ValueError(
            "parameters must be None or a RefinedClimateParameters instance, got %r; "
            "a falsy non-None value is rejected instead of silently defaulting"
            % type(parameters).__name__)
    if not isinstance(include_snow_line, bool):
        raise ValueError("include_snow_line must be a bool")
    started = time.perf_counter()

    def check_time(stage):
        """Post-stage soft check: reports lateness, cannot interrupt a kernel."""
        elapsed = time.perf_counter() - started
        if elapsed > MAX_SECONDS:
            raise ValueError(
                "single call passed the %.0f s soft budget after stage %r (%.3f s); "
                "this check cannot interrupt a running kernel, it only falsifies the "
                "result" % (MAX_SECONDS, stage, elapsed))
        return elapsed

    x, z = _broadcast_points(x_m, z_m)
    _require_grid_aligned(x, "x_m")
    _require_grid_aligned(z, "z_m")
    edges = _validate_time_edges(time_edges_s, x.size)
    shape = x.shape
    flat_x = np.ascontiguousarray(x.reshape(-1))
    flat_z = np.ascontiguousarray(z.reshape(-1))

    air = sample_climate_v2(seed, x, z, elevation_m, parameters=parameters,
                            elevation_sampler=elevation_sampler)
    temperature = np.asarray(air["monthly_temperature_c"], np.float64)
    if temperature.shape != (12,) + shape:
        raise ValueError("v2 monthly temperature shape drift")
    if not np.isfinite(temperature).all():
        raise ValueError("v2 returned a non-finite monthly temperature")
    band = np.asarray(air["latitude_band_norm"], np.float64)
    if band.shape != shape or not np.isfinite(band).all():
        raise ValueError("v2 latitude band shape or finiteness drift")
    elevation = np.asarray(air["elevation_m"], np.float64).reshape(shape)
    if not np.isfinite(elevation).all():
        raise ValueError(
            "non-finite elevation reached this layer; a sampler returning NaN or inf "
            "is rejected here as well as in the v2 kernel")
    elevation_source = air["elevation_source"]
    check_time("climate")

    # --- freezing count straight from the temperature, no threshold inversion ---
    at_or_below_freezing = temperature <= 0.
    freezing_month_count = np.count_nonzero(at_or_below_freezing, axis=0).astype(np.int64)
    has_freezing_month = freezing_month_count > 0
    all_months_freezing = freezing_month_count == 12
    coldest = np.argmin(temperature, axis=0).astype(np.int64)
    warmest = np.argmax(temperature, axis=0).astype(np.int64)
    annual_mean = np.mean(temperature, axis=0)
    amplitude = np.max(temperature, axis=0) - np.min(temperature, axis=0)
    offset = np.asarray(air["latitude_temperature_offset_c"], np.float64).reshape(shape)
    if not np.isfinite(offset).all():
        raise ValueError("non-finite band temperature offset")

    # --- wind: read the v2 answer, then verify the band rule did not drift ------
    wind_x, wind_z = air["wind_unit"]
    wind_x = np.asarray(wind_x, np.int64).reshape(shape)
    wind_z = np.asarray(wind_z, np.int64).reshape(shape)
    band_index = np.asarray(_wind_band_index(band), np.int64).reshape(shape)
    expected = np.asarray(WIND_BAND_UNITS, np.int64)
    if not (np.array_equal(expected[band_index, 0], wind_x)
            and np.array_equal(expected[band_index, 1], wind_z)):
        raise ValueError(
            "wind band rule drift: the v2 returned wind_unit does not match "
            "WIND_BAND_UNITS at the declared band limits; refusing to guess which "
            "answer is authoritative")
    band_names = np.asarray(WIND_BAND_NAMES, dtype=object)[band_index]
    check_time("wind")

    # --- period temperature: whole years closed form, bounded remainder ---------
    period = None
    if edges is not None:
        flat = np.ascontiguousarray(temperature.reshape(12, -1))
        intervals = [
            _interval_mean_monthly(flat, float(start), float(end))
            for start, end in zip(edges, edges[1:])]
        period = np.stack(intervals).reshape((edges.size - 1,) + shape)
        if not np.isfinite(period).all():
            raise ValueError("non-finite period mean temperature")
    check_time("period")

    # --- optional snow line: pass-through with its own elevation semantics ------
    snow = None
    if include_snow_line:
        snow = snow_line(seed, x, z, parameters=parameters)
        for key in ("seasonal_snow_line_m", "perennial_snow_line_m"):
            values = np.asarray(snow[key], np.float64)
            if values.size == 0:
                raise ValueError("empty snow-line diagnostic")
    check_time("snow_line")

    # --- composite identity: binds the request AND the realised output ----------
    code_identities = _code_identities()
    order = _canonical_order(flat_x, flat_z)
    arrays = {
        "canonical_x_m": np.ascontiguousarray(flat_x[order]),
        "canonical_z_m": np.ascontiguousarray(flat_z[order]),
        "canonical_elevation_m": np.ascontiguousarray(elevation.reshape(-1)[order]),
        "canonical_monthly_temperature_c": np.ascontiguousarray(
            temperature.reshape(12, -1)[:, order].T),
        "canonical_latitude_band_norm": np.ascontiguousarray(band.reshape(-1)[order]),
        "canonical_latitude_temperature_offset_c":
            np.ascontiguousarray(offset.reshape(-1)[order]),
        "canonical_wind_bearing": np.ascontiguousarray(
            np.stack((wind_x.reshape(-1)[order], wind_z.reshape(-1)[order]), axis=1)),
        "canonical_annual_mean_temperature_c":
            np.ascontiguousarray(annual_mean.reshape(-1)[order]),
        "canonical_seasonal_temperature_amplitude_c":
            np.ascontiguousarray(amplitude.reshape(-1)[order]),
        "canonical_freezing_month_count":
            np.ascontiguousarray(freezing_month_count.reshape(-1)[order]),
    }
    if period is not None:
        arrays["canonical_period_mean_temperature_c"] = np.ascontiguousarray(
            period.reshape(period.shape[0], -1)[:, order])

    record = {
        "schema": SCHEMA,
        "world_seed": seed,
        "grid_spacing_m": GRID_SPACING_M,
        "point_count": int(x.size),
        "query_shape": [int(value) for value in shape],
        "query_rank": int(len(shape)),
        "points_digest": _points_digest(flat_x, flat_z),
        "canonical_order": "lexsort by (x, z); canonical for the digest only, never "
                           "for the returned arrays",
        "calendar": calendar(),
        "climate_schema": CLIMATE_SCHEMA,
        "v2_parameter_identity_sha256": parameters.identity_sha256,
        "v1_base_parameter_identity_sha256": parameters.base_parameter_identity_sha256,
        "latitude_period_m": float(LATITUDE_PERIOD_M),
        "latitude_temperature_range_c": float(parameters.latitude_temperature_range_c),
        "elevation_source": elevation_source,
        "elevation_sampler_identity": (
            "bound by the values returned, not by the callable's name"),
        "wind": {
            "rule": "latitude_norm -> _wind_band_index(WIND_TRADE_BAND_LIMIT, "
                    "WIND_POLAR_BAND_LIMIT) -> WIND_BAND_UNITS",
            "trade_band_limit": float(WIND_TRADE_BAND_LIMIT),
            "polar_band_limit": float(WIND_POLAR_BAND_LIMIT),
            "units": [list(unit) for unit in WIND_BAND_UNITS],
            "names": list(WIND_BAND_NAMES),
            "parameter_identity_sha256": parameters.identity_sha256,
            "consistency_check": "returned v2 wind_unit re-verified against the "
                                 "imported table; drift raises instead of guessing",
        },
        "period": None if edges is None else {
            "algorithm": INTERVAL_ALGORITHM,
            "time_edges_s": [float(value) for value in edges],
            "declaration": "start-year tail, closed-form whole years and end-year "
                           "head over month centers, wrapping at the year boundary; "
                           "same convention as the v1 interval rain integral, "
                           "applied to temperature; never a difference of two large "
                           "antiderivatives",
            "cost_bound": "bounded by MAX_REMAINDER_SEGMENTS per piece, not by "
                          "the physical span",
        },
        "snow_line_requested": bool(include_snow_line),
        "snow_line_elevation_semantics": (
            "snow_line has no elevation argument: it is solved from zero-elevation "
            "monthly means and the lapse rate, so it is NOT driven by the caller's "
            "elevation sampler and is not labelled DEM-driven"),
        "annual_mean_semantics": (
            "unweighted arithmetic mean of the twelve monthly means (equals v2 "
            "BIO1); not day-weighted"),
        "declared_limits": list(DECLARED_LIMITS),
        "code_identities": code_identities,
        "semantics": SEMANTICS,
    }
    identity_sha256 = identity(arrays, record)

    return {
        "schema": SCHEMA,
        "shape": [int(value) for value in shape],
        "x_m": x, "z_m": z,
        "calendar": calendar(),
        "monthly_temperature_c": temperature,
        "annual_mean_temperature_c": annual_mean,
        "seasonal_temperature_amplitude_c": amplitude,
        "coldest_month_index": coldest,
        "warmest_month_index": warmest,
        "monthly_at_or_below_freezing": at_or_below_freezing,
        "freezing_month_count": freezing_month_count,
        "has_freezing_month": has_freezing_month,
        "all_months_freezing": all_months_freezing,
        "latitude_band_norm": band,
        "latitude_temperature_offset_c": offset,
        "wind_bearing_x": wind_x,
        "wind_bearing_z": wind_z,
        "wind_band_index": band_index,
        "wind_band_name": band_names,
        "elevation_m": elevation,
        "elevation_source": elevation_source,
        "period_mean_temperature_c": period,
        "time_edges_s": None if edges is None else edges,
        "snow_line": snow,
        "sources": {
            "x_m": {"source": SOURCE_OF["x_m"], "units": UNITS["x_m"],
                    "note": "absolute world metres, 30 m grid reference points; "
                            "never snapped or interpolated"},
            "z_m": {"source": SOURCE_OF["z_m"], "units": UNITS["z_m"],
                    "note": "absolute world metres, 30 m grid reference points"},
            "monthly_temperature_c": {
                "source": SOURCE_OF["monthly_temperature_c"],
                "units": UNITS["monthly_temperature_c"],
                "note": "monthly mean; not a daily maximum, minimum or diurnal range",
            },
            "annual_mean_temperature_c": {
                "source": SOURCE_OF["annual_mean_temperature_c"],
                "units": UNITS["annual_mean_temperature_c"],
                "note": "equals the v2 BIO1 of the same months; NOT day-weighted, "
                        "because month lengths differ",
            },
            "period_mean_temperature_c": {
                "source": SOURCE_OF["period_mean_temperature_c"],
                "units": UNITS["period_mean_temperature_c"],
                "note": "month-center piecewise linear, wrapping at the year "
                        "boundary; a full-year interval reproduces the "
                        "annual_weights-weighted mean, which is a third value "
                        "distinct from both annual_mean_temperature_c and the "
                        "day-weighted mean",
            },
            "seasonal_temperature_amplitude_c": {
                "source": SOURCE_OF["seasonal_temperature_amplitude_c"],
                "units": UNITS["seasonal_temperature_amplitude_c"],
            },
            "latitude_band_norm": {
                "source": SOURCE_OF["latitude_band_norm"],
                "units": UNITS["latitude_band_norm"],
                "note": "synthetic east-west band; not a real latitude and never "
                        "converted to degrees",
            },
            "latitude_temperature_offset_c": {
                "source": SOURCE_OF["latitude_temperature_offset_c"],
                "units": UNITS["latitude_temperature_offset_c"],
                "note": "one band offset applied to all twelve months",
            },
            "coldest_month_index": {
                "source": SOURCE_OF["coldest_month_index"],
                "units": UNITS["coldest_month_index"],
            },
            "warmest_month_index": {
                "source": SOURCE_OF["warmest_month_index"],
                "units": UNITS["warmest_month_index"],
            },
            "monthly_at_or_below_freezing": {
                "source": SOURCE_OF["monthly_at_or_below_freezing"],
                "units": UNITS["monthly_at_or_below_freezing"],
                "note": "threshold diagnostic per month; not a phase state",
            },
            "freezing_month_count": {
                "source": SOURCE_OF["freezing_month_count"],
                "units": UNITS["freezing_month_count"],
                "note": "a threshold diagnostic; not snowpack, snow-water "
                        "equivalent, glacier or melt",
                "inversion_avoided": "per-month snow-line elevations are not "
                                     "inverted into a month count",
            },
            "has_freezing_month": {
                "source": SOURCE_OF["has_freezing_month"],
                "units": UNITS["has_freezing_month"],
            },
            "all_months_freezing": {
                "source": SOURCE_OF["all_months_freezing"],
                "units": UNITS["all_months_freezing"],
            },
            "wind_bearing_x": {
                "source": SOURCE_OF["wind_bearing_x"],
                "units": UNITS["wind_bearing_x"],
                "note": "axial unit vector from the synthetic band; not a measured "
                        "wind and not a continuous stress",
            },
            "wind_bearing_z": {
                "source": SOURCE_OF["wind_bearing_z"],
                "units": UNITS["wind_bearing_z"],
            },
            "wind_band_index": {
                "source": SOURCE_OF["wind_band_index"],
                "units": UNITS["wind_band_index"],
            },
            "wind_band_name": {
                "source": SOURCE_OF["wind_band_name"],
                "units": UNITS["wind_band_name"],
                "note": "synthetic band label; not a climatological zone name",
            },
            "elevation_m": {
                "source": SOURCE_OF["elevation_m"],
                "units": UNITS["elevation_m"],
                "note": "the value v2 actually used for the lapse rate; "
                        "elevation_source says where it came from",
            },
            "time_edges_s": {
                "source": SOURCE_OF["time_edges_s"],
                "units": UNITS["time_edges_s"],
                "note": "none when no period was requested",
            },
            "monthly_first_freezing_elevation_m": {
                "source": SOURCE_OF["monthly_first_freezing_elevation_m"],
                "units": UNITS["monthly_first_freezing_elevation_m"],
                "note": "per month; the elevation where that month's mean starts "
                        "dropping below zero",
            },
            "seasonal_snow_line_m": {
                "source": SOURCE_OF["seasonal_snow_line_m"],
                "units": UNITS["seasonal_snow_line_m"],
                "note": "the lowest monthly first-freezing elevation of the year",
            },
            "perennial_snow_line_m": {
                "source": SOURCE_OF["perennial_snow_line_m"],
                "units": UNITS["perennial_snow_line_m"],
                "note": "the highest monthly first-freezing elevation of the year",
            },
            "snow_line": {
                "source": "metric_climate_refinement.snow_line (pass-through)",
                "units": "m",
                "note": "solved from zero-elevation monthly means and the lapse "
                        "rate; NOT driven by the caller's elevation sampler; never "
                        "a precipitation term and never snowpack",
            },
        },
        "units": dict(UNITS),
        "identity": {"identity_sha256": identity_sha256,
                     "parameter_identity_sha256": parameters.identity_sha256,
                     "base_parameter_identity_sha256":
                         parameters.base_parameter_identity_sha256,
                     "points_digest": record["points_digest"],
                     "record": record},
        "code_identities": code_identities,
        "cost": {"seconds": round(check_time("identity"), 3),
                 "max_seconds": MAX_SECONDS,
                 "max_seconds_semantics": "post-stage soft check; cannot interrupt "
                                          "a running kernel",
                 "period_peak_bytes": period_peak_bytes(
                     x.size, None if edges is None else edges.size - 1),
                 "rss_note": "do not read this as tree RSS; process RSS is measured "
                             "by the caller/driver"},
        "semantics": SEMANTICS,
        "declared_limits": list(DECLARED_LIMITS),
        "not_returned": list(NOT_RETURNED),
        "notes": [
            "adapter only: every physical quantity comes from sample_climate_v2 or "
            "from a declared derivation over its output",
            "no PET, no actual ET, no snowpack, no glacier, no land cover are "
            "returned; those belong to S5, S7 and later cards",
            "the vapour budget (boundary supply, depletion, recycling) is G4 scope "
            "and is deliberately absent here",
            "does not feed the default world, the M1-M4 finite-river product or any "
            "seasonal hydrology run; wiring is a separate card",
        ],
    }
