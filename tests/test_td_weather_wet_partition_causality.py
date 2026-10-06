"""Diagnostic regressions documenting original wet-bypass discontinuity."""

import numpy as np

from terrain_pipeline.td_basin_storage_compiled import advance_hour


def forcing_only(initial_depth, step_s, rain_mm_h=2.288880014936935):
    states = np.array([[initial_depth], [30.], [0.], [0.]])
    runoff = np.array([15., 150., .15, 1., 3600., 259200.])
    return advance_hour(states, np.zeros_like(states), np.array([rain_mm_h]),
        np.array([1400.]), np.empty((0, 2), dtype=np.int64), np.empty(0, dtype=np.int64),
        np.empty(0), np.array([-1], dtype=np.int64), 30., step_s, int(3600 / step_s),
        runoff, np.array([.6, 1e-9, .15]))


def test_actual_rain_wet_threshold_has_distinct_persistent_branches():
    dry = forcing_only(.99e-9, 1.25)
    wet = forcing_only(1.01e-9, 1.25)
    assert dry[0][0, 0] == 0
    assert wet[0][0, 0] > .002
    assert dry[2][1, 0] == 0
    assert wet[2][2, 0] == 0
    assert abs(dry[0][1, 0] - wet[0][1, 0]) > 2


def test_wet_partition_branches_persist_under_time_refinement_and_conserve():
    for initial_depth in (.99e-9, 1.01e-9):
        depths = []
        for step in (2.5, 1.25, .625, .3125):
            result = forcing_only(initial_depth, step)
            states, ledger = result[0], result[2]
            before = 900 * (initial_depth + .03)
            after = 900 * (states[0, 0] + states[1:, 0].sum() / 1000)
            residual = after - before - ledger[0, 0] + ledger[3, 0] + ledger[5, 0]
            assert abs(residual) < 1e-9
            assert np.all(states >= 0)
            depths.append(states[0, 0])
        assert max(depths) - min(depths) < 1e-10
