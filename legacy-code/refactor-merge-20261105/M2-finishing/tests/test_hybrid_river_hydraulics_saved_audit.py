import copy
import unittest

import numpy as np

from tools.audit_hybrid_river_hydraulics import (
    accuracy_parameters, check_accuracy_policy, check_three_origins, compare_saved,
    physical_identity, section_area, section_friction)


class SavedHydraulicsAuditTests(unittest.TestCase):
    def test_bdf_precision_binding_preserves_forcing_and_rejects_looser_gate(self):
        from tools.hybrid_hydraulics_preparation_common import accuracy_policy
        original = {"max_step_s": 10., "relative_tolerance": 1e-7, "absolute_tolerance": 1e-9,
                    "duration_s": 900., "pulse_q_m3_s": 6., "max_rhs_evaluations": 200000}
        base = accuracy_parameters(original, "base")
        refined = accuracy_parameters(original, "refined")
        self.assertEqual(base["max_step_s"], 2.5)
        self.assertEqual(refined["max_step_s"], 1.25)
        for key in ("duration_s", "pulse_q_m3_s", "max_rhs_evaluations"):
            self.assertEqual(base[key], original[key])
            self.assertEqual(refined[key], original[key])
        model = {"model_version": "fixture", "model_parameters": {}, "friction_policy": {},
                 "inventory_policy": {}, "forcing_configuration_pin": {}, "graph_identity_sha256": "graph",
                 "geometry_identity_sha256": "geometry", "integration": "BDF", "accuracy_policy": accuracy_policy()}
        model["physical_model_identity_sha256"] = physical_identity(model)
        index = {"integration": "BDF", "accuracy_policy": accuracy_policy(), "reused_cases": {},
                 "generated_cases": ["pulse-base"], "completed_cases": ["pulse-base"],
                 "physical_model_identity_sha256": model["physical_model_identity_sha256"]}
        check_accuracy_policy(index, model)
        index["accuracy_policy"]["comparison_gates_unchanged"]["volume_absolute_tolerance_m3"] = .001
        with self.assertRaisesRegex(ValueError, "BDF accuracy policy"):
            check_accuracy_policy(index, model)

    def test_actual_open_closed_and_pressure_section_storage(self):
        surface = {"kind": "open_polyline", "polyline_transverse_elevation_m": [[-1, 100], [0, 99], [1, 100]]}
        self.assertAlmostEqual(section_area(surface, 99.5), .25)
        cave = {"kind": "closed_polygon", "polygon_transverse_elevation_m": [[-1, 99], [1, 99], [1, 101], [-1, 101]], "pressure_slot_width_m": .02}
        self.assertAlmostEqual(section_area(cave, 100), 2)
        self.assertAlmostEqual(section_area(cave, 102), 4.02)
        cell = {"section": cave, "roughness_manning": .03}
        actual = section_friction(cell, 101, .001)
        self.assertAlmostEqual(actual["actual_wetted_perimeter_m"], 8)
        self.assertAlmostEqual(actual["effective_friction_perimeter_m"], 6)
        self.assertAlmostEqual(section_friction(cell, 101.001, .001)["effective_friction_perimeter_m"], 8)

    def test_cold_refinement_rejects_hidden_internal_exchange_difference(self):
        base = {"cell_ids": ["first", "second", "third"], "times_s": [0, 1],
                "hydraulic_head_m": [[1, 1, 1], [1, 1, 1]], "water_volume_m3": [[1, 1, 1], [1, 1, 1]],
                "source_tracer_mass_m3": [[0, 0, 0], [0, 0, 0]], "tailwater_tracer_mass_m3": [[0, 0, 0], [0, 0, 0]],
                "boundary_ledger_m3": [[0] * 6, [0] * 6]}
        for key in ("paired_link_water_integral_m3", "paired_link_source_integral_m3", "paired_link_tailwater_integral_m3"):
            base[key] = [[0, 0], [1, 1]]
        compare_saved(base, copy.deepcopy(base))
        changed = copy.deepcopy(base)
        changed["paired_link_water_integral_m3"][1][0] = 2
        with self.assertRaisesRegex(ValueError, "paired link refinement"):
            compare_saved(base, changed)
        diluted = copy.deepcopy(base)
        diluted["paired_link_water_integral_m3"][1] = [1000, 1000]
        changed = copy.deepcopy(diluted)
        changed["paired_link_water_integral_m3"][1][0] += .001
        with self.assertRaisesRegex(ValueError, "paired link refinement"):
            compare_saved(diluted, changed)
        volumes = np.asarray([[3., 4., 5.], [3., 4., 5.]])
        origins = {"untraced_water_volume_m3": volumes.tolist(), "outlet_untraced_out_m3": [0, 0]}
        for key in ("paired_link_water_integral_m3", "paired_link_source_integral_m3",
                    "paired_link_tailwater_integral_m3", "paired_link_untraced_integral_m3"):
            origins[key] = [[0, 0], [0, 0]]
        zeros = np.zeros_like(volumes)
        self.assertTrue(check_three_origins(origins, volumes, zeros, zeros, volumes[0], np.zeros((2, 6)))["three_origin_inventory_verified"])
        origins["untraced_water_volume_m3"][1][0] -= .01
        with self.assertRaisesRegex(ValueError, "sum of its three"):
            check_three_origins(origins, volumes, zeros, zeros, volumes[0], np.zeros((2, 6)))


if __name__ == "__main__":
    unittest.main()
