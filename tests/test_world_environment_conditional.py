import numpy as np
import pytest

from terrain_pipeline import environment_processes as kernels
from terrain_pipeline.world_environment_conditional import run_conditional_processes, advance_native_glacier


def context():
    shape = (3, 3)
    return dict(height_m=np.arange(9, dtype=float).reshape(shape)[::-1].copy(),
                spacing_m=2000., world_seed=20260903, origin_native_xz=(0, 0),
                receiver=np.full(shape, -1, np.int64), valid_mask=np.ones(shape, bool),
                protected_mask=np.zeros(shape, bool), ocean_mask=np.zeros(shape, bool),
                river_mask=np.zeros(shape, bool))


def test_aeolian_runs_only_with_explicit_finite_inventory_and_closes_account():
    ctx = context()
    loose = np.zeros((3, 3))
    loose[1, 1] = 20.
    forcing = dict(wind_x_m_s=8., wind_z_m_s=0., water_saturation=0., vegetation_cover=0.)
    data = dict(aeolian=dict(state=kernels.aeolian_initialize(ctx, loose_solid_m3=loose),
                            forcing=forcing, source_identity='finite-sand-source', grain_provenance='declared sand fraction'))
    actual = run_conditional_processes(ctx, data, dt_s=600.)
    result = actual['results']['aeolian']
    assert actual['processes']['aeolian']['status'] == 'computed'
    assert result['fluxes']['entrained_solid_m3'].sum() > 0.
    assert abs(result['ledger']['solid_residual_m3']) < 1e-12
    wet = dict(aeolian=dict(data['aeolian'], forcing=dict(forcing, water_saturation=1.)))
    blocked = run_conditional_processes(ctx, wet, dt_s=600.)
    assert blocked['results']['aeolian']['fluxes']['entrained_solid_m3'].sum() == 0.
    np.testing.assert_array_equal(data['aeolian']['state']['loose_solid_m3'], loose)


def test_volcanic_supply_requires_dated_geological_event_and_is_finite():
    ctx = context()
    forcing = dict(lava_input_m3=np.eye(3)*10., ash_input_m3=0., wind_x_m_s=0., wind_z_m_s=0., geothermal_w_m2=.05)
    supplied = dict(state=kernels.volcanism_initialize(ctx), forcing=forcing, source_identity='magmatic-source')
    pending = run_conditional_processes(ctx, dict(volcanism=supplied), dt_s=600.)
    assert pending['processes']['volcanism']['status'] == 'pending-input'
    prepared = run_conditional_processes(ctx, dict(volcanism=dict(supplied, event_identity='geology-049-volcanism')), dt_s=600.)
    result = prepared['results']['volcanism']
    assert result['ledger']['event_input_solid_m3'] == 30.
    assert abs(result['ledger']['solid_residual_m3']) < 1e-12
    assert result['fluxes']['height_change_m'].sum() > 0.


def test_frozen_ground_uses_prepared_energy_and_water_inventory():
    ctx = context()
    initial = kernels.frozen_ground_initialize(ctx, liquid_water_m=.1, soil_temperature_c=0.)
    result = run_conditional_processes(ctx, dict(frozen_ground=dict(state=initial,
        source_identity='bound-soil-column', forcing=dict(air_temperature_c=-10., ground_heat_w_m2=0., geothermal_heat_w_m2=.05))),dt_s=86400.)
    frozen = result['results']['frozen_ground']
    assert frozen['state']['ground_ice_m'].sum() > 0.
    np.testing.assert_allclose(frozen['state']['ground_ice_m']+frozen['state']['liquid_water_m'],.1)


def test_missing_unknown_and_untriggered_processes_are_explicit():
    ctx = context()
    missing = run_conditional_processes(ctx, {}, dt_s=600.)
    assert missing['processes']['groundwater']['status'] == 'pending-input'
    with pytest.raises(ValueError, match='unknown'):
        run_conditional_processes(ctx, dict(invented={}),dt_s=600.)
    skipped = run_conditional_processes(ctx, dict(aeolian=dict(status='not-triggered',reason='no exposed loose sand')),dt_s=600.)
    assert skipped['processes']['aeolian']['reason'] == 'no exposed loose sand'


def test_glacier_native_support_keeps_ice_water_and_rock_accounts_separate():
    inputs = dict(source_identity='synthetic-native-unit-flowline',thickness_start_m=np.zeros(3),
        bed_m=np.array([100.,90.,80.]),accumulation_mm=np.full((1,3),100.),
        ablation_mm=np.zeros((1,3)),time_edges_s=np.array([0.,3600.]),
        x_m=np.arange(3)*30.,width_m=30.,bedrock_erodible_m3=np.full(3,900.),
        land_port_mask=np.ones(3,bool))
    actual = advance_native_glacier(inputs)
    assert actual['process']['status'] == 'computed'
    assert actual['result']['ledger']['ice']['max_abs_residual_m3'] < 1e-8
    water_volume = .1*900*3
    assert actual['result']['arrays']['ice_volume_edge_m3'][-1].sum() > water_volume
    coarse = advance_native_glacier(dict(inputs,x_m=np.arange(3)*2000.,width_m=2000.))
    assert coarse['process']['status'] == 'unsupported-scale'
