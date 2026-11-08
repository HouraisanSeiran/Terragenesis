import unittest
from unittest.mock import patch

import numpy as np
from scipy.sparse import eye

from terrain_pipeline import channel_geometry as design
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_td_generated_rivers import GeneratedRiverConfig
from terrain_pipeline.channel_geometry import _sparse_mesh


class DesignMergeGroupTests(unittest.TestCase):
    def setUp(self):
        self.config = GeneratedRiverConfig()
        self.terrain = TerrainGrid(np.full((4, 4), 10.0), np.ones((4, 4), bool),
                                   0.0, 0.0, 30.0, 30.0, "observed_dem", "groups", "a" * 64)

    def bundle(self, points, ids, *, depth=0.5, padding=None):
        receiver = np.array([1, -1])
        width = np.full(2, 2.0)
        source_nodes = design._metric_channel_geometry_sample(self.terrain.elevation_m, points, self.terrain)[0]
        profile = (np.array([0, 2]), np.array([0.0, 1.0]), source_nodes,
                   source_nodes - [depth, depth + 1e-5 * np.linalg.norm(points[1]-points[0])])
        result = design.build_design_geometry(points, receiver, width, np.full(2, 0.25),
                                              profile, self.terrain, 1.0, 4.0, 1e-5)
        cells, vertices, triangles, source, _, cut, closure, lower, upper, pad, boundary = result
        if padding is not None:
            pad = np.full(len(vertices), padding)
            upper = np.full(len(vertices), 4.0-padding)
            upper[boundary] = 0.0
            cut, closure = design.solve_design_bed(points, receiver, cells, vertices, triangles,
                                                   source, lower, upper, self.terrain, 1.0,
                                                   profile, 1e-5, width=width)
        arrays = dict(sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles,
                      source_elevation_m=source, source_node_cell_ids=np.asarray(ids),
                      receiver=receiver, node_xz_m=points, width_m=width, base_depth_m=np.full(2, 0.25),
                      cut_depth_m=cut, design_minimum_cut_m=lower, design_maximum_cut_m=upper,
                      source_interpolation_padding_m=pad, profile_offsets=profile[0], profile_t=profile[1],
                      profile_source_m=profile[2], profile_center_bed_m=profile[3])
        from dataclasses import asdict
        metadata = dict(closure=closure, minimum_bed_slope_m_per_m=1e-5,
                        source_identity_sha256=self.terrain.identity_sha256, config=asdict(self.config))
        return dict(arrays=arrays, metadata=metadata)

    def merge(self, bundles):
        return design.merge_design_bundles(self.terrain, bundles, self.config, np.full(4, 0.25))

    def test_disjoint_optima_reused_and_match_monolithic_volume_and_bounds(self):
        bundles = [self.bundle(np.array([[15., 20.], [20., 20.]]), [0, 1]),
                   self.bundle(np.array([[65., 60.], [70., 60.]]), [2, 3])]
        with patch.object(design, '_i27_linprog', wraps=design._i27_linprog) as solver:
            merged = self.merge(bundles)
        self.assertEqual(solver.call_count, 0)
        a, closure = merged["arrays"], merged["metadata"]["closure"]
        self.assertEqual(closure["support_group_count"], 2)
        self.assertEqual(closure["reused_optimal_components"], 2)
        profile = tuple(a[k] for k in ("profile_offsets", "profile_t", "profile_source_m", "profile_center_bed_m"))
        monolithic, _ = design.solve_design_bed(a["node_xz_m"], a["receiver"], a["sparse_cell_xy"],
                                               a["vertices_xz_m"], a["triangles"], a["source_elevation_m"],
                                               a["design_minimum_cut_m"], a["design_maximum_cut_m"],
                                               self.terrain, 1.0, profile, 1e-5, width=a["width_m"])
        self.assertAlmostEqual(design._mesh_volume_chunked(a["vertices_xz_m"], a["triangles"], monolithic),
                               merged["metadata"]["cut_volume_m3"], places=8)
        self.assertTrue(np.all(a["cut_depth_m"][a["design_zero_boundary_vertex_mask"]] == 0))
        self.assertLessEqual(closure["maximum_gradient_residual_m_per_m"], 1e-8)
        self.assertLessEqual(closure["maximum_transverse_residual_m"], 1e-8)

    def test_touching_components_recompute_unique_shared_bed(self):
        points = np.array([[15., 20.], [20., 20.]])
        bundles = [self.bundle(points, [0, 1]), self.bundle(points, [2, 3])]
        with patch.object(design, '_i27_linprog', wraps=design._i27_linprog) as solver:
            merged = self.merge(bundles)
        self.assertEqual(solver.call_count, 1)
        self.assertEqual(merged["metadata"]["closure"]["support_group_count"], 1)
        self.assertEqual(merged["metadata"]["closure"]["reused_optimal_components"], 0)
        self.assertEqual(len(merged["arrays"]["sparse_cell_xy"]), len(bundles[0]["arrays"]["sparse_cell_xy"]))
        self.assertAlmostEqual(merged["metadata"]["cut_volume_m3"],
                               design._mesh_volume_chunked(bundles[0]["arrays"]["vertices_xz_m"],
                                                           bundles[0]["arrays"]["triangles"],
                                                           bundles[0]["arrays"]["cut_depth_m"]), places=8)

    def test_canonical_mesh_matches_scalar_order_for_unsorted_negative_cells(self):
        cells = np.array([[2, 1], [-2, -1], [0, 0], [1, 1], [-1, -1]], np.int32)
        corners = sorted({(x + ox, z + oz) for x, z in cells
                          for ox, oz in ((0, 0), (1, 0), (1, 1), (0, 1))},
                         key=lambda point: (point[1], point[0]))
        lookup = {point: index for index, point in enumerate(corners)}
        origin, spacing = np.array([3.25, -7.5]), .75
        from dataclasses import replace
        terrain = replace(self.terrain, x0_m=origin[0], z0_m=origin[1])
        expected_vertices = np.asarray([origin + spacing * np.asarray(point) for point in corners]
                                       + [origin + spacing * (cell + .5) for cell in cells])
        expected_faces = []
        for index, (x, z) in enumerate(cells):
            sw, se, ne, nw = (lookup[point] for point in ((x, z), (x+1, z), (x+1, z+1), (x, z+1)))
            center = len(corners) + index
            expected_faces.extend(((sw, se, center), (se, ne, center), (ne, nw, center), (nw, sw, center)))
        vertices, triangles = _sparse_mesh(cells, terrain, spacing, len(expected_vertices))
        np.testing.assert_array_equal(vertices, expected_vertices)
        np.testing.assert_array_equal(triangles, expected_faces)
        with self.assertRaisesRegex(ValueError, "vertex budget exceeded"):
            _sparse_mesh(cells, terrain, spacing, len(expected_vertices) - 1)

    def test_array_boundary_matches_scalar_exposed_corner_rule(self):
        cells = np.array([[1, 2], [0, 0], [2, 2], [1, 1], [89, 89], [88, 89]])
        vertices, _ = _sparse_mesh(cells, self.terrain, 1.0, 100)
        known = set(map(tuple, cells))
        lookup = {tuple(point): index for index, point in enumerate(vertices)}
        expected = set()
        for x, z in cells:
            faces = (((x-1, z), ((x, z), (x, z+1)), x > 0),
                     ((x+1, z), ((x+1, z), (x+1, z+1)), x+1 < 90),
                     ((x, z-1), ((x, z), (x+1, z)), z > 0),
                     ((x, z+1), ((x, z+1), (x+1, z+1)), z+1 < 90))
            for neighbor, corners, interior in faces:
                if interior and neighbor not in known:
                    expected.update(lookup[corner] for corner in corners)
        np.testing.assert_array_equal(design.interior_support_boundary_vertices(cells, vertices, self.terrain, 1.0),
                                      sorted(expected))

    def test_edge_and_corner_contacts_are_shared_support_groups(self):
        for second, expected in (((1, 0), 1), ((1, 1), 1), ((2, 2), 2)):
            with self.subTest(second=second):
                cells = np.array([[0, 0], second])
                vertices, _ = _sparse_mesh(cells, self.terrain, 1.0, 100)
                lookup = {tuple(p): i for i, p in enumerate(vertices)}
                supports = []
                for cell in cells:
                    local, _ = _sparse_mesh(cell[None], self.terrain, 1.0, 100)
                    mapping = np.array([lookup[tuple(p)] for p in local])
                    supports.append(({}, mapping, False))
                roots, _, _ = design._design_support_groups(supports, len(vertices), np.arange(len(vertices)),
                                                            eye(len(vertices), format="csr"))
                self.assertEqual(len(np.unique(roots)), expected)

    def test_global_radius_adds_rows_and_infeasible_old_optimum_falls_back(self):
        self.terrain = TerrainGrid(np.repeat((10.0 + .2*np.arange(4)*30.0)[:, None], 4, axis=1),
                                   np.ones((4, 4), bool), 0.0, 0.0, 30.0, 30.0,
                                   "observed_dem", "radius-groups", "b" * 64)
        bundles = [self.bundle(np.array([[15., 20.], [20., 20.]]), [0, 1], depth=2.5, padding=.5),
                   self.bundle(np.array([[65., 60.], [70., 60.]]), [2, 3])]
        old_rows = bundles[0]["metadata"]["closure"]["transverse_constraints"]
        with patch.object(design, '_i27_linprog', wraps=design._i27_linprog) as solver:
            merged = self.merge(bundles)
        closure = merged["metadata"]["closure"]
        self.assertEqual(closure["support_group_count"], 2)
        self.assertEqual(closure["reused_optimal_components"], 1)
        self.assertEqual(solver.call_count, 1)
        self.assertGreater(closure["transverse_constraints"], old_rows + bundles[1]["metadata"]["closure"]["transverse_constraints"])
        self.assertLessEqual(closure["maximum_transverse_residual_m"], 1e-8)

    def test_changed_bundle_config_does_not_reuse_old_optimum(self):
        bundles = [self.bundle(np.array([[15., 20.], [20., 20.]]), [0, 1])]
        bundles[0]["metadata"]["config"]["max_cut_m"] = 3.0
        with patch.object(design, '_i27_linprog', wraps=design._i27_linprog) as solver:
            merged = self.merge(bundles)
        self.assertEqual(solver.call_count, 1)
        self.assertEqual(merged["metadata"]["closure"]["reused_optimal_components"], 0)

    def test_missing_or_different_constraint_model_recomputes_same_config(self):
        bundle = self.bundle(np.array([[15., 20.], [20., 20.]]), [0, 1])
        for model in (None, "historical-full-circle-node-cap"):
            with self.subTest(model=model):
                if model is None:
                    bundle["metadata"]["closure"].pop("constraint_model")
                else:
                    bundle["metadata"]["closure"]["constraint_model"] = model
                with patch.object(design, '_i27_linprog', wraps=design._i27_linprog) as solver:
                    merged = self.merge([bundle])
                self.assertEqual(solver.call_count, 1)
                self.assertEqual(merged["metadata"]["closure"]["reused_optimal_components"], 0)
                self.assertEqual(merged["metadata"]["closure"]["constraint_model"],
                                 design.DESIGN_BED_CONSTRAINT_MODEL)


if __name__ == "__main__":
    unittest.main()
