import unittest

import numpy as np

from terrain_pipeline.large_scale_surface_network import (
    LargeScaleBudget, build_large_scale_network, estimate_resident_bytes,
    synthetic_terrain_diffusion_height, validate_large_scale_network)


class LargeScaleSurfaceNetworkTests(unittest.TestCase):
    def test_1024_full_coverage_d4_seams_outlets_and_determinism(self):
        height = synthetic_terrain_diffusion_height(1024)
        budget = LargeScaleBudget(tile_size=128, max_resident_bytes=512 * 1024 * 1024)
        first = build_large_scale_network(height, budget=budget)
        second = build_large_scale_network(height, budget=budget)
        np.testing.assert_array_equal(first["arrays"]["receiver"], second["arrays"]["receiver"])
        self.assertEqual(first["metadata"]["tile_count"], 64)
        self.assertGreater(first["metadata"]["cross_tile_receiver_count"], 0)
        self.assertGreater(first["metadata"]["boundary_outlet_count"], 0)
        report = validate_large_scale_network(first, budget=budget)
        self.assertEqual(report["coverage_fraction"], 1.0)
        self.assertEqual(report["cells"], 1024 * 1024)

    def test_2048_cross_tile_generation_with_bounded_estimate(self):
        height = synthetic_terrain_diffusion_height(2048)
        budget = LargeScaleBudget(tile_size=256, max_resident_bytes=512 * 1024 * 1024)
        network = build_large_scale_network(height, budget=budget)
        report = validate_large_scale_network(network, budget=budget)
        self.assertEqual(report["cells"], 2048 * 2048)
        self.assertGreater(report["cross_tile_receiver_count"], 0)
        self.assertLess(report["estimated_resident_bytes"], budget.max_resident_bytes)

    def test_shared_boundaries_are_tile_size_independent(self):
        height = synthetic_terrain_diffusion_height(1024)
        first = build_large_scale_network(height, budget=LargeScaleBudget(tile_size=128))
        second = build_large_scale_network(height, budget=LargeScaleBudget(tile_size=256))
        np.testing.assert_array_equal(first["arrays"]["receiver"], second["arrays"]["receiver"])
        np.testing.assert_array_equal(first["arrays"]["accumulation_cells"],
                                      second["arrays"]["accumulation_cells"])

    def test_memory_budget_rejects_before_allocation(self):
        height = synthetic_terrain_diffusion_height(1024)
        with self.assertRaises(MemoryError):
            build_large_scale_network(height, budget=LargeScaleBudget(max_resident_bytes=1024))
        self.assertGreater(estimate_resident_bytes(1024, 256), 1024)

    def test_invalid_graph_is_rejected(self):
        network = build_large_scale_network(synthetic_terrain_diffusion_height(1024),
                                            budget=LargeScaleBudget(tile_size=256))
        network["arrays"]["receiver"][500, 500] = 500 * 1024 + 500 + 2
        with self.assertRaises(ValueError):
            validate_large_scale_network(network)


if __name__ == "__main__":
    unittest.main()
