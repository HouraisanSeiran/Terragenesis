from dataclasses import replace
import numpy as np
import pytest
from terrain_pipeline.coastal_delta_branching import start, advance_river_event
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig, solve
from terrain_pipeline.coastal_delta_product import load_checkpoint, save_checkpoint, _source_fingerprint
from terrain_pipeline.coastal_marine_sediment import MarineConfig, make_state


def fixture():
    shape = (9, 13)
    base = np.full(shape, -2.)
    base[4, 6] = .05
    seeds = np.zeros(shape, bool); seeds[:, -1] = True
    state = make_state(base_bed_m=base, bed_solid_m3=0., mobile_solid_m3=0.,
                       porosity=.4, valid_mask=True, ocean_seed_mask=seeds,
                       spacing_m=100., origin_xz_m=(0., 0.), source_identity='test')
    trunk = [[4, c] for c in range(12)]
    branches = [[[4,4],[3,4],[3,5],[3,6],[3,7],[3,8],[3,9],[3,10],[3,11]],
                [[4,6],[5,6],[5,7],[5,8],[5,9],[5,10],[5,11]]]
    p = start(state, {'trunk': trunk, 'fork_indices': [4, 6], 'branches': branches},
              input_id='formation', discharge_m3_s=30., solid_rate_m3_s=.1)
    return state, p


def test_head_shared_and_tidal_boundary():
    s,p = fixture(); cfg=HydraulicConfig(upstream_stage_limit_m=4.)
    low = solve(s,p,0.,cfg); high = solve(s,p,.7,cfg)
    assert low['accepted_q_m3_s'] == pytest.approx(30.)
    nodes = {(a,b):(h,d,q) for a,b,h,d,q in low['nodes']}
    assert nodes[4,6][1] > 0 and s.bed_m[4,6] > 0
    assert nodes[4,0][2] == pytest.approx(sum(low['route_q_m3_s']))
    assert len(nodes) == len(low['nodes'])
    assert {(a,b):h for a,b,h,_,_ in high['nodes']}[4,0] > nodes[4,0][0]


def test_high_barrier_rejects_water():
    s,p=fixture(); base=s.base_bed_m.copy(); base[4,2]=10.
    s=replace(s,base_bed_m=base)
    r=solve(s,p,0.,HydraulicConfig(upstream_stage_limit_m=4.))
    assert r['accepted_q_m3_s'] == 0 and r['rejected_q_m3_s'] == 30.


def test_event_conservation_cold_restart_and_identity(tmp_path):
    s,p=fixture(); cfg=HydraulicConfig(upstream_stage_limit_m=4.)
    marine=MarineConfig(step_s=300.,tide_amplitude_m=.2)
    out, report=advance_river_event(s,p,600.,marine,input_id='event1',inlet_solid_rate_m3_s=.1,hydraulic_config=cfg)
    q=report['updated_progress']; save_checkpoint(tmp_path/'state',out,q)
    restored,rp=load_checkpoint(tmp_path/'state')
    stock=lambda a: sum(float(getattr(a,k).sum()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))+a.exported_solid_m3
    assert stock(out)-stock(s)+report['undelivered_solid_m3'] == pytest.approx(60.)
    assert out.time_s==600 and q['years']==p['years']
    a,ar=advance_river_event(out,q,300.,marine,input_id='event2',inlet_solid_rate_m3_s=.1,hydraulic_config=cfg)
    b,br=advance_river_event(restored,rp,300.,marine,input_id='event2',inlet_solid_rate_m3_s=.1,hydraulic_config=cfg)
    assert np.array_equal(a.bed_solid_m3,b.bed_solid_m3) and ar==br
    with pytest.raises(ValueError):
        advance_river_event(restored,rp,300.,marine,input_id='event2',hydraulic_config=HydraulicConfig(5.))


def test_river_wet_inlet_above_ocean_keeps_its_solid():
    s,p=fixture(); base=s.base_bed_m.copy(); base[4,0]=.05
    s=replace(s,base_bed_m=base); p['source_state_fingerprint']=_source_fingerprint(s)
    result,report=advance_river_event(s,p,1.,MarineConfig(step_s=1.),input_id='dry-ocean-inlet',
                                      inlet_solid_rate_m3_s=.1, active_layer_m=0.,
                                      hydraulic_config=HydraulicConfig(4.))
    assert report['delivered_water_m3'] == pytest.approx(30.)
    assert report['undelivered_solid_m3'] == 0
    assert result.mobile_solid_m3[4,0] > 0
    assert report['updated_progress']['river_hydraulics']['nodes'][0][3] > 0


def test_blocked_inlet_books_all_water_and_sediment_pending():
    s,p=fixture(); base=s.base_bed_m.copy(); base[4,2]=10.
    s=replace(s,base_bed_m=base); p['source_state_fingerprint']=_source_fingerprint(s)
    result,report=advance_river_event(s,p,300.,MarineConfig(step_s=300.),input_id='blocked',
                                     inlet_solid_rate_m3_s=.1,hydraulic_config=HydraulicConfig(4.))
    assert report['delivered_water_m3']==0 and report['undelivered_water_m3']==pytest.approx(9000.)
    assert report['delivered_solid_m3']==0 and report['undelivered_solid_m3']==pytest.approx(30.)
    assert result.water_input_m3==s.water_input_m3


def test_branch_with_impassable_crest_redistributes():
    s,p=fixture(); base=s.base_bed_m.copy(); base[3,7]=10.
    result=solve(replace(s,base_bed_m=base),p,0.,HydraulicConfig(4.))
    assert result['route_q_m3_s'][1] == 0
    assert result['route_q_m3_s'][0] > 0 and result['route_q_m3_s'][2] > 0
    assert sum(result['route_q_m3_s']) == pytest.approx(result['accepted_q_m3_s'])


def test_nested_blocked_branch_preserves_other_fork_share():
    state, progress = fixture()
    base = state.base_bed_m.copy()
    base[5, 9] = 10.
    result = solve(replace(state, base_bed_m=base), progress, 0., HydraulicConfig(4.))
    assert result['active'] == [True, True, False]
    assert result['accepted_q_m3_s'] == pytest.approx(30.)
    assert result['route_q_m3_s'] == pytest.approx([19.8, 10.2, 0.])


def section_progress(state, progress, width=30.):
    progress = dict(progress)
    cells = {tuple(c) for route in progress['routes'] for c in route}
    progress['hydraulic_sections'] = {'nodes': [[z, x, float(state.bed_m[z,x]), width, 2.]
                                                for z, x in sorted(cells)]}
    return progress


def test_sections_use_fixed_width_and_tide_at_exterior():
    state, progress = fixture()
    narrow = section_progress(state, progress, 10.)
    wide = section_progress(state, progress, 80.)
    cfg = HydraulicConfig(10.)
    a = solve(state, narrow, 0., cfg)
    b = solve(state, wide, 0., cfg)
    high = solve(state, wide, .5, cfg)
    assert a['nodes'][0][2] > b['nodes'][0][2]
    assert high['nodes'][0][2] > b['nodes'][0][2]
    mouth = tuple(progress['routes'][0][-1])
    assert {(n[0], n[1]): n[2] for n in b['nodes']}[mouth] > 0.
    assert b['accepted_q_m3_s'] == pytest.approx(30.)


def test_section_fork_resistance_is_local_and_conservative():
    state, progress = fixture()
    p = section_progress(state, progress)
    cfg = HydraulicConfig(10.)
    original = solve(state, p, 0., cfg)
    for row in p['hydraulic_sections']['nodes']:
        if row[:2] in progress['routes'][2][7:]:
            row[3] = 80.
            row[2] -= 1.
    changed = solve(state, p, 0., cfg)
    assert changed['route_q_m3_s'][2] > original['route_q_m3_s'][2]
    assert changed['route_q_m3_s'][1] == pytest.approx(original['route_q_m3_s'][1], rel=1e-4)
    assert sum(changed['route_q_m3_s']) == pytest.approx(changed['accepted_q_m3_s'])
    cells = [(n[0], n[1]) for n in changed['nodes']]
    assert len(cells) == len(set(cells))
    assert changed['nodes'][0][4] == pytest.approx(changed['accepted_q_m3_s'])


def test_section_blockage_missing_and_upstream_capacity():
    state, progress = fixture()
    p = section_progress(state, progress, 10.)
    cfg = HydraulicConfig(4.)
    for row in p['hydraulic_sections']['nodes']:
        if row[:2] == [5, 9]:
            row[2] = 5.; row[4] = 5.
    result = solve(state, p, 0., cfg)
    assert not result['active'][2]
    assert result['route_q_m3_s'][2] == 0.
    p['hydraulic_sections']['nodes'] = [row for row in p['hydraulic_sections']['nodes'] if row[:2] != [4, 2]]
    missing = solve(state, p, 0., cfg)
    assert missing['accepted_q_m3_s'] == 0.
    p = section_progress(state, progress, 1.)
    limited = solve(state, p, 0., HydraulicConfig(.5))
    assert 0 < limited['accepted_q_m3_s'] < 30.
    assert limited['rejected_q_m3_s'] == pytest.approx(30. - limited['accepted_q_m3_s'])
    assert limited['nodes'][0][2] <= .5 + 1e-8


def test_sections_rejoined_paths_share_flow_once():
    state, progress = fixture()
    p = section_progress(state, progress, 30.)
    upper = [[4, 0], [4, 1], [3, 2], [3, 3], [4, 4], [4, 5], [3, 6], [3, 7], [4, 8], [4, 9], [4, 10], [4, 11]]
    lower = [[4, 0], [4, 1], [5, 2], [5, 3], [4, 4], [4, 5], [5, 6], [5, 7], [4, 8], [4, 9], [4, 10], [4, 11]]
    p['routes'] = [upper, lower, upper[:6] + lower[6:], lower[:6] + upper[6:]]
    p['shares'] = [.25] * 4
    p['hydraulic_sections']['nodes'] = [[z, x, -2., 30., 2.] for z, x in sorted({tuple(c) for route in p['routes'] for c in route})]
    result = solve(state, p, 0., HydraulicConfig(10.))
    nodes = {(r[0], r[1]): r for r in result['nodes']}
    assert result['accepted_q_m3_s'] == pytest.approx(30.)
    assert sum(result['route_q_m3_s']) == pytest.approx(30.)
    for cell in [(4, 0), (4, 4), (4, 8), (4, 11)]:
        assert nodes[cell][4] == pytest.approx(30.)
    assert nodes[3, 2][4] + nodes[5, 2][4] == pytest.approx(30.)
