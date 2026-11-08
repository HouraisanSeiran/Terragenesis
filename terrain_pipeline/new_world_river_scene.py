"""Authenticated raw scene extraction from a native routed event.

Native account indices refer to the parent 30 m raster; node positions are the
planner's irregular physical coordinates. This product is not a hydraulic solve.
"""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
from terrain_pipeline import new_world_native_water as water

SCHEMA = 'new-world-river-scene-v1'
MAX_CELLS = 4_000_000


def _hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _identity(m):
    return hashlib.sha256(json.dumps({k: v for k, v in m.items() if k != 'identity'}, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def extract(water_path, *, expected_terrain_identity, expected_planner_identity,
            expected_water_identity, mouth_id, interval, origin_native_xz, shape_zx):
    """Extract a half-open native-grid window and its upstream main chain.

    ``interval`` is the native event sequence number, not an absolute time.
    Boundary contributions are routed edge volumes, including off-window edges.
    No profile construction or wet-connectivity claim is made.
    """
    if not all(isinstance(x, str) and x.strip() for x in (expected_terrain_identity, expected_planner_identity, expected_water_identity, mouth_id)):
        raise ValueError('expected identities and mouth ID required')
    if type(interval) is not int or interval < 0:
        raise ValueError('invalid interval')
    if (len(origin_native_xz) != 2 or len(shape_zx) != 2 or
        any(type(v) is not int for v in (*origin_native_xz, *shape_zx)) or
        min(shape_zx) < 1 or np.prod(shape_zx) > MAX_CELLS):
        raise ValueError('invalid or oversized scene extent')
    product = water.read_product(water_path, expected_terrain_identity=expected_terrain_identity,
                                 expected_planner_identity=expected_planner_identity,
                                 expected_water_identity=expected_water_identity)
    wm, _ = product
    pm, a, trace = product.context
    if wm['interval'] != interval:
        raise ValueError('wrong water interval')
    mouth = water.query_mouth(product, mouth_id)
    if mouth is None:
        raise ValueError('mouth not represented in water event')
    matches = np.flatnonzero(a['derived/mouth_id'][:pm['counts']['mouths']] == int(mouth_id))
    if len(matches) != 1 or str(int(mouth_id)) != mouth_id:
        raise ValueError('invalid mouth identity')
    j = int(matches[0]); source = int(a['derived/mouth_source'][j]); target = int(a['derived/mouth_ocean_receiver'][j])
    rows, cols = pm['shape_zx']; ox, oz = pm['origin_native_xz']; x0, z0 = origin_native_xz
    height, width = shape_zx; x = x0-ox; z = z0-oz
    if x < 0 or z < 0 or x+width > cols or z+height > rows:
        raise ValueError('scene outside source bounds')
    def inside(index):
        return x <= index % cols < x+width and z <= index // cols < z+height
    if not inside(source) or not inside(target):
        raise ValueError('scene must contain mouth source and ocean receiver')
    if (mouth['index'] != source or mouth['receiver_index'] != target or
        mouth['source_native_xz'] != [ox+source%cols, oz+source//cols] or
        mouth['target_native_xz'] != [ox+target%cols, oz+target//cols] or
        int(a['routing/receiver'][source]) != target or not a['ocean_mask'].ravel()[target] or
        float(trace.ravel()[source]) != mouth['known_local_volume_m3']):
        raise ValueError('mouth binding mismatch')
    # Scan the frozen receiver array in chunks; do not assume adjacency symmetry.
    incoming = {}
    rec = a['routing/receiver']; flat_trace = trace.ravel()
    for start in range(0, rows*cols, 65536):
        r = np.asarray(rec[start:start+65536]); valid = r >= 0
        candidates = np.flatnonzero(valid)
        for k in candidates:
            dest = int(r[k])
            if inside(dest):
                incoming.setdefault(dest, []).append(start + int(k))
    chain = [source]; boundary = []
    while True:
        node = chain[-1]
        edges = incoming.get(node, [])
        def key(i):
            v = float(flat_trace[i])
            return (-v if np.isfinite(v) else float('inf'), i)
        eligible = sorted((i for i in edges if inside(i) and np.isfinite(flat_trace[i])), key=key)
        chosen = eligible[0] if eligible else None
        for i in sorted(edges):
            if i != chosen:
                v = float(flat_trace[i])
                boundary.append({'source_index': i, 'receiver_index': node,
                                 'known_volume_m3': v if np.isfinite(v) else None,
                                 'outside_scene': not inside(i)})
        if chosen is None:
            break
        chain.append(chosen)
    chain.reverse()
    indices = np.asarray(chain, dtype=np.int64)
    volumes = np.asarray(flat_trace[indices], dtype=np.float64)
    differences = volumes.copy()
    if len(chain) > 1:
        differences[1:] -= volumes[:-1]
    unknown = a['derived/total_water_unknown'][indices]
    pools = a['derived/pool_index'][indices]
    reasons = ['raw bed profile and physical channel sections require validation']
    if np.any(unknown) or mouth['total_water_unknown']:
        reasons.append('total water unknown')
    if np.any(pools >= 0):
        reasons.append('lake transition unsupported')
    if np.any(differences < -1e-9):
        reasons.append('negative internal routed-volume difference')
    if any(b['known_volume_m3'] is None for b in boundary):
        reasons.append('unrepresented boundary trace')
    sl = np.s_[z:z+height, x:x+width]
    arrays = {name: np.array(a[name][sl], copy=True) for name in
              ('bed_m', 'valid_mask', 'ocean_mask', 'closed_below_sea_mask', 'unknown_mask')}
    arrays.update(parent_index=indices, node_xz_m=np.column_stack((a['graph/node_x_m'][indices], a['graph/node_z_m'][indices])),
                  routed_volume_m3=volumes, incremental_volume_m3=differences,
                  total_water_unknown=np.asarray(unknown, dtype=bool), pool_index=np.asarray(pools, dtype=np.int64))
    metadata = {'schema': SCHEMA, 'water_path': str(Path(water_path).resolve()),
        'terrain_identity': expected_terrain_identity, 'planner_identity': expected_planner_identity,
        'water_identity': expected_water_identity, 'world_seed': pm['world_seed'],
        'parent_origin_native_xz': pm['origin_native_xz'], 'parent_shape_zx': pm['shape_zx'],
        'origin_native_xz': list(origin_native_xz), 'shape_zx': list(shape_zx),
        'origin_xz_m': [x0*30, z0*30], 'spacing_m': 30,
        'coordinate_contract': 'raster account index is native x,z times 30 m; node_xz_m is irregular planner position',
        'mouth_id': mouth_id, 'mouth_source_index': source, 'ocean_receiver_index': target,
        'mouth_source_native_xz': mouth['source_native_xz'], 'ocean_receiver_native_xz': mouth['target_native_xz'],
        'mouth_source_xz_m': [float(a['graph/node_x_m'][source]), float(a['graph/node_z_m'][source])],
        'ocean_receiver_xz_m': [float(a['graph/node_x_m'][target]), float(a['graph/node_z_m'][target])],
        'interval': interval, 'duration_s': wm['duration_s'], 'time_basis': 'event duration only; absolute start unavailable',
        'known_mouth_volume_m3': mouth['known_local_volume_m3'], 'mouth_total_water_unknown': mouth['total_water_unknown'],
        'boundary_contributions': boundary, 'status': 'unresolved', 'reasons': reasons,
        'bed_status': 'unchanged authenticated parent bed', 'physical_solve_ready': False,
        'wet_connectivity_certified': False, 'derived_bed_delta': None,
        'revalidation_required_after_bed_change': True}
    for arr in arrays.values():
        arr.flags.writeable = False
    return metadata, arrays


def prepare(water_path, output, **kwargs):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    metadata, arrays = extract(water_path, **kwargs)
    temp = Path(tempfile.mkdtemp(prefix=output.name + '.pending-', dir=output.parent))
    try:
        np.savez_compressed(temp / 'scene.npz', **arrays)
        metadata['array_sha256'] = _hash(temp / 'scene.npz')
        metadata['identity'] = _identity(metadata)
        (temp / 'manifest.json').write_text(json.dumps(metadata, sort_keys=True, allow_nan=False), encoding='utf8')
        read_product(temp, expected_identity=metadata['identity'], **{k: kwargs[k] for k in ('expected_terrain_identity', 'expected_planner_identity', 'expected_water_identity')})
        os.rename(temp, output)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return metadata, arrays


def read_product(path, *, expected_identity, expected_terrain_identity, expected_planner_identity, expected_water_identity):
    if not expected_identity:
        raise ValueError('expected scene identity required')
    root = Path(path)
    m = json.loads((root / 'manifest.json').read_text(encoding='utf8'))
    if m.get('schema') != SCHEMA or m.get('identity') != expected_identity or _identity(m) != expected_identity or _hash(root / 'scene.npz') != m.get('array_sha256'):
        raise ValueError('scene integrity mismatch')
    expected, arrays = extract(m['water_path'], expected_terrain_identity=expected_terrain_identity,
        expected_planner_identity=expected_planner_identity, expected_water_identity=expected_water_identity,
        mouth_id=m['mouth_id'], interval=m['interval'], origin_native_xz=m['origin_native_xz'], shape_zx=m['shape_zx'])
    if {k: v for k, v in m.items() if k not in ('identity', 'array_sha256')} != expected:
        raise ValueError('scene source binding mismatch')
    with np.load(root / 'scene.npz', allow_pickle=False) as saved:
        if set(saved.files) != set(arrays) or any(not np.array_equal(saved[k], v, equal_nan=True) for k, v in arrays.items()):
            raise ValueError('scene arrays differ from authenticated source')
    return m, arrays
