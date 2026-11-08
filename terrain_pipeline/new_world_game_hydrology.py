"""Finite 90 m known-local runoff scenario on the frozen whole-support graph."""
import json
import time
from pathlib import Path

import numpy as np
from numba import njit

from terrain_pipeline.new_world_stage1 import derive_native_hydrology
from terrain_pipeline.drainage import route_pool_interval as route_pool_interval

IDENTITY = 'c751a09a6f02e8c336b6b9b8fb4b11b5dc67386e9a8470b0b1d90858bf1ffb72'
ROOT = Path('.scratch/river-upgrade-20261101')


@njit
def levels(labels, bed, spill, storage, area):
    count = storage.size
    lo = np.full(count, np.inf)
    for i in range(labels.size):
        p = labels[i]
        if p >= 0 and bed[i] < lo[p]:
            lo[p] = bed[i]
    hi = spill.copy()
    for _ in range(32):
        mid = (lo + hi) * .5
        volume = np.zeros(count)
        for i in range(labels.size):
            p = labels[i]
            if p >= 0 and mid[p] > bed[i]:
                volume[p] += (mid[p] - bed[i]) * area
        for p in range(count):
            if volume[p] < storage[p]:
                lo[p] = mid[p]
            else:
                hi[p] = mid[p]
    for p in range(count):
        if storage[p] == 0:
            hi[p] = np.nan
    return hi


def run(*, terrain=None, routing=None, output=None, source_identity=IDENTITY):
    """Prepare a new product from explicit saved inputs; never overwrite an output."""
    start = time.monotonic()
    terrain = Path(terrain) if terrain is not None else ROOT / 'terrain-v3'
    route_root = Path(routing) if routing is not None else ROOT / 'game-grade-90m'
    out = Path(output) if output is not None else ROOT / 'game-hydro-v1'
    source = json.loads((terrain / 'manifest.json').read_text(encoding='utf8'))
    if source['identity'] != source_identity:
        raise ValueError('terrain identity mismatch')
    out.mkdir(exist_ok=False)
    marker = out / '.computing.pid'
    import os
    marker.write_text(str(os.getpid()), encoding='ascii')
    try:
        load = lambda p: np.load(p, mmap_mode='r', allow_pickle=False)
        graph = {k: load(route_root / 'graph' / (k + '.npy')) for k in ('indptr', 'indices', 'node_x_m', 'node_z_m')}
        route = {k: load(route_root / 'routing' / (k + '.npy')) for k in ('filled', 'order', 'rank', 'receiver')}
        bed, ocean, unknown, valid = [load(route_root / (k + '.npy')) for k in ('bed_m', 'ocean_mask', 'unknown_mask', 'valid_mask')]
        product = derive_native_hydrology(graph, route, bed, ocean, unknown, valid, (0, 0), source_identity, out / 'derived', cell_area_m2=8100.)
        pools, mouths, arrays = product['pools'], product['mouths'], product['arrays']
        nodes = mouths['source']
        xy = np.column_stack((graph['node_x_m'][nodes] * 3 - 61440, graph['node_z_m'][nodes] * 3 - 61440))
        np.save(out / 'mouth_world_xz_m.npy', xy)
        np.save(out / 'mouth_unknown.npy', arrays['total_water_unknown'][nodes])
        np.save(out / 'time_seconds.npy', np.array([0, 15 * 86400, 30 * 86400], dtype=np.int64))
        n, p, m = bed.size, len(pools['id']), len(nodes)
        flow_file = np.lib.format.open_memmap(out / 'node_water_m3.npy', mode='w+', dtype='f8', shape=(2, n))
        mouth_file = np.lib.format.open_memmap(out / 'mouth_water_m3.npy', mode='w+', dtype='f8', shape=(2, m))
        store_file = np.lib.format.open_memmap(out / 'pool_storage_m3.npy', mode='w+', dtype='f8', shape=(3, p))
        level_file = np.lib.format.open_memmap(out / 'pool_level_m.npy', mode='w+', dtype='f8', shape=(3, p))
        store_file[0] = 0
        level_file[0] = np.nan
        climate = load(terrain / 'climate_base.npy')
        annual = np.asarray(climate[2, ::3, ::3], dtype=np.float64).ravel()
        if not np.isfinite(annual).all() or np.any(annual < 0):
            raise ValueError('invalid annual TD precipitation')
        local = annual * (15 / 365) * .001 * .3 * 8100
        local[~(valid & ~ocean & ~unknown).ravel()] = 0
        budgets = []
        for i in range(2):
            storage = np.array(store_file[i], copy=True)
            flow, retained = route_pool_interval(local, route['order'], route['receiver'], arrays['pool_index'], pools['anchor'], pools['capacity_m3'], storage)
            flow_file[i] = flow
            mouth_file[i] = flow[nodes]
            store_file[i + 1] = storage
            level_file[i + 1] = levels(arrays['pool_index'], bed.ravel(), pools['spill_m'], storage, 8100.)
            outlets = (route['receiver'] < 0) & valid.ravel() & ~ocean.ravel()
            delivered = float(flow[nodes].sum() + flow[outlets].sum())
            input_m3 = float(local.sum())
            budgets.append(dict(local_m3=input_m3, retained_m3=float(retained), terminal_m3=delivered, residual_m3=input_m3-retained-delivered))
            for f in (flow_file, mouth_file, store_file, level_file):
                f.flush()
        record = dict(schema='game-hydro-v1', source_identity=source_identity, shape_zx=list(bed.shape), spacing_m=90, cell_area_m2=8100, origin_center_m=[-61440,-61440], ocean_level_m=0, source_paths=dict(terrain=str(terrain), routing=str(route_root), lowland=str(ROOT/'game-grade-lowland')), forcing='finite 30 day scenario: TD climate_base[2] annual precipitation mm/year, uniform annual rate; runoff coefficient 0.3, no evaporation or snow model', initial_pool_storage_m3=0, unknown_external_inflow='unknown; volumes represent known local component only', budgets=budgets, pool_count=p, mouth_count=m, runtime_seconds=time.monotonic()-start)
        import hashlib
        record['output_sha256'] = {}
        for path in sorted(out.rglob('*.npy')):
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                    digest.update(chunk)
            record['output_sha256'][path.relative_to(out).as_posix()] = digest.hexdigest()
        (out / 'manifest.json').write_text(json.dumps(record, indent=2), encoding='utf8')
        return record
    finally:
        marker.unlink(missing_ok=True)

class GameHydrologyProduct:
    """Mapped saved scenario. IDs are meaningful only with `identity`."""

    def __init__(self, directory, *, expected_identity=None, expected_product_identity=None):
        import hashlib

        self.directory = Path(directory)
        try:
            raw = (self.directory / 'manifest.json').read_bytes()
            self.manifest = json.loads(raw)
            m = self.manifest
            if m['schema'] != 'game-hydro-v1' or not isinstance(m['source_identity'], str) or not m['source_identity']:
                raise ValueError('invalid product source or schema')
            shape = tuple(m['shape_zx'])
            if len(shape) != 2 or any(type(x) is not int or x <= 0 for x in shape):
                raise ValueError('invalid grid shape')
            spacing = float(m['spacing_m'])
            area = float(m['cell_area_m2'])
            origin = np.asarray(m['origin_center_m'], dtype=float)
            if not np.isfinite([spacing, area]).all() or spacing <= 0 or area != spacing * spacing or origin.shape != (2,) or not np.isfinite(origin).all():
                raise ValueError('invalid grid geometry')
            self.manifest_sha256 = hashlib.sha256(raw).hexdigest()
            namespace = dict(source=m['source_identity'], shape=shape, spacing_m=spacing, origin=origin.tolist(), schema=m['schema'])
            self.identity = hashlib.sha256(json.dumps(namespace, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            self.product_identity = hashlib.sha256((self.identity + ':' + self.manifest_sha256).encode()).hexdigest()
            if expected_identity is not None and expected_identity != self.identity:
                raise ValueError('grid identity mismatch')
            if expected_product_identity is not None and expected_product_identity != self.product_identity:
                raise ValueError('product identity mismatch')
            p, mouths = m['pool_count'], m['mouth_count']
            if type(p) is not int or p < 0 or type(mouths) is not int or mouths < 0:
                raise ValueError('invalid counts')
            specs = {'time_seconds': (None,), 'node_water_m3': (None, shape[0] * shape[1]),
                     'mouth_water_m3': (None, mouths), 'mouth_unknown': (mouths,),
                     'pool_storage_m3': (None, p), 'pool_level_m': (None, p),
                     'derived/pool_index': (shape[0] * shape[1],),
                     'derived/pool_id': (p,), 'derived/mouth_id': (mouths,),
                     'derived/mouth_source': (mouths,), 'derived/total_water_unknown': (shape[0] * shape[1],)}
            self.arrays = {}
            for name, expected in specs.items():
                a = np.load(self.directory / (name + '.npy'), mmap_mode='r', allow_pickle=False)
                if len(a.shape) != len(expected) or any(want is not None and actual != want for actual, want in zip(a.shape, expected)) or a.dtype.kind not in 'biuf':
                    raise ValueError('invalid array: ' + name)
                self.arrays[name] = a
            t = self.arrays['time_seconds']
            if len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0):
                raise ValueError('invalid time boundaries')
            for name in ('node_water_m3', 'mouth_water_m3'):
                if self.arrays[name].shape[0] != len(t) - 1:
                    raise ValueError('invalid interval count')
            for name in ('pool_storage_m3', 'pool_level_m'):
                if self.arrays[name].shape[0] != len(t):
                    raise ValueError('invalid boundary count')
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError('invalid game hydrology product') from exc

    def query(self, z, x, interval):
        """Return known-local routed volume and actual pool state at interval end."""
        shape = self.manifest['shape_zx']
        if any(type(v) is not int for v in (z, x, interval)) or not (0 <= z < shape[0] and 0 <= x < shape[1] and 0 <= interval < len(self.arrays['time_seconds']) - 1):
            raise ValueError('query outside product')
        i = z * shape[1] + x
        pool = int(self.arrays['derived/pool_index'][i])
        if pool < -1 or pool >= self.manifest['pool_count']:
            raise ValueError('invalid pool index')
        result = dict(product_identity=self.product_identity, grid_identity=self.identity, known_local_volume_m3=float(self.arrays['node_water_m3'][interval, i]),
                      total_water_unknown=bool(self.arrays['derived/total_water_unknown'][i]), pool=None)
        if pool >= 0:
            result['pool'] = dict(id=int(self.arrays['derived/pool_id'][pool]),
                                  storage_m3=float(self.arrays['pool_storage_m3'][interval + 1, pool]),
                                  level_m=float(self.arrays['pool_level_m'][interval + 1, pool]))
        return result


def read_product(directory, *, expected_identity=None, expected_product_identity=None):
    return GameHydrologyProduct(directory, expected_identity=expected_identity, expected_product_identity=expected_product_identity)


def lifecycle_inputs(product, routing_directory, terrain_directory, interval=0):
    """Adapt the saved 90 m scenario to PartitionRouter without rebuilding terrain."""
    if interval not in (0, 1):
        raise ValueError('scenario interval outside saved forcing')
    m = product.manifest
    if m['spacing_m'] != 90 or m['cell_area_m2'] != 8100:
        raise ValueError('adapter requires the saved 90 m scenario')
    route = Path(routing_directory)
    terrain = Path(terrain_directory)
    paths = m['source_paths']
    if route.resolve() != Path(paths['routing']).resolve() or terrain.resolve() != Path(paths['terrain']).resolve():
        raise ValueError('scenario source paths mismatch')
    source = json.loads((terrain / 'manifest.json').read_text(encoding='utf8'))
    if source['identity'] != m['source_identity']:
        raise ValueError('terrain identity mismatch')
    load = lambda path: np.load(path, mmap_mode='r', allow_pickle=False)
    shape = tuple(m['shape_zx'])
    d = product.directory / 'derived'
    ids, anchors, capacities, spills = [load(d / (name + '.npy')) for name in ('pool_id', 'pool_anchor', 'pool_capacity_m3', 'pool_spill_m')]
    labels = product.arrays['derived/pool_index']
    if any(a.shape != ids.shape for a in (anchors, capacities, spills)) or np.any((labels < -1) | (labels >= len(ids))):
        raise ValueError('invalid pool table')
    basin = np.zeros(labels.size, dtype=np.uint64)
    present = labels >= 0
    basin[present] = ids[labels[present]]
    pools = [dict(id=str(int(ids[i])), anchor_index=int(anchors[i]), capacity_m3=float(capacities[i]), spill_stage_m=float(spills[i])) for i in range(len(ids))]
    arrays = {name: load(route / (name + '.npy')) for name in ('bed_m', 'valid_mask', 'ocean_mask')}
    arrays.update({name: load(route / 'routing' / (name + '.npy')).reshape(shape) for name in ('receiver', 'rank')})
    arrays.update(basin_id=basin.reshape(shape),
                  terminal_kind=load(d / 'terminal_type.npy').reshape(shape),
                  watershed_id=load(d / 'watershed_id.npy').reshape(shape),
                  total_water_unknown=product.arrays['derived/total_water_unknown'].reshape(shape))
    if any(a.shape != shape for a in arrays.values()):
        raise ValueError('routing grid mismatch')
    annual = np.asarray(load(terrain / 'climate_base.npy')[2, ::3, ::3], dtype=np.float64)
    if annual.shape != shape or not np.isfinite(annual).all() or np.any(annual < 0):
        raise ValueError('invalid climate grid')
    local = annual * (15 / 365) * .001 * .3 * 8100
    unknown = load(route / 'unknown_mask.npy')
    local[~(arrays['valid_mask'] & ~arrays['ocean_mask'] & ~unknown)] = 0
    manifest = dict(identity=product.identity, pools=pools, cell_area_m2=8100.)
    state = None
    if interval:
        state = dict(hydrology_identity=product.identity, source=product.identity, next_interval=interval,
                     storage_m3=np.asarray(product.arrays['pool_storage_m3'][interval]).tolist())
    return (manifest, arrays), local, state
