import unittest

import numpy as np

from tools.audit_td_forcing_v10_reference import assert_accounts, reservoir_after
from tools.audit_td_weather_causality import reduce_case


class IndependentForcingReferenceTests(unittest.TestCase):
    def test_closed_form_reservoir_has_correct_limits(self):
        self.assertEqual(reservoir_after(12., 0., 0., 3600.), 12.)
        self.assertAlmostEqual(reservoir_after(12., 0., 3600., 3600.), 12. / np.e)
        self.assertEqual(reservoir_after(15., 15., 7200., 3600.), 15.)

    def test_compartment_audit_rejects_balanced_wrong_transfer(self):
        initial = np.zeros((4, 1))
        states = np.array([[.001], [0.], [0.], [0.]])
        ledger = np.zeros((8, 1))
        ledger[0] = ledger[1] = 1.
        with self.assertRaises(AssertionError):
            assert_accounts(initial, dict(states=states, ledger_mm=ledger))

    def test_transport_causal_audit_checks_cells_and_unmodified_stores(self):
        topology = dict(face_cells=np.array([[0, 1]], np.int64), boundary_cells=np.empty(0, np.int64))
        initial = np.array([[1., 0.], [30., 30.], [0., 0.], [0., 0.]])
        states = initial.copy()
        states[0] = [.75, .25]
        arrays = dict(states=states, errors=np.zeros_like(states), ledger=np.zeros((8, 2)),
                      face_forward_m3=np.array([.25]), face_reverse_m3=np.zeros(1))
        self.assertTrue(reduce_case(initial, arrays, topology, 1., transport_only=True)["budget_passed"])
        states[0] = [.5, .5]
        with self.assertRaises(ValueError):
            reduce_case(initial, arrays, topology, 1., transport_only=True)
        states[0] = [.75, .25]
        states[1] = [29., 31.]
        with self.assertRaises(AssertionError):
            reduce_case(initial, arrays, topology, 1., transport_only=True)


if __name__ == "__main__":
    unittest.main()
