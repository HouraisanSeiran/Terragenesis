import unittest

import numpy as np

from tools.audit_td_native_channel_path_continuity import certify_corridor, certify_stencils


class ContinuousPathTests(unittest.TestCase):
    def topology(self):
        return dict(valid_mask=np.ones((8, 8), bool), protected_mask=np.zeros((8, 8), bool),
                    open_boundary_mask=np.zeros((8, 8), bool),
                    contribution_owner=np.zeros((8, 8), np.int64), node_parent=np.array([-1], np.int64))

    def test_segment_certificates_and_grid_splits(self):
        points = np.array([[.2, .2], [6.8, 4.8]])
        result = certify_corridor(points, points, 2.)
        self.assertGreater(result["certified_subsegments"], 1)
        self.assertLessEqual(result["maximum_certified_distance_upper_m"], 2.)
        result = certify_stencils(points, self.topology(), [0., 0.], 1.)
        self.assertGreater(result["constant_stencil_intervals"], 6)
        self.assertEqual(result["leaf_owner"], 0)

    def test_endpoint_minimum_false_positive_rejected(self):
        original = np.array([[-1., 1.], [-1., -10.], [1., -10.], [1., 1.]])
        rendered = np.array([[-.8, 1.], [.6, 1.]])
        self.assertLess(min(.2, .4) + 1.4 / 2, .95)
        with self.assertRaisesRegex(ValueError, "leaves original corridor"):
            certify_corridor(rendered, original, .95)

    def test_intermediate_barriers_and_leaf_rejected(self):
        points = np.array([[.2, .2], [6.8, .2]])
        for name in ("protected_mask", "open_boundary_mask", "valid_mask"):
            topology = self.topology()
            topology[name][0, 3] = name != "valid_mask"
            with self.assertRaisesRegex(ValueError, "stencil crosses"):
                certify_stencils(points, topology, [0., 0.], 1.)
        topology = self.topology()
        topology["node_parent"] = np.array([-1, -1], np.int64)
        topology["contribution_owner"][:, 3:] = 1
        with self.assertRaisesRegex(ValueError, "stencil crosses|basin leaves"):
            certify_stencils(points, topology, [0., 0.], 1.)

    def test_nonleaf_and_budget_rejected(self):
        points = np.array([[.2, .2], [6.8, .2]])
        topology = self.topology()
        topology["node_parent"] = np.array([-1, 0], np.int64)
        with self.assertRaisesRegex(ValueError, "not a leaf"):
            certify_stencils(points, topology, [0., 0.], 1.)
        with self.assertRaisesRegex(ValueError, "budget"):
            certify_stencils(points, self.topology(), [0., 0.], 1., max_checks=2)
        with self.assertRaisesRegex(ValueError, "budget"):
            certify_corridor(points, points, 1., max_checks=2)

    def test_gridline_segment_and_grid_crossing_stencil(self):
        points = np.array([[2., .2], [2., 6.8]])
        topology = self.topology()
        result = certify_stencils(points, topology, [0., 0.], 1.)
        self.assertEqual(result["leaf_owner"], 0)
        topology["protected_mask"][3, 3] = True
        with self.assertRaisesRegex(ValueError, "stencil crosses"):
            certify_stencils(points, topology, [0., 0.], 1.)


if __name__ == "__main__":
    unittest.main()
