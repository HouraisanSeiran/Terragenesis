from dataclasses import replace

import numpy as np
import pytest

from terrain_pipeline.regional_surface_hydraulics import prepare_surface_geometry, SurfaceBudget
from terrain_pipeline.surface_rivers.metric_fv_suspended_supply import advance_suspended, SuspendedConfig, integrate_schedule
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig, incident_wave_field, transport_bedload
from terrain_pipeline.surface_rivers.metric_fv_growth_coupling import advance_growth, _calm_transport
from tools.run_natural_fv_growth import forcing_step


def geometry():
    bed = np.full((3, 3), -.5)
    g = prepare_surface_geometry(bed, spacing_m=5., origin_m_xz=[0., 0.], source_identity="test")
    g["arrays"]["fixed_bed_cell"] = np.zeros(9, bool)
    return g


def packet(g, duration=1.):
    a = g["arrays"]
    return {"time_start_s": 0., "time_end_s": duration, "depth_before_m": np.ones(9),
        "depth_after_m": np.ones(9), "internal_transfer_m3": np.zeros(len(a["face_left"])),
        "boundary_transfer_m3": np.zeros(len(a["boundary_cell"]))}


def test_fresh_solid_moves_off_fixed_inlet_then_settles_without_losing_mass():
    g = geometry()
    g["arrays"]["fixed_bed_cell"][0] = True
    p = packet(g)
    p["internal_transfer_m3"][0] = 12.5
    result = advance_suspended(np.zeros((3, 3)), g["arrays"]["H2_m"], g, p, 1., [0],
        SuspendedConfig(settling_velocity_m_s=.2, max_bed_change_m=.1))
    assert result["deposited_solid_m3"].flat[0] == 0.
    assert result["deposited_solid_m3"].flat[1] > 0.
    assert result["bed_m"].flat[1] > -.5
    assert abs(result["ledger"]["residual_solid_m3"]) < 1.e-12
    assert result["ledger"]["final_suspended_solid_m3"] + result["ledger"]["deposited_solid_m3"] == pytest.approx(1.)


def test_reverse_face_transport_and_clear_boundary_inflow_conserve_solid():
    g = geometry()
    p = packet(g)
    p["internal_transfer_m3"][0] = -12.5
    p["boundary_transfer_m3"][0] = -10.
    initial = np.zeros((3, 3))
    initial.flat[1] = .5
    result = advance_suspended(initial, g["arrays"]["H2_m"], g, p, 0., [0], SuspendedConfig(settling_velocity_m_s=0.))
    assert result["suspended_solid_m3"].flat[0] > 0.
    assert result["suspended_solid_m3"].sum() == pytest.approx(.5)
    assert result["boundary_export_solid_m3"].sum() == 0.


def test_partial_source_cursor_and_acceleration_never_repeat_entitlement():
    schedule = np.array([[0., 0., 10., 2., 20., 100.], [1., 0., 20., 4., 20., 100.]])
    a, _ = integrate_schedule(schedule, 0., 25.)
    b, _ = integrate_schedule(schedule, 25., 100.)
    assert a + b == pytest.approx(6.)
    assert integrate_schedule(schedule, 125., 10.) == (0., 20.)
    load, q, cursor = forcing_step(schedule, 0., 1., 100., .01)
    assert load <= .01 * q + 1.e-10
    assert load == pytest.approx(integrate_schedule(schedule, 0., cursor)[0])
    off, _, paused = forcing_step(schedule, cursor, 1., 100., .01, supply_off=True)
    assert off == 0. and paused == cursor


def test_zero_wave_shortcut_is_private_and_does_not_patch_frozen_module():
    assert _calm_transport.__globals__["incident_wave_field"] is not incident_wave_field
    assert advance_suspended.__module__.endswith("metric_fv_suspended_supply")
    g = geometry()
    p = packet(g)
    p.update(momentum_before=np.zeros((9, 2)), momentum_after=np.zeros((9, 2)),
        tailwater_m=np.zeros(len(g["arrays"]["boundary_cell"])))
    config = BedloadConfig(wave_height_m=0.)
    ordinary = transport_bedload(g["arrays"]["H2_m"], np.full((3, 3), -.8), g, p, config)
    shortcut = _calm_transport(g["arrays"]["H2_m"], np.full((3, 3), -.8), g, p, config)
    for key in ("bed_m", "inventory_solid_m3", "internal_transfer_solid_m3", "boundary_export_solid_m3"):
        np.testing.assert_array_equal(ordinary[key], shortcut[key])


def test_transient_dilute_violation_cannot_be_hidden_by_fast_settling():
    g = geometry()
    with pytest.raises(ValueError, match="before settling"):
        advance_suspended(np.zeros((3, 3)), g["arrays"]["H2_m"], g, packet(g), 2., [0],
            SuspendedConfig(settling_velocity_m_s=100., max_bed_change_m=1.))


def test_live_fv_bed_feedback_and_chunk_restart_keep_complete_state():
    g = geometry()
    floor = np.full((3, 3), -.8)
    depth = np.ones((3, 3))
    momentum = np.zeros((9, 2))
    captured = []
    config = BedloadConfig(wave_height_m=0., mpm_coefficient=0., max_bed_change_m=.1)
    settling = SuspendedConfig(settling_velocity_m_s=.1, max_bed_change_m=.1)
    budget = SurfaceBudget(max_snapshots=5, max_duration_s=1., max_bytes=32 * 1024 ** 2)
    result = advance_growth(g, floor_m=floor, depth_m=depth, momentum_m2_s=momentum,
        suspended_solid_m3=np.zeros((3, 3)), river_q_m3_s=[1., 1.], input_solid_m3=[.01, .01],
        sea_stages_m=[0., 0.], inlet_cells=[0, 1, 2], interval_s=.1, budget=budget,
        bedload_config=config, suspended_config=settling, interval_observer=lambda w, b, s, l: captured.append((w, s)))
    a = result["arrays"]
    assert a["bed_m"][-1].max() > -.5
    assert a["suspended_solid_m3"][-1].sum() > 0.
    np.testing.assert_array_equal(captured[1][0]["depth_before_m"], captured[0][0]["depth_after_m"])
    np.testing.assert_array_equal(captured[1][0]["momentum_before"], captured[0][0]["momentum_after"])
    np.testing.assert_allclose(g["arrays"]["subcell_bed_relative_m"][:, 0], a["bed_m"][-1].ravel() + .5)
    assert max(abs(row["combined_residual_solid_m3"]) for row in result["sediment_ledgers"]) < 1.e-10
    assert abs(a["ledger"][-1, -1]) < 1.e-10
    first = advance_growth(geometry(), floor_m=floor, depth_m=depth, momentum_m2_s=momentum,
        suspended_solid_m3=np.zeros((3, 3)), river_q_m3_s=[1.], input_solid_m3=[.01],
        sea_stages_m=[0.], inlet_cells=[0, 1, 2], interval_s=.1, budget=budget,
        bedload_config=config, suspended_config=settling)
    first_a = first["arrays"]
    restarted = prepare_surface_geometry(first_a["bed_m"][-1].copy(), spacing_m=5., origin_m_xz=[0., 0.], source_identity="test")
    restarted["arrays"]["fixed_bed_cell"] = np.zeros(9, bool)
    second = advance_growth(restarted, floor_m=floor, depth_m=first_a["depth_m"][-1],
        momentum_m2_s=np.column_stack([first_a["momentum_x_m2_s"][-1].ravel(), first_a["momentum_z_m2_s"][-1].ravel()]),
        suspended_solid_m3=first_a["suspended_solid_m3"][-1], river_q_m3_s=[1.], input_solid_m3=[.01],
        sea_stages_m=[0.], inlet_cells=[0, 1, 2], interval_s=.1, budget=budget,
        bedload_config=config, suspended_config=settling)
    for key in ("bed_m", "depth_m", "momentum_x_m2_s", "momentum_z_m2_s", "suspended_solid_m3"):
        np.testing.assert_allclose(second["arrays"][key][-1], a[key][-1], atol=2.e-12, rtol=2.e-12)
