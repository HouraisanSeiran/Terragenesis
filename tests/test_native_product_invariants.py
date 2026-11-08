import unittest

import numpy as np

from terrain_pipeline.drainage import check_event_budget as check_event_budget
from terrain_pipeline.drainage import check_routing as check_routing


class NativeProductInvariantTests(unittest.TestCase):
    def test_good_routing_passes(self):
        valid = np.array([True, True, True, True])
        order = np.array([0, 1, 2, 3])
        receiver = np.array([-1, 0, 1, 2])
        self.assertTrue(check_routing(order, receiver, valid)['ok'])

    def test_negative_tail_is_caught(self):
        valid = np.array([True, True, False, True])
        order = np.array([0, 1, 3, -1])
        receiver = np.array([1, 3, -1, -1])
        result = check_routing(order, receiver, valid)
        self.assertFalse(result['ok'])
        self.assertEqual(result['order_negative'], 1)

    def test_receiver_not_downstream_is_caught(self):
        valid = np.array([True, True, True])
        result = check_routing(np.array([0, 1, 2]), np.array([1, 2, -1]), valid)
        self.assertFalse(result['ok'])

    def test_budget_pass_and_fail(self):
        good = dict(budgets=[dict(local_m3=1e8, retained_m3=6e7, terminal_m3=4e7, residual_m3=1e-8)])
        self.assertTrue(check_event_budget(good)['ok'])
        bad = dict(budgets=[dict(local_m3=1e8, retained_m3=6e7, terminal_m3=4e7, residual_m3=5.0)])
        self.assertFalse(check_event_budget(bad)['ok'])
        negative = dict(budgets=[dict(local_m3=1e8, retained_m3=-1., terminal_m3=1e8, residual_m3=0.)])
        self.assertFalse(check_event_budget(negative)['ok'])


if __name__ == '__main__':
    unittest.main()
