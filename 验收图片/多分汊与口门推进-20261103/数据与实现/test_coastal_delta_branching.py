from dataclasses import replace
from pathlib import Path
import copy
import numpy as np
import pytest
from terrain_pipeline.coastal_delta_branching import start, propose, split, advance_years, segment_fluxes, _record
from terrain_pipeline.coastal_delta_product import load_checkpoint, save_checkpoint
from terrain_pipeline.coastal_marine_longterm import LongtermConfig
from terrain_pipeline.coastal_marine_sediment import make_state

P = Path('.scratch/coast-marine-reorganization-20261102')

def small():
    shape=(8, 12)
    seeds=np.zeros(shape, bool); seeds[:, -1]=True
    state=make_state(base_bed_m=np.full(shape,-2.), bed_solid_m3=0, mobile_solid_m3=0, porosity=.4, valid_mask=True, ocean_seed_mask=seeds, spacing_m=100., origin_xz_m=(0.,0.), source_identity='test')
    trunk=[[3,c] for c in range(12)]
    network={'trunk':trunk,'fork_indices':[4,6],'branches':[[[3,4],[2,4],[2,5],[2,6],[2,7],[2,8],[2,9],[2,10],[2,11]],[[3,6],[4,6],[4,7],[4,8],[4,9],[4,10],[4,11]]]}
    return state,start(state,network,input_id='test',discharge_m3_s=3000,solid_rate_m3_s=1.6)

def test_no_change_or_remote_deposition_cannot_trigger():
    state,p=small()
    assert propose(state,state,p) is None
    stock=state.bed_solid_m3.copy(); stock[0,0]=6000
    assert propose(replace(state,bed_solid_m3=stock),state,p) is None

def test_real_split_conserves_stock_and_segment_flux():
    state,p=load_checkpoint(P/'branch-feedback-v3-split')
    proposal=p['history'][-1]['proposal']; before=copy.deepcopy(p)
    before['history'].pop(); before['routes'].pop(); share=before['shares'].pop(); before['shares'][proposal['parent']]+=share
    stock=state.bed_solid_m3.copy(); mobile=state.mobile_solid_m3.copy()
    for r,c,depth in proposal['excavation']:
        amount=depth*state.spacing_m**2*(1-state.porosity[r,c]); stock[r,c]+=amount; mobile[r,c]-=amount
    original=_record(replace(state,bed_solid_m3=stock,mobile_solid_m3=mobile),before)
    result,after=split(original,before,proposal)
    assert np.isclose(result.bed_solid_m3.sum()+result.mobile_solid_m3.sum(),original.bed_solid_m3.sum()+original.mobile_solid_m3.sum())
    assert np.allclose(result.bed_solid_m3,state.bed_solid_m3)
    edges=segment_fluxes(after); incoming={}; outgoing={}
    for edge in edges:
        a=tuple(edge['from_zx']); b=tuple(edge['to_zx']); outgoing[a]=outgoing.get(a,0)+edge['discharge_m3_s']; incoming[b]=incoming.get(b,0)+edge['discharge_m3_s']
    for node in incoming.keys() & outgoing.keys(): assert np.isclose(incoming[node],outgoing[node])
    import networkx as nx
    assert nx.is_directed_acyclic_graph(nx.DiGraph((tuple(e['from_zx']),tuple(e['to_zx'])) for e in edges))

def test_restart_stale_progress_and_clock(tmp_path):
    state,p=small(); cfg=LongtermConfig(max_step_s=31557.6,max_rise_m=1)
    a,p1=advance_years(state,p,.001,cfg,max_formative_step_years=.001)
    assert a.time_s==state.time_s
    save_checkpoint(tmp_path/'checkpoint',a,p1)
    restored,rp=load_checkpoint(tmp_path/'checkpoint')
    b,p2=advance_years(a,p1,.001,cfg,max_formative_step_years=.001)
    c,cp=advance_years(restored,rp,.001,cfg,max_formative_step_years=.001)
    assert p2==cp and np.array_equal(b.bed_solid_m3,c.bed_solid_m3)
    with pytest.raises(ValueError): advance_years(a,p,.001,cfg,max_formative_step_years=.001)

def test_split_refreshes_only_parent_and_new_child_reference():
    state,p=small()
    untouched=copy.deepcopy(p['control_references'][1:])
    proposal={'parent':0,'fork_index':5,'path':[[3,5],[4,5],[5,5],[5,6],[5,7]],'excavation':[], 'old_capacity_depth_m':1.,'new_capacity_depth_m':1.}
    state,p=split(state,p,proposal)
    assert p['control_references'][1:3]==untouched
    assert p['control_references'][0]['mouth']==p['routes'][0][-6:]
    assert p['control_references'][3]['mouth']==p['routes'][3][-6:]


def test_river_event_moves_finite_sediment_and_books_single_inlet():
    from terrain_pipeline.coastal_delta_branching import _river_exchange, advance_river_event
    from terrain_pipeline.coastal_marine_sediment import MarineConfig
    from terrain_pipeline.coastal_delta_product import _source_fingerprint
    state,p=small(); mobile=state.mobile_solid_m3.copy(); mobile[3,1]=500.
    state=replace(state,mobile_solid_m3=mobile); p['source_state_fingerprint']=_source_fingerprint(state)
    moved,report=_river_exchange(state,p,100.,capacity_concentration=.01,active_layer_m=0.)
    assert report['internal_transfer_solid_m3']>0 and moved.mobile_solid_m3[3,1]<500.
    assert np.isclose(moved.mobile_solid_m3.sum(),state.mobile_solid_m3.sum())
    cfg=MarineConfig(step_s=300.,settling_rate_s=.0001)
    result,info=advance_river_event(state,p,600.,cfg,input_id='event',inlet_solid_rate_m3_s=.1)
    assert result.time_s==state.time_s+600 and result.water_input_m3-state.water_input_m3==3000*600
    assert sum(r['input_id']=='event' for r in result.consumed_packets)==1
    total=lambda x: x.mobile_solid_m3.sum()+x.bed_solid_m3.sum()+x.stranded_solid_m3.sum()+x.exported_solid_m3
    assert np.isclose(total(result)-total(state),60.)
    with pytest.raises(ValueError): advance_river_event(result,p,600.,cfg,input_id='event')

def test_erosion_budget_is_shared_across_event_substeps():
    from terrain_pipeline.coastal_delta_branching import _river_exchange
    state,p=small(); stock=state.bed_solid_m3.copy(); stock[3,1]=1000.
    state=replace(state,bed_solid_m3=stock)
    budget={tuple(c):0. for route in p['routes'] for c in route}
    budget[(3,1)]=25.
    one,r1=_river_exchange(state,p,50.,erosion_remaining=budget)
    two,r2=_river_exchange(one,p,50.,erosion_remaining=budget)
    assert np.isclose(r1['entrained_solid_m3']+r2['entrained_solid_m3'],25.)
    assert budget[(3,1)]==0 and np.isclose(two.bed_solid_m3[3,1],975.)

def test_shoreline_extension_uses_finite_deposits_and_preserves_other_references(tmp_path):
    from terrain_pipeline.coastal_delta_branching import update_shoreline_mouths, mouth_exterior_faces
    state,p=load_checkpoint(P/'multi-branch-v2-stage')
    before=mouth_exterior_faces(state,p)
    assert not before[2] and all(before[i] for i in (0,1,3,4))
    result,after,changes=update_shoreline_mouths(state,p)
    assert all(mouth_exterior_faces(result,after)) and len(changes)==1
    assert changes[0]['route']==2 and len(after['routes'])==len(p['routes'])
    assert after['control_references'][0]==p['control_references'][0]
    assert after['control_references'][1]==p['control_references'][1]
    assert np.isclose(result.bed_solid_m3.sum()+result.mobile_solid_m3.sum(),state.bed_solid_m3.sum()+state.mobile_solid_m3.sum())
    assert np.all(result.bed_solid_m3>=0) and np.array_equal(result.base_bed_m,state.base_bed_m)
    assert changes[0]['excavated_solid_m3']>0
    save_checkpoint(tmp_path/'extended',result,after)
    _,saved=load_checkpoint(tmp_path/'extended')
    assert saved['segments']==segment_fluxes(saved)
    assert len(saved['widths_m'])==len(saved['active'])==len(saved['routes'])
    again,unchanged,extra=update_shoreline_mouths(result,after)
    assert not extra and unchanged==after and np.array_equal(again.bed_solid_m3,result.bed_solid_m3)

def test_shoreline_update_rejects_insufficient_cut_without_mutation():
    from terrain_pipeline.coastal_delta_branching import update_shoreline_mouths
    state,p=load_checkpoint(P/'multi-branch-v2-stage')
    before=state.bed_solid_m3.copy(); original=copy.deepcopy(p)
    with pytest.raises(ValueError): update_shoreline_mouths(state,p,max_cut_m=.01,radius_cells=3)
    assert np.array_equal(state.bed_solid_m3,before) and p==original

def test_shared_fork_donor_is_not_counted_twice():
    from terrain_pipeline.coastal_delta_branching import _river_exchange
    state,p=small(); mobile=state.mobile_solid_m3.copy(); mobile[3,4]=100.
    state=replace(state,mobile_solid_m3=mobile)
    result,_=_river_exchange(state,p,10.,active_layer_m=0.)
    a=result.mobile_solid_m3[3,5]; b=result.mobile_solid_m3[2,4]
    assert a>0 and b>0 and np.isclose(a/b,.66/.34)
    assert np.isclose(result.mobile_solid_m3.sum(),100.)
    assert np.isclose(result.mobile_solid_m3[3,4]+a+b,100.)
