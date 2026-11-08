"""Behavior checks for finite phase-driven coastal transport."""
import numpy as np
import pytest

from terrain_pipeline.surface_rivers.metric_coastal_transport import (
    CoastalConfig, channel_water_stage, connected_sea, derived_construction,
    flowing_reach_stage, foreshore_outflow, run_coastal_transport,
)


def case(tides=True, waves=True, supply=100., config=None):
    rows, cols = np.indices((51, 61))
    bed = (25.-rows)*.13+.07*np.cos(cols/5.)
    protected = np.zeros_like(bed, bool)
    protected[:5] = True
    settings = config or CoastalConfig(activity_radius_m=4700.)
    return bed, protected, run_coastal_transport(bed, protected, [[27, 30]],
        np.array([[supply]]), 100., settings, tides=tides, waves=waves)


def test_zero_forcing_and_supply_exact_and_zero_amplitudes_no_hidden_loss():
    bed, _, result = case(False, False, 0.)
    np.testing.assert_array_equal(bed, result["bed_m"])
    bed, _, result = case(True, True, 0., CoastalConfig(tide_amplitude_m=0., wave_height_m=0.))
    np.testing.assert_array_equal(bed, result["bed_m"])
    assert result["ledger"]["offshore_export_solid_m3"] == 0.


def test_tide_wave_alter_bed_and_conserve_finite_inventory():
    bed, protected, combined = case()
    _, _, zero = case(False, False)
    assert np.max(np.abs(combined["bed_m"]-zero["bed_m"])) > .00001
    assert np.max(np.abs(combined["tide_height_delta_m"])) > 0.
    assert np.max(np.abs(combined["wave_height_delta_m"])) > 0.
    assert np.count_nonzero(combined["high_tide_wet_mask"]) > np.count_nonzero(combined["low_tide_wet_mask"])
    assert abs(combined["ledger"]["residual_solid_m3"]) < 1.e-6
    assert combined["mobile_solid_m3"].min() >= 0.
    assert np.min(combined["bed_m"]-combined["rock_floor_m"]) >= -1.e-12
    np.testing.assert_array_equal(bed[protected], combined["bed_m"][protected])
    components = sum(combined[key] for key in ("tide_height_delta_m", "wave_height_delta_m",
        "river_supply_height_delta_m", "export_height_delta_m"))
    np.testing.assert_allclose(combined["bed_m"]-bed, components, atol=1.e-12)
    np.testing.assert_array_equal(combined["bed_m"], case()[2]["bed_m"])


def test_disconnected_lowland_remains_dry_until_connected_over_sill():
    bed = np.ones((11, 11))
    bed[-1] = -2.
    bed[4:7, 4:7] = -1.
    assert not connected_sea(bed, 0.)[5, 5]
    assert connected_sea(bed, 1.1)[5, 5]


def test_disconnected_terminal_supply_is_escrowed_not_created_on_dry_ground():
    bed = np.ones((31, 31))*3.
    bed[-1] = -2.
    bed[12:19, 12:19] = -.3
    result = run_coastal_transport(bed, np.zeros_like(bed, bool), [[15, 15]],
        np.array([[100.]]), 100., CoastalConfig(), tides=False, waves=False)
    # Kernels have finite tails; a disconnected terminal must not remotely supply
    # a separate sea beyond its local 3-sigma receiving neighborhood.
    assert result["pending_terminal_solid_m3"][0] == 100.
    np.testing.assert_array_equal(result["bed_m"], bed)


def test_construction_preserves_channel_upstream_and_td_addition():
    rows, cols = np.indices((81, 81))
    macro = np.where((rows > 15) & (cols > 15), 70., 25.)
    td = .2*np.sin(rows/3.)
    protected = np.zeros_like(macro, bool)
    protected[:, 40] = True
    result, delta, weight = derived_construction(macro+td, td, protected, protected, 100.)
    np.testing.assert_array_equal(result[protected], (macro+td)[protected])
    np.testing.assert_array_equal(delta[[0, -1]], 0.)
    assert np.abs(delta).max() > 1.
    assert weight.min() == 0.


@pytest.mark.parametrize("config", [CoastalConfig(wave_direction_xz=(0., 0.)),
    CoastalConfig(tide_amplitude_m=float("nan")), CoastalConfig(porosity=1.)])
def test_invalid_forcing_rejected(config):
    with pytest.raises(ValueError):
        case(config=config)


def test_positive_flow_negative_tide_has_hydraulic_depth_zero_flow_can_dry():
    station = np.arange(5)*100.
    bed = np.linspace(-.4, -.05, 5)
    stage, control = flowing_reach_stage(bed, station, 80., 1.5, -.65)
    critical = (1.5**2/(9.81*80.**2))**(1./3.)
    assert np.all(stage-bed >= critical-1.e-12)
    np.testing.assert_allclose(control, critical)
    dry, control = flowing_reach_stage(bed, station, 80., 0., -.65)
    np.testing.assert_array_equal(dry, bed)
    np.testing.assert_array_equal(control, 0.)


def test_foreshore_minimax_route_reaches_sea_without_bed_excavation():
    from scipy.ndimage import label
    bed = np.full((15, 21), 2.)
    bed[7, 1:20] = np.linspace(.1, -.9, 19)
    bed[:, -1] = -1.
    original = bed.copy()
    sea = connected_sea(bed, -.65)
    initial = np.full_like(bed, np.nan)
    initial[7, 1] = .4
    surface, routes, states = foreshore_outflow(bed, sea, initial, [[7, 1]], [3.], [20.], 20.)
    labels, _ = label(np.isfinite(surface) | sea)
    assert labels[7, 1] == labels[7, -1] > 0
    assert sea[tuple(routes[0][-1])]
    assert np.all(routes[0][:, 0] == 7)
    assert states[0]["maximum_sill_m"] == pytest.approx(.1)
    assert states[0]["prism_replacement_time_s"] > 0.
    np.testing.assert_array_equal(bed, original)
    dry, routes, states = foreshore_outflow(bed, sea, np.full_like(bed, np.nan), [[7, 1]], [0.], [20.], 20.)
    assert not np.isfinite(dry).any()
    assert states[0]["status"] == "zero_flow"


def test_gate_already_in_sea_does_not_contract_or_raise_existing_river_head():
    bed = np.full((5, 5), -1.)
    sea = np.ones_like(bed, bool)
    river = np.full_like(bed, np.nan)
    river[2, 2] = .3
    surface, routes, states = foreshore_outflow(bed, sea, river, [[2, 2]], [100.], [120.], 20.)
    np.testing.assert_array_equal(surface, river)
    assert states[0]["gate_stage_m"] == .3
    assert states[0]["effective_raster_width_m"] == 120.
    assert states[0]["water_prism_m3"] == states[0]["path_length_m"] == 0.
