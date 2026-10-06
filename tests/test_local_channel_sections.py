import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.local_channel_sections import (SectionRecipe, evaluate_sections,
                                                     load_sections, save_sections)
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel


def synthetic_plan(width=4., cap=10.):
    height = np.full((5, 5), 10.)
    outlet = np.ones((5, 5), dtype=bool)
    receiver = np.full(25, -1, dtype=np.int64)
    for donor, target in ((1, 6), (3, 8), (6, 12), (8, 12), (12, 17), (17, 22)):
        receiver[donor] = target
        outlet.flat[donor] = False
    # The required route order is downstream first, including the shared junction.
    order = np.array([cell for cell in range(25) if outlet.flat[cell]] +
                     [17, 12, 6, 8, 1, 3], dtype=np.int64)
    q = np.full((5, 5), .01)
    q.flat[[1, 3, 6, 8, 12, 17, 22]] = .1
    return plan_channel(height, receiver, order, outlet, q, 10., 10.,
                        0., 0., 0., "synthetic", ChannelRecipe(
                            reference_discharge_m3_s=.1, reference_width_m=width,
                            min_width_m=width, max_width_m=width,
                            reference_depth_m=1., min_depth_m=1., max_depth_m=1.,
                            max_cut_m=cap))


class LocalChannelSectionsTests(unittest.TestCase):
    def test_enclosed_segment_has_zero_outer_cut(self):
        height = np.full((7, 7), 10.)
        outlet = np.ones((7, 7), dtype=bool)
        receiver = np.full(49, -1, dtype=np.int64)
        receiver[3 * 7 + 2] = 3 * 7 + 3
        outlet[3, 2] = False
        q = np.full((7, 7), .01)
        q[3, 2:4] = .1
        order = np.array([cell for cell in range(49) if outlet.flat[cell]] + [3 * 7 + 2])
        plan = plan_channel(height, receiver, order, outlet, q, 10., 10., 0., 0.,
                            0., "enclosed", ChannelRecipe(reference_width_m=4.,
                            min_width_m=4., max_width_m=4.))
        section = evaluate_sections(plan, 0., 0., 1., 1., (61, 61),
                                    np.zeros((61, 61), bool), SectionRecipe())
        cut = section["arrays"]["required_cut_m"]
        self.assertFalse(section["summary"]["requires_shared_fine_extension"])
        self.assertFalse(np.any(cut[0, :]) or np.any(cut[-1, :]) or
                         np.any(cut[:, 0]) or np.any(cut[:, -1]))

    def test_adjacent_windows_match_whole_grid_and_shared_nodes(self):
        plan = synthetic_plan()
        recipe = SectionRecipe(max_local_cut_m=10.)
        whole = evaluate_sections(plan, 0., 0., 1., 1., (41, 41),
                                  np.zeros((41, 41), bool), recipe)
        left = evaluate_sections(plan, 0., 0., 1., 1., (41, 21),
                                 np.zeros((41, 21), bool), recipe)
        right = evaluate_sections(plan, 20., 0., 1., 1., (41, 21),
                                  np.zeros((41, 21), bool), recipe)
        for key in ("source_surface_m", "required_cut_m", "bounded_surface_m"):
            np.testing.assert_array_equal(left["arrays"][key], whole["arrays"][key][:, :21])
            np.testing.assert_array_equal(right["arrays"][key], whole["arrays"][key][:, 20:])
            np.testing.assert_array_equal(left["arrays"][key][:, -1], right["arrays"][key][:, 0])
        self.assertAlmostEqual(left["summary"]["actual_cut_volume_m3"] +
                               right["summary"]["actual_cut_volume_m3"],
                               whole["summary"]["actual_cut_volume_m3"])

    def test_protection_budget_and_clipped_edge_are_diagnostic(self):
        plan = synthetic_plan(cap=.1)
        protect = np.zeros((21, 21), bool)
        protect[10, 10] = True
        section = evaluate_sections(plan, 10., 10., 1., 1., (21, 21),
                                    protect, SectionRecipe(max_local_cut_m=.1))
        arrays = section["arrays"]
        self.assertTrue(section["summary"]["blocked_by_plan"])
        self.assertTrue(arrays["over_budget_mask"].any())
        self.assertTrue(arrays["protected_conflict_mask"].any())
        self.assertEqual(arrays["actual_cut_m"][10, 10], 0.)
        self.assertTrue(section["summary"]["requires_shared_fine_extension"])
        self.assertTrue(arrays["clipped_boundary_mask"].any())

    def test_outside_source_rejected_and_storage_round_trip(self):
        plan = synthetic_plan()
        with self.assertRaises(ValueError):
            evaluate_sections(plan, -1., 0., 1., 1., (3, 3),
                              np.zeros((3, 3), bool), SectionRecipe())
        section = evaluate_sections(plan, 0., 0., 1., 1., (41, 41),
                                    np.zeros((41, 41), bool), SectionRecipe())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "section.npz"
            save_sections(section, path)
            reloaded = load_sections(path)
            self.assertEqual(section["identity_sha256"], reloaded["identity_sha256"])
            for name, value in section["arrays"].items():
                np.testing.assert_array_equal(value, reloaded["arrays"][name])
            with self.assertRaises(FileExistsError):
                save_sections(section, path)

    def test_cosine_cross_section_and_unchanged_exterior(self):
        plan = synthetic_plan(width=4.)
        original = plan["arrays"]["source_height_m"].copy()
        section = evaluate_sections(plan, 0., 0., 1., 1., (41, 41),
                                    np.zeros((41, 41), bool), SectionRecipe(max_local_cut_m=10.))
        cut = section["arrays"]["required_cut_m"]
        # The vertical segment x=20, z=20..30 has a 2 m half width.
        self.assertAlmostEqual(cut[25, 20], 1.0029142135623736, places=6)
        self.assertAlmostEqual(cut[25, 21], .5014571067811868, places=6)
        self.assertAlmostEqual(cut[25, 22], 0., places=8)
        self.assertEqual(cut[40, 0], 0.)
        np.testing.assert_array_equal(plan["arrays"]["source_height_m"], original)

    def test_narrow_segment_reports_sampling_and_local_refinement(self):
        plan = synthetic_plan(width=1.)
        section = evaluate_sections(plan, 0.5, 0.5, 4., 5., (8, 8),
                                    np.zeros((8, 8), bool), SectionRecipe())
        self.assertGreater(section["summary"]["potentially_unsampled_segments"], 0)
        whole = evaluate_sections(plan, 0., 0., 2., 4., (11, 21),
                                  np.zeros((11, 21), bool), SectionRecipe())
        self.assertGreater(whole["summary"]["needs_refinement_nodes"], 0)


if __name__ == "__main__":
    unittest.main()
