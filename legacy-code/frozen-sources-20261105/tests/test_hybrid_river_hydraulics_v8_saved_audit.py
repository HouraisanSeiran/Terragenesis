import copy
from dataclasses import asdict, replace
import json
import unittest

from tools.audit_hybrid_river_hydraulics import check_result
from tools.audit_hybrid_river_hydraulics_v8 import check_frame, expected_frame, local_geometry, projected_result
from tools.td_shared_channel_fine_saved_audit import digest


class LocalFrameSavedAuditTests(unittest.TestCase):
    def test_saved_two_second_projection_checks_actual_local_flux_and_inventory(self):
        from terrain_pipeline.hybrid_river_hydraulics_common import Experiment
        from terrain_pipeline.hybrid_river_hydraulics_v8 import run_experiment, translate_section
        from tests.hybrid_hydraulics_fixtures import tiny_model

        model = tiny_model()
        model = replace(model, cells=tuple(replace(cell, section=translate_section(cell.section, -1350))
                                          for cell in model.cells))
        geometry = {"hydraulic_cells": [], "hydraulic_links": [asdict(link) for link in model.links]}
        for cell in model.cells:
            section = cell.section.original
            if section.kind == "closed_polygon":
                saved_section = {"kind": "closed_polygon", "polygon_transverse_elevation_m": section.polygon,
                                 "pressure_slot_width_m": section.pressure_slot_width_m}
            else:
                saved_section = {"kind": "open_polyline", "polyline_transverse_elevation_m": [[0, 1350], [1, 1350]]}
            geometry["hydraulic_cells"].append({"cell_id": cell.cell_id, "kind": cell.kind,
                "length_m": cell.length_m, "roughness_manning": cell.roughness_manning, "section": saved_section})
        experiment = Experiment("pulse", 2, .5, .05, 1350.1, (1350.2, 1350.2, 1350.2),
                                (0, .5, 1, 2), max_step_s=.05, source_arrival_threshold_m3=1e-8)
        record = run_experiment(model, experiment, .02)
        parameters = json.loads(json.dumps(asdict(experiment)))
        record["local_solver_parameters_identity_sha256"] = digest(record["local_solver_parameters"])
        record = json.loads(json.dumps(record))
        projected, local, local_parameters = projected_result(record, geometry, parameters)
        report = check_result(projected, local, local_parameters)
        self.assertLess(report["max_per_cell_water_residual_m3"], 1e-9)
        self.assertTrue(report["three_origin_inventory_verified"])
        wrong = copy.deepcopy(record)
        wrong["local_solver_parameters"]["pulse_q_m3_s"] *= 2
        with self.assertRaisesRegex(ValueError, "local solver parameters"):
            projected_result(wrong, geometry, parameters)

    def test_common_datum_and_global_output_binding_reject_inconsistent_frame(self):
        geometry = {"hydraulic_cells": [{"section": {"kind": "open_polyline",
                    "polyline_transverse_elevation_m": [[-1, 1367], [0, 1366.5], [1, 1367]]}}]}
        original = copy.deepcopy(geometry)
        frame = expected_frame(geometry)
        self.assertEqual(frame["datum_m"], 1366)
        self.assertEqual(local_geometry(geometry, 1366)["hydraulic_cells"][0]["section"]["polyline_transverse_elevation_m"],
                         [[-1, 1], [0, .5], [1, 1]])
        self.assertEqual(geometry, original)
        record = {"times_s": [0, 1], "hydraulic_head_m": [[1366.75], [1366.875]],
                  "local_hydraulic_head_m": [[.75], [.875]], "numerical_frame": frame,
                  "local_tailwater_head_m": .9, "execution_progress": {"numerical_frame": frame}}
        parameters = {"tailwater_head_m": 1366.9}
        record["local_tailwater_head_m"] = parameters["tailwater_head_m"] - frame["datum_m"]
        check_frame(record, geometry, parameters)
        wrong = copy.deepcopy(record)
        wrong["local_hydraulic_head_m"][1][0] += .01
        with self.assertRaisesRegex(ValueError, "global/local"):
            check_frame(wrong, geometry, parameters)
        wrong = copy.deepcopy(record)
        wrong["numerical_frame"]["tiny_flux_deadband"] = True
        with self.assertRaisesRegex(ValueError, "local vertical datum"):
            check_frame(wrong, geometry, parameters)


if __name__ == "__main__":
    unittest.main()
