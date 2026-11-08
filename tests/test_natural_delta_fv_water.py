import json
import numpy as np
from tools.run_natural_delta_fv_water import run, make_geometry, add_flat_cell_support

def test_fixed_bed_river_sea_face_transfers_close_every_cell(tmp_path):
    parent = tmp_path / 'parent'
    parent.mkdir()
    bed = np.full((4, 5), -0.75)
    types = np.zeros(bed.shape, np.int64)
    types[:, 0] = -1
    types[:, -1] = -1
    types[-1] = -1
    types[0, 2] = 1
    depth = np.full_like(bed, 0.8)
    np.savez(parent / 'result.npz', bed_m=bed[None], depth_m=depth[None], initial_bed_m=bed, cell_type=types)
    (parent / 'summary.json').write_text(json.dumps({'config': {'dx_m': 5.0}}))
    output = tmp_path / 'output'
    summary = run(parent, output, duration_s=1.0, interval_s=0.5, river_q_m3_s=2.0)
    with np.load(output / 'result.npz') as saved:
        np.testing.assert_array_equal(saved['bed_m'], bed)
        np.testing.assert_array_equal(saved['depth_m'][0], depth)
        boundary_cells = saved['boundary_cell']
        kinds = saved['boundary_kind']
        for index in range(2):
            with np.load(output / 'intervals' / f'{index:05d}.npz') as packet:
                transfer = np.zeros(bed.size)
                np.add.at(transfer, saved['face_left'], -packet['internal_transfer_m3'])
                np.add.at(transfer, saved['face_right'], packet['internal_transfer_m3'])
                np.add.at(transfer, boundary_cells, -packet['boundary_transfer_m3'])
                transfer += packet['forcing_volume_m3']
                np.testing.assert_allclose((packet['depth_after_m'] - packet['depth_before_m']) * 25.0, transfer, rtol=0.0, atol=2e-14)
                np.testing.assert_array_equal(packet['boundary_transfer_m3'][kinds == 0], 0.0)
    assert abs(summary['ledger_final_m3'][0] - 2.0) < 1e-12
    assert summary['maximum_abs_water_residual_m3'] < 1e-11

def test_single_subcell_acceleration_matches_flat_cell_evolution_and_fluxes():
    from terrain_pipeline.surface_hydraulics import SurfaceBudget
    from terrain_pipeline.shallow_water import advance_hydrostatic_hll as reference
    from terrain_pipeline.shallow_water import advance_shallow_water_accelerated as accelerated
    bed = np.array([[0.15, -0.3, -0.2, -0.4, -0.6], [0.2, -0.25, 0.05, -0.3, -0.7], [0.25, -0.2, 0.1, -0.25, -0.8], [0.3, -0.1, -0.2, -0.3, -0.8]])
    types = np.zeros(bed.shape, np.int64)
    types[:, -1] = -1
    types[-1] = -1
    geometry = make_geometry(bed, types, 5.0)
    source = np.zeros_like(bed)
    source[0, 1] = 2.0
    outputs, packets = ([], [])
    for advance in (reference, accelerated):
        if advance is accelerated:
            add_flat_cell_support(geometry)
        intervals = []
        outputs.append(advance(geometry, initial_depth_m=np.maximum(-bed, 0.0), forcing_interval_s=1.0, intervals=3, forcing_provider=lambda index: source, boundary_stage_provider=lambda index: np.full(2 * sum(bed.shape), -0.01 * index), source_identity='saved-natural-delta-final-bed', forcing_identity='test', budget=SurfaceBudget(max_dt_s=0.1, max_snapshots=5), snapshot_interval_s=1.0, interval_observer=intervals.append, momentum_observer=lambda packet: None))
        packets.append(intervals)
    for name, expected in outputs[0]['arrays'].items():
        np.testing.assert_allclose(outputs[1]['arrays'][name], expected, atol=2e-12, rtol=2e-12)
    for expected, actual in zip(*packets):
        for name in expected:
            np.testing.assert_allclose(actual[name], expected[name], atol=2e-12, rtol=2e-12)

def test_periodic_sea_boundary_is_applied_and_gross_exchange_closes(tmp_path):
    parent = tmp_path / 'parent'
    parent.mkdir()
    bed = np.full((3, 4), -0.75)
    types = np.zeros(bed.shape, np.int64)
    types[:, -1] = -1
    types[0, 1] = 1
    np.savez(parent / 'result.npz', bed_m=bed[None], depth_m=(-bed)[None], initial_bed_m=bed, cell_type=types)
    (parent / 'summary.json').write_text(json.dumps({'config': {'dx_m': 5.0}}))
    output = tmp_path / 'tide'
    summary = run(parent, output, duration_s=16.0, interval_s=1.0, river_q_m3_s=0.0, tide_amplitude_m=0.1, tide_period_s=16.0, backend='accelerated-v7')
    with np.load(output / 'result.npz') as saved:
        expected = 0.1 * np.sin(2.0 * np.pi * saved['forcing_time_s'] / 16.0)
        np.testing.assert_allclose(saved['sea_stage_at_forcing_times_m'], expected, atol=1e-15)
        np.testing.assert_array_equal(saved['applied_sea_stage_m'], expected[:-1])
        assert saved['interval_sea_imported_m3'].sum() > 0.0
        assert saved['interval_sea_exported_m3'].sum() > 0.0
        assert saved['depth_m'][4].mean() > saved['depth_m'][0].mean()
        assert saved['depth_m'][12].mean() < saved['depth_m'][4].mean()
        for index in range(16):
            with np.load(output / 'intervals' / f'{index:05d}-first-substep.npz') as packet:
                np.testing.assert_array_equal(packet['tailwater_m'], expected[index])
    assert summary['maximum_abs_boundary_exchange_residual_m3'] < 1e-12
    assert summary['maximum_abs_water_residual_m3'] < 1e-11
