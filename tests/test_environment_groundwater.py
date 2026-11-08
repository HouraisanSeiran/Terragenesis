import unittest

import numpy as np

from terrain_pipeline import environment_processes as process
from tests.test_environment_mass_processes import context, restored


class GroundwaterTests(unittest.TestCase):
    def test_zero_driver_and_input_unchanged(self):
        ctx = context()
        state = process.groundwater_initial_state(ctx, groundwater_water_m3=1., surface_water_m3=1.)
        result = process.groundwater_step(state, {}, ctx, 1.)
        for name in state:
            np.testing.assert_array_equal(result["state"][name], state[name])
            self.assertFalse(np.shares_memory(result["state"][name], state[name]))

    def test_head_flow_limited_jointly_across_edges(self):
        ctx = context(np.zeros((3, 3)))
        stock = np.zeros((3, 3))
        stock[1, 1] = 1.
        state = process.groundwater_initial_state(ctx, groundwater_water_m3=stock)
        result = process.groundwater_step(state, {"lateral_conductance_m2_s": 100.}, ctx, 100.)
        self.assertLess(result["state"]["groundwater_water_m3"][1, 1], 1.)
        self.assertGreater(np.count_nonzero(result["fluxes"]["lateral_net_m3"] > 0.), 1)
        self.assertGreaterEqual(result["state"]["groundwater_water_m3"].min(), -1e-14)
        self.assertAlmostEqual(result["ledger"]["water_residual_m3"], 0.)

    def test_bidirectional_river_lake_exchange_is_single_transfer(self):
        ctx = context()
        ctx["river_mask"][:] = True
        ctx["lake_mask"] = np.zeros((1, 5), bool)
        ctx["lake_mask"][0, 1] = True
        state = process.groundwater_initial_state(ctx, groundwater_water_m3=1., surface_water_m3=1.)
        head = ctx["height_m"] - 5.
        stage = head.copy()
        stage[0, 0] -= 10.
        stage[0, 1] += 10.
        result = process.groundwater_step(state, dict(surface_stage_m=stage, surface_conductance_m2_s=100.), ctx, 1.)
        exchange = result["fluxes"]["groundwater_to_surface_m3"]
        self.assertEqual(exchange[0, 0], 1.)
        self.assertEqual(exchange[0, 1], -1.)
        self.assertAlmostEqual(result["state"]["surface_water_m3"].sum() +
                               result["state"]["groundwater_water_m3"].sum(), 10.)
        self.assertAlmostEqual(result["ledger"]["water_residual_m3"], 0.)

    def test_recharge_spring_pumping_and_resume(self):
        ctx = context()
        state = process.groundwater_initial_state(ctx)
        forcing = dict(recharge_m3=3., lateral_conductance_m2_s=.001, pumping_request_m3=.2)
        first = process.groundwater_step(state, forcing, ctx, 1.)
        self.assertGreater(first["fluxes"]["spring_m3"].sum(), 0.)
        self.assertAlmostEqual(first["ledger"]["water_residual_m3"], 0.)
        direct = process.groundwater_step(first["state"], forcing, ctx, 1.)
        resumed = process.groundwater_step(restored(first["state"]), forcing, ctx, 1.)
        for name in state:
            np.testing.assert_array_equal(direct["state"][name], resumed["state"][name])

    def test_invalid_yield_and_no_support_input_refused(self):
        ctx = context()
        state = process.groundwater_initial_state(ctx)
        with self.assertRaises(ValueError):
            process.groundwater_step(state, {"specific_yield": 0.}, ctx, 1.)
        ctx["valid_mask"][0, 0] = False
        ctx["receiver"][0, 0] = -1
        with self.assertRaisesRegex(ValueError, "forcing outside"):
            process.groundwater_step(state, {"recharge_m3": 1.}, ctx, 1.)
