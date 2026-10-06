"""Prepare actual polygon faces from a pinned, independently audited coupled composition."""

import argparse
from fractions import Fraction
from importlib.metadata import version
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hybrid_river_faces_v2 import MAX_BYTES, MAX_RSS, POLICY_SHA256, SCHEMA, build_faces, guard, seal
from tools.prepare_hybrid_river_faces import BASE, GEOMETRY_SHA, file_sha, load_inputs, read, save

CODE_FILES = ("terrain_pipeline/hybrid_river_faces_v2.py", "tools/prepare_hybrid_river_faces_v2.py",
              "tests/test_hybrid_river_faces_v2.py")
FROZEN_CODE = {"terrain_pipeline/hybrid_river_faces.py": "73ae18fc30afabb70ed4b3d1c043606141e560c7d0d818f38053ac018b5acc8a",
               "tools/prepare_hybrid_river_faces.py": "e4c7051473aaaa5dbe79baa5314fc4fe52e68af7e9197a8871eb68272b82fb2e",
               "tests/test_hybrid_river_faces.py": "a329e3850f7e211dbf07c756263650d0f3d1b7b3848f1ee7a8c833fe52b290e6",
               "terrain_pipeline/hybrid_surface_composition.py": "0a9b424ca1994d150c8bf6c3cb90c2ce8c263cd5ca78cace24134242b02c5dd3",
               "tools/prepare_hybrid_surface_composition.py": "93e50dec6ac93cbda8396fb2b344fd40204a1c72942c944a17e0ecd698bafff8",
               "tests/test_hybrid_surface_composition.py": "5df84c0c6c5cfb17b83c1f25cfc3819ee7c221c9b850d5d62dfbcaf443bc0ae7"}
SOURCE_STAGE_SHA256 = {
    "source_index_pin": "54f1fe63f8f8ff2b79e5bb7332c97fa76ec77b780abf772ad9245081b45af105",
    "source_composition_pin": "4ef1ed45bf4bd9b819e267273e622ca6475c4271e6d89672be31396e485f1f1d",
    "checkpoint_pin": "f84621ff8cecc5e7ef5e33f156c1d7329e998727a21d74d0823cb02207422394"}


def same_pin(first, second):
    return (first["sha256"] == second["sha256"]
            and Path(first["path"]).resolve(strict=True) == Path(second["path"]).resolve(strict=True)
            and ("identity_sha256" not in first or "identity_sha256" not in second
                 or first["identity_sha256"] == second["identity_sha256"]))


def check_stage_lineage(composition):
    lineage = composition["stage_lineage"]
    records = {}
    for key, expected in SOURCE_STAGE_SHA256.items():
        pin = lineage[key]
        if pin["sha256"] != expected:
            raise ValueError("wrong_fixed_saved_boolean_stage:" + key)
        records[key] = read(pin)
    index, source, checkpoint = (records[key] for key in SOURCE_STAGE_SHA256)
    if (index["schema"] != "td-hybrid-surface-composition-preparation-v2"
            or source["schema"] != "td-hybrid-surface-composition-v2"
            or checkpoint["schema"] != "td-hybrid-surface-composition-boolean-checkpoint-v2"
            or not same_pin(index["composition"], lineage["source_composition_pin"])
            or not same_pin(source["checkpoint_boolean_pin"], lineage["checkpoint_pin"])
            or checkpoint["artifacts"] != lineage["boolean_artifact_pins"]
            or any(record["inputs"] != composition["inputs"] for record in records.values())
            or source["status"] != lineage["source_status"] or index["status"] != source["status"]
            or source["rejection_reasons"] != lineage["source_rejection_reasons"]
            or index["rejection_reasons"] != source["rejection_reasons"]):
        raise ValueError("saved_boolean_stage_original_pins_inputs_or_refusal_changed")
    if (checkpoint["status"] != "boolean_stage_unverified" or checkpoint["portal_checks_started"] is not False
            or source["boolean_stage_preserved"] is not True
            or not same_pin(composition["checkpoint_boolean_pin"], lineage["checkpoint_pin"])
            or set(lineage["boolean_artifact_pins"]) != {
                "surface_cutter", "coupled_cutter", "rock_after", "removed", "extra_removed", "surface_prisms"}):
        raise ValueError("saved_boolean_stage_incomplete_or_changed")
    for group, lineage_key in (("code_sha256", "source_code_sha256"),
                               ("readonly_dependency_code_sha256", "source_readonly_dependency_code_sha256")):
        if any(record[group] != lineage[lineage_key] for record in records.values()):
            raise ValueError("saved_boolean_stage_original_source_map_changed")
        for name, expected in lineage[lineage_key].items():
            path = (ROOT / name).resolve(strict=True)
            if not path.is_relative_to(ROOT) or file_sha(path) != expected:
                raise ValueError("saved_boolean_stage_original_source_changed:" + name)
    for name, pin in lineage["boolean_artifact_pins"].items():
        if name not in index["artifacts"] or not same_pin(index["artifacts"][name], pin):
            raise ValueError("saved_boolean_stage_artifact_not_in_original_index:" + name)
        if name == "surface_prisms":
            actual_pin = composition["surface_prisms_pin"]
        else:
            actual_pin = composition["mesh_pins"][name]
        if not same_pin(actual_pin, pin):
            raise ValueError("saved_boolean_stage_main_artifact_replaced:" + name)
        read(pin)
        guard()


def check_native_identity_binding(binding, inputs, sections):
    expected = sections["hierarchy_identity_sha256"]
    if (binding["verified"] is not True
            or binding["original_pin"] != inputs["original_hierarchy"]
            or binding["sections_pin"] != inputs["original_06_sections"]
            or binding["wet_protection_pin"] != inputs["original_wet_protection_manifest"]
            or binding["identity_source"] != "pinned_original_06_sections.hierarchy_identity_sha256"
            or binding["expected_hierarchy_identity_sha256"] != expected
            or binding["manifest_hierarchy_identity_sha256"] != expected
            or binding["original_inputs_or_pin_modified"] is not False
            or binding["archive_and_array_budgets_unchanged"] is not True):
        raise ValueError("audit_v4_native_identity_not_bound_to_original_sections_and_manifest")


def check_resumed_evidence(audit, parent, composition_pin, composition):
    resumed = audit["resumed_evidence"]
    if (resumed["audit_pin"]["sha256"] != "82aad9f51e59b4a9718b69d8c7a2b85e501e847d7f976cadadb1bb84ebdfb2a0"
            or parent["schema"] != "td-hybrid-surface-composition-independent-audit-v4"
            or parent["status"] != "refused" or not parent["errors"]
            or resumed["audit_identity_sha256"] != parent["identity_sha256"]
            or resumed["composition_pin"] != composition_pin or parent["composition_pin"] != composition_pin
            or resumed["composition_identity_sha256"] != composition["identity_sha256"]
            or parent["composition_identity_sha256"] != composition["identity_sha256"]
            or resumed["completed_stages"] != ["native_binding", "native_prisms", "material"]
            or resumed["native_prisms_material_inherited"] is not True
            or resumed["source_material_recomputed"] is not False
            or resumed["ports_inherited"] is not False or resumed["audit_code_sha256_matched"] is not True
            or sorted(resumed["validated_mesh_roles"]) != sorted(composition["mesh_pins"])
            or parent["native_half_arm_sources_verified"] is not True or parent["materials_verified"] is not True
            or parent["two_sided_complete_port_verified"] is not False
            or audit["new_stages_completed"] != ["port:sink", "port:spring"]):
        raise ValueError("audit_v5_resumed_source_material_evidence_not_bound_to_original_report")
    if (audit["schema"] == "td-hybrid-surface-composition-independent-audit-v6"
            and (resumed.get("failed_continuation_sha256") !=
                 "ba3da3e65c41db558b52fd2fb046d89f571f06f4fd41cd572fcdeb309f80e245")):
        raise ValueError("audit_v6_failed_v5_continuation_not_bound")
    fields = ("inherited_evidence", "native_identity_binding", "source_reports", "material",
              "material_boolean_evidence", "mesh_validation_reports", "stage_lineage", "inputs", "mesh_pins")
    if any(audit[field] != parent[field] for field in fields):
        raise ValueError("audit_v5_inherited_source_material_evidence_changed")
    winding = audit["interval_winding"]
    from terrain_pipeline.hybrid_river_graph import identity
    if (winding["every_query_certified"] is not True or not isinstance(winding["queries"], list)
            or not winding["queries"] or identity(winding["policy"]) != winding["policy_identity_sha256"]
            or winding["policy"].get("tolerance_rational") != str(Fraction.from_float(1e-7))):
        raise ValueError("audit_v5_interval_winding_evidence_missing_or_uncertified")
    required = ("mesh_pin", "solid_label", "original_vertex_triangle_identity_sha256", "point_local_xyz_m",
                "point_exact_rational_xyz_m", "triangle_count", "triangle_interval_evaluations", "attempts",
                "certified_target", "returned_value", "tolerance_rational", "lower_rational", "upper_rational",
                "maximum_absolute_error_rational", "verified", "whole_interval_inside_original_tolerance",
                "source_vertices_or_triangles_modified", "decimal_digits")
    for query in winding["queries"]:
        if (any(field not in query for field in required) or query["verified"] is not True
                or query["whole_interval_inside_original_tolerance"] is not True
                or query["source_vertices_or_triangles_modified"] is not False
                or query["certified_target"] not in (0, 1)
                or query["returned_value"] != float(query["certified_target"])
                or query["tolerance_rational"] != str(Fraction.from_float(1e-7))
                or query["decimal_digits"] not in (50, 100, 160)
                or not isinstance(query["attempts"], list)
                or not isinstance(query["triangle_interval_evaluations"], int)
                or query["triangle_interval_evaluations"] < 1):
            raise ValueError("audit_v5_interval_query_certificate_incomplete")


def load_composition(index_pin, audit_pin):
    from terrain_pipeline.hybrid_surface_composition_v3 import POLICY_SHA256 as COMPOSITION_POLICY_SHA256
    index = read(index_pin)
    if index["schema"] != "td-hybrid-surface-composition-preparation-v3":
        raise ValueError("wrong_composition_index_schema")
    composition_pin = index["composition"]
    composition = read(composition_pin)
    audit = read(audit_pin)
    if (composition["schema"] != "td-hybrid-surface-composition-v3"
            or composition["status"] != "candidate_unverified" or composition["rejection_reasons"]
            or index["status"] != composition["status"] or index["rejection_reasons"] != composition["rejection_reasons"]
            or composition["policy_identity_sha256"] != COMPOSITION_POLICY_SHA256
            or composition["inputs"] != index["inputs"]
            or composition["code_sha256"] != index["code_sha256"]
            or composition["readonly_dependency_code_sha256"] != index["readonly_dependency_code_sha256"]
            or index["policy_identity_sha256"] != composition["policy_identity_sha256"]
            or audit["schema"] != "td-hybrid-surface-composition-independent-audit-v6"
            or audit["status"] != "passed" or audit["errors"]
            or audit["two_sided_complete_port_verified"] is not True
            or not same_pin(audit["composition_pin"], composition_pin)
            or audit["composition_identity_sha256"] != composition["identity_sha256"]
            or audit["inputs"] != composition["inputs"]
            or audit["mesh_pins"] != composition["mesh_pins"]
            or audit["surface_prisms_pin"] != composition["surface_prisms_pin"]
            or audit["materials_verified"] is not True or audit["native_half_arm_sources_verified"] is not True
            or audit["material"]["independent_boolean_verified"] is not True):
        raise ValueError("composition_independent_material_audit_binding_missing_or_invalid")
    policy = composition["numerical_slice_policy"]
    numerical_identity = composition["numerical_slice_policy_identity_sha256"]
    from terrain_pipeline.hybrid_river_graph import identity
    from terrain_pipeline.hybrid_mesh_plane_v2 import NUMERICAL_POLICY, NUMERICAL_POLICY_SHA256
    if (identity(policy) != numerical_identity or policy != NUMERICAL_POLICY or numerical_identity != NUMERICAL_POLICY_SHA256
            or audit["numerical_slice_policy"] != policy
            or audit["numerical_slice_policy_identity_sha256"] != numerical_identity
            or index["numerical_slice_policy"] != policy or index["numerical_slice_policy_identity_sha256"] != numerical_identity):
        raise ValueError("exact_slice_numerical_identity_not_bound_across_composition_and_audit")
    lineage = composition["stage_lineage"]
    if (not isinstance(lineage, dict) or lineage.get("main_boolean_recomputed") is not False
            or index["stage_lineage"] != lineage or audit["stage_lineage"] != lineage):
        raise ValueError("saved_stage_replay_lineage_not_bound_across_composition_and_audit")
    if audit["stage_lineage_verified"] is not True:
        raise ValueError("saved_stage_replay_lineage_not_independently_verified")
    check_stage_lineage(composition)
    geometry_pin, geometry_audit_pin = composition["inputs"]["geometry"], composition["inputs"]["geometry_audit"]
    geometry, vdm, attachments, ports, original_meshes = load_inputs(geometry_pin, geometry_audit_pin)
    sections = read(geometry["inputs"]["original_06_sections"])
    check_native_identity_binding(audit["native_identity_binding"], geometry["inputs"], sections)
    resumed_parent = read(audit["resumed_evidence"]["audit_pin"])
    check_resumed_evidence(audit, resumed_parent, composition_pin, composition)
    failed_continuation = audit["resumed_evidence"].get("failed_continuation_pin")
    if (not isinstance(failed_continuation, dict)
            or failed_continuation.get("sha256") != "ba3da3e65c41db558b52fd2fb046d89f571f06f4fd41cd572fcdeb309f80e245"):
        raise ValueError("audit_v6_failed_v5_pin_missing")
    failed = read(failed_continuation)
    if (failed["schema"] != "td-hybrid-surface-composition-independent-audit-v5"
            or failed["status"] != "refused"
            or failed["failure_stage"] != "v4_parent_binding"
            or failed["errors"] != ["v4_parent_binding: KeyError: 'path'"]):
        raise ValueError("audit_v6_failed_v5_report_changed")
    for name, expected in resumed_parent["code_sha256"].items():
        source_path = (ROOT / name).resolve(strict=True)
        if not source_path.is_relative_to(ROOT) or file_sha(source_path) != expected:
            raise ValueError("resumed_composition_audit_source_changed:" + name)
    inherited = audit["inherited_evidence"]
    prior = read(inherited["audit_pin"])
    if (inherited["audit_pin"]["sha256"] != "4ea6f5700735395e3591a744a25d22ab520a6ae486d4c5c2d3a201c83d01a977"
            or composition_pin["sha256"] != "88ed045a0589d130a2622cba3b4ace4a139b6513ebca2616a1bae67bdda0e4b6"
            or prior["schema"] != "td-hybrid-surface-composition-independent-audit-v3"
            or inherited["audit_identity_sha256"] != prior["identity_sha256"]
            or not same_pin(inherited["composition_pin"], composition_pin)
            or not same_pin(prior["composition_pin"], composition_pin)
            or inherited["composition_identity_sha256"] != composition["identity_sha256"]
            or prior["composition_identity_sha256"] != composition["identity_sha256"]
            or inherited["completed_stages"] != ["stage_lineage", "mesh_validation"]
            or inherited["mesh_validation_inherited"] is not True
            or inherited["exact_mesh_recomputed"] is not False
            or inherited["source_material_ports_inherited"] is not False
            or inherited["audit_code_sha256_matched"] is not True
            or sorted(inherited["mesh_roles"]) != sorted(composition["mesh_pins"])
            or sorted(inherited["validated_mesh_roles"]) != sorted(composition["mesh_pins"])
            or audit["mesh_validation_reports"] != prior["mesh_validation_reports"]
            or sorted(audit["mesh_validation_reports"]) != sorted(inherited["mesh_roles"])):
        raise ValueError("audit_v4_inherited_mesh_evidence_not_bound_to_original_report")
    for name, expected in prior["code_sha256"].items():
        source_path = (ROOT / name).resolve(strict=True)
        if not source_path.is_relative_to(ROOT) or file_sha(source_path) != expected:
            raise ValueError("inherited_composition_audit_source_changed:" + name)
    if (geometry_pin["sha256"] != GEOMETRY_SHA
            or audit["geometry_sha256"] != GEOMETRY_SHA
            or audit["policy_identity_sha256"] != composition["policy_identity_sha256"]
            or composition["geometry_identity_sha256"] != geometry["identity_sha256"]
            or composition["graph_identity_sha256"] != geometry["graph_identity_sha256"]
            or composition["inputs"]["vdm"] != geometry["vdm_pin"]
            or composition["inputs"]["surface_attachments"] != geometry["surface_attachments_pin"]
            or composition["mesh_pins"]["rock_before"] != geometry["mesh_pins"]["rock_before"]
            or any(composition["mesh_pins"]["original_" + name] != geometry["mesh_pins"][name]
                   for name in ("cutter", "rock_after", "removed"))):
        raise ValueError("coupled_composition_changed_original_geometry_VDM_or_mesh_identity")
    for group in ("code_sha256", "readonly_dependency_code_sha256"):
        for name, expected in composition[group].items():
            source_path = (ROOT / name).resolve(strict=True)
            if not source_path.is_relative_to(ROOT) or file_sha(source_path) != expected:
                raise ValueError("composition_or_readonly_dependency_code_changed:" + name)
    for name, expected in audit["code_sha256"].items():
        source_path = (ROOT / name).resolve(strict=True)
        if not source_path.is_relative_to(ROOT) or file_sha(source_path) != expected:
            raise ValueError("independent_composition_audit_source_changed:" + name)
    for kind, attachment in attachments["attachments"].items():
        if composition["inputs"]["surface_nodes"][kind] != attachment["surface_node_pin"]:
            raise ValueError("coupled_half_arm_node_binding_changed")
        read(attachment["surface_node_pin"])
        report = audit["portal_reports"].get(kind)
        if (not report or report.get("verified") is not True or report.get("two_sided_complete_port_verified") is not True
                or report["port_identity_sha256"] != ports[kind]["identity_sha256"]
                or report["canonical_port_pin"] != attachment["canonical_port_pin"]
                or report["offset_slices_not_acceptance_basis"] is not True):
            raise ValueError("independent_two_sided_port_bound_to_other_canonical_port")
    meshes = {name: read(composition["mesh_pins"]["coupled_cutter" if name == "cutter" else name])
              for name in ("cutter", "rock_after", "removed", "rock_before")}
    meshes["original_cutter"] = original_meshes["cutter"]
    prisms = read(composition["surface_prisms_pin"])
    if (prisms["schema"] != "td-hybrid-surface-prisms-v1"
            or prisms["common_local_origin_xyz_m"] != meshes["cutter"]["local_origin_xyz_m"]):
        raise ValueError("unknown_or_unbound_surface_prism_role_sources")
    return composition, audit, geometry, vdm, attachments, ports, meshes, prisms


def prepare(output, index_pin, audit_pin):
    import manifold3d
    if version("manifold3d") != "3.5.4":
        raise ValueError("fixed_manifold3d_3.5.4_required")
    for name, expected in FROZEN_CODE.items():
        if file_sha(ROOT / name) != expected:
            raise ValueError("frozen_v1_face_source_changed:" + name)
    output = Path(output).resolve()
    if output.exists() or output.parent not in (BASE.resolve(), (ROOT / "verification/hybrid-river-network").resolve()):
        raise ValueError("new_bounded_verification_package_required")
    started = time.monotonic()
    composition, audit, geometry, vdm, attachments, ports, meshes, prisms = load_composition(index_pin, audit_pin)
    inputs = {"geometry": composition["inputs"]["geometry"], "geometry_audit": composition["inputs"]["geometry_audit"],
              "graph": composition["inputs"]["graph"], "vdm": composition["inputs"]["vdm"],
              "surface_attachments": composition["inputs"]["surface_attachments"],
              "composition_index": index_pin, "composition": read(index_pin)["composition"],
              "composition_audit": audit_pin, "original_inputs": composition["inputs"],
              "stage_lineage": composition["stage_lineage"],
              "mesh_pins": composition["mesh_pins"], "surface_prisms": composition["surface_prisms_pin"]}
    code = {name: file_sha(ROOT / name) for name in CODE_FILES}
    dependencies = {**FROZEN_CODE, **composition["code_sha256"], **composition["readonly_dependency_code_sha256"],
                    **audit["code_sha256"]}
    exact_source = "terrain_pipeline/hybrid_mesh_plane_v2.py"
    if exact_source not in dependencies or file_sha(ROOT / exact_source) != dependencies[exact_source]:
        raise ValueError("exact_mesh_plane_source_pin_missing_or_changed")
    try:
        faces = build_faces(geometry, vdm, attachments, ports, meshes, composition, audit, prisms, audit_pin)
    except (ValueError, MemoryError) as error:
        faces = seal({"schema": SCHEMA, "status": "refused", "rejection_reasons": [str(error)],
                      "faces": [], "face_count": 0, "unknown_geometry_not_zero_flow": True,
                      "independent_audit_passed": False, "hydraulic_solved": False})
    faces.update(inputs=inputs, code_sha256=code, readonly_dependency_code_sha256=dependencies,
                 stage_lineage=composition["stage_lineage"],
                 policy_identity_sha256=POLICY_SHA256,
                 numerical_slice_policy=composition["numerical_slice_policy"],
                 numerical_slice_policy_identity_sha256=composition["numerical_slice_policy_identity_sha256"],
                 runtime={"manifold3d": version("manifold3d"), "manifold3d_binary_sha256": file_sha(manifold3d.__file__),
                          "shapely": version("shapely")})
    seal(faces)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".coupled-polygon-faces-", dir=output.parent) as temporary:
        staging = Path(temporary) / "package"
        staging.mkdir()
        try:
            face_pin = save(staging / "faces.json", faces, output / "faces.json")
        except ValueError as error:
            faces = seal({"schema": SCHEMA, "status": "refused", "rejection_reasons": [str(error)],
                          "faces": [], "face_count": 0, "inputs": inputs, "code_sha256": code,
                          "readonly_dependency_code_sha256": dependencies, "policy_identity_sha256": POLICY_SHA256,
                          "stage_lineage": composition["stage_lineage"],
                          "numerical_slice_policy": composition["numerical_slice_policy"],
                          "numerical_slice_policy_identity_sha256": composition["numerical_slice_policy_identity_sha256"],
                          "whole_package_budget_refused_no_selected_subset": True,
                          "independent_audit_passed": False, "hydraulic_solved": False})
            face_pin = save(staging / "faces.json", faces, output / "faces.json")
        result = seal({"schema": "td-hybrid-river-faces-preparation-v2", "status": faces["status"],
                       "rejection_reasons": faces["rejection_reasons"], "faces": face_pin, "inputs": inputs,
                       "geometry_identity_sha256": geometry["identity_sha256"], "graph_identity_sha256": geometry["graph_identity_sha256"],
                       "composition_identity_sha256": composition["identity_sha256"], "policy_identity_sha256": POLICY_SHA256,
                       "stage_lineage": composition["stage_lineage"],
                       "numerical_slice_policy": composition["numerical_slice_policy"],
                       "numerical_slice_policy_identity_sha256": composition["numerical_slice_policy_identity_sha256"],
                       "code_sha256": code, "readonly_dependency_code_sha256": dependencies,
                       "independent_audit_passed": False, "hydraulic_solved": False,
                       "resource": {"elapsed_wall_s": time.monotonic() - started, "actual_peak_rss_bytes": guard(),
                                    "max_file_bytes": MAX_BYTES, "max_rss_bytes": MAX_RSS,
                                    "solver_calls": 0, "old_packages_changed": False}})
        save(staging / "index.json", result, output / "index.json")
        staging.rename(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("composition-index", "composition-audit"):
        parser.add_argument("--" + name, required=True, type=Path)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args.output,
        {"path": str(args.composition_index.resolve(strict=True)), "sha256": args.composition_index_sha256},
        {"path": str(args.composition_audit.resolve(strict=True)), "sha256": args.composition_audit_sha256})
    print(json.dumps({"status": result["status"], "rejection_reasons": result["rejection_reasons"]}))
    return 0 if result["status"] == "candidate_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
