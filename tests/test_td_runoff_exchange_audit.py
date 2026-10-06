"""Saved independent accounts reject false storage and stage narratives."""

import unittest

from tests import test_td_basin_runoff_exchange as fixtures
from tools.audit_td_runoff_exchange import audit_arrays, verify_controls


class IndependentRunoffAuditTests(unittest.TestCase):
    def case(self):
        fixture = fixtures.RunoffExchangeTests()
        topology = fixture.topology()
        event = fixture.simulate(topology=topology)
        return topology, fixture.writable(event)

    def test_independent_accounts_pass_actual_event(self):
        topology, event = self.case()
        self.assertTrue(audit_arrays(topology, event)["passed"])

    def test_reject_balanced_global_but_false_leaf_inventory(self):
        topology, event = self.case()
        event["arrays"]["surface_volume_m3"][-1, 0] += .01
        event["arrays"]["surface_volume_m3"][-1, 1] -= .01
        with self.assertRaisesRegex(ValueError, "ledger failed"):
            audit_arrays(topology, event)

    def test_reject_false_stage_despite_identical_water_accounts(self):
        topology, event = self.case()
        event["arrays"]["stage_m"][-1, 0] += .01
        with self.assertRaisesRegex(ValueError, "stage-volume"):
            audit_arrays(topology, event)

    def test_reject_canceling_errors_between_soil_and_fast_stores(self):
        topology, event = self.case()
        event["arrays"]["soil_mm"][-1, 0] += .001
        event["arrays"]["fast_mm"][-1, 0] -= .001
        with self.assertRaisesRegex(ValueError, "component"):
            audit_arrays(topology, event)

    def test_same_event_cannot_be_relabeled_as_finer_controls(self):
        _, event = self.case()
        level = {"level": 1, "controls": {"max_step_s": 150., "rtol": 2.5e-7, "atol_stage_m": 1e-7, "flux_atol_m3": .0005}}
        with self.assertRaisesRegex(ValueError, "actual two-level"):
            verify_controls(event, level)


if __name__ == "__main__":
    unittest.main()
