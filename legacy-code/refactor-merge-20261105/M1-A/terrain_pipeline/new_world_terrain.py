"""Immutable, bounded raw-TD bed and inherited window classifications."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from scipy.ndimage import label

from terrain_pipeline import plate_td_product
from terrain_pipeline.coastal_terrain import classify

POLICY = "raw-td-parent-anchor-four-neighbour-v2"
# The published v2 implementation predates the mosaic reader. Its recorded
# producer hash is part of immutable product identity, not the reader version.
V2_PUBLISHED_ALGORITHMS = frozenset({"dfa8195c2f7267f200b54ae56bce4afb3c873709e365790de7f59a094d55cd11"})
WORLD_SEED = 20261020
NAMES = {"bed_m", "raw_td_m", "valid_mask", "ocean_mask", "closed_below_sea_mask", "unknown_mask", "climate_base"}


def _identity(record):
    record = {k: v for k, v in record.items() if k != "source_path"}
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _derive(manifest, source):
    if not manifest["coastal"]:
        raise ValueError("certified coastal parent required")
    raw = source["raw_td"]
    anchor = manifest["anchor_bed_zx"]
    origin = manifest["origin_native_xz"]
    bed_origin = manifest["bed_origin_native_xz"]
    if (not isinstance(anchor, list) or len(anchor) != 2 or
            any(type(v) is not int for v in anchor)):
        raise ValueError("invalid parent anchor")
    az = anchor[0] + bed_origin[1] - origin[1]
    ax = anchor[1] + bed_origin[0] - origin[0]
    if not (0 <= az < raw.shape[0] and 0 <= ax < raw.shape[1]):
        raise ValueError("parent anchor outside raw TD")
    valid = np.ones(raw.shape, dtype=bool)
    if raw[az, ax] < 0:
        codes, _ = classify(raw, valid, [(az, ax)])
    else:
        components, _ = label(raw < 0)
        edges = np.unique(np.concatenate((components[0], components[-1], components[:, 0], components[:, -1])))
        codes = np.where(raw >= 0, 1, np.where(np.isin(components, edges), 0, 3)).astype(np.uint8)
    return {"bed_m": raw, "raw_td_m": raw, "valid_mask": valid,
            "ocean_mask": codes == 2, "closed_below_sea_mask": codes == 3,
            "unknown_mask": codes == 0, "climate_base": source["td_climate"]}


def prepare(source, output, *, expected_source_identity):
    if not isinstance(expected_source_identity, str) or len(expected_source_identity) != 64:
        raise ValueError("expected source identity required")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    source_file = Path(source) / "manifest.json"
    source_manifest = json.loads(source_file.read_text(encoding="utf-8")) if source_file.exists() else {}
    if source_manifest.get("schema") == "new-world-source-mosaic-v1":
        return _prepare_mosaic(source, output, expected_source_identity)
    parent, source_arrays = plate_td_product.read_product(source, expected_identity=expected_source_identity)
    arrays = _derive(parent, source_arrays)
    tmp = Path(tempfile.mkdtemp(prefix=".terrain-stage-", dir=output.parent))
    try:
        hashes = {}
        for name, array in arrays.items():
            np.save(tmp / (name + ".npy"), array, allow_pickle=False)
            hashes[name] = plate_td_product.digest(tmp / (name + ".npy"))
        manifest = {"schema": "new-world-terrain-v2", "policy": POLICY,
                    "source_path": str(Path(source).resolve()), "world_seed": WORLD_SEED,
                    "algorithm_sha256": plate_td_product.digest(Path(__file__)),
                    "source_identity": expected_source_identity, "plate_identity": parent["plate_identity"],
                    "origin_native_xz": parent["origin_native_xz"], "shape_zx": parent["source_shape_zx"],
                    "spacing_m": 30, "sea_m": 0, "files": hashes,
                    "classification_support": "whole finite TD window; frozen parent anchor mapped to raw; dry anchor certifies no ocean; four-neighbour; boundary wet without anchor unknown; enclosed means below datum, not a lake",
                    "climate_support": "five stored TD channels; no 22.5 km halo; no new G4 rain-shadow acceptance",
                    "morphology": "not user accepted"}
        manifest["identity"] = _identity(manifest)
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        read_product(tmp)
        os.rename(tmp, output)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return read_product(output)


def read_product(path, expected_identity=None):
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") == "new-world-terrain-v3":
        return _read_mosaic_terrain(path, manifest, expected_identity)
    identity = manifest.get("identity")
    record = {k: v for k, v in manifest.items() if k != "identity"}
    if identity != _identity(record) or (expected_identity is not None and identity != expected_identity):
        raise ValueError("identity mismatch")
    if (manifest.get("schema") != "new-world-terrain-v2" or manifest.get("policy") != POLICY or
        manifest.get("spacing_m") != 30 or manifest.get("sea_m") != 0 or
        type(manifest.get("world_seed")) is not int or manifest["world_seed"] != WORLD_SEED or
        manifest.get("algorithm_sha256") not in V2_PUBLISHED_ALGORITHMS | {plate_td_product.digest(Path(__file__))} or
        not isinstance(manifest.get("source_path"), str) or not Path(manifest["source_path"]).is_absolute() or
        set(manifest.get("files", {})) != NAMES):
        raise ValueError("product contract mismatch")
    origin, shape = manifest["origin_native_xz"], manifest["shape_zx"]
    if len(origin) != 2 or any(type(v) is not int for v in origin) or len(shape) != 2 or any(type(v) is not int or v <= 0 for v in shape):
        raise ValueError("invalid coordinates")
    for key in ("source_identity", "plate_identity"):
        value = manifest[key]
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("invalid source identity")
    parent, source = plate_td_product.read_product(manifest["source_path"], expected_identity=manifest["source_identity"])
    if (parent["world_seed"] != WORLD_SEED or parent["plate_identity"] != manifest["plate_identity"] or
            parent["origin_native_xz"] != origin or parent["source_shape_zx"] != shape or
            parent["spacing_m"] != manifest["spacing_m"] or parent["sea_m"] != manifest["sea_m"]):
        raise ValueError("parent metadata mismatch")
    expected = _derive(parent, source)
    arrays = {}
    for name in NAMES:
        file = path / (name + ".npy")
        if plate_td_product.digest(file) != manifest["files"][name]:
            raise ValueError("array hash mismatch")
        arrays[name] = np.load(file, mmap_mode="r", allow_pickle=False)
        expected_shape = (5, *shape) if name == "climate_base" else tuple(shape)
        dtype = np.bool_ if name.endswith("_mask") else np.float32
        if arrays[name].shape != expected_shape or arrays[name].dtype != dtype or not np.isfinite(arrays[name]).all():
            raise ValueError("invalid array")
        if not np.array_equal(arrays[name], expected[name]):
            raise ValueError("parent derivation mismatch: " + name)
    bed = arrays["bed_m"]
    ocean, closed, unknown, valid = (arrays[k] for k in ("ocean_mask", "closed_below_sea_mask", "unknown_mask", "valid_mask"))
    if (not valid.all() or not np.array_equal(bed, arrays["raw_td_m"]) or
        np.any((ocean.astype(np.uint8) + closed + unknown) > 1) or
        not np.array_equal(ocean | closed | unknown, bed < 0)):
        raise ValueError("invalid classification or bed")
    return manifest, arrays


def _mosaic_derive(parent, source):
    from terrain_pipeline import new_world_source_mosaic as mosaic
    plate = mosaic.load_product(parent["source_paths"]["plate"], expected_identity=parent["plate_identity"])
    evidence = mosaic._boundary_evidence(plate, parent["origin_native_xz"], parent["shape_zx"])
    raw = source["raw_td"]
    ocean, closed, unknown = mosaic.classify_boundary_ocean(raw, evidence)
    return {"bed_m": raw, "raw_td_m": raw, "valid_mask": np.ones(raw.shape, bool),
            "ocean_mask": ocean, "closed_below_sea_mask": closed, "unknown_mask": unknown,
            "climate_base": source["td_climate"]}


def _prepare_mosaic(source, output, expected_identity):
    from terrain_pipeline import new_world_source_mosaic as mosaic
    parent, source_arrays = mosaic.read_product(source, expected_identity=expected_identity)
    arrays = _mosaic_derive(parent, source_arrays)
    tmp = Path(tempfile.mkdtemp(prefix=".terrain-stage-", dir=output.parent))
    try:
        hashes = {}
        for name, array in arrays.items():
            np.save(tmp / (name + ".npy"), array, allow_pickle=False)
            hashes[name] = plate_td_product.digest(tmp / (name + ".npy"))
        m = {"schema": "new-world-terrain-v3", "source_schema": mosaic.SCHEMA,
             "policy": "raw-negative-four-neighbour-macro-ocean-boundary-v1", "source_path": str(Path(source).resolve()),
             "source_identity": expected_identity, "plate_identity": parent["plate_identity"],
             "world_seed": WORLD_SEED, "origin_native_xz": parent["origin_native_xz"],
             "shape_zx": parent["shape_zx"], "spacing_m": 30, "sea_m": 0, "files": hashes,
             "classification_support": "finite boundary inherits frozen macro ocean; not global hydrodynamic certification"}
        m["identity"] = _identity(m)
        (tmp / "manifest.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
        _read_mosaic_terrain(tmp, m, None)
        os.rename(tmp, output)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return read_product(output)


def _read_mosaic_terrain(path, m, expected_identity):
    from terrain_pipeline import new_world_source_mosaic as mosaic
    if (m.get("identity") != _identity({k: v for k, v in m.items() if k != "identity"}) or
            (expected_identity is not None and m["identity"] != expected_identity) or
            m.get("schema") != "new-world-terrain-v3" or m.get("source_schema") != mosaic.SCHEMA or
            m.get("policy") != "raw-negative-four-neighbour-macro-ocean-boundary-v1" or
            m.get("world_seed") != WORLD_SEED or m.get("spacing_m") != 30 or m.get("sea_m") != 0 or
            set(m.get("files", {})) != NAMES):
        raise ValueError("terrain contract or identity mismatch")
    parent, source = mosaic.read_product(m["source_path"], expected_identity=m["source_identity"])
    if any(m[k] != parent[k] for k in ("plate_identity", "origin_native_xz", "shape_zx", "world_seed", "spacing_m", "sea_m")):
        raise ValueError("mosaic metadata mismatch")
    expected = _mosaic_derive(parent, source)
    arrays = {}
    for name in NAMES:
        file = path / (name + ".npy")
        if plate_td_product.digest(file) != m["files"][name]:
            raise ValueError("terrain array hash mismatch")
        arrays[name] = np.load(file, mmap_mode="r", allow_pickle=False)
        if arrays[name].dtype != expected[name].dtype or arrays[name].shape != expected[name].shape or not np.array_equal(arrays[name], expected[name]):
            raise ValueError("terrain derivation mismatch: " + name)
    return m, arrays


def query_window(product, origin_native_xz, shape):
    """Return read-only views: origin [x,z] is in native 30 m indices, shape [z,x] in cells."""
    manifest, arrays = product
    if (len(origin_native_xz) != 2 or len(shape) != 2 or
        any(type(v) is not int for v in origin_native_xz) or
        any(type(v) is not int or v <= 0 for v in shape)):
        raise ValueError("integer origin and positive integer shape required")
    x = origin_native_xz[0] - manifest["origin_native_xz"][0]
    z = origin_native_xz[1] - manifest["origin_native_xz"][1]
    if x < 0 or z < 0 or z + shape[0] > manifest["shape_zx"][0] or x + shape[1] > manifest["shape_zx"][1]:
        raise ValueError("window outside product")
    window = {name: a[..., z:z + shape[0], x:x + shape[1]] for name, a in arrays.items()}
    for view in window.values():
        view.setflags(write=False)
    return {"identity": manifest["identity"], "source_identity": manifest["source_identity"],
            "origin_native_xz": list(origin_native_xz), "shape_zx": list(shape), "spacing_m": 30}, window
