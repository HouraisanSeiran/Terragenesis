import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import GeometryConfig
from terrain_pipeline.channel_geometry import build_valley_incision, load_valley_incision, save_valley_incision, validate_valley_incision


def uphill_source():
    height = np.full((9, 9), 11., np.float64)
    height[3, 3], height[3, 4] = 10., 15.
    height[4, 3], height[4, 4] = 15., 9.
    return TerrainGrid(height, np.ones_like(height, bool), 0., 0., 4., 4.,
                       "observed_dem", "quadratic inside-cell hill", "a" * 64)


def build(source=None, *, config=None, owner=None, lake=None):
    source = source or uphill_source()
    shape = source.elevation_m.shape
    return build_valley_incision(
        source, np.array([3 * 9 + 3, 4 * 9 + 4], np.int64),
        np.array([1, -1], np.int64), np.array([2., 2.]), np.array([.25, .25]),
        owner_grid=np.zeros(shape, np.int64) if owner is None else owner,
        corridor_mask=np.ones(shape, bool),
        lake_mask=np.zeros(shape, bool) if lake is None else lake,
        config=config or GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0))


class ValleyIncisionTests(unittest.TestCase):
    def test_varying_base_depth_shifts_quadratic_extremum(self):
        from terrain_pipeline.channel_geometry import _profile
        terrain = uphill_source()
        points = np.array([[12., 12.], [16., 16.]])
        profile = _profile(points, np.array([1, -1], np.int64),
                           np.array([.25, 1.]), terrain, 4.)
        t = profile[1]
        source = profile[2]
        tilted = source - (.25 + .75 * t) + 1e-5 * np.sqrt(32.) * t
        self.assertTrue(np.any((t > 0.) & (t < 1.)))
        self.assertAlmostEqual(float(t[np.argmax(tilted)]), .42045, delta=.001)
        self.assertTrue(np.all(np.diff(profile[3]) < 0.))

    def test_bilinear_interior_cut_controls_footprint_radius(self):
        from terrain_pipeline.channel_geometry import _profile, _profile_max_cut_per_edge

        terrain = uphill_source()
        points = np.array([[12., 12.], [16., 16.]])
        receiver = np.array([1, -1], np.int64)
        profile = _profile(points, receiver, np.array([.25, 1.]), terrain, 4.)
        knot_maximum = float(np.max(profile[2] - profile[3]))
        continuous_maximum = float(_profile_max_cut_per_edge(
            points, receiver, profile, terrain)[0])
        self.assertGreater(continuous_maximum, knot_maximum + .01)
        self.assertAlmostEqual(continuous_maximum, 2.52275299, places=6)

    def test_original_quadratic_rises_but_final_canonical_bed_descends(self):
        bundle = build()
        self.assertTrue(validate_valley_incision(bundle))
        a = bundle["arrays"]
        self.assertEqual(a["node_xz_m"].tolist(), [[12., 12.], [16., 16.]])
        self.assertGreater(a["profile_source_m"].max(), a["profile_source_m"][0])
        self.assertTrue(np.all(np.diff(a["profile_center_bed_m"]) < 0.))
        self.assertTrue(np.all(a["cut_depth_m"] >= 0.))
        self.assertLessEqual(a["cut_depth_m"].max(), 4.)
        self.assertTrue(bundle["metadata"]["original_bed_may_rise_within_edge"])
        self.assertFalse(bundle["metadata"]["hydraulic_ready"])

    def test_source_owner_lake_and_depth_gate_reject(self):
        source = uphill_source()
        owner = np.zeros(source.elevation_m.shape, np.int64)
        owner[3, 4] = 1
        with self.assertRaisesRegex(ValueError, "divide|footprint"):
            build(owner=owner)
        lake = np.zeros(source.elevation_m.shape, bool)
        lake[4, 4] = True
        with self.assertRaisesRegex(ValueError, "wet"):
            build(lake=lake)
        with self.assertRaisesRegex(ValueError, "maximum|depth"):
            build(config=GeometryConfig(fine_spacing_m=.5, max_cut_m=1., smoothing_iterations=0))

    def test_cold_roundtrip_and_rehashed_cut_reject(self):
        bundle = build()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "incision.npz"
            save_valley_incision(path, bundle)
            loaded = load_valley_incision(path, expected_sha256=file_sha256(path),
                                          expected_identity=bundle["identity_sha256"])
        self.assertEqual(loaded["identity_sha256"], bundle["identity_sha256"])
        forged = deepcopy(bundle)
        forged["arrays"]["cut_depth_m"] = forged["arrays"]["cut_depth_m"].copy()
        forged["arrays"]["cut_depth_m"][100] += .01
        forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
        with self.assertRaisesRegex(ValueError, "incision"):
            validate_valley_incision(forged)

    def test_junction_uses_one_shared_mesh_cut_and_port(self):
        rows, cols = np.indices((13, 13))
        height = 30. - .3 * cols + .01 * rows
        terrain = TerrainGrid(height.astype(np.float64), np.ones(height.shape, bool),
                              0., 0., 4., 4., "observed_dem", "Y valley", "a" * 64)
        ids = np.array([4 * 13 + 4, 6 * 13 + 4, 5 * 13 + 6, 5 * 13 + 8], np.int64)
        result = build_valley_incision(
            terrain, ids, np.array([2, 2, 3, -1], np.int64),
            np.full(4, 2.), np.full(4, .25),
            owner_grid=np.zeros(height.shape, np.int64), corridor_mask=np.ones(height.shape, bool),
            lake_mask=np.zeros(height.shape, bool),
            config=GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0))
        a = result["arrays"]
        self.assertEqual(len(a["canonical_port_edge_node_indices"]), 3)
        self.assertEqual(np.count_nonzero(np.all(a["vertices_xz_m"] == a["node_xz_m"][2], axis=1)), 1)
        faces = a["triangles"]
        xy = a["vertices_xz_m"][faces]
        area = abs((xy[:, 1, 0] - xy[:, 0, 0]) * (xy[:, 2, 1] - xy[:, 0, 1])
                   - (xy[:, 2, 0] - xy[:, 0, 0]) * (xy[:, 1, 1] - xy[:, 0, 1])) / 2.
        self.assertAlmostEqual(float(np.sum(area * a["cut_depth_m"][faces].mean(axis=1))),
                               result["metadata"]["cut_volume_m3"], places=7)


if __name__ == "__main__":
    unittest.main()
