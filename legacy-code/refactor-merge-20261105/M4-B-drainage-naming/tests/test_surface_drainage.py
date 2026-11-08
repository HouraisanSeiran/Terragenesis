import unittest

import numpy as np

from terrain_pipeline.surface_rivers import GridInput, RoutingResult, accumulate, channel_mask, route
from terrain_pipeline.drainage import build_mesh as build_mesh


class SurfaceDrainageTests(unittest.TestCase):
    def test_single_explicit_outlet_conserves_runoff_and_input(self):
        height = np.array([[9., 8., 7.], [8., 7., 6.], [7., 6., 5.]])
        outlets = np.zeros_like(height, dtype=bool)
        outlets[2, 2] = True
        before = height.copy()
        routing = route(height, outlets, 2.0)
        np.testing.assert_array_equal(height, before)
        self.assertEqual(int(routing.receiver[8]), -1)
        self.assertEqual(np.count_nonzero(routing.receiver == -1), 1)
        runoff = np.full_like(height, .5)
        extra = np.zeros_like(height)
        extra[0, 0] = 3.0
        result = accumulate(routing, runoff, 2.0, extra)
        self.assertAlmostEqual(result.input_total, 21.0)
        self.assertAlmostEqual(result.outlet_total, 21.0)
        self.assertAlmostEqual(result.residual, 0.0)
        self.assertAlmostEqual(result.discharge[2, 2], 21.0)
        self.assertTrue(channel_mask(result.discharge, 20.0)[2, 2])
        self.assertFalse(channel_mask(result.discharge, 22.0).any())

    def test_pit_fill_flat_route_is_deterministic_and_acyclic(self):
        height = np.array([[10., 10., 10.], [10., 0., 10.], [10., 10., 9.]])
        outlets = np.zeros_like(height, dtype=bool)
        outlets[2, 2] = True
        a = route(height, outlets, 1.0)
        b = route(height, outlets, 1.0)
        np.testing.assert_array_equal(a.receiver, b.receiver)
        np.testing.assert_array_equal(a.order, b.order)
        self.assertEqual(height[1, 1], 0.0)
        # The center has no direct graph edge to the diagonal 9 m outlet;
        # its escape must cross the actual 10 m surrounding barrier.
        self.assertEqual(a.routing_height[1, 1], 10.0)
        rank = np.empty(height.size, dtype=np.int64)
        rank[a.order] = np.arange(height.size)
        for i, downstream in enumerate(a.receiver):
            if downstream >= 0:
                self.assertLess(rank[downstream], rank[i])

    def test_only_masked_boundary_cells_are_outlets(self):
        height = np.full((3, 3), 5.0)
        outlets = np.zeros_like(height, dtype=bool)
        outlets[0, 1] = True
        routing = route(height, outlets, 1.0)
        np.testing.assert_array_equal(np.flatnonzero(routing.receiver == -1), [1])
        result = accumulate(routing, np.ones_like(height), 1.0)
        self.assertEqual(result.outlet_discharge[0, 1], 9.0)

    def test_multiple_outlets_have_complete_budget(self):
        height = np.ones((4, 4))
        outlets = np.zeros_like(height, dtype=bool)
        outlets[0, 0] = outlets[3, 3] = True
        routing = route(height, outlets, 3.0)
        result = accumulate(routing, np.ones_like(height), 3.0)
        self.assertAlmostEqual(result.outlet_total, 144.0)
        self.assertAlmostEqual(result.residual, 0.0)
        self.assertEqual(np.count_nonzero(result.outlet_discharge), 2)

    def test_descent_uses_representative_positions_instead_of_raster_axes(self):
        height = np.array([[10., 8.], [8., 8.]])
        outlets = np.array([[False, True], [False, True]])
        routing = route(height, outlets, 1.0)
        mesh = build_mesh(height.shape, spacing_m=1.)
        distances = np.hypot(mesh.node_x_m - mesh.node_x_m[0], mesh.node_z_m - mesh.node_z_m[0])
        self.assertLess(distances[3], distances[1])
        self.assertEqual(routing.receiver[0], 3)

    def test_explicit_confluence_sums_local_runoff(self):
        height = np.array([[4., 4., 4.], [3., 2., 3.], [4., 1., 4.]])
        outlets = np.zeros_like(height, dtype=bool)
        outlets[2, 1] = True
        grid = GridInput(height, 2.0, (-100.0, 50.0), np.ones_like(height), outlets)
        routing = route(grid.height, grid.outlet_mask, grid.spacing_blocks)
        result = accumulate(routing, grid.runoff, grid.spacing_blocks)
        self.assertEqual(grid.origin, (-100.0, 50.0))
        donors = np.flatnonzero(routing.receiver == 4)
        self.assertGreaterEqual(len(donors), 2)
        self.assertEqual(result.discharge[1, 1], 4.0 + sum(result.discharge.flat[i] for i in donors))
        self.assertEqual(result.discharge[2, 1], 36.0)

    def test_input_and_routing_arrays_are_read_only(self):
        height = np.array([[2., 1.]])
        runoff = np.ones_like(height)
        outlets = np.array([[False, True]])
        grid = GridInput(height, 1.0, (-4., 6.), runoff, outlets)
        for array in (grid.height, grid.runoff, grid.outlet_mask):
            self.assertFalse(array.flags.writeable)
            with self.assertRaises(ValueError):
                array.flat[0] = 0
        height[0, 0] = 99
        self.assertEqual(grid.height[0, 0], 2.0)
        routing = route(grid.height, grid.outlet_mask, grid.spacing_blocks)
        for array in (routing.receiver, routing.order, routing.routing_height, routing.outlet_mask):
            self.assertFalse(array.flags.writeable)
            with self.assertRaises(ValueError):
                array.flat[0] = 0

    def test_rejects_invalid_receiver_and_order(self):
        height = np.array([[3., 2., 1.]])
        outlets = np.array([[False, False, True]])
        valid = route(height, outlets, 1.0)
        bad_receiver = RoutingResult(np.array([1, 0, -1]), valid.order,
                                     valid.routing_height, valid.outlet_mask, 1.0)
        with self.assertRaises(ValueError):
            accumulate(bad_receiver, np.ones_like(height), 1.0)
        bad_order = RoutingResult(valid.receiver, np.array([2, 2, 0]),
                                  valid.routing_height, valid.outlet_mask, 1.0)
        with self.assertRaises(ValueError):
            accumulate(bad_order, np.ones_like(height), 1.0)

    def test_rejects_missing_outlets_and_invalid_grids(self):
        height = np.ones((2, 2))
        with self.assertRaises(ValueError):
            route(height, np.zeros((2, 2), dtype=bool), 1.0)
        with self.assertRaises(ValueError):
            route(np.array([[np.nan]]), np.array([[True]]), 1.0)
        with self.assertRaises(ValueError):
            GridInput(height, 1.0, (0, 0), np.ones_like(height), np.zeros((2, 2), bool))


if __name__ == "__main__":
    unittest.main()
