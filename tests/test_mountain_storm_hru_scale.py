import unittest

import numpy as np

from tools.verify_mountain_storm_hru_scale import partition_bins, error_metrics


class HRUScaleTests(unittest.TestCase):
    def test_pure_lake_merge_tie_and_unique_area(self):
        mask = np.ones((1, 3), np.bool_)
        lake = np.array([[False, True, False]])
        owner, details = partition_bins(mask, lake, [0., 0.], 30., 30.)
        np.testing.assert_array_equal(owner, [[0, 0, 1]])
        self.assertEqual(details["total_area_m2"], 2700.)
        self.assertEqual(details["pure_lake_merges"][0]["to_bin"], [0, 0])
        self.assertTrue(all(count > 0 for count in details["land_counts"]))

    def test_multiple_lake_bins_keep_original_land_target(self):
        mask = np.ones((1, 4), np.bool_)
        lake = np.array([[False, True, True, True]])
        owner, details = partition_bins(mask, lake, [0., 0.], 30., 30.)
        np.testing.assert_array_equal(owner, [[0, 0, 0, 0]])
        self.assertEqual(details["pure_lake_merges"][-1]["selected_D4_bin_hops"], 3)

    def test_disconnected_lake_rejected(self):
        mask = np.array([[True, False, True]])
        lake = np.array([[False, False, True]])
        with self.assertRaisesRegex(ValueError, "no D4"):
            partition_bins(mask, lake, [0., 0.], 30., 30.)

    def test_no_lake_merge_and_inactive_area(self):
        mask = np.array([[True, False, True]])
        owner, details = partition_bins(mask, np.zeros_like(mask), [-60., 0.], 30., 30.)
        np.testing.assert_array_equal(owner, [[0, -1, 1]])
        self.assertEqual(details["total_area_m2"], 1800.)
        self.assertEqual(details["pure_lake_merges"], [])

    def test_metrics_preserve_total_and_detect_local_error(self):
        owner = np.array([[0, 0]], np.int64)
        metrics = error_metrics(owner, np.array([[2., 4.]]), np.array([[3.]]), np.array([[False, True]]))
        self.assertEqual(metrics["max_cell_error_mm_h"], 1.)
        self.assertEqual(metrics["max_lake_error_mm_h"], 1.)
        self.assertEqual(metrics["max_signed_total_rain_rate_error_mm_h_cells"], 0.)

    def test_invalid_grid_rejected(self):
        mask = np.ones((1, 1), np.bool_)
        with self.assertRaises(ValueError):
            partition_bins(mask, np.zeros_like(mask), [float("nan"), 0.], 30., 30.)


if __name__ == "__main__":
    unittest.main()
