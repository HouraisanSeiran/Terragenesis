from dataclasses import replace
import numpy as np
import pytest

from tests.test_fv_suspended_growth import geometry, packet
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig
from terrain_pipeline.surface_rivers.metric_fv_suspended_supply import SuspendedConfig
from terrain_pipeline.surface_rivers.metric_fv_exchange_v3 import ExchangeConfig, entrain, slope_transport
from terrain_pipeline.surface_rivers.metric_fv_growth_coupling_v3 import advance_growth
from tools.inspect_natural_fv_growth import audit_chunk
from terrain_pipeline.surface_rivers.metric_fv_growth_coupling import advance_growth as v1_advance


def water(g, speed=0.):
    w = packet(g, .1)
    w.update(momentum_before=np.tile([speed, 0.], (9, 1)), momentum_after=np.tile([speed, 0.], (9, 1)))
    return w


def test_clear_high_shear_entrains_finite_bed_and_respects_capacity_fixed_floor():
    g = geometry()
    g["arrays"]["fixed_bed_cell"][0] = True
    bed = np.full((3, 3), -.5)
    floor = bed - .00001
    config = BedloadConfig(wave_height_m=0., max_bed_change_m=.1)
    changed, mass, eroded, _ = entrain(bed, np.zeros_like(bed), floor, g, water(g, 3.), config, ExchangeConfig())
    assert eroded.sum() > 0. and eroded.flat[0] == 0.
    assert np.min(changed - floor) >= -1.e-12
    assert mass.max() <= .03 * 25.
    assert ((bed - changed) * 25. * .65).sum() == pytest.approx(mass.sum(), abs=1.e-12)
    full = np.full_like(bed, .03 * 25.)
    _, _, eroded_full, _ = entrain(bed, full, floor, g, water(g, 3.), config, ExchangeConfig())
    assert eroded_full.sum() == 0.


def test_wet_bank_slope_moves_downhill_conservatively_and_dry_land_stays():
    g = geometry()
    bed = np.full((3, 3), -.5)
    bed[1, 1] = 2.
    floor = bed - .1
    config = BedloadConfig(wave_height_m=0., max_bed_change_m=.1)
    cfg = ExchangeConfig(critical_slope_m_m=.1)
    changed, transfer, _ = slope_transport(bed, floor, g, .1, config, cfg, np.ones_like(bed))
    assert changed[1, 1] < bed[1, 1] and transfer.any()
    assert changed.sum() == pytest.approx(bed.sum(), abs=1.e-12)
    assert np.min(changed - floor) >= -1.e-12
    dry, transfer, _ = slope_transport(bed, floor, g, .1, config, cfg, np.zeros_like(bed))
    np.testing.assert_array_equal(dry, bed)
    assert not transfer.any()


def step(g, depth, momentum, suspended, count=1, exchange=ExchangeConfig()):
    return advance_growth(g, floor_m=np.full((3, 3), -.8), depth_m=depth, momentum_m2_s=momentum,
        suspended_solid_m3=suspended, river_q_m3_s=[0.] * count, input_solid_m3=[0.] * count,
        sea_stages_m=[0.] * count, inlet_cells=[0, 1, 2], interval_s=.01,
        budget=SurfaceBudget(max_snapshots=5, max_duration_s=1., max_bytes=32 * 1024 ** 2),
        bedload_config=BedloadConfig(wave_height_m=0., mpm_coefficient=0., max_bed_change_m=.1),
        suspended_config=SuspendedConfig(settling_velocity_m_s=.1, max_bed_change_m=.1), exchange_config=exchange)


def test_real_fv_still_water_deposits_and_high_shear_suppresses_deposition():
    initial = np.full((3, 3), .01)
    still = step(geometry(), np.ones((3, 3)), np.zeros((9, 2)), initial)
    shear = step(geometry(), np.ones((3, 3)), np.tile([2., 0.], (9, 1)), initial)
    assert still["sediment_ledgers"][0]["suspended"]["deposited_solid_m3"] > 0.
    assert shear["sediment_ledgers"][0]["suspended"]["deposited_solid_m3"] == 0.
    assert shear["sediment_ledgers"][0]["suspended"]["entrained_solid_m3"] > 0.
    for result in (still, shear):
        assert abs(result["sediment_ledgers"][0]["combined_residual_solid_m3"]) < 1.e-10


def test_real_fv_restart_equals_continuous_with_exchange():
    depth, momentum, suspended = np.ones((3, 3)), np.tile([1., 0.], (9, 1)), np.zeros((3, 3))
    continuous = step(geometry(), depth, momentum, suspended, count=2)
    first = step(geometry(), depth, momentum, suspended)["arrays"]
    g = geometry()
    g["arrays"]["H2_m"][:] = first["bed_m"][-1]
    flat = first["bed_m"][-1].ravel()
    a = g["arrays"]
    a["face_crest_m"][:] = np.maximum(flat[a["face_left"]], flat[a["face_right"]])
    a["boundary_crest_m"][:] = flat[a["boundary_cell"]]
    second = step(g, first["depth_m"][-1], np.column_stack((first["momentum_x_m2_s"][-1].ravel(),
        first["momentum_z_m2_s"][-1].ravel())), first["suspended_solid_m3"][-1])
    for key in ("bed_m", "depth_m", "momentum_x_m2_s", "momentum_z_m2_s", "suspended_solid_m3"):
        np.testing.assert_allclose(second["arrays"][key][-1], continuous["arrays"][key][-1], atol=2.e-12, rtol=2.e-12)


def test_disabled_operators_equal_frozen_v1_real_fv():
    kwargs = dict(floor_m=np.full((3, 3), -.8), depth_m=np.ones((3, 3)), momentum_m2_s=np.zeros((9, 2)),
        suspended_solid_m3=np.full((3, 3), .01), river_q_m3_s=[0.], input_solid_m3=[0.],
        sea_stages_m=[0.], inlet_cells=[0, 1, 2], interval_s=.01,
        budget=SurfaceBudget(max_snapshots=3, max_duration_s=1., max_bytes=32 * 1024 ** 2),
        bedload_config=BedloadConfig(wave_height_m=0., mpm_coefficient=0., max_bed_change_m=.1),
        suspended_config=SuspendedConfig(settling_velocity_m_s=.1, max_bed_change_m=.1))
    old = v1_advance(geometry(), **kwargs)
    new = advance_growth(geometry(), **kwargs, exchange_config=ExchangeConfig(enabled=False, slope_enabled=False))
    for key in ("bed_m", "depth_m", "momentum_x_m2_s", "momentum_z_m2_s", "suspended_solid_m3"):
        np.testing.assert_allclose(old["arrays"][key], new["arrays"][key], atol=1.e-14, rtol=1.e-14)
