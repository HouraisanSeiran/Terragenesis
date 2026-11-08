"""Consolidated audit_hybrid_hydraulics implementations; numeric expressions preserved."""
from __future__ import annotations
import argparse as _i5_argparse
import ast as _i5_ast
import json as _i5_json
import math as _i5_math
from pathlib import Path as _i5_Path
import sys as _i5_sys
import time as _i5_time
import numpy as _i5_np
from shapely.geometry import Polygon as _i5_Polygon
from shapely.geometry import box as _i5_box
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i5_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import checked_path as _i5_checked_path
from tools.td_shared_channel_fine_saved_audit import check_identity as _i5_check_identity
from tools.td_shared_channel_fine_saved_audit import check_memory as _i5_check_memory
from tools.td_shared_channel_fine_saved_audit import digest as _i5_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i5_file_sha256
from tools.td_shared_channel_fine_saved_audit import read as _i5_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i5_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i5_require
import argparse as _i6_argparse
import json as _i6_json
from pathlib import Path as _i6_Path
import sys as _i6_sys
import time as _i6_time
import numpy as _i6_np
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i6_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import check_memory as _i6_check_memory
from tools.td_shared_channel_fine_saved_audit import digest as _i6_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i6_file_sha256
from tools.td_shared_channel_fine_saved_audit import read as _i6_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i6_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i6_require
import argparse as _i7_argparse
import copy as _i7_copy
import json as _i7_json
import math as _i7_math
from pathlib import Path as _i7_Path
import sys as _i7_sys
import time as _i7_time
import numpy as _i7_np
from tools.td_shared_channel_fine_saved_audit import MAX_BYTES as _i7_MAX_BYTES
from tools.td_shared_channel_fine_saved_audit import checked_path as _i7_checked_path
from tools.td_shared_channel_fine_saved_audit import check_memory as _i7_check_memory
from tools.td_shared_channel_fine_saved_audit import digest as _i7_digest
from tools.td_shared_channel_fine_saved_audit import file_sha256 as _i7_file_sha256
from tools.td_shared_channel_fine_saved_audit import read as _i7_read
from tools.td_shared_channel_fine_saved_audit import read_audit as _i7_read_audit
from tools.td_shared_channel_fine_saved_audit import require as _i7_require
CATEGORY = 'C'
ROOT = _i5_Path(__file__).resolve().parents[1]
AUDIT_SCHEMA = 'td-hybrid-river-hydraulics-independent-audit-v1'
LEDGER_COLUMNS = ['source_in_m3', 'outlet_water_out_m3', 'tailwater_water_in_m3', 'source_tracer_out_m3', 'tailwater_tracer_in_m3', 'tailwater_tracer_out_m3']
ARRAY_KEYS = ('water_volume_m3', 'source_tracer_mass_m3', 'tailwater_tracer_mass_m3')
LINK_KEYS = ('paired_link_water_integral_m3', 'paired_link_source_integral_m3', 'paired_link_tailwater_integral_m3')

def check_same_physics(include_bdf=False):
    names = ('physical', 'flows', 'rhs_for', 'guard', 'capacity_for', 'inventory_policy', 'friction_state', 'effective_conveyance', 'validate_transition', 'roof_contact_length')
    signatures = []

    class SolverLabels(_i5_ast.NodeTransformer):

        def visit_Constant(self, node):
            replacements = {'BDF_rhs_trial': 'Radau_rhs_trial', 'reject_entire_BDF_step_and_halve_retry': 'reject_entire_Radau_step_and_halve_retry', 'no_interpolated_inventory_output_saved_times_are_BDF_endpoints': 'no_interpolated_inventory_output_saved_times_are_Radau_endpoints'}
            if isinstance(node.value, str) and node.value in replacements:
                node.value = replacements[node.value]
            return node
    from tools.frozen_hybrid_hydraulics import HydraulicsLegacyReplay as HydraulicsLegacyReplay
    replay = HydraulicsLegacyReplay()
    paths = [replay.source_path(ROOT / ('terrain_pipeline/hybrid_river_hydraulics_' + version + '.py')) for version in (('v5', 'v6', 'v7') if include_bdf else ('v5', 'v6'))]
    paths.append(ROOT / 'legacy-code/refactor-merge-20261105/M2/terrain_pipeline/hybrid_river_hydraulics_radau.py')
    for path in paths:
        tree = _i5_ast.parse(path.read_text(encoding='utf-8'))
        tree = SolverLabels().visit(tree)
        methods = {}
        for name in names:
            found = [node for node in _i5_ast.walk(tree) if isinstance(node, _i5_ast.FunctionDef) and node.name == name]
            _i5_require(len(found) == 1, 'ambiguous shared physics implementation: ' + name)
            methods[name] = _i5_ast.dump(found[0], include_attributes=False)
        signatures.append(methods)
    _i5_require(all((methods == signatures[0] for methods in signatures[1:])), 'numerical revisions do not share frozen physics')

def check_accuracy_policy(index, model):
    expected = {'schema': 'td-hybrid-river-accuracy-policy-v7', 'integration': 'BDF', 'forcing_configuration_pin_unchanged': True, 'parameter_transform': {'base': {'relative_tolerance_divisor': 64, 'absolute_tolerance_divisor': 64, 'max_step_divisor': 4}, 'refined': {'relative_tolerance_divisor': 256, 'absolute_tolerance_divisor': 256, 'max_step_divisor': 8}}, 'unchanged_scope': 'all_other_pinned_Experiment_parameters_initial_geometry_slot_forcing_and_guards', 'comparison_gates_unchanged': {'volume_absolute_tolerance_m3': 0.0001, 'head_absolute_tolerance_m': 0.001, 'volume_relative_tolerance': 0.01, 'paired_and_origin_absolute_tolerance_m3': 0.0001}, 'reused_cases_allowed': False, 'precision_change_not_physical_change': True}
    _i5_require(index['integration'] == model['integration'] == 'BDF' and index['accuracy_policy'] == model['accuracy_policy'] == expected and (index['reused_cases'] == {}) and (set(index['generated_cases']) == set(index['completed_cases'])) and (index['physical_model_identity_sha256'] == model['physical_model_identity_sha256'] == physical_identity(model)), 'undeclared/changed BDF accuracy policy or reused inaccurate cases')

def accuracy_parameters(original, level):
    tolerance_divisor, step_divisor = (64, 4) if level == 'base' else (256, 8)
    return {**original, 'max_step_s': original['max_step_s'] / step_divisor, 'relative_tolerance': original['relative_tolerance'] / tolerance_divisor, 'absolute_tolerance': original['absolute_tolerance'] / tolerance_divisor}

def physical_identity(model):
    fields = ('model_version', 'model_parameters', 'friction_policy', 'inventory_policy', 'forcing_configuration_pin', 'graph_identity_sha256', 'geometry_identity_sha256')
    return _i5_digest({key: model[key] for key in fields})

def check_case_binding(record, index, model, name):
    own_model = _i5_read(record['hydraulic_model_parameters'])
    own_version = record['schema'].rsplit('-', 1)[-1]
    _i5_require(own_model['schema'] == 'td-hybrid-river-hydraulic-model-parameters-' + own_version and record['hydraulic_model_parameters_identity_sha256'] == own_model['identity_sha256'] and (own_model['code_sha256'] == record['code_sha256']) and (record['model_parameters'] == own_model['model_parameters']) and (record['friction_policy'] == own_model['friction_policy']) and (record['model_version'] == own_model['model_version']) and (record['numerical_version'] == own_model['numerical_version']) and all((record['jacobian_policy'][key] == value for key, value in own_model['jacobian_policy'].items())), 'unbound saved case/model/code policy')
    if index['schema'].endswith('v6'):
        _i5_require(physical_identity(own_model) == physical_identity(model) and record['inventory_policy'] == own_model['inventory_policy'], 'changed reused physical model')
        if name == 'pulse-base':
            provenance = index['reused_cases'][name]
            parent = _i5_read(provenance['source_index_pin'])
            _i5_require(parent['schema'] == 'td-hybrid-river-hydraulics-preparation-v5' and parent['status'] in ('failed_partial', 'diagnostic_accepted', 'refused_diagnostic_evidence') and (name in parent['completed_cases']) and (parent['artifacts'][name + '.json'] == index['artifacts'][name + '.json'] == provenance['source_result_pin']) and (parent['hydraulic_model_parameters'] == record['hydraulic_model_parameters'] == provenance['source_model_pin']) and (parent['inputs'] == index['inputs']) and (parent['numerical_version'] == record['numerical_version']) and (parent['model_version'] == own_model['model_version']) and (parent['friction_policy'] == own_model['friction_policy']) and (parent['jacobian_policy'] == own_model['jacobian_policy']) and (len(parent['code_sha256']) == 17) and (parent['code_sha256'] == record['code_sha256'] == provenance['code_sha256']) and (record['schema'] == 'td-hybrid-river-hydraulics-v5') and (provenance['result_unmodified'] is True) and (index['reused_case_work'] == record['work']) and (provenance['physical_model_identity_sha256'] == physical_identity(model)) and all((index['code_sha256'].get(key) == value for key, value in record['code_sha256'].items())), 'unfinished/changed baseline improperly reused')
        else:
            _i5_require(record['schema'] == 'td-hybrid-river-hydraulics-v6' and record['code_sha256'] == index['code_sha256'] and (record['hydraulic_model_parameters'] == index['hydraulic_model_parameters']) and (record['physical_model_identity_sha256'] == index['physical_model_identity_sha256']), 'wrong generated analytic case binding')
    else:
        _i5_require(record['code_sha256'] == index['code_sha256'] and record['hydraulic_model_parameters'] == index['hydraulic_model_parameters'], 'wrong saved friction revision')
        if index['schema'].endswith('v7'):
            _i5_require(record['schema'] == 'td-hybrid-river-hydraulics-v7' and record['integration'] == own_model['integration'] == 'BDF' and (record['accuracy_policy'] == index['accuracy_policy']) and (record['accuracy_level'] == name.rsplit('-', 1)[-1]) and (record['input_parameters_identity_sha256'] == index['input_parameter_identities'][record['scenario']]) and (record['physical_model_identity_sha256'] == physical_identity(model)), 'unbound BDF case accuracy/physical identity')
    for path, sha in record['code_sha256'].items():
        _i5_require(_i5_file_sha256(ROOT / path) == sha, 'case frozen code changed: ' + path)

def section_area(section, head):
    if section['kind'] == 'open_polyline':
        area = 0.0
        points = section['polyline_transverse_elevation_m']
        for first, second in zip(points[:-1], points[1:]):
            width = second[0] - first[0]
            _i5_require(width > 0, 'unordered actual surface section')
            first_depth, second_depth = (head - first[1], head - second[1])
            if min(first_depth, second_depth) >= 0:
                area += width * (first_depth + second_depth) / 2
            elif max(first_depth, second_depth) > 0:
                positive_depth = max(first_depth, second_depth)
                area += width * positive_depth ** 2 / (2 * abs(first_depth - second_depth))
        return area
    _i5_require(section['kind'] == 'closed_polygon', 'unexpected actual section kind')
    points = _i5_np.asarray(section['polygon_transverse_elevation_m'], dtype=float)
    origin = points[0]
    polygon = _i5_Polygon(points - origin)
    _i5_require(polygon.is_valid and polygon.area > 0, 'invalid final VDM polygon')
    floor, crown = (points[:, 1].min(), points[:, 1].max())
    if head <= floor:
        return 0.0
    if head >= crown:
        return polygon.area + section['pressure_slot_width_m'] * (head - crown)
    lower_x, lower_y, upper_x, upper_y = polygon.bounds
    return polygon.intersection(_i5_box(lower_x - 1, lower_y - 1, upper_x + 1, head - origin[1])).area

def array(record, key, shape):
    result = _i5_np.asarray(record[key], dtype=float)
    _i5_require(result.shape == shape and _i5_np.isfinite(result).all(), 'invalid saved array: ' + key)
    return result

def section_friction(cell, head, width):
    section = cell['section']
    closed = section['kind'] == 'closed_polygon'
    points = section['polygon_transverse_elevation_m' if closed else 'polyline_transverse_elevation_m']
    edges = list(zip(points, points[1:] + points[:1])) if closed else list(zip(points[:-1], points[1:]))
    perimeter = 0.0
    floor = min((point[1] for point in points))
    for first, second in edges:
        lower, upper = sorted((first[1], second[1]))
        length = _i5_math.dist(first, second)
        if head <= floor:
            continue
        if head >= upper and (closed or lower < upper or head > upper):
            perimeter += length
        elif head > lower:
            perimeter += length * (head - lower) / (upper - lower)
    roof = 0.0
    effective = perimeter
    if closed:
        crown = max((point[1] for point in points))
        roof = _i5_math.fsum((_i5_math.dist(first, second) for first, second in edges if first[1] == crown and second[1] == crown))
        if width > 0 and head >= crown:
            fraction = min(1.0, (head - crown) / width)
            effective -= roof * (1 - fraction ** 2 * (3 - 2 * fraction))
    else:
        perimeter += max(0.0, head - points[0][1]) + max(0.0, head - points[-1][1])
        effective = perimeter
    area = section_area(section, head)
    _i5_require(area == 0 or (perimeter > 0 and effective > 0), 'nonpositive wet friction perimeter')

    def capacity(value):
        return area * (area / value) ** (2 / 3) / cell['roughness_manning'] if area > 0 else 0.0
    return {'area_m2': area, 'actual_wetted_perimeter_m': perimeter, 'effective_friction_perimeter_m': effective, 'actual_horizontal_roof_length_m': roof, 'actual_geometry_manning_conveyance': capacity(perimeter), 'effective_manning_conveyance': capacity(effective)}

def check_friction_probes(record, geometry, parameters):
    policy = record['friction_policy']
    width = policy['width_m']
    _i5_require(isinstance(width, (int, float)) and _i5_math.isfinite(width) and (0 < width <= 0.05) and (policy['transition_start'] == 'crown') and (policy['transition_end'] == 'crown+width_m') and (policy['actual_perimeter_unchanged'] is True) and (policy['storage_area_unchanged'] is True) and (policy['pressure_slot_width_unchanged'] is True) and (policy['roof_length_source'] == 'sum_actual_polygon_edges_with_both_endpoints_at_crown') and (policy['constitutive_kind'] == 'C1_effective_roof_contact_friction') and (policy['contact_polynomial'] == 'u*u*(3-2*u)_for_0<=u<=1'), 'unknown/undeclared effective roof friction model')
    cells, links = (geometry['hydraulic_cells'], geometry['hydraulic_links'])
    snapshots, probes = (record['saved_section_diagnostics'], record['instantaneous_flux_probes'])
    times = record['times_s']
    _i5_require(len(snapshots) == len(probes) == len(times), 'incomplete actual section/flux probes')
    maximum = 0.0

    def matched(actual, expected):
        nonlocal maximum
        _i5_require(isinstance(actual, (int, float)) and _i5_math.isfinite(actual), 'nonfinite section/flux diagnostic')
        error = abs(actual - expected)
        maximum = max(maximum, error)
        _i5_require(error <= 1e-08 + 1e-10 * abs(expected), 'independent section friction/flux mismatch')

    def discharge(capacity, difference, length):
        return capacity * difference / ((difference ** 2 + 1e-08) ** 0.25 * _i5_math.sqrt(length))
    for ordinal, seconds in enumerate(times):
        snapshot, probe = (snapshots[ordinal], probes[ordinal])
        _i5_require(snapshot['time_s'] == probe['time_s'] == seconds and len(snapshot['cells']) == len(cells) and (len(probe['links']) == len(links)), 'misaligned section/flux probes')
        heads = record['hydraulic_head_m'][ordinal]
        volumes = record['water_volume_m3'][ordinal]
        source = record['source_tracer_mass_m3'][ordinal]
        tailwater = record['tailwater_tracer_mass_m3'][ordinal]
        capacities = []
        for cell_index, (cell, saved) in enumerate(zip(cells, snapshot['cells'])):
            _i5_require(saved['cell_id'] == cell['cell_id'] and saved['kind'] == cell['kind'], 'probe ownership mismatch')
            friction = section_friction(cell, heads[cell_index], width)
            for key, expected in friction.items():
                matched(saved[key], expected)
            for key, expected in (('head_m', heads[cell_index]), ('volume_m3', volumes[cell_index]), ('source_tracer_mass_m3', source[cell_index]), ('tailwater_tracer_mass_m3', tailwater[cell_index])):
                matched(saved[key], expected)
            if 'untraced_water_volume_m3' in record:
                matched(saved['untraced_water_volume_m3'], record['untraced_water_volume_m3'][ordinal][cell_index])
            capacities.append(friction['effective_manning_conveyance'])
        matched(snapshot['total_water_m3'], sum(volumes))
        matched(probe['source_q_m3_s'], parameters['pulse_q_m3_s'] if seconds < parameters['pulse_duration_s'] else 0.0)
        for link_index, (link, saved) in enumerate(zip(links, probe['links'])):
            flow = discharge(min(capacities[link_index:link_index + 2]), heads[link_index] - heads[link_index + 1], link['length_m'])
            donor = link_index if flow >= 0 else link_index + 1
            flow *= volumes[donor] / (volumes[donor] + 1e-06)
            _i5_require(saved['link_id'] == link['link_id'] and saved['donor_cell_id'] == cells[donor]['cell_id'], 'flux donor mismatch')
            matched(saved['water_q_m3_s'], flow)
            matched(saved['source_tracer_q_m3_s'], flow * source[donor] / volumes[donor])
            matched(saved['tailwater_tracer_q_m3_s'], flow * tailwater[donor] / volumes[donor])
        tail_capacity = section_friction(cells[-1], parameters['tailwater_head_m'], width)['effective_manning_conveyance']
        flow = discharge(min(capacities[-1], tail_capacity), heads[-1] - parameters['tailwater_head_m'], cells[-1]['length_m'] / 2)
        if flow >= 0:
            flow *= volumes[-1] / (volumes[-1] + 1e-06)
            source_flow, tailwater_flow = (flow * source[-1] / volumes[-1], flow * tailwater[-1] / volumes[-1])
        else:
            source_flow, tailwater_flow = (0.0, flow)
        matched(probe['outlet_signed_water_q_m3_s'], flow)
        matched(probe['outlet_signed_source_tracer_q_m3_s'], source_flow)
        matched(probe['outlet_signed_tailwater_tracer_q_m3_s'], tailwater_flow)
    return {'effective_roof_friction_independently_verified': True, 'transition_width_m': width, 'max_section_and_flux_diagnostic_difference': maximum}

def check_three_origins(record, volumes, source, tailwater, initial, ledgers):
    untraced = array(record, 'untraced_water_volume_m3', volumes.shape)
    _i5_require(_i5_np.all(untraced >= 0) and _i5_np.max(abs(untraced[0] - initial)) <= 1e-09, 'invalid explicit initial-origin inventory')
    composition = float(_i5_np.max(abs(volumes - (untraced + source + tailwater))))
    _i5_require(composition <= 1e-10, 'water is not the sum of its three explicit origins')
    integral = array(record, 'paired_link_untraced_integral_m3', (len(volumes), volumes.shape[1] - 1))
    outgoing = array(record, 'outlet_untraced_out_m3', (len(volumes),))
    _i5_require(_i5_np.max(abs(integral[0])) == 0 and outgoing[0] == 0 and _i5_np.all(outgoing >= -1e-09) and _i5_np.all(_i5_np.diff(outgoing) >= -1e-09), 'invalid initial-origin cumulative exchange')
    expected = _i5_np.tile(initial, (len(volumes), 1))
    expected[:, :-1] -= integral
    expected[:, 1:] += integral
    expected[:, -1] -= outgoing
    residual = float(_i5_np.max(abs(untraced - expected)))
    _i5_require(residual <= 0.0001, 'per-cell initial-origin conservation failed')
    link_error = float(_i5_np.max(abs(_i5_np.asarray(record['paired_link_water_integral_m3']) - integral - record['paired_link_source_integral_m3'] - record['paired_link_tailwater_integral_m3'])))
    _i5_require(link_error <= 0.0001 and _i5_np.max(abs(ledgers[:, 1] - outgoing - ledgers[:, 3] - ledgers[:, 5])) <= 0.0001, 'three origins do not exhaust the water exchange ledger')
    return {'three_origin_inventory_verified': True, 'max_three_origin_composition_difference_m3': composition, 'max_per_cell_untraced_residual_m3': residual, 'max_three_origin_link_difference_m3': link_error, 'initial_origin_remaining_m3': float(untraced[-1].sum()), 'initial_origin_exported_m3': float(outgoing[-1])}

def check_result(record, geometry, parameters):
    _i5_check_identity(record)
    _i5_require(record['status'] == 'diagnostic_completed', 'partial/refused case cannot be accepted')
    _i5_require(record['parameters'] == parameters and record['parameters_identity_sha256'] == _i5_digest(parameters), 'saved experiment differs from explicit configuration')
    cells, links = (geometry['hydraulic_cells'], geometry['hydraulic_links'])
    count, times = (len(cells), _i5_np.asarray(record['times_s'], dtype=float))
    _i5_require(3 <= count <= 64 and len(links) == count - 1, 'invalid bounded physical chain')
    _i5_require(record['cell_ids'] == [cell['cell_id'] for cell in cells] and record['link_ids'] == [link['link_id'] for link in links], 'actual geometry ownership mismatch')
    _i5_require(times.tolist() == parameters['saved_times_s'] and 2 <= len(times) <= 4096 and _i5_np.isfinite(times).all() and (times[0] == 0) and (times[-1] == parameters['duration_s']) and _i5_np.all(_i5_np.diff(times) > 0), 'physical saved-time mismatch')
    shape = (len(times), count)
    volumes, source, tailwater = [array(record, key, shape) for key in ARRAY_KEYS]
    heads = array(record, 'hydraulic_head_m', shape)
    initial = array(record, 'initial_untraced_water_m3', (count,))
    configured_heads = _i5_np.asarray(parameters['initial_heads_m'], dtype=float)
    _i5_require(configured_heads.shape == (count,) and _i5_np.isfinite(configured_heads).all() and (_i5_np.max(abs(heads[0] - configured_heads)) <= 1e-09), 'initial saved head differs from explicit configuration')
    configured_volumes = _i5_np.asarray([section_area(cell['section'], head) * cell['length_m'] for cell, head in zip(cells, configured_heads)])
    _i5_require(_i5_np.max(abs(initial - configured_volumes)) <= 1e-07, 'initial untraced inventory differs from actual configured geometry')
    _i5_require(_i5_np.all(volumes > 0) and _i5_np.all(source >= 0) and _i5_np.all(tailwater >= 0) and _i5_np.all(source + tailwater <= volumes + 1e-07), 'positivity/tracer composition mismatch')
    _i5_require(_i5_np.max(abs(volumes[0] - initial)) <= 1e-09 and _i5_np.max(abs(source[0])) == 0 and (_i5_np.max(abs(tailwater[0])) == 0), 'initial storage/tracer origin mismatch')
    ledgers = array(record, 'boundary_ledger_m3', (len(times), 6))
    _i5_require(record['ledger_columns'] == LEDGER_COLUMNS and _i5_np.max(abs(ledgers[0])) == 0 and _i5_np.all(ledgers >= -1e-09) and _i5_np.all(_i5_np.diff(ledgers, axis=0) >= -1e-09), 'invalid cumulative boundary ledger')
    link_integrals = [array(record, key, (len(times), count - 1)) for key in LINK_KEYS]
    _i5_require(all((_i5_np.max(abs(integral[0])) == 0 for integral in link_integrals)), 'nonzero initial internal exchange')
    _i5_require(_i5_np.max(abs(ledgers[:, 2] - ledgers[:, 4])) <= 1e-09, 'tailwater inlet attribution mismatch')
    expected_source = _i5_np.minimum(times, parameters['pulse_duration_s']) * parameters['pulse_q_m3_s']
    _i5_require(_i5_np.max(abs(ledgers[:, 0] - expected_source)) <= 1e-06, 'duplicate/missing prescribed pulse source')
    tolerance = 0.0001
    residuals = []
    for stored, initial_storage, integral, incoming, outgoing in ((volumes, initial, link_integrals[0], ledgers[:, 0], ledgers[:, 1] - ledgers[:, 2]), (source, _i5_np.zeros(count), link_integrals[1], ledgers[:, 0], ledgers[:, 3]), (tailwater, _i5_np.zeros(count), link_integrals[2], _i5_np.zeros(len(times)), ledgers[:, 5] - ledgers[:, 4])):
        expected = _i5_np.tile(initial_storage, (len(times), 1))
        expected[:, 0] += incoming
        expected[:, -1] -= outgoing
        expected[:, :-1] -= integral
        expected[:, 1:] += integral
        residuals.append(float(_i5_np.max(abs(stored - expected))))
    _i5_require(max(residuals) <= tolerance, 'per-cell paired water/tracer conservation failed')
    area_error = 0.0
    pressure_count = 0
    compliance_volume = _i5_np.zeros(len(times))
    max_pressure_excess = 0.0
    max_engineered_bank_excess = 0.0
    overbank_count = 0
    for ordinal, cell in enumerate(cells):
        _i5_require(cell['length_m'] > 0, 'invalid actual storage length')
        section = cell['section']
        for row, head in enumerate(heads[:, ordinal]):
            area_error = max(area_error, abs(section_area(section, head) * cell['length_m'] - volumes[row, ordinal]))
            closed = section['kind'] == 'closed_polygon'
            crown = max((point[1] for point in section['polygon_transverse_elevation_m'])) if closed else _i5_math.inf
            pressurized = closed and head > crown
            if closed:
                excess = max(0.0, head - crown)
                max_pressure_excess = max(max_pressure_excess, excess)
                compliance_volume[row] += section['pressure_slot_width_m'] * excess * cell['length_m']
            else:
                points = section['polyline_transverse_elevation_m']
                bank = min(points[0][1], points[-1][1])
                bank_excess = max(0.0, head - bank)
                max_engineered_bank_excess = max(max_engineered_bank_excess, bank_excess)
                overbank_count += int(bank_excess > 0)
            actual_stage = record['open_channel_stage_m'][row][ordinal]
            actual_pressure = record['pressurized_head_m'][row][ordinal]
            _i5_require((actual_stage is None) == pressurized and (actual_pressure is not None) == pressurized, 'pressure head mislabeled as open water surface')
            value = actual_pressure if pressurized else actual_stage
            _i5_require(abs(value - head) <= 1e-09, 'stage/head value mismatch')
            pressure_count += int(pressurized)
    _i5_require(area_error <= 1e-07, 'saved inventory does not match actual VDM/open-section geometry')
    threshold = parameters['source_arrival_threshold_m3']
    arrival_indices = _i5_np.flatnonzero(source[:, -1] >= threshold)
    arrival_time = float(times[arrival_indices[0]]) if len(arrival_indices) else None
    sink_index = next((ordinal for ordinal, link in enumerate(links) if link['kind'] == 'sink_exchange'))
    reached_outlet = bool(ledgers[-1, 3] >= threshold)
    reverse_sink = bool(-link_integrals[0][-1, sink_index] > threshold and tailwater[-1, 0] >= threshold)
    _i5_require(record['source_arrival_time_s'] == arrival_time and record['source_reached_engineered_outlet'] == reached_outlet and (record['reverse_reached_sink'] == reverse_sink), 'source/return arrival claim mismatch')
    _i5_require(record['boundary_scope'] == 'positively_wet_prescribed_tailwater_only_no_dry_free_outfall', 'unsupported hydraulic boundary scope')
    for flag in ('natural_outlet_certified', 'full_network_verified', 'finite_speed_front_verified', 'three_dimensional_flow_solved'):
        _i5_require(record[flag] is False, 'unjustified promotion: ' + flag)
    for segment in record['integration_segments']:
        _i5_require(0 < segment['max_adaptive_step_s'] <= parameters['max_step_s'] + 1e-09 and segment['accepted_steps'] > 0, 'saved integrator step contract mismatch')
    work = record['work']
    jacobian_count = work.get('jacobian_evaluations', 0)
    friction_report = {}
    if record.get('numerical_version'):
        policy = record['jacobian_policy']
        _i5_require(policy['ledger_feedback_columns'] == 'exact_zero' and record['jacobian_policy']['scipy_adaptive_difference_factor_used'] is False and (work['jacobian_rhs_evaluations'] == (0 if record['schema'].endswith(('v6', 'v7')) else jacobian_count * (count + 1))), 'explicit Jacobian policy/work mismatch')
        if record['schema'] in ('td-hybrid-river-hydraulics-v4', 'td-hybrid-river-hydraulics-v5', 'td-hybrid-river-hydraulics-v6', 'td-hybrid-river-hydraulics-v7'):
            version = record['schema'].rsplit('-', 1)[-1]
            width = record['friction_policy']['width_m']
            cap = min(1e-06, record['model_parameters']['head_regularization_m'] * 0.01, width * 0.01)
            numerical = {'v4': 'head_bounded_log_difference_Radau_step_diagnostics-v4', 'v5': 'three_origin_direct_inventory_Radau_positivity_rejection-v5', 'v6': 'three_origin_analytic_native_chain_Radau-v6', 'v7': 'three_origin_analytic_native_chain_BDF_precision-v7'}[version]
            _i5_require(record['numerical_version'] == numerical and record['model_version'] == 'explicit_roof_friction_contact_transition-' + ('v5' if version in ('v6', 'v7') else version), 'unknown instrumented numerical/physical version')
            if version not in ('v6', 'v7'):
                _i5_require(policy['max_head_step_m'] == cap and policy['nominal_head_ceiling_m'] == 1e-06 and (policy['head_step_target_fraction_of_cap'] == 0.5) and (policy['head_step_fraction_of_friction_transition'] == 0.01) and (policy['head_step_float_margin'] == '16_ulp_of_base_head') and (policy['head_cap_rule'] == 'min(nominal_head_ceiling_m,head_regularization_m*0.01,width_m*0.01_if_positive)') and (policy['observed_max_head_step_m'] == work['jacobian_max_observed_head_step_m']) and (0 <= work['jacobian_max_observed_head_step_m'] <= cap + 16 * max((_i5_math.ulp(float(head)) for head in heads.ravel()))), 'head-bounded Jacobian policy/work mismatch')
            if version == 'v4':
                _i5_require(policy['log_volume_nominal_absolute_step'] == 1e-06 and policy['tracer_columns'] == 'analytic_donor_transport' and (0 < work['jacobian_min_log_step'] <= work['jacobian_max_log_step'] <= 1e-06 + 1e-14), 'log-volume Jacobian policy mismatch')
            elif version == 'v5':
                _i5_require(policy['total_inventory_nominal_relative_step'] == 1e-06 and policy['tracer_columns'] == 'all_three_origin_columns_share_total_inventory_feedback_plus_analytic_composition' and (policy['step_units'] == 'm3_total_inventory_constant_composition_forward_difference_bounded_by_head') and (0 < work['jacobian_min_volume_step_m3'] <= work['jacobian_max_volume_step_m3']), 'three-origin Jacobian policy mismatch')
            else:
                _i5_require(policy['method'] == 'native_piecewise_section_and_signed_Manning_full_chain_analytic' and policy['inventory_columns'] == 'all_three_origins_share_dV_dM_equal_one_plus_exact_donor_composition' and (policy['section_breakpoint_branch'] == 'right_height_band') and (policy['min_capacity_tie_branch'] == 'left_or_cell_at_boundary') and (policy['zero_signed_flow_donor_branch'] == 'left_or_cell_outlet') and (policy['jacobian_rhs_evaluations_per_call'] == 0) and (policy['jacobian_link_evaluations_per_call'] == 2 * count) and (work['jacobian_link_evaluations'] == 2 * count * jacobian_count) and (work['jacobian_flow_evaluations'] == count * jacobian_count) and (work['jacobian_link_derivative_evaluations'] == count * jacobian_count) and (work['jacobian_native_section_derivatives'] == count * jacobian_count) and (work['jacobian_section_fallback_evaluations'] == 0), 'unknown/miscounted analytic actual-section Jacobian')
            progress = record['execution_progress']
            _i5_require(progress['physical_event_complete'] is True and progress['diagnostic_stop_s'] is None and (progress['last_accepted_physical_time_s'] == parameters['duration_s']) and (progress['triggered_guard'] is None) and (progress['accepted_steps'] == sum((segment['accepted_steps'] for segment in record['integration_segments']))) and (progress['work']['rhs_evaluations'] == work['rhs_evaluations']), 'partial/guarded run masquerading as complete event')
            friction_report = check_friction_probes(record, geometry, parameters)
            if version in ('v5', 'v6', 'v7'):
                friction_report.update(check_three_origins(record, volumes, source, tailwater, initial, ledgers))
                inventory = record['inventory_policy']
                solver = 'BDF' if version == 'v7' else 'Radau'
                _i5_require(inventory['origins'] == ['untraced', 'source', 'tailwater'] and inventory['water_definition'] == 'sum_three_origin_inventories' and (inventory['state_units'] == 'm3') and (inventory['negative_inventory_action'] == 'reject_entire_' + solver + '_step_and_halve_retry') and (inventory['output_clamp'] is False) and (inventory['posthoc_normalization'] is False) and (inventory['positivity_tolerance_m3'] == 0) and (inventory['initial_origin'] == 'untraced') and (inventory['pulse_origin'] == 'source') and (inventory['reverse_boundary_origin'] == 'tailwater') and (inventory['retry_budget'] == 'one_original_event_work_wall_RSS_budget_never_reset') and (inventory['dense_inventory_check'] == 'no_interpolated_inventory_output_saved_times_are_' + solver + '_endpoints'), 'unknown/nonconservative three-origin policy')
                witness = record['dense_positivity_witness']
                _i5_require(witness['policy'] == 'no_dense_inventory_output_saved_times_are_' + solver + '_endpoints' and witness['interpolated_inventory_samples'] == 0 and (witness['accepted_steps'] == progress['accepted_steps']) and (witness['negative_inventory_tolerance_m3'] == 0), 'unsupported dense positivity claim')
                segments = record['integration_segments']
                expected_breaks = sorted(set(times.tolist() + [parameters['pulse_duration_s']]))
                _i5_require([segment['start_s'] for segment in segments] == expected_breaks[:-1] and [segment['end_s'] for segment in segments] == expected_breaks[1:] and (work['observation_segment_initializations'] == len(segments)) and (work[solver.lower() + '_constructor_attempts'] == len(segments) + work['solver_reinitializations']) and (work['solver_reinitializations'] == work['positivity_rejected_steps'] + work['constructor_nonpositive_retries']) and (work['accepted_endpoint_inventory_checks'] >= progress['accepted_steps']), 'hidden reset or miscounted endpoint/positivity retries')
                if version == 'v7':
                    orders = progress['accepted_BDF_order_after_step_counts']
                    _i5_require(record['integration'] == progress['integration'] == 'BDF' and set(orders) <= {'1', '2', '3', '4', '5'} and all((isinstance(value, int) and value >= 0 for value in orders.values())) and (sum(orders.values()) == progress['accepted_steps']), 'wrong BDF integrator/order evidence')
            _i5_require(work['diagnostic_flux_link_evaluations'] == len(times) * count, 'saved flux-probe work mismatch')
        else:
            _i5_require(record['numerical_version'] == 'fixed_log_volume_difference_analytic_tracer_jacobian-v3' and policy['log_volume_absolute_step'] == 1e-06, 'unknown numerical revision')
    _i5_require(work['rhs_evaluations'] <= parameters['max_rhs_evaluations'] and work['link_evaluations'] == (work['rhs_evaluations'] + (2 if record['schema'].endswith(('v6', 'v7')) else 1) * jacobian_count) * count + work.get('diagnostic_flux_link_evaluations', 0) and (work['link_evaluations'] <= parameters['max_link_evaluations']) and (work['actual_peak_rss_bytes'] <= 1024 ** 3) and (work['wall_seconds'] <= parameters['max_wall_seconds']) and (work['old_hll_face_work'] == 0) and (work['old_hll_face_budget_remaining_unchanged'] == 2949448968), 'saved resource/work contract failed')
    return {**friction_report, 'max_per_cell_water_residual_m3': residuals[0], 'max_per_cell_source_residual_m3': residuals[1], 'max_per_cell_tailwater_residual_m3': residuals[2], 'conservation_tolerance_m3': tolerance, 'max_actual_section_volume_difference_m3': area_error, 'pressurized_saved_cell_count': pressure_count, 'max_pressure_above_actual_crown_m': max_pressure_excess, 'max_engineered_stage_above_section_bank_m': max_engineered_bank_excess, 'overbank_saved_cell_count': overbank_count, 'pressure_slot_compliance_volume_m3': compliance_volume.tolist(), 'max_pressure_slot_compliance_volume_m3': float(compliance_volume.max()), 'initial_untraced_water_m3': float(initial.sum()), 'source_in_m3': float(ledgers[-1, 0]), 'source_arrival_time_s': arrival_time, 'source_outlet_m3': float(ledgers[-1, 3]), 'source_export_fraction': float(ledgers[-1, 3] / ledgers[-1, 0]) if ledgers[-1, 0] else None, 'outlet_water_out_m3': float(ledgers[-1, 1]), 'tailwater_water_in_m3': float(ledgers[-1, 2]), 'tailwater_arrived_first_surface_m3': float(tailwater[-1, 0]), 'source_reached_engineered_outlet': reached_outlet, 'reverse_reached_sink': reverse_sink}

def compare_saved(base, refined):
    _i5_require(base['cell_ids'] == refined['cell_ids'] and base['times_s'] == refined['times_s'], 'unaligned refinement')
    head_error = float(_i5_np.max(abs(_i5_np.asarray(base['hydraulic_head_m']) - refined['hydraulic_head_m'])))
    volume_error = float(_i5_np.max(abs(_i5_np.asarray(base['water_volume_m3']) - refined['water_volume_m3'])))
    relative_error = float(_i5_np.max(abs(_i5_np.asarray(base['water_volume_m3']) - refined['water_volume_m3']) / refined['water_volume_m3']))
    tracer_error = max((float(_i5_np.max(abs(_i5_np.asarray(base[key]) - refined[key]))) for key in ARRAY_KEYS[1:] + ('boundary_ledger_m3',)))
    link_l1 = {}
    link_absolute = {}
    extra_links = ('paired_link_untraced_integral_m3',) if 'untraced_water_volume_m3' in base else ()
    for key in LINK_KEYS + extra_links:
        first, second = (_i5_np.asarray(base[key]), _i5_np.asarray(refined[key]))
        maximum = float(_i5_np.max(abs(first - second)))
        absolute = float(_i5_np.sum(abs(first - second)))
        denominator = float(_i5_np.sum(abs(second)))
        _i5_require(maximum <= 0.0001 and absolute <= 0.0001 + 0.01 * denominator, 'paired link refinement failed: ' + key)
        link_absolute[key] = maximum
        link_l1[key] = absolute / denominator if denominator else None
    _i5_require(head_error <= 0.001 and volume_error <= 0.0001 and (relative_error <= 0.01) and (tracer_error <= 0.0001), 'saved 1mm/1percent refinement failed')
    if extra_links:
        _i5_require(max((float(_i5_np.max(abs(_i5_np.asarray(base[key]) - refined[key]))) for key in ('untraced_water_volume_m3', 'outlet_untraced_out_m3'))) <= 0.0001, 'explicit initial-origin refinement failed')
    return {'max_head_difference_m': head_error, 'max_volume_difference_m3': volume_error, 'max_relative_volume_difference': relative_error, 'max_tracer_ledger_difference_m3': tracer_error, 'paired_link_relative_l1': link_l1, 'paired_link_max_absolute_difference_m3': link_absolute}

def audit(index_pin):
    index = _i5_read(index_pin)
    inputs = index['inputs']
    graph = _i5_read(inputs['graph'])
    geometry = _i5_read(inputs['geometry'])
    geometry_audit = _i5_read_audit(inputs['geometry_audit'])
    configuration = _i5_read(inputs['experiments'])
    _i5_require(index['schema'] in ('td-hybrid-river-hydraulics-preparation-v1', 'td-hybrid-river-hydraulics-preparation-v2', 'td-hybrid-river-hydraulics-preparation-v3', 'td-hybrid-river-hydraulics-preparation-v4', 'td-hybrid-river-hydraulics-preparation-v5', 'td-hybrid-river-hydraulics-preparation-v6', 'td-hybrid-river-hydraulics-preparation-v7'), 'wrong saved hydraulics schema')
    _i5_require(index['status'] == 'diagnostic_accepted' and set(index['artifacts']) == {'pulse-base.json', 'pulse-refined.json', 'reverse_tailwater-base.json', 'reverse_tailwater-refined.json'}, 'unfinished or refused engineering events cannot be accepted')
    if index['schema'] != 'td-hybrid-river-hydraulics-preparation-v1':
        _i5_require(set(index['completed_cases']) == {'pulse-base', 'pulse-refined', 'reverse_tailwater-base', 'reverse_tailwater-refined'} and len(index['completed_cases']) == 4 and (index['section_adapter_schema'] == 'td-hybrid-river-fast-sections-v2'), 'incomplete/unknown optimized-section checkpoint')
    if index['schema'].endswith('v3'):
        _i5_require(index['numerical_version'] == 'fixed_log_volume_difference_analytic_tracer_jacobian-v3' and len(index['code_sha256']) == 11, 'unknown explicit-Jacobian solver revision')
    if index['schema'].endswith(('v4', 'v5', 'v6', 'v7')):
        version = index['schema'].rsplit('-', 1)[-1]
        numerical = {'v4': 'head_bounded_log_difference_Radau_step_diagnostics-v4', 'v5': 'three_origin_direct_inventory_Radau_positivity_rejection-v5', 'v6': 'three_origin_analytic_native_chain_Radau-v6', 'v7': 'three_origin_analytic_native_chain_BDF_precision-v7'}[version]
        _i5_require(index['numerical_version'] == numerical and len(index['code_sha256']) == {'v4': 14, 'v5': 17, 'v6': 20, 'v7': 23}[version], 'unknown instrumented solver revision')
        hydraulic_model = _i5_read(index['hydraulic_model_parameters'])
        _i5_require(index['diagnostic_stop_s'] is None and (not index['diagnostic_artifacts']) and (hydraulic_model['schema'] == 'td-hybrid-river-hydraulic-model-parameters-' + version) and (hydraulic_model['graph_identity_sha256'] == graph['identity_sha256']) and (hydraulic_model['geometry_identity_sha256'] == geometry['identity_sha256']) and (hydraulic_model['forcing_configuration_pin'] == inputs['experiments']) and (hydraulic_model['model_version'] == index['model_version'] == 'explicit_roof_friction_contact_transition-' + ('v5' if version in ('v6', 'v7') else version)) and (hydraulic_model['numerical_version'] == index['numerical_version']) and (hydraulic_model['friction_policy'] == index['friction_policy']) and (hydraulic_model['jacobian_policy'] == index['jacobian_policy']), 'unbound/partial/changed declared hydraulic model')
        _i5_require(hydraulic_model['code_sha256'] == index['code_sha256'], 'model/code binding mismatch')
        if version in ('v5', 'v6', 'v7'):
            resource = index['resource']
            solver = 'BDF' if version == 'v7' else 'Radau'
            _i5_require(resource['whole_event_not_split_or_restarted'] is False and resource['one_complete_forcing_event_budget_no_work_or_wall_reset'] is True and (resource['observation_times_reinitialize_' + solver] is True) and (resource['negative_inventory_rollback_reinitializes_' + solver + '_with_same_event_budget'] is True), 'hidden observation segmentation/work reset')
        if version == 'v7':
            check_same_physics(include_bdf=True)
            check_accuracy_policy(index, hydraulic_model)
        if version == 'v6':
            check_same_physics()
            _i5_require(set(index['reused_cases']) == {'pulse-base'} and set(index['generated_cases']) == {'pulse-refined', 'reverse_tailwater-base', 'reverse_tailwater-refined'} and (index['physical_model_identity_sha256'] == hydraulic_model['physical_model_identity_sha256'] == physical_identity(hydraulic_model)) and (index['reuse_contract']['reused_result_rewritten'] is False) and (index['reuse_contract']['reused_work_not_counted_as_new'] is True), 'invalid complete-case reuse/physical identity')
    _i5_require(geometry_audit['status'] == 'passed' and (not geometry_audit.get('errors')) and (geometry_audit['geometry_sha256'] == inputs['geometry']['sha256']) and geometry_audit['actual_hydraulic_sections_verified'] and geometry_audit['actual_portal_connections_verified'], 'unverified actual geometry input')
    for record in (index, geometry, configuration):
        _i5_require(record['graph_identity_sha256'] == graph['identity_sha256'], 'parent graph mismatch')
    _i5_require(index['geometry_identity_sha256'] == geometry['identity_sha256'] and configuration['geometry_identity_sha256'] == geometry['identity_sha256'], 'parent geometry mismatch')
    for pin in graph['inputs'].values():
        _i5_checked_path(pin)
    for pin in geometry['inputs'].values():
        _i5_checked_path(pin)
    for parent in (geometry, geometry_audit):
        for field in ('code_sha256', 'audit_code_sha256', 'readonly_dependency_code_sha256'):
            for name, sha in parent.get(field, {}).items():
                _i5_require(_i5_file_sha256(ROOT / name) == sha, 'frozen geometry/audit dependency changed: ' + name)
    for name, sha in index['code_sha256'].items():
        _i5_require(_i5_file_sha256(ROOT / name) == sha, 'frozen solver code changed: ' + name)
    scenarios = {row['scenario']: row for row in configuration['scenarios']}
    _i5_require(set(scenarios) == {'pulse', 'reverse_tailwater'}, 'wrong engineering scenarios')
    reports = {}
    new_rhs = 0
    new_links = 0
    for scenario, parameters in scenarios.items():
        base = _i5_read(index['artifacts'][scenario + '-base.json'])
        refined = _i5_read(index['artifacts'][scenario + '-refined.json'])
        for record in (base, refined):
            _i5_require(record['inputs'] == inputs and record['graph_identity_sha256'] == graph['identity_sha256'] and (record['geometry_identity_sha256'] == geometry['identity_sha256']), 'result/input binding mismatch')
            _i5_require(record['model_parameters'] == {'head_regularization_m': 0.0001, 'donor_regularization_m3': 1e-06}, 'hidden hydraulic regularization change')
            if index['schema'] not in ('td-hybrid-river-hydraulics-preparation-v1', 'td-hybrid-river-hydraulics-preparation-v6'):
                _i5_require(record['code_sha256'] == index['code_sha256'] and record['section_adapter_schema'] == index['section_adapter_schema'], 'optimized-section result code binding mismatch')
            if index['schema'].endswith('v3'):
                _i5_require(record['schema'] == 'td-hybrid-river-hydraulics-v3' and record['numerical_version'] == index['numerical_version'], 'wrong saved Jacobian revision')
            if index['schema'].endswith(('v4', 'v5', 'v6', 'v7')):
                case_name = scenario + ('-base' if record is base else '-refined')
                check_case_binding(record, index, hydraulic_model, case_name)
                if version == 'v7' or (version == 'v6' and case_name != 'pulse-base'):
                    new_rhs += record['work']['rhs_evaluations']
                    new_links += record['work']['link_evaluations']
                _i5_require(record['section_adapter_schema'] == index['section_adapter_schema'], 'changed actual section adapter')
                if version in ('v5', 'v6', 'v7'):
                    _i5_require(record['inventory_policy'] == hydraulic_model['inventory_policy'], 'unbound inventory model')
        if index['schema'].endswith(('v4', 'v5', 'v6', 'v7')):
            _i5_require(base['friction_policy'] == refined['friction_policy'], 'refinement changed constitutive physics')
        refined_parameters = {**parameters, 'max_step_s': parameters['max_step_s'] / 2, 'relative_tolerance': parameters['relative_tolerance'] / 4, 'absolute_tolerance': parameters['absolute_tolerance'] / 4}
        if index['schema'].endswith('v7'):
            _i5_require(index['input_parameter_identities'][scenario] == _i5_digest(parameters), 'BDF accuracy transform changed original event identity')
            refined_parameters = accuracy_parameters(parameters, 'refined')
            parameters = accuracy_parameters(parameters, 'base')
        base_report = check_result(base, geometry, parameters)
        refined_report = check_result(refined, geometry, refined_parameters)
        refinement = compare_saved(base, refined)
        required = 'source_reached_engineered_outlet' if scenario == 'pulse' else 'reverse_reached_sink'
        _i5_require(base_report[required] and refined_report[required], 'missing actual arrival evidence: ' + scenario)
        meaningful_key = 'source_outlet_m3' if scenario == 'pulse' else 'tailwater_arrived_first_surface_m3'
        meaningful_minimum = max(1.0, base_report['source_in_m3'] * 0.001) if scenario == 'pulse' else 1.0
        _i5_require(base_report[meaningful_key] >= meaningful_minimum and refined_report[meaningful_key] >= meaningful_minimum, 'threshold arrival is insufficient meaningful transported volume: ' + scenario)
        for record, report in ((base, base_report), (refined, refined_report)):
            times = _i5_np.asarray(record['times_s'])
            ledgers = _i5_np.asarray(record['boundary_ledger_m3'])
            late_index = int(_i5_np.searchsorted(times, times[-1] - 100, side='left'))
            report['late_100s_source_export_m3'] = float(ledgers[-1, 3] - ledgers[late_index, 3])
            if scenario == 'pulse':
                _i5_require(report['late_100s_source_export_m3'] >= 0.5, 'no meaningful late-window source transport')
        refined_report['meaningful_transport_minimum_m3'] = meaningful_minimum
        reports[scenario] = {'base': base_report, 'refined': refined_report, 'refinement': refinement}
        _i5_check_memory()
    if index['schema'].endswith(('v6', 'v7')):
        _i5_require(index['work']['new_1d_rhs_evaluations'] == new_rhs and index['work']['new_1d_link_evaluations'] == new_links, 'reused/unfinished work mixed with new complete-case work')
    return {'schema': AUDIT_SCHEMA, 'status': 'passed', 'errors': [], 'index_sha256': index_pin['sha256'], 'inputs': inputs, 'reports': reports, 'actual_section_storage_verified': True, 'paired_per_cell_water_and_tracers_verified': True, 'time_refinement_verified': True, 'scope': 'saved_finite_1d_diffusive_storage_and_two_engineering_events_not_independent_momentum_solver', 'continuous_between_steps_positivity_certified': False, 'numerical_version': index.get('numerical_version'), 'accuracy_policy': index.get('accuracy_policy'), 'natural_outlet_certified': False, 'full_network_verified': False, 'three_dimensional_flow_solved': False}

def _entry_audit_hybrid_river_hydraulics():
    parser = _i5_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=_i5_Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=_i5_Path, required=True)
    args = parser.parse_args()
    _i5_require(not args.output.exists(), 'new independent audit output required')
    started = _i5_time.monotonic()
    index_pin = {'path': str(args.input.resolve()), 'sha256': args.sha256}
    try:
        report = audit(index_pin)
    except (ValueError, KeyError, TypeError, OSError) as error:
        report = {'schema': AUDIT_SCHEMA, 'status': 'refused', 'index_sha256': args.sha256, 'errors': [str(error)], 'natural_outlet_certified': False}
    report['resource'] = {'wall_seconds': _i5_time.monotonic() - started, 'actual_peak_rss_bytes': _i5_check_memory()}
    report['code_sha256'] = {name: _i5_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_hydraulics.py', 'tools/td_shared_channel_fine_saved_audit.py', 'tests/test_hybrid_hydraulics_saved_audit.py')}
    report['identity_sha256'] = _i5_digest(report)
    payload = _i5_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i5_require(len(payload) <= _i5_MAX_BYTES, 'independent audit exceeds file limit')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(_i5_json.dumps(report, ensure_ascii=True))
    if report['status'] != 'passed':
        raise SystemExit(1)
_i6_sys.path.insert(0, str(ROOT))

def diagnose(index_pin):
    index = _i6_read(index_pin)
    _i6_require(index['schema'] in ('td-hybrid-river-hydraulics-preparation-v6', 'td-hybrid-river-hydraulics-preparation-v7') and index['status'] in ('failed_partial', 'refused_diagnostic_evidence'), 'only refused v6/v7 saved batches are supported')
    inputs = index['inputs']
    graph, geometry, configuration = [_i6_read(inputs[key]) for key in ('graph', 'geometry', 'experiments')]
    geometry_audit = _i6_read_audit(inputs['geometry_audit'])
    model = _i6_read(index['hydraulic_model_parameters'])
    _i6_require(geometry_audit['status'] == 'passed' and (not geometry_audit['errors']) and (geometry_audit['geometry_sha256'] == inputs['geometry']['sha256']) and (geometry_audit['actual_hydraulic_sections_verified'] is True) and (geometry_audit['actual_portal_connections_verified'] is True), 'actual geometry audit not passed or not bound')
    _i6_require(model['code_sha256'] == index['code_sha256'] and model['forcing_configuration_pin'] == inputs['experiments'] and (index['physical_model_identity_sha256'] == physical_identity(model)) and (model['geometry_identity_sha256'] == index['geometry_identity_sha256'] == geometry['identity_sha256']) and (model['graph_identity_sha256'] == index['graph_identity_sha256'] == graph['identity_sha256']) and (configuration['geometry_identity_sha256'] == geometry['identity_sha256']) and (configuration['graph_identity_sha256'] == graph['identity_sha256']), 'unbound diagnostic model/forcing/graph/geometry')
    for parent in (index, geometry, geometry_audit):
        for key in ('code_sha256', 'audit_code_sha256', 'readonly_dependency_code_sha256'):
            for name, sha in parent.get(key, {}).items():
                _i6_require(_i6_file_sha256(ROOT / name) == sha, 'frozen dependency changed: ' + name)
    bdf = index['schema'].endswith('v7')
    check_same_physics(include_bdf=bdf)
    if bdf:
        check_accuracy_policy(index, model)
    parameters_by_scenario = {row['scenario']: row for row in configuration['scenarios']}
    reports, records = ({}, {})
    for name in index['completed_cases']:
        record = _i6_read(index['artifacts'][name + '.json'])
        check_case_binding(record, index, model, name)
        scenario, level = name.rsplit('-', 1)
        original = parameters_by_scenario[scenario]
        _i6_require(record['inputs'] == inputs, 'diagnostic case input binding mismatch')
        if bdf:
            _i6_require(index['input_parameter_identities'][scenario] == _i6_digest(original), 'original forcing identity changed')
            parameters = accuracy_parameters(original, level)
        else:
            parameters = original if level == 'base' else {**original, 'max_step_s': original['max_step_s'] / 2, 'relative_tolerance': original['relative_tolerance'] / 4, 'absolute_tolerance': original['absolute_tolerance'] / 4}
        reports[name] = check_result(record, geometry, parameters)
        records[name] = record
    comparisons = {}
    for scenario in parameters_by_scenario:
        if scenario + '-base' not in records or scenario + '-refined' not in records:
            comparisons[scenario] = {'status': 'not_comparable_missing_case'}
            continue
        base, refined = (records[scenario + '-base'], records[scenario + '-refined'])
        difference = abs(_i6_np.asarray(base['hydraulic_head_m']) - refined['hydraulic_head_m'])
        row, column = _i6_np.unravel_index(difference.argmax(), difference.shape)
        evidence = {'max_head_difference_m': float(difference[row, column]), 'worst_head_time_s': base['times_s'][row], 'worst_head_cell_id': base['cell_ids'][column], 'final_max_head_difference_m': float(difference[-1].max()), 'max_volume_difference_m3': float(_i6_np.max(abs(_i6_np.asarray(base['water_volume_m3']) - refined['water_volume_m3']))), 'paired_link_max_absolute_difference_m3': {key: float(_i6_np.max(abs(_i6_np.asarray(base[key]) - refined[key]))) for key in ('paired_link_water_integral_m3', 'paired_link_source_integral_m3', 'paired_link_tailwater_integral_m3', 'paired_link_untraced_integral_m3')}}
        try:
            evidence.update(compare_saved(base, refined), status='passed_individual_pair_only')
        except ValueError as error:
            evidence.update(status='refused', error=str(error))
        comparisons[scenario] = evidence
    return {'schema': 'td-hybrid-river-hydraulics-saved-diagnostic-v1', 'status': 'saved_diagnostic_read_not_acceptance', 'index_pin': index_pin, 'parent_batch_status': index['status'], 'inputs': inputs, 'completed_case_reports': reports, 'comparisons': comparisons, 'failure': index.get('failure'), 'recorded_batch_work': index['work'], 'independent_acceptance_passed': False, 'water_animation_authorized': False, 'time_refinement_verified': False, 'natural_outlet_certified': False, 'full_network_verified': False, 'three_dimensional_flow_solved': False, 'scope': 'independent_actual_section_and_completed_case_ledger_checks_from_refused_batch_only'}

def _entry_audit_hybrid_river_hydraulics_diagnostic():
    parser = _i6_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=_i6_Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=_i6_Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    _i6_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification diagnostic output required')
    started = _i6_time.monotonic()
    report = diagnose({'path': str(args.input.resolve()), 'sha256': args.sha256})
    report['resource'] = {'wall_seconds': _i6_time.monotonic() - started, 'actual_peak_rss_bytes': _i6_check_memory()}
    report['code_sha256'] = {name: _i6_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_hydraulics.py', 'tools/audit_hybrid_hydraulics.py', 'tools/td_shared_channel_fine_saved_audit.py', 'tests/test_hybrid_hydraulics_saved_audit.py')}
    report['identity_sha256'] = _i6_digest(report)
    payload = _i6_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i6_require(len(payload) <= _i6_MAX_BYTES, 'saved diagnostic exceeds file budget')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(_i6_json.dumps({'status': report['status'], 'output': str(output), 'sha256': _i6_file_sha256(output), 'completed_cases': list(report['completed_case_reports']), 'comparisons': report['comparisons']}))
NUMERICAL_VERSION = 'three_origin_local_vertical_frame_analytic_Radau_precision-v8'

def local_geometry(geometry, datum):
    local = _i7_copy.deepcopy(geometry)
    for cell in local['hydraulic_cells']:
        section = cell['section']
        key = 'polygon_transverse_elevation_m' if section['kind'] == 'closed_polygon' else 'polyline_transverse_elevation_m'
        _i7_require(section['kind'] in ('open_polyline', 'closed_polygon'), 'local frame requires actual polygon/polyline sections')
        section[key] = [[point[0], point[1] - datum] for point in section[key]]
    return local

def expected_frame(geometry):
    floors = []
    for cell in geometry['hydraulic_cells']:
        section = cell['section']
        points = section.get('polygon_transverse_elevation_m', section.get('polyline_transverse_elevation_m'))
        _i7_require(points is not None, 'actual section floor not supplied')
        floors.append(min((point[1] for point in points)))
    return {'schema': 'td-hybrid-river-local-vertical-frame-v8', 'datum_m': _i7_math.floor(min(floors)), 'datum_policy': 'floor_minimum_actual_section_floor_m', 'computation': 'one_common_local_frame_before_inverse_friction_flux_and_Jacobian', 'output': 'global_head_equals_datum_plus_local_head', 'source_geometry_unchanged': True, 'tiny_flux_deadband': False}

def check_frame(record, geometry, parameters):
    expected = expected_frame(geometry)
    _i7_require(record['numerical_frame'] == expected, 'wrong/non-common local vertical datum policy')
    local_heads = _i7_np.asarray(record['local_hydraulic_head_m'], dtype=float)
    global_heads = _i7_np.asarray(record['hydraulic_head_m'], dtype=float)
    _i7_require(local_heads.shape == global_heads.shape == (len(record['times_s']), len(geometry['hydraulic_cells'])) and _i7_np.isfinite(local_heads).all() and _i7_np.isfinite(global_heads).all() and _i7_np.array_equal(global_heads, local_heads + expected['datum_m']), 'global/local head output mismatch')
    _i7_require(record['local_tailwater_head_m'] == parameters['tailwater_head_m'] - expected['datum_m'] and record['execution_progress']['numerical_frame'] == expected, 'local tailwater/progress not bound to common frame')
    return (expected, local_heads)

def projected_result(record, geometry, parameters):
    frame, heads = check_frame(record, geometry, parameters)
    datum = frame['datum_m']
    projected = _i7_copy.deepcopy(record)
    projected['schema'] = 'td-hybrid-river-hydraulics-v6'
    projected['numerical_version'] = 'three_origin_analytic_native_chain_Radau-v6'
    projected['hydraulic_head_m'] = heads.tolist()
    for key in ('open_channel_stage_m', 'pressurized_head_m'):
        projected[key] = [[float(head) if original is not None else None for original, head in zip(row, local_row)] for row, local_row in zip(record[key], heads)]
        for global_row, local_row in zip(record[key], projected[key]):
            _i7_require(all((global_value is None or global_value == local_value + datum for global_value, local_value in zip(global_row, local_row))), 'global stage/pressure output not bound to local head')
    for ordinal, snapshot in enumerate(projected['saved_section_diagnostics']):
        for column, cell in enumerate(snapshot['cells']):
            _i7_require(cell['head_m'] == record['hydraulic_head_m'][ordinal][column] and cell['local_head_m'] == float(heads[ordinal, column]), 'section probe has unbound global/local head')
            section = geometry['hydraulic_cells'][column]['section']
            if section['kind'] == 'closed_polygon':
                _i7_require(cell['crown_m'] == max((point[1] for point in section['polygon_transverse_elevation_m'])), 'section probe crown not in source global frame')
            else:
                points = section['polyline_transverse_elevation_m']
                _i7_require(cell['low_bank_m'] == min(points[0][1], points[-1][1]), 'section probe bank not in source global frame')
            cell['head_m'] = float(heads[ordinal, column])
    local_parameters = {**parameters, 'initial_heads_m': [value - datum for value in parameters['initial_heads_m']], 'tailwater_head_m': parameters['tailwater_head_m'] - datum}
    _i7_require(record['local_solver_parameters'] == local_parameters and record['local_solver_parameters_identity_sha256'] == _i7_digest(local_parameters), 'local solver parameters changed forcing/precision or mixed datum')
    projected['parameters'] = local_parameters
    projected['parameters_identity_sha256'] = _i7_digest(local_parameters)
    projected.pop('identity_sha256', None)
    projected['identity_sha256'] = _i7_digest(projected)
    return (projected, local_geometry(geometry, datum), local_parameters)

def check_accuracy(index, model):
    expected = {'schema': 'td-hybrid-river-accuracy-policy-v8', 'integration': 'Radau', 'forcing_configuration_pin_unchanged': True, 'parameter_transform': {'base': {'relative_tolerance_divisor': 64, 'absolute_tolerance_divisor': 64, 'max_step_divisor': 4}, 'refined': {'relative_tolerance_divisor': 256, 'absolute_tolerance_divisor': 256, 'max_step_divisor': 8}}, 'unchanged_scope': 'all_other_pinned_Experiment_parameters_initial_geometry_slot_forcing_and_guards', 'comparison_gates_unchanged': {'volume_absolute_tolerance_m3': 0.0001, 'head_absolute_tolerance_m': 0.001, 'volume_relative_tolerance': 0.01, 'paired_and_origin_absolute_tolerance_m3': 0.0001}, 'reused_cases_allowed': False, 'precision_change_not_physical_change': True}
    _i7_require(index['integration'] == model['integration'] == 'Radau' and index['accuracy_policy'] == model['accuracy_policy'] == expected and (index['reused_cases'] == {}), 'unbound local-frame accuracy policy')

def audit_hybrid_river_hydraulics_mechanism_8_audit(index_pin):
    index = _i7_read(index_pin)
    _i7_require(index['schema'] == 'td-hybrid-river-hydraulics-preparation-v8' and index['status'] == 'diagnostic_accepted', 'unfinished/refused local-frame batch cannot be accepted')
    cases = {scenario + '-' + level for scenario in ('pulse', 'reverse_tailwater') for level in ('base', 'refined')}
    _i7_require(set(index['completed_cases']) == set(index['generated_cases']) == cases and len(index['completed_cases']) == 4 and (set(index['artifacts']) == {name + '.json' for name in cases}), 'local-frame batch missing complete cases')
    inputs = index['inputs']
    graph, geometry, configuration = [_i7_read(inputs[key]) for key in ('graph', 'geometry', 'experiments')]
    geometry_audit = _i7_read_audit(inputs['geometry_audit'])
    model = _i7_read(index['hydraulic_model_parameters'])
    _i7_require(geometry_audit['status'] == 'passed' and (not geometry_audit['errors']) and (geometry_audit['geometry_sha256'] == inputs['geometry']['sha256']) and (geometry_audit['actual_hydraulic_sections_verified'] is True) and (geometry_audit['actual_portal_connections_verified'] is True), 'unbound/unverified actual geometry')
    from tools.prepare_hybrid_hydraulics import source_identity as source_identity
    current_code, historical_code = source_identity()
    _i7_require(model.get('source_layout') == index.get('source_layout') == 'explicit_common_radau_v8_20261023' and model.get('frozen_reference_code_sha256') == index.get('frozen_reference_code_sha256') == historical_code and (index['code_sha256'] == current_code), 'current source identity mismatch; historical batches require explicit legacy replay')
    _i7_require(model['schema'] == 'td-hybrid-river-hydraulic-model-parameters-v8' and model['model_version'] == index['model_version'] == 'explicit_roof_friction_contact_transition-v5' and (model['numerical_version'] == index['numerical_version'] == NUMERICAL_VERSION) and (model['code_sha256'] == index['code_sha256'] == current_code) and (model['forcing_configuration_pin'] == inputs['experiments']) and (model['graph_identity_sha256'] == index['graph_identity_sha256'] == graph['identity_sha256']) and (model['geometry_identity_sha256'] == index['geometry_identity_sha256'] == geometry['identity_sha256']) and (model['physical_model_identity_sha256'] == index['physical_model_identity_sha256'] == physical_identity(model)) and (model['numerical_frame'] == index['numerical_frame'] == expected_frame(geometry)) and (model['friction_policy'] == index['friction_policy']) and (model['jacobian_policy'] == index['jacobian_policy']) and (model['model_parameters'] == {'head_regularization_m': 0.0001, 'donor_regularization_m3': 1e-06}) and (index['diagnostic_stop_s'] is None) and (not index['diagnostic_artifacts']), 'unbound local-frame physical/numerical model')
    for parent in (index, geometry, geometry_audit):
        for field in ('code_sha256', 'audit_code_sha256', 'readonly_dependency_code_sha256'):
            for name, sha in parent.get(field, {}).items():
                _i7_require(_i7_file_sha256(ROOT / name) == sha, 'frozen dependency changed: ' + name)
    for parent in (graph, geometry):
        for pin in parent['inputs'].values():
            _i7_checked_path(pin)
    _i7_require(configuration['graph_identity_sha256'] == graph['identity_sha256'] and configuration['geometry_identity_sha256'] == geometry['identity_sha256'], 'wrong actual forcing parents')
    check_same_physics()
    check_accuracy(index, model)
    resource = index['resource']
    _i7_require(resource['whole_event_not_split_or_restarted'] is False and resource['one_complete_forcing_event_budget_no_work_or_wall_reset'] is True and (resource['observation_times_reinitialize_Radau'] is True) and (resource['negative_inventory_rollback_reinitializes_Radau_with_same_event_budget'] is True), 'hidden local-frame observation reset or changed budget')
    parameters_by_scenario = {row['scenario']: row for row in configuration['scenarios']}
    _i7_require(set(parameters_by_scenario) == {'pulse', 'reverse_tailwater'}, 'wrong engineering scenarios')
    reports = {}
    new_rhs, new_links = (0, 0)
    for scenario, original in parameters_by_scenario.items():
        _i7_require(index['input_parameter_identities'][scenario] == _i7_digest(original), 'original forcing identity changed')
        pair, pair_reports = ([], [])
        for level in ('base', 'refined'):
            name = scenario + '-' + level
            record = _i7_read(index['artifacts'][name + '.json'])
            parameters = accuracy_parameters(original, level)
            check_case_binding(record, index, model, name)
            _i7_require(record['schema'] == 'td-hybrid-river-hydraulics-v8' and record['parameters'] == parameters and (record['parameters_identity_sha256'] == _i7_digest(parameters)) and (record['input_parameters_identity_sha256'] == _i7_digest(original)) and (record['inputs'] == inputs) and (record['accuracy_level'] == level) and (record['accuracy_policy'] == index['accuracy_policy']) and (record['integration'] == 'Radau') and (record['inventory_policy'] == model['inventory_policy']) and (record['graph_identity_sha256'] == graph['identity_sha256']) and (record['geometry_identity_sha256'] == geometry['identity_sha256']) and (record['physical_model_identity_sha256'] == physical_identity(model)) and (record['section_adapter_schema'] == index['section_adapter_schema'] == 'td-hybrid-river-fast-sections-v2'), 'unbound local-frame saved case/accuracy/source')
            projected, local, local_parameters = projected_result(record, geometry, parameters)
            report = check_result(projected, local, local_parameters)
            report['local_frame_flux_independently_verified'] = True
            report['datum_m'] = index['numerical_frame']['datum_m']
            times = record['times_s']
            late_start = times[-1] - 100
            _i7_require(late_start in times, 'missing exact late-window observation')
            report['late_100s_source_export_m3'] = record['boundary_ledger_m3'][-1][3] - record['boundary_ledger_m3'][times.index(late_start)][3]
            if scenario == 'pulse':
                _i7_require(report['source_reached_engineered_outlet'] and report['source_outlet_m3'] >= 2.7 and (report['late_100s_source_export_m3'] >= 0.5), 'insufficient real source transport')
            else:
                _i7_require(report['reverse_reached_sink'] and report['tailwater_arrived_first_surface_m3'] >= 1, 'insufficient actual return flow')
            pair.append(projected)
            pair_reports.append(report)
            new_rhs += record['work']['rhs_evaluations']
            new_links += record['work']['link_evaluations']
        reports[scenario] = {'base': pair_reports[0], 'refined': pair_reports[1], 'refinement': compare_saved(*pair)}
        _i7_check_memory()
    _i7_require(index['work']['new_1d_rhs_evaluations'] == new_rhs and index['work']['new_1d_link_evaluations'] == new_links and (index['work']['old_hll_face_work'] == 0), 'wrong complete event work ledger')
    return {'schema': AUDIT_SCHEMA, 'status': 'passed', 'errors': [], 'index_sha256': index_pin['sha256'], 'inputs': inputs, 'reports': reports, 'actual_section_storage_verified': True, 'paired_per_cell_water_and_tracers_verified': True, 'time_refinement_verified': True, 'numerical_frame': index['numerical_frame'], 'accuracy_policy': index['accuracy_policy'], 'numerical_version': NUMERICAL_VERSION, 'local_frame_flux_independently_verified': True, 'scope': 'saved_finite_1d_diffusive_storage_two_engineering_events_in_common_local_vertical_frame', 'projection_semantics': 'in_memory_local_geometry_and_inventory_projection_into_frozen_v6_checks_original_cases_unmodified', 'continuous_between_steps_positivity_certified': False, 'natural_outlet_certified': False, 'full_network_verified': False, 'three_dimensional_flow_solved': False}

def _entry_audit_hybrid_river_hydraulics_v8():
    parser = _i7_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=_i7_Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=_i7_Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    _i7_require(not output.exists() and output.is_relative_to(ROOT / 'verification'), 'new verification audit output required')
    started = _i7_time.monotonic()
    index_pin = {'path': str(args.input.resolve()), 'sha256': args.sha256}
    try:
        report = audit_hybrid_river_hydraulics_mechanism_8_audit(index_pin)
    except (ValueError, KeyError, TypeError, OSError) as error:
        report = {'schema': AUDIT_SCHEMA, 'status': 'refused', 'index_sha256': args.sha256, 'errors': [str(error)], 'natural_outlet_certified': False}
    report['resource'] = {'wall_seconds': _i7_time.monotonic() - started, 'actual_peak_rss_bytes': _i7_check_memory()}
    report['code_sha256'] = {name: _i7_file_sha256(ROOT / name) for name in ('tools/audit_hybrid_hydraulics.py', 'tools/audit_hybrid_hydraulics.py', 'tools/td_shared_channel_fine_saved_audit.py', 'tests/test_hybrid_hydraulics_saved_audit.py', 'tests/test_hybrid_hydraulics_saved_audit.py')}
    report['identity_sha256'] = _i7_digest(report)
    payload = _i7_json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    _i7_require(len(payload) <= _i7_MAX_BYTES, 'independent audit file budget exceeded')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    summary = {scenario: values['refinement'] for scenario, values in report.get('reports', {}).items()}
    print(_i7_json.dumps({'status': report['status'], 'errors': report['errors'], 'output': str(output), 'sha256': _i7_file_sha256(output), 'refinement': summary}))
    if report['status'] != 'passed':
        raise SystemExit(1)

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'audit': '_entry_audit_hybrid_river_hydraulics', 'diagnostic': '_entry_audit_hybrid_river_hydraulics_diagnostic', 'local-frame': '_entry_audit_hybrid_river_hydraulics_v8'}
    values = list(sys.argv[1:] if argv is None else argv)
    if len(commands) == 1:
        selected = next(iter(commands))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('command', choices=tuple(commands))
        parsed, values = parser.parse_known_args(values)
        selected = parsed.command
    function = globals()[commands[selected]]
    previous = sys.argv
    try:
        sys.argv = [previous[0]] + values
        return function(values) if inspect.signature(function).parameters else function()
    finally:
        sys.argv = previous
if __name__ == '__main__':
    main()
