"""Actual polygon faces with topology-derived roles and audited coupled port evidence."""

import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon

from terrain_pipeline.hybrid_geometry_common import (
    AREA_TOLERANCE_M2, MAX_BYTES, MAX_RSS, TOLERANCE_M, canonical_floor,
    guard, plane_frame, project, seal, solid_from_mesh,
    support_indices, unproject)
from terrain_pipeline.hybrid_mesh_plane_v2 import (
    NUMERICAL_POLICY, NUMERICAL_POLICY_SHA256, slice_solid, triangle_supports)
from terrain_pipeline.hybrid_river_graph import identity

SCHEMA = "td-hybrid-river-faces-v2"
FACE_SCHEMA = "td-hybrid-river-face-v2"
ROLES = frozenset(("floor", "lateral", "roof", "endcap"))
POLICY = {"version": "actual_polygon_topology_coupled_link_faces-v2",
          "geometry": "actual_coupled_saved_solid_slices_polygon_authoritative_no_height_function",
          "numerical_slice": "td-hybrid-exact-mesh-plane-slice-v2_rational_loops_explicit_projection_collapse_no_CrossSection",
          "coordinates": "common_local_XYZ_metres_face_u_Ylocal",
          "source_role": "original_station_major_VDM_triangle_or_audited_surface_prism_triangle",
          "physical_exposure": "actual_rock_wall_or_saved_open_boundary_separate_from_source_role",
          "canonical": "independent_composition_complete_two_sided_port_proof_required_no_cap_deletion",
          "composition": "independently_audited_v3_saved_stage_replay_original_geometry_and_main_mesh_pins_unchanged",
          "removed": "multiple_material_components_allowed_only_with_exact_boolean_replay_not_fluid_connectivity",
          "unknown": "refused_not_zero_flow",
          "slot": "storage_only_never_enlarges_face",
          "hydraulics": "needs_info_no_law_no_solver_no_Q"}
POLICY_SHA256 = identity(POLICY)


def vdm_role_source(vdm, mesh, common_origin, mesh_pin):
    stations = vdm["stations"]
    if len(stations) < 2:
        raise ValueError("unknown_incomplete_station_major_VDM")
    counts = {len(station["derived_ring_xyz_m"]) for station in stations}
    floors = {station["floor_vertex_count"] for station in stations}
    if len(counts) != 1 or len(floors) != 1:
        raise ValueError("unknown_variable_ring_topology")
    count, floor_count = counts.pop(), floors.pop()
    if floor_count < 2 or count != floor_count + 2:
        raise ValueError("unknown_ring_floor_lateral_roof_topology")
    points = np.asarray([station["derived_ring_xyz_m"] for station in stations], float).reshape(-1, 3)
    saved = np.asarray(mesh["vertices_local_xyz_m"], float)
    triangles = np.asarray(mesh["triangles"], int)
    if (points.shape != saved.shape or not np.array_equal(points - np.asarray(mesh["local_origin_xyz_m"], float), saved)
            or triangles.shape != np.asarray(vdm["triangles"]).shape
            or not np.array_equal(triangles, vdm["triangles"])):
        raise ValueError("original_cutter_not_immutable_station_major_VDM")
    roles = []
    for ordinal, triangle in enumerate(triangles):
        station_ids = set(int(vertex) // count for vertex in triangle)
        offsets = set(int(vertex) % count for vertex in triangle)
        if len(station_ids) == 1:
            if station_ids not in ({0}, {len(stations) - 1}):
                raise ValueError("unknown_interior_station_cap")
            role = "endcap"
            ring_edge = None
        else:
            if len(station_ids) != 2 or max(station_ids) - min(station_ids) != 1:
                raise ValueError("nonadjacent_station_triangle_not_supported")
            edges = [edge for edge in range(count) if offsets == {edge, (edge + 1) % count}]
            if len(edges) != 1:
                raise ValueError("unknown_triangle_ring_edge")
            ring_edge = edges[0]
            role = "floor" if ring_edge < floor_count - 1 else "roof" if ring_edge == floor_count else "lateral"
        roles.append({"triangle_index": ordinal, "source_role": role, "ring_edge_index": ring_edge,
                      "station_indices": sorted(station_ids), "vertex_indices": triangle.tolist()})
    return {"mesh_pin": mesh_pin, "points_local_xyz_m": points - np.asarray(common_origin),
            "triangles": triangles, "triangle_roles": roles,
            "role_rule": "station_major_floor_vertex_count_not_edge_slope"}


def surface_role_sources(prisms, common_origin, prism_pin):
    sources = []
    triangle_count = 0
    for kind in ("sink", "spring"):
        for bottom in prisms["half_arms"][kind]["bottom_triangles"]:
            mesh = bottom["prism"]
            points = np.asarray(mesh["vertices_local_xyz_m"], float)
            triangles = np.asarray(mesh["triangles"], int)
            roles = bottom["prism_triangle_roles"]
            if (points.shape != (6, 3) or triangles.shape != (8, 3)
                    or roles != ["floor", "artificial_top_cap"] + ["lateral"] * 6
                    or not np.isfinite(points).all()):
                raise ValueError("unknown_surface_prism_role_topology")
            world_bottom = np.asarray(bottom["bottom_vertices_xyz_m"], float)
            if not np.array_equal(world_bottom - np.asarray(mesh["local_origin_xyz_m"]), points[:3]):
                raise ValueError("surface_role_floor_not_actual_saved_bottom")
            sources.append({"mesh_pin": prism_pin,
                "points_local_xyz_m": points + (np.asarray(mesh["local_origin_xyz_m"]) - np.asarray(common_origin)),
                "triangles": triangles, "role_rule": "audited_saved_triangular_prism_topology",
                "triangle_roles": [{"triangle_index": ordinal, "source_role": "roof" if role == "artificial_top_cap" else role,
                    "original_prism_role": role, "half_arm_kind": kind, "bottom_triangle_id": bottom["bottom_triangle_id"],
                    "fan_key": bottom["fan_key"], "source_function_identity_sha256": bottom["source_function_identity_sha256"],
                    "prism_identity_sha256": mesh["identity_sha256"], "vertex_indices": triangles[ordinal].tolist()}
                    for ordinal, role in enumerate(roles)]})
            triangle_count += len(triangles)
            if triangle_count > 200000:
                raise ValueError("whole_surface_role_triangle_budget_exceeded")
    return sources


def role_slice(source, frame):
    segments, coplanar = triangle_supports(source["points_local_xyz_m"], source["triangles"], frame)
    roles = {item["triangle_index"]: item for item in source["triangle_roles"]}
    if set(roles) != set(range(len(source["triangles"]))):
        raise ValueError("unknown_incomplete_source_triangle_roles")
    for collection in (segments, coplanar):
        for item in collection:
            role = roles[item["triangle_index"]]
            if role["source_role"] not in ROLES:
                raise ValueError("unsupported_saved_source_role")
            item["source_role"] = role["source_role"]
            item["role_provenance"] = role
    return {"mesh_pin": source["mesh_pin"], "role_rule": source["role_rule"],
            "numerical_policy": NUMERICAL_POLICY, "numerical_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
            "triangle_segments": segments, "coplanar_triangle_supports": coplanar}


def boundary_parts(polygon, before, after, slices, role_slices, frame):
    sources = [(source_index, item) for source_index, record in enumerate(role_slices)
               for item in record["triangle_segments"] if item["source_role"] != "endcap"]
    pieces = []
    coordinates = list(polygon.exterior.coords)
    for first, second in zip(coordinates, coordinates[1:]):
        line = LineString((first, second))
        if line.length <= TOLERANCE_M:
            continue
        points = []
        pending = [line.intersection(before.boundary), line.intersection(after.boundary)]
        for source_index, item in sources:
            source_line = LineString(item["points_uv_m"])
            if line.distance(source_line) <= TOLERANCE_M:
                points.extend(Point(point) for point in source_line.coords if line.distance(Point(point)) <= TOLERANCE_M)
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
            part = LineString((line.interpolate(lower, normalized=True), line.interpolate(upper, normalized=True)))
            if part.length <= TOLERANCE_M:
                continue
            support = [(source_index, item) for source_index, item in sources
                       if part.difference(LineString(item["points_uv_m"]).buffer(TOLERANCE_M)).length <= TOLERANCE_M]
            roles = {item["source_role"] for source_index, item in support}
            if len(roles) != 1:
                raise ValueError("unknown_or_ambiguous_actual_boundary_source_role")
            role = roles.pop()
            inside = before.buffer(TOLERANCE_M).covers(part)
            wall = inside and part.difference(after.boundary.buffer(TOLERANCE_M)).length <= TOLERANCE_M
            if wall:
                category = "actual_rock_wet_wall"
            elif inside:
                raise ValueError("unknown_inside_rock_boundary_without_after_wall")
            else:
                category = {"floor": "saved_cut_floor_open_air_side",
                            "lateral": "engineering_lateral_wall_above_terrain",
                            "roof": "artificial_cutter_top_cap_not_wetted_wall"}[role]
            cutter_support = support_indices(part, slices["cutter"])
            rock_support = support_indices(part, slices["rock_after"])
            if not cutter_support or (wall and not rock_support):
                raise ValueError("actual_polygon_boundary_missing_saved_triangle_support")
            uv = list(map(list, part.coords))
            pieces.append({"points_uv_m": uv, "points_local_xyz_m": unproject(uv, frame).tolist(),
                           "source_role": role, "physical_exposure": category, "category": category,
                           "source_role_support": [{"source_index": source_index, **item["role_provenance"]}
                                                   for source_index, item in support],
                           "source_triangle_indices": {"cutter": cutter_support, "rock_after": rock_support},
                           "potential_wetted_length_m": float(part.length) if wall else None})
    if not pieces:
        raise ValueError("unknown_empty_actual_polygon_boundary")
    return pieces


def classify_aperture(slices, shapes, role_slices, frame, canonical_profile=None, port_evidence=None):
    cutter, before, after, removed = (shapes[name] for name in ("cutter", "rock_before", "rock_after", "removed"))
    if cutter.is_empty or cutter.geom_type != "Polygon" or cutter.interiors or not cutter.is_valid:
        raise ValueError("unknown_or_multiple_or_holed_actual_fluid_domain")
    if removed.geom_type not in ("Polygon", "MultiPolygon") and not removed.is_empty:
        raise ValueError("unknown_nonpolygon_material_slice")
    blocked = float(cutter.intersection(after).area)
    mismatch = float(removed.symmetric_difference(cutter.intersection(before)).area)
    projection_bounds = {name: record["projection_area_error_bound_m2"] for name, record in slices.items()}
    if any(not math.isfinite(value) or not 0 <= value <= AREA_TOLERANCE_M2
           for value in projection_bounds.values()):
        raise ValueError("actual_slice_projection_error_bound_invalid")
    blocked_upper = math.nextafter(math.fsum((blocked, projection_bounds["cutter"], projection_bounds["rock_after"])), math.inf)
    mismatch_upper = math.nextafter(math.fsum((mismatch, *(projection_bounds[name]
        for name in ("removed", "cutter", "rock_before")))), math.inf)
    if blocked_upper > AREA_TOLERANCE_M2:
        raise ValueError("actual_rock_after_blocks_face_no_cap_deletion")
    if mismatch_upper > AREA_TOLERANCE_M2:
        raise ValueError("actual_total_removed_slice_boolean_mismatch")
    if canonical_profile is not None:
        if not port_evidence or not port_evidence.get("two_sided_complete_port_verified"):
            raise ValueError("unknown_canonical_two_sided_complete_port")
        if LineString(canonical_profile).difference(cutter.boundary.buffer(TOLERANCE_M)).length > TOLERANCE_M:
            raise ValueError("canonical_native_profile_not_actual_polygon_boundary")
    pieces = boundary_parts(cutter, before, after, slices, role_slices, frame)
    closed = all(piece["physical_exposure"] == "actual_rock_wet_wall" for piece in pieces)
    extensions = [{"points_uv_m": piece["points_uv_m"], "u_interval_m": sorted((piece["points_uv_m"][0][0], piece["points_uv_m"][-1][0])),
                   "source_role_support": piece["source_role_support"]}
                  for piece in pieces if piece["physical_exposure"] == "artificial_cutter_top_cap_not_wetted_wall"]
    if not closed and not extensions:
        raise ValueError("unknown_open_face_without_topology_supported_free_top_interval")
    floor_pieces = [piece["points_uv_m"] for piece in pieces if piece["source_role"] == "floor"]
    if not floor_pieces:
        raise ValueError("unknown_missing_actual_topological_floor")
    return {"kind": "closed_polygon" if closed else "open_actual_polygon",
            "polygon_uv_m": list(map(list, cutter.exterior.coords))[:-1],
            "polygon_local_xyz_m": unproject(list(cutter.exterior.coords)[:-1], frame).tolist(),
            "boundary_pieces": pieces, "floor_boundary_pieces_uv_m": floor_pieces,
            "polygon_authoritative": True, "floor_height_function_required": False,
            "blocked_area_m2": blocked, "removed_replay_difference_area_m2": mismatch,
            "blocked_area_upper_bound_m2": blocked_upper,
            "removed_replay_difference_area_upper_bound_m2": mismatch_upper,
            "projection_area_error_bounds_m2": projection_bounds,
            "material_component_count": len(removed.geoms) if removed.geom_type == "MultiPolygon" else int(not removed.is_empty),
            "material_components_do_not_certify_fluid_connectivity": True,
            "bounded_display_aperture_area_m2": float(cutter.area), "actual_excavated_aperture_area_m2": float(removed.area),
            "pressure_slot_enlarges_face": False, "closed_boundary_certified": closed,
            "canonical_two_sided_evidence": port_evidence,
            "open_extension": None if closed else {"kind": "explicit_engineering_supported_top_intervals_only",
                "unbounded_above_cut_floor": False, "supported_free_top_intervals": extensions,
                "actual_rock_roof_segments_remain_bounded": True, "extension_is_not_physical_path_certification": True}}


def build_faces(geometry, vdm, attachments, ports, meshes, composition, composition_audit, prisms, audit_pin):
    common = np.asarray(meshes["cutter"]["local_origin_xyz_m"], float)
    solids = {name: solid_from_mesh(meshes[name], common) for name in ("cutter", "removed", "rock_before", "rock_after")}
    role_sources = [vdm_role_source(vdm, meshes["original_cutter"], common, composition["mesh_pins"]["original_cutter"])]
    role_sources.extend(surface_role_sources(prisms, common, composition["surface_prisms_pin"]))
    stations = vdm["stations"]
    links = geometry["hydraulic_links"]
    cells = {cell["cell_id"]: cell for cell in geometry["hydraulic_cells"]}
    if len(stations) != 17 or len(links) != 18:
        raise ValueError("fixed_original_route_requires_17_stations_18_links")
    pins = {name: composition["mesh_pins"]["coupled_cutter" if name == "cutter" else name]
            for name in ("cutter", "removed", "rock_before", "rock_after")}
    faces = []
    for ordinal, link in enumerate(links):
        canonical, binding, evidence = None, None, None
        if ordinal in (0, 17):
            kind = "sink" if ordinal == 0 else "spring"
            station = stations[0 if kind == "sink" else -1]
            port = ports[kind]
            frame = plane_frame(station["origin_xyz_m"], port["flow_unit_xz"], common)
            attachment = attachments["attachments"][kind]
            proof = attachment["actual_complete_port_proof"]
            if (proof["midpoint_port_identity_sha256"] != port["identity_sha256"]
                    or sorted(segment["profile_segment_index"] for segment in proof["segments"]) != [0, 1, 2]
                    or not attachment["half_arm_triangle_indices"] or any(not segment["pieces"] for segment in proof["segments"])):
                raise ValueError("unknown_incomplete_original_canonical_attachment")
            canonical = canonical_floor(port, frame)
            binding = {"kind": kind, "canonical_port_pin": attachment["canonical_port_pin"],
                       "surface_node_pin": attachment["surface_node_pin"], "port_identity_sha256": port["identity_sha256"],
                       "actual_complete_port_proof": proof, "half_arm_triangle_indices": attachment["half_arm_triangle_indices"],
                       "canonical_profile_uv_m": canonical, "hydraulic_boundary_certified": False}
            evidence = {"composition_audit_pin": audit_pin, "kind": kind,
                        "two_sided_complete_port_verified": bool(composition_audit.get("two_sided_complete_port_verified", False)
                            and composition_audit.get("portal_reports", {}).get(kind, {}).get("verified", False)
                            and composition_audit.get("portal_reports", {}).get(kind, {}).get("two_sided_complete_port_verified", False)),
                        "independent_port_report": composition_audit.get("portal_reports", {}).get(kind),
                        "composition_portal_connection": composition["portal_connections"].get(kind),
                        "no_endcap_deleted": True, "offset_traces_are_diagnostic_only": True}
            orientation = {"canonical_station_id": station["station_id"], "flow_unit_xz": port["flow_unit_xz"]}
            rule = "immutable_canonical_shared_port_with_audited_actual_two_sided_volume"
        else:
            first, second = stations[ordinal - 1], stations[ordinal]
            if (link["from_cell_id"], link["to_cell_id"]) != (first["station_id"], second["station_id"]):
                raise ValueError("original_link_station_order_mismatch")
            first_point, second_point = np.asarray(first["origin_xyz_m"]), np.asarray(second["origin_xyz_m"])
            frame = plane_frame((first_point + second_point) / 2, (second_point - first_point)[[0, 2]], common)
            orientation = {"station_ids": [first["station_id"], second["station_id"]],
                           "station_origin_world_xyz_m": [first_point.tolist(), second_point.tolist()]}
            rule = "actual_adjacent_station_midpoint_XZ_flow_plane"
        if ([cells[key]["roughness_manning"] for key in (link["from_cell_id"], link["to_cell_id"])] != [.035, .035]
                or not math.isfinite(link["length_m"]) or link["length_m"] <= 0):
            raise ValueError("unknown_original_roughness_or_link_length")
        record = {"schema": FACE_SCHEMA, "face_id": "face:" + str(ordinal), "link_id": link["link_id"],
                  "from_cell_id": link["from_cell_id"], "to_cell_id": link["to_cell_id"],
                  "plane": frame, "plane_rule": rule, "orientation_witness": orientation,
                  "roughness_manning": .035, "roughness_source_cell_ids": [link["from_cell_id"], link["to_cell_id"]],
                  "length_m": link["length_m"], "length_source": "unchanged_original_geometry_hydraulic_link",
                  "roughness_binding_only_not_new_face_friction_certification": True,
                  "length_binding_only_not_resistance_length_certification": True,
                  "numerical_slice_policy": composition["numerical_slice_policy"],
                  "numerical_slice_policy_identity_sha256": composition["numerical_slice_policy_identity_sha256"],
                  "additional_step_loss": None, "shared_port_binding": binding,
                  "status": "candidate", "rejection_reasons": [],
                  "hydraulic_use": {"status": "needs_info", "discharge_computed": False,
                      "unknown_loss_is_not_zero": True, "unknown_geometry_is_not_closed_zero_flow": True,
                      "required": ["independent_actual_face_geometry_passed", "explicit_face_roughness_adoption",
                                   "explicit_quasi_steady_resistance_length_policy", "explicit_step_contraction_expansion_loss_policy"]}}
        try:
            slices, shapes = {}, {}
            for name, solid in solids.items():
                slices[name], shapes[name] = slice_solid(solid, frame, pins[name])
                if (slices[name]["schema"] != "td-hybrid-exact-mesh-plane-slice-v2"
                        or slices[name]["numerical_policy"] != composition["numerical_slice_policy"]
                        or slices[name]["numerical_policy_identity_sha256"] != NUMERICAL_POLICY_SHA256
                        or slices[name]["display_projection_certified"] is not True
                        or not math.isfinite(slices[name]["projection_area_error_bound_m2"])
                        or not 0 <= slices[name]["projection_area_error_bound_m2"] <= AREA_TOLERANCE_M2):
                    raise ValueError("actual_slice_numerical_policy_differs_from_audited_composition")
            record["solid_slices"] = slices
            roles = [role_slice(source, frame) for source in role_sources]
            roles = [source for source in roles if source["triangle_segments"] or source["coplanar_triangle_supports"]]
            if any(source["numerical_policy_identity_sha256"] != composition["numerical_slice_policy_identity_sha256"] for source in roles):
                raise ValueError("source_role_exact_slice_policy_differs_from_composition")
            record["source_role_slices"] = roles
            record["aperture"] = classify_aperture(slices, shapes, roles, frame, canonical, evidence)
        except ValueError as error:
            record.update(status="refused", rejection_reasons=[str(error)], unknown_geometry_not_zero_flow=True)
        faces.append(seal(record))
        guard()
    refused = [face["face_id"] for face in faces if face["status"] != "candidate"]
    return seal({"schema": SCHEMA, "status": "refused" if refused else "candidate_unverified",
                 "faces": faces, "face_count": len(faces), "rejection_reasons": refused,
                 "geometry_identity_sha256": geometry["identity_sha256"], "graph_identity_sha256": geometry["graph_identity_sha256"],
                 "composition_identity_sha256": composition["identity_sha256"], "policy": POLICY, "policy_identity_sha256": POLICY_SHA256,
                 "stage_lineage": composition["stage_lineage"],
                 "numerical_slice_policy": composition["numerical_slice_policy"],
                 "numerical_slice_policy_identity_sha256": composition["numerical_slice_policy_identity_sha256"],
                 "independent_audit_passed": False, "hydraulic_solved": False, "water_discharge_computed": False,
                 "storage_geometry_changed": False, "pressure_slot_enlarges_face": False, "native_exact": False,
                 "actual_peak_rss_bytes": guard()})
