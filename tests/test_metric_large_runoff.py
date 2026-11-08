import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.runoff import RUNOFF_ARRAY_KEYS as ARRAY_KEYS
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.common_infra import RainfallForcing, TerrainGrid
from terrain_pipeline.runoff import runoff_from_forcing_large as runoff_from_forcing_large
from terrain_pipeline.runoff import validate_large_rainfall_runoff_result as validate_large_rainfall_runoff_result
from terrain_pipeline.runoff import runoff_from_forcing as runoff_from_forcing


def terrain():
    return TerrainGrid(np.array([[4., 3., 2.], [1., 0., 0.]]),
                       np.array([[True, False, True], [True, True, True]]),
                       x0_m=10., z0_m=20., dx_m=3., dz_m=4.,
                       source_kind="generated_terrain", source_id="small",
                       source_sha256="a" * 64)


def forcing(rain_unknown=0.):
    rain = np.zeros((3, 2, 3), dtype=np.float64)
    rain[0] = [[10., rain_unknown, 20.], [30., 40., 50.]]
    rain[1] = [[0., 0., 5.], [0., 5., 0.]]
    return RainfallForcing(np.array([20., 320., 620., 920.]), rain,
                           source_id="small-pulse", source_sha256="b" * 64)


class LargeRunoffTests(unittest.TestCase):
    def test_chunked_native_result_matches_regular_adapter_exactly(self):
        params = RunoffParameters(initial_soil_mm=0., potential_et_mm_h=0.)
        regular = runoff_from_forcing(terrain(), forcing(), parameters=params,
                                     output_indices=[1, 3])
        chunked = runoff_from_forcing_large(terrain(), forcing(), parameters=params,
                                            output_indices=[1, 3], chunk_size=2)
        for key in ARRAY_KEYS:
            with self.subTest(key=key):
                np.testing.assert_array_equal(chunked["native_result"][key],
                                              regular["native_result"][key])
        self.assertEqual(chunked["native_result"]["metadata"], regular["native_result"]["metadata"])
        for key in ("valid_cell_ids", "state_time_seconds", "output_time_seconds",
                    "output_state_indices"):
            np.testing.assert_array_equal(chunked[key], regular[key])
        for key in regular["output_states_mm"]:
            np.testing.assert_array_equal(chunked["output_states_mm"][key],
                                          regular["output_states_mm"][key])
        for key in regular["ledger"]:
            if key == "totals_m3":
                self.assertEqual(chunked["ledger"][key], regular["ledger"][key])
            else:
                np.testing.assert_array_equal(chunked["ledger"][key], regular["ledger"][key])
        self.assertEqual(chunked["metadata"], regular["metadata"])
        self.assertTrue(validate_large_rainfall_runoff_result(chunked["native_result"])["valid"])
        np.testing.assert_array_equal(chunked["valid_cell_ids"], [0, 2, 3, 4, 5])
        np.testing.assert_array_equal(chunked["native_result"]["area_m2"], np.full(5, 12.))

    def test_unknown_rain_nonuniform_dt_and_budget_fail_before_solver(self):
        with patch('terrain_pipeline.runoff.simulate_rainfall_runoff',
                   side_effect=AssertionError("solver called")):
            with self.assertRaisesRegex(ValueError, "invalid terrain"):
                runoff_from_forcing_large(terrain(), forcing(1.), chunk_size=2)
            nonuniform = RainfallForcing(np.array([0., 300., 601., 900.]), forcing().rain_mm_h,
                                         source_id="bad-dt", source_sha256="b" * 64)
            with self.assertRaisesRegex(ValueError, "uniform"):
                runoff_from_forcing_large(terrain(), nonuniform, chunk_size=2)
            with patch('terrain_pipeline.runoff.MAX_LARGE_CELLS', 4):
                with self.assertRaisesRegex(ValueError, "budget"):
                    runoff_from_forcing_large(terrain(), forcing(), chunk_size=2)
            with self.assertRaises(ValueError):
                runoff_from_forcing_large(terrain(), forcing(), chunk_size=0)

    def test_large_validator_rejects_corrupt_native_component(self):
        native = runoff_from_forcing_large(terrain(), forcing(), chunk_size=2)["native_result"]
        native["outflow_volume_m3"][0, 3] += 1.
        with self.assertRaisesRegex(ValueError, "balance|ledger"):
            validate_large_rainfall_runoff_result(native, chunk_size=2)


if __name__ == "__main__":
    unittest.main()
