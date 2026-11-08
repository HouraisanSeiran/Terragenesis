"""Persistent finite-world regions, recomputed together when they meet."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.world_water_layout import LayoutSpec
from terrain_pipeline.world_river_network_io import verify_network, write_network

MAX_CELLS = 1048576
WORLD_CELLS = 409600 ** 2
PREPARATION_REVISION = "connected-irregular-network-water-v3"


def make_spec(preset, water=None):
    if water is None:
        water = {"lakes": .12, "earth": .62, "archipelago": .8}[preset]
    return LayoutSpec(preset, water, world_seed=20261020, layout_id="large-world-first-pass",
                      mode="finite", frame_origin_m=(0., 0.), frame_side_m=12_288_000.)


def _bounds(origin, shape):
    if (len(origin) != 2 or len(shape) != 2 or any(type(v) is not int for v in (*origin, *shape))
            or any(v <= 0 for v in shape)):
        raise ValueError("origin and shape must be integer pairs with positive shape")
    x, z = origin
    rows, cols = shape
    if x < 0 or z < 0 or x + cols > 409600 or z + rows > 409600:
        raise ValueError("region outside finite world")
    return [x, z, x + cols, z + rows]


def _touch(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def _covered_area(rectangles):
    edges = sorted({x for b in rectangles for x in (b[0], b[2])})
    area = 0
    for left, right in zip(edges, edges[1:]):
        spans = sorted((b[1], b[3]) for b in rectangles if b[0] < right and b[2] > left)
        end = None
        for start, stop in spans:
            if end is None or start > end:
                area += (right - left) * (stop - start)
                end = stop
            elif stop > end:
                area += (right - left) * (stop - end)
                end = stop
    return area


def _atomic_json(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".registry-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def open_registry(path, spec, source_family, forcing, sigma_cells=6.):
    if not isinstance(source_family, str) or not source_family:
        raise ValueError("source_family is required")
    world = {"layout_identity": spec.identity(), "layout": spec.parameters(),
             "source_family": source_family, "forcing": forcing, "sigma_cells": sigma_cells,
             "preparation_revision": PREPARATION_REVISION}
    world_id = identity({}, world)
    path = Path(path)
    if (path / "registry.json").exists():
        registry = json.loads((path / "registry.json").read_text(encoding="utf-8"))
        if registry.get("world", {}).get("preparation_revision") != PREPARATION_REVISION:
            raise ValueError("preparation algorithm revision differs; use a new store directory")
        if registry["world_identity"] != world_id or registry["world"] != world:
            raise ValueError("world identity mismatch")
        return registry
    return {"schema": "world-terrain-store-v1", "world": world, "world_identity": world_id,
            "pages": [], "source_bounds": [], "source_support_cells": 0,
            "components": [], "prepared_cells": 0, "world_cells": WORLD_CELLS}


def plan(registry, origin, shape, pages, coverage):
    bounds = _bounds(origin, shape)
    selected = []
    while True:
        added = [component for component in registry["components"]
                 if component not in selected and _touch(bounds, component["bounds"])]
        if not added:
            break
        for component in added:
            selected.append(component)
            bounds = _union(bounds, component["bounds"])
    rows, cols = bounds[3] - bounds[1], bounds[2] - bounds[0]
    if rows * cols > MAX_CELLS:
        raise ValueError("connected support exceeds 1048576 cells; a larger-domain solution is required")
    hit = next((item for item in selected if item["bounds"][0] <= origin[0]
                and item["bounds"][1] <= origin[1] and item["bounds"][2] >= origin[0] + shape[1]
                and item["bounds"][3] >= origin[1] + shape[0]), None)
    missing = ({"missing_cells": 0} if hit is not None else
               coverage([bounds[0], bounds[1]], [rows, cols], pages))
    return {"bounds": bounds, "origin_native_xz": bounds[:2], "shape_zx": [rows, cols],
            "selected": selected, "hit": hit, "coverage": missing}


def read_component(path, component, world_identity):
    root = Path(path) / "versions" / component["version"]
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    with np.load(root / "arrays.npz", allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    expected = metadata.pop("identity_sha256")
    if metadata["world_identity"] != world_identity or expected != component["identity_sha256"]:
        raise ValueError("component world or registry identity mismatch")
    if any(a.shape != tuple(metadata["shape_zx"]) for a in arrays.values()):
        raise ValueError("component shape mismatch")
    if identity(arrays, metadata) != expected:
        raise ValueError("component identity mismatch")
    if metadata.get("network") is not None:
        verify_network(root, metadata["network"])
    return arrays, metadata


def prepare(path, registry, request, pages, spec, *, compose, form, render):
    if request["hit"] is not None:
        read_component(path, request["hit"], registry["world_identity"])
        return request["hit"]
    if request["coverage"]["missing_cells"]:
        raise ValueError("source coverage missing; generate or register source pages first")
    world = registry["world"]
    origin, shape = request["origin_native_xz"], request["shape_zx"]
    composition = compose(spec, pages, origin, shape, sigma_cells=world["sigma_cells"],
                          max_cells=MAX_CELLS, source_family=world["source_family"])
    water = form(composition, origin, world_seed=20261020, **world["forcing"])
    arrays = {k: v for k, v in composition.items() if k != "metadata" and v is not None}
    arrays.update(water["arrays"])
    metadata = {"schema": "world-terrain-region-v1", "world_identity": registry["world_identity"],
                "origin_native_xz": origin, "shape_zx": shape, "composition": composition["metadata"],
                "water": water["metadata"], "water_identity": water["identity_sha256"],
                "stages": ["macro", "td_source", "composition", "water_and_bed"]}
    version = uuid.uuid4().hex
    root = Path(path)
    (root / "versions").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".region-", dir=root / "versions") as temp:
        staging = Path(temp) / "product"
        staging.mkdir()
        network = water.get("network")
        if network is not None:
            metadata["network"] = write_network(staging, network, water["metadata"].get("network", {}))
        digest = identity(arrays, metadata)
        np.savez_compressed(staging / "arrays.npz", **arrays)
        (staging / "metadata.json").write_text(json.dumps({**metadata, "identity_sha256": digest},
            sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
        render_arrays = arrays if network is None else {**arrays, "__river_network__": network}
        render(render_arrays, origin, staging / "stages.png")
        staging.rename(root / "versions" / version)
    component = {"version": version, "bounds": request["bounds"], "identity_sha256": digest}
    updated = dict(registry)
    updated["components"] = [c for c in registry["components"] if c not in request["selected"]] + [component]
    updated["pages"] = pages
    existing = {item["path"]: item for item in registry["source_bounds"]}
    for item in request["coverage"].get("sources", []):
        existing[item["path"]] = {"path": item["path"], "sha256": item["sha256"],
                                  "bounds": item["trusted_bounds_native_xz"]}
    updated["source_bounds"] = list(existing.values())
    clipped = [[max(0, b[0]), max(0, b[1]), min(409600, b[2]), min(409600, b[3])]
               for b in (item["bounds"] for item in updated["source_bounds"])]
    updated["source_support_cells"] = _covered_area([b for b in clipped if b[0] < b[2] and b[1] < b[3]])
    updated["prepared_cells"] = sum((b["bounds"][2] - b["bounds"][0]) *
                                    (b["bounds"][3] - b["bounds"][1]) for b in updated["components"])
    _atomic_json(root / "registry.json", updated)
    registry.update(updated)
    return component
