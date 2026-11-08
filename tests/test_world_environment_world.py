import numpy as np
import pytest

from terrain_pipeline import drainage
from terrain_pipeline.world_environment_world import generation_environment


def data():
    shape=(6,6)
    z,x=np.indices(shape)
    bed=10000.-z*1800.-x*100.
    ocean=np.zeros(shape,bool)
    mesh=drainage.grid_mesh(shape,x0_m=1000.,z0_m=1000.,dx_m=2000.,world_seed=20260903)
    outlets=np.zeros(shape,bool);outlets[-1]=True
    route=drainage.route_graph(bed,outlets,mesh)
    source=dict(elevation_m=bed,spacing_m=2000.,world_seed=20260903,source_identity='world-env-test',
        first_xz_m=[1000.,1000.],ocean_mask=ocean,receiver=route.receiver.reshape(shape),mesh=mesh,
        loose_solid_m3=np.full(shape,1e5))
    seasonal=dict(arrays=dict(temperature_c=np.full(shape,10.),soil_water_mm=np.zeros(shape),
        cover_fraction=np.zeros(shape),wind_x_m_s=np.full(shape,8.),wind_z_m_s=np.zeros(shape),
        monthly_weathered_rock_m=np.full((12,)+shape,1e-6)))
    return source,dict(porosity=np.full(shape,.35)),seasonal


def test_finite_causal_wind_and_slope_close_solid_account():
    source,materials,seasonal=data()
    result=generation_environment(source,materials,seasonal)
    assert result['arrays']['aeolian_entrained_solid_m3'].sum()>0
    assert result['arrays']['mass_mobilized_solid_m3'].sum()>0
    assert abs(result['metadata']['solid_budget']['solid_residual_m3'])<1e-7
    wet=dict(arrays=dict(seasonal['arrays'],soil_water_mm=np.full((6,6),150.)))
    suppressed=generation_environment(source,materials,wet)
    assert suppressed['arrays']['aeolian_entrained_solid_m3'].sum()==0
    assert np.all(source['loose_solid_m3']==1e5)


def test_blocks_own_donors_and_exchange_halos_once():
    source,materials,seasonal=data()
    small=generation_environment(source,materials,seasonal,config=dict(environment_block_rows=1,environment_pair_block=2))
    large=generation_environment(source,materials,seasonal,config=dict(environment_block_rows=100,environment_pair_block=8192))
    for name in small['arrays']:
        np.testing.assert_allclose(small['arrays'][name],large['arrays'][name],rtol=1e-14,atol=1e-9)
    assert small['metadata']['solid_budget']['solid_residual_m3']==large['metadata']['solid_budget']['solid_residual_m3']


def test_empty_material_and_zero_weathering_supply_no_sand():
    source,materials,seasonal=data()
    source['loose_solid_m3'][:]=0.
    seasonal['arrays']['monthly_weathered_rock_m'][:]=0.
    result=generation_environment(source,materials,seasonal)
    assert result['arrays']['mass_mobilized_solid_m3'].sum()==0
    assert result['arrays']['aeolian_entrained_solid_m3'].sum()==0
    assert result['arrays']['height_change_m'].sum()==0
    assert result['metadata']['processes']['volcanism']['status']=='not-triggered'


def test_unconsumed_current_volcanic_event_uses_real_kernel_and_own_stock():
    from terrain_pipeline import environment_processes as kernels
    source,materials,seasonal=data()
    context=dict(height_m=source['elevation_m'],spacing_m=2000.,receiver=source['receiver'],
        valid_mask=np.ones((6,6),bool),protected_mask=np.zeros((6,6),bool),ocean_mask=source['ocean_mask'])
    source['current_volcanic_event']=dict(context=context,state=kernels.volcanism_initialize(context),
        forcing=dict(lava_input_m3=np.eye(6)*10.,ash_input_m3=0.,wind_x_m_s=0.,wind_z_m_s=0.,geothermal_w_m2=.05),
        source_identity='actual-geological-event',event_identity='geology-current-eruption',age_ma=0.)
    result=generation_environment(source,materials,seasonal)
    assert result['metadata']['processes']['volcanism']['status']=='computed'
    assert result['metadata']['volcanic_budget']['event_input_solid_m3']==60.
    assert abs(result['metadata']['volcanic_budget']['solid_residual_m3'])<1e-9
    assert result['arrays']['volcanic_deposited_lava_m3'].sum()>0.
    assert result['arrays']['volcanic_height_change_m'].sum()>0.
    context['height_m']=context['height_m']+1.
    with pytest.raises(ValueError,match='bind the actual bed'):
        generation_environment(source,materials,seasonal)


def test_no_wind_keeps_slope_marine_and_export_accounts_separate():
    source,materials,seasonal=data()
    seasonal['arrays'].pop('wind_x_m_s')
    seasonal['arrays'].pop('wind_z_m_s')
    source['ocean_mask'][-1]=True
    result=generation_environment(source,materials,seasonal)
    assert result['arrays']['marine_received_solid_m3'].sum()>0.
    assert result['arrays']['boundary_export_solid_m3'].sum()==0.
    assert result['arrays']['airborne_solid_m3'].sum()==0.
    assert abs(result['metadata']['solid_budget']['solid_residual_m3'])<1e-7


def test_receivers_and_work_configuration_reject_invented_support():
    source,materials,seasonal=data()
    with pytest.raises(ValueError,match='positive integer'):
        generation_environment(source,materials,seasonal,config=dict(environment_block_rows=.5))
    source['receiver']=source['receiver'].copy()
    source['receiver'][0,0]=source['elevation_m'].size
    with pytest.raises(ValueError,match='actual metric mesh'):
        generation_environment(source,materials,seasonal)


def test_weathering_debits_only_available_bedrock():
    source,materials,seasonal=data()
    source['rock_remaining_m3']=np.full((6,6),2.)
    seasonal['arrays']['monthly_weathered_rock_m'][:]=1.
    result=generation_environment(source,materials,seasonal)
    assert np.all(result['arrays']['weathered_rock_m3']==2.)
    assert result['metadata']['weathering_supply']['reserve_limited_cells']==36
    assert abs(result['metadata']['solid_budget']['solid_residual_m3'])<1e-7
    source['rock_remaining_m3'][:]=0.
    empty=generation_environment(source,materials,seasonal)
    assert empty['arrays']['weathered_rock_m3'].sum()==0.
    assert empty['arrays']['dissolved_solid_m3'].sum()==0.
