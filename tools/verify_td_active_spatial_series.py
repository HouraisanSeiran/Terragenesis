"""Independent workers for the original 900s TD active spatial comparison."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone
from unittest.mock import patch
import numpy as np
from terrain_pipeline.common_infra import file_sha256, load_bundle
from terrain_pipeline.channel_geometry import ChannelConfig
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, SedimentConfig
from terrain_pipeline.surface_rivers.metric_resolution_series import audit_series, run_series, slice_forcing, _native, _validate_basis, _validate_checkpoint
from tools.verify_td_active_spatial import source, peak_rss_bytes
POLICY = dict(levels=[128, 256, 512], reference_level=512, dt_seconds=0.25, temporal_dt_seconds=0.125, segment_seconds=5.0, sample_times_seconds=[300.0, 600.0, 900.0], inventory_relative_tolerance=0.03, export_relative_tolerance=0.03, half_export_time_tolerance_seconds=0.5, temporal_relative_tolerance=0.002, bed_absolute_tolerance_m=0.001, budget_absolute_tolerance_m3=1e-08, max_worker_seconds=180.0, max_worker_rss_bytes=1024 ** 3, max_nodes=2048, max_product_trace_bytes=128 * 1024 ** 2)
OFFLINE_RESOURCE_POLICY = dict(max_worker_seconds=600.0, max_worker_rss_bytes=1024 ** 3, reason='complete900s2048-node spatial reference exceeds smaller-domain180s engineering budget; numerical tolerances and128MiB per product unchanged')
COVERAGE_POLICY = dict(frozen_before_final_scores=True, numerical_thresholds='unchanged original policy', acceptance='at least one non-reference resolution passes all spatial thresholds and its temporal thresholds plus reference temporal thresholds; report failed coarser levels explicitly', resource_requirement='all six observed worker chains within authorized600s/1GiB')
ENGINEERING_POLICY = dict(max_normal_worker_seconds=600.0, max_normal_worker_rss_bytes=1024 ** 3, normal_case=dict(level=512, dt_seconds=0.125, horizon_seconds=900.0, nodes=2048), acceptance='final code uninterrupted complete original active900s solve/save in one independent highest-reference worker; recovery chains and old180s failures remain reported separately')

def implementation_pins():
    root = Path(__file__).resolve().parents[1]
    files = ('terrain_pipeline/channel_geometry.py', 'terrain_pipeline/surface_hydraulics.py', 'terrain_pipeline/surface_rivers/metric_channel_product.py', 'terrain_pipeline/surface_rivers/metric_bed_update.py', 'terrain_pipeline/surface_rivers/metric_sediment.py', 'terrain_pipeline/surface_rivers/metric_resolution_exchange.py', 'terrain_pipeline/surface_rivers/metric_resolution_series.py', 'terrain_pipeline/common_infra.py', 'tools/verify_td_active_spatial_series.py')
    return {file: file_sha256(root / file) for file in files}

def record_resource_extension(output):
    output = Path(output)
    target = output / 'resource-extension.json'
    if target.exists():
        record = json.loads(target.read_text(encoding='utf-8'))
        if record['offline_resource_policy'] != OFFLINE_RESOURCE_POLICY or record['old_frozen_policy_sha256'] != file_sha256(output / 'frozen-policy.json'):
            raise ValueError('resource extension changed')
        return record
    manifest = json.loads((output / 'level512-fine' / 'manifest.json').read_text(encoding='utf-8'))
    record = dict(schema='terragenesis-offline-resource-extension-v1', recorded_at_utc=datetime.now(timezone.utc).isoformat(), old_frozen_policy_sha256=file_sha256(output / 'frozen-policy.json'), old_worker_seconds=180.0, offline_resource_policy=OFFLINE_RESOURCE_POLICY, authorized_progress=dict(completed_physical_seconds=350.0, elapsed_seconds=106.85, segments=70), recorded_progress=dict(segments=len(manifest['segments']), status=manifest['status'], elapsed_segment_seconds=sum((segment['elapsed_seconds'] for segment in manifest['segments']))))
    target.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record

def worker(output, level, dt, horizon, reuse_complete_prefix=None):
    started = time.perf_counter()
    net, forcing, old, pin = source()
    if horizon != 900.0:
        forcing = slice_forcing(forcing, 0.0, horizon)
    mi = old['material_inputs']
    result = run_series(net, forcing, np.full(4, level, np.int64), MaterialParameters(**old['material']), output=output, source_manifest=pin, segment_seconds=POLICY['segment_seconds'], channel_config=ChannelConfig(max_dt_seconds=dt, max_steps=10000), sediment_config=SedimentConfig(max_dt_seconds=dt, max_steps=10000), initial_alluvium_depth_m=mi['initial_alluvium_depth_m'], rock_reserve_depth_m=mi['rock_reserve_depth_m'], external_concentration=mi['external_solid_concentration_m3_per_m3'], reuse_complete_prefix=reuse_complete_prefix)
    resources = dict(elapsed_seconds=time.perf_counter() - started, peak_rss_bytes=peak_rss_bytes(), status=result['status'], segments=len(result['segments']), level=level, dt_seconds=dt, horizon_seconds=horizon, implementation_sha256=implementation_pins())
    if reuse_complete_prefix:
        parent_directory = Path(reuse_complete_prefix).parent
        prior = json.loads((parent_directory / 'worker-resource.json').read_text(encoding='utf-8'))
        resources['suffix_worker_seconds'] = resources['elapsed_seconds']
        resources['prefix_original_worker_seconds'] = prior['elapsed_seconds']
        resources['elapsed_seconds'] += prior['elapsed_seconds']
        resources['peak_rss_bytes'] = max(resources['peak_rss_bytes'], prior['peak_rss_bytes'])
    resources['performance_passed'] = resources['elapsed_seconds'] <= POLICY['max_worker_seconds'] and resources['peak_rss_bytes'] <= POLICY['max_worker_rss_bytes'] and (result['status'] == 'complete')
    resources['old_180s_passed'] = resources['performance_passed']
    resources['new_offline_600s_passed'] = resources['elapsed_seconds'] <= OFFLINE_RESOURCE_POLICY['max_worker_seconds'] and resources['peak_rss_bytes'] <= OFFLINE_RESOURCE_POLICY['max_worker_rss_bytes'] and (result['status'] == 'complete')
    resources['retained_segments_solve_save_seconds'] = sum((segment['elapsed_seconds'] for segment in result['segments']))
    resources['prefix_cold_audit_seconds'] = result.get('prefix_cold_audit_seconds', 0.0)
    resources['retained_segments_600s_passed'] = resources['retained_segments_solve_save_seconds'] <= OFFLINE_RESOURCE_POLICY['max_worker_seconds'] and resources['peak_rss_bytes'] <= OFFLINE_RESOURCE_POLICY['max_worker_rss_bytes'] and (result['status'] == 'complete')
    path = Path(output) / 'worker-resource.json'
    path.write_text(json.dumps(resources, indent=2) + '\n', encoding='utf-8')
    return resources

def preserve_storage_interruption(source_directory, output):
    """Pin a committed prefix after an unhandled ENOSPC, without editing evidence."""
    source_directory = Path(source_directory).absolute()
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    original = source_directory / 'manifest.json'
    manifest = json.loads(original.read_text(encoding='utf-8'))
    if manifest['status'] != 'running' or not manifest['segments'] or any((s['water_status'] != 'complete' or s['solid_status'] != 'complete' for s in manifest['segments'])):
        raise ValueError('not a fully committed interrupted storage prefix')
    last = manifest['segments'][-1]['checkpoint']
    checkpoint = load_bundle(source_directory / last['path'], expected_sha256=last['sha256'], validator=_validate_checkpoint)
    manifest['status'] = 'failed_prefix'
    manifest['last_time_seconds'] = float(checkpoint['arrays']['time_seconds'][0])
    manifest['storage_interruption'] = dict(original_manifest_path=str(original), original_manifest_sha256=file_sha256(original), reason='ENOSPC raised during uncommitted native product save; only manifest-pinned complete segments retained')
    for field in ('basis', 'initial_checkpoint'):
        manifest[field] = dict(manifest[field], path=str(source_directory / manifest[field]['path']))
    for segment in manifest['segments']:
        for field in ('water', 'solid', 'checkpoint'):
            segment[field] = dict(segment[field], path=str(source_directory / segment[field]['path']))
    continuation = manifest['continuation']
    prior_manifest = source_directory / continuation['parent_manifest_path']
    continuation['parent_manifest_path'] = str(prior_manifest.absolute())
    path = output / 'manifest.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    prior = json.loads((prior_manifest.parent / 'worker-resource.json').read_text(encoding='utf-8'))
    timestamps = [f.stat().st_mtime for f in source_directory.iterdir()]
    observed = max(timestamps) - source_directory.stat().st_ctime
    resources = dict(prior, status='storage_interruption', elapsed_seconds=prior['elapsed_seconds'] + observed, interrupted_worker_file_timestamp_seconds=observed, interrupted_worker_timing_semantics='observed directory creation through last product write; excludes source setup and process teardown; retained lower bound after exception lost normal timer', interrupted_peak_rss_unrecorded=True)
    (output / 'worker-resource.json').write_text(json.dumps(resources, indent=2) + '\n', encoding='utf-8')
    return manifest

def difference(actual, reference):
    errors = {}
    for field, observations in actual['stocks'].items():
        a = np.array([observations[str(t)] for t in POLICY['sample_times_seconds']])
        r = np.array([reference['stocks'][field][str(t)] for t in POLICY['sample_times_seconds']])
        if field == 'bed_elevation_m':
            errors[field] = float(np.max(np.abs(a - r)))
        else:
            errors[field] = float(np.max(np.abs(a - r)) / max(float(np.max(np.abs(r))), 1e-12))
    for field in ('export_m3', 'solid_export_m3'):
        errors[field] = abs(actual[field] - reference[field]) / max(abs(reference[field]), 1e-12)
    for field in ('half_export_seconds', 'half_solid_export_seconds'):
        errors[field] = abs(actual[field] - reference[field])
    return errors

def cold_report(path):
    path = Path(path)
    report = json.loads(path.read_text(encoding='utf-8'))
    if report['schema'] == 'terragenesis-active-spatial-series-verification-v2':
        coverage_path = path.parent / 'coverage-policy.json'
        if file_sha256(coverage_path) != report['coverage_policy_sha256'] or json.loads(coverage_path.read_text(encoding='utf-8'))['coverage_policy'] != COVERAGE_POLICY:
            raise ValueError('frozen coverage declaration changed')
        engineering_path = path.parent / report['engineering_budget_supplement_path']
        if file_sha256(engineering_path) != report['engineering_budget_supplement_sha256'] or json.loads(engineering_path.read_text(encoding='utf-8'))['engineering_policy'] != ENGINEERING_POLICY:
            raise ValueError('engineering budget interpretation changed')
    extension_path = path.parent / report['resource_extension_path'] if 'resource_extension_path' in report else None
    extension = json.loads(extension_path.read_text(encoding='utf-8')) if extension_path else record_resource_extension(path.parent)
    if extension['offline_resource_policy'] != OFFLINE_RESOURCE_POLICY:
        raise ValueError('offline resource extension changed')
    if report['policy'] != POLICY:
        raise ValueError('frozen spatial-series policy changed')
    net, forcing, old, pin = source()
    if report['source'] != pin:
        raise ValueError('original Stage4 source changed')
    observations = {}
    resources = {}
    with patch('terrain_pipeline.surface_rivers.metric_resolution_series.solve_channel', side_effect=AssertionError('cold water solve')), patch('terrain_pipeline.surface_rivers.metric_resolution_series.solve_sediment', side_effect=AssertionError('cold sediment solve')):
        for name, product in report['cases'].items():
            manifest_path = path.parent / product['path']
            if file_sha256(manifest_path) != product['sha256']:
                raise ValueError('series manifest pin changed')
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            expected_endpoints = product.get('actual_segment_endpoints_seconds', np.r_[np.arange(0.0, 900.0, POLICY['segment_seconds']), 900.0])
            np.testing.assert_array_equal(manifest['segment_endpoints_seconds'], expected_endpoints)
            basis = load_bundle(manifest_path.parent / manifest['basis']['path'], expected_sha256=manifest['basis']['sha256'], validator=_validate_basis)
            bn, bf = _native(basis)
            for field in ('receiver', 'length_m', 'width_m', 'bed_elevation_m', 'bed_slope', 'roughness', 'max_depth_m', 'terminal_kind', 'receiver_distance_m'):
                np.testing.assert_array_equal(getattr(bn, field), getattr(net, field))
            np.testing.assert_array_equal(bf.time_seconds, forcing.time_seconds)
            np.testing.assert_array_equal(bf.local_q_m3_s, forcing.local_q_m3_s)
            np.testing.assert_array_equal(basis['arrays']['counts'], np.full(4, product['level'], np.int64))
            bm = basis['metadata']
            if bm['material'] != old['material'] or bm['material_inputs'] != old['material_inputs'] or bm['channel_config'] != asdict(ChannelConfig(max_dt_seconds=product['dt_seconds'], max_steps=10000)) or (bm['sediment_config'] != asdict(SedimentConfig(max_dt_seconds=product['dt_seconds'], max_steps=10000))):
                raise ValueError('original material/config/input changed')
            observations[name] = audit_series(manifest_path, POLICY['sample_times_seconds'])
            resources[name] = json.loads((manifest_path.parent / 'worker-resource.json').read_text(encoding='utf-8'))
            observations[name]['actual_segment_endpoints_seconds'] = manifest['segment_endpoints_seconds']
            observations[name]['time_policy_continuation'] = manifest.get('continuation')
            resource = resources[name]
            resource['old_180s_passed'] = resource['elapsed_seconds'] <= POLICY['max_worker_seconds'] and resource['peak_rss_bytes'] <= POLICY['max_worker_rss_bytes'] and (resource['status'] == 'complete')
            resource['new_offline_600s_passed'] = resource['elapsed_seconds'] <= OFFLINE_RESOURCE_POLICY['max_worker_seconds'] and resource['peak_rss_bytes'] <= OFFLINE_RESOURCE_POLICY['max_worker_rss_bytes'] and (resource['status'] == 'complete')
            if observations[name]['status'] != 'complete' or observations[name]['last_time_seconds'] != 900.0:
                raise ValueError('full900s comparison not complete')
            if observations[name]['max_product_bytes'] > POLICY['max_product_trace_bytes'] or observations[name]['nodes'] > POLICY['max_nodes']:
                raise ValueError('bounded product resource failed')
    reference = observations['level512-fine']
    spatial = {str(level): difference(observations[f'level{level}'], reference) for level in POLICY['levels']}
    temporal = {str(level): difference(observations[f'level{level}'], observations[f'level{level}-fine']) for level in POLICY['levels']}

    def time_ok(error):
        return max((error[k] for k in ('water_volume_m3', 'mobile_solid_m3', 'loose_solid_m3', 'cumulative_rock_removed_m3', 'export_m3', 'solid_export_m3'))) <= POLICY['temporal_relative_tolerance'] and max((error[k] for k in ('half_export_seconds', 'half_solid_export_seconds'))) <= POLICY['half_export_time_tolerance_seconds'] and (error['bed_elevation_m'] <= POLICY['bed_absolute_tolerance_m'])
    accepted = []
    for level in (128, 256):
        e = spatial[str(level)]
        stock_ok = max((e[k] for k in ('water_volume_m3', 'mobile_solid_m3', 'loose_solid_m3', 'cumulative_rock_removed_m3'))) <= POLICY['inventory_relative_tolerance']
        export_ok = max(e['export_m3'], e['solid_export_m3']) <= POLICY['export_relative_tolerance']
        timing_ok = max(e['half_export_seconds'], e['half_solid_export_seconds']) <= POLICY['half_export_time_tolerance_seconds']
        if stock_ok and export_ok and timing_ok and (e['bed_elevation_m'] <= POLICY['bed_absolute_tolerance_m']) and time_ok(temporal[str(level)]) and time_ok(temporal['512']):
            accepted.append(level)
    normal_measurement = None
    normal_passed = False
    if 'normal_worker' in report:
        worker_pin = report['normal_worker']
        normal_manifest_path = path.parent / worker_pin['manifest_path']
        resource_path = path.parent / worker_pin['resource_path']
        if file_sha256(normal_manifest_path) != worker_pin['manifest_sha256'] or file_sha256(resource_path) != worker_pin['resource_sha256']:
            raise ValueError('normal worker evidence pin changed')
        normal_manifest = json.loads(normal_manifest_path.read_text(encoding='utf-8'))
        if 'continuation' in normal_manifest or 'storage_interruption' in normal_manifest:
            raise ValueError('normal worker must be uninterrupted')
        with patch('terrain_pipeline.surface_rivers.metric_resolution_series.solve_channel', side_effect=AssertionError('cold normal water')), patch('terrain_pipeline.surface_rivers.metric_resolution_series.solve_sediment', side_effect=AssertionError('cold normal solid')):
            normal_observation = audit_series(normal_manifest_path, POLICY['sample_times_seconds'])
        normal_resource = json.loads(resource_path.read_text(encoding='utf-8'))
        if normal_resource.get('implementation_sha256') != implementation_pins():
            raise ValueError('normal worker final implementation changed')
        if normal_observation['basis_identity_sha256'] != reference['basis_identity_sha256'] or normal_observation['source_manifest'] != pin or normal_resource['level'] != 512 or (normal_resource['dt_seconds'] != 0.125) or (normal_resource['horizon_seconds'] != 900.0):
            raise ValueError('normal benchmark original reference changed')
        normal_error = difference(normal_observation, reference)
        normal_passed = normal_resource['status'] == normal_observation['status'] == 'complete' and normal_observation['last_time_seconds'] == 900.0 and (normal_resource['elapsed_seconds'] <= 600.0) and (normal_resource['peak_rss_bytes'] <= 1024 ** 3) and time_ok(normal_error)
        normal_measurement = dict(resource=normal_resource, reference_error=normal_error, passed=normal_passed, observations=normal_observation)
    return dict(status='accepted_original_active900s' if accepted and normal_passed else 'unresolved_original_active900s', accepted_uniform_levels=accepted, physical_status='accepted_original_active900s' if accepted else 'unresolved_original_active900s', engineering_status='passed_normal_worker' if normal_passed else 'pending_normal_worker' if normal_measurement is None else 'failed_normal_worker', normal_resource_measurement=normal_measurement, minimum_accepted_level=min(accepted) if accepted else None, spatial_error=spatial, temporal_error=temporal, resources=resources, resource_extension=extension, coverage_policy=COVERAGE_POLICY, engineering_budget_policy=ENGINEERING_POLICY, observations=observations, scope='entire original four-node900s active frozen-water sediment domain; no dynamic bed-feedback spatial or2D acceptance')

def assemble_reused_report(output, normal_worker=None):
    import os
    output = Path(output).resolve()
    coverage_path = output / 'coverage-policy.json'
    if not coverage_path.exists():
        raise ValueError('coverage policy must be frozen before final scores')
    coverage_record = json.loads(coverage_path.read_text(encoding='utf-8'))
    if coverage_record['coverage_policy'] != COVERAGE_POLICY:
        raise ValueError('frozen coverage policy changed')
    _, _, _, pin = source()
    report = dict(schema='terragenesis-active-spatial-series-verification-v2', policy=POLICY, coverage_policy=COVERAGE_POLICY, source=pin, cases={}, coverage_policy_sha256=file_sha256(coverage_path), engineering_budget_supplement_path='engineering-budget-supplement.json', engineering_budget_supplement_sha256=file_sha256(output / 'engineering-budget-supplement.json'), resource_extension_path='../spatial-series-20261011-final/resource-extension.json', save_policy_disclosure='actual schedules pinned per case; completed128/256 use original15s saves;512 reuse pinned complete prefixes then v2 downward-representable times with5s suffix saves')
    for level in POLICY['levels']:
        for fine in (False, True):
            name = f'level{level}' + ('-fine' if fine else '')
            parent = output if level == 512 else output.parent / 'spatial-series-20261011-02'
            manifest_path = parent / name / 'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest['status'] != 'complete':
                raise ValueError('cannot assemble incomplete case: ' + name)
            report['cases'][name] = dict(path=os.path.relpath(manifest_path, output), sha256=file_sha256(manifest_path), level=level, dt_seconds=POLICY['temporal_dt_seconds'] if fine else POLICY['dt_seconds'], actual_segment_endpoints_seconds=manifest['segment_endpoints_seconds'])
    path = output / 'report.json'
    if normal_worker is not None:
        normal_worker = Path(normal_worker).absolute()
        manifest = normal_worker / 'manifest.json'
        resource = normal_worker / 'worker-resource.json'
        report['normal_worker'] = dict(manifest_path=str(manifest), manifest_sha256=file_sha256(manifest), resource_path=str(resource), resource_sha256=file_sha256(resource))
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    report['audit'] = cold_report(path)
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report

def verify(output, reference_only=False, resume=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=resume)
    _, _, _, pin = source()
    report = dict(schema='terragenesis-active-spatial-series-verification-v1', policy=POLICY, source=pin, cases={})
    if resume:
        report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
        if report['policy'] != POLICY or report['source'] != pin:
            raise ValueError('resume policy/source changed')
    else:
        (output / 'frozen-policy.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for level in reversed(POLICY['levels']):
        for fine in (True, False):
            name = f'level{level}' + ('-fine' if fine else '')
            dt = POLICY['temporal_dt_seconds'] if fine else POLICY['dt_seconds']
            if name in report['cases']:
                previous = report['cases'][name]
                if previous['level'] != level or previous['dt_seconds'] != dt or file_sha256(output / previous['path']) != previous['sha256']:
                    raise ValueError('previous worker pin changed')
                continue
            result = subprocess.run([sys.executable, '-B', '-m', 'tools.verify_td_active_spatial_series', '--worker', '--output', str(output / name), '--level', str(level), '--dt', str(dt)], check=True, capture_output=True, text=True)
            print(result.stdout.strip(), flush=True)
            manifest = output / name / 'manifest.json'
            report['cases'][name] = dict(path=str(manifest.relative_to(output)), sha256=file_sha256(manifest), level=level, dt_seconds=dt)
            (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            if reference_only:
                report['reference_worker_resource'] = json.loads((output / name / 'worker-resource.json').read_text(encoding='utf-8'))
                (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
                return report
    report['audit'] = cold_report(output / 'report.json')
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    p.add_argument('--worker', action='store_true')
    p.add_argument('--audit', action='store_true')
    p.add_argument('--level', type=int, default=512)
    p.add_argument('--dt', type=float, default=0.125)
    p.add_argument('--horizon', type=float, default=900.0)
    p.add_argument('--reference-only', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--record-resource-extension', action='store_true')
    p.add_argument('--reuse-complete-prefix')
    p.add_argument('--assemble-reused', action='store_true')
    p.add_argument('--normal-worker')
    a = p.parse_args()
    if a.record_resource_extension:
        result = record_resource_extension(a.output)
    elif a.worker:
        result = worker(a.output, a.level, a.dt, a.horizon, a.reuse_complete_prefix)
    elif a.audit:
        result = cold_report(a.output)
        (Path(a.output).parent / 'cold-audit.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    elif a.assemble_reused:
        result = assemble_reused_report(a.output, a.normal_worker)
    else:
        result = verify(a.output, a.reference_only, a.resume)
    print(json.dumps({k: v for k, v in result.get('audit', result).items() if k != 'observations'}, indent=2), flush=True)
