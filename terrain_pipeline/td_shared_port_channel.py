"""Versioned shared-midpoint channels; display geometry, not fine or hydraulics."""

from collections import defaultdict, deque
from copy import deepcopy
import math

import numpy as np

from terrain_pipeline import td_source_conforming_banks as geometry
from terrain_pipeline import td_source_conforming_banks_v3 as fans
from terrain_pipeline import td_ported_junction as junction
from terrain_pipeline.td_ported_network_composition import match_ports, _contact, check_memory

SCHEMA = "td-shared-port-channel-v1"
MAX_NODES = 128
MAX_NODES_HARD = 256
MAX_FACES = 20000
MAX_BYTES = 64 * 1024**2
MAX_RSS = 1024**3
BANK_SLOPE_H_PER_V = 2.
PARAMETERS = {"max_cut_m": 4., "conflict_tolerance_m": 1e-9,
    "bank_slope_h_per_v": BANK_SLOPE_H_PER_V}
POLICY = {"schema": SCHEMA,
    "metrics": "unchanged_upstream_saved_node_section_width_depth_q",
    "offsets": "[-width/2-depth*2,-width/2,width/2,width/2+depth*2]",
    "bank_slope_h_per_v": 2., "cuts": "[0,upstream_depth,upstream_depth,0]",
    "midpoint": "one_canonical_actual_arc_midpoint_with_flow_normal_direction",
    "source": "original_native_bilinear_minus_nonnegative_affine_cut_fans",
    "center": "unchanged_saved_node_depth_not_legacy_absolute_floor",
    "node_geometry": "degree1_terminal_strip_degree2_3_4_complete_directional_inner_port_ring_with_zero_cut_exterior_gap_controls",
    "turn_controls": "actual_polar_gap_greater_than_180deg_insert_zero_cut_bank_at_gap_bisector_radius_max_adjacent_radius",
    "inset": "min(0.4*half_arc_length,max(1m,1.5*outer_bank_offset))",
    "terminal": "source_relative_saved_node_metrics_with_original_terminal_and_clipping_evidence",
    "wet": "original_source_gates_and_conservative_whole_native_patch_wet_guard",
    "selection": "largest_original_land_component_then_safety_clipping_longest_directed_chain_and_connected_branches",
    "acceptance": "new_derived_geometry_never_inherit_06_acceptance_or_delete_parent_reasons",
    "replacement": "new_mesh_only_original06_is_separate_context_no_fine_transaction",
    "connectivity": "complete_three_actual_reverse_boundary_edges_and_whole_native_source_depth_coefficients",
    "max_cut_m": 4., "slope": "diagnostic_only_no_hydraulic_acceptance"}
POLICY_IDENTITY_SHA256 = geometry._record_identity(POLICY)
FLAGS = ("fine_generated", "material_budget_verified", "hydraulic_ready", "hydraulic_solved",
    "full_network_verified", "natural_outlet_certified", "bed_changed")


def seal(record):
    record.pop("identity_sha256", None)
    return geometry._seal(record)


def _maps(paths, sections):
    return ({item["node_id"]: item for item in paths["nodes"]},
        {item["arc_id"]: item for item in paths["arcs"] if item["kind"] == "land_channel"},
        {item["node_id"]: (index, item) for index, item in enumerate(sections["node_sections"])})


def _check_parents(hierarchy, paths, sections):
    for parent in (paths, sections):
        if (parent["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]
                or parent["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]):
            raise ValueError("source and hierarchy parent identity mismatch")
    if paths["ordinary_identity_sha256"] != sections["ordinary_identity_sha256"]:
        raise ValueError("ordinary path and section parent mismatch")


def _components(node_ids, arc_records):
    neighbors = {node_id: set() for node_id in node_ids}
    for arc in arc_records:
        first, second = arc["node_ids"]
        neighbors[first].add(second)
        neighbors[second].add(first)
    result, visited = [], set()
    for root in sorted(neighbors):
        if root in visited:
            continue
        queue, members = [root], []
        visited.add(root)
        while queue:
            current = queue.pop()
            members.append(current)
            for neighbor in sorted(neighbors[current]):
                if neighbor not in visited:
                    queue.append(neighbor)
                    visited.add(neighbor)
        result.append(sorted(members))
    return sorted(result, key=lambda members: (-len(members), members[0]))


def _length(arc, nodes):
    first, second = [np.asarray(nodes[node_id]["xyz_m"])[[0, 2]] for node_id in arc["node_ids"]]
    return float(np.linalg.norm(second - first))


def longest_chain(node_ids, arc_records, nodes):
    outgoing = defaultdict(list)
    indegree = dict.fromkeys(node_ids, 0)
    for arc in arc_records:
        first, second = arc["node_ids"]
        outgoing[first].append(arc)
        indegree[second] += 1
    queue = deque(sorted(node_id for node_id, degree in indegree.items() if degree == 0))
    distance = dict.fromkeys(node_ids, 0.)
    predecessor, processed = {}, set()
    while queue:
        current = queue.popleft()
        processed.add(current)
        for arc in sorted(outgoing[current], key=lambda item: item["arc_id"]):
            second = arc["node_ids"][1]
            proposed = distance[current] + _length(arc, nodes)
            if proposed > distance[second]:
                distance[second] = proposed
                predecessor[second] = (current, arc["arc_id"])
            indegree[second] -= 1
            if indegree[second] == 0:
                queue.append(second)
    cycles = sorted(set(node_ids) - processed)
    if cycles:
        return {"node_ids": [], "arc_ids": [], "plan_length_m": None, "cycle_node_ids": cycles}
    if not node_ids:
        return {"node_ids": [], "arc_ids": [], "plan_length_m": 0., "cycle_node_ids": []}
    endpoint = max(sorted(node_ids), key=lambda node_id: distance[node_id])
    chain_nodes, chain_arcs = [endpoint], []
    while chain_nodes[-1] in predecessor:
        first, arc_id = predecessor[chain_nodes[-1]]
        chain_nodes.append(first)
        chain_arcs.append(arc_id)
    chain_nodes.reverse()
    chain_arcs.reverse()
    return {"node_ids": chain_nodes, "arc_ids": chain_arcs, "plan_length_m": distance[endpoint],
        "source_xyz_m": [nodes[node_id]["xyz_m"] for node_id in chain_nodes], "cycle_node_ids": []}


def _safety(node, section, context):
    reasons = set()
    if section is None:
        return ["missing_saved_node_section"], None
    if section.get("anchor") or any("lake" in kind or "anchor" in kind for kind in node.get("kinds", [])):
        reasons.add("original_anchor_or_lake")
    reasons.update("original_safety:" + reason for reason in section.get("rejection_reasons", [])
        if any(word in reason for word in ("unknown", "protected", "anchor", "nonfinite")))
    depth = section.get("depth_m")
    width = section.get("width_m")
    if not isinstance(depth, (int, float)) or not math.isfinite(depth) or not 0. < depth <= 4.:
        reasons.add("invalid_saved_node_depth")
    if not isinstance(width, (int, float)) or not math.isfinite(width) or width <= 0.:
        reasons.add("invalid_saved_node_width")
    sample = geometry._source_sample(context, node["xyz_m"][0], node["xyz_m"][2])
    reasons.update(sample["rejection_reasons"])
    return sorted(reasons), sample


def select_fragment(hierarchy, paths, sections, *, wet_protection, max_nodes=MAX_NODES):
    if type(max_nodes) is not int or not 2 <= max_nodes <= MAX_NODES_HARD:
        raise ValueError("max_nodes must be an integer from 2 to 256")
    _check_parents(hierarchy, paths, sections)
    nodes, arcs, profiles = _maps(paths, sections)
    context = geometry._context(hierarchy, sections["selected_leaf_ids"], wet_protection)
    original_nodes = sorted({node_id for arc in arcs.values() for node_id in arc["node_ids"]})
    components = _components(original_nodes, arcs.values())
    mother = set(components[0]) if components else set()
    clipping, allowed = [], set()
    for node_id in sorted(mother):
        section = profiles.get(node_id, (None, None))[1]
        reasons, sample = _safety(nodes[node_id], section, context)
        if reasons:
            clipping.append({"node_id": node_id, "rejection_reasons": reasons,
                "parent_section_index": profiles.get(node_id, (None,))[0],
                "parent_rejection_reasons": [] if section is None else section.get("rejection_reasons", []),
                "source_sample": sample, "source_xyz_m": nodes[node_id]["xyz_m"]})
        else:
            allowed.add(node_id)
    safe_arcs = [arc for arc in arcs.values() if set(arc["node_ids"]) <= allowed]
    safe_components = _components(allowed, safe_arcs)
    choices = []
    for component in safe_components:
        component_set = set(component)
        members = [arc for arc in safe_arcs if set(arc["node_ids"]) <= component_set]
        chain = longest_chain(component, members, nodes)
        degree = defaultdict(int)
        for arc in members:
            for node_id in arc["node_ids"]:
                degree[node_id] += 1
        choices.append((chain, component, members, degree))
    choices.sort(key=lambda item: (-(item[0]["plan_length_m"] or 0.), -len(item[1]), item[1][0]))
    chain, available, member_arcs, degree = choices[0] if choices else (
        {"node_ids": [], "arc_ids": [], "plan_length_m": 0.}, [], [], {})
    trunk = chain["node_ids"]
    has_branch = any(value >= 3 for value in degree.values())
    trunk_budget = max_nodes - min(16, max_nodes // 4) if has_branch and len(trunk) >= max_nodes else max_nodes
    trunk_window = trunk[:trunk_budget]
    if len(trunk) > trunk_budget:
        windows = [trunk[index:index + trunk_budget] for index in range(len(trunk) - trunk_budget + 1)]
        trunk_window = max(windows, key=lambda window: (sum(degree.get(node_id, 0) >= 3 for node_id in window),
            math.fsum(profiles[node_id][1].get("representative_q_m3_s", 0.) for node_id in window)))
    selected = set(trunk_window)
    while len(selected) < max_nodes:
        frontier = []
        for arc in member_arcs:
            first, second = arc["node_ids"]
            if (first in selected) != (second in selected):
                outside = second if first in selected else first
                flow = profiles[first][1].get("representative_q_m3_s", 0.)
                frontier.append((-float(flow), arc["arc_id"], outside))
        if not frontier:
            break
        selected.add(min(frontier)[2])
    selected_arcs = sorted(arc["arc_id"] for arc in member_arcs if set(arc["node_ids"]) <= selected)
    cut_arcs = []
    for arc in arcs.values():
        if set(arc["node_ids"]) & selected and arc["arc_id"] not in selected_arcs:
            reason = "safety_clip" if not set(arc["node_ids"]) <= allowed else "node_budget_boundary"
            cut_arcs.append({"arc_id": arc["arc_id"], "node_ids": arc["node_ids"], "reason": reason})
    graph = seal({"schema": "td-shared-port-land-graph-v1", "parents": {
        "paths": paths["identity_sha256"], "ordinary": paths["ordinary_identity_sha256"]},
        "nodes": [nodes[node_id] for node_id in original_nodes], "arcs": list(arcs.values()),
        "original_land_arc_count": len(arcs), "components": components,
        "largest_component_node_ids": sorted(mother)})
    selection = seal({"schema": "td-shared-port-selection-v1", "policy_identity_sha256": POLICY_IDENTITY_SHA256,
        "graph_identity_sha256": graph["identity_sha256"], "mother_component_node_ids": sorted(mother),
        "safety_clipping": clipping, "safe_component_node_ids": available, "longest_selection_chain": chain,
        "selected_node_ids": sorted(selected), "selected_arc_ids": selected_arcs,
        "budget_clipped_node_ids": sorted(set(available) - selected), "boundary_arc_clipping": cut_arcs,
        "max_nodes": max_nodes, "selection_not_geometry_verified": True,
        "selected_branch_node_ids": sorted(node_id for node_id in selected if sum(
            node_id in arcs[arc_id]["node_ids"] for arc_id in selected_arcs) >= 3)})
    return graph, selection


def _native_parts(start, end, context):
    start, end = np.asarray(start, float), np.asarray(end, float)
    delta = end - start
    length = float(np.linalg.norm(delta))
    if length <= 1e-8:
        raise ValueError("degenerate_edge")
    knots = [0., 1.]
    for axis in range(2):
        if abs(delta[axis]) <= 1e-12:
            continue
        low, high = sorted([start[axis], end[axis]])
        first = math.ceil((low - context["origin"][axis]) / context["spacing"])
        last = math.floor((high - context["origin"][axis]) / context["spacing"])
        if last - first > 1024:
            raise MemoryError("edge native knot budget exceeded")
        for index in range(first, last + 1):
            parameter = (context["origin"][axis] + index * context["spacing"] - start[axis]) / delta[axis]
            if 1e-8 / length < parameter < 1. - 1e-8 / length:
                knots.append(float(parameter))
    ordered = []
    for parameter in sorted(knots):
        if not ordered or (parameter - ordered[-1]) * length > 1e-8:
            ordered.append(parameter)
    return [(low, high, start + delta * low, start + delta * high) for low, high in zip(ordered, ordered[1:])]


def _patch_wet(context, patch):
    return bool(set(patch["native_cell_ids"]) & context["covered_native_cells"]) or any(
        context["height"].ravel()[cell] < context["stage_by_leaf"].get(
            int(context["arrays"]["contribution_owner"].ravel()[cell]), -math.inf)
        for cell in patch["native_cell_ids"])


def _cut_at(first, second, parameter):
    if parameter == 0.:
        return first
    if parameter == 1.:
        return second
    return first + (second - first) * parameter


def _profile(center, flow, section, context):
    width, depth = float(section["width_m"]), float(section["depth_m"])
    if not math.isfinite(width) or width <= 0. or not math.isfinite(depth) or not 0. < depth <= 4.:
        raise ValueError("invalid_saved_profile_metrics")
    normal = np.array([-flow[1], flow[0]])
    run = depth * BANK_SLOPE_H_PER_V
    offsets, depths = [-width / 2. - run, -width / 2., width / 2., width / 2. + run], [0., depth, depth, 0.]
    points, samples, reasons = [], [], set()
    for offset, cut in zip(offsets, depths):
        location = center + normal * offset
        sample = geometry._source_sample(context, *map(float, location))
        samples.append(sample)
        reasons.update(sample["rejection_reasons"])
        if sample["height_m"] is None:
            reasons.add("profile_source_unknown")
        if cut > 0. and sample["wet_source_support"]:
            reasons.add("profile_wet_cut_refused")
        points.append([float(location[0]), None if sample["height_m"] is None else sample["height_m"] - cut,
            float(location[1])])
    segments = []
    if not reasons:
        for number in range(3):
            start, end = np.asarray(points[number:number + 2])[:, [0, 2]]
            pieces = []
            for low, high, first, second in _native_parts(start, end, context):
                native = geometry.source_segment_polynomial(context, first, second)
                cut_first = _cut_at(depths[number], depths[number + 1], low)
                cut_second = _cut_at(depths[number], depths[number + 1], high)
                gate = geometry._source_sample(context, *map(float, (first + second) / 2.))
                reasons.update(gate["rejection_reasons"])
                if max(cut_first, cut_second) > 0. and _patch_wet(context, native):
                    reasons.add("profile_native_patch_wet_cut_refused")
                pieces.append({"interval_t01": [low, high], "start_xz_m": first.tolist(), "end_xz_m": second.tolist(),
                    "source": native, "depth_coefficients_m_t01": [cut_first, cut_second - cut_first]})
            segments.append({"profile_segment_index": number, "points_xyz_m": points[number:number + 2], "native_pieces": pieces})
    return {"profile_xyz_m": points, "cut_depths_m": depths, "transverse_offsets_m": offsets,
        "width_m": width, "depth_m": depth, "bank_run_m": run,
        "bank_slope_h_per_v": 2., "source_samples": samples, "profile_segments": segments,
        "status": "refused" if reasons else "candidate", "rejection_reasons": sorted(reasons)}


def build_midpoint_port(hierarchy, paths, sections, *, arc_id, wet_protection, input_pins=None):
    _check_parents(hierarchy, paths, sections)
    nodes, arcs, profiles = _maps(paths, sections)
    arc = arcs[arc_id]
    context = geometry._context(hierarchy, sections["selected_leaf_ids"], wet_protection)
    first, second = [np.asarray(nodes[node_id]["xyz_m"])[[0, 2]] for node_id in arc["node_ids"]]
    length = float(np.linalg.norm(second - first))
    if length <= 1e-8:
        raise ValueError("zero_length_actual_arc")
    flow, center = (second - first) / length, (first + second) / 2.
    upstream_index, section = profiles[arc["node_ids"][0]]
    reasons = set()
    flow_value = section.get("representative_q_m3_s")
    if not isinstance(flow_value, (int, float)) or not math.isfinite(flow_value) or flow_value < 0.:
        reasons.add("invalid_saved_upstream_q")
    for node_id in arc["node_ids"]:
        safety, sample = _safety(nodes[node_id], profiles.get(node_id, (None, None))[1], context)
        reasons.update(safety)
    profile = {}
    try:
        profile = _profile(center, flow, section, context)
        reasons.update(profile["rejection_reasons"])
    except ValueError as error:
        reasons.add(str(error))
    return seal({"schema": "td-shared-midpoint-port-v1", "policy_identity_sha256": POLICY_IDENTITY_SHA256,
        "inputs": dict(input_pins or {}), "parents": {"paths": paths["identity_sha256"], "sections": sections["identity_sha256"],
            "hierarchy": hierarchy["identity_sha256"], "source": hierarchy["metadata"]["source_identity_sha256"]},
        "arc_id": arc_id, "node_ids": arc["node_ids"], "source_arc_xyz_m": [nodes[node_id]["xyz_m"] for node_id in arc["node_ids"]],
        "midpoint_xz_m": center.tolist(), "flow_unit_xz": flow.tolist(), "length_m": length,
        "upstream_section_index": upstream_index, "upstream_parent_section": deepcopy(section),
        "representative_q_m3_s": section.get("representative_q_m3_s"), "profile": profile,
        "status": "refused" if reasons else "candidate", "rejection_reasons": sorted(reasons),
        "old_absolute_profile_acceptance_inherited": False, **{flag: False for flag in FLAGS}})


def _prove_mesh(record, context):
    mesh = record["geometry"]
    incidence = defaultdict(list)
    reasons = set()
    profile_edges = {}
    for arm in record["arms"]:
        for number, (first, second) in enumerate(zip(arm["midpoint_vertex_ids"], arm["midpoint_vertex_ids"][1:])):
            profile_edges[tuple(sorted((first, second)))] = {"kind": "shared_midpoint_open_geometric_port",
                "arc_id": arm["arc_id"], "midpoint_port_identity_sha256": arm["midpoint_port_identity_sha256"],
                "profile_segment_index": number, "hydraulic_boundary_claimed": False}
    terminal_ids = mesh.get("terminal_vertex_ids", [])
    for number, (first, second) in enumerate(zip(terminal_ids, terminal_ids[1:])):
        profile_edges[tuple(sorted((first, second)))] = {"kind": "source_relative_terminal_open_section",
            "profile_segment_index": number, "terminal_evidence": record["terminal_evidence"], "hydraulic_boundary_claimed": False}
    triangles = []
    for number, indices in enumerate(mesh["triangles"]):
        face = {"triangle_id": "shared:" + record["node_id"] + ":" + str(number),
            "vertices_xyz_m": [mesh["vertices_xyz_m"][index] for index in indices], "vertex_ids": indices,
            "replacement_role": mesh["triangle_roles"][number]}
        triangles.append(face)
        for edge_index in range(3):
            first, second = indices[edge_index], indices[(edge_index + 1) % 3]
            incidence[tuple(sorted((first, second)))].append({"triangle_id": face["triangle_id"],
                "triangle_index": number, "edge_index": edge_index,
                "points_xyz_m": [mesh["vertices_xyz_m"][first], mesh["vertices_xyz_m"][second]]})
    proofs = []
    registry = defaultdict(list)
    for key, sides in sorted(incidence.items()):
        if len(sides) > 2 or len(sides) == 2 and sides[0]["points_xyz_m"] != sides[1]["points_xyz_m"][::-1]:
            reasons.add("nonmanifold_or_wrong_direction_internal_edge")
        first_id, second_id = key
        pair = [mesh["vertices_xyz_m"][first_id], mesh["vertices_xyz_m"][second_id]]
        cuts = [mesh["vertex_depths_m"][first_id], mesh["vertex_depths_m"][second_id]]
        boundary = profile_edges.get(key)
        if len(sides) == 1 and boundary is None and max(cuts) > 0.:
            reasons.add("unbound_nonzero_cut_boundary")
        for low, high, first, second in _native_parts(np.asarray(pair[0])[[0, 2]], np.asarray(pair[1])[[0, 2]], context):
            depths = [_cut_at(cuts[0], cuts[1], parameter) for parameter in (low, high)]
            source_samples = [geometry._source_sample(context, *map(float, point)) for point in (first, second)]
            local_reasons = set(reason for sample in source_samples for reason in sample["rejection_reasons"])
            if any(depth < 0. or depth > 4. or not math.isfinite(depth) for depth in depths):
                local_reasons.add("strict_native_edge_cut_refused")
            native = geometry.source_segment_polynomial(context, first, second)
            if max(depths) > 0. and _patch_wet(context, native):
                local_reasons.add("edge_native_patch_wet_cut_refused")
            for point, depth in zip((first, second), depths):
                bucket = fans._bucket(point)
                for horizontal in (-1, 0, 1):
                    for vertical in (-1, 0, 1):
                        for prior, value in registry[(bucket[0] + horizontal, bucket[1] + vertical)]:
                            if np.max(np.abs(point - prior)) <= 1e-8 and abs(depth - value) > 1e-9:
                                local_reasons.add("incident_native_knot_depth_conflict")
                registry[bucket].append((point, depth))
            coefficients = [depths[0], depths[1] - depths[0]]
            proof = {"kind": "edge_function_proof", "segment_id": "edge:" + str(len(proofs)),
                "start_xz_m": first.tolist(), "end_xz_m": second.tolist(), "source": native,
                "depth_coefficients_m_t01": coefficients, "sides": sides,
                "side_depth_knots": [{"triangle_id": side["triangle_id"], "edge_index": side["edge_index"],
                    "depth_knots_m": depths} for side in sides], "source_samples": source_samples,
                "boundary_condition": boundary if boundary is not None else {"kind": "source_bank_zero_cut" if len(sides) == 1 else "shared_node_internal_edge"},
                "policy_identity_sha256": POLICY_IDENTITY_SHA256,
                "status": "refused" if local_reasons else "candidate", "rejection_reasons": sorted(local_reasons)}
            proof["common_function_identity_sha256"] = geometry._record_identity({key: proof[key]
                for key in ("start_xz_m", "end_xz_m", "source", "depth_coefficients_m_t01", "policy_identity_sha256")})
            proofs.append(seal(proof))
            reasons.update(local_reasons)
    record["edge_proofs"] = proofs
    by_triangle = defaultdict(list)
    for proof in proofs:
        for side in proof["sides"]:
            by_triangle[side["triangle_id"]].append(proof)
    global_vertices = defaultdict(list)
    for face in triangles:
        function = fans.build_triangle_function(face, by_triangle[face["triangle_id"]], context, PARAMETERS)
        function["policy_identity_sha256"] = POLICY_IDENTITY_SHA256
        for fan in function["fans"]:
            for point, depth in zip(fan["vertices_xz_m"], fan["depth_at_vertices_m"]):
                if not 0. <= depth <= 4.:
                    reasons.add("strict_fan_depth_refused")
                bucket = fans._bucket(np.asarray(point))
                for horizontal in (-1, 0, 1):
                    for vertical in (-1, 0, 1):
                        for prior, value in global_vertices[(bucket[0] + horizontal, bucket[1] + vertical)]:
                            if max(abs(left - right) for left, right in zip(point, prior)) <= 1e-8 and abs(depth - value) > 1e-9:
                                reasons.add("global_incident_fan_vertex_depth_conflict")
                global_vertices[bucket].append((point, depth))
            for patch in fan["native_patches"]:
                if max(fan["depth_at_vertices_m"]) > 0. and _patch_wet(context, patch):
                    reasons.add("fan_native_patch_wet_cut_refused")
        record["source_functions"].append(seal(function))
        reasons.update(function["rejection_reasons"])
    return reasons


def _port_descriptor(record, arm):
    mesh = record["geometry"]
    ids = arm["midpoint_vertex_ids"]
    segments = []
    for number, (first, second) in enumerate(zip(ids, ids[1:])):
        pair = [mesh["vertices_xyz_m"][first], mesh["vertices_xyz_m"][second]]
        pieces = []
        for proof in record["edge_proofs"]:
            boundary = proof["boundary_condition"]
            if boundary.get("arc_id") != arm["arc_id"] or boundary.get("profile_segment_index") != number:
                continue
            if len(proof["sides"]) != 1:
                raise ValueError("midpoint_port_not_actual_boundary")
            side = proof["sides"][0]
            native, depth = proof["source"]["source_coefficients_m_t012"], proof["depth_coefficients_m_t01"]
            start, end = np.asarray(pair)[:, [0, 2]]
            vector = end - start
            interval = sorted(float((np.asarray(proof[name]) - start) @ vector / (vector @ vector))
                for name in ("start_xz_m", "end_xz_m"))
            pieces.append({"interval_t01": interval, "start_xz_m": proof["start_xz_m"], "end_xz_m": proof["end_xz_m"],
                "source_coefficients_m_t012": native, "bed_coefficients_m_t012": [native[0] - depth[0], native[1] - depth[1], native[2]],
                "depth_coefficients_m_t01": depth, "segment_id": proof["segment_id"],
                "side": {"kind": "node", "node_id": record["node_id"], "hub_node_id": record["node_id"],
                    "triangle_index": side["triangle_index"], "edge_index": side["edge_index"], "points_xyz_m": side["points_xyz_m"]}})
        if not pieces:
            raise ValueError("missing_midpoint_native_pieces")
        segments.append({"points_xyz_m": pair, "profile_segment_index": number, "pieces": pieces})
    return {"kind": "node", "hub_node_id": record["node_id"], "node_id": record["node_id"], "arc_id": arm["arc_id"],
        "outer_node_id": "midpoint:" + arm["arc_id"], "midpoint_port_identity_sha256": arm["midpoint_port_identity_sha256"],
        "original_profile_xyz_m": [mesh["vertices_xyz_m"][index] for index in ids], "segments": segments,
        "boundary_condition": "shared_midpoint_geometry_port_only", "hydraulic_boundary_claimed": False}


def _inner_port_proof(record, arm):
    mesh = record["geometry"]
    ids = arm["inner_vertex_ids"]
    segments = []
    for number, (first, second) in enumerate(zip(ids, ids[1:])):
        pair = [mesh["vertices_xyz_m"][first], mesh["vertices_xyz_m"][second]]
        pieces = []
        for proof in record["edge_proofs"]:
            sides = [side for side in proof["sides"] if side["points_xyz_m"] in (pair, pair[::-1])]
            if not sides:
                continue
            if len(sides) != 2 or sides[0]["points_xyz_m"] != sides[1]["points_xyz_m"][::-1]:
                raise ValueError("inner_port_requires_two_actual_reverse_sides")
            roles = [mesh["triangle_roles"][side["triangle_index"]]["region"] for side in sides]
            if set(roles) != {"half_arm", "node_ring"}:
                raise ValueError("inner_port_not_between_half_arm_and_core")
            start, end = np.asarray(pair)[:, [0, 2]]
            vector = end - start
            interval = sorted(float((np.asarray(proof[name]) - start) @ vector / (vector @ vector))
                for name in ("start_xz_m", "end_xz_m"))
            pieces.append({"segment_id": proof["segment_id"], "interval_t01": interval,
                "side_refs": [{key: side[key] for key in ("triangle_id", "triangle_index", "edge_index")} for side in sides],
                "reverse_seam": True, "common_function_identity_sha256": proof["common_function_identity_sha256"]})
        intervals = sorted(piece["interval_t01"] for piece in pieces)
        if (not intervals or abs(intervals[0][0]) > 1e-8 or abs(intervals[-1][1] - 1.) > 1e-8
                or any(abs(left[1] - right[0]) > 1e-8 for left, right in zip(intervals, intervals[1:]))):
            raise ValueError("inner_port_native_intervals_incomplete")
        segments.append({"profile_segment_index": number, "points_xyz_m": pair, "native_pieces": pieces})
    return seal({"kind": "complete_inner_four_point_port", "arc_id": arm["arc_id"], "profile_vertex_ids": ids,
        "profile_segments": segments, "status": "candidate", "policy_identity_sha256": POLICY_IDENTITY_SHA256})


def build_node_piece(hierarchy, paths, sections, *, node_id, midpoint_ports, wet_protection,
                     clipping_evidence=None, input_pins=None):
    check_memory()
    _check_parents(hierarchy, paths, sections)
    nodes, arcs, profiles = _maps(paths, sections)
    index, section = profiles[node_id]
    context = geometry._context(hierarchy, sections["selected_leaf_ids"], wet_protection)
    reasons, center_sample = _safety(nodes[node_id], section, context)
    reasons = set(reasons)
    ports = sorted(midpoint_ports, key=lambda item: item["arc_id"])
    if not 1 <= len(ports) <= 4:
        reasons.add("requires_one_to_four_actual_half_arms")
    if len({port["arc_id"] for port in ports}) != len(ports):
        reasons.add("duplicate_half_arm")
    for port in ports:
        geometry._check_identity(port)
        if port["status"] != "candidate":
            reasons.add("midpoint_refused:" + port["arc_id"])
        if (node_id not in port["node_ids"] or arcs[port["arc_id"]]["node_ids"] != port["node_ids"]
                or port["parents"]["paths"] != paths["identity_sha256"]
                or port["parents"]["sections"] != sections["identity_sha256"]
                or port["parents"]["hierarchy"] != hierarchy["identity_sha256"]
                or port["policy_identity_sha256"] != POLICY_IDENTITY_SHA256):
            reasons.add("midpoint_parent_or_actual_arc_mismatch")
    mesh = {"vertices_xyz_m": [], "vertex_depths_m": [], "triangles": [], "triangle_roles": [],
        "ring_vertex_indices": [], "outer_bank_control_vertex_ids": []}
    original_degree = sum(node_id in arc["node_ids"] for arc in arcs.values())
    record = {"schema": "td-shared-port-node-piece-v1", "policy_identity_sha256": POLICY_IDENTITY_SHA256,
        "inputs": dict(input_pins or {}), "parents": {"paths": paths["identity_sha256"], "sections": sections["identity_sha256"],
            "hierarchy": hierarchy["identity_sha256"], "source": hierarchy["metadata"]["source_identity_sha256"]},
        "node_id": node_id, "source_xyz_m": nodes[node_id]["xyz_m"], "node_section_index": index,
        "parent_section": deepcopy(section), "center_depth_m": section["depth_m"], "center_source_sample": center_sample,
        "degree": len(ports), "original_land_degree": original_degree, "parameters": PARAMETERS,
        "geometry": mesh, "arms": [], "edge_proofs": [], "port_proofs": [], "inner_port_proofs": [], "source_functions": [],
        "bed_slope_diagnostics": [], "terminal_evidence": None, "wet_protection": context["wet_protection"],
        **{flag: False for flag in FLAGS}}
    if reasons:
        record.update(status="refused", rejection_reasons=sorted(reasons))
        return seal(record)
    center = np.asarray(nodes[node_id]["xyz_m"])[[0, 2]]

    def vertex(location, cut):
        sample = geometry._source_sample(context, *map(float, location))
        reasons.update(sample["rejection_reasons"])
        if sample["height_m"] is None:
            raise ValueError("node_vertex_source_unknown")
        if cut > 0. and sample["wet_source_support"]:
            reasons.add("node_vertex_wet_cut_refused")
        mesh["vertices_xyz_m"].append([float(location[0]), sample["height_m"] - cut, float(location[1])])
        mesh["vertex_depths_m"].append(cut)
        return len(mesh["vertices_xyz_m"]) - 1

    def face(indices, role):
        points = np.asarray([mesh["vertices_xyz_m"][identifier] for identifier in indices])[:, [0, 2]]
        if junction._cross(points[1] - points[0], points[2] - points[0]) < 0.:
            indices = indices[::-1]
        mesh["triangles"].append(indices)
        mesh["triangle_roles"].append(role)

    groups = []
    try:
        for port in ports:
            profile = port["profile"]
            flow = np.asarray(port["flow_unit_xz"])
            normal = np.array([-flow[1], flow[0]])
            radial = np.asarray(port["midpoint_xz_m"]) - center
            half_length = float(np.linalg.norm(radial))
            radial /= half_length
            bank_extent = max(abs(value) for value in profile["transverse_offsets_m"])
            if bank_extent >= half_length:
                reasons.add("profile_width_half_arc_distance_conflict")
            outer_ids = []
            for point, cut in zip(profile["profile_xyz_m"], profile["cut_depths_m"]):
                mesh["vertices_xyz_m"].append(deepcopy(point))
                mesh["vertex_depths_m"].append(cut)
                outer_ids.append(len(mesh["vertices_xyz_m"]) - 1)
            inner_ids = []
            if len(ports) == 1:
                terminal = _profile(center, flow, section, context)
                reasons.update(terminal["rejection_reasons"])
                if terminal["status"] == "refused":
                    break
                for point, cut in zip(terminal["profile_xyz_m"], terminal["cut_depths_m"]):
                    inner_ids.append(vertex(np.asarray(point)[[0, 2]], cut))
                mesh["terminal_vertex_ids"] = inner_ids
                record["terminal_evidence"] = {"classification": "actual_land_terminal" if original_degree == 1 else "clipped_fragment_boundary",
                    "original_node_section_index": index, "original_profile_xyz_m": section.get("cross_section_xyz_m", []),
                    "derived_terminal_profile": terminal, "clipping": clipping_evidence or [],
                    "unchanged_absolute_floor_claimed": False, "hydraulic_boundary_claimed": False}
                inset = 0.
            else:
                inset = min(.4 * half_length, max(1., 1.5 * bank_extent))
                for offset, cut in zip(profile["transverse_offsets_m"], profile["cut_depths_m"]):
                    inner_ids.append(vertex(center + radial * inset + normal * offset, cut))
                order = inner_ids if junction._cross(radial, normal) > 0. else inner_ids[::-1]
                groups.append((math.atan2(radial[1], radial[0]), order))
            arm = {"arc_id": port["arc_id"], "node_ids": port["node_ids"],
                "midpoint_port_identity_sha256": port["identity_sha256"], "midpoint_vertex_ids": outer_ids,
                "inner_vertex_ids": inner_ids, "inset_m": inset, "flow_unit_xz": port["flow_unit_xz"],
                "profile_xyz_m": profile["profile_xyz_m"], "half_length_m": half_length}
            record["arms"].append(arm)
            for number in range(3):
                face([outer_ids[number], outer_ids[number + 1], inner_ids[number]], {"region": "half_arm", "arc_id": port["arc_id"]})
                face([outer_ids[number + 1], inner_ids[number + 1], inner_ids[number]], {"region": "half_arm", "arc_id": port["arc_id"]})
            center_bed = center_sample["height_m"] - section["depth_m"]
            midpoint_bed = (profile["profile_xyz_m"][1][1] + profile["profile_xyz_m"][2][1]) / 2.
            upstream_bed, downstream_bed = (center_bed, midpoint_bed) if port["node_ids"][0] == node_id else (midpoint_bed, center_bed)
            record["bed_slope_diagnostics"].append({"arc_id": port["arc_id"], "half_length_m": half_length,
                "center_bed_m": center_bed, "midpoint_mean_bottom_bed_m": midpoint_bed,
                "flow_downhill_slope_m_per_m": (upstream_bed - downstream_bed) / half_length,
                "adverse_bed_slope": upstream_bed < downstream_bed, "diagnostic_only": True,
                "fine_or_hydraulic_profile_claimed": False})
        if len(ports) >= 2:
            ring = [identifier for angle, group in sorted(groups) for identifier in group]
            expanded = []
            for first, second in zip(ring, ring[1:] + ring[:1]):
                expanded.append(first)
                first_delta, second_delta = np.asarray(mesh["vertices_xyz_m"])[[first, second]][:, [0, 2]] - center
                gap = math.atan2(junction._cross(first_delta, second_delta), float(first_delta @ second_delta)) % (2. * math.pi)
                if gap > math.pi + 1e-10:
                    angle = math.atan2(first_delta[1], first_delta[0]) + gap / 2.
                    radius = max(float(np.linalg.norm(first_delta)), float(np.linalg.norm(second_delta)))
                    control = vertex(center + radius * np.array([math.cos(angle), math.sin(angle)]), 0.)
                    expanded.append(control)
                    mesh["outer_bank_control_vertex_ids"].append(control)
            ring = expanded
            mesh["ring_vertex_indices"] = ring
            center_id = vertex(center, section["depth_m"])
            mesh["center_vertex_id"] = center_id
            for first, second in zip(ring, ring[1:] + ring[:1]):
                delta_first, delta_second = np.asarray(mesh["vertices_xyz_m"])[[first, second]][:, [0, 2]] - center
                if junction._cross(delta_first, delta_second) <= 1e-10:
                    reasons.add("directional_inner_ring_not_star_shaped")
                face([first, second, center_id], {"region": "node_ring", "node_id": node_id})
        empty_context = {"mesh": {"vertices_xyz_m": [], "triangles": []}}
        reasons.update(junction._mesh_checks(mesh, empty_context, []))
        if not reasons:
            reasons.update(_prove_mesh(record, context))
        if not reasons:
            for arm in record["arms"]:
                descriptor = _port_descriptor(record, arm)
                record["port_proofs"].append(descriptor)
                if len(ports) >= 2:
                    record["inner_port_proofs"].append(_inner_port_proof(record, arm))
            if len(record["port_proofs"]) != len(ports):
                reasons.add("incomplete_actual_midpoint_ports")
    except (ValueError, np.linalg.LinAlgError) as error:
        reasons.add("node_geometry_or_source_refused:" + str(error))
    record.update(status="refused" if reasons else "candidate", rejection_reasons=sorted(reasons),
        display_mesh_semantics="visualization_approximation_exact_bed_is_native_source_minus_saved_affine_cut_fans",
        construction_checks={"positive_nonoverlapping_projection": not reasons,
            "center_inside_simple_directional_ring": len(ports) >= 2 and not reasons,
            "complete_inner_port_functions": len(ports) >= 2 and not reasons,
            "independent_audit_passed": False})
    check_memory()
    if geometry._record_bytes(record) > MAX_BYTES:
        raise MemoryError("node JSON exceeds 64MiB")
    return seal(record)


class FragmentComposer:
    def __init__(self, paths, sections, selection):
        self.paths, self.sections, self.selection = paths, sections, selection
        self.mesh = {"schema": "td-shared-port-fragment-mesh-v1", "vertices_xyz_m": [], "triangles": [], "face_origins": [],
            "old06_mesh_included": False, "parametric_only": True, **{flag: False for flag in FLAGS}}
        self.rows, self.ports, self.seams = [], {}, []
        self.closed = set()
        self.face_points = []

    def add_node(self, record, pin=None):
        node_id = record["node_id"]
        if any(row["node_id"] == node_id for row in self.rows):
            raise ValueError("duplicate node package")
        row = {"node_id": node_id, "pin": pin, "source_xyz_m": record["source_xyz_m"],
            "generation_status": record["status"], "composition_status": "refused",
            "generation_rejection_reasons": record["rejection_reasons"], "rejection_reasons": [],
            "arc_ids": [arm["arc_id"] for arm in record["arms"]], "bed_slope_diagnostics": record["bed_slope_diagnostics"]}
        if record["terminal_evidence"] is not None:
            row["terminal_port"] = {"classification": record["terminal_evidence"]["classification"],
                "profile_xyz_m": record["terminal_evidence"]["derived_terminal_profile"]["profile_xyz_m"],
                "hydraulic_boundary_claimed": False}
        self.rows.append(row)
        if record["status"] != "candidate":
            row["rejection_reasons"] = ["node_generation_refused"]
            return row
        reasons, seams = set(), []
        if len(self.mesh["triangles"]) + len(record["geometry"]["triangles"]) > MAX_FACES:
            reasons.add("fragment_face_budget_exceeded")
        for port in record["port_proofs"]:
            prior = self.ports.get(port["arc_id"])
            if prior is None:
                continue
            if port["arc_id"] in self.closed:
                reasons.add("midpoint_more_than_two_sides")
                continue
            if prior["midpoint_port_identity_sha256"] != port["midpoint_port_identity_sha256"]:
                reasons.add("canonical_midpoint_identity_mismatch")
            seam, reason = match_ports(port, prior)
            if reason:
                reasons.add("midpoint_seam:" + reason)
            else:
                seam["arc_id"] = port["arc_id"]
                seam["first_node_id"], seam["second_node_id"] = port["node_id"], prior["node_id"]
                seam["midpoint_port_identity_sha256"] = port["midpoint_port_identity_sha256"]
                seams.append(seam)
        allowed = {tuple(sorted(tuple(point) for point in np.asarray(seam["original_profile_xyz_m"][number:number + 2])[:, [0, 2]].tolist()))
            for seam in seams for number in range(3)}
        allowed_points = [np.asarray(point)[[0, 2]] for seam in seams for point in seam["original_profile_xyz_m"]]
        geometry_record = record["geometry"]
        projected = np.asarray(geometry_record["vertices_xyz_m"])[np.asarray(geometry_record["triangles"], int)][:, :, [0, 2]]
        if self.face_points:
            prior_points = np.asarray(self.face_points)
            low, high = prior_points[:, :, [0, 2]].min(axis=1), prior_points[:, :, [0, 2]].max(axis=1)
            for number, triangle in enumerate(projected):
                candidates = np.flatnonzero(np.all(high + 1e-8 >= triangle.min(axis=0), axis=1)
                    & np.all(low - 1e-8 <= triangle.max(axis=0), axis=1))
                new_indices = geometry_record["triangles"][number]
                for prior_index in candidates:
                    old_triangle = prior_points[prior_index][:, [0, 2]]
                    if junction._overlap_area(triangle, old_triangle) > 1e-8:
                        reasons.add("new_node_projected_overlap")
                    for edge in range(3):
                        pair = [geometry_record["vertices_xyz_m"][new_indices[edge]], geometry_record["vertices_xyz_m"][new_indices[(edge + 1) % 3]]]
                        key = tuple(sorted(tuple(point) for point in np.asarray(pair)[:, [0, 2]].tolist()))
                        for old_edge in range(3):
                            old_pair = [prior_points[prior_index][old_edge].tolist(), prior_points[prior_index][(old_edge + 1) % 3].tolist()]
                            if _contact(pair, old_pair) and (key not in allowed or pair != old_pair[::-1]):
                                reasons.add("partial_unbound_wrong_direction_or_nonmanifold_contact")
                            for points, other in ((pair, old_pair), (old_pair, pair)):
                                first, second = np.asarray(other)[:, [0, 2]]
                                vector = second - first
                                squared_length = float(vector @ vector)
                                for point in np.asarray(points)[:, [0, 2]]:
                                    parameter = float((point - first) @ vector / squared_length)
                                    if (0. <= parameter <= 1. and abs(junction._cross(vector, point - first)) <= 1e-8 * math.sqrt(squared_length)
                                            and not any(np.max(np.abs(point - allowed_point)) <= 1e-8 for allowed_point in allowed_points)):
                                        reasons.add("unbound_vertex_or_t_junction_contact")
        if reasons:
            row["rejection_reasons"] = sorted(reasons)
            return row
        offset = len(self.mesh["vertices_xyz_m"])
        self.mesh["vertices_xyz_m"].extend(deepcopy(geometry_record["vertices_xyz_m"]))
        self.mesh["triangles"].extend([[offset + identifier for identifier in triangle] for triangle in geometry_record["triangles"]])
        for number, (indices, role) in enumerate(zip(geometry_record["triangles"], geometry_record["triangle_roles"])):
            self.mesh["face_origins"].append({"node_id": node_id, "triangle_index": number, "role": role})
            self.face_points.append([geometry_record["vertices_xyz_m"][identifier] for identifier in indices])
        for port in record["port_proofs"]:
            if port["arc_id"] not in self.ports:
                self.ports[port["arc_id"]] = deepcopy(port)
        self.closed.update(seam["arc_id"] for seam in seams)
        self.seams.extend(seams)
        row["composition_status"] = "selected"
        check_memory()
        return row

    def finish(self, port_rows, input_pins=None):
        nodes, arcs, profiles = _maps(self.paths, self.sections)
        selected_nodes = sorted(row["node_id"] for row in self.rows if row["composition_status"] == "selected")
        actual_arcs = [arcs[arc_id] for arc_id in sorted(self.closed)]
        components = _components(selected_nodes, actual_arcs)
        degree = defaultdict(int)
        for arc in actual_arcs:
            for node_id in arc["node_ids"]:
                degree[node_id] += 1
        longest = longest_chain(selected_nodes, actual_arcs, nodes)
        open_ports = [{"node_id": port["node_id"], "arc_id": arc_id,
            "midpoint_port_identity_sha256": port["midpoint_port_identity_sha256"],
            "profile_xyz_m": port["original_profile_xyz_m"], "reason": "other_half_arm_not_composition_selected",
            "boundary_condition": "shared_midpoint_geometry_port_only", "hydraulic_boundary_claimed": False}
            for arc_id, port in sorted(self.ports.items()) if arc_id not in self.closed]
        terminal_ports = [{"node_id": row["node_id"], **row["terminal_port"], "reason": "geometric_terminal_open_section"}
            for row in self.rows if row["composition_status"] == "selected" and "terminal_port" in row]
        complete_arcs = set(self.closed)
        selected_attempts = set(self.selection["selected_arc_ids"])
        replacement = [number for number, arc_id in enumerate(self.sections["mesh"]["triangle_arc_ids"]) if arc_id in complete_arcs]
        context_ids = [number for number, arc_id in enumerate(self.sections["mesh"]["triangle_arc_ids"]) if arc_id not in selected_attempts]
        main_component = next((component for component in components if longest["node_ids"] and longest["node_ids"][0] in component), [])
        main_component_arc_ids = {arc["arc_id"] for arc in actual_arcs if set(arc["node_ids"]) <= set(main_component)}
        mesh_points = np.asarray(self.mesh["vertices_xyz_m"]).reshape(-1, 3)
        topology = {"schema": "td-shared-port-channel-topology-v1", "metrics_status": "candidate_unverified", "verified": False,
            "components": [{"component_id": number, "node_ids": component,
                "arc_ids": [arc["arc_id"] for arc in actual_arcs if set(arc["node_ids"]) <= set(component)],
                "bounds_xyz_m": [np.asarray([nodes[node_id]["xyz_m"] for node_id in component]).min(axis=0).tolist(),
                    np.asarray([nodes[node_id]["xyz_m"] for node_id in component]).max(axis=0).tolist()]} for number, component in enumerate(components)],
            "component_count": len(components), "joined_arc_ids": sorted(self.closed), "joined_arc_count": len(self.closed),
            "longest_directed_path": longest, "branch_node_ids": sorted(node_id for node_id, count in degree.items() if count >= 3),
            "branch_arc_ids": sorted(main_component_arc_ids - set(longest["arc_ids"])),
            "other_component_arc_ids": sorted(set(self.closed) - main_component_arc_ids), "open_ports": open_ports,
            "terminal_open_ports": terminal_ports, "source_terrain": {key: self.paths.get(key) for key in ("origin_m_xz", "spacing_m", "grid_shape")},
            "geometry_bounds_xyz_m": [mesh_points.min(axis=0).tolist(), mesh_points.max(axis=0).tolist()] if len(mesh_points) else None,
            "source_identity_sha256": self.paths["source_identity_sha256"], "no_node_id_only_connections": True, **{flag: False for flag in FLAGS}}
        manifest = {"schema": SCHEMA, "policy": POLICY, "policy_identity_sha256": POLICY_IDENTITY_SHA256,
            "parameters": PARAMETERS, "inputs": dict(input_pins or {}), "selected_node_ids": selected_nodes,
            "selected_arc_ids": sorted(self.closed), "attempted_arc_ids": self.selection["selected_arc_ids"],
            "nodes": self.rows, "ports": port_rows, "shared_midpoint_seams": self.seams,
            "replacement": {"candidate_replaced_06_triangle_ids": replacement, "independent_old_context_triangle_ids": context_ids,
                "partial_or_refused_selected_arc_ids": sorted(selected_attempts - complete_arcs),
                "original_06_in_fragment_mesh": False, "old_packages_changed": False,
                "fine_replacement_committed": False, "material_effects_generated": False},
            "metrics_status": "candidate_unverified", "independent_audit_passed": False, **{flag: False for flag in FLAGS}}
        return {"manifest": seal(manifest), "mesh": seal(self.mesh), "topology": seal(topology)}
