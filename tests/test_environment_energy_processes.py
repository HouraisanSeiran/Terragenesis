from copy import deepcopy
import unittest

import numpy as np

from terrain_pipeline import environment_processes as radiation
from terrain_pipeline import environment_processes as frozen
from terrain_pipeline import environment_processes as aeolian
from terrain_pipeline import environment_processes as volcanism


def context(shape=(5, 5)):
    height = np.broadcast_to(np.arange(shape[1], 0, -1, dtype=float), shape).copy()
    receiver = np.arange(height.size, dtype=np.int64).reshape(shape) + 1
    receiver[:, -1] = -1
    return {"height_m": height, "spacing_m": 30., "origin_native_xz": (-30, 70),
        "world_seed": 20261020, "receiver": receiver.ravel(), "river_mask": np.zeros(shape, bool),
        "ocean_mask": np.zeros(shape, bool), "valid_mask": np.ones(shape, bool),
        "protected_mask": np.zeros(shape, bool)}


class EnergyProcessesTests(unittest.TestCase):
    def test_radiation_night_day_slope_shadow_and_budget(self):
        ctx = context()
        state = radiation.radiation_initialize(ctx)
        night = radiation.radiation_step(state, {"time_s": 0.}, ctx, 60.)
        self.assertEqual(night["ledger"]["absorbed_j"], 0.)
        noon = radiation.radiation_step(state, {"time_s": 43170.}, ctx, 60.)
        self.assertGreater(noon["ledger"]["absorbed_j"], 0.)
        np.testing.assert_allclose(noon["ledger"]["incident_j"],
            noon["ledger"]["absorbed_j"] + noon["ledger"]["reflected_j"], rtol=1e-14)
        ridge = context((5, 9))
        ridge["height_m"][:] = 0.
        ridge["height_m"][:, 5] = 300.
        morning = radiation.radiation_step(radiation.radiation_initialize(ridge), {"time_s": 25000.}, ridge, 60.)
        self.assertTrue(morning["fluxes"]["terrain_shadow_mask"][:, :4].any())
        self.assertGreater(np.ptp(morning["fluxes"]["absorbed_shortwave_w_m2"]), 0.)
        reflected = radiation.radiation_step(state, {"time_s": 43170., "albedo": 1.}, ctx, 60.)
        self.assertEqual(reflected["ledger"]["absorbed_j"], 0.)

    def test_freeze_thaw_latent_water_and_snow_insulation(self):
        ctx = context()
        state = frozen.frozen_ground_initialize(ctx)
        zero = frozen.frozen_ground_step(state, {}, ctx, 600.)
        for key in state:
            if key not in ("thaw_time_s", "frozen_time_s"):
                np.testing.assert_array_equal(zero["state"][key], state[key])
        cold = frozen.frozen_ground_step(state, {"ground_heat_w_m2": -100.}, ctx, 86400.)
        self.assertTrue((cold["state"]["ground_ice_m"] > 0).all())
        np.testing.assert_allclose(cold["state"]["ground_ice_m"], 100. * 86400. / frozen.LATENT_J_M3)
        self.assertTrue((cold["fluxes"]["infiltration_factor"] < 1).all())
        self.assertTrue((cold["fluxes"]["height_change_m"] > 0).all())
        warm = frozen.frozen_ground_step(cold["state"], {"ground_heat_w_m2": 100.}, ctx, 86400.)
        np.testing.assert_allclose(warm["state"]["liquid_water_m"], state["liquid_water_m"])
        self.assertTrue((warm["fluxes"]["height_change_m"] < 0).all())
        self.assertAlmostEqual(cold["ledger"]["water_residual_m3"], 0.)
        self.assertLess(abs(cold["ledger"]["energy_residual_j"]),
                        abs(cold["ledger"]["heat_input_j"]) * 1e-12)
        bare = frozen.frozen_ground_step(state, {"air_temperature_c": -10.}, ctx, 3600.)
        snowstate = frozen.frozen_ground_initialize(ctx, snow_swe_m=.2)
        insulated = frozen.frozen_ground_step(snowstate, {"air_temperature_c": -10.}, ctx, 3600.)
        self.assertTrue((insulated["state"]["ground_ice_m"] < bare["state"]["ground_ice_m"]).all())
        melted = frozen.frozen_ground_step(snowstate, {"ground_heat_w_m2": 1000.}, ctx, 86400.)
        self.assertTrue((melted["fluxes"]["snow_meltwater_m"] > 0).all())
        self.assertAlmostEqual(melted["ledger"]["water_residual_m3"], 0., delta=1e-9)

    def test_wind_actual_displacement_protection_export_and_limits(self):
        ctx = context()
        inventory = np.zeros((5, 5))
        inventory[2, 1] = 1.
        state = aeolian.aeolian_initialize(ctx, loose_solid_m3=inventory)
        calm = aeolian.aeolian_step(state, {}, ctx, 60.)
        np.testing.assert_array_equal(calm["state"]["loose_solid_m3"], inventory)
        forcing = {"wind_x_m_s": 10.}
        blown = aeolian.aeolian_step(state, forcing, ctx, 60.)
        self.assertGreater(blown["state"]["airborne_solid_m3"][2, 2], 0.)
        self.assertGreater(blown["fluxes"]["deposited_solid_m3"][2, 2], 0.)
        self.assertLess(blown["state"]["loose_solid_m3"][2, 1], 1.)
        self.assertAlmostEqual(blown["ledger"]["solid_residual_m3"], 0.)
        for factor in ("water_saturation", "vegetation_cover"):
            stopped = aeolian.aeolian_step(state, {**forcing, factor: 1.}, ctx, 60.)
            np.testing.assert_array_equal(stopped["state"]["loose_solid_m3"], inventory)
        ctx["protected_mask"][2, 2] = True
        blocked = aeolian.aeolian_step(state, forcing, ctx, 60.)
        self.assertEqual(blocked["state"]["airborne_solid_m3"][2, 2], 0.)
        inventory[:] = 0.
        inventory[2, -1] = 1.
        edge = aeolian.aeolian_step(aeolian.aeolian_initialize(ctx, loose_solid_m3=inventory), forcing, ctx, 60.)
        self.assertGreater(edge["ledger"]["boundary_export_solid_m3"], 0.)
        self.assertAlmostEqual(edge["ledger"]["solid_residual_m3"], 0.)

    def test_lava_event_graph_transport_mass_heat_and_consumed_geothermal(self):
        ctx = context()
        state = volcanism.volcanism_initialize(ctx)
        zero = volcanism.volcanism_step(state, {}, ctx, 600.)
        self.assertEqual(zero["ledger"]["final_solid_m3"], 0.)
        event = np.zeros((5, 5))
        event[2, 1] = 1.
        erupted = volcanism.volcanism_step(state, {"lava_input_m3": event, "ash_input_m3": event * .2}, ctx, 600.)
        self.assertGreater(erupted["state"]["mobile_lava_m3"][2, 2], 0.)
        self.assertAlmostEqual(erupted["state"]["mobile_lava_m3"][2, 2], np.exp(-600. / 3600.))
        self.assertGreater(erupted["fluxes"]["height_change_m"][2, 2], 0.)
        self.assertAlmostEqual(erupted["ledger"]["solid_residual_m3"], 0.)
        self.assertAlmostEqual(erupted["ledger"]["heat_residual_j"], 0., delta=1e-5)
        ice = frozen.frozen_ground_initialize(ctx, liquid_water_m=0., ground_ice_m=.1)
        heated = frozen.frozen_ground_step(ice, {"geothermal_heat_w_m2": erupted["fluxes"]["geothermal_heat_w_m2"]}, ctx, 600.)
        self.assertGreater(heated["fluxes"]["thawed_water_m"][2, 2], 0.)
        sunny = radiation.radiation_step(radiation.radiation_initialize(ctx), {"time_s": 43170.}, ctx, 60.)
        solar_thaw = frozen.frozen_ground_step(ice, {"ground_heat_w_m2": sunny["fluxes"]["net_ground_heat_w_m2"]}, ctx, 60.)
        self.assertTrue((solar_thaw["fluxes"]["thawed_water_m"] > 0).all())
        self.assertTrue((sunny["fluxes"]["potential_evaporation_m"] > 0).all())
        windy = volcanism.volcanism_step(state, {"ash_input_m3": event, "wind_x_m_s": 10.}, ctx, 60.)
        self.assertGreater(windy["state"]["airborne_ash_m3"][2, 2], 0.)
        self.assertGreater(windy["fluxes"]["deposited_ash_solid_m3"][2, 2], 0.)
        self.assertAlmostEqual(windy["ledger"]["solid_residual_m3"], 0.)

    def test_protected_and_unknown_state_unchanged_and_invalid_forcing(self):
        ctx = context()
        ctx["protected_mask"][1, 1] = True
        ctx["valid_mask"][2, 2] = False
        ctx["ocean_mask"][3, 3] = True
        modules = [(radiation, radiation.radiation_initialize(ctx), {"time_s": 43170.}),
            (frozen, frozen.frozen_ground_initialize(ctx), {"ground_heat_w_m2": -100.}),
            (aeolian, aeolian.aeolian_initialize(ctx, loose_solid_m3=1.), {"wind_x_m_s": 10.}),
            (volcanism, volcanism.volcanism_initialize(ctx), {"geothermal_w_m2": 100.})]
        for module, state, forcing in modules:
            result = module.step(state, forcing, ctx, 60.)
            for key in state:
                for cell in ((1, 1), (2, 2)):
                    self.assertEqual(result["state"][key][cell], state[key][cell])
            if module is frozen:
                for key in state:
                    self.assertEqual(result["state"][key][3, 3], state[key][3, 3])
        with self.assertRaises(ValueError):
            aeolian.aeolian_step(modules[2][1], {"water_saturation": 2.}, ctx, 60.)
        with self.assertRaises(ValueError):
            volcanism.volcanism_step(modules[3][1], {"lava_input_m3": 1.}, ctx, 60.)

    def test_nonlocal_lava_graph_edge_uses_metric_distance_and_retains_terminal(self):
        from terrain_pipeline.drainage import grid_mesh as grid_mesh
        ctx = context((7, 7))
        mesh = grid_mesh((7, 7), x0_m=-900., z0_m=2100.)
        pairs = [(node, int(target)) for node in range(49)
                 for target in mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]
                 if max(abs(node // 7 - target // 7), abs(node % 7 - target % 7)) > 1]
        self.assertTrue(pairs)
        donor, target = pairs[0]
        ctx["height_m"][:] = 0.
        ctx["height_m"].flat[donor] = 10.
        ctx["receiver"][:] = -1
        ctx["receiver"][donor] = target
        ctx["node_x_m"], ctx["node_z_m"] = mesh.node_x_m, mesh.node_z_m
        source = np.zeros((7, 7))
        source.flat[donor] = 2.
        length = np.hypot(mesh.node_x_m[donor] - mesh.node_x_m[target],
                          mesh.node_z_m[donor] - mesh.node_z_m[target])
        result = volcanism.volcanism_step(volcanism.volcanism_initialize(ctx), {"lava_input_m3": source}, ctx, 60.)
        expected = 2. * min(1., .05 * 60. / length)
        self.assertAlmostEqual(result["fluxes"]["lava_transport_solid_m3"].flat[donor], expected)
        self.assertGreater(result["state"]["mobile_lava_m3"].flat[target], 0.)
        continued = volcanism.volcanism_step(result["state"], {}, ctx, 600.)
        self.assertEqual(continued["ledger"]["boundary_export_solid_m3"], 0.)
        self.assertAlmostEqual(continued["ledger"]["final_solid_m3"], 2.)

    def test_ash_downwind_boundary_export_closes_separate_from_lava_heat(self):
        ctx = context()
        event = np.zeros((5, 5))
        event[2, -1] = 3.
        result = volcanism.volcanism_step(volcanism.volcanism_initialize(ctx),
            {"ash_input_m3": event, "wind_x_m_s": 10.}, ctx, 60.)
        self.assertAlmostEqual(result["ledger"]["boundary_export_solid_m3"], 3.)
        self.assertAlmostEqual(result["ledger"]["final_solid_m3"], 0.)
        self.assertAlmostEqual(result["ledger"]["solid_residual_m3"], 0.)
        self.assertEqual(result["ledger"]["cooling_heat_j"], 0.)

    def test_multiple_freeze_steps_close_independent_latent_and_sensible_energy(self):
        ctx = context()
        current = frozen.frozen_ground_initialize(ctx, liquid_water_m=.001)
        initial = deepcopy(current)
        heat_j = 0.
        for _ in range(3):
            result = frozen.frozen_ground_step(current, {"ground_heat_w_m2": -100.}, ctx, 3600.)
            heat_j += result["ledger"]["heat_input_j"]
            current = result["state"]
        self.assertTrue((current["soil_temperature_c"] < 0).all())
        area = 900.
        final_energy = (current["soil_temperature_c"] * 2.e6 + current["liquid_water_m"] * 3.34e8).sum() * area
        initial_energy = (initial["soil_temperature_c"] * 2.e6 + initial["liquid_water_m"] * 3.34e8).sum() * area
        np.testing.assert_allclose(final_energy - initial_energy, heat_j, rtol=1e-13)
        self.assertTrue((current["frozen_time_s"] == 10800.).all())

    def test_shadow_is_cast_behind_ridge_not_just_slope_albedo(self):
        ctx = context((3, 9))
        ctx["height_m"][:] = 0.
        ctx["height_m"][:, 5] = 300.
        result = radiation.radiation_step(radiation.radiation_initialize(ctx), {"time_s": 25000., "latitude_deg": 0.}, ctx, 60.)
        self.assertGreater(result["fluxes"]["sun_direction_xyz"][0], 0.)
        self.assertTrue(result["fluxes"]["terrain_shadow_mask"][1, 2])
        self.assertFalse(result["fluxes"]["terrain_shadow_mask"][1, 7])
        self.assertEqual(result["fluxes"]["absorbed_shortwave_w_m2"][1, 2], 0.)
        self.assertGreater(result["fluxes"]["absorbed_shortwave_w_m2"][1, 7], 0.)

    def test_inputs_immutable_and_checkpoint_continuation(self):
        ctx = context()
        cases = [(radiation, radiation.radiation_initialize(ctx), {"time_s": 43170.}),
                 (frozen, frozen.frozen_ground_initialize(ctx), {"ground_heat_w_m2": -10.}),
                 (aeolian, aeolian.aeolian_initialize(ctx, loose_solid_m3=1.), {"wind_x_m_s": 10.}),
                 (volcanism, volcanism.volcanism_initialize(ctx), {"lava_input_m3": .01})]
        for module, state, forcing in cases:
            with self.subTest(module=module.__name__):
                original = deepcopy((ctx, state, forcing))
                one = module.step(state, forcing, ctx, 60.)
                saved = {key: value.copy() for key, value in one["state"].items()}
                two = module.step(one["state"], forcing, ctx, 60.)
                resumed = module.step(saved, forcing, ctx, 60.)
                for key in two["state"]:
                    np.testing.assert_array_equal(two["state"][key], resumed["state"][key])
                for actual, expected in zip((ctx, state, forcing), original):
                    for key in actual:
                        np.testing.assert_array_equal(actual[key], expected[key])
                with self.assertRaises(ValueError):
                    module.step(state, forcing, ctx, 0.)


if __name__ == "__main__":
    unittest.main()
