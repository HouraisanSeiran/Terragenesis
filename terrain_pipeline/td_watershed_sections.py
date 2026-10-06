"""Ordinary-event parametric sections; no raster bed or solved channel water.

USGS PP252 (1953), doi:10.3133/pp252 informs the existing uncalibrated
NaturalNetworkRecipe. These candidates are not regional hydraulic fits.
"""

from collections import deque
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import publish_bytes
from terrain_pipeline.td_natural_river_network import (
    LEVELS, NaturalNetworkRecipe, _level_value, _width_depth)


SCHEMA = "td-watershed-sections-v1"
MAX_BYTES = 32 * 1024 * 1024
MAX_CELLS = 250_000
MAX_WINDOW_CELLS = 250_000
MAX_FINE_CELLS = 2_000_000
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable",
         "permanent_trunk_ready", "material_budget_verified", "new_bed_hydrology_verified",
         "flow_regime_certified", "junction_patch_ready")
ANCHORS = {"lake_entry", "spill", "engineering", "lake_terminal"}


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _shape_identity(record):
    fields = ("schema", "source_identity_sha256", "hierarchy_identity_sha256",
              "topology_identity_sha256", "ordinary_identity_sha256", "parameters",
              "selected_leaf_ids", "node_sections", "mesh", "edge_sections", "support_arcs",
              "reach_diagnostics", "fine_requests", "exchange_injections")
    return _digest({field: record[field] for field in fields})


def _finite_array(value, shape, name, nonnegative=False):
    array = np.asarray(value, dtype=float)
    if array.shape != shape or not np.isfinite(array).all():
        raise ValueError(f"invalid {name}")
    if nonnegative and np.any(array < 0):
        raise ValueError(f"negative {name}")
    return array


def _carriers(hierarchy, topology, ordinary):
    arrays = hierarchy["arrays"]
    height = np.asarray(arrays["height_m"])
    if height.ndim != 2 or not 0 < height.size <= MAX_CELLS:
        raise ValueError("source grid budget exceeded")
    spacing = float(hierarchy["metadata"]["spacing_m"])
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("invalid spacing")
    duration = float(ordinary["metadata"]["duration_s"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid ordinary duration")
    if topology.get("metadata", {}).get("hierarchy_identity_sha256", hierarchy["identity_sha256"]) != hierarchy["identity_sha256"]:
        raise ValueError("topology hierarchy mismatch")
    for parent, key in ((hierarchy, "hierarchy_identity_sha256"),
                        (topology, "topology_identity_sha256")):
        if ordinary["metadata"].get(key, parent["identity_sha256"]) != parent["identity_sha256"]:
            raise ValueError("ordinary parent mismatch")
    leaves = [int(value) for value in topology["arrays"]["leaf_ids"]]
    lookup = {leaf: index for index, leaf in enumerate(leaves)}
    if len(lookup) != len(leaves):
        raise ValueError("duplicate leaves")
    effective_area = _finite_array(topology["arrays"]["leaf_area_m2"], (len(leaves),), "leaf area", True)
    if np.any(effective_area <= 0):
        raise ValueError("empty effective basin")
    event = ordinary["arrays"]
    runoff = np.asarray(event["outflow_volume_m3"], dtype=float)
    if runoff.ndim != 2 or runoff.shape[1] != len(leaves) or not len(runoff):
        raise ValueError("invalid runoff shape")
    _finite_array(runoff, runoff.shape, "runoff", True)
    stages = np.asarray(event["stage_m"], dtype=float)
    if stages.ndim != 2 or stages.shape[1] != len(leaves) or not len(stages):
        raise ValueError("invalid stages")
    _finite_array(stages, stages.shape, "stages")
    owner = np.asarray(arrays["contribution_owner"]).ravel()
    valid = np.asarray(arrays["valid_mask"], dtype=bool).ravel()
    protected = np.asarray(arrays["protected_mask"], dtype=bool).ravel()
    receiver = np.asarray(arrays["receiver"]).ravel()
    if any(len(value) != height.size for value in (owner, valid, protected, receiver)):
        raise ValueError("source array shape mismatch")
    usable = valid & ~protected & np.isin(owner, leaves)
    if not np.isfinite(height.ravel()[usable]).all():
        raise ValueError("nonfinite usable heights")
    local_area = np.where(usable, spacing ** 2, 0.)
    local_q = np.zeros(height.size)
    incoming_q = np.zeros(height.size)
    for leaf, position in lookup.items():
        cells = usable & (owner == leaf)
        if not math.isclose(float(cells.sum()) * spacing ** 2, effective_area[position], rel_tol=1e-9, abs_tol=1e-7):
            raise ValueError("effective area differs from usable source cells")
        local_q[cells] = float(runoff[:, position].sum()) / duration / effective_area[position] * spacing ** 2
    faces = topology["faces"]
    forward = _finite_array(event["face_forward_m3"], (len(runoff), len(faces)), "forward", True)
    reverse = _finite_array(event["face_reverse_m3"], forward.shape, "reverse", True)
    seen = set()
    injections = []
    for position, face in enumerate(faces):
        if face["face_id"] in seen:
            raise ValueError("duplicate physical incoming face")
        seen.add(face["face_id"])
        signed = float((forward[:, position] - reverse[:, position]).sum())
        if signed == 0:
            continue
        receiver_leaf = int(face["leaf_ids"][1 if signed > 0 else 0])
        source_leaf = int(face["leaf_ids"][0 if signed > 0 else 1])
        cells = [int(cell) for cell in face["cell_ids"]]
        if len(cells) != 2 or any(not 0 <= cell < height.size for cell in cells):
            raise ValueError("invalid physical face")
        actual = np.asarray(arrays["face_cells"])[int(face["face_index"])].tolist()
        if cells != actual or sorted(int(owner[cell]) for cell in cells) != list(face["leaf_ids"]):
            raise ValueError("physical face ownership mismatch")
        target = next(cell for cell in cells if int(owner[cell]) == receiver_leaf)
        if not usable[target]:
            raise ValueError("incoming face not on usable receiver")
        incoming_q[target] += abs(signed) / duration
        injections.append({"face_id": face["face_id"], "source_leaf_id": source_leaf,
                           "receiver_leaf_id": receiver_leaf, "receiver_cell_id": target,
                           "net_volume_m3": abs(signed), "representative_q_m3_s": abs(signed) / duration,
                           "semantics": "actual_net_exchange_not_source_attribution"})
    indegree = np.zeros(height.size, dtype=np.int64)
    downstream = np.full(height.size, -1, dtype=np.int64)
    columns = height.shape[1]
    for cell in np.flatnonzero(usable):
        target = int(receiver[cell])
        if target == -1:
            continue
        if not 0 <= target < height.size or not usable[target] or owner[cell] != owner[target]:
            raise ValueError("receiver leaves usable contribution basin")
        row, column = divmod(int(cell), columns)
        target_row, target_column = divmod(target, columns)
        if abs(row - target_row) + abs(column - target_column) != 1:
            raise ValueError("non-D4 receiver")
        downstream[cell] = target
        indegree[target] += 1
    queue = deque(int(cell) for cell in np.flatnonzero(usable & (indegree == 0)))
    order = []
    while queue:
        cell = queue.popleft()
        order.append(cell)
        target = int(downstream[cell])
        if target >= 0:
            local_area[target] += local_area[cell]
            local_q[target] += local_q[cell]
            incoming_q[target] += incoming_q[cell]
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(order) != int(usable.sum()):
        raise ValueError("receiver cycle")
    return {"height": height, "spacing": spacing, "owner": owner, "usable": usable,
            "receiver": downstream, "area": local_area, "local_q": local_q,
            "incoming_q": incoming_q, "order": order, "lookup": lookup,
            "stage_max": stages.max(axis=0), "injections": injections, "duration": duration}


def _sample(context, hierarchy, x_m, z_m):
    origin = hierarchy["metadata"]["origin_m_xz"]
    column = (x_m - float(origin[0])) / context["spacing"]
    row = (z_m - float(origin[1])) / context["spacing"]
    rows, columns = context["height"].shape
    if not 0 <= row <= rows - 1 or not 0 <= column <= columns - 1:
        raise ValueError("outside_source_coverage")
    row0, column0 = math.floor(row), math.floor(column)
    row1, column1 = min(row0 + 1, rows - 1), min(column0 + 1, columns - 1)
    corners = [row0 * columns + column0, row0 * columns + column1,
               row1 * columns + column0, row1 * columns + column1]
    valid = hierarchy["arrays"]["valid_mask"].ravel()
    protected = hierarchy["arrays"]["protected_mask"].ravel()
    if any(not valid[cell] for cell in corners):
        raise ValueError("unknown_source_coverage")
    if any(protected[cell] for cell in corners):
        raise ValueError("protected_source_coverage")
    if any(int(context["owner"][cell]) not in context["selected_leaves"] for cell in corners):
        raise ValueError("outside_selected_component")
    fraction_row, fraction_column = row - row0, column - column0
    weights = [(1 - fraction_row) * (1 - fraction_column), (1 - fraction_row) * fraction_column,
               fraction_row * (1 - fraction_column), fraction_row * fraction_column]
    return float(sum(weight * context["height"].ravel()[cell] for weight, cell in zip(weights, corners)))


def _level(area, discharge, width, depth, recipe):
    areas = (recipe.minimum_area_m2, recipe.seasonal_area_m2, recipe.perennial_area_m2, recipe.mainstem_area_m2)
    flows = (recipe.minimum_q_m3_s * (1.2 - .4 * recipe.material_erodibility),
             recipe.seasonal_q_m3_s, recipe.perennial_q_m3_s, recipe.mainstem_q_m3_s)
    level = None
    for index in range(4):
        if (area >= areas[index] and discharge >= flows[index] and
                width >= _level_value(recipe, index, "min_width_m") and
                depth >= _level_value(recipe, index, "min_depth_m")):
            level = index
    return level


def _triangle_buckets(points, spacing):
    first_column = math.floor(min(point[0] for point in points) / spacing)
    last_column = math.floor(max(point[0] for point in points) / spacing)
    first_row = math.floor(min(point[2] for point in points) / spacing)
    last_row = math.floor(max(point[2] for point in points) / spacing)
    return [(column, row) for column in range(first_column, last_column + 1)
            for row in range(first_row, last_row + 1)]


def _triangle_overlap(first, second):
    for triangle in (first, second):
        for index in range(3):
            start, end = triangle[index], triangle[(index + 1) % 3]
            axis = [end[2] - start[2], start[0] - end[0]]
            length = math.hypot(*axis)
            if length < 1e-12:
                continue
            first_projection = [(point[0] * axis[0] + point[2] * axis[1]) / length for point in first]
            second_projection = [(point[0] * axis[0] + point[2] * axis[1]) / length for point in second]
            if min(max(first_projection), max(second_projection)) - max(min(first_projection), min(second_projection)) <= 1e-9:
                return False
    return True


def _register_triangles(vertices, triangles, incidence, buckets, spacing):
    staged_edges = {}
    staged_triangles = []
    staged_buckets = {}
    for triangle in triangles:
        points = [vertices[index] for index in triangle]
        signed_area = ((points[1][0] - points[0][0]) * (points[2][2] - points[0][2]) -
                       (points[1][2] - points[0][2]) * (points[2][0] - points[0][0])) / 2
        if signed_area <= 1e-9:
            return "nonpositive_projected_triangle_area"
        for first, second in zip(triangle, triangle[1:] + triangle[:1]):
            key = tuple(sorted((first, second)))
            directions = incidence.get(key, []) + staged_edges.get(key, [])
            if len(directions) >= 2:
                return "nonmanifold_mesh_edge"
            if directions and directions[0] != (second, first):
                return "inconsistent_mesh_edge_orientation"
            staged_edges.setdefault(key, []).append((first, second))
        keys = _triangle_buckets(points, spacing)
        nearby = {}
        for key in keys:
            for other in buckets.get(key, []) + staged_buckets.get(key, []):
                nearby[tuple(other)] = other
        for other in nearby.values():
            if _triangle_overlap(points, [vertices[index] for index in other]):
                return "overlapping_mesh_triangles"
        staged_triangles.append((triangle, keys))
        for key in keys:
            staged_buckets.setdefault(key, []).append(triangle)
    for key, directions in staged_edges.items():
        incidence.setdefault(key, []).extend(directions)
    for triangle, keys in staged_triangles:
        for key in keys:
            buckets.setdefault(key, []).append(triangle)
    return None


def _fine_request(identifier, points, width, depth, level, reasons, context, hierarchy, remaining):
    spacing = min(width / max(2., 2. * float("junction" in reasons or "spill" in reasons or "outlet" in reasons)),
                  _level_value(context["recipe"], level or 0, "required_spacing_m"))
    margin = width / 2 + depth * _level_value(context["recipe"], level or 0, "bank_slope_h_per_v")
    margin += _level_value(context["recipe"], level or 0, "protection_distance_m")
    bbox = [min(point[0] for point in points) - margin, min(point[2] for point in points) - margin,
            max(point[0] for point in points) + margin, max(point[2] for point in points) + margin]
    extent = [math.floor(bbox[0] / spacing), math.floor(bbox[1] / spacing),
              math.ceil(bbox[2] / spacing), math.ceil(bbox[3] / spacing)]
    bbox = [extent[0] * spacing, extent[1] * spacing, extent[2] * spacing, extent[3] * spacing]
    shape = [extent[3] - extent[1] + 1, extent[2] - extent[0] + 1]
    cells = shape[0] * shape[1]
    refusal = []
    origin = hierarchy["metadata"]["origin_m_xz"]
    rows, columns = context["height"].shape
    first_column = math.floor((bbox[0] - origin[0]) / context["spacing"])
    last_column = math.ceil((bbox[2] - origin[0]) / context["spacing"])
    first_row = math.floor((bbox[1] - origin[1]) / context["spacing"])
    last_row = math.ceil((bbox[3] - origin[1]) / context["spacing"])
    if first_column < 0 or first_row < 0 or last_column >= columns or last_row >= rows:
        refusal.append("outside_source_coverage")
    selection = np.s_[max(0, first_row):min(rows, last_row + 1), max(0, first_column):min(columns, last_column + 1)]
    arrays = hierarchy["arrays"]
    if not arrays["valid_mask"][selection].all():
        refusal.append("unknown_source_coverage")
    if arrays["protected_mask"][selection].any():
        refusal.append("protected_source_coverage")
    if not np.isin(arrays["contribution_owner"][selection], list(context["selected_leaves"])).all():
        refusal.append("outside_selected_component")
    if arrays["open_boundary_mask"][selection].any():
        refusal.append("engineering_open_boundary_contact")
    if cells > MAX_WINDOW_CELLS:
        refusal.append("window_cell_budget_exceeded")
    if cells > remaining:
        refusal.append("total_fine_cell_budget_exceeded")
    return {"request_id": identifier, "bbox_m_xz": bbox, "window_bbox_m_xz": bbox,
            "grid_extent": extent, "grid_shape": shape, "target_spacing_m": spacing,
            "width_m": width, "estimated_cells": cells, "estimated_bytes": cells * 32,
            "reasons": sorted(set(reasons)), "refusal_reasons": refusal,
            "status": "refused" if refusal else "requested", "generation_requested": False,
            "fine_dem_available": False, "source_spacing_m": context["spacing"],
            "semantics": "spatial_resolution_requirement_not_resampled_fine_DEM"}


def build_watershed_sections(paths, hierarchy, topology, ordinary, recipe=None):
    """Build shared bank/bed candidates and explicit, budgeted fine requirements."""
    recipe = NaturalNetworkRecipe() if recipe is None else recipe
    if not isinstance(recipe, NaturalNetworkRecipe):
        raise ValueError("NaturalNetworkRecipe required")
    context = _carriers(hierarchy, topology, ordinary)
    context["recipe"] = recipe
    context["selected_leaves"] = set(paths["selected_leaf_ids"])
    nodes = {node["node_id"]: node for node in paths["nodes"]}
    if len(nodes) != len(paths["nodes"]) or len(nodes) > MAX_CELLS or len(paths["arcs"]) > MAX_CELLS:
        raise ValueError("path node/arc budget or uniqueness failure")
    for key, expected in (("hierarchy_identity_sha256", hierarchy["identity_sha256"]),
                          ("ordinary_identity_sha256", ordinary["identity_sha256"])):
        if paths.get(key, expected) != expected:
            raise ValueError("path parent mismatch")
    origin = hierarchy["metadata"]["origin_m_xz"]
    columns = context["height"].shape[1]
    for identifier, node in nodes.items():
        cell = node["cell_id"]
        if type(cell) is not int or not 0 <= cell < context["height"].size or identifier != f"cell:{cell}":
            raise ValueError("invalid shared node")
        expected = [origin[0] + cell % columns * context["spacing"],
                    float(context["height"].ravel()[cell]), origin[1] + cell // columns * context["spacing"]]
        point = _finite_array(node["xyz_m"], (3,), "node xyz")
        if not np.allclose(point, expected, atol=1e-8, rtol=0) or int(context["owner"][cell]) != node["leaf_id"]:
            raise ValueError("node differs from native source")
        if not math.isclose(node["local_upstream_area_m2"], context["area"][cell], rel_tol=1e-9, abs_tol=1e-7):
            raise ValueError("node local receiver area mismatch")
    arcs = sorted(paths["arcs"], key=lambda arc: arc["arc_id"])
    if len({arc["arc_id"] for arc in arcs}) != len(arcs):
        raise ValueError("duplicate arc")
    land = []
    diagnostics = []
    support = []
    for arc in arcs:
        if arc["node_ids"] != [f"cell:{cell}" for cell in arc["cell_ids"]]:
            raise ValueError("arc nodes differ from cells")
        if any(identifier not in nodes for identifier in arc["node_ids"]):
            raise ValueError("arc refers to missing node")
        if arc["xyz_m"] != [nodes[identifier]["xyz_m"] for identifier in arc["node_ids"]]:
            raise ValueError("arc differs from original XYZ")
        if arc["kind"] != "land_channel":
            if arc["channel_candidate"]:
                raise ValueError("support arc cannot cut bed")
            support.append(deepcopy(arc))
            continue
        reasons = []
        cells = arc["cell_ids"]
        if len(cells) != 2:
            raise ValueError("land arc must be a two-node receiver edge")
        first, second = cells
        if context["receiver"][first] != second:
            reasons.append("not_actual_receiver_D4")
        leaf = arc["leaf_id"]
        if leaf not in context["lookup"] or any(context["owner"][cell] != leaf for cell in cells):
            reasons.append("land_leaf_mismatch")
        elif any(context["height"].ravel()[cell] <= context["stage_max"][context["lookup"][leaf]] for cell in cells):
            reasons.append("ordinary_lake_stage_contact")
        if not arc["channel_candidate"] or not context["usable"][cells].all():
            reasons.append("not_usable_land_candidate")
        diagnostic = {"arc_id": arc["arc_id"], "node_ids": list(arc["node_ids"]),
                      "kind": arc["kind"], "is_main_path": arc["is_main_path"],
                      "rejection_reasons": reasons, "status": "rejected" if reasons else "candidate",
                      "parametric_only": True, "bed_rasterized": False}
        diagnostics.append(diagnostic)
        if not reasons:
            land.append((arc, diagnostic))
    incident = {}
    donors = {}
    for arc, diagnostic in land:
        first, second = arc["node_ids"]
        incident.setdefault(first, []).append(arc)
        incident.setdefault(second, []).append(arc)
        donors.setdefault(second, set()).add(first)
    sections = {}
    for identifier in sorted(incident):
        node = nodes[identifier]
        cell = node["cell_id"]
        discharge = float(context["local_q"][cell] + context["incoming_q"][cell])
        target = int(context["receiver"][cell])
        slope = max(0., float((context["height"].ravel()[cell] - context["height"].ravel()[target]) / context["spacing"])) if target >= 0 else 0.
        width, depth = _width_depth(discharge, slope, recipe)
        level = _level(context["area"][cell], discharge, width, depth, recipe)
        evidence = []
        if level is None:
            evidence.append("area_or_ordinary_carrier_geometry_threshold_unmet")
        if level is not None and level >= 2:
            evidence.append("perennial_frequency_baseflow_and_duration_unmeasured")
        sections[identifier] = {"node_id": identifier, "cell_id": cell, "source_xyz_m": list(node["xyz_m"]),
            "bed_m": node["xyz_m"][1] - depth, "width_m": width, "depth_m": depth,
            "representative_q_m3_s": discharge, "local_runoff_q_m3_s": float(context["local_q"][cell]),
            "incoming_exchange_q_m3_s": float(context["incoming_q"][cell]),
            "local_upstream_area_m2": float(context["area"][cell]),
            "level": LEVELS[level] + "_proxy" if level is not None else "needs_evidence",
            "geometry_threshold_level": LEVELS[level] if level is not None else None,
            "needs_evidence": True, "evidence_reasons": evidence or ["uncalibrated_ordinary_event_carrier"],
            "anchor": bool(set(node["kinds"]) & ANCHORS), "junction": len(donors.get(identifier, ())) > 1,
            "cross_section_xyz_m": [], "rejection_reasons": [], "parametric_only": True,
            "bed_rasterized": False, "flow_regime_certified": False,
            "level_semantics": "ordinary_event_geometry_threshold_proxy_not_certified_flow_regime", "_level": level}
    for cell in context["order"]:
        identifier = f"cell:{cell}"
        target_id = f"cell:{int(context['receiver'][cell])}"
        if identifier not in sections or target_id not in sections:
            continue
        section, target = sections[identifier], sections[target_id]
        target["width_m"] = max(target["width_m"], section["width_m"])
        target["depth_m"] = max(target["depth_m"], section["depth_m"])
        target["representative_q_m3_s"] = max(target["representative_q_m3_s"], section["representative_q_m3_s"])
        target["bed_m"] = min(target["source_xyz_m"][1] - target["depth_m"],
                               section["bed_m"] - .0001 * context["spacing"])
    for identifier, section in sections.items():
        node = nodes[identifier]
        if section["anchor"]:
            section["bed_m"] = node["xyz_m"][1]
            section["depth_m"] = 0.
            section["rejection_reasons"].append("anchor_cut_conflict")
        if section["junction"] or len(incident[identifier]) >= 3:
            section["rejection_reasons"].append("needs_junction_patch")
        section["junction_patch_ready"] = False
        cut = node["xyz_m"][1] - section["bed_m"]
        section["required_cut_m"] = cut
        if cut > 4. + 1e-9:
            section["rejection_reasons"].append("four_metre_cut_budget_exceeded")
        outgoing = [arc for arc in incident[identifier] if arc["node_ids"][0] == identifier]
        reference = outgoing[0] if outgoing else incident[identifier][0]
        points = reference["xyz_m"]
        direction = np.asarray(points[1])[[0, 2]] - np.asarray(points[0])[[0, 2]]
        norm = float(np.linalg.norm(direction))
        normal = [-float(direction[1]) / norm, float(direction[0]) / norm]
        section["transverse_unit_xz"] = normal
        run = section["depth_m"] * _level_value(recipe, section["_level"] or 0, "bank_slope_h_per_v")
        offsets = [-section["width_m"] / 2 - run, -section["width_m"] / 2,
                   section["width_m"] / 2, section["width_m"] / 2 + run]
        try:
            for index, offset in enumerate(offsets):
                x_m = node["xyz_m"][0] + normal[0] * offset
                z_m = node["xyz_m"][2] + normal[1] * offset
                source_bank = _sample(context, hierarchy, x_m, z_m)
                if source_bank < section["bed_m"] - 1e-9:
                    raise ValueError("bank_below_candidate_bed")
                if source_bank - section["bed_m"] > 4. + 1e-9 and index in (1, 2):
                    raise ValueError("transverse_four_metre_cut_budget_exceeded")
                section["cross_section_xyz_m"].append([x_m, source_bank if index in (0, 3) else section["bed_m"], z_m])
        except ValueError as error:
            section["rejection_reasons"].append(str(error))
            section["cross_section_xyz_m"] = []
    for identifier, node in sorted(nodes.items()):
        if identifier in sections:
            continue
        cell = node["cell_id"]
        sections[identifier] = {"node_id": identifier, "cell_id": cell,
            "source_xyz_m": list(node["xyz_m"]), "bed_m": node["xyz_m"][1],
            "width_m": 0., "depth_m": 0., "required_cut_m": 0.,
            "representative_q_m3_s": float(context["local_q"][cell] + context["incoming_q"][cell]),
            "local_runoff_q_m3_s": float(context["local_q"][cell]),
            "incoming_exchange_q_m3_s": float(context["incoming_q"][cell]),
            "local_upstream_area_m2": float(context["area"][cell]),
            "level": "source_support_only", "geometry_threshold_level": None,
            "level_semantics": "unchanged_source_support_not_channel_geometry", "flow_regime_certified": False,
            "needs_evidence": True, "evidence_reasons": ["support_cannot_modify_bed"],
            "anchor": bool(set(node["kinds"]) & ANCHORS), "junction": False,
            "cross_section_xyz_m": [], "rejection_reasons": [],
            "parametric_only": True, "bed_rasterized": False, "_level": None}
    mesh = {"vertices_xyz_m": [], "triangles": [], "node_vertex_indices": {},
            "triangle_arc_ids": [], "parametric_only": True, "bed_rasterized": False,
            "junction_patch_ready": False, "edge_incidence_max": 0,
            "positive_projected_area": True, "nonoverlapping_projection": True}
    incidence, triangle_buckets = {}, {}
    edges = []
    for arc, diagnostic in land:
        first, second = (sections[identifier] for identifier in arc["node_ids"])
        reasons = diagnostic["rejection_reasons"]
        reasons.extend(sorted(set(first["rejection_reasons"] + second["rejection_reasons"])))
        if first["_level"] is None or second["_level"] is None:
            reasons.append("insufficient_ordinary_supply_or_area")
        if first["bed_m"] - second["bed_m"] < .0001 * context["spacing"] - 1e-9:
            reasons.append("candidate_bed_slope_failed")
        if not reasons:
            signs = []
            vertices = first["cross_section_xyz_m"] + second["cross_section_xyz_m"]
            for index in range(3):
                for triangle in ((index, index + 4, index + 1), (index + 1, index + 4, index + 5)):
                    points = [vertices[vertex] for vertex in triangle]
                    signed = ((points[1][0] - points[0][0]) * (points[2][2] - points[0][2]) -
                              (points[1][2] - points[0][2]) * (points[2][0] - points[0][0]))
                    signs.append(signed)
            if min(abs(value) for value in signs) < 1e-9 or min(signs) < 0 < max(signs):
                reasons.append("folded_or_degenerate_bank_geometry")
        diagnostic.update(status="rejected" if reasons else "geometry_candidate",
                          representative_q_m3_s=max(first["representative_q_m3_s"], second["representative_q_m3_s"]),
                          level=first["level"], needs_evidence=True, flow_regime_certified=False)
        if reasons:
            continue
        proposed_vertices = list(mesh["vertices_xyz_m"])
        proposed_indices = dict(mesh["node_vertex_indices"])
        for section in (first, second):
            identifier = section["node_id"]
            if identifier not in proposed_indices:
                start = len(proposed_vertices)
                proposed_indices[identifier] = list(range(start, start + 4))
                proposed_vertices.extend(deepcopy(section["cross_section_xyz_m"]))
        first_indices, second_indices = (proposed_indices[identifier] for identifier in arc["node_ids"])
        proposed_triangles = []
        for index in range(3):
            triangles = [[first_indices[index], second_indices[index], first_indices[index + 1]],
                         [first_indices[index + 1], second_indices[index], second_indices[index + 1]]]
            if signs[0] < 0:
                triangles = [triangle[::-1] for triangle in triangles]
            proposed_triangles.extend(triangles)
        problem = _register_triangles(proposed_vertices, proposed_triangles, incidence,
                                      triangle_buckets, context["spacing"])
        if problem:
            reasons.append(problem)
            diagnostic["status"] = "rejected"
            continue
        triangle_indices = list(range(len(mesh["triangles"]), len(mesh["triangles"]) + 6))
        mesh["vertices_xyz_m"] = proposed_vertices
        mesh["node_vertex_indices"] = proposed_indices
        mesh["triangles"].extend(proposed_triangles)
        mesh["triangle_arc_ids"].extend([arc["arc_id"]] * 6)
        edges.append({"arc_id": arc["arc_id"], "node_ids": list(arc["node_ids"]),
                      "cross_section_xyz_m": [deepcopy(first["cross_section_xyz_m"]), deepcopy(second["cross_section_xyz_m"])],
                      "triangle_indices": triangle_indices})
    mesh["edge_incidence_max"] = max((len(directions) for directions in incidence.values()), default=0)
    fine = []
    remaining = MAX_FINE_CELLS
    for arc, diagnostic in land:
        first, second = (sections[identifier] for identifier in arc["node_ids"])
        reasons = ["land_channel", "width_resolution"]
        if arc["is_main_path"]:
            reasons.append("mainline")
        if first["junction"] or second["junction"]:
            reasons.append("junction")
        request = _fine_request(arc["arc_id"], arc["xyz_m"], min(first["width_m"], second["width_m"]),
                                max(first["depth_m"], second["depth_m"]), first["_level"], reasons,
                                context, hierarchy, remaining)
        fine.append(request)
        if request["status"] == "requested":
            remaining -= request["estimated_cells"]
    for identifier, node in sorted(nodes.items()):
        kinds = set(node["kinds"])
        if not kinds & {"spill", "engineering", "lake_entry"}:
            continue
        discharge = float(context["local_q"][node["cell_id"]] + context["incoming_q"][node["cell_id"]])
        width, depth = _width_depth(discharge, 0., recipe)
        reasons = sorted(kinds & ANCHORS)
        if "engineering" in kinds:
            reasons.append("outlet")
        request = _fine_request(identifier, [node["xyz_m"]], width, depth, None, reasons,
                                context, hierarchy, remaining)
        fine.append(request)
        if request["status"] == "requested":
            remaining -= request["estimated_cells"]
    for arc in support:
        if not arc["is_main_path"]:
            continue
        for index in range(max(1, len(arc["xyz_m"]) - 1)):
            points = arc["xyz_m"][index:index + 2]
            cell = arc["cell_ids"][index]
            discharge = float(context["local_q"][cell] + context["incoming_q"][cell])
            width, depth = _width_depth(discharge, 0., recipe)
            reasons = ["mainline", "unchanged_source_support", "width_resolution"]
            if arc["kind"] == "cross_face":
                reasons.append("spill")
            if arc["kind"] == "engineering_outlet_support":
                reasons.append("outlet")
            request = _fine_request(f"{arc['arc_id']}:window:{index}", points, width, depth,
                                    None, reasons, context, hierarchy, remaining)
            request["parent_arc_id"] = arc["arc_id"]
            fine.append(request)
            if request["status"] == "requested":
                remaining -= request["estimated_cells"]
    priorities = ("outlet", "spill", "junction", "mainline")
    fine.sort(key=lambda request: (
        next((index for index, reason in enumerate(priorities) if reason in request["reasons"]), len(priorities)),
        request["request_id"]))
    remaining = MAX_FINE_CELLS
    for request in fine:
        refusal = [reason for reason in request["refusal_reasons"] if reason != "total_fine_cell_budget_exceeded"]
        if request["estimated_cells"] > remaining:
            refusal.append("total_fine_cell_budget_exceeded")
        request["refusal_reasons"] = refusal
        request["status"] = "refused" if refusal else "requested"
        if not refusal:
            remaining -= request["estimated_cells"]
    for section in sections.values():
        del section["_level"]
    result = {"schema": SCHEMA,
              "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
              "hierarchy_identity_sha256": hierarchy["identity_sha256"], "topology_identity_sha256": topology["identity_sha256"],
              "ordinary_identity_sha256": ordinary["identity_sha256"],
              "composite_parent_identity": {"paths": paths.get("identity_sha256"), "graph": paths.get("graph_identity_sha256")},
              "selected_leaf_ids": list(paths["selected_leaf_ids"]),
              "parameters": asdict(recipe), "node_sections": list(sections.values()), "mesh": mesh,
              "edge_sections": edges, "support_arcs": support, "fine_requests": fine,
              "reach_diagnostics": diagnostics, "exchange_injections": context["injections"],
              "summary": {"land_edges": len(land), "mesh_edges": len(edges), "rejected_edges": sum(bool(item["rejection_reasons"]) for item in diagnostics),
                          "fine_requested_cells": MAX_FINE_CELLS - remaining,
                          "fine_refused_windows": sum(item["status"] == "refused" for item in fine)},
              "budgets": {"max_json_bytes": MAX_BYTES, "max_window_cells": MAX_WINDOW_CELLS, "max_fine_cells": MAX_FINE_CELLS},
              "coordinate_system": "model_xyz_m", "parametric_only": True, "bed_rasterized": False,
              "bed_changed": False, "source": {"bed_changed": False}, "candidate_changed": "geometry_only",
              "supply_semantics": "ordinary_event_mean_carrier_proxy_not_instantaneous_Q_or_multiyear_flow; uncalibrated_uniform_basin_spatial_allocation; actual_net_exchange_not_source_attribution; no_water_created",
              "ordinary_duration_s": context["duration"],
              "source_spacing_m": context["spacing"],
              "exchange_scope": "all_topology_faces_including_nonforest_inputs; each_positive_cumulative_directional_net_once_on_receiver_then_to_sink; engineering_export_not_attributed_to_forest",
              "level_semantics": "existing_four_area_Q_width_depth_thresholds_only; perennial_supply_unverified; no_permanent_mainstem_claim",
              "bank_sampling": "original_coarse_bilinear_height_for_parametric_bank_geometry_not_fine_DEM",
              "continuity_semantics": "source_centerline_support_continuity_is_not_candidate_channel_bed_continuity; accepted_mesh_only_on_nonrejected_land_edges; lake_interfaces_depth_zero_with_incident_cut_edges_refused; junction_strips_omitted_pending_patch",
              "calibration": "uncalibrated prototype; USGS PP252 (1953), doi:10.3133/pp252; existing NaturalNetworkRecipe unchanged",
              **{flag: False for flag in FLAGS}}
    result["candidate_shape_identity_sha256"] = _shape_identity(result)
    result["identity_sha256"] = _digest(result)
    validate_watershed_sections(result)
    return result


def validate_watershed_sections(record):
    """Validate finite JSON, diagnostic flags, shared mesh and resource budgets."""
    payload = _encoded(record)
    if len(payload) > MAX_BYTES or record.get("schema") != SCHEMA:
        raise ValueError("sections schema or JSON byte budget failure")
    if any(record.get(flag) is not False for flag in FLAGS):
        raise ValueError("sections cannot grant certification")
    if (record.get("parametric_only") is not True or record.get("bed_rasterized") is not False or
            record.get("bed_changed") is not False or record.get("source", {}).get("bed_changed") is not False or
            record.get("candidate_changed") != "geometry_only"):
        raise ValueError("invalid geometry-only status")
    unsigned = {key: value for key, value in record.items() if key != "identity_sha256"}
    if record.get("identity_sha256") != _digest(unsigned):
        raise ValueError("sections identity mismatch")
    if record.get("candidate_shape_identity_sha256") != _shape_identity(record):
        raise ValueError("candidate output shape identity mismatch")
    sections = {section["node_id"]: section for section in record["node_sections"]}
    if len(sections) != len(record["node_sections"]) or len(sections) > MAX_CELLS:
        raise ValueError("duplicate or excessive sections")
    for section in sections.values():
        if section["flow_regime_certified"] is not False or section["parametric_only"] is not True or section["bed_rasterized"] is not False:
            raise ValueError("section cannot grant certification")
        if any(section[name] < 0 for name in ("width_m", "depth_m", "representative_q_m3_s", "required_cut_m")):
            raise ValueError("negative section geometry or supply")
        if section["anchor"] and (section["depth_m"] != 0 or section["bed_m"] != section["source_xyz_m"][1]):
            raise ValueError("anchor differs from unchanged source bed")
        points = section["cross_section_xyz_m"]
        if points:
            _finite_array(points, (4, 3), "cross section")
            if points[1][1] != section["bed_m"] or points[2][1] != section["bed_m"]:
                raise ValueError("cross section differs from shared bed")
    mesh = record["mesh"]
    if mesh["junction_patch_ready"] is not False or mesh["parametric_only"] is not True or mesh["bed_rasterized"] is not False:
        raise ValueError("invalid candidate mesh flags")
    vertices = _finite_array(mesh["vertices_xyz_m"], (len(mesh["vertices_xyz_m"]), 3), "mesh vertices") if mesh["vertices_xyz_m"] else np.empty((0, 3))
    for identifier, indices in mesh["node_vertex_indices"].items():
        if identifier not in sections or len(indices) != 4 or any(type(index) is not int or not 0 <= index < len(vertices) for index in indices):
            raise ValueError("invalid shared mesh node")
        if vertices[indices].tolist() != sections[identifier]["cross_section_xyz_m"]:
            raise ValueError("mesh differs from shared node section")
    if len(mesh["triangles"]) != len(mesh["triangle_arc_ids"]):
        raise ValueError("triangle provenance mismatch")
    for triangle in mesh["triangles"]:
        if len(triangle) != 3 or len(set(triangle)) != 3 or any(type(index) is not int or not 0 <= index < len(vertices) for index in triangle):
            raise ValueError("invalid triangle")
    incidence, buckets = {}, {}
    problem = _register_triangles(mesh["vertices_xyz_m"], mesh["triangles"], incidence,
                                  buckets, record["source_spacing_m"])
    if problem:
        raise ValueError(problem)
    if mesh["edge_incidence_max"] != max((len(directions) for directions in incidence.values()), default=0):
        raise ValueError("mesh incidence summary mismatch")
    diagnostics = {item["arc_id"]: item for item in record["reach_diagnostics"]}
    for edge in record["edge_sections"]:
        if edge["arc_id"] not in diagnostics or diagnostics[edge["arc_id"]]["rejection_reasons"]:
            raise ValueError("rejected reach cannot enter saved mesh")
        if edge["cross_section_xyz_m"] != [sections[identifier]["cross_section_xyz_m"] for identifier in edge["node_ids"]]:
            raise ValueError("edge differs from shared node sections")
        for index in edge["triangle_indices"]:
            if not 0 <= index < len(mesh["triangles"]) or mesh["triangle_arc_ids"][index] != edge["arc_id"]:
                raise ValueError("edge triangle provenance mismatch")
    requested = 0
    for request in record["fine_requests"]:
        spacing = request["target_spacing_m"]
        if spacing <= 0 or spacing > request["width_m"] / 2 + 1e-12:
            raise ValueError("fine spacing must resolve width")
        extent = request["grid_extent"]
        if len(extent) != 4 or any(type(value) is not int for value in extent):
            raise ValueError("invalid fine extent")
        shape = [extent[3] - extent[1] + 1, extent[2] - extent[0] + 1]
        cells = shape[0] * shape[1]
        if min(shape) <= 0 or shape != request["grid_shape"] or cells != request["estimated_cells"] or cells * 32 != request["estimated_bytes"]:
            raise ValueError("fine budget estimate mismatch")
        if request["fine_dem_available"] is not False or request["generation_requested"] is not False:
            raise ValueError("fine requests cannot claim generated DEM")
        if request["status"] == "requested":
            if request["refusal_reasons"] or cells > MAX_WINDOW_CELLS:
                raise ValueError("invalid accepted fine budget")
            requested += cells
        elif request["status"] != "refused" or not request["refusal_reasons"]:
            raise ValueError("invalid fine refusal")
    if requested > MAX_FINE_CELLS or requested != record["summary"]["fine_requested_cells"]:
        raise ValueError("fine total budget mismatch")
    return record


def save_watershed_sections(record, path):
    validate_watershed_sections(record)
    publish_bytes(Path(path), _encoded(record))
    return Path(path)


def load_watershed_sections(path, *, expected_sha256=None, expected_identity=None):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("sections JSON byte budget exceeded")
    payload = path.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("sections file hash mismatch")
    record = json.loads(payload)
    validate_watershed_sections(record)
    if expected_identity is not None and record["identity_sha256"] != expected_identity:
        raise ValueError("sections expected identity mismatch")
    return record
