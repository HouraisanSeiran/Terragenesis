import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.drainage import route_graph as route_graph
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.surface_rivers.contracts import GridInput
from terrain_pipeline.drainage import route as route
from terrain_pipeline.surface_rivers.pipeline import process


class SurfaceRoutingFrameTests(unittest.TestCase):
    def test_overview_routes_at_its_declared_cell_centers(self):
        from terrain_pipeline.fictional_world_overview import OverviewRequest, _drainage
        request = OverviewRequest(grid_size=128)
        rows, cols = np.indices((9, 11))
        bed = 100. - rows - cols * .4
        land = np.ones(bed.shape, bool)
        land[-1, :] = False
        first = .5 * request.spacing_m
        mesh = grid_mesh(bed.shape, x0_m=first, z0_m=first,
                         dx_m=request.spacing_m, world_seed=request.seed)
        expected = route_graph(bed, ~land, mesh)
        actual, _, _ = _drainage(request, bed, land)
        np.testing.assert_array_equal(actual.receiver, expected.receiver)

    def test_pipeline_uses_exact_world_frame(self):
        rows, cols = np.indices((11, 13))
        bed = 100. - rows * .7 - cols * .4
        outlets = np.zeros(bed.shape, bool)
        outlets[-1, -1] = True
        origin = (-17.25, 102.5)
        spacing = 7.
        grid = GridInput(bed, spacing, origin, np.ones(bed.shape), outlets)
        mesh = grid_mesh(bed.shape, x0_m=origin[0], z0_m=origin[1], dx_m=spacing,
                         world_seed=grid.world_seed)
        expected = route_graph(bed, outlets, mesh)
        product = process(grid, threshold_q=1e20)
        np.testing.assert_array_equal(product.receiver.ravel(), expected.receiver)
        np.testing.assert_array_equal(product.input_height, bed)
        self.assertEqual(product.metadata['origin_world_xz'], list(origin))
        self.assertEqual(product.metadata['world_seed'], grid.world_seed)

    def test_shifted_overlapping_route_windows_preserve_absolute_nodes(self):
        rows, cols = np.indices((19, 21))
        bed = 100. + rows * .7 + cols * .3
        outlets = np.zeros(bed.shape, bool)
        outlets[[0, -1], :] = True
        outlets[:, [0, -1]] = True
        captured = []

        def observe(height, explicit_outlets, mesh):
            captured.append(mesh)
            return route_graph(height, explicit_outlets, mesh)

        with patch('terrain_pipeline.drainage.route_graph', side_effect=observe):
            full = route(bed, outlets, 7., origin_world_xz=(-17.25, 102.5))
            cropped = bed[3:16, 4:18]
            border = np.zeros(cropped.shape, bool)
            border[[0, -1], :] = True
            border[:, [0, -1]] = True
            sub = route(cropped, border, 7., origin_world_xz=(10.75, 123.5))
        for name in ('node_x_m', 'node_z_m'):
            first = getattr(captured[0], name).reshape(bed.shape)[3:16, 4:18]
            second = getattr(captured[1], name).reshape(cropped.shape)
            np.testing.assert_array_equal(first, second)
        for row in range(4, 9):
            for col in range(4, 10):
                target = int(sub.receiver[row * cropped.shape[1] + col])
                rr, cc = divmod(target, cropped.shape[1])
                self.assertEqual(int(full.receiver[(row + 3) * bed.shape[1] + col + 4]),
                                 (rr + 3) * bed.shape[1] + cc + 4)


if __name__ == '__main__':
    unittest.main()
