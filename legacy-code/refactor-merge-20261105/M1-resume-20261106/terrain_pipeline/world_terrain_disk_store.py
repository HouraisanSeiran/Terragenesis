"""Disk-backed preparation and immutable tiled publication for large regions."""
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.world_terrain_store import _atomic_json, _bounds, _touch, _union
from terrain_pipeline.world_river_network_io import verify_network

TILE_SIDE = 512
REVISION = "disk-irregular-network-water-v2"


def tiles(origin, shape):
    for z in range(0, shape[0], TILE_SIDE):
        for x in range(0, shape[1], TILE_SIDE):
            yield [origin[0] + x, origin[1] + z], [min(TILE_SIDE, shape[0] - z), min(TILE_SIDE, shape[1] - x)]


def open_registry(path, spec, source_family, forcing, sigma):
    world = {"layout": spec.parameters(), "layout_identity": spec.identity(), "source_family": source_family,
             "forcing": forcing, "sigma_cells": sigma, "revision": REVISION}
    world_id = identity({}, world)
    registry_path = Path(path) / "registry.json"
    if registry_path.exists():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        if registry.get("world_identity") != world_id or registry.get("world") != world:
            raise ValueError("world or algorithm identity mismatch; use a new store directory")
        return registry
    return {"schema": "world-terrain-disk-store-v1", "world": world, "world_identity": world_id,
            "pages": [], "components": [], "prepared_cells": 0, "world_cells": 409600 ** 2}


def plan(registry, origin, shape):
    bounds = _bounds(origin, shape)
    selected = []
    while True:
        added = [c for c in registry["components"] if c not in selected and _touch(bounds, c["bounds"])]
        if not added:
            break
        for c in added:
            selected.append(c)
            bounds = _union(bounds, c["bounds"])
    hit = next((c for c in selected if c["bounds"][0] <= origin[0] and c["bounds"][1] <= origin[1]
                and c["bounds"][2] >= origin[0] + shape[1] and c["bounds"][3] >= origin[1] + shape[0]), None)
    return {"bounds": bounds, "origin_native_xz": bounds[:2],
            "shape_zx": [bounds[3] - bounds[1], bounds[2] - bounds[0]], "selected": selected, "hit": hit}


def _sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(path, registry, request, pages, spec, *, compose, solve, disk_budget_gib=8.):
    if request["hit"]:
        root, manifest = read_manifest(path, request["hit"], registry["world_identity"])
        for tile in manifest["composition_tiles"] + manifest["water_tiles"]:
            if _sha(root / tile["file"]) != tile["sha256"]:
                raise ValueError("disk region tile identity mismatch")
        return request["hit"]
    root = Path(path)
    versions = root / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    origin, shape = request["origin_native_xz"], request["shape_zx"]
    if not np.isfinite(disk_budget_gib) or disk_budget_gib <= 0:
        raise ValueError("disk budget must be positive and finite")
    estimated = shape[0] * shape[1] * 512
    if estimated > disk_budget_gib * 1024 ** 3 or estimated > shutil.disk_usage(versions).free:
        raise ValueError("estimated disk requirement exceeds budget or available space")
    world = registry["world"]
    with tempfile.TemporaryDirectory(prefix=".disk-region-", dir=versions) as temporary:
        staging = Path(temporary) / "product"
        staging.mkdir()
        height = np.lib.format.open_memmap(staging / "height.npy", mode="w+", dtype="float64", shape=tuple(shape))
        ocean = None
        composition_tiles = []
        try:
            ocean = np.lib.format.open_memmap(staging / "ocean.npy", mode="w+", dtype="bool", shape=tuple(shape))
            for tile_origin, tile_shape in tiles(origin, shape):
                product = compose(spec, pages, tile_origin, tile_shape, sigma_cells=world["sigma_cells"],
                                  source_family=world["source_family"])
                z, x = tile_origin[1] - origin[1], tile_origin[0] - origin[0]
                sl = np.s_[z:z + tile_shape[0], x:x + tile_shape[1]]
                height[sl] = product["composed_elevation_m"]
                ocean[sl] = product["ocean_mask"] if product["ocean_mask"] is not None else False
                name = "composition-%d-%d.npz" % (tile_origin[0], tile_origin[1])
                np.savez_compressed(staging / name, **{k: v for k, v in product.items() if k != "metadata" and v is not None})
                composition_tiles.append({"origin_native_xz": tile_origin, "shape_zx": tile_shape,
                                          "file": name, "sha256": _sha(staging / name), "metadata": product["metadata"]})
            height.flush()
            ocean.flush()
        finally:
            height._mmap.close()
            if ocean is not None:
                ocean._mmap.close()
        water = solve(staging / "height.npy", staging / "ocean.npy", staging / "water",
                      origin_native_xz=origin, world_seed=20261020, **world["forcing"])
        fields = {}
        try:
            for name, file in water["fields"].items():
                fields[name] = np.load(staging / "water" / file, mmap_mode="r", allow_pickle=False)
            if not fields:
                raise ValueError("water fields are empty")
            if any(field.shape != tuple(shape) for field in fields.values()):
                raise ValueError("water field shape mismatch")
            water_tiles = []
            for tile_origin, tile_shape in tiles(origin, shape):
                z, x = tile_origin[1] - origin[1], tile_origin[0] - origin[0]
                sl = np.s_[z:z + tile_shape[0], x:x + tile_shape[1]]
                name = "water-%d-%d.npz" % tuple(tile_origin)
                np.savez_compressed(staging / name, **{key: value[sl] for key, value in fields.items()})
                water_tiles.append({"origin_native_xz": tile_origin, "shape_zx": tile_shape,
                                    "file": name, "sha256": _sha(staging / name)})
        finally:
            for field in fields.values():
                field._mmap.close()
        manifest = {"schema": "world-terrain-disk-region-v1", "world_identity": registry["world_identity"],
                    "origin_native_xz": origin, "shape_zx": shape, "composition_tiles": composition_tiles,
                    "water_tiles": water_tiles, "water_metadata": water["metadata"]}
        if water.get("network") is not None:
            network = dict(water["network"])
            network["file"] = "water/" + network["file"]
            verify_network(staging, network)
            manifest["network"] = network
        manifest["identity_sha256"] = identity({}, manifest)
        (staging / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
        version = uuid.uuid4().hex
        staging.rename(versions / version)
    component = {"version": version, "bounds": request["bounds"], "identity_sha256": manifest["identity_sha256"]}
    updated = dict(registry)
    updated["components"] = [c for c in registry["components"] if c not in request["selected"]] + [component]
    updated["pages"] = pages
    updated["prepared_cells"] = sum((c["bounds"][2] - c["bounds"][0]) * (c["bounds"][3] - c["bounds"][1]) for c in updated["components"])
    _atomic_json(root / "registry.json", updated)
    registry.update(updated)
    return component


def read_manifest(path, component, world_identity):
    root = Path(path) / "versions" / component["version"]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest.pop("identity_sha256")
    if manifest["world_identity"] != world_identity or expected != component["identity_sha256"] or identity({}, manifest) != expected:
        raise ValueError("disk region identity mismatch")
    if manifest.get("network") is not None:
        verify_network(root, manifest["network"])
    return root, manifest
