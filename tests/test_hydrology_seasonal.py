import copy
from dataclasses import replace
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np

from terrain_pipeline.runoff import LakeGeometry as LakeGeometry
from builtins import ValueError as SeasonalBalanceError
from terrain_pipeline.runoff import SeasonalConfig as SeasonalConfig
from terrain_pipeline.runoff import seasonal_climate as seasonal_climate
from terrain_pipeline.runoff import load_seasonal_water_balance as load_seasonal_water_balance
from terrain_pipeline.runoff import save_seasonal_water_balance as save_seasonal_water_balance
from terrain_pipeline.runoff import simulate_seasonal_water_balance as simulate_seasonal_water_balance
from terrain_pipeline.runoff import validate_seasonal_water_balance as validate_seasonal_water_balance


def fixture(kind="coastal"):
    height = np.array([[3., 2., 3.], [2., 0., 2.], [3., 2., 3.]])
    return {"height_m": height, "owner_domain_id": np.zeros((3, 3), dtype=np.int32),
            "seed": 7, "origin_xz_m": [1000., -1000.], "spacing_m": 10.,
            "domains": [{"domain_id": 0, "kind": kind, "lake_terminal_index": 4,
                         "lake_spill_elevation_m": 10.}]}


class SeasonalTests(unittest.TestCase):
    def test_two_lakes_keep_each_domain_events_in_their_actual_step_and_cold_replay(self):
        from terrain_pipeline.runoff import MONTH_DAYS as MONTH_DAYS
        from terrain_pipeline.runoff import SHORE_EVENT_SCHEMA as SHORE_EVENT_SCHEMA
        plan = {"height_m": np.array([[0., 1., 11., 0., 1., 11.]]),
                "owner_domain_id": np.array([[0, 0, 0, 1, 1, 1]], dtype=np.int32),
                "seed": 7, "origin_xz_m": [0., 0.], "spacing_m": np.sqrt(1000.),
                "identity_sha256": "two-independent-lakes",
                "domains": [{"domain_id": domain, "kind": "inland", "lake_terminal_index": domain * 3,
                             "lake_spill_elevation_m": 10.} for domain in (0, 1)]}
        rain = np.zeros((12, 1, 6))
        pet = np.zeros_like(rain)
        rain[:, 0, [2, 5]] = MONTH_DAYS[:, None] * 6.
        pet[:, 0, [0, 1, 3, 4]] = MONTH_DAYS[:, None] * 4.
        result = simulate_seasonal_water_balance(plan, climate={"precipitation_mm": rain, "potential_et_mm": pet},
                                               initial_lake_volume_m3=np.full(2, 1000.))
        self.assertEqual(result["metadata"]["shore_event_schema"], SHORE_EVENT_SCHEMA)
        self.assertEqual(len(result["shore_events"]), 365)
        for events in result["shore_events"]:
            self.assertEqual([event["domain_id"] for event in events], [0, 1])
            self.assertTrue(all(event["kind"] == "stationary_real_shore" for event in events))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "two-lakes.npz"
            save_seasonal_water_balance(plan, result, path)
            cold = load_seasonal_water_balance(plan, path)
            self.assertEqual(cold["shore_events"], result["shore_events"])

    def test_real_shore_falling_crossing_and_empty_lake_conserve_inventory(self):
        from terrain_pipeline.runoff import _shore_step as _shore_step
        from terrain_pipeline.runoff import WeightedLakeGeometry as WeightedLakeGeometry
        beds = np.array([0., 1.])
        area = np.full(2, 1000.)
        membership = np.ones(2, dtype=bool)
        lake = WeightedLakeGeometry(beds, area, membership, 10.)
        for initial, soil, rain, pet in (
                (1000.1, np.zeros(2), np.zeros(2), np.full(2, 2.)),
                (0., np.full(2, 120.), np.full(2, 5.), np.zeros(2))):
            after, volume, ledger, events = _shore_step(beds, membership, soil, initial,
                rain, pet, area, lake, 1., SeasonalConfig())
            change = np.sum((after - soil) * area) / 1000 + volume - initial
            self.assertAlmostEqual(change, ledger["land_rain_m3"] + ledger["lake_rain_m3"]
                - ledger["land_et_m3"] - ledger["lake_evaporation_m3"], places=9)
            if initial:
                self.assertEqual(events[0]["kind"], "real_bed_crossing")
                self.assertLess(volume, 1000.)
            else:
                self.assertGreater(volume, 0.)
                self.assertFalse(any(event["kind"] == "stationary_real_shore" for event in events))

    def test_real_shore_stationary_mixture_and_crossing_conserve_inventory(self):
        from terrain_pipeline.runoff import _shore_step as _shore_step
        from terrain_pipeline.runoff import WeightedLakeGeometry as WeightedLakeGeometry
        beds = np.array([0., 1.])
        area = np.full(2, 1000.)
        membership = np.ones(2, dtype=bool)
        lake = WeightedLakeGeometry(beds, area, membership, 10.)
        soil = np.full(2, 100.)
        rain = np.zeros(2)
        pet = np.full(2, 2.)
        for initial in (lake.volume(1.), lake.volume(1.) - .1):
            after, volume, ledger, events = _shore_step(beds, membership, soil, initial,
                rain, pet, area, lake, 1., SeasonalConfig())
            self.assertAlmostEqual(volume, lake.volume(1.), places=7)
            self.assertEqual(events[-1]["kind"], "stationary_real_shore")
            self.assertGreater(events[-1]["wet_fraction"], 0)
            self.assertLess(events[-1]["wet_fraction"], 1)
            self.assertEqual(events[-1]["tied_area_m2"], 1000.)
            if initial < lake.volume(1.):
                self.assertEqual(events[0]["kind"], "real_bed_crossing")
            change = np.sum((after - soil) * area) / 1000 + volume - initial
            self.assertAlmostEqual(change, ledger["land_rain_m3"] + ledger["lake_rain_m3"]
                - ledger["land_et_m3"] - ledger["lake_evaporation_m3"], places=9)

    def test_shooting_rejects_small_endpoint_drift_with_nonperiodic_wet_dry_trajectory(self):
        plan = fixture("inland")
        climate = {"precipitation_mm": np.zeros((12, 3, 3)), "potential_et_mm": np.zeros((12, 3, 3))}
        retained_calls = 0
        def year(height, owner, domains, lakes, area, climate, config, soil, volumes, retain=False):
            nonlocal retained_calls
            end = volumes.copy()
            if end[0] == 0:
                end[0] += .00001
            states = [soil.copy() for _ in range(13)]
            if retain:
                retained_calls += 1
                if retained_calls == 1:
                    states[6][1, 1] += .02
            monthly = {key: np.zeros((12, 1)) for key in (
                "land_rain_m3", "lake_rain_m3", "land_et_m3", "lake_evaporation_m3",
                "runoff_to_terminal_m3", "coastal_outflow_m3", "soil_change_m3", "lake_change_m3")}
            return soil.copy(), end, monthly, states, [end.copy() for _ in range(13)], [], []
        with patch('terrain_pipeline.runoff._year', side_effect=year), patch(
                'terrain_pipeline.runoff.validate_seasonal_water_balance'):
            result = simulate_seasonal_water_balance(plan, climate=climate)
        self.assertEqual(result["metadata"]["shooting_trials"][0]["full_trajectory_soil_error_mm"], .02)
        self.assertGreaterEqual(result["metadata"]["shooting_iterations"], 2)
        self.assertEqual(result["metadata"]["successive_year_soil_max_error_mm"], 0.)
        self.assertEqual(result["metadata"]["periodic_solver_algorithm"], "hydrology-periodic-shooting-full-trajectory-v2")

    def test_endpoint_convergence_keeps_iterating_until_annual_trajectory_matches(self):
        plan = fixture()
        climate = {"precipitation_mm": np.zeros((12, 3, 3)), "potential_et_mm": np.zeros((12, 3, 3))}
        calls = []
        oscillate = False
        def year(height, owner, domains, lakes, area, climate, config, soil, volumes, retain=False):
            calls.append(retain)
            monthly = {key: np.zeros((12, 1)) for key in (
                "land_rain_m3", "lake_rain_m3", "land_et_m3", "lake_evaporation_m3",
                "runoff_to_terminal_m3", "coastal_outflow_m3", "soil_change_m3", "lake_change_m3")}
            states = [np.zeros_like(height) for _ in range(13)]
            if (len(calls) == 2 and not oscillate) or (oscillate and len(calls) % 2 == 0):
                states[6][1, 1] = .02
            return soil.copy(), volumes.copy(), monthly, states, [volumes.copy() for _ in range(13)], [], []
        with patch('terrain_pipeline.runoff._year', side_effect=year), patch(
                'terrain_pipeline.runoff.validate_seasonal_water_balance'):
            result = simulate_seasonal_water_balance(plan, climate=climate)
        self.assertEqual(result["metadata"]["successive_year_soil_max_error_mm"], 0.)
        self.assertGreaterEqual(len(calls), 4)
        self.assertLessEqual(result["metadata"]["annual_map_evaluations"], 150)
        calls.clear()
        oscillate = True
        with patch('terrain_pipeline.runoff._year', side_effect=year), patch(
                'terrain_pipeline.runoff.validate_seasonal_water_balance'):
            with self.assertRaises(SeasonalBalanceError) as failed:
                simulate_seasonal_water_balance(plan, replace(SeasonalConfig(), max_years=6), climate)
        diagnostics = failed.exception.diagnostics
        self.assertEqual(diagnostics["annual_map_evaluations"], 6)
        self.assertEqual(diagnostics["successive_year_soil_max_error_mm"], .02)
        self.assertEqual(diagnostics["successive_year_level_max_error_m"], 0.)
        self.assertEqual(len(calls), 6)

    def test_existing_climate_repeats_and_world_coordinates_match(self):
        plan = fixture()
        a = seasonal_climate(plan)
        np.testing.assert_array_equal(a["precipitation_mm"], seasonal_climate(plan)["precipitation_mm"])
        shifted = copy.deepcopy(plan)
        shifted["origin_xz_m"][0] += 10.
        b = seasonal_climate(shifted)
        np.testing.assert_array_equal(a["precipitation_mm"][:, :, 1:], b["precipitation_mm"][:, :, :-1])
        shifted["seed"] += 1
        self.assertFalse(np.array_equal(a["precipitation_mm"], seasonal_climate(shifted)["precipitation_mm"]))

    def test_coastal_complete_state_and_cold_tamper_check(self):
        plan = fixture()
        rain = np.full((12, 3, 3), 30.)
        rain[0] = 250.
        climate = {"precipitation_mm": rain, "potential_et_mm": np.full_like(rain, 55.)}
        dry = simulate_seasonal_water_balance(plan, climate=climate)
        wet = simulate_seasonal_water_balance(plan, climate=climate, initial_soil_mm=np.full((3, 3), 120.))
        np.testing.assert_allclose(dry["soil_mm"], wet["soil_mm"], atol=.02)
        self.assertGreater(dry["monthly"]["coastal_outflow_m3"].sum(), 0)
        validate_seasonal_water_balance(plan, dry)
        tampered = copy.deepcopy(dry)
        tampered["steps"]["lake_rain_m3"][0, 0] += 1
        with self.assertRaises(ValueError):
            validate_seasonal_water_balance(plan, tampered)

    def test_exact_bed_geometry_and_nested_pocket_rejection(self):
        plan = fixture("inland")
        lake = LakeGeometry(plan["height_m"], plan["owner_domain_id"], plan["domains"][0], 100.)
        self.assertEqual(lake.volume(1.), 100.)
        self.assertEqual(lake.volume(2.5), 450.)
        self.assertEqual(lake.level(450.), 2.5)
        plan["height_m"] = np.array([[0., 5., 1.], [9., 9., 9.], [9., 9., 9.]])
        plan["domains"][0]["lake_terminal_index"] = 0
        with self.assertRaises(SeasonalBalanceError):
            LakeGeometry(plan["height_m"], plan["owner_domain_id"], plan["domains"][0], 100.)

    def test_lake_rain_partition_dry_state_and_spill_failure(self):
        plan = fixture("inland")
        climate = {"precipitation_mm": np.zeros((12, 3, 3)), "potential_et_mm": np.ones((12, 3, 3))}
        result = simulate_seasonal_water_balance(plan, climate=climate)
        self.assertEqual(result["lake_volume_m3"].sum(), 0)
        climate["precipitation_mm"][:] = 5000.
        with self.assertRaisesRegex(SeasonalBalanceError, "spill"):
            simulate_seasonal_water_balance(plan, climate=climate)

    def test_nonconvergence_is_bounded(self):
        plan = fixture()
        climate = {"precipitation_mm": np.full((12, 3, 3), 20.), "potential_et_mm": np.full((12, 3, 3), 10.)}
        with self.assertRaisesRegex(SeasonalBalanceError, "max_years"):
            simulate_seasonal_water_balance(plan, replace(SeasonalConfig(), max_years=1), climate)

    def test_wet_lake_partition_and_half_day_step(self):
        plan = fixture("inland")
        rain = np.full((12, 3, 3), 30.)
        rain[0] = 250.
        climate = {"precipitation_mm": rain, "potential_et_mm": np.full_like(rain, 100.)}
        daily = simulate_seasonal_water_balance(plan, climate=climate)
        half = simulate_seasonal_water_balance(plan, replace(SeasonalConfig(), substeps_per_day=2), climate)
        self.assertGreater(daily["monthly"]["lake_rain_m3"].sum(), 0)
        np.testing.assert_allclose(daily["lake_level_m"], half["lake_level_m"], atol=.003)
        for result in (daily, half):
            total_rain = result["monthly"]["land_rain_m3"] + result["monthly"]["lake_rain_m3"]
            np.testing.assert_allclose(total_rain[:, 0], rain.sum(axis=(1, 2)) * .1)
        tampered = copy.deepcopy(daily)
        tampered["lake_volume_m3"][2, 0] = np.nan
        with self.assertRaises(ValueError):
            validate_seasonal_water_balance(plan, tampered)

    def test_immutable_archive_and_cold_read(self):
        plan = fixture()
        plan["identity_sha256"] = "synthetic-parent"
        result = simulate_seasonal_water_balance(plan)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "seasonal.npz"
            save_seasonal_water_balance(plan, result, path)
            cold = load_seasonal_water_balance(plan, path)
            np.testing.assert_array_equal(result["soil_mm"], cold["soil_mm"])
            with self.assertRaises(FileExistsError):
                save_seasonal_water_balance(plan, result, path)
            wrong = dict(plan, identity_sha256="another-parent")
            with self.assertRaisesRegex(ValueError, "identity"):
                load_seasonal_water_balance(wrong, path)
            invented = copy.deepcopy(result)
            invented["metadata"].pop("shore_event_schema")
            invented["shore_events"][0] = [{"kind": "real_bed_crossing", "level_m": 1., "dt_days": 1.}]
            tampered = Path(folder) / "invented-event.npz"
            save_seasonal_water_balance(plan, invented, tampered)
            with self.assertRaisesRegex(ValueError, "events differ from physical replay"):
                load_seasonal_water_balance(plan, tampered)


if __name__ == "__main__":
    unittest.main()
