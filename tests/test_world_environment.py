import numpy as np

from terrain_pipeline.climate_forcing import advance_soil
from terrain_pipeline.runoff import RunoffParameters
from terrain_pipeline.world_environment import _constant_month_bucket, climate_fields, run_seasons


def test_accelerated_month_matches_existing_hourly_bucket():
    params = RunoffParameters()
    states = np.array([[30.,140.,1.],[1.,4.,8.],[10.,20.,0.]],np.float64)
    exact = states.copy()
    rain = np.array([100.,300.,.1]) / (31*24)
    pet = np.array([.15,.15,.15])
    runoff = np.zeros(3)
    et = np.zeros(3)
    for hour in range(31*24):
        exact, release, actual_et, change = advance_soil(rain,exact,dt_s=3600.,parameters=params)
        runoff += release
        et += actual_et
    actual_runoff,actual_et = _constant_month_bucket(rain*31*24,states,pet,31*24,15.,150.,1.,3600.,259200.)
    np.testing.assert_allclose(states,exact,atol=1e-11,rtol=1e-12)
    np.testing.assert_allclose(actual_runoff,runoff,atol=1e-10)
    np.testing.assert_allclose(actual_et,et,atol=1e-10)


def season(precip=100.,temperature=10.):
    shape = (2,2)
    climate = dict(arrays=dict(monthly_temperature_c=np.full((12,)+shape,temperature),
                               monthly_precipitation_mm=np.full((12,)+shape,precip)))
    return run_seasons(np.ones(shape)*100.,world_seed=20260903,first_xz_m=(1000.,1000.),
        spacing_m=2000.,ocean_mask=np.zeros(shape,bool),receiver=np.array([-1,0,0,1]),
        order=np.arange(4),lake_id=np.zeros(shape,int),materials=dict(erodibility=.5,porosity=.3),
        climate=climate,config=dict(spinup_years=1,output_years=1))


def test_causal_rain_and_water_account_separate_from_spinup():
    dry,wet = season(0.),season(100.)
    assert wet['arrays']['monthly_runoff_m3'].sum() > dry['arrays']['monthly_runoff_m3'].sum()
    assert dry['arrays']['monthly_runoff_m3'].sum() < 1e-3
    assert len(wet['metadata']['water_budget']['spinup']) == 12
    assert wet['arrays']['spinup_monthly_runoff_m3'].shape==(12,2,2)
    np.testing.assert_allclose(wet['arrays']['spinup_monthly_runoff_m3'].sum(axis=(1,2)),
        [row['local_runoff_m3'] for row in wet['metadata']['water_budget']['spinup']])
    for ledger in wet['metadata']['water_budget']['output']:
        assert abs(ledger['water_residual_m3']) < 1e-5
    volume = wet['arrays']['monthly_runoff_m3'][0].ravel().sum()
    assert abs(wet['arrays']['monthly_discharge_m3_s'][0].ravel()[0] *31*86400 - volume) < 1e-5


def test_snow_and_missing_processes_are_not_faked():
    cold = season(100.,-10.)
    assert cold['arrays']['monthly_snow_swe_mm'][-1].min() > 0
    assert cold['metadata']['processes']['glacier']['status'] == 'pending-preparation'
    assert cold['metadata']['processes']['groundwater']['status'] == 'pending-input'
    assert cold['metadata']['processes']['aeolian']['status'] == 'pending-input'


def test_climate_allocation_blocks_do_not_change_world_values():
    height = np.arange(12).reshape(3,4)*100.
    kw = dict(world_seed=20260903,first_xz_m=(1000.,1000.),spacing_m=2000.,ocean_mask=np.zeros((3,4),bool))
    a = climate_fields(height,config=dict(block_cells=2),**kw)
    b = climate_fields(height,config=dict(block_cells=262144),**kw)
    for name in a['arrays']:
        np.testing.assert_array_equal(a['arrays'][name],b['arrays'][name])
    assert a['metadata']['identity'] == b['metadata']['identity']


def test_saved_seasonal_stocks_continue_without_restarting_warmup():
    shape = (2,2)
    climate = dict(arrays=dict(monthly_temperature_c=np.full((12,)+shape,10.),
                               monthly_precipitation_mm=np.full((12,)+shape,100.)))
    kw = dict(world_seed=20260903,first_xz_m=(1000.,1000.),spacing_m=2000.,
        ocean_mask=np.zeros(shape,bool),receiver=np.array([-1,0,0,1]),order=np.arange(4),
        lake_id=np.zeros(shape,int),materials=dict(erodibility=.5,porosity=.3),climate=climate)
    full = run_seasons(np.ones(shape)*100.,config=dict(spinup_years=0,output_years=2),**kw)
    first = run_seasons(np.ones(shape)*100.,config=dict(spinup_years=0,output_years=1),**kw)
    second = run_seasons(np.ones(shape)*100.,config=dict(spinup_years=0,output_years=1),initial_state=first['state'],**kw)
    for name in ('monthly_runoff_m3','monthly_soil_water_mm','monthly_soil_thickness_m'):
        np.testing.assert_array_equal(full['arrays'][name][12:],second['arrays'][name])
    assert second['arrays']['temperature_c'].shape == shape
    np.testing.assert_array_equal(second['arrays']['precipitation_mm_yr'],np.full(shape,1200.))
