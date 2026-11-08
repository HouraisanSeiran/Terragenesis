"""Behaviour tests for the synthetic remote-sensing renderer."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tools.render_remote_sensing import (
    DECLARATION, ELEVATION_BANDS, bilinear, false_colour_rgb, floodplain_depth_state,
    floodplain_mask_on, grid_axes, lake_mask_on, lake_state, node_state, stage_field,
    surface_rgb, water_rgb,
)


class BilinearTests(unittest.TestCase):
    def test_grid_axes_reproduces_origin_and_spacing(self):
        xs, zs = grid_axes((-100.0, 50.0), 10.0, (3, 4))
        np.testing.assert_allclose(xs, [-100.0, -90.0, -80.0, -70.0])
        np.testing.assert_allclose(zs, [50.0, 60.0, 70.0])

    def test_grid_points_are_reproduced_exactly(self):
        page = np.array([[0.0, 1.0], [2.0, 3.0]])
        xs, zs = grid_axes((0.0, 0.0), 10.0, page.shape)
        values = bilinear(page, xs, zs, xs, zs)
        np.testing.assert_allclose(values, page)

    def test_midpoint_is_the_cell_average(self):
        page = np.array([[0.0, 2.0], [4.0, 6.0]])
        xs, zs = grid_axes((0.0, 0.0), 10.0, page.shape)
        values = bilinear(page, xs, zs, np.array([5.0]), np.array([5.0]))
        self.assertAlmostEqual(float(values[0, 0]), 3.0, places=12)

    def test_sampling_outside_the_page_is_clamped(self):
        page = np.array([[0.0, 1.0], [2.0, 3.0]])
        xs, zs = grid_axes((0.0, 0.0), 10.0, page.shape)
        values = bilinear(page, xs, zs, np.array([-50.0, 100.0]),
                          np.array([-50.0, 100.0]))
        # Both coordinates clamp to the page corners, so the corners come back.
        np.testing.assert_allclose(values, page)

    def test_shape_mismatch_is_refused(self):
        with self.assertRaises(ValueError):
            bilinear(np.zeros((2, 3)), np.arange(4.0), np.arange(2.0),
                     np.array([0.0]), np.array([0.0]))


class StageFieldTests(unittest.TestCase):
    def state(self):
        return {
            "node_xz_m": np.array([[0.0, 0.0], [1000.0, 0.0]]),
            "receiver": np.array([1, -1]),
            "stage_m": np.array([10.0, 9.0]),
            "width_m": np.array([100.0, 100.0]),
            "depth_m": np.array([1.0, 2.0]),
        }

    def test_surface_is_interpolated_along_the_reach(self):
        xs = np.array([250.0, 750.0])
        zs = np.array([0.0])
        surface, distance, half, along = stage_field(xs, zs, self.state())
        np.testing.assert_allclose(surface[0], [9.75, 9.25], atol=1e-12)
        np.testing.assert_allclose(along[0], [1.25, 1.75], atol=1e-12)
        np.testing.assert_allclose(half[0], [50.0, 50.0])
        np.testing.assert_allclose(distance[0], [0.0, 0.0], atol=1e-12)

    def test_transverse_distance_to_the_centreline(self):
        xs = np.array([500.0])
        zs = np.array([-30.0, 30.0, 90.0])
        _, distance, half, _ = stage_field(xs, zs, self.state())
        np.testing.assert_allclose(distance[:, 0], [30.0, 30.0, 90.0])
        np.testing.assert_allclose(half[:, 0], [50.0, 50.0, 50.0])

    def test_beyond_a_terminal_node_stays_undefined(self):
        xs = np.array([1200.0, -200.0])
        zs = np.array([0.0])
        surface, distance, _, _ = stage_field(xs, zs, self.state())
        self.assertTrue(np.isinf(distance[0, 0]))
        self.assertTrue(np.isinf(distance[0, 1]))
        self.assertTrue(np.isnan(surface[0, 0]))
        self.assertTrue(np.isnan(surface[0, 1]))

    def test_zero_length_segment_is_refused(self):
        state = self.state()
        state["node_xz_m"] = np.array([[0.0, 0.0], [0.0, 0.0]])
        with self.assertRaises(ValueError):
            stage_field(np.array([0.0]), np.array([0.0]), state)


class NodeStateTests(unittest.TestCase):
    def test_mean_depth_uses_the_control_area(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            geom = dict(node_xz_m=np.array([[0.0, 0.0], [1.0, 0.0]]),
                        receiver=np.array([1, -1]),
                        width_m=np.array([10.0, 20.0]))
            np.savez(root / "generated-geometry.npz", **geom)
            np.savez(root / "dynamic-water-sediment-bed.npz",
                     water_volume_m3=np.array([[100.0, 400.0]]),
                     node_bed_m=np.array([[5.0, 4.0]]),
                     material_area_m2=np.array([200.0, 800.0]),
                     time_seconds=np.array([0.0]))
            state = node_state(root, 0)
        # control length = area/width -> 20 m and 40 m; depth = V/(w*L)
        np.testing.assert_allclose(state["control_length_m"], [20.0, 40.0])
        np.testing.assert_allclose(state["depth_m"], [0.5, 0.5])
        np.testing.assert_allclose(state["stage_m"], [5.5, 4.5])

    def test_nonpositive_width_is_refused(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            np.savez(root / "generated-geometry.npz",
                     node_xz_m=np.array([[0.0, 0.0]]),
                     receiver=np.array([-1]),
                     width_m=np.array([0.0]))
            np.savez(root / "dynamic-water-sediment-bed.npz",
                     water_volume_m3=np.array([[1.0]]),
                     node_bed_m=np.array([[0.0]]),
                     material_area_m2=np.array([1.0]),
                     time_seconds=np.array([0.0]))
            with self.assertRaises(ValueError):
                node_state(root, 0)


class LakeTests(unittest.TestCase):
    def build(self, root, *, stage=306.5, cell_area=1.0e8, bed=195.4, sill=306.3,
              terminal=1, centre=(1300000.0, 1290000.0)):
        np.savez(root / "generated-geometry.npz",
                 node_xz_m=np.array([[0.0, 0.0], list(centre)]),
                 receiver=np.array([1, -1]),
                 width_m=np.array([800.0, 800.0]))
        np.savez(root / "lake-storage.npz",
                 time_edges_seconds=np.array([0.0, 3600.0, 7200.0]),
                 stage_m=np.array([306.0, 306.2, stage]),
                 volume_m3=np.array([1.0e10, 1.05e10, cell_area * (stage - bed)]),
                 surface_area_m2=np.full(3, cell_area),
                 sill_stage_m=np.array(sill))
        (root / "lake-definition.json").write_text(json.dumps({
            "terminal_node_index": terminal,
            "lake": {"cell_area_m2": [cell_area], "bed_elevation_m": [bed]},
        }), encoding="utf-8")
        return root

    def test_stage_is_interpolated_to_the_interval(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.build(Path(folder))
            lake = lake_state(root, 3600.0)
        self.assertAlmostEqual(lake["stage_m"], 306.2, places=6)
        self.assertAlmostEqual(lake["depth_m"], 306.2 - 195.4, places=6)
        self.assertAlmostEqual(lake["half_size_m"], 5000.0, places=6)

    def test_depth_never_goes_negative_below_the_bed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.build(Path(folder), stage=100.0)
            lake = lake_state(root, 7200.0)
        self.assertEqual(lake["depth_m"], 0.0)

    def test_mask_is_the_modelled_cell_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.build(Path(folder))
            lake = lake_state(root, 7200.0)
        xs = np.array([1294000.0, 1296000.0, 1300000.0, 1304000.0, 1306000.0])
        zs = np.array([1290000.0])
        wet = lake_mask_on(xs, zs, lake)
        np.testing.assert_array_equal(wet[0], [False, True, True, True, False])

    def test_no_lake_files_yields_none(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(lake_state(Path(folder), 0.0))


class BedFrameTests(unittest.TestCase):
    """The coupled-bed option must never break runs that have no bed field."""

    def make_run(self, root, *, with_field=False):
        root = Path(root)
        vertices = np.array([[0.0, 0.0], [100.0, 0.0], [0.0, 100.0], [100.0, 100.0]])
        np.savez(root / "generated-geometry.npz",
                 vertices_xz_m=vertices,
                 triangles=np.array([[0, 1, 2], [1, 3, 2]]),
                 bed_elevation_m=np.full(4, 10.0),
                 node_xz_m=np.array([[0.0, 0.0], [100.0, 0.0]]),
                 receiver=np.array([1, -1]),
                 width_m=np.array([100.0, 100.0]))
        np.savez(root / "dynamic-water-sediment-bed.npz",
                 water_volume_m3=np.array([[1000.0, 1000.0]]),
                 node_bed_m=np.array([[10.0, 10.0]]),
                 material_area_m2=np.array([10000.0, 10000.0]),
                 time_seconds=np.array([0.0]))
        np.savez(root / "source-terrain-and-forcing.npz",
                 height_m=np.full((2, 2), 10.0),
                 origin_xz_m=np.array([-50.0, -50.0]))
        (root / "source-selection.json").write_text(
            json.dumps({"coarse_terrain_spacing_m": 100.0}), encoding="utf-8")
        if with_field:
            np.savez(root / "bed-change-field.npz",
                     final_bed_m=np.full(4, 9.0),
                     initial_bed_m=np.full(4, 10.0),
                     bed_change_m=np.full(4, -1.0))
        return root

    def window(self):
        return np.array([25.0, 75.0]), np.array([25.0, 75.0])

    def test_without_a_field_the_static_carve_is_used(self):
        from tools.render_remote_sensing import carved_bed
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_run(Path(folder))
            xs, zs = self.window()
            values, _, _ = carved_bed(root, xs, zs)
        np.testing.assert_allclose(values, 10.0)

    def test_asking_for_the_coupled_bed_without_the_field_is_refused(self):
        from tools.render_remote_sensing import carved_bed
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_run(Path(folder))
            xs, zs = self.window()
            with self.assertRaises(ValueError):
                carved_bed(root, xs, zs, frame="final")

    def test_the_field_selects_initial_final_and_change(self):
        from tools.render_remote_sensing import carved_bed
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_run(Path(folder), with_field=True)
            xs, zs = self.window()
            final, _, _ = carved_bed(root, xs, zs, frame="final")
            initial, _, _ = carved_bed(root, xs, zs, frame="initial")
            change, _, _ = carved_bed(root, xs, zs, frame="change")
        np.testing.assert_allclose(final, 9.0)
        np.testing.assert_allclose(initial, 10.0)
        np.testing.assert_allclose(change, -1.0)

    def test_compose_defaults_to_the_static_carve_and_still_renders(self):
        from tools.render_remote_sensing import compose
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_run(Path(folder))
            xs, zs = self.window()
            rgb, diagnostics, _, bed, _, _, _ = compose(root, xs, zs, 0)
        self.assertEqual(rgb.shape, (2, 2, 3))
        np.testing.assert_allclose(bed, 10.0)
        # 1000 m3 over 100 m x 100 m of control area is 0.1 m of water, so the
        # channel is wet; the point is that the call itself still works.
        self.assertGreater(diagnostics["wet_pixels"], 0)

    def test_compose_draws_the_final_bed_when_asked(self):
        from tools.render_remote_sensing import compose
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_run(Path(folder), with_field=True)
            xs, zs = self.window()
            _, _, _, bed, _, _, _ = compose(root, xs, zs, 0, bed_frame="final")
        np.testing.assert_allclose(bed, 9.0)


class ColourTests(unittest.TestCase):
    def test_surface_rgb_is_bounded_and_shape_correct(self):
        height = np.linspace(0.0, 2500.0, 100).reshape(10, 10)
        rgb = surface_rgb(height, 50.0)
        self.assertEqual(rgb.shape, (10, 10, 3))
        self.assertGreaterEqual(float(rgb.min()), 0.0)
        self.assertLessEqual(float(rgb.max()), 1.0)

    def test_water_colour_darkens_with_depth(self):
        rgb = water_rgb(np.array([0.02, 0.47]))
        self.assertGreater(float(rgb[0].sum()), float(rgb[1].sum()))

    def test_false_colour_makes_open_water_dark(self):
        height = np.full((6, 6), 100.0)
        wet = np.zeros((6, 6), bool)
        wet[3, 3] = True
        rgb = false_colour_rgb(height, 50.0, wet)
        self.assertLess(float(rgb[3, 3].sum()), float(rgb[0, 0].sum()))

    def test_elevation_bands_are_ordered(self):
        thresholds = [band[0] for band in ELEVATION_BANDS]
        self.assertEqual(thresholds, sorted(thresholds))

    def test_declaration_marks_the_image_as_synthetic(self):
        self.assertIn("NOT SATELLITE OBSERVATION", DECLARATION)


class FloodplainFieldTests(unittest.TestCase):
    """The optional two-dimensional depth field, read from a saved product."""

    def write_run(self, directory):
        np.savez(directory / "floodplain-depth-field.npz",
                 depth_m=np.array([[[0., 0.], [0., 2.]],
                                   [[1., 1.], [1., 1.]]]),
                 time_s=np.array([0., 3600.]),
                 height_m=np.zeros((2, 2)),
                 origin_xz_m=np.array([0., 0.]),
                 spacing_m=np.float64(10.))
        return directory

    def test_missing_product_returns_none(self):
        with tempfile.TemporaryDirectory() as name:
            self.assertIsNone(floodplain_depth_state(Path(name), 0.))

    def test_nearest_frame_is_selected_by_time(self):
        with tempfile.TemporaryDirectory() as name:
            directory = self.write_run(Path(name))
            state = floodplain_depth_state(directory, 3000.)
            self.assertEqual(state["frame"], 1)
            self.assertAlmostEqual(float(state["depth_m"].max()), 1.)

    def test_sampling_returns_zero_outside_the_page(self):
        state = {"depth_m": np.ones((2, 2)), "origin_xz_m": np.array([0., 0.]),
                 "spacing_m": 10., "height_m": np.zeros((2, 2)),
                 "time_seconds": 0., "frame": 0, "frames_available": 1}
        inside = floodplain_mask_on(np.array([0., 10.]), np.array([0., 10.]), state)
        np.testing.assert_allclose(inside, np.ones((2, 2)))
        outside = floodplain_mask_on(np.array([-500., 900.]), np.array([500., 900.]), state)
        np.testing.assert_allclose(outside, np.zeros((2, 2)))

    def test_negative_stored_depth_is_clamped_not_propagated(self):
        state = {"depth_m": np.array([[-1., 3.], [0., 0.]]), "origin_xz_m": np.array([0., 0.]),
                 "spacing_m": 10., "height_m": np.zeros((2, 2)),
                 "time_seconds": 0., "frame": 0, "frames_available": 1}
        values = floodplain_mask_on(np.array([0., 10.]), np.array([0., 10.]), state)
        self.assertGreaterEqual(float(values.min()), 0.)


if __name__ == "__main__":
    unittest.main()
