"""Resume fixed composition02 saved stage without recomputing its main Boolean."""

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hybrid_geometry import HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY as NUMERICAL_POLICY, HYBRID_MESH_PLANE_MECHANISM_2_NUMERICAL_POLICY_SHA256 as NUMERICAL_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY as POLICY, HYBRID_SURFACE_COMPOSITION_MECHANISM_3_POLICY_SHA256 as POLICY_SHA256, HYBRID_SURFACE_COMPOSITION_MECHANISM_3_SCHEMA as SCHEMA, resume_composition
from terrain_pipeline.hybrid_geometry import MAX_BYTES, MAX_RSS, guard, seal
from tools.prepare_hybrid_river_faces import BASE, file_sha, load_inputs, read
from tools.prepare_hybrid_surface_composition import save

SOURCE = BASE / "hybrid-surface-composition-20261006-02/index.json"
SOURCE_SHA = "54f1fe63f8f8ff2b79e5bb7332c97fa76ec77b780abf772ad9245081b45af105"
CODE_FILES = ("terrain_pipeline/hybrid_mesh_plane_v2.py", "terrain_pipeline/hybrid_surface_composition_v3.py",
    "tools/prepare_hybrid_surface_composition_v3.py", "tests/test_hybrid_surface_composition_v3.py")
FROZEN_SOURCE_CODE = {"terrain_pipeline/hybrid_mesh_plane.py": "ebe155432189c443e8bba0e0ef873873eeb7d4e65d46eaa7756c6877977e23f9",
    "terrain_pipeline/hybrid_surface_composition_v2.py": "9ca048b281f6cbf3fa358d84bed4f9a9df97ebfe9e9b2ec2f66129311e0042bd",
    "tools/prepare_hybrid_surface_composition_v2.py": "c7d47d03afbd4c361d95a58c06468e8546a65ebfd7b2a96e19728907bb81509a",
    "tests/test_hybrid_surface_composition_v2.py": "2e41c913fa454d64598664947dc0e9cc40cb3e95763ac30c7bc011f4bdd7c18c"}


def load_stage(index_pin):
    if index_pin["sha256"] != SOURCE_SHA:
        raise ValueError("only_fixed_composition02_saved_stage_authorized")
    index = read(index_pin)
    composition = read(index["composition"])
    checkpoint_pin = composition["checkpoint_boolean_pin"]
    checkpoint = read(checkpoint_pin)
    stage = checkpoint["composition_stage"]
    if (index["schema"] != "td-hybrid-surface-composition-preparation-v2"
            or composition["schema"] != "td-hybrid-surface-composition-v2"
            or checkpoint["schema"] != "td-hybrid-surface-composition-boolean-checkpoint-v2"
            or checkpoint["portal_checks_started"] is not False or checkpoint["status"] != "boolean_stage_unverified"
            or stage["status"] != "boolean_stage_unverified" or stage["rejection_reasons"]
            or index["inputs"] != checkpoint["inputs"] or composition["inputs"] != checkpoint["inputs"]
            or index["code_sha256"] != FROZEN_SOURCE_CODE or checkpoint["code_sha256"] != FROZEN_SOURCE_CODE
            or composition["code_sha256"] != FROZEN_SOURCE_CODE
            or index["readonly_dependency_code_sha256"] != checkpoint["readonly_dependency_code_sha256"]
            or composition["readonly_dependency_code_sha256"] != checkpoint["readonly_dependency_code_sha256"]
            or checkpoint["material"] != stage["material"] or composition["material"] != stage["material"]):
        raise ValueError("saved_Boolean_stage_lineage_or_material_changed")
    for group in ("code_sha256", "readonly_dependency_code_sha256"):
        for name, sha in checkpoint[group].items():
            if file_sha(ROOT / name) != sha:
                raise ValueError("frozen_saved_stage_source_code_changed:" + name)
    inputs = checkpoint["inputs"]
    geometry, vdm, attachments, ports, original_meshes = load_inputs(inputs["geometry"], inputs["geometry_audit"])
    if (stage["geometry_identity_sha256"] != geometry["identity_sha256"]
            or stage["graph_identity_sha256"] != geometry["graph_identity_sha256"]):
        raise ValueError("stage_original_geometry_identity_changed")
    records = {name: read(pin) for name, pin in checkpoint["artifacts"].items()}
    for name, pin in checkpoint["artifacts"].items():
        if index["artifacts"][name] != pin or (name != "surface_prisms" and composition["mesh_pins"][name] != pin):
            raise ValueError("stage_artifact_pin_changed:" + name)
    if composition["surface_prisms_pin"] != checkpoint["artifacts"]["surface_prisms"]:
        raise ValueError("immutable_stage_prism_pin_changed")
    reusable_pins = {name: pin for name, pin in index["artifacts"].items() if name.endswith("_collar")}
    reusable = {name: read(pin) for name, pin in reusable_pins.items()}
    lineage = {"source_index_pin": index_pin, "source_composition_pin": index["composition"], "checkpoint_pin": checkpoint_pin,
        "boolean_artifact_pins": checkpoint["artifacts"], "source_code_sha256": checkpoint["code_sha256"],
        "source_readonly_dependency_code_sha256": checkpoint["readonly_dependency_code_sha256"],
        "source_status": composition["status"], "source_rejection_reasons": composition["rejection_reasons"],
        "main_boolean_recomputed": False}
    meshes = {name: record for name, record in records.items() if name != "surface_prisms"}
    meshes["original_cutter"] = original_meshes["cutter"]
    return stage, inputs, geometry, vdm, attachments, ports, meshes, records["surface_prisms"], lineage, reusable, reusable_pins


def prepare(output, source_pin):
    import manifold3d
    if version("manifold3d") != "3.5.4":
        raise ValueError("fixed_manifold3d_3.5.4_required")
    output = Path(output).resolve()
    if output.exists() or output.parent not in (BASE.resolve(), (ROOT / "verification/hybrid-river-network").resolve()):
        raise ValueError("new_bounded_saved_stage_package_required")
    started = time.monotonic()
    stage, inputs, geometry, vdm, attachments, ports, meshes, prisms, lineage, reusable, inherited_collars = load_stage(source_pin)
    code = {name: file_sha(ROOT / name) for name in CODE_FILES}
    dependencies = {**lineage["source_code_sha256"], **lineage["source_readonly_dependency_code_sha256"]}
    try:
        composition, artifacts = resume_composition(stage, vdm, attachments, ports, meshes, prisms, lineage, reusable)
    except (ValueError, AttributeError, TypeError, OverflowError) as error:
        composition = dict(stage)
        composition.update(schema=SCHEMA, status="refused", rejection_reasons=[type(error).__name__ + ":" + str(error)],
            policy=POLICY, policy_identity_sha256=POLICY_SHA256, numerical_slice_policy=NUMERICAL_POLICY,
            numerical_slice_policy_identity_sha256=NUMERICAL_POLICY_SHA256, stage_lineage=lineage,
            main_boolean_recomputed=False, material_inherited_unchanged=True, portal_connections={})
        artifacts = {}
    with tempfile.TemporaryDirectory(prefix=".surface-composition-v3-", dir=output.parent) as temporary:
        staging = Path(temporary) / "package"
        staging.mkdir()
        new_pins = {name: save(staging / (name + ".json"), record, output / (name + ".json")) for name, record in artifacts.items()}
        original = geometry["mesh_pins"]
        pins = {"rock_before": original["rock_before"], **{"original_" + name: original[name] for name in ("cutter", "rock_after", "removed")},
            **{name: pin for name, pin in lineage["boolean_artifact_pins"].items() if name != "surface_prisms"},
            **inherited_collars, **new_pins}
        composition.update(inputs=inputs, code_sha256=code, readonly_dependency_code_sha256=dependencies,
            mesh_pins=pins, surface_prisms_pin=lineage["boolean_artifact_pins"]["surface_prisms"],
            checkpoint_boolean_pin=lineage["checkpoint_pin"], runtime={"manifold3d": version("manifold3d"),
                "manifold3d_binary_sha256": file_sha(manifold3d.__file__), "shapely": version("shapely"), "numpy": version("numpy")})
        composition_pin = save(staging / "composition.json", seal(composition), output / "composition.json")
        index = seal({"schema": "td-hybrid-surface-composition-preparation-v3", "status": composition["status"],
            "rejection_reasons": composition["rejection_reasons"], "composition": composition_pin,
            "inputs": inputs, "stage_lineage": lineage, "artifacts": {**lineage["boolean_artifact_pins"], **inherited_collars, **new_pins},
            "code_sha256": code, "readonly_dependency_code_sha256": dependencies,
            "policy_identity_sha256": POLICY_SHA256, "numerical_slice_policy": NUMERICAL_POLICY,
            "numerical_slice_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
            "independent_audit_passed": False, "hydraulic_ready": False, "hydraulic_solved": False,
            "resource": {"elapsed_wall_s": time.monotonic() - started, "actual_peak_rss_bytes": guard(),
                "max_rss_bytes": MAX_RSS, "max_file_bytes": MAX_BYTES, "main_boolean_calls": 0, "solver_calls": 0}})
        save(staging / "index.json", index, output / "index.json")
        if sum(path.stat().st_size for path in staging.iterdir()) > MAX_BYTES:
            raise ValueError("whole_resume_package_64MiB_budget_exceeded_no_publication")
        guard()
        staging.rename(output)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-index", type=Path, default=SOURCE)
    parser.add_argument("--source-index-sha256", default=SOURCE_SHA)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.output, {"path": str(args.source_index.resolve(strict=True)), "sha256": args.source_index_sha256})
    print(json.dumps({"status": result["status"], "rejection_reasons": result["rejection_reasons"], "output": str(args.output)}))
    return 0 if result["status"] == "candidate_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
