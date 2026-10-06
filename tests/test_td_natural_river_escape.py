import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.diagnose_td_natural_river_escape import (
    INDEX,
    INDEX_SHA256,
    MAX_PLAN_BYTES,
    PLAN,
    _read_json,
    _verify_pins_unchanged,
    diagnose_escape_chain,
    load_saved_inputs,
    main,
)


class NaturalRiverEscapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network, cls.hierarchy, cls.plan, cls.pins = load_saved_inputs()

    def diagnose(self, plan):
        return diagnose_escape_chain(self.network, self.hierarchy, plan, self.pins)

    def test_saved_chain_has_exact_faces_and_only_static_comparisons(self):
        report = self.diagnose(self.plan)
        self.assertEqual(report["selected_terminal_cell_id"], 16088)
        self.assertEqual(report["selected_contribution_leaf_id"], 1020)
        self.assertGreater(len(report["escape_chain"]["physical_face_steps"]), 0)
        self.assertTrue(report["flags"]["potential_only"])
        self.assertFalse(report["flags"]["natural_outlet_verified"])
        self.assertFalse(report["flags"]["solver_advanced"])
        self.assertEqual(len(report["fixed_forcing_volume_comparison"]), 4)
        mask = self.network["arrays"]["selected_basin_mask"].ravel()
        bed = self.hierarchy["arrays"]["height_m"].ravel()[mask]
        stage = report["global_potential_escape_stage_m"]
        spacing = self.hierarchy["metadata"]["spacing_m"]
        expected = float(np.maximum(stage - bed, 0).sum() * spacing ** 2)
        self.assertAlmostEqual(report["hypothetical_original_bed_storage_m3"]["global_escape_stage"], expected)
        for scenario in report["fixed_forcing_volume_comparison"]:
            self.assertAlmostEqual(scenario["constant_rate_volume_m3"],
                                   scenario["rainfall_runoff_m3"] + scenario["baseflow_m3"])
        self.assertIn("auditor_sha256", report)
        self.assertIn("escape_plan", report["pins"])
        self.assertNotIn("terminal_to_terminal_centerline", json.dumps(report))

    def test_bad_face_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        leaf = int(self.hierarchy["arrays"]["contribution_owner"].ravel()[16088])
        record = next(item for item in plan["leaves"] if item["leaf_id"] == leaf)
        record["minimum_face"]["face_cell_ids"][0] = 0
        with self.assertRaisesRegex(ValueError, "minimum face"):
            self.diagnose(plan)

    def test_parent_cycle_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        leaf = int(self.hierarchy["arrays"]["contribution_owner"].ravel()[16088])
        record = next(item for item in plan["leaves"] if item["leaf_id"] == leaf)
        record["parent_leaf_id"] = leaf
        with self.assertRaisesRegex(ValueError, "rank/cycle"):
            self.diagnose(plan)

    def test_minimax_stage_tampering_is_rejected(self):
        plan = copy.deepcopy(self.plan)
        leaf = int(self.hierarchy["arrays"]["contribution_owner"].ravel()[16088])
        record = next(item for item in plan["leaves"] if item["leaf_id"] == leaf)
        record["minimum_escape_stage_m"] += 1.0
        with self.assertRaisesRegex(ValueError, "minimax"):
            self.diagnose(plan)

    def test_foreign_hierarchy_and_source_are_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan["hierarchy_identity_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "foreign hierarchy"):
            self.diagnose(plan)
        plan = copy.deepcopy(self.plan)
        plan["source_identity_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "foreign hierarchy"):
            self.diagnose(plan)

    def test_external_pins_and_no_overwrite(self):
        with self.assertRaisesRegex(ValueError, "SHA"):
            load_saved_inputs(index_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "SHA"):
            _read_json(PLAN, "0" * 64, MAX_PLAN_BYTES)
        with self.assertRaisesRegex(ValueError, "identity"):
            load_saved_inputs(plan_identity="0" * 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing.json"
            path.write_text("keep", encoding="utf-8")
            with patch("tools.diagnose_td_natural_river_escape.load_saved_inputs") as loader:
                with self.assertRaises(FileExistsError):
                    main(["--output", str(path)])
                loader.assert_not_called()
            self.assertEqual(path.read_text(encoding="utf-8"), "keep")

    def test_index_flags_and_prepublish_pins(self):
        index = _read_json(INDEX, INDEX_SHA256, 2 * 1024 * 1024)
        index["hydraulic_ready"] = True
        with patch("tools.diagnose_td_natural_river_escape._read_json", return_value=index):
            with self.assertRaisesRegex(ValueError, "certification flags"):
                load_saved_inputs()
        pins = copy.deepcopy(self.pins)
        pins["network"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "input changed"):
            _verify_pins_unchanged(pins)

    def test_cold_saved_diagnosis_does_not_build_any_artifact(self):
        with patch("terrain_pipeline.td_basin_hierarchy.build_basin_hierarchy",
                   side_effect=AssertionError("hierarchy build")), patch(
                "terrain_pipeline.td_natural_river_network.build_natural_river_network",
                side_effect=AssertionError("network build")), patch(
                "terrain_pipeline.td_basin_escape_plan.make_basin_escape_plan",
                side_effect=AssertionError("escape plan build")):
            network, hierarchy, plan, pins = load_saved_inputs()
            report = diagnose_escape_chain(network, hierarchy, plan, pins)
        self.assertEqual(report["selected_terminal_cell_id"], 16088)
        self.assertTrue(report["flags"]["potential_only"])


if __name__ == "__main__":
    unittest.main()
