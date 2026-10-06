import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terrain_pipeline.mountain_source_adapter import file_sha256
from tools.export_td_candidate_bounded_review import export


class BoundedReviewTests(unittest.TestCase):
    def test_invalid_explicit_capacity_rejected_before_io(self):
        for budget in (0, -1, 1024 ** 3 + 1, True, 1.5):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                export("missing", "output", budget)

    def test_explicit_capacity_delivery_and_no_solver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selection = root / "selection.json"
            selection.write_text("{}", encoding="utf-8")
            record = root / "selection-record.json"
            record.write_text(json.dumps(dict(path=str(selection), expected_sha256=file_sha256(selection))), encoding="utf-8")
            destination = root / "review"
            def exported(source_record, output, *, output_budget_bytes):
                self.assertEqual(output_budget_bytes, 768 * 1024 ** 2)
                self.assertEqual(source_record["expected_sha256"], file_sha256(selection))
                destination.mkdir()
                (destination / "index.json").write_text("{}", encoding="utf-8")
                return dict(identity_sha256="a" * 64, estimated_output_upper_bytes=699932672, artifact_bytes=123)
            with patch("tools.export_td_candidate_bounded_review.export_candidate_weather_review", side_effect=exported):
                result = export(record, destination, 768 * 1024 ** 2)
            self.assertFalse(result["solver_advanced"])
            self.assertEqual(result["compute_resource_budget_bytes"], 1024 ** 3)
            self.assertTrue((root / "review-delivery.json").exists())
            selection.write_text("changed", encoding="utf-8")
            with patch("tools.export_td_candidate_bounded_review.export_candidate_weather_review") as worker:
                with self.assertRaisesRegex(ValueError, "selection external pin"):
                    export(record, root / "rejected", 768 * 1024 ** 2)
                worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
