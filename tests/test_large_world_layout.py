"""Finite world layout and absolute conditioning contracts, CPU only."""
import unittest

import numpy as np

from terrain_pipeline.world_water_layout import LayoutSpec, classify_points, layout_field
from diffusion.world_layout_conditioning import (WorldLayoutGenerationConfig,
                                                  layout_elevation_m,
                                                  make_conditioning_map,
                                                  select_nonempty_window)


class LargeWorldTests(unittest.TestCase):
    def test_modes_keep_absolute_coordinates_and_target(self):
        for preset, water in (("earth", .62), ("archipelago", .8), ("lakes", .12)):
            with self.subTest(preset=preset):
                spec = LayoutSpec(preset, water, mode="finite", frame_origin_m=(0, 0),
                                  frame_side_m=12_288_000)
                # Independent of the fixed 512-cell calibration lattice.
                axis = (np.arange(511) + .5) * spec.frame_side_m / 511
                x, z = np.meshgrid(axis, axis)
                whole = classify_points(spec, x, z)
                left = classify_points(spec, x[:, :255], z[:, :255])
                np.testing.assert_array_equal(whole[:, :255], left)
                self.assertLess(abs(np.mean(whole != 0) - water), .02)
                window = select_nonempty_window(spec, 129,
                                                prefer="lake" if preset == "lakes" else "coast")
                self.assertTrue(window["contains"]["land"])
                self.assertTrue(all(value % 30.0 == 0 for value in window["origin_m"]))
                page_axis = np.arange(129) * 30.0
                page_x, page_z = np.meshgrid(window["origin_m"][0] + page_axis,
                                             window["origin_m"][1] + page_axis)
                page = classify_points(spec, page_x, page_z)
                self.assertTrue(np.any(page == 0))
                self.assertTrue(np.any(page == (2 if preset == "lakes" else 1)))

    def test_factory_uses_absolute_indices(self):
        spec = LayoutSpec("lakes", .12, mode="finite", frame_origin_m=(0, 0),
                          frame_side_m=12_288_000)
        factory = make_conditioning_map(spec, WorldLayoutGenerationConfig.from_layout(spec),
                                        origin_world_m=(0, 0))
        whole = factory.sample_raw(40, 70, 48, 78)
        part = factory.sample_raw(44, 70, 48, 78)
        np.testing.assert_array_equal(whole[:, :, 4:], part)

    def test_field_crosses_region_boundary_continuously(self):
        spec = LayoutSpec("lakes", .12, mode="finite", frame_origin_m=(0, 0),
                          frame_side_m=12_288_000)
        x = spec.region_side_m + np.array([-1.0, 0.0, 1.0])
        field = layout_field(spec, x, np.full(3, 1_000_000.0))
        self.assertLess(np.max(np.abs(np.diff(field))), 0.001)

    def test_shore_and_bed_are_continuous(self):
        spec = LayoutSpec("lakes", .12, mode="finite", frame_origin_m=(0, 0),
                          frame_side_m=12_288_000)
        config = WorldLayoutGenerationConfig.from_layout(spec)
        window = select_nonempty_window(spec, 129, prefer="lake")
        x, z = window["anchor_m"]
        elevations = layout_elevation_m(spec, config, np.array([x - 1, x, x + 1]),
                                        np.full(3, z))
        self.assertLess(abs(elevations[1]), .01)
        self.assertLess(np.max(np.abs(np.diff(elevations))), 1.0)
        self.assertLess(np.min(elevations), 0)
        self.assertGreater(np.max(elevations), 0)

    def test_scale_changes_field_and_threshold_cache_key(self):
        first = LayoutSpec("lakes", .12, mode="finite", frame_origin_m=(0, 0),
                           frame_side_m=12_288_000)
        second = LayoutSpec("lakes", .12, mode="finite", frame_origin_m=(0, 0),
                            frame_side_m=12_288_000, region_side_m=1_000_000)
        x = np.array([1_000_000.0, 2_000_000.0, 3_000_000.0])
        z = np.array([2_000_000.0, 3_000_000.0, 4_000_000.0])
        self.assertFalse(np.array_equal(layout_field(first, x, z), layout_field(second, x, z)))
        self.assertNotEqual(first.identity(), second.identity())


if __name__ == "__main__":
    unittest.main()
