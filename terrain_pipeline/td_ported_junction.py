"""Source-relative arm strips joined to a hub ring with complete four-point ports."""

from collections import defaultdict
from copy import deepcopy
import math
from pathlib import Path
import tempfile

import numpy as np

from terrain_pipeline import channel_geometry as geometry
from terrain_pipeline import channel_geometry as source_banks

SCHEMA = "td-ported-junction-v1"
MAX_BYTES = 64 * 1024**2
MAX_RSS = 1024**3
MAX_TRIANGLES = 256
POLICY = {"schema": SCHEMA, "arms": "all_actual_three_land_channel_incident_arcs",
    "outer": "unchanged_four_point_profile_reverse_kept_06_seam_or_explicit_bound_section_open_stub",
    "inner": "independent_flow_normal_profile_preserve_each_outer_transverse_offsets_and_depths",
    "ring": "complete_four_point_ports_in_radial_order_star_center_triangulation",
    "source": "native_bilinear_minus_shared_nonnegative_affine_depth_fans",
    "outer_native_knots": "actual_native_source_minus_unchanged_legacy_line_whole_coefficients",
    "wet": "original_source_gates_and_conservative_native_patch_wet_guard",
    "max_cut_m": 4., "replacement": "whole_component_all_or_none_no_fine_cells_or_material_effects"}
POLICY_IDENTITY_SHA256 = geometry._record_identity(POLICY)
FLAGS = ("bed_changed", "fine_generated", "hydraulic_solved", "hydraulic_ready",
         "full_river_verified", "natural_outlet_certified", "material_budget_verified")


def _seal(record):
    record.pop("identity_sha256", None)
    return geometry._seal(record)


def _cross(first, second):
    return float(first[0] * second[1] - first[1] * second[0])


def _same_segment(first, second):
    return first == second or first == second[::-1]


def _old_port_witnesses(sections, profile):
    mesh = sections["mesh"]
    incidence = defaultdict(list)
    owners = {triangle: (index, section) for index, section in enumerate(sections["edge_sections"])
              for triangle in section["triangle_indices"]}
    for triangle_index, indices in enumerate(mesh["triangles"]):
        for edge_index in range(3):
            pair = [mesh["vertices_xyz_m"][indices[edge_index]],
                    mesh["vertices_xyz_m"][indices[(edge_index + 1) % 3]]]
            incidence[tuple(sorted(tuple(point) for point in pair))].append((triangle_index, edge_index, pair))
    witnesses = []
    if len(profile) != 4:
        return witnesses
    for profile_segment, pair in enumerate(zip(profile, profile[1:])):
        matches = incidence.get(tuple(sorted(tuple(point) for point in pair)), [])
        for triangle_index, edge_index, points in matches:
            owner = owners.get(triangle_index)
            if len(matches) != 1 or owner is None:
                continue
            section_index, section = owner
            for profile_index, saved in enumerate(section["cross_section_xyz_m"]):
                if saved == profile:
                    witnesses.append({"profile_segment_index": profile_segment,
                        "section_index": section_index, "arc_id": section["arc_id"],
                        "profile_index": profile_index, "triangle_index": triangle_index,
                        "edge_index": edge_index, "points_xyz_m": deepcopy(points),
                        "original_triangle_vertex_indices": mesh["triangles"][triangle_index]})
    return witnesses


def _profile_check(profile, node, flow):
    points = np.asarray(profile, float)
    if points.shape != (4, 3) or not np.isfinite(points).all():
        return "missing_or_invalid_outer_four_point_profile"
    relative = points[:, [0, 2]] - np.asarray(node["xyz_m"])[[0, 2]]
    normal = np.array([-flow[1], flow[0]])
    offsets = relative @ normal
    if (np.max(np.abs(relative @ flow)) > 1e-8 or np.any(np.diff(offsets) <= 1e-8)
            or not offsets[0] < offsets[1] < 0. < offsets[2] < offsets[3]):
        return "outer_profile_not_ordered_transverse_to_actual_arc"
    return None


def _overlap_area(first, second):
    polygon = [np.asarray(point) for point in first]
    for start, end in zip(second, np.roll(second, -1, axis=0)):
        if not polygon:
            return 0.
        result = []
        for point, next_point in zip(polygon, polygon[1:] + polygon[:1]):
            first_side, second_side = _cross(end - start, point - start), _cross(end - start, next_point - start)
            if first_side >= 0.:
                result.append(point)
            if (first_side >= 0.) != (second_side >= 0.):
                result.append(point + first_side / (first_side - second_side) * (next_point - point))
        polygon = result
    if len(polygon) < 3:
        return 0.
    anchor = polygon[0]
    return abs(math.fsum(_cross(first - anchor, second - anchor)
                        for first, second in zip(polygon, polygon[1:] + polygon[:1]))) / 2


def _mesh_checks(mesh, sections, kept_triangles):
    points = np.asarray(mesh["vertices_xyz_m"])[:, [0, 2]]
    incidence, reasons = defaultdict(list), set()
    projected = []
    kept_projected = np.asarray([[sections["mesh"]["vertices_xyz_m"][index]
                                 for index in sections["mesh"]["triangles"][triangle_index]]
                                for triangle_index in kept_triangles], float).reshape(-1, 3, 3)[:, :, [0, 2]]
    kept_low, kept_high = kept_projected.min(axis=1), kept_projected.max(axis=1)
    for triangle_index, indices in enumerate(mesh["triangles"]):
        triangle = points[indices]
        if _cross(triangle[1] - triangle[0], triangle[2] - triangle[0]) <= 1e-10:
            reasons.add("degenerate_or_reversed_patch_triangle")
        projected.append(triangle)
        for edge_index in range(3):
            first, second = indices[edge_index], indices[(edge_index + 1) % 3]
            incidence[tuple(sorted((first, second)))].append((triangle_index, first, second))
    for sides in incidence.values():
        if len(sides) > 2 or len(sides) == 2 and sides[0][1:] != sides[1][1:][::-1]:
            reasons.add("nonmanifold_or_same_direction_patch_seam")
    for number, triangle in enumerate(projected):
        for other in projected[number + 1:]:
            if _overlap_area(triangle, other) > 1e-8:
                reasons.add("patch_projected_triangle_overlap")
        candidates = np.flatnonzero(np.all(kept_high >= triangle.min(axis=0), axis=1)
                                    & np.all(kept_low <= triangle.max(axis=0), axis=1))
        for kept_index in candidates:
            old = kept_projected[kept_index]
            if _cross(old[1] - old[0], old[2] - old[0]) < 0:
                old = old[::-1]
            if (np.any(triangle.max(axis=0) < old.min(axis=0))
                    or np.any(old.max(axis=0) < triangle.min(axis=0))):
                continue
            if _overlap_area(triangle, old) > 1e-8:
                reasons.add("patch_overlaps_kept_06_mesh")
    return reasons


def _port_proofs(arms, mesh, edge_proofs):
    result = []
    for arm in arms:
        for kind in ("outer", "inner"):
            profile_ids = arm[kind + "_profile_vertex_ids"]
            pieces, reasons = [], set()
            for profile_segment, (first, second) in enumerate(zip(profile_ids, profile_ids[1:])):
                pair = [mesh["vertices_xyz_m"][first], mesh["vertices_xyz_m"][second]]
                start, end = np.asarray(pair)[:, [0, 2]]
                vector = end - start
                matches = []
                for proof in edge_proofs:
                    points = [np.asarray(proof[name]) for name in ("start_xz_m", "end_xz_m")]
                    if any(abs(_cross(vector, point - start)) > 1e-8 * np.linalg.norm(vector) for point in points):
                        continue
                    interval = sorted(float((point - start) @ vector / (vector @ vector)) for point in points)
                    if interval[0] < -1e-8 or interval[1] > 1 + 1e-8:
                        continue
                    new = [side for side in proof["sides"] if not side["triangle_id"].startswith("legacy06:")]
                    roles = {mesh["triangle_roles"][int(side["triangle_id"].split(":")[1])]["region"] for side in new}
                    if kind == "outer":
                        stub = arm["attachment_status"] != "actual_old_mesh"
                        valid = (len(new) == 1 and roles == {"arm"} and
                                 (len(proof["sides"]) == 1 and proof.get("bound_original_section") is not None if stub
                                  else len(proof["sides"]) == 2))
                    else:
                        stub = False
                        valid = len(new) == len(proof["sides"]) == 2 and roles == {"arm", "hub"}
                    reverse = len(proof["sides"]) == 2 and float(
                        (np.asarray(proof["sides"][0]["points_xyz_m"])[1, [0, 2]]
                         - np.asarray(proof["sides"][0]["points_xyz_m"])[0, [0, 2]]) @
                        (np.asarray(proof["sides"][1]["points_xyz_m"])[1, [0, 2]]
                         - np.asarray(proof["sides"][1]["points_xyz_m"])[0, [0, 2]])) < 0.
                    if not valid or not reverse and not stub or proof["status"] != "candidate":
                        reasons.add("port_missing_reverse_two_sided_whole_function")
                    matches.append({"segment_id": proof["segment_id"], "interval_t01": interval,
                        "side_refs": [{"triangle_id": side["triangle_id"], "edge_index": side["edge_index"]}
                                      for side in proof["sides"]], "reverse_seam": bool(reverse)})
                cursor = 0.
                for match in sorted(matches, key=lambda item: item["interval_t01"]):
                    lower, upper = match["interval_t01"]
                    if abs(lower - cursor) > 1e-8:
                        reasons.add("port_native_piece_gap_or_duplicate")
                    cursor = upper
                if abs(cursor - 1.) > 1e-8:
                    reasons.add("port_profile_segment_not_fully_covered")
                pieces.append({"profile_segment_index": profile_segment, "points_xyz_m": pair, "native_pieces": matches})
            result.append(_seal({"kind": kind + "_port_proof", "arc_id": arm["arc_id"],
                "node_ids": arm["node_ids"], "profile_vertex_ids": profile_ids,
                "profile_segments": pieces, "status": "refused" if reasons else "candidate",
                "attachment_status": arm["attachment_status"] if kind == "outer" else "internal_arm_hub_shared_profile",
                "rejection_reasons": sorted(reasons)}))
    return result


def _stub_binding(segment, record):
    if len(segment["sides"]) != 1:
        return None
    side = segment["sides"][0]
    for arm in record["arms"]:
        if arm["attachment_status"] == "actual_old_mesh":
            continue
        for profile_segment, pair in enumerate(zip(arm["outer_profile_xyz_m"], arm["outer_profile_xyz_m"][1:])):
            if _same_segment(side["points_xyz_m"], list(pair)):
                return {"arc_id": arm["arc_id"], "node_ids": arm["node_ids"],
                    "outer_node_id": arm["outer_node_id"], "outer_section_index": arm["outer_section_index"],
                    "profile_segment_index": profile_segment, "original_points_xyz_m": list(pair),
                    "attachment_status": "bound_original_section_no_accepted_external_strip",
                    "external_mesh_attachment_claimed": False}
    return None


def _edge_proofs(segments, record, context):
    context["v3_parameters"] = record["parameters"]
    context["v3_legacy_knots"] = {}
    for segment in segments:
        source_banks._register_legacy_knots(segment, context)
        binding = _stub_binding(segment, record)
        if binding is None:
            continue
        bound_edge = {"points_xyz_m": binding["original_points_xyz_m"]}
        for name in ("start_xz_m", "end_xz_m"):
            point = np.asarray(segment[name])
            sample = geometry._source_sample(context, *map(float, point))
            if sample["height_m"] is None:
                continue
            depth = sample["height_m"] - geometry._edge_y(bound_edge, point)
            existing = source_banks._constraint(context, point)
            if existing:
                if abs(existing[0]["cut_depth_m"] - depth) > 1e-9:
                    existing[0]["conflicting_legacy_depth"] = True
            else:
                constraint = {"xz_m": point.tolist(), "cut_depth_m": depth,
                    "legacy_triangle_id": None, "legacy_edge_index": None,
                    "legacy_segment_id": segment["segment_id"], "conflicting_legacy_depth": False,
                    "binding_kind": "bound_original_section_open_stub", "bound_original_section": binding}
                context["v3_legacy_knots"].setdefault(source_banks._bucket(point), []).append(constraint)
    result = []
    for segment in segments:
        proof = source_banks._td_source_conforming_banks_mechanism_3_proof(segment, context)
        binding = _stub_binding(segment, record)
        proof["bound_original_section"] = binding
        if binding is not None:
            reasons = set(proof["rejection_reasons"])
            reasons.discard("uncovered_boundary_has_nonzero_depth")
            source = proof["source"]
            depths = proof["side_depth_knots"][0]["depth_knots_m"]
            coefficients = None if any(depth is None for depth in depths) else [depths[0], depths[1] - depths[0]]
            edge = {"points_xyz_m": binding["original_points_xyz_m"]}
            bed_start, bed_end = [geometry._edge_y(edge, np.asarray(segment[name])) for name in ("start_xz_m", "end_xz_m")]
            bed = [bed_start, bed_end - bed_start, 0.]
            difference = None if coefficients is None or source is None else [
                source["source_coefficients_m_t012"][0] - coefficients[0] - bed[0],
                source["source_coefficients_m_t012"][1] - coefficients[1] - bed[1],
                source["source_coefficients_m_t012"][2]]
            if difference is None or max(abs(value) for value in difference) > 1e-9:
                reasons.add("bound_original_section_whole_function_mismatch")
            proof["bound_original_section"].update(bed_coefficients_m_t012=bed,
                                                    difference_coefficients_m_t012=difference)
            proof["depth_coefficients_m_t01"] = None if reasons else coefficients
            proof["v3proof"]["proposed_depth_coefficients_m_t01"] = coefficients
            proof["v3proof"]["depth_rule"] = "native_source_minus_bound_original_section_line_v1"
            proof["boundary_condition"] = "bound_original_section_open_stub_v1"
            proof["status"] = "refused" if reasons else "candidate"
            proof["rejection_reasons"] = sorted(reasons)
        proof["policy_identity_sha256"] = POLICY_IDENTITY_SHA256
        proof["v3proof"]["policy_identity_sha256"] = POLICY_IDENTITY_SHA256
        proof["common_function_identity_sha256"] = None if proof["status"] == "refused" else geometry._record_identity({
            "start_xz_m": proof["start_xz_m"], "end_xz_m": proof["end_xz_m"], "source": proof["source"],
            "depth_coefficients_m_t01": proof["depth_coefficients_m_t01"], "policy_identity_sha256": POLICY_IDENTITY_SHA256})
        result.append(_seal(proof))
    return result


def build_ported_junction(hierarchy, paths, sections, *, hub_node_id, incident_arc_ids=None,
                          wet_protection, input_pins=None, inset_m=None):
    """Return one atomic geometry candidate or an accurately witnessed whole-hub refusal."""
    geometry._rss_guard()
    for parent in (paths, sections):
        if (parent["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]
                or parent["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]):
            raise ValueError("source/hierarchy parent linkage mismatch")
    if paths["ordinary_identity_sha256"] != sections["ordinary_identity_sha256"]:
        raise ValueError("ordinary path/section linkage mismatch")
    nodes = {node["node_id"]: node for node in paths["nodes"]}
    section_map = {section["node_id"]: (index, section) for index, section in enumerate(sections["node_sections"])}
    if hub_node_id not in nodes or hub_node_id not in section_map:
        raise ValueError("explicit hub absent from saved parents")
    actual = [(index, arc) for index, arc in enumerate(paths["arcs"])
              if arc["kind"] == "land_channel" and len(arc["node_ids"]) == 2 and hub_node_id in arc["node_ids"]]
    arc_ids = sorted(arc["arc_id"] for index, arc in actual)
    if incident_arc_ids is not None and sorted(incident_arc_ids) != arc_ids:
        raise ValueError("explicit incident arcs differ from complete actual hub census")
    context = geometry._i46__context(hierarchy, sections["selected_leaf_ids"], wet_protection)
    hub_section_index, hub_section = section_map[hub_node_id]
    reasons = set()
    if len(actual) != 3:
        reasons.add("hub_requires_exactly_three_actual_land_arms")
    if hub_section.get("anchor"):
        reasons.add("hub_anchor_refused")
    reasons.update("hub_parent:" + reason for reason in hub_section.get("rejection_reasons", []) if reason != "needs_junction_patch")
    arms = []
    diagnostics = {item["arc_id"]: item for item in sections["reach_diagnostics"]}
    for path_index, arc in sorted(actual, key=lambda item: item[1]["arc_id"]):
        outer_id = next(identifier for identifier in arc["node_ids"] if identifier != hub_node_id)
        outer_index, outer = section_map[outer_id]
        flow = np.asarray(nodes[arc["node_ids"][1]]["xyz_m"])[[0, 2]] - np.asarray(nodes[arc["node_ids"][0]]["xyz_m"])[[0, 2]]
        length = float(np.linalg.norm(flow))
        if length <= 1e-8:
            raise ValueError("zero length actual arm")
        flow = flow / length
        profile = deepcopy(outer.get("cross_section_xyz_m", []))
        arm_reasons = set(outer.get("rejection_reasons", []))
        if outer.get("anchor"):
            arm_reasons.add("outer_anchor_refused")
        problem = _profile_check(profile, nodes[outer_id], flow)
        if problem:
            arm_reasons.add(problem)
        witnesses = _old_port_witnesses(sections, profile)
        attachment = "actual_old_mesh" if sorted(witness["profile_segment_index"] for witness in witnesses) == [0, 1, 2] else "bound_original_section_no_accepted_external_strip"
        if witnesses and attachment != "actual_old_mesh":
            arm_reasons.add("outer_profile_partially_attached_kept_mesh")
        diagnostic = diagnostics.get(arc["arc_id"])
        if diagnostic is None:
            arm_reasons.add("incident_arc_missing_parent_diagnostic")
        else:
            arm_reasons.update("incident_parent:" + reason for reason in diagnostic["rejection_reasons"] if reason != "needs_junction_patch")
        arms.append({"arc_id": arc["arc_id"], "node_ids": arc["node_ids"], "path_arc_index": path_index,
            "outer_node_id": outer_id, "outer_section_index": outer_index,
            "outer_profile_xyz_m": profile, "outer_parent_rejection_reasons": outer.get("rejection_reasons", []),
            "outer_anchor": bool(outer.get("anchor")), "outer_old_mesh_edge_witnesses": witnesses,
            "attachment_status": attachment,
            "parent_incident_diagnostic": diagnostic, "flow_unit_xz": flow.tolist(), "arm_length_m": length,
            "rejection_reasons": sorted(arm_reasons)})
        reasons.update(arc["arc_id"] + ":" + reason for reason in arm_reasons)
    kept_ids = list(range(len(sections["mesh"]["triangles"])))
    if any(section["arc_id"] in arc_ids for section in sections["edge_sections"]):
        reasons.add("requested_incident_arc_already_has_accepted_06_mesh")
    record = {"schema": SCHEMA, "policy": POLICY, "policy_identity_sha256": POLICY_IDENTITY_SHA256,
        "source_function_policy_identity_sha256": source_banks.POLICY_IDENTITY_SHA256,
        "inputs": dict(input_pins or {}), "parents": {"hierarchy": hierarchy["identity_sha256"],
            "paths": paths["identity_sha256"], "sections": sections["identity_sha256"],
            "source": hierarchy["metadata"]["source_identity_sha256"]},
        "hub_node_id": hub_node_id, "hub_section_index": hub_section_index,
        "hub_parent_section": deepcopy(hub_section), "requested_replacement_arc_ids": arc_ids,
        "selected_leaf_ids": sections["selected_leaf_ids"], "wet_protection": context["wet_protection"],
        "arms": arms, "old_kept_mesh_triangle_ids": kept_ids,
        "geometry": {"vertices_xyz_m": [], "vertex_depths_m": [], "triangles": [], "triangle_roles": [], "ring_vertex_indices": []},
        "edge_proofs": [], "port_proofs": [], "source_functions": [],
        "parameters": {"max_cut_m": 4., "conflict_tolerance_m": 1e-9},
        "budgets": {"max_bytes": MAX_BYTES, "max_rss_bytes": MAX_RSS, "max_triangles": MAX_TRIANGLES},
        "display_mesh_semantics": "visualization_approximation_only_exact_bed_is_saved_native_source_minus_affine_depth_fans",
        **{flag: False for flag in FLAGS}}
    if not reasons:
        reasons.update(_construct(record, nodes, sections, context, inset_m))
    record["status"] = "refused" if reasons else "candidate"
    record["rejection_reasons"] = sorted(reasons)
    record["geometry_through_connection"] = not reasons
    record["internal_three_arm_geometry_candidate"] = not reasons
    record["actual_external_attachment_count"] = sum(arm["attachment_status"] == "actual_old_mesh" for arm in arms) if not reasons else 0
    record["external_closure_verified"] = not reasons and record["actual_external_attachment_count"] == 3
    record["full_network_verified"] = False
    record["transaction"] = {"atomic": True, "candidate_replacement_arc_ids": [] if reasons else arc_ids,
        "replaced_original_triangle_indices": [], "old_kept_triangle_indices": kept_ids,
        "original_06_kept_unchanged": True, "parent_rejection_reasons_unchanged": True,
        "fine_cells_replaced": 0, "material_effects_generated": False}
    _seal(record)
    if geometry._record_bytes(record) > MAX_BYTES:
        raise MemoryError("ported junction record exceeds 64MiB")
    geometry._rss_guard()
    return record


def _construct(record, nodes, sections, context, inset_m):
    mesh, reasons = record["geometry"], set()
    center_xz = np.asarray(nodes[record["hub_node_id"]]["xyz_m"])[[0, 2]]
    center_depth = record["hub_parent_section"]["depth_m"]
    ring_groups = []

    def vertex(point, depth):
        mesh["vertices_xyz_m"].append(list(map(float, point)))
        mesh["vertex_depths_m"].append(float(depth))
        return len(mesh["vertices_xyz_m"]) - 1

    def triangle(indices, role):
        projected = np.asarray([mesh["vertices_xyz_m"][index] for index in indices])[:, [0, 2]]
        if _cross(projected[1] - projected[0], projected[2] - projected[0]) < 0.:
            indices = indices[::-1]
        mesh["triangles"].append(indices)
        mesh["triangle_roles"].append(role)

    for arm in record["arms"]:
        outer = np.asarray(arm["outer_profile_xyz_m"])
        radial = np.asarray(nodes[arm["outer_node_id"]]["xyz_m"])[[0, 2]] - center_xz
        radial /= np.linalg.norm(radial)
        flow = np.asarray(arm["flow_unit_xz"])
        normal = np.array([-flow[1], flow[0]])
        offsets = (outer[:, [0, 2]] - np.asarray(nodes[arm["outer_node_id"]]["xyz_m"])[[0, 2]]) @ normal
        distance = min(.4 * arm["arm_length_m"], max(1., 1.5 * max(abs(offsets)))) if inset_m is None else float(inset_m)
        if not math.isfinite(distance) or not 0. < distance < .5 * arm["arm_length_m"]:
            raise ValueError("arm inset must be positive and below half actual arm length")
        arm["inset_m"] = distance
        arm["outer_transverse_offsets_m"] = offsets.tolist()
        arm["preserved_outer_channel_width_m"] = float(offsets[2] - offsets[1])
        depths = []
        outer_ids, inner_ids = [], []
        for point, offset in zip(outer, offsets):
            sample = geometry._source_sample(context, point[0], point[2])
            reasons.update(sample["rejection_reasons"])
            depth = None if sample["height_m"] is None else sample["height_m"] - point[1]
            if depth is None or not math.isfinite(depth) or not 0. <= depth <= 4.:
                reasons.add("outer_profile_fill_unknown_or_cut_exceeded")
                return reasons
            depths.append(depth)
            outer_ids.append(vertex(point, depth))
            location = center_xz + radial * distance + normal * offset
            inner_source = geometry._source_sample(context, *map(float, location))
            reasons.update(inner_source["rejection_reasons"])
            if inner_source["height_m"] is None:
                return reasons | {"inner_source_unknown"}
            if depth > 0. and inner_source["wet_source_support"]:
                reasons.add("inner_wet_source_cut_refused")
            inner_ids.append(vertex([location[0], inner_source["height_m"] - depth, location[1]], depth))
        arm["outer_profile_vertex_ids"], arm["inner_profile_vertex_ids"] = outer_ids, inner_ids
        arm["inner_profile_xyz_m"] = [mesh["vertices_xyz_m"][index] for index in inner_ids]
        arm["outer_cut_depths_m"] = depths
        for profile_segment in range(3):
            triangle([outer_ids[profile_segment], outer_ids[profile_segment + 1], inner_ids[profile_segment]],
                     {"region": "arm", "arc_id": arm["arc_id"]})
            triangle([outer_ids[profile_segment + 1], inner_ids[profile_segment + 1], inner_ids[profile_segment]],
                     {"region": "arm", "arc_id": arm["arc_id"]})
        order = inner_ids if _cross(radial, np.asarray(arm["inner_profile_xyz_m"])[-1, [0, 2]]
                                  - np.asarray(arm["inner_profile_xyz_m"])[0, [0, 2]]) > 0 else inner_ids[::-1]
        ring_groups.append((math.atan2(radial[1], radial[0]), order))
    ring = [index for angle, group in sorted(ring_groups) for index in group]
    mesh["ring_vertex_indices"] = ring
    center_source = geometry._source_sample(context, *map(float, center_xz))
    reasons.update(center_source["rejection_reasons"])
    if center_source["height_m"] is None or not 0. <= center_depth <= 4.:
        return reasons | {"hub_source_unknown_or_cut_exceeded"}
    if center_depth > 0. and center_source["wet_source_support"]:
        reasons.add("hub_wet_source_cut_refused")
    center_id = vertex([center_xz[0], center_source["height_m"] - center_depth, center_xz[1]], center_depth)
    mesh["hub_center_vertex_id"] = center_id
    for first, second in zip(ring, ring[1:] + ring[:1]):
        first_xz, second_xz = np.asarray(mesh["vertices_xyz_m"])[[first, second]][:, [0, 2]]
        if _cross(first_xz - center_xz, second_xz - center_xz) <= 1e-10:
            reasons.add("inner_port_ring_not_star_shaped")
        triangle([center_id, first, second], {"region": "hub", "hub_node_id": record["hub_node_id"]})
    if len(mesh["triangles"]) > MAX_TRIANGLES:
        raise MemoryError("ported junction triangle budget exceeded")
    reasons.update(_mesh_checks(mesh, sections, record["old_kept_mesh_triangle_ids"]))
    groups, triangles = defaultdict(list), []
    for number, indices in enumerate(mesh["triangles"]):
        face = {"triangle_id": "junction:" + str(number), "vertices_xyz_m": [mesh["vertices_xyz_m"][index] for index in indices],
                "replacement_role": mesh["triangle_roles"][number], "vertex_ids": indices}
        triangles.append(face)
        for edge_index in range(3):
            edge = geometry._edge_record(face, edge_index)
            edge["zero_depth_boundary_eligible"] = all(mesh["vertex_depths_m"][index] == 0.
                for index in (indices[edge_index], indices[(edge_index + 1) % 3]))
            groups[geometry._line_key(np.asarray(edge["points_xyz_m"])[:, [0, 2]])].append(edge)
    for arm in record["arms"]:
        for witness in arm["outer_old_mesh_edge_witnesses"]:
            edge = {"triangle_id": "legacy06:" + str(witness["triangle_index"]),
                    "edge_index": witness["edge_index"], "points_xyz_m": witness["points_xyz_m"]}
            groups[geometry._line_key(np.asarray(edge["points_xyz_m"])[:, [0, 2]])].append(edge)
    edge_proofs = _edge_proofs(geometry._segments(groups, context), record, context)
    record["edge_proofs"] = edge_proofs
    by_triangle = defaultdict(list)
    for proof in edge_proofs:
        reasons.update(proof["rejection_reasons"])
        for side in proof["sides"]:
            by_triangle[side["triangle_id"]].append(proof)
    for face in triangles:
        function = source_banks.build_triangle_function(face, by_triangle[face["triangle_id"]], context, record["parameters"])
        function["policy_identity_sha256"] = POLICY_IDENTITY_SHA256
        _seal(function)
        record["source_functions"].append(function)
        reasons.update(function["rejection_reasons"])
        for fan in function["fans"]:
            if any(not 0. <= depth <= 4. for depth in fan["depth_at_vertices_m"]):
                reasons.add("fan_strict_cut_depth_exceeded")
            for patch in fan["native_patches"]:
                covered = bool(set(patch["native_cell_ids"]) & context["covered_native_cells"])
                wet_stage = any(context["height"].ravel()[cell] < context["stage_by_leaf"].get(
                    int(context["arrays"]["contribution_owner"].ravel()[cell]), -math.inf) for cell in patch["native_cell_ids"])
                if (covered or wet_stage) and max(fan["depth_at_vertices_m"]) > 0.:
                    reasons.add("native_patch_wet_cut_conservatively_refused")
    record["port_proofs"] = _port_proofs(record["arms"], mesh, edge_proofs)
    reasons.update(reason for proof in record["port_proofs"] for reason in proof["rejection_reasons"])
    return reasons


def save_ported_junction(record, directory):
    geometry._check_identity(record)
    if record["schema"] != SCHEMA or record["policy_identity_sha256"] != POLICY_IDENTITY_SHA256:
        raise ValueError("ported junction schema/policy mismatch")
    if geometry._record_bytes(record) > MAX_BYTES:
        raise MemoryError("ported junction file exceeds 64MiB")
    target = Path(directory)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ported-junction-", dir=target.parent) as staging:
        stage = Path(staging) / "package"
        geometry._rss_guard()
        geometry._write_record(stage / "junction.json", record)
        stage.rename(target)
    return target
