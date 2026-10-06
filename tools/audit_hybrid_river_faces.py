"""Independent cold evidence for saved, source-bound hydraulic face geometry."""

import argparse
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
    MAX_BYTES, check_identity, check_memory, checked_path, compare, digest, file_sha256, read, read_audit, require)

AUDIT_SCHEMA = "td-hybrid-river-faces-independent-audit-v1"
PLANE_TOLERANCE_M = 1e-8
GEOMETRY_SHA256 = "3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593"
GEOMETRY_AUDIT_SHA256 = "703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364"
GRAPH_SHA256 = "279d632e6f471c2629a37d7d6954adbcb734be19278e009eb352c9852593846a"
FROZEN_FACE_CODE = {
    "terrain_pipeline/hybrid_river_faces.py": "73ae18fc30afabb70ed4b3d1c043606141e560c7d0d818f38053ac018b5acc8a",
    "tools/prepare_hybrid_river_faces.py": "e4c7051473aaaa5dbe79baa5314fc4fe52e68af7e9197a8871eb68272b82fb2e",
    "tests/test_hybrid_river_faces.py": "a329e3850f7e211dbf07c756263650d0f3d1b7b3848f1ee7a8c833fe52b290e6"}
POLICY = {"version": "actual_saved_solid_link_faces-v1",
    "coordinates": "common_local_XYZ_metres_Y_vertical_face_u_Ylocal",
    "gallery_plane": "adjacent_station_origin_midpoint_normal_actual_XZ_station_difference",
    "attachment_plane": "exact_immutable_canonical_gallery_0_16_with_complete_saved_half_arm_proof",
    "geometry": "actual_Mesh64_plane_slices_not_minimum_of_endpoint_sections",
    "wall": "actual_rock_after_boundary_separate_from_free_surface_engineering_wall_and_artificial_cutter_cap",
    "open": "saved_actual_cut_floor_with_explicit_engineering_vertical_extensions_not_a_closed_cutter_roof",
    "slot": "storage_only_never_enlarges_face",
    "unknown": "missing_geometry_or_multiple_disconnected_apertures_refused_never_zero_flow_closed_wall",
    "flow": "not_computed_no_step_loss_no_new_roughness_original_link_length"}


def triangle_plane_segments(vertices, triangles, origin, normal, transverse):
    vertices = np.asarray(vertices, dtype=float)
    triangles = np.asarray(triangles)
    origin, normal, transverse = (np.asarray(value, dtype=float) for value in (origin, normal, transverse))
    require(vertices.ndim == 2 and vertices.shape[1] == 3 and np.isfinite(vertices).all(), "invalid source vertices")
    require(triangles.ndim == 2 and triangles.shape[1] == 3
            and np.issubdtype(triangles.dtype, np.integer) and triangles.min() >= 0
            and triangles.max() < len(vertices), "invalid source triangle references")
    require(all(value.shape == (3,) and np.isfinite(value).all() for value in (origin, normal, transverse)),
            "invalid face plane frame")
    compare(np.linalg.norm(normal), 1., "unit face normal")
    compare(np.linalg.norm(transverse), 1., "unit transverse axis")
    compare(normal[1], 0., "horizontal flow normal")
    compare(transverse[1], 0., "horizontal transverse axis")
    compare(normal @ transverse, 0., "orthogonal face axes")
    intersections, coplanar = {}, []
    for ordinal, indices in enumerate(triangles):
        points = vertices[indices]
        distances = (points - origin) @ normal
        if np.all(np.abs(distances) <= PLANE_TOLERANCE_M):
            coplanar.append(ordinal)
            continue
        if distances.min() > PLANE_TOLERANCE_M or distances.max() < -PLANE_TOLERANCE_M:
            continue
        crossings = []
        for first, second in ((0, 1), (1, 2), (2, 0)):
            if abs(distances[first]) <= PLANE_TOLERANCE_M:
                crossings.append(points[first])
            if distances[first] * distances[second] < 0:
                fraction = distances[first] / (distances[first] - distances[second])
                crossings.append(points[first] + fraction * (points[second] - points[first]))
        unique = []
        for point in crossings:
            if all(np.linalg.norm(point - previous) > PLANE_TOLERANCE_M for previous in unique):
                unique.append(point)
        if len(unique) >= 2:
            pairs = [(np.linalg.norm(first - second), first, second)
                     for offset, first in enumerate(unique) for second in unique[offset + 1:]]
            length, first, second = max(pairs, key=lambda item: item[0])
            if length > PLANE_TOLERANCE_M:
                intersections[ordinal] = np.asarray([[(point - origin) @ transverse, point[1]]
                                                     for point in (first, second)])
    return intersections, coplanar


def polygons_geometry(contours):
    from shapely.geometry import GeometryCollection, Polygon
    result = GeometryCollection()
    for contour in contours:
        points = np.asarray(contour, dtype=float)
        require(points.ndim == 2 and points.shape[1] == 2 and len(points) >= 3 and np.isfinite(points).all(),
                "invalid saved slice contour")
        polygon = Polygon(points)
        require(polygon.is_valid and polygon.area > 0., "invalid/self-intersecting saved slice polygon")
        result = result.symmetric_difference(polygon)
    return result


def independently_slice(solid, origin, normal, transverse):
    library = manifold_library()
    transform = np.asarray([np.append(transverse, -np.dot(transverse, origin)),
                            [0., 1., 0., 0.], np.append(normal, -np.dot(normal, origin))])
    result = polygons_geometry(solid.manifold(library).transform(transform).slice(0.).to_polygons())
    from shapely.geometry import Polygon
    _, coplanar = triangle_plane_segments(solid.vertices, solid.triangles, origin, normal, transverse)
    for ordinal in coplanar:
        points = solid.points[ordinal]
        polygon = Polygon(np.column_stack(((points - origin) @ transverse, points[:, 1])))
        if polygon.area > 1e-8:
            result = result.union(polygon)
    return result


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


def audit_slice(record, solid, frame, pin):
    from shapely.geometry import LineString, Polygon
    require(record["mesh_pin"] == pin and record["coordinate_convention"] == frame["coordinate_convention"],
            "slice source/frame binding differs")
    origin, normal, transverse = [np.asarray(frame[key], float) for key in
                                  ("origin_local_xyz_m", "normal_local_xyz", "transverse_unit_xyz")]
    segments, coplanar = triangle_plane_segments(solid.vertices, solid.triangles, origin, normal, transverse)
    saved = record["triangle_segments"]
    require(len({item["triangle_index"] for item in saved}) == len(saved)
            and {item["triangle_index"] for item in saved} == set(segments), "incomplete/duplicate triangle-plane support")
    for item in saved:
        ordinal = item["triangle_index"]
        require(type(ordinal) is int and item["vertex_indices"] == solid.triangles[ordinal].tolist(),
                "triangle source references differ")
        expected = LineString(segments[ordinal])
        points = np.asarray(item["points_uv_m"], float)
        require(points.shape == (2, 2) and np.isfinite(points).all(), "invalid saved plane segment")
        require(expected.hausdorff_distance(LineString(points)) <= PLANE_TOLERANCE_M, "fabricated triangle-plane segment")
        xyz = origin + points[:, :1] * transverse
        xyz[:, 1] = points[:, 1]
        compare(item["points_local_xyz_m"], xyz, "triangle segment inverse frame", atol=PLANE_TOLERANCE_M)
    expected_caps = {}
    for ordinal in coplanar:
        points = solid.points[ordinal]
        polygon = Polygon(np.column_stack(((points - origin) @ transverse, points[:, 1])))
        if polygon.area > 1e-8:
            expected_caps[ordinal] = polygon
    saved_caps = record["coplanar_triangle_supports"]
    require(len({item["triangle_index"] for item in saved_caps}) == len(saved_caps)
            and {item["triangle_index"] for item in saved_caps} == set(expected_caps), "coplanar support census differs")
    for item in saved_caps:
        ordinal = item["triangle_index"]
        require(item["vertex_indices"] == solid.triangles[ordinal].tolist(), "coplanar source references differ")
        require(Polygon(item["polygon_uv_m"]).symmetric_difference(expected_caps[ordinal]).area <= 1e-8,
                "fabricated coplanar triangle")
    expected_method = "Mesh64_transform_slice_exact_plane" + ("_union_exact_saved_coplanar_triangles" if expected_caps else "")
    require(record["method"] == expected_method, "undeclared slice/coplanar policy")
    actual = independently_slice(solid, origin, normal, transverse)
    supplied = saved_slice_geometry(record)
    difference = supplied.symmetric_difference(actual).area
    require(difference <= 1e-8, "saved slice differs from independent source solid slice")
    compare(record["area_m2"], actual.area, "actual slice area", atol=1e-8)
    return actual, {"area_m2": actual.area, "symmetric_difference_m2": difference,
                    "triangle_segments": len(segments), "coplanar_triangles": len(expected_caps)}


def whole_line_supported(line, boundary):
    return line.difference(boundary.buffer(PLANE_TOLERANCE_M)).length <= PLANE_TOLERANCE_M


def verify_floor(points, aperture):
    from shapely.geometry import LineString
    floor = np.asarray(points, float)
    require(floor.ndim == 2 and floor.shape[1] == 2 and len(floor) >= 2 and np.isfinite(floor).all()
            and np.all(np.diff(floor[:, 0]) > 0), "invalid saved cut floor")
    line = LineString(floor)
    require(whole_line_supported(line, aperture.boundary), "cut floor not actual source boundary")
    compare(floor[[0, -1], 0], [aperture.bounds[0], aperture.bounds[2]], "whole aperture floor width", atol=1e-8)
    knots = sorted(set(floor[:, 0].tolist() + [point[0] for point in aperture.exterior.coords]))
    probes = knots + [(first + second) / 2 for first, second in zip(knots, knots[1:])]
    for offset in probes:
        vertical = LineString([(offset, aperture.bounds[1] - 1), (offset, aperture.bounds[3] + 1)])
        intersection = aperture.intersection(vertical)
        require(not intersection.is_empty, "cut floor crosses missing aperture")
        compare(float(np.interp(offset, floor[:, 0], floor[:, 1])), intersection.bounds[1],
                "saved floor is actual lower aperture envelope", atol=1e-8)
    return line


def audit_aperture(record, slices, shapes, frame, canonical=None):
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    cutter, before, after, removed = [shapes[key] for key in ("cutter", "rock_before", "rock_after", "removed")]
    require(not cutter.is_empty and cutter.geom_type == "Polygon" and not cutter.interiors
            and (removed.is_empty or removed.geom_type == "Polygon" and not removed.interiors),
            "unknown/multiple/holed actual aperture cannot be accepted")
    require(not removed.is_empty or canonical is not None,
            "unknown empty excavation without verified canonical whole port")
    require(record["pressure_slot_enlarges_face"] is False, "storage slot fabricated a face aperture")
    polygon = Polygon(record["polygon_uv_m"])
    require(polygon.is_valid and polygon.symmetric_difference(cutter).area <= 1e-8, "aperture not actual cutter domain")
    uv = np.asarray(record["polygon_uv_m"], float)
    xyz = np.asarray(frame["origin_local_xyz_m"]) + uv[:, :1] * np.asarray(frame["transverse_unit_xyz"])
    xyz[:, 1] = uv[:, 1]
    compare(record["polygon_local_xyz_m"], xyz, "aperture localXYZ", atol=1e-8)
    blocked = cutter.intersection(after).area
    replay = removed.symmetric_difference(cutter.intersection(before)).area
    outside = cutter.difference(before).area
    require(blocked <= 1e-8 and replay <= 1e-8, "actual aperture blocked or removed/source intersection differs")
    for key, expected in (("blocked_area_m2", blocked), ("removed_replay_difference_area_m2", replay),
                          ("actual_excavated_aperture_area_m2", removed.area),
                          ("cutter_outside_original_rock_area_m2", outside),
                          ("bounded_display_aperture_area_m2", cutter.area)):
        compare(record[key], expected, key, atol=1e-8)
    floor = verify_floor(record["cut_floor_uv_m"], cutter)
    pieces, wall_lengths, covered = record["boundary_pieces"], [], []
    require(pieces, "missing aperture boundary census")
    for piece in pieces:
        points = np.asarray(piece["points_uv_m"], float)
        require(points.shape == (2, 2) and np.isfinite(points).all(), "invalid boundary segment")
        line = LineString(points)
        require(line.length > PLANE_TOLERANCE_M and whole_line_supported(line, cutter.boundary), "fabricated boundary piece")
        xyz = np.asarray(frame["origin_local_xyz_m"]) + points[:, :1] * np.asarray(frame["transverse_unit_xyz"])
        xyz[:, 1] = points[:, 1]
        compare(piece["points_local_xyz_m"], xyz, "boundary inverse frame", atol=1e-8)
        category = piece["category"]
        actual_wall = whole_line_supported(line, after.boundary) and before.buffer(PLANE_TOLERANCE_M).covers(line)
        if actual_wall:
            require(category == "actual_rock_wet_wall", "actual rock wall misclassified")
            compare(piece["potential_wetted_length_m"], line.length, "actual wet wall length", atol=1e-8)
            wall_lengths.append(line.length)
        else:
            require(not before.buffer(PLANE_TOLERANCE_M).covers(line),
                    "unknown in-rock edge without actual whole-wall support")
            require(category != "actual_rock_wet_wall" and piece["potential_wetted_length_m"] is None,
                    "non-rock/artificial edge counted as real wetted wall")
            if whole_line_supported(line, floor):
                require(category == "saved_cut_floor_open_air_side", "open cut floor category differs")
            elif abs(points[0, 0] - points[1, 0]) <= PLANE_TOLERANCE_M:
                require(category == "engineering_lateral_wall_above_terrain", "engineering wall category differs")
            else:
                require(category == "artificial_cutter_top_cap_not_wetted_wall", "artificial cap category differs")
        for role, indices in piece["source_triangle_indices"].items():
            require(role in ("cutter", "rock_after") and len(set(indices)) == len(indices)
                    and all(type(index) is int for index in indices), "invalid wall source roles/references")
            support_lines = [LineString(item["points_uv_m"]) for item in slices[role]["triangle_segments"]
                             if item["triangle_index"] in indices]
            support_caps = [Polygon(item["polygon_uv_m"]) for item in slices[role]["coplanar_triangle_supports"]
                            if item["triangle_index"] in indices]
            available = {item["triangle_index"] for item in slices[role]["triangle_segments"] + slices[role]["coplanar_triangle_supports"]}
            require(set(indices) <= available, "wall references non-intersecting source triangles")
            if role == "cutter" or actual_wall:
                require(indices and whole_line_supported(line, unary_union(support_lines + support_caps)),
                        "whole wall/edge lacks actual triangle support")
        require(set(piece["source_triangle_indices"]) == {"cutter", "rock_after"}, "wall source census differs")
        covered.append(line)
    union = unary_union(covered)
    require(whole_line_supported(cutter.boundary, union)
            and abs(sum(line.length for line in covered) - union.length) <= 1e-8, "missing/overlapping aperture boundary pieces")
    closed = bool(outside <= 1e-8 and len(wall_lengths) == len(pieces) and canonical is None)
    require(type(record["closed_boundary_certified"]) is bool and record["closed_boundary_certified"] is closed
            and record["kind"] == ("closed_polygon" if closed else "open_cut_floor"), "closed/open aperture classification differs")
    if canonical is not None:
        require(LineString(canonical).hausdorff_distance(floor) <= 1e-8, "canonical whole floor missing from actual slice")
        compare(record["cut_floor_uv_m"], canonical, "canonical full native knot function", atol=1e-8)
    extension = record["open_extension"]
    if closed:
        require(extension is None, "closed actual aperture given artificial extension")
    else:
        extensions = []
        for piece in pieces:
            if piece["category"] != "artificial_cutter_top_cap_not_wetted_wall":
                continue
            points = piece["points_uv_m"]
            first, second = sorted(points, key=lambda point: point[0])
            require(second[0] - first[0] > PLANE_TOLERANCE_M, "zero-width free top interval")
            upper = max(cutter.bounds[3], before.bounds[3] if not before.is_empty else cutter.bounds[3],
                        after.bounds[3] if not after.is_empty else cutter.bounds[3]) + 1
            column = Polygon([first, second, [second[0], upper], [first[0], upper]])
            require(column.intersection(before).area <= 1e-8 and column.intersection(after).area <= 1e-8
                    and column.intersection(cutter).area <= 1e-8,
                    "free-top engineering extension penetrates actual rock roof or is not upper boundary")
            extensions.append({"u_interval_m": [first[0], second[0]], "lower_boundary_uv_m": points,
                               "kind": "above_saved_artificial_cap_only_not_above_actual_rock_roof"})
        require(extensions, "unknown open face without supported artificial free-top interval")
        require(extension == {"kind": "explicit_engineering_vertical", "lateral_u_m": [floor.coords[0][0], floor.coords[-1][0]],
                              "unbounded_above_cut_floor": False,
                              "unbounded_only_over_supported_free_top_intervals": extensions,
                              "actual_rock_roof_segments_remain_bounded": True,
                              "artificial_cutter_roof_is_not_flow_ceiling": True,
                              "extension_is_engineering_not_whole_physical_path_certification": True,
                              "not_actual_terrain_floodplain": True}, "undeclared engineering open extension")
    free_edges = []
    removed_points = list(removed.exterior.coords) if not removed.is_empty else []
    for first, second in zip(removed_points, removed_points[1:]):
        line = LineString([first, second])
        if line.length > PLANE_TOLERANCE_M and not whole_line_supported(line, cutter.boundary):
            free_edges.append(line)
    supplied_free = []
    for edge in record["terrain_opening_free_edges"]:
        line = LineString(edge["points_uv_m"])
        require(edge["category"] == "original_rock_top_opening_free_boundary_not_wall"
                and whole_line_supported(line, before.boundary), "free opening edge not source rock boundary")
        refs = edge["rock_before_triangle_indices"]
        lines = [LineString(item["points_uv_m"]) for item in slices["rock_before"]["triangle_segments"] if item["triangle_index"] in refs]
        caps = [Polygon(item["polygon_uv_m"]) for item in slices["rock_before"]["coplanar_triangle_supports"] if item["triangle_index"] in refs]
        require(refs and whole_line_supported(line, unary_union(lines + caps)), "free opening lacks original source triangle support")
        supplied_free.append(line)
    expected_free, saved_free = unary_union(free_edges), unary_union(supplied_free)
    require(whole_line_supported(expected_free, saved_free) and whole_line_supported(saved_free, expected_free),
            "missing/fabricated original rock free-edge census")
    return {"kind": record["kind"], "bounded_area_m2": cutter.area,
            "actual_rock_wall_length_m": math.fsum(wall_lengths), "boundary_piece_count": len(pieces),
            "actual_excavated_area_m2": removed.area, "engineering_open_extension_not_actual_rock_boundary": not closed,
            "slot_excluded": True, "free_surface_clip_not_counted_as_wall": True}


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


def audit_face(face, ordinal, geometry, vdm, attachments, solids, common_origin):
    check_identity(face)
    link = geometry["hydraulic_links"][ordinal]
    require(face["schema"] == "td-hybrid-river-face-v1" and face["face_id"] == "face:" + str(ordinal)
            and face["status"] == "candidate" and not face["rejection_reasons"], "refused/unknown face cannot be promoted")
    for key in ("link_id", "from_cell_id", "to_cell_id", "length_m"):
        require(face[key] == link[key], "actual link binding differs: " + key)
    cells = {cell["cell_id"]: cell for cell in geometry["hydraulic_cells"]}
    require(face["length_source"] == "unchanged_geometry_hydraulic_link" and face["length_m"] > 0
            and face["roughness_manning"] == .035
            and face["roughness_source_cell_ids"] == [link["from_cell_id"], link["to_cell_id"]]
            and all(cells[key]["roughness_manning"] == .035 for key in face["roughness_source_cell_ids"])
            and face["additional_step_loss"] is None, "undeclared n/length/step loss")
    stations = vdm["stations"]
    canonical = None
    if ordinal in (0, 17):
        kind = "sink" if ordinal == 0 else "spring"
        attachment = attachments["attachments"][kind]
        port = read(attachment["canonical_port_pin"])
        source_node = read(attachment["surface_node_pin"])
        station = stations[0 if ordinal == 0 else -1]
        require(link["to_cell_id"] == station["station_id"] if ordinal == 0 else link["from_cell_id"] == station["station_id"],
                "canonical attachment gallery endpoint differs")
        require(geometry["portal_bindings"][kind]["port_identity_sha256"] == port["identity_sha256"],
                "canonical port differs from original geometry")
        check_plane(face["plane"], station["origin_xyz_m"], port["flow_unit_xz"], common_origin)
        require(face["orientation_witness"] == {"canonical_station_id": station["station_id"],
                    "actual_flow_unit_xz": port["flow_unit_xz"], "actual_source_arc_xyz_m": port["source_arc_xyz_m"],
                    "not_oblique_endpoint_section_projection": True}, "canonical face orientation source differs")
        canonical = source_canonical_floor(port, face["plane"])
        binding = face["shared_port_binding"]
        expected = {"kind": kind, "canonical_port_pin": attachment["canonical_port_pin"],
                    "surface_node_pin": attachment["surface_node_pin"], "port_identity_sha256": port["identity_sha256"],
                    "actual_complete_port_proof": attachment["actual_complete_port_proof"],
                    "half_arm_triangle_indices": attachment["half_arm_triangle_indices"],
                    "canonical_floor_uv_m": canonical, "hydraulic_boundary_certified": False,
                    "shared_whole_function_not_endpoint_minimum": True}
        require(binding == expected and face["plane_rule"] == "actual_canonical_shared_port_plane", "incomplete canonical attachment binding")
        proof = binding["actual_complete_port_proof"]
        require(proof in source_node["port_proofs"] and proof["midpoint_port_identity_sha256"] == port["identity_sha256"]
                and sorted(segment["profile_segment_index"] for segment in proof["segments"]) == [0, 1, 2]
                and all(segment["pieces"] for segment in proof["segments"]), "canonical whole profile not original complete proof")
        source_triangles = source_node["geometry"]["triangles"]
        require(binding["half_arm_triangle_indices"] and all(type(index) is int and 0 <= index < len(source_triangles)
                for index in binding["half_arm_triangle_indices"]), "invalid actual half-arm triangle references")
    else:
        first, second = stations[ordinal - 1], stations[ordinal]
        require((link["from_cell_id"], link["to_cell_id"]) == (first["station_id"], second["station_id"])
                and face["shared_port_binding"] is None
                and face["plane_rule"] == "actual_adjacent_station_midpoint_XZ_flow_plane", "wrong gallery plane/link rule")
        start, end = np.asarray(first["origin_xyz_m"]), np.asarray(second["origin_xyz_m"])
        check_plane(face["plane"], (start + end) / 2, (end - start)[[0, 2]], common_origin)
        require(face["orientation_witness"] == {"station_ids": [first["station_id"], second["station_id"]],
                    "station_origin_world_xyz_m": [start.tolist(), end.tolist()],
                    "normal_rule": "unit_horizontal_discrete_centerline_segment_not_area_cosine_rescale"},
                "gallery face orientation witness differs")
    require(set(face["solid_slices"]) == set(solids), "four actual solid slice census differs")
    shapes, reports = {}, {}
    for role, solid in solids.items():
        shapes[role], reports[role] = audit_slice(face["solid_slices"][role], solid, face["plane"], geometry["mesh_pins"][role])
        check_memory()
    return {"face_id": face["face_id"], "link_id": link["link_id"], "plane_verified": True,
            "canonical_complete_floor_verified": canonical is not None, "solid_slices": reports,
            "aperture": audit_aperture(face["aperture"], face["solid_slices"], shapes, face["plane"], canonical)}


def audit(face_pin):
    record = read(face_pin)
    require(record["schema"] == "td-hybrid-river-faces-v1"
            and record["status"] in ("candidate_unverified", "refused"), "wrong saved face schema/status")
    require(record["code_sha256"] == FROZEN_FACE_CODE, "frozen face implementation binding differs")
    inputs = record["inputs"]
    require(inputs["geometry"]["sha256"] == GEOMETRY_SHA256
            and inputs["geometry_audit"]["sha256"] == GEOMETRY_AUDIT_SHA256
            and inputs["graph"]["sha256"] == GRAPH_SHA256, "only fixed independently passed geometry03 parents supported")
    geometry = read(inputs["geometry"])
    geometry_audit = read_audit(inputs["geometry_audit"])
    graph = read(inputs["graph"])
    require(geometry_audit["status"] == "passed" and not geometry_audit["errors"]
            and geometry_audit["geometry_sha256"] == GEOMETRY_SHA256
            and geometry_audit["geometry_identity_sha256"] == geometry["identity_sha256"]
            and geometry_audit["actual_hydraulic_sections_verified"] is True
            and geometry_audit["actual_portal_connections_verified"] is True
            and geometry_audit["mesh_pins"] == geometry["mesh_pins"]
            and geometry_audit["vdm_pin"] == geometry["vdm_pin"]
            and geometry_audit["graph_identity_sha256"] == geometry["graph_identity_sha256"]
            and geometry_audit["inputs"] == geometry["inputs"]
            and inputs["graph"] == geometry["inputs"]["graph"]
            and graph["identity_sha256"] == geometry["graph_identity_sha256"], "geometry/independent audit/graph linkage differs")
    require(inputs["mesh_pins"] == geometry["mesh_pins"] and inputs["vdm"] == geometry["vdm_pin"]
            and inputs["surface_attachments"] == geometry["surface_attachments_pin"], "actual face sources substituted")
    for parent in (record, geometry, geometry_audit):
        for group in ("code_sha256", "readonly_dependency_code_sha256", "audit_code_sha256"):
            for name, sha in parent.get(group, {}).items():
                require(file_sha256(ROOT / name) == sha, "frozen source changed: " + name)
    for parent in (geometry, graph):
        for pin in parent["inputs"].values():
            checked_path(pin)
    require(geometry["status"] == "candidate" and not geometry["rejection_reasons"]
            and set(record["inputs"]) == {"geometry", "geometry_audit", "graph", "mesh_pins", "vdm", "surface_attachments"},
            "changed geometry/face input contract")
    require(record.get("policy") == POLICY and record["policy_identity_sha256"] == digest(POLICY), "face policy differs")
    for flag in ("independent_audit_passed", "hydraulic_solved", "native_exact", "water_discharge_computed",
                 "storage_geometry_changed", "pressure_slot_enlarges_face"):
        require(record[flag] is False, "face source prematurely promoted capability: " + flag)
    require(record["geometry_identity_sha256"] == geometry["identity_sha256"]
            and record["graph_identity_sha256"] == graph["identity_sha256"]
            and record["runtime"]["manifold3d"] == "3.5.4", "face geometry identity/runtime differs")
    library = manifold_library()
    require(file_sha256(library.__file__) == record["runtime"]["manifold3d_binary_sha256"], "actual slice library binary changed")
    vdm, attachments = read(inputs["vdm"]), read(inputs["surface_attachments"])
    require(len(vdm["stations"]) == 17 and len(geometry["hydraulic_links"]) == 18
            and record["face_count"] == len(record["faces"]) == 18, "fixed 18-link face census incomplete")
    solids, common = {}, None
    for role, pin in geometry["mesh_pins"].items():
        mesh = read(pin)
        require(mesh["role"] == role and mesh["schema"] == "td-hybrid-local-solid-mesh-v1", "wrong actual mesh role")
        origin = np.asarray(mesh["local_origin_xyz_m"], float)
        if common is None:
            common = origin
        require(np.array_equal(common, origin), "source solids not in common frame")
        solids[role] = Solid(mesh["vertices_local_xyz_m"], mesh["triangles"], role)
    require(set(solids) == {"cutter", "removed", "rock_before", "rock_after"}, "actual solid census differs")
    reports, errors = [], []
    for ordinal, face in enumerate(record["faces"]):
        try:
            reports.append(audit_face(face, ordinal, geometry, vdm, attachments, solids, common))
        except (ValueError, KeyError, TypeError, IndexError) as error:
            errors.append({"face_id": face.get("face_id"), "error": str(error),
                           "saved_status": face.get("status"), "saved_rejection_reasons": face.get("rejection_reasons")})
    refused = [face["face_id"] for face in record["faces"] if face["status"] != "candidate"]
    require(record["rejection_reasons"] == refused
            and record["status"] == ("refused" if refused else "candidate_unverified"), "saved whole-package refusal census differs")
    return {"schema": AUDIT_SCHEMA, "status": "refused" if errors else "passed", "errors": errors,
            "faces_pin": face_pin, "inputs": inputs, "geometry_sha256": GEOMETRY_SHA256,
            "geometry_identity_sha256": geometry["identity_sha256"], "graph_identity_sha256": graph["identity_sha256"],
            "reports": reports, "verified_face_count": len(reports), "actual_slice_sources_verified": not errors,
            "wet_wall_boundary_sources_verified": not errors, "hydraulic_solved": False,
            "n_and_length_provenance_only_not_physical_adoption": True, "additional_step_loss_unknown_not_zero": True,
            "hydraulic_constitutive_law_accepted": False, "whole_link_step_support_certified": False,
            "unbounded_engineering_extension_is_actual_rock_aperture": False,
            "scope": "18_saved_local_transverse_faces_not_full_link_control_sill_or_dynamic_flow_certification",
            "tolerances": {"plane_and_boundary_m": PLANE_TOLERANCE_M, "slice_difference_m2": 1e-8}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--faces", type=Path, required=True)
    parser.add_argument("--faces-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / "verification"), "new verification audit file required")
    pin = {"path": str(args.faces.resolve()), "sha256": args.faces_sha256}
    started = time.monotonic()
    try:
        report = audit(pin)
    except (ValueError, KeyError, TypeError, IndexError, OSError, RuntimeError) as error:
        report = {"schema": AUDIT_SCHEMA, "status": "refused", "errors": [str(error)], "faces_pin": pin,
                  "hydraulic_solved": False, "hydraulic_constitutive_law_accepted": False}
    report["resource"] = {"wall_seconds": time.monotonic() - started, "actual_peak_rss_bytes": check_memory(),
                          "solver_calls": 0, "source_artifacts_modified": False}
    report["code_sha256"] = {name: file_sha256(ROOT / name) for name in (
        "tools/audit_hybrid_river_faces.py", "tests/test_hybrid_river_faces_saved_audit.py",
        "tools/hybrid_cave_saved_audit.py", "tools/td_shared_channel_fine_saved_audit.py")}
    report["identity_sha256"] = digest(report)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "independent face audit exceeds 64MiB file budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(json.dumps({"status": report["status"], "errors": report["errors"], "output": str(output),
                      "sha256": file_sha256(output), "verified_face_count": report.get("verified_face_count", 0)}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
