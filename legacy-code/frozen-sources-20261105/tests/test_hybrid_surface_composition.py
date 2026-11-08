"""Two tiny source/Boolean cases, never prepare actual geometry or flow."""

import json
import unittest

from terrain_pipeline.hybrid_surface_composition import canonical_boundary_witness, exact_depth, saved_patch_depth, triangular_prism, volume_ledger
from terrain_pipeline.hybrid_cave_geometry import manifold_from_record


class SurfaceCompositionTests(unittest.TestCase):
    def test_saved_exact_edge_and_cut_only_boolean_material(self):
        import manifold3d as manifold
        fan = {"vertices_xz_m": [[-178439.37434404684, 68351.55803256418],
            [-178440., 68355.], [-178441.87696785945, 68355.]],
            "depth_at_vertices_m": [.619548634445664, .619548634445697, .619548634445697]}
        self.assertAlmostEqual(exact_depth(fan, [-178441., 68355.]), .619548634445697)
        record = triangular_prism([[0., 1., 0.], [2., 1., 0.], [0., 1., 2.]], 5., [0., 0., 0.])
        self.assertEqual(json.loads(json.dumps(record, allow_nan=False)), record)
        surface = manifold_from_record(record)
        attachment = {"half_arm_triangle_indices": [0], "actual_complete_port_proof": {
            "original_profile_xyz_m": [[0., 1., 0.], [.5, 1., 0.], [1.5, 1., 0.], [2., 1., 0.]],
            "segments": [{"pieces": [{"start_xz_m": [0., 0.], "end_xz_m": [2., 0.],
                "bed_coefficients_m_t012": [1., 0., 0.]}]}]}}
        bottoms = [{"bottom_triangle_id": 0, "fan_key": "actual", "bottom_vertices_xyz_m":
            [[0., 1., 0.], [2., 1., 0.], [0., 1., -2.]]}]
        support = canonical_boundary_witness(attachment, bottoms,
            attachment["actual_complete_port_proof"]["original_profile_xyz_m"], [0., 1.], "sink")
        self.assertEqual(support[0]["supports"][0]["interval_t01"], [0., 1.])
        self.assertEqual(support[0]["supports"][0]["maximum_whole_linear_error_m"], 0.)
        before = manifold.Manifold.cube([4., 4., 4.])
        gallery = manifold.Manifold.cube([1., 2., 4.]).translate([.25, .5, 0.])
        old_after, old_removed = before - gallery, before ^ gallery
        coupled = gallery + surface
        after, removed, extra = before - coupled, before ^ coupled, old_after ^ surface
        ledger = volume_ledger(before, old_after, old_removed, after, removed, extra)
        self.assertGreater(ledger["extra_removed_m3"], 0.)
        self.assertEqual(ledger["fill_m3"], 0.)
        self.assertAlmostEqual(ledger["total_removed_m3"], ledger["original_removed_m3"] + ledger["extra_removed_m3"])
        self.assertEqual((after - before).volume(), 0.)

    def test_illegal_source_depth_missing_domain_and_cap_refused(self):
        fan = {"vertices_xz_m": [[0., 0.], [1., 0.], [0., 1.]], "depth_at_vertices_m": [-1e-16, .5, .5]}
        with self.assertRaisesRegex(ValueError, "strict"):
            exact_depth(fan, [0., 0.])
        fan = {**fan, "depth_at_vertices_m": [0., .5, .5]}
        with self.assertRaisesRegex(ValueError, "outside"):
            exact_depth(fan, [1., 1.])
        with self.assertRaisesRegex(ValueError, "cap"):
            triangular_prism([[0., 1., 0.], [1., 1., 0.], [0., 1., 1.]], 1., [0., 0., 0.])
        patch_fan = {**fan, "depth_origin_xz_m": [0., 0.], "depth_coefficients_m_1xz": [-1e-16, 0., 0.]}
        with self.assertRaisesRegex(ValueError, "strict"):
            saved_patch_depth(patch_fan, [.25, .25])


if __name__ == "__main__":
    unittest.main()
