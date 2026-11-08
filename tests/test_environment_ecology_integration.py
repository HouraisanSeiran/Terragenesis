"""Actual process-to-process inventory transfers, separate from TD acceptance."""
import unittest

import numpy as np

from terrain_pipeline import environment_processes as coast
from terrain_pipeline import environment_processes as soil
from terrain_pipeline import environment_processes as vegetation
from terrain_pipeline import environment_processes as habitat
from tests.environment_ecology_fixtures import context


def carbon(plant, ground):
    return float(sum(plant[name].sum() for name in
                     ("biomass_carbon_kg", "dead_carbon_kg", "char_carbon_kg"))
                 + ground["organic_carbon_kg"].sum())


def nutrient(plant, ground):
    return float(plant["plant_nutrient_kg"].sum()
                 + ground["nutrient_kg"].sum() + ground["organic_nutrient_kg"].sum())


class EcologyIntegrationTests(unittest.TestCase):
    def test_soil_vegetation_return_packets_conserve_shared_carbon_and_nutrient(self):
        ctx = context()
        plant = vegetation.initialize_succession(ctx, biomass_carbon_kg_m2=2., dead_carbon_kg_m2=.2)
        ground = soil.initialize_soil_chemistry(ctx)
        before_c = carbon(plant, ground)
        before_n = nutrient(plant, ground)
        chemistry = soil.advance_soil_chemistry(ground, {"plant_uptake_demand_kg": .1}, ctx, 86400.)
        ecology = vegetation.advance_succession(plant, {
            "plant_nutrient_uptake_kg": chemistry["fluxes"]["plant_uptake_kg"],
            "plant_stress_factor": chemistry["fluxes"]["plant_stress_factor"],
            "fire_hazard_s": 1.e-7}, ctx, 86400.)
        returned = soil.advance_soil_chemistry(chemistry["state"], {
            "plant_nutrient_return_kg": ecology["fluxes"]["plant_nutrient_return_kg"],
            "litter_carbon_kg": ecology["fluxes"]["litter_carbon_kg"]}, ctx, 1.)
        expected_c = (before_c + ecology["ledger"]["photosynthesis_carbon_kg"]
                      - ecology["ledger"]["fire_atmosphere_carbon_kg"]
                      - chemistry["ledger"]["respired_carbon_kg"]
                      - returned["ledger"]["respired_carbon_kg"])
        self.assertAlmostEqual(carbon(ecology["state"], returned["state"]), expected_c, delta=1.e-8)
        self.assertAlmostEqual(nutrient(ecology["state"], returned["state"]), before_n, delta=1.e-9)

    def test_coast_debits_actual_soil_water_salt_packet_then_ecology_consumes_stress(self):
        ctx = context()
        before_coast = coast.initialize_coastal_exchange(ctx)
        demand = np.zeros((7, 7))
        demand[3, 4] = .01
        exchange = coast.advance_coastal_exchange(before_coast, {"soil_exchange_m3_s": demand,
                              "tide_amplitude_m": .5, "tide_period_s": 3600.}, ctx, 900.)
        packet_water = exchange["fluxes"]["soil_water_m3"]
        packet_salt = exchange["fluxes"]["soil_salt_kg"]
        self.assertGreater(packet_water.sum(), 0.)
        initial_ground = soil.initialize_soil_chemistry(ctx, water_depth_m=.01)
        concentration = np.divide(packet_salt, packet_water, out=np.zeros((7, 7)), where=packet_water > 0.)
        chemistry = soil.advance_soil_chemistry(initial_ground, {"water_input_m3_s": packet_water / 900.,
            "inflow_salinity_kg_m3": concentration, "plant_uptake_demand_kg": .1}, ctx, 900.)
        final_water = exchange["state"]["water_m3"].sum() + chemistry["state"]["water_m3"].sum()
        expected_water = (before_coast["water_m3"].sum() + initial_ground["water_m3"].sum()
                          + exchange["ledger"]["signed_ocean_water_m3"])
        self.assertAlmostEqual(final_water, expected_water, delta=1.e-8)
        final_salt = (exchange["state"]["salt_kg"].sum() + chemistry["state"]["salt_dissolved_kg"].sum()
                      + chemistry["state"]["salt_solid_kg"].sum())
        expected_salt = before_coast["salt_kg"].sum() + exchange["ledger"]["signed_ocean_salt_kg"]
        self.assertAlmostEqual(final_salt, expected_salt, delta=1.e-7)
        plant = vegetation.advance_succession(vegetation.initialize_succession(ctx, biomass_carbon_kg_m2=4.), {
            "plant_nutrient_uptake_kg": chemistry["fluxes"]["plant_uptake_kg"],
            "plant_stress_factor": chemistry["fluxes"]["plant_stress_factor"]}, ctx, 86400.)
        animals = habitat.advance_habitat(habitat.initialize_habitat(ctx, population_individuals=.1), {
            "vegetation_cover_fraction": plant["fluxes"]["cover_fraction"],
            "disturbance_fraction": plant["state"]["disturbance_fraction"],
            "water_available_fraction": np.clip(chemistry["state"]["water_m3"] / 90., 0., 1.),
            "water_temperature_c": 15.}, ctx, 86400.)
        self.assertGreater(animals["ledger"]["gross_migration_individuals"], 0.)
        self.assertGreater(animals["state"]["occupancy_s"].sum(), 0.)
