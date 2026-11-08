import unittest

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from tools.diagnose_td_river_bottom_budget import necessary_bounds


class BottomBudgetDiagnosisTests(unittest.TestCase):
    def bounds(self, first_high_row):
        height = np.full((11, 11), 100., dtype=float)
        height[first_high_row:] = 110.
        terrain = TerrainGrid(height, np.ones(height.shape, bool), 0., 0., 1., 1.,
                              "observed_dem", "fixture", "a" * 64)
        points = np.array([[2., 5.], [8., 5.]])
        receiver = np.array([1, -1])
        profile = (np.array([0, 2]), np.array([0., 1.]),
                   np.array([100., 100.]), np.array([99., 99.]))
        return necessary_bounds(points, receiver, np.array([6., 6.]), profile,
                                terrain, np.array([57, 63]))

    def test_true_bottom_violation_identifies_world_point_and_required_cut(self):
        result = self.bounds(6)
        bottom = result["edge_strip"]["physical_half_bottom"]
        self.assertGreater(bottom["violations"], 0)
        self.assertGreater(bottom["maximum_required_cut_m"], 10.9)
        worst = bottom["worst"]
        self.assertLessEqual(worst["lateral_distance_m"], 3.)
        self.assertAlmostEqual(worst["necessary_cut_m"],
                               worst["source_height_m"] - worst["highest_center_bed_m"] - worst["transverse_rise_m"])

    def test_guard_conflict_is_separate_from_real_bottom(self):
        result = self.bounds(9)
        self.assertEqual(result["edge_strip"]["physical_half_bottom"]["violations"], 0)
        self.assertGreater(result["edge_strip"]["bottom_guard_shell"]["violations"], 0)
        self.assertGreater(result["node_cap"]["bottom_guard_shell"]["violations"], 0)
