"""Preflight/freeze or explicitly cold-run only the missing .005s pulse level.

No --resume exists. Failed/interrupted snapshots cannot be solver inputs; a new
authorized attempt requires a new directory and starts at physical time zero.
"""

import argparse
import copy
import gc
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_entry_pulse_incremental import EXECUTION_VERSION, PulseLock, atomic_index, run_fine_cold
from terrain_pipeline.td_entry_pulse_propagation import FLAGS, build_dry_drain_geometry, propagation_diagnostics, validate_experiment
from terrain_pipeline.td_entry_shallow_water import MAX_BYTES, MAX_WORK, check_resource, compare_levels
from tools.prepare_td_entry_shallow_water import load, pin, read_json, save

RECOVERY = ROOT/'verification/natural-river-network/entry-pulse-interruption-20261006-01'
RECOVERY_SHA = 'f364af912843dc967163f64ff86fa3589962d97ff303ebdff906a8d4dc6d1d2e'
AUDIT_SHA = '4ecf235bd5af156243ee1d55511b25386c56a6e7acd66ca26d63eb085e2bcb2b'
NEW_CODE = ('terrain_pipeline/td_entry_pulse_execution_v2.py',
            'terrain_pipeline/td_entry_pulse_incremental.py', 'tools/complete_td_entry_pulse_incremental.py')
CASE_ID = 'isolated-normal-pulse-retreat-level-1'
LOCK_PATH = ROOT/'verification/natural-river-network/.td-entry-pulse-incremental.lock'


def checked_pin(record):
    path = Path(record['path']).resolve(strict=True)
    if (not path.is_relative_to(ROOT) or file_sha256(path) != record['sha256'] or
            path.stat().st_size != record['bytes']):
        raise ValueError('immutable_parent_pin_mismatch:'+str(path))


def checked_json(record):
    checked_pin(record)
    return read_json(record['path'], record['sha256'])


def preflight(output):
    output = Path(output).resolve()
    allowed = ROOT/'verification/natural-river-network'
    if (output.exists() or not output.is_relative_to(allowed) or
            not output.name.startswith('entry-pulse-incremental-')):
        raise ValueError('new_entry_pulse_incremental_directory_required_no_resume')
    if LOCK_PATH.exists():
        raise ValueError('pulse_PID_lock_exists_operator_review_required:'+str(LOCK_PATH))
    recovered = read_json(RECOVERY/'index.json', RECOVERY_SHA)
    audit = read_json(RECOVERY/'independent-audit.json', AUDIT_SHA)
    if (recovered['schema'] != 'td-entry-pulse-interruption-recovery-v1' or audit['status'] != 'passed' or
            audit['index_sha256'] != RECOVERY_SHA or audit['solver_calls'] != 0 or
            audit['local_saved_hydraulics_verified'] is not True or
            audit['all_water_from_upstream_Q_verified'] is not True):
        raise ValueError('fixed_coarse_recovery_audit_not_accepted')
    original = checked_json(recovered['parent'])
    preparation_audit = checked_json(recovered['preparation_audit'])
    source = checked_json(recovered['source_parent_index'])
    source_audit = checked_json(recovered['source_parent_audit'])
    if (preparation_audit['status'] != 'passed' or preparation_audit['index_sha256'] != recovered['parent']['sha256'] or
            source_audit['status'] != 'passed' or source_audit['index_sha256'] != recovered['source_parent_index']['sha256']):
        raise ValueError('original_parent_audit_binding_mismatch')
    for key in ('carrier', 'geometry', 'forcing', 'declared_maxdt_s', 'code_sha256', 'inputs',
                'source_parent_index', 'source_parent_audit'):
        if recovered[key] != original[key]:
            raise ValueError('recovery_original_parent_mismatch:'+key)
    if recovered['carrier'] != source['carrier']:
        raise ValueError('original_source_carrier_changed')
    old_codes = dict(source['code_sha256'], **recovered['code_sha256'])
    for filename, sha256 in old_codes.items():
        path = (ROOT/filename).resolve(strict=True)
        if not path.is_relative_to(ROOT) or file_sha256(path) != sha256:
            raise ValueError('old_parent_code_pin_changed:'+filename)
    for record in recovered['inputs'].values():
        checked_pin(record)
    for key in ('carrier', 'geometry', 'forcing'):
        checked_pin(recovered[key])
    carrier, geometry, forcing = (load(recovered[key]) for key in ('carrier', 'geometry', 'forcing'))
    expected_geometry = build_dry_drain_geometry(carrier, load(source['geometry']))
    if expected_geometry['identity_sha256'] != geometry['identity_sha256']:
        raise ValueError('geometry_not_original_dry_drain')
    del expected_geometry
    validate_experiment(carrier, geometry, forcing)
    if (recovered['declared_maxdt_s'] != [.01, .005] or forcing['metadata']['duration_s'] != 240. or
            forcing['metadata']['pulse_s'] != 120. or forcing['metadata']['interval_s'] != 10.):
        raise ValueError('original_240s_120s_10s_dt_schedule_changed')
    if len(recovered['cases']) != 1 or recovered['cases'][0]['level'] != 0:
        raise ValueError('exactly_one_saved_coarse_level_required')
    coarse_case = recovered['cases'][0]
    if (coarse_case['case_index'] != 0 or coarse_case['max_dt_s'] != .01 or
            coarse_case['status'] != 'saved_requires_independent_audit'):
        raise ValueError('coarse_case_declaration_mismatch')
    for key in ('state', 'intervals', 'first_rk'):
        checked_pin(coarse_case[key])
    coarse_state = load(coarse_case['state'])
    coarse_meta = coarse_state['metadata']
    for key, expected in (('source_identity', carrier['identity_sha256']),
                          ('forcing_identity', forcing['identity_sha256']),
                          ('geometry_identity_sha256', geometry['identity_sha256'])):
        if coarse_meta[key] != expected:
            raise ValueError('coarse_identity_mismatch:'+key)
    if (coarse_meta['status'] != 'completed' or coarse_meta['committed_time_s'] != 240. or
            coarse_meta['max_dt_requested_s'] != .01 or
            not np.array_equal(coarse_state['arrays']['time_s'], forcing['arrays']['time_s'])):
        raise ValueError('coarse_not_complete_original_event')
    faces = len(geometry['arrays']['face_left'])+len(geometry['arrays']['boundary_cell'])
    coarse_work = coarse_meta['face_evaluations']*3//2
    if (coarse_meta['face_evaluations'] != 2*faces*coarse_meta['substeps'] or
            coarse_work != recovered['resource']['complete_saved_face_work_units'] or
            coarse_work != audit['complete_saved_face_work_units'] or
            recovered['resource']['conservatively_reserved_total_face_work_units'] != MAX_WORK or
            recovered['resource']['uncheckpointed_fine_attempt_work_unknown'] is not True):
        raise ValueError('old_saved_work_or_unknown_reservation_mismatch')
    del coarse_state
    codes = {name: file_sha256(ROOT/name) for name in NEW_CODE}
    minimum_work = 3*faces*math.ceil(240/.005)
    saved_estimate = geometry['arrays']['H2_m'].size*8*(90+80*24)
    if minimum_work > MAX_WORK:
        raise ValueError('fine_minimum_face_work_exceeds_new_budget')
    report = dict(schema='td-entry-pulse-incremental-preflight-v1', status='ready_for_coordinator_precheck',
        output=str(output), recovery_parent=pin(RECOVERY/'index.json'), recovery_audit=pin(RECOVERY/'independent-audit.json'),
        original_parent=recovered['parent'], original_preparation_audit=recovered['preparation_audit'],
        carrier=recovered['carrier'], geometry=recovered['geometry'], forcing=recovered['forcing'],
        coarse_case=coarse_case, old_parent_code_sha256=old_codes, code_sha256=recovered['code_sha256'],
        execution_code_sha256=codes,
        incremental_auditor_code_sha256=file_sha256(ROOT/'tools/audit_td_entry_pulse_incremental.py'),
        execution_version=EXECUTION_VERSION, cold_only=True, snapshot_resumable=False,
        restart_requires_time_zero=True, fine_max_dt_s=.005, declared_maxdt_s=[.01, .005],
        duration_s=240., pulse_s=120., interval_s=10., cells=geometry['arrays']['H2_m'].size, faces=faces,
        new_fine_max_work=MAX_WORK, new_fine_max_wall_s=7200., max_bytes=MAX_BYTES,
        nominal_fine_face_work=minimum_work, nominal_is_not_CFL_upper_bound=True,
        nominal_new_work_headroom=MAX_WORK-minimum_work, saved_array_estimate_bytes=saved_estimate,
        reused_coarse_actual_face_work=coarse_work, coarse_solver_calls_this_attempt=0,
        old_allocation_reserved_face_work=MAX_WORK, lost_old_fine_actual_work_unknown=True,
        legacy_audit_combined_nominal_face_work=coarse_work+minimum_work,
        legacy_audit_combined_limit=MAX_WORK,
        lock_path=str(LOCK_PATH), water_solves=0)
    report['preflight_sha256'] = hashlib.sha256(json.dumps(report, sort_keys=True, allow_nan=False).encode('utf8')).hexdigest()
    check_resource()
    return report, recovered, carrier, geometry, forcing


def run(output, expected_preflight_sha256):
    report, recovered, carrier, geometry, forcing = preflight(output)
    if report['preflight_sha256'] != expected_preflight_sha256:
        raise ValueError('coordinator_preflight_fingerprint_mismatch')
    output = Path(output).resolve()
    with PulseLock(LOCK_PATH, expected_preflight_sha256):
        output.mkdir(parents=True, exist_ok=False)
        started = time.monotonic()
        manifest = copy.deepcopy(recovered)
        manifest.update(schema='td-entry-pulse-propagation-run-v1',
            persistence_schema='td-entry-pulse-incremental-v1', status='running',
            recovery_parent=report['recovery_parent'], recovery_audit=report['recovery_audit'],
            old_parent_code_sha256=report['old_parent_code_sha256'], code_sha256=report['code_sha256'],
            execution_code_sha256=report['execution_code_sha256'],
            incremental_auditor_code_sha256=report['incremental_auditor_code_sha256'],
            preflight_sha256=expected_preflight_sha256, preflight_report=report, snapshot_resumable=False,
            restart_requires_time_zero=True, execution_version=EXECUTION_VERSION,
            execution_mode='missing_fine_only_incremental_cold_start',
            checkpoints=[], comparisons=[], old_allocation_resource=copy.deepcopy(recovered['resource']), **FLAGS)
        manifest['resource'] = dict(max_work=MAX_WORK, max_bytes=MAX_BYTES, max_wall_per_case_s=7200.,
            actual_peak_rss_bytes=check_resource(), total_face_work_units=0,
            committed_fine_actual_face_work_units=0, actual_new_face_work_units=0, new_fine_max_work=MAX_WORK,
            new_fine_allocation_reserved_face_work_units=MAX_WORK,
            old_allocation_reserved_face_work_units=MAX_WORK, lost_old_fine_actual_work_unknown=True,
            reused_coarse_actual_face_work_units=report['reused_coarse_actual_face_work'],
            coarse_solver_calls_this_attempt=0, fine_solver_calls_this_attempt=0, committed_fine_time_s=0.,
            face_work_semantics='this attempt fine only: RK1+RK2+endpoint at every actual substep; coarse reuse and old unknown allocation separately retained')
        atomic_index(output/'index.json', manifest)

        def commit(snapshot_pin, progress):
            manifest['checkpoints'].append(dict(snapshot=snapshot_pin, **progress))
            resource = manifest['resource']
            resource.update(total_face_work_units=progress['actual_face_work_units'],
                committed_fine_actual_face_work_units=progress['actual_face_work_units'],
                actual_new_face_work_units=progress['actual_face_work_units'],
                committed_fine_time_s=progress['time_s'],
                actual_peak_rss_bytes=max(resource['actual_peak_rss_bytes'], progress['actual_peak_rss_bytes'], check_resource()),
                wall_s=time.monotonic()-started)
            atomic_index(output/'index.json', manifest)

        try:
            manifest['resource']['fine_solver_calls_this_attempt'] = 1
            atomic_index(output/'index.json', manifest)
            state, packets, first_rk = run_fine_cold(carrier, geometry, forcing, output=output/'snapshots',
                code_sha256=report['execution_code_sha256'], on_commit=commit)
            diagnostic = propagation_diagnostics(carrier, geometry, state, packets)
            case = dict(case_id=CASE_ID, case_index=0, level=1, max_dt_s=.005,
                state=save(output/(CASE_ID+'-state.npz'), state),
                intervals=save(output/(CASE_ID+'-intervals.npz'), packets),
                first_rk=save(output/(CASE_ID+'-first-rk.npz'), first_rk), diagnostics=diagnostic,
                status='saved_requires_independent_audit' if diagnostic['source_isolation_diagnostic_passed'] else 'diagnostic_failure')
            manifest['cases'].append(case)
            del first_rk
            gc.collect()
            coarse_state = load(recovered['cases'][0]['state'])
            coarse_packets = load(recovered['cases'][0]['intervals'])
            comparison = compare_levels(coarse_state, state, coarse_packets, packets)
            comparison['case_name'] = 'isolated-normal-pulse-retreat'
            manifest['comparisons'].append(comparison)
            manifest['status'] = case['status']
            fine_work = state['metadata']['actual_face_work_units']
            manifest['resource'].update(total_face_work_units=fine_work,
                new_fine_completed_actual_face_work_units=fine_work,
                new_fine_allocation_reserved_face_work_units=0,
                legacy_audit_saved_pair_face_work_units=report['reused_coarse_actual_face_work']+fine_work,
                uncommitted_fine_work_unknown=False)
            if manifest['status'] == 'diagnostic_failure':
                manifest['failure'] = 'global_substep_boundary_input_not_exact_zero'
        except BaseException as error:
            manifest.update(status='diagnostic_failure', failure=type(error).__name__+':'+str(error),
                restart_policy='new authorized attempt, new directory, dry state at physical time zero; no snapshot resume')
            manifest['resource'].update(uncommitted_fine_work_unknown=True,
                new_fine_allocation_reserved_face_work_units=MAX_WORK)
            manifest['resource']['wall_s'] = time.monotonic()-started
            atomic_index(output/'index.json', manifest)
            raise
        manifest['resource'].update(wall_s=time.monotonic()-started,
            actual_peak_rss_bytes=max(manifest['resource']['actual_peak_rss_bytes'], check_resource()))
        atomic_index(output/'index.json', manifest)
        return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--preflight-sha256')
    args = parser.parse_args()
    if args.run and not args.preflight_sha256:
        parser.error('--run requires the coordinator-reviewed --preflight-sha256')
    if args.preflight:
        result = preflight(args.output)[0]
    else:
        manifest = run(args.output, args.preflight_sha256)
        result = dict(output=str(args.output.resolve()), index_sha256=file_sha256(args.output/'index.json'),
                      status=manifest['status'], cases=len(manifest['cases']), resource=manifest['resource'])
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    if result['status'] == 'diagnostic_failure':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
