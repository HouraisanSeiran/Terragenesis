import numpy as np
import pytest
from terrain_pipeline.coastal_marine_sediment import load_state, make_state, advance, MarineConfig
from terrain_pipeline.coastal_delta_product import DeltaConfig, start, advance_formation, save_checkpoint, load_checkpoint, read_product, _width, _route, _ocean_transit_graph, _transit, _spread
from terrain_pipeline.coastal_marine_product import load_product as load_base_product

SOURCE='.scratch/coast-marine-reorganization-20261102/sediment-v3-state.npz'
BASE='.scratch/coast-marine-reorganization-20261102/base-product-v2'

def total(s):
    return sum(getattr(s,k).sum() for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3')) + s.exported_solid_m3 + s.unresolved_solid_m3

def test_restart_inventory_replay_and_marine_continuation(tmp_path, monkeypatch):
    source=load_state(SOURCE)
    cfg=DeltaConfig(formation_id='test-rank4',inlet_zx=(214,401),direction_xz=(10200,1200),clearance_m=1,total_years=20,interval_years=10)
    progress=start(source,cfg)
    first,p,_=advance_formation(source,progress,cfg)
    save_checkpoint(tmp_path/'snapshot',first,p)
    restored,p=load_checkpoint(tmp_path/'snapshot')
    product, _, loaded_progress = read_product(tmp_path/'snapshot', source, BASE)
    assert loaded_progress == p
    assert np.array_equal(product['source_bed_m'], source.bed_m)
    assert np.array_equal(product['final_bed_m'], restored.bed_m)
    assert np.all(product['classification'][~source.valid_mask] == 0)
    _, base = load_base_product(BASE)
    assert np.array_equal(product['source_classification'],base['classification'])
    assert np.all(product['classification'][base['classification']==0]==0)
    # The real source contains unknown negative cells but no code-3 examples.
    # Simulate an explicitly classified enclosed cell at the same location.
    ocean,_=classify_ocean(source,0.)
    cell=tuple(np.argwhere((base['classification']==0) & source.valid_mask & ~ocean)[0])
    adjusted=dict(base); adjusted['classification']=base['classification'].copy()
    adjusted['classification'][cell]=3
    manifest,_=load_base_product(BASE)
    monkeypatch.setattr('terrain_pipeline.coastal_delta_product.load_base_product',lambda _: (manifest,adjusted))
    enclosed,_,_=read_product(tmp_path/'snapshot',source,BASE)
    assert enclosed['source_classification'][cell]==3
    assert enclosed['classification'][cell]==3
    with pytest.raises(ValueError):
        read_product(tmp_path/'snapshot', replace(source,source_identity='wrong'), BASE)
    altered=source.mobile_solid_m3.copy(); altered[214,401]+=1
    with pytest.raises(ValueError):
        read_product(tmp_path/'snapshot', replace(source,mobile_solid_m3=altered), BASE)
    assert not product['final_bed_m'].flags.writeable
    assert np.array_equal(first.mobile_solid_m3,restored.mobile_solid_m3)
    with pytest.raises(ValueError): start(restored,cfg)
    resumed,done,network=advance_formation(restored,p,cfg)
    continuous,expected,_=advance_formation(source,progress,cfg,2)
    assert np.array_equal(resumed.bed_solid_m3,continuous.bed_solid_m3)
    assert np.array_equal(resumed.mobile_solid_m3,continuous.mobile_solid_m3)
    assert done == expected
    assert done['pending_solid_m3']==0
    assert np.isclose(total(resumed)-total(source),done['supply_solid_m3'],rtol=1e-10)
    assert np.array_equal(resumed.base_bed_m,source.base_bed_m)
    for path in [network['trunk'],*network['branches']]:
        assert all(abs(a[0]-b[0])+abs(a[1]-b[1])==1 for a,b in zip(path,path[1:]))
    with pytest.raises(ValueError): advance_formation(resumed,done,cfg)
    event=advance(resumed,[],3600,MarineConfig(step_s=1800, tide_amplitude_m=1, wave_height_m=1.5, transport_rate_s=2e-5, settling_rate_s=1e-5))
    assert np.isclose(total(event),total(resumed),rtol=1e-10)
    assert np.isclose(event.time_s,resumed.time_s+3600)
    assert not np.array_equal(event.mobile_solid_m3,resumed.mobile_solid_m3)
    assert resumed.consumed_packets[-1]["delivered_solid_m3"] == done["supply_solid_m3"]
    wet,_=classify_ocean(resumed,0.)
    assert not np.any(resumed.mobile_solid_m3[~wet])
    for r,c,q,w,bed in network["sections"]:
        assert np.isclose(bed,resumed.bed_m[r,c],atol=1e-10)
    trunk=set(map(tuple,network["trunk"]))
    a,b=[set(map(tuple,path)) for path in network["branches"]]
    assert len(trunk & a)==len(trunk & b)==1
    assert not a & b
    with pytest.raises(ValueError): start(event,cfg)

def test_local_mobile_and_width_feedback():
    source=load_state(SOURCE)
    cfg=DeltaConfig(formation_id='test-rank4',inlet_zx=(214,401),direction_xz=(10200,1200),clearance_m=1,total_years=20,interval_years=10)
    first,p,n=advance_formation(source,start(source,cfg),cfg)
    second,q,n2=advance_formation(first,p,cfg)
    assert np.count_nonzero(first.mobile_solid_m3-source.mobile_solid_m3)>20
    assert q['reach_exchange'] and any(x[1]>0 for x in q['reach_exchange'].values())
    assert _width(100,100,30)<_width(100,100,0)
    assert any(section[2] < cfg.discharge_m3_s for section in n2['sections'])
    assert max(section[3] for section in n2['sections']) < source.spacing_m
from dataclasses import replace
from terrain_pipeline.coastal_marine_sediment import classify_ocean

def test_existing_remote_mobile_is_not_reinjected_at_inlet():
    source=load_state(SOURCE)
    ocean,_=classify_ocean(source,0.)
    z,x=np.indices(ocean.shape)
    candidates=np.argwhere(ocean & (abs(z-214)+abs(x-401)>70))
    cell=tuple(candidates[len(candidates)//2])
    mobile=source.mobile_solid_m3.copy(); mobile[cell]+=1e7
    amended=replace(source,mobile_solid_m3=mobile)
    cfg=DeltaConfig(formation_id='test-rank4',inlet_zx=(214,401),direction_xz=(10200,1200),clearance_m=1,total_years=10,interval_years=10)
    plain,_,_=advance_formation(source,start(source,cfg),cfg)
    pulsed,_,_=advance_formation(amended,start(amended,cfg),cfg)
    assert np.isclose(pulsed.mobile_solid_m3[cfg.inlet_zx],plain.mobile_solid_m3[cfg.inlet_zx],atol=1e-7)
    assert np.isclose(total(pulsed)-total(plain),1e7,rtol=1e-8)


def test_geometric_route_bridges_and_respects_barriers():
    cost = np.ones((12, 12))
    path = _route(cost, (1, 1), (9, 8))
    assert all(abs(a[0]-b[0])+abs(a[1]-b[1]) == 1 for a,b in zip(path,path[1:]))
    assert max(sum(1 for _ in group) for _, group in __import__('itertools').groupby(
        (b[0]-a[0], b[1]-a[1]) for a,b in zip(path,path[1:]))) <= 2
    cost[1:10, 5] = np.inf
    path = _route(cost, (2, 2), (2, 8))
    assert all(np.isfinite(cost[cell]) for cell in path)
    assert any(r >= 10 or r == 0 for r, _ in path)


def test_transit_is_time_limited_and_uses_wet_boundary():
    wet=np.ones((1,5),bool)
    seed=np.zeros_like(wet); seed[0,4]=True
    downstream,_=_ocean_transit_graph(wet,seed)
    stock=np.zeros((1,5)); stock[0,0]=100
    remaining,exported=_transit(stock,downstream,2,1,uniform=True)
    assert exported.sum()==0
    assert np.isclose(remaining.sum(),100)
    assert np.all(remaining[0,2:]==0)
    remaining,exported=_transit(stock,downstream,10,1,uniform=True)
    assert np.isclose(remaining.sum(),50)
    assert np.isclose(exported[0,4],50)
    assert np.count_nonzero(exported)==1


def test_finite_highwater_overbank_deposits_on_new_land_not_source_land():
    base=np.full((5,7),-1.); base[2,4]=.2
    seeds=np.zeros_like(base,bool); seeds[:,0]=True
    solid=np.zeros_like(base); solid[2,2]=1.2*6000
    state=make_state(base_bed_m=base,bed_solid_m3=solid,mobile_solid_m3=0,porosity=.4,
        valid_mask=True,ocean_seed_mask=seeds,spacing_m=100,origin_xz_m=(0,0),source_identity='overbank')
    source_wet,_=classify_ocean(replace(state,bed_solid_m3=np.zeros_like(solid)),0)
    wet,_=classify_ocean(state,1.); wet &= source_wet
    mobile=np.zeros_like(base);mobile[2,1]=10000
    stranded=np.zeros_like(base); stock=solid.copy();bed=state.bed_m.copy()
    _spread(mobile,stranded,wet,np.zeros_like(wet),np.full_like(base,-1),bed,stock,
            np.full_like(base,6000),DeltaConfig(),state,source_wet)
    assert bed[2,2] > state.bed_m[2,2]
    assert bed[2,4] == base[2,4]
    assert np.isclose(stock.sum()+mobile.sum()+stranded.sum(),solid.sum()+10000)


def test_centuries_inventory_does_not_bury_port_in_two_tides():
    source=load_state(SOURCE)
    cfg=DeltaConfig(formation_id='transit-event-regression',inlet_zx=(214,401),direction_xz=(10200,1200),
                    clearance_m=1,total_years=400,interval_years=20,solid_rate_m3_s=.08,extent_m=9000)
    formed,p,network=advance_formation(source,start(source,cfg),cfg,20)
    marine=MarineConfig(tide_amplitude_m=1,wave_height_m=1.5,wave_direction_xz=(-1,0),
        transport_rate_s=2e-5,entrainment_rate_s=1e-6,settling_rate_s=1e-5,
        export_rate_s=1e-6,step_s=1800,transverse_diffusivity_m2_s=30)
    event=advance(formed,[],90000,marine)
    wet,_=classify_ocean(event,0)
    assert wet[cfg.inlet_zx]
    assert max((event.bed_m-formed.bed_m)[source.valid_mask]) < 1
    assert formed.mobile_solid_m3.sum() < p['supply_solid_m3']*.01
    assert p['marine_transit']['exported_solid_m3'] > 0
    for key, volume in p['marine_transit']['boundary_export_m3'].items():
        row,col=map(int,key.split(':'))
        assert source.ocean_seed_mask[row,col] and volume>0
    assert np.isclose(total(formed)-total(source),p['supply_solid_m3'],rtol=1e-10)
    assert np.isclose(total(event),total(formed),rtol=1e-10)
    assert all(wet[cell] for cell in network['trunk'])
    from scipy import ndimage
    source_ocean,_=classify_ocean(source,0)
    before=source_ocean & (formed.bed_m>=0)
    after=source_ocean & (event.bed_m>=0)
    assert before.sum()>50
    assert after.sum()>=before.sum()*.8
    before_labels,_=ndimage.label(source.valid_mask & (formed.bed_m>=0))
    after_labels,_=ndimage.label(source.valid_mask & (event.bed_m>=0))
    before_attached=before & (before_labels==before_labels[213,400])
    after_attached=after & (after_labels==after_labels[213,400])
    assert after_attached.sum()>=before_attached.sum()*.8
    assert np.median(formed.bed_m[before])>.05
    assert np.max(np.abs(formed.bed_m[source.bed_m>=0]-source.bed_m[source.bed_m>=0]))<1e-8
