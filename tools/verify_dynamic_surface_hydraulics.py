"""UTC evidence for the explicit storage graph, including failure prefixes."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from terrain_pipeline import surface_hydraulics as hydro
SOURCE_FILES = ('terrain_pipeline/surface_hydraulics.py', 'tests/test_surface_hydraulics.py', 'tools/verify_dynamic_surface_hydraulics.py', 'docs/dynamic-surface-hydraulics-v1.md')

def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def source_file_hashes():
    return {name: {'path': str((ROOT / name).resolve()), 'file_sha256': file_sha256(ROOT / name), 'size_bytes': (ROOT / name).stat().st_size} for name in SOURCE_FILES}

def fixed_case(steps=3, upstream_q=1.0, tailwater=0.0):
    local = np.zeros((steps, 3))
    local[:, 0] = upstream_q
    boundary = np.zeros((steps + 1, 3))
    boundary[:, 2] = tailwater
    return hydro.HydraulicsInput(bed_m=np.zeros(3), area_m2=np.full(3, 10.0), initial_stage_m=np.array([0.0, 0.0, tailwater]), edges=np.array([[0, 1], [1, 2]], dtype=np.int64), conductance_m2_s=np.ones(2), local_q_m3_s=local, boundary_mask=np.array([False, False, True]), boundary_stage_m=boundary, dt_s=1.0, max_depth_m=10.0, valid_mask=np.ones(3, dtype=bool), protected_mask=np.zeros(3, dtype=bool), coords_m=np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]), source='verifier-engineered-three-node-explicit-graph', datum='local zero bed, metres', coords='local Cartesian (x,z), metres')

def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')

def record_case(directory, name, inputs, *, expected_status='completed', expected_stage=None, cancel=None):
    result = hydro.evaluate(inputs, cancel=cancel)
    bundle = directory / (name + '.npz')
    hydro.save(result, bundle)
    bundle_sha256 = file_sha256(bundle)
    loaded = hydro.load(bundle)
    record = {'bundle': str(bundle.resolve()), 'status': result.status, 'bundle_file_sha256': bundle_sha256, 'bundle_size_bytes': bundle.stat().st_size, 'bundle_file_unchanged_after_reload': file_sha256(bundle) == bundle_sha256, 'committed_steps': result.committed_steps, 'identity_sha256': result.identity_sha256, 'saved_identity_equal': loaded.identity_sha256 == result.identity_sha256, 'static_validation': hydro.validate(loaded), 'stage_m': loaded.stage_m.tolist(), 'storage_m3': loaded.storage_m3.tolist(), 'qedges_m3_s': loaded.qedges_m3_s.tolist(), 'time_s': loaded.time_s.tolist(), 'ledger_columns': list(hydro.LEDGER_COLUMNS), 'committed_ledger_m3': loaded.ledger_m3.tolist(), 'failed_step': None if loaded.failed_step is None else {'step_n': loaded.failed_step.step_n, 'reason': loaded.failed_step.reason, 'previous_stage_m': loaded.failed_step.previous_stage_m.tolist(), 'next_stage_m': loaded.failed_step.next_stage_m.tolist(), 'next_storage_m3': loaded.failed_step.next_storage_m3.tolist(), 'qedges_m3_s': loaded.failed_step.qedges_m3_s.tolist(), 'uncommitted_ledger_m3': loaded.failed_step.ledger_m3.tolist()}}
    write_json(directory / (name + '.json'), record)
    if result.status != expected_status or not record['saved_identity_equal'] or (not record['bundle_file_unchanged_after_reload']):
        raise AssertionError(name + ' status or reload mismatch')
    if expected_stage is not None:
        np.testing.assert_allclose(loaded.stage_m, expected_stage, rtol=1e-12, atol=1e-12)
    return record

def run_cases(directory):
    cases = {}
    cases['two_reach_delay'] = record_case(directory, 'two_reach_delay', fixed_case(), expected_stage=[[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [0.19, 0.01, 0.0], [0.272, 0.027, 0.0]])
    cases['tailwater_reverse'] = record_case(directory, 'tailwater_reverse', fixed_case(upstream_q=0.0, tailwater=1.0), expected_stage=[[0.0, 0.0, 1.0], [0.0, 0.1, 1.0], [0.01, 0.18, 1.0], [0.027, 0.245, 1.0]])
    cases['tailwater_two'] = record_case(directory, 'tailwater_two', fixed_case(upstream_q=0.0, tailwater=2.0), expected_stage=[[0.0, 0.0, 2.0], [0.0, 0.2, 2.0], [0.02, 0.36, 2.0], [0.054, 0.49, 2.0]])
    cases['steady_analytic'] = record_case(directory, 'steady_analytic', replace(fixed_case(), initial_stage_m=np.array([2.0, 1.0, 0.0])), expected_stage=np.tile([2.0, 1.0, 0.0], (4, 1)))
    cases['zero_q'] = record_case(directory, 'zero_q', fixed_case(upstream_q=0.0), expected_stage=np.zeros((4, 3)))
    cases['negative_storage'] = record_case(directory, 'negative_storage', replace(fixed_case(upstream_q=0.0), bed_m=np.array([2.0, 0.0, 0.0]), initial_stage_m=np.array([2.0, 0.0, 0.0])), expected_status='failed')
    cases['max_depth'] = record_case(directory, 'max_depth', replace(fixed_case(), max_depth_m=0.15), expected_status='failed')
    inputs = fixed_case(upstream_q=0.0)
    boundary = inputs.boundary_stage_m.copy()
    boundary[-1, 2] = 11.0
    cases['terminal_boundary_depth'] = record_case(directory, 'terminal_boundary_depth', replace(inputs, boundary_stage_m=boundary), expected_status='failed')
    calls = iter([False, True])
    cases['cancel_prefix'] = record_case(directory, 'cancel_prefix', fixed_case(), cancel=lambda: next(calls), expected_status='cancelled')
    rejections = {}
    for name, changes in {'unstable_dt': {'dt_s': 5.01}, 'unknown_support': {'valid_mask': np.array([True, False, True])}, 'protected_support': {'protected_mask': np.array([False, True, False])}, 'retained_cap': {'limits': hydro.ResourceLimits(max_retained_bytes=100)}}.items():
        try:
            replace(fixed_case(), **changes)
        except ValueError as error:
            rejections[name] = {'rejected': True, 'reason': str(error)}
        else:
            raise AssertionError(name + ' unexpectedly accepted')
    write_json(directory / 'input-rejections.json', rejections)
    return (cases, rejections)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-tests', action='store_true')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'verification' / 'dynamic-surface-hydraulics')
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    directory = args.output_root.resolve() / ('run-' + started.strftime('%Y%m%dT%H%M%S.%fZ'))
    directory.mkdir(parents=True, exist_ok=False)
    report = {'started_utc': started.isoformat(), 'algorithm': hydro.ALGORITHM, 'geometry_mode': hydro.GEOMETRY_MODE, 'status': 'running', 'evidence_directory': str(directory), 'scope': 'caller engineering K; linear diffusion, not Manning/CFL/Saint-Venant/legacy integration'}
    report['source_files'] = source_file_hashes()
    write_json(directory / 'started.json', report)
    exit_code = 0
    try:
        cases, rejections = run_cases(directory)
        report.update({'cases': cases, 'input_rejections': rejections})
        if not args.skip_tests:
            command = [sys.executable, '-m', 'unittest', 'tests.test_surface_hydraulics.DynamicSurfaceHydraulicsTests', '-v']
            process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
            with (directory / 'focused-tests.log').open('x', encoding='utf-8') as stream:
                stream.write(process.stdout + process.stderr)
            report['tests'] = {'command': command, 'exit_code': process.returncode}
            if process.returncode:
                raise AssertionError('focused tests failed; see focused-tests.log')
        else:
            report['tests'] = {'skipped': True}
        if source_file_hashes() != report['source_files']:
            raise AssertionError('source files changed during verification')
        report['status'] = 'passed'
    except Exception as error:
        exit_code = 1
        report.update({'status': 'failed', 'error_type': type(error).__name__, 'error': str(error)})
        with (directory / 'failure-traceback.log').open('x', encoding='utf-8') as stream:
            stream.write(traceback.format_exc())
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['source_files_at_finish'] = source_file_hashes()
        report['source_files_unchanged'] = report['source_files_at_finish'] == report['source_files']
        report['evidence_files'] = {path.name: {'file_sha256': file_sha256(path), 'size_bytes': path.stat().st_size} for path in sorted(directory.iterdir()) if path.is_file()}
        write_json(directory / 'report.json', report)
    print(json.dumps({'status': report['status'], 'report': str(directory / 'report.json')}, ensure_ascii=False))
    return exit_code
if __name__ == '__main__':
    raise SystemExit(main())
