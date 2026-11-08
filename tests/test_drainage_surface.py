"""M4 tests.test_drainage_surface; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from terrain_pipeline.drainage import build_mesh as _m4_test_surface_drainage_build_mesh
from terrain_pipeline.surface_rivers import GridInput as _m4_test_surface_drainage_GridInput
from terrain_pipeline.surface_rivers import RoutingResult as _m4_test_surface_drainage_RoutingResult
from terrain_pipeline.surface_rivers import accumulate as _m4_test_surface_drainage_accumulate
from terrain_pipeline.surface_rivers import channel_mask as _m4_test_surface_drainage_channel_mask
from terrain_pipeline.surface_rivers import route as _m4_test_surface_drainage_route
import numpy as _m4_test_surface_drainage_np
import unittest as _m4_test_surface_drainage_unittest

# --- tests/test_surface_drainage.py:9 ---
class TestSurfaceDrainageSurfaceDrainageTests(_m4_test_surface_drainage_unittest.TestCase):
    def test_single_explicit_outlet_conserves_runoff_and_input(self):
        height = _m4_test_surface_drainage_np.array([[9., 8., 7.], [8., 7., 6.], [7., 6., 5.]])
        outlets = _m4_test_surface_drainage_np.zeros_like(height, dtype=bool)
        outlets[2, 2] = True
        before = height.copy()
        routing = _m4_test_surface_drainage_route(height, outlets, 2.0)
        _m4_test_surface_drainage_np.testing.assert_array_equal(height, before)
        self.assertEqual(int(routing.receiver[8]), -1)
        self.assertEqual(_m4_test_surface_drainage_np.count_nonzero(routing.receiver == -1), 1)
        runoff = _m4_test_surface_drainage_np.full_like(height, .5)
        extra = _m4_test_surface_drainage_np.zeros_like(height)
        extra[0, 0] = 3.0
        result = _m4_test_surface_drainage_accumulate(routing, runoff, 2.0, extra)
        self.assertAlmostEqual(result.input_total, 21.0)
        self.assertAlmostEqual(result.outlet_total, 21.0)
        self.assertAlmostEqual(result.residual, 0.0)
        self.assertAlmostEqual(result.discharge[2, 2], 21.0)
        self.assertTrue(_m4_test_surface_drainage_channel_mask(result.discharge, 20.0)[2, 2])
        self.assertFalse(_m4_test_surface_drainage_channel_mask(result.discharge, 22.0).any())

    def test_pit_fill_flat_route_is_deterministic_and_acyclic(self):
        height = _m4_test_surface_drainage_np.array([[10., 10., 10.], [10., 0., 10.], [10., 10., 9.]])
        outlets = _m4_test_surface_drainage_np.zeros_like(height, dtype=bool)
        outlets[2, 2] = True
        a = _m4_test_surface_drainage_route(height, outlets, 1.0)
        b = _m4_test_surface_drainage_route(height, outlets, 1.0)
        _m4_test_surface_drainage_np.testing.assert_array_equal(a.receiver, b.receiver)
        _m4_test_surface_drainage_np.testing.assert_array_equal(a.order, b.order)
        self.assertEqual(height[1, 1], 0.0)
        # The center has no direct graph edge to the diagonal 9 m outlet;
        # its escape must cross the actual 10 m surrounding barrier.
        self.assertEqual(a.routing_height[1, 1], 10.0)
        rank = _m4_test_surface_drainage_np.empty(height.size, dtype=_m4_test_surface_drainage_np.int64)
        rank[a.order] = _m4_test_surface_drainage_np.arange(height.size)
        for i, downstream in enumerate(a.receiver):
            if downstream >= 0:
                self.assertLess(rank[downstream], rank[i])

    def test_only_masked_boundary_cells_are_outlets(self):
        height = _m4_test_surface_drainage_np.full((3, 3), 5.0)
        outlets = _m4_test_surface_drainage_np.zeros_like(height, dtype=bool)
        outlets[0, 1] = True
        routing = _m4_test_surface_drainage_route(height, outlets, 1.0)
        _m4_test_surface_drainage_np.testing.assert_array_equal(_m4_test_surface_drainage_np.flatnonzero(routing.receiver == -1), [1])
        result = _m4_test_surface_drainage_accumulate(routing, _m4_test_surface_drainage_np.ones_like(height), 1.0)
        self.assertEqual(result.outlet_discharge[0, 1], 9.0)

    def test_multiple_outlets_have_complete_budget(self):
        height = _m4_test_surface_drainage_np.ones((4, 4))
        outlets = _m4_test_surface_drainage_np.zeros_like(height, dtype=bool)
        outlets[0, 0] = outlets[3, 3] = True
        routing = _m4_test_surface_drainage_route(height, outlets, 3.0)
        result = _m4_test_surface_drainage_accumulate(routing, _m4_test_surface_drainage_np.ones_like(height), 3.0)
        self.assertAlmostEqual(result.outlet_total, 144.0)
        self.assertAlmostEqual(result.residual, 0.0)
        self.assertEqual(_m4_test_surface_drainage_np.count_nonzero(result.outlet_discharge), 2)

    def test_descent_uses_representative_positions_instead_of_raster_axes(self):
        height = _m4_test_surface_drainage_np.array([[10., 8.], [8., 8.]])
        outlets = _m4_test_surface_drainage_np.array([[False, True], [False, True]])
        routing = _m4_test_surface_drainage_route(height, outlets, 1.0)
        mesh = _m4_test_surface_drainage_build_mesh(height.shape, spacing_m=1.)
        distances = _m4_test_surface_drainage_np.hypot(mesh.node_x_m - mesh.node_x_m[0], mesh.node_z_m - mesh.node_z_m[0])
        self.assertLess(distances[3], distances[1])
        self.assertEqual(routing.receiver[0], 3)

    def test_explicit_confluence_sums_local_runoff(self):
        height = _m4_test_surface_drainage_np.array([[4., 4., 4.], [3., 2., 3.], [4., 1., 4.]])
        outlets = _m4_test_surface_drainage_np.zeros_like(height, dtype=bool)
        outlets[2, 1] = True
        grid = _m4_test_surface_drainage_GridInput(height, 2.0, (-100.0, 50.0), _m4_test_surface_drainage_np.ones_like(height), outlets)
        routing = _m4_test_surface_drainage_route(grid.height, grid.outlet_mask, grid.spacing_blocks)
        result = _m4_test_surface_drainage_accumulate(routing, grid.runoff, grid.spacing_blocks)
        self.assertEqual(grid.origin, (-100.0, 50.0))
        donors = _m4_test_surface_drainage_np.flatnonzero(routing.receiver == 4)
        self.assertGreaterEqual(len(donors), 2)
        self.assertEqual(result.discharge[1, 1], 4.0 + sum(result.discharge.flat[i] for i in donors))
        self.assertEqual(result.discharge[2, 1], 36.0)

    def test_input_and_routing_arrays_are_read_only(self):
        height = _m4_test_surface_drainage_np.array([[2., 1.]])
        runoff = _m4_test_surface_drainage_np.ones_like(height)
        outlets = _m4_test_surface_drainage_np.array([[False, True]])
        grid = _m4_test_surface_drainage_GridInput(height, 1.0, (-4., 6.), runoff, outlets)
        for array in (grid.height, grid.runoff, grid.outlet_mask):
            self.assertFalse(array.flags.writeable)
            with self.assertRaises(ValueError):
                array.flat[0] = 0
        height[0, 0] = 99
        self.assertEqual(grid.height[0, 0], 2.0)
        routing = _m4_test_surface_drainage_route(grid.height, grid.outlet_mask, grid.spacing_blocks)
        for array in (routing.receiver, routing.order, routing.routing_height, routing.outlet_mask):
            self.assertFalse(array.flags.writeable)
            with self.assertRaises(ValueError):
                array.flat[0] = 0

    def test_rejects_invalid_receiver_and_order(self):
        height = _m4_test_surface_drainage_np.array([[3., 2., 1.]])
        outlets = _m4_test_surface_drainage_np.array([[False, False, True]])
        valid = _m4_test_surface_drainage_route(height, outlets, 1.0)
        bad_receiver = _m4_test_surface_drainage_RoutingResult(_m4_test_surface_drainage_np.array([1, 0, -1]), valid.order,
                                     valid.routing_height, valid.outlet_mask, 1.0)
        with self.assertRaises(ValueError):
            _m4_test_surface_drainage_accumulate(bad_receiver, _m4_test_surface_drainage_np.ones_like(height), 1.0)
        bad_order = _m4_test_surface_drainage_RoutingResult(valid.receiver, _m4_test_surface_drainage_np.array([2, 2, 0]),
                                  valid.routing_height, valid.outlet_mask, 1.0)
        with self.assertRaises(ValueError):
            _m4_test_surface_drainage_accumulate(bad_order, _m4_test_surface_drainage_np.ones_like(height), 1.0)

    def test_rejects_missing_outlets_and_invalid_grids(self):
        height = _m4_test_surface_drainage_np.ones((2, 2))
        with self.assertRaises(ValueError):
            _m4_test_surface_drainage_route(height, _m4_test_surface_drainage_np.zeros((2, 2), dtype=bool), 1.0)
        with self.assertRaises(ValueError):
            _m4_test_surface_drainage_route(_m4_test_surface_drainage_np.array([[_m4_test_surface_drainage_np.nan]]), _m4_test_surface_drainage_np.array([[True]]), 1.0)
        with self.assertRaises(ValueError):
            _m4_test_surface_drainage_GridInput(height, 1.0, (0, 0), _m4_test_surface_drainage_np.ones_like(height), _m4_test_surface_drainage_np.zeros((2, 2), bool))
