"""Bounded continuation of the fixed v3 audit, retaining completed mesh evidence."""

import argparse
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import audit_hybrid_surface_composition_v3 as frozen
from tools.hybrid_surface_resume_saved_audit import ValidatedSolid, load_native_bound
from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, check_memory, compare, digest, file_sha256, read, read_audit, require)

AUDIT_SCHEMA = "td-hybrid-surface-composition-independent-audit-v4"
COMPOSITION_SHA256 = "88ed045a0589d130a2622cba3b4ace4a139b6513ebca2616a1bae67bdda0e4b6"
PREVIOUS_AUDIT_SHA256 = "4ea6f5700735395e3591a744a25d22ab520a6ae486d4c5c2d3a201c83d01a977"
BASE = ROOT / "verification/natural-river-network/hybrid-surface-composition-20261006-03"
PREVIOUS_CODE = {
    "tests/test_hybrid_surface_composition_v3_saved_audit.py": "5900221e64c864a909992daeb34c5aced97b5636d52fad137234d584d8f66924",
    "tools/audit_hybrid_river_faces.py": "f16987cfbcef80977b96c948c125757d55002d0dbab9d6ae9d3eea80bde71ded",
    "tools/audit_hybrid_surface_composition.py": "bb655a3a06ae410b22c72810d18a73a5c7b576b809a4ce9d0ef853255337b585",
    "tools/audit_hybrid_surface_composition_v3.py": "6d1a59873b8543b25c532fdfbf4265fec2e93a9a394a0232242796926013cd3d",
    "tools/hybrid_cave_saved_audit.py": "9fbdbb83b5b5ca54c3da815d1288d45ffd40fabad0bd12c2d22dd311d2b3474a",
    "tools/hybrid_exact_solid_saved_audit.py": "0fc1adcfabd817aa13558ff2eaade19d8f150d8a2a1322cda2ef8582733f333f",
    "tools/td_shared_channel_fine_saved_audit.py": "f654e5a9730280e5fdd5e03206be1d3de8cb9b92852aeb047b86cee91655b0a9"}
ERRORS = frozen.ERRORS + (AttributeError, OverflowError, ZeroDivisionError)


def validate_resume_parent(composition_pin, previous_pin):
    require(composition_pin["sha256"] == COMPOSITION_SHA256
            and previous_pin["sha256"] == PREVIOUS_AUDIT_SHA256, "only fixed composition03/audit-v1 continuation authorized")
    record, parent = read(composition_pin), read_audit(previous_pin)
    require(record["schema"] == "td-hybrid-surface-composition-v3"
            and record["status"] == "candidate_unverified" and not record["rejection_reasons"]
            and parent["schema"] == frozen.AUDIT_SCHEMA and parent["status"] == "refused"
            and parent["errors"] == ["'identity_sha256'"]
            and parent["composition_pin"] == composition_pin
            and parent["composition_identity_sha256"] == record["identity_sha256"],
            "unknown continuation point or mismatched saved composition")
    require(parent["code_sha256"] == PREVIOUS_CODE, "previous audit code registry differs")
    for name, sha in PREVIOUS_CODE.items():
        require(file_sha256(ROOT / name) == sha, "previous audit frozen source changed: " + name)
    frozen.check_code_pins(record)
    require(parent["stage_lineage_verified"] is True and parent["stage_lineage"] == record["stage_lineage"]
            and parent["inputs"] == record["inputs"] and parent["mesh_pins"] == record["mesh_pins"]
            and parent["surface_prisms_pin"] == record["surface_prisms_pin"]
            and parent["native_half_arm_sources_verified"] is False and parent["materials_verified"] is False
            and parent["two_sided_complete_port_verified"] is False
            and "material_boolean_evidence" not in parent and "portal_reports" not in parent,
            "incomplete/unknown inherited evidence boundaries")
    require(parent["numerical_slice_policy"] == record["numerical_slice_policy"] == frozen.NUMERICAL_POLICY
            and parent["numerical_slice_policy_identity_sha256"] == record["numerical_slice_policy_identity_sha256"]
            == frozen.NUMERICAL_POLICY_SHA256
            and parent["solid_validation_policy"] == frozen.SOLID_POLICY
            and parent["solid_validation_policy_identity_sha256"] == frozen.SOLID_POLICY_SHA256
            and record["policy"] == frozen.POLICY and record["policy_identity_sha256"] == digest(frozen.POLICY),
            "inherited numerical/solid/source policy differs")
    reports = parent["mesh_validation_reports"]
    require(set(reports) == set(record["mesh_pins"]) and len(reports) == 15, "all fifteen completed mesh reports required")
    return record, parent


def validate_material_account(record, meshes, material):
    saved = record["material"]
    for key, expected in (("original_rock_before_m3", meshes["rock_before"].signed_volume),
            ("original_rock_after_m3", meshes["original_rock_after"].signed_volume),
            ("new_rock_after_m3", meshes["rock_after"].signed_volume),
            *((key, material[key]) for key in ("original_removed_m3", "extra_removed_m3", "total_removed_m3"))):
        compare(saved[key], expected, "saved material " + key, atol=1e-7, rtol=1e-9)
    residuals = [saved["original_rock_before_m3"] - saved["original_rock_after_m3"] - saved["original_removed_m3"],
                 saved["original_rock_before_m3"] - saved["new_rock_after_m3"] - saved["total_removed_m3"],
                 saved["total_removed_m3"] - saved["original_removed_m3"] - saved["extra_removed_m3"]]
    compare(saved["signed_residuals_m3"], residuals, "saved signed material residuals", atol=1e-7)
    require(saved["fill_m3"] == 0. and saved["fine15_material_replaced"] is False
            and saved["sampled_solid_material_not_native_exact"] is True
            and abs(saved["residual_tolerance_m3"] - material["comparison_tolerance_m3"]) <= 1e-12,
            "original material semantics or thresholds changed")


def record_failure(report, stage, error):
    message = stage + ": " + type(error).__name__ + ": " + str(error)
    report["errors"].append(message)
    frames = traceback.extract_tb(error.__traceback__)
    source = frames[-1] if frames else None
    report["failure_stage"] = stage
    report["failures"].append({"stage": stage, "error_type": type(error).__name__, "message": str(error),
        "source_path": str(Path(source.filename).resolve()) if source else None,
        "source_line": source.lineno if source else None, "source_function": source.name if source else None})


def resume(composition_pin, previous_pin, report):
    report["current_stage"] = "resume_parent_binding"
    record, parent = validate_resume_parent(composition_pin, previous_pin)
    report.update(composition_identity_sha256=record["identity_sha256"], inputs=record["inputs"],
        mesh_pins=record["mesh_pins"], surface_prisms_pin=record["surface_prisms_pin"],
        checkpoint_boolean_pin=record["checkpoint_boolean_pin"], stage_lineage=record["stage_lineage"],
        stage_lineage_verified=True, mesh_validation_reports=parent["mesh_validation_reports"],
        geometry_sha256=frozen.previous.GEOMETRY_SHA256, policy_identity_sha256=digest(frozen.POLICY),
        inherited_evidence={"audit_pin": previous_pin, "audit_identity_sha256": parent["identity_sha256"],
            "composition_pin": composition_pin, "composition_identity_sha256": record["identity_sha256"],
            "completed_stages": ["stage_lineage", "mesh_validation"], "mesh_roles": sorted(record["mesh_pins"]),
            "mesh_validation_inherited": True, "exact_mesh_recomputed": False,
            "source_material_ports_inherited": False, "audit_code_sha256_matched": True,
            "validated_mesh_roles": []})
    meshes, origin = {}, None
    for role, pin in record["mesh_pins"].items():
        report["current_stage"] = "inherit_mesh:" + role
        mesh = read(pin)
        require(mesh["role"] == role.removeprefix("original_"), "inherited mesh role differs")
        current = np.asarray(mesh["local_origin_xyz_m"], float)
        require(current.shape == (3,) and np.isfinite(current).all(), "invalid inherited local origin")
        if origin is None:
            origin = current
        require(np.array_equal(origin, current), "inherited meshes do not share local origin")
        meshes[role] = ValidatedSolid(mesh, parent["mesh_validation_reports"][role], role)
        report["inherited_evidence"]["validated_mesh_roles"].append(role)
    report["current_stage"] = "native_source_inputs"
    geometry = read(record["inputs"]["geometry"])
    sections_pin = geometry["inputs"]["original_06_sections"]
    sections = read(sections_pin)
    protection_pin = geometry["inputs"]["original_wet_protection_manifest"]
    protection = read(protection_pin)["wet_protection"]
    attachments, vdm = read(record["inputs"]["surface_attachments"]), read(record["inputs"]["vdm"])
    report["current_stage"] = "native_manifest_binding"
    native, binding = load_native_bound(geometry["inputs"]["original_hierarchy"],
        sections["hierarchy_identity_sha256"], sections["selected_leaf_ids"], protection)
    binding.update(sections_pin=sections_pin, wet_protection_pin=protection_pin)
    report["native_identity_binding"] = binding
    report["new_stages_completed"].append("native_binding")
    report["current_stage"] = "native_half_arm_prisms"
    prisms = read(record["surface_prisms_pin"])
    _, sources = frozen.audit_prisms(prisms, attachments, vdm, native, origin, meshes)
    report.update(native_half_arm_sources_verified=True, source_reports=sources,
        original_source_sampling_cut_lookup_mismatches=record["original_source_sampling_cut_lookup_mismatches"])
    report["new_stages_completed"].append("native_prisms")
    report["current_stage"] = "material_independent_boolean"
    material = frozen.previous.audit_material_solids(*(meshes[key] for key in (
        "rock_before", "original_rock_after", "original_removed", "surface_cutter", "coupled_cutter",
        "rock_after", "extra_removed", "removed", "original_cutter")))
    report["material_boolean_evidence"] = material
    report["current_stage"] = "material_saved_account"
    validate_material_account(record, meshes, material)
    report.update(materials_verified=True, material=material)
    report["new_stages_completed"].append("material")
    report["current_stage"] = "coupled_cutter_components"
    library = frozen.manifold_library()
    require(len(meshes["coupled_cutter"].manifold(library).decompose()) == record["coupled_cutter_component_count"] == 1,
            "actual coupled cutter disconnected")
    require(set(record["portal_connections"]) == {"sink", "spring"}, "complete portal census required")
    for kind in ("sink", "spring"):
        report["current_stage"] = "port:" + kind
        report["exact_slice_reports"][kind] = {}
        try:
            report["portal_reports"][kind] = frozen.audit_port(kind, record, prisms, geometry, attachments,
                vdm, meshes, origin, report["exact_slice_reports"][kind])
            report["new_stages_completed"].append("port:" + kind)
        except ERRORS as error:
            record_failure(report, report["current_stage"], error)
            report["portal_reports"][kind] = {"verified": False, "two_sided_complete_port_verified": False,
                                             "errors": [report["errors"][-1]]}
    verified = not report["errors"] and all(report["portal_reports"].get(kind, {}).get("two_sided_complete_port_verified") is True
                                           for kind in ("sink", "spring"))
    report.update(status="passed" if verified else "refused", two_sided_complete_port_verified=verified,
                  current_stage="complete")


def audit(composition_pin, previous_pin):
    report = {"schema": AUDIT_SCHEMA, "status": "refused", "errors": [], "failures": [], "failure_stage": None,
        "composition_pin": composition_pin, "native_half_arm_sources_verified": False, "materials_verified": False,
        "two_sided_complete_port_verified": False, "portal_reports": {}, "exact_slice_reports": {}, "new_stages_completed": [],
        "numerical_slice_policy": frozen.NUMERICAL_POLICY, "numerical_slice_policy_identity_sha256": frozen.NUMERICAL_POLICY_SHA256,
        "solid_validation_policy": frozen.SOLID_POLICY, "solid_validation_policy_identity_sha256": frozen.SOLID_POLICY_SHA256,
        "hydraulic_constitutive_law_accepted": False, "hydraulic_solved": False, "native_exact": False,
        "fine15_replaced": False, "original_sampling_defects_revalidated_as_correct": False,
        "whole_link_control_sill_verified": False, "builder_or_slicer_called": False,
        "scope": "byte_bound_completed_mesh_evidence_and_new_native_material_full_port_cold_checks",
        "tolerances": {"canonical_boundary_m": 1e-8, "whole_port_gap_area_m2": 1e-8, "collar_boolean_difference_m3": 1e-7}}
    try:
        resume(composition_pin, previous_pin, report)
    except ERRORS as error:
        record_failure(report, report.get("current_stage", "audit_entry"), error)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--composition", type=Path, default=BASE / "composition.json")
    parser.add_argument("--composition-sha256", default=COMPOSITION_SHA256)
    parser.add_argument("--previous-audit", type=Path, default=BASE / "independent-audit-v1.json")
    parser.add_argument("--previous-audit-sha256", default=PREVIOUS_AUDIT_SHA256)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / "verification"), "new verification audit file required")
    pin = {"path": str(args.composition.resolve()), "sha256": args.composition_sha256}
    previous_pin = {"path": str(args.previous_audit.resolve()), "sha256": args.previous_audit_sha256}
    started = time.monotonic()
    report = audit(pin, previous_pin)
    report["resource"] = {"wall_seconds": time.monotonic() - started, "actual_peak_rss_bytes": check_memory(),
        "solver_calls": 0, "source_artifacts_modified": False, "exact_mesh_recomputations": 0,
        "producer_stage_recomputations": 0}
    report["code_sha256"] = {**PREVIOUS_CODE, **{name: file_sha256(ROOT / name) for name in (
        "tools/audit_hybrid_surface_composition_v4.py", "tools/hybrid_surface_resume_saved_audit.py",
        "tests/test_hybrid_surface_composition_v4_saved_audit.py")}}
    report["identity_sha256"] = digest(report)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "continuation audit exceeds 64MiB budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(json.dumps({"status": report["status"], "errors": report["errors"], "failure_stage": report["failure_stage"],
                      "output": str(output), "sha256": file_sha256(output)}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
