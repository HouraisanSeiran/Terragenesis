import unittest
from dataclasses import replace

import numpy as np

from terrain_pipeline.climate_forcing import MONTH_EDGES_S, YEAR_S, NoiseStormParameters as StormParameters, interval_seasonal_storm_rain_mm
from terrain_pipeline.runoff import LowlandRunoffConfig as LowlandRunoffConfig
from terrain_pipeline.runoff import prepare_event_routing as prepare_event_routing


class MetricEventResponseTests(unittest.TestCase):
    def test_storm_absolute_samples_and_time_partition_agree(self):
        x, z = np.meshgrid(np.arange(-4, 5) * 12000., np.arange(-3, 4) * 12000.)
        params = StormParameters(occurrence_probability=1.)
        monthly = np.ones((12, *x.shape)) * 80.
        def rain(x_values, z_values, months, start, end):
            return interval_seasonal_storm_rain_mm(
                932, x_values, z_values, start, end,
                monthly_precipitation_mm=months, storm_parameters=params)
        whole = rain(x, z, monthly, 0., 86400.)
        first = rain(x, z, monthly, 0., 17321.)
        last = rain(x, z, monthly, 17321., 86400.)
        self.assertGreater(whole["storm_depth_mm"].sum(), 0.)
        stripe = rain(x[:, 3:6], z[:, 3:6], monthly[:, :, 3:6], 0., 86400.)
        for key in whole:
            np.testing.assert_allclose(whole[key], first[key] + last[key], atol=1e-12)
            np.testing.assert_array_equal(whole[key][:, 3:6], stripe[key])
            np.testing.assert_array_equal(whole[key], rain(x, z, monthly, 0., 86400.)[key])
        other = interval_seasonal_storm_rain_mm(933, x, z, 0., 86400.,
            monthly_precipitation_mm=monthly, storm_parameters=params)
        self.assertFalse(np.array_equal(whole["storm_depth_mm"], other["storm_depth_mm"]))

    def test_season_repeats_smoothly_and_preserves_annual_target(self):
        monthly = np.array([5., 10., 40., 100., 90., 40., 5., 3., 7., 2., 1., 50.])[:, None]
        params = StormParameters(occurrence_probability=0.)
        def rain(start, end):
            return interval_seasonal_storm_rain_mm(1, [0.], [0.], start, end,
                monthly_precipitation_mm=monthly, storm_parameters=params)["total_depth_mm"]
        annual = sum(rain(float(a), float(b)) for a, b in zip(MONTH_EDGES_S, MONTH_EDGES_S[1:]))
        np.testing.assert_allclose(annual, monthly.sum(), rtol=1e-14)
        np.testing.assert_allclose(rain(1000., 7200.), rain(YEAR_S + 1000., YEAR_S + 7200.))
        np.testing.assert_allclose(rain(YEAR_S - 1., YEAR_S), rain(YEAR_S, YEAR_S + 1.), rtol=1e-6)
        np.testing.assert_allclose(rain(YEAR_S - 2000., YEAR_S + 3000.),
                                   rain(YEAR_S - 2000., YEAR_S) + rain(YEAR_S, YEAR_S + 3000.))

    def test_event_conservation_finite_cap_and_terminal_scopes(self):
        receiver = np.array([1, 2, -1, -1])
        order = np.arange(4)
        capacity = np.array([0., 10., 4., 0.])
        initial = np.array([0., 3., 1., 0.])
        config = LowlandRunoffConfig(monthly_evaporation_depth_m=.015)
        router = prepare_event_routing(receiver, order, capacity, initial,
                                       np.array([False, False, False, True]), 10., config=config)
        local = np.array([100., 0., 0., 7.])
        result = router.step(local, 3600.)
        arrays, ledger = result["arrays"], result["ledger"]
        incoming = np.zeros(4)
        np.add.at(incoming, receiver[:2], arrays["outflow_m3"][:2])
        np.testing.assert_allclose(initial + local + incoming,
            arrays["outflow_m3"] + arrays["storage_m3"] + arrays["evaporation_m3"], atol=1e-12)
        self.assertTrue(np.all(arrays["storage_m3"] <= capacity))
        self.assertGreater(ledger["overflow_m3"], 0.)
        self.assertGreater(ledger["unresolved_terminal_export_m3"], 0.)
        self.assertEqual(ledger["unknown_boundary_export_m3"], 7.)
        self.assertAlmostEqual(ledger["balance_residual_m3"], 0., places=11)
        np.testing.assert_array_equal(initial, [0., 3., 1., 0.])
        before = router.storage.copy()
        with self.assertRaises(ValueError):
            router.step(np.array([np.nan, 0., 0., 0.]), 3600.)
        np.testing.assert_array_equal(before, router.storage)

    def test_dry_recession_uses_physical_time_and_keeps_source_labels(self):
        source = dict(receiver=np.array([-1]), topological_order=np.array([0]),
                      storage_capacity_m3=np.array([100.]), final_storage_m3=np.array([80.]),
                      permanent_channel_mask=np.array([False]), seasonal_channel_mask=np.array([True]))
        originals = {key: value.copy() for key, value in source.items()}
        config = replace(LowlandRunoffConfig(), monthly_evaporation_depth_m=0.)
        def make_router():
            return prepare_event_routing(source["receiver"], source["topological_order"],
                source["storage_capacity_m3"], source["final_storage_m3"], np.array([False]), 10., config=config)
        whole, split = make_router(), make_router()
        monthly = whole.step(np.zeros(1), 30. * 86400.)
        first = split.step(np.zeros(1), 86400.)
        stored_snapshot = first["arrays"]["storage_m3"].copy()
        for _ in range(29):
            last = split.step(np.zeros(1), 86400.)
        np.testing.assert_allclose(monthly["arrays"]["storage_m3"], [80. * .65], rtol=1e-14)
        np.testing.assert_allclose(last["arrays"]["storage_m3"], monthly["arrays"]["storage_m3"], rtol=1e-14)
        self.assertGreater(first["arrays"]["routed_q_m3_s"][0], last["arrays"]["routed_q_m3_s"][0])
        np.testing.assert_array_equal(first["arrays"]["storage_m3"], stored_snapshot)
        split.step(np.array([1000000.]), 3600.)
        for key in source:
            np.testing.assert_array_equal(source[key], originals[key])


if __name__ == "__main__":
    unittest.main()
