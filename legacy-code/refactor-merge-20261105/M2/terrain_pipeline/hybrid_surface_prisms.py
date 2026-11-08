"""Saved native half-arm prism construction and complete canonical witnesses."""
from fractions import Fraction
import math
import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import triangulate, unary_union
from terrain_pipeline.hybrid_cave_geometry import manifold_from_record, mesh_record
from terrain_pipeline.hybrid_geometry_common import TOLERANCE_M, MAX_TRIANGLES, guard
from terrain_pipeline.hybrid_river_graph import identity


POLICY = {
    "version": "saved-native-halfarm-prism-composition-v1",
    "operation": "original_sampled_rock_minus_union_immutable_gallery_and_surface_prisms",
    "floor": "saved_native_patch_bilinear_minus_saved_affine_cut_at_vertices_piecewise_planar",
    "entity_domain": "original_saved_native_patch_polygon_authority_including_recorded_clip_roundoff_not_resnapped_fan",
    "canonical": "whole_original_native_piece_linear_boundary_match_not_four_point_only",
    "approximation": "not_native_exact_not_fine15_material_no_resampling_or_double_depth_cut",
    "top": "explicit_common_horizontal_cap_above_all_saved_rock_and_gallery_vertices",
    "material": "original_removed_plus_disjoint_extra_removed_equals_total_no_fill",
    "portal": "full_supported_shared_interface_and_exact_unblocked_polygon_offsets_diagnostic_only",
    "hydraulics": "not_solved_no_discharge_or_resistance_law_acceptance",
}


def exact_depth(fan, point):
    vertices = fan["vertices_xz_m"]
    if any(not math.isfinite(depth) or not 0. <= depth <= 4. for depth in fan["depth_at_vertices_m"]):
        raise ValueError("strict_invalid_saved_vertex_depth")
    for vertex, depth in zip(vertices, fan["depth_at_vertices_m"]):
        if list(point) == vertex:
            if not 0. <= depth <= 4.:
                raise ValueError("strict_invalid_saved_vertex_depth")
            return float(depth)
    coordinates = [[Fraction(float(value)) for value in vertex] for vertex in vertices]
    query = [Fraction(float(value)) for value in point]
    first = [coordinates[1][axis] - coordinates[0][axis] for axis in range(2)]
    second = [coordinates[2][axis] - coordinates[0][axis] for axis in range(2)]
    relative = [query[axis] - coordinates[0][axis] for axis in range(2)]
    determinant = first[0] * second[1] - first[1] * second[0]
    if determinant == 0:
        raise ValueError("degenerate_saved_native_fan")
    weight_first = (relative[0] * second[1] - relative[1] * second[0]) / determinant
    weight_second = (first[0] * relative[1] - first[1] * relative[0]) / determinant
    weights = [1 - weight_first - weight_second, weight_first, weight_second]
    if min(weights) < 0:
        raise ValueError("point_outside_exact_saved_fan")
    depth = math.fsum(float(weight) * value for weight, value in zip(weights, fan["depth_at_vertices_m"]))
    if not 0. <= depth <= 4.:
        raise ValueError("strict_negative_or_maxcut_depth_no_clamp")
    return depth


def native_height(patch, point):
    origin = patch["patch_origin_m_xz"]
    spacing = patch["native_spacing_m"]
    if not math.isfinite(spacing) or spacing <= 0:
        raise ValueError("invalid_native_patch_spacing")
    local = (np.asarray(point) - origin) / spacing
    coefficients = patch["bilinear_coefficients_m"]
    return float(coefficients[0] + coefficients[1] * local[0] + coefficients[2] * local[1]
        + coefficients[3] * local[0] * local[1])


def saved_patch_depth(fan, point):
    if any(not math.isfinite(depth) or not 0. <= depth <= 4. for depth in fan["depth_at_vertices_m"]):
        raise ValueError("strict_invalid_saved_vertex_depth")
    for vertex, depth in zip(fan["vertices_xz_m"], fan["depth_at_vertices_m"]):
        if list(point) == vertex:
            return float(depth)
    coefficients = fan["depth_coefficients_m_1xz"]
    relative = np.asarray(point) - fan["depth_origin_xz_m"]
    depth = math.fsum([coefficients[0], coefficients[1] * relative[0], coefficients[2] * relative[1]])
    if not math.isfinite(depth) or not 0. <= depth <= 4.:
        raise ValueError("strict_saved_patch_affine_depth_no_clamp")
    return float(depth)


def triangular_prism(bottom_xyz, cap_y, origin):
    bottom = np.asarray(bottom_xyz, dtype=float)
    if bottom.shape != (3, 3) or not np.isfinite(bottom).all() or cap_y <= bottom[:, 1].max():
        raise ValueError("invalid_surface_prism_floor_or_cap")
    if Polygon(bottom[:, [0, 2]]).area <= 0:
        raise ValueError("degenerate_surface_prism_projection")
    top = bottom.copy()
    top[:, 1] = cap_y
    vertices = np.vstack((bottom, top)) - origin
    triangles = [[0, 2, 1], [3, 4, 5], [0, 1, 4], [0, 4, 3],
        [1, 2, 5], [1, 5, 4], [2, 0, 3], [2, 3, 5]]
    return mesh_record(vertices, triangles, origin, "surface_half_arm_closed_triangular_prism")


def half_arm_prisms(node, attachment, cap_y, origin):
    if node["status"] != "candidate" or node["rejection_reasons"]:
        raise ValueError("original_surface_node_not_accepted_candidate")
    ids = attachment["half_arm_triangle_indices"]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("missing_or_duplicate_original_half_arm_triangles")
    wanted = {"shared:" + node["node_id"] + ":" + str(ordinal) for ordinal in ids}
    for ordinal in ids:
        if not isinstance(ordinal, int) or not 0 <= ordinal < len(node["geometry"]["triangles"]):
            raise ValueError("invalid_original_half_arm_triangle_reference")
        role = node["geometry"]["triangle_roles"][ordinal]
        if role["region"] != "half_arm" or role["arc_id"] != attachment["actual_complete_port_proof"]["arc_id"]:
            raise ValueError("half_arm_source_role_or_actual_arc_mismatch")
    compact = {fan["fan_key"]: fan for fan in attachment["compact_native_fans"]}
    functions = [function for function in node["source_functions"] if function["triangle_id"] in wanted]
    if {function["triangle_id"] for function in functions} != wanted:
        raise ValueError("incomplete_original_half_arm_function_sources")
    bottoms, solids = [], []
    for function in functions:
        if function["status"] != "candidate" or function["rejection_reasons"]:
            raise ValueError("refused_original_half_arm_function")
        for source_fan in function["fans"]:
            fan = compact.get(source_fan["fan_id"])
            if fan is None or any(fan[key] != source_fan[key] for key in
                    ("vertices_xz_m", "depth_at_vertices_m", "depth_coefficients_m_1xz", "depth_origin_xz_m")):
                raise ValueError("compact_and_original_native_fan_mismatch")
            polygon = Polygon(fan["vertices_xz_m"])
            patches = source_fan["native_patches"]
            domains = [Polygon(patch["polygon_xz_m"]) for patch in patches]
            if (not polygon.is_valid or any(not domain.is_valid for domain in domains)
                    or polygon.symmetric_difference(unary_union(domains)).area > 1e-8
                    or abs(sum(domain.area for domain in domains) - polygon.area) > 1e-8):
                raise ValueError("native_patch_domain_gap_or_overlap")
            for patch, domain in zip(patches, domains):
                triangles = [triangle for triangle in triangulate(domain) if domain.covers(triangle)]
                if abs(sum(triangle.area for triangle in triangles) - domain.area) > 1e-8:
                    raise ValueError("whole_native_patch_triangulation_gap")
                for triangle in triangles:
                    horizontal = [list(point) for point in list(triangle.exterior.coords)[:3]]
                    depths = [saved_patch_depth(fan, point) for point in horizontal]
                    domain_witnesses = []
                    for point in horizontal:
                        try:
                            exact_depth(fan, point)
                            inside = True
                        except ValueError as error:
                            if str(error) != "point_outside_exact_saved_fan":
                                raise
                            inside = False
                        domain_witnesses.append({"point_xz_m": point, "inside_original_fan_exact_domain": inside,
                            "entity_domain_authority": "original_saved_native_patch_polygon",
                            "clip_point_not_snapped": True})
                    bottom = [[point[0], native_height(patch, point) - depth, point[1]]
                        for point, depth in zip(horizontal, depths)]
                    prism = triangular_prism(bottom, cap_y, origin)
                    solids.append(manifold_from_record(prism))
                    bottoms.append({"bottom_triangle_id": len(bottoms), "triangle_id": function["triangle_id"],
                        "fan_key": fan["fan_key"], "source_function_identity_sha256": function["identity_sha256"],
                        "bottom_vertices_xyz_m": bottom, "depth_at_vertices_m": depths,
                        "saved_native_patch": patch, "saved_affine_fan": source_fan,
                        "saved_patch_vertex_domain_witnesses": domain_witnesses,
                        "prism": prism, "prism_triangle_roles": ["floor", "artificial_top_cap"] + ["lateral"] * 6,
                        "bilinear_interior_is_planar_approximation": True,
                        "conservative_interior_height_error_bound_m": float(abs(patch["bilinear_coefficients_m"][3])
                            * np.ptp(np.asarray(horizontal)[:, 0]) * np.ptp(np.asarray(horizontal)[:, 1])
                            / patch["native_spacing_m"]**2)})
    if not bottoms or sum(len(item["prism"]["triangles"]) for item in bottoms) > MAX_TRIANGLES:
        raise ValueError("whole_surface_prism_budget_or_missing_sources")
    guard()
    return bottoms, solids


def canonical_boundary_witness(attachment, bottoms, ring, flow, kind):
    proof = attachment["actual_complete_port_proof"]
    if not proof["segments"] or not attachment["half_arm_triangle_indices"]:
        raise ValueError("missing_complete_original_port_proof")
    origin = np.asarray(ring[0], dtype=float)[[0, 2]]
    normal = np.asarray(flow, dtype=float)
    normal /= np.linalg.norm(normal)
    side = -1. if kind == "sink" else 1.
    witnesses = []
    for segment in proof["segments"]:
        for piece in segment["pieces"]:
            expected = piece["bed_coefficients_m_t012"]
            if expected[2] != 0.:
                raise ValueError("quadratic_canonical_requires_exact_new_geometry")
            start, end = np.asarray(piece["start_xz_m"]), np.asarray(piece["end_xz_m"])
            vector = end - start
            length = float(np.linalg.norm(vector))
            if length <= TOLERANCE_M:
                raise ValueError("degenerate_canonical_piece")
            intervals = []
            for bottom in bottoms:
                vertices = np.asarray(bottom["bottom_vertices_xyz_m"])
                for first, second in zip(vertices, np.roll(vertices, -1, axis=0)):
                    horizontal = np.array([first[[0, 2]], second[[0, 2]]])
                    fractions = (horizontal - start) @ vector / (length * length)
                    distances = np.linalg.norm(horizontal - (start + fractions[:, None] * vector), axis=1)
                    if max(distances) > TOLERANCE_M or abs(fractions[1] - fractions[0]) * length <= TOLERANCE_M:
                        continue
                    lower, upper = max(0., float(min(fractions))), min(1., float(max(fractions)))
                    if (upper - lower) * length <= TOLERANCE_M:
                        continue
                    slope = float((second[1] - first[1]) / (fractions[1] - fractions[0]))
                    intercept = float(first[1] - slope * fractions[0])
                    error = max(abs(intercept - expected[0]), abs(intercept + slope - expected[0] - expected[1]))
                    if error > TOLERANCE_M:
                        raise ValueError("whole_canonical_piece_floor_mismatch")
                    signed = side * ((vertices[:, [0, 2]] - origin) @ normal)
                    if min(signed) < -TOLERANCE_M or max(signed) <= TOLERANCE_M:
                        raise ValueError("surface_port_support_not_actual_exterior_half_arm")
                    intervals.append({"interval_t01": [lower, upper], "bottom_triangle_id": bottom["bottom_triangle_id"],
                        "fan_key": bottom["fan_key"], "edge_xyz_m": [first.tolist(), second.tolist()],
                        "actual_bed_coefficients_m_t012": [intercept, slope, 0.],
                        "maximum_whole_linear_error_m": error, "exterior_support_distance_m": float(max(signed))})
            cursor = 0.
            for item in sorted(intervals, key=lambda value: value["interval_t01"]):
                lower, upper = item["interval_t01"]
                if (lower - cursor) * length > TOLERANCE_M:
                    raise ValueError("canonical_whole_piece_boundary_gap")
                cursor = max(cursor, upper)
            if (1. - cursor) * length > TOLERANCE_M:
                raise ValueError("canonical_whole_piece_boundary_missing")
            witnesses.append({"original_piece": piece, "full_interval_t01": [0., 1.], "supports": intervals})
    floor = LineString([np.asarray(point)[[0, 2]] for point in ring])
    original = LineString([np.asarray(point)[[0, 2]] for point in proof["original_profile_xyz_m"]])
    if floor.hausdorff_distance(original) > TOLERANCE_M:
        raise ValueError("immutable_gallery_floor_horizontal_port_mismatch")
    return witnesses
