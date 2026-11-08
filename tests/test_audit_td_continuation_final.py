import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terrain_pipeline.common_infra import file_sha256
from tests.test_td_hour_pages_acceptance_io import fixture, write_json
from tools import audit_td_continuation_final as auditor


class FinalContinuationAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.index, self.arguments = fixture(self.root)
        (self.root / "fixture").write_bytes(b"controlled final acceptance fixture")
        self.code = {"fixture": file_sha256(self.root / "fixture")}
        self.index["code_sha256"] = self.code
        inputs = json.loads((self.root / "run-inputs.json").read_text(encoding="utf-8"))
        inputs["code_sha256"] = self.code
        write_json(self.root / "run-inputs.json", inputs)
        for scenario in ("ordinary", "strong"):
            write_json(self.root / (scenario + "-comparison.json"), self.index["scenarios"][scenario])
        self.pin = write_json(self.root / "index.json", self.index)["expected_sha256"]
        resource = {"index_sha256": self.pin, "scope": "complete ordinary+strong both steps execution",
                    "complete": True, "peak_rss_bytes": 1, "peak_private_bytes": 1}
        self.resource_record = write_json(self.root / "resource.json", resource)

    def accept(self):
        with patch.object(auditor, "ROOT", self.root), patch.object(auditor, "PRIMARY_PATH", self.root / "fixture"), patch.object(auditor, "PRIMARY_SHA256", self.code["fixture"]):
            return auditor.accept(self.root, self.pin, self.resource_record)

    def test_combines_actual_cold_loader_and_independent_raw_reductions(self):
        result = self.accept()
        self.assertTrue(result["all_saved_numerical_gates_passed"])
        self.assertTrue(result["cold_acceptance"]["io_chain_accepted"])
        self.assertTrue(result["original_inputs_and_frozen_code_unchanged"])
        self.assertFalse(result["hydraulic_ready"])
        self.assertEqual(set(result["numerical_reports"]), {"ordinary", "strong"})

    def test_standalone_comparison_cannot_diverge_from_final_index(self):
        comparison = dict(self.index["scenarios"]["ordinary"])
        comparison["gate_passed"] = False
        write_json(self.root / "ordinary-comparison.json", comparison)
        with self.assertRaisesRegex(ValueError, "differs"):
            self.accept()

    def test_frozen_dependency_changes_are_rejected(self):
        (self.root / "fixture").write_bytes(b"changed execution dependency")
        with self.assertRaisesRegex(ValueError, "frozen code"):
            self.accept()


if __name__ == "__main__":
    unittest.main()
