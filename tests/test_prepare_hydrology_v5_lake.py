import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import prepare_hydrology_v5_lake as entry


class ExistingLakeRevalidationTests(unittest.TestCase):
    def test_both_resolutions_keep_failures_and_original_periodic_limits(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(entry, "limit_resources"), \
                patch.object(entry, "load_plan", return_value={"identity_sha256": "parent"}), \
                patch.object(entry, "file_sha256", return_value="a" * 64), \
                patch("tools.prepare_hydrology_domains.prepare_hybrid_lake_seasonal",
                      return_value={"status": "rejected", "reason": "bounded failure"}) as prepare, \
                patch('terrain_pipeline.runoff.load_hybrid_lake_bundle') as cold:
            output = Path(folder) / "validation"
            entry.revalidate_existing("plan.npz", "corrected.npz", output)
            self.assertEqual(prepare.call_count, 2)
            for call, substeps in zip(prepare.call_args_list, (1, 2)):
                config = call.args[-1]
                self.assertEqual(config["substeps_per_day"], substeps)
                self.assertEqual(config["max_years"], 150)
                self.assertEqual(config["convergence_depth_mm"], .01)
                self.assertEqual(config["convergence_lake_level_m"], .001)
            cold.assert_not_called()
            self.assertEqual(json.loads((output / "time-resolution-comparison.json").read_text())["status"],
                             "unavailable_periodic_rejection")
            self.assertTrue((output / "daily-result.json").exists())
            self.assertTrue((output / "halfday-result.json").exists())


if __name__ == "__main__":
    unittest.main()
