import copy
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.drainage import resolve_dem_flats as resolve_dem_flats
from terrain_pipeline.drainage import candidate_mesh as candidate_mesh
from terrain_pipeline.runoff import simulate_dem_rainfall as simulate_dem_rainfall
from terrain_pipeline.runoff import validate_dem_rainfall as validate_dem_rainfall


DRY = RunoffParameters(infiltration_capacity_mm_h=0., potential_et_mm_h=0.,
                       percolation_mm_h=0., initial_soil_mm=0., fast_tau_s=1., slow_tau_s=1.)


def fixture(height):
    height = np.asarray(height, np.float64)
    candidate = {"arrays": {"height_m": height, "valid_mask": np.isfinite(height), "unknown_mask": ~np.isfinite(height)},
                 "grid": {"spacing_x_m": 90., "spacing_z_m": 90., "crs": "EPSG:32651", "units": "metres"}}
    return candidate, resolve_dem_flats(candidate)


class RealDemRainfallRoutingTests(unittest.TestCase):
    def simulate(self, candidate, flat, rain, **options):
        defaults = {"dt_s": 90., "parameters": DRY}
        defaults.update(options)
        return simulate_dem_rainfall(candidate, flat, np.asarray(rain, np.float64), **defaults)

    def test_zero_rain_dry_zero_balance_and_wet_soil_baseflow(self):
        candidate, flat = fixture([[3, 2, 1]])
        dry = self.simulate(candidate, flat, np.zeros(5))
        self.assertTrue(validate_dem_rainfall(candidate, flat, dry)["verified"])
        self.assertTrue(np.all(dry["channel_storage"] == 0))
        self.assertTrue(all(np.all(value == 0) for value in dry["ledger"].values()))
        wet = self.simulate(candidate, flat, np.zeros(5), parameters=RunoffParameters())
        self.assertGreater(wet["local_volume"].sum(), 0.)
        self.assertTrue(validate_dem_rainfall(candidate, flat, wet)["verified"])
        self.assertLess(abs(wet["ledger"]["whole_system_residual_m3"]).max(), 1e-7)

    def test_pulse_one_edge_per_step_exponential_release(self):
        candidate, flat = fixture([[3, 2, 1]])
        rain = np.zeros((4, 3))
        rain[0, 0] = 40.
        result = self.simulate(candidate, flat, rain)
        local = result["local_volume"][0, 0]
        mesh = candidate_mesh(candidate)
        lengths = np.hypot(np.diff(mesh.node_x_m), np.diff(mesh.node_z_m))
        fractions = -np.expm1(-90. / lengths)
        self.assertAlmostEqual(result["channel_storage"][1, 0], local)
        self.assertEqual(result["channel_storage"][1, 1], 0.)
        self.assertEqual(result["channel_storage"][2, 2], 0.)
        self.assertAlmostEqual(result["channel_storage"][2, 1], local * fractions[0])
        self.assertAlmostEqual(result["channel_storage"][3, 2], local * fractions[0] * fractions[1])
        self.assertTrue(np.all(result["ledger"]["engineering_discharge_m3"] == 0))
        self.assertTrue(validate_dem_rainfall(candidate, flat, result)["verified"])

    def test_diagonal_length_controls_release(self):
        candidate, flat = fixture([[3, 4], [4, 1]])
        receiver = flat["network"].receiver.ravel()
        mesh = candidate_mesh(candidate)
        donor = next(int(cell) for cell in np.flatnonzero(receiver >= 0)
                     if cell // 2 != receiver[cell] // 2 and cell % 2 != receiver[cell] % 2)
        target = int(receiver[donor])
        rain = np.zeros((2, 4))
        rain[0, donor] = 40.
        result = self.simulate(candidate, flat, rain)
        length = np.hypot(mesh.node_x_m[donor] - mesh.node_x_m[target],
                          mesh.node_z_m[donor] - mesh.node_z_m[target])
        fraction = -np.expm1(-90. / length)
        self.assertAlmostEqual(result["channel_storage"][2, target], result["local_volume"][0, donor] * fraction)

    def test_batch_size_uniform_and_spatial_equivalence(self):
        candidate, flat = fixture([[4, 4, 3, 2], [4, 4, 3, 1]])
        rain = np.array([0., 20., 0., 5., 0.])
        expected = self.simulate(candidate, flat, rain, batch_cells=1, parameters=RunoffParameters())
        for size in (3, 100000, 10000000):
            result = self.simulate(candidate, flat, np.broadcast_to(rain[:, None], (5, 8)),
                                   batch_cells=size, parameters=RunoffParameters())
            for key in ("valid_cell_ids", "local_volume", "channel_storage", "final_soil_mm", "final_fast_mm", "final_slow_mm"):
                np.testing.assert_array_equal(result[key], expected[key])
            for key in expected["ledger"]:
                np.testing.assert_allclose(result["ledger"][key], expected["ledger"][key], rtol=1e-10, atol=1e-8)
            self.assertTrue(validate_dem_rainfall(candidate, flat, result)["verified"])
        self.assertEqual(self.simulate(candidate, flat, np.zeros(96))["metadata"]["effective_batch_cells"], 1000000 // 96)

    def test_unknown_component_risk_inherited_even_when_root_not_adjacent(self):
        candidate, flat = fixture([[5, 5, 5, 5, np.nan], [5, 5, 5, 5, np.nan]])
        self.assertFalse(flat["network"].unknown_adjacent_terminal[0, 0])
        self.assertTrue(flat["components"][0]["touches_unknown"])
        result = self.simulate(candidate, flat, np.ones(6) * 20)
        self.assertGreater(result["ledger"]["unknown_retained_m3"][-1], 0.)
        self.assertTrue(np.all(result["ledger"]["internal_retained_m3"] == 0))
        with self.assertRaises(ValueError):
            self.simulate(candidate, flat, np.ones(6), engineering_terminal_ids=(0,))

    def test_explicit_closed_boundary_engineering_discharge_never_verified_natural(self):
        candidate, flat = fixture([[5, 5, 5]])
        rain = np.zeros((4, 3))
        rain[0, 0] = 40.
        retained = self.simulate(candidate, flat, rain)
        result = self.simulate(candidate, flat, rain, engineering_terminal_ids=(0,))
        self.assertEqual(result["ledger"]["engineering_discharge_m3"][0], 0.)
        self.assertGreater(result["ledger"]["engineering_discharge_m3"][1], 0.)
        self.assertLess(result["channel_storage"][-1].sum(), retained["channel_storage"][-1].sum())
        self.assertTrue(np.all(result["ledger"]["verified_external_m3"] == 0))
        self.assertFalse(result["summary"]["natural_outlet_verified"])
        self.assertTrue(validate_dem_rainfall(candidate, flat, result)["verified"])
        internal_candidate, internal_flat = fixture([[9, 9, 9], [9, 0, 9], [9, 9, 9]])
        with self.assertRaises(ValueError):
            self.simulate(internal_candidate, internal_flat, [10], engineering_terminal_ids=(4,))

    def test_malicious_rain_runoff_storage_ledger_source_and_risk_rejected(self):
        candidate, flat = fixture([[3, 2, 1]])
        original = self.simulate(candidate, flat, [20, 0, 0])
        mutations = [lambda value: value["rain_mm_h"].__setitem__(0, 30.),
                     lambda value: value["local_volume"].__setitem__((0, 0), 999.),
                     lambda value: value["channel_storage"].__setitem__((2, 1), 999.),
                     lambda value: value["final_soil_mm"].__setitem__(0, 99.),
                     lambda value: value["ledger"]["engineering_discharge_m3"].__setitem__(1, 99.),
                     lambda value: value["ledger"]["verified_external_m3"].__setitem__(1, 1.),
                     lambda value: value["metadata"].update(candidate_height_sha256="0" * 64),
                     lambda value: value["metadata"]["parameters"].update(initial_soil_mm=100.),
                     lambda value: value["summary"].update(natural_outlet_verified=True)]
        for mutation in mutations:
            result = copy.deepcopy(original)
            mutation(result)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_dem_rainfall(candidate, flat, result)
        result = copy.deepcopy(original)
        result["rain_mm_h"][0] = 30
        result["metadata"]["rain_sha256"] = array_hash(result["rain_mm_h"])
        with self.assertRaises(ValueError):
            validate_dem_rainfall(candidate, flat, result)
        altered = copy.deepcopy(flat)
        altered["components"][0]["touches_unknown"] = True
        with self.assertRaises(ValueError):
            validate_dem_rainfall(candidate, altered, original)

    def test_balanced_fake_transfer_rejected_by_local_propagation_equation(self):
        candidate, flat = fixture([[3, 2, 1]])
        result = self.simulate(candidate, flat, [20, 0, 0])
        result["channel_storage"][1, 0] -= .1
        result["channel_storage"][1, 1] += .1
        with self.assertRaises(ValueError):
            validate_dem_rainfall(candidate, flat, result)

    def test_invalid_bool_nonfinite_shape_parameters_and_engineering_ids(self):
        candidate, flat = fixture([[3, 2, 1]])
        for rain in (np.ones(97), np.zeros(0), np.zeros((3, 2)), np.ones((1, 3), bool),
                     np.array([np.nan]), np.array([np.inf]), np.array([-1.]), np.array([1e6 + 1])):
            with self.subTest(rain=rain), self.assertRaises(ValueError):
                simulate_dem_rainfall(candidate, flat, rain, dt_s=90.)
        for options in ({"dt_s": True}, {"dt_s": 0}, {"speed_m_s": True}, {"speed_m_s": 0},
                        {"speed_m_s": np.inf}, {"batch_cells": True}, {"batch_cells": 0},
                        {"parameters": {}}, {"engineering_terminal_ids": (True,)},
                        {"engineering_terminal_ids": (2, 2)}, {"engineering_terminal_ids": (1,)}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.simulate(candidate, flat, [10], **options)

    def test_entry_and_retained_budget_rejected_before_solver_or_allocation(self):
        candidate = {"arrays": {"height_m": np.zeros((500, 1000)), "valid_mask": np.ones((500, 1000), bool)}}
        with patch('terrain_pipeline.drainage.validate_flat_routing', side_effect=AssertionError("budget first")):
            with self.assertRaises(ValueError):
                simulate_dem_rainfall(candidate, {}, np.zeros(49), dt_s=90.)
            rain = np.broadcast_to(np.zeros((48, 1)), (48, 500000))
            with self.assertRaisesRegex(ValueError, "512MiB"):
                simulate_dem_rainfall(candidate, {}, rain, dt_s=90.)

    def test_validator_does_not_replay_propagation_solver_and_sources_unchanged(self):
        candidate, flat = fixture([[3, 2, 1]])
        before = candidate["arrays"]["height_m"].copy()
        receiver = flat["network"].receiver.copy()
        result = self.simulate(candidate, flat, [10, 0, 0])
        with patch('terrain_pipeline.runoff.simulate_dem_rainfall', side_effect=AssertionError("no propagation replay")):
            self.assertTrue(validate_dem_rainfall(candidate, flat, result)["verified"])
        np.testing.assert_array_equal(before, candidate["arrays"]["height_m"])
        np.testing.assert_array_equal(receiver, flat["network"].receiver)
        self.assertLessEqual(result["summary"]["retained_array_nbytes"], 512 * 1024 * 1024)

    def test_explicit_metric_spacing_required_and_non90_grid_used(self):
        candidate, flat = fixture([[3, 2, 1]])
        candidate.pop("grid")
        with self.assertRaisesRegex(ValueError, "explicit metric"):
            self.simulate(candidate, flat, [10])
        candidate["grid"] = {"spacing_x_m": 30., "spacing_z_m": 60., "crs": "EPSG:32651", "units": "metres"}
        result = self.simulate(candidate, flat, [[40, 0, 0], [0, 0, 0]])
        self.assertAlmostEqual(result["ledger"]["rain_volume_m3"][0], 1.8)
        mesh = candidate_mesh(candidate)
        length = np.hypot(mesh.node_x_m[0] - mesh.node_x_m[1], mesh.node_z_m[0] - mesh.node_z_m[1])
        self.assertAlmostEqual(result["channel_storage"][2, 1],
                               result["local_volume"][0, 0] * -np.expm1(-90. / length))
        self.assertTrue(validate_dem_rainfall(candidate, flat, result)["verified"])
        candidate["grid"]["units"] = "degrees"
        with self.assertRaises(ValueError):
            self.simulate(candidate, flat, [10])

    def test_integer_float32_and_float64_rain_normalized_identity(self):
        candidate, flat = fixture([[3, 2, 1]])
        results = [simulate_dem_rainfall(candidate, flat, np.array([10, 0, 0], dtype=dtype), dt_s=90., parameters=DRY)
                   for dtype in (np.int64, np.float32, np.float64)]
        for result in results:
            self.assertEqual(result["rain_mm_h"].dtype, np.dtype(np.float64))
            self.assertEqual(result["metadata"], results[0]["metadata"])
            self.assertTrue(validate_dem_rainfall(candidate, flat, result)["verified"])


if __name__ == "__main__":
    unittest.main()
