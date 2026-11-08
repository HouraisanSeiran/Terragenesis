from copy import deepcopy
import unittest

import numpy as np

from terrain_pipeline import environment_processes as process
from tests.test_environment_mass_processes import context, restored


class NetworkTransitionTests(unittest.TestCase):
    def setUp(self):
        self.ctx = context([[3., 2., 1., 2., 3.]])
        self.state = process.network_transition_initial_state(self.ctx, water_m3=1., sediment_solid_m3=2., floodplain_solid_m3=3.)

    def test_zero_bed_change_keeps_graph_and_stocks(self):
        result = process.network_transition_step(self.state, {}, self.ctx, 1.)
        self.assertEqual(result["metadata"]["changed_owner_cells"], 0)
        self.assertFalse(result["fluxes"]["receiver_changed_mask"].any())
        self.assertEqual(result["metadata"]["status"], "proposal_requires_explicit_commit")

    def test_real_rerouting_owner_events_commit_and_conservative_stocks(self):
        change = np.array([[0., 0., 4., 0., 0.]])
        result = process.network_transition_step(self.state, {"bed_change_m": change}, self.ctx, 1.)
        self.assertGreater(result["metadata"]["changed_owner_cells"], 0)
        self.assertTrue(result["fluxes"]["receiver_changed_mask"].any())
        np.testing.assert_array_equal(result["state"]["receiver"], self.state["receiver"])
        committed = process.commit_transition(self.state, result, self.ctx)
        self.assertEqual(committed["metadata"]["status"], "committed_separate_revision")
        self.assertFalse(np.array_equal(committed["state"]["receiver"], self.state["receiver"]))
        for name in process.INVENTORIES:
            np.testing.assert_array_equal(committed["state"][name], self.state[name])
            self.assertGreater(result["fluxes"]["reassigned_" + name].sum(), 0.)
        np.testing.assert_array_equal(self.ctx["height_m"], [[3., 2., 1., 2., 3.]])

    def test_resumed_commit_and_next_step(self):
        proposal = process.network_transition_step(self.state, {"bed_change_m": [[0., 0., 4., 0., 0.]]}, self.ctx, 1.)
        first = process.commit_transition(restored(self.state), proposal, self.ctx)["state"]
        new_context = {**self.ctx, "height_m": first["height_m"], "receiver": first["receiver"]}
        direct = process.network_transition_step(first, {}, new_context, 1.)
        resumed = process.network_transition_step(restored(first), {}, new_context, 1.)
        for name in direct["state"]:
            np.testing.assert_array_equal(direct["state"][name], resumed["state"][name])

    def test_tampered_proposal_stale_stock_and_protected_change_refused(self):
        proposal = process.network_transition_step(self.state, {}, self.ctx, 1.)
        forged = deepcopy(proposal)
        forged["fluxes"]["proposed_receiver"][0, 0] = -1
        with self.assertRaisesRegex(ValueError, "proposal graph"):
            process.commit_transition(self.state, forged, self.ctx)
        stale = restored(self.state)
        stale["water_m3"][0, 0] += 1.
        with self.assertRaisesRegex(ValueError, "stale"):
            process.commit_transition(stale, proposal, self.ctx)
        self.ctx["protected_mask"][0, 2] = True
        with self.assertRaisesRegex(ValueError, "protected"):
            process.network_transition_step(self.state, {"bed_change_m": [[0., 0., 1., 0., 0.]]}, self.ctx, 1.)

    def test_flood_source_uphill_edge_is_preserved_with_zero_bed_change(self):
        ctx = context([[0., 1.]])
        ctx["receiver"] = np.array([[1, -1]])
        state = process.network_transition_initial_state(ctx)
        result = process.network_transition_step(state, {}, ctx, 1.)
        np.testing.assert_array_equal(result["fluxes"]["proposed_receiver"], ctx["receiver"])
        np.testing.assert_array_equal(state["owner_terminal_cell"], [[1, 1]])
        self.assertEqual(result["metadata"]["bed_induced_changed_edges"], 0)

    def test_flood_rerouting_cannot_cross_invalid_gap(self):
        ctx = context([[3., 2., 1., 2., 3.]])
        ctx["valid_mask"][0, 2] = False
        ctx["receiver"][0, [1, 2, 3]] = -1
        ctx["routing_policy"] = "source_terminal_flood"
        ctx["source_terminal_mask"] = ctx["receiver"] < 0
        state = process.network_transition_initial_state(ctx)
        result = process.network_transition_step(state, {"bed_change_m": [[1., 0., 0., 0., 0.]]}, ctx, 1.)
        np.testing.assert_array_equal(result["fluxes"]["proposed_owner_terminal_cell"], [[1, 1, -1, 3, 3]])
