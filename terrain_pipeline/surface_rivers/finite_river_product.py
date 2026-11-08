"""Read-only codec and query layer for the promoted finite-sample product.

Scope: this module only *reads* a promoted product directory and answers questions about the
already computed finite event; it never solves, routes, generates terrain or writes into the
product. ``write_product`` exists for the promotion tool and for explicit resumed outputs, and it
is atomic and non-overwriting. Nothing here imports the scratch drivers.

Coordinates: a stored cell ``(row, col)`` of the M1 window has reference point
``world_x = (origin_native_x + col) * 30 m`` (same for ``z``); ``--native`` means the caller passes
those native indices instead of metres. A point that does not land on a cell reference point, or
falls outside the 3951-cell drainage set, is refused rather than clipped or snapped.

Time: ``seconds_edges`` has ``intervals + 1`` entries including ``t = 0`` and ``t = end``. Interval
``i`` owns the half-open window ``[edges[i], edges[i+1])`` and its discharge; the lake state is
stored at edges. ``t = end`` answers the last interval and the end state, flagged ``asof``.
"""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.surface_rivers.finite_river_block_schedule import (
    BlockSchedule,
    layout_from_block_of,
)
from terrain_pipeline.surface_rivers.finite_river_event import (
    FiniteEventDomain,
    prepare_finite_event_domain,
)

PRODUCT_SCHEMA = 'finite-river-product-v1'
PRODUCT_DIRECTORY = Path('artifacts') / 'finite-river-sample-v1'
SPACING_M = 30.0
CELL_AREA_M2 = 900.0
KIND_CODES = ('inactive', 'interior', 'retained')
MAX_PRODUCT_BYTES = 512 * 1024 * 1024

DOMAIN_FILES = {'elevation_m': 'domain/elevation_m.npy',
                'resolved_mask': 'domain/resolved_mask.npy',
                'receiver': 'domain/receiver.npy',
                'terminal_kind_code': 'domain/terminal_kind_code.npy',
                'member_mask': 'domain/member_mask.npy',
                'reach_mask': 'domain/reach_mask.npy'}
EVENT_FILE = 'event/arrays.npz'
LAYOUT_FILES = {'block_of': 'layout/block_of.npy'}
EVENT_KEYS = ('seconds_edges', 'rain_mm_h', 'soil_states_mm', 'local_q_m3_s', 'routed_q_m3_s',
              'delivered_to_lake_m3', 'lake_volume_m3', 'lake_level_m', 'lake_wet_cells',
              'et_mm_land', 'release_mm_land')
META_KEYS = {'schema', 'created_at', 'role', 'capabilities', 'source_code_identity',
             'test_evidence', 'provenance', 'domain', 'time', 'model', 'forcing', 'layout',
             'checkpoints', 'features', 'files', 'limitations', 'gates'}


def repo_root(start=None):
    return Path(__file__).resolve().parents[2] if start is None else Path(start)


def default_product_directory(root=None):
    return (repo_root(root) / PRODUCT_DIRECTORY)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def array_sha(array):
    array = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode('ascii'))
    digest.update(array.dtype.str.encode('ascii'))
    digest.update(array.tobytes())
    return digest.hexdigest()


def _finite(value, label, *, positive=False):
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer,
                                                                    np.floating))
            or not np.isfinite(float(value)) or float(value) < 0
            or (positive and float(value) == 0.0)):
        raise ValueError('finite %srequired %s' % ('positive ' if positive else 'nonnegative ', label))
    return float(value)


class FiniteRiverProduct:
    """Loaded, validated finite-sample product; every array is read-only."""

    def __init__(self, directory, meta, arrays, checkpoint_meta):
        self.directory = Path(directory)
        self.meta = meta
        self.arrays = arrays
        self.checkpoint_meta = checkpoint_meta

    # -- metadata ---------------------------------------------------------
    @property
    def domain(self):
        return self.meta['domain']

    @property
    def time(self):
        return self.meta['time']

    @property
    def intervals(self):
        return int(self.meta['time']['intervals'])

    def identity(self):
        return {'product_schema': self.meta['schema'],
                'source_code_identity': self.meta['source_code_identity'],
                'test_evidence': self.meta['test_evidence'],
                'files': self.meta['files'],
                'provenance': self.meta['provenance']}

    # -- coordinate handling ---------------------------------------------
    def cell_of_world(self, x, z, *, native=False):
        domain = self.domain
        origin_x, origin_z = (int(value) for value in domain['origin_native_xz'])
        rows, columns = (int(value) for value in domain['grid_shape_zx'])
        if native:
            column = float(x) - origin_x
            row = float(z) - origin_z
        else:
            column = float(x) / SPACING_M - origin_x
            row = float(z) / SPACING_M - origin_z
        if (not np.isfinite(column)) or (not np.isfinite(row)):
            raise ValueError('finite point required')
        if abs(column - round(column)) > 1e-6 or abs(row - round(row)) > 1e-6:
            raise ValueError('point is not a 30 m cell reference point; no interpolation is offered')
        row_index, column_index = int(round(row)), int(round(column))
        if not (0 <= row_index < rows and 0 <= column_index < columns):
            raise ValueError('point is outside the declared finite window')
        flat = row_index * columns + column_index
        return {'row': row_index, 'column': column_index, 'cell_flat': flat,
                'world_m': [float((origin_x + column_index) * SPACING_M),
                            float((origin_z + row_index) * SPACING_M)]}

    def active_position(self, cell_flat):
        positions = self.arrays['active_index']
        index = int(np.searchsorted(positions, int(cell_flat)))
        if index >= positions.size or int(positions[index]) != int(cell_flat):
            return None
        return index

    def interval_of_time(self, time_s):
        seconds = _finite(time_s, 'physical time')
        edges = np.asarray(self.arrays['seconds_edges'], np.float64)
        end = float(edges[-1])
        if seconds > end + 1e-12:
            raise ValueError('physical time beyond the stored event (%.6f s > %.6f s)'
                             % (seconds, end))
        if seconds >= end - 1e-12:
            return {'time_s': seconds, 'interval_index': self.intervals - 1,
                    'state_edge': self.intervals, 'asof': 't=end',
                    'interval_seconds': [float(edges[-2]), float(edges[-1])]}
        interval = int(np.floor(seconds / float(self.time['dt_s']) + 1e-9))
        edge_value = float(edges[interval])
        state_edge = interval if abs(seconds - edge_value) <= 1e-9 else interval + 1
        return {'time_s': seconds, 'interval_index': interval, 'state_edge': state_edge,
                'asof': None if state_edge == interval else 'interval_end',
                'interval_seconds': [float(edges[interval]), float(edges[interval + 1])]}

    def lake_state(self, edge):
        edge = int(edge)
        if not 0 <= edge <= self.intervals:
            raise ValueError('state edge outside the stored event')
        volume = float(self.arrays['lake_volume_m3'][edge])
        return {'edge_index': edge,
                'time_s': float(self.arrays['seconds_edges'][edge]),
                'volume_m3': volume,
                'level_m': float(self.arrays['lake_level_m'][edge]),
                'wet_cells': int(self.arrays['lake_wet_cells'][edge]),
                'dry': volume == 0.0}

    # -- query ------------------------------------------------------------
    def query(self, x, z, time_s, *, native=False):
        cell = self.cell_of_world(x, z, native=native)
        position = self.active_position(cell['cell_flat'])
        if position is None:
            raise ValueError('point %s is outside the 3951-cell finite drainage set'
                             % (cell['world_m'],))
        window = self.interval_of_time(time_s)
        interval = window['interval_index']
        lake = self.lake_state(window['state_edge'])
        domain = self.domain
        safe_volume = float(domain['safe_capacity_m3'])
        return {
            'product_schema': self.meta['schema'],
            'query': {'point_m': cell['world_m'], 'input': [float(x), float(z)],
                      'coordinate_mode': 'native_grid' if native else 'world_metres'},
            'cell': {'row': cell['row'], 'column': cell['column'],
                     'cell_flat': cell['cell_flat'], 'active_position': position},
            'interval_index': interval,
            'state_edge_index': int(window['state_edge']),
            'time': {'requested_s': window['time_s'], 'interval_index': interval,
                     'interval_seconds': window['interval_seconds'],
                     'state_edge': window['state_edge'], 'state_time_s': lake['time_s'],
                     'asof': window['asof'],
                     'semantics': 'interval Q lives in [edges[i], edges[i+1]); state is stored at edges'},
            'local_q_m3_s': float(self.arrays['local_q_m3_s'][interval, position]),
            'routed_q_m3_s': float(self.arrays['routed_q_m3_s'][interval, position]),
            'lake': lake,
            'safety': {'safe_level_m': float(domain['safe_level_m']),
                       'safe_capacity_m3': safe_volume,
                       'lake_headroom_m3': safe_volume - lake['volume_m3'],
                       'lake_within_safe': bool(lake['volume_m3'] <= safe_volume)},
            'model': dict(self.meta['model']),
            'capabilities': dict(self.meta['capabilities']),
            'identity': {'product_schema': self.meta['schema'],
                         'source_code_identity': self.meta['source_code_identity'],
                         'files_sha256': self.meta['files']},
        }

    # -- explicit recovery ------------------------------------------------
    def domain_object(self):
        return rebuild_domain(self)

    def schedule_object(self):
        return rebuild_schedule(self)


def _require_file(path, size_limit=MAX_PRODUCT_BYTES):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError('product member missing: %s' % path.name)
    if path.stat().st_size > size_limit:
        raise ValueError('product member too large: %s' % path.name)
    return path


def load_product(directory=None, *, verify_files=True):
    """Load and validate a product; any schema, size, digest or shape mismatch refuses."""
    directory = Path(directory) if directory is not None else default_product_directory()
    meta_path = _require_file(directory / 'product.json', 4 * 1024 * 1024)
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    if set(meta) != META_KEYS:
        raise ValueError('product.json keys are not the declared set')
    if meta['schema'] != PRODUCT_SCHEMA:
        raise ValueError('unsupported product schema')
    files = meta['files']
    if not isinstance(files, dict) or not files:
        raise ValueError('product files map required')
    for relative, digest in files.items():
        if str(relative).startswith('/') or '..' in str(relative):
            raise ValueError('product file keys must be relative paths inside the product')
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError('product file digests must be sha256 hex')
        if verify_files and sha256_file(_require_file(directory / relative)) != digest:
            raise ValueError('product file digest mismatch: %s' % relative)
    arrays = {'active_index': np.load(_require_file(directory / 'event/active_index.npy')),
              'land_index': np.load(_require_file(directory / 'event/land_index.npy')),
              'lake_bed_index': np.load(_require_file(directory / 'event/lake_bed_index.npy')),
              'head_path_index': np.load(_require_file(directory / 'event/head_path_index.npy'))}
    with np.load(_require_file(directory / EVENT_FILE), allow_pickle=False) as archive:
        if set(archive.files) != set(EVENT_KEYS):
            raise ValueError('event arrays are not the declared set')
        for key in EVENT_KEYS:
            arrays[key] = np.array(archive[key])
    _validate_arrays(meta, arrays)
    checkpoints = {}
    for key, record in meta['checkpoints'].items():
        state = directory / record['state_path']
        manifest = directory / record['manifest_path']
        _require_file(state, 8 * 1024 * 1024)
        _require_file(manifest, 4 * 1024 * 1024)
        if verify_files:
            for path, digest in ((state, record['state_sha256']),
                                 (manifest, record['manifest_sha256'])):
                if sha256_file(path) != digest:
                    raise ValueError('checkpoint digest mismatch: %s' % path.name)
        checkpoints[key] = {'record': record, 'state_path': state, 'manifest_path': manifest}
    return FiniteRiverProduct(directory, meta, arrays, checkpoints)


def _validate_arrays(meta, arrays):
    domain = meta['domain']
    active = int(domain['active_cells'])
    land = int(domain['land_cells'])
    members = int(domain['lake_bed_cells'])
    intervals = int(meta['time']['intervals'])
    expected = {'active_index': ((active,), np.int64),
                'land_index': ((land,), np.int64),
                'lake_bed_index': ((members,), np.int64),
                'head_path_index': ((int(domain['head_path_cells']),), np.int64),
                'seconds_edges': ((intervals + 1,), np.float64),
                'rain_mm_h': ((intervals,), np.float64),
                'soil_states_mm': ((intervals + 1, 3, land), np.float64),
                'local_q_m3_s': ((intervals, active), np.float64),
                'routed_q_m3_s': ((intervals, active), np.float64),
                'delivered_to_lake_m3': ((intervals,), np.float64),
                'lake_volume_m3': ((intervals + 1,), np.float64),
                'lake_level_m': ((intervals + 1,), np.float64),
                'lake_wet_cells': ((intervals + 1,), np.int64),
                'et_mm_land': ((intervals, land), np.float64),
                'release_mm_land': ((intervals, land), np.float64)}
    for key, (shape, dtype) in expected.items():
        array = arrays[key]
        if array.shape != shape or array.dtype != dtype:
            raise ValueError('product array %s must be %s %s' % (key, dtype.__name__, shape))
        if array.dtype.kind == 'f' and not np.isfinite(array).all():
            raise ValueError('product array %s contains non-finite values' % key)
    edges = np.asarray(arrays['seconds_edges'])
    if not np.allclose(np.diff(edges), float(meta['time']['dt_s']), rtol=0, atol=1e-9):
        raise ValueError('product time edges are not uniform')
    if float(edges[0]) != 0.0:
        raise ValueError('product time edges must start at 0')
    positions = np.asarray(arrays['active_index'])
    if positions.size != active or (np.diff(positions) <= 0).any():
        raise ValueError('active cell index must be a strict ascending unique list')
    if (arrays['lake_volume_m3'] < 0).any():
        raise ValueError('lake volume must be nonnegative')
    if float(arrays['lake_volume_m3'].max()) > float(domain['safe_capacity_m3']):
        raise ValueError('stored lake inventory exceeds the declared safe capacity')
    if (arrays['local_q_m3_s'] < 0).any() or (arrays['routed_q_m3_s'] < 0).any():
        raise ValueError('discharge must be nonnegative')


def write_product(directory, *, meta, arrays, extra_files=()):
    """Publish a self-contained product atomically; an existing directory is never replaced."""
    target = Path(directory)
    if target.exists():
        raise FileExistsError('product directory already exists: %s' % target)
    meta = dict(meta)
    if set(meta) != META_KEYS:
        raise ValueError('product metadata keys are not the declared set')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.product-', dir=target.parent))
    try:
        files = {}
        def store(relative, writer):
            path = temporary / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            writer(path)
            files[relative] = sha256_file(path)
        for key, relative in DOMAIN_FILES.items():
            if key in arrays:
                store(relative, lambda path, value=arrays[key]: np.save(path, value))
        for key, relative in LAYOUT_FILES.items():
            if key in arrays:
                store(relative, lambda path, value=arrays[key]: np.save(path, value))
        for key in ('active_index', 'land_index', 'lake_bed_index', 'head_path_index'):
            store('event/%s.npy' % key,
                  lambda path, value=arrays[key]: np.save(path, np.asarray(value)))
        store(EVENT_FILE, lambda path: np.savez_compressed(
            path, **{key: arrays[key] for key in EVENT_KEYS}))
        for relative, source in extra_files:
            def copy(path, source=Path(source)):
                shutil.copyfile(source, path)
            store(relative, copy)
        meta['files'] = dict(files)
        (temporary / 'product.json').write_text(
            json.dumps(meta, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
        for name in ('product.json',):
            if not (temporary / name).is_file():
                raise ValueError('product member was not written: %s' % name)
        if target.exists():
            raise FileExistsError('product directory appeared while writing: %s' % target)
        os.rename(str(temporary), str(target))
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {'directory': str(target), 'files': files,
            'product_sha256': sha256_file(target / 'product.json')}


def rebuild_domain(product):
    """Rebuild the prepared finite domain from the product's own domain arrays."""
    if not isinstance(product, FiniteRiverProduct):
        raise ValueError('loaded finite river product required')
    domain = product.domain
    directory = product.directory
    elevation = np.load(directory / DOMAIN_FILES['elevation_m'])
    resolved = np.load(directory / DOMAIN_FILES['resolved_mask'])
    receiver = np.load(directory / DOMAIN_FILES['receiver'])
    codes = np.load(directory / DOMAIN_FILES['terminal_kind_code'])
    member = np.load(directory / DOMAIN_FILES['member_mask'])
    reach = np.load(directory / DOMAIN_FILES['reach_mask'])
    kinds = np.full(codes.shape, 'inactive', 'U24')
    for index, name in enumerate(KIND_CODES):
        kinds[codes == index] = name
    return prepare_finite_event_domain(
        elevation_m=elevation, resolved_mask=resolved, receiver=receiver,
        terminal_kind=kinds, member_mask=member, reach_mask=reach,
        cell_area_m2=float(domain['cell_area_m2']),
        safe_level_m=float(domain['safe_level_m']),
        safe_capacity_m3=float(domain['safe_capacity_m3']))


def rebuild_schedule(product):
    """Rebuild the block schedule recorded by the product (needed only for explicit recovery)."""
    block = product.meta['layout']
    domain = rebuild_domain(product)
    layout = layout_from_block_of(domain, np.load(product.directory / block['block_of_path']),
                                  block_count=int(block['block_count']),
                                  cuts=block['cuts'], label='product')
    return BlockSchedule(domain, layout, dispatch_order=block['dispatch_order'])


def checkpoint_parameters(product):
    return RunoffParameters(**product.meta['model']['parameters'])


def default_model_record(*, parameters, routing_policy, dt_s, intervals):
    return {'routing': routing_policy,
            'soil_kernel': 'terrain_pipeline.climate_forcing.advance_soil',
            'lake': 'exact piecewise-linear V(h) over the lake bed cells',
            'no_channel_storage': True,
            'channel_storage_m3': 0.0,
            'dt_s': float(dt_s), 'intervals': int(intervals),
            'parameters': {key: float(value) for key, value in vars(parameters).items()}}
