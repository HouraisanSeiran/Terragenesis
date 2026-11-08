import unittest
import numpy as np
from terrain_pipeline.basin_storage import forcing as forcing
from terrain_pipeline.basin_storage import add as add
from terrain_pipeline.basin_storage import reset_transport_compensation as reset_transport_compensation
from terrain_pipeline.basin_storage import reset_hourly_ledger_compensation as reset_hourly_ledger_compensation
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters


class CompensatedForcingTests(unittest.TestCase):
    def test_exact_exhaustion_with_old_compensation(self):
        for old_error in (-1e-16, 1e-16):
            values = np.array([1e-8])
            compensation = np.array([old_error])
            add(values, -values.copy(), compensation)
            self.assertEqual(values[0], 0)
            self.assertEqual(compensation[0], 0)
            add(values, np.array([1e-12]), compensation)
            self.assertEqual(values[0], 1e-12)

    def test_depleted_soil_fast_slow_and_water(self):
        keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "local_release_m3", "surface_et_m3")
        errors = {key: np.array([1e-16]) for key in ("depth", "soil", "fast", "slow") + keys}
        for key in keys:
            errors[key][:] = 0
        ledgers = {key: np.zeros((1, 1)) for key in keys}
        states = [np.array([1e-8]) for index in range(4)]
        runoff = RunoffParameters(initial_soil_mm=0, potential_et_mm_h=1, percolation_mm_h=1, fast_tau_s=1, slow_tau_s=1)
        forcing(*states, np.zeros(1), 1000, runoff, {"wet_threshold_m": 1e-9, "surface_evaporation_mm_h": 1}, 1, ledgers, 0, errors)
        self.assertTrue(all(np.all(values == 0) for values in states))
        self.assertTrue(all(errors[key][0] == 0 for key in ("depth", "soil", "fast", "slow")))

    def test_transport_and_hourly_reset_scope(self):
        errors = {key: np.ones(1) for key in ("depth", "soil", "rain_volume_m3")}
        reset_transport_compensation(errors)
        self.assertEqual(errors["depth"][0], 0)
        self.assertEqual(errors["soil"][0], 1)
        reset_hourly_ledger_compensation(errors, ("rain_volume_m3",))
        self.assertEqual(errors["rain_volume_m3"][0], 0)

    def test_repeated_zero_face_forcing_budget(self):
        keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "local_release_m3", "surface_et_m3")
        for dt in (5., 2.5):
            depth, soil, fast, slow = np.zeros(1), np.array([30.]), np.zeros(1), np.zeros(1)
            errors = {key: np.zeros(1) for key in ("depth", "soil", "fast", "slow") + keys}
            ledgers = {key: np.zeros((24, 1)) for key in keys}
            config = {"wet_threshold_m": 1e-9, "surface_evaporation_mm_h": .15}
            runoff = RunoffParameters()
            for frame in range(24):
                for key in keys:
                    errors[key][:] = 0
                before = 900 * (depth + (soil + fast + slow) / 1000)
                rain = np.array([10. if frame < 6 else 0.])
                for substep in range(round(3600 / dt) * 2):
                    forcing(depth, soil, fast, slow, rain, dt / 2, runoff, config, 900, ledgers, frame, errors)
                after = 900 * (depth + (soil + fast + slow) / 1000)
                residual = ledgers["rain_volume_m3"][frame] - ledgers["soil_et_m3"][frame] - ledgers["surface_et_m3"][frame] - (after-before)
                self.assertLess(abs(residual[0]) * 65536, 1e-6)
                self.assertTrue(all(np.all(values >= 0) for values in (depth, soil, fast, slow)))


if __name__ == "__main__":
    unittest.main()
