# -*- coding: utf-8 -*-
"""Contract tests for the seasonal snow/SWE store (G7 first card).

Every case is a small synthetic set of cells with declared weather. Nothing here reads real
terrain, a TD page, a saved product or a climate model: the point is the SWE ledger, the
declared phase reuse, the single liquid path into the existing soil bucket, and the refusals.
"""
import unittest

import numpy as np

from terrain_pipeline import soil_water as snow
from terrain_pipeline import soil_water as metric_pet_et


DAY = 86400.0


def cell_points(count):
    return [1000.0 + 30.0 * i for i in range(count)], [2000.0] * count


class SnowParameterTests(unittest.TestCase):
    def test_the_declared_threshold_must_be_the_adapter_threshold(self):
        with self.assertRaises(ValueError):
            snow.SnowParameters(freezing_threshold_c=-2.0,
                                phase_parameters=metric_pet_et.PetEtParameters(
                                    freezing_threshold_c=0.0))

    def test_the_parameters_enter_the_identity(self):
        first = snow.SnowParameters().identity()
        second = snow.SnowParameters(degree_day_melt_mm_per_day_c=6.0).identity()
        self.assertNotEqual(first, second)
        self.assertEqual(first["degree_day_melt_mm_per_day_c"], 4.0)
        self.assertIn("sublimation_demand_mm_per_day", first)
        self.assertNotIn("runoff", first["phase_parameters"])


class PhaseAndStoreTests(unittest.TestCase):
    def _two_intervals(self):
        """Cold then warm, one cell: snow falls while cold, then the interval turns warm."""
        edges = np.asarray([0.0, DAY, 2 * DAY])
        temperature = np.asarray([[-5.0], [5.0]])      # declared per interval
        precip = np.asarray([[10.0], [0.0]])           # 10 mm fell while it was cold
        return edges, temperature, precip

    def test_solid_precipitation_builds_swe_and_melt_is_zero(self):
        """No sublimation is declared here, so the store grows by exactly what fell."""
        edges, temperature, precip = self._two_intervals()
        x, z = cell_points(1)
        parameters = snow.SnowParameters(sublimation_demand_mm_per_day=0.0)
        result = snow.advance_snow_ice(
            swe_start_mm=np.zeros(1), temperature_c=temperature, precip_mm=precip,
            time_edges_s=edges, x_m=x, z_m=z, temperature_source="declared_interval",
            parameters=parameters)
        arrays = result["arrays"]
        self.assertAlmostEqual(arrays["swe_edge_mm"][1, 0], 10.0, places=9)
        self.assertAlmostEqual(arrays["solid_precip_mm"][0, 0], 10.0, places=9)
        self.assertAlmostEqual(arrays["liquid_precip_mm"][0, 0], 0.0, places=12)
        self.assertAlmostEqual(arrays["melt_mm"][0, 0], 0.0, places=12)
        self.assertAlmostEqual(arrays["liquid_to_land_mm"][0, 0], 0.0, places=12)

    def test_the_default_sublimation_demand_is_really_deducted(self):
        """The default 0.5 mm/day demand is a real term, not a label: it is accounted in."""
        edges, temperature, precip = self._two_intervals()
        x, z = cell_points(1)
        result = snow.advance_snow_ice(
            swe_start_mm=np.zeros(1), temperature_c=temperature, precip_mm=precip,
            time_edges_s=edges, x_m=x, z_m=z, temperature_source="declared_interval")
        arrays = result["arrays"]
        self.assertAlmostEqual(arrays["sublimation_mm"][0, 0], 0.5, places=9)
        self.assertAlmostEqual(arrays["swe_edge_mm"][1, 0], 9.5, places=9)
        ledger = result["ledger_mm"]
        self.assertLessEqual(abs(ledger["max_abs_residual_mm"]), 1e-9)

    def test_warm_interval_melts_and_the_ledger_closes(self):
        """No sublimation declared: the whole store is available to melt."""
        edges, temperature, precip = self._two_intervals()
        x, z = cell_points(1)
        parameters = snow.SnowParameters(sublimation_demand_mm_per_day=0.0)
        result = snow.advance_snow_ice(
            swe_start_mm=np.zeros(1), temperature_c=temperature, precip_mm=precip,
            time_edges_s=edges, x_m=x, z_m=z, temperature_source="declared_interval",
            parameters=parameters)
        arrays = result["arrays"]
        ledger = result["ledger_mm"]
        # 4 mm/(day*C) at 5 C over one day = 20 mm potential, limited by the 10 mm stored
        self.assertAlmostEqual(arrays["melt_mm"][1, 0], 10.0, places=9)
        self.assertAlmostEqual(arrays["swe_edge_mm"][-1, 0], 0.0, places=9)
        self.assertAlmostEqual(arrays["liquid_to_land_mm"][1, 0], 10.0, places=9)
        self.assertLessEqual(abs(ledger["max_abs_residual_mm"]), 1e-9)

    def test_melt_never_drives_the_store_negative(self):
        edges = np.asarray([0.0, DAY, 2 * DAY, 3 * DAY])
        temperature = np.asarray([[-5.0], [10.0], [10.0]])
        precip = np.asarray([[2.0], [0.0], [0.0]])
        x, z = cell_points(1)
        result = snow.advance_snow_ice(
            swe_start_mm=np.zeros(1), temperature_c=temperature, precip_mm=precip,
            time_edges_s=edges, x_m=x, z_m=z, temperature_source="declared_interval")
        swe = result["arrays"]["swe_edge_mm"][:, 0]
        self.assertTrue(np.all(swe >= 0.0))
        self.assertAlmostEqual(swe[0], 0.0, places=12)
        self.assertAlmostEqual(swe[-1], 0.0, places=9)

    def test_sublimation_removes_swe_without_becoming_melt(self):
        """A declared demand removes snow to the atmosphere; it never becomes land water."""
        edges = np.asarray([0.0, DAY])
        temperature = np.asarray([[-5.0]])
        precip = np.asarray([[2.0]])
        x, z = cell_points(1)
        parameters = snow.SnowParameters(sublimation_demand_mm_per_day=2.0)
        result = snow.advance_snow_ice(
            swe_start_mm=np.zeros(1), temperature_c=temperature, precip_mm=precip,
            time_edges_s=edges, x_m=x, z_m=z, temperature_source="declared_interval",
            parameters=parameters)
        arrays = result["arrays"]
        # 2 mm fell and 2 mm was demanded: the store ends at zero, nothing reached the land
        self.assertAlmostEqual(arrays["sublimation_mm"][0, 0], 2.0, places=9)
        self.assertAlmostEqual(arrays["melt_mm"][0, 0], 0.0, places=12)
        self.assertAlmostEqual(arrays["liquid_to_land_mm"][0, 0], 0.0, places=12)
        self.assertAlmostEqual(arrays["swe_edge_mm"][-1, 0], 0.0, places=9)

    def test_the_declared_order_decides_who_gets_the_scarce_snow(self):
        """A 1 mm store on a warm interval where melt and the declared demand both exceed it.

        The store is declared directly as ``swe_start_mm``: a warm interval cannot build snow
        (its precipitation would be liquid rain), and the cold accumulation case is covered on
        its own above. The default 0.5 mm/day demand stays in place — nothing is switched off to
        force an ordering. 4 mm/(day*C) at 5 C over one day is 20 mm of potential melt against
        0.5 mm of demand for 1 mm of snow, so only the declared order decides which of the two
        takes it.
        """
        edges = np.asarray([0.0, DAY])
        temperature = np.asarray([[5.0]])
        precip = np.asarray([[0.0]])
        x, z = cell_points(1)
        parameters = snow.SnowParameters(degree_day_melt_mm_per_day_c=4.0,
                                         sublimation_demand_mm_per_day=0.5)
        melt_first = snow.advance_snow_ice(
            swe_start_mm=np.asarray([1.0]), temperature_c=temperature, precip_mm=precip,
            time_edges_s=edges, x_m=x, z_m=z, temperature_source="declared_interval",
            order="melt_then_sublimation", parameters=parameters)["arrays"]
        sublimation_first = snow.advance_snow_ice(
            swe_start_mm=np.asarray([1.0]), temperature_c=temperature, precip_mm=precip,
            time_edges_s=edges, x_m=x, z_m=z, temperature_source="declared_interval",
            order="sublimation_then_melt", parameters=parameters)["arrays"]
        # melt first: the whole millimetre goes to the land surface as melt
        self.assertAlmostEqual(melt_first["melt_mm"][0, 0], 1.0, places=9)
        self.assertAlmostEqual(melt_first["sublimation_mm"][0, 0], 0.0, places=9)
        self.assertAlmostEqual(melt_first["liquid_to_land_mm"][0, 0], 1.0, places=9)
        self.assertAlmostEqual(melt_first["swe_edge_mm"][-1, 0], 0.0, places=9)
        # demand first: only 0.5 mm leaves to the atmosphere, the other 0.5 mm melts
        self.assertAlmostEqual(sublimation_first["sublimation_mm"][0, 0], 0.5, places=9)
        self.assertAlmostEqual(sublimation_first["melt_mm"][0, 0], 0.5, places=9)
        self.assertAlmostEqual(sublimation_first["liquid_to_land_mm"][0, 0], 0.5, places=9)
        self.assertAlmostEqual(sublimation_first["swe_edge_mm"][-1, 0], 0.0, places=9)

    def test_liquid_and_solid_are_a_conserved_split_of_the_input(self):
        edges = np.asarray([0.0, DAY, 2 * DAY])
        temperature = np.asarray([[-3.0], [3.0]])
        precip = np.asarray([[4.0], [6.0]])
        x, z = cell_points(1)
        arrays = snow.advance_snow_ice(
            swe_start_mm=np.zeros(1), temperature_c=temperature, precip_mm=precip,
            time_edges_s=edges, x_m=x, z_m=z,
            temperature_source="declared_interval")["arrays"]
        split = arrays["solid_precip_mm"] + arrays["liquid_precip_mm"]
        self.assertTrue(np.allclose(split, precip, rtol=0.0, atol=1e-12))

    def test_a_monthly_mean_temperature_uses_the_repository_calendar(self):
        """A sub-hourly interval so the PET adapter's own dt gate is honoured, not widened."""
        edges = np.asarray([0.0, 1800.0, 3600.0])
        monthly = np.full((12, 1), -8.0)
        precip = np.asarray([[5.0], [5.0]])
        x, z = cell_points(1)
        result = snow.advance_snow_ice(
            swe_start_mm=np.zeros(1), temperature_c=monthly, precip_mm=precip,
            time_edges_s=edges, x_m=x, z_m=z, temperature_source="monthly_mean")
        arrays = result["arrays"]
        # every month is below freezing, so the whole input is solid and nothing melts
        self.assertTrue(np.allclose(arrays["solid_precip_mm"], precip, atol=1e-12))
        self.assertTrue(np.allclose(arrays["melt_mm"], 0.0, atol=1e-12))
        self.assertEqual(result["metadata"]["temperature_source"], "monthly_mean")

    def test_a_mixed_monthly_mean_gives_a_declared_mixture(self):
        """One interval straddling the June/July boundary: the mixture is the real weighting.

        The PET calendar gate is one hour, so the interval has to be short. June and July are
        on opposite sides of the declared threshold, so a 3600 s interval split evenly between
        them must give exactly a half liquid fraction — computed from the repository's own
        ``calendar_month_seconds``, not assumed from an annual profile.
        """
        from terrain_pipeline.soil_water import calendar_month_seconds

        june_end_s = (31 + 28 + 31 + 30 + 31 + 30) * DAY     # start of July on the 365-day table
        edges = np.asarray([june_end_s - 1800.0, june_end_s + 1800.0])
        monthly = np.asarray([-8.0] * 6 + [8.0] * 6).reshape(12, 1)
        month_seconds = calendar_month_seconds(edges)
        # the split really is June/July, and really is half and half
        self.assertAlmostEqual(month_seconds[0, 5], 1800.0, places=6)
        self.assertAlmostEqual(month_seconds[0, 6], 1800.0, places=6)
        expected_fraction = float(
            metric_pet_et.liquid_fraction(monthly, month_seconds).ravel()[0])
        self.assertAlmostEqual(expected_fraction, 0.5, places=9)
        precip = np.asarray([[100.0]])
        x, z = cell_points(1)
        arrays = snow.advance_snow_ice(
            swe_start_mm=np.zeros(1), temperature_c=monthly, precip_mm=precip,
            time_edges_s=edges, x_m=x, z_m=z,
            temperature_source="monthly_mean")["arrays"]
        self.assertAlmostEqual(arrays["liquid_precip_mm"][0, 0], 100.0 * expected_fraction,
                               places=6)
        self.assertAlmostEqual(arrays["solid_precip_mm"][0, 0],
                               100.0 * (1.0 - expected_fraction), places=6)

    def test_a_long_interval_is_refused_on_the_monthly_contract(self):
        """The monthly contract reuses the PET calendar, whose own gate is one hour."""
        edges = np.asarray([0.0, 30.0 * DAY])
        monthly = np.full((12, 1), -8.0)
        x, z = cell_points(1)
        with self.assertRaises(ValueError):
            snow.advance_snow_ice(
                swe_start_mm=np.zeros(1), temperature_c=monthly,
                precip_mm=np.asarray([[5.0]]), time_edges_s=edges, x_m=x, z_m=z,
                temperature_source="monthly_mean")
        # the per-interval contract has no such ceiling, so the same span is allowed
        arrays = snow.advance_snow_ice(
            swe_start_mm=np.zeros(1), temperature_c=np.asarray([[-8.0]]),
            precip_mm=np.asarray([[5.0]]), time_edges_s=edges, x_m=x, z_m=z,
            temperature_source="declared_interval")["arrays"]
        self.assertAlmostEqual(arrays["solid_precip_mm"][0, 0], 5.0, places=9)


class RefusalTests(unittest.TestCase):
    def test_a_negative_initial_store_is_refused(self):
        edges = np.asarray([0.0, DAY])
        x, z = cell_points(1)
        with self.assertRaises(ValueError):
            snow.advance_snow_ice(swe_start_mm=np.asarray([-1.0]),
                                  temperature_c=np.asarray([[-1.0]]),
                                  precip_mm=np.asarray([[0.0]]), time_edges_s=edges,
                                  x_m=x, z_m=z, temperature_source="declared_interval")

    def test_exceeding_the_declared_swe_ceiling_is_refused(self):
        edges = np.asarray([0.0, DAY])
        x, z = cell_points(1)
        parameters = snow.SnowParameters(max_swe_mm=5.0)
        with self.assertRaises(ValueError):
            snow.advance_snow_ice(swe_start_mm=np.zeros(1),
                                  temperature_c=np.asarray([[-5.0]]),
                                  precip_mm=np.asarray([[50.0]]), time_edges_s=edges,
                                  x_m=x, z_m=z, temperature_source="declared_interval",
                                  parameters=parameters)

    def test_a_time_contract_that_does_not_match_is_refused(self):
        edges = np.asarray([0.0, DAY, 2 * DAY])
        x, z = cell_points(1)
        with self.assertRaises(ValueError):
            snow.advance_snow_ice(swe_start_mm=np.zeros(1),
                                  temperature_c=np.asarray([[-1.0]]),
                                  precip_mm=np.asarray([[0.0], [0.0]]),
                                  time_edges_s=edges, x_m=x, z_m=z,
                                  temperature_source="declared_interval")
        with self.assertRaises(ValueError):
            snow.advance_snow_ice(swe_start_mm=np.zeros(1),
                                  temperature_c=np.asarray([[-1.0], [-1.0]]),
                                  precip_mm=np.asarray([[0.0], [0.0]]),
                                  time_edges_s=edges, x_m=x, z_m=z,
                                  temperature_source="monthly_mean")

    def test_one_point_per_cell_is_required(self):
        edges = np.asarray([0.0, DAY])
        x, z = cell_points(2)
        with self.assertRaises(ValueError):
            snow.advance_snow_ice(swe_start_mm=np.zeros(1),
                                  temperature_c=np.asarray([[-1.0]]),
                                  precip_mm=np.asarray([[0.0]]), time_edges_s=edges,
                                  x_m=x, z_m=z, temperature_source="declared_interval")


class BucketTests(unittest.TestCase):
    def test_the_liquid_path_is_consumed_once_by_the_existing_bucket(self):
        edges = np.asarray([0.0, DAY])
        x, z = cell_points(1)
        liquid = np.asarray([[12.0]])                 # liquid precipitation + melt
        states = np.zeros((3, 1))
        result = snow.advance_soil_with_liquid(liquid, edges, states, x_m=x, z_m=z)
        # a long interval is split into fixed sub-steps, never silently shortened
        self.assertGreaterEqual(result["substeps_per_interval"][0], 24)
        self.assertLessEqual(result["max_step_s"], snow.MAX_BUCKET_STEP_S)
        self.assertEqual(result["bucket_module"], metric_pet_et.BUCKET_MODULE)
        total_out = (float(result["released_mm"].sum())
                     + float(result["evaporated_mm"].sum())
                     + float(result["states"].sum()))
        self.assertAlmostEqual(total_out, 12.0, places=6)

    def test_the_bucket_ceiling_is_never_raised(self):
        edges = np.asarray([0.0, DAY])
        x, z = cell_points(1)
        with self.assertRaises(ValueError):
            snow.advance_soil_with_liquid(np.asarray([[1.0]]), edges, np.zeros((3, 1)),
                                          x_m=x, z_m=z, max_step_s=7200.0)

    def test_the_substep_helper_respects_the_ceiling(self):
        parts = snow.bucket_substeps(9000.0)
        self.assertTrue(all(part <= snow.MAX_BUCKET_STEP_S for part in parts))
        self.assertAlmostEqual(sum(parts), 9000.0, places=9)


class DescriptionTests(unittest.TestCase):
    def test_the_module_states_what_it_does_not_claim(self):
        described = snow.snow_ice_describe()
        self.assertEqual(described["schema"], snow.SNOW_ICE_SCHEMA)
        # structural: a declared field, not a sentence a reader has to pattern-match
        self.assertIn("snow_depth", described["not_modelled"])
        self.assertIn("glacier", described["not_modelled"])
        self.assertNotIn("snow_depth_m", described)
        self.assertIn("declared_interval", described["temperature_sources"])
        self.assertIn("sublimation_demand_mm_per_day",
                      described["default_parameters"])
        self.assertEqual(described["monthly_mean_max_interval_s"],
                         snow.MAX_BUCKET_STEP_S)


if __name__ == "__main__":
    unittest.main()
