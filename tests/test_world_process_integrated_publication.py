"""New publication uses real small kernels; legacy identities stay separate."""
import json
from types import SimpleNamespace

import numpy as np

from terrain_pipeline import world_processes as world
from terrain_pipeline.world_environment_world import unpack_state


def source():
    z,x=np.indices((6,6))
    bed=100.-z*10.-x*3.
    ocean=z==5
    bed[ocean]=-10.
    shape=bed.shape
    return dict(elevation_m=bed,ocean_mask=ocean,first_xz_m=[0.,0.],spacing_m=2000.,
        world_seed=20260903,source_identity='small-source',materials=dict(porosity=np.full(shape,.35),
        erodibility=np.full(shape,.2),soil_thickness_m=np.full(shape,.3)),climate=dict(
        monthly_temperature_c=np.full((12,)+shape,5.),monthly_precipitation_mm=np.full((12,)+shape,50.),
        wind_x_m_s=np.zeros(shape),wind_z_m_s=np.zeros(shape)))


def config():
    return dict(integrated_environment=True,spinup_years=0,output_years=1,shaping_rounds=1,
        equivalent_exposure_seconds=100.,basin_preparation_seconds=900.,
        native_environment=dict(max_basin_cells=16),environment=dict(block_cells=12))


def assert_saved_lake_closure(arrays):
    total=lambda name:float(np.sum(arrays[name]))
    initial=total('lake_pre_native_initial_storage_m3')
    local=total('lake_pre_native_local_runoff_m3')
    before_native=total('lake_pre_native_final_storage_m3')
    pre_export=sum(total('lake_pre_native_'+name) for name in ('marine_export_m3','external_dependency_m3'))
    post_export=sum(total('lake_post_native_'+name) for name in ('marine_export_m3','external_dependency_m3'))
    final=total('final_lake_storage_m3')
    melt=total('native_glacier_runoff_m3')
    tolerance=1e-12*max(1.,initial+local+melt)
    assert abs(initial+local-before_native-pre_export)<tolerance
    assert abs(before_native+melt-final-post_export)<tolerance


def test_integrated_owners_native_climate_and_cold_read(tmp_path):
    result=world.compute(source(),config())
    arrays,metadata=result['arrays'],result['metadata']
    assert metadata['algorithm']==world.INTEGRATED_ALGORITHM
    initial={key for key in arrays if key.startswith('initial_owner__')}
    assert initial
    assert all('final_owner__'+key.removeprefix('initial_owner__') in arrays for key in initial)
    state=unpack_state(metadata['environment']['state_record'],arrays)
    assert state['integrated']['elapsed_s']==365*86400.
    assert state['weathering']
    assert metadata['environment']['environment_bed_commit']['status']=='committed'
    assert metadata['environment']['sea_preparation']['actual_consumer']['affected_cells']>0
    assert np.any(arrays['sea_air_temperature_feedback_c'])
    assert abs(metadata['solid_budget']['residual_m3']) < 1e-4
    assert abs(metadata['water_budget']['residual_m3']) < 1e-4
    assert arrays['initial_lake_storage_m3'].sum()==metadata['water_budget']['initial_storage_m3']==0.
    saved=world.save_product(result,tmp_path/'product')
    loaded=world.query(tmp_path/'product')
    assert_saved_lake_closure(loaded['arrays'])
    restored=unpack_state(loaded['metadata']['environment']['state_record'],loaded['arrays'])
    assert restored['integrated']['binding']==state['integrated']['binding']
    np.testing.assert_array_equal(restored['integrated']['water']['groundwater_m3'],state['integrated']['water']['groundwater_m3'])
    assert saved['identity']==loaded['identity']
    json.dumps(loaded['metadata'],allow_nan=False)
    assert 'costs' not in loaded['metadata']['environment']
    assert 'observed_costs' in saved['performance']
    # Supply one finite native coastal return in the exact shared schema. Its
    # previous interval is over; the next real annual daily owner consumes it.
    from terrain_pipeline.world_environment_world import pack_state
    from terrain_pipeline.common_infra import json_sha256
    prepared=unpack_state(metadata['native_environment']['prepared_record'],arrays)
    basin=prepared['state']['basin-0']
    packet=dict(schema='world-environment-exchange-v1',process='coast_soil_exchange',source_identity='small-source',
        parent_state_identity='finite-native-parent',parent_terrain_revision='prior-bed',support_global_ids=[0],
        mapping_weights=[1.],owner_from='coast-audit',owner_to='seasonal-soil',interval_start_s=0.,
        interval_end_s=365*86400.,quantities=dict(water_m3=5.,salt_kg=.1),
        source_debit=dict(status='debited',account_id='audit-stock'),status='in-flight',consumed_by=None)
    packet['id']=json_sha256(packet)
    basin['pending_packets'].append(packet)
    metadata['native_environment']['prepared_record']=pack_state(prepared,arrays,'native_prepared')
    with_return=world.save_product(result,tmp_path/'with-return')
    continued=world.continue_environment(tmp_path/'with-return',tmp_path/'next')
    next_product=world.query(tmp_path/'next')
    assert_saved_lake_closure(next_product['arrays'])
    next_state=unpack_state(next_product['metadata']['environment']['state_record'],next_product['arrays'])
    assert next_state['integrated']['elapsed_s']==2*365*86400.
    assert next_state['integrated']['handoffs']['consumed_ids']
    assert next_product['metadata']['continuation']['incoming_native_packet_ids']==next_state['integrated']['handoffs']['consumed_ids']
    assert continued['parent_product_identity']==with_return['identity']
    np.testing.assert_array_equal(next_product['arrays']['initial_owner__water__groundwater_m3'],
        loaded['arrays']['final_owner__water__groundwater_m3'])
    assert next_product['metadata']['environment']['state_rebase']['ownership'].startswith('all inventories')
    assert abs(next_product['metadata']['solid_budget']['residual_m3']) < 1e-4


def test_no_sea_status_survives_publication_and_continuation(tmp_path):
    inland=source()
    inland['ocean_mask']=np.zeros_like(inland['ocean_mask'])
    result=world.compute(inland,config())
    metadata=result['metadata']
    status=metadata['environment']['processes']['basin_water_heat']
    assert status==metadata['native_environment']['statuses']['basin_water_heat']
    assert status['status']=='not-triggered'
    assert metadata['environment']['sea_preparation']['actual_consumer']['affected_cells']==0
    assert not np.any(result['arrays']['sea_air_temperature_feedback_c'])
    world.save_product(result,tmp_path/'inland')
    world.continue_environment(tmp_path/'inland',tmp_path/'next')
    continued=world.query(tmp_path/'next')
    next_status=continued['metadata']['environment']['processes']['basin_water_heat']
    assert next_status==continued['metadata']['native_environment']['statuses']['basin_water_heat']
    assert next_status['status']=='not-triggered'
    assert not np.any(continued['arrays']['sea_air_temperature_feedback_c'])


def test_actual_mouth_water_and_river_solid_debit_and_metric_bed_coverage():
    from test_world_environment_native import coast_prepared,source as native_source
    from terrain_pipeline.world_environment_world import advance_native_world
    prepared,region=coast_prepared()
    region['node']=0
    region['context']['protected_mask'][:]=True
    region['context']['protected_mask'][region['context']['river_mask']]=False
    s=native_source()
    shape=s['elevation_m'].shape
    rec=np.full(shape,-1,np.int64)
    rec.flat[0]=8
    routed=np.zeros((1,)+shape)
    routed[0].flat[0]=30.
    routed[0].flat[8]=50.
    ocean=np.zeros(shape,bool)
    ocean.flat[8]=True
    s['ocean_mask']=ocean
    loose=np.zeros(shape)
    loose.flat[0]=100.
    marine=np.zeros(shape)
    marine.flat[8]=20.
    arrays=dict(receiver=rec,ocean_mask=ocean,lagoon_mask=np.zeros(shape,bool),
        monthly_routed_volume_m3=routed,loose_solid_m3=loose,marine_received_solid_m3=marine,
        elevation_m=s['elevation_m'].copy(),mobile_solid_m3=np.zeros(shape),rock_removed_m3=np.zeros(shape),
        monthly_runoff_m3=np.zeros_like(routed))
    seasonal=dict(state=dict(integrated=dict(elapsed_s=900.)))
    _,result,packets=advance_native_world(s,prepared,{'state':{}},arrays,seasonal,
        dict(output_years=900./(365*86400.)))
    river=[packet for packet in packets if packet['process']=='river_to_coast']
    assert sum(packet['quantities'].get('water_m3',0.) for packet in river)==30.
    assert sum(packet['quantities'].get('solid_m3',0.) for packet in river)==20.
    assert arrays['native_final_routed_marine_water_m3'].sum()==20.
    assert arrays['marine_received_solid_m3'].sum()==0.
    final=result['state']['coast-0']['core']['bed_solid_m3'].sum()
    assert arrays['loose_solid_m3'].sum()+final==120.
    expected=np.zeros(shape).ravel()
    for commit in result['bed_commit']:
        np.add.at(expected,commit['support_global_ids'],
            np.asarray(commit['bed_change_m'])*np.asarray(commit['mapping_weights']))
    np.testing.assert_array_equal(arrays['native_committed_bed_change_m'].ravel(),expected)
    assert np.any(expected)


def test_costs_are_observational_and_new_memory_estimate_is_explicit():
    metadata=dict(algorithm='x',environment=dict(costs=dict(wall_s=1.),state_binding='stable'),cpu_seconds=2.)
    a,costs=world._content_metadata(metadata)
    metadata['environment']['costs']['wall_s']=90.
    b,_=world._content_metadata(metadata)
    assert a==b and costs
    assert 'integrated_environment' not in world.plan(source(),{})['config']
    assert world.plan(source(),config())['estimated_memory_bytes']>world.plan(source(),{})['estimated_memory_bytes']


def test_lake_storage_survives_next_interval_and_changed_pool_capacity():
    from terrain_pipeline import drainage
    from terrain_pipeline import world_process_hydrology as hydro
    s=source()
    bed=np.full((6,6),20.)
    bed[2:4,2:4]=1.
    bed[-1]=-10.
    ocean=s['ocean_mask']
    lagoon=np.zeros_like(ocean)
    mesh=drainage.grid_mesh(bed.shape,x0_m=0.,z0_m=0.,dx_m=2000.,world_seed=20260903)
    route=hydro.routing(bed,ocean,lagoon,mesh)
    labels,_=drainage.pool_labels(bed.ravel(),route.filled.ravel(),mesh.indptr,mesh.indices)
    lakes=np.where(ocean.ravel(),0,labels+1).reshape(bed.shape)
    prior=np.zeros_like(bed)
    assert lakes[2,2]>0
    prior[2,2]=50.
    seasonal=dict(arrays=dict(monthly_runoff_m3=np.zeros((12,)+bed.shape)),state=dict(integrated={}))
    _,_,budget=world._seasonal_lake_routing(seasonal,route,lakes,bed,ocean,lagoon,2000.,prior)
    assert budget['initial_storage_m3']==50.
    assert budget['final_storage_m3']==50.
    assert abs(seasonal['arrays']['final_lake_storage_m3'].sum()-50.)<1e-10
    np.testing.assert_array_equal(seasonal['arrays']['initial_lake_storage_m3'],prior)
    # Removing the pool releases its actual water once instead of discarding it.
    no_pools=np.zeros_like(lakes)
    _,_,released=world._seasonal_lake_routing(seasonal,route,no_pools,bed,ocean,lagoon,2000.,prior)
    assert released['initial_storage_m3']==50.
    assert released['lake_stock_remap']['released_by_capacity_or_topology_m3']==50.
    assert abs(released['residual_m3'])<1e-8


def test_warm_lake_and_changed_topology_close_from_cold_saved_stage_arrays(tmp_path):
    from terrain_pipeline import drainage
    s=source()
    ocean=s['ocean_mask']
    lagoon=np.zeros_like(ocean)
    bed=np.full((6,6),20.)
    bed[2:4,2:4]=1.
    bed[ocean]=-10.
    mesh=drainage.grid_mesh(bed.shape,x0_m=0.,z0_m=0.,dx_m=2000.,world_seed=20260903)
    route=world.hydro.routing(bed,ocean,lagoon,mesh)
    labels,_=drainage.pool_labels(bed.ravel(),route.filled.ravel(),mesh.indptr,mesh.indices)
    lakes=np.where(ocean.ravel(),0,labels+1).reshape(bed.shape)
    warmup=np.zeros((12,)+bed.shape)
    warmup[0,2,2]=50.
    local=np.zeros_like(warmup)
    local[0,2,2]=7.
    local[0,0,0]=11.
    seasonal=dict(arrays=dict(spinup_monthly_runoff_m3=warmup,monthly_runoff_m3=local),state=dict(integrated={}))
    monthly,_,water=world._seasonal_lake_routing(seasonal,route,lakes,bed,ocean,lagoon,2000.)
    assert np.isclose(seasonal['arrays']['initial_lake_storage_m3'].sum(),50.,rtol=0.,atol=1e-10)
    assert np.isclose(seasonal['arrays']['lake_pre_native_final_storage_m3'].sum(),57.,rtol=0.,atol=1e-10)
    z,x=np.indices(bed.shape)
    changed=100.-z*10.-x*3.
    changed[ocean]=-10.
    next_route=world.hydro.routing(changed,ocean,lagoon,mesh)
    assert np.any(next_route.receiver!=route.receiver)
    labels,_=drainage.pool_labels(changed.ravel(),next_route.filled.ravel(),mesh.indptr,mesh.indices)
    next_lakes=np.where(ocean.ravel(),0,labels+1).reshape(bed.shape)
    glacier=np.zeros_like(bed)
    glacier[2,2]=3.
    arrays=dict(seasonal['arrays'],native_glacier_runoff_m3=glacier)
    _,_,water=world._post_native_lakes(seasonal,arrays,next_route,next_lakes,changed,ocean,lagoon,2000.,monthly,water)
    arrays.update(seasonal['arrays'])
    world.save_product(dict(arrays=arrays,metadata=dict(config={},water_budget=water),details=[]),tmp_path/'stages')
    cold=world.query(tmp_path/'stages')['arrays']
    initial=cold['lake_pre_native_initial_storage_m3'].sum()
    pre_final=cold['lake_pre_native_final_storage_m3'].sum()
    local_total=cold['lake_pre_native_local_runoff_m3'].sum()
    pre_export=sum(cold['lake_pre_native_'+name].sum() for name in ('marine_export_m3','external_dependency_m3'))
    post_export=sum(cold['lake_post_native_'+name].sum() for name in ('marine_export_m3','external_dependency_m3'))
    final=cold['final_lake_storage_m3'].sum()
    np.testing.assert_allclose([initial,pre_final,local_total],[50.,57.,18.],rtol=0.,atol=1e-10)
    assert abs(initial+local_total-pre_final-pre_export)<1e-8
    assert abs(pre_final+cold['native_glacier_runoff_m3'].sum()-final-post_export)<1e-8
    assert abs(initial+local_total+cold['native_glacier_runoff_m3'].sum()-final-pre_export-post_export)<1e-8


def test_integrated_round_resume_has_stable_content_identity(tmp_path,monkeypatch):
    import psutil
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=16*2**30))
    cfg=dict(config(),shaping_rounds=2)
    expected=world.save_product(world.compute(source(),cfg),tmp_path/'whole')
    paused=world.prepare(source(),tmp_path/'resume',dict(cfg,pause_after_round=1))
    assert paused['status']=='paused'
    resumed=world.resume(tmp_path/'resume/checkpoint.json')
    assert resumed['identity']==expected['identity']


def test_actual_manning_field_changes_the_existing_hydraulic_solution():
    from terrain_pipeline import drainage
    from terrain_pipeline.world_process_hydrology import representative_hydraulics
    s=source()
    mesh=drainage.grid_mesh((6,6),x0_m=0.,z0_m=0.,dx_m=2000.,world_seed=20260903)
    route=world.hydro.routing(s['elevation_m'],s['ocean_mask'],np.zeros((6,6),bool),mesh)
    q=np.full((6,6),10.)
    smooth=representative_hydraulics(s['elevation_m'],route.receiver,q,mesh,roughness=np.full((6,6),.02))
    rough=representative_hydraulics(s['elevation_m'],route.receiver,q,mesh,roughness=np.full((6,6),.08))
    flowing=smooth['depth_m']>0
    assert np.any(flowing)
    assert np.all(rough['depth_m'][flowing]>smooth['depth_m'][flowing])
