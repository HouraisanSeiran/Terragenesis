"""Focused checks for optional branch and delta geometry prototypes."""
import unittest
import numpy as np

from terrain_pipeline.surface_rivers.branches import build_branches
from terrain_pipeline.surface_rivers.hydraulics import BranchHydraulics, ChannelHydraulics
from terrain_pipeline.surface_rivers.delta import deposit_delta


class BranchDeltaTests(unittest.TestCase):
    def test_branch_rejoins_and_conserves_discharge(self):
        height = np.full((9, 11), 30.0)
        corridor = np.zeros_like(height, dtype=bool)
        main = [(4, x) for x in range(1, 10)]
        for x, point in enumerate(main, start=1):
            corridor[point] = True
            height[point] = 20-x
        for x in range(2, 9):
            corridor[3, x] = True
            height[3, x] = 20-x-.1
        hydraulics = BranchHydraulics(ChannelHydraulics(2, 2, .03, .01), ChannelHydraulics(2, 1, .03, .01))
        result = build_branches(height, main, corridor, 100, hydraulics=hydraulics)
        self.assertEqual(len(result.paths), 2)
        self.assertEqual(result.paths[0][0], result.paths[1][0])
        self.assertEqual(result.paths[0][-1], result.paths[1][-1])
        self.assertTrue(any(z == 3 for z, _ in result.paths[1]))
        self.assertIn(result.split, main)
        self.assertIn(result.rejoin, main)
        for branch in result.paths:
            self.assertTrue(all(corridor[point] for point in branch))
            self.assertTrue(all(height[b] <= height[a] for a, b in zip(branch, branch[1:])))
        self.assertAlmostEqual(sum(result.fractions), 1)
        self.assertAlmostEqual(sum(result.discharges), 100)

    def test_no_corridor_and_uphill_candidate_remain_single(self):
        height = np.tile(np.arange(10, 0, -1, dtype=float), (7, 1))
        main = [(3, x) for x in range(10)]
        corridor = np.zeros_like(height, dtype=bool)
        corridor[3] = True
        one = build_branches(height, main, corridor, 7)
        self.assertEqual(one.paths, (tuple(main),))
        corridor[2, 1:9] = True
        height[2, 1:9] = 99
        uphill = build_branches(height, main, corridor, 7)
        self.assertEqual(uphill.paths, (tuple(main),))
        self.assertEqual(uphill.discharges, (7,))

    def test_delta_needs_connected_ocean_mouth_and_conserves_solid(self):
        height = np.zeros((15, 15), dtype=float)
        land = np.zeros_like(height, dtype=bool)
        land[:7] = True
        ocean = ~land
        path = [(z, 7) for z in range(4, 12)]
        result = deposit_delta(height, land, ocean, path, 10, porosity=.25, max_radius=4)
        self.assertEqual(result.mouth, (7, 7))
        self.assertTrue(np.all(result.height_delta[land] == 0))
        self.assertTrue(np.all(result.height_delta[~ocean] == 0))
        self.assertGreater(result.deposited_solid, 0)
        self.assertAlmostEqual(result.deposited_solid + result.exported_solid, 10)
        self.assertAlmostEqual(result.deposited_solid,
                               float(result.height_delta.sum() * .75))
        np.testing.assert_array_equal(height, np.zeros_like(height))
        no_ocean = deposit_delta(height, land, np.zeros_like(ocean), path, 10)
        self.assertIsNone(no_ocean.mouth)
        self.assertEqual(no_ocean.deposited_solid, 0)
        self.assertEqual(no_ocean.exported_solid, 10)

    def test_delta_spacing_capacity_and_ocean_component(self):
        height = np.zeros((15, 15), dtype=float)
        land = np.zeros_like(height, dtype=bool)
        land[:7] = True
        ocean = np.zeros_like(land)
        ocean[7:11, 3:10] = True
        ocean[13, 7] = True
        path = [(5, 7), (6, 7), (7, 7)]
        result = deposit_delta(height, land, ocean, path, 200,
                               porosity=.25, max_radius=6, spacing_blocks=2)
        self.assertEqual(result.mouth, (7, 7))
        self.assertEqual(result.height_delta[13, 7], 0)
        self.assertLessEqual(float(result.height_delta.max()), .5 + 1e-10)
        self.assertAlmostEqual(result.deposited_solid,
                               float(result.height_delta.sum() * .75 * 4))
        self.assertAlmostEqual(result.deposited_solid + result.exported_solid, 200)
    def test_internal_lake_is_not_ocean(self):
        height = np.zeros((9, 9), dtype=float)
        land = np.ones_like(height, dtype=bool)
        land[4, 4] = False
        result = deposit_delta(height, land, np.zeros_like(land),
                               [(2, 4), (3, 4), (4, 4)], 2)
        self.assertIsNone(result.mouth)
        self.assertEqual(result.exported_solid, 2)


if __name__ == "__main__":
    unittest.main()