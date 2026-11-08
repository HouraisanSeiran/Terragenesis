"""Two bounded rational-collapse/hierarchy cases; no actual stage preparation."""

from fractions import Fraction
import json
import unittest

import numpy as np

from terrain_pipeline.hybrid_geometry import _side, _trace, ceil_fraction, hybrid_mesh_plane_mechanism_2_slice_solid as slice_solid
from terrain_pipeline.hybrid_geometry import plane_frame


def loop_data(points):
    nodes = {"v:" + str(index): {"node_id": "v:" + str(index), "point_uv_m": list(map(float, point)),
        "rational_uv_m": list(map(str, point))} for index, point in enumerate(points)}
    ids = list(nodes)
    segments = [{"triangle_index": ordinal, "intersection_node_ids": [first, second], "incident_halfspace": "both"}
        for ordinal, (first, second) in enumerate(zip(ids, ids[1:] + ids[:1]))]
    return nodes, segments


class SurfaceCompositionV3Tests(unittest.TestCase):
    def test_exact_orientation_identity_collapse_and_certified_full_loop(self):
        frame = plane_frame([0., 0., 0.], [0., 1.], [0., 0., 0.])
        adjacent = np.nextafter(1., np.inf)
        points = [[1., 1., 1.], [adjacent, 1., -1.], [1., adjacent, -1.]]
        nodes, segments, _, _, collapses = _trace(points, [[0, 1, 2]], frame)
        self.assertEqual(len(segments), 1)
        self.assertEqual(len(collapses), 1)
        self.assertGreater(Fraction(segments[0]["orientation_rational"]), 0)
        first, second = [nodes[index] for index in segments[0]["intersection_node_ids"]]
        self.assertNotEqual(first["rational_uv_m"], second["rational_uv_m"])
        self.assertEqual(first["point_uv_m"], second["point_uv_m"])
        half = Fraction(1, 2)
        ring = [[Fraction(0), Fraction(0)], [Fraction(1), Fraction(0)], [Fraction(1), half],
            [Fraction(1), half + Fraction(1, 10**30)], [Fraction(1), Fraction(1)], [Fraction(0), Fraction(1)]]
        loop_nodes, loop_segments = loop_data(ring)
        shape, loops = _side(loop_nodes, loop_segments, "positive")
        self.assertEqual(shape.area, 1.)
        self.assertEqual(len(loops[0]["node_ids"]), 6)
        self.assertEqual(len(loops[0]["display_loop_node_ids"]), 5)
        self.assertTrue(loops[0]["hierarchy_certified"])
        certificate = loops[0]
        error = Fraction(certificate["maximum_projection_distance_l1_rational"])
        perimeter = Fraction(certificate["display_perimeter_l1_rational"])
        bound = Fraction(certificate["projection_area_bound_rational"])
        self.assertGreaterEqual(bound, 2 * error * perimeter)
        self.assertGreaterEqual(Fraction(certificate["conservative_projection_area_bound_m2"]), bound)
        self.assertGreaterEqual(Fraction(ceil_fraction(Fraction(1, 10))), Fraction(1, 10))
        self.assertEqual(json.loads(json.dumps(loops, allow_nan=False)), loops)

    def test_positive_area_projection_loss_refused_and_holes_preserved(self):
        import manifold3d as manifold
        tiny = Fraction(1, 10**30)
        nodes, segments = loop_data([[Fraction(1), Fraction(1)], [Fraction(1) + tiny, Fraction(1)],
            [Fraction(1), Fraction(1) + tiny]])
        with self.assertRaisesRegex(ValueError, "projection_not_certified"):
            _side(nodes, segments, "positive")
        frame = plane_frame([0., 0., 0.], [0., 1.], [0., 0., 0.])
        hollow = manifold.Manifold.cube([4., 4., 4.], center=True) - manifold.Manifold.cube([1., 1., 6.], center=True)
        mesh = hollow.to_mesh64()
        record, domain = slice_solid((hollow, np.asarray(mesh.vert_properties[:, :3]), np.asarray(mesh.tri_verts)), frame, {"fixture": "hole"})
        self.assertEqual(domain.area, 15.)
        self.assertEqual(len(domain.interiors), 1)
        exact_bound = sum(Fraction(loop["projection_area_bound_rational"]) for loop in record["identity_loops"])
        exact_bound += sum(Fraction(cap["projection_certificate"]["projection_area_bound_rational"])
            for cap in record["coplanar_triangle_supports"])
        self.assertEqual(Fraction(record["projection_area_error_bound_rational"]), exact_bound)
        self.assertGreaterEqual(Fraction(record["projection_area_error_bound_m2"]), exact_bound)
        self.assertTrue(any(item.get("ray_parities") == [0, 0] for item in record["occupancy_witnesses"]))
        self.assertEqual(json.loads(json.dumps(record, allow_nan=False)), record)


if __name__ == "__main__":
    unittest.main()
