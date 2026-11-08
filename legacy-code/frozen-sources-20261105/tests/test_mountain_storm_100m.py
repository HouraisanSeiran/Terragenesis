import unittest

from tools.verify_mountain_storm_100m import compare


class Storm100mComparisonTests(unittest.TestCase):
    def test_same_physical_comparison(self):
        old = {"peak_q_m3_s": 2., "peak_interval_start_h": 14.,
               "total_boundary_volume_m3": 100., "lake_max_stage_m": {"0": 30.},
               "water_account": {"rain_m3": 200., "final_storage_m3": 100.}}
        new = {"peak_q_m3_s": 3., "peak_interval_start_h": 13.75,
               "total_boundary_volume_m3": 110., "lake_max_stage_m": {"0": 30.002},
               "water_account": {"rain_m3": 200., "final_storage_m3": 90.}}
        difference = compare(new, old)
        self.assertEqual(difference["peak_q_difference_percent"], 50.)
        self.assertEqual(difference["peak_time_difference_h"], -.25)
        self.assertAlmostEqual(difference["boundary_volume_difference_percent"], 10.)
        self.assertAlmostEqual(difference["lake_max_stage_difference_m"]["0"], .002)
        self.assertEqual(difference["water_account_difference"]["rain_m3"], 0.)
        self.assertEqual(difference["water_account_difference"]["final_storage_m3"], -10.)

    def test_baseline_identity(self):
        baseline = {"peak_q_m3_s": 1., "peak_interval_start_h": 0.,
                    "total_boundary_volume_m3": 20., "lake_max_stage_m": {"0": 5.},
                    "water_account": {"rain_m3": 0., "initial_storage_m3": 40.}}
        difference = compare(baseline, baseline)
        self.assertEqual(difference["peak_q_difference_percent"], 0.)
        self.assertTrue(all(value == 0. for value in difference["water_account_difference"].values()))


if __name__ == "__main__":
    unittest.main()
