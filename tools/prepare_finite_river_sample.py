"""Promote the accepted M1/M2/M3 finite-sample evidence into one self-contained product.

This tool only reads the three accepted run trees, verifies their cross-consistency and the
declared gates, and publishes `artifacts/finite-river-sample-v1` atomically. It never runs the
physical kernels, never searches terrain and never regenerates a TD page: promotion is a copy plus
a digest/identity binding. An existing product directory is refused, never replaced.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.runoff import RunoffParameters as RunoffParameters  # noqa: E402
from terrain_pipeline.surface_rivers.finite_river_event import (  # noqa: E402
    ROUTING_POLICY,
    LakeStageCurve,
)
from terrain_pipeline.surface_rivers.finite_river_product import (  # noqa: E402
    DOMAIN_FILES,
    KIND_CODES,
    LAYOUT_FILES,
    PRODUCT_SCHEMA,
    default_model_record,
    default_product_directory,
    sha256_file,
    write_product,
)

KIND_CODE = {name: index for index, name in enumerate(KIND_CODES)}
DEFAULT_M1 = '.scratch/finite-river-sample/m1-domain-v1/results-main-v1/candidate-E-main-v1'
DEFAULT_M2 = '.scratch/finite-river-sample/m2-supply-v1/results-main-v1'
DEFAULT_M3 = '.scratch/finite-river-sample/m3-recovery-v1/results-main-v1'
CHANNEL_STORAGE_NOTE = ('quasi_steady_d8_no_channel_storage: each interval is routed and delivered '
                        'inside the same interval, so the product stores no in-transit channel '
                        'water and a checkpoint needs none')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def fail(message):
    print('FAILED: %s' % message, file=sys.stderr)
    return 2


def verify_sources(m1, m2, m3, checkpoint_key):
    """Explicit read-only verification of the three accepted evidence trees."""
    candidate = read_json(m1 / 'candidate.json')
    if not candidate.get('m1_ready') or not candidate.get('diag_selected'):
        raise ValueError('M1 candidate is not the accepted ready sample')
    catchment = candidate['catchment']
    if catchment['drainage_unknown_cells'] != 0 or catchment['unknown_cells_in_catchment'] != 0:
        raise ValueError('M1 catchment is not unknown-free')
    safe = catchment['event_safe']
    event = read_json(m2 / 'event' / 'event.json')
    if event.get('stage_status') != 'PASS' or not all(event['gates'].values()):
        raise ValueError('M2 event record is not PASS on every gate')
    ladder = read_json(m3 / 'index.json')
    if not ladder.get('all_ran') or any(record['status'] != 'PASS'
                                        for record in ladder['records']):
        raise ValueError('M3 ladder is not fully PASS')
    reference = read_json(m3 / 'reference' / 'reference.json')
    delivered = float(reference['delivered_total_m3'])
    if abs(delivered - float(event['water_account']['final_lake_m3'])) > 1e-6:
        raise ValueError('M3 reference and M2 event disagree on the delivered total')
    m2_arrays_path = m2 / 'event' / 'event-arrays.npz'
    m3_arrays_path = m3 / 'reference' / 'arrays.npz'
    with np.load(m2_arrays_path) as left, np.load(m3_arrays_path) as right:
        for key in ('seconds_edges', 'rain_mm_h', 'local_q_m3_s_active', 'delivered_to_lake_m3',
                    'lake_volume_m3', 'lake_level_m', 'lake_wet_cells'):
            name = 'local_q_m3_s' if key == 'local_q_m3_s_active' else key
            if not np.array_equal(np.asarray(left[key]), np.asarray(right[name])):
                raise ValueError('M2 and M3 disagree on %s' % key)
    checkpoint_dir = m3 / ('ckpt-%s' % checkpoint_key)
    manifest = read_json(checkpoint_dir / 'manifest.json')
    if manifest['interval_index'] != int(checkpoint_key.lstrip('k')):
        raise ValueError('checkpoint index disagrees with its directory name')
    if manifest['identity']['model'] != 'quasi_steady_d8_no_channel_storage':
        raise ValueError('checkpoint model declaration moved')
    return candidate, event, reference, manifest, ladder


def build_payload(args):
    m1 = Path(args.m1_dir)
    m2 = Path(args.m2_dir)
    m3 = Path(args.m3_dir)
    candidate, event, reference, manifest, ladder = verify_sources(m1, m2, m3,
                                                                  args.checkpoint_key)
    catchment = candidate['catchment']
    safe = catchment['event_safe']
    origin = candidate['source']['origin_native_xz']
    rows, columns = candidate['source']['shape_zx']
    spacing = float(candidate['source']['spacing_m'])
    with np.load(m1 / 'evidence' / 'inputs_and_routing.npz') as archive:
        elevation = np.ascontiguousarray(archive['elevation_m'], np.float64)
        resolved = np.ascontiguousarray(archive['resolved_mask'], bool)
        receiver = np.ascontiguousarray(archive['receiver'], np.int64)
        kinds = np.ascontiguousarray(archive['terminal_kind'])
        unknown = np.ascontiguousarray(archive['upstream_unknown_mask'], bool)
    with np.load(m1 / 'evidence' / 'catchment_masks.npz') as archive:
        member = np.ascontiguousarray(archive['member_mask'], bool)
        reach = np.ascontiguousarray(archive['reach_mask'], bool)
    if unknown.reshape(-1)[reach].any():
        raise ValueError('M1 evidence carries unknown upstream cells inside the reach')
    if elevation.shape != (rows, columns):
        raise ValueError('M1 elevation shape disagrees with the candidate record')
    codes = np.zeros(elevation.shape, np.int8)
    for name, index in KIND_CODE.items():
        codes[kinds == name] = index
    with np.load(m2 / 'event' / 'event-arrays.npz') as archive:
        active_index = np.ascontiguousarray(archive['active_index'], np.int64)
        land_index = np.ascontiguousarray(archive['land_index'], np.int64)
        lake_bed_index = np.ascontiguousarray(archive['lake_bed_index'], np.int64)
        head_path_index = np.ascontiguousarray(archive['head_path_index'], np.int64)
    with np.load(m3 / 'reference' / 'arrays.npz') as archive:
        arrays = {key: np.ascontiguousarray(archive[key]) for key in
                  ('seconds_edges', 'rain_mm_h', 'soil_states_mm', 'local_q_m3_s',
                   'routed_q_m3_s', 'delivered_to_lake_m3', 'lake_volume_m3', 'lake_level_m',
                   'lake_wet_cells', 'et_mm_land', 'release_mm_land')}
    with np.load(m3 / 'blocks2-forward' / 'arrays.npz') as archive:
        block_of = np.ascontiguousarray(archive['block_of'], np.int64)
    parameters = RunoffParameters(**event['parameters'])
    intervals = int(arrays['seconds_edges'].size) - 1
    dt_s = float(arrays['seconds_edges'][1] - arrays['seconds_edges'][0])
    # independent re-derivation of the lake curve and the cell membership, not a copy of a role
    bed = np.sort(elevation.reshape(-1)[member])
    curve = LakeStageCurve(bed, 900.0)
    if abs(float(curve.volume(float(safe['safe_level_m']))) - float(safe['safe_capacity_m3'])) > 1e-9:
        raise ValueError('lake curve re-derivation disagrees with the declared safe capacity')
    if int(reach.sum()) != 3951 or int(member.sum()) != 16 or int((reach & ~member).sum()) != 3935:
        raise ValueError('M1 membership is not the accepted 3951/3935/16 support')
    if float(arrays['lake_volume_m3'].max()) > float(safe['safe_capacity_m3']):
        raise ValueError('stored lake inventory exceeds the declared safe capacity')
    world = lambda flat: [float((int(origin[0]) + int(flat) % columns) * spacing),
                          float((int(origin[1]) + int(flat) // columns) * spacing)]
    mid_flat = int(head_path_index[head_path_index.size // 2])
    terminal_flat = int(np.flatnonzero(reach & (receiver.reshape(-1) < 0))[0])
    arrays.update({'elevation_m': elevation, 'resolved_mask': resolved, 'receiver': receiver,
                   'terminal_kind_code': codes, 'member_mask': member, 'reach_mask': reach,
                   'active_index': active_index, 'land_index': land_index,
                   'lake_bed_index': lake_bed_index, 'head_path_index': head_path_index,
                   'block_of': block_of})
    meta = {
        'schema': PRODUCT_SCHEMA,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'role': 'finite_sample_default_consumption',
        'capabilities': {'finite_sample_complete': True, 'world_complete': False,
                         'hydraulic_ready': False, 'natural_outlet_verified': False,
                         'publishable': False, 'restart_verified': True,
                         'wave_level_restart': False},
        'source_code_identity': args.source_code_identity,
        'test_evidence': args.test_evidence,
        'provenance': {'m1': {'path': str(args.m1_dir).replace('\\', '/'),
                              'candidate': 'E-main-v1', 'head_id': candidate['sample']['head_id']},
                       'm2': {'path': str(args.m2_dir).replace('\\', '/'),
                              'event_sha256': sha256_file(m2 / 'event' / 'event.json')},
                       'm3': {'path': str(args.m3_dir).replace('\\', '/'),
                              'reference_sha256': sha256_file(m3 / 'reference' / 'arrays.npz')},
                       'prepared_by': 'tools/prepare_finite_river_sample.py',
                       'physical_rerun': False},
        'domain': {'origin_native_xz': [int(origin[0]), int(origin[1])],
                   'origin_m_xz': [float(int(origin[0]) * spacing),
                                   float(int(origin[1]) * spacing)],
                   'spacing_m': spacing, 'cell_area_m2': 900.0,
                   'grid_shape_zx': [int(rows), int(columns)],
                   'active_cells': int(reach.sum()),
                   'land_cells': int((reach & ~member).sum()),
                   'lake_bed_cells': int(member.sum()),
                   'terminal_cell_flat': terminal_flat,
                   'terminal_world_m': world(terminal_flat),
                   'head_path_cells': int(head_path_index.size),
                   'safe_level_m': float(safe['safe_level_m']),
                   'safe_capacity_m3': float(safe['safe_capacity_m3']),
                   'd8_min_cut_m': float(safe['d8_min_cut_m']),
                   'world_convention': ('cell reference point: world = (origin_native + index) * 30 m; '
                                        'no interpolation between cells'),
                   'support_identity': {'active_mask_sha256': sha256_file(
                       m1 / 'evidence' / 'catchment_masks.npz')}},
        'time': {'dt_s': dt_s, 'intervals': intervals,
                 'start_s': 0.0, 'end_s': float(arrays['seconds_edges'][-1]),
                 'seconds_edges': [float(value) for value in arrays['seconds_edges']],
                 'interval_semantics': ('interval i owns [edges[i], edges[i+1]) and its discharge; '
                                        'lake state is stored at edges[i]')},
        'model': default_model_record(parameters=parameters, routing_policy=ROUTING_POLICY,
                                      dt_s=dt_s, intervals=intervals),
        'forcing': {'kind': event['forcing']['kind'],
                    'rain_mm_h_by_interval': [float(value) for value in arrays['rain_mm_h']],
                    'total_rain_m3': float(event['water_account']['rain_m3'])},
        'layout': {'block_count': 2, 'cuts': [119, 173, 228], 'dispatch_order': 'forward',
                   'block_of_path': LAYOUT_FILES['block_of'],
                   'block_of_sha256': None, 'used_for': 'explicit recovery only'},
        'checkpoints': {args.checkpoint_key: {
            'interval_index': int(manifest['interval_index']),
            'elapsed_s': float(manifest['elapsed_s']),
            'lake_volume_m3': float(manifest['lake_volume_m3']),
            'cumulative': {key: float(value) for key, value in manifest['cumulative'].items()},
            'initial': {key: float(value) for key, value in manifest['initial'].items()},
            'state_path': 'checkpoints/%s/state.npz' % args.checkpoint_key,
            'manifest_path': 'checkpoints/%s/manifest.json' % args.checkpoint_key,
            'state_sha256': sha256_file(m3 / ('ckpt-%s' % args.checkpoint_key) / 'state.npz'),
            'manifest_sha256': sha256_file(m3 / ('ckpt-%s' % args.checkpoint_key)
                                          / 'manifest.json')}},
        'features': {'head_world_m': world(int(head_path_index[0])),
                     'mid_world_m': world(mid_flat),
                     'lake_world_m': world(terminal_flat),
                     'head_path_world_m': [world(int(flat)) for flat in head_path_index]},
        'files': {},
        'limitations': [
            'finite sample only: one 3951-cell drainage set inside the declared window; '
            'world_complete is false',
            CHANNEL_STORAGE_NOTE,
            'no travel time, no wave-level restart and no transient hydraulics are claimed',
            'the lake is an event-bounded stock; above the safe level the sample is refused rather '
            'than spilled',
            'hydraulic_ready, natural_outlet_verified and publishable stay false; this product '
            'completes nothing outside the finite sample',
        ],
        'gates': {'m2_event_status': event['stage_status'],
                  'm2_gates_passed': int(sum(1 for value in event['gates'].values() if value)),
                  'm3_ladder_all_ran': bool(ladder['all_ran']),
                  'm3_stages': len(ladder['records']),
                  'm3_reference_delivered_m3': float(reference['delivered_total_m3']),
                  'm2_m3_arrays_identical': True,
                  'source_verification': 'M2/M3 shared arrays compared element-wise at promotion'},
    }
    extra_files = [('checkpoints/%s/state.npz' % args.checkpoint_key,
                    m3 / ('ckpt-%s' % args.checkpoint_key) / 'state.npz'),
                   ('checkpoints/%s/manifest.json' % args.checkpoint_key,
                    m3 / ('ckpt-%s' % args.checkpoint_key) / 'manifest.json')]
    return meta, arrays, extra_files, candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--m1-dir', default=DEFAULT_M1)
    parser.add_argument('--m2-dir', default=DEFAULT_M2)
    parser.add_argument('--m3-dir', default=DEFAULT_M3)
    parser.add_argument('--checkpoint-key', default='k8')
    parser.add_argument('--output-dir', default=str(default_product_directory(ROOT)))
    parser.add_argument('--dry-run', action='store_true',
                        help='verify and describe the product without writing it')
    arguments = parser.parse_args(argv)
    arguments.m1_dir = ROOT / arguments.m1_dir if not Path(arguments.m1_dir).is_absolute() \
        else Path(arguments.m1_dir)
    arguments.m2_dir = ROOT / arguments.m2_dir if not Path(arguments.m2_dir).is_absolute() \
        else Path(arguments.m2_dir)
    arguments.m3_dir = ROOT / arguments.m3_dir if not Path(arguments.m3_dir).is_absolute() \
        else Path(arguments.m3_dir)
    watch = ['tools/publish_domain_bundle.py',
             'terrain_pipeline/surface_rivers/finite_river_product.py',
             'terrain_pipeline/surface_rivers/finite_river_event.py',
             'terrain_pipeline/surface_rivers/finite_river_block_schedule.py',
             'tools/prepare_finite_river_sample.py']
    tests = ['tests/test_finite_river_product.py', 'tests/test_publish_domain_bundle.py']
    missing = [name for name in watch + tests if not (ROOT / name).is_file()]
    if missing:
        return fail('product identity files are missing: %s' % missing)
    arguments.source_code_identity = {name: sha256_file(ROOT / name) for name in watch}
    arguments.test_evidence = {name: sha256_file(ROOT / name) for name in tests}
    try:
        meta, arrays, extra_files, candidate = build_payload(arguments)
    except (ValueError, OSError, KeyError, FileNotFoundError) as error:
        return fail('verification refused: %s: %s' % (type(error).__name__, error))
    meta['layout']['block_of_sha256'] = _block_sha(arrays['block_of'])
    summary = {'product_dir': arguments.output_dir, 'schema': meta['schema'],
               'domain': meta['domain'], 'time': {'dt_s': meta['time']['dt_s'],
                                                  'intervals': meta['time']['intervals']},
               'checkpoints': sorted(meta['checkpoints']),
               'files': len(arrays), 'dry_run': arguments.dry_run,
               'source_code_identity': meta['source_code_identity']}
    if arguments.dry_run:
        print(json.dumps(summary, indent=2, default=str))
        return 0
    try:
        published = write_product(arguments.output_dir, meta=meta, arrays=arrays,
                                  extra_files=extra_files)
    except FileExistsError as error:
        return fail('refusing to overwrite an existing product: %s' % error)
    summary['published'] = published
    print(json.dumps(summary, indent=2, default=str))
    return 0


def _block_sha(block_of):
    import hashlib
    block_of = np.ascontiguousarray(block_of)
    digest = hashlib.sha256()
    digest.update(str(block_of.shape).encode('ascii'))
    digest.update(block_of.dtype.str.encode('ascii'))
    digest.update(block_of.tobytes())
    return digest.hexdigest()


if __name__ == '__main__':
    sys.exit(main())
