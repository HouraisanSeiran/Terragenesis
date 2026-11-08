from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.environment_regional_hydraulics import advance_climate_driver, build_climate_driver, crop_climate_result, initial_climate_state, load_climate_driver, load_climate_state, save_climate_driver, save_climate_state, validate_climate_driver, validate_climate_state
from terrain_pipeline.climate_forcing import _interval_mean_monthly


STORE = Path(__file__).resolve().parents[1] / ".scratch/river-generation-review/real-lakes-42km"


@unittest.skipUnless((STORE / "registry.json").exists(), "saved same-world TD review store unavailable")
class SameWorldClimateDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = build_climate_driver(STORE)

    def step(self, state, end_time_s, recycle=None):
        return advance_climate_driver(self.driver, state, end_time_s,
            external_inflow_kg_per_s=10., wind_speed_m_s=1., uplift_gain=.01,
            et_recycle_kg=recycle)

    def test_saved_support_and_actual_same_bed(self):
        d = self.driver
        self.assertEqual(d["metadata"]["origin_native_xz"], [43700, 42100])
        self.assertEqual(d["metadata"]["shape_zx"], [64, 64])
        self.assertEqual(d["metadata"]["wind_bearing"], [-1, 0])
        self.assertEqual(d["metadata"]["source"]["support_bounds_native_xz_exclusive"],
                         [43450, 41850, 44514, 42414])
        root = STORE / "versions/3e2381055b1a403a9e854cf4ba6d6f29"
        with np.load(root / "water/river-network.npz", allow_pickle=False) as archive:
            raw = archive["node_raw_bed_m"].reshape(1400, 1400)[600:664, 300:364]
        np.testing.assert_array_equal(raw, d["arrays"]["elevation_m"])
        self.assertLess(d["arrays"]["orographic_gradient"].min(), 0.)
        self.assertGreater(d["arrays"]["orographic_gradient"].max(), 0.)
        self.assertLess(d["arrays"]["monthly_temperature_c"].min(), 0.)
        self.assertGreater(d["arrays"]["monthly_temperature_c"].max(), 0.)

    def test_actual_cfl_rain_inventory_and_explicit_external_boundary(self):
        old = initial_climate_state(self.driver, vapour_kg=1000.)
        new, forcing = self.step(old, 3600.)
        ledger = forcing["ledger"]
        self.assertEqual(ledger["substeps"], 120)
        self.assertEqual(ledger["max_cfl"], 1.)
        self.assertEqual(ledger["inflow_kg"], 64 * 10 * 3600)
        self.assertGreater(ledger["outflow_kg"], 0.)
        self.assertGreater(ledger["precipitation_kg"], 0.)
        self.assertLess(abs(ledger["closure_residual_kg"]), 1e-6)
        self.assertAlmostEqual(forcing["precipitation_mm"].sum() * 900., ledger["precipitation_kg"])
        np.testing.assert_allclose(forcing["rainfall_m_s"] * 3600. * 1000., forcing["precipitation_mm"])
        self.assertTrue(validate_climate_state(new, self.driver))
        np.testing.assert_array_equal(old["arrays"]["vapour_kg"], 1000.)

    def test_et_is_recycled_once_by_caller_next_interval(self):
        initial = initial_climate_state(self.driver)
        first, a = self.step(initial, 30.)
        recycle = np.full((64, 64), 7.)
        second, b = self.step(first, 60., recycle)
        _, c = self.step(second, 90.)
        self.assertEqual(a["ledger"]["recycle_kg"], 0.)
        self.assertEqual(b["ledger"]["recycle_kg"], 4096 * 7.)
        self.assertEqual(c["ledger"]["recycle_kg"], 0.)
        self.assertNotIn("pending_et_kg", second["arrays"])

    def test_cold_resume_and_steps_never_read_source_again(self):
        old = initial_climate_state(self.driver, time_s=120.)
        first, _ = self.step(old, 240.)
        expected, expected_forcing = self.step(first, 360., np.ones((64, 64)))
        with tempfile.TemporaryDirectory() as directory:
            driver_path, state_path = Path(directory) / "driver.npz", Path(directory) / "state.npz"
            save_climate_driver(driver_path, self.driver)
            save_climate_state(state_path, first)
            driver = load_climate_driver(driver_path, expected_sha256=file_sha256(driver_path))
            state = load_climate_state(state_path, expected_sha256=file_sha256(state_path))
            with patch('terrain_pipeline.environment_regional_hydraulics._saved_terrain_support',
                       side_effect=AssertionError("source read during continuation")):
                with patch('terrain_pipeline.environment_regional_hydraulics.file_sha256',
                           side_effect=AssertionError("source rehash during continuation")):
                    actual, forcing = advance_climate_driver(driver, state, 360.,
                        external_inflow_kg_per_s=10., wind_speed_m_s=1., uplift_gain=.01,
                        et_recycle_kg=np.ones((64, 64)))
            self.assertEqual(expected["identity_sha256"], actual["identity_sha256"])
            self.assertEqual(expected_forcing["ledger"], forcing["ledger"])
            np.testing.assert_array_equal(expected_forcing["precipitation_mm"], forcing["precipitation_mm"])

    def test_absolute_calendar_and_adjacent_queries_crop_same_result(self):
        start = 31536000. + 86400. * 20
        state = initial_climate_state(self.driver, time_s=start)
        _, forcing = self.step(state, start + 3600.)
        expected = _interval_mean_monthly(self.driver["arrays"]["monthly_temperature_c"].reshape(12, -1),
                                         start, start + 3600.).reshape(64, 64)
        np.testing.assert_array_equal(expected, forcing["air_temperature_c"])
        left = crop_climate_result(forcing, row=0, col=0, shape_zx=(64, 32))
        right = crop_climate_result(forcing, row=0, col=32, shape_zx=(64, 32))
        np.testing.assert_array_equal(np.concatenate([left["precipitation_mm"], right["precipitation_mm"]], axis=1),
                                      forcing["precipitation_mm"])
        self.assertEqual(left["ledger"], right["ledger"])
        self.assertTrue(validate_climate_driver(self.driver))

    def test_missing_halo_is_rejected_without_padding(self):
        with self.assertRaisesRegex(ValueError, "does not cover"):
            build_climate_driver(STORE, origin_native_xz=(43400, 42100))
        with self.assertRaisesRegex(ValueError, "4096"):
            build_climate_driver(STORE, shape_zx=(65, 65))

    def test_invalid_time_and_unresolved_boundary_are_rejected(self):
        state = initial_climate_state(self.driver)
        for end in (0., -1., float("nan")):
            with self.assertRaises(ValueError):
                self.step(state, end)
        with self.assertRaises((ValueError, TypeError)):
            advance_climate_driver(self.driver, state, 30., external_inflow_kg_per_s=None,
                                   wind_speed_m_s=1., uplift_gain=.01)


if __name__ == "__main__":
    unittest.main()
