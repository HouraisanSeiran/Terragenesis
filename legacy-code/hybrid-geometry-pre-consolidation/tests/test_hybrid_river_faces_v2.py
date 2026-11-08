"""Two self-contained solid/polygon cases; no actual preparation or hydraulics."""

import unittest

import numpy as np
from shapely.geometry import LineString, Polygon

from terrain_pipeline.hybrid_cave_geometry import sweep_triangles
from terrain_pipeline.hybrid_river_faces import lower_floor, slice_solid as legacy_slice_solid
from terrain_pipeline.hybrid_river_faces_v2 import (
    classify_aperture, plane_frame, role_slice, seal, slice_solid, surface_role_sources, vdm_role_source)


def fixture():
    import manifold3d as manifold
    ring = [[1., 0.], [0., -.2], [-1., 0.], [-1., .0023], [-1.0023, .0023], [-1.0023, 2.], [1., 2.]]
    stations = [{"station_id": "station:" + str(ordinal), "floor_vertex_count": 5,
                 "origin_xyz_m": [0., 0., depth], "transverse_unit_xz": [1., 0.],
                 "derived_ring_xyz_m": [[point[0], point[1], depth] for point in ring]}
                for ordinal, depth in enumerate((-2., 2.))]
    vdm = {"stations": stations, "triangles": sweep_triangles(stations)}
    points = np.array([station["derived_ring_xyz_m"] for station in stations]).reshape(-1, 3)
    triangles = np.array(vdm["triangles"], dtype=np.uint64)
    solid = manifold.Manifold(manifold.Mesh64(np.array(points, order="C"), np.array(triangles, order="C")))
    if solid.volume() < 0:
        triangles = triangles[:, ::-1].copy()
        vdm["triangles"] = triangles.tolist()
        solid = manifold.Manifold(manifold.Mesh64(np.array(points, order="C"), np.array(triangles, order="C")))
    if solid.is_empty() or solid.volume() <= 0:
        raise ValueError("invalid self-contained swept fixture")
    mesh = seal({"vertices_local_xyz_m": points.tolist(), "triangles": triangles.tolist(), "local_origin_xyz_m": [0., 0., 0.]})
    frame = plane_frame([0., 0., 0.], [0., 1.], [0., 0., 0.])
    source = vdm_role_source(vdm, mesh, [0., 0., 0.], {"path": "source-fixture", "sha256": "0" * 64})
    return solid, frame, role_slice(source, frame), mesh, vdm


def slices_for(cutter, before, frame):
    records, shapes = {}, {}
    for name, solid in {"cutter": cutter, "rock_before": before, "rock_after": before - cutter, "removed": before ^ cutter}.items():
        mesh = solid.to_mesh64()
        records[name], shapes[name] = slice_solid((solid, np.array(mesh.vert_properties[:, :3], copy=True),
                                                 np.array(mesh.tri_verts, copy=True)), frame,
                                                {"path": name + "-fixture", "sha256": "0" * 64})
    return records, shapes


class ActualPolygonFaceTests(unittest.TestCase):
    def test_exact_mesh64_top_precision_cached_roles_and_actual_polygon(self):
        import manifold3d as manifold
        top = 3.0432591911956024
        initial = manifold.Manifold.cube([6.23213, 4., 2.], center=True).to_mesh64()
        points = np.array(initial.vert_properties[:, :3], copy=True)
        points[:, 1] = np.where(points[:, 1] > 0, top, -1.)
        triangles = np.array(initial.tri_verts, dtype=np.uint64, copy=True)
        solid = manifold.Manifold(manifold.Mesh64(np.array(points, order="C"), np.array(triangles, order="C")))
        frame = plane_frame([0., 0., 0.], [0., 1.], [0., 0., 0.])
        data = (solid, points, triangles)
        pin = {"path": "precision-fixture", "sha256": "0" * 64}
        record, actual = slice_solid(data, frame, pin)
        legacy, quantized = legacy_slice_solid(data, frame, pin)
        self.assertEqual(actual.bounds[3], top)
        self.assertGreater(actual.difference(quantized).area, 1e-8)
        self.assertEqual(record["schema"], "td-hybrid-exact-mesh-plane-slice-v2")
        self.assertTrue(record["display_projection_certified"])
        self.assertLessEqual(record["projection_area_error_bound_m2"], 1e-8)
        self.assertTrue(all("rational_xyz_m" in node and "rational_uv_m" in node
                            for node in record["intersection_nodes"]))
        role_source = {"mesh_pin": pin, "points_local_xyz_m": points, "triangles": triangles,
                       "role_rule": "precision_fixture",
                       "triangle_roles": [{"triangle_index": ordinal, "source_role": "lateral"}
                                          for ordinal in range(len(triangles))]}
        roles = role_slice(role_source, frame)
        for saved, role in zip(record["triangle_segments"], roles["triangle_segments"]):
            self.assertEqual(saved["intersection_node_ids"], role["intersection_node_ids"])
            self.assertEqual(saved["points_uv_m"], role["points_uv_m"])
        self.assertEqual(roles["numerical_policy_identity_sha256"], record["numerical_policy_identity_sha256"])
        next_coordinate = np.nextafter(1., np.inf)
        collapsed_source = {"mesh_pin": pin, "role_rule": "synthetic_distinct_rational_same_display",
                            "points_local_xyz_m": np.array([[1., 1., 1.], [next_coordinate, 1., -1.],
                                                             [1., next_coordinate, -1.]]),
                            "triangles": np.array([[0, 1, 2]]),
                            "triangle_roles": [{"triangle_index": 0, "source_role": "lateral"}]}
        collapsed = role_slice(collapsed_source, frame)["triangle_segments"][0]
        self.assertNotEqual(*collapsed["intersection_node_ids"])
        self.assertEqual(*collapsed["points_uv_m"])
        self.assertNotEqual(*collapsed["rational_points_uv_m"])
        self.assertNotEqual(collapsed["orientation_rational"], "0")
        self.assertIn(collapsed["exact_orientation_sign"], (-1, 1))
        local_origin = [-179000., 1350., 68000.]
        local_points = [[.25, 0., 0.], [1., 0., 0.], [.25, 0., 1.],
                        [.25, 2., 0.], [1., 2., 0.], [.25, 2., 1.]]
        prism = seal({"vertices_local_xyz_m": local_points, "triangles": [[0, 1, 2]] * 8,
                      "local_origin_xyz_m": local_origin})
        bottom = {"prism": prism, "prism_triangle_roles": ["floor", "artificial_top_cap"] + ["lateral"] * 6,
                  "bottom_vertices_xyz_m": (np.asarray(local_points[:3]) + local_origin).tolist(),
                  "bottom_triangle_id": "fixture:0", "fan_key": "fixture",
                  "source_function_identity_sha256": "0" * 64}
        prisms = {"half_arms": {kind: {"bottom_triangles": [bottom]} for kind in ("sink", "spring")}}
        for saved_source in surface_role_sources(prisms, local_origin, pin):
            self.assertTrue(np.array_equal(saved_source["points_local_xyz_m"], np.asarray(local_points)))
        cutter, frame, source, mesh, vdm = fixture()
        before = manifold.Manifold.cube([6., 5., 6.], center=True).translate([0., -2., 0.])
        records, shapes = slices_for(cutter, before, frame)
        with self.assertRaisesRegex(ValueError, "cut_floor_not_actual"):
            lower_floor(shapes["cutter"])
        result = classify_aperture(records, shapes, [source], frame)
        self.assertEqual(result["kind"], "open_actual_polygon")
        self.assertTrue(result["polygon_authoritative"])
        self.assertFalse(result["floor_height_function_required"])
        floor = [piece for piece in result["boundary_pieces"] if piece["source_role"] == "floor"]
        vertical_length = sum(LineString(piece["points_uv_m"]).length for piece in floor
                              if abs(piece["points_uv_m"][0][0] - piece["points_uv_m"][-1][0]) < 1e-12)
        self.assertAlmostEqual(vertical_length, .0023, delta=1e-8)
        roof = [piece for piece in result["boundary_pieces"] if piece["source_role"] == "roof"]
        self.assertTrue(all(piece["category"] == "artificial_cutter_top_cap_not_wetted_wall" for piece in roof))
        self.assertFalse(result["pressure_slot_enlarges_face"])
        first = manifold.Manifold.cube([.5, 5., 6.], center=True).translate([-.65, -2., 0.])
        second = manifold.Manifold.cube([.5, 5., 6.], center=True).translate([.65, -2., 0.])
        records, shapes = slices_for(cutter, first + second, frame)
        self.assertEqual(shapes["removed"].geom_type, "MultiPolygon")
        result = classify_aperture(records, shapes, [source], frame)
        self.assertEqual(result["material_component_count"], 2)
        self.assertTrue(result["material_components_do_not_certify_fluid_connectivity"])
        self.assertEqual(Polygon(result["polygon_uv_m"]).geom_type, "Polygon")

    def test_blocking_cap_missing_two_sided_role_support_and_multiple_fluid_refused(self):
        import manifold3d as manifold
        cutter, frame, source, mesh, vdm = fixture()
        before = manifold.Manifold.cube([6., 5., 6.], center=True).translate([0., -2., 0.])
        records, shapes = slices_for(cutter, before, frame)
        profile = [point["points_uv_m"] for point in source["triangle_segments"] if point["source_role"] == "floor"][0]
        with self.assertRaisesRegex(ValueError, "two_sided"):
            classify_aperture(records, shapes, [source], frame, profile, {"two_sided_complete_port_verified": False})
        blocked = dict(shapes)
        blocked["rock_after"] = shapes["rock_after"].union(shapes["cutter"])
        with self.assertRaisesRegex(ValueError, "no_cap_deletion"):
            classify_aperture(records, blocked, [source], frame, profile, {"two_sided_complete_port_verified": True})
        uncertain = {name: {**record, "projection_area_error_bound_m2": 0.}
                     for name, record in records.items()}
        uncertain["cutter"]["projection_area_error_bound_m2"] = 6e-9
        uncertain["rock_after"]["projection_area_error_bound_m2"] = 6e-9
        with self.assertRaisesRegex(ValueError, "no_cap_deletion"):
            classify_aperture(uncertain, shapes, [source], frame)
        with self.assertRaisesRegex(ValueError, "source_role"):
            classify_aperture(records, shapes, [], frame)
        multiple = dict(shapes)
        multiple["cutter"] = shapes["cutter"].union(Polygon([[3., 0.], [4., 0.], [4., 1.], [3., 1.]]))
        with self.assertRaisesRegex(ValueError, "multiple"):
            classify_aperture(records, multiple, [source], frame)
        changed = {**mesh, "vertices_local_xyz_m": [[point[0] + .01, point[1], point[2]] for point in mesh["vertices_local_xyz_m"]]}
        with self.assertRaisesRegex(ValueError, "immutable_station"):
            vdm_role_source(vdm, changed, [0., 0., 0.], {})


if __name__ == "__main__":
    unittest.main()
