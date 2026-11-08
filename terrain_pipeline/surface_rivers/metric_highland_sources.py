"""Fixed-geometry highland source regions and river-head candidates at 30 m.

What this module is, and what it deliberately is not
----------------------------------------------------
Stage B1 *geometry* of the approved highland/mainstem route
(``.scratch/highland-mainstem-world``). It answers three questions for one declared
window, and nothing else:

``highland_relief`` / ``highland_candidates``
    The frozen ``highland-source-geometry-dev-v1`` elevation gate and 300 m local
    relief gate. The unresolved pattern is preserved, never repaired: a cell whose
    21x21 square neighbourhood is not fully resolved has **no** relief (NaN), and its
    elevation stays NaN exactly where the loader left it.
``source_regions``
    D4 connected patches of those candidates, identified by **world** signed-int64
    members (never by window-local indices), with the declared area gate, and with an
    explicit ``pending`` verdict as soon as a patch touches the support edge or an
    unresolved neighbour. A cropped window can split a patch; that split is recorded
    as pending and is never presented as a complete source region.
``head_candidates``
    River heads where the **verified strict irregular graph** contribution first crosses 100 cells
    *and* that crossing lies inside an area-qualified highland patch, then
    de-duplicated inside each region at 600 m by a declared deterministic order
    (known contribution scale descending, then world ``(x, z)`` ascending).

Deliberately absent
-------------------
* No second irregular graph. The one authority is
  ``native_30m_source.build_strict_topology`` (which itself calls
  ``irregular_grid.strict_receivers``); D4 is used here **only** to group source
  region members and never replaces the river irregular graph.
* No second accumulation. Known contribution counts and propagated completeness come
  from ``metric_network_accumulation.accumulate_network_discharge`` with unit local Q.
* No mainstem/reach generation, no corridor, no lake, no routing repair. This stage
  emits **head candidates only**: a river that already formed downstream is neither
  re-sourced in the lowland nor cut at the patch boundary here, because no mainstem
  path is drawn in this stage at all.
* No runoff, soil bucket, water balance, rainfall, snow or perennial-flow claim.
  A geometry candidate is not water. ``rainfall_supported`` stays
  ``rainfall_supported_pending`` and ``perennial_flow_certified`` stays ``False``;
  nothing in this module can flip either.
* No support that follows a render window: the region identity is world-anchored and
  excludes the window origin, shape and any support-local index.

Frozen rule
-----------
``highland-source-geometry-dev-v1`` is the only rule implemented here. Every value is
``declared_uncalibrated``: fixed engineering assumptions chosen from one saved P1
distribution, not an empirical law and not a global claim. A different value is a new
rule identity with a new approval, so :func:`_resolve_rule` **refuses** any deviation
instead of accepting a knob.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import (
    label,
    maximum_filter,
    maximum_filter1d,
    minimum_filter,
    minimum_filter1d,
)

from terrain_pipeline.common_infra import identity
from terrain_pipeline.drainage import MAX_NETWORK_CELLS as MAX_NETWORK_CELLS
from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge
from terrain_pipeline.surface_rivers.native_30m_source import (
    DEFAULT_WORLD_SEED,
    NATIVE_SPACING_M,
    build_strict_topology,
)

__all__ = [
    "ARRAY_NAMES",
    "BUNDLE_KEYS",
    "DECLARED_PARAMETERS",
    "DECLARED_SPACING_M",
    "DECLARED_WORLD_SEED",
    "DEFAULT_MAX_CELLS",
    "LOGICAL_VERSION",
    "REGION_RECORD_KEYS",
    "RULE_VERSION",
    "SCHEMA",
    "STATUS_HEAD_CERTIFIED",
    "STATUS_HEAD_PENDING",
    "STATUS_REGION_BELOW_AREA",
    "STATUS_REGION_COMPLETE",
    "STATUS_REGION_PENDING",
    "build_highland_sources",
    "declared_rule",
    "head_candidates",
    "highland_candidates",
    "highland_relief",
    "identity",
    "member_sha256",
    "source_regions",
    "validate_highland_sources",
]


# --------------------------------------------------------------------------- #
# declared vocabulary, budgets and the frozen geometric rule
# --------------------------------------------------------------------------- #
SCHEMA = "metric-highland-source-regions-v1"
RULE_VERSION = "highland-source-geometry-dev-v1"
LOGICAL_VERSION = "b-highland-geometry-irregular-v2"

#: The frozen continuous baseline (``CONTRIBUTING.md``), and the native lattice.
DECLARED_WORLD_SEED = DEFAULT_WORLD_SEED          # 20261020
DECLARED_SPACING_M = NATIVE_SPACING_M             # 30.0

#: P2 declared support budget of this route (``.scratch/highland-mainstem-world/
#: parameters.md``). It is **not** raised here: a larger support needs its own declared
#: budget card, a pre-allocation refusal negative and a separate review. It is also
#: the default ``max_cells`` of every public entry point, so an ad-hoc caller cannot
#: silently compute on a wider window. ``MAX_CELLS_P2 == metric_world_domains
#: .MAX_SUPPORT_CELLS == review_world_reaches.MAX_SUPPORT_CELLS`` is asserted by the
#: tests, so the three cannot drift apart unnoticed.
DEFAULT_MAX_CELLS = 148_225

#: The single frozen development rule. Each value is ``declared_uncalibrated``.
#: Semantics, in the order they are applied:
#:
#: ``model_sea_level_m``
#:     The original TD model height reference. It is **not** a surveyed vertical
#:     datum; the elevation gate is absolute against it and is never recomputed per
#:     window (no per-window percentile renormalisation).
#: ``min_source_elevation_above_sea_m``
#:     Ridge-ward elevation gate, between P75 and P90 of the saved P1 distribution,
#:     rounded to a hundred metres.
#: ``relief_radius_m`` / ``relief_window_cells``
#:     A **square** 21x21 window (axis radius 300 m, corners further): the corner
#:     distance is larger than the radius, so this must never be described as a disc.
#: ``min_local_relief_m``
#:     Removes relatively flat high plateaus; below the P10 of the saved sample.
#: ``min_source_region_area_m2``
#:     90000 m2 = at least 100 native cells, so one noisy cell is never a source.
#: ``source_head_min_spacing_m``
#:     Within-region head spacing, of the order of the full relief-window width. It is
#:     not a radius for handing a head across a ridge.
#: ``min_head_upstream_cells``
#:     Geometric size gate on known contribution. It is **not** discharge, not a
#:     perennial-flow threshold and not a water volume.
#: ``slope_filter``
#:     Deliberately absent: real slope is kept as a diagnostic and no slope hard gate
#:     is applied. Introducing one is a new rule version.
DECLARED_PARAMETERS = {
    "model_sea_level_m": 0.0,
    "min_source_elevation_above_sea_m": 1400.0,
    "relief_radius_m": 300.0,
    "relief_window_cells": 21,
    "min_local_relief_m": 100.0,
    "min_source_region_area_m2": 90000.0,
    "source_head_min_spacing_m": 600.0,
    "min_head_upstream_cells": 100,
    "slope_filter": None,
}

#: Calibration status of every declared value. ``declared_uncalibrated`` is the only
#: honest label: the numbers were chosen from one saved P1 distribution for one
#: declared engineering hypothesis, and no observation calibrated them.
CALIBRATION_STATUS = "declared_uncalibrated"

STATUS_REGION_COMPLETE = "region_candidate_complete"
STATUS_REGION_PENDING = "region_candidate_pending"
STATUS_REGION_BELOW_AREA = "region_below_area"

STATUS_HEAD_CERTIFIED = "head_geometry_certified"
STATUS_HEAD_PENDING = "head_geometry_pending"

# Machine-stable reason vocabulary. A reason is a word, never prose, so a caller can
# classify a refusal without matching a message.
REASON_COMPLETE = "complete"
REASON_SUPPORT_EDGE = "support_edge"
REASON_UNKNOWN_NEIGHBOUR = "unknown_neighbour"
REASON_REGION_BELOW_AREA = "region_below_min_area"
REASON_OUTSIDE_QUALIFIED_REGION = "outside_qualified_region"
REASON_SPACING_SUPPRESSED = "spacing_suppressed"
REASON_SUPPRESSION_PENDING = "spacing_suppression_pending"
REASON_UPSTREAM_UNKNOWN = "upstream_unknown"
REASON_NO_CANDIDATE = "no_candidate"
REASON_BUDGET = "budget_exceeded"
REASON_ELEVATION_MASK = "elevation_mask_contract"
REASON_SEED_MISMATCH = "seed_mismatch"
REASON_SPACING_MISMATCH = "spacing_mismatch"
REASON_SHAPE_MISMATCH = "shape_mismatch"
REASON_UNDECLARED_RULE = "undeclared_rule"
REASON_GRAPH_INVALID = "routing_graph_invalid"

REASON_VOCABULARY = (
    REASON_COMPLETE, REASON_SUPPORT_EDGE, REASON_UNKNOWN_NEIGHBOUR,
    REASON_REGION_BELOW_AREA, REASON_OUTSIDE_QUALIFIED_REGION,
    REASON_SPACING_SUPPRESSED, REASON_SUPPRESSION_PENDING, REASON_UPSTREAM_UNKNOWN,
    REASON_NO_CANDIDATE, REASON_BUDGET, REASON_ELEVATION_MASK, REASON_SEED_MISMATCH,
    REASON_SPACING_MISMATCH, REASON_SHAPE_MISMATCH, REASON_UNDECLARED_RULE,
    REASON_GRAPH_INVALID,
)

#: The public array block of a bundle. Every derived array is recomputable from
#: ``elevation_m`` + ``resolved_mask`` + the declared rule, which is what makes the
#: independent validator possible at all.
ARRAY_NAMES = (
    "elevation_m", "resolved_mask", "relief_m", "highland_candidate",
    "region_index", "region_ptr", "region_cells", "head_flags",
    "known_upstream_cells", "upstream_complete",
)

BUNDLE_KEYS = {"schema", "arrays", "regions", "heads", "rejects", "metadata",
               "identity_sha256"}

#: The record fields compared by the validator, besides the member CSR arrays. The
#: member **world** coordinates live in ``region_cells`` (int64 pairs), not in JSON:
#: packing or float coordinates are never member identity.
REGION_RECORD_KEYS = (
    "region_id", "source_identity_sha256", "member_count", "area_m2", "member_sha256",
    "status", "reason_codes", "min_elevation_m", "max_elevation_m", "min_relief_m",
    "touches_support_edge", "unknown_neighbour_cells", "qualified", "anchor_world_xz",
    "head_count",
)
HEAD_RECORD_KEYS = (
    "head_id", "region_id", "world_xz", "known_upstream_cells", "status",
    "reason_codes", "geometry_certified",
)

#: A window that carries routing results is refused: topology, contribution and
#: completeness are rebuilt from the field and the mask, so no caller can hand in a
#: receiver or a ``complete_mask`` through the source dictionary.
FORBIDDEN_WINDOW_KEYS = (
    "receiver", "terminal_kind", "upstream_cells", "complete_mask",
    "upstream_unknown_mask", "region_index", "region_id",
)

_D4_STRUCTURE = np.array([[False, True, False],
                          [True, True, True],
                          [False, True, False]], dtype=bool)
_D4_STEPS = ((-1, 0), (0, -1), (0, 1), (1, 0))

_SOURCE_SHA_CACHE = {}


# --------------------------------------------------------------------------- #
# 0. scalar / rule validation
# --------------------------------------------------------------------------- #
def _strict_int(value, name):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("%s must be an integer, not a boolean" % name)
    if isinstance(value, (int, np.integer)):
        return int(value)
    raise ValueError("%s must be an integer, got %s" % (name, type(value).__name__))


def _strict_float(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, float, np.integer, np.floating)):
        raise ValueError("%s must be a number" % name)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("%s must be finite" % name)
    return result


def _int_pair(values, name):
    if isinstance(values, np.ndarray):
        if values.shape != (2,):
            raise ValueError("%s must carry exactly two integers" % name)
        items = values.tolist()
    elif isinstance(values, (list, tuple)) and len(values) == 2:
        items = list(values)
    else:
        raise ValueError("%s must be a two-element sequence of integers" % name)
    return [_strict_int(item, name) for item in items]


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _parameters_sha256(parameters):
    return hashlib.sha256(_canonical(parameters).encode("utf-8")).hexdigest()


def declared_rule():
    """The frozen rule as a data record (a copy: callers cannot mutate the module)."""
    return {
        "rule_version": RULE_VERSION,
        "logical_version": LOGICAL_VERSION,
        "world_seed": DECLARED_WORLD_SEED,
        "spacing_m": DECLARED_SPACING_M,
        "parameters": copy.deepcopy(DECLARED_PARAMETERS),
        "calibration": {key: CALIBRATION_STATUS for key in DECLARED_PARAMETERS},
        "slope_filter": DECLARED_PARAMETERS["slope_filter"],
        "parameters_sha256": _parameters_sha256(DECLARED_PARAMETERS),
    }


def _normalise_parameters(rule):
    """Accept the declared record (or its ``parameters`` mapping) and nothing else."""
    if not isinstance(rule, dict):
        raise ValueError("%s: the geometric rule must be a mapping" % REASON_UNDECLARED_RULE)
    if "parameters" in rule:
        for key in ("rule_version", "world_seed", "spacing_m"):
            if key not in rule:
                raise ValueError("%s: rule record is missing %r"
                                 % (REASON_UNDECLARED_RULE, key))
        if rule["rule_version"] != RULE_VERSION:
            raise ValueError("%s: rule_version %r is not %r"
                             % (REASON_UNDECLARED_RULE, rule["rule_version"], RULE_VERSION))
        if _strict_int(rule["world_seed"], "world_seed") != DECLARED_WORLD_SEED:
            raise ValueError("%s: world_seed %r is not the frozen %d"
                             % (REASON_SEED_MISMATCH, rule["world_seed"],
                                DECLARED_WORLD_SEED))
        if _strict_float(rule["spacing_m"], "spacing_m") != DECLARED_SPACING_M:
            raise ValueError("%s: spacing_m %r is not the native %.1f m"
                             % (REASON_SPACING_MISMATCH, rule["spacing_m"],
                                DECLARED_SPACING_M))
        supplied = rule["parameters"]
        extras = sorted(set(rule) - {"rule_version", "logical_version", "world_seed",
                                     "spacing_m", "parameters", "calibration",
                                     "slope_filter", "parameters_sha256"})
        if extras:
            raise ValueError("%s: unexpected rule members %s"
                             % (REASON_UNDECLARED_RULE, extras))
    else:
        supplied = rule
    if not isinstance(supplied, dict):
        raise ValueError("%s: parameters must be a mapping" % REASON_UNDECLARED_RULE)
    missing = sorted(set(DECLARED_PARAMETERS) - set(supplied))
    extras = sorted(set(supplied) - set(DECLARED_PARAMETERS))
    if missing or extras:
        raise ValueError("%s: parameters must be exactly the frozen keys (missing %s, "
                         "unexpected %s)"
                         % (REASON_UNDECLARED_RULE, missing, extras))
    normalised = {}
    for key, expected in DECLARED_PARAMETERS.items():
        value = supplied[key]
        if expected is None:
            if value is not None:
                raise ValueError("%s: %r is frozen to None (no slope hard gate); a slope "
                                 "gate needs a new rule_version and a separate approval"
                                 % (REASON_UNDECLARED_RULE, key))
            normalised[key] = None
        elif isinstance(expected, int):
            normalised[key] = _strict_int(value, key)
        else:
            normalised[key] = _strict_float(value, key)
    if normalised != DECLARED_PARAMETERS:
        differences = {key: normalised[key] for key in DECLARED_PARAMETERS
                       if normalised[key] != DECLARED_PARAMETERS[key]}
        raise ValueError("%s: %s is the only geometric rule this module implements; "
                         "refused differences %s. A different gate is a new rule_version, "
                         "not a call-site knob." % (REASON_UNDECLARED_RULE, RULE_VERSION,
                                                   differences))
    return normalised


def _resolve_rule(rule):
    """Return the frozen parameters; ``None`` means the declared rule."""
    if rule is None:
        return copy.deepcopy(DECLARED_PARAMETERS)
    return _normalise_parameters(rule)


def _geometry(parameters):
    """Derived scalars of the rule, computed once (never guessed at a call site)."""
    spacing = DECLARED_SPACING_M
    window_cells = int(parameters["relief_window_cells"])
    if window_cells % 2 == 0:
        raise ValueError("%s: the relief window must be odd (a centre cell)"
                         % REASON_UNDECLARED_RULE)
    radius_cells = (window_cells - 1) // 2
    if abs(radius_cells * spacing - float(parameters["relief_radius_m"])) > 1e-9:
        raise ValueError("%s: relief_radius_m %r disagrees with %d cells at %.1f m"
                         % (REASON_UNDECLARED_RULE, parameters["relief_radius_m"],
                            radius_cells, spacing))
    cell_area = spacing * spacing
    min_cells = int(math.ceil(float(parameters["min_source_region_area_m2"]) / cell_area))
    if abs(min_cells * cell_area - float(parameters["min_source_region_area_m2"])) > 1e-6:
        raise ValueError("%s: min_source_region_area_m2 %r is not a whole number of "
                         "%.1f m2 cells"
                         % (REASON_UNDECLARED_RULE,
                            parameters["min_source_region_area_m2"], cell_area))
    return {
        "spacing_m": spacing,
        "cell_area_m2": cell_area,
        "window_cells": window_cells,
        "radius_cells": radius_cells,
        "min_region_cells": min_cells,
        "elevation_threshold_m": (float(parameters["model_sea_level_m"])
                                  + float(parameters["min_source_elevation_above_sea_m"])),
        "min_relief_m": float(parameters["min_local_relief_m"]),
        "head_spacing_m": float(parameters["source_head_min_spacing_m"]),
        "min_head_cells": int(parameters["min_head_upstream_cells"]),
    }


# --------------------------------------------------------------------------- #
# 1. window / array gates (refusals happen before any computation)
# --------------------------------------------------------------------------- #
def _arrays(elevation_m, resolved_mask):
    """Strict field/mask contract: float64 2D, boolean mask, NaN exactly where unresolved."""
    field = elevation_m
    if not isinstance(field, np.ndarray) or field.dtype != np.float64 or field.ndim != 2:
        raise ValueError("elevation must be a 2D float64 ndarray")
    mask = resolved_mask
    if (not isinstance(mask, np.ndarray) or mask.dtype != np.bool_
            or mask.shape != field.shape):
        raise ValueError("resolved_mask must be a boolean array of the elevation's shape")
    if min(field.shape) < 2:
        raise ValueError("%s: a window of at least 2x2 cells is required, got %s"
                         % (REASON_SHAPE_MISMATCH, list(field.shape)))
    # The unresolved state must survive: NaN exactly on unresolved cells, finite on
    # resolved ones. A filled-in unknown is refused rather than reinterpreted.
    if not np.array_equal(np.isnan(field), ~mask) or not np.isfinite(field[mask]).all():
        raise ValueError("%s: elevation must be NaN exactly on the unresolved cells and "
                         "finite on every resolved cell (no zero fill, no extrapolation)"
                         % REASON_ELEVATION_MASK)
    return field, mask


def _check_window(window, *, parameters, max_cells):
    """Validate one assembled window dict and its declared budget."""
    if not isinstance(window, dict):
        raise ValueError("a window is the loader's mapping")
    required = ("field", "resolved_mask", "origin_native_xz", "shape_zx",
                "world_seed", "spacing_m")
    missing = [key for key in required if key not in window]
    if missing:
        raise ValueError("window is missing %s" % missing)
    smuggled = [key for key in FORBIDDEN_WINDOW_KEYS if key in window]
    if smuggled:
        raise ValueError("%s: a window may not carry routing results (%s); topology, "
                         "contribution and completeness are rebuilt from the field and "
                         "the mask" % (REASON_GRAPH_INVALID, smuggled))
    seed = _strict_int(window["world_seed"], "world_seed")
    if seed != DECLARED_WORLD_SEED:
        raise ValueError("%s: world_seed %d is not the frozen %d"
                         % (REASON_SEED_MISMATCH, seed, DECLARED_WORLD_SEED))
    spacing = _strict_float(window["spacing_m"], "spacing_m")
    if spacing != DECLARED_SPACING_M:
        raise ValueError("%s: spacing_m %r is not the native %.1f m"
                         % (REASON_SPACING_MISMATCH, spacing, DECLARED_SPACING_M))
    budget = _strict_int(max_cells, "max_cells")
    if budget <= 0 or budget > DEFAULT_MAX_CELLS:
        raise ValueError("%s: max_cells=%d is outside the declared P2 budget of %d; the "
                         "budget is not raised at a call site" % (REASON_BUDGET, budget,
                                                                 DEFAULT_MAX_CELLS))
    field, mask = _arrays(window["field"], window["resolved_mask"])
    rows, columns = field.shape
    declared_shape = _int_pair(window["shape_zx"], "shape_zx")
    if declared_shape != [rows, columns]:
        raise ValueError("%s: declared shape %s disagrees with the field %s"
                         % (REASON_SHAPE_MISMATCH, declared_shape, [rows, columns]))
    origin = _int_pair(window["origin_native_xz"], "origin_native_xz")
    for value in origin:
        if abs(value + max(rows, columns)) > 2 ** 62:
            raise ValueError("%s: origin %s is outside the signed int64 lattice"
                             % (REASON_SHAPE_MISMATCH, origin))
    cells = int(rows) * int(columns)
    # Budget refusal comes before any full-extent array is allocated.
    if cells > budget:
        raise ValueError("%s: window %dx%d = %d cells exceeds max_cells=%d"
                         % (REASON_BUDGET, rows, columns, cells, budget))
    if cells > MAX_NETWORK_CELLS:
        raise ValueError("%s: %d cells exceeds the reused accumulator ceiling %d"
                         % (REASON_BUDGET, cells, MAX_NETWORK_CELLS))
    if cells > DEFAULT_MAX_CELLS:
        raise ValueError("%s: %d cells exceeds the declared P2 support of %d"
                         % (REASON_BUDGET, cells, DEFAULT_MAX_CELLS))
    return field, mask, origin, rows, columns


# --------------------------------------------------------------------------- #
# 2. the frozen elevation and relief gates
# --------------------------------------------------------------------------- #
def _window_extremes(field, mask, window_cells, *, separable):
    """Square window max/min, with the exterior treated as unresolved.

    ``separable=False`` uses the 2-D filters (the producer path), ``separable=True``
    two 1-D passes (the validator path). They are two implementations of the same
    declared square window, which is exactly what an independent re-derivation needs;
    the unresolved exterior is constant in both, so no sentinel can enter a retained
    statistic.
    """
    high = np.where(mask, field, -np.inf)
    low = np.where(mask, field, np.inf)
    if separable:
        hi = maximum_filter1d(maximum_filter1d(high, window_cells, axis=0,
                                               mode="constant", cval=-np.inf),
                              window_cells, axis=1, mode="constant", cval=-np.inf)
        lo = minimum_filter1d(minimum_filter1d(low, window_cells, axis=0,
                                               mode="constant", cval=np.inf),
                              window_cells, axis=1, mode="constant", cval=np.inf)
        return hi, lo, _separable_coverage(mask, window_cells)
    hi = maximum_filter(high, size=window_cells, mode="constant", cval=-np.inf)
    lo = minimum_filter(low, size=window_cells, mode="constant", cval=np.inf)
    covered = minimum_filter(mask.astype(np.uint8), size=window_cells,
                             mode="constant", cval=0).astype(bool)
    return hi, lo, covered


def _separable_coverage(mask, window_cells):
    """Separable "the whole window is resolved" test, padded with constant False.

    Padding with ``False`` is what makes the support edge differ from an interior cell:
    a window that reaches past the support is not fully resolved and carries no relief.
    """
    radius = (window_cells - 1) // 2
    rows, columns = mask.shape
    counts = mask.astype(np.int32)
    # A leading zero row/column makes the window sum a plain difference of two cumulative
    # entries: sum over [i, i + window_cells) is cumulative[i + window_cells] -
    # cumulative[i]. Without those leading zeros the window would be off by one cell and
    # the border band would be wrong -- which is exactly what a support edge must never be.
    by_row = np.pad(counts, ((radius, radius), (0, 0)), mode="constant",
                    constant_values=0)
    row_cumulative = np.concatenate([np.zeros((1, columns), np.int32),
                                     np.cumsum(by_row, axis=0, dtype=np.int32)], axis=0)
    rows_ok = ((row_cumulative[window_cells:window_cells + rows]
                - row_cumulative[:rows]) == window_cells)
    by_column = np.pad(counts, ((0, 0), (radius, radius)), mode="constant",
                       constant_values=0)
    column_cumulative = np.concatenate(
        [np.zeros((rows, 1), np.int32), np.cumsum(by_column, axis=1, dtype=np.int32)],
        axis=1)
    columns_ok = ((column_cumulative[:, window_cells:window_cells + columns]
                   - column_cumulative[:, :columns]) == window_cells)
    return rows_ok & columns_ok


def _relief(field, mask, geometry, *, separable=False):
    """Local peak-to-trough range of the declared square window; NaN where uncovered.

    Only a cell whose whole window is resolved receives a relief value: the statistic
    is never computed over a partial neighbourhood, so an unknown is not converted into
    a small relief (which would silently make a patch look flat).
    """
    hi, lo, covered = _window_extremes(field, mask, geometry["window_cells"],
                                       separable=separable)
    relief = np.full(field.shape, np.nan, np.float64)
    with np.errstate(invalid="ignore"):
        value = hi - lo
    relief[covered] = value[covered]
    return relief, covered


def highland_relief(elevation_m, resolved_mask, *, rule=None):
    """The 300 m square local relief, NaN where the window is not fully resolved."""
    parameters = _resolve_rule(rule)
    geometry = _geometry(parameters)
    field, mask = _arrays(elevation_m, resolved_mask)
    if min(field.shape) <= geometry["window_cells"]:
        raise ValueError("%s: a %dx%d window cannot carry a %d-cell relief window"
                         % (REASON_SHAPE_MISMATCH, field.shape[0], field.shape[1],
                            geometry["window_cells"]))
    relief, covered = _relief(field, mask, geometry)
    return {
        "relief_m": relief,
        "covered": covered,
        "window_cells": geometry["window_cells"],
        "radius_m": float(parameters["relief_radius_m"]),
        "relief_unknown_cells": int((mask & ~covered).sum()),
    }


def highland_candidates(elevation_m, resolved_mask, *, rule=None):
    """Elevation gate AND relief gate: the geometric highland candidate mask.

    The elevation gate is absolute against the declared model sea level, so the same
    world cell is inside or outside the gate regardless of which window asked. Nothing
    here looks at a percentile of the current window.
    """
    parameters = _resolve_rule(rule)
    geometry = _geometry(parameters)
    field, mask = _arrays(elevation_m, resolved_mask)
    relief_report = highland_relief(field, mask, rule=parameters)
    relief = relief_report["relief_m"]
    high = mask & (field >= geometry["elevation_threshold_m"])
    steep_enough = relief >= geometry["min_relief_m"]
    candidate = high & steep_enough
    return {
        "relief_m": relief,
        "covered": relief_report["covered"],
        "elevation_candidate": high,
        "relief_candidate": steep_enough,
        "candidate": candidate,
        "relief_unknown_cells": relief_report["relief_unknown_cells"],
        "elevation_threshold_m": geometry["elevation_threshold_m"],
        "min_relief_m": geometry["min_relief_m"],
    }


# --------------------------------------------------------------------------- #
# 3. world members and the region digest
# --------------------------------------------------------------------------- #
def _world_pairs(flat, origin, columns):
    flat = np.asarray(flat, np.int64)
    x = origin[0] + (flat % columns)
    z = origin[1] + (flat // columns)
    return np.stack([x, z], axis=1).astype(np.int64, copy=False)


def member_sha256(world_xz):
    """sha256 over the world ``(x, z)`` int64 little-endian pairs, sorted by ``(x, z)``.

    This is the B-chain member serialisation (``metric_world_domains``): permuting the
    input cannot change the digest, the pair count is bound by the byte length, and no
    packed key or float coordinate ever enters it.
    """
    keys = np.ascontiguousarray(np.asarray(world_xz, np.int64).reshape(-1, 2))
    order = np.lexsort((keys[:, 1], keys[:, 0]))
    return hashlib.sha256(np.dtype("<i8").type(
        np.ascontiguousarray(keys[order], "<i8")).tobytes()).hexdigest()


def _region_id(parameters, world_sha, member_count):
    """World-anchored region identity: rule, seed, lattice and the member set only.

    The window origin, its shape, the support-local flat indices and every derived
    statistic are excluded on purpose: the same world patch keeps one id in a wider or
    narrower window, and a different member set always gets a different id.
    """
    payload = {
        "schema": "highland-source-region-v1",
        "rule_version": RULE_VERSION,
        "logical_version": LOGICAL_VERSION,
        "world_seed": DECLARED_WORLD_SEED,
        "spacing_m": DECLARED_SPACING_M,
        "parameters_sha256": _parameters_sha256(parameters),
        "member_sha256": world_sha,
        "member_count": int(member_count),
        "connectivity": "D4",
        "scope": "source_region_geometry_only",
    }
    return "hsr-" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _source_identity_sha256(parameters, region_id, member_sha, elevations):
    """Identity of the **source product** a region carries, not of the member object.

    ``region_id`` names the world member object: it stays the same while the same int64
    cells stay D4-connected under the same rule, so a support change can never renumber
    it. What the terrain under those cells *is* is a different question, and this digest
    answers it: it binds the member set to the elevation values actually stored on those
    members, in sorted world ``(x, z)`` order, plus the rule and parameter identity.

    Consequences, all intended:

    * the same world patch over the same terrain keeps one source identity in a wider or
      narrower window -- only world-anchored members and their stored values enter;
    * editing the terrain on a member changes the source identity even when the member
      set, and therefore ``region_id``, cannot change;
    * the digest of the whole support is deliberately **not** included: a support digest
      would make one world object's identity depend on how much surrounding ground a
      caller happened to load, which is exactly the instability ``region_id`` avoids.
    """
    payload = {
        "schema": "highland-source-region-source-v1",
        "rule_version": RULE_VERSION,
        "logical_version": LOGICAL_VERSION,
        "world_seed": DECLARED_WORLD_SEED,
        "spacing_m": DECLARED_SPACING_M,
        "parameters_sha256": _parameters_sha256(parameters),
        "region_id": region_id,
        "member_sha256": member_sha,
    }
    digest = hashlib.sha256(_canonical(payload).encode("utf-8"))
    values = np.ascontiguousarray(np.asarray(elevations, np.float64), dtype="<f8")
    digest.update(values.tobytes(order="C"))
    return "hsi-" + digest.hexdigest()


def _head_id(parameters, region_id, world_xz):
    """World-anchored head identity: rule, its region and its world cell.

    The observed contribution count is an **annotation**, not identity: it depends on
    how much upstream a support happened to include. Certification is a separate field
    and requires a complete upstream, so a support cannot buy identity with a wider
    window either.
    """
    payload = {
        "schema": "highland-source-head-v1",
        "rule_version": RULE_VERSION,
        "logical_version": LOGICAL_VERSION,
        "world_seed": DECLARED_WORLD_SEED,
        "spacing_m": DECLARED_SPACING_M,
        "parameters_sha256": _parameters_sha256(parameters),
        "region_id": region_id,
        "world_xz": [int(world_xz[0]), int(world_xz[1])],
        "rule": "first_known_contribution_crossing_in_qualified_patch",
    }
    return "hsh-" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 4. D4 source regions
# --------------------------------------------------------------------------- #
def _undetermined_cells(mask, covered):
    """Cells whose candidate status this support cannot decide.

    Three ways a cell can be undecided, and they must not be confused with a decided
    negative:

    * it is unresolved (the pages answered nothing there), or
    * its relief window is not fully resolved (so it has no relief and cannot be tested
      against the relief gate), or
    * it lies outside the support entirely.

    A cell that is resolved, has a known relief and simply fails the elevation or relief
    gate is a **decided** negative: a patch next to it genuinely ends there.
    """
    return ~(mask & covered)


def _ring_undetermined(members, columns, rows, undetermined):
    """How many D4 neighbours of a member set this support cannot decide.

    This is the honest completeness question for a source region: a patch is complete only
    when every cell around it was actually *decided* as a non-candidate. Cell sets alone
    cannot answer it -- a cropped window simply stops producing candidates at its relief
    margin, which would otherwise look like a smaller finished patch. A neighbour outside
    the window is counted as undecided too: the support says nothing there.
    """
    member_rows = members // columns
    member_columns = members % columns
    count = 0
    seen = set()
    for dr, dc in _D4_STEPS:
        rows_of = member_rows + dr
        columns_of = member_columns + dc
        outside = ((rows_of < 0) | (rows_of >= rows) | (columns_of < 0)
                   | (columns_of >= columns))
        count += int(outside.sum())
        inside = ~outside
        for cell in (rows_of[inside] * columns + columns_of[inside]).tolist():
            if cell in seen:
                continue
            seen.add(cell)
            count += int(undetermined[cell])
    return count


def _touches_boundary(members, columns, rows, radius):
    """Whether any member sits within the relief radius of the support boundary.

    A patch this close to the window edge asserts nothing about the ground beyond it: the
    candidate test itself is already truncated there by the relief margin (the outermost
    ``radius`` cells of a support can never carry a full window), so the region must stay
    pending. Stated as one flag rather than inferred from a count, so a reader cannot
    mistake a cropped member set for a complete region.
    """
    member_rows = members // columns
    member_columns = members % columns
    reach = int(radius) + 1
    return bool(((member_rows - reach < 0) | (member_rows + reach > rows - 1)
                 | (member_columns - reach < 0)
                 | (member_columns + reach > columns - 1)).any())


def _region_record(parameters, geometry, world, elevations, reliefs, *, touches_edge,
                   unknown_cells):
    """Shape one region record; the member set itself is decided elsewhere."""
    world_sha = member_sha256(world)
    member_count = int(world.shape[0])
    area_m2 = float(member_count) * geometry["cell_area_m2"]
    reasons = []
    if touches_edge:
        reasons.append(REASON_SUPPORT_EDGE)
    if unknown_cells:
        reasons.append(REASON_UNKNOWN_NEIGHBOUR)
    if member_count < geometry["min_region_cells"]:
        status = STATUS_REGION_BELOW_AREA
        reasons.append(REASON_REGION_BELOW_AREA)
    elif reasons:
        status = STATUS_REGION_PENDING
    else:
        status = STATUS_REGION_COMPLETE
        reasons.append(REASON_COMPLETE)
    anchor = world[int(np.lexsort((world[:, 1], world[:, 0]))[0])]
    region_id = _region_id(parameters, world_sha, member_count)
    return {
        "region_id": region_id,
        "source_identity_sha256": _source_identity_sha256(parameters, region_id, world_sha,
                                                           elevations),
        "member_count": member_count,
        "area_m2": area_m2,
        "member_sha256": world_sha,
        "status": status,
        "reason_codes": reasons,
        "min_elevation_m": float(elevations.min()),
        "max_elevation_m": float(elevations.max()),
        "min_relief_m": float(reliefs.min()),
        "touches_support_edge": bool(touches_edge),
        "unknown_neighbour_cells": int(unknown_cells),
        # A patch below the area gate or cut by the support is not an area-qualified
        # patch, so no head may be placed in it.
        "qualified": bool(member_count >= geometry["min_region_cells"]),
        "anchor_world_xz": [int(anchor[0]), int(anchor[1])],
        "head_count": 0,
    }


def _regions_by_label(candidate, mask, field, relief, origin, columns, parameters,
                      geometry, covered):
    """Vectorised (producer) D4 grouping: one ``label`` pass, then grouped index ranges."""
    labelled, count = label(candidate, structure=_D4_STRUCTURE)
    flat_labels = labelled.reshape(-1)
    index = np.full(flat_labels.size, -1, np.int64)
    undetermined = _undetermined_cells(mask, covered).reshape(-1)
    rows = candidate.shape[0]
    if count == 0:
        return ([], index.reshape(candidate.shape), np.zeros(1, np.int64),
                np.zeros((0, 2), np.int64), 0)
    order = np.argsort(flat_labels, kind="stable")
    counts = np.bincount(flat_labels, minlength=count + 1)
    pointer = np.zeros(count + 2, np.int64)
    np.cumsum(counts, out=pointer[1:])
    flat_field = field.reshape(-1)
    flat_relief = relief.reshape(-1)

    found = []
    for label_value in range(1, count + 1):
        members = order[pointer[label_value]:pointer[label_value + 1]]
        if members.size == 0:
            continue
        world = _world_pairs(members, origin, columns)
        pair_order = np.lexsort((world[:, 1], world[:, 0]))
        members = members[pair_order]
        world = world[pair_order]
        member_rows = members // columns
        member_columns = members % columns
        touches = _touches_boundary(members, columns, rows,
                                    int(geometry["radius_cells"]))
        unknown_cells = _ring_undetermined(members, columns, rows, undetermined)
        record = _region_record(parameters, geometry, world, flat_field[members],
                                flat_relief[members], touches_edge=touches,
                                unknown_cells=unknown_cells)
        record["_members"] = members
        record["_world"] = world
        found.append(record)

    # Ordered by world anchor (min z, min x): a window relabelling cannot reorder them.
    found.sort(key=lambda item: (item["anchor_world_xz"][1], item["anchor_world_xz"][0]))
    region_ptr = np.zeros(len(found) + 1, np.int64)
    for position, record in enumerate(found):
        region_ptr[position + 1] = region_ptr[position] + record["member_count"]
        index[record["_members"]] = position
    region_cells = (np.concatenate([record["_world"] for record in found])
                    if found else np.zeros((0, 2), np.int64))
    for position, record in enumerate(found):
        record.pop("_members", None)
        record.pop("_world", None)
    return found, index.reshape(candidate.shape), region_ptr, region_cells, count


def source_regions(window, *, rule=None, max_cells=DEFAULT_MAX_CELLS):
    """D4 source regions of the frozen highland rule over one declared window.

    Full table, no silent drops: a patch that misses the area gate is listed with
    ``region_below_area``, a patch touching the support edge or an unresolved D4
    neighbour is listed as ``region_candidate_pending``. An empty result is a legal
    answer (``no_candidate``), not an exception -- but it is always reported.
    """
    parameters = _resolve_rule(rule)
    geometry = _geometry(parameters)
    field, mask, origin, rows, columns = _check_window(window, parameters=parameters,
                                                       max_cells=max_cells)
    marks = highland_candidates(field, mask, rule=parameters)
    candidate = marks["candidate"]
    relief = marks["relief_m"]
    regions, index, region_ptr, region_cells, label_count = _regions_by_label(
        candidate, mask, field, relief, origin, columns, parameters, geometry,
        marks["covered"])

    qualified = [item for item in regions if item["qualified"]]
    census = {
        "support_cells": int(field.size),
        "resolved_cells": int(mask.sum()),
        "unresolved_cells": int((~mask).sum()),
        "relief_unknown_cells": int((mask & ~marks["covered"]).sum()),
        "elevation_candidate_cells": int(marks["elevation_candidate"].sum()),
        "relief_candidate_cells": int(marks["relief_candidate"].sum()),
        "candidate_cells": int(candidate.sum()),
        "label_components": int(label_count),
        "region_count": len(regions),
        "qualified_regions": len(qualified),
        "complete_regions": sum(1 for item in regions
                                if item["status"] == STATUS_REGION_COMPLETE),
        "pending_regions": sum(1 for item in regions
                               if item["status"] == STATUS_REGION_PENDING),
        "below_area_regions": sum(1 for item in regions
                                  if item["status"] == STATUS_REGION_BELOW_AREA),
        "region_member_cells": int(sum(item["member_count"] for item in regions)),
        "largest_region_cells": int(max((item["member_count"] for item in regions),
                                        default=0)),
    }
    rejects = []
    if not regions:
        rejects.append({"reason_codes": [REASON_NO_CANDIDATE],
                        "detail": "no cell passed the elevation and relief gates"})
    else:
        for item in regions:
            if item["status"] == STATUS_REGION_BELOW_AREA:
                rejects.append({"reason_codes": [REASON_REGION_BELOW_AREA],
                                "region_id": item["region_id"],
                                "anchor_world_xz": item["anchor_world_xz"],
                                "member_count": item["member_count"],
                                "area_m2": item["area_m2"],
                                "required_cells": geometry["min_region_cells"]})
            elif item["status"] == STATUS_REGION_PENDING:
                rejects.append({"reason_codes": list(item["reason_codes"]),
                                "region_id": item["region_id"],
                                "anchor_world_xz": item["anchor_world_xz"],
                                "member_count": item["member_count"],
                                "note": "pending is not a smaller certified region: the "
                                        "member set may continue outside this support"})
    return {
        "regions": regions,
        "region_index": index,
        "region_ptr": region_ptr,
        "region_cells": region_cells,
        "relief_m": relief,
        "covered": marks["covered"],
        "candidate": candidate,
        "elevation_candidate": marks["elevation_candidate"],
        "census": census,
        "rejects": rejects,
        "parameters": parameters,
        "geometry": geometry,
        "origin_native_xz": origin,
        "shape_zx": [rows, columns],
    }


# --------------------------------------------------------------------------- #
# 5. verified strict irregular-graph contribution and the first crossing
# --------------------------------------------------------------------------- #
def _module_source_sha256(name):
    """Content digest of a reused module, recorded so the dependency is observable."""
    if name not in _SOURCE_SHA_CACHE:
        module = importlib.import_module(name)
        path = getattr(module, "__file__", None)
        _SOURCE_SHA_CACHE[name] = (
            hashlib.sha256(Path(path).read_bytes()).hexdigest()
            if path and Path(path).is_file() else None)
    return _SOURCE_SHA_CACHE[name]


def _verify_receiver(receiver, field, mask, mesh):
    """A receiver must be a real irregular graph neighbour of every resolved cell.

    A jump, a self edge, an unresolved target or an index outside the window is refused,
    so an injected graph cannot make a cell drain into an arbitrary place.
    """
    shape = field.shape
    if (not isinstance(receiver, np.ndarray) or receiver.dtype != np.int64
            or receiver.shape != shape):
        raise ValueError("%s: receiver must be an int64 array of the window shape"
                         % REASON_GRAPH_INVALID)
    flat_receiver = receiver.reshape(-1)
    flat_mask = mask.reshape(-1)
    size = flat_receiver.size
    if np.any(flat_receiver[~flat_mask] != -1):
        raise ValueError("%s: an unresolved cell must have receiver -1"
                         % REASON_GRAPH_INVALID)
    live = flat_mask & (flat_receiver >= 0)
    source = np.flatnonzero(live)
    target = flat_receiver[source]
    if np.any((target < 0) | (target >= size)):
        raise ValueError("%s: receiver index outside the window" % REASON_GRAPH_INVALID)
    if np.any(source == target) or np.any(~flat_mask[target]):
        raise ValueError("%s: self receiver or unresolved receiver target"
                         % REASON_GRAPH_INVALID)
    from terrain_pipeline.drainage import receiver_edges_valid as receiver_edges_valid
    if not receiver_edges_valid(receiver, mesh):
        raise ValueError("%s: receiver must follow the masked irregular graph" % REASON_GRAPH_INVALID)
    return np.ascontiguousarray(receiver, np.int64)


def _check_routing(routing, field, mask, max_cells, origin_native_xz=(0, 0)):
    """Return verified contribution and completeness, from the one strict authority.

    The strict irregular graph of ``native_30m_source.build_strict_topology`` is **always** rebuilt
    from the field and the mask, and its ``terminal_kind`` and ``upstream_unknown_mask``
    seeds are always the ones used. Contribution counts and completeness come from
    ``metric_network_accumulation.accumulate_network_discharge`` with unit local Q, so a
    "count" is a cell count.

    ``routing`` may carry a receiver, and it is accepted only when it is
    **bit-identical** to that rebuilt strict receiver. irregular graph adjacency alone is not the
    rule: an alternative downhill graph (a different but still legal irregular graph choice at a tie,
    or a hand-built drain graph) would silently re-route the network, and -- worse -- an
    injected graph used to arrive with an all-zero seed mask, which washed every
    window-edge and hole-adjacent unknown out of the completeness propagation and
    upgraded a cell count of 556 incomplete upstream cells to "complete". A caller's
    receiver can therefore never do more than confirm the authority; counts,
    completeness and terminal labels are never taken from it.

    The accumulator is called with its own budget ceiling, so the check that refuses an
    over-budget window cannot be bypassed here.
    """
    topology = build_strict_topology(field, mask, origin_native_xz=origin_native_xz,
                                     world_seed=DECLARED_WORLD_SEED)
    receiver = topology["receiver"]
    terminal_kind = topology["terminal_kind"]
    seeds = topology["upstream_unknown_mask"]
    # The provenance is a constant *because the computation is*: the routing always comes
    # from this rebuild. Whether a caller happened to hand in the same receiver is a
    # property of the call, not of the product, so it is not recorded here -- a bundle's
    # identity must not depend on which equivalent call path produced it.
    origin = "strict_authority_rebuilt_from_field_and_mask"
    if routing is not None:
        if not isinstance(routing, dict) or "receiver" not in routing:
            raise ValueError("%s: an injected routing block carries at least a receiver"
                             % REASON_GRAPH_INVALID)
        extras = sorted(set(routing) - {"receiver"})
        if extras:
            raise ValueError("%s: an injected routing block carries only a receiver; "
                             "terminal labels, contribution counts and completeness are "
                             "recomputed by the one accumulator (refused extras %s)"
                             % (REASON_GRAPH_INVALID, extras))
        supplied = _verify_receiver(routing["receiver"], field, mask, topology["mesh"])
        if not np.array_equal(supplied, receiver):
            differing = int(np.count_nonzero(supplied.reshape(-1)
                                             != receiver.reshape(-1)))
            raise ValueError("%s: the supplied receiver is not the strict downhill irregular graph of "
                             "this field and mask (%d cells differ); an alternative "
                             "downhill graph is refused because one strict kernel is the "
                             "only routing authority" % (REASON_GRAPH_INVALID, differing))
    accumulated = accumulate_network_discharge(
        receiver, mask.astype(np.float64), mask, terminal_kind=terminal_kind,
        upstream_unknown_mask=seeds, max_cells=int(max_cells))
    routed = accumulated["known_routed_q_m3_s"]
    counts = np.rint(routed)
    if not np.array_equal(counts.astype(np.float64), routed):
        raise RuntimeError("unit local Q did not produce integral contribution counts")
    return {
        "receiver": np.ascontiguousarray(receiver, np.int64),
        "terminal_kind": terminal_kind,
        "upstream_cells": np.ascontiguousarray(counts.astype(np.int64), np.int64),
        "complete_mask": np.ascontiguousarray(accumulated["complete_mask"], np.bool_),
        "upstream_unknown_mask": np.ascontiguousarray(seeds, np.bool_),
        "origin": origin,
    }

def _donor_max_counts(receiver, mask, counts):
    """Largest contribution among a cell's donors (0 where it has none).

    ``np.maximum.at`` accumulates every duplicate, unlike a fancy-index assignment,
    which would silently keep only one donor of a confluence.
    """
    size = receiver.size
    result = np.zeros(size, np.int64)
    live = mask & (receiver >= 0)
    np.maximum.at(result, receiver[live], counts[live])
    return result


def head_candidates(window, regions, routing, *, rule=None, max_cells=DEFAULT_MAX_CELLS):
    """River-head candidates: first known-contribution crossing inside a patch.

    A head is a cell whose **known contribution first crosses** ``min_head_upstream_cells``
    -- ``count(c) >= 100`` while every donor stays below it -- and which lies inside an
    area-qualified highland patch. The crossing shape matters: picking the largest
    upstream count downstream would name a point already inside the mainstem, so the
    first crossing is used instead and the downstream continuation is left alone.

    Inside each region the survivors are de-duplicated at ``source_head_min_spacing_m``
    with a declared order: known contribution descending, then world ``(x, z)``
    ascending. The order is a rule, not a scan artefact, so permuting cells cannot change
    which heads survive. A head is ``head_geometry_certified`` only when its region is
    complete and its own upstream is complete; otherwise it stays ``head_geometry_pending``
    and is never called a certified world head.
    """
    parameters = _resolve_rule(rule)
    geometry = _geometry(parameters)
    field, mask, origin, rows, columns = _check_window(window, parameters=parameters,
                                                       max_cells=max_cells)
    if regions["origin_native_xz"] != origin or regions["shape_zx"] != [rows, columns]:
        raise ValueError("%s: the region table belongs to another window"
                         % REASON_GRAPH_INVALID)
    graph = _check_routing(routing, field, mask, max_cells, origin)
    receiver = graph["receiver"].reshape(-1)
    counts = graph["upstream_cells"].reshape(-1)
    complete = graph["complete_mask"].reshape(-1)
    flat_mask = mask.reshape(-1)
    donor_max = _donor_max_counts(receiver, flat_mask, counts)

    crossing = (flat_mask & (counts >= geometry["min_head_cells"])
                & (donor_max < geometry["min_head_cells"]))
    targets = np.flatnonzero(crossing)
    index = regions["region_index"].reshape(-1)
    records = regions["regions"]

    heads = []
    rejects = []
    if targets.size:
        world = _world_pairs(targets, origin, columns)
        region_of = index[targets]
        for position, cell in enumerate(targets):
            if region_of[position] < 0:
                rejects.append({
                    "reason_codes": [REASON_OUTSIDE_QUALIFIED_REGION],
                    "world_xz": [int(world[position, 0]), int(world[position, 1])],
                    "known_upstream_cells": int(counts[cell]),
                    "detail": "the first crossing is not inside any highland candidate "
                              "patch, so no head is declared there"})
                continue
            record = records[region_of[position]]
            if not record["qualified"]:
                rejects.append({
                    "reason_codes": [REASON_OUTSIDE_QUALIFIED_REGION,
                                     REASON_REGION_BELOW_AREA],
                    "region_id": record["region_id"],
                    "world_xz": [int(world[position, 0]), int(world[position, 1])],
                    "known_upstream_cells": int(counts[cell]),
                    "detail": "the patch is below the declared area gate"})
        keep_by_region = {}
        ordered = np.lexsort((world[:, 1], world[:, 0], -counts[targets]))
        for position in ordered:
            cell = targets[position]
            region_position = region_of[position]
            if region_position < 0 or not records[region_position]["qualified"]:
                continue
            x, z = int(world[position, 0]), int(world[position, 1])
            survivors = keep_by_region.setdefault(int(region_position), [])
            spacing_m = geometry["head_spacing_m"]
            blocked = None
            for kept in survivors:
                distance = math.hypot((x - kept[0]) * DECLARED_SPACING_M,
                                      (z - kept[1]) * DECLARED_SPACING_M)
                if distance < spacing_m:
                    blocked = (kept[0], kept[1], distance, kept[2], kept[3])
                    break
            if blocked is not None:
                # Whether a suppression is *decided* depends on the suppressor, not only
                # on the distance. The declared order is kept (contribution descending,
                # then world (x, z)), but a suppressor whose own upstream is incomplete
                # (or whose region is pending) is itself only provisional: if a wider
                # support later completes it -- or downgrades it -- this candidate may
                # come back. Calling that a decided 600 m exclusion would make the head
                # table flip when the support grows, so it is recorded as pending with
                # the blocking object named.
                decided = bool(blocked[4])
                reason = (REASON_SPACING_SUPPRESSED if decided
                          else REASON_SUPPRESSION_PENDING)
                rejects.append({
                    "reason_codes": [reason],
                    "region_id": records[region_position]["region_id"],
                    "world_xz": [x, z],
                    "known_upstream_cells": int(counts[cell]),
                    "kept_world_xz": [int(blocked[0]), int(blocked[1])],
                    "distance_m": float(blocked[2]),
                    "required_m": float(spacing_m),
                    "suppressor_complete": decided,
                    "decided": decided})
                continue
            reasons = []
            if records[region_position]["status"] != STATUS_REGION_COMPLETE:
                reasons.extend(code for code in records[region_position]["reason_codes"]
                               if code != REASON_COMPLETE)
            if not bool(complete[cell]):
                reasons.append(REASON_UPSTREAM_UNKNOWN)
            certified = not reasons
            head_id = _head_id(parameters, records[region_position]["region_id"], (x, z))
            survivors.append((x, z, head_id, certified))
            heads.append({
                "head_id": head_id,
                "region_id": records[region_position]["region_id"],
                "world_xz": [x, z],
                "known_upstream_cells": int(counts[cell]),
                "status": STATUS_HEAD_CERTIFIED if certified else STATUS_HEAD_PENDING,
                "reason_codes": [REASON_COMPLETE] if certified else reasons,
                "geometry_certified": bool(certified),
            })
    heads.sort(key=lambda item: (item["world_xz"][1], item["world_xz"][0]))
    census = {
        "crossing_cells": int(targets.size),
        "heads_declared": len(heads),
        "heads_certified": sum(1 for item in heads if item["geometry_certified"]),
        "heads_pending": sum(1 for item in heads if not item["geometry_certified"]),
        "rejected_outside_patch": sum(
            1 for item in rejects
            if REASON_OUTSIDE_QUALIFIED_REGION in item["reason_codes"]),
        "rejected_spacing": sum(1 for item in rejects
                                if REASON_SPACING_SUPPRESSED in item["reason_codes"]),
        "rejected_spacing_pending": sum(
            1 for item in rejects
            if REASON_SUPPRESSION_PENDING in item["reason_codes"]),
        "min_head_upstream_cells": geometry["min_head_cells"],
        "head_spacing_m": geometry["head_spacing_m"],
    }
    if not heads:
        rejects.append({"reason_codes": [REASON_NO_CANDIDATE],
                        "detail": "no first crossing fell inside a qualified highland "
                                  "patch; no head is invented to fill the table"})
    return {
        "heads": heads,
        "rejects": rejects,
        "census": census,
        "routing": graph,
    }

# --------------------------------------------------------------------------- #
# 6. the bundle
# --------------------------------------------------------------------------- #
def _build_metadata(window, parameters, geometry, region_census, head_census, origin,
                    max_cells):
    """Metadata bound to the real rule, the real source and the real arrays.

    The binding is explicit rather than implied: the parameter digest, the source
    records and content digest, the window origin/shape and the rule version are all
    stored, so a bundle cannot be re-labelled into another rule or another world.
    """
    field = np.ascontiguousarray(window["field"], np.float64)
    mask = np.ascontiguousarray(window["resolved_mask"], np.bool_)
    content = hashlib.sha256()
    content.update(str(tuple(field.shape)).encode("ascii"))
    content.update(field.dtype.str.encode("ascii"))
    content.update(field.tobytes(order="C"))
    content.update(mask.dtype.str.encode("ascii"))
    content.update(mask.tobytes(order="C"))
    return {
        "schema": SCHEMA,
        "rule_version": RULE_VERSION,
        "logical_version": LOGICAL_VERSION,
        "world_seed": DECLARED_WORLD_SEED,
        "spacing_m": DECLARED_SPACING_M,
        "origin_native_xz": [int(origin[0]), int(origin[1])],
        "shape_zx": [int(field.shape[0]), int(field.shape[1])],
        "max_cells": int(max_cells),
        "parameters": copy.deepcopy(parameters),
        "parameters_sha256": _parameters_sha256(parameters),
        "calibration": {key: CALIBRATION_STATUS for key in parameters},
        "geometry": dict(geometry),
        "slope_filter": DECLARED_PARAMETERS["slope_filter"],
        "source": {
            "kind": "caller_declared_window",
            "world_seed": DECLARED_WORLD_SEED,
            "spacing_m": DECLARED_SPACING_M,
            "origin_native_xz": [int(origin[0]), int(origin[1])],
            "shape_zx": [int(field.shape[0]), int(field.shape[1])],
            "assembly_digest": window.get("assembly_digest"),
            "source_records": list(window.get("source_records", [])),
            "field_mask_sha256": content.hexdigest(),
            "statement": ("the field/mask digest is a content binding recorded here; "
                          "it is not a signature and not an external page pin"),
        },
        "region_census": dict(region_census),
        "head_census": dict(head_census),
        "status": "geometry_candidates_only",
        "rainfall_supported": "rainfall_supported_pending",
        "perennial_flow_certified": False,
        "water_budget": "none",
        "mainstem_generated": False,
        "certified_world_heads": int(head_census["heads_certified"]),
        "identity_policy": (
            "region_id binds rule_version + logical_version + world_seed + spacing_m + "
            "parameters_sha256 + the world member set (sorted int64 (x,z) pairs, D4); "
            "head_id adds the world cell. Window origin, window shape, support-local "
            "flat indices, observed contribution counts and every derived statistic are "
            "excluded, so identity is support-independent while certification is not."),
        "coordinate_rule": (
            "array cell (z_index, x_index) sits at world native (x, z) = "
            "origin_native_xz + (x_index, z_index); signed int64 native cells on the "
            "30 m Terrain Diffusion lattice; metres are derived for display only and "
            "never hashed"),
        "policy": {
            "relief": ("square %dx%d window (axis radius %d cells = %.0f m); the corner "
                       "distance is larger, so it is not a disc; a cell whose window is "
                       "not fully resolved has no relief at all" % (
                           geometry["window_cells"], geometry["window_cells"],
                           geometry["radius_cells"],
                           DECLARED_SPACING_M * geometry["radius_cells"])),
            "elevation_reference": ("absolute against the declared model sea level "
                                    "%.0f m; never renormalised per window, and not a "
                                    "surveyed vertical datum"
                                    % DECLARED_PARAMETERS["model_sea_level_m"]),
            "slope": "diagnostic only: no slope hard gate in this rule version",
            "pending": ("a patch touching the support edge or an unresolved D4 "
                        "neighbour is pending; a cropped window never presents a split "
                        "patch as a complete source region"),
            "d4": ("D4 groups source-region members only. It never replaces the river "
                   "irregular graph: the strict irregular graph authority is "
                   "native_30m_source.build_strict_topology"),
            "heads": ("first known-contribution crossing at >= %d cells inside an "
                      "area-qualified patch, not the largest upstream count downstream"
                      % geometry["min_head_cells"]),
            "dedup": ("inside one region: known contribution descending, then world "
                      "(x, z) ascending, then a %.0f m minimum planar separation"
                      % geometry["head_spacing_m"]),
            "downstream": ("no mainstem is generated at this stage, so a river that has "
                           "already formed downstream is neither re-sourced in the "
                           "lowland nor broken at the patch boundary here"),
            "water": ("geometry never certifies supply: rainfall_supported stays "
                      "rainfall_supported_pending and perennial_flow_certified stays "
                      "False; a cell count is not a discharge"),
        },
        "dependency_source_sha256": {
            "terrain_pipeline.surface_rivers.native_30m_source":
                _module_source_sha256("terrain_pipeline.surface_rivers.native_30m_source"),
            'terrain_pipeline.drainage':
                _module_source_sha256(
                    'terrain_pipeline.drainage'),
        },
    }


def _head_flags(shape, heads, origin):
    """Boolean head mask, so a consumer does not have to map world back to indices."""
    flags = np.zeros(shape, np.bool_)
    for item in heads:
        x, z = item["world_xz"]
        row = int(z) - int(origin[1])
        column = int(x) - int(origin[0])
        if not (0 <= row < shape[0] and 0 <= column < shape[1]):
            raise ValueError("a head fell outside the window it was built from")
        flags[row, column] = True
    return flags


def build_highland_sources(window, *, rule=None, max_cells=DEFAULT_MAX_CELLS, graph=None):
    """One geometry bundle: regions, head candidates and the full reject table.

    ``graph`` is optional. When omitted, the verified strict irregular graph topology and the
    contribution/completeness arrays are rebuilt from the field and the mask with the
    **original** kernels. When supplied, it is verified first (irregular graph adjacency plus the
    contribution conservation identity) and refused if it does not hold, so importing a
    comparison function is never mistaken for having run it.

    Nothing here mutates its inputs: the inputs are re-read, and every stored array is
    a fresh contiguous copy, so a caller that keeps the window cannot observe a change
    and cannot alias a stored array.
    """
    parameters = _resolve_rule(rule)
    geometry = _geometry(parameters)
    field, mask, origin, rows, columns = _check_window(window, parameters=parameters,
                                                       max_cells=max_cells)
    regions = source_regions(window, rule=parameters, max_cells=max_cells)
    heads = head_candidates(window, regions, graph, rule=parameters, max_cells=max_cells)

    head_counts = {}
    for item in heads["heads"]:
        head_counts[item["region_id"]] = head_counts.get(item["region_id"], 0) + 1
    record_regions = []
    for item in regions["regions"]:
        record = {key: item[key] for key in REGION_RECORD_KEYS}
        record["head_count"] = int(head_counts.get(item["region_id"], 0))
        record_regions.append(record)

    arrays = {
        "elevation_m": np.array(field, np.float64, order="C", copy=True),
        "resolved_mask": np.array(mask, np.bool_, order="C", copy=True),
        "relief_m": np.array(regions["relief_m"], np.float64, order="C", copy=True),
        "highland_candidate": np.array(regions["candidate"], np.bool_, order="C",
                                       copy=True),
        "region_index": np.array(regions["region_index"], np.int64, order="C", copy=True),
        "region_ptr": np.array(regions["region_ptr"], np.int64, order="C", copy=True),
        "region_cells": np.array(regions["region_cells"], np.int64, order="C", copy=True),
        "head_flags": _head_flags((rows, columns), heads["heads"], origin),
        "known_upstream_cells": np.array(heads["routing"]["upstream_cells"], np.int64,
                                         order="C", copy=True),
        "upstream_complete": np.array(heads["routing"]["complete_mask"], np.bool_,
                                      order="C", copy=True),
    }
    metadata = _build_metadata(window, parameters, geometry, regions["census"],
                               heads["census"], origin, max_cells)
    metadata["routing_origin"] = heads["routing"]["origin"]
    bundle = {
        "schema": SCHEMA,
        "arrays": arrays,
        "regions": record_regions,
        "heads": [{key: item[key] for key in HEAD_RECORD_KEYS} for item in heads["heads"]],
        "rejects": list(regions["rejects"]) + list(heads["rejects"]),
        "metadata": metadata,
    }
    bundle["identity_sha256"] = identity(arrays, metadata)
    return bundle


# --------------------------------------------------------------------------- #
# 7. independent validation
# --------------------------------------------------------------------------- #
def _flood_regions(candidate, mask, field, relief, origin, columns, parameters, geometry,
                   covered):
    """Independent (validator) D4 grouping: explicit flood fill, no ``label`` call.

    Different algorithm, same declared rule. A cell set that only agreed because both
    sides shared one vectorised routine would prove nothing, so this walks the
    candidate mask with its own stack and rebuilds every member set from scratch.
    """
    rows = candidate.shape[0]
    visited = np.zeros(candidate.shape, np.bool_)
    undetermined = _undetermined_cells(mask, covered).reshape(-1)
    flat_field = field.reshape(-1)
    flat_relief = relief.reshape(-1)
    found = []
    for start_row in range(rows):
        for start_column in range(columns):
            if visited[start_row, start_column] or not candidate[start_row, start_column]:
                continue
            stack = [(start_row, start_column)]
            visited[start_row, start_column] = True
            members = []
            while stack:
                row, column = stack.pop()
                members.append(row * columns + column)
                for dr, dc in _D4_STEPS:
                    next_row = row + dr
                    next_column = column + dc
                    if (0 <= next_row < rows and 0 <= next_column < columns
                            and candidate[next_row, next_column]
                            and not visited[next_row, next_column]):
                        visited[next_row, next_column] = True
                        stack.append((next_row, next_column))
            cells = np.array(sorted(members), np.int64)
            world = _world_pairs(cells, origin, columns)
            pair_order = np.lexsort((world[:, 1], world[:, 0]))
            cells = cells[pair_order]
            world = world[pair_order]
            member_rows = cells // columns
            member_columns = cells % columns
            touches = _touches_boundary(cells, columns, rows,
                                        int(geometry["radius_cells"]))
            record = _region_record(parameters, geometry, world, flat_field[cells],
                                    flat_relief[cells], touches_edge=touches,
                                    unknown_cells=_ring_undetermined(cells, columns,
                                                                    rows,
                                                                    undetermined))
            record["_members"] = cells
            record["_world"] = world
            found.append(record)
    found.sort(key=lambda item: (item["anchor_world_xz"][1], item["anchor_world_xz"][0]))
    return found


def _heads_independently(parameters, geometry, records, index, origin, columns, mask,
                         receiver, counts, complete):
    """Rebuild the head selection with a donor CSR and a brute-force spacing filter.

    The crossing test is written from the definition -- ``count >= threshold`` and no
    donor at or above it -- using the receiver graph to collect the donors; the
    per-region order is re-sorted explicitly and the spacing test is a plain distance
    loop. Agreement therefore cannot come from sharing the producer's vectorised
    shortcuts.

    The **reject rows are rebuilt too**, in the producer's order (all refused crossings
    first, in flat order, then the spacing rows in the declared order), because a reject
    table that can be edited without being noticed is a claim nobody checks.
    """
    flat_mask = mask.reshape(-1)
    flat_counts = counts.reshape(-1)
    flat_complete = complete.reshape(-1)
    flat_receiver = receiver.reshape(-1)
    width = columns
    threshold = geometry["min_head_cells"]
    # Donor CSR: for every cell, the cells that drain into it.
    live = np.flatnonzero(flat_mask & (flat_receiver >= 0))
    targets = flat_receiver[live]
    order = np.argsort(targets, kind="stable")
    donors = live[order]
    donor_targets = targets[order]
    pointer = np.zeros(flat_counts.size + 1, np.int64)
    np.cumsum(np.bincount(donor_targets, minlength=flat_counts.size), out=pointer[1:])
    crossing = []
    outside = 0
    outside_rows = []
    for cell in np.flatnonzero(flat_mask):
        if flat_counts[cell] < threshold:
            continue
        local = donors[pointer[cell]:pointer[cell + 1]]
        if local.size and int(flat_counts[local].max()) >= threshold:
            continue
        row, column = divmod(int(cell), width)
        world_cell = [column + int(origin[0]), row + int(origin[1])]
        if index[cell] < 0:
            outside += 1
            outside_rows.append({
                "reason_codes": [REASON_OUTSIDE_QUALIFIED_REGION],
                "world_xz": world_cell,
                "known_upstream_cells": int(flat_counts[cell]),
                "detail": "the first crossing is not inside any highland candidate "
                          "patch, so no head is declared there"})
            continue
        record = records[index[cell]]
        if not record["qualified"]:
            outside += 1
            outside_rows.append({
                "reason_codes": [REASON_OUTSIDE_QUALIFIED_REGION, REASON_REGION_BELOW_AREA],
                "region_id": record["region_id"],
                "world_xz": world_cell,
                "known_upstream_cells": int(flat_counts[cell]),
                "detail": "the patch is below the declared area gate"})
            continue
        crossing.append(int(cell))
    groups = {}
    for cell in crossing:
        groups.setdefault(int(index[cell]), []).append(cell)
    heads = []
    spacing_rows = []
    suppressed = 0
    suppressed_pending = 0
    for region_position in sorted(groups):
        record = records[region_position]
        cells = np.array(groups[region_position], np.int64)
        world = _world_pairs(cells, origin, width)
        order = np.lexsort((world[:, 1], world[:, 0], -flat_counts[cells]))
        kept = []
        for position in order:
            x, z = int(world[position, 0]), int(world[position, 1])
            cell = int(cells[position])
            reasons = []
            if record["status"] != STATUS_REGION_COMPLETE:
                reasons.extend(code for code in record["reason_codes"]
                               if code != REASON_COMPLETE)
            if not bool(flat_complete[cell]):
                reasons.append(REASON_UPSTREAM_UNKNOWN)
            certified = not reasons
            blocker = None
            for kept_x, kept_z, kept_certified in kept:
                if math.hypot((x - kept_x) * DECLARED_SPACING_M,
                              (z - kept_z) * DECLARED_SPACING_M) < geometry["head_spacing_m"]:
                    blocker = bool(kept_certified)
                    break
            if blocker is not None:
                # Same asymmetry as the producer, written out here independently: only a
                # suppressor that is itself certified settles the 600 m exclusion.
                reason = (REASON_SPACING_SUPPRESSED if blocker
                          else REASON_SUPPRESSION_PENDING)
                if blocker:
                    suppressed += 1
                else:
                    suppressed_pending += 1
                spacing_rows.append({
                    "reason_codes": [reason],
                    "region_id": record["region_id"],
                    "world_xz": [x, z],
                    "known_upstream_cells": int(flat_counts[cell]),
                    "kept_world_xz": [kept_x, kept_z],
                    "distance_m": float(math.hypot((x - kept_x) * DECLARED_SPACING_M,
                                                    (z - kept_z) * DECLARED_SPACING_M)),
                    "required_m": float(geometry["head_spacing_m"]),
                    "suppressor_complete": blocker,
                    "decided": blocker})
                continue
            kept.append((x, z, certified))
            heads.append({
                "head_id": _head_id(parameters, record["region_id"], (x, z)),
                "region_id": record["region_id"],
                "world_xz": [x, z],
                "known_upstream_cells": int(flat_counts[cell]),
                "status": STATUS_HEAD_CERTIFIED if certified else STATUS_HEAD_PENDING,
                "reason_codes": [REASON_COMPLETE] if certified else reasons,
                "geometry_certified": bool(certified),
            })
    heads.sort(key=lambda item: (item["world_xz"][1], item["world_xz"][0]))
    # Independent per-region traversal still emits global candidate-priority rows.
    spacing_rows.sort(key=lambda item: (-item['known_upstream_cells'],
                                        item['world_xz'][0], item['world_xz'][1]))
    head_rejects = outside_rows + spacing_rows
    if not heads:
        head_rejects.append({"reason_codes": [REASON_NO_CANDIDATE],
                             "detail": "no first crossing fell inside a qualified highland "
                                       "patch; no head is invented to fill the table"})
    census = {
        "crossing_cells": int(len(crossing) + outside),
        "heads_declared": len(heads),
        "heads_certified": sum(1 for item in heads if item["geometry_certified"]),
        "heads_pending": sum(1 for item in heads if not item["geometry_certified"]),
        "rejected_outside_patch": outside,
        "rejected_spacing": suppressed,
        "rejected_spacing_pending": suppressed_pending,
        "min_head_upstream_cells": geometry["min_head_cells"],
        "head_spacing_m": geometry["head_spacing_m"],
    }
    return heads, census, head_rejects


def _region_reject_rows(records, geometry):
    """The region half of the reject table, rebuilt from the independent records.

    Same rows, same order as :func:`source_regions`: a below-area patch first, then a
    pending one -- the producer appends them while walking the region table in its
    canonical anchor order, so walking it again here reproduces the table exactly.
    """
    rows = []
    if not records:
        rows.append({"reason_codes": [REASON_NO_CANDIDATE],
                     "detail": "no cell passed the elevation and relief gates"})
        return rows
    for item in records:
        if item["status"] == STATUS_REGION_BELOW_AREA:
            rows.append({"reason_codes": [REASON_REGION_BELOW_AREA],
                         "region_id": item["region_id"],
                         "anchor_world_xz": item["anchor_world_xz"],
                         "member_count": item["member_count"],
                         "area_m2": item["area_m2"],
                         "required_cells": geometry["min_region_cells"]})
        elif item["status"] == STATUS_REGION_PENDING:
            rows.append({"reason_codes": list(item["reason_codes"]),
                         "region_id": item["region_id"],
                         "anchor_world_xz": item["anchor_world_xz"],
                         "member_count": item["member_count"],
                         "note": "pending is not a smaller certified region: the "
                                 "member set may continue outside this support"})
    return rows


def _check_reject_table(stored, expected):
    """Compare the whole reject table row by row, not just its length.

    A reject table is a claim: it says which candidates were refused and why. Deleting a
    row, editing a distance or relabelling a pending suppression as a decided one must
    fail here even when the bundle's own digest was re-sealed, because this comparison
    never reads the digest.
    """
    if not isinstance(stored, list):
        raise ValueError("the reject table must be a list")
    if len(stored) != len(expected):
        raise ValueError("the reject table carries %d rows; the independent re-derivation "
                         "produces %d (a deleted or invented refusal is refused)"
                         % (len(stored), len(expected)))
    for position, (row, want) in enumerate(zip(stored, expected)):
        if not isinstance(row, dict):
            raise ValueError("reject row %d is not a mapping" % position)
        if set(row) != set(want):
            raise ValueError("reject row %d carries %s; the re-derivation carries %s"
                             % (position, sorted(row), sorted(want)))
        for key in sorted(want):
            if row[key] != want[key]:
                raise ValueError("reject row %d field %r disagrees with the independent "
                                 "re-derivation (%r vs %r)"
                                 % (position, key, row[key], want[key]))


def _check_census(metadata, parameters, geometry, field, mask, rebuilt, head_census):
    """Recompute both censuses and compare field by field, rather than spot-checking."""
    qualified = [item for item in rebuilt if item["qualified"]]
    expected_regions = {
        "support_cells": int(field.size),
        "resolved_cells": int(mask.sum()),
        "unresolved_cells": int((~mask).sum()),
        "region_count": len(rebuilt),
        "qualified_regions": len(qualified),
        "complete_regions": sum(1 for item in rebuilt
                                if item["status"] == STATUS_REGION_COMPLETE),
        "pending_regions": sum(1 for item in rebuilt
                               if item["status"] == STATUS_REGION_PENDING),
        "below_area_regions": sum(1 for item in rebuilt
                                  if item["status"] == STATUS_REGION_BELOW_AREA),
        "region_member_cells": int(sum(item["member_count"] for item in rebuilt)),
        "largest_region_cells": int(max((item["member_count"] for item in rebuilt),
                                        default=0)),
    }
    stored_regions = metadata.get("region_census")
    if not isinstance(stored_regions, dict):
        raise ValueError("metadata region_census must be a mapping")
    for key, value in sorted(expected_regions.items()):
        if _strict_int(stored_regions.get(key), "region_census.%s" % key) != value:
            raise ValueError("region_census %r disagrees with the independent count "
                             "(%r vs %r)" % (key, stored_regions.get(key), value))
    for key in ("relief_unknown_cells", "elevation_candidate_cells",
                "relief_candidate_cells", "candidate_cells", "label_components"):
        stored_value = _strict_int(stored_regions.get(key), "region_census.%s" % key)
        if stored_value < 0:
            raise ValueError("region_census %r is negative" % key)
    stored_heads = metadata.get("head_census")
    if not isinstance(stored_heads, dict):
        raise ValueError("metadata head_census must be a mapping")
    for key in ("heads_declared", "heads_certified", "heads_pending",
                "rejected_outside_patch", "rejected_spacing",
                "rejected_spacing_pending", "crossing_cells"):
        if _strict_int(stored_heads.get(key), "head_census.%s" % key) != int(
                head_census[key]):
            raise ValueError("head_census %r disagrees with the independent count "
                             "(%r vs %r)" % (key, stored_heads.get(key),
                                              head_census[key]))
    if _strict_int(stored_heads.get("min_head_upstream_cells"),
                   "head_census.min_head_upstream_cells") != geometry["min_head_cells"]:
        raise ValueError("head_census min_head_upstream_cells disagrees with the frozen rule")
    if _strict_float(stored_heads.get("head_spacing_m"),
                     "head_census.head_spacing_m") != geometry["head_spacing_m"]:
        raise ValueError("head_census head_spacing_m disagrees with the frozen rule")
    if _strict_int(metadata.get("certified_world_heads"), "certified_world_heads") != int(
            head_census["heads_certified"]):
        raise ValueError("certified_world_heads disagrees with the independent certified "
                         "head count")
    if metadata.get("status") != "geometry_candidates_only":
        raise ValueError("metadata status %r is not the geometry-only stage"
                         % (metadata.get("status"),))
    del parameters


def _check_identity(bundle, field, mask):
    """Recompute the bundle digest from its own payload and refuse any mismatch.

    The digest covers ``arrays`` and ``metadata`` only, which is exactly why the record
    tables above are re-derived independently instead of trusted: a re-sealed digest can
    cover a forged table, so both checks are needed and neither substitutes for the other.
    """
    stored = bundle.get("identity_sha256")
    if not isinstance(stored, str) or len(stored) != 64:
        raise ValueError("identity_sha256 must be a 64-character digest, got %r"
                         % (stored,))
    expected = identity(bundle["arrays"], bundle["metadata"])
    if stored != expected:
        raise ValueError("the identity_sha256 digest does not cover this bundle: the "
                         "arrays or the metadata were edited after it was sealed "
                         "(%s vs %s)" % (stored, expected))
    source = bundle["metadata"].get("source")
    if not isinstance(source, dict):
        raise ValueError("metadata source must be a mapping")
    content = hashlib.sha256()
    content.update(str(tuple(field.shape)).encode("ascii"))
    content.update(field.dtype.str.encode("ascii"))
    content.update(field.tobytes(order="C"))
    content.update(mask.dtype.str.encode("ascii"))
    content.update(mask.tobytes(order="C"))
    if source.get("field_mask_sha256") != content.hexdigest():
        raise ValueError("metadata source field_mask_sha256 does not describe the stored "
                         "elevation and mask")
    if list(source.get("origin_native_xz", [])) != list(
            bundle["metadata"]["origin_native_xz"]):
        raise ValueError("metadata source origin disagrees with the bundle origin")
    if list(source.get("shape_zx", [])) != list(bundle["metadata"]["shape_zx"]):
        raise ValueError("metadata source shape disagrees with the bundle shape")


def _check_stored_arrays(arrays, field, mask, relief, covered, candidate, geometry):
    """Compare the derived full-extent arrays against the independent re-derivation."""
    stored_relief = arrays["relief_m"]
    if not np.array_equal(np.isnan(stored_relief), ~covered):
        raise ValueError("array 'relief_m' must be NaN exactly where the relief window is "
                         "not fully resolved")
    if not np.array_equal(stored_relief[covered], relief[covered]):
        raise ValueError("array 'relief_m' disagrees with the independent square-window "
                         "re-derivation")
    if not np.array_equal(arrays["highland_candidate"], candidate):
        raise ValueError("array 'highland_candidate' disagrees with the declared elevation "
                         "and relief gates")
    if not np.array_equal(arrays["resolved_mask"], mask):
        raise ValueError("array 'resolved_mask' disagrees with itself")
    if not np.array_equal(np.isnan(arrays["elevation_m"]), ~mask):
        raise ValueError("array 'elevation_m' must keep NaN exactly on unresolved cells")
    if not np.array_equal(arrays["elevation_m"][mask], field[mask]):
        raise ValueError("array 'elevation_m' disagrees with itself")
    del geometry


def validate_highland_sources(bundle, *, window=None):
    """Re-derive every claim from the stored elevation, mask and declared rule.

    Independence is the point: the relief window is re-applied with separable 1-D
    passes, the D4 members with an explicit flood fill, the first crossing with a direct
    per-cell donor check, and the 600 m de-duplication with a brute-force distance loop.
    Re-sealing the metadata after editing a derived array, a member set, an area, a head
    or a status therefore cannot pass. Source re-authentication (page pins) is **not**
    attempted: a checksum is not a signature and no page is read here.

    The routing step is **always** re-derived, never skipped. The strict irregular graph topology is
    rebuilt from the stored ``elevation_m`` and ``resolved_mask`` with the one strict
    kernel (the same budget as the producer permits it), then contribution and
    completeness are recomputed by the one accumulator. A validator that accepted a
    bundle on the strength of its own re-sealed arrays and a *forged* head count was a
    hole, not a convenience: the head table is part of what a bundle claims.

    ``window`` is therefore optional and may only carry a receiver, which is accepted
    when it is bit-identical to that rebuilt strict receiver (an alternative downhill
    graph is refused). It is a cross-check for a caller holding the assembled pages, not
    a substitute for the rebuild.
    """
    if not isinstance(bundle, dict) or set(bundle) != BUNDLE_KEYS:
        raise ValueError("a highland bundle is exactly %s" % (sorted(BUNDLE_KEYS),))
    if bundle["schema"] != SCHEMA:
        raise ValueError("unexpected bundle schema %r" % (bundle["schema"],))
    metadata = bundle["metadata"]
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a mapping")
    if metadata.get("rule_version") != RULE_VERSION:
        raise ValueError("metadata rule_version %r is not %r"
                         % (metadata.get("rule_version"), RULE_VERSION))
    parameters = _normalise_parameters(metadata.get("parameters"))
    geometry = _geometry(parameters)
    if _parameters_sha256(parameters) != metadata.get("parameters_sha256"):
        raise ValueError("parameters_sha256 does not match the declared parameters")
    if _strict_int(metadata.get("world_seed"), "world_seed") != DECLARED_WORLD_SEED:
        raise ValueError("%s: metadata world_seed is not the frozen seed"
                         % REASON_SEED_MISMATCH)
    if _strict_float(metadata.get("spacing_m"), "spacing_m") != DECLARED_SPACING_M:
        raise ValueError("%s: metadata spacing_m is not the native lattice"
                         % REASON_SPACING_MISMATCH)
    # Supply and stage claims cannot be upgraded by editing a bundle.
    if metadata.get("rainfall_supported") != "rainfall_supported_pending":
        raise ValueError("geometry cannot certify supply: rainfall_supported must stay "
                         "'rainfall_supported_pending'")
    if metadata.get("perennial_flow_certified") is not False:
        raise ValueError("geometry cannot certify a perennial flow")
    if metadata.get("mainstem_generated") is not False:
        raise ValueError("this stage emits heads only; a mainstem claim is refused")
    # A bundle records the budget it was actually computed under. That budget may be any
    # legal value up to the declared P2 ceiling (a smaller caller budget is legitimate and
    # must not be mistaken for a non-default bundle), so it is checked against the ceiling
    # rather than against the constant.
    bundle_budget = _strict_int(metadata.get("max_cells"), "max_cells")
    if not 1 <= bundle_budget <= DEFAULT_MAX_CELLS:
        raise ValueError("%s: metadata max_cells=%d is outside the declared P2 budget of %d"
                         % (REASON_BUDGET, bundle_budget, DEFAULT_MAX_CELLS))
    calibration = metadata.get("calibration")
    if not isinstance(calibration, dict) or set(calibration) != set(parameters):
        raise ValueError("calibration status must cover every declared parameter")
    if set(calibration.values()) != {CALIBRATION_STATUS}:
        raise ValueError("every declared parameter must stay %r" % CALIBRATION_STATUS)

    arrays = bundle["arrays"]
    if not isinstance(arrays, dict) or set(arrays) != set(ARRAY_NAMES):
        raise ValueError("the bundle arrays must be exactly %s" % (list(ARRAY_NAMES),))
    expected_dtypes = {
        "elevation_m": np.dtype(np.float64),
        "resolved_mask": np.dtype(np.bool_),
        "relief_m": np.dtype(np.float64),
        "highland_candidate": np.dtype(np.bool_),
        "region_index": np.dtype(np.int64),
        "region_ptr": np.dtype(np.int64),
        "region_cells": np.dtype(np.int64),
        "head_flags": np.dtype(np.bool_),
        "known_upstream_cells": np.dtype(np.int64),
        "upstream_complete": np.dtype(np.bool_),
    }
    for name, dtype in expected_dtypes.items():
        value = arrays[name]
        if not isinstance(value, np.ndarray) or value.dtype != dtype:
            raise ValueError("array %r must have dtype %s" % (name, dtype.str))
    field = arrays["elevation_m"]
    mask = arrays["resolved_mask"]
    shape = list(field.shape)
    if int(field.size) > bundle_budget:
        raise ValueError("%s: the stored window has %d cells but the bundle declares "
                         "max_cells=%d" % (REASON_BUDGET, int(field.size), bundle_budget))
    if _int_pair(metadata["shape_zx"], "shape_zx") != shape:
        raise ValueError("%s: metadata shape disagrees with the stored elevation"
                         % REASON_SHAPE_MISMATCH)
    origin = _int_pair(metadata["origin_native_xz"], "origin_native_xz")
    declared_window = {
        "field": field,
        "resolved_mask": mask,
        "origin_native_xz": origin,
        "shape_zx": shape,
        "world_seed": metadata["world_seed"],
        "spacing_m": metadata["spacing_m"],
    }
    _check_window(declared_window, parameters=parameters, max_cells=DEFAULT_MAX_CELLS)

    relief, covered = _relief(field, mask, geometry, separable=True)
    high = mask & (field >= geometry["elevation_threshold_m"])
    steep = np.where(covered, relief, -np.inf) >= geometry["min_relief_m"]
    candidate = high & steep
    _check_stored_arrays(arrays, field, mask, relief, covered, candidate, geometry)

    rebuilt = _flood_regions(candidate, mask, field, relief, origin, shape[1],
                             parameters, geometry, covered)
    stored_regions = bundle["regions"]
    if not isinstance(stored_regions, list) or len(stored_regions) != len(rebuilt):
        raise ValueError("the stored region table does not carry %d regions; a split or "
                         "merged member set is refused" % len(rebuilt))
    index = np.full(field.size, -1, np.int64)
    pointer = np.zeros(len(rebuilt) + 1, np.int64)
    cells_out = []
    regions = []
    for position, (stored, independent) in enumerate(zip(stored_regions, rebuilt)):
        if not isinstance(stored, dict) or set(stored) != set(REGION_RECORD_KEYS):
            raise ValueError("region records carry exactly %s"
                             % (list(REGION_RECORD_KEYS),))
        for key in REGION_RECORD_KEYS:
            if key == "head_count":
                continue
            if stored[key] != independent[key]:
                raise ValueError("region %d field %r disagrees with the independent "
                                 "re-derivation (%r vs %r)"
                                 % (position, key, stored[key], independent[key]))
        member_count = int(stored["member_count"])
        if abs(float(stored["area_m2"])
               - member_count * DECLARED_SPACING_M * DECLARED_SPACING_M) > 1e-6:
            raise ValueError("region %d area_m2 disagrees with its member count at 30 m"
                             % position)
        if bool(stored["qualified"]) != (member_count >= geometry["min_region_cells"]):
            raise ValueError("region %d qualified flag disagrees with the area gate"
                             % position)
        index[independent["_members"]] = position
        pointer[position + 1] = pointer[position] + member_count
        cells_out.append(independent["_world"])
        regions.append(independent)
    expected_cells = (np.concatenate(cells_out) if cells_out
                      else np.zeros((0, 2), np.int64))
    if not np.array_equal(arrays["region_index"], index.reshape(shape)):
        raise ValueError("array 'region_index' disagrees with the independent member sets")
    if not np.array_equal(arrays["region_ptr"], pointer):
        raise ValueError("array 'region_ptr' disagrees with the independent region sizes")
    if not np.array_equal(arrays["region_cells"], expected_cells):
        raise ValueError("array 'region_cells' disagrees with the independent member sets: "
                         "world members are identity, so a support-local index may not "
                         "stand in for them")

    counts = arrays["known_upstream_cells"]
    complete = arrays["upstream_complete"]
    if counts.shape != tuple(shape) or complete.shape != tuple(shape):
        raise ValueError("the contribution arrays must have the window shape")
    if np.any(counts[mask] < 1) or np.any(counts[~mask] != 0):
        raise ValueError("known_upstream_cells must be a positive cell count on resolved "
                         "cells and zero elsewhere")
    if np.any(complete[~mask]):
        raise ValueError("an unresolved cell cannot be upstream-complete")

    stored_heads = bundle["heads"]
    if not isinstance(stored_heads, list):
        raise ValueError("the head table must be a list")
    for position, item in enumerate(stored_heads):
        if not isinstance(item, dict) or set(item) != set(HEAD_RECORD_KEYS):
            raise ValueError("head records carry exactly %s" % (list(HEAD_RECORD_KEYS),))
    flags = arrays["head_flags"]
    expected_flags = _head_flags(tuple(shape), stored_heads, origin)
    if not np.array_equal(flags, expected_flags):
        raise ValueError("array 'head_flags' disagrees with the stored head table")

    report = {
        "schema": "metric-highland-sources-validation-v1",
        "regions_rederived": len(rebuilt),
        "heads_stored": len(stored_heads),
        "head_table_rederived": True,
        "region_census": dict(metadata.get("region_census", {})),
        "head_census": dict(metadata.get("head_census", {})),
    }
    # The routing step runs unconditionally: the strict irregular graph is rebuilt from the stored
    # elevation and mask, so a bundle cannot carry a forged count table, a hand-cleared
    # completeness mask or an invented head past this point.
    supplied_receiver = None
    if window is not None:
        if not isinstance(window, dict):
            raise ValueError("%s: the window argument is a mapping carrying a receiver"
                             % REASON_GRAPH_INVALID)
        extras_forbidden = sorted((set(window) & set(FORBIDDEN_WINDOW_KEYS))
                                 - {"receiver"})
        if extras_forbidden:
            raise ValueError("%s: a window may not carry stored routing results (%s)"
                             % (REASON_GRAPH_INVALID, extras_forbidden))
        extras = sorted(set(window) - {"receiver"})
        if extras:
            raise ValueError("%s: the window argument carries at most a receiver for "
                             "cross-checking (refused %s); the topology is rebuilt "
                             "from the stored elevation and mask"
                             % (REASON_GRAPH_INVALID, extras))
        supplied_receiver = window.get("receiver")
    routing = (None if supplied_receiver is None
               else {"receiver": supplied_receiver})
    graph = _check_routing(routing, field, mask, DEFAULT_MAX_CELLS, origin)
    if not np.array_equal(graph["upstream_cells"], counts):
        raise ValueError("array 'known_upstream_cells' disagrees with the accumulator "
                         "re-run over the rebuilt strict receiver")
    if not np.array_equal(graph["complete_mask"], complete):
        raise ValueError("array 'upstream_complete' disagrees with the accumulator "
                         "re-run over the rebuilt strict receiver")
    rebuilt_heads, census, head_rejects = _heads_independently(
        parameters, geometry, regions, index, origin, shape[1], mask,
        graph["receiver"], graph["upstream_cells"], graph["complete_mask"])
    if rebuilt_heads != stored_heads:
        raise ValueError("the head table disagrees with the independent re-derivation: "
                         "heads %r vs %r"
                         % ([item["world_xz"] for item in rebuilt_heads],
                            [item["world_xz"] for item in stored_heads]))
    _check_reject_table(bundle["rejects"], _region_reject_rows(regions, geometry)
                        + head_rejects)
    _check_census(metadata, parameters, geometry, field, mask, rebuilt, census)
    _check_identity(bundle, field, mask)
    report["routing_origin"] = graph["origin"]
    report["head_census_independent"] = census
    return report
