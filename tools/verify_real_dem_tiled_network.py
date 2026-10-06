"""Strict D8 tiled traversal comparison, not a streamed or dynamic solver.

Cold verification may reconstruct static evidence, but never modifies sources,
publishes files, or advances dynamic state. Height and network state are global
ndarrays; the actual candidate dimensions, not a hypothetical 1024 grid, apply.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
import tempfile
from time import perf_counter
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.dem_domain import load_dem_candidate
from terrain_pipeline.real_dem_surface_network import RealDemNetwork, build_real_dem_network
from tools import verify_real_dem_outlet_classification as stage_a_exporter
from tools.verify_real_dem_outlet_classification import (
    DEFAULT_AUDIT, DEFAULT_CANDIDATE, DEFAULT_VECTORS, canonical_bytes,
    check_unchanged, checked_hash, confined_file, file_sha256, read_json,
    reject_natural_claims, source_record, value_hash,
)

DEFAULT_STAGE_A = ROOT / "verification/real-dem-outlet-classification/run-20261001T151020146526Z"
DEFAULT_OUTPUT_ROOT = ROOT / "verification/real-dem-tiled-network"
ALGORITHM = "real-dem-tiled-network-export-v1"
ARRAY_NAMES = ("receiver", "order", "accumulation_cells", "boundary_outlet",
               "unknown_adjacent_terminal")
CONFIG = {"tile_sizes": [256, 512, 128], "tile_orders": ["row_major", "reversed"],
          "connectivity": 8, "stored_tile_size": 256, "stored_tile_order": "row_major"}


def load_inputs(candidate_path, stage_a_path, vectors_path, audit_path):
    classification = stage_a_exporter.verify_package(
        stage_a_path, candidate_path=candidate_path, vectors_path=vectors_path,
        audit_path=audit_path, match_distance_m=180.0)
    inputs = {name: source_record(path) for name, path in
              (("candidate", candidate_path), ("vectors", vectors_path), ("audit", audit_path))}
    stage_a = Path(stage_a_path).resolve(strict=True)
    inputs["stage_a_manifest"] = source_record(confined_file(stage_a, "manifest.json"))
    manifest = read_json(inputs["stage_a_manifest"]["path"])
    reject_natural_claims(manifest)
    if (manifest["inputs"] != {name: inputs[name] for name in ("candidate", "vectors", "audit")}
            or manifest["source_unchanged"] is not True
            or manifest["algorithm_sha256"] != value_hash(manifest["algorithm"])
            or manifest["config_sha256"] != value_hash(manifest["config"])):
        raise ValueError("stage A input/configuration binding mismatch")
    for name in ("classification.json", "terminal-layer.geojson", "evidence-levels.json"):
        record = source_record(confined_file(stage_a, name))
        declaration = manifest["artifacts"][name]
        if (declaration["path"] != name or record["sha256"] != checked_hash(declaration["sha256"])
                or record["bytes"] != declaration["bytes"]):
            raise ValueError(f"stage A artifact hash mismatch: {name}")
        inputs["stage_a_" + name] = record
    audit = read_json(inputs["audit"]["path"])
    vectors = read_json(inputs["vectors"]["path"])
    reject_natural_claims(audit)
    reject_natural_claims(vectors)
    sources = []
    for declaration in audit["sources"]:
        record = source_record(declaration["path"])
        if (record["sha256"] != checked_hash(declaration["sha256_before"])
                or record["sha256"] != checked_hash(declaration["sha256_after"])
                or declaration["unchanged"] is not True or record["bytes"] != declaration["bytes"]):
            raise ValueError("audit source mismatch")
        sources.append(record)
    paths = [record["path"] for record in sources]
    archives = [record for record in sources
                if Path(record["path"]).name == "HydroRIVERS_v10_as_shp.zip"]
    if (len(set(paths)) != len(paths) or len(archives) != 1
            or archives[0]["sha256"] != checked_hash(vectors["source_archive_sha256"])):
        raise ValueError("audit/vectors archive binding mismatch")
    candidate = load_dem_candidate(inputs["candidate"]["path"], verify_source=True)
    declaration = candidate["manifest"]["identity"]["source"]
    dem_source = source_record(declaration["path"])
    if dem_source["sha256"] != checked_hash(declaration["sha256"]):
        raise ValueError("candidate source mismatch")
    sources.append(dem_source)
    if sources != manifest["source_files"]:
        raise ValueError("stage A source bindings mismatch")
    for name in ("classification.json", "terminal-layer.geojson", "evidence-levels.json"):
        if manifest["artifacts"][name]["source_files"] != [inputs[key] for key in
                ("candidate", "vectors", "audit")] + sources:
            raise ValueError("stage A artifact source bindings mismatch")
    if canonical_bytes(classification) != canonical_bytes(read_json(inputs["stage_a_classification.json"]["path"])):
        raise ValueError("stage A classification changed after full verification")
    reject_natural_claims(classification)
    check_unchanged(list(inputs.values()) + sources)
    return candidate, classification, inputs, sources


def network_arrays(network):
    return {name: getattr(network, name) for name in ARRAY_NAMES}


def array_records(arrays):
    return {name: {"dtype": array.dtype.str, "shape": list(array.shape),
                   "nbytes": array.nbytes,
                   "sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest()}
            for name, array in arrays.items()}


def compare_network(network, reference):
    for name, expected in network_arrays(reference).items():
        actual = getattr(network, name)
        if (not isinstance(actual, np.ndarray) or actual.dtype != expected.dtype
                or actual.shape != expected.shape or not np.array_equal(actual, expected)):
            raise ValueError(f"network reference mismatch: {name}")


def classification_check(candidate, classification, network):
    valid = candidate["arrays"]["valid_mask"]
    cells = np.flatnonzero(valid.ravel() & (network.receiver.ravel() < 0))
    records = classification["outlets"]
    if (len(records) != len(cells) or any(type(item["cell_id"]) is not int for item in records)
            or sorted(item["cell_id"] for item in records) != cells.tolist()):
        raise ValueError("stage A terminal coverage/cell IDs mismatch")
    counts = dict.fromkeys(("unknown_adjacent", "boundary_clip", "internal_sink"), 0)
    contribution = 0
    for item in records:
        cell_id = item["cell_id"]
        unknown = bool(network.unknown_adjacent_terminal.ravel()[cell_id])
        boundary = bool(network.boundary_outlet.ravel()[cell_id])
        primary = "unknown_adjacent" if unknown else "boundary_clip" if boundary else "internal_sink"
        amount = int(network.accumulation_cells.ravel()[cell_id])
        if (item["classification"] != primary or type(item["contributing_cells"]) is not int
                or item["contributing_cells"] != amount
                or item["is_unknown_adjacent"] is not unknown
                or item["is_boundary_clip"] is not boundary
                or item["natural_outlet_verified"] is not False
                or item["row_col"] != list(divmod(cell_id, valid.shape[1]))):
            raise ValueError("stage A terminal classification/contribution mismatch")
        counts[primary] += 1
        contribution += amount
    summary = classification["summary"]
    if (summary["classification_counts"] != counts or summary["contributing_cells"] != contribution
            or summary["terminal_cells"] != len(cells) or contribution != int(valid.sum())):
        raise ValueError("stage A summary mismatch")
    return {"terminal_cells": len(cells), "classification_counts": counts,
            "contributing_cells": contribution,
            "unknown_adjacent_terminals": int(network.unknown_adjacent_terminal.sum()),
            "boundary_terminals": int(network.boundary_outlet.sum()),
            "unknown_and_boundary_count": int(np.count_nonzero(
                network.unknown_adjacent_terminal & network.boundary_outlet)),
            "natural_outlet_verified": False}


def tile_statistics(network, tile_size):
    rows, cols = network.receiver.shape
    source_ids = np.flatnonzero(network.receiver.ravel() >= 0)
    target_ids = network.receiver.ravel()[source_ids]
    cross = ((source_ids // cols // tile_size != target_ids // cols // tile_size)
             | (source_ids % cols // tile_size != target_ids % cols // tile_size))
    tile_rows = math.ceil(rows / tile_size)
    tile_cols = math.ceil(cols / tile_size)
    full_tiles = (rows // tile_size) * (cols // tile_size)
    return {"tile_count": tile_rows * tile_cols,
            "partial_tiles": tile_rows * tile_cols - full_tiles,
            "cross_tile_edges": int(cross.sum())}


def compute(candidate, classification):
    module = importlib.import_module("terrain_pipeline.real_dem_tiled_network")
    arrays = candidate["arrays"]
    started = perf_counter()
    reference = build_real_dem_network(arrays["height_m"], arrays["valid_mask"], connectivity=8)
    reference_runtime = perf_counter() - started
    evidence = classification_check(candidate, classification, reference)
    comparisons = []
    stored = None
    for tile_size in CONFIG["tile_sizes"]:
        for tile_order in CONFIG["tile_orders"]:
            started = perf_counter()
            network = module.build_tiled_network(candidate, tile_size=tile_size, tile_order=tile_order)
            validation = module.validate_tiled_network(candidate, network, tile_size=tile_size)
            runtime = perf_counter() - started
            compare_network(network, reference)
            classification_check(candidate, classification, network)
            comparisons.append({"tile_size": tile_size, "tile_order": tile_order,
                                "runtime_seconds": runtime, "exact_reference_equal": True,
                                "validation": validation,
                                **tile_statistics(network, tile_size)})
            if tile_size == 256 and tile_order == "row_major":
                stored = network
    output_arrays = network_arrays(stored)
    report = {"schema_version": 1, "algorithm": ALGORITHM,
              "shape_zx": list(arrays["height_m"].shape),
              "reference_runtime_seconds": reference_runtime, "comparisons": comparisons,
              "stage_a_consistency": evidence,
              "unknown_cells": int((~arrays["valid_mask"]).sum()),
              "output_nbytes": sum(array.nbytes for array in output_arrays.values()),
              "precision": {name: array.dtype.str for name, array in output_arrays.items()},
              "height_unchanged": True, "source_unchanged": True,
              "notes": ["Global network state and height ndarray/mask retained in memory.",
                        "Tiled traversal is not a streamed solver or bounded-memory solver.",
                        "Actual candidate shape only; no 1024 real DEM claim.",
                        "Strict downhill D8 reference; no height modification or dynamic advancement.",
                        "Unknown cells are barriers, not ocean; all terminals remain classified."]}
    algorithm = {"version": ALGORITHM, "export_code_sha256": file_sha256(__file__),
                 "tiled_code_sha256": file_sha256(module.__file__),
                 "reference_code_sha256": file_sha256(sys.modules[build_real_dem_network.__module__].__file__)}
    return report, output_arrays, algorithm


def deterministic_report(report):
    copied = json.loads(canonical_bytes(report))
    runtime = copied.pop("reference_runtime_seconds")
    if isinstance(runtime, bool) or not isinstance(runtime, (int, float)) or not math.isfinite(runtime) or runtime < 0:
        raise ValueError("invalid reference runtime")
    for comparison in copied["comparisons"]:
        runtime = comparison.pop("runtime_seconds")
        if isinstance(runtime, bool) or not isinstance(runtime, (int, float)) or not math.isfinite(runtime) or runtime < 0:
            raise ValueError("invalid tile runtime")
    return copied


def make_manifest(directory, report, arrays, algorithm, inputs, sources):
    return {"schema_version": 1, "algorithm": algorithm,
            "algorithm_sha256": value_hash(algorithm), "config": CONFIG,
            "config_sha256": value_hash(CONFIG), "inputs": inputs, "source_files": sources,
            "source_unchanged": True, "arrays": array_records(arrays),
            "deterministic_report_sha256": value_hash(deterministic_report(report)),
            "artifacts": {name: {"path": name, "sha256": file_sha256(directory / name),
                                  "bytes": (directory / name).stat().st_size,
                                  "source_files": list(inputs.values()) + sources}
                          for name in ("report.json", "network.npz")}}


def read_network(path, expected):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if (len(members) != len(ARRAY_NAMES) or {item.filename for item in members}
                != {name + ".npy" for name in ARRAY_NAMES}):
            raise ValueError("unexpected network archive members")
        for member in members:
            name = member.filename[:-4]
            if member.file_size > expected[name].nbytes + 4096:
                raise ValueError("network member exceeds reference size")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name].copy() for name in ARRAY_NAMES}
    network = RealDemNetwork(**arrays)
    compare_network(network, RealDemNetwork(**expected))
    return arrays


def validate_output_root(output_root, paths):
    workspace = ROOT.resolve()
    verification = (workspace / "verification").resolve()
    if (not verification.is_relative_to(workspace) or not output_root.is_relative_to(verification)
            or output_root == verification):
        raise ValueError("output-root must be strictly inside workspace/verification")
    if any(Path(path).resolve().is_relative_to(output_root) for path in paths):
        raise ValueError("output-root contains input or source files")


def export_package(*, candidate_path=DEFAULT_CANDIDATE, stage_a_path=DEFAULT_STAGE_A,
                   vectors_path=DEFAULT_VECTORS, audit_path=DEFAULT_AUDIT,
                   output_root=DEFAULT_OUTPUT_ROOT):
    output_root = Path(output_root).resolve()
    validate_output_root(output_root, (candidate_path, vectors_path, audit_path,
                                      Path(stage_a_path) / "manifest.json"))
    candidate, classification, inputs, sources = load_inputs(candidate_path, stage_a_path, vectors_path, audit_path)
    validate_output_root(output_root, [record["path"] for record in list(inputs.values()) + sources])
    height_hash = hashlib.sha256(candidate["arrays"]["height_m"].tobytes()).hexdigest()
    report, arrays, algorithm = compute(candidate, classification)
    if hashlib.sha256(candidate["arrays"]["height_m"].tobytes()).hexdigest() != height_hash:
        raise ValueError("candidate height changed")
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=output_root) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        (staging / "report.json").write_bytes(canonical_bytes(report))
        np.savez_compressed(staging / "network.npz", **arrays)
        read_network(staging / "network.npz", arrays)
        manifest = make_manifest(staging, report, arrays, algorithm, inputs, sources)
        (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
        check_unchanged(list(inputs.values()) + sources)
        if destination.exists():
            raise FileExistsError(destination)
        staging.rename(destination)
    return destination, report


def verify_package(directory, *, candidate_path=DEFAULT_CANDIDATE, stage_a_path=DEFAULT_STAGE_A,
                   vectors_path=DEFAULT_VECTORS, audit_path=DEFAULT_AUDIT):
    directory = Path(directory).resolve(strict=True)
    if {path.name for path in directory.iterdir()} != {"manifest.json", "report.json", "network.npz"}:
        raise ValueError("unexpected bundle files")
    for name in ("manifest.json", "report.json", "network.npz"):
        confined_file(directory, name)
    manifest = read_json(directory / "manifest.json")
    report = read_json(directory / "report.json")
    reject_natural_claims(manifest)
    reject_natural_claims(report)
    candidate, classification, inputs, sources = load_inputs(candidate_path, stage_a_path, vectors_path, audit_path)
    rebuilt_report, arrays, algorithm = compute(candidate, classification)
    if canonical_bytes(deterministic_report(report)) != canonical_bytes(deterministic_report(rebuilt_report)):
        raise ValueError("report statistics/reference replay mismatch")
    read_network(directory / "network.npz", arrays)
    expected = make_manifest(directory, report, arrays, algorithm, inputs, sources)
    if canonical_bytes(manifest) != canonical_bytes(expected):
        raise ValueError("manifest source, artifact, array or algorithm binding mismatch")
    check_unchanged(list(inputs.values()) + sources)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--stage-a-package", type=Path, default=DEFAULT_STAGE_A)
    parser.add_argument("--vectors", type=Path, default=DEFAULT_VECTORS)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--verify-package", type=Path)
    args = parser.parse_args(argv)
    options = {"candidate_path": args.candidate, "stage_a_path": args.stage_a_package,
               "vectors_path": args.vectors, "audit_path": args.audit}
    try:
        if args.verify_package is None:
            output, report = export_package(output_root=args.output_root, **options)
        else:
            output = args.verify_package.resolve()
            report = verify_package(output, **options)
        print(json.dumps({"output": str(output), "shape_zx": report["shape_zx"],
                          "classification": report["stage_a_consistency"],
                          "output_nbytes": report["output_nbytes"], "source_unchanged": True,
                          "verified": args.verify_package is not None}, separators=(",", ":")))
    except (ValueError, OSError, KeyError, TypeError, ImportError, zipfile.BadZipFile) as error:
        parser.exit(1, f"tiled network verification failed: {error}\n")


if __name__ == "__main__":
    main()
