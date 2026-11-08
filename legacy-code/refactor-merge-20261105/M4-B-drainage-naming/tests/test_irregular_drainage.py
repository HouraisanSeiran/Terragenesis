import unittest

import numpy as np

from terrain_pipeline.drainage import _bounded_adjacency as _bounded_adjacency
from terrain_pipeline.drainage import accumulate_graph as accumulate_graph
from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.drainage import route_graph as route_graph
from terrain_pipeline.drainage import accumulate as accumulate
from terrain_pipeline.drainage import route as route


class IrregularDrainageTests(unittest.TestCase):
    def test_positions_are_absolute_and_window_stable(self):
        large = build_mesh((24, 25), (-9, -11))
        small = build_mesh((16, 17), (-5, -7))
        for name in ("node_x_m", "node_z_m"):
            expected = getattr(large, name).reshape(large.shape)[4:20, 4:21]
            np.testing.assert_array_equal(expected, getattr(small, name).reshape(small.shape))
        for z in range(4, 12):
            for x in range(4, 13):
                small_id = z * 17 + x
                large_id = (z + 4) * 25 + x + 4
                near_small = small.indices[small.indptr[small_id]:small.indptr[small_id + 1]]
                near_large = large.indices[large.indptr[large_id]:large.indptr[large_id + 1]]
                expected = {(int(i) // 25 - 4, int(i) % 25 - 4) for i in near_large}
                actual = {(int(i) // 17, int(i) % 17) for i in near_small}
                self.assertEqual(expected, actual)

    def test_nodes_stay_in_accounts_and_edges_have_continuous_directions(self):
        mesh = build_mesh((15, 17), (-12, 7))
        z, x = np.indices(mesh.shape)
        np.testing.assert_array_equal(np.rint(mesh.node_x_m / 30), x.ravel() - 12)
        np.testing.assert_array_equal(np.rint(mesh.node_z_m / 30), z.ravel() + 7)
        start = np.repeat(np.arange(mesh.node_x_m.size), np.diff(mesh.indptr))
        dx = mesh.node_x_m[mesh.indices] - mesh.node_x_m[start]
        dz = mesh.node_z_m[mesh.indices] - mesh.node_z_m[start]
        np.testing.assert_allclose(mesh.edge_length_m, np.hypot(dx, dz))
        self.assertTrue(np.all(mesh.edge_length_m > 0))
        self.assertGreater(np.count_nonzero((abs(dx) > 0) & (abs(dz) > 0)
                                          & (abs(abs(dx) - abs(dz)) > 0.1)), 500)

    def test_bounded_blocks_match_whole_triangulation_and_are_symmetric(self):
        mesh = build_mesh((29, 31), (-13, 19))
        tiled_ptr, tiled_idx = _bounded_adjacency(mesh.node_x_m, mesh.node_z_m,
                                                 mesh.shape, mesh.spacing_m, core_size=7)
        np.testing.assert_array_equal(mesh.indptr, tiled_ptr)
        np.testing.assert_array_equal(mesh.indices, tiled_idx)
        for current in range(mesh.node_x_m.size):
            for neighbor in mesh.indices[mesh.indptr[current]:mesh.indptr[current + 1]]:
                self.assertIn(current, mesh.indices[mesh.indptr[neighbor]:mesh.indptr[neighbor + 1]])

    def test_flood_routes_graph_edges_acyclically_and_conserves(self):
        mesh = build_mesh((11, 13), (-3, -4))
        bed = np.full(mesh.shape, 9.0)
        bed[2:9, 2:11] = -4
        bed[0, 6] = 2
        outlets = np.zeros(mesh.shape, bool)
        outlets[0, 6] = True
        original = bed.copy()
        result = route_graph(bed, outlets, mesh)
        np.testing.assert_array_equal(bed, original)
        self.assertTrue(np.all(result.filled >= bed))
        self.assertGreater(result.filled[5, 5], bed[5, 5])
        for current, downstream in enumerate(result.receiver):
            if downstream < 0:
                self.assertTrue(outlets.flat[current])
                continue
            self.assertIn(downstream, mesh.indices[mesh.indptr[current]:mesh.indptr[current + 1]])
            self.assertLess(result.rank[downstream], result.rank[current])
            self.assertLessEqual(result.filled.flat[downstream], result.filled.flat[current])
        local = np.arange(bed.size, dtype=float).reshape(bed.shape) + 1
        flow = accumulate_graph(result.receiver, result.order, local)
        self.assertEqual(float(flow[outlets].sum()), float(local.sum()))
        again = route_graph(bed, outlets, mesh)
        np.testing.assert_array_equal(result.receiver, again.receiver)

    def test_receiver_chooses_largest_metric_slope(self):
        mesh = build_mesh((12, 13))
        bed = np.sin(mesh.node_x_m / 53).reshape(mesh.shape) * 5 + mesh.node_z_m.reshape(mesh.shape) / 10
        outlets = np.zeros(mesh.shape, bool)
        outlets[0] = True
        result = route_graph(bed, outlets, mesh)
        for current in np.flatnonzero(~outlets.ravel()):
            edges = np.arange(mesh.indptr[current], mesh.indptr[current + 1])
            neighbors = mesh.indices[edges]
            eligible = (result.rank[neighbors] < result.rank[current]) & (result.filled.ravel()[neighbors] <= result.filled.flat[current])
            slopes = (result.filled.flat[current] - result.filled.ravel()[neighbors[eligible]]) / mesh.edge_length_m[edges[eligible]]
            chosen_edge = edges[neighbors == result.receiver[current]][0]
            chosen_slope = (result.filled.flat[current] - result.filled.flat[result.receiver[current]]) / mesh.edge_length_m[chosen_edge]
            self.assertAlmostEqual(chosen_slope, float(slopes.max()))

    def test_adapter_preserves_account_area_and_contract(self):
        bed = np.arange(35, dtype=float).reshape(5, 7)
        outlets = np.zeros(bed.shape, bool)
        outlets[0] = True
        routing = route(bed, outlets, 30, origin_native_xz=(-7, 2))
        result = accumulate(routing, np.ones(bed.shape), 30)
        self.assertEqual(result.input_total, 35 * 900)
        self.assertEqual(result.outlet_total, result.input_total)

    def test_tiny_meshes_and_invalid_input(self):
        for shape in ((1, 1), (1, 2), (1, 3), (3, 1)):
            mesh = build_mesh(shape)
            outlets = np.zeros(shape, bool)
            outlets.flat[0] = True
            result = route_graph(np.zeros(shape), outlets, mesh)
            flow = accumulate_graph(result.receiver, result.order, np.ones(shape))
            self.assertEqual(flow.flat[0], np.prod(shape))
        with self.assertRaises(ValueError):
            build_mesh((0, 4))
        mesh = build_mesh((3, 4))
        with self.assertRaises(ValueError):
            route_graph(np.zeros(mesh.shape), np.zeros(mesh.shape, bool), mesh)
        with self.assertRaises(ValueError):
            accumulate_graph(np.array([1, 0]), np.array([0, 1]), np.ones(2))
        with self.assertRaises(ValueError):
            accumulate_graph(np.array([-1]), np.array([0]), np.array([-1.0]))


if __name__ == "__main__":
    unittest.main()
