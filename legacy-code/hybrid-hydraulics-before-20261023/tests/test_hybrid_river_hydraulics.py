import unittest
from dataclasses import replace

import numpy as np

from terrain_pipeline.hybrid_river_hydraulics import Cell, Experiment, Link, Model, Section, compare_refinement, run_experiment


def tiny_model():
    surface = Section.from_record({"kind": "open_polyline", "polyline_transverse_elevation_m": [[0, 0], [1, 0]], "sidewall_extension": "explicit_engineering_vertical"})
    conduit = Section.from_record({"kind": "closed_polygon", "polygon_transverse_elevation_m": [[0, 0], [1, 0], [1, 1], [0, 1]], "pressure_slot_width_m": 0.01})
    return Model((Cell("sink", "surface", 1, 0.2, surface), Cell("cave", "underground", 1, 0.2, conduit), Cell("spring", "surface", 1, 0.2, surface)),
                 (Link("entry", "sink", "cave", 1, "sink_exchange"), Link("exit", "cave", "spring", 1, "spring_exchange")))


class HybridHydraulicsTests(unittest.TestCase):
    def test_pulse_storage_tracer_conservation_and_time_refinement(self):
        model = tiny_model()
        experiment = Experiment("pulse", 2, 0.5, 0.05, 0.1, (0.2, 0.2, 0.2), (0, 0.5, 1, 2), max_step_s=0.2, source_arrival_threshold_m3=1e-8)
        base = run_experiment(model, experiment)
        fine = run_experiment(model, replace(experiment, max_step_s=0.1, relative_tolerance=2.5e-8, absolute_tolerance=2.5e-10))
        self.assertTrue(fine["source_reached_engineered_outlet"])
        self.assertEqual(compare_refinement(base, fine)["status"], "passed")
        self.assertLess(fine["max_water_residual_m3"], 1e-6)
        self.assertLess(fine["max_source_residual_m3"], 1e-8)
        self.assertAlmostEqual(fine["boundary_ledger_m3"][-1][0], 0.025, places=8)
        self.assertEqual(fine["work"]["old_hll_face_work"], 0)
        self.assertTrue(np.all(np.asarray(fine["source_tracer_mass_m3"]) >= 0))
        self.assertAlmostEqual(model.cells[1].section.area_perimeter(1.2)[0], 1.002)
        self.assertAlmostEqual(model.cells[1].section.head_for_area(1.002), 1.2)

    def test_reverse_tailwater_real_signed_exchange_and_strict_refusals(self):
        model = tiny_model()
        experiment = Experiment("reverse_tailwater", 2, 0, 0, 0.4, (0.2, 0.2, 0.2), (0, 1, 2), max_step_s=0.2, source_arrival_threshold_m3=1e-8)
        result = run_experiment(model, experiment)
        self.assertTrue(result["reverse_reached_sink"])
        self.assertLess(result["paired_link_water_integral_m3"][-1][0], 0)
        self.assertEqual(result["boundary_ledger_m3"][-1][0], 0)
        self.assertGreater(result["tailwater_tracer_mass_m3"][-1][0], 0)
        self.assertFalse(result["natural_outlet_certified"])
        with self.assertRaises(ValueError):
            run_experiment(model, replace(experiment, initial_heads_m=(-1e-16, 0.2, 0.2)))
        with self.assertRaises(ValueError):
            run_experiment(model, replace(experiment, pulse_q_m3_s=0.1))
        with self.assertRaises(ValueError):
            run_experiment(model, replace(experiment, tailwater_head_m=0))
        with self.assertRaises(ValueError):
            run_experiment(replace(model, links=(model.links[1], model.links[0])), experiment)
        with self.assertRaises(ValueError):
            model.cells[1].section.head_for_area(-1e-16)


if __name__ == "__main__":
    unittest.main()
