from copy import deepcopy
import unittest

import numpy as np

from tools.td_ported_junction_saved_audit_v3 import reconstructed_depths

FIRST = [-179130., 68008.44166471517]
LAST = [-179104.0104261543, 68007.3263825638]
DEPTH = .6909995322273517


def fixture():
    arrays = dict(height_m=np.zeros((4, 4)), valid_mask=np.ones((4, 4), bool),
                  protected_mask=np.zeros((4, 4), bool), open_boundary_mask=np.zeros((4, 4), bool),
                  cell_owner=np.zeros((4, 4), int), contribution_owner=np.zeros((4, 4), int),
                  node_unknown_contact=np.zeros(1, bool))
    hierarchy = dict(arrays=arrays, metadata=dict(origin_m_xz=[-179160., 67980.], spacing_m=30.))
    vertices = [[FIRST[0], -DEPTH, FIRST[1]], [LAST[0], 0., LAST[1]], [FIRST[0], -.1, FIRST[1]+1.]]
    faces = {"junction:0": dict(vertices_xyz_m=vertices)}
    proof = dict(start_xz_m=FIRST, end_xz_m=LAST,
                 boundary_condition="shared_incident_native_knot_depth_v3",
                 depth_support_knots=[dict(xz_m=point, original_vertex_refs=[dict(
                     triangle_id="junction:0", edge_index=0, xyz_m=vertex)])
                     for point, vertex in zip((FIRST, LAST), vertices[:2])],
                 v3proof=dict(knot_constraints=[None, None]))
    return proof, faces, dict(selected_leaf_ids=[0]), hierarchy


class ExactSupportEndpointTests(unittest.TestCase):
    def test_real_segment42_exact_endpoints_keep_independently_rebuilt_zero(self):
        proof, faces, record, hierarchy = fixture()
        points = np.asarray([FIRST, LAST])
        vector = points[1]-points[0]
        fractions = (points-points[0])@vector/(vector@vector)
        self.assertGreaterEqual(fractions[1], 1.)
        depths = reconstructed_depths(proof, {}, faces, record, hierarchy)
        np.testing.assert_array_equal(depths, [DEPTH, 0.])
        nearby_not_exact = deepcopy(proof)
        nearby_not_exact["end_xz_m"] = (points[1]+vector*1e-10).tolist()
        with self.assertRaisesRegex(ValueError, "strict nonnegative/maxcut"):
            reconstructed_depths(nearby_not_exact, {}, faces, record, hierarchy)

    def test_true_negative_original_support_depth_remains_refused(self):
        proof, faces, record, hierarchy = fixture()
        faces["junction:0"]["vertices_xyz_m"][1][1] = .025
        proof["depth_support_knots"][1]["original_vertex_refs"][0]["xyz_m"][1] = .025
        with self.assertRaisesRegex(ValueError, "original support source invalid/negative"):
            reconstructed_depths(proof, {}, faces, record, hierarchy)


if __name__ == "__main__":
    unittest.main()
