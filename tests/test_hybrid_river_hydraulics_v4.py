from dataclasses import replace
import math
import unittest

import numpy as np

from terrain_pipeline.hybrid_river_hydraulics import Cell, Experiment, Section, compare_refinement, conveyance
from terrain_pipeline.hybrid_river_hydraulics_v4 import (
    HydraulicDiagnosticStop, HydraulicExecutionFailure, build_system, friction_state,
    jacobian_policy, roof_contact_length, run_experiment)
from terrain_pipeline.hybrid_river_sections_v2 import FastSection, accelerate_model
from tests.test_hybrid_river_hydraulics import tiny_model


class CrownTransitionTests(unittest.TestCase):
    def test_actual_roof_storage_and_head_bounded_jacobian(self):
        polygon = [[-3.1967823050840103, 1361.9088846317172],
                   [-1.9354601538332739, 1361.1410485018523], [0, 1360.9324492759495],
                   [1.9354601538332739, 1360.9335159861266], [3.1967823050840103, 1361.5633909417586],
                   [3.25678230507099, 1363.8488846317173], [-3.25678230507099, 1363.8488846317173]]
        for vertices, expected_roof in ((polygon, 6.51356461014198),
                                       ([[0, 0], [4, 0], [4, 4], [3, 4], [3, 2], [1, 2], [1, 4], [0, 4]], 2)):
            original = Section.from_record({"kind": "closed_polygon", "polygon_transverse_elevation_m": vertices,
                                            "pressure_slot_width_m": 0.02})
            section = FastSection(original)
            cell = Cell("gallery", "underground", 8, 0.03, section)
            self.assertAlmostEqual(roof_contact_length(section), expected_roof)
            crown = section.crown_m
            for offset in (-1e-6, 0, 1e-6, 0.01, 0.02, 0.03):
                head = crown + offset
                details = friction_state(cell, head, 0.02)
                area, perimeter = original.area_perimeter(head)
                self.assertAlmostEqual(details["area_m2"], area, places=8)
                self.assertAlmostEqual(details["actual_wetted_perimeter_m"], perimeter, places=8)
                self.assertAlmostEqual(section.head_for_area(area), head, places=8)
                self.assertEqual(friction_state(cell, head, 0)["effective_manning_conveyance"], conveyance(cell, head))
                if offset >= 0.02:
                    self.assertAlmostEqual(details["effective_friction_perimeter_m"], perimeter)
            below = friction_state(cell, crown - 1e-7, 0.02)
            at = friction_state(cell, crown, 0.02)
            self.assertLess(abs(at["effective_friction_perimeter_m"] - below["effective_friction_perimeter_m"]), 1e-6)
            self.assertLess(abs(at["effective_manning_conveyance"] - below["effective_manning_conveyance"]), 1e-3)
        model = accelerate_model(tiny_model())
        experiment = Experiment("pulse", 2, 0.5, 0.05, 0.2, (0.3, 1.000001, 0.3), (0, 1, 2))
        system = build_system(model, experiment, 0.02)
        matrix = system.jacobian_for(0.05)(0, system.initial_state)
        np.testing.assert_array_equal(matrix, system.jacobian_for(0.05)(0, system.initial_state))
        self.assertTrue(np.isfinite(matrix).all())
        np.testing.assert_array_equal(matrix[:, 3 * system.count:], 0)
        self.assertEqual(jacobian_policy(model, 0.02)["max_head_step_m"], 1e-6)
        self.assertLessEqual(system.work["jacobian_max_observed_head_step_m"], 1e-6 + 16 * math.ulp(1.000001))

    def test_short_stop_failure_telemetry_and_pulse_reverse_refinement(self):
        model = accelerate_model(tiny_model())
        experiment = Experiment("pulse", 2, 0.5, 0.05, 0.1, (0.2, 0.2, 0.2), (0, 0.5, 1, 2),
                                max_step_s=0.2, source_arrival_threshold_m3=1e-8)
        with self.assertRaises(HydraulicDiagnosticStop) as stopped:
            run_experiment(model, experiment, 0.02, diagnostic_stop_s=0.1)
        progress = stopped.exception.progress
        self.assertEqual(progress["last_accepted_physical_time_s"], 0.1)
        self.assertFalse(progress["physical_event_complete"])
        self.assertGreater(progress["min_accepted_step_s"], 0)
        self.assertGreater(progress["work"]["rhs_evaluations"], 0)
        self.assertAlmostEqual(progress["last_accepted_inventory"]["boundary_and_paired_ledgers_m3"][0], 0.005)
        with self.assertRaises(HydraulicExecutionFailure) as failed:
            run_experiment(model, replace(experiment, max_rhs_evaluations=3), 0.02)
        progress = failed.exception.progress
        self.assertEqual(progress["triggered_guard"], "max_rhs_evaluations")
        self.assertEqual(progress["work"]["rhs_evaluations"], 4)
        self.assertEqual(progress["accepted_steps"], 0)
        self.assertIsNone(progress["min_accepted_step_s"])
        self.assertEqual(progress["last_evaluation"]["context"], "Jacobian_log_column_0")
        self.assertFalse(progress["last_trial"]["is_accepted_state"])
        for scenario, tailwater in (("pulse", 0.1), ("reverse_tailwater", 0.4)):
            parameters = replace(experiment, scenario=scenario, tailwater_head_m=tailwater,
                                 pulse_q_m3_s=0.05 if scenario == "pulse" else 0,
                                 pulse_duration_s=0.5 if scenario == "pulse" else 0)
            base = run_experiment(model, parameters, 0.02)
            fine = run_experiment(model, replace(parameters, max_step_s=0.1, relative_tolerance=2.5e-8,
                                                 absolute_tolerance=2.5e-10), 0.02)
            self.assertEqual(compare_refinement(base, fine)["status"], "passed")
            self.assertLess(fine["max_water_residual_m3"], 1e-6)
            self.assertLess(fine["max_source_residual_m3"], 1e-8)
            self.assertLess(fine["max_tailwater_residual_m3"], 1e-8)
            work = fine["work"]
            self.assertEqual(work["jacobian_rhs_evaluations"], work["jacobian_evaluations"] * 4)
            self.assertEqual(work["link_evaluations"], (work["rhs_evaluations"] + work["jacobian_evaluations"]) * 3
                             + work["diagnostic_flux_link_evaluations"])
            self.assertTrue(fine["source_reached_engineered_outlet"] if scenario == "pulse" else fine["reverse_reached_sink"])


if __name__ == "__main__":
    unittest.main()
