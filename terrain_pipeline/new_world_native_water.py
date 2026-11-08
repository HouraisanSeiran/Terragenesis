import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

from terrain_pipeline import new_world_stage1 as stage1
from terrain_pipeline.new_world_river_lifecycle import PartitionRouter
from terrain_pipeline.basin_storage import PoolStorage as PoolStorage

SCHEMA = 'stage1-water-event-v1'


def _hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _identity(m):
    return hashlib.sha256(json.dumps({k: v for k, v in m.items() if k != 'identity'}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def resource_estimate(manifest, arrays=None):
    n = int(np.prod(manifest['shape_zx']))
    p = int(manifest['counts']['pools'])
    # Without verified classification, conservatively assume every cell is active.
    active = n if arrays is None else int(np.count_nonzero(arrays['valid_mask'] & ~arrays['ocean_mask']))
    # Native mappings, bridged basin and input, mapped source pages and validation
    # temporaries; active sorting/ledgers, SQLite cache, reader and pool allowance.
    mapped_and_native = 80 * n
    active_working = 200 * active
    pool_working = 4096 * p
    reader_allowance = 1024**3
    return {'nodes': n, 'active_nodes': active, 'pools': p,
            'mapped_and_native_bytes': mapped_and_native, 'active_working_bytes': active_working,
            'pool_working_bytes': pool_working, 'reader_allowance_bytes': reader_allowance,
            'ram_bytes': reader_allowance + mapped_and_native + active_working + pool_working,
            'journal_disk_bytes': 512*1024**2 + 288*active + 4096*p + 8*n,
            'assumption': 'single scheduler; mapped source pages, validation, reader and SQLite WAL allowance'}


def _bridge(product):
    m, a = product
    shape = tuple(m['shape_zx'])
    n = int(np.prod(shape))
    labels = a['derived/pool_index']
    ids = a['derived/pool_id']
    basin = np.zeros(n, np.uint64)
    for start in range(0, n, 65536):
        end = min(start + 65536, n)
        lab = labels[start:end]
        good = lab >= 0
        basin[start:end][good] = ids[lab[good]]
    pools = [{'id': str(int(ids[i])), 'anchor_index': int(a['derived/pool_anchor'][i]),
              'capacity_m3': float(a['derived/pool_capacity_m3'][i]),
              'spill_stage_m': float(a['derived/pool_spill_m'][i])} for i in range(len(ids))]
    arrays = {'bed_m': a['bed_m'], 'valid_mask': a['valid_mask'], 'ocean_mask': a['ocean_mask'],
              'basin_id': basin.reshape(shape), 'receiver': a['routing/receiver'].reshape(shape),
              'rank': a['routing/rank'].reshape(shape), 'terminal_kind': a['derived/terminal_type'].reshape(shape),
              'watershed_id': a['derived/watershed_id'].reshape(shape),
              'total_water_unknown': a['derived/total_water_unknown'].reshape(shape)}
    return {'identity': m['identity'], 'pools': pools}, arrays


def preflight(planner_path, output, *, expected_terrain_identity, expected_planner_identity):
    if not expected_planner_identity or not expected_terrain_identity:
        raise ValueError('expected source identities required')
    product = stage1.read_product(planner_path, expected_terrain_identity=expected_terrain_identity)
    if product[0]['identity'] != expected_planner_identity:
        raise ValueError('planner identity mismatch')
    if Path(output).exists():
        raise FileExistsError(output)
    budget = resource_estimate(product[0], product[1])
    import psutil
    budget['available_ram_bytes'] = psutil.virtual_memory().available
    parent = Path(output).resolve().parent
    budget['available_disk_bytes'] = shutil.disk_usage(parent).free
    budget['fits'] = budget['available_ram_bytes'] >= budget['ram_bytes'] and budget['available_disk_bytes'] >= budget['journal_disk_bytes']
    return product, budget



def _decorate_result(result, m, a, bridge):
    mouths = {int(s): i for i, s in enumerate(a['derived/mouth_source'][:m['counts']['mouths']])}
    cols = m['shape_zx'][1]
    origin = m['origin_native_xz']
    for row in result['outlets']:
        i = row['index']
        row['source_native_xz'] = [origin[0] + i % cols, origin[1] + i // cols]
        if row['kind'] == 'marine':
            j = mouths[i]
            row['mouth_id'] = str(int(a['derived/mouth_id'][j]))
            row['target_native_xz'] = a['derived/mouth_ocean_native_xz'][j].tolist()
    result['outlets'] = [row for row in result['outlets'] if row['kind'] != 'marine' or row['known_local_volume_m3'] != 0]
    labels = a['derived/pool_index']
    cells = np.flatnonzero(labels >= 0)
    cells = cells[np.argsort(labels[cells], kind='stable')]
    counts = np.bincount(labels[cells], minlength=len(result['lakes']))
    offsets = np.r_[0, np.cumsum(counts)]
    bed = a['bed_m'].ravel()
    for i, lake in enumerate(result['lakes']):
        members = cells[offsets[i]:offsets[i+1]]
        curve = PoolStorage(members, bed, bridge[0]['pools'][i]['spill_stage_m'], 900.)
        stage = curve.stage_at_volume(lake['storage_m3'])
        lake['level_m'] = float(stage)
        lake['wet_area_m2'] = float(np.count_nonzero(bed[members] < stage) * 900)
    return result

def prepare(planner_path, output, *, expected_terrain_identity, expected_planner_identity,
            source, duration_s, runoff_depth_m, partitions=1, previous=None, resume=False, stop_after=None):
    if not isinstance(source, str) or not source.strip() or not np.isfinite(duration_s) or duration_s <= 0 or not np.isfinite(runoff_depth_m) or runoff_depth_m < 0:
        raise ValueError('declared source, finite nonnegative depth and positive duration required')
    output = Path(output).resolve()
    pending = output.with_name(output.name + '.pending')
    declaration = dict(planner_path=str(Path(planner_path).resolve()), output=str(output),
                       terrain_identity=expected_terrain_identity, planner_identity=expected_planner_identity,
                       source=source, duration_s=float(duration_s), runoff_depth_m=float(runoff_depth_m),
                       partitions=partitions, previous_path=str(Path(previous).resolve()) if previous is not None else None)
    if stop_after not in (None, 'send', 'receive'):
        raise ValueError('invalid checkpoint boundary')
    if output.exists():
        if not resume:
            raise FileExistsError(output)
        existing = read_product(output, expected_terrain_identity=expected_terrain_identity, expected_planner_identity=expected_planner_identity)
        if any(existing[0].get(k) != v for k, v in declaration.items() if k != 'output'):
            raise ValueError('completed event declaration mismatch')
        return existing
    if resume:
        try:
            saved = json.loads((pending / 'checkpoint.json').read_text(encoding='utf8'))
            if saved.get('identity') != _identity(saved) or saved.get('declaration') != declaration or not (pending / 'journal.sqlite').is_file():
                raise ValueError('pending checkpoint declaration mismatch')
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError('invalid pending checkpoint') from exc
    elif pending.exists():
        raise FileExistsError(pending)
    product, budget = preflight(planner_path, output, expected_terrain_identity=expected_terrain_identity, expected_planner_identity=expected_planner_identity)
    if not budget['fits']:
        raise ValueError('resource preflight does not fit: ' + json.dumps(budget))
    m, a = product
    state = None
    if previous is not None:
        prior, result = read_product(previous, expected_terrain_identity=expected_terrain_identity, expected_planner_identity=expected_planner_identity)
        state = result['state']
        if state['source'] != source:
            raise ValueError('continuation source mismatch')
    interval = 0 if state is None else state['next_interval']
    bridge = _bridge(product)
    local = runoff_depth_m * 900.
    output = Path(output).resolve()
    temp = pending
    if not resume:
        temp.mkdir()
        checkpoint = {'schema': 'stage1-water-checkpoint-v1', 'declaration': declaration,
                      'interval': interval, 'previous_identity': prior['identity'] if previous is not None else None,
                      'initial_state': state}
        checkpoint['identity'] = _identity(checkpoint)
        (temp / 'checkpoint.json').write_text(json.dumps(checkpoint, sort_keys=True, allow_nan=False), encoding='utf8')
    elif (saved.get('schema') != 'stage1-water-checkpoint-v1' or saved.get('interval') != interval or
          saved.get('previous_identity') != (prior['identity'] if previous is not None else None) or saved.get('initial_state') != state):
        raise ValueError('pending checkpoint state mismatch')
    try:
        if resume:
            import sqlite3
            from contextlib import closing
            try:
                with closing(sqlite3.connect(f"{(temp / 'journal.sqlite').as_uri()}?mode=ro", uri=True)) as check:
                    if check.execute('PRAGMA quick_check').fetchone() != ('ok',) or check.execute("SELECT COUNT(*) FROM metadata WHERE key IN ('config', 'progress')").fetchone() != (2,):
                        raise ValueError('invalid pending journal')
            except sqlite3.DatabaseError as exc:
                raise ValueError('invalid pending journal') from exc
        router = PartitionRouter(temp / 'journal.sqlite', bridge, local, duration_s, interval=interval, source=source, partitions=partitions, state=state, trace=True)
        try:
            progress = router.run(stop_after=stop_after)
            if not progress['complete']:
                return {'status': 'pending', 'checkpoint_path': str(temp), 'boundary': stop_after,
                        'interval': interval, 'budget': progress}, None
            result = router.result()
            trace = np.lib.format.open_memmap(temp / 'routed_volume_m3.npy', mode='w+', dtype='float64', shape=tuple(m['shape_zx']))
            trace[:] = np.nan
            flat = trace.ravel()
            cursor = router.db.execute('SELECT cell, volume FROM trace')
            while True:
                rows = cursor.fetchmany(65536)
                if not rows:
                    break
                flat[np.fromiter((row[0] for row in rows), dtype=np.int64)] = np.fromiter((row[1] for row in rows), dtype=np.float64)
            trace.flush()
            del flat, trace
        finally:
            router.close()
        _decorate_result(result, m, a, bridge)
        result['initial_state'] = state or {'hydrology_identity': m['identity'], 'source': source, 'next_interval': 0, 'storage_m3': [0.] * len(result['lakes'])}
        (temp / 'result.json').write_text(json.dumps(result, sort_keys=True, allow_nan=False), encoding='utf8')
        manifest = {'schema': SCHEMA, 'planner_path': str(Path(planner_path).resolve()), 'planner_identity': expected_planner_identity,
                    'terrain_identity': expected_terrain_identity, 'source': source, 'runoff_depth_m': float(runoff_depth_m),
                    'duration_s': float(duration_s), 'interval': interval, 'partitions': partitions,
                    'previous_path': str(Path(previous).resolve()) if previous is not None else None,
                    'previous_identity': prior['identity'] if previous is not None else None,
                    'forcing': 'finite declared land-only runoff event', 'resource_budget': budget,
                    'origin_native_xz': m['origin_native_xz'], 'shape_zx': m['shape_zx'], 'spacing_m': m['spacing_m'],
                    'units': {'runoff_depth': 'm', 'duration': 's', 'volume': 'm3', 'discharge': 'm3/s', 'lake_level': 'm', 'wet_area': 'm2'},
                    'files': {name: _hash(temp / name) for name in ('result.json', 'journal.sqlite', 'routed_volume_m3.npy')}}
        manifest['identity'] = _identity(manifest)
        (temp / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, allow_nan=False), encoding='utf8')
        read_product(temp, expected_terrain_identity=expected_terrain_identity,
                     expected_planner_identity=expected_planner_identity, expected_water_identity=manifest['identity'])
        os.rename(temp, output)
        return manifest, result
    except BaseException:
        raise


class WaterProduct(tuple):
    def __new__(cls, manifest, result, planner, arrays, trace):
        obj = super().__new__(cls, (manifest, result))
        obj.context = (planner, arrays, trace)
        return obj


def read_product(path, *, expected_terrain_identity, expected_planner_identity, expected_water_identity=None, _seen=None):
    root = Path(path)
    seen = set() if _seen is None else _seen
    resolved = root.resolve()
    if resolved in seen:
        raise ValueError('cyclic previous event')
    seen.add(resolved)
    try:
        m = json.loads((root / 'manifest.json').read_text(encoding='utf8'))
        if (not expected_terrain_identity or not expected_planner_identity or
                m.get('schema') != SCHEMA or m.get('identity') != _identity(m) or
                m.get('terrain_identity') != expected_terrain_identity or
                m.get('planner_identity') != expected_planner_identity or
                (expected_water_identity is not None and m.get('identity') != expected_water_identity)):
            raise ValueError('water identity mismatch')
        product = stage1.read_product(m['planner_path'], expected_terrain_identity=expected_terrain_identity)
        source, arrays = product
        if source['identity'] != expected_planner_identity:
            raise ValueError('planner identity mismatch')
        if any(m.get(k) != source[k] for k in ('shape_zx', 'origin_native_xz', 'spacing_m')):
            raise ValueError('water native grid mismatch')
        units = {'runoff_depth': 'm', 'duration': 's', 'volume': 'm3', 'discharge': 'm3/s', 'lake_level': 'm', 'wet_area': 'm2'}
        if (m.get('units') != units or m.get('forcing') != 'finite declared land-only runoff event' or
                not isinstance(m.get('source'), str) or not m['source'].strip() or
                type(m.get('interval')) is not int or m['interval'] < 0 or
                type(m.get('partitions')) is not int or m['partitions'] not in (1, 2, 4)):
            raise ValueError('invalid event declaration')
        for key, positive in (('duration_s', True), ('runoff_depth_m', False)):
            value = m.get(key)
            if type(value) not in (int, float) or not np.isfinite(value) or value < 0 or (positive and value == 0):
                raise ValueError('invalid event ' + key)
        if set(m['files']) != {'result.json', 'journal.sqlite', 'routed_volume_m3.npy'} or any(_hash(root / name) != digest for name, digest in m['files'].items()):
            raise ValueError('water product hash mismatch')
        trace = np.load(root / 'routed_volume_m3.npy', mmap_mode='r', allow_pickle=False)
        if trace.dtype != np.dtype('float64') or trace.shape != tuple(source['shape_zx']):
            raise ValueError('invalid routed volume array')
        result = json.loads((root / 'result.json').read_text(encoding='utf8'))
        initial = result['initial_state']
        if m['interval'] == 0 and initial != {'hydrology_identity': source['identity'], 'source': m['source'], 'next_interval': 0, 'storage_m3': [0.] * source['counts']['pools']}:
            raise ValueError('invalid initial state')
        if m['interval'] == 0:
            if m.get('previous_path') is not None or m.get('previous_identity') is not None:
                raise ValueError('invalid previous event')
        else:
            previous_path = m.get('previous_path')
            if not isinstance(previous_path, str) or Path(previous_path).resolve() == root.resolve():
                raise ValueError('invalid previous event')
            prior, prior_result = read_product(previous_path, expected_terrain_identity=expected_terrain_identity, expected_planner_identity=expected_planner_identity, expected_water_identity=m.get('previous_identity'), _seen=seen)
            if not m.get('previous_identity') or prior['interval'] != m['interval'] - 1 or prior_result['state'] != initial:
                raise ValueError('previous event state mismatch')
        bridge = _bridge(product)
        local = m['runoff_depth_m'] * 900.
        with tempfile.TemporaryDirectory(prefix='water-verify-') as temp:
            router = PartitionRouter(Path(temp) / 'verify.sqlite', bridge, local, m['duration_s'], interval=m['interval'], source=m['source'], partitions=m['partitions'], state=initial, trace=True)
            try:
                router.run()
                expected = _decorate_result(router.result(), source, arrays, bridge)
                expected['initial_state'] = initial
                if json.dumps(result, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
                    raise ValueError('water result semantic mismatch')
                flat = trace.ravel()
                # Check every represented edge and every absent cell without a domain-sized copy.
                cursor = router.db.execute('SELECT cell, volume FROM trace ORDER BY cell')
                offset = 0
                for cell, volume in cursor:
                    if not np.isnan(flat[offset:cell]).all() or not np.isfinite(flat[cell]) or flat[cell] < 0 or flat[cell] != volume:
                        raise ValueError('routed trace semantic mismatch')
                    offset = cell + 1
                if not np.isnan(flat[offset:]).all():
                    raise ValueError('routed trace semantic mismatch')
            finally:
                router.close()
        m['_product_path'] = str(root.resolve())
        for array in arrays.values():
            if isinstance(array, np.ndarray):
                array.flags.writeable = False
        trace.flags.writeable = False
        return WaterProduct(m, result, source, arrays, trace)
    except (KeyError, TypeError, IndexError, OSError, json.JSONDecodeError) as exc:
        raise ValueError('invalid water product') from exc


def query_mouth(product, mouth_id):
    return next((x for x in product[1]['outlets'] if x.get('mouth_id') == str(mouth_id)), None)


def query_cell(product, native_x, native_z):
    """Read one native cell; None routed volume means no routed edge is represented."""
    m, result = product
    planner, arrays, trace = product.context
    return _query_cell(m, result, planner, arrays, trace, native_x, native_z)


def _query_cell(m, result, planner, arrays, trace, native_x, native_z):
    if type(native_x) is not int or type(native_z) is not int:
        raise ValueError('native coordinates must be integers')
    x = native_x - planner['origin_native_xz'][0]
    z = native_z - planner['origin_native_xz'][1]
    rows, cols = planner['shape_zx']
    if not (0 <= x < cols and 0 <= z < rows):
        raise ValueError('native coordinate outside product')
    index = z * cols + x
    label = int(arrays['derived/pool_index'][index])
    volume = float(trace[z, x])
    lake = result['lakes'][label] if label >= 0 else None
    return {'native_xz': [native_x, native_z], 'valid': bool(arrays['valid_mask'][z, x]),
            'ocean': bool(arrays['ocean_mask'][z, x]),
            'total_water_unknown': bool(arrays['derived/total_water_unknown'][index]),
            'routed_volume_m3': volume if np.isfinite(volume) else None,
            'duration_s': m['duration_s'], 'source': m['source'],
            'lake_id': lake['id'] if lake else None,
            'lake_level_m': lake['level_m'] if lake else None,
            'lake_wet_area_m2': lake['wet_area_m2'] if lake else None}


def query_window(product, x_min, z_min, x_max, z_max):
    """Query a half-open native-coordinate window as rows of cell records."""
    if any(type(v) is not int for v in (x_min, z_min, x_max, z_max)) or x_min >= x_max or z_min >= z_max:
        raise ValueError('invalid native window')
    m, result = product
    planner, arrays, trace = product.context
    return [[_query_cell(m, result, planner, arrays, trace, x, z) for x in range(x_min, x_max)] for z in range(z_min, z_max)]
