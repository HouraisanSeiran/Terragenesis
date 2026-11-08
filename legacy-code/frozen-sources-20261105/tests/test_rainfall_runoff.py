import copy
from dataclasses import replace
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.rainfall_runoff import (
    RunoffParameters, load_rainfall_runoff_npz, save_rainfall_runoff_npz,
    simulate_rainfall_runoff, validate_rainfall_runoff_result,
)


class RainfallRunoffTests(unittest.TestCase):
    def simulate(self, rain, parameters=None, dt_s=3600.0, area=None):
        rain = np.asarray(rain, dtype=np.float64)
        if area is None:
            area = np.full(rain.shape[1], 1000.0)
        return simulate_rainfall_runoff(rain, area, dt_s=dt_s,
                                       source_id="synthetic-storm-v1", parameters=parameters)

    def isolated(self, **changes):
        return replace(RunoffParameters(), initial_soil_mm=0.0,
                       potential_et_mm_h=0.0, percolation_mm_h=0.0, **changes)

    def test_dry_zero_and_initial_storage_recession(self):
        empty = self.simulate(np.zeros((6, 2)), self.isolated())
        np.testing.assert_array_equal(empty["local_q_m3_s"], 0.0)
        parameters = replace(self.isolated(), initial_fast_mm=12.0, initial_slow_mm=5.0)
        result = self.simulate(np.zeros((6, 1)), parameters)
        times = np.arange(7) * 3600.0
        np.testing.assert_allclose(result["fast_mm"][:, 0], 12 * np.exp(-times / parameters.fast_tau_s))
        np.testing.assert_allclose(result["slow_mm"][:, 0], 5 * np.exp(-times / parameters.slow_tau_s))
        self.assertAlmostEqual(result["outflow_volume_m3"].sum(), 17 - result["fast_mm"][-1, 0] - result["slow_mm"][-1, 0])

    def test_constant_rain_analytic_reservoir_and_volume(self):
        parameters = self.isolated(infiltration_capacity_mm_h=0.0)
        result = self.simulate(np.full((4, 1), 20.0), parameters)
        expected = 20 * (1 - np.exp(-np.arange(5)))
        np.testing.assert_allclose(result["fast_mm"][:, 0], expected)
        self.assertAlmostEqual(result["rain_volume_m3"].sum(), 80.0)
        self.assertAlmostEqual(result["outflow_volume_m3"].sum() + result["fast_mm"][-1, 0], 80.0)
        self.assertLess(result["outflow_volume_m3"][0, 0], 20.0)
        np.testing.assert_allclose(result["balance_residual_m3"], 0.0, atol=1e-12)

    def test_saturated_antecedent_has_stronger_response_without_loss(self):
        rain = np.full((6, 1), 12.0)
        base = self.isolated(infiltration_capacity_mm_h=30.0)
        dry = self.simulate(rain, replace(base, initial_soil_mm=10.0))
        wet = self.simulate(rain, replace(base, initial_soil_mm=142.5))
        self.assertEqual(dry["outflow_volume_m3"].sum(), 0.0)
        self.assertGreater(wet["outflow_volume_m3"].sum(), 30.0)
        self.assertEqual(wet["soil_mm"][-1, 0], 150.0)
        self.assertAlmostEqual(wet["excess_mm"].sum(), 64.5)
        self.assertTrue(validate_rainfall_runoff_result(wet)["valid"])

    def test_actual_et_and_percolation_are_availability_limited(self):
        parameters = RunoffParameters(initial_soil_mm=0.2, potential_et_mm_h=0.15,
                                      percolation_mm_h=1.0)
        result = self.simulate(np.zeros((3, 1)), parameters)
        self.assertAlmostEqual(result["actual_et_mm"].sum(), 0.15)
        self.assertAlmostEqual(result["percolation_mm"].sum(), 0.05)
        self.assertEqual(result["soil_mm"][-1, 0], 0.0)
        self.assertGreater(result["slow_release_mm"][1, 0], 0.0)

    def test_long_coupled_dry_period_recharges_then_recedes(self):
        parameters = RunoffParameters(initial_soil_mm=142.5, initial_slow_mm=0.0)
        result = self.simulate(np.zeros((14 * 24, 1)), parameters)
        discharge = result["local_q_m3_s"][:, 0]
        self.assertGreater(discharge[95], discharge[47])
        depleted_step = int(np.flatnonzero(result["soil_mm"][:, 0] == 0.0)[0])
        self.assertGreater(depleted_step, 96)
        self.assertTrue(np.all(np.diff(discharge[depleted_step:]) < 0.0))
        np.testing.assert_allclose(discharge[depleted_step + 1:] / discharge[depleted_step:-1],
                                   np.exp(-3600.0 / parameters.slow_tau_s))
        self.assertAlmostEqual(result["et_volume_m3"].sum() + result["outflow_volume_m3"].sum()
                               + result["slow_mm"][-1, 0], parameters.initial_soil_mm)

    def test_storm_recession_area_scaling_and_determinism(self):
        rain = np.zeros((10, 2))
        rain[1:3] = 30.0
        parameters = self.isolated(infiltration_capacity_mm_h=0.0)
        result = self.simulate(rain, parameters, area=np.array([1000.0, 3000.0]))
        np.testing.assert_allclose(result["local_q_m3_s"][:, 1], 3 * result["local_q_m3_s"][:, 0])
        self.assertGreater(result["local_q_m3_s"][3, 0], 0.0)
        self.assertTrue(np.all(np.diff(result["local_q_m3_s"][3:, 0]) < 0))
        repeated = self.simulate(rain, parameters, area=np.array([1000.0, 3000.0]))
        for key in result:
            if key != "metadata":
                np.testing.assert_array_equal(result[key], repeated[key])

    def test_exact_reservoir_refinement_and_small_timestep(self):
        parameters = self.isolated(infiltration_capacity_mm_h=0.0)
        coarse = self.simulate(np.full((4, 1), 20.0), parameters)
        fine = self.simulate(np.full((16, 1), 20.0), parameters, dt_s=900.0)
        np.testing.assert_allclose(coarse["fast_mm"], fine["fast_mm"][::4], atol=1e-12)
        np.testing.assert_allclose(coarse["outflow_volume_m3"], fine["outflow_volume_m3"].reshape(4, 4, 1).sum(axis=1), atol=1e-12)
        tiny = self.simulate([[20.0]], replace(parameters, fast_tau_s=1e12), dt_s=1e-6)
        self.assertGreater(tiny["fast_release_mm"][0, 0], 0.0)
        self.assertTrue(np.isfinite(tiny["local_q_m3_s"]).all())

    def test_soil_splitting_refinement_converges(self):
        parameters = RunoffParameters(initial_soil_mm=149.0)
        volumes = []
        for subdivisions in (1, 2, 4, 8, 64):
            result = self.simulate(np.full((4 * subdivisions, 1), 12.0), parameters,
                                   dt_s=3600.0 / subdivisions)
            volumes.append(result["outflow_volume_m3"].sum())
        errors = np.abs(np.array(volumes[:-1]) - volumes[-1])
        self.assertTrue(np.all(np.diff(errors) < 0))

    def test_inputs_and_outputs_do_not_alias(self):
        rain = np.ones((2, 2))
        area = np.array([1000.0, 2000.0])
        before_rain, before_area = rain.copy(), area.copy()
        result = self.simulate(rain, area=area)
        np.testing.assert_array_equal(rain, before_rain)
        np.testing.assert_array_equal(area, before_area)
        result["rain_mm_h"][:] = 0.0
        result["area_m2"][:] = 1.0
        np.testing.assert_array_equal(rain, before_rain)
        np.testing.assert_array_equal(area, before_area)

    def test_invalid_inputs_parameters_and_budget(self):
        for rain in (np.array([[np.nan]]), np.array([[np.inf]]), np.array([[-1.0]]),
                     np.zeros((0, 1)), np.zeros((1, 0)), np.zeros(2), np.array([[1j]])):
            with self.subTest(rain=rain), self.assertRaises(ValueError):
                simulate_rainfall_runoff(rain, np.ones(1), dt_s=1, source_id="test")
        for area in (np.array([0.0]), np.array([-1.0]), np.array([np.inf]), np.ones(2)):
            with self.assertRaises(ValueError):
                self.simulate([[1.0]], area=area)
        for dt_s in (0.0, -1.0, np.nan, np.inf, True, 1e-9):
            with self.assertRaises(ValueError):
                self.simulate([[1.0]], dt_s=dt_s)
        for changes in ({"fast_tau_s": 0}, {"initial_soil_mm": 151},
                        {"potential_et_mm_h": -1}, {"percolation_mm_h": np.inf},
                        {"slow_tau_s": True}):
            with self.assertRaises(ValueError):
                RunoffParameters(**changes)
        for source in ("", " ", None):
            with self.assertRaises(ValueError):
                simulate_rainfall_runoff(np.ones((1, 1)), np.ones(1), dt_s=1, source_id=source)
        huge = np.broadcast_to(np.array(0.0), (1001, 1000))
        with patch("terrain_pipeline.rainfall_runoff.np.zeros", side_effect=AssertionError("allocation before budget")):
            with self.assertRaises(ValueError):
                simulate_rainfall_runoff(huge, np.ones(1000), dt_s=1, source_id="test")

    def test_static_validator_detects_saved_state_and_ledger_tamper(self):
        result = self.simulate([[30.0], [0.0]])
        with patch("terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff", side_effect=AssertionError("solver called")), patch("terrain_pipeline.rainfall_runoff._release", side_effect=AssertionError("release helper called")):
            self.assertTrue(validate_rainfall_runoff_result(result)["valid"])
        for key in ("soil_mm", "outflow_volume_m3", "local_q_m3_s", "balance_residual_m3"):
            damaged = copy.deepcopy(result)
            damaged[key][-1, 0] += 1.0
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_rainfall_runoff_result(damaged)

    def test_archive_roundtrip_no_overwrite_and_hash_tamper(self):
        result = self.simulate([[30.0], [0.0]])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "runoff.npz"
            save_rainfall_runoff_npz(target, result)
            loaded = load_rainfall_runoff_npz(target)
            self.assertEqual(result["metadata"], loaded["metadata"])
            for key in result:
                if key != "metadata":
                    np.testing.assert_array_equal(result[key], loaded[key])
            original = target.read_bytes()
            with self.assertRaises(FileExistsError):
                save_rainfall_runoff_npz(target, result)
            self.assertEqual(original, target.read_bytes())
            with np.load(target, allow_pickle=False) as archive:
                payload = {key: archive[key] for key in archive.files}
            payload["local_q_m3_s"][1, 0] += 1.0
            damaged = Path(directory) / "tampered.npz"
            np.savez(damaged, **payload)
            with self.assertRaisesRegex(ValueError, "hash"):
                load_rainfall_runoff_npz(damaged)
            manifest = json.loads(payload["manifest"].tobytes())
            manifest["metadata"]["source_id"] = "other-terrain"
            payload["manifest"] = np.frombuffer(json.dumps(manifest).encode(), dtype=np.uint8)
            np.savez(damaged, **payload)
            with self.assertRaisesRegex(ValueError, "metadata hash"):
                load_rainfall_runoff_npz(damaged)

    def test_coherent_constitutive_counterfeit_rehashed_archive(self):
        original = self.simulate([[30.0]], RunoffParameters(initial_soil_mm=10.0))
        for flux_key in ("infiltration_mm", "actual_et_mm", "percolation_mm", "fast_release_mm", "slow_release_mm"):
            result = copy.deepcopy(original)
            if flux_key == "infiltration_mm":
                result[flux_key][0, 0] += 1.0
                result["excess_mm"][0, 0] -= 1.0
            else:
                result[flux_key][0, 0] += 0.1
            result["soil_mm"][1] = result["soil_mm"][0] + result["infiltration_mm"][0] - result["actual_et_mm"][0] - result["percolation_mm"][0]
            result["fast_mm"][1] = result["fast_mm"][0] + result["excess_mm"][0] - result["fast_release_mm"][0]
            result["slow_mm"][1] = result["slow_mm"][0] + result["percolation_mm"][0] - result["slow_release_mm"][0]
            result["et_volume_m3"][:] = result["actual_et_mm"]
            result["outflow_volume_m3"][:] = result["fast_release_mm"] + result["slow_release_mm"]
            result["local_q_m3_s"][:] = result["outflow_volume_m3"] / 3600.0
            result["storage_change_m3"][:] = sum(np.diff(result[key], axis=0) for key in ("soil_mm", "fast_mm", "slow_mm"))
            result["balance_residual_m3"][:] = result["rain_volume_m3"] - result["et_volume_m3"] - result["outflow_volume_m3"] - result["storage_change_m3"]
            np.testing.assert_allclose(result["balance_residual_m3"], 0.0, atol=1e-12)
            with self.subTest(flux=flux_key), self.assertRaises(ValueError):
                validate_rainfall_runoff_result(result)
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "forged.npz"
                save_rainfall_runoff_npz(target, original)
                with np.load(target, allow_pickle=False) as archive:
                    payload = {key: archive[key] for key in archive.files}
                manifest = json.loads(payload["manifest"].tobytes())
                for key in result:
                    if key != "metadata":
                        payload[key] = result[key]
                        digest = hashlib.sha256()
                        digest.update(str(result[key].shape).encode("ascii"))
                        digest.update(result[key].dtype.str.encode("ascii"))
                        digest.update(result[key].tobytes())
                        manifest["hashes"][key] = digest.hexdigest()
                payload["manifest"] = np.frombuffer(json.dumps(manifest).encode(), dtype=np.uint8)
                np.savez(target, **payload)
                with self.assertRaisesRegex(ValueError, "balance/ledger mismatch"):
                    load_rainfall_runoff_npz(target)

    def test_metadata_and_strict_json_rejection(self):
        result = self.simulate([[1.0]])
        for key, value in (("q_semantics", "instantaneous"), ("cell_order", "reordered"),
                           ("extra", 1)):
            damaged = copy.deepcopy(result)
            damaged["metadata"][key] = value
            with self.assertRaises(ValueError):
                validate_rainfall_runoff_result(damaged)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "runoff.npz"
            save_rainfall_runoff_npz(target, result)
            with np.load(target, allow_pickle=False) as archive:
                payload = {key: archive[key] for key in archive.files}
            for invalid in ('{"metadata":{},"metadata":{}}', '{"metadata":NaN}', '{"metadata":Infinity}'):
                payload["manifest"] = np.frombuffer(invalid.encode(), dtype=np.uint8)
                np.savez(target, **payload)
                with self.assertRaises(ValueError):
                    load_rainfall_runoff_npz(target)

    def test_archive_budget_and_shape_checked_before_np_load(self):
        result = self.simulate([[1.0]])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "runoff.npz"
            save_rainfall_runoff_npz(target, result)
            with patch("terrain_pipeline.rainfall_runoff.MAX_ENTRIES", 0), patch("terrain_pipeline.rainfall_runoff.np.load", side_effect=AssertionError("loaded before budget")):
                with self.assertRaisesRegex(ValueError, "budget"):
                    load_rainfall_runoff_npz(target)
            with np.load(target, allow_pickle=False) as archive:
                payload = {key: archive[key] for key in archive.files}
            payload["area_m2"] = np.ones(2)
            np.savez(target, **payload)
            with patch("terrain_pipeline.rainfall_runoff.np.load", side_effect=AssertionError("loaded before shapes")):
                with self.assertRaisesRegex(ValueError, "shapes"):
                    load_rainfall_runoff_npz(target)

    def test_no_clobber_publication_race(self):
        result = self.simulate([[1.0]])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "runoff.npz"

            def competitor(temporary, destination):
                Path(destination).write_bytes(b"competitor-won")
                raise FileExistsError(destination)

            with patch("terrain_pipeline.rainfall_runoff.os.link", side_effect=competitor):
                with self.assertRaises(FileExistsError):
                    save_rainfall_runoff_npz(target, result)
            self.assertEqual(target.read_bytes(), b"competitor-won")
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_archive_rejects_pickle_and_failed_publish_cleans_up(self):
        result = self.simulate([[1.0]])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "runoff.npz"
            with patch("terrain_pipeline.rainfall_runoff.os.link", side_effect=OSError("unsupported")):
                with self.assertRaises(OSError):
                    save_rainfall_runoff_npz(target, result)
            self.assertEqual(list(Path(directory).iterdir()), [])
            save_rainfall_runoff_npz(target, result)
            with np.load(target, allow_pickle=False) as archive:
                payload = {key: archive[key] for key in archive.files}
            payload["soil_mm"] = np.array([[object()]], dtype=object)
            np.savez(target, **payload)
            with self.assertRaises(ValueError):
                load_rainfall_runoff_npz(target)


if __name__ == "__main__":
    unittest.main()
