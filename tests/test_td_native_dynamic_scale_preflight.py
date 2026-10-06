"""Native v10 scale preflight uses actual driver limits without solver imports."""

import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline import td_native_dynamic_scale_preflight as scale
from terrain_pipeline.td_basin_storage_v10_io import STATES, LEDGERS, FLUX


class ScaleTests(unittest.TestCase):
    def test_exact_full_grid_work_and_driver_rejections(self):
        hierarchy = {"arrays": {"face_cells": [None] * 130560,
                                "valid_mask": np.ones((256, 256), dtype=bool)}}
        inputs = {"code_sha256": {name: "pin" for name in scale.EVIDENCE}, "hierarchy": {"path": "pin"}}
        with patch.object(scale, "_pin_inputs", return_value=(inputs, {}, {"metadata": {
                "spacing_m": 30., "origin_m_xz": [100., 200.]}}, hierarchy)):
            report = scale.preflight()
        for size in scale.SIZES:
            case = report["sizes"][str(size)]
            faces = 2 * size * (size - 1)
            self.assertEqual(case["d4_faces_upper_exact_for_full_valid_grid"], faces)
            self.assertEqual(case["hour_work"]["2.5"]["face_steps_per_hour"], 1440 * faces)
            self.assertEqual(case["hour_work"]["1.25"]["face_steps_per_hour"], 2880 * faces)
            self.assertEqual(case["full_24h_rain_values"], 24 * size * size)
            self.assertEqual(case["cell_area_footprint_m_xz"], [size * 30., size * 30.])
            self.assertEqual(case["sample_center_span_m_xz"], [(size - 1) * 30., (size - 1) * 30.])
            self.assertFalse(case["dynamic_solver_ready"])
        self.assertEqual(report["origin_m_xz"], [100., 200.])
        self.assertTrue(report["sizes"]["256"]["actual_v10_profile_prepare_ready"])
        self.assertFalse(report["sizes"]["512"]["actual_v10_profile_prepare_ready"])
        self.assertFalse(report["sizes"]["1024"]["actual_v10_profile_prepare_ready"])
        self.assertFalse(report["sizes"]["2048"]["actual_v10_profile_prepare_ready"])
        self.assertFalse(report["hydraulic_ready"])

    def test_window_coverage_and_halo_budget(self):
        case = scale._size(1024, 30.)
        windows = case["window_plan"]["windows"]
        self.assertEqual(len(windows), 16)
        self.assertEqual(sum((window["interior_zx"][1] - window["interior_zx"][0]) *
                             (window["interior_zx"][3] - window["interior_zx"][2]) for window in windows), 1024**2)
        self.assertTrue(case["window_plan"]["all_window_local_limits_passed"])
        self.assertEqual(windows[5]["cells_including_halo"], 258**2)
        self.assertEqual(windows[5]["d4_faces_upper"], 2 * 258 * 257)

    def test_memory_is_only_an_estimate(self):
        estimate = scale.estimate_memory(256**2, 2 * 256 * 255, 4 * 256 - 4)
        self.assertTrue(estimate["estimate_not_measurement"])
        self.assertEqual(estimate["full_24h_rain_bytes"], 24 * 256**2 * 8)
        self.assertEqual(estimate["estimated_resident_arrays_and_scratch_bytes"],
                         2 * estimate["full_24h_rain_bytes"] + estimate["saved_page_arrays_bytes"] +
                         estimate["checkpoint_arrays_bytes"] + estimate["solver_and_ssprk2_scratch_reserve_bytes"])
        self.assertNotIn("conservative_peak_estimate_bytes", estimate)

    def test_exact_page_and_checkpoint_array_bytes_from_tiny_schema(self):
        cells, faces, boundary = 6, 7, 3
        page = {name: np.empty((2, cells), dtype=np.float64) for name in STATES}
        page.update({name: np.empty((1, cells), dtype=np.float64) for name in LEDGERS})
        page["rain_mm_h"] = np.empty((1, cells), dtype=np.float64)
        page["height_m"] = np.empty((2, 3), dtype=np.float64)
        page["valid_mask"] = np.empty((2, 3), dtype=bool)
        page["receiver"] = np.empty(cells, dtype=np.int64)
        page["face_cells"] = np.empty((faces, 2), dtype=np.int64)
        page["boundary_cells"] = np.empty(boundary, dtype=np.int64)
        page["boundary_width_m"] = np.empty(boundary, dtype=np.float64)
        for name in FLUX:
            page[name] = np.empty(faces if name.startswith(("face_", "active_")) else cells,
                                  dtype=np.float64)
        checkpoint = {name: np.empty(cells, dtype=np.float64) for name in STATES}
        checkpoint.update({"error_" + name: np.empty(cells, dtype=np.float64) for name in STATES})
        checkpoint.update({"cumulative_" + name: np.empty(faces if name.startswith(("face_", "active_"))
                                                  else cells, dtype=np.float64) for name in FLUX})
        estimate = scale.estimate_memory(cells, faces, boundary)
        self.assertEqual(estimate["saved_page_arrays_bytes"], sum(array.nbytes for array in page.values()))
        self.assertEqual(estimate["checkpoint_arrays_bytes"], sum(array.nbytes for array in checkpoint.values()))

    def test_changed_code_pin_is_rejected(self):
        with patch.object(scale, "file_sha256", return_value="changed"):
            with self.assertRaises(ValueError):
                scale._pin_inputs()

    def test_import_does_not_load_solver_or_numba(self):
        code = ("import terrain_pipeline.td_native_dynamic_scale_preflight; import sys; "
                "assert 'numba' not in sys.modules; "
                "assert 'terrain_pipeline.td_basin_storage_v10' not in sys.modules")
        subprocess.run([sys.executable, "-c", code], check=True)


if __name__ == "__main__":
    unittest.main()
