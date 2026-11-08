"""Save Boolean/material stage, then independently retain every portal result; no solver."""

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hybrid_geometry import NUMERICAL_POLICY, NUMERICAL_POLICY_SHA256
from terrain_pipeline.hybrid_geometry import MAX_BYTES, HYBRID_SURFACE_COMPOSITION_MECHANISM_2_POLICY_SHA256 as POLICY_SHA256, HYBRID_SURFACE_COMPOSITION_MECHANISM_2_SCHEMA as SCHEMA, hybrid_surface_composition_mechanism_2_build_composition as build_composition
from terrain_pipeline.hybrid_geometry import MAX_RSS, guard, seal
from tools.prepare_hybrid_river_faces import AUDIT, AUDIT_SHA, BASE, GEOMETRY, GEOMETRY_SHA, file_sha, load_inputs, read
from tools.prepare_hybrid_surface_composition import save

CODE_FILES = ("terrain_pipeline/hybrid_mesh_plane.py", "terrain_pipeline/hybrid_surface_composition_v2.py",
    "tools/prepare_hybrid_surface_composition_v2.py", "tests/test_hybrid_surface_composition_v2.py")
FROZEN_V1_CODE = {"terrain_pipeline/hybrid_surface_composition.py": "0a9b424ca1994d150c8bf6c3cb90c2ce8c263cd5ca78cace24134242b02c5dd3",
    "tools/prepare_hybrid_surface_composition.py": "93e50dec6ac93cbda8396fb2b344fd40204a1c72942c944a17e0ecd698bafff8",
    "tests/test_hybrid_surface_composition.py": "5df84c0c6c5cfb17b83c1f25cfc3819ee7c221c9b850d5d62dfbcaf443bc0ae7"}
DEPENDENCIES = ("terrain_pipeline/hybrid_cave_geometry.py", "terrain_pipeline/hybrid_river_faces.py",
    "terrain_pipeline/hybrid_river_graph.py", "tools/prepare_hybrid_river_faces.py")


def refused_from_stage(staging, output, error):
    checkpoint_path = Path(staging) / "checkpoint_boolean.json"
    if checkpoint_path.exists():
        checkpoint = json.loads(checkpoint_path.read_bytes())
        record = dict(checkpoint["composition_stage"])
        record["checkpoint_boolean_pin"] = {"path": str(Path(output) / "checkpoint_boolean.json"),
            "sha256": file_sha(checkpoint_path), "bytes": checkpoint_path.stat().st_size,
            "identity_sha256": checkpoint["identity_sha256"]}
    else:
        record = {"schema": SCHEMA, "policy_identity_sha256": POLICY_SHA256,
            "numerical_slice_policy": NUMERICAL_POLICY,
            "numerical_slice_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
            "independent_audit_passed": False, "hydraulic_ready": False, "hydraulic_solved": False}
    record.update(status="refused", rejection_reasons=[type(error).__name__ + ":" + str(error)],
        boolean_stage_preserved=checkpoint_path.exists(),
        portal_connections={kind: {"status": "not_verified", "rejection_reasons": ["preparation_exception"],
            "two_sided_complete_port_verified": False} for kind in ("sink", "spring")},
        preparation_exception={"type": type(error).__name__, "message": str(error)})
    return seal(record)


def prepare(output, geometry_pin, audit_pin):
    import manifold3d
    if version("manifold3d") != "3.5.4":
        raise ValueError("fixed_manifold3d_3.5.4_required")
    output = Path(output).resolve()
    if output.exists() or output.parent not in (BASE.resolve(), (ROOT / "verification/hybrid-river-network").resolve()):
        raise ValueError("new_bounded_surface_composition_package_required")
    for name, expected in FROZEN_V1_CODE.items():
        if file_sha(ROOT / name) != expected:
            raise ValueError("frozen_v1_changed:" + name)
    started = time.monotonic()
    geometry, vdm, attachments, ports, meshes = load_inputs(geometry_pin, audit_pin)
    node_pins = {kind: value["surface_node_pin"] for kind, value in attachments["attachments"].items()}
    nodes = {kind: read(pin) for kind, pin in node_pins.items()}
    sampling = read(geometry["source_sampling_pin"])
    inputs = {"geometry": geometry_pin, "geometry_audit": audit_pin, "graph": geometry["inputs"]["graph"],
        "mesh_pins": geometry["mesh_pins"], "vdm": geometry["vdm_pin"], "surface_attachments": geometry["surface_attachments_pin"],
        "surface_nodes": node_pins, "original_source_sampling": geometry["source_sampling_pin"]}
    code = {name: file_sha(ROOT / name) for name in CODE_FILES}
    dependencies = {**geometry["code_sha256"], **geometry["readonly_dependency_code_sha256"], **FROZEN_V1_CODE,
        **{name: file_sha(ROOT / name) for name in DEPENDENCIES}}
    runtime = {"manifold3d": version("manifold3d"), "manifold3d_binary_sha256": file_sha(manifold3d.__file__),
        "shapely": version("shapely"), "numpy": version("numpy")}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".surface-composition-v2-", dir=output.parent) as temporary:
        staging = Path(temporary) / "package"
        staging.mkdir()
        stage_pins = {}

        def persist_stage(record, artifacts):
            for name, artifact in artifacts.items():
                stage_pins[name] = save(staging / (name + ".json"), artifact, output / (name + ".json"))
            checkpoint = seal({"schema": "td-hybrid-surface-composition-boolean-checkpoint-v2",
                "status": "boolean_stage_unverified", "composition_stage": record, "artifacts": dict(stage_pins),
                "inputs": inputs, "code_sha256": code, "readonly_dependency_code_sha256": dependencies,
                "runtime": runtime, "material": record["material"], "portal_checks_started": False,
                "numerical_slice_policy": NUMERICAL_POLICY,
                "numerical_slice_policy_identity_sha256": NUMERICAL_POLICY_SHA256})
            pin = save(staging / "checkpoint_boolean.json", checkpoint, output / "checkpoint_boolean.json")
            if sum(path.stat().st_size for path in staging.iterdir()) > MAX_BYTES:
                raise ValueError("whole_stage_package_64MiB_budget_exceeded")
            return pin

        try:
            composition, artifacts = build_composition(geometry, vdm, attachments, ports, meshes, nodes, sampling, persist_stage)
        except (ValueError, AttributeError, TypeError, OverflowError) as error:
            composition = refused_from_stage(staging, output, error)
            artifacts = {}
        pins = dict(stage_pins)
        for name, artifact in artifacts.items():
            if name not in pins:
                try:
                    pins[name] = save(staging / (name + ".json"), artifact, output / (name + ".json"))
                except (AttributeError, TypeError, OverflowError) as error:
                    composition = refused_from_stage(staging, output, error)
                    break

        def bind(record):
            record.update(inputs=inputs, code_sha256=code, readonly_dependency_code_sha256=dependencies, runtime=runtime,
                mesh_pins={"rock_before": geometry["mesh_pins"]["rock_before"],
                **{"original_" + name: geometry["mesh_pins"][name] for name in ("cutter", "rock_after", "removed")},
                **{name: pin for name, pin in pins.items() if name != "surface_prisms"}})
            if "surface_prisms" in pins:
                record["surface_prisms_pin"] = pins["surface_prisms"]
            return seal(record)

        try:
            composition = bind(composition)
            composition_pin = save(staging / "composition.json", composition, output / "composition.json")
        except (AttributeError, TypeError, OverflowError) as error:
            composition = bind(refused_from_stage(staging, output, error))
            composition_pin = save(staging / "composition.json", composition, output / "composition.json")
        index = seal({"schema": "td-hybrid-surface-composition-preparation-v2", "status": composition["status"],
            "rejection_reasons": composition["rejection_reasons"], "composition": composition_pin, "artifacts": pins,
            "inputs": inputs, "code_sha256": code, "readonly_dependency_code_sha256": dependencies,
            "policy_identity_sha256": POLICY_SHA256, "numerical_slice_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
            "numerical_slice_policy": NUMERICAL_POLICY,
            "independent_audit_passed": False, "hydraulic_ready": False, "hydraulic_solved": False,
            "resource": {"elapsed_wall_s": time.monotonic() - started, "actual_peak_rss_bytes": guard(),
                "max_rss_bytes": MAX_RSS, "max_file_bytes": MAX_BYTES, "solver_calls": 0, "old_packages_changed": False}})
        save(staging / "index.json", index, output / "index.json")
        if sum(path.stat().st_size for path in staging.iterdir()) > MAX_BYTES:
            raise ValueError("whole_composition_package_64MiB_budget_exceeded_no_publication")
        guard()
        staging.rename(output)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, default=GEOMETRY)
    parser.add_argument("--geometry-sha256", default=GEOMETRY_SHA)
    parser.add_argument("--geometry-audit", type=Path, default=AUDIT)
    parser.add_argument("--geometry-audit-sha256", default=AUDIT_SHA)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.output, {"path": str(args.geometry.resolve(strict=True)), "sha256": args.geometry_sha256},
        {"path": str(args.geometry_audit.resolve(strict=True)), "sha256": args.geometry_audit_sha256})
    print(json.dumps({"status": result["status"], "rejection_reasons": result["rejection_reasons"], "output": str(args.output)}))
    return 0 if result["status"] == "candidate_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
