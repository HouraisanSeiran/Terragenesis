from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_basin_breach import (
    generate_saddle_breach, load_saddle_breach, saddle_path_face_identity, save_saddle_breach,
)
from terrain_pipeline.td_material_field import _bundle, _save_bundle, make_material_field
from tests.test_td_material_field import malicious_archive


def fixture(*, height=((2, 2.01, 1.98, 1.94),), target=(2, 1.98, 1.96, 1.94),
            path=(0, 1, 2, 3), volume=None, duration=None, protected=None,
            thickness=4, parameters=None, face_identity=None, missing_hydro=False,
            missing_anchor=False, anchor_override=None, hydro_override=None):
    height = np.asarray(height, np.float64)
    material = make_material_field(height.shape, origin_m_xz=(0, 0), spacing_m=1,
                                   protected_mask=protected, parameters={"erodibility_range": [1, 1],
                                   "weak_path_preference_range": [1, 1],
                                   "erodible_thickness_range_m": [thickness, thickness]})
    topology = "1" * 64
    face_identity = face_identity or saddle_path_face_identity(height, path, source_identity_sha256="2" * 64, topology_identity_sha256=topology)
    water = np.full(len(path), 1e8) if volume is None else np.asarray(volume)
    wet_time = np.full(len(path), 86400) if duration is None else np.asarray(duration)
    exposure = {"hydro_identity_sha256": "3" * 64, "face_cell_ids": list(path[1:3]),
                "outward_volume_m3": float(water[1]), "positive_outflow_steps": int(wet_time[1]), "dt_s": 1}
    anchor = {"topology_identity_sha256": topology, "source_basin_id": 0, "destination_basin_id": 1,
              "tail_cell_ids": [path[-1]], "engineering_open_boundary": False}
    anchor.update(anchor_override or {})
    exposure.update(hydro_override or {})
    return generate_saddle_breach(height, np.isfinite(height), spacing_m=1, materials=material,
                                  path_cell_ids=path, target_bed_m=target, path_face_identity=face_identity,
                                  source_identity_sha256="2" * 64, topology_identity_sha256=topology,
                                  hydro_identity_sha256="3" * 64,
                                  routed_volume_m3=water, wet_duration_s=wet_time,
                                  hydro_face_evidence=None if missing_hydro else exposure,
                                  downstream_anchor_evidence=None if missing_anchor else anchor,
                                  parameters=parameters)


class SaddleBreachTests(unittest.TestCase):
    def assert_rejected(self, result, reason):
        self.assertEqual(result["metadata"]["status"], "rejected")
        self.assertIn(reason, result["metadata"]["rejection_reasons"])
        np.testing.assert_array_equal(result["arrays"]["height_m"], result["arrays"]["original_height_m"])
        self.assertEqual(result["metadata"]["ledger"]["source_solid_m3"], 0)

    def test_saddle_original_uphill_becomes_target_downhill_with_exact_source(self):
        result = fixture()
        self.assertEqual(result["metadata"]["status"], "candidate")
        np.testing.assert_allclose(result["arrays"]["height_m"], [[2, 1.98, 1.96, 1.94]], atol=1e-14)
        self.assertTrue(np.all(np.diff(result["arrays"]["height_m"][0]) < 0))
        ledger = result["metadata"]["ledger"]
        self.assertAlmostEqual(ledger["source_geometry_m3"], 0.05)
        self.assertAlmostEqual(ledger["source_solid_m3"], 0.045)
        self.assertAlmostEqual(ledger["source_mass_kg"], 0.045 * 2650)
        self.assertEqual(ledger["stored_solid_m3"], ledger["source_solid_m3"])
        self.assertFalse(result["metadata"]["hydrology_coupled_verified"])

    def test_zero_water_and_duration_refuse_entire_path(self):
        for options in ({"volume": [0, 0, 0, 0]}, {"duration": [0, 0, 0, 0]}):
            self.assert_rejected(fixture(**options), "no_water_or_duration_at_cut")

    def test_insufficient_potential_no_partial_cut(self):
        self.assert_rejected(fixture(volume=[1, 1, 1, 1]), "insufficient_water_material_potential")

    def test_thickness_exhaustion_refuses_no_clipping(self):
        self.assert_rejected(fixture(thickness=0.015), "insufficient_erodible_thickness")

    def test_protection_refused_at_interior_and_anchor(self):
        for cell in (0, 1, 3):
            mask = np.zeros((1, 4), bool)
            mask[0, cell] = True
            if cell == 3:
                with self.assertRaises(ValueError):
                    fixture(protected=mask)
            else:
                self.assert_rejected(fixture(protected=mask), "protected_path_cell")

    def test_unknown_path_refuses_and_preserves_nan(self):
        self.assert_rejected(fixture(height=((2, np.nan, 1.98, 1.94),)), "unknown_path_cell")

    def test_target_uphill_fill_and_anchor_changes_refused(self):
        self.assert_rejected(fixture(target=(2, 1.99, 2, 1.95)), "target_not_strictly_downhill")
        self.assert_rejected(fixture(target=(2, 2.02, 1.97, 1.95)), "target_requires_unsourced_fill")
        self.assert_rejected(fixture(target=(1.999, 1.99, 1.97, 1.95)), "endpoint_anchor_changed")

    def test_bad_face_identity_diagonal_cycle_and_budget_refused(self):
        for options in ({"face_identity": "0" * 64}, {"path": (0, 2, 1, 3)},
                        {"path": (0, 1, 0, 3)}, {"parameters": {"max_path_cells": 3}},
                        {"parameters": {"erosion_scale_m": np.inf}}, {"volume": [1, -1, 1, 1]}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                fixture(**options)

    def test_no_change_outside_bent_d4_path(self):
        result = fixture(height=((2, 2.01, 8), (8, 1.98, 1.94)), path=(0, 1, 4, 5))
        self.assertEqual(result["arrays"]["height_m"][0, 2], 8)
        self.assertEqual(result["arrays"]["height_m"][1, 0], 8)
        self.assertEqual(result["metadata"]["status"], "candidate")

    def test_formula_target_slope_and_source_input_unchanged(self):
        height = np.asarray([[2, 2.01, 1.98, 1.94]])
        result = fixture(height=height)
        potential = 0.15 * np.log1p(1e8 / 1000) * (1 - np.exp(-86400 / 3600)) * np.sqrt(0.02)
        self.assertAlmostEqual(result["arrays"]["path_potential_depth_m"][1], potential)
        np.testing.assert_array_equal(height, [[2, 2.01, 1.98, 1.94]])

    def test_missing_actual_face_and_anchor_evidence_rejected(self):
        self.assert_rejected(fixture(missing_hydro=True), "missing_actual_saddle_face_flux_evidence")
        self.assert_rejected(fixture(missing_anchor=True), "missing_legal_downstream_anchor_evidence")

    def test_illegal_anchor_tail_source_basin_and_face_exposure_refused(self):
        for options in ({"anchor_override": {"destination_basin_id": 0}},
                        {"anchor_override": {"tail_cell_ids": [3, 2, 1]}},
                        {"hydro_override": {"hydro_identity_sha256": "4" * 64}},
                        {"hydro_override": {"face_cell_ids": [2, 1]}},
                        {"hydro_override": {"outward_volume_m3": 1}},
                        {"parameters": {"erosion_scale_m": 1}}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                fixture(**options)

    def test_nonlinear_target_refused(self):
        self.assert_rejected(fixture(target=(2, 1.99, 1.97, 1.94)), "target_not_anchor_linear_interpolation")

    def test_path_identity_changes_with_original_bed_and_source(self):
        height = np.asarray([[2, 2.01, 1.98, 1.94]])
        first = saddle_path_face_identity(height, [0, 1, 2, 3], source_identity_sha256="2" * 64, topology_identity_sha256="1" * 64)
        height[0, 1] += 0.001
        second = saddle_path_face_identity(height, [0, 1, 2, 3], source_identity_sha256="2" * 64, topology_identity_sha256="1" * 64)
        third = saddle_path_face_identity(height, [0, 1, 2, 3], source_identity_sha256="4" * 64, topology_identity_sha256="1" * 64)
        self.assertNotEqual(first, second)
        self.assertNotEqual(second, third)

    def test_solid_only_in_endpoint_inventory_anchor_bed_unchanged(self):
        result = fixture()
        arrays = result["arrays"]
        np.testing.assert_array_equal(arrays["stored_solid_m3"][0, :-1], 0)
        self.assertAlmostEqual(arrays["stored_solid_m3"][0, -1], 0.045)
        self.assertEqual(arrays["height_m"][0, -1], arrays["original_height_m"][0, -1])

    def test_hard_64_cell_budget(self):
        with self.assertRaises(ValueError):
            fixture(height=(tuple(np.linspace(2, 1, 65)),), path=tuple(range(65)), target=tuple(np.linspace(2, 1, 65)))

    def test_cold_pinned_read_no_generation_and_no_overwrite(self):
        result = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "saddle.npz"
            save_saddle_breach(result, path)
            with patch("terrain_pipeline.td_basin_breach.generate_saddle_breach", side_effect=AssertionError("forbidden")), patch("terrain_pipeline.td_material_field.make_material_field", side_effect=AssertionError("forbidden")):
                loaded = load_saddle_breach(path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"])
            self.assertEqual(result["identity_sha256"], loaded["identity_sha256"])
            with self.assertRaises(FileExistsError):
                save_saddle_breach(result, path)

    def test_rehashed_forgery_and_header_refused(self):
        result = fixture()
        forged = _bundle(result["arrays"], {**result["metadata"], "model": "forged"})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "forged.npz"
            _save_bundle(forged, path)
            with self.assertRaises(ValueError):
                load_saddle_breach(path, expected_identity=result["identity_sha256"])
            bad = Path(temporary) / "bad.npz"
            malicious_archive(bad)
            with patch("numpy.load", side_effect=AssertionError("must not allocate")):
                with self.assertRaises(ValueError):
                    load_saddle_breach(bad, expected_sha256=file_sha256(bad))


if __name__ == "__main__":
    unittest.main()
