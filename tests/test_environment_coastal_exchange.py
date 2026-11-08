import unittest

import numpy as np

from terrain_pipeline.environment_processes import initialize_coastal_exchange as initialize, advance_coastal_exchange as step
from tests.environment_ecology_fixtures import assert_same, cold, context, immutable_call


class CoastalExchangeTests(unittest.TestCase):
    def test_zero_forcing_preserves_prism_salt_bed(self):
        ctx = context()
        state = initialize(ctx)
        result = immutable_call(self, step, state, {}, ctx, 3600.)
        for name in ("water_m3", "salt_kg", "bed_solid_m3", "bed_m"):
            np.testing.assert_array_equal(state[name], result["state"][name])
        assert_same(self, state, step(state, {}, ctx, 0.)["state"])

    def test_tide_has_signed_flood_ebb_and_finite_salt_ledger(self):
        ctx = context()
        state = initialize(ctx)
        result = step(state, {"tide_amplitude_m": .5, "tide_period_s": 3600.}, ctx, 3600.)
        self.assertGreater(result["fluxes"]["flood_water_m3"].sum(), 0.)
        self.assertGreater(result["fluxes"]["ebb_water_m3"].sum(), 0.)
        for key in ("water_residual_m3", "salt_residual_kg", "solid_residual_m3"):
            self.assertAlmostEqual(result["ledger"][key], 0., delta=1.e-8)
        self.assertGreaterEqual(result["state"]["salt_kg"].min(), 0.)

    def test_freshwater_dilution_wave_transfer_and_explicit_river_solid(self):
        ctx = context()
        state = initialize(ctx)
        mouth = np.zeros((7, 7), bool)
        mouth[3, 4] = True
        forcing = {"mouth_mask": mouth, "river_boundary_water_m3_s": mouth * .1,
                   "river_boundary_solid_m3_s": mouth * .001, "wave_height_m": 1.,
                   "wave_direction_xz": (1., 1.)}
        result = immutable_call(self, step, state, forcing, ctx, 3600.)
        self.assertLess(result["fluxes"]["salinity_kg_m3"][3, 4], 35.)
        self.assertAlmostEqual(result["ledger"]["river_water_input_m3"], 360.)
        self.assertAlmostEqual(result["ledger"]["river_solid_input_m3"], 3.6)
        self.assertGreater(result["ledger"]["gross_wave_transfer_solid_m3"], 0.)
        self.assertGreater(np.abs(result["state"]["bed_m"] - state["bed_m"]).max(), 0.)
        self.assertGreaterEqual(result["state"]["bed_solid_m3"].min(), 0.)
        for key in ("water_residual_m3", "salt_residual_kg", "solid_residual_m3"):
            self.assertAlmostEqual(result["ledger"][key], 0., delta=1.e-7)
        assert_same(self, step(result["state"], forcing, ctx, 100.)["state"],
                    step(cold(result["state"]), forcing, ctx, 100.)["state"])

    def test_unknown_dry_barrier_cannot_be_flooded_from_scene_edge(self):
        ctx = context()
        ctx["valid_mask"][:, 4] = False
        ctx["height_m"][:, :4] = -.1
        state = initialize(ctx)
        self.assertEqual(state["water_m3"][:, :4].sum(), 0.)
        result = step(state, {"tide_amplitude_m": 1.}, ctx, 3600.)
        self.assertEqual(result["state"]["water_m3"][:, :4].sum(), 0.)

    def test_unlabelled_river_input_rejected(self):
        ctx = context()
        with self.assertRaises(ValueError):
            step(initialize(ctx), {"river_boundary_water_m3_s": 1.}, ctx, 1.)
