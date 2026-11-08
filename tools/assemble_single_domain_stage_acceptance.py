"""Publish one bounded stage verdict from externally pinned independent evidence."""
import argparse
import json
import os
from pathlib import Path
import sys
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.surface_execution_guards import execution_isolated
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.td_native_weather_storage_io import _json
from terrain_pipeline.single_domain_surface_consumer import load_consumer_manifest
ROLES = {'native_index', 'native_temporal', 'native_independent', 'native_cold', 'native_consumer', 'native_portability', 'uniform_index', 'uniform_independent', 'uniform_cold', 'uniform_consumer', 'uniform_portability', 'adaptive_index', 'adaptive_independent', 'adaptive_cold', 'adaptive_consumer', 'adaptive_portability', 'adaptive_frames_independent', 'saved_review'}
CASES = {'dry-rain-root4', 'zero-source-lake-root4', 'tailwater-baseline-root4', 'tailwater-rise-root1', 'tailwater-rise-root1-half-dt', 'tailwater-rise-root2', 'tailwater-rise-root4'}

def require(condition, message):
    if not condition:
        raise ValueError('stage acceptance: ' + message)

def bound_report(report):
    observed = report['resource']
    require(observed['elapsed_s'] <= 1800 and max(observed['peak_rss_bytes'], observed['peak_private_bytes']) <= 1073741824, 'independent evidence exceeds declared time/memory budget')

def assemble(evidence_path, output):
    evidence_path = Path(evidence_path).resolve(strict=True)
    evidence = _json(dict(path=str(evidence_path), expected_sha256=file_sha256(evidence_path)))
    require(set(evidence) == ROLES, 'complete named evidence inventory required')
    saved = {role: _json(pin) for role, pin in evidence.items()}
    for role in ('native_independent', 'native_cold', 'uniform_independent', 'uniform_cold', 'adaptive_independent', 'adaptive_cold'):
        phase = role.split('_')[0]
        require(saved[role]['index_record'] == evidence[phase + '_index'], role + ' original source mismatch')
        bound_report(dict(resource=saved[role]) if role == 'native_independent' else saved[role])
    require(saved['native_temporal']['all_saved_numerical_gates_passed'] is True and saved['native_temporal']['io_chain_accepted'] is True, 'native time gates failed')
    require(saved['native_index']['acceptance_record'] == evidence['native_temporal'], 'native temporal evidence is not bound by native index')
    require(saved['native_independent']['accepted_same_bed_saved_chain'] is True, 'native same-bed chain failed')
    require(saved['native_cold']['frame_count'] == 50 and saved['native_cold']['production_construction_disabled'] is True and (saved['native_cold']['forbidden_solver_modules_absent'] is True) and (saved['native_cold']['solver_advanced'] is False), 'native cold coverage failed')
    require(saved['uniform_index']['all_predeclared_gates_passed'] is False and saved['uniform_independent']['all_predeclared_gates_passed'] is False, 'historical uniform failure must remain explicit')
    uniform_cold = saved['uniform_cold']
    require(uniform_cold['frame_count'] == 35 and uniform_cold['pure_io_verified'] is True and (uniform_cold['production_construction_disabled'] is True) and execution_isolated(uniform_cold) and (uniform_cold['solver_advanced'] is False), 'historical uniform cold coverage/isolation failed')
    adaptive, audit, cold = (saved[role] for role in ('adaptive_index', 'adaptive_independent', 'adaptive_cold'))
    require(set(adaptive['cases']) == CASES and set(audit['cases']) == CASES and (set(cold['cases']) == CASES), 'complete seven adaptive scenarios required')
    require(adaptive['source_v7_index'] == evidence['uniform_index'] and adaptive['uniform_coarse_convergence_claim'] is False and (adaptive['source_uniform_coarse_gates_passed'] is False), 'adaptive source/model scope changed')
    require(adaptive['all_predeclared_gates_passed'] is True, 'adaptive declared numerical gates failed')
    measured = adaptive['resources']
    require(measured['elapsed_s'] <= 1800 and max(measured['peak_rss_bytes'], measured['peak_private_bytes']) <= 1073741824, 'adaptive execution time/memory budget failed')
    stage_root = Path(evidence['adaptive_index']['path']).resolve().parent
    stage_files = [path for path in stage_root.rglob('*') if path.is_file()]
    published_bytes = sum((path.stat().st_size for path in stage_files))
    temporary_peak = max((case['solver']['peak_work_disk_bytes'] for case in adaptive['cases'].values()))
    highwater = adaptive['resource_highwater']
    require(highwater['observation_count'] > 0 and highwater['combined_output_and_work_bytes'] >= measured['output_bytes'] and (highwater['largest_file_bytes'] >= measured['largest_artifact_bytes']), 'simultaneous execution disk observations missing')
    require(published_bytes <= 2147483648 and highwater['combined_output_and_work_bytes'] <= 2147483648 and (highwater['largest_file_bytes'] <= 268435456) and (max((path.stat().st_size for path in stage_files)) <= 268435456), 'adaptive permanent/temporary disk or artifact budget failed')
    require(max(highwater['peak_rss_bytes'], highwater['peak_private_bytes']) <= 1073741824, 'adaptive complete observed memory budget failed')
    for name in ('all_predeclared_gates_passed', 'reference_comparisons_independently_verified', 'controlled_tailwater_independently_verified', 'original_forcing_and_initial_contracts_verified', 'physical_equations_independently_verified'):
        require(audit.get(name) is True, 'independent adaptive gate missing: ' + name)
    require(len(audit['comparisons']) == 4 and all((item['maximum_saved_depth_difference_m'] <= 0.01 and item['maximum_relative_surface_volume_difference'] <= 0.01 and (item['passed'] is True) for item in audit['comparisons'])), 'independent full-window depth/volume thresholds failed')
    require(cold['pure_io_verified'] is True and (cold['production_execution_imports_forbidden'] is True or cold.get('execution_functions_guarded') is True) and execution_isolated(cold) and (cold['solver_advanced'] is False), 'adaptive cold execution isolation failed')
    for name in CASES:
        require(audit['cases'][name]['snapshots_verified'] == 5 and cold['cases'][name]['snapshots_verified'] == 5, 'adaptive saved time coverage incomplete')
        require(audit['cases'][name]['complete_leaf_mass_momentum_chain_verified'] is True, 'adaptive complete inventory chain failed')
    frame_audit = saved['adaptive_frames_independent']
    require(frame_audit.get('bound_frames_verified') == 35 and frame_audit.get('all_fan_geometry_gates_passed') is True and (frame_audit.get('original_snapshot_bindings_verified') is True) and (frame_audit.get('original_rainfall_runoff_bindings_verified') is True), 'independent AMR fan binding/geometry failed')
    require(frame_audit['source_manifest'] == evidence['adaptive_consumer'], 'independent frame report source mismatch')
    require(frame_audit['source_index'] == evidence['adaptive_index'], 'independent frame original stage mismatch')
    bound_report(frame_audit)
    for phase in ('native', 'uniform', 'adaptive'):
        consumer_pin, portability = (evidence[phase + '_consumer'], saved[phase + '_portability'])
        context = load_consumer_manifest(consumer_pin['path'], expected_sha256=consumer_pin['expected_sha256'])
        require(context['manifest']['source_index'] == evidence[phase + '_index'], 'consumer original phase index changed')
        bound_report(context['manifest'])
        require(portability['source_manifest'] == consumer_pin and portability['authenticated_relative_payloads'] is True and (portability['original_source_access_forbidden'] is True) and execution_isolated(portability) and (portability['http_server_stopped'] is True), 'relocated consumption failed')
        bound_report(portability)
    require(saved['adaptive_portability']['adaptive_water_frames']['bound_frames_verified'] == 35, 'relocated complete adaptive frame validation failed')
    review = saved['saved_review']
    require(review['source_manifest'] == evidence['adaptive_consumer'] and review['solver_advanced'] is False and (review['full_window_maps'] is True) and (review['actual_patch_bed_triangles'] > 0) and (review['actual_patch_water_triangles'] > 0), 'saved review source/mesh scope mismatch')
    require(file_sha256(review['png']['path']) == review['png']['expected_sha256'], 'saved review image changed')
    bound_report(review)
    bound_report(audit)
    bound_report(cold)
    for role, pin in evidence.items():
        require(file_sha256(pin['path']) == pin['expected_sha256'], role + ' changed during acceptance assembly')
    output = Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    result = dict(schema='single-domain-finite-surface-stage-acceptance-v1', stage=1, status='resolved', bounded_engineering_stage_accepted=True, evidence=evidence, evidence_inventory=dict(path=str(evidence_path), expected_sha256=file_sha256(evidence_path)), native_scope=dict(shape=[256, 256], spacing_m=30.0, duration_s=86400.0, saved_frames=50, immutable_bed_and_receiver_graph=True), fine_scope=dict(native_window=[150, 158, 241, 249], extent_m=[240, 240], duration_s=120.0, saved_frames=35, canonical_spacing_m=1.0, adaptive_leaf_spacings_m=[1, 2, 4], independent_reference='saved uniform 1m half-dt; all cells and all five saved times'), numerical_comparisons=audit['comparisons'], scenario_gates=audit['scenario_gates'], saved_review=review['png'], adaptive_execution_resource=dict(measured, final_published_bytes=published_bytes, maximum_case_temporary_bytes=temporary_peak, simultaneous_disk_highwater=highwater, complete_combined_disk_peak_bytes=max(published_bytes, highwater['combined_output_and_work_bytes'])), budgets=dict(max_memory_bytes=1073741824, max_artifact_bytes=268435456, max_output_bytes=2147483648, max_wall_s=1800), uniform_coarse_convergence_claim=False, original_uniform_spatial_gates_passed=False, full_native_domain_fine_verified=False, official_frontend_integrated=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False, solver_advanced=False, next_stage=2, next_stage_started=False, limitations=['This accepts the bounded algorithm and saved consumer workflow; it does not certify natural outlets or calibrated hydrodynamics.', 'Native 7.68km coverage and selected 240m fine coverage have distinct resolutions and durations.', 'AMR resolves useful wet regions largely at 1m; saved leaf occupancy is the evidence for efficiency.', 'Original uniform 2m/1m and 4m/2m depth comparisons failed and remain diagnostic.', 'Shared water fans conserve canonical inventory and are visualization reconstructions.', 'The designated frontend and Minecraft integration remain separate pending consumers.'], assembly_code_sha256=file_sha256(Path(__file__)))
    target = output / 'acceptance-index.json'
    publish_bytes(target, (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8'))
    pin = dict(path=str(target), expected_sha256=file_sha256(target))
    print(json.dumps(pin), flush=True)
    return pin
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    assemble(args.evidence, args.output)
