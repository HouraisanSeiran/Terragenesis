"""Explicit, bounded, generation-free surface network tile storage."""

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import zipfile
import uuid
from types import MappingProxyType

import numpy as np

from terrain_pipeline.artifacts.contracts import canonical_json, digest
from terrain_pipeline.surface_network_consumer import (
    GEOMETRY, GRAPH, _file_hash, _freeze, _immutable, _reject_link_chain, _world_index,
    load_surface_network_delivery,
)


VERSION = "surface-network-tiles-v1"
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_WINDOW_CELLS = 65536
MAX_CACHE_BYTES = 64 * 1024 * 1024
MAX_TILE_CELLS = 65536
MAX_TILES = 100000
MAX_SOURCE_BYTES = 512 * 1024 * 1024
SOURCE_FILES = {'manifest.json', 'hydro.npz', 'base/manifest.json', 'base/arrays.npz',
                'derived/manifest.json', 'derived/arrays.npz'}


def _plain(value):
    if isinstance(value, (dict, MappingProxyType)):
        return {key: _plain(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(child) for child in value]
    return value


def _tile_size(tile_cells):
    if type(tile_cells) is not int or not 1 <= tile_cells <= 255 or (tile_cells + 1) ** 2 > MAX_TILE_CELLS:
        raise ValueError('invalid square tile cell span')


def _bounded_hash(path, limit=MAX_FILE_BYTES):
    _reject_link_chain(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('missing or oversized array file')
    return _file_hash(path)


def _records(records, fields, shape=None):
    if set(records) != fields:
        raise ValueError('array fields mismatch')
    total_bytes = 0
    for name, record in records.items():
        if set(record) != {'dtype', 'shape', 'sha256'}:
            raise ValueError('invalid array record')
        dimensions = record['shape']
        if (not isinstance(dimensions, (list, tuple)) or not dimensions or
                any(type(count) is not int or count < 1 for count in dimensions) or
                (shape is not None and tuple(dimensions) != tuple(shape))):
            raise ValueError('invalid array dimensions')
        dtype = np.dtype(record['dtype'])
        if dtype.hasobject or dtype.kind not in 'bifu' or dtype.itemsize > 8:
            raise ValueError('invalid array dtype')
        if name.endswith('mask') and dtype != np.dtype(bool):
            raise ValueError('invalid mask dtype')
        if name in ('receiver', 'order') and dtype.kind not in 'iu':
            raise ValueError('graph indices must be integers')
        if not isinstance(record['sha256'], str) or len(record['sha256']) != 64:
            raise ValueError('invalid array hash')
        total_bytes += math.prod(dimensions) * dtype.itemsize
    if total_bytes > MAX_FILE_BYTES:
        raise ValueError('array byte bound exceeded')


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("nonfinite JSON constant")


def _json(path):
    if not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("missing or oversized manifest")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                      parse_constant=_invalid_constant)


def _write_json(path, value):
    data = canonical_json(value)
    if len(data.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds bound")
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _record(array):
    return {"dtype": array.dtype.str, "shape": list(array.shape),
            "sha256": hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()}


def _read_arrays(path, records, limit=MAX_FILE_BYTES):
    _records(records, set(records))
    _reject_link_chain(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError("missing or oversized array file")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if sum(entry.file_size for entry in entries) > limit:
            raise ValueError('total uncompressed array byte bound exceeded')
        if len(entries) != len(records) or {entry.filename for entry in entries} != {name + ".npy" for name in records}:
            raise ValueError("array members mismatch")
        for entry in entries:
            record = records[entry.filename[:-4]]
            if entry.file_size > limit or entry.compress_type != zipfile.ZIP_STORED:
                raise ValueError("array exceeds bound or is compressed")
            with archive.open(entry) as stream:
                version = np.lib.format.read_magic(stream)
                if version not in ((1, 0), (2, 0)):
                    raise ValueError("unsupported array header")
                reader = (np.lib.format.read_array_header_1_0 if version == (1, 0)
                          else np.lib.format.read_array_header_2_0)
                shape, fortran, dtype = reader(stream, max_header_size=10000)
                if (fortran or dtype.kind not in "bifu" or dtype.hasobject or tuple(shape) != tuple(record["shape"]) or
                        dtype.str != record["dtype"] or math.prod(shape) * dtype.itemsize != entry.file_size - stream.tell()):
                    raise ValueError("array header mismatch")
        with np.load(path, allow_pickle=False) as archive:
            arrays = {name: _immutable(archive[name]) for name in records}
    if {name: _record(array) for name, array in arrays.items()} != _plain(records):
        raise ValueError("array payload mismatch")
    return MappingProxyType(arrays)


def _geometry(arrays, grid, bounds, source_manifest, graph):
    z0, z1, x0, x1 = bounds
    shape = (z1 - z0, x1 - x0)
    if set(arrays) != GEOMETRY or any(array.shape != shape for array in arrays.values()):
        raise ValueError("tile geometry fields or shape mismatch")
    if any(arrays[name].dtype != bool for name in GEOMETRY if name.endswith("mask")):
        raise ValueError("invalid mask type")
    if any(not np.isfinite(arrays[name]).all() for name in GEOMETRY if not name.endswith("mask")):
        raise ValueError("nonfinite geometry")
    h0, h1, h2 = (arrays[name] for name in ("source_surface_m", "valley_surface_m", "final_surface_m"))
    for name, expected in (("valley_cut_m", h0 - h1), ("bed_cut_m", h1 - h2),
                           ("total_cut_m", h0 - h2)):
        if np.any(arrays[name] < -1e-9) or not np.allclose(arrays[name], expected, rtol=0, atol=1e-9):
            raise ValueError("H0/H1/H2 cut mismatch")
    wet, water = arrays["wet_mask"], arrays["water_surface_m"]
    domain, protected, legal = (arrays[name] for name in ("domain_mask", "protected_mask", "legal_outlet_mask"))
    if (np.any(water[~wet] != 0) or np.any(water[wet] <= h2[wet]) or
            np.any((wet | (arrays["total_cut_m"] > 1e-9) | legal) & (~domain | protected))):
        raise ValueError("invalid water, domain or protected geometry")
    rows, columns = grid["shape_zx"]
    boundary = np.zeros(shape, bool)
    if z0 == 0:
        boundary[0] = True
    if z1 == rows:
        boundary[-1] = True
    if x0 == 0:
        boundary[:, 0] = True
    if x1 == columns:
        boundary[:, -1] = True
    if np.any(wet & boundary & ~legal):
        raise ValueError("undeclared wet boundary")
    inputs = source_manifest['proof']['inputs']
    if (np.any(arrays['bed_cut_m'] > inputs['budget']['max_bed_cut_m'] + 1e-9) or
            np.any(arrays['valley_cut_m'] > inputs['valley_recipe']['max_valley_depth_m'] + 1e-9)):
        raise ValueError('actual tile cut exceeds original depth budget')
    minimum_depth = inputs['inundation_recipe']['min_water_depth_m']
    if np.any(wet & (water - h2 < minimum_depth - 1e-9)):
        raise ValueError('actual wet depth below original minimum')
    threshold = max(.5, minimum_depth * 10)
    for axis in (0, 1):
        before = (slice(None, -1), slice(None)) if axis == 0 else (slice(None), slice(None, -1))
        after = (slice(1, None), slice(None)) if axis == 0 else (slice(None), slice(1, None))
        if np.any(wet[before] & wet[after] & (np.abs(water[before] - water[after]) > threshold + 1e-9)):
            raise ValueError('adjacent wet stage transition exceeds original threshold')
    positions = graph['world_xz_m']
    columns = np.rint((positions[:, 0] - grid['origin_x_m']) / grid['spacing_x_m']).astype(int)
    rows = np.rint((positions[:, 1] - grid['origin_z_m']) / grid['spacing_z_m']).astype(int)
    inside = (rows >= z0) & (rows < z1) & (columns >= x0) & (columns < x1)
    active = graph['active_mask']
    selected = inside & active
    local_rows, local_columns = rows[selected] - z0, columns[selected] - x0
    if (not np.all(wet[local_rows, local_columns]) or
            not np.allclose(water[local_rows, local_columns], graph['node_stage_m'][selected], atol=1e-8, rtol=0)):
        raise ValueError('tile active node wet/stage differs from graph')
    outlets = inside & active & graph['outlet_mask']
    if not np.all(legal[rows[outlets] - z0, columns[outlets] - x0]):
        raise ValueError('tile active outlet lacks legal boundary')
    for donor in np.flatnonzero(active & (graph['receiver'] >= 0)):
        target = int(graph['receiver'][donor])
        if (max(rows[donor], rows[target]) < z0 or min(rows[donor], rows[target]) >= z1 or
                max(columns[donor], columns[target]) < x0 or min(columns[donor], columns[target]) >= x1):
            continue
        steps = max(abs(rows[target] - rows[donor]), abs(columns[target] - columns[donor]))
        previous_bed = None
        for step in range(steps + 1):
            fraction = step / steps
            row = int(round(rows[donor] + fraction * (rows[target] - rows[donor])))
            column = int(round(columns[donor] + fraction * (columns[target] - columns[donor])))
            if not (z0 <= row < z1 and x0 <= column < x1):
                previous_bed = None
                continue
            row -= z0
            column -= x0
            stage = graph['node_stage_m'][donor] * (1 - fraction) + graph['node_stage_m'][target] * fraction
            depth = stage - h2[row, column]
            if (not wet[row, column] or depth < inputs['stage_recipe']['min_clearance_m'] - 1e-9 or
                    depth > inputs['stage_recipe']['max_depth_m'] + 1e-9 or
                    (previous_bed is not None and h2[row, column] > previous_bed + 1e-9)):
                raise ValueError('tile channel edge is dry, blocked or reverse-sloped')
            previous_bed = h2[row, column]


def _tile_specs(grid, tile_cells):
    rows, columns = grid["shape_zx"]
    for z0 in range(0, rows - 1, tile_cells):
        for x0 in range(0, columns - 1, tile_cells):
            yield [z0, min(z0 + tile_cells + 1, rows), x0, min(x0 + tile_cells + 1, columns)]


def _source_files(source, staging, source_manifest):
    copied = staging / "source"
    _reject_link_chain(copied)
    declared = {'manifest.json': _file_hash(source / 'manifest.json'), **source_manifest['files']}
    if set(declared) != SOURCE_FILES:
        raise ValueError('unexpected source delivery file set')
    total_bytes = 0
    for name in declared:
        path = source / name
        _reject_link_chain(path)
        if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError('source file exceeds bound')
        total_bytes += path.stat().st_size
    if total_bytes > MAX_SOURCE_BYTES:
        raise ValueError('source total byte bound exceeded')
    copied.mkdir(exist_ok=True)
    for name, expected in declared.items():
        path = copied / name
        _reject_link_chain(path)
        path.parent.mkdir(exist_ok=True)
        if path.exists():
            if _file_hash(path) != expected:
                raise ValueError('staged source file differs')
        else:
            shutil.copyfile(source / name, path)
        if _file_hash(path) != expected:
            raise ValueError('source file changed during copy')
    return copied


def _prepare_unlocked(source_path, destination_path, *, tile_cells=64,
                      max_tiles=None, cancel=None, resume=False):
    """Return False when paused; return destination after a complete atomic publication."""
    source, destination = Path(source_path), Path(destination_path)
    staging = destination.with_name(destination.name + ".staging")
    for path in (source, destination, staging):
        _reject_link_chain(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir() or source.resolve() == staging.resolve():
        raise ValueError("invalid source or destination")
    _tile_size(tile_cells)
    if max_tiles is not None and (type(max_tiles) is not int or max_tiles < 1):
        raise ValueError("invalid work budget")
    delivery = load_surface_network_delivery(source)
    source_manifest = _json(source / 'manifest.json')
    grid = source_manifest["grid"]
    if math.ceil((grid['shape_zx'][0] - 1) / tile_cells) * math.ceil((grid['shape_zx'][1] - 1) / tile_cells) > MAX_TILES:
        raise ValueError('tile count bound exceeded')
    specs = list(_tile_specs(grid, tile_cells))
    recipe = {"tile_cells": tile_cells, "grid": grid, "source_content_id": source_manifest["content_id"],
              "source_manifest": source_manifest, "source_manifest_sha256": _file_hash(source / "manifest.json"),
              'source_windows': [{field: _record(delivery['geometry'][field][bounds[0]:bounds[1], bounds[2]:bounds[3]])
                                  for field in GEOMETRY} for bounds in specs]}
    if (staging / "progress.json").exists():
        if not resume:
            raise FileExistsError(staging)
        progress = _json(staging / "progress.json")
        (staging / "manifest.json").unlink(missing_ok=True)
        if progress["recipe"] != recipe or progress["bounds"] != specs:
            raise ValueError("resume source or recipe changed")
    else:
        if resume:
            raise FileNotFoundError(staging)
        staging.mkdir(exist_ok=True)
        (staging / "tiles").mkdir()
        (staging / 'proof').mkdir()
        progress = {"recipe": recipe, "bounds": specs, "completed": {}}
        _write_json(staging / "progress.json", progress)
    copied = _source_files(source, staging, source_manifest)
    if _file_hash(copied / "manifest.json") != recipe["source_manifest_sha256"]:
        raise ValueError("staged source manifest differs")
    staged_delivery = load_surface_network_delivery(copied)
    if _plain(staged_delivery['manifest']) != source_manifest:
        raise ValueError('staged source identity differs')
    graph_path = staging / "graph.npz"
    if not graph_path.exists():
        np.savez(graph_path, **delivery["centerline"])
    graph_records = {name: _record(array) for name, array in delivery["centerline"].items()}
    graph = _read_arrays(graph_path, graph_records)
    if any(not np.array_equal(graph[name], delivery["centerline"][name]) for name in GRAPH):
        raise ValueError("staged graph differs from source")
    expected_names = {f'{index:06d}.npz': (index, bounds) for index, bounds in enumerate(specs)}
    if set(progress['completed']) - set(expected_names):
        raise ValueError('unexpected completed tile')
    for name, expected in progress['completed'].items():
        path = staging / 'tiles' / name
        _reject_link_chain(path)
        if _bounded_hash(path) != expected['sha256']:
            raise ValueError('completed tile damaged; resume refused')
        index, bounds = expected_names[name]
        arrays = _read_arrays(path, expected['arrays'])
        proof = _read_arrays(staging / 'proof' / name, recipe['source_windows'][index])
        _geometry(arrays, grid, bounds, source_manifest, graph)
        if any(not np.array_equal(arrays[field], proof[field]) or
               not np.array_equal(arrays[field], delivery['geometry'][field][bounds[0]:bounds[1], bounds[2]:bounds[3]]) for field in GEOMETRY):
            raise ValueError('completed tile differs from source; resume refused')
    done = 0
    for index, bounds in enumerate(specs):
        name = f'{index:06d}.npz'
        if name in progress['completed']:
            continue
        if cancel is not None and cancel():
            return False
        if max_tiles is not None and done >= max_tiles:
            return False
        path = staging / "tiles" / name
        _reject_link_chain(path)
        arrays = {field: delivery["geometry"][field][bounds[0]:bounds[1], bounds[2]:bounds[3]] for field in GEOMETRY}
        _geometry(arrays, grid, bounds, source_manifest, graph)
        proof_path = staging / 'proof' / name
        _reject_link_chain(proof_path)
        with proof_path.with_suffix('.tmp').open('wb') as stream:
            np.savez(stream, **arrays)
        os.replace(proof_path.with_suffix('.tmp'), proof_path)
        temporary = path.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            np.savez(stream, **arrays)
        os.replace(temporary, path)
        progress["completed"][name] = {"sha256": _file_hash(path),
                                        "arrays": {field: _record(array) for field, array in arrays.items()}}
        _write_json(staging / "progress.json", progress)
        done += 1
    tiles = [{"path": f"tiles/{index:06d}.npz", "bounds": bounds,
              'proof_sha256': _file_hash(staging / 'proof' / f'{index:06d}.npz'),
              **progress["completed"][f"{index:06d}.npz"]} for index, bounds in enumerate(specs)]
    manifest = {"version": VERSION, "recipe": recipe, "tiles": tiles,
                "graph": {"path": "graph.npz", "sha256": _file_hash(graph_path), "arrays": graph_records},
                "source_files": {name: _file_hash(copied / name) for name in sorted(SOURCE_FILES)},
                "limits": {"max_window_cells": MAX_WINDOW_CELLS, "max_cache_bytes": MAX_CACHE_BYTES,
                           "max_file_bytes": MAX_FILE_BYTES}}
    manifest["content_id"] = digest(manifest)
    if cancel is not None and cancel():
        return False
    _write_json(staging / "manifest.json", manifest)
    if cancel is not None and cancel():
        (staging / "manifest.json").unlink()
        return False
    verify_all_tiles(load_surface_network_tiles(staging, allow_staging=True))
    if cancel is not None and cancel():
        (staging / "manifest.json").unlink()
        return False
    if destination.exists():
        raise FileExistsError(destination)
    os.rename(staging, destination)
    return destination


def prepare_surface_network_tiles(source_path, destination_path, *, tile_cells=64,
                                  max_tiles=None, cancel=None, resume=False):
    """Validate a delivery and prepare bounded tiles; resume uses exclusive staging access."""
    destination = Path(destination_path)
    _tile_size(tile_cells)
    if max_tiles is not None and (type(max_tiles) is not int or max_tiles < 1):
        raise ValueError('invalid work budget')
    if type(resume) is not bool or (cancel is not None and not callable(cancel)):
        raise ValueError('invalid resume/cancel argument')
    staging = destination.with_name(destination.name + ".staging")
    source = Path(source_path).resolve()
    if destination.resolve().is_relative_to(source) or staging.resolve().is_relative_to(source):
        raise ValueError('destination must not be inside the immutable source')
    _reject_link_chain(destination)
    _reject_link_chain(staging)
    if destination.exists():
        raise FileExistsError(destination)
    staging.mkdir(exist_ok=True)
    lock = staging / ".prepare.lock"
    token = uuid.uuid4().hex
    owned = False
    try:
        with lock.open("x") as stream:
            stream.write(token)
        owned = True
        try:
            return _prepare_unlocked(source_path, destination_path, tile_cells=tile_cells,
                                     max_tiles=max_tiles, cancel=cancel, resume=resume)
        except Exception:
            (staging / "manifest.json").unlink(missing_ok=True)
            raise
    finally:
        if owned:
            for candidate in (lock, destination / '.prepare.lock'):
                if candidate.is_file() and candidate.read_text(encoding='utf-8') == token:
                    candidate.unlink()


class SurfaceNetworkTiles:
    def __init__(self, path, manifest, graph):
        self.path = path
        self.manifest = _freeze(manifest)
        self.centerline = graph
        self._cache = {}
        self._cache_bytes = 0

    def _tile(self, index):
        tile = self.manifest["tiles"][index]
        path = self.path / tile["path"]
        _reject_link_chain(path)
        if _bounded_hash(path) != tile["sha256"]:
            raise ValueError("tile file hash mismatch")
        recipe = self.manifest['recipe']
        proof_path = self.path / 'proof' / f'{index:06d}.npz'
        _reject_link_chain(proof_path)
        if _bounded_hash(proof_path) != tile['proof_sha256']:
            raise ValueError('source window file hash mismatch')
        if index in self._cache:
            return self._cache[index]
        size = sum(math.prod(record['shape']) * np.dtype(record['dtype']).itemsize for record in tile['arrays'].values())
        if size > MAX_CACHE_BYTES:
            raise ValueError('tile exceeds cache bound')
        arrays = _read_arrays(path, tile["arrays"])
        proof = _read_arrays(proof_path, recipe['source_windows'][index])
        if any(not np.array_equal(arrays[name], proof[name]) for name in GEOMETRY):
            raise ValueError('tile differs from validated source window')
        _geometry(arrays, recipe['grid'], tile['bounds'], recipe['source_manifest'], self.centerline)
        size = sum(array.nbytes for array in arrays.values())
        if size > MAX_CACHE_BYTES:
            raise ValueError("tile exceeds cache bound")
        if self._cache_bytes + size > MAX_CACHE_BYTES:
            self._cache.clear()
            self._cache_bytes = 0
        self._cache[index] = arrays
        self._cache_bytes += size
        return arrays


def load_surface_network_tiles(path, *, allow_staging=False):
    """Load the index and graph only; tiles are validated when accessed."""
    directory = Path(path)
    _reject_link_chain(directory)
    if not allow_staging and ((directory / ".prepare.lock").exists() or
                              (directory / "progress.json").exists() and directory.name.endswith(".staging")):
        raise ValueError("unfinished tile staging directory")
    manifest = _json(directory / "manifest.json")
    if set(manifest) != {"version", "recipe", "tiles", "graph", "source_files", "limits", "content_id"} or manifest["version"] != VERSION:
        raise ValueError("invalid tile manifest")
    if digest({key: value for key, value in manifest.items() if key != "content_id"}) != manifest["content_id"]:
        raise ValueError("tile manifest identity mismatch")
    recipe = manifest["recipe"]
    if set(recipe) != {'tile_cells', 'grid', 'source_content_id', 'source_manifest', 'source_manifest_sha256', 'source_windows'}:
        raise ValueError("invalid tile recipe")
    source_manifest = recipe["source_manifest"]
    if (set(manifest['source_files']) != SOURCE_FILES or
            manifest['source_files']['manifest.json'] != recipe['source_manifest_sha256'] or
            {name: value for name, value in manifest['source_files'].items() if name != 'manifest.json'} != source_manifest['files']):
        raise ValueError('source file identity chain mismatch')
    if (source_manifest.get("content_id") != recipe["source_content_id"] or
            digest({key: value for key, value in source_manifest.items() if key != "content_id"}) != recipe["source_content_id"] or
            source_manifest.get("grid") != recipe["grid"]):
        raise ValueError("source identity chain mismatch")
    grid = recipe["grid"]
    if (type(recipe["tile_cells"]) is not int or not 1 <= recipe["tile_cells"] <= 255 or
            len(grid["shape_zx"]) != 2 or any(type(count) is not int or count < 2 for count in grid["shape_zx"]) or
            math.prod(grid["shape_zx"]) > 1000000 or
            any(isinstance(grid[name], bool) or not isinstance(grid[name], (int, float)) or not math.isfinite(grid[name]) or
                (name.startswith("spacing") and grid[name] <= 0) for name in
                ("origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m"))):
        raise ValueError("invalid tile grid")
    inputs = source_manifest['proof']['inputs']
    for name in ('budget', 'valley_recipe', 'stage_recipe', 'inundation_recipe'):
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
               not math.isfinite(value) or value < 0 for value in inputs[name].values()):
            raise ValueError('invalid original numeric constraint')
    if source_manifest['proof']['accepted'] is not True or source_manifest['proof']['status'] != 'accepted':
        raise ValueError('source is not an accepted delivery')
    _tile_size(recipe['tile_cells'])
    if math.ceil((grid['shape_zx'][0] - 1) / recipe['tile_cells']) * math.ceil((grid['shape_zx'][1] - 1) / recipe['tile_cells']) > MAX_TILES:
        raise ValueError('tile count bound exceeded')
    specs = list(_tile_specs(grid, recipe["tile_cells"]))
    if len(manifest['tiles']) != len(specs) or len(recipe['source_windows']) != len(specs):
        raise ValueError("tile index count mismatch")
    for index, (tile, bounds) in enumerate(zip(manifest["tiles"], specs)):
        if set(tile) != {'path', 'bounds', 'sha256', 'arrays', 'proof_sha256'}:
            raise ValueError('invalid tile record')
        if tile["path"] != f"tiles/{index:06d}.npz" or tile["bounds"] != bounds or set(tile["arrays"]) != GEOMETRY:
            raise ValueError("tile index mismatch")
        if any(record["shape"] != [bounds[1] - bounds[0], bounds[3] - bounds[2]] for record in tile["arrays"].values()):
            raise ValueError("tile array shape mismatch")
        shape = (bounds[1] - bounds[0], bounds[3] - bounds[2])
        _records(tile['arrays'], GEOMETRY, shape)
        _records(recipe['source_windows'][index], GEOMETRY, shape)
        if any(tile['arrays'][name]['dtype'] != source_manifest['arrays'][name]['dtype'] for name in GEOMETRY):
            raise ValueError('tile/source dtype mismatch')
    if manifest["limits"] != {"max_window_cells": MAX_WINDOW_CELLS, "max_cache_bytes": MAX_CACHE_BYTES,
                              "max_file_bytes": MAX_FILE_BYTES}:
        raise ValueError("unsupported tile limits")
    graph_info = manifest["graph"]
    _reject_link_chain(directory / 'graph.npz')
    _records(graph_info['arrays'], GRAPH)
    count_shape = graph_info['arrays']['receiver']['shape']
    if (len(count_shape) != 1 or count_shape[0] > 250000 or
            any(record['shape'] != ([count_shape[0], 2] if name == 'world_xz_m' else count_shape)
                for name, record in graph_info['arrays'].items())):
        raise ValueError('invalid coarse graph dimensions')
    if graph_info['arrays'] != {name: source_manifest['arrays'][name] for name in GRAPH}:
        raise ValueError('graph differs from source records')
    if graph_info["path"] != "graph.npz" or set(graph_info["arrays"]) != GRAPH or _bounded_hash(directory / "graph.npz") != graph_info["sha256"]:
        raise ValueError("graph identity mismatch")
    graph = _read_arrays(directory / "graph.npz", graph_info["arrays"])
    count = graph["receiver"].size
    if (count > 250000 or graph["world_xz_m"].shape != (count, 2) or
            any(graph[name].shape != (count,) for name in GRAPH - {"world_xz_m"}) or
            any(graph[name].dtype != bool for name in ("active_mask", "outlet_mask")) or
            not np.isfinite(graph["world_xz_m"]).all() or
            any(not np.isfinite(graph[name]).all() for name in
                ("discharge_m3_s", "local_discharge_m3_s", "node_stage_m")) or
            np.any(graph["discharge_m3_s"] < 0) or np.any(graph["local_discharge_m3_s"] < -1e-8) or
            np.any((graph["receiver"] < -1) | (graph["receiver"] >= count)) or
            not np.array_equal(graph["outlet_mask"], graph["receiver"] == -1) or
            not np.array_equal(np.sort(graph["order"]), np.arange(count))):
        raise ValueError("invalid coarse graph size")
    local = graph["discharge_m3_s"].copy()
    donors = np.flatnonzero(graph["receiver"] >= 0)
    rank = np.empty(count, dtype=int)
    rank[graph['order']] = np.arange(count)
    if np.any(rank[graph['receiver'][donors]] >= rank[donors]):
        raise ValueError('coarse graph order is not topological')
    positions = graph['world_xz_m']
    if len(np.unique(positions, axis=0)) != count:
        raise ValueError('duplicate graph coordinates')
    for axis, origin, spacing, length in ((0, grid['origin_x_m'], grid['spacing_x_m'], grid['shape_zx'][1]),
                                         (1, grid['origin_z_m'], grid['spacing_z_m'], grid['shape_zx'][0])):
        indices = (positions[:, axis] - origin) / spacing
        if np.any((indices < 0) | (indices > length - 1)) or not np.allclose(indices, np.rint(indices), rtol=0, atol=1e-8):
            raise ValueError('coarse graph is not on the fine grid')
    if (np.any(graph['active_mask'][donors] & ~graph['active_mask'][graph['receiver'][donors]]) or
            np.any(graph['node_stage_m'][~graph['active_mask']] != 0)):
        raise ValueError('invalid active graph/stage')
    np.subtract.at(local, graph["receiver"][donors], graph["discharge_m3_s"][donors])
    if not np.allclose(local, graph["local_discharge_m3_s"], atol=1e-8, rtol=0):
        raise ValueError("coarse graph Q mismatch")
    return SurfaceNetworkTiles(directory, manifest, graph)


def slice_surface_network_tiles(store, z_slice, x_slice):
    grid = store.manifest["recipe"]["grid"]
    for part, length in ((z_slice, grid["shape_zx"][0]), (x_slice, grid["shape_zx"][1])):
        if (not isinstance(part, slice) or part.step not in (None, 1) or type(part.start) is not int or
                type(part.stop) is not int or not 0 <= part.start < part.stop <= length):
            raise ValueError("window requires bounded unit-step slices")
    shape = (z_slice.stop - z_slice.start, x_slice.stop - x_slice.start)
    if math.prod(shape) > MAX_WINDOW_CELLS:
        raise ValueError("window cell bound exceeded")
    result = {name: np.empty(shape, dtype=np.dtype(store.manifest["tiles"][0]["arrays"][name]["dtype"])) for name in GEOMETRY}
    covered = np.zeros(shape, bool)
    for index, tile in enumerate(store.manifest["tiles"]):
        z0, z1, x0, x1 = tile["bounds"]
        top, bottom = max(z0, z_slice.start), min(z1, z_slice.stop)
        left, right = max(x0, x_slice.start), min(x1, x_slice.stop)
        if top >= bottom or left >= right:
            continue
        arrays = store._tile(index)
        target = np.s_[top-z_slice.start:bottom-z_slice.start, left-x_slice.start:right-x_slice.start]
        source = np.s_[top-z0:bottom-z0, left-x0:right-x0]
        overlap = covered[target]
        for name in GEOMETRY:
            if np.any(overlap) and not np.array_equal(result[name][target][overlap], arrays[name][source][overlap]):
                raise ValueError("shared tile seam mismatch")
            result[name][target] = arrays[name][source]
        covered[target] = True
    if not covered.all():
        raise ValueError("tile coverage gap")
    result["water_depth_m"] = np.where(result["wet_mask"], result["water_surface_m"] - result["final_surface_m"], 0.)
    return MappingProxyType({"origin_x_m": grid["origin_x_m"] + x_slice.start * grid["spacing_x_m"],
                             "origin_z_m": grid["origin_z_m"] + z_slice.start * grid["spacing_z_m"],
                             "spacing_x_m": grid["spacing_x_m"], "spacing_z_m": grid["spacing_z_m"],
                             "vertical_datum": grid["vertical_datum"], "unit": "m",
                             "content_id": store.manifest["content_id"],
                             "arrays": MappingProxyType({name: _immutable(array) for name, array in result.items()})})


def sample_surface_network_tiles(store, world_x_m, world_z_m):
    grid = store.manifest["recipe"]["grid"]
    column = _world_index(world_x_m, grid["origin_x_m"], grid["spacing_x_m"], grid["shape_zx"][1])
    row = _world_index(world_z_m, grid["origin_z_m"], grid["spacing_z_m"], grid["shape_zx"][0])
    return slice_surface_network_tiles(store, slice(row, row + 1), slice(column, column + 1))


def slice_surface_network_tiles_world(store, bounds_xz_m):
    if not isinstance(bounds_xz_m, (tuple, list)) or len(bounds_xz_m) != 4:
        raise ValueError("world bounds require xmin,zmin,xmax,zmax")
    grid = store.manifest["recipe"]["grid"]
    x0, z0, x1, z1 = bounds_xz_m
    columns, rows = grid["shape_zx"][1], grid["shape_zx"][0]
    left = _world_index(x0, grid["origin_x_m"], grid["spacing_x_m"], columns)
    right = _world_index(x1, grid["origin_x_m"], grid["spacing_x_m"], columns)
    top = _world_index(z0, grid["origin_z_m"], grid["spacing_z_m"], rows)
    bottom = _world_index(z1, grid["origin_z_m"], grid["spacing_z_m"], rows)
    return slice_surface_network_tiles(store, slice(top, bottom + 1), slice(left, right + 1))


def verify_all_tiles(store):
    """Explicit full source replay, seams and unique-node/global-weight integration."""
    source = store.path / "source"
    for name, expected in store.manifest["source_files"].items():
        if Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name or ':' in name:
            raise ValueError('invalid source proof path')
        path = source / name
        _reject_link_chain(path)
        if _file_hash(path) != expected:
            raise ValueError("source proof file mismatch")
    delivery = load_surface_network_delivery(source)
    if canonical_json(_plain(delivery['manifest'])) != canonical_json(_plain(store.manifest['recipe']['source_manifest'])):
        raise ValueError("source manifest mismatch")
    for name in GRAPH:
        if not np.array_equal(store.centerline[name], delivery["centerline"][name]):
            raise ValueError("coarse graph differs from source")
    grid = store.manifest['recipe']['grid']
    shape = tuple(grid['shape_zx'])
    unique = {name: np.empty(shape, dtype=delivery['geometry'][name].dtype) for name in GEOMETRY}
    covered = np.zeros(shape, dtype=bool)
    tile_integrals = {name: {'volume_m3': 0., 'area_m2': 0.} for name in ('valley_cut_m', 'bed_cut_m', 'total_cut_m')}
    cell_area = grid['spacing_x_m'] * grid['spacing_z_m']
    for index, tile in enumerate(store.manifest["tiles"]):
        arrays = store._tile(index)
        z0, z1, x0, x1 = tile["bounds"]
        target = np.s_[z0:z1, x0:x1]
        overlap = covered[target]
        for name in GEOMETRY:
            if np.any(overlap) and not np.array_equal(unique[name][target][overlap], arrays[name][overlap]):
                raise ValueError('shared tile seam mismatch')
            if not np.array_equal(arrays[name], delivery["geometry"][name][z0:z1, x0:x1]):
                raise ValueError("tile differs from validated source")
            unique[name][target] = arrays[name]
        covered[target] = True
        weights = np.ones((z1 - z0, x1 - x0))
        weights[[0, -1], :] *= .5
        weights[:, [0, -1]] *= .5
        for name in tile_integrals:
            tile_integrals[name]['volume_m3'] += float(np.sum(arrays[name] * weights) * cell_area)
            tile_integrals[name]['area_m2'] += float(np.sum((arrays[name] > 1e-9) * weights) * cell_area)
    if not covered.all():
        raise ValueError('tile coverage gap')
    weights = np.ones(shape)
    weights[[0, -1], :] *= .5
    weights[:, [0, -1]] *= .5
    integrals = {name: {'volume_m3': float(np.sum(unique[name] * weights) * cell_area),
                        'area_m2': float(np.sum((unique[name] > 1e-9) * weights) * cell_area)} for name in tile_integrals}
    for name in integrals:
        for quantity in integrals[name]:
            if not math.isclose(integrals[name][quantity], tile_integrals[name][quantity], rel_tol=1e-12, abs_tol=1e-9):
                raise ValueError('tile/global integral mismatch')
    return _freeze({'verified': True, 'unique_nodes': int(covered.sum()), 'tile_count': len(store.manifest['tiles']),
                    'integrals': integrals, 'tile_weighted_integrals': tile_integrals,
                    'source_replayed': True, 'seams_equal': True})
