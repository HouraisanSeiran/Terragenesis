import numpy as np
import pytest

from terrain_pipeline.mountain_forms import RidgeBreakupConfig, _gaussian, _kernel, rasterize_ridge_breakup as rasterize, sample_ridge_breakup_stages as sample_stages


def test_gaussian_constant_and_support():
    c = RidgeBreakupConfig()
    offsets, weights = _kernel(c)
    assert offsets.tolist() == list(range(-4, 5))
    assert np.isclose(weights.sum(), 1)
    result = _gaussian(np.array([-901., 0., 400.]), np.array([2., 100., 300.]), c,
                       lambda x, z: np.full_like(x, 7.0))
    np.testing.assert_allclose(result, 7, atol=1e-12)
    x, z = np.array([-127., 430., 2010.]), np.array([212., -43., 678.])
    linear = _gaussian(x, z, c, lambda a, b: 2 * a - 3 * b + 11)
    np.testing.assert_allclose(linear, 2 * x - 3 * z + 11, atol=1e-10)
    # A kernel node cannot see a feature beyond its finite support.
    value = _gaussian(np.array([0.]), np.array([0.]), c,
                      lambda x, z: ((x == 1500) & (z == 0)).astype(float))
    assert value[0] == 0


def test_gaussian_reuse_matches_direct_convolution():
    c = RidgeBreakupConfig(gaussian_step_m=300.25)
    offsets, weights = _kernel(c)
    def signal(x, z):
        return np.sin(x / 800) + np.cos(z / 1300)
    x = np.r_[np.linspace(-3000, 3000, 100), 1e8]
    z = np.r_[np.linspace(4000, -5000, 100), -1e8]
    actual = _gaussian(x, z, c, signal)
    ix, iz = np.floor(x / c.gaussian_step_m), np.floor(z / c.gaussian_step_m)
    fx, fz = x / c.gaussian_step_m - ix, z / c.gaussian_step_m - iz
    corners = []
    for dx, dz in ((0, 0), (1, 0), (0, 1), (1, 1)):
        value = np.zeros_like(x)
        for j, wz in zip(offsets, weights):
            for i, wx in zip(offsets, weights):
                value += wx * wz * signal((ix + dx + i) * c.gaussian_step_m,
                                           (iz + dz + j) * c.gaussian_step_m)
        corners.append(value)
    a, b, d, e = corners
    expected = (a * (1 - fx) + b * fx) * (1 - fz) + (d * (1 - fx) + e * fx) * fz
    np.testing.assert_array_equal(actual, expected)


def test_switches_and_core():
    base = rasterize((0, 0), (24, 24), 1000, RidgeBreakupConfig(gaussian_sigma_m=0, warp_m=0, gap_strength=0, detail_amplitude_m=0))
    for key in ('gaussian_delta_m', 'breakup_delta_m', 'final_delta_m'):
        np.testing.assert_array_equal(base[key], base['original_delta_m'])
    full = rasterize((0, 0), (24, 24), 1000)
    core = full['protection_mask'] == 1
    assert core.any()
    for key in ('original_height_m', 'gaussian_height_m', 'breakup_height_m', 'height_m'):
        np.testing.assert_array_equal(full[key][core], full['advanced_base_m'][core])
    assert np.max(np.abs(full['breakup_delta_m'] - full['gaussian_delta_m'])) > 1
    assert np.max(np.abs(full['final_delta_m'] - full['breakup_delta_m'])) > 1


def test_chunk_order_and_common_points():
    x = np.array([-1e8, -300.00001, -300., -299.99999, 0, 8000, 1e8])
    z = np.array([1e8, 0, 0, 0, 0, -9000, -1e8])
    original = sample_stages(x, z)
    order = [6, 0, 4, 2, 5, 1, 3]
    shuffled = sample_stages(x[order], z[order])
    chunk = sample_stages(x[:3], z[:3])
    for key in ('gaussian_delta_m', 'breakup_delta_m', 'height_m'):
        np.testing.assert_array_equal(original[key][order], shuffled[key])
        np.testing.assert_array_equal(original[key][:3], chunk[key])
        assert abs(original[key][1] - original[key][2]) < 0.1
    coarse = rasterize((-500, -500), (3, 3), 500)
    fine = rasterize((-500, -500), (5, 5), 250)
    np.testing.assert_array_equal(coarse['height_m'], fine['height_m'][::2, ::2])


def test_parameter_and_extent_validation():
    for kwargs in ({'gap_strength': 2}, {'gaussian_step_m': 0}, {'gaussian_sigma_m': float('nan')}, {'gaussian_sigma_m': 3000, 'gaussian_step_m': 100}):
        with pytest.raises(ValueError):
            RidgeBreakupConfig(**kwargs)
    with pytest.raises(ValueError):
        sample_stages(1e9, 0)


def test_individual_breakup_controls():
    x = np.arange(12) * 1000
    z = np.arange(12)[:, None] * 1000
    common = dict(gaussian_sigma_m=0, detail_amplitude_m=0)
    baseline = sample_stages(x, z, RidgeBreakupConfig(**common, warp_m=0, gap_strength=0))
    warped = sample_stages(x, z, RidgeBreakupConfig(**common, warp_m=700, gap_strength=0))
    gap = sample_stages(x, z, RidgeBreakupConfig(**common, warp_m=0, gap_strength=1))
    assert np.max(np.abs(warped['breakup_delta_m'] - baseline['breakup_delta_m'])) > 10
    assert np.max(np.abs(gap['breakup_delta_m'] - baseline['breakup_delta_m'])) > 10
    assert np.all(np.abs(gap['breakup_delta_m']) <= np.abs(baseline['breakup_delta_m']) + 1e-10)
    np.testing.assert_array_equal(gap['final_delta_m'], gap['breakup_delta_m'])
    negative = gap['warped_delta_m'] < 0
    np.testing.assert_array_equal(gap['warped_delta_m'][negative], gap['breakup_delta_m'][negative])
    assert np.any(gap['ridge_retention'] == 0)
    assert np.any(gap['ridge_retention'] == 1)


def test_seed_and_extent_limits():
    from terrain_pipeline.mountain_forms import VoronoiConfig

    a = sample_stages(np.arange(4) * 1000, 0)
    b = sample_stages(np.arange(4) * 1000, 0,
                      RidgeBreakupConfig(voronoi=VoronoiConfig(world_seed=20260904, family='ridge_network')))
    assert not np.allclose(a['final_delta_m'], b['final_delta_m'])
    limit = a['metadata']['valid_coordinate_limit_m']
    sample_stages(np.array([-limit, limit]), np.array([limit, -limit]))
    with pytest.raises(ValueError):
        sample_stages(limit + 1, 0)
