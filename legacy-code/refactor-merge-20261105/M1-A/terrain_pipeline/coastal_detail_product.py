"""Source-checked CPU preparation and cold reading of static coastal detail.

The small frozen-source record is also usable with portable fixtures. Real CLI
preparation only accepts the approved old Coastal v1 identity. File paths remain
provenance but do not affect numerical identity. No source is ever overwritten.
"""
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import numpy as np
import psutil
from terrain_pipeline.coastal_detail_refinement import DetailParameters, detail_support, refine
from terrain_pipeline.coastal_terrain import classify
from terrain_pipeline.coastal_terrain_product import read_product as read_baseline, file_hash

APPROVED_BASELINE = "42a50c3b13f8f4169002438e879d54e53fb094cff9bde9dd7659bfebe4336c60"
BASE_FIELDS = {"bed.npy", "valid.npy", "classification.npy", "shoreline.npy"}
OUTPUT_FIELDS = BASE_FIELDS | {"delta.npy", "distance_m.npy", "weight.npy"}
SOURCE_KEYS = {"kind", "baseline_path", "baseline_identity", "files", "raw_path", "raw_file_sha256", "raw_array_sha256", "metadata_path", "metadata_sha256", "terrain_identity", "world_seed", "shape_zx", "origin_xz_m", "spacing_m", "source_shape_zx", "source_origin_xz_m", "source_slice_zx", "anchors_zx"}


def identity(record):
    """Canonical identity excludes only paths and the identity field itself."""
    def numerical(value):
        if isinstance(value, dict):
            return {k: numerical(v) for k, v in value.items() if k != "identity" and not k.endswith("_path")}
        if isinstance(value, list):
            return [numerical(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(numerical(record), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def array_hash(array):
    digest = hashlib.sha256()
    for start in range(0, array.shape[0], 64):
        digest.update(np.ascontiguousarray(array[start:start + 64]).tobytes())
    return digest.hexdigest()


def _algorithms():
    return {name: file_hash(Path(__file__).with_name(name)) for name in (
        "coastal_detail_product.py", "coastal_detail_refinement.py", "coastal_terrain.py", "coastal_terrain_product.py")}


def _preflight(source, budget, output=None):
    # Includes mapped new raw source pages, EDT temporaries, independent cold
    # recomputation and saved arrays. No model or macro array is loaded here.
    shape = source.get("shape_zx", [])
    raw_shape = source.get("source_shape_zx", [])
    if len(shape) != 2 or len(raw_shape) != 2 or any(type(v) is not int or v <= 0 for v in shape + raw_shape):
        raise ValueError("invalid source shape")
    needed = math.prod(shape) * 128 + math.prod(raw_shape) * 4 + 32_000_000
    if needed > budget or budget > 1_000_000_000 or psutil.virtual_memory().available < needed:
        raise ValueError("insufficient memory budget (maximum 1GB)")
    if output is not None:
        parent = Path(output).parent
        while not parent.exists():
            parent = parent.parent
        if shutil.disk_usage(parent).free < math.prod(shape) * 32 + 1_000_000:
            raise ValueError("insufficient disk budget")
    return needed


def _approved_record(path):
    path = Path(path).resolve()
    m = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if m.get("identity") != APPROVED_BASELINE:
        raise ValueError("approved baseline identity required")
    z0, z1, x0, x1 = m["fixed_source_slice_zx"]
    radius = m["valid_margin_cells"]
    return {"kind": "approved-coastal-v1", "baseline_path": str(path), "baseline_identity": m["identity"], "files": m["files"],
            **{k: m[k] for k in ("raw_path", "raw_file_sha256", "raw_array_sha256", "metadata_path", "metadata_sha256", "terrain_identity", "world_seed", "shape_zx", "origin_xz_m", "spacing_m", "source_shape_zx", "source_origin_xz_m")},
            "source_slice_zx": [z0 + radius, z1 - radius, x0 + radius, x1 - radius],
            "anchors_zx": [[m["anchor_source_zx"][0] - z0 - radius, m["anchor_source_zx"][1] - x0 - radius]]}


def _frozen_baseline_identity(source):
    return identity({k: source[k] for k in ("files", "shape_zx", "origin_xz_m", "spacing_m", "anchors_zx")})


def _load_source(source):
    if set(source) != SOURCE_KEYS or set(source["files"]) != BASE_FIELDS or source["world_seed"] != 20261020 or source["spacing_m"] != 30:
        raise ValueError("invalid frozen source record")
    for name in ("origin_xz_m", "source_origin_xz_m"):
        if not isinstance(source[name], list) or len(source[name]) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in source[name]):
            raise ValueError("invalid source origin")
    if source["kind"] == "approved-coastal-v1":
        if _approved_record(source["baseline_path"]) != source:
            raise ValueError("baseline source binding mismatch")
        _, baseline = read_baseline(source["baseline_path"], expected_identity=APPROVED_BASELINE)
    elif source["kind"] == "frozen-detail-source-v1":
        if source["baseline_identity"] != _frozen_baseline_identity(source):
            raise ValueError("frozen baseline identity mismatch")
        baseline = {}
        for name, digest in source["files"].items():
            path = Path(source["baseline_path"]) / name
            if file_hash(path) != digest:
                raise ValueError("baseline source hash mismatch")
            baseline[name[:-4]] = np.load(path, mmap_mode="r", allow_pickle=False)
    else:
        raise ValueError("unknown source kind")
    for name, dtype in (("bed", np.float32), ("valid", np.bool_), ("classification", np.uint8), ("shoreline", np.bool_)):
        if list(baseline[name].shape) != source["shape_zx"] or baseline[name].dtype != dtype:
            raise ValueError("baseline source arrays mismatch")
    if not np.isfinite(baseline["bed"]).all():
        raise ValueError("nonfinite baseline")
    codes, shore = classify(baseline["bed"], baseline["valid"], source["anchors_zx"])
    if not np.array_equal(codes, baseline["classification"]) or not np.array_equal(shore, baseline["shoreline"]):
        raise ValueError("baseline classification mismatch")
    if file_hash(source["metadata_path"]) != source["metadata_sha256"] or file_hash(source["raw_path"]) != source["raw_file_sha256"]:
        raise ValueError("external source hash mismatch")
    metadata = json.loads(Path(source["metadata_path"]).read_text(encoding="utf-8"))
    if (metadata.get("terrain_identity") != source["terrain_identity"] or metadata.get("world_seed") != 20261020 or metadata.get("source_shape_zx") != source["source_shape_zx"] or metadata.get("native_spacing_m") != source["spacing_m"] or metadata.get("native_source_origin_xz_m") != source["source_origin_xz_m"] or metadata.get("source_origin_native_xz") != [v / source["spacing_m"] for v in source["source_origin_xz_m"]]):
        raise ValueError("metadata source coordinates mismatch")
    binding = metadata.get("native_source_paths", {}).get("raw_td_30m", {})
    # The metadata's original path is provenance. Actual mapped bytes are bound
    # by both hashes, permitting relocation without changing numerical identity.
    if binding.get("sha256") != source["raw_file_sha256"] or binding.get("array_sha256") != source["raw_array_sha256"]:
        raise ValueError("metadata raw binding mismatch")
    raw = np.load(source["raw_path"], mmap_mode="r", allow_pickle=False)
    if list(raw.shape) != source["source_shape_zx"] or raw.dtype != np.float32 or array_hash(raw) != source["raw_array_sha256"]:
        raise ValueError("raw source array mismatch")
    mapping = source["source_slice_zx"]
    if len(mapping) != 4 or any(type(v) is not int for v in mapping):
        raise ValueError("invalid source slice")
    z0, z1, x0, x1 = mapping
    if not (0 <= z0 < z1 <= raw.shape[0] and 0 <= x0 < x1 <= raw.shape[1]) or [z1 - z0, x1 - x0] != source["shape_zx"] or source["origin_xz_m"] != [source["source_origin_xz_m"][0] + x0 * source["spacing_m"], source["source_origin_xz_m"][1] + z0 * source["spacing_m"]]:
        raise ValueError("source slice/world mapping mismatch")
    return baseline, raw[z0:z1, x0:x1]


def _derive(source, params):
    baseline, raw = _load_source(source)
    support = detail_support(baseline["bed"], baseline["valid"], baseline["classification"], baseline["shoreline"], params)
    bed, delta = refine(raw, baseline["bed"], support=support, params=params)
    codes, shore = classify(bed, baseline["valid"], source["anchors_zx"])
    return {"bed": bed, "delta": delta, "valid": baseline["valid"], "classification": codes, "shoreline": shore, **support}


def prepare_source(source, output, *, params=DetailParameters(), memory_budget_bytes=1_000_000_000):
    """Prepare an explicitly frozen source record (portable fixtures included)."""
    params.validate()
    if params.spacing_m != source["spacing_m"]:
        raise ValueError("parameter/source spacing mismatch")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    needed = _preflight(source, memory_budget_bytes, output)
    arrays = _derive(source, params)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".coastal-detail-", dir=output.parent))
    try:
        files = {}
        for name, array in arrays.items():
            path = stage / (name + ".npy")
            np.save(path, array, allow_pickle=False)
            files[path.name] = file_hash(path)
        manifest = {"schema": "coastal-detail-product-v1", "algorithm_version": "static-td-bandpass-restoration-v1", "source": source, "parameters": asdict(params), "origin_xz_m": source["origin_xz_m"], "spacing_m": source["spacing_m"], "shape_zx": source["shape_zx"], "world_seed": 20261020, "randomness": "none", "finite_support": {"filter_radius_cells": params.validate(), "filter_radius_m": params.radius_m, "distance_support": "shared full-baseline connected-ocean land-cell shoreline; capped raster EDT", "window_contract": "slice shared support; discard radius cells on each edge"}, "algorithm_sha256": _algorithms(), "files": files}
        manifest["identity"] = identity(manifest)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (stage / "performance.json").write_text(json.dumps({"estimated_working_bytes": needed, "new_raw_source_count": 1, "raw_access": "stream hash and read-only mmap", "peak_process_bytes_before_cold_read": getattr(psutil.Process().memory_info(), "peak_wset", psutil.Process().memory_info().rss)}, indent=2), encoding="utf-8")
        del arrays
        read_product(stage, expected_identity=manifest["identity"], memory_budget_bytes=memory_budget_bytes)
        if output.exists():
            raise FileExistsError(output)
        os.rename(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest


def prepare(baseline, output, *, params=DetailParameters(), memory_budget_bytes=1_000_000_000):
    return prepare_source(_approved_record(baseline), output, params=params, memory_budget_bytes=memory_budget_bytes)


def read_product(path, *, expected_identity=None, memory_budget_bytes=1_000_000_000):
    """Hash sources and arrays, then independently reproduce every derived field."""
    path = Path(path)
    m = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if m.get("identity") != identity(m) or (expected_identity is not None and m["identity"] != expected_identity):
        raise ValueError("product identity mismatch")
    if m.get("schema") != "coastal-detail-product-v1" or m.get("algorithm_version") != "static-td-bandpass-restoration-v1" or set(m.get("files", {})) != OUTPUT_FIELDS or m.get("algorithm_sha256") != _algorithms() or m.get("world_seed") != 20261020 or m.get("randomness") != "none":
        raise ValueError("invalid product schema or algorithm")
    if set(m["parameters"]) != set(asdict(DetailParameters())):
        raise ValueError("incomplete detail parameters")
    params = DetailParameters(**m["parameters"])
    radius = params.validate()
    source = m["source"]
    if any(m[k] != source[k] for k in ("shape_zx", "origin_xz_m", "spacing_m")) or params.spacing_m != source["spacing_m"] or m["finite_support"] != {"filter_radius_cells": radius, "filter_radius_m": params.radius_m, "distance_support": "shared full-baseline connected-ocean land-cell shoreline; capped raster EDT", "window_contract": "slice shared support; discard radius cells on each edge"}:
        raise ValueError("inconsistent product coordinates or support")
    _preflight(source, memory_budget_bytes)
    arrays = {}
    for name, digest in m["files"].items():
        if file_hash(path / name) != digest:
            raise ValueError("product array hash mismatch")
        array = np.load(path / name, mmap_mode="r", allow_pickle=False)
        dtype = np.bool_ if name in {"valid.npy", "shoreline.npy"} else np.uint8 if name == "classification.npy" else np.float32
        if list(array.shape) != m["shape_zx"] or array.dtype != dtype or not np.isfinite(array).all():
            raise ValueError("invalid product array")
        arrays[name[:-4]] = array
    derived = _derive(source, params)
    for name, actual in arrays.items():
        if not np.array_equal(actual, derived[name]):
            raise ValueError("derived relation mismatch: " + name)
        actual.flags.writeable = False
    return m, arrays
