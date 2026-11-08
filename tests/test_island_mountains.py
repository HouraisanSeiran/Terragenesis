"""Declared analytic large-island fixtures; never a claim about the real world."""
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from terrain_pipeline.island_mountains import (
    IslandMountainConfig, IslandMountainPlan, analyze_island_mountains, blend_mountain_surface,
    load_mountain_plan, mountain_analysis_windows, sample_mountain_weights, save_mountain_plan,
)


def area_v2_plan(product):
    from terrain_pipeline.island_mountains import AREA_ALGORITHM, AREA_POLICY, identity
    plan=analyze_island_mountains(product)
    manifest=plan.manifest
    manifest.update(algorithm=AREA_ALGORITHM,blend_policy=AREA_POLICY,schema='island-mountain-plan-v2')
    manifest.pop('peak_normalization_required')
    manifest['identity']=identity({k:v for k,v in manifest.items() if k!='identity'})
    return IslandMountainPlan(manifest,plan.selected_interior,plan.coast_distance_m,plan.interior_distance_m)


def declared_product(kind='large'):
    def query(x, z):
        x, z = np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
        radius = 35000. if kind != 'small' else 2000.
        land = x*x+z*z <= radius**2
        lagoon = np.zeros(x.shape,bool)
        base = np.full(x.shape,-4000.)
        if kind == 'ring':
            lagoon = x*x+z*z < 25000.**2
            land &= ~lagoon
        if kind == 'thin':
            land = (abs(x)<60000)&(abs(z)<10000)
        if kind == 'mainland':
            base = np.where((x>0)&land,200.,base)
        if kind == 'edge':
            land = (x+90000)**2+z*z <= radius**2
        # A negative-water slit separates two apparent lobes despite overlapping
        # hypothetical feature support radii. Qualification uses actual land.
        if kind == 'channel':
            land &= abs(x)>2000
        height=500.*np.clip((radius-np.hypot(x,z))/1000.,0.,1.)
        if kind in ('thin','edge','channel'):
            height=np.full(x.shape,500.)
        return dict(elevation_m=np.where(land,height,-4000.),base_elevation_m=base,
                    protected=np.ones(x.shape,bool),lagoon=lagoon)
    return SimpleNamespace(identity=('a' if kind=='large' else 'b')*64,
        source=SimpleNamespace(identity='c'*64,bounds_m=(-100000.,-100000.,100000.,100000.)),
        config=SimpleNamespace(world_seed=20260903),query=query)


def test_default_area_only_and_optional_interior_width():
    p=declared_product();plan=analyze_island_mountains(p)
    assert not plan.empty and len(plan.manifest['selected_components'])==1
    row=plan.manifest['components'][0]
    assert 3800<row['exposed_area_km2']<3900
    assert row['usable_interior_max_inscribed_diameter_m']>50000
    assert plan.manifest['config']['analysis_spacing_m']==1000
    assert plan.manifest['config']['coast_buffer_m']==0
    assert plan.manifest['config']['min_usable_width_m']==0
    assert plan.manifest['config']['min_area_km2']==25
    assert not plan.manifest['qualification']['width_filter_enabled']
    assert plan.identity==analyze_island_mountains(p).identity
    changed=analyze_island_mountains(p,replace(IslandMountainConfig(),min_area_km2=5000))
    assert changed.empty and changed.identity!=plan.identity


@pytest.mark.parametrize('kind,reason',[('small','area-not-strictly-above-threshold'),
    ('thin','usable-interior-width-below-threshold'),('mainland','connected-to-original-land'),
    ('edge','finite-boundary'),('ring','registered-lagoon-rim'),('channel','area-not-strictly-above-threshold')])
def test_small_narrow_continental_edge_atoll_and_separate_channel_lobes_rejected(kind,reason):
    config=IslandMountainConfig()
    if kind=='thin':config=replace(config,min_usable_width_m=20000.)
    if kind=='channel':config=replace(config,min_area_km2=2000.)
    plan=analyze_island_mountains(declared_product(kind),config)
    assert plan.empty
    assert any(reason in r['exclusion_reasons'] for r in plan.manifest['components'])
    if kind=='channel':
        assert len(plan.manifest['components'])==2


def test_fixed_plan_samples_partition_order_coast_zero_and_raw_unchanged():
    product=declared_product();plan=area_v2_plan(product)
    x=np.linspace(-40000,40000,321);z=np.zeros_like(x)
    weights=sample_mountain_weights(plan,product,x,z)
    assert weights[160]==1 and not weights[abs(x)>=35000].any()
    assert np.all((weights>=0)&(weights<=1))
    assert np.max(abs(np.diff(weights)))<.55
    pieces=np.r_[sample_mountain_weights(plan,product,x[:127],z[:127]),
                 sample_mountain_weights(plan,product,x[127:],z[127:])]
    np.testing.assert_array_equal(weights,pieces)
    np.testing.assert_array_equal(weights[::-1],sample_mountain_weights(plan,product,x[::-1],z[::-1]))
    decoded=np.full(x.shape,-30.,np.float32);before=decoded.copy()
    final,w=blend_mountain_surface(plan,product,x,z,decoded)
    np.testing.assert_array_equal(decoded,before)
    base=product.query(x,z)['elevation_m'].astype(np.float32)
    np.testing.assert_array_equal(final[w==0],base[w==0])
    assert final[160]==2.


def test_frozen_plan_roundtrip_wrong_product_integrity_and_budget(tmp_path):
    product=declared_product();plan=analyze_island_mountains(product)
    path=tmp_path/'plan.npz';save_mountain_plan(plan,path)
    restored=load_mountain_plan(path,plan.identity,product)
    np.testing.assert_array_equal(restored.selected_interior,plan.selected_interior)
    original_identity=plan.identity
    altered=plan.manifest;altered['identity']='0'*64
    assert plan.identity==original_identity
    with pytest.raises(ValueError):plan.selected_interior.setflags(write=True)
    with pytest.raises(ValueError):plan.interior_distance_m.setflags(write=True)
    forged=IslandMountainPlan(altered,plan.selected_interior,plan.coast_distance_m,plan.interior_distance_m)
    with pytest.raises(ValueError,match='identity'):save_mountain_plan(forged,tmp_path/'forged.npz')
    with pytest.raises(FileExistsError):save_mountain_plan(plan,path)
    with pytest.raises(ValueError,match='another'):load_mountain_plan(path,plan.identity,declared_product('small'))
    with pytest.raises(ValueError,match='identity'):load_mountain_plan(path,'0'*64,product)
    with np.load(path) as a:arrays={k:a[k] for k in a.files}
    arrays['coast_distance_m'][50,50]+=1
    np.savez(tmp_path/'bad.npz',**arrays)
    with pytest.raises(ValueError,match='integrity'):load_mountain_plan(tmp_path/'bad.npz',plan.identity,product)
    with pytest.raises(ValueError,match='budget'):
        analyze_island_mountains(product,replace(IslandMountainConfig(),max_analysis_cells=4))


def test_dense_selected_interior_boundary_profile_is_continuous():
    product=declared_product();plan=analyze_island_mountains(product)
    x=np.linspace(15000.,35000.,20001);z=np.zeros_like(x)
    weights=sample_mountain_weights(plan,product,x,z)
    assert weights[0]==1 and weights[-1]==0
    assert np.max(abs(np.diff(weights)))<.01
    # Every fixed-grid boundary has matching left/right limits, including the
    # selected-interior boundary rather than only the coast-distance ramp.
    boundaries=np.arange(15000.,35000.,1000.)
    left=sample_mountain_weights(plan,product,boundaries-1e-5,np.zeros_like(boundaries))
    right=sample_mountain_weights(plan,product,boundaries+1e-5,np.zeros_like(boundaries))
    np.testing.assert_allclose(left,right,rtol=0,atol=1e-7)


def test_product_query_budget_batches_and_actual_plan_cli(tmp_path,monkeypatch):
    product=declared_product();query=product.query;calls=[]
    product.config.max_query_points=127
    def limited(x,z):
        size=np.broadcast_arrays(x,z)[0].size
        assert size<=127
        calls.append(size)
        return query(x,z)
    product.query=limited
    plan=analyze_island_mountains(product)
    assert calls and max(calls)<=127 and not plan.empty
    tool=Path(__file__).resolve().parents[1]/'tools/prepare_island_mountains.py'
    spec=importlib.util.spec_from_file_location('declared_plan_tool',tool)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'load_product',lambda *args:product)
    path=tmp_path/'from-tool.npz'
    assert module.main(['--islands','declared','--expected-island-identity',product.identity,'--out',str(path)])==0
    assert load_mountain_plan(path,plan.identity,product).identity==plan.identity


def cell_island(cell_count, *, thin=False):
    product=declared_product()
    def query(x,z):
        x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
        # Exact connected fixed-grid fixture with arbitrary cell count.
        ix=np.floor(x/1000).astype(int);iz=np.floor(z/1000).astype(int)
        if thin:
            land=(ix>=0)&(ix<cell_count)&(iz==0)
        else:
            side=int(np.sqrt(cell_count))
            land=((ix>=0)&(ix<side)&(iz>=0)&(iz<cell_count//side))
            land|=(ix>=0)&(ix<cell_count%side)&(iz==cell_count//side)
        return dict(elevation_m=np.where(land,500.,-4000.),base_elevation_m=np.full(x.shape,-4000.),
                    protected=np.ones(x.shape,bool),lagoon=np.zeros(x.shape,bool))
    product.query=query
    product.source.bounds_m=(-20000.,-20000.,150000.,30000.) if thin else (-20000.,-20000.,30000.,30000.)
    return product


@pytest.mark.parametrize('threshold,excluded,accepted',[(25,25,26),(25,100,101),(100,100,101)])
def test_strict_area_boundaries_and_no_second_width_gate(threshold,excluded,accepted):
    config=IslandMountainConfig(min_area_km2=threshold)
    exact=analyze_island_mountains(cell_island(excluded),config)
    assert exact.manifest['components'][0]['exposed_area_km2']==excluded
    assert exact.empty == (excluded<=threshold)
    if exact.empty:
        assert 'area-not-strictly-above-threshold' in exact.manifest['components'][0]['exclusion_reasons']
    product=cell_island(accepted);plan=analyze_island_mountains(product,config)
    assert not plan.empty and plan.manifest['components'][0]['exposed_area_km2']==accepted
    assert sample_mountain_weights(plan,product,np.array([500.]),np.array([500.]))[0]>0
    thin=cell_island(101,thin=True);thin_plan=analyze_island_mountains(thin)
    assert not thin_plan.empty and thin_plan.manifest['components'][0]['exposed_area_km2']==101
    assert sample_mountain_weights(thin_plan,thin,np.array([50500.]),np.array([500.]))[0]>0
    buffered=analyze_island_mountains(product,IslandMountainConfig(coast_buffer_m=20000))
    assert not buffered.empty  # Protection is allowed to reduce weights, not area qualification.


def test_height_taper_zero_at_sea_and_continuous_small_island_coast_raw_unchanged():
    product=declared_product('small')
    # radius 6km is ~112km2, above the new threshold.
    query=product.query
    def small_query(x,z):
        x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float));r=np.hypot(x,z)
        out=query(x,z);out['elevation_m']=np.where(r<=6000,500*np.clip((6000-r)/1000,0,1),-4000.)
        return out
    product.query=small_query;plan=area_v2_plan(product)
    assert not plan.empty
    x=np.linspace(0,6100,6101);z=np.zeros_like(x)
    weights=sample_mountain_weights(plan,product,x,z)
    assert weights[0]>0 and not weights[x>=6000].any()
    assert max(abs(np.diff(weights)))<.01
    decoded=np.full(x.shape,1200.,np.float32);original=decoded.copy()
    h,w=blend_mountain_surface(plan,product,x,z,decoded)
    np.testing.assert_array_equal(decoded,original)
    np.testing.assert_array_equal(h[w==0],product.query(x,z)['elevation_m'].astype(np.float32)[w==0])


def test_legacy_plan_read_only_exact_profile_and_versioned_identity(tmp_path):
    path=Path(__file__).with_name('fixtures')/'island-mountain-plan-v1.npz'
    golden=json.loads(path.with_suffix('.json').read_text())
    product=declared_product();legacy=load_mountain_plan(path,golden['identity'],product)
    x=np.linspace(golden['profile_start'],golden['profile_stop'],golden['profile_count'])
    weights=sample_mountain_weights(legacy,product,x,np.zeros_like(x))
    assert hashlib.sha256(weights.tobytes()).hexdigest()==golden['weights_sha256']
    assert legacy.identity==golden['identity']
    current=analyze_island_mountains(product)
    assert current.identity!=legacy.identity
    assert current.manifest['blend_policy']!=legacy.manifest['blend_policy']
    with pytest.raises(ValueError,match='read-only'):save_mountain_plan(legacy,tmp_path/'legacy.npz')


def grouped_product():
    product=declared_product()
    product.features=tuple(SimpleNamespace(feature_id=str(i),center_x_m=x,center_z_m=0.,support_radius_m=9000.)
                           for i,x in enumerate((-40000.,40000.)))
    def query(x,z):
        x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
        r=np.minimum(np.hypot(x+40000,z),np.hypot(x-40000,z))
        return dict(elevation_m=np.where(r<=6000,500*np.clip((6000-r)/1000,0,1),-4000.),
                    base_elevation_m=np.full(x.shape,-4000.),protected=r<9000,
                    lagoon=np.zeros(x.shape,bool))
    product.query=query
    return product


def test_fixed_full_support_windows_match_whole_domain_and_outside_zero(tmp_path):
    product=grouped_product();full=analyze_island_mountains(product)
    windows=mountain_analysis_windows(product,tile_margin_m=15360.)
    assert len(windows)==2 and all(row['status']=='ready' for row in windows)
    x=np.linspace(-100000,99999,4000);z=np.zeros_like(x)
    total=np.zeros_like(x);accepted_area=0
    for i,row in enumerate(windows):
        cfg=replace(IslandMountainConfig(),analysis_bounds_m=row['bounds_m'])
        local=analyze_island_mountains(product,cfg)
        assert not local.empty and local.manifest['grid']['bounds_m']==row['bounds_m']
        path=tmp_path/f'window{i}.npz';save_mountain_plan(local,path)
        loaded=load_mountain_plan(path,local.identity,product)
        total+=sample_mountain_weights(loaded,product,x,z)
        outside=sample_mountain_weights(loaded,product,np.array([-1e7,1e7]),np.zeros(2))
        assert not outside.any()
        accepted_area+=sum(r['exposed_area_km2'] for r in local.manifest['components'] if r['accepted'])
    np.testing.assert_array_equal(total,sample_mountain_weights(full,product,x,z))
    assert accepted_area==sum(r['exposed_area_km2'] for r in full.manifest['components'] if r['accepted'])
    with pytest.raises(ValueError,match='align'):
        analyze_island_mountains(product,replace(IslandMountainConfig(),analysis_bounds_m=(-51001.,-10000.,-29000.,10000.)))
    with pytest.raises(ValueError,match='support'):
        analyze_island_mountains(product,replace(IslandMountainConfig(),analysis_bounds_m=(-44000.,-10000.,-30000.,10000.)))
    # Identity-valid but source-misaligned windows must also fail on cold load.
    with np.load(tmp_path/'window0.npz') as a:arrays={k:a[k] for k in a.files}
    manifest=json.loads(str(arrays['manifest_json']));manifest['grid']['bounds_m'][0]+=1
    from terrain_pipeline.island_mountains import identity
    manifest['identity']=identity({k:v for k,v in manifest.items() if k!='identity'})
    arrays['manifest_json']=np.array(json.dumps(manifest));np.savez(tmp_path/'bad-window.npz',**arrays)
    with pytest.raises(ValueError):load_mountain_plan(tmp_path/'bad-window.npz',manifest['identity'],product)


def test_large_domain_windows_allocate_no_full_grid_and_oversize_is_explicit():
    product=grouped_product();product.source.bounds_m=(-5000000.,-5000000.,5000000.,5000000.)
    calls=[];query=product.query
    def counted(x,z):calls.append(np.broadcast_arrays(x,z)[0].size);return query(x,z)
    product.query=counted
    windows=mountain_analysis_windows(product)
    assert len(windows)==2 and not calls
    assert sum(r['analysis_cells'] for r in windows)<1000
    with pytest.raises(ValueError,match='budget'):analyze_island_mountains(product)
    assert not calls
    for row in windows:
        assert not analyze_island_mountains(product,replace(IslandMountainConfig(),analysis_bounds_m=row['bounds_m'])).empty
    pending=mountain_analysis_windows(product,replace(IslandMountainConfig(),max_analysis_cells=100))
    assert all(row['status']=='pending-analysis' and row['reason'] for row in pending)
    with pytest.raises(ValueError,match='budget'):
        analyze_island_mountains(product,replace(IslandMountainConfig(),max_analysis_cells=100,
                                                analysis_bounds_m=pending[0]['bounds_m']))
    # Expanded tile-margin windows merge instead of double-consuming a field.
    merged=mountain_analysis_windows(product,tile_margin_m=50000.)
    assert len(merged)==1 and merged[0]['feature_ids']==['0','1']


def test_explicit_old_threshold_cold_load_and_existing_peak_targets(tmp_path):
    product=cell_island(101)
    old=analyze_island_mountains(product,IslandMountainConfig(min_area_km2=100))
    new=analyze_island_mountains(product)
    assert old.identity!=new.identity
    assert old.manifest['components'][0]['peak_height_target_m']==new.manifest['components'][0]['peak_height_target_m']
    path=tmp_path/'old-threshold.npz'
    save_mountain_plan(old,path)
    restored=load_mountain_plan(path,old.identity,product)
    assert restored.manifest['config']['min_area_km2']==100
    assert restored.manifest==old.manifest
    assert analyze_island_mountains(cell_island(26),IslandMountainConfig(min_area_km2=100)).empty
