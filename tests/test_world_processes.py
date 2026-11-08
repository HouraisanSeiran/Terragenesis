"""World adapter tests exercise causality, budgets and persisted replay."""
import json
from types import SimpleNamespace
import sys

import numpy as np
import pytest

from terrain_pipeline import world_processes as processes
from terrain_pipeline.world_process_detail import apply_replacements


def test_saved_missing_integrated_flag_resumes_exact_legacy_identity(source,tmp_path):
    cfg=dict(shaping_rounds=2,equivalent_exposure_seconds=1000.)
    expected=processes.save_product(processes.compute(source,cfg),tmp_path/'whole-legacy')
    paused=processes.prepare(source,tmp_path/'resumed-legacy',dict(cfg,pause_after_round=1))
    assert paused['status']=='paused'
    checkpoint=json.loads((tmp_path/'resumed-legacy/checkpoint.json').read_text(encoding='utf8'))
    assert 'integrated_environment' not in checkpoint['config']
    actual=processes.resume(tmp_path/'resumed-legacy/checkpoint.json')
    assert actual['metadata']['algorithm']==processes.ALGORITHM
    assert actual['identity']==expected['identity']


@pytest.fixture
def source(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=16*2**30))
    def seasons(bed, **kwargs):
        climate = kwargs.get('climate') or {}
        rain = climate.get('rain_mm', 100.)
        local = np.full((12,) + bed.shape, rain / 1000 * kwargs['spacing_m'] ** 2)
        local[:, kwargs['ocean_mask']] = 0.
        return dict(arrays=dict(monthly_runoff_m3=local), state={}, metadata=dict(status='test-local-volume-driver'))
    monkeypatch.setitem(sys.modules, 'terrain_pipeline.world_environment', SimpleNamespace(run_seasons=seasons))
    import terrain_pipeline
    monkeypatch.setattr(terrain_pipeline, 'world_environment', sys.modules['terrain_pipeline.world_environment'], raising=False)
    shape = (8, 8)
    z, x = np.indices(shape)
    bed = 500. - z * 30 - x * 15
    ocean = np.zeros(shape, bool)
    ocean[-1] = True
    bed[-1] = -20.
    return dict(elevation_m=bed, ocean_mask=ocean, first_xz_m=[1000., 1000.], spacing_m=2000.,
                world_seed=20260903, source_identity='a' * 64,
                materials=dict(porosity=np.full(shape, .35), erodibility=np.full(shape, .8)))


def test_rain_material_and_inventory_causality(source):
    cfg = dict(shaping_rounds=2, equivalent_exposure_seconds=1e8)
    wet = processes.compute(source, cfg)
    dry = processes.compute(dict(source, climate=dict(rain_mm=0.)), cfg)
    hard = processes.compute(dict(source, materials=dict(porosity=.35, erodibility=0.)), cfg)
    bare = processes.compute(dict(source, initial_loose_thickness_m=0.), cfg)
    assert wet['arrays']['erosion_m'].sum() > 0
    assert dry['arrays']['erosion_m'].sum() == 0
    assert hard['arrays']['erosion_m'].sum() == 0
    assert bare['metadata']['solid_budget']['initial_loose_solid_m3'] == 0
    assert not np.array_equal(wet['arrays']['elevation_m'], bare['arrays']['elevation_m'])
    for result in (wet, dry, hard, bare):
        assert abs(result['metadata']['solid_budget']['residual_m3']) < 1e-5
        assert abs(result['metadata']['water_budget']['residual_m3']) < 1e-5
        np.testing.assert_array_equal(result['arrays']['elevation_m'][source['ocean_mask']], source['elevation_m'][source['ocean_mask']])


def test_persisted_resume_matches_continuous(source, tmp_path):
    continuous = processes.prepare(source, tmp_path / 'continuous', dict(shaping_rounds=3))
    paused = processes.prepare(source, tmp_path / 'resumed', dict(shaping_rounds=3, pause_after_round=1))
    assert paused['status'] == 'paused'
    completed = processes.resume(paused['checkpoint'])
    assert completed['identity'] == continuous['identity']
    left = processes.query(tmp_path / 'continuous', ['elevation_m', 'discharge_m3_s'])
    right = processes.query(tmp_path / 'resumed', ['elevation_m', 'discharge_m3_s'])
    for name in left['arrays']:
        np.testing.assert_array_equal(left['arrays'][name], right['arrays'][name])
    source_path = tmp_path / 'resumed/source_elevation_m.npy'
    source_path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='source changed'):
        processes.resume(paused['checkpoint'])


def test_query_never_prepares(source, tmp_path):
    with pytest.raises(FileNotFoundError):
        processes.query(tmp_path / 'missing')
    assert not (tmp_path / 'missing').exists()
    processes.prepare(source, tmp_path / 'world', dict(shaping_rounds=1))
    path = tmp_path / 'world/elevation_m.npy'
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='SHA'):
        processes.query(tmp_path / 'world', ['elevation_m'])


def test_unknown_rim_and_single_replacement(source):
    result = processes.compute(source, dict(shaping_rounds=1))
    assert result['metadata']['water_budget']['external_dependency_m3'] > 0
    assert len(result['details']) <= 4
    assert all(row['status'] == 'pending-terrain' for row in result['details'])
    coarse = dict(elevation_m=np.zeros((2, 2)))
    detail = dict(consumed_package_id='boundary-a', replaces_support_id='support-a', support_indices=[1], replacement_arrays=dict(elevation_m=[3.]))
    applied, consumed = apply_replacements(coarse, [detail])
    assert applied['elevation_m'].ravel()[1] == 3.
    assert coarse['elevation_m'].sum() == 0
    with pytest.raises(ValueError, match='twice'):
        apply_replacements(coarse, [detail], consumed_package_ids=consumed)


def test_explicit_materials_or_history_required(source):
    del source['materials']
    with pytest.raises(ValueError, match='history'):
        processes.compute(source)


def test_nested_history_and_bound_mesh_resume(source, tmp_path):
    from terrain_pipeline import drainage
    source['mesh'] = drainage.grid_mesh(source['elevation_m'].shape, x0_m=1000., z0_m=1000., dx_m=2000., world_seed=12345)
    # Serialization must preserve genuine nested geology arrays and mesh jitter,
    # even when they are not needed for this explicit-material scenario.
    source['geology_history'] = dict(arrays=dict(example=np.arange(4.)), metadata=dict(source='actual-initial'))
    paused = processes.prepare(source, tmp_path / 'nested', dict(shaping_rounds=2, pause_after_round=1))
    result = processes.resume(paused['checkpoint'])
    assert result['status'] == 'published-coarse'
    continuous=processes.prepare(source,tmp_path/'nested-continuous',dict(shaping_rounds=2))
    assert result['identity']==continuous['identity']


def test_lake_storage_limits_release_without_potential_water():
    from terrain_pipeline.world_process_hydrology import lake_balance
    bed=np.array([[0.,2.],[1.,3.]])
    filled=np.array([[2.,2.],[2.,3.]])
    labels=np.array([[1,0],[1,0]])
    receiver=np.array([1,-1,0,1],np.int64)
    order=np.array([1,0,2,3],np.int64)
    flow,water,ledger=lake_balance(np.zeros((2,2)),receiver,order,labels,bed,filled,1.)
    assert not np.isfinite(water).any()
    assert flow.sum()==0.
    flow,water,ledger=lake_balance(np.array([[1.,0.],[0.,0.]]),receiver,order,labels,bed,filled,1.)
    assert flow[1]==0.
    assert ledger['retained_m3']==1.
    assert ledger['final_storage_m3']==1.
    overflow,_,later=lake_balance(np.array([[4.,0.],[0.,0.]]),receiver,order,labels,bed,filled,1.,ledger['storage_by_pool_m3'])
    assert overflow[1]==2.
    assert later['final_storage_m3']==3.


def test_publish_does_not_mutate_and_refuses_overwrite(source,tmp_path):
    result=processes.compute(source,dict(shaping_rounds=1))
    elapsed=result['metadata']['cpu_seconds']
    processes.save_product(result,tmp_path/'published')
    assert result['metadata']['cpu_seconds']==elapsed
    with pytest.raises(FileExistsError):
        processes.save_product(result,tmp_path/'published')


def test_resource_gate_remains_explicit(source,tmp_path,monkeypatch):
    import psutil
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=1))
    with pytest.raises(MemoryError,match='memory gate'):
        processes.prepare(source,tmp_path/'too-small')
    assert not (tmp_path/'too-small').exists()


def test_geological_bed_is_causal_and_keeps_coarse_coast(source,monkeypatch):
    from terrain_pipeline import world_geology
    shape=source['elevation_m'].shape
    history=dict(arrays=dict(layer_top_m=np.ones((1,)+shape),
        geological_surface_m=source['elevation_m']+12.,final_layout_elevation_m=source['elevation_m']),
        metadata=dict(identity='history',origin_xz_m=[1000.,1000.],spacing_m=2000.,shape_zx=list(shape)))
    monkeypatch.setattr(world_geology,'sample_materials',lambda *args:source['materials'])
    generated=processes.compute(dict(source,geology_history=history,climate=dict(rain_mm=0.)),dict(shaping_rounds=1))
    a=generated['arrays']
    protected=a['protected_mask']
    np.testing.assert_array_equal(a['elevation_m'][~protected],source['elevation_m'][~protected]+12.)
    np.testing.assert_array_equal(a['elevation_m'][protected],source['elevation_m'][protected])
    assert a['geological_protection_adjustment_m'][protected].max()==-12.
    assert generated['metadata']['geological_bed_application']['applied_displacement_m3']>0


def test_environment_supplies_real_finite_stocks_once(source,monkeypatch,tmp_path):
    def seasons(src,bed,*args,**kwargs):
        shape=bed.shape
        weather=float(src.get('weather_depth',1e-6))
        return dict(arrays=dict(monthly_runoff_m3=np.zeros((12,)+shape),
            temperature_c=np.full(shape,10.),soil_water_mm=np.zeros(shape),cover_fraction=np.zeros(shape),
            monthly_weathered_rock_m=np.full((12,)+shape,weather),
            wind_x_m_s=np.full(shape,8.),wind_z_m_s=np.zeros(shape)),metadata={})
    monkeypatch.setattr(processes,'_seasons',seasons)
    source['initial_loose_thickness_m']=0.
    cfg=dict(shaping_rounds=2)
    wet=processes.compute(source,cfg)
    dry=processes.compute(dict(source,weather_depth=0.),cfg)
    assert wet['arrays']['rock_removed_m3'].sum()>0
    assert wet['arrays']['loose_solid_m3'].sum()>0
    assert dry['arrays']['loose_solid_m3'].sum()==0
    assert abs(wet['metadata']['solid_budget']['residual_m3'])<1e-6
    assert wet['metadata']['generation_environment']['solid_budget']['weathered_rock_m3']>0
    continuous=processes.prepare(source,tmp_path/'environment-continuous',cfg)
    paused=processes.prepare(source,tmp_path/'environment-resume',dict(cfg,pause_after_round=1))
    resumed=processes.resume(paused['checkpoint'])
    assert continuous['identity']==resumed['identity']


def test_environment_stage_reports_missing_wind_honestly(source, monkeypatch):
    def seasons(src, bed, *args, **kwargs):
        shape = bed.shape
        return dict(arrays=dict(monthly_runoff_m3=np.zeros((12,) + shape),
            temperature_c=np.full(shape, 10.), soil_water_mm=np.zeros(shape), cover_fraction=np.zeros(shape),
            monthly_weathered_rock_m=np.full((12,) + shape, 1e-6)), metadata={})
    monkeypatch.setattr(processes, '_seasons', seasons)
    result = processes.compute(source, dict(shaping_rounds=1))
    assert result['metadata']['generation_environment']['status'] == 'partial-or-pending'
    assert 'aeolian' in result['metadata']['generation_environment']['pending_processes']
    assert result['metadata']['stages']['environment'] == 'partial-or-pending'


def test_prepared_environment_regions_replace_matching_accounts(source, monkeypatch,tmp_path):
    def seasons(src, bed, *args, **kwargs):
        shape = bed.shape
        return dict(arrays=dict(monthly_runoff_m3=np.zeros((12,) + shape),
            temperature_c=np.full(shape, 10.), soil_water_mm=np.zeros(shape), cover_fraction=np.zeros(shape),
            monthly_weathered_rock_m=np.zeros((12,) + shape),
            wind_x_m_s=np.zeros(shape), wind_z_m_s=np.zeros(shape)), metadata={})
    monkeypatch.setattr(processes, '_seasons', seasons)
    shape = source['elevation_m'].shape
    height = source['elevation_m'].copy()
    ocean = source['ocean_mask'].copy()
    region = dict(id='aeolian-a', kind='aeolian', source_identity=source['source_identity'],
        context=dict(height_m=height, spacing_m=source['spacing_m'], ocean_mask=ocean),
        state=dict(loose_solid_m3=np.full(shape, 1e5), airborne_solid_m3=np.zeros(shape)),
        intervals=[dict(dt_s=600., forcing=dict(wind_x_m_s=np.full(shape, 8.), wind_z_m_s=np.zeros(shape),
            water_saturation=np.zeros(shape), vegetation_cover=np.zeros(shape)))])
    with pytest.raises(ValueError,match='initial inventory differs'):
        processes.compute(dict(source, environment_regions=[region], initial_loose_thickness_m=0.),
                          dict(shaping_rounds=1))
    region['state']['loose_solid_m3']=np.where(ocean,0.,source['spacing_m']**2*.65)
    result = processes.compute(dict(source, environment_regions=[region]),dict(shaping_rounds=1))
    rows = result['metadata']['generation_environment']['prepared_regions']
    assert rows[0]['status'] == 'computed'
    assert result['arrays']['loose_solid_m3'].sum() >= 0
    assert abs(result['metadata']['solid_budget']['residual_m3'])<1e-6
    processes.save_product(result,tmp_path/'prepared-environment')
    processes.query(tmp_path/'prepared-environment')


def test_actual_history_mesh_and_environment_resume(tmp_path,monkeypatch):

    import psutil
    from terrain_pipeline.world_geology import build_history
    from terrain_pipeline import drainage
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(available=16*2**30))
    z,x=np.indices((5,5))
    initial=dict(elevation_m=500.-z*80.-x*20.,continental_fraction=np.ones((5,5)),plate_id=np.zeros((5,5),int))
    final=dict(initial,elevation_m=initial['elevation_m']+50.)
    history=build_history(initial,final,world_seed=20260903,origin_xz_m=[0.,0.],spacing_m=2000.,stages=3,
        initial_source_identity='saved-initial',final_source_identity='saved-final')
    source=dict(elevation_m=final['elevation_m'],ocean_mask=np.zeros((5,5),bool),first_xz_m=[0.,0.],spacing_m=2000.,
        world_seed=20260903,source_identity='coarse-source',plate_identity='plate-source',geology_history=history,
        mesh=drainage.grid_mesh((5,5),x0_m=0.,z0_m=0.,dx_m=2000.,world_seed=99))
    continuous=processes.prepare(source,tmp_path/'actual-continuous',dict(shaping_rounds=2))
    paused=processes.prepare(source,tmp_path/'actual-resume',dict(shaping_rounds=2,pause_after_round=1))
    resumed=processes.resume(paused['checkpoint'])
    assert continuous['identity']==resumed['identity']
    product=processes.query(tmp_path/'actual-resume')
    assert product['metadata']['generation_environment']['solid_budget']['weathered_rock_m3']>0
    assert product['metadata']['plate_identity']=='plate-source'
    assert abs(product['metadata']['solid_budget']['residual_m3'])<1e-4
    assert (tmp_path/'actual-resume/geology-history.npz').is_file()


def test_detail_coast_refresh_does_not_turn_enclosed_bed_into_ocean(source):
    generated=processes.compute(source,dict(shaping_rounds=1))
    previous={name:value.copy() for name,value in generated['arrays'].items()}
    bed=np.full((8,8),100.)
    bed[:,0]=-1.
    bed[2,:4]=-1.
    previous['elevation_m']=bed.copy()
    arrays={name:value.copy() for name,value in previous.items()}
    arrays['ocean_mask']=bed<0
    arrays['elevation_m'][2,1]=1.
    processes._refresh_detail_world(arrays,generated['metadata'],None,previous)
    assert arrays['ocean_mask'][2,0]
    assert not arrays['ocean_mask'][2,2]
    assert not arrays['ocean_mask'][2,3]
    assert generated['metadata']['topology_refresh']['changed_land_cells']==3
    assert abs(generated['metadata']['water_budget']['residual_m3'])<1e-5


def test_lake_spinup_uses_its_own_runoff_and_output_initial_storage():
    bed=np.array([[0.,2.],[1.,3.]])
    route=SimpleNamespace(receiver=np.array([1,-1,0,1],np.int64),
        order=np.array([1,0,2,3],np.int64),filled=np.array([[2.,2.],[2.,3.]]))
    lakes=np.array([[1,0],[1,0]])
    warmup=np.zeros((12,2,2));warmup[0,0,0]=1.
    output=np.zeros((12,2,2));output[0,0,0]=4.
    seasonal=dict(arrays=dict(monthly_runoff_m3=output,spinup_monthly_runoff_m3=warmup))
    monthly,surface,ledger=processes._seasonal_lake_routing(seasonal,route,lakes,bed,
        np.zeros((2,2),bool),np.zeros((2,2),bool),1.)
    assert ledger['spinup']['months_completed']==12
    assert ledger['initial_storage_m3']==1.
    assert ledger['final_storage_m3']==3.
    assert ledger['local_runoff_m3']==4.
    assert ledger['external_dependency_m3']==2.
    assert monthly[0].ravel()[1]==2.
    assert ledger['residual_m3']==0.
