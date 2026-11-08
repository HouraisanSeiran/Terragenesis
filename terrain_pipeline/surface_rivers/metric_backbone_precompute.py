# -*- coding: utf-8 -*-
"""River backbone precompute: OR-gated segmentation and bounded side-input contracts.

What this module is
-------------------
Pure graph algebra over an **already assembled** receiver. It never routes terrain,
never re-derives D8, never fills a depression and never edits an edge to make a
network look complete. The channel is decided by an explicit gate mask
(``area_cells >= a_min_cells`` **or** a declared flux quantity ``>= q_min``), and the
segments are a maximal, vertex-disjoint partition of that channel.

Why it is a separate layer from ``metric_world_reaches``
-----------------------------------------------------
B2's channel rule is baked into ``resolved_mask & (receiver >= 0) & (upstream_cells >=
threshold)`` and its validator asserts ``reach_of_cell`` equals that expression exactly,
so a flux-only candidate can never enter B2 and *faking* ``upstream_cells`` is
forbidden. This module therefore defines a **new object** with a new schema and new
world-anchored reach ids; B2 is read-only reuse.

Four quantities that are never merged
-------------------------------------
``area_cells`` / ``area_m2``  upstream catchment **area** (cell counts, not discharge)
``q_source_model_scenario``   **actual event** routed water from a declared event model
``q_climatology_estimate``    **estimate** from a caller-declared, uncalibrated input
``water_depth_m`` / ``stage_m`` hydraulic **state** -- never produced here

A real routed m3/s from an event model *is* physical water; it is not a hydraulic state.
This layer neither demotes it nor promotes an estimate to it.

Completeness is per quantity
----------------------------
``area_complete`` and ``q_*_complete`` are **separate** accumulations of the same kernel
flag over different seeds: the parent's window-cut seeds plus, for a flux quantity, every
cell whose local input is unavailable. A quantity's completeness is therefore never read
off the area's.

Side inputs (aggregation vs. refinement) are one slot, not two
--------------------------------------------------------------
``resolve_side_input`` returns exactly one ``chosen`` record. ``aggregated`` and
``refined`` are both reported for comparison, and a deliberately double-counted variant
is emitted with the error it produces so the deduplication is testable.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, digest
from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge

SCHEMA = "metric-river-backbone-v1"
LOGICAL_VERSION = "backbone-or-a-qest-v1"
ALGORITHM = "metric-river-backbone"

SPACING_M = 30.0
CELL_AREA_M2 = 900.0
MAX_SUPPORT_CELLS = 148_225
MAX_REACHES = 32_768
MAX_STEPS = 512

#: First-card **configuration candidates**, not frozen physical thresholds. Both values
#: are part of every reach identity, so changing one produces a new object instead of
#: silently re-labelling the old one.
DEFAULT_A_MIN_CELLS = 48
DEFAULT_Q_MIN_M3_S = 1.0e-3

#: Declared ceiling on resolved branches. **Derived, not magic**: every branch member is a
#: distinct non-channel cell, so the sum of all branch member counts cannot exceed the valid
#: cell count (148 225). The per-branch working set is ``steps * members`` floats -- a branch
#: solve allocates only its own members, never a grid copy -- so the whole set together is at
#: most ``steps * cells * 8`` = 28.5 MB at 24 steps, and the largest single branch is far
#: below that. Time is the same sum: <= 3.6 M member-steps. The binding cost is the stored
#: record (member cells + three short series per branch), which stays ~1 MB at 148 225 members.
#: The former 256 was a prototype count, not a physical limit; 1024 keeps a declared headroom
#: without letting a runaway segmentation write an unbounded payload.
DEFAULT_MAX_BRANCHES = 1024

TERMINAL_KIND_DTYPE = np.dtype("U24")
TERMINAL_LABELS = ("inactive", "interior", "retained", "open_outflow", "unknown_boundary")

QUANTITY_SCENARIO = "source_model_scenario"
QUANTITY_CLIMATOLOGY = "climatology_estimate"
FLUX_QUANTITIES = (QUANTITY_SCENARIO, QUANTITY_CLIMATOLOGY)
FLUX_QUANTITY_SEMANTICS = {
    QUANTITY_SCENARIO: {
        "unit": "m3/s",
        "nature": "actual_event_routed_water",
        "claim": ("a declared event model's real production routed on this support; this is "
                  "physical water, and it is still not a hydraulic state"),
    },
    QUANTITY_CLIMATOLOGY: {
        "unit": "m3/s",
        "nature": "declared_estimate_uncalibrated",
        "claim": ("a caller-declared climatological estimate; uncalibrated, never presented "
                  "as an observed or simulated event"),
    },
}

AREA_STATUS_COMPLETE = "complete"
AREA_STATUS_PENDING = "lower_bound_pending"
QUANTITY_STATUS_AVAILABLE = "available"
QUANTITY_STATUS_PENDING = "not_available_pending"

CHANNEL_RULE = (
    "gate = valid & ((area_cells >= a_min_cells) | (gate_q >= q_min for at least one "
    "declared, available, finite, nonnegative flux quantity)); a gate on a lower-bound "
    "quantity selects only cells whose known lower bound already passes, and the count of "
    "such cells is reported. The gate is a property selection, not a routability claim: "
    "routable channel = gate & (receiver >= 0), and gate & (receiver < 0) is kept separately "
    "as selected terminal anchors. Neither half is dropped.")
SEGMENTATION_RULE = (
    "a reach starts at a channel cell whose channel-donor count is not 1 (0 = source, >= 2 "
    "= junction) and continues downstream while the next cell is a plain channel "
    "continuation; a junction cell belongs to the downstream reach, so reaches are maximal "
    "and vertex-disjoint; one-cell source and confluence reaches are kept")
REACH_IDENTITY_POLICY = (
    "reach_id = 'rb-' + sha256 over a world-anchored logical payload (algorithm, logical "
    "version, channel rule, both gates, world seed, spacing, plan_version, the root's world "
    "(x,z), the ordered source-to-tail world path digest and the downstream rule). The "
    "support origin/shape, local flat indices, reach_index and the selection of other "
    "reaches are excluded, so the same world reach keeps one id in a wider support; the "
    "path digest is over the ordered sequence and never over a set.")
DOWNSTREAM_RULE = (
    "reach_downstream is the reach that owns the receiver target of this reach's tail "
    "cell, or -1 when the tail drains into its structural terminal; a downstream reach is "
    "never inferred across a root boundary")
TERMINAL_POLICY = (
    "two independent fields: event_receiver (a declared finite event receiver with its own "
    "evidence and time/volume bounds) and permanent_terminal (ocean mouth / world "
    "endorheic / pending). A retained or unknown_boundary cell is never either one by "
    "default, and v1 emits permanent_terminal=pending only")
DISPLAY_LINE_POLICY = (
    "not_provided_in_v1: the ordered native trace is the authority; a simplified polyline "
    "may never be used for excavation, routing or physics and is not shipped here")
LOCAL_Q_POLICY = (
    "area is an upstream cell count and is never called discharge; flux is reported per "
    "declared quantity with its own completeness, and a missing local input is propagated "
    "downstream instead of being read as zero")

REASON_UNPREPARED = "unprepared"
REASON_BUDGET = "budget_exceeded"
REASON_CHANNEL_RECEIVER_NOT_TERMINAL = "channel_receiver_not_terminal"
REASON_SEGMENT_COVERAGE = "segment_coverage_mismatch"
REASON_CROSS_ROOT_FLOW = "cross_root_flow"
REASON_TERMINAL_EDGE_MISSING = "terminal_edge_missing"
REASON_REACH_CYCLE = "reach_cycle"
REASON_QUANTITY_MISMATCH = "quantity_contract_mismatch"
REASON_EVIDENCE_INSUFFICIENT = "event_receiver_evidence_insufficient"
REASON_GATE_TERMINAL = "gate_selected_terminal_anchor"

REASON_VOCABULARY = (
    REASON_UNPREPARED, REASON_BUDGET, REASON_CHANNEL_RECEIVER_NOT_TERMINAL,
    REASON_SEGMENT_COVERAGE, REASON_CROSS_ROOT_FLOW, REASON_TERMINAL_EDGE_MISSING,
    REASON_REACH_CYCLE, REASON_QUANTITY_MISMATCH, REASON_EVIDENCE_INSUFFICIENT,
    REASON_GATE_TERMINAL,
)

PARENT_KEYS = ("schema", "arrays", "metadata", "identity_sha256")
PARENT_ARRAY_KEYS = ("receiver", "resolved_mask", "terminal_kind", "upstream_cells",
                     "owner_index", "complete_mask", "upstream_unknown_mask")

BUNDLE_KEYS = {"schema", "parent", "arrays", "reaches", "roots", "metadata",
               "identity_sha256"}


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _strict_int(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError("%s must be an integer, got %r" % (name, type(value).__name__))
    number = int(value)
    if minimum is not None and number < minimum:
        raise ValueError("%s must be >= %d, got %d" % (name, minimum, number))
    if maximum is not None and number > maximum:
        raise ValueError("%s must be <= %d, got %d" % (name, maximum, number))
    return number


def _finite_float(value, name, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError("%s must be numeric" % name)
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("%s must be finite" % name)
    if minimum is not None and number < minimum:
        raise ValueError("%s must be >= %r, got %r" % (name, minimum, number))
    return number


def _grid(value, name, dtype, shape=None):
    if not isinstance(value, np.ndarray) or value.dtype != dtype or value.ndim != 2:
        raise ValueError("%s must be a 2D %s array" % (name, np.dtype(dtype).name))
    if shape is not None and value.shape != tuple(shape):
        raise ValueError("%s must have shape %s, got %s" % (name, list(shape), list(value.shape)))
    return value


def _sha_world_pairs(pairs):
    block = np.ascontiguousarray(np.asarray(pairs, np.int64).reshape(-1, 2), dtype="<i8")
    return hashlib.sha256(block.tobytes()).hexdigest()


def _world_of(flat, origin_native_xz, columns):
    flat = np.asarray(flat, np.int64).reshape(-1)
    return np.stack([origin_native_xz[0] + flat % columns,
                     origin_native_xz[1] + flat // columns], axis=1)


def _hop_length_m(first, second, columns, spacing_m):
    return float(spacing_m) * math.hypot(first // columns - second // columns,
                                         first % columns - second % columns)


def _chain_length_m(cells, columns, spacing_m):
    if len(cells) < 2:
        return 0.0
    return float(sum(_hop_length_m(int(first), int(second), columns, spacing_m)
                     for first, second in zip(cells[:-1], cells[1:])))


# --------------------------------------------------------------------------- #
# parent view (structural only; the B1 semantic gate belongs to prepare/audit)
# --------------------------------------------------------------------------- #
def parent_view(parent):
    """Expose the parent's declared arrays after a **structural** check.

    The B1 semantic gate (``metric_world_domains.validate_domain_candidates``) is not
    re-run here: it is an expensive full recomputation that belongs to ``prepare`` and to
    the independent audit. This function refuses an incoherent parent (wrong shapes,
    dtypes, receiver outside the grid, undeclared terminal vocabulary) so a build can
    never read nonsense, and leaves certification to its own gate.
    """
    if not isinstance(parent, dict) or any(key not in parent for key in PARENT_KEYS):
        raise ValueError("%s: the parent must carry %s" % (REASON_UNPREPARED, list(PARENT_KEYS)))
    arrays = parent["arrays"]
    if not isinstance(arrays, dict):
        raise ValueError("%s: the parent arrays must be a mapping" % REASON_UNPREPARED)
    missing = [key for key in PARENT_ARRAY_KEYS if key not in arrays]
    if missing:
        raise ValueError("%s: the parent is missing arrays %s" % (REASON_UNPREPARED, missing))
    receiver = arrays["receiver"]
    if not isinstance(receiver, np.ndarray) or receiver.dtype != np.int64 or receiver.ndim != 2:
        raise ValueError("%s: the parent receiver must be a 2D int64 array" % REASON_UNPREPARED)
    shape = receiver.shape
    cells = int(shape[0] * shape[1])
    if cells > MAX_SUPPORT_CELLS:
        raise ValueError("%s: %d cells exceeds the declared support ceiling %d; a larger "
                         "support needs its own budget and a separate review"
                         % (REASON_BUDGET, cells, MAX_SUPPORT_CELLS))
    valid = _grid(arrays["resolved_mask"], "resolved_mask", np.dtype(np.bool_), shape)
    kinds = arrays["terminal_kind"]
    if (not isinstance(kinds, np.ndarray) or kinds.shape != shape
            or kinds.dtype.kind != "U"):
        raise ValueError("%s: terminal_kind must be a Unicode array of the parent shape"
                         % REASON_UNPREPARED)
    if not np.isin(kinds[valid], ("interior", "retained", "open_outflow",
                                  "unknown_boundary")).all():
        raise ValueError("%s: the parent declares a terminal kind outside %s"
                         % (REASON_UNPREPARED, list(TERMINAL_LABELS)))
    if np.any(kinds[~valid] != "inactive"):
        raise ValueError("%s: inactive cells must declare terminal_kind 'inactive'"
                         % REASON_UNPREPARED)
    _grid(arrays["upstream_cells"], "upstream_cells", np.dtype(np.int64), shape)
    _grid(arrays["owner_index"], "owner_index", np.dtype(np.int64), shape)
    _grid(arrays["complete_mask"], "complete_mask", np.dtype(np.bool_), shape)
    seeds = _grid(arrays["upstream_unknown_mask"], "upstream_unknown_mask",
                  np.dtype(np.bool_), shape)
    if np.any(seeds[~valid]):
        raise ValueError("%s: inactive cells cannot seed an unknown upstream" % REASON_UNPREPARED)
    flat_receiver = receiver.reshape(-1)
    if np.any(flat_receiver < -1) or np.any(flat_receiver >= cells):
        raise ValueError("%s: the parent receiver index is outside the grid" % REASON_UNPREPARED)
    flat_valid = valid.reshape(-1)
    if np.any(flat_receiver[~flat_valid] != -1):
        raise ValueError("%s: inactive cells must have receiver -1" % REASON_UNPREPARED)
    live = flat_valid & (flat_receiver >= 0)
    if np.any(~flat_valid[flat_receiver[live]]):
        raise ValueError("%s: a receiver target is an inactive cell" % REASON_UNPREPARED)
    metadata = parent["metadata"]
    if not isinstance(metadata, dict):
        raise ValueError("%s: the parent metadata must be a mapping" % REASON_UNPREPARED)
    support = metadata.get("support", {})
    if not isinstance(support, dict):
        support = {}
    origin = support.get("origin_native_xz") or metadata.get("origin_native_xz")
    if not isinstance(origin, (list, tuple)) or len(origin) != 2:
        raise ValueError("%s: the parent must declare a signed native (x,z) origin"
                         % REASON_UNPREPARED)
    world_seed = support.get("world_seed", metadata.get("world_seed"))
    plan_version = support.get("plan_version", metadata.get("plan_version"))
    return {
        "bundle": parent,
        "schema": parent["schema"],
        "identity_sha256": parent["identity_sha256"],
        "shape": shape,
        "origin_native_xz": [int(origin[0]), int(origin[1])],
        "world_seed": _strict_int(world_seed, "world_seed", minimum=0),
        "spacing_m": _finite_float(support.get("spacing_m", SPACING_M), "spacing_m",
                                   minimum=1e-6),
        "plan_version": _strict_int(plan_version, "plan_version", minimum=1),
        "support_identity_sha256": metadata.get("support_identity_sha256"),
        "receiver": receiver,
        "valid_mask": valid,
        "terminal_kind": kinds,
        "upstream_cells": arrays["upstream_cells"],
        "owner_index": arrays["owner_index"],
        "complete_mask": arrays["complete_mask"],
        "upstream_unknown_mask": seeds,
    }


# --------------------------------------------------------------------------- #
# accumulation: area, flux, and per-quantity completeness
# --------------------------------------------------------------------------- #
def _kinds_for_kernel(valid_mask, receiver, terminal_kind):
    kinds = np.full(receiver.shape, "inactive", dtype=TERMINAL_KIND_DTYPE)
    live = valid_mask & (receiver >= 0)
    kinds[valid_mask & ~live] = terminal_kind[valid_mask & ~live]
    kinds[live] = "interior"
    return kinds


def propagate_unknown(*, receiver, valid_mask, terminal_kind, unknown_seed,
                      max_cells=MAX_SUPPORT_CELLS):
    """Propagate "this cell has an undeclared or missing input" downstream.

    The propagation is the frozen kernel's own flag (``upstream_unknown_mask`` OR-
    accumulated along the receiver), not a second walk: one quantity must not get two
    implementations that can disagree in direction. The unit local flux is only the
    kernel's required carrier -- the returned flow is discarded.
    """
    shape = receiver.shape
    _grid(valid_mask, "valid_mask", np.dtype(np.bool_), shape)
    seeds = _grid(unknown_seed, "unknown_seed", np.dtype(np.bool_), shape)
    if np.any(seeds[~valid_mask]):
        raise ValueError("unknown seeds cannot sit on inactive cells")
    unit = np.where(valid_mask, 1.0, 0.0)
    out = accumulate_network_discharge(
        receiver, unit, valid_mask,
        terminal_kind=_kinds_for_kernel(valid_mask, receiver, terminal_kind),
        upstream_unknown_mask=seeds, max_cells=int(max_cells))
    return np.ascontiguousarray(out["complete_mask"], np.bool_)


def accumulate_area(*, receiver, valid_mask, terminal_kind, upstream_unknown_mask,
                    max_cells=MAX_SUPPORT_CELLS):
    """Upstream **cell count** and its own completeness.

    ``area_cells`` and ``area_m2`` are catchment area. They are never called discharge: a
    cell count is not m3/s and the two are never summed.
    """
    shape = receiver.shape
    _grid(valid_mask, "valid_mask", np.dtype(np.bool_), shape)
    seeds = _grid(upstream_unknown_mask, "upstream_unknown_mask", np.dtype(np.bool_), shape)
    unit = np.where(valid_mask, 1.0, 0.0)
    out = accumulate_network_discharge(
        receiver, unit, valid_mask,
        terminal_kind=_kinds_for_kernel(valid_mask, receiver, terminal_kind),
        upstream_unknown_mask=seeds, max_cells=int(max_cells))
    routed = out["known_routed_q_m3_s"]
    area = np.rint(routed).astype(np.int64)
    if not np.array_equal(area.astype(np.float64), routed):
        raise RuntimeError("an upstream cell count must be integral; a unit local flux "
                           "produced a fractional count")
    if np.any(area[~valid_mask] != 0):
        raise RuntimeError("an inactive cell accumulated upstream cells")
    return (np.ascontiguousarray(area, np.int64),
            np.ascontiguousarray(out["complete_mask"], np.bool_))


def _local_flux_block(local_flux, valid_mask, steps):
    block = np.asarray(local_flux, np.float64)
    if block.ndim != 3 or block.shape[0] != int(steps) or block.shape[1:] != valid_mask.shape:
        raise ValueError("local_flux must be [steps, z, x] with steps=%d and the grid shape"
                         % int(steps))
    if not np.isfinite(block).all():
        raise ValueError("local_flux must be finite")
    if np.any(block < 0.0):
        raise ValueError("local_flux must be nonnegative")
    if np.any(block[:, ~valid_mask] != 0.0):
        raise ValueError("inactive cells must carry zero local flux")
    return block


def accumulate_flux(*, receiver, valid_mask, terminal_kind, local_flux,
                    max_cells=MAX_SUPPORT_CELLS):
    """Accumulate one flux quantity over the same graph, one kernel call per step.

    Returns the routed field per step plus the per-step terminal ledger. No completeness is
    derived here: a quantity's completeness is its own ``quantity_complete`` result.
    """
    block = np.asarray(local_flux, np.float64)
    if block.ndim != 3:
        raise ValueError("local_flux must be [steps, z, x]")
    steps = int(block.shape[0])
    kinds = _kinds_for_kernel(valid_mask, receiver, terminal_kind)
    flow = np.zeros((steps,) + receiver.shape, np.float64)
    totals = {name: np.zeros(steps, np.float64) for name in
              ("input_total_m3_s", "retained_m3_s", "open_outflow_m3_s",
               "unknown_pending_m3_s", "residual_m3_s")}
    for step in range(steps):
        out = accumulate_network_discharge(receiver, block[step], valid_mask,
                                           terminal_kind=kinds, max_cells=int(max_cells))
        flow[step] = out["known_routed_q_m3_s"]
        for name in totals:
            totals[name][step] = out[name]
    return np.ascontiguousarray(flow), totals


def quantity_complete(*, receiver, valid_mask, terminal_kind, available_mask,
                      parent_unknown_seed, max_cells=MAX_SUPPORT_CELLS):
    """A flux quantity's own completeness.

    Two independent sources of ignorance are merged, and only these two:

    1. the parent's window-cut seeds (an inflow from outside the support is undeclared);
    2. every valid cell whose local input for **this** quantity is unavailable.

    ``area_complete`` is not consulted. A complete catchment says nothing about whether the
    water input was known, and reading one off the other is exactly the mistake this
    signature prevents.
    """
    shape = receiver.shape
    _grid(available_mask, "available_mask", np.dtype(np.bool_), shape)
    _grid(parent_unknown_seed, "parent_unknown_seed", np.dtype(np.bool_), shape)
    unknown = valid_mask & (~available_mask | parent_unknown_seed)
    return propagate_unknown(receiver=receiver, valid_mask=valid_mask,
                             terminal_kind=terminal_kind, unknown_seed=unknown,
                             max_cells=max_cells)


def missing_input_seed(*, receiver, valid_mask, available_mask, parent_unknown_seed,
                       max_cells=MAX_SUPPORT_CELLS):
    """The explicit seed array a quantity's completeness rests on (for the audit)."""
    _grid(available_mask, "available_mask", np.dtype(np.bool_), receiver.shape)
    _grid(parent_unknown_seed, "parent_unknown_seed", np.dtype(np.bool_), receiver.shape)
    return np.ascontiguousarray(valid_mask & (~available_mask | parent_unknown_seed), np.bool_)


# --------------------------------------------------------------------------- #
# gates and segmentation
# --------------------------------------------------------------------------- #
def channel_gates(*, valid_mask, area_cells, gate_flux, a_min_cells, q_min_m3_s,
                  available=None):
    """``a_gate | q_gate`` where ``gate_flux`` is ``{quantity: flux_at_gate_step}``.

    A gate applied to a lower-bound quantity selects only cells whose *known* lower bound
    already passes, which is a sound selection; the count of those cells is reported so a
    reviewer can see how much of the channel rests on a lower bound.

    Only a **declared** flux quantity may open a gate, and its values must be finite and
    nonnegative: an arbitrary array name cannot smuggle a number in as physics. When
    ``available`` is given (``{quantity: bool mask}``) a cell outside that quantity's
    declared availability cannot open the gate either, so a gate can never be driven by a
    value the build does not actually have.

    The returned mask is the **raw** gate and may still contain structural terminals; the
    caller must intersect it with ``receiver >= 0`` before segmenting (see
    :func:`routable_channel`) and keep the selected terminals as anchors.
    """
    a_min_cells = _strict_int(a_min_cells, "a_min_cells", minimum=1)
    q_min = _finite_float(q_min_m3_s, "q_min_m3_s", minimum=0.0)
    valid = np.asarray(valid_mask, np.bool_)
    area = _grid(np.asarray(area_cells, np.int64), "area_cells", np.dtype(np.int64),
                 valid.shape)
    a_gate = valid & (area >= a_min_cells)
    q_gate = np.zeros(valid.shape, np.bool_)
    per_quantity = {}
    for name in sorted(gate_flux):
        if name not in FLUX_QUANTITIES:
            raise ValueError("%s: %r is not a declared flux quantity; %s are the only "
                             "quantities allowed to open a gate"
                             % (REASON_QUANTITY_MISMATCH, name, list(FLUX_QUANTITIES)))
        values = _grid(np.asarray(gate_flux[name], np.float64), "gate_flux[%s]" % name,
                       np.dtype(np.float64), valid.shape)
        if not np.isfinite(values).all():
            raise ValueError("%s: gate_flux[%s] must be finite"
                             % (REASON_QUANTITY_MISMATCH, name))
        if np.any(values < 0.0):
            raise ValueError("%s: gate_flux[%s] must be nonnegative"
                             % (REASON_QUANTITY_MISMATCH, name))
        usable = valid
        if available is not None and name in available:
            usable_mask = _grid(np.asarray(available[name], np.bool_),
                                 "available[%s]" % name, np.dtype(np.bool_), valid.shape)
            usable = usable & usable_mask
        hit = usable & (values >= q_min)
        per_quantity[name] = int(hit.sum())
        q_gate |= hit
    return (a_gate | q_gate), a_gate, q_gate, per_quantity


def routable_channel(*, gate_mask, receiver):
    """Split a raw gate into the cells that can be walked and the terminals it selects.

    The gate is a *property* selection and says nothing about routability: a structural
    terminal (``receiver < 0``) can pass an area or flux gate. Segmenting such a cell would
    be asking a directed chain to continue from a cell that has no receiver. So the gate is
    split, explicitly and by name, and both halves are published:

    ``routable``     ``gate & (receiver >= 0)`` -- what the reaches are built from
    ``terminals``    ``gate & (receiver < 0)``  -- selected end points, kept as anchors

    Neither half is dropped: a terminal that passes the gate becomes a recorded anchor, and
    a reach whose tail drains into it still carries its own terminal edge.
    """
    gate = np.asarray(gate_mask, np.bool_)
    rec = np.asarray(receiver, np.int64)
    if gate.shape != rec.shape:
        raise ValueError("gate_mask and receiver must share one shape")
    routable = gate & (rec >= 0)
    terminals = gate & (rec < 0)
    return routable, terminals


def segment_on_channel(*, receiver, valid_mask, channel_mask, max_reaches=MAX_REACHES):
    """Partition an **explicit** channel mask into maximal, vertex-disjoint reaches.

    Same semantics as the B2 partition, but the channel is the caller's mask instead of an
    ``upstream_cells`` threshold. Faking the counts to reach this shape would be a forged
    parent; taking the mask is not.
    """
    rec = np.asarray(receiver, np.int64).reshape(-1)
    valid = np.asarray(valid_mask, np.bool_).reshape(-1)
    channel = np.asarray(channel_mask, np.bool_).reshape(-1) & valid
    channel_cells = int(channel.sum())
    if channel_cells == 0:
        return {"channel": channel, "channel_cells": 0,
                "donors": np.zeros(rec.size, np.int64),
                "reach_of_cell": np.full(rec.size, -1, np.int64), "chains": []}
    if np.any(channel & (rec < 0)):
        raise ValueError("%s: a channel cell has no receiver" % REASON_CHANNEL_RECEIVER_NOT_TERMINAL)
    donors = np.bincount(rec[channel], minlength=rec.size).astype(np.int64)
    starts = np.flatnonzero(channel & (donors != 1))
    if starts.size > int(max_reaches):
        raise ValueError("%s: %d makes exceeds the declared reach ceiling %d; split the "
                         "support instead of relaxing the budget"
                         % (REASON_BUDGET, starts.size, max_reaches))
    reach_of_cell = np.full(rec.size, -1, np.int64)
    chains = []
    for start in starts.tolist():
        chain = [start]
        reach_of_cell[start] = len(chains)
        current = start
        while True:
            following = int(rec[current])
            if following < 0 or not channel[following] or donors[following] != 1:
                break
            reach_of_cell[following] = len(chains)
            chain.append(following)
            current = following
        chains.append(chain)
    if channel_cells and not chains:
        raise RuntimeError("a non-empty channel produced no reach")
    covered = int((reach_of_cell >= 0).sum())
    if covered != channel_cells:
        raise RuntimeError("%s: %d channel cells sit outside every reach"
                           % (REASON_SEGMENT_COVERAGE, channel_cells - covered))
    return {"channel": channel, "channel_cells": channel_cells, "donors": donors,
            "reach_of_cell": reach_of_cell, "chains": chains}


def reach_downstream(*, receiver, chains, terminal_kind=None):
    """The owning reach of each tail's receiver, ``-1`` when the tail ends outside the channel.

    A tail's receiver can be (a) another channel cell -- a normal handoff, (b) a structural
    terminal -- the last edge of a terminal reach, or (c) a valid cell that simply **failed
    the gate** -- a gate cut. Case (c) is not an error: the reach really does end there, the
    cell below is outside the declared channel, and the edge is still recorded so the cut is
    visible rather than hidden. What is an error is a tail whose receiver is an invalid cell.

    Returns ``(downstream, ends)``; ``ends`` tags every reach whose tail does not hand off
    as ``structural_terminal`` (recognised from ``terminal_kind``) or ``gate_cut``.
    """
    rec = np.asarray(receiver, np.int64).reshape(-1)
    flat_reach = np.full(rec.size, -1, np.int64)
    for index, chain in enumerate(chains):
        flat_reach[np.asarray(chain, np.int64)] = index
    downstream = np.full(len(chains), -1, np.int64)
    ends = []
    kinds = None
    if terminal_kind is not None:
        kinds = np.asarray(terminal_kind).reshape(-1)
    for index, chain in enumerate(chains):
        tail = int(chain[-1])
        following = int(rec[tail])
        if following < 0:
            # a routable channel cell cannot get here; recorded as an invalid end
            ends.append({"reach_index": index, "tail_cell_flat": tail,
                         "receiver_cell_flat": -1, "reason": "no_receiver"})
            continue
        owner = int(flat_reach[following])
        if owner >= 0:
            downstream[index] = owner
            continue
        label = None if kinds is None else str(kinds[following])
        ends.append({"reach_index": index, "tail_cell_flat": tail,
                     "receiver_cell_flat": following,
                     "terminal_kind_of_receiver": label,
                     "reason": ("structural_terminal"
                                if label in ("retained", "open_outflow", "unknown_boundary")
                                else "gate_cut")})
    return downstream, ends


# --------------------------------------------------------------------------- #
# side inputs: aggregation vs. real subgraph refinement
# --------------------------------------------------------------------------- #
def assign_local_branches(*, receiver, valid_mask, channel_mask, supply_mask,
                          origin_native_xz=None):
    """Assign every non-channel supply cell to exactly one branch, by entry cell.

    The entry is the **last** supply cell still outside the channel, so the side input is
    injected at the real confluence cell and never moved up to a reach head. A cell with no
    path into the channel, or one caught in a cycle, is listed as unassigned -- never
    dropped silently.
    """
    rec = np.asarray(receiver, np.int64).reshape(-1)
    valid = np.asarray(valid_mask, np.bool_).reshape(-1)
    channel = np.asarray(channel_mask, np.bool_).reshape(-1) & valid
    supply = np.asarray(supply_mask, np.bool_).reshape(-1) & valid
    columns = np.asarray(valid_mask).shape[1]
    segmentation = segment_on_channel(receiver=receiver, valid_mask=valid_mask,
                                      channel_mask=channel_mask)
    flat_reach = np.full(rec.size, -1, np.int64)
    for index, chain in enumerate(segmentation["chains"]):
        flat_reach[np.asarray(chain, np.int64)] = index
    grouped = {}
    unassigned = []
    for cell in np.flatnonzero(supply & (flat_reach < 0)).tolist():
        seen = set()
        current = int(cell)
        entry = -1
        reach = -1
        while True:
            if current in seen:
                unassigned.append({"cell_flat": int(cell), "reason": "cycle"})
                break
            seen.add(current)
            following = int(rec[current])
            if following < 0:
                unassigned.append({"cell_flat": int(cell), "reason": "no_channel_downstream"})
                break
            if flat_reach[following] >= 0:
                entry = current
                reach = int(flat_reach[following])
                break
            current = following
        if entry >= 0:
            grouped.setdefault((entry, reach), []).append(int(cell))
    branches = []
    for (entry, reach), members in sorted(grouped.items()):
        cells = np.asarray(sorted(members), np.int64)
        world = (None if origin_native_xz is None
                 else _world_of(cells, origin_native_xz, columns))
        branches.append({
            "entry_cell_flat": int(entry),
            "entry_receiver_cell_flat": int(rec[entry]),
            "entry_reach_index": int(reach),
            "member_cells": cells,
            "member_count": int(cells.size),
            "member_world_xz": (None if world is None
                                else [[int(a), int(b)] for a, b in world.tolist()]),
            "member_world_sha256": (None if world is None else _sha_world_pairs(world)),
        })
    return {"branches": branches, "unassigned": unassigned,
            "assigned_cells": int(sum(b["member_count"] for b in branches)),
            "supply_cells": int(supply.sum())}


def aggregate_branch_supply(*, branch, local_flux):
    """The aggregated side input: every member's local flux summed, per step.

    ``area_cells`` here is the branch's own cell count (each member counted once), not a sum
    of member areas -- the members already form the branch's closed subtree and summing
    per-member areas would count nested cells repeatedly.
    """
    members = np.asarray(branch["member_cells"], np.int64)
    block = np.asarray(local_flux, np.float64)
    if block.ndim != 3:
        raise ValueError("local_flux must be [steps, z, x]")
    steps = int(block.shape[0])
    flat = block.reshape(steps, -1)
    if members.size and int(members.max()) >= flat.shape[1]:
        raise ValueError("a branch member is outside the flux grid")
    supply = (np.zeros(steps, np.float64) if not members.size
              else flat[:, members].sum(axis=1))
    return {"area_cells": int(members.size), "q_m3_s": [float(v) for v in supply]}


def solve_branch_subgraph(*, receiver, valid_mask, branch, local_flux):
    """Really solve the branch's receiver subtree and deliver it at its entry cell.

    The answer is produced by a Kahn-style scalar queue over the branch's own members; it
    does **not** read the whole-graph answer and does not read any reference routed field.
    Under a lossless accumulation graph the value equals the aggregated sum; the point of
    solving it separately is that the two are computed independently, and because a future
    branch with storage or rejection would separate them.

    Only the branch's own members are allocated: a per-branch copy of the whole grid would
    cost ``steps * cells`` floats per branch for no information, and that cost is what
    decides how many branches fit a run.
    """
    rec = np.asarray(receiver, np.int64).reshape(-1)
    valid = np.asarray(valid_mask, np.bool_).reshape(-1)
    members = np.asarray(branch["member_cells"], np.int64)
    entry = int(branch["entry_cell_flat"])
    block = np.asarray(local_flux, np.float64)
    if block.ndim != 3:
        raise ValueError("local_flux must be [steps, z, x]")
    steps = int(block.shape[0])
    flat = block.reshape(steps, -1)
    if not members.size:
        return {"area_cells": 1, "q_m3_s": [float(v) for v in flat[:, entry]]}
    if not np.all(valid[members]):
        raise ValueError("a branch member is not a valid cell")
    position = {int(cell): index for index, cell in enumerate(members.tolist())}
    pending = np.zeros(members.size, np.int64)
    for index, cell in enumerate(members.tolist()):
        target = position.get(int(rec[cell]))
        if target is not None:
            pending[target] += 1
    area = np.ones(members.size, np.int64)
    flow = flat[:, members].copy()
    frontier = [index for index in range(members.size) if pending[index] == 0]
    processed = 0
    while frontier:
        following = []
        for index in frontier:
            processed += 1
            target = position.get(int(rec[int(members[index])]))
            if target is None:
                continue
            area[target] += area[index]
            flow[:, target] += flow[:, index]
            pending[target] -= 1
            if pending[target] == 0:
                following.append(target)
        frontier = following
    if processed != int(members.size):
        raise ValueError("%s: the branch subgraph contains a cycle" % REASON_REACH_CYCLE)
    entry_index = position.get(entry)
    if entry_index is None:
        raise ValueError("the branch entry is not one of its members")
    return {"area_cells": int(area[entry_index]),
            "q_m3_s": [float(v) for v in flow[:, entry_index]]}


def resolve_side_input(*, receiver, valid_mask, branch, local_flux, time_edges_s,
                       mode="refined", rtol=1e-12, atol=1e-15):
    """The one side-input slot for a branch: ``aggregated`` or ``refined``, never both.

    Returns a single ``chosen`` record (so no caller can add the two), both alternatives for
    comparison, the member coverage, and the error a deliberate double count would produce.
    """
    if mode not in ("aggregated", "refined"):
        raise ValueError("mode must be 'aggregated' or 'refined', got %r" % (mode,))
    edges = np.asarray(time_edges_s, np.float64).reshape(-1)
    block = np.asarray(local_flux, np.float64)
    if block.ndim != 3:
        raise ValueError("local_flux must be [steps, z, x]")
    steps = int(block.shape[0])
    if edges.size != steps + 1 or np.any(np.diff(edges) <= 0.0):
        raise ValueError("%s: time_edges_s must hold steps+1 increasing physical edges"
                         % REASON_QUANTITY_MISMATCH)
    members = np.asarray(branch["member_cells"], np.int64)
    aggregated = aggregate_branch_supply(branch=branch, local_flux=block)
    refined = solve_branch_subgraph(receiver=receiver, valid_mask=valid_mask,
                                    branch=branch, local_flux=block)
    aggregated_q = np.asarray(aggregated["q_m3_s"], np.float64)
    refined_q = np.asarray(refined["q_m3_s"], np.float64)
    matches = bool(np.allclose(aggregated_q, refined_q, rtol=rtol, atol=atol)
                   and int(aggregated["area_cells"]) == int(refined["area_cells"]))
    double_q = aggregated_q + refined_q
    chosen = refined if mode == "refined" else aggregated
    return {
        "mode": mode,
        "chosen": {"from": mode, "area_cells": int(chosen["area_cells"]),
                   "q_m3_s": [float(v) for v in chosen["q_m3_s"]]},
        "aggregated": aggregated,
        "refined": refined,
        "matches": matches,
        "matches_policy": {
            "rtol": float(rtol), "atol": float(atol),
            "note": ("lossless accumulation makes the two mathematically equal; only a loss, "
                     "storage or rejection inside the branch would separate them")},
        "coverage": {
            "member_count": int(members.size),
            "member_world_sha256": branch.get("member_world_sha256"),
            "entry_cell_flat": int(branch["entry_cell_flat"]),
            "entry_receiver_cell_flat": int(branch["entry_receiver_cell_flat"]),
            "entry_reach_index": int(branch["entry_reach_index"]),
            "coverage_complete": bool(branch.get("member_world_sha256") is not None),
            "member_world_xz_policy": ("world coordinates are derived from member_cells and "
                                      "the support origin; storing them again would double "
                                      "the record for no new information"),
        },
        "time_edges_s": [float(v) for v in edges],
        "steps": steps,
        "double_count_negative": {
            "area_cells": int(aggregated["area_cells"] + refined["area_cells"]),
            "q_m3_s": [float(v) for v in double_q],
            "error_vs_chosen_m3_s": [float(v) for v in (double_q - refined_q)],
            "detected": bool(int(aggregated["area_cells"] + refined["area_cells"])
                             != int(refined["area_cells"])
                             or not np.allclose(double_q, refined_q, rtol=rtol, atol=atol)),
            "note": ("choosing both representations adds one extra copy of the same supply; "
                     "this record exists so the deduplication is checkable, not so it is used"),
        },
    }


# --------------------------------------------------------------------------- #
# event receiver evidence (explicit adapter for the delivered finite-sample product)
# --------------------------------------------------------------------------- #
def build_event_receiver_record(*, terminal_cell_world_native, product_schema, product_identity,
                                origin_native_xz, shape_zx, terminal_cell_flat,
                                safe_level_m, safe_volume_m3, seconds_edges_s,
                                time_edge_volume_m3, time_edge_level_m,
                                source_files, lake_bed_cell_count, active_cell_count):
    """Adapt the delivered finite-sample evidence into an explicit event receiver record.

    Everything the record asserts is copied out of the product (its own safe level, safe
    volume, clock, per-edge lake state and source digests); nothing is inferred from a
    ``retained`` label here, and a record missing any of it is refused rather than emitted
    with a weaker claim.

    The claim is deliberately small: it says this cell is an **event receiver** that the
    named product actually stored water in, within the stated safe range and time edges. It
    never says the cell is a permanent terminal.
    """
    if not isinstance(source_files, dict) or not source_files:
        raise ValueError("%s: source_files with sha256 digests are required"
                         % REASON_EVIDENCE_INSUFFICIENT)
    for name, sha in sorted(source_files.items()):
        if not isinstance(sha, str) or len(sha) != 64:
            raise ValueError("%s: source file %r has no 64-character sha256"
                             % (REASON_EVIDENCE_INSUFFICIENT, name))
    if not isinstance(product_schema, str) or not product_schema:
        raise ValueError("%s: the product schema is required" % REASON_EVIDENCE_INSUFFICIENT)
    if not isinstance(product_identity, str) or len(product_identity) != 64:
        raise ValueError("%s: the product identity digest is required"
                         % REASON_EVIDENCE_INSUFFICIENT)
    origin = [int(v) for v in np.asarray(origin_native_xz, np.int64).reshape(-1)]
    shape = [int(v) for v in np.asarray(shape_zx, np.int64).reshape(-1)]
    if len(origin) != 2 or len(shape) != 2:
        raise ValueError("%s: the product must declare a native origin and shape"
                         % REASON_EVIDENCE_INSUFFICIENT)
    edges = np.asarray(seconds_edges_s, np.float64).reshape(-1)
    if edges.size < 2 or np.any(np.diff(edges) <= 0.0):
        raise ValueError("%s: increasing physical time edges are required"
                         % REASON_EVIDENCE_INSUFFICIENT)
    volume = np.asarray(time_edge_volume_m3, np.float64).reshape(-1)
    level = np.asarray(time_edge_level_m, np.float64).reshape(-1)
    if volume.size != edges.size or level.size != edges.size:
        raise ValueError("%s: the lake ledger must be stored at every time edge"
                         % REASON_EVIDENCE_INSUFFICIENT)
    safe_level = _finite_float(safe_level_m, "safe_level_m")
    safe_volume = _finite_float(safe_volume_m3, "safe_volume_m3", minimum=0.0)
    if safe_volume <= 0.0:
        raise ValueError("%s: a zero safe volume is not an event receiver"
                         % REASON_EVIDENCE_INSUFFICIENT)
    if float(np.max(volume)) > safe_volume * (1.0 + 1e-12):
        raise ValueError("%s: the stored lake volume exceeds the declared safe volume"
                         % REASON_EVIDENCE_INSUFFICIENT)
    if float(np.max(level)) > safe_level * (1.0 + 1e-12):
        raise ValueError("%s: the stored lake level exceeds the declared safe level"
                         % REASON_EVIDENCE_INSUFFICIENT)
    filled = int((volume > 0.0).sum())
    if filled == 0:
        raise ValueError("%s: the product stores no water in this receiver at any edge"
                         % REASON_EVIDENCE_INSUFFICIENT)
    terminal_world = [int(v) for v in np.asarray(terminal_cell_world_native,
                                                 np.int64).reshape(-1)]
    if len(terminal_world) != 2:
        raise ValueError("%s: the matched terminal world cell is required"
                         % REASON_EVIDENCE_INSUFFICIENT)
    return {
        "kind": "finite_event_lake_storage",
        "is_event_receiver": True,
        "is_permanent_terminal": False,
        "claim_scope": ("stored water in this cell within the product's declared safe level, "
                        "safe volume and time edges only; no permanent outlet is claimed"),
        "product_schema": product_schema,
        "product_identity_sha256": product_identity,
        "product_origin_native_xz": origin,
        "product_shape_zx": shape,
        "product_terminal_cell_flat": _strict_int(terminal_cell_flat, "terminal_cell_flat",
                                                  minimum=0),
        "matched_terminal_world_native": terminal_world,
        "safe_level_m": safe_level,
        "safe_volume_m3": safe_volume,
        "supported_time_edges_s": [float(v) for v in edges],
        "stored_volume_m3_at_edges": [float(v) for v in volume],
        "stored_level_m_at_edges": [float(v) for v in level],
        "edges_with_stored_water": filled,
        "time_edges_without_water": [float(v) for v in edges[volume <= 0.0]],
        "lake_bed_cell_count": _strict_int(lake_bed_cell_count, "lake_bed_cell_count",
                                           minimum=1),
        "active_cell_count": _strict_int(active_cell_count, "active_cell_count", minimum=1),
        "source_files_sha256": {str(k): str(v) for k, v in sorted(source_files.items())},
        "outside_supported_range": "refuse",
    }


def event_receiver_identity(record):
    """The identity of the **one** receiving lake a record describes.

    Several reaches can end in the same lake: a terminal cell may receive more than one
    channel tail, so more than one reach legitimately references the same receiver evidence.
    What must never happen is two reaches claiming **different** lakes, or the same lake with
    contradictory bounds. The identity therefore keys on the product plus the matched
    terminal cell and the safe envelope; the referencing reach count is not part of it.
    """
    if not isinstance(record, dict):
        raise ValueError("%s: an event receiver record must be a mapping"
                         % REASON_EVIDENCE_INSUFFICIENT)
    return (record.get("kind"), record.get("product_schema"),
            record.get("product_identity_sha256"),
            tuple(record.get("product_origin_native_xz") or ()),
            tuple(record.get("matched_terminal_world_native") or ()),
            record.get("safe_level_m"), record.get("safe_volume_m3"),
            tuple(record.get("supported_time_edges_s") or ()),
            tuple(sorted((record.get("source_files_sha256") or {}).items())))


def permanent_terminal_pending():
    """The only permanent terminal this layer may emit.

    A support edge, a ``retained`` interior terminal, an ``unknown_boundary`` cut and a node
    that still has a downstream are all *not* terminal evidence. Emitting any of them as an
    ocean mouth or a world endorheic root is the mistake this function exists to prevent.
    """
    return {"kind": "pending", "reason": "no_trusted_land_sea_or_world_basin_evidence",
            "is_permanent_terminal": False}


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _reach_id(payload_base, root_world_xz, path_sha256):
    payload = dict(payload_base)
    payload["root_world_xz"] = [int(root_world_xz[0]), int(root_world_xz[1])]
    payload["world_path_sha256"] = path_sha256
    return "rb-" + hashlib.sha256(digest(payload).encode("utf-8")).hexdigest()


def build_backbone(*, parent, quantities, a_min_cells=DEFAULT_A_MIN_CELLS,
                   q_min_m3_s=DEFAULT_Q_MIN_M3_S, time_edges_s, event_receiver=None,
                   side_inputs=None, max_cells=MAX_SUPPORT_CELLS,
                   max_reaches=MAX_REACHES):
    """Build one OR-gated backbone over a parent B1 bundle.

    ``quantities`` maps a declared quantity name to ``{"local_flux": [steps, z, x],
    "available_mask": [z, x], "gate_time_index": int, "provenance": dict}``. Every quantity
    shares the one ``time_edges_s`` clock; a steady estimate is the caller's constant across
    those edges.

    ``side_inputs`` optionally declares one branch-resolution rule per quantity:
    ``{"quantity": name, "mode": "aggregated"|"refined", "max_branches": int}``. The
    branches are the non-channel cells that carry that quantity's local input; each is
    resolved to **one** side-input slot (see ``resolve_side_input``) and the record -- entry
    cell, member digest, the chosen source and the deliberate double count -- is stored so an
    independent reader can re-solve it. A build with ``side_inputs=None`` stores no
    replacement and says so rather than pretending the branches carry nothing.
    """
    view = parent_view(parent)
    shape = view["shape"]
    columns = shape[1]
    cells = int(shape[0] * shape[1])
    if cells > int(max_cells):
        raise ValueError("%s: %d cells outside the accumulation budget"
                         % (REASON_BUDGET, cells))
    receiver = view["receiver"]
    valid = view["valid_mask"]
    kinds = view["terminal_kind"]
    seeds = view["upstream_unknown_mask"]
    owner = view["owner_index"]

    edges = np.asarray(time_edges_s, np.float64).reshape(-1)
    if edges.size < 2 or edges.size > MAX_STEPS + 1 or np.any(np.diff(edges) <= 0.0):
        raise ValueError("%s: time_edges_s must be 2..%d increasing physical edges"
                         % (REASON_QUANTITY_MISMATCH, MAX_STEPS + 1))
    steps = int(edges.size - 1)

    area, area_complete = accumulate_area(receiver=receiver, valid_mask=valid,
                                          terminal_kind=kinds,
                                          upstream_unknown_mask=seeds, max_cells=max_cells)

    flux_report = {}
    gate_flux = {}
    payloads = {}
    for name in sorted(quantities):
        if name not in FLUX_QUANTITIES:
            raise ValueError("%s: %r is not a declared flux quantity"
                             % (REASON_QUANTITY_MISMATCH, name))
        spec = quantities[name] or {}
        local = _local_flux_block(spec.get("local_flux"), valid, steps)
        available = _grid(np.asarray(spec.get("available_mask"), np.bool_),
                          "available_mask", np.dtype(np.bool_), shape)
        if np.any(local[:, ~available] != 0.0):
            raise ValueError("%s: %s carries flux on a cell it declares unavailable"
                             % (REASON_QUANTITY_MISMATCH, name))
        complete = quantity_complete(receiver=receiver, valid_mask=valid,
                                     terminal_kind=kinds, available_mask=available,
                                     parent_unknown_seed=seeds, max_cells=max_cells)
        flow, totals = accumulate_flux(receiver=receiver, valid_mask=valid,
                                       terminal_kind=kinds, local_flux=local,
                                       max_cells=max_cells)
        gate_index = _strict_int(spec.get("gate_time_index", steps - 1),
                                 "gate_time_index", minimum=0, maximum=steps - 1)
        gate_flux[name] = np.ascontiguousarray(flow[gate_index], np.float64)
        flux_report[name] = {
            "semantics": FLUX_QUANTITY_SEMANTICS[name],
            "status": QUANTITY_STATUS_AVAILABLE,
            "gate_time_index": gate_index,
            "gate_time_s": [float(edges[gate_index]), float(edges[gate_index + 1])],
            "steps": steps,
            "available_cells": int((available & valid).sum()),
            "unavailable_valid_cells": int((~available & valid).sum()),
            "complete_valid_cells": int((complete & valid).sum()),
            "pending_valid_cells": int((~complete & valid).sum()),
            "input_total_m3_s": [float(v) for v in totals["input_total_m3_s"]],
            "residual_m3_s": [float(v) for v in totals["residual_m3_s"]],
            "max_abs_residual_m3_s": float(np.max(np.abs(totals["residual_m3_s"]))),
            "provenance": dict(spec.get("provenance") or {}),
            "missing_input_policy": ("a cell without local input is seeded unknown and "
                                     "propagated downstream; it is never read as zero"),
        }
        payloads[name] = {"flow": flow, "complete": complete, "local": local,
                          "available": available}

    gate_mask, a_gate, q_gate, per_quantity_gate = channel_gates(
        valid_mask=valid, area_cells=area, gate_flux=gate_flux,
        a_min_cells=a_min_cells, q_min_m3_s=q_min_m3_s,
        available={name: payload["available"] for name, payload in payloads.items()})
    # The gate is a property selection; the reaches can only be built on cells that have a
    # receiver. A structural terminal that passes the gate is kept as an explicit anchor,
    # never segmented and never silently dropped.
    channel_mask, gate_terminal_mask = routable_channel(gate_mask=gate_mask,
                                                        receiver=receiver)
    segmentation = segment_on_channel(receiver=receiver, valid_mask=valid,
                                      channel_mask=channel_mask, max_reaches=max_reaches)
    chains = segmentation["chains"]
    flat_reach = segmentation["reach_of_cell"]
    downstream, ends = reach_downstream(receiver=receiver, chains=chains,
                                        terminal_kind=kinds)
    # one derivation only: the reach rows read the reason from here
    end_of_reach = {item["reach_index"]: item for item in ends}

    reach_count = len(chains)
    reach_ptr = np.zeros(reach_count + 1, np.int64)
    np.cumsum(np.asarray([len(chain) for chain in chains], np.int64), out=reach_ptr[1:])
    reach_cells = (np.concatenate([np.asarray(chain, np.int64) for chain in chains])
                   if chains else np.zeros(0, np.int64))
    node_count_total = int(reach_cells.size)

    flat_area = area.reshape(-1)
    flat_area_complete = area_complete.reshape(-1)
    flat_rec = receiver.reshape(-1)
    flat_valid = valid.reshape(-1)
    flat_owner = owner.reshape(-1)
    flat_kinds = kinds.reshape(-1)

    # --- side inputs: one resolved slot per branch, never an inherited port field
    side_input_report = {}
    if side_inputs:
        if not isinstance(side_inputs, dict):
            raise ValueError("%s: side_inputs must be a mapping keyed by quantity"
                             % REASON_QUANTITY_MISMATCH)
        for name in sorted(side_inputs):
            if name not in payloads:
                raise ValueError("%s: a side-input rule names %r which has no declared input"
                                 % (REASON_QUANTITY_MISMATCH, name))
            rule = side_inputs[name] or {}
            mode = rule.get("mode", "refined")
            max_branches = _strict_int(rule.get("max_branches", DEFAULT_MAX_BRANCHES),
                                       "max_branches", minimum=1)
            payload = payloads[name]
            available_flat = payload["available"].reshape(-1)
            supply = valid.reshape(-1) & available_flat
            assigned = assign_local_branches(receiver=receiver, valid_mask=valid,
                                             channel_mask=channel_mask,
                                             supply_mask=supply.reshape(shape),
                                             origin_native_xz=view["origin_native_xz"])
            if len(assigned["branches"]) > max_branches:
                raise ValueError("%s: %d branches exceed the declared max_branches=%d; raise "
                                 "the rule or narrow the support instead of dropping branches"
                                 % (REASON_QUANTITY_MISMATCH, len(assigned["branches"]),
                                    max_branches))
            branches = sorted(assigned["branches"],
                              key=lambda branch: -branch["member_count"])
            rows = []
            for branch in branches:
                resolved = resolve_side_input(receiver=receiver, valid_mask=valid,
                                              branch=branch, local_flux=payload["local"],
                                              time_edges_s=edges, mode=mode)
                row = dict(resolved)
                row["member_cells"] = [int(v) for v in branch["member_cells"].tolist()]
                row["entry_cell_flat"] = int(branch["entry_cell_flat"])
                rows.append(row)
            side_input_report[name] = {
                "mode": mode,
                "max_branches": max_branches,
                "branch_count": len(assigned["branches"]),
                "assigned_cells": int(assigned["assigned_cells"]),
                "unassigned": assigned["unassigned"],
                "single_source_policy": ("each branch carries exactly one chosen source; the "
                                        "aggregated and refined forms are both reported but "
                                        "never both counted"),
                "inherited_port_field_used": False,
                "branches": rows,
            }

    handoff_pairs = np.zeros((reach_count, 2), np.int64)
    handoff_lengths = np.zeros(reach_count, np.float64)
    lengths = np.zeros(reach_count, np.float64)
    terminal_pairs = []
    for index, chain in enumerate(chains):
        tail = int(chain[-1])
        following = int(flat_rec[tail])
        lengths[index] = _chain_length_m(chain, columns, view["spacing_m"])
        # A routable channel cell always has a receiver by construction, so `following` is a
        # real cell: either the next channel cell, a structural terminal, or a cell that
        # simply failed the gate. The last two end the reach, and both are recorded.
        if following < 0:
            raise RuntimeError("%s: a routable channel cell lost its receiver"
                               % REASON_CHANNEL_RECEIVER_NOT_TERMINAL)
        handoff_pairs[index] = (tail, following)
        handoff_lengths[index] = _hop_length_m(tail, following, columns, view["spacing_m"])
        if downstream[index] < 0:
            terminal_pairs.append((tail, following))
    terminal_edge_pairs = (np.ascontiguousarray(
        np.asarray(terminal_pairs, np.int64).reshape(-1, 2), np.int64)
        if terminal_pairs else np.zeros((0, 2), np.int64))

    node_area = (flat_area[reach_cells] if node_count_total else np.zeros(0, np.int64))
    node_area_complete = (flat_area_complete[reach_cells] if node_count_total
                          else np.zeros(0, np.bool_))
    node_arrays = {}
    for name, payload in payloads.items():
        flow = payload["flow"].reshape(steps, -1)
        node_arrays["node_q_%s_m3_s" % name] = np.ascontiguousarray(
            flow[:, reach_cells] if node_count_total else np.zeros((steps, 0), np.float64))
        node_arrays["node_q_%s_complete" % name] = np.ascontiguousarray(
            payload["complete"].reshape(-1)[reach_cells] if node_count_total
            else np.zeros(0, np.bool_))

    local_index = np.ascontiguousarray(np.flatnonzero(flat_valid), np.int64)
    local_arrays = {}
    for name, payload in payloads.items():
        block = payload["local"].reshape(steps, -1)[:, local_index]
        local_arrays["local_input_%s_m3_s" % name] = np.ascontiguousarray(block, np.float64)
        local_arrays["local_input_%s_available" % name] = np.ascontiguousarray(
            payload["available"].reshape(-1)[local_index], np.bool_)

    payload_base = {
        "algorithm": ALGORITHM,
        "logical_version": LOGICAL_VERSION,
        "channel_rule": CHANNEL_RULE,
        "a_min_cells": _strict_int(a_min_cells, "a_min_cells", minimum=1),
        "q_min_m3_s": _finite_float(q_min_m3_s, "q_min_m3_s", minimum=0.0),
        "world_seed": view["world_seed"],
        "spacing_m": view["spacing_m"],
        "plan_version": view["plan_version"],
        "downstream_rule": DOWNSTREAM_RULE,
    }

    reach_rows = []
    for index, chain in enumerate(chains):
        head = int(chain[0])
        tail = int(chain[-1])
        root_index = int(flat_owner[head])
        world = _world_of(chain, view["origin_native_xz"], columns)
        path_sha = _sha_world_pairs(world)
        following = int(flat_rec[tail])
        terminal_reason = None
        if downstream[index] < 0:
            if int(flat_owner[following]) != root_index:
                raise ValueError("%s: reach %d drains into root %d but belongs to root %d"
                                 % (REASON_CROSS_ROOT_FLOW, index,
                                    int(flat_owner[following]), root_index))
            terminal_world = [int(v) for v in
                              _world_of([following], view["origin_native_xz"], columns)[0]]
            terminal_label = str(flat_kinds[following])
            terminal_reason = end_of_reach[index]["reason"]
        else:
            terminal_world = None
            terminal_label = None
        receiver_record = None
        if terminal_world is not None and event_receiver is not None:
            matched = (event_receiver.get("product_origin_native_xz")
                       == view["origin_native_xz"]
                       and event_receiver.get("matched_terminal_world_native") == terminal_world
                       and bool(flat_area_complete[following]))
            if matched and event_receiver.get("kind") == "finite_event_lake_storage":
                receiver_record = dict(event_receiver)
        root_world = [int(v) for v in _world_of([head], view["origin_native_xz"], columns)[0]]
        reach_rows.append({
            "reach_index": index,
            "reach_id": _reach_id(payload_base, root_world, path_sha),
            "root_index": root_index,
            "root_world_xz": root_world,
            "head_world_xz": [int(v) for v in world[0]],
            "tail_world_xz": [int(v) for v in world[-1]],
            "node_count": len(chain),
            "edges": len(chain) - 1,
            "length_m": float(lengths[index]),
            "handoff_length_m": float(handoff_lengths[index]),
            "reach_source": bool(int(segmentation["donors"][head]) == 0),
            "reach_donors": int(np.count_nonzero(downstream == index)),
            "downstream_reach_index": int(downstream[index]),
            "terminal_kind": terminal_label,
            "terminal_cell_world_xz": terminal_world,
            "terminal_reason": terminal_reason,
            "event_receiver": receiver_record,
            "permanent_terminal": (permanent_terminal_pending()
                                   if terminal_reason == "structural_terminal" else None),
            "world_path_sha256": path_sha,
            "area_status_at_tail": (AREA_STATUS_COMPLETE if bool(flat_area_complete[tail])
                                    else AREA_STATUS_PENDING),
            "area_status_at_head": (AREA_STATUS_COMPLETE if bool(flat_area_complete[head])
                                    else AREA_STATUS_PENDING),
            "area_cells_at_tail": int(flat_area[tail]),
            "area_m2_at_tail": float(int(flat_area[tail]) * CELL_AREA_M2),
            "display_line": None,
        })
    ids = [row["reach_id"] for row in reach_rows]
    for row in reach_rows:
        row["downstream_reach_id"] = (None if row["downstream_reach_index"] < 0
                                       else ids[row["downstream_reach_index"]])

    root_index_array = np.asarray([row["root_index"] for row in reach_rows], np.int64)
    root_rows = []
    for root_index in sorted(set(root_index_array.tolist())):
        own = [row for row in reach_rows if row["root_index"] == root_index]
        root_rows.append({
            "root_index": int(root_index),
            "root_world_xz": own[0]["root_world_xz"],
            "reach_count": len(own),
            "channel_cell_count": int(sum(row["node_count"] for row in own)),
            "terminal_edge_count": int(sum(1 for row in own
                                           if row["terminal_cell_world_xz"] is not None)),
            "terminal_kinds": sorted({row["terminal_kind"] for row in own
                                      if row["terminal_kind"] is not None}),
            "event_receiver_reaches": int(sum(1 for row in own
                                              if row["event_receiver"] is not None)),
        })

    arrays = {
        "receiver": np.ascontiguousarray(receiver, np.int64),
        "valid_mask": np.ascontiguousarray(valid, np.bool_),
        "terminal_kind": np.ascontiguousarray(kinds, TERMINAL_KIND_DTYPE),
        "upstream_unknown_mask": np.ascontiguousarray(seeds, np.bool_),
        "area_cells": np.ascontiguousarray(area, np.int64),
        "area_complete": np.ascontiguousarray(area_complete, np.bool_),
        "channel_mask": np.ascontiguousarray(channel_mask, np.bool_),
        "gate_mask": np.ascontiguousarray(gate_mask, np.bool_),
        "gate_terminal_mask": np.ascontiguousarray(gate_terminal_mask, np.bool_),
        "a_gate_mask": np.ascontiguousarray(a_gate, np.bool_),
        "q_gate_mask": np.ascontiguousarray(q_gate, np.bool_),
        "reach_of_cell": np.ascontiguousarray(flat_reach.reshape(shape), np.int64),
        "reach_ptr": reach_ptr,
        "reach_cells": np.ascontiguousarray(reach_cells, np.int64),
        "reach_downstream": np.ascontiguousarray(downstream, np.int64),
        "reach_head": np.asarray([int(chain[0]) for chain in chains], np.int64),
        "reach_tail": np.asarray([int(chain[-1]) for chain in chains], np.int64),
        "reach_root_index": np.ascontiguousarray(root_index_array, np.int64),
        "reach_source": np.asarray([row["reach_source"] for row in reach_rows], np.bool_),
        "reach_donors": np.asarray([row["reach_donors"] for row in reach_rows], np.int64),
        "reach_node_count": np.asarray([row["node_count"] for row in reach_rows], np.int64),
        "reach_length_m": np.ascontiguousarray(lengths, np.float64),
        "reach_handoff_length_m": np.ascontiguousarray(handoff_lengths, np.float64),
        "terminal_edge_pairs": np.ascontiguousarray(terminal_edge_pairs, np.int64),
        "handoff_edge_pairs": np.ascontiguousarray(handoff_pairs, np.int64),
        "node_area_cells": np.ascontiguousarray(node_area, np.int64),
        "node_area_complete": np.ascontiguousarray(node_area_complete, np.bool_),
        "local_input_index": local_index,
        "time_edges_s": np.ascontiguousarray(edges, np.float64),
    }
    arrays.update(node_arrays)
    arrays.update(local_arrays)

    counts = {
        "cells": cells,
        "valid_cells": int(valid.sum()),
        "inactive_cells": int((~valid).sum()),
        "a_gate_cells": int(a_gate.sum()),
        "q_gate_cells": int(q_gate.sum()),
        "q_gate_only_cells": int((q_gate & ~a_gate).sum()),
        "gate_cells": int(gate_mask.sum()),
        "gate_terminal_cells": int(gate_terminal_mask.sum()),
        "gate_cut_reaches": int(sum(1 for item in ends if item["reason"] == "gate_cut")),
        "structural_terminal_reaches": int(sum(
            1 for row in reach_rows if row["terminal_reason"] == "structural_terminal")),
        "channel_cells": int(segmentation["channel_cells"]),
        "reach_count": int(reach_count),
        "node_count_total": node_count_total,
        "terminal_edge_count": int(terminal_edge_pairs.shape[0]),
        "roots_with_channel": len(root_rows),
        "area_complete_cells": int(area_complete.sum()),
        "area_pending_cells": int((valid & ~area_complete).sum()),
        "q_gate_cells_by_quantity": per_quantity_gate,
        "q_gate_only_cells_by_quantity": {
            name: int((q_gate & ~a_gate).sum()) for name in sorted(gate_flux)},
        "event_receiver_reaches": int(sum(1 for row in reach_rows
                                          if row["event_receiver"] is not None)),
    }

    metadata = {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "logical_version": LOGICAL_VERSION,
        "parent_schema": view["schema"],
        "parent_identity_sha256": view["identity_sha256"],
        "support_identity_sha256": view["support_identity_sha256"],
        "world_seed": view["world_seed"],
        "spacing_m": view["spacing_m"],
        "plan_version": view["plan_version"],
        "origin_native_xz": list(view["origin_native_xz"]),
        "shape_zx": [int(shape[0]), int(shape[1])],
        "cell_area_m2": CELL_AREA_M2,
        "declared_gates": {
            "a_min_cells": payload_base["a_min_cells"],
            "q_min_m3_s": payload_base["q_min_m3_s"],
            "gate_policy": ("first-card configuration candidates, part of every reach "
                            "identity; not frozen physical thresholds"),
        },
        "clock": {"time_edges_s": [float(v) for v in edges], "steps": steps,
                  "semantics": ("interval i owns [edges[i], edges[i+1]); every declared flux "
                                "quantity shares this one clock")},
        "quantities": flux_report,
        "side_inputs": side_input_report,
        "side_input_policy": ("a branch is resolved to one side-input slot; aggregated and "
                              "refined are both computed and compared, and storing both "
                              "would double count the same supply"),
        "quantity_vocabulary": list(FLUX_QUANTITIES),
        "flux_availability": ("declared" if flux_report
                              else "not_available_pending: no flux input was declared for this "
                                   "build; the channel rests on the area gate alone and the "
                                   "area selection is kept"),
        "area_status_definition": {"complete": AREA_STATUS_COMPLETE,
                                   "pending": AREA_STATUS_PENDING,
                                   "unit": "cell_count_and_m2", "is_discharge": False},
        "flux_status_definition": {"available": QUANTITY_STATUS_AVAILABLE,
                                   "pending": QUANTITY_STATUS_PENDING, "unit": "m3/s"},
        "hydraulic_state": {
            "available": False,
            "reason": ("no water depth, stage or hydraulic state is produced in this layer; "
                       "a real routed event flux is physical water and is not a hydraulic "
                       "state"),
            "water_depth_m": "unavailable_no_hydraulic_state",
            "stage_m": "unavailable_no_hydraulic_state"},
        "channel_rule": CHANNEL_RULE,
        "segmentation_rule": SEGMENTATION_RULE,
        "reach_identity_policy": REACH_IDENTITY_POLICY,
        "downstream_rule": DOWNSTREAM_RULE,
        "terminal_policy": TERMINAL_POLICY,
        "display_line_policy": DISPLAY_LINE_POLICY,
        "local_q_policy": LOCAL_Q_POLICY,
        "status": ("topology_prepared" if segmentation["channel_cells"]
                   else "empty_network_no_channel"),
        "counts": counts,
        "reason_vocabulary": list(REASON_VOCABULARY),
        "limits": {
            "no_second_d8": True,
            "no_filling": True,
            "no_hydraulics": True,
            "no_permanent_terminal": True,
            "retained_is_not_a_lake": True,
            "unknown_boundary_is_not_an_outlet": True,
            "reach_count_is_not_river_count": True,
            "display_line_not_provided": True,
        },
    }
    identity = digest({"metadata": metadata,
                       "arrays": {name: array_hash(np.asarray(value))
                                  for name, value in sorted(arrays.items())}})
    return {
        "schema": SCHEMA,
        "parent": {"schema": view["schema"],
                   "identity_sha256": view["identity_sha256"],
                   "support_identity_sha256": view["support_identity_sha256"],
                   "plan_version": view["plan_version"]},
        "arrays": arrays,
        "reaches": reach_rows,
        "roots": root_rows,
        "metadata": metadata,
        "identity_sha256": identity,
    }


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #
def _rebuild_quantities(bundle):
    arrays = bundle["arrays"]
    shape = arrays["receiver"].shape
    edges = np.asarray(arrays["time_edges_s"], np.float64)
    steps = int(edges.size - 1)
    index = np.asarray(arrays["local_input_index"], np.int64)
    quantities = {}
    for name, report in bundle["metadata"]["quantities"].items():
        local_name = "local_input_%s_m3_s" % name
        available_name = "local_input_%s_available" % name
        if local_name not in arrays or available_name not in arrays:
            raise ValueError("the bundle does not store the %s local input" % name)
        grid = np.zeros((steps, int(shape[0] * shape[1])), np.float64)
        np.add.at(grid, (slice(None), index), np.asarray(arrays[local_name], np.float64))
        available = np.zeros(int(shape[0] * shape[1]), np.bool_)
        available[index] = np.asarray(arrays[available_name], np.bool_)
        quantities[name] = {
            "local_flux": grid.reshape((steps,) + shape),
            "available_mask": available.reshape(shape),
            "gate_time_index": int(report["gate_time_index"]),
            "provenance": report.get("provenance") or {},
        }
    return quantities


def _side_input_rules(bundle):
    """Recover the branch-resolution rules the bundle declares, for a rebuild."""
    recorded = bundle["metadata"].get("side_inputs") or {}
    if not isinstance(recorded, dict):
        raise ValueError("%s: the stored side_inputs record must be a mapping"
                         % REASON_QUANTITY_MISMATCH)
    rules = {}
    for name, record in recorded.items():
        if not isinstance(record, dict):
            raise ValueError("%s: the side-input record of %r must be a mapping"
                             % (REASON_QUANTITY_MISMATCH, name))
        rules[name] = {"mode": record.get("mode", "refined"),
                       "max_branches": int(record.get("max_branches", DEFAULT_MAX_BRANCHES))}
    return rules


def validate_backbone(bundle, parent):
    """Recompute the whole backbone from the parent and the stored inputs, then compare.

    A re-sealed reach row, a changed terminal, a forged gate or an edited node series is
    refused because every derived array, every reach row, the root rows and the whole
    metadata block are rebuilt rather than compared as digests only. This is the
    **explicit** verification entry; a cold load must not do this implicitly.
    """
    if not isinstance(bundle, dict) or set(bundle) != BUNDLE_KEYS:
        raise ValueError("a backbone bundle is %s" % sorted(BUNDLE_KEYS))
    if bundle["schema"] != SCHEMA:
        raise ValueError("unexpected backbone schema %r" % (bundle["schema"],))
    metadata = bundle["metadata"]
    if not isinstance(metadata, dict) or metadata.get("schema") != SCHEMA:
        raise ValueError("the backbone metadata must declare schema %r" % (SCHEMA,))
    view = parent_view(parent)
    if bundle["parent"] != {"schema": view["schema"],
                            "identity_sha256": view["identity_sha256"],
                            "support_identity_sha256": view["support_identity_sha256"],
                            "plan_version": view["plan_version"]}:
        raise ValueError("%s: the bundle is not bound to the parent it was built from"
                         % REASON_UNPREPARED)
    gates = metadata["declared_gates"]
    event_receiver_rows = [row for row in bundle["reaches"] if row.get("event_receiver")]
    # Several reaches may end in the **same** lake: one terminal cell can receive more than
    # one channel tail. That is one receiver with several references, not several lakes, and
    # no inflow reach is ever dropped to satisfy this check. What is refused is two reaches
    # claiming different lakes, or the same lake with contradictory evidence.
    identities = {event_receiver_identity(row["event_receiver"])
                  for row in event_receiver_rows}
    if len(identities) > 1:
        raise ValueError("%s: %d reaches reference %d different event receivers; a product may "
                         "declare one receiving lake"
                         % (REASON_EVIDENCE_INSUFFICIENT, len(event_receiver_rows),
                            len(identities)))
    event_receiver = (event_receiver_rows[0]["event_receiver"]
                      if event_receiver_rows else None)
    rebuilt = build_backbone(
        parent=parent,
        quantities=_rebuild_quantities(bundle),
        a_min_cells=gates["a_min_cells"],
        q_min_m3_s=gates["q_min_m3_s"],
        time_edges_s=np.asarray(bundle["arrays"]["time_edges_s"], np.float64),
        event_receiver=event_receiver,
        side_inputs=_side_input_rules(bundle),
    )
    stored = bundle["arrays"]
    rebuilt_arrays = rebuilt["arrays"]
    if set(stored) != set(rebuilt_arrays):
        raise ValueError("the backbone array names do not match the recomputation: %s"
                         % sorted(set(stored) ^ set(rebuilt_arrays)))
    for name in sorted(rebuilt_arrays):
        if not np.array_equal(np.asarray(stored[name]), np.asarray(rebuilt_arrays[name])):
            raise ValueError("the stored array %r does not agree with the recomputation" % name)
    if bundle["reaches"] != rebuilt["reaches"]:
        raise ValueError("the reach rows do not agree with the recomputation")
    if bundle["roots"] != rebuilt["roots"]:
        raise ValueError("the root rows do not agree with the recomputation")
    if metadata != rebuilt["metadata"]:
        differing = sorted(key for key in set(metadata) | set(rebuilt["metadata"])
                           if metadata.get(key) != rebuilt["metadata"].get(key))
        raise ValueError("the metadata does not agree with the recomputation; differing keys "
                         "%s" % differing)
    if bundle["identity_sha256"] != rebuilt["identity_sha256"]:
        raise ValueError("the backbone identity is not the identity of its own content")
    _assert_semantics(bundle, view)
    return None


def _assert_semantics(bundle, view):
    """Structural properties a reader must be able to trust, stated one by one."""
    arrays = bundle["arrays"]
    receiver = view["receiver"].reshape(-1)
    valid = view["valid_mask"].reshape(-1)
    channel = arrays["channel_mask"].reshape(-1)
    gate = arrays["gate_mask"].reshape(-1)
    gate_terminal = arrays["gate_terminal_mask"].reshape(-1)
    reach_of_cell = arrays["reach_of_cell"].reshape(-1)
    reach_count = int(np.asarray(arrays["reach_downstream"]).size)
    # The gate is a property selection; the channel is its routable half and the rest is kept
    # as selected terminal anchors. Both halves must reconstruct the gate exactly.
    if not np.array_equal(gate, channel | gate_terminal):
        raise ValueError("%s: gate_mask is not channel_mask | gate_terminal_mask"
                         % REASON_GATE_TERMINAL)
    if np.any(gate_terminal & (receiver >= 0)):
        raise ValueError("%s: a gate terminal anchor has a receiver" % REASON_GATE_TERMINAL)
    if not np.array_equal(reach_of_cell >= 0, channel):
        raise ValueError("%s: reach_of_cell does not cover exactly the declared channel"
                         % REASON_SEGMENT_COVERAGE)
    if reach_count and int(reach_of_cell.max()) >= reach_count:
        raise ValueError("%s: a cell points at a reach index that does not exist"
                         % REASON_SEGMENT_COVERAGE)
    # A routable channel cell has a receiver by construction (routable_channel); this states it.
    if np.any(channel & (receiver < 0)):
        raise ValueError("%s: a routable channel cell has no receiver"
                         % REASON_CHANNEL_RECEIVER_NOT_TERMINAL)
    if np.any(reach_of_cell[~valid] >= 0):
        raise ValueError("%s: an inactive cell belongs to a reach" % REASON_SEGMENT_COVERAGE)
    pointer = np.asarray(arrays["reach_ptr"], np.int64)
    if pointer.size != reach_count + 1 or int(pointer[0]) != 0:
        raise ValueError("%s: reach_ptr must hold one entry per reach plus a zero"
                         % REASON_SEGMENT_COVERAGE)
    if reach_count and np.any(np.diff(pointer) < 1):
        raise ValueError("%s: a reach carries no cell" % REASON_SEGMENT_COVERAGE)
    cells = np.asarray(arrays["reach_cells"], np.int64)
    if int(pointer[-1]) != int(cells.size):
        raise ValueError("%s: reach_ptr does not close over reach_cells"
                         % REASON_SEGMENT_COVERAGE)
    if np.unique(cells).size != cells.size:
        raise ValueError("%s: a channel cell appears in two reaches" % REASON_SEGMENT_COVERAGE)
    nodes = int(cells.size)
    for name in ("node_area_cells", "node_area_complete"):
        if int(np.asarray(arrays[name]).size) != nodes:
            raise ValueError("the node array %r is not aligned with reach_cells" % name)
    steps = int(np.asarray(arrays["time_edges_s"]).size - 1)
    for name, value in arrays.items():
        if name.startswith("node_q_") and name.endswith("_m3_s"):
            if value.shape != (steps, nodes):
                raise ValueError("the node flux series %r must be [steps, nodes]" % name)
    for index in range(reach_count):
        chain = cells[int(pointer[index]):int(pointer[index + 1])]
        for first, second in zip(chain[:-1], chain[1:]):
            if int(receiver[first]) != int(second):
                raise ValueError("%s: reach %d is not an unbroken receiver chain"
                                 % (REASON_SEGMENT_COVERAGE, index))
        downstream_index = int(np.asarray(arrays["reach_downstream"])[index])
        following = int(receiver[chain[-1]])
        if following < 0:
            raise ValueError("%s: a routable channel tail has no receiver"
                             % REASON_CHANNEL_RECEIVER_NOT_TERMINAL)
        if downstream_index < 0:
            if int(reach_of_cell[following]) >= 0:
                raise ValueError("%s: reach %d claims an end but drains into reach %d"
                                 % (REASON_TERMINAL_EDGE_MISSING, index,
                                    int(reach_of_cell[following])))
        else:
            if int(reach_of_cell[following]) != downstream_index:
                raise ValueError("%s: reach %d downstream is not the owner of its tail's "
                                 "receiver" % (REASON_TERMINAL_EDGE_MISSING, index))
    for row in bundle["reaches"]:
        terminal = row.get("permanent_terminal")
        if terminal is not None and terminal.get("kind") != "pending":
            raise ValueError("%s: this layer may only emit a pending permanent terminal"
                             % REASON_EVIDENCE_INSUFFICIENT)
        record = row.get("event_receiver")
        if record is not None:
            if record.get("kind") != "finite_event_lake_storage":
                raise ValueError("%s: an undeclared receiver kind"
                                 % REASON_EVIDENCE_INSUFFICIENT)
            if record.get("is_permanent_terminal"):
                raise ValueError("%s: an event receiver is never a permanent terminal"
                                 % REASON_EVIDENCE_INSUFFICIENT)
            if not record.get("source_files_sha256"):
                raise ValueError("%s: an event receiver must cite its product sources"
                                 % REASON_EVIDENCE_INSUFFICIENT)
    return None
