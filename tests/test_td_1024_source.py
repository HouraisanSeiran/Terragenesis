import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from tools.generate_td_1024_source import main, stitch_tiles


def tiles(size=3):
    result = {}
    for row in range(2):
        for col in range(2):
            z, x = np.indices((size, size))
            height = (row * (size - 1) + z + col * (size - 1) + x).astype(np.float32)
            climate = np.broadcast_to(height, (5, size, size)).copy()
            result[row, col] = (height, climate)
    return result


class StitchTests(unittest.TestCase):
    def test_fixed_ownership_and_exact_seam(self):
        height, climate, audit = stitch_tiles(tiles(), seam_tolerance_m=0.)
        expected = np.add.outer(np.arange(4), np.arange(4)).astype(np.float32)
        np.testing.assert_array_equal(height, expected)
        np.testing.assert_array_equal(climate[0], expected)
        self.assertEqual(audit["elevation_m"]["max_abs"], 0.)
        self.assertTrue(audit["accepted"])
        self.assertEqual(audit["ownership"], "northwest_512_core_per_513_tile")

    def test_seam_difference_is_reported_without_blending(self):
        values = tiles()
        values[0, 1][0][:, 0] += 2.
        height, _, audit = stitch_tiles(values, seam_tolerance_m=.25)
        self.assertEqual(height[0, 2], 4.)
        self.assertEqual(audit["elevation_m"]["max_abs"], 2.)
        self.assertFalse(audit["accepted"])

    def test_rejects_bad_tile_shapes_and_nonfinite(self):
        values = tiles()
        values[1, 1] = (np.ones((2, 2)), np.ones((5, 2, 2)))
        with self.assertRaises(ValueError):
            stitch_tiles(values)
        values = tiles()
        values[0, 0][0][0, 0] = np.nan
        with self.assertRaises(ValueError):
            stitch_tiles(values)

    def test_default_cli_writes_plan_without_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate"
            with patch("diffusion.physical_backend.PhysicalTerrainDiffusionBackend") as backend:
                main(["--output", str(output)])
                backend.assert_not_called()
            plan = json.loads((output / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["shape"], [1024, 1024])
            self.assertEqual(plan["origin_native_xz"], [-6144, 2048])
            self.assertFalse(plan["gpu_inference_run"])
            self.assertFalse((output / "source.npz").exists())
            with self.assertRaises(FileExistsError):
                main(["--output", str(output)])


if __name__ == "__main__":
    unittest.main()
