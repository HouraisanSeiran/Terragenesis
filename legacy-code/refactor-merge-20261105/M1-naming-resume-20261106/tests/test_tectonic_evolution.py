"""Fixed-seed mechanism controls, independent of TD and default terrain paths."""

from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline import tectonic as core
from terrain_pipeline.tectonic import CrustState, TectonicConfig, evolve, initialize, surface_fields


def fixture(kind="continental", velocities=((2500., 0.), (-2500., 0.))):
    config = TectonicConfig(shape=(8, 16), cell_size_m=10000., plate_count=2, steps=1)
    coverage = np.zeros((2, 8, 16))
    coverage[0, :, :8] = 1
    coverage[1, :, 8:] = 1
    continental = coverage * 35000
    oceanic = np.zeros_like(coverage)
    if kind == "mixed":
        continental[0] = 0
        oceanic[0] = coverage[0] * 7000
    state = CrustState(coverage, continental, oceanic, np.array(((40000., 40000.), (120000., 40000.))),
                       np.array(velocities, dtype=float))
    return config, state


class TectonicEvolutionTests(unittest.TestCase):
    def assert_balanced(self, result):
        for budget in result.budgets:
            for material in ("continental", "oceanic"):
                scale = max(1., budget[f"initial_{material}_m3"], budget[f"final_{material}_m3"])
                self.assertLessEqual(abs(budget[f"{material}_balance_residual_m3"]), scale * 1e-12)
                self.assertLessEqual(abs(budget[f"advection_{material}_residual_m3"]), scale * 1e-12)

    def test_zero_motion_preserves_every_field(self):
        config, state = fixture(velocities=((0, 0), (0, 0)))
        result = evolve(replace(config, steps=4), state)
        np.testing.assert_array_equal(result.final.continental_m, state.continental_m)
        np.testing.assert_array_equal(result.final.plate_coverage, state.plate_coverage)
        np.testing.assert_array_equal(result.elevation_m, result.initial_elevation_m)
        self.assertTrue(all(b["rift_oceanic_added_m3"] == b["subducted_oceanic_m3"] == 0 for b in result.budgets))

    def test_common_integer_translation_moves_material_without_collision(self):
        config, state = fixture("mixed", velocities=((10000, 0), (10000, 0)))
        result = evolve(replace(config, steps=3), state)
        np.testing.assert_array_equal(result.final.continental_m, np.roll(state.continental_m, 3, axis=2))
        np.testing.assert_array_equal(result.final.oceanic_m, np.roll(state.oceanic_m, 3, axis=2))
        np.testing.assert_array_equal(result.elevation_m, np.roll(result.initial_elevation_m, 3, axis=1))
        self.assertTrue(all(b["sutured_continental_m3"] == b["subducted_oceanic_m3"] == b["rift_oceanic_added_m3"] == 0 for b in result.budgets))
        self.assert_balanced(result)

    def test_fractional_common_translation_only_diffuses(self):
        config, state = fixture("mixed", velocities=((2500, 1000), (2500, 1000)))
        result = evolve(replace(config, steps=5), state)
        self.assertTrue(all(b["sutured_continental_m3"] == b["subducted_oceanic_m3"] == b["rift_oceanic_added_m3"] == 0 for b in result.budgets))
        self.assertGreater(result.budgets[0]["advection_continental_l2_loss_m4"], 0)
        self.assertLessEqual(result.crust_thickness_m.max(), 35000)
        self.assert_balanced(result)

    def test_interior_crust_embryo_moves_without_any_plate_boundary(self):
        config = TectonicConfig(shape=(8, 16), plate_count=1, steps=2,
                                 origin_x_m=-80000, origin_z_m=-40000)
        coverage = np.ones((1, 8, 16))
        continental = np.zeros_like(coverage)
        continental[0, 2:5, 4:7] = 35000
        oceanic = np.where(continental > 0, 0., 7000.)
        state = CrustState(coverage, continental, oceanic,
                           np.array(((-40000., 0.),)), np.array(((10000., 0.),)))
        result = evolve(config, state)
        np.testing.assert_array_equal(result.final.continental_m, np.roll(continental, 2, axis=2))
        np.testing.assert_array_equal(result.final.oceanic_m, np.roll(oceanic, 2, axis=2))
        self.assertEqual(result.budgets[0]["convergent_faces"], 0)
        self.assertGreater(result.budgets[0]["advected_continental_m3"], 0)
        self.assert_balanced(result)

    def test_continental_convergence_thickens_and_sutures_at_contact(self):
        config, state = fixture()
        result = evolve(config, state)
        self.assertGreater(result.final.continental_m.sum(axis=0)[:, 7:9].max(), 35000)
        self.assertGreater(result.elevation_m[:, 7:9].max(), result.initial_elevation_m.max())
        self.assertGreater(result.budgets[0]["sutured_continental_m3"], 0)
        self.assertEqual(result.budgets[0]["subducted_oceanic_m3"], 0)
        self.assert_balanced(result)

    def test_ocean_continent_convergence_removes_ocean_at_contact(self):
        config, state = fixture("mixed")
        result = evolve(config, state)
        self.assertGreater(result.budgets[0]["subducted_oceanic_m3"], 0)
        self.assertLess(result.final.oceanic_m[:, :, 7:9].sum(), state.oceanic_m[:, :, 7:9].sum())
        self.assert_balanced(result)
        disabled = evolve(replace(config, subduction_fraction=0), state)
        self.assertEqual(disabled.budgets[0]["subducted_oceanic_m3"], 0)
        self.assert_balanced(disabled)

    def test_rifting_separates_continents_and_fills_gap_with_ocean(self):
        config, state = fixture(velocities=((-2500, 0), (2500, 0)))
        result = evolve(config, state)
        self.assertLess(result.final.continental_m.sum(axis=0)[:, 7:9].max(), 35000)
        self.assertGreater(result.final.oceanic_m[:, :, 7:9].sum(), 0)
        self.assertGreater(result.budgets[0]["rift_oceanic_added_m3"], 0)
        disabled = evolve(replace(config, rift_fraction=0), state)
        self.assertEqual(disabled.budgets[0]["rift_oceanic_added_m3"], 0)
        self.assert_balanced(result)

    def test_transform_only_slides_material(self):
        config, state = fixture("mixed", velocities=((0, 2500), (0, -2500)))
        result = evolve(config, state)
        self.assertGreater(result.budgets[0]["transform_faces"], 0)
        self.assertEqual(result.budgets[0]["convergent_faces"], 0)
        self.assertEqual(result.budgets[0]["subducted_oceanic_m3"], 0)
        self.assertEqual(result.budgets[0]["rift_oceanic_added_m3"], 0)
        self.assert_balanced(result)

    def test_aggregated_initialization_is_periodic_and_crust_is_independent(self):
        from terrain_pipeline.tectonic import geometry_metrics
        config = TectonicConfig(shape=(24, 32), plate_count=5, steps=3)
        state = initialize(config)
        metrics = geometry_metrics(state.plate_coverage.argmax(0), config.cell_size_m)
        self.assertEqual(metrics["periodic_components_per_plate"], [1] * config.plate_count)
        self.assertGreaterEqual(min(metrics["plate_area_cells"]), config.min_plate_cells)
        self.assertGreater(state.formation["microcell_count"], config.plate_count * 8)
        self.assertGreater(sum(state.formation["continuous_concave_vertices_per_plate"]), 0)
        # Mixed plates demonstrate that coastlines do not follow polygons;
        # entirely oceanic plates are allowed, as are entirely continental ones.
        mixed = (state.continental_m.sum(axis=(1, 2)) > 0) & (state.oceanic_m.sum(axis=(1, 2)) > 0)
        self.assertTrue(mixed.any())
        self.assertGreater(np.count_nonzero(state.continental_m.sum(axis=(1, 2))), 1)
        first, second = evolve(config), evolve(config)
        np.testing.assert_array_equal(first.final.continental_m, second.final.continental_m)
        np.testing.assert_array_equal(first.elevation_m, second.elevation_m)
        self.assertEqual(first.budgets, second.budgets)
        self.assertEqual(first.metadata, second.metadata)
        self.assertEqual(len(set(first.metadata["purpose_seeds"].values())), 3)
        self.assert_balanced(first)

    def test_input_is_unchanged_and_snapshots_are_independent(self):
        config, state = fixture()
        before = state.continental_m.copy()
        result = evolve(config, state)
        np.testing.assert_array_equal(state.continental_m, before)
        result.final.continental_m[:] = 0
        np.testing.assert_array_equal(result.initial.continental_m, before)
        np.testing.assert_array_equal(state.continental_m, before)

    def test_surface_is_buoyancy_from_material_not_plate_identity(self):
        _, state = fixture("mixed")
        fields = surface_fields(state)
        self.assertAlmostEqual(fields["elevation_m"][0, 0], 7000 * (1 - 3000/3300) - 4500)
        self.assertAlmostEqual(fields["elevation_m"][0, 10], 35000 * (1 - 2800/3300) - 4500)
        state.plate_coverage = state.plate_coverage[::-1]
        np.testing.assert_array_equal(surface_fields(state)["elevation_m"], fields["elevation_m"])

    def test_default_initial_and_final_surfaces_have_land_and_ocean(self):
        # Fixed, uncalibrated -4500 m datum; sea level is always zero metres.
        for config in (TectonicConfig(), TectonicConfig(shape=(64, 64), steps=20)):
            with self.subTest(shape=config.shape):
                result = evolve(config)
                self.assertEqual(result.metadata["elevation_offset_m"], -4500)
                for elevation in (result.initial_elevation_m, result.elevation_m):
                    land = np.mean(elevation > 0)
                    ocean = np.mean(elevation < 0)
                    self.assertGreater(land, 0.05)
                    self.assertGreater(ocean, 0.20)
                    self.assertTrue(np.isfinite(elevation).all())
                self.assert_balanced(result)

    def test_cfl_boundary_uses_nonnegative_transport_weights(self):
        # 1 - .9 - .1 is negative in float64, although .9 + .1 == 1.
        config, state = fixture("mixed", velocities=((9000, 1000), (9000, 1000)))
        result = evolve(replace(config, steps=3), state)
        self.assertTrue((result.final.plate_coverage >= 0).all())
        self.assertTrue((result.final.continental_m >= 0).all())
        self.assertTrue((result.final.oceanic_m >= 0).all())
        self.assert_balanced(result)

    def test_cfl_above_one_is_rejected_at_input_without_mutation(self):
        for excess in (np.spacing(1.), 5e-15, 1e-14):
            config, state = fixture("mixed", velocities=((1 + excess, 0), (0, 0)))
            config = replace(config, cell_size_m=1)
            state.plate_seeds_m /= 10000
            before = state.continental_m.copy()
            with self.subTest(excess=excess), self.assertRaisesRegex(ValueError, "CFL"):
                evolve(config, state)
            np.testing.assert_array_equal(state.continental_m, before)

    def test_runtime_rejects_injected_transport_material_creation(self):
        original_advect = core._advect
        for material, call_index in (("continental", 5), ("oceanic", 6)):
            config, state = fixture("mixed", velocities=((0, 0), (0, 0)))
            before = getattr(state, f"{material}_m").copy()
            calls = 0

            def corrupt_transport(field, displacement):
                nonlocal calls
                calls += 1
                transported = original_advect(field, displacement)
                if calls == call_index:
                    # Inject only on step two, on an already present plate.
                    transported[0, 0, 0] += 1
                return transported

            with self.subTest(material=material), patch.object(core, "_advect", side_effect=corrupt_transport):
                with self.assertRaisesRegex(ValueError, f"step 2: {material} .*budget exceeded"):
                    evolve(replace(config, steps=3), state)
            self.assertEqual(calls, 6)
            np.testing.assert_array_equal(getattr(state, f"{material}_m"), before)

    def test_runtime_checks_actual_state_even_if_reported_budget_is_balanced(self):
        original_step = core._step
        for material in ("continental", "oceanic"):
            config, state = fixture("mixed", velocities=((0, 0), (0, 0)))

            def corrupt_state(config, current):
                after, budget = original_step(config, current)
                getattr(after, f"{material}_m")[0, 0, 0] += 1
                return after, budget

            with self.subTest(material=material), patch.object(core, "_step", side_effect=corrupt_state):
                with self.assertRaisesRegex(ValueError, f"{material} material budget exceeded"):
                    evolve(config, state)

    def test_tiny_inventory_absolute_tolerance_is_separate_for_each_material(self):
        original_advect = core._advect
        for material, call_index in (("continental", 2), ("oceanic", 3)):
            for injected_m3, rejected in ((1e-13, False), (1e-11, True)):
                config, state = fixture("mixed", velocities=((0, 0), (0, 0)))
                config = replace(config, cell_size_m=1)
                state.plate_seeds_m /= 10000
                getattr(state, f"{material}_m")[:] *= 1e-20
                calls = 0

                def corrupt_transport(field, displacement):
                    nonlocal calls
                    calls += 1
                    transported = original_advect(field, displacement)
                    if calls == call_index:
                        transported[0, 0, 0] += injected_m3
                    return transported

                with self.subTest(material=material, injected_m3=injected_m3):
                    with patch.object(core, "_advect", side_effect=corrupt_transport):
                        if rejected:
                            with self.assertRaisesRegex(ValueError, f"{material} .*budget exceeded"):
                                evolve(config, state)
                        else:
                            evolve(config, state)

    def test_runtime_rejects_nonfinite_budget(self):
        config, state = fixture()
        original_step = core._step
        for invalid in (float("nan"), float("inf")):
            def corrupt_budget(config, current):
                after, budget = original_step(config, current)
                budget["continental_balance_residual_m3"] = invalid
                return after, budget

            with self.subTest(invalid=invalid), patch.object(core, "_step", side_effect=corrupt_budget):
                with self.assertRaisesRegex(ValueError, "nonfinite evolution budget"):
                    evolve(config, state)

    def test_invalid_input_fails_without_mutation(self):
        config, state = fixture()
        for change in ({"time_step": float("nan")}, {"cell_size_m": 0}, {"steps": -1},
                       {"plate_count": 0}, {"rift_fraction": 2}, {"shape": (8.5, 16)},
                       {"max_speed_m_per_step": -1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                evolve(replace(config, **change), state)
        for field, index, value in (("continental_m", (0, 0, 0), -1),
                                    ("oceanic_m", (0, 0, 0), np.nan),
                                    ("plate_coverage", (0, 0, 0), 0.5),
                                    ("plate_seeds_m", (0, 0), -1),
                                    ("velocities_m_per_step", (0, 0), np.inf),
                                    ("velocities_m_per_step", (0, 0), 20000)):
            config, state = fixture()
            getattr(state, field)[index] = value
            before = state.continental_m.copy()
            with self.subTest(field=field), self.assertRaises(ValueError):
                evolve(config, state)
            np.testing.assert_array_equal(state.continental_m, before)


if __name__ == "__main__":
    unittest.main()
