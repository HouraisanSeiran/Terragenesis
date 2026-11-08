"""Prepare a new cut-only half-arm/cave composition; never run hydraulics."""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hybrid_geometry import MAX_BYTES, HYBRID_SURFACE_COMPOSITION_POLICY_SHA256 as POLICY_SHA256, build_composition
from terrain_pipeline.hybrid_geometry import MAX_RSS, guard, seal
from tools.prepare_hybrid_river_faces import AUDIT, AUDIT_SHA, BASE, GEOMETRY, GEOMETRY_SHA, file_sha, load_inputs, read

CODE_FILES = ("terrain_pipeline/hybrid_surface_composition.py", "tools/prepare_hybrid_surface_composition.py",
    "tests/test_hybrid_surface_composition.py")
DEPENDENCIES = ("terrain_pipeline/hybrid_cave_geometry.py", "terrain_pipeline/hybrid_river_faces.py",
    "terrain_pipeline/hybrid_river_graph.py", "tools/prepare_hybrid_river_faces.py")


def save(path, record, final_path):
    payload = json.dumps(record, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise ValueError("whole_surface_composition_file_64MiB_budget_exceeded")
    guard()
    path.write_bytes(payload)
    return {"path": str(final_path), "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
        "identity_sha256": record["identity_sha256"]}


def prepare(output, geometry_pin, audit_pin):
    import manifold3d
    if version("manifold3d") != "3.5.4":
        raise ValueError("fixed_manifold3d_3.5.4_required")
    output = Path(output).resolve()
    if output.exists() or output.parent not in (BASE.resolve(), (ROOT / "verification/hybrid-river-network").resolve()):
        raise ValueError("new_bounded_surface_composition_package_required")
    started = time.monotonic()
    geometry, vdm, attachments, ports, meshes = load_inputs(geometry_pin, audit_pin)
    node_pins = {kind: value["surface_node_pin"] for kind, value in attachments["attachments"].items()}
    nodes = {kind: read(pin) for kind, pin in node_pins.items()}
    sampling = read(geometry["source_sampling_pin"])
    inputs = {"geometry": geometry_pin, "geometry_audit": audit_pin, "graph": geometry["inputs"]["graph"],
        "mesh_pins": geometry["mesh_pins"], "vdm": geometry["vdm_pin"],
        "surface_attachments": geometry["surface_attachments_pin"], "surface_nodes": node_pins,
        "original_source_sampling": geometry["source_sampling_pin"]}
    code = {name: file_sha(ROOT / name) for name in CODE_FILES}
    dependencies = {**geometry["code_sha256"], **geometry["readonly_dependency_code_sha256"],
        **{name: file_sha(ROOT / name) for name in DEPENDENCIES}}
    try:
        composition, artifacts = build_composition(geometry, vdm, attachments, ports, meshes, nodes, sampling)
    except (ValueError, MemoryError) as error:
        composition = seal({"schema": "td-hybrid-surface-composition-v1", "status": "refused",
            "rejection_reasons": [str(error)], "policy_identity_sha256": POLICY_SHA256,
            "independent_audit_passed": False, "hydraulic_ready": False, "hydraulic_solved": False})
        artifacts = {}
    composition.update(inputs=inputs, code_sha256=code, readonly_dependency_code_sha256=dependencies,
        runtime={"manifold3d": version("manifold3d"), "manifold3d_binary_sha256": file_sha(manifold3d.__file__),
            "shapely": version("shapely"), "numpy": version("numpy")})
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".surface-composition-", dir=output.parent) as temporary:
        staging = Path(temporary) / "package"
        staging.mkdir()
        pins = {name: save(staging / (name + ".json"), record, output / (name + ".json"))
            for name, record in artifacts.items()}
        composition["mesh_pins"] = {"rock_before": geometry["mesh_pins"]["rock_before"],
            **{"original_" + name: geometry["mesh_pins"][name] for name in ("cutter", "rock_after", "removed")},
            **{name: pin for name, pin in pins.items() if name != "surface_prisms"}}
        if "surface_prisms" in pins:
            composition["surface_prisms_pin"] = pins["surface_prisms"]
        seal(composition)
        composition_pin = save(staging / "composition.json", composition, output / "composition.json")
        index = seal({"schema": "td-hybrid-surface-composition-preparation-v1", "status": composition["status"],
            "rejection_reasons": composition["rejection_reasons"], "composition": composition_pin,
            "artifacts": pins, "inputs": inputs, "code_sha256": code, "readonly_dependency_code_sha256": dependencies,
            "policy_identity_sha256": POLICY_SHA256, "independent_audit_passed": False, "hydraulic_ready": False,
            "hydraulic_solved": False, "resource": {"elapsed_wall_s": time.monotonic() - started,
                "actual_peak_rss_bytes": guard(), "max_rss_bytes": MAX_RSS, "max_file_bytes": MAX_BYTES,
                "solver_calls": 0, "old_packages_changed": False}})
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
