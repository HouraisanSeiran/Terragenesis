from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline import environment_product as product
from terrain_pipeline import environment_regional_hydraulics as climate
from terrain_pipeline import soil_water as seasonal
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.climate_forcing import advance_soil

STORE = Path(__file__).resolve().parents[1] / ".scratch/river-generation-review/real-lakes-42km"


class BucketFluxAdapterTests(unittest.TestCase):
    def test_flux_exposure_preserves_default_numbers(self):
        states = np.array([[0., 50., 149.], [1., 3., 5.], [2., 4., 6.]])
        rain = np.array([10., 20., 100.])
        args = {"dt_s": 1800., "parameters": RunoffParameters()}
        old = advance_soil(rain, states, **args)
        detailed = advance_soil(rain, states, return_fluxes=True, **args)
        for before, after in zip(old, detailed[:4]):
            np.testing.assert_array_equal(before, after)
        next_states, release, et, _, fluxes = detailed
        np.testing.assert_allclose(next_states[0] - states[0], fluxes["infiltration_mm"] - et - fluxes["percolation_mm"])
        np.testing.assert_allclose(next_states[1] - states[1], fluxes["excess_mm"] - fluxes["fast_release_mm"])
        np.testing.assert_allclose(next_states[2] - states[2], fluxes["percolation_mm"] - fluxes["slow_release_mm"])
        np.testing.assert_array_equal(release, fluxes["fast_release_mm"] + fluxes["slow_release_mm"])


@unittest.skipUnless((STORE / "registry.json").exists(), "same-world saved TD source unavailable")
class SeasonalCouplingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = climate.build_climate_driver(STORE)
        cls.context, cls.sources = product.context_from_store(STORE, 600, 300, 64)

    def initial(self, *, frozen=False, crop=False):
        initial = {"soil_chemistry": {"water_depth_m": .03, "salinity_kg_m3": 1.}}
        if frozen:
            initial["frozen_ground"] = {"liquid_water_m": 0., "ground_ice_m": .1, "soil_temperature_c": 0.}
        ctx, sources = (product.context_from_store(STORE, 610, 310, 33) if crop else (self.context, self.sources))
        return product.initialize(ctx, sources, initial, mode="seasonal", climate_driver=self.driver,
                                  seasonal_parameters={"initial_swe_mm": 20.,
                                      "initial_swe_source": "declared engineering initial snow, not observation"})

    def forcing(self):
        return {"climate": {"external_inflow_kg_per_s": 10., "wind_speed_m_s": 1., "uplift_gain": .01},
                "radiation": {"longitude_deg": 180.}}

    def test_actual_snow_bucket_single_soil_owner_and_next_interval_et_recycle(self):
        old = self.initial()
        first = product.advance(old, self.forcing(), 3600.)
        t = first["last_transfers"]
        self.assertGreater(t["seasonal_melt_m3"].sum(), 0.)
        self.assertGreater(t["g5_et_m3"].sum(), 0.)
        self.assertGreater(t["g5_release_m3"].sum(), 0.)
        np.testing.assert_allclose(first["states"]["soil_chemistry"]["water_m3"] - old["states"]["soil_chemistry"]["water_m3"],
                                   t["g5_infiltration_m3"] - t["g5_et_m3"] - t["g5_percolation_m3"], atol=1.e-10)
        np.testing.assert_allclose((first["seasonal"]["fast_mm"] - old["seasonal"]["fast_mm"]) * .9,
                                   t["seasonal_liquid_to_land_m3"] - t["g5_infiltration_m3"] - t["g5_fast_release_m3"], atol=1.e-10)
        np.testing.assert_allclose((first["seasonal"]["slow_mm"] - old["seasonal"]["slow_mm"]) * .9,
                                   t["g5_percolation_m3"] - t["g5_slow_release_m3"], atol=1.e-10)
        np.testing.assert_allclose(t["g5_release_m3"], t["g5_fast_release_m3"] + t["g5_slow_release_m3"])
        np.testing.assert_array_equal(first["states"]["frozen_ground"]["snow_swe_m"], 0.)
        np.testing.assert_array_equal(first["seasonal"]["pending_et_kg"], t["g5_et_m3"] * 1000.)
        self.assertEqual(first["results"]["climate"]["ledger"]["recycle_kg"], 0.)
        second = product.advance(first, self.forcing(), 3600.)
        self.assertAlmostEqual(second["results"]["climate"]["ledger"]["recycle_kg"],
                               first["seasonal"]["pending_et_kg"].sum(), places=7)
        np.testing.assert_array_equal(second["last_transfers"]["seasonal_et_recycle_kg"], first["seasonal"]["pending_et_kg"])
        for result in (first, second):
            self.assertLess(abs(result["last_budget"]["water_m3_residual"]), 1.e-6)
            np.testing.assert_array_equal(result["context"]["receiver"], old["context"]["receiver"])
            np.testing.assert_array_equal(result["context"]["height_m"], old["context"]["height_m"])
        self.assertGreater(first["pending_packets"]["subsurface_salt_kg"].sum(), 0.)

    def test_g12_freezing_scales_the_actual_g5_infiltration_consumer(self):
        warm = product.advance(self.initial(), self.forcing(), 3600.)
        frozen = product.advance(self.initial(frozen=True), self.forcing(), 3600.)
        self.assertLess(frozen["last_transfers"]["g5_infiltration_m3"].sum(), warm["last_transfers"]["g5_infiltration_m3"].sum())
        self.assertGreater(frozen["seasonal"]["fast_mm"].sum(), warm["seasonal"]["fast_mm"].sum())

    def test_cold_resume_query_and_fixed_support_crop(self):
        first = product.advance(self.initial(crop=True), self.forcing(), 3600.)
        self.assertEqual(first["seasonal"]["pending_et_kg"].shape, (64, 64))
        self.assertEqual(first["seasonal"]["snow_swe_mm"].shape, (33, 33))
        self.assertGreater(first["cumulative_ledger"]["precipitation_unmodelled_export_m3"], 0.)
        outside = first["seasonal"]["pending_et_kg"].copy()
        outside[10:43, 10:43] = 0.
        np.testing.assert_array_equal(outside, 0.)
        direct = product.advance(first, self.forcing(), 3600.)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seasonal.npz"
            sha = product.save_product(first, path)
            with patch.object(climate, "_saved_terrain_support", side_effect=AssertionError("source regenerated")), \
                 patch.object(product, "advance", side_effect=AssertionError("query advanced")), \
                 patch.object(product, "context_from_store", side_effect=AssertionError("source read")):
                loaded = product.load_product(path, expected_sha256=sha)
                self.assertEqual(product.product_identity(first), product.product_identity(loaded))
                query = product.query_product(loaded, 2, 2)["seasonal"]
                self.assertEqual(query["snow_swe_mm"], first["seasonal"]["snow_swe_mm"][2, 2])
                self.assertEqual(query["driver_identity_sha256"], self.driver["identity_sha256"])
                self.assertEqual(query["source_world_identity"], self.sources["source_world_identity"])
                self.assertEqual(query["initial_swe_source"], first["seasonal"]["initial_swe_source"])
                self.assertIn("material", query)
            resumed = product.advance(loaded, self.forcing(), 3600.)
            self.assertEqual(product.product_identity(direct), product.product_identity(resumed))

    def test_explicit_boundary_source_binding_and_time_bounds(self):
        old = self.initial()
        with self.assertRaisesRegex(ValueError, "explicitly declared"):
            product.advance(old, {}, 3600.)
        with self.assertRaisesRegex(ValueError, "at most 3600"):
            product.advance(old, self.forcing(), 7200.)
        driving = self.forcing()
        driving["rainfall_m_s"] = 1.
        with self.assertRaisesRegex(ValueError, "pinned climate"):
            product.advance(old, driving, 3600.)
        wrong_sources = deepcopy(self.sources)
        wrong_sources["source_world_identity"] = "wrong-world"
        with self.assertRaisesRegex(ValueError, "source binding mismatch"):
            product.initialize(self.context, wrong_sources, mode="seasonal", climate_driver=self.driver)
        wrong_bed = deepcopy(self.context)
        wrong_bed["source_height_m"][0, 0] += 1.
        with self.assertRaisesRegex(ValueError, "same saved TD-derived bed"):
            product.initialize(wrong_bed, self.sources, mode="seasonal", climate_driver=self.driver)
        with self.assertRaisesRegex(ValueError, "cannot be overridden"):
            product.initialize(self.context, self.sources, {"mass": {"solubility": .9}},
                               mode="seasonal", climate_driver=self.driver)
