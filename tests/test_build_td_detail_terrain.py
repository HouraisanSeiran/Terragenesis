"""Declared arithmetic of the TD detail page: seeds, interpolation, damping weights."""
import json
import unittest

import numpy as np

from tools.build_td_detail_terrain import (
    COARSE_SPACING_M, NATIVE_SPACING_M, WORLD_SEED, array_digest, bilinear,
    channel_weights, derived_subseed, grid_axes, smoothstep,
)
from terrain_pipeline.surface_rivers.world_channel_graph import derive_noise_seed


class TdDetailTerrainTests(unittest.TestCase):
    def test_subseed_rule_matches_the_documented_world_noise_seeds(self):
        for purpose in ("climate", "rainfall", "light", "td-detail"):
            self.assertEqual(derived_subseed(purpose), derive_noise_seed(WORLD_SEED, purpose))
        self.assertEqual(derived_subseed("climate"), 1720059512)
        self.assertEqual(derived_subseed("rainfall"), 2124400829)
        self.assertEqual(derived_subseed("light"), 1694027887)
        self.assertNotEqual(derived_subseed("td-detail"), derived_subseed("climate"))

    def test_bilinear_reproduces_an_affine_field_exactly(self):
        page = np.array([[0.0, 10.0, 20.0], [1.0, 11.0, 21.0], [2.0, 12.0, 22.0]])
        gx = 1000.0 + np.arange(3) * 10000.0
        gz = 500.0 + np.arange(3) * 10000.0
        xs = np.array([3000.0, 7777.5, 12500.0])
        zs = np.array([2500.0, 9000.0])
        expected_z, expected_x = np.meshgrid(zs, xs, indexing="ij")
        expected = (expected_z - 500.0) / 10000.0 + (expected_x - 1000.0) / 10000.0 * 10.0
        np.testing.assert_allclose(bilinear(page, gx, gz, xs, zs), expected, atol=1e-12)

    def test_grid_axes_start_at_the_declared_origin(self):
        gx, gz = grid_axes([1250000.0, 1200000.0], COARSE_SPACING_M, (12, 12))
        self.assertEqual(float(gx[0]), 1250000.0)
        self.assertEqual(float(gz[0]), 1200000.0)
        self.assertEqual(float(gx[-1]), 1360000.0)
        self.assertEqual(float(gz[-1]), 1310000.0)

    def test_native_window_origin_is_a_whole_number_of_30_m_cells(self):
        self.assertEqual(NATIVE_SPACING_M, 30.0)
        self.assertEqual(int(43077 * NATIVE_SPACING_M), 1292310)
        self.assertEqual(int(42560 * NATIVE_SPACING_M), 1276800)
        self.assertEqual(513 * 30.0, 15390.0)

    def test_smoothstep_is_zero_one_sided_and_saturating(self):
        values = smoothstep(np.array([-1.0, 0.0, 0.5, 1.0, 2.0]))
        np.testing.assert_allclose(values, [0.0, 0.0, 0.5, 1.0, 1.0])

    def test_channel_weight_is_zero_on_the_trench_and_saturates_outside(self):
        geometry = {"node_xz_m": np.array([[0.0, 0.0], [0.0, 5000.0]]),
                    "receiver": np.array([1, -1], np.int64),
                    "width_m": np.array([800.0, 800.0]),
                    "depth_m": np.array([0.4, 0.4])}
        xs = np.arange(-2010.0, 2011.0, 30.0)   # includes the centreline at x = 0
        zs = np.arange(0.0, 5001.0, 30.0)
        footprint, distance_m, weight = channel_weights(
            geometry, xs, zs, spacing=30.0, guard_m=150.0, ramp_m=300.0)
        centre = distance_m[:, len(xs) // 2]
        # the canonical envelope is half width + BANK_SLOPE * depth = 400 + 0.8 m
        self.assertAlmostEqual(float(centre.min()), -400.8, places=6)
        self.assertTrue(footprint[:, len(xs) // 2].any())
        self.assertEqual(float(weight[:, len(xs) // 2].min()), 0.0)
        self.assertEqual(float(weight[:, 0].min()), 1.0)
        self.assertTrue(np.all(weight[footprint] == 0.0))
        ramp = weight[(~footprint) & (distance_m > 200.0) & (distance_m < 400.0)]
        self.assertTrue(np.all((ramp > 0.0) & (ramp < 1.0)))

    def test_channel_weight_refuses_an_empty_footprint(self):
        geometry = {"node_xz_m": np.array([[0.0, 0.0], [0.0, 5000.0]]),
                    "receiver": np.array([1, -1], np.int64),
                    "width_m": np.array([800.0, 800.0]),
                    "depth_m": np.array([0.4, 0.4])}
        with self.assertRaises(ValueError):
            channel_weights(geometry, np.array([1e6]), np.array([1e6]), 30.0, 1.0, 10.0)

    def test_array_digest_changes_with_payload(self):
        first = array_digest(np.zeros((2, 2)))
        self.assertEqual(first, array_digest(np.zeros((2, 2))))
        self.assertNotEqual(first, array_digest(np.ones((2, 2))))
        self.assertNotEqual(first, array_digest(np.zeros((2, 3))))

    def test_world_seed_is_the_pinned_constant(self):
        self.assertEqual(WORLD_SEED, 20261020)


if __name__ == "__main__":
    unittest.main()
