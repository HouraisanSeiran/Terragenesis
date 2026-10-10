import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.audit_td_morphology_candidates import write_audit


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "verification/td-morphology-candidates/td256-20261010-01"


class AuditTDMorphologyCandidatesTests(unittest.TestCase):
    def test_tiny_package_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            result = write_audit(PACKAGE, Path(directory))
            self.assertEqual(result["status"], "passed")
            self.assertTrue((Path(directory) / "audit.json").is_file())

    def test_summary_tampering_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "package"
            shutil.copytree(PACKAGE, package)
            summary_path = package / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["parent_graph_identity_sha256"] = "0" * 64
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            result = write_audit(package, Path(directory) / "audit")
            self.assertEqual(result["status"], "refused")
            self.assertTrue(result["failures"])

    def test_artifact_sha_tampering_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "package"
            shutil.copytree(PACKAGE, package)
            with (package / "inputs.npz").open("ab") as stream:
                stream.write(b"tampered")
            result = write_audit(package, Path(directory) / "audit")
            self.assertEqual(result["status"], "refused")

    def test_generation_entrypoints_are_not_called(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("tools.prepare_td_morphology_candidates._build", side_effect=AssertionError("generation called")):
                with mock.patch("terrain_pipeline.surface_rivers.metric_delta_product.build_delta_candidate_product", side_effect=AssertionError("generation called")):
                    result = write_audit(PACKAGE, Path(directory))
            self.assertEqual(result["status"], "passed")

    def test_existing_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "audit.json").write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                write_audit(PACKAGE, output)
            self.assertEqual((output / "audit.json").read_text(encoding="utf-8"), "existing")


if __name__ == "__main__":
    unittest.main()
