import unittest
import numpy as np

from terrain_pipeline.surface_domain import LargeBenchmarkBudget, prepare_large_static, run_one_step_storage, validate_large_static


class LargeSurfaceNetworkBenchmarkTests(unittest.TestCase):
    def test_1024_static_tiles_crossings_and_outlets_are_deterministic(self):
        rows = np.arange(1024, dtype=np.float64)[:, None]
        columns = np.arange(1024, dtype=np.float64)[None, :]
        height = rows + columns
        budget = LargeBenchmarkBudget(tile_cells=256, max_resident_bytes=256 * 1024 * 1024)
        first = prepare_large_static(height, spacing_m=30., origin_m_xz=[100., 200.], budget=budget)
        second = prepare_large_static(height, spacing_m=30., origin_m_xz=[100., 200.], budget=budget)
        for key in first["arrays"]:
            np.testing.assert_array_equal(first["arrays"][key], second["arrays"][key])
        self.assertEqual(first["metadata"]["tile_count"], 16)
        self.assertGreater(first["arrays"]["crossing_donor"].size, 0)
        self.assertEqual(validate_large_static(first)["cells"], 1024 * 1024)

    def test_step_storage_is_tile_partitioned_and_bounded(self):
        height = np.zeros((1024, 1024), np.float32)
        static = prepare_large_static(height, budget=LargeBenchmarkBudget(tile_cells=256))
        result = run_one_step_storage(static, forcing_m3_s=.01, duration_s=900.)
        self.assertEqual(result["arrays"]["tile_input_volume_m3"].shape, (16,))
        self.assertAlmostEqual(float(result["arrays"]["total_input_volume_m3"]), 9437184., places=8)

    def test_rejects_non_terrain_diffusion_or_large_budget(self):
        with self.assertRaises(ValueError):
            prepare_large_static(np.zeros((512, 512), np.float64))
        with self.assertRaises(ValueError):
            prepare_large_static(np.zeros((1024, 1024), np.int16))
        with self.assertRaises(ValueError):
            prepare_large_static(np.zeros((1024, 1024), np.float64), budget=LargeBenchmarkBudget(max_cells=1024))


if __name__ == "__main__":
    unittest.main()
