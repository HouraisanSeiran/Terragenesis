import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.channel_geometry import GeometryConfig
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import _close_bed, build_monotone_union, load_monotone_union, save_monotone_union, validate_monotone_union
from terrain_pipeline.channel_geometry import _sparse_mesh, _sparse_slope
from tests.test_metric_valley_incision import uphill_source
from tests.test_metric_valley_centerline import fixture
from terrain_pipeline.channel_geometry import build_valley_centerline


class MonotoneUnionTests(unittest.TestCase):
    def test_shaped_centerline_generates_cold_loadable_monotone_bed(self):
        terrain, ids, receiver, options = fixture()
        width, depth = np.full(4, 2.), np.full(4, .25)
        centerline = build_valley_centerline(terrain, ids, receiver, width, depth, **options)
        product = build_monotone_union(terrain, ids, receiver, width, depth,
                                      centerline=centerline, **options)
        np.testing.assert_array_equal(product["arrays"]["node_xz_m"],
                                      centerline["arrays"]["node_xz_m"])
        self.assertGreater(centerline["metadata"]["moved_nodes"], 0)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shaped.npz"
            save_monotone_union(path, product)
            with patch('terrain_pipeline.channel_geometry._i34_linprog',
                       side_effect=AssertionError("cold validator ran optimizer")):
                loaded = load_monotone_union(path, expected_sha256=file_sha256(path),
                                             expected_identity=product["identity_sha256"])
        self.assertTrue(validate_monotone_union(loaded))
        forged = deepcopy(product)
        points = forged["arrays"]["node_xz_m"].copy()
        points[0, 0] += .1
        forged["arrays"]["node_xz_m"] = points
        forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
        with self.assertRaisesRegex(ValueError, "anchor moved"):
            validate_monotone_union(forged)

    def test_mesh_centerline_closure_repairs_uphill_without_fill(self):
        rows, cols = np.indices((3, 3))
        height = (10. - .1 * cols).astype(np.float64)
        terrain = TerrainGrid(height, np.ones(height.shape, bool), 0., 0., 1., 1.,
                              "observed_dem", "linear", "a" * 64)
        cells = np.array([[0, 0], [1, 0]], np.int64)
        vertices, triangles = _sparse_mesh(cells, terrain, 1., 100)
        source = 10. - .1 * vertices[:, 0]
        cut = np.zeros(len(vertices))
        cut[np.flatnonzero(np.all(vertices == [.5, .5], axis=1))[0]] = 1.
        points = np.array([[0., .5], [2., .5]])
        receiver = np.array([1, -1], np.int64)
        with self.assertRaisesRegex(ValueError, "uphill"):
            _sparse_slope(points, receiver, cells, vertices, triangles, source-cut, 1., terrain)
        closed, ledger = _close_bed(points, receiver, cells, vertices, triangles,
                                    source, cut, terrain, 1., 4.)
        self.assertTrue(np.all(closed >= cut))
        self.assertGreater(ledger["extra_cut_vertices"], 0)
        _sparse_slope(points, receiver, cells, vertices, triangles, source-closed, 1., terrain)

    def test_product_cold_roundtrip_and_cut_tamper(self):
        terrain = uphill_source()
        shape = terrain.elevation_m.shape
        product = build_monotone_union(
            terrain, np.array([30, 40], np.int64), np.array([1, -1], np.int64),
            np.array([2., 2.]), np.array([.25, .25]),
            owner_grid=np.zeros(shape, np.int64), corridor_mask=np.ones(shape, bool),
            lake_mask=np.zeros(shape, bool), source_plan_identity_sha256="b" * 64,
            config=GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0))
        self.assertTrue(validate_monotone_union(product))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "monotone.npz"
            save_monotone_union(path, product)
            with (patch('terrain_pipeline.channel_geometry._i34_linprog',
                        side_effect=AssertionError("cold validator ran optimizer")),
                  patch('terrain_pipeline.channel_geometry.build_monotone_union',
                        side_effect=AssertionError("cold validator ran builder"))):
                loaded = load_monotone_union(path, expected_sha256=file_sha256(path),
                                             expected_identity=product["identity_sha256"])
        self.assertEqual(loaded["identity_sha256"], product["identity_sha256"])
        forged = deepcopy(product)
        forged["arrays"]["cut_depth_m"] = forged["arrays"]["cut_depth_m"].copy()
        forged["arrays"]["cut_depth_m"][20] += .01
        forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
        with self.assertRaisesRegex(ValueError, "field mismatch"):
            validate_monotone_union(forged)


if __name__ == "__main__":
    unittest.main()
