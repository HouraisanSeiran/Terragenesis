"""Finite-core gate contracts, independent of the closure algorithm."""
import copy
import unittest

import numpy as np

from terrain_pipeline.surface_rivers.metric_domain_closed_gate import (
    check_domain_closed, check_topology_closed,
)
from terrain_pipeline.surface_rivers.metric_domain_closure import clear_cache
from terrain_pipeline.surface_rivers.metric_domain_pipeline import REASON_ORDER


def topology():
    shape = (5, 5)
    core = np.zeros(shape, bool)
    core[1:4, 1:4] = True
    accepted = np.zeros(shape, bool)
    accepted.flat[[6, 7, 12]] = True
    ocean = ~accepted
    terminal = np.arange(25).reshape(shape)
    terminal.flat[[6, 7]] = 12
    receiver = np.full(shape, -1, np.int64)
    receiver.flat[6] = 7
    receiver.flat[7] = 12
    owner_x = np.full(shape, np.nan)
    owner_z = np.full(shape, np.nan)
    owner_x[accepted] = 2.0
    owner_z[accepted] = 2.0
    return {"shape": shape, "origin_x_m": 0.0, "origin_z_m": 0.0,
            "spacing_m": 1.0, "in_core": core, "accepted": accepted,
            "ocean": ocean, "unresolved": np.zeros(shape, bool),
            "receiver": receiver, "terminal": terminal,
            "owner_outlet_x_m": owner_x, "owner_outlet_z_m": owner_z}


class ClosedGateTests(unittest.TestCase):
    def assert_boundary_refusal(self, t):
        report = check_topology_closed(t, [(1, 1)])
        self.assertFalse(report["passed"])
        self.assertEqual(report["refused_domains"], 1)
        self.assertEqual(report["reason_tally"]["unresolved_border"], 1)
        self.assertEqual(set(report["reason_tally"]), set(REASON_ORDER))
        self.assertEqual(report["domains"][0]["reason"], "unresolved_border")

    def test_three_cell_domain_with_margin_support_is_accepted_and_read_only(self):
        t = topology()
        before = copy.deepcopy(t)
        report = check_topology_closed(t, [(1, 1), (2, 1), (1, 1)])
        self.assertTrue(report["passed"])
        self.assertEqual(report["accepted_points"], 3)
        self.assertEqual(report["accepted_domains"], 1)
        self.assertEqual(report["domains"][0]["core_members"], 3)
        self.assertEqual(report["domains"][0]["kind"], "closed_basin")
        for name, value in t.items():
            np.testing.assert_equal(value, before[name])

    def test_same_domain_margin_land_is_accepted(self):
        t = topology()
        t["ocean"].flat[2] = False
        t["terminal"].flat[2] = 12
        t["receiver"].flat[2] = 7
        t["receiver"].flat[7] = 12
        t["owner_outlet_x_m"][t["accepted"]] = 2.0
        report = check_topology_closed(t, [(1, 1)])
        self.assertTrue(report["passed"])
        self.assertEqual(report["domains"][0]["margin_members"], 1)

    def test_margin_terminal_is_accepted_when_inside_built_tile(self):
        t = topology()
        t["terminal"].flat[[6, 7, 12]] = 2
        t["receiver"].flat[12] = 2
        t["owner_outlet_z_m"][t["accepted"]] = 0.0
        report = check_topology_closed(t, [(1, 1)])
        self.assertTrue(report["passed"])
        self.assertEqual(report["domains"][0]["margin_members"], 0)

    def test_unselected_member_must_have_same_terminal(self):
        t = topology()
        t["terminal"].flat[7] = 7
        self.assert_boundary_refusal(t)

    def test_unselected_member_receiver_must_stay_in_core(self):
        t = topology()
        t["receiver"].flat[7] = 2
        self.assert_boundary_refusal(t)

    def test_unresolved_member_or_terminal_refuses(self):
        for node in (7, 12):
            with self.subTest(node=node):
                t = topology()
                t["unresolved"].flat[node] = True
                self.assert_boundary_refusal(t)

    def test_cycle_and_out_of_range_receiver_refuse(self):
        for receiver in (6, 25, -2):
            with self.subTest(receiver=receiver):
                t = topology()
                t["receiver"].flat[7] = receiver
                self.assert_boundary_refusal(t)

    def test_unselected_bad_domain_does_not_poison_selected_domain(self):
        t = topology()
        t["ocean"].flat[18] = False
        t["accepted"].flat[18] = True
        t["terminal"].flat[18] = 2
        t["owner_outlet_x_m"].flat[18] = 2.0
        t["owner_outlet_z_m"].flat[18] = 0.0
        self.assertTrue(check_topology_closed(t, [(1, 1)])["passed"])
        self.assertFalse(check_topology_closed(t, [(3, 3)])["passed"])

    def test_coastal_and_ocean_keep_existing_reasons(self):
        t = topology()
        t["ocean"].flat[12] = True
        t["accepted"].flat[12] = False
        report = check_topology_closed(t, [(1, 1), (2, 2)])
        self.assertTrue(report["passed"])
        self.assertEqual(report["reason_tally"]["coastal"], 1)
        self.assertEqual(report["reason_tally"]["ocean"], 1)
        self.assertEqual(report["domains"][0]["kind"], "coastal")

    def test_point_outside_snapshot_uses_existing_reason(self):
        report = check_topology_closed(topology(), [(20, 20)])
        self.assertFalse(report["passed"])
        self.assertEqual(report["reason_tally"]["out_of_tile"], 1)

    def test_real_three_cell_domain_and_known_margin_terminal_pass(self):
        self.addCleanup(clear_cache)
        valid = check_domain_closed(20261020, [(170000, 10000)])
        self.assertTrue(valid["passed"])
        self.assertEqual(valid["domains"][0]["core_members"], 3)
        self.assertEqual(valid["domains"][0]["margin_members"], 0)
        margin_terminal = check_domain_closed(20261020, [(40000, 0)])
        self.assertTrue(margin_terminal["passed"])
        self.assertEqual(margin_terminal["domains"][0]["margin_members"], 1)


if __name__ == "__main__":
    unittest.main()
