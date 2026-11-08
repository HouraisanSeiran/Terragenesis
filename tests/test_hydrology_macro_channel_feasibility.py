import unittest

import numpy as np

from terrain_pipeline.hydrology_macro_channel_feasibility import (
    channel_section_intervals, fan4_source_weights, frozen_river_channel_feasibility_constraints,
)


class ChannelFeasibilityTests(unittest.TestCase):
    def fixture(self):
        receiver = np.full((3, 3), -1, int)
        receiver[1, 1] = 5
        return {"height_m": np.zeros((3, 3)), "receiver": receiver,
                "owner_domain_id": np.zeros((3, 3), int),
                "origin_xz_m": [-30., -30.], "spacing_m": 30.}

    def build(self, **kwargs):
        return frozen_river_channel_feasibility_constraints(self.fixture(), (21, 31),
            [-15., -15.], 2., np.ones((21, 31), bool), source_edges=[(4, 5)], **kwargs)

    def test_interval_elimination_matches_all_pairs(self):
        rng = np.random.default_rng(73)
        offsets = np.array([-13., -6., 0., 6., 13.])
        for _ in range(100):
            height = rng.uniform(-6., 6., len(offsets))
            lower, upper = channel_section_intervals(height, offsets, design_depth_m=.5)
            feasible = lower.max() <= upper.min()
            rhs = channel_section_intervals(np.zeros(len(offsets)), offsets, design_depth_m=.5)
            rows_feasible = np.all(height[:, None]-height[None, :] <= rhs[1][None, :]-rhs[0][:, None])
            self.assertEqual(feasible, rows_feasible)

    def test_tapered_minimum_and_padding_follow_fine_contract(self):
        half = 4 + np.sqrt(2.)
        lower, upper = channel_section_intervals(np.zeros(4), [0., half, half+.5, half+1.],
                                                 design_depth_m=.5, padding_m=.1)
        np.testing.assert_allclose(upper, [-.6, -.6, -.35, 0.])
        self.assertAlmostEqual(lower[0], -3.9)
        self.assertAlmostEqual(lower[-1], -3.9 - .02*half - .5)

    def test_matrix_rows_match_section_intervals_and_keep_terminals(self):
        result = self.build()
        z, x = np.mgrid[:21, :31]
        height = 20.+.4*x+.1*z
        actual = np.sum(height.ravel()[result["columns"]]*result["coefficients"], axis=1)
        pairs = np.asarray(result["sample_pairs_xz_m"])
        delta = pairs[:, 0]-pairs[:, 1]
        np.testing.assert_allclose(actual, .2*delta[:, 0]+.05*delta[:, 1], atol=1e-12)
        self.assertGreater(len(actual), 0)
        self.assertEqual(result["metadata"]["unsupported_sections"], 0)
        # Every terminal pixel is set above: rows must survive unchanged.
        dry = frozen_river_channel_feasibility_constraints(self.fixture(), (21,31), [-15.,-15.],
            2., np.zeros((21,31), bool), source_edges=[(4,5)])
        np.testing.assert_array_equal(dry["columns"], result["columns"])
        np.testing.assert_array_equal(dry["rhs"], result["rhs"])

    def test_support_gap_is_reported_and_budget_is_not_silently_truncated(self):
        result = frozen_river_channel_feasibility_constraints(self.fixture(), (8,31), [-15.,-5.],
            2., np.zeros((8,31), bool), source_edges=[(4,5)])
        self.assertEqual(result["metadata"]["unsupported_sections"], 3)
        self.assertEqual(result["columns"].shape, (0,8))
        self.assertTrue(result["metadata"]["unsupported_examples"])
        with self.assertRaisesRegex(ValueError, "constraint budget"):
            self.build(maximum_constraints=1)
        with self.assertRaisesRegex(ValueError, "section budget"):
            self.build(maximum_sections=1)

    def test_real_foreign_owner_is_rejected(self):
        owners = np.zeros((21,31), int)
        owners[1,8] = 2
        with self.assertRaisesRegex(ValueError, "another registered owner"):
            self.build(owner_domain_id=owners, ocean_mask=np.zeros(owners.shape, bool))

    def test_outer_support_samples_supply_floor_only(self):
        result = self.build()
        pairs = result["sample_pairs_xz_m"]
        centers = result["world_xz_m"]
        lower_offset = np.linalg.norm(pairs[:,0]-centers, axis=1)
        upper_offset = np.linalg.norm(pairs[:,1]-centers, axis=1)
        self.assertLessEqual(lower_offset.max(), result["metadata"]["rise_radius_m"]+1e-8)
        self.assertGreater(upper_offset.max(), result["metadata"]["rise_radius_m"]+.9)
        self.assertFalse(result["metadata"]["fine_lp_necessary_condition"])

    def test_minus_one_outlet_requires_registered_coarse_ocean(self):
        plan = self.fixture()
        plan["owner_domain_id"][1,2] = -1
        args = (plan, (21,31), [-15.,-15.], 2., np.ones((21,31), bool))
        with self.assertRaisesRegex(ValueError, "registered coarse ocean"):
            frozen_river_channel_feasibility_constraints(*args, source_edges=[(4,5)])
        plan["ocean_mask"] = plan["owner_domain_id"] == -1
        result = frozen_river_channel_feasibility_constraints(*args, source_edges=[(4,5)],
            owner_domain_id=np.full((21,31), -1), ocean_mask=np.ones((21,31),bool))
        self.assertGreater(len(result["rhs"]), 0)
        with self.assertRaisesRegex(ValueError, "another registered owner"):
            frozen_river_channel_feasibility_constraints(*args, source_edges=[(4,5)],
                owner_domain_id=np.full((21,31), -1), ocean_mask=np.zeros((21,31),bool))

    def test_diagonal_eight_column_rows_use_bilinear_samples(self):
        plan = self.fixture()
        plan["receiver"][1,1] = 8
        result = frozen_river_channel_feasibility_constraints(plan, (61,61), [-30.,-30.],
            1., np.zeros((61,61), bool), source_edges=[(4,8)], maximum_constraints=100000)
        self.assertEqual(result["columns"].shape[1], 8)
        np.testing.assert_allclose(result["coefficients"].sum(axis=1), 0., atol=1e-14)

    def test_fan4_weights_match_production_mesh_height_at_faces_and_boundaries(self):
        from terrain_pipeline.channel_geometry import _mesh_height
        native_height = np.array([[2., 7., 3.], [8., 19., 11.], [4., -3., 6.]])
        rng = np.random.default_rng(17)
        points = np.vstack((rng.uniform(0., 4., (50,2)), [[0.,0.],[4.,4.],[2.,2.],[2.,1.5],[1.25,1.25]]))
        for point in points:
            fine = np.minimum(np.floor(point).astype(int), 3)
            vertices = fine + np.array([[0.,0.],[1.,0.],[1.,1.],[0.,1.],[.5,.5]])
            triangles = np.array([[0,1,4],[1,2,4],[2,3,4],[3,0,4]])
            vertex_height = []
            for vertex in vertices:
                cell = np.minimum(np.floor(vertex/2).astype(int), 1)
                x, z = vertex/2-cell
                cx, cz = cell
                vertex_height.append((1-x)*(1-z)*native_height[cz,cx]+x*(1-z)*native_height[cz,cx+1]
                    +(1-x)*z*native_height[cz+1,cx]+x*z*native_height[cz+1,cx+1])
            ids, weights = fan4_source_weights(point, (3,3), [0.,0.], 2., 1.)
            actual = np.dot(native_height.ravel()[ids], weights)
            expected = _mesh_height(point, 0, vertices, triangles, np.asarray(vertex_height))
            self.assertAlmostEqual(actual, expected, places=12)
        with self.assertRaisesRegex(ValueError, "divide"):
            fan4_source_weights([0.,0.], (3,3), [0.,0.], 2., .7)


if __name__ == "__main__":
    unittest.main()
