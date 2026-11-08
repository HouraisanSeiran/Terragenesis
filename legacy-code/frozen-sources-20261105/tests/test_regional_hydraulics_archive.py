"""Cold evidence and exact discrete water-column geometry rejection tests."""

from copy import deepcopy
from dataclasses import replace
import json
import tempfile
from pathlib import Path
import unittest

import numpy as np

from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget, validate_budget, prepare_surface_geometry, validate_surface_geometry, limited_inertial_fluxes, _net_flux
from terrain_pipeline.regional_hydraulics_archive import read_arrays, validate_momentum, validate_full_region_coordinates
from terrain_pipeline.regional_hydraulics_mesh import water_columns, validate_water_columns
from terrain_pipeline.mountain_source_adapter import file_sha256


class RegionalEvidenceTests(unittest.TestCase):
    def test_full_region_rejects_resigned_metric_footprint(self):
        geometry = {"metadata": {"shape": [256, 256], "spacing_m": 30., "origin_m_xz": [-184320., 61440.], "area_m2": 58982400.}}
        validate_full_region_coordinates(geometry)
        for key, value in (("spacing_m", 60.), ("origin_m_xz", [-184305., 61455.]), ("shape", [128, 128]), ("area_m2", 1.)):
            forged = deepcopy(geometry)
            forged["metadata"][key] = value
            with self.assertRaises(ValueError):
                validate_full_region_coordinates(forged)

    def test_budget_all_fields_reject_invalid(self):
        for key, value in vars(SurfaceBudget()).items():
            for invalid in (False, float("nan"), 0, -1):
                with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                    validate_budget(replace(SurfaceBudget(), **{key: invalid}))

    def test_geometry_exact_shapes_and_origin(self):
        bed = np.zeros((2, 3))
        for origin in ([0.], [0., float("nan")]):
            with self.assertRaises(ValueError):
                prepare_surface_geometry(bed, spacing_m=30., origin_m_xz=origin, source_identity="test")
        geometry = prepare_surface_geometry(bed, spacing_m=30., origin_m_xz=[0., 0.], source_identity="test")
        for key in geometry["arrays"]:
            forged = deepcopy(geometry)
            forged["arrays"][key] = forged["arrays"][key].astype(np.float32)
            with self.assertRaises(ValueError):
                validate_surface_geometry(forged, trusted_height=bed, source_identity="test")
        forged = deepcopy(geometry)
        forged["metadata"]["spacing_m"] = -30.
        with self.assertRaises(ValueError):
            validate_surface_geometry(forged, trusted_height=bed, source_identity="test")

    def test_header_preflight_rejects_extra_and_wrong_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.npz"
            np.savez(path, depth=np.zeros((2, 3)))
            digest = file_sha256(path)
            with self.assertRaises(ValueError):
                read_arrays(path, {"depth": ((6,), "float64")}, expected_sha256=digest)
            arrays = read_arrays(path, {"depth": ((2, 3), "float64")}, expected_sha256=digest)
            self.assertFalse(arrays["depth"].flags.writeable)
            with self.assertRaises(ValueError):
                read_arrays(path, {}, expected_sha256=digest)

    def test_momentum_forgery_conserves_volume_but_rejected(self):
        geometry = prepare_surface_geometry(np.zeros((1, 2)), spacing_m=30., origin_m_xz=[0., 0.], source_identity="test")
        budget = SurfaceBudget()
        depth, forcing, tailwater = np.array([.2, .1]), np.zeros(2), np.zeros(6)
        internal, boundary, limiter = limited_inertial_fluxes(geometry, depth, np.zeros(1), np.zeros(6), tailwater, forcing, 1., budget)
        packet = {"depth_before_m": depth, "depth_after_m": depth + _net_flux(geometry, internal, boundary) / 900.,
            "forcing_m3_s": forcing, "tailwater_m": tailwater, "internal_q_before_m3_s": np.zeros(1),
            "boundary_q_before_m3_s": np.zeros(6), "internal_q_after_m3_s": internal, "boundary_q_after_m3_s": boundary}
        meta = {"dt_s": 1., "limiter": limiter}
        validate_momentum(packet, meta, geometry, budget)
        packet["internal_q_after_m3_s"] = internal + .01
        packet["depth_after_m"] = depth + _net_flux(geometry, internal + .01, boundary) / 900.
        with self.assertRaises(ValueError):
            validate_momentum(packet, meta, geometry, budget)

    def test_columns_exact_volume_upward_tops_and_dry_omission(self):
        bed = np.array([[1500., 1501.], [1490., 1492.]])
        depth = np.array([[.1, 0.], [.3, .01]])
        packet = water_columns(bed, depth, spacing_m=30., origin_m_xz=[10., 20.], source_identity="test", time_s=900.)
        result = validate_water_columns(packet, trusted_height=bed, saved_depth=depth, source_identity="test")
        self.assertAlmostEqual(result["volume_m3"], 369.)
        self.assertEqual(result["wet_cells"], 3)
        triangles = packet["arrays"]["vertices_xyz_m"][packet["arrays"]["triangles"]]
        signed_volume = np.einsum("ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])).sum() / 6
        self.assertAlmostEqual(signed_volume, 369., places=6)
        packet["arrays"]["vertices_xyz_m"][4, 1] += .01
        with self.assertRaises(ValueError):
            validate_water_columns(packet, trusted_height=bed, saved_depth=depth, source_identity="test")

    def test_mesh_reports_stage_rounding_not_fake_zero_error(self):
        bed = np.array([[1500.]])
        depth = np.array([[1e-14]])
        packet = water_columns(bed, depth, spacing_m=30., origin_m_xz=[0., 0.], source_identity="test", time_s=0.)
        result = validate_water_columns(packet, trusted_height=bed, saved_depth=depth, source_identity="test",
            trusted_spacing_m=30., trusted_origin_m_xz=[0., 0.])
        self.assertEqual(result["zero_coordinate_height_positive_depth_cells"], 1)
        self.assertEqual(result["coordinate_column_volume_m3"], 0.)
        self.assertLess(result["volume_error_m3"], 0.)
        with self.assertRaises(ValueError):
            validate_water_columns(packet, trusted_height=bed, saved_depth=depth, source_identity="test", trusted_spacing_m=60.)

    def test_mesh_loader_requires_declared_nonempty_keyframes(self):
        from tools.verify_regional_hydraulics_mesh_load import check
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "manifest.json").write_text(json.dumps({"artifacts": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                check(path, expected_manifest_sha256=file_sha256(path / "manifest.json"))


if __name__ == "__main__":
    unittest.main()
