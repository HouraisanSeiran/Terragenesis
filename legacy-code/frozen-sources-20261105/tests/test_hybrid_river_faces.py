"""Two bounded actual-solid slicing cases; no real face preparation or flow."""

import json
import unittest

import numpy as np
from shapely.geometry import Polygon

from terrain_pipeline.hybrid_river_faces import (
    classify_aperture, plane_frame, project, slice_solid, unproject)


class RiverFaceTests(unittest.TestCase):
    def test_library_oblique_plane_common_vertical_frame_and_actual_closed_void(self):
        import manifold3d as manifold
        normal = np.array([.6, 0., .8])
        frame = plane_frame([-178440., 1366., 68355.], normal[[0, 2]], [-178443., 1360., 68350.])
        basis = np.array([frame["transverse_unit_xyz"], frame["vertical_unit_xyz"], frame["normal_local_xyz"]])
        self.assertAlmostEqual(float(np.linalg.det(basis)), 1.)
        origin = np.array(frame["origin_local_xyz_m"])
        before = manifold.Manifold.cube([12., 12., 12.], center=True).translate(origin.tolist())
        cutter = manifold.Manifold.cube([2., 4., 16.], center=True)
        rotation = np.column_stack((basis.T, origin))
        cutter = cutter.transform(rotation.tolist())
        after, removed = before - cutter, before ^ cutter
        records, shapes = {}, {}
        for name, solid in {"cutter": cutter, "removed": removed, "rock_before": before, "rock_after": after}.items():
            mesh = solid.to_mesh64()
            data = (solid, np.array(mesh.vert_properties[:, :3], copy=True), np.array(mesh.tri_verts, dtype=int, copy=True))
            records[name], shapes[name] = slice_solid(data, frame, {"path": name, "sha256": "0" * 64})
            self.assertTrue(records[name]["triangle_segments"])
        result = classify_aperture(records, shapes, frame)
        self.assertEqual(result["kind"], "closed_polygon")
        self.assertAlmostEqual(result["bounded_display_aperture_area_m2"], 8., places=7)
        self.assertFalse(result["pressure_slot_enlarges_face"])
        self.assertTrue(all(piece["category"] == "actual_rock_wet_wall" for piece in result["boundary_pieces"]))
        uv = [[-1., 3.], [1., 7.]]
        local = unproject(uv, frame)
        np.testing.assert_allclose(project(local, frame), uv, atol=1e-12)
        np.testing.assert_array_equal(local[:, 1], [3., 7.])
        self.assertTrue(all(piece["source_triangle_indices"]["rock_after"] for piece in result["boundary_pieces"]))
        open_frame = plane_frame([0., 0., 0.], [0., 1.], [0., 0., 0.])
        before = manifold.Manifold.cube([8., 8., 12.], center=True).translate([0., -4., 0.])
        cutter = manifold.Manifold.cube([2., 3., 16.], center=True).translate([0., .5, 0.])
        records, shapes = {}, {}
        for name, solid in {"cutter": cutter, "removed": before ^ cutter, "rock_before": before, "rock_after": before - cutter}.items():
            mesh = solid.to_mesh64()
            records[name], shapes[name] = slice_solid((solid, np.array(mesh.vert_properties[:, :3], copy=True),
                np.array(mesh.tri_verts, dtype=int, copy=True)), open_frame, {"path": name, "sha256": "0" * 64})
        open_result = classify_aperture(records, shapes, open_frame)
        self.assertEqual(open_result["kind"], "open_cut_floor")
        self.assertFalse(open_result["open_extension"]["unbounded_above_cut_floor"])
        self.assertTrue(open_result["terrain_opening_free_edges"])
        self.assertTrue(open_result["open_extension"]["unbounded_only_over_supported_free_top_intervals"])
        self.assertTrue(any(piece["category"] == "artificial_cutter_top_cap_not_wetted_wall" for piece in open_result["boundary_pieces"]))
        self.assertEqual(json.loads(json.dumps(open_result, allow_nan=False)), open_result)

    def test_unknown_aperture_multiple_components_and_missing_support_refused(self):
        frame = plane_frame([0., 0., 0.], [0., 1.], [0., 0., 0.])
        square = Polygon([[-1., -1.], [1., -1.], [1., 1.], [-1., 1.]])
        records = {name: {"triangle_segments": [], "coplanar_triangle_supports": []}
            for name in ("cutter", "removed", "rock_before", "rock_after")}
        shapes = {"cutter": Polygon(), "removed": square, "rock_before": square, "rock_after": Polygon()}
        with self.assertRaisesRegex(ValueError, "unknown"):
            classify_aperture(records, shapes, frame)
        shapes["cutter"] = square.union(Polygon([[3., -1.], [5., -1.], [5., 1.], [3., 1.]]))
        with self.assertRaisesRegex(ValueError, "multiple"):
            classify_aperture(records, shapes, frame)
        shapes["cutter"] = square
        with self.assertRaisesRegex(ValueError, "support"):
            classify_aperture(records, shapes, frame)
        with self.assertRaisesRegex(ValueError, "plane"):
            plane_frame([0., 0., 0.], [0., 0.], [0., 0., 0.])


if __name__ == "__main__":
    unittest.main()
