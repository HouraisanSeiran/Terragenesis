import copy
from fractions import Fraction
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from tools import audit_hybrid_surface_composition_v3 as audit
from tools.hybrid_exact_solid_saved_audit import ExactSolid


class SurfaceCompositionV3SavedAuditTests(unittest.TestCase):
    def test_exact_positive_facets_retained_with_area_volume_and_true_zero_refused(self):
        vertices = [[0., 0., 0.], [1., 0., 0.], [0., 1e-20, 0.], [0., 0., 1.]]
        triangles = [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]
        solid = ExactSolid(vertices, triangles, "tiny positive original facets")
        evidence = solid.validation_evidence
        self.assertEqual(evidence["retained_triangle_count"], 4)
        self.assertEqual(evidence["deleted_triangle_count"], 0)
        self.assertEqual(evidence["exact_zero_triangle_count"], 0)
        self.assertEqual(len(evidence["triangle_area_le_1e_minus14_m2_ids"]), 2)
        self.assertEqual(evidence["minimum_positive_area_m2_approx"], 5e-21)
        self.assertEqual(solid.exact_signed_volume, Fraction.from_float(1e-20) / 6)
        self.assertTrue(evidence["all_original_faces_retained"])
        self.assertEqual(solid.triangles.tolist(), triangles)
        changed = copy.deepcopy(vertices)
        changed[2] = [0., 0., 0.]
        with self.assertRaisesRegex(ValueError, "exact-zero"):
            ExactSolid(changed, triangles)
        with self.assertRaisesRegex(ValueError, "nonpositive exact"):
            ExactSolid(vertices, [triangle[::-1] for triangle in triangles])
        changed_faces = copy.deepcopy(triangles)
        changed_faces[0].reverse()
        with self.assertRaisesRegex(ValueError, "orientation"):
            ExactSolid(vertices, changed_faces)

    def test_rational_identity_collapse_certificate_hierarchy_and_partial_refusal(self):
        frame = {"origin_local_xyz_m": [0., 0., 0.], "normal_local_xyz": [0., 0., 1.], "transverse_unit_xyz": [1., 0., 0.]}
        source = SimpleNamespace(vertices=np.asarray([[1., 1., 1.], [1., np.nextafter(1., np.inf), 1.],
                                                      [1., 1., -2.**-60]]), triangles=np.asarray([[0, 1, 2]]))
        nodes, segments, _, _ = audit.independent_triangle_trace(source, frame)
        segment = segments[0]
        self.assertEqual(segment["points_uv_m"][0], segment["points_uv_m"][1])
        self.assertNotEqual(segment["rational_points_uv_m"][0], segment["rational_points_uv_m"][1])
        self.assertGreater(Fraction(segment["orientation_rational"]), 0)
        self.assertEqual(segment["exact_orientation_sign"], 1)
        self.assertIn("orientation_before_reversal_rational", segment)
        self.assertEqual(len(nodes), 2)
        exact = [[Fraction(-1), Fraction(-1)], [Fraction(1), Fraction(-1)], [Fraction(1), Fraction(1)],
                 [Fraction(1) - Fraction(1, 2**56), Fraction(1)], [Fraction(-1), Fraction(1)]]
        names = ["v:" + str(index) for index in range(5)]
        loop_nodes = {name: {"rational_uv_m": list(map(str, point)), "point_uv_m": list(map(float, point))}
                      for name, point in zip(names, exact)}
        loop_segments = {index: {"intersection_node_ids": [name, names[(index + 1) % 5]], "incident_halfspace": "both"}
                         for index, name in enumerate(names)}
        display_ids = [names[index] for index in (0, 1, 2, 4)]
        area = audit.rational_area(exact)
        error = 2.**-56
        exact_bound = 16 * Fraction.from_float(error) + Fraction.from_float(math.nextafter(math.pi, math.inf)) * Fraction.from_float(error)**2
        rounded_bound = float(exact_bound)
        if Fraction.from_float(rounded_bound) < exact_bound:
            rounded_bound = math.nextafter(rounded_bound, math.inf)
        loop = {"side": "positive", "node_ids": names, "display_loop_node_ids": display_ids,
            "triangle_supports": [[index] for index in range(5)], "signed_area_m2_rational": str(area),
            "signed_area_m2": float(area), "display_signed_area_m2_rational": "4", "area_error_m2": 0.,
            "maximum_projection_distance_m": error, "conservative_projection_area_bound_m2": rounded_bound,
            "maximum_projection_distance_l1_rational": str(Fraction.from_float(error)),
            "display_perimeter_l1_rational": "8", "projection_area_bound_rational": str(exact_bound),
            "containment_query_uv_rational": ["0", "0"], "exact_parent_loop_index": None,
            "display_parent_loop_index": None, "hierarchy_certified": True}
        shape, bound = audit.certified_side([loop], "positive", loop_nodes, loop_segments)
        self.assertEqual(shape.area, 4.)
        self.assertLess(bound, 1e-8)
        self.assertEqual(bound, exact_bound)
        self.assertGreaterEqual(Fraction.from_float(loop["conservative_projection_area_bound_m2"]), bound)
        self.assertEqual(audit.area_upper(0., 0.), math.nextafter(0., math.inf))
        changed = copy.deepcopy(loop)
        changed["projection_area_bound_rational"] = "0"
        with self.assertRaisesRegex(ValueError, "certificate"):
            audit.certified_side([changed], "positive", loop_nodes, loop_segments)
        changed = copy.deepcopy(loop)
        changed["node_ids"].remove(names[3])
        with self.assertRaises(ValueError):
            audit.certified_side([changed], "positive", loop_nodes, loop_segments)
        changed = copy.deepcopy(loop)
        changed["display_parent_loop_index"] = 0
        with self.assertRaisesRegex(ValueError, "hierarchy"):
            audit.certified_side([changed], "positive", loop_nodes, loop_segments)
        with self.assertRaisesRegex(ValueError, "self-intersecting"):
            audit.check_rational_boundaries([[[Fraction(0), Fraction(0)], [Fraction(2), Fraction(2)],
                                               [Fraction(0), Fraction(2)], [Fraction(2), Fraction(0)]]])

        def failed_after_material(pin, progress):
            progress.update(native_half_arm_sources_verified=True, materials_verified=True,
                            material={"independent_boolean_verified": True})
            raise ValueError("saved whole port refused")

        with patch.object(audit, "audit_complete", side_effect=failed_after_material):
            report = audit.audit({"path": "unused-tiny", "sha256": "unused-tiny"})
        self.assertEqual(report["status"], "refused")
        self.assertTrue(report["native_half_arm_sources_verified"])
        self.assertTrue(report["materials_verified"])
        self.assertFalse(report["two_sided_complete_port_verified"])
        self.assertFalse(report["hydraulic_constitutive_law_accepted"])


if __name__ == "__main__":
    unittest.main()
