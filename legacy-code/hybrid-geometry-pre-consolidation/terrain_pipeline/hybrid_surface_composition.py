"""Cut-only surface half-arm prisms coupled to immutable saved cave geometry."""

from fractions import Fraction
import math

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import triangulate, unary_union

from terrain_pipeline.hybrid_cave_geometry import manifold_from_record, mesh_record, save_manifold
from terrain_pipeline.hybrid_river_faces import guard, plane_frame, seal, slice_solid
from terrain_pipeline.hybrid_river_graph import identity

SCHEMA = "td-hybrid-surface-composition-v1"
MAX_BYTES = 64 * 1024**2
MAX_TRIANGLES = 200000
TOLERANCE_M = 1e-8
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
POLICY_SHA256 = identity(POLICY)


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


def volume_ledger(before, old_after, old_removed, after, removed, extra):
    values = {"original_rock_before_m3": float(before.volume()), "original_removed_m3": float(old_removed.volume()),
        "original_rock_after_m3": float(old_after.volume()), "total_removed_m3": float(removed.volume()),
        "extra_removed_m3": float(extra.volume()), "new_rock_after_m3": float(after.volume()), "fill_m3": 0.}
    residuals = [values["original_rock_before_m3"] - values["original_rock_after_m3"] - values["original_removed_m3"],
        values["original_rock_before_m3"] - values["new_rock_after_m3"] - values["total_removed_m3"],
        values["total_removed_m3"] - values["original_removed_m3"] - values["extra_removed_m3"]]
    tolerance = max(1e-7, values["original_rock_before_m3"] * 1e-10)
    if max(map(abs, residuals)) > tolerance:
        raise ValueError("signed_original_total_extra_material_balance_failed")
    values.update(signed_residuals_m3=residuals, residual_tolerance_m3=tolerance,
        fine15_material_replaced=False, sampled_solid_material_not_native_exact=True)
    return values


def saved_sampling_mismatch_witnesses(sampling, attachments, ports):
    witnesses = []
    for kind in ("sink", "spring"):
        attachment = attachments["attachments"][kind]
        triangle_ids = {"shared:" + fan["node_id"] + ":" + str(ordinal)
            for fan in attachment["compact_native_fans"][:1] for ordinal in attachment["half_arm_triangle_indices"]}
        fans = [fan for fan in attachment["compact_native_fans"] if fan["triangle_id"] in triangle_ids]
        midpoint = np.asarray(ports[kind]["midpoint_xz_m"])
        flow = np.asarray(ports[kind]["flow_unit_xz"])
        for sample in sampling["samples"]:
            point = sample["xz_m"]
            if abs(float((np.asarray(point) - midpoint) @ flow)) > TOLERANCE_M:
                continue
            hits = []
            for fan in fans:
                vertices = np.asarray(fan["vertices_xz_m"])
                if np.any(np.asarray(point) < vertices.min(axis=0)) or np.any(np.asarray(point) > vertices.max(axis=0)):
                    continue
                try:
                    depth = exact_depth(fan, point)
                except ValueError as error:
                    if str(error) == "point_outside_exact_saved_fan":
                        continue
                    raise
                hits.append({"fan_key": fan["fan_key"], "exact_domain_cut_depth_m": depth,
                    "saved_vertices_xz_m": fan["vertices_xz_m"], "saved_vertex_depths_m": fan["depth_at_vertices_m"]})
            if not hits:
                continue
            depths = [hit["exact_domain_cut_depth_m"] for hit in hits]
            if max(depths) - min(depths) > 1e-9:
                raise ValueError("independent_exact_saved_fan_shared_depth_mismatch")
            if abs(depths[0] - sample["cut_depth_m"]) > 1e-9:
                witnesses.append({"kind": kind, "source_sampling_row": sample["row"], "source_sampling_column": sample["column"],
                    "point_xz_m": point, "saved_cut_depth_m": sample["cut_depth_m"], "saved_fan_keys": sample["fan_keys"],
                    "saved_derived_bed_m": sample["derived_bed_m"], "saved_original_source_sample": sample["source_sample"],
                    "exact_domain_supports": hits, "expected_cut_depth_m": depths[0],
                    "sampled_top_excess_height_m": depths[0] - sample["cut_depth_m"],
                    "classification": "saved_cut_lookup_mismatch_exact_domain_not_source_height_recalculation",
                    "scope": "only_saved_port_plane_grid_samples_no_global_source_claim"})
    return witnesses


def build_composition(geometry, vdm, attachments, ports, meshes, nodes, sampling):
    import manifold3d as manifold
    origin = np.asarray(meshes["rock_before"]["local_origin_xyz_m"], dtype=float)
    if any(record["local_origin_xyz_m"] != origin.tolist() for record in meshes.values()):
        raise ValueError("saved_mesh_common_local_origin_mismatch")
    immutable_vertices = np.array([station["derived_ring_xyz_m"] for station in vdm["stations"]]).reshape(-1, 3) - origin
    if (not np.array_equal(immutable_vertices, np.asarray(meshes["cutter"]["vertices_local_xyz_m"]))
            or vdm["triangles"] != meshes["cutter"]["triangles"]):
        raise ValueError("immutable_vdm_original_cutter_array_mismatch")
    cap_y = max(max(point[1] for point in meshes[name]["vertices_local_xyz_m"]) + origin[1]
        for name in ("rock_before", "cutter")) + 10.
    surface_solids, surface_records, connections = [], {}, {}
    for kind, ordinal in (("sink", 0), ("spring", len(vdm["stations"]) - 1)):
        attachment = attachments["attachments"][kind]
        bottoms, solids = half_arm_prisms(nodes[kind], attachment, cap_y, origin)
        station = vdm["stations"][ordinal]
        floor_ring = station["derived_ring_xyz_m"][:station["floor_vertex_count"]]
        witnesses = canonical_boundary_witness(attachment, bottoms, floor_ring, ports[kind]["flow_unit_xz"], kind)
        surface_records[kind] = {"node_id": nodes[kind]["node_id"], "node_pin": attachment["surface_node_pin"],
            "half_arm_triangle_indices": attachment["half_arm_triangle_indices"], "bottom_triangles": bottoms,
            "immutable_gallery_station_index": ordinal, "immutable_gallery_ring_xyz_m": station["derived_ring_xyz_m"],
            "canonical_whole_piece_witnesses": witnesses}
        surface_solids.extend(solids)
        connections[kind] = {"canonical_whole_piece_witnesses": witnesses,
            "immutable_gallery_station_index": ordinal, "original_complete_port_proof": attachment["actual_complete_port_proof"],
            "full_shared_interface_supported": True, "offset_traces_are_diagnostic_only": True}
    surface = manifold.Manifold.batch_boolean(surface_solids, manifold.OpType.Add)
    before, cutter, old_after, old_removed = (manifold_from_record(meshes[name])
        for name in ("rock_before", "cutter", "rock_after", "removed"))
    coupled = cutter + surface
    after, removed, extra = before - coupled, before ^ coupled, old_after ^ surface
    for solid in (surface, coupled, after, removed, extra):
        if solid.status() != manifold.Error.NoError:
            raise ValueError("surface_composition_boolean_failed")
    if any(solid.is_empty() for solid in (surface, coupled, after, removed)):
        raise ValueError("missing_surface_composition_solid")
    component_count = len(coupled.decompose())
    if component_count != 1:
        raise ValueError("surface_gallery_coupled_cutter_not_one_component")
    artifacts = {"surface_cutter": save_manifold(surface, origin, "surface_cutter"),
        "coupled_cutter": save_manifold(coupled, origin, "coupled_cutter"),
        "rock_after": save_manifold(after, origin, "rock_after"), "removed": save_manifold(removed, origin, "total_removed")}
    if extra.is_empty():
        artifacts["extra_removed"] = seal({"schema": "td-hybrid-empty-solid-v1", "role": "extra_removed",
            "local_origin_xyz_m": origin.tolist(), "vertices_local_xyz_m": [], "triangles": [], "signed_volume_m3": 0.})
    else:
        artifacts["extra_removed"] = save_manifold(extra, origin, "extra_removed")
    for name, record in artifacts.items():
        if len(record["triangles"]) > MAX_TRIANGLES:
            raise ValueError("whole_composition_triangle_budget_exceeded")
    solids = {"coupled_cutter": coupled, "rock_after": after, "removed": removed}
    for kind, ordinal in (("sink", 0), ("spring", len(vdm["stations"]) - 1)):
        station = vdm["stations"][ordinal]
        normal = ports[kind]["flow_unit_xz"]
        frame = plane_frame(station["origin_xyz_m"], normal, origin)
        diagnostics, shapes = {}, {}
        for name, solid in solids.items():
            mesh = solid.to_mesh64()
            record, shape = slice_solid((solid, np.array(mesh.vert_properties[:, :3]), np.array(mesh.tri_verts)), frame,
                {"artifact": name})
            diagnostics[name], shapes[name] = record, shape
        gallery_ring = np.asarray(station["derived_ring_xyz_m"])
        horizontal = (gallery_ring[:, [0, 2]] - np.asarray(station["origin_xyz_m"])[[0, 2]]) @ np.asarray(frame["transverse_unit_xz"])
        aperture = Polygon(np.column_stack((horizontal, gallery_ring[:, 1] - origin[1])))
        blocked = float(aperture.intersection(shapes["rock_after"]).area)
        missing = float(aperture.difference(shapes["coupled_cutter"]).area)
        if not aperture.is_valid or blocked > 1e-8 or missing > 1e-8:
            raise ValueError("actual_full_canonical_port_blocked_or_missing:" + kind)
        epsilon = min(.001, min(item["exterior_support_distance_m"] for witness in
            connections[kind]["canonical_whole_piece_witnesses"] for item in witness["supports"]) / 16.)
        basis = np.array([frame["transverse_unit_xyz"], frame["vertical_unit_xyz"], frame["normal_local_xyz"]]).T
        bounds = aperture.bounds
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        center = np.array(frame["origin_local_xyz_m"]) + np.array(frame["transverse_unit_xyz"]) * ((bounds[0] + bounds[2]) / 2.)
        center[1] = (bounds[1] + bounds[3]) / 2.
        half_collars, collar_proofs = [], {}
        surface_sign = -1. if kind == "sink" else 1.
        for side_name, side_solid, sign in (("surface", surface, surface_sign), ("gallery", cutter, -surface_sign)):
            slab_center = center + sign * epsilon / 2. * np.array(frame["normal_local_xyz"])
            slab = manifold.Manifold.cube([width, height, epsilon], center=True).transform(
                np.column_stack((basis, slab_center)).tolist())
            collar = side_solid ^ slab
            if collar.is_empty() or collar.volume() <= 0 or len(collar.decompose()) != 1:
                raise ValueError("missing_positive_volume_full_port_collar:" + kind + ":" + side_name)
            mesh = collar.to_mesh64()
            collar_slice, collar_domain = slice_solid((collar, np.array(mesh.vert_properties[:, :3]),
                np.array(mesh.tri_verts)), frame, {"artifact": kind + "_" + side_name + "_collar"})
            uncovered = float(aperture.difference(collar_domain).area)
            if uncovered > 1e-8:
                raise ValueError("whole_port_not_covered_by_both_volume_collars:" + kind + ":" + side_name)
            name = kind + "_" + side_name + "_collar"
            artifacts[name] = save_manifold(collar, origin, name)
            collar_proofs[side_name] = {"artifact": name, "positive_volume_m3": float(collar.volume()),
                "whole_aperture_uncovered_area_m2": uncovered, "interface_solid_slice": collar_slice,
                "source_solid": "surface_cutter" if side_name == "surface" else "original_cutter",
                "normal_side_sign": sign, "slab_width_height_depth_m": [width, height, epsilon],
                "slab_transform_3x4": np.column_stack((basis, slab_center)).tolist()}
            half_collars.append(collar)
        connected_collar = half_collars[0] + half_collars[1]
        rock_overlap = float((connected_collar ^ after).volume())
        if len(connected_collar.decompose()) != 1 or rock_overlap > 1e-7:
            raise ValueError("actual_full_port_volume_collar_disconnected_or_blocked:" + kind)
        artifacts[kind + "_connected_collar"] = save_manifold(connected_collar, origin, kind + "_connected_collar")
        traces = []
        for offset in (-epsilon, -epsilon / 2., epsilon / 2., epsilon):
            displaced = np.asarray(station["origin_xyz_m"]) + offset * np.asarray(frame["normal_local_xyz"])
            shifted_frame = plane_frame(displaced, normal, origin)
            trace = {"offset_m": offset, "plane": shifted_frame, "solid_slices": {}}
            for name, solid in solids.items():
                mesh = solid.to_mesh64()
                record, _ = slice_solid((solid, np.array(mesh.vert_properties[:, :3]), np.array(mesh.tri_verts)), shifted_frame,
                    {"artifact": name})
                trace["solid_slices"][name] = record
            traces.append(trace)
        connections[kind].update(plane=frame, exact_solid_slices=diagnostics, one_sided_diagnostic_traces=traces,
            epsilon_rule="min_1mm_and_minimum_actual_exterior_support_distance_div16",
            gallery_aperture_uv_m=list(map(list, aperture.exterior.coords))[:-1],
            exact_blocked_area_m2=blocked, exact_missing_cutter_area_m2=missing,
            positive_volume_connection={"sides": collar_proofs, "connected_collar_artifact": kind + "_connected_collar",
                "component_count": 1, "actual_rock_overlap_volume_m3": rock_overlap,
                "constructed_by_intersecting_actual_cutters_not_new_excavation": True},
            hydraulic_boundary_certified=False)
    artifacts["surface_prisms"] = seal({"schema": "td-hybrid-surface-prisms-v1", "common_local_origin_xyz_m": origin.tolist(),
        "cap_y_world_m": cap_y, "cap_above_saved_rock_and_gallery_margin_m": 10., "half_arms": surface_records,
        "bottom_semantics": POLICY["floor"], "native_exact": False})
    result = seal({"schema": SCHEMA, "status": "candidate_unverified", "rejection_reasons": [],
        "policy": POLICY, "policy_identity_sha256": POLICY_SHA256, "geometry_identity_sha256": geometry["identity_sha256"],
        "graph_identity_sha256": geometry["graph_identity_sha256"], "portal_connections": connections,
        "coupled_cutter_component_count": component_count, "material": volume_ledger(before, old_after, old_removed, after, removed, extra),
        "original_source_sampling_cut_lookup_mismatches": saved_sampling_mismatch_witnesses(sampling, attachments, ports),
        "original_sampled_rock_retained_cut_only_not_source_resampling": True,
        "vdm_moved": False, "ports_moved": False, "fill_generated": False, "native_exact": False,
        "fine15_replaced": False, "independent_audit_passed": False, "hydraulic_ready": False, "hydraulic_solved": False,
        "full_network_verified": False, "actual_peak_rss_bytes": guard()})
    return result, artifacts
