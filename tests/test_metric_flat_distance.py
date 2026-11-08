import unittest

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.common_infra import BoundaryGrid, TerrainGrid
from terrain_pipeline.drainage import accumulate_local_discharge as accumulate_local_discharge
from terrain_pipeline.drainage import diagnostic_mesh as diagnostic_mesh
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from terrain_pipeline.surface_rivers.metric_naturalness_audit import geometry_metrics


class FlatDistanceTests(unittest.TestCase):
    def test_straight_curvature_is_exactly_zero_for_axes_and_diagonals(self):
        for direction in ((90., 0.), (90., 90.), (0., 90.), (-90., 90.)):
            points = np.arange(3)[:, None] * np.array(direction)[None, :]
            result = geometry_metrics(points, [2., 1., 0.], np.array([1, 2, -1]), curvature_method="atan2")
            self.assertEqual(result["curvature_rad_per_m"]["samples"], [0.])
        legacy = geometry_metrics([[0., 0.], [90., 90.], [180., 180.]], [2., 1., 0.], np.array([1, 2, -1]))
        self.assertGreater(legacy["curvature_rad_per_m"]["samples"][0], 0.)

    def test_turn_angle_is_translation_rotation_invariant(self):
        first = np.array([[0., 0.], [90., 0.], [90., 90.]])
        angle = np.pi / 7.
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        rotated = first @ rotation + [1e5, -1e5]
        values = [geometry_metrics(points, [2., 1., 0.], np.array([1, 2, -1]), curvature_method="atan2")["curvature_rad_per_m"]["samples"][0] for points in (first, rotated)]
        self.assertAlmostEqual(values[0], np.pi / 180.)
        self.assertAlmostEqual(values[0], values[1], places=12)

    def terrain_boundary(self, dx=90., dz=90., exits=((0, 0), (2, 4))):
        height = np.zeros((5, 5), np.float64)
        terrain = TerrainGrid(height, np.ones(height.shape, bool), 0., 0., dx, dz,
                              "diagnostic_dem_proxy", "flat-distance-fixture", "a" * 64)
        kinds = np.full(height.shape, "interior", dtype="U24")
        kinds[[0, -1], :] = "closed_wall"
        kinds[:, [0, -1]] = "closed_wall"
        for row, column in exits:
            kinds[row, column] = "open_outflow"
        return terrain, BoundaryGrid(kinds, np.zeros(height.shape, bool), "mixed",
                                      identity({"kind": kinds}, {}))

    def distance(self, graph, start):
        distance = 0.
        visited = set()
        while graph.receiver[start] >= 0:
            self.assertNotIn(start, visited)
            visited.add(start)
            distance += graph.edge_length_m[start]
            start = int(graph.receiver[start])
        return distance, start

    def test_metric_strategy_resolves_equal_hop_paths_by_meters(self):
        terrain, boundary = self.terrain_boundary()
        old = route_diagnostic(terrain, boundary)
        metric = route_diagnostic(terrain, boundary, flat_distance_strategy="metric_distance")
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import dijkstra
        mesh = diagnostic_mesh(terrain)
        adjacency = csr_matrix((mesh.edge_length_m, mesh.indices, mesh.indptr), shape=(25, 25))
        shortest = dijkstra(adjacency, indices=[0, 14])[:, 12]
        self.assertAlmostEqual(self.distance(metric, 12)[0], float(shortest.min()))
        self.assertLessEqual(self.distance(metric, 12)[0], self.distance(old, 12)[0])
        self.assertEqual(old.policy, "original_bed_irregular_plateau_bfs_v2")
        self.assertEqual(metric.policy, "original_bed_irregular_plateau_metric_distance_v2")
        self.assertNotEqual(old.identity_sha256, metric.identity_sha256)
        np.testing.assert_array_equal(terrain.elevation_m, np.zeros((5, 5)))

    def test_non_square_grid_uses_both_physical_spacings(self):
        terrain, boundary = self.terrain_boundary(dx=100., dz=1., exits=((2, 0), (4, 2)))
        metric = route_diagnostic(terrain, boundary, flat_distance_strategy="metric_distance")
        from scipy.sparse import csr_matrix
        from scipy.sparse.csgraph import dijkstra
        mesh = diagnostic_mesh(terrain)
        adjacency = csr_matrix((mesh.edge_length_m, mesh.indices, mesh.indptr), shape=(25, 25))
        shortest = dijkstra(adjacency, indices=[10, 22])[:, 12]
        self.assertAlmostEqual(self.distance(metric, 12)[0], float(shortest.min()))
        self.assertEqual(self.distance(metric, 12)[1], 22)

    def test_closed_flat_retains_lake_and_all_incoming_area(self):
        terrain, boundary = self.terrain_boundary(exits=())
        graph = route_diagnostic(terrain, boundary, flat_distance_strategy="metric_distance")
        flux = accumulate_local_discharge(graph, terrain.valid_mask * terrain.cell_area_m2)
        self.assertEqual(flux["lake_retained_m3_s"], 25. * 90. ** 2)
        self.assertEqual(flux["residual_m3_s"], 0.)
        self.assertEqual(int((graph.receiver < 0).sum()), 1)

    def test_unknown_boundary_remains_unresolved_and_conservative(self):
        terrain, boundary = self.terrain_boundary(exits=())
        kinds = boundary.kind.copy()
        kinds[0, :] = "unknown_boundary"
        boundary = BoundaryGrid(kinds, np.zeros(kinds.shape, bool), "mixed", identity({"kind": kinds}, {}))
        graph = route_diagnostic(terrain, boundary, flat_distance_strategy="metric_distance")
        flux = accumulate_local_discharge(graph, np.ones((5, 5)))
        self.assertEqual(flux["unknown_pending_m3_s"], 25.)
        self.assertEqual(flux["lake_retained_m3_s"], 0.)
        self.assertEqual(flux["residual_m3_s"], 0.)


if __name__ == "__main__":
    unittest.main()
