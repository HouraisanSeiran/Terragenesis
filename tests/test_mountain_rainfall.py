"""Small helper regressions and pinned mountain provenance checks only."""

import unittest

import numpy as np

from tools.verify_mountain_rainfall import (
    SOURCE_NAMES, downstream_order, independent_budget, load_source, rainfall_schedule,
    response_units, spatial_sum,
)


class MountainRainfallTests(unittest.TestCase):
    def test_full_saved_mountains_and_physical_areas(self):
        for name in SOURCE_NAMES:
            with self.subTest(name=name):
                source = load_source(name)
                height = source["height_m"]
                self.assertEqual(height.shape, (487, 487))
                self.assertGreater(np.ptp(height), 100)
                self.assertEqual(source["spacing_m"], 30)
                self.assertTrue(source["raw_available"])
                self.assertEqual(source["raw_config"]["conditioning_mode"], "geographic_v5")
                owner, area, mean, low, high = response_units(height, 30)
                self.assertLessEqual(area.size, 64)
                np.testing.assert_array_equal(area, np.bincount(owner.ravel()) * 900)
                self.assertEqual(area.sum(), height.size * 900)
                self.assertTrue(((mean >= low) & (mean <= high)).all())
                order = downstream_order(source["receiver"], source["outlet_mask"])
                flow = spatial_sum(area * 1e-8, owner, area, 30,
                                   source["receiver"], order)
                self.assertAlmostEqual(flow[source["outlet_mask"]].sum(), area.sum() * 1e-8, places=8)

    def test_land_owner_has_no_ocean_area(self):
        height = np.array([[-4., 1., 2.], [0., 3., 4.]])
        owner, area, mean, low, high = response_units(height, 10, 2)
        np.testing.assert_array_equal(owner[height <= 0], -1)
        self.assertEqual(area.sum(), 400)
        np.testing.assert_array_equal(area, np.bincount(owner[height > 0]) * 100)

    def test_graph_rejects_cycles_and_outlet_mismatch(self):
        for receiver, outlets in (([1, 0], [False, False]),
                                  ([-1, 0], [False, True]),
                                  ([-1, 3], [True, False])):
            with self.assertRaises(ValueError):
                downstream_order(receiver, outlets)

    def test_spatial_diagnostic_does_not_double_count_area(self):
        owner = np.array([[0, 0, 1]])
        area = np.array([200., 100.])
        receiver = np.array([1, 2, -1])
        order = downstream_order(receiver, [[False, False, True]])
        flow = spatial_sum(np.array([2., 3.]), owner, area, 10, receiver, order)
        np.testing.assert_allclose(flow, [[1., 2., 5.]])

    def test_deterministic_storm_with_dry_recession(self):
        heights = np.linspace(100, 900, 64)
        time, dry = rainfall_schedule(heights, "dry_storm")
        _, wet = rainfall_schedule(heights, "wet_storm")
        np.testing.assert_array_equal(dry, wet)
        self.assertEqual(dry.shape, (1344, 64))
        self.assertTrue((dry[time >= 18] == 0).all())
        self.assertTrue((dry[time < 6] == 0).all())
        self.assertGreater(dry[:, -1].sum(), dry[:, 0].sum())
        _, finer = rainfall_schedule(heights, "dry_storm", dt_s=450)
        np.testing.assert_allclose(dry.sum(axis=0) * 900, finer.sum(axis=0) * 450)

    def test_invalid_response_units_and_schedule(self):
        for height, spacing in (([[1, 1]], 30), ([[1, np.nan]], 30),
                                ([[1, 2]], 0), ([[-2, -1]], 30)):
            with self.assertRaises(ValueError):
                response_units(height, spacing)
        with self.assertRaises(ValueError):
            rainfall_schedule([1, 2], "unknown")
        with self.assertRaises(ValueError):
            rainfall_schedule([1, 2], "steady", dt_s=0)

    def test_saved_budget_rejects_local_corruption_despite_global_cancellation(self):
        arrays = {"area_m2": np.array([1e10, 100.]),
                  "rain_mm_h": np.array([[3600., 3600.]]),
                  "local_q_m3_s": np.array([[1e7, .1]]),
                  "actual_et_m3": np.zeros((1, 2)),
                  "soil_m3": np.zeros((2, 2)),
                  "fast_m3": np.zeros((2, 2)), "slow_m3": np.zeros((2, 2))}
        self.assertEqual(independent_budget(arrays, 1000)["residual_m3"], 0)
        arrays["local_q_m3_s"][0, 0] -= .001
        arrays["local_q_m3_s"][0, 1] += .001
        with self.assertRaises(ValueError):
            independent_budget(arrays, 1000)

    def test_actual_mountain_runoff_wet_dry_and_late_recession(self):
        from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
        from terrain_pipeline.runoff import simulate_rainfall_runoff as simulate_rainfall_runoff

        source = load_source("normal_mountain")
        owner, area, mean, lower, upper = response_units(source["height_m"], 30)
        time, rain = rainfall_schedule(mean, "dry_storm")
        peaks = []
        for initial_soil in (15., 135.):
            result = simulate_rainfall_runoff(rain, area, dt_s=900, source_id="test-mountain",
                                             parameters=RunoffParameters(initial_soil_mm=initial_soil))
            arrays = {"area_m2": area, "rain_mm_h": rain,
                      "local_q_m3_s": result["local_q_m3_s"],
                      "actual_et_m3": result["et_volume_m3"]}
            for reservoir in ("soil", "fast", "slow"):
                arrays[f"{reservoir}_m3"] = result[f"{reservoir}_mm"] * area[None, :] * .001
            self.assertLess(independent_budget(arrays, 900)["max_hru_step_tolerance_ratio"], 1)
            local = result["local_q_m3_s"].sum(axis=1)
            peaks.append(local.max())
            self.assertGreater(local[168 * 4 - 1], local[-1])
            self.assertGreater(local[-1], 0)
        self.assertGreater(peaks[1], peaks[0])

    def test_steady_rain_is_spatially_uniform(self):
        time, rain = rainfall_schedule(np.linspace(100, 1000, 64), "steady")
        self.assertTrue((rain[time < 24] == 3).all())
        self.assertTrue((rain[time >= 24] == 0).all())


if __name__ == "__main__":
    unittest.main()
