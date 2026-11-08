from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline import soil_water as cover
from terrain_pipeline import environment_product as api
from terrain_pipeline import environment_product as world
from terrain_pipeline.common_infra import file_sha256
from tests.test_environment_mass_processes import rates

ROOT = Path(__file__).resolve().parents[1]
SAVED = ROOT / ".scratch/stage2-world-integration/seasonal-verification-final"


class LandCoverInputTests(unittest.TestCase):
    def test_only_allocated_soil_and_regolith_porosity_supply_thickness(self):
        shape = (1, 3)
        product = {"context": {"height_m": np.zeros(shape), "spacing_m": 30., "origin_native_xz": [0, 0],
                                "valid_mask": np.ones(shape, bool), "ocean_mask": np.zeros(shape, bool),
                                "protected_mask": np.zeros(shape, bool)},
                   "states": {"mass": {"soil_solid_m3": np.array([[0., 90., 180.]]),
                                         "parent_solid_m3": np.array([[900., 0., 0.]]),
                                         "regolith_porosity": np.full(shape, .5)},
                              "soil_chemistry": {"water_m3": np.full(shape, 9.)}},
                   "seasonal": {"climate_driver": {"metadata": {"origin_native_xz": [0, 0], "shape_zx": list(shape)},
                       "arrays": {"monthly_temperature_c": np.full((12,) + shape, 14.)}},
                       "fast_mm": np.full(shape, 999.), "slow_mm": np.full(shape, 999.)}}
        result = cover.assess(product)
        np.testing.assert_array_equal(result["soil_thickness_bulk_m"], [[0., .2, .4]])
        np.testing.assert_array_equal(result["water_state_total_mm"], 10.)
        self.assertEqual(result["growth_support_factor"][0, 0], 0.)
        self.assertGreater(result["growth_support_factor"][0, 2], result["growth_support_factor"][0, 1])
        self.assertEqual(result["land_cover"][0], "bare_rock")


@unittest.skipUnless((SAVED / "initial.npz").exists(), "saved fixed-world seasonal verification product unavailable")
class SavedLandCoverIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = SAVED / "initial.npz"
        cls.old = api.load_product(path, expected_sha256=file_sha256(path))
        cls.driving = json.loads((SAVED / "forcing.json").read_text(encoding="utf-8"))

    def initial(self):
        return api.initialize(self.old["context"], self.old["sources"],
                              {"soil_chemistry": {"water_depth_m": .03}}, mode="seasonal-v2",
                              climate_driver=self.old["seasonal"]["climate_driver"])

    def test_real_g9_delivery_drives_g6_then_actual_g15_growth(self):
        initial = self.initial()
        driving = deepcopy(self.driving)
        driving["mass"] = {"weathering_parameters": rates(1.e-3), "soil_request_solid_m3": 30.}
        delivered = api.advance(initial, driving, 3600.)
        control_driving = deepcopy(driving)
        control_driving["mass"]["soil_request_solid_m3"] = 0.
        potential_only = api.advance(initial, control_driving, 3600.)
        self.assertGreater(potential_only["states"]["mass"]["parent_solid_m3"].sum(), 0.)
        self.assertEqual(potential_only["seasonal"]["land_cover"]["soil_thickness_bulk_m"].sum(), 0.)
        self.assertGreater(delivered["seasonal"]["land_cover"]["soil_thickness_bulk_m"].sum(), 0.)
        grown = api.advance(delivered, self.driving, 3600.)
        bare = api.advance(potential_only, self.driving, 3600.)
        self.assertGreater(grown["results"]["succession"]["ledger"]["photosynthesis_carbon_kg"],
                           bare["results"]["succession"]["ledger"]["photosynthesis_carbon_kg"])
        self.assertGreater(grown["last_transfers"]["soil_root_cohesion_pa"].sum(), bare["last_transfers"]["soil_root_cohesion_pa"].sum())
        self.assertLess(abs(grown["last_budget"]["water_m3_residual"]), 1.e-6)

    def test_completed_snapshot_and_cold_queries_do_not_run_producers(self):
        product = api.advance(self.initial(), self.driving, 3600.)
        snapshot = cover.snapshot(product)
        idx = np.flatnonzero(product["seasonal"]["land_cover"]["active_mask"].ravel())
        np.testing.assert_array_equal(snapshot.arrays["suitability"], product["seasonal"]["land_cover"]["suitability"].ravel()[idx])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process_path, arrays, record = root / "process.npz", root / "snapshot.npz", root / "snapshot.json"
            sha = api.save_product(product, process_path)
            with patch.object(cover, "assess", side_effect=AssertionError("cold query assessed")), \
                 patch.object(api, "advance", side_effect=AssertionError("cold query advanced")), \
                 patch.object(api, "context_from_store", side_effect=AssertionError("cold query read terrain")):
                prepared = cover.prepare_snapshot(process_path, expected_sha256=sha, arrays_path=arrays, record_path=record)
                loaded = world.world_load(arrays, record, expected_world_identity=prepared.world_identity)
                queried = world.world_query(loaded, [loaded.record["x_m"][0]], [loaded.record["z_m"][0]])
                self.assertEqual(queried["suitability"][0], snapshot.arrays["suitability"][0])
                cold = api.load_product(process_path, expected_sha256=sha)
                self.assertEqual(api.product_identity(product), api.product_identity(cold))
                row, col = np.unravel_index(idx[0], product["context"]["height_m"].shape)
                self.assertIn("land_cover", api.query_product(cold, int(row), int(col))["seasonal"])

    def test_saved_seasonal_v1_identity_and_behavior_remain_available(self):
        self.assertNotIn("land_cover", self.old["seasonal"])
        identity = api.product_identity(self.old)
        advanced = api.advance(self.old, self.driving, 3600.)
        self.assertEqual(advanced["algorithm"], "finite-environment-seasonal-coupling-v1")
        self.assertNotIn("land_cover", advanced["seasonal"])
        self.assertEqual(api.product_identity(self.old), identity)
        final_path = SAVED / "final.npz"
        prior_final = api.load_product(final_path, expected_sha256=file_sha256(final_path))
        while advanced["time_s"] < prior_final["time_s"]:
            advanced = api.advance(advanced, self.driving, 3600.)
        self.assertEqual(api.product_identity(advanced), api.product_identity(prior_final))

    def test_v2_hydraulic_handoff_debits_once_and_v1_refuses(self):
        initial = self.initial()
        driving = deepcopy(self.driving)
        mask = initial["context"]["valid_mask"] & ~initial["context"]["ocean_mask"] & ~initial["context"]["protected_mask"]
        driving.update(hydraulic_handoff_mask=mask, groundwater={"surface_conductance_m2_s": 0.},
                       mass={"weathering_parameters": rates(1.e-3), "transport_fraction_per_s": .0001})
        result = api.advance(initial, driving, 3600.)
        transfers = result["last_transfers"]
        self.assertGreater(transfers["external_hydraulic_water_m3"].sum(), 0.)
        np.testing.assert_array_equal(result["states"]["groundwater"]["surface_water_m3"][mask], 0.)
        np.testing.assert_array_equal(result["states"]["mass"]["river_sediment_solid_m3"][mask], 0.)
        self.assertEqual(result["cumulative_ledger"]["external_hydraulic_water_m3"], transfers["external_hydraulic_water_m3"].sum())
        self.assertEqual(result["cumulative_ledger"]["external_hydraulic_solid_m3"], transfers["external_hydraulic_solid_m3"].sum())
        self.assertLess(abs(result["last_budget"]["water_m3_residual"]), 1.e-6)
        self.assertLess(abs(result["last_budget"]["solid_m3_residual"]), 1.e-6)
        with self.assertRaisesRegex(ValueError, "unsupported product forcing"):
            api.advance(self.old, driving, 3600.)
        driving["hydraulic_handoff_mask"] = mask.astype(float)
        with self.assertRaisesRegex(ValueError, "matching bool"):
            api.advance(initial, driving, 3600.)
