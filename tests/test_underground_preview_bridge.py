"""Local bridge guards without geometry recomputation."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("underground_preview", Path(__file__).resolve().parents[1]
                                             / "web-preview/underground_preview.py")
PREVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREVIEW)


class UndergroundBridgeTests(unittest.TestCase):
    def test_parameter_rejection_and_single_flight(self):
        recipe = dict(PREVIEW.DEFAULT_PARAMETERS)
        self.assertEqual(PREVIEW.parameters(recipe), recipe)
        for invalid in ({**recipe, "seed": True}, {**recipe, "width_scale": float("nan")},
                        {**recipe, "path": "outside"}, {**recipe, "lateral_amplitude_m": 4.}):
            with self.assertRaises(ValueError):
                PREVIEW.parameters(invalid)
        PREVIEW.LOCK.acquire()
        try:
            with self.assertRaises(PREVIEW.GenerationBusy):
                PREVIEW.generate(recipe)
        finally:
            PREVIEW.LOCK.release()

    def test_failure_releases_lock_and_no_shell_interpolation(self):
        with patch.object(PREVIEW.subprocess, "run", side_effect=PREVIEW.subprocess.TimeoutExpired("worker", 60)):
            with self.assertRaises(PREVIEW.subprocess.TimeoutExpired):
                PREVIEW.generate(dict(PREVIEW.DEFAULT_PARAMETERS))
        self.assertFalse(PREVIEW.LOCK.locked())
        with self.assertRaises(ValueError):
            PREVIEW.unique_object([("seed", 1), ("seed", 2)])


if __name__ == "__main__":
    unittest.main()
