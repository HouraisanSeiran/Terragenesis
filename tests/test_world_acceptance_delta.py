"""External contracts for same-world mouth selection and water/solid ledgers."""
import numpy as np
import pytest

from terrain_pipeline.world_acceptance_delta import select_mouth, simulate_world_delta


def world_fixture():
    rows, cols = 100, 100
    zz, xx = np.indices((rows, cols))
    ocean = xx >= 65
    receiver = np.full((rows, cols), -1, int)
    q = np.zeros((rows, cols))
    for col in range(10, 65):
        receiver[50, col] = 50*cols+col+1
        q[50, col] = 20.
    receiver[20, 64] = 20*cols+65
    q[20, 64] = 2.
    product = dict(ocean_mask=ocean, receiver=receiver, discharge_m3_s=q,
                   node_x_m=(xx*90).ravel(), node_z_m=(zz*90).ravel())
    nz, nx = np.indices((300, 300))
    native = (65*90-45-nx*30)*.002
    return product, native


def test_selects_actual_largest_ocean_edge_and_upstream_path():
    product, _ = world_fixture()
    mouth, chain, xy, q = select_mouth(product)
    assert mouth == 5064
    assert q == 20.
    assert chain[0] == 5010
    assert chain[-1] == mouth
    assert np.all(product['receiver'].ravel()[chain[:-1]] == chain[1:])
    assert np.array_equal(xy[mouth], [5760., 4500.])


def test_same_world_delta_preserves_original_and_balances_water_and_solid():
    product, native = world_fixture()
    original = native.copy()
    arrays, meta = simulate_world_delta(product, native, [0., 0.], months=1)
    assert np.array_equal(native, original)
    assert meta['actual_upstream_q_m3_s'] == 20.
    assert meta['construction_cut_bulk_m3'] > 0.
    assert meta['construction_fill_bulk_m3'] == 0.
    ledger = meta['ledger']
    assert abs(ledger['balance_residual_solid_m3']) < 1.e-6
    assert ledger['water_terminal_export_m3'] == pytest.approx(ledger['water_input_m3'], rel=1.e-7)
    assert np.any(arrays['wet_mask'] & ~arrays['ocean_mask'])
    assert np.any(arrays['bed_change_m'] > 0.)
    assert np.array_equal(arrays['final_bed_m'][arrays['ocean_mask']], arrays['constructed_bed_m'][arrays['ocean_mask']])
    origin, spacing = arrays['origin_xz_m'], float(arrays['spacing_m'])
    source = arrays['trunk_path_xz_m'][0]
    col, row = np.rint((source-origin)/spacing).astype(int)
    assert arrays['constructed_bed_m'][row, col] == arrays['original_bed_m'][row, col]
    assert arrays['wet_mask'][row, col]
    for name in ['trunk_path_xz_m']+[f'branch{index}_path_xz_m' for index in range(3)]:
        cells = np.rint((arrays[name]-origin)/spacing).astype(int)
        assert np.all(arrays['wet_mask'][cells[:, 1], cells[:, 0]])
    for index in range(3):
        endpoint = arrays[f'branch{index}_path_xz_m'][-1]
        col, row = np.rint((endpoint-origin)/spacing).astype(int)
        assert arrays['ocean_mask'][row, col]
        assert arrays['wet_mask'][row, col]


def test_no_actual_ocean_mouth_is_rejected():
    product, _ = world_fixture()
    product['ocean_mask'][:] = False
    with pytest.raises(ValueError, match='land-to-ocean'):
        select_mouth(product)


def test_inlet_follows_real_flow_jump_and_irregular_graph_junctions_remain_wet():
    product, native = world_fixture()
    product['discharge_m3_s'][50, 10:55] = .001
    product['node_x_m'] = product['node_x_m'].astype(float)+13.
    product['node_z_m'] = product['node_z_m'].astype(float)+11.
    arrays, meta = simulate_world_delta(product, native, [0., 0.], months=1)
    assert meta['inlet_node'] >= 5055
    assert meta['actual_upstream_q_m3_s'] == 20.
    assert all(check['all_wet_in_inlet_component'] for check in meta['wet_connectivity'])
    assert meta['ledger']['water_terminal_export_m3'] == pytest.approx(meta['ledger']['water_input_m3'], rel=1.e-6)
