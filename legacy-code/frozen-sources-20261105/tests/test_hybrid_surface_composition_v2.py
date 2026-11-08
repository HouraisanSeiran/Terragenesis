"""Two tiny unquantized mesh-plane cases; never run actual preparation or flow."""

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from shapely.geometry import GeometryCollection, LineString, Point, Polygon

from terrain_pipeline.hybrid_cave_geometry import manifold_from_record, mesh_record
from terrain_pipeline.hybrid_mesh_plane import slice_solid, triangle_supports
from terrain_pipeline.hybrid_river_faces import plane_frame
from terrain_pipeline.hybrid_river_faces import seal
from terrain_pipeline.hybrid_surface_composition_v2 import _domain
from tools.prepare_hybrid_surface_composition_v2 import refused_from_stage
from tools.prepare_hybrid_surface_composition import save


def box():
    left, right = -3.1160651283571497, 3.1160651283571497
    bottom, top = -.06256177661430229, 3.0432591911956024
    vertices = [[left, bottom, -1.], [right, bottom, -1.], [right, top, -1.], [left, top, -1.],
        [left, bottom, 1.], [right, bottom, 1.], [right, top, 1.], [left, top, 1.]]
    triangles = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
        [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]
    record = mesh_record(vertices, triangles, [0., 0., 0.], "tiny_original_box")
    return record, Polygon([[left, bottom], [right, bottom], [right, top], [left, top]])


class SurfaceCompositionV2Tests(unittest.TestCase):
    def test_quantized_top_band_exact_shared_edges_and_holes(self):
        import manifold3d as manifold
        record, expected = box()
        solid = manifold_from_record(record)
        mesh = solid.to_mesh64()
        points, triangles = np.asarray(mesh.vert_properties[:, :3]), np.asarray(mesh.tri_verts)
        frame = plane_frame([0., 0., 0.], [0., 1.], [0., 0., 0.])
        result, shape = slice_solid((solid, points, triangles), frame, {"fixture": "box"})
        self.assertEqual(shape.bounds, expected.bounds)
        self.assertEqual(expected.difference(shape).area, 0.)
        old_shape = Polygon(solid.slice(0.).to_polygons()[0])
        self.assertGreater(expected.difference(old_shape).area, 1e-8)
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
        self.assertEqual(len({node["node_id"] for node in result["intersection_nodes"]}), len(result["intersection_nodes"]))
        self.assertTrue(all(item["ray_parities"] == [1, 1] for item in result["occupancy_witnesses"]))
        hollow = manifold.Manifold.cube([4., 4., 4.], center=True) - manifold.Manifold.cube([1., 1., 6.], center=True)
        mesh = hollow.to_mesh64()
        saved, domain = slice_solid((hollow, np.asarray(mesh.vert_properties[:, :3]), np.asarray(mesh.tri_verts)), frame, {"fixture": "hole"})
        self.assertAlmostEqual(domain.area, 15.)
        self.assertEqual(len(domain.interiors), 1)
        self.assertEqual(len(saved["holes_uv_m"][0]), 1)
        self.assertTrue(any(item.get("ray_parities") == [0, 0] for item in saved["occupancy_witnesses"]))

    def test_coplanar_closed_and_one_sided_semantics_and_unknown_refusal(self):
        record, expected = box()
        solid = manifold_from_record(record)
        points, triangles = np.asarray(record["vertices_local_xyz_m"]), np.asarray(record["triangles"])
        frame = plane_frame([0., 0., 1.], [0., 1.], [0., 0., 0.])
        result, shape = slice_solid((solid, points, triangles), frame, {"fixture": "exact_cap"})
        self.assertAlmostEqual(shape.area, expected.area)
        self.assertEqual(result["one_sided_interior_traces"]["positive"]["area_m2"], 0.)
        self.assertAlmostEqual(result["one_sided_interior_traces"]["negative"]["area_m2"], expected.area)
        self.assertTrue(all(item["occupied_incident_side"] == "negative" for item in result["coplanar_triangle_supports"]))
        with self.assertRaisesRegex(ValueError, "identity_graph"):
            slice_solid((solid, points, triangles[:-1]), plane_frame([0., 0., 0.], [0., 1.], [0., 0., 0.]), {"fixture": "open"})
        segments, caps = triangle_supports(points, triangles, frame)
        self.assertEqual(caps, result["coplanar_triangle_supports"])
        self.assertEqual(segments, result["triangle_segments"])
        line, point = LineString([[0., 0.], [1., 0.]]), Point(2., 0.)
        contact = _domain(GeometryCollection([line, point]))
        self.assertEqual(contact["area_m2"], 0.)
        self.assertEqual(contact["contact_lines_uv_m"], [[[0., 0.], [1., 0.]]])
        self.assertEqual(contact["contact_points_uv_m"], [[2., 0.]])
        mixed = _domain(GeometryCollection([expected, GeometryCollection([line, point])]))
        self.assertEqual(mixed["area_m2"], expected.area)
        self.assertEqual(len(mixed["polygons_uv_m"]), 1)
        self.assertEqual(json.loads(json.dumps(mixed, allow_nan=False)), mixed)
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory)
            stage = {"schema": "td-hybrid-surface-composition-v2", "status": "boolean_stage_unverified",
                "material": {"extra_removed_m3": 1.25}, "original_source_sampling_cut_lookup_mismatches": [{"saved_cut_depth_m": 0.}]}
            checkpoint = seal({"composition_stage": stage, "material": stage["material"]})
            save(staging / "checkpoint_boolean.json", checkpoint, staging / "published/checkpoint_boolean.json")
            refused = refused_from_stage(staging, staging / "published", AttributeError("exterior"))
            self.assertEqual(refused["status"], "refused")
            self.assertEqual(refused["material"], stage["material"])
            self.assertEqual(refused["original_source_sampling_cut_lookup_mismatches"], stage["original_source_sampling_cut_lookup_mismatches"])
            self.assertTrue(refused["boolean_stage_preserved"])
            self.assertTrue((staging / "checkpoint_boolean.json").exists())
            self.assertFalse(refused["portal_connections"]["sink"]["two_sided_complete_port_verified"])
            self.assertEqual(json.loads(json.dumps(refused, allow_nan=False)), refused)


if __name__ == "__main__":
    unittest.main()
