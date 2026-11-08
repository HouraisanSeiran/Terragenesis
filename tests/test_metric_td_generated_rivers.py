import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.common_infra import TerrainGrid, BoundaryGrid
from terrain_pipeline.surface_rivers.metric_td_generated_rivers import (
    GeneratedRiverConfig,
    component_geometry,
    component_centerline,
    load_component_geometry,
    save_component_geometry,
    selected_components,
    shared_node_depths,
    spill_candidate,
)


class GeneratedRiverTests(unittest.TestCase):
    def test_local_route_stage_receives_physical_config_and_unknown_stays_explicit(self):
        terrain = self.terrain()
        config = GeneratedRiverConfig(fine_spacing_m=2., max_cut_m=3.,
                                      transverse_bottom_slope_m_per_m=.03)
        def unknown(terrain, points, receiver, width, depth, profile, ids, **kwargs):
            self.assertEqual(kwargs["spacing"], 2.)
            self.assertEqual(kwargs["max_cut"], 3.)
            self.assertEqual(kwargs["bottom_slope"], .03)
            self.assertEqual(kwargs["minimum_slope"], 1e-5)
            return points, profile, dict(status="unknown_needs_full_bed", attempted_candidates=0)
        with patch("terrain_pipeline.surface_rivers.metric_td_generated_rivers.repair_local_conflicts", side_effect=unknown):
            _, _, policy = component_centerline(terrain, np.array([58, 59, 60]),
                np.array([1, 2, -1]), np.full(3, 6.), np.full(3, .25), config)
        self.assertEqual(policy["local_original_row_bed_repair"]["status"], "unknown_needs_full_bed")
        self.assertEqual(policy["budget_hotspot_repair"]["final_counts"], [0, 0, 0])
        self.assertIn("necessary_repair_stage_final_maxima", policy["budget_hotspot_repair"])

    def test_unrepaired_original_row_conflict_rejects_before_bed_generation(self):
        def conflict(terrain, points, receiver, width, depth, profile, ids, **kwargs):
            return points, profile, dict(status="local_conflicts_remain", attempted_candidates=32)
        with patch("terrain_pipeline.surface_rivers.metric_td_generated_rivers.repair_local_conflicts", side_effect=conflict):
            with self.assertRaisesRegex(ValueError, "original-row local bed conflicts"):
                component_centerline(self.terrain(), np.array([58, 59, 60]),
                    np.array([1, 2, -1]), np.full(3, 6.), np.full(3, .25), GeneratedRiverConfig())

    def test_world_ulp_triangle_support_does_not_admit_real_exterior(self):
        from terrain_pipeline.channel_geometry import _barycentric

        vertices = np.array(
            [
                [-480654.0, -1955731.0],
                [-480653.0, -1955731.0],
                [-480653.0, -1955730.0],
                [-480654.0, -1955730.0],
                [-480653.5, -1955730.5],
            ]
        )
        triangles = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
        ids, weights = _barycentric(
            np.array([-480654.00000000064, -1955730.3]), 0, vertices, triangles
        )
        self.assertAlmostEqual(float(weights.sum()), 1.0)
        with self.assertRaisesRegex(ValueError, "outside sparse triangles"):
            _barycentric(np.array([-480654.00001, -1955730.3]), 0, vertices, triangles)

    def terrain(self):
        z, x = np.indices((11, 11))
        return TerrainGrid(
            (100.0 - x * 0.2 + ((z - 5) * 0.01) ** 2).astype(np.float64),
            np.ones((11, 11), bool),
            0.0,
            0.0,
            30.0,
            30.0,
            "observed_dem",
            "fixture",
            "a" * 64,
        )

    def test_component_partition_covers_confluences_and_all_edges(self):
        source = np.array([0, 1, 2, 6, 8])
        target = np.array([2, 2, 3, 7, 9])
        result = selected_components(source, target)
        self.assertEqual([part.tolist() for part in result], [[0, 1, 2], [3], [4]])
        np.testing.assert_array_equal(np.sort(np.concatenate(result)), np.arange(5))

    def test_shared_node_depths_propagate_at_confluence(self):
        terrain = self.terrain()
        ids = np.array([58, 59, 60], np.int64)
        receiver = np.array([1, 2, -1], np.int64)
        _, depth = shared_node_depths(
            terrain, ids, receiver, np.array([1.0, 0.25, 0.25]), 4.0
        )
        self.assertGreater(depth[1], 0.79)
        self.assertGreater(depth[2], 0.59)

    def test_actual_component_mesh_cold_roundtrip(self):
        terrain = self.terrain()
        ids = np.array([58, 59, 60], np.int64)
        receiver = np.array([1, 2, -1], np.int64)
        product = component_geometry(
            terrain,
            ids,
            receiver,
            np.full(3, 6.0),
            np.full(3, 0.25),
            GeneratedRiverConfig(),
        )
        self.assertGreater(product["metadata"]["cut_volume_m3"], 0.0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bed.npz"
            save_component_geometry(path, product)
            loaded = load_component_geometry(
                path,
                expected_sha256=file_sha256(path),
                expected_identity=product["identity_sha256"],
            )
            np.testing.assert_array_equal(
                loaded["arrays"]["bed_elevation_m"],
                product["arrays"]["bed_elevation_m"],
            )

    def test_spill_work_preserves_unknown_boundary_and_deep_pit(self):
        terrain = self.terrain()
        height = terrain.elevation_m.copy()
        height[5, 5] -= 10.0
        terrain = TerrainGrid(
            height,
            terrain.valid_mask,
            0.0,
            0.0,
            30.0,
            30.0,
            "observed_dem",
            "pit",
            "a" * 64,
        )
        kinds = np.full(height.shape, "interior", dtype="U24")
        kinds[[0, -1], :] = "unknown_boundary"
        kinds[:, [0, -1]] = "unknown_boundary"
        graph, work, metadata = spill_candidate(
            terrain,
            BoundaryGrid(kinds, np.zeros(height.shape, bool), "unknown", "b" * 64),
            4.0,
        )
        self.assertEqual(graph.outlet_kind[60], "lake_preserved")
        self.assertNotIn("open_outflow", graph.outlet_kind)
        self.assertLessEqual(float((work - height).max()), 4.0)
        self.assertTrue(metadata["work_surface_only"])

    def test_quadratic_bowl_uses_continuous_envelope_within_four_m(self):
        height = np.full((5, 5), 20.0, np.float64)
        height[1, 1] = height[2, 2] = 10.0
        height[1, 2] = height[2, 1] = 8.0
        terrain = TerrainGrid(
            height,
            np.ones(height.shape, bool),
            0.0,
            0.0,
            30.0,
            30.0,
            "observed_dem",
            "bowl",
            "a" * 64,
        )
        ids = np.array([6, 12], np.int64)
        receiver = np.array([1, -1], np.int64)
        _, depth = shared_node_depths(terrain, ids, receiver, np.full(2, 0.25), 4.0)
        self.assertLess(depth[-1], 1.251)
        self.assertGreater(depth[-1], 1.25)
        product = component_geometry(
            terrain,
            ids,
            receiver,
            np.full(2, 6.0),
            np.full(2, 0.25),
            GeneratedRiverConfig(),
        )
        self.assertLessEqual(product["metadata"]["maximum_cut_m"], 4.0)

    def test_boundary_route_keeps_collinear_clipped_cross_section(self):
        rows, cols = np.indices((11, 11))
        terrain = TerrainGrid(
            (100.0 - rows * 0.2).astype(np.float64),
            np.ones((11, 11), bool),
            0.0,
            0.0,
            30.0,
            30.0,
            "observed_dem",
            "edge",
            "a" * 64,
        )
        ids = np.array([54, 65, 76], np.int64)
        receiver = np.array([1, 2, -1], np.int64)
        product = component_geometry(
            terrain,
            ids,
            receiver,
            np.full(3, 6.0),
            np.full(3, 0.25),
            GeneratedRiverConfig(),
        )
        a = product["arrays"]
        self.assertGreater(product["metadata"]["clipped_port_points"], 0)
        np.testing.assert_allclose(
            a["port_profile_xz_m"][:, :, 1],
            a["port_xz_m"][:, 1, None] * np.ones((2, 4)),
        )
        self.assertTrue(np.all(a["port_profile_xz_m"][:, :, 0] <= 300.0))

    def test_near_coincident_triangle_breaks_at_large_world_origin(self):
        from terrain_pipeline.channel_geometry import _sparse_mesh, _sparse_slope
        from terrain_pipeline.channel_geometry import _close_bed, _line_constraints

        terrain = TerrainGrid(
            np.array([[10.0, 9.0], [10.0, 9.0]], np.float64),
            np.ones((2, 2), bool),
            1_000_000.0,
            1_000_000.0,
            10.0,
            10.0,
            "observed_dem",
            "origin",
            "a" * 64,
        )
        cells = np.array([[x, z] for z in range(10) for x in range(10)], np.int64)
        vertices, triangles = _sparse_mesh(cells, terrain, 1.0, 1000)
        points = np.array(
            [[1_000_000.1, 1_000_000.1], [1_000_009.9, 1_000_009.9000000001]]
        )
        receiver = np.array([1, -1], np.int64)
        source = 10.0 - 0.1 * (vertices[:, 0] - 1_000_000.0)
        cut, _ = _close_bed(
            points,
            receiver,
            cells,
            vertices,
            triangles,
            source,
            np.zeros(len(source)),
            terrain,
            1.0,
            4.0,
            minimum_slope_m_per_m=1e-5,
        )
        _sparse_slope(
            points, receiver, cells, vertices, triangles, source - cut, 1.0, terrain
        )
        segments = _line_constraints(
            points, receiver, cells, vertices, triangles, terrain, 1.0
        )
        self.assertGreater(
            min(
                dt * np.linalg.norm(points[1] - points[0])
                for _, _, dt, _, _ in segments
            ),
            1e-9,
        )

    def test_physical_gradient_is_enforced_on_short_triangle_span(self):
        from terrain_pipeline.channel_geometry import _close_bed
        from terrain_pipeline.channel_geometry import _mesh_directional_weights, _sparse_mesh

        terrain = TerrainGrid(
            np.full((2, 2), 1000.0, np.float64),
            np.ones((2, 2), bool),
            1_000_000.0,
            1_000_000.0,
            1.0,
            1.0,
            "observed_dem",
            "short-span",
            "a" * 64,
        )
        cells = np.array([[0, 0]], np.int64)
        vertices, triangles = _sparse_mesh(cells, terrain, 1.0, 100)
        points = np.array(
            [[1_000_000.1, 1_000_000.2], [1_000_000.1000002, 1_000_000.2000002]]
        )
        source = np.full(len(vertices), 1000.0)
        cut, _ = _close_bed(
            points,
            np.array([1, -1], np.int64),
            cells,
            vertices,
            triangles,
            source,
            np.zeros(len(vertices)),
            terrain,
            1.0,
            4.0,
            minimum_slope_m_per_m=1e-5,
        )
        direction = points[1] - points[0]
        ids, weights = _mesh_directional_weights(
            points.mean(axis=0),
            0,
            vertices,
            triangles,
            direction / np.linalg.norm(direction),
        )
        bed = source - cut
        gradient = weights[1:] @ (bed[ids[1:]] - bed[ids[0]])
        self.assertGreaterEqual(-gradient, 1e-5 - 1e-8)
        self.assertGreater(float(cut.max()), 1e-6)


if __name__ == "__main__":
    unittest.main()
