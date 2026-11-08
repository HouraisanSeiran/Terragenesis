import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_td_hour_pages_acceptance_io import fixture, write_json
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.td_surface_reaches import _plain
from terrain_pipeline.td_hour_pages_acceptance_io import load_hour_pages_index
from tools.audit_td_storage_continuation import audit_scenario
from tools.publish_td_accepted_review import accepted_inputs, publish_review


class PublishAcceptedReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name).resolve()
        index, options = fixture(cls.root, rain_rate=1.)
        cold = _plain(load_hour_pages_index(cls.root / "index.json", **options))
        numerical = {}
        for scenario in ("ordinary", "strong"):
            comparison = cls.root / (scenario + "-comparison.json")
            write_json(comparison, index["scenarios"][scenario])
            report = audit_scenario(comparison, file_sha256(comparison))
            numerical[scenario] = write_json(cls.root / (scenario + "-audit.json"), report)
        cls.path = cls.root / "acceptance-index.json"
        cls.acceptance = dict(schema="td-independent-final-continuation-acceptance-v1",
            input_index=str(cls.root / "index.json"), input_index_sha256=options["expected_sha256"],
            acceptance_arguments=options, cold_acceptance=cold, numerical_reports=numerical,
            all_saved_numerical_gates_passed=True, original_inputs_and_frozen_code_unchanged=True)
        write_json(cls.path, cls.acceptance)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def tearDown(self):
        write_json(self.path, self.acceptance)

    def test_explicit_review_publication_and_independent_decoding(self):
        result = publish_review(self.path, file_sha256(self.path), self.root / "review")
        self.assertEqual(result["independent_native_audit"]["decoded_values_exact"], 612)
        self.assertFalse(result["frontend_connected"])
        self.assertFalse(result["hydraulic_ready"])

    def test_false_complete_gate_rejected_without_creating_output(self):
        value = dict(self.acceptance, all_saved_numerical_gates_passed=False)
        write_json(self.path, value)
        with self.assertRaisesRegex(ValueError, "complete"):
            publish_review(self.path, file_sha256(self.path), self.root / "rejected")
        self.assertFalse((self.root / "rejected").exists())

    def test_changed_independent_report_and_wrong_external_pin_rejected(self):
        with self.assertRaisesRegex(ValueError, "pin"):
            accepted_inputs(self.path, "0" * 64)
        record = self.acceptance["numerical_reports"]["ordinary"]
        report = Path(record["path"])
        original = report.read_bytes()
        try:
            report.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "report external pin"):
                accepted_inputs(self.path, file_sha256(self.path))
        finally:
            report.write_bytes(original)

    def test_failed_post_export_audit_cannot_leave_final_output(self):
        output = self.root / "failed-after-export"
        with patch("tools.publish_td_accepted_review.audit_binary", side_effect=ValueError("intentional audit failure")):
            with self.assertRaisesRegex(ValueError, "intentional"):
                publish_review(self.path, file_sha256(self.path), output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
