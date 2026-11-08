"""Corrected tests for tools/fluvial_delta_region_budget.py (hand-computed)."""

import unittest

import numpy as np

from tools.fluvial_delta_region_budget import summarize_phase_regions


class TestBudget(unittest.TestCase):
    def _run(self, names, delta, ref, fin, valid, ocean, **kw):
        return summarize_phase_regions(names, delta, ref, fin, valid, ocean, **kw)

    def test_phase_net_pos_neg_and_endpoint(self):
        # 2x3 grid, spacing 1 -> cell area 1.
        ref = np.array([[0.0, 1.0, np.nan], [0.5, -0.5, np.nan]])
        fin = np.array([[0.1, 1.0, np.nan], [0.0, -1.0, np.nan]])
        valid = np.array([[True, True, False], [True, True, False]])
        ocean = np.array([[True, True, False], [True, True, False]])
        d1 = np.array([[2.0, -1.0, np.nan], [7.0, 3.0, np.nan]])
        d2 = np.array([[-1.0, -2.0, np.nan], [0.0, 1.0, np.nan]])
        delta = np.stack([d1, d2])
        out = self._run(["p1", "p2"], delta, ref, fin, valid, ocean,
                        spacing_m=1.0, sea_level_m=0.0, band_m=0.25)
        r = out["regions"]["region_all_ocean"]
        self.assertEqual(r["cell_count"], 4)
        self.assertEqual(r["area_m2"], 4.0)
        # p1 = 2+(-1)+7+3 = 11 ; p2 = -1-2+0+1 = -2
        self.assertEqual(r["phase_net_m3"]["p1"], 11.0)
        self.assertEqual(r["phase_net_m3"]["p2"], -2.0)
        self.assertEqual(r["phase_positive_m3"]["p1"], 12.0)   # 2+7+3
        self.assertEqual(r["phase_negative_m3"]["p1"], -1.0)
        self.assertEqual(r["phase_positive_m3"]["p2"], 1.0)
        self.assertEqual(r["phase_negative_m3"]["p2"], -3.0)  # -1-2
        self.assertEqual(r["phase_net_total_m3"], 9.0)
        # endpoint heights: 0.1-0.0=0.1; 1.0-1.0=0; 0.0-0.5=-0.5; -1.0-(-0.5)=-0.5
        # sum = -0.9 ; *1 = -0.9
        self.assertAlmostEqual(r["endpoint_m3"], -0.9)
        self.assertAlmostEqual(r["residual_m3"], -9.9)

    def test_basic_numbers(self):
        ref = np.array([[0.0, 1.0]])
        fin = np.array([[1.0, 0.0]])
        valid = np.array([[True, True]])
        ocean = np.array([[True, True]])
        delta = np.stack([np.array([[3.0, -1.0]]), np.array([[-1.0, -4.0]])])
        out = self._run(["p1", "p2"], delta, ref, fin, valid, ocean,
                        spacing_m=1.0, sea_level_m=0.0, band_m=5.0)
        r = out["regions"]["region_all_ocean"]
        self.assertEqual(r["cell_count"], 2)
        self.assertEqual(r["area_m2"], 2.0)
        self.assertEqual(r["phase_net_m3"]["p1"], 2.0)
        self.assertEqual(r["phase_net_m3"]["p2"], -5.0)
        self.assertEqual(r["phase_positive_m3"]["p1"], 3.0)
        self.assertEqual(r["phase_negative_m3"]["p1"], -1.0)
        self.assertEqual(r["phase_net_total_m3"], -3.0)
        self.assertEqual(r["endpoint_m3"], 0.0)
        self.assertEqual(r["residual_m3"], 3.0)

    def test_spacing_scaling_endpoint_only(self):
        ref = np.array([[0.0]])
        fin = np.array([[0.5]])
        valid = np.array([[True]])
        ocean = np.array([[True]])
        delta = np.stack([np.array([[7.0]])])
        out = self._run(["p1"], delta, ref, fin, valid, ocean,
                        spacing_m=2.0, sea_level_m=0.0, band_m=10.0)
        r = out["regions"]["region_all_ocean"]
        self.assertEqual(out["cell_area_m2"], 4.0)
        self.assertEqual(r["area_m2"], 4.0)
        self.assertEqual(r["phase_net_m3"]["p1"], 7.0)
        self.assertEqual(r["endpoint_m3"], 2.0)
        self.assertEqual(r["residual_m3"], -5.0)

    def test_regions_fixed_on_reference(self):
        ref = np.array([[0.1, 0.5, 2.0]])
        fin = np.array([[9.0, 9.0, 9.0]])
        valid = np.array([[True, True, True]])
        ocean = np.array([[True, True, True]])
        delta = np.zeros((1, 1, 3))
        out = self._run(["p"], delta, ref, fin, valid, ocean,
                        spacing_m=1.0, sea_level_m=0.0, band_m=0.25)
        self.assertEqual(out["regions"]["region_all_ocean"]["cell_count"], 3)
        # |ref| <= 0.25 -> only 0.1
        self.assertEqual(out["regions"]["region_near_sea_level"]["cell_count"], 1)
        # ref > 0 -> all three
        self.assertEqual(out["regions"]["region_above_sea_level"]["cell_count"], 3)

    def test_duplicate_phase_aggregation(self):
        ref = np.zeros((1, 1))
        fin = np.zeros((1, 1))
        valid = np.ones((1, 1), dtype=bool)
        ocean = np.ones((1, 1), dtype=bool)
        delta = np.stack([np.array([[1.0]]), np.array([[2.0]]), np.array([[3.0]])])
        out = self._run(["a", "b", "a"], delta, ref, fin, valid, ocean, spacing_m=1.0)
        self.assertEqual(out["phase_names"], ["a", "b"])
        r = out["regions"]["region_all_ocean"]
        self.assertEqual(r["phase_net_m3"]["a"], 4.0)
        self.assertEqual(r["phase_net_m3"]["b"], 2.0)
        self.assertEqual(r["phase_net_total_m3"], 6.0)

    def test_signed_residual_preserved(self):
        ref = np.zeros((1, 1))
        fin = np.array([[1.0]])
        valid = np.ones((1, 1), dtype=bool)
        ocean = np.ones((1, 1), dtype=bool)
        delta = np.stack([np.array([[0.5]])])
        out = self._run(["p"], delta, ref, fin, valid, ocean, spacing_m=1.0)
        r = out["regions"]["region_all_ocean"]
        self.assertEqual(r["endpoint_m3"], 1.0)
        self.assertEqual(r["phase_net_total_m3"], 0.5)
        self.assertEqual(r["residual_m3"], 0.5)

    def test_empty_regions(self):
        ref = np.zeros((1, 1))
        fin = np.zeros((1, 1))
        valid = np.ones((1, 1), dtype=bool)
        ocean = np.zeros((1, 1), dtype=bool)
        delta = np.stack([np.array([[5.0]])])
        out = self._run(["p"], delta, ref, fin, valid, ocean, spacing_m=1.0)
        for rname in ("region_all_ocean", "region_near_sea_level", "region_above_sea_level"):
            r = out["regions"][rname]
            self.assertEqual(r["cell_count"], 0)
            self.assertEqual(r["area_m2"], 0.0)
            self.assertEqual(r["phase_net_m3"]["p"], 0.0)
            self.assertEqual(r["phase_net_total_m3"], 0.0)
            self.assertEqual(r["endpoint_m3"], 0.0)
            self.assertEqual(r["residual_m3"], 0.0)

    def test_invalid_vs_valid_nan(self):
        ref = np.array([[0.0, np.nan]])
        fin = np.array([[0.0, np.nan]])
        valid = np.array([[True, False]])
        ocean = np.array([[True, True]])
        delta = np.stack([np.array([[1.0, np.nan]])])
        out = self._run(["p"], delta, ref, fin, valid, ocean, spacing_m=1.0)
        self.assertEqual(out["regions"]["region_all_ocean"]["cell_count"], 1)
        self.assertEqual(out["regions"]["region_all_ocean"]["phase_net_m3"]["p"], 1.0)

    def test_valid_non_ocean_nonfinite_rejected(self):
        # valid=True, ocean=False -> still a valid cell -> finiteness enforced.
        ref = np.array([[np.nan]])
        fin = np.array([[0.0]])
        valid = np.array([[True]])
        ocean = np.array([[False]])
        delta = np.stack([np.array([[1.0]])])
        with self.assertRaises(ValueError):
            self._run(["p"], delta, ref, fin, valid, ocean, spacing_m=1.0)

    def test_empty_phases_retain_endpoint(self):
        ref = np.zeros((1, 1))
        fin = np.array([[2.0]])
        valid = np.ones((1, 1), dtype=bool)
        ocean = np.ones((1, 1), dtype=bool)
        delta = np.zeros((0, 1, 1))
        out = self._run([], delta, ref, fin, valid, ocean, spacing_m=1.0)
        self.assertEqual(out["phase_names"], [])
        r = out["regions"]["region_all_ocean"]
        self.assertEqual(r["phase_net_m3"], {})
        self.assertEqual(r["phase_net_total_m3"], 0.0)
        self.assertEqual(r["endpoint_m3"], 2.0)
        self.assertEqual(r["residual_m3"], 2.0)

    def test_no_mutation(self):
        ref = np.zeros((1, 1))
        fin = np.array([[1.0]])
        valid = np.ones((1, 1), dtype=bool)
        ocean = np.ones((1, 1), dtype=bool)
        delta = np.stack([np.array([[1.0]])])
        ref_c, fin_c, d_c, v_c, o_c = ref.copy(), fin.copy(), delta.copy(), valid.copy(), ocean.copy()
        self._run(["p"], delta, ref, fin, valid, ocean, spacing_m=1.0)
        np.testing.assert_array_equal(ref, ref_c)
        np.testing.assert_array_equal(fin, fin_c)
        np.testing.assert_array_equal(delta, d_c)
        np.testing.assert_array_equal(valid, v_c)
        np.testing.assert_array_equal(ocean, o_c)

    def test_malformed_inputs(self):
        ref = np.zeros((2, 2))
        fin = np.zeros((2, 2))
        valid = np.ones((2, 2), dtype=bool)
        ocean = np.ones((2, 2), dtype=bool)
        delta = np.zeros((1, 2, 2))
        base = dict(spacing_m=1.0)
        with self.subTest(case="names_is_str"):
            with self.assertRaises(TypeError):
                self._run("p", delta, ref, fin, valid, ocean, **base)
        with self.subTest(case="empty_name"):
            with self.assertRaises(ValueError):
                self._run([" "], delta, ref, fin, valid, ocean, **base)
        for name, args, kw in [
            ("bad_delta_ndim", (["p"], np.zeros((2, 2)), ref, fin, valid, ocean), base),
            ("phase_count_mismatch", (["p", "q"], delta, ref, fin, valid, ocean), base),
            ("bad_ref_shape", (["p"], delta, np.zeros((3, 3)), fin, valid, ocean), base),
            ("bad_fin_shape", (["p"], delta, ref, np.zeros((3, 3)), valid, ocean), base),
            ("bad_valid_shape", (["p"], delta, ref, fin, np.ones((3, 3), dtype=bool), ocean), base),
            ("bad_ocean_shape", (["p"], delta, ref, fin, valid, np.ones((3, 3), dtype=bool)), base),
            ("nonbool_valid", (["p"], delta, ref, fin, np.ones((2, 2)), ocean), base),
            ("nonbool_ocean", (["p"], delta, ref, fin, valid, np.ones((2, 2))), base),
            ("bad_spacing", (["p"], delta, ref, fin, valid, ocean), dict(spacing_m=-1.0)),
            ("nonfinite_spacing", (["p"], delta, ref, fin, valid, ocean), dict(spacing_m=np.inf)),
            ("bad_band", (["p"], delta, ref, fin, valid, ocean), dict(spacing_m=1.0, band_m=-0.5)),
            ("nonfinite_band", (["p"], delta, ref, fin, valid, ocean), dict(spacing_m=1.0, band_m=np.nan)),
            ("nonfinite_sea_level", (["p"], delta, ref, fin, valid, ocean), dict(spacing_m=1.0, sea_level_m=np.inf)),
        ]:
            with self.subTest(case=name):
                with self.assertRaises((TypeError, ValueError)):
                    self._run(*args, **kw)

    def test_nonfinite_on_valid_cells_rejected(self):
        valid = np.ones((1, 1), dtype=bool)
        ocean = np.ones((1, 1), dtype=bool)
        delta_ok = np.stack([np.array([[1.0]])])
        for case, ref, fin, delta in [
            ("ref_nan", np.array([[np.nan]]), np.zeros((1, 1)), delta_ok),
            ("fin_inf", np.zeros((1, 1)), np.array([[np.inf]]), delta_ok),
            ("delta_inf", np.zeros((1, 1)), np.zeros((1, 1)), np.stack([np.array([[np.inf]])])),
        ]:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    self._run(["p"], delta, ref, fin, valid, ocean, spacing_m=1.0)

    def test_native_types(self):
        out = self._run(["p"], np.stack([np.array([[1.0]])]),
                        np.zeros((1, 1)), np.array([[1.0]]),
                        np.ones((1, 1), dtype=bool), np.ones((1, 1), dtype=bool),
                        spacing_m=1.0)
        r = out["regions"]["region_all_ocean"]
        self.assertIsInstance(r["cell_count"], int)
        self.assertIsInstance(r["area_m2"], float)
        self.assertIsInstance(r["endpoint_m3"], float)
        self.assertIsInstance(r["residual_m3"], float)


if __name__ == "__main__":
    unittest.main()
