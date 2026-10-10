import json
from pathlib import Path
import tempfile
import unittest

from terrain_pipeline.mountain_source_adapter import file_sha256
from tests.test_prepare_td_river_diagnostic import small_source
from tools.prepare_td_river_milestones import prepare, audit_saved
from tools.audit_td_river_milestones import audit


class PrepareMilestonesTests(unittest.TestCase):
    def test_saved_milestones_preserve_source_and_sampling_water(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.npz"
            source_sha = small_source(source)
            output = root / "milestones"
            result = prepare(output, source_path=source, source_sha256=source_sha)
            self.assertEqual(result["status"], "diagnostic_m1_m2")
            self.assertEqual(file_sha256(source), source_sha)
            report = audit_saved(output)
            self.assertEqual(report["sampling"]["dense_time_seconds"], [0., 300., 600., 900.])
            self.assertEqual(report["sampling"]["sparse_time_seconds"], [0., 900.])
            self.assertTrue(report["sampling"]["same_final_states"])
            self.assertTrue(report["sampling"]["same_cumulative_water"])
            self.assertTrue(report["tiles"]["rain_bit_exact"])
            self.assertEqual(report["tiles"]["internal_cut_open_count"], 0)
            self.assertEqual(len(report["routing_policies"]), 3)
            self.assertFalse(report["publishable"])
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["cold_read_verified"])
            guarded = audit(output, root / "cold-audit.json")
            self.assertEqual(guarded["status"], "cold_m1_m2_verified")
            self.assertEqual(guarded["mass_balance_m3"], report["mass_balance_m3"])
            with self.assertRaises(FileExistsError):
                prepare(output, source_path=source, source_sha256=source_sha)

    def test_bad_source_pin_publishes_only_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.npz"
            small_source(source)
            output = root / "refusal"
            result = prepare(output, source_path=source, source_sha256="0" * 64)
            self.assertEqual(result["status"], "refused")
            self.assertEqual([item.name for item in output.iterdir()], ["refusal.json"])


if __name__ == "__main__":
    unittest.main()
