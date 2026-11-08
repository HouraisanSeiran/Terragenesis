import copy
from dataclasses import replace

import numpy as np
import pytest

from terrain_pipeline.coastal_delta_avulsion import activate_candidate
from terrain_pipeline.coastal_delta_branching import _record
from terrain_pipeline.coastal_delta_evolution import save, load
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from test_coastal_delta_multicell import fixture


def configured():
    state, p = fixture()
    bed = state.bed_solid_m3.copy()
    bed[9, :] += 3. * state.spacing_m**2 * (1-state.porosity[9, :])
    state = replace(state, bed_solid_m3=bed)
    p['hierarchical_plan'] = {'forks': [], 'route_depths': [0, 0], 'side_branch_counts': [0, 0],
        'route_shares': list(p['shares']), 'design_q_m3_s': [50., 50.],
        'resolved_vertex_xz_m': [100., 500.], 'prepared_paths': {'cells': copy.deepcopy(p['routes']), 'points_xz': []},
        'config': {'max_depth': 3, 'max_side_branches': 2, 'max_mouths': 8, 'min_spacing_m': 100.,
                   'min_design_q_m3_s': 1., 'min_fraction': .2, 'sea_axis_xz': [1., 0.],
                   'fan_half_angle_deg': 80., 'fan_max_length_m': 3000., 'min_forward_m': 100.,
                   'max_backtrack_m': 300., 'max_detour_ratio': 2.}}
    return _record(state, p), p


def test_baseline_no_rise_and_limits():
    s, p = configured()
    s, p, report = activate_candidate(s, p, hydraulic_config=HydraulicConfig(12.))
    assert report['trigger'] == 'baseline_recorded'
    out, q, report = activate_candidate(s, p, hydraulic_config=HydraulicConfig(12.))
    assert report['trigger'] == 'no_downstream_rise' and out is s and q is p
    p['hierarchical_plan']['config']['max_mouths'] = 2
    s = _record(s, p)
    out, q, report = activate_candidate(s, p, hydraulic_config=HydraulicConfig(12.))
    assert report['trigger'] == 'mouth_limit' and out is s and q is p


def test_raised_but_no_ocean_preserves_stock(tmp_path):
    s, p = configured()
    s, p, _ = activate_candidate(s, p, hydraulic_config=HydraulicConfig(12.))
    for row in p['avulsion_baseline_sections']:
        row[2] -= .2
    s = _record(s, p)
    before = copy.deepcopy(p)
    out, q, report = activate_candidate(s, p, hydraulic_config=HydraulicConfig(12.), sea_level_m=-100.)
    assert not report['activated'] and out is s and q is p and p == before
    assert np.array_equal(out.bed_solid_m3, s.bed_solid_m3)
    save(tmp_path/'check', s, p)
    s2, p2 = load(tmp_path/'check')
    _, _, again = activate_candidate(s2, p2, hydraulic_config=HydraulicConfig(12.), sea_level_m=-100.)
    assert again['trigger'] == report['trigger']


def test_success_consumes_trigger_and_survives_reload(tmp_path):
    s, p = configured()
    s, p, _ = activate_candidate(s, p, hydraulic_config=HydraulicConfig(12.))
    for row in p['avulsion_baseline_sections']:
        row[2] -= .2
    s = _record(s, p)
    old_parts = copy.deepcopy(p['node_footprints'])
    old_total = sum(getattr(s, f).sum() for f in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'))
    out, q, report = activate_candidate(s, p, hydraulic_config=HydraulicConfig(12.))
    assert report['activated'], report
    assert q['node_footprints'][:len(old_parts)] == old_parts
    assert sum(getattr(out, f).sum() for f in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')) == pytest.approx(old_total)
    assert q['river_hydraulics']['route_q_m3_s'][-1] > 0
    save(tmp_path/'success', out, q)
    restored, rp = load(tmp_path/'success')
    again, rq, result = activate_candidate(restored, rp, hydraulic_config=HydraulicConfig(12.))
    assert not result['activated'] and result['trigger'] == 'no_downstream_rise'
    assert again is restored and rq is rp



def test_front_excludes_ocean_interior():
    from terrain_pipeline.coastal_delta_multicell_avulsion import coastal_front
    bed = np.full((9, 12), -2.)
    bed[:, :3] = 1.
    valid = np.ones_like(bed, dtype=bool)
    ocean = bed < 0
    front = coastal_front(valid, bed, ocean, valid, 0.)
    assert front[:, 2:4].all()
    assert not front[:, 4:].any()
    assert not front[:, :2].any()
