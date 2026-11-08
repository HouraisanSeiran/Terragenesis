import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.channel_geometry import assess_local_bed, design_support_edges


class LocalBedAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.points = np.array([[0., 0.], [4., 0.], [0., 0.], [4., 0.]])
        self.receiver = np.array([1, -1, 3, -1])
        self.width = np.full(4, 2.)
        self.depth = np.full(4, .25)

    def test_exact_support_includes_overlap_ties_and_spacing_guard(self):
        point = np.array([2., 2.5])
        edges = design_support_edges(point, self.points, self.receiver, self.width,
                                     self.depth, 2., .26, .01)
        self.assertEqual([(source, target) for source, target, _ in edges], [(0, 1), (2, 3)])
        self.assertEqual(design_support_edges(point, self.points, self.receiver,
                         self.width, self.depth, .5, .26, .01), [])

    def test_nonmatching_lower_bound_cannot_invent_support(self):
        self.assertEqual(design_support_edges(np.array([2., 0.]), self.points,
            self.receiver, self.width, self.depth, 1., .5, .01), [])

    def test_adapter_uses_primitive_and_attributes_verified_dual_roots(self):
        model = dict(vertices=np.array([[2., 0.]]), bounds=np.array([[.26, 4.]]),
                     source_padding=np.array([.01]), transverse_radius_policy="relaxation",
                     boundary_policy="no artificial crop boundary")
        result = dict(status=2, outcome="infeasible", message="actual row conflict",
            variable_count=1, row_count=2, solver_calls=2,
            extra_cut=dict(certificate_valid=True, minimum_extra_ceiling_m=.02,
                           root_vertex_indices=[0], root_lower_bound_duals=[1.]))
        with patch('terrain_pipeline.channel_geometry.build_local', return_value=model) as build:
            with patch('terrain_pipeline.channel_geometry.assess_local', return_value=result) as solve:
                assessment = assess_local_bed(self.points, self.receiver, self.width,
                    self.depth, None, None, {}, spacing=2., max_cut=3.,
                    bottom_slope=.03, minimum_slope=2e-5)
        self.assertEqual(assessment["contributing_edges"], [(0, 1), (2, 3)])
        self.assertEqual(assessment["solver_calls"], 2)
        self.assertEqual(build.call_args.kwargs, dict(spacing=2., max_cut=3., bottom_slope=.03, minimum_slope=2e-5))
        self.assertEqual(solve.call_count, 1)

    def test_unverified_extra_cut_has_no_search_witness(self):
        model = dict(transverse_radius_policy="relaxation", boundary_policy="relaxation")
        result = dict(status=2, outcome="infeasible", message="conflict", variable_count=1,
                      row_count=2, extra_cut=dict(certificate_valid=False))
        with patch('terrain_pipeline.channel_geometry.build_local', return_value=model):
            with patch('terrain_pipeline.channel_geometry.assess_local', return_value=result):
                assessment = assess_local_bed(self.points, self.receiver, self.width,
                    self.depth, None, None, {}, spacing=1., max_cut=4.,
                    bottom_slope=.02, minimum_slope=1e-5)
        self.assertNotIn("contributing_edges", assessment)
        self.assertNotIn("extra_cut", assessment)


if __name__ == "__main__":
    unittest.main()
