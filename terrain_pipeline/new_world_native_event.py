"""Native-grid finite runoff event using the saved flood and derived pools."""
import json
import os
import time
from pathlib import Path

import numpy as np
from numba import njit
from terrain_pipeline.new_world_game_hydrology import IDENTITY, ROOT, levels
from terrain_pipeline.runoff import LowlandRunoffConfig as LowlandRunoffConfig
from terrain_pipeline.drainage import route_pool_interval as route_pool_interval


@njit
def classify(order, receiver, labels, anchors, flow, ocean, unknown, valid, channel, capture, threshold):
    for j in range(order.size):
        i = order[j]
        p = labels[i]
        channel[i] = valid[i] and not ocean[i] and not unknown[i] and flow[i] >= threshold and (p < 0 or anchors[p] == i)
        target = receiver[i]
        if channel[i]:
            capture[i] = i
        elif target >= 0:
            capture[i] = capture[target]
        else:
            capture[i] = -1


def run(*, terrain=None, routing=None, output=None, source_identity=IDENTITY):
    start = time.monotonic()
    terrain = Path(terrain or ROOT / 'terrain-v3')
    routing = Path(routing or ROOT / 'native-final-routing-v1')
    out = Path(output or ROOT / 'native-event-v1')
    source = json.loads((terrain / 'manifest.json').read_text(encoding='utf8'))
    derived_meta = json.loads((routing / 'derived.json').read_text(encoding='utf8'))
    if source['identity'] != source_identity or derived_meta['cell_area_m2'] != 900:
        raise ValueError('source or area mismatch')
    out.mkdir(exist_ok=False)
    load = lambda p: np.load(p, mmap_mode='r', allow_pickle=False)
    bed = load(terrain / 'bed_m.npy')
    shape = bed.shape
    n = bed.size
    ocean, unknown, valid = (load(terrain / (x + '.npy')).ravel() for x in ('ocean_mask', 'unknown_mask', 'valid_mask'))
    climate = load(terrain / 'climate_base.npy')
    d = routing / 'derived'
    labels, anchors, capacity, spill, nodes, receivers, unknown_total = (load(d / (x + '.npy')) for x in ('pool_index','pool_anchor','pool_capacity_m3','pool_spill_m','mouth_source','mouth_ocean_receiver','total_water_unknown'))
    order, receiver = (load(routing / 'routing' / (x + '.npy')) for x in ('order','receiver'))
    p, m = len(anchors), len(nodes)
    if n != len(labels) or climate.shape[1:] != shape:
        raise ValueError('grid mismatch')
    local = np.lib.format.open_memmap(out / 'local_contribution_m3.npy', mode='w+', dtype='f8', shape=(n,))
    annual = climate[2].ravel()
    for a in range(0, n, 262144):
        b = min(a + 262144, n)
        v = annual[a:b]
        if not np.isfinite(v).all() or np.any(v < 0):
            raise ValueError('invalid precipitation')
        local[a:b] = v * (15 / 365 * .001 * .3 * 900) * (valid[a:b] & ~ocean[a:b] & ~unknown[a:b])
    local.flush()
    np.save(out / 'time_seconds.npy', np.array([0, 1296000, 2592000], dtype='i8'))
    for name, ids in [('mouth_world_xz_m', nodes), ('mouth_ocean_world_xz_m', receivers)]:
        xy = np.column_stack((ids % shape[1] * 30 - 61440, ids // shape[1] * 30 - 61440)).astype('f8')
        np.save(out / (name + '.npy'), xy)
    np.save(out / 'mouth_unknown.npy', unknown_total[nodes])
    if not np.all(ocean[receivers]):
        raise ValueError('mouth receiver is not source ocean')
    flows = np.lib.format.open_memmap(out / 'node_water_m3.npy', mode='w+', dtype='f8', shape=(2,n))
    mouth = np.lib.format.open_memmap(out / 'mouth_water_m3.npy', mode='w+', dtype='f8', shape=(2,m))
    stores = np.lib.format.open_memmap(out / 'pool_storage_m3.npy', mode='w+', dtype='f8', shape=(3,p))
    stages = np.lib.format.open_memmap(out / 'pool_level_m.npy', mode='w+', dtype='f8', shape=(3,p))
    stores[0] = 0
    stages[0] = np.nan
    budgets = []
    for interval in range(2):
        storage = np.array(stores[interval])
        flow, retained = route_pool_interval(local, order, receiver, labels, anchors, capacity, storage)
        flows[interval] = flow
        mouth[interval] = flow[nodes]
        stores[interval+1] = storage
        stages[interval+1] = levels(labels, bed.ravel(), spill, storage, 900.)
        terminal = 0.
        for a in range(0,n,262144):
            b = min(a+262144,n)
            terminal += float(flow[a:b][(receiver[a:b] < 0) & valid[a:b] & ~ocean[a:b]].sum())
        terminal += float(mouth[interval].sum())
        total = float(local.sum())
        budgets.append(dict(local_m3=total, retained_m3=float(retained), terminal_m3=terminal, residual_m3=total-retained-terminal))
        for f in (flows,mouth,stores,stages): f.flush()
        del flow
    channel = np.lib.format.open_memmap(out / 'channel_mask.npy', mode='w+', dtype='?', shape=(n,))
    capture = np.lib.format.open_memmap(out / 'capture_index.npy', mode='w+', dtype='i4', shape=(n,))
    config = LowlandRunoffConfig()
    classify(order, receiver, labels, anchors, flows[1], ocean, unknown, valid, channel, capture, config.channel_q_threshold_m3_s * 1296000)
    channel.flush(); capture.flush()
    record = dict(schema='native-event-v1', source_identity=source_identity, shape_zx=list(shape), spacing_m=30, cell_area_m2=900, origin_center_m=[-61440,-61440], source_paths=dict(terrain=str(terrain), routing=str(routing)), pool_count=p, mouth_count=m, budgets=budgets, forcing='annual TD precipitation mm/year * 0.3, uniform over 365 days; dry initial pools; no evaporation', unknown_external_inflow='unknown', channel_policy='interval 2 mean Q >= LowlandRunoffConfig.channel_q_threshold_m3_s; pool interiors excluded except overflow anchor; capture is downstream first channel index, -1 absent', channel_q_threshold_m3_s=config.channel_q_threshold_m3_s, runtime_seconds=time.monotonic()-start)
    tmp = out / 'manifest.tmp'
    tmp.write_text(json.dumps(record, indent=2), encoding='utf8')
    os.replace(tmp, out / 'manifest.json')
    return record


class NativeEventProduct:
    """Read saved native water; optional masks are explicitly selected products."""

    def __init__(self, directory, *, base_event=None, lowland=None, network=None):
        import hashlib

        self.directory = Path(directory).resolve()
        self.manifest = self._manifest(self.directory)
        m = self.manifest
        schema = m.get('schema')
        if schema not in ('native-event-v1', 'native-event-v3'):
            raise ValueError('unsupported native event schema')
        shape = tuple(m.get('shape_zx', ()))
        if len(shape) != 2 or any(type(v) is not int or v <= 0 for v in shape):
            raise ValueError('invalid event grid')
        if m.get('spacing_m') != 30 or m.get('cell_area_m2') != 900 or m.get('origin_center_m') != [-61440, -61440]:
            raise ValueError('invalid native grid geometry')
        self.shape = shape
        self.base_directory = self.directory
        self.base_manifest = m
        if schema == 'native-event-v3':
            reference = base_event if base_event is not None else m.get('base_event')
            if not reference:
                raise ValueError('corrected event requires base_event')
            self.base_directory = self._reference(reference)
            self.base_manifest = self._manifest(self.base_directory)
            if self.base_manifest.get('schema') != 'native-event-v1':
                raise ValueError('base event must be native-event-v1')
            self._check_grid(self.base_manifest, 'base event')
            if any(self.base_manifest.get(k) != m.get(k) for k in ('pool_count', 'mouth_count')):
                raise ValueError('base event count mismatch')
            if m.get('base_event') and self.base_directory != self._reference(m['base_event']):
                raise ValueError('base event path mismatch')
        paths = m['source_paths']
        base_paths = self.base_manifest['source_paths']
        for key in ('terrain', 'routing'):
            if self._reference(paths[key]) != self._reference(base_paths[key]):
                raise ValueError('source path mismatch: ' + key)
        terrain = self._reference(paths['terrain'])
        self.derived = self._reference(paths['routing']) / 'derived'
        source = self._manifest(terrain)
        if source.get('identity') != m.get('source_identity'):
            raise ValueError('terrain identity mismatch')
        n = shape[0] * shape[1]
        p = m['pool_count']
        mouths = m['mouth_count']
        if type(p) is not int or type(mouths) is not int or min(p, mouths) < 0:
            raise ValueError('invalid event counts')
        def mapped(directory, name, expected):
            try:
                a = np.load(directory / (name + '.npy'), mmap_mode='r', allow_pickle=False)
            except (OSError, ValueError) as exc:
                raise ValueError('missing or invalid array: ' + name) from exc
            if a.shape != expected or a.dtype.kind not in 'biuf':
                raise ValueError('invalid array shape or dtype: ' + name)
            return a
        self.arrays = {}
        times = np.load(self.base_directory / 'time_seconds.npy', mmap_mode='r', allow_pickle=False)
        if times.ndim != 1 or len(times) < 2 or np.any(np.diff(times) <= 0):
            raise ValueError('invalid time boundaries')
        self.arrays['time_seconds'] = times
        intervals = len(times) - 1
        for name, expected in [('node_water_m3', (intervals,n)), ('mouth_water_m3', (intervals,mouths)), ('pool_storage_m3', (intervals+1,p)), ('pool_level_m', (intervals+1,p))]:
            self.arrays[name] = mapped(self.directory, name, expected)
        if schema == 'native-event-v3':
            self.arrays['pool_capacity_m3'] = mapped(self.directory, 'pool_capacity_m3', (p,))
        self.labels = mapped(self.derived, 'pool_index', (n,))
        self.ids = mapped(self.derived, 'pool_id', (p,))
        self.unknown = mapped(self.derived, 'total_water_unknown', (n,))
        self.arrays['mouth_id'] = mapped(self.derived, 'mouth_id', (mouths,)) if (self.derived / 'mouth_id.npy').exists() else None
        self.arrays['mouth_source'] = mapped(self.derived, 'mouth_source', (mouths,))
        self.arrays['mouth_unknown'] = mapped(self.base_directory, 'mouth_unknown', (mouths,))
        self.arrays['mouth_world_xz_m'] = mapped(self.base_directory, 'mouth_world_xz_m', (mouths,2))
        self.arrays['mouth_ocean_world_xz_m'] = mapped(self.base_directory, 'mouth_ocean_world_xz_m', (mouths,2))
        self.arrays['local_contribution_m3'] = mapped(self.base_directory, 'local_contribution_m3', (n,))
        self.channel_selection_interval = 1
        self.channel_source = None
        if lowland is not None:
            low = self._reference(lowland)
            low_manifest = self._manifest(low)
            self._check_grid(low_manifest, 'lowland')
            if low_manifest.get('schema') != 'native-lowland-v1':
                raise ValueError('invalid lowland schema')
            self.arrays['channel_mask'] = mapped(low, 'channel_mask', shape).reshape(n)
            self.arrays['capture_index'] = mapped(low, 'capture_index', shape).reshape(n)
            self.channel_source = str(low)
        elif schema == 'native-event-v1':
            for name in ('channel_mask', 'capture_index'):
                self.arrays[name] = mapped(self.directory, name, (n,))
            self.channel_source = str(self.directory)
        self.network = None
        if network is not None:
            network_path = self._reference(network)
            nm = self._manifest(network_path)
            if nm.get('schema') != 'native-network-v4' or nm.get('source_identity') != m.get('source_identity'):
                raise ValueError('network identity or schema mismatch')
            if self._reference(nm['event_product']) != self.directory:
                raise ValueError('network event path mismatch')
            digest = hashlib.sha256((self.directory / 'manifest.json').read_bytes()).hexdigest()
            if nm.get('input_manifest_sha256', {}).get('event') != digest:
                raise ValueError('network event manifest mismatch')
            if lowland is not None:
                if self._reference(nm['source_paths']['lowland']) != low:
                    raise ValueError('network lowland path mismatch')
                low_hash = hashlib.sha256((low / 'manifest.json').read_bytes()).hexdigest()
                if nm.get('input_manifest_sha256', {}).get('lowland') != low_hash:
                    raise ValueError('network lowland manifest mismatch')
            self.network = network_path
        self.metadata = dict(channel_source=self.channel_source, channel_selection_interval=1,
            channel_policy=('explicit lowland day-30 selection' if lowland is not None else
                            'v1 day-30 selection' if schema == 'native-event-v1' else
                            'no channel selection supplied; inherited manifest channel_policy does not describe v3 files'),
            base_event=str(self.base_directory), network=str(self.network) if self.network else None)

    def _reference(self, path):
        path = Path(path)
        if path.is_absolute():
            return path.resolve()
        # Saved repository products use repository-relative paths. Also permit
        # portable paths relative to the product directory.
        repo = Path(__file__).resolve().parent.parent
        for candidate in (repo / path, self.directory / path, Path.cwd() / path):
            if candidate.exists():
                return candidate.resolve()
        return (repo / path).resolve()

    @staticmethod
    def _manifest(directory):
        try:
            return json.loads((directory / 'manifest.json').read_text(encoding='utf8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError('missing or invalid manifest: ' + str(directory)) from exc

    def _check_grid(self, other, label):
        for key in ('source_identity', 'shape_zx', 'spacing_m', 'cell_area_m2', 'origin_center_m'):
            if other.get(key) != self.manifest.get(key):
                raise ValueError(label + ' identity or grid mismatch: ' + key)

    def query(self, z, x, interval):
        rows, cols = self.shape
        if any(type(v) is not int for v in (z, x, interval)) or not (0 <= z < rows and 0 <= x < cols and 0 <= interval < len(self.arrays['time_seconds']) - 1):
            raise ValueError('outside product')
        i = z * cols + x
        p = int(self.labels[i])
        if p < -1 or p >= len(self.ids):
            raise ValueError('invalid pool index')
        pool = None if p < 0 else dict(id=int(self.ids[p]), storage_m3=float(self.arrays['pool_storage_m3'][interval+1,p]), level_m=float(self.arrays['pool_level_m'][interval+1,p]))
        channel = self.arrays.get('channel_mask')
        capture = self.arrays.get('capture_index')
        return dict(known_local_volume_m3=float(self.arrays['node_water_m3'][interval,i]), total_water_unknown=bool(self.unknown[i]), channel=None if channel is None else bool(channel[i]), capture_index=None if capture is None else int(capture[i]), channel_selection_interval=self.channel_selection_interval if channel is not None else None, channel_applies_to_interval=(interval == self.channel_selection_interval) if channel is not None else False, pool=pool)


def read_product(directory, *, base_event=None, lowland=None, network=None):
    return NativeEventProduct(directory, base_event=base_event, lowland=lowland, network=network)
