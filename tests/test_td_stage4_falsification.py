import unittest
from pathlib import Path
import tempfile

from tools.verify_td_stage4_falsification import BUDGET, lake_ablation, peak_rss_bytes


class Stage4FalsificationTests(unittest.TestCase):
    def test_process_rss_measurement_has_bytes_and_frozen_limit(self):
        self.assertGreater(peak_rss_bytes(), 0)
        self.assertEqual(BUDGET["peak_rss_limit_bytes"], 1073741824)

    def test_actual_lake_removal_and_outlet_disable_are_cold_auditable(self):
        with tempfile.TemporaryDirectory() as directory:
            report = lake_ablation(Path(directory))
            self.assertEqual(len(report["cases"]), 3)
            for case in report["cases"]:
                self.assertEqual(set(case["cases"]), {"lake_on_closed", "lake_on_open", "lake_off_open"})
                for variant in case["cases"].values():
                    self.assertTrue(variant["cold_read_verified"])
                    self.assertEqual(variant["status"], "complete")
                    self.assertLess(abs(variant["ledger"]["residual_m3"]), 1e-8)
                    self.assertTrue(Path(variant["path"]).is_file())
                self.assertEqual(case["cases"]["lake_on_closed"]["ledger"]["external_m3"], 0.)


if __name__ == "__main__":
    unittest.main()
