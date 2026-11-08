from copy import deepcopy

import numpy as np
import pytest

from terrain_pipeline.coastal_delta_branching import _record
from terrain_pipeline.coastal_delta_evolution import advance_years, FloodplainConfig, save, load
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig, solve
from terrain_pipeline.coastal_delta_node_inventory import ChannelInventory
from test_coastal_delta_multicell import fixture, total


def graph_fixture():
    state, p = fixture()
    p['hydraulics_backend'] = 'physical_edge_graph'
    p['river_hydraulics'] = solve(state, p, 0., HydraulicConfig(12.))
    return _record(state, p), p


def advance(state, p, years, name, **kwargs):
    return advance_years(state, p, years, input_id=name, hydraulic_config=HydraulicConfig(12.),
        floodplain_config=FloodplainConfig(exchange_fraction=0.),
        annual_channel_exchange='capacity_balance', annual_erosion_depth_m_per_year=.1,
        river_deposition_reference_length_m=1000., **kwargs)


def test_underloaded_flow_erodes_finite_stock_and_scales_with_years(tmp_path):
    state, p = graph_fixture()
    before = deepcopy(p)
    inlet = tuple(p['routes'][0][0])
    pool = ChannelInventory(state, p)
    s1, p1 = advance(state, p, .2, 'whole')
    s2, p2 = advance(state, p, .1, 'half-a')
    s2, p2 = advance(s2, p2, .1, 'half-b')
    b1 = p1['fixed_channel_footprint']['last_feedback']['nodes']
    b2 = p2['fixed_channel_footprint']['last_feedback']['nodes']
    assert p == before
    assert b1[str(inlet)]['external_solid_m3'] < b1[str(inlet)]['capacity_solid_m3']
    assert all(b['deposited_solid_m3'] == 0 for b in b1.values())
    assert b1[str(inlet)]['eroded_solid_m3'] > 0
    solid_factor = state.spacing_m**2*sum(part[2]*(1-state.porosity[part[0],part[1]]) for part in pool._parts[inlet])
    assert b1[str(inlet)]['eroded_solid_m3'] == pytest.approx(.1*.2*solid_factor)
    assert b1[str(inlet)]['eroded_solid_m3'] == pytest.approx(2*b2[str(inlet)]['eroded_solid_m3'])
    assert ChannelInventory(s1, p1).section_bed(inlet) == pytest.approx(ChannelInventory(s2,p2).section_bed(inlet))
    for result, progress in ((s1,p1),(s2,p2)):
        assert total(result)-total(state)+progress['integrated']['pending_solid_m3'] == pytest.approx(.01*.2*365.25*86400., abs=1e-6)
        assert np.array_equal(result.base_bed_m, state.base_bed_m)
    assert p1['river_hydraulics']['accepted_q_m3_s'] > 0
    assert p1['integrated']['river_eroded_solid_m3']==pytest.approx(sum(b['eroded_solid_m3'] for b in b1.values()))
    save(tmp_path/'annual-capacity',s1,p1)
    restored, rp=load(tmp_path/'annual-capacity')
    # Saved mode/rate resume without repeating the opt-in arguments.
    _, resumed=advance_years(restored,rp,.01,input_id='resume',hydraulic_config=HydraulicConfig(12.),
        floodplain_config=FloodplainConfig(exchange_fraction=0.),river_deposition_reference_length_m=1000.)
    assert resumed['integrated']['multicell_parameters']['annual_channel_exchange']=='capacity_balance'


def test_overload_deposits_only_excess_and_retains_untransported_mobile():
    state,p=graph_fixture()
    inlet=tuple(p['routes'][0][0])
    pool=ChannelInventory(state,p)
    pool.add(inlet,'mobile_solid_m3',1000.)
    state,p=pool.commit(state,p)
    state=_record(state,p)
    out,updated=advance(state,p,.000001,'overload',river_deposition_fraction=.5)
    budget=updated['fixed_channel_footprint']['last_feedback']['nodes'][str(inlet)]
    available=budget['initial_mobile_solid_m3']+budget['external_solid_m3']
    excess=available-budget['capacity_solid_m3']
    assert excess>0 and 0<budget['deposited_solid_m3']<=excess
    assert budget['transported_solid_m3']==pytest.approx(budget['capacity_solid_m3'])
    assert budget['eroded_solid_m3']==0
    assert ChannelInventory(out,updated).amount(inlet,'mobile_solid_m3')==pytest.approx(
        available-budget['deposited_solid_m3']-budget['transported_solid_m3'])
    assert total(out)-total(state)+updated['integrated']['pending_solid_m3']==pytest.approx(.01*.000001*365.25*86400.,abs=1e-6)


def test_explicit_mode_transition_preserves_prior_identity_and_rejects_legacy():
    state,p=graph_fixture()
    legacy,lp=advance_years(state,p,.000001,input_id='old-mode',hydraulic_config=HydraulicConfig(12.),
        floodplain_config=FloodplainConfig(exchange_fraction=0.),river_deposition_reference_length_m=1000.)
    old=deepcopy(lp['integrated']['multicell_parameters'])
    _,updated=advance(legacy,lp,.000001,'new-mode')
    transition=updated['integrated']['multicell_parameter_transitions'][-1]
    assert transition['previous']==old and transition['input_id']=='new-mode'
    assert lp['integrated']['multicell_parameters']==old
    state,p=fixture()
    with pytest.raises(ValueError,match='physical_edge_graph'):
        advance(state,p,.000001,'requires-graph')


def test_finite_bed_and_zero_flow_do_not_supply_fake_erosion():
    state,p=graph_fixture()
    inlet=tuple(p['routes'][0][0])
    pool=ChannelInventory(state,p)
    # Remove real loose bed into mobile, then leave a known small erodible stock.
    removed=pool.take(inlet,'bed_solid_m3',pool.amount(inlet,'bed_solid_m3'))
    pool.add(inlet,'mobile_solid_m3',removed)
    pool.add(inlet,'bed_solid_m3',1.)
    pool.take(inlet,'mobile_solid_m3',1.)
    state,p=pool.commit(state,p)
    state=_record(state,p)
    out,updated=advance(state,p,.2,'finite-bed')
    b=updated['fixed_channel_footprint']['last_feedback']['nodes'][str(inlet)]
    assert b['eroded_solid_m3']==pytest.approx(1.)
    assert total(out)-total(state)+updated['integrated']['pending_solid_m3']==pytest.approx(.01*.2*365.25*86400.,abs=1e-6)
    dry_p=deepcopy(p)
    dry_p.pop('river_hydraulics')
    dry,dp=advance_years(_record(state,dry_p),dry_p,.001,input_id='dry',hydraulic_config=HydraulicConfig(-100.),
        annual_channel_exchange='capacity_balance')
    assert dp['river_hydraulics']['accepted_q_m3_s']==0
    assert dp['integrated']['river_eroded_solid_m3']==0
    assert total(dry)==pytest.approx(total(state),abs=1e-6)


def test_old_marine_default_normalizes_but_mode_change_is_rejected(tmp_path):
    from terrain_pipeline.coastal_marine_longterm import LongtermConfig
    state,p=graph_fixture()
    state,p=advance(state,p,.000001,'old-marine',marine_config=LongtermConfig())
    old=deepcopy(p)
    old['integrated']['multicell_parameters']['marine'].pop('boundary_transport')
    save(tmp_path/'old-marine',_record(state,old),old)
    restored,rp=load(tmp_path/'old-marine')
    _,resumed=advance(restored,rp,.000001,'default-resume',marine_config=LongtermConfig())
    assert resumed['integrated']['multicell_parameters']['marine']['boundary_transport']=='exchange_only'
    before=deepcopy(rp)
    with pytest.raises(ValueError,match='parameters do not match'):
        advance(restored,rp,.000001,'different-boundary',
            marine_config=LongtermConfig(boundary_transport='advective_outflow'))
    assert rp==before
    fresh,fp=graph_fixture()
    new,np_=advance(fresh,fp,.000001,'new-open-mode',
        marine_config=LongtermConfig(boundary_transport='advective_outflow'))
    save(tmp_path/'new-open-mode',new,np_)
    _,saved=load(tmp_path/'new-open-mode')
    assert saved['integrated']['multicell_parameters']['marine']['boundary_transport']=='advective_outflow'
