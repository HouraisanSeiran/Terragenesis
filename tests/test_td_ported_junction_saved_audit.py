from copy import deepcopy
import unittest

import numpy as np

from tools.td_ported_junction_saved_audit import (
    audit_mesh, boundary_coverage, verify_outer_function,
    verify_reverse_ports, verify_shared_function, verify_fan_wet_vertices)


def triangle_order(points, indices):
    projected = np.asarray(points)[indices][:, [0, 2]]
    first, second = projected[1]-projected[0], projected[2]-projected[0]
    return indices if first[0]*second[1]-first[1]*second[0] > 0 else indices[::-1]


def three_port_fixture():
    inner_profiles, strips = [], []
    for angle in (0., 2*np.pi/3, 4*np.pi/3):
        radial = np.array([np.cos(angle), np.sin(angle)])
        normal = np.array([-radial[1], radial[0]])
        inner = [[point[0], 9.8, point[1]] for point in (2*radial+offset*normal for offset in (-.6, -.2, .2, .6))]
        outer = [[point[0], 9.8, point[1]] for point in (4*radial+offset*normal for offset in (-.6, -.2, .2, .6))]
        vertices = inner+outer
        triangles = [triangle_order(vertices, indices) for segment in range(3)
                     for indices in ([segment, segment+1, segment+4], [segment+1, segment+5, segment+4])]
        inner_profiles.append(inner)
        strips.append((vertices, triangles))
    ring = sorted([point for profile in inner_profiles for point in profile], key=lambda point: np.arctan2(point[2], point[0]))
    vertices = [[0., 9.8, 0.]]+ring
    triangles = [triangle_order(vertices, [0, index+1, (index+1)%len(ring)+1]) for index in range(len(ring))]
    return inner_profiles, strips, vertices, triangles


def hierarchy_fixture():
    arrays = dict(height_m=np.full((5, 5), 10.), valid_mask=np.ones((5, 5), bool),
                  protected_mask=np.zeros((5, 5), bool), open_boundary_mask=np.zeros((5, 5), bool),
                  cell_owner=np.zeros((5, 5), int), contribution_owner=np.zeros((5, 5), int),
                  node_unknown_contact=np.zeros(1, bool))
    return dict(arrays=arrays, metadata=dict(origin_m_xz=[0., 0.], spacing_m=1.))


class PortedJunctionSavedAuditTests(unittest.TestCase):
    def test_actual_three_full_ports_reverse_winding_and_no_overlap(self):
        profiles, strips, hub_vertices, hub_triangles = three_port_fixture()
        audit_mesh(hub_vertices, hub_triangles)
        all_vertices, all_triangles = list(hub_vertices), list(hub_triangles)
        for profile, (vertices, triangles) in zip(profiles, strips):
            hub_coverage, strip_coverage = verify_reverse_ports(hub_vertices, hub_triangles, vertices, triangles, profile)
            self.assertEqual(len(hub_coverage), 3)
            self.assertEqual(len(strip_coverage), 3)
            offset = len(all_vertices)
            all_vertices.extend(vertices)
            all_triangles.extend([[index+offset for index in triangle] for triangle in triangles])
        audit_mesh(all_vertices, all_triangles)
        declared_only = [[point[0]*.5, point[1], point[2]*.5] for point in profiles[0]]
        with self.assertRaises(ValueError):
            boundary_coverage(hub_vertices, hub_triangles, declared_only)
        with self.assertRaises(ValueError):
            audit_mesh(all_vertices, all_triangles+[all_triangles[0]])
        with self.assertRaises(ValueError):
            audit_mesh([[0., 10., 0.], [2., 10., 0.], [0., 10., 2.],
                        [.2, 10., .2], [1., 10., .2], [.2, 10., 1.]], [[0, 1, 2], [3, 4, 5]])

    def test_whole_native_functions_no_fill_maxcut_and_old_wet(self):
        hierarchy = hierarchy_fixture()
        fan = dict(vertices_xz_m=[[.25, .5], [2.25, .5], [.25, 1.5]],
                   depth_origin_xz_m=[.25, .5], depth_coefficients_m_1xz=[.2, 0., 0.],
                   depth_at_vertices_m=[.2, .2, .2])
        other = deepcopy(fan)
        verify_shared_function(hierarchy, {0}, fan, other, [.25, .5], [2.25, .5])
        verify_outer_function(hierarchy, {0}, fan, [.25, .5], [2.25, .5], [[.25, 9.8, .5], [2.25, 9.8, .5]])
        other["depth_coefficients_m_1xz"][0] += .025
        with self.assertRaises(ValueError):
            verify_shared_function(hierarchy, {0}, fan, other, [.25, .5], [2.25, .5])
        for illegal in (-.01, 4.01):
            invalid = deepcopy(fan)
            invalid["depth_coefficients_m_1xz"][0] = illegal
            invalid["depth_at_vertices_m"] = [illegal]*3
            with self.assertRaises(ValueError):
                verify_fan_wet_vertices(invalid, hierarchy, {0}, dict(covered_native_cell_ids=[], stage_by_leaf=[]))
        with self.assertRaises(ValueError):
            verify_fan_wet_vertices(fan, hierarchy, {0}, dict(covered_native_cell_ids=[5], stage_by_leaf=[]))


if __name__ == "__main__":
    unittest.main()
