import numpy as np
import pytest

from terrain_pipeline.surface_hydraulics import prepare_surface_geometry, SurfaceBudget
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig, transport_bedload, incident_wave_field, MorphodynamicStepTooLarge
from terrain_pipeline.surface_rivers.metric_fv_coastal_coupling import advance_coupled


def fixture(speed=1., seconds=10.):
    bed = np.full((3, 5), -.5)
    kinds = np.zeros(2 * sum(bed.shape), np.int64)
    kinds[3:6] = 2
    geometry = prepare_surface_geometry(bed, spacing_m=5., origin_m_xz=[0., 0.],
        source_identity="finite-test", boundary_kind=kinds)
    a = geometry["arrays"]
    axes = np.r_[np.zeros(12, int), np.ones(10, int)]
    packet = {"time_start_s": 0., "time_end_s": seconds,
        "depth_before_m": np.full(bed.size, .5), "depth_after_m": np.full(bed.size, .5),
        "momentum_before": np.tile([.5 * speed, 0.], (bed.size, 1)),
        "momentum_after": np.tile([.5 * speed, 0.], (bed.size, 1)),
        "internal_transfer_m3": np.where(axes == 0, speed * .5 * 5. * seconds, 0.),
        "boundary_transfer_m3": np.where(a["boundary_kind"] == 2, speed * .5 * 5. * seconds, 0.)}
    return bed, geometry, packet


def test_finite_floor_total_donor_cap_and_export_close():
    bed, geometry, packet = fixture(speed=3., seconds=100.)
    floor = bed - .003
    result = transport_bedload(bed, floor, geometry, packet, BedloadConfig(wave_height_m=0., max_bed_change_m=.01))
    assert result["bed_m"].min() >= floor.min() - 1.e-15
    assert result["ledger"]["maximum_abs_bed_change_m"] <= .003 + 1.e-15
    assert result["ledger"]["exported_solid_m3"] > 0.
    assert abs(result["ledger"]["residual_solid_m3"]) < 1.e-12
    assert result["ledger"]["inventory_limited_donors"] > 0


def test_bed_change_ceiling_refuses_full_step_without_silently_scaling_rate():
    bed, geometry, packet = fixture(speed=3., seconds=100.)
    before = bed.copy()
    with pytest.raises(MorphodynamicStepTooLarge, match="no transport-rate scaling"):
        transport_bedload(bed, bed - .3, geometry, packet, BedloadConfig(wave_height_m=0., max_bed_change_m=.001))
    np.testing.assert_array_equal(bed, before)


def test_actual_wetting_front_uses_shared_crest_depth_not_receiver_film():
    bed = np.array([[-.17321941576331757, -.13646286725997925]])
    h = np.array([.03691029690081416, 1.0257947230094785e-5])
    geometry = prepare_surface_geometry(bed, spacing_m=5., origin_m_xz=[0., 0.], source_identity="wet-front")
    packet = {"time_start_s": 0., "time_end_s": .5, "depth_before_m": h, "depth_after_m": h,
        "momentum_before": np.zeros((2, 2)), "momentum_after": np.zeros((2, 2)),
        "internal_transfer_m3": np.array([.0001374894351904243 * .5]),
        "boundary_transfer_m3": np.zeros(6)}
    result = transport_bedload(bed, bed - 1., geometry, packet, BedloadConfig(wave_height_m=0.))
    np.testing.assert_allclose(result["face_effective_depth_m"], [8.20031723529624e-5], rtol=1.e-10)
    np.testing.assert_allclose(result["face_normal_velocity_m_s"], [.3353271129527404], rtol=1.e-10)
    assert abs(result["bed_m"] - bed).max() < .01
    assert result["internal_transfer_solid_m3"][0] < .1


def test_breaking_limited_airy_orbital_velocity_tends_to_zero_with_depth():
    bed = np.zeros((1, 4))
    kinds = np.full(2 * sum(bed.shape), 2, np.int64)
    geometry = prepare_surface_geometry(bed, spacing_m=5., origin_m_xz=[0., 0.],
        source_identity="thin-wave", boundary_kind=kinds)
    config = BedloadConfig(wave_height_m=.3, wave_direction_xz=(-1, 0), dry_depth_m=1.e-12)
    values = []
    for h in (.01, .0001, .000001, .00000001):
        field = incident_wave_field(np.full_like(bed, h), geometry, config)
        assert field["wave_height_m"].max() <= .78 * h * (1. + 1.e-12)
        values.append(field["wave_orbital_velocity_m_s"].max())
    assert np.all(np.diff(values) < 0.)
    assert values[-1] < values[0] / 100.


def test_zero_current_symmetric_waves_and_subcritical_current_do_not_draw_bed():
    for speed in (0., 1.e-4):
        bed, geometry, packet = fixture(speed=speed)
        config = BedloadConfig(wave_height_m=.4 if speed == 0 else 0., wave_direction_xz=(-1, 0))
        result = transport_bedload(bed, bed - .3, geometry, packet, config)
        np.testing.assert_array_equal(result["bed_m"], bed)
        assert result["ledger"]["exported_solid_m3"] == 0.


def test_incident_rays_are_boundary_driven_and_land_blocks_wave():
    bed, geometry, _ = fixture()
    depth = np.full_like(bed, .5)
    depth[:, 2] = 0.
    wave = incident_wave_field(depth, geometry, BedloadConfig(wave_height_m=.2, wave_direction_xz=(-1, 0)))
    assert np.all(wave["wave_height_m"][:, 3:] > 0.)
    np.testing.assert_array_equal(wave["wave_height_m"][:, :3], 0.)


def test_incident_waves_stir_existing_current_transport_and_reversal_follows_flow():
    bed, geometry, packet = fixture(speed=.2, seconds=1.)
    calm = transport_bedload(bed, bed - .3, geometry, packet,
        BedloadConfig(wave_height_m=0., wave_direction_xz=(-1, 0)))
    stirred = transport_bedload(bed, bed - .3, geometry, packet,
        BedloadConfig(wave_height_m=.3, wave_direction_xz=(-1, 0)))
    assert stirred["ledger"]["gross_internal_transfer_solid_m3"] > calm["ledger"]["gross_internal_transfer_solid_m3"]
    bed, geometry, reverse = fixture(speed=-.2, seconds=1.)
    reversed_result = transport_bedload(bed, bed - .3, geometry, reverse,
        BedloadConfig(wave_height_m=.3, wave_direction_xz=(-1, 0)))
    assert stirred["internal_transfer_solid_m3"][:12].sum() > 0.
    assert reversed_result["internal_transfer_solid_m3"][:12].sum() < 0.


def execute(geometry, depth, *, intervals=4, momentum=None, config=None, observer=None):
    return advance_coupled(geometry, floor_m=np.full(depth.shape, -.8), initial_depth_m=depth,
        source_m3_s=np.full(depth.shape, .01), sea_stage_provider=lambda index: np.zeros(2 * sum(depth.shape)),
        intervals=intervals, interval_s=.5, budget=SurfaceBudget(max_dt_s=.05, max_snapshots=intervals + 2),
        config=config or BedloadConfig(wave_height_m=0., mpm_coefficient=0.),
        initial_momentum_m2_s=momentum, momentum_observer=observer)


def test_saved_momentum_continuation_matches_uninterrupted_hydraulics():
    bed, geometry, _ = fixture()
    depth = np.full_like(bed, .55)
    whole = execute(geometry, depth)
    bed, geometry, _ = fixture()
    first = execute(geometry, depth, intervals=2)
    a = first["arrays"]
    momentum = np.column_stack([a["momentum_x_m2_s"][-1].ravel(), a["momentum_z_m2_s"][-1].ravel()])
    witnesses = []
    second = execute(geometry, a["depth_m"][-1], intervals=2, momentum=momentum, observer=witnesses.append)
    np.testing.assert_array_equal(witnesses[0]["state_before"][:, 1:], momentum)
    for key in ("depth_m", "momentum_x_m2_s", "momentum_z_m2_s"):
        np.testing.assert_allclose(second["arrays"][key][-1], whole["arrays"][key][-1], atol=2.e-13, rtol=2.e-13)


def test_real_bed_feedback_retains_water_and_momentum_between_intervals():
    bed, geometry, _ = fixture()
    depth = np.full_like(bed, .5)
    momentum = np.tile([.5, 0.], (bed.size, 1))
    witnesses = []
    active = execute(geometry, depth, momentum=momentum,
        config=BedloadConfig(wave_height_m=.2, wave_direction_xz=(-1, 0), max_bed_change_m=.001), observer=witnesses.append)
    assert np.max(abs(active["arrays"]["bed_m"][-1] - bed)) > 0.
    for index in range(1, 4):
        previous = active["arrays"]
        np.testing.assert_array_equal(witnesses[index]["state_before"][:, 0], previous["depth_m"][index].ravel())
        np.testing.assert_array_equal(witnesses[index]["state_before"][:, 1], previous["momentum_x_m2_s"][index].ravel())
    bed2, geometry2, _ = fixture()
    frozen = execute(geometry2, depth, momentum=momentum)
    assert np.max(abs(active["arrays"]["depth_m"][-1] - frozen["arrays"]["depth_m"][-1])) > 1.e-10
    assert abs(active["arrays"]["ledger"][-1, -1]) < 1.e-10
