import tempfile
import unittest
from copy import deepcopy

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_contracts import TerrainGrid
from terrain_pipeline.surface_rivers.metric_forcing import (
    SpatialRainRecipe, build_spatial_forcing, load_spatial_forcing_package,
    save_spatial_forcing_package,
    validate_spatial_forcing_package,
)


def grid(x0=0., columns=4):
    return TerrainGrid(np.zeros((2, columns), np.float64), np.ones((2, columns), bool),
                       x0_m=x0, z0_m=0., dx_m=30., dz_m=30.,
                       source_kind="generated_terrain", source_id="test",
                       source_sha256="a" * 64)


def recipe():
    return SpatialRainRecipe(seed=7, scales=((60., 1.),), amplitude=.4,
                             multiplier_min=.5, multiplier_max=1.5,
                             reference_origin_m_xz=(0., 0.), reference_spacing_m=30.,
                             reference_shape_zx=(2, 4))


class SpatialForcingTests(unittest.TestCase):
    def test_absolute_coordinates_match_tile_and_cold_read(self):
        times = np.array([0., 300., 600.])
        base = np.array([30., 0.])
        whole, package = build_spatial_forcing(grid(), times, base, recipe())
        tile, _ = build_spatial_forcing(grid(60., 2), times, base, recipe())
        np.testing.assert_array_equal(whole.rain_mm_h[:, :, 2:], tile.rain_mm_h)
        np.testing.assert_array_equal(package["arrays"]["multiplier"][:, 2:],
                                      build_spatial_forcing(grid(60., 2), times, base, recipe())[1]["arrays"]["multiplier"])
        self.assertTrue(np.all(package["arrays"]["multiplier"] > 0.))
        self.assertAlmostEqual(package["metadata"]["valid_multiplier_mean"], 1., places=12)
        with tempfile.TemporaryDirectory() as folder:
            path = folder + "/forcing.npz"
            save_spatial_forcing_package(path, package)
            cold = load_spatial_forcing_package(path, expected_sha256=file_sha256(path),
                                                expected_identity=package["identity_sha256"])
            np.testing.assert_array_equal(cold["arrays"]["multiplier"], package["arrays"]["multiplier"])

    def test_unknown_zero_and_invalid_recipe_rejected(self):
        terrain = grid()
        mask = terrain.valid_mask.copy()
        mask[0, 1] = False
        masked = TerrainGrid(terrain.elevation_m, mask, x0_m=0., z0_m=0., dx_m=30., dz_m=30.,
                             source_kind="generated_terrain", source_id="masked", source_sha256="a" * 64)
        forcing, package = build_spatial_forcing(masked, np.array([0., 300.]), np.array([30.]), recipe())
        self.assertEqual(forcing.rain_mm_h[0, 0, 1], 0.)
        self.assertEqual(package["arrays"]["multiplier"][0, 1], 0.)
        with self.assertRaises(ValueError):
            SpatialRainRecipe(seed=-1)
        with self.assertRaises(ValueError):
            SpatialRainRecipe(amplitude=100.)
        with self.assertRaises(ValueError):
            SpatialRainRecipe(scales=((60., 1e-320),))
        with self.assertRaises(ValueError):
            build_spatial_forcing(grid(), np.array([0., 300., 610.]), np.array([1., 1.]), recipe())

    def test_cold_validation_rejects_rehashed_semantic_promotion(self):
        _, original = build_spatial_forcing(grid(), np.array([0., 300.]), np.array([30.]), recipe())
        for key, value in (("calibration", "per_tile_mean_one"),
                           ("temporal_semantics", "instantaneous"),
                           ("reference_noise_mean", 100.),
                           ("target_origin_m_xz", [1e15, 0.]),
                           ("noise_algorithm", "unverified")):
            modified = deepcopy(original)
            modified["metadata"][key] = value
            modified["identity_sha256"] = identity(modified["arrays"], modified["metadata"])
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_spatial_forcing_package(modified)
        supplied_scales = [[60., 1.]]
        immutable = SpatialRainRecipe(scales=supplied_scales)
        supplied_scales[0][0] = 100.
        self.assertEqual(immutable.scales, ((60., 1.),))


if __name__ == "__main__":
    unittest.main()
