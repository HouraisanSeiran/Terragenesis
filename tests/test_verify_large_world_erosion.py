import unittest

from tools.verify_large_world_erosion import run


class ErosionVerificationTest(unittest.TestCase):
    def test_finite_erosion_comparisons_and_feedback(self):
        cases = run()["cases"]
        low, high, hard = (cases[name] for name in ("low_q_soft", "high_q_soft", "high_q_hard"))
        self.assertTrue(0. < low["eroded_rock_m3"] < high["eroded_rock_m3"] < high["rock_reserve_m3"])
        self.assertTrue(0. <= hard["eroded_rock_m3"] < high["eroded_rock_m3"])
        for case in cases.values():
            self.assertAlmostEqual(case["solid_residual_m3"], 0., delta=1e-9)
            self.assertAlmostEqual(case["eroded_rock_m3"],
                                   case["exported_solid_m3"] + case["remaining_mobile_solid_m3"] + case["remaining_loose_solid_m3"],
                                   delta=1e-9)
            self.assertAlmostEqual(case["slope"][1][0], (case["bed_m"][1][0] - case["bed_m"][1][1]) / 20.)
        self.assertLess(high["bed_m"][1][0], high["bed_m"][0][0])
        self.assertLess(high["slope"][1][0], high["slope"][0][0])
        self.assertGreater(high["water_depth_m"][1][0], high["water_depth_m"][0][0])
