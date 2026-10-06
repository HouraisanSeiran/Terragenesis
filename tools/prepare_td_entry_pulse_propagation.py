"""Pinned preparation and explicitly gated two-level isolated pulse execution."""

import argparse
import gc
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_entry_shallow_water import MAX_BYTES, MAX_WORK, check_resource, compare_levels
from terrain_pipeline.td_entry_pulse_propagation import (
    FLAGS, ORDINARY_Q_M3_S, build_dry_drain_geometry, build_pulse_forcing,
    propagation_diagnostics, run_pulse_level, validate_experiment)
from tools.prepare_td_entry_shallow_water import load, pin, publish, read_json, save

PARENT = ROOT/'verification/natural-river-network/entry-shallow-water-prepare-20261005-03'
PARENT_SHA = '232c9d1d378b02a7abc76670a8989fa97c58d7201b0ec3b323876ceaf5aedc56'
PARENT_AUDIT_SHA = 'fc0f18c09656ceefeffa5453f67a7f6a5f483e919273da993d32020b1ff38539'
RESPONSE = ROOT/'verification/natural-river-network/entry-shallow-water-events-20261005-01'
RESPONSE_SHA = '6879b7114f575ee7231c3b75e91c604b18e73d25473f3b981592289681b26767'
EVENT_INDEX_SHA = '83c4feca72e4a21c7cd14f896f88e3cab6291f3d356ab807a35511fd4009c989'
EVENT_AUDIT_SHA = 'b060d06fbb5933cbc7ed47fb17605ab2bf0dec9fbde84ecce50296ac63af8d0e'
NEW_CODE = ('terrain_pipeline/td_entry_pulse_propagation.py', 'tools/prepare_td_entry_pulse_propagation.py')


def check_codes(code_pins):
    for name, sha256 in code_pins.items():
        if file_sha256(ROOT/name) != sha256:
            raise ValueError('frozen_code_pin_changed:'+name)


def read_accepted_parent():
    parent = read_json(PARENT/'index.json', PARENT_SHA)
    audit = read_json(PARENT/'independent-audit.json', PARENT_AUDIT_SHA)
    if audit['status'] != 'passed' or audit['index_sha256'] != PARENT_SHA:
        raise ValueError('prepare03_audit_not_bound_or_passed')
    check_codes(parent['code_sha256'])
    carrier, geometry, old_forcing = (load(parent[name]) for name in ('carrier', 'geometry', 'forcing'))
    if (audit['carrier']['entry_id'] != carrier['metadata']['entry_id'] or
            audit['carrier']['ordinary_q_m3_s'] != ORDINARY_Q_M3_S or
            not audit['carrier']['own_bed_forcing_verified'] or
            not audit['carrier']['lake_support_bed_unmodified']):
        raise ValueError('parent_carrier_acceptance_mismatch')
    return parent, carrier, geometry, old_forcing


def prior_response():
    index = read_json(RESPONSE/'index.json', EVENT_INDEX_SHA)
    audit = read_json(RESPONSE/'independent-audit.json', EVENT_AUDIT_SHA)
    report = read_json(RESPONSE/'response-diagnostics.json', RESPONSE_SHA)
    if audit['status'] != 'passed' or audit['index_sha256'] != EVENT_INDEX_SHA or report['audit_sha256'] != EVENT_AUDIT_SHA:
        raise ValueError('old_response_acceptance_mismatch')
    normal = next(case for case in report['cases'] if case['case_name'] == 'normal-pulse-retreat-level-1')
    return dict(response=pin(RESPONSE/'response-diagnostics.json'), index=pin(RESPONSE/'index.json'),
                audit=pin(RESPONSE/'independent-audit.json'), prior_duration_s=normal['time_s'][-1],
                prior_centerline_front_m=normal['centerline_land_wet_front_m'][-1],
                prior_cross_30m_m3=next(cut['cumulative_downstream_m3'] for cut in normal['cuts'] if cut['station_m'] == 30),
                prior_cross_60m_m3=next(cut['cumulative_downstream_m3'] for cut in normal['cuts'] if cut['station_m'] == 60),
                duration_selection='240s is a declared new event with 120s pulse then 120s retreat; prior 60s front 26.5625m motivates extension but does not guarantee 60m arrival')


def prepare(output):
    started = time.monotonic()
    parent, carrier, parent_geometry, old_forcing = read_accepted_parent()
    response = prior_response()
    geometry = build_dry_drain_geometry(carrier, parent_geometry)
    forcing = build_pulse_forcing(carrier, geometry)
    if not np.array_equal(forcing['arrays']['forcing_m3_s'][0, 0], old_forcing['arrays']['forcing_m3_s'][0, 0]):
        raise ValueError('original_injection_mask_or_Q_changed')
    faces = len(geometry['arrays']['face_left'])+len(geometry['arrays']['boundary_cell'])
    work = 3*faces*(24000+48000)
    if work >= MAX_WORK:
        raise ValueError('nominal_two_level_work_not_below_6e9')
    codes = dict(parent['code_sha256'], **{name: file_sha256(ROOT/name) for name in NEW_CODE})
    manifest = dict(schema='td-entry-pulse-propagation-preparation-v1', status='prepared_requires_independent_audit',
        parent=pin(PARENT/'index.json'), parent_audit=pin(PARENT/'independent-audit.json'),
        source_parent_index=pin(PARENT/'index.json'), source_parent_audit=pin(PARENT/'independent-audit.json'),
        carrier=parent['carrier'], parent_geometry=parent['geometry'], parent_forcing=parent['forcing'],
        geometry=save(output/'geometry.npz', geometry), forcing=save(output/'forcing.npz', forcing),
        inputs=parent['inputs'], prior_response=response, code_sha256=codes, cases=[],
        declared_maxdt_s=[.01, .005],
        resource=dict(max_work=MAX_WORK, max_bytes=MAX_BYTES, max_cells=65536, estimated_two_level_face_work=work,
                      nominal_remaining_work_for_other_task11=MAX_WORK-work,
                      max_wall_per_case_s=7200., actual_peak_rss_bytes=check_resource(), wall_s=time.monotonic()-started, water_solves=0),
        semantics='new all-dry source-isolation experiment; prepare03 carrier unchanged; original wet support reception, not natural lake/mouth or continuation', **FLAGS)
    publish(output/'index.json', manifest)
    return manifest


def run(input_dir, input_sha256, audit_path, audit_sha256, output):
    started = time.monotonic()
    index_path = input_dir/'index.json'
    prepared = read_json(index_path, input_sha256)
    accepted = read_json(audit_path, audit_sha256)
    if (prepared['schema'] != 'td-entry-pulse-propagation-preparation-v1' or
            accepted['status'] != 'passed' or accepted['index_sha256'] != input_sha256):
        raise ValueError('independent_pulse_preparation_audit_required')
    check_codes(prepared['code_sha256'])
    parent, carrier, parent_geometry, old_forcing = read_accepted_parent()
    if prepared['carrier'] != parent['carrier'] or prepared['parent'] != pin(PARENT/'index.json') or prepared['parent_audit'] != pin(PARENT/'independent-audit.json'):
        raise ValueError('immutable_carrier_or_parent_pin_changed')
    if (prepared['source_parent_index'] != prepared['parent'] or
            prepared['source_parent_audit'] != prepared['parent_audit']):
        raise ValueError('source_parent_alias_pin_mismatch')
    geometry, forcing = load(prepared['geometry']), load(prepared['forcing'])
    expected_geometry = build_dry_drain_geometry(carrier, parent_geometry)
    if geometry['identity_sha256'] != expected_geometry['identity_sha256']:
        raise ValueError('dry_drain_geometry_has_unapproved_changes')
    validate_experiment(carrier, geometry, forcing)
    if (prepared['declared_maxdt_s'] != [.01, .005] or forcing['metadata']['duration_s'] != 240. or
            forcing['metadata']['pulse_s'] != 120. or forcing['metadata']['interval_s'] != 10.):
        raise ValueError('task11_time_schedule_or_maxdt_changed')
    manifest = dict(schema='td-entry-pulse-propagation-run-v1', status='running', parent=pin(index_path),
                    preparation_audit=pin(audit_path), carrier=prepared['carrier'], geometry=prepared['geometry'],
                    source_parent_index=prepared['source_parent_index'], source_parent_audit=prepared['source_parent_audit'],
                    declared_maxdt_s=prepared['declared_maxdt_s'],
                    forcing=prepared['forcing'], inputs=prepared['inputs'], code_sha256=prepared['code_sha256'],
                    prior_response=prepared['prior_response'], cases=[], comparisons=[], **FLAGS)
    work, levels = 0, []
    for level, dt in enumerate(prepared['declared_maxdt_s']):
        case_id = 'isolated-normal-pulse-retreat-level-'+str(level)
        try:
            state, packets, first_rk = run_pulse_level(carrier, geometry, forcing, max_dt_s=dt,
                work_limit=int((MAX_WORK-work)*2//3), wall_limit_s=7200.)
        except (RuntimeError, ValueError, MemoryError) as error:
            manifest['cases'].append(dict(case_id=case_id, level=level, status='diagnostic_failure', failure=str(error)))
            manifest.update(status='diagnostic_failure', failure=str(error))
            break
        completed = state['metadata']['status'] == 'completed'
        used = state['metadata']['face_evaluations']*3//2 if completed else state['metadata']['resource_work_upper_bound']
        work += used
        diagnostic = propagation_diagnostics(carrier, geometry, state, packets)
        case = dict(case_id=case_id, case_index=0, level=level, max_dt_s=dt,
                    state=save(output/(case_id+'-state.npz'), state),
                    intervals=save(output/(case_id+'-intervals.npz'), packets),
                    first_rk=save(output/(case_id+'-first-rk.npz'), first_rk), diagnostics=diagnostic,
                    status='saved_requires_independent_audit' if completed and diagnostic['source_isolation_diagnostic_passed'] else 'diagnostic_failure')
        manifest['cases'].append(case)
        if case['status'] == 'diagnostic_failure':
            manifest.update(status='diagnostic_failure', failure=state['metadata'].get('failure') or 'global_substep_boundary_input_not_exact_zero')
            break
        levels.append((state, packets))
        del first_rk
        gc.collect()
    if len(levels) == 2:
        comparison = compare_levels(levels[0][0], levels[1][0], levels[0][1], levels[1][1])
        comparison['case_name'] = 'isolated-normal-pulse-retreat'
        manifest['comparisons'].append(comparison)
        manifest['status'] = 'saved_requires_independent_audit'
    manifest['resource'] = dict(actual_peak_rss_bytes=check_resource(), wall_s=time.monotonic()-started,
        total_face_work_units=work, max_work=MAX_WORK, max_bytes=MAX_BYTES,
        face_work_semantics='all RK1+RK2+endpoint faces; failure reserves allocation, no continuation or repeated event')
    publish(output/'index.json', manifest)
    return manifest


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-only', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--input-sha256')
    parser.add_argument('--preparation-audit', type=Path)
    parser.add_argument('--preparation-audit-sha256')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    allowed = (ROOT/'verification/natural-river-network').resolve()
    if output.exists() or not output.is_relative_to(allowed) or not output.name.startswith('entry-pulse-propagation-'):
        raise ValueError('new_independent_entry_pulse_output_directory_required')
    if args.run and not all((args.input, args.input_sha256, args.preparation_audit, args.preparation_audit_sha256)):
        parser.error('--run requires input index SHA and preparation audit path/SHA')
    result = (prepare(output) if args.prepare_only else
              run(args.input.resolve(), args.input_sha256, args.preparation_audit,
                  args.preparation_audit_sha256, output))
    print(json.dumps(dict(output=str(output), status=result['status'], cases=len(result['cases']), resource=result['resource'])))
    if result['status'] == 'diagnostic_failure':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
