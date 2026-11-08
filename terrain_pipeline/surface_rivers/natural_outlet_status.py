"""One outlet-state vocabulary, and a conservative river-to-sea outlet gate.

Why this module exists
----------------------
The repository answers "where does this water end" in five disjoint vocabularies
and none of them can express *both* "interior terminal of a finite graph" and
"certified natural outlet":

* ``native_30m_source._EMITTABLE_TERMINALS`` =
  ``(inactive, interior, retained, unknown_boundary)`` -- ``open_outflow`` is
  never emitted, and ``retained`` is documented as "an interior terminal of this
  finite graph. Not a natural lake, not an outlet";
* ``metric_network_accumulation`` accepts ``open_outflow`` but never decides it;
* ``metric_depression_gate`` answers ``lake`` / ``pass_through``, with
  ``truncated_not_judged`` as a *flag*, not a verdict;
* ``metric_cross_region`` refuses with ``out_of_tile`` / ``unresolved_border`` /
  ``overlapping_disagreement`` / ``ocean`` / ``closed_basin``;
* ``natural_outlet_certification`` produces two booleans, not a graph label.

A consumer that is handed a ``retained`` terminal therefore has no honest way to
say "this is not an outlet, and here is the reason". This module is that
vocabulary plus the gate that decides when a claim may be upgraded.

The seven states, kept strictly apart
------------------------------------
``lake``                       a depression the gate judged a real water body.
``natural_outlet``             **certified** river-to-sea outlet. Only this module
                              may assign it, and only with all six evidence gates.
``retained``                   interior terminal of a finite graph. Not a lake,
                              not an outlet, not hydrologically closed.
``open_outflow``               an externally declared *open* outflow boundary:
                              water leaves here instead of ponding. The 30 m
                              source stage never emits it; declaring one is
                              evidence about a boundary, and it is the **only**
                              graph label a certification may be built on.
``unknown_boundary``           the downstream continuation left the window or met
                              unresolved support. Declared, never repaired.
``truncated_not_judged``       the depression/outlet judgement was refused because
                              the feature sat inside the untrusted border band.
``artificial_window_boundary`` a window or engineering cut. A cell on it is a
                              boundary of *this run*, not a feature of the world.

``unverified_outlet_candidate`` is deliberately **not** one of the seven: it is a
claim of ``natural_outlet`` that failed at least one gate. It exists so a failed
claim cannot be silently reported as any of the six legitimate states.

Six evidence gates, all required
-------------------------------
``continuous_downstream_coverage``
    An explicit observed path from the terminal to a coastline cell: contiguous,
    inside resolved coverage, non-increasing in bed height, endpoints exact, and
    not re-entering the terminal's own catchment. The receiver graph ends at the
    terminal (its ``receiver`` is ``-1``), so the continuation to the sea can
    only be *evidence*; requiring the receiver chain itself to reach the coast is
    what made the older raster gate refuse every multi-cell river mouth.
``not_artificial_boundary``
    The terminal's graph label is ``open_outflow``; no path cell, the coastline
    cell or the terminal lies on an artificial window edge or a declared
    engineering boundary. ``retained`` is refused unconditionally: a strictly
    downhill receiver graph says the water *stops* at a ``retained`` cell, so
    calling it a mouth would contradict the graph the certificate is built on.
    ``unknown_boundary`` is refused for the opposite reason: its continuation is
    outside this run's coverage.
``no_unknown_pollution``
    No path cell and no contributing (upstream) cell of the terminal is
    unresolved or upstream-unknown. A certified outlet must not be fed by a
    catchment whose boundary was cut. The unknown set is the caller's declared
    mask **unioned** with the set this module derives from the resolved mask (a
    resolved cell with incomplete bounded irregular graph support), so declaring an
    empty mask cannot hide a window cut.
``world_coordinate_source_pin``
    Fixed world seed, 30 m spacing, an integer native origin, every source page
    SHA256-pinned, and the declared outlet world coordinate reproducible from the
    native index lattice. No inferred coordinates.
``water_quantity_evidence``
    A finite positive discharge with named provenance and independent
    observation. A dry mouth is not an outlet.
``water_level_evidence``
    A declared vertical datum with a finite uncertainty, and a water surface at
    the outlet at or below the declared sea level *within that uncertainty*.

Failure is reported, never repaired: a refused claim keeps every reason code and
never becomes any of the six legitimate states.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

import numpy as np

__all__ = [
    "ARTIFICIAL_WINDOW_BOUNDARY",
    "CANDIDATE_STATE",
    "EXPECTED_WORLD_SEED",
    "GATE_NAMES",
    "GRAPH_TERMINAL_LABELS",
    "LAKE",
    "NATURAL_OUTLET",
    "NATIVE_SPACING_M",
    "OPEN_OUTFLOW",
    "REASON_CODES",
    "REQUIRED_STATES",
    "RETAINED",
    "SCHEMA",
    "TERMINAL_STATE",
    "TRUNCATED_NOT_JUDGED",
    "UNKNOWN_BOUNDARY",
    "certify_natural_outlet",
    "state_of_terminal_kind",
    "validate_report",
]


SCHEMA = "native-30m-natural-outlet-status-v2"

#: The fixed continuous test baseline (``CONTRIBUTING.md``): never re-chosen.
EXPECTED_WORLD_SEED = 20261020

#: Terrain Diffusion native resolution; a scale knob would be a different world.
NATIVE_SPACING_M = 30.0

LAKE = "lake"
NATURAL_OUTLET = "natural_outlet"
RETAINED = "retained"
OPEN_OUTFLOW = "open_outflow"
UNKNOWN_BOUNDARY = "unknown_boundary"
TRUNCATED_NOT_JUDGED = "truncated_not_judged"
ARTIFICIAL_WINDOW_BOUNDARY = "artificial_window_boundary"

#: The states a consumer must be able to tell apart, and nothing else.
REQUIRED_STATES = (LAKE, NATURAL_OUTLET, RETAINED, OPEN_OUTFLOW,
                   UNKNOWN_BOUNDARY, TRUNCATED_NOT_JUDGED,
                   ARTIFICIAL_WINDOW_BOUNDARY)

#: A claim that failed a gate. Not a state of the world.
CANDIDATE_STATE = "unverified_outlet_candidate"

#: The five words ``metric_network_discharge_product.TERMINAL_LABELS`` uses. Held
#: locally so this module imports no product; a test pins the two lists equal.
GRAPH_TERMINAL_LABELS = ("inactive", "interior", "retained", "open_outflow",
                         "unknown_boundary")

#: Graph label -> outlet state. ``open_outflow`` maps to itself and is *not* a
#: certification; nothing here upgrades a graph label on its own.
TERMINAL_STATE = {RETAINED: RETAINED, OPEN_OUTFLOW: OPEN_OUTFLOW,
                  UNKNOWN_BOUNDARY: UNKNOWN_BOUNDARY}

GATE_NAMES = ("continuous_downstream_coverage",
              "not_artificial_boundary",
              "no_unknown_pollution",
              "world_coordinate_source_pin",
              "water_quantity_evidence",
              "water_level_evidence")

REASON_CODES = frozenset({
    # gate: continuous_downstream_coverage
    "missing_continuous_downstream_coverage",
    "path_not_contiguous",
    "path_endpoints_mismatch",
    "path_crosses_unresolved",
    "path_is_not_downhill",
    "path_reenters_catchment",
    "terminal_is_not_receiver_exit",
    "endpoint_not_explicit_coastline",
    # gate: not_artificial_boundary
    "path_crosses_artificial_boundary",
    "terminal_on_artificial_boundary",
    "graph_label_is_not_an_open_outflow",
    "terminal_is_unknown_boundary",
    "declared_artificial_window_boundary_is_not_a_natural_outlet",
    # gate: no_unknown_pollution
    "unknown_pollution_on_path",
    "unknown_pollution_in_upstream_catchment",
    # gate: world_coordinate_source_pin
    "missing_world_coordinate_source_pin",
    "world_coordinate_source_pin_mismatch",
    "world_coordinate_mismatch",
    # gate: water_quantity_evidence
    "missing_water_quantity_evidence",
    "zero_or_negative_discharge",
    "discharge_provenance_unstated",
    "discharge_not_independently_observed",
    # gate: water_level_evidence
    "missing_water_level_evidence",
    "outlet_bed_above_declared_sea_level",
    "water_surface_above_declared_sea_level",
    "water_surface_below_outlet_bed",
    # declaration-level refusals: a label is never a certification
    "declared_retained_is_not_a_natural_outlet",
    "declared_open_outflow_is_not_a_natural_outlet",
    "declared_unknown_boundary_is_not_a_natural_outlet",
    "declared_truncated_not_judged_blocks_certification",
    "declared_lake_is_not_a_natural_outlet",
})

_DECLARED_REFUSAL = {
    RETAINED: "declared_retained_is_not_a_natural_outlet",
    OPEN_OUTFLOW: "declared_open_outflow_is_not_a_natural_outlet",
    UNKNOWN_BOUNDARY: "declared_unknown_boundary_is_not_a_natural_outlet",
    TRUNCATED_NOT_JUDGED: "declared_truncated_not_judged_blocks_certification",
    ARTIFICIAL_WINDOW_BOUNDARY:
        "declared_artificial_window_boundary_is_not_a_natural_outlet",
    LAKE: "declared_lake_is_not_a_natural_outlet",
}

_SHA256 = re.compile(r"[0-9a-f]{64}")




# --------------------------------------------------------------------------- #
# scalar and array validation
# --------------------------------------------------------------------------- #
def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _integer(value: Any, name: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("%s must be an integer, not a boolean" % name)
    if isinstance(value, (int, np.integer)):
        return int(value)
    raise ValueError("%s must be an integer, got %s" % (name, type(value).__name__))


def _number(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or isinstance(value, (str, bytes)):
        raise ValueError("%s must be a real number, got %r" % (name, value))
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError("%s must be a real number, got %r" % (name, value)) from None
    if not math.isfinite(result):
        raise ValueError("%s must be finite, got %r" % (name, result))
    return result


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError("%s must be a boolean, got %r" % (name, value))
    return bool(value)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("%s must be a non-empty string" % name)
    return value


def _mapping(value: Any, name: str, keys: frozenset) -> dict:
    if not isinstance(value, dict):
        raise ValueError("%s must be a dictionary" % name)
    if set(value) != keys:
        raise ValueError("%s must carry exactly %s, got %s"
                         % (name, sorted(keys), sorted(value)))
    return dict(value)


def _field_block(value: Any, name: str, fields: int,
                 allow_empty: bool = False) -> np.ndarray:
    """Coerce to an array of the declared rank; emptiness is a refusal by default."""
    text = str(name)
    if isinstance(value, np.ndarray):
        item = value
    elif isinstance(value, (list, tuple)):
        item = np.asarray(value)
    else:
        raise ValueError("%s must be an array" % text)
    if item.ndim != fields:
        raise ValueError("%s must be %d-dimensional, got %d"
                         % (text, fields, item.ndim))
    if not allow_empty and any(size == 0 for size in item.shape):
        raise ValueError("%s must be non-empty" % text)
    return item


def _receiver_and_bed(graph: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Validated ``(receiver, height, valid, kinds)`` of one finite 30 m graph."""
    record = _mapping(graph, "graph", frozenset({"receiver", "height_m", "valid_mask",
                                                 "terminal_kind"}))
    receiver = _field_block(record["receiver"], "graph.receiver", 2)
    if receiver.dtype.kind not in "iu":
        raise ValueError("graph.receiver must be an integer array")
    receiver = receiver.astype(np.int64, copy=False)
    height = _field_block(record["height_m"], "graph.height_m", 2).astype(np.float64,
                                                                          copy=False)
    valid = _field_block(record["valid_mask"], "graph.valid_mask", 2)
    if valid.dtype != np.bool_:
        raise ValueError("graph.valid_mask must be a boolean array")
    kinds = _field_block(record["terminal_kind"], "graph.terminal_kind", 2)
    if kinds.dtype.kind != "U":
        raise ValueError("graph.terminal_kind must be a unicode array")
    if not (receiver.shape == height.shape == valid.shape == kinds.shape):
        raise ValueError("graph arrays must share one 2D shape")
    if not valid.any():
        raise ValueError("graph.valid_mask must contain at least one cell")
    if not np.isfinite(height[valid]).all():
        raise ValueError("resolved cells must carry finite bed heights")
    if np.any(receiver[~valid] != -1):
        raise ValueError("an unresolved cell carries no receiver")
    if np.any((receiver < -1) | (receiver >= receiver.size)):
        raise ValueError("a receiver index lies outside the grid")
    if not np.isin(kinds[valid], GRAPH_TERMINAL_LABELS).all():
        raise ValueError("graph.terminal_kind carries an unknown label")
    live = valid & (receiver >= 0)
    flat_receiver = receiver.reshape(-1)
    flat_height = height.reshape(-1)
    flat_valid = valid.reshape(-1)
    sources = np.flatnonzero(live)
    targets = flat_receiver[sources]
    if targets.size:
        if np.any(~flat_valid[targets]):
            raise ValueError("a receiver target must itself be a resolved cell")
        if np.any(flat_height[targets] >= flat_height[sources]):
            raise ValueError("the receiver graph must be strictly downhill, so its "
                             "chains are acyclic and every terminal is a real minimum")
    if np.any(kinds[live] != "interior"):
        raise ValueError("a cell with a receiver must be labelled interior")
    return receiver, height, valid, kinds


def _terminal_labels(receiver: np.ndarray, height: np.ndarray,
                     valid: np.ndarray) -> np.ndarray:
    """Flat index of the terminal each cell drains to, by ascending bed height.

    Ascending order guarantees ``labels[receiver[i]]`` is final when ``i`` is
    processed, because the receiver is strictly lower (validated above).
    """
    flat_receiver = receiver.reshape(-1)
    flat_height = height.reshape(-1)
    flat_valid = valid.reshape(-1)
    live = np.flatnonzero(flat_valid)
    labels = np.full(flat_height.size, -1, np.int64)
    for position in live[np.argsort(flat_height[live], kind="stable")]:
        downstream = int(flat_receiver[position])
        labels[position] = int(position) if downstream < 0 else labels[downstream]
    return labels.reshape(height.shape)


def state_of_terminal_kind(kind: str) -> str:
    """State of one graph terminal label: ``retained`` is never an outlet."""
    if not isinstance(kind, str):
        raise ValueError("a terminal kind must be a string")
    if kind in TERMINAL_STATE:
        return TERMINAL_STATE[kind]
    raise ValueError("%r is not a terminal label: a cell that carries a receiver is "
                     "'interior', and 'inactive' is not a state of the world" % (kind,))


def derived_unknown_mask(valid_mask, *, origin_native_xz=(0, 0), spacing_m=30.,
                         world_seed=20261020) -> np.ndarray:
    """Cells whose upstream is undeclared because a neighbour is unresolved.

    A resolved cell with incomplete bounded irregular graph support has lost a
    potential donor to the window cut, so its inflow from outside this run is
    undeclared -- exactly the seed ``native_30m_source.build_strict_topology``
    declares. Recomputed here rather than taken on trust, so an empty caller mask
    cannot claim a clean catchment that the resolved mask contradicts.
    """
    valid = np.asarray(valid_mask)
    if valid.ndim != 2 or valid.dtype != np.bool_:
        raise ValueError("derived_unknown_mask needs a 2D boolean resolved mask")
    from terrain_pipeline.drainage import graph_support_unknown as graph_support_unknown
    return graph_support_unknown(valid,
        x0_m=origin_native_xz[0] * spacing_m, z0_m=origin_native_xz[1] * spacing_m,
        dx_m=spacing_m, world_seed=world_seed)

# --------------------------------------------------------------------------- #
# the gate
# --------------------------------------------------------------------------- #
def certify_natural_outlet(*, candidate: dict, graph: dict, downstream: dict,
                           masks: dict, source_pin: dict, water_quantity: dict,
                           water_level: dict,
                           expected_world_seed: int = EXPECTED_WORLD_SEED,
                           expected_spacing_m: float = NATIVE_SPACING_M) -> dict:
    """Decide whether one terminal may be called a certified natural outlet.

    Every input is explicit evidence. Nothing is inferred: no coastline is derived
    from nodata, no outlet from a window edge, no discharge from a receiver count,
    no sea level from the minimum bed of the window. A missing input is a refusal,
    not a default.

    Returns a validated report. ``assigned_state`` is one of :data:`REQUIRED_STATES`
    or :data:`CANDIDATE_STATE`; ``natural_outlet_verified`` is ``True`` exactly
    when ``assigned_state == 'natural_outlet'``.
    """
    seed = _integer(expected_world_seed, "expected_world_seed")
    spacing = _number(expected_spacing_m, "expected_spacing_m")

    claim = _mapping(candidate, "candidate",
                     frozenset({"terminal_cell_id", "declared_state"}))
    terminal = _integer(claim["terminal_cell_id"], "candidate.terminal_cell_id")
    declared = _text(claim["declared_state"], "candidate.declared_state")
    if declared not in REQUIRED_STATES and declared != NATURAL_OUTLET:
        raise ValueError("candidate.declared_state %r is not one of the seven states"
                         % (declared,))

    receiver, height, valid, kinds = _receiver_and_bed(graph)
    if not 0 <= terminal < receiver.size:
        raise ValueError("candidate.terminal_cell_id lies outside the grid")
    flat_receiver = receiver.reshape(-1)
    flat_valid = valid.reshape(-1)
    flat_height = height.reshape(-1)
    flat_kinds = kinds.reshape(-1)
    if not flat_valid[terminal]:
        raise ValueError("a candidate terminal must be a resolved cell")

    labels = _terminal_labels(receiver, height, valid)
    catchment = (labels.reshape(-1) == terminal) & flat_valid

    evidence = _mapping(downstream, "downstream",
                        frozenset({"path_cell_ids", "coastline_cell_id",
                                   "independent_observation"}))
    # An empty path is legal input and must be *refused by the gate*, not by the
    # validator: "no downstream evidence was supplied" is a reason code, not a
    # malformed call.
    path = _field_block(evidence["path_cell_ids"], "downstream.path_cell_ids", 1,
                        allow_empty=True)
    if path.dtype.kind not in "iu":
        # ``np.asarray([])`` is float64; an empty path carries no index to coerce, so
        # it is not a malformed call -- the gate refuses it with a reason code.
        if path.size != 0:
            raise ValueError("downstream.path_cell_ids must be integers")
    path = path.astype(np.int64, copy=False).reshape(-1)
    coast = _integer(evidence["coastline_cell_id"], "downstream.coastline_cell_id")
    independent = _boolean(evidence["independent_observation"],
                           "downstream.independent_observation")

    bounds = _mapping(masks, "masks", frozenset({"coastline_mask",
                                                 "artificial_boundary_mask",
                                                 "unknown_mask"}))
    coastline_mask = _field_block(bounds["coastline_mask"], "masks.coastline_mask", 2)
    artificial = _field_block(bounds["artificial_boundary_mask"],
                              "masks.artificial_boundary_mask", 2)
    unknown = _field_block(bounds["unknown_mask"], "masks.unknown_mask", 2)
    for name, array in (("coastline_mask", coastline_mask),
                        ("artificial_boundary_mask", artificial),
                        ("unknown_mask", unknown)):
        if array.dtype != np.bool_:
            raise ValueError("masks.%s must be a boolean array" % name)
        if array.shape != height.shape:
            raise ValueError("masks.%s must share the graph's 2D shape" % name)
    flat_coast = coastline_mask.reshape(-1)
    flat_artificial = artificial.reshape(-1)
    flat_unknown = unknown.reshape(-1)

    pin = _mapping(source_pin, "source_pin",
                   frozenset({"world_seed", "spacing_m", "native_origin_xz",
                              "outlet_world_xz_m", "page_sha256", "pinned"}))
    quantity = _mapping(water_quantity, "water_quantity",
                        frozenset({"q_m3_s", "provenance", "independent"}))
    level = _mapping(water_level, "water_level",
                     frozenset({"sea_level_m", "water_surface_m", "outlet_bed_m",
                                "datum", "uncertainty_m"}))

    reasons: list[str] = []
    gates: dict[str, bool] = {}

    # ---- gate 1: continuous downstream coverage ---------------------------- #
    path_ok = True
    if path.size < 1:
        reasons.append("missing_continuous_downstream_coverage")
        path_ok = False
    else:
        if np.any(path < 0) or np.any(path >= receiver.size):
            reasons.append("missing_continuous_downstream_coverage")
            path_ok = False
        elif np.unique(path).size != path.size:
            reasons.append("path_reenters_catchment")
            path_ok = False
        if path_ok:
            if int(path[0]) != terminal or int(path[-1]) != coast:
                reasons.append("path_endpoints_mismatch")
                path_ok = False
            if flat_receiver[terminal] >= 0:
                reasons.append("terminal_is_not_receiver_exit")
                path_ok = False
            if not (0 <= coast < receiver.size) or not flat_coast[coast]:
                reasons.append("endpoint_not_explicit_coastline")
                path_ok = False
            if np.any(~flat_valid[path]):
                reasons.append("path_crosses_unresolved")
                path_ok = False
            rows, columns = np.divmod(path, height.shape[1])
            if path.size > 1 and np.any(np.abs(np.diff(rows)) + np.abs(np.diff(columns)) != 1):
                reasons.append("path_not_contiguous")
                path_ok = False
            if path.size > 1 and not np.all(np.diff(flat_height[path]) <= 1e-9):
                reasons.append("path_is_not_downhill")
                path_ok = False
            downstream_only = catchment[path]
            downstream_only[0] = False
            if downstream_only.any():
                reasons.append("path_reenters_catchment")
                path_ok = False
    gates["continuous_downstream_coverage"] = path_ok

    # ---- gate 2: not an artificial boundary -------------------------------- #
    boundary_ok = True
    if flat_artificial[terminal]:
        reasons.append("terminal_on_artificial_boundary")
        boundary_ok = False
    terminal_label = str(flat_kinds[terminal])
    # The graph itself must already say water leaves here. A strictly downhill
    # receiver graph makes ``retained`` a place where the water *stops*, so
    # certifying it as a mouth would contradict the very graph the certificate is
    # built on; ``unknown_boundary`` means the continuation is outside this run.
    if terminal_label != OPEN_OUTFLOW:
        reasons.append("graph_label_is_not_an_open_outflow")
        boundary_ok = False
        if terminal_label == UNKNOWN_BOUNDARY:
            reasons.append("terminal_is_unknown_boundary")
    if path_ok:
        if flat_artificial[path].any():
            reasons.append("path_crosses_artificial_boundary")
            boundary_ok = False
        if not (0 <= coast < receiver.size) or flat_artificial[coast]:
            reasons.append("path_crosses_artificial_boundary")
            boundary_ok = False
    gates["not_artificial_boundary"] = boundary_ok

    # ---- gate 3: no unknown pollution -------------------------------------- #
    # The unknown set is the caller's declaration UNION the set derived from the
    # resolved mask. Trusting the declaration alone would let a caller pass an
    # all-False mask and certify a catchment the resolved mask says was cut.
    pollution_ok = True
    declared_unknown = flat_unknown.copy()
    support_origin = pin["native_origin_xz"]
    origin_known = (isinstance(support_origin, (list, tuple)) and len(support_origin) == 2
                    and all(isinstance(value, (int, np.integer))
                            and not isinstance(value, (bool, np.bool_)) for value in support_origin))
    support_unknown = (derived_unknown_mask(valid, origin_native_xz=support_origin,
                       spacing_m=spacing, world_seed=seed) if origin_known else valid)
    effective_unknown = declared_unknown | support_unknown.reshape(-1)
    if path_ok and effective_unknown[path].any():
        reasons.append("unknown_pollution_on_path")
        pollution_ok = False
    if effective_unknown[catchment].any():
        reasons.append("unknown_pollution_in_upstream_catchment")
        pollution_ok = False
    gates["no_unknown_pollution"] = pollution_ok

    # ---- gate 4: fixed world-coordinate source pin ------------------------- #
    pin_ok = True
    declared_seed = pin["world_seed"]
    declared_spacing = pin["spacing_m"]
    origin = pin["native_origin_xz"]
    pages = pin["page_sha256"]
    pinned_flag = pin["pinned"]
    if isinstance(declared_seed, bool) or not isinstance(declared_seed, (int, np.integer)):
        reasons.append("missing_world_coordinate_source_pin")
        pin_ok = False
    elif int(declared_seed) != seed:
        reasons.append("world_coordinate_source_pin_mismatch")
        pin_ok = False
    try:
        if float(declared_spacing) != spacing:
            reasons.append("world_coordinate_source_pin_mismatch")
            pin_ok = False
    except (TypeError, ValueError):
        reasons.append("missing_world_coordinate_source_pin")
        pin_ok = False
    if (not isinstance(origin, (list, tuple)) or len(origin) != 2
            or any(isinstance(value, bool) or not isinstance(value, (int, np.integer))
                   for value in origin)):
        reasons.append("missing_world_coordinate_source_pin")
        pin_ok = False
        origin = None
    if (not isinstance(pages, (list, tuple)) or not pages
            or any(not isinstance(item, str) or _SHA256.fullmatch(item) is None
                   for item in pages)):
        reasons.append("missing_world_coordinate_source_pin")
        pin_ok = False
    if pinned_flag is not True:
        reasons.append("missing_world_coordinate_source_pin")
        pin_ok = False
    outlet_world = pin["outlet_world_xz_m"]
    if (not isinstance(outlet_world, (list, tuple)) or len(outlet_world) != 2):
        reasons.append("missing_world_coordinate_source_pin")
        pin_ok = False
    elif origin is not None and pin_ok:
        row, column = np.divmod(np.array([terminal]), height.shape[1])
        expected_x = (int(origin[0]) + int(column[0])) * spacing
        expected_z = (int(origin[1]) + int(row[0])) * spacing
        try:
            if (abs(float(outlet_world[0]) - expected_x) > 1e-9
                    or abs(float(outlet_world[1]) - expected_z) > 1e-9):
                reasons.append("world_coordinate_mismatch")
                pin_ok = False
        except (TypeError, ValueError):
            reasons.append("missing_world_coordinate_source_pin")
            pin_ok = False
    gates["world_coordinate_source_pin"] = pin_ok

    # ---- gate 5: water quantity ------------------------------------------- #
    quantity_ok = True
    try:
        q = _number(quantity["q_m3_s"], "water_quantity.q_m3_s")
    except ValueError:
        reasons.append("missing_water_quantity_evidence")
        quantity_ok = False
        q = None
    if quantity_ok and q <= 0.0:
        reasons.append("zero_or_negative_discharge")
        quantity_ok = False
    if not isinstance(quantity["provenance"], str) or not quantity["provenance"]:
        reasons.append("discharge_provenance_unstated")
        quantity_ok = False
        provenance = None
    else:
        provenance = quantity["provenance"]
    if quantity["independent"] is not True:
        reasons.append("discharge_not_independently_observed")
        quantity_ok = False
    gates["water_quantity_evidence"] = quantity_ok

    # ---- gate 6: water level ---------------------------------------------- #
    level_ok = True
    try:
        sea = _number(level["sea_level_m"], "water_level.sea_level_m")
        surface = _number(level["water_surface_m"], "water_level.water_surface_m")
        bed = _number(level["outlet_bed_m"], "water_level.outlet_bed_m")
        uncertainty = _number(level["uncertainty_m"], "water_level.uncertainty_m")
        datum = _text(level["datum"], "water_level.datum")
    except ValueError:
        reasons.append("missing_water_level_evidence")
        level_ok = False
        sea = surface = bed = uncertainty = None
        datum = None
    if level_ok:
        tolerance = uncertainty + 1e-9
        if uncertainty < 0.0:
            reasons.append("missing_water_level_evidence")
            level_ok = False
        if bed > sea + tolerance:
            reasons.append("outlet_bed_above_declared_sea_level")
            level_ok = False
        if surface > sea + tolerance:
            reasons.append("water_surface_above_declared_sea_level")
            level_ok = False
        if bed > surface + tolerance:
            reasons.append("water_surface_below_outlet_bed")
            level_ok = False
    gates["water_level_evidence"] = level_ok

    # ---- the claim never upgrades a label --------------------------------- #
    if declared != NATURAL_OUTLET:
        reasons.append(_DECLARED_REFUSAL[declared])
    certified = (declared == NATURAL_OUTLET and all(gates.values()))
    if declared == NATURAL_OUTLET and certified is False:
        assigned = CANDIDATE_STATE
    elif declared == NATURAL_OUTLET:
        assigned = NATURAL_OUTLET
    else:
        assigned = declared

    ordered = list(dict.fromkeys(reasons))
    report = {
        "schema": SCHEMA,
        "terminal_cell_id": terminal,
        "row_col": [int(value) for value in np.unravel_index(terminal, height.shape)],
        "declared_state": declared,
        "assigned_state": assigned,
        "graph_terminal_kind": str(flat_kinds[terminal]),
        "gates": {name: bool(gates[name]) for name in GATE_NAMES},
        "failure_reasons": ordered,
        "natural_outlet_verified": assigned == NATURAL_OUTLET,
        "ocean_outlet_certified": assigned == NATURAL_OUTLET,
        "evidence": {
            "path_cell_ids": [int(value) for value in path.tolist()],
            "coastline_cell_id": coast,
            "independent_observation": independent,
            "upstream_catchment_cells": int(catchment.sum()),
            "source_pin": {"world_seed": int(declared_seed)
                           if not isinstance(declared_seed, bool)
                           and isinstance(declared_seed, (int, np.integer)) else None,
                           "spacing_m": float(declared_spacing)
                           if isinstance(declared_spacing, (int, float, np.floating))
                           and not isinstance(declared_spacing, bool) else None,
                           "native_origin_xz": list(origin) if origin is not None else None,
                           "outlet_world_xz_m": [float(value) for value in outlet_world]
                           if isinstance(outlet_world, (list, tuple)) and len(outlet_world) == 2
                           else None,
                           "page_sha256": list(pages) if isinstance(pages, (list, tuple)) else None,
                           "pinned": bool(pinned_flag)},
            "water_quantity": {"q_m3_s": q, "provenance": provenance,
                               "independent": quantity["independent"] is True},
            "water_level": {"sea_level_m": sea, "water_surface_m": surface,
                            "outlet_bed_m": bed, "datum": datum,
                            "uncertainty_m": uncertainty},
        },
        "policy": {
            "label_is_not_a_certification": (
                "retained / open_outflow / unknown_boundary / lake / "
                "truncated_not_judged / artificial_window_boundary are states, not "
                "certifications; none of them may be reported as a natural outlet"),
            "required_gates": list(GATE_NAMES),
            "no_inference": ("no coastline from nodata, no outlet from a window edge, "
                             "no sea level from the window minimum, no discharge from a "
                             "receiver count"),
            "multi_cell_path": ("the observed downstream path explains the continuation "
                                "the finite receiver graph cannot: a terminal has no "
                                "downstream, so a multi-cell river mouth is admissible "
                                "only through that evidence"),
        },
        "source_unchanged": True,
        "solver_called": False,
        "limitations": [
            "This module classifies evidence; it does not locate a mouth, measure a "
            "discharge, or establish a vertical datum.",
            "A certified outlet is a statement about the declared evidence set, not "
            "about an observed river.",
        ],
    }
    report["identity_sha256"] = _digest(report)
    validate_report(report)
    return report


def validate_report(report: dict) -> bool:
    """Re-derive every derived field of a report; a mismatch is a hard error."""
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise ValueError("unsupported natural outlet status report")
    assigned = report.get("assigned_state")
    if assigned not in REQUIRED_STATES and assigned != CANDIDATE_STATE:
        raise ValueError("invalid assigned state")
    declared = report.get("declared_state")
    if declared not in REQUIRED_STATES:
        raise ValueError("invalid declared state")
    gates = report.get("gates")
    if not isinstance(gates, dict) or set(gates) != set(GATE_NAMES):
        raise ValueError("invalid gate set")
    if not all(isinstance(value, bool) for value in gates.values()):
        raise ValueError("gate values must be boolean")
    reasons = report.get("failure_reasons")
    if (not isinstance(reasons, list) or len(set(reasons)) != len(reasons)
            or any(item not in REASON_CODES for item in reasons)):
        raise ValueError("invalid failure reasons")
    expected = declared == NATURAL_OUTLET and all(gates.values())
    if report.get("natural_outlet_verified") is not expected:
        raise ValueError("natural outlet flag does not follow from the gates")
    if report.get("ocean_outlet_certified") is not expected:
        raise ValueError("ocean outlet flag does not follow from the gates")
    if expected:
        if assigned != NATURAL_OUTLET:
            raise ValueError("a fully gated claim must be assigned the certified state")
    elif declared == NATURAL_OUTLET:
        if assigned != CANDIDATE_STATE:
            raise ValueError("a failed claim may only become a candidate")
    elif assigned != declared:
        raise ValueError("a non-outlet declaration keeps its own state")
    if declared != NATURAL_OUTLET and _DECLARED_REFUSAL[declared] not in reasons:
        raise ValueError("a non-outlet declaration must carry its refusal reason")
    body = dict(report)
    identity = body.pop("identity_sha256", None)
    if not isinstance(identity, str) or identity != _digest(body):
        raise ValueError("natural outlet status identity mismatch")
    return True
