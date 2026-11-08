"""Read only fixed geometry03 and prepare bounded actual link faces; no solver."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hybrid_geometry import MAX_BYTES, MAX_RSS, HYBRID_RIVER_FACES_POLICY_SHA256 as POLICY_SHA256, build_faces, guard, seal
from terrain_pipeline.hybrid_geometry import identity, load_graph

BASE = ROOT / "verification/natural-river-network"
GEOMETRY = BASE / "hybrid-cave-geometry-20261006-03/geometry.json"
AUDIT = GEOMETRY.parent / "independent-audit-v2.json"
GEOMETRY_SHA = "3ba55abbb06f6f4cd8ac5a65dba2de362df958acf48843adcef2351bd465f593"
AUDIT_SHA = "703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364"
GRAPH_SHA = "279d632e6f471c2629a37d7d6954adbcb734be19278e009eb352c9852593846a"
CODE_FILES = ("terrain_pipeline/hybrid_river_faces.py", "tools/prepare_hybrid_river_faces.py", "tests/test_hybrid_river_faces.py")


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(pin, *, check_identity=True):
    path = Path(pin["path"]).resolve(strict=True)
    if not path.is_relative_to(ROOT) or path.stat().st_size > MAX_BYTES or file_sha(path) != pin["sha256"]:
        raise ValueError("fixed_input_path_bytes_or_SHA_mismatch:" + str(path))
    record = json.loads(path.read_bytes())
    if check_identity:
        unsigned = dict(record)
        expected = unsigned.pop("identity_sha256")
        if identity(unsigned) != expected or pin.get("identity_sha256", expected) != expected:
            raise ValueError("saved_input_identity_mismatch")
    return record


def load_inputs(geometry_pin, audit_pin):
    if geometry_pin["sha256"] != GEOMETRY_SHA or audit_pin["sha256"] != AUDIT_SHA:
        raise ValueError("only_fixed_independently_passed_geometry03_authorized")
    geometry, audit = read(geometry_pin), read(audit_pin, check_identity=False)
    if (geometry["schema"] != "td-hybrid-river-geometry-v1" or geometry["status"] != "candidate"
            or geometry["rejection_reasons"] or audit["schema"] != "td-hybrid-cave-geometry-independent-audit-v1"
            or audit["status"] != "passed" or audit["errors"] or audit["geometry_sha256"] != GEOMETRY_SHA
            or not audit["actual_portal_connections_verified"] or not audit["actual_hydraulic_sections_verified"]
            or audit["graph_identity_sha256"] != geometry["graph_identity_sha256"]
            or audit["mesh_pins"] != geometry["mesh_pins"] or audit["inputs"] != geometry["inputs"]
            or audit["vdm_pin"] != geometry["vdm_pin"]):
        raise ValueError("fixed_geometry_audit_linkage_or_scope_invalid")
    graph_pin = geometry["inputs"]["graph"]
    if graph_pin["sha256"] != GRAPH_SHA:
        raise ValueError("wrong_fixed_actual_typed_graph")
    graph_record = read(graph_pin)
    graph = load_graph(graph_record)
    if graph_record["identity_sha256"] != geometry["graph_identity_sha256"]:
        raise ValueError("typed_graph_geometry_identity_mismatch")
    for pin in geometry["inputs"].values():
        if not Path(pin["path"]).resolve(strict=True).is_relative_to(ROOT) or file_sha(pin["path"]) != pin["sha256"]:
            raise ValueError("original_readonly_input_pin_changed")
    for group in ("code_sha256", "readonly_dependency_code_sha256"):
        for name, sha in geometry[group].items():
            if file_sha(ROOT / name) != sha:
                raise ValueError("frozen_geometry_dependency_changed:" + name)
    ports = {}
    for kind in ("sink", "spring"):
        node = next(node for node in graph.nodes if node.kind == kind)
        ports[kind] = json.loads(node.source_record_json)
        if geometry["portal_bindings"][kind]["port_identity_sha256"] != ports[kind]["identity_sha256"]:
            raise ValueError("actual_canonical_port_binding_mismatch")
    meshes = {name: read(pin) for name, pin in geometry["mesh_pins"].items()}
    vdm, attachments = read(geometry["vdm_pin"]), read(geometry["surface_attachments_pin"])
    return geometry, vdm, attachments, ports, meshes


def save(path, record, final_path):
    payload = json.dumps(record, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_BYTES:
        raise ValueError("whole_face_saved_file_64MiB_budget_exceeded")
    guard()
    path.write_bytes(payload)
    return {"path": str(final_path), "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
        "identity_sha256": record["identity_sha256"]}


def prepare(output, geometry_pin, audit_pin):
    import manifold3d
    from importlib.metadata import version
    if version("manifold3d") != "3.5.4":
        raise ValueError("fixed_Mesh64_manifold3d_3.5.4_required")
    output = Path(output).resolve()
    if output.exists() or output.parent not in (BASE.resolve(), (ROOT / "verification/hybrid-river-network").resolve()):
        raise ValueError("new_bounded_verification_package_required")
    started = time.monotonic()
    geometry, vdm, attachments, ports, meshes = load_inputs(geometry_pin, audit_pin)
    bindings = {"geometry": geometry_pin, "geometry_audit": audit_pin, "graph": geometry["inputs"]["graph"],
        "mesh_pins": geometry["mesh_pins"], "vdm": geometry["vdm_pin"], "surface_attachments": geometry["surface_attachments_pin"]}
    code = {name: file_sha(ROOT / name) for name in CODE_FILES}
    try:
        faces = build_faces(geometry, vdm, attachments, ports, meshes)
        faces.update(inputs=bindings, code_sha256=code,
            runtime={"manifold3d": version("manifold3d"), "manifold3d_binary_sha256": file_sha(manifold3d.__file__), "shapely": version("shapely")})
        seal(faces)
    except (ValueError, MemoryError) as error:
        faces = seal({"schema": "td-hybrid-river-faces-v1", "status": "refused", "rejection_reasons": [str(error)],
            "inputs": bindings, "faces": [], "face_count": 0, "policy_identity_sha256": POLICY_SHA256,
            "code_sha256": code, "unknown_geometry_not_zero_flow": True, "independent_audit_passed": False, "hydraulic_solved": False})
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".actual-link-faces-", dir=output.parent) as temporary:
        staging = Path(temporary) / "package"
        staging.mkdir()
        try:
            face_pin = save(staging / "faces.json", faces, output / "faces.json")
        except ValueError as error:
            faces = seal({"schema": "td-hybrid-river-faces-v1", "status": "refused", "rejection_reasons": [str(error)],
                "inputs": bindings, "faces": [], "face_count": 0, "code_sha256": code, "policy_identity_sha256": POLICY_SHA256,
                "whole_package_budget_refused_no_selected_subset": True, "independent_audit_passed": False, "hydraulic_solved": False})
            face_pin = save(staging / "faces.json", faces, output / "faces.json")
        index = seal({"schema": "td-hybrid-river-faces-preparation-v1", "status": faces["status"],
            "rejection_reasons": faces["rejection_reasons"], "faces": face_pin, "inputs": bindings,
            "geometry_identity_sha256": geometry["identity_sha256"], "graph_identity_sha256": geometry["graph_identity_sha256"],
            "policy_identity_sha256": POLICY_SHA256, "code_sha256": code, "independent_audit_passed": False, "hydraulic_solved": False,
            "resource": {"elapsed_wall_s": time.monotonic() - started, "actual_peak_rss_bytes": guard(),
                "max_rss_bytes": MAX_RSS, "max_file_bytes": MAX_BYTES, "solver_calls": 0, "old_packages_changed": False}})
        save(staging / "index.json", index, output / "index.json")
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
    index = prepare(args.output, {"path": str(args.geometry.resolve(strict=True)), "sha256": args.geometry_sha256},
        {"path": str(args.geometry_audit.resolve(strict=True)), "sha256": args.geometry_audit_sha256})
    print(json.dumps({"status": index["status"], "rejection_reasons": index["rejection_reasons"], "output": str(args.output)}))
    return 0 if index["status"] == "candidate_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
