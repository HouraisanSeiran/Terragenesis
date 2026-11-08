"""Detailed preparation proves real solver use, source binding and single supply."""
import json
from pathlib import Path

import numpy as np
import pytest

from terrain_pipeline.common_infra import file_sha256, json_sha256
from terrain_pipeline import world_processes as processes
from terrain_pipeline.world_process_detail import boundary_package, validate_boundary, load_native_terrain, solve_native_reach


def coarse_product():
    shape=(8,8)
    bed=np.full(shape,200.)
    arrays=dict(elevation_m=bed.copy(),initial_elevation_m=bed+1.,discharge_m3_s=np.ones(shape),
        generation_transported_solid_m3=np.full(shape,10.),loose_solid_m3=np.full(shape,2e5),
        porosity=np.full(shape,.35),erodibility=np.full(shape,.2))
    receiver=np.arange(64,dtype=np.int64)+1
    receiver[-1]=-1
    arrays.update(receiver=receiver.reshape(shape),ocean_mask=np.zeros(shape,bool),lake_id=np.zeros(shape,np.int32))
    metadata=dict(source_identity='a'*64,world_seed=20260903,spacing_m=2000.,first_xz_m=[1000.,1000.],
        config=dict(shaping_rounds=16,equivalent_exposure_seconds=1e8,rock_reserve_m=1.,roughness=.04),
        stages=dict(detailed='pending'))
    arrays.update(initial_loose_solid_m3=arrays['loose_solid_m3'].copy(),rock_removed_m3=np.zeros(shape),
        mobile_solid_m3=np.zeros(shape),marine_received_solid_m3=np.zeros(shape),external_dependency_solid_m3=np.zeros(shape))
    metadata['solid_budget']=dict(initial_loose_solid_m3=float(arrays['loose_solid_m3'].sum()),
        final_loose_solid_m3=float(arrays['loose_solid_m3'].sum()),rock_removed_m3=0.,final_mobile_solid_m3=0.,
        marine_received_solid_m3=0.,external_dependency_solid_m3=0.,residual_m3=0.)
    return dict(arrays=arrays,metadata=metadata,identity='b'*64,details=[])


def native_fixture(tmp_path):
    # A declared synthetic native fixture verifies adapters; it is not a model
    # terrain acceptance result and is labelled accordingly in its generator.
    root=tmp_path/'native';root.mkdir()
    zz,xx=np.indices((513,513))
    bed=(300.-.03*xx-.06*zz).astype(np.float32)
    np.save(root/'elevation.npy',bed)
    m=dict(schema='terragenesis-local30-v1',ready=True,plate_identity='a'*64,world_seed=20260903,
        generator=dict(kind='synthetic-test-fixture-not-model-inference'),
        grid=dict(first_sample_xz_m=[1000.,1000.],spacing_m=30.,shape_zx=[513,513]),
        layers=dict(elevation_m=dict(file='elevation.npy',sha256=file_sha256(root/'elevation.npy'))))
    m['identity']=json_sha256(m)
    (root/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
    entry=dict(manifest_path=str(root/'manifest.json'),manifest_sha256=file_sha256(root/'manifest.json'))
    return entry


def test_boundary_carries_actual_rate_once_and_rejects_tampering():
    p=coarse_product();r=dict(node=9,coarse_support_id='support')
    b=boundary_package(p,r,'terrain',duration_s=2.)
    assert b['water_m3']==2.
    assert b['solid_m3']==10./(16*1e8)*2.
    validate_boundary(b,source_identity='a'*64,terrain_identity='terrain')
    b['water_m3']+=1.
    with pytest.raises(ValueError,match='identity'):
        validate_boundary(b,source_identity='a'*64,terrain_identity='terrain')


def test_native_source_binding_and_real_solver(tmp_path):
    entry=native_fixture(tmp_path)
    with pytest.raises(ValueError,match='another world'):
        load_native_terrain(entry,source_identity='z'*64)
    t=load_native_terrain(entry,source_identity='a'*64)
    r=dict(id='region',node=9,coarse_support_id='support',kind='river_reach',location_xz_m=[3000.,3000.])
    result=solve_native_reach(coarse_product(),r,t,config=dict(detail_duration_s=2.,max_detail_nodes=8))
    assert result['hydraulic']['metadata']['status']=='complete'
    assert result['sediment']['metadata']['status']=='complete'
    assert len(result['native_arrays']['node'])==8
    assert result['budgets']['boundary_water_m3']==pytest.approx(result['budgets']['solver_water_input_m3'])
    assert result['budgets']['boundary_solid_m3']==pytest.approx(result['budgets']['solver_external_solid_m3'])
    assert result['replacement_arrays']['elevation_m'].size>0
    dry_supply=coarse_product()
    dry_supply['arrays']['generation_transported_solid_m3'][:]=0.
    no_sand=solve_native_reach(dry_supply,r,t,config=dict(detail_duration_s=2.,max_detail_nodes=8))
    assert no_sand['budgets']['solver_external_solid_m3']==0.
    assert result['sediment']['arrays']['step_external_solid_m3'].sum()>0.


def test_pending_batch_preserves_preview_and_publishes_new_identity(tmp_path):
    p=coarse_product()
    p['details']=[dict(id='region',node=9,coarse_support_id='support',kind='river_reach',
        location_xz_m=[3000.,3000.],status='pending-terrain')]
    processes.save_product(p,tmp_path/'preview')
    result=processes.continue_details(tmp_path/'preview',tmp_path/'fine',terrain_entries=[])
    assert result['details'][0]['status']=='pending-terrain'
    np.testing.assert_array_equal(processes.query(tmp_path/'preview')['arrays']['elevation_m'],
                                  processes.query(tmp_path/'fine')['arrays']['elevation_m'])
    assert result['identity']!=processes.query(tmp_path/'preview')['identity']


def test_forged_manifest_and_checkpoint_are_rejected(tmp_path):
    p=coarse_product();processes.save_product(p,tmp_path/'preview')
    path=tmp_path/'preview'/'manifest.json';m=json.loads(path.read_text())
    m['metadata']['source_identity']='forged';path.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='manifest identity'):
        processes.query(path.parent)


def test_completed_batch_keeps_actual_traces_and_cold_read_checks(tmp_path):
    p=coarse_product()
    p['details']=[dict(id='region',node=9,coarse_support_id='support',kind='river_reach',
        location_xz_m=[3000.,3000.],status='pending-terrain')]
    entry=native_fixture(tmp_path)
    processes.save_product(p,tmp_path/'preview')
    result=processes.continue_details(tmp_path/'preview',tmp_path/'fine',terrain_entries=[entry],
        config=dict(detail_duration_s=2.,max_detail_nodes=8))
    assert result['details'][0]['status']=='complete'
    assert len(result['consumed_package_ids'])==1
    assert abs(result['metadata']['solid_budget']['residual_m3'])<1e-6
    assert result['detail_files']
    processes.query(tmp_path/'fine')
    path=tmp_path/'fine'/'detail-region'/'sediment.npz'
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='detail file SHA'):
        processes.query(tmp_path/'fine')


def test_distinct_plate_identity_is_preserved_and_checked(tmp_path):
    p=coarse_product()
    p['metadata']['plate_identity']='a'*64
    p['metadata']['source_identity']='c'*64
    p['details']=[dict(id='region',node=9,coarse_support_id='support',kind='river_reach',
        location_xz_m=[3000.,3000.],status='pending-terrain')]
    processes.save_product(p,tmp_path/'preview')
    result=processes.continue_details(tmp_path/'preview',tmp_path/'fine',terrain_entries=[native_fixture(tmp_path)],
        config=dict(detail_duration_s=2.,max_detail_nodes=8))
    assert result['details'][0]['status']=='complete'
    assert result['metadata']['source_identity']=='c'*64
    assert result['metadata']['plate_identity']=='a'*64
    assert result['metadata']['topology_refresh']['status']=='complete'
    assert abs(result['metadata']['water_budget']['residual_m3'])<1e-5
    a=processes.query(tmp_path/'fine')['arrays']
    assert a['monthly_routed_volume_m3'].shape==(12,8,8)
    np.testing.assert_allclose(a['discharge_m3_s'],a['monthly_routed_volume_m3'].sum(axis=0)/(365*86400))
    from terrain_pipeline.climate_forcing import MONTH_DAYS
    np.testing.assert_allclose(a['monthly_discharge_m3_s']*np.asarray(MONTH_DAYS)[:,None,None]*86400,
        a['monthly_routed_volume_m3'])


def test_unknown_downstream_boundary_is_not_invented(tmp_path):
    terrain=load_native_terrain(native_fixture(tmp_path),source_identity='a'*64)
    product=coarse_product()
    product['arrays']['receiver'][:]=-1
    r=dict(id='region',node=9,coarse_support_id='support',kind='river_reach',location_xz_m=[3000.,3000.])
    with pytest.raises(ValueError,match='continuation required'):
        solve_native_reach(product,r,terrain,config=dict(detail_duration_s=2.,max_detail_nodes=8))
