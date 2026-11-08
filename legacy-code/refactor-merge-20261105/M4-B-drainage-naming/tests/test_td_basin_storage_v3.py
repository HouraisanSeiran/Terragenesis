import unittest

import numpy as np
from scipy.integrate import solve_ivp

from terrain_pipeline.basin_storage import exchange_event_threshold as exchange
from terrain_pipeline.basin_storage import parameters_event_strang as parameters


class V3Tests(unittest.TestCase):
    def test_cross_sill_exact_event_matches_threshold_ode(self):
        bed = np.array([0., 2.])
        initial = np.array([4., 0.])
        faces = np.array([[0, 1]], dtype=np.int64)
        config = parameters({"surface_evaporation_mm_h": 0})
        rate = .6

        def derivative(_, values):
            head = bed + values
            difference = head[0] - head[1]
            if difference <= 0:
                return np.zeros(2)
            flow = rate * max(difference - max(0., bed[1] - head[1]), 0)
            return np.array([-flow, flow])

        reference = solve_ivp(derivative, (0, 60), initial, rtol=1e-12, atol=1e-13, max_step=.001)
        actual, forward, reverse, _, _, _ = exchange(initial, bed, faces, np.array([], dtype=np.int64),
            np.array([]), 1., 60., config, 2)
        np.testing.assert_allclose(actual, reference.y[:, -1], atol=2e-5)
        self.assertGreater(forward[0], 0)
        self.assertEqual(reverse[0], 0)
        self.assertAlmostEqual(actual.sum(), initial.sum(), places=12)

    def test_event_formula_does_not_use_partial_excess_as_initial_difference(self):
        bed = np.array([0., 2.])
        faces = np.array([[0, 1]], dtype=np.int64)
        config = parameters(None)
        actual, *_ = exchange(np.array([4., 0.]), bed, faces, np.array([], dtype=np.int64), np.array([]), 1., 1., config, 2)
        difference = 4 - 2
        expected = difference / 2 * (1 - np.exp(-2 * .6))
        self.assertAlmostEqual(4 - actual[0], expected, places=12)

    def test_random_matching_is_positive_and_conservative(self):
        rng = np.random.default_rng(20261002)
        for _ in range(30):
            rows, columns = 3, 5
            ids = np.arange(rows * columns).reshape(rows, columns)
            faces = np.vstack((np.column_stack((ids[:, :-1].ravel(), ids[:, 1:].ravel())),
                np.column_stack((ids[:-1].ravel(), ids[1:].ravel())))).astype(np.int64)
            first, second = faces[:, 0], faces[:, 1]
            groups = np.where(first // columns == second // columns, first % columns % 2, 2 + first // columns % 2)
            prepared = tuple(np.flatnonzero(groups == group) for group in range(4))
            actual, forward, reverse, _, forward_s, reverse_s = exchange(rng.uniform(0, 5, rows * columns),
                rng.uniform(1300, 1400, rows * columns), faces, np.array([], dtype=np.int64), np.array([]), 30., 2.5,
                parameters(None), columns, prepared)
            self.assertTrue(np.isfinite(actual).all())
            self.assertGreaterEqual(actual.min(), 0)
            self.assertAlmostEqual(actual.sum(), actual.sum(), places=12)
            self.assertTrue(np.all(forward_s + reverse_s <= 2.5 + 1e-12))


if __name__ == "__main__":
    unittest.main()
