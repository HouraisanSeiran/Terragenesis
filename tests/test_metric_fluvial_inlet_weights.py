import unittest

import numpy as np

from terrain_pipeline.surface_rivers.metric_fluvial_water_repair import (
    mask_inlet_upstream_weights,
)


def make_jwalk():
    return np.repeat([-1, 0, 1], 3)


class InletUpstreamWeightTests(unittest.TestCase):
    def base(self, shape=(5, 5)):
        weights = np.ones((*shape, 9)) / 9.
        celltype = np.zeros(shape, dtype=int)
        return weights, celltype

    def test_valid_multi_inlet_matches_original_arithmetic_float32(self):
        weights, celltype = self.base()
        weights = weights.astype(np.float32)
        celltype[0, 1] = 1
        celltype[0, 3] = 1
        weights[0, 1] = np.arange(9, dtype=np.float32)
        weights[0, 3] = np.linspace(1., 2., 9, dtype=np.float32)
        reference = weights.copy()
        jwalk = make_jwalk()
        upstream = jwalk < 0
        for column in (1, 3):
            reference[0, column, upstream] = 0.
            total = float(reference[0, column].sum())
            reference[0, column] /= total
        stats = mask_inlet_upstream_weights(weights, jwalk, celltype)
        np.testing.assert_array_equal(weights, reference)
        self.assertEqual(weights.dtype, np.float32)
        np.testing.assert_array_equal(weights[1:], (np.ones((4, 5, 9)) / 9.).astype(np.float32))
        self.assertEqual(stats["inlet_cells"], 2)
        self.assertEqual(stats["changed_cells"], 2)
        expected_removed = float(np.arange(9, dtype=np.float32)[upstream].sum())
        expected_removed += float(np.linspace(1., 2., 9, dtype=np.float32)[upstream].sum())
        self.assertEqual(stats["removed_upstream_weight_sum"], expected_removed)

    def test_valid_multi_inlet_matches_original_arithmetic_float64(self):
        weights, celltype = self.base()
        celltype[0, 1] = 1
        celltype[0, 3] = 1
        weights[0, 1] = np.arange(9, dtype=np.float64) * 0.137
        weights[0, 3] = np.linspace(1., 2., 9)
        original = weights.copy()
        reference = weights.copy()
        jwalk = make_jwalk()
        upstream = jwalk < 0
        for column in (1, 3):
            reference[0, column, upstream] = 0.
            total = float(reference[0, column].sum())
            reference[0, column] /= total
        stats = mask_inlet_upstream_weights(weights, jwalk, celltype)
        np.testing.assert_array_equal(weights, reference)
        self.assertEqual(weights.dtype, np.float64)
        expected_removed = float(original[0, 1, upstream].sum())
        expected_removed += float(original[0, 3, upstream].sum())
        self.assertEqual(stats["removed_upstream_weight_sum"], expected_removed)

    def test_later_inlet_zero_legal_weights_is_atomic(self):
        weights, celltype = self.base()
        celltype[0, 1] = 1
        celltype[0, 3] = 1
        jwalk = make_jwalk()
        upstream = jwalk < 0
        weights[0, 3] = 0.
        weights[0, 3, upstream] = 1. / 3.
        original = weights.copy()
        with self.assertRaisesRegex(ValueError, "no legal non-upstream"):
            mask_inlet_upstream_weights(weights, jwalk, celltype)
        np.testing.assert_array_equal(weights, original)

    def test_later_inlet_invalid_weights_are_atomic(self):
        jwalk = make_jwalk()
        upstream = jwalk < 0
        downstream = ~upstream
        downstream_index = int(np.flatnonzero(downstream)[0])
        upstream_index = int(np.flatnonzero(upstream)[0])
        cases = (
            ("negative", -1., downstream_index),
            ("nan", np.nan, downstream_index),
            ("inf", np.inf, downstream_index),
            ("negative_upstream", -1., upstream_index),
            ("nan_upstream", np.nan, upstream_index),
            ("inf_upstream", np.inf, upstream_index),
        )
        for name, value, index in cases:
            with self.subTest(kind=name):
                weights, celltype = self.base()
                celltype[0, 1] = 1
                celltype[0, 3] = 1
                weights[0, 3, index] = value
                original = weights.copy()
                with self.assertRaisesRegex(ValueError, "non-finite or negative"):
                    mask_inlet_upstream_weights(weights, jwalk, celltype)
                np.testing.assert_array_equal(weights, original)

    def test_non_inlet_invalid_weights_preserved(self):
        weights, celltype = self.base()
        celltype[0, 1] = 1
        celltype[0, 3] = 0
        celltype[1, 2] = 1
        jwalk = make_jwalk()
        weights[0, 3] = np.linspace(3., 4., 9)
        weights[0, 3, 0] = np.nan
        weights[0, 3, 1] = -5.
        weights[2, 2] = np.linspace(5., 6., 9)
        weights[2, 2, 4] = np.inf
        reference = weights.copy()
        mask_inlet_upstream_weights(weights, jwalk, celltype)
        np.testing.assert_array_equal(weights[0, 3], reference[0, 3])
        np.testing.assert_array_equal(weights[1], reference[1])
        np.testing.assert_array_equal(weights[2], reference[2])

    def test_no_inlet_returns_zero_stats_and_no_writes(self):
        weights, celltype = self.base()
        jwalk = make_jwalk()
        weights.setflags(write=False)
        original = weights.copy()
        stats = mask_inlet_upstream_weights(weights, jwalk, celltype)
        np.testing.assert_array_equal(weights, original)
        self.assertEqual(stats["inlet_cells"], 0)
        self.assertEqual(stats["changed_cells"], 0)
        self.assertEqual(stats["removed_upstream_weight_sum"], 0.)

    def test_inlet_without_upstream_weight_renormalizes_exactly(self):
        weights, celltype = self.base()
        celltype[0, 2] = 1
        jwalk = make_jwalk()
        upstream = jwalk < 0
        weights[0, 2, upstream] = 0.
        weights[0, 2, ~upstream] = np.array([2., 4., 8., 16., 32., 64.])
        reference = weights.copy()
        reference[0, 2, upstream] = 0.
        total = float(reference[0, 2].sum())
        reference[0, 2] /= total
        stats = mask_inlet_upstream_weights(weights, jwalk, celltype)
        np.testing.assert_array_equal(weights[0, 2], reference[0, 2])
        self.assertEqual(stats["inlet_cells"], 1)
        self.assertEqual(stats["changed_cells"], 0)
        self.assertEqual(stats["removed_upstream_weight_sum"], 0.)


if __name__ == "__main__":
    unittest.main()
