from dataclasses import replace
import numpy as np
import pytest

from terrain_pipeline.coastal_marine_sediment import (
    MarineConfig, RiverPacket, advance, classify_ocean, load_state, make_state, save_state, wave_exposure,
)


def grid(base=None, solid=0, mobile=0, time_s=0):
    if base is None:
        base = np.full((7, 12), -5.)
    seeds = np.zeros(base.shape, bool)
    seeds[:, 0] = True
    return make_state(base_bed_m=base, bed_solid_m3=solid, mobile_solid_m3=mobile,
                      porosity=.4, valid_mask=True, ocean_seed_mask=seeds, spacing_m=100,
                      origin_xz_m=(10, 20), source_identity="fixture", time_s=time_s)


def packet(**overrides):
    args = dict(input_id='p1', source_id='scenario', start_s=0., end_s=100., row=3, col=1,
                water_m3=100000., solid_m3=100., known=True, direction_xz=(1., 0.), width_m=20., depth_m=2.)
    args.update(overrides)
    return RiverPacket(**args)


def test_connectivity_and_idle_stock():
    base = np.full((7, 12), -5.)
    base[:, 5] = 2
    solid = np.zeros_like(base); solid[3, 1] = 10
    s = grid(base, solid)
    ocean, shore = classify_ocean(s, 0)
    assert ocean[3, 1] and not ocean[3, 6] and shore[3, 5]
    out = advance(s, [], 100)
    np.testing.assert_array_equal(out.bed_solid_m3, s.bed_solid_m3)
    np.testing.assert_array_equal(out.mobile_solid_m3, s.mobile_solid_m3)


def test_river_drives_transport_without_waves_or_tide_and_clear_water():
    s = grid()
    cfg = MarineConfig(settling_rate_s=.002, step_s=10)
    out = advance(s, [packet()], 100, cfg)
    assert out.bed_solid_m3[3, 2:].sum() + out.mobile_solid_m3[3, 2:].sum() > 1
    assert out.bed_solid_m3.sum() > 0
    assert np.isclose(out.bed_solid_m3.sum() + out.mobile_solid_m3.sum(), 100)
    mobile = np.zeros((7, 12)); mobile[3, 1] = 100
    clear = advance(grid(mobile=mobile), [packet(solid_m3=0)], 100, cfg)
    still = advance(grid(mobile=mobile), [], 100, cfg)
    assert clear.mobile_solid_m3[3, 2:].sum() > still.mobile_solid_m3[3, 2:].sum()


def test_interval_restart_and_absolute_phase(tmp_path):
    s = grid(time_s=100)
    p = packet(start_s=100, end_s=300)
    cfg = MarineConfig(tide_amplitude_m=1, tide_period_s=400, transport_rate_s=.001,
                       settling_rate_s=.001, export_rate_s=.001, step_s=10)
    whole = advance(s, [p], 200, cfg)
    partial = advance(s, [p], 100, cfg)
    assert partial.water_input_m3 == 50000
    path = tmp_path / 'state.npz'; save_state(path, partial)
    resumed = advance(load_state(path), [], 100, cfg)
    np.testing.assert_allclose(whole.bed_solid_m3, resumed.bed_solid_m3, atol=1e-12)
    np.testing.assert_allclose(whole.mobile_solid_m3, resumed.mobile_solid_m3, atol=1e-12)
    assert np.isclose(whole.exported_solid_m3, resumed.exported_solid_m3)
    assert resumed.consumed_packets[0]['delivered_solid_m3'] == 100
    with pytest.raises(ValueError): advance(resumed, [p], 10, cfg)
    assert np.isclose(whole.bed_solid_m3.sum()+whole.mobile_solid_m3.sum()+whole.exported_solid_m3, 100)


def test_tide_flood_points_up_slope_and_ebb_reverses():
    base = np.tile(np.linspace(-10, -2, 12), (7, 1))
    mobile = np.zeros_like(base); mobile[3, 5] = 100
    cfg = MarineConfig(tide_amplitude_m=1, tide_period_s=400, transport_rate_s=.01, step_s=10)
    flood = advance(grid(base, mobile=mobile), [], 10, cfg)
    ebb = advance(grid(base, mobile=mobile, time_s=200), [], 10, cfg)
    assert flood.mobile_solid_m3[3, 6] > flood.mobile_solid_m3[3, 4]
    assert ebb.mobile_solid_m3[3, 4] > ebb.mobile_solid_m3[3, 6]


def test_island_shields_incident_waves():
    base = np.full((7, 12), -5.); base[3, 4] = 1
    s = grid(base); ocean, _ = classify_ocean(s, 0)
    exposure = wave_exposure(s, ocean, np.maximum(-s.bed_m, 0), MarineConfig(wave_height_m=1))
    assert exposure[3, 3] > 0 and exposure[3, 5] == 0 and exposure[2, 5] > 0


def test_unknown_is_preserved_and_bad_packet_rejected():
    unknown = packet(input_id='unknown', known=False, water_m3=None, solid_m3=None)
    out = advance(grid(), [unknown], 100)
    assert out.consumed_packets[0]['delivered_solid_m3'] is None
    assert out.mobile_solid_m3.sum() == 0
    with pytest.raises(ValueError): advance(grid(), [packet(solid_m3=-1)], 100)


def test_existing_bed_stock_is_inherited_and_not_recharged():
    solid = np.zeros((7, 12)); solid[3, 1] = 80
    s = grid(solid=solid)
    cfg = MarineConfig(entrainment_rate_s=.001, settling_rate_s=.002, step_s=10)
    out = advance(s, [packet()], 100, cfg)
    assert np.isclose(out.bed_solid_m3.sum() + out.mobile_solid_m3.sum(), 180)
    assert out.bed_m[3, 1] != s.bed_m[3, 1]
    continued = advance(out, [], 100, cfg)
    assert np.isclose(continued.bed_solid_m3.sum() + continued.mobile_solid_m3.sum(), 180)


def test_waves_reentrain_only_exposed_stock():
    base = np.full((7, 12), -5.); base[3, 4] = 1
    solid = np.zeros_like(base); solid[2, 5] = 100; solid[3, 5] = 100
    s = grid(base, solid)
    out = advance(s, [], 10, MarineConfig(wave_height_m=1, entrainment_rate_s=.1, step_s=10))
    assert out.mobile_solid_m3[2, 5] > 0
    assert out.mobile_solid_m3[3, 5] == 0


def test_active_layer_bounds_erosion_and_preserves_thin_cover():
    # Same exposed bed elevation and forcing, different sediment thickness.
    thin_solid = np.zeros((7,12)); thin_solid[3,2]=60.
    thick_solid = np.zeros((7,12)); thick_solid[3,2]=6000.
    thin_base = np.full((7,12),-5.); thin_base[3,2]-=60/6000
    thick_base = np.full((7,12),-5.); thick_base[3,2]-=1.
    cfg=MarineConfig(wave_height_m=1,entrainment_rate_s=.001,step_s=100,
                     active_sediment_layer_m=.1,transverse_diffusivity_m2_s=0)
    thin=advance(grid(thin_base,thin_solid),[],100,cfg)
    thick=advance(grid(thick_base,thick_solid),[],100,cfg)
    fraction=(1-np.exp(-.001*100/7))*(5/6)
    assert np.isclose(thin.mobile_solid_m3[3,2],60*fraction)
    assert np.isclose(thick.mobile_solid_m3[3,2],600*fraction)
    assert np.isclose(thick.bed_solid_m3.sum()+thick.mobile_solid_m3.sum(),6000)
    with pytest.raises(ValueError):
        advance(grid(),[],10,replace(cfg,active_sediment_layer_m=-1))


def test_oblique_river_has_conservative_transverse_spreading_without_tide_or_wave():
    base = np.full((31, 31), -5.)
    s = grid(base)
    p = packet(row=15, col=5, direction_xz=(1., .5), water_m3=600000.,
               end_s=600, width_m=100, depth_m=3)
    no_mix = advance(s, [p], 600, MarineConfig(step_s=10, transverse_diffusivity_m2_s=0))
    mixed = advance(s, [p], 600, MarineConfig(step_s=10, transverse_diffusivity_m2_s=30))
    rows, cols = np.indices(base.shape)
    across = (rows-15) - .5*(cols-5)
    def variance(state):
        stock = state.mobile_solid_m3 + state.bed_solid_m3
        return np.sum(stock * (across - np.sum(stock * across)/stock.sum())**2)/stock.sum()
    assert variance(mixed) > variance(no_mix) * 1.2
    assert np.isclose(mixed.mobile_solid_m3.sum()+mixed.bed_solid_m3.sum(), 100)


def test_spreading_does_not_cross_land_or_disconnected_sea():
    base = np.full((15, 20), -5.); base[:, 9] = 2.
    s = grid(base)
    p = packet(row=7, col=5, direction_xz=(1., .5), end_s=600, water_m3=600000.)
    out = advance(s, [p], 600, MarineConfig(step_s=10, transverse_diffusivity_m2_s=50))
    assert np.count_nonzero(out.mobile_solid_m3[:, 9:]) == 0
    assert np.isclose(out.mobile_solid_m3.sum(), 100)


def test_blocked_receiver_backlog_reload_and_reopening(tmp_path):
    base = np.full((7, 12), -5.); base[2:5, 4:7] = 1.
    mobile = np.zeros_like(base); mobile[3, 5] = 20.
    s = grid(base, mobile=mobile)
    p = packet(row=3, col=5, end_s=100)
    cfg = MarineConfig(step_s=10)
    blocked = advance(s, [p], 50, cfg)
    assert blocked.consumed_packets[0]['pending_solid_m3'] == 50
    assert blocked.stranded_solid_m3[3, 5] == 20
    assert blocked.mobile_solid_m3[3, 5] == 0
    path = tmp_path/'blocked.npz'; save_state(path, blocked)
    reopened = advance(load_state(path), [], 50, replace(cfg, sea_level_m=2.))
    assert reopened.consumed_packets[0]['pending_solid_m3'] == 0
    assert reopened.stranded_solid_m3.sum() == 0
    assert np.isclose(reopened.mobile_solid_m3.sum()+reopened.bed_solid_m3.sum(), 120)
    with pytest.raises(ValueError): advance(reopened, [p], 10, cfg)


def test_blocked_mouth_reroutes_only_to_adjacent_ocean():
    base = np.full((7, 12), -5.); base[3, 5] = 1
    s = grid(base)
    out = advance(s, [packet(row=3, col=5)], 10, MarineConfig(step_s=10))
    assert out.consumed_packets[0]['pending_solid_m3'] == 0
    assert out.mobile_solid_m3[3, 6] > 0


def test_deposit_exposes_mouth_then_supply_moves_to_connected_neighbor():
    base = np.full((7, 12), -5.); base[3, 5] = -.001
    p = packet(row=3, col=5, end_s=100, water_m3=10., solid_m3=100.)
    out = advance(grid(base), [p], 100, MarineConfig(step_s=10, settling_rate_s=1., transverse_diffusivity_m2_s=0.))
    assert out.bed_m[3, 5] >= 0
    assert out.bed_solid_m3[3, 6] > 0
    pending = out.consumed_packets[0]['pending_solid_m3']
    assert pending == 0
    assert np.isclose(out.bed_solid_m3.sum()+out.mobile_solid_m3.sum()+out.stranded_solid_m3.sum()+pending, 100)
