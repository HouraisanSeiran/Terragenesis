from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.hybrid_river_hydraulics import Experiment, compare_refinement
from terrain_pipeline.hybrid_river_hydraulics_v5 import (
    NUMERICAL_VERSION as SOURCE_NUMERICAL_VERSION, build_system as build_system_v5, jacobian_policy as source_jacobian_policy)
from terrain_pipeline.hybrid_river_hydraulics_v6 import (
    build_system, roof_contact_length, run_experiment, section_slopes)
from terrain_pipeline.hybrid_river_sections_v2 import accelerate_model
from tests.test_hybrid_river_hydraulics import tiny_model
from tools.prepare_hybrid_river_hydraulics_v6 import (
    FROZEN_CODE, atomic_save, bind_reused_pulse_base, identity, physical_model_identity)


class AnalyticJacobianTests(unittest.TestCase):
    def test_exact_v5_rhs_analytic_directional_and_native_crown_branches(self):
        model = accelerate_model(tiny_model())
        for heads, tailwater in (((0.3, 0.23, 0.18), 0.15), ((0.15, 0.2, 0.26), 0.35)):
            parameters = Experiment("pulse", 2, 0.5, 0.05, tailwater, heads, (0, 1, 2))
            system = build_system(model, parameters, 0.02)
            original = build_system_v5(model, parameters, 0.02)
            state = system.initial_state.copy()
            state[:9] = (np.array([0.3, 0.4, 0.3])[:, None] * system.initial_volumes).ravel()
            rhs = system.rhs_for(0.05)
            np.testing.assert_array_equal(rhs(0, state), original.rhs_for(0.05)(0, state))
            matrix = system.jacobian_for(0.05)(0, state)
            np.testing.assert_array_equal(matrix[:, 9:], 0)
            self.assertEqual(system.work["jacobian_rhs_evaluations"], 0)
            self.assertEqual(system.work["rhs_evaluations"], 1)
            self.assertEqual(system.work["jacobian_link_evaluations"], 6)
            self.assertTrue(np.isfinite(matrix).all())
            direction = np.zeros(len(state))
            direction[:9] = [0.11, -0.17, 0.13, 0.019, -0.027, 0.031, -0.016, 0.023, -0.014]
            for delta in (1e-5, 1e-7):
                independent = (rhs(0, state + delta * direction) - rhs(0, state - delta * direction)) / (2 * delta)
                np.testing.assert_allclose(matrix @ direction, independent, rtol=2e-6, atol=1e-8)
            ledger_rows = (23, 12, 14)
            for origin, row in enumerate(ledger_rows):
                balance = matrix[origin * 3:(origin + 1) * 3].sum(axis=0) + matrix[row]
                if origin == 2:
                    balance -= matrix[13]
                np.testing.assert_allclose(balance, 0, atol=1e-14)
        gallery = model.cells[1]
        roof = roof_contact_length(gallery.section)
        for head in (0.5, 1.0, 1.01, 1.02, 1.1):
            capacity, head_slope, capacity_slope = section_slopes(gallery, head, 0.02, roof)
            if head >= 1:
                self.assertAlmostEqual(head_slope, 100)
            if head == gallery.section.crown_m:
                self.assertAlmostEqual(capacity_slope, capacity * 5 / 3)
                continue
            step = 1e-9
            volume = gallery.section.area_perimeter(head)[0]
            displaced_head = gallery.section.head_for_area(volume + step)
            raised_capacity = section_slopes(gallery, displaced_head, 0.02, roof)[0]
            self.assertAlmostEqual(capacity_slope, (raised_capacity - capacity) / step, delta=max(1e-3, abs(capacity_slope) * 2e-5))
        tie = Experiment("reverse_tailwater", 2, 0, 0, 0.2, (0.2, 0.2, 0.2), (0, 1, 2))
        system = build_system(model, tie, 0.02)
        self.assertTrue(np.isfinite(system.jacobian_for(0)(0, system.initial_state)).all())

    def test_short_pulse_reverse_refinement_and_pinned_reuse_rejection(self):
        model = accelerate_model(tiny_model())
        pulse_base = None
        for scenario, tailwater in (("pulse", 0.1), ("reverse_tailwater", 0.4)):
            parameters = Experiment(scenario, 2, 0.5 if scenario == "pulse" else 0,
                                    0.05 if scenario == "pulse" else 0, tailwater,
                                    (0.2, 0.2, 0.2), (0, 0.5, 1, 2), max_step_s=0.2,
                                    source_arrival_threshold_m3=1e-8)
            base = run_experiment(model, parameters, 0.02)
            fine = run_experiment(model, replace(parameters, max_step_s=0.1, relative_tolerance=2.5e-8,
                                                 absolute_tolerance=2.5e-10), 0.02)
            self.assertEqual(compare_refinement(base, fine)["status"], "passed")
            origins = np.array([fine["untraced_water_volume_m3"], fine["source_tracer_mass_m3"],
                                fine["tailwater_tracer_mass_m3"]])
            self.assertTrue(np.all(origins >= 0))
            np.testing.assert_array_equal(origins.sum(axis=0), fine["water_volume_m3"])
            self.assertLess(fine["max_untraced_residual_m3"], 1e-8)
            work = fine["work"]
            self.assertEqual(work["jacobian_rhs_evaluations"], 0)
            self.assertEqual(work["link_evaluations"], work["rhs_evaluations"] * 3 + work["jacobian_link_evaluations"]
                             + work["diagnostic_flux_link_evaluations"])
            self.assertTrue(fine["source_reached_engineered_outlet"] if scenario == "pulse" else fine["reverse_reached_sink"])
            if scenario == "pulse":
                pulse_base, pulse_parameters = base, parameters
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = {"graph": {"path": "graph", "sha256": "a" * 64}}
            manifest = {"schema": "td-hybrid-river-hydraulic-model-parameters-v5",
                        "model_version": pulse_base["model_version"], "model_parameters": pulse_base["model_parameters"],
                        "friction_policy": pulse_base["friction_policy"], "inventory_policy": pulse_base["inventory_policy"],
                        "forcing_configuration_pin": {"path": "forcing", "sha256": "b" * 64},
                        "graph_identity_sha256": "c" * 64, "geometry_identity_sha256": "d" * 64,
                        "code_sha256": FROZEN_CODE, "numerical_version": SOURCE_NUMERICAL_VERSION,
                        "jacobian_policy": source_jacobian_policy(model, 0.02)}
            model_pin = atomic_save(root, "model.json", manifest)
            result = {**pulse_base, "schema": "td-hybrid-river-hydraulics-v5", "inputs": inputs,
                      "code_sha256": FROZEN_CODE, "parameters": asdict(pulse_parameters),
                      "parameters_identity_sha256": identity(asdict(pulse_parameters)),
                      "hydraulic_model_parameters": model_pin,
                      "hydraulic_model_parameters_identity_sha256": model_pin["identity_sha256"],
                      "graph_identity_sha256": manifest["graph_identity_sha256"],
                      "geometry_identity_sha256": manifest["geometry_identity_sha256"],
                      "numerical_version": manifest["numerical_version"], "jacobian_policy": manifest["jacobian_policy"]}
            result_pin = atomic_save(root, "base.json", result)
            source_index = {"schema": "td-hybrid-river-hydraulics-preparation-v5", "status": "failed_partial",
                            "completed_cases": ["pulse-base"], "artifacts": {"pulse-base.json": result_pin},
                            "model_version": manifest["model_version"], "friction_policy": manifest["friction_policy"],
                            "jacobian_policy": manifest["jacobian_policy"], "numerical_version": SOURCE_NUMERICAL_VERSION,
                            "inputs": inputs, "code_sha256": FROZEN_CODE, "hydraulic_model_parameters": model_pin}
            source_pin = atomic_save(root, "index.json", source_index)
            returned_pin, saved, provenance = bind_reused_pulse_base(source_pin, inputs, pulse_parameters, manifest, model)
            self.assertEqual(returned_pin, result_pin)
            self.assertEqual(provenance["physical_model_identity_sha256"], physical_model_identity(manifest))
            changed = {**manifest, "friction_policy": {**manifest["friction_policy"], "width_m": 0.03}}
            with self.assertRaises(ValueError):
                bind_reused_pulse_base(source_pin, inputs, pulse_parameters, changed, model)
            bad = atomic_save(root, "incomplete.json", {**source_index, "completed_cases": []})
            with self.assertRaises(ValueError):
                bind_reused_pulse_base(bad, inputs, pulse_parameters, manifest, model)
            fake_model = atomic_save(root, "fake-model.json", {**manifest, "numerical_version": "fixture_v5_numerical"})
            fake_result = atomic_save(root, "fake-result.json", {**result, "numerical_version": "fixture_v5_numerical",
                                                               "hydraulic_model_parameters": fake_model,
                                                               "hydraulic_model_parameters_identity_sha256": fake_model["identity_sha256"]})
            fake_index = atomic_save(root, "fake-index.json", {**source_index, "numerical_version": "fixture_v5_numerical",
                                                              "hydraulic_model_parameters": fake_model,
                                                              "artifacts": {"pulse-base.json": fake_result}})
            with self.assertRaises(ValueError):
                bind_reused_pulse_base(fake_index, inputs, pulse_parameters, manifest, model)


if __name__ == "__main__":
    unittest.main()
