"""Cold audit incremental fine commits, then reuse the original pulse audit.

The output retains the old audit schema for the unchanged pure-IO exporter.
The original audit's combined saved-pair 6e9 gate is additionally retained; it
is not an accounting reset of either the old allocation or the new fine budget.
"""

import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_entry_pulse_incremental import EXECUTION_VERSION, read_snapshot, snapshot_binding
from tools.audit_td_entry_shallow_water import check_memory, read_bundle, read_json
from tools.audit_td_entry_pulse_propagation import audit as audit_original
from tools.complete_td_entry_pulse_incremental import RECOVERY, RECOVERY_SHA, AUDIT_SHA, NEW_CODE, checked_pin

AUDIT_CODE = ('tools/audit_td_entry_pulse_incremental.py', 'tools/audit_td_entry_pulse_propagation.py',
              'tools/audit_td_entry_shallow_water.py', 'tools/td_entry_saved_audit.py',
              'tools/single_domain_shallow_water_audit.py')


def exact(actual, expected, name):
    if not np.array_equal(actual, expected):
        raise ValueError('incremental_snapshot_final_mismatch:'+name)


def check_snapshot_series(checkpoints, state, intervals, first_rk, binding, geometry):
    arrays, meta = state['arrays'], state['metadata']
    count = len(arrays['time_s'])-1
    if len(checkpoints) != count or count == 0:
        raise ValueError('complete_saved_snapshot_series_required')
    face_count = len(geometry['arrays']['face_left'])+len(geometry['arrays']['boundary_cell'])
    previous_work = previous_steps = summed_work = 0
    previous_internal = np.zeros(len(geometry['arrays']['face_left']))
    previous_boundary = np.zeros(len(geometry['arrays']['boundary_cell']))
    for interval, entry in enumerate(checkpoints):
        checked_pin(entry['snapshot'])
        snapshot = read_snapshot(entry['snapshot'], binding)
        saved, progress = snapshot['arrays'], snapshot['metadata']
        if progress['interval'] != interval or progress['time_s'] != arrays['time_s'][interval+1]:
            raise ValueError('snapshot_order_or_global_time_mismatch')
        for key, value in entry.items():
            if key != 'snapshot' and progress.get(key) != value:
                raise ValueError('snapshot_manifest_progress_mismatch:'+key)
        expected_keys = {'depth_m', 'momentum_m2_s', 'ledger', 'final_internal_q_m3_s', 'final_boundary_q_m3_s'}
        expected_keys.update('interval__'+key for key in intervals['arrays'])
        expected_keys.update('rk__'+key for key in first_rk['arrays'])
        if set(saved) != expected_keys:
            raise ValueError('snapshot_observer_schema_mismatch')
        exact(saved['depth_m'], arrays['depth_m'][interval+1], 'depth')
        momentum = np.column_stack((arrays['momentum_x_m2_s'][interval+1].ravel(),
                                    arrays['momentum_z_m2_s'][interval+1].ravel()))
        exact(saved['momentum_m2_s'], momentum, 'real_momentum')
        exact(saved['ledger'], arrays['ledger'][interval+1], 'gross_ledger')
        for name, observer in (('interval', intervals), ('rk', first_rk)):
            for key, value in observer['arrays'].items():
                snapshot_value = saved[name+'__'+key]
                if name+'__'+key in progress['observer_scalar_keys']:
                    snapshot_value = snapshot_value.reshape(())
                exact(snapshot_value, value[interval], name+':'+key)
        exact(saved['final_internal_q_m3_s'], saved['interval__internal_q_after_m3_s'], 'internal_endpoint')
        exact(saved['final_boundary_q_m3_s'], saved['interval__boundary_q_after_m3_s'], 'boundary_endpoint')
        exact(saved['interval__internal_q_before_m3_s'], previous_internal, 'internal_endpoint_continuity')
        exact(saved['interval__boundary_q_before_m3_s'], previous_boundary, 'boundary_endpoint_continuity')
        previous_internal = saved['final_internal_q_m3_s'].copy()
        previous_boundary = saved['final_boundary_q_m3_s'].copy()
        work, steps = progress['actual_face_work_units'], progress['substeps']
        if (type(work) is not int or type(steps) is not int or steps <= previous_steps or work <= previous_work or
                work != 3*face_count*steps or progress['face_evaluations'] != 2*face_count*steps or
                progress['actual_peak_rss_bytes'] > 1024**3 or progress['wall_s'] > 7200.):
            raise ValueError('checkpoint_actual_RK_endpoint_work_or_resource_mismatch')
        if progress['budget'] != meta['budget']:
            raise ValueError('checkpoint_final_physical_budget_mismatch')
        summed_work += work-previous_work
        previous_work, previous_steps = work, steps
        del snapshot
        check_memory()
    exact(previous_internal, arrays['final_internal_q_m3_s'], 'final_internal_endpoint')
    exact(previous_boundary, arrays['final_boundary_q_m3_s'], 'final_boundary_endpoint')
    if summed_work != meta['actual_face_work_units'] or previous_steps != meta['substeps']:
        raise ValueError('snapshot_final_actual_work_mismatch')
    for key in ('minimum_dt_s', 'maximum_dt_s', 'maximum_wave_speed_m_s', 'limited_donor_count'):
        if progress[key] != meta['diagnostics'][key]:
            raise ValueError('snapshot_final_diagnostics_mismatch:'+key)
    return summed_work


def audit(index, index_path):
    if (index['schema'] != 'td-entry-pulse-propagation-run-v1' or index['persistence_schema'] != 'td-entry-pulse-incremental-v1' or
            index['status'] != 'saved_requires_independent_audit' or
            index['execution_mode'] != 'missing_fine_only_incremental_cold_start' or
            index['execution_version'] != EXECUTION_VERSION or index['snapshot_resumable'] is not False or
            index['restart_requires_time_zero'] is not True):
        raise ValueError('completed_extended_v1_cold_fine_index_required')
    if (Path(index['recovery_parent']['path']).resolve() != RECOVERY/'index.json' or
            index['recovery_parent']['sha256'] != RECOVERY_SHA or
            Path(index['recovery_audit']['path']).resolve() != RECOVERY/'independent-audit.json' or
            index['recovery_audit']['sha256'] != AUDIT_SHA):
        raise ValueError('fixed_recovery_parent_and_audit_required')
    recovered, recovered_audit = (read_json(index[key]) for key in ('recovery_parent', 'recovery_audit'))
    if recovered_audit['status'] != 'passed' or recovered_audit['index_sha256'] != RECOVERY_SHA:
        raise ValueError('fixed_recovery_audit_mismatch')
    for key in ('parent', 'preparation_audit', 'carrier', 'geometry', 'forcing', 'inputs',
                'source_parent_index', 'source_parent_audit', 'declared_maxdt_s', 'code_sha256'):
        if index[key] != recovered[key]:
            raise ValueError('old_parent_or_physics_pin_changed:'+key)
    if index['old_allocation_resource'] != recovered['resource']:
        raise ValueError('lost_old_fine_allocation_was_erased')
    execution_codes = index['execution_code_sha256']
    if set(execution_codes) != set(NEW_CODE):
        raise ValueError('exact_new_execution_code_pins_required')
    for filename, sha256 in execution_codes.items():
        if file_sha256(ROOT/filename) != sha256:
            raise ValueError('new_execution_code_changed:'+filename)
    auditor_sha = file_sha256(ROOT/'tools/audit_td_entry_pulse_incremental.py')
    if index['incremental_auditor_code_sha256'] != auditor_sha:
        raise ValueError('frozen_incremental_auditor_changed')
    frozen = dict(index['preflight_report'])
    frozen_sha = frozen.pop('preflight_sha256')
    calculated_sha = hashlib.sha256(json.dumps(frozen, sort_keys=True, allow_nan=False).encode('utf8')).hexdigest()
    if (frozen_sha != calculated_sha or index['preflight_sha256'] != calculated_sha or
            Path(frozen['output']).resolve() != Path(index_path).resolve().parent or
            frozen['execution_code_sha256'] != execution_codes or frozen['code_sha256'] != index['code_sha256'] or
            frozen['incremental_auditor_code_sha256'] != auditor_sha):
        raise ValueError('coordinator_frozen_preflight_mismatch')
    cases = sorted(index['cases'], key=lambda case: case['level'])
    if len(cases) != 2 or [case['level'] for case in cases] != [0, 1] or cases[0] != recovered['cases'][0]:
        raise ValueError('exact_original_coarse_case_reuse_required_no_regeneration')
    for key in ('state', 'intervals', 'first_rk'):
        checked_pin(cases[0][key])
        checked_pin(cases[1][key])
        fine_path = Path(cases[1][key]['path']).resolve()
        if fine_path.parent != Path(index_path).resolve().parent:
            raise ValueError('fine_case_not_saved_in_this_attempt')
    if cases[1]['case_index'] != 0 or cases[1]['max_dt_s'] != .005:
        raise ValueError('new_case_must_be_exact_fine_level')
    carrier, geometry, forcing = (read_bundle(index[key]) for key in ('carrier', 'geometry', 'forcing'))
    state, intervals, first_rk = (read_bundle(cases[1][key]) for key in ('state', 'intervals', 'first_rk'))
    meta, arrays = state['metadata'], state['arrays']
    if (meta['status'] != 'completed' or meta['committed_time_s'] != 240. or
            meta['execution_version'] != EXECUTION_VERSION or meta['snapshot_resumable'] is not False or
            len(arrays['time_s']) != 25 or len(intervals['arrays']['interval']) != 24 or
            len(first_rk['arrays']['interval']) != 24 or not np.array_equal(arrays['time_s'], np.arange(25)*10.) or
            np.any(arrays['depth_m'][0] != 0) or np.any(arrays['momentum_x_m2_s'][0] != 0) or
            np.any(arrays['momentum_z_m2_s'][0] != 0)):
        raise ValueError('complete_24_interval_25_frame_dry_time_zero_fine_required')
    for entry in index['checkpoints']:
        if Path(entry['snapshot']['path']).resolve().parent != Path(index_path).resolve().parent/'snapshots':
            raise ValueError('snapshot_not_owned_by_this_attempt')
    binding = snapshot_binding(carrier, geometry, forcing, .005, execution_codes)
    actual_new_work = check_snapshot_series(index['checkpoints'], state, intervals, first_rk, binding, geometry)
    resource = index['resource']
    old_work = recovered['resource']['complete_saved_face_work_units']
    if (not 0 < actual_new_work <= 6_000_000_000 or
            any(resource[key] != actual_new_work for key in ('actual_new_face_work_units', 'total_face_work_units',
                'committed_fine_actual_face_work_units', 'new_fine_completed_actual_face_work_units')) or
            resource['reused_coarse_actual_face_work_units'] != old_work or
            resource['old_allocation_reserved_face_work_units'] != 6_000_000_000 or
            resource['lost_old_fine_actual_work_unknown'] is not True or
            resource['new_fine_max_work'] != 6_000_000_000 or resource['max_work'] != 6_000_000_000 or
            resource['max_bytes'] != 1024**3 or resource['max_wall_per_case_s'] != 7200. or
            resource['coarse_solver_calls_this_attempt'] != 0 or resource['fine_solver_calls_this_attempt'] != 1 or
            resource['committed_fine_time_s'] != 240. or resource['uncommitted_fine_work_unknown'] is not False or
            resource['new_fine_allocation_reserved_face_work_units'] != 0 or
            resource['legacy_audit_saved_pair_face_work_units'] != old_work+actual_new_work or
            resource['actual_peak_rss_bytes'] > 1024**3 or meta['total_wall_s'] > 7200.):
        raise ValueError('new_fine_or_old_reuse_resource_accounting_mismatch')
    del state, intervals, first_rk, carrier, geometry, forcing
    gc.collect()
    result = audit_original(index)
    result.update(incremental_persistence_verified=True, execution_code_pins_verified=True,
        original_coarse_exact_three_artifact_reuse_verified=True, completed_snapshots=24, saved_frames=25,
        actual_new_face_work_units=actual_new_work, reused_coarse_actual_face_work_units=old_work,
        old_lost_fine_actual_work_unknown=True, old_allocation_reserved_face_work_units=6_000_000_000,
        snapshot_resumable=False, restart_requires_time_zero=True,
        execution_mode=index['execution_mode'], water_solves=0,
        audit_code_sha256=dict(execution_codes, **{filename: file_sha256(ROOT/filename) for filename in AUDIT_CODE}),
        actual_peak_incremental_audit_rss_bytes=check_memory())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/'verification/natural-river-network'):
        raise ValueError('new_incremental_independent_audit_output_required')
    result = audit(read_json(dict(path=str(args.input.resolve()), sha256=args.sha256)), args.input)
    result['index_sha256'] = args.sha256
    publish_bytes(output, (json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf8'))
    print(json.dumps({key: value for key, value in result.items() if key not in
                     ('cases', 'source_isolated_reception', 'audit_code_sha256')}, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
