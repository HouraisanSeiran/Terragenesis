"""Continue the fixed v5 audit after its saved-input pin traversal bug."""

import argparse
import copy
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import audit_hybrid_surface_composition_v4 as v4
from tools import audit_hybrid_surface_composition_v5 as v5
from tools.hybrid_interval_winding_saved_audit import (
    IntervalSolid, POLICY, POLICY_SHA256, runtime_identity)
from tools.hybrid_surface_resume_saved_audit import ValidatedSolid
from tools.td_shared_channel_fine_saved_audit import (
    MAX_BYTES, check_memory, checked_path, digest, file_sha256, read, read_audit, require)

AUDIT_SCHEMA = "td-hybrid-surface-composition-independent-audit-v6"
COMPOSITION_SHA256 = v4.COMPOSITION_SHA256
V5_AUDIT_SHA256 = "ba3da3e65c41db558b52fd2fb046d89f571f06f4fd41cd572fcdeb309f80e245"
V4_AUDIT_SHA256 = "82aad9f51e59b4a9718b69d8c7a2b85e501e847d7f976cadadb1bb84ebdfb2a0"
BASE = v4.BASE
V4_PATH = BASE / "independent-audit-v2.json"

V5_CODE = {**v5.PREVIOUS_CODE,
    "tools/audit_hybrid_surface_composition_v5.py": "bb1500f24ebdc3702645ea7676de6a774556f8bdd79b479ab7600eac4783fb16",
    "tools/hybrid_interval_winding_saved_audit.py": "cc9fe11238bbdcd70ae14f32d73e83108c50c631515076412ed656715a563d81",
    "tests/test_hybrid_surface_composition_v5_saved_audit.py": "127a62a35c4b823e417f39bd3a70ef88a56a18aa468c863f684c306a6d0bed67"}
ERRORS = v5.ERRORS


def iter_input_pins(record):
    inputs = record["inputs"]
    for name in ("geometry", "geometry_audit", "graph", "original_source_sampling",
                 "surface_attachments", "vdm"):
        yield "inputs." + name, inputs[name]
    for name, pin in inputs["mesh_pins"].items():
        yield "inputs.mesh_pins." + name, pin
    for name, pin in inputs["surface_nodes"].items():
        yield "inputs.surface_nodes." + name, pin


def validate_parent(composition_pin, v5_pin, v4_pin):
    require(composition_pin["sha256"] == COMPOSITION_SHA256
            and v5_pin["sha256"] == V5_AUDIT_SHA256
            and v4_pin["sha256"] == V4_AUDIT_SHA256,
            "only fixed composition03/v5/v4 continuation authorized")
    record, failed_v5 = read(composition_pin), read_audit(v5_pin)
    require(failed_v5["schema"] == v5.AUDIT_SCHEMA and failed_v5["status"] == "refused"
            and failed_v5["composition_pin"] == composition_pin
            and failed_v5["failure_stage"] == "v4_parent_binding"
            and failed_v5["errors"] == ["v4_parent_binding: KeyError: 'path'"]
            and failed_v5["code_sha256"] == V5_CODE,
            "v5 failure report or code binding differs")
    for name, sha in V5_CODE.items():
        require(file_sha256(ROOT / name) == sha, "fixed v5 source changed: " + name)
    old_record, parent = read(composition_pin), read_audit(v4_pin)
    require(parent["composition_pin"] == composition_pin
            and parent["schema"] == v4.AUDIT_SCHEMA
            and parent["status"] == "refused"
            and parent["composition_identity_sha256"] == old_record["identity_sha256"]
            and parent["code_sha256"] == {
                **v4.PREVIOUS_CODE,
                "tools/audit_hybrid_surface_composition_v4.py":
                    "9db6e56a046c4fb3fc4319add596c2e828a1763dabfffaf372f0a94c03b39396",
                "tools/hybrid_surface_resume_saved_audit.py":
                    "d96494f0bf0467700e70dcf8ef2231d96002f2cf56572aeeb896a77f4c0844f5",
                "tests/test_hybrid_surface_composition_v4_saved_audit.py":
                    "c57b87e2efbd6225fd22db586ec7a2380ff9b5668ed6db0938a42e1c7924f2a6"},
            "fixed v4 parent binding differs")
    v4.validate_resume_parent(composition_pin, parent["inherited_evidence"]["audit_pin"])
    require(parent["new_stages_completed"] == ["native_binding", "native_prisms", "material"]
            and parent["native_half_arm_sources_verified"] is True
            and parent["materials_verified"] is True
            and parent["two_sided_complete_port_verified"] is False,
            "v4 completed evidence boundary differs")
    require(record["identity_sha256"] == old_record["identity_sha256"], "composition identity changed")
    for label, pin in iter_input_pins(record):
        checked_path(pin)
    for name in ("source_index_pin", "source_composition_pin", "checkpoint_pin"):
        checked_path(record["stage_lineage"][name])
    for pin in record["stage_lineage"]["boolean_artifact_pins"].values():
        checked_path(pin)
    checked_path(record["checkpoint_boolean_pin"])
    geometry = read(record["inputs"]["geometry"])
    sections_pin = geometry["inputs"]["original_06_sections"]
    sections = read(sections_pin)
    checked_path(geometry["inputs"]["original_hierarchy"])
    checked_path(geometry["inputs"]["original_wet_protection_manifest"])
    binding = parent["native_identity_binding"]
    require(binding["verified"] is True and binding["original_inputs_or_pin_modified"] is False
            and binding["original_pin"] == geometry["inputs"]["original_hierarchy"]
            and binding["sections_pin"] == sections_pin
            and binding["expected_hierarchy_identity_sha256"]
            == binding["manifest_hierarchy_identity_sha256"] == sections["hierarchy_identity_sha256"],
            "v4 native binding differs")
    require(parent["material_boolean_evidence"] == parent["material"]
            and parent["material"]["independent_boolean_verified"] is True,
            "v4 material evidence differs")
    return record, parent, geometry


def resume(composition_pin, v5_pin, v4_pin, report):
    report["current_stage"] = "v5_parent_binding"
    record, parent, geometry = validate_parent(composition_pin, v5_pin, v4_pin)
    inherited_names = (
        "composition_identity_sha256", "inputs", "mesh_pins", "surface_prisms_pin",
        "checkpoint_boolean_pin", "stage_lineage", "stage_lineage_verified",
        "mesh_validation_reports", "geometry_sha256", "policy_identity_sha256",
        "inherited_evidence", "native_identity_binding", "source_reports",
        "original_source_sampling_cut_lookup_mismatches", "native_half_arm_sources_verified",
        "materials_verified", "material_boolean_evidence", "material",
        "numerical_slice_policy", "numerical_slice_policy_identity_sha256",
        "solid_validation_policy", "solid_validation_policy_identity_sha256", "tolerances")
    for name in inherited_names:
        report[name] = copy.deepcopy(parent[name])
    report["resumed_evidence"] = {
        "audit_pin": v4_pin, "audit_identity_sha256": parent["identity_sha256"],
        "failed_continuation_pin": v5_pin, "failed_continuation_sha256": V5_AUDIT_SHA256,
        "composition_pin": composition_pin, "composition_identity_sha256": record["identity_sha256"],
        "completed_stages": ["native_binding", "native_prisms", "material"],
        "native_prisms_material_inherited": True, "source_material_recomputed": False,
        "ports_inherited": False, "audit_code_sha256_matched": True,
        "validated_mesh_roles": []}
    report["current_stage"] = "interval_runtime_binding"
    report["interval_winding"]["runtime"] = runtime_identity()
    meshes, origin = {}, None
    for role, pin in record["mesh_pins"].items():
        report["current_stage"] = "bind_original_mesh:" + role
        mesh = read(pin)
        require(mesh["role"] == role.removeprefix("original_"), "original mesh role differs")
        own_origin = np.asarray(mesh["local_origin_xyz_m"], float)
        require(own_origin.shape == (3,) and np.isfinite(own_origin).all(), "invalid original mesh origin")
        if origin is None:
            origin = own_origin
        require(np.array_equal(origin, own_origin), "original mesh frames differ")
        meshes[role] = IntervalSolid(
            ValidatedSolid(mesh, parent["mesh_validation_reports"][role], role),
            pin, report["interval_winding"]["queries"])
        report["resumed_evidence"]["validated_mesh_roles"].append(role)
    report["current_stage"] = "read_saved_port_inputs"
    prisms = read(record["surface_prisms_pin"])
    attachments, vdm = read(record["inputs"]["surface_attachments"]), read(record["inputs"]["vdm"])
    for kind in ("sink", "spring"):
        report["current_stage"] = "port:" + kind
        report["exact_slice_reports"][kind] = {}
        try:
            report["portal_reports"][kind] = v4.frozen.audit_port(
                kind, record, prisms, geometry, attachments, vdm, meshes, origin,
                report["exact_slice_reports"][kind])
            report["new_stages_completed"].append("port:" + kind)
        except ERRORS as error:
            v4.record_failure(report, report["current_stage"], error)
            report["portal_reports"][kind] = {
                "verified": False, "two_sided_complete_port_verified": False,
                "errors": [report["errors"][-1]]}
    queries = report["interval_winding"]["queries"]
    certified = bool(queries) and all(query.get("verified") is True for query in queries)
    report["interval_winding"]["every_query_certified"] = certified
    passed = certified and not report["errors"] and all(
        report["portal_reports"][kind].get("two_sided_complete_port_verified") is True
        for kind in ("sink", "spring"))
    report.update(status="passed" if passed else "refused",
                  two_sided_complete_port_verified=passed, current_stage="complete")


def audit(composition_pin, v5_pin, v4_pin):
    report = {"schema": AUDIT_SCHEMA, "status": "refused", "errors": [], "failures": [],
        "failure_stage": None, "composition_pin": composition_pin, "new_stages_completed": [],
        "portal_reports": {}, "exact_slice_reports": {}, "native_half_arm_sources_verified": False,
        "materials_verified": False, "two_sided_complete_port_verified": False,
        "hydraulic_constitutive_law_accepted": False, "hydraulic_solved": False,
        "native_exact": False, "fine15_replaced": False,
        "original_sampling_defects_revalidated_as_correct": False,
        "whole_link_control_sill_verified": False, "builder_or_slicer_called": False,
        "scope": "fixed_v4_native_prisms_material_inherited_only_unresolved_full_ports_rechecked",
        "interval_winding": {"policy": POLICY, "policy_identity_sha256": POLICY_SHA256,
                             "queries": [], "every_query_certified": False}}
    try:
        resume(composition_pin, v5_pin, v4_pin, report)
    except ERRORS as error:
        v4.record_failure(report, report.get("current_stage", "audit_entry"), error)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--composition", type=Path, default=BASE / "composition.json")
    parser.add_argument("--composition-sha256", default=COMPOSITION_SHA256)
    parser.add_argument("--previous-audit", type=Path, default=BASE / "independent-audit-v3.json")
    parser.add_argument("--previous-audit-sha256", default=V5_AUDIT_SHA256)
    parser.add_argument("--v4-audit", type=Path, default=V4_PATH)
    parser.add_argument("--v4-audit-sha256", default=V4_AUDIT_SHA256)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / "verification"),
            "new verification audit file required")
    started = time.monotonic()
    report = audit({"path": str(args.composition.resolve()), "sha256": args.composition_sha256},
                   {"path": str(args.previous_audit.resolve()), "sha256": args.previous_audit_sha256},
                   {"path": str(args.v4_audit.resolve()), "sha256": args.v4_audit_sha256})
    report["resource"] = {"wall_seconds": time.monotonic() - started,
        "actual_peak_rss_bytes": check_memory(), "solver_calls": 0,
        "source_artifacts_modified": False, "exact_mesh_recomputations": 0,
        "native_prism_material_recomputations": 0, "producer_stage_recomputations": 0,
        "interval_triangle_evaluations": sum(q.get("triangle_interval_evaluations", 0)
                                             for q in report["interval_winding"]["queries"])}
    report["code_sha256"] = {**V5_CODE, "tools/audit_hybrid_surface_composition_v6.py":
        file_sha256(ROOT / "tools/audit_hybrid_surface_composition_v6.py"),
        "tests/test_hybrid_surface_composition_v6_saved_audit.py":
        file_sha256(ROOT / "tests/test_hybrid_surface_composition_v6_saved_audit.py")}
    report["identity_sha256"] = digest(report)
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(len(payload) <= MAX_BYTES, "continuation audit exceeds 64MiB")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(json.dumps({"status": report["status"], "errors": report["errors"],
                      "failure_stage": report["failure_stage"], "output": str(output),
                      "sha256": file_sha256(output)}))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
