import numpy as np
import pytest

from terrain_pipeline.procedural_mountain_erosion import (
    MAX_COORDINATE_M, MAX_DELTA_M, directional_detail,
)


def sample(x, z, *, seed=20260903, strength=0.8):
    return directional_detail(x, z, 3200.0, 0.4, -0.2, 0.3,
                              world_seed=seed, strength=strength)


def test_point_chunk_and_order_consistency():
    x = np.linspace(-2500, 2500, 37)
    z = np.linspace(1200, -1700, 37)
    whole = sample(x, z)
    chunks = np.concatenate([sample(x[:13], z[:13]), sample(x[13:], z[13:])])
    points = np.array([sample(a, b) for a, b in zip(x, z)])
    order = np.arange(x.size)[::-1]
    assert np.array_equal(whole, chunks)
    assert np.array_equal(whole, points)
    assert np.array_equal(whole, sample(x[order], z[order])[order])
    assert whole.dtype == np.float64


def test_seed_strength_and_bounded_amplitude():
    x, z = np.meshgrid(np.linspace(-5000, 5000, 30), np.linspace(-3000, 3000, 20))
    a = sample(x, z, strength=1.0)
    assert np.any(a != sample(x, z, seed=5, strength=1.0))
    assert np.all(np.abs(a) <= MAX_DELTA_M)
    assert np.array_equal(sample(x, z, strength=0), np.zeros_like(x))


def test_flat_and_phase_cancellation_are_finite():
    x = np.linspace(-12000, 12000, 1000)
    for slope in (0.0, 1e-300, 1e300):
        result = directional_detail(x, 31, 1, slope, 0, 0,
                                    world_seed=7, strength=1)
        assert np.all(np.isfinite(result))
        assert np.all(np.abs(result) <= MAX_DELTA_M)


@pytest.mark.parametrize("args,kwargs", [
    ((float('nan'), 0, 0, 0, 0, 0), {}),
    ((0, 0, float('inf'), 0, 0, 0), {}),
    ((MAX_COORDINATE_M + 1, 0, 0, 0, 0, 0), {}),
    ((0, 0, 0, 0, 0, 1.01), {}),
    (([1, 2], [1, 2, 3], 0, 0, 0, 0), {}),
    ((0, 0, 0, 0, 0, 0), {'strength': -0.1}),
    ((0, 0, 0, 0, 0, 0), {'strength': float('nan')}),
    ((0, 0, 0, 0, 0, 0), {'world_seed': 1.5}),
])
def test_invalid_inputs_rejected_even_at_zero_strength(args, kwargs):
    params = {'world_seed': 1, 'strength': 0}
    params.update(kwargs)
    with pytest.raises(ValueError):
        directional_detail(*args, **params)

@pytest.mark.parametrize('boundary', [-2400.0, -1200.0, -600.0, -300.0,
                                      300.0, 600.0, 1200.0, 2400.0])
@pytest.mark.parametrize('axis', ['x', 'z'])
def test_cell_boundary_height_and_slope_are_continuous(boundary, axis):
    # Compare limits and one-sided derivatives at every octave boundary.
    epsilon = 0.001
    positions = boundary + np.array([-2, -1, 0, 1, 2]) * epsilon
    if axis == 'x':
        values = sample(positions, np.full(5, 193.7), strength=1)
    else:
        values = sample(np.full(5, 193.7), positions, strength=1)
    left_slope = (values[2] - values[1]) / epsilon
    right_slope = (values[3] - values[2]) / epsilon
    assert abs(values[3] - values[1]) < 0.001
    assert abs(right_slope - left_slope) < 1e-4


def test_sample_limit_and_unsigned_seed():
    from terrain_pipeline.procedural_mountain_erosion import MAX_SAMPLES

    with pytest.raises(ValueError, match='sample count'):
        sample(np.empty(0), 0)
    # Broadcasting would expand these small inputs to an oversized result.
    with pytest.raises(ValueError, match='sample count'):
        sample(np.zeros((MAX_SAMPLES // 2 + 1, 1)), np.zeros((1, 2)))
    for seed in (-1, 2**64, True):
        with pytest.raises(ValueError, match='world_seed'):
            sample(0, 0, seed=seed)
    assert np.isfinite(sample(0, 0, seed=2**64 - 1))
