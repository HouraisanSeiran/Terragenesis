import unittest
from unittest.mock import patch

import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.td_basin_storage_v4 import exchange, parameters
from terrain_pipeline.td_basin_storage_implicit import exchange as v2_exchange
from terrain_pipeline.td_basin_storage_v4 import simulate_basin_storage
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_storage import validate_basin_storage


class ThresholdPairTests(unittest.TestCase):
    def test_high_bed_dry_recipient(self):
        actual, *_ = exchange(np.array([1., 0.]), np.array([2., 0.]), np.array([[0, 1]], np.int64),
            np.array([], np.int64), np.array([]), 1., 1., parameters(None), 2)
        np.testing.assert_allclose(actual, [np.exp(-.6), 1 - np.exp(-.6)], atol=1e-12)

    def test_independent_ode_both_directions_and_crossing(self):
        cases = [([2., 0.], [1., 0.]), ([0., 2.], [0., 1.]), ([2., 0.], [5., 0.]),
                 ([0., 2.], [0., 5.]), ([0., 2.], [4., 0.]), ([2., 0.], [0., 0.]),
                 ([2., 0.], [3., 3.])]
        for beds, initial in cases:
            bed = np.array(beds)
            depth = np.array(initial)

            def ode(time, values):
                head = bed + values
                donor, recipient = (0, 1) if head[0] >= head[1] else (1, 0)
                flow = .6 * max(head[donor] - max(max(bed), head[recipient]), 0.)
                derivative = np.zeros(2)
                derivative[donor] = -flow
                derivative[recipient] = flow
                return derivative

            reference = solve_ivp(ode, (0., 5.), depth, method="DOP853", rtol=1e-12, atol=1e-13)
            actual, forward, reverse, _, forward_s, reverse_s = exchange(depth, bed,
                np.array([[0, 1]], np.int64), np.array([], np.int64), np.array([]), 1., 5., parameters(None), 2)
            np.testing.assert_allclose(actual, reference.y[:, -1], atol=1e-9, rtol=0)
            self.assertAlmostEqual(actual.sum(), depth.sum(), places=12)
            self.assertTrue(np.all(actual >= 0))
            self.assertTrue(np.all(forward_s + reverse_s <= 5.))

    def test_compiled_v2_differential_matching_and_boundary(self):
        random = np.random.default_rng(20261002)
        grid = np.arange(15).reshape(3, 5)
        faces = np.vstack((np.column_stack((grid[:, :-1].ravel(), grid[:, 1:].ravel())),
                           np.column_stack((grid[:-1].ravel(), grid[1:].ravel())))).astype(np.int64)
        for duration in (60., 5., 2.5, 1.25):
            for case in range(10):
                depth = random.uniform(0, 8, 15)
                bed = random.uniform(1300, 1400, 15)
                inputs = (depth, bed, faces, np.array([0, 14], np.int64), np.array([60., 30.]),
                          30., duration, parameters(None), 5)
                actual = exchange(*inputs)
                expected = v2_exchange(*inputs)
                for got, wanted in zip(actual, expected):
                    np.testing.assert_allclose(got, wanted, atol=1e-9, rtol=1e-11)
                self.assertAlmostEqual(actual[0].sum() * 900 + actual[3].sum(), depth.sum() * 900, places=8)

    def test_v4_saved_validation_never_advances_compiled_kernel(self):
        hierarchy = build_basin_hierarchy(make_td_source(np.array([[2., 0.]]), spacing_m=1))
        result = simulate_basin_storage(hierarchy, np.array([0.]), dt_s=10,
                                        initial_depth_m=np.array([[1., 0.]]))
        with patch("terrain_pipeline.td_basin_storage_v4._compiled_exchange", side_effect=AssertionError("no JIT")):
            self.assertTrue(validate_basin_storage(result))
        self.assertEqual(result["metadata"]["algorithm"], "D4-threshold-exact-Strang-v4")
        self.assertFalse(result["metadata"]["hydraulic_ready"])

    def test_independent_work_budget_rejected(self):
        with self.assertRaises(ValueError):
            parameters({"max_work_face_steps": 6_000_000_001})


if __name__ == "__main__":
    unittest.main()
