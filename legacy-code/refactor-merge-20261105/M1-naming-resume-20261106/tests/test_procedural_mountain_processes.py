import numpy as np
from terrain_pipeline import mountain_forms as processes
from terrain_pipeline.mountain_forms import MountainConfig, rasterize_procedural as rasterize


def test_processes_are_separate_seeded_and_close_budgets(monkeypatch):
    called = []
    real = processes.advance_glacier
    def wrapped(**kwargs):
        called.append(kwargs)
        return real(**kwargs)
    monkeypatch.setattr(processes, 'advance_glacier', wrapped)
    arrays, meta = processes.prepare_process_evidence((0., 0.), 20260903)
    expected = rasterize((0., 0.), (65, 65), 30., MountainConfig(world_seed=20260903))['height_m']
    np.testing.assert_array_equal(arrays['source_height_m'], expected)
    np.testing.assert_array_equal(arrays['glacier_before_m'], expected[32, 28:37])
    assert called and meta['world_seed'] == 20260903
    assert abs(meta['routing']['residual_m3_s']) < 1e-9
    assert abs(meta['diffusion']['volume_delta_m3']) < 1e-6
    assert meta['diffusion']['minimum_floor_margin_m'] >= 0
    assert meta['glacier']['ledger']['ice']['max_abs_residual_m3'] < 1e-6
    np.testing.assert_allclose(arrays['glacier_after_m'], arrays['glacier_before_m'] + arrays['glacier_final_bed_delta_m'])
