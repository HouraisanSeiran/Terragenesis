import unittest

import numpy as np

from terrain_pipeline.common_infra import BoundaryGrid, RainfallForcing, RoutingGraph, TerrainGrid


def terrain(height, **kwargs):
    values = np.asarray(height, dtype=np.float64)
    options = dict(elevation_m=values, valid_mask=np.isfinite(values), x0_m=100., z0_m=200.,
                   dx_m=3., dz_m=4., source_kind="generated_terrain", source_id="synthetic",
                   source_sha256="a" * 64)
    options.update(kwargs)
    return TerrainGrid(**options)


class TerrainContractTests(unittest.TestCase):
    def test_million_cell_grid_and_three_interval_forcing_have_bounded_capacity(self):
        shape = (1024, 1024)
        grid = terrain(np.zeros(shape), dx_m=30., dz_m=30.)
        self.assertEqual(grid.world_xz(1024 * 1024 - 1), (30790., 30890.))
        forcing = RainfallForcing(np.array([0., 300., 600., 900.]), np.zeros((3,) + shape),
                                  source_id="large", source_sha256="c" * 64)
        self.assertEqual(forcing.rain_mm_h.shape, (3, 1024, 1024))
        larger_static_grid = terrain(np.zeros((1025, 1024)))
        self.assertEqual(larger_static_grid.elevation_m.shape, (1025, 1024))
        with self.assertRaises(ValueError):
            terrain(np.zeros((1281, 1280)))
        with self.assertRaises(ValueError):
            RainfallForcing(np.arange(5, dtype=np.float64), np.zeros((4,) + shape),
                            source_id="over-budget", source_sha256="c" * 64)

    def test_metric_numbers_are_serializable_and_extents_cannot_overflow(self):
        grid = terrain([[1., 0.]], x0_m=np.int64(10), dz_m=np.float32(4))
        self.assertEqual(grid.world_xz(1), (13., 200.))
        self.assertEqual(len(grid.identity_sha256), 64)
        with self.assertRaisesRegex(ValueError, "area"):
            terrain([[1., 0.]], dx_m=1e-200, dz_m=1e-200)
        with self.assertRaisesRegex(ValueError, "extent"):
            terrain([[1., 0.]], x0_m=1e308, dx_m=1e308, dz_m=1.)

    def test_rectangular_metric_grid_is_immutable_and_hashes_coordinates(self):
        raw = np.array([[3., 2.], [1., 0.]])
        grid = terrain(raw)
        self.assertEqual(grid.cell_area_m2, 12.)
        self.assertEqual(grid.world_xz(3), (103., 204.))
        self.assertEqual(grid.identity_sha256, terrain(raw).identity_sha256)
        self.assertNotEqual(grid.identity_sha256, terrain(raw, x0_m=101.).identity_sha256)
        raw[0, 0] = 999.
        self.assertEqual(grid.elevation_m[0, 0], 3.)
        with self.assertRaises(ValueError):
            grid.elevation_m.setflags(write=True)
        self.assertEqual(grid.provenance_status, "pending_provenance")

    def test_boundary_types_direction_and_forcing_intervals_are_explicit(self):
        kind = np.array([["closed_wall", "open_outflow"]])
        boundary = BoundaryGrid(kind, np.zeros((1, 2), bool), source_id="fixture", source_sha256="b" * 64)
        self.assertTrue(boundary.outlet_mask[0, 1])
        with self.assertRaises(ValueError):
            BoundaryGrid(kind, np.ones((1, 2), bool), source_id="fixture", source_sha256="b" * 64)
        forcing = RainfallForcing(np.array([5., 65., 185.]), np.array([[[60., 60.]], [[0., 0.]]]),
                                  source_id="pulse", source_sha256="c" * 64)
        np.testing.assert_array_equal(forcing.interval_seconds, [60., 120.])
        np.testing.assert_array_equal(forcing.rainfall_depth_mm[:, 0, 0], [1., 0.])
        with self.assertRaises(ValueError):
            RainfallForcing(np.array([0., 0., 2.]), forcing.rain_mm_h, source_id="x", source_sha256="c" * 64)

    def test_graph_binds_donors_and_rejects_cycles(self):
        arguments = dict(receiver=np.array([1, -1, 1], np.int64),
                         order_downstream_first=np.array([1, 0, 2], np.int64),
                         valid_mask=np.ones((1, 3), bool), edge_length_m=np.array([3., 0., 3.]),
                         edge_slope=np.array([1., 0., 1.]),
                         outlet_kind=np.array(["interior", "open_outflow", "interior"]),
                         lake_id=np.full(3, -1, np.int64), terrain_identity_sha256="a" * 64,
                         boundary_identity_sha256="b" * 64)
        graph = RoutingGraph(**arguments)
        self.assertEqual(graph.donors, ((), (0, 2), ()))
        with self.assertRaises(ValueError):
            RoutingGraph(**dict(arguments, receiver=np.array([1, 0, -1], np.int64)))
        long_edge = RoutingGraph(**dict(arguments, receiver=np.array([2, -1, 1], np.int64),
                                       order_downstream_first=np.array([1, 2, 0], np.int64)))
        self.assertEqual(long_edge.receiver[0], 2)
        with self.assertRaisesRegex(ValueError, "self"):
            RoutingGraph(**dict(arguments, receiver=np.array([0, -1, 1], np.int64)))

    def test_public_graph_rejects_diagonal_crossing_unknown_corners(self):
        with self.assertRaisesRegex(ValueError, "unknown corner"):
            RoutingGraph(receiver=np.array([3, -1, -1, -1], np.int64),
                         order_downstream_first=np.array([3, 0], np.int64),
                         valid_mask=np.array([[True, False], [False, True]]),
                         edge_length_m=np.array([5., 0., 0., 0.]),
                         edge_slope=np.array([1., 0., 0., 0.]),
                         outlet_kind=np.array(["interior", "inactive", "inactive", "open_outflow"]),
                         lake_id=np.full(4, -1, np.int64), terrain_identity_sha256="a" * 64,
                         boundary_identity_sha256="b" * 64)


if __name__ == "__main__":
    unittest.main()
