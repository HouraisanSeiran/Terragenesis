import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from terrain_pipeline.surface_rivers import GridInput, route
from terrain_pipeline.surface_rivers.channel import carve_channels
from terrain_pipeline.surface_rivers.pipeline import process, save
from tools.preview_surface_rivers import y_confluence


class SurfaceRiverAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = y_confluence()
        cls.product = process(cls.grid, 2.0)
        cls.routing = route(cls.grid.height, cls.grid.outlet_mask, cls.grid.spacing_blocks)

    def test_two_branches_merge_with_shared_discharge(self):
        q = self.product.discharge
        receiver = self.routing.receiver
        junction = 24 * q.shape[1] + 24
        donors = np.flatnonzero(receiver == junction)
        self.assertGreaterEqual(len(donors), 2)
        self.assertEqual(sum(self.product.flowline_mask.flat[i] for i in donors), 2)
        self.assertAlmostEqual(q.flat[junction],
            sum(q.flat[i] for i in donors) + self.grid.runoff.flat[junction] * self.grid.spacing_blocks ** 2,
            places=4)

    def test_downstream_wet_cross_section_widens(self):
        wet = np.isfinite(self.product.water_surface)
        self.assertEqual(np.count_nonzero(self.product.unresolved_mask), 0)
        for row in (24, 25, 30, 40, 48):
            self.assertGreaterEqual(np.count_nonzero(wet[row]), 5)
        self.assertGreaterEqual(np.count_nonzero(wet[30]), np.count_nonzero(wet[24]))
        self.assertGreater(self.product.width_blocks[30].max(), self.product.width_blocks[15].max())

    def test_water_stays_within_carved_corridor_and_stage_descends(self):
        water = self.product.water_surface
        wet = np.isfinite(water)
        self.assertFalse(np.any(wet & ~self.product.channel_mask))
        self.assertTrue(np.all(water[wet] > self.product.height[wet]))
        for cell, downstream in enumerate(self.routing.receiver):
            if downstream >= 0 and np.isfinite(water.flat[cell]) and np.isfinite(water.flat[downstream]):
                self.assertLessEqual(water.flat[downstream], water.flat[cell] + 1e-6)

    def test_original_height_unchanged_and_budget_balanced(self):
        np.testing.assert_array_equal(self.product.input_height, self.grid.height)
        np.testing.assert_allclose(self.product.vdm_dy,
            self.product.height - self.product.input_height, rtol=0, atol=0)
        self.assertLess(abs(self.product.metadata["residual"]), 1e-8)

    def test_flowline_water_is_four_connected_to_outlet(self):
        wet = np.isfinite(self.product.water_surface)
        outlet_z, outlet_x = np.argwhere(self.grid.outlet_mask)[0]
        stack = [(int(outlet_z), int(outlet_x))]
        reached = np.zeros(wet.shape, dtype=bool)
        while stack:
            z, x = stack.pop()
            if reached[z, x] or not wet[z, x]:
                continue
            reached[z, x] = True
            for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nz, nx = z + dz, x + dx
                if 0 <= nz < wet.shape[0] and 0 <= nx < wet.shape[1]:
                    stack.append((nz, nx))
        self.assertTrue(np.all(reached[self.product.flowline_mask]))

    def test_deep_pit_with_small_incision_cap_is_marked_unresolved(self):
        height = np.array([[15., 15., 15.], [15., 0., 15.], [15., 15., 14.]])
        outlet = np.zeros(height.shape, dtype=bool)
        outlet[-1, -1] = True
        grid = GridInput(height, 1.0, (0., 0.), np.ones_like(height), outlet)
        result = process(grid, 1.0, max_incision=.1)
        self.assertTrue(np.any(result.unresolved_mask))
        self.assertFalse(result.metadata["complete_water_surface"])
        self.assertLessEqual(float(np.max(grid.height - result.height)), .1 + 1e-8)
        np.testing.assert_array_equal(grid.height, height)

    def test_invalid_order_rejected_before_channel_processing(self):
        height = np.array([[3., 2., 1.]])
        discharge = np.array([[3., 2., 1.]])
        receiver = np.array([1, 2, -1])
        with self.assertRaises(ValueError):
            carve_channels(height, receiver, np.array([2, 2, 0]), discharge, 1.0, 1.0)

    def test_saved_artifact_round_trips_without_changing_source(self):
        before = self.grid.height.copy()
        with TemporaryDirectory() as folder:
            path = Path(folder) / "surface.npz"
            save(path, self.product)
            with np.load(path, allow_pickle=False) as loaded:
                for key, expected in (("input_height", self.product.input_height),
                                      ("processed_height", self.product.height),
                                      ("vdm_dy", self.product.vdm_dy),
                                      ("water_surface", self.product.water_surface),
                                      ("discharge", self.product.discharge),
                                      ("receiver", self.product.receiver),
                                      ("channel_mask", self.product.channel_mask),
                                      ("flowline_mask", self.product.flowline_mask),
                                      ("width_blocks", self.product.width_blocks),
                                      ("unresolved_mask", self.product.unresolved_mask),
                                      ("outlet_mask", self.product.outlet_mask)):
                    np.testing.assert_array_equal(loaded[key], expected)
                self.assertIn("surface-routing-width-channel-v4", str(loaded["metadata"]))
        np.testing.assert_array_equal(self.grid.height, before)


if __name__ == "__main__":
    unittest.main()
