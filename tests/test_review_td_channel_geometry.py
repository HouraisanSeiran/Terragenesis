"""Acceptance checks reject physically inconsistent saved geometry."""
from pathlib import Path
import tempfile
import unittest

import numpy as np

from tools.review_td_channel_geometry import cold_audit, generate, hardness_fields, render
from tools.review_td_lowland_runoff import product_identity


class ChannelGeometryReviewTests(unittest.TestCase):
    def candidate(self):
        source = {"original_td_m": np.full((3, 3), 10.),
            "receiver": np.array([1, 4, 1, 4, 7, 4, 7, -1, 7]),
            "permanent_channel_mask": np.ones((3, 3), bool),
            "seasonal_channel_mask": np.zeros((3, 3), bool),
            "object_flags": np.ones((3, 3), np.uint8),
            "mean_routed_q_m3_s": np.array([[1., 3., 1.], [2., 8., 2.], [1., 12., 1.]])}
        meta = {"spacing_m": 30., "origin_xz_m": [0., 0.], "seed": 3}
        arrays, metadata = generate(source, meta, Path("test-source.npz"), "test-sha")
        return source, arrays, metadata

    def test_cold_archive_passes_and_numeric_sections_saved(self):
        source, arrays, metadata = self.candidate()
        report = cold_audit(arrays, metadata, source)
        self.assertTrue(report["passed"], report)
        self.assertEqual(arrays["section_parametric_cut_m"].shape[1], 481)
        np.testing.assert_array_equal(source["original_td_m"], 10.)

    def test_rebound_identity_does_not_hide_wrong_width(self):
        source, arrays, metadata = self.candidate()
        arrays["channel_width_m"][0, 0] += 1.
        metadata["product_identity_sha256"] = product_identity(arrays, metadata)
        report = cold_audit(arrays, metadata, source)
        self.assertFalse(report["passed"])
        self.assertFalse(report["gates"]["independent_width_formula"])

    def test_rebound_identity_does_not_hide_cut_or_budget_tamper(self):
        source, arrays, metadata = self.candidate()
        arrays["cut_depth_m"][0, 0] += .5
        metadata["product_identity_sha256"] = product_identity(arrays, metadata)
        report = cold_audit(arrays, metadata, source)
        self.assertFalse(report["gates"]["independent_actual_raster_cut"])
        self.assertFalse(report["gates"]["bulk_volume_ledger"])

    def test_only_wetland_and_lake_flags_protect_excavation(self):
        source, _, _ = self.candidate()
        source["object_flags"][0] = [3, 5, 9]
        source["object_flags"][1, 0] = 17
        arrays, metadata = generate(source, {"spacing_m": 30., "origin_xz_m": [0., 0.], "seed": 3}, Path("test.npz"), "sha")
        np.testing.assert_array_equal(arrays["protected_mask"][0], [True, True, False])
        self.assertFalse(arrays["protected_mask"][1, 0])
        self.assertEqual(arrays["cut_depth_m"][0, 0], 0.)
        self.assertGreater(arrays["channel_width_m"][0, 0], 0.)
        self.assertGreater(arrays["channel_width_m"][0, 2], 0.)
        self.assertTrue(cold_audit(arrays, metadata, source)["passed"])

    def test_hardness_is_coordinate_stable_and_visuals_render(self):
        bed, bank = hardness_fields((3, 3), 30., [0., 0.], 3)
        smaller_bed, smaller_bank = hardness_fields((2, 2), 30., [30., 30.], 3)
        np.testing.assert_array_equal(bed[1:, 1:], smaller_bed)
        np.testing.assert_array_equal(bank[1:, 1:], smaller_bank)
        source, arrays, metadata = self.candidate()
        with tempfile.TemporaryDirectory() as folder:
            images = render(source, arrays, metadata, Path(folder))
            self.assertTrue(all((Path(folder)/name).stat().st_size > 1000 for name in images))


if __name__ == "__main__":
    unittest.main()
