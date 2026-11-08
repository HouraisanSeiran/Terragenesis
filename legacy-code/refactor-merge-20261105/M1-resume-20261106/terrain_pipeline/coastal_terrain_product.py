"""Explicit, source-bound offline preparation of the saved TD review region."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from dataclasses import asdict
import numpy as np
import psutil
from terrain_pipeline.coastal_terrain import CoastalParameters, coastal_support, compose, classify
from terrain_pipeline.tectonic_product import load_product

RAW_HASH = "1dfa01dbb798fa698a7a68a1fc820e33e90606a67c79c2a6498967440ea35aaa"
RAW_ARRAY = "f414d614e665400125815ff0c6f06135f6c8700da5d615ecb463379b5bdcdd30"
MACRO_HASH = "81d70f255b7b91ed7c2b04795c9bf91d9eb49a447361e6d5349c75716558573f"
MACRO_ARRAY = "6c12aa113d67bad5ca94f0fc1fa8ce384a509692f47d8e4b33eb1acdd7f930af"
TD_ID = "b11092789e5077fbe7c61926b2b1c0788ef22065edf2597035a13abe506ee607"

def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def array_hash(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def plate_macro(path, identity, shape, origin_xz_m, spacing_m):
    product = load_product(path, expected_identity=identity)
    out = np.empty(shape, np.float32)
    x = origin_xz_m[0] + np.arange(shape[1])[None, :] * spacing_m
    for start in range(0, shape[0], 64):
        stop = min(start + 64, shape[0])
        z = origin_xz_m[1] + np.arange(start, stop)[:, None] * spacing_m
        out[start:stop] = product.sample(x, z, outside="reject")["elevation_m"]
    return out



def prepare(raw_path, macro_path, metadata_path, output, *, plate_path=None, plate_identity=None, memory_budget_bytes=850_000_000):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    # Estimate before reading or allocating any terrain arrays.
    needed = 850_000_000
    disk_parent = output.parent
    while not disk_parent.exists():
        disk_parent = disk_parent.parent
    if memory_budget_bytes < needed or psutil.virtual_memory().available < needed or shutil.disk_usage(disk_parent).free < 500_000_000:
        raise ValueError("insufficient memory or disk budget")
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if (metadata.get("terrain_identity") != TD_ID or metadata.get("source_shape_zx") != [3834, 3834] or metadata.get("source_origin_native_xz") != [3351, -1917] or metadata.get("native_spacing_m") != 30):
        raise ValueError("wrong TD metadata or coordinate identity")
    if file_hash(raw_path) != RAW_HASH or file_hash(macro_path) != MACRO_HASH:
        raise ValueError("source file hash mismatch")
    raw = np.load(raw_path, mmap_mode="r", allow_pickle=False)
    original_macro = np.load(macro_path, mmap_mode="r", allow_pickle=False)
    if raw.shape != (3834, 3834) or original_macro.shape != raw.shape or array_hash(raw) != RAW_ARRAY or array_hash(original_macro) != MACRO_ARRAY:
        raise ValueError("source array hash or shape mismatch")
    # Fixed source extent includes the review window, filter support, coastal
    # distance support and independently identified offshore anchor.
    z0, z1, x0, x1 = 640, 3210, 640, 3450
    raw = raw[z0:z1, x0:x1]
    if plate_path is None:
        macro = original_macro[z0:z1, x0:x1]
        macro_identity = MACRO_ARRAY
    else:
        if not plate_identity:
            raise ValueError("plate identity required")
        macro = plate_macro(plate_path, plate_identity, raw.shape, (100530+x0*30, -57510+z0*30), 30)
        plate = load_product(plate_path, expected_identity=plate_identity)
        if not bool(plate.sample(190050, 0, outside="reject")["ocean_connected"]):
            raise ValueError("plate anchor is not connected ocean")
        macro_identity = plate_identity
    params = CoastalParameters()
    support = coastal_support(macro, params, anchors=[(1917-z0, 2984-x0)])
    bed = compose(raw, macro, params, support=support)
    radius = params.validate()
    # Anchor is an independently identified offshore point in the source macro.
    anchors = [(1917-z0-radius, 2984-x0-radius)]
    valid = np.ones(bed.shape, bool)
    margin = int(params.coast_band_m / params.spacing_m) - radius
    valid[:margin,:] = False
    valid[-margin:,:] = False
    valid[:,:margin] = False
    valid[:,-margin:] = False
    codes, shore = classify(bed, valid, anchors)
    output.parent.mkdir(parents=True, exist_ok=True)
    peak_rss = getattr(psutil.Process().memory_info(), "peak_wset", psutil.Process().memory_info().rss)
    del support, macro, raw, original_macro
    tmp = Path(tempfile.mkdtemp(prefix=".coast-", dir=output.parent))
    try:
        arrays = {"bed": bed, "valid": valid, "classification": codes, "shoreline": shore}
        hashes = {}
        for name, array in arrays.items():
            path = tmp / (name + ".npy")
            np.save(path, array, allow_pickle=False)
            hashes[path.name] = file_hash(path)
        source_files = [Path(__file__), Path(__file__).with_name("coastal_terrain.py")]
        manifest = {"schema": "coastal-terrain-v1", "algorithm_version": "coastal-bed-v1", "preflight_estimated_bytes": needed, "parameters": asdict(params), "origin_xz_m": [100530 + (x0+radius)*30, -57510 + (z0+radius)*30], "spacing_m": 30, "shape_zx": list(bed.shape), "source_shape_zx": [3834,3834], "source_origin_xz_m": [100530,-57510], "valid_margin_cells": radius, "coast_support_margin_cells": 200, "support_boundary_note": "outer 104 cells of saved bed may lack full horizontal coastal support; review window has complete support", "fixed_source_slice_zx": [z0,z1,x0,x1], "coast_support": "fixed macro shoreline distance, capped at coast_band_m; computed before crop", "coordinate_convention": "cell centres; x east, z south; arrays z,x", "terrain_identity": TD_ID, "world_seed": 20261020, "raw_path": str(Path(raw_path).resolve()), "raw_file_sha256": RAW_HASH, "raw_array_sha256": RAW_ARRAY, "original_macro_path": str(Path(macro_path).resolve()), "original_macro_file_sha256": MACRO_HASH, "original_macro_array_sha256": MACRO_ARRAY, "metadata_path": str(Path(metadata_path).resolve()), "metadata_sha256": file_hash(metadata_path), "macro_identity": macro_identity, "plate_path": str(Path(plate_path).resolve()) if plate_path else None, "plate_file_sha256": file_hash(plate_path) if plate_path else None, "td_conditioning": "original macro; plate combination is derived adaptation, not new inference", "anchor_source_zx": [1917,2984], "anchor_world_xz_m": [190050,0], "anchor_provenance": ("plate frozen ocean_connected and final wet bed" if plate_path else "interior offshore point east of original macro coast; final bed wet"), "algorithm_sha256": {p.name:file_hash(p) for p in source_files}, "files": hashes}
        (tmp / "performance.json").write_text(json.dumps({"measured_peak_rss_bytes_before_staging": peak_rss, "preflight_estimated_bytes": needed}, indent=2), encoding="utf-8")
        manifest["identity"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        read_product(tmp, expected_identity=manifest["identity"])
        os.rename(tmp, output)
    finally:
        if tmp.exists() and tmp.resolve().parent == output.parent.resolve() and tmp.name.startswith(".coast-"):
            shutil.rmtree(tmp)
    return read_product(output)


def read_product(path, *, expected_identity=None):
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    identity = manifest.pop("identity", None)
    actual = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if identity != actual or (expected_identity is not None and identity != expected_identity):
        raise ValueError("product identity mismatch")
    manifest["identity"] = identity
    if manifest.get("schema") != "coastal-terrain-v1" or set(manifest.get("files", {})) != {"bed.npy", "valid.npy", "classification.npy", "shoreline.npy"}:
        raise ValueError("invalid product manifest")
    result = {}
    for name, expected in manifest["files"].items():
        if file_hash(path / name) != expected:
            raise ValueError("product hash mismatch")
        result[name[:-4]] = np.load(path / name, allow_pickle=False)
        if list(result[name[:-4]].shape) != manifest["shape_zx"]:
            raise ValueError("product shape mismatch")
    bed, valid, codes, shore = result["bed"], result["valid"], result["classification"], result["shoreline"]
    if bed.dtype != np.float32 or not np.isfinite(bed).all() or codes.dtype != np.uint8 or not np.isin(codes, [0,1,2,3]).all() or shore.dtype != np.bool_ or valid.dtype != np.bool_:
        raise ValueError("invalid product fields")
    z0, _, x0, _ = manifest["fixed_source_slice_zx"]
    radius = manifest["valid_margin_cells"]
    anchor = (1917-z0-radius, 2984-x0-radius)
    params = CoastalParameters(**manifest["parameters"])
    if (manifest.get("algorithm_version") != "coastal-bed-v1" or manifest.get("anchor_source_zx") != [1917,2984] or manifest.get("anchor_world_xz_m") != [190050,0] or params.validate() != radius or manifest["spacing_m"] != 30 or params.spacing_m != 30 or any(not isinstance(v, int) for v in manifest["fixed_source_slice_zx"]) or not (0 <= z0 < manifest["fixed_source_slice_zx"][1] <= 3834 and 0 <= x0 < manifest["fixed_source_slice_zx"][3] <= 3834) or manifest["source_shape_zx"] != [3834,3834] or manifest["source_origin_xz_m"] != [100530,-57510] or manifest["origin_xz_m"] != [100530+(x0+radius)*30,-57510+(z0+radius)*30] or manifest["shape_zx"] != [manifest["fixed_source_slice_zx"][1]-z0-2*radius, manifest["fixed_source_slice_zx"][3]-x0-2*radius]):
        raise ValueError("inconsistent product coordinates")
    border = int(params.coast_band_m / params.spacing_m) - radius
    expected_valid = np.ones(bed.shape, bool)
    if border > 0:
        expected_valid[:border,:] = expected_valid[-border:,:] = False
        expected_valid[:,:border] = expected_valid[:,-border:] = False
    if not np.array_equal(valid, expected_valid):
        raise ValueError("invalid domain mask")
    check_codes, check_shore = classify(bed, valid, [anchor], params.sea_m)
    if not np.array_equal(codes, check_codes) or not np.array_equal(shore, check_shore):
        raise ValueError("inconsistent classification")
    for array in result.values():
        array.flags.writeable = False
    return manifest, result
