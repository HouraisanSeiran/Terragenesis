from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_basin_morphology import generate_morphology, load_morphology, save_morphology
from terrain_pipeline.td_material_field import _bundle, _save_bundle, make_material_field
from tests.test_td_material_field import malicious_archive


def fixture(height=((3.0, 2.0, 1.0),), receiver=(1, 2, -1), volume=None, duration=None,
            protected=None, material_parameters=None, **options):
    height = np.asarray(height, np.float64)
    materials = make_material_field(height.shape, origin_m_xz=(0, 0), spacing_m=1,
                                    protected_mask=protected, parameters=material_parameters or {
                                        "erodibility_range": [1, 1], "weak_path_preference_range": [1, 1],
                                        "erodible_thickness_range_m": [4, 4]})
    result = generate_morphology(height, np.isfinite(height), np.asarray(receiver, np.int64),
                                 np.full(height.shape, 1000.0) if volume is None else volume,
                                 np.full(height.shape, 3600.0) if duration is None else duration,
                                 spacing_m=1, materials=materials, **options)
    return result


class MorphologyTests(unittest.TestCase):
    def test_chain_formula_and_source_mass_export(self):
        result = fixture(parameters={"engineering_open_boundary_cell_ids": [2]})
        expected_depth = 0.15 * np.log(2) * (1 - np.exp(-1))
        arrays = result["arrays"]
        np.testing.assert_allclose(arrays["erosion_depth_m"], [[expected_depth, expected_depth, 0]], rtol=1e-14)
        expected_solid = 2 * expected_depth * 0.9
        self.assertAlmostEqual(result["metadata"]["ledger"]["exported_solid_m3"], expected_solid)
        self.assertAlmostEqual(result["metadata"]["ledger"]["source_mass_kg"], expected_solid * 2650)
        self.assertEqual(result["metadata"]["generation_rounds"], 1)
        self.assertFalse(result["metadata"]["hydrology_coupled_verified"])

    def test_closed_internal_terminal_stores_all_solid(self):
        result = fixture()
        ledger = result["metadata"]["ledger"]
        self.assertAlmostEqual(ledger["source_solid_m3"], ledger["stored_solid_m3"])
        self.assertEqual(ledger["exported_solid_m3"], 0)
        self.assertEqual(result["arrays"]["height_m"][0, 2], 1)

    def test_deposit_porosity_conversion_and_downstream_source(self):
        result = fixture(candidate_kind="deposition")
        arrays = result["arrays"]
        solid = result["metadata"]["ledger"]["source_solid_m3"]
        self.assertAlmostEqual(arrays["deposit_geometry_m3"][0, 2], solid / 0.65)
        self.assertAlmostEqual(result["metadata"]["ledger"]["stored_solid_m3"], 0)
        np.testing.assert_array_equal(arrays["original_height_m"], [[3, 2, 1]])

    def test_branch_confluence_allocates_each_source_once(self):
        result = fixture(height=((3, 2), (4, 1)), receiver=(1, 3, 3, -1), candidate_kind="deposition")
        arrays = result["arrays"]
        self.assertAlmostEqual(arrays["incoming_solid_m3"][1, 1], float(np.sum(arrays["source_solid_m3"])))
        self.assertAlmostEqual(float(np.sum(arrays["deposited_solid_m3"])), float(np.sum(arrays["source_solid_m3"])))

    def test_zero_water_or_duration_no_geometry_or_sediment(self):
        for options in ({"volume": np.zeros((1, 3))}, {"duration": np.zeros((1, 3))}):
            result = fixture(**options)
            self.assertEqual(result["metadata"]["ledger"]["source_solid_m3"], 0)
            np.testing.assert_array_equal(result["arrays"]["height_delta_m"], 0)

    def test_sensitivity_and_material_exhaustion(self):
        ordinary = fixture()
        stronger = fixture(volume=np.full((1, 3), 2000))
        self.assertGreater(stronger["arrays"]["erosion_depth_m"][0, 0], ordinary["arrays"]["erosion_depth_m"][0, 0])
        thin = fixture(material_parameters={"erodible_thickness_range_m": [0.001, 0.001]}, parameters={"erosion_scale_m": 100})
        self.assertTrue(np.all(thin["arrays"]["erosion_depth_m"] <= 0.001))
        self.assertEqual(thin["metadata"]["diagnostics"]["exhausted_cell_count"], 2)

    def test_capacity_and_deposit_bound_remainder_explicit(self):
        result = fixture(parameters={"transport_ratio": 0.00001, "max_deposit_depth_m": 0.0001}, candidate_kind="deposition")
        self.assertTrue(np.all(result["arrays"]["transported_solid_m3"] <= 0.01))
        self.assertTrue(np.all(result["arrays"]["deposit_depth_m"] <= 0.0001 + 1e-15))
        self.assertGreater(result["metadata"]["ledger"]["stored_solid_m3"], 0)

    def test_flat_retains_original_height(self):
        result = fixture(height=((2, 2, 2),))
        self.assertEqual(result["metadata"]["ledger"]["source_solid_m3"], 0)

    def test_protection_rejected_and_zero_water_protection_preserved(self):
        protected = np.asarray([[False, True, False]])
        with self.assertRaises(ValueError):
            fixture(protected=protected)
        result = fixture(protected=protected, volume=np.zeros((1, 3)))
        np.testing.assert_array_equal(result["arrays"]["height_m"], [[3, 2, 1]])

    def test_unknown_terminal_allowed_but_crossing_rejected(self):
        result = fixture(height=((3, 2, np.nan),), receiver=(1, -1, -1), volume=np.asarray([[1000, 1000, 0]]), duration=np.asarray([[3600, 3600, 0]]))
        self.assertEqual(result["metadata"]["ledger"]["exported_solid_m3"], 0)
        with self.assertRaises(ValueError):
            fixture(height=((3, np.nan, 1),), volume=np.asarray([[1000, 0, 1000]]), duration=np.asarray([[3600, 0, 3600]]))

    def test_illegal_graph_and_parameters_refused(self):
        for options in ({"receiver": (2, 2, -1)}, {"receiver": (1, 0, -1), "height": ((2, 2, 1),)},
                        {"height": ((1, 2, 3),)}, {"receiver": (1, 3, -1)},
                        {"parameters": {"engineering_open_boundary_cell_ids": [0]}},
                        {"parameters": {"max_work_cells": 2}}, {"parameters": {"erosion_scale_m": np.nan}},
                        {"volume": np.asarray([[1, -1, 1]])}, {"duration": np.asarray([[1, np.inf, 1]])}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                fixture(**options)

    def test_cold_read_without_generation_and_no_overwrite(self):
        result = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "morphology.npz"
            save_morphology(result, path)
            digest = file_sha256(path)
            with patch("terrain_pipeline.td_basin_morphology.generate_morphology", side_effect=AssertionError("advance forbidden")), patch("terrain_pipeline.td_material_field.make_material_field", side_effect=AssertionError("generation forbidden")):
                loaded = load_morphology(path, expected_sha256=digest, expected_identity=result["identity_sha256"])
                self.assertEqual(result["identity_sha256"], loaded["identity_sha256"])
            with self.assertRaises(FileExistsError):
                save_morphology(result, path)
            self.assertEqual(digest, file_sha256(path))

    def test_forgery_and_malicious_header_rejected(self):
        result = fixture()
        forged = _bundle(result["arrays"], {**result["metadata"], "model": "forged"})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "forged.npz"
            _save_bundle(forged, path)
            with self.assertRaises(ValueError):
                load_morphology(path, expected_identity=result["identity_sha256"])
            bad = Path(temporary) / "malicious.npz"
            malicious_archive(bad)
            with patch("numpy.load", side_effect=AssertionError("allocation forbidden")):
                with self.assertRaises(ValueError):
                    load_morphology(bad, expected_sha256=file_sha256(bad))


if __name__ == "__main__":
    unittest.main()
