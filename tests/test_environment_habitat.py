import unittest

import numpy as np

from terrain_pipeline.environment_processes import initialize_habitat as initialize, advance_habitat as step
from terrain_pipeline.environment_processes import initialize_succession, advance_succession
from terrain_pipeline.drainage import build_mesh as build_mesh
from tests.environment_ecology_fixtures import assert_same, cold, context, immutable_call


class HabitatTests(unittest.TestCase):
    def test_empty_population_cannot_spontaneously_colonize(self):
        ctx = context()
        forcing = {"vegetation_cover_fraction": 1., "water_available_fraction": 1.}
        state = initialize(ctx)
        result = immutable_call(self, step, state, forcing, ctx, 86400.)
        assert_same(self, state, result["state"])
        self.assertFalse(result["fluxes"]["reachable_mask"].any())
        self.assertEqual(result["ledger"]["births_individuals"], 0.)

    def test_connected_cost_corridor_moves_population_and_closes_ledger(self):
        ctx = context()
        population = np.zeros((7, 7))
        population[3, 1] = .1
        state = initialize(ctx, population_individuals=population)
        forcing = {"vegetation_cover_fraction": 1., "water_available_fraction": 1.}
        result = step(state, forcing, ctx, 86400.)
        self.assertGreater(result["ledger"]["gross_migration_individuals"], 0.)
        self.assertGreater(result["state"]["population_individuals"][3, 2], 0.)
        self.assertGreater(result["fluxes"]["corridor_cost_m"][3, 2], 0.)
        self.assertGreater(result["state"]["occupancy_s"][3, 2], 0.)
        self.assertAlmostEqual(result["ledger"]["population_residual"], 0., delta=1.e-12)
        assert_same(self, step(result["state"], forcing, ctx, 86400.)["state"],
                    step(cold(result["state"]), forcing, ctx, 86400.)["state"])
        assert_same(self, state, step(state, forcing, ctx, 0.)["state"])

    def test_barrier_blocks_reachability_and_migration(self):
        ctx = context()
        ctx["valid_mask"][:, 2] = False
        population = np.zeros((7, 7))
        population[3, 1] = .1
        result = step(initialize(ctx, population_individuals=population),
                      {"vegetation_cover_fraction": 1., "water_available_fraction": 1.}, ctx, 86400.)
        self.assertFalse(result["fluxes"]["reachable_mask"][:, 3:].any())
        self.assertEqual(result["state"]["population_individuals"][:, 3:].sum(), 0.)

    def test_multiple_occupied_seeds_cannot_bypass_actual_edge_cost(self):
        ctx = context()
        ctx["spacing_m"] = 10000.
        population = np.zeros((7, 7))
        population[3, 1] = population[3, 2] = .1
        result = step(initialize(ctx, population_individuals=population),
                      {"vegetation_cover_fraction": 1., "water_available_fraction": 1.}, ctx, 86400.)
        self.assertEqual(result["ledger"]["gross_migration_individuals"], 0.)
        np.testing.assert_array_equal(result["fluxes"]["migration_net_individuals"], 0.)

    def test_saved_adjacency_is_not_reconnected_by_window_triangulation(self):
        ctx = context()
        mesh = build_mesh((7, 7), origin_native_xz=ctx["origin_native_xz"],
                          spacing_m=30., world_seed=ctx["world_seed"])
        ctx.update(node_x_m=mesh.node_x_m.reshape(7, 7), node_z_m=mesh.node_z_m.reshape(7, 7),
                   graph_edge_source=np.empty(0, np.int64), graph_edge_target=np.empty(0, np.int64))
        population = np.zeros((7, 7))
        population[3, 1] = .1
        result = step(initialize(ctx, population_individuals=population),
                      {"vegetation_cover_fraction": 1., "water_available_fraction": 1.}, ctx, 86400.)
        self.assertEqual(result["ledger"]["gross_migration_individuals"], 0.)
        self.assertEqual(np.count_nonzero(result["fluxes"]["reachable_mask"]), 1)

    def test_fire_cover_and_water_temperature_change_actual_capacity_and_survival(self):
        ctx = context()
        vegetation = initialize_succession(ctx, biomass_carbon_kg_m2=4.)
        healthy = advance_succession(vegetation, {}, ctx, 86400.)
        burned = advance_succession(vegetation, {"fire_hazard_s": .001}, ctx, 86400.)
        state = initialize(ctx, population_individuals=.3)
        results = []
        for ecology in (healthy, burned):
            result = step(state, {"vegetation_cover_fraction": ecology["fluxes"]["cover_fraction"],
                "disturbance_fraction": ecology["state"]["disturbance_fraction"],
                "water_available_fraction": 1., "water_temperature_c": 15.}, ctx, 30. * 86400.)
            results.append(result)
        self.assertGreater(results[0]["state"]["population_individuals"].sum(), results[1]["state"]["population_individuals"].sum())
        hot = step(state, {"vegetation_cover_fraction": 1., "water_available_fraction": 1.,
                          "water_temperature_c": 80.}, ctx, 86400.)
        self.assertEqual(hot["fluxes"]["carrying_capacity_individuals"].sum(), 0.)
        self.assertGreater(hot["ledger"]["deaths_individuals"], 0.)
