import dataclasses

import numpy as np
import pytest

from terrain_pipeline import mountain_forms as advanced
from terrain_pipeline.mountain_forms import ProductMountainConfig, sample_product_mountains


def test_formula_and_disabled():
    x = np.array([-23000.0, 0, 1500, 999999000])
    for alpha in (0, 0.65, 1):
        c = ProductMountainConfig(alpha=alpha, advanced_enabled=False)
        result = sample_product_mountains(x, 420, c)
        expected = c.base_m + c.amplitude_m * result['ridge'] ** c.ridge_power * (1 - alpha + alpha * result['volume'])
        np.testing.assert_array_equal(result['macro_height_m'], expected)
        np.testing.assert_array_equal(result['height_m'], expected)
        np.testing.assert_array_equal(result['delta_m'], 0)
        assert np.all((result['ridge'] >= 0) & (result['ridge'] <= 1))
        assert np.all((result['volume'] >= 0) & (result['volume'] <= 1))


def test_filter_driven_by_macro_and_fixed_neighborhood(monkeypatch):
    original = advanced.filter_height
    calls = []
    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(advanced, 'filter_height', capture)
    c = ProductMountainConfig(batch_size=2)
    x = np.array([123., 456., -1000.])
    z = np.array([888., -300., 800.])
    result = sample_product_mountains(x, z, c)
    assert len(calls) == 2
    np.testing.assert_array_equal(calls[0][0][2], result['macro_height_m'][:2])
    np.testing.assert_array_equal(calls[0][0][3], result['slope_x'][:2])
    np.testing.assert_array_equal(calls[0][0][5], result['fade_target'][:2])
    no_filter = dataclasses.replace(c, advanced_enabled=False)
    def macro(dx, dz):
        return sample_product_mountains(x + dx, z + dz, no_filter)['macro_height_m']
    np.testing.assert_array_equal(result['slope_x'], (macro(30, 0) - macro(-30, 0)) / 60)
    target = np.clip((result['macro_height_m'] - (macro(600, 0) + macro(-600, 0) + macro(0, 600) + macro(0, -600)) / 4) / 120, -1, 1)
    np.testing.assert_array_equal(result['fade_target'], target)
    np.testing.assert_array_equal(result['height_m'], result['macro_height_m'] + result['delta_m'])


def test_order_batch_and_common_points():
    x = np.array([-999999000., -24000, -60, 0, 60, 24000, 999999000.])
    z = np.array([-900000000., -6000, 0, 60, 120, 6000, 900000000.])
    a = sample_product_mountains(x, z, ProductMountainConfig(batch_size=3))
    b = sample_product_mountains(x[::-1], z[::-1], ProductMountainConfig(batch_size=7))
    for key in a:
        np.testing.assert_array_equal(a[key], b[key][::-1])
    grid = sample_product_mountains(x[:3, None], z[None, :3])
    for i in range(3):
        point = sample_product_mountains(x[i], z[i])
        for key in a:
            assert a[key][i] == grid[key][i, i] == point[key]


def test_invalid_inputs_and_halo():
    for args in ((float('nan'), 0), (1e9 - 599, 0), (0, -1e9 + 599), ([], [])):
        with pytest.raises(ValueError):
            sample_product_mountains(*args)
    sample_product_mountains(1e9 - 600, -1e9 + 600)
    for kwargs in ({'alpha': 1.1}, {'world_seed': -1}, {'batch_size': 0}, {'advanced_enabled': 1}):
        with pytest.raises(ValueError):
            ProductMountainConfig(**kwargs)


def test_compact_site_field_matches_wider_search_at_edges_and_far_coordinates():
    from diffusion.geographic_noise import _hash, smooth_noise
    from terrain_pipeline.mountain_forms import _fields
    from terrain_pipeline.common_infra import derive_subseed

    config = ProductMountainConfig(warp_m=0)
    seeds = tuple(derive_subseed(config.world_seed, purpose) for purpose in
                  ('product-ridge', 'product-warp', 'product-voronoi-sites'))
    rng = np.random.default_rng(12345)
    # Construct points on and beside cell edges and corners in the stretched
    # domain, then invert its rotation to obtain world coordinates.
    offsets = np.array([-1e-9, 0, 1e-9, 0.5, 1 - 1e-9, 1, 1 + 1e-9])
    gx, gz = np.meshgrid(offsets, offsets)
    gx = np.concatenate((gx.ravel(), rng.uniform(-30, 30, 200), [30000.0, -30000.0]))
    gz = np.concatenate((gz.ravel(), rng.uniform(-30, 30, 200), [-60000.0, 60000.0]))
    u = gx * config.cell_size_m * config.anisotropy
    v = gz * config.cell_size_m
    x = 0.8660254037844386 * u - 0.5 * v
    z = 0.5 * u + 0.8660254037844386 * v
    for warp_m in (0, 1700):
        c = dataclasses.replace(config, warp_m=warp_m)
        actual = _fields(x, z, c, seeds)[1]
        wx = x + c.warp_m * smooth_noise(x, z, 24000, seeds[1], 1)
        wz = z + c.warp_m * smooth_noise(x, z, 24000, seeds[1], 2)
        qx = (0.8660254037844386 * wx + 0.5 * wz) / (c.cell_size_m * c.anisotropy)
        qz = (-0.5 * wx + 0.8660254037844386 * wz) / c.cell_size_m
        ix, iz = np.floor(qx).astype(np.int64), np.floor(qz).astype(np.int64)
        remainder = np.ones(x.shape)
        for dz in range(-2, 3):
            for dx in range(-2, 3):
                cx, cz = ix + dx, iz + dz
                sx = cx + 0.5 + 0.25 * _hash(cx, cz, seeds[2], 1)
                sz = cz + 0.5 + 0.25 * _hash(cx, cz, seeds[2], 2)
                distance = np.hypot(qx - sx, qz - sz)
                t = np.clip((distance - 1) / 0.25, 0, 1)
                weight = np.exp(-2.2 * distance * distance) * (1 - t * t * (3 - 2 * t))
                remainder *= 1 - weight
        np.testing.assert_array_equal(actual, 1 - remainder)



def test_final_height_converges_across_site_switch_and_ridge_crest():
    from diffusion.geographic_noise import _hash, smooth_noise
    from terrain_pipeline.common_infra import derive_subseed

    c = ProductMountainConfig(warp_m=0)
    site_seed = derive_subseed(c.world_seed, 'product-voronoi-sites')
    ridge_seed = derive_subseed(c.world_seed, 'product-ridge')
    def site(ix, iz):
        ix, iz = np.array(ix), np.array(iz)
        return (ix + 0.5 + 0.25 * _hash(ix, iz, site_seed, 1),
                iz + 0.5 + 0.25 * _hash(ix, iz, site_seed, 2))
    a, b = site(0, 0), site(1, 0)
    # The midpoint lies on the bisector of adjacent sites; verify it is a
    # genuine nearest-site switch rather than an obscured bisector.
    gx, gz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    distances = [np.hypot(gx - site(i, j)[0], gz - site(i, j)[1])
                 for j in range(-2, 3) for i in range(-2, 4)]
    assert np.isclose(sorted(distances)[0], sorted(distances)[1])
    assert sorted(distances)[2] > sorted(distances)[1] + 1e-4
    u, v = gx * c.cell_size_m * c.anisotropy, gz * c.cell_size_m
    switch = (0.8660254037844386 * u - 0.5 * v, 0.5 * u + 0.8660254037844386 * v)

    def noise(x):
        z = 7000.0
        u = (0.8660254037844386 * x + 0.5 * z) / 2.5
        v = -0.5 * x + 0.8660254037844386 * z
        return (0.72 * smooth_noise(u, v, c.ridge_spacing_m, ridge_seed, 1)
                + 0.28 * smooth_noise(u, v, c.ridge_spacing_m / 2, ridge_seed, 2))
    points = np.linspace(-30000, 30000, 301)
    vals = noise(points)
    index = np.flatnonzero(vals[:-1] * vals[1:] < 0)[0]
    left, right = points[index:index + 2]
    for _ in range(50):
        mid = (left + right) / 2
        if noise(left) * noise(mid) <= 0:
            right = mid
        else:
            left = mid
    crest = ((left + right) / 2, 7000.0)
    steps = np.array([1.0, 0.1, 0.01, 0.001])
    for point, alpha in ((switch, 0.65), (crest, 0)):
        cfg = dataclasses.replace(c, alpha=alpha)
        result = sample_product_mountains(point[0] + np.r_[-steps, steps], point[1], cfg)
        for field in ('volume', 'ridge', 'slope_x', 'slope_z', 'height_m'):
            differences = np.abs(result[field][:4] - result[field][4:])
            assert differences[-1] < differences[0] * 0.01 + 1e-9, (field, differences)
            assert differences[-1] < (0.01 if field == 'height_m' else 0.001), (field, differences)
