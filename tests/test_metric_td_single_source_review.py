"""Single-source TD river review contracts; no large solve or GPU."""

import copy
import unittest
from unittest.mock import patch

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_morphology_coupling import _pack, _unpack
from terrain_pipeline.surface_rivers.metric_td_single_source_review import review_water_cycle_case
from terrain_pipeline.surface_rivers.metric_water_cycle import load_water_cycle
from tools.review_td_single_source_river import DEFAULT_EVIDENCE, DEFAULT_REFERENCE, review


class SingleSourceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        cls.reference = json.loads(DEFAULT_REFERENCE.read_text(encoding="utf-8"))
        cls.evidence = load_water_cycle(DEFAULT_EVIDENCE, expected_sha256=file_sha256(DEFAULT_EVIDENCE))

    def test_one_source_all_four_layers_and_unassessed_reference(self):
        with patch("terrain_pipeline.surface_rivers.metric_boundary_coupling.solve_coupled",
                   side_effect=AssertionError("no replay of coupled solve")):
            result = review()
        self.assertEqual(result["source"]["raw_source_sha256"],
                         self.evidence["metadata"]["inputs"]["metadata"]["source_file_sha256"])
        self.assertFalse(result["source"]["natural_outlet_verified"])
        self.assertEqual(result["saved_water"]["boundary_kind"], "closed")
        self.assertLessEqual(abs(result["saved_water"]["whole_inventory_residual_m3"]),
                             result["saved_water"]["tolerance_m3"])
        self.assertIn(result["real_reference_comparison"]["status"],
                      ("context_only_scale_mismatch_not_assessed", "not_assessed_grid_extent_or_channel_support_mismatch"))
        self.assertFalse(result["natural_certification"])

    def test_rehashed_different_saved_terrain_is_rejected(self):
        altered = copy.deepcopy(self.evidence)
        inputs = _unpack(altered["arrays"], altered["metadata"], "inputs")
        height = inputs["arrays"]["terrain_height_m"].copy()
        height[0, 0] += 1.
        inputs["arrays"]["terrain_height_m"] = height
        inputs["identity_sha256"] = identity(inputs["arrays"], inputs["metadata"])
        _pack(altered["arrays"], altered["metadata"], "inputs", inputs)
        altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
        with self.assertRaises(ValueError):
            review_water_cycle_case(altered, real_reference=self.reference)

    def test_rehashed_boundary_switch_is_rejected(self):
        altered = copy.deepcopy(self.evidence)
        altered["metadata"]["boundary_kind"] = "unknown"
        altered["identity_sha256"] = identity(altered["arrays"], altered["metadata"])
        with self.assertRaises(ValueError):
            review_water_cycle_case(altered, real_reference=self.reference)

    def test_context_only_reference_not_reported_as_realism_pass(self):
        result = review_water_cycle_case(self.evidence, real_reference=self.reference)
        self.assertNotIn(result["real_reference_comparison"]["status"], ("pass", "fail"))

    def test_modified_reference_identity_is_rejected(self):
        changed = copy.deepcopy(self.reference)
        changed["natural_certification"] = True
        with self.assertRaises(ValueError):
            review_water_cycle_case(self.evidence, real_reference=changed)


if __name__ == "__main__":
    unittest.main()
