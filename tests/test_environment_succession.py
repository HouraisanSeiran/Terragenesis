import unittest

import numpy as np

from terrain_pipeline.environment_processes import initialize_succession as initialize, advance_succession as step
from tests.environment_ecology_fixtures import assert_same, cold, context, immutable_call


class SuccessionTests(unittest.TestCase):
    def test_zero_step_and_zero_nutrient_have_no_growth(self):
        ctx = context()
        state = initialize(ctx, biomass_carbon_kg_m2=2., dead_carbon_kg_m2=1.)
        result = immutable_call(self, step, state, {}, ctx, 0.)
        assert_same(self, state, result["state"])
        no_nutrient = step(state, {}, ctx, 86400.)
        self.assertEqual(no_nutrient["ledger"]["photosynthesis_carbon_kg"], 0.)
        self.assertEqual(no_nutrient["ledger"]["fire_atmosphere_carbon_kg"], 0.)

    def test_fire_consumes_finite_fuel_and_closes_carbon_nutrient(self):
        ctx = context()
        state = initialize(ctx, biomass_carbon_kg_m2=2., dead_carbon_kg_m2=1.)
        forcing = {"fire_hazard_s": .01, "plant_nutrient_uptake_kg": 0.}
        result = immutable_call(self, step, state, forcing, ctx, 86400.)
        self.assertGreater(result["ledger"]["fire_atmosphere_carbon_kg"], 0.)
        self.assertGreater(result["state"]["char_carbon_kg"].sum(), 0.)
        self.assertLess(result["state"]["biomass_carbon_kg"].sum(), state["biomass_carbon_kg"].sum())
        for name in ("carbon_residual_kg", "nutrient_residual_kg"):
            self.assertAlmostEqual(result["ledger"][name], 0., delta=1.e-8)
        self.assertGreaterEqual(result["state"]["biomass_carbon_kg"].min(), 0.)
        self.assertEqual(result["state"]["biomass_carbon_kg"][0, 0], state["biomass_carbon_kg"][0, 0])

    def test_recovery_consumes_nutrient_and_increases_root_roughness(self):
        ctx = context()
        state = initialize(ctx, biomass_carbon_kg_m2=.1)
        forcing = {"plant_nutrient_uptake_kg": np.full((7, 7), 1.),
                   "plant_stress_factor": 1., "water_available_fraction": 1., "temperature_c": 20.}
        recovered = step(state, forcing, ctx, 30. * 86400.)
        stressed = step(state, dict(forcing, plant_stress_factor=0.), ctx, 30. * 86400.)
        self.assertGreater(recovered["fluxes"]["root_cohesion_pa"].sum(), stressed["fluxes"]["root_cohesion_pa"].sum())
        self.assertGreater(recovered["fluxes"]["manning_n"].sum(), stressed["fluxes"]["manning_n"].sum())
        self.assertLessEqual(recovered["fluxes"]["nutrient_assimilated_kg"].sum(), 49.)
        self.assertAlmostEqual(recovered["ledger"]["nutrient_residual_kg"], 0., delta=1.e-10)
        assert_same(self, step(recovered["state"], forcing, ctx, 86400.)["state"],
                    step(cold(recovered["state"]), forcing, ctx, 86400.)["state"])

    def test_invalid_hazard_rejected(self):
        ctx = context()
        with self.assertRaises(ValueError):
            step(initialize(ctx), {"fire_hazard_s": -1.}, ctx, 1.)
