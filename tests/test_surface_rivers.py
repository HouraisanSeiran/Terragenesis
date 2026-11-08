import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from terrain_pipeline.surface_rivers import GridInput, route
from terrain_pipeline.channel_geometry import carve_channels
from terrain_pipeline.surface_rivers.bridge import bridge_diagonals
from terrain_pipeline.surface_rivers.pipeline import RECIPE, process, save
from tools.preview_surface_rivers import y_confluence


class SurfaceRiverAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = y_confluence()
        cls.product = process(cls.grid, 2.0)
        cls.routing = route(cls.grid.height, cls.grid.outlet_mask, cls.grid.spacing_blocks,
                            origin_world_xz=cls.grid.origin, world_seed=cls.grid.world_seed)

    def test_two_branches_merge_with_shared_discharge(self):
        q = self.product.discharge
        receiver = self.routing.receiver
        active_donor_count = np.bincount(receiver[(receiver >= 0) & self.product.flowline_mask.ravel()], minlength=q.size)
        junction = int(np.argmax(active_donor_count))
        donors = np.flatnonzero(receiver == junction)
        self.assertGreaterEqual(active_donor_count[junction], 2)
        self.assertAlmostEqual(q.flat[junction],
            sum(q.flat[i] for i in donors) + self.grid.runoff.flat[junction] * self.grid.spacing_blocks ** 2,
            places=4)

    def test_downstream_wet_cross_section_widens(self):
        wet = np.isfinite(self.product.water_surface)
        self.assertEqual(np.count_nonzero(self.product.unresolved_mask), 0)
        for row in (24, 25, 30, 40, 48):
            self.assertGreaterEqual(np.count_nonzero(wet[row]), 5)
        self.assertGreaterEqual(np.count_nonzero(wet[30]), np.count_nonzero(wet[24]))
        width = self.product.width_blocks
        for cell, target in enumerate(self.routing.receiver):
            if target >= 0 and self.product.flowline_mask.flat[cell]:
                self.assertGreaterEqual(width.flat[target], width.flat[cell])
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
        disconnected = self.product.flowline_mask & ~reached
        self.assertFalse(disconnected.any())
        self.assertTrue(np.all(reached[self.product.flowline_mask]))
        self.assertTrue(np.all(self.product.unresolved_mask[disconnected]))
        self.assertTrue(np.all(~wet[self.product.unresolved_mask]))
        self.assertEqual(self.product.metadata["complete_water_surface"], not self.product.unresolved_mask.any())

    def test_nonlocal_graph_edge_gets_four_connected_raster_support(self):
        source = np.full((7, 9), 10.)
        bed, water = source.copy(), np.full(source.shape, np.nan)
        corridor = np.zeros(source.shape, bool)
        receiver = np.full(source.size, -1, np.int64)
        start, end = 2 * 9 + 1, 3 * 9 + 6
        receiver[start] = end
        for cell in (start, end):
            bed.flat[cell], water.flat[cell], corridor.flat[cell] = 8., 8.5, True
        result_bed, result_water, result_corridor, bad = bridge_diagonals(
            source, bed, water, corridor, corridor, receiver, 4.)
        self.assertEqual(bad, [])
        reached, stack = set(), [start]
        while stack:
            cell = stack.pop()
            if cell in reached or not np.isfinite(result_water.flat[cell]):
                continue
            reached.add(cell)
            row, col = divmod(cell, source.shape[1])
            for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nr, nc = row + dr, col + dc
                if 0 <= nr < source.shape[0] and 0 <= nc < source.shape[1]:
                    stack.append(nr * source.shape[1] + nc)
        self.assertIn(end, reached)
        self.assertGreater(len(reached), 2)
        self.assertTrue(np.all(result_corridor[np.isfinite(result_water)]))
        self.assertLessEqual(float((source - result_bed).max()), 4.)
        # A ridge above the edit cap leaves the entire edge uncommitted.
        source[:, 4] = 100.
        failed_bed, failed_water, _, bad = bridge_diagonals(
            source, bed, water, corridor, corridor, receiver, 4.)
        self.assertEqual(bad, [(start, end)])
        np.testing.assert_array_equal(failed_bed, bed)
        np.testing.assert_array_equal(failed_water, water)

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
                self.assertIn(RECIPE, str(loaded["metadata"]))
        np.testing.assert_array_equal(self.grid.height, before)


if __name__ == "__main__":
    unittest.main()
