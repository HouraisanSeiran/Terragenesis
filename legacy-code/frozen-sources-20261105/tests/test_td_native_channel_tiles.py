import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.td_native_channel_geometry import GeometryRecipe, build_channel_geometry
from terrain_pipeline.td_native_channel_tiles import (
    TileRecipe, audit_tile_geometry, build_channel_tile, load_channel_tile, save_channel_tile,
    split_window_2x2, validate_channel_tile,
)
from tests.test_td_native_channel_geometry import fixture


class NativeChannelTileTests(unittest.TestCase):
    def geometry(self):
        return build_channel_geometry(*fixture())

    def test_four_independent_tiles_have_exact_shared_boundaries(self):
        geometry = self.geometry()
        window = (0, 60, 0, 60)
        full = build_channel_tile(geometry, window=window)
        parts = [build_channel_tile(geometry, window=part) for part in split_window_2x2(window)]
        for name in ("native_bilinear_bed_m", "candidate_bed_m", "candidate_cut_m"):
            np.testing.assert_array_equal(parts[0]["arrays"][name][:, -1], parts[1]["arrays"][name][:, 0])
            np.testing.assert_array_equal(parts[0]["arrays"][name][-1], parts[2]["arrays"][name][0])
            for part in parts:
                first_x, last_x, first_z, last_z = part["metadata"]["window"]
                np.testing.assert_array_equal(part["arrays"][name], full["arrays"][name][first_z:last_z + 1, first_x:last_x + 1])

    def test_edge_union_order_independent_and_no_fill(self):
        geometry = self.geometry()
        active = np.flatnonzero(geometry["arrays"]["edge_geometry_active"])
        first = build_channel_tile(geometry, window=(0, 60, 0, 60))
        second = build_channel_tile(geometry, window=(0, 60, 0, 60), edge_order=active[::-1])
        self.assertEqual(first["identity_sha256"], second["identity_sha256"])
        self.assertTrue(np.all(first["arrays"]["candidate_bed_m"] <= first["arrays"]["native_bilinear_bed_m"]))

    def test_cosine_normal_profile_and_bounded_caps(self):
        hierarchy, page = fixture()
        geometry = build_channel_geometry(hierarchy, page, GeometryRecipe(
            minimum_width_m=10., maximum_width_m=10., minimum_depth_m=1., maximum_depth_m=1.))
        arrays = build_channel_tile(geometry, window=(0, 60, 0, 60))["arrays"]
        self.assertEqual(arrays["candidate_cut_m"][15, 30], 1.)
        self.assertAlmostEqual(arrays["candidate_cut_m"][15, 32], .5 * (1. + np.cos(np.pi * 2. / 5.)))
        self.assertEqual(arrays["candidate_cut_m"][15, 35], 0.)
        self.assertEqual(arrays["candidate_cut_m"][15, 40], 0.)

    def test_zero_q_leaves_native_bilinear_bed_unchanged(self):
        hierarchy, page = fixture()
        geometry = build_channel_geometry(hierarchy, page, GeometryRecipe(active_q_threshold_m3_s=1.))
        arrays = build_channel_tile(geometry, window=(0, 60, 0, 60))["arrays"]
        self.assertFalse(arrays["candidate_cut_m"].any())
        np.testing.assert_array_equal(arrays["candidate_bed_m"], arrays["native_bilinear_bed_m"])
        self.assertEqual(arrays["native_bilinear_bed_m"][15, 15], 2.5)

    def test_sampling_common_world_points_exact(self):
        geometry = self.geometry()
        tiles = {spacing: build_channel_tile(geometry, window=(0, int(60 / spacing), 0, int(60 / spacing)),
                                              recipe=TileRecipe(spacing)) for spacing in (.5, 1., 2.)}
        for name in ("native_bilinear_bed_m", "candidate_cut_m", "candidate_bed_m"):
            np.testing.assert_array_equal(tiles[.5]["arrays"][name][::2, ::2], tiles[1.]["arrays"][name])
            np.testing.assert_array_equal(tiles[1.]["arrays"][name][::2, ::2], tiles[2.]["arrays"][name])

    def test_cold_tiles_load_order_and_geometry_reconstruction(self):
        geometry = self.geometry()
        with tempfile.TemporaryDirectory() as directory:
            records = []
            for index, window in enumerate(split_window_2x2((0, 60, 0, 60))):
                result = build_channel_tile(geometry, window=window)
                path = Path(directory) / (str(index) + ".npz")
                save_channel_tile(path, result)
                records.append(dict(path=path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"]))
            with patch("terrain_pipeline.td_native_channel_tiles.build_channel_tile", side_effect=AssertionError("cold read must not derive")):
                first = [load_channel_tile(**record, geometry=geometry) for record in records]
                second = [load_channel_tile(**record, geometry=geometry) for record in reversed(records)]
            for tile in first:
                self.assertTrue(audit_tile_geometry(tile, geometry))
            self.assertEqual([tile["identity_sha256"] for tile in first], [tile["identity_sha256"] for tile in reversed(second)])
            with self.assertRaises(ValueError):
                load_channel_tile(**dict(records[0], expected_sha256="0" * 64))
            bad = copy.deepcopy(first[0])
            bad["arrays"] = {name: values.copy() for name, values in bad["arrays"].items()}
            bad["arrays"]["candidate_cut_m"] += .01
            bad["arrays"]["candidate_bed_m"] = bad["arrays"]["native_bilinear_bed_m"] - bad["arrays"]["candidate_cut_m"]
            bad["identity_sha256"] = identity(bad["arrays"], bad["metadata"])
            path = Path(directory) / "rehashed.npz"
            save_channel_tile(path, bad)
            loaded_bad = load_channel_tile(path, expected_sha256=file_sha256(path), expected_identity=bad["identity_sha256"], geometry=geometry)
            with self.assertRaisesRegex(ValueError, "differs"):
                audit_tile_geometry(loaded_bad, geometry)

    def test_invalid_bounds_unknown_stencil_and_nonfinite_rejected(self):
        geometry = self.geometry()
        for window in ((0, 512, 0, 10), (-1, 10, 0, 10), (0., 10, 0, 10), (0, 61, 0, 10)):
            with self.subTest(window=window), self.assertRaises(ValueError):
                build_channel_tile(geometry, window=window)
        with self.assertRaises(ValueError):
            TileRecipe(.25)
        unknown = copy.deepcopy(geometry)
        unknown["arrays"] = {name: values.copy() for name, values in unknown["arrays"].items()}
        unknown["arrays"]["node_cell_ids"] = np.array([0, 1], dtype=np.int64)
        with patch("terrain_pipeline.td_native_channel_tiles.validate_channel_geometry"), self.assertRaises(ValueError):
            build_channel_tile(unknown, window=(0, 10, 0, 10))
        tile = build_channel_tile(geometry, window=(0, 10, 0, 10))
        for name in ("native_bilinear_bed_m", "candidate_cut_m"):
            invalid = copy.deepcopy(tile)
            invalid["arrays"] = {key: values.copy() for key, values in invalid["arrays"].items()}
            invalid["arrays"][name][0, 0] = np.nan
            invalid["identity_sha256"] = identity(invalid["arrays"], invalid["metadata"])
            with self.assertRaises(ValueError):
                validate_channel_tile(invalid)


if __name__ == "__main__":
    unittest.main()
