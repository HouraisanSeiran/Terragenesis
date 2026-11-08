import copy
import unittest

import numpy as np

from tools.audit_hybrid_surface_composition_v2 import (
    NUMERICAL_POLICY, NUMERICAL_POLICY_SHA256, SLICE_SCHEMA, Solid, audit_exact_slice, check_shape, digest)

TRIANGLES = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
             [3, 7, 6], [3, 6, 2], [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5]]
FRAME = {"origin_local_xyz_m": [0., 0., 0.], "normal_local_xyz": [0., 0., 1.],
         "transverse_unit_xyz": [1., 0., 0.], "coordinate_convention": "local_XYZ_metres_Y_vertical"}
PIN = {"artifact": "tiny_saved_solid"}


def seal(record):
    record.pop("identity_sha256", None)
    record["identity_sha256"] = digest(record)
    return record


def box_vertices(left, bottom, right, top, depth=1.):
    return [[left, bottom, -depth], [right, bottom, -depth], [right, top, -depth], [left, top, -depth],
            [left, bottom, depth], [right, bottom, depth], [right, top, depth], [left, top, depth]]


def midpoint_fixture(left, bottom, right, top, offset=0, inward=False):
    middle_x, middle_y = (left + right) / 2, (bottom + top) / 2
    edges = [(0, 4), (0, 5), (1, 5), (1, 6), (2, 6), (3, 6), (3, 7), (0, 7)]
    points = [[left, bottom], [middle_x, bottom], [right, bottom], [right, middle_y],
              [right, top], [middle_x, top], [left, top], [left, middle_y]]
    names = ["e:" + str(first + offset) + ":" + str(second + offset) for first, second in edges]
    nodes = [{"node_id": name, "vertex_indices": [first + offset, second + offset],
              "point_local_xyz_m": [point[0], point[1], 0.], "point_uv_m": point}
             for name, (first, second), point in zip(names, edges, points)]
    segments = []
    support_indices = [5, 4, 11, 10, 7, 6, 9, 8]
    for index, ordinal in enumerate(support_indices):
        pair = [index, (index + 1) % 8]
        triangle = [value + offset for value in TRIANGLES[ordinal]]
        if inward:
            pair.reverse()
            triangle.reverse()
        segments.append({"triangle_index": ordinal + offset // 8 * 12, "vertex_indices": triangle,
            "intersection_node_ids": [names[value] for value in pair], "incident_halfspace": "both",
            "points_local_xyz_m": [nodes[value]["point_local_xyz_m"] for value in pair],
            "points_uv_m": [points[value] for value in pair]})
    loops = []
    loop_ids = names[::-1] if inward else names
    references = {tuple(sorted(segment["intersection_node_ids"])): [segment["triangle_index"]] for segment in segments}
    for side in ("positive", "negative"):
        loops.append({"side": side, "node_ids": loop_ids,
            "signed_area_m2": (right - left) * (top - bottom) * (-1 if inward else 1),
            "triangle_supports": [references[tuple(sorted(pair))]
                for pair in zip(loop_ids, loop_ids[1:] + loop_ids[:1])]})
    return nodes, segments, loops


def record_base():
    return {"schema": SLICE_SCHEMA, "mesh_pin": PIN,
        "method": "original_identity_cached_rational_mesh_plane_no_CrossSection",
        "numerical_policy": copy.deepcopy(NUMERICAL_POLICY), "numerical_policy_identity_sha256": NUMERICAL_POLICY_SHA256,
        "coordinate_convention": FRAME["coordinate_convention"],
        "coplanar_semantics": "closed_trace_contains_actual_original_facets_side_occupation_recorded"}


class SurfaceCompositionV2SavedAuditTests(unittest.TestCase):
    def test_shared_edges_holes_and_unsnapped_original_top(self):
        top = 3.0432591911956024
        vertices = box_vertices(-1., -1., 1., top) + box_vertices(-.25, -.25, .25, .25, .5)
        triangles = TRIANGLES + [[index + 8 for index in triangle[::-1]] for triangle in TRIANGLES]
        solid = Solid(vertices, triangles, "tiny saved cavity")
        nodes, segments, loops = midpoint_fixture(-1., -1., 1., top)
        inner_nodes, inner_segments, inner_loops = midpoint_fixture(-.25, -.25, .25, .25, 8, True)
        outer = [[-1., -1.], [1., -1.], [1., top], [-1., top]]
        hole = [[-.25, -.25], [-.25, .25], [.25, .25], [.25, -.25]]
        domain = {"polygons_uv_m": [outer], "holes_uv_m": [[hole]], "area_m2": 2 * (top + 1) - .25}
        record = record_base()
        record.update(**domain, intersection_nodes=nodes + inner_nodes, triangle_segments=segments + inner_segments,
            coplanar_triangle_supports=[], identity_loops=loops + inner_loops,
            vertex_plane_classifications=[{"vertex_index": index, "sign": -1 if index % 8 < 4 else 1,
                "classification_method": "exact_rational"} for index in range(16)],
            one_sided_interior_traces={side: copy.deepcopy(domain) for side in ("positive", "negative")},
            occupancy_witnesses=[{"point_uv_m": [.75, .75], "point_local_xyz_m": [.75, .75, 0.],
                "classification": "original_Mesh64_interior_two_ray_parities", "region": "retained_polygon", "ray_parities": [1, 1]},
                {"point_uv_m": [0., 0.], "point_local_xyz_m": [0., 0., 0.],
                 "classification": "original_Mesh64_void_two_ray_parities", "region": "excluded_hole", "ray_parities": [0, 0]}])
        shape, report = audit_exact_slice(seal(record), solid, FRAME, PIN)
        self.assertEqual(shape.bounds[3], top)
        self.assertEqual(len(shape.interiors), 1)
        self.assertEqual(report["independent_hole_occupancy_probes"], 1)
        self.assertFalse(report["builder_or_slicer_called"])
        changed = copy.deepcopy(record)
        changed["intersection_nodes"][4]["point_uv_m"][1] = float(np.nextafter(top, -np.inf))
        with self.assertRaisesRegex(ValueError, "shared-edge intersection"):
            audit_exact_slice(seal(changed), solid, FRAME, PIN)
        changed = copy.deepcopy(record)
        changed["identity_loops"].pop()
        with self.assertRaisesRegex(ValueError, "exhaust"):
            audit_exact_slice(seal(changed), solid, FRAME, PIN)
        changed = copy.deepcopy(record)
        changed["holes_uv_m"] = [[]]
        with self.assertRaisesRegex(ValueError, "holes differ"):
            audit_exact_slice(seal(changed), solid, FRAME, PIN)

    def test_coplanar_closed_boundary_retains_actual_occupied_side_and_policy(self):
        from shapely.geometry import GeometryCollection, LineString, Point, Polygon
        contact = {"polygons_uv_m": [], "holes_uv_m": [], "area_m2": 0.,
                   "contact_lines_uv_m": [[[0., 0.], [1., 0.]]], "contact_points_uv_m": [[2., 0.]]}
        touching = GeometryCollection([LineString([[0., 0.], [1., 0.]]), Point(2., 0.)])
        self.assertEqual(check_shape(contact, touching, "tiny contact", require_contacts=True), 0.)
        with self.assertRaisesRegex(ValueError, "components/holes"):
            check_shape(contact, GeometryCollection([touching, Polygon([[0., 1.], [1., 1.], [1., 2.]])]),
                        "tiny contact", require_contacts=True)
        changed_contact = {**contact, "contact_lines_uv_m": []}
        with self.assertRaisesRegex(ValueError, "contact lines"):
            check_shape(changed_contact, touching, "tiny contact", require_contacts=True)
        vertices = box_vertices(-1., -1., 1., 1.)
        solid = Solid(vertices, TRIANGLES, "tiny capped solid")
        frame = {**FRAME, "origin_local_xyz_m": [0., 0., 1.]}
        names = ["v:" + str(index) for index in range(4, 8)]
        nodes = [{"node_id": name, "vertex_indices": [index], "point_local_xyz_m": vertices[index],
                  "point_uv_m": vertices[index][:2]} for name, index in zip(names, range(4, 8))]
        segments = []
        for ordinal, first, second in ((5, 4, 5), (11, 5, 6), (6, 6, 7), (8, 7, 4)):
            segments.append({"triangle_index": ordinal, "vertex_indices": TRIANGLES[ordinal],
                "intersection_node_ids": ["v:" + str(first), "v:" + str(second)], "incident_halfspace": "negative",
                "points_local_xyz_m": [vertices[first], vertices[second]], "points_uv_m": [vertices[first][:2], vertices[second][:2]]})
        caps = [{"triangle_index": ordinal, "vertex_indices": TRIANGLES[ordinal],
                 "intersection_node_ids": ["v:" + str(index) for index in TRIANGLES[ordinal]],
                 "polygon_uv_m": [vertices[index][:2] for index in TRIANGLES[ordinal]],
                 "normal_dot_plane": 4., "occupied_incident_side": "negative"} for ordinal in (2, 3)]
        domain = {"polygons_uv_m": [[vertices[index][:2] for index in range(4, 8)]], "holes_uv_m": [[]], "area_m2": 4.}
        record = record_base()
        record.update(**domain, intersection_nodes=nodes, triangle_segments=segments, coplanar_triangle_supports=caps,
            identity_loops=[{"side": "negative", "node_ids": names, "signed_area_m2": 4., "triangle_supports": [[5], [11], [6], [8]]}],
            vertex_plane_classifications=[{"vertex_index": index, "sign": -1 if index < 4 else 0,
                "classification_method": "exact_rational"} for index in range(8)],
            one_sided_interior_traces={"negative": domain, "positive": {"polygons_uv_m": [], "holes_uv_m": [], "area_m2": 0.}},
            occupancy_witnesses=[{"point_uv_m": [0., 0.], "point_local_xyz_m": [0., 0., 1.],
                "classification": "original_oriented_coplanar_boundary_facet", "region": "retained_polygon",
                "coplanar_triangle_indices": [2, 3]}])
        shape, report = audit_exact_slice(seal(record), solid, frame, PIN)
        self.assertEqual(shape.area, 4.)
        self.assertEqual(report["coplanar_triangles"], 2)
        changed = copy.deepcopy(record)
        changed["coplanar_triangle_supports"][0]["occupied_incident_side"] = "positive"
        with self.assertRaisesRegex(ValueError, "coplanar facet"):
            audit_exact_slice(seal(changed), solid, frame, PIN)
        changed = copy.deepcopy(record)
        changed["numerical_policy"]["identity"] = "rounded_bucket"
        changed["numerical_policy_identity_sha256"] = digest(changed["numerical_policy"])
        with self.assertRaisesRegex(ValueError, "policy binding"):
            audit_exact_slice(seal(changed), solid, frame, PIN)
        with self.assertRaisesRegex(ValueError, "source/numerical"):
            audit_exact_slice(record, solid, frame, {"artifact": "other"})


if __name__ == "__main__":
    unittest.main()
