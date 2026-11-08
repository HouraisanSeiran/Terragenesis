"""Fixed vertex-prism evidence; only new run directories are published."""
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline import surface_domain as storage
from tests.test_surface_domain import _test_surface_multidomain_dynamic_forcing as forcing
from tests.test_surface_domain import TEST_SURFACE_VARIABLE_STORAGE_SOURCE as SOURCE, SurfaceVariableStorageTests, _test_surface_variable_storage_fixture as fixture, static_disabled
SOURCE_SHA256 = 'c85e8ef84b896df2f2f3e48d2c062bc9b9c0ddd66d4cf0b56320ef6cc6ea16cd'

def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def retain(name, record, directory):
    path = directory / (name + '.npz')
    storage.save_surface_variable_storage(record, path)
    with ExitStack() as stack:
        static_disabled(stack)
        loaded = storage.load_surface_variable_storage(path)
        storage.query_surface_variable_storage(loaded)
    if loaded['identity_sha256'] != record['identity_sha256']:
        raise AssertionError('saved identity changed')
    return {'path': str(path.resolve()), 'file_sha256': file_hash(path), 'identity_sha256': loaded['identity_sha256'], 'status': loaded['status'], 'committed_steps': loaded['committed_steps'], 'failed_step': dict(loaded['failed_step']) if loaded['failed_step'] is not None else None, 'physical_duration_s': float(loaded['time_s'][-1]), 'initial_internal_storage_m3': float(loaded['storage_m3'][0].sum()), 'initial_domain_storage_m3': [float(loaded['storage_m3'][0, first:last].sum()) for first, last in zip(loaded['source']['node_offsets'][:-1], loaded['source']['node_offsets'][1:])], 'maximum_domain_residual_m3': float(np.abs(loaded['domain_ledger_m3'][:, :, 5]).max()) if loaded['committed_steps'] else 0.0, 'maximum_global_residual_m3': float(np.abs(loaded['ledger_m3'][:, 5]).max()) if loaded['committed_steps'] else 0.0, 'static_no_generation': True}

def independent_algebra(record):
    source = record['source']
    boundary = source['dynamic']['inputs']['boundary_mask']
    volumes = np.zeros_like(record['storage_m3'])
    areas = []
    global_node = 0
    for binding in source['bindings']:
        fine = binding['source_mosaic']
        area = fine['grid']['spacing_x_m'] * fine['grid']['spacing_z_m'] / 6
        for local_node in range(len(binding['node_flat_ids'])):
            corners = []
            for cell, owner in zip(binding['wet_cell_ids'], binding['wet_cell_owner']):
                if owner == local_node:
                    for triangle in fine['triangles'][2 * cell:2 * cell + 2]:
                        corners.extend(fine['nodes']['h2_m'][triangle].tolist())
            beds = np.asarray(corners)
            areas.append(float(area * np.count_nonzero(beds == beds.min())))
            if not boundary[global_node]:
                volumes[:, global_node] = (area * np.maximum(record['stage_m'][:, global_node, None] - beds, 0)).sum(axis=1)
            global_node += 1
    np.testing.assert_allclose(record['storage_m3'], volumes, atol=1e-10, rtol=1e-12)
    np.testing.assert_allclose(volumes[0].sum(), 224.5721879136545, atol=1e-10, rtol=0)
    edges = source['edges']
    for step in range(record['committed_steps']):
        flux = record['conductance_m2_s'] * (record['stage_m'][step, edges[:, 0]] - record['stage_m'][step, edges[:, 1]])
        net = np.zeros(len(boundary))
        for endpoints, rate in zip(edges, flux):
            net[endpoints[0]] -= rate
            net[endpoints[1]] += rate
        expected = record['storage_m3'][step] + record['dt_s'] * (record['local_q_m3_s'][step] + net)
        expected[boundary] = 0
        np.testing.assert_allclose(record['qedges_m3_s'][step], flux, atol=1e-12, rtol=0)
        np.testing.assert_allclose(record['storage_m3'][step + 1], expected, atol=1e-10, rtol=0)
        rows = []
        for first, last in zip(source['node_offsets'][:-1], source['node_offsets'][1:]):
            before = record['storage_m3'][step, first:last].sum()
            after = record['storage_m3'][step + 1, first:last].sum()
            mask = boundary[first:last]
            local = record['dt_s'] * record['local_q_m3_s'][step, first:last][~mask].sum()
            inward = -record['dt_s'] * net[first:last][mask].sum()
            rows.append([before, local, inward, after, after - before, after - before - local - inward])
        np.testing.assert_allclose(record['domain_ledger_m3'][step], rows, atol=1e-10, rtol=0)
        np.testing.assert_allclose(record['ledger_m3'][step], np.sum(rows, axis=0), atol=1e-10, rtol=0)
    return sorted(set(areas))

def main():
    started = datetime.now(timezone.utc)
    directory = ROOT / 'verification/surface-variable-storage' / ('run-' + started.strftime('%Y%m%dT%H%M%S.%fZ'))
    directory.mkdir(parents=True, exist_ok=False)
    implementation = ('terrain_pipeline/surface_domain.py', 'tests/test_surface_domain.py', 'tools/verify_surface_variable_storage.py', 'docs/surface-variable-storage-v1.md')
    report = {'started_utc': started.isoformat(), 'status': 'running', 'source_path': str(SOURCE.resolve()), 'source_file_sha256': file_hash(SOURCE), 'algorithm_version': storage.SURFACE_VARIABLE_STORAGE_VERSION, 'geometry': storage.SURFACE_VARIABLE_STORAGE_GEOMETRY, 'implementation_sha256': {str((ROOT / item).resolve()): file_hash(ROOT / item) for item in implementation}, 'cases': {}, 'limits': 'vertex-prism piecewise linear V(h), fixed wet footprint and linear K; no exact continuous partial-triangle integral, inertia, measured sections, natural certification or frontend acceptance', 'independent_coordinator_review': 'pending', 'natural_outlets_certified': False, 'full_dynamic_wave_prepared': False}
    try:
        if report['source_file_sha256'] != SOURCE_SHA256:
            raise AssertionError('accepted source file changed')
        source, base, pulse, raised = fixture()
        report['source_identity_sha256'] = source['identity_sha256']
        report['binding_sha256'] = [item['identity_sha256'] for item in source['bindings']]
        report['counts'] = {'nodes': len(source['node_keys']), 'edges': len(source['edges']), 'boundary': int(source['dynamic']['inputs']['boundary_mask'].sum()), 'wet_cells': sum((len(item['wet_cell_ids']) for item in source['bindings']))}
        if report['counts'] != {'nodes': 16, 'edges': 14, 'boundary': 2, 'wet_cells': 676}:
            raise AssertionError('fixed source counts changed')
        failed_values = forcing()
        failed_values['tailwater_m'][2:] = 100.0
        failed = storage.prepare_surface_variable_storage(source, **failed_values)
        cancelled = storage.prepare_surface_variable_storage(source, **forcing(), cancel=lambda: True)
        cases = {'baseline': base, 'pulse': pulse, 'domain2-tailwater-rise': raised, 'failed-prefix': failed, 'cancelled-prefix': cancelled}
        for name, record in cases.items():
            report['minimum_positive_area_m2'] = independent_algebra(record)
            report['cases'][name] = retain(name, record, directory)
        if (failed['status'], failed['committed_steps'], cancelled['status'], cancelled['committed_steps']) != ('failed', 1, 'cancelled', 0):
            raise AssertionError('prefix evidence differs')
        np.testing.assert_array_equal(pulse['stage_m'][:, :8], raised['stage_m'][:, :8])
        np.testing.assert_array_equal(pulse['qedges_m3_s'][:, :7], raised['qedges_m3_s'][:, :7])
        report['domain1_unchanged_by_domain2_tailwater'] = True
        report['domain2_negative_flux_count'] = int((raised['qedges_m3_s'][:, 7:] < 0).sum())
        report['pulse_downstream_stage_change_m'] = float(pulse['stage_m'][-1, 6] - base['stage_m'][-1, 6])
        if not report['domain2_negative_flux_count'] or abs(report['pulse_downstream_stage_change_m']) <= 1e-12:
            raise AssertionError('pulse propagation or reversed backwater absent')
        with (directory / 'focused-tests.txt').open('x', encoding='utf8') as stream:
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceVariableStorageTests)
            tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        report['focused_tests'] = {'run': tests.testsRun, 'failures': len(tests.failures), 'errors': len(tests.errors), 'sha256': file_hash(directory / 'focused-tests.txt')}
        if not tests.wasSuccessful() or file_hash(SOURCE) != SOURCE_SHA256 or any((file_hash(Path(path)) != expected for path, expected in report['implementation_sha256'].items())):
            raise AssertionError('focused tests or immutable source check failed')
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        raise
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report_path = directory / 'report.json'
        with report_path.open('x', encoding='utf8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        print(str(report_path.resolve()))
        print('report_sha256=' + file_hash(report_path))
if __name__ == '__main__':
    main()
