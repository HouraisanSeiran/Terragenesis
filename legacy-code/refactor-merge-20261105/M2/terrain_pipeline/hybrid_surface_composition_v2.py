"""Stage-preserving surface composition with unquantized saved-mesh slices."""

import numpy as np
from shapely.geometry import Polygon

from terrain_pipeline.hybrid_cave_geometry import manifold_from_record, save_manifold
from terrain_pipeline.hybrid_mesh_plane import NUMERICAL_POLICY, NUMERICAL_POLICY_SHA256, slice_solid
from terrain_pipeline.hybrid_river_faces import guard, plane_frame, seal, slice_solid as legacy_slice_solid
from terrain_pipeline.hybrid_river_graph import identity
from terrain_pipeline.hybrid_surface_composition import (
    MAX_BYTES, MAX_TRIANGLES, POLICY as GEOMETRIC_POLICY, canonical_boundary_witness, half_arm_prisms,
    saved_sampling_mismatch_witnesses, volume_ledger)

SCHEMA = "td-hybrid-surface-composition-v2"
POLICY = {**GEOMETRIC_POLICY, "version": "saved-native-halfarm-prism-composition-v2",
    "numerical_slice": NUMERICAL_POLICY_SHA256,
    "failure": "saved_boolean_stage_and_material_before_port_checks_port_failure_preserves_artifacts"}
POLICY_SHA256 = identity(POLICY)


def _solid_slice(solid, frame, name):
    mesh = solid.to_mesh64()
    data = (solid, np.array(mesh.vert_properties[:, :3]), np.array(mesh.tri_verts))
    record, shape = slice_solid(data, frame, {"artifact": name})
    return data, record, shape


def _domain(shape):
    polygons, lines, points = [], [], []
    pending = [shape]
    while pending:
        item = pending.pop()
        if item.is_empty:
            continue
        if item.geom_type == "Polygon":
            polygons.append(item)
        elif item.geom_type in ("LineString", "LinearRing"):
            lines.append(list(map(list, item.coords)))
        elif item.geom_type == "Point":
            points.append(list(item.coords[0]))
        elif item.geom_type in ("MultiPolygon", "MultiLineString", "MultiPoint", "GeometryCollection"):
            pending.extend(reversed(list(item.geoms)))
        else:
            raise ValueError("unsupported_port_domain_geometry:" + item.geom_type)
    return {"polygons_uv_m": [list(map(list, polygon.exterior.coords))[:-1] for polygon in polygons],
        "holes_uv_m": [[list(map(list, hole.coords))[:-1] for hole in polygon.interiors] for polygon in polygons],
        "contact_lines_uv_m": lines, "contact_points_uv_m": points,
        "area_m2": float(shape.area)}


def _portal(kind, station, port, connection, solids, surface, cutter, after, origin, artifacts):
    import manifold3d as manifold
    frame = plane_frame(station["origin_xyz_m"], port["flow_unit_xz"], origin)
    ring = np.asarray(station["derived_ring_xyz_m"])
    horizontal = (ring[:, [0, 2]] - np.asarray(station["origin_xyz_m"])[[0, 2]]) @ np.asarray(frame["transverse_unit_xz"])
    aperture = Polygon(np.column_stack((horizontal, ring[:, 1] - origin[1])))
    connection.update(plane=frame, gallery_aperture_uv_m=list(map(list, aperture.exterior.coords))[:-1],
        exact_solid_slices={}, legacy_quantization_diagnostics={}, hydraulic_boundary_certified=False,
        two_sided_complete_port_verified=False)
    if not aperture.is_valid:
        raise ValueError("invalid_immutable_port_aperture")
    shapes = {}
    for name, solid in solids.items():
        data, record, shapes[name] = _solid_slice(solid, frame, name)
        connection["exact_solid_slices"][name] = record
        try:
            old_record, old_shape = legacy_slice_solid(data, frame, {"artifact": name})
            connection["legacy_quantization_diagnostics"][name] = {
                "legacy_method": old_record["method"], "legacy_domain": _domain(old_shape),
                "legacy_vs_exact_symmetric_difference_area_m2": float(old_shape.symmetric_difference(shapes[name]).area),
                "legacy_blocked_or_missing_area_m2": float(aperture.intersection(old_shape).area
                    if name == "rock_after" else aperture.difference(old_shape).area), "acceptance_use": False}
        except ValueError as error:
            connection["legacy_quantization_diagnostics"][name] = {"diagnostic_error": str(error), "acceptance_use": False}
    blocked = aperture.intersection(shapes["rock_after"])
    missing = aperture.difference(shapes["coupled_cutter"])
    connection.update(exact_blocked_area_m2=float(blocked.area), exact_missing_cutter_area_m2=float(missing.area),
        blocked_domain=_domain(blocked), missing_domain=_domain(missing))
    if blocked.area > 1e-8 or missing.area > 1e-8:
        raise ValueError("actual_full_canonical_port_blocked_or_missing:" + kind)
    epsilon = min(.001, min(item["exterior_support_distance_m"] for witness in connection["canonical_whole_piece_witnesses"]
        for item in witness["supports"]) / 16.)
    connection["epsilon_rule"] = "min_1mm_and_minimum_actual_exterior_support_distance_div16"
    basis = np.array([frame["transverse_unit_xyz"], frame["vertical_unit_xyz"], frame["normal_local_xyz"]]).T
    bounds = aperture.bounds
    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    center = np.array(frame["origin_local_xyz_m"]) + np.array(frame["transverse_unit_xyz"]) * ((bounds[0] + bounds[2]) / 2.)
    center[1] = (bounds[1] + bounds[3]) / 2.
    half_collars = []
    proof = {"sides": {}, "constructed_by_intersecting_actual_cutters_not_new_excavation": True}
    connection["positive_volume_connection"] = proof
    surface_sign = -1. if kind == "sink" else 1.
    for side_name, side_solid, sign in (("surface", surface, surface_sign), ("gallery", cutter, -surface_sign)):
        name = kind + "_" + side_name + "_collar"
        slab_center = center + sign * epsilon / 2. * np.array(frame["normal_local_xyz"])
        transform = np.column_stack((basis, slab_center)).tolist()
        slab = manifold.Manifold.cube([width, height, epsilon], center=True).transform(transform)
        collar = side_solid ^ slab
        side = {"artifact": name, "positive_volume_m3": float(collar.volume()),
            "source_solid": "surface_cutter" if side_name == "surface" else "original_cutter", "normal_side_sign": sign,
            "slab_width_height_depth_m": [width, height, epsilon], "slab_transform_3x4": transform,
            "component_count": len(collar.decompose())}
        proof["sides"][side_name] = side
        if not collar.is_empty():
            artifacts[name] = save_manifold(collar, origin, name)
        if collar.is_empty() or collar.volume() <= 0 or side["component_count"] != 1:
            raise ValueError("missing_positive_volume_full_port_collar:" + kind + ":" + side_name)
        _, record, domain = _solid_slice(collar, frame, name)
        gap = aperture.difference(domain)
        side.update(interface_solid_slice=record, whole_aperture_uncovered_area_m2=float(gap.area), uncovered_domain=_domain(gap))
        if gap.area > 1e-8:
            raise ValueError("whole_port_not_covered_by_both_volume_collars:" + kind + ":" + side_name)
        half_collars.append(collar)
    connected = half_collars[0] + half_collars[1]
    name = kind + "_connected_collar"
    artifacts[name] = save_manifold(connected, origin, name)
    overlap = float((connected ^ after).volume())
    proof.update(connected_collar_artifact=name, component_count=len(connected.decompose()), actual_rock_overlap_volume_m3=overlap)
    if proof["component_count"] != 1 or overlap > 1e-7:
        raise ValueError("actual_full_port_volume_collar_disconnected_or_blocked:" + kind)
    connection["one_sided_diagnostic_traces"] = []
    for offset in (-epsilon, -epsilon / 2., epsilon / 2., epsilon):
        displaced = np.asarray(station["origin_xyz_m"]) + offset * np.asarray(frame["normal_local_xyz"])
        shifted = plane_frame(displaced, port["flow_unit_xz"], origin)
        trace = {"offset_m": offset, "plane": shifted, "solid_slices": {}}
        connection["one_sided_diagnostic_traces"].append(trace)
        for name, solid in solids.items():
            _, record, _ = _solid_slice(solid, shifted, name)
            trace["solid_slices"][name] = record
    connection["two_sided_complete_port_verified"] = True


def build_composition(geometry, vdm, attachments, ports, meshes, nodes, sampling, save_stage=None):
    import manifold3d as manifold
    origin = np.asarray(meshes["rock_before"]["local_origin_xyz_m"])
    if any(record["local_origin_xyz_m"] != origin.tolist() for record in meshes.values()):
        raise ValueError("saved_mesh_common_local_origin_mismatch")
    vertices = np.array([station["derived_ring_xyz_m"] for station in vdm["stations"]]).reshape(-1, 3) - origin
    if not np.array_equal(vertices, meshes["cutter"]["vertices_local_xyz_m"]) or vdm["triangles"] != meshes["cutter"]["triangles"]:
        raise ValueError("immutable_vdm_original_cutter_array_mismatch")
    cap_y = max(max(point[1] for point in meshes[name]["vertices_local_xyz_m"]) + origin[1]
        for name in ("rock_before", "cutter")) + 10.
    surface_solids, surface_records, connections = [], {}, {}
    for kind, ordinal in (("sink", 0), ("spring", len(vdm["stations"]) - 1)):
        attachment = attachments["attachments"][kind]
        bottoms, parts = half_arm_prisms(nodes[kind], attachment, cap_y, origin)
        station = vdm["stations"][ordinal]
        witnesses = canonical_boundary_witness(attachment, bottoms,
            station["derived_ring_xyz_m"][:station["floor_vertex_count"]], ports[kind]["flow_unit_xz"], kind)
        surface_solids.extend(parts)
        surface_records[kind] = {"node_id": nodes[kind]["node_id"], "node_pin": attachment["surface_node_pin"],
            "half_arm_triangle_indices": attachment["half_arm_triangle_indices"], "bottom_triangles": bottoms,
            "immutable_gallery_station_index": ordinal, "immutable_gallery_ring_xyz_m": station["derived_ring_xyz_m"],
            "canonical_whole_piece_witnesses": witnesses}
        connections[kind] = {"canonical_whole_piece_witnesses": witnesses, "immutable_gallery_station_index": ordinal,
            "original_complete_port_proof": attachment["actual_complete_port_proof"],
            "full_shared_interface_supported": True, "offset_traces_are_diagnostic_only": True}
    surface = manifold.Manifold.batch_boolean(surface_solids, manifold.OpType.Add)
    before, cutter, old_after, old_removed = (manifold_from_record(meshes[name])
        for name in ("rock_before", "cutter", "rock_after", "removed"))
    coupled = cutter + surface
    after, removed, extra = before - coupled, before ^ coupled, old_after ^ surface
    if any(solid.status() != manifold.Error.NoError for solid in (surface, coupled, after, removed, extra)):
        raise ValueError("surface_composition_boolean_failed")
    if any(solid.is_empty() for solid in (surface, coupled, after, removed)):
        raise ValueError("missing_surface_composition_solid")
    artifacts = {name: save_manifold(solid, origin, name) for name, solid in
        (("surface_cutter", surface), ("coupled_cutter", coupled), ("rock_after", after), ("removed", removed))}
    artifacts["extra_removed"] = (save_manifold(extra, origin, "extra_removed") if not extra.is_empty() else
        seal({"schema": "td-hybrid-empty-solid-v1", "role": "extra_removed", "local_origin_xyz_m": origin.tolist(),
            "vertices_local_xyz_m": [], "triangles": [], "signed_volume_m3": 0.}))
    artifacts["surface_prisms"] = seal({"schema": "td-hybrid-surface-prisms-v1", "common_local_origin_xyz_m": origin.tolist(),
        "cap_y_world_m": cap_y, "cap_above_saved_rock_and_gallery_margin_m": 10., "half_arms": surface_records,
        "bottom_semantics": GEOMETRIC_POLICY["floor"], "native_exact": False})
    result = {"schema": SCHEMA, "status": "boolean_stage_unverified", "rejection_reasons": [],
        "policy": POLICY, "policy_identity_sha256": POLICY_SHA256,
        "numerical_slice_policy": NUMERICAL_POLICY, "numerical_slice_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
        "geometry_identity_sha256": geometry["identity_sha256"], "graph_identity_sha256": geometry["graph_identity_sha256"],
        "material": volume_ledger(before, old_after, old_removed, after, removed, extra),
        "coupled_cutter_component_count": len(coupled.decompose()),
        "original_source_sampling_cut_lookup_mismatches": saved_sampling_mismatch_witnesses(sampling, attachments, ports),
        "original_sampled_rock_retained_cut_only_not_source_resampling": True,
        "vdm_moved": False, "ports_moved": False, "fill_generated": False, "native_exact": False, "fine15_replaced": False,
        "independent_audit_passed": False, "hydraulic_ready": False, "hydraulic_solved": False, "full_network_verified": False}
    for name, record in artifacts.items():
        if name != "surface_prisms" and len(record["triangles"]) > MAX_TRIANGLES:
            raise ValueError("whole_composition_triangle_budget_exceeded")
    if save_stage is not None:
        result["checkpoint_boolean_pin"] = save_stage(seal(dict(result)), artifacts)
    if result["coupled_cutter_component_count"] != 1:
        result["rejection_reasons"].append("surface_gallery_coupled_cutter_not_one_component")
    solids = {"coupled_cutter": coupled, "rock_after": after, "removed": removed}
    for kind, ordinal in (("sink", 0), ("spring", len(vdm["stations"]) - 1)):
        connection = connections[kind]
        try:
            _portal(kind, vdm["stations"][ordinal], ports[kind], connection, solids, surface, cutter, after, origin, artifacts)
            connection.update(status="verified_geometry_unverified_audit", rejection_reasons=[])
        except ValueError as error:
            connection.update(status="refused", rejection_reasons=[str(error)], two_sided_complete_port_verified=False)
            result["rejection_reasons"].append(kind + ":" + str(error))
    result.update(portal_connections=connections, status="refused" if result["rejection_reasons"] else "candidate_unverified",
        actual_peak_rss_bytes=guard(), boolean_stage_preserved=True)
    return seal(result), artifacts
