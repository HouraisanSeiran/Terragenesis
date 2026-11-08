import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.channel_geometry import ChannelRecipe, load_plan, plan_channel, save_plan
from terrain_pipeline.artifacts.contracts import array_hash
from terrain_pipeline.surface_rivers import route
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import route_graph as route_graph


def make_plan(height, q, spacing=10., recipe=None):
    outlet = np.zeros(height.shape, dtype=bool)
    outlet[-1, -1] = True
    routing = route(height, outlet, spacing)
    return plan_channel(height, routing.receiver, routing.order, outlet, q,
                        spacing, spacing, 0., 0., 0., "test-source", recipe or ChannelRecipe())


class MetricChannelPlanTests(unittest.TestCase):
    def test_diagonal_uses_physical_length_and_confluence_stricter_bed(self):
        height = np.full((2, 3), 10.)
        outlet = np.zeros(height.shape, dtype=bool)
        outlet[1, 1] = True
        mesh = grid_mesh(height.shape, dx_m=3., dz_m=4.)
        routing = route_graph(height, outlet, mesh)
        receiver, order = routing.receiver, routing.order
        q = np.full(height.shape, .1)
        recipe = ChannelRecipe(reference_width_m=1., reference_depth_m=1.,
                               min_depth_m=1., max_depth_m=1., max_cut_m=10.,
                               min_bed_slope_m_per_m=.2)
        plan = plan_channel(height, receiver, order, outlet, q, 3., 4.,
                            0., 0., 0., "synthetic", recipe)
        path_lengths = []
        for start in range(height.size):
            length, node = 0., start
            while receiver[node] >= 0:
                target = receiver[node]
                length += np.hypot(mesh.node_x_m[node] - mesh.node_x_m[target],
                                   mesh.node_z_m[node] - mesh.node_z_m[target])
                node = target
            path_lengths.append(length)
        expected = 9. - .2 * max(path_lengths)
        self.assertAlmostEqual(plan["arrays"]["target_bed_m"][1, 1], expected)
        self.assertAlmostEqual(plan["arrays"]["required_cut_m"][1, 1], 10. - expected)

    def test_threshold_and_spacing_do_not_set_nominal_dimensions(self):
        height = np.array([[10., 9., 8.]])
        q = np.array([[.05, .1, .2]])
        first = make_plan(height, q, 1., ChannelRecipe(start_discharge_m3_s=.05))
        second = make_plan(height, q, 10., ChannelRecipe(start_discharge_m3_s=.02))
        np.testing.assert_array_equal(first["arrays"]["nominal_width_m"],
                                      second["arrays"]["nominal_width_m"])
        np.testing.assert_array_equal(first["arrays"]["nominal_depth_m"],
                                      second["arrays"]["nominal_depth_m"])
        self.assertFalse(first["arrays"]["needs_refinement_mask"].any())
        self.assertTrue(second["arrays"]["needs_refinement_mask"].all())

    def test_threshold_does_not_change_shared_cell_nominal_dimensions(self):
        height = np.array([[10., 10., 10.], [9., 9., 9.], [8., 8., 8.]])
        q = np.array([[.01, .02, .01], [.03, .05, .03], [.04, .07, .1]])
        lower = make_plan(height, q, 1., ChannelRecipe(start_discharge_m3_s=.01))
        higher = make_plan(height, q, 1., ChannelRecipe(start_discharge_m3_s=.04))
        shared = higher["arrays"]["channel_mask"]
        np.testing.assert_array_equal(lower["arrays"]["nominal_width_m"][shared],
                                      higher["arrays"]["nominal_width_m"][shared])
        np.testing.assert_array_equal(lower["arrays"]["nominal_depth_m"][shared],
                                      higher["arrays"]["nominal_depth_m"][shared])

    def test_diagonal_length_and_budget_failure(self):
        height = np.array([[10., 10.], [10., 10.]])
        q = np.ones_like(height)
        plan = make_plan(height, q, 10., ChannelRecipe(max_cut_m=.1,
                            min_bed_slope_m_per_m=.1, reference_depth_m=.2,
                            min_depth_m=.2, max_depth_m=.2))
        arrays = plan["arrays"]
        self.assertTrue(arrays["over_budget_mask"].any())
        self.assertTrue(arrays["failed_slope_edge_donor_mask"].any())
        self.assertGreater(arrays["required_cut_m"].max(), 1.)
        np.testing.assert_array_equal(height, np.full((2, 2), 10.))

    def test_invalid_inputs_and_reproducible_storage(self):
        height = np.array([[2., 1.]])
        q = np.array([[.1, .2]])
        with self.assertRaises(ValueError):
            make_plan(height, q, recipe=ChannelRecipe(max_cut_m=-1.))
        with self.assertRaises(ValueError):
            make_plan(height, np.array([[np.nan, .2]]))
        outlet = np.array([[False, True]])
        with self.assertRaises(ValueError):
            plan_channel(height, [1, 0], [0, 1], outlet, q, 1., 1.,
                         0., 0., 0., "test", ChannelRecipe())
        large = np.ones((3, 3))
        far_receiver = np.full(9, -1)
        far_receiver[0] = 8
        far_outlets = np.ones((3, 3), dtype=bool)
        far_outlets[0, 0] = False
        with self.assertRaises(ValueError):
            plan_channel(large, far_receiver, np.arange(9)[::-1], far_outlets,
                         large, 1., 1., 0., 0., 0., "test", ChannelRecipe())
        plan = make_plan(height, q)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.npz"
            save_plan(plan, path)
            reloaded = load_plan(path)
            self.assertEqual(plan["identity_sha256"], reloaded["identity_sha256"])
            for name, original in plan["arrays"].items():
                np.testing.assert_array_equal(original, reloaded["arrays"][name])
                self.assertFalse(reloaded["arrays"][name].flags.writeable)
            with self.assertRaises(FileExistsError):
                save_plan(plan, path)

    def test_plan_owns_inputs_and_rejects_channel_ending_before_outlet(self):
        height = np.array([[3., 2., 1.]])
        q = np.array([[.1, .1, .1]])
        plan = make_plan(height, q)
        identity = plan["identity_sha256"]
        original_height = plan["arrays"]["source_height_m"].copy()
        original_q = plan["arrays"]["discharge_m3_s"].copy()
        height[0, 0] = 100.
        q[0, 0] = 100.
        np.testing.assert_array_equal(plan["arrays"]["source_height_m"], original_height)
        np.testing.assert_array_equal(plan["arrays"]["discharge_m3_s"], original_q)
        self.assertEqual(plan["identity_sha256"], identity)
        with self.assertRaisesRegex(ValueError, "terminates before explicit outlet"):
            make_plan(np.array([[3., 2., 1.]]), np.array([[.1, .01, .01]]))

    def test_tampered_source_cannot_be_rehashed_without_identity_change(self):
        plan = make_plan(np.array([[3., 2., 1.]]), np.array([[.1, .1, .1]]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.npz"
            save_plan(plan, path)
            with np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name].copy() for name in archive.files if name != "manifest"}
                manifest = json.loads(str(archive["manifest"].item()))
            arrays["source_height_m"][0, 0] += 1.
            manifest["array_sha256"]["source_height_m"] = array_hash(arrays["source_height_m"])
            np.savez_compressed(path, manifest=json.dumps(manifest, sort_keys=True), **arrays)
            with self.assertRaisesRegex(ValueError, "differs from identity"):
                load_plan(path)

    def test_failed_atomic_publication_leaves_no_destination_or_temp_file(self):
        plan = make_plan(np.array([[3., 2., 1.]]), np.array([[.1, .1, .1]]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.npz"
            with patch('terrain_pipeline.channel_geometry.os.link', side_effect=OSError("link failed")):
                with self.assertRaisesRegex(OSError, "link failed"):
                    save_plan(plan, path)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
