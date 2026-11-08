"""Independent original source/material/frame witnesses, without legacy audit entrypoints."""
from fractions import Fraction
import math
import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from tools.hybrid_cave_saved_audit import Solid, manifold_library
from tools.td_shared_channel_fine_saved_audit import check_identity, check_memory, compare, read, require


PLANE_TOLERANCE_M = 1e-8

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


def saved_slice_geometry(record):
    from shapely.geometry import GeometryCollection, Polygon
    require(len(record["polygons_uv_m"]) == len(record["holes_uv_m"]), "slice hole ownership mismatch")
    result = GeometryCollection()
    for exterior, holes in zip(record["polygons_uv_m"], record["holes_uv_m"]):
        polygon = Polygon(exterior, holes)
        require(polygon.is_valid and polygon.area > 0., "invalid saved slice with holes")
        require(result.intersection(polygon).area <= 1e-8, "overlapping saved slice components")
        result = result.union(polygon)
    return result


def whole_line_supported(line, boundary):
    return line.difference(boundary.buffer(PLANE_TOLERANCE_M)).length <= PLANE_TOLERANCE_M


def check_plane(frame, world_origin, flow_xz, common_origin):
    world_origin, common_origin = np.asarray(world_origin, float), np.asarray(common_origin, float)
    flow = np.asarray(flow_xz, float)
    require(flow.shape == (2,) and np.isfinite(flow).all() and np.linalg.norm(flow) > 1e-8, "unknown actual flow axis")
    flow = flow / np.linalg.norm(flow)
    normal, transverse = [flow[0], 0., flow[1]], [flow[1], 0., -flow[0]]
    for key, expected in (("origin_world_xyz_m", world_origin), ("origin_local_xyz_m", world_origin - common_origin),
                          ("common_local_origin_xyz_m", common_origin), ("normal_local_xyz", normal),
                          ("transverse_unit_xyz", transverse), ("transverse_unit_xz", [flow[1], -flow[0]]),
                          ("vertical_unit_xyz", [0., 1., 0.])):
        compare(frame[key], expected, "actual plane " + key, atol=1e-8)
    require(frame["coordinate_convention"] == "u_metres_Ylocal_metres_not_floor_relative"
            and frame["positive_normal"] == "from_cell_to_cell_actual_horizontal_route", "wrong face frame semantics")


def source_canonical_floor(port, frame):
    require(port["status"] == "candidate" and not port["rejection_reasons"], "refused canonical source port")
    common = np.asarray(frame["common_local_origin_xyz_m"], float)
    origin = np.asarray(frame["origin_local_xyz_m"], float)
    normal, transverse = np.asarray(frame["normal_local_xyz"]), np.asarray(frame["transverse_unit_xyz"])
    floor = []
    for segment in port["profile"]["profile_segments"]:
        for piece in segment["native_pieces"]:
            source, cut = piece["source"]["source_coefficients_m_t012"], piece["depth_coefficients_m_t01"]
            require(source[2] == 0 and 0 <= min(cut[0], sum(cut)) <= max(cut[0], sum(cut)) <= 4,
                    "unsupported/illegal canonical native floor")
            for fraction, xz in ((0., piece["start_xz_m"]), (1., piece["end_xz_m"])):
                height = source[0] + source[1] * fraction - cut[0] - cut[1] * fraction
                point = np.asarray([xz[0], height, xz[1]]) - common
                require(abs((point - origin) @ normal) <= 1e-8, "source canonical floor off actual face plane")
                uv = [float((point - origin) @ transverse), float(point[1])]
                if not floor or math.dist(uv, floor[-1]) > 1e-8:
                    floor.append(uv)
    floor.sort(key=lambda point: point[0])
    require(len(floor) >= 4 and all(second[0] > first[0] for first, second in zip(floor, floor[1:])),
            "canonical port whole floor/knot census invalid")
    return floor
