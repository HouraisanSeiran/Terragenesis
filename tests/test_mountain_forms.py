"""Consolidated tests.test_mountain_forms implementations; numeric expressions preserved."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import math as _i19_math
import hashlib as _i19_hashlib
import numpy as _i19_np
import pytest as _i19_pytest
from terrain_pipeline.mountain_forms import AdvancedFilterConfig as _i19_AdvancedFilterConfig
from terrain_pipeline.mountain_forms import filter_height as _i19_filter_height
from terrain_pipeline.mountain_forms import MAX_SAMPLES as _i19_MAX_SAMPLES
import dataclasses as _i20_dataclasses
import numpy as _i20_np
import pytest as _i20_pytest
from terrain_pipeline import mountain_forms as _i20_advanced
from terrain_pipeline.mountain_forms import ProductMountainConfig as _i20_ProductMountainConfig
from terrain_pipeline.mountain_forms import sample_product_mountains as _i20_sample_product_mountains
from dataclasses import replace as _i21_replace
import numpy as _i21_np
import pytest as _i21_pytest
from terrain_pipeline.mountain_forms import HALO_M as _i21_HALO_M
from terrain_pipeline.mountain_forms import MAX_COORDINATE_M as _i21_MAX_COORDINATE_M
from terrain_pipeline.mountain_forms import LocalVolumeConfig as _i21_LocalVolumeConfig
from terrain_pipeline.mountain_forms import sample_local_volume_mountains as _i21_sample_local_volume_mountains
from terrain_pipeline.mountain_forms import ProductMountainConfig as _i21_ProductMountainConfig
from terrain_pipeline.mountain_forms import sample_product_mountains as _i21_sample_product_mountains
import json as _i22_json
import subprocess as _i22_subprocess
import sys as _i22_sys
import numpy as _i22_np
import pytest as _i22_pytest
from terrain_pipeline.mountain_forms import MountainConfig as _i22_MountainConfig
from terrain_pipeline.mountain_forms import rasterize_procedural as _i22_rasterize
from terrain_pipeline.mountain_forms import sample_procedural_height as _i22_sample_height
from terrain_pipeline.mountain_forms import sample_procedural_stages as _i22_sample_stages
from terrain_pipeline.common_infra import WORLD_SEED as _i22_WORLD_SEED
from terrain_pipeline.common_infra import seed_mountains_v1 as _i22_seed_mountains_v1
from terrain_pipeline.common_infra import derive_subseed as _i22_derive_subseed
import numpy as _i23_np
import pytest as _i23_pytest
import json as _i23_json
from diffusion.geographic_noise import _hash as _i23__hash
from terrain_pipeline.mountain_forms import VoronoiConfig as _i23_VoronoiConfig
from terrain_pipeline.mountain_forms import _sample_batch as _i23__sample_batch
from terrain_pipeline.mountain_forms import _structure as _i23__structure
from terrain_pipeline.mountain_forms import rasterize_voronoi as _i23_rasterize
from terrain_pipeline.mountain_forms import sample_voronoi_stages as _i23_sample_stages
from terrain_pipeline.common_infra import seed_mountains_v1 as _i23_seed_mountains_v1
from terrain_pipeline.common_infra import derive_subseed as _i23_derive_subseed
import numpy as _i24_np
import pytest as _i24_pytest
from terrain_pipeline.mountain_forms import RidgeBreakupConfig as _i24_RidgeBreakupConfig
from terrain_pipeline.mountain_forms import _gaussian as _i24__gaussian
from terrain_pipeline.mountain_forms import _kernel as _i24__kernel
from terrain_pipeline.mountain_forms import rasterize_ridge_breakup as _i24_rasterize
from terrain_pipeline.mountain_forms import sample_ridge_breakup_stages as _i24_sample_stages
import numpy as _i25_np
import pytest as _i25_pytest
from terrain_pipeline.procedural_mountain_erosion import MAX_COORDINATE_M as _i25_MAX_COORDINATE_M
from terrain_pipeline.procedural_mountain_erosion import MAX_DELTA_M as _i25_MAX_DELTA_M
from terrain_pipeline.procedural_mountain_erosion import directional_detail as _i25_directional_detail
import numpy as _i26_np
from terrain_pipeline import mountain_forms as _i26_processes
from terrain_pipeline.mountain_forms import MountainConfig as _i26_MountainConfig
from terrain_pipeline.mountain_forms import rasterize_procedural as _i26_rasterize
from dataclasses import replace as _i27_replace
import json as _i27_json
from pathlib import Path as _i27_Path
import tempfile as _i27_tempfile
import unittest as _i27_unittest
from unittest.mock import patch as _i27_patch
import numpy as _i27_np
from terrain_pipeline.tectonic import CrustState as _i27_CrustState
from terrain_pipeline.tectonic import TectonicConfig as _i27_TectonicConfig
from terrain_pipeline.tectonic import evolve as _i27_evolve
from terrain_pipeline.tectonic import freeze as _i27_freeze
from terrain_pipeline.tectonic import load_product as _i27_load_base
from terrain_pipeline.mountain_forms import WORLD_SEED as _i27_WORLD_SEED
from terrain_pipeline.mountain_forms import WorldMountainConfig as _i27_WorldMountainConfig
from terrain_pipeline.mountain_forms import _ridge_height as _i27__ridge_height
from terrain_pipeline.mountain_forms import load_belt_product as _i27_load_product
from terrain_pipeline.mountain_forms import prepare_world_mountain_belts as _i27_prepare_world_mountain_belts
from terrain_pipeline.mountain_forms import save_belt_product as _i27_save_product

CATEGORY = 'B'

# Source: tests.test_advanced_terrain_filter
def run(x, z, seed=20260903, config=None, target=0.2):
    return _i19_filter_height(x, z, 1000, 0.4, -0.2, target, world_seed=seed, config=config)

# Source: tests.test_advanced_terrain_filter
def scalar_one_octave(x, z, sx, sz, target, seed, c):
    seed = int.from_bytes(_i19_hashlib.sha256(f'advanced-terrain-filter-v1:{seed}:phacelle'.encode()).digest()[:4], 'little') % 1000000
    x, z = (x / c.wavelength_m, z / c.wavelength_m)
    sx, sz = (sx * c.wavelength_m / c.amplitude_m, sz * c.wavelength_m / c.amplitude_m)
    length = max(_i19_math.hypot(sx, sz), 1e-10)
    gx = sx * (1 - c.assumed_slope[1]) + sx / length * c.assumed_slope[0] * c.assumed_slope[1]
    gz = sz * (1 - c.assumed_slope[1]) + sz / length * c.assumed_slope[0] * c.assumed_slope[1]
    norm = _i19_math.hypot(gx, gz)
    dx, dz = (gx / norm, gz / norm) if norm > 1e-10 else (0, 0)
    side_x, side_z = (-dz * c.cell_scale * _i19_math.tau, dx * c.cell_scale * _i19_math.tau)
    kx, kz = (1 / _i19_math.pi, _i19_math.exp(-1))
    co = si = total = 0.0
    ix, iz = (_i19_math.floor(x), _i19_math.floor(z))
    for i in (-1, 0, 1, 2):
        for j in (-1, 0, 1, 2):
            a = (ix + i + seed * 0.06711056) * kx + kz
            b = (iz + j + seed * 0.00583715) * kz + kx
            q = a * b * (a + b)
            t = q - _i19_math.floor(q)
            a, b = (16 * kx * t, 16 * kz * t)
            hx, hz = (-1 + 2 * (a - _i19_math.floor(a)), -1 + 2 * (b - _i19_math.floor(b)))
            rx, rz = (x - ix - i - hx * 0.5, z - iz - j - hz * 0.5)
            weight = max(0, _i19_math.exp(-2 * (rx * rx + rz * rz)) - 0.01111)
            phase = rx * side_x + rz * side_z + _i19_math.pi * 0.5
            co += _i19_math.cos(phase) * weight
            si += _i19_math.sin(phase) * weight
            total += weight
    co, si = (co / total, si / total)
    magnitude = max(1 - c.normalization, _i19_math.hypot(co, si))
    co, si = (co / magnitude, si / magnitude)
    r, o = (c.rounding, c.onset)
    rounding = (r[1] + (r[0] - r[1]) * max(0, min(1, target + 0.5))) * r[2]
    t, s = (length * o[0], rounding * o[0])
    smooth = t - 0.5 * s if t >= s else 0.5 * t * t / s
    mask = 1 - (1 - max(0, min(1, smooth))) ** 2
    layer = target * (1 - mask) + co * c.gully_weight * mask
    dx_delta = si * -side_x * c.gully_weight * mask
    dz_delta = si * -side_z * c.gully_weight * mask
    rm = 1 - (1 - max(0, min(1, length * o[2]))) ** 2
    rt = target * (1 - rm) + co * rm
    rm *= 1 - (1 - max(0, min(1, abs(si) * o[3]))) ** 2
    return (layer * c.amplitude_m, (sx + dx_delta) * c.amplitude_m / c.wavelength_m, (sz + dz_delta) * c.amplitude_m / c.wavelength_m, rt * (1 - rm))

# Source: tests.test_advanced_terrain_filter
@_i19_pytest.mark.parametrize('x,z,sx,sz,target', [(123, 456, 0.4, -0.2, 0.3), (-333, 900, 0.02, 0.04, -0.8), (25, -740, 0, 0, -1)])
def test_one_octave_scalar_reference(x, z, sx, sz, target):
    c = _i19_AdvancedFilterConfig(octaves=1, hash_mode='upstream')
    out = _i19_filter_height(x, z, 500, sx, sz, target, world_seed=42, config=c)
    expected = scalar_one_octave(x, z, sx, sz, target, 42, c)
    assert _i19_np.allclose([out['delta_m'], out['artistic_slope_x'], out['artistic_slope_z'], out['ridge_map']], expected, rtol=1e-12, atol=1e-12)

# Source: tests.test_advanced_terrain_filter
def test_point_chunk_order_seed_and_zero():
    x = _i19_np.linspace(-4000, 4000, 35)
    z = _i19_np.linspace(2000, -2500, 35)
    all_values = run(x, z)
    for key in all_values:
        assert _i19_np.array_equal(all_values[key], _i19_np.concatenate([run(x[:12], z[:12])[key], run(x[12:], z[12:])[key]]))
        assert _i19_np.array_equal(all_values[key], _i19_np.array([run(a, b)[key] for a, b in zip(x, z)]))
        assert _i19_np.array_equal(all_values[key], run(x[::-1], z[::-1])[key][::-1])
    assert _i19_np.any(all_values['height_m'] != run(x, z, seed=1)['height_m'])
    zero = run(x, z, config=_i19_AdvancedFilterConfig(amplitude_m=0))
    assert _i19_np.array_equal(zero['height_m'], _i19_np.full(x.shape, 1000.0))
    assert _i19_np.array_equal(zero['delta_m'], _i19_np.zeros_like(x))

# Source: tests.test_advanced_terrain_filter
def test_flat_structural_target_sign():
    c = _i19_AdvancedFilterConfig(octaves=1)
    for target in (-1, 1):
        out = _i19_filter_height(15, 99, 0, 0, 0, target, world_seed=4, config=c)
        assert out['delta_m'] == _i19_pytest.approx(target * c.amplitude_m)

# Source: tests.test_advanced_terrain_filter
@_i19_pytest.mark.parametrize('boundary', [-3600.0, -1800.0, -900.0, -450.0, 450.0, 900.0, 1800.0, 3600.0])
@_i19_pytest.mark.parametrize('axis', [0, 1])
def test_boundaries_are_continuous(boundary, axis):
    pos = boundary + _i19_np.array([-1.0, 0.0, 1.0]) * 0.0001
    a = run(pos, 111) if axis == 0 else run(111, pos)
    assert abs(a['height_m'][2] - a['height_m'][0]) < 0.01
    assert abs((a['height_m'][2] - 2 * a['height_m'][1] + a['height_m'][0]) / 0.0001) < 0.01

# Source: tests.test_advanced_terrain_filter
def test_validation():
    for x, z, seed in [(_i19_np.empty(0), 0, 1), (_i19_np.zeros((_i19_MAX_SAMPLES // 2 + 1, 1)), _i19_np.zeros((1, 2)), 1), (1000000000.0 + 1, 0, 1), (0, 0, -1), (0, 0, 2 ** 64)]:
        with _i19_pytest.raises(ValueError):
            run(x, z, seed=seed)
    with _i19_pytest.raises(ValueError):
        run(0, 0, target=1.01)
    with _i19_pytest.raises(ValueError):
        run(0, 0, config=_i19_AdvancedFilterConfig(lacunarity=0))

# Source: tests.test_advanced_terrain_filter
@_i19_pytest.mark.parametrize('origin', [2200000, -2200000, 900000000, -900000000])
def test_stable_hash_varies_at_far_lattice_cells(origin):
    from terrain_pipeline.mountain_forms import _stable_hash2
    x = _i19_np.arange(origin, origin + 100, dtype=_i19_np.int64)
    a, b = _stable_hash2(x, x + 18, 13)
    c, d = _stable_hash2(x, x + 18, 14)
    assert _i19_np.ptp(a) > 1.5 and _i19_np.ptp(b) > 1.5
    assert _i19_np.unique(a).size == 100 and _i19_np.unique(b).size == 100
    assert _i19_np.any(a != c) and _i19_np.any(b != d)

# Source: tests.test_advanced_terrain_filter
def test_tiny_amplitude_and_smooth_start_are_safe():
    from terrain_pipeline.mountain_forms import _smooth_start
    with _i19_pytest.raises(ValueError, match='at least'):
        run(0, 0, config=_i19_AdvancedFilterConfig(amplitude_m=1e-300))
    with _i19_np.errstate(over='raise', invalid='raise', divide='raise'):
        assert _i19_np.array_equal(_smooth_start(_i19_np.array([1e+300, 0.5]), _i19_np.array([0.0, 1.0])), _i19_np.array([1e+300, 0.125]))
        result = run(0, 0, config=_i19_AdvancedFilterConfig(amplitude_m=0.001))
        assert all((_i19_np.isfinite(v) for v in result.values()))
    with _i19_pytest.raises(ValueError, match='hash_mode'):
        run(0, 0, config=_i19_AdvancedFilterConfig(hash_mode='unknown'))

# Source: tests.test_product_mountains
def test_formula_and_disabled():
    x = _i20_np.array([-23000.0, 0, 1500, 999999000])
    for alpha in (0, 0.65, 1):
        c = _i20_ProductMountainConfig(alpha=alpha, advanced_enabled=False)
        result = _i20_sample_product_mountains(x, 420, c)
        expected = c.base_m + c.amplitude_m * result['ridge'] ** c.ridge_power * (1 - alpha + alpha * result['volume'])
        _i20_np.testing.assert_array_equal(result['macro_height_m'], expected)
        _i20_np.testing.assert_array_equal(result['height_m'], expected)
        _i20_np.testing.assert_array_equal(result['delta_m'], 0)
        assert _i20_np.all((result['ridge'] >= 0) & (result['ridge'] <= 1))
        assert _i20_np.all((result['volume'] >= 0) & (result['volume'] <= 1))

# Source: tests.test_product_mountains
def test_filter_driven_by_macro_and_fixed_neighborhood(monkeypatch):
    original = _i20_advanced.filter_height
    calls = []

    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(_i20_advanced, 'filter_height', capture)
    c = _i20_ProductMountainConfig(batch_size=2)
    x = _i20_np.array([123.0, 456.0, -1000.0])
    z = _i20_np.array([888.0, -300.0, 800.0])
    result = _i20_sample_product_mountains(x, z, c)
    assert len(calls) == 2
    _i20_np.testing.assert_array_equal(calls[0][0][2], result['macro_height_m'][:2])
    _i20_np.testing.assert_array_equal(calls[0][0][3], result['slope_x'][:2])
    _i20_np.testing.assert_array_equal(calls[0][0][5], result['fade_target'][:2])
    no_filter = _i20_dataclasses.replace(c, advanced_enabled=False)

    def macro(dx, dz):
        return _i20_sample_product_mountains(x + dx, z + dz, no_filter)['macro_height_m']
    _i20_np.testing.assert_array_equal(result['slope_x'], (macro(30, 0) - macro(-30, 0)) / 60)
    target = _i20_np.clip((result['macro_height_m'] - (macro(600, 0) + macro(-600, 0) + macro(0, 600) + macro(0, -600)) / 4) / 120, -1, 1)
    _i20_np.testing.assert_array_equal(result['fade_target'], target)
    _i20_np.testing.assert_array_equal(result['height_m'], result['macro_height_m'] + result['delta_m'])

# Source: tests.test_product_mountains
def test_order_batch_and_common_points():
    x = _i20_np.array([-999999000.0, -24000, -60, 0, 60, 24000, 999999000.0])
    z = _i20_np.array([-900000000.0, -6000, 0, 60, 120, 6000, 900000000.0])
    a = _i20_sample_product_mountains(x, z, _i20_ProductMountainConfig(batch_size=3))
    b = _i20_sample_product_mountains(x[::-1], z[::-1], _i20_ProductMountainConfig(batch_size=7))
    for key in a:
        _i20_np.testing.assert_array_equal(a[key], b[key][::-1])
    grid = _i20_sample_product_mountains(x[:3, None], z[None, :3])
    for i in range(3):
        point = _i20_sample_product_mountains(x[i], z[i])
        for key in a:
            assert a[key][i] == grid[key][i, i] == point[key]

# Source: tests.test_product_mountains
def test_invalid_inputs_and_halo():
    for args in ((float('nan'), 0), (1000000000.0 - 599, 0), (0, -1000000000.0 + 599), ([], [])):
        with _i20_pytest.raises(ValueError):
            _i20_sample_product_mountains(*args)
    _i20_sample_product_mountains(1000000000.0 - 600, -1000000000.0 + 600)
    for kwargs in ({'alpha': 1.1}, {'world_seed': -1}, {'batch_size': 0}, {'advanced_enabled': 1}):
        with _i20_pytest.raises(ValueError):
            _i20_ProductMountainConfig(**kwargs)

# Source: tests.test_product_mountains
def test_compact_site_field_matches_wider_search_at_edges_and_far_coordinates():
    from diffusion.geographic_noise import _hash
    from diffusion.geographic_noise import smooth_noise
    from terrain_pipeline.mountain_forms import _fields
    from terrain_pipeline.common_infra import derive_subseed
    config = _i20_ProductMountainConfig(warp_m=0)
    seeds = tuple((derive_subseed(config.world_seed, purpose) for purpose in ('product-ridge', 'product-warp', 'product-voronoi-sites')))
    rng = _i20_np.random.default_rng(12345)
    offsets = _i20_np.array([-1e-09, 0, 1e-09, 0.5, 1 - 1e-09, 1, 1 + 1e-09])
    gx, gz = _i20_np.meshgrid(offsets, offsets)
    gx = _i20_np.concatenate((gx.ravel(), rng.uniform(-30, 30, 200), [30000.0, -30000.0]))
    gz = _i20_np.concatenate((gz.ravel(), rng.uniform(-30, 30, 200), [-60000.0, 60000.0]))
    u = gx * config.cell_size_m * config.anisotropy
    v = gz * config.cell_size_m
    x = 0.8660254037844386 * u - 0.5 * v
    z = 0.5 * u + 0.8660254037844386 * v
    for warp_m in (0, 1700):
        c = _i20_dataclasses.replace(config, warp_m=warp_m)
        actual = _fields(x, z, c, seeds)[1]
        wx = x + c.warp_m * smooth_noise(x, z, 24000, seeds[1], 1)
        wz = z + c.warp_m * smooth_noise(x, z, 24000, seeds[1], 2)
        qx = (0.8660254037844386 * wx + 0.5 * wz) / (c.cell_size_m * c.anisotropy)
        qz = (-0.5 * wx + 0.8660254037844386 * wz) / c.cell_size_m
        ix, iz = (_i20_np.floor(qx).astype(_i20_np.int64), _i20_np.floor(qz).astype(_i20_np.int64))
        remainder = _i20_np.ones(x.shape)
        for dz in range(-2, 3):
            for dx in range(-2, 3):
                cx, cz = (ix + dx, iz + dz)
                sx = cx + 0.5 + 0.25 * _hash(cx, cz, seeds[2], 1)
                sz = cz + 0.5 + 0.25 * _hash(cx, cz, seeds[2], 2)
                distance = _i20_np.hypot(qx - sx, qz - sz)
                t = _i20_np.clip((distance - 1) / 0.25, 0, 1)
                weight = _i20_np.exp(-2.2 * distance * distance) * (1 - t * t * (3 - 2 * t))
                remainder *= 1 - weight
        _i20_np.testing.assert_array_equal(actual, 1 - remainder)

# Source: tests.test_product_mountains
def test_final_height_converges_across_site_switch_and_ridge_crest():
    from diffusion.geographic_noise import _hash
    from diffusion.geographic_noise import smooth_noise
    from terrain_pipeline.common_infra import derive_subseed
    c = _i20_ProductMountainConfig(warp_m=0)
    site_seed = derive_subseed(c.world_seed, 'product-voronoi-sites')
    ridge_seed = derive_subseed(c.world_seed, 'product-ridge')

    def site(ix, iz):
        ix, iz = (_i20_np.array(ix), _i20_np.array(iz))
        return (ix + 0.5 + 0.25 * _hash(ix, iz, site_seed, 1), iz + 0.5 + 0.25 * _hash(ix, iz, site_seed, 2))
    a, b = (site(0, 0), site(1, 0))
    gx, gz = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    distances = [_i20_np.hypot(gx - site(i, j)[0], gz - site(i, j)[1]) for j in range(-2, 3) for i in range(-2, 4)]
    assert _i20_np.isclose(sorted(distances)[0], sorted(distances)[1])
    assert sorted(distances)[2] > sorted(distances)[1] + 0.0001
    u, v = (gx * c.cell_size_m * c.anisotropy, gz * c.cell_size_m)
    switch = (0.8660254037844386 * u - 0.5 * v, 0.5 * u + 0.8660254037844386 * v)

    def noise(x):
        z = 7000.0
        u = (0.8660254037844386 * x + 0.5 * z) / 2.5
        v = -0.5 * x + 0.8660254037844386 * z
        return 0.72 * smooth_noise(u, v, c.ridge_spacing_m, ridge_seed, 1) + 0.28 * smooth_noise(u, v, c.ridge_spacing_m / 2, ridge_seed, 2)
    points = _i20_np.linspace(-30000, 30000, 301)
    vals = noise(points)
    index = _i20_np.flatnonzero(vals[:-1] * vals[1:] < 0)[0]
    left, right = points[index:index + 2]
    for _ in range(50):
        mid = (left + right) / 2
        if noise(left) * noise(mid) <= 0:
            right = mid
        else:
            left = mid
    crest = ((left + right) / 2, 7000.0)
    steps = _i20_np.array([1.0, 0.1, 0.01, 0.001])
    for point, alpha in ((switch, 0.65), (crest, 0)):
        cfg = _i20_dataclasses.replace(c, alpha=alpha)
        result = _i20_sample_product_mountains(point[0] + _i20_np.r_[-steps, steps], point[1], cfg)
        for field in ('volume', 'ridge', 'slope_x', 'slope_z', 'height_m'):
            differences = _i20_np.abs(result[field][:4] - result[field][4:])
            assert differences[-1] < differences[0] * 0.01 + 1e-09, (field, differences)
            assert differences[-1] < (0.01 if field == 'height_m' else 0.001), (field, differences)

# Source: tests.test_local_volume_mountains
def test_stages_and_negative_only_gain():
    x, z = _i21_np.meshgrid(_i21_np.linspace(0, 24000, 19), _i21_np.linspace(0, 24000, 19))
    config = _i21_LocalVolumeConfig()
    result = _i21_sample_local_volume_mountains(x, z, config)
    control = _i21_sample_local_volume_mountains(x, z, _i21_replace(config, depth_gain=1))
    raw = result['raw_advanced_delta_m']
    _i21_np.testing.assert_array_equal(result['raw_advanced_delta_m'], control['raw_advanced_delta_m'])
    _i21_np.testing.assert_allclose(result['final_delta_m'], result['slope_fade'] * _i21_np.where(raw < 0, raw * 2.4, raw))
    _i21_np.testing.assert_array_equal(result['final_delta_m'][raw >= 0], control['final_delta_m'][raw >= 0])
    assert _i21_np.any(raw < 0) and _i21_np.any(raw > 0)
    assert _i21_np.any(result['p'] == 0) and _i21_np.any(result['p'] > 0)
    _i21_np.testing.assert_array_equal(result['macro_height_m'][result['p'] == 0], result['h0_m'][result['p'] == 0])
    assert _i21_np.all((result['slope_fade'] >= 0) & (result['slope_fade'] <= 1))
    slope = _i21_np.hypot(result['slope_x'], result['slope_z'])
    assert _i21_np.all(result['slope_fade'][slope <= config.slope_fade_low] == 0)

# Source: tests.test_local_volume_mountains
def test_disabled_matches_product_macro_and_deterministic_sampling():
    x = _i21_np.array([-987654321.0, -24000, 0, 1234, 24000])
    z = _i21_np.array([123456789.0, -500, 0, 6789, 12000])
    config = _i21_LocalVolumeConfig(k=0, advanced_enabled=False, batch_size=2)
    whole = _i21_sample_local_volume_mountains(x, z, config)
    product = _i21_sample_product_mountains(x, z, _i21_ProductMountainConfig(advanced_enabled=False))
    _i21_np.testing.assert_array_equal(whole['height_m'], product['macro_height_m'])
    _i21_np.testing.assert_array_equal(whole['final_delta_m'], _i21_np.zeros(x.size))
    for i in range(x.size):
        part = _i21_sample_local_volume_mountains(x[i], z[i], _i21_replace(config, batch_size=1))
        for key in whole:
            _i21_np.testing.assert_array_equal(whole[key][i], part[key])

# Source: tests.test_local_volume_mountains
def test_shared_points_and_order():
    coords = _i21_np.arange(-3, 4) * 600.0
    fine = _i21_sample_local_volume_mountains(coords, 900, _i21_LocalVolumeConfig(batch_size=3))
    coarse = _i21_sample_local_volume_mountains(coords[::2][::-1], 900)
    for key in fine:
        _i21_np.testing.assert_array_equal(fine[key][::2][::-1], coarse[key])

# Source: tests.test_local_volume_mountains
@_i21_pytest.mark.parametrize('kwargs', [{'k': -1}, {'depth_gain': 0}, {'cell_size_m': 0}, {'cell_threshold_low': 0.8, 'cell_threshold_high': 0.8}, {'slope_fade_low': float('nan')}, {'batch_size': True}, {'world_seed': -1}, {'advanced_enabled': 1}])
def test_invalid_config(kwargs):
    with _i21_pytest.raises(ValueError):
        _i21_LocalVolumeConfig(**kwargs)

# Source: tests.test_local_volume_mountains
def test_invalid_coordinates_and_halo():
    for x in ([], [float('nan')], [_i21_MAX_COORDINATE_M - _i21_HALO_M + 1]):
        with _i21_pytest.raises(ValueError):
            _i21_sample_local_volume_mountains(x, 0)
    _i21_sample_local_volume_mountains(_i21_MAX_COORDINATE_M - _i21_HALO_M, 0)

# Source: tests.test_procedural_mountains
def test_seed_and_point_order_are_stable():
    assert _i22_WORLD_SEED == 20260903
    assert _i22_derive_subseed(_i22_WORLD_SEED, 'sites') != _i22_derive_subseed(_i22_WORLD_SEED, 'erosion')
    config = _i22_MountainConfig(detail_strength=0)
    x = _i22_np.linspace(-50000, 50000, 101)
    z = _i22_np.sin(x / 10000) * 20000
    expected = _i22_sample_height(x, z, config)
    order = _i22_np.random.default_rng(42).permutation(x.size)
    actual = _i22_np.concatenate([_i22_sample_height(x[part], z[part], config) for part in _i22_np.array_split(order, 7)])
    assert _i22_np.array_equal(actual, expected[order])
    assert not _i22_np.array_equal(expected, _i22_sample_height(x, z, _i22_MountainConfig(world_seed=20260904, detail_strength=0)))

# Source: tests.test_procedural_mountains
def test_nested_spacing_and_metadata():
    config = _i22_MountainConfig(family='granite_dome', detail_strength=0)
    fine = _i22_rasterize((-1200, -1800), (17, 17), 30, config)
    for spacing, stride in [(60, 2), (120, 4)]:
        coarse = _i22_rasterize((-1200, -1800), (16 // stride + 1,) * 2, spacing, config)
        assert _i22_np.array_equal(fine['height_m'][::stride, ::stride], coarse['height_m'])
    assert fine['metadata']['world_seed'] == _i22_WORLD_SEED
    _i22_json.dumps(fine['metadata'], allow_nan=False)

# Source: tests.test_procedural_mountains
def test_families_have_distinct_base_shapes_and_site_edges_are_continuous():
    coords = _i22_np.linspace(-16000, 16000, 129)
    xx, zz = _i22_np.meshgrid(coords, coords)
    fields = [_i22_sample_height(xx, zz, _i22_MountainConfig(family=f, detail_strength=0)) for f in ('granite_dome', 'layered_massif', 'glacial_horn')]
    for field in fields:
        assert _i22_np.ptp(field) > 500
    for i in range(3):
        for j in range(i):
            assert _i22_np.sqrt(_i22_np.mean((fields[i] - fields[j]) ** 2)) > 100
    x = _i22_np.array([24000.0 - 0.001, 24000.0 + 0.001])
    assert abs(_i22_np.diff(_i22_sample_height(x, [10000, 10000], _i22_MountainConfig(detail_strength=0)))[0]) < 0.1

# Source: tests.test_procedural_mountains
def test_stages_share_macro_field_and_reconstruct_result():
    x, z = _i22_np.meshgrid(_i22_np.linspace(-30000, 30000, 49), _i22_np.linspace(-30000, 30000, 49))
    stages = [_i22_sample_stages(x, z, _i22_MountainConfig(family=f, detail_strength=0)) for f in ('granite_dome', 'layered_massif', 'glacial_horn')]
    assert all((_i22_np.array_equal(stages[0]['base_noise_m'], item['base_noise_m']) for item in stages))
    for item in stages:
        assert _i22_np.array_equal(item['height_m'], item['advanced_base_m'] + item['regional_noise_delta_m'])
    for i in range(3):
        for j in range(i):
            assert _i22_np.sqrt(_i22_np.mean((stages[i]['regional_noise_delta_m'] - stages[j]['regional_noise_delta_m']) ** 2)) > 50

# Source: tests.test_procedural_mountains
def test_advanced_is_in_base_and_pointwise():
    x = _i22_np.linspace(-12000, 12000, 21)
    z = _i22_np.linspace(5000, -5000, 21)
    full = _i22_sample_stages(x, z)
    chunks = [_i22_sample_stages(x[:9], z[:9]), _i22_sample_stages(x[9:], z[9:])]
    for key in full:
        assert _i22_np.array_equal(full[key], _i22_np.concatenate([part[key] for part in chunks]))
    assert _i22_np.any(full['advanced_base_m'] != full['base_noise_m'])
    disabled = _i22_sample_stages(x, z, _i22_MountainConfig(detail_strength=0))
    assert _i22_np.array_equal(disabled['base_noise_m'], disabled['advanced_base_m'])
    fine = _i22_rasterize((-300, -300), (9, 9), 30)
    coarse = _i22_rasterize((-300, -300), (5, 5), 60)
    for key in full:
        assert _i22_np.array_equal(fine[key][::2, ::2], coarse[key])

# Source: tests.test_procedural_mountains
@_i22_pytest.mark.parametrize('x,z', [([float('nan')], [0]), ([100000000000.0], [0]), ([], []), ([0, 1], [0, 1, 2])])
def test_invalid_coordinates(x, z):
    with _i22_pytest.raises(ValueError):
        _i22_sample_height(x, z, _i22_MountainConfig(detail_strength=0))

# Source: tests.test_procedural_mountains
@_i22_pytest.mark.parametrize('kwargs', [{'world_seed': -1}, {'world_seed': True}, {'family': 'missing'}, {'detail_strength': float('nan')}, {'detail_strength': 1.1}, {'detail_strength': 1e-07}])
def test_procedural_mountains_test_invalid_config(kwargs):
    with _i22_pytest.raises(ValueError):
        _i22_MountainConfig(**kwargs)

# Source: tests.test_procedural_mountains
@_i22_pytest.mark.parametrize('shape,spacing', [((0, 1), 30), ((2.5, 2), 30), ((1025, 1024), 30), ((2, 2), float('inf')), ((2, 2), 0)])
def test_invalid_raster(shape, spacing):
    with _i22_pytest.raises(ValueError):
        _i22_rasterize((0, 0), shape, spacing, _i22_MountainConfig(detail_strength=0))

# Source: tests.test_procedural_mountains
def test_module_import_does_not_load_model_dependencies():
    code = "import sys; import terrain_pipeline.mountain_forms; assert 'torch' not in sys.modules; assert 'diffusion.geography_physical' not in sys.modules"
    _i22_subprocess.run([_i22_sys.executable, '-c', code], check=True)

# Source: tests.test_voronoi_mountains
@_i23_pytest.fixture(scope='module')
def sampled():
    return _i23_rasterize((0, 0), (48, 48), 24000 / 47)

# Source: tests.test_voronoi_mountains
def test_protection_and_actual_stages(sampled):
    mask = sampled['protection_mask']
    core = mask == 1
    assert core.any() and _i23_np.any(mask == 0) and _i23_np.any((mask > 0) & (mask < 1))
    _i23_np.testing.assert_array_equal(sampled['height_m'][core], sampled['advanced_base_m'][core])
    _i23_np.testing.assert_allclose(sampled['unprotected_height_m'], sampled['advanced_base_m'] + sampled['structure_delta_m'])
    assert _i23_np.max(_i23_np.abs(sampled['height_m'][mask == 0] - sampled['advanced_base_m'][mask == 0])) > 10

# Source: tests.test_voronoi_mountains
def test_chunk_order_and_common_points():
    x = _i23_np.array([-100000000.0, -6000.00001, -6000, -5999.99999, 0, 9000, 100000000.0])
    z = _i23_np.array([100000000.0, 0, 0, 0, 0, -9000, -100000000.0])
    full = _i23_sample_stages(x, z)
    order = _i23_np.array([6, 0, 4, 2, 5, 1, 3])
    shuffled = _i23_sample_stages(x[order], z[order])
    for key in ('advanced_base_m', 'structure_delta_m', 'protection_mask', 'height_m'):
        _i23_np.testing.assert_array_equal(full[key][order], shuffled[key])
        _i23_np.testing.assert_array_equal(full[key][:3], _i23_sample_stages(x[:3], z[:3])[key])
        assert abs(full[key][1] - full[key][2]) < 0.1
    coarse = _i23_rasterize((-1000, -1000), (3, 3), 1000)
    fine = _i23_rasterize((-1000, -1000), (5, 5), 500)
    _i23_np.testing.assert_array_equal(coarse['height_m'], fine['height_m'][::2, ::2])

# Source: tests.test_voronoi_mountains
def test_families_and_seed():
    x = _i23_np.arange(8) * 1500
    z = _i23_np.arange(8)[:, None] * 1500
    fields = [_i23_sample_stages(x, z, _i23_VoronoiConfig(family=f))['structure_delta_m'] for f in ('mixed', 'cellular_massif', 'ridge_network')]
    assert not _i23_np.allclose(fields[0], fields[1])
    assert not _i23_np.allclose(fields[1], fields[2])
    changed = _i23_sample_stages(x, z, _i23_VoronoiConfig(world_seed=20260904))['height_m']
    assert not _i23_np.allclose(changed, _i23_sample_stages(x, z)['height_m'])

# Source: tests.test_voronoi_mountains
@_i23_pytest.mark.parametrize('kwargs', [{'family': 'invalid'}, {'world_seed': -1}, {'cell_size_m': 0}, {'warp_m': float('nan')}, {'anisotropy': 4}, {'protection_threshold_m': 0}, {'detail_strength': True}])
def test_voronoi_mountains_test_invalid_config(kwargs):
    with _i23_pytest.raises(ValueError):
        _i23_VoronoiConfig(**kwargs)

# Source: tests.test_voronoi_mountains
def test_voronoi_mountains_test_invalid_coordinates():
    with _i23_pytest.raises(ValueError):
        _i23_sample_stages([float('nan')], [0])
    with _i23_pytest.raises(ValueError):
        _i23_rasterize((0, 0), (2, 2), 0)
    with _i23_pytest.raises(ValueError):
        _i23_sample_stages([0, 1000000000.0 - 599], [0, 0])

# Source: tests.test_voronoi_mountains
def test_batching_matches_unbatched():
    x = _i23_np.linspace(-24000, 24000, 16400)
    z = _i23_np.sin(x / 1000) * 10000
    batched = _i23_sample_stages(x, z)
    unbatched = _i23__sample_batch(x, z)
    for key in ('advanced_base_m', 'structure_delta_m', 'unprotected_height_m', 'protection_mask', 'height_m'):
        _i23_np.testing.assert_array_equal(batched[key], unbatched[key])

# Source: tests.test_voronoi_mountains
@_i23_pytest.mark.parametrize('world_seed', [20260903, 20260904])
@_i23_pytest.mark.parametrize('family', ['cellular_massif', 'ridge_network'])
def test_transformed_lattice_boundary_against_larger_search(world_seed, family):
    config = _i23_VoronoiConfig(world_seed=world_seed, family=family, warp_m=0, anisotropy=3)
    seed = _i23_derive_subseed(world_seed, 'voronoi-sites')
    warp_seed = _i23_derive_subseed(world_seed, 'voronoi-warp')
    angle = 2 * _i23_np.pi * (seed % 1000003 / 1000003)
    gx = _i23_np.array([-2 - 1e-08, -2, -2 + 1e-08, 0.2, 0.8, 1.0])
    gz = _i23_np.array([0.3, 0.3, 0.3, -1 - 1e-08, -1 + 1e-08, 1.0])
    a = gx * config.cell_size_m * config.anisotropy
    b = gz * config.cell_size_m
    x = _i23_np.cos(angle) * a - _i23_np.sin(angle) * b
    z = _i23_np.sin(angle) * a + _i23_np.cos(angle) * b
    distances, attrs = ([], [])
    ix, iz = (_i23_np.floor(gx).astype(int), _i23_np.floor(gz).astype(int))
    for dz in range(-3, 4):
        for dx in range(-3, 4):
            cx, cz = (ix + dx, iz + dz)
            sx = cx + 0.5 + 0.25 * _i23__hash(cx, cz, seed, 1)
            sz = cz + 0.5 + 0.25 * _i23__hash(cx, cz, seed, 2)
            distances.append(_i23_np.hypot(gx - sx, gz - sz))
            attrs.append(_i23__hash(cx, cz, seed, 3))
    distances, attrs = (_i23_np.array(distances), _i23_np.array(attrs))
    order = _i23_np.argsort(distances, axis=0)
    first = _i23_np.take_along_axis(distances, order[:1], axis=0)[0]
    second = _i23_np.take_along_axis(distances, order[1:2], axis=0)[0]
    attr = _i23_np.take_along_axis(attrs, order[:1], axis=0)[0]
    t = _i23_np.clip((second - first) / 0.7, 0, 1)
    interior = t * t * (3 - 2 * t)
    if family == 'cellular_massif':
        expected = 1.3 * _i23_np.exp(-2.2 * first * first) * (0.8 + 0.2 * attr * interior) - 0.55
    else:
        expected = 1.35 * _i23_np.exp(-5 * (second - first)) - 0.42
    actual = _i23__structure(x, z, config, seed, warp_seed)
    _i23_np.testing.assert_allclose(actual, config.amplitude_m * expected, atol=1e-09)
    assert abs(actual[0] - actual[2]) < 0.001

# Source: tests.test_voronoi_mountains
def test_metadata_json_with_numpy_shape():
    result = _i23_rasterize((0, 0), (_i23_np.int64(2), _i23_np.int64(2)), _i23_np.float64(30))
    _i23_json.dumps(result['metadata'])
    assert result['metadata']['subseeds']['advanced-phacelle'] == 10860721302913963045

# Source: tests.test_voronoi_mountains
def test_transition_width_preserves_core():
    wide = _i23_rasterize((0, 0), (32, 32), 24000 / 31)
    narrow = _i23_rasterize((0, 0), (32, 32), 24000 / 31, _i23_VoronoiConfig(protection_transition_m=17.5))
    _i23_np.testing.assert_array_equal(wide['protection_mask'] == 1, narrow['protection_mask'] == 1)
    assert _i23_np.mean((wide['protection_mask'] > 0) & (wide['protection_mask'] < 1)) > _i23_np.mean((narrow['protection_mask'] > 0) & (narrow['protection_mask'] < 1))

# Source: tests.test_ridge_breakup
def test_gaussian_constant_and_support():
    c = _i24_RidgeBreakupConfig()
    offsets, weights = _i24__kernel(c)
    assert offsets.tolist() == list(range(-4, 5))
    assert _i24_np.isclose(weights.sum(), 1)
    result = _i24__gaussian(_i24_np.array([-901.0, 0.0, 400.0]), _i24_np.array([2.0, 100.0, 300.0]), c, lambda x, z: _i24_np.full_like(x, 7.0))
    _i24_np.testing.assert_allclose(result, 7, atol=1e-12)
    x, z = (_i24_np.array([-127.0, 430.0, 2010.0]), _i24_np.array([212.0, -43.0, 678.0]))
    linear = _i24__gaussian(x, z, c, lambda a, b: 2 * a - 3 * b + 11)
    _i24_np.testing.assert_allclose(linear, 2 * x - 3 * z + 11, atol=1e-10)
    value = _i24__gaussian(_i24_np.array([0.0]), _i24_np.array([0.0]), c, lambda x, z: ((x == 1500) & (z == 0)).astype(float))
    assert value[0] == 0

# Source: tests.test_ridge_breakup
def test_gaussian_reuse_matches_direct_convolution():
    c = _i24_RidgeBreakupConfig(gaussian_step_m=300.25)
    offsets, weights = _i24__kernel(c)

    def signal(x, z):
        return _i24_np.sin(x / 800) + _i24_np.cos(z / 1300)
    x = _i24_np.r_[_i24_np.linspace(-3000, 3000, 100), 100000000.0]
    z = _i24_np.r_[_i24_np.linspace(4000, -5000, 100), -100000000.0]
    actual = _i24__gaussian(x, z, c, signal)
    ix, iz = (_i24_np.floor(x / c.gaussian_step_m), _i24_np.floor(z / c.gaussian_step_m))
    fx, fz = (x / c.gaussian_step_m - ix, z / c.gaussian_step_m - iz)
    corners = []
    for dx, dz in ((0, 0), (1, 0), (0, 1), (1, 1)):
        value = _i24_np.zeros_like(x)
        for j, wz in zip(offsets, weights):
            for i, wx in zip(offsets, weights):
                value += wx * wz * signal((ix + dx + i) * c.gaussian_step_m, (iz + dz + j) * c.gaussian_step_m)
        corners.append(value)
    a, b, d, e = corners
    expected = (a * (1 - fx) + b * fx) * (1 - fz) + (d * (1 - fx) + e * fx) * fz
    _i24_np.testing.assert_array_equal(actual, expected)

# Source: tests.test_ridge_breakup
def test_switches_and_core():
    base = _i24_rasterize((0, 0), (24, 24), 1000, _i24_RidgeBreakupConfig(gaussian_sigma_m=0, warp_m=0, gap_strength=0, detail_amplitude_m=0))
    for key in ('gaussian_delta_m', 'breakup_delta_m', 'final_delta_m'):
        _i24_np.testing.assert_array_equal(base[key], base['original_delta_m'])
    full = _i24_rasterize((0, 0), (24, 24), 1000)
    core = full['protection_mask'] == 1
    assert core.any()
    for key in ('original_height_m', 'gaussian_height_m', 'breakup_height_m', 'height_m'):
        _i24_np.testing.assert_array_equal(full[key][core], full['advanced_base_m'][core])
    assert _i24_np.max(_i24_np.abs(full['breakup_delta_m'] - full['gaussian_delta_m'])) > 1
    assert _i24_np.max(_i24_np.abs(full['final_delta_m'] - full['breakup_delta_m'])) > 1

# Source: tests.test_ridge_breakup
def test_ridge_breakup_test_chunk_order_and_common_points():
    x = _i24_np.array([-100000000.0, -300.00001, -300.0, -299.99999, 0, 8000, 100000000.0])
    z = _i24_np.array([100000000.0, 0, 0, 0, 0, -9000, -100000000.0])
    original = _i24_sample_stages(x, z)
    order = [6, 0, 4, 2, 5, 1, 3]
    shuffled = _i24_sample_stages(x[order], z[order])
    chunk = _i24_sample_stages(x[:3], z[:3])
    for key in ('gaussian_delta_m', 'breakup_delta_m', 'height_m'):
        _i24_np.testing.assert_array_equal(original[key][order], shuffled[key])
        _i24_np.testing.assert_array_equal(original[key][:3], chunk[key])
        assert abs(original[key][1] - original[key][2]) < 0.1
    coarse = _i24_rasterize((-500, -500), (3, 3), 500)
    fine = _i24_rasterize((-500, -500), (5, 5), 250)
    _i24_np.testing.assert_array_equal(coarse['height_m'], fine['height_m'][::2, ::2])

# Source: tests.test_ridge_breakup
def test_parameter_and_extent_validation():
    for kwargs in ({'gap_strength': 2}, {'gaussian_step_m': 0}, {'gaussian_sigma_m': float('nan')}, {'gaussian_sigma_m': 3000, 'gaussian_step_m': 100}):
        with _i24_pytest.raises(ValueError):
            _i24_RidgeBreakupConfig(**kwargs)
    with _i24_pytest.raises(ValueError):
        _i24_sample_stages(1000000000.0, 0)

# Source: tests.test_ridge_breakup
def test_individual_breakup_controls():
    x = _i24_np.arange(12) * 1000
    z = _i24_np.arange(12)[:, None] * 1000
    common = dict(gaussian_sigma_m=0, detail_amplitude_m=0)
    baseline = _i24_sample_stages(x, z, _i24_RidgeBreakupConfig(**common, warp_m=0, gap_strength=0))
    warped = _i24_sample_stages(x, z, _i24_RidgeBreakupConfig(**common, warp_m=700, gap_strength=0))
    gap = _i24_sample_stages(x, z, _i24_RidgeBreakupConfig(**common, warp_m=0, gap_strength=1))
    assert _i24_np.max(_i24_np.abs(warped['breakup_delta_m'] - baseline['breakup_delta_m'])) > 10
    assert _i24_np.max(_i24_np.abs(gap['breakup_delta_m'] - baseline['breakup_delta_m'])) > 10
    assert _i24_np.all(_i24_np.abs(gap['breakup_delta_m']) <= _i24_np.abs(baseline['breakup_delta_m']) + 1e-10)
    _i24_np.testing.assert_array_equal(gap['final_delta_m'], gap['breakup_delta_m'])
    negative = gap['warped_delta_m'] < 0
    _i24_np.testing.assert_array_equal(gap['warped_delta_m'][negative], gap['breakup_delta_m'][negative])
    assert _i24_np.any(gap['ridge_retention'] == 0)
    assert _i24_np.any(gap['ridge_retention'] == 1)

# Source: tests.test_ridge_breakup
def test_seed_and_extent_limits():
    from terrain_pipeline.mountain_forms import VoronoiConfig
    a = _i24_sample_stages(_i24_np.arange(4) * 1000, 0)
    b = _i24_sample_stages(_i24_np.arange(4) * 1000, 0, _i24_RidgeBreakupConfig(voronoi=VoronoiConfig(world_seed=20260904, family='ridge_network')))
    assert not _i24_np.allclose(a['final_delta_m'], b['final_delta_m'])
    limit = a['metadata']['valid_coordinate_limit_m']
    _i24_sample_stages(_i24_np.array([-limit, limit]), _i24_np.array([limit, -limit]))
    with _i24_pytest.raises(ValueError):
        _i24_sample_stages(limit + 1, 0)

# Source: tests.test_procedural_mountain_erosion
def sample(x, z, *, seed=20260903, strength=0.8):
    return _i25_directional_detail(x, z, 3200.0, 0.4, -0.2, 0.3, world_seed=seed, strength=strength)

# Source: tests.test_procedural_mountain_erosion
def test_point_chunk_and_order_consistency():
    x = _i25_np.linspace(-2500, 2500, 37)
    z = _i25_np.linspace(1200, -1700, 37)
    whole = sample(x, z)
    chunks = _i25_np.concatenate([sample(x[:13], z[:13]), sample(x[13:], z[13:])])
    points = _i25_np.array([sample(a, b) for a, b in zip(x, z)])
    order = _i25_np.arange(x.size)[::-1]
    assert _i25_np.array_equal(whole, chunks)
    assert _i25_np.array_equal(whole, points)
    assert _i25_np.array_equal(whole, sample(x[order], z[order])[order])
    assert whole.dtype == _i25_np.float64

# Source: tests.test_procedural_mountain_erosion
def test_seed_strength_and_bounded_amplitude():
    x, z = _i25_np.meshgrid(_i25_np.linspace(-5000, 5000, 30), _i25_np.linspace(-3000, 3000, 20))
    a = sample(x, z, strength=1.0)
    assert _i25_np.any(a != sample(x, z, seed=5, strength=1.0))
    assert _i25_np.all(_i25_np.abs(a) <= _i25_MAX_DELTA_M)
    assert _i25_np.array_equal(sample(x, z, strength=0), _i25_np.zeros_like(x))

# Source: tests.test_procedural_mountain_erosion
def test_flat_and_phase_cancellation_are_finite():
    x = _i25_np.linspace(-12000, 12000, 1000)
    for slope in (0.0, 1e-300, 1e+300):
        result = _i25_directional_detail(x, 31, 1, slope, 0, 0, world_seed=7, strength=1)
        assert _i25_np.all(_i25_np.isfinite(result))
        assert _i25_np.all(_i25_np.abs(result) <= _i25_MAX_DELTA_M)

# Source: tests.test_procedural_mountain_erosion
@_i25_pytest.mark.parametrize('args,kwargs', [((float('nan'), 0, 0, 0, 0, 0), {}), ((0, 0, float('inf'), 0, 0, 0), {}), ((_i25_MAX_COORDINATE_M + 1, 0, 0, 0, 0, 0), {}), ((0, 0, 0, 0, 0, 1.01), {}), (([1, 2], [1, 2, 3], 0, 0, 0, 0), {}), ((0, 0, 0, 0, 0, 0), {'strength': -0.1}), ((0, 0, 0, 0, 0, 0), {'strength': float('nan')}), ((0, 0, 0, 0, 0, 0), {'world_seed': 1.5})])
def test_invalid_inputs_rejected_even_at_zero_strength(args, kwargs):
    params = {'world_seed': 1, 'strength': 0}
    params.update(kwargs)
    with _i25_pytest.raises(ValueError):
        _i25_directional_detail(*args, **params)

# Source: tests.test_procedural_mountain_erosion
@_i25_pytest.mark.parametrize('boundary', [-2400.0, -1200.0, -600.0, -300.0, 300.0, 600.0, 1200.0, 2400.0])
@_i25_pytest.mark.parametrize('axis', ['x', 'z'])
def test_cell_boundary_height_and_slope_are_continuous(boundary, axis):
    epsilon = 0.001
    positions = boundary + _i25_np.array([-2, -1, 0, 1, 2]) * epsilon
    if axis == 'x':
        values = sample(positions, _i25_np.full(5, 193.7), strength=1)
    else:
        values = sample(_i25_np.full(5, 193.7), positions, strength=1)
    left_slope = (values[2] - values[1]) / epsilon
    right_slope = (values[3] - values[2]) / epsilon
    assert abs(values[3] - values[1]) < 0.001
    assert abs(right_slope - left_slope) < 0.0001

# Source: tests.test_procedural_mountain_erosion
def test_sample_limit_and_unsigned_seed():
    from terrain_pipeline.procedural_mountain_erosion import MAX_SAMPLES
    with _i25_pytest.raises(ValueError, match='sample count'):
        sample(_i25_np.empty(0), 0)
    with _i25_pytest.raises(ValueError, match='sample count'):
        sample(_i25_np.zeros((MAX_SAMPLES // 2 + 1, 1)), _i25_np.zeros((1, 2)))
    for seed in (-1, 2 ** 64, True):
        with _i25_pytest.raises(ValueError, match='world_seed'):
            sample(0, 0, seed=seed)
    assert _i25_np.isfinite(sample(0, 0, seed=2 ** 64 - 1))

# Source: tests.test_procedural_mountain_processes
def test_processes_are_separate_seeded_and_close_budgets(monkeypatch):
    called = []
    real = _i26_processes.advance_glacier

    def wrapped(**kwargs):
        called.append(kwargs)
        return real(**kwargs)
    monkeypatch.setattr(_i26_processes, 'advance_glacier', wrapped)
    arrays, meta = _i26_processes.prepare_process_evidence((0.0, 0.0), 20260903)
    expected = _i26_rasterize((0.0, 0.0), (65, 65), 30.0, _i26_MountainConfig(world_seed=20260903))['height_m']
    _i26_np.testing.assert_array_equal(arrays['source_height_m'], expected)
    _i26_np.testing.assert_array_equal(arrays['glacier_before_m'], expected[32, 28:37])
    assert called and meta['world_seed'] == 20260903
    assert abs(meta['routing']['residual_m3_s']) < 1e-09
    assert abs(meta['diffusion']['volume_delta_m3']) < 1e-06
    assert meta['diffusion']['minimum_floor_margin_m'] >= 0
    assert meta['glacier']['ledger']['ice']['max_abs_residual_m3'] < 1e-06
    _i26_np.testing.assert_allclose(arrays['glacier_after_m'], arrays['glacier_before_m'] + arrays['glacier_final_bed_delta_m'])

# Source: tests.test_world_mountain_belts
ROOT = _i27_Path(__file__).resolve().parents[1]

# Source: tests.test_world_mountain_belts
def background(*, direction=1, thick=False, gap=False):
    config = _i27_TectonicConfig(shape=(16, 24), plate_count=2, steps=0, origin_x_m=-120000.0, origin_z_m=-80000.0)
    coverage = _i27_np.zeros((2, *config.shape))
    coverage[0, :, :12] = 1
    coverage[1, :, 12:] = 1
    continental = coverage * 35000
    oceanic = _i27_np.zeros_like(coverage)
    continental[:, :, :2] = 0
    oceanic[:, :, :2] = coverage[:, :, :2] * 7000
    if thick:
        continental[:, 2:14, 10:14] = coverage[:, 2:14, 10:14] * 52000
    if gap:
        continental[:, 7:9, :] = 0
        oceanic[:, 7:9, :] = coverage[:, 7:9, :] * 7000
    continental[:, 5, 5] = coverage[:, 5, 5] * 28000
    state = _i27_CrustState(coverage, continental, oceanic, _i27_np.array([[-70000.0, 0.0], [70000.0, 0.0]]), _i27_np.array([[1000.0 * direction, 0.0], [-1000.0 * direction, 0.0]]))
    return _i27_freeze(config, _i27_evolve(config, state))

# Source: tests.test_world_mountain_belts
class WorldMountainBeltsTests(_i27_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.base = background()
        cls.product = _i27_prepare_world_mountain_belts(cls.base)

    def test_convergent_direction_and_divergent_transform_exclusion(self):
        inventory = self.product.manifest['source_inventory']
        self.assertEqual(inventory['boundary_counts']['convergent_faces'], 16)
        self.assertEqual(len(inventory['candidates']), 1)
        self.assertEqual(inventory['candidates'][0]['kind'], 'convergent_boundary')
        self.assertGreater(self.product.arrays['mountain_height_m'].max(), 500)
        for direction in (-1, 0):
            product = _i27_prepare_world_mountain_belts(background(direction=direction))
            self.assertEqual(product.manifest['source_inventory']['ridges'], [])
            self.assertFalse(_i27_np.any(product.arrays['mountain_height_m']))

    def test_disconnected_boundary_is_not_bridged_across_sea(self):
        product = _i27_prepare_world_mountain_belts(background(gap=True))
        candidates = product.manifest['source_inventory']['candidates']
        self.assertEqual(len(candidates), 2)
        for candidate in candidates:
            points = _i27_np.asarray(candidate['vertices_m'])
            self.assertTrue(_i27_np.all(points[:, 1] < -10000) or _i27_np.all(points[:, 1] > 10000))

    def test_thick_crust_prior_is_recorded_without_inventing_history(self):
        product = _i27_prepare_world_mountain_belts(background(direction=0, thick=True))
        candidates = product.manifest['source_inventory']['candidates']
        self.assertTrue(candidates)
        self.assertEqual({c['kind'] for c in candidates}, {'thick_crust_morphology_prior'})
        self.assertTrue(all((c['threshold_m'] == 40000 for c in candidates)))
        self.assertGreater(product.arrays['mountain_height_m'].max(), 0)

    def test_determinism_and_separate_historical_seed(self):
        other = _i27_prepare_world_mountain_belts(self.base)
        self.assertEqual(other.identity, self.product.identity)
        self.assertEqual(other.manifest['world_seed'], _i27_WORLD_SEED)
        self.assertEqual(other.manifest['base_world_seed'], 20261020)
        self.assertEqual(other.manifest['base_source']['identity'], self.base.identity)
        for key in other.arrays:
            _i27_np.testing.assert_array_equal(other.arrays[key], self.product.arrays[key])

    def test_same_frozen_geometry_across_grid_spacing(self):
        finer = _i27_prepare_world_mountain_belts(self.base, _i27_WorldMountainConfig(spacing_m=2000))
        self.assertEqual(finer.manifest['source_inventory'], self.product.manifest['source_inventory'])
        x = _i27_np.array([-118001.0, -100000.0, -15123.0, 173.0, 87654.0])
        z = _i27_np.array([-77999.0, -50000.0, 17000.0, 34123.0, 71001.0])
        coarse_values = self.product.evaluate_geometry(x, z)
        fine_values = finer.evaluate_geometry(x, z)
        for key in coarse_values:
            _i27_np.testing.assert_array_equal(coarse_values[key], fine_values[key])

    def test_no_evolution_no_wrap_and_read_only_query(self):
        with _i27_patch('terrain_pipeline.tectonic.evolve', side_effect=AssertionError), _i27_patch.object(type(self.base), 'sample', side_effect=AssertionError):
            product = _i27_prepare_world_mountain_belts(self.base)
            first = product.evaluate_geometry(-120000.0, -75000.0)
            source = self.base.arrays['final/elevation_m'][0, 0]
            self.assertEqual(float(first['raw_elevation_m']), source)
            result = product.query(-120000.0, -80000.0)
            self.assertEqual(float(result['elevation_m']), product.arrays['elevation_m'][0, 0])
        for values in product.arrays.values():
            with self.assertRaises(ValueError):
                values.setflags(write=True)
        manifest = product.manifest
        manifest['world_seed'] = 9
        self.assertEqual(product.manifest['world_seed'], _i27_WORLD_SEED)

    def test_query_centres_reverse_overlap_and_no_cache_growth(self):
        grid = self.product.manifest['grid']
        x = grid['origin_x_m'] + (_i27_np.arange(grid['shape'][1]) + 0.5) * grid['spacing_m']
        z = grid['origin_z_m'] + (_i27_np.arange(grid['shape'][0]) + 0.5) * grid['spacing_m']
        before = set(vars(self.product))
        values = self.product.query(x[None, :], z[:, None])
        reverse = self.product.query(x[::-1][None, :], z[::-1, None])
        overlap = self.product.query(x[10:20][None, :], z[3:15, None])
        for key in values:
            _i27_np.testing.assert_array_equal(values[key], self.product.arrays[key])
            _i27_np.testing.assert_array_equal(reverse[key][::-1, ::-1], values[key])
            _i27_np.testing.assert_array_equal(overlap[key], values[key][3:15, 10:20])
        self.assertEqual(set(vars(self.product)), before)

    def test_bent_ridge_bisector_has_continuous_peak_phase(self):
        inventory = self.product.manifest['source_inventory']
        inventory['ridges'] = [{'source_id': 'bent-test', 'role': 'main', 'style': 'folded_ranges', 'vertices_m': [[-50000.0, 0.0], [0.0, 0.0], [0.0, 50000.0]], 'width_m': 30000.0, 'amplitude_m': 2000.0, 'peak_spacing_m': 45000.0, 'phase': 0.8, 'cross_power': 1.5}]
        inventory['basins'] = []
        with _i27_patch('terrain_pipeline.mountain_forms._inventory', return_value=inventory):
            product = _i27_prepare_world_mountain_belts(self.base)
        differences = []
        for epsilon in (1.0, 0.01, 0.0001):
            values = product.evaluate_geometry(_i27_np.array([-20000.0, -20000.0]), _i27_np.array([20000.0 - epsilon, 20000.0 + epsilon]))['mountain_height_m']
            differences.append(float(abs(values[1] - values[0])))
        self.assertLess(differences[-1], 0.0001)
        self.assertLess(differences[1], differences[0] * 0.02)
        self.assertLess(differences[2], differences[1] * 0.02)

    def test_ocean_inland_negative_and_stage_composition(self):
        arrays = self.product.arrays
        ocean = arrays['ocean_connected']
        self.assertTrue(_i27_np.any(arrays['inland_depression']))
        self.assertFalse(_i27_np.any(ocean & arrays['inland_depression']))
        _i27_np.testing.assert_array_equal(arrays['elevation_m'][ocean], arrays['raw_elevation_m'][ocean])
        self.assertFalse(_i27_np.any(arrays['mountain_height_m'][ocean]))
        self.assertFalse(_i27_np.any(arrays['basin_depth_m'][ocean]))
        _i27_np.testing.assert_allclose(arrays['elevation_m'], arrays['base_elevation_m'] + arrays['mountain_height_m'] - arrays['basin_depth_m'], atol=0.0005)
        inland = arrays['inland_depression']
        _i27_np.testing.assert_array_equal(arrays['elevation_m'][inland], arrays['raw_elevation_m'][inland])
        disabled = _i27_prepare_world_mountain_belts(self.base, _i27_WorldMountainConfig(flatten_base=False, amplitude_scale=0))
        _i27_np.testing.assert_array_equal(disabled.arrays['elevation_m'], disabled.arrays['raw_elevation_m'])

    def test_invalid_coordinates_configuration_and_budgets(self):
        for x, z in ((-120001.0, 0), (120000.0, 0), (0, 80000.0), (0, -80001.0), (_i27_np.nan, 0), (0, _i27_np.inf)):
            for method in (self.product.query, self.product.evaluate_geometry):
                with self.assertRaises(ValueError):
                    method(x, z)
        for kwargs in ({'spacing_m': 0}, {'spacing_m': _i27_np.nan}, {'world_seed': True}, {'max_belts': 0}, {'amplitude_scale': -1}):
            with self.assertRaises(ValueError):
                _i27_WorldMountainConfig(**kwargs)
        for kwargs in ({'max_cells': 10}, {'max_source_cells': 10}, {'max_segments': 1}, {'spacing_m': 7000}):
            with self.assertRaises(ValueError):
                _i27_prepare_world_mountain_belts(self.base, _i27_WorldMountainConfig(**kwargs))

    def test_save_cold_read_no_overwrite_and_tamper_rejection(self):
        with _i27_tempfile.TemporaryDirectory(dir=ROOT / '.scratch') as directory:
            path = _i27_Path(directory) / 'product.npz'
            _i27_save_product(self.product, path)
            with _i27_patch('terrain_pipeline.mountain_forms.prepare_world_mountain_belts', side_effect=AssertionError):
                loaded = _i27_load_product(path, expected_identity=self.product.identity)
                _i27_np.testing.assert_array_equal(loaded.evaluate_geometry(0, 0)['elevation_m'], self.product.evaluate_geometry(0, 0)['elevation_m'])
            with self.assertRaises(FileExistsError):
                _i27_save_product(self.product, path)
            with self.assertRaises(ValueError):
                _i27_load_product(path, expected_identity='wrong')
            with _i27_np.load(path, allow_pickle=False) as archive:
                payload = {k: archive[k].copy() for k in archive.files}
            payload['elevation_m'][4, 4] += 1
            bad = _i27_Path(directory) / 'tampered.npz'
            _i27_np.savez(bad, **payload)
            with self.assertRaises(ValueError):
                _i27_load_product(bad)

    def test_real_source_has_curved_main_parallel_branch_peak_saddles(self):
        path = ROOT / '.scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz'
        if not path.exists():
            self.skipTest('local shaped-v4 source unavailable')
        base = _i27_load_base(path)
        product = _i27_prepare_world_mountain_belts(base)
        inventory = product.manifest['source_inventory']
        self.assertEqual({r['role'] for r in inventory['ridges']}, {'main', 'parallel', 'oblique_branch'})
        self.assertEqual(len({r['style'] for r in inventory['ridges']}), 3)
        self.assertTrue(inventory['basins'])
        self.assertGreater(product.arrays['basin_depth_m'].max(), 100)
        main = max((r for r in inventory['ridges'] if r['role'] == 'main'), key=lambda r: _i27_np.linalg.norm(_i27_np.diff(r['vertices_m'], axis=0), axis=1).sum())
        points = _i27_np.asarray(main['vertices_m'])
        self.assertGreater(_i27_np.linalg.norm(_i27_np.diff(points, axis=0), axis=1).sum(), _i27_np.linalg.norm(points[-1] - points[0]) * 1.01)
        length = _i27_np.concatenate(([0.0], _i27_np.cumsum(_i27_np.linalg.norm(_i27_np.diff(points, axis=0), axis=1))))
        distance = _i27_np.linspace(length[-1] * 0.1, length[-1] * 0.9, 200)
        x = _i27_np.interp(distance, length, points[:, 0])
        z = _i27_np.interp(distance, length, points[:, 1])
        values = product.evaluate_geometry(x, z)['mountain_height_m']
        extrema = _i27_np.diff(_i27_np.sign(_i27_np.diff(values)))
        self.assertGreater(_i27_np.count_nonzero(extrema < 0), 2)
        self.assertGreater(float(_i27_np.ptp(values)), 300)

    def test_real_ocean_cell_faces_have_continuous_geometry(self):
        path = ROOT / '.scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz'
        if not path.exists():
            self.skipTest('local shaped-v4 source unavailable')
        base = _i27_load_base(path)
        product = _i27_prepare_world_mountain_belts(base)
        ocean = base.arrays['final/ocean_connected']
        config = base.manifest['config']
        spacing = config['cell_size_m']
        for axis in (0, 1):
            if axis == 1:
                rows, cols = _i27_np.nonzero(ocean[:, :-1] != ocean[:, 1:])
                x = config['origin_x_m'] + (cols + 1) * spacing
                z = config['origin_z_m'] + (rows + 0.5) * spacing
                left = product.evaluate_geometry(x - 0.001, z)
                right = product.evaluate_geometry(x + 0.001, z)
            else:
                rows, cols = _i27_np.nonzero(ocean[:-1, :] != ocean[1:, :])
                x = config['origin_x_m'] + (cols + 0.5) * spacing
                z = config['origin_z_m'] + (rows + 1) * spacing
                left = product.evaluate_geometry(x, z - 0.001)
                right = product.evaluate_geometry(x, z + 0.001)
            for field in ('raw_elevation_m', 'base_elevation_m', 'mountain_height_m', 'basin_depth_m', 'elevation_m'):
                self.assertLess(float(_i27_np.max(abs(left[field] - right[field]))), 0.1, field)

    def test_styles_change_sections_and_branch_structure(self):
        path = ROOT / '.scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz'
        if not path.exists():
            self.skipTest('local shaped-v4 source unavailable')
        product = _i27_prepare_world_mountain_belts(_i27_load_base(path))
        ridges = product.manifest['source_inventory']['ridges']
        for main in (r for r in ridges if r['role'] == 'main'):
            relatives = [r for r in ridges if r['source_id'] == main['source_id']]
            parallel = [r for r in relatives if r['role'] == 'parallel']
            self.assertEqual(len(parallel), 1 if main['style'] == 'block_plateau_margin' else 2)
            if main['style'] == 'worn_ranges':
                self.assertTrue(all((r['amplitude_m'] <= main['amplitude_m'] * 0.33 for r in relatives if r['role'] != 'main')))
        points = _i27_np.array([[-100000.0, 0.0], [100000.0, 0.0]])
        section = {'width_m': 20000.0, 'amplitude_m': 2000.0, 'peak_spacing_m': 60000.0, 'phase': 0.4}
        profiles = {}
        for style, power in (('folded', 1.5), ('block', 3.7), ('worn', 2.3)):
            profiles[style] = _i27__ridge_height({**section, 'cross_power': power}, points, _i27_np.zeros(3), _i27_np.array([0.0, 10000.0, 30000.0]))
            profiles[style] /= profiles[style][0]
        self.assertGreater(profiles['block'][1], profiles['folded'][1] + 0.15)
        self.assertLess(profiles['block'][2], profiles['worn'][2] * 0.5)
