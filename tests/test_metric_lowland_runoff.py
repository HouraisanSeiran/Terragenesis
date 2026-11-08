import unittest
from dataclasses import replace

import numpy as np

from terrain_pipeline.runoff import LowlandRunoffConfig as LowlandRunoffConfig
from terrain_pipeline.runoff import OBJECT_FLAGS as OBJECT_FLAGS
from terrain_pipeline.runoff import classify_and_route as classify_and_route


def fixture():
    height = np.tile([40., 30., 20., 2., 1., .5, 0.], (3, 1))
    receiver = np.full(height.size, -1, np.int64)
    receiver[7:13] = np.arange(8, 14)
    order = np.arange(height.size, dtype=np.int64)
    area = np.full(height.size, 100.)
    area[7:14] = np.arange(1, 8) * 100.
    runoff = np.zeros((12, *height.shape))
    runoff[:, 1, 0] = 1000.
    config = LowlandRunoffConfig(
        relief_radius_m=10., lowland_relief_m=2., lowland_slope=.1,
        upland_initiation_area_m2=10000., lowland_initiation_area_m2=10000.,
        channel_q_threshold_m3_s=.00001, monthly_evaporation_depth_m=0.,
        monthly_release_fraction=.5)
    return height, np.zeros_like(height), receiver, order, area, runoff, config


def run(data, config=None):
    height, raises, receiver, order, area, runoff, defaults = data
    return classify_and_route(height, raises, receiver, order, area, 10., runoff,
                              config=defaults if config is None else config)


class LowlandRunoffTests(unittest.TestCase):
    def test_suppressed_lowland_source_keeps_water_and_original_graph(self):
        data = fixture()
        data[5][:] = 0.
        data[5][:, 1, 4] = 3.
        data[1][1, 4] = .1
        before = data[2].copy()
        result = run(data)
        arrays, metadata = result["arrays"], result["metadata"]
        self.assertFalse(arrays["permanent_channel_mask"].any())
        self.assertFalse(arrays["seasonal_channel_mask"].any())
        self.assertGreater(arrays["final_storage_m3"].sum(), 0.)
        np.testing.assert_array_equal(arrays["receiver"], before)
        ledger = metadata["month_ledger"]
        accounted = (ledger[-1]["storage_after_m3"] + sum(
            row["unknown_boundary_export_m3"] + row["unresolved_terminal_export_m3"]
            + row["evaporation_m3"] for row in ledger))
        self.assertAlmostEqual(accounted, 3. * 36)

    def test_upland_trunk_remains_continuous_through_lowland(self):
        data = fixture()
        config = replace(data[-1], upland_initiation_area_m2=200.)
        arrays = run(data, config)["arrays"]
        self.assertFalse(arrays["lowland_mask"][1, 1])
        self.assertTrue(arrays["lowland_mask"][1, 4])
        self.assertFalse(arrays["permanent_initiation_mask"][1, 4])
        self.assertTrue(arrays["permanent_channel_mask"][1, 1:].all())
        np.testing.assert_allclose(arrays["mean_full_network_q_m3_s"][1],
                                   arrays["mean_full_network_q_m3_s"][1, 0])
        # The geomorphic classification is invariant under an elevation datum.
        shifted = list(data)
        shifted[0] = data[0] + 5000.
        np.testing.assert_array_equal(run(tuple(shifted), config)["arrays"]["lowland_mask"],
                                      arrays["lowland_mask"])
        data[5][:, 1, 0] = 3.
        data[1][1, 4] = .1
        config = replace(config, channel_q_threshold_m3_s=.0000007,
                         monthly_release_fraction=0., monthly_evaporation_depth_m=.015)
        arrays = run(data, config)["arrays"]
        self.assertEqual(arrays["wet_month_count"][1, 4], 0)
        self.assertTrue(arrays["permanent_channel_mask"][1, 1:].all())

    def test_first_terrain_receiver_has_no_object_type_precedence(self):
        data = fixture()
        data[1][1, 4] = .1
        config = replace(data[-1], lowland_initiation_area_m2=550.)
        arrays = run(data, config)["arrays"]
        self.assertTrue(arrays["permanent_channel_mask"][1, 5])
        self.assertEqual(arrays["first_receiving_object_id"][1, 3], 11)
        self.assertEqual(arrays["first_receiving_object_flags"][1, 3],
                         OBJECT_FLAGS["wetland"])
        # A different storage class at the same first location is still first.
        data[1][1, 4] = 0.
        arrays = run(data, config)["arrays"]
        self.assertEqual(arrays["first_receiving_object_id"][1, 3], 11)
        self.assertEqual(arrays["first_receiving_object_flags"][1, 3],
                         OBJECT_FLAGS["floodplain"])
        config = replace(config, upland_initiation_area_m2=350.)
        arrays = run(data, config)["arrays"]
        self.assertEqual(arrays["first_receiving_object_id"][1, 2], 10)
        self.assertEqual(arrays["first_receiving_object_flags"][1, 2], OBJECT_FLAGS["river"])
        # Nearby off-path candidates cannot receive flow across the divide.
        self.assertNotEqual(arrays["first_receiving_object_id"][1, 3], 4)

    def test_finite_storage_overflow_and_unresolved_terminals_balance(self):
        data = fixture()
        data[2][12] = -1
        data[1][1, 4:6] = .1
        data[5][:, 0, 0] = 7.
        config = replace(data[-1], monthly_evaporation_depth_m=.015)
        result = run(data, config)
        arrays = result["arrays"]
        self.assertTrue(np.all(arrays["final_storage_m3"] <= arrays["storage_capacity_m3"]))
        ledger = result["metadata"]["month_ledger"]
        self.assertGreater(sum(row["overflow_m3"] for row in ledger), 0.)
        self.assertGreater(sum(row["storage_release_m3"] for row in ledger), 0.)
        self.assertGreater(sum(row["evaporation_m3"] for row in ledger), 0.)
        self.assertGreater(sum(row["unresolved_terminal_export_m3"] for row in ledger), 0.)
        self.assertAlmostEqual(sum(row["unknown_boundary_export_m3"] for row in ledger), 7. * 36)
        for row in ledger:
            self.assertAlmostEqual(row["input_runoff_m3"] + row["storage_before_m3"],
                row["storage_after_m3"] + row["evaporation_m3"]
                + row["unknown_boundary_export_m3"] + row["unresolved_terminal_export_m3"])
        incoming = np.zeros(data[0].size)
        active = np.flatnonzero(data[2] >= 0)
        np.add.at(incoming, data[2][active], arrays["last_year_outflow_m3"].ravel()[active])
        np.testing.assert_allclose(
            arrays["last_year_local_runoff_m3"].ravel() + incoming
            + arrays["last_year_initial_storage_m3"].ravel(),
            arrays["last_year_outflow_m3"].ravel()
            + arrays["last_year_evaporation_m3"].ravel()
            + arrays["final_storage_m3"].ravel(), rtol=1e-12, atol=1e-10)

    def test_climate_changes_initiation_and_is_deterministic(self):
        data = fixture()
        config = replace(data[-1], upland_initiation_area_m2=200.)
        wet = run(data, config)
        repeat = run(data, config)
        for key in wet["arrays"]:
            np.testing.assert_array_equal(wet["arrays"][key], repeat["arrays"][key])
        self.assertEqual(wet["metadata"], repeat["metadata"])
        data[5][4:] = 0.
        seasonal = run(data, config)["arrays"]
        self.assertFalse(seasonal["permanent_channel_mask"].any())
        self.assertTrue(seasonal["seasonal_channel_mask"][1, 1:].all())
        data[5][:] = 0.
        dry = run(data, config)["arrays"]
        self.assertFalse(dry["permanent_channel_mask"].any())
        self.assertFalse(dry["seasonal_channel_mask"].any())

    def test_rejects_nonterrain_jumps_uphill_and_invalid_dag(self):
        for mutation in ("jump", "uphill", "order", "nonfinite"):
            with self.subTest(mutation=mutation):
                data = fixture()
                if mutation == "jump":
                    data[2][7] = 13
                elif mutation == "uphill":
                    data[0][1, 1] = 50.
                elif mutation == "order":
                    data[3][7:14] = data[3][7:14][::-1]
                else:
                    data[5][0, 1, 0] = np.nan
                with self.assertRaises(ValueError):
                    run(data)


if __name__ == "__main__":
    unittest.main()
