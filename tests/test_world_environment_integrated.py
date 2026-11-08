import numpy as np
import pytest
import json
from pathlib import Path

from terrain_pipeline.world_environment import run_seasons
from terrain_pipeline.world_environment_coupling import global_groundwater, prepare_snow_history, radiation_month
from terrain_pipeline.world_environment_state import flatten_arrays
from terrain_pipeline.common_infra import json_sha256
from terrain_pipeline.environment_processes import frozen_ground_step, radiation_step
from terrain_pipeline.world_environment_coupling import _freeze_global
from terrain_pipeline.world_environment_coupling import _cap_face_roundoff
from terrain_pipeline.world_environment_coupling import longwave_exchange,thermal_scenario_parameters


def run(years=1, initial=None, temperature=10., precipitation=100., environment=None):
    shape = (2,2)
    return run_seasons(np.array([[100.,102.],[104.,106.]]),world_seed=20260903,
        first_xz_m=(1000.,1000.),spacing_m=2000.,ocean_mask=np.zeros(shape,bool),
        receiver=np.array([-1,0,0,1]),order=np.arange(4),lake_id=np.full(shape,-1),
        materials=dict(porosity=.3,permeability_m2=1e-13),
        climate=dict(arrays=dict(monthly_temperature_c=np.full((12,)+shape,temperature),
            monthly_precipitation_mm=np.full((12,)+shape,precipitation))),
        config=dict(integrated_environment=True,spinup_years=0,output_years=years,
                    environment=dict(output_fields='all',**(environment or {}))),initial_state=initial)


def test_water_and_solutes_are_owned_and_accounted():
    result = run()
    for row in result['metadata']['water_budget']['output']:
        assert abs(row['water_residual_m3'])<1e-6
    arrays,state = result['arrays'],result['state']['integrated']
    assert arrays['monthly_groundwater_recharge_m3'].sum()>0
    assert arrays['monthly_groundwater_baseflow_m3'].sum()>0
    assert np.all(arrays['monthly_groundwater_baseflow_m3']<=arrays['monthly_runoff_m3']+1e-8)
    assert np.all(result['state']['soil_fast_slow_mm'][2]==0)
    assert state['routed_exports']['salt_kg'].sum()>0
    for category in ('chemistry','ecology','thermal','habitat'):
        for row in result['metadata']['process_budgets'][category]:
            for name,value in row.items():
                if 'residual' in name:
                    tolerance = max(1e-3,abs(row.get('heat_input_j',0.))*1e-12)
                    assert abs(value)<tolerance,(category,name,value)
    assert arrays['root_cohesion_pa'].max()>0
    np.testing.assert_allclose(arrays['root_cohesion_pa'],arrays['cover_fraction']*6000)


def test_continuation_is_bitwise_same_and_inputs_are_not_aliased():
    full,first = run(2),run()
    snapshots = {k:v.copy() for k,v in flatten_arrays(first['state']).items()}
    second = run(initial=first['state'])
    for name,value in flatten_arrays(full['state']).items():
        np.testing.assert_array_equal(value,flatten_arrays(second['state'])[name])
    for name,value in snapshots.items():
        np.testing.assert_array_equal(value,flatten_arrays(first['state'])[name])
    for name in ('monthly_runoff_m3','monthly_biomass_carbon_kg','monthly_soil_salt_kg'):
        np.testing.assert_array_equal(full['arrays'][name][12:],second['arrays'][name])
    with pytest.raises(ValueError,match='binding'):
        run(initial=first['state'],temperature=11.)


def test_global_shared_faces_transport_water_and_tracers_once():
    water = np.array([[1.,0.,0.]])
    salt = np.array([[2.,0.,0.]])
    nutrient = np.array([[.1,0.,0.]])
    result = global_groundwater(water,dict(salt_kg=salt,nutrient_kg=nutrient),
        np.zeros_like(water),np.ones_like(water),np.ones_like(water),
        np.array([0,1]),np.array([1,2]),1.,1.,np.full_like(water,100.),1e30)
    np.testing.assert_allclose(water,[[0.,1.,0.]],atol=1e-20)
    np.testing.assert_allclose(salt,water*2)
    np.testing.assert_allclose(nutrient,water*.1)
    assert abs(result['water_residual_m3'])<1e-12


def test_30m_multiface_donor_exhaustion_never_exports_negative_baseflow():
    # Eight simultaneously capped physical faces previously summed a few ulps
    # above this donor's stock, producing a negative aquifer drain at 30m.
    water=np.zeros((1,9))
    water[0,0]=.1
    tracers=dict(salt_kg=water.copy()*3.,nutrient_kg=water.copy()*.02)
    initial_salt=float(tracers['salt_kg'].sum())
    result=global_groundwater(water,tracers,np.array([[100.]+[0.]*8]),
        np.full_like(water,.2),np.linspace(.01,.03,9).reshape(water.shape),
        np.zeros(8,dtype=int),np.arange(1,9),30.**2,86400.,
        np.full_like(water,100.),np.full_like(water,90*86400.),np.linspace(.5,1.5,8))
    assert np.all(result['baseflow_m3']>=0.)
    assert np.all(water>=0.)
    assert all(np.all(pool>=0.) for pool in tracers.values())
    assert float(water.sum()+result['baseflow_m3'].sum())==pytest.approx(.1,abs=1e-16)
    assert result['donor_roundoff_transfer_reduction_m3']>0.
    assert abs(result['tracer_residual_kg']['salt_kg'])<=4*np.spacing(initial_salt)
    assert float(tracers['salt_kg'].sum()+result['exports']['salt_kg'].sum())==pytest.approx(initial_salt,abs=4*np.spacing(initial_salt))


def test_shared_face_roundoff_cap_progresses_for_subnormal_inventory():
    quantum=np.nextafter(0.,1.)
    amounts,remaining,reduction=_cap_face_roundoff(np.full(3,quantum),np.zeros(3,dtype=int),np.array([2*quantum]))
    assert remaining[0]==0.
    assert reduction==quantum
    assert np.all(amounts>=0.)


def test_ten_year_sparse_snow_history_replays_global_supports():
    shape=(2,2)
    kwargs=dict(temperature_c=np.full((12,)+shape,-10.),precipitation_mm=np.full((12,)+shape,100.),
        spacing_m=2000.,ocean_mask=np.zeros(shape,bool))
    summary=prepare_snow_history(**kwargs)
    selected=prepare_snow_history(**kwargs,support_ids=[3,0])
    assert summary['history']['swe_mm'].shape==(120,0)
    assert selected['history']['swe_mm'].shape==(120,2)
    np.testing.assert_array_equal(summary['terminal_swe_mm'],selected['terminal_swe_mm'])
    np.testing.assert_array_equal(selected['history']['swe_mm'][-1],selected['terminal_swe_mm'].ravel()[[3,0]])
    assert np.all(summary['last_five_year_minimum_swe_mm']>0)


def test_cold_state_has_causal_frozen_infiltration_and_bounded_radiation():
    cold=run(temperature=-60.,precipitation=0.)
    assert cold['arrays']['monthly_ground_ice_m'].max()>0
    assert cold['arrays']['monthly_infiltration_factor'].min()<1
    dark=radiation_month(np.zeros((2,2)),2000.,0,np.zeros((2,2),bool))
    assert not dark['absorbed_shortwave_w_m2'].any()


def test_saved_actual_cold_td_forcing_retains_water_and_freezes():
    fixture=json.loads((Path(__file__).parent/'fixtures/cold_td_environment_20261108.json').read_text(encoding='utf-8'))
    a={k:np.asarray(v,float) for k,v in fixture['fields'].items()}
    shape=a['elevation_m'].shape
    result=run_seasons(a['elevation_m'],world_seed=fixture['world_seed'],first_xz_m=fixture['first_xz_m'],
        spacing_m=30.,ocean_mask=np.zeros(shape,bool),receiver=np.full(a['elevation_m'].size,-1),
        order=np.arange(a['elevation_m'].size),lake_id=np.full(shape,-1),
        materials={k:a[k] for k in ('porosity','permeability_m2','erodibility','bed_hardness','solubility')},
        climate=dict(arrays={k:a[k] for k in ('monthly_temperature_c','monthly_precipitation_mm')}),
        config=dict(integrated_environment=True,spinup_years=0,output_years=1,environment=dict(output_fields='all')))
    assert result['arrays']['monthly_ground_ice_m'].max()>0
    assert result['arrays']['monthly_infiltration_factor'].min()<1
    assert result['arrays']['monthly_soil_water_mm'].max()>0
    assert result['arrays']['monthly_soil_temperature_c'].min()<0
    for name,row in result['metadata']['independent_accounts'].items():
        if isinstance(row,dict):
            assert abs(row['residual'])<1e-10*max(1.,abs(row['initial']),abs(row['external_input']),abs(row['external_output'])),(name,row)


def test_longwave_exchange_uses_kelvin_and_finite_declared_parameters():
    parameters,soil=thermal_scenario_parameters({})
    assert soil['field_capacity_fraction']==.6
    surface=np.array([[0.,10.]])
    down,up=longwave_exchange(surface,surface,dict(parameters,sky_emissivity=1.),np.ones(surface.shape,bool))
    np.testing.assert_array_equal(down,up)
    cold_down,warm_up=longwave_exchange(surface,np.full(surface.shape,-10.),parameters,np.ones(surface.shape,bool))
    assert np.all(cold_down<warm_up)
    assert np.all(warm_up>300.)
    with pytest.raises(ValueError,match='emissivity'):
        thermal_scenario_parameters(dict(thermal_parameters=dict(sky_emissivity=1.1)))
    with pytest.raises(ValueError,match='field_capacity'):
        thermal_scenario_parameters(dict(soil_water_parameters=dict(field_capacity_fraction=-.1)))


def test_independent_accounts_include_true_initial_arrays_and_external_fluxes():
    result=run()
    assert 'initial_owner__water__root_liquid_m' in result['arrays']
    for key,row in result['metadata']['independent_accounts'].items():
        if isinstance(row,dict):
            scale=max(1.,abs(row['initial']),abs(row['external_input']))
            assert abs(row['residual'])<scale*1e-11,(key,row)
    assert result['metadata']['independent_accounts']['carbon']['external_input']>0
    assert result['metadata']['processes']['disturbance']['status']=='not-triggered'
    for name,direction in (('energy_input_j','external_input'),('energy_output_j','external_output')):
        assert result['arrays']['cumulative_external__'+name].sum()==pytest.approx(
            result['metadata']['independent_accounts']['energy'][direction],rel=1e-13)


def test_native_packets_are_time_bound_and_consumed_once_across_resume():
    first=run()
    packet=dict(schema='world-environment-exchange-v1',process='coast_to_soil',
        source_identity=first['state']['integrated']['binding'],parent_state_identity='native-state',
        parent_terrain_revision=None,owner_from='coast-1',owner_to='seasonal-soil',
        source_debit=dict(status='debited',account_id='native-debit-1'),
        interval_start_s=365*86400,interval_end_s=365*86400+10*86400,
        support_global_ids=[0],mapping_weights=[1.],status='in-flight',consumed_by=None,
        quantities=dict(water_m3=100.,salt_kg=2.,nutrient_kg=.1,organic_carbon_kg=1.,sensible_heat_j=200.))
    packet['id']=json_sha256(packet)
    second=run(initial=first['state'],environment=dict(native_exchange=[packet]))
    assert second['state']['integrated']['handoffs']['consumed_ids']==[packet['id']]
    assert second['metadata']['independent_accounts']['water']['external_input']>19200000
    third=run(initial=second['state'],environment=dict(native_exchange=[packet]))
    assert third['state']['integrated']['handoffs']['consumed_ids']==[packet['id']]
    assert third['metadata']['independent_accounts']['salt']['external_input']==0
    for key,row in second['metadata']['independent_accounts'].items():
        if isinstance(row,dict):
            assert abs(row['residual'])<max(1.,abs(row['external_input']),abs(row['initial']))*1e-11,(key,row)


def test_signed_freeze_adapter_matches_original_positive_forcing_kernel():
    shape=(2,2)
    water=dict(root_liquid_m=np.full(shape,.03),ground_ice_m=np.zeros(shape),snow_swe_m=np.full(shape,.1))
    thermal=dict(soil_temperature_c=np.zeros(shape),thaw_time_s=np.zeros(shape),frozen_time_s=np.zeros(shape))
    context=dict(height_m=np.ones(shape),spacing_m=2000.,ocean_mask=np.zeros(shape,bool))
    core_state=dict(liquid_water_m=water['root_liquid_m'],ground_ice_m=water['ground_ice_m'],snow_swe_m=water['snow_swe_m'],**thermal)
    core=frozen_ground_step(core_state,dict(air_temperature_c=10.,ground_heat_w_m2=20.,geothermal_heat_w_m2=.06),context,86400.)
    state=dict(water=water,thermal=thermal)
    flux,_=_freeze_global(state,np.full(shape,10.),np.full(shape,20.),np.full(shape,.06),context,1)
    np.testing.assert_array_equal(core['state']['liquid_water_m'],water['root_liquid_m'])
    np.testing.assert_array_equal(core['state']['snow_swe_m'],water['snow_swe_m'])
    np.testing.assert_array_equal(core['state']['soil_temperature_c'],thermal['soil_temperature_c'])
    np.testing.assert_array_equal(core['fluxes']['height_change_m'],flux['height_change_m'])


def test_bounded_radiation_matches_core_when_world_fits_horizon():
    height=np.array([[100.,103.],[102.,110.]])
    context=dict(height_m=height,spacing_m=2000.)
    expected=np.zeros(height.shape)
    for phase in range(4):
        result=radiation_step(dict(absorbed_energy_j_m2=np.zeros(height.shape)),
            dict(time_s=(15+(phase+.5)/4)*86400.-.5),context,1.)
        expected+=result['fluxes']['absorbed_shortwave_w_m2']/4
    actual=radiation_month(height,2000.,0,np.ones(height.shape,bool))
    np.testing.assert_allclose(actual['absorbed_shortwave_w_m2'],expected,rtol=1e-14)


def test_midmonth_event_is_consumed_once_and_historical_supply_is_ignored():
    first=run()
    event=dict(id='current-eruption-1',kind='volcanism',start_s=365*86400+15*86400,
        source_binding=first['state']['integrated']['binding'],age_ma=0.,global_cell_ids=[0],
        lava_input_m3=1.,ash_input_m3=.1)
    historic=dict(event,id='historical-eruption',age_ma=2.)
    second=run(initial=first['state'],environment=dict(dated_events=[event,historic]))
    stocks=second['state']['integrated']
    assert stocks['events']['consumed_ids']==[event['id']]
    assert stocks['volcanism']['deposited_lava_m3'].sum()==pytest.approx(1.)
    assert sum(row['event_input_solid_m3'] for row in second['metadata']['process_budgets']['volcanism'])==pytest.approx(1.1)
    third=run(initial=second['state'])
    assert third['state']['integrated']['volcanism']['deposited_lava_m3'].sum()==pytest.approx(1.)
    bad=dict(event,id='bad-time',start_s=1.)
    with pytest.raises(ValueError,match='daily boundary'):
        run(initial=first['state'],environment=dict(dated_events=[bad]))


def test_global_habitat_adapter_matches_core_canonical_shared_capacity():
    from terrain_pipeline.drainage import grid_mesh
    from terrain_pipeline.environment_processes import advance_habitat
    from terrain_pipeline.world_environment_coupling_habitat import advance_global_habitat
    shape=(3,3)
    mesh=grid_mesh(shape,x0_m=1000.,z0_m=-1000.,dx_m=100.,world_seed=20260903)
    source=np.repeat(np.arange(9),np.diff(mesh.indptr))
    context=dict(height_m=np.arange(9,dtype=float).reshape(shape),spacing_m=100.,
        world_seed=20260903,origin_native_xz=mesh.origin_native_xz,receiver=np.full(shape,-1),
        valid_mask=np.ones(shape,bool),ocean_mask=np.zeros(shape,bool),river_mask=np.zeros(shape,bool),
        protected_mask=np.zeros(shape,bool),graph_edge_source=source,graph_edge_target=mesh.indices,
        node_x_m=mesh.node_x_m.reshape(shape),node_z_m=mesh.node_z_m.reshape(shape))
    state=dict(population_individuals=np.array([[5.,0.,10.],[0.,0.,0.],[1.,0.,3.]]),occupancy_s=np.zeros(shape))
    forcing=dict(vegetation_cover_fraction=np.full(shape,.8),water_available_fraction=np.full(shape,.7),
        disturbance_fraction=np.zeros(shape),water_temperature_c=np.full(shape,15.))
    expected=advance_habitat(state,forcing,context,86400.)
    actual=advance_global_habitat(state,forcing,context,mesh,86400.)
    for category in ('state','fluxes'):
        for name,value in expected[category].items():
            np.testing.assert_allclose(actual[category][name],value,rtol=1e-13,atol=1e-12)


def test_default_diagnostics_are_bounded_and_blocks_preserve_state():
    all_fields=run()
    kwargs=dict(integrated_environment=True,spinup_years=0,output_years=1,
        environment=dict(block_cells=1))
    shape=(2,2)
    small=run_seasons(np.array([[100.,102.],[104.,106.]]),world_seed=20260903,
        first_xz_m=(1000.,1000.),spacing_m=2000.,ocean_mask=np.zeros(shape,bool),
        receiver=np.array([-1,0,0,1]),order=np.arange(4),lake_id=np.full(shape,-1),
        materials=dict(porosity=.3,permeability_m2=1e-13),
        climate=dict(arrays=dict(monthly_temperature_c=np.full((12,)+shape,10.),
            monthly_precipitation_mm=np.full((12,)+shape,100.))),config=kwargs)
    assert 'monthly_biomass_carbon_kg' not in small['arrays']
    assert 'biomass_carbon_kg' in small['arrays']
    for name,value in flatten_arrays(all_fields['state']).items():
        np.testing.assert_array_equal(value,flatten_arrays(small['state'])[name])


def test_disturbance_event_is_single_finite_fraction():
    first=run()
    event=dict(id='fire-midmonth',kind='fire',start_s=365*86400+15*86400,
        source_binding=first['state']['integrated']['binding'],age_ma=0.,global_cell_ids=[0],fraction=.5)
    result=run(initial=first['state'],environment=dict(dated_events=[event]))
    assert result['state']['integrated']['events']['consumed_ids']==[event['id']]
    assert result['metadata']['processes']['disturbance']['status']=='computed'
    assert result['arrays']['cumulative_external__fire_atmosphere_carbon_kg'][0,0]>0
    assert result['arrays']['cumulative_external__fire_atmosphere_carbon_kg'][1,1]==0
    resumed=run(initial=result['state'])
    assert resumed['arrays']['cumulative_external__fire_atmosphere_carbon_kg'].sum()==0
