import unittest
from types import SimpleNamespace

import numpy as np

from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import build_design_geometry, merge_design_bundles, design_cut_bounds, solve_design_bed, source_interpolation_padding, _mesh_volume_chunked
from terrain_pipeline.channel_geometry import _mesh_height, _sparse_mesh, _sparse_cells


class ContinuousDesignBedTests(unittest.TestCase):
    def test_floor_clip_tolerance_does_not_extrapolate_triangle_edges(self):
        from terrain_pipeline.channel_geometry import _clip_floor_polygon
        polygon = np.array([[1.1e-10, 0.], [.9e-10, 1.], [.9e-10, 0.]])
        clipped = _clip_floor_polygon(polygon, np.array([1., 0.]), 0.)
        self.assertGreaterEqual(len(clipped), 3)
        self.assertTrue(np.all(clipped >= polygon.min(axis=0)))
        self.assertTrue(np.all(clipped <= polygon.max(axis=0)))

    def test_four_arm_junction_floor_retains_every_arm(self):
        from terrain_pipeline.channel_geometry import continuous_center_floor_constraints, _edge_continuous_floor_constraints
        terrain = TerrainGrid(np.full((2, 2), 101.), np.ones((2, 2), bool),
                              0., 0., 30., 30., "observed_dem", "four-arm", "f" * 64)
        points = np.array([[15., 15.], [5., 15.], [15., 5.], [15., 25.], [25., 15.]])
        receiver = np.array([4, 0, 0, 0, -1])
        width = np.full(5, 4.)
        zz, xx = np.indices((30, 30))
        cells = np.column_stack((xx.ravel(), zz.ravel()))
        vertices, triangles = _sparse_mesh(cells, terrain, 1., 10000)
        source, maximum = np.full(len(vertices), 101.), np.full(len(vertices), 4.)
        ids, weights, rhs = continuous_center_floor_constraints(points, receiver, width, cells, vertices,
                                                                triangles, source, terrain, 1., maximum)
        counts = [len(_edge_continuous_floor_constraints(node, points, receiver, width, cells, vertices,
                   triangles, source, terrain, 1., maximum, junction=0)[2]) for node in range(4)]
        self.assertTrue(all(count > 0 for count in counts))
        self.assertEqual(len(rhs), sum(counts))
        np.testing.assert_allclose(np.sum(weights*np.full(len(vertices), 100.)[ids], axis=1), 0., atol=1e-10)

    def test_explicit_support_radius_preserves_default_and_rejects_invalid_edges(self):
        terrain = TerrainGrid(np.full((2, 2), 10.0), np.ones((2, 2), bool),
                              0.0, 0.0, 30.0, 30.0, "observed_dem", "radius", "e" * 64)
        points = np.array([[8.0, 15.0], [22.0, 15.0]])
        receiver, width = np.array([1, -1]), np.full(2, 4.0)
        profile = (np.array([0, 2]), np.array([0.0, 1.0]),
                   np.full(2, 10.0), np.array([9.5, 9.4999]))
        options = SimpleNamespace(fine_spacing_m=1.0, max_vertices=10_000)
        default = _sparse_cells(points, receiver, width, profile, options, terrain)
        explicit = _sparse_cells(points, receiver, width, profile, options, terrain,
                                 support_radius_m=np.array([2.0 + 2.0 * 0.5001]))
        np.testing.assert_array_equal(default, explicit)
        for radius in (np.array([]), np.array([1.0, 2.0]), np.array([np.nan]),
                       np.array([np.inf]), np.array([-1.0]), np.array([0.0]), 2.0):
            with self.subTest(radius=radius):
                with self.assertRaisesRegex(ValueError, "support radius"):
                    _sparse_cells(points, receiver, width, profile, options, terrain,
                                  support_radius_m=radius)

    def test_chunked_material_volume_matches_full_mesh_across_batch_boundary(self):
        from terrain_pipeline.channel_geometry import _mesh_volume

        vertices = np.array([[0.0, 0.0], [3.0, 0.0], [0.0, 2.0]])
        triangles = np.tile(np.array([[0, 1, 2]]), (200_003, 1))
        cut = np.array([0.125, 0.375, 0.8125])
        for datum in (0.0, 0.25):
            expected = _mesh_volume(vertices, triangles, cut, datum=datum)
            actual = _mesh_volume_chunked(vertices, triangles, cut, datum=datum)
            np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=0.0)

    def transverse_fixture(self, points, receiver, width=4.0):
        terrain = TerrainGrid(np.full((2, 2), 10.0), np.ones((2, 2), bool),
                              0.0, 0.0, 30.0, 30.0, "observed_dem", "shape", "c" * 64)
        edges = np.flatnonzero(receiver >= 0)
        beds = 8.0 - points[:, 0] * 0.001
        profile = (np.arange(0, 2 * len(edges) + 1, 2),
                   np.tile([0.0, 1.0], len(edges)), np.full(2 * len(edges), 10.0),
                   np.column_stack((beds[edges], beds[receiver[edges]])).ravel())
        result = build_design_geometry(points, receiver, np.full(len(points), width),
                                       np.full(len(points), 0.5), profile, terrain,
                                       1.0, 4.0, 1e-5)
        return terrain, result

    def test_actual_deep_profile_has_full_bottom_instead_of_center_slot(self):
        points = np.array([[8.0, 15.0], [22.0, 15.0]])
        terrain, result = self.transverse_fixture(points, np.array([1, -1]))
        cells, vertices, triangles, source, _, cut, closure = result[:7]
        lookup = {tuple(cell): i for i, cell in enumerate(cells)}
        bed = source - cut
        for x in (10.0, 15.0, 20.0):
            center = _mesh_height(np.array([x, 15.0]), lookup[(int(x), 15)],
                                  vertices, triangles, bed)
            for z in np.linspace(13.0, 17.0, 17):
                actual = _mesh_height(np.array([x, z]), lookup[(int(x), int(z))],
                                      vertices, triangles, bed)
                self.assertLessEqual(actual, center + abs(z - 15.0) * 0.02 + 1e-8)
        self.assertTrue(closure["transverse_bed_coupling"])
        self.assertLessEqual(closure["maximum_transverse_residual_m"], 1e-8)
        self.assertTrue(np.all(cut[result[-1]] == 0.0))
        self.assertLessEqual(float(cut.max()), 4.0)
        self.assertTrue(np.all(terrain.elevation_m == 10.0))

    def test_small_bend_and_shared_confluence_preserve_physical_limits(self):
        examples = (
            (np.array([[8.0, 14.0], [15.0, 15.0], [22.0, 15.0]]),
             np.array([1, 2, -1])),
            (np.array([[8.0, 12.0], [8.0, 18.0], [15.0, 15.0], [22.0, 15.0]]),
             np.array([2, 2, 3, -1])),
        )
        for points, receiver in examples:
            with self.subTest(receiver=receiver):
                _, result = self.transverse_fixture(points, receiver)
                self.assertLessEqual(float(result[5].max()), 4.0)
                self.assertLessEqual(result[6]["maximum_gradient_residual_m_per_m"], 1e-8)
                self.assertLessEqual(result[6]["maximum_transverse_residual_m"], 1e-8)

    def test_outer_bend_wedge_and_source_terminal_caps_follow_actual_node_bed(self):
        examples = (
            (np.array([[8.0, 12.0], [15.0, 15.0], [22.0, 15.0]]),
             np.array([1, 2, -1]), 6.0, ((1, np.array([14.5, 17.5])),)),
            (np.array([[8.0, 15.0], [22.0, 15.0]]), np.array([1, -1]),
             4.0, ((0, np.array([7.0, 16.0])), (1, np.array([23.0, 16.0])))),
        )
        for points, receiver, width, probes in examples:
            terrain, result = self.transverse_fixture(points, receiver, width)
            cells, vertices, triangles, source, _, cut = result[:6]
            lookup = {tuple(cell): i for i, cell in enumerate(cells)}
            bed = source - cut
            for node, probe in probes:
                center = _mesh_height(points[node], lookup[tuple(points[node].astype(int))],
                                      vertices, triangles, bed)
                actual = _mesh_height(probe, lookup[tuple(probe.astype(int))],
                                      vertices, triangles, bed)
                radius = float(np.linalg.norm(probe - points[node]))
                self.assertLessEqual(actual, center + radius * 0.02 + 1e-8)
            self.assertTrue(np.all(cut[result[-1]] == 0.0))
            self.assertLessEqual(float(cut.max()), 4.0)
            self.assertGreater(result[6]["transverse_node_cap_constraints"], 0)

    def test_wide_bottom_rejects_real_four_meter_budget_conflict(self):
        terrain = TerrainGrid(np.array([[10.0, 10.0], [70.0, 70.0]]),
                              np.ones((2, 2), bool), 0.0, 0.0, 30.0, 30.0,
                              "observed_dem", "steep", "d" * 64)
        points = np.array([[8.0, 15.0], [22.0, 15.0]])
        profile = (np.array([0, 2]), np.array([0.0, 1.0]),
                   np.array([40.0, 40.0]), np.array([38.0, 37.999]))
        with self.assertRaisesRegex(ValueError, "cut bounds or is infeasible"):
            build_design_geometry(points, np.array([1, -1]), np.full(2, 4.0),
                                  np.full(2, 0.5), profile, terrain, 1.0, 4.0, 1e-5)

    def test_mixed_global_keeps_legacy_cut_and_new_design_profile(self):
        terrain, cells, vertices, triangles = self.fixture(
            np.array([[10.0, 9.0], [10.0, 9.0]])
        )
        source = 10.0 - vertices[:, 0] / 4.0
        bundles = []
        for z, new in ((1.0, False), (3.0, True)):
            points = np.array([[0.5, z], [3.5, z]])
            a = dict(
                source_node_cell_ids=np.array([0, 1]),
                receiver=np.array([1, -1]),
                node_xz_m=points,
                width_m=np.ones(2),
                base_depth_m=np.ones(2),
                sparse_cell_xy=cells,
                vertices_xz_m=vertices,
                triangles=triangles,
                cut_depth_m=np.full(len(vertices), 1.0 if new else 4.0),
                profile_offsets=np.array([0, 2]),
                profile_t=np.array([0.0, 1.0]),
                profile_source_m=10.0 - points[:, 0] / 4.0,
                profile_center_bed_m=9.0 - points[:, 0] / 4.0,
            )
            if new:
                a.update(
                    design_minimum_cut_m=np.full(len(vertices), 0.25),
                    source_interpolation_padding_m=np.zeros(len(vertices)),
                )
            bundles.append(dict(arrays=a))
        from terrain_pipeline.surface_rivers.metric_td_generated_rivers import (
            GeneratedRiverConfig,
        )

        # The legacy field already cuts 4m everywhere on a 0.25m/m incline:
        # a 0.02m/m source cap would require additional, forbidden incision.
        with self.assertRaisesRegex(ValueError, "cut bounds or is infeasible"):
            merge_design_bundles(terrain, bundles, GeneratedRiverConfig(), np.array([0.25, 0.25]))
        config = GeneratedRiverConfig(transverse_bottom_slope_m_per_m=0.3)
        result = merge_design_bundles(terrain, bundles, config, np.array([0.25, 0.25]))
        a = result["arrays"]
        self.assertTrue(np.all(a["cut_depth_m"] == 4.0))
        self.assertTrue(
            np.array_equal(a["design_constraint_node_mask"], [False, False, True, True])
        )
        self.assertTrue(np.array_equal(a["profile_offsets"], [0, 2, 4]))
        self.assertAlmostEqual(result["metadata"]["cut_volume_m3"], 64.0)
        self.assertTrue(np.all(a["design_maximum_cut_m"] == 4.0))
        bundles[1]["arrays"]["source_interpolation_padding_m"] = np.full(
            len(vertices), 0.001
        )
        with self.assertRaisesRegex(ValueError, "ordered nonnegative cut bounds"):
            merge_design_bundles(terrain, bundles, config, np.array([0.25, 0.25]))

    def test_expanded_banks_reconnect_to_known_source(self):
        terrain = TerrainGrid(
            np.full((2, 2), 10.0),
            np.ones((2, 2), bool),
            0.0,
            0.0,
            40.0,
            40.0,
            "observed_dem",
            "bank",
            "b" * 64,
        )
        points = np.array([[16.0, 20.0], [24.0, 20.0]])
        profile = (
            np.array([0, 2]),
            np.array([0.0, 1.0]),
            np.array([10.0, 10.0]),
            np.array([9.5, 9.4999]),
        )
        result = build_design_geometry(
            points,
            np.array([1, -1]),
            np.array([1.0, 1.0]),
            np.array([0.5, 0.5]),
            profile,
            terrain,
            1.0,
            4.0,
            1e-5,
        )
        cut, boundary = result[5], result[-1]
        self.assertGreater(len(boundary), 0)
        self.assertTrue(np.all(cut[boundary] == 0.0))

    def fixture(self, heights=None, spacing=1.0):
        terrain = TerrainGrid(
            np.full((2, 2), 10.0) if heights is None else heights,
            np.ones((2, 2), bool),
            0.0,
            0.0,
            4.0,
            4.0,
            "observed_dem",
            "design",
            "a" * 64,
        )
        count = int(4.0 / spacing)
        cells = np.array([(x, z) for z in range(count) for x in range(count)], np.int64)
        vertices, triangles = _sparse_mesh(cells, terrain, spacing, 10000)
        return terrain, cells, vertices, triangles

    def test_fan4_padding_bounds_bilinear_interpolation_error(self):
        terrain, cells, vertices, triangles = self.fixture(
            np.array([[10.0, 10.0], [10.0, 14.0]]), 0.5
        )
        source = 10.0 + vertices[:, 0] * vertices[:, 1] / 4.0
        padding = source_interpolation_padding(cells, vertices, triangles, terrain, 0.5)
        self.assertAlmostEqual(float(padding.max()), 0.25 * 0.5**2 / 16.0)
        for face, ids in enumerate(triangles):
            for u in np.linspace(0.0, 1.0, 9):
                for v in np.linspace(0.0, 1.0 - u, 9):
                    weights = np.array([1.0 - u - v, u, v])
                    point = weights @ vertices[ids]
                    actual = 10.0 + point[0] * point[1] / 4.0
                    error = abs(actual - weights @ source[ids])
                    self.assertLessEqual(error, float(padding[ids].max()) + 1e-12)

    def test_conservative_bottom_preserves_depth_between_vertices(self):
        terrain, cells, vertices, triangles = self.fixture(
            np.array([[10.0, 10.0], [10.0, 14.0]]), 0.5
        )
        points = np.array([[0.5, 2.0], [3.5, 2.0]])
        lower, _, _ = design_cut_bounds(
            points,
            np.array([1, -1]),
            np.array([0.7, 0.7]),
            np.array([0.3, 0.5]),
            cells,
            vertices,
            triangles,
            terrain,
            0.5,
            4.0,
        )
        source = 10.0 + vertices[:, 0] * vertices[:, 1] / 4.0
        lookup = {tuple(cell): index for index, cell in enumerate(cells)}
        for t in np.linspace(0.0, 1.0, 21):
            for cross in np.linspace(-0.35, 0.35, 11):
                point = points[0] + t * (points[1] - points[0]) + np.array([0.0, cross])
                key = tuple(np.floor(point / 0.5).astype(int))
                bed = _mesh_height(
                    point, lookup[key], vertices, triangles, source - lower
                )
                raw = 10.0 + point[0] * point[1] / 4.0
                self.assertGreaterEqual(raw - bed, 0.3 + 0.2 * t - 1e-10)

    def test_profile_internal_knot_is_preserved_by_physical_bed(self):
        terrain, cells, vertices, triangles = self.fixture()
        points = np.array([[0.5, 2.0], [3.5, 2.0]])
        receiver = np.array([1, -1])
        source = np.full(len(vertices), 10.0)
        profile = (
            np.array([0, 3]),
            np.array([0.0, 0.3, 1.0]),
            np.array([10.0, 10.0, 10.0]),
            np.array([9.5, 8.5, 8.49]),
        )
        cut, metadata = solve_design_bed(
            points,
            receiver,
            cells,
            vertices,
            triangles,
            source,
            np.full(len(vertices), 0.25),
            np.full(len(vertices), 4.0),
            terrain,
            1.0,
            profile,
            1e-5,
        )
        lookup = {tuple(cell): index for index, cell in enumerate(cells)}
        for t in np.linspace(0.0, 1.0, 101):
            point = points[0] + t * (points[1] - points[0])
            key = tuple(np.floor(point).astype(int))
            bed = _mesh_height(point, lookup[key], vertices, triangles, source - cut)
            target = np.interp(t, profile[1], profile[3])
            self.assertLessEqual(bed, target + 1e-8)
        self.assertTrue(metadata["profile_mesh_breakpoint_union"])
        self.assertLess(float(cut.max()), 4.0)


if __name__ == "__main__":
    unittest.main()
