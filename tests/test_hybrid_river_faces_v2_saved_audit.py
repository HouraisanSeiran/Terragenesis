import copy
import unittest

import numpy as np

from terrain_pipeline.hybrid_cave_geometry import mesh_record
from terrain_pipeline.hybrid_river_faces import plane_frame
from terrain_pipeline.hybrid_river_faces_v2 import role_slice, surface_role_sources
from tools.audit_hybrid_river_faces_v2 import audit_role_slice, topology_roles


class FaceRoleAuditTests(unittest.TestCase):
    def test_topological_roles_do_not_depend_on_slanted_side_slope(self):
        ring = [[-3, 1, 0], [-2, 0, 0], [0, -.1, 0], [2, 0, 0], [3, 1, 0],
                [3.02, 3, 0], [-3.02, 3, 0]]
        stations = [{"derived_ring_xyz_m": [[point[0], point[1], station] for point in ring],
                     "floor_vertex_count": 5} for station in range(17)]
        triangles = [[0, 1, 8], [4, 5, 12], [5, 6, 13], [6, 0, 7], [0, 2, 1]]
        vdm = {"stations": stations, "triangles": triangles}
        mesh = {"local_origin_xyz_m": [0, 0, 0], "triangles": triangles,
                "vertices_local_xyz_m": [point for station in stations for point in station["derived_ring_xyz_m"]]}
        roles = topology_roles(vdm, mesh)
        self.assertEqual([item["source_role"] for item in roles], ["floor", "lateral", "roof", "lateral", "endcap"])
        wrong = copy.deepcopy(mesh)
        wrong["vertices_local_xyz_m"][5][0] += .1
        with self.assertRaises(ValueError):
            topology_roles(vdm, wrong)

    def test_nonadjacent_sweep_and_interior_cap_are_refused(self):
        stations = [{"derived_ring_xyz_m": [[offset, offset % 2, station] for offset in range(4)],
                     "floor_vertex_count": 2} for station in range(17)]
        for triangle in ([0, 1, 9], [4, 5, 6]):
            vdm = {"stations": stations, "triangles": [triangle]}
            mesh = {"local_origin_xyz_m": [0, 0, 0], "triangles": [triangle],
                    "vertices_local_xyz_m": [point for station in stations for point in station["derived_ring_xyz_m"]]}
            with self.assertRaises(ValueError):
                topology_roles(vdm, mesh)

    def test_exact_role_identities_and_incident_sides_cannot_be_forged(self):
        vertices = [[0., 0., 0.], [2., 0., 0.], [0., 0., 2.],
                    [0., 2., 0.], [2., 2., 0.], [0., 2., 2.]]
        triangles = [[0, 1, 2], [3, 5, 4], [0, 3, 1], [1, 3, 4],
                     [1, 4, 2], [2, 4, 5], [2, 5, 0], [0, 5, 3]]
        mesh = mesh_record(vertices, triangles, [0., 0., 0.], "fixture")
        bottom = {"prism": mesh, "prism_triangle_roles": ["floor", "artificial_top_cap"] + ["lateral"] * 6,
                  "bottom_triangle_id": 0, "fan_key": "fixture", "source_function_identity_sha256": "0" * 64,
                  "bottom_vertices_xyz_m": vertices[:3]}
        prisms = {"half_arms": {"sink": {"bottom_triangles": [bottom]}, "spring": {"bottom_triangles": []}}}
        pin = {"path": "fixture", "sha256": "0" * 64}
        source = surface_role_sources(prisms, np.zeros(3), pin)[0]
        for depth in (1., 0.):
            frame = plane_frame([0., 0., depth], [0., 1.], [0., 0., 0.])
            record = role_slice(source, frame)
            audit_role_slice(record, frame, None, None, None, prisms, pin)
            for field, value in (("intersection_node_ids", ["forged", "forged"]),
                                 ("incident_halfspace", "forged"),
                                 ("points_local_xyz_m", [[0., 0., 0.], [0., 0., 0.]]),
                                 ("points_uv_m", [[0., 0.], [0., 0.]])):
                changed = copy.deepcopy(record)
                changed["triangle_segments"][0][field] = value
                with self.assertRaises(ValueError):
                    audit_role_slice(changed, frame, None, None, None, prisms, pin)
            if record["coplanar_triangle_supports"]:
                for field, value in (("intersection_node_ids", ["forged"] * 3),
                                     ("normal_dot_plane", 0.), ("occupied_incident_side", "forged")):
                    changed = copy.deepcopy(record)
                    changed["coplanar_triangle_supports"][0][field] = value
                    with self.assertRaises(ValueError):
                        audit_role_slice(changed, frame, None, None, None, prisms, pin)


if __name__ == "__main__":
    unittest.main()
