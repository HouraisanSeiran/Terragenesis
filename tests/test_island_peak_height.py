"""Whole-component native peaks, seam invariance and incomplete raw coverage."""
import hashlib
from types import SimpleNamespace
import numpy as np
import pytest
from terrain_pipeline.island_mountains import (
    IslandMountainConfig, analyze_island_mountains, peak_height_for_area,
    component_native_tiles, PeakNormalizationBuilder, apply_peak_surface,
)


def fixture():
    def query(x,z):
        x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
        r=np.hypot(x,z)
        return dict(elevation_m=np.where(r<6500,500*np.clip((6500-r)/1000,0,1),-4000.),
            base_elevation_m=np.full(x.shape,-4000.),lagoon=np.zeros(x.shape,bool),protected=r<6500)
    p=SimpleNamespace(identity='a'*64,source=SimpleNamespace(identity='b'*64,
        bounds_m=(-30000.,-30000.,30000.,30000.)),config=SimpleNamespace(world_seed=20260903),query=query)
    return p,analyze_island_mountains(p)


def tiles(plan,constant=False):
    result=[]
    for ix,iz in component_native_tiles(plan,plan.manifest['selected_components'][0]):
        x=(ix*512+np.arange(513)[None,:])*30.
        z=(iz*512+np.arange(513)[:,None])*30.
        raw=np.full((513,513),1000.,np.float32) if constant else (1000+.01*x+.03*z).astype(np.float32)
        result.append((ix,iz,raw))
    return result


def normalize(plan,p,values):
    records=[dict(ix=ix,iz=iz,identity='c'*64,elevation_sha256=hashlib.sha256(raw.tobytes()).hexdigest()) for ix,iz,raw in values]
    b=PeakNormalizationBuilder(plan,p,records)
    for ix,iz,raw in values:b.observe_raw(ix,iz,raw)
    for ix,iz,raw in reversed(values):b.observe_scale(ix,iz,raw)
    return b.finalize()


def test_area_curve_bounds_determinism_and_config():
    for area in (25,26,50,100):
        assert peak_height_for_area(area,ripple_fraction=0)==300
        assert 270<=peak_height_for_area(area)<=330
    assert peak_height_for_area(100,ripple_fraction=0)==300
    assert peak_height_for_area(2000,ripple_fraction=0)==3000
    assert peak_height_for_area(5000,ripple_fraction=0)==3000
    values=[peak_height_for_area(a,ripple_fraction=0) for a in (100,200,500,1000,2000)]
    assert values==sorted(values)
    assert peak_height_for_area(150,seed=20260903,island_key='fixed')==peak_height_for_area(150,seed=20260903,island_key='fixed')
    for a in (100,150,500,2000,5000):
        h=peak_height_for_area(a)
        assert 270<=h<=3300
    assert IslandMountainConfig(min_area_km2=5000).min_area_km2==5000
    with pytest.raises(ValueError):peak_height_for_area(float('nan'))
    with pytest.raises(ValueError):peak_height_for_area(100,min_m=4000,max_m=3000)


@pytest.mark.parametrize('constant',[False,True])
def test_complete_component_peak_raw_immutable_and_shared_edges(constant):
    p,plan=fixture();values=tiles(plan,constant);norm=normalize(plan,p,values)
    row=norm['components'][0];assert row['status']=='ready'
    surfaces={};peak=-np.inf
    for ix,iz,raw in values:
        before=raw.tobytes()
        x=(ix*512+np.arange(513)[None,:])*30.;z=(iz*512+np.arange(513)[:,None])*30.
        h,w=apply_peak_surface(plan,p,norm,x,z,raw)
        base=p.query(x,z)['elevation_m'].astype(np.float32)
        np.testing.assert_array_equal(h[w==0],base[w==0])
        assert before==raw.tobytes()
        peak=max(peak,float(h.max()));surfaces[ix,iz]=h
    assert peak==pytest.approx(row['effective_peak_m'],abs=.001)
    for (ix,iz),h in surfaces.items():
        if (ix+1,iz) in surfaces:np.testing.assert_array_equal(h[:,-1],surfaces[ix+1,iz][:,0])
        if (ix,iz+1) in surfaces:np.testing.assert_array_equal(h[-1],surfaces[ix,iz+1][0])


def test_incomplete_component_retains_base_and_tampering_rejected():
    p,plan=fixture();values=tiles(plan)[:1];norm=normalize(plan,p,values)
    assert norm['components'][0]['status']=='pending'
    ix,iz,raw=values[0];x=(ix*512+np.arange(513)[None,:])*30.;z=(iz*512+np.arange(513)[:,None])*30.
    h,w=apply_peak_surface(plan,p,norm,x,z,raw)
    assert not w.any()
    np.testing.assert_array_equal(h,p.query(x,z)['elevation_m'].astype(np.float32))
    norm['components'][0]['status']='ready'
    with pytest.raises(ValueError,match='identity'):apply_peak_surface(plan,p,norm,x,z,raw)
