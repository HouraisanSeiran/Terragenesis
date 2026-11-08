import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from terrain_pipeline.channel_geometry import _barycentric_batch, transverse_bed_constraints
from terrain_pipeline.channel_geometry import _barycentric
from terrain_pipeline.channel_geometry import _cell_at_point, _sparse_mesh


class BatchedDesignBarycentricTests(unittest.TestCase):
    def test_real_seed29_gridline_roundoff_keeps_represented_cell(self):
        origin = np.array([53520., -1296480.])
        point = np.array([53855.99999999998, -1293878.])
        self.assertEqual(_cell_at_point(point, {(336, 2602): 0}, origin, 1.), (336, 2602))
        with self.assertRaisesRegex(ValueError, "leaves sparse mesh support"):
            _cell_at_point(point - [1e-6, 0.], {(336, 2602): 0}, origin, 1.)

    def test_first_face_ids_and_weights_match_on_grid_edges_centers_and_large_origins(self):
        cells = np.array([(x, z) for z in range(4) for x in range(4)], np.int64)
        for origin in (np.zeros(2), np.array([1_228_800.0, 2_457_600.0])):
            terrain = SimpleNamespace(x0_m=origin[0], z0_m=origin[1])
            vertices, triangles = _sparse_mesh(cells, terrain, 1.0, 1000)
            interior = vertices[triangles].mean(axis=1)
            points = np.concatenate((vertices, interior))
            lookup = {tuple(cell): i for i, cell in enumerate(cells)}
            owners = np.array([lookup[_cell_at_point(point, lookup, origin, 1.0)]
                               for point in points], np.int64)
            scalar = [_barycentric(point, cell, vertices, triangles)
                      for point, cell in zip(points, owners)]
            indices, weights = _barycentric_batch(points, owners, vertices, triangles)
            np.testing.assert_array_equal(indices, np.array([item[0] for item in scalar]))
            np.testing.assert_array_equal(weights, np.array([item[1] for item in scalar]))

    def test_empty_projected_edge_rows_keep_empty_shapes(self):
        indices, weights = _barycentric_batch(np.empty((0, 2)), np.empty(0, np.int64),
                                               np.empty((0, 2)), np.empty((0, 3), np.int64))
        self.assertEqual(indices.shape, (0, 3))
        self.assertEqual(weights.shape, (0, 3))

    def test_optional_real_saved_s4c9_all_transverse_rows_match_scalar_reference(self):
        root = Path(__file__).resolve().parents[1]
        path = root / "verification/td-terrain-generated-rivers/shape-repair-20261012-09-s4c9/sample-4-component-9.npz"
        reference = root / ".scratch/td-river-shape-repair/transverse-original-09.npz"
        if not path.is_file() or not reference.is_file():
            self.skipTest("optional integration case: real TD artifact and scalar row reference required")
        with np.load(path, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata"]))
            terrain = SimpleNamespace(**{key: metadata["terrain_metadata"][key]
                                         for key in ("x0_m", "z0_m", "dx_m", "dz_m")})
            args = tuple(archive[key] for key in ("node_xz_m", "receiver", "width_m",
                                                 "sparse_cell_xy", "vertices_xz_m", "triangles",
                                                 "source_elevation_m"))
            upper = archive["design_maximum_cut_m"]
        actual = transverse_bed_constraints(*args, terrain, metadata["config"]["fine_spacing_m"],
                                             upper, transverse_bottom_slope=metadata["config"]["transverse_bottom_slope_m_per_m"])
        with np.load(reference, allow_pickle=False) as oracle:
            np.testing.assert_array_equal(actual[0], oracle["indices"])
            np.testing.assert_array_equal(actual[1], oracle["weights"])
            np.testing.assert_array_equal(actual[2], oracle["limits"])
            self.assertEqual(actual[3], int(oracle["cap_count"]))


if __name__ == "__main__":
    unittest.main()
