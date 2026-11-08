import tempfile
import unittest
from pathlib import Path
import json

import numpy as np

from terrain_pipeline.channel_centerline import (SmoothingRecipe, build_centerline,
                                                  load_centerline, save_centerline,
                                                  validate_centerline_for_plan,
                                                  _segments_cross, _shared_edge_overlap)
from terrain_pipeline.artifacts.contracts import array_hash
from terrain_pipeline.local_channel_sections import SectionRecipe, evaluate_sections, load_sections
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel
from terrain_pipeline.metric_channel_plan import load_plan
from tests.test_local_channel_sections import synthetic_plan


def corner_plan():
    height = np.full((4, 4), 10.)
    outlet = np.ones((4, 4), bool)
    receiver = np.full(16, -1, dtype=np.int64)
    for cell, target in ((1, 5), (5, 6), (6, 10)):
        receiver[cell] = target
        outlet.flat[cell] = False
    order = np.array([cell for cell in range(16) if outlet.flat[cell]] + [6, 5, 1])
    q = np.full((4, 4), .01)
    q.flat[[1, 5, 6, 10]] = .1
    return plan_channel(height, receiver, order, outlet, q, 10., 10., 0., 0.,
                        0., "corner", ChannelRecipe(reference_depth_m=1.,
                        min_depth_m=1., max_depth_m=1., max_cut_m=10.,
                        min_bed_slope_m_per_m=.0001))


class ChannelCenterlineTests(unittest.TestCase):
    def test_corner_moves_only_internal_nodes_and_zero_strength_is_legacy(self):
        plan = corner_plan()
        original = plan["arrays"]["source_height_m"].copy()
        zero = build_centerline(plan, SmoothingRecipe(strength=0.))
        np.testing.assert_array_equal(zero["arrays"]["node_world_xz_m"],
                                      zero["arrays"]["original_world_xz_m"])
        smooth = build_centerline(plan, SmoothingRecipe(max_offset_m=10.))
        arrays = smooth["arrays"]
        self.assertGreater(smooth["summary"]["moved_nodes"], 0)
        np.testing.assert_array_equal(arrays["node_world_xz_m"][arrays["anchor_mask"]],
                                      arrays["original_world_xz_m"][arrays["anchor_mask"]])
        self.assertLessEqual(smooth["summary"]["max_offset_m"], 10.)
        np.testing.assert_array_equal(plan["arrays"]["source_height_m"], original)
        legacy = evaluate_sections(plan, 0., 0., 1., 1., (31, 31),
                                   np.zeros((31, 31), bool), SectionRecipe())
        explicit_zero = evaluate_sections(plan, 0., 0., 1., 1., (31, 31),
                                          np.zeros((31, 31), bool), SectionRecipe(), zero)
        np.testing.assert_array_equal(legacy["arrays"]["required_cut_m"],
                                      explicit_zero["arrays"]["required_cut_m"])

    def test_corridor_rejects_and_confluence_anchor_stays_fixed(self):
        plan = corner_plan()
        with self.assertRaisesRegex(ValueError, "corridor"):
            build_centerline(plan, SmoothingRecipe(max_offset_m=.1))
        confluence = synthetic_plan()
        smooth = build_centerline(confluence, SmoothingRecipe(max_offset_m=10.))
        arrays = smooth["arrays"]
        junction = np.where(arrays["node_flat_index"] == 12)[0][0]
        self.assertTrue(arrays["anchor_mask"][junction])
        np.testing.assert_array_equal(arrays["node_world_xz_m"][junction],
                                      arrays["original_world_xz_m"][junction])

    def test_shared_smoothed_geometry_matches_adjacent_tiles_and_storage(self):
        plan = corner_plan()
        smooth = build_centerline(plan, SmoothingRecipe(max_offset_m=10.))
        recipe = SectionRecipe(max_local_cut_m=10.)
        whole = evaluate_sections(plan, 0., 0., 1., 1., (31, 31),
                                  np.zeros((31, 31), bool), recipe, smooth)
        left = evaluate_sections(plan, 0., 0., 1., 1., (31, 16),
                                 np.zeros((31, 16), bool), recipe, smooth)
        right = evaluate_sections(plan, 15., 0., 1., 1., (31, 16),
                                  np.zeros((31, 16), bool), recipe, smooth)
        np.testing.assert_array_equal(left["arrays"]["required_cut_m"],
                                      whole["arrays"]["required_cut_m"][:, :16])
        np.testing.assert_array_equal(right["arrays"]["required_cut_m"],
                                      whole["arrays"]["required_cut_m"][:, 15:])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "centerline.npz"
            save_centerline(smooth, path)
            loaded = load_centerline(path)
            self.assertTrue(validate_centerline_for_plan(loaded, plan))
            np.testing.assert_array_equal(loaded["arrays"]["node_world_xz_m"],
                                          smooth["arrays"]["node_world_xz_m"])
            with self.assertRaises(FileExistsError):
                save_centerline(smooth, path)

    def test_crossing_touch_overlap_and_separation_guards(self):
        self.assertTrue(_segments_cross(np.array([0., 0.]), np.array([2., 2.]),
                                        np.array([0., 2.]), np.array([2., 0.])))
        self.assertTrue(_segments_cross(np.array([0., 0.]), np.array([2., 0.]),
                                        np.array([1., 0.]), np.array([1., 2.])))
        self.assertTrue(_shared_edge_overlap(np.array([0., 0.]), np.array([2., 0.]),
                                             np.array([0., 0.]), np.array([1., 0.]),
                                             np.array([0., 0.])))
        shifted = np.array([1_000_000., 1_000_000.])
        self.assertFalse(_shared_edge_overlap(shifted, shifted + [2., 0.],
                                              shifted, shifted + [-1., 0.],
                                              shifted))
        self.assertTrue(_segments_cross(shifted, shifted + [2., 2.],
                                        shifted + [0., 2.], shifted + [2., 0.]))
        with self.assertRaisesRegex(ValueError, "separation"):
            build_centerline(synthetic_plan(), SmoothingRecipe(max_offset_m=10.,
                                                               min_separation_m=100.))

    def test_new_length_slope_failure_is_reported(self):
        plan = synthetic_plan()
        centerline = build_centerline(plan, SmoothingRecipe(max_offset_m=10.))
        self.assertGreater(centerline["summary"]["slope_failed_edges"], 0)
        self.assertTrue(centerline["arrays"]["slope_failed_donor_mask"].any())

    def test_saved_geometry_tamper_and_wrong_plan_rejected(self):
        plan = corner_plan()
        centerline = build_centerline(plan, SmoothingRecipe(max_offset_m=10.))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "centerline.npz"
            save_centerline(centerline, path)
            with np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name].copy() for name in archive.files if name != "manifest"}
                manifest = json.loads(str(archive["manifest"].item()))
            arrays["node_world_xz_m"][1, 0] += .1
            manifest["array_sha256"]["node_world_xz_m"] = array_hash(arrays["node_world_xz_m"])
            np.savez_compressed(path, manifest=json.dumps(manifest), **arrays)
            with self.assertRaisesRegex(ValueError, "geometry differs from identity"):
                load_centerline(path)
        with self.assertRaisesRegex(ValueError, "source plan mismatch"):
            validate_centerline_for_plan(centerline, synthetic_plan())

    def test_default_sections_match_saved_v1_artifact_exactly(self):
        root = Path(__file__).resolve().parents[1]
        plan = load_plan(root / "verification/metric-channel-plan/run-20260929T140629572001Z/normal_mountain-plan.npz")
        original = load_sections(root / "verification/local-channel-sections/run-20260929T142543606808Z/normal-mountain-local-sections.npz")
        current = evaluate_sections(plan, 354240., 468420., 1., 1., (61, 61),
                                    np.zeros((61, 61), bool), SectionRecipe())
        self.assertEqual(current["identity_sha256"], original["identity_sha256"])
        for name in current["arrays"]:
            np.testing.assert_array_equal(current["arrays"][name], original["arrays"][name])


if __name__ == "__main__":
    unittest.main()
