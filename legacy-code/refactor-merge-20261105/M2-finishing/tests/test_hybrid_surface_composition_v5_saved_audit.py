from fractions import Fraction
import unittest

import mpmath
from mpmath.ctx_iv import MPIntervalContext

from tools.hybrid_exact_solid_saved_audit import ExactSolid
from tools.hybrid_interval_winding_saved_audit import IntervalSolid, POLICY_SHA256, TOLERANCE, exact_bounds


class SurfaceCompositionV5SavedAuditTests(unittest.TestCase):
    def test_thin_saved_solid_has_certified_interior_and_void_without_global_mutation(self):
        vertices = [[0., 0., 0.], [1., 0., 0.], [0., 1e-12, 0.], [0., 0., 1.]]
        triangles = [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]
        original = ExactSolid(vertices, triangles, "tiny thin original")
        queries = []
        wrapper = IntervalSolid(original, {"path": "tiny immutable mesh", "sha256": "a" * 64}, queries)
        before = mpmath.iv.dps
        self.assertEqual(wrapper.winding([.2, 2e-13, .2]), 1.)
        self.assertEqual(wrapper.winding([2., 2e-13, 2.]), 0.)
        self.assertEqual(mpmath.iv.dps, before)
        self.assertEqual(wrapper.vertices.tolist(), vertices)
        self.assertEqual(wrapper.triangles.tolist(), triangles)
        self.assertEqual(wrapper.signed_volume, original.signed_volume)
        for query in queries:
            lower, upper = Fraction(query["lower_rational"]), Fraction(query["upper_rational"])
            target = query["certified_target"]
            self.assertTrue(query["verified"])
            self.assertLess(target - TOLERANCE, lower)
            self.assertLess(upper, target + TOLERANCE)
            self.assertEqual(query["policy_identity_sha256"], POLICY_SHA256)

    def test_exact_boundary_and_vertex_refused_and_library_bounds_are_not_rounded_float_proof(self):
        solid = ExactSolid([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
                           [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], "tiny")
        queries = []
        wrapper = IntervalSolid(solid, {"sha256": "b" * 64}, queries)
        with self.assertRaisesRegex(ValueError, "exact triangle boundary"):
            wrapper.winding([.25, .25, 0.])
        with self.assertRaisesRegex(ValueError, "touches saved vertex"):
            wrapper.winding([0., 0., 0.])
        self.assertTrue(all(not query["verified"] and "error" in query for query in queries))
        budget_queries = [{} for _ in range(512)]
        budget_limited = IntervalSolid(solid, {"sha256": "c" * 64}, budget_queries)
        with self.assertRaisesRegex(ValueError, "query budget"):
            budget_limited.winding([.2, .2, .2])
        self.assertFalse(budget_queries[-1]["verified"])
        context = MPIntervalContext()
        context.dps = 50
        lower, upper = exact_bounds(context.mpf(1) / context.mpf(3))
        self.assertLess(lower, Fraction(1, 3))
        self.assertLess(Fraction(1, 3), upper)
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            exact_bounds(context.mpf(["-inf", "inf"]))


if __name__ == "__main__":
    unittest.main()
