"""Current fixed-support prism/Boolean/rational-portal/faces assembly; no new physics."""

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import time

from terrain_pipeline.hybrid_geometry import MAX_BYTES, guard, seal
from terrain_pipeline.hybrid_geometry import HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256 as NUMERICAL_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import hybrid_river_faces_mechanism_2_build_faces as build_faces
from terrain_pipeline.hybrid_geometry import build_boolean_stage
from terrain_pipeline.hybrid_geometry import resume_composition
from terrain_pipeline.hybrid_geometry import HYBRID_SURFACE_PRISMS_POLICY as GEOMETRIC_POLICY
from terrain_pipeline.hybrid_geometry import identity
from tools.hybrid_geometry_io import ROOT, GEOMETRY, AUDIT, GEOMETRY_SHA, AUDIT_SHA, file_sha, load_inputs, read, save, CURRENT_GENERATOR_FILES


SCHEMA = "td-hybrid-current-composition-v1"
POLICY = {**GEOMETRIC_POLICY, "version": "original-Boolean-plus-rational-port-integration-v1",
          "main_boolean": "fresh-original-fixed-geometry-Boolean-stage-preserved-before-port-checks",
          "numerical_slice": NUMERICAL_POLICY_SHA256,
          "portal_boolean": "original-bounded-collars-no-added-excavation",
          "integration_only_no_new_physical_law": True}
POLICY_SHA256 = identity(POLICY)
CURRENT_FILES = CURRENT_GENERATOR_FILES


def prepare(output, geometry_pin=None, geometry_audit_pin=None, progress=print):
    from tools.audit_hybrid_geometry_current import audit_composition, audit_faces
    if version("manifold3d") != "3.5.4":
        raise ValueError("fixed manifold3d 3.5.4 required")
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to(ROOT / ".scratch"):
        raise ValueError("new current integration output under workspace .scratch required")
    geometry_pin = geometry_pin or {"path": str(GEOMETRY), "sha256": GEOMETRY_SHA}
    geometry_audit_pin = geometry_audit_pin or {"path": str(AUDIT), "sha256": AUDIT_SHA}
    geometry, vdm, attachments, ports, original = load_inputs(geometry_pin, geometry_audit_pin)
    if len(vdm["stations"]) != 17 or len(geometry["hydraulic_links"]) != 18:
        raise ValueError("current geometry integration remains fixed 17 stations / 18 links")
    nodes = {kind: read(value["surface_node_pin"]) for kind, value in attachments["attachments"].items()}
    sampling = read(geometry["source_sampling_pin"])
    inputs = {"geometry": geometry_pin, "geometry_audit": geometry_audit_pin, "graph": geometry["inputs"]["graph"],
              "mesh_pins": geometry["mesh_pins"], "vdm": geometry["vdm_pin"],
              "surface_attachments": geometry["surface_attachments_pin"],
              "surface_nodes": {kind: value["surface_node_pin"] for kind, value in attachments["attachments"].items()},
              "original_source_sampling": geometry["source_sampling_pin"]}
    code = {name: file_sha(ROOT / name) for name in CURRENT_FILES}
    output.mkdir(parents=True)
    started = time.monotonic()
    index = {"schema": "td-hybrid-current-integration-index-v1", "status": "preparing",
             "inputs": inputs, "code_sha256": code, "code_source_context": "current",
             "hydraulic_ready": False, "publishable": False, "stages_completed": []}

    def persist(name, record):
        return save(output / (name + ".json"), seal(record), output / (name + ".json"))

    try:
        progress("current: original main Boolean stage")
        stage, artifacts = build_boolean_stage(geometry, vdm, attachments, ports, original, nodes, sampling)
        main_pins = {name: persist(name, record) for name, record in artifacts.items()}
        checkpoint = persist("checkpoint_boolean", {"schema": "td-hybrid-current-boolean-checkpoint-v1",
            "status": "boolean_stage_unverified", "portal_checks_started": False, "composition_stage": stage,
            "inputs": inputs, "artifacts": main_pins, "code_sha256": code, "code_source_context": "current"})
        stage_index = persist("boolean-stage-index", {"schema": "td-hybrid-current-boolean-index-v1",
            "status": "boolean_stage_unverified", "inputs": inputs, "artifacts": main_pins,
            "checkpoint": checkpoint, "code_sha256": code, "code_source_context": "current"})
        index.update(boolean_checkpoint=checkpoint, boolean_index=stage_index)
        index["stages_completed"].append("fresh-main-Boolean-saved")
        progress("current: latest rational portal integration")
        lineage = {"mode": "fresh-original-boolean-then-rational-port", "source_index_pin": stage_index,
                   "checkpoint_pin": checkpoint, "main_boolean_recomputed": True}
        current_meshes = {name: record for name, record in artifacts.items() if name != "surface_prisms"}
        current_meshes["original_cutter"] = original["cutter"]
        composition, collars = resume_composition(stage, vdm, attachments, ports, current_meshes,
            artifacts["surface_prisms"], lineage)
        collar_pins = {name: persist(name, record) for name, record in collars.items()}
        original_pins = {"rock_before": geometry["mesh_pins"]["rock_before"],
                         **{"original_" + name: geometry["mesh_pins"][name] for name in ("cutter", "rock_after", "removed")}}
        composition.update(schema=SCHEMA, policy=POLICY, policy_identity_sha256=POLICY_SHA256,
            main_boolean_recomputed=True, boolean_stage_source_identity_sha256=stage["identity_sha256"],
            checkpoint_boolean_pin=checkpoint, inputs=inputs, code_sha256=code, code_source_context="current",
            mesh_pins={**original_pins, **{name: pin for name, pin in main_pins.items() if name != "surface_prisms"}, **collar_pins},
            surface_prisms_pin=main_pins["surface_prisms"],
            runtime={name: version(name) for name in ("manifold3d", "numpy", "shapely")},
            integration_only_no_new_physical_law=True)
        composition_pin = persist("composition", composition)
        index["composition"] = composition_pin
        index["stages_completed"].append("rational-port-stage-saved")
        progress("current: independent composition cold audit")
        audited = audit_composition(composition_pin)
        audit_pin = persist("composition-audit", audited)
        index["composition_audit"] = audit_pin
        index["stages_completed"].append("composition-independent-audit")
        progress("current: latest actual face generation")
        faces_meshes = {name: read(composition["mesh_pins"]["coupled_cutter" if name == "cutter" else name])
                       for name in ("cutter", "removed", "rock_before", "rock_after")}
        faces_meshes["original_cutter"] = original["cutter"]
        faces = build_faces(geometry, vdm, attachments, ports, faces_meshes, composition, audited,
                            artifacts["surface_prisms"], audit_pin)
        face_policy = {**faces["policy"], "composition": "independently-audited-current-fresh-Boolean-rational-integration"}
        faces.update(schema="td-hybrid-current-faces-v1", policy=face_policy,
                     policy_identity_sha256=identity(face_policy),
                     inputs={"geometry": geometry_pin, "composition": composition_pin, "composition_audit": audit_pin},
                     code_sha256=code, code_source_context="current")
        faces_pin = persist("faces", faces)
        index["faces"] = faces_pin
        progress("current: independent face cold audit")
        face_audit = audit_faces(faces_pin)
        index["faces_audit"] = persist("faces-audit", face_audit)
        index["stages_completed"].append("faces-independent-audit")
        index["status"] = "candidate_integration_verified"
    except Exception as error:
        index.update(status="refused", errors=[type(error).__name__ + ": " + str(error)],
                     failure_kind="generation_or_validation_exception")
    index.update(elapsed_wall_s=time.monotonic() - started, actual_peak_rss_bytes=guard())
    if sum(path.stat().st_size for path in output.iterdir() if path.is_file()) > MAX_BYTES:
        index.update(status="refused", errors=["whole current integration package exceeds 64MiB"])
    persist("index", index)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    result = prepare(arguments.output)
    print(json.dumps({"status": result["status"], "stages_completed": result["stages_completed"],
                      "errors": result.get("errors", [])}))
    return 0 if result["status"] == "candidate_integration_verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
