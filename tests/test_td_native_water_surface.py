import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.td_native_water_surface import (
    _grid, build_water_surface, export_water_obj, load_pinned_page, load_water_surface,
    save_water_surface, validate_water_surface,
)
from tests.test_td_native_channel_geometry import fixture


REAL_PAGE = Path(__file__).resolve().parents[1] / (
    "verification/td-basin-generation/A-native-weather-v10-20261002T185307845630Z/"
    "eastward-2.5s/hour-00/storage.npz")
REAL_SHA = "c89756a42ae10b2b14d95cb2951c20ec54a7079ff81bf224ad87d358e290d1c8"
REAL_IDENTITY = "11432c57c7ec42acd0f7613e328a8f5edda00327cb0ff27e7a5fe0bf9df2ab80"


class NativeWaterSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hierarchy, cls.page = fixture()

    def test_original_grid_volume_and_threshold(self):
        surface = build_water_surface(self.page, source_sha256="a" * 64, wet_threshold_m=.01)
        arrays = surface["arrays"]
        page_arrays = self.page["arrays"]
        self.assertEqual(len(arrays["cell_ids"]), int(page_arrays["valid_mask"].sum()))
        expected = float(page_arrays["depth_m"][-1].sum() * 30. ** 2)
        self.assertAlmostEqual(surface["metadata"]["grid_water_volume_m3"], expected)
        ids = arrays["vertex_cell_ids"]
        np.testing.assert_array_equal(arrays["vertices_xyz_m"][:, 1],
                                      page_arrays["height_m"].ravel()[ids] + page_arrays["depth_m"][-1, ids])
        self.assertFalse(surface["metadata"]["derived_fine_hydraulics"])
        self.assertFalse(surface["metadata"]["hydraulic_ready"])
        high = build_water_surface(self.page, source_sha256="a" * 64, wet_threshold_m=100.)
        self.assertEqual(len(high["arrays"]["triangles"]), 0)
        self.assertEqual(high["metadata"]["grid_water_volume_m3"], surface["metadata"]["grid_water_volume_m3"])

    def test_hole_and_dry_display(self):
        height = np.arange(16, dtype=np.float64).reshape(4, 4)
        depth = np.ones((4, 4), np.float64)
        valid = np.ones((4, 4), bool)
        valid[1, 1] = False
        depth[1, 1] = 0
        depth[2, 2] = 0
        vertex_ids, triangles, wet, quads = _grid(height, depth, valid, .5)
        self.assertFalse(wet[1, 1])
        self.assertFalse(wet[2, 2])
        self.assertEqual(int(quads.sum()), 2)
        self.assertEqual(len(triangles), 4)
        self.assertNotIn(1 * 4 + 1, vertex_ids)
        self.assertNotIn(2 * 4 + 2, vertex_ids)
        valid[:] = True
        depth[:] = 1
        _, triangles, _, quads = _grid(height, depth, valid, .5)
        self.assertEqual(int(quads.sum()), 9)
        self.assertEqual(len(triangles), 18)

    def test_negative_nonfinite_budget_and_tamper(self):
        height = np.zeros((2, 2), np.float64)
        depth = np.ones((2, 2), np.float64)
        valid = np.ones((2, 2), bool)
        for value in (-1., np.nan, np.inf):
            changed = depth.copy()
            changed[0, 0] = value
            with self.assertRaises(ValueError):
                _grid(height, changed, valid, .1)
        with self.assertRaisesRegex(ValueError, "budget"):
            _grid(np.zeros((501, 501)), np.zeros((501, 501)), np.ones((501, 501), bool), .1)
        with self.assertRaises(ValueError):
            _grid(height, depth, valid, 0.)
        surface = build_water_surface(self.page, source_sha256="a" * 64, wet_threshold_m=.01)
        forged = copy.deepcopy(surface)
        forged["arrays"] = {name: value.copy() for name, value in forged["arrays"].items()}
        forged["arrays"]["vertices_xyz_m"][0, 1] += 1
        forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
        with self.assertRaisesRegex(ValueError, "source height/depth"):
            validate_water_surface(forged)

    def test_npz_obj_cold_and_external_pins(self):
        surface = build_water_surface(self.page, source_sha256="a" * 64, wet_threshold_m=.01)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "surface.npz"
            obj = Path(directory) / "surface.obj"
            save_water_surface(path, surface)
            with patch("terrain_pipeline.td_native_water_surface.build_water_surface", side_effect=AssertionError("rebuilt")):
                cold = load_water_surface(path, expected_sha256=file_sha256(path),
                                          expected_identity=surface["identity_sha256"])
            self.assertEqual(cold["identity_sha256"], surface["identity_sha256"])
            export_water_obj(obj, cold)
            self.assertEqual(sum(line.startswith("f ") for line in obj.read_text().splitlines()),
                             len(surface["arrays"]["triangles"]))
            obj_vertices = np.array([[float(value) for value in line.split()[1:]]
                                     for line in obj.read_text().splitlines() if line.startswith("v ")])
            np.testing.assert_array_equal(obj_vertices, surface["arrays"]["vertices_xyz_m"])
            with self.assertRaises(ValueError):
                load_water_surface(path, expected_sha256="0" * 64,
                                   expected_identity=surface["identity_sha256"])
            with self.assertRaises(FileExistsError):
                export_water_obj(obj, cold)
            with self.assertRaises(FileExistsError):
                save_water_surface(path, surface)
            with self.assertRaises(ValueError):
                load_pinned_page(path, expected_sha256="0" * 64, expected_identity="a" * 64)

    def test_real_saved_page_cold_read_without_generation(self):
        with patch("terrain_pipeline.td_native_water_surface.build_water_surface", side_effect=AssertionError("built")):
            page = load_pinned_page(REAL_PAGE, expected_sha256=REAL_SHA, expected_identity=REAL_IDENTITY)
        self.assertEqual(page["identity_sha256"], REAL_IDENTITY)
        self.assertEqual(page["metadata"]["spacing_m"], 30.)
        with self.assertRaises(ValueError):
            load_pinned_page(REAL_PAGE, expected_sha256="0" * 64, expected_identity=REAL_IDENTITY)


if __name__ == "__main__":
    unittest.main()
