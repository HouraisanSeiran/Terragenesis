# -*- coding: utf-8 -*-
"""Seasonal snow (SWE) and melt: a bounded per-cell store over declared weather (G7 first card).

What this module is
-------------------
A **store plus a phase decision**, not a climate model and not a glacier model:

1. the rain/snow phase comes from the repository's existing declared-threshold adapter
   (``metric_pet_et.liquid_fraction``), so there is exactly one phase formula in the repo;
2. per-cell snow water equivalent (SWE) accumulates from the solid part of the declared
   precipitation and is removed by degree-day melt and by an **explicitly declared**
   sublimation demand;
3. the liquid water that reaches the ground is reported as ``liquid_to_land_mm`` =
   direct liquid precipitation **plus** melt, and it is consumed **once** by the existing
   soil bucket (:func:`advance_soil`), never by both the bucket and the PET adapter.

What it deliberately does not do
--------------------------------
No snow depth (that would need a density this stage does not have), no glacier, no ice flow,
no ice erosion, no verdict on whether a snow patch is a glacier. A multi-year net loss or a
multi-year net gain says nothing here: the store is seasonal and bounded, and the glacier
question is a separate card with its own mass-balance and flow model.

Time and space
--------------
``time_edges_s`` is the caller's declared physical clock (it may cross month and year
boundaries); the calendar split is the repository's own 365-day table
(``metric_pet_et.calendar_month_seconds``). Precipitation is an explicit depth per interval.
A monthly total is never turned into one storm. Space is the absolute world coordinate at the
native 30 m cell; the 1 m minimum spacing unit is a bound, not a claim of 1 m accuracy.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, digest
from terrain_pipeline.regional_surface_forcing import advance_soil
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.surface_rivers import metric_pet_et

SCHEMA = "seasonal-snow-ice-v1"
LOGICAL_VERSION = "seasonal-swe-degree-day-v1"
ALGORITHM = "seasonal-swe-degree-day"

CELL_AREA_M2 = 900.0
NATIVE_SPACING_M = 30.0
MAX_CELLS = 65536
MAX_INTERVALS = 8760
MAX_BUCKET_STEP_S = 3600.0

TEMPERATURE_SOURCES = ("monthly_mean", "declared_interval")
MELT_ORDERS = ("melt_then_sublimation", "sublimation_then_melt")

PHASE_SOURCE = (
    "metric_pet_et.liquid_fraction (declared freezing threshold, month-seconds weighted); "
    "this module adds no second phase formula")
CALENDAR_SOURCE = (
    "metric_pet_et.calendar_month_seconds (fixed 365-day month table); a monthly total is "
    "never turned into a single storm")
SUBLIMATION_POLICY = (
    "an explicitly declared demand in mm per day, applied in the declared order and hard "
    "limited by the SWE that is actually left; it is not derived from temperature alone and "
    "is never the same water as PET")
#: What this module structurally does **not** model. Stated as a field so a reader never has to
#: pattern-match a prose sentence.
NOT_MODELLED = ("snow_depth", "glacier", "ice_flow", "ice_erosion", "hydraulic_state",
                "channel_routing", "calibration", "one_metre_accuracy")
MONTHLY_MEAN_MAX_INTERVAL_S = MAX_BUCKET_STEP_S
LIMITATIONS = (
    "seasonal snow store only: no snow depth (no density), no glacier, no ice flow, no ice "
    "erosion",
    "no verdict on whether this snow is a glacier; multi-year net balance is not modelled",
    "degree-day coefficients and the sublimation demand are declared engineering "
    "assumptions, uncalibrated, carried in the identity",
    "a monthly total is never converted into one storm event; the caller declares interval "
    "depths on explicit physical time edges",
    "the liquid path enters the existing soil bucket once; this module adds no second bucket, "
    "no channel routing and no hydraulic state",
    "the bucket accepts at most a 3600 s step, so a longer snow interval is consumed in "
    "fixed sub-steps and the module reports that split; the old limit is not relaxed",
)


def _finite(value, name, *, minimum=None, maximum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError("%s must be numeric" % name)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("%s must be finite" % name)
    if positive and number <= 0.0:
        raise ValueError("%s must be positive" % name)
    if minimum is not None and number < minimum:
        raise ValueError("%s must be >= %r" % (name, minimum))
    if maximum is not None and number > maximum:
        raise ValueError("%s must be <= %r" % (name, maximum))
    return number


@dataclass(frozen=True)
class SnowParameters:
    """Declared engineering parameters. Uncalibrated; every value enters the identity."""

    freezing_threshold_c: float = 0.0
    degree_day_melt_mm_per_day_c: float = 4.0
    sublimation_demand_mm_per_day: float = 0.5
    max_swe_mm: float = 5000.0
    min_melt_temperature_c: float = 0.0
    #: The PET adapter's own parameters, used **only** for the phase decision. The bucket's
    #: PET rate lives in ``RunoffParameters`` and is applied by ``advance_soil``.
    phase_parameters: metric_pet_et.PetEtParameters = field(
        default_factory=metric_pet_et.PetEtParameters)

    def __post_init__(self):
        _finite(self.freezing_threshold_c, "freezing_threshold_c")
        _finite(self.degree_day_melt_mm_per_day_c, "degree_day_melt_mm_per_day_c",
                minimum=0.0)
        _finite(self.sublimation_demand_mm_per_day, "sublimation_demand_mm_per_day",
                minimum=0.0)
        _finite(self.max_swe_mm, "max_swe_mm", positive=True)
        _finite(self.min_melt_temperature_c, "min_melt_temperature_c")
        if not isinstance(self.phase_parameters, metric_pet_et.PetEtParameters):
            raise ValueError("phase_parameters must be PetEtParameters")
        if self.phase_parameters.freezing_threshold_c != self.freezing_threshold_c:
            raise ValueError("the phase threshold must be the one the adapter is given; "
                             "two thresholds would be two phases")

    def identity(self):
        payload = asdict(self)
        payload["phase_parameters"] = asdict(self.phase_parameters)
        payload["phase_parameters"].pop("runoff", None)
        return payload


def _edges(time_edges_s):
    edges = np.asarray(time_edges_s, np.float64)
    if edges.ndim != 1 or edges.size < 2 or edges.size - 1 > MAX_INTERVALS:
        raise ValueError("time_edges_s must be 1D with 1..%d intervals" % MAX_INTERVALS)
    if not np.isfinite(edges).all() or np.any(np.diff(edges) <= 0.0):
        raise ValueError("time_edges_s must be finite and strictly increasing")
    return edges


def _cells(values, name, shape):
    array = np.asarray(values, np.float64)
    if array.shape != shape:
        raise ValueError("%s must have shape %s, got %s"
                         % (name, list(shape), list(array.shape)))
    if not np.isfinite(array).all():
        raise ValueError("%s must be finite" % name)
    return array


def _points(x_m, z_m):
    x = np.asarray(x_m, np.float64).reshape(-1)
    z = np.asarray(z_m, np.float64).reshape(-1)
    if x.shape != z.shape or x.size == 0 or x.size > MAX_CELLS:
        raise ValueError("x_m/z_m must be 1..%d matching points" % MAX_CELLS)
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("world coordinates must be finite")
    return x, z


def _temperature_intervals(temperature_c, temperature_source, edges, parameters):
    """``(T, N)`` interval mean temperature and ``(T, N)`` liquid fraction.

    Two declared contracts, and never a silent conversion between them:

    ``monthly_mean``       ``(12, N)`` monthly means; the interval mean is the elapsed-second
                          weighted average from the repository's own calendar, and the phase
                          mixture comes from ``metric_pet_et.liquid_fraction``. That public
                          entry reads the same 365-day clock through the PET adapter's own
                          ``dt_s <= 3600`` gate, so **every interval must be at most one hour**
                          on this contract. A longer interval is refused rather than silently
                          split: the bucket gate is not widened, and this module does not carry
                          a second phase formula to work around it.
    ``declared_interval``  ``(T, N)`` one declared mean per interval; the phase is the same
                          declared threshold applied to that interval mean. A ``(T, N)``
                          array is **never** handed to ``liquid_fraction``, which requires the
                          twelve-month axis. This contract has **no** per-interval length
                          ceiling; the bucket consumption is split separately.
    """
    intervals = int(edges.size - 1)
    if temperature_source not in TEMPERATURE_SOURCES:
        raise ValueError("temperature_source must be one of %s" % (TEMPERATURE_SOURCES,))
    array = np.asarray(temperature_c, np.float64)
    if temperature_source == "monthly_mean":
        if array.ndim != 2 or array.shape[0] != 12:
            raise ValueError("monthly_mean temperature must be [12, N]")
        cells = array.shape[1]
        _cells(array, "monthly_temperature_c", (12, cells))
        longest = float(np.max(np.diff(edges)))
        if longest > MAX_BUCKET_STEP_S:
            raise ValueError(
                "the monthly_mean contract reads the calendar through metric_pet_et, whose "
                "own gate refuses dt_s > %r s; the longest interval here is %r s. Use edges "
                "of at most one hour, or declare per-interval temperatures with "
                "temperature_source='declared_interval', which has no such ceiling. The PET "
                "gate is not widened here." % (MAX_BUCKET_STEP_S, longest))
        month_seconds = metric_pet_et.calendar_month_seconds(edges)
        total = month_seconds.sum(axis=1)
        if np.any(total <= 0.0):
            raise ValueError("every interval must spend positive time inside the calendar")
        interval_temperature = (month_seconds @ array) / total[:, None]
        fraction = metric_pet_et.liquid_fraction(array, month_seconds, parameters.phase_parameters)
        return interval_temperature, fraction
    if array.ndim != 2 or array.shape[0] != intervals:
        raise ValueError("declared_interval temperature must be [intervals, N] = [%d, N]"
                         % intervals)
    cells = array.shape[1]
    _cells(array, "interval_temperature_c", (intervals, cells))
    fraction = (array >= parameters.freezing_threshold_c).astype(np.float64)
    return array, fraction


def advance_snow_ice(*, swe_start_mm, temperature_c, precip_mm, time_edges_s, x_m, z_m,
                     temperature_source="monthly_mean",
                     order="melt_then_sublimation", parameters=None):
    """Advance one seasonal snow store per cell over the declared intervals.

    ``precip_mm`` is the **depth per interval** (``[intervals, N]``), not a rate and not a
    monthly total: the caller declares it on the same physical edges it declares the
    temperature on.

    The reported liquid path is ``liquid_to_land_mm = liquid_precip_mm + melt_mm``; both parts
    are also returned separately so a consumer can attribute them. That single liquid field
    is what the soil bucket takes (:func:`advance_soil_with_liquid`), and the melt is **not**
    handed to the PET adapter as well: the phase decision has already been made here, and
    sending melt back through the adapter would freeze it a second time on a cold month mean.
    """
    edges = _edges(time_edges_s)
    intervals = int(edges.size - 1)
    parameters = SnowParameters() if parameters is None else parameters
    if not isinstance(parameters, SnowParameters):
        raise ValueError("parameters must be SnowParameters")
    if order not in MELT_ORDERS:
        raise ValueError("order must be one of %s" % (MELT_ORDERS,))
    temperature, fraction = _temperature_intervals(temperature_c, temperature_source, edges,
                                                   parameters)
    cells = temperature.shape[1]
    x, z = _points(x_m, z_m)
    if x.size != cells:
        raise ValueError("one world point per cell is required: %d points for %d cells"
                         % (x.size, cells))
    start = np.asarray(swe_start_mm, np.float64)
    if start.shape != (cells,):
        raise ValueError("swe_start_mm must be one value per cell")
    if not np.isfinite(start).all() or np.any(start < 0.0):
        raise ValueError("swe_start_mm must be finite and nonnegative")
    if np.any(start > parameters.max_swe_mm):
        raise ValueError("swe_start_mm exceeds the declared ceiling %r mm"
                         % parameters.max_swe_mm)
    precip = _cells(precip_mm, "precip_mm", (intervals, cells))
    if np.any(precip < 0.0):
        raise ValueError("precip_mm must be nonnegative")
    dt_days = np.diff(edges) / 86400.0

    swe = np.zeros((intervals + 1, cells), np.float64)
    swe[0] = start
    solid = np.zeros((intervals, cells), np.float64)
    liquid = np.zeros((intervals, cells), np.float64)
    melt = np.zeros((intervals, cells), np.float64)
    sublimation = np.zeros((intervals, cells), np.float64)
    for index in range(intervals):
        solid[index] = (1.0 - fraction[index]) * precip[index]
        liquid[index] = fraction[index] * precip[index]
        available = swe[index] + solid[index]
        if np.any(available > parameters.max_swe_mm):
            raise ValueError("interval %d would exceed the declared SWE ceiling %r mm"
                             % (index, parameters.max_swe_mm))
        potential_melt = (parameters.degree_day_melt_mm_per_day_c
                          * np.maximum(temperature[index] - parameters.min_melt_temperature_c,
                                       0.0)
                          * dt_days[index])
        demand = parameters.sublimation_demand_mm_per_day * dt_days[index]
        if order == "melt_then_sublimation":
            removed_melt = np.minimum(potential_melt, available)
            removed_sublimation = np.minimum(demand, available - removed_melt)
        else:
            removed_sublimation = np.minimum(demand, available)
            removed_melt = np.minimum(potential_melt, available - removed_sublimation)
        melt[index] = removed_melt
        sublimation[index] = removed_sublimation
        swe[index + 1] = available - removed_melt - removed_sublimation
    if np.any(swe < 0.0):                       # defensive: the limits above already ensure it
        raise RuntimeError("the snow store went negative")

    liquid_to_land = liquid + melt
    residual = (swe[-1] - swe[0] - solid.sum(axis=0) + melt.sum(axis=0)
                + sublimation.sum(axis=0))
    if np.abs(residual).max() > 1e-9:
        raise RuntimeError("the SWE ledger does not close (max |residual| = %r mm)"
                           % float(np.abs(residual).max()))
    payload = {
        "schema": SCHEMA,
        "logical_version": LOGICAL_VERSION,
        "algorithm": ALGORITHM,
        "temperature_source": temperature_source,
        "order": order,
        "parameters": parameters.identity(),
        "phase_source": PHASE_SOURCE,
        "calendar_source": CALENDAR_SOURCE,
        "sublimation_policy": SUBLIMATION_POLICY,
        "time_edges_s": [float(v) for v in edges],
        "x_m": [float(v) for v in x],
        "z_m": [float(v) for v in z],
        "cell_area_m2": CELL_AREA_M2,
        "spacing_m": NATIVE_SPACING_M,
        "claims_denied": {"snow_depth": True, "glacier": True, "ice_flow": True,
                          "ice_erosion": True, "hydraulics": True, "channel": True,
                          "calibrated": True, "one_metre_accuracy": True},
    }
    arrays = {
        "swe_edge_mm": swe,
        "solid_precip_mm": solid,
        "liquid_precip_mm": liquid,
        "melt_mm": melt,
        "sublimation_mm": sublimation,
        "liquid_to_land_mm": liquid_to_land,
    }
    return {
        "arrays": arrays,
        "ledger_mm": {
            "swe_start_mm": [float(v) for v in swe[0]],
            "swe_end_mm": [float(v) for v in swe[-1]],
            "solid_precip_mm_total": [float(v) for v in solid.sum(axis=0)],
            "liquid_precip_mm_total": [float(v) for v in liquid.sum(axis=0)],
            "melt_mm_total": [float(v) for v in melt.sum(axis=0)],
            "sublimation_mm_total": [float(v) for v in sublimation.sum(axis=0)],
            "liquid_to_land_mm_total": [float(v) for v in liquid_to_land.sum(axis=0)],
            "residual_mm": [float(v) for v in residual],
            "max_abs_residual_mm": float(np.abs(residual).max()),
            "sublimation_leaves_the_cell": True,
            "note": ("SWE closes as swe_end - swe_start = solid - melt - sublimation; the melt "
                     "and the direct liquid precipitation both go to the land surface once, "
                     "and the sublimation does not"),
        },
        "metadata": payload,
        "identity_sha256": digest({
            "metadata": payload,
            "arrays": {name: array_hash(value) for name, value in sorted(arrays.items())}}),
    }


def bucket_substeps(dt_s):
    """Fixed sub-step split so the existing bucket's own ``dt_s <= 3600`` bound is honoured."""
    dt = _finite(dt_s, "dt_s", positive=True)
    count = int(math.ceil(dt / MAX_BUCKET_STEP_S))
    if count < 1:
        raise ValueError("at least one sub-step is required")
    return [dt / count for _ in range(count)]


def advance_soil_with_liquid(liquid_to_land_mm, time_edges_s, states, *, x_m, z_m,
                             runoff_parameters=None, max_step_s=MAX_BUCKET_STEP_S):
    """Consume the liquid path **once** through the repository's existing soil bucket.

    ``liquid_to_land_mm`` is ``[intervals, N]`` and already includes melt; it is converted to
    the bucket's ``mm/h`` rate per interval and stepped in fixed sub-steps no longer than the
    bucket's declared ceiling. The bucket's own limit is never relaxed, and a longer snow
    interval is reported as a split rather than silently shortened.

    Only :func:`advance_soil` is called: the melt is not re-phased and not passed to the PET
    adapter, so no water is frozen twice and none is deducted twice.
    """
    edges = _edges(time_edges_s)
    intervals = int(edges.size - 1)
    liquid = np.asarray(liquid_to_land_mm, np.float64)
    if liquid.ndim != 2 or liquid.shape[0] != intervals:
        raise ValueError("liquid_to_land_mm must be [intervals, N]")
    if not np.isfinite(liquid).all() or np.any(liquid < 0.0):
        raise ValueError("liquid_to_land_mm must be finite and nonnegative")
    cells = liquid.shape[1]
    x, z = _points(x_m, z_m)
    if x.size != cells:
        raise ValueError("one world point per cell is required")
    parameters = runoff_parameters or RunoffParameters()
    if not isinstance(parameters, RunoffParameters):
        raise ValueError("runoff_parameters must be RunoffParameters")
    if max_step_s > MAX_BUCKET_STEP_S:
        raise ValueError("the bucket ceiling is %r s; it is never raised here"
                         % MAX_BUCKET_STEP_S)
    state = np.array(states, np.float64, copy=True)
    if state.shape != (3, cells):
        raise ValueError("states must be [3, N] (soil, fast, slow)")
    if not np.isfinite(state).all() or np.any(state < 0.0):
        raise ValueError("states must be finite and nonnegative")
    released = np.zeros((intervals, cells), np.float64)
    evaporated = np.zeros((intervals, cells), np.float64)
    change = np.zeros((intervals, cells), np.float64)
    substeps_used = []
    for index in range(intervals):
        span = float(np.diff(edges)[index])
        if span > max_step_s:
            count = int(math.ceil(span / max_step_s))
            parts = [span / count] * count
        else:
            parts = [span]
        rate = liquid[index] / (span / 3600.0)   # mm/h for this interval
        for dt in parts:
            state, release, et, delta = advance_soil(rate, state, dt_s=float(dt),
                                                     parameters=parameters)
            released[index] += release
            evaporated[index] += et
            change[index] += delta
        substeps_used.append(len(parts))
    return {
        "states": state,
        "released_mm": released,
        "evaporated_mm": evaporated,
        "state_change_mm": change,
        "substeps_per_interval": substeps_used,
        "max_step_s": float(max_step_s),
        "bucket_module": metric_pet_et.BUCKET_MODULE,
        "note": ("the liquid path is consumed once by the existing bucket; the melt is not "
                 "sent back through the PET adapter, so nothing is re-frozen or deducted "
                 "twice"),
    }


def describe():
    return {
        "schema": SCHEMA,
        "logical_version": LOGICAL_VERSION,
        "algorithm": ALGORITHM,
        "temperature_sources": list(TEMPERATURE_SOURCES),
        "melt_orders": list(MELT_ORDERS),
        "phase_source": PHASE_SOURCE,
        "calendar_source": CALENDAR_SOURCE,
        "sublimation_policy": SUBLIMATION_POLICY,
        "not_modelled": list(NOT_MODELLED),
        "monthly_mean_max_interval_s": MONTHLY_MEAN_MAX_INTERVAL_S,
        "limitations": list(LIMITATIONS),
        "default_parameters": SnowParameters().identity(),
        "bucket_module": metric_pet_et.BUCKET_MODULE,
        "max_bucket_step_s": MAX_BUCKET_STEP_S,
        "cells_bound": MAX_CELLS,
        "intervals_bound": MAX_INTERVALS,
        "cell_area_m2": CELL_AREA_M2,
        "spacing_m": NATIVE_SPACING_M,
    }
