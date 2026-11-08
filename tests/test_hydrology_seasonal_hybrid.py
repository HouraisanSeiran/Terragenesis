import copy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.hydrology_detail import _digest as detail_digest
from terrain_pipeline.runoff import LakeGeometry as LakeGeometry
from terrain_pipeline.runoff import load_seasonal_water_balance as load_seasonal_water_balance
from terrain_pipeline.runoff import save_seasonal_water_balance as save_seasonal_water_balance
from terrain_pipeline.runoff import simulate_seasonal_water_balance as simulate_seasonal_water_balance
from terrain_pipeline.runoff import validate_seasonal_water_balance as validate_seasonal_water_balance
from terrain_pipeline.runoff import WeightedLakeGeometry as WeightedLakeGeometry
from terrain_pipeline.runoff import hybrid_column_inputs as hybrid_column_inputs
from terrain_pipeline.runoff import prepare_hybrid_lake_plan as prepare_hybrid_lake_plan
from terrain_pipeline.runoff import simulate_hybrid_lake_water_balance as simulate_hybrid_lake_water_balance
from terrain_pipeline.runoff import fill_lake_patch_to_boundary_saddles as fill_lake_patch_to_boundary_saddles
from terrain_pipeline.runoff import prepare_connected_hybrid_lake_detail as prepare_connected_hybrid_lake_detail
from terrain_pipeline.runoff import validate_hybrid_lake_connectivity as validate_hybrid_lake_connectivity
from terrain_pipeline.runoff import save_hybrid_lake_bundle as save_hybrid_lake_bundle
from terrain_pipeline.runoff import load_hybrid_lake_bundle as load_hybrid_lake_bundle


def fixture():
    height = np.array([[3., 2., 3.], [2., 0., 2.], [3., 2., 3.]])
    plan = {"height_m": height, "owner_domain_id": np.zeros((3, 3), np.int32),
            "identity_sha256": "f" * 64, "seed": 7, "origin_xz_m": [0., 0.], "spacing_m": 10.,
            "domains": [{"domain_id": 0, "kind": "inland", "lake_terminal_index": 4,
                         "lake_spill_elevation_m": 10.}]}
    arrays = {"derived_height_m": np.zeros((2, 2)), "owner_domain_id": np.zeros((2, 2), np.int32)}
    metadata = {"plan_identity": plan["identity_sha256"], "origin_xz_m": [9., 9.], "spacing_m": 2.,
                "raw_provenance": {"archive_sha256": "b" * 64, "generation_metadata": {
                    "artifact_kind": "terrain_diffusion_output", "schema": "hydrology-canonical-td-window-v1",
                    "identity": "c" * 64, "seed": "7", "tile_assembly": [{"fixture": True}]}}}
    detail = {"arrays": arrays, "metadata": metadata}
    resign(detail)
    rain = np.full((12, 3, 3), 30.)
    rain[0] = 250.
    climate = {"precipitation_mm": rain, "potential_et_mm": np.full_like(rain, 100.)}
    return plan, detail, climate


def resign(detail):
    metadata = {key: value for key, value in detail["metadata"].items() if key != "identity"}
    detail["metadata"]["identity"] = detail_digest({"metadata": metadata, "arrays": {
        key: hashlib.sha256(value.tobytes()).hexdigest() for key, value in sorted(detail["arrays"].items())}})


class HybridLakeTests(unittest.TestCase):
    def prepare(self, plan, detail, climate):
        return prepare_hybrid_lake_plan(plan, detail, source_sha256="a" * 64,
                                        domain_id=0, coarse_climate=climate)

    def test_weighted_volume_area_inverse_and_equal_bed_ties(self):
        lake = WeightedLakeGeometry(np.array([[0., 0., 2.]]), np.array([[2., 3., 5.]]),
                                    np.ones((1, 3), bool), 10.)
        self.assertEqual(lake.area(0.), 0.)
        self.assertEqual(lake.area(1.), 5.)
        self.assertEqual(lake.volume(3.), 20.)
        self.assertEqual(lake.level(0.), 0.)
        for level in (0., .5, 2., 3., 9.5):
            self.assertAlmostEqual(lake.level(lake.volume(level)), level)
        self.assertEqual(lake.capacity_m3, 90.)

    def test_partial_cell_replacement_preserves_area_and_capacity(self):
        plan, detail, climate = fixture()
        before = copy.deepcopy(plan)
        prepared = self.prepare(plan, detail, climate)
        columns = prepared["plan"]
        areas, lakes = hybrid_column_inputs(columns)
        self.assertEqual(areas.sum(), 900.)
        self.assertEqual(prepared["audit"]["replacement_cell_ids"], [4])
        self.assertEqual(prepared["audit"]["replacement_areas_m2"], [16.])
        coarse_lake = LakeGeometry(plan["height_m"], plan["owner_domain_id"], plan["domains"][0], 100.)
        for level in (0., 1., 2.5, 9.):
            self.assertAlmostEqual(lakes[0].volume(level), coarse_lake.volume(level))
        self.assertEqual(lakes[0].capacity_m3, coarse_lake.capacity_m3)
        np.testing.assert_array_equal(plan["height_m"], before["height_m"])
        self.assertFalse(prepared["audit"]["seasonal_certification_inherited"])
        self.assertFalse(prepared["audit"]["fine_geometry_certified"])

    def test_boundary_split_conserves_each_parent_and_inherits_its_climate(self):
        plan, detail, climate = fixture()
        detail["metadata"]["origin_xz_m"] = [5., 10.]
        detail["arrays"] = {"derived_height_m": np.array([[1.]]), "owner_domain_id": np.zeros((1, 1), np.int32)}
        resign(detail)
        climate["precipitation_mm"][:, 1, 0] = 10.
        climate["precipitation_mm"][:, 1, 1] = 20.
        prepared = self.prepare(plan, detail, climate)
        self.assertEqual(prepared["audit"]["replacement_cell_ids"], [3, 4])
        self.assertEqual(prepared["audit"]["replacement_areas_m2"], [2., 2.])
        parent = prepared["plan"]["seasonal_parent_cell_id"].ravel()
        areas = prepared["plan"]["seasonal_column_area_m2"].ravel()
        np.testing.assert_array_equal(np.bincount(parent, weights=areas), np.full(9, 100.))
        self.assertEqual(prepared["climate"]["precipitation_mm"][0, 0, -2:].tolist(), [10., 20.])

    def test_lower_fine_bed_changes_capacity_exactly_once(self):
        plan, detail, climate = fixture()
        detail["arrays"]["derived_height_m"][:] = -2.
        resign(detail)
        prepared = self.prepare(plan, detail, climate)
        _, lakes = hybrid_column_inputs(prepared["plan"])
        coarse_lake = LakeGeometry(plan["height_m"], plan["owner_domain_id"], plan["domains"][0], 100.)
        self.assertEqual(lakes[0].capacity_m3 - coarse_lake.capacity_m3, 32.)

    def test_provenance_area_climate_and_geometry_tampering_rejected(self):
        plan, detail, climate = fixture()
        wrong = copy.deepcopy(detail)
        wrong["metadata"]["plan_identity"] = "e" * 64
        resign(wrong)
        with self.assertRaisesRegex(ValueError, "parent identity"):
            self.prepare(plan, wrong, climate)
        prepared = self.prepare(plan, detail, climate)
        wrong = copy.deepcopy(prepared["plan"])
        wrong["seasonal_column_area_m2"][0, -1] += 1.
        with self.assertRaisesRegex(ValueError, "source arrays"):
            hybrid_column_inputs(wrong)
        wrong_climate = copy.deepcopy(prepared["climate"])
        wrong_climate["precipitation_mm"][0, 0, -1] += 1.
        with self.assertRaisesRegex(ValueError, "forcing"):
            hybrid_column_inputs(prepared["plan"], wrong_climate)

    def test_recomputed_periodic_ledger_and_cold_read(self):
        plan, detail, climate = fixture()
        coarse = simulate_seasonal_water_balance(plan, climate=climate)
        hybrid = simulate_hybrid_lake_water_balance(plan, detail, source_sha256="a" * 64,
                                                    domain_id=0, climate=climate)
        result, columns = hybrid["result"], hybrid["plan"]
        self.assertEqual(result["metadata"]["algorithm"], "hydrology-seasonal-hybrid-lake-v1")
        self.assertGreater(result["metadata"]["annual_map_evaluations"], 0)
        np.testing.assert_allclose(coarse["lake_level_m"], result["lake_level_m"], atol=.002)
        expected_rain = climate["precipitation_mm"].sum(axis=(1, 2)) * .1
        np.testing.assert_allclose(result["monthly"]["land_rain_m3"][:, 0] + result["monthly"]["lake_rain_m3"][:, 0], expected_rain)
        with TemporaryDirectory() as folder:
            path = Path(folder) / "hybrid.npz"
            save_seasonal_water_balance(columns, result, path)
            cold = load_seasonal_water_balance(columns, path)
            np.testing.assert_array_equal(cold["lake_geometry"]["0"]["bed_areas_m2"], result["lake_geometry"]["0"]["bed_areas_m2"])
            tampered = copy.deepcopy(cold)
            tampered["lake_geometry"]["0"]["bed_areas_m2"][0] += 1.
            with self.assertRaisesRegex(ValueError, "lake geometry"):
                validate_seasonal_water_balance(columns, tampered)

    def test_priority_flood_minimum_saddle_and_immutable_boundary(self):
        height = np.full((5, 5), 5.)
        height[0, 2] = 4.
        height[1:4, 1:4] = 1.
        filled = fill_lake_patch_to_boundary_saddles(height)
        np.testing.assert_array_equal(filled[1:4, 1:4], np.full((3, 3), 4.))
        np.testing.assert_array_equal(filled[[0, -1]], height[[0, -1]])
        np.testing.assert_array_equal(filled[:, [0, -1]], height[:, [0, -1]])
        np.testing.assert_array_equal(fill_lake_patch_to_boundary_saddles(filled), filled)

    def correction_fixture(self):
        from dataclasses import asdict
        from terrain_pipeline.hydrology_detail import DetailBudget
        plan, detail, climate = fixture()
        height = np.full((5, 5), 5.)
        height[0, 2] = 4.
        height[1:4, 1:4] = 1.
        detail["arrays"] = {"derived_height_m": height, "owner_domain_id": np.zeros((5, 5), np.int32),
                            "original_td_m": np.zeros((5, 5)), "macro_delta_m": height.copy(),
                            "local_channel_delta_m": np.zeros((5, 5)), "shared_boundary_protected": np.zeros((5, 5), bool)}
        detail["metadata"].update(origin_xz_m=[8., 8.], spacing_m=1., budget=asdict(DetailBudget()))
        resign(detail)
        return plan, detail, climate

    def test_correction_combined_budget_shared_boundary_and_source_identity(self):
        plan, detail, climate = self.correction_fixture()
        original = copy.deepcopy(detail)
        corrected = prepare_connected_hybrid_lake_detail(plan, detail, source_sha256="a" * 64, domain_id=0)
        report = corrected["metadata"]["lake_correction"]
        self.assertEqual(report["filled_pixel_count"], 9)
        self.assertEqual(report["fill_volume_m3"], 27.)
        self.assertEqual(report["maximum_fill_m"], 3.)
        self.assertFalse(report["canonical_core_exact_crop"])
        self.assertNotEqual(corrected["metadata"]["identity"], detail["metadata"]["identity"])
        np.testing.assert_array_equal(detail["arrays"]["derived_height_m"], original["arrays"]["derived_height_m"])
        np.testing.assert_array_equal(corrected["arrays"]["original_td_m"], detail["arrays"]["original_td_m"])
        rounded = copy.deepcopy(corrected)
        recorded = rounded["metadata"]["ledger"]["macro_absolute_volume_m3"]
        rounded["metadata"]["ledger"]["macro_absolute_volume_m3"] = float(np.nextafter(recorded, np.inf))
        rounded["metadata"]["lake_correction"]["combined_ledger"]["macro_absolute_volume_m3"] = float(np.nextafter(recorded, np.inf))
        resign(rounded)
        self.prepare(plan, rounded, climate)
        rounded["metadata"]["ledger"]["macro_absolute_volume_m3"] += 1.
        resign(rounded)
        with self.assertRaisesRegex(ValueError, "budget ledger"):
            self.prepare(plan, rounded, climate)
        detail["arrays"]["shared_boundary_protected"][2, 2] = True
        resign(detail)
        with self.assertRaisesRegex(ValueError, "protected shared boundary"):
            prepare_connected_hybrid_lake_detail(plan, detail, source_sha256="a" * 64, domain_id=0)
        detail = original
        detail["metadata"]["budget"]["macro_max_abs_m"] = 2.
        resign(detail)
        with self.assertRaisesRegex(ValueError, "combined.*budget"):
            prepare_connected_hybrid_lake_detail(plan, detail, source_sha256="a" * 64, domain_id=0)

    def test_critical_stage_pocket_rejected_even_when_endpoints_connected(self):
        plan, detail, climate = fixture()
        detail["metadata"].update(origin_xz_m=[9., 9.], spacing_m=1.)
        detail["arrays"] = {"derived_height_m": np.array([[0., 2., 0.], [2., 1., 2.], [0., 2., 0.]]),
                            "owner_domain_id": np.zeros((3, 3), np.int32)}
        resign(detail)
        prepared = self.prepare(plan, detail, climate)
        _, lakes = hybrid_column_inputs(prepared["plan"])
        initial, final = lakes[0].volume(.5), lakes[0].volume(2.5)
        trial = {"metadata": {"domain_ids": [0]}, "lake_volume_m3": np.array([[initial]]),
                 "steps": {"lake_change_m3": np.array([[final - initial]])}}
        with patch('terrain_pipeline.runoff.validate_seasonal_water_balance'):
            report = validate_hybrid_lake_connectivity(plan, detail, prepared, trial)
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["disconnected_pixel_count"], 1)
        self.assertGreater(report["failing_stage_m"], 1.)
        self.assertLess(report["failing_stage_m"], 2.)

    def test_saved_bundle_rebuilds_geometry_and_cold_checks_period(self):
        from terrain_pipeline.hydrology_detail import file_sha256, save_detail
        plan, detail, climate = fixture()
        with TemporaryDirectory() as folder:
            source = Path(folder) / "fine.npz"
            save_detail(source, detail)
            sha = file_sha256(source)
            bundle = simulate_hybrid_lake_water_balance(plan, detail, source_sha256=sha, domain_id=0, climate=climate)
            target = Path(folder) / "bundle"
            manifest = save_hybrid_lake_bundle(plan, detail, bundle, target, source_path=source, source_sha256=sha)
            self.assertEqual(manifest["status"], "periodic_accounts_converged_local_geometry_rejected")
            self.assertIn("ring is dry", bundle["connectivity"]["reason"])
            cold = load_hybrid_lake_bundle(plan, target)
            self.assertEqual(cold["audit"], bundle["audit"])
            self.assertEqual(cold["connectivity"], bundle["connectivity"])
            np.testing.assert_array_equal(cold["result"]["lake_level_m"], bundle["result"]["lake_level_m"])
            with self.assertRaises(FileExistsError):
                save_hybrid_lake_bundle(plan, detail, bundle, target, source_path=source, source_sha256=sha)
            wrong = dict(plan, identity_sha256="d" * 64)
            with self.assertRaisesRegex(ValueError, "parent mismatch"):
                load_hybrid_lake_bundle(wrong, target)


if __name__ == "__main__":
    unittest.main()
