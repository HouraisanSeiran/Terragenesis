"""UTC fixed evidence: actual saved river endpoint plus explicit synthetic coast."""
from terrain_pipeline.surface_identity import _plain as _merged_coast__plain
import argparse
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
from unittest.mock import patch
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from terrain_pipeline import surface_domain as coast
from terrain_pipeline import surface_domain as consumer
from terrain_pipeline import surface_domain as recovery
from tests.test_surface_domain import SAVED_PREPARED, SAVED_PREPARED_SHA256, coherent_source_forgery, fixed_drop_inputs, reseal
SOURCE_FILES = ('terrain_pipeline/surface_domain.py', 'tests/test_surface_domain.py', 'tools/verify_surface_coast_drop.py', 'docs/surface-coast-drop-v1.md')
STATIC_DEPENDENCIES = ('terrain_pipeline/surface_domain.py',)

def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write('\n')

def source_hashes():
    return {name: {'path': str((ROOT / name).resolve()), 'file_sha256': file_sha256(ROOT / name)} for name in SOURCE_FILES}

def dependency_hashes():
    return {name: {'path': str((ROOT / name).resolve()), 'file_sha256': file_sha256(ROOT / name)} for name in STATIC_DEPENDENCIES}

def retain(directory, result):
    path = directory / 'actual-river-engineering-coast.npz'
    coast.save_coast_drop(result, path)
    before = file_sha256(path)
    with ExitStack() as stack:
        for name in ('prepare_coast_drop', '_attachment', '_stencil', '_triangles', '_corridor_cells', '_source_triangles', '_proof_gate', 'validate_surface_domains', '_sample'):
            stack.enter_context(patch.object(coast, name, side_effect=AssertionError('static load generated ' + name)))
        stack.enter_context(patch.object(consumer, '_fine_source', side_effect=AssertionError('fine resampling')))
        stack.enter_context(patch.object(consumer, '_proof_gate', side_effect=AssertionError('consumer proof generation')))
        stack.enter_context(patch.object(recovery, 'recover_surface_network', side_effect=AssertionError('recovery')))
        loaded = coast.load_coast_drop(path)
        queried = coast.query_coast_drop(loaded)
    record = {'bundle': str(path), 'bundle_file_sha256': before, 'bundle_unchanged': file_sha256(path) == before, 'identity_sha256': loaded['identity_sha256'], 'default_load_query_generation_disabled': True, 'static_validation': coast.validate_coast_drop(loaded), 'centerline_xyz_m': queried['arrays']['centerline_xyz_m'].tolist(), 'river_bed_xyz_m': queried['attachment']['river_bed_xyz_m'].tolist(), 'river_water_xyz_m': queried['attachment']['river_water_xyz_m'].tolist(), 'sea_bed_xyz_m': queried['attachment']['sea_bed_xyz_m'].tolist(), 'sea_water_xyz_m': queried['attachment']['sea_water_xyz_m'].tolist(), 'terminal_q_m3_s': queried['attachment']['terminal_q_m3_s'], 'cut_volume_m3': queried['ledger']['cut_volume_m3'], 'max_cut_depth_m': queried['ledger']['max_cut_depth_m'], 'source_model': coast.SOURCE_MODEL, 'natural_outlet_certified': False}
    write_json(directory / 'positive.json', record)
    np.testing.assert_allclose(loaded['arrays']['centerline_xyz_m'][:, 1], np.linspace(4.2, 0.0, 21))
    np.testing.assert_allclose(loaded['attachment']['river_water_xyz_m'][:, 1], [4.275, 4.2375, 4.2, 4.2])
    if not record['bundle_unchanged'] or loaded['identity_sha256'] != result['identity_sha256']:
        raise AssertionError('coast bundle identity changed')
    return record

def rejection(directory, name, callback):
    try:
        callback()
    except ValueError as error:
        record = {'rejected': True, 'reason': str(error), 'geometry_published': False}
        write_json(directory / (name + '.json'), record)
        return record
    raise AssertionError(name + ' unexpectedly accepted')

def fixed_cases(directory):
    if file_sha256(SAVED_PREPARED) != SAVED_PREPARED_SHA256:
        raise AssertionError('original saved prepared source changed')
    inputs = fixed_drop_inputs()
    attachment, corridor, sea, stations, budget = inputs
    result = coast.prepare_coast_drop(*inputs)
    positive = retain(directory, result)
    failures = {}
    for name, value in (('unknown_mask', True), ('protected_mask', True), ('wet_mask', False), ('valid_mask', False)):
        mask = getattr(corridor, name).copy()
        mask[10, 1] = value
        changed = replace(corridor, **{name: mask})
        failures[name] = rejection(directory, name, lambda changed=changed: coast.prepare_coast_drop(attachment, changed, sea, stations, budget))
    bed, h0 = (corridor.h2_m.copy(), corridor.h0_m.copy())
    bed[10, 1] = 20.0
    h0[10, 1] = 20.0
    changed = replace(corridor, h0_m=h0, h2_m=bed)
    failures['interior_ridge'] = rejection(directory, 'interior_ridge', lambda: coast.prepare_coast_drop(attachment, changed, sea, stations, budget))
    failures['skipped_cells'] = rejection(directory, 'skipped_cells', lambda: coast.prepare_coast_drop(attachment, corridor, sea, stations[::2], budget))
    failures['missing_sea'] = rejection(directory, 'missing_sea', lambda: coast.prepare_coast_drop(attachment, corridor, None, stations, budget))
    high_sea = replace(sea, sea_level_m=5.0, water_m=np.full_like(sea.water_m, 5.0))
    failures['high_sea'] = rejection(directory, 'high_sea', lambda: coast.prepare_coast_drop(attachment, corridor, high_sea, stations, budget))
    failures['cut_budget'] = rejection(directory, 'cut_budget', lambda: coast.prepare_coast_drop(attachment, corridor, sea, stations, coast.DropBudget(4.0, 0.0)))
    failures['resources'] = rejection(directory, 'resources', lambda: coast.prepare_coast_drop(*inputs, resources=coast.DropResources(max_vertices=83)))
    for name in ('bed_xyz_m', 'water_xyz_m', 'corridor_weights', 'h0_m'):
        forged = _merged_coast__plain(result)
        array = forged['arrays'][name].copy()
        array.flat[len(array.ravel()) // 2] += 0.5
        forged['arrays'][name] = array
        forged = reseal(forged)
        failures['rehash_' + name] = rejection(directory, 'rehash_' + name, lambda forged=forged: coast.validate_coast_drop(forged))
    forged = _merged_coast__plain(result)
    source = forged['inputs']['corridor']
    array = source['h2_m'].copy()
    array[10, 1] += 0.1
    source['h2_m'] = array
    source['identity_sha256'] = coast.fingerprint({key: value for key, value in source.items() if key != 'identity_sha256'})
    forged = reseal(forged)
    failures['rehash_source'] = rejection(directory, 'rehash_source', lambda: coast.validate_coast_drop(forged))
    for mode in ('water', 'Q', 'H0', 'grid'):
        forged = coherent_source_forgery(result, mode)
        failures['coherent_source_' + mode] = rejection(directory, 'coherent_source_' + mode, lambda forged=forged: coast.validate_coast_drop(forged))
    return {'positive': positive, 'rejections': failures}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-tests', action='store_true')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'verification/surface-coast-drop')
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    directory = args.output_root.resolve() / ('run-' + started.strftime('%Y%m%dT%H%M%S.%fZ'))
    directory.mkdir(parents=True, exist_ok=False)
    report = {'started_utc': started.isoformat(), 'status': 'running', 'algorithm': coast.SURFACE_COAST_DROP_VERSION, 'source_files': source_hashes(), 'saved_prepared_source': str(SAVED_PREPARED), 'static_dependency_files': dependency_hashes(), 'saved_prepared_source_file_sha256': file_sha256(SAVED_PREPARED), 'expected_prepared_source_file_sha256': SAVED_PREPARED_SHA256, 'scope': coast.MODE, 'natural_outlet_certified': False}
    write_json(directory / 'started.json', report)
    exit_code = 0
    try:
        report['cases'] = fixed_cases(directory)
        if not args.skip_tests:
            command = [sys.executable, '-m', 'unittest', 'tests.test_surface_domain.SurfaceCoastDropTests', '-v']
            process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            with (directory / 'focused-tests.log').open('x', encoding='utf-8') as stream:
                stream.write(process.stdout + process.stderr)
            report['tests'] = {'command': command, 'exit_code': process.returncode}
            if process.returncode:
                raise AssertionError('focused tests failed')
        else:
            report['tests'] = {'skipped': True}
        if source_hashes() != report['source_files'] or dependency_hashes() != report['static_dependency_files'] or file_sha256(SAVED_PREPARED) != SAVED_PREPARED_SHA256:
            raise AssertionError('source files changed during verification')
        report['status'] = 'passed'
    except Exception as error:
        exit_code = 1
        report.update({'status': 'failed', 'error_type': type(error).__name__, 'error': str(error)})
        with (directory / 'failure-traceback.log').open('x', encoding='utf-8') as stream:
            stream.write(traceback.format_exc())
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['source_files_at_finish'] = source_hashes()
        report['evidence_files'] = {path.name: {'file_sha256': file_sha256(path), 'size_bytes': path.stat().st_size} for path in sorted(directory.iterdir()) if path.is_file()}
        write_json(directory / 'report.json', report)
    print(json.dumps({'status': report['status'], 'report': str(directory / 'report.json')}, ensure_ascii=True))
    return exit_code
if __name__ == '__main__':
    raise SystemExit(main())
