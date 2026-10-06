from dataclasses import asdict
import unittest

import numpy as np

from terrain_pipeline.hybrid_river_hydraulics import Experiment, compare_refinement
from terrain_pipeline.hybrid_river_hydraulics_v6 import build_system as build_system_v6
from terrain_pipeline.hybrid_river_hydraulics_v7 import (
    INTEGRATION, MODEL_VERSION, build_system, run_experiment)
from terrain_pipeline.hybrid_river_sections_v2 import accelerate_model
from tests.test_hybrid_river_hydraulics import tiny_model
from tools.prepare_hybrid_river_hydraulics_v7 import accuracy_policy, paired_refinement, precision_experiments


class BDFPrecisionTests(unittest.TestCase):
    def test_same_physics_directional_jacobian_and_explicit_precision_transform(self):
        model = accelerate_model(tiny_model())
        for heads, tailwater in (((0.3, 0.23, 0.18), 0.15), ((0.15, 0.2, 0.26), 0.35)):
            original = Experiment("pulse", 2, 0.5, 0.05, tailwater, heads, (0, 1, 2), max_step_s=0.2)
            base, fine = precision_experiments(original)
            for parameters, tolerance_divisor, step_divisor in ((base, 64, 4), (fine, 256, 8)):
                parameters.validate(model)
                self.assertEqual(parameters.relative_tolerance, original.relative_tolerance / tolerance_divisor)
                self.assertEqual(parameters.absolute_tolerance, original.absolute_tolerance / tolerance_divisor)
                self.assertEqual(parameters.max_step_s, original.max_step_s / step_divisor)
                for key, value in asdict(original).items():
                    if key not in ("relative_tolerance", "absolute_tolerance", "max_step_s"):
                        self.assertEqual(asdict(parameters)[key], value)
            system = build_system(model, base, 0.02)
            previous = build_system_v6(model, base, 0.02)
            state = system.initial_state.copy()
            state[:9] = (np.array([0.3, 0.4, 0.3])[:, None] * system.initial_volumes).ravel()
            rhs = system.rhs_for(0.05)
            np.testing.assert_array_equal(rhs(0, state), previous.rhs_for(0.05)(0, state))
            matrix = system.jacobian_for(0.05)(0, state)
            np.testing.assert_array_equal(matrix, previous.jacobian_for(0.05)(0, state))
            np.testing.assert_array_equal(matrix[:, 9:], 0)
            direction = np.zeros(len(state))
            direction[:9] = [0.11, -0.17, 0.13, 0.019, -0.027, 0.031, -0.016, 0.023, -0.014]
            step = 1e-6
            independent = (rhs(0, state + step * direction) - rhs(0, state - step * direction)) / (2 * step)
            np.testing.assert_allclose(matrix @ direction, independent, rtol=2e-6, atol=1e-8)
        self.assertEqual(INTEGRATION, "BDF")
        self.assertEqual(MODEL_VERSION, "explicit_roof_friction_contact_transition-v5")
        self.assertFalse(accuracy_policy()["reused_cases_allowed"])

    def test_two_second_BDF_pulse_reverse_strict_origins_and_refinement(self):
        model = accelerate_model(tiny_model())
        for scenario, tailwater in (("pulse", 0.1), ("reverse_tailwater", 0.4)):
            original = Experiment(scenario, 2, 0.5 if scenario == "pulse" else 0,
                                  0.05 if scenario == "pulse" else 0, tailwater, (0.2, 0.2, 0.2),
                                  (0, 0.5, 1, 2), max_step_s=0.2, source_arrival_threshold_m3=1e-8)
            base_parameters, fine_parameters = precision_experiments(original)
            base = run_experiment(model, base_parameters, 0.02)
            fine = run_experiment(model, fine_parameters, 0.02)
            self.assertEqual(compare_refinement(base, fine)["status"], "passed")
            self.assertEqual(paired_refinement(base, fine)["status"], "passed")
            origins = np.array([fine["untraced_water_volume_m3"], fine["source_tracer_mass_m3"],
                                fine["tailwater_tracer_mass_m3"]])
            self.assertTrue(np.all(origins >= 0))
            np.testing.assert_array_equal(origins.sum(axis=0), fine["water_volume_m3"])
            self.assertEqual(fine["integration"], "BDF")
            self.assertEqual(fine["model"], "finite_1d_diffusive_storage_signed_manning_BDF")
            self.assertEqual(fine["work"]["jacobian_rhs_evaluations"], 0)
            self.assertEqual(fine["work"]["observation_segment_initializations"], 3)
            self.assertEqual(fine["work"]["bdf_constructor_attempts"], 3 + fine["work"]["solver_reinitializations"])
            self.assertEqual(sum(fine["execution_progress"]["accepted_BDF_order_after_step_counts"].values()),
                             fine["execution_progress"]["accepted_steps"])
            self.assertEqual(fine["work"]["link_evaluations"], fine["work"]["rhs_evaluations"] * 3
                             + fine["work"]["jacobian_link_evaluations"] + fine["work"]["diagnostic_flux_link_evaluations"])
            self.assertLess(fine["max_untraced_residual_m3"], 1e-8)
            self.assertLess(fine["max_source_residual_m3"], 1e-8)
            self.assertLess(fine["max_tailwater_residual_m3"], 1e-8)
            self.assertTrue(fine["source_reached_engineered_outlet"] if scenario == "pulse" else fine["reverse_reached_sink"])


if __name__ == "__main__":
    unittest.main()
