import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from terrain_pipeline.common_infra import publish_bytes
from tools.generate_td_terrain_rivers import main


class GeneratedPublicationTests(unittest.TestCase):
    def test_startup_and_completed_manifest_publish_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.json"
            publish_bytes(raw, b"{}")

            def saved_sample(output, registration):
                report = dict(accepted_edges=3, rejected_edges=1)
                publish_bytes(output / "report.json", json.dumps(report).encode())
                return report, []

            with patch(
                "tools.generate_td_terrain_rivers.snapshot_generation_sources",
                return_value=[],
            ), patch(
                "tools.generate_td_terrain_rivers.load_generated_td_source",
                return_value={},
            ), patch(
                "tools.generate_td_terrain_rivers.generate_sample",
                side_effect=saved_sample,
            ):
                main(["--report", str(raw), "--output", str(root / "batch")])
            startup = json.loads((root / "batch/startup-manifest.json").read_text())
            final = json.loads((root / "batch/manifest.json").read_text())
            self.assertEqual(startup["status"], "running")
            self.assertEqual(final["status"], "completed")
            self.assertEqual(len(final["samples"]), 6)

    def test_sample_failure_does_not_publish_completed_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.json"
            publish_bytes(raw, b"{}")
            with patch(
                "tools.generate_td_terrain_rivers.snapshot_generation_sources",
                return_value=[],
            ), patch(
                "tools.generate_td_terrain_rivers.load_generated_td_source",
                return_value={},
            ), patch(
                "tools.generate_td_terrain_rivers.generate_sample",
                side_effect=ValueError("saved geometry failed"),
            ):
                with self.assertRaisesRegex(ValueError, "saved geometry failed"):
                    main(["--report", str(raw), "--output", str(root / "batch")])
            self.assertTrue((root / "batch/startup-manifest.json").exists())
            self.assertFalse((root / "batch/manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
