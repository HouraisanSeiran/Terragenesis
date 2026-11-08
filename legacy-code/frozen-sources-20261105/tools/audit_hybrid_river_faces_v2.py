"""Cold audit of actual polygon link faces and independently sourced wall roles."""

import argparse
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.audit_hybrid_river_faces import (
    check_plane, source_canonical_floor, whole_line_supported)
from tools.hybrid_exact_solid_saved_audit import ExactSolid as Solid
from tools.audit_hybrid_surface_composition_v3 import (
    NUMERICAL_POLICY, NUMERICAL_POLICY_SHA256, audit_exact_slice, check_stage_lineage, independent_triangle_trace)
from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, check_identity, check_memory, compare, digest, file_sha256, read, read_audit, require)

SCHEMA = "td-hybrid-river-faces-independent-audit-v2"


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


def audit(pin):
    record = read(pin)
    require(record["schema"] == "td-hybrid-river-faces-v2", "wrong face schema")
    inputs = record["inputs"]
    geometry, composition = read(inputs["geometry"]), read(inputs["composition"])
    coupled_audit = read_audit(inputs["composition_audit"])
    require(composition["schema"] == "td-hybrid-surface-composition-v3"
            and composition["status"] == "candidate_unverified" and not composition["rejection_reasons"]
            and coupled_audit["schema"] == "td-hybrid-surface-composition-independent-audit-v4"
            and coupled_audit["status"] == "passed" and not coupled_audit["errors"]
            and coupled_audit["composition_pin"]["sha256"] == inputs["composition"]["sha256"]
            and Path(coupled_audit["composition_pin"]["path"]).resolve() == Path(inputs["composition"]["path"]).resolve()
            and coupled_audit["composition_identity_sha256"] == composition["identity_sha256"]
            and coupled_audit["inputs"] == composition["inputs"]
            and coupled_audit["mesh_pins"] == composition["mesh_pins"]
            and coupled_audit["surface_prisms_pin"] == composition["surface_prisms_pin"]
            and coupled_audit["policy_identity_sha256"] == composition["policy_identity_sha256"]
            and coupled_audit["materials_verified"] is True
            and coupled_audit["native_half_arm_sources_verified"] is True
            and coupled_audit["material"]["independent_boolean_verified"] is True
            and coupled_audit["two_sided_complete_port_verified"] is True
            and coupled_audit["stage_lineage_verified"] is True
            and coupled_audit["stage_lineage"] == composition["stage_lineage"]
            and record["stage_lineage"] == inputs["stage_lineage"] == composition["stage_lineage"]
            and composition["main_boolean_recomputed"] is False
            and composition["material_inherited_unchanged"] is True
            and record["composition_identity_sha256"] == composition["identity_sha256"], "coupled geometry not independently accepted")
    check_stage_lineage(composition)
    require(composition["numerical_slice_policy"] == NUMERICAL_POLICY
            and composition["numerical_slice_policy_identity_sha256"] == NUMERICAL_POLICY_SHA256
            and record["numerical_slice_policy"] == NUMERICAL_POLICY
            and record["numerical_slice_policy_identity_sha256"] == NUMERICAL_POLICY_SHA256,
            "unverified quantized slice policy")
    require(inputs["geometry"] == composition["inputs"]["geometry"]
            and inputs["geometry_audit"] == composition["inputs"]["geometry_audit"]
            and inputs["graph"] == composition["inputs"]["graph"]
            and inputs["vdm"] == composition["inputs"]["vdm"]
            and inputs["surface_attachments"] == composition["inputs"]["surface_attachments"]
            and inputs["surface_prisms"] == composition["surface_prisms_pin"]
            and inputs["mesh_pins"] == composition["mesh_pins"]
            and inputs["original_inputs"] == composition["inputs"]
            and coupled_audit["geometry_sha256"] == inputs["geometry"]["sha256"]
            and inputs["geometry"]["sha256"] == "3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593",
            "mixed geometry/source/mesh parents")
    composition_index = read(inputs["composition_index"])
    require(composition_index["schema"] == "td-hybrid-surface-composition-preparation-v3"
            and composition_index["composition"]["sha256"] == inputs["composition"]["sha256"]
            and Path(composition_index["composition"]["path"]).resolve() == Path(inputs["composition"]["path"]).resolve()
            and composition_index["inputs"] == composition["inputs"]
            and composition_index["stage_lineage"] == composition["stage_lineage"]
            and composition_index["code_sha256"] == composition["code_sha256"], "composition index binding differs")
    for parent in (record, composition, coupled_audit):
        for group in ("code_sha256", "readonly_dependency_code_sha256", "audit_code_sha256"):
            for name, sha in parent.get(group, {}).items():
                require(file_sha256(ROOT / name) == sha, "frozen source changed: " + name)
    require(geometry["identity_sha256"] == record["geometry_identity_sha256"]
            and geometry["graph_identity_sha256"] == record["graph_identity_sha256"]
            and record["face_count"] == len(record["faces"]) == len(geometry["hydraulic_links"]) == 18,
            "geometry/face census differs")
    for flag in ("independent_audit_passed", "hydraulic_solved", "water_discharge_computed",
                 "storage_geometry_changed", "pressure_slot_enlarges_face", "native_exact"):
        require(record[flag] is False, "premature hydraulic/geometry promotion")
    vdm = read(composition["inputs"]["vdm"])
    prisms = read(composition["surface_prisms_pin"])
    attachments = read(composition["inputs"]["surface_attachments"])
    original_pin = composition["mesh_pins"]["original_cutter"]
    original = read(original_pin)
    pins = {role: composition["mesh_pins"]["coupled_cutter" if role == "cutter" else role]
            for role in ("cutter", "rock_before", "rock_after", "removed")}
    meshes = {role: read(mesh_pin) for role, mesh_pin in pins.items()}
    common = np.asarray(meshes["cutter"]["local_origin_xyz_m"])
    solids = {}
    for role, mesh in meshes.items():
        require(np.array_equal(mesh["local_origin_xyz_m"], common), "source solids not in common frame")
        solids[role] = Solid(mesh["vertices_local_xyz_m"], mesh["triangles"], role)
    reports, errors = [], []
    cells = {cell["cell_id"]: cell for cell in geometry["hydraulic_cells"]}
    for ordinal, face in enumerate(record["faces"]):
        try:
            check_identity(face)
            require(face["schema"] == "td-hybrid-river-face-v2" and face["face_id"] == "face:" + str(ordinal)
                    and face["status"] == "candidate" and not face["rejection_reasons"], "unknown/refused face")
            link = geometry["hydraulic_links"][ordinal]
            for key in ("link_id", "from_cell_id", "to_cell_id", "length_m"):
                require(face[key] == link[key], "original hydraulic link substituted")
            require(face["additional_step_loss"] is None and face["roughness_manning"] == .035
                    and face["roughness_source_cell_ids"] == [link["from_cell_id"], link["to_cell_id"]]
                    and all(cells[key]["roughness_manning"] == .035 for key in face["roughness_source_cell_ids"]),
                    "undeclared resistance parameters")
            if ordinal in (0, 17):
                kind = "sink" if ordinal == 0 else "spring"
                port = read(attachments["attachments"][kind]["canonical_port_pin"])
                station = vdm["stations"][0 if ordinal == 0 else -1]
                portal_report = coupled_audit["portal_reports"][kind]
                require(portal_report["verified"] is True and portal_report["two_sided_complete_port_verified"] is True
                        and portal_report["port_identity_sha256"] == port["identity_sha256"]
                        and portal_report["canonical_port_pin"] == attachments["attachments"][kind]["canonical_port_pin"],
                        "per-portal identity/verification differs")
                check_plane(face["plane"], station["origin_xyz_m"], port["flow_unit_xz"], common)
                canonical = source_canonical_floor(port, face["plane"])
                binding = face["shared_port_binding"]
                attachment = attachments["attachments"][kind]
                require(binding == {"kind": kind, "canonical_port_pin": attachment["canonical_port_pin"],
                        "surface_node_pin": attachment["surface_node_pin"], "port_identity_sha256": port["identity_sha256"],
                        "actual_complete_port_proof": attachment["actual_complete_port_proof"],
                        "half_arm_triangle_indices": attachment["half_arm_triangle_indices"],
                        "canonical_profile_uv_m": canonical, "hydraulic_boundary_certified": False},
                        "whole native canonical profile differs")
                evidence = face["aperture"]["canonical_two_sided_evidence"]
                require(evidence["composition_audit_pin"] == inputs["composition_audit"]
                        and evidence["two_sided_complete_port_verified"] is True
                        and evidence["composition_portal_connection"] == composition["portal_connections"][kind]
                        and evidence["no_endcap_deleted"] is True, "missing actual two-sided port proof")
            else:
                first, second = vdm["stations"][ordinal - 1:ordinal + 1]
                require((link["from_cell_id"], link["to_cell_id"]) == (first["station_id"], second["station_id"])
                        and face["shared_port_binding"] is None
                        and face["aperture"]["canonical_two_sided_evidence"] is None, "wrong route binding")
                start, end = np.asarray(first["origin_xyz_m"]), np.asarray(second["origin_xyz_m"])
                check_plane(face["plane"], (start + end) / 2, (end - start)[[0, 2]], common)
                canonical = None
            require(set(face["solid_slices"]) == set(solids), "actual solid slice census differs")
            shapes = {role: audit_exact_slice(face["solid_slices"][role], solid, face["plane"], pins[role])[0]
                      for role, solid in solids.items()}
            role_lines = [audit_role_slice(source, face["plane"], original, original_pin, vdm,
                                          prisms, composition["surface_prisms_pin"])
                          for source in face["source_role_slices"]]
            if canonical is not None:
                require(whole_line_supported(LineString(canonical), shapes["cutter"].boundary), "canonical floor not actual face boundary")
            report = audit_boundary(face["aperture"], shapes, face["solid_slices"], role_lines, face["plane"])
            reports.append({"face_id": face["face_id"], "link_id": link["link_id"], "aperture": report})
            check_memory()
        except (ValueError, KeyError, TypeError, IndexError) as error:
            errors.append({"face_id": face.get("face_id"), "error": str(error),
                           "saved_rejection_reasons": face.get("rejection_reasons")})
    refused = [item["face_id"] for item in record["faces"] if item["status"] != "candidate"]
    require(record["rejection_reasons"] == refused
            and record["status"] == ("refused" if refused else "candidate_unverified"), "refusal census differs")
    return {"schema": SCHEMA, "status": "refused" if errors else "passed", "errors": errors,
            "faces_pin": pin, "inputs": inputs, "reports": reports, "verified_face_count": len(reports),
            "geometry_identity_sha256": geometry["identity_sha256"], "composition_identity_sha256": composition["identity_sha256"],
            "actual_slice_sources_verified": not errors, "wet_wall_boundary_sources_verified": not errors,
            "two_sided_canonical_ports_verified": not errors, "hydraulic_solved": False,
            "hydraulic_constitutive_law_accepted": False, "whole_link_step_support_certified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--faces", type=Path, required=True)
    parser.add_argument("--faces-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / "verification"), "new verification audit required")
    pin = {"path": str(args.faces.resolve()), "sha256": args.faces_sha256}
    started = time.monotonic()
    try:
        report = audit(pin)
    except (ValueError, KeyError, TypeError, IndexError, OSError, RuntimeError) as error:
        report = {"schema": SCHEMA, "status": "refused", "errors": [str(error)], "faces_pin": pin,
                  "hydraulic_solved": False, "hydraulic_constitutive_law_accepted": False}
    report["resource"] = {"wall_seconds": time.monotonic() - started, "peak_rss_bytes": check_memory(), "solver_calls": 0}
    report["code_sha256"] = {name: file_sha256(ROOT / name) for name in (
        "tools/audit_hybrid_river_faces_v2.py", "tests/test_hybrid_river_faces_v2_saved_audit.py",
        "tools/audit_hybrid_surface_composition_v3.py", "tools/hybrid_exact_solid_saved_audit.py",
        "tools/audit_hybrid_river_faces.py", "tools/hybrid_cave_saved_audit.py", "tools/td_shared_channel_fine_saved_audit.py")}
    report["identity_sha256"] = digest(report)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "audit exceeds file budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(json.dumps({"status": report["status"], "errors": report["errors"],
                      "verified_face_count": report.get("verified_face_count", 0), "sha256": file_sha256(output)}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
