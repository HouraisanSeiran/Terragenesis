import math
import unittest

import numpy as np

from terrain_pipeline.surface_rivers.metric_fluvial_slope_stability import relax_mobile_slopes


class SlopeStabilityTests(unittest.TestCase):
    def relax(self, bed, base, fraction=None, eligible=None, **kwargs):
        bed = np.asarray(bed, dtype=np.float64)
        fraction = np.full(bed.shape, .5) if fraction is None else np.asarray(fraction)
        eligible = np.ones(bed.shape, bool) if eligible is None else eligible
        return relax_mobile_slopes(bed, base, fraction, np.full(bed.shape, .3),
                                   eligible, dx_m=5., **kwargs)

    def assert_conservative(self, result):
        for field in ("raw_residual_bulk_m3", "raw_residual_sand_bulk_m3",
                      "raw_residual_mud_bulk_m3"):
            self.assertAlmostEqual(result.ledger[field], 0., delta=1e-9)
        self.assertEqual(result.ledger["exported_bulk_m3"], 0.)

    def test_actual_front_drop_relaxes_without_changing_input(self):
        bed = np.array([[0., 0.], [-1.9598298, -16.3442364]])
        original = bed.copy()
        result = self.relax(bed, np.array([[0., 0.], [-16.4475915, -16.7729112]]))
        self.assertTrue(result.converged)
        self.assertAlmostEqual(result.bed_m[1, 0] - result.bed_m[1, 1],
                               5. * math.tan(math.radians(30.)))
        self.assertGreater(result.ledger["transferred_bulk_m3"], 100.)
        np.testing.assert_array_equal(bed, original)
        self.assert_conservative(result)

    def test_supply_exhaustion_preserves_inherited_rock_cliff(self):
        bed = np.array([[0., 0.], [10., 0.]])
        base = np.array([[0., 0.], [9.8, 0.]])
        result = self.relax(bed, base, substrate_sand_fraction=.2)
        self.assertTrue(result.converged)
        np.testing.assert_allclose(result.bed_m[1], [9.8, .2], atol=1e-14)
        self.assertEqual(result.sand_fraction[1, 0], .2)
        self.assertEqual(result.active_layer[1, 0], .2)
        self.assertGreater(result.ledger["maximum_immobile_excess_after_m"], 6.)
        self.assert_conservative(result)
        unchanged = self.relax(bed, bed)
        np.testing.assert_array_equal(unchanged.bed_m, bed)
        self.assertEqual(unchanged.ledger["sweeps"], 0)

    def test_diagonal_uses_actual_distance_and_masks_boundaries(self):
        bed = np.zeros((3, 3))
        bed[1, 1] = 10.
        base = np.zeros_like(bed)
        eligible = np.zeros_like(bed, bool)
        eligible[1, 1] = eligible[2, 2] = True
        result = self.relax(bed, base, eligible=eligible)
        self.assertAlmostEqual(result.bed_m[1, 1] - result.bed_m[2, 2],
                               5. * math.sqrt(2.) * math.tan(math.radians(30.)))
        np.testing.assert_array_equal(result.bed_m[~eligible], bed[~eligible])
        np.testing.assert_array_equal(result.active_layer[~eligible], .3)
        self.assert_conservative(result)
        bed[0, 1] = 100.
        eligible[0, 1] = True
        row_zero = self.relax(bed, base, eligible=eligible)
        self.assertEqual(row_zero.bed_m[0, 1], 100.)

    def test_mixture_fills_cut_receiver_and_conserves_both_classes(self):
        bed = np.array([[0., 0.], [8., -3.]])
        base = np.array([[0., 0.], [-1., -4.]])
        fractions = np.array([[.5, .5], [.8, .1]])
        result = self.relax(bed, base, fractions)
        volume = result.ledger["transferred_bulk_m3"]
        expected = (25. * .1 + volume * .8) / (25. + volume)
        self.assertAlmostEqual(result.sand_fraction[1, 1], expected)
        self.assertEqual(result.sand_fraction[1, 0], .8)
        np.testing.assert_array_equal(result.active_layer[1], result.sand_fraction[1])
        self.assert_conservative(result)

    def test_multineighbor_is_deterministic_and_never_overdraws(self):
        bed = np.zeros((9, 9))
        bed[4, 4] = 20.
        base = np.zeros_like(bed)
        fractions = np.linspace(0., 1., bed.size).reshape(bed.shape)
        result = self.relax(bed, base, fractions)
        again = self.relax(bed, base, fractions)
        self.assertTrue(result.converged)
        self.assertTrue(np.all(result.bed_m >= base))
        self.assertLessEqual(result.ledger["maximum_mobile_excess_after_m"], 1e-6)
        np.testing.assert_array_equal(result.bed_m, again.bed_m)
        np.testing.assert_array_equal(result.sand_fraction, again.sand_fraction)
        self.assertEqual(result.ledger, again.ledger)
        self.assert_conservative(result)

    def test_finite_stop_returns_actual_unconverged_state(self):
        bed = np.zeros((12, 12))
        bed[5, 5] = 100.
        result = self.relax(bed, np.zeros_like(bed), max_sweeps=1)
        self.assertFalse(result.converged)
        self.assertEqual(result.ledger["sweeps"], 1)
        self.assertGreater(result.ledger["maximum_mobile_excess_after_m"], 1e-6)
        self.assertFalse(np.array_equal(result.bed_m, bed))
        self.assert_conservative(result)


if __name__ == "__main__":
    unittest.main()
