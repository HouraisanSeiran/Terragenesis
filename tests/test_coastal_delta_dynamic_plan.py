"""Explicit dynamic graph enrollment and finite-stock deposition triggers."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from terrain_pipeline.coastal_delta_branching import _record
from terrain_pipeline.coastal_delta_evolution import load, save
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
from terrain_pipeline.coastal_delta_multicell_avulsion import activate_multicell_candidate
from terrain_pipeline.coastal_delta_network_plan import DynamicPlanConfig, enroll_dynamic_plan
from terrain_pipeline.coastal_delta_node_inventory import ChannelInventory
from test_coastal_delta_multicell_avulsion import configured
from test_coastal_delta_multicell import total

HYDRAULIC = HydraulicConfig(12.)


def policy(**changes):
    base = DynamicPlanConfig(min_actual_child_q_m3_s=2., min_effective_width_m=5.,
        min_spacing_m=150., min_forward_m=100., sea_axis_xz=(1., 0.),
        fan_half_angle_deg=80., fan_max_length_m=4000., direction_decay_m=200.,
        max_detour_ratio=2., max_backtrack_m=300.)
    return replace(base, **changes)


def fixture(config=None, *, width_m=80., discharge_m3_s=1000., world_seed=20261020):
    from terrain_pipeline.coastal_delta_geological_network import construct
    from terrain_pipeline.coastal_marine_sediment import make_state
    base = np.full((20, 30), -5.)
    bed = np.full_like(base, 18000.)
    bed[-1] += 18000.  # A real coast, established before enrollment.
    seeds = np.zeros_like(base, bool)
    seeds[:, -1] = True
    seeds[:, 0] = True
    state = make_state(base_bed_m=base, bed_solid_m3=bed, mobile_solid_m3=0., porosity=.4,
        valid_mask=True, ocean_seed_mask=seeds, spacing_m=100., origin_xz_m=(0., 0.), source_identity='dynamic')
    state, p, _ = construct(state, domain=state.valid_mask, inlet_zx=(8, 1), main_outlet_zx=(8, 26),
        forks=[(0, 5, (3, 26))], hydraulic_config=HYDRAULIC, input_id='formation',
        discharge_m3_s=discharge_m3_s, solid_rate_m3_s=.01, depth_m=5., width_m=width_m,
        reference_q_m3_s=discharge_m3_s, max_width_m=400., subdivisions=12, world_seed=world_seed)
    p['hydraulics_backend'] = 'physical_edge_graph'
    state = _record(state, p)
    state, p, report = enroll_dynamic_plan(state, p, config=config or policy(),
        hydraulic_config=HYDRAULIC, sea_level_m=0., input_id='finite-stock-test')
    assert report['enrolled'], report
    return state, p


def deposit(state, progress, route_index, rise=.2):
    """Move real unowned loose bed stock into an owned downstream section."""
    target = tuple(progress['routes'][route_index][-2])
    pool = ChannelInventory(state, progress)
    amount = pool.area(target)*(1-state.porosity[target])*rise
    donor = (0, 0)
    assert all((r, c) != donor for _, _, parts in progress['node_footprints'] for r, c, *_ in parts)
    bed = state.bed_solid_m3.copy()
    assert bed[donor] >= amount
    bed[donor] -= amount
    debited = replace(state, bed_solid_m3=bed)
    pool = ChannelInventory(debited, progress)
    pool.add(target, 'bed_solid_m3', amount)
    out, p = pool.commit(debited, progress)
    assert total(out) == pytest.approx(total(state), abs=1e-6)
    return _record(out, p), p


def activate(s, p):
    return activate_multicell_candidate(s, p, hydraulic_config=HYDRAULIC)


def test_parent_child_grandchild_fresh_deposition_and_reload(tmp_path):
    s, p = fixture(world_seed=1)
    s0, p0, r = activate(s, p)
    assert r['trigger'] == 'no_downstream_rise' and s0 is s and p0 is p
    s, p = deposit(s, p, 0)
    original_total = total(s)
    s, p, r = activate(s, p)
    assert r['activated'], r
    assert r['parent'] == 0
    child = r['attachment']['route_index']
    assert r['attachment']['actual_arm']['min_new_edge_q_m3_s'] >= 2
    assert r['attachment']['actual_arm']['retained_parent_q_m3_s'] >= 2
    assert total(s) == pytest.approx(original_total, abs=1e-6)
    _, _, r = activate(s, p)
    assert r['trigger'] == 'no_downstream_rise'
    save(tmp_path/'first', s, p)
    s, p = load(tmp_path/'first')
    _, _, r = activate(s, p)
    assert r['trigger'] == 'no_downstream_rise'
    s, p = deposit(s, p, child)
    s, p, r = activate(s, p)
    assert r['activated'], r
    assert r['parent'] == child
    assert p['hierarchical_plan']['route_depths'][-1] == 3
    assert len(p['dynamic_plan']['lineage']) == 3
    assert total(s) == pytest.approx(original_total, abs=1e-6)
    _, _, r = activate(s, p)
    assert not r['activated']
    replay = deepcopy(p)
    replay.pop('dynamic_plan')
    replay.pop('hierarchical_plan')
    _, _, r = enroll_dynamic_plan(_record(s, replay), replay, config=policy(),
        hydraulic_config=HYDRAULIC, sea_level_m=0., input_id='child-lineage-replay')
    assert r['enrolled'], r
    assert r['route_depths'] == [2, 1, 3, 3]
    assert r['side_branch_counts'] == [2, 0, 1, 0]



def test_enrollment_idempotent_transactional_and_identity(tmp_path):
    s, p = fixture()
    before = deepcopy(p)
    out, q, report = enroll_dynamic_plan(s, p, config=policy(), hydraulic_config=HYDRAULIC,
                                         sea_level_m=0., input_id='finite-stock-test')
    assert report['reason'] == 'already_enrolled' and out is s and q is p and p == before
    out, q, report = enroll_dynamic_plan(s, p, config=policy(max_depth=2), hydraulic_config=HYDRAULIC,
                                         sea_level_m=0., input_id='finite-stock-test')
    assert not report['enrolled'] and out is s and q is p and p == before
    save(tmp_path/'enrolled', s, p)
    restored, rp = load(tmp_path/'enrolled')
    assert rp == p
    assert np.array_equal(restored.bed_solid_m3, s.bed_solid_m3)
    p['dynamic_plan']['config']['min_rise_m'] = .01
    assert activate(s, p)[2]['trigger'] == 'dynamic_policy_identity_mismatch'


@pytest.mark.parametrize('limits,trigger', [({'max_depth': 0}, 'parent_limits'),
    ({'max_side_branches': 0}, 'parent_limits'), ({'max_mouths': 2}, 'mouth_limit'),
    ({'min_actual_child_q_m3_s': 1000}, 'parent_limits')])
def test_actual_flow_and_topology_gates(limits, trigger):
    s, p = fixture(policy(**limits))
    s, p = deposit(s, p, 0)
    before = deepcopy(p)
    out, q, r = activate(s, p)
    assert r['trigger'] == trigger and out is s and q is p and p == before
    assert r['counts']['paths_tested'] == 0


def test_bounded_failed_search_preserves_stock(monkeypatch):
    from terrain_pipeline import coastal_delta_multicell_avulsion as avulsion
    calls = []
    def unreachable(*args, **kwargs):
        calls.append(1)
        raise ValueError('fixture unreachable candidate')
    s, p = fixture(policy(max_total_candidates=2, max_candidates_per_parent=2))
    s, p = deposit(s, p, 0)
    before = deepcopy(p)
    monkeypatch.setattr(avulsion, 'irregular_valley_path', unreachable)
    out, q, r = activate(s, p)
    assert len(calls) == r['counts']['paths_tested']
    assert 0 < len(calls) <= 2
    assert len(r['attempts']) == len(calls)
    assert all(c['paths_tested'] <= 2 for c in r['parent_counts'].values())
    assert out is s and q is p and p == before


def test_legacy_and_unenrolled_graph_require_explicit_enrollment():
    s, p = configured()
    p['hydraulics_backend'] = 'physical_edge_graph'
    s = _record(s, p)
    assert activate(s, p)[2]['trigger'] == 'dynamic_not_enrolled'


def test_replay_old_rejoin_history_and_reject_missing_ambiguous():
    from test_coastal_delta_graph_integration import two_rejoins
    s, p = two_rejoins()
    for h in p['history']:
        if h.get('event') == 'branch_attachment':
            for key in ('parent_index', 'fork_index', 'fork_zx', 'rejoin_zx'):
                h.pop(key, None)
    old = deepcopy(p)
    out, q, r = enroll_dynamic_plan(s, p, config=policy(max_side_branches=4),
        hydraulic_config=HYDRAULIC, sea_level_m=0., input_id='replay')
    assert r['enrolled'], r
    assert r['route_depths'] == [3, 1, 2, 3]
    assert r['side_branch_counts'] == [3, 0, 0, 0]
    assert p == old and q['routes'] == p['routes'] and q['route_geometry'] == p['route_geometry']
    assert q['hydraulic_sections'] == p['hydraulic_sections']
    for field in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'):
        assert np.array_equal(getattr(out, field), getattr(s, field))
    broken = deepcopy(p)
    broken['history'] = [h for h in broken['history'] if h.get('event') != 'branch_attachment']
    out, q, r = enroll_dynamic_plan(s, broken, config=policy(), hydraulic_config=HYDRAULIC,
                                   sea_level_m=0., input_id='missing')
    assert not r['enrolled'] and out is s and q is broken
    ambiguous = deepcopy(p)
    # Two saved initial covers with the same prefix make the old parent ambiguous.
    ambiguous['routes'][1] = deepcopy(ambiguous['routes'][0])
    s2 = _record(s, ambiguous)
    out, q, r = enroll_dynamic_plan(s2, ambiguous, config=policy(), hydraulic_config=HYDRAULIC,
                                   sea_level_m=0., input_id='ambiguous')
    assert not r['enrolled'] and 'ambiguous' in r['reason']


@pytest.mark.parametrize('settings,reason', [({'min_effective_width_m': 1000.}, 'width'),
    ({'min_actual_child_q_m3_s': 200.}, 'wet flow')])
def test_new_actual_arm_rejection_is_atomic(settings, reason):
    from test_coastal_delta_branch_attachment import candidate
    from terrain_pipeline.coastal_delta_branch_attachment import attach_multicell_branch
    s, p = configured()
    p.pop('hierarchical_plan')
    p['hydraulics_backend'] = 'physical_edge_graph'
    s = _record(s, p)
    cfg = policy(**settings)
    if 'min_actual_child_q_m3_s' in settings:
        cfg = replace(cfg, min_actual_child_q_m3_s=20.)
    s, p, enrolled = enroll_dynamic_plan(s, p, config=cfg, hydraulic_config=HYDRAULIC, sea_level_m=0., input_id='atomic')
    assert enrolled['enrolled']
    k, path, xy = candidate(s, p)
    before = deepcopy(p)
    out, q, r = attach_multicell_branch(s, p, parent_index=0, fork_index=k,
        path_zx=path, path_xz_m=xy, hydraulic_config=HYDRAULIC)
    assert not r['attached'] and reason in r['reason'], r
    assert out is s and q is p and p == before


def test_fractional_construction_fork_survives_real_mouth_extension():
    from test_coastal_delta_multicell import fixture as original_fixture
    from terrain_pipeline.coastal_delta_branching import mouth_exterior_faces
    from terrain_pipeline.coastal_delta_mouth_extension import extend_multicell_mouths
    s, p = original_fixture()
    p['geological_network']['forks'][0][1] = 3/(len(p['routes'][0])-1)
    original_length = len(p['routes'][0])
    bed = s.bed_solid_m3.copy()
    for options in mouth_exterior_faces(s, p):
        for cell in options:
            cell = tuple(cell)
            bed[cell] += 4*s.spacing_m**2*(1-s.porosity[cell])
    s = _record(replace(s, bed_solid_m3=bed), p)
    s, p, extension = extend_multicell_mouths(s, p, hydraulic_config=HYDRAULIC,
                                            radius_m=400., max_cut_m=.5)
    assert extension['extended'] and len(p['routes'][0]) > original_length
    p['hydraulics_backend'] = 'physical_edge_graph'
    s = _record(s, p)
    _, _, report = enroll_dynamic_plan(s, p, config=policy(), hydraulic_config=HYDRAULIC,
                                       sea_level_m=0., input_id='extended-fraction')
    assert report['enrolled'], report
    assert report['lineage'][0]['fork_index'] == 3


def test_shared_existing_child_prefix_is_rejected_transactionally():
    from terrain_pipeline.coastal_delta_branch_attachment import attach_multicell_branch
    from terrain_pipeline.coastal_delta_routes import irregular_valley_path
    s, p = fixture()
    k = 2
    start = tuple(p['routes'][0][k])
    forbidden = np.zeros(s.bed_m.shape, bool)
    for route in p['routes']:
        for c in route:
            forbidden[tuple(c)] = True
    forbidden[start] = False
    xy = next(row[2:] for row in p['route_geometry']['nodes'] if tuple(row[:2]) == start)
    path, points = irregular_valley_path(s.bed_m, s.valid_mask, start, (18, 15), 12., s.spacing_m,
        origin_xz_m=s.origin_xz_m, world_seed=p['route_geometry']['seed'], forbidden=forbidden,
        start_xz_m=xy)
    before = deepcopy(p)
    out, q, r = attach_multicell_branch(s, p, parent_index=0, fork_index=k,
        path_zx=path, path_xz_m=points, hydraulic_config=HYDRAULIC)
    assert not r['attached'] and 'existing child upstream prefix' in r['reason'], r
    assert out is s and q is p and p == before
    s, p = deposit(s, p, 0)
    _, _, r = activate(s, p)
    assert all(a['fork_index'] > 5 for a in r.get('attempts', []) if a['parent'] == 0)


def test_frozen_c_history_replay_if_available():
    prefix = Path('.scratch/delta-reference-shapes-20261104/reference-case-v7/prepared-c/initial')
    if not prefix.with_suffix('.json').exists():
        pytest.skip('local frozen TD fixture is unavailable')
    s, p = load(prefix)
    before = deepcopy(p)
    cfg = DynamicPlanConfig(max_mouths=3, min_spacing_m=900., min_forward_m=600.)
    out, q, r = enroll_dynamic_plan(s, p, config=cfg,
        hydraulic_config=HydraulicConfig(**p['river_hydraulics']['parameters']),
        sea_level_m=0., input_id='frozen-c-replay')
    assert r['enrolled'], r
    assert r['route_depths'] == [2, 1, 2] and r['side_branch_counts'] == [2, 0, 0]
    assert p == before and q['routes'] == p['routes'] and q['route_geometry'] == p['route_geometry']
    assert p['river_hydraulics']['route_q_m3_s'][2] == 0.
    _, _, activation = activate_multicell_candidate(out, q,
        hydraulic_config=HydraulicConfig(**p['river_hydraulics']['parameters']))
    assert activation['trigger'] == 'no_downstream_rise'
    assert activation['counts']['eligible_parents'] >= 1
    for field in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'):
        assert np.array_equal(getattr(out, field), getattr(s, field))


def test_dry_new_arm_rejected_with_existing_network_still_flowing():
    from test_coastal_delta_branch_attachment import candidate
    from terrain_pipeline.coastal_delta_branch_attachment import attach_multicell_branch
    s, p = configured()
    p.pop('hierarchical_plan')
    p['hydraulics_backend'] = 'physical_edge_graph'
    k, path, xy = candidate(s, p)
    bed = s.bed_solid_m3.copy()
    bed[6:8, 3:14] += 1e6  # Actual finite high outer sill; original node stock unchanged.
    s = _record(replace(s, bed_solid_m3=bed), p)
    s, p, r = enroll_dynamic_plan(s, p, config=policy(), hydraulic_config=HYDRAULIC,
                                 sea_level_m=0., input_id='dry-arm')
    assert r['enrolled'], r
    before = deepcopy(p)
    out, q, r = attach_multicell_branch(s, p, parent_index=0, fork_index=k,
        path_zx=path, path_xz_m=xy, hydraulic_config=HYDRAULIC)
    assert not r['attached'] and 'continuous actual wet flow' in r['reason'], r
    assert out is s and q is p and p == before
