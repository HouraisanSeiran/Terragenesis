import unittest

import numpy as np

from terrain_pipeline.basin_storage import exchange_strang_two_sweep as exchange
from terrain_pipeline.basin_storage import parameters_strang_split as parameters
from terrain_pipeline.basin_storage import storageimplicit_simulate as simulate_basin_storage
from terrain_pipeline.basin_storage import validate_basin_storage as validate_basin_storage
from tests import test_td_basin_storage as fixtures


class AnalyticFaceTests(unittest.TestCase):
    def test_refinement_compiled_exchange_matches_numpy(self):
        from terrain_pipeline.basin_storage import refinement_compiled_exchange as _compiled_exchange
        faces = np.array([[0, 1], [1, 2], [3, 4], [4, 5], [0, 3], [1, 4], [2, 5]], np.int64)
        first, second = faces[:, 0], faces[:, 1]
        groups = np.where(first // 3 == second // 3, first % 3 % 2, 2 + first // 3 % 2)
        prepared = tuple(np.flatnonzero(groups == group) for group in range(4))
        ordered = np.concatenate(prepared)
        offsets = np.concatenate(([0], np.cumsum([len(values) for values in prepared])))
        bed = np.array([0., 1., .4, 1.8, .1, 1.2])
        depth = np.array([3., 0., .05, 0., 2.4, .1])
        boundary = np.array([0, 5], np.int64)
        width = np.array([60., 60.])
        config = parameters(None)
        for substep in (60, 5, 2.5):
            expected = exchange(depth, bed, faces, boundary, width, 30., substep, config, 3, prepared)
            actual = _compiled_exchange(depth, bed, faces, boundary, width, 30., substep, .6, ordered, offsets)
            for actual_array, expected_array in zip(actual, expected):
                np.testing.assert_allclose(actual_array, expected_array, rtol=1e-12, atol=1e-12)

    def test_pair_exponential_and_threshold_crossing(self):
        config = parameters({"surface_evaporation_mm_h": 0})
        faces = np.array([[0, 1]], np.int64)
        depth, forward, reverse, exported, forward_s, reverse_s = exchange(
            np.array([3., 0.]), np.array([0., 0.]), faces, np.array([], np.int64), np.array([]), 1., 1., config, 2)
        expected = 1.5 * (1 - np.exp(-1.2))
        self.assertAlmostEqual(forward[0], expected)
        np.testing.assert_allclose(depth, [3 - expected, expected])
        depth, forward, reverse, exported, forward_s, reverse_s = exchange(
            np.array([3., 0.]), np.array([0., 2.]), faces, np.array([], np.int64), np.array([]), 1., 1., config, 2)
        expected = 0.5 * (1 - np.exp(-1.2))
        self.assertAlmostEqual(forward[0], expected)
        self.assertEqual(reverse[0], 0)
        self.assertEqual(forward_s[0], 1)
        depth, forward, reverse, exported, forward_s, reverse_s = exchange(
            np.array([3., 0.]), np.array([2., 0.]), faces, np.array([], np.int64), np.array([]), 1., 10., config, 2)
        self.assertAlmostEqual(depth.sum(), 3)
        self.assertGreater(depth[1], 2)
        self.assertGreaterEqual(depth.min(), 0)

    def test_nested_and_recession_same_fixtures(self):
        helper = fixtures.BasinStorageTests()
        topology = helper.topology([[0, 2, 1, 4, 0]])
        for volume, expected in ((2.5, [2, 0, .5, 0, 0]), (4, [7/3, 1/3, 4/3, 0, 0]), (9.5, [4, 2, 3, 0, .5])):
            result = simulate_basin_storage(topology, np.zeros(1), dt_s=7200, initial_depth_m=[[volume, 0, 0, 0, 0]],
                runoff_parameters=fixtures.DRY_SOIL, parameters={"surface_evaporation_mm_h": 0, "substep_s": 10})
            np.testing.assert_allclose(result["arrays"]["depth_m"][-1], expected, atol=1e-9)
            self.assertTrue(validate_basin_storage(result))
        recession = simulate_basin_storage(topology, np.zeros(4), initial_depth_m=[[7/3, 1/3, 4/3, 0, 0]],
            runoff_parameters=fixtures.DRY_SOIL, parameters={"surface_evaporation_mm_h": 200, "substep_s": 10})
        self.assertEqual(recession["arrays"]["wet_pool_count"][0], 1)
        self.assertEqual(recession["arrays"]["wet_pool_count"][-1], 2)
        self.assertTrue(validate_basin_storage(recession))

    def test_matching_groups_non_square_and_bidirectional_ledger(self):
        topology = fixtures.BasinStorageTests().topology([[0, 1, 0, 2], [0, 0, 1, 0]])
        result = simulate_basin_storage(topology, np.array([30., 0.]), initial_depth_m=[[2, 0, 0, 0], [0, 0, 0, 1]],
            runoff_parameters=fixtures.DRY_SOIL, parameters={"surface_evaporation_mm_h": 0, "substep_s": 60})
        self.assertTrue(validate_basin_storage(result))
        self.assertEqual(result["arrays"]["limiter_active_count"].sum(), 0)
        self.assertFalse(result["metadata"]["morphology_flux_ready"])


if __name__ == "__main__":
    unittest.main()
