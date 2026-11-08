"""PET/ET adapter and water ledger over the repository's existing soil bucket (G5 first card).

What this module is
-------------------
An **adapter plus ledger**, not a new physical law. It

1. computes potential evapotranspiration from an explicit monthly-mean temperature
   input using the repository's **existing** temperature-index model,
2. splits every declared physical interval on the real 365-day calendar, so an
   interval that crosses a month or a year boundary is integrated month by month
   instead of being attributed to a single month,
3. applies the repository's **existing** soil bucket
   (``terrain_pipeline.regional_surface_forcing.advance_soil``) once per interval,
   realising a per-cell PET rate by **exact scalar grouping** (``RunoffParameters``
   carries a scalar ``potential_et_mm_h``; see :func:`advance_pet_et` and
   :func:`preflight`), and
4. reports an auditable water ledger. The **main account** is
   ``delta(soil+fast+slow) = liquid_rain - actual_ET - release``; the **soil
   sub-account** is an independent audit recomputed here from the same parameters
   and must reproduce the bucket's soil edge bit for bit, otherwise it is reported
   as a mismatch rather than presented as truth.

The PET expression lives in exactly one place here,
:func:`temperature_index_pet_rate_mm_h`, and is a **declared synonymous expression**
of the existing model at ``terrain_pipeline/hydrology_seasonal.py:74`` (source
identity :data:`SEASONAL_SOURCE_SHA256`)::

    potential_et_mm = pet_base_mm_per_day
                    + pet_temperature_mm_per_day_c * max(temperature, 0.0)

The only differences are (a) the parameters are read from
:class:`terrain_pipeline.hydrology_seasonal.SeasonalConfig` instead of being inlined,
and (b) the result is converted from mm/day to mm/hour by dividing by 24. The old
function is never imported for its body, never monkeypatched and never invoked
through a fabricated plan: ``seasonal_climate`` resamples the v1 climate internally,
so calling it here would silently substitute a v1 temperature for the caller's
v2/G3 temperature.

What this module explicitly does NOT do
---------------------------------------
* no second soil bucket and no second PET formula (see :data:`LIMITATIONS`),
* no river network, no channel, no routing and no boundary condition: this entry
  point has no boundary API at all, so no ``unknown_boundary`` gate is faked here,
* no aquifer, no groundwater baseflow, no deep loss: ``slow`` is an **internal**
  store, not a deep outlet, and the internal ``percolation -> slow -> slow_release``
  path is not deducted twice,
* no snowpack depth and no glacier: solid precipitation is withheld from the bucket
  and reported as an equivalent water depth (``solid_precipitation_swe_mm``); snow
  depth would need a density this stage does not have, and the G7 snow store is
  ``not_modeled``,
* no calibration claim: the PET parameters are declared engineering assumptions
  reused from ``SeasonalConfig``, not a fit to observations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import importlib
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.runoff import SeasonalConfig as SeasonalConfig
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.regional_surface_forcing import advance_soil
from terrain_pipeline.surface_rivers.metric_noise_forcing import (
    MONTH_DAYS, MONTH_EDGES_S, YEAR_S)


__all__ = [
    "ALGORITHM",
    "BUCKET_MODULE",
    "CHECKPOINT_SCHEMA",
    "LIMITATIONS",
    "PetEtParameters",
    "PHASE_SCHEMA",
    "SCHEMA",
    "SUBSTEP_POLICY",
    "SUBSTEP_STATUS",
    "SUBSTEP_WORST_CASE_PER_INTERVAL",
    "advance_pet_et",
    "advance_pet_et_segment",
    "calendar_month_seconds",
    "describe",
    "interval_pet_mm",
    "liquid_fraction",
    "load_pet_et_checkpoint",
    "model_identity",
    "monthly_potential_et_mm",
    "parameters_from_seasonal_config",
    "pet_parameter_identity",
    "preflight",
    "save_pet_et_checkpoint",
    "temperature_index_pet_rate_mm_h",
]


ALGORITHM = "pet-et-adapter-v1"
SCHEMA = "metric-pet-et-v1"
PHASE_SCHEMA = "declared-freezing-threshold-v1"
CHECKPOINT_SCHEMA = "metric-pet-et-checkpoint-v1"
PET_PARAMETER_SCHEMA = "metric-pet-parameters-v1"

#: The single bucket this adapter drives. It is imported, never copied.
BUCKET_MODULE = "terrain_pipeline.regional_surface_forcing.advance_soil"

#: 每一条模型依赖的源码字节（不是只有模块名字）都会进 ``model_identity``。
#: 本模块自己也在表里：换掉适配器自身的任何一个字节，身份就变。
_IDENTITY_MODULES = (
    ("terrain_pipeline.surface_rivers.metric_pet_et", "metric_pet_et.py"),
    ("terrain_pipeline.regional_surface_forcing", "regional_surface_forcing.py"),
    ('terrain_pipeline.runoff', "rainfall_runoff.py"),
    ('terrain_pipeline.runoff', "hydrology_seasonal.py"),
    ("terrain_pipeline.surface_rivers.metric_noise_forcing", "metric_noise_forcing.py"),
)

#: Source identity of the existing temperature-index model this adapter expresses.
SEASONAL_SOURCE_PATH = "terrain_pipeline/hydrology_seasonal.py"
SEASONAL_SOURCE_SHA256 = (
    "43f07b683a40c5e9bb1afe5440bda63e131744fbb68e7af4623d44ea770a1e05")
SEASONAL_PET_LINE = 74
SEASONAL_PET_EXPRESSION = (
    "potential_et_mm = pet_base_mm_per_day + pet_temperature_mm_per_day_c * "
    "np.maximum(temperature, 0)")

#: The declared phase criterion reuses the existing snow-line *semantics*.
#: ``SNOW_LINE_CRITERION`` in ``metric_climate_refinement.py:156`` is a **string
#: constant**, not a phase function; the numeric threshold is a parameter here.
PHASE_SOURCE = (
    "reuses the semantics of metric_climate_refinement.SNOW_LINE_CRITERION "
    "('monthly_mean_temperature_below_zero_celsius'); that constant is a string, "
    "not a phase function, so the numeric threshold is an explicit parameter")
PHASE_SEMANTICS = "declared_monthly_mean_threshold_not_daily_phase"

NOT_AVAILABLE = "not_available"
NOT_MODELED = "not_modeled"

#: What actually happens at a calendar month/year boundary inside one requested interval.
SUBSTEP_POLICY = (
    "the bucket is advanced once per calendar piece of the interval (month and year edges), "
    "each piece with that month's own PET rate and its own phase decision; the requested "
    "interval only aggregates the per-piece outputs. An interval that straddles a month "
    "edge under a supply limit is therefore equal to running the pieces separately, which "
    "is asserted by the tests. No daily or diurnal variation is introduced")
SUBSTEP_STATUS = "substepped_at_calendar_edges"

TEMPERATURE_SOURCES = (
    "caller_declared_monthly_mean",
    "g3_monthly_mean",
    "a1_published_monthly_mean",
)
RAIN_SOURCES = ("declared_event", "background_estimate")

MAX_CELLS = 4096
MAX_INTERVALS = 8760
#: Worst case number of calendar sub-steps one interval can be split into. A 3600 s
#: interval can only straddle one month edge, so at most 2 pieces (the 12th month plus the
#: year edge is still one boundary). Declared so the budget is not optimistic.
SUBSTEP_WORST_CASE_PER_INTERVAL = 2
MAX_CELL_INTERVALS = 2_000_000
MAX_OUTPUT_BYTES = 128 * 1024 * 1024

#: Per-interval ``(T, N)`` float64 fields written by :func:`advance_pet_et`.
INTERVAL_FLOAT_FIELDS = (
    "rain_mm",
    "liquid_rate_mm_h",
    "liquid_rain_mm",
    "solid_precipitation_swe_mm",
    "liquid_fraction",
    "interval_pet_mm",
    "pet_rate_mm_h",
    "actual_et_mm",
    "release_mm",
    "subsurface_transfer_mm",
    "infiltration_mm",
    "storage_change_mm",
    "available_supply_mm",
)
#: Per-edge ``(T+1, N)`` float64 fields.
EDGE_FLOAT_FIELDS = ("soil_edge_mm", "fast_edge_mm", "slow_edge_mm")
#: Per-interval ``(T,)`` int64 fields.
INTERVAL_INT_FIELDS = ("substeps_per_interval",)
#: Monthly ``(12, N)`` float64 fields.
MONTHLY_FLOAT_FIELDS = (
    "monthly_temperature_c", "monthly_potential_et_mm", "calendar_month_seconds")
#: ``(T, N)`` regime labels (fixed-width unicode).
REGIME_FIELD = "et_regime"
REGIME_WIDTH = 16

LIMITATIONS = (
    "PET/ET adapter only: it copies no bucket and no PET formula, it drives "
    "regional_surface_forcing.advance_soil with an exact per-cell scalar PET rate.",
    "available_water from metric_soil_condition is never used as storage and never "
    "used as actual ET; storage is the bucket's own soil/fast/slow states.",
    "monthly precipitation totals are never turned into a single storm event; the "
    "caller must declare interval-average rain on explicit physical time edges.",
    "solid_precipitation_swe_mm is an equivalent water depth of withheld solid input, "
    "not a snow depth (no density) and not a snowpack state.",
    "slow is an internal store fed by percolation; it is not an aquifer and its "
    "release is not a groundwater baseflow.",
    "no channel, no routing, no boundary condition and no natural-outlet claim.",
    "the PET parameters are declared engineering assumptions reused from "
    "SeasonalConfig; they are not calibrated and this module reports no Hargreaves "
    "or FAO comparison.",
    "RunoffParameters.initial_soil_mm/initial_fast_mm/initial_slow_mm are ignored: "
    "the initial states are the explicit ``states`` argument.",
)


# --------------------------------------------------------------------------- #
# parameters
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PetEtParameters:
    """PET parameters (reused from ``SeasonalConfig``) plus the declared phase threshold.

    ``runoff`` carries the bucket parameters. Its ``potential_et_mm_h`` is
    **overridden per group** at call time with the exact per-cell PET rate; keeping
    the field here only means the other six bucket parameters are stated in one
    place and enter the model identity.
    """

    pet_base_mm_per_day: float = 0.5
    pet_temperature_mm_per_day_c: float = 0.12
    freezing_threshold_c: float = 0.0
    runoff: RunoffParameters = field(default_factory=RunoffParameters)

    def __post_init__(self):
        for name in ("pet_base_mm_per_day", "pet_temperature_mm_per_day_c"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0.0):
                raise ValueError(
                    "invalid %s: a finite nonnegative number is required" % (name,))
        threshold = self.freezing_threshold_c
        if (isinstance(threshold, bool) or not isinstance(threshold, (int, float))
                or not math.isfinite(threshold)):
            raise ValueError(
                "invalid freezing_threshold_c: a finite number is required")
        if not isinstance(self.runoff, RunoffParameters):
            raise ValueError("runoff must be a RunoffParameters instance")
        self.runoff.__post_init__()

    @property
    def pet_parameter_identity_sha256(self):
        return pet_parameter_identity(self)


def parameters_from_seasonal_config(climate, runoff=None, *, freezing_threshold_c=0.0):
    """Read the existing PET **parameters** from a ``SeasonalConfig``.

    Only the two parameter values are read. ``seasonal_climate`` is never called:
    it resamples the v1 climate internally, which would replace the caller's v2/G3
    monthly temperature with a v1 one.
    """
    if not isinstance(climate, SeasonalConfig):
        raise ValueError("a SeasonalConfig instance is required")
    return PetEtParameters(
        pet_base_mm_per_day=float(climate.pet_base_mm_per_day),
        pet_temperature_mm_per_day_c=float(climate.pet_temperature_mm_per_day_c),
        freezing_threshold_c=freezing_threshold_c,
        runoff=RunoffParameters() if runoff is None else runoff)


# --------------------------------------------------------------------------- #
# digests
# --------------------------------------------------------------------------- #

def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(payload):
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _array_digest(array):
    values = np.ascontiguousarray(np.asarray(array))
    hasher = hashlib.sha256()
    hasher.update(str(values.shape).encode("ascii"))
    hasher.update(values.dtype.str.encode("ascii"))
    hasher.update(values.tobytes(order="C"))
    return hasher.hexdigest()


def _points_digest(x_m, z_m):
    """Order-, shape- and window-independent digest of the world point set."""
    x = np.asarray(x_m, np.float64).reshape(-1)
    z = np.asarray(z_m, np.float64).reshape(-1)
    return _array_digest(np.stack((x[_point_order(x, z)], z[_point_order(x, z)])))


def _point_order(x_m, z_m):
    """Canonical cell order: sort by ``(x, z)`` so identity is order independent."""
    x = np.asarray(x_m, np.float64).reshape(-1)
    z = np.asarray(z_m, np.float64).reshape(-1)
    return np.lexsort((z, x))


def _ordered_digest(array, order, axis):
    """Digest an array after putting its cells in canonical point order."""
    values = np.asarray(array, np.float64)
    return _array_digest(np.take(values, order, axis=axis))


def _source_identities():
    """Module-byte identities of this adapter and the frozen cores it drives.

    ``model_identity`` must bind the actual code, not only a module **name**: two
    different builds of ``advance_soil`` would otherwise share an identity. Computed
    once per process and memoised, so repeated identity calls do not re-read the same
    five files.
    """
    cached = getattr(_source_identities, "_cache", None)
    if cached is not None:
        return cached
    identities = {}
    for module_name, basename in _IDENTITY_MODULES:
        module = importlib.import_module(module_name)
        path = getattr(module, "__file__", None)
        if path is None:
            raise ValueError("no source file for %r" % (module_name,))
        with open(path, "rb") as stream:
            identities[module_name] = {
                "basename": basename,
                "source_sha256": hashlib.sha256(stream.read()).hexdigest(),
            }
    _source_identities._cache = identities
    return identities


def pet_parameter_identity(parameters=None):
    """Identity of the PET parameters **only** (bucket parameters do not enter).

    Changing any ``RunoffParameters`` field other than the PET override must leave
    this digest unchanged; :func:`model_identity` is the place where everything is
    bound together.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    if not isinstance(params, PetEtParameters):
        raise ValueError("PetEtParameters required")
    return _digest({
        "schema": PET_PARAMETER_SCHEMA,
        "pet_base_mm_per_day": params.pet_base_mm_per_day,
        "pet_temperature_mm_per_day_c": params.pet_temperature_mm_per_day_c,
        "freezing_threshold_c": params.freezing_threshold_c,
        "expression": {
            "path": SEASONAL_SOURCE_PATH,
            "sha256": SEASONAL_SOURCE_SHA256,
            "line": SEASONAL_PET_LINE,
            "form": SEASONAL_PET_EXPRESSION,
        },
    })


def model_identity(*, parameters, x_m, z_m, time_edges_s, states,
                   monthly_temperature_c, rain_mm_h, spacing_m,
                   temperature_source, rain_source):
    """Identity binding points, forcing, time edges, initial states and all parameters."""
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    if not isinstance(params, PetEtParameters):
        raise ValueError("PetEtParameters required")
    x = np.asarray(x_m, np.float64).reshape(-1)
    z = np.asarray(z_m, np.float64).reshape(-1)
    if x.size != z.size:
        raise ValueError("x_m and z_m must have the same number of points")
    order = _point_order(x, z)
    return _digest({
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "pet_parameter_identity_sha256": pet_parameter_identity(params),
        "bucket": {
            "module": BUCKET_MODULE,
            "parameters": asdict(params.runoff),
            "pet_realisation": (
                "exact per-cell scalar grouping: RunoffParameters.potential_et_mm_h "
                "is replaced inside each group; no averaging, no bucketing"),
            "ignored_initial_fields": [
                "initial_soil_mm", "initial_fast_mm", "initial_slow_mm"],
        },
        "code_identities": _source_identities(),
        "spacing_m": float(spacing_m),
        "temperature_source": temperature_source,
        "rain_source": rain_source,
        "cell_order": "canonical lexsort by (x_m, z_m): identity is order independent",
        "points_sha256": _points_digest(x, z),
        "time_edges_sha256": _array_digest(np.asarray(time_edges_s, np.float64)),
        "initial_states_sha256": _ordered_digest(states, order, axis=1),
        "monthly_temperature_sha256": _ordered_digest(
            monthly_temperature_c, order, axis=1),
        "rain_mm_h_sha256": _ordered_digest(rain_mm_h, order, axis=1),
    })


# --------------------------------------------------------------------------- #
# budget
# --------------------------------------------------------------------------- #

def preflight(cells, intervals):
    """Compute the whole budget before allocating anything.

    The worst case for the number of bucket calls is ``cells * intervals`` (one
    group per cell per interval, i.e. every cell has a distinct PET rate). That is
    the number this gate bounds, because no averaging or coarse re-bucketing of the
    PET rate is permitted.
    """
    if isinstance(cells, bool) or not isinstance(cells, int) or not 1 <= cells <= MAX_CELLS:
        raise ValueError("cells outside 1..%d" % (MAX_CELLS,))
    if (isinstance(intervals, bool) or not isinstance(intervals, int)
            or not 1 <= intervals <= MAX_INTERVALS):
        raise ValueError("intervals outside 1..%d" % (MAX_INTERVALS,))
    work = cells * intervals
    if work > MAX_CELL_INTERVALS:
        raise ValueError(
            "cell-interval work %d exceeds %d; a longer run must be chunked and its "
            "output sampled, not claimed as a full step-by-step product"
            % (work, MAX_CELL_INTERVALS))
    # ``<U16`` costs 4 bytes per character, so the label field is 4 * REGIME_WIDTH.
    interval_bytes = (len(INTERVAL_FLOAT_FIELDS) * 8 + 4 * REGIME_WIDTH) * work
    edge_bytes = len(EDGE_FLOAT_FIELDS) * 8 * (intervals + 1) * cells
    int_bytes = len(INTERVAL_INT_FIELDS) * 8 * intervals
    monthly_bytes = len(MONTHLY_FLOAT_FIELDS) * 8 * 12 * cells
    inventory_bytes = 8 * (intervals + 1)
    estimated = interval_bytes + edge_bytes + int_bytes + monthly_bytes + inventory_bytes
    if estimated > MAX_OUTPUT_BYTES:
        raise ValueError(
            "estimated output %d bytes exceeds %d" % (estimated, MAX_OUTPUT_BYTES))
    return {
        "cells": cells,
        "intervals": intervals,
        "cell_intervals": work,
        "max_bucket_calls": work * SUBSTEP_WORST_CASE_PER_INTERVAL,
        "estimated_output_bytes": estimated,
        "max_cells": MAX_CELLS,
        "max_intervals": MAX_INTERVALS,
        "max_cell_intervals": MAX_CELL_INTERVALS,
        "max_output_bytes": MAX_OUTPUT_BYTES,
        "bucket_gate": ("regional_surface_forcing.preflight(cells, intervals, "
                        "block_cells, dt_s) also bounds cells*intervals at "
                        "MAX_CELL_STEPS=25000000 and dt_s at 3600 s"),
    }


# --------------------------------------------------------------------------- #
# PET: the one declared synonymous expression
# --------------------------------------------------------------------------- #

def _pet_daily_mm(temperature_c, parameters):
    """The one expression: existing temperature-index PET, in mm per day.

    Synonymous with ``terrain_pipeline/hydrology_seasonal.py:74`` (see
    :data:`SEASONAL_PET_EXPRESSION` and :data:`SEASONAL_SOURCE_SHA256`). The two
    parameters are read from :class:`SeasonalConfig` through
    :class:`PetEtParameters`; the arithmetic is the original arithmetic, so the two
    derived quantities below keep the original operation order.
    """
    return (parameters.pet_base_mm_per_day
            + parameters.pet_temperature_mm_per_day_c * np.maximum(temperature_c, 0.0))


def temperature_index_pet_rate_mm_h(temperature_c, parameters=None):
    """Existing temperature-index PET in **mm/hour** (the only unit conversion).

    Equal to the mm/day expression divided by 24. Negative temperature contributes
    nothing beyond the base rate, exactly as ``np.maximum(temperature, 0)`` in the
    original; the four PET parameters are never refitted here.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    if not isinstance(params, PetEtParameters):
        raise ValueError("PetEtParameters required")
    temperature = np.asarray(temperature_c, np.float64)
    if not np.isfinite(temperature).all():
        raise ValueError("finite monthly temperature required")
    return _pet_daily_mm(temperature, params) / 24.0


def monthly_potential_et_mm(monthly_temperature_c, parameters=None):
    """``(12, N)`` monthly PET depth, same operation order as the original.

    ``daily_mm_per_day * MONTH_DAYS`` is exactly ``seasonal_climate`` line 76
    (``pet * MONTH_DAYS``), so an equivalence test can compare bit for bit. It is the
    monthly depth, **not** an interval depth: interval depths are integrated on the
    real calendar by :func:`interval_pet_mm`.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    temperature = np.asarray(monthly_temperature_c, np.float64)
    if temperature.ndim < 2 or temperature.shape[0] != 12:
        raise ValueError("monthly_temperature_c must be [12, ...]")
    if not np.isfinite(temperature).all():
        raise ValueError("finite monthly temperature required")
    days = MONTH_DAYS.reshape((12,) + (1,) * (temperature.ndim - 1))
    return _pet_daily_mm(temperature, params) * days


def _month_index(seconds_in_year):
    index = int(np.searchsorted(MONTH_EDGES_S, seconds_in_year, side="right") - 1)
    return min(11, max(0, index))


def _split_interval(start_s, end_s):
    """Split ``[start_s, end_s)`` on the real 365-day calendar into month pieces."""
    pieces = []
    lower = float(start_s)
    upper_bound = float(end_s)
    while lower < upper_bound:
        year = math.floor(lower / YEAR_S)
        in_year = lower - year * YEAR_S
        month = _month_index(in_year)
        month_end = year * YEAR_S + float(MONTH_EDGES_S[month + 1])
        upper = min(upper_bound, month_end)
        if not upper > lower:
            raise ValueError(
                "degenerate calendar split at %.17g s: the interval edges do not "
                "advance on the declared 365-day calendar" % (lower,))
        pieces.append((month, upper - lower))
        lower = upper
    return pieces


def calendar_month_seconds(time_edges_s):
    """``(T, 12)`` seconds each interval actually spends inside each calendar month."""
    edges = _validate_edges(time_edges_s)
    result = np.zeros((edges.size - 1, 12), np.float64)
    for index in range(edges.size - 1):
        for month, seconds in _split_interval(edges[index], edges[index + 1]):
            result[index, month] += seconds
    return result


def interval_pet_mm(monthly_temperature_c, time_edges_s, parameters=None):
    """``(T, N)`` interval-average PET depth, integrated across month/year edges.

    Monthly mean temperature is the declared input; it repeats every year on the
    declared calendar (365 days, no leap day, the same convention as
    ``metric_noise_forcing.MONTH_EDGES_S``). An interval that spans a month boundary
    is integrated month by month, so the depth is never assigned to a single month.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    if not isinstance(params, PetEtParameters):
        raise ValueError("PetEtParameters required")
    temperature = np.asarray(monthly_temperature_c, np.float64)
    if temperature.ndim != 2 or temperature.shape[0] != 12:
        raise ValueError("monthly_temperature_c must be [12, N]")
    if not np.isfinite(temperature).all():
        raise ValueError("finite monthly temperature required")
    edges = _validate_edges(time_edges_s)
    rate_by_month = temperature_index_pet_rate_mm_h(temperature, params)
    depth = np.zeros((edges.size - 1, temperature.shape[1]), np.float64)
    for index in range(edges.size - 1):
        for month, seconds in _split_interval(edges[index], edges[index + 1]):
            depth[index] += rate_by_month[month] * (seconds / 3600.0)
    return depth


def liquid_fraction(monthly_temperature_c, month_seconds, parameters=None):
    """``(T, N)`` liquid fraction of the declared precipitation.

    The only criterion is the declared monthly-mean threshold
    (:data:`PHASE_SOURCE`): a month whose mean is **strictly below** the threshold
    contributes solid, at or above it contributes liquid. When an interval spans a
    month boundary the fraction is the elapsed-time-weighted mixture of the two, and
    that mixture is declared, not fitted. This is an approximation from a monthly
    mean, never a daily or hourly phase, and it does not build a snowpack.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    temperature = np.asarray(monthly_temperature_c, np.float64)
    if temperature.ndim != 2 or temperature.shape[0] != 12:
        raise ValueError("monthly_temperature_c must be [12, N]")
    seconds = np.asarray(month_seconds, np.float64)
    if seconds.ndim != 2 or seconds.shape[1] != 12:
        raise ValueError("month_seconds must be [T, 12]")
    if seconds.shape[0] != 0 and (not np.isfinite(seconds).all() or np.any(seconds < 0)):
        raise ValueError("finite nonnegative month seconds required")
    liquid = (temperature >= params.freezing_threshold_c).astype(np.float64)
    total = seconds.sum(axis=1)
    weighted = seconds @ liquid
    fraction = np.zeros(weighted.shape, np.float64)
    np.divide(weighted, total[:, None], out=fraction, where=total[:, None] > 0.0)
    if total.shape[0] and np.any(total <= 0.0):
        raise ValueError("every interval must spend positive time inside the calendar")
    return np.clip(fraction, 0.0, 1.0)


# --------------------------------------------------------------------------- #
# validators
# --------------------------------------------------------------------------- #

def _validate_edges(time_edges_s):
    edges = np.asarray(time_edges_s, np.float64)
    if edges.ndim != 1 or edges.size < 2:
        raise ValueError("time_edges_s must be a one-dimensional array of at least 2 edges")
    if not np.isfinite(edges).all():
        raise ValueError("finite physical time edges required")
    if edges[0] < 0.0:
        raise ValueError("time edges must be nonnegative physical seconds")
    if np.any(np.diff(edges) <= 0.0):
        raise ValueError("strictly increasing time edges required")
    longest = float(np.max(np.diff(edges)))
    if longest > 3600.0:
        raise ValueError(
            "the bucket only accepts dt_s <= 3600 s; the longest declared interval is "
            "%.17g s, so refine the interval edges instead of widening the gate"
            % (longest,))
    return edges


def _validate_coordinates(x_m, z_m, cells):
    x = np.asarray(x_m, np.float64).reshape(-1)
    z = np.asarray(z_m, np.float64).reshape(-1)
    if x.size != cells or z.size != cells:
        raise ValueError("x_m and z_m must each provide one coordinate per cell")
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("finite absolute world coordinates required")
    if max(float(np.max(np.abs(x))), float(np.max(np.abs(z)))) > 1e12:
        raise ValueError("bounded absolute world coordinates required")
    return x, z


def _validate_states(states, cells, parameters):
    array = np.asarray(states, np.float64)
    if array.ndim != 2 or array.shape != (3, cells):
        raise ValueError("states must be a float64 [3, N] block")
    if not np.isfinite(array).all():
        raise ValueError("finite initial soil/fast/slow states required")
    if np.any(array < 0.0):
        raise ValueError("nonnegative initial soil/fast/slow states required")
    capacity = parameters.runoff.soil_capacity_mm
    if np.any(array[0] > capacity):
        raise ValueError(
            "initial soil above the prescribed soil_capacity_mm (%.17g)" % (capacity,))
    return array


def _validate_source(value, allowed, name):
    if not isinstance(value, str) or value not in allowed:
        raise ValueError("%s must be one of %r" % (name, allowed))
    return value


# --------------------------------------------------------------------------- #
# the one grouped bucket call
# --------------------------------------------------------------------------- #

def _advance_grouped(liquid_rate_mm_h, states, *, dt_s, pet_rate_mm_h, parameters):
    """Exact per-PET-value grouping over the existing bucket.

    ``RunoffParameters.potential_et_mm_h`` is a scalar, so a spatially varying PET
    rate is realised by grouping **identical float values** with ``np.unique`` (an
    exact operation, no binning, no averaging) and issuing one bucket call per
    distinct value. Each cell's arithmetic is then identical to calling the bucket on
    that cell alone, which the test suite asserts bit for bit.
    """
    values, inverse = np.unique(pet_rate_mm_h, return_inverse=True)
    inverse = inverse.reshape(-1)
    cells = int(states.shape[1])
    next_states = np.empty((3, cells), np.float64)
    release = np.empty(cells, np.float64)
    actual_et = np.empty(cells, np.float64)
    change = np.empty(cells, np.float64)
    sizes = []
    for index, value in enumerate(values):
        mask = inverse == index
        group_parameters = replace(parameters, potential_et_mm_h=float(value))
        group_states, group_release, group_et, group_change = advance_soil(
            liquid_rate_mm_h[mask], states[:, mask], dt_s=dt_s,
            parameters=group_parameters)
        next_states[:, mask] = group_states
        release[mask] = group_release
        actual_et[mask] = group_et
        change[mask] = group_change
        sizes.append(int(mask.sum()))
    report = {
        "unique_pet_groups": int(values.size),
        "calls": int(values.size),
        "group_sizes": sizes,
        "realisation": ("np.unique on the float64 PET rate: exact, no averaging, no "
                        "coarse re-bucketing"),
    }
    return next_states, release, actual_et, change, report


# --------------------------------------------------------------------------- #
# main entry
# --------------------------------------------------------------------------- #

def advance_pet_et(monthly_temperature_c, rain_mm_h, time_edges_s, states, *,
                   x_m, z_m, spacing_m=30.0, parameters=None,
                   temperature_source="caller_declared_monthly_mean",
                   rain_source="declared_event"):
    """Advance the existing soil bucket with a per-cell PET rate and report the ledger.

    Parameters
    ----------
    monthly_temperature_c : [12, N] float64
        Declared monthly-mean temperature in degC. It is the **declared input** of
        this adapter; the adapter never resamples a climate model.
    rain_mm_h : [T, N] float64
        Declared interval-average precipitation intensity in mm/hour on
        ``time_edges_s``. Never derived from an annual total.
    time_edges_s : [T+1] float64
        Strictly increasing physical seconds; every interval is at most 3600 s
        because that is the bucket's own gate.
    states : [3, N] float64
        Explicit initial soil/fast/slow storage in mm (the bucket's own state order).

    Returns
    -------
    dict
        ``soil_edge_mm``/``fast_edge_mm``/``slow_edge_mm`` are ``[T+1, N]`` **edges**:
        the state before interval ``t`` is ``edge[t]`` and after it ``edge[t+1]``.
        There is deliberately no second ``[T+1, N]`` before/after pair.

    Notes
    -----
    The main account is ``delta(soil+fast+slow) = liquid_rain - ET - release``.
    ``subsurface_transfer_mm`` (percolation from soil into the internal slow store) is
    reported for the soil sub-account only and is **never** deducted a second time:
    it is an internal transfer, not a deep loss. ``release_mm`` already contains both
    the fast and the slow release, so it is deducted exactly once.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    if not isinstance(params, PetEtParameters):
        raise ValueError("PetEtParameters required")
    temperature_source = _validate_source(
        temperature_source, TEMPERATURE_SOURCES, "temperature_source")
    rain_source = _validate_source(rain_source, RAIN_SOURCES, "rain_source")
    if (isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float))
            or not math.isfinite(spacing_m) or spacing_m <= 0.0):
        raise ValueError("finite positive spacing_m required")

    temperature = np.asarray(monthly_temperature_c, np.float64)
    if temperature.ndim != 2 or temperature.shape[0] != 12:
        raise ValueError("monthly_temperature_c must be [12, N]")
    if not np.isfinite(temperature).all():
        raise ValueError("finite monthly temperature required")
    cells = int(temperature.shape[1])

    rain_rate = np.asarray(rain_mm_h, np.float64)
    if rain_rate.ndim != 2 or rain_rate.shape[1] != cells:
        raise ValueError("rain_mm_h must be [T, N] matching monthly_temperature_c")
    intervals = int(rain_rate.shape[0])
    if not np.isfinite(rain_rate).all():
        raise ValueError("finite interval-average rain required")
    if np.any(rain_rate < 0.0) or np.any(rain_rate > 1000.0):
        raise ValueError("rain intensity must lie in 0..1000 mm/h")

    edges = _validate_edges(time_edges_s)
    if edges.size - 1 != intervals:
        raise ValueError("time_edges_s must carry exactly T+1 edges for T intervals")

    initial = _validate_states(states, cells, params)
    x, z = _validate_coordinates(x_m, z_m, cells)
    budget = preflight(cells, intervals)

    # This adapter issues one ``advance_soil`` call per (interval, PET-value group).
    # It does **not** use the streaming writer ``generate_forcing``, so that writer's
    # MAX_STEPS=288 / MAX_CELL_STEPS=25000000 gates do not apply here; the bucket's own
    # per-call gates do, and they are declared rather than assumed.
    bucket_gate = {
        "bucket": BUCKET_MODULE,
        "max_dt_s": 3600.0,
        "max_cells_per_call": 65536,
        "calls": ("one advance_soil call per calendar sub-step per distinct PET value; "
                  "an interval that straddles a month/year edge is sub-stepped"),
        "streaming_writer_not_used": (
            "regional_surface_forcing.generate_forcing (MAX_STEPS=288, "
            "MAX_CELL_STEPS=25000000) is a streaming file writer and is not part of "
            "this adapter; a long run is a caller-side chunking decision"),
    }

    interval_seconds = np.diff(edges)
    hours = interval_seconds / 3600.0
    month_seconds = calendar_month_seconds(edges)
    # Interval-level aggregates kept for reporting only; the bucket never sees them.
    pet_depth = interval_pet_mm(temperature, edges, params)
    pet_rate = pet_depth / hours[:, None]
    liquid = liquid_fraction(temperature, month_seconds, params)
    rain_mm = rain_rate * hours[:, None]

    # --- declared choice: the bucket is sub-stepped at every calendar month/year edge ---
    # An interval that crosses a month boundary is **not** averaged and then pushed through
    # one bucket step: each calendar piece advances the bucket with that month's own PET
    # rate and its own phase decision, and the requested interval only aggregates the
    # outputs. See ``SUBSTEP_POLICY`` in the returned report. Without this, a month-boundary
    # interval under a supply limit would not be equal to running the pieces separately.
    rate_by_month = temperature_index_pet_rate_mm_h(temperature, params)
    liquid_by_month = (temperature >= params.freezing_threshold_c).astype(np.float64)

    soil_edge = np.empty((intervals + 1, cells), np.float64)
    fast_edge = np.empty((intervals + 1, cells), np.float64)
    slow_edge = np.empty((intervals + 1, cells), np.float64)
    soil_edge[0] = initial[0]
    fast_edge[0] = initial[1]
    slow_edge[0] = initial[2]

    actual_et = np.empty((intervals, cells), np.float64)
    release = np.empty((intervals, cells), np.float64)
    subsurface = np.empty((intervals, cells), np.float64)
    infiltration = np.empty((intervals, cells), np.float64)
    change = np.empty((intervals, cells), np.float64)
    available_supply = np.empty((intervals, cells), np.float64)
    liquid_rain = np.empty((intervals, cells), np.float64)
    solid_rain = np.empty((intervals, cells), np.float64)
    substeps = np.empty(intervals, np.int64)
    regime = np.empty((intervals, cells), dtype="<U%d" % (REGIME_WIDTH,))
    groups = {"unique_pet_groups": [], "calls": [], "group_sizes": [],
              "substeps_per_interval": [],
              "realisation": "np.unique on the float64 PET rate: exact, no averaging"}

    runoff = params.runoff
    current = initial.copy()
    for step in range(intervals):
        pieces = _split_interval(edges[step], edges[step + 1])
        substeps[step] = len(pieces)
        step_release = np.zeros(cells, np.float64)
        step_et = np.zeros(cells, np.float64)
        step_change = np.zeros(cells, np.float64)
        step_subsurface = np.zeros(cells, np.float64)
        step_infiltration = np.zeros(cells, np.float64)
        step_liquid = np.zeros(cells, np.float64)
        step_supply = np.zeros(cells, np.float64)
        limited_by_pet = np.ones(cells, bool)
        limited_by_supply = np.ones(cells, bool)
        calls_here = 0
        groups_here = 0
        for piece_index, (month, seconds) in enumerate(pieces):
            piece_hours = seconds / 3600.0
            # ``liquid_by_month[month]`` is a per-cell array (shape ``[N]``), not a scalar:
            # the phase decision is spatial, because every cell has its own monthly mean.
            # Taking ``float(...)`` here (or the first cell, or an average) would collapse
            # that field; it stays a ``[N]`` array all the way into the exact grouping.
            piece_fraction = liquid_by_month[month]
            piece_liquid_rate = rain_rate[step] * piece_fraction
            piece_pet_rate = rate_by_month[month]
            next_states, piece_release, piece_et, piece_change, report = _advance_grouped(
                piece_liquid_rate, current, dt_s=float(seconds),
                pet_rate_mm_h=piece_pet_rate, parameters=runoff)
            calls_here += report["calls"]
            groups_here += report["unique_pet_groups"]
            groups["group_sizes"].append(report["group_sizes"])

            # Independent audit of the same parameters for **this** sub-step: the bucket
            # returns neither the infiltration nor the percolation, so both are re-derived
            # here from the same declared parameters and compared with its soil edge.
            cap_infiltration = runoff.infiltration_capacity_mm_h * piece_hours
            headroom = np.maximum(runoff.soil_capacity_mm - current[0], 0.0)
            piece_infiltration = np.minimum(
                np.minimum(piece_liquid_rate * piece_hours, cap_infiltration), headroom)
            piece_supply = current[0] + piece_infiltration
            piece_percolation = np.minimum(
                piece_supply - piece_et, runoff.percolation_mm_h * piece_hours)
            piece_pet_limit = piece_pet_rate * piece_hours

            step_release += piece_release
            step_et += piece_et
            step_change += piece_change
            step_subsurface += piece_percolation
            step_infiltration += piece_infiltration
            step_liquid += piece_liquid_rate * piece_hours
            if piece_index == 0:
                step_supply = piece_supply
            limited_by_pet &= piece_supply >= piece_pet_limit
            limited_by_supply &= piece_supply < piece_pet_limit
            current = next_states

        groups["unique_pet_groups"].append(groups_here)
        groups["calls"].append(calls_here)
        groups["substeps_per_interval"].append(len(pieces))

        actual_et[step] = step_et
        release[step] = step_release
        subsurface[step] = step_subsurface
        infiltration[step] = step_infiltration
        change[step] = step_change
        available_supply[step] = step_supply
        liquid_rain[step] = step_liquid
        solid_rain[step] = rain_mm[step] - step_liquid
        regime[step] = np.where(limited_by_pet, "pet_limited",
                                np.where(limited_by_supply, "supply_limited",
                                         "mixed_boundary"))
        soil_edge[step + 1] = current[0]
        fast_edge[step + 1] = current[1]
        slow_edge[step + 1] = current[2]

    cell_area = float(spacing_m) ** 2
    inventory_edge = (soil_edge + fast_edge + slow_edge).sum(axis=1) * cell_area / 1000.0

    # --- ledger -----------------------------------------------------------------
    # The **main account is recomputed from the real edges**: ``edge_storage_delta`` is the
    # true difference of the saved soil/fast/slow edges, so a mismatch between the edges and
    # the bucket's own change array can never be hidden behind a "conserved" verdict. The
    # bucket's ``change`` array is kept only as an independent cross-check field.
    edge_storage_delta = (soil_edge[1:] + fast_edge[1:] + slow_edge[1:]) \
        - (soil_edge[:-1] + fast_edge[:-1] + slow_edge[:-1])
    edge_residual = edge_storage_delta - (liquid_rain - actual_et - release)
    bucket_residual = change - (liquid_rain - actual_et - release)
    volume_factor = cell_area / 1000.0
    total_balance = float(edge_residual.sum()) * volume_factor
    edge_max = float(np.max(np.abs(edge_residual))) if edge_residual.size else 0.0
    bucket_max = float(np.max(np.abs(bucket_residual))) if bucket_residual.size else 0.0
    edge_vs_bucket = float(np.max(np.abs(edge_storage_delta - change))) \
        if change.size else 0.0
    # Tolerance: the bucket's own cell-local gate is 1e-10 mm, so a real answer is at or
    # below it; anything above is reported as **not verified**, not rounded away.
    ledger_tolerance_mm = 1e-10
    main_verified = bool(edge_max <= ledger_tolerance_mm
                         and edge_vs_bucket <= ledger_tolerance_mm)
    soil_audit = (soil_edge[:-1] + infiltration - actual_et - subsurface)
    soil_mismatch = int(np.count_nonzero(soil_audit != soil_edge[1:]))
    soil_abs = np.abs(soil_audit - soil_edge[1:])
    # The solid phase is withheld from the bucket, so it must be accounted explicitly here:
    # rain = liquid + solid, and neither part is allowed to vanish.
    solid_total = float(solid_rain.sum())
    rain_total = float(rain_mm.sum())
    liquid_total = float(liquid_rain.sum())
    solid_accounting = {
        "rain_mm_total": rain_total,
        "liquid_mm_total": liquid_total,
        "solid_equivalent_water_mm_total": solid_total,
        "liquid_plus_solid_minus_rain_mm": liquid_total + solid_total - rain_total,
        "solid_is_withheld_not_lost": True,
        "solid_destination": (
            "withheld from the bucket and reported as an equivalent water depth; the "
            "G7 snow store is not modelled, so this water is neither stored as snow nor "
            "routed as meltwater"),
    }

    pet_limited = int(np.count_nonzero(regime == "pet_limited"))
    supply_limited = int(np.count_nonzero(regime == "supply_limited"))
    mixed_boundary = int(np.count_nonzero(regime == "mixed_boundary"))
    denominator = intervals * cells
    regimes = {
        "pet_limited": pet_limited,
        "supply_limited": supply_limited,
        "mixed_boundary": mixed_boundary,
        "denominator": denominator,
        "pet_limited_fraction": (pet_limited / denominator) if denominator else 0.0,
        "rule": (
            "per sub-step: pet_limited when soil_before + infiltration >= that step's PET "
            "(the equality case is pet_limited, because the bucket then returns the PET "
            "cap itself), supply_limited when strictly below it. An interval that "
            "straddles a calendar month edge is labelled mixed_boundary when its own "
            "sub-steps disagree. The branch counts are a rule-coverage gate; a real "
            "window need not realise every branch."),
    }
    ledger = {
        "main_account": "delta(soil+fast+slow) = liquid_rain - actual_et - release",
        "main_account_source": (
            "recomputed from the saved state edges, not from the bucket's change array"),
        "main_max_abs_residual_mm": edge_max,
        "main_account_verified": main_verified,
        "ledger_tolerance_mm": ledger_tolerance_mm,
        "bucket_internal_max_abs_residual_mm": bucket_max,
        "edge_vs_bucket_change_max_abs_mm": edge_vs_bucket,
        "total_balance_residual_m3": total_balance,
        "inventory_delta_m3": float(inventory_edge[-1] - inventory_edge[0]),
        "total_liquid_rain_mm": float(liquid_rain.sum()),
        "total_actual_et_mm": float(actual_et.sum()),
        "total_release_mm": float(release.sum()),
        "storage_change_m3": float(inventory_edge[-1] - inventory_edge[0]),
        "total_liquid_rain_m3": float(liquid_rain.sum()) * volume_factor,
        "total_actual_et_m3": float(actual_et.sum()) * volume_factor,
        "total_release_m3": float(release.sum()) * volume_factor,
        "total_balance_residual_unit": "m3",
        "release_deducted_once": True,
        "subsurface_transfer_is_internal": True,
        "solid_accounting": solid_accounting,
        "soil_sub_account": {
            "status": "audited" if soil_mismatch == 0 else "audit_mismatch",
            "mismatched_cells": soil_mismatch,
            "max_abs_difference_mm": float(np.max(soil_abs)) if soil_abs.size else 0.0,
            "definition": ("soil_edge[t] + infiltration - actual_et - subsurface "
                           "must equal soil_edge[t+1] bit for bit"),
            "note": ("the bucket returns neither infiltration nor percolation; both are "
                     "re-derived from the same declared parameters for this audit only"),
        },
    }
    not_available = {
        "deep_loss": {"status": NOT_AVAILABLE,
                      "reason": "no deep outlet is modelled; percolation stays inside the fast/slow stores"},
        "aquifer_storage": {"status": NOT_AVAILABLE,
                            "reason": "no aquifer exists in this chain; the slow store is not one"},
        "baseflow": {"status": NOT_AVAILABLE,
                     "reason": "slow release is an internal store discharge, not a groundwater baseflow"},
        "snowpack_state": {"status": NOT_MODELED,
                           "reason": "the G7 snow store is not modelled; solid input is withheld and reported as an equivalent depth"},
        "glacier": {"status": NOT_MODELED,
                    "reason": "no multi-year mass balance, ice motion or ice erosion exists in this stage"},
    }

    sources = {
        "monthly_temperature_c": {
            "source": temperature_source,
            "units": "degC_monthly_mean",
            "semantics": "monthly_mean_not_daily_and_not_diurnal",
            "note": "declared input; this adapter never resamples a climate model",
        },
        "rain_mm_h": {
            "source": rain_source,
            "units": "mm_per_hour_interval_average",
            "time_edges": "explicit physical seconds",
            "note": "an annual total is never converted into a single storm event",
        },
        "monthly_potential_et_mm": {
            "source": "temperature_index_from_monthly_temperature_c",
            "units": "mm_per_month",
            "expression": {"path": SEASONAL_SOURCE_PATH,
                           "sha256": SEASONAL_SOURCE_SHA256,
                           "line": SEASONAL_PET_LINE,
                           "form": SEASONAL_PET_EXPRESSION},
            "note": "declared engineering assumptions reused from SeasonalConfig; not calibrated",
        },
        "interval_pet_mm": {
            "source": "calendar_integration_of_monthly_potential_et",
            "units": "mm_per_interval",
            "calendar": "365 days, no leap day, month edges from metric_noise_forcing.MONTH_EDGES_S",
        },
        "pet_rate_mm_h": {
            "source": "interval_pet_mm / interval hours",
            "units": "mm_per_hour",
            "note": "this is the scalar handed to the bucket, per exact value group",
        },
        "actual_et_mm": {"source": BUCKET_MODULE + " returned et",
                         "units": "mm_per_interval"},
        "release_mm": {"source": BUCKET_MODULE + " returned release (fast + slow)",
                       "units": "mm_per_interval"},
        "subsurface_transfer_mm": {
            "source": "independent audit of percolation (soil -> internal slow store)",
            "units": "mm_per_interval",
            "note": "internal transfer only; never deducted from the main account",
        },
        "infiltration_mm": {
            "source": "independent audit from the same declared parameters",
            "units": "mm_per_interval"},
        "soil_edge_mm": {"source": BUCKET_MODULE + " states[0] at the edge",
                         "units": "mm", "shape": "[T+1, N]"},
        "fast_edge_mm": {"source": BUCKET_MODULE + " states[1] at the edge",
                         "units": "mm", "shape": "[T+1, N]"},
        "slow_edge_mm": {"source": BUCKET_MODULE + " states[2] at the edge",
                         "units": "mm", "shape": "[T+1, N]"},
        "liquid_rain_mm": {"source": "liquid_rate_mm_h * interval hours",
                          "units": "mm_per_interval"},
        "liquid_rate_mm_h": {"source": "rain_mm_h * liquid_fraction (the rate handed to the bucket)",
                             "units": "mm_per_hour"},
        "solid_precipitation_swe_mm": {
            "source": "rain_mm * (1 - liquid_fraction)",
            "units": "mm_equivalent_water_depth",
            "semantics": "withheld_solid_input",
            "note": ("NOT a snow depth: no density is assumed. The solid part is withheld "
                     "from the bucket and reported here so it cannot silently vanish"),
        },
        "liquid_fraction": {"source": PHASE_SOURCE, "units": "1",
                            "semantics": PHASE_SEMANTICS},
        "inventory_m3_edge": {"source": "(soil+fast+slow) * cell_area / 1000",
                              "units": "m3", "shape": "[T+1]"},
        "available_supply_mm": {
            "source": "soil_edge[t] + infiltration (the bucket's ET order)",
            "units": "mm_per_interval"},
        "et_regime": {"source": "available_supply_mm vs interval_pet_mm",
                      "units": "label", "values": ["pet_limited", "supply_limited"]},
    }
    provenance_split = {
        "temperature": temperature_source,
        "rain": rain_source,
        "background_estimate_columns": [] if rain_source != "background_estimate" else ["rain_mm"],
        "event_columns": [] if rain_source != "declared_event" else ["rain_mm"],
        "rule": ("a background-estimate column and a real-event column are never merged "
                 "into one number; the source label is recorded and enters the identity"),
    }

    sub_seed_registration = {
        "world_seed": None,
        "purpose": None,
        "noise_used": False,
        "note": ("this chain consumes no noise: temperature-index PET and the bucket are "
                 "deterministic arithmetic, so no subseed is invented. If a noise-driven "
                 "producer is attached later it must record its derived value here."),
    }

    limitations = list(LIMITATIONS)
    if rain_source == "background_estimate":
        limitations.append(
            "rain_source is background_estimate: this run is a declared background "
            "estimate, not a real event, and must not be reported as realised weather.")
    if temperature_source != "g3_monthly_mean":
        limitations.append(
            "monthly temperature is %r, not a G3 production field; the G3 consumer is "
            "still to be integrated by the main branch." % (temperature_source,))

    pet_sha = pet_parameter_identity(params)
    identity = {
        "pet_parameter_identity_sha256": pet_sha,
        "model_identity_sha256": model_identity(
            parameters=params, x_m=x, z_m=z, time_edges_s=edges, states=initial,
            monthly_temperature_c=temperature, rain_mm_h=rain_rate, spacing_m=spacing_m,
            temperature_source=temperature_source, rain_source=rain_source),
        "points_sha256": _points_digest(x, z),
        "bucket_module": BUCKET_MODULE,
        "bucket_parameters": asdict(runoff),
        "pet_parameters": {
            "pet_base_mm_per_day": params.pet_base_mm_per_day,
            "pet_temperature_mm_per_day_c": params.pet_temperature_mm_per_day_c,
            "freezing_threshold_c": params.freezing_threshold_c,
        },
        "ignored_bucket_initial_fields": [
            "initial_soil_mm", "initial_fast_mm", "initial_slow_mm"],
    }

    return {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "phase_schema": PHASE_SCHEMA,
        "shape": [intervals, cells],
        "spacing_m": float(spacing_m),
        "cell_area_m2": cell_area,
        "x_m": x, "z_m": z,
        "time_edges_s": edges,
        "interval_seconds": interval_seconds,
        "monthly_temperature_c": temperature,
        "monthly_potential_et_mm": monthly_potential_et_mm(temperature, params),
        "calendar_month_seconds": month_seconds,
        "interval_pet_mm": pet_depth,
        "pet_rate_mm_h": pet_rate,
        "rain_mm": rain_mm,
        "liquid_rain_mm": liquid_rain,
        "liquid_rate_mm_h": liquid_rain / hours[:, None],
        "solid_precipitation_swe_mm": solid_rain,
        "liquid_fraction": liquid,
        "substeps_per_interval": substeps,
        "soil_edge_mm": soil_edge,
        "fast_edge_mm": fast_edge,
        "slow_edge_mm": slow_edge,
        "actual_et_mm": actual_et,
        "release_mm": release,
        "subsurface_transfer_mm": subsurface,
        "infiltration_mm": infiltration,
        "storage_change_mm": change,
        "available_supply_mm": available_supply,
        "et_regime": regime,
        "inventory_m3_edge": inventory_edge,
        "ledger": ledger,
        "regimes": regimes,
        "substep_policy": SUBSTEP_POLICY,
        "groups": groups,
        "sources": sources,
        "units": {
            "monthly_temperature_c": "degC_monthly_mean",
            "monthly_potential_et_mm": "mm_per_month",
            "interval_pet_mm": "mm_per_interval",
            "pet_rate_mm_h": "mm_per_hour",
            "rain_mm": "mm_per_interval",
            "liquid_rain_mm": "mm_per_interval",
            "liquid_rate_mm_h": "mm_per_hour",
            "solid_precipitation_swe_mm": "mm_equivalent_water_depth",
            "liquid_fraction": "1",
            "soil_edge_mm": "mm",
            "fast_edge_mm": "mm",
            "slow_edge_mm": "mm",
            "actual_et_mm": "mm_per_interval",
            "release_mm": "mm_per_interval",
            "subsurface_transfer_mm": "mm_per_interval",
            "infiltration_mm": "mm_per_interval",
            "storage_change_mm": "mm_per_interval",
            "available_supply_mm": "mm_per_interval",
            "inventory_m3_edge": "m3",
            "calendar_month_seconds": "s",
            "time_edges_s": "s",
            "interval_seconds": "s",
        },
        "provenance_split": provenance_split,
        "sub_seed_registration": sub_seed_registration,
        "not_available": not_available,
        "budget": budget,
        "bucket_gate": bucket_gate,
        "identity": identity,
        "limitations": limitations,
    }


def advance_pet_et_segment(rain_mm_h, time_edges_s, states, *, x_m, z_m,
                           monthly_temperature_c, spacing_m=30.0, parameters=None,
                           temperature_source="caller_declared_monthly_mean",
                           rain_source="declared_event"):
    """Resume on the **same** interval partition from a saved edge.

    This is a thin, honest wrapper: it forwards the remaining interval edges, the
    remaining rain rows and the stored states to :func:`advance_pet_et`, with the
    monthly temperature unchanged. Bit-for-bit equality with a continuous run is only
    promised when the interval edges are the original ones; changing the partition
    changes the discrete bucket time-stepping, because the bucket is not a continuous
    ODE and its release law integrates ``storage * (1 - exp(-dt/tau))`` per step.
    """
    edges = _validate_edges(time_edges_s)
    rain = np.asarray(rain_mm_h, np.float64)
    if rain.ndim != 2 or rain.shape[0] != edges.size - 1:
        raise ValueError("rain_mm_h must be [T, N] for the given T+1 edges")
    return advance_pet_et(
        monthly_temperature_c, rain, edges, states,
        x_m=x_m, z_m=z_m, spacing_m=spacing_m, parameters=parameters,
        temperature_source=temperature_source, rain_source=rain_source)


# --------------------------------------------------------------------------- #
# checkpoint
# --------------------------------------------------------------------------- #

def save_pet_et_checkpoint(path, *, states, edge_index, time_edges_s, parameters,
                           rain_mm_h, monthly_temperature_c, x_m, z_m):
    """Write one edge checkpoint bound to its **source** (points, forcing, temperature).

    A saved state is only shape-compatible with other point sets, forcings and monthly
    temperatures, so ``x_m``/``z_m`` and the forcing arrays are stored as digests. Without
    them a same-shaped state from somewhere else could be restored silently.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    array = np.asarray(states, np.float64)
    if array.ndim != 2 or array.shape[0] != 3 or not np.isfinite(array).all():
        raise ValueError("finite [3, N] states required")
    edges = _validate_edges(time_edges_s)
    if isinstance(edge_index, bool) or not isinstance(edge_index, int) \
            or not 0 <= edge_index < edges.size:
        raise ValueError("edge_index outside 0..T")
    rain = np.asarray(rain_mm_h, np.float64)
    temperature = np.asarray(monthly_temperature_c, np.float64)
    if rain.ndim != 2 or rain.shape[1] != array.shape[1]:
        raise ValueError("rain_mm_h must be [T, N] matching the states")
    if temperature.ndim != 2 or temperature.shape[0] != 12 \
            or temperature.shape[1] != array.shape[1]:
        raise ValueError("monthly_temperature_c must be [12, N] matching the states")
    if rain.shape[0] < edge_index:
        raise ValueError("rain_mm_h has fewer rows than the checkpoint edge index")
    x, z = _validate_coordinates(x_m, z_m, array.shape[1])
    order = _point_order(x, z)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema": CHECKPOINT_SCHEMA,
        "algorithm": ALGORITHM,
        "edge_index": int(edge_index),
        "edge_seconds": float(edges[edge_index]),
        "states_shape": list(array.shape),
        "rain_shape": list(rain.shape),
        "monthly_temperature_shape": list(temperature.shape),
        "pet_parameter_identity_sha256": pet_parameter_identity(params),
        "bucket_parameters": asdict(params.runoff),
        "points_sha256": _points_digest(x, z),
        "cell_order": "canonical lexsort by (x_m, z_m)",
        "monthly_temperature_sha256": _ordered_digest(temperature, order, axis=1),
        "rain_prefix_sha256": _ordered_digest(rain[:edge_index], order, axis=1),
        "cell_count": int(array.shape[1]),
    }
    with open(destination, "wb") as stream:
        np.savez_compressed(
            stream,
            states=array,
            time_edges_s=edges,
            metadata_json=np.array(json.dumps(metadata, sort_keys=True, allow_nan=False)),
            points_x=x,
            points_z=z,
            rain_prefix=rain[:edge_index],
            monthly_temperature=temperature)
    return metadata


def load_pet_et_checkpoint(path, *, time_edges_s, parameters, x_m, z_m,
                           rain_mm_h, monthly_temperature_c, states_shape=None):
    """Read a checkpoint and prove it belongs to **this** points/forcing/partition.

    Refused without a message about tolerance when: the point set, the monthly temperature,
    the already-consumed rain prefix, the interval-edge prefix, the PET/bucket parameters
    or the state legality do not match. The state array alone is deliberately not enough.
    """
    if parameters is None:
        parameters = PetEtParameters()
    params = parameters
    edges = _validate_edges(time_edges_s)
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"]))
        if metadata.get("schema") != CHECKPOINT_SCHEMA:
            raise ValueError("unknown checkpoint schema")
        if metadata.get("pet_parameter_identity_sha256") != pet_parameter_identity(params):
            raise ValueError("checkpoint PET parameters differ from the declared ones")
        if metadata.get("bucket_parameters") != asdict(params.runoff):
            raise ValueError("checkpoint bucket parameters differ from the declared ones")
        stored_edges = np.asarray(archive["time_edges_s"], np.float64)
        edge_index = int(metadata["edge_index"])
        if edge_index < 0 or edge_index >= stored_edges.size:
            raise ValueError("checkpoint edge_index outside its own edge array")
        if stored_edges.size > edges.size:
            raise ValueError("checkpoint partition is longer than the declared one")
        if not np.array_equal(stored_edges[:edge_index + 1], edges[:edge_index + 1]):
            raise ValueError(
                "checkpoint does not belong to the declared partition prefix; only the "
                "original interval edges give a bit-for-bit resume")
        states = np.asarray(archive["states"], np.float64)
        if states.ndim != 2 or states.shape[0] != 3 or not np.isfinite(states).all():
            raise ValueError("invalid checkpoint states")
        if np.any(states < 0.0):
            raise ValueError("negative checkpoint states")
        if np.any(states[0] > params.runoff.soil_capacity_mm):
            raise ValueError("checkpoint soil above soil_capacity_mm")
        if states_shape is not None and tuple(states.shape) != tuple(states_shape):
            raise ValueError("checkpoint states shape differs from the declared one")

        # --- source binding: points, temperature, consumed rain prefix ----------------
        cells = int(states.shape[1])
        x, z = _validate_coordinates(x_m, z_m, cells)
        order = _point_order(x, z)
        if metadata.get("points_sha256") != _points_digest(x, z):
            raise ValueError(
                "checkpoint points differ from the declared point set; a same-shaped state "
                "from another location cannot be restored")
        stored_x = np.asarray(archive["points_x"], np.float64)
        stored_z = np.asarray(archive["points_z"], np.float64)
        if not (np.array_equal(stored_x, x) and np.array_equal(stored_z, z)):
            raise ValueError("checkpoint stores a different point set than declared")
        temperature = np.asarray(monthly_temperature_c, np.float64)
        if temperature.ndim != 2 or temperature.shape[0] != 12 \
                or temperature.shape[1] != cells:
            raise ValueError("monthly_temperature_c must be [12, N] matching the states")
        if metadata.get("monthly_temperature_sha256") != _ordered_digest(
                temperature, order, axis=1):
            raise ValueError(
                "checkpoint monthly temperature differs from the declared one")
        rain = np.asarray(rain_mm_h, np.float64)
        if rain.ndim != 2 or rain.shape[1] != cells or rain.shape[0] < edge_index:
            raise ValueError("rain_mm_h must be [T, N] with T >= the checkpoint edge index")
        if metadata.get("rain_prefix_sha256") != _ordered_digest(
                rain[:edge_index], order, axis=1):
            raise ValueError(
                "checkpoint consumed a different rain prefix than the declared forcing")
    return {
        "schema": CHECKPOINT_SCHEMA,
        "edge_index": edge_index,
        "edge_seconds": float(stored_edges[edge_index]),
        "states": states,
        "time_edges_s": stored_edges,
        "points_x": stored_x,
        "points_z": stored_z,
        "metadata": metadata,
    }


# --------------------------------------------------------------------------- #
# static declaration
# --------------------------------------------------------------------------- #

def describe():
    """Static declaration for review and downstream references (no numeric effect)."""
    return {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "phase_schema": PHASE_SCHEMA,
        "bucket_module": BUCKET_MODULE,
        "network_coupling": "none",
        "boundary_api": "none",
        "pet_expression": {
            "path": SEASONAL_SOURCE_PATH,
            "sha256": SEASONAL_SOURCE_SHA256,
            "line": SEASONAL_PET_LINE,
            "form": SEASONAL_PET_EXPRESSION,
            "declared_synonymous": True,
        },
        "phase_source": PHASE_SOURCE,
        "phase_semantics": PHASE_SEMANTICS,
        "temperature_sources": list(TEMPERATURE_SOURCES),
        "rain_sources": list(RAIN_SOURCES),
        "state_edges": "[T+1, N] edge convention; soil_before = edge[t], soil_after = edge[t+1]",
        "limits": {
            "max_cells": MAX_CELLS,
            "max_intervals": MAX_INTERVALS,
            "max_cell_intervals": MAX_CELL_INTERVALS,
            "max_output_bytes": MAX_OUTPUT_BYTES,
            "max_interval_seconds": 3600.0,
        },
        "never": [
            "a second soil bucket",
            "a second PET formula",
            "averaging or coarse re-bucketing of the PET rate",
            "available_water used as storage or as actual ET",
            "an annual precipitation total used as a single storm event",
            "an aquifer, a groundwater baseflow or a deep loss",
            "snow depth or glacier from a freezing-threshold diagnostic",
            "resume equality across a changed interval partition",
            "a channel network or a boundary condition in this entry point",
        ],
        "limitations": list(LIMITATIONS),
    }
