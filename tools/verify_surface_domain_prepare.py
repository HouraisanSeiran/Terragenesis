"""Fixed CPU-only complete-domain scenarios; retain success and failure UTC evidence."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from unittest.mock import patch
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from terrain_pipeline.artifacts.contracts import array_hash
from terrain_pipeline.surface_domain import SurfaceDomainResources, evaluate_surface_domains, load_surface_domains, plan_surface_domains, query_surface_domain, save_surface_domains
from terrain_pipeline.surface_domain import SurfaceNetworkBudget
from terrain_pipeline.surface_domain import RecoveryRecipe
from tests.test_surface_domain import complete_two_domain_inputs, fine_configurations, _test_surface_domain_prepare_rehash as rehash, write_rehashed_bundle
from terrain_pipeline.surface_identity import _plain

def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()

def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')

def retain(name, result, directory):
    path = directory / (name + '.npz')
    save_surface_domains(result, path)
    with patch('terrain_pipeline.surface_domain._flood', side_effect=AssertionError('load routed')), patch('terrain_pipeline.surface_domain.plan_channel', side_effect=AssertionError('load planned')), patch('terrain_pipeline.surface_domain.recover_surface_network', side_effect=AssertionError('load recovered')):
        loaded = load_surface_domains(path, allow_unprepared=result['status'] != 'prepared')
        if result['status'] == 'prepared':
            for entry in loaded['domains']:
                query_surface_domain(loaded, entry['domain_id'], slice(None), slice(None))
    if loaded['identity_sha256'] != result['identity_sha256']:
        raise AssertionError('domain identity changed on reload')
    record = {'status': result['status'], 'bundle': str(path.resolve()), 'bundle_sha256': file_hash(path), 'identity_sha256': result['identity_sha256'], 'failures': list(result['failures']), 'static_semantic_reload': True, 'load_query_no_route_plan_recovery': True}
    if result['kind'] == 'evaluation':
        record['usage'] = dict(result['usage'])
        record['domains'] = [{'domain_id': entry['domain_id'], 'status': entry['status'], 'reason': entry['reason'], 'attempts': [] if entry['recovery'] is None else _plain(entry['recovery']['attempts'])} for entry in result['domains']]
    else:
        record['domains'] = _plain(result['domains'])
        record['coastal_transfers'] = _plain(result['coastal_transfers'])
        record['unrouted_local_discharge_m3_s'] = result['unrouted_local_discharge_m3_s']
    write_json(directory / (name + '.json'), record)
    return record

def generated_source_probe(directory):
    source_dir = ROOT / 'verification' / 'river-feasibility' / 'extended-20260929T114427548312Z'
    source_path = source_dir / 'seed20261002-x-16000-z-13952-size1025.npz'
    old_candidate_path = source_dir / 'candidate-domain.npz'
    before = {str(path): file_hash(path) for path in (source_path, old_candidate_path)}
    expected = '408aae491bf11868c11f1fea343703acb725f23cf97ee574cfd4d317261a934b'
    if before[str(source_path)] != expected:
        raise AssertionError('original generated source file identity changed')
    with np.load(source_path, allow_pickle=False) as archive:
        height = archive['elevation'].astype(np.float64)
        metadata = json.loads(str(archive['metadata'].item()))
    with np.load(old_candidate_path, allow_pickle=False) as archive:
        old_catchment = archive['land_catchment_mask']
        mouth = archive['first_ocean_mouth_grid_zx'].tolist()
    land = height > 0.0
    shape = height.shape
    inputs = dict(height_m=height, valid_mask=np.isfinite(height), domain_labels=land.astype(np.int64), land_mask=land, ocean_mask=~land, protected_mask=np.zeros(shape, bool), coastal_outlets=[], runoff_m_s=np.where(land, 1e-08, 0.0), external_q_m3_s=np.zeros(shape), spacing_x_m=float(metadata['native_resolution_m']), spacing_z_m=float(metadata['native_resolution_m']), origin_x_m=float(metadata['native_origin'][0]), origin_z_m=float(metadata['native_origin'][1]), sea_level_elevation_m=0.0, vertical_datum='generated-relative-sea-zero-not-observed-datum', source_identity='file-sha256:' + before[str(source_path)], source_kind='generated_model_candidate_not_observation', boundary_complete=False, scope='complete_grid', outlet_evidence='engineering_declared', resources=SurfaceDomainResources())
    result = plan_surface_domains(**inputs)
    if result['status'] != 'diagnostic' or 'coarse_resource_limit' not in result['failures']:
        raise AssertionError('full source must retain default coarse resource failure')
    record = retain('generated-full-window-resource', result, directory)
    land_count = int(land.sum())
    candidate_count = int(old_catchment.sum())
    evidence = {'source_path': str(source_path.resolve()), 'source_file_sha256': before[str(source_path)], 'source_height_float64_sha256': array_hash(height), 'shape_zx': list(shape), 'spacing_x_m': inputs['spacing_x_m'], 'spacing_z_m': inputs['spacing_z_m'], 'origin_interpretation': 'native_origin copied from archived metadata; not independent georeferencing', 'source_min_m': float(height.min()), 'source_max_m': float(height.max()), 'finite_cells': int(np.isfinite(height).sum()), 'declared_land_cells': land_count, 'declared_ocean_cells': int((~land).sum()), 'domain_membership': {'1': land_count}, 'old_catchment_cells': candidate_count, 'land_outside_old_catchment': int((land & ~old_catchment).sum()), 'old_mouth_grid_zx': mouth, 'old_mouth_h0_m': float(height[tuple(mouth)]), 'old_catchment_scope': 'subdomain; cannot represent all source land', 'land_ocean_evidence': 'engineering threshold declaration only, no natural coast certification', 'boundary_complete': False, 'independent_dem_datum_outlet_verified': False, 'lowland_not_real_mountain': True, 'fine_prepared': False, 'old_fine_4441x2221_not_loaded_or_recomputed': True, 'all_raw_files_unchanged': all((file_hash(path) == before[str(path)] for path in (source_path, old_candidate_path)))}
    if land_count != 402641 or candidate_count != 7993 or evidence['land_outside_old_catchment'] != 394648:
        raise AssertionError('source coverage differs from independent expected counts')
    write_json(directory / 'generated-source-evidence.json', evidence)
    record['source_evidence'] = evidence
    return record

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-tests', action='store_true')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory = ROOT / 'verification' / 'surface-domain-prepare' / ('run-' + stamp)
    directory.mkdir(parents=True, exist_ok=False)
    report = {'run_directory': str(directory.resolve()), 'started_utc': stamp, 'status': 'running', 'cases': {}}
    started = time.perf_counter()
    write_json(directory / 'report.json', report)
    try:
        candidate = plan_surface_domains(**complete_two_domain_inputs())
        report['cases']['candidate'] = retain('two-domain-candidate', candidate, directory)
        prepared = evaluate_surface_domains(candidate, fine_configurations(candidate))
        if prepared['status'] != 'prepared':
            retain('two-domain-positive-failed', prepared, directory)
            raise AssertionError('complete-domain positive did not actually prepare')
        report['cases']['prepared'] = retain('two-domain-prepared', prepared, directory)
        metrics = []
        for entry in prepared['domains']:
            arrays = query_surface_domain(prepared, entry['domain_id'], slice(None), slice(None))
            recovery = entry['recovery']
            depth = arrays['water_surface_m'][arrays['wet_mask']] - arrays['final_surface_m'][arrays['wet_mask']]
            metrics.append({'domain_id': entry['domain_id'], 'fine_shape_zx': list(arrays['wet_mask'].shape), 'wet_nodes': int(arrays['wet_mask'].sum()), 'depth_min_m': float(depth.min()), 'depth_max_m': float(depth.max()), 'selected_method': recovery['selected_method'], 'changed_fine_nodes': int((arrays['total_cut_m'] > 1e-09).sum()), 'cut_volume_m3': recovery['surface']['summary']['cut_volume_m3'], 'cut_area_m2': recovery['surface']['summary']['area_m2']})
        report['positive_metrics'] = {'land_nodes_routed': int((candidate['arrays']['receiver'] >= -1).sum()), 'coastal_transfers': _plain(candidate['coastal_transfers']), 'domains': metrics, 'scope': 'all declared coarse land nodes and per-domain fine river engineering', 'continuous_full_land_fine_mosaic': False, 'fine_bbox_gap_x_m': 10.0, 'last_land_h0_m': 4.0, 'river_outlet_stage_m': 4.2, 'sea_level_m': 0.0, 'continuous_land_to_ocean_wet_drop_geometry': False, 'retained_bytes_not_measured_process_peak': True, 'not_natural_mountain_or_hydrodynamic_certification': True}
        for name in ('unknown', 'no_exit', 'protected', 'coarse_limit'):
            inputs = complete_two_domain_inputs()
            if name == 'unknown':
                inputs['domain_labels'][1, 1] = -1
            elif name == 'no_exit':
                inputs['coastal_outlets'] = inputs['coastal_outlets'][:1]
            elif name == 'protected':
                inputs['protected_mask'][1, 1] = True
            else:
                inputs['resources'] = SurfaceDomainResources(max_coarse_cells=10)
            result = plan_surface_domains(**inputs)
            if result['status'] != 'diagnostic':
                raise AssertionError(name + ' unexpectedly publishable')
            report['cases'][name] = retain(name, result, directory)
        for name, bounds in (('joint_fine_limit', {'max_fine_cells': 5000}), ('joint_attempt_limit', {'max_attempts': 1}), ('joint_retained_limit', {'max_retained_bytes': 1000000})):
            inputs = complete_two_domain_inputs()
            inputs['resources'] = SurfaceDomainResources(**bounds)
            limited = plan_surface_domains(**inputs)
            result = evaluate_surface_domains(limited, fine_configurations(limited))
            report['cases'][name] = retain(name, result, directory)
            if result['status'] != 'diagnostic' or result['usage']['attempts'] != 0:
                raise AssertionError('joint resource preflight did not reject before recovery')
        configs = fine_configurations(candidate)
        configs = {key: replace(value, budget=SurfaceNetworkBudget(4.0, 0.0, 0.0), recovery_recipe=RecoveryRecipe(max_attempts=1)) for key, value in configs.items()}
        report['cases']['actual_budget'] = retain('actual-fine-budget', evaluate_surface_domains(candidate, configs), directory)

        def cancel():
            cancel.calls += 1
            return cancel.calls > 1
        cancel.calls = 0
        report['cases']['cancel_prefix'] = retain('cancel-prefix', evaluate_surface_domains(candidate, fine_configurations(candidate), cancel=cancel), directory)
        for name in ('false_coast', 'ocean_peak', 'retained_input'):
            inputs = complete_two_domain_inputs()
            if name == 'false_coast':
                inputs['coastal_outlets'][0] = (1, 7 * 16 + 4, 0)
            elif name == 'ocean_peak':
                inputs['height_m'][8, 4] = 100.0
            else:
                inputs['resources'] = SurfaceDomainResources(max_retained_bytes=100)
            try:
                plan_surface_domains(**inputs)
            except ValueError as error:
                evidence = {'rejected': True, 'reason': str(error), 'input_height_sha256': array_hash(inputs['height_m']), 'input_labels_sha256': array_hash(inputs['domain_labels'])}
                write_json(directory / (name + '.json'), evidence)
                report['cases'][name] = evidence
            else:
                raise AssertionError(name + ' unexpectedly accepted')
        for name in ('cross_domain', 'usage_zero'):
            tampered = _plain(candidate if name == 'cross_domain' else prepared)
            if name == 'cross_domain':
                tampered['arrays']['receiver'] = tampered['arrays']['receiver'].copy()
                tampered['arrays']['receiver'][3 * 16 + 7] = 3 * 16 + 8
            else:
                for entry in tampered['domains']:
                    entry['charged_coarse_cells'] = 0
                    entry['charged_fine_cells'] = 0
                tampered['usage']['coarse_work_cells'] = 0
                tampered['usage']['fine_cells'] = 0
            path = directory / ('rehashed-' + name + '.npz')
            write_rehashed_bundle(rehash(tampered), path)
            try:
                load_surface_domains(path, allow_unprepared=True)
            except ValueError as error:
                report['cases']['rehashed_' + name] = {'rejected': True, 'reason': str(error), 'bundle': str(path.resolve())}
            else:
                raise AssertionError('rehashed ' + name + ' passed semantic validation')
        report['cases']['generated_source'] = generated_source_probe(directory)
        if not args.skip_tests:
            test_started = time.perf_counter()
            process = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', 'tests.test_surface_domain.SurfaceDomainPrepareTests', '-v'], cwd=ROOT, capture_output=True, text=True, encoding='utf8')
            (directory / 'focused-tests.txt').write_text(process.stdout + process.stderr, encoding='utf8')
            report['focused_tests'] = {'returncode': process.returncode, 'seconds': time.perf_counter() - test_started}
            if process.returncode:
                raise AssertionError('focused tests failed')
        report['code_sha256'] = {str(path.relative_to(ROOT)): file_hash(path) for path in (ROOT / 'terrain_pipeline' / 'surface_domain.py', ROOT / 'tests' / 'test_surface_domain.py', Path(__file__), ROOT / 'docs' / 'surface-domain-prepare-v1.md')}
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        (directory / 'failure.txt').write_text(traceback.format_exc(), encoding='utf8')
        raise
    finally:
        report['seconds'] = time.perf_counter() - started
        write_json(directory / 'report.json', report)
        print(str(directory.resolve()))
if __name__ == '__main__':
    main()
