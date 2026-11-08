"""Independent cold audit of saved lake/spill graphs and their review artifacts.

Accepted parent audits cover old water ledgers. This tool reads pinned arrays,
not event loaders with solver-backed validators, and never generates a graph,
forest, route, terrain, or event. Stage coverage permits zero-depth endpoints.
"""

import argparse
from collections import deque
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from unittest.mock import patch

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, publish_bytes


PARENT_SHA = "9091396732558f7b795888bd83c86713c3e8c9e644768c3b8cb801ab9b152437"
PARENT_AUDIT_SHA = "636f619b0661bb0bb50ccd8bb9f242dae255f4a6a202f9c64a7162af889adbf6"
BASELINE_SHA = "cd78c2f2ce9c6a1abbd98ae7ee528079dfb2ee1b5ce2905458e64137aa868e5f"
CODE = {'terrain_pipeline/basin_topology.py', 'terrain_pipeline/basin_topology.py',
        'terrain_pipeline/basin_topology.py', "tools/prepare_td_lake_spill_graph.py"}
FLAGS = {"hydraulic_ready", "natural_outlet_verified", "publishable", "permanent_trunk_ready",
         "hydraulic_verified", "permanent_river_verified", "channel_verified", "is_terrestrial_river",
         "is_sea_outlet", "bed_modified", "solver_advanced", "bed_changed", "water_generated",
         "generation_requested"}
MIN_VOLUME = 1e-6
TOLERANCE = .01
FORBIDDEN = (
    'terrain_pipeline.basin_topology.build_lake_spill_graph',
    'terrain_pipeline.basin_topology.face_evidence',
    'terrain_pipeline.basin_topology.sampled_stage',
    'terrain_pipeline.basin_topology.build_outlet_forest',
    'terrain_pipeline.basin_topology.trace_spill_connection',
    'terrain_pipeline.basin_topology.trace_engineering_outlet',
    'terrain_pipeline.basin_topology.build_outlet_forest',
    'terrain_pipeline.basin_topology.trace_spill_connection',
    'terrain_pipeline.basin_topology.trace_engineering_outlet',
    "tools.prepare_td_lake_spill_graph.run",
    "tools.prepare_td_lake_spill_graph.build_lake_spill_graph",
    "tools.prepare_td_lake_spill_graph.main_route_support",
    "tools.prepare_td_lake_spill_graph.frontier_requests",
    "tools.prepare_td_lake_spill_graph.build_review_case",
    'terrain_pipeline.basin_topology.build_basin_hierarchy',
    'terrain_pipeline.basin_storage.build_overflow_topology',
    'terrain_pipeline.basin_storage.simulate_overflow',
    'terrain_pipeline.basin_storage.simulate_runoff_exchange',
    'terrain_pipeline.runoff.simulate_rainfall_runoff',
    'scipy.integrate.Radau',
    'terrain_pipeline.basin_storage.load_runoff_exchange',
    'terrain_pipeline.basin_storage.validate_runoff_exchange',
    'terrain_pipeline.basin_storage.simulate_radau_overflow',
    'scipy.integrate.Radau',
    'terrain_pipeline.runoff.simulate_rainfall_runoff',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def read_json(path):
    def pairs(items):
        record = {}
        for key, value in items:
            require(key not in record, "duplicate JSON key: " + key)
            record[key] = value
        return record

    def finite(value):
        parsed = float(value)
        require(math.isfinite(parsed), "nonfinite JSON number")
        return parsed

    def constant(value):
        raise ValueError("nonfinite JSON constant: " + value)

    require(path.stat().st_size <= 128 * 1024**2, "JSON exceeds audit byte budget")
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_float=finite,
                      parse_constant=constant)


def pinned_path(pin, base, seen, *, local=False):
    path = (base / pin["path"]).resolve(strict=True)
    require(path.is_relative_to(base.resolve() if local else ROOT.resolve()), "pin escapes allowed directory")
    sha = pin["sha256"]
    require(isinstance(sha, str) and len(sha) == 64 and
            all(character in "0123456789abcdef" for character in sha), "invalid SHA256 pin")
    require(file_sha256(path) == sha, "SHA256 mismatch: " + str(path))
    require(path not in seen or seen[path] == sha, "contradictory file pins")
    if "bytes" in pin:
        require(pin["bytes"] == path.stat().st_size, "pin size mismatch")
    seen[path] = sha
    return path


def pinned_json(pin, base, seen, *, local=False):
    return read_json(pinned_path(pin, base, seen, local=local))


def equal(actual, expected, label):
    if isinstance(expected, dict):
        require(isinstance(actual, dict), label + ": expected object")
        for key, value in expected.items():
            require(key in actual, label + ": missing " + key)
            equal(actual[key], value, label + "." + key)
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(actual) == len(expected), label + ": list coverage mismatch")
        for position, (left, right) in enumerate(zip(actual, expected)):
            equal(left, right, f"{label}[{position}]")
    elif isinstance(expected, float):
        require(type(actual) in (int, float) and math.isfinite(actual) and
                math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10), label + ": numeric mismatch")
    else:
        require(type(actual) is type(expected) and actual == expected, label + ": value mismatch")


def flags(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FLAGS:
                require(child is False, "uncertified/mutation flag: " + key)
            flags(child)
    elif isinstance(value, list):
        for child in value:
            flags(child)


def bundle(pin, base, seen):
    path = pinned_path(pin, base, seen)

    def verify_identity(result):
        require(result["identity_sha256"] == pin["identity_sha256"] ==
                identity(result["arrays"], result["metadata"]), "saved bundle identity mismatch")

    return load_bundle(path, expected_sha256=pin["sha256"], validator=verify_identity)


def same_pin(actual, expected, actual_base, expected_base, seen):
    require(actual["sha256"] == expected["sha256"] and
            actual.get("identity_sha256") == expected.get("identity_sha256"), "input differs from accepted parent")
    require(pinned_path(actual, actual_base, seen) == pinned_path(expected, expected_base, seen),
            "input path differs from accepted parent")


def xyz(hierarchy, cells):
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    columns = arrays["height_m"].shape[1]
    spacing, origin = metadata["spacing_m"], metadata["origin_m_xz"]
    return [[float(origin[0] + (cell % columns) * spacing), float(arrays["height_m"].ravel()[cell]),
             float(origin[1] + (cell // columns) * spacing)] for cell in cells]


def d4(first, second, columns):
    return abs(first // columns - second // columns) + abs(first % columns - second % columns) == 1


def physical_face(hierarchy, face):
    arrays = hierarchy["arrays"]
    position = face["face_index"]
    require(type(position) is int and 0 <= position < len(arrays["face_cells"]), "invalid hierarchy face index")
    cells = face["cell_ids"]
    require(cells == arrays["face_cells"][position].tolist() and len(cells) == 2, "physical face cells mismatch")
    require(all(type(cell) is int and 0 <= cell < arrays["height_m"].size for cell in cells), "invalid face cells")
    require(d4(*cells, arrays["height_m"].shape[1]), "physical face is not D4")
    require(arrays["valid_mask"].ravel()[cells].all(), "invalid physical face")
    require(face["leaf_ids"] == sorted(arrays["contribution_owner"].ravel()[cells].tolist()) and
            len(set(face["leaf_ids"])) == 2, "physical face owners mismatch")
    require(face["sill_m"] == float(arrays["height_m"].ravel()[cells].max()) ==
            float(arrays["face_level_m"][position]), "physical sill mismatch")
    endpoints = [[float(value).hex() for value in point] for point in xyz(hierarchy, cells)]
    require(face["face_id"] == "face:" + digest([hierarchy["metadata"]["source_identity_sha256"],
                                               sorted(endpoints)]), "physical face ID mismatch")


def physical_boundary(hierarchy, boundary):
    arrays = hierarchy["arrays"]
    cell = boundary["cell_id"]
    require(type(cell) is int and 0 <= cell < arrays["height_m"].size, "invalid engineering boundary cell")
    row, column = divmod(cell, arrays["height_m"].shape[1])
    rows, columns = arrays["height_m"].shape
    sides = int(row == 0) + int(row == rows - 1) + int(column == 0) + int(column == columns - 1)
    require(sides > 0 and arrays["open_boundary_mask"].ravel()[cell] and
            arrays["valid_mask"].ravel()[cell], "engineering boundary not valid open perimeter")
    require(boundary["leaf_id"] == int(arrays["contribution_owner"].ravel()[cell]), "engineering boundary owner mismatch")
    matches = np.flatnonzero(arrays["boundary_cells"] == cell)
    require(len(matches) == 1, "engineering boundary not exact hierarchy boundary")
    require(boundary["sill_m"] == float(arrays["height_m"].ravel()[cell]) ==
            float(arrays["boundary_level_m"][matches[0]]), "engineering sill mismatch")
    require(boundary["width_m"] == sides * hierarchy["metadata"]["spacing_m"], "engineering width mismatch")
    if "face_count" in boundary:
        equal(boundary["face_count"], sides, "engineering face_count")


class RouteRefusal(ValueError):
    pass


def route_cells(hierarchy, first, leaf, budget):
    arrays = hierarchy["arrays"]
    unknown = arrays["node_unknown_contact"]
    if not 0 <= leaf < len(unknown) or unknown[leaf] or np.any(arrays["node_parent"] == leaf):
        raise RouteRefusal("unknown or non-leaf route owner")
    flat = {key: arrays[key].ravel() for key in
            ("height_m", "valid_mask", "protected_mask", "contribution_owner", "cell_owner", "receiver")}
    cells, visited = [], set()
    current = first
    while True:
        if not 0 <= current < len(flat["height_m"]):
            raise RouteRefusal("receiver outside grid")
        node = int(flat["cell_owner"][current])
        if (not flat["valid_mask"][current] or flat["protected_mask"][current] or
                int(flat["contribution_owner"][current]) != leaf or not 0 <= node < len(unknown) or
                unknown[node] or not np.isfinite(flat["height_m"][current])):
            raise RouteRefusal("route crosses invalid, protected, unknown or foreign owner")
        if current in visited or len(cells) >= budget:
            raise RouteRefusal("route cycle or sample budget")
        cells.append(current)
        visited.add(current)
        target = int(flat["receiver"][current])
        if target == -1:
            if node != leaf:
                raise RouteRefusal("terminal owner mismatch")
            return cells
        if not 0 <= target < len(flat["height_m"]) or not d4(current, target, arrays["height_m"].shape[1]):
            raise RouteRefusal("receiver not D4")
        if flat["height_m"][target] > flat["height_m"][current]:
            raise RouteRefusal("receiver climbs terrain")
        current = target


def geometry(hierarchy, stored, face, source, receiver, stage, *, engineering=False):
    require(isinstance(stored, dict), "missing sampled geometry")
    equal(stored, {"schema": "td-lake-spill-geometry-v1",
                   "kind": "engineering_outlet" if engineering else "basin_spill_connection",
                   "coordinate_system": "model_xyz_m_original_bed", "bed_modified": False,
                   "hydraulic_verified": False, "permanent_river_verified": False,
                   "natural_outlet_verified": False}, "geometry contract")
    try:
        owners = hierarchy["arrays"]["contribution_owner"].ravel()
        if engineering:
            first = face["cell_id"]
        else:
            first = next(cell for cell in face["cell_ids"] if owners[cell] == source)
        upstream = route_cells(hierarchy, first, source, 2048)
        heights = hierarchy["arrays"]["height_m"].ravel()[upstream]
        required = max(face["sill_m"], float(heights.max()))
        if stage < required:
            raise RouteRefusal("stage does not cover sill and source samples")
        downstream = []
        if not engineering:
            second = next(cell for cell in face["cell_ids"] if owners[cell] == receiver)
            downstream = route_cells(hierarchy, second, receiver, 2048 - len(upstream))
    except RouteRefusal:
        require(stored["status"] == "rejected" and isinstance(stored["reason"], str) and
                bool(stored["reason"]), "unsafe route not rejected with reason")
        return False
    require(stored["status"] == "accepted" and stored["reason"] is None, "valid sampled route unexpectedly rejected")
    equal(stored, {"source_leaf_id": source, "source_stage_m": float(stage), "sill_m": float(face["sill_m"]),
                   "source_sinkcell": upstream[-1], "path_cell_count": len(upstream) + len(downstream)}, "geometry identity")
    wet_cells = list(reversed(upstream))
    equal(stored["source_lake_approach"], {"kind": "sampled_submerged_lake_approach", "cell_ids": wet_cells,
          "xyz_m": xyz(hierarchy, wet_cells), "source_stage_m": float(stage), "required_stage_m": float(required),
          "all_samples_stage_covered": True, "all_samples_submerged": bool(np.all(heights < stage)),
          "is_terrestrial_river": False}, "source sampled wet approach")
    if engineering:
        equal(stored, {"boundary_cell_id": first, "width_m": float(face["width_m"]),
                       "is_engineering": True, "is_sea_outlet": False}, "engineering geometry")
    else:
        equal(stored, {"receiver_leaf_id": receiver, "dest_sinkcell": downstream[-1],
                       "face_id": face["face_id"], "face_index": face["face_index"]}, "spill geometry")
        equal(stored["downhill_terrain_approach"], {"kind": "downhill_terrain_support_pending_channel",
              "cell_ids": downstream, "xyz_m": xyz(hierarchy, downstream), "channel_verified": False}, "downhill support")
        equal(stored["cross_face"], {"cell_ids": [first, second], "xyz_m": xyz(hierarchy, [first, second])}, "cross-face geometry")
    return True


def face_verdict(event, reference, position):
    forward = event["arrays"]["face_forward_m3"][:, position]
    reverse = event["arrays"]["face_reverse_m3"][:, position]
    ref_forward = reference["arrays"]["face_forward_m3"][:, position]
    ref_reverse = reference["arrays"]["face_reverse_m3"][:, position]
    net, ref_net = forward - reverse, ref_forward - ref_reverse
    gross = forward + reverse
    active = np.flatnonzero(gross >= MIN_VOLUME)
    significant = np.maximum(gross, ref_forward + ref_reverse) >= MIN_VOLUME
    signs = np.sign(net[active])
    nonzero = signs[signs != 0]
    switches = int(np.sum(nonzero[1:] != nonzero[:-1]))
    direction = int(np.sign(net.sum()))
    late_start = int(len(net) * .8)
    late = float(net[late_start:].sum())
    late_reference = float(ref_net[late_start:].sum())
    late_absolute = float(np.abs(net[late_start:]).sum())
    consistency = max(0., direction * late / late_absolute) if late_absolute else 0.
    delta = np.abs(net[significant] - ref_net[significant])
    relative = float(delta.sum() / max(float(np.abs(ref_net[significant]).sum()), MIN_VOLUME))
    interval_error = float(np.max(delta / np.maximum(np.abs(ref_net[significant]), MIN_VOLUME))) if len(delta) else 0.
    reasons = []
    conditions = [
        (not len(active) or direction == 0, "no_significant_directional_transfer"),
        (switches > 0, "saved_interval_direction_switches"),
        (direction * float(net.sum()) < (1 - TOLERANCE) * float(gross.sum()), "cancellation_exceeds_one_percent"),
        (direction * late < MIN_VOLUME or direction * late_reference < MIN_VOLUME, "no_same_direction_late_reception"),
        (consistency < 1 - TOLERANCE, "late_direction_not_consistent"),
        (relative > TOLERANCE or interval_error > TOLERANCE, "per_face_time_refinement_failed"),
        (not np.array_equal(np.sign(net[significant]), np.sign(ref_net[significant])), "refinement_direction_disagreement"),
    ]
    for failed, reason in conditions:
        if failed:
            reasons.append(reason)
    return {"stable_relationship": not reasons, "direction": direction,
            "forward_m3": float(forward.sum()), "reverse_m3": float(reverse.sum()),
            "net_m3": float(net.sum()), "gross_m3": float(gross.sum()),
            "canceled_m3": float(2 * min(forward.sum(), reverse.sum())),
            "active_interval_sign_switches": switches, "first_active_interval": int(active[0]) if len(active) else None,
            "last_active_interval": int(active[-1]) if len(active) else None, "late_start_interval": late_start,
            "late_net_m3": late, "late_direction_consistency": consistency,
            "interval_net_relative_l1_difference": relative, "max_interval_net_relative_difference": interval_error,
            "rejection_reasons": reasons}


def sample_stage(event, position, transfer):
    active = np.flatnonzero(transfer >= MIN_VOLUME)
    if not len(active):
        return None
    indices = np.unique(np.concatenate((active, active + 1)))
    selected = int(indices[np.argmax(event["arrays"]["stage_m"][indices, position])])
    return {"saved_index": selected, "time_s": float(selected * 300.),
            "stage_m": float(event["arrays"]["stage_m"][selected, position])}


def ranges(mask):
    result = []
    for position in np.flatnonzero(mask).tolist():
        if result and result[-1][1] == position:
            result[-1][1] += 1
        else:
            result.append([position, position + 1])
    return result


def forest_checks(graph, leaves, areas, blocked):
    forest = graph["routing_forest"]
    records = {record["leaf_id"]: record for record in forest["records"]}
    equal([record["leaf_id"] for record in forest["records"]], sorted(leaves), "forest leaf coverage")
    seeds = {}
    for outlet in graph["outlets"]:
        if not outlet["routing_eligible"]:
            continue
        leaf = outlet["leaf_id"]
        candidate = {"leaf_id": leaf, "cell_id": outlet["cell_id"], "outflow_m3": outlet["outflow_m3"]}
        if leaf not in seeds or (-candidate["outflow_m3"], candidate["cell_id"]) < (-seeds[leaf]["outflow_m3"], seeds[leaf]["cell_id"]):
            seeds[leaf] = candidate
    directed = [{"face_id": edge["face_id"], "source_leaf_id": edge["source_leaf_id"],
                 "receiver_leaf_id": edge["receiver_leaf_id"], "net_m3": abs(edge["ordinary"]["net_m3"])}
                for edge in graph["edges"] if edge["routing_eligible"]]
    directed.sort(key=lambda edge: edge["face_id"])
    incoming = {leaf: [] for leaf in leaves}
    outgoing = {leaf: [] for leaf in leaves}
    for edge in directed:
        incoming[edge["receiver_leaf_id"]].append(edge["source_leaf_id"])
        outgoing[edge["source_leaf_id"]].append(edge)
    distance = {leaf: 0 for leaf in seeds}
    queue = deque(sorted(seeds))
    while queue:
        receiver = queue.popleft()
        for source in incoming[receiver]:
            if source not in blocked and source not in distance:
                distance[source] = distance[receiver] + 1
                queue.append(source)
    children = {leaf: [] for leaf in leaves}
    for leaf in sorted(leaves, key=lambda item: (distance.get(item, math.inf), item)):
        record = records[leaf]
        if leaf not in distance:
            equal(record, {"reachable": False, "parent_leaf_id": None, "parent_face_id": None,
                           "root_leaf_id": None, "root_boundary_cell_id": None, "hops": None,
                           "supported_area_m2": 0., "reason": "blocked" if leaf in blocked else
                           "no_event_supported_route_to_export"}, "unreachable forest record")
            continue
        equal(record, {"reachable": True, "hops": distance[leaf], "reason": None}, "reachable forest record")
        if distance[leaf] == 0:
            equal(record, {"parent_leaf_id": None, "parent_face_id": None,
                           "root_leaf_id": leaf, "root_boundary_cell_id": seeds[leaf]["cell_id"]}, "forest root")
        else:
            candidates = [edge for edge in outgoing[leaf] if distance.get(edge["receiver_leaf_id"]) == distance[leaf] - 1]
            selected = min(candidates, key=lambda edge: (records[edge["receiver_leaf_id"]]["root_leaf_id"],
                records[edge["receiver_leaf_id"]]["root_boundary_cell_id"], -edge["net_m3"],
                edge["face_id"], edge["receiver_leaf_id"]))
            parent = records[selected["receiver_leaf_id"]]
            equal(record, {"parent_leaf_id": parent["leaf_id"], "parent_face_id": selected["face_id"],
                           "root_leaf_id": parent["root_leaf_id"],
                           "root_boundary_cell_id": parent["root_boundary_cell_id"]}, "forest parent/tie choice")
            children[parent["leaf_id"]].append(leaf)
    descendants = {}
    for leaf in sorted(distance, key=lambda item: (-distance[item], item)):
        members = {leaf}
        for child in children[leaf]:
            require(members.isdisjoint(descendants[child]), "forest double-counted descendant area")
            members.update(descendants[child])
        descendants[leaf] = members
        equal(records[leaf]["supported_area_m2"], float(math.fsum(areas[item] for item in sorted(members))), "forest supported area")
    components = []
    assigned = set()
    for root in sorted(seeds):
        members = sorted(descendants[root])
        require(assigned.isdisjoint(members), "forest components overlap")
        assigned.update(members)
        components.append({"root_leaf_id": root, "root_boundary_cell_id": seeds[root]["cell_id"],
                           "leaf_ids": members, "area_m2": float(math.fsum(areas[item] for item in members)),
                           "leaf_count": len(members), "outlet": seeds[root]})
    require(assigned == set(distance), "forest component coverage mismatch")
    equal(forest["components"], components, "forest unique components")
    primary = min(components, key=lambda item: (-item["area_m2"], -item["outlet"]["outflow_m3"],
                  item["root_boundary_cell_id"], item["root_leaf_id"])) if components else None
    equal(forest["primary_component"], primary, "primary component")
    path = []
    if primary is not None:
        current = primary["root_leaf_id"]
        while True:
            path.append(current)
            if not children[current]:
                break
            current = min(children[current], key=lambda child: (-records[child]["supported_area_m2"], child))
    equal(forest["main_path"], path, "root-first main path")
    equal(forest["main_path_face_ids"], [records[leaf]["parent_face_id"] for leaf in reversed(path[1:])], "source-first main faces")
    ordered = sorted(leaves)
    indices = {leaf: position for position, leaf in enumerate(ordered)}
    adjacency = csr_matrix(([1] * len(directed),
        ([indices[edge["source_leaf_id"]] for edge in directed], [indices[edge["receiver_leaf_id"]] for edge in directed])),
        shape=(len(ordered), len(ordered)))
    groups = {}
    if ordered:
        _, labels = connected_components(adjacency, directed=True, connection="strong")
        for leaf, label in zip(ordered, labels):
            groups.setdefault(int(label), []).append(leaf)
    strong = sorted(groups.values())
    cyclic = [group for group in strong if len(group) > 1]
    equal(forest["graph_diagnostics"], {"directed_edges": directed, "leaf_count": len(leaves),
          "edge_count": len(directed), "strong_components": strong, "cyclic_components": cyclic,
          "has_cycles": bool(cyclic), "blocked_leaf_ids": sorted(blocked)}, "forest original-graph diagnostics")
    for name in ("permanent_trunk_ready", "hydraulic_ready", "natural_outlet_verified", "publishable"):
        require(forest.get(name) is False, "missing/true forest uncertified flag")


def route_support(graph, topology, ordinary):
    support = graph["main_route_support"]
    forest = graph["routing_forest"]
    primary = forest["primary_component"]
    if primary is None:
        equal(support, {"path_face_ids": [], "positive_intervals": [], "positive_duration_s": 0.}, "empty main support")
        return {"faces": [], "boundary": None, "common_positive_intervals": []}
    mask = np.ones(ordinary["metadata"]["steps"], dtype=bool)
    positions = {face["face_id"]: position for position, face in enumerate(topology["faces"])}
    edges = {edge["face_id"]: edge for edge in graph["edges"]}
    witnesses = []
    for face_id in forest["main_path_face_ids"]:
        position = positions[face_id]
        signed = ordinary["arrays"]["face_forward_m3"][:, position] - ordinary["arrays"]["face_reverse_m3"][:, position]
        directional = signed * edges[face_id]["ordinary"]["direction"]
        positive = directional >= MIN_VOLUME
        mask &= positive
        witnesses.append({"face_id": face_id, "direction": edges[face_id]["ordinary"]["direction"],
                          "directional_net_m3": directional.tolist(), "positive_intervals": ranges(positive)})
    position = next(position for position, boundary in enumerate(topology["engineering_boundaries"])
                    if boundary["cell_id"] == primary["root_boundary_cell_id"])
    outflow = ordinary["arrays"]["engineering_boundary_outflow_m3"][:, position]
    mask &= outflow >= MIN_VOLUME
    equal(support, {"path_face_ids": forest["main_path_face_ids"], "root_boundary_cell_id": primary["root_boundary_cell_id"],
                   "positive_intervals": ranges(mask), "positive_duration_s": float(mask.sum() * 300.),
                   "saved_index_for_review": int(np.flatnonzero(mask)[-1] + 1) if mask.any() else len(mask)}, "main interval intersection")
    return {"faces": witnesses, "boundary": {"cell_id": primary["root_boundary_cell_id"],
            "outflow_m3": outflow.tolist(), "positive_intervals": ranges(outflow >= MIN_VOLUME)},
            "common_positive_intervals": ranges(mask),
            "semantics": "saved interval net-transfer support only; not instantaneous positive depth, travel time or permanent river"}


def frontier_checks(graph):
    primary = graph["routing_forest"]["primary_component"]
    expected = []
    mismatches = []
    if primary is not None:
        members = set(primary["leaf_ids"])
        nodes = {node["leaf_id"]: node for node in graph["nodes"]}
        for edge in graph["edges"]:
            first, second = edge["leaf_ids"]
            if (first in members) == (second in members):
                continue
            source, receiver = (second, first) if first in members else (first, second)
            if nodes[source]["blocked_reasons"] or nodes[receiver]["blocked_reasons"]:
                continue
            direction = 1 if source == first else -1
            observed_geometry = edge["geometry"]
            expected.append({"face_id": edge["face_id"], "face_cell_ids": edge["cell_ids"],
                "source_leaf_id": source, "receiver_leaf_id": receiver,
                "upstream_exclusive_area_m2": nodes[source]["exclusive_area_m2"], "physical_sill_m": edge["sill_m"],
                "ordinary_net_toward_main_m3": float(direction * edge["ordinary"]["net_m3"]),
                "stage_gap_to_sill_m": float(max(0., edge["sill_m"] - nodes[source]["ordinary_stage_max_m"])),
                "ordinary_rejection_reasons": edge["ordinary"]["rejection_reasons"],
                "geometry_rejection_reason": None if observed_geometry is None else observed_geometry["reason"],
                "generation_requested": False})
            if observed_geometry is not None and edge["source_leaf_id"] != source:
                mismatches.append(edge["face_id"])
    expected.sort(key=lambda item: (item["ordinary_net_toward_main_m3"] <= 0., item["stage_gap_to_sill_m"],
                                  -item["upstream_exclusive_area_m2"], item["face_id"]))
    equal(graph["frontier_requests"], expected, "shared-face frontier census")
    return {"request_count": len(expected), "observed_geometry_opposes_request_face_ids": mismatches,
            "requested_direction_geometry_verified": False,
            "semantics": "legacy geometry_rejection_reason belongs to observed edge direction, not an independently evaluated inward request"}


def audit_case(case, review, hierarchy, topology, events):
    graph = case["_graph"]
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    ordinary, reference = events["ordinary"], events["ordinary_reference"]
    leaves = topology["arrays"]["leaf_ids"].tolist()
    areas = {leaf: float(area) for leaf, area in zip(leaves, topology["arrays"]["leaf_area_m2"])}
    lookup = {leaf: position for position, leaf in enumerate(leaves)}
    equal(graph, {"schema": "td-lake-spill-graph-v1", "algorithm": "saved-ordinary-stable-faces-retained-lakes-v1",
                 "source_identity_sha256": metadata["source_identity_sha256"],
                 "hierarchy_identity_sha256": hierarchy["identity_sha256"], "topology_identity_sha256": topology["identity_sha256"],
                 "event_identity_sha256": {key: event["identity_sha256"] for key, event in events.items()},
                 "thresholds": {"minimum_volume_m3": MIN_VOLUME, "relative_tolerance": TOLERANCE, "late_start_fraction": .8},
                 "solver_advanced": False, "bed_changed": False, "water_generated": False,
                 "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
                 "permanent_trunk_ready": False}, "graph provenance")
    flags(graph)
    equal([node["leaf_id"] for node in graph["nodes"]], leaves, "node coverage")
    owner = arrays["contribution_owner"].ravel()
    blocked = set()
    for node in graph["nodes"]:
        leaf = node["leaf_id"]
        cells = np.flatnonzero(arrays["valid_mask"].ravel() & (owner == leaf))
        sinks = cells[arrays["receiver"].ravel()[cells] < 0]
        require(len(sinks) == 1, "one sink required per contribution leaf")
        reasons = []
        if arrays["node_unknown_contact"][leaf]:
            reasons.append("unknown_contact")
        if arrays["protected_mask"].ravel()[cells].any():
            reasons.append("protected_basin")
        if reasons:
            blocked.add(leaf)
        equal(areas[leaf], float(np.sum(~arrays["protected_mask"].ravel()[cells]) * metadata["spacing_m"]**2), "exclusive valid unprotected area")
        stages = ordinary["arrays"]["stage_m"][:, lookup[leaf]]
        equal(node, {"kind": "retained_basin_storage", "terminal_cell_id": int(sinks[0]),
                     "terminal_xyz_m": xyz(hierarchy, [int(sinks[0])])[0], "exclusive_area_m2": areas[leaf],
                     "ordinary_stage_min_m": float(stages.min()), "ordinary_stage_max_m": float(stages.max()),
                     "ordinary_max_surface_volume_m3": float(ordinary["arrays"]["surface_volume_m3"][:, lookup[leaf]].max()),
                     "ordinary_runoff_supply_m3": float(ordinary["arrays"]["outflow_volume_m3"][:, lookup[leaf]].sum()),
                     "blocked_reasons": reasons}, "saved basin node")
    require(len(graph["edges"]) == len(topology["faces"]), "face census incomplete")
    for position, (edge, face) in enumerate(zip(graph["edges"], topology["faces"])):
        physical_face(hierarchy, face)
        equal(edge, face, "graph physical face")
        normal = face_verdict(ordinary, reference, position)
        storm = face_verdict(events["strong"], events["strong_reference"], position)
        equal(edge["ordinary"], normal, "ordinary per-face verdict")
        equal(edge["strong"], storm, "strong per-face verdict")
        equal(edge["strong_direction_agrees"], bool(normal["direction"] != 0 and normal["direction"] == storm["direction"]), "strong direction agreement")
        eligible = False
        if normal["stable_relationship"]:
            source, receiver = face["leaf_ids"] if normal["direction"] > 0 else face["leaf_ids"][::-1]
            directional = normal["direction"] * (ordinary["arrays"]["face_forward_m3"][:, position] -
                                                  ordinary["arrays"]["face_reverse_m3"][:, position])
            sample = sample_stage(ordinary, lookup[source], directional)
            equal(edge, {"source_leaf_id": source, "receiver_leaf_id": receiver, "sampled_source_stage": sample}, "sampled directional source")
            if sample is None:
                equal(edge["geometry"], {"status": "rejected", "reason": "no_significant_saved_directional_interval"},
                      "no significant saved directional interval")
                accepted = False
            else:
                accepted = geometry(hierarchy, edge["geometry"], face, source, receiver, sample["stage_m"])
            eligible = accepted and source not in blocked and receiver not in blocked
        else:
            equal(edge, {"source_leaf_id": None, "receiver_leaf_id": None, "geometry": None}, "unstable face route refusal")
        equal(edge["routing_eligible"], eligible, "edge routing eligibility")
    require(len(graph["outlets"]) == len(topology["engineering_boundaries"]), "engineering outlet census incomplete")
    for position, (outlet, boundary) in enumerate(zip(graph["outlets"], topology["engineering_boundaries"])):
        physical_boundary(hierarchy, boundary)
        equal(outlet, boundary, "engineering boundary identity")
        actual = ordinary["arrays"]["engineering_boundary_outflow_m3"][:, position]
        other = reference["arrays"]["engineering_boundary_outflow_m3"][:, position]
        significant = np.maximum(actual, other) >= MIN_VOLUME
        error = float(np.abs(actual - other).sum() / max(float(other.sum()), MIN_VOLUME))
        maximum = float(np.max(np.abs(actual[significant] - other[significant]) /
                              np.maximum(other[significant], MIN_VOLUME))) if significant.any() else 0.
        sample = sample_stage(ordinary, lookup[boundary["leaf_id"]], actual)
        equal(outlet["sampled_source_stage"], sample, "engineering source stage")
        reasons = []
        if actual.sum() < MIN_VOLUME or other.sum() < MIN_VOLUME:
            reasons.append("no_actual_boundary_export")
        if error > TOLERANCE or maximum > TOLERANCE:
            reasons.append("outlet_time_refinement_failed")
        accepted = False
        if sample is None:
            require(outlet["geometry"] is None, "outlet has geometry without active saved sample")
        else:
            accepted = geometry(hierarchy, outlet["geometry"], boundary, boundary["leaf_id"], None,
                                sample["stage_m"], engineering=True)
            if not accepted:
                reasons.append("outlet_geometry_rejected")
        if boundary["leaf_id"] in blocked:
            reasons.append("blocked_basin")
        equal(outlet, {"kind": "engineering_outlet", "outflow_m3": float(actual.sum()),
              "strong_outflow_m3": float(events["strong"]["arrays"]["engineering_boundary_outflow_m3"][:, position].sum()),
              "relative_l1_difference": error, "max_interval_relative_difference": maximum,
              "routing_eligible": not reasons and sample is not None, "rejection_reasons": reasons}, "engineering actual-export verdict")
    forest_checks(graph, leaves, areas, blocked)
    support_witness = route_support(graph, topology, ordinary)
    frontier = frontier_checks(graph)
    primary = graph["routing_forest"]["primary_component"]
    members = [] if primary is None else primary["leaf_ids"]
    support_mask = arrays["valid_mask"] & np.isin(arrays["contribution_owner"], members)
    selected = graph["main_route_support"].get("saved_index_for_review", 0)
    stages = np.full(len(arrays["node_parent"]), -np.inf)
    stages[topology["arrays"]["leaf_ids"]] = ordinary["arrays"]["stage_m"][selected]
    wet = support_mask & (stages[np.maximum(arrays["contribution_owner"], 0)] > arrays["height_m"]) & ~arrays["protected_mask"]
    parent_faces = {record["parent_face_id"] for record in graph["routing_forest"]["records"]
                    if record["leaf_id"] in members and record["parent_face_id"] is not None}
    expected_routes = [edge for edge in graph["edges"] if edge["face_id"] in parent_faces]
    expected_outlet = None if primary is None else next(outlet for outlet in graph["outlets"]
        if outlet["cell_id"] == primary["root_boundary_cell_id"])
    equal(review, {"case_id": case["case_id"], "source_identity_sha256": graph["source_identity_sha256"],
          "height_m": arrays["height_m"].tolist(), "primary_support_cell_ids": np.flatnonzero(support_mask).tolist(),
          "sampled_lake_wet_cell_ids": np.flatnonzero(wet).tolist(), "sampled_index": selected,
          "sampled_time_s": float(selected * 300.), "primary_component": primary, "nodes": graph["nodes"],
          "routes": expected_routes, "outlet": expected_outlet, "main_route_support": graph["main_route_support"],
          "frontier_requests": graph["frontier_requests"], "hydraulic_ready": False, "natural_outlet_verified": False,
          "publishable": False, "permanent_trunk_ready": False}, "review saved-array footprint/routes")
    summary = {"basin_count": len(leaves), "physical_faces": len(graph["edges"]),
        "ordinary_stable_faces": sum(edge["ordinary"]["stable_relationship"] for edge in graph["edges"]),
        "routing_eligible_faces": sum(edge["routing_eligible"] for edge in graph["edges"]),
        "routing_eligible_outlets": sum(outlet["routing_eligible"] for outlet in graph["outlets"]),
        "primary_event_supported_area_m2": 0. if primary is None else primary["area_m2"],
        "primary_basin_count": 0 if primary is None else primary["leaf_count"],
        "static_largest_catchment_area_m2": max(areas.values()),
        "main_route_positive_duration_s": graph["main_route_support"]["positive_duration_s"],
        "frontier_request_count": len(graph["frontier_requests"])}
    equal(case["summary"], summary, "index graph summary")
    return {"case_id": case["case_id"], "summary": summary, "main_interval_witness": support_witness,
            "frontier_review": frontier, "sampled_stage_coverage_semantics": "stage >= bed; strict submergence is separately stage > bed"}


def event_headers(event, topology, hierarchy, name):
    metadata, arrays = event["metadata"], event["arrays"]
    duration = 86400. if name.startswith("ordinary") else 21600.
    steps = int(duration / 300.)
    equal(metadata, {"schema": "td-basin-runoff-exchange-v1", "duration_s": duration,
          "timestep_s": 300., "steps": steps, "max_step_s": 300. if name.endswith("reference") else 150.,
          "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
          "hierarchy_identity_sha256": hierarchy["identity_sha256"], "topology_identity_sha256": topology["identity_sha256"],
          "leaf_order": "topology arrays.leaf_ids order; rainfall columns are not remapped"}, "saved event headers")
    count = len(topology["arrays"]["leaf_ids"])
    shapes = {"stage_m": (steps + 1, count), "surface_volume_m3": (steps + 1, count),
              "outflow_volume_m3": (steps, count), "rain_mm_h": (steps, count),
              "face_forward_m3": (steps, len(topology["faces"])),
              "face_reverse_m3": (steps, len(topology["faces"])),
              "engineering_boundary_outflow_m3": (steps, len(topology["engineering_boundaries"]))}
    for key, shape in shapes.items():
        require(arrays[key].shape == shape and arrays[key].dtype == np.float64 and np.isfinite(arrays[key]).all(),
                "invalid saved event array: " + key)
        if key != "stage_m":
            require(np.all(arrays[key] >= 0), "negative saved transfer/store: " + key)
    flags(metadata)


def audit_saved(directory, expected_sha256, seen):
    index = pinned_json({"path": "index.json", "sha256": expected_sha256}, directory, seen, local=True)
    equal(index, {"schema": "td-lake-spill-preparation-v1", "status": "ready_for_independent_audit",
          "solver_advanced": False, "bed_changed": False, "water_generated": False, "hydraulic_ready": False,
          "natural_outlet_verified": False, "publishable": False, "permanent_trunk_ready": False}, "preparation index")
    flags(index)
    require(set(index["code_sha256"]) == CODE, "generation code pin coverage mismatch")
    for name, sha in index["code_sha256"].items():
        pinned_path({"path": name, "sha256": sha}, ROOT, seen)
    require(index["parent_index"]["sha256"] == PARENT_SHA and index["parent_audit"]["sha256"] == PARENT_AUDIT_SHA and
            index["baseline_index"]["sha256"] == BASELINE_SHA, "accepted parent pins changed")
    parent = pinned_json(index["parent_index"], ROOT, seen)
    parent_audit = pinned_json(index["parent_audit"], ROOT, seen)
    equal(parent_audit, {"status": "passed", "index_sha256": PARENT_SHA, "cold_read": True,
                         "solver_advanced": False}, "accepted conditioning parent audit")
    same_pin(index["baseline_index"], parent["configuration"]["baseline_index"], ROOT, ROOT, seen)
    same_pin(index["baseline_audit"], parent["configuration"]["baseline_audit"], ROOT, ROOT, seen)
    baseline = pinned_json(index["baseline_index"], ROOT, seen)
    baseline_audit = pinned_json(index["baseline_audit"], ROOT, seen)
    equal(baseline_audit, {"status": "passed", "index_sha256": BASELINE_SHA, "cold_read": True,
                           "solver_advanced": False}, "accepted baseline water audit")
    derived = [candidate for candidate in parent["candidates"] if candidate["candidate_id"] == "limited_fill"]
    require(len(derived) == 1, "accepted limited_fill parent coverage")
    parent_directory = pinned_path(index["parent_index"], ROOT, seen).parent
    baseline_directory = pinned_path(index["baseline_index"], ROOT, seen).parent
    configurations = {"baseline": (parent["configuration"]["hierarchy"], parent["configuration"]["baseline_topology"],
                                   baseline["cases"], baseline_directory),
                      "limited_fill": (derived[0]["hierarchy"], derived[0]["topology"], derived[0]["cases"], parent_directory)}
    equal([case["case_id"] for case in index["cases"]], ["baseline", "limited_fill"], "preparation case coverage")
    review = pinned_json(index["review"], directory, seen, local=True)
    equal(review, {"schema": "td-lake-spill-review-v1", "solver_advanced": False,
                  "hydraulic_ready": False, "natural_outlet_verified": False,
                  "publishable": False, "permanent_trunk_ready": False}, "review envelope")
    flags(review)
    equal([case["case_id"] for case in review["cases"]], ["baseline", "limited_fill"], "review case coverage")
    image = pinned_path(index["image"], directory, seen, local=True)
    with image.open("rb") as stream:
        header = stream.read(24)
    require(len(header) == 24 and header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR", "review image not PNG")
    width, height = struct.unpack(">II", header[16:24])
    require(width > 0 and height > 0, "blank-dimension review image")
    results = []
    for case, review_case in zip(index["cases"], review["cases"]):
        hierarchy_pin, topology_pin, parent_cases, base = configurations[case["case_id"]]
        pins = case["inputs"]
        require(set(pins) == {"hierarchy", "topology", "events"}, "input pin coverage")
        same_pin(pins["hierarchy"], hierarchy_pin, directory, base, seen)
        same_pin(pins["topology"], topology_pin, directory, base, seen)
        hierarchy = bundle(pins["hierarchy"], directory, seen)
        topology = pinned_json(pins["topology"], directory, seen)
        require(topology["identity_sha256"] == pins["topology"]["identity_sha256"] ==
                digest({key: value for key, value in topology.items() if key != "identity_sha256"}), "topology identity mismatch")
        equal(topology, {"schema": "td-original-bed-overflow-topology-v1"}, "saved topology schema")
        topology["arrays"] = {key: np.asarray(value) for key, value in topology["arrays"].items()}
        equal(topology["metadata"], {"hierarchy_identity_sha256": hierarchy["identity_sha256"],
              "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
              "origin_m_xz": hierarchy["metadata"]["origin_m_xz"],
              "spacing_m": float(hierarchy["metadata"]["spacing_m"])}, "topology source/grid")
        require(hierarchy["metadata"]["schema"] == "td-basin-hierarchy-v1", "hierarchy schema mismatch")
        lookup = {item["name"]: item for item in parent_cases}
        require(len(parent_cases) == 2 and set(lookup) == {"normal-spatial-recession-24h", "strong-spatial-recession-6h"},
                "accepted event case coverage")
        require(set(pins["events"]) == {"ordinary", "ordinary_reference", "strong", "strong_reference"}, "event pin coverage")
        events = {}
        for prefix, name in (("ordinary", "normal-spatial-recession-24h"), ("strong", "strong-spatial-recession-6h")):
            levels = lookup[name]["levels"]
            equal([level["level"] for level in levels], [0, 1], "accepted refinement levels")
            for key, level in ((prefix, levels[1]), (prefix + "_reference", levels[0])):
                same_pin(pins["events"][key], level["event"], directory, base, seen)
                events[key] = bundle(pins["events"][key], directory, seen)
                event_headers(events[key], topology, hierarchy, key)
            require(events[prefix]["identity_sha256"] != events[prefix + "_reference"]["identity_sha256"], "duplicated refinement event")
            for key in ("parameters", "runoff_metadata", "topology_identity_sha256", "hierarchy_identity_sha256", "source_identity_sha256"):
                equal(events[prefix]["metadata"][key], events[prefix + "_reference"]["metadata"][key], "refinement forcing/physics")
            require(np.array_equal(events[prefix]["arrays"]["rain_mm_h"], events[prefix + "_reference"]["arrays"]["rain_mm_h"]),
                    "refinement rain arrays differ")
        graph = pinned_json(case["graph"], directory, seen, local=True)
        require(graph["identity_sha256"] == case["graph"]["identity_sha256"] ==
                digest({key: value for key, value in graph.items() if key != "identity_sha256"}), "graph identity mismatch")
        results.append(audit_case(dict(case, _graph=graph), review_case, hierarchy, topology, events))
        equal(review, {"origin_m_xz": hierarchy["metadata"]["origin_m_xz"],
                       "spacing_m": float(hierarchy["metadata"]["spacing_m"])}, "review shared grid")
    return {"status": "passed", "cases": results, "parent_audit_reused": index["parent_audit"],
            "baseline_audit_reused": index["baseline_audit"], "old_water_ledgers_recomputed": False,
            "image_pin_verified": True, "image_size_px": [width, height], "image_visual_content_audited": False}


def audit(directory, expected_sha256):
    directory = Path(directory).resolve(strict=True)
    require(directory.is_relative_to(ROOT.resolve()) and directory.is_dir(), "audit directory must be inside workspace")
    destination = directory / "independent-audit.json"
    require(not destination.exists(), "audit report already exists; refusing overwrite")
    seen = {Path(__file__).resolve(): file_sha256(Path(__file__))}
    report = {"schema": "td-lake-spill-graph-independent-audit-v1", "index_sha256": expected_sha256,
              "cold_read": True, "solver_advanced": False, "graph_generated": False, "geometry_built": False,
              "forest_generated": False, "bed_changed": False, "water_generated": False,
              "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
              "permanent_trunk_ready": False,
              "scope": "accepted-parent pins, saved per-face ordinary/strong refinement, sampled receiver geometry, actual engineering exports, unique-area forest, interval intersection, frontier and review pins; no old water ledger replay or hydraulic certification"}
    try:
        with ExitStack() as guards:
            for target in FORBIDDEN:
                guards.enter_context(patch(target, side_effect=AssertionError("cold audit forbids generating/solving: " + target)))
            report.update(audit_saved(directory, expected_sha256, seen))
            for path, sha in seen.items():
                require(file_sha256(path) == sha, "input/code changed during cold audit: " + str(path))
    except (ValueError, KeyError, TypeError, IndexError, OSError, AssertionError, StopIteration, OverflowError) as error:
        report.update(status="diagnostic_failure", failure_type=type(error).__name__, failure_reason=str(error))
    report["audit_code_sha256"] = seen[Path(__file__).resolve()]
    report["verified_file_count"] = len(seen)
    publish_bytes(destination, json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    arguments = parser.parse_args()
    result = audit(arguments.directory, arguments.index_sha256)
    print(json.dumps({key: result.get(key) for key in ("status", "failure_reason", "verified_file_count")}, ensure_ascii=False))
    sys.exit(0 if result["status"] == "passed" else 1)
