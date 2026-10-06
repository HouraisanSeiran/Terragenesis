import numpy as np

from terrain_pipeline.td_basin_forcing_v10 import simulate_forcing


def test_threshold_perturbation_is_continuous_and_conservative():
    states = np.array([[.99e-9, 1.01e-9], [30., 30.], [0., 0.], [0., 0.]])
    result = simulate_forcing(states, np.array([2.288880014936935] * 2))
    assert np.max(abs(result['states'][:, 0] - result['states'][:, 1])) < 1e-7
    assert np.max(abs(result['balance_residual_mm'])) < 1e-9
    assert np.all(result['states'] >= 0)


def test_capacity_and_evaporation_events_converge_without_wet_classification():
    rain = np.array([.149999, .15, .150001, 14.999999, 15., 15.000001, 30.])
    states = np.zeros((4, len(rain)))
    states[0] = 1.01e-9
    states[1] = 30.
    results = [simulate_forcing(states, rain, substep_s=step) for step in (2.5, 1.25, .625, .3125)]
    for result in results:
        assert np.all(result['states'] >= 0)
        assert np.max(abs(result['balance_residual_mm'])) < 1e-9
    assert np.max(abs(results[-2]['states'][0] - results[-1]['states'][0])) < 1e-5


def test_surface_infiltration_and_inventory_exhaustion_are_explicit():
    states = np.array([[.001, 0.], [30., 150.], [0., 0.], [0., 0.]])
    result = simulate_forcing(states, np.zeros(2))
    assert result['ledger_mm'][2, 0] > .9
    assert result['states'][0, 0] == 0
    assert result['ledger_mm'][2, 1] >= 0
    assert np.all(result['states'] >= 0)


def test_invalid_inputs_rejected_before_mutation():
    states = np.array([[0.], [30.], [0.], [0.]])
    before = states.copy()
    try:
        simulate_forcing(states, np.array([np.nan]))
    except ValueError:
        pass
    else:
        raise AssertionError('nonfinite rain accepted')
    assert np.array_equal(states, before)
