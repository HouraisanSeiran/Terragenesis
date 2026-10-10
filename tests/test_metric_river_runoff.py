import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.surface_rivers.metric_contracts import BoundaryGrid, RainfallForcing, TerrainGrid
from terrain_pipeline.surface_rivers.metric_runoff import boundary_flux, runoff_from_forcing


def terrain():
    return TerrainGrid(np.array([[2., 1.], [0., np.nan]]),
                       np.array([[True, True], [True, False]]),
                       x0_m=0., z0_m=0., dx_m=3., dz_m=4.,
                       source_kind="generated_terrain", source_id="grid",
                       source_sha256="a" * 64)


def forcing(times=(50., 3650., 7250.)):
    return RainfallForcing(np.asarray(times, dtype=np.float64),
                           np.array([[[20., 0.], [0., 0.]],
                                     [[0., 0.], [0., 0.]]]),
                           source_id="pulse", source_sha256="b" * 64)


def fast_parameters():
    return RunoffParameters(infiltration_capacity_mm_h=0., soil_capacity_mm=0.,
                            potential_et_mm_h=0., percolation_mm_h=0.,
                            initial_soil_mm=0., fast_tau_s=3600.)


class MetricRunoffTests(unittest.TestCase):
    def test_pulse_uses_native_cell_area_and_full_interval_ledger(self):
        result = runoff_from_forcing(terrain(), forcing(), parameters=fast_parameters())
        native = result["native_result"]
        np.testing.assert_array_equal(result["valid_cell_ids"], np.array([0, 1, 2], np.int64))
        np.testing.assert_array_equal(native["area_m2"], np.full(3, 12.))
        np.testing.assert_array_equal(result["state_time_seconds"], [50., 3650., 7250.])
        np.testing.assert_array_equal(result["output_state_indices"], [0, 1, 2])
        np.testing.assert_array_equal(result["output_time_seconds"], [50., 3650., 7250.])
        expected_release = .24 * np.exp(-1.)
        self.assertAlmostEqual(native["local_q_m3_s"][0, 0], expected_release / 3600.)
        self.assertAlmostEqual(native["local_q_m3_s"][1, 0],
                               .24 * (1. - np.exp(-1.)) ** 2 / 3600.)
        self.assertAlmostEqual(result["ledger"]["rain_volume_m3"][0], .24)
        self.assertAlmostEqual(result["ledger"]["outflow_volume_m3"][0], expected_release)
        self.assertAlmostEqual(result["ledger"]["storage_change_m3"][0], .24 - expected_release)
        self.assertAlmostEqual(result["ledger"]["totals_m3"]["rain_volume_m3"], .24)
        np.testing.assert_allclose(result["ledger"]["balance_residual_m3"], 0., atol=1e-12)
        self.assertEqual(result["metadata"]["q_semantics"], "interval_average_local_release_not_river_routed")
        self.assertEqual(result["metadata"]["state_semantics"], "end_of_interval")

    def test_output_sampling_does_not_change_release_or_ledger(self):
        all_states = runoff_from_forcing(terrain(), forcing(), parameters=fast_parameters())
        sampled = runoff_from_forcing(terrain(), forcing(), parameters=fast_parameters(), output_indices=[2])
        np.testing.assert_array_equal(sampled["output_state_indices"], [2])
        np.testing.assert_array_equal(sampled["output_time_seconds"], [7250.])
        np.testing.assert_array_equal(sampled["state_time_seconds"], all_states["state_time_seconds"])
        np.testing.assert_array_equal(sampled["native_result"]["local_q_m3_s"], all_states["native_result"]["local_q_m3_s"])
        self.assertEqual(sampled["ledger"]["totals_m3"], all_states["ledger"]["totals_m3"])

    def test_rejects_nonuniform_steps_masked_rain_and_bad_indices(self):
        with self.assertRaisesRegex(ValueError, "uniform"):
            runoff_from_forcing(terrain(), forcing((0., 3600., 9000.)))
        with self.assertRaisesRegex(ValueError, "uniform"):
            runoff_from_forcing(terrain(), forcing((0., 1000000., 2000000.0000005)))
        wet_unknown = RainfallForcing(forcing().time_seconds,
                                      np.array([[[0., 0.], [0., 1.]], [[0., 0.], [0., 0.]]]),
                                      source_id="bad", source_sha256="b" * 64)
        with self.assertRaisesRegex(ValueError, "invalid terrain"):
            runoff_from_forcing(terrain(), wet_unknown)
        for indices in ([0], [3], [2, 1], np.array([2, 1], dtype=np.uint64),
                        [1, 1], [1.], [True]):
            with self.subTest(indices=indices), self.assertRaises(ValueError):
                runoff_from_forcing(terrain(), forcing(), output_indices=indices)
        with self.assertRaises(ValueError):
            runoff_from_forcing(terrain(), forcing(), parameters={})
        with self.assertRaises(ValueError):
            runoff_from_forcing(terrain(), object())

    def test_ledger_overflow_is_rejected(self):
        native = {key: np.zeros((2, 3)) for key in
                  ("rain_volume_m3", "et_volume_m3", "outflow_volume_m3",
                   "storage_change_m3", "balance_residual_m3")}
        native["rain_volume_m3"][0, :2] = 1e308
        native.update({key: np.zeros((3, 3)) for key in ("soil_mm", "fast_mm", "slow_mm")})
        with patch("terrain_pipeline.surface_rivers.metric_runoff.simulate_rainfall_runoff",
                   return_value=native), self.assertRaisesRegex(ValueError, "finite|overflow"):
            runoff_from_forcing(terrain(), forcing())

    def test_boundary_flux_is_outward_positive_and_rejects_unknown(self):
        kind = np.array([["open_outflow", "closed_wall", "interior"],
                         ["prescribed_stage", "prescribed_stage", "prescribed_discharge"]])
        boundary = BoundaryGrid(kind, np.array([[False, False, False], [False, True, True]]),
                                source_id="edge", source_sha256="c" * 64,
                                stage_m=np.array([[0., 0., 0.], [2., 2., 0.]]),
                                discharge_m3_s=np.array([[0., 0., 0.], [0., 0., -4.]]))
        proposal = np.array([[-3., 5., 7.], [-2., -3., 99.]])
        np.testing.assert_array_equal(boundary_flux(boundary, proposal),
                                      [[0., 0., 0.], [0., -3., -4.]])
        outward = proposal.copy()
        outward[0, 0] = 3.
        self.assertEqual(boundary_flux(boundary, outward)[0, 0], 3.)
        unknown = BoundaryGrid(np.array([["unknown_boundary"]]), np.array([[False]]),
                               source_id="unknown", source_sha256="c" * 64)
        with self.assertRaisesRegex(ValueError, "unknown"):
            boundary_flux(unknown, np.array([[1.]]))
        np.testing.assert_array_equal(boundary_flux(unknown, np.array([[0.]])), [[0.]])
        with self.assertRaises(ValueError):
            boundary_flux(unknown, np.array([[np.nan]]))


if __name__ == "__main__":
    unittest.main()
