import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from scipy.sparse import coo_matrix

from terrain_pipeline.channel_geometry import _metric_channel_geometry_sample as _sample
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.channel_geometry import bed_constraints, design_cut_bounds, interior_support_boundary_vertices, transverse_bed_constraints
from terrain_pipeline.channel_geometry import _row_inside, assess_local, build_local
from terrain_pipeline.channel_geometry import _sparse_cells, _sparse_mesh


def signatures(matrix, kinds, limits, vertices):
    result = []
    for row in range(matrix.shape[0]):
        lo, hi = matrix.indptr[row:row + 2]
        ids, weights = matrix.indices[lo:hi], matrix.data[lo:hi]
        order = np.lexsort((vertices[ids, 0], vertices[ids, 1]))
        result.append((str(kinds[row]), tuple(map(tuple, vertices[ids[order]])),
                       tuple(weights[order]), float(limits[row])))
    return Counter(result)


class LocalDesignBedTests(unittest.TestCase):
    def fixture(self, points, receiver):
        x, z = np.meshgrid(np.arange(9.0), np.arange(9.0))
        terrain = TerrainGrid(20.0 - 0.1 * x + 0.003 * x * z,
                              np.ones((9, 9), bool), 0.0, 0.0, 10.0, 10.0,
                              "observed_dem", "local-model", "a" * 64)
        edges = np.flatnonzero(receiver >= 0)
        source = _sample(terrain.elevation_m, points, terrain)[0]
        bed = source - 1.0
        profile = (np.arange(0, 2 * len(edges) + 1, 2),
                   np.tile([0.0, 1.0], len(edges)),
                   np.column_stack((source[edges], source[receiver[edges]])).ravel(),
                   np.column_stack((bed[edges], bed[receiver[edges]])).ravel())
        return terrain, np.full(len(points), 4.0), np.full(len(points), 0.5), profile

    def full_model(self, points, receiver, terrain, width, depth, profile, parameters):
        spacing, max_cut = parameters["spacing"], parameters["max_cut"]
        edges = np.flatnonzero(receiver >= 0)
        radius = np.maximum(width[edges], width[receiver[edges]]) / 2.0 + (np.sqrt(2.0) + 1.0) * spacing + 2.0 * max_cut
        cells = _sparse_cells(points, receiver, width, profile,
                              SimpleNamespace(fine_spacing_m=spacing, max_vertices=100_000),
                              terrain, support_radius_m=radius)
        vertices, triangles = _sparse_mesh(cells, terrain, spacing, 100_000)
        source = _sample(terrain.elevation_m, vertices, terrain)[0]
        lower, upper, padding = design_cut_bounds(points, receiver, width, depth, cells,
                                                 vertices, triangles, terrain, spacing, max_cut)
        upper[interior_support_boundary_vertices(cells, vertices, terrain, spacing)] = 0.0
        base = bed_constraints(points, receiver, cells, vertices, triangles, source, terrain,
                               spacing, profile, parameters["minimum_slope"])
        transverse = transverse_bed_constraints(points, receiver, width, cells, vertices, triangles,
                                                source, terrain, spacing, upper, None, parameters["bottom_slope"])
        strips = len(transverse[2]) - transverse[3]
        rows = base + [(ids, weights, limit, "strip" if i < strips else "cap")
                       for i, (ids, weights, limit) in enumerate(zip(*transverse[:3]))]
        rr, cc, vv = [], [], []
        for row, (ids, weights, _, _) in enumerate(rows):
            rr.extend([row] * len(ids))
            cc.extend(ids)
            vv.extend(weights)
        matrix = coo_matrix((vv, (rr, cc)), shape=(len(rows), len(vertices))).tocsr()
        matrix.eliminate_zeros()
        return dict(matrix=matrix, vertices=vertices, source=source,
                    bounds=np.column_stack((lower, upper)), source_padding=padding,
                    limits=np.array([row[2] for row in rows]), kinds=np.array([row[3] for row in rows]))

    def test_cropped_bend_and_confluence_have_exact_full_rows_and_bounds(self):
        examples = (
            (np.array([[4.0, 8.0], [22.0, 18.0], [40.0, 32.0], [68.0, 32.0]]),
             np.array([1, 2, 3, -1]), [22.0, 18.0]),
            (np.array([[4.0, 18.0], [4.0, 26.0], [25.0, 22.0], [45.0, 22.0], [68.0, 22.0]]),
             np.array([2, 2, 3, 4, -1]), [25.0, 22.0]),
        )
        parameters = dict(spacing=0.5, max_cut=3.0, bottom_slope=0.03, minimum_slope=2e-5)
        for points, receiver, center in examples:
            with self.subTest(receiver=receiver):
                terrain, width, depth, profile = self.fixture(points, receiver)
                full = self.full_model(points, receiver, terrain, width, depth, profile, parameters)
                window = dict(center_xz_m=center, side_m=12.0)
                maximum = float(full["bounds"][:, 1].max())
                local = build_local(points, receiver, width, depth, profile, terrain, window,
                                    **parameters, maximum_depth=maximum)
                self.assertLess(local["selected_edges"], np.count_nonzero(receiver >= 0))
                inside = np.all(np.abs(full["vertices"] - center) <= 6.0, axis=1)
                keep = np.array([np.all(inside[full["matrix"].indices[lo:hi]])
                                 for lo, hi in zip(full["matrix"].indptr[:-1], full["matrix"].indptr[1:])])
                expected = signatures(full["matrix"][keep], full["kinds"][keep], full["limits"][keep], full["vertices"])
                actual = signatures(local["matrix"], local["kinds"], local["limits"], local["vertices"])
                self.assertEqual(actual, expected)
                self.assertTrue({"gradient", "profile", "strip"}.issubset(set(local["kinds"])))
                if len(receiver) == 4:
                    self.assertIn("cap", local["kinds"])
                lookup = {tuple(vertex): i for i, vertex in enumerate(full["vertices"])}
                mapping = np.array([lookup[tuple(vertex)] for vertex in local["vertices"]])
                for key in ("source", "bounds", "source_padding"):
                    np.testing.assert_array_equal(local[key], full[key][mapping])
                relaxed = build_local(points, receiver, width, depth, profile, terrain, window, **parameters)
                self.assertLessEqual(relaxed["transverse_maximum_depth"], maximum)
                relaxed_rows = signatures(relaxed["matrix"], relaxed["kinds"], relaxed["limits"], relaxed["vertices"])
                self.assertFalse(relaxed_rows - expected)
                self.assertTrue(np.all(relaxed["bounds"][:, 1] > 0.0))

    def test_duplicate_cancellation_uses_actual_nonzero_support(self):
        retained = np.array([True, False])
        self.assertTrue(_row_inside(np.array([0, 1, 1]), np.array([1.0, 2.0, -2.0]), retained))
        self.assertFalse(_row_inside(np.array([0, 1, 1]), np.array([1.0, 2.0, -1.0]), retained))

    def test_assessment_never_promotes_local_feasibility_or_time_limit(self):
        model = dict(matrix=coo_matrix([[1.0]]).tocsr(), limits=np.array([1.0]), bounds=np.array([[0.0, 1.0]]))
        for status, expected in ((0, "clear"), (2, "infeasible"), (1, "unknown")):
            with self.subTest(status=status), patch('terrain_pipeline.channel_geometry._i33_linprog',
                                                  return_value=SimpleNamespace(status=status, message="test", x=np.array([0.0]))):
                self.assertEqual(assess_local(model)["outcome"], expected)

    def test_actual_extra_cut_certificate_identifies_lower_bound_root(self):
        model = dict(matrix=coo_matrix([[-1.0, 1.0]]).tocsr(), limits=np.array([-0.5]),
                     bounds=np.array([[0.0, 1.0], [0.8, 1.0]]),
                     source_padding=np.zeros(2),
                     vertices=np.array([[0.0, 0.0], [1.0, 0.0]]))
        result = assess_local(model)
        self.assertEqual(result["outcome"], "infeasible")
        self.assertEqual(result["solver_calls"], 2)
        extra = result["extra_cut"]
        self.assertTrue(extra["certificate_valid"])
        self.assertTrue(extra["dual_finite"])
        self.assertAlmostEqual(extra["minimum_extra_ceiling_m"], 0.3)
        self.assertEqual(extra["root_vertex_indices"], [1])
        self.assertEqual(extra["root_lower_bound_duals"], [1.0])
        self.assertNotIn("lower_bound_duals", extra)

    def test_status_zero_needs_finite_feasible_primal_solution(self):
        model = dict(matrix=coo_matrix([[1.0]]).tocsr(), limits=np.array([0.5]), bounds=np.array([[0.0, 1.0]]))
        for solution in (None, np.array([np.nan]), np.array([np.inf]), np.array([1.1]), np.array([0.6])):
            with self.subTest(solution=solution), patch('terrain_pipeline.channel_geometry._i33_linprog',
                                                       return_value=SimpleNamespace(status=0, message="test", x=solution)):
                self.assertEqual(assess_local(model)["outcome"], "unknown")


if __name__ == "__main__":
    unittest.main()
