"""Fixed saved-source dynamic adapter scenarios, actual UTC evidence and static reload."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import traceback
import unittest
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline import surface_domain as adapter
from terrain_pipeline import surface_domain as mosaic
from terrain_pipeline.surface_domain import load_surface_domains
from tests.test_surface_domain import SAVED_DOMAIN_PATH, SAVED_DOMAIN_SHA256, SurfaceDynamicPrepareTests, forcing, generation_disabled
SAVED_MOSAIC_PATH = ROOT / 'verification/surface-fine-mosaic/run-20260930T123659.258177Z/single-proof-terminal.npz'
SAVED_MOSAIC_SHA256 = '8d4e26492f2b6314e2d6139717855870e3cdf296b1b814d7dde0e27347983617'

def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def independent_ledger(result):
    binding, dynamic = (result['binding'], result['dynamic'])
    inputs = dynamic['inputs']
    boundary = binding['boundary_mask']
    maximum = 0.0
    for step in range(dynamic['committed_steps']):
        before, after = dynamic['stage_m'][step:step + 2]
        edges = binding['edges']
        flux = inputs['conductance_m2_s'] * (before[edges[:, 0]] - before[edges[:, 1]])
        np.testing.assert_allclose(flux, dynamic['qedges_m3_s'][step], rtol=0, atol=1e-12)
        net = np.zeros(len(before))
        np.add.at(net, edges[:, 0], -flux)
        np.add.at(net, edges[:, 1], flux)
        expected = dynamic['storage_m3'][step].copy()
        expected[~boundary] += inputs['dt_s'] * (inputs['local_q_m3_s'][step, ~boundary] + net[~boundary])
        expected[boundary] = 0.0
        np.testing.assert_allclose(expected, dynamic['storage_m3'][step + 1], rtol=0, atol=1e-10)
        np.testing.assert_allclose(after[~boundary], binding['bed_m'][~boundary] + expected[~boundary] / binding['area_m2'][~boundary], rtol=0, atol=1e-12)
        storage_change = float(dynamic['storage_m3'][step + 1].sum() - dynamic['storage_m3'][step].sum())
        local = float(inputs['dt_s'] * inputs['local_q_m3_s'][step, ~boundary].sum())
        boundary_volume = float(-inputs['dt_s'] * net[boundary].sum())
        maximum = max(maximum, abs(storage_change - local - boundary_volume))
        np.testing.assert_allclose(dynamic['ledger_m3'][step, 1:3], [local, boundary_volume], rtol=0, atol=1e-10)
    return maximum

def retain(name, result, directory):
    path = directory / (name + '.npz')
    adapter.save_surface_dynamic(result, path)
    with ExitStack() as stack:
        generation_disabled(stack)
        loaded = adapter.load_surface_dynamic(path)
        adapter.query_surface_dynamic(loaded)
    if loaded['identity_sha256'] != result['identity_sha256']:
        raise AssertionError('identity changed on static reload')
    binding, dynamic = (loaded['binding'], loaded['dynamic'])
    internal = ~binding['boundary_mask']
    return {'bundle': str(path.resolve()), 'file_sha256': file_hash(path), 'identity_sha256': loaded['identity_sha256'], 'source_proof_sha256': binding['source_proof_sha256'], 'binding_sha256': binding['identity_sha256'], 'status': loaded['status'], 'committed_steps': dynamic['committed_steps'], 'static_no_generation_reload': True, 'nodes': len(binding['node_flat_ids']), 'edges': len(binding['edges']), 'node_flat_ids': binding['node_flat_ids'].tolist(), 'area_m2': binding['area_m2'].tolist(), 'wet_cells': len(binding['wet_cell_ids']), 'unique_wet_area_m2': float(binding['area_m2'].sum()), 'internal_area_m2': float(binding['area_m2'][internal].sum()), 'open_boundary_area_m2_not_internal_storage': float(binding['area_m2'][~internal].sum()), 'initial_internal_storage_m3': float(dynamic['storage_m3'][0].sum()), 'final_internal_storage_m3': float(dynamic['storage_m3'][-1].sum()), 'maximum_independent_qv_residual_m3': independent_ledger(loaded), 'signed_boundary_volume_into_internal_m3': float(dynamic['ledger_m3'][:, 2].sum()), 'caller_local_volume_m3': float(dynamic['ledger_m3'][:, 1].sum()), 'negative_edge_flux_values': int((dynamic['qedges_m3_s'] < 0).sum()), 'natural_outlets_certified': False, 'full_dynamic_wave_prepared': False}

def run_cases(directory, report, args):
    sources = (('saved-accepted-recovery-mosaic', SAVED_MOSAIC_PATH, SAVED_MOSAIC_SHA256), ('saved-prepared-old-domains', SAVED_DOMAIN_PATH, SAVED_DOMAIN_SHA256))
    report['source_files'] = []
    for name, path, expected_hash in sources:
        before = file_hash(path)
        if before != expected_hash:
            raise AssertionError('source evidence SHA256 differs: ' + str(path))
        report['source_files'].append({'name': name, 'path': str(path.resolve()), 'file_sha256': before})
    saved_mosaic = mosaic.load_fine_mosaic(SAVED_MOSAIC_PATH)
    binding = adapter.bind_surface_dynamic_source(saved_mosaic, vertical_datum=saved_mosaic['vertical_datum'])
    for name, kwargs in (('steady', {}), ('pulse', {'pulse': True}), ('tailwater-rise', {'raised': True})):
        result = adapter.prepare_surface_dynamic(binding, **forcing(binding, **kwargs))
        if result['status'] != 'completed':
            raise AssertionError('fixed positive did not complete: ' + name)
        report['cases'][name] = retain(name, result, directory)
    cancelled = adapter.prepare_surface_dynamic(binding, **forcing(binding, steps=4), cancel=lambda: True)
    report['cases']['cancelled-prefix'] = retain('cancelled-prefix', cancelled, directory)
    params = forcing(binding, steps=4)
    params['tailwater_m'][2:] = 100.0
    failed = adapter.prepare_surface_dynamic(binding, **params)
    if failed['status'] != 'failed' or failed['dynamic']['committed_steps'] != 1:
        raise AssertionError('fixed failed prefix changed')
    report['cases']['failed-tailwater-prefix'] = retain('failed-tailwater-prefix', failed, directory)
    domains = load_surface_domains(SAVED_DOMAIN_PATH)
    old_binding = adapter.bind_surface_dynamic_source(domains, domain_id=1, vertical_datum=domains['candidate']['inputs']['vertical_datum'])
    params = forcing(old_binding, steps=5)
    params['conductance_m2_s'][:] = 0.01
    params['dt_s'] = 0.1
    params['local_q_m3_s'][:, 0] = 0.1
    old = adapter.prepare_surface_dynamic(old_binding, **params)
    record = retain('saved-old-prepared-domain1', old, directory)
    if record['node_flat_ids'] != [9, 11, 16, 17, 23, 30, 37, 45] or record['area_m2'] != [22.0, 40.0, 48.0, 84.0, 55.0, 40.0, 33.0, 16.0] or record['initial_internal_storage_m3'] != 161.0 or (old['status'] != 'completed'):
        raise AssertionError('saved old prepared domain binding changed')
    report['cases']['saved-old-prepared-domain1'] = record
    for record in report['source_files']:
        record['unchanged'] = file_hash(Path(record['path'])) == record['file_sha256']
        if not record['unchanged']:
            raise AssertionError('source evidence changed')
    if not args.skip_tests:
        with (directory / 'focused-tests.txt').open('x', encoding='utf8') as stream:
            tests = unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceDynamicPrepareTests)
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(tests)
        report['focused_tests'] = {'run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors)}
        if not result.wasSuccessful():
            raise AssertionError('focused tests failed')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-tests', action='store_true')
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    directory = ROOT / 'verification/surface-dynamic-prepare' / ('run-' + started.strftime('%Y%m%dT%H%M%S.%fZ'))
    directory.mkdir(parents=True, exist_ok=False)
    report = {'started_utc': started.isoformat(), 'algorithm_version': adapter.SURFACE_DYNAMIC_PREPARE_VERSION, 'status': 'running', 'output_directory': str(directory.resolve()), 'cases': {}, 'source_files': [], 'natural_outlets_certified': False, 'full_dynamic_wave_prepared': False, 'implementation_files': {str(path.resolve()): file_hash(path) for path in (ROOT / 'terrain_pipeline/surface_domain.py', ROOT / 'tests/test_surface_domain.py', ROOT / 'tools/verify_surface_dynamic_prepare.py', ROOT / 'docs/surface-dynamic-prepare-v1.md')}, 'frozen_dependency_files': {str(path.resolve()): file_hash(path) for path in (ROOT / 'terrain_pipeline/surface_domain.py', ROOT / 'terrain_pipeline/surface_hydraulics.py')}}
    try:
        run_cases(directory, report, args)
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', error=str(error), traceback=traceback.format_exc())
        (directory / 'traceback.txt').write_text(report['traceback'], encoding='utf8')
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        with (directory / 'report.json').open('x', encoding='utf8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        print(json.dumps(report, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
