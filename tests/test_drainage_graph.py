"""M4 tests.test_drainage_graph; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from terrain_pipeline.drainage import _bounded_adjacency as _m4_test_irregular_drainage_bounded_adjacency
from terrain_pipeline.drainage import accumulate as _m4_test_irregular_drainage_accumulate
from terrain_pipeline.drainage import accumulate_graph as _m4_test_irregular_drainage_accumulate_graph
from terrain_pipeline.drainage import build_mesh as _m4_test_irregular_drainage_build_mesh
from terrain_pipeline.drainage import route as _m4_test_irregular_drainage_route
from terrain_pipeline.drainage import route_graph as _m4_test_irregular_drainage_route_graph
import numpy as _m4_test_irregular_drainage_np
import unittest as _m4_test_irregular_drainage_unittest

# --- tests/test_irregular_drainage.py:13 ---
class TestIrregularDrainageIrregularDrainageTests(_m4_test_irregular_drainage_unittest.TestCase):
    def test_positions_are_absolute_and_window_stable(self):
        large = _m4_test_irregular_drainage_build_mesh((24, 25), (-9, -11))
        small = _m4_test_irregular_drainage_build_mesh((16, 17), (-5, -7))
        for name in ("node_x_m", "node_z_m"):
            expected = getattr(large, name).reshape(large.shape)[4:20, 4:21]
            _m4_test_irregular_drainage_np.testing.assert_array_equal(expected, getattr(small, name).reshape(small.shape))
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
        mesh = _m4_test_irregular_drainage_build_mesh((15, 17), (-12, 7))
        z, x = _m4_test_irregular_drainage_np.indices(mesh.shape)
        _m4_test_irregular_drainage_np.testing.assert_array_equal(_m4_test_irregular_drainage_np.rint(mesh.node_x_m / 30), x.ravel() - 12)
        _m4_test_irregular_drainage_np.testing.assert_array_equal(_m4_test_irregular_drainage_np.rint(mesh.node_z_m / 30), z.ravel() + 7)
        start = _m4_test_irregular_drainage_np.repeat(_m4_test_irregular_drainage_np.arange(mesh.node_x_m.size), _m4_test_irregular_drainage_np.diff(mesh.indptr))
        dx = mesh.node_x_m[mesh.indices] - mesh.node_x_m[start]
        dz = mesh.node_z_m[mesh.indices] - mesh.node_z_m[start]
        _m4_test_irregular_drainage_np.testing.assert_allclose(mesh.edge_length_m, _m4_test_irregular_drainage_np.hypot(dx, dz))
        self.assertTrue(_m4_test_irregular_drainage_np.all(mesh.edge_length_m > 0))
        self.assertGreater(_m4_test_irregular_drainage_np.count_nonzero((abs(dx) > 0) & (abs(dz) > 0)
                                          & (abs(abs(dx) - abs(dz)) > 0.1)), 500)

    def test_bounded_blocks_match_whole_triangulation_and_are_symmetric(self):
        mesh = _m4_test_irregular_drainage_build_mesh((29, 31), (-13, 19))
        tiled_ptr, tiled_idx = _m4_test_irregular_drainage_bounded_adjacency(mesh.node_x_m, mesh.node_z_m,
                                                 mesh.shape, mesh.spacing_m, core_size=7)
        _m4_test_irregular_drainage_np.testing.assert_array_equal(mesh.indptr, tiled_ptr)
        _m4_test_irregular_drainage_np.testing.assert_array_equal(mesh.indices, tiled_idx)
        for current in range(mesh.node_x_m.size):
            for neighbor in mesh.indices[mesh.indptr[current]:mesh.indptr[current + 1]]:
                self.assertIn(current, mesh.indices[mesh.indptr[neighbor]:mesh.indptr[neighbor + 1]])

    def test_flood_routes_graph_edges_acyclically_and_conserves(self):
        mesh = _m4_test_irregular_drainage_build_mesh((11, 13), (-3, -4))
        bed = _m4_test_irregular_drainage_np.full(mesh.shape, 9.0)
        bed[2:9, 2:11] = -4
        bed[0, 6] = 2
        outlets = _m4_test_irregular_drainage_np.zeros(mesh.shape, bool)
        outlets[0, 6] = True
        original = bed.copy()
        result = _m4_test_irregular_drainage_route_graph(bed, outlets, mesh)
        _m4_test_irregular_drainage_np.testing.assert_array_equal(bed, original)
        self.assertTrue(_m4_test_irregular_drainage_np.all(result.filled >= bed))
        self.assertGreater(result.filled[5, 5], bed[5, 5])
        for current, downstream in enumerate(result.receiver):
            if downstream < 0:
                self.assertTrue(outlets.flat[current])
                continue
            self.assertIn(downstream, mesh.indices[mesh.indptr[current]:mesh.indptr[current + 1]])
            self.assertLess(result.rank[downstream], result.rank[current])
            self.assertLessEqual(result.filled.flat[downstream], result.filled.flat[current])
        local = _m4_test_irregular_drainage_np.arange(bed.size, dtype=float).reshape(bed.shape) + 1
        flow = _m4_test_irregular_drainage_accumulate_graph(result.receiver, result.order, local)
        self.assertEqual(float(flow[outlets].sum()), float(local.sum()))
        again = _m4_test_irregular_drainage_route_graph(bed, outlets, mesh)
        _m4_test_irregular_drainage_np.testing.assert_array_equal(result.receiver, again.receiver)

    def test_receiver_chooses_largest_metric_slope(self):
        mesh = _m4_test_irregular_drainage_build_mesh((12, 13))
        bed = _m4_test_irregular_drainage_np.sin(mesh.node_x_m / 53).reshape(mesh.shape) * 5 + mesh.node_z_m.reshape(mesh.shape) / 10
        outlets = _m4_test_irregular_drainage_np.zeros(mesh.shape, bool)
        outlets[0] = True
        result = _m4_test_irregular_drainage_route_graph(bed, outlets, mesh)
        for current in _m4_test_irregular_drainage_np.flatnonzero(~outlets.ravel()):
            edges = _m4_test_irregular_drainage_np.arange(mesh.indptr[current], mesh.indptr[current + 1])
            neighbors = mesh.indices[edges]
            eligible = (result.rank[neighbors] < result.rank[current]) & (result.filled.ravel()[neighbors] <= result.filled.flat[current])
            slopes = (result.filled.flat[current] - result.filled.ravel()[neighbors[eligible]]) / mesh.edge_length_m[edges[eligible]]
            chosen_edge = edges[neighbors == result.receiver[current]][0]
            chosen_slope = (result.filled.flat[current] - result.filled.flat[result.receiver[current]]) / mesh.edge_length_m[chosen_edge]
            self.assertAlmostEqual(chosen_slope, float(slopes.max()))

    def test_adapter_preserves_account_area_and_contract(self):
        bed = _m4_test_irregular_drainage_np.arange(35, dtype=float).reshape(5, 7)
        outlets = _m4_test_irregular_drainage_np.zeros(bed.shape, bool)
        outlets[0] = True
        routing = _m4_test_irregular_drainage_route(bed, outlets, 30, origin_native_xz=(-7, 2))
        result = _m4_test_irregular_drainage_accumulate(routing, _m4_test_irregular_drainage_np.ones(bed.shape), 30)
        self.assertEqual(result.input_total, 35 * 900)
        self.assertEqual(result.outlet_total, result.input_total)

    def test_tiny_meshes_and_invalid_input(self):
        for shape in ((1, 1), (1, 2), (1, 3), (3, 1)):
            mesh = _m4_test_irregular_drainage_build_mesh(shape)
            outlets = _m4_test_irregular_drainage_np.zeros(shape, bool)
            outlets.flat[0] = True
            result = _m4_test_irregular_drainage_route_graph(_m4_test_irregular_drainage_np.zeros(shape), outlets, mesh)
            flow = _m4_test_irregular_drainage_accumulate_graph(result.receiver, result.order, _m4_test_irregular_drainage_np.ones(shape))
            self.assertEqual(flow.flat[0], _m4_test_irregular_drainage_np.prod(shape))
        with self.assertRaises(ValueError):
            _m4_test_irregular_drainage_build_mesh((0, 4))
        mesh = _m4_test_irregular_drainage_build_mesh((3, 4))
        with self.assertRaises(ValueError):
            _m4_test_irregular_drainage_route_graph(_m4_test_irregular_drainage_np.zeros(mesh.shape), _m4_test_irregular_drainage_np.zeros(mesh.shape, bool), mesh)
        with self.assertRaises(ValueError):
            _m4_test_irregular_drainage_accumulate_graph(_m4_test_irregular_drainage_np.array([1, 0]), _m4_test_irregular_drainage_np.array([0, 1]), _m4_test_irregular_drainage_np.ones(2))
        with self.assertRaises(ValueError):
            _m4_test_irregular_drainage_accumulate_graph(_m4_test_irregular_drainage_np.array([-1]), _m4_test_irregular_drainage_np.array([0]), _m4_test_irregular_drainage_np.array([-1.0]))
