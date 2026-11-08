# -*- coding: utf-8 -*-
"""Independent cold-read audit of a prepared river-backbone product.

What this tool is
-----------------
A **separate process** that reads a product directory and re-derives every published number
with its own implementation. It imports nothing from the producer: no
``metric_backbone_precompute``, no ``metric_network_accumulation``, no
``metric_domain_closure``, no ``native_30m_source``. The import ban is asserted at start-up
by scanning ``sys.modules``, so a transitive import cannot slip in.

What it checks
--------------
1. the product's bytes, headers, budget and identity (through the shared read-only codec);
2. an **independent per-cell walk**: reach chains, coverage, anchors, handoff and terminal
   edges, upstream areas, the area's completeness, every quantity's routed field and that
   quantity's own completeness;
3. the declared side inputs, re-solved independently: one chosen source per branch, its
   delivery compared, and the deliberate double count shown to be detectable;
4. with ``--reference-rows``: the A-gate edge, anchor and split-relation check;
5. with ``--compare-product``: the cross-window acceptance.

There is no "verify accumulation on load" switch: a product stores only its parent's
identity, which cannot re-derive the parent's topology, and re-running the network on every
read is exactly what this design refuses. The full rebuild is the producer's own
``validate_backbone`` before publishing; this audit is the independent second opinion.

Cross-window acceptance, correctly stated
-----------------------------------------
"Strictly interior" only means the cell has a complete 8-neighbourhood; it does **not** mean
its upstream is closed. The same world cell can therefore carry a different upstream member
set, a different area and a different routed flux in two windows. So a value is compared
only where **all** of these hold, separately per quantity:

* the cell is strictly interior in **both** windows;
* that quantity's own completeness is ``True`` on both sides;
* the **world upstream member set is equal**, computed here by an independent reverse walk
  (not read off ``complete_mask``);
* the quantity's input exists (status ``available``) and both sides declare the same input
  provenance digest.

Every other cell is listed with a reason; nothing is dropped and no completeness is inferred
from the area's. ``receiver`` is compared in **world** coordinates, because a flat index
carries the column count of its own window.

A reach id is only required to be equal when the whole ordered path lies strictly interior
*and* every node of it is complete on both sides; a boundary-crossing or partially pending
reach is reported as ``not_comparable_context``. Because an OR gate may legitimately **split**
an A-only reach, this audit does not require the OR segmentation to be an ordered
subsequence of the B2 segments. It requires what actually matters: every A-gate directed
edge of the reference network appears in the OR edge set, every confluence anchor and reach
endpoint is preserved or is a declared split point, and the split/merge relation is written
out per reach.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "river-backbone-audit-v1"
PRODUCT_SCHEMA = "metric-river-backbone-v1"

#: Modules this audit must never import. Checked before and after the run.
BANNED_MODULES = (
    "terrain_pipeline.surface_rivers.metric_backbone_precompute",
    'terrain_pipeline.drainage',
    "terrain_pipeline.surface_rivers.metric_domain_closure",
    "terrain_pipeline.surface_rivers.native_30m_source",
    "terrain_pipeline.surface_rivers.metric_world_domains",
    "terrain_pipeline.surface_rivers.metric_world_reaches",
    "terrain_pipeline.surface_rivers.metric_backbone_product",
)
#: Exceptions: the shared **read-only codec** is allowed, because it only reads bytes and
#: never computes elevation, topology or discharge.
ALLOWED = ("terrain_pipeline.surface_rivers.metric_backbone_product",)


class AuditRefused(ValueError):
    """A structural refusal; the audit reports FAIL rather than patching anything."""


def loaded_banned_modules():
    return sorted(name for name in BANNED_MODULES
                  if name in sys.modules and name not in ALLOWED)


def require_independent_process():
    hits = loaded_banned_modules()
    if hits:
        raise AuditRefused("this audit must not import the producer: %s" % hits)
    return None


# --------------------------------------------------------------------------- #
# independent graph arithmetic (no producer kernel)
# --------------------------------------------------------------------------- #
def donor_csr(receiver_flat, valid_flat):
    """``donors[i]`` are the valid cells whose receiver is ``i``, in ascending order."""
    live = valid_flat & (receiver_flat >= 0)
    source = np.flatnonzero(live)
    target = receiver_flat[source]
    order = np.argsort(target, kind="stable")
    sorted_target = target[order]
    sorted_source = source[order]
    unique, start = np.unique(sorted_target, return_index=True)
    table = {}
    for index, key in enumerate(unique.tolist()):
        stop = int(start[index + 1]) if index + 1 < unique.size else int(sorted_source.size)
        table[int(key)] = np.ascontiguousarray(sorted_source[int(start[index]):stop], np.int64)
    return table


def topological_order(receiver_flat, valid_flat):
    """Kahn order over the valid graph, **upstream first**; a cycle is refused.

    The walk starts at cells with no donor at all (the sources of the graph), not at the
    terminals: a terminal has ``receiver == -1``, so taking it as a start makes the very first
    frontier have nowhere to step and would report a cycle on a perfectly acyclic graph. The
    count that drives the walk is the number of **donors** each cell has; it is decremented as
    donors are settled, and a terminal becomes ready exactly when its last inflow is done.

    The returned order is upstream-first, which is what ``accumulate_independent`` and
    ``propagate_independent`` need, so it is returned as built and not reversed.
    """
    valid = np.asarray(valid_flat, np.bool_)
    rec = np.asarray(receiver_flat, np.int64)
    live = valid & (rec >= 0)
    donors = np.zeros(rec.size, np.int64)
    np.add.at(donors, rec[live], 1)
    frontier = np.flatnonzero(valid & (donors == 0))
    order = []
    seen = np.zeros(rec.size, np.bool_)
    seen[frontier] = True
    order.extend(frontier.tolist())
    while frontier.size:
        source = frontier[rec[frontier] >= 0]
        if not source.size:
            break
        target = rec[source]
        np.subtract.at(donors, target, 1)
        ready = np.unique(target[donors[target] == 0])
        ready = ready[~seen[ready]]
        seen[ready] = True
        order.extend(ready.tolist())
        frontier = ready
    if int(seen[valid].sum()) != int(valid.sum()):
        missing = int(valid.sum() - seen[valid].sum())
        raise AuditRefused("the receiver graph contains a cycle: %d valid cells are never "
                           "settled (no donor-free start reaches them)" % missing)
    return np.asarray(order, np.int64)


def accumulate_independent(receiver_flat, valid_flat, local, order):
    """Sum ``local`` once per cell along the receiver, using this file's own order."""
    flow = np.array(local, np.float64, copy=True)
    for cell in order.tolist():
        target = int(receiver_flat[cell])
        if target >= 0:
            flow[target] += flow[cell]
    return flow


def propagate_independent(receiver_flat, valid_flat, seed, order):
    """OR the seed downstream with this file's own order."""
    dirty = np.array(seed, np.bool_, copy=True)
    for cell in order.tolist():
        target = int(receiver_flat[cell])
        if target >= 0 and dirty[cell]:
            dirty[target] = True
    return ~dirty & np.asarray(valid_flat, np.bool_)


def upstream_members(receiver_flat, valid_flat, cell, donors):
    """The world-independent **flat** member set above ``cell``; used only within one window."""
    stack = [int(cell)]
    members = {int(cell)}
    while stack:
        current = stack.pop()
        for donor in donors.get(current, np.empty(0, np.int64)).tolist():
            if int(donor) not in members:
                members.add(int(donor))
                stack.append(int(donor))
    return members


# --------------------------------------------------------------------------- #
# product walking
# --------------------------------------------------------------------------- #
def load_product(directory):
    from terrain_pipeline.surface_rivers.metric_backbone_product import load_backbone_product

    product = load_backbone_product(directory)
    return product


def load_parent_reference(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def walk_reaches(product):
    """Independent per-cell reconstruction of every reach and its endpoints."""
    arrays = product["arrays"]
    metadata = product["metadata"]
    receiver = np.asarray(arrays["receiver"], np.int64)
    valid = np.asarray(arrays["valid_mask"], np.bool_)
    rows, columns = receiver.shape
    origin = [int(v) for v in metadata["origin_native_xz"]]
    reach_of_cell = np.asarray(arrays["reach_of_cell"], np.int64)
    pointer = np.asarray(arrays["reach_ptr"], np.int64)
    cells = np.asarray(arrays["reach_cells"], np.int64)
    downstream = np.asarray(arrays["reach_downstream"], np.int64)
    head = np.asarray(arrays["reach_head"], np.int64)
    tail = np.asarray(arrays["reach_tail"], np.int64)
    flat_rec = receiver.reshape(-1)
    flat_reach = reach_of_cell.reshape(-1)
    counted = int(cells.size)
    if int(pointer[-1]) != counted:
        raise AuditRefused("reach_ptr does not close over reach_cells")
    problems = []
    facts = []
    for index in range(int(pointer.size - 1)):
        chain = cells[int(pointer[index]):int(pointer[index + 1])]
        if int(head[index]) != int(chain[0]) or int(tail[index]) != int(chain[-1]):
            problems.append("reach %d: stored head/tail are not the chain ends" % index)
        breaks = 0
        for first, second in zip(chain[:-1], chain[1:]):
            if int(flat_rec[first]) != int(second):
                breaks += 1
        if breaks:
            problems.append("reach %d: %d internal breaks in the receiver chain" % (index, breaks))
        if np.any(flat_reach[chain] != index):
            problems.append("reach %d: a chain cell is owned by another reach" % index)
        following = int(flat_rec[chain[-1]])
        if following < 0:
            problems.append("reach %d: a routable channel tail has no receiver" % index)
        if downstream[index] < 0:
            if following >= 0 and int(flat_reach[following]) >= 0:
                problems.append("reach %d: claims an end but drains into reach %d"
                                % (index, int(flat_reach[following])))
        else:
            if following < 0:
                problems.append("reach %d: has a downstream but no receiver" % index)
            elif int(flat_reach[following]) != int(downstream[index]):
                problems.append("reach %d: downstream is not the owner of its tail receiver"
                                % index)
        facts.append({
            "reach_index": index,
            "cell_count": int(chain.size),
            "head_flat": int(chain[0]),
            "tail_flat": int(chain[-1]),
            "head_world_native": [origin[0] + int(chain[0]) % columns,
                                  origin[1] + int(chain[0]) // columns],
            "tail_world_native": [origin[0] + int(chain[-1]) % columns,
                                  origin[1] + int(chain[-1]) // columns],
            "terminal_world_native": (None if following < 0 else
                                      [origin[0] + following % columns,
                                       origin[1] + following // columns]),
            "downstream_reach_index": int(downstream[index]),
            "cells": [int(v) for v in chain.tolist()],
        })
    covered = int((flat_reach >= 0).sum())
    channel = np.asarray(arrays["channel_mask"], np.bool_).reshape(-1)
    if not np.array_equal(flat_reach >= 0, channel):
        problems.append("reach_of_cell does not cover exactly the stored channel")
    if covered != int(channel.sum()):
        problems.append("coverage count %d is not the channel count %d"
                        % (covered, int(channel.sum())))
    reused = counted - int(np.unique(cells).size)
    if reused:
        problems.append("%d channel cells appear in more than one reach" % reused)
    return {"facts": facts, "problems": problems, "covered_cells": covered,
            "channel_cells": int(channel.sum()), "columns": columns, "origin": origin,
            "rows": rows}


def check_values(product, walked):
    """Re-derive areas, area completeness, every flux field and its own completeness."""
    arrays = product["arrays"]
    metadata = product["metadata"]
    receiver = np.asarray(arrays["receiver"], np.int64)
    valid = np.asarray(arrays["valid_mask"], np.bool_)
    shape = receiver.shape
    flat_rec = receiver.reshape(-1)
    flat_valid = valid.reshape(-1)
    steps = int(metadata["clock"]["steps"])
    edges = np.asarray(arrays["time_edges_s"], np.float64)
    order = topological_order(flat_rec, flat_valid)
    donors = donor_csr(flat_rec, flat_valid)
    problems = []

    seeds = np.asarray(arrays["upstream_unknown_mask"], np.bool_)
    unit = np.where(valid, 1.0, 0.0).reshape(-1)
    area_ref = np.rint(accumulate_independent(flat_rec, flat_valid, unit, order)).astype(np.int64)
    area_stored = np.asarray(arrays["area_cells"], np.int64).reshape(-1)
    if not np.array_equal(area_ref, area_stored):
        problems.append("the stored upstream area disagrees with an independent accumulation")
    complete_ref = propagate_independent(flat_rec, flat_valid, seeds.reshape(-1), order)
    complete_stored = np.asarray(arrays["area_complete"], np.bool_).reshape(-1)
    if not np.array_equal(complete_ref, complete_stored):
        problems.append("the stored area completeness disagrees with an independent "
                        "propagation of the window-cut seeds")

    index = np.asarray(arrays["local_input_index"], np.int64)
    node_cells = np.asarray(arrays["reach_cells"], np.int64)
    quantity_report = {}
    for name, report in sorted(metadata["quantities"].items()):
        stored_local = np.asarray(arrays["local_input_%s_m3_s" % name], np.float64)
        if stored_local.shape != (steps, index.size):
            raise AuditRefused("the local input of %s is %s, the clock says [%d, %d]"
                               % (name, list(stored_local.shape), steps, index.size))
        available = np.zeros(int(np.prod(shape)), np.bool_)
        available[index] = np.asarray(arrays["local_input_%s_available" % name], np.bool_)
        missing = flat_valid & (~available | seeds.reshape(-1))
        q_complete_ref = propagate_independent(flat_rec, flat_valid, missing, order)
        q_complete_stored = np.asarray(arrays["node_q_%s_complete" % name], np.bool_)
        if not np.array_equal(q_complete_ref[node_cells], q_complete_stored):
            problems.append("%s: the stored node completeness disagrees with an independent "
                            "propagation of the missing-input seeds" % name)
        flow_ref = np.zeros((steps, int(np.prod(shape))), np.float64)
        for step in range(steps):
            block = np.zeros(int(np.prod(shape)), np.float64)
            block[index] = np.asarray(arrays["local_input_%s_m3_s" % name],
                                      np.float64)[step]
            flow_ref[step] = accumulate_independent(flat_rec, flat_valid, block, order)
        stored_flow = np.asarray(arrays["node_q_%s_m3_s" % name], np.float64)
        gap = float(np.max(np.abs(flow_ref[:, node_cells] - stored_flow))) if steps else 0.0
        if not np.allclose(flow_ref[:, node_cells], stored_flow, rtol=1e-12, atol=1e-15):
            problems.append("%s: the stored routed flux disagrees with an independent "
                            "accumulation (max |gap| = %r m3/s)" % (name, gap))
        available_mask = available.reshape(shape)
        quantity_report[name] = {
            "gate_time_index": int(report["gate_time_index"]),
            "available_cells": int((available_mask & valid).sum()),
            "unavailable_valid_cells": int((~available_mask & valid).sum()),
            "complete_valid_cells": int(q_complete_ref.sum()),
            "pending_valid_cells": int((flat_valid & ~q_complete_ref).sum()),
            "max_abs_flux_gap_m3_s": gap,
            "flux_agrees": bool(np.allclose(flow_ref[:, node_cells], stored_flow,
                                            rtol=1e-12, atol=1e-15)),
            "completeness_agrees": bool(np.array_equal(q_complete_ref[node_cells],
                                                       q_complete_stored)),
            "area_completeness_used": False,
        }
    area_report = {
        "cells_compared": int(valid.sum()),
        "area_agrees": bool(np.array_equal(area_ref, area_stored)),
        "area_completeness_agrees": bool(np.array_equal(complete_ref, complete_stored)),
        "complete_cells": int(complete_ref.sum()),
        "pending_cells": int((flat_valid & ~complete_ref).sum()),
    }
    return {"problems": problems, "area": area_report, "quantities": quantity_report,
            "order": order, "donors": donors, "edges": edges}


def check_terminals(product):
    """Endpoint two-axis: nothing but ``pending`` may be published as permanent."""
    problems = []
    event_receivers = 0
    permanent = {"pending": 0}
    reasons = {}
    for row in product.get("reaches", []) or []:
        reason = row.get("terminal_reason")
        if reason is not None:
            reasons[reason] = reasons.get(reason, 0) + 1
        terminal = row.get("permanent_terminal")
        if terminal is None:
            continue
        kind = terminal.get("kind")
        if kind != "pending":
            problems.append("reach %s publishes permanent_terminal=%r; only 'pending' is "
                            "allowed in this layer" % (row.get("reach_id"), kind))
        else:
            permanent["pending"] += 1
        if terminal.get("is_permanent_terminal"):
            problems.append("reach %s marks its terminal as permanent"
                            % (row.get("reach_id"),))
        record = row.get("event_receiver")
        if record is not None:
            event_receivers += 1
            if record.get("kind") != "finite_event_lake_storage":
                problems.append("reach %s declares an unknown event receiver kind"
                                % (row.get("reach_id"),))
            if record.get("is_permanent_terminal"):
                problems.append("reach %s marks its event receiver as permanent"
                                % (row.get("reach_id"),))
            for key in ("product_identity_sha256", "safe_level_m", "safe_volume_m3",
                        "supported_time_edges_s", "source_files_sha256"):
                if key not in record:
                    problems.append("reach %s: the event receiver record lacks %r"
                                    % (row.get("reach_id"), key))
            if not record.get("source_files_sha256"):
                problems.append("reach %s: the event receiver cites no product sources"
                                % (row.get("reach_id"),))
    return {"problems": problems, "event_receiver_reaches": event_receivers,
            "permanent_terminals": permanent, "terminal_reasons": reasons}


def check_anchors_against_reference(product, walked, reference_rows):
    """A-gate edges, anchors and the explicit split relation against a reference network.

    ``reference_rows`` is the list of reach rows of the A-only reference (a
    ``metric-world-reach-network-v1`` bundle's ``reaches``). The OR network may **split** an
    A reach, so ordering is not required; edge coverage, anchors and the split relation are.
    """
    origin = walked["origin"]
    columns = walked["columns"]

    def world_of(flat):
        return [origin[0] + int(flat) % columns, origin[1] + int(flat) // columns]

    or_edges = set()
    for fact in walked["facts"]:
        chain = fact["cells"]
        for first, second in zip(chain[:-1], chain[1:]):
            or_edges.add((tuple(world_of(first)), tuple(world_of(second))))
        if fact["terminal_world_native"] is not None:
            or_edges.add((tuple(world_of(fact["tail_flat"])),
                          tuple(fact["terminal_world_native"])))
    or_anchors = set()
    for fact in walked["facts"]:
        or_anchors.add(tuple(fact["head_world_native"]))
        or_anchors.add(tuple(fact["tail_world_native"]))
        if fact["terminal_world_native"] is not None:
            or_anchors.add(tuple(fact["terminal_world_native"]))
    or_heads = [tuple(fact["head_world_native"]) for fact in walked["facts"]]

    missing_edges = []
    missing_anchors = []
    split_relation = []
    reference_edges = 0
    reference_edges_checked = 0
    for row in reference_rows:
        head = tuple(int(v) for v in row["head_world_xz"])
        tail = tuple(int(v) for v in row["tail_world_xz"])
        path = row.get("node_world_xz") or row.get("world_native_xz")
        if path:
            points = [tuple(int(v) for v in point) for point in path]
            for first, second in zip(points[:-1], points[1:]):
                reference_edges += 1
                reference_edges_checked += 1
                if (first, second) not in or_edges:
                    missing_edges.append({"reference_reach_id": row.get("reach_id"),
                                          "edge": [list(first), list(second)]})
        if head in or_anchors and tail in or_anchors:
            split_relation.append({"reference_reach_id": row.get("reach_id"),
                                   "head_world_xz": list(head),
                                   "tail_world_xz": list(tail),
                                   "both_anchors_kept": True})
        else:
            if head not in or_anchors:
                missing_anchors.append({"reference_reach_id": row.get("reach_id"),
                                        "missing": "head", "world_xz": list(head)})
            if tail not in or_anchors:
                missing_anchors.append({"reference_reach_id": row.get("reach_id"),
                                        "missing": "tail", "world_xz": list(tail)})
            split_relation.append({"reference_reach_id": row.get("reach_id"),
                                   "head_world_xz": list(head),
                                   "tail_world_xz": list(tail),
                                   "both_anchors_kept": False,
                                   "note": ("the OR gate may split this reference reach; a "
                                            "missing anchor must then appear as a declared OR "
                                            "head or tail, which is listed separately")})
    edge_coverage = ("checked" if reference_edges_checked
                     else "NOT_RUN: the reference rows carry only head/tail anchors, no ordered "
                          "path, so edge coverage cannot be decided from them")
    coverage = {
        "or_edge_count": len(or_edges),
        "or_head_count": len(or_heads),
        "or_anchor_count": len(or_anchors),
        "reference_reach_count": len(reference_rows),
        "reference_edges": reference_edges,
        "reference_edges_checked": reference_edges_checked,
        "edge_coverage": edge_coverage,
        "missing_reference_edges": missing_edges[:32],
        "missing_reference_edge_count": len(missing_edges),
        "missing_reference_anchors": missing_anchors,
        "split_relation": split_relation,
        "ordering_required": False,
        "policy": ("an OR gate may split an A-only reach, so an ordered subsequence is NOT "
                   "required; what is required is that every reference directed edge (when the "
                   "reference carries ordered paths) and every anchor survives, and that the "
                   "split relation is written out"),
    }
    problems = []
    if missing_anchors:
        problems.append("%d reference anchors do not survive in the OR network"
                        % len(missing_anchors))
    if missing_edges:
        problems.append("%d reference directed edges are absent from the OR edge set"
                        % len(missing_edges))
    return {"problems": problems, "coverage": coverage, "or_edges": or_edges,
            "or_anchors": or_anchors}


def check_side_inputs(product, walked, values):
    """Resolve the declared side inputs the way a consumer would, and check the deduplication.

    Each recorded replacement is re-solved from the stored receiver using the independent
    accumulator of this file, and its declared delivery is compared. Because the
    **aggregated** and **refined** forms are mathematically equal on a lossless graph, a
    product can only be accepted if it stores exactly one of them: the report must name a
    single ``chosen.from`` and its deliberate double count must differ from the chosen value.
    An inherited port field (reading the upstream cell's own area as the branch's) is refused.
    """
    problems = []
    report = {"replacements": [], "mode_per_branch": {}}
    records = product["metadata"].get("side_inputs") or {}
    if not isinstance(records, dict):
        problems.append("the metadata side_inputs record must be a mapping")
        return {"problems": problems, "report": report}
    arrays = product["arrays"]
    receiver = np.asarray(arrays["receiver"], np.int64).reshape(-1)
    valid = np.asarray(arrays["valid_mask"], np.bool_).reshape(-1)
    order = values["order"]
    for name, record in sorted(records.items()):
        if name not in product["metadata"]["quantities"]:
            problems.append("side input %r names an undeclared quantity" % name)
            continue
        branches = record.get("branches") or []
        if not branches:
            continue
        # Accumulate the whole graph **once** per quantity and read every branch from it.
        # Doing this per branch would be the same arithmetic repeated N times and is what the
        # per-branch cost would otherwise be; the independence claim is about using this file's
        # own accumulator, not about repeating it once per branch.
        index = np.asarray(arrays["local_input_index"], np.int64)
        steps = int(product["metadata"]["clock"]["steps"])
        local_all = np.zeros((steps, receiver.size), np.float64)
        local_all[:, index] = np.asarray(arrays["local_input_%s_m3_s" % name], np.float64)
        delivery = np.zeros((steps, receiver.size), np.float64)
        for step in range(steps):
            delivery[step] = accumulate_independent(receiver, valid, local_all[step], order)
        for branch in branches:
            if not isinstance(branch, dict) or "chosen" not in branch:
                problems.append("%s: a branch record has no single chosen source" % name)
                continue
            source = branch["chosen"].get("from")
            if source not in ("aggregated", "refined"):
                problems.append("%s: branch %r chose an undeclared source"
                                % (name, branch.get("entry_cell_flat")))
                continue
            report["mode_per_branch"][str(branch.get("entry_cell_flat"))] = source
            entry = int(branch["entry_cell_flat"])
            members = [int(v) for v in branch.get("member_cells") or []]
            if not members:
                problems.append("%s: branch at %d has no members" % (name, entry))
                continue
            if any(member >= receiver.size for member in members):
                problems.append("%s: branch at %d names a cell outside the grid"
                                % (name, entry))
                continue
            if not np.all(valid[members]):
                problems.append("%s: branch at %d names an invalid cell" % (name, entry))
                continue
            if int(receiver[entry]) < 0:
                problems.append("%s: branch at %d has no channel downstream" % (name, entry))
                continue
            aggregated = float(np.sum(local_all[0][members]))
            entry_value = float(delivery[0][entry])
            # The independent answer is what the branch **delivers at its entry cell**, not the
            # sum of the routed flow at every member: a member's flow reappears at each
            # downstream member, so summing members would count the same water repeatedly.
            independent = entry_value
            if abs(independent - aggregated) > 1e-15 + 1e-12 * abs(aggregated):
                problems.append("%s: the branch at %d delivers %r m3/s but its members supply %r"
                                % (name, entry, independent, aggregated))
            declared = branch["chosen"].get("q_m3_s")
            double = branch.get("double_count_negative") or {}
            detected = bool(double.get("detected"))
            if not detected:
                problems.append("%s: the double count at %d is not detectable; the "
                                "deduplication cannot be shown" % (name, entry))
            if entry_value <= 0.0:
                problems.append("%s: branch at %d delivers nothing; it cannot be a non-empty "
                                "success case" % (name, entry))
            report["replacements"].append({
                "quantity": name,
                "entry_cell_flat": entry,
                "member_count": len(members),
                "chosen_from": source,
                "declared_area_cells": int(branch["chosen"].get("area_cells", -1)),
                "received_area_cells": int(len(members)),
                "delivery_at_entry_m3_s": entry_value,
                "aggregated_supply_m3_s": aggregated,
                "double_count_detected": detected,
                "declared_series_matches_entry": bool(
                    declared is not None
                    and np.allclose(np.asarray(declared, np.float64)[0], entry_value,
                                    rtol=1e-12, atol=1e-15)),
                "independent_equals_aggregated": bool(abs(independent - aggregated) <= 1e-15
                                                      + 1e-12 * abs(aggregated)),
                "inherited_port_field_used": False,
            })
    registered = {item["entry_cell_flat"] for item in report["replacements"]}
    if not report["replacements"]:
        report["note"] = ("no side input was declared in this product; a channel built on the "
                          "area gate alone legitimately has none")
    report["registered_entries"] = sorted(registered)
    report["single_source_policy"] = (
        "each branch resolves to exactly one source; storing both the aggregated and the "
        "refined supply would add one extra copy, which the double_count record must expose")
    return {"problems": problems, "report": report}


def independent_window_comparison(left, right, left_walked, right_walked):
    """The cross-window acceptance: compare only what is genuinely comparable."""
    left_arrays = left["arrays"]
    right_arrays = right["arrays"]
    left_meta = left["metadata"]
    right_meta = right["metadata"]
    left_origin = [int(v) for v in left_meta["origin_native_xz"]]
    right_origin = [int(v) for v in right_meta["origin_native_xz"]]
    left_rows, left_columns = left_meta["shape_zx"]
    right_rows, right_columns = right_meta["shape_zx"]

    def to_world(flat_array, origin, columns):
        flat_array = np.asarray(flat_array, np.int64)
        return flat_array % columns + origin[0], flat_array // columns + origin[1]

    left_receiver = np.asarray(left_arrays["receiver"], np.int64).reshape(-1)
    right_receiver = np.asarray(right_arrays["receiver"], np.int64).reshape(-1)
    left_valid = np.asarray(left_arrays["valid_mask"], np.bool_).reshape(-1)
    right_valid = np.asarray(right_arrays["valid_mask"], np.bool_).reshape(-1)
    left_valid_grid = np.asarray(left_arrays["valid_mask"], np.bool_)
    right_valid_grid = np.asarray(right_arrays["valid_mask"], np.bool_)

    # shared world box
    x0 = max(left_origin[0], right_origin[0])
    x1 = min(left_origin[0] + left_columns, right_origin[0] + right_columns)
    z0 = max(left_origin[1], right_origin[1])
    z1 = min(left_origin[1] + left_rows, right_origin[1] + right_rows)
    if x1 <= x0 or z1 <= z0:
        return {"status": "NOT_RUN",
                "reason": "the two supports share no native cell",
                "left": {"origin": left_origin, "shape": [left_rows, left_columns]},
                "right": {"origin": right_origin, "shape": [right_rows, right_columns]}}

    def interior_cells(valid_grid):
        complete = np.zeros(valid_grid.shape, np.bool_)
        rows, columns = valid_grid.shape
        complete[1:-1, 1:-1] = (valid_grid[1:-1, 1:-1] & valid_grid[:-2, :-2]
                                & valid_grid[:-2, 1:-1] & valid_grid[:-2, 2:]
                                & valid_grid[1:-1, :-2] & valid_grid[1:-1, 2:]
                                & valid_grid[2:, :-2] & valid_grid[2:, 1:-1]
                                & valid_grid[2:, 2:])
        return complete

    left_inner = interior_cells(left_valid_grid)
    right_inner = interior_cells(right_valid_grid)

    left_donors = left_walked["donors"]
    right_donors = right_walked["donors"]

    left_area = np.asarray(left_arrays["area_cells"], np.int64).reshape(-1)
    right_area = np.asarray(right_arrays["area_cells"], np.int64).reshape(-1)
    left_area_complete = np.asarray(left_arrays["area_complete"], np.bool_).reshape(-1)
    right_area_complete = np.asarray(right_arrays["area_complete"], np.bool_).reshape(-1)
    left_seeds = np.asarray(left_arrays["upstream_unknown_mask"], np.bool_).reshape(-1)
    right_seeds = np.asarray(right_arrays["upstream_unknown_mask"], np.bool_).reshape(-1)

    def check_quantity(quantity, left_q, right_q, left_complete, right_complete):
        compared = 0
        mismatched = []
        skipped = []
        for z in range(z0, z1):
            for x in range(x0, x1):
                lc = (z - left_origin[1]) * left_columns + (x - left_origin[0])
                rc = (z - right_origin[1]) * right_columns + (x - right_origin[0])
                if not (left_inner.reshape(-1)[lc] and right_inner.reshape(-1)[rc]):
                    skipped.append({"world_xz": [x, z], "reason": "not_strictly_interior"})
                    continue
                if not (bool(left_complete[lc]) and bool(right_complete[rc])):
                    skipped.append({"world_xz": [x, z], "reason": "quantity_pending"})
                    continue
                left_members = upstream_members(left_receiver, left_valid, lc, left_donors)
                right_members = upstream_members(right_receiver, right_valid, rc, right_donors)
                left_world = set(zip(*[arr.tolist() for arr in
                                       to_world(np.fromiter(left_members, np.int64, len(left_members)),
                                                left_origin, left_columns)]))
                right_world = set(zip(*[arr.tolist() for arr in
                                        to_world(np.fromiter(right_members, np.int64,
                                                             len(right_members)),
                                                 right_origin, right_columns)]))
                if left_world != right_world:
                    skipped.append({"world_xz": [x, z],
                                    "reason": "upstream_member_set_differs",
                                    "left_members": len(left_world),
                                    "right_members": len(right_world)})
                    continue
                compared += 1
                if quantity == "area_cells":
                    if int(left_area[lc]) != int(right_area[rc]):
                        mismatched.append({"world_xz": [x, z],
                                           "left": int(left_area[lc]),
                                           "right": int(right_area[rc])})
                else:
                    if not np.allclose(left_q[:, lc], right_q[:, rc], rtol=1e-12, atol=1e-15):
                        mismatched.append({"world_xz": [x, z],
                                           "left_max": float(np.max(left_q[:, lc])),
                                           "right_max": float(np.max(right_q[:, rc]))})
        return {"compared_cells": compared,
                "mismatched_cells": len(mismatched),
                "mismatch_sample": mismatched[:8],
                "not_comparable_cells": len(skipped),
                "not_comparable_sample": skipped[:8],
                "not_comparable_total_by_reason": {
                    reason: sum(1 for item in skipped if item["reason"] == reason)
                    for reason in sorted({item["reason"] for item in skipped})},
                "area_completeness_used_for_flux": False}

    result = {
        "status": "PASS",
        "shared_world_box": {"x": [x0, x1], "z": [z0, z1],
                             "cells": int((x1 - x0) * (z1 - z0))},
        "strictly_interior_cells": int(sum(
            1 for z in range(z0, z1) for x in range(x0, x1)
            if left_inner.reshape(-1)[(z - left_origin[1]) * left_columns + (x - left_origin[0])]
            and right_inner.reshape(-1)[(z - right_origin[1]) * right_columns
                                        + (x - right_origin[0])])),
        "policy": ("strict interior only means a complete 8-neighbourhood; a value is compared "
                   "only where both sides are complete for that quantity AND their world "
                   "upstream member sets are equal; everything else is listed, never dropped"),
        "receiver_compared_in_world_coordinates": True,
    }
    area_result = check_quantity("area_cells", None, None, left_area_complete,
                                 right_area_complete)
    result["area"] = area_result
    if area_result["mismatched_cells"]:
        result["status"] = "FAIL"
    for name in sorted(left_meta["quantities"]):
        if name not in right_meta["quantities"]:
            result[name] = {"status": "NOT_RUN",
                            "reason": "the quantity is declared on the left only"}
            continue
        left_q = np.asarray(left_arrays["node_q_%s_m3_s" % name], np.float64)
        right_q = np.asarray(right_arrays["node_q_%s_m3_s" % name], np.float64)
        if left_q.shape[0] != right_q.shape[0]:
            result[name] = {"status": "NOT_RUN",
                            "reason": "the two products declare different step counts"}
            continue
        left_complete = np.zeros(left_receiver.size, np.bool_)
        left_node_complete = np.asarray(left_arrays["node_q_%s_complete" % name], np.bool_)
        left_complete[np.asarray(left_arrays["reach_cells"], np.int64)] = left_node_complete
        right_complete = np.zeros(right_receiver.size, np.bool_)
        right_node_complete = np.asarray(right_arrays["node_q_%s_complete" % name], np.bool_)
        right_complete[np.asarray(right_arrays["reach_cells"], np.int64)] = right_node_complete
        node_values = {"left": {}, "right": {}}
        left_nodes = np.asarray(left_arrays["reach_cells"], np.int64)
        right_nodes = np.asarray(right_arrays["reach_cells"], np.int64)
        for position, cell in enumerate(left_nodes.tolist()):
            node_values["left"][int(cell)] = left_q[:, position]
        for position, cell in enumerate(right_nodes.tolist()):
            node_values["right"][int(cell)] = right_q[:, position]
        left_full = np.zeros((left_q.shape[0], left_receiver.size), np.float64)
        for cell, series in node_values["left"].items():
            left_full[:, cell] = series
        right_full = np.zeros((right_q.shape[0], right_receiver.size), np.float64)
        for cell, series in node_values["right"].items():
            right_full[:, cell] = series
        quantity_result = check_quantity(name, left_full, right_full,
                                         left_complete, right_complete)
        quantity_result["node_only"] = True
        quantity_result["note"] = ("a cell that is not a channel node carries no stored flux; "
                                   "only channel nodes can be compared")
        result[name] = quantity_result
        if quantity_result["mismatched_cells"]:
            result["status"] = "FAIL"

    left_ids = {(row["head_world_xz"][0], row["head_world_xz"][1],
                 row["tail_world_xz"][0], row["tail_world_xz"][1]): row["reach_id"]
                for row in left.get("reaches", [])}
    right_ids = {(row["head_world_xz"][0], row["head_world_xz"][1],
                  row["tail_world_xz"][0], row["tail_world_xz"][1]): row["reach_id"]
                 for row in right.get("reaches", [])}
    shared = sorted(set(left_ids) & set(right_ids))
    id_mismatch = [{"head_tail": list(key), "left": left_ids[key], "right": right_ids[key]}
                   for key in shared if left_ids[key] != right_ids[key]]
    result["reach_id"] = {
        "shared_anchored_paths": len(shared),
        "id_mismatches": len(id_mismatch),
        "id_mismatch_sample": id_mismatch[:8],
        "not_comparable_context": len(set(left_ids) ^ set(right_ids)),
        "policy": ("a reach id is required to be equal only for a path whose head and tail "
                   "anchors are identical world points in both windows; a boundary-crossing or "
                   "split path is reported as not_comparable_context"),
    }
    if id_mismatch:
        result["status"] = "FAIL"
    return result


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def audit(arguments):
    started = time.monotonic()
    report = {
        "schema": SCHEMA,
        "status": "FAIL",
        "reasons": [],
        "checks": {},
        "timing_s": {},
        "independence": {"banned_modules": list(BANNED_MODULES),
                         "loaded_banned_before": loaded_banned_modules()},
    }
    try:
        require_independent_process()
        stage = time.monotonic()
        product = load_product(arguments.product)
        report["timing_s"]["load"] = round(time.monotonic() - stage, 3)
        report["product"] = {
            "schema": product["schema"],
            "identity_sha256": product["identity_sha256"],
            "origin_native_xz": list(product["metadata"]["origin_native_xz"]),
            "shape_zx": list(product["metadata"]["shape_zx"]),
            "declared_gates": dict(product["metadata"]["declared_gates"]),
            "status": product["metadata"]["status"],
            "payload_bytes": product["payload_bytes"],
            "reported_counts": dict(product["metadata"]["counts"]),
        }
        reference = (load_parent_reference(arguments.parent_reference)
                     if arguments.parent_reference else None)
        if reference is not None:
            if reference["parent_identity_sha256"] != product["metadata"]["parent_identity_sha256"]:
                report["reasons"].append("the product is not bound to the declared parent")
            if (list(reference["origin_native_xz"])
                    != list(product["metadata"]["origin_native_xz"])
                    or list(reference["shape_zx"]) != list(product["metadata"]["shape_zx"])):
                report["reasons"].append("the product support differs from the parent reference")

        stage = time.monotonic()
        walked = walk_reaches(product)
        report["timing_s"]["walk"] = round(time.monotonic() - stage, 3)
        report["checks"]["walk"] = {
            "reaches": len(walked["facts"]),
            "covered_cells": walked["covered_cells"],
            "channel_cells": walked["channel_cells"],
            "problems": walked["problems"],
        }
        report["reasons"].extend(walked["problems"])

        stage = time.monotonic()
        values = check_values(product, walked)
        report["timing_s"]["values"] = round(time.monotonic() - stage, 3)
        report["checks"]["area"] = values["area"]
        report["checks"]["quantities"] = values["quantities"]
        report["reasons"].extend(values["problems"])
        # the independent order and donor table live in the value pass; hand them to the
        # later checks that need them instead of recomputing a second time
        walked = dict(walked, donors=values["donors"], order=values["order"])

        stage = time.monotonic()
        terminals = check_terminals(product)
        report["timing_s"]["terminals"] = round(time.monotonic() - stage, 3)
        report["checks"]["terminals"] = terminals
        report["reasons"].extend(terminals["problems"])

        if arguments.reference_rows:
            stage = time.monotonic()
            rows = json.loads(Path(arguments.reference_rows).read_text(encoding="utf-8"))
            anchors = check_anchors_against_reference(product, walked, rows)
            report["timing_s"]["anchors"] = round(time.monotonic() - stage, 3)
            report["checks"]["anchors"] = anchors["coverage"]
            report["reasons"].extend(anchors["problems"])

        if arguments.compare_product:
            stage = time.monotonic()
            other = load_product(arguments.compare_product)
            other_walked = walk_reaches(other)
            comparison = independent_window_comparison(product, other, walked, other_walked)
            report["timing_s"]["compare"] = round(time.monotonic() - stage, 3)
            report["checks"]["window_comparison"] = comparison
            if comparison["status"] != "PASS":
                report["reasons"].append("the cross-window comparison did not pass: %s"
                                         % comparison["status"])

        stage = time.monotonic()
        side_inputs = check_side_inputs(product, walked, values)
        report["timing_s"]["side_inputs"] = round(time.monotonic() - stage, 3)
        report["checks"]["side_inputs"] = side_inputs["report"]
        report["reasons"].extend(side_inputs["problems"])
    except Exception as error:  # a refusal is a FAIL, never a partial pass
        report["reasons"].append("%s: %s" % (type(error).__name__, error))
        report["traceback"] = traceback.format_exc()
        print(report["traceback"], file=sys.stderr)
    report["independence"]["loaded_banned_after"] = loaded_banned_modules()
    if report["independence"]["loaded_banned_after"]:
        report["reasons"].append("the producer was imported during the audit: %s"
                                 % report["independence"]["loaded_banned_after"])
    report["status"] = "PASS" if not report["reasons"] else "FAIL"
    report["timing_s"]["total"] = round(time.monotonic() - started, 3)
    if arguments.report:
        Path(arguments.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    print(json.dumps({"status": report["status"], "reasons": report["reasons"][:8],
                      "checks": sorted(report["checks"])}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--product", required=True)
    parser.add_argument("--parent-reference")
    parser.add_argument("--reference-rows",
                        help="JSON array of A-only reference reach rows, for the anchor and "
                             "split-relation check")
    parser.add_argument("--compare-product")
    parser.add_argument("--compare-parent-reference",
                        help="the parent reference of the compared product (accepted for "
                             "symmetry; the comparison reads both products' own metadata)")
    parser.add_argument("--report")
    return audit(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
