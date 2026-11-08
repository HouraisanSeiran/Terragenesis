"""Analytic and graph-path tests for independent audit references."""
import math
import unittest
import numpy as np

from tools.native_30m_graph_reference import independent_accumulation
from tools.native_30m_section_reference import normal_depth_reference


class IndependentGraphTests(unittest.TestCase):
    def fixture(self):
        # 0 -> 2 <- 1; 2 -> 3; 4 independent terminal.
        return (np.array([[2, 2, 3, -1, -1]], np.int64), np.ones((1, 5)),
                np.ones((1, 5), bool), np.array([[True, False, False, False, False]]))

    def test_known_flow_and_exact_downstream_unknown(self):
        args = self.fixture()
        saved = [x.copy() for x in args]
        q, complete, count = independent_accumulation(*args)
        np.testing.assert_array_equal(q, [[1., 1., 3., 4., 1.]])
        np.testing.assert_array_equal(complete, [[False, True, False, False, True]])
        self.assertEqual(count, 5)
        for one, two in zip(args, saved):
            np.testing.assert_array_equal(one, two)

    def test_independent_per_source_path_oracle(self):
        rec = np.array([[3, 3, 4, 5, 5, 6, -1]], np.int64)
        local = np.array([[.1, .2, .3, .4, .5, .6, .7]])
        expected = np.zeros(7)
        for start in range(7):
            cell = start
            while cell >= 0:
                expected[cell] += local.ravel()[start]
                cell = rec.ravel()[cell]
        q, _, _ = independent_accumulation(rec, local, np.ones_like(rec, bool), np.zeros_like(rec, bool))
        np.testing.assert_allclose(q.ravel(), expected, rtol=1e-14, atol=1e-14)

    def test_cycle_self_target_and_inactive_target(self):
        rec, q, valid, dirty = self.fixture()
        for replacement in (np.array([[1, 0, -1, -1, -1]], np.int64),
                            np.array([[0, -1, -1, -1, -1]], np.int64)):
            with self.assertRaises(ValueError):
                independent_accumulation(replacement, q, valid, dirty)
        valid[0, 2] = False
        q[0, 2] = 0
        rec[0, 2] = -1
        with self.assertRaisesRegex(ValueError, 'inactive receiver target'):
            independent_accumulation(rec, q, valid, dirty)

    def test_inactive_is_not_terminal(self):
        rec, q, valid, dirty = self.fixture()
        valid[0, 4] = False
        q[0, 4] = 0.
        result, complete, processed = independent_accumulation(rec, q, valid, dirty)
        self.assertEqual(result[0, 4], 0.)
        self.assertFalse(complete[0, 4])
        self.assertEqual(processed, 4)


class IndependentDepthTests(unittest.TestCase):
    def test_known_one_meter_depth(self):
        target = (1/3)**(2/3)
        self.assertAlmostEqual(normal_depth_reference(target, 1., 1., 1.), 1., places=14)

    def test_increasing_discharge_decreasing_slope(self):
        a = normal_depth_reference(10., 20., .01, .035)
        self.assertGreater(normal_depth_reference(20., 20., .01, .035), a)
        self.assertLess(normal_depth_reference(10., 20., .02, .035), a)

    def test_returned_depth_reproduces_conveyance(self):
        for q, w, slope, n in ((.01, 1., .001, .04), (15., 55., .02, .035), (200., 100., .0001, .03)):
            d = normal_depth_reference(q, w, slope, n)
            area = w*d
            calculated = area*(area/(w+2*d))**(2/3)*math.sqrt(slope)/n
            self.assertAlmostEqual(calculated/q, 1., places=13)

    def test_invalid_inputs_refused(self):
        for bad in (0., -1., True, float('nan'), float('inf')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normal_depth_reference(bad, 1., 1., 1.)


if __name__ == '__main__':
    unittest.main()
