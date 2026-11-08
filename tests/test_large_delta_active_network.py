import numpy as np
import pytest
from terrain_pipeline.large_delta_active_network import build_network, corridor_field, curve_edge


def test_corridor_field_matches_overlapping_world_coordinates():
    full = corridor_field((30, 40), (1200, -3000), 30)
    part = corridor_field((10, 15), (1350, -2790), 30)
    np.testing.assert_allclose(full[7:17, 5:20], part, atol=1e-14)


def test_curve_keeps_other_windows_when_one_has_an_obstacle():
    land = np.ones((100, 180), dtype=bool)
    land[45:50, 55:65] = False
    path = [(50, x) for x in range(10, 160)]
    cells, positions, diagnostics = curve_edge(path, land, [], set(), 30)
    np.testing.assert_array_equal(positions[0], path[0])
    np.testing.assert_array_equal(positions[-1], path[-1])
    assert diagnostics['terrain'] > 0
    assert diagnostics['accepted_windows'] > 0
    assert np.max(np.abs(positions[:, 0] - 50)) > 1
    assert len(cells) == len(set(cells))
    assert np.max(np.abs(np.diff(np.array(cells), axis=0))) <= 1
    assert all(land[p] for p in cells)


def scenario():
    bed = np.ones((200, 100))
    bed[:, 90:] = -1
    original = bed - 2
    deposit = np.full_like(bed, 2.)
    ocean = bed < 0
    q = np.full(3, 20.)
    forcing = dict(time_seconds=np.arange(4)*86400., interval_water_q_m3_s=q,
                   interval_water_m3=q*86400., interval_delivered_solid_m3=np.array([2., 3., 4.]))
    return bed, original, deposit, ocean, forcing


def test_tree_conservation_and_connected_wet_sections():
    bed, original, deposit, ocean, forcing = scenario()
    result, metrics = build_network(bed, original, deposit, (0, 0), 30, (300, 3000), ocean, forcing, 4)
    parent = result['parent']; q = result['branch_q_m3_s']; lines = result['centerline_sections']
    # A straight shoreline need not support several inland bifurcations.
    assert len(result['leaf_indices']) >= 1
    assert q[parent == -1].sum() == pytest.approx(20.)
    for i in range(len(parent)):
        children = np.flatnonzero(parent == i)
        if len(children):
            assert q[children].sum() == pytest.approx(q[i])
            end = lines[lines[:, 0] == i][-1]
            for child in children:
                start = lines[lines[:, 0] == child][0]
                np.testing.assert_allclose(end[2:6], start[2:6])
        section = lines[lines[:, 0] == i]
        assert np.all(section[:, 5] > section[:, 4])
        assert np.all(np.abs(np.diff(np.rint(section[:, 2:4]/30), axis=0)) <= 1)
    assert np.all(result['bed_m'] >= original-3)
    assert metrics['solid_deposited_m3'] > 0
    np.testing.assert_array_equal(result['source_interval_solid_m3'], forcing['interval_delivered_solid_m3'])
    np.testing.assert_allclose(result['daily_branch_solid_in_m3'] + result['solid_storage_m3'][:-1], result['daily_branch_solid_out_m3'] + result['daily_branch_deposited_solid_m3'] + result['solid_storage_m3'][1:])
    assert metrics['max_stage_backstep_m'] < 1e-10
    assert np.all(result['event_bed_change_m'] >= 0)
    for leaf in result['leaf_indices']:
        section = lines[lines[:, 0] == leaf]
        assert np.all(np.diff(section[:, 5]) <= 1e-10)
        x, z = np.rint(section[-1, 2:4]/30).astype(int)
        assert ocean[z, x]
        assert section[-1, 5] == pytest.approx(0.)
    assert metrics['water_input_m3'] + metrics['initial_water_storage_m3'] == pytest.approx(metrics['water_outlet_m3'] + metrics['final_water_storage_m3'])
    assert metrics['solid_input_m3'] == pytest.approx(metrics['solid_outlet_m3'] + metrics['final_mobile_solid_m3'] + metrics['solid_deposited_m3'])
    assert np.sum(result['daily_branch_solid_out_m3'][:, result['leaf_indices']]) <= forcing['interval_delivered_solid_m3'].sum()


def test_rejects_inconsistent_forcing():
    bed, original, deposit, ocean, forcing = scenario()
    forcing['interval_water_m3'][0] += 1
    with pytest.raises(ValueError, match='forcing'):
        build_network(bed, original, deposit, (0, 0), 30, (300, 3000), ocean, forcing)
