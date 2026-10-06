from copy import deepcopy
import unittest

import numpy as np

from tools.audit_td_fine_bed_shards import digest
from tools.td_source_conforming_saved_audit import native_edge_polynomial
from tools.td_source_conforming_saved_audit_v3 import (
    POLICY, constrained_depths, incident_constraints, legacy_line_polynomial,
    verify_incident_fans, verify_v3proof)


def hierarchy_fixture():
    heights = np.tile([10., 10.1, 10.225, 10.4], (4, 1))
    arrays = dict(height_m=heights, valid_mask=np.ones((4, 4), bool),
                  protected_mask=np.zeros((4, 4), bool), open_boundary_mask=np.zeros((4, 4), bool),
                  cell_owner=np.zeros((4, 4), int), contribution_owner=np.zeros((4, 4), int),
                  node_unknown_contact=np.zeros(1, bool))
    return dict(arrays=arrays, metadata=dict(origin_m_xz=[0., 0.], spacing_m=1.))


def proof_fixture(hierarchy, start=(1., 0.), end=(2., 0.)):
    source = native_edge_polynomial(hierarchy, {0}, start, end)["source_height_polynomial_m"]
    points = [[0., 9.9, 0.], [3., 10.2, 0.]]
    old = legacy_line_polynomial(points, start, end)
    depths = (np.asarray(source)-old)[:2]
    neighbor = dict(triangle_id="legacy06:0", edge_index=0, bed_coefficients_m_t012=old.tolist())
    proof = dict(segment_id="native", start_xz_m=list(start), end_xz_m=list(end),
                 sides=[dict(triangle_id="legacy06:0", edge_index=0, points_xyz_m=points)],
                 depth_coefficients_m_t01=depths.tolist())
    proof["v3proof"] = dict(policy_identity_sha256=digest(POLICY), depth_rule="native_source_minus_legacy_line_v3",
                            unchanged_neighbor_polynomials=[neighbor],
                            whole_coefficient_differences_m_t012=[dict(triangle_id="legacy06:0", edge_index=0,
                                                                     difference_coefficients_m_t012=[0., 0., source[2]])],
                            proposed_depth_coefficients_m_t01=depths.tolist())
    return proof, source


class SavedAuditV3Tests(unittest.TestCase):
    def test_native_legacy_coefficients_and_shared_incident_fan_knots(self):
        hierarchy = hierarchy_fixture()
        proof, source = proof_fixture(hierarchy)
        verify_v3proof(proof, source, digest(POLICY))
        registry, conflicts = incident_constraints({"native": proof}, hierarchy, {0})
        values = constrained_depths([1., 0.], [2., 0.], [.133333333333, .166666666667], registry, conflicts)
        np.testing.assert_allclose(values, [.1, .125], atol=1e-12, rtol=0)
        stale = deepcopy(proof)
        stale["depth_coefficients_m_t01"] = [.1, .05]
        stale["v3proof"]["proposed_depth_coefficients_m_t01"] = [.1, .05]
        with self.assertRaises(ValueError):
            verify_v3proof(stale, source, digest(POLICY))
        center = np.array([1.5, 1.])
        first = np.array([center, [1., 0.], [2., 0.]])
        second = np.array([center, [2., 0.], [2., 1.]])
        coefficients = np.array([.2, .025, .0875])
        fans = [(first, center, coefficients, "first"), (second, center, coefficients, "second")]
        verify_incident_fans(fans)
        with self.assertRaisesRegex(ValueError, "incident fan knot crack"):
            verify_incident_fans([fans[0], (second, center, coefficients+np.array([.025, 0., 0.]), "cracked")])

    def test_refused_quadratic_witness_is_not_geometry_acceptance(self):
        hierarchy = hierarchy_fixture()
        proof, source = proof_fixture(hierarchy)
        curved = np.asarray(source)+[0., 0., .025]
        proof["v3proof"]["whole_coefficient_differences_m_t012"][0]["difference_coefficients_m_t012"] = [0., 0., .025]
        proof["depth_coefficients_m_t01"] = None
        verify_v3proof(proof, curved, digest(POLICY), require_match=False)
        with self.assertRaises(ValueError):
            verify_v3proof(proof, curved, digest(POLICY), require_match=True)
        forged = deepcopy(proof)
        forged["v3proof"]["whole_coefficient_differences_m_t012"][0]["difference_coefficients_m_t012"] = [0., 0., 0.]
        with self.assertRaises(ValueError):
            verify_v3proof(forged, curved, digest(POLICY), require_match=False)
        with self.assertRaises(ValueError):
            constrained_depths([1., 0.], [2., 0.], [.1, .125], {(100000000, 0): [(np.array([1., 0.]), .1)]}, {(100000000, 0)})


if __name__ == "__main__":
    unittest.main()
