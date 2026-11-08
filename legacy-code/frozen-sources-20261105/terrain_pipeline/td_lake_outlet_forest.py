"""Deterministic event-supported routing diagnostics, not permanent rivers."""

from collections import deque
from copy import deepcopy
import math

from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components


def _identifier(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _positive(value, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) or value <= 0):
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _face_key(value):
    if isinstance(value, str) and value:
        return (1, value)
    return (0, _identifier(value, "face_id"))


def _fields(record, names, kind):
    if not isinstance(record, dict) or any(name not in record for name in names):
        raise ValueError(f"{kind} must contain {', '.join(names)}")


def build_outlet_forest(leaf_ids, areas_m2, directed_edges, outlets, *, blocked_leaf_ids=()):
    """Select shortest supported routes to actual exports without altering edges.

    Ties prefer root leaf/cell, larger face net volume, then face/receiver ID.
    Components own each reachable leaf exactly once. Main path is root-first
    and follows the child with largest accumulated upstream area. Its face IDs
    are source-to-export; event-union support does not prove simultaneous flow.
    """
    if len(leaf_ids) != len(areas_m2):
        raise ValueError("leaf_ids and areas_m2 must have equal lengths")
    areas = {}
    for leaf_id, area in zip(leaf_ids, areas_m2):
        leaf_id = _identifier(leaf_id, "leaf_id")
        if leaf_id in areas:
            raise ValueError("leaf_ids must be unique")
        areas[leaf_id] = _positive(area, "area_m2")
    ordered_ids = sorted(areas)
    blocked = {_identifier(leaf_id, "blocked_leaf_id") for leaf_id in blocked_leaf_ids}
    if not blocked.issubset(areas):
        raise ValueError("blocked_leaf_ids must refer to known leaves")

    incoming = {leaf_id: [] for leaf_id in ordered_ids}
    edges = []
    face_ids = set()
    for edge in directed_edges:
        _fields(edge, ("face_id", "source_leaf_id", "receiver_leaf_id", "net_m3"), "edge")
        face_id = edge["face_id"]
        _face_key(face_id)
        source = _identifier(edge["source_leaf_id"], "source_leaf_id")
        receiver = _identifier(edge["receiver_leaf_id"], "receiver_leaf_id")
        _positive(edge["net_m3"], "net_m3")
        if source not in areas or receiver not in areas:
            raise ValueError("edges must refer to known leaves")
        if source == receiver:
            raise ValueError("self-loop edges are not allowed")
        if face_id in face_ids:
            raise ValueError("edge face_ids must be unique")
        face_ids.add(face_id)
        copied = deepcopy(edge)
        edges.append(copied)
        incoming[receiver].append(copied)
    edges.sort(key=lambda edge: _face_key(edge["face_id"]))

    seeds = {}
    for outlet in outlets:
        _fields(outlet, ("leaf_id", "cell_id", "outflow_m3"), "outlet")
        leaf_id = _identifier(outlet["leaf_id"], "outlet leaf_id")
        cell_id = _identifier(outlet["cell_id"], "outlet cell_id")
        outflow = _positive(outlet["outflow_m3"], "outflow_m3")
        if leaf_id not in areas:
            raise ValueError("outlets must refer to known leaves")
        if leaf_id in blocked:
            continue
        previous = seeds.get(leaf_id)
        if previous is None or (-outflow, cell_id) < (-previous["outflow_m3"], previous["cell_id"]):
            seeds[leaf_id] = {"leaf_id": leaf_id, "cell_id": cell_id, "outflow_m3": outflow}

    indices = {leaf_id: index for index, leaf_id in enumerate(ordered_ids)}
    adjacency = csr_matrix(
        ([1] * len(edges),
         ([indices[edge["source_leaf_id"]] for edge in edges],
          [indices[edge["receiver_leaf_id"]] for edge in edges])),
        shape=(len(ordered_ids), len(ordered_ids)),
    )
    if ordered_ids:
        _, labels = connected_components(adjacency, directed=True, connection="strong")
        groups = {}
        for leaf_id, label in zip(ordered_ids, labels):
            groups.setdefault(int(label), []).append(leaf_id)
        strong_components = sorted(groups.values())
    else:
        strong_components = []
    cyclic_components = [group for group in strong_components if len(group) > 1]

    hops = {leaf_id: 0 for leaf_id in sorted(seeds)}
    queue = deque(sorted(seeds))
    visit_order = []
    while queue:
        receiver = queue.popleft()
        visit_order.append(receiver)
        for edge in sorted(incoming[receiver], key=lambda edge: _face_key(edge["face_id"])):
            source = edge["source_leaf_id"]
            if source in blocked or source in hops:
                continue
            hops[source] = hops[receiver] + 1
            queue.append(source)

    records = {}
    children = {leaf_id: [] for leaf_id in ordered_ids}
    for leaf_id in ordered_ids:
        records[leaf_id] = {
            "leaf_id": leaf_id,
            "reachable": leaf_id in hops,
            "parent_leaf_id": None,
            "parent_face_id": None,
            "root_leaf_id": None,
            "root_boundary_cell_id": None,
            "hops": hops.get(leaf_id),
            "supported_area_m2": 0.0,
            "reason": "blocked" if leaf_id in blocked else "no_event_supported_route_to_export",
        }
    outgoing = {leaf_id: [] for leaf_id in ordered_ids}
    for edge in edges:
        outgoing[edge["source_leaf_id"]].append(edge)
    for leaf_id in sorted(visit_order, key=lambda leaf_id: (hops[leaf_id], leaf_id)):
        record = records[leaf_id]
        if hops[leaf_id] == 0:
            root_leaf_id = leaf_id
        else:
            candidates = [edge for edge in outgoing[leaf_id]
                          if hops.get(edge["receiver_leaf_id"]) == hops[leaf_id] - 1]
            selected = min(candidates, key=lambda edge: (
                records[edge["receiver_leaf_id"]]["root_leaf_id"],
                records[edge["receiver_leaf_id"]]["root_boundary_cell_id"],
                -edge["net_m3"], _face_key(edge["face_id"]), edge["receiver_leaf_id"],
            ))
            parent = selected["receiver_leaf_id"]
            root_leaf_id = records[parent]["root_leaf_id"]
            record["parent_leaf_id"] = parent
            record["parent_face_id"] = selected["face_id"]
            children[parent].append(leaf_id)
        record["root_leaf_id"] = root_leaf_id
        record["root_boundary_cell_id"] = seeds[root_leaf_id]["cell_id"]
        record["reason"] = None
    for leaf_id in sorted(visit_order, key=lambda leaf_id: (-hops[leaf_id], leaf_id)):
        records[leaf_id]["supported_area_m2"] = math.fsum(
            [areas[leaf_id]] + [records[child]["supported_area_m2"] for child in sorted(children[leaf_id])]
        )

    members = {root: [] for root in seeds}
    for leaf_id in ordered_ids:
        if records[leaf_id]["reachable"]:
            members[records[leaf_id]["root_leaf_id"]].append(leaf_id)
    components = [{
        "root_leaf_id": root,
        "root_boundary_cell_id": seeds[root]["cell_id"],
        "leaf_ids": members[root],
        "area_m2": math.fsum(areas[leaf_id] for leaf_id in members[root]),
        "leaf_count": len(members[root]),
        "outlet": deepcopy(seeds[root]),
    } for root in sorted(seeds)]
    primary = min(components, key=lambda component: (
        -component["area_m2"], -component["outlet"]["outflow_m3"],
        component["root_boundary_cell_id"], component["root_leaf_id"],
    )) if components else None
    main_path = []
    if primary is not None:
        current = primary["root_leaf_id"]
        while True:
            main_path.append(current)
            if not children[current]:
                break
            current = min(children[current], key=lambda child: (
                -records[child]["supported_area_m2"], child,
            ))
    return {
        "records": [records[leaf_id] for leaf_id in ordered_ids],
        "components": components,
        "primary_component": deepcopy(primary),
        "main_path": main_path,
        "main_path_face_ids": [records[leaf_id]["parent_face_id"]
                               for leaf_id in reversed(main_path[1:])],
        "graph_diagnostics": {
            "directed_edges": edges,
            "leaf_count": len(ordered_ids),
            "edge_count": len(edges),
            "strong_components": strong_components,
            "cyclic_components": cyclic_components,
            "has_cycles": bool(cyclic_components),
            "blocked_leaf_ids": sorted(blocked),
        },
        "permanent_trunk_ready": False,
        "hydraulic_ready": False,
        "natural_outlet_verified": False,
        "publishable": False,
    }
