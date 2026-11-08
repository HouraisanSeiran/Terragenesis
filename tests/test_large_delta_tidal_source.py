import numpy as np
from pathlib import Path
from terrain_pipeline.large_delta_tidal_source import active_layer, load_source


def test_active_layer_is_finite_and_disjoint():
    original = np.array([0., 0., 0., 10., 0.])
    formed = np.array([.1, 1., 0., 10., 0.])
    initial = np.array([.1, .5, 0., 10., -.5])
    layer = active_layer(original, formed, np.array([.1, 1., 0., 0., 0.]), initial,
                         np.array([True, False, True, False, False]), np.ones(5, bool))
    np.testing.assert_allclose(layer['formation_cover_m'], [.1, .25, 0, 0, 0])
    np.testing.assert_allclose(layer['marine_assumed_m'], [.15, 0, .25, 0, 0])
    np.testing.assert_allclose(layer['channel_assumed_m'], [0, 0, 0, 0, .25])
    np.testing.assert_allclose(layer['floor_m'], [-.15, .25, -.25, 10, -.75])


def test_saved_source_is_pre_event_and_has_single_forcing():
    root = Path(__file__).resolve().parents[1]
    source = load_source(root / '.scratch/delta-tides-bars-20261102/source-v1/source-manifest.json')
    with np.load(root / '.scratch/large-delta-20261101/active-network-v12/network.npz') as n:
        np.testing.assert_array_equal(source['initial_bed_m'], n['initial_channel_bed_m'])
        np.testing.assert_array_equal(source['sections'], n['initial_centerline_sections'])
        assert np.any(source['initial_bed_m'] != n['bed_m'])
        np.testing.assert_array_equal(source['forcing']['interval_water_m3'], n['source_interval_water_m3'])
        np.testing.assert_array_equal(source['forcing']['interval_delivered_solid_m3'], n['source_interval_solid_m3'])
    assert source['manifest']['world_seed'] == 20261020
    assert len(source['reach_segments']) == 5 and source['sea_anchors_xz_m'].shape == (3, 2)
    assert source['forcing']['time_seconds'][-1] == 30 * 86400
    assert np.isclose(source['forcing']['interval_delivered_solid_m3'].sum(), 161.61942082569308)
    assert source['manifest']['formation_solid_m3']['placed'] == 668512432.9733305
    assert source['manifest']['construction_excavation']['deposit_excavation_solid_m3'] > 0
    assert source['manifest']['external_sediment'] == 'unknown'
    assert np.all(source['active_layer']['floor_m'] <= source['initial_bed_m'])
