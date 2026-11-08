from dataclasses import replace
import unittest

import numpy as np

from terrain_pipeline.hybrid_river_hydraulics_common import Experiment, Section, compare_refinement, signed_flow
from terrain_pipeline.hybrid_river_hydraulics_radau import build_system
from terrain_pipeline.hybrid_river_hydraulics_v8 import (
    HydraulicDiagnosticStop, local_experiment, local_model, numerical_frame, run_experiment, translate_section)
from terrain_pipeline.hybrid_river_sections_v2 import accelerate_model, FastSection
from tests.hybrid_hydraulics_fixtures import tiny_model
from tools.prepare_hybrid_river_hydraulics_v8 import ROOT, file_sha, paired_refinement, precision_experiments, source_identity


class LocalVerticalFrameTests(unittest.TestCase):
    def test_synthetic_sections_storage_and_large_datum_flux_jacobian(self):
        sections = [Section.from_record(record) for record in (
            {"kind": "open_polyline", "sidewall_extension": "explicit_engineering_vertical",
             "polyline_transverse_elevation_m": [[-3, 1362.75], [-1, 1360.25], [1, 1360.25], [4, 1363.5]]},
            {"kind": "closed_polygon", "pressure_slot_width_m": 0.02,
             "polygon_transverse_elevation_m": [[-3, 1358.25], [3, 1358.25], [3.5, 1360.75], [-3.5, 1360.75]]})]
        datum = float(np.floor(min(section.floor_m for section in sections)))
        for section in sections:
            global_section = FastSection(section)
            translated = translate_section(section, datum)
            heads = [section.floor_m + 0.05, section.floor_m + 0.3]
            if section.crown_m is not None:
                heads.extend((section.crown_m, section.crown_m + 0.01, section.crown_m + 3))
            for head in heads:
                np.testing.assert_allclose(global_section.area_perimeter(head), translated.area_perimeter(head - datum),
                                           rtol=2e-11, atol=2e-11)
                area = global_section.area_perimeter(head)[0]
                self.assertAlmostEqual(translated.head_for_area(area) + datum, global_section.head_for_area(area), places=10)
        original = tiny_model()
        raised = replace(original, cells=tuple(replace(cell, section=translate_section(cell.section, -1350)) for cell in original.cells))
        frame = numerical_frame(raised)
        lowered = local_model(raised, frame)
        parameters = Experiment("pulse", 2, 0.5, 0.05, 1350.15, (1350.3, 1350.23, 1350.18), (0, 1, 2))
        global_system = build_system(accelerate_model(raised), parameters, 0.02)
        local_system = build_system(lowered, local_experiment(parameters, frame), 0.02)
        state = local_system.initial_state.copy()
        state[:9] = (np.array([0.3, 0.4, 0.3])[:, None] * local_system.initial_volumes).ravel()
        np.testing.assert_allclose(global_system.rhs_for(0.05)(0, state), local_system.rhs_for(0.05)(0, state), rtol=2e-10, atol=2e-10)
        np.testing.assert_allclose(global_system.jacobian_for(0.05)(0, state), local_system.jacobian_for(0.05)(0, state), rtol=2e-10, atol=2e-10)
        local_head = lowered.cells[1].section.head_for_area(1.00000000000001)
        displaced = lowered.cells[1].section.head_for_area(1.00000000000002)
        self.assertNotEqual(displaced, local_head)
        self.assertNotEqual(signed_flow(500, displaced - local_head, 9, 1e-4), 0)
        current_code, historical_code = source_identity()
        for name, expected in current_code.items():
            self.assertEqual(file_sha(ROOT / name), expected, name)
        self.assertEqual(len(historical_code), 33)

    def test_two_second_pulse_reverse_refinement_and_failure_frames(self):
        original = tiny_model()
        model = replace(original, cells=tuple(replace(cell, section=translate_section(cell.section, -1350)) for cell in original.cells))
        for scenario, tailwater in (("pulse", 1350.1), ("reverse_tailwater", 1350.4)):
            parameters = Experiment(scenario, 2, 0.5 if scenario == "pulse" else 0, 0.05 if scenario == "pulse" else 0,
                                    tailwater, (1350.2, 1350.2, 1350.2), (0, 0.5, 1, 2), max_step_s=0.2,
                                    source_arrival_threshold_m3=1e-8)
            base_parameters, refined_parameters = precision_experiments(parameters)
            base = run_experiment(model, base_parameters, 0.02)
            fine = run_experiment(model, refined_parameters, 0.02)
            self.assertEqual(compare_refinement(base, fine)["status"], "passed")
            self.assertEqual(paired_refinement(base, fine)["status"], "passed")
            origins = np.array([fine["untraced_water_volume_m3"], fine["source_tracer_mass_m3"], fine["tailwater_tracer_mass_m3"]])
            self.assertTrue(np.all(origins >= 0))
            np.testing.assert_array_equal(origins.sum(axis=0), fine["water_volume_m3"])
            np.testing.assert_array_equal(np.array(fine["local_hydraulic_head_m"]) + 1350, fine["hydraulic_head_m"])
            self.assertEqual(fine["local_tailwater_head_m"], tailwater - 1350)
            self.assertEqual(fine["work"]["jacobian_rhs_evaluations"], 0)
            self.assertTrue(fine["source_reached_engineered_outlet"] if scenario == "pulse" else fine["reverse_reached_sink"])
            with self.assertRaises(HydraulicDiagnosticStop) as stopped:
                run_experiment(model, base_parameters, 0.02, diagnostic_stop_s=0.5)
            progress = stopped.exception.progress
            self.assertEqual(progress["last_accepted_physical_time_s"], 0.5)
            self.assertGreater(progress["work"]["rhs_evaluations"], 0)
            self.assertEqual(progress["numerical_frame"], numerical_frame(model))
            for cell in progress["last_accepted_inventory"]["cells"]:
                self.assertEqual(cell["head_m"], cell["local_head_m"] + 1350)
            self.assertEqual(progress["global_parameters"]["tailwater_head_m"], tailwater)


if __name__ == "__main__":
    unittest.main()
