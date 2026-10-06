"""Shared native-cell paths on an unchanged bed, without water solving.

Only canonical two-cell receiver arcs are channel candidates. Saved spill
geometry is support, including any dry part of a downstream support polyline.
"""

from collections import deque
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, publish_bytes
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy
from terrain_pipeline.td_lake_outlet_forest import build_outlet_forest
from terrain_pipeline.td_lake_spill_geometry import trace_engineering_outlet, trace_spill_connection
from terrain_pipeline.td_lake_spill_graph import digest, sampled_stage

SCHEMA = "td-watershed-paths-v1"
ALGORITHM = "native-receiver-local-area-retained-lake-support-v1"
MAX_BYTES = 32 * 1024**2
MAX_CELLS = 250_000
MAX_ARCS = 250_000
MAX_PATH_SAMPLES = 1_000_000
FLAGS = ("hydraulic_ready", "hydraulic_verified", "natural_outlet_verified", "publishable",
         "permanent_trunk_ready", "permanent_river_verified", "transient_converged",
         "solver_advanced", "bed_changed", "water_generated")
INTERFACES = {"lake_entry", "lake_interface", "spill", "engineering", "lake_terminal"}
SUPPORT_KINDS = {"source_lake_approach", "cross_face", "downhill_terrain_approach",
                 "engineering_outlet_support", "lake_entry_support", "lake_receiver_support"}


def _positive(value, name):
    if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
        raise ValueError("invalid " + name)
    return float(value)


def _pin(record, name):
    value = record.get(name)
    if (not isinstance(value, str) or len(value) != 64 or
            any(character not in "0123456789abcdef" for character in value)):
        raise ValueError("invalid identity: " + name)
    return value


def _payload(record):
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise MemoryError("watershed paths exceed 32MiB")
    return payload


def _inputs(graph, hierarchy, ordinary):
    validate_basin_hierarchy(hierarchy)
    if graph.get("schema") != "td-lake-spill-graph-v1" or graph.get("identity_sha256") != digest(
            {key: value for key, value in graph.items() if key != "identity_sha256"}):
        raise ValueError("graph identity/schema mismatch")
    if any(graph.get(name) is not False for name in (
            "hydraulic_ready", "natural_outlet_verified", "publishable", "permanent_trunk_ready",
            "solver_advanced", "bed_changed", "water_generated")):
        raise ValueError("graph certification or mutation claim")
    metadata = ordinary["metadata"]
    if (metadata.get("schema") != "td-basin-runoff-exchange-v1" or
            ordinary.get("identity_sha256") != identity(ordinary["arrays"], metadata) or
            graph["event_identity_sha256"]["ordinary"] != ordinary["identity_sha256"] or
            metadata["topology_identity_sha256"] != graph["topology_identity_sha256"] or
            metadata["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or
            graph["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or
            metadata["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"] or
            graph["source_identity_sha256"] != metadata["source_identity_sha256"]):
        raise ValueError("ordinary/graph/hierarchy/source identity mismatch")
    if any(metadata.get(name) is not False for name in (
            "hydraulic_ready", "transient_converged", "natural_outlet_verified", "publishable")):
        raise ValueError("ordinary certification claim")
    for values in ordinary["arrays"].values():
        if not isinstance(values, np.ndarray) or not np.isfinite(values).all():
            raise ValueError("ordinary contains nonfinite/nonarray data")
    arrays = hierarchy["arrays"]
    owner = arrays["contribution_owner"].ravel()
    valid = arrays["valid_mask"].ravel()
    leaves = [int(leaf) for leaf in np.unique(owner[valid])]
    if [node["leaf_id"] for node in graph["nodes"]] != leaves:
        raise ValueError("graph nodes differ from actual contribution leaf order")
    stages = ordinary["arrays"]["stage_m"]
    if (stages.ndim != 2 or stages.shape != (metadata["steps"] + 1, len(leaves)) or
            not np.isfinite(stages).all() or metadata["duration_s"] != 86400. or
            metadata["timestep_s"] != 300.):
        raise ValueError("ordinary full saved-stage dimensions/time mismatch")
    spacing = float(hierarchy["metadata"]["spacing_m"])
    blocked = []
    for position, node in enumerate(graph["nodes"]):
        leaf = leaves[position]
        cells = np.flatnonzero(valid & (owner == leaf))
        sinks = cells[arrays["receiver"][cells] < 0]
        if (len(sinks) != 1 or node["terminal_cell_id"] != int(sinks[0]) or
                node["exclusive_area_m2"] != len(cells) * spacing**2 or
                node["ordinary_stage_max_m"] != float(stages[:, position].max())):
            raise ValueError("graph basin differs from actual bed/stages")
        reasons = []
        if arrays["node_unknown_contact"][leaf]:
            reasons.append("unknown_contact")
        if arrays["protected_mask"].ravel()[cells].any():
            reasons.append("protected_basin")
        if node["blocked_reasons"] != reasons:
            raise ValueError("graph basin protection/unknown mismatch")
        if reasons:
            blocked.append(leaf)
    edges = [{"face_id": edge["face_id"], "source_leaf_id": edge["source_leaf_id"],
              "receiver_leaf_id": edge["receiver_leaf_id"], "net_m3": abs(edge["ordinary"]["net_m3"])}
             for edge in graph["edges"] if edge["routing_eligible"]]
    outlets = [{"leaf_id": outlet["leaf_id"], "cell_id": outlet["cell_id"],
                "outflow_m3": outlet["outflow_m3"]}
               for outlet in graph["outlets"] if outlet["routing_eligible"]]
    forest = build_outlet_forest(leaves, [node["exclusive_area_m2"] for node in graph["nodes"]],
                                edges, outlets, blocked_leaf_ids=blocked)
    if forest != graph["routing_forest"]:
        raise ValueError("graph parent/main paths differ from deterministic forest")
    primary = forest["primary_component"]
    if primary is None:
        raise ValueError("graph has no primary outlet component")
    return forest, leaves, stages


def _build(graph, hierarchy, ordinary, minimum_area_m2):
    minimum_area = _positive(minimum_area_m2, "minimum_area_m2")
    forest, leaves, stages = _inputs(graph, hierarchy, ordinary)
    primary = forest["primary_component"]
    selected = primary["leaf_ids"]
    selected_set = set(selected)
    arrays = hierarchy["arrays"]
    bed = arrays["height_m"].ravel()
    owner = arrays["contribution_owner"].ravel()
    receiver = arrays["receiver"]
    valid = arrays["valid_mask"].ravel()
    protected = arrays["protected_mask"].ravel()
    cell_owner = arrays["cell_owner"].ravel()
    unknown = arrays["node_unknown_contact"]
    spacing = float(hierarchy["metadata"]["spacing_m"])
    origin = hierarchy["metadata"]["origin_m_xz"]
    columns = arrays["height_m"].shape[1]
    cells = np.flatnonzero(valid & np.isin(owner, selected))
    if len(bed) > MAX_CELLS or len(cells) > MAX_CELLS:
        raise MemoryError("native cell budget exceeded")
    if protected[cells].any() or unknown[cell_owner[cells]].any() or unknown[selected].any():
        raise ValueError("primary component touches protected/unknown cells")
    active = np.zeros(len(bed), bool)
    active[cells] = True
    incoming = np.zeros(len(bed), np.int64)
    for cell in cells:
        target = int(receiver[cell])
        if target >= 0:
            if not active[target]:
                raise ValueError("receiver leaves selected contribution cells")
            incoming[target] += 1
    pending = incoming.copy()
    area = np.zeros(len(bed), np.float64)
    area[cells] = spacing**2
    queue = deque(int(cell) for cell in cells if pending[cell] == 0)
    visited = 0
    while queue:
        cell = queue.popleft()
        visited += 1
        target = int(receiver[cell])
        if target >= 0:
            area[target] += area[cell]
            pending[target] -= 1
            if pending[target] == 0:
                queue.append(target)
    if visited != len(cells) or not np.isfinite(area[cells]).all():
        raise ValueError("receiver cycle/nonfinite local accumulation")
    maximum_stage = {leaf: float(stages[:, leaves.index(leaf)].max()) for leaf in selected}
    main_faces = set(forest["main_path_face_ids"])
    main_receiver_pairs = set()
    for edge in graph["edges"]:
        if edge["face_id"] in main_faces:
            route = edge["geometry"]["downhill_terrain_approach"]["cell_ids"]
            main_receiver_pairs.update(zip(route, route[1:]))
    nodes = {}
    arcs = []
    sample_count = 0

    def node(cell, kind):
        cell = int(cell)
        if not 0 <= cell < len(bed) or not active[cell]:
            raise ValueError("support cell outside selected valid cells")
        if cell not in nodes:
            row, column = divmod(cell, columns)
            nodes[cell] = {"node_id": f"cell:{cell}", "cell_id": cell,
                           "xyz_m": [float(origin[0] + column * spacing), float(bed[cell]),
                                     float(origin[1] + row * spacing)],
                           "kinds": set(), "leaf_id": int(owner[cell]),
                           "local_upstream_area_m2": float(area[cell])}
        nodes[cell]["kinds"].add(kind)
        if bed[cell] <= maximum_stage[int(owner[cell])]:
            nodes[cell]["kinds"].add("lake_covered")
        if incoming[cell] >= 2:
            nodes[cell]["kinds"].add("confluence")
        return nodes[cell]

    def arc(arc_id, kind, route, leaf, face_id=None, main=False, support=None, sample=None):
        nonlocal sample_count
        route = [int(cell) for cell in route]
        if not route:
            raise ValueError("empty path")
        sample_count += len(route)
        if len(arcs) >= MAX_ARCS or sample_count > MAX_PATH_SAMPLES:
            raise MemoryError("arc/path sample budget exceeded")
        points = [node(cell, kind) for cell in route]
        for first, second in zip(route, route[1:]):
            if abs(first // columns - second // columns) + abs(first % columns - second % columns) != 1:
                raise ValueError("non D4 arc")
        item = {"arc_id": arc_id, "kind": kind, "node_ids": [point["node_id"] for point in points],
                "cell_ids": route, "xyz_m": [point["xyz_m"][:] for point in points],
                "leaf_id": int(leaf), "face_id": face_id, "is_main_path": bool(main),
                "channel_candidate": kind == "land_channel",
                "local_upstream_area_m2": float(area[route[0]])}
        if support is not None:
            if support["xyz_m"] != item["xyz_m"]:
                raise ValueError("saved support coordinates differ from actual bed")
            item["source_geometry"] = deepcopy(support)
        if sample is not None:
            item["sampled_source_stage"] = deepcopy(sample)
        arcs.append(item)
        return item

    lakes = []
    graph_nodes = {item["leaf_id"]: item for item in graph["nodes"]}
    for leaf in selected:
        terminal = graph_nodes[leaf]["terminal_cell_id"]
        node(terminal, "lake_terminal")
        leaf_cells = cells[owner[cells] == leaf]
        covered = leaf_cells[bed[leaf_cells] <= maximum_stage[leaf]]
        lakes.append({"leaf_id": leaf, "terminal_node_id": f"cell:{terminal}",
                      "terminal_cell_id": terminal, "ordinary_stage_max_m": maximum_stage[leaf],
                      "stage_semantics": "maximum over all ordinary saved stages; not simultaneous water geometry",
                      "covered_cell_ids": [int(cell) for cell in covered],
                      "exclusive_area_m2": len(leaf_cells) * spacing**2,
                      "local_terminal_upstream_area_m2": float(area[terminal]),
                      "entry_node_ids": [], "entry_interfaces": [],
                      "spill_node_ids": [], "engineering_node_ids": []})
    lake_lookup = {lake["leaf_id"]: lake for lake in lakes}
    for cell in cells:
        target = int(receiver[cell])
        if target < 0 or area[cell] < minimum_area:
            continue
        leaf = int(owner[cell])
        dry_source = bed[cell] > maximum_stage[leaf]
        dry_target = bed[target] > maximum_stage[leaf]
        if dry_source and dry_target:
            kind = "land_channel"
        elif dry_source:
            kind = "lake_entry_support"
        else:
            kind = "lake_receiver_support"
        item = arc(f"receiver:{int(cell)}:{target}", kind, [cell, target], leaf,
                   main=(int(cell), target) in main_receiver_pairs)
        if dry_source and not dry_target:
            node(cell, "lake_entry")
            node(target, "lake_entry")
            node(cell, "lake_interface")
            node(target, "lake_interface")
            interface = {"land_node_id": f"cell:{int(cell)}", "wet_node_id": f"cell:{target}",
                         "support_arc_id": item["arc_id"]}
            item["lake_interface"] = deepcopy(interface)
            item["interface_node_ids"] = [interface["land_node_id"], interface["wet_node_id"]]
            lake_lookup[leaf]["entry_interfaces"].append(interface)
    parent_records = {record["leaf_id"]: record for record in forest["records"]}
    edge_lookup = {edge["face_id"]: (position, edge) for position, edge in enumerate(graph["edges"])}
    for leaf in selected:
        parent = parent_records[leaf]
        if parent["parent_leaf_id"] is None:
            continue
        position, edge = edge_lookup[parent["parent_face_id"]]
        if (edge["source_leaf_id"] != leaf or edge["receiver_leaf_id"] != parent["parent_leaf_id"] or
                edge["receiver_leaf_id"] not in selected_set):
            raise ValueError("selected parent face orientation mismatch")
        directional = edge["ordinary"]["direction"] * (
            ordinary["arrays"]["face_forward_m3"][:, position] -
            ordinary["arrays"]["face_reverse_m3"][:, position])
        sample = sampled_stage(ordinary, leaves.index(leaf), directional)
        if sample is None or edge["sampled_source_stage"] != sample:
            raise ValueError("source active maximum sampled stage mismatch")
        expected = trace_spill_connection(hierarchy, edge, leaf, edge["receiver_leaf_id"],
                                          source_stage_m=sample["stage_m"])
        if expected["status"] != "accepted" or expected != edge["geometry"]:
            raise ValueError("selected saved geometry differs from actual receiver/face")
        for kind in ("source_lake_approach", "cross_face", "downhill_terrain_approach"):
            support = expected[kind]
            support_leaf = edge["receiver_leaf_id"] if kind == "downhill_terrain_approach" else leaf
            arc(f"face:{edge['face_id']}:{kind}", kind, support["cell_ids"], support_leaf,
                edge["face_id"], edge["face_id"] in main_faces, support, sample)
        for cell in expected["cross_face"]["cell_ids"]:
            node(cell, "spill")
    roots = [(position, outlet) for position, outlet in enumerate(graph["outlets"])
             if outlet["routing_eligible"] and outlet["leaf_id"] == primary["root_leaf_id"] and
             outlet["cell_id"] == primary["root_boundary_cell_id"]]
    if len(roots) != 1:
        raise ValueError("primary root engineering outlet mismatch")
    position, outlet = roots[0]
    sample = sampled_stage(ordinary, leaves.index(outlet["leaf_id"]),
                           ordinary["arrays"]["engineering_boundary_outflow_m3"][:, position])
    if sample is None or sample != outlet["sampled_source_stage"]:
        raise ValueError("root maximum sampled stage mismatch")
    expected = trace_engineering_outlet(hierarchy, outlet, source_stage_m=sample["stage_m"])
    if expected["status"] != "accepted" or expected != outlet["geometry"]:
        raise ValueError("root geometry differs from actual engineering perimeter")
    support = expected["source_lake_approach"]
    arc(f"outlet:{outlet['cell_id']}", "engineering_outlet_support", support["cell_ids"],
        outlet["leaf_id"], main=True, support=support, sample=sample)
    node(outlet["cell_id"], "engineering")
    for lake in lakes:
        for kind, field in (("lake_entry", "entry_node_ids"), ("spill", "spill_node_ids"),
                            ("engineering", "engineering_node_ids")):
            lake[field] = [nodes[cell]["node_id"] for cell in sorted(nodes)
                           if nodes[cell]["leaf_id"] == lake["leaf_id"] and kind in nodes[cell]["kinds"]]
    for point in nodes.values():
        point["kinds"] = sorted(point["kinds"])
        point["lake_interfaces"] = sorted(INTERFACES.intersection(point["kinds"]))
    result = {"schema": SCHEMA, "algorithm": ALGORITHM,
              "coordinate_system": "model_xyz_m_original_bed",
              "grid_shape": list(arrays["height_m"].shape), "spacing_m": spacing,
              "origin_m_xz": [float(value) for value in origin],
              "graph_identity_sha256": graph["identity_sha256"],
              "source_identity_sha256": graph["source_identity_sha256"],
              "hierarchy_identity_sha256": hierarchy["identity_sha256"],
              "ordinary_identity_sha256": ordinary["identity_sha256"],
              "topology_identity_sha256": graph["topology_identity_sha256"],
              "parameters": {"minimum_area_m2": minimum_area},
              "selected_leaf_ids": list(selected), "nodes": [nodes[cell] for cell in sorted(nodes)],
              "arcs": sorted(arcs, key=lambda item: item["arc_id"]), "lakes": lakes,
              "budget": {"max_cells": MAX_CELLS, "max_arcs": MAX_ARCS,
                         "max_path_samples": MAX_PATH_SAMPLES, "max_bytes": MAX_BYTES,
                         "selected_valid_cells": len(cells), "path_samples": sample_count},
              "semantics": "local area is native receiver upstream cell area, not forest event support; support arcs never authorize carving",
              **{name: False for name in FLAGS}}
    result["identity_sha256"] = digest(result)
    _payload(result)
    return result


def build_watershed_paths(graph, hierarchy, ordinary, *, minimum_area_m2=3600.):
    """Return a source-pinned JSON record; never modify inputs or invoke a solver."""
    result = _build(graph, hierarchy, ordinary, minimum_area_m2)
    validate_watershed_paths(result)
    return result


def validate_watershed_paths(paths, graph=None, hierarchy=None, ordinary=None):
    """Validate stored structure; with all parents, verify exact source geometry."""
    _payload(paths)
    if (paths.get("schema") != SCHEMA or paths.get("algorithm") != ALGORITHM or
            paths.get("identity_sha256") != digest({key: value for key, value in paths.items()
                                                    if key != "identity_sha256"}) or
            any(paths.get(name) is not False for name in FLAGS)):
        raise ValueError("watershed paths schema/identity/flags mismatch")
    for name in ("identity_sha256", "graph_identity_sha256", "source_identity_sha256",
                 "hierarchy_identity_sha256", "ordinary_identity_sha256", "topology_identity_sha256"):
        _pin(paths, name)
    minimum = _positive(paths["parameters"]["minimum_area_m2"], "minimum_area_m2")
    spacing = _positive(paths["spacing_m"], "spacing_m")
    shape = paths["grid_shape"]
    origin = paths["origin_m_xz"]
    if (len(shape) != 2 or any(type(size) is not int or size <= 0 for size in shape) or
            math.prod(shape) > MAX_CELLS or len(origin) != 2 or
            any(type(value) not in (int, float) or not math.isfinite(value) for value in origin)):
        raise ValueError("invalid native grid geometry")
    selected = paths["selected_leaf_ids"]
    if (not selected or any(type(leaf) is not int or leaf < 0 for leaf in selected) or
            selected != sorted(set(selected))):
        raise ValueError("invalid selected leaves")
    if len(paths["nodes"]) > MAX_CELLS or len(paths["arcs"]) > MAX_ARCS:
        raise MemoryError("node/arc budget exceeded")
    nodes = {}
    for point in paths["nodes"]:
        cell = point["cell_id"]
        kinds = point["kinds"]
        if (type(cell) is not int or not 0 <= cell < math.prod(shape) or point["node_id"] != f"cell:{cell}" or
                point["node_id"] in nodes or point["leaf_id"] not in selected or
                not kinds or any(not isinstance(kind, str) for kind in kinds) or
                kinds != sorted(set(kinds)) or point["lake_interfaces"] != sorted(INTERFACES.intersection(kinds)) or
                len(point["xyz_m"]) != 3 or any(type(value) not in (int, float) or
                not math.isfinite(value) for value in point["xyz_m"])):
            raise ValueError("invalid/duplicate shared cell node")
        _positive(point["local_upstream_area_m2"], "local_upstream_area_m2")
        if (point["xyz_m"][0] != origin[0] + cell % shape[1] * spacing or
                point["xyz_m"][2] != origin[1] + cell // shape[1] * spacing):
            raise ValueError("node coordinate differs from native cell")
        nodes[point["node_id"]] = point
    lake_lookup = {}
    for lake in paths["lakes"]:
        leaf = lake["leaf_id"]
        terminal = nodes.get(lake["terminal_node_id"])
        if (leaf not in selected or leaf in lake_lookup or terminal is None or
                terminal["leaf_id"] != leaf or "lake_terminal" not in terminal["kinds"] or
                type(lake["ordinary_stage_max_m"]) not in (int, float) or
                not math.isfinite(lake["ordinary_stage_max_m"])):
            raise ValueError("invalid retained lake terminal/stage")
        lake_lookup[leaf] = lake
        for kind, field in (("lake_entry", "entry_node_ids"), ("spill", "spill_node_ids"),
                            ("engineering", "engineering_node_ids")):
            expected = [point["node_id"] for point in paths["nodes"]
                        if point["leaf_id"] == leaf and kind in point["kinds"]]
            if lake[field] != expected:
                raise ValueError("lake interface node mismatch")
    if set(lake_lookup) != set(selected):
        raise ValueError("missing retained lake")
    arc_ids = set()
    samples = 0
    for item in paths["arcs"]:
        kind = item["kind"]
        if (not isinstance(item["arc_id"], str) or not item["arc_id"] or item["arc_id"] in arc_ids or
                kind not in SUPPORT_KINDS | {"land_channel"} or item["leaf_id"] not in selected or
                type(item["is_main_path"]) is not bool or
                item["channel_candidate"] is not (kind == "land_channel") or
                not item["node_ids"] or len(item["node_ids"]) != len(item["cell_ids"]) or
                len(item["node_ids"]) != len(item["xyz_m"])):
            raise ValueError("invalid typed arc")
        arc_ids.add(item["arc_id"])
        samples += len(item["cell_ids"])
        for node_id, cell, xyz in zip(item["node_ids"], item["cell_ids"], item["xyz_m"]):
            point = nodes.get(node_id)
            if point is None or point["cell_id"] != cell or point["xyz_m"] != xyz or kind not in point["kinds"]:
                raise ValueError("arc does not reference shared actual node")
        for first, second in zip(item["cell_ids"], item["cell_ids"][1:]):
            if (abs(first // shape[1] - second // shape[1]) +
                    abs(first % shape[1] - second % shape[1]) != 1):
                raise ValueError("non D4 stored path")
        if kind == "land_channel":
            stage = lake_lookup[item["leaf_id"]]["ordinary_stage_max_m"]
            if (len(item["node_ids"]) != 2 or item["face_id"] is not None or
                    item["local_upstream_area_m2"] != nodes[item["node_ids"][0]]["local_upstream_area_m2"] or
                    item["local_upstream_area_m2"] < minimum or
                    any(nodes[node_id]["leaf_id"] != item["leaf_id"] for node_id in item["node_ids"]) or
                    any(xyz[1] <= stage for xyz in item["xyz_m"]) or
                    item["xyz_m"][1][1] > item["xyz_m"][0][1]):
                raise ValueError("land channel violates dry/nonascending/local-area contract")
        if "lake_interface" in item:
            interface = item["lake_interface"]
            interface_ids = [interface["land_node_id"], interface["wet_node_id"]]
            if (kind != "lake_entry_support" or interface["support_arc_id"] != item["arc_id"] or
                    item["node_ids"] != interface_ids or item["interface_node_ids"] != interface_ids or
                    any("lake_entry" not in nodes[node_id]["kinds"] or
                        "lake_interface" not in nodes[node_id]["kinds"] for node_id in interface_ids) or
                    item["xyz_m"][0][1] <= lake_lookup[item["leaf_id"]]["ordinary_stage_max_m"] or
                    item["xyz_m"][1][1] > lake_lookup[item["leaf_id"]]["ordinary_stage_max_m"]):
                raise ValueError("land/wet lake interface mismatch")
    for lake in paths["lakes"]:
        expected = [item["lake_interface"] for item in paths["arcs"]
                    if item["leaf_id"] == lake["leaf_id"] and "lake_interface" in item]
        if sorted(lake["entry_interfaces"], key=lambda item: item["support_arc_id"]) != expected:
            raise ValueError("structured lake entry interfaces mismatch")
    if samples > MAX_PATH_SAMPLES or paths["budget"]["path_samples"] != samples:
        raise ValueError("path sample budget mismatch")
    budget = paths["budget"]
    if (budget["max_cells"] != MAX_CELLS or budget["max_arcs"] != MAX_ARCS or
            budget["max_path_samples"] != MAX_PATH_SAMPLES or budget["max_bytes"] != MAX_BYTES or
            type(budget["selected_valid_cells"]) is not int or
            not len(nodes) <= budget["selected_valid_cells"] <= MAX_CELLS):
        raise ValueError("native geometry budget mismatch")
    parents = (graph, hierarchy, ordinary)
    if any(parent is not None for parent in parents):
        if any(parent is None for parent in parents):
            raise ValueError("exact validation requires graph, hierarchy and ordinary together")
        if paths != _build(graph, hierarchy, ordinary, minimum):
            raise ValueError("watershed paths differ from actual pinned parents")
    return True


def save_watershed_paths(paths, path):
    """Atomically publish a finite, budgeted JSON artifact."""
    validate_watershed_paths(paths)
    publish_bytes(path, _payload(paths))


def load_watershed_paths(path, *, expected_sha256, expected_identity,
                         graph=None, hierarchy=None, ordinary=None):
    """Cold-read a pinned artifact, optionally validating against all parents."""
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise MemoryError("watershed paths exceed 32MiB")
    payload = path.read_bytes()
    if len(payload) > MAX_BYTES:
        raise MemoryError("watershed paths exceed 32MiB")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("external watershed file SHA256 mismatch")
    paths = json.loads(payload)
    if paths.get("identity_sha256") != expected_identity:
        raise ValueError("external watershed identity mismatch")
    validate_watershed_paths(paths, graph, hierarchy, ordinary)
    return paths
