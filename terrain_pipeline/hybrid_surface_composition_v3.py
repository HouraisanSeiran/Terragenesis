"""Resume saved Boolean geometry; rational topology and bounded portal collars only."""

import math
import numpy as np
from shapely.geometry import Polygon

from terrain_pipeline.hybrid_cave_geometry import manifold_from_record, save_manifold
from terrain_pipeline.hybrid_mesh_plane_v2 import NUMERICAL_POLICY, NUMERICAL_POLICY_SHA256, slice_solid
from terrain_pipeline.hybrid_river_faces import guard, plane_frame, seal
from terrain_pipeline.hybrid_river_graph import identity
from terrain_pipeline.hybrid_surface_composition_v2 import _domain
from terrain_pipeline.hybrid_surface_composition import POLICY as GEOMETRIC_POLICY

SCHEMA = "td-hybrid-surface-composition-v3"
POLICY = {**GEOMETRIC_POLICY, "version": "saved-stage-rational-surface-composition-v3",
    "numerical_slice": NUMERICAL_POLICY_SHA256,
    "main_boolean": "immutable_composition02_checkpoint_mesh_pins_material_and_extra_removed_not_recomputed",
    "portal_boolean": "bounded_collars_only_reuse_saved_collars_when_available",
    "failure": "saved_stage_lineage_material_and_partial_port_reports_preserved"}
POLICY_SHA256 = identity(POLICY)


def _slice(solid, record, frame, name):
    return slice_solid((solid, np.asarray(record["vertices_local_xyz_m"]), np.asarray(record["triangles"])),
        frame, {"artifact": name, "identity_sha256": record["identity_sha256"],
            "triangle_identity_authority": "immutable_saved_record_arrays"})


def _area_upper(area, bound):
    return math.nextafter(math.fsum((float(area), bound)), math.inf)


def _portal(kind, station, port, connection, solids, meshes, origin, artifacts, reusable):
    import manifold3d as manifold
    frame = plane_frame(station["origin_xyz_m"], port["flow_unit_xz"], origin)
    ring = np.asarray(station["derived_ring_xyz_m"])
    horizontal = (ring[:, [0, 2]] - np.asarray(station["origin_xyz_m"])[[0, 2]]) @ np.asarray(frame["transverse_unit_xz"])
    aperture = Polygon(np.column_stack((horizontal, ring[:, 1] - origin[1])))
    connection.update(plane=frame, gallery_aperture_uv_m=list(map(list, aperture.exterior.coords))[:-1],
        exact_solid_slices={}, hydraulic_boundary_certified=False, two_sided_complete_port_verified=False)
    if not aperture.is_valid:
        raise ValueError("invalid_original_canonical_aperture")
    shapes = {}
    for name in ("coupled_cutter", "rock_after", "removed"):
        record, shapes[name] = _slice(solids[name], meshes[name], frame, name)
        connection["exact_solid_slices"][name] = record
    blocked, missing = aperture.intersection(shapes["rock_after"]), aperture.difference(shapes["coupled_cutter"])
    blocked_bound = connection["exact_solid_slices"]["rock_after"]["projection_area_error_bound_m2"]
    missing_bound = connection["exact_solid_slices"]["coupled_cutter"]["projection_area_error_bound_m2"]
    connection.update(exact_blocked_area_m2=float(blocked.area), exact_missing_cutter_area_m2=float(missing.area),
        blocked_domain=_domain(blocked), missing_domain=_domain(missing),
        blocked_area_upper_bound_m2=_area_upper(blocked.area, blocked_bound),
        missing_area_upper_bound_m2=_area_upper(missing.area, missing_bound))
    if connection["blocked_area_upper_bound_m2"] > 1e-8 or connection["missing_area_upper_bound_m2"] > 1e-8:
        raise ValueError("actual_full_canonical_port_blocked_or_missing:" + kind)
    depth = min(.001, min(item["exterior_support_distance_m"] for witness in connection["canonical_whole_piece_witnesses"]
        for item in witness["supports"]) / 16.)
    connection["epsilon_rule"] = "min_1mm_and_minimum_actual_exterior_support_distance_div16"
    basis = np.array([frame["transverse_unit_xyz"], frame["vertical_unit_xyz"], frame["normal_local_xyz"]]).T
    bounds = aperture.bounds
    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    center = np.array(frame["origin_local_xyz_m"]) + np.array(frame["transverse_unit_xyz"]) * ((bounds[0] + bounds[2]) / 2.)
    center[1] = (bounds[1] + bounds[3]) / 2.
    collars = []
    proof = {"sides": {}, "constructed_by_intersecting_actual_cutters_not_new_excavation": True}
    connection["positive_volume_connection"] = proof
    surface_sign = -1. if kind == "sink" else 1.
    for side_name, source, sign in (("surface", "surface_cutter", surface_sign), ("gallery", "original_cutter", -surface_sign)):
        name = kind + "_" + side_name + "_collar"
        slab_center = center + sign * depth / 2. * np.array(frame["normal_local_xyz"])
        transform = np.column_stack((basis, slab_center)).tolist()
        if name in reusable:
            collar = manifold_from_record(reusable[name])
            inherited = True
        else:
            slab = manifold.Manifold.cube([width, height, depth], center=True).transform(transform)
            collar = solids[source] ^ slab
            inherited = False
        side = {"artifact": name, "positive_volume_m3": float(collar.volume()), "source_solid": source,
            "normal_side_sign": sign, "slab_width_height_depth_m": [width, height, depth], "slab_transform_3x4": transform,
            "component_count": len(collar.decompose()), "inherited_saved_collar": inherited}
        proof["sides"][side_name] = side
        if not collar.is_empty() and not inherited:
            artifacts[name] = save_manifold(collar, origin, name)
        if collar.is_empty() or collar.volume() <= 0 or side["component_count"] != 1:
            raise ValueError("missing_positive_volume_collar:" + kind + ":" + side_name)
        record, shape = _slice(collar, reusable[name] if inherited else artifacts[name], frame, name)
        gap = aperture.difference(shape)
        bound = record["projection_area_error_bound_m2"]
        side.update(interface_solid_slice=record, whole_aperture_uncovered_area_m2=float(gap.area),
            uncovered_area_upper_bound_m2=_area_upper(gap.area, bound), uncovered_domain=_domain(gap))
        if side["uncovered_area_upper_bound_m2"] > 1e-8:
            raise ValueError("whole_port_collar_coverage_failed:" + kind + ":" + side_name)
        collars.append(collar)
    name = kind + "_connected_collar"
    connected = manifold_from_record(reusable[name]) if name in reusable else collars[0] + collars[1]
    if name not in reusable:
        artifacts[name] = save_manifold(connected, origin, name)
    overlap = float((connected ^ solids["rock_after"]).volume())
    proof.update(connected_collar_artifact=name, component_count=len(connected.decompose()), actual_rock_overlap_volume_m3=overlap)
    if proof["component_count"] != 1 or overlap > 1e-7:
        raise ValueError("whole_port_volume_disconnected_or_blocked:" + kind)
    connection.update(one_sided_diagnostic_traces=[], offset_traces_not_recomputed=True,
        two_sided_complete_port_verified=True)


def resume_composition(stage, vdm, attachments, ports, meshes, prisms, lineage, reusable=None):
    origin = np.asarray(meshes["rock_after"]["local_origin_xyz_m"])
    if any(record["local_origin_xyz_m"] != origin.tolist() for record in meshes.values()):
        raise ValueError("saved_stage_local_frame_changed")
    solids = {name: manifold_from_record(meshes[name]) for name in
        ("surface_cutter", "coupled_cutter", "rock_after", "removed", "original_cutter")}
    result = dict(stage)
    result.pop("identity_sha256", None)
    result.update(schema=SCHEMA, policy=POLICY, policy_identity_sha256=POLICY_SHA256,
        numerical_slice_policy=NUMERICAL_POLICY, numerical_slice_policy_identity_sha256=NUMERICAL_POLICY_SHA256,
        stage_lineage=lineage, main_boolean_recomputed=False, material_inherited_unchanged=True,
        portal_connections={}, rejection_reasons=[], boolean_stage_preserved=True)
    if stage["coupled_cutter_component_count"] != 1:
        result["rejection_reasons"].append("source_coupled_cutter_not_one_component")
    artifacts = {}
    for kind, ordinal in (("sink", 0), ("spring", len(vdm["stations"]) - 1)):
        connection = {"canonical_whole_piece_witnesses": prisms["half_arms"][kind]["canonical_whole_piece_witnesses"],
            "immutable_gallery_station_index": ordinal,
            "original_complete_port_proof": attachments["attachments"][kind]["actual_complete_port_proof"],
            "full_shared_interface_supported": True, "offset_traces_are_diagnostic_only": True}
        result["portal_connections"][kind] = connection
        try:
            _portal(kind, vdm["stations"][ordinal], ports[kind], connection, solids, meshes, origin, artifacts, reusable or {})
            connection.update(status="verified_geometry_unverified_audit", rejection_reasons=[])
        except (ValueError, AttributeError, TypeError, OverflowError) as error:
            connection.update(status="refused", rejection_reasons=[type(error).__name__ + ":" + str(error)],
                two_sided_complete_port_verified=False)
            result["rejection_reasons"].append(kind + ":" + type(error).__name__ + ":" + str(error))
    result.update(status="refused" if result["rejection_reasons"] else "candidate_unverified", actual_peak_rss_bytes=guard())
    return seal(result), artifacts
