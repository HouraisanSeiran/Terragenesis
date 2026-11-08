import copy
import unittest

import numpy as np
from shapely.geometry import LineString, Polygon, box

from tools.audit_hybrid_river_faces import (
    Solid, audit_aperture, audit_slice, check_plane, triangle_plane_segments)


def frame():
    return {"origin_world_xyz_m": [100., 1350., 200.5], "origin_local_xyz_m": [0., 0., .5],
            "common_local_origin_xyz_m": [100., 1350., 200.], "normal_local_xyz": [0., 0., 1.],
            "transverse_unit_xyz": [1., 0., 0.], "transverse_unit_xz": [1., 0.],
            "vertical_unit_xyz": [0., 1., 0.], "coordinate_convention": "u_metres_Ylocal_metres_not_floor_relative",
            "positive_normal": "from_cell_to_cell_actual_horizontal_route"}


def boundary_record(shape):
    segments = []
    rings = [] if shape.is_empty else [shape.exterior, *shape.interiors]
    for ring in rings:
        for first, second in zip(list(ring.coords), list(ring.coords)[1:]):
            segments.append({"triangle_index": len(segments), "points_uv_m": [list(first), list(second)]})
    return {"triangle_segments": segments, "coplanar_triangle_supports": []}


def open_fixture():
    cutter, before = box(0, 0, 2, 3), box(-1, -1, 3, 1)
    shapes = {"cutter": cutter, "rock_before": before, "rock_after": before.difference(cutter),
              "removed": before.intersection(cutter)}
    slices = {role: boundary_record(shape) for role, shape in shapes.items()}
    parts = [([[0, 0], [2, 0]], "actual_rock_wet_wall"),
             ([[2, 0], [2, 1]], "actual_rock_wet_wall"),
             ([[2, 1], [2, 3]], "engineering_lateral_wall_above_terrain"),
             ([[2, 3], [0, 3]], "artificial_cutter_top_cap_not_wetted_wall"),
             ([[0, 3], [0, 1]], "engineering_lateral_wall_above_terrain"),
             ([[0, 1], [0, 0]], "actual_rock_wet_wall")]
    pieces = []
    for points, category in parts:
        line = LineString(points)
        sources = {role: [item["triangle_index"] for item in slices[role]["triangle_segments"]
                         if LineString(item["points_uv_m"]).intersection(line.buffer(1e-8)).length > 1e-8]
                   for role in ("cutter", "rock_after")}
        pieces.append({"points_uv_m": points, "points_local_xyz_m": [[point[0], point[1], .5] for point in points],
                       "category": category, "potential_wetted_length_m": line.length if category == "actual_rock_wet_wall" else None,
                       "source_triangle_indices": sources})
    top_refs = [item["triangle_index"] for item in slices["rock_before"]["triangle_segments"]
                if LineString(item["points_uv_m"]).intersection(LineString([[0, 1], [2, 1]])).length > 0]
    record = {"kind": "open_cut_floor", "polygon_uv_m": [[0, 0], [2, 0], [2, 3], [0, 3]],
              "polygon_local_xyz_m": [[0, 0, .5], [2, 0, .5], [2, 3, .5], [0, 3, .5]],
              "cut_floor_uv_m": [[0, 0], [2, 0]], "boundary_pieces": pieces,
              "terrain_opening_free_edges": [{"points_uv_m": [[0, 1], [2, 1]],
                 "category": "original_rock_top_opening_free_boundary_not_wall", "rock_before_triangle_indices": top_refs}],
              "blocked_area_m2": 0., "removed_replay_difference_area_m2": 0.,
              "actual_excavated_aperture_area_m2": 2., "cutter_outside_original_rock_area_m2": 4.,
              "bounded_display_aperture_area_m2": 6., "pressure_slot_enlarges_face": False,
              "closed_boundary_certified": False,
              "open_extension": {"kind": "explicit_engineering_vertical", "lateral_u_m": [0, 2],
                  "unbounded_above_cut_floor": False,
                  "unbounded_only_over_supported_free_top_intervals": [{"u_interval_m": [0, 2],
                      "lower_boundary_uv_m": [[2, 3], [0, 3]],
                      "kind": "above_saved_artificial_cap_only_not_above_actual_rock_roof"}],
                  "actual_rock_roof_segments_remain_bounded": True, "artificial_cutter_roof_is_not_flow_ceiling": True,
                  "extension_is_engineering_not_whole_physical_path_certification": True,
                  "not_actual_terrain_floodplain": True}}
    return record, slices, shapes


class SavedFaceAuditTests(unittest.TestCase):
    def test_source_cube_slice_and_plane_reject_fabricated_support(self):
        vertices = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                    [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]
        triangles = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                     [3, 7, 6], [3, 6, 2], [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5]]
        solid = Solid(vertices, triangles, "tiny saved cube")
        plane = frame()
        check_plane(plane, [100, 1350, 200.5], [0, 1], [100, 1350, 200])
        segments, coplanar = triangle_plane_segments(vertices, triangles, [0, 0, .5], [0, 0, 1], [1, 0, 0])
        self.assertEqual(len(segments), 8)
        self.assertEqual(coplanar, [])
        pin = {"path": "synthetic", "sha256": "synthetic"}
        record = {"mesh_pin": pin, "coordinate_convention": plane["coordinate_convention"],
                  "method": "Mesh64_transform_slice_exact_plane", "polygons_uv_m": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
                  "holes_uv_m": [[]], "area_m2": 1., "coplanar_triangle_supports": [], "triangle_segments": []}
        for ordinal, points in segments.items():
            record["triangle_segments"].append({"triangle_index": ordinal, "vertex_indices": triangles[ordinal],
                "points_uv_m": points.tolist(), "points_local_xyz_m": [[point[0], point[1], .5] for point in points]})
        shape, report = audit_slice(record, solid, plane, pin)
        self.assertAlmostEqual(shape.area, 1.)
        self.assertAlmostEqual(report["symmetric_difference_m2"], 0.)
        wrong = copy.deepcopy(record)
        wrong["triangle_segments"].pop()
        with self.assertRaisesRegex(ValueError, "triangle-plane support"):
            audit_slice(wrong, solid, plane, pin)
        wrong = copy.deepcopy(record)
        wrong["triangle_segments"][0]["points_uv_m"][0][1] += .1
        with self.assertRaisesRegex(ValueError, "fabricated triangle-plane"):
            audit_slice(wrong, solid, plane, pin)
        wrong_frame = copy.deepcopy(plane)
        wrong_frame["origin_local_xyz_m"][2] = .25
        with self.assertRaisesRegex(ValueError, "actual plane"):
            check_plane(wrong_frame, [100, 1350, 200.5], [0, 1], [100, 1350, 200])

    def test_open_cap_extension_wall_census_and_unknown_rejection(self):
        record, slices, shapes = open_fixture()
        report = audit_aperture(record, slices, shapes, frame())
        self.assertEqual(report["actual_rock_wall_length_m"], 4.)
        self.assertEqual(report["bounded_area_m2"], 6.)
        wrong = copy.deepcopy(record)
        wrong["boundary_pieces"][3]["category"] = "actual_rock_wet_wall"
        wrong["boundary_pieces"][3]["potential_wetted_length_m"] = 2.
        with self.assertRaisesRegex(ValueError, "artificial edge"):
            audit_aperture(wrong, slices, shapes, frame())
        wrong = copy.deepcopy(record)
        wrong["open_extension"]["unbounded_above_cut_floor"] = True
        with self.assertRaisesRegex(ValueError, "engineering open extension"):
            audit_aperture(wrong, slices, shapes, frame())
        wrong_shapes = {**shapes, "removed": Polygon()}
        with self.assertRaisesRegex(ValueError, "empty excavation"):
            audit_aperture(record, slices, wrong_shapes, frame())
        wrong = copy.deepcopy(record)
        wrong["pressure_slot_enlarges_face"] = True
        with self.assertRaisesRegex(ValueError, "storage slot"):
            audit_aperture(wrong, slices, shapes, frame())
        wrong = copy.deepcopy(record)
        wrong["boundary_pieces"].pop()
        with self.assertRaisesRegex(ValueError, "boundary pieces"):
            audit_aperture(wrong, slices, shapes, frame())


if __name__ == "__main__":
    unittest.main()
