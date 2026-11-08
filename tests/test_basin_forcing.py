"""M4 tests.test_basin_forcing; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from terrain_pipeline.basin_storage import add as _m4_test_td_basin_forcing_compensated_add
from terrain_pipeline.basin_storage import forcing as _m4_test_td_basin_forcing_compensated_forcing
from terrain_pipeline.basin_storage import reset_hourly_ledger_compensation as _m4_test_td_basin_forcing_compensated_reset_hourly_ledger_compensation
from terrain_pipeline.basin_storage import reset_transport_compensation as _m4_test_td_basin_forcing_compensated_reset_transport_compensation
from terrain_pipeline.basin_storage import simulate_forcing as _m4_test_td_basin_forcing_v10_simulate_forcing
from terrain_pipeline.runoff import RunoffParameters as _m4_test_td_basin_forcing_compensated_RunoffParameters
import numpy as _m4_test_td_basin_forcing_compensated_np
import numpy as _m4_test_td_basin_forcing_v10_np
import unittest as _m4_test_td_basin_forcing_compensated_unittest

# --- tests/test_td_basin_forcing_v10.py:6 ---
def basin_forcing_profile_10_test_threshold_perturbation_is_continuous_and_conservative():
    states = _m4_test_td_basin_forcing_v10_np.array([[.99e-9, 1.01e-9], [30., 30.], [0., 0.], [0., 0.]])
    result = _m4_test_td_basin_forcing_v10_simulate_forcing(states, _m4_test_td_basin_forcing_v10_np.array([2.288880014936935] * 2))
    assert _m4_test_td_basin_forcing_v10_np.max(abs(result['states'][:, 0] - result['states'][:, 1])) < 1e-7
    assert _m4_test_td_basin_forcing_v10_np.max(abs(result['balance_residual_mm'])) < 1e-9
    assert _m4_test_td_basin_forcing_v10_np.all(result['states'] >= 0)

# --- tests/test_td_basin_forcing_v10.py:14 ---
def basin_forcing_profile_10_test_capacity_and_evaporation_events_converge_without_wet_classification():
    rain = _m4_test_td_basin_forcing_v10_np.array([.149999, .15, .150001, 14.999999, 15., 15.000001, 30.])
    states = _m4_test_td_basin_forcing_v10_np.zeros((4, len(rain)))
    states[0] = 1.01e-9
    states[1] = 30.
    results = [_m4_test_td_basin_forcing_v10_simulate_forcing(states, rain, substep_s=step) for step in (2.5, 1.25, .625, .3125)]
    for result in results:
        assert _m4_test_td_basin_forcing_v10_np.all(result['states'] >= 0)
        assert _m4_test_td_basin_forcing_v10_np.max(abs(result['balance_residual_mm'])) < 1e-9
    assert _m4_test_td_basin_forcing_v10_np.max(abs(results[-2]['states'][0] - results[-1]['states'][0])) < 1e-5

# --- tests/test_td_basin_forcing_v10.py:26 ---
def basin_forcing_profile_10_test_surface_infiltration_and_inventory_exhaustion_are_explicit():
    states = _m4_test_td_basin_forcing_v10_np.array([[.001, 0.], [30., 150.], [0., 0.], [0., 0.]])
    result = _m4_test_td_basin_forcing_v10_simulate_forcing(states, _m4_test_td_basin_forcing_v10_np.zeros(2))
    assert result['ledger_mm'][2, 0] > .9
    assert result['states'][0, 0] == 0
    assert result['ledger_mm'][2, 1] >= 0
    assert _m4_test_td_basin_forcing_v10_np.all(result['states'] >= 0)

# --- tests/test_td_basin_forcing_v10.py:35 ---
def basin_forcing_profile_10_test_invalid_inputs_rejected_before_mutation():
    states = _m4_test_td_basin_forcing_v10_np.array([[0.], [30.], [0.], [0.]])
    before = states.copy()
    try:
        _m4_test_td_basin_forcing_v10_simulate_forcing(states, _m4_test_td_basin_forcing_v10_np.array([_m4_test_td_basin_forcing_v10_np.nan]))
    except ValueError:
        pass
    else:
        raise AssertionError('nonfinite rain accepted')
    assert _m4_test_td_basin_forcing_v10_np.array_equal(states, before)

# --- tests/test_td_basin_forcing_compensated.py:10 ---
class BasinForcingCompensatedCompensatedForcingTests(_m4_test_td_basin_forcing_compensated_unittest.TestCase):
    def test_exact_exhaustion_with_old_compensation(self):
        for old_error in (-1e-16, 1e-16):
            values = _m4_test_td_basin_forcing_compensated_np.array([1e-8])
            compensation = _m4_test_td_basin_forcing_compensated_np.array([old_error])
            _m4_test_td_basin_forcing_compensated_add(values, -values.copy(), compensation)
            self.assertEqual(values[0], 0)
            self.assertEqual(compensation[0], 0)
            _m4_test_td_basin_forcing_compensated_add(values, _m4_test_td_basin_forcing_compensated_np.array([1e-12]), compensation)
            self.assertEqual(values[0], 1e-12)

    def test_depleted_soil_fast_slow_and_water(self):
        keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "local_release_m3", "surface_et_m3")
        errors = {key: _m4_test_td_basin_forcing_compensated_np.array([1e-16]) for key in ("depth", "soil", "fast", "slow") + keys}
        for key in keys:
            errors[key][:] = 0
        ledgers = {key: _m4_test_td_basin_forcing_compensated_np.zeros((1, 1)) for key in keys}
        states = [_m4_test_td_basin_forcing_compensated_np.array([1e-8]) for index in range(4)]
        runoff = _m4_test_td_basin_forcing_compensated_RunoffParameters(initial_soil_mm=0, potential_et_mm_h=1, percolation_mm_h=1, fast_tau_s=1, slow_tau_s=1)
        _m4_test_td_basin_forcing_compensated_forcing(*states, _m4_test_td_basin_forcing_compensated_np.zeros(1), 1000, runoff, {"wet_threshold_m": 1e-9, "surface_evaporation_mm_h": 1}, 1, ledgers, 0, errors)
        self.assertTrue(all(_m4_test_td_basin_forcing_compensated_np.all(values == 0) for values in states))
        self.assertTrue(all(errors[key][0] == 0 for key in ("depth", "soil", "fast", "slow")))

    def test_transport_and_hourly_reset_scope(self):
        errors = {key: _m4_test_td_basin_forcing_compensated_np.ones(1) for key in ("depth", "soil", "rain_volume_m3")}
        _m4_test_td_basin_forcing_compensated_reset_transport_compensation(errors)
        self.assertEqual(errors["depth"][0], 0)
        self.assertEqual(errors["soil"][0], 1)
        _m4_test_td_basin_forcing_compensated_reset_hourly_ledger_compensation(errors, ("rain_volume_m3",))
        self.assertEqual(errors["rain_volume_m3"][0], 0)

    def test_repeated_zero_face_forcing_budget(self):
        keys = ("rain_volume_m3", "lake_rain_m3", "land_rain_m3", "soil_et_m3", "local_release_m3", "surface_et_m3")
        for dt in (5., 2.5):
            depth, soil, fast, slow = _m4_test_td_basin_forcing_compensated_np.zeros(1), _m4_test_td_basin_forcing_compensated_np.array([30.]), _m4_test_td_basin_forcing_compensated_np.zeros(1), _m4_test_td_basin_forcing_compensated_np.zeros(1)
            errors = {key: _m4_test_td_basin_forcing_compensated_np.zeros(1) for key in ("depth", "soil", "fast", "slow") + keys}
            ledgers = {key: _m4_test_td_basin_forcing_compensated_np.zeros((24, 1)) for key in keys}
            config = {"wet_threshold_m": 1e-9, "surface_evaporation_mm_h": .15}
            runoff = _m4_test_td_basin_forcing_compensated_RunoffParameters()
            for frame in range(24):
                for key in keys:
                    errors[key][:] = 0
                before = 900 * (depth + (soil + fast + slow) / 1000)
                rain = _m4_test_td_basin_forcing_compensated_np.array([10. if frame < 6 else 0.])
                for substep in range(round(3600 / dt) * 2):
                    _m4_test_td_basin_forcing_compensated_forcing(depth, soil, fast, slow, rain, dt / 2, runoff, config, 900, ledgers, frame, errors)
                after = 900 * (depth + (soil + fast + slow) / 1000)
                residual = ledgers["rain_volume_m3"][frame] - ledgers["soil_et_m3"][frame] - ledgers["surface_et_m3"][frame] - (after-before)
                self.assertLess(abs(residual[0]) * 65536, 1e-6)
                self.assertTrue(all(_m4_test_td_basin_forcing_compensated_np.all(values >= 0) for values in (depth, soil, fast, slow)))
