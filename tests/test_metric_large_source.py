import unittest

import numpy as np

from terrain_pipeline.surface_rivers.metric_large_source import load_large_td_source, stitch_tiles


class LargeSourceTests(unittest.TestCase):
    def test_stitch_tiles_owns_each_core_and_reports_seams(self):
        tiles = {}
        for row in range(2):
            for col in range(2):
                elevation = np.arange(9, dtype=np.float32).reshape(3, 3) + row * 9 + col
                climate = np.repeat(elevation[None, ...], 5, axis=0)
                tiles[row, col] = elevation, climate
        height, climate, audit = stitch_tiles(tiles, seam_tolerance_m=100.)
        np.testing.assert_array_equal(height, np.block([[tiles[0, 0][0][:2, :2], tiles[0, 1][0][:2, :2]],
                                                        [tiles[1, 0][0][:2, :2], tiles[1, 1][0][:2, :2]]]))
        self.assertEqual(climate.shape, (5, 4, 4))
        self.assertTrue(audit["accepted"])
        self.assertFalse(audit["hydrologic_seam_certified"])

    def test_missing_or_bad_pin_is_rejected(self):
        with self.assertRaises((FileNotFoundError, ValueError)):
            load_large_td_source("missing-source.npz", expected_sha256="0" * 64)

    def test_stitch_rejects_incomplete_or_nonfinite_tiles(self):
        with self.assertRaises(ValueError):
            stitch_tiles({(0, 0): (np.zeros((3, 3), np.float32), np.zeros((5, 3, 3), np.float32))},
                         seam_tolerance_m=1.)
        tiles = {(row, col): (np.ones((3, 3), np.float32), np.ones((5, 3, 3), np.float32))
                 for row in range(2) for col in range(2)}
        tiles[1, 1][0][0, 0] = np.nan
        with self.assertRaises(ValueError):
            stitch_tiles(tiles)


if __name__ == "__main__":
    unittest.main()
