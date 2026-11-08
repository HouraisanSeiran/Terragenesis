import unittest

import numpy as np

from terrain_pipeline.environment_processes import initialize_soil_chemistry as initialize, advance_soil_chemistry as step
from terrain_pipeline.environment_processes import initialize_succession, advance_succession
from tests.environment_ecology_fixtures import assert_same, cold, context, immutable_call


class SoilChemistryTests(unittest.TestCase):
    def test_zero_drivers_and_zero_step(self):
        ctx = context()
        state = initialize(ctx, organic_carbon_kg_m2=0., organic_nutrient_kg_m2=0.)
        assert_same(self, state, immutable_call(self, step, state, {}, ctx, 0.)["state"])
        assert_same(self, state, step(state, {}, ctx, 3600.)["state"])

    def test_evaporation_concentrates_and_precipitates_finite_salt(self):
        ctx = context()
        state = initialize(ctx, water_depth_m=.1, salinity_kg_m3=20.)
        result = immutable_call(self, step, state, {"evaporation_m3_s": 1.}, ctx, 85.)
        self.assertGreater(result["fluxes"]["salinity_kg_m3"][3, 3], 20.)
        dry = step(state, {"evaporation_m3_s": 1.e8}, ctx, 1.)
        self.assertEqual(dry["state"]["water_m3"][3, 3], 0.)
        self.assertGreater(dry["state"]["salt_solid_kg"][3, 3], 0.)
        rewetted = step(dry["state"], {"water_input_m3_s": 100.}, ctx, 10.)
        self.assertLess(rewetted["state"]["salt_solid_kg"][3, 3], dry["state"]["salt_solid_kg"][3, 3])
        for key in ("water_residual_m3", "salt_residual_kg", "carbon_residual_kg", "nutrient_residual_kg"):
            self.assertAlmostEqual(result["ledger"][key], 0., delta=1.e-8)

    def test_leaching_uptake_and_mineralization_cannot_overdraw(self):
        ctx = context()
        state = initialize(ctx, salinity_kg_m3=4.)
        result = step(state, {"drainage_m3_s": 1.e6, "plant_uptake_demand_kg": 1.e20}, ctx, 3600.)
        self.assertGreater(result["ledger"]["salt_leached_kg"], 0.)
        self.assertGreater(result["ledger"]["nutrient_leached_kg"], 0.)
        self.assertTrue(all(np.all(array >= 0.) for array in result["state"].values()))
        self.assertAlmostEqual(result["ledger"]["nutrient_residual_kg"], 0., delta=1.e-9)
        assert_same(self, step(result["state"], {}, ctx, 3600.)["state"],
                    step(cold(result["state"]), {}, ctx, 3600.)["state"])

    def test_soil_actual_uptake_and_salt_stress_change_vegetation(self):
        ctx = context()
        vegetation = initialize_succession(ctx, biomass_carbon_kg_m2=.1)
        results = []
        for salinity in (0., 40.):
            soil = initialize(ctx, salinity_kg_m3=salinity)
            chemistry = step(soil, {"plant_uptake_demand_kg": .1}, ctx, 30. * 86400.)
            recovery = advance_succession(vegetation, {
                "plant_nutrient_uptake_kg": chemistry["fluxes"]["plant_uptake_kg"],
                "plant_stress_factor": chemistry["fluxes"]["plant_stress_factor"]}, ctx, 30. * 86400.)
            returned = step(chemistry["state"], {
                "litter_carbon_kg": recovery["fluxes"]["litter_carbon_kg"],
                "plant_nutrient_return_kg": recovery["fluxes"]["plant_nutrient_return_kg"]}, ctx, 1.)
            self.assertGreater(returned["ledger"]["litter_carbon_kg"], 0.)
            self.assertAlmostEqual(recovery["ledger"]["nutrient_residual_kg"], 0., delta=1.e-9)
            results.append(recovery["fluxes"]["cover_fraction"].sum())
        self.assertGreater(results[0], results[1])

    def test_nonfinite_and_negative_inputs_rejected(self):
        ctx = context()
        with self.assertRaises(ValueError):
            step(initialize(ctx), {"water_input_m3_s": np.nan}, ctx, 1.)
        with self.assertRaises(ValueError):
            step(initialize(ctx), {}, ctx, -1.)
