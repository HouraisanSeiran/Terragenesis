"""Explicit, finite morphology preparation and representative discharge capture."""
from copy import deepcopy

from .coastal_delta_branching import _record, _update_activity
from .coastal_delta_hydraulics import solve


def capture_formative_discharge(state, progress, *, hydraulic_config, reference_sea_level_m=0.):
    """Save positive unique node Q from a reference-level graph solve.

    Dry reference solves retain historical positive Q. This is a representative
    boundary condition, not a climate statistic or instantaneous tidal flow.
    The saved operational hydraulics remain at their existing sea level.
    """
    if progress.get('hydraulics_backend') != 'physical_edge_graph':
        raise ValueError('representative actual discharge requires physical_edge_graph')
    p = deepcopy(progress)
    solution = solve(state, p, reference_sea_level_m, hydraulic_config)
    previous = p.get('formative_discharge', {})
    values = {tuple(row[:2]): row[2] for row in previous.get('nodes', [])}
    references = {tuple(row[:2]): row[2] for row in previous.get('node_reference_sea_level_m', [])}
    for z, x, _, _, q in solution['nodes']:
        if q > p['discharge_m3_s']*1e-7:
            values[z, x] = q
            references[z, x] = float(reference_sea_level_m)
    p['formative_discharge'] = {
        'nodes': [[*node, q] for node, q in sorted(values.items())],
        'node_reference_sea_level_m': [[*node, references.get(node, previous.get('reference_sea_level_m'))]
                                      for node in sorted(values)],
        'source': 'reference-level physical graph unique node discharge; last positive value retained',
        'reference_sea_level_m': float(reference_sea_level_m),
        'reference_semantics': 'latest attempted solve; each retained positive node value keeps its own reference level',
        'parameters': solution['parameters'], 'algorithm': solution['algorithm'],
        'accepted_q_m3_s': solution['accepted_q_m3_s']}
    return _record(state, p), p


def prepare_morphology(state, progress, *, sea_level_m, hydraulic_config,
                       max_cut_m=.5, min_wet_depth_m=.05, subdivisions=None,
                       capture_formative=False, reference_sea_level_m=0.):
    """Claim finite banks using existing design widths, then solve current stages.

    Bank requests use freshly solved stages at the actual supplied sea level;
    bank cuts enter mobile inventory and never modify the immutable source.
    """
    from .coastal_delta_bank_formation import prepare_banks
    p = deepcopy(progress)
    _update_activity(state, p, sea_level_m, 'morphology:before', hydraulic_config)
    state = _record(state, p)
    state, p, report = prepare_banks(state, p, max_cut_m=max_cut_m,
        min_wet_depth_m=min_wet_depth_m, subdivisions=subdivisions)
    _update_activity(state, p, sea_level_m, 'morphology:after', hydraulic_config)
    report['hydraulics_recompute_required'] = False
    report['recomputed_sea_level_m'] = float(sea_level_m)
    p['fixed_channel_footprint']['lateral_change'] = 'explicit finite bank preparation; hydraulics recomputed'
    if capture_formative:
        state, p = capture_formative_discharge(_record(state, p), p,
            hydraulic_config=hydraulic_config, reference_sea_level_m=reference_sea_level_m)
    return _record(state, p), p, report
