from dataclasses import replace
import unittest

import numpy as np

from terrain_pipeline.hybrid_river_hydraulics import Experiment, compare_refinement
from terrain_pipeline.hybrid_river_hydraulics_v3 import LOG_VOLUME_DIFFERENCE_STEP, build_system, run_experiment
from terrain_pipeline.hybrid_river_sections_v2 import accelerate_model
from tests.test_hybrid_river_hydraulics import tiny_model


class ExplicitJacobianTests(unittest.TestCase):
    def test_zero_ledger_feedback_repeatable_finite_directional_jacobian(self):
        model = accelerate_model(tiny_model())
        for heads, tailwater in (((0.3, 0.23, 0.18), 0.15), ((0.15, 0.2, 0.26), 0.35)):
            experiment = Experiment("pulse", 2, 0.5, 0.05, tailwater, heads, (0, 1, 2), max_step_s=0.2)
            system = build_system(model, experiment)
            count = system.count
            state = system.initial_state.copy()
            state[count:2 * count] = 0.2 * system.initial_volumes
            state[2 * count:3 * count] = 0.3 * system.initial_volumes
            rhs, jacobian = system.rhs_for(0.05), system.jacobian_for(0.05)
            derivative = rhs(0, state)
            ledger_changed = state.copy()
            ledger_changed[3 * count:] = np.arange(len(state) - 3 * count) * 1e9
            np.testing.assert_array_equal(derivative, rhs(0, ledger_changed))
            matrix = jacobian(0, state)
            np.testing.assert_array_equal(matrix, jacobian(0, state))
            self.assertEqual(matrix.shape, (len(state), len(state)))
            self.assertTrue(np.isfinite(matrix).all())
            np.testing.assert_array_equal(matrix[:, 3 * count:], 0)
            self.assertGreater(np.max(abs(matrix[3 * count:, :3 * count])), 0)
            direction = np.zeros(len(state))
            direction[:3 * count] = [0.11, -0.17, 0.13, 0.019, -0.027, 0.031, -0.016, 0.023, -0.014]
            for difference_step in (2e-5, 3e-7):
                independent = (rhs(0, state + difference_step * direction) - rhs(0, state - difference_step * direction)) / (2 * difference_step)
                np.testing.assert_allclose(matrix @ direction, independent, rtol=2e-4, atol=2e-7)
            outlet_mass_rows = [3 * count + 3, 3 * count + 5]
            if heads[-1] < tailwater:
                np.testing.assert_array_equal(matrix[outlet_mass_rows, count:3 * count], 0)
            self.assertEqual(system.work["jacobian_rhs_evaluations"], 2 * (count + 1))
            self.assertGreater(system.work["link_evaluations"], system.work["rhs_evaluations"] * (len(model.links) + 1))
        thin = Experiment("reverse_tailwater", 2, 0, 0, 1.2, (0.0001, 1.000001, 0.0001), (0, 1, 2), max_step_s=0.2)
        system = build_system(model, thin)
        self.assertTrue(np.isfinite(system.jacobian_for(0)(0, system.initial_state)).all())
        invalid = system.initial_state.copy()
        invalid[0] = 601
        with self.assertRaises(ValueError):
            system.jacobian_for(0)(0, invalid)
        bounded = build_system(model, replace(thin, max_rhs_evaluations=1))
        with self.assertRaises(ValueError):
            bounded.jacobian_for(0)(0, bounded.initial_state)
        self.assertEqual(LOG_VOLUME_DIFFERENCE_STEP, 1e-6)

    def test_short_pulse_and_reverse_with_saved_refinement_and_conservation(self):
        model = accelerate_model(tiny_model())
        for scenario, tailwater in (("pulse", 0.1), ("reverse_tailwater", 0.4)):
            experiment = Experiment(scenario, 2, 0.5 if scenario == "pulse" else 0, 0.05 if scenario == "pulse" else 0,
                                    tailwater, (0.2, 0.2, 0.2), (0, 0.5, 1, 2), max_step_s=0.2, source_arrival_threshold_m3=1e-8)
            base = run_experiment(model, experiment)
            fine = run_experiment(model, replace(experiment, max_step_s=0.1, relative_tolerance=2.5e-8, absolute_tolerance=2.5e-10))
            self.assertEqual(compare_refinement(base, fine)["status"], "passed")
            self.assertLess(fine["max_water_residual_m3"], 1e-6)
            self.assertLess(fine["max_source_residual_m3"], 1e-8)
            self.assertLess(fine["max_tailwater_residual_m3"], 1e-8)
            self.assertGreater(fine["work"]["jacobian_evaluations"], 0)
            self.assertEqual(fine["work"]["old_hll_face_work"], 0)
            self.assertFalse(fine["jacobian_policy"]["scipy_adaptive_difference_factor_used"])
            self.assertEqual(fine["model_parameters"], {"head_regularization_m": 1e-4, "donor_regularization_m3": 1e-6})
            self.assertTrue(np.all(np.asarray(fine["source_tracer_mass_m3"]) >= 0))
            if scenario == "pulse":
                self.assertTrue(fine["source_reached_engineered_outlet"])
                self.assertAlmostEqual(fine["boundary_ledger_m3"][-1][0], 0.025)
            else:
                self.assertTrue(fine["reverse_reached_sink"])
                self.assertEqual(fine["boundary_ledger_m3"][-1][0], 0)


if __name__ == "__main__":
    unittest.main()
