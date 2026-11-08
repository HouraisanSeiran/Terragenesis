import unittest

import numpy as np

from tools.audit_hybrid_surface_composition import (
    Solid, audit_material_solids, exact_fan_cut, manifold_library, saved_patch_affine_depth)


def box_solid(low, high, label):
    vertices = [[low[0], low[1], low[2]], [high[0], low[1], low[2]],
                [high[0], high[1], low[2]], [low[0], high[1], low[2]],
                [low[0], low[1], high[2]], [high[0], low[1], high[2]],
                [high[0], high[1], high[2]], [low[0], high[1], high[2]]]
    triangles = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                 [3, 7, 6], [3, 6, 2], [0, 4, 7], [0, 7, 3], [1, 2, 6], [1, 6, 5]]
    return Solid(vertices, triangles, label)


def saved_solid(manifold, label):
    mesh = manifold.to_mesh64()
    return Solid(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts, dtype=np.int64), label)


class SurfaceCompositionSavedAuditTests(unittest.TestCase):
    def test_exact_edge_membership_without_negative_depth_or_outside_clamp(self):
        fan = {"vertices_xz_m": [[0., 0.], [10., 0.], [0., 10.]], "depth_at_vertices_m": [0., 1., 2.]}
        self.assertLess(1 - 8 / 10 - 2 / 10, 0.)
        self.assertEqual(exact_fan_cut(fan, [8., 2.]), 1.2)
        self.assertIsNone(exact_fan_cut(fan, [8., np.nextafter(2., np.inf)]))
        self.assertEqual(exact_fan_cut(fan, [0., 0.]), 0.)
        patch_function = {**fan, "depth_coefficients_m_1xz": [0., .1, .2], "depth_origin_xz_m": [0., 0.]}
        self.assertAlmostEqual(saved_patch_affine_depth(patch_function, [8., np.nextafter(2., np.inf)]), 1.2)
        self.assertEqual(saved_patch_affine_depth(patch_function, [10., 0.]), 1.)
        with self.assertRaisesRegex(ValueError, "strict original patch"):
            saved_patch_affine_depth(patch_function, [-1., -1.])
        with self.assertRaisesRegex(ValueError, "invalid saved fan"):
            exact_fan_cut({**fan, "depth_at_vertices_m": [0., -.01, 2.]}, [8., 2.])

    def test_saved_boolean_increment_uses_only_remaining_rock_and_rejects_double_cut(self):
        library = manifold_library()
        original = box_solid([0, 0, 0], [4, 3, 4], "original rock")
        gallery = box_solid([1, 0, 1], [2, 2, 3], "original gallery")
        surface = box_solid([1, 1, 1], [3, 4, 3], "surface cutter")
        rock, cave, carve = [solid.manifold(library) for solid in (original, gallery, surface)]
        old_after = saved_solid(rock - cave, "old after")
        old_removed = saved_solid(rock ^ cave, "old removed")
        combined = saved_solid(cave + carve, "combined cutter")
        actual = saved_solid(rock - (cave + carve), "actual after")
        extra = saved_solid((rock - cave) ^ carve, "extra removed")
        total = saved_solid(rock ^ (cave + carve), "total removed")
        report = audit_material_solids(original, old_after, old_removed, surface, combined, actual, extra, total, gallery)
        self.assertAlmostEqual(report["original_removed_m3"], 4.)
        self.assertAlmostEqual(report["extra_removed_m3"], 6.)
        self.assertAlmostEqual(report["total_removed_m3"], 10.)
        self.assertAlmostEqual(report["actual_added_rock_difference_m3"], 0.)
        with self.assertRaisesRegex(ValueError, "extra removed"):
            audit_material_solids(original, old_after, old_removed, surface, combined, actual, total, total, gallery)


if __name__ == "__main__":
    unittest.main()
