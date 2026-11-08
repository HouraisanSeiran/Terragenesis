"""Actual saved-solid transverse link faces; no flow or storage solver."""

import math

import numpy as np
import psutil
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from terrain_pipeline.hybrid_river_graph import identity

SCHEMA = "td-hybrid-river-faces-v1"
FACE_SCHEMA = "td-hybrid-river-face-v1"
MAX_BYTES = 64 * 1024**2
MAX_RSS = 1024**3
TOLERANCE_M = 1e-8
AREA_TOLERANCE_M2 = 1e-8
MAX_TRIANGLES = 200000
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
POLICY_SHA256 = identity(POLICY)


def seal(record):
    record.pop("identity_sha256", None)
    record["identity_sha256"] = identity(record)
    return record


def guard():
    memory = psutil.Process().memory_info()
    peak = max(memory.rss, getattr(memory, "peak_wset", 0))
    if peak > MAX_RSS:
        raise MemoryError("whole_face_package_1GiB_budget_exceeded")
    return peak


def plane_frame(origin_world, flow_xz, common_origin):
    origin_world, common_origin = np.asarray(origin_world, float), np.asarray(common_origin, float)
    flow = np.asarray(flow_xz, float)
    if (origin_world.shape != (3,) or common_origin.shape != (3,) or flow.shape != (2,)
            or not all(np.isfinite(value).all() for value in (origin_world, common_origin, flow))
            or np.linalg.norm(flow) <= TOLERANCE_M):
        raise ValueError("unknown_or_invalid_face_plane")
    flow /= np.linalg.norm(flow)
    normal = np.array([flow[0], 0., flow[1]])
    transverse = np.array([flow[1], 0., -flow[0]])
    return {"origin_world_xyz_m": origin_world.tolist(), "origin_local_xyz_m": (origin_world - common_origin).tolist(),
        "common_local_origin_xyz_m": common_origin.tolist(), "normal_local_xyz": normal.tolist(),
        "transverse_unit_xyz": transverse.tolist(), "transverse_unit_xz": transverse[[0, 2]].tolist(),
        "vertical_unit_xyz": [0., 1., 0.], "coordinate_convention": "u_metres_Ylocal_metres_not_floor_relative",
        "positive_normal": "from_cell_to_cell_actual_horizontal_route"}


def project(vertices_local, frame):
    points = np.asarray(vertices_local, float)
    relative = points - np.array(frame["origin_local_xyz_m"])
    return np.column_stack((relative @ np.array(frame["transverse_unit_xyz"]), points[:, 1]))


def unproject(points_uv, frame):
    points = np.asarray(points_uv, float)
    origin = np.array(frame["origin_local_xyz_m"])
    result = origin + points[:, :1] * np.array(frame["transverse_unit_xyz"])
    result[:, 1] = points[:, 1]
    return result


def solid_from_mesh(record, common_origin):
    import manifold3d as manifold
    points = np.array(record["vertices_local_xyz_m"], dtype=np.float64, order="C", copy=True)
    triangles = np.array(record["triangles"], dtype=np.uint64, order="C", copy=True)
    if (points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all()
            or triangles.ndim != 2 or triangles.shape[1] != 3 or not 0 < len(triangles) <= MAX_TRIANGLES
            or triangles.max() >= len(points)):
        raise ValueError("invalid_or_unbounded_saved_solid_mesh")
    origin = np.asarray(record["local_origin_xyz_m"], float)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("invalid_saved_solid_origin")
    points += origin - common_origin
    solid = manifold.Manifold(manifold.Mesh64(points, triangles))
    if solid.status() != manifold.Error.NoError or solid.is_empty() or solid.volume() <= 0:
        raise ValueError("saved_solid_not_positive_closed_manifold")
    return solid, points, triangles


def triangle_supports(points, triangles, frame):
    origin, normal = np.array(frame["origin_local_xyz_m"]), np.array(frame["normal_local_xyz"])
    distances = (points - origin) @ normal
    triangle_distances = distances[triangles]
    indices = np.flatnonzero((triangle_distances.min(axis=1) <= TOLERANCE_M)
        & (triangle_distances.max(axis=1) >= -TOLERANCE_M))
    segments, coplanar = [], []
    for ordinal in indices:
        ids = triangles[ordinal]
        vertices, values = points[ids], distances[ids]
        if np.max(np.abs(values)) <= TOLERANCE_M:
            uv = project(vertices, frame)
            polygon = Polygon(uv)
            if polygon.area > AREA_TOLERANCE_M2:
                coplanar.append({"triangle_index": int(ordinal), "vertex_indices": ids.tolist(), "polygon_uv_m": uv.tolist()})
            continue
        intersections = []
        for first in range(3):
            following = (first + 1) % 3
            if abs(values[first]) <= TOLERANCE_M:
                intersections.append(vertices[first])
            if values[first] * values[following] < 0.:
                fraction = values[first] / (values[first] - values[following])
                intersections.append((1. - fraction) * vertices[first] + fraction * vertices[following])
        distinct = []
        for point in intersections:
            if all(np.linalg.norm(point - other) > TOLERANCE_M for other in distinct):
                distinct.append(point)
        if len(distinct) < 2:
            continue
        if len(distinct) > 2:
            pair = max(((first, second) for first in distinct for second in distinct), key=lambda pair: np.linalg.norm(pair[1] - pair[0]))
            distinct = list(pair)
        segments.append({"triangle_index": int(ordinal), "vertex_indices": ids.tolist(),
            "points_local_xyz_m": np.asarray(distinct).tolist(), "points_uv_m": project(distinct, frame).tolist()})
    return segments, coplanar


def polygon_from_loops(loops):
    polygons, holes = [], []
    for loop in loops:
        points = np.asarray(loop, float)
        area = float(np.sum(points[:, 0] * np.roll(points[:, 1], -1) - points[:, 1] * np.roll(points[:, 0], -1)) / 2.)
        polygon = Polygon(points)
        if not polygon.is_valid or polygon.area <= AREA_TOLERANCE_M2:
            raise ValueError("invalid_actual_slice_polygon")
        (polygons if area > 0 else holes).append(polygon)
    result = unary_union(polygons)
    if holes:
        result = result.difference(unary_union(holes))
    return result


def slice_solid(solid_data, frame, pin):
    solid, points, triangles = solid_data
    origin = np.array(frame["origin_local_xyz_m"])
    normal, transverse = np.array(frame["normal_local_xyz"]), np.array(frame["transverse_unit_xyz"])
    transform = np.vstack((np.r_[transverse, -float(transverse @ origin)], [0., 1., 0., 0.], np.r_[normal, -float(normal @ origin)]))
    loops = [np.array(loop, dtype=float).tolist() for loop in solid.transform(transform.tolist()).slice(0.).to_polygons()]
    segments, coplanar = triangle_supports(points, triangles, frame)
    shape = polygon_from_loops(loops) if loops else Polygon()
    method = "Mesh64_transform_slice_exact_plane"
    if coplanar:
        caps = unary_union([Polygon(item["polygon_uv_m"]) for item in coplanar])
        shape = shape.union(caps)
        method += "_union_exact_saved_coplanar_triangles"
    if not shape.is_valid:
        raise ValueError("actual_slice_boolean_invalid")
    polygons = [shape] if shape.geom_type == "Polygon" and not shape.is_empty else list(shape.geoms) if shape.geom_type == "MultiPolygon" else []
    record = {"mesh_pin": pin, "method": method, "polygons_uv_m": [list(map(list, polygon.exterior.coords))[:-1] for polygon in polygons],
        "holes_uv_m": [[list(map(list, ring.coords))[:-1] for ring in polygon.interiors] for polygon in polygons],
        "area_m2": float(shape.area), "triangle_segments": segments, "coplanar_triangle_supports": coplanar,
        "coordinate_convention": frame["coordinate_convention"]}
    return record, shape


def lower_floor(polygon):
    coordinates = np.array(polygon.exterior.coords[:-1])
    values = sorted(set(float(point[0]) for point in coordinates))
    floor = []
    for value in values:
        candidates = [point[1] for point in coordinates if point[0] == value]
        for first, second in zip(coordinates, np.roll(coordinates, -1, axis=0)):
            if min(first[0], second[0]) < value < max(first[0], second[0]):
                fraction = (value - first[0]) / (second[0] - first[0])
                candidates.append(float((1. - fraction) * first[1] + fraction * second[1]))
        floor.append([value, min(candidates)])
    if len(floor) < 2 or any(second[0] - first[0] <= 0 for first, second in zip(floor, floor[1:])):
        raise ValueError("unknown_open_cut_floor")
    line = LineString(floor)
    if line.difference(polygon.boundary.buffer(TOLERANCE_M)).length > TOLERANCE_M:
        raise ValueError("cut_floor_not_actual_cutter_boundary")
    return floor


def support_indices(line, slice_record):
    result = {item["triangle_index"] for item in slice_record["triangle_segments"]
        if LineString(item["points_uv_m"]).distance(line) <= TOLERANCE_M
        and LineString(item["points_uv_m"]).intersection(line.buffer(TOLERANCE_M)).length > TOLERANCE_M}
    result.update(item["triangle_index"] for item in slice_record["coplanar_triangle_supports"]
        if Polygon(item["polygon_uv_m"]).distance(line) <= TOLERANCE_M)
    return sorted(result)


def boundary_pieces(aperture, before, after, records, frame):
    floor = LineString(lower_floor(aperture))
    coordinates = list(aperture.exterior.coords)
    pieces = []
    for first, second in zip(coordinates, coordinates[1:]):
        line = LineString([first, second])
        if line.length <= TOLERANCE_M:
            continue
        points = []
        pending = [line.intersection(before.boundary), line.intersection(after.boundary)]
        while pending:
            intersection = pending.pop()
            if intersection.is_empty:
                continue
            if intersection.geom_type == "Point":
                points.append(intersection)
            elif intersection.geom_type == "LineString":
                points.extend(Point(point) for point in intersection.coords)
            elif hasattr(intersection, "geoms"):
                pending.extend(intersection.geoms)
        fractions = sorted({0., 1., *(float(line.project(point, normalized=True)) for point in points)})
        for lower, upper in zip(fractions, fractions[1:]):
            part = LineString([line.interpolate(lower, normalized=True), line.interpolate(upper, normalized=True)])
            if part.length <= TOLERANCE_M:
                continue
            on_floor = part.difference(floor.buffer(TOLERANCE_M)).length <= TOLERANCE_M
            inside_before = before.buffer(TOLERANCE_M).covers(part)
            actual_wall = (inside_before and part.difference(after.boundary.buffer(TOLERANCE_M)).length <= TOLERANCE_M)
            if actual_wall:
                category = "actual_rock_wet_wall"
            elif inside_before:
                raise ValueError("unknown_inside_rock_boundary_without_whole_rock_after_wall_support")
            elif on_floor:
                category = "saved_cut_floor_open_air_side"
            elif abs(part.coords[0][0] - part.coords[-1][0]) <= TOLERANCE_M:
                category = "engineering_lateral_wall_above_terrain"
            else:
                category = "artificial_cutter_top_cap_not_wetted_wall"
            support = support_indices(part, records["cutter"])
            if not support:
                raise ValueError("missing_actual_cutter_triangle_boundary_support")
            rock_support = support_indices(part, records["rock_after"])
            if category == "actual_rock_wet_wall" and not rock_support:
                raise ValueError("unknown_actual_wall_without_saved_rock_triangle_support")
            uv = list(map(list, part.coords))
            pieces.append({"points_uv_m": uv, "points_local_xyz_m": unproject(uv, frame).tolist(), "category": category,
                "potential_wetted_length_m": float(part.length) if category == "actual_rock_wet_wall" else None,
                "source_triangle_indices": {"cutter": support, "rock_after": rock_support}})
    return pieces


def classify_aperture(records, shapes, frame, *, canonical_floor=None):
    cutter, before, after, removed = (shapes[name] for name in ("cutter", "rock_before", "rock_after", "removed"))
    if cutter.is_empty:
        raise ValueError("unknown_no_saved_cutter_aperture")
    if cutter.geom_type != "Polygon" or cutter.interiors:
        raise ValueError("multiple_or_holed_void_aperture_not_certified")
    if removed.geom_type not in ("Polygon",) or removed.interiors:
        raise ValueError("missing_or_multiple_actual_excavation_slice")
    if removed.is_empty and canonical_floor is None:
        raise ValueError("unknown_open_floor_without_actual_excavation_or_canonical_port")
    blocked = float(cutter.intersection(after).area)
    if blocked > AREA_TOLERANCE_M2:
        raise ValueError("actual_rock_after_blocks_face_aperture")
    mismatch = float(removed.symmetric_difference(cutter.intersection(before)).area)
    if mismatch > AREA_TOLERANCE_M2:
        raise ValueError("actual_removed_slice_differs_from_rock_before_cut")
    outside = float(cutter.difference(before).area)
    pieces = boundary_pieces(cutter, before, after, records, frame)
    closed = bool(outside <= AREA_TOLERANCE_M2 and all(piece["category"] == "actual_rock_wet_wall" for piece in pieces))
    floor = lower_floor(cutter)
    if canonical_floor is not None:
        canonical = LineString(canonical_floor)
        if canonical.hausdorff_distance(LineString(floor)) > TOLERANCE_M:
            raise ValueError("canonical_complete_native_floor_not_actual_slice_floor")
        floor = canonical_floor
        closed = False
    if not closed and not floor:
        raise ValueError("unknown_open_aperture_no_floor")
    free_edges = []
    for polygon in ([removed] if not removed.is_empty else []):
        coordinates = list(polygon.exterior.coords)
        for first, second in zip(coordinates, coordinates[1:]):
            edge = LineString([first, second])
            if edge.length > TOLERANCE_M and edge.difference(cutter.boundary.buffer(TOLERANCE_M)).length > TOLERANCE_M:
                free_edges.append({"points_uv_m": [list(first), list(second)], "category": "original_rock_top_opening_free_boundary_not_wall",
                    "rock_before_triangle_indices": support_indices(edge, records["rock_before"])})
    polygon_uv = list(map(list, cutter.exterior.coords))[:-1]
    extensions = [{"u_interval_m": sorted([piece["points_uv_m"][0][0], piece["points_uv_m"][-1][0]]),
        "lower_boundary_uv_m": piece["points_uv_m"], "kind": "above_saved_artificial_cap_only_not_above_actual_rock_roof"}
        for piece in pieces if piece["category"] == "artificial_cutter_top_cap_not_wetted_wall"]
    if not closed and not extensions:
        raise ValueError("unknown_open_face_without_supported_free_top_interval")
    return {"kind": "closed_polygon" if closed else "open_cut_floor", "polygon_uv_m": polygon_uv,
        "polygon_local_xyz_m": unproject(polygon_uv, frame).tolist(), "cut_floor_uv_m": floor,
        "boundary_pieces": pieces, "terrain_opening_free_edges": free_edges,
        "blocked_area_m2": blocked, "removed_replay_difference_area_m2": mismatch,
        "actual_excavated_aperture_area_m2": float(removed.area), "cutter_outside_original_rock_area_m2": outside,
        "bounded_display_aperture_area_m2": float(cutter.area), "pressure_slot_enlarges_face": False,
        "open_extension": None if closed else {"kind": "explicit_engineering_vertical", "lateral_u_m": [floor[0][0], floor[-1][0]],
            "unbounded_above_cut_floor": False, "unbounded_only_over_supported_free_top_intervals": extensions,
            "actual_rock_roof_segments_remain_bounded": True, "artificial_cutter_roof_is_not_flow_ceiling": True,
            "extension_is_engineering_not_whole_physical_path_certification": True,
            "not_actual_terrain_floodplain": True}, "closed_boundary_certified": closed}


def canonical_floor(port, frame):
    floor = []
    if port["status"] != "candidate" or port["rejection_reasons"]:
        raise ValueError("unknown_refused_canonical_port")
    for segment in port["profile"]["profile_segments"]:
        for piece in segment["native_pieces"]:
            coefficients = piece["source"]["source_coefficients_m_t012"]
            cut = piece["depth_coefficients_m_t01"]
            if coefficients[2] != 0. or min(cut[0], cut[0] + cut[1]) < 0 or max(cut[0], cut[0] + cut[1]) > 4:
                raise ValueError("unknown_unsupported_canonical_native_function")
            for fraction, point in ((0., piece["start_xz_m"]), (1., piece["end_xz_m"])):
                world = np.array([point[0], coefficients[0] + fraction * coefficients[1] - cut[0] - fraction * cut[1], point[1]])
                local = world - np.array(frame["common_local_origin_xyz_m"])
                if abs(float((local - frame["origin_local_xyz_m"]) @ frame["normal_local_xyz"])) > TOLERANCE_M:
                    raise ValueError("canonical_floor_not_in_shared_plane")
                uv = project([local], frame)[0].tolist()
                if not floor or math.dist(uv, floor[-1]) > TOLERANCE_M:
                    floor.append(uv)
    floor.sort(key=lambda point: point[0])
    if len(floor) < 4:
        raise ValueError("incomplete_canonical_four_point_profile")
    return floor


def build_faces(geometry, vdm, attachments, ports, meshes):
    common = np.array(meshes["cutter"]["local_origin_xyz_m"], float)
    solids = {name: solid_from_mesh(record, common) for name, record in meshes.items()}
    stations = vdm["stations"]
    cells = {cell["cell_id"]: cell for cell in geometry["hydraulic_cells"]}
    faces = []
    links = geometry["hydraulic_links"]
    if len(stations) != 17 or len(links) != 18:
        raise ValueError("fixed_geometry03_requires_17_stations_18_links")
    for ordinal, link in enumerate(links):
        binding, canonical = None, None
        if ordinal in (0, 17):
            kind = "sink" if ordinal == 0 else "spring"
            station = stations[0 if kind == "sink" else -1]
            port = ports[kind]
            frame = plane_frame(station["origin_xyz_m"], port["flow_unit_xz"], common)
            evidence = attachments["attachments"][kind]
            proof = evidence["actual_complete_port_proof"]
            if (proof["midpoint_port_identity_sha256"] != port["identity_sha256"]
                    or sorted(segment["profile_segment_index"] for segment in proof["segments"]) != [0, 1, 2]
                    or not evidence["half_arm_triangle_indices"] or any(not segment["pieces"] for segment in proof["segments"])):
                raise ValueError("unknown_incomplete_saved_surface_attachment")
            canonical = canonical_floor(port, frame)
            binding = {"kind": kind, "canonical_port_pin": evidence["canonical_port_pin"], "surface_node_pin": evidence["surface_node_pin"],
                "port_identity_sha256": port["identity_sha256"], "actual_complete_port_proof": proof,
                "half_arm_triangle_indices": evidence["half_arm_triangle_indices"], "canonical_floor_uv_m": canonical,
                "hydraulic_boundary_certified": False, "shared_whole_function_not_endpoint_minimum": True}
            orientation_witness = {"canonical_station_id": station["station_id"], "actual_flow_unit_xz": port["flow_unit_xz"],
                "actual_source_arc_xyz_m": port["source_arc_xyz_m"], "not_oblique_endpoint_section_projection": True}
            rule = "actual_canonical_shared_port_plane"
        else:
            first, second = stations[ordinal - 1], stations[ordinal]
            if (link["from_cell_id"], link["to_cell_id"]) != (first["station_id"], second["station_id"]):
                raise ValueError("link_station_order_mismatch")
            first_point, second_point = np.array(first["origin_xyz_m"]), np.array(second["origin_xyz_m"])
            frame = plane_frame((first_point + second_point) / 2., (second_point - first_point)[[0, 2]], common)
            orientation_witness = {"station_ids": [first["station_id"], second["station_id"]],
                "station_origin_world_xyz_m": [first_point.tolist(), second_point.tolist()],
                "normal_rule": "unit_horizontal_discrete_centerline_segment_not_area_cosine_rescale"}
            rule = "actual_adjacent_station_midpoint_XZ_flow_plane"
        roughness = [cells[key]["roughness_manning"] for key in (link["from_cell_id"], link["to_cell_id"])]
        if roughness != [.035, .035] or not math.isfinite(link["length_m"]) or link["length_m"] <= 0:
            raise ValueError("unknown_roughness_or_invalid_original_link_length")
        record = {"schema": FACE_SCHEMA, "face_id": "face:" + str(ordinal), "link_id": link["link_id"],
            "from_cell_id": link["from_cell_id"], "to_cell_id": link["to_cell_id"], "plane": frame, "plane_rule": rule,
            "orientation_witness": orientation_witness,
            "length_m": link["length_m"], "length_source": "unchanged_geometry_hydraulic_link",
            "roughness_manning": .035, "roughness_source_cell_ids": [link["from_cell_id"], link["to_cell_id"]],
            "roughness_binding_only_not_new_face_friction_certification": True,
            "length_binding_only_not_resistance_length_certification": True,
            "additional_step_loss": None, "shared_port_binding": binding, "status": "candidate", "rejection_reasons": []}
        record["hydraulic_use"] = {"status": "needs_info", "discharge_computed": False,
            "required": ["independent_actual_face_geometry_passed", "explicit_face_roughness_adoption",
                "explicit_quasi_steady_resistance_length_policy", "explicit_step_contraction_expansion_loss_policy"],
            "unknown_loss_is_not_zero": True, "unknown_geometry_is_not_closed_zero_flow": True}
        try:
            slices, shapes = {}, {}
            for name in ("cutter", "removed", "rock_before", "rock_after"):
                slices[name], shapes[name] = slice_solid(solids[name], frame, geometry["mesh_pins"][name])
            record["solid_slices"] = slices
            record["aperture"] = classify_aperture(slices, shapes, frame, canonical_floor=canonical)
        except ValueError as error:
            record.update(status="refused", rejection_reasons=[str(error)], unknown_geometry_not_zero_flow=True)
        faces.append(seal(record))
        guard()
    refused = [face["face_id"] for face in faces if face["status"] != "candidate"]
    return seal({"schema": SCHEMA, "status": "refused" if refused else "candidate_unverified", "rejection_reasons": refused,
        "faces": faces, "face_count": len(faces), "geometry_identity_sha256": geometry["identity_sha256"],
        "graph_identity_sha256": geometry["graph_identity_sha256"], "policy": POLICY, "policy_identity_sha256": POLICY_SHA256,
        "independent_audit_passed": False, "hydraulic_solved": False, "native_exact": False,
        "water_discharge_computed": False, "storage_geometry_changed": False, "pressure_slot_enlarges_face": False,
        "actual_peak_rss_bytes": guard()})
