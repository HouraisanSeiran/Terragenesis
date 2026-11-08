"""Independent saved surface-carve source, material and port-volume audit."""

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.hybrid_cave_saved_audit import Solid, manifold_library
from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, check_identity, checked_path, check_memory, compare, digest, file_sha256, load_native, read, read_audit, require)
from tools.audit_hybrid_river_faces import audit_slice, check_plane

AUDIT_SCHEMA = "td-hybrid-surface-composition-independent-audit-v1"
GEOMETRY_SHA256 = "3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593"
GEOMETRY_AUDIT_SHA256 = "703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364"
FROZEN_COMPOSITION_CODE = {
    "terrain_pipeline/hybrid_surface_composition.py": "0a9b424ca1994d150c8bf6c3cb90c2ce8c263cd5ca78cace24134242b02c5dd3",
    "tools/prepare_hybrid_surface_composition.py": "93e50dec6ac93cbda8396fb2b344fd40204a1c72942c944a17e0ecd698bafff8",
    "tests/test_hybrid_surface_composition.py": "5df84c0c6c5cfb17b83c1f25cfc3819ee7c221c9b850d5d62dfbcaf443bc0ae7"}
POLICY = {"version": "saved-native-halfarm-prism-composition-v1",
    "operation": "original_sampled_rock_minus_union_immutable_gallery_and_surface_prisms",
    "floor": "saved_native_patch_bilinear_minus_saved_affine_cut_at_vertices_piecewise_planar",
    "entity_domain": "original_saved_native_patch_polygon_authority_including_recorded_clip_roundoff_not_resnapped_fan",
    "canonical": "whole_original_native_piece_linear_boundary_match_not_four_point_only",
    "approximation": "not_native_exact_not_fine15_material_no_resampling_or_double_depth_cut",
    "top": "explicit_common_horizontal_cap_above_all_saved_rock_and_gallery_vertices",
    "material": "original_removed_plus_disjoint_extra_removed_equals_total_no_fill",
    "portal": "full_supported_shared_interface_and_exact_unblocked_polygon_offsets_diagnostic_only",
    "hydraulics": "not_solved_no_discharge_or_resistance_law_acceptance"}


class EmptySolid:
    def manifold(self, library):
        return library.Manifold()


def exact_fan_cut(fan, point):
    points = fan["vertices_xz_m"]
    depths = fan["depth_at_vertices_m"]
    require(len(points) == 3 and all(len(vertex) == 2 for vertex in points) and len(point) == 2
            and len(depths) == 3 and all(math.isfinite(value) for vertex in points for value in vertex)
            and all(math.isfinite(value) for value in point)
            and all(math.isfinite(value) and 0 <= value <= 4 for value in depths), "invalid saved fan inputs")
    exact_points = [[Fraction.from_float(float(value)) for value in vertex] for vertex in points]
    target = [Fraction.from_float(float(value)) for value in point]
    first = [exact_points[1][axis] - exact_points[0][axis] for axis in (0, 1)]
    second = [exact_points[2][axis] - exact_points[0][axis] for axis in (0, 1)]
    offset = [target[axis] - exact_points[0][axis] for axis in (0, 1)]
    determinant = first[0] * second[1] - first[1] * second[0]
    require(determinant != 0, "degenerate saved fan domain")
    weight_first = (offset[0] * second[1] - offset[1] * second[0]) / determinant
    weight_second = (first[0] * offset[1] - first[1] * offset[0]) / determinant
    weights = [1 - weight_first - weight_second, weight_first, weight_second]
    if min(weights) < 0:
        return None
    value = sum(weight * Fraction.from_float(float(depth)) for weight, depth in zip(weights, depths))
    require(0 <= value <= 4, "strict exact fan cut depth invalid")
    return float(value)


def saved_patch_affine_depth(fan, point):
    require(all(math.isfinite(depth) and 0 <= depth <= 4 for depth in fan["depth_at_vertices_m"]),
            "invalid original fan vertex depths")
    for vertex, depth in zip(fan["vertices_xz_m"], fan["depth_at_vertices_m"]):
        if np.array_equal(vertex, point):
            return float(depth)
    coefficients = fan["depth_coefficients_m_1xz"]
    offset = np.asarray(point, float) - np.asarray(fan["depth_origin_xz_m"], float)
    value = math.fsum((coefficients[0], coefficients[1] * offset[0], coefficients[2] * offset[1]))
    require(math.isfinite(value) and 0 <= value <= 4, "strict original patch affine depth invalid; no clamp")
    return value


def volume_difference(first, second):
    return float((first - second).volume() + (second - first).volume())


def audit_material_solids(original_rock, old_after, old_removed, surface_cutter, combined_cutter,
                          actual_after, extra_removed, total_removed, gallery_cutter):
    library = manifold_library()
    solids = [solid.manifold(library) for solid in (original_rock, old_after, old_removed, surface_cutter,
              combined_cutter, actual_after, extra_removed, total_removed, gallery_cutter)]
    rock, previous, previous_removed, surface, combined, actual, extra, total, gallery = solids
    tolerance = max(1e-7, rock.volume() * 1e-10)
    require(volume_difference(previous, rock - gallery) <= tolerance
            and volume_difference(previous_removed, rock ^ gallery) <= tolerance, "original saved rock/cave material mismatch")
    require(volume_difference(combined, gallery + surface) <= tolerance, "combined cutter not actual gallery/surface union")
    require(volume_difference(actual, rock - combined) <= tolerance, "actual rock not original minus combined cutter")
    require(volume_difference(total, rock ^ combined) <= tolerance, "total removed not actual original rock intersection")
    require(volume_difference(extra, previous - actual) <= tolerance
            and volume_difference(extra, previous ^ surface) <= tolerance, "extra removed not newly cut old remaining rock")
    fill = float((actual - previous).volume())
    overlap = float((previous_removed ^ extra).volume())
    residual = float(total.volume() - previous_removed.volume() - extra.volume())
    require(fill <= tolerance and overlap <= tolerance and abs(residual) <= tolerance
            and volume_difference(total, previous_removed + extra) <= tolerance,
            "fill/overlapping extra/original-plus-extra material mismatch")
    check_memory()
    return {"original_removed_m3": previous_removed.volume(), "extra_removed_m3": extra.volume(),
            "total_removed_m3": total.volume(), "signed_increment_residual_m3": residual,
            "actual_added_rock_difference_m3": fill, "old_extra_overlap_m3": overlap,
            "independent_boolean_verified": True, "comparison_tolerance_m3": tolerance}


def source_patch_height(patch, point, native):
    row, column = patch["patch_row_column"]
    require(type(row) is int and type(column) is int and 0 <= row < native.height.shape[0] - 1
            and 0 <= column < native.height.shape[1] - 1, "invalid native source patch index")
    origin = native.origin + np.asarray([column, row]) * native.spacing
    heights = [float(native.height[row, column]), float(native.height[row, column + 1]),
               float(native.height[row + 1, column]), float(native.height[row + 1, column + 1])]
    coefficients = [heights[0], heights[1] - heights[0], heights[2] - heights[0],
                    heights[3] - heights[1] - heights[2] + heights[0]]
    compare(patch["patch_origin_m_xz"], origin, "original native patch origin", atol=1e-9)
    require(patch["native_spacing_m"] == native.spacing, "native source spacing changed")
    compare(patch["native_height_m"], heights, "native original patch heights", atol=0.)
    compare(patch["bilinear_coefficients_m"], coefficients, "native bilinear whole coefficients", atol=1e-12)
    columns = native.height.shape[1]
    require(patch["native_cell_ids"] == [row * columns + column, row * columns + column + 1,
            (row + 1) * columns + column, (row + 1) * columns + column + 1], "native patch provenance differs")
    position = (np.asarray(point, float) - origin) / native.spacing
    require(np.all(position >= 0) and np.all(position <= 1), "prism vertex outside saved native patch")
    sample = native.sample(point)
    require(not sample["rejection_reasons"] and not sample["wet_source_support"]
            and sample["height_m"] is not None, "prism source wet/protected/unknown/unselected")
    return float(coefficients[0] + coefficients[1] * position[0] + coefficients[2] * position[1]
                 + coefficients[3] * position[0] * position[1])


def audit_prisms(saved, attachments, vdm, native, origin, meshes):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    require(saved["schema"] == "td-hybrid-surface-prisms-v1" and saved["native_exact"] is False
            and saved["bottom_semantics"] == POLICY["floor"] and set(saved["half_arms"]) == {"sink", "spring"},
            "changed prism source/approximation contract")
    compare(saved["common_local_origin_xyz_m"], origin, "prism shared local origin", atol=0.)
    expected_cap = max(float(meshes[role].vertices[:, 1].max() + origin[1]) for role in ("rock_before", "original_cutter")) + 10.
    require(saved["cap_y_world_m"] == expected_cap and saved["cap_above_saved_rock_and_gallery_margin_m"] == 10.,
            "surface cutter cap not fixed above actual original solids")
    library = manifold_library()
    records, all_prisms, reports = {}, [], {}
    expected_faces = {tuple(sorted(face)) for face in ((0, 2, 1), (3, 4, 5), (0, 1, 4), (0, 4, 3),
                      (1, 2, 5), (1, 5, 4), (2, 0, 3), (2, 3, 5))}
    for kind, ordinal in (("sink", 0), ("spring", len(vdm["stations"]) - 1)):
        half = saved["half_arms"][kind]
        attachment = attachments["attachments"][kind]
        node = read(attachment["surface_node_pin"])
        wanted = {"shared:" + node["node_id"] + ":" + str(index) for index in attachment["half_arm_triangle_indices"]}
        functions = {item["triangle_id"]: item for item in node["source_functions"] if item["triangle_id"] in wanted}
        require(set(functions) == wanted and node["status"] == "candidate" and not node["rejection_reasons"]
                and half["node_id"] == node["node_id"] and half["node_pin"] == attachment["surface_node_pin"]
                and half["half_arm_triangle_indices"] == attachment["half_arm_triangle_indices"]
                and half["immutable_gallery_station_index"] == ordinal
                and half["immutable_gallery_ring_xyz_m"] == vdm["stations"][ordinal]["derived_ring_xyz_m"],
                "original whole half-arm/immutable gallery sources differ")
        expected = {}
        for function in functions.values():
            check_identity(function)
            require(function["status"] == "candidate" and not function["rejection_reasons"], "refused original source function")
            for fan in function["fans"]:
                require(fan["fan_id"] not in expected, "duplicate original fan")
                compact = next((item for item in attachment["compact_native_fans"] if item["fan_key"] == fan["fan_id"]), None)
                require(compact is not None and all(compact[key] == fan[key] for key in
                        ("vertices_xz_m", "depth_at_vertices_m", "depth_coefficients_m_1xz", "depth_origin_xz_m")),
                        "original native/compact affine fan mismatch")
                domains = [Polygon(patch["polygon_xz_m"]) for patch in fan["native_patches"]]
                require(all(domain.is_valid and domain.area > 0 for domain in domains)
                        and Polygon(fan["vertices_xz_m"]).symmetric_difference(unary_union(domains)).area <= 1e-8,
                        "original native patch coverage differs from fan domain")
                expected[fan["fan_id"]] = (function, fan)
        coverage = {}
        own = []
        bottoms = half["bottom_triangles"]
        require(bottoms and [item["bottom_triangle_id"] for item in bottoms] == list(range(len(bottoms)))
                and len(bottoms) * 8 <= 200000, "invalid bounded prism triangle census")
        maximum_approximation = 0.
        maximum_bilinear_bound = 0.
        outside_vertex_count = 0
        for item in bottoms:
            require(item["fan_key"] in expected, "surface cutter uses non-half-arm source")
            function, fan = expected[item["fan_key"]]
            require(item["triangle_id"] == function["triangle_id"]
                    and item["source_function_identity_sha256"] == function["identity_sha256"]
                    and item["saved_affine_fan"] == fan and item["saved_native_patch"] in fan["native_patches"]
                    and item["bilinear_interior_is_planar_approximation"] is True,
                    "prism native/fan function substituted or approximation concealed")
            patch = item["saved_native_patch"]
            patch_index = fan["native_patches"].index(patch)
            bottom = np.asarray(item["bottom_vertices_xyz_m"], float)
            require(bottom.shape == (3, 3) and np.isfinite(bottom).all(), "invalid bottom triangle")
            polygon = Polygon(bottom[:, [0, 2]])
            domain = Polygon(patch["polygon_xz_m"])
            require(polygon.is_valid and polygon.area > 0 and polygon.difference(domain).area <= 1e-10,
                    "bottom triangle outside original native patch")
            coverage.setdefault((item["fan_key"], patch_index), []).append(polygon)
            expected_depths = []
            domain_witnesses = []
            for point in bottom:
                horizontal = point[[0, 2]]
                require(any(np.array_equal(horizontal, vertex) for vertex in patch["polygon_xz_m"]),
                        "prism introduced or snapped a saved patch vertex")
                inside = exact_fan_cut(fan, horizontal) is not None
                outside_vertex_count += int(not inside)
                domain_witnesses.append({"point_xz_m": horizontal.tolist(), "inside_original_fan_exact_domain": inside,
                                         "entity_domain_authority": "original_saved_native_patch_polygon",
                                         "clip_point_not_snapped": True})
                depth = saved_patch_affine_depth(fan, horizontal)
                expected_depths.append(depth)
                compare(point[1], source_patch_height(patch, point[[0, 2]], native) - depth,
                        "prism bottom original native minus cut", atol=1e-9)
            compare(item["depth_at_vertices_m"], expected_depths, "strict original affine depths", atol=1e-12)
            require(item["saved_patch_vertex_domain_witnesses"] == domain_witnesses,
                    "exact original fan domain/patch authority witnesses concealed")
            centroid = bottom.mean(axis=0)
            depth = saved_patch_affine_depth(fan, centroid[[0, 2]])
            deviation = source_patch_height(patch, centroid[[0, 2]], native) - depth - centroid[1]
            maximum_approximation = max(maximum_approximation, abs(deviation))
            bilinear_bound = abs(patch["bilinear_coefficients_m"][3]) * np.ptp(bottom[:, 0]) * np.ptp(bottom[:, 2]) / native.spacing**2
            compare(item["conservative_interior_height_error_bound_m"], bilinear_bound,
                    "saved bilinear planar approximation bound", atol=1e-12)
            maximum_bilinear_bound = max(maximum_bilinear_bound, float(bilinear_bound))
            prism = item["prism"]
            check_identity(prism)
            require(prism["schema"] == "td-hybrid-local-solid-mesh-v1"
                    and prism["role"] == "surface_half_arm_closed_triangular_prism"
                    and item["prism_triangle_roles"] == ["floor", "artificial_top_cap"] + ["lateral"] * 6
                    and {tuple(sorted(face)) for face in prism["triangles"]} == expected_faces,
                    "prism closure/source roles differ")
            top = bottom.copy()
            top[:, 1] = expected_cap
            compare(prism["local_origin_xyz_m"], origin, "prism origin", atol=0.)
            compare(prism["vertices_local_xyz_m"], np.vstack((bottom, top)) - origin, "prism actual vertices", atol=1e-9)
            solid = Solid(prism["vertices_local_xyz_m"], prism["triangles"], "source prism")
            compare(prism["signed_volume_m3"], solid.signed_volume, "saved source prism volume", atol=1e-7)
            own.append(solid)
            all_prisms.append(solid.manifold(library))
        for fan_key, (_, fan) in expected.items():
            for patch_index, patch in enumerate(fan["native_patches"]):
                parts = coverage.get((fan_key, patch_index), [])
                domain = Polygon(patch["polygon_xz_m"])
                require(parts and domain.symmetric_difference(unary_union(parts)).area <= 1e-8
                        and abs(sum(part.area for part in parts) - domain.area) <= 1e-8,
                        "missing/overlapping whole native patch prism coverage")
        records[kind] = own
        reports[kind] = {"bottom_triangles": len(bottoms), "original_half_arm_triangles": len(wanted),
                         "native_source_and_saved_patch_affine_function_verified": True,
                         "exact_original_fan_outside_vertex_occurrences": outside_vertex_count,
                         "entity_domain_authority": "original_saved_native_patch_polygon",
                         "max_sampled_centroid_planar_native_difference_m": maximum_approximation,
                         "max_saved_bilinear_component_error_bound_m": maximum_bilinear_bound,
                         "centroid_probe_is_not_global_approximation_bound": True}
        check_memory()
    expected_surface = library.Manifold.batch_boolean(all_prisms, library.OpType.Add)
    tolerance = max(1e-7, expected_surface.volume() * 1e-10)
    require(volume_difference(expected_surface, meshes["surface_cutter"].manifold(library)) <= tolerance,
            "saved surface cutter not union of source-bound closed prisms")
    extra = meshes["extra_removed"].manifold(library)
    require((extra - expected_surface).volume() <= tolerance, "extra removed escapes source-supported prism volume")
    return records, reports


def audit_canonical_pieces(witnesses, proof, bottoms, flow, kind, station):
    expected_pieces = [piece for segment in proof["segments"] for piece in segment["pieces"]]
    require([item["original_piece"] for item in witnesses] == expected_pieces and witnesses,
            "canonical whole piece census differs")
    normal = np.asarray(flow, float)
    normal /= np.linalg.norm(normal)
    side = -1. if kind == "sink" else 1.
    origin = np.asarray(station["origin_xyz_m"])[[0, 2]]
    minimum_distance = math.inf
    for witness in witnesses:
        piece = witness["original_piece"]
        start, end = np.asarray(piece["start_xz_m"]), np.asarray(piece["end_xz_m"])
        delta = end - start
        squared_length = float(delta @ delta)
        require(squared_length > 1e-16 and piece["bed_coefficients_m_t012"][2] == 0.
                and witness["full_interval_t01"] == [0., 1.] and witness["supports"],
                "unsupported canonical piece")
        length = math.sqrt(squared_length)
        intervals = []
        for support in witness["supports"]:
            index = support["bottom_triangle_id"]
            require(type(index) is int and 0 <= index < len(bottoms), "canonical references unknown source bottom")
            bottom = bottoms[index]
            vertices = np.asarray(bottom["bottom_vertices_xyz_m"])
            edge = np.asarray(support["edge_xyz_m"], float)
            require(edge.shape == (2, 3) and support["fan_key"] == bottom["fan_key"]
                    and any(np.array_equal(edge, np.asarray([vertices[offset], vertices[(offset + 1) % 3]])) for offset in range(3)),
                    "canonical edge not original saved prism bottom edge")
            fractions = (edge[:, [0, 2]] - start) @ delta / squared_length
            require(np.max(np.linalg.norm(edge[:, [0, 2]] - (start + fractions[:, None] * delta), axis=1)) <= 1e-8
                    and abs(fractions[1] - fractions[0]) * length > 1e-8, "canonical support edge off whole source line")
            interval = [max(0., float(min(fractions))), min(1., float(max(fractions)))]
            require((interval[1] - interval[0]) * length > 1e-8, "empty canonical support interval")
            compare(support["interval_t01"], interval, "canonical whole interval", atol=1e-12)
            slope = (edge[1, 1] - edge[0, 1]) / (fractions[1] - fractions[0])
            intercept = edge[0, 1] - slope * fractions[0]
            expected = piece["bed_coefficients_m_t012"]
            error = max(abs(intercept - expected[0]), abs(intercept + slope - expected[0] - expected[1]))
            require(error <= 1e-8, "whole canonical bed coefficient mismatch")
            compare(support["actual_bed_coefficients_m_t012"], [intercept, slope, 0.], "saved canonical coefficients", atol=1e-9)
            compare(support["maximum_whole_linear_error_m"], error, "saved whole coefficient error", atol=1e-12)
            distances = side * ((vertices[:, [0, 2]] - origin) @ normal)
            require(distances.min() >= -1e-8 and distances.max() > 1e-8, "canonical support not exterior half-arm volume")
            compare(support["exterior_support_distance_m"], distances.max(), "actual exterior prism support", atol=1e-8)
            minimum_distance = min(minimum_distance, float(distances.max()))
            intervals.append(interval)
        cursor = 0.
        for lower, upper in sorted(intervals):
            require((lower - cursor) * length <= 1e-8, "canonical full function gap")
            cursor = max(cursor, upper)
        require((1 - cursor) * length <= 1e-8, "canonical whole function incomplete")
    return minimum_distance


def audit_connections(composition, saved, geometry, attachments, vdm, meshes, origin):
    from shapely.geometry import Polygon
    library = manifold_library()
    require(set(composition["portal_connections"]) == {"sink", "spring"}, "missing two actual port connection records")
    reports = {}
    for kind, ordinal in (("sink", 0), ("spring", len(vdm["stations"]) - 1)):
        connection = composition["portal_connections"][kind]
        attachment = attachments["attachments"][kind]
        port = read(attachment["canonical_port_pin"])
        station = vdm["stations"][ordinal]
        require(port["identity_sha256"] == geometry["portal_bindings"][kind]["port_identity_sha256"]
                and connection["original_complete_port_proof"] == attachment["actual_complete_port_proof"]
                and connection["immutable_gallery_station_index"] == ordinal
                and connection["offset_traces_are_diagnostic_only"] is True
                and connection["hydraulic_boundary_certified"] is False
                and connection["full_shared_interface_supported"] is True
                and connection["canonical_whole_piece_witnesses"] == saved["half_arms"][kind]["canonical_whole_piece_witnesses"],
                "canonical connection source/claim differs")
        minimum_distance = audit_canonical_pieces(connection["canonical_whole_piece_witnesses"],
            attachment["actual_complete_port_proof"], saved["half_arms"][kind]["bottom_triangles"],
            port["flow_unit_xz"], kind, station)
        frame = connection["plane"]
        check_plane(frame, station["origin_xyz_m"], port["flow_unit_xz"], origin)
        ring = np.asarray(station["derived_ring_xyz_m"], float)
        uv = np.column_stack(((ring[:, [0, 2]] - np.asarray(station["origin_xyz_m"])[[0, 2]])
                              @ np.asarray(frame["transverse_unit_xz"]), ring[:, 1] - origin[1]))
        aperture = Polygon(uv)
        require(aperture.is_valid and aperture.area > 0 and not aperture.interiors, "invalid immutable gallery port domain")
        compare(connection["gallery_aperture_uv_m"], uv, "whole immutable gallery aperture", atol=1e-8)
        shapes = {}
        require(set(connection["exact_solid_slices"]) == {"coupled_cutter", "rock_after", "removed"}, "exact port slice census differs")
        for role, record in connection["exact_solid_slices"].items():
            shapes[role], _ = audit_slice(record, meshes[role], frame, {"artifact": role})
        blocked = aperture.intersection(shapes["rock_after"]).area
        missing = aperture.difference(shapes["coupled_cutter"]).area
        require(blocked <= 1e-8 and missing <= 1e-8, "actual full port blocked or absent; no cap deletion permitted")
        compare(connection["exact_blocked_area_m2"], blocked, "actual exact port blocked area", atol=1e-8)
        compare(connection["exact_missing_cutter_area_m2"], missing, "actual exact port missing area", atol=1e-8)
        epsilon = min(.001, minimum_distance / 16)
        require(connection["epsilon_rule"] == "min_1mm_and_minimum_actual_exterior_support_distance_div16",
                "changed bounded collar depth policy")
        bounds = aperture.bounds
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        basis = np.asarray([frame["transverse_unit_xyz"], frame["vertical_unit_xyz"], frame["normal_local_xyz"]]).T
        center = np.asarray(frame["origin_local_xyz_m"]) + np.asarray(frame["transverse_unit_xyz"]) * ((bounds[0] + bounds[2]) / 2)
        center[1] = (bounds[1] + bounds[3]) / 2
        proof = connection["positive_volume_connection"]
        require(set(proof["sides"]) == {"surface", "gallery"}
                and proof["constructed_by_intersecting_actual_cutters_not_new_excavation"] is True,
                "whole two-sided positive-volume source proof missing")
        side_solids, side_reports = [], {}
        surface_sign = -1. if kind == "sink" else 1.
        for side, sign, source in (("surface", surface_sign, "surface_cutter"), ("gallery", -surface_sign, "original_cutter")):
            side_proof = proof["sides"][side]
            role = kind + "_" + side + "_collar"
            require(side_proof["artifact"] == role and side_proof["source_solid"] == source
                    and side_proof["normal_side_sign"] == sign, "two-sided source orientation differs")
            transform = np.column_stack((basis, center + sign * epsilon / 2 * np.asarray(frame["normal_local_xyz"])))
            compare(side_proof["slab_width_height_depth_m"], [width, height, epsilon], "source collar slab dimensions", atol=1e-12)
            compare(side_proof["slab_transform_3x4"], transform, "source collar frame/side", atol=1e-9)
            slab = library.Manifold.cube([width, height, epsilon], center=True).transform(transform)
            expected = meshes[source].manifold(library) ^ slab
            actual = meshes[role].manifold(library)
            require(not actual.is_empty() and actual.volume() > 0 and len(actual.decompose()) == 1
                    and volume_difference(expected, actual) <= 1e-7, "collar not connected positive-volume actual source/slab intersection")
            compare(side_proof["positive_volume_m3"], actual.volume(), "actual positive collar volume", atol=1e-7)
            domain, _ = audit_slice(side_proof["interface_solid_slice"], meshes[role], frame, {"artifact": role})
            gap = aperture.difference(domain).area
            require(gap <= 1e-8, "two-sided collar does not cover complete immutable port")
            compare(side_proof["whole_aperture_uncovered_area_m2"], gap, "whole port collar gap", atol=1e-8)
            side_solids.append(actual)
            side_reports[side] = {"mesh_pin": composition["mesh_pins"][role], "volume_m3": actual.volume(),
                                  "whole_port_gap_m2": gap, "actual_source_solid": source}
        connected_role = kind + "_connected_collar"
        require(proof["connected_collar_artifact"] == connected_role, "wrong saved connected collar")
        connected = meshes[connected_role].manifold(library)
        require(len(connected.decompose()) == proof["component_count"] == 1
                and volume_difference(connected, side_solids[0] + side_solids[1]) <= 1e-7,
                "two actual source collars not one connected saved volume")
        overlap = float((connected ^ meshes["rock_after"].manifold(library)).volume())
        require(overlap <= 1e-7, "whole-port connection volume blocked by actual remaining rock")
        compare(proof["actual_rock_overlap_volume_m3"], overlap, "saved connected collar actual rock overlap", atol=1e-7)
        require((connected - meshes["coupled_cutter"].manifold(library)).volume() <= 1e-7,
                "connection proof adds fictitious excavation outside actual coupled cutter")
        traces = connection["one_sided_diagnostic_traces"]
        require([trace["offset_m"] for trace in traces] == [-epsilon, -epsilon / 2, epsilon / 2, epsilon],
                "offset diagnostics not bound to source-derived depth")
        for trace in traces:
            shifted = np.asarray(station["origin_xyz_m"]) + trace["offset_m"] * np.asarray(frame["normal_local_xyz"])
            check_plane(trace["plane"], shifted, port["flow_unit_xz"], origin)
            require(set(trace["solid_slices"]) == {"coupled_cutter", "rock_after", "removed"}, "diagnostic trace census differs")
            for role, record in trace["solid_slices"].items():
                audit_slice(record, meshes[role], trace["plane"], {"artifact": role})
        reports[kind] = {"verified": True, "port_identity_sha256": port["identity_sha256"],
                         "canonical_port_pin": attachment["canonical_port_pin"], "two_sided_complete_port_verified": True,
                         "exact_blocked_area_m2": blocked, "exact_missing_cutter_area_m2": missing,
                         "positive_volume_sides": side_reports, "connected_collar_pin": composition["mesh_pins"][connected_role],
                         "actual_rock_overlap_volume_m3": overlap, "offset_slices_not_acceptance_basis": True,
                         "scope": "source_supported_full_canonical_port_local_positive_volume_join_not_whole_link_or_hydraulics"}
        check_memory()
    return reports


def audit_sampling_mismatches(saved, sampling, attachments):
    expected = []
    for kind in ("sink", "spring"):
        attachment = attachments["attachments"][kind]
        node = read(attachment["surface_node_pin"])
        wanted = {"shared:" + node["node_id"] + ":" + str(index) for index in attachment["half_arm_triangle_indices"]}
        fans = [fan for fan in attachment["compact_native_fans"] if fan["triangle_id"] in wanted]
        port = read(attachment["canonical_port_pin"])
        for sample in sampling["samples"]:
            point = np.asarray(sample["xz_m"], float)
            if abs((point - port["midpoint_xz_m"]) @ np.asarray(port["flow_unit_xz"])) > 1e-8:
                continue
            hits = []
            for fan in fans:
                vertices = np.asarray(fan["vertices_xz_m"])
                if np.any(point < vertices.min(axis=0)) or np.any(point > vertices.max(axis=0)):
                    continue
                depth = exact_fan_cut(fan, point)
                if depth is not None:
                    hits.append({"fan_key": fan["fan_key"], "exact_domain_cut_depth_m": depth,
                                 "saved_vertices_xz_m": fan["vertices_xz_m"], "saved_vertex_depths_m": fan["depth_at_vertices_m"]})
            if not hits:
                continue
            depths = [hit["exact_domain_cut_depth_m"] for hit in hits]
            require(max(depths) - min(depths) <= 1e-9, "exact original shared fan depth mismatch")
            if abs(depths[0] - sample["cut_depth_m"]) > 1e-9:
                expected.append({"kind": kind, "source_sampling_row": sample["row"], "source_sampling_column": sample["column"],
                    "point_xz_m": sample["xz_m"], "saved_cut_depth_m": sample["cut_depth_m"], "saved_fan_keys": sample["fan_keys"],
                    "saved_derived_bed_m": sample["derived_bed_m"], "saved_original_source_sample": sample["source_sample"],
                    "exact_domain_supports": hits, "expected_cut_depth_m": depths[0],
                    "sampled_top_excess_height_m": depths[0] - sample["cut_depth_m"],
                    "classification": "saved_cut_lookup_mismatch_exact_domain_not_source_height_recalculation",
                    "scope": "only_saved_port_plane_grid_samples_no_global_source_claim"})
    require(len(saved) == len(expected), "original source sampling mismatch witness census differs")
    for actual, independent in zip(saved, expected):
        require(set(actual) == set(independent), "source sampling mismatch fields differ")
        for field, value in independent.items():
            if field in ("expected_cut_depth_m", "sampled_top_excess_height_m"):
                compare(actual[field], value, "exact original source mismatch " + field, atol=1e-12)
            elif field == "exact_domain_supports":
                require(len(actual[field]) == len(value), "source mismatch exact domain support census differs")
                for saved_hit, expected_hit in zip(actual[field], value):
                    for key in ("fan_key", "saved_vertices_xz_m", "saved_vertex_depths_m"):
                        require(saved_hit[key] == expected_hit[key], "source mismatch support changed")
                    compare(saved_hit["exact_domain_cut_depth_m"], expected_hit["exact_domain_cut_depth_m"],
                            "source mismatch exact cut", atol=1e-12)
            else:
                require(actual[field] == value, "source sampling mismatch source provenance differs: " + field)
    return expected


def audit(composition_pin):
    record = read(composition_pin)
    require(record["schema"] == "td-hybrid-surface-composition-v1" and record["status"] == "candidate_unverified"
            and not record["rejection_reasons"], "refused/incomplete source composition cannot be accepted")
    inputs = record["inputs"]
    require(set(inputs) == {"geometry", "geometry_audit", "graph", "mesh_pins", "vdm", "surface_attachments", "surface_nodes", "original_source_sampling"}
            and inputs["geometry"]["sha256"] == GEOMETRY_SHA256
            and inputs["geometry_audit"]["sha256"] == GEOMETRY_AUDIT_SHA256, "fixed geometry03 parents differ")
    geometry, old_audit, graph = read(inputs["geometry"]), read_audit(inputs["geometry_audit"]), read(inputs["graph"])
    require(old_audit["status"] == "passed" and not old_audit["errors"]
            and old_audit["geometry_sha256"] == GEOMETRY_SHA256
            and old_audit["geometry_identity_sha256"] == geometry["identity_sha256"]
            and old_audit["mesh_pins"] == geometry["mesh_pins"] and old_audit["inputs"] == geometry["inputs"]
            and old_audit["actual_portal_connections_verified"] is True
            and old_audit["actual_hydraulic_sections_verified"] is True
            and graph["identity_sha256"] == geometry["graph_identity_sha256"] == record["graph_identity_sha256"]
            and record["geometry_identity_sha256"] == geometry["identity_sha256"], "original saved geometry parent chain differs")
    require(inputs["graph"] == geometry["inputs"]["graph"] and inputs["mesh_pins"] == geometry["mesh_pins"]
            and inputs["vdm"] == geometry["vdm_pin"] and inputs["surface_attachments"] == geometry["surface_attachments_pin"]
            and inputs["original_source_sampling"] == geometry["source_sampling_pin"],
            "original saved sources changed")
    expected_code_names = {"terrain_pipeline/hybrid_surface_composition.py", "tools/prepare_hybrid_surface_composition.py",
                           "tests/test_hybrid_surface_composition.py"}
    require(set(record["code_sha256"]) == expected_code_names and record["code_sha256"] == FROZEN_COMPOSITION_CODE,
            "composition frozen code identity differs")
    for parent in (record, geometry, old_audit):
        for group in ("code_sha256", "readonly_dependency_code_sha256", "audit_code_sha256"):
            for name, sha in parent.get(group, {}).items():
                require(file_sha256(ROOT / name) == sha, "pinned implementation changed: " + name)
    for parent in (geometry, graph):
        for pin in parent["inputs"].values():
            checked_path(pin)
    require(record["policy"] == POLICY and record["policy_identity_sha256"] == digest(POLICY), "unknown composition/source policy")
    for flag in ("vdm_moved", "ports_moved", "fill_generated", "native_exact", "fine15_replaced",
                 "independent_audit_passed", "hydraulic_ready", "hydraulic_solved", "full_network_verified"):
        require(record[flag] is False, "source composition prematurely promoted: " + flag)
    require(record["original_sampled_rock_retained_cut_only_not_source_resampling"] is True,
            "original source defects or repair semantics hidden")
    library = manifold_library()
    require(record["runtime"]["manifold3d"] == "3.5.4"
            and record["runtime"]["manifold3d_binary_sha256"] == file_sha256(library.__file__), "composition Boolean runtime differs")
    attachments, vdm = read(inputs["surface_attachments"]), read(inputs["vdm"])
    sampling = read(inputs["original_source_sampling"])
    sampling_mismatches = audit_sampling_mismatches(record["original_source_sampling_cut_lookup_mismatches"], sampling, attachments)
    require(inputs["surface_nodes"] == {kind: attachment["surface_node_pin"] for kind, attachment in attachments["attachments"].items()}
            and set(inputs["surface_nodes"]) == {"sink", "spring"}, "original half-arm node bindings differ")
    original_pins = {"rock_before": geometry["mesh_pins"]["rock_before"],
                     **{"original_" + role: geometry["mesh_pins"][role] for role in ("cutter", "rock_after", "removed")}}
    extra_roles = {kind + "_" + side + "_collar" for kind in ("sink", "spring") for side in ("surface", "gallery", "connected")}
    expected_meshes = set(original_pins) | {"surface_cutter", "coupled_cutter", "rock_after", "removed", "extra_removed"} | extra_roles
    require(set(record["mesh_pins"]) == expected_meshes and all(record["mesh_pins"][role] == pin for role, pin in original_pins.items()),
            "original/new mesh identity or complete volume-proof census differs")
    meshes, origin = {}, None
    for role, pin in record["mesh_pins"].items():
        mesh = read(pin)
        local_origin = np.asarray(mesh["local_origin_xyz_m"], float)
        require(local_origin.shape == (3,) and np.isfinite(local_origin).all(), "invalid common local mesh origin")
        if origin is None:
            origin = local_origin
        require(np.array_equal(origin, local_origin), "composition solids not in common local frame")
        expected_role = role.removeprefix("original_")
        if role == "removed":
            expected_role = "total_removed"
        require(mesh["role"] == expected_role, "saved mesh role substituted")
        if mesh["schema"] == "td-hybrid-empty-solid-v1":
            require(role == "extra_removed" and mesh["vertices_local_xyz_m"] == [] and mesh["triangles"] == []
                    and mesh["signed_volume_m3"] == 0., "unknown/invalid empty material solid")
            meshes[role] = EmptySolid()
        else:
            require(mesh["schema"] == "td-hybrid-local-solid-mesh-v1", "unknown saved solid schema")
            meshes[role] = Solid(mesh["vertices_local_xyz_m"], mesh["triangles"], role)
            compare(mesh["signed_volume_m3"], meshes[role].signed_volume, "saved actual solid volume", atol=1e-7, rtol=1e-9)
    sections = read(geometry["inputs"]["original_06_sections"])
    protection = read(geometry["inputs"]["original_wet_protection_manifest"])["wet_protection"]
    native = load_native(geometry["inputs"]["original_hierarchy"], sections["selected_leaf_ids"], protection)
    prisms = read(record["surface_prisms_pin"])
    _, source_reports = audit_prisms(prisms, attachments, vdm, native, origin, meshes)
    material = audit_material_solids(*(meshes[key] for key in ("rock_before", "original_rock_after", "original_removed",
        "surface_cutter", "coupled_cutter", "rock_after", "extra_removed", "removed", "original_cutter")))
    saved_material = record["material"]
    for key, expected in (("original_rock_before_m3", meshes["rock_before"].signed_volume),
                          ("original_removed_m3", material["original_removed_m3"]),
                          ("original_rock_after_m3", meshes["original_rock_after"].signed_volume),
                          ("total_removed_m3", material["total_removed_m3"]),
                          ("extra_removed_m3", material["extra_removed_m3"]),
                          ("new_rock_after_m3", meshes["rock_after"].signed_volume)):
        compare(saved_material[key], expected, "saved material " + key, atol=1e-7, rtol=1e-9)
    residuals = [saved_material["original_rock_before_m3"] - saved_material["original_rock_after_m3"] - saved_material["original_removed_m3"],
                 saved_material["original_rock_before_m3"] - saved_material["new_rock_after_m3"] - saved_material["total_removed_m3"],
                 saved_material["total_removed_m3"] - saved_material["original_removed_m3"] - saved_material["extra_removed_m3"]]
    compare(saved_material["signed_residuals_m3"], residuals, "saved signed material residuals", atol=1e-7)
    require(saved_material["fill_m3"] == 0. and saved_material["fine15_material_replaced"] is False
            and saved_material["sampled_solid_material_not_native_exact"] is True
            and abs(saved_material["residual_tolerance_m3"] - material["comparison_tolerance_m3"]) <= 1e-12,
            "fill or material accuracy policy changed")
    require(len(meshes["coupled_cutter"].manifold(library).decompose()) == record["coupled_cutter_component_count"] == 1,
            "actual coupled cutter disconnected")
    errors = []
    portal_reports = {kind: {"verified": False, "two_sided_complete_port_verified": False} for kind in ("sink", "spring")}
    try:
        portal_reports = audit_connections(record, prisms, geometry, attachments, vdm, meshes, origin)
    except (ValueError, KeyError, TypeError, IndexError, RuntimeError) as error:
        errors.append("two-sided whole-port verification failed: " + str(error))
    verified = not errors
    return {"schema": AUDIT_SCHEMA, "status": "passed" if verified else "refused", "errors": errors,
            "composition_pin": composition_pin, "composition_identity_sha256": record["identity_sha256"], "inputs": inputs,
            "mesh_pins": record["mesh_pins"], "surface_prisms_pin": record["surface_prisms_pin"],
            "geometry_sha256": GEOMETRY_SHA256, "policy_identity_sha256": digest(POLICY),
            "native_half_arm_sources_verified": True, "source_reports": source_reports,
            "original_source_sampling_cut_lookup_mismatches": sampling_mismatches,
            "materials_verified": True, "material": material, "portal_reports": portal_reports,
            "two_sided_complete_port_verified": verified, "hydraulic_constitutive_law_accepted": False,
            "hydraulic_solved": False, "native_exact": False, "fine15_replaced": False,
            "original_sampling_defects_revalidated_as_correct": False, "whole_link_control_sill_verified": False,
            "scope": "source_bound_piecewise_planar_surface_carve_increment_and_local_full_port_volume_connections",
            "tolerances": {"canonical_boundary_m": 1e-8, "whole_port_gap_area_m2": 1e-8, "collar_boolean_difference_m3": 1e-7}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--composition", type=Path, required=True)
    parser.add_argument("--composition-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / "verification"), "new verification audit file required")
    pin = {"path": str(args.composition.resolve()), "sha256": args.composition_sha256}
    started = time.monotonic()
    try:
        report = audit(pin)
    except (ValueError, KeyError, TypeError, IndexError, OSError, RuntimeError) as error:
        report = {"schema": AUDIT_SCHEMA, "status": "refused", "errors": [str(error)], "composition_pin": pin,
                  "materials_verified": False, "two_sided_complete_port_verified": False,
                  "hydraulic_constitutive_law_accepted": False, "hydraulic_solved": False}
    report["resource"] = {"wall_seconds": time.monotonic() - started, "actual_peak_rss_bytes": check_memory(),
                          "solver_calls": 0, "source_artifacts_modified": False}
    report["code_sha256"] = {name: file_sha256(ROOT / name) for name in (
        "tools/audit_hybrid_surface_composition.py", "tests/test_hybrid_surface_composition_saved_audit.py",
        "tools/audit_hybrid_river_faces.py", "tools/hybrid_cave_saved_audit.py", "tools/td_shared_channel_fine_saved_audit.py")}
    report["identity_sha256"] = digest(report)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "composition independent audit exceeds 64MiB file budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(json.dumps({"status": report["status"], "errors": report["errors"], "output": str(output),
                      "sha256": file_sha256(output), "two_sided_complete_port_verified": report["two_sided_complete_port_verified"]}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
