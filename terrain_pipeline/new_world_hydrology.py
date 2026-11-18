"""Finite parent-support hydrology bound to an immutable new-world terrain."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from scipy.sparse import csr_matrix

from terrain_pipeline import td_source as new_world_terrain
from terrain_pipeline.drainage import IrregularMesh as IrregularMesh
from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.drainage import route_graph as route_graph
from terrain_pipeline.drainage import accumulate_graph as accumulate_graph
from terrain_pipeline.drainage import pool_labels as pool_labels
from terrain_pipeline.basin_storage import PoolStorage as PoolStorage
from terrain_pipeline.drainage import route_pool_interval as route_pool_interval
from terrain_pipeline.tectonic import digest

VERSION = 'finite-parent-hydrology-v2'

def _identity(record):
    return _hash({k: v for k, v in record.items() if k not in ('identity', 'terrain_path')})


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _id(identity, kind, x, z):
    return int.from_bytes(hashlib.sha256(f'{VERSION}:{identity}:{kind}:{x}:{z}'.encode()).digest()[:8], 'big') or 1


def _solve(manifest, source):
    bed = np.asarray(source['bed_m'], dtype=np.float64)
    valid = np.asarray(source['valid_mask'], dtype=bool)
    ocean = np.asarray(source['ocean_mask'], dtype=bool)
    unknown = np.asarray(source['unknown_mask'], dtype=bool)
    shape = bed.shape
    origin = manifest['origin_native_xz']
    seed = manifest['world_seed']
    mesh = build_mesh(shape, tuple(origin), 30., seed)
    n = bed.size
    # Remove edges across invalid cells; invalid nodes are isolated explicit outlets.
    starts = np.repeat(np.arange(n), np.diff(mesh.indptr))
    keep = valid.ravel()[starts] & valid.ravel()[mesh.indices]
    graph = csr_matrix((mesh.edge_length_m[keep], (starts[keep], mesh.indices[keep])), shape=(n, n))
    mesh = IrregularMesh(mesh.shape, mesh.origin_native_xz, mesh.spacing_m, mesh.world_seed,
                         mesh.node_x_m, mesh.node_z_m, graph.indptr, graph.indices, graph.data)
    boundary = np.zeros(shape, dtype=bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    # Any valid node adjacent to an invalid node is a finite-domain edge.
    invalid_neighbors = np.zeros(n, dtype=bool)
    invalid_neighbors[starts[~keep & valid.ravel()[starts]]] = True
    boundary |= invalid_neighbors.reshape(shape)
    edge_unknown = valid & ~ocean & (boundary | unknown)
    outlets = ~valid | ocean | edge_unknown
    routing = route_graph(bed, outlets, mesh)
    receiver = routing.receiver
    terminal = np.arange(n, dtype=np.int64)
    for cell in routing.order:
        if receiver[cell] >= 0:
            terminal[cell] = terminal[receiver[cell]]
    kind = np.zeros(n, dtype=np.uint8)  # 0 invalid, 1 ocean, 2 unknown, 3 inland
    kind[ocean.ravel()] = 1
    kind[edge_unknown.ravel()] = 2
    kind[valid.ravel() & (receiver < 0) & ~ocean.ravel() & ~edge_unknown.ravel()] = 3
    terminal_kind = kind[terminal]
    ids = np.zeros(n, dtype=np.uint64)
    for cell in np.unique(terminal[valid.ravel()]):
        ids[cell] = _id(manifest['identity'], 'watershed', origin[0] + int(cell % shape[1]), origin[1] + int(cell // shape[1]))
    watershed = ids[terminal]
    watershed[~valid.ravel()] = 0
    labels, count = pool_labels(bed.ravel(), routing.filled.ravel(), mesh.indptr, mesh.indices)
    basin_id = np.zeros(n, dtype=np.uint64)
    pools = []
    for label in range(count):
        cells = np.flatnonzero(labels == label)
        anchor = cells[np.argmin(routing.rank[cells])]
        identifier = _id(manifest['identity'], 'basin', origin[0] + int(anchor % shape[1]), origin[1] + int(anchor // shape[1]))
        basin_id[cells] = identifier
        stage = float(routing.filled.ravel()[anchor])
        pool = PoolStorage(cells, bed.ravel(), stage, 900.)
        pools.append({'id': str(identifier), 'anchor_index': int(anchor), 'spill_stage_m': stage, 'capacity_m3': pool.capacity_m3})
    local = valid.astype(np.float64).ravel() * 900.  # m², unit runoff depth
    lower = accumulate_graph(receiver, routing.order, local)
    # Boundary inflow is not observed: all downstream cells remain unknown.
    total_unknown = edge_unknown.ravel().copy()
    for cell in routing.order[::-1]:
        target = receiver[cell]
        if target >= 0 and total_unknown[cell]:
            total_unknown[target] = True
    # Even where no boundary reaches this particular route, watershed completeness
    # has not been certified against a larger support.
    total_unknown[valid.ravel()] = True
    result = {k: np.asarray(v) for k, v in source.items()}
    result.update(receiver=receiver.reshape(shape), terminal_index=terminal.reshape(shape),
                  terminal_kind=terminal_kind.reshape(shape), watershed_id=watershed.reshape(shape),
                  basin_id=basin_id.reshape(shape), filled_routing_m=routing.filled,
                  known_local_area_m2=lower.reshape(shape), total_water_unknown=total_unknown.reshape(shape),
                  boundary_unknown=edge_unknown, rank=routing.rank.reshape(shape))
    return result, pools, seed


def prepare(terrain_path, output, *, expected_terrain_identity):
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    if not isinstance(expected_terrain_identity, str) or len(expected_terrain_identity) != 64:
        raise ValueError('expected terrain identity required')
    terrain, source = new_world_terrain.read_world_terrain(terrain_path, expected_identity=expected_terrain_identity)
    arrays, pools, seed = _solve(terrain, source)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.hydrology-stage-', dir=output.parent))
    try:
        hashes = {}
        for name, array in arrays.items():
            np.save(tmp / (name + '.npy'), array, allow_pickle=False)
            hashes[name] = digest(tmp / (name + '.npy'))
        manifest = {'schema': VERSION, 'terrain_identity': expected_terrain_identity,
                    'terrain_path': str(Path(terrain_path).resolve()),
                    'origin_native_xz': terrain['origin_native_xz'], 'shape_zx': list(arrays['bed_m'].shape),
                    'spacing_m': 30, 'world_seed': seed, 'seed_source': 'terrain manifest',
                    'files': hashes, 'pools': pools,
                    'scope': 'finite parent support only; no expanded-domain or partition certification',
                    'water': 'known_local_area_m2 is unit-depth local runoff lower bound; total water unknown',
                    'terminal_kinds': {'0': 'invalid', '1': 'ocean', '2': 'unknown', '3': 'inland'}}
        manifest['identity'] = _identity(manifest)
        (tmp / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        read_product(tmp, expected_terrain_identity=expected_terrain_identity)
        os.rename(tmp, output)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return read_product(output, expected_terrain_identity=expected_terrain_identity)


def read_product(path, expected_identity=None, *, expected_terrain_identity=None):
    path = Path(path)
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    identity = manifest.get('identity')
    if identity != _identity(manifest) or (expected_identity is not None and identity != expected_identity):
        raise ValueError('identity mismatch')
    if manifest.get('schema') != VERSION or (expected_terrain_identity is not None and manifest.get('terrain_identity') != expected_terrain_identity):
        raise ValueError('terrain identity or schema mismatch')
    names = set(new_world_terrain.NAMES) | {'receiver', 'terminal_index', 'terminal_kind', 'watershed_id', 'basin_id', 'filled_routing_m', 'known_local_area_m2', 'total_water_unknown', 'boundary_unknown', 'rank'}
    if set(manifest['files']) != names or manifest['spacing_m'] != 30:
        raise ValueError('product contract mismatch')
    origin, dims = manifest.get('origin_native_xz'), manifest.get('shape_zx')
    if (not isinstance(origin, list) or len(origin) != 2 or any(type(v) is not int for v in origin)
            or not isinstance(dims, list) or len(dims) != 2 or any(type(v) is not int or v <= 0 for v in dims)
            or type(manifest.get('world_seed')) is not int or manifest['world_seed'] != 20261020
            or not isinstance(manifest.get('terrain_path'), str) or not Path(manifest['terrain_path']).is_absolute()):
        raise ValueError('invalid coordinates, seed or source path')
    terrain, source = new_world_terrain.read_world_terrain(manifest['terrain_path'], expected_identity=manifest['terrain_identity'])
    if (terrain['origin_native_xz'] != origin or terrain['shape_zx'] != dims
            or terrain['world_seed'] != manifest['world_seed'] or terrain['spacing_m'] != 30):
        raise ValueError('terrain metadata mismatch')
    shape = tuple(dims)
    dtypes = {name: (np.bool_ if name.endswith('_mask') else np.float32) for name in new_world_terrain.NAMES}
    dtypes.update(receiver=np.int64, terminal_index=np.int64, terminal_kind=np.uint8,
                  watershed_id=np.uint64, basin_id=np.uint64, filled_routing_m=np.float64,
                  known_local_area_m2=np.float64, total_water_unknown=np.bool_, boundary_unknown=np.bool_, rank=np.int64)
    arrays = {}
    for name in names:
        file = path / (name + '.npy')
        if digest(file) != manifest['files'][name]:
            raise ValueError('array hash mismatch')
        a = np.load(file, mmap_mode='r', allow_pickle=False)
        if a.shape != ((5, *shape) if name == 'climate_base' else shape) or a.dtype != dtypes[name] or not np.isfinite(a).all():
            raise ValueError('array shape or value mismatch')
        if name in source and not np.array_equal(a, source[name]):
            raise ValueError('terrain array mismatch: ' + name)
        arrays[name] = a
    r = arrays['receiver'].ravel()
    rank = arrays['rank'].ravel()
    n = r.size
    if np.any((r < -1) | (r >= n)) or not np.array_equal(np.sort(rank), np.arange(n)):
        raise ValueError('invalid receiver or rank')
    cells = np.flatnonzero(r >= 0)
    if np.any(rank[r[cells]] >= rank[cells]):
        raise ValueError('receiver cycle or invalid rank')
    valid = arrays['valid_mask'].ravel()
    ocean = arrays['ocean_mask'].ravel()
    boundary = arrays['boundary_unknown'].ravel()
    terminal = arrays['terminal_index'].ravel()
    kinds = arrays['terminal_kind'].ravel()
    if np.any((terminal < 0) | (terminal >= n)) or np.any(r[terminal] != -1):
        raise ValueError('invalid terminal')
    if np.any(terminal[cells] != terminal[r[cells]]):
        raise ValueError('terminal does not follow receiver')
    expected_kind = np.zeros(n, np.uint8)
    expected_kind[ocean] = 1
    expected_kind[boundary] = 2
    expected_kind[valid & (r < 0) & ~ocean & ~boundary] = 3
    if not np.array_equal(kinds, expected_kind[terminal]):
        raise ValueError('terminal kind mismatch')
    ids = np.zeros(n, np.uint64)
    for cell in np.unique(terminal[valid]):
        ids[cell] = _id(manifest['terrain_identity'], 'watershed', origin[0] + int(cell % shape[1]), origin[1] + int(cell // shape[1]))
    expected_ids = ids[terminal]
    expected_ids[~valid] = 0
    if not np.array_equal(arrays['watershed_id'].ravel(), expected_ids) or not arrays['total_water_unknown'].ravel()[valid].all():
        raise ValueError('watershed identity or unknown mismatch')
    basin = arrays['basin_id'].ravel()
    seen = set()
    pool_cells = np.flatnonzero(basin)
    pool_cells = pool_cells[np.argsort(basin[pool_cells], kind='stable')]
    group_ids, group_starts = np.unique(basin[pool_cells], return_index=True)
    group_ends = np.r_[group_starts[1:], len(pool_cells)]
    for pool in manifest['pools']:
        anchor = pool['anchor_index']
        if type(anchor) is not int or not 0 <= anchor < n:
            raise ValueError('invalid pool anchor')
        identifier = _id(manifest['terrain_identity'], 'basin', origin[0] + anchor % shape[1], origin[1] + anchor // shape[1])
        position = np.searchsorted(group_ids, identifier)
        if position >= len(group_ids) or group_ids[position] != identifier:
            raise ValueError('invalid pool identity')
        members = pool_cells[group_starts[position]:group_ends[position]]
        if (pool['id'] != str(identifier) or identifier in seen or not members.size or anchor not in members
                or rank[anchor] != rank[members].min()):
            raise ValueError('invalid pool identity')
        stage = float(arrays['filled_routing_m'].ravel()[anchor])
        capacity = PoolStorage(members, arrays['bed_m'].ravel(), stage, 900.).capacity_m3
        if pool['spill_stage_m'] != stage or not np.isclose(pool['capacity_m3'], capacity, rtol=1e-12, atol=1e-8):
            raise ValueError('invalid pool capacity')
        seen.add(identifier)
    if set(group_ids) != seen:
        raise ValueError('unlisted basin')
    return manifest, arrays


def route_event(product, runoff_depth_m, duration_s, *, input_source):
    """Route a declared finite local event from dry pools; external water remains unknown."""
    manifest, arrays = product
    if (not isinstance(input_source, str) or not input_source.strip() or
            not np.isfinite(duration_s) or duration_s <= 0):
        raise ValueError('positive duration and input source required')
    depth = np.asarray(runoff_depth_m, dtype=np.float64)
    if depth.ndim == 0:
        depth = np.full(arrays['bed_m'].shape, depth)
    if depth.shape != arrays['bed_m'].shape or not np.isfinite(depth).all() or np.any(depth < 0):
        raise ValueError('invalid declared runoff depth')
    valid = arrays['valid_mask'].ravel()
    local = depth.ravel() * valid * 900.
    pools = manifest['pools']
    labels = np.full(local.size, -1, dtype=np.int64)
    basin = arrays['basin_id'].ravel()
    anchors = np.array([p['anchor_index'] for p in pools], dtype=np.int64)
    capacity = np.array([p['capacity_m3'] for p in pools], dtype=np.float64)
    for i, pool in enumerate(pools):
        labels[basin == int(pool['id'])] = i
    storage = np.zeros(len(pools), dtype=np.float64)
    receiver = arrays['receiver'].ravel()
    order = np.argsort(arrays['rank'].ravel())
    flow, retained = route_pool_interval(local, order, receiver, labels, anchors, capacity, storage)
    terminals = np.flatnonzero(valid & (receiver < 0))
    outlets = [{'index': int(i), 'kind': int(arrays['terminal_kind'].ravel()[i]),
                'watershed_id': str(int(arrays['watershed_id'].ravel()[i])), 'volume_m3': float(flow[i])}
               for i in terminals]
    total = float(local.sum())
    discharged = float(sum(item['volume_m3'] for item in outlets))
    residual = total - discharged - float(storage.sum())
    if not np.isclose(residual, 0., atol=max(1e-7, total * 1e-10), rtol=0):
        raise ValueError('event water balance failed')
    return {'terrain_identity': manifest['terrain_identity'], 'hydrology_identity': manifest['identity'],
            'duration_s': float(duration_s), 'input_source': input_source,
            'declared_local_input_m3': total, 'external_water': 'unknown',
            'outlets': outlets, 'pool_storage_m3': storage.tolist(),
            'stored_m3': float(storage.sum()), 'outflow_m3': discharged, 'residual_m3': residual}


def query_window(product, origin_native_xz, shape):
    manifest, arrays = product
    if len(origin_native_xz) != 2 or len(shape) != 2 or any(type(v) is not int for v in (*origin_native_xz, *shape)) or any(v <= 0 for v in shape):
        raise ValueError('integer coordinates and positive shape required')
    x = origin_native_xz[0] - manifest['origin_native_xz'][0]
    z = origin_native_xz[1] - manifest['origin_native_xz'][1]
    if x < 0 or z < 0 or x + shape[1] > manifest['shape_zx'][1] or z + shape[0] > manifest['shape_zx'][0]:
        raise ValueError('outside parent support')
    return {k: a[..., z:z + shape[0], x:x + shape[1]] for k, a in arrays.items()}


def sample_climate(product, x, z):
    return query_window(product, (x, z), (1, 1))['climate_base'][:, 0, 0]


def query_mouth(product, x, z):
    window = query_window(product, (x, z), (1, 1))
    return {'ocean': bool(window['ocean_mask'][0, 0]), 'terminal_kind': int(window['terminal_kind'][0, 0]), 'watershed_id': int(window['watershed_id'][0, 0])}
