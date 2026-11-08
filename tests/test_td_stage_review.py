"""The review adapter preserves candidate identity and native arrays."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from tools.prepare_td_stage_review import file_pin, prepare, supplemental_summary

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stage_morphology_preview", ROOT / "web-preview/morphology_preview.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class StageReviewTests(unittest.TestCase):
    def test_spatial_v2_keeps_physical_and_engineering_decisions_separate(self):
        report = {"schema": "terragenesis-active-spatial-series-verification-v2",
                  "audit": {"status": "unresolved_original_active900s", "physical_status": "accepted_original_active900s",
                            "engineering_status": "pending_normal_worker", "minimum_accepted_level": 128,
                            "normal_resource_measurement": None, "observations": {"large": [0.] * 1000}}}
        summary = supplemental_summary(report)
        self.assertEqual(summary["status"], "unresolved_original_active900s")
        self.assertEqual(summary["physical_status"], "accepted_original_active900s")
        self.assertEqual(summary["engineering_status"], "pending_normal_worker")
        self.assertEqual(summary["minimum_accepted_level"], 128)
        self.assertNotIn("observations", summary)

    def supplemental_fixture(self, directory):
        original = json.loads(adapter.STAGE_MANIFEST.read_text(encoding="utf-8"))
        report = {"schema": "terragenesis-active-spatial-series-verification-v1", "source": {"sha256": "1" * 64},
            "policy": {"inventory_relative_tolerance": .03}, "cases": {"level128": {"path": "case/manifest.json", "sha256": "2" * 64}},
            "audit": {"status": "unresolved_original_active900s", "scope": "saved independent one dimensional scope",
                "spatial_error": {"128": {"active_sediment_relative_error": .04}},
                "resources": {"level128": {"performance_passed": True, "peak_rss_bytes": 123456}},
                "observations": {"large_raw_series": list(range(1000))}}}
        report_path = Path(directory) / "supplemental.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        manifest_path = Path(directory) / "manifest.json"
        pins = original["artifacts"]
        prepared = prepare(ROOT / pins["stage3"]["path"], ROOT / pins["cutoff"]["path"],
                           ROOT / pins["stage4"]["path"], manifest_path, supplemental_reports={"spatial-series": report_path})
        return report, report_path, manifest_path, prepared

    def test_saved_supplement_summary_and_full_export_keep_independent_failure(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".scratch") as directory:
            report, _, manifest, prepared = self.supplemental_fixture(directory)
            self.assertIsNone(prepared["supplemental_reports"]["spatial-series"]["status"])
            with patch.object(adapter, "STAGE_MANIFEST", manifest):
                payload = adapter.saved_case()
            review = payload["stage_review"]
            displayed = review["stage4"]["supplemental_reports"]["spatial-series"]
            self.assertEqual(displayed["summary"]["status"], "unresolved_original_active900s")
            self.assertEqual(displayed["summary"]["status_source"], "audit.status")
            self.assertEqual(displayed["summary"]["spatial_error"], report["audit"]["spatial_error"])
            self.assertEqual(displayed["summary"]["resources"], report["audit"]["resources"])
            self.assertNotIn("observations", displayed["summary"])
            self.assertNotIn("report", displayed)
            self.assertEqual(review["stage4_full_report"]["supplemental_reports"]["spatial-series"]["report"], report)
            self.assertFalse(payload["capabilities"]["publishable"])
            self.assertFalse(payload["capabilities"]["topology_mutation"])

    def test_changed_supplement_or_forged_summary_rejects_whole_payload(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".scratch") as directory:
            _, report_path, manifest, prepared = self.supplemental_fixture(directory)
            prepared["supplemental_reports"]["spatial-series"]["summary"]["status"] = "passed"
            manifest.write_text(json.dumps(prepared), encoding="utf-8")
            with patch.object(adapter, "STAGE_MANIFEST", manifest):
                with self.assertRaisesRegex(ValueError, "summary mismatch"):
                    adapter.saved_case()
            report_path.write_text("{}", encoding="utf-8")
            with patch.object(adapter, "STAGE_MANIFEST", manifest):
                with self.assertRaisesRegex(ValueError, "supplemental report pin mismatch"):
                    adapter.saved_case()

    def test_actual_native_arrays_identity_and_false_capabilities(self):
        stage = adapter._stage_review()
        self.assertIsNotNone(stage, "prepare the fixed stage review manifest first")
        payload = adapter.saved_case()
        arrays, metadata = stage["cutoff"]["arrays"], stage["cutoff"]["metadata"]
        np.testing.assert_array_equal(payload["terrain"]["height_m"], arrays["terrain_elevation_m"])
        self.assertEqual(payload["summary_body_sha256"], stage["cutoff"]["identity_sha256"])
        self.assertEqual(payload["parent_graph_identity_sha256"], metadata["parent_graph_identity_sha256"])
        self.assertFalse(payload["capabilities"]["publishable"])
        self.assertFalse(payload["capabilities"]["topology_mutation"])
        self.assertEqual(set(payload["candidates"]), {"cutoff", "delta", "bank", "braided", "fan", "floodplain"})
        self.assertEqual(len(payload["stage_review"]["failure_cases"]), 6)
        full_report = payload["stage_review"]["stage4_full_report"]
        self.assertEqual({key: full_report[key] for key in stage["stage4"]}, stage["stage4"])
        for name, report in stage.get("supplemental_reports", {}).items():
            self.assertEqual(full_report["supplemental_reports"][name]["report"], report["report"])
        full_cases = stage["stage4"]["cases"]["terrain"]["cases"]
        displayed_cases = payload["stage_review"]["stage4"]["cases"]["terrain"]["cases"]
        self.assertEqual(len(full_cases), len(displayed_cases))
        if metadata["status"] == "candidate":
            np.testing.assert_array_equal(payload["candidates"]["cutoff"]["after_bed_m"], arrays["after_bed_m"])
            self.assertEqual(payload["candidates"]["cutoff"]["event"], metadata["event_record"])

    def test_changed_pin_is_rejected_and_no_cache_masks_change(self):
        original = json.loads(adapter.STAGE_MANIFEST.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(dir=ROOT / ".scratch") as directory:
            manifest = Path(directory) / "manifest.json"
            original["artifacts"]["stage4"]["sha256"] = "0" * 64
            manifest.write_text(json.dumps(original), encoding="utf-8")
            with patch.object(adapter, "STAGE_MANIFEST", manifest):
                with self.assertRaisesRegex(ValueError, "pin mismatch"):
                    adapter.saved_case()

    def test_any_bad_child_refuses_whole_review_payload(self):
        original = json.loads(adapter.STAGE_MANIFEST.read_text(encoding="utf-8"))
        source_report = ROOT / original["artifacts"]["stage3"]["path"]
        report = json.loads(source_report.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(dir=ROOT / ".scratch") as directory:
            for artifact in report["artifacts"].values():
                artifact["path"] = str((source_report.parent / artifact["path"]).resolve())
            report["artifacts"]["delta"]["sha256"] = "0" * 64
            report_path = Path(directory) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            original["artifacts"]["stage3"] = file_pin(report_path)
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps(original), encoding="utf-8")
            with patch.object(adapter, "STAGE_MANIFEST", manifest):
                with self.assertRaisesRegex(ValueError, "hash|SHA256"):
                    adapter.saved_case()


if __name__ == "__main__":
    unittest.main()
