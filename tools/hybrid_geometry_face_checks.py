"""Independent current face topology/role/boundary checks, no producer imports."""
import math
import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from tools.hybrid_geometry_audit_base import check_plane, source_canonical_floor, whole_line_supported
from tools.hybrid_geometry_saved_checks import NUMERICAL_POLICY, NUMERICAL_POLICY_SHA256, audit_exact_slice, independent_triangle_trace
from tools.hybrid_exact_solid_saved_audit import ExactSolid as Solid
from tools.td_shared_channel_fine_saved_audit import check_identity, check_memory, compare, digest, read, require


def topology_roles(vdm, mesh):
    stations = vdm["stations"]
    sizes = {len(item["derived_ring_xyz_m"]) for item in stations}
    floors = {item["floor_vertex_count"] for item in stations}
    require(len(sizes) == len(floors) == 1 and len(stations) == 17, "unsupported original chart topology")
    count, floor = next(iter(sizes)), next(iter(floors))
    require(count == floor + 2 and floor >= 2, "unsupported floor/roof chart")
    points = np.asarray([item["derived_ring_xyz_m"] for item in stations], float).reshape(-1, 3)
    compare(mesh["vertices_local_xyz_m"], points - np.asarray(mesh["local_origin_xyz_m"]),
            "immutable VDM/cutter vertices", atol=0.)
    require(mesh["triangles"] == vdm["triangles"], "immutable VDM/cutter triangles")
    roles = []
    for ordinal, triangle in enumerate(mesh["triangles"]):
        station_ids = sorted({vertex // count for vertex in triangle})
        offsets = {vertex % count for vertex in triangle}
        if len(station_ids) == 1:
            require(station_ids in ([0], [len(stations) - 1]), "interior cap not supported")
            edge, role = None, "endcap"
        else:
            require(len(station_ids) == 2 and station_ids[1] == station_ids[0] + 1, "nonadjacent source stations")
            edges = [edge for edge in range(count) if {(edge + 1) % count, edge} == offsets]
            require(len(edges) == 1, "invalid ring edge topology")
            edge = edges[0]
            if edge < floor - 1:
                role = "floor"
            elif edge == floor:
                role = "roof"
            else:
                role = "lateral"
        roles.append({"triangle_index": ordinal, "source_role": role, "ring_edge_index": edge,
                      "station_indices": station_ids, "vertex_indices": triangle})
    return roles


def audit_role_slice(record, frame, original_mesh, original_pin, vdm, prisms, prism_pin):
    require(record["numerical_policy"] == NUMERICAL_POLICY
            and record["numerical_policy_identity_sha256"] == NUMERICAL_POLICY_SHA256,
            "role numerical policy substituted")
    if record["role_rule"] == "station_major_floor_vertex_count_not_edge_slope":
        require(record["mesh_pin"] == original_pin, "original role source substituted")
        mesh, roles = original_mesh, topology_roles(vdm, original_mesh)
    else:
        require(record["role_rule"] == "audited_saved_triangular_prism_topology"
                and record["mesh_pin"] == prism_pin, "unsupported role source")
        witnesses = record["triangle_segments"] + record["coplanar_triangle_supports"]
        require(witnesses, "empty role slice")
        binding = witnesses[0]["role_provenance"]
        kind, bottom_id = binding["half_arm_kind"], binding["bottom_triangle_id"]
        require(kind in ("sink", "spring"), "unknown prism half-arm")
        candidates = [item for item in prisms["half_arms"][kind]["bottom_triangles"]
                      if item["bottom_triangle_id"] == bottom_id]
        require(len(candidates) == 1, "ambiguous prism source")
        bottom, roles = candidates[0], []
        mesh = bottom["prism"]
        check_identity(mesh)
        require(len(mesh["triangles"]) == 8
                and bottom["prism_triangle_roles"] == ["floor", "artificial_top_cap"] + ["lateral"] * 6,
                "invalid saved prism topology")
        for ordinal, triangle in enumerate(mesh["triangles"]):
            source_role = "floor" if ordinal == 0 else "roof" if ordinal == 1 else "lateral"
            roles.append({"triangle_index": ordinal, "source_role": source_role,
                          "original_prism_role": bottom["prism_triangle_roles"][ordinal],
                          "half_arm_kind": kind, "bottom_triangle_id": bottom_id, "fan_key": bottom["fan_key"],
                          "source_function_identity_sha256": bottom["source_function_identity_sha256"],
                          "prism_identity_sha256": mesh["identity_sha256"], "vertex_indices": triangle})
    points = np.asarray(mesh["vertices_local_xyz_m"]) + (np.asarray(mesh["local_origin_xyz_m"])
        - np.asarray(frame["common_local_origin_xyz_m"]))
    origin, normal, transverse = [np.asarray(frame[key]) for key in
                                  ("origin_local_xyz_m", "normal_local_xyz", "transverse_unit_xyz")]
    role_solid = Solid(points, mesh["triangles"], "saved topology role source")
    _, segments, coplanar, _ = independent_triangle_trace(role_solid, frame)
    saved = record["triangle_segments"]
    require(len(saved) == len(segments) and {item["triangle_index"] for item in saved} == set(segments),
            "role line census differs")
    lines = {}
    for item in saved:
        ordinal = item["triangle_index"]
        expected = segments[ordinal]
        require(item["vertex_indices"] == mesh["triangles"][ordinal]
                and item["role_provenance"] == roles[ordinal] and item["source_role"] == roles[ordinal]["source_role"],
                "fabricated topology role")
        require(set(item) == set(expected) | {"source_role", "role_provenance"}
                and all(item[key] == value for key, value in expected.items()),
            "role source intersection identity or incident side differs")
        line = LineString(item["points_uv_m"])
        require(line.hausdorff_distance(LineString(segments[ordinal]["points_uv_m"])) <= 1e-8,
                "fabricated role support segment")
        uv = np.asarray(item["points_uv_m"])
        xyz = origin + uv[:, :1] * transverse
        xyz[:, 1] = uv[:, 1]
        compare(item["points_local_xyz_m"], xyz, "role segment frame", atol=1e-8)
        lines[ordinal] = (line, roles[ordinal])
    expected_caps = {}
    for ordinal, item in coplanar.items():
        expected_caps[ordinal] = Polygon(item["polygon_uv_m"])
    saved_caps = record["coplanar_triangle_supports"]
    require(len(saved_caps) == len(expected_caps)
            and {item["triangle_index"] for item in saved_caps} == set(expected_caps), "role cap census differs")
    for item in saved_caps:
        ordinal = item["triangle_index"]
        expected = coplanar[ordinal]
        require(item["role_provenance"] == roles[ordinal] and item["source_role"] == roles[ordinal]["source_role"]
                and item["vertex_indices"] == mesh["triangles"][ordinal]
                and Polygon(item["polygon_uv_m"]).symmetric_difference(expected_caps[ordinal]).area <= 1e-8,
                "fabricated coplanar topology role")
        require(set(item) == set(expected) | {"source_role", "role_provenance"}
                and all(item[key] == value for key, value in expected.items()),
            "role source coplanar identity or occupied side differs")
    return lines


def audit_boundary(aperture, shapes, slices, role_lines, frame):
    cutter, before, after, removed = [shapes[key] for key in ("cutter", "rock_before", "rock_after", "removed")]
    require(cutter.geom_type == "Polygon" and not cutter.is_empty and not cutter.interiors,
            "unknown/multiple fluid aperture")
    polygon = Polygon(aperture["polygon_uv_m"])
    require(polygon.is_valid and polygon.symmetric_difference(cutter).area <= 1e-8
            and aperture["polygon_authoritative"] is True and aperture["floor_height_function_required"] is False,
            "actual polygon replaced by height function")
    require(aperture["pressure_slot_enlarges_face"] is False and cutter.intersection(after).area <= 1e-8,
            "actual rock blocks fluid aperture or storage slot enlarges face")
    replay = removed.symmetric_difference(cutter.intersection(before)).area
    require(replay <= 1e-8, "removed material not actual Boolean slice")
    bounds = {role: record["projection_area_error_bound_m2"] for role, record in slices.items()}
    blocked_upper = math.nextafter(math.fsum((cutter.intersection(after).area,
                                           bounds["cutter"], bounds["rock_after"])), math.inf)
    replay_upper = math.nextafter(math.fsum((replay, bounds["removed"],
                                          bounds["cutter"], bounds["rock_before"])), math.inf)
    require(aperture["projection_area_error_bounds_m2"] == bounds
            and aperture["blocked_area_upper_bound_m2"] == blocked_upper
            and aperture["removed_replay_difference_area_upper_bound_m2"] == replay_upper
            and blocked_upper <= 1e-8 and replay_upper <= 1e-8,
            "face projection error or conservative acceptance bound differs")
    for key, expected in (("blocked_area_m2", cutter.intersection(after).area),
                          ("removed_replay_difference_area_m2", replay),
                          ("bounded_display_aperture_area_m2", cutter.area),
                          ("actual_excavated_aperture_area_m2", removed.area)):
        compare(aperture[key], expected, key, atol=1e-8)
    components = len(removed.geoms) if removed.geom_type == "MultiPolygon" else int(not removed.is_empty)
    require(aperture["material_component_count"] == components
            and aperture["material_components_do_not_certify_fluid_connectivity"] is True,
            "material components confused with fluid connectivity")
    origin, transverse = np.asarray(frame["origin_local_xyz_m"]), np.asarray(frame["transverse_unit_xyz"])
    uv = np.asarray(aperture["polygon_uv_m"])
    xyz = origin + uv[:, :1] * transverse
    xyz[:, 1] = uv[:, 1]
    compare(aperture["polygon_local_xyz_m"], xyz, "polygon frame", atol=1e-8)
    lines, floors, tops, wet_lengths = [], [], [], []
    for piece in aperture["boundary_pieces"]:
        line = LineString(piece["points_uv_m"])
        require(line.length > 1e-8 and whole_line_supported(line, cutter.boundary), "fabricated aperture boundary")
        uv = np.asarray(piece["points_uv_m"])
        xyz = origin + uv[:, :1] * transverse
        xyz[:, 1] = uv[:, 1]
        compare(piece["points_local_xyz_m"], xyz, "boundary frame", atol=1e-8)
        support = []
        for reference in piece["source_role_support"]:
            source_index, ordinal = reference["source_index"], reference["triangle_index"]
            require(type(source_index) is int and 0 <= source_index < len(role_lines)
                    and ordinal in role_lines[source_index], "unknown role support reference")
            source_line, source_role = role_lines[source_index][ordinal]
            require(reference == {"source_index": source_index, **source_role}
                    and source_role["source_role"] != "endcap", "endcap/fabricated source counted as wall")
            support.append(source_line)
        require(support and whole_line_supported(line, unary_union(support)), "whole boundary missing role support")
        roles = {reference["source_role"] for reference in piece["source_role_support"]}
        require(roles == {piece["source_role"]}, "ambiguous source role")
        wall = before.buffer(1e-8).covers(line) and whole_line_supported(line, after.boundary)
        expected = "actual_rock_wet_wall" if wall else {
            "floor": "saved_cut_floor_open_air_side", "lateral": "engineering_lateral_wall_above_terrain",
            "roof": "artificial_cutter_top_cap_not_wetted_wall"}[piece["source_role"]]
        require(wall or not before.buffer(1e-8).covers(line), "inside-rock boundary missing actual wall")
        require(piece["physical_exposure"] == piece["category"] == expected, "incorrect physical exposure")
        if wall:
            compare(piece["potential_wetted_length_m"], line.length, "actual wet wall", atol=1e-8)
            wet_lengths.append(line.length)
        else:
            require(piece["potential_wetted_length_m"] is None, "artificial/free edge counted as actual wet wall")
        for role in ("cutter", "rock_after"):
            ids = piece["source_triangle_indices"][role]
            require(len(ids) == len(set(ids)), "duplicate wall triangle refs")
            supports = [LineString(item["points_uv_m"]) for item in slices[role]["triangle_segments"]
                        if item["triangle_index"] in ids]
            supports.extend(Polygon(item["polygon_uv_m"]) for item in slices[role]["coplanar_triangle_supports"]
                            if item["triangle_index"] in ids)
            available = {item["triangle_index"] for item in slices[role]["triangle_segments"] + slices[role]["coplanar_triangle_supports"]}
            require(set(ids) <= available, "wall refs nonintersecting triangles")
            if role == "cutter" or wall:
                require(supports and whole_line_supported(line, unary_union(supports)), "whole wall lacks actual source triangles")
        lines.append(line)
        if piece["source_role"] == "floor":
            floors.append(piece["points_uv_m"])
        if expected == "artificial_cutter_top_cap_not_wetted_wall":
            tops.append({"points_uv_m": piece["points_uv_m"],
                         "u_interval_m": sorted((piece["points_uv_m"][0][0], piece["points_uv_m"][-1][0])),
                         "source_role_support": piece["source_role_support"]})
    require(lines and whole_line_supported(cutter.boundary, unary_union(lines))
            and abs(math.fsum(line.length for line in lines) - unary_union(lines).length) <= 1e-8,
            "missing/duplicate aperture boundary")
    closed = len(wet_lengths) == len(lines)
    require(aperture["closed_boundary_certified"] is closed
            and aperture["kind"] == ("closed_polygon" if closed else "open_actual_polygon")
            and floors == aperture["floor_boundary_pieces_uv_m"] and floors, "actual boundary classification differs")
    expected_extension = None if closed else {
        "kind": "explicit_engineering_supported_top_intervals_only", "unbounded_above_cut_floor": False,
        "supported_free_top_intervals": tops, "actual_rock_roof_segments_remain_bounded": True,
        "extension_is_not_physical_path_certification": True}
    require(aperture["open_extension"] == expected_extension and (closed or tops), "unsupported engineering extension")
    return {"kind": aperture["kind"], "area_m2": cutter.area,
            "actual_rock_wet_wall_length_m": math.fsum(wet_lengths), "boundary_piece_count": len(lines),
            "polygon_and_source_roles_verified": True}
