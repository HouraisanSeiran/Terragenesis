"""Analyze one pinned M1/M2 graph without rerouting or rebuilding hydrology.

Run with python -m tools.prepare_td_reference_routing. Optional dependencies
are declared in algorithm/requirements-reference.txt and are never installed here.
The comparison codec's internal _terrain_boundary is intentionally reused so
saved terrain and boundary contracts have exactly the same decoding semantics.
"""

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, load_bundle, save_bundle
from terrain_pipeline.surface_rivers.metric_routing_comparison import (
    POLICIES, _terrain_boundary, decode_routing_comparison, load_routing_comparison,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "td-reference-graph-analysis-v1"
READINESS = {"hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}
CODE_PATHS = (
    "tools/prepare_td_reference_routing.py",
    "terrain_pipeline/surface_rivers/metric_reference_routing.py",
    "terrain_pipeline/surface_rivers/metric_routing_comparison.py",
    "terrain_pipeline/surface_rivers/metric_contracts.py",
    "terrain_pipeline/surface_rivers/metric_drainage.py",
    "terrain_pipeline/mountain_source_adapter.py",
    "terrain_pipeline/rainfall_runoff.py",
    "algorithm/requirements-reference.txt",
)


def _sha256(value, name):
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)):
        raise ValueError(name + " must be a lowercase SHA256")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key: " + key)
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("non-finite manifest value: " + value)


def _read_source(input_dir, manifest_sha256):
    manifest_path = input_dir / "manifest.json"
    payload = manifest_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != _sha256(manifest_sha256, "manifest pin"):
        raise ValueError("manifest SHA256 differs from external pin")
    manifest = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "td-river-m1-m2-preparation-v1"
            or manifest.get("status") != "diagnostic_m1_m2"
            or manifest.get("cold_read_verified") is not True
            or any(manifest.get(key) is not False for key in READINESS)):
        raise ValueError("input must be a cold-verified diagnostic M1/M2 manifest")
    pin = manifest["artifacts"]["routing-comparison"]
    package_sha256 = _sha256(pin["sha256"], "routing comparison pin")
    package_identity = _sha256(pin["identity_sha256"], "routing comparison identity")
    relative_path = Path(pin["path"])
    package_path = (input_dir / relative_path).resolve()
    if relative_path.is_absolute() or not package_path.is_relative_to(input_dir):
        raise ValueError("routing comparison path must stay inside input directory")
    bundle = load_routing_comparison(package_path, expected_sha256=package_sha256,
                                     expected_identity=package_identity)
    sources = {
        "manifest": {"path": str(manifest_path), "sha256": manifest_sha256},
        "routing_comparison": {"path": str(package_path), "sha256": package_sha256,
                               "identity_sha256": package_identity},
    }
    return bundle, sources


def _reference_api():
    try:
        importlib.import_module("pyflwdir")
    except ImportError as error:
        raise ImportError(
            "pyflwdir is required; install algorithm/requirements-reference.txt"
        ) from error
    module = importlib.import_module("terrain_pipeline.surface_rivers.metric_reference_routing")
    required = ("analyze_td_graph", "compare_reference_to_td", "result_to_record",
                "validate_reference_record")
    if any(not callable(getattr(module, name, None)) for name in required):
        raise RuntimeError("metric_reference_routing graph-analysis interface is not yet available")
    return module


def _code_pins():
    return {name: file_sha256(ROOT / name) for name in CODE_PATHS}


def _verify_sources(sources):
    for name, pin in sources.items():
        if file_sha256(pin["path"]) != pin["sha256"]:
            raise ValueError(name + " bytes changed during graph analysis")


def _statistics(record, terrain, graph):
    arrays = record["arrays"]
    valid = terrain.valid_mask.ravel()
    receiver = np.asarray(arrays["receiver"]).ravel()
    area = np.asarray(arrays["upstream_area_m2"]).ravel()
    stream_order = np.asarray(arrays["stream_order"]).ravel()
    terminal = valid & (receiver < 0)
    orders, counts = np.unique(stream_order[valid], return_counts=True)
    kinds, kind_counts = np.unique(graph.outlet_kind[terminal], return_counts=True)
    return {
        "grid_shape_zx": list(terrain.valid_mask.shape),
        "valid_cell_count": int(valid.sum()),
        "unknown_cell_count": int((~valid).sum()),
        "cell_area_m2": terrain.cell_area_m2,
        "valid_grid_area_m2": float(valid.sum()) * terrain.cell_area_m2,
        "upstream_area_m2": {"min": float(area[valid].min()),
                             "max": float(area[valid].max()),
                             "terminal_sum": float(area[terminal].sum())},
        "terminal_cell_count": int(terminal.sum()),
        "terminal_kind_counts": {str(kind): int(count) for kind, count in zip(kinds, kind_counts)},
        "strahler": {"max": int(stream_order[valid].max()),
                     "cell_counts": {str(int(order)): int(count)
                                     for order, count in zip(orders, counts)}},
    }


def prepare(input_dir, output, *, manifest_sha256, policy="original_bed_d8"):
    """Publish only a cold-validated analysis; never overwrite or audit M1/M2 hydrology."""
    output = Path(output).absolute()
    if os.path.lexists(output):
        raise FileExistsError(output)
    output = output.resolve()
    if policy not in POLICIES:
        raise ValueError("unknown routing policy: " + str(policy))
    input_dir = Path(input_dir).resolve()
    bundle, sources = _read_source(input_dir, manifest_sha256)
    graphs = decode_routing_comparison(bundle)
    terrain, boundary = _terrain_boundary(bundle)
    graph = graphs[policy]
    code_pins = _code_pins()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="." + output.name + ".partial-", dir=output.parent))
    published = False
    try:
        api = _reference_api()
        result = api.analyze_td_graph(terrain, boundary, graph)
        comparison = api.compare_reference_to_td(result, graph)
        for name in ("receiver", "terminal_cell", "upstream_area_m2"):
            if name not in comparison["mismatch_counts"]:
                raise ValueError("reference comparison is missing mismatch count: " + name)
            if comparison["mismatch_counts"][name] != 0:
                raise ValueError("preserved TD graph analysis differs: " + name)
        record = api.result_to_record(result)
        analysis_path = staging / "graph-analysis.npz"
        save_bundle(analysis_path, record, validator=api.validate_reference_record)
        analysis_sha256 = file_sha256(analysis_path)
        cold = load_bundle(analysis_path, expected_sha256=analysis_sha256,
                           validator=api.validate_reference_record, max_bytes=512 * 1024 * 1024)
        if cold["identity_sha256"] != record["identity_sha256"]:
            raise ValueError("cold analysis identity differs")
        report = {
            "schema": SCHEMA, "status": "external_reference_graph_diagnostic",
            "sources": sources, "policy": policy,
            "graph_identity_sha256": graph.identity_sha256,
            "terrain_identity_sha256": terrain.identity_sha256,
            "boundary_identity_sha256": boundary.identity_sha256,
            "terrain_provenance": terrain.metadata(),
            "backend": result.backend, "version": result.version,
            "reference_metadata": cold["metadata"],
            "statistics": _statistics(cold, terrain, graph),
            "comparison": comparison, "mismatch_counts": comparison["mismatch_counts"],
            "artifacts": {"graph-analysis": {"path": "graph-analysis.npz",
                                             "sha256": analysis_sha256,
                                             "identity_sha256": cold["identity_sha256"]}},
            "code_sha256": code_pins, "cold_read_verified": True,
            "source_bytes_unchanged": True,
            "rerouted": False, "rainfall_recomputed": False, "hydraulics_recomputed": False,
            **READINESS,
        }
        _verify_sources(sources)
        if _code_pins() != code_pins:
            raise ValueError("analysis code changed during preparation")
        (staging / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        _verify_sources(sources)
        if os.path.lexists(output):
            raise FileExistsError(output)
        staging.rename(output)
        published = True
        return report
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--policy", choices=POLICIES, default="original_bed_d8")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = prepare(args.input, args.output, manifest_sha256=args.manifest_sha256,
                         policy=args.policy)
    except (OSError, ValueError, KeyError, TypeError, ImportError, RuntimeError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps({"status": report["status"], "output": str(args.output.resolve()),
                      "mismatch_counts": report["mismatch_counts"], **READINESS},
                     ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
