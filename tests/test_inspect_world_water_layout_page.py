import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tools.inspect_world_water_layout_page import inspect_page


class InspectWorldWaterLayoutPageTest(unittest.TestCase):
    def test_synthetic_page_statistics_and_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "page"
            page.mkdir()
            np.save(page / "elevation.npy", np.array([[-1., 1.], [2., -2.]]))
            np.save(page / "layout-classes.npy", np.array([[2, 2], [0, 1]], np.uint8))
            metadata = {"origin_native_xz": [-10, 20], "page_side_cells": 2,
                        "conditioning_parameters": {"sea_datum_m": 0.}}
            (page / "page.json").write_text(json.dumps(metadata), encoding="utf-8")
            _, _, _, report = inspect_page(page)
            self.assertEqual(report["classification_statistics"]["lake"]["fraction_below_water_level"], .5)
            self.assertEqual(report["classification_statistics"]["lake"]["min_m"], -1.)
            self.assertEqual(report["classification_statistics"]["sea"]["mean_m"], -2.)
            self.assertEqual(report["design_water_vs_below_level_agreement_fraction"], .75)
            self.assertEqual(report["design_water_above_or_at_level_cells"], 1)
            output = root / "inspection"
            subprocess.run([sys.executable, "tools/inspect_world_water_layout_page.py", str(page),
                            "--output-dir", str(output)], check=True, capture_output=True)
            self.assertTrue((output / "inspection.png").is_file())
            self.assertEqual(json.loads((output / "summary.json").read_text(encoding="utf-8"))["origin_native_xz"], [-10, 20])

    def test_missing_level_and_shape_fail_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / "page"
            page.mkdir()
            np.save(page / "elevation.npy", np.zeros((2, 2)))
            np.save(page / "layout-classes.npy", np.zeros((2, 2), np.uint8))
            (page / "page.json").write_text(json.dumps({"origin_native_xz": [0, 0], "page_side_cells": 2}), encoding="utf-8")
            output = root / "inspection"
            command = [sys.executable, "tools/inspect_world_water_layout_page.py", str(page), "--output-dir", str(output)]
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertFalse(output.exists())
            self.assertEqual(inspect_page(page, 0.)[3]["water_level_source"], "explicit CLI argument")
            np.save(page / "layout-classes.npy", np.zeros((1, 2), np.uint8))
            self.assertNotEqual(subprocess.run(command + ["--water-level-m", "0"], capture_output=True).returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
