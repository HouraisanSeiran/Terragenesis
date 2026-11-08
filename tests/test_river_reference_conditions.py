import unittest

import numpy as np

from tools.audit_river_reference_conditions import spatial_blocks


class ReferenceConditionsTests(unittest.TestCase):
    def test_all_windows_roles_and_coverage_are_fixed_before_metrics(self):
        height = np.arange(144 * 144, dtype=float).reshape(144, 144)
        valid = np.ones(height.shape, bool)
        unknown = np.zeros(height.shape, bool)
        valid[50, 50], unknown[50, 50] = False, True
        blocks = spatial_blocks(height, valid, unknown)
        self.assertEqual(len(blocks), 9)
        self.assertEqual([b["role"] for b in blocks[:3]], ["fit", "calibration", "real_holdout"])
        self.assertEqual(sum(b["eligible_complete_coverage"] for b in blocks), 8)
        self.assertEqual(blocks[4]["unknown_cells"], 1)
        occupied = np.zeros(height.shape, int)
        for block in blocks:
            z0, z1, x0, x1 = block["window_zx"]
            occupied[z0:z1, x0:x1] += 1
        np.testing.assert_array_equal(occupied, np.ones(height.shape))

    def test_overlapping_valid_unknown_and_nonfinite_known_rejected(self):
        height = np.zeros((48, 48))
        valid = np.ones(height.shape, bool)
        with self.assertRaises(ValueError):
            spatial_blocks(height, valid, valid)
        height[0, 0] = np.nan
        with self.assertRaises(ValueError):
            spatial_blocks(height, valid, np.zeros(height.shape, bool))


if __name__ == "__main__":
    unittest.main()
