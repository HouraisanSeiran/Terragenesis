"""Flat routing evidence export with full frozen A/B proofs, not lake certification.

Global height, mask, component and graph ndarrays remain resident. Cold replay
does not publish files, modify sources, or advance dynamic state. Raw A terminal
records are provenance only, never the resolved terminal contribution table.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import shutil
from pathlib import Path
import sys
import tempfile
from time import perf_counter
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.real_dem_surface_network import RealDemNetwork
from tools import verify_real_dem_tiled_network as stage_b
from tools.verify_real_dem_outlet_classification import (
    DEFAULT_AUDIT, DEFAULT_CANDIDATE, DEFAULT_VECTORS, canonical_bytes,
    check_unchanged, confined_file, file_sha256, read_json, reject_natural_claims,
    source_record, value_hash,
)

DEFAULT_STAGE_A = stage_b.DEFAULT_STAGE_A
DEFAULT_STAGE_B = ROOT / "verification/real-dem-tiled-network/run-20261001T153332885702Z"
DEFAULT_OUTPUT_ROOT = ROOT / "verification/real-dem-flat-routing"
ALGORITHM = "real-dem-flat-routing-export-v1"
ARRAY_NAMES = stage_b.ARRAY_NAMES + ("component_id", "distance_to_exit")
CONFIG = {"comparisons": [{"tile_size": 256, "tile_order": "row_major"},
                          {"tile_size": 512, "tile_order": "reversed"}],
          "stored_tile_size": 256, "stored_tile_order": "row_major"}
MAX_REPORT_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


def load_inputs(candidate_path, stage_a_path, stage_b_path, vectors_path, audit_path):
    options = {"candidate_path": candidate_path, "stage_a_path": stage_a_path,
               "vectors_path": vectors_path, "audit_path": audit_path}
    directory = Path(stage_b_path).resolve(strict=True)
    before = {"stage_b_" + name: source_record(confined_file(directory, name))
              for name in ("manifest.json", "report.json", "network.npz")}
    stage_b.verify_package(directory, **options)
    candidate, raw_classification, inputs, sources = stage_b.load_inputs(
        candidate_path, stage_a_path, vectors_path, audit_path)
    inputs.update(before)
    check_unchanged(list(inputs.values()) + sources)
    return candidate, raw_classification, inputs, sources


def result_arrays(result):
    return {**stage_b.network_arrays(result["network"]),
            "component_id": result["component_id"], "distance_to_exit": result["distance_to_exit"]}


def terminal_risks(candidate, result):
    network = result["network"]
    valid = candidate["arrays"]["valid_mask"]
    component = result["component_id"].ravel()
    records = {record["component_id"]: record for record in result["components"]}
    terminals = np.flatnonzero(valid.ravel() & (network.receiver.ravel() == -1))
    counts = dict.fromkeys(("unknown_adjacent", "boundary_clip", "internal_retention"), 0)
    risks = []
    for cell_id in terminals:
        record = records[int(component[cell_id])]
        if record["root_cell_id"] != int(cell_id):
            raise ValueError("resolved terminal must be closed component root")
        unknown = record["touches_unknown"]
        boundary = record["touches_boundary"]
        if type(unknown) is not bool or type(boundary) is not bool:
            raise ValueError("component risk must be boolean")
        primary = "unknown_adjacent" if unknown else "boundary_clip" if boundary else "internal_retention"
        counts[primary] += 1
        risks.append({"cell_id": int(cell_id), "component_id": int(component[cell_id]),
                      "classification": primary, "component_touches_unknown": unknown,
                      "component_touches_boundary": boundary,
                      "contributing_cells": int(network.accumulation_cells.ravel()[cell_id]),
                      "natural_outlet_verified": False, "ocean_outlet_certified": False})
    contribution = sum(record["contributing_cells"] for record in risks)
    if contribution != int(valid.sum()):
        raise ValueError("resolved terminal contribution coverage mismatch")
    return {"terminals": risks, "classification_counts": counts,
            "contributing_cells_sum": contribution,
            "unknown_and_boundary_count": sum(record["component_touches_unknown"] and
                                              record["component_touches_boundary"] for record in risks)}


def compute(candidate):
    module = importlib.import_module("terrain_pipeline.real_dem_flat_routing")
    before = stage_b.array_records(candidate["arrays"])
    comparisons = []
    stored = None
    for config in CONFIG["comparisons"]:
        started = perf_counter()
        result = module.resolve_dem_flats(candidate, **config)
        validation = module.validate_flat_routing(candidate, result)
        runtime = perf_counter() - started
        arrays = result_arrays(result)
        if stored is None:
            stored = result
        else:
            for name, expected in result_arrays(stored).items():
                actual = arrays[name]
                if actual.dtype != expected.dtype or actual.shape != expected.shape or not np.array_equal(actual, expected):
                    raise ValueError(f"flat configurations differ: {name}")
            for name in ("components", "summary"):
                if canonical_bytes(result[name]) != canonical_bytes(stored[name]):
                    raise ValueError(f"flat configurations differ: {name}")
        comparisons.append({**config, "runtime_seconds": runtime, "exact_equal": True,
                            "validation": validation})
    if stage_b.array_records(candidate["arrays"]) != before:
        raise ValueError("candidate arrays changed")
    arrays = result_arrays(stored)
    risk = terminal_risks(candidate, stored)
    report = {"schema_version": 1, "algorithm": ALGORITHM,
              "shape_zx": list(candidate["arrays"]["height_m"].shape),
              "components": stored["components"], "summary": stored["summary"],
              "risk": risk, "terminals": risk["terminals"],
              "terminal_classification_counts": risk["classification_counts"],
              "comparisons": comparisons,
              "output_nbytes": sum(array.nbytes for array in arrays.values()),
              "source_unchanged": True, "natural_outlet_verified": False,
              "ocean_outlet_certified": False,
              "notes": ["Global ndarray height/mask/component/graph state; not streamed solver.",
                        "Raw Stage A classification is provenance, not flat terminal counts or contributions.",
                        "Closed component risk covers every member, not only root neighbors.",
                        "Original height retained; no filling, lake/ocean certification or dynamic advancement."]}
    reject_natural_claims(report)
    algorithm = {"version": ALGORITHM, "export_code_sha256": file_sha256(__file__),
                 "flat_algorithm": module.ALGORITHM, "flat_code_sha256": file_sha256(module.__file__),
                 "stage_b_export_code_sha256": file_sha256(stage_b.__file__),
                 "tiled_code_sha256": file_sha256(importlib.import_module("terrain_pipeline.real_dem_tiled_network").__file__)}
    return report, arrays, algorithm


def deterministic_report(report):
    value = json.loads(canonical_bytes(report))
    for comparison in value["comparisons"]:
        runtime = comparison.pop("runtime_seconds")
        if type(runtime) not in (int, float) or not np.isfinite(runtime) or runtime < 0:
            raise ValueError("invalid runtime")
    return value


def read_result(path, expected_arrays, report):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != len(ARRAY_NAMES) or {item.filename for item in members} != {name + ".npy" for name in ARRAY_NAMES}:
            raise ValueError("unexpected flat archive members")
        for member in members:
            if member.file_size > expected_arrays[member.filename[:-4]].nbytes + 4096:
                raise ValueError("flat archive member exceeds expected size")
        if sum(member.file_size for member in members) > sum(array.nbytes for array in expected_arrays.values()) + 4096 * len(ARRAY_NAMES):
            raise ValueError("flat archive exceeds total array budget")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name].copy() for name in ARRAY_NAMES}
    for name, expected in expected_arrays.items():
        actual = arrays[name]
        if actual.dtype != expected.dtype or actual.shape != expected.shape:
            raise ValueError(f"invalid flat array dtype/shape: {name}")
    return {"network": RealDemNetwork(**{name: arrays[name] for name in stage_b.ARRAY_NAMES}),
            "component_id": arrays["component_id"], "distance_to_exit": arrays["distance_to_exit"],
            "components": report["components"], "summary": report["summary"]}


def make_manifest(directory, report, arrays, algorithm, inputs, sources):
    return {"schema_version": 1, "algorithm": algorithm, "algorithm_sha256": value_hash(algorithm),
            "config": CONFIG, "config_sha256": value_hash(CONFIG), "inputs": inputs,
            "source_files": sources, "source_unchanged": True,
            "arrays": stage_b.array_records(arrays),
            "deterministic_report_sha256": value_hash(deterministic_report(report)),
            "artifacts": {name: {"path": name, "sha256": file_sha256(directory / name),
                                  "bytes": (directory / name).stat().st_size,
                                  "source_files": list(inputs.values()) + sources}
                          for name in ("report.json", "network.npz")}}


def validate_output_root(output, paths):
    workspace = ROOT.resolve()
    verification = (workspace / "verification").resolve()
    if (not verification.is_relative_to(workspace) or not output.is_relative_to(verification)
            or output == verification or any(Path(path).resolve().is_relative_to(output) for path in paths)):
        raise ValueError("unsafe output-root; require verification child separate from inputs/sources")


def export_package(*, stage_b_path=DEFAULT_STAGE_B, candidate_path=DEFAULT_CANDIDATE, stage_a_path=DEFAULT_STAGE_A,
                   vectors_path=DEFAULT_VECTORS, audit_path=DEFAULT_AUDIT, output_root=DEFAULT_OUTPUT_ROOT):
    output = Path(output_root).resolve()
    validate_output_root(output, (candidate_path, vectors_path, audit_path,
                                 Path(stage_a_path) / "manifest.json", Path(stage_b_path) / "manifest.json"))
    candidate, raw_classification, inputs, sources = load_inputs(
        candidate_path, stage_a_path, stage_b_path, vectors_path, audit_path)
    validate_output_root(output, [record["path"] for record in list(inputs.values()) + sources])
    report, arrays, algorithm = compute(candidate)
    payload = canonical_bytes(report)
    if len(payload) > MAX_REPORT_BYTES:
        raise ValueError("flat report exceeds byte budget")
    output.mkdir(parents=True, exist_ok=True)
    required_bytes = len(payload) + sum(array.nbytes for array in arrays.values()) + MAX_MANIFEST_BYTES
    if shutil.disk_usage(output).free < required_bytes:
        raise ValueError("insufficient output disk space")
    destination = output / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=output) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        (staging / "report.json").write_bytes(payload)
        np.savez_compressed(staging / "network.npz", **arrays)
        result = read_result(staging / "network.npz", arrays, report)
        importlib.import_module("terrain_pipeline.real_dem_flat_routing").validate_flat_routing(candidate, result)
        manifest = make_manifest(staging, report, arrays, algorithm, inputs, sources)
        (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
        check_unchanged(list(inputs.values()) + sources)
        if destination.exists():
            raise FileExistsError(destination)
        staging.rename(destination)
    return destination, report


def verify_package(directory, *, stage_b_path=DEFAULT_STAGE_B, candidate_path=DEFAULT_CANDIDATE,
                   stage_a_path=DEFAULT_STAGE_A, vectors_path=DEFAULT_VECTORS, audit_path=DEFAULT_AUDIT):
    directory = Path(directory).resolve(strict=True)
    if {path.name for path in directory.iterdir()} != {"manifest.json", "report.json", "network.npz"}:
        raise ValueError("unexpected flat bundle files")
    for name in ("manifest.json", "report.json", "network.npz"):
        confined_file(directory, name)
    if ((directory / "report.json").stat().st_size > MAX_REPORT_BYTES
            or (directory / "manifest.json").stat().st_size > MAX_MANIFEST_BYTES):
        raise ValueError("flat JSON exceeds byte budget")
    report = read_json(directory / "report.json")
    manifest = read_json(directory / "manifest.json")
    reject_natural_claims(report)
    reject_natural_claims(manifest)
    candidate, raw_classification, inputs, sources = load_inputs(
        candidate_path, stage_a_path, stage_b_path, vectors_path, audit_path)
    rebuilt_report, expected_arrays, algorithm = compute(candidate)
    result = read_result(directory / "network.npz", expected_arrays, report)
    importlib.import_module("terrain_pipeline.real_dem_flat_routing").validate_flat_routing(candidate, result)
    for name, actual in result_arrays(result).items():
        if not np.array_equal(actual, expected_arrays[name]):
            raise ValueError(f"flat array deterministic replay mismatch: {name}")
    if canonical_bytes(deterministic_report(report)) != canonical_bytes(deterministic_report(rebuilt_report)):
        raise ValueError("flat report deterministic replay mismatch")
    expected = make_manifest(directory, report, expected_arrays, algorithm, inputs, sources)
    if canonical_bytes(manifest) != canonical_bytes(expected):
        raise ValueError("flat manifest source/algorithm/artifact binding mismatch")
    check_unchanged(list(inputs.values()) + sources)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--stage-a-package", type=Path, default=DEFAULT_STAGE_A)
    parser.add_argument("--stage-b-package", type=Path, default=DEFAULT_STAGE_B)
    parser.add_argument("--vectors", type=Path, default=DEFAULT_VECTORS)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--verify-package", type=Path)
    args = parser.parse_args(argv)
    options = {"candidate_path": args.candidate, "stage_a_path": args.stage_a_package,
               "stage_b_path": args.stage_b_package, "vectors_path": args.vectors, "audit_path": args.audit}
    try:
        if args.verify_package is None:
            output, report = export_package(output_root=args.output_root, **options)
        else:
            output = args.verify_package.resolve()
            report = verify_package(output, **options)
        print(json.dumps({"output": str(output), "summary": report["summary"],
                          "risk_counts": report["risk"]["classification_counts"],
                          "source_unchanged": True, "verified": args.verify_package is not None},
                         separators=(",", ":")))
    except (ValueError, OSError, KeyError, TypeError, ImportError, zipfile.BadZipFile) as error:
        parser.exit(1, f"flat routing verification failed: {error}\n")


if __name__ == "__main__":
    main()
