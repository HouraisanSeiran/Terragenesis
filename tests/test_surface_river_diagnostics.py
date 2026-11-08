import unittest
import json
import hashlib
from pathlib import Path

import numpy as np

from terrain_pipeline.surface_rivers import GridInput, route
from terrain_pipeline.surface_rivers.diagnostics import RiverDiagnostics, route_cut_lower_bound
from terrain_pipeline.surface_rivers.pipeline import process
from tools.diagnose_river_feasibility import _boundary_connected_ocean, _coast_catchments


class SurfaceRiverDiagnosticsTests(unittest.TestCase):
    def test_first_cause_and_propagation_are_distinct(self):
        diagnostics = RiverDiagnostics((2, 2))
        diagnostics.mark_cell("bed_cut_cap", 0)
        diagnostics.mark_cell("stage_above_bank", 0)
        diagnostics.mark_cell("neighbor_failed", 0, propagated=True)
        self.assertEqual(diagnostics.summary()["first_cause_counts"]["bed_cut_cap"], 1)
        self.assertEqual(diagnostics.summary()["first_cause_counts"]["stage_above_bank"], 0)
        self.assertEqual(diagnostics.summary()["propagation_counts"]["neighbor_failed"], 1)

    def test_fixed_route_cut_lower_bound_exposes_cap(self):
        height = np.array([[10., 20., 0.]])
        receiver = np.array([1, 2, -1])
        order = np.array([2, 1, 0])
        estimate = route_cut_lower_bound(height, receiver, order, 4)
        self.assertGreater(estimate["max_cut_m"], 10)
        self.assertGreater(estimate["above_cap_cells"], 0)

    def test_fixed_route_cut_rejects_invalid_inputs(self):
        height = np.array([[2., 1.]])
        for bad_height, receiver, order, cap, drop in (
                (np.empty((0, 2)), [-1, -1], [0, 1], 4., .01),
                (np.array([[np.nan, 1.]]), [-1, 0], [0, 1], 4., .01),
                (height, [1, 0], [0, 1], 4., .01),
                (height, [-1, 0], [1, 0], 4., .01),
                (height, [-1, 0], [0, 1], -1., .01),
                (height, [-1, 0], [0, 1], 4., 0.)):
            with self.subTest(receiver=receiver, order=order, cap=cap, drop=drop):
                with self.assertRaises(ValueError):
                    route_cut_lower_bound(bad_height, receiver, order, cap, drop)

    def test_coast_catchment_flags_land_boundary(self):
        height = np.full((7, 7), -1., dtype=float)
        height[2:5, 2:5] = 2.
        closed = _coast_catchments(height, _boundary_connected_ocean(height, 0.))
        self.assertEqual(sum(item["land_cells"] for item in closed), 9)
        self.assertTrue(all(item["observed_window_closed"] for item in closed))
        height[1, 3] = height[0, 3] = 2.
        open_groups = _coast_catchments(height, _boundary_connected_ocean(height, 0.))
        self.assertEqual(sum(item["land_cells"] for item in open_groups), 11)
        self.assertGreater(sum(item["land_boundary_cells"] for item in open_groups), 0)

    def test_two_mouths_do_not_merge_through_shared_ocean_edge(self):
        height = np.full((9, 9), 5., dtype=float)
        slopes = np.array([[8., 8., 8.], [7., 7., 7.], [6., 6., 6.],
                           [4., 4., 4.], [2., 2., 2.]])
        height[1:6, 1:4] = slopes
        height[1:6, 5:8] = slopes
        height[5, 2:7] = -1.
        height[6:9, 4] = -1.
        ocean = _boundary_connected_ocean(height, 0.)
        groups = _coast_catchments(height, ocean)
        self.assertEqual(sum(group["land_cells"] for group in groups),
                         np.count_nonzero(height > 0))
        mouths = {tuple(group["first_ocean_cell_grid_zx"]) for group in groups}
        self.assertIn((5, 2), mouths)
        self.assertIn((5, 6), mouths)
        self.assertTrue(all(height[mouth] <= 0 for mouth in mouths))
        # If routing continues through the ocean, these land cells share one edge terminal.
        sea_edge = ocean.copy()
        sea_edge[:-1, :] = False
        old_route = route(height, sea_edge, 30.)
        terminal = np.empty(height.size, dtype=np.int64)
        for cell in old_route.order:
            target = old_route.receiver[cell]
            terminal[cell] = cell if target < 0 else terminal[target]
        self.assertEqual(len(np.unique(terminal[height.ravel() > 0])), 1)

    def test_frozen_mountain_products_stay_readonly_and_new_generation_is_explicit(self):
        from terrain_pipeline.metric_region import METRIC_30M_RECIPE_V1, process_region
        from tools.verify_metric_rivers import (SOURCE_ROOT, SAMPLES, SPACING_M,
                                                RUNOFF_M_PER_S, THRESHOLD_M3_PER_S,
                                                MAX_INCISION_M, SEA_M, HALO_X, HALO_Z)
        root = Path(__file__).resolve().parents[1]
        baseline = root / "verification/metric-rivers/run-20260929T110135621570Z"
        fields = ("input_height", "processed_height", "vdm_dy", "water_surface",
                  "discharge", "receiver", "channel_mask", "flowline_mask",
                  "width_blocks", "unresolved_mask", "outlet_mask")
        for name, phase, seed, x, z in SAMPLES[:2]:
            with self.subTest(name=name):
                source = SOURCE_ROOT / phase / f"seed{seed}-x{x}-z{z}.npz"
                with np.load(source, allow_pickle=False) as archive:
                    raw = archive["elevation"].astype(np.float64) + SEA_M
                processed = process_region(raw, SEA_M, SPACING_M, SPACING_M,
                                           recipe=METRIC_30M_RECIPE_V1).elevation_m
                height = processed[HALO_Z:-HALO_Z, HALO_X:-HALO_X].copy()
                boundary = np.zeros(height.shape, dtype=bool)
                boundary[0, :] = boundary[-1, :] = True
                boundary[:, 0] = boundary[:, -1] = True
                outlet = np.zeros(height.shape, dtype=bool)
                outlet.flat[int(np.argmin(np.where(boundary, height, np.inf)))] = True
                grid = GridInput(height, SPACING_M,
                                 ((x + HALO_X) * SPACING_M, (z + HALO_Z) * SPACING_M),
                                 np.full(height.shape, RUNOFF_M_PER_S), outlet)
                diagnostics = RiverDiagnostics(height.shape)
                archived_path = baseline / f"{name}.npz"
                archived_digest = hashlib.sha256(archived_path.read_bytes()).hexdigest()
                product = process(grid, THRESHOLD_M3_PER_S, MAX_INCISION_M, diagnostics)
                without_diagnostics = process(grid, THRESHOLD_M3_PER_S, MAX_INCISION_M)
                np.testing.assert_array_equal(product.input_height, height)
                np.testing.assert_array_equal(product.height, without_diagnostics.height)
                np.testing.assert_array_equal(product.water_surface, without_diagnostics.water_surface)
                self.assertEqual(product.metadata, without_diagnostics.metadata)
                self.assertLessEqual(float((height - product.height).max()), MAX_INCISION_M + 1e-8)
                self.assertTrue(np.all(product.height <= height + 1e-8))
                self.assertAlmostEqual(product.metadata["input_total"], product.metadata["outlet_total"], places=7)
                self.assertIn("irregular", product.metadata["recipe"])
                with np.load(archived_path, allow_pickle=False) as saved:
                    for field in fields:
                        self.assertIn(field, saved)
                    self.assertNotEqual(product.metadata["recipe"], json.loads(str(saved["metadata"].item()))["recipe"])
                self.assertEqual(hashlib.sha256(archived_path.read_bytes()).hexdigest(), archived_digest)

    def test_opt_in_diagnostics_preserve_product(self):
        height = np.array([[15., 15., 15.], [15., 0., 15.], [15., 15., 14.]])
        outlet = np.zeros(height.shape, dtype=bool)
        outlet[-1, -1] = True
        grid = GridInput(height, 1.0, (0., 0.), np.ones_like(height), outlet)
        original = process(grid, 1.0, max_incision=.1)
        diagnostics = RiverDiagnostics(height.shape)
        observed = process(grid, 1.0, max_incision=.1, diagnostics=diagnostics)
        for field in ("input_height", "height", "vdm_dy", "water_surface", "discharge",
                      "receiver", "channel_mask", "flowline_mask", "width_blocks",
                      "unresolved_mask", "outlet_mask"):
            np.testing.assert_array_equal(getattr(observed, field), getattr(original, field))
        self.assertEqual(observed.metadata, original.metadata)
        self.assertGreaterEqual(sum(diagnostics.summary()["cause_counts"].values()), 1)


if __name__ == "__main__":
    unittest.main()
