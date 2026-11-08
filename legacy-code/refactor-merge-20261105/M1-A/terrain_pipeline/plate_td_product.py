"""Bounded staged plate-conditioned TD source and coastal product."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from dataclasses import asdict
import math

import numpy as np
import psutil

from diffusion.plate_td_backend import generate
from diffusion.plate_td_conditioning import PLATE_IDENTITY, WORLD_SEED
from diffusion.physical_config import PhysicalGenerationConfig
from terrain_pipeline.coastal_archipelago import relief
from terrain_pipeline.coastal_terrain import CoastalParameters, coastal_support, compose, classify
from terrain_pipeline.tectonic_product import load_product


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _identity(record):
    # Runtime and locations are provenance, not numerical content identity.
    canonical = json.loads(json.dumps(record))
    canonical.pop("source_path", None)
    generation = canonical.get("generation", {})
    generation.get("record", {}).pop("source", None)
    # These opaque IDs include model_dir before normalization. Their full
    # metadata stays below, and _check_generation validates both provenance IDs.
    generation.pop("physical_generation_identity", None)
    generation.get("physical_generation", {}).pop("conditioning_identity", None)
    generation.get("record", {}).get("config", {}).pop("model_dir", None)
    generation.get("physical_generation", {}).get("config", {}).pop("model_dir", None)
    generation.get("physical_generation", {}).get("upstream", {}).pop("source", None)
    for key in ("wall_clock_s", "peak_child_rss_mib", "peak_child_gpu_mib", "allocated_peak_mib", "reserved_peak_mib"):
        generation.pop(key, None)
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _validate_model(config, metadata):
    from diffusion.paths import inside
    model_dir = inside(config.model_dir)
    for name, entry in metadata["model"]["files"].items():
        file = (model_dir / name).resolve()
        if not file.is_relative_to(model_dir.resolve()) or not file.is_file() or file.stat().st_size != entry["bytes"] or digest(file) != entry["sha256"]:
            raise ValueError("model content mismatch: " + name)


def _check_generation(generation):
    config = PhysicalGenerationConfig.from_record(generation["record"]["config"])
    identity, metadata = config.generation_identity()
    if generation["physical_generation_identity"] != identity or generation["physical_generation"] != json.loads(json.dumps(metadata)):
        raise ValueError("model or physical generation identity mismatch")
    files = [Path(__file__).parents[1] / "diffusion/plate_td_backend.py",
             Path(__file__).parents[1] / "diffusion/plate_td_conditioning.py",
             Path(__file__).with_name("tectonic_product.py"), Path(__file__),
             Path(__file__).with_name("coastal_terrain.py"),
             Path(__file__).with_name("coastal_archipelago.py"),
             Path(__file__).parents[1] / "diffusion/geographic_noise.py"]
    _validate_model(config, metadata)
    if generation["source_sha256"] != {p.name: digest(p) for p in files}:
        raise ValueError("source implementation identity mismatch")


def _macro(product, origin, side):
    out = np.empty((side, side), np.float32)
    x = (origin[0] + np.arange(side))[None, :] * 30.0
    for start in range(0, side, 32):
        z = (origin[1] + np.arange(start, min(start + 32, side)))[:, None] * 30.0
        out[start:start + len(z)] = product.sample(x, z, outside="reject")["elevation_m"]
    return out


def prepare(source, output, origin, side, config, *, compose_coast, expected_identity, relief_strength=0.0):
    """Run real TD and stage a new directory; never overwrite an existing product."""
    if type(compose_coast) is not bool or type(relief_strength) not in (int, float) or not math.isfinite(relief_strength) or not 0 <= relief_strength <= 1 or (not compose_coast and relief_strength != 0):
        raise ValueError("invalid coastal relief strength")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    if type(side) is not int or not 1 <= side <= 1337 or len(origin) != 2 or any(type(v) is not int for v in origin):
        raise ValueError("invalid source window")
    if compose_coast and side <= 400:
        raise ValueError("coastal product needs 200 cells of support on each side")
    # Conservative bounded working set, separate from worker's existing 4 GiB cap.
    estimated = 300_000_000 + side * side * 160
    if psutil.virtual_memory().available < estimated:
        raise ValueError("insufficient available host memory for staging")
    parent = output.parent.resolve()
    if not parent.is_dir() or shutil.disk_usage(parent).free < 100_000_000 + side * side * 50:
        raise ValueError("missing parent or insufficient disk space")
    product = load_product(source, expected_identity=expected_identity)
    # Verify extent before starting a GPU worker.
    product.sample(np.array([origin[0], origin[0] + side - 1]) * 30.,
                   np.array([origin[1], origin[1] + side - 1]) * 30., outside="reject")
    _, model_metadata = config.generation_identity()
    _validate_model(config, model_metadata)
    raw, climate, generation = generate(source, origin, side, config, expected_identity=expected_identity)
    macro = _macro(product, origin, side)
    arrays = {"raw_td": raw, "td_climate": climate, "macro": macro}
    parameters = asdict(CoastalParameters())
    anchor = None
    if compose_coast:
        # Anchors are certified by the frozen macro ocean mask, then checked wet
        # on the composed bed. Choose deterministically within the valid core.
        x = (origin[0] + np.arange(200, side - 200))[None, :] * 30.
        z = (origin[1] + np.arange(200, side - 200))[:, None] * 30.
        connected = product.sample(x, z, outside="reject")["ocean_connected"]
        candidates = np.argwhere(connected & (macro[200:-200, 200:-200] < 0))
        if not len(candidates):
            raise ValueError("no certified ocean anchor in valid core")
        macro_anchor = tuple((candidates[0] + 200).tolist())
        params = CoastalParameters()
        support = coastal_support(macro, params, anchors=[macro_anchor])
        bed = compose(raw, macro, params, support=support)
        margin = 200 - params.validate()
        valid = np.ones(bed.shape, dtype=bool)
        valid[:margin, :] = valid[-margin:, :] = False
        valid[:, :margin] = valid[:, -margin:] = False
        relief_array = relief(bed, valid, support[96:-96, 96:-96],
                              ((origin[0] + 96) * 30., (origin[1] + 96) * 30.), strength=relief_strength)
        bed = (bed + relief_array).astype(np.float32)
        arrays["relief"] = relief_array
        for candidate in candidates:
            az, ax = (candidate + margin).tolist()
            if bed[az, ax] < 0:
                anchor = [az, ax]
                break
        if anchor is None:
            raise ValueError("no certified ocean anchor remains wet in final bed")
        codes, shore = classify(bed, valid, [anchor])
        arrays.update(bed=bed, valid=valid, classification=codes, shoreline=shore)
    tmp = Path(tempfile.mkdtemp(prefix=".plate-td-", dir=parent))
    try:
        hashes = {}
        for name, array in arrays.items():
            np.save(tmp / (name + ".npy"), array, allow_pickle=False)
            hashes[name] = digest(tmp / (name + ".npy"))
        manifest = {"schema": "plate-td-source-v1", "source_path": str(Path(source).resolve()),
                    "plate_identity": expected_identity, "world_seed": WORLD_SEED,
                    "origin_native_xz": list(origin), "source_shape_zx": [side, side],
                    "spacing_m": 30, "sea_m": 0, "generation": generation,
                    "parameters": parameters, "coastal": compose_coast, "relief_strength": relief_strength, "anchor_bed_zx": anchor,
                    "bed_origin_native_xz": [origin[0] + 96, origin[1] + 96] if compose_coast else None,
                    "valid_margin_bed_cells": 104 if compose_coast else None,
                    "climate_support_note": "TD climate; conditioning uses approximate rebase of clipped physical climate, retaining procedural maritime and orographic terms. No tectonic wind model or 22.5km downstream halo claimed.",
                    "files": hashes}
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
    identity = manifest.pop("identity")
    if identity != _identity(manifest) or (expected_identity is not None and identity != expected_identity):
        raise ValueError("manifest identity mismatch")
    manifest["identity"] = identity
    if (manifest["schema"] != "plate-td-source-v1" or manifest["world_seed"] != WORLD_SEED or manifest["spacing_m"] != 30 or manifest["sea_m"] != 0 or type(manifest["coastal"]) is not bool or len(manifest["origin_native_xz"]) != 2 or any(type(v) is not int for v in manifest["origin_native_xz"]) or manifest["parameters"] != asdict(CoastalParameters())):
        raise ValueError("source contract mismatch")
    strength = manifest["relief_strength"]
    if type(strength) not in (int, float) or not math.isfinite(strength) or not 0 <= strength <= 1 or (not manifest["coastal"] and strength != 0):
        raise ValueError("invalid relief strength")
    if not manifest["coastal"] and any(manifest[k] is not None for k in ("anchor_bed_zx", "bed_origin_native_xz", "valid_margin_bed_cells")):
        raise ValueError("unexpected coastal metadata")
    record = manifest["generation"]["record"]
    if (record["source"] != manifest["source_path"] or record["plate_identity"] != manifest["plate_identity"] or record["seed"] != WORLD_SEED or record["origin"] != manifest["origin_native_xz"] or record["side"] != manifest["source_shape_zx"][0]):
        raise ValueError("generation record mismatch")
    _check_generation(manifest["generation"])
    names = {"raw_td", "td_climate", "macro"}
    if manifest["coastal"]:
        names |= {"bed", "valid", "classification", "shoreline", "relief"}
    if set(manifest["files"]) != names:
        raise ValueError("wrong product files")
    arrays = {}
    for name in names:
        file = path / (name + ".npy")
        if digest(file) != manifest["files"][name]:
            raise ValueError("array hash mismatch")
        arrays[name] = np.load(file, mmap_mode="r", allow_pickle=False)
    side, cols = manifest["source_shape_zx"]
    if type(side) is not int or side != cols or not 1 <= side <= 1337 or arrays["raw_td"].shape != (side, side) or arrays["macro"].shape != (side, side) or arrays["td_climate"].shape != (5, side, side):
        raise ValueError("source shape mismatch")
    for name in ("raw_td", "macro", "td_climate"):
        if arrays[name].dtype != np.float32 or not np.isfinite(arrays[name]).all():
            raise ValueError("invalid source array")
    product = load_product(manifest["source_path"], expected_identity=manifest["plate_identity"])
    if product.manifest["config"]["world_seed"] != WORLD_SEED:
        raise ValueError("plate seed mismatch")
    origin = manifest["origin_native_xz"]
    if not np.array_equal(arrays["macro"], _macro(product, origin, side)):
        raise ValueError("macro source mismatch")
    if manifest["coastal"]:
        params = CoastalParameters(**manifest["parameters"])
        if side <= 400 or manifest["valid_margin_bed_cells"] != 104 or params != CoastalParameters() or manifest["bed_origin_native_xz"] != [v + 96 for v in manifest["origin_native_xz"]]:
            raise ValueError("coastal coordinates or parameters mismatch")
        shape = (side - 192, side - 192)
        if any(arrays[name].shape != shape for name in ("bed", "valid", "classification", "shoreline", "relief")) or arrays["relief"].dtype != np.float32 or not np.isfinite(arrays["relief"]).all():
            raise ValueError("invalid coastal array shapes or relief")
        if (arrays["bed"].shape != (side - 192, side - 192) or arrays["bed"].dtype != np.float32 or not np.isfinite(arrays["bed"]).all() or arrays["valid"].dtype != np.bool_ or arrays["classification"].dtype != np.uint8 or arrays["shoreline"].dtype != np.bool_):
            raise ValueError("invalid coastal arrays")
        valid = np.ones((side - 192, side - 192), bool)
        valid[:104, :] = valid[-104:, :] = False
        valid[:, :104] = valid[:, -104:] = False
        if not np.array_equal(arrays["valid"], valid):
            raise ValueError("invalid support")
        x = (origin[0] + np.arange(200, side - 200))[None, :] * 30.
        z = (origin[1] + np.arange(200, side - 200))[:, None] * 30.
        connected = product.sample(x, z, outside="reject")["ocean_connected"]
        candidates = np.argwhere(connected & (arrays["macro"][200:-200, 200:-200] < 0))
        if not len(candidates):
            raise ValueError("missing macro ocean anchor")
        macro_anchor = tuple((candidates[0] + 200).tolist())
        support = coastal_support(arrays["macro"], params, anchors=[macro_anchor])
        expected_bed = compose(arrays["raw_td"], arrays["macro"], params, support=support)
        expected_relief = relief(expected_bed, valid, support[96:-96, 96:-96],
                                 ((origin[0] + 96) * 30., (origin[1] + 96) * 30.), strength=strength)
        if not np.array_equal(expected_relief, arrays["relief"]):
            raise ValueError("relief derivation mismatch")
        expected_bed = (expected_bed + expected_relief).astype(np.float32)
        if not np.array_equal(expected_bed, arrays["bed"]):
            raise ValueError("bed derivation mismatch")
        anchor = manifest["anchor_bed_zx"]
        if not any(np.array_equal(candidate + 104, anchor) for candidate in candidates):
            raise ValueError("anchor is not certified macro ocean")
        codes, shore = classify(arrays["bed"], valid, [manifest["anchor_bed_zx"]])
        if not np.array_equal(codes, arrays["classification"]) or not np.array_equal(shore, arrays["shoreline"]):
            raise ValueError("classification mismatch")
    return manifest, arrays
