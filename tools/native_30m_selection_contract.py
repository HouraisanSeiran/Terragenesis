"""Declare actual selector defaults and verify saved selection without changing it."""
import inspect
import numpy as np


def selection_rule():
    from terrain_pipeline.surface_rivers.native_30m_reach_selection import select_from_topology
    names = ('min_stem_m', 'min_catchment_cells', 'contact_margin_cells', 'max_nodes',
             'max_stride', 'max_catchment_cells', 'max_subwindow_cells')
    signature = inspect.signature(select_from_topology)
    return {'schema': 'native-30m-actual-reach-rule-v1',
            'parameters': {name: signature.parameters[name].default for name in names},
            'candidate_scope': 'all valid finite graph terminals; raw cut-boundary seeds plus contact margin propagated',
            'eligibility': 'complete catchment, catchment size, stem length, sampled node count, subwindow cell budget',
            'ordering': 'largest catchment cell count; smallest terminal flat id on ties',
            'stem': 'largest accumulated donor count; smallest donor flat id on ties',
            'subwindow_extra_margin_cells': 12,
            'reject_codes': ['catchment_not_complete', 'small_or_budget', 'stem_too_short',
                             'nodes_over_budget', 'subwindow_over_budget']}


def verify_saved_selection(env):
    from terrain_pipeline.surface_rivers.native_30m_reach_selection import select_from_topology
    a = env['arrays']
    fresh = select_from_topology(a['source.npz']['field'], a['topology.npz'],
                                 origin_native_xz=env['manifest']['parameters']['origin_native_xz'],
                                 **selection_arguments(env['manifest']['parameters']))
    saved = env['json_records']['selection.json']
    if fresh['candidates'] != saved['candidates']:
        raise ValueError('selection_candidate_table_recompute_mismatch')
    masks = {'catchment_mask', 'flowline_mask', 'stem_flat_cells'}
    for name in masks:
        if not np.array_equal(fresh['chosen'][name], a['selection.npz'][name]):
            raise ValueError('selection_recompute_mismatch:' + name)
    scalars = {k: v for k, v in fresh['chosen'].items() if k not in masks}
    # Convert numpy scalars/arrays without changing the numerical comparison.
    for key, value in scalars.items():
        if not np.array_equal(np.asarray(value), np.asarray(saved['chosen'][key])):
            raise ValueError('selection_scalar_recompute_mismatch:' + key)
    return {'rule': effective_rule(env['manifest']['parameters']), 'candidate_count': len(fresh['candidates']),
            'accepted_count': sum(bool(item['accepted']) for item in fresh['candidates']),
            'selection_recomputed': True}


def selection_arguments(parameters):
    import math
    values = parameters.get('selection_parameters', {})
    if not isinstance(values, dict):
        raise ValueError('selection_parameter_fields')
    result = dict(values)
    if values:
        allowed = set(selection_rule()['parameters'])
        if not set(values).issubset(allowed):
            raise ValueError('selection_parameter_fields')
        for name, value in values.items():
            if name == 'min_stem_m':
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError('selection_parameter_value:' + name)
            elif type(value) is not int or value <= 0:
                raise ValueError('selection_parameter_value:' + name)
    terminal = parameters.get('terminal_native_xz')
    if terminal is not None:
        if not isinstance(terminal, (tuple, list)) or len(terminal) != 2 or any(type(v) is not int for v in terminal):
            raise ValueError('terminal_native_xz_must_be_int_pair')
        if 'shape_zx' in parameters and 'origin_native_xz' in parameters:
            x, z = terminal
            ox, oz = parameters['origin_native_xz']
            h, w = parameters['shape_zx']
            if not (ox <= x < ox+w and oz <= z < oz+h):
                raise ValueError('terminal_outside_window')
        result['terminal_native_xz'] = list(terminal)
    return result


def effective_rule(parameters):
    options = selection_arguments(parameters)
    rule = selection_rule()
    values = {k: v for k, v in options.items() if k != 'terminal_native_xz'}
    if values:
        rule['parameters'].update(values)
    if 'terminal_native_xz' in options:
        rule['selection_mode'] = 'caller_terminal_after_full_candidate_census'
        rule['requested_terminal_native_xz'] = options['terminal_native_xz']
    return rule


def parameters_from_rule_file(value):
    if not isinstance(value, dict):
        raise ValueError('selection_rule_file_fields')
    if 'schema' in value:
        if value.get('schema') != 'native-30m-actual-reach-rule-v1' or not isinstance(value.get('parameters'), dict):
            raise ValueError('unsupported_selection_rule_schema')
        expected = selection_rule()
        expected['parameters'].update(value['parameters'])
        if value != expected:
            raise ValueError('unsupported_selection_rule_semantics')
        values = value['parameters']
    else:
        values = value
    selection_arguments({'selection_parameters': values})
    return dict(values)
