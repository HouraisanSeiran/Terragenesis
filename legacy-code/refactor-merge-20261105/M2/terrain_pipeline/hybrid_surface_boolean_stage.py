"""Original main Boolean stage, separated from every historical portal algorithm."""
import numpy as np
from terrain_pipeline.hybrid_cave_geometry import manifold_from_record, save_manifold
from terrain_pipeline.hybrid_geometry_common import MAX_BYTES, MAX_TRIANGLES, seal
from terrain_pipeline.hybrid_mesh_plane_v2 import NUMERICAL_POLICY, NUMERICAL_POLICY_SHA256
from terrain_pipeline.hybrid_surface_prisms import POLICY as GEOMETRIC_POLICY, half_arm_prisms, canonical_boundary_witness
from terrain_pipeline.hybrid_surface_material import saved_sampling_mismatch_witnesses, volume_ledger
from terrain_pipeline.hybrid_river_graph import identity

SCHEMA = "td-hybrid-surface-boolean-stage-current-v1"
POLICY = {**GEOMETRIC_POLICY, "version": "original-main-boolean-stage-current-v1",
          "numerical_slice": NUMERICAL_POLICY_SHA256,
          "failure": "Boolean-stage-preserved-before-any-rational-portal-check"}
POLICY_SHA256 = identity(POLICY)


def build_boolean_stage(geometry, vdm, attachments, ports, meshes, nodes, sampling):
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
    return seal(result), artifacts
