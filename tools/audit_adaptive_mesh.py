"""Consolidated audit_adaptive_mesh implementations; numeric expressions preserved."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import argparse as _i18_argparse
import json as _i18_json
import hashlib as _i18_hashlib
import os as _i18_os
from pathlib import Path as _i18_Path
import sys as _i18_sys
import time as _i18_time
import numpy as _i18_np
import psutil as _i18_psutil
from tools.audit_single_domain_fine_stage import read_json as _i18_read_json
from tools.audit_single_domain_fine_stage import read_bundle as _i18_read_bundle
from tools.audit_single_domain_fine_stage import audit_fan as _i18_audit_fan
import argparse as _i19_argparse
import json as _i19_json
import os as _i19_os
from pathlib import Path as _i19_Path
import sys as _i19_sys
import time as _i19_time
import psutil as _i19_psutil
import numpy as _i19_np
from tools.audit_single_domain_fine_stage import read_json as _i19_read_json
from tools.audit_single_domain_fine_stage import read_bundle as _i19_read_bundle
from tools.audit_shallow_water import face_flux as _x0_face_flux
CATEGORY = 'B'
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    _i18_os.environ.setdefault(name, '1')
ROOT = _i18_Path(__file__).resolve().parents[1]
_i18_sys.path.insert(0, str(ROOT))

def physical_rhs(geometry, state, tailwater, gravity, dt):
    from terrain_pipeline.adaptive_mesh import storage_stage as _i18_storage_stage
    a, m = (geometry['arrays'], geometry['metadata'])
    stage = _i18_storage_stage(state[:, 0], geometry)
    velocity = _i18_np.divide(state[:, 1:], state[:, 0, None], out=_i18_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    left, right, axis = (a['face_left'], a['face_right'], a['face_axis'])
    cells, area = (a['boundary_cell'], a['leaf_area_m2'])
    internal, boundary = (_i18_np.zeros((len(left), 3)), _i18_np.zeros((len(cells), 3)))
    pressure = _i18_np.zeros_like(state)
    for direction in (0, 1):
        mask = axis == direction
        crest = a['face_crest_relative_m'][mask]
        hl, hr = (_i18_np.maximum(stage[left[mask]] - crest, 0), _i18_np.maximum(stage[right[mask]] - crest, 0))
        first, second = (_i18_np.column_stack((hl, hl[:, None] * velocity[left[mask]])), _i18_np.column_stack((hr, hr[:, None] * velocity[right[mask]])))
        flux, _, _ = _x0_face_flux(first, second, crest, crest, gravity, direction)
        internal[mask] = flux
        _i18_np.add.at(pressure[:, direction + 1], left[mask], 0.5 * gravity * hl ** 2 / area[left[mask]])
        _i18_np.add.at(pressure[:, direction + 1], right[mask], -0.5 * gravity * hr ** 2 / area[right[mask]])
        mask = a['boundary_axis'] == direction
        ids, kind, sign = (cells[mask], a['boundary_kind'][mask], a['boundary_sign'][mask])
        crest = a['boundary_bed_relative_m'][mask].copy()
        opened = kind != 0
        crest[opened] = _i18_np.maximum(crest[opened], a['boundary_crest_m'][mask][opened] - m['hydraulic_datum_m'])
        h = _i18_np.maximum(stage[ids] - crest, 0)
        first = _i18_np.column_stack((h, h[:, None] * velocity[ids]))
        ghost = first.copy()
        ghost[:, direction + 1] *= -1
        outside = _i18_np.where(kind == 1, crest, tailwater[mask] - m['hydraulic_datum_m'])
        ghost[opened, 0] = _i18_np.maximum(outside[opened] - crest[opened], 0)
        ghost[opened, 1:] = 0
        first[:, direction + 1] *= sign
        ghost[:, direction + 1] *= sign
        flux, _, _ = _x0_face_flux(first, ghost, crest, crest, gravity, direction)
        flux[:, direction + 1] *= sign
        boundary[mask] = flux
        _i18_np.add.at(pressure[:, direction + 1], ids, sign * 0.5 * gravity * h ** 2 / area[ids])
    outgoing = _i18_np.bincount(left, weights=_i18_np.maximum(internal[:, 0], 0), minlength=len(state))
    outgoing += _i18_np.bincount(right, weights=_i18_np.maximum(-internal[:, 0], 0), minlength=len(state))
    outgoing += _i18_np.bincount(cells, weights=_i18_np.maximum(boundary[:, 0], 0), minlength=len(state))
    scale = _i18_np.ones(len(state))
    limited = outgoing * dt > state[:, 0] * area
    scale[limited] = state[limited, 0] * area[limited] / (dt * outgoing[limited]) * (1 - 1e-12)
    internal *= _i18_np.where(internal[:, 0] >= 0, scale[left], scale[right])[:, None]
    boundary *= _i18_np.where(boundary[:, 0] >= 0, scale[cells], 1.0)[:, None]
    rhs = pressure.copy()
    _i18_np.add.at(rhs, left, -internal / area[left, None])
    _i18_np.add.at(rhs, right, internal / area[right, None])
    _i18_np.add.at(rhs, cells, -boundary / area[cells, None])
    return (rhs, internal, boundary, pressure)

def audit_step(packet, geometry, budget):
    from terrain_pipeline.adaptive_mesh import near as _i18_near
    from terrain_pipeline.adaptive_mesh import storage_stage as _i18_storage_stage
    a = geometry['arrays']
    before, predictor, after = (packet[name] for name in ('state_before', 'state_predictor', 'state_after'))
    dt, g = (packet['dt_s'], budget['gravity_m_s2'])
    area = a['leaf_area_m2']
    if not 0 < dt <= budget['max_dt_s'] or any((_i18_np.any(state[:, 0] < 0) for state in (before, predictor, after))):
        raise ValueError('adaptive independent sampled time/depth mismatch')
    stage = _i18_storage_stage(before[:, 0], geometry)
    minimum_bed = a['sorted_subcell_bed_relative_m'][a['subcell_offset']]
    velocity = _i18_np.divide(before[:, 1:], before[:, 0, None], out=_i18_np.zeros_like(before[:, 1:]), where=before[:, 0, None] > 0)
    speed = float((abs(velocity).sum(axis=1) + 2 * _i18_np.sqrt(g * _i18_np.maximum(stage - minimum_bed, 0))).max(initial=0))
    outside_bed = _i18_np.maximum(a['boundary_bed_relative_m'], a['boundary_crest_m'] - geometry['metadata']['hydraulic_datum_m'])
    outside = _i18_np.where(a['boundary_kind'] == 1, outside_bed, packet['tailwater_m'] - geometry['metadata']['hydraulic_datum_m'])
    speed = max(speed, float((2 * _i18_np.sqrt(g * _i18_np.maximum(outside - outside_bed, 0)[a['boundary_kind'] != 0])).max(initial=0)))
    if dt > budget['inertial_cfl'] * a['leaf_spacing_m'].min() / max(speed, 1e-12) + 1e-12:
        raise ValueError('adaptive independent CFL mismatch')
    equations = []
    for number, state in ((1, before), (2, predictor)):
        rhs, internal, boundary, pressure = physical_rhs(geometry, state, packet['tailwater_m'], g, dt)
        for name, expected in (('internal_flux', internal), ('boundary_flux', boundary), ('bed_source', pressure)):
            _i18_near(packet[f'rk{number}_' + name], expected, 'independent physical RK ' + name)
        rhs[:, 0] += packet['forcing_m3_s'] / area
        equations.append(rhs)
    _i18_near(predictor, before + dt * equations[0], 'independent predictor')
    updated = 0.5 * before + 0.5 * (predictor + dt * equations[1])
    stage = _i18_storage_stage(updated[:, 0], geometry)
    factor = _i18_np.zeros(len(state))
    for cell, count in enumerate(a['subcell_count']):
        offset = a['subcell_offset'][cell]
        h = _i18_np.maximum(stage[cell] - a['sorted_subcell_bed_relative_m'][offset:offset + count], 0)
        factor[cell] = _i18_np.sum(h[h > 0] ** (-1 / 3)) / count
    _i18_near(packet['manning_inverse_depth_third_mean'], factor, 'independent canonical Manning integral')
    squared = updated[:, 0] ** 2
    denominator = squared + dt * g * budget['roughness_s_m_third'] ** 2 * _i18_np.hypot(updated[:, 1], updated[:, 2]) * factor
    damping = _i18_np.divide(squared, denominator, out=_i18_np.zeros_like(squared), where=denominator > 0)
    before_drag = updated[:, 1:].copy()
    updated[:, 1:] *= damping[:, None]
    _i18_near(after, updated, 'independent SSPRK2 and canonical drag')
    _i18_near(packet['manning_momentum_change'], updated[:, 1:] - before_drag, 'independent Manning impulse')
    return dict(equations_sampled=True, physical_HLL_verified=True, canonical_Manning_verified=True, CFL_verified=True)

def audit_frame(frame_record, bed_record, snapshot_record, geometry, number):
    frame, metadata, _ = _i18_read_bundle(frame_record)
    bed, bed_metadata, bed_id = _i18_read_bundle(bed_record)
    snapshot, snapshot_metadata, snapshot_id = _i18_read_bundle(snapshot_record)
    if metadata.get('schema') != 'surface-adaptive-canonical-water-fan-v1' or metadata['bed_identity'] != bed_id or metadata['adaptive_snapshot_identity'] != snapshot_id or (metadata['adaptive_geometry_identity'] != geometry['identity_sha256']) or (metadata['state_index'] != number) or (metadata['time_s'] != snapshot_metadata['time_s']) or (not _i18_np.array_equal(bed['H2_m'], geometry['arrays']['canonical_bed_m'])) or (bed_metadata['origin_m_xz'] != geometry['metadata']['origin_m_xz']) or (not _i18_np.array_equal(frame['cell_depth_m'], snapshot['canonical_depth_m'])):
        raise ValueError('adaptive independent frame original bed/snapshot/geometry/time binding mismatch')
    return _i18_audit_fan(bed, frame, 1.0)

def audit_saved(index_record, output, *, physical=True):
    from terrain_pipeline.adaptive_mesh import near as _i18_near
    from terrain_pipeline.adaptive_mesh import load_adaptive_run as _i18_load_adaptive_run
    from terrain_pipeline.common_infra import file_sha256 as _i18_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i18_publish_bytes
    started = _i18_time.monotonic()
    index = _i18_read_json(index_record)
    run_records = {'run': index_record} if index.get('schema') == 'surface-adaptive-run-index-v1' else {name: case['run'] for name, case in index['cases'].items()}
    cases, depths = ({}, {})
    for name, pin in run_records.items():
        print('independent adaptive ' + name, flush=True)
        loaded = _i18_load_adaptive_run(pin['path'], expected_sha256=pin['expected_sha256'])
        samples = []
        if physical:
            for packet in loaded['first_steps']:
                samples.append(audit_step(packet, loaded['geometries'][packet['geometry_identity']], loaded['index']['budget']))
            for epoch in loaded['epochs']:
                geometry = loaded['geometries'][epoch['geometry_identity']]
                interval = epoch['interval']
                _, internal, boundary, _ = physical_rhs(geometry, epoch['state_after'], loaded['forcing']['tailwater_m'][interval], loaded['index']['budget']['gravity_m_s2'], 0.0)
                _i18_near(epoch['internal_q_after_m3_s'], internal[:, 0], 'independent epoch endpoint internal Q')
                _i18_near(epoch['boundary_q_after_m3_s'], boundary[:, 0], 'independent epoch endpoint boundary Q')
        snapshots = loaded['snapshots']
        initial = snapshots[0]['canonical_depth_m']
        depths[name] = _i18_np.asarray([snapshot['canonical_depth_m'] for snapshot in snapshots])
        drift = max((float(abs(snapshot['canonical_depth_m'] - initial).max()) for snapshot in snapshots))
        source_free = bool(_i18_np.all(loaded['forcing']['forcing_m3_s'] == 0))
        cases[name] = dict(geometries_verified=len(loaded['geometries']), snapshots_verified=len(snapshots), epochs_verified=len(loaded['epochs']), refinements_verified=len(loaded['refinements']), first_steps_verified=len(loaded['first_steps']), physical_samples=samples, complete_leaf_mass_momentum_chain_verified=True, original_snapshot_inventory_verified=True, source_free=source_free, maximum_canonical_depth_change_m=drift, source_semantics=loaded['source_semantics'], independent_import_lower_bound_m3=sum((float(_i18_np.maximum(-epoch['boundary_transfer'][:, 0], 0).sum()) for epoch in loaded['epochs'])), gross_boundary_import_m3=float(loaded['states']['ledger'][-1, 1]), actual_substeps=loaded['states']['solver_metadata']['substeps'], maximum_dt_s=loaded['index']['budget']['max_dt_s'], forcing_interval_s=loaded['forcing']['dt_s'], local_forcing_sha256=_i18_hashlib.sha256(loaded['forcing']['forcing_m3_s'].tobytes()).hexdigest(), canonical_initial_inventory_sha256=_i18_hashlib.sha256(initial.tobytes()).hexdigest(), initial_depth=initial.copy(), source_record=loaded['index']['source_record'], snapshot_times_s=[snapshot['time_s'] for snapshot in snapshots], source_free_lake_gate_passed=drift <= 1e-09 if 'lake' in name and source_free else None, uniform_coarse_convergence_claim=False, solver_advanced=False)
        memory = _i18_psutil.Process().memory_info()
        if max(getattr(memory, 'peak_wset', memory.rss), getattr(memory, 'peak_pagefile', memory.vms)) > 1073741824 or _i18_time.monotonic() - started > 1800:
            raise RuntimeError('adaptive independent audit resource exceeded')
    if _i18_file_sha256(index_record['path']) != index_record['expected_sha256']:
        raise ValueError('adaptive observed index changed')
    memory = _i18_psutil.Process().memory_info()
    result = dict(schema='surface-adaptive-independent-audit-v1', index_record=index_record, cases=cases, pure_saved_chain_read=True, equations_sampled=physical, physical_equations_independently_verified=physical, production_adaptive_helpers_called=False, solver_advanced=False, stage_accepted=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False, resource=dict(elapsed_s=_i18_time.monotonic() - started, peak_rss_bytes=int(getattr(memory, 'peak_wset', memory.rss)), peak_private_bytes=int(getattr(memory, 'peak_pagefile', memory.vms))), code_sha256=_i18_file_sha256(_i18_Path(__file__)), limitations=['First-step physical equations are sampled; all geometry epochs and refinement inventory transactions are checked.', 'Adaptive agreement is not a uniform coarse-grid convergence claim; reference comparisons and original strict stage gates require explicit independent evaluation.'])
    if index.get('schema') == 'single-domain-adaptive-stage-index-v1':
        result.update(audit_stage_gates(index, cases, depths))
    for case in cases.values():
        case.pop('initial_depth')
    root = _i18_Path(output).resolve()
    root.relative_to(ROOT)
    root.mkdir(parents=True, exist_ok=False)
    target = root / 'report.json'
    _i18_publish_bytes(target, (_i18_json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    print(_i18_json.dumps(dict(path=str(target), expected_sha256=_i18_file_sha256(target))), flush=True)
    return result

def audit_stage_gates(index, cases, depths):
    from terrain_pipeline.adaptive_mesh import near as _i18_near
    declaration = _i18_read_json(index['predeclared'])
    source = _i18_read_json(index['source_v7_index'])
    source_report = _i18_read_json(index['source_v7_report'])
    if source['report'] != index['source_v7_report'] or declaration['source_v7_index'] != index['source_v7_index'] or source_report['all_predeclared_gates_passed'] is not False or (index.get('uniform_coarse_convergence_claim') is not False):
        raise ValueError('adaptive independent original uniform evidence/claim mismatch')
    gates = declaration['gates']
    required_cases = {'dry-rain-root4', 'zero-source-lake-root4', 'tailwater-baseline-root4', 'tailwater-rise-root1', 'tailwater-rise-root1-half-dt', 'tailwater-rise-root2', 'tailwater-rise-root4'}
    if set(cases) != required_cases or len(index['comparisons']) != 4:
        raise ValueError('adaptive independent complete seven-case stage/four comparisons required')
    if gates['max_saved_depth_difference_m'] != 0.01 or gates['max_relative_surface_volume_difference'] != 0.01 or gates['max_lake_depth_change_m'] != 1e-09:
        raise ValueError('adaptive independent strict original gates changed')
    for name, case in cases.items():
        source_name = index['cases'][name]['source_v7_case']
        if case['source_record'] != source['cases'][source_name]['run'] or case['snapshot_times_s'] != [0.0, 30.0, 60.0, 90.0, 120.0]:
            raise ValueError('adaptive independent original case source or physical timeline mismatch')
        semantics = case['source_semantics']
        if name == 'zero-source-lake-root4':
            if semantics != 'explicit zero-source closed lake correction of prior soil-release case':
                raise ValueError('adaptive independent only static lake may override original forcing')
        elif semantics != 'original saved canonical source/time schedule':
            raise ValueError('adaptive independent nonstatic forcing differs from original four-store source')
    baseline, rise = (cases['tailwater-baseline-root4'], cases['tailwater-rise-root4'])
    if baseline['maximum_dt_s'] != rise['maximum_dt_s'] or baseline['forcing_interval_s'] != rise['forcing_interval_s'] or baseline['local_forcing_sha256'] != rise['local_forcing_sha256']:
        raise ValueError('adaptive controlled tailwater baseline/run forcing or cadence changed')
    _i18_near(baseline['initial_depth'], rise['initial_depth'], 'controlled tailwater common original initial inventory')
    reference_case = source['cases']['tailwater-rise-1m-half-dt']
    reference_run = _i18_read_json(reference_case['run'])
    reference, _, _ = _i18_read_bundle(reference_run['states'])
    times = reference['time_s']
    if not _i18_np.array_equal(times, _i18_np.arange(5) * 30.0):
        raise ValueError('adaptive independent all saved reference times mismatch')
    reference_depth = reference['depth_m']

    def compare(first, second, label):
        if first.shape != second.shape:
            raise ValueError('adaptive independent fullwindow comparison shape mismatch')
        error = float(abs(first - second).max())
        volume = float((abs(first.sum(axis=(1, 2)) - second.sum(axis=(1, 2))) / _i18_np.maximum(second.sum(axis=(1, 2)), 1e-12)).max())
        return dict(label=label, maximum_saved_depth_difference_m=error, maximum_relative_surface_volume_difference=volume, passed=error <= 0.01 and volume <= 0.01)
    comparisons = [compare(depths['tailwater-rise-root1'], depths['tailwater-rise-root1-half-dt'], 'independent root1 temporal')]
    changed = cases['tailwater-rise-root1-half-dt']['actual_substeps'] > cases['tailwater-rise-root1']['actual_substeps']
    comparisons[0].update(actual_temporal_resolution_changed=changed, passed=comparisons[0]['passed'] and changed)
    comparisons += [compare(depths[f'tailwater-rise-root{size}'], reference_depth, f'independent adaptive root{size} vs uniform1m') for size in (1, 2, 4)]
    for calculated, reported in zip(comparisons, index['comparisons']):
        _i18_near(_i18_np.asarray(calculated['maximum_saved_depth_difference_m']), _i18_np.asarray(reported['maximum_saved_depth_difference_m']), 'reported fullwindow depth comparison')
        _i18_near(_i18_np.asarray(calculated['maximum_relative_surface_volume_difference']), _i18_np.asarray(reported['maximum_relative_surface_volume_difference']), 'reported fullwindow volume comparison')
    lake = cases['zero-source-lake-root4']
    if not lake['source_free']:
        raise ValueError('adaptive independent static lake has real saved source')
    response = depths['tailwater-rise-root4'][-1] - depths['tailwater-baseline-root4'][-1]
    imported = cases['tailwater-rise-root4']['independent_import_lower_bound_m3']
    scenarios = dict(zero_source_lake=dict(max_depth_change_m=lake['maximum_canonical_depth_change_m'], passed=lake['maximum_canonical_depth_change_m'] <= 1e-09), controlled_tailwater=dict(max_depth_increase_m=float(response.max()), positive_response_cells=int(_i18_np.sum(response > gates['minimum_tailwater_response_m'])), imported_volume_lower_bound_m3=imported, passed=float(response.max()) > gates['minimum_tailwater_response_m'] and imported > gates['minimum_tailwater_import_m3']))
    western = response[:, :max(1, response.shape[1] // 2)]
    positions = _i18_np.argwhere(response > gates['minimum_tailwater_response_m'])
    scenarios['controlled_tailwater'].update(maximum_west_half_depth_increase_m=float(western.max()), positive_west_half_response_cells=int(_i18_np.sum(western > gates['minimum_tailwater_response_m'])), farthest_response_from_prescribed_east_boundary_m=float((response.shape[1] - 0.5 - positions[:, 1]).max(initial=0)), original_common_forcing_and_initial_inventory_verified=True)
    _i18_near(_i18_np.asarray(scenarios['zero_source_lake']['max_depth_change_m']), _i18_np.asarray(index['scenario_gates']['zero_source_lake']['max_depth_change_m']), 'reported actual zero-source lake drift')
    _i18_near(_i18_np.asarray(scenarios['controlled_tailwater']['max_depth_increase_m']), _i18_np.asarray(index['scenario_gates']['controlled_tailwater']['max_depth_increase_m']), 'reported controlled tailwater response')
    return dict(comparisons=comparisons, scenario_gates=scenarios, all_predeclared_gates_passed=all((item['passed'] for item in comparisons)) and all((item['passed'] for item in scenarios.values())), reference_comparisons_independently_verified=True, controlled_tailwater_independently_verified=True, original_forcing_and_initial_contracts_verified=True, uniform_coarse_convergence_claim=False, source_uniform_coarse_gates_passed=False, reference_is_independent_saved_uniform_1m=True)

def _entry_audit_surface_adaptive():
    parser = _i18_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', required=True, type=_i18_Path)
    parser.add_argument('--index-sha256', required=True)
    parser.add_argument('--output', required=True, type=_i18_Path)
    args = parser.parse_args()
    audit_saved(dict(path=str(args.index.resolve()), expected_sha256=args.index_sha256), args.output)
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    _i19_os.environ.setdefault(name, '1')
_i19_sys.path.insert(0, str(ROOT))

def audit(manifest_record, output):
    from terrain_pipeline.common_infra import file_sha256 as _i19_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i19_publish_bytes
    from terrain_pipeline.single_domain_surface_consumer import load_consumer_manifest as _i19_load_consumer_manifest
    from terrain_pipeline.adaptive_mesh import validate_geometry as _i19_validate_geometry
    started = _i19_time.monotonic()
    context = _i19_load_consumer_manifest(manifest_record['path'], expected_sha256=manifest_record['expected_sha256'])
    manifest = context['manifest']
    if manifest['backend'] != 'adaptive-saved-canonical-fan':
        raise ValueError('independent adaptive fan requires AMR consumer')
    stage = _i19_read_json(manifest['source_index'])
    source = _i19_read_json(stage['source_v7_index'])
    required_cases = {'dry-rain-root4', 'zero-source-lake-root4', 'tailwater-baseline-root4', 'tailwater-rise-root1', 'tailwater-rise-root1-half-dt', 'tailwater-rise-root2', 'tailwater-rise-root4'}
    if stage.get('schema') != 'single-domain-adaptive-stage-index-v1' or set(manifest['scenarios']) != required_cases or set(stage['cases']) != required_cases:
        raise ValueError('independent adaptive fan complete seven-case coverage required')
    artifacts = {item['path']: item for item in manifest['artifacts']}
    root = _i19_Path(manifest_record['path']).resolve().parent

    def copied_pin(name, original=None):
        item = artifacts[name]
        if original is not None and (item['sha256'] != original['expected_sha256'] or item['identity_sha256'] != original['expected_identity']):
            raise ValueError('independent adaptive copied original record mismatch')
        return dict(path=str(root / name), expected_sha256=item['sha256'], expected_identity=item['identity_sha256'])
    cases = {}
    count = 0
    for name, scenario in manifest['scenarios'].items():
        case = stage['cases'][name]
        run = _i19_read_json(case['run'])
        source_case = source['cases'][case['source_v7_case']]
        source_run = _i19_read_json(source_case['run'])
        if run['source_record'] != source_case['run']:
            raise ValueError('independent adaptive original four-store run binding mismatch')
        original_pin = copied_pin(scenario['evidence']['original_rainfall_runoff'], source_run['forcing'])
        original_forcing, _, _ = _i19_read_bundle(original_pin)
        actual_pin = copied_pin(scenario['evidence']['forcing'], run['forcing'])
        actual_forcing, _, _ = _i19_read_bundle(actual_pin)
        override = name == 'zero-source-lake-root4'
        original_item = artifacts[scenario['evidence']['original_rainfall_runoff']]
        provenance = original_item['provenance']
        if original_item['role'] != 'original-rainfall-runoff' or provenance['source_index'] != stage['source_v7_index'] or provenance['source_run'] != source_case['run'] or (provenance['source_artifact'] != source_run['forcing']) or (provenance['used_hydraulic_forcing_zero'] is not override) or (scenario['used_hydraulic_forcing_zero'] is not override):
            raise ValueError('independent adaptive original four-store provenance/override mismatch')
        original_q = original_forcing['local_q_m3_s'].reshape(actual_forcing['forcing_m3_s'].shape)
        if not (_i19_np.all(actual_forcing['forcing_m3_s'] == 0) if override else _i19_np.array_equal(actual_forcing['forcing_m3_s'], original_q)):
            raise ValueError('independent adaptive actual/original hydraulic forcing mismatch')
        bed_pin = copied_pin(scenario['geometry'], case['bed'])
        if len(scenario['frames']) != 5 or len(run['snapshots']) != 5:
            raise ValueError('independent adaptive five original snapshots required')
        frames = []
        for number, frame in enumerate(scenario['frames']):
            snapshot_pin = copied_pin(frame['snapshot'], run['snapshots'][number])
            _, snapshot_metadata, _ = _i19_read_bundle(snapshot_pin)
            key = snapshot_metadata['geometry_identity']
            geometry_pin = copied_pin(frame['adaptive_geometry'], run['geometries'][key])
            arrays, metadata, _ = _i19_read_bundle(geometry_pin)
            geometry = dict(arrays=arrays, metadata=metadata['raw_geometry_metadata'], identity_sha256=metadata['raw_geometry_identity'])
            _i19_validate_geometry(geometry)
            frame_pin = copied_pin(frame['artifact'])
            provenance = artifacts[frame['artifact']]['provenance']
            if provenance['source_run'] != case['run'] or provenance['source_snapshot'] != run['snapshots'][number] or provenance['source_bed'] != case['bed'] or (provenance['source_adaptive_geometry_identity'] != key):
                raise ValueError('independent adaptive frame original provenance mismatch')
            frames.append(audit_frame(frame_pin, bed_pin, snapshot_pin, geometry, number))
            count += 1
        cases[name] = dict(bound_frames_verified=len(frames), frames=frames, original_four_store_forcing_copy_verified=True, used_hydraulic_forcing_zero=override)
        print('independent adaptive fans ' + name, flush=True)
    if _i19_file_sha256(manifest_record['path']) != manifest_record['expected_sha256'] or count != 35:
        raise ValueError('independent adaptive consumer changed or frame coverage incomplete')
    memory = _i19_psutil.Process().memory_info()
    resource = dict(elapsed_s=_i19_time.monotonic() - started, peak_rss_bytes=int(getattr(memory, 'peak_wset', memory.rss)), peak_private_bytes=int(getattr(memory, 'peak_pagefile', memory.vms)))
    if resource['elapsed_s'] > 1800 or max(resource['peak_rss_bytes'], resource['peak_private_bytes']) > 1073741824:
        raise RuntimeError('independent adaptive consumer resource budget exceeded')
    result = dict(schema='surface-adaptive-consumer-independent-audit-v1', source_manifest=manifest_record, source_index=manifest['source_index'], cases=cases, bound_frames_verified=count, all_fan_geometry_gates_passed=True, original_snapshot_bindings_verified=True, resource=resource, original_four_store_forcing_copies_verified=True, original_rainfall_runoff_bindings_verified=True, solver_advanced=False, stage_accepted=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False, code_sha256=_i19_file_sha256(_i19_Path(__file__)))
    output = _i19_Path(output).resolve()
    output.relative_to(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    target = output / 'report.json'
    _i19_publish_bytes(target, (_i19_json.dumps(result, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    print(_i19_json.dumps(dict(path=str(target), expected_sha256=_i19_file_sha256(target))), flush=True)
    return result

def _entry_audit_surface_adaptive_consumer():
    parser = _i19_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=_i19_Path)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--output', required=True, type=_i19_Path)
    args = parser.parse_args()
    audit(dict(path=str(args.manifest.resolve()), expected_sha256=args.manifest_sha256), args.output)

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'run': '_entry_audit_surface_adaptive', 'consumer': '_entry_audit_surface_adaptive_consumer'}
    values = list(sys.argv[1:] if argv is None else argv)
    if len(commands) == 1:
        selected = next(iter(commands))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        option = '--scope'
        if option:
            parser.add_argument(option, choices=tuple(commands), required=True)
            parsed, values = parser.parse_known_args(values)
            selected = getattr(parsed, option[2:].replace('-', '_'))
        else:
            parser.add_argument('command', choices=tuple(commands))
            parsed, values = parser.parse_known_args(values)
            selected = parsed.command
    function = globals()[commands[selected]]
    previous = sys.argv
    try:
        sys.argv = [previous[0]] + values
        return function()
    finally:
        sys.argv = previous
if __name__ == '__main__':
    main()
