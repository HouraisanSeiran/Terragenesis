import json
import unittest

import numpy as np

from tests import test_td_hour_pages_review as review_fixture
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.td_hour_pages_review import export_hour_pages_review
from tools.audit_td_hour_pages_binary import audit, decode


class IndependentNativeBinaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        review_fixture.HourPagesReviewTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        review_fixture.HourPagesReviewTests.tearDownClass()

    def test_actual_binary_and_leaf_inventories_match_all_saved_frames(self):
        fixture = review_fixture.HourPagesReviewTests
        report = audit(fixture.destination / "index.json", file_sha256(fixture.destination / "index.json"))
        self.assertEqual(report["series_frames"], 50)
        self.assertEqual(report["decoded_values_exact"], 612)
        self.assertFalse(report["solver_advanced"])

    def test_shifted_row_offset_rejected_even_with_valid_binary(self):
        fixture = review_fixture.HourPagesReviewTests
        record = next(dict(value) for value in fixture.result["pages"] if value["kind"] == "cell_membership")
        record["row_offset"] = 1
        with self.assertRaisesRegex(ValueError, "coverage"):
            decode(fixture.destination, [record], "cell_membership", np.zeros((3, 4), dtype="<i8"), record["columns"])

    def test_rehashed_wet_count_is_checked_against_original_npz(self):
        fixture = review_fixture.HourPagesReviewTests
        index_path = fixture.destination / "index.json"
        original_index = index_path.read_bytes()
        manifest = json.loads(original_index)
        record = next(value for value in manifest["pages"] if value["kind"] == "leaf_states")
        target = fixture.destination / record["file"]
        original_page = target.read_bytes()
        try:
            payload = json.loads(original_page)
            payload["rows"][0]["wet_count"] += 1
            target.write_text(json.dumps(payload), encoding="utf-8")
            record["expected_sha256"] = file_sha256(target)
            record["bytes"] = target.stat().st_size
            index_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "wet count"):
                audit(index_path, file_sha256(index_path))
        finally:
            target.write_bytes(original_page)
            index_path.write_bytes(original_index)

    def test_optional_actual_hour_flux_binary_has_complete_coverage(self):
        fixture = review_fixture.HourPagesReviewTests
        destination = fixture.root / "independent-with-flux"
        export_hour_pages_review(fixture.input_index, destination, acceptance_arguments=fixture.arguments, include_hour_flux=True)
        index_path = destination / "index.json"
        result = audit(index_path, file_sha256(index_path))
        self.assertEqual(result["decoded_values_exact"], 1288)


if __name__ == "__main__":
    unittest.main()
