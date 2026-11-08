"""Prepare one explicit pinned gallery; never run a hydraulic solver."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.hybrid_geometry import BedSampler, MAX_BYTES, POLICY_SHA256, Parameters, build_geometry, hybrid_cave_geometry_guard as guard, seal
from terrain_pipeline.hybrid_geometry import FilePin, identity, load_graph, read_pinned
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline import channel_geometry as source

CODE_FILES = ("terrain_pipeline/hybrid_cave_geometry.py", "tools/prepare_hybrid_cave_geometry.py",
    "tests/test_hybrid_cave_geometry.py")
SURFACE_INDEX_SHA = "d4b2e125b54137de40d4ecfab4cc72f1252afb4f96c82858eafa9298d04e1d68"
SURFACE_AUDIT_SHA = "54e7577d6c3e0c75836003c9092e5e5dc70f6a96872238c4d1eb7f2f216845d5"


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(record):
    return read_pinned(FilePin(record["path"], record["sha256"]))


def checked_identity(record):
    unsigned = dict(record)
    expected = unsigned.pop("identity_sha256")
    if identity(unsigned) != expected:
        raise ValueError("saved content identity mismatch")


def load_inputs(graph_pin):
    record = read_pinned(graph_pin)
    graph = load_graph(record)
    inputs = {key: asdict(pin) for key, pin in graph.inputs}
    for pin in inputs.values():
        if file_sha(pin["path"]) != pin["sha256"]:
            raise ValueError("immutable graph parent pin changed: " + pin["path"])
    if inputs["surface_index"]["sha256"] != SURFACE_INDEX_SHA or inputs["surface_audit"]["sha256"] != SURFACE_AUDIT_SHA:
        raise ValueError("only fixed actual task14 package authorized")
    fine_index, fine_audit = read(inputs["fine_index"]), read(inputs["fine_audit"])
    checked_identity(fine_index)
    if (fine_index["schema"] != "td-shared-channel-fine-preparation-v1" or fine_index["status"] != "candidate_unverified"
            or fine_audit["status"] != "passed" or fine_audit.get("errors")
            or fine_audit["index_sha256"] != inputs["fine_index"]["sha256"]):
        raise ValueError("fine package requires genuine independent passed audit")
    if (fine_index["channel"]["index"]["sha256"] != SURFACE_INDEX_SHA
            or fine_index["channel"]["audit"]["sha256"] != SURFACE_AUDIT_SHA):
        raise ValueError("fine parent is not fixed task14")
    for key in ("manifest", "material", "compact_fans"):
        if fine_index[key]["sha256"] != fine_audit[key + "_sha256"] or inputs["fine_" + key]["sha256"] != fine_index[key]["sha256"]:
            raise ValueError("graph/fine actual artifact audit linkage mismatch")
    surface_index = read(inputs["surface_index"])
    for index in (fine_index, surface_index):
        for name, expected in index["code_sha256"].items():
            if file_sha(ROOT / name) != expected:
                raise ValueError("frozen parent implementation changed: " + name)
    hierarchy_pin = inputs["original_hierarchy"]
    original_hierarchy = surface_index["inputs"]["hierarchy"]
    if any(original_hierarchy[key] != hierarchy_pin[key] for key in ("path", "sha256")):
        raise ValueError("original hierarchy parent pin mismatch")
    hierarchy = load_basin_hierarchy(Path(hierarchy_pin["path"]), expected_sha256=hierarchy_pin["sha256"],
        expected_identity=original_hierarchy["identity_sha256"])
    sections = read(inputs["original_06_sections"])
    protection = read(inputs["original_wet_protection_manifest"])["wet_protection"]
    context = source._i46__context(hierarchy, sections["selected_leaf_ids"], protection)
    fans = read(fine_index["compact_fans"])
    checked_identity(fans)
    return record, BedSampler(context, fans["fans"])


def save(path, record):
    size = 0
    digest = hashlib.sha256()
    with path.open("xb") as stream:
        try:
            for fragment in json.JSONEncoder(sort_keys=True, allow_nan=False, separators=(",", ":")).iterencode(record):
                data = fragment.encode("utf-8")
                size += len(data)
                if size > MAX_BYTES:
                    raise ValueError("whole_geometry_file_budget_exceeded")
                digest.update(data)
                stream.write(data)
            guard()
        except (ValueError, MemoryError):
            stream.close()
            path.unlink()
            raise
    return {"path": str(path), "sha256": digest.hexdigest(), "bytes": size,
        "identity_sha256": record["identity_sha256"]}


def prepare(graph_pin, output, parameters):
    output = Path(output).resolve()
    if output.exists() or not output.is_relative_to(ROOT / "verification"):
        raise ValueError("new verification output directory required")
    partial = output.with_name(output.name + ".partial")
    if partial.exists():
        raise ValueError("existing partial package must not be overwritten")
    started = time.perf_counter()
    graph_record, sampler = load_inputs(graph_pin)
    partial.mkdir(parents=True)
    pins = {}
    try:
        geometry, artifacts = build_geometry(graph_record, sampler, parameters)
        geometry["inputs"]["graph"] = asdict(graph_pin)
        for key in list(artifacts):
            record = artifacts.pop(key)
            pin = save(partial / (key + ".json"), record)
            pin["path"] = str(output / (key + ".json"))
            pins[key] = pin
            del record
        geometry["mesh_pins"] = {key: pins[key] for key in ("rock_before", "cutter", "rock_after", "removed")}
        geometry.update({key + "_pin": pins[key] for key in ("vdm", "source_sampling", "surface_attachments")})
        geometry["code_sha256"] = {name: file_sha(ROOT / name) for name in CODE_FILES}
        geometry["readonly_dependency_code_sha256"] = {
            str(Path(module.__file__).resolve().relative_to(ROOT)).replace("\\", "/"): file_sha(module.__file__)
            for name, module in list(sys.modules.items()) if name.startswith("terrain_pipeline.") and getattr(module, "__file__", None)}
        from importlib.metadata import version
        if version("manifold3d") != "3.5.4":
            raise ValueError("only_pinned_manifold3d_3.5.4_authorized")
        import manifold3d
        geometry["runtime"] = {"manifold3d": version("manifold3d"), "manifold3d_binary_sha256": file_sha(manifold3d.__file__),
            "numpy": version("numpy"), "python": sys.version}
        geometry["resource"] = {"elapsed_s": time.perf_counter() - started, "top_grid_count": sampler_grid_count(pins, partial),
            "hard_grid_count": 300000, "hard_rss_bytes": 1024**3, "hard_file_bytes": MAX_BYTES,
            "actual_peak_rss_bytes": guard(), "solver_calls": 0}
        seal(geometry)
        geometry_pin = save(partial / "geometry.json", geometry)
        geometry_pin["path"] = str(output / "geometry.json")
        index = {"schema": "td-hybrid-cave-geometry-preparation-v1", "status": "candidate", "rejection_reasons": [],
            "geometry": geometry_pin, "artifacts": pins, "graph": asdict(graph_pin),
            "graph_identity_sha256": graph_record["identity_sha256"], "policy_identity_sha256": POLICY_SHA256,
            "code_sha256": geometry["code_sha256"], "independent_audit_passed": False, "hydraulic_solved": False}
    except (ValueError, MemoryError) as error:
        index = {"schema": "td-hybrid-cave-geometry-preparation-v1", "status": "refused", "rejection_reasons": [str(error)],
            "graph": asdict(graph_pin), "graph_identity_sha256": graph_record["identity_sha256"],
            "policy_identity_sha256": POLICY_SHA256, "parameters": asdict(parameters),
            "code_sha256": {name: file_sha(ROOT / name) for name in CODE_FILES},
            "partial_artifacts_not_accepted": pins, "independent_audit_passed": False, "hydraulic_solved": False}
    seal(index)
    save(partial / "index.json", index)
    partial.rename(output)
    return index


def sampler_grid_count(pins, partial):
    record = json.loads((partial / "source_sampling.json").read_bytes())
    return record["top_vertex_count"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--graph-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    for name, default in asdict(Parameters()).items():
        parser.add_argument("--" + name.replace("_", "-"), type=int if name == "stations" else float, default=default)
    args = parser.parse_args()
    parameters = Parameters(**{name: getattr(args, name) for name in asdict(Parameters())})
    index = prepare(FilePin(str(args.graph.resolve(strict=True)), args.graph_sha256), args.output, parameters)
    print(json.dumps({"status": index["status"], "rejection_reasons": index["rejection_reasons"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if index["status"] == "candidate" else 2


if __name__ == "__main__":
    raise SystemExit(main())
