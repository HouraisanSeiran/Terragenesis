"""Prepare-only entry carrier, or explicitly run two events at two time limits."""
import argparse
import gc
import json
from pathlib import Path
import sys
import time
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, publish_bytes, save_bundle
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.td_entry_shallow_water import MAX_BYTES, MAX_WORK, FLAGS, build_entry_bed, build_geometry, build_forcing, check_resource, compare_levels, event_diagnostics, run_case
PARENT = ROOT / 'verification/natural-river-network/fine-bed-raster-lake-entry-20261005-01'
PINS = {'index.json': '113f3990de828f25f4b766afffa58c948a5d5aea12b9e2de05d383486795f759', 'independent-audit.json': '787ed835e848bc7b23158d845db2160495ae0ea01dfccf7813773d046d95b6ed', 'entry-readiness.json': '5ae6e8bedd664f1e1785bd2368c5be046ea06dc9809d52026739464fffabfdad'}
CODE = ('terrain_pipeline/td_entry_shallow_water.py', 'tools/prepare_td_entry_shallow_water.py', 'terrain_pipeline/shallow_water.py', 'terrain_pipeline/surface_hydraulics.py', 'terrain_pipeline/mountain_source_adapter.py', 'terrain_pipeline/basin_topology.py', 'terrain_pipeline/runoff.py')

def pin(path, record=None):
    result = dict(path=str(Path(path).resolve()), sha256=file_sha256(path), bytes=Path(path).stat().st_size)
    if record is not None:
        result['identity_sha256'] = record['identity_sha256']
    return result

def read_json(path, sha256, max_bytes=64 * 1024 ** 2):
    path = Path(path).resolve(strict=True)
    if not path.is_relative_to(ROOT) or path.stat().st_size > max_bytes or file_sha256(path) != sha256:
        raise ValueError('input_pin_path_or_budget_mismatch')
    with path.open(encoding='utf8') as stream:
        result = json.load(stream)
    check_resource()
    return result

def check_bundle(record):
    if identity(record['arrays'], record['metadata']) != record['identity_sha256']:
        raise ValueError('bundle_content_identity_mismatch')
    if any((not np.isfinite(value).all() for value in record['arrays'].values())):
        raise ValueError('nonfinite_bundle')

def save(path, record):
    check_resource()
    save_bundle(path, record, validator=check_bundle)
    check_resource()
    return pin(path, record)

def load(pin_record):
    result = load_bundle(pin_record['path'], expected_sha256=pin_record['sha256'], validator=check_bundle, max_bytes=MAX_BYTES)
    if result['identity_sha256'] != pin_record['identity_sha256']:
        raise ValueError('external_bundle_identity_mismatch')
    return result

def publish(path, record):
    publish_bytes(path, (json.dumps(record, sort_keys=True, allow_nan=False, indent=2) + '\n').encode())

def prepare(args):
    started = time.monotonic()
    index = read_json(PARENT / 'index.json', PINS['index.json'])
    audit = read_json(PARENT / 'independent-audit.json', PINS['independent-audit.json'])
    readiness = read_json(PARENT / 'entry-readiness.json', PINS['entry-readiness.json'])
    fine_pin = index['raster']
    if audit['status'] != 'passed' or audit['raster_sha256'] != fine_pin['sha256'] or audit['raster_identity_sha256'] != fine_pin['identity_sha256'] or (readiness['source_raster_sha256'] != fine_pin['sha256']) or (readiness['source_audit_sha256'] != PINS['independent-audit.json']):
        raise ValueError('parent_audit_readiness_not_bound')
    fine = read_json(fine_pin['path'], fine_pin['sha256'])
    inputs = {name: pin(PARENT / name) for name in PINS}
    inputs['fine'] = fine_pin
    loaded = {}
    for role, name in (('paths', '06_paths'), ('sections', '06_sections'), ('transitions', '09_transitions')):
        source_pin = index['inputs'][name]
        loaded[role] = read_json(source_pin['path'], source_pin['sha256'])
        if loaded[role]['identity_sha256'] != source_pin['identity_sha256']:
            raise ValueError('parent_identity_mismatch')
        inputs[role] = source_pin
    if readiness['source_transition_sha256'] != inputs['transitions']['sha256']:
        raise ValueError('readiness_transition_not_bound')
    hierarchy_pin = index['inputs']['hierarchy']
    hierarchy = load_basin_hierarchy(hierarchy_pin['path'], expected_sha256=hierarchy_pin['sha256'], expected_identity=hierarchy_pin['identity_sha256'])
    inputs['hierarchy'] = hierarchy_pin
    if fine['identity_sha256'] != fine_pin['identity_sha256']:
        raise ValueError('fine_identity_mismatch')
    carrier = build_entry_bed(hierarchy, loaded['paths'], loaded['sections'], loaded['transitions'], fine, readiness, entry_id=args.entry_id, margin_m=args.margin_m)
    geometry = build_geometry(carrier)
    forcing = build_forcing(carrier, geometry, duration_s=args.duration_s, interval_s=args.interval_s)
    code_sha256 = {name: file_sha256(ROOT / name) for name in CODE}
    manifest = dict(schema='td-entry-shallow-water-preparation-v1', status='prepared_not_hydraulically_verified', entry_id=carrier['metadata']['entry_id'], inputs=inputs, code_sha256=code_sha256, carrier=save(args.output / 'bed.npz', carrier), geometry=save(args.output / 'geometry.npz', geometry), forcing=save(args.output / 'forcing.npz', forcing), cases=[], declared_maxdt_s=[args.coarse_maxdt_s, args.fine_maxdt_s], resource=dict(actual_peak_rss_bytes=check_resource(), wall_s=time.monotonic() - started, max_bytes=MAX_BYTES, max_cells=65536, max_work=MAX_WORK, preparation_work_units=int(carrier['arrays']['source_bed_m'].size * 4 + len(carrier['arrays']['triangle_indices'])), water_solves=0), semantics='90m original native support, accepted edge+taper+unchanged lake support; local engineering window, not natural outlet or complete river', **FLAGS)
    publish(args.output / 'index.json', manifest)
    return manifest

def run(args):
    started = time.monotonic()
    index_path = args.input / 'index.json'
    parent = read_json(index_path, args.input_sha256)
    for name, sha256 in parent['code_sha256'].items():
        if file_sha256(ROOT / name) != sha256:
            raise ValueError('prepared_code_pin_changed')
    carrier, geometry, forcing = (load(parent[name]) for name in ('carrier', 'geometry', 'forcing'))
    maxdt = parent['declared_maxdt_s']
    if not 0 < maxdt[1] < maxdt[0]:
        raise ValueError('time_limits_not_refined')
    manifest = dict(schema='td-entry-shallow-water-run-v1', parent=pin(index_path), carrier=parent['carrier'], geometry=parent['geometry'], forcing=parent['forcing'], inputs=parent['inputs'], code_sha256=parent['code_sha256'], cases=[], comparisons=[], **FLAGS)
    work = parent['resource']['preparation_work_units']
    for case_index, case_name in enumerate(forcing['metadata']['case_names']):
        levels = []
        for level_index, dt in enumerate(maxdt):
            if work >= MAX_WORK:
                manifest['failure'] = 'total_work_budget_exhausted'
                break
            case_id = case_name + '-level-' + str(level_index)
            try:
                state, intervals, first_rk = run_case(carrier, geometry, forcing, case_index=case_index, max_dt_s=dt, work_limit=int((MAX_WORK - work) / 1.5))
            except (RuntimeError, ValueError, MemoryError) as error:
                manifest['cases'].append(dict(case_id=case_id, status='diagnostic_failure', failure=str(error)))
                manifest.update(status='diagnostic_failure', failure=str(error), resource=dict(actual_peak_rss_bytes=check_resource(), wall_s=time.monotonic() - started, work_before_failed_case=work, max_work=MAX_WORK, max_bytes=MAX_BYTES))
                publish(args.output / 'index.json', manifest)
                return manifest
            failed = state['metadata']['status'] != 'completed'
            work += state['metadata']['resource_work_upper_bound'] if failed else state['metadata']['face_evaluations'] * 3 // 2
            saved = dict(case_id=case_id, case_index=case_index, level=level_index, max_dt_s=dt, state=save(args.output / (case_id + '-state.npz'), state), intervals=save(args.output / (case_id + '-intervals.npz'), intervals), first_rk=save(args.output / (case_id + '-first-rk.npz'), first_rk), diagnostics=event_diagnostics(carrier, state, intervals), status='diagnostic_failure' if failed else 'saved_requires_independent_audit')
            manifest['cases'].append(saved)
            if failed:
                manifest.update(status='diagnostic_failure', failure=state['metadata']['failure'], resource=dict(actual_peak_rss_bytes=check_resource(), wall_s=time.monotonic() - started, work_reserved_upper_bound=work, max_work=MAX_WORK, max_bytes=MAX_BYTES))
                publish(args.output / 'index.json', manifest)
                return manifest
            levels.append((state, intervals))
            del first_rk
            gc.collect()
        if len(levels) == 2:
            comparison = compare_levels(levels[0][0], levels[1][0], levels[0][1], levels[1][1])
            comparison['case_name'] = case_name
            manifest['comparisons'].append(comparison)
        del levels
        gc.collect()
    manifest['resource'] = dict(actual_peak_rss_bytes=check_resource(), wall_s=time.monotonic() - started, total_face_and_preparation_work_units=work, max_work=MAX_WORK, max_bytes=MAX_BYTES, face_work_semantics='RK1+RK2+endpoint faces; endpoint included beyond solver face_evaluations')
    manifest['status'] = 'saved_requires_independent_audit'
    publish(args.output / 'index.json', manifest)
    return manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-only', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--input-sha256')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--entry-id', default='receiver:61623:61622')
    parser.add_argument('--margin-m', type=float, default=1.0)
    parser.add_argument('--duration-s', type=float, default=60.0)
    parser.add_argument('--interval-s', type=float, default=5.0)
    parser.add_argument('--coarse-maxdt-s', type=float, default=0.01)
    parser.add_argument('--fine-maxdt-s', type=float, default=0.005)
    args = parser.parse_args()
    args.output = args.output.resolve()
    allowed = (ROOT / 'verification/natural-river-network').resolve()
    if args.output.exists() or not args.output.is_relative_to(allowed) or (not args.output.name.startswith('entry-shallow-water-')):
        raise ValueError('new_entry_shallow_water_output_directory_required')
    if not 0 < args.fine_maxdt_s < args.coarse_maxdt_s:
        raise ValueError('invalid_maxdt_pair')
    if args.prepare_only and (not 0 < args.duration_s <= 120 or args.interval_s not in (5.0, 10.0)):
        raise ValueError('bounded_120s_window_with_5_or_10s_snapshot_interval_required')
    if args.run and (args.input is None or args.input_sha256 is None):
        parser.error('--run requires --input and --input-sha256')
    result = run(args) if args.run else prepare(args)
    print(json.dumps(dict(output=str(args.output), status=result['status'], cases=len(result['cases']), entry_id=result.get('entry_id'), resource=result.get('resource')), allow_nan=False))
if __name__ == '__main__':
    main()
