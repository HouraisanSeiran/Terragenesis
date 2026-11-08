"""Complete reach network over the B1 structural domain candidates.

What this layer is
------------------
B1 (``metric_world_domains``) answers *which structural terminal each cell drains to*
and publishes a closed, world-anchored candidate set. This module turns that set into
a **complete reach network**: every reach carries an explicit downstream reach, every
tributary joins the trunk step by step, and every root and every internal chain end has
a stable reason.

What it deliberately does not do
--------------------------------
No routing, no filling, no lake connection, no section width/depth, no hydraulics, no
sediment, and no water. The irregular graph receiver is the parent's -- this module never re-derives
it, never reroutes a cell, and never edits an edge to make a network look complete.
Cell *counts* inherited from the parent are diagnostics; they are never called
discharge. ``candidate_closed`` does not mean natural: a closed structural candidate is
still only a structural object, and a support edge is still not an outlet.

Why ``mountain_runoff_routing.build_reaches`` is not called
-----------------------------------------------------------
Measured on the real entry point (``terrain_pipeline/mountain_runoff_routing.py``,
``:84-160``), two of its declared gates contradict this layer:

1. ``not np.isfinite(height).all()`` refuses the **whole window**. A legal
   partially-covered B1 bundle keeps NaN on unresolved cells by policy
   (``metric_world_domains``' ``unresolved_policy``); handing it a filled height would
   present an unknown as terrain.
2. ``np.array_equal(flat_receiver == -1, outlets)`` requires **every** structural
   terminal to be declared an outlet. B1's ``retained`` and ``unknown_boundary`` are
   terminals of a finite graph, not sea outlets; adopting that gate is exactly the
   "window edge as sea" mistake this project has already paid for.

So this module performs the *thinnest* possible graph-chain partition -- one grouping
over the parent's existing receiver, no second irregular graph, no new hydraulics, no HRU or area
allocation -- and ``tests/test_metric_world_reaches.py`` compares its per-cell partition
against ``build_reaches`` on a synthetic input that *is* admissible to that backend
(finite heights, one HRU, ``receiver == -1`` exactly on the outlet mask), and asserts the
two inapplicabilities above rather than merely mentioning them.

Channel rule (the only selection in this layer)
-----------------------------------------------
``channel = resolved_mask & (receiver >= 0) & (upstream_cells >= min_upstream_cells)``

Upstream cell count is non-decreasing downstream along a irregular graph DAG, so a channel set closes
downstream by construction; nothing is ever appended to reach a terminal. A structural
terminal is never a channel cell (its receiver is ``-1``), so a reach can never be drawn
onto it: the last edge is stored separately in ``terminal_edge_pairs``. ``min_upstream_cells``
is a **declared display/channel-candidate gate**, not a physical threshold.

Segmentation
------------
A reach starts at a channel cell whose channel-donor count is not one (0 = source,
>= 2 = junction) and continues downstream while the next cell is a plain channel
continuation. A junction cell belongs to the downstream reach, so reaches are maximal and
vertex-disjoint. Legal one-cell source and confluence reaches are kept; a pure terminal
sentinel reach cannot arise here (terminals are not channel cells).

Identity
--------
``reach_id`` is derived from a world-anchored payload (algorithm, logical version, channel
rule, ``min_upstream_cells``, seed, spacing, ``plan_version``, the root's world ``(x,z)``,
the **ordered** world path digest and the downstream rule). It excludes the support
origin/shape, local flat indices, ``reach_index`` and page paths, so the same world reach
keeps its id when an unrelated basin is added to the support. The path order matters: the
digest is over the source-to-tail world sequence, never over a set.
"""
from __future__ import annotations

import hashlib
import importlib
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.surface_rivers.metric_world_domains import (
    MAX_SUPPORT_CELLS,
    REASON_ROOT_NOT_TERMINAL,
    validate_domain_candidates,
)

__all__ = [
    "ARRAY_NAMES",
    "BUNDLE_KEYS",
    "CHANNEL_RULE",
    "DEFAULT_MIN_UPSTREAM_CELLS",
    "LOGICAL_VERSION",
    "MAX_REACHES",
    "MAX_REACH_BYTES",
    "REACH_IDENTITY_POLICY",
    "REACH_KEYS",
    "REASON_BUDGET",
    "REASON_CHANNEL_RECEIVER_NOT_TERMINAL",
    "REASON_CROSS_ROOT_FLOW",
    "REASON_NO_CHANNEL_CELLS",
    "REASON_REACH_CYCLE",
    "REASON_SEGMENT_DONOR_MISMATCH",
    "REASON_TERMINAL_EDGE_DUPLICATE",
    "REASON_TERMINAL_EDGE_MISSING",
    "REASON_UNPREPARED",
    "ROOT_KEYS",
    "SCHEMA",
    "SEGMENTATION_RULE",
    "STATUS_COMPLETE",
    "STATUS_EMPTY",
    "build_world_reaches",
    "validate_world_reaches",
]


# --------------------------------------------------------------------------- #
# declared vocabulary, budgets and rules (all stated, none tuned)
# --------------------------------------------------------------------------- #
SCHEMA = "metric-world-reach-network-v1"
LOGICAL_VERSION = "b2-reach-network-irregular-v2"

#: Declared display/channel-candidate gate: a channel cell must carry at least this many
#: upstream cells (itself included). It is a **selection** for display and channel
#: candidates, not a physical threshold, and it is part of every reach identity.
DEFAULT_MIN_UPSTREAM_CELLS = 48

CHANNEL_RULE = (
    "channel = resolved_mask & (receiver >= 0) & (upstream_cells >= min_upstream_cells); "
    "upstream cell count is non-decreasing downstream, so a channel closes downstream by "
    "construction; a structural terminal is never a channel cell")

SEGMENTATION_RULE = (
    "a reach starts at a channel cell whose channel-donor count is not 1 (0 = source, "
    ">=2 = junction) and runs downstream while the next cell is a plain channel "
    "continuation; a junction cell belongs to the downstream reach, so reaches are "
    "maximal and vertex-disjoint; one-cell source and confluence reaches are kept and a "
    "pure terminal sentinel reach cannot arise")

REACH_IDENTITY_POLICY = (
    "reach_id = 'wr-' + sha256 over a world-anchored logical payload (algorithm, logical "
    "version, channel rule, min_upstream_cells, world seed, spacing, plan_version, the "
    "root's world (x,z), the ordered source-to-tail world path digest and the downstream "
    "rule). It excludes the support origin/shape, local flat indices, reach_index and page "
    "paths, so the same world reach keeps one id in a wider or narrower support; the path "
    "digest is over the ordered sequence and never over a set.")

DOWNSTREAM_RULE = (
    "reach_downstream is the reach that owns the receiver target of this reach's tail "
    "cell, or -1 when the tail drains into its structural terminal; a downstream reach is "
    "never inferred across a root boundary")

LOCAL_Q_POLICY = (
    "upstream cell counts are inherited from the parent domain bundle for diagnostics "
    "only; they are cell counts, not discharge, and this layer produces no water, no "
    "section geometry and no hydraulics")

#: Self-imposed ceilings of **this module**. They are new, explicitly declared B2 limits --
#: not a "same order as the old backend" argument (the old backend's 2048 is a different
#: quantity) and not a measured maximum scale. ``MAX_REACHES`` is additionally clamped to
#: the number of channel cells, so a real network can never approach it unnoticed.
MAX_REACHES = 32_768
#: An **estimate of the payload** (arrays plus per-reach metadata), not a resident-memory
#: ceiling: Python/numpy overhead, the parent bundle's own arrays and the caller's copies
#: all sit outside it, and the estimate is reported in ``metadata['budget']``.
MAX_REACH_BYTES = 256 * 1024 * 1024
_BYTES_PER_CELL = 8 + 8 + 8 + 8 + 1
_BYTES_PER_REACH = 8 * 6 + 1 + 8 + 8 + 8 + 64

REASON_NO_CHANNEL_CELLS = "no_channel_cells"
REASON_CHANNEL_RECEIVER_NOT_TERMINAL = "channel_receiver_not_terminal"
REASON_CROSS_ROOT_FLOW = "cross_root_flow"
REASON_REACH_CYCLE = "reach_cycle"
REASON_TERMINAL_EDGE_MISSING = "terminal_edge_missing"
REASON_TERMINAL_EDGE_DUPLICATE = "terminal_edge_duplicate"
REASON_SEGMENT_DONOR_MISMATCH = "segment_donor_mismatch"
REASON_HANDOFF_MISMATCH = "handoff_mismatch"
REASON_BUDGET = "budget_exceeded"
REASON_UNPREPARED = "unprepared"

REASON_VOCABULARY = (
    REASON_NO_CHANNEL_CELLS, REASON_CHANNEL_RECEIVER_NOT_TERMINAL,
    REASON_CROSS_ROOT_FLOW, REASON_REACH_CYCLE, REASON_TERMINAL_EDGE_MISSING,
    REASON_TERMINAL_EDGE_DUPLICATE, REASON_SEGMENT_DONOR_MISMATCH,
    REASON_HANDOFF_MISMATCH, REASON_BUDGET, REASON_UNPREPARED,
)

#: Topology only. A network is *prepared*, never a certified physical domain: the
#: channel is a declared display gate, the parent may be partially unknown, and nothing
#: here certifies a lake or a coast. ``whole_support_upstream_complete`` says separately
#: whether every parent cell was complete, so "prepared" can never be read as "complete".
STATUS_TOPOLOGY_PREPARED = "topology_prepared"
STATUS_EMPTY = "empty_network_no_channel"

#: ``terminal_edge_pairs`` is a **directed** set: pair ``(a, b)`` means the flow leaves
#: ``a`` into ``b``. It is ordered deterministically but its two columns are never swapped,
#: and de-duplication is by the ordered edge only. ``handoff_edge_pairs`` is row-aligned
#: with the reach index (row *i* is reach *i*'s own outgoing edge) and is likewise never
#: reversed.
EDGE_POLICY = (
    "edge pairs are directed (source, target): the two columns are never swapped and "
    "de-duplication is by the ordered edge; terminal_edge_pairs is ordered "
    "deterministically, handoff_edge_pairs is row-aligned with the reach index")

BUNDLE_KEYS = {"schema", "parent", "arrays", "reaches", "roots", "metadata",
               "identity_sha256"}

ARRAY_NAMES = (
    "reach_of_cell", "reach_ptr", "reach_cells", "reach_downstream", "reach_head",
    "reach_tail", "reach_root_index", "reach_source", "reach_donors",
    "terminal_edge_pairs", "handoff_edge_pairs", "mainstem_reach_mask",
    "reach_length_m", "reach_handoff_length_m", "reach_node_count", "reach_edges",
)

REACH_KEYS = (
    "reach_id", "reach_index", "root_index", "root_world_xz", "head_world_xz",
    "tail_world_xz", "node_count", "edges", "length_m", "handoff_length_m",
    "reach_source", "reach_donors", "downstream_reach_index", "downstream_reach_id",
    "terminal_kind", "terminal_root_world_xz", "terminal_cell_world_xz",
    "terminal_physical_endpoint_evidence", "world_path_sha256", "on_mainstem",
)

ROOT_KEYS = (
    "root_index", "root_world_xz", "root_kind", "status", "upstream_complete",
    "channel_cell_count", "reach_count", "tributary_reach_count",
    "terminal_edge_count", "channel_mainstem_reach_count", "channel_mainstem_length_m",
    "channel_mainstem_node_count", "channel_mainstem_edges",
    "channel_mainstem_channel_cell_count", "channel_mainstem_reach_ids",
    "raw_mainstem_node_count", "raw_mainstem_edges", "raw_mainstem_length_m",
    "raw_mainstem_reach_ids",
)

_SHA_CACHE = {}


# --------------------------------------------------------------------------- #
# validation helpers
# --------------------------------------------------------------------------- #
def _strict_int(value, name):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError("%s must be an integer, not a boolean" % name)
    if isinstance(value, (int, np.integer)):
        return int(value)
    raise ValueError("%s must be an integer, got %s" % (name, type(value).__name__))


def _grid(array, name, dtype, shape=None):
    if not isinstance(array, np.ndarray) or array.dtype != np.dtype(dtype) \
            or array.ndim != 2 or min(array.shape) < 1:
        raise ValueError("%s must be a non-empty %s [Z,X] array" % (name, dtype))
    if shape is not None and array.shape != shape:
        raise ValueError("%s must have shape %s, got %s"
                         % (name, list(shape), list(array.shape)))
    return np.ascontiguousarray(array)


def _vector(array, name, dtype, minimum=0):
    if not isinstance(array, np.ndarray) or array.dtype != np.dtype(dtype) \
            or array.ndim != 1 or array.size < minimum:
        raise ValueError("%s must be a %s vector of length >= %d" % (name, dtype, minimum))
    return np.ascontiguousarray(array)


def _sha_world_pairs(pairs):
    block = np.ascontiguousarray(np.asarray(pairs, np.int64).reshape(-1, 2), dtype="<i8")
    return hashlib.sha256(block.tobytes()).hexdigest()


def _world_of(flat, origin_native_xz, columns):
    flat = np.asarray(flat, np.int64)
    x = origin_native_xz[0] + (flat % columns)
    z = origin_native_xz[1] + (flat // columns)
    return np.stack([x, z], axis=1).astype(np.int64)


def _module_source_sha256(name):
    if name not in _SHA_CACHE:
        module = importlib.import_module(name)
        path = getattr(module, "__file__", None)
        _SHA_CACHE[name] = (hashlib.sha256(Path(path).read_bytes()).hexdigest()
                            if path and Path(path).is_file() else None)
    return _SHA_CACHE[name]


def _dependency_sha256():
    return {name: _module_source_sha256(name) for name in (
        "terrain_pipeline.surface_rivers.metric_world_reaches",
        "terrain_pipeline.surface_rivers.metric_world_domains",
        "terrain_pipeline.surface_rivers.native_30m_source",
        'terrain_pipeline.drainage',
        "terrain_pipeline.common_infra",
    )}


# --------------------------------------------------------------------------- #
# the parent: gate first, then read the declared arrays
# --------------------------------------------------------------------------- #
def _parent_view(parent_domain_bundle):
    """Validate the parent through the B1 gate, then expose its declared arrays.

    The parent is validated with ``metric_world_domains.validate_domain_candidates``
    before anything is read from it: a reach network built on a parent whose topology,
    ownership or completeness was re-sealed is refused at the source rather than exposed
    here.
    """
    if not isinstance(parent_domain_bundle, dict):
        raise ValueError("%s: the parent domain bundle must be a mapping" % REASON_UNPREPARED)
    try:
        validate_domain_candidates(parent_domain_bundle)
    except ValueError as error:
        raise ValueError("%s: the parent domain bundle does not pass the B1 gate: %s"
                         % (REASON_UNPREPARED, error)) from None
    arrays = parent_domain_bundle["arrays"]
    metadata = parent_domain_bundle["metadata"]
    shape = tuple(arrays["receiver"].shape)
    parent_identity = parent_domain_bundle["identity_sha256"]
    support = metadata["support"]
    return {
        "bundle": parent_domain_bundle,
        "identity_sha256": parent_identity,
        "schema": parent_domain_bundle["schema"],
        "shape": shape,
        "origin_native_xz": [int(support["origin_native_xz"][0]),
                             int(support["origin_native_xz"][1])],
        "world_seed": int(support["world_seed"]),
        "spacing_m": float(support["spacing_m"]),
        "plan_version": int(support["plan_version"]),
        "support_identity_sha256": metadata["support_identity_sha256"],
        "elevation_m": arrays["elevation_m"],
        "resolved_mask": arrays["resolved_mask"],
        "receiver": arrays["receiver"],
        "upstream_cells": arrays["upstream_cells"],
        "owner_index": arrays["owner_index"],
        "complete_mask": arrays["complete_mask"],
        "root_cells": arrays["root_cells"],
        "root_complete": arrays["root_complete"],
        "member_ptr": arrays["member_ptr"],
        "member_cells": arrays["member_cells"],
        "mainstem_ptr": arrays["mainstem_ptr"],
        "mainstem_cells": arrays["mainstem_cells"],
        "terminal_kind": arrays["terminal_kind"],
        "candidates": parent_domain_bundle["candidates"],
    }


# --------------------------------------------------------------------------- #
# segmentation: one grouping pass over the parent's receiver
# --------------------------------------------------------------------------- #
def _check_budget(cells, reach_bound):
    if reach_bound > MAX_REACHES:
        raise ValueError("%s: at most %d reaches fit the declared ceiling; this support "
                         "would need up to %d (raise the gate or split the support, do not "
                         "relax the budget in place)"
                         % (REASON_BUDGET, MAX_REACHES, reach_bound))
    estimate = cells * _BYTES_PER_CELL + reach_bound * _BYTES_PER_REACH
    if estimate > MAX_REACH_BYTES:
        raise ValueError("%s: the network needs about %d bytes (%d cells, %d reaches) but "
                         "the declared byte budget is %d"
                         % (REASON_BUDGET, estimate, cells, reach_bound,
                            MAX_REACH_BYTES))
    return estimate


def _segments(parent, min_upstream_cells):
    """Partition the declared channel into maximal, vertex-disjoint reaches."""
    rows, columns = parent["shape"]
    receiver = parent["receiver"].reshape(-1)
    resolved = parent["resolved_mask"].reshape(-1)
    upstream = parent["upstream_cells"].reshape(-1)
    owner = parent["owner_index"].reshape(-1)

    channel = resolved & (receiver >= 0) & (upstream >= min_upstream_cells)
    if np.any(channel & (receiver < 0)):
        raise RuntimeError("%s: a channel cell has no receiver" % REASON_CHANNEL_RECEIVER_NOT_TERMINAL)
    channel_cells = int(channel.sum())

    # Channel donors: how many *channel* cells feed each cell. One `bincount` for the
    # whole grid, so the cost does not depend on the reach or root count.
    source = np.flatnonzero(channel)
    target = receiver[source]
    donors = np.bincount(target, minlength=receiver.size).astype(np.int64)
    starts = np.flatnonzero(channel & (donors != 1))

    reach_of_cell = np.full(receiver.size, -1, np.int64)
    chains = []
    for start in starts.tolist():
        chain = [start]
        reach_of_cell[start] = len(chains)
        current = start
        while True:
            following = int(receiver[current])
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
        raise RuntimeError("%s: %d channel cells are outside every reach"
                           % (REASON_SEGMENT_DONOR_MISMATCH, channel_cells - covered))
    return {
        "channel": channel,
        "channel_cells": channel_cells,
        "donors": donors,
        "reach_of_cell": reach_of_cell,
        "chains": chains,
    }


def _downstream_and_terminals(parent, segmentation):
    """Explicit ``reach_downstream`` plus the last edge of every terminal reach.

    A channel tail's receiver is either another channel cell (so the reach hands off to
    the reach that owns it) or a **structural terminal** (``receiver == -1``, which is
    never a channel cell), in which case ``reach_downstream`` is ``-1`` and the edge is
    recorded in ``terminal_edge_pairs``. Any other case -- a receiver that is neither a
    channel cell nor a terminal -- means the channel was not downstream closed, and that
    is refused rather than patched by extending the reach.
    """
    receiver = parent["receiver"].reshape(-1)
    reach_of_cell = segmentation["reach_of_cell"]
    chains = segmentation["chains"]
    tails = [int(chain[-1]) for chain in chains]
    downstream = np.full(len(chains), -1, np.int64)
    crossing = []
    edges = []
    for index, tail in enumerate(tails):
        following = int(receiver[tail])
        if following < 0:
            raise RuntimeError("%s: reach %d has a channel tail with no receiver"
                               % (REASON_CHANNEL_RECEIVER_NOT_TERMINAL, index))
        target = int(reach_of_cell[following])
        if target >= 0:
            downstream[index] = target
            continue
        if int(receiver[following]) >= 0:
            raise RuntimeError("%s: reach %d drains into cell %d, which is neither a "
                               "channel cell nor a structural terminal; the channel is not "
                               "downstream closed"
                               % (REASON_CHANNEL_RECEIVER_NOT_TERMINAL, index, following))
        edges.append((tail, following))
    # A cross-root edge is impossible in a self-consistent parent (owner is derived from
    # the receiver chain); if one appears it is reported, never repaired.
    owner = parent["owner_index"].reshape(-1)
    for index, (tail, following) in enumerate(edges):
        if int(owner[tail]) != int(owner[following]):
            crossing.append((index, tail, following))
    return {
        "downstream": downstream,
        "tails": tails,
        "terminal_edges": edges,
        "cross_root": crossing,
    }


def _reach_donors(segmentation, downstream_edges):
    """Upstream *reach* count per reach: cross-reach edges only."""
    chains = segmentation["chains"]
    donors = np.zeros(len(chains), np.int64)
    for index, target in enumerate(downstream_edges.tolist()):
        if target >= 0:
            donors[target] += 1
    return donors


def _parent_mesh(parent):
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    if "_metric_mesh" not in parent:
        spacing = parent["spacing_m"]
        origin = parent["origin_native_xz"]
        parent["_metric_mesh"] = grid_mesh(parent["shape"],
            x0_m=origin[0] * spacing, z0_m=origin[1] * spacing,
            dx_m=spacing, world_seed=parent["world_seed"])
    return parent["_metric_mesh"]


def _reach_lengths(parent, chains):
    """Segment length in metres: the sum of the irregular graph hop lengths inside the reach.

    A reach of L cells carries L-1 intra-reach hops; the final hop into the structural
    terminal is **not** counted here, because it belongs to ``terminal_edge_pairs`` and
    this layer never draws a reach onto a terminal cell.
    """
    mesh = _parent_mesh(parent)
    receiver = parent["receiver"].reshape(-1)
    lengths = np.zeros(len(chains), np.float64)
    for index, chain in enumerate(chains):
        total = 0.0
        for cell in chain[:-1]:
            following = int(receiver[cell])
            total += math.hypot(mesh.node_x_m[cell] - mesh.node_x_m[following],
                                mesh.node_z_m[cell] - mesh.node_z_m[following])
        lengths[index] = total
    return lengths


def _reach_id(payload_base, root_world_xz, path_sha256, downstream_rule):
    """World-anchored logical identity of one reach."""
    payload = dict(payload_base)
    payload["root_world_xz"] = [int(root_world_xz[0]), int(root_world_xz[1])]
    payload["world_path_sha256"] = path_sha256
    payload["downstream_rule"] = downstream_rule
    return "wr-" + identity({}, payload)


def _directed_edges(pairs, parent):
    """Deterministic order for **directed** edges, without swapping the two columns.

    ``(source, target)`` is ordered by the source's world ``(x, z)`` then the target's,
    so two runs agree, but the columns are never exchanged: reversing an edge would
    describe a different flow. De-duplication is by the ordered edge only.
    """
    if not pairs:
        return np.zeros((0, 2), np.int64)
    edges = np.asarray(pairs, np.int64).reshape(-1, 2)
    world = np.concatenate(
        [_world_of(edges[:, 0], parent["origin_native_xz"], parent["shape"][1]),
         _world_of(edges[:, 1], parent["origin_native_xz"], parent["shape"][1])], axis=1)
    order = np.lexsort((world[:, 3], world[:, 2], world[:, 1], world[:, 0]))
    ordered = edges[order]
    seen = set()
    unique = []
    for edge in ordered.tolist():
        key = (edge[0], edge[1])
        if key in seen:
            raise ValueError("%s: the directed edge %s appears twice"
                             % (REASON_TERMINAL_EDGE_DUPLICATE, key))
        seen.add(key)
        unique.append(edge)
    return np.ascontiguousarray(np.asarray(unique, np.int64).reshape(-1, 2), np.int64)


def _hop_length_m(parent, first, second):
    mesh = _parent_mesh(parent)
    return math.hypot(mesh.node_x_m[first] - mesh.node_x_m[second],
                      mesh.node_z_m[first] - mesh.node_z_m[second])


def _handoffs(parent, chains, downstream, tails):
    """One outgoing edge per reach: into the next reach's head, or into its terminal.

    Every selected channel cell has exactly one receiver edge, and every one of those
    edges is accounted for exactly once: either it is *internal* to its reach (both ends
    in the same reach) or it is a *handoff* (tail of the reach into the next reach's head,
    or tail into the structural terminal). ``internal_edges == node_count - 1`` and the
    per-reach handoff length is the length of that single edge -- so for a one-cell reach
    the internal length is 0 while its handoff is still 30 m (or 42.43 m diagonally).
    """
    receiver = parent["receiver"].reshape(-1)
    edges = []
    lengths = np.zeros(len(chains), np.float64)
    for index, chain in enumerate(chains):
        tail = tails[index]
        following = int(receiver[tail])
        if following < 0:
            raise RuntimeError("%s: a channel tail has no receiver"
                               % REASON_CHANNEL_RECEIVER_NOT_TERMINAL)
        if downstream[index] >= 0:
            expected = int(chains[int(downstream[index])][0])
            if following != expected:
                raise RuntimeError("%s: reach %d hands off to %d but the downstream reach "
                                   "starts at %d"
                                   % (REASON_HANDOFF_MISMATCH, index, following, expected))
        edges.append((tail, following))
        lengths[index] = _hop_length_m(parent, tail, following)
    return edges, lengths


def _build(parent, min_upstream_cells):
    """The single path both ``build_world_reaches`` and validation go through."""
    rows, columns = parent["shape"]
    cells = rows * columns
    if cells > MAX_SUPPORT_CELLS:
        raise ValueError("%s: %d cells exceeds the declared support ceiling %d"
                         % (REASON_BUDGET, cells, MAX_SUPPORT_CELLS))
    segmentation = _segments(parent, min_upstream_cells)
    chains = segmentation["chains"]
    reach_count = len(chains)
    # A real network can never carry more reaches than channel cells; the cell count is
    # therefore the honest bound handed to the budget check.
    _check_budget(cells, max(min(reach_count, segmentation["channel_cells"]), 1))

    linkage = _downstream_and_terminals(parent, segmentation)
    downstream = linkage["downstream"]
    donors = _reach_donors(segmentation, downstream)
    cell_donors = segmentation["donors"]
    lengths = _reach_lengths(parent, chains)
    handoff_edges, handoff_lengths = _handoffs(parent, chains, downstream, linkage["tails"])

    receiver = parent["receiver"].reshape(-1)
    owner = parent["owner_index"].reshape(-1)
    reach_of_cell = segmentation["reach_of_cell"]
    terminal_kind = parent["terminal_kind"].reshape(-1)
    world_flat = _world_of(np.arange(cells, dtype=np.int64),
                          parent["origin_native_xz"], columns)

    # The trunks are resolved **before** the reach rows are written, because trunk
    # membership is defined by the parent's ordered path rather than by a set of cells.
    trunks, on_trunk = _trunks(parent, segmentation, linkage, min_upstream_cells)

    payload_base = {
        "algorithm": "metric-world-reach",
        "logical_version": LOGICAL_VERSION,
        "channel_rule": CHANNEL_RULE,
        "min_upstream_cells": int(min_upstream_cells),
        "world_seed": parent["world_seed"],
        "spacing_m": parent["spacing_m"],
        "plan_version": parent["plan_version"],
    }
    root_world = [tuple(int(value) for value in candidate["root_world_xz"])
                  for candidate in parent["candidates"]]

    reach_rows = []
    for index, chain in enumerate(chains):
        head = int(chain[0])
        tail = int(chain[-1])
        root_index = int(owner[head])
        path = _world_of(np.asarray(chain, np.int64), parent["origin_native_xz"], columns)
        path_sha = _sha_world_pairs(path)
        following = int(receiver[tail])
        if downstream[index] < 0:
            if following < 0:
                raise RuntimeError("%s: a terminal reach ends on a terminal cell"
                                   % REASON_CHANNEL_RECEIVER_NOT_TERMINAL)
            terminal_cell = following
            if int(owner[terminal_cell]) != root_index:
                raise ValueError("%s: reach %d drains into root %d but belongs to root %d"
                                 % (REASON_CROSS_ROOT_FLOW, index,
                                    int(owner[terminal_cell]), root_index))
            terminal_world = [int(world_flat[terminal_cell, 0]),
                              int(world_flat[terminal_cell, 1])]
            terminal_label = str(terminal_kind[terminal_cell])
            evidence = parent["candidates"][root_index]["physical_endpoint_evidence"]
            downstream_index = -1
            downstream_id = None
        else:
            downstream_index = int(downstream[index])
            terminal_world = None
            terminal_label = None
            evidence = None
            downstream_id = None      # filled in a second pass, once ids are known
        reach_rows.append({
            "reach_index": index,
            "root_index": root_index,
            "root_world_xz": list(root_world[root_index]),
            "head_world_xz": [int(path[0, 0]), int(path[0, 1])],
            "tail_world_xz": [int(path[-1, 0]), int(path[-1, 1])],
            "node_count": len(chain),
            "edges": len(chain) - 1,
            "length_m": float(lengths[index]),
            "handoff_length_m": float(handoff_lengths[index]),
            # A reach is a *source* when its head has no channel donor at all -- a cell
            # count, not a reach count; `reach_donors` below is the segment count.
            "reach_source": bool(int(cell_donors[head]) == 0),
            "reach_donors": int(donors[index]),
            "downstream_reach_index": downstream_index,
            "terminal_kind": terminal_label,
            "terminal_root_world_xz": terminal_world,
            "terminal_cell_world_xz": (None if terminal_world is None
                                       else list(terminal_world)),
            "terminal_physical_endpoint_evidence": evidence,
            "world_path_sha256": path_sha,
            "on_mainstem": bool(on_trunk[index]),
            "reach_id": _reach_id(payload_base, root_world[root_index], path_sha,
                                   DOWNSTREAM_RULE),
        })

    identifiers = [row["reach_id"] for row in reach_rows]
    for row in reach_rows:
        index = row["downstream_reach_index"]
        row["downstream_reach_id"] = None if index < 0 else identifiers[index]

    reach_ptr = np.zeros(reach_count + 1, np.int64)
    np.cumsum(np.array([len(chain) for chain in chains], np.int64), out=reach_ptr[1:])
    reach_cells = (np.concatenate([np.asarray(chain, np.int64) for chain in chains])
                   if chains else np.zeros(0, np.int64))

    terminal_edges = linkage["terminal_edges"]
    pairs_local = _directed_edges(terminal_edges, parent)

    arrays = {
        "reach_of_cell": np.ascontiguousarray(reach_of_cell.reshape(rows, columns), np.int64),
        "reach_ptr": reach_ptr,
        "reach_cells": np.ascontiguousarray(reach_cells, np.int64),
        "reach_downstream": np.ascontiguousarray(downstream, np.int64),
        "reach_head": np.asarray([int(chain[0]) for chain in chains], np.int64),
        "reach_tail": np.asarray([int(chain[-1]) for chain in chains], np.int64),
        "reach_root_index": np.asarray([row["root_index"] for row in reach_rows], np.int64),
        "reach_source": np.asarray([row["reach_source"] for row in reach_rows], bool),
        "reach_donors": np.ascontiguousarray(donors, np.int64),
        "terminal_edge_pairs": pairs_local,
        # Row *i* is reach *i*'s own outgoing edge, so the two arrays stay aligned and the
        # row order is the (deterministic) reach order. Columns are never swapped.
        "handoff_edge_pairs": np.ascontiguousarray(
            np.asarray(handoff_edges, np.int64).reshape(-1, 2), np.int64),
        "mainstem_reach_mask": np.asarray([row["on_mainstem"] for row in reach_rows], bool),
        "reach_length_m": np.ascontiguousarray(lengths, np.float64),
        "reach_handoff_length_m": np.ascontiguousarray(handoff_lengths, np.float64),
        "reach_node_count": np.asarray([row["node_count"] for row in reach_rows], np.int64),
        "reach_edges": np.asarray([row["edges"] for row in reach_rows], np.int64),
    }

    root_rows = _root_rows(parent, reach_rows, segmentation, terminal_edges, trunks)
    status = (STATUS_TOPOLOGY_PREPARED if segmentation["channel_cells"]
              else STATUS_EMPTY)
    reasons = [] if segmentation["channel_cells"] else [REASON_NO_CHANNEL_CELLS]
    if linkage["cross_root"]:
        raise ValueError("%s: %d terminal edges cross a root boundary"
                         % (REASON_CROSS_ROOT_FLOW, len(linkage["cross_root"])))

    metadata = _metadata(parent, min_upstream_cells, arrays, reach_rows, root_rows,
                         segmentation, status, reasons)
    return arrays, reach_rows, root_rows, metadata


def _ordered_trunk(parent, segmentation, linkage, root_index):
    """The ordered source→root trunk of one root, mapped onto this layer's reaches.

    The order comes from the **parent's own ordered mainstem** (source→root), never from a
    set and never from a flat-index sort: a set loses the flow order, and a flat sort
    reverses it on a northward or westward trunk (the exact error this function exists to
    avoid). Cells outside the declared channel are dropped, then consecutive duplicates
    are collapsed, which yields the ordered reach sequence of the trunk.

    The result is verified against the reach graph: every adjacent pair must be exactly
    the handoff of the earlier reach into the later one, and the last reach must hand off
    into this root's structural terminal. A trunk that does not satisfy that is refused
    instead of being drawn as a chain.
    """
    low = int(parent["mainstem_ptr"][root_index])
    high = int(parent["mainstem_ptr"][root_index + 1])
    ordered_cells = [int(cell) for cell in parent["mainstem_cells"][low:high]]
    if not ordered_cells:
        raise RuntimeError("%s: root %d has no parent mainstem" % (REASON_UNPREPARED, root_index))
    root_cell = int(parent["root_cells"][root_index])
    if ordered_cells[-1] != root_cell:
        raise RuntimeError("%s: the parent mainstem of root %d does not end at its root"
                           % (REASON_ROOT_NOT_TERMINAL, root_index))
    reach_of_cell = segmentation["reach_of_cell"]
    channel = segmentation["channel"]
    trunk_cells = [cell for cell in ordered_cells if bool(channel[cell])]
    sequence = []
    for cell in trunk_cells:
        reach_index = int(reach_of_cell[cell])
        if reach_index < 0:
            raise RuntimeError("%s: a channel trunk cell belongs to no reach"
                               % REASON_SEGMENT_DONOR_MISMATCH)
        if not sequence or sequence[-1] != reach_index:
            sequence.append(reach_index)
    receiver = parent["receiver"].reshape(-1)
    downstream = linkage["downstream"]
    for first, second in zip(sequence[:-1], sequence[1:]):
        if int(downstream[first]) != second:
            raise RuntimeError("%s: trunk of root %d walks reach %d then %d, but %d "
                               "hands off to %d"
                               % (REASON_HANDOFF_MISMATCH, root_index, first, second,
                                  first, int(downstream[first])))
    if sequence and int(downstream[sequence[-1]]) >= 0:
        raise RuntimeError("%s: the trunk of root %d ends at reach %d, which hands off "
                           "further instead of into the terminal"
                           % (REASON_TERMINAL_EDGE_MISSING, root_index, sequence[-1]))
    # Length is taken directly along the ordered parent path, so it does not depend on
    # any per-reach bookkeeping: S channel cells plus the terminal cell give S hops.
    path = trunk_cells + [root_cell]
    length = _chain_length_m(parent, path)
    return {
        "root_index": int(root_index),
        "channel_cells": trunk_cells,
        "reaches": sequence,
        "terminal_cell": root_cell,
        "length_m": float(length),
    }


def _trunks(parent, segmentation, linkage, threshold):
    """One ordered trunk per root, plus the per-reach trunk membership."""
    trunks = {}
    on_trunk = np.zeros(len(segmentation["chains"]), bool)
    for index in range(int(parent["root_cells"].size)):
        trunk = _ordered_trunk(parent, segmentation, linkage, index)
        trunks[index] = trunk
        for reach_index in trunk["reaches"]:
            on_trunk[reach_index] = True
    return trunks, on_trunk


def _root_rows(parent, reach_rows, segmentation, terminal_edges, trunks):
    """One row per parent candidate -- complete or not, with a channel or without.

    Two mainstem reports are kept apart on purpose:

    * ``raw_mainstem_*`` describes the **parent's** trunk: the full source-to-root chain,
      including cells outside the declared channel (so a source cell below the gate is
      still part of the raw trunk).
    * ``channel_mainstem_*`` describes the trunk **inside** this selection: its reaches,
      their internal length plus their handoff edges, ending at the reach that hands off
      into the structural terminal.

    ``reach_count`` is the number of segments, and ``tributary_reach_count`` the segments
    that are not on the trunk. Neither is a count of independent rivers: a single river
    can be many segments, and two segments may belong to the same trunk.
    """
    rows = []
    chains = segmentation["chains"]
    root_count = int(parent["root_cells"].size)
    for index in range(root_count):
        candidate = parent["candidates"][index]
        cells = [row for row in reach_rows if row["root_index"] == index]
        trunk = trunks[index]
        sequence = list(trunk["reaches"])
        by_index = {row["reach_index"]: row for row in reach_rows}
        # **Node and edge counts follow the ordered with-terminal path**: S channel
        # reaches on the trunk plus the terminal give S+1 nodes and S edges. The pure
        # channel cell count is reported under its own name so neither number is read as
        # the other, and an empty trunk is 0/0/0 rather than an invented root.
        channel_cell_count = len(trunk["channel_cells"])
        if sequence:
            node_count = channel_cell_count + 1
            edges = channel_cell_count
            trunk_length = trunk["length_m"]
        else:
            node_count = 0
            edges = 0
            trunk_length = 0.0
        # The **raw** trunk is the parent's own complete source→root chain: its node count
        # is however many cells the parent put there, independent of the channel gate, so
        # a trunk whose source sits below the gate still reports its full length. An empty
        # channel therefore leaves the raw counts untouched while the channel counts are 0.
        raw_low = int(parent["mainstem_ptr"][index])
        raw_high = int(parent["mainstem_ptr"][index + 1])
        raw_node_count = raw_high - raw_low
        rows.append({
            "root_index": index,
            "root_world_xz": list(candidate["root_world_xz"]),
            "root_kind": candidate["root_kind"],
            "status": candidate["status"],
            "upstream_complete": bool(parent["root_complete"][index]),
            "channel_cell_count": int(sum(len(chains[row["reach_index"]])
                                          for row in cells)),
            "reach_count": len(cells),
            "tributary_reach_count": len(cells) - len(sequence),
            "terminal_edge_count": int(sum(
                1 for edge in terminal_edges
                if int(parent["owner_index"].reshape(-1)[edge[0]]) == index)),
            "channel_mainstem_reach_count": len(sequence),
            "channel_mainstem_length_m": float(trunk_length),
            "channel_mainstem_node_count": int(node_count),
            "channel_mainstem_edges": int(edges),
            "channel_mainstem_channel_cell_count": int(channel_cell_count),
            "channel_mainstem_reach_ids": [by_index[reach]["reach_id"]
                                           for reach in sequence],
            "raw_mainstem_node_count": int(raw_node_count),
            "raw_mainstem_edges": int(raw_node_count - 1),
            "raw_mainstem_length_m": float(_chain_length_m(
                parent, parent["mainstem_cells"]
                [int(parent["mainstem_ptr"][index]):int(parent["mainstem_ptr"][index + 1])])),
            "raw_mainstem_reach_ids": [by_index[reach]["reach_id"] for reach in sequence],
        })
    return rows


def _chain_length_m(parent, cells):
    """Length of an arbitrary ordered parent chain, hop by hop (no terminal hop added)."""
    total = 0.0
    for first, second in zip(cells[:-1], cells[1:]):
        total += _hop_length_m(parent, int(first), int(second))
    return float(total)


def _raw_reach_ids(parent, segmentation, root_index):
    reach_of_cell = segmentation["reach_of_cell"]
    return [int(reach_of_cell[int(cell)]) for cell in parent["mainstem_cells"]
            [int(parent["mainstem_ptr"][root_index]):
             int(parent["mainstem_ptr"][root_index + 1])]
            if reach_of_cell[int(cell)] >= 0]


def _display_root(parent, rows):
    """The single root used for display: complete first, then the most members.

    Ties are broken on the world ``(x, z)`` of the root, so the choice is a pure function
    of the data and never "whichever looked best". A support with no complete root
    returns ``None`` rather than promoting an incomplete one.
    """
    complete = [index for index, candidate in enumerate(parent["candidates"])
                if candidate["status"] == "candidate_closed"]
    if not complete:
        return None
    ranked = sorted(complete, key=lambda index: (
        -int(parent["candidates"][index]["member_count"]),
        int(parent["candidates"][index]["root_world_xz"][0]),
        int(parent["candidates"][index]["root_world_xz"][1])))
    return int(ranked[0])


def _metadata(parent, min_upstream_cells, arrays, reach_rows, root_rows, segmentation,
              status, reasons):
    channel_cells = segmentation["channel_cells"]
    valid_cells = int(parent["resolved_mask"].sum())
    whole_complete = bool(parent["complete_mask"][parent["resolved_mask"]].all())
    terminal_edges = arrays["terminal_edge_pairs"]
    handoff_edges = arrays["handoff_edge_pairs"]
    counts = {
        "cells": int(parent["receiver"].size),
        "valid_cells": valid_cells,
        "inactive_cells": int((~parent["resolved_mask"]).sum()),
        "channel_cells": channel_cells,
        "unselected_valid_cells": valid_cells - channel_cells,
        "reach_count": len(reach_rows),
        "source_reach_count": sum(1 for row in reach_rows if row["reach_source"]),
        "single_cell_reach_count": sum(1 for row in reach_rows if row["node_count"] == 1),
        "terminal_edge_count": int(terminal_edges.shape[0]),
        "handoff_edge_count": int(handoff_edges.shape[0]),
        "mainstem_reach_count": sum(1 for row in reach_rows if row["on_mainstem"]),
        "node_count_total": int(sum(row["node_count"] for row in reach_rows)),
        "edges_total": int(sum(row["edges"] for row in reach_rows)),
        "length_m_total": float(sum(row["length_m"] for row in reach_rows)),
        "handoff_length_m_total": float(sum(row["handoff_length_m"]
                                             for row in reach_rows)),
        "roots_with_channel": sum(1 for row in root_rows if row["reach_count"]),
        "roots_without_channel": sum(1 for row in root_rows if not row["reach_count"]),
        "unknown_root_count": sum(1 for row in root_rows
                                  if row["root_kind"] == "unknown_boundary"),
        "incomplete_root_count": sum(1 for row in root_rows
                                     if not row["upstream_complete"]),
    }
    estimate = _check_budget(int(parent["receiver"].size),
                             max(min(len(reach_rows), channel_cells), 1))
    return {
        "schema": SCHEMA,
        "parent_identity_sha256": parent["identity_sha256"],
        "parent_schema": parent["schema"],
        "support_identity_sha256": parent["support_identity_sha256"],
        "world_seed": parent["world_seed"],
        "spacing_m": parent["spacing_m"],
        "plan_version": parent["plan_version"],
        "min_upstream_cells": int(min_upstream_cells),
        "channel_rule": CHANNEL_RULE,
        "segmentation_rule": SEGMENTATION_RULE,
        "edge_policy": EDGE_POLICY,
        "reach_identity_policy": REACH_IDENTITY_POLICY,
        "local_q_policy": LOCAL_Q_POLICY,
        "status": status,
        "whole_support_upstream_complete": whole_complete,
        "physical_domain_certified": False,
        "display_root_index": (None if _display_root(parent, root_rows) is None
                               else _display_root(parent, root_rows)),
        "display_root_rule": (
            "the complete candidate with the most members, ties by the root's world "
            "(x, z); no complete root means no display root, an incomplete one is never "
            "promoted"),
        "reason_codes": list(reasons),
        "reason_vocabulary": list(REASON_VOCABULARY),
        "counts": counts,
        "budget": {
            "max_reaches": MAX_REACHES,
            "max_reach_bytes": MAX_REACH_BYTES,
            "estimated_payload_bytes": int(estimate),
            "note": ("estimated payload only, not a resident-memory ceiling; the parent "
                     "bundle, the caller's copies and interpreter overhead are outside it"),
            "unknown_budget_policy": (
                "an unknown budget refuses rather than silently changing the declared "
                "min_upstream_cells"),
        },
        "algorithm": {
            "name": "metric-world-reach-network",
            "version": LOGICAL_VERSION,
            "partition": ("one grouping over the parent's existing receiver; no second "
                          "irregular graph, no new routing, no filling, no hydraulics"),
            "channel_selection": CHANNEL_RULE,
            "reused_from_parent": ("receiver, resolved_mask, upstream_cells, owner_index, "
                                   "terminal_kind, mainstem cells"),
        },
        "algorithm_dependency_sha256": _dependency_sha256(),
        "limits": {
            "no_section_geometry": True,
            "no_hydraulics": True,
            "no_sediment": True,
            "no_water": True,
            "candidate_closed_is_not_natural": True,
            "outside_support_remains_unknown": True,
            "reach_count_is_not_river_count": True,
            "no_lake_or_coast_connection": True,
        },
    }


def build_world_reaches(parent_domain_bundle, *, min_upstream_cells=DEFAULT_MIN_UPSTREAM_CELLS):
    """Turn a validated B1 domain bundle into a complete reach network.

    The parent is validated first (``validate_domain_candidates``); nothing is read from
    an unvalidated or re-sealed parent. The network covers the **declared channel** only:
    valid cells below ``min_upstream_cells`` are reported as unselected rather than being
    silently treated as dry, and an empty channel is a legal empty network instead of a
    "complete river network".
    """
    threshold = _strict_int(min_upstream_cells, "min_upstream_cells")
    if threshold < 1:
        raise ValueError("min_upstream_cells must be a positive integer, got %d" % threshold)
    parent = _parent_view(parent_domain_bundle)
    arrays, reach_rows, root_rows, metadata = _build(parent, threshold)
    return {
        "schema": SCHEMA,
        "parent": {
            "schema": parent["schema"],
            "identity_sha256": parent["identity_sha256"],
            "support_identity_sha256": parent["support_identity_sha256"],
            "plan_version": parent["plan_version"],
        },
        "arrays": arrays,
        "reaches": reach_rows,
        "roots": root_rows,
        "metadata": metadata,
        "identity_sha256": identity(arrays, metadata),
    }


# --------------------------------------------------------------------------- #
# validation: recompute from the parent, then assert the semantics explicitly
# --------------------------------------------------------------------------- #
def _compare_arrays(stored, rebuilt):
    if not isinstance(stored, dict) or set(stored) != set(ARRAY_NAMES):
        raise ValueError("the reach arrays must be exactly %s" % (list(ARRAY_NAMES),))
    for name in ARRAY_NAMES:
        value = stored[name]
        expected = rebuilt[name]
        if not isinstance(value, np.ndarray) or value.dtype != expected.dtype:
            raise ValueError("array %r must have dtype %s" % (name, expected.dtype))
        if value.shape != expected.shape:
            raise ValueError("array %r must have shape %s, got %s"
                             % (name, list(expected.shape), list(value.shape)))
        if not np.array_equal(value, expected):
            raise ValueError("array %r does not agree with the recomputation from the "
                             "parent's receiver and ownership" % name)


def validate_world_reaches(bundle, parent_domain_bundle):
    """Recompute the whole network from the parent and refuse any disagreement.

    The parent must be passed in **and** pass the B1 gate: a bundle carries only its
    parent's identity, which cannot re-derive the parent's topology, so the original
    parent is what gets revalidated here. Every derived array, every reach row, every
    root row and the whole metadata block are then recomputed through the same build path
    and compared, so re-sealing a wrong downstream, a duplicated member, a fabricated
    root or a dropped one-cell reach still fails.

    On top of the recomputation, the explicit structural assertions below state the
    properties a reader must be able to trust; each of them follows from the rebuild, and
    stating them keeps the refusal reason precise.
    """
    if not isinstance(bundle, dict) or set(bundle) != BUNDLE_KEYS:
        raise ValueError("a reach bundle is %s" % (sorted(BUNDLE_KEYS),))
    if bundle["schema"] != SCHEMA:
        raise ValueError("unexpected reach bundle schema %r" % (bundle["schema"],))
    metadata = bundle["metadata"]
    if not isinstance(metadata, dict) or metadata.get("schema") != SCHEMA:
        raise ValueError("the reach metadata must declare schema %r" % (SCHEMA,))
    if not isinstance(metadata.get("min_upstream_cells"), int):
        raise ValueError("%s: min_upstream_cells must be declared" % REASON_UNPREPARED)
    parent = _parent_view(parent_domain_bundle)
    if bundle["parent"] != {
            "schema": parent["schema"],
            "identity_sha256": parent["identity_sha256"],
            "support_identity_sha256": parent["support_identity_sha256"],
            "plan_version": parent["plan_version"]}:
        raise ValueError("%s: the bundle is not bound to the parent it was built from"
                         % REASON_UNPREPARED)
    if metadata.get("parent_identity_sha256") != parent["identity_sha256"]:
        raise ValueError("%s: the metadata parent identity does not match the supplied "
                         "parent" % REASON_UNPREPARED)
    threshold = _strict_int(metadata["min_upstream_cells"], "min_upstream_cells")
    if threshold < 1:
        raise ValueError("min_upstream_cells must be positive, got %d" % threshold)
    # Bind the declared gate to the actual selection rule instead of merely re-reading it:
    # a bundle whose declared threshold does not reproduce the declared channel is refused
    # before anything is rebuilt.
    recorded_channel = int(metadata["counts"]["channel_cells"])
    declared_channel = int((parent["resolved_mask"].reshape(-1)
                            & (parent["receiver"].reshape(-1) >= 0)
                            & (parent["upstream_cells"].reshape(-1) >= threshold)).sum())
    if declared_channel != recorded_channel:
        raise ValueError("%s: the declared min_upstream_cells=%d selects %d channel cells "
                         "but the metadata records %d; the gate does not reproduce the "
                         "declared channel" % (REASON_SEGMENT_DONOR_MISMATCH, threshold,
                                               declared_channel, recorded_channel))
    # The declared channel must also be the one actually written, so a bundle cannot
    # declare one gate and carry the raster of another.
    covered = int((bundle["arrays"]["reach_of_cell"] >= 0).sum())
    if covered != recorded_channel:
        raise ValueError("%s: reach_of_cell covers %d cells but the metadata declares %d "
                         "channel cells" % (REASON_SEGMENT_DONOR_MISMATCH, covered,
                                            recorded_channel))

    stored = bundle["arrays"]
    if not isinstance(stored, dict):
        raise ValueError("the reach arrays must be a mapping")
    rebuilt_arrays, rebuilt_reaches, rebuilt_roots, rebuilt_metadata = _build(parent, threshold)
    _compare_arrays(stored, rebuilt_arrays)
    if bundle["reaches"] != rebuilt_reaches:
        raise ValueError("the reach list does not agree with the recomputation")
    if bundle["roots"] != rebuilt_roots:
        raise ValueError("the root list does not agree with the recomputation")
    if metadata != rebuilt_metadata:
        raise ValueError("the metadata does not agree with the recomputation; a re-sealed "
                         "derived field is still refused")
    if bundle["identity_sha256"] != identity(stored, metadata):
        raise ValueError("the bundle identity_sha256 is not the identity of its arrays and "
                         "metadata")

    _assert_semantics(parent, stored, bundle["reaches"], threshold, bundle["roots"])
    return None


def _assert_semantics(parent, arrays, reaches, threshold, root_rows):
    """Structural assertions a reader must be able to trust, stated one by one."""
    receiver = parent["receiver"].reshape(-1)
    resolved = parent["resolved_mask"].reshape(-1)
    upstream = parent["upstream_cells"].reshape(-1)
    owner = parent["owner_index"].reshape(-1)
    reach_of_cell = arrays["reach_of_cell"].reshape(-1)
    pointer = arrays["reach_ptr"]
    cells = arrays["reach_cells"]
    downstream = arrays["reach_downstream"]
    donors = arrays["reach_donors"]
    reach_count = int(downstream.size)

    expected_channel = resolved & (receiver >= 0) & (upstream >= threshold)
    if not np.array_equal(reach_of_cell >= 0, expected_channel):
        raise ValueError("%s: reach_of_cell does not cover exactly the declared channel"
                         % REASON_SEGMENT_DONOR_MISMATCH)

    # CSR self-consistency: every reach's slice is exactly its members, once.
    if pointer.shape != (reach_count + 1,) or pointer[0] != 0:
        raise ValueError("the reach CSR pointer is malformed")
    if int(pointer[-1]) != int(expected_channel.sum()):
        raise ValueError("the reach CSR does not cover the channel exactly once")
    seen = np.zeros(receiver.size, bool)
    for index in range(reach_count):
        low, high = int(pointer[index]), int(pointer[index + 1])
        if high <= low:
            raise ValueError("reach %d has no members; a reach is never empty" % index)
        members = cells[low:high]
        if not np.array_equal(reach_of_cell[members], np.full(members.size, index)):
            raise ValueError("reach %d membership disagrees with reach_of_cell" % index)
        if seen[members].any():
            raise ValueError("%s: a channel cell belongs to two reaches"
                             % REASON_SEGMENT_DONOR_MISMATCH)
        seen[members] = True
        roots = np.unique(owner[members])
        if roots.size != 1:
            raise ValueError("%s: reach %d spans two roots" % (REASON_CROSS_ROOT_FLOW, index))
        if int(roots[0]) != int(arrays["reach_root_index"][index]):
            raise ValueError("%s: reach %d declares the wrong root"
                             % (REASON_CROSS_ROOT_FLOW, index))
        if int(arrays["reach_head"][index]) != int(members[0]):
            raise ValueError("reach %d head is not its first member" % index)
        if int(arrays["reach_tail"][index]) != int(members[-1]):
            raise ValueError("reach %d tail is not its last member" % index)
        if int(arrays["reach_node_count"][index]) != members.size:
            raise ValueError("reach %d node_count disagrees with its members" % index)
        if int(arrays["reach_edges"][index]) != members.size - 1:
            raise ValueError("reach %d edges must be node_count - 1" % index)
        for first, second in zip(members[:-1], members[1:]):
            if int(receiver[first]) != int(second):
                raise ValueError("reach %d is not a receiver chain" % index)
    if not seen[expected_channel].all():
        raise ValueError("%s: a channel cell belongs to no reach"
                         % REASON_SEGMENT_DONOR_MISMATCH)

    # Downstream: never across roots, never a cycle, and donors == upstream reach count.
    for index in range(reach_count):
        target = int(downstream[index])
        tail = int(arrays["reach_tail"][index])
        following = int(receiver[tail])
        if target >= 0:
            if int(arrays["reach_root_index"][target]) != int(arrays["reach_root_index"][index]):
                raise ValueError("%s: reach %d hands off across roots"
                                 % (REASON_CROSS_ROOT_FLOW, index))
            if following != int(arrays["reach_head"][target]):
                raise ValueError("%s: reach %d hands off to %d but the downstream reach "
                                 "starts at %d" % (REASON_HANDOFF_MISMATCH, index,
                                                   following,
                                                   int(arrays["reach_head"][target])))
        else:
            if following < 0:
                raise ValueError("%s: reach %d ends on a terminal cell instead of above it"
                                 % (REASON_CHANNEL_RECEIVER_NOT_TERMINAL, index))
            if int(owner[following]) != int(arrays["reach_root_index"][index]):
                raise ValueError("%s: reach %d drains into another root"
                                 % (REASON_CROSS_ROOT_FLOW, index))
    tallies = np.zeros(reach_count, np.int64)
    for index in range(reach_count):
        if int(downstream[index]) >= 0:
            tallies[int(downstream[index])] += 1
    if not np.array_equal(tallies, donors):
        raise ValueError("%s: reach_donors is not the upstream reach count"
                         % REASON_SEGMENT_DONOR_MISMATCH)
    seen_index = np.zeros(reach_count, bool)
    for index in range(reach_count):
        current = int(downstream[index])
        while current >= 0:
            if current == index:
                raise ValueError("%s: reach_downstream contains a cycle at reach %d"
                                 % (REASON_REACH_CYCLE, index))
            if seen_index[current]:
                break
            current = int(downstream[current])

    # Directed edges: source and target are never swapped, and the union of internal
    # edges and handoff edges covers every selected channel edge exactly once.
    handoff = arrays["handoff_edge_pairs"]
    terminal = arrays["terminal_edge_pairs"]
    if handoff.shape != (reach_count, 2):
        raise ValueError("%s: there must be exactly one handoff edge per reach"
                         % REASON_HANDOFF_MISMATCH)
    for index in range(reach_count):
        source, target = int(handoff[index, 0]), int(handoff[index, 1])
        if source != int(arrays["reach_tail"][index]):
            raise ValueError("%s: handoff %d does not start at its reach tail"
                             % (REASON_HANDOFF_MISMATCH, index))
        if int(receiver[source]) != target:
            raise ValueError("%s: handoff %d is not a receiver edge"
                             % (REASON_HANDOFF_MISMATCH, index))
        expected = _hop_length_m(parent, source, target)
        if not math.isclose(float(arrays["reach_handoff_length_m"][index]), expected,
                            rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("%s: reach %d handoff length is not the length of its edge"
                             % (REASON_HANDOFF_MISMATCH, index))
    internal = 0
    for index in range(reach_count):
        internal += int(arrays["reach_edges"][index])
    if internal + handoff.shape[0] != int(expected_channel.sum()):
        raise ValueError("%s: internal edges plus handoff edges do not cover every "
                         "selected channel edge exactly once"
                         % (REASON_HANDOFF_MISMATCH,))

    # Terminal reaches: exactly one directed edge into the structural terminal, and that
    # terminal is this root's cell. The orientation is never canonicalised.
    terminal_reaches = [index for index in range(reach_count)
                        if int(downstream[index]) < 0]
    if terminal.shape != (len(terminal_reaches), 2):
        raise ValueError("%s: every terminal reach needs exactly one terminal edge"
                         % REASON_TERMINAL_EDGE_MISSING)
    expected_terminals = {(int(arrays["reach_tail"][index]), int(receiver[int(arrays["reach_tail"][index])]))
                          for index in terminal_reaches}
    stored_terminals = {(int(row[0]), int(row[1])) for row in terminal.tolist()}
    if stored_terminals != expected_terminals:
        raise ValueError("%s: terminal_edge_pairs is not the set of terminal reach edges"
                         % REASON_TERMINAL_EDGE_MISSING)
    for row in terminal.tolist():
        if int(row[0]) == int(row[1]):
            raise ValueError("a terminal edge may not be a self edge")
        if int(receiver[int(row[0])]) != int(row[1]):
            raise ValueError("%s: terminal edge %s is not oriented as a receiver edge"
                             % (REASON_TERMINAL_EDGE_MISSING, row))
        if int(owner[int(row[1])]) != int(owner[int(row[0])]):
            raise ValueError("%s: a terminal edge crosses a root boundary"
                             % REASON_CROSS_ROOT_FLOW)

    # One-cell reaches are legal and must never be dropped.
    single = sum(1 for index in range(reach_count)
                 if int(arrays["reach_node_count"][index]) == 1)
    expected_single = sum(1 for index in range(reach_count)
                          if int(pointer[index + 1]) - int(pointer[index]) == 1)
    if single != expected_single:
        raise ValueError("%s: a one-cell reach was dropped" % REASON_SEGMENT_DONOR_MISMATCH)
    for row in reaches:
        for key in REACH_KEYS:
            if key not in row:
                raise ValueError("reach %r is missing the required field %r"
                                 % (row.get("reach_index"), key))
        if set(row) != set(REACH_KEYS):
            raise ValueError("reach %r carries fields outside the declared key set"
                             % (row.get("reach_index"),))
    if any(row["terminal_kind"] == "open_outflow" for row in reaches):
        raise ValueError("this layer never certifies an open outflow")
    _assert_trunk_order(parent, arrays, reaches, root_rows)


def _assert_trunk_order(parent, arrays, reaches, root_rows):
    """The trunk sequence must be a real flow path, not a list that merely looks ordered.

    For every root, the reported ``channel_mainstem_reach_ids`` must:

    * be the parent's ordered source→root trunk, with channel cells kept and consecutive
      duplicates collapsed -- recomputed here from ``mainstem_cells``, so a flat-index or
      set-based list cannot pass;
    * satisfy ``downstream_reach_id`` of item *i* == item *i+1* for every adjacent pair;
    * end at the reach whose ``downstream_reach_index`` is ``-1`` and whose terminal is
      this root's cell;
    * report ``node_count == channel cell count + 1`` and ``edges == channel cell count``
      (the with-terminal path), and 0/0/0 when the trunk is empty.

    Length is recomputed straight from the ordered parent path, so it does not merely agree
    with the builder's own bookkeeping.
    """
    by_id = {row["reach_id"]: row for row in reaches}
    channel = (arrays["reach_of_cell"].reshape(-1) >= 0)
    for row in root_rows:
        index = int(row["root_index"])
        low = int(parent["mainstem_ptr"][index])
        high = int(parent["mainstem_ptr"][index + 1])
        ordered = [int(cell) for cell in parent["mainstem_cells"][low:high]]
        if not ordered or ordered[-1] != int(parent["root_cells"][index]):
            raise ValueError("%s: root %d has no parent trunk ending at its root"
                             % (REASON_ROOT_NOT_TERMINAL, index))
        # **Raw counts are bound to the parent directly**, not re-derived through the
        # builder: they are the length of the parent's own mainstem slice. Comparing them
        # to the stored values here is what makes a wrong raw count fail even though the
        # rebuild would repeat the same mistake.
        raw_nodes = high - low
        if (int(row["raw_mainstem_node_count"]) != raw_nodes
                or int(row["raw_mainstem_edges"]) != raw_nodes - 1):
            raise ValueError("root %d must report the parent's own raw trunk length: %d "
                             "nodes and %d edges, got %d/%d"
                             % (index, raw_nodes, raw_nodes - 1,
                                int(row["raw_mainstem_node_count"]),
                                int(row["raw_mainstem_edges"])))
        raw_length = _chain_length_m(parent, ordered)
        if not math.isclose(float(row["raw_mainstem_length_m"]), raw_length,
                            rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("%s: the raw trunk length of root %d is not the length of the "
                             "parent's own mainstem" % (REASON_HANDOFF_MISMATCH, index))
        trunk_cells = [cell for cell in ordered if bool(channel[cell])]
        reach_of_cell = arrays["reach_of_cell"].reshape(-1)
        sequence = []
        for cell in trunk_cells:
            reach_index = int(reach_of_cell[cell])
            if reach_index < 0:
                raise ValueError("%s: a channel trunk cell belongs to no reach"
                                 % REASON_SEGMENT_DONOR_MISMATCH)
            if not sequence or sequence[-1] != reach_index:
                sequence.append(reach_index)
        expected_ids = [reaches[reach]["reach_id"] for reach in sequence]
        if row["channel_mainstem_reach_ids"] != expected_ids:
            raise ValueError(
                "%s: the trunk of root %d is not the parent's ordered path; a set or a "
                "flat-index sort would produce this list" % (REASON_HANDOFF_MISMATCH, index))
        for first, second in zip(expected_ids[:-1], expected_ids[1:]):
            if by_id[first]["downstream_reach_id"] != second:
                raise ValueError("%s: trunk step %s -> %s is not a downstream edge"
                                 % (REASON_HANDOFF_MISMATCH, first, second))
        if expected_ids:
            last = by_id[expected_ids[-1]]
            if last["downstream_reach_index"] >= 0:
                raise ValueError("%s: the trunk of root %d ends before the terminal"
                                 % (REASON_TERMINAL_EDGE_MISSING, index))
            if last["terminal_root_world_xz"] != row["root_world_xz"]:
                raise ValueError("%s: the trunk of root %d ends at another root's terminal"
                                 % (REASON_CROSS_ROOT_FLOW, index))
            nodes = len(trunk_cells) + 1
            if (row["channel_mainstem_node_count"] != nodes
                    or row["channel_mainstem_edges"] != len(trunk_cells)
                    or row["channel_mainstem_channel_cell_count"] != len(trunk_cells)):
                raise ValueError("root %d must report S+1 nodes, S edges and S channel "
                                 "cells for S=%d" % (index, len(trunk_cells)))
        else:
            if (row["channel_mainstem_node_count"] != 0
                    or row["channel_mainstem_edges"] != 0
                    or row["channel_mainstem_length_m"] != 0.0):
                raise ValueError("root %d has no channel trunk, so its counts must be 0/0/0"
                                 % index)
        path = trunk_cells + [int(parent["root_cells"][index])]
        expected_length = _chain_length_m(parent, path)
        if not math.isclose(float(row["channel_mainstem_length_m"]), expected_length,
                            rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("%s: the trunk length of root %d is not the length of its "
                             "ordered path" % (REASON_HANDOFF_MISMATCH, index))
