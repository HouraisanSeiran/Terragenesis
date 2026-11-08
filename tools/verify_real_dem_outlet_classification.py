"""Atomic stage A export and repeatable, read-only cold verification.

Validation may reconstruct static routing evidence, but never writes inputs or
sources, advances dynamic state, or publishes files during package verification.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_source import file_sha256, load_dem_candidate

DEFAULT_CANDIDATE = ROOT / "verification/dem-domain/run-20261001T135530750135Z/dem-candidate.npz"
DEFAULT_VECTORS = ROOT / "verification/hydrovector-evidence/run-20260930T060422593821Z/selected_vectors.json"
DEFAULT_AUDIT = DEFAULT_VECTORS.with_name("report.json")
DEFAULT_OUTPUT_ROOT = ROOT / "verification/real-dem-outlet-classification"
PRODUCTS = ("classification.json", "terminal-layer.geojson", "evidence-levels.json")
EXPORT_ALGORITHM = "real-dem-outlet-classification-export-v1"


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def value_hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def unique_pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON key: {name}")
        result[name] = value
    return result


def reject_constant(value):
    raise ValueError(f"nonfinite JSON value: {value}")


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        reject_constant(value)
    return number


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=unique_pairs, parse_constant=reject_constant,
                      parse_float=finite_float)


def reject_natural_claims(value):
    if isinstance(value, dict):
        for name, item in value.items():
            lowered = name.lower()
            guarded = ("natural" in lowered or "certif" in lowered
                       or lowered in {"independent_coastline", "independent_centerline",
                                      "dem_nodata_is_ocean", "real_basin_passed"})
            if guarded and item is True:
                raise ValueError(f"unsupported natural certification: {name}")
            reject_natural_claims(item)
    elif isinstance(value, list):
        for item in value:
            reject_natural_claims(item)


def checked_hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("invalid SHA256")
    return value


def source_record(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"not a source file: {path}")
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": file_sha256(path)}


def load_bound_inputs(candidate_path, vectors_path, audit_path):
    inputs = {name: source_record(path) for name, path in
              (("candidate", candidate_path), ("vectors", vectors_path), ("audit", audit_path))}
    vectors = read_json(inputs["vectors"]["path"])
    audit = read_json(inputs["audit"]["path"])
    reject_natural_claims(vectors)
    reject_natural_claims(audit)
    sources = []
    paths = set()
    for declaration in audit["sources"]:
        record = source_record(declaration["path"])
        if record["path"] in paths:
            raise ValueError("duplicate audit source path")
        paths.add(record["path"])
        before = checked_hash(declaration["sha256_before"])
        after = checked_hash(declaration["sha256_after"])
        if (record["sha256"] != before or before != after
                or declaration["unchanged"] is not True
                or record["bytes"] != declaration["bytes"]):
            raise ValueError(f"audit source mismatch: {record['path']}")
        sources.append(record)
    archives = [record for record in sources
                if Path(record["path"]).name == "HydroRIVERS_v10_as_shp.zip"]
    if (len(archives) != 1 or archives[0]["sha256"] !=
            checked_hash(vectors["source_archive_sha256"])):
        raise ValueError("vectors/archive binding mismatch")
    offline = load_dem_candidate(inputs["candidate"]["path"], verify_source=False)
    declaration = offline["manifest"]["identity"]["source"]
    dem_source = source_record(declaration["path"])
    if dem_source["sha256"] != checked_hash(declaration["sha256"]):
        raise ValueError("candidate/source binding mismatch")
    sources.append(dem_source)
    candidate = load_dem_candidate(inputs["candidate"]["path"], verify_source=True)
    reject_natural_claims(candidate["manifest"])
    check_unchanged(list(inputs.values()) + sources)
    return candidate, vectors, audit, inputs, sources


def check_unchanged(records):
    for record in records:
        if source_record(record["path"]) != record:
            raise ValueError(f"source changed during operation: {record['path']}")


def evidence_levels():
    return {
        "schema_version": 1,
        "status": "diagnostic_only_not_natural_outlet_certification",
        "dem": {"level": "surface_proxy", "fine_bed_verified": False,
                "nodata_is_ocean": False},
        "hydrorivers": {"level": "same_source_cross_reference",
                        "independent_measurement": False,
                        "next_down_zero_is_ocean": False},
        "hydrobasins": {"level": "coarse_bbox_context_only",
                        "independent_measurement": False,
                        "coast_flag_certifies_outlet": False},
        "gaps": ["independent_coastline", "independent_natural_outlet_evidence",
                 "bathymetry", "synchronous_measured_discharge"],
        "natural_mouth_verified": False,
        "ocean_outlet_certified": False,
    }


def compute_products(candidate, vectors, audit, match_distance_m):
    if (isinstance(match_distance_m, bool) or not math.isfinite(match_distance_m)
            or match_distance_m <= 0):
        raise ValueError("match-distance-m must be finite and positive")
    module = importlib.import_module("terrain_pipeline.real_dem_outlet_classification")
    report = module.build_outlet_classification(
        candidate, vectors, audit, match_distance_m=match_distance_m)
    module.validate_outlet_classification(report, candidate, vectors, audit)
    products = dict(zip(PRODUCTS, (report, module.classification_geojson(report), evidence_levels())))
    for product in products.values():
        canonical_bytes(product)
        reject_natural_claims(product)
    algorithm = {"export": EXPORT_ALGORITHM,
                 "export_code_sha256": file_sha256(__file__),
                 "classifier_code_sha256": file_sha256(module.__file__)}
    return products, algorithm


def package_manifest(products, algorithm, config, inputs, sources):
    return {"schema_version": 1, "algorithm": algorithm,
            "algorithm_sha256": value_hash(algorithm),
            "config": config, "config_sha256": value_hash(config),
            "inputs": inputs, "source_files": sources, "source_unchanged": True,
            "artifacts": {name: {"path": name,
                                  "sha256": hashlib.sha256(canonical_bytes(product)).hexdigest(),
                                  "bytes": len(canonical_bytes(product)),
                                  "source_files": list(inputs.values()) + sources}
                          for name, product in products.items()}}


def confined_file(directory, name):
    path = directory / name
    if path.is_symlink() or path.resolve().parent != directory.resolve() or not path.is_file():
        raise ValueError(f"unsafe package file: {name}")
    return path


def verify_package(directory, *, candidate_path=DEFAULT_CANDIDATE,
                   vectors_path=DEFAULT_VECTORS, audit_path=DEFAULT_AUDIT,
                   match_distance_m=180.0):
    """Replay a fixed bundle without publishing files or advancing dynamic state."""
    directory = Path(directory).resolve(strict=True)
    if {path.name for path in directory.iterdir()} != set(PRODUCTS) | {"manifest.json"}:
        raise ValueError("unexpected package files")
    manifest = read_json(confined_file(directory, "manifest.json"))
    reject_natural_claims(manifest)
    candidate, vectors, audit, inputs, sources = load_bound_inputs(candidate_path, vectors_path, audit_path)
    products, algorithm = compute_products(candidate, vectors, audit, match_distance_m)
    expected = package_manifest(products, algorithm, {"match_distance_m": match_distance_m}, inputs, sources)
    if canonical_bytes(manifest) != canonical_bytes(expected):
        raise ValueError("manifest binding, algorithm, configuration or hash mismatch")
    for name, product in products.items():
        path = confined_file(directory, name)
        if file_sha256(path) != checked_hash(expected["artifacts"][name]["sha256"]):
            raise ValueError(f"artifact hash mismatch: {name}")
        loaded = read_json(path)
        reject_natural_claims(loaded)
        if canonical_bytes(loaded) != canonical_bytes(product):
            raise ValueError(f"artifact replay mismatch: {name}")
    check_unchanged(list(inputs.values()) + sources)
    return products["classification.json"]


def validate_output_root(output_root, protected_paths):
    workspace = ROOT.resolve()
    verification = (workspace / "verification").resolve()
    if (not verification.is_relative_to(workspace)
            or not output_root.is_relative_to(verification)
            or output_root == verification):
        raise ValueError("output-root must be strictly inside workspace/verification")
    for path in protected_paths:
        source = Path(path).resolve()
        if source.is_relative_to(output_root):
            raise ValueError(f"output-root contains an input or source file: {source}")


def export_package(*, candidate_path=DEFAULT_CANDIDATE, vectors_path=DEFAULT_VECTORS,
                   audit_path=DEFAULT_AUDIT, output_root=DEFAULT_OUTPUT_ROOT,
                   match_distance_m=180.0):
    output_root = Path(output_root).resolve()
    validate_output_root(output_root, (candidate_path, vectors_path, audit_path))
    candidate, vectors, audit, inputs, sources = load_bound_inputs(candidate_path, vectors_path, audit_path)
    validate_output_root(output_root, [record["path"] for record in list(inputs.values()) + sources])
    products, algorithm = compute_products(candidate, vectors, audit, match_distance_m)
    manifest = package_manifest(products, algorithm, {"match_distance_m": match_distance_m}, inputs, sources)
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=output_root) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        for name, product in {**products, "manifest.json": manifest}.items():
            (staging / name).write_bytes(canonical_bytes(product))
        for name in PRODUCTS:
            if file_sha256(staging / name) != manifest["artifacts"][name]["sha256"]:
                raise ValueError("staged artifact hash mismatch")
        check_unchanged(list(inputs.values()) + sources)
        if output.exists():
            raise FileExistsError(output)
        staging.rename(output)
    return output, products["classification.json"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--vectors", type=Path, default=DEFAULT_VECTORS)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--match-distance-m", type=float, default=180.0)
    parser.add_argument("--verify-package", type=Path)
    args = parser.parse_args(argv)
    options = {"candidate_path": args.candidate, "vectors_path": args.vectors,
               "audit_path": args.audit, "match_distance_m": args.match_distance_m}
    try:
        if args.verify_package is not None:
            output = args.verify_package.resolve()
            report = verify_package(output, **options)
        else:
            output, report = export_package(output_root=args.output_root, **options)
        print(json.dumps({"output": str(output), "summary": report.get("summary", {}),
                          "source_unchanged": True, "verified": args.verify_package is not None},
                         ensure_ascii=True, allow_nan=False, separators=(",", ":")))
    except (ValueError, OSError, KeyError, TypeError, ImportError) as error:
        parser.exit(1, f"outlet classification failed: {error}\n")


if __name__ == "__main__":
    main()
