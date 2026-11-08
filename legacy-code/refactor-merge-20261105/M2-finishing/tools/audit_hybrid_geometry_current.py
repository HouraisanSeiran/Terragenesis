"""Independent cold checks for the current fixed-support geometry integration."""

import numpy as np

from tools.hybrid_geometry_audit_base import EmptySolid, audit_material_solids, audit_sampling_mismatches
from tools.hybrid_geometry_saved_checks import Solid, audit_prisms, audit_port, NUMERICAL_POLICY_SHA256
from tools.td_shared_channel_fine_saved_audit import check_identity, compare, read, require
from tools.hybrid_surface_resume_saved_audit import load_native_bound
from tools.hybrid_interval_winding_saved_audit import IntervalSolid, runtime_identity
from tools.hybrid_geometry_io import GEOMETRY_SHA, read as read_current, load_inputs, verify_current_code, current_audit_code


SCHEMA = "td-hybrid-current-composition-audit-v1"


def load_native_for_geometry(geometry):
    sections_pin = geometry["inputs"]["original_06_sections"]
    sections = read_current(sections_pin)
    protection_pin = geometry["inputs"]["original_wet_protection_manifest"]
    protection = read_current(protection_pin)["wet_protection"]
    native, binding = load_native_bound(geometry["inputs"]["original_hierarchy"],
        sections["hierarchy_identity_sha256"], sections["selected_leaf_ids"], protection)
    return native, {**binding, "sections_pin": dict(sections_pin),
                    "sections_identity_field": "hierarchy_identity_sha256",
                    "sections_record_identity_sha256": sections["identity_sha256"],
                    "wet_protection_pin": dict(protection_pin)}


def audit_composition(composition_pin):
    record = read_current(composition_pin)
    verify_current_code(record)
    require(record["schema"] == "td-hybrid-current-composition-v1"
            and record["status"] == "candidate_unverified" and not record["rejection_reasons"],
            "current composition is incomplete or refused")
    for name in ("independent_audit_passed", "hydraulic_ready", "hydraulic_solved", "full_network_verified"):
        require(record[name] is False, "premature current composition claim: " + name)
    inputs = record["inputs"]
    require(inputs["geometry"]["sha256"] == GEOMETRY_SHA, "current fixed source geometry differs")
    geometry, vdm, attachments, ports, original_meshes = load_inputs(inputs["geometry"], inputs["geometry_audit"])
    require(inputs["graph"] == geometry["inputs"]["graph"] and inputs["mesh_pins"] == geometry["mesh_pins"]
            and inputs["vdm"] == geometry["vdm_pin"] and inputs["surface_attachments"] == geometry["surface_attachments_pin"]
            and inputs["original_source_sampling"] == geometry["source_sampling_pin"], "current original input registry differs")
    require(len(vdm["stations"]) == 17 and len(geometry["hydraulic_links"]) == 18,
            "current integration scope is fixed 17 stations / 18 links")
    require(record["geometry_identity_sha256"] == geometry["identity_sha256"]
            and record["graph_identity_sha256"] == geometry["graph_identity_sha256"],
            "current composition original graph or geometry differs")
    require(record["numerical_slice_policy_identity_sha256"] == NUMERICAL_POLICY_SHA256,
            "current slice numerical identity differs")
    lineage = record["stage_lineage"]
    stage_index = read_current(lineage["source_index_pin"])
    checkpoint = read_current(lineage["checkpoint_pin"])
    require(lineage["mode"] == "fresh-original-boolean-then-rational-port"
            and stage_index["schema"] == "td-hybrid-current-boolean-index-v1"
            and checkpoint["schema"] == "td-hybrid-current-boolean-checkpoint-v1"
            and checkpoint["portal_checks_started"] is False
            and stage_index["inputs"] == checkpoint["inputs"] == inputs
            and stage_index["artifacts"] == checkpoint["artifacts"]
            and record["main_boolean_recomputed"] is True,
            "current fresh stage lineage is missing or mixed with historical fixed-v3")
    verify_current_code(stage_index)
    verify_current_code(checkpoint)
    require(stage_index["code_sha256"] == checkpoint["code_sha256"] == record["code_sha256"], "current stage code map changed")
    stage = checkpoint["composition_stage"]
    check_identity(stage)
    require(stage["schema"] == "td-hybrid-surface-boolean-stage-current-v1"
            and stage["material"] == record["material"]
            and record["boolean_stage_source_identity_sha256"] == stage["identity_sha256"],
            "current stage material or identity changed during portal integration")
    for name, pin in checkpoint["artifacts"].items():
        actual = record["surface_prisms_pin"] if name == "surface_prisms" else record["mesh_pins"][name]
        require(actual == pin, "current main Boolean stage artifact replaced: " + name)
    meshes = {}
    interval_queries = []
    origin = None
    for role, pin in record["mesh_pins"].items():
        mesh = read_current(pin)
        location = np.asarray(mesh["local_origin_xyz_m"], float)
        if origin is None:
            origin = location
        require(np.array_equal(location, origin), "current solids do not share one local origin")
        if mesh["schema"] == "td-hybrid-empty-solid-v1":
            require(role == "extra_removed" and mesh["signed_volume_m3"] == 0.0
                    and mesh["triangles"] == [] and mesh["vertices_local_xyz_m"] == [],
                    "invalid current empty solid")
            meshes[role] = EmptySolid()
        else:
            validated = Solid(mesh["vertices_local_xyz_m"], mesh["triangles"], role)
            meshes[role] = IntervalSolid(validated, pin, interval_queries)
            compare(mesh["signed_volume_m3"], meshes[role].signed_volume, "current saved volume " + role,
                    atol=1e-7, rtol=1e-9)
    native, native_binding = load_native_for_geometry(geometry)
    prisms = read_current(record["surface_prisms_pin"])
    _, source_reports = audit_prisms(prisms, attachments, vdm, native, origin, meshes)
    material = audit_material_solids(*(meshes[name] for name in (
        "rock_before", "original_rock_after", "original_removed", "surface_cutter", "coupled_cutter",
        "rock_after", "extra_removed", "removed", "original_cutter")))
    for name in ("original_removed_m3", "extra_removed_m3", "total_removed_m3"):
        compare(record["material"][name], material[name], "current material " + name, atol=1e-7, rtol=1e-9)
    sampling = read_current(inputs["original_source_sampling"])
    mismatch = audit_sampling_mismatches(record["original_source_sampling_cut_lookup_mismatches"], sampling, attachments)
    reports, evidence = {}, {}
    for kind in ("sink", "spring"):
        evidence[kind] = {}
        reports[kind] = audit_port(kind, record, prisms, geometry, attachments, vdm, meshes, origin, evidence[kind])
    return {"schema": SCHEMA, "status": "passed", "errors": [], "composition_pin": composition_pin,
            "composition_identity_sha256": record["identity_sha256"], "inputs": inputs,
            "mesh_pins": record["mesh_pins"], "surface_prisms_pin": record["surface_prisms_pin"],
            "materials_verified": True, "native_half_arm_sources_verified": True,
            "two_sided_complete_port_verified": True, "stage_lineage_verified": True,
            "stage_lineage": lineage, "material": material, "portal_reports": reports,
            "prism_source_reports": source_reports, "sampling_mismatch_report": mismatch,
            "native_identity_binding": native_binding,
            "interval_winding_queries": interval_queries, "interval_runtime": runtime_identity(),
            "portal_evidence": evidence, "hydraulic_ready": False, "publishable": False,
            "audit_code_sha256": current_audit_code()}


def audit_faces(pin):
    from shapely.geometry import LineString
    from tools.hybrid_geometry_audit_base import check_plane, source_canonical_floor, whole_line_supported
    from tools.hybrid_geometry_saved_checks import audit_exact_slice, NUMERICAL_POLICY
    from tools.hybrid_geometry_face_checks import audit_role_slice, audit_boundary
    record = read_current(pin)
    verify_current_code(record)
    require(record["schema"] == "td-hybrid-current-faces-v1", "wrong current face schema")
    inputs = record["inputs"]
    geometry = read_current(inputs["geometry"])
    composition = read_current(inputs["composition"])
    coupled_audit = read_current(inputs["composition_audit"])
    verify_current_code(composition)
    require(coupled_audit.get("audit_code_sha256") == current_audit_code(), "current composition auditor source changed")
    require(composition["schema"] == "td-hybrid-current-composition-v1"
            and composition["status"] == "candidate_unverified" and not composition["rejection_reasons"]
            and coupled_audit["schema"] == SCHEMA and coupled_audit["status"] == "passed"
            and coupled_audit["errors"] == [] and coupled_audit["composition_pin"] == inputs["composition"]
            and coupled_audit["composition_identity_sha256"] == composition["identity_sha256"]
            and coupled_audit["inputs"] == composition["inputs"]
            and coupled_audit["mesh_pins"] == composition["mesh_pins"]
            and coupled_audit["surface_prisms_pin"] == composition["surface_prisms_pin"]
            and coupled_audit["materials_verified"] is True
            and coupled_audit["native_half_arm_sources_verified"] is True
            and coupled_audit["two_sided_complete_port_verified"] is True
            and coupled_audit["stage_lineage_verified"] is True
            and coupled_audit["stage_lineage"] == composition["stage_lineage"]
            and record["stage_lineage"] == composition["stage_lineage"]
            and record["composition_identity_sha256"] == composition["identity_sha256"],
            "current faces do not bind the independently audited composition")
    require(record["numerical_slice_policy"] == composition["numerical_slice_policy"] == NUMERICAL_POLICY
            and record["numerical_slice_policy_identity_sha256"] == NUMERICAL_POLICY_SHA256
            and composition["numerical_slice_policy_identity_sha256"] == NUMERICAL_POLICY_SHA256,
            "current faces have an unverified slice policy")
    require(inputs["geometry"] == composition["inputs"]["geometry"]
            and inputs["geometry"]["sha256"] == GEOMETRY_SHA
            and geometry["identity_sha256"] == record["geometry_identity_sha256"]
            and geometry["graph_identity_sha256"] == record["graph_identity_sha256"]
            and record["face_count"] == len(record["faces"]) == len(geometry["hydraulic_links"]) == 18,
            "current geometry/face census differs")
    for flag in ("independent_audit_passed", "hydraulic_solved", "water_discharge_computed",
                 "storage_geometry_changed", "pressure_slot_enlarges_face", "native_exact"):
        require(record[flag] is False, "premature current face claim: " + flag)
    vdm = read_current(composition["inputs"]["vdm"])
    prisms = read_current(composition["surface_prisms_pin"])
    attachments = read_current(composition["inputs"]["surface_attachments"])
    original_pin = composition["mesh_pins"]["original_cutter"]
    original = read_current(original_pin)
    pins = {role: composition["mesh_pins"]["coupled_cutter" if role == "cutter" else role]
            for role in ("cutter", "rock_before", "rock_after", "removed")}
    meshes = {role: read_current(mesh_pin) for role, mesh_pin in pins.items()}
    common = np.asarray(meshes["cutter"]["local_origin_xyz_m"])
    solids = {}
    interval_queries = []
    for role, mesh in meshes.items():
        require(np.array_equal(mesh["local_origin_xyz_m"], common), "current face source frames differ")
        validated = Solid(mesh["vertices_local_xyz_m"], mesh["triangles"], role)
        solids[role] = IntervalSolid(validated, pins[role], interval_queries)
    reports, errors = [], []
    cells = {cell["cell_id"]: cell for cell in geometry["hydraulic_cells"]}
    for ordinal, face in enumerate(record["faces"]):
        try:
            check_identity(face)
            require(face["schema"] == "td-hybrid-river-face-v2" and face["face_id"] == "face:" + str(ordinal)
                    and face["status"] == "candidate" and not face["rejection_reasons"], "unknown/refused current face")
            link = geometry["hydraulic_links"][ordinal]
            for key in ("link_id", "from_cell_id", "to_cell_id", "length_m"):
                require(face[key] == link[key], "original hydraulic link substituted")
            require(face["additional_step_loss"] is None and face["roughness_manning"] == .035
                    and face["roughness_source_cell_ids"] == [link["from_cell_id"], link["to_cell_id"]]
                    and all(cells[key]["roughness_manning"] == .035 for key in face["roughness_source_cell_ids"]),
                    "undeclared current resistance parameters")
            if ordinal in (0, 17):
                kind = "sink" if ordinal == 0 else "spring"
                port = read_current(attachments["attachments"][kind]["canonical_port_pin"])
                station = vdm["stations"][0 if ordinal == 0 else -1]
                portal_report = coupled_audit["portal_reports"][kind]
                require(portal_report["verified"] is True and portal_report["two_sided_complete_port_verified"] is True
                        and portal_report["port_identity_sha256"] == port["identity_sha256"]
                        and portal_report["canonical_port_pin"] == attachments["attachments"][kind]["canonical_port_pin"],
                        "current per-portal audit identity differs")
                check_plane(face["plane"], station["origin_xyz_m"], port["flow_unit_xz"], common)
                canonical = source_canonical_floor(port, face["plane"])
                binding = face["shared_port_binding"]
                attachment = attachments["attachments"][kind]
                require(binding == {"kind": kind, "canonical_port_pin": attachment["canonical_port_pin"],
                        "surface_node_pin": attachment["surface_node_pin"], "port_identity_sha256": port["identity_sha256"],
                        "actual_complete_port_proof": attachment["actual_complete_port_proof"],
                        "half_arm_triangle_indices": attachment["half_arm_triangle_indices"],
                        "canonical_profile_uv_m": canonical, "hydraulic_boundary_certified": False},
                        "current whole canonical profile differs")
                evidence = face["aperture"]["canonical_two_sided_evidence"]
                require(evidence["composition_audit_pin"] == inputs["composition_audit"]
                        and evidence["two_sided_complete_port_verified"] is True
                        and evidence["composition_portal_connection"] == composition["portal_connections"][kind]
                        and evidence["no_endcap_deleted"] is True, "current two-sided face evidence missing")
            else:
                first, second = vdm["stations"][ordinal - 1:ordinal + 1]
                require((link["from_cell_id"], link["to_cell_id"]) == (first["station_id"], second["station_id"])
                        and face["shared_port_binding"] is None
                        and face["aperture"]["canonical_two_sided_evidence"] is None, "current route binding differs")
                start, end = np.asarray(first["origin_xyz_m"]), np.asarray(second["origin_xyz_m"])
                check_plane(face["plane"], (start + end) / 2, (end - start)[[0, 2]], common)
                canonical = None
            require(set(face["solid_slices"]) == set(solids), "current slice census differs")
            shapes = {role: audit_exact_slice(face["solid_slices"][role], solid, face["plane"], pins[role])[0]
                      for role, solid in solids.items()}
            role_lines = [audit_role_slice(source, face["plane"], original, original_pin, vdm,
                                          prisms, composition["surface_prisms_pin"])
                          for source in face["source_role_slices"]]
            if canonical is not None:
                require(whole_line_supported(LineString(canonical), shapes["cutter"].boundary),
                        "current canonical floor not an actual face boundary")
            boundary = audit_boundary(face["aperture"], shapes, face["solid_slices"], role_lines, face["plane"])
            reports.append({"face_id": face["face_id"], "link_id": link["link_id"], "aperture": boundary})
        except (ValueError, KeyError, TypeError, IndexError) as error:
            errors.append({"face_id": face.get("face_id"), "error": str(error)})
    require(not errors and len(reports) == 18, "current face audit failed: " + str(errors))
    return {"schema": "td-hybrid-current-face-audit-v1", "status": "passed", "errors": [],
            "faces_pin": pin, "inputs": inputs, "reports": reports, "verified_face_count": len(reports),
            "composition_identity_sha256": composition["identity_sha256"],
            "actual_slice_sources_verified": True, "two_sided_canonical_ports_verified": True,
            "interval_winding_queries": interval_queries, "interval_runtime": runtime_identity(),
            "hydraulic_solved": False, "publishable": False}
