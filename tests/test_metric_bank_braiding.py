import unittest

import numpy as np

from terrain_pipeline.surface_rivers.metric_bank_braiding import (
    BankPointbarConfig, BraidedConfig, build_bank_pointbar_candidate,
    build_braided_candidate)
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid


class MetricBankBraidingTests(unittest.TestCase):
    def setUp(self):
        height = np.zeros((9, 9), dtype=np.float64)
        self.terrain = TerrainGrid(height, np.ones(height.shape, dtype=bool), 0., 0., 1., 1.,
                                   "diagnostic_dem_proxy", "fixture", "a" * 64)

    def test_curvature_signs_unknown_protection_and_conservation(self):
        positive = np.array([[2., 2.], [3., 3.], [4., 2.], [5., 1.]], dtype=np.float64)
        negative = np.array([[2., 2.], [3., 1.], [4., 2.], [5., 3.]], dtype=np.float64)
        config = BankPointbarConfig(max_erosion_depth_m=.1, max_deposit_depth_m=.1, porosity=0.)
        first = build_bank_pointbar_candidate(self.terrain, positive, "b" * 64, "c" * 64, 2., config)
        second = build_bank_pointbar_candidate(self.terrain, negative, "b" * 64, "c" * 64, 2., config)
        self.assertTrue(np.any(first["erosion_mask"]))
        self.assertTrue(np.any(second["erosion_mask"]))
        self.assertFalse(np.array_equal(first["erosion_mask"], second["erosion_mask"]))
        ledger = first["solid_ledger"]
        self.assertAlmostEqual(ledger["input_solid_m3"] + ledger["eroded_solid_m3"],
                               ledger["deposited_solid_m3"] + ledger["exported_solid_m3"] + ledger["unresolved_solid_m3"])

    def test_unknown_cells_are_untouched_and_event_is_deterministic(self):
        valid = self.terrain.valid_mask.copy()
        valid[3, 3] = False
        terrain = TerrainGrid(self.terrain.elevation_m.copy(), valid, 0., 0., 1., 1.,
                              "diagnostic_dem_proxy", "fixture", "a" * 64)
        points = np.array([[2., 2.], [3., 2.], [4., 3.], [5., 4.]], dtype=np.float64)
        result = build_bank_pointbar_candidate(terrain, points, "b" * 64, "c" * 64, 1.)
        self.assertFalse(np.any(result["height_delta_m"][~valid]))
        repeat = build_bank_pointbar_candidate(terrain, points, "b" * 64, "c" * 64, 1.)
        self.assertEqual(result["event"].identity_sha256, repeat["event"].identity_sha256)
        self.assertEqual(result["event"].event_type, "bank_migration")

    def test_braided_candidates_are_finite_and_do_not_write_graph(self):
        water = np.zeros((9, 9), dtype=bool)
        water[4, 1:8] = True
        water[3, 2:7] = True
        water[5, 2:7] = True
        path = tuple((4, column) for column in range(1, 8))
        result = build_braided_candidate(self.terrain, path, water, "b" * 64, "c" * 64,
                                         10., 2., BraidedConfig(max_candidates=3, branch_fraction=.2))
        self.assertIn(len(result["candidate_paths"]), (2, 3))
        self.assertAlmostEqual(sum(result["flow_split"]), 1.)
        self.assertFalse(result["routing_graph_written"])
        ledger = result["solid_ledger"]
        self.assertAlmostEqual(ledger["input_solid_m3"], ledger["deposited_solid_m3"] + ledger["unresolved_solid_m3"])
        self.assertEqual(result["event"].event_type, "bifurcation")

    def test_invalid_inputs_rejected(self):
        water = np.ones((9, 9), dtype=bool)
        with self.assertRaises(ValueError):
            build_bank_pointbar_candidate(self.terrain, np.zeros((2, 2), dtype=np.float32), "b" * 64, "c" * 64, 1.)
        with self.assertRaises(ValueError):
            build_braided_candidate(self.terrain, ((0, 0), (0, 2)), water, "b" * 64, "c" * 64, 1., 1.)
        with self.assertRaises(ValueError):
            build_braided_candidate(self.terrain, ((0, 0), (0, 1)), water, "bad", "c" * 64, 1., 1.)


if __name__ == "__main__":
    unittest.main()
