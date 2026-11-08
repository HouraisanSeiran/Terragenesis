"""Cold audit of pinned watershed candidates, without generators or water replay."""

import argparse
from collections import Counter, defaultdict, deque
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, publish_bytes

PARENT_SHA = "79d6b056cb4a3d612009daea42e1f45fbf5ed19950b625d1c7ee5e8d90e401f6"
PARENT_AUDIT_SHA = "bff158c828efedfecb975d6201986128b1b73059a40f96ca3216062bc58fbded"
MAX_BYTES = 32 * 1024**2
ANCHORS = {"lake_entry", "spill", "engineering", "lake_terminal"}
FLAGS = {
    "hydraulic_ready", "hydraulic_verified", "natural_outlet_verified", "publishable",
    "permanent_trunk_ready", "permanent_river_verified", "transient_converged",
    "solver_advanced", "bed_changed", "water_generated", "bed_modified",
    "material_budget_verified", "new_bed_hydrology_verified", "flow_regime_certified",
    "junction_patch_ready", "bed_rasterized", "generation_requested", "fine_dem_available",
    "water_surface_meshed", "channel_verified", "is_terrestrial_river", "is_sea_outlet"}
FORBIDDEN = (
    'terrain_pipeline.channel_geometry.build_watershed_paths',
    'terrain_pipeline.channel_geometry._td_watershed_paths_build',
    'terrain_pipeline.channel_geometry._td_watershed_paths_inputs',
    'terrain_pipeline.channel_geometry.validate_watershed_paths',
    'terrain_pipeline.channel_geometry._i49_build_outlet_forest',
    'terrain_pipeline.channel_geometry._i49_trace_spill_connection',
    'terrain_pipeline.channel_geometry._i49_trace_engineering_outlet',
    'terrain_pipeline.channel_geometry.build_watershed_sections',
    'terrain_pipeline.channel_geometry._carriers',
    'terrain_pipeline.channel_geometry._i50__width_depth',
    'terrain_pipeline.channel_geometry.validate_watershed_sections',
    'terrain_pipeline.basin_topology.build_outlet_forest',
    'terrain_pipeline.basin_topology.build_lake_spill_graph',
    'terrain_pipeline.basin_topology.build_outlet_forest',
    'terrain_pipeline.basin_topology.trace_spill_connection',
    'terrain_pipeline.basin_topology.trace_engineering_outlet',
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
    "terrain_pipeline.td_natural_river_network.build_natural_river_network",
    "terrain_pipeline.td_natural_river_network._width_depth",
    'terrain_pipeline.runoff.simulate_rainfall_runoff',
    "scipy.integrate.solve_ivp", "scipy.integrate.Radau",
    "tools.prepare_td_watershed_geometry.run",
    "tools.prepare_td_watershed_geometry.build_watershed_paths",
    "tools.prepare_td_watershed_geometry.build_watershed_sections",
    "tools.prepare_td_watershed_geometry.make_review",
    "tools.prepare_td_watershed_geometry.render_review")
SHAPE_FIELDS = ("schema", "source_identity_sha256", "hierarchy_identity_sha256",
                "topology_identity_sha256", "ordinary_identity_sha256", "parameters",
                "selected_leaf_ids", "node_sections", "mesh", "edge_sections", "support_arcs",
                "reach_diagnostics", "fine_requests", "exchange_injections")
LEVELS = ("small_gully", "seasonal_tributary", "perennial_tributary", "mainstem")
PREFIXES = ("gully", "seasonal", "perennial", "mainstem")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def equal(actual, expected, label):
    if isinstance(expected, dict):
        require(isinstance(actual, dict), label + ": expected object")
        for key, value in expected.items():
            require(key in actual, label + ": missing " + key)
            equal(actual[key], value, label + "." + key)
    elif isinstance(expected, (list, tuple)):
        require(isinstance(actual, (list, tuple)) and len(actual) == len(expected), label + ": length")
        for position, (left, right) in enumerate(zip(actual, expected)):
            equal(left, right, f"{label}[{position}]")
    elif isinstance(expected, float):
        require(type(actual) in (int, float) and math.isfinite(actual) and
                math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-8), label + ": numeric mismatch")
    else:
        require(type(actual) is type(expected) and actual == expected, label + ": mismatch")


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def number(value):
        value = float(value)
        require(math.isfinite(value), "nonfinite JSON")
        return value

    def constant(value):
        raise ValueError("nonfinite JSON: " + value)

    require(path.stat().st_size <= MAX_BYTES, "JSON exceeds 32MiB")
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


def pinned(pin, base, seen, local=False):
    path = (base / pin["path"]).resolve(strict=True)
    require(path.is_relative_to(base.resolve() if local else ROOT.resolve()), "pin escapes allowed root")
    require(file_sha256(path) == pin["sha256"], "file SHA mismatch: " + str(path))
    require(path not in seen or seen[path] == pin["sha256"], "contradictory file pins")
    if "bytes" in pin:
        require(path.stat().st_size == pin["bytes"], "pinned byte count mismatch")
    seen[path] = pin["sha256"]
    return path


def json_pin(pin, base, seen, local=False):
    result = read_json(pinned(pin, base, seen, local))
    if "identity_sha256" in pin:
        require(result["identity_sha256"] == pin["identity_sha256"], "external JSON identity mismatch")
    return result


def bundle(pin, base, seen):
    def check(result):
        require(result["identity_sha256"] == pin["identity_sha256"] ==
                identity(result["arrays"], result["metadata"]), "bundle identity mismatch")
    return load_bundle(pinned(pin, base, seen), expected_sha256=pin["sha256"], validator=check)


def envelope(record, schema):
    require(record["schema"] == schema, "schema mismatch: " + schema)
    require(record["identity_sha256"] == digest({key: value for key, value in record.items()
                                                if key != "identity_sha256"}), "record identity mismatch")
    false_flags(record)
    required = {"hydraulic_ready", "natural_outlet_verified", "publishable"}
    if schema != "td-original-bed-overflow-topology-v1":
        required.add("permanent_trunk_ready")
    if schema in ("td-lake-spill-graph-v1", "td-watershed-paths-v1", "td-watershed-geometry-review-v1"):
        required.update(("solver_advanced", "bed_changed"))
    if schema == "td-watershed-sections-v1":
        required.update(("material_budget_verified", "new_bed_hydrology_verified",
                         "flow_regime_certified", "junction_patch_ready"))
    flag_record = record["metadata"] if schema == "td-original-bed-overflow-topology-v1" else record
    require(all(flag_record.get(name) is False for name in required), "missing required false flags")


def false_flags(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FLAGS:
                require(child is False, "certification/generation flag: " + key)
            false_flags(child)
    elif isinstance(value, list):
        for child in value:
            false_flags(child)


def context(hierarchy, topology, ordinary):
    arrays = hierarchy["arrays"]
    bed = arrays["height_m"].ravel()
    owner = arrays["contribution_owner"].ravel()
    usable = arrays["valid_mask"].ravel() & ~arrays["protected_mask"].ravel()
    leaves = topology["arrays"]["leaf_ids"]
    usable &= np.isin(owner, leaves)
    spacing = float(hierarchy["metadata"]["spacing_m"])
    columns = arrays["height_m"].shape[1]
    receiver = arrays["receiver"].ravel()
    duration = float(ordinary["metadata"]["duration_s"])
    require(len(bed) <= 250_000 and spacing > 0 and duration == 86400., "source/event budget")
    stage = ordinary["arrays"]["stage_m"]
    runoff = ordinary["arrays"]["outflow_volume_m3"]
    require(stage.shape == (289, len(leaves)) and runoff.shape == (288, len(leaves)), "ordinary array shape")
    require(np.isfinite(stage).all() and np.isfinite(runoff).all() and (runoff >= 0).all(), "ordinary data")
    area = np.where(usable, spacing**2, 0.)
    local = np.zeros(len(bed))
    exchange = np.zeros(len(bed))
    maximum = {}
    for position, leaf in enumerate(leaves):
        selected = usable & (owner == leaf)
        basin_area = float(topology["arrays"]["leaf_area_m2"][position])
        equal(basin_area, float(selected.sum()) * spacing**2, "usable leaf area")
        local[selected] = float(runoff[:, position].sum()) / duration / basin_area * spacing**2
        maximum[int(leaf)] = float(stage[:, position].max())
    injections = []
    forward, reverse = (ordinary["arrays"][name] for name in ("face_forward_m3", "face_reverse_m3"))
    require(forward.shape == reverse.shape == (288, len(topology["faces"])), "ordinary face shape")
    require(np.isfinite(forward).all() and np.isfinite(reverse).all() and
            (forward >= 0).all() and (reverse >= 0).all(), "ordinary face arrays")
    for position, face in enumerate(topology["faces"]):
        signed = float((forward[:, position] - reverse[:, position]).sum())
        if signed == 0:
            continue
        source, target_leaf = face["leaf_ids"] if signed > 0 else face["leaf_ids"][::-1]
        cells = face["cell_ids"]
        equal(cells, arrays["face_cells"][face["face_index"]].tolist(), "incoming physical face")
        target = next(cell for cell in cells if owner[cell] == target_leaf)
        require(usable[target], "net input onto unusable cell")
        exchange[target] += abs(signed) / duration
        injections.append({"face_id": face["face_id"], "source_leaf_id": source,
                           "receiver_leaf_id": target_leaf, "receiver_cell_id": target,
                           "net_volume_m3": abs(signed), "representative_q_m3_s": abs(signed) / duration,
                           "semantics": "actual_net_exchange_not_source_attribution"})
    donors = np.zeros(len(bed), dtype=np.int64)
    for cell in np.flatnonzero(usable):
        target = int(receiver[cell])
        if target < 0:
            require(target == -1, "invalid sink")
            continue
        require(0 <= target < len(bed) and usable[target] and owner[target] == owner[cell] and
                abs(cell // columns - target // columns) + abs(cell % columns - target % columns) == 1 and
                bed[target] <= bed[cell], "invalid native receiver")
        donors[target] += 1
    pending = donors.copy()
    queue = deque(int(cell) for cell in np.flatnonzero(usable & (pending == 0)))
    order = []
    while queue:
        cell = queue.popleft()
        order.append(cell)
        target = int(receiver[cell])
        if target >= 0:
            area[target] += area[cell]
            local[target] += local[cell]
            exchange[target] += exchange[cell]
            pending[target] -= 1
            if pending[target] == 0:
                queue.append(target)
    require(len(order) == int(usable.sum()), "receiver cycle")
    return dict(arrays=arrays, bed=bed, owner=owner, usable=usable, receiver=receiver,
                donors=donors, area=area, local=local, exchange=exchange, maximum=maximum,
                spacing=spacing, columns=columns, order=order, injections=injections,
                origin=hierarchy["metadata"]["origin_m_xz"], hierarchy=hierarchy)


def xyz(context_data, cell):
    return [float(context_data["origin"][0] + cell % context_data["columns"] * context_data["spacing"]),
            float(context_data["bed"][cell]),
            float(context_data["origin"][1] + cell // context_data["columns"] * context_data["spacing"])]


def audit_paths(paths, graph, data):
    envelope(paths, "td-watershed-paths-v1")
    primary = graph["routing_forest"]["primary_component"]
    selected = primary["leaf_ids"]
    equal(paths["selected_leaf_ids"], selected, "primary leaf selection")
    require(paths["parameters"]["minimum_area_m2"] == 3600., "fixed land threshold")
    equal(paths, {"grid_shape": list(data["arrays"]["height_m"].shape), "spacing_m": data["spacing"],
                  "origin_m_xz": data["origin"]}, "path native grid")
    cells = np.flatnonzero(data["usable"] & np.isin(data["owner"], selected))
    unknown = data["arrays"]["node_unknown_contact"]
    require(not unknown[selected].any() and
            not unknown[data["arrays"]["cell_owner"].ravel()[cells]].any(), "unknown primary cells")
    require(len(cells) == int((data["arrays"]["valid_mask"].ravel() &
                              np.isin(data["owner"], selected)).sum()), "protected primary")
    expected = {}
    interfaces = defaultdict(list)
    main_pairs = set()
    main_faces = set(graph["routing_forest"]["main_path_face_ids"])
    by_face = {edge["face_id"]: edge for edge in graph["edges"]}
    parents = {record["leaf_id"]: record for record in graph["routing_forest"]["records"]}
    sinks = {}
    for leaf in selected:
        leaf_cells = cells[data["owner"][cells] == leaf]
        terminals = leaf_cells[data["receiver"][leaf_cells] == -1]
        require(len(terminals) == 1, "leaf terminal coverage")
        sinks[leaf] = int(terminals[0])
        parent = parents[leaf]
        if parent["parent_leaf_id"] is None:
            continue
        edge = by_face[parent["parent_face_id"]]
        require(edge["routing_eligible"] and edge["source_leaf_id"] == leaf and
                edge["receiver_leaf_id"] == parent["parent_leaf_id"] and
                parents[parent["parent_leaf_id"]]["hops"] == parent["hops"] - 1, "parent path orientation/hops")
        geometry = edge["geometry"]
        require(geometry["status"] == "accepted", "parent support rejected")
        if edge["face_id"] in main_faces:
            route = geometry["downhill_terrain_approach"]["cell_ids"]
            main_pairs.update(zip(route, route[1:]))
        for kind in ("source_lake_approach", "cross_face", "downhill_terrain_approach"):
            support = geometry[kind]
            expected[f"face:{edge['face_id']}:{kind}"] = dict(
                kind=kind, cell_ids=support["cell_ids"], source_geometry=support,
                sampled_source_stage=edge["sampled_source_stage"], face_id=edge["face_id"],
                leaf_id=edge["receiver_leaf_id"] if kind == "downhill_terrain_approach" else leaf,
                is_main_path=edge["face_id"] in main_faces, channel_candidate=False)
    root = next(outlet for outlet in graph["outlets"] if outlet["routing_eligible"] and
                outlet["leaf_id"] == primary["root_leaf_id"] and outlet["cell_id"] == primary["root_boundary_cell_id"])
    expected[f"outlet:{root['cell_id']}"] = dict(kind="engineering_outlet_support",
        cell_ids=root["geometry"]["source_lake_approach"]["cell_ids"],
        source_geometry=root["geometry"]["source_lake_approach"], sampled_source_stage=root["sampled_source_stage"],
        leaf_id=root["leaf_id"], face_id=None, is_main_path=True, channel_candidate=False)
    for cell_value in cells:
        cell = int(cell_value)
        target = int(data["receiver"][cell])
        if target < 0 or data["area"][cell] < 3600.:
            continue
        leaf = int(data["owner"][cell])
        dry = data["bed"][[cell, target]] > data["maximum"][leaf]
        kind = "land_channel" if dry.all() else "lake_entry_support" if dry[0] else "lake_receiver_support"
        arc_id = f"receiver:{cell}:{target}"
        expected[arc_id] = dict(kind=kind, cell_ids=[cell, target], leaf_id=leaf, face_id=None,
                                is_main_path=(cell, target) in main_pairs, channel_candidate=kind == "land_channel")
        if kind == "lake_entry_support":
            interface = dict(land_node_id=f"cell:{cell}", wet_node_id=f"cell:{target}", support_arc_id=arc_id)
            interfaces[leaf].append(interface)
            expected[arc_id].update(lake_interface=interface,
                                   interface_node_ids=[interface["land_node_id"], interface["wet_node_id"]])
    arcs = {arc["arc_id"]: arc for arc in paths["arcs"]}
    require(len(arcs) == len(paths["arcs"]) and set(arcs) == set(expected), "complete typed arc coverage")
    node_kinds = defaultdict(set)
    for arc_id, wanted in expected.items():
        arc = arcs[arc_id]
        equal(arc, wanted, "arc " + arc_id)
        if "source_geometry" in wanted:
            require(arc["source_geometry"] == wanted["source_geometry"] and
                    arc["sampled_source_stage"] == wanted["sampled_source_stage"], "parent support must be verbatim")
        route = wanted["cell_ids"]
        equal(arc["node_ids"], [f"cell:{cell}" for cell in route], "shared arc references")
        equal(arc["xyz_m"], [xyz(data, cell) for cell in route], "native arc XYZ")
        equal(arc["local_upstream_area_m2"], float(data["area"][route[0]]), "arc local area")
        for first, second in zip(route, route[1:]):
            require(abs(first // data["columns"] - second // data["columns"]) +
                    abs(first % data["columns"] - second % data["columns"]) == 1, "support not D4")
        for cell in route:
            require(data["usable"][cell] and int(data["owner"][cell]) in selected, "unusable arc cell")
            node_kinds[cell].add(wanted["kind"])
        if wanted["kind"] == "cross_face":
            for cell in route:
                node_kinds[cell].add("spill")
    for leaf, terminal in sinks.items():
        node_kinds[terminal].add("lake_terminal")
        for interface in interfaces[leaf]:
            for field in ("land_node_id", "wet_node_id"):
                node_kinds[int(interface[field].split(":")[1])].update(("lake_entry", "lake_interface"))
    node_kinds[root["cell_id"]].add("engineering")
    nodes = {node["cell_id"]: node for node in paths["nodes"]}
    require(len(nodes) == len(paths["nodes"]) and set(nodes) == set(node_kinds), "shared node coverage")
    for cell, kinds in node_kinds.items():
        if data["donors"][cell] >= 2:
            kinds.add("confluence")
        if data["bed"][cell] <= data["maximum"][int(data["owner"][cell])]:
            kinds.add("lake_covered")
        equal(nodes[cell], dict(node_id=f"cell:{cell}", cell_id=cell, xyz_m=xyz(data, cell),
              leaf_id=int(data["owner"][cell]), kinds=sorted(kinds),
              lake_interfaces=sorted(kinds & (ANCHORS | {"lake_interface"})),
              local_upstream_area_m2=float(data["area"][cell])), "shared cell node")
    lakes = {lake["leaf_id"]: lake for lake in paths["lakes"]}
    require(len(lakes) == len(paths["lakes"]) and set(lakes) == set(selected), "lake coverage")
    for leaf, lake in lakes.items():
        leaf_cells = cells[data["owner"][cells] == leaf]
        equal(lake, dict(terminal_cell_id=sinks[leaf], terminal_node_id=f"cell:{sinks[leaf]}",
              ordinary_stage_max_m=data["maximum"][leaf], covered_cell_ids=[int(cell) for cell in leaf_cells
              if data["bed"][cell] <= data["maximum"][leaf]], exclusive_area_m2=len(leaf_cells) * data["spacing"]**2,
              local_terminal_upstream_area_m2=float(data["area"][sinks[leaf]]), entry_interfaces=interfaces[leaf]), "lake footprint")
        for kind, field in (("lake_entry", "entry_node_ids"), ("spill", "spill_node_ids"),
                            ("engineering", "engineering_node_ids")):
            equal(lake[field], [nodes[cell]["node_id"] for cell in sorted(nodes)
                               if nodes[cell]["leaf_id"] == leaf and kind in nodes[cell]["kinds"]], "lake anchors")
    equal(paths["budget"], dict(max_cells=250_000, max_arcs=250_000, max_path_samples=1_000_000,
          max_bytes=MAX_BYTES, selected_valid_cells=len(cells), path_samples=sum(len(arc["cell_ids"]) for arc in arcs.values())), "paths budget")
    return {node["node_id"]: node for node in nodes.values()}, arcs, cells


def dimensions(discharge, slope, recipe):
    ratio = max(discharge / recipe["reference_q_m3_s"], 1e-12)
    factor = min(1.5, max(.7, (max(slope, .0001) / .01)**(-.08)))
    width = recipe["reference_width_m"] * ratio**recipe["width_exponent"] * factor * (.8 + .4 * recipe["material_erodibility"])
    depth = recipe["reference_depth_m"] * ratio**recipe["depth_exponent"] / factor
    return min(recipe["maximum_width_m"], max(recipe["minimum_width_m"], width)), min(
        recipe["maximum_depth_m"], max(recipe["minimum_depth_m"], depth))


def level_for(area, discharge, width, depth, recipe):
    level = None
    for index, prefix in enumerate(PREFIXES):
        area_key = ("minimum_area_m2", "seasonal_area_m2", "perennial_area_m2", "mainstem_area_m2")[index]
        flow_key = ("minimum_q_m3_s", "seasonal_q_m3_s", "perennial_q_m3_s", "mainstem_q_m3_s")[index]
        flow = recipe[flow_key] * (1.2 - .4 * recipe["material_erodibility"] if index == 0 else 1.)
        if area >= recipe[area_key] and discharge >= flow and width >= recipe[prefix + "_min_width_m"] and depth >= recipe[prefix + "_min_depth_m"]:
            level = index
    return level


def sample_bank(data, selected, east, south):
    row = (south - data["origin"][1]) / data["spacing"]
    column = (east - data["origin"][0]) / data["spacing"]
    rows, columns = data["arrays"]["height_m"].shape
    require(0 <= row <= rows - 1 and 0 <= column <= columns - 1, "outside_source_coverage")
    row0, column0 = math.floor(row), math.floor(column)
    row1, column1 = min(row0 + 1, rows - 1), min(column0 + 1, columns - 1)
    corners = [row0 * columns + column0, row0 * columns + column1,
               row1 * columns + column0, row1 * columns + column1]
    require(data["arrays"]["valid_mask"].ravel()[corners].all(), "unknown_source_coverage")
    require(not data["arrays"]["protected_mask"].ravel()[corners].any(), "protected_source_coverage")
    require(all(int(data["owner"][cell]) in selected for cell in corners), "outside_selected_component")
    fraction_row, fraction_column = row - row0, column - column0
    weights = [(1 - fraction_row) * (1 - fraction_column), (1 - fraction_row) * fraction_column,
               fraction_row * (1 - fraction_column), fraction_row * fraction_column]
    return float(sum(weight * data["bed"][cell] for weight, cell in zip(weights, corners)))


def audit_sections(sections, nodes, arcs, data, paths):
    envelope(sections, "td-watershed-sections-v1")
    require(sections["candidate_shape_identity_sha256"] == digest({field: sections[field] for field in SHAPE_FIELDS}), "actual output shape identity")
    equal(sections["composite_parent_identity"], dict(paths=paths["identity_sha256"], graph=paths["graph_identity_sha256"]), "composite parent")
    equal(sections["selected_leaf_ids"], paths["selected_leaf_ids"], "section leaves")
    equal(sections["exchange_injections"], data["injections"], "all-face net carrier injections")
    require(sections["support_arcs"] == [arcs[key] for key in sorted(arcs) if not arcs[key]["channel_candidate"]], "support carrier altered")
    equal(sections, dict(parametric_only=True, bed_rasterized=False, bed_changed=False,
          source=dict(bed_changed=False), candidate_changed="geometry_only", ordinary_duration_s=86400.,
          source_spacing_m=data["spacing"]), "geometry-only sections")
    recipe = sections["parameters"]
    from dataclasses import asdict
    from terrain_pipeline.td_natural_river_network import NaturalNetworkRecipe
    require(recipe == asdict(NaturalNetworkRecipe()), "preparation must use unchanged default recipe")
    land = [arcs[key] for key in sorted(arcs) if arcs[key]["channel_candidate"]]
    incident, donors = defaultdict(list), defaultdict(set)
    for arc in land:
        first, second = arc["node_ids"]
        incident[first].append(arc)
        incident[second].append(arc)
        donors[second].add(first)
    expected = {}
    levels = {}
    for identifier in sorted(incident):
        node = nodes[identifier]
        cell = node["cell_id"]
        discharge = float(data["local"][cell] + data["exchange"][cell])
        target = int(data["receiver"][cell])
        slope = max(0., float((data["bed"][cell] - data["bed"][target]) / data["spacing"])) if target >= 0 else 0.
        width, depth = dimensions(discharge, slope, recipe)
        level = level_for(data["area"][cell], discharge, width, depth, recipe)
        levels[identifier] = level
        expected[identifier] = dict(width_m=width, depth_m=depth, bed_m=node["xyz_m"][1] - depth,
            representative_q_m3_s=discharge, geometry_threshold_level=LEVELS[level] if level is not None else None,
            level=LEVELS[level] + "_proxy" if level is not None else "needs_evidence",
            anchor=bool(set(node["kinds"]) & ANCHORS), junction=len(donors[identifier]) > 1)
    for cell in data["order"]:
        identifier, target_id = f"cell:{cell}", f"cell:{int(data['receiver'][cell])}"
        if identifier not in expected or target_id not in expected:
            continue
        source, target = expected[identifier], expected[target_id]
        for field in ("width_m", "depth_m", "representative_q_m3_s"):
            target[field] = max(source[field], target[field])
        target["bed_m"] = min(nodes[target_id]["xyz_m"][1] - target["depth_m"], source["bed_m"] - .0001 * data["spacing"])
    node_sections = {section["node_id"]: section for section in sections["node_sections"]}
    require(len(node_sections) == len(sections["node_sections"]) and set(node_sections) == set(nodes), "section node coverage")
    for identifier, node in nodes.items():
        section = node_sections[identifier]
        cell = node["cell_id"]
        equal(section, dict(cell_id=cell, source_xyz_m=node["xyz_m"],
              local_runoff_q_m3_s=float(data["local"][cell]), incoming_exchange_q_m3_s=float(data["exchange"][cell]),
              local_upstream_area_m2=float(data["area"][cell]), parametric_only=True,
              bed_rasterized=False, flow_regime_certified=False, needs_evidence=True), "node carrier")
        if identifier not in expected:
            equal(section, dict(width_m=0., depth_m=0., bed_m=node["xyz_m"][1], required_cut_m=0.,
                  level="source_support_only", geometry_threshold_level=None, cross_section_xyz_m=[],
                  anchor=bool(set(node["kinds"]) & ANCHORS), junction=False,
                  representative_q_m3_s=float(data["local"][cell] + data["exchange"][cell])), "unchanged support node")
            continue
        wanted = expected[identifier]
        required_reasons = []
        if wanted["anchor"]:
            wanted.update(bed_m=node["xyz_m"][1], depth_m=0.)
            required_reasons.append("anchor_cut_conflict")
        if wanted["junction"] or len(incident[identifier]) >= 3:
            required_reasons.append("needs_junction_patch")
        wanted["required_cut_m"] = node["xyz_m"][1] - wanted["bed_m"]
        if wanted["required_cut_m"] > 4. + 1e-9:
            required_reasons.append("four_metre_cut_budget_exceeded")
        reference = next((arc for arc in incident[identifier] if arc["node_ids"][0] == identifier), incident[identifier][0])
        direction = np.asarray(reference["xyz_m"][1])[[0, 2]] - np.asarray(reference["xyz_m"][0])[[0, 2]]
        normal = [-float(direction[1]) / float(np.linalg.norm(direction)), float(direction[0]) / float(np.linalg.norm(direction))]
        wanted["transverse_unit_xz"] = normal
        run = wanted["depth_m"] * recipe[PREFIXES[levels[identifier] or 0] + "_bank_slope_h_per_v"]
        width = wanted["width_m"]
        profile = []
        try:
            for position, offset in enumerate((-width / 2 - run, -width / 2, width / 2, width / 2 + run)):
                east, south = node["xyz_m"][0] + normal[0] * offset, node["xyz_m"][2] + normal[1] * offset
                bank = sample_bank(data, set(paths["selected_leaf_ids"]), east, south)
                require(bank >= wanted["bed_m"] - 1e-9, "bank_below_candidate_bed")
                require(position not in (1, 2) or bank - wanted["bed_m"] <= 4. + 1e-9, "transverse_four_metre_cut_budget_exceeded")
                profile.append([east, wanted["bed_m"] if position in (1, 2) else bank, south])
        except ValueError as error:
            required_reasons.append(str(error))
            profile = []
        wanted["cross_section_xyz_m"] = profile
        equal(section, wanted, "shared width/depth/bed/profile")
        equal(section["rejection_reasons"], required_reasons, "node rejection evidence")
        expected_evidence = []
        if levels[identifier] is None:
            expected_evidence.append("area_or_ordinary_carrier_geometry_threshold_unmet")
        elif levels[identifier] >= 2:
            expected_evidence.append("perennial_frequency_baseflow_and_duration_unmeasured")
        equal(section["evidence_reasons"], expected_evidence or ["uncalibrated_ordinary_event_carrier"], "flow proxy evidence")
    diagnostics = {item["arc_id"]: item for item in sections["reach_diagnostics"]}
    require(len(diagnostics) == len(land) == len(sections["reach_diagnostics"]) and
            set(diagnostics) == {arc["arc_id"] for arc in land}, "reach diagnostic coverage")
    for arc in land:
        diagnostic = diagnostics[arc["arc_id"]]
        first, second = (node_sections[identifier] for identifier in arc["node_ids"])
        required_reasons = set(first["rejection_reasons"] + second["rejection_reasons"])
        if any(levels[identifier] is None for identifier in arc["node_ids"]):
            required_reasons.add("insufficient_ordinary_supply_or_area")
        if first["bed_m"] - second["bed_m"] < .0001 * data["spacing"] - 1e-9:
            required_reasons.add("candidate_bed_slope_failed")
        if not required_reasons:
            profile = first["cross_section_xyz_m"] + second["cross_section_xyz_m"]
            signs = []
            for position in range(3):
                for triangle in ((position, position + 4, position + 1), (position + 1, position + 4, position + 5)):
                    points = [profile[index] for index in triangle]
                    signs.append((points[1][0] - points[0][0]) * (points[2][2] - points[0][2]) -
                                 (points[1][2] - points[0][2]) * (points[2][0] - points[0][0]))
            if min(abs(value) for value in signs) < 1e-9 or min(signs) < 0 < max(signs):
                required_reasons.add("folded_or_degenerate_bank_geometry")
        mesh_reasons = {"nonpositive_projected_triangle_area", "nonmanifold_mesh_edge",
                        "inconsistent_mesh_edge_orientation", "overlapping_mesh_triangles"}
        actual_reasons = set(diagnostic["rejection_reasons"])
        require(required_reasons <= actual_reasons and actual_reasons <= required_reasons | mesh_reasons,
                "reach refusal does not match independently checked evidence")
        require(not required_reasons or not actual_reasons & mesh_reasons,
                "mesh check claimed on an already rejected reach")
        equal(diagnostic, dict(node_ids=arc["node_ids"], kind="land_channel", is_main_path=arc["is_main_path"],
              status="rejected" if diagnostic["rejection_reasons"] else "geometry_candidate",
              representative_q_m3_s=max(first["representative_q_m3_s"], second["representative_q_m3_s"]),
              level=first["level"], needs_evidence=True, flow_regime_certified=False), "reach carrier/status")
    return node_sections, levels, land, diagnostics


def overlaps(first, second):
    for triangle in (first, second):
        for index in range(3):
            edge = triangle[(index + 1) % 3] - triangle[index]
            axis = np.array([edge[1], -edge[0]])
            length = float(np.linalg.norm(axis))
            if length < 1e-12:
                continue
            left, right = first @ (axis / length), second @ (axis / length)
            if min(left.max(), right.max()) - max(left.min(), right.min()) <= 1e-9:
                return False
    return True


def audit_mesh(sections, node_sections, arcs, diagnostics, spacing):
    mesh = sections["mesh"]
    equal(mesh, dict(parametric_only=True, bed_rasterized=False, junction_patch_ready=False,
                    positive_projected_area=True, nonoverlapping_projection=True), "mesh envelope")
    vertices = np.asarray(mesh["vertices_xyz_m"], dtype=float).reshape(-1, 3)
    require(np.isfinite(vertices).all() and len(vertices) <= 1_000_000, "mesh vertices")
    index_owners = []
    for identifier, indices in mesh["node_vertex_indices"].items():
        require(identifier in node_sections and len(indices) == 4 and
                all(type(index) is int and 0 <= index < len(vertices) for index in indices), "shared mesh index")
        equal(vertices[indices].tolist(), node_sections[identifier]["cross_section_xyz_m"], "mesh shared section")
        index_owners.extend(indices)
    require(sorted(index_owners) == list(range(len(vertices))), "vertex sharing/coverage")
    incidence, buckets = defaultdict(list), defaultdict(list)
    projected = []
    triangles = mesh["triangles"]
    require(len(triangles) == len(mesh["triangle_arc_ids"]) <= 1_500_000, "triangle provenance/count")
    for position, triangle in enumerate(triangles):
        require(len(triangle) == len(set(triangle)) == 3 and
                all(type(index) is int and 0 <= index < len(vertices) for index in triangle), "triangle indices")
        points = vertices[triangle][:, (0, 2)]
        signed = (points[1, 0] - points[0, 0]) * (points[2, 1] - points[0, 1]) - (points[1, 1] - points[0, 1]) * (points[2, 0] - points[0, 0])
        require(signed / 2 > 1e-9, "degenerate/nonpositive triangle")
        for first, second in zip(triangle, triangle[1:] + triangle[:1]):
            key = tuple(sorted((first, second)))
            require(len(incidence[key]) < 2 and (not incidence[key] or incidence[key][0] == (second, first)), "mesh incidence/orientation")
            incidence[key].append((first, second))
        bounds = np.floor(np.array([points.min(axis=0), points.max(axis=0)]) / spacing).astype(int)
        keys = [(east, south) for east in range(bounds[0, 0], bounds[1, 0] + 1)
                for south in range(bounds[0, 1], bounds[1, 1] + 1)]
        for other in {other for key in keys for other in buckets[key]}:
            require(not overlaps(points, projected[other]), "positive-area projected triangle overlap")
        for key in keys:
            buckets[key].append(position)
        projected.append(points)
    equal(mesh["edge_incidence_max"], max((len(value) for value in incidence.values()), default=0), "incidence summary")
    accepted = {identifier for identifier, item in diagnostics.items() if not item["rejection_reasons"]}
    edges = {edge["arc_id"]: edge for edge in sections["edge_sections"]}
    require(len(edges) == len(sections["edge_sections"]) and set(edges) == accepted, "accepted mesh reach coverage")
    coverage = []
    for identifier, edge in edges.items():
        arc = arcs[identifier]
        equal(edge["node_ids"], arc["node_ids"], "edge endpoints")
        equal(edge["cross_section_xyz_m"], [node_sections[node_id]["cross_section_xyz_m"] for node_id in arc["node_ids"]], "shared edge bed")
        indices = edge["triangle_indices"]
        require(len(indices) == 6 and len(set(indices)) == 6 and
                all(type(index) is int and 0 <= index < len(triangles) and mesh["triangle_arc_ids"][index] == identifier for index in indices), "six strip triangles/provenance")
        first, second = (mesh["node_vertex_indices"][node_id] for node_id in arc["node_ids"])
        expected = []
        for position in range(3):
            expected.extend([frozenset((first[position], second[position], first[position + 1])),
                             frozenset((first[position + 1], second[position], second[position + 1]))])
        require(Counter(frozenset(triangles[index]) for index in indices) == Counter(expected), "strip triangle topology")
        coverage.extend(indices)
    require(sorted(coverage) == list(range(len(triangles))), "triangle coverage")
    mesh_reasons = {"nonpositive_projected_triangle_area", "nonmanifold_mesh_edge",
                    "inconsistent_mesh_edge_orientation", "overlapping_mesh_triangles"}
    for identifier in sorted(diagnostics):
        claimed = set(diagnostics[identifier]["rejection_reasons"]) & mesh_reasons
        if not claimed:
            continue
        first_id, second_id = arcs[identifier]["node_ids"]
        profile = node_sections[first_id]["cross_section_xyz_m"] + node_sections[second_id]["cross_section_xyz_m"]
        require(len(profile) == 8 and len(claimed) == 1, "invalid mesh refusal provenance")
        local_triangles = []
        for position in range(3):
            local_triangles.extend([(position, position + 4, position + 1), (position + 1, position + 4, position + 5)])
        local_points = np.asarray(profile)[:, (0, 2)]
        signed = np.linalg.det(np.vstack((local_points[local_triangles[0][1]] - local_points[local_triangles[0][0]],
                                         local_points[local_triangles[0][2]] - local_points[local_triangles[0][0]])))
        if signed < 0:
            local_triangles = [triangle[::-1] for triangle in local_triangles]
        previous = [position for position, arc_id in enumerate(mesh["triangle_arc_ids"]) if arc_id < identifier]
        problem = None
        hypothetical = {(node_id, offset): mesh["node_vertex_indices"].get(node_id, [f"{node_id}:{index}" for index in range(4)])[offset]
                        for node_id in (first_id, second_id) for offset in range(4)}
        staged_edges = defaultdict(list)
        staged_points = []
        for triangle in local_triangles:
            points = local_points[list(triangle)]
            area = np.linalg.det(np.vstack((points[1] - points[0], points[2] - points[0]))) / 2
            if area <= 1e-9:
                problem = "nonpositive_projected_triangle_area"
                break
            references = [hypothetical[(first_id if index < 4 else second_id, index % 4)] for index in triangle]
            for first, second in zip(references, references[1:] + references[:1]):
                key = frozenset((first, second))
                earlier = []
                for position in previous:
                    other = triangles[position]
                    earlier.extend((start, end) for start, end in zip(other, other[1:] + other[:1])
                                   if frozenset((start, end)) == key)
                directions = earlier + staged_edges[key]
                if len(directions) >= 2:
                    problem = "nonmanifold_mesh_edge"
                    break
                if directions and directions[0] != (second, first):
                    problem = "inconsistent_mesh_edge_orientation"
                    break
                staged_edges[key].append((first, second))
            if problem:
                break
            if any(overlaps(points, projected[position]) for position in previous) or any(overlaps(points, other) for other in staged_points):
                problem = "overlapping_mesh_triangles"
                break
            staged_points.append(points)
        require(claimed == {problem}, "mesh refusal lacks independent geometric witness")


def audit_fine(sections, nodes, arcs, node_sections, levels, land, data, selected):
    recipe = sections["parameters"]
    windows = {}

    def carrier_dimensions(cell, request_id):
        section = node_sections[f"cell:{cell}"]
        canonical_q = section["local_runoff_q_m3_s"] + section["incoming_exchange_q_m3_s"]
        independent_q = float(data["local"][cell] + data["exchange"][cell])
        equal(canonical_q, independent_q, "fine request " + request_id + ": verified carrier")
        canonical = dimensions(canonical_q, 0., recipe)
        equal(canonical, dimensions(independent_q, 0., recipe),
              "fine request " + request_id + ": verified width/depth")
        return canonical

    for arc in land:
        first, second = (node_sections[node_id] for node_id in arc["node_ids"])
        reasons = ["land_channel", "width_resolution"]
        if arc["is_main_path"]:
            reasons.append("mainline")
        if first["junction"] or second["junction"]:
            reasons.append("junction")
        windows[arc["arc_id"]] = (arc["xyz_m"], min(first["width_m"], second["width_m"]),
                                   max(first["depth_m"], second["depth_m"]), levels[arc["node_ids"][0]], reasons)
    for identifier, node in sorted(nodes.items()):
        kinds = set(node["kinds"])
        if kinds & {"spill", "engineering", "lake_entry"}:
            cell = node["cell_id"]
            width, depth = carrier_dimensions(cell, identifier)
            reasons = sorted(kinds & ANCHORS) + (["outlet"] if "engineering" in kinds else [])
            windows[identifier] = ([node["xyz_m"]], width, depth, None, reasons)
    for arc in sections["support_arcs"]:
        if arc["is_main_path"]:
            for position in range(max(1, len(arc["xyz_m"]) - 1)):
                cell = arc["cell_ids"][position]
                request_id = f"{arc['arc_id']}:window:{position}"
                width, depth = carrier_dimensions(cell, request_id)
                reasons = ["mainline", "unchanged_source_support", "width_resolution"]
                if arc["kind"] == "cross_face":
                    reasons.append("spill")
                if arc["kind"] == "engineering_outlet_support":
                    reasons.append("outlet")
                windows[request_id] = (arc["xyz_m"][position:position + 2], width, depth, None, reasons)
    requests = sections["fine_requests"]
    require(len(requests) == len(windows) and {item["request_id"] for item in requests} == set(windows), "fine window coverage")
    priority = ("outlet", "spill", "junction", "mainline")
    require(requests == sorted(requests, key=lambda item: (
        next((position for position, reason in enumerate(priority) if reason in item["reasons"]), 4), item["request_id"])), "fine priority")
    remaining = 2_000_000
    rows, columns = data["arrays"]["height_m"].shape
    for request in requests:
        points, width, depth, level, reasons = windows[request["request_id"]]
        prefix = PREFIXES[level or 0]
        spacing = min(width / 2., recipe[prefix + "_required_spacing_m"])
        padding = width / 2 + depth * recipe[prefix + "_bank_slope_h_per_v"]
        padding += recipe[prefix + "_protection_distance_m"]
        raw = [min(point[0] for point in points) - padding, min(point[2] for point in points) - padding,
               max(point[0] for point in points) + padding, max(point[2] for point in points) + padding]
        extent = [math.floor(raw[0] / spacing), math.floor(raw[1] / spacing), math.ceil(raw[2] / spacing), math.ceil(raw[3] / spacing)]
        bbox = [value * spacing for value in extent]
        shape = [extent[3] - extent[1] + 1, extent[2] - extent[0] + 1]
        count = math.prod(shape)
        refusal = []
        first_column = math.floor((bbox[0] - data["origin"][0]) / data["spacing"])
        last_column = math.ceil((bbox[2] - data["origin"][0]) / data["spacing"])
        first_row = math.floor((bbox[1] - data["origin"][1]) / data["spacing"])
        last_row = math.ceil((bbox[3] - data["origin"][1]) / data["spacing"])
        if first_column < 0 or first_row < 0 or last_column >= columns or last_row >= rows:
            refusal.append("outside_source_coverage")
        selection = np.s_[max(0, first_row):min(rows, last_row + 1), max(0, first_column):min(columns, last_column + 1)]
        arrays = data["arrays"]
        for condition, reason in ((not arrays["valid_mask"][selection].all(), "unknown_source_coverage"),
                (arrays["protected_mask"][selection].any(), "protected_source_coverage"),
                (not np.isin(arrays["contribution_owner"][selection], selected).all(), "outside_selected_component"),
                (arrays["open_boundary_mask"][selection].any(), "engineering_open_boundary_contact"),
                (count > 250_000, "window_cell_budget_exceeded"), (count > remaining, "total_fine_cell_budget_exceeded")):
            if condition:
                refusal.append(reason)
        equal(request, dict(bbox_m_xz=bbox, window_bbox_m_xz=bbox, grid_extent=extent, grid_shape=shape,
              target_spacing_m=spacing, width_m=width, estimated_cells=count, estimated_bytes=count * 32,
              reasons=sorted(set(reasons)), refusal_reasons=refusal, status="refused" if refusal else "requested",
              generation_requested=False, fine_dem_available=False, source_spacing_m=data["spacing"]),
              "fine request " + request["request_id"] + ": extent/coverage/budget")
        if ":window:" in request["request_id"]:
            equal(request["parent_arc_id"], request["request_id"].rsplit(":window:", 1)[0],
                  "fine request " + request["request_id"] + ": support provenance")
        if not refusal:
            remaining -= count
    equal(sections["budgets"], dict(max_json_bytes=MAX_BYTES, max_window_cells=250_000, max_fine_cells=2_000_000), "fine budgets")
    return 2_000_000 - remaining


def audit_saved(directory, index_sha256, seen):
    index = json_pin(dict(path="index.json", sha256=index_sha256), directory, seen, True)
    require(index["schema"] == "td-watershed-geometry-preparation-v1" and index["status"] == "ready_for_independent_audit", "index envelope")
    false_flags(index)
    require(all(index.get(name) is False for name in ("hydraulic_ready", "natural_outlet_verified",
            "permanent_trunk_ready", "publishable", "solver_advanced", "bed_changed")), "index false flags")
    equal(index, dict(parametric_only=True, bed_rasterized=False, water_surface_meshed=False), "index status")
    require(index["parent_index"]["sha256"] == PARENT_SHA and index["parent_audit"]["sha256"] == PARENT_AUDIT_SHA, "accepted parent pins")
    parent = json_pin(index["parent_index"], ROOT, seen)
    parent_base = pinned(index["parent_index"], ROOT, seen).parent
    accepted = json_pin(index["parent_audit"], ROOT, seen)
    equal(accepted, dict(status="passed", index_sha256=PARENT_SHA, cold_read=True, solver_advanced=False), "accepted parent audit")
    for source in (parent, index):
        for name, sha in source["code_sha256"].items():
            pinned(dict(path=name, sha256=sha), ROOT, seen)
    require(set(index["code_sha256"]) == {"terrain_pipeline/td_watershed_paths.py", "terrain_pipeline/td_watershed_sections.py",
            "terrain_pipeline/td_natural_river_network.py", "terrain_pipeline/common_infra.py",
            'terrain_pipeline/basin_topology.py', 'terrain_pipeline/basin_storage.py',
            'terrain_pipeline/basin_storage.py', "tools/prepare_td_watershed_geometry.py"}, "preparation code pin coverage")
    source = next(case for case in parent["cases"] if case["case_id"] == "baseline")
    expected_pins = dict(hierarchy=source["inputs"]["hierarchy"], topology=source["inputs"]["topology"], ordinary=source["inputs"]["events"]["ordinary"])
    require(set(index["inputs"]) == set(expected_pins), "ordinary-only input pins")
    for name, wanted in {**expected_pins, "parent_graph": source["graph"]}.items():
        actual = index["parent_graph"] if name == "parent_graph" else index["inputs"][name]
        require(actual["sha256"] == wanted["sha256"] and actual["identity_sha256"] == wanted["identity_sha256"] and
                pinned(actual, directory, seen) == pinned(wanted, parent_base, seen), "input differs from accepted baseline")
    hierarchy = bundle(index["inputs"]["hierarchy"], directory, seen)
    ordinary = bundle(index["inputs"]["ordinary"], directory, seen)
    topology = json_pin(index["inputs"]["topology"], directory, seen)
    envelope(topology, "td-original-bed-overflow-topology-v1")
    topology["arrays"] = {key: np.asarray(value) for key, value in topology["arrays"].items()}
    graph = json_pin(index["parent_graph"], directory, seen)
    envelope(graph, "td-lake-spill-graph-v1")
    paths = json_pin(index["paths"], directory, seen, True)
    sections = json_pin(index["sections"], directory, seen, True)
    review = json_pin(index["review"], directory, seen, True)
    parent_ids = dict(source_identity_sha256=hierarchy["metadata"]["source_identity_sha256"],
                      hierarchy_identity_sha256=hierarchy["identity_sha256"],
                      topology_identity_sha256=topology["identity_sha256"])
    equal(ordinary["metadata"], parent_ids, "ordinary immutable parents")
    equal(graph, parent_ids, "graph immutable parents")
    require(graph["event_identity_sha256"]["ordinary"] == ordinary["identity_sha256"], "graph ordinary identity")
    for record in (paths, sections):
        equal(record, dict(**parent_ids, ordinary_identity_sha256=ordinary["identity_sha256"]), "new geometry parents")
    require(paths["graph_identity_sha256"] == graph["identity_sha256"], "path graph identity")
    data = context(hierarchy, topology, ordinary)
    nodes, arcs, cells = audit_paths(paths, graph, data)
    node_sections, levels, land, diagnostics = audit_sections(sections, nodes, arcs, data, paths)
    audit_mesh(sections, node_sections, arcs, diagnostics, data["spacing"])
    fine_cells = audit_fine(sections, nodes, arcs, node_sections, levels, land, data, paths["selected_leaf_ids"])
    summary = dict(land_edges=len(land), mesh_edges=len(sections["edge_sections"]),
                   rejected_edges=sum(bool(item["rejection_reasons"]) for item in diagnostics.values()),
                   fine_requested_cells=fine_cells, fine_refused_windows=sum(item["status"] == "refused" for item in sections["fine_requests"]))
    equal(sections["summary"], summary, "sections summary")
    equal(index["summary"], dict(primary_support_area_m2=graph["routing_forest"]["primary_component"]["area_m2"],
          basin_count=len(paths["selected_leaf_ids"]), node_count=len(nodes), arc_count=len(arcs), land_arc_count=len(land),
          section_count=len(node_sections), vertex_count=len(sections["mesh"]["vertices_xyz_m"]),
          triangle_count=len(sections["mesh"]["triangles"]), fine_request_count=len(sections["fine_requests"]), details=summary), "index summary")
    envelope(review, "td-watershed-geometry-review-v1")
    require(review["paths"] == paths and review["sections"] == sections, "review payload differs from geometry")
    sample_index = graph["main_route_support"]["saved_index_for_review"]
    leaf_lookup = {int(leaf): position for position, leaf in enumerate(topology["arrays"]["leaf_ids"])}
    sampled = ordinary["arrays"]["stage_m"][sample_index]
    wet_cells = [int(cell) for cell in cells if sampled[leaf_lookup[int(data["owner"][cell])]] > data["bed"][cell]]
    equal(review, dict(case_id="baseline", height_m=hierarchy["arrays"]["height_m"].tolist(),
          origin_m_xz=data["origin"], spacing_m=data["spacing"], primary_support_cell_ids=cells.tolist(),
          sampled_lake_wet_cell_ids=wet_cells, sampled_index=sample_index,
          sampled_time_s=sample_index * ordinary["metadata"]["timestep_s"],
          sampled_stage_by_leaf=[dict(leaf_id=leaf, stage_m=float(sampled[leaf_lookup[leaf]])) for leaf in paths["selected_leaf_ids"]],
          parametric_only=True, bed_rasterized=False, water_surface_meshed=False), "review sampled footprint")
    require([pin["path"] for pin in index["images"]] == ["watershed-overview.png", "channel-closeup.png"], "review image coverage")
    images = []
    for pin in index["images"]:
        image_path = pinned(pin, directory, seen, True)
        with image_path.open("rb") as stream:
            header = stream.read(24)
        require(len(header) == 24 and header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR", "PNG header")
        width, height = struct.unpack(">II", header[16:24])
        require(width > 0 and height > 0, "PNG dimensions")
        images.append(dict(path=pin["path"], size_px=[width, height]))
    resource = index["resource"]
    require(resource["max_rss_bytes"] == 1024**3 and type(resource["peak_rss_bytes"]) is int and
            0 < resource["peak_rss_bytes"] <= 1024**3 and resource["max_json_bytes"] == MAX_BYTES and
            type(resource["elapsed_s"]) in (int, float) and math.isfinite(resource["elapsed_s"]) and resource["elapsed_s"] >= 0, "recorded preparation resource budget")
    forest_faces = set(graph["routing_forest"]["main_path_face_ids"]) | {
        record["parent_face_id"] for record in graph["routing_forest"]["records"] if record["leaf_id"] in paths["selected_leaf_ids"]}
    return dict(status="passed", summary=summary, selected_valid_cells=len(cells),
                parent_audit_reused=index["parent_audit"], old_water_ledgers_recomputed=False,
                ordinary_only=True, strong_event_loaded=False, exchange_injection_count=len(data["injections"]),
                nonforest_injection_count=sum(item["face_id"] not in forest_faces for item in data["injections"]),
                candidate_shape_identity_sha256=sections["candidate_shape_identity_sha256"],
                images=images, image_visual_content_audited=False,
                preparation_resource_record_verified=True, resource_measurement_independently_reproduced=False)


def audit(directory, index_sha256, report_name="independent-audit.json"):
    directory = Path(directory).resolve(strict=True)
    require(directory.is_dir() and directory.is_relative_to(ROOT.resolve()), "audit directory outside workspace")
    require(isinstance(report_name, str) and Path(report_name).name == report_name and
            report_name not in ("", ".", "..", "index.json", "paths.json", "sections.json", "review.json") and
            report_name.endswith(".json"), "report must be a new JSON basename")
    destination = directory / report_name
    require(not destination.exists(), "refusing to overwrite audit report")
    seen = {Path(__file__).resolve(): file_sha256(Path(__file__))}
    report = dict(schema="td-watershed-geometry-independent-audit-v1", index_sha256=index_sha256,
        cold_read=True, solver_advanced=False, geometry_built=False, forest_generated=False,
        bed_changed=False, water_generated=False, hydraulic_ready=False, natural_outlet_verified=False,
        permanent_trunk_ready=False, publishable=False, old_water_ledgers_recomputed=False,
        scope="pinned baseline native paths, ordinary carriers, shared sections and mesh, refusals, fine requirements and review; no old water replay or hydraulic certification")
    mocks = {}
    try:
        with ExitStack() as guards:
            for target in FORBIDDEN:
                mocks[target] = guards.enter_context(patch(target, side_effect=AssertionError("cold audit forbids: " + target)))
            report.update(audit_saved(directory, index_sha256, seen))
            require(all(mock.call_count == 0 for mock in mocks.values()), "forbidden generator/solver invoked")
            for path, sha in seen.items():
                require(file_sha256(path) == sha, "input/code changed during audit: " + str(path))
    except Exception as error:
        report.update(status="diagnostic_failure", failure_type=type(error).__name__, failure_reason=str(error))
    report["forbidden_api_call_counts"] = {target: mock.call_count for target, mock in mocks.items()}
    report["zero_forbidden_calls"] = len(mocks) == len(FORBIDDEN) and all(mock.call_count == 0 for mock in mocks.values())
    report["audit_code_sha256"] = seen[Path(__file__).resolve()]
    report["verified_file_count"] = len(seen)
    publish_bytes(destination, json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--report-name", default="independent-audit.json")
    arguments = parser.parse_args()
    result = audit(arguments.directory, arguments.index_sha256, arguments.report_name)
    print(json.dumps({key: result.get(key) for key in ("status", "failure_reason", "verified_file_count", "zero_forbidden_calls")}, ensure_ascii=False))
    sys.exit(0 if result["status"] == "passed" else 1)
