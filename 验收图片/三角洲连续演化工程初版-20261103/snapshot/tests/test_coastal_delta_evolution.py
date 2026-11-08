from dataclasses import replace
import numpy as np
import pytest
from terrain_pipeline.coastal_delta_evolution import FloodplainConfig, overbank_exchange
from terrain_pipeline.coastal_marine_sediment import make_state


def fixture():
    base=np.full((7,7),2.)
    base[3,1:5]=0.
    seeds=np.zeros_like(base,dtype=bool); seeds[0,0]=True
    mobile=np.zeros_like(base); mobile[3,1]=100.
    return make_state(base_bed_m=base,bed_solid_m3=0.,mobile_solid_m3=mobile,porosity=.4,
        valid_mask=True,ocean_seed_mask=seeds,spacing_m=100.,origin_xz_m=(0.,0.),source_identity='test')


def test_wet_connected_flood_and_bounded_budget():
    s=fixture(); cfg=FloodplainConfig(exchange_fraction=.5,max_lateral_distance_m=400.,max_solid_fraction=.01)
    out,report=overbank_exchange(s,[(3,1)],[1.],1000.,config=cfg)
    assert report['diverted_water_m3']==report['returned_water_m3']==500.
    assert 0 < report['deposited_solid_m3'] <= 5.
    assert out.bed_solid_m3.sum()+out.mobile_solid_m3.sum()+out.stranded_solid_m3.sum()==pytest.approx(100.)
    assert np.all(out.bed_m<=np.maximum(s.bed_m,1.))


def test_no_flood_across_dry_ridge_or_when_below_bank():
    s=fixture(); base=s.base_bed_m.copy(); base[3,2]=2.; s=replace(s,base_bed_m=base)
    out,info=overbank_exchange(s,[(3,1)],[1.],1000.)
    assert out.bed_solid_m3[3,3]==0 and info['deposited_solid_m3']==0
    out,_=overbank_exchange(s,[(3,1)],[0.],1000.)
    assert np.array_equal(out.mobile_solid_m3,s.mobile_solid_m3)


def test_channel_cut_is_finite_and_cannot_cut_base():
    from terrain_pipeline.coastal_delta_evolution import open_deposited_path
    s=fixture(); stock=s.bed_solid_m3.copy(); stock[3,2]=3000.; stock[3,3]=1500.
    s=replace(s,bed_solid_m3=stock)
    out,report=open_deposited_path(s,[(3,2),(3,3)],0.)
    assert report['excavated_solid_m3']==pytest.approx(4500.)
    assert out.bed_solid_m3.sum()+out.mobile_solid_m3.sum()==pytest.approx(s.bed_solid_m3.sum()+s.mobile_solid_m3.sum())
    with pytest.raises(ValueError): open_deposited_path(s,[(3,2),(2,2)],0.)
    assert s.bed_solid_m3[3,2]==3000.


def test_event_wrapper_preserves_budget_and_restart(tmp_path):
    from terrain_pipeline.coastal_delta_evolution import advance_event
    from terrain_pipeline.coastal_delta_product import load_checkpoint, save_checkpoint
    from terrain_pipeline.coastal_delta_branching import start
    from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
    from terrain_pipeline.coastal_marine_sediment import MarineConfig
    base=np.full((9,13),-2.); seeds=np.zeros_like(base,dtype=bool); seeds[:,-1]=True
    s=make_state(base_bed_m=base,bed_solid_m3=0.,mobile_solid_m3=10.,porosity=.4,valid_mask=True,
                 ocean_seed_mask=seeds,spacing_m=100.,origin_xz_m=(0.,0.),source_identity='test')
    trunk=[[4,c] for c in range(12)]
    p=start(s,{'trunk':trunk,'fork_indices':[4,6],'branches':[
        [[4,4],[3,4],[3,5],[3,6],[3,7],[3,8],[3,9],[3,10],[3,11]],
        [[4,6],[5,6],[5,7],[5,8],[5,9],[5,10],[5,11]]]},
        input_id='formation',discharge_m3_s=30.,solid_rate_m3_s=.1)
    kwargs={'marine_config':MarineConfig(step_s=300.),'hydraulic_config':HydraulicConfig(4.),'inlet_solid_rate_m3_s':.1}
    a,report=advance_event(s,p,300.,input_id='first',**kwargs)
    total=lambda t: sum(float(getattr(t,k).sum()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))+t.exported_solid_m3
    assert total(a)-total(s)+report['undelivered_solid_m3']==pytest.approx(30.)
    save_checkpoint(tmp_path/'state',a,report['updated_progress'])
    b,bp=load_checkpoint(tmp_path/'state')
    c,cr=advance_event(a,report['updated_progress'],300.,input_id='second',**kwargs)
    d,dr=advance_event(b,bp,300.,input_id='second',**kwargs)
    assert np.array_equal(c.bed_solid_m3,d.bed_solid_m3) and cr==dr


def test_flood_water_limits_wet_area_and_donor_head():
    s = fixture()
    base = np.full((7, 7), 4.)
    base[3, 1] = base[3, 3] = base[3, 5] = 0.
    base[3, 2] = 2.
    base[3, 4] = 2.
    mobile = np.zeros_like(base); mobile[3, 1] = 100.
    s = replace(s, base_bed_m=base, mobile_solid_m3=mobile)
    cfg = FloodplainConfig(exchange_fraction=1., max_lateral_distance_m=500.)
    out, info = overbank_exchange(s, [(3, 1), (3, 5)], [1., 3.], 100., config=cfg)
    assert out.bed_solid_m3[3, 3] == 0.
    assert info['diverted_water_m3'] <= 100.
    assert info['wet_area_m2'] <= 100. / 1.


def test_rewetting_releases_only_local_stock():
    s = fixture()
    stranded = s.stranded_solid_m3.copy(); stranded[3, 2] = 100.
    s = replace(s, stranded_solid_m3=stranded, mobile_solid_m3=np.zeros_like(s.mobile_solid_m3))
    out, info = overbank_exchange(s, [(3, 1)], [1.], 1000.,
        config=FloodplainConfig(exchange_fraction=1., max_lateral_distance_m=100.))
    assert 0 < info['rewetted_solid_m3'] <= info['diverted_water_m3'] * .01
    assert out.bed_solid_m3[3, 2] > 0.
    assert sum(a.sum() for a in (out.bed_solid_m3, out.mobile_solid_m3, out.stranded_solid_m3)) == pytest.approx(100.)


def test_marine_same_cell_rewet_does_not_jump_to_neighbor():
    from terrain_pipeline.coastal_marine_sediment import MarineConfig, advance
    base = np.full((3, 3), 1.)
    base[0, 1] = base[1, 1] = -1.
    seeds = np.zeros((3, 3), dtype=bool); seeds[0, 1] = True
    s = make_state(base_bed_m=base, bed_solid_m3=0., mobile_solid_m3=0., porosity=.4,
        valid_mask=True, ocean_seed_mask=seeds, spacing_m=100., origin_xz_m=(0., 0.), source_identity='test')
    stranded = s.stranded_solid_m3.copy(); stranded[1, 2] = 10.
    s = replace(s, stranded_solid_m3=stranded)
    dry = advance(s, [], 1., MarineConfig(same_cell_wet_dry=True))
    assert dry.stranded_solid_m3[1, 2] == 10.
    assert dry.mobile_solid_m3[1, 1] == 0.
    wet = advance(dry, [], 1., MarineConfig(sea_level_m=2., same_cell_wet_dry=True, transverse_diffusivity_m2_s=0.))
    assert wet.stranded_solid_m3[1, 2] == 0.
    assert wet.mobile_solid_m3[1, 2] == pytest.approx(10.)


def test_integrated_annual_budget_and_restart(tmp_path):
    from terrain_pipeline.coastal_delta_evolution import initialize, advance_years
    from terrain_pipeline.coastal_delta_product import save_checkpoint, load_checkpoint
    s = fixture()
    route = np.array([[3, 1], [3, 2], [3, 3], [3, 4]])
    routes = {'main_cells_zx': route, 'branch_offsets': np.array([0]),
        'branch_cells_zx': np.empty((0, 2), int), 'section_bed_m': np.zeros(4),
        'section_bank_m': np.ones(4), 'section_width_m': np.full(4, 20.),
        'section_stage_m': np.ones(4)}
    s, p = initialize(s, routes, {'source_identity': 'test'}, discharge_m3_s=10., solid_rate_m3_s=.1)
    solution = {'accepted_q_m3_s': 5., 'route_q_m3_s': [5.]}
    out, progress = advance_years(s, p, .001, input_id='year-1', hydraulic_result=solution)
    amount = .1 * .001 * 365.25 * 86400
    before = sum(getattr(s, n).sum() for n in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'))
    after = sum(getattr(out, n).sum() for n in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'))
    assert after - before + progress['integrated']['pending_solid_m3'] == pytest.approx(amount)
    assert progress['integrated']['accepted_water_m3'] == pytest.approx(5 * .001 * 365.25 * 86400)
    assert progress['integrated']['river_deposited_solid_m3'] > 0
    assert progress['integrated']['sections']['section_width_m'][0] < 20.
    assert out.time_s == s.time_s
    save_checkpoint(tmp_path/'checkpoint', out, progress)
    restored, loaded = load_checkpoint(tmp_path/'checkpoint')
    next1, p1 = advance_years(out, progress, .001, input_id='year-2', hydraulic_result=solution)
    next2, p2 = advance_years(restored, loaded, .001, input_id='year-2', hydraulic_result=solution)
    assert np.array_equal(next1.bed_solid_m3, next2.bed_solid_m3)
    assert p1 == p2
    with pytest.raises(ValueError):
        advance_years(out, progress, .001, input_id='year-1', hydraulic_result=solution)


def test_annual_floodplain_receives_incoming_sediment():
    from terrain_pipeline.coastal_delta_evolution import initialize, advance_years
    s = fixture()
    base = s.base_bed_m.copy(); base[2, 1:5] = 0.
    s = replace(s, base_bed_m=base, mobile_solid_m3=np.zeros_like(base))
    route = np.array([[3, 1], [3, 2], [3, 3], [3, 4]])
    routes = {'main_cells_zx': route, 'branch_offsets': np.array([0]),
        'branch_cells_zx': np.empty((0, 2), int), 'section_bed_m': np.zeros(4),
        'section_bank_m': np.ones(4), 'section_width_m': np.full(4, 20.),
        'section_stage_m': np.ones(4)}
    s, p = initialize(s, routes, {'source_identity': 'test'}, discharge_m3_s=10., solid_rate_m3_s=.01)
    solution = {'accepted_q_m3_s': 10., 'route_q_m3_s': [10.],
                'nodes': [[*cell, 1., 1., 10.] for cell in route]}
    out, p = advance_years(s, p, .001, input_id='flood', hydraulic_result=solution,
        floodplain_config=FloodplainConfig(exchange_fraction=.5, max_lateral_distance_m=100.))
    report = p['history'][-1]['floodplain']
    assert report['new_solid_m3'] > 0
    assert report['deposited_solid_m3'] > 0
    assert report['new_solid_m3'] + report['rewetted_solid_m3'] <= report['diverted_water_m3'] * .01 + 1e-8
    total = sum(float(getattr(out, k).sum()) for k in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'))
    assert total == pytest.approx(.01 * .001 * 365.25 * 86400.)


def test_net_geometry_refresh_covers_extended_and_branch_nodes():
    from terrain_pipeline.coastal_delta_evolution import _refresh_geometry
    s = fixture()
    stock = s.bed_solid_m3.copy(); stock[3, 1:4] += 6000.
    after = replace(s, bed_solid_m3=stock)
    p = {'routes': [[[3, 1], [3, 2]], [[3, 1], [3, 3]]],
         'hydraulic_sections': {'nodes': [[3, 1, 0., 20., 1.], [3, 2, 0., 40., 1.], [3, 3, 0., 50., 1.]]},
         'integrated': {'sections': {'section_bed_m': [0.], 'section_width_m': [20.], 'section_bank_m': [1.]}}}
    _refresh_geometry(s, after, p)
    assert [n[2] for n in p['hydraulic_sections']['nodes']] == pytest.approx([1., 1., 1.])
    assert p['integrated']['sections']['section_bed_m'] == pytest.approx([1.])


def test_invalid_infinite_years_rejected_before_loop():
    from terrain_pipeline.coastal_delta_evolution import initialize, advance_years
    s = fixture(); route = np.array([[3, 1], [3, 2]])
    routes = {'main_cells_zx': route, 'branch_offsets': np.array([0]), 'branch_cells_zx': np.empty((0, 2), int),
              'section_bed_m': np.zeros(2), 'section_bank_m': np.ones(2),
              'section_width_m': np.full(2, 20.), 'section_stage_m': np.ones(2)}
    s, p = initialize(s, routes, {'source_identity': 'test'})
    with pytest.raises(ValueError):
        advance_years(s, p, float('inf'), input_id='infinite')


def test_river_transport_uses_explicit_section_bed(monkeypatch):
    from terrain_pipeline import coastal_delta_branching as branching
    s = fixture()
    edges = [{'from_zx': [3, 1], 'to_zx': [3, 2], 'discharge_m3_s': 10.}]
    monkeypatch.setattr(branching, '_event_edges', lambda *args, **kwargs: edges)
    p = {'routes': [[[3, 1], [3, 2]]], 'shares': [1.], 'discharge_m3_s': 10.,
         'hydraulic_sections': {'nodes': [[3, 1, 2., 20., 2.], [3, 2, 2., 20., 2.]]}}
    blocked, _ = branching._river_exchange(s, p, 10., river_stages={(3,1): 1., (3,2): 1.})
    assert blocked.mobile_solid_m3[3,2] == 0.
    p['hydraulic_sections']['nodes'][0][2] = 0.
    p['hydraulic_sections']['nodes'][1][2] = 0.
    flowing, _ = branching._river_exchange(s, p, 10., river_stages={(3,1): 1., (3,2): 1.})
    assert flowing.mobile_solid_m3[3,2] > 0.


def test_tidal_phases_conserve_supply_and_leave_physical_clock():
    from terrain_pipeline.coastal_delta_evolution import initialize, advance_years, TidalConfig
    from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig
    from terrain_pipeline.coastal_marine_longterm import LongtermConfig
    base=np.full((7,7),-2.); seeds=np.zeros_like(base,dtype=bool); seeds[:,-1]=True
    s=make_state(base_bed_m=base,bed_solid_m3=0.,mobile_solid_m3=0.,porosity=.4,
        valid_mask=True,ocean_seed_mask=seeds,spacing_m=100.,origin_xz_m=(0.,0.),source_identity='test')
    route=np.array([[3,1],[3,2],[3,3],[3,4],[3,5]])
    routes={'main_cells_zx':route,'branch_offsets':np.array([0]),'branch_cells_zx':np.empty((0,2),int),
        'section_bed_m':np.full(5,-2.),'section_bank_m':np.ones(5),
        'section_width_m':np.full(5,20.),'section_stage_m':np.ones(5)}
    s,p=initialize(s,routes,{'source_identity':'test'},discharge_m3_s=10.,solid_rate_m3_s=.01)
    out,p=advance_years(s,p,.0001,input_id='tide',hydraulic_config=HydraulicConfig(4.),
        marine_config=LongtermConfig(),tidal_config=TidalConfig(.2,4),step_years=.25)
    assert out.time_s==s.time_s and out.water_input_m3==s.water_input_m3
    assert len([x for x in p['history'] if x.get('event')=='integrated_years'])==4
    total=lambda v:sum(float(getattr(v,k).sum()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))+v.exported_solid_m3
    assert total(out)-total(s)+p['integrated']['pending_solid_m3']==pytest.approx(.01*.0001*365.25*86400)
