"""Independent native-segment and incident-knot checks for saved v3 banks."""

import numpy as np
from collections import defaultdict

from tools.td_entry_saved_audit import assert_close
from tools.td_source_conforming_saved_audit import native_edge_polynomial
from tools.audit_td_fine_bed_raster import _source

POLICY = {
    "algorithm": "native-bilinear-minus-legacy-matched-shared-knot-affine-depth-fan-v3",
    "legacy_depth": "native_segment_source_minus_unchanged_legacy_line_whole_coefficients",
    "legacy_quadratic": "refuse_nonzero_source_quadratic_no_joint_neighbor_version",
    "incident_knots": "legacy_constraint_propagates_to_all_incident_edges_before_fan_build",
    "interior_depth": "original_shared_T_vertex_interpolation_unless_legacy_constrained",
    "uncovered_nonzero": "classify_from_original_sections_paths_but_refuse_without_bound_BC",
    "nonnegative": "strict_no_clamp",
    "gates": "unchanged_v2_maxcut_wet_source_coverage_atomic_signed_material",
}


def knot_key(point):
    return tuple(int(np.floor(float(value)/1e-8)) for value in point)


def nearby(registry, point):
    bucket = knot_key(point)
    return [record for horizontal in (-1, 0, 1) for vertical in (-1, 0, 1)
            for record in registry.get((bucket[0]+horizontal, bucket[1]+vertical), [])
            if np.max(np.abs(np.asarray(point)-record[0])) <= 1e-8]


def legacy_line_polynomial(points_xyz_m, start_xz_m, end_xz_m):
    points = np.asarray(points_xyz_m, float)
    endpoints = np.asarray([start_xz_m, end_xz_m], float)
    if points.shape != (2, 3) or endpoints.shape != (2, 2) or not np.isfinite(points).all() or not np.isfinite(endpoints).all():
        raise ValueError("invalid saved legacy line")
    vector = points[1, [0, 2]] - points[0, [0, 2]]
    squared_length = float(vector @ vector)
    if squared_length <= 1e-16:
        raise ValueError("degenerate saved legacy line")
    offsets = endpoints - points[0, [0, 2]]
    fractions = offsets @ vector / squared_length
    distance = np.abs(offsets[:, 0]*vector[1] - offsets[:, 1]*vector[0])/np.sqrt(squared_length)
    if distance.max() > 1e-8 or fractions.min() < -1e-8 or fractions.max() > 1+1e-8:
        raise ValueError("native segment outside saved legacy line")
    heights = points[0, 1] + fractions*(points[1, 1]-points[0, 1])
    return np.array([heights[0], heights[1]-heights[0], 0.])


def legacy_endpoint_depths(points_xyz_m, start, end, hierarchy, selected):
    legacy_line_polynomial(points_xyz_m, start, end)
    vertices = np.asarray(points_xyz_m, float)
    vector = vertices[1, [0, 2]]-vertices[0, [0, 2]]
    depths = []
    for point in (start, end):
        point = np.asarray(point, float)
        height, reasons, provenance = _source(hierarchy["arrays"], hierarchy["metadata"], selected, point)
        if height is None:
            raise ValueError("unknown native legacy endpoint source")
        fraction = float((point-vertices[0, [0, 2]])@vector/(vector@vector))
        old_height = float(vertices[0, 1]+fraction*(vertices[1, 1]-vertices[0, 1]))
        depths.append(height-old_height)
    return np.asarray(depths)


def incident_constraints(proofs, hierarchy, selected):
    registry = {}
    conflicts = set()
    for proof in proofs.values():
        legacy = [side for side in proof["sides"] if side["triangle_id"].startswith("legacy06:")]
        if not legacy:
            continue
        start, end = proof["start_xz_m"], proof["end_xz_m"]
        for side in legacy:
            try:
                depths = legacy_endpoint_depths(side["points_xyz_m"], start, end, hierarchy, selected)
            except ValueError:
                continue
            for point, value in zip((start, end), depths):
                key = knot_key(point)
                existing = nearby(registry, point)
                if existing:
                    if abs(existing[0][1]-value) > 1e-9:
                        conflicts.add(knot_key(existing[0][0]))
                else:
                    registry.setdefault(key, []).append((np.asarray(point), float(value)))
    return registry, conflicts


def constrained_depths(start, end, default_depths, registry, conflicts):
    values = np.asarray(default_depths, float).copy()
    for index, point in enumerate((start, end)):
        found = nearby(registry, point)
        if any(knot_key(record[0]) in conflicts for record in found):
            raise ValueError("conflicting incident native legacy knot")
        if found:
            assert_close([record[1] for record in found], np.full(len(found), found[0][1]), "incident legacy knot constraints", atol=1e-9)
            values[index] = found[0][1]
    return values


def verify_v3proof(proof, source_coefficients, policy_identity, *, require_match=True):
    saved = proof["v3proof"]
    if saved["policy_identity_sha256"] != policy_identity:
        raise ValueError("v3 edge policy identity differs")
    neighbors = [side for side in proof["sides"] if side["triangle_id"].startswith("legacy06:")]
    expected_rule = "native_source_minus_legacy_line_v3" if neighbors else "shared_incident_native_knot_depth_v3"
    if saved["depth_rule"] != expected_rule:
        raise ValueError("v3 edge depth rule differs")
    records = saved["unchanged_neighbor_polynomials"]
    if len(records) != len(neighbors):
        raise ValueError("missing unchanged neighbor coefficient proof")
    differences = []
    bed = np.asarray(source_coefficients, float).copy()
    proposed = saved["proposed_depth_coefficients_m_t01"]
    if proposed is None:
        if require_match or neighbors:
            raise ValueError("missing proposed native depth coefficients")
        return
    bed[:2] -= proposed
    for side, record in zip(neighbors, records):
        if (record["triangle_id"], record["edge_index"]) != (side["triangle_id"], side["edge_index"]):
            raise ValueError("unchanged neighbor proof binding differs")
        old_line = legacy_line_polynomial(side["points_xyz_m"], proof["start_xz_m"], proof["end_xz_m"])
        assert_close(record["bed_coefficients_m_t012"], old_line, "saved unchanged native-segment coefficients", atol=1e-9)
        differences.append(dict(triangle_id=side["triangle_id"], edge_index=side["edge_index"],
                                difference_coefficients_m_t012=(bed-old_line).tolist()))
        if require_match:
            assert_close(bed, old_line, "whole unchanged neighbor coefficients", atol=1e-9)
    if len(saved["whole_coefficient_differences_m_t012"]) != len(differences):
        raise ValueError("missing complete coefficient differences")
    for actual, expected in zip(saved["whole_coefficient_differences_m_t012"], differences):
        if actual["triangle_id"] != expected["triangle_id"] or actual["edge_index"] != expected["edge_index"]:
            raise ValueError("coefficient difference neighbor binding differs")
        assert_close(actual["difference_coefficients_m_t012"], expected["difference_coefficients_m_t012"], "saved complete coefficient differences", atol=1e-9)
    if require_match:
        assert_close(proposed, proof["depth_coefficients_m_t01"], "proposed accepted depth coefficients", atol=1e-9)


def verify_knot_constraints(proof, registry, conflicts, hierarchy, selected, all_triangles):
    constraints = proof["v3proof"]["knot_constraints"]
    if len(constraints) != 2:
        raise ValueError("v3 native endpoint constraint census differs")
    for point, record in zip((proof["start_xz_m"], proof["end_xz_m"]), constraints):
        found = nearby(registry, point)
        if record is None:
            if found:
                raise ValueError("omitted incident legacy native knot constraint")
            continue
        assert_close(record["xz_m"], point, "constraint native endpoint binding", atol=1e-8)
        identifier = record["legacy_triangle_id"]
        if not identifier.startswith("legacy06:") or identifier not in all_triangles:
            raise ValueError("fabricated unchanged legacy knot reference")
        edge_index = record["legacy_edge_index"]
        if edge_index not in (0, 1, 2):
            raise ValueError("invalid unchanged legacy knot edge")
        vertices = np.asarray(all_triangles[identifier]["vertices_xyz_m"])
        edge = vertices[[edge_index, (edge_index+1)%3]]
        vector = edge[1, [0, 2]]-edge[0, [0, 2]]
        fraction = float((np.asarray(point)-edge[0, [0, 2]])@vector/(vector@vector))
        assert_close(edge[0, [0, 2]]+fraction*vector, point, "constraint lies on legacy edge", atol=1e-8)
        if fraction < -1e-8 or fraction > 1+1e-8:
            raise ValueError("constraint outside legacy edge")
        height, reasons, provenance = _source(hierarchy["arrays"], hierarchy["metadata"], selected, np.asarray(point))
        if height is None:
            raise ValueError("unknown native constraint source")
        depth = height-(edge[0, 1]+fraction*(edge[1, 1]-edge[0, 1]))
        assert_close(record["cut_depth_m"], depth, "independent incident constraint source-oldline", atol=1e-9)
        expected_conflict = any(knot_key(item[0]) in conflicts for item in found)
        if record["conflicting_legacy_depth"] and not expected_conflict:
            for other_id, triangle in all_triangles.items():
                if not other_id.startswith("legacy06:"):
                    continue
                other_vertices = np.asarray(triangle["vertices_xyz_m"])
                for other_index in range(3):
                    endpoints = other_vertices[[other_index, (other_index+1)%3]]
                    direction = endpoints[1, [0, 2]]-endpoints[0, [0, 2]]
                    fraction = float((np.asarray(point)-endpoints[0, [0, 2]])@direction/(direction@direction))
                    if fraction < -1e-8 or fraction > 1+1e-8:
                        continue
                    if np.max(np.abs(endpoints[0, [0, 2]]+fraction*direction-point)) > 1e-8:
                        continue
                    other_depth = height-(endpoints[0, 1]+fraction*(endpoints[1, 1]-endpoints[0, 1]))
                    expected_conflict |= abs(other_depth-depth) > 1e-9
            if not expected_conflict:
                raise ValueError("unsubstantiated legacy constraint conflict")
            conflicts.add(knot_key(point))


def boundary_evidence(sections, paths):
    incoming = defaultdict(list)
    arcs = {arc["arc_id"]: arc for arc in paths["arcs"]}
    nodes = {node["node_id"]: node for node in sections["node_sections"]}
    for arc in arcs.values():
        for first, second in zip(arc["node_ids"], arc["node_ids"][1:]):
            incoming[second].append(dict(arc_id=arc["arc_id"], from_node_id=first))
    result = {}
    mesh = sections["mesh"]
    for number, section in enumerate(sections["edge_sections"]):
        profiles = section.get("cross_section_xyz_m", [])
        if not profiles or not section.get("node_ids"):
            continue
        node_id = section["node_ids"][0]
        node, arc = nodes.get(node_id), arcs.get(section["arc_id"])
        bound = (arc is not None and arc["node_ids"][:2] == section["node_ids"][:2]
                 and node is not None and node.get("cross_section_xyz_m") == profiles[0]
                 and not node.get("rejection_reasons", [])
                 and np.isfinite(node.get("representative_q_m3_s", np.nan))
                 and node.get("representative_q_m3_s", 0.) > 0.)
        for triangle_index in section["triangle_indices"]:
            indices = mesh["triangles"][triangle_index]
            for edge_index in range(3):
                points = [mesh["vertices_xyz_m"][indices[edge_index]], mesh["vertices_xyz_m"][indices[(edge_index+1)%3]]]
                if not any(points == [first, second] or points == [second, first]
                           for first, second in zip(profiles[0], profiles[0][1:])):
                    continue
                result[f"06:{triangle_index}:{edge_index}"] = dict(
                    classification="upstream_profile_without_bound_BC" if bound and not incoming[node_id] else "truncated_bank",
                    sections_identity_sha256=sections["identity_sha256"], paths_identity_sha256=paths["identity_sha256"],
                    section_index=number, arc_id=section["arc_id"], node_id=node_id, profile_index=0,
                    original_edge_xyz_m=points, original_profile_xyz_m=profiles[0],
                    ordinary_identity_sha256=sections.get("ordinary_identity_sha256"),
                    representative_q_m3_s=None if node is None else node.get("representative_q_m3_s"),
                    incoming_path_steps=incoming[node_id], section_path_profile_bound=bool(bound),
                    boundary_condition_bound=False, hydraulic_inflow_claimed=False)
    return result


def verify_incident_fans(fans):
    registry = {}
    for points, origin, coefficients, fan_id in fans:
        points = np.asarray(points, float)
        values = coefficients[0] + (points-origin) @ coefficients[1:]
        for point, value in zip(points, values):
            found = nearby(registry, point)
            for record in found:
                assert_close(value, record[1], "incident fan knot crack "+fan_id, atol=1e-9)
            registry.setdefault(knot_key(point), []).append((point, float(value)))
