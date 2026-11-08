from dataclasses import replace
import unittest

import numpy as np
from scipy.integrate._ivp.radau import RadauDenseOutput

from terrain_pipeline.hybrid_river_hydraulics import Experiment, compare_refinement
from terrain_pipeline.hybrid_river_hydraulics_v5 import (
    HydraulicExecutionFailure, NonpositiveWaterTrial, build_system,
    dense_positivity_violation, run_experiment)
from terrain_pipeline.hybrid_river_sections_v2 import accelerate_model
from tests.test_hybrid_river_hydraulics import tiny_model


class ThreeOriginInventoryTests(unittest.TestCase):
    def test_chain_jacobian_three_origin_ledgers_and_dense_interior_negativity(self):
        model = accelerate_model(tiny_model())
        for heads, tailwater in (((0.3, 0.23, 0.18), 0.15), ((0.15, 0.2, 0.26), 0.35)):
            parameters = Experiment("pulse", 2, 0.5, 0.05, tailwater, heads, (0, 1, 2), max_step_s=0.2)
            system = build_system(model, parameters, 0.02)
            state = system.initial_state.copy()
            state[:9] = (np.array([0.3, 0.4, 0.3])[:, None] * system.initial_volumes).ravel()
            rhs, jacobian = system.rhs_for(0.05), system.jacobian_for(0.05)
            derivative = rhs(0, state)
            rates = derivative[:9].reshape(3, 3)
            for origin, ledger_in, ledger_out in ((0, 0, derivative[23]),
                                                  (1, derivative[9], derivative[12]),
                                                  (2, derivative[13], derivative[14])):
                self.assertAlmostEqual(rates[origin].sum(), ledger_in - ledger_out, places=12)
            matrix = jacobian(0, state)
            np.testing.assert_array_equal(matrix, jacobian(0, state))
            np.testing.assert_array_equal(matrix[:, 9:], 0)
            changed = state.copy()
            changed[9:] = 1e9
            np.testing.assert_array_equal(rhs(0, changed), derivative)
            self.assertTrue(np.isfinite(matrix).all())
            direction = np.zeros(len(state))
            direction[:9] = [0.11, -0.17, 0.13, 0.019, -0.027, 0.031, -0.016, 0.023, -0.014]
            delta = 1e-6
            independent = (rhs(0, state + delta * direction) - rhs(0, state - delta * direction)) / (2 * delta)
            np.testing.assert_allclose(matrix @ direction, independent, rtol=3e-4, atol=2e-7)
            self.assertLessEqual(system.work["jacobian_max_observed_head_step_m"], 1e-6 + 1e-14)
            bad = state.copy()
            bad[:9] = 0
            with self.assertRaises(NonpositiveWaterTrial):
                rhs(0, bad)
        initial = np.zeros(24)
        initial[:3] = 1
        initial[3] = 0.1
        coefficients = np.zeros((24, 3))
        coefficients[3] = [-1, 1, 0]
        dense = RadauDenseOutput(0, 1, initial, coefficients)
        self.assertTrue(np.all(dense(0)[:9] >= 0))
        self.assertTrue(np.all(dense(1)[:9] >= 0))
        witness = dense_positivity_violation(dense, 3)
        self.assertEqual(witness["origin"], "source")
        self.assertEqual(witness["time_s"], 0.5)
        self.assertAlmostEqual(witness["minimum_origin_inventory_m3"], -0.15)
        thin = Experiment("reverse_tailwater", 2, 0, 0, 1.01, (0.001, 1.000001, 0.001), (0, 1, 2))
        system = build_system(model, thin, 0.02)
        self.assertTrue(np.isfinite(system.jacobian_for(0)(0, system.initial_state)).all())

    def test_thin_near_crown_pulse_reverse_conservation_and_refinement(self):
        model = accelerate_model(tiny_model())
        for scenario, tailwater, heads in (("pulse", 0.1, (0.2, 0.2, 0.2)),
                                          ("reverse_tailwater", 0.4, (0.2, 0.2, 0.2))):
            parameters = Experiment(scenario, 2, 0.5 if scenario == "pulse" else 0,
                                    0.05 if scenario == "pulse" else 0, tailwater, heads,
                                    (0, 0.5, 1, 2), max_step_s=0.2, source_arrival_threshold_m3=1e-8)
            base = run_experiment(model, parameters, 0.02)
            fine = run_experiment(model, replace(parameters, max_step_s=0.1, relative_tolerance=2.5e-8,
                                                 absolute_tolerance=2.5e-10), 0.02)
            self.assertEqual(compare_refinement(base, fine)["status"], "passed")
            origins = np.array([fine["untraced_water_volume_m3"], fine["source_tracer_mass_m3"],
                                fine["tailwater_tracer_mass_m3"]])
            self.assertTrue(np.all(origins >= 0))
            np.testing.assert_array_equal(origins.sum(axis=0), fine["water_volume_m3"])
            self.assertLess(fine["max_untraced_residual_m3"], 1e-8)
            self.assertLess(fine["max_source_residual_m3"], 1e-8)
            self.assertLess(fine["max_tailwater_residual_m3"], 1e-8)
            for origin, field in ((0, "paired_link_untraced_integral_m3"),
                                  (1, "paired_link_source_integral_m3"), (2, "paired_link_tailwater_integral_m3")):
                paired = np.array(fine[field])
                reconstructed = origins[origin, 0].copy()[None, :].repeat(4, axis=0)
                reconstructed[:, :-1] -= paired
                reconstructed[:, 1:] += paired
                ledgers = np.array(fine["boundary_ledger_m3"])
                if origin == 0:
                    reconstructed[:, -1] -= fine["outlet_untraced_out_m3"]
                elif origin == 1:
                    reconstructed[:, 0] += ledgers[:, 0]
                    reconstructed[:, -1] -= ledgers[:, 3]
                else:
                    reconstructed[:, -1] += ledgers[:, 4] - ledgers[:, 5]
                np.testing.assert_allclose(reconstructed, origins[origin], rtol=0, atol=1e-10)
            work = fine["work"]
            self.assertEqual(work["observation_segment_initializations"], 3)
            self.assertEqual(work["radau_constructor_attempts"], 3 + work["solver_reinitializations"])
            self.assertEqual(work["jacobian_rhs_evaluations"], work["jacobian_evaluations"] * 4)
            self.assertEqual(work["link_evaluations"], (work["rhs_evaluations"] + work["jacobian_evaluations"]) * 3
                             + work["diagnostic_flux_link_evaluations"])
            self.assertTrue(fine["source_reached_engineered_outlet"] if scenario == "pulse" else fine["reverse_reached_sink"])
            with self.assertRaises(HydraulicExecutionFailure) as failed:
                run_experiment(model, replace(parameters, max_rhs_evaluations=3), 0.02)
            self.assertEqual(failed.exception.progress["work"]["rhs_evaluations"], 4)
            self.assertEqual(failed.exception.progress["accepted_steps"], 0)


if __name__ == "__main__":
    unittest.main()
