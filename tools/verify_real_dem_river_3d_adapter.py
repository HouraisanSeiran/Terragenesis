"""Gated illustrative shared-bank geometry; never a publishable water body."""

import argparse
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline import real_dem_river_3d_adapter as geometry
from terrain_pipeline.dem_domain import load_dem_candidate
from terrain_pipeline.real_dem_surface_network import RealDemNetwork
from tools import export_real_dem_review as review_exporter
from tools import verify_real_dem_rainfall_routing as rainfall_exporter
from tools.verify_real_dem_outlet_classification import (
    DEFAULT_CANDIDATE, canonical_bytes, check_unchanged, confined_file,
    file_sha256, read_json, reject_natural_claims, source_record, value_hash,
)

DEFAULT_FLAT = rainfall_exporter.DEFAULT_FLAT
DEFAULT_RAINFALL = ROOT / "verification/real-dem-rainfall-routing/run-20261001T155846516349Z"
DEFAULT_OUTPUT_ROOT = ROOT / "verification/real-dem-river-3d-adapter"
ALGORITHM = "real-dem-river-3d-adapter-export-v1"
CONFIG = {"min_contributing_cells": 100., "width_m": 20., "depth_m": 1., "tile_sizes": [256, 512]}
JSON_KEYS = {"metadata", "array_hashes", "metadata_sha256", "content_sha256"}
MAX_JSON_BYTES = 4 * 1024 * 1024


def load_inputs(review_path, rainfall_path):
    review = Path(review_path).resolve(strict=True)
    rainfall = Path(rainfall_path).resolve(strict=True)
    before = [source_record(confined_file(review, name)) for name in
              ("manifest.json", "static-layers.json", "zero_dry.json", "uniform.json", "pulse.json")]
    before += [source_record(confined_file(rainfall, name)) for name in
               ("manifest.json", "report.json", "zero_dry.npz", "uniform.npz", "pulse.npz")]
    manifest = review_exporter.verify_package(review, rainfall)
    records = manifest["inputs"] + before
    unique = {}
    for record in records:
        actual = source_record(record["path"])
        if actual != record or (record["path"] in unique and unique[record["path"]] != record):
            raise ValueError("D proof source hash mismatch")
        unique[record["path"]] = record
    candidate = load_dem_candidate(DEFAULT_CANDIDATE, verify_source=True)
    flat_report = read_json(confined_file(DEFAULT_FLAT, "report.json"))
    flat_archive = confined_file(DEFAULT_FLAT, "network.npz")
    required = [DEFAULT_CANDIDATE, DEFAULT_FLAT / "manifest.json", DEFAULT_FLAT / "report.json", flat_archive]
    for path in required:
        record = source_record(path)
        if unique.get(record["path"]) != record:
            raise ValueError("fixed candidate/flat not bound by D proof")
    with np.load(flat_archive, allow_pickle=False) as archive:
        flat_arrays = {name: archive[name].copy() for name in rainfall_exporter.flat_exporter.ARRAY_NAMES}
    flat = {"network": RealDemNetwork(**{name: flat_arrays[name] for name in
                                        rainfall_exporter.flat_exporter.stage_b.ARRAY_NAMES}),
            "component_id": flat_arrays["component_id"], "distance_to_exit": flat_arrays["distance_to_exit"],
            "components": flat_report["components"], "summary": flat_report["summary"]}
    check_unchanged(list(unique.values()))
    return candidate, flat, list(unique.values())


def identity():
    return {"version": ALGORITHM, "export_code_sha256": file_sha256(__file__),
            "geometry_algorithm": geometry.ALGORITHM, "geometry_code_sha256": file_sha256(geometry.__file__),
            "review_export_code_sha256": file_sha256(review_exporter.__file__),
            "rainfall_export_code_sha256": file_sha256(rainfall_exporter.__file__),
            "flat_code_sha256": file_sha256(importlib.import_module("terrain_pipeline.real_dem_flat_routing").__file__)}


def arrays_record(result):
    return rainfall_exporter.flat_exporter.stage_b.array_records({name: result[name] for name in geometry.ARRAY_NAMES})


def validate_fixed(candidate, flat, result):
    if canonical_bytes(result["metadata"]["parameters"]) != canonical_bytes({name: CONFIG[name] for name in
            ("min_contributing_cells", "width_m", "depth_m")}):
        raise ValueError("geometry fixed engineering parameters mismatch")
    reject_natural_claims(result["metadata"])
    if result["metadata"]["publishable"] is not False:
        raise ValueError("geometry must remain nonpublishable")
    return geometry.validate_river_geometry(candidate, flat, result)


def build(candidate, flat):
    first = None
    for tile_size in CONFIG["tile_sizes"]:
        result = geometry.build_river_geometry(candidate, flat, min_contributing_cells=100.,
                                               width_m=20., depth_m=1., tile_size=tile_size)
        validate_fixed(candidate, flat, result)
        if first is None:
            first = result
        else:
            for name in geometry.ARRAY_NAMES:
                if (result[name].dtype != first[name].dtype or result[name].shape != first[name].shape
                        or not np.array_equal(result[name], first[name])):
                    raise ValueError(f"tile geometry differs: {name}")
            if result["array_hashes"] != first["array_hashes"] or result["content_sha256"] != first["content_sha256"]:
                raise ValueError("tile geometry hashes differ")
    return first


def topology_report(candidate, result):
    ids = result["node_ids"]
    edges = result["edges"]
    cols = candidate["arrays"]["height_m"].shape[1]
    if np.unique(ids).size != len(ids) or np.unique(result["edge_ids"]).size != len(edges):
        raise ValueError("duplicate global node/edge ID")
    seams = []
    for size in CONFIG["tile_sizes"]:
        cross = ((edges[:, 0] // cols // size != edges[:, 1] // cols // size)
                 | (edges[:, 0] % cols // size != edges[:, 1] % cols // size))
        shared = np.unique(edges[cross])
        seams.append({"tile_size": size, "cross_tile_edges": int(cross.sum()),
                      "shared_global_node_count": len(shared), "global_nodes_unique": True,
                      "two_shared_bank_vertices_per_node": True})
    return {"schema_version": 1, "algorithm": ALGORITHM, "config": CONFIG,
            "shape_zx": list(candidate["arrays"]["height_m"].shape),
            "node_count": len(ids), "edge_count": len(edges),
            "head_count": int(result["heads"].sum()), "junction_count": int(result["junctions"].sum()),
            "terminal_count": int(result["terminals"].sum()),
            "degenerate_face_count": len(result["degenerate_face_ids"]),
            "mesh_accepted": result["metadata"]["mesh_accepted"], "seams": seams,
            "tile_comparison_exact": True, "retained_array_nbytes": sum(result[name].nbytes for name in geometry.ARRAY_NAMES),
            "memory_scope": "retained geometry only, not peak total RAM", "publishable": False,
            "natural_outlet_verified": False, "ocean_outlet_certified": False,
            "notes": ["Global shared bank indices; illustrative width 20m/depth 1m, not observed channel.",
                      "No continuous water surface, hydraulic readiness, Minecraft or frontend integration.",
                      "Unknown/component risks retained; no natural certification."]}


def obj_name(result):
    return "mesh.obj" if result["metadata"]["mesh_accepted"] else "diagnostic-mesh.obj"


def obj_lines(result):
    yield "# Illustrative engineering ribbon; publishable=false; not a water body\n"
    if not result["metadata"]["mesh_accepted"]:
        yield "# DIAGNOSTIC ONLY: degenerate faces; mesh rejected\n"
    for vertex in result["vertices"]:
        yield "v " + " ".join(format(float(value), ".17g") for value in vertex) + "\n"
    for face in result["faces"]:
        yield "f " + " ".join(str(int(value) + 1) for value in face) + "\n"


def read_geometry(directory, candidate):
    record = read_json(confined_file(directory, "geometry.json"))
    if set(record) != JSON_KEYS:
        raise ValueError("invalid geometry JSON schema")
    path = confined_file(directory, "geometry.npz")
    valid_cells = int(candidate["arrays"]["valid_mask"].sum())
    budget = min(geometry.MAX_BYTES, valid_cells * 300 + len(geometry.ARRAY_NAMES) * 4096)
    if path.stat().st_size > budget:
        raise ValueError("geometry compressed budget exceeded")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if (len(members) != len(geometry.ARRAY_NAMES) or {item.filename for item in members}
                != {name + ".npy" for name in geometry.ARRAY_NAMES}
                or sum(item.file_size for item in members) > budget):
            raise ValueError("geometry archive members/decompressed budget mismatch")
        node_count = int(np.count_nonzero(candidate["arrays"]["valid_mask"]))
        limits = {name: node_count * 8 for name in geometry.ARRAY_NAMES}
        for name in ("node_xyz", "cross_sections", "edges"):
            limits[name] = node_count * 24
        limits["vertices"] = limits["faces"] = node_count * 48
        for member in members:
            if member.file_size > limits[member.filename[:-4]] + 4096:
                raise ValueError("geometry member byte budget exceeded")
    with np.load(path, allow_pickle=False) as archive:
        result = {name: archive[name].copy() for name in geometry.ARRAY_NAMES}
    return {**result, **record}


def make_manifest(directory, result, report, inputs):
    algorithm = identity()
    names = ("geometry.npz", "geometry.json", "report.json", obj_name(result))
    return {"schema_version": 1, "algorithm": algorithm, "algorithm_sha256": value_hash(algorithm),
            "config": CONFIG, "config_sha256": value_hash(CONFIG), "inputs": inputs,
            "arrays": arrays_record(result), "source_unchanged": True, "publishable": False,
            "artifacts": {name: {"path": name, "sha256": file_sha256(directory / name),
                                  "bytes": (directory / name).stat().st_size} for name in names}}


def check_output(output, inputs):
    workspace = ROOT.resolve()
    verification = (workspace / "verification").resolve()
    allowed = (verification / "real-dem-river-3d-adapter").resolve()
    if (not verification.is_relative_to(workspace) or not allowed.is_relative_to(verification)
            or output != allowed or any(Path(item["path"]).resolve().is_relative_to(output) for item in inputs)):
        raise ValueError("unsafe geometry output-root")


def export_package(review_path, rainfall_path, *, output_root=DEFAULT_OUTPUT_ROOT):
    output = Path(output_root).resolve()
    check_output(output, [])
    candidate, flat, inputs = load_inputs(review_path, rainfall_path)
    check_output(output, inputs)
    result = build(candidate, flat)
    report = topology_report(candidate, result)
    output.mkdir(parents=True, exist_ok=True)
    destination = output / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=output) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        np.savez_compressed(staging / "geometry.npz", **{name: result[name] for name in geometry.ARRAY_NAMES})
        (staging / "geometry.json").write_bytes(canonical_bytes({name: result[name] for name in JSON_KEYS}))
        (staging / "report.json").write_bytes(canonical_bytes(report))
        with (staging / obj_name(result)).open("w", encoding="ascii", newline="\n") as stream:
            stream.writelines(obj_lines(result))
        validate_fixed(candidate, flat, read_geometry(staging, candidate))
        (staging / "manifest.json").write_bytes(canonical_bytes(make_manifest(staging, result, report, inputs)))
        check_unchanged(inputs)
        if destination.exists():
            raise FileExistsError(destination)
        staging.rename(destination)
    return destination, report


def verify_package(directory, review_path, rainfall_path):
    directory = Path(directory).resolve(strict=True)
    candidate, flat, inputs = load_inputs(review_path, rainfall_path)
    for name in ("manifest.json", "geometry.json", "report.json"):
        if confined_file(directory, name).stat().st_size > MAX_JSON_BYTES:
            raise ValueError("geometry JSON budget exceeded")
    result = read_geometry(directory, candidate)
    validate_fixed(candidate, flat, result)
    names = {"manifest.json", "geometry.json", "geometry.npz", "report.json", obj_name(result)}
    if {item.name for item in directory.iterdir()} != names:
        raise ValueError("unexpected geometry package files")
    mesh = confined_file(directory, obj_name(result))
    with mesh.open("r", encoding="ascii", newline="") as stream:
        for expected in obj_lines(result):
            if stream.readline() != expected:
                raise ValueError("OBJ global bank/face replay mismatch")
        if stream.read(1):
            raise ValueError("extra OBJ content")
    report = topology_report(candidate, result)
    if canonical_bytes(read_json(directory / "report.json")) != canonical_bytes(report):
        raise ValueError("geometry topology/seam/risk report mismatch")
    manifest = read_json(directory / "manifest.json")
    reject_natural_claims(manifest)
    if canonical_bytes(manifest) != canonical_bytes(make_manifest(directory, result, report, inputs)):
        raise ValueError("geometry manifest code/source/hash binding mismatch")
    check_unchanged(inputs)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-package", required=True, type=Path)
    parser.add_argument("--rainfall-package", required=True, type=Path, default=DEFAULT_RAINFALL,
                        help=f"explicit C gate; fixed formal package: {DEFAULT_RAINFALL}")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--verify-package", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.verify_package is None:
            output, report = export_package(args.review_package, args.rainfall_package, output_root=args.output_root)
        else:
            output = args.verify_package.resolve()
            report = verify_package(output, args.review_package, args.rainfall_package)
        print(json.dumps({"output": str(output), "nodes": report["node_count"], "edges": report["edge_count"],
                          "degenerate_faces": report["degenerate_face_count"], "mesh_accepted": report["mesh_accepted"],
                          "publishable": False, "source_unchanged": True}, separators=(",", ":")))
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as error:
        parser.exit(1, f"river 3D adapter failed: {error}\n")


if __name__ == "__main__":
    main()
