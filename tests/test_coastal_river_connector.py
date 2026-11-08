import numpy as np
from scipy.ndimage import label
from terrain_pipeline.coastal_river_connector import connect, refine_valley, deliver_scenario, reconcile_sections


def test_connection_preserves_port_and_accounts_cut():
    terrain = np.full((31, 101), 5.)
    terrain[:, -1] = -1.
    original = terrain.copy()
    result = connect(terrain, (0., 0.), 10., [[0., 150.], [1000., 150.]])
    np.testing.assert_array_equal(terrain, original)
    assert result['bed_m'][15, -1] == -1.
    assert np.isclose(result['removed_bulk_m3'], result['cut_m'].sum() * 100)
    assert result['width_m'] < 100
    assert np.all(np.diff(result['stage_m']) <= 0)
    components, _ = label(result['wet'], structure=np.ones((3, 3)))
    assert components[15, 0] == components[15, -1] != 0


def test_rejects_path_outside_source():
    import pytest
    with pytest.raises(ValueError, match='outside'):
        connect(np.ones((3, 3)), (0., 0.), 10., [[0., 0.], [30., 0.]])


def test_valley_search_follows_low_ground_with_fixed_endpoints():
    terrain = np.full((21, 41), 40.)
    terrain[10, :] = 0.
    terrain[10, 12:29] = 40.
    terrain[9, 10:31] = 0.
    path, deviation = refine_valley(terrain, (0., 0.), 30.,
                                    [[0., 300.], [1200., 300.]], corridor_m=90.)
    np.testing.assert_array_equal(path[[0, -1]], [[0., 300.], [1200., 300.]])
    assert np.any(path[:, 1] == 270.)
    assert deviation <= 90.


def test_packet_counts_only_arrived_and_rejects_reuse():
    import pytest
    from terrain_pipeline.coastal_marine_sediment import make_state
    shape = (5, 5); seeds = np.zeros(shape, bool); seeds[0, 0] = True
    state = make_state(base_bed_m=np.full(shape, -2.), bed_solid_m3=0.,
        mobile_solid_m3=0., porosity=.4, valid_mask=np.ones(shape, bool),
        ocean_seed_mask=seeds, spacing_m=100., origin_xz_m=(0., 0.), source_identity='test', time_s=100.)
    kwargs = dict(input_id='one', duration_s=100., travel_time_s=20., q_m3_s=10.,
                  solid_rate_m3_s=.5, width_m=10., depth_m=2., inlet_zx=(2, 2))
    final, ledger = deliver_scenario(state, **kwargs)
    assert final.time_s == 200.
    assert ledger['marine_delivered_water_m3'] == 800.
    assert ledger['in_transit_solid_m3'] == 10.
    with pytest.raises(ValueError, match='duplicate'):
        deliver_scenario(final, **kwargs)


def test_hydraulic_control_responds_to_discharge():
    terrain = np.tile(np.linspace(20., -1., 101), (31, 1))
    small = connect(terrain, (0., 0.), 10., [[0., 150.], [1000., 150.]], q_m3_s=30., hydraulic=True)
    large = connect(terrain, (0., 0.), 10., [[0., 150.], [1000., 150.]], q_m3_s=150., hydraulic=True)
    assert large['width_m'] > small['width_m']
    assert large['control_depth_m'] != small['control_depth_m']
    closed = reconcile_sections(large, (0., 0.), 10.)
    assert np.min(closed['section_node_capacity_m3_s']) >= 150.
    assert closed['stage_m'][-1] == large['stage_m'][-1]


def test_restart_delivers_transit_once_and_preserves_unknown(tmp_path):
    import pytest
    from terrain_pipeline.coastal_river_connector import deliver_packets
    from terrain_pipeline.coastal_marine_sediment import RiverPacket, make_state, save_state, load_state
    shape = (5, 5)
    seeds = np.zeros(shape, bool)
    seeds[0, 0] = True
    state = make_state(base_bed_m=np.full(shape, -2.), bed_solid_m3=0., mobile_solid_m3=0.,
        porosity=.4, valid_mask=np.ones(shape, bool), ocean_seed_mask=seeds,
        spacing_m=100., origin_xz_m=(0., 0.), source_identity='test')
    packet = RiverPacket('finite', 'source', 0., 100., 2, 2, 1000., 50., True, (1., 0.), 10., 2.)
    unknown = RiverPacket('unknown', 'source', 0., 100., 2, 2, None, None, False, (1., 0.), 10., 2.)
    whole = deliver_packets(state, [packet, unknown], duration_s=200., travel_time_s=40.)
    first = deliver_packets(state, [packet, unknown], duration_s=100., travel_time_s=40.)
    save_state(tmp_path / 'marine.npz', first)
    restored = load_state(tmp_path / 'marine.npz')
    second = deliver_packets(restored, [], duration_s=100., travel_time_s=40.)
    assert second.water_input_m3 == pytest.approx(whole.water_input_m3)
    assert second.consumed_packets[0]['delivered_solid_m3'] == pytest.approx(50.)
    assert second.consumed_packets[1]['delivered_solid_m3'] is None
    def inventory(s):
        return (s.bed_solid_m3.sum() + s.mobile_solid_m3.sum()
                + s.stranded_solid_m3.sum() + s.exported_solid_m3 + s.unresolved_solid_m3)
    assert inventory(second) == pytest.approx(inventory(whole))
    third = deliver_packets(second, [], duration_s=100., travel_time_s=40.)
    assert third.water_input_m3 == pytest.approx(1000.)
    with pytest.raises(ValueError):
        deliver_packets(second, [packet], duration_s=100., travel_time_s=40.)


def test_reconcile_varied_width_keeps_port_and_capacity():
    terrain = np.tile(np.linspace(20., -3., 201), (81, 1))
    for discharge in (30., 150., 600.):
        result = connect(terrain, (0., 0.), 10., [[0., 400.], [2000., 400.]],
                         q_m3_s=discharge, hydraulic=True)
        closed = reconcile_sections(result, (0., 0.), 10., q_m3_s=discharge)
        assert closed['section_node_capacity_m3_s'].min() >= discharge
        assert closed['stage_m'][-1] == result['stage_m'][-1]
