import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terrain_pipeline.common_infra import file_sha256
from tools.prepare_basin_candidate_comparison import build


class CandidateComparisonTests(unittest.TestCase):
    def fixture(self, directory):
        candidates = [{"candidate_id": name, "changed_cells": 0} for name in
                      ("baseline", "valley_incision", "source_deposition", *(f"saddle_breach_{index}" for index in range(8)))]
        path = directory / "records.json"
        path.write_text(json.dumps({"schema": "td-basin-candidate-records-v1", "selected_candidate_id": "baseline", "candidates": candidates}), encoding="utf-8")
        return path

    def test_all_eleven_candidates_reported_without_adoption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(Path(directory))
            result = build(path, expected_sha256=file_sha256(path))
            self.assertEqual(len(result["treatments"]), 11)
            self.assertEqual(result["decision"]["selected"], "baseline")
            self.assertFalse(result["decision"]["automatic_adoption"])
            self.assertFalse(result["flags"]["cold_read_artifacts_verified"])
            self.assertFalse(result["flags"]["hydrology_recomputed"])
            self.assertFalse(result["treatments"][-1]["same_bed_saved_water_available"])

    def test_wrong_external_pin_and_duplicate_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(Path(directory))
            with self.assertRaises(ValueError):
                build(path, expected_sha256="0" * 64)
            records = json.loads(path.read_text(encoding="utf-8"))
            records["candidates"].append(records["candidates"][0])
            path.write_text(json.dumps(records), encoding="utf-8")
            with self.assertRaises(ValueError):
                build(path)

    def test_verified_mode_requires_both_external_pins_and_cold_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            path = self.fixture(directory)
            baseline = directory / "baseline.json"
            baseline.write_text(json.dumps({"inputs": {"saved": "fixture"}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                build(path, baseline_inputs=baseline)
            with patch('terrain_pipeline.basin_storage.load_candidate_comparison', return_value={"flags": {"publishable": False}}) as adapter:
                result = build(path, expected_sha256=file_sha256(path), baseline_inputs=baseline,
                               expected_baseline_sha256=file_sha256(baseline))
                adapter.assert_called_once_with(path.resolve(), expected_sha256=file_sha256(path), baseline_records={"saved": "fixture"})
            self.assertTrue(result["flags"]["cold_read_artifacts_verified"])
            self.assertFalse(result["flags"]["publishable"])


if __name__ == "__main__":
    unittest.main()
