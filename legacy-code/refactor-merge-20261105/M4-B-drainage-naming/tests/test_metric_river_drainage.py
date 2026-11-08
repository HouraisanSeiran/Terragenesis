import unittest

import numpy as np

from terrain_pipeline.common_infra import BoundaryGrid, TerrainGrid
from terrain_pipeline.drainage import accumulate_local_discharge as accumulate_local_discharge
from terrain_pipeline.drainage import diagnostic_mesh as diagnostic_mesh
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic


def fixture(height, kinds=None, *, dx=3., dz=4.):
    values = np.asarray(height, dtype=np.float64)
    valid = np.isfinite(values)
    terrain = TerrainGrid(values, valid, 0., 0., dx, dz, "diagnostic_dem_proxy", "fixture", "a" * 64)
    if kinds is None:
        kinds = np.full(values.shape, "interior", dtype="U24")
        kinds[[0, -1], :] = "closed_wall"
        kinds[:, [0, -1]] = "closed_wall"
    kinds = np.asarray(kinds, dtype="U24").copy()
    kinds[~valid] = "unknown_boundary"
    boundary = BoundaryGrid(kinds, np.zeros(values.shape, bool), "fixture", "b" * 64)
    return terrain, boundary


class DiagnosticDrainageTests(unittest.TestCase):
    def test_flat_routes_to_explicit_outlet_and_conserves_discharge(self):
        terrain, boundary = fixture([[2., 2., 2.]], [["closed_wall", "closed_wall", "open_outflow"]])
        graph = route_diagnostic(terrain, boundary)
        np.testing.assert_array_equal(graph.receiver, [1, 2, -1])
        result = accumulate_local_discharge(graph, np.array([[1., 2., 3.]]))
        np.testing.assert_array_equal(result["routed_q_m3_s"], [[1., 3., 6.]])
        self.assertEqual(result["open_outflow_m3_s"], 6.)
        self.assertEqual(result["residual_m3_s"], 0.)

    def test_steepest_metric_slope_and_y_confluence(self):
        terrain, boundary = fixture([[5., 9., 5.], [9., 2., 9.], [9., 0., 9.]], dx=3., dz=4.)
        kinds = boundary.kind.copy()
        kinds[2, 1] = "open_outflow"
        boundary = BoundaryGrid(kinds, np.zeros(kinds.shape, bool), "fixture", "b" * 64)
        graph = route_diagnostic(terrain, boundary)
        self.assertEqual(graph.receiver[0], 4)
        self.assertGreaterEqual(np.count_nonzero(graph.receiver == 4), 2)
        self.assertEqual(graph.receiver[4], 7)
        mesh = diagnostic_mesh(terrain)
        for cell in np.flatnonzero(graph.receiver >= 0):
            target = graph.receiver[cell]
            length = np.hypot(mesh.node_x_m[cell] - mesh.node_x_m[target],
                              mesh.node_z_m[cell] - mesh.node_z_m[target])
            self.assertAlmostEqual(graph.edge_length_m[cell], length)
            self.assertAlmostEqual(graph.edge_slope[cell],
                                   (terrain.elevation_m.flat[cell] - terrain.elevation_m.flat[target]) / length)
            neighbors = mesh.indices[mesh.indptr[cell]:mesh.indptr[cell + 1]]
            lengths = mesh.edge_length_m[mesh.indptr[cell]:mesh.indptr[cell + 1]]
            slopes = (terrain.elevation_m.flat[cell] - terrain.elevation_m.ravel()[neighbors]) / lengths
            self.assertAlmostEqual(graph.edge_slope[cell], max(0., float(slopes.max())))
        result = accumulate_local_discharge(graph, np.ones((3, 3)))
        self.assertEqual(result["open_outflow_m3_s"], 9.)
        self.assertEqual(result["input_total_m3_s"], 9.)

    def test_multiple_explicit_outlets_and_prescribed_candidate(self):
        terrain, _ = fixture([[2., 1., 2., 1.]])
        kinds = np.array([["closed_wall", "open_outflow", "closed_wall", "prescribed_stage"]])
        boundary = BoundaryGrid(kinds, np.zeros((1, 4), bool), "fixture", "b" * 64,
                                stage_m=np.array([[0., 0., 0., 1.]]))
        graph = route_diagnostic(terrain, boundary)
        result = accumulate_local_discharge(graph, np.ones((1, 4)))
        self.assertEqual(result["open_outflow_m3_s"], 2.)
        self.assertEqual(result["prescribed_boundary_candidate_m3_s"], 2.)
        self.assertEqual(result["residual_m3_s"], 0.)

    def test_closed_basin_preserves_minimum_cell_as_lake(self):
        terrain, boundary = fixture([[4., 4., 4.], [4., 0., 4.], [4., 4., 4.]])
        graph = route_diagnostic(terrain, boundary)
        self.assertEqual(graph.receiver[4], -1)
        self.assertEqual(graph.outlet_kind[4], "lake_preserved")
        self.assertEqual(graph.lake_id[4], 4)
        result = accumulate_local_discharge(graph, np.ones((3, 3)))
        self.assertEqual(result["lake_retained_m3_s"], 9.)
        self.assertEqual(result["open_outflow_m3_s"], 0.)

    def test_unknown_blocks_flow_and_diagonal_corner(self):
        terrain, boundary = fixture([[3., np.nan, 0.], [np.nan, 1., 2.], [5., 5., 5.]])
        graph = route_diagnostic(terrain, boundary)
        self.assertNotEqual(graph.receiver[0], 4)
        self.assertEqual(graph.receiver[4], -1)
        self.assertEqual(graph.outlet_kind[4], "unknown_boundary")
        self.assertEqual(graph.receiver[1], -1)
        result = accumulate_local_discharge(graph, np.where(terrain.valid_mask, 1., 0.))
        self.assertEqual(result["unknown_pending_m3_s"], 7.)
        with self.assertRaises(ValueError):
            accumulate_local_discharge(graph, np.ones((3, 3)))

    def test_determinism_identity_and_invalid_boundary(self):
        terrain, boundary = fixture([[1., 1.], [1., 1.]])
        first = route_diagnostic(terrain, boundary)
        second = route_diagnostic(terrain, boundary)
        np.testing.assert_array_equal(first.receiver, second.receiver)
        np.testing.assert_array_equal(first.order_downstream_first, second.order_downstream_first)
        self.assertEqual(first.terrain_identity_sha256, terrain.identity_sha256)
        self.assertEqual(first.boundary_identity_sha256, boundary.identity_sha256)
        bad_terrain, _ = fixture(np.ones((3, 3)))
        bad_kind = np.full((3, 3), "closed_wall", dtype="U24")
        bad_kind[1, 1] = "open_outflow"
        with self.assertRaises(ValueError):
            bad = BoundaryGrid(bad_kind, np.zeros((3, 3), bool), "bad", "b" * 64)
            route_diagnostic(bad_terrain, bad)

    def test_perimeter_must_have_explicit_boundary_kind(self):
        terrain, _ = fixture([[2., 1.]])
        boundary = BoundaryGrid(np.array([["interior", "open_outflow"]]),
                                np.zeros((1, 2), bool), "bad", "b" * 64)
        with self.assertRaises(ValueError):
            route_diagnostic(terrain, boundary)


if __name__ == "__main__":
    unittest.main()
