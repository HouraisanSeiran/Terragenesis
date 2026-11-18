"""山体形态生成：骨架、体量、破碎、山带与过程证据（A 类）。

合并自 `advanced_terrain_filter`、`product_mountains`、`local_volume_mountains`、
`procedural_mountains`、`voronoi_mountains`、`ridge_breakup`、`world_mountain_belts`、
`procedural_mountain_processes`。同组重名的 `ALGORITHM` / `ALGORITHM_ID` / `FAMILIES` /
`sample_stages` / `rasterize` / `_coordinates` 按算法线起命名变体。
`ProductMountainConfig`、`_fields`、`ProductMountainConfig` 相关名字**保持原样**——
织梦闭包 `skeleton_mountains` 直接引用它们。
"""


# ========================================================================
# 外部依赖（合并前各旧文件的 import，去重后集中在此）
# ========================================================================
from dataclasses import dataclass
import hashlib
import numbers
import numpy as np
import math
from diffusion.geographic_noise import _hash, smooth_noise
from terrain_pipeline.common_infra import WORLD_SEED, derive_subseed
from dataclasses import asdict, dataclass
from diffusion.geographic_noise import smooth_noise
from terrain_pipeline.common_infra import WORLD_SEED, SEED_DERIVATION, derive_subseed
from dataclasses import asdict, dataclass, field
from terrain_pipeline.common_infra import derive_subseed
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
from scipy.ndimage import gaussian_filter1d, label
from diffusion.geographic_noise import field as noise_field
from terrain_pipeline.tectonic import FrozenTectonicProduct
from terrain_pipeline.common_infra import WORLD_SEED
from terrain_pipeline.common_infra import TerrainGrid, BoundaryGrid
from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
from terrain_pipeline.drainage import accumulate_local_discharge as accumulate_local_discharge
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import conservative_diffusion_step
from terrain_pipeline.environment_processes import advance_glacier



# ------------------------------------------------------------------------
# 原 terrain_pipeline/advanced_terrain_filter.py
# ------------------------------------------------------------------------

ADVANCED_ALGORITHM_ID = 'advanced-terrain-filter-v2-stable-hash'


SEED_DERIVATION_ID = 'advanced-terrain-filter-v1'


MAX_SAMPLES = 1_048_576


MAX_COORDINATE_M = 1_000_000_000.0


@dataclass(frozen=True)
class AdvancedFilterConfig:
    amplitude_m: float = 400.0
    wavelength_m: float = 1800.0
    octaves: int = 3
    gain: float = 0.5
    lacunarity: float = 2.0
    gully_weight: float = 0.5
    detail: float = 1.5
    rounding: tuple = (0.1, 0.0, 0.1, 2.0)
    onset: tuple = (1.25, 1.25, 2.8, 1.5)
    assumed_slope: tuple = (0.7, 1.0)
    cell_scale: float = 0.7
    normalization: float = 0.5
    hash_mode: str = 'stable'


def _check_config(c):
    if not isinstance(c, AdvancedFilterConfig):
        raise ValueError('config must be AdvancedFilterConfig')
    if c.hash_mode not in ('stable', 'upstream'):
        raise ValueError('hash_mode must be stable or upstream')
    for name, low, high in (('amplitude_m', 0, 1e6), ('wavelength_m', 1, 1e9),
                            ('gain', 0, 1), ('lacunarity', 1, 4),
                            ('gully_weight', 0, 1), ('detail', 0.01, 8),
                            ('cell_scale', 0.01, 4), ('normalization', 0, 0.999)):
        v = getattr(c, name)
        if isinstance(v, (bool, np.bool_)) or not isinstance(v, numbers.Real) or not np.isfinite(v) or not low <= v <= high:
            raise ValueError(f'invalid {name}')
    if 0 < c.amplitude_m < 0.001:
        raise ValueError('nonzero amplitude_m must be at least 0.001 m')
    if isinstance(c.octaves, bool) or not isinstance(c.octaves, numbers.Integral) or not 1 <= c.octaves <= 8:
        raise ValueError('octaves must be in [1, 8]')
    for name, n, upper in (('rounding', 4, 8), ('onset', 4, 8), ('assumed_slope', 2, 8)):
        a = np.asarray(getattr(c, name), dtype=np.float64)
        if a.shape != (n,) or not np.all(np.isfinite(a)) or np.any(a < 0) or np.any(a > upper):
            raise ValueError(f'invalid {name}')
    if c.assumed_slope[1] > 1:
        raise ValueError('assumed_slope mix must be in [0, 1]')


def _hash2(x, z, seed):
    kx, kz = 1.0 / np.pi, np.exp(-1.0)
    x = (x + seed * 0.06711056) * kx + kz
    z = (z + seed * 0.00583715) * kz + kx
    q = x * z * (x + z)
    t = q - np.floor(q)
    a, b = 16 * kx * t, 16 * kz * t
    return -1 + 2 * (a - np.floor(a)), -1 + 2 * (b - np.floor(b))


def _stable_hash2(x, z, seed):
    """Hash signed integer lattice cells with independent uint64 lanes."""
    def lane(salt):
        with np.errstate(over='ignore'):
            v = x.astype(np.int64).astype(np.uint64) * np.uint64(0x9E3779B185EBCA87)
            v ^= z.astype(np.int64).astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F)
            v ^= np.uint64(seed) + np.uint64(salt)
            v ^= v >> np.uint64(30)
            v *= np.uint64(0xBF58476D1CE4E5B9)
            v ^= v >> np.uint64(27)
            v *= np.uint64(0x94D049BB133111EB)
            v ^= v >> np.uint64(31)
        return -1.0 + (v >> np.uint64(11)).astype(np.float64) * (2.0 / 9007199254740992.0)
    return lane(0xA0761D6478BD642F), lane(0xE7037ED1A0B428DB)


def _phacelle(x, z, dx, dz, cell_scale, normalization, seed, hash_mode):
    side_x, side_z = -dz * cell_scale * (2 * np.pi), dx * cell_scale * (2 * np.pi)
    ix, iz = np.floor(x), np.floor(z)
    fx, fz = x - ix, z - iz
    co, si, total = np.zeros_like(x), np.zeros_like(x), np.zeros_like(x)
    for i in (-1, 0, 1, 2):
        for j in (-1, 0, 1, 2):
            hash_fn = _stable_hash2 if hash_mode == 'stable' else _hash2
            hx, hz = hash_fn(ix + i, iz + j, seed)
            rx, rz = fx - i - hx * 0.5, fz - j - hz * 0.5
            weight = np.maximum(0.0, np.exp(-2 * (rx * rx + rz * rz)) - 0.01111)
            phase = rx * side_x + rz * side_z + np.pi * 0.5
            co += np.cos(phase) * weight
            si += np.sin(phase) * weight
            total += weight
    co, si = co / total, si / total
    magnitude = np.maximum(1 - normalization, np.hypot(co, si))
    return co / magnitude, si / magnitude, side_x, side_z


def _ease(t):
    return 1 - (1 - np.clip(t, 0, 1)) ** 2


def _smooth_start(t, smoothing):
    # Upstream's branch avoids zero division when smoothing is zero.
    t, smoothing = np.broadcast_arrays(t, smoothing)
    result = t - 0.5 * smoothing
    curved = t < smoothing
    # Evaluate only where the quadratic branch applies; t / smoothing < 1.
    ratio = np.divide(t, smoothing, out=np.zeros_like(t), where=curved)
    return np.where(curved, 0.5 * t * ratio, result)


def filter_height(x_m, z_m, base_height_m, slope_x, slope_z, fade_target, *, world_seed, config=None):
    """Return height, delta, artistic slopes and ridge map at broadcast points.

    Coordinates are in [-1e9,1e9] metres; target is in [-1,1], slopes are
    dimensionless metres/metre. Seed is uint64; sample count is 1..1048576.
    """
    c = AdvancedFilterConfig() if config is None else config
    _check_config(c)
    if isinstance(world_seed, (bool, np.bool_)) or not isinstance(world_seed, numbers.Integral) or not 0 <= world_seed < 2**64:
        raise ValueError('world_seed must be an unsigned 64-bit integer')
    try:
        x, z, h, sx, sz, target = np.broadcast_arrays(*[np.asarray(v, dtype=np.float64) for v in (x_m,z_m,base_height_m,slope_x,slope_z,fade_target)])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('inputs must be broadcastable real numbers') from exc
    if x.size == 0 or x.size > MAX_SAMPLES:
        raise ValueError('broadcast sample count must be in [1,1048576]')
    if any(not np.all(np.isfinite(v)) for v in (x,z,h,sx,sz,target)):
        raise ValueError('inputs must be finite')
    if np.any(np.abs(x) > MAX_COORDINATE_M) or np.any(np.abs(z) > MAX_COORDINATE_M):
        raise ValueError('coordinates exceed fixed domain')
    if np.any(np.abs(target) > 1):
        raise ValueError('fade_target must be in [-1,1]')
    if c.amplitude_m == 0:
        zero = np.zeros_like(x)
        return {'height_m': h.copy(), 'delta_m': zero, 'artistic_slope_x': sx.copy(), 'artistic_slope_z': sz.copy(), 'ridge_map': zero.copy()}
    # Bound extreme finite slopes so derived arithmetic cannot overflow.
    if np.any(np.abs(sx) > 1e6) or np.any(np.abs(sz) > 1e6):
        raise ValueError('slope magnitude component exceeds 1e6')
    digest = hashlib.sha256(f'{SEED_DERIVATION_ID}:{world_seed}:phacelle'.encode('ascii')).digest()
    seed = (int.from_bytes(digest[:8], 'little') if c.hash_mode == 'stable'
            else int.from_bytes(digest[:4], 'little') % 1_000_000)
    px, pz = x / c.wavelength_m, z / c.wavelength_m
    xs, zs = sx * (c.wavelength_m / c.amplitude_m), sz * (c.wavelength_m / c.amplitude_m)
    length = np.maximum(np.hypot(xs, zs), 1e-10)
    r, o = c.rounding, c.onset
    rounded = (r[1] + (r[0] - r[1]) * np.clip(target + 0.5, 0, 1)) * r[2]
    mask = _ease(_smooth_start(length * o[0], rounded * o[0]))
    ridge_mask, ridge_target = _ease(length * o[2]), target.copy()
    gx = xs * (1-c.assumed_slope[1]) + xs / length * c.assumed_slope[0] * c.assumed_slope[1]
    gz = zs * (1-c.assumed_slope[1]) + zs / length * c.assumed_slope[0] * c.assumed_slope[1]
    delta = np.zeros_like(x)
    freq, strength, rounding_mult = 1.0, 1.0, 1.0
    fade = target.copy()
    for _ in range(c.octaves):
        norm = np.hypot(gx, gz)
        dx = np.divide(gx, norm, out=np.zeros_like(gx), where=norm > 1e-10)
        dz = np.divide(gz, norm, out=np.zeros_like(gz), where=norm > 1e-10)
        co, si, side_x, side_z = _phacelle(px * freq, pz * freq, dx, dz, c.cell_scale, c.normalization, seed, c.hash_mode)
        side_x, side_z = -side_x * freq, -side_z * freq
        gx += np.sign(si) * side_x * strength * c.gully_weight
        gz += np.sign(si) * side_z * strength * c.gully_weight
        layer = fade * (1-mask) + co * c.gully_weight * mask
        delta += layer * strength
        xs += si * side_x * c.gully_weight * mask * strength
        zs += si * side_z * c.gully_weight * mask * strength
        fade = layer
        rounded = (r[1] + (r[0]-r[1]) * np.clip(co + 0.5, 0, 1)) * rounding_mult
        new_mask = _ease(_smooth_start(np.abs(si)*o[1], rounded*o[1]))
        mask = (1 - (1 - np.clip(mask, 0, 1)) ** c.detail) * new_mask
        ridge_target = ridge_target * (1-ridge_mask) + co * ridge_mask
        ridge_mask *= _ease(np.abs(si)*o[3])
        strength *= c.gain
        freq *= c.lacunarity
        rounding_mult *= r[3]
    delta = delta * c.amplitude_m
    return {'height_m': np.asarray(h + delta), 'delta_m': np.asarray(delta),
            'artistic_slope_x': np.asarray(xs * c.amplitude_m / c.wavelength_m),
            'artistic_slope_z': np.asarray(zs * c.amplitude_m / c.wavelength_m),
            'ridge_map': np.asarray(ridge_target * (1-ridge_mask))}



# ------------------------------------------------------------------------
# 原 terrain_pipeline/product_mountains.py
# ------------------------------------------------------------------------

PRODUCT_ALGORITHM_ID = "product-mountains-v2-smooth-mass"


HALO_M = 600.0


@dataclass(frozen=True)
class ProductMountainConfig:
    world_seed: int = WORLD_SEED
    alpha: float = 0.65
    base_m: float = 200.0
    amplitude_m: float = 3200.0
    ridge_power: float = 2.0
    ridge_smoothing: float = 0.04
    ridge_spacing_m: float = 9000.0
    warp_m: float = 1700.0
    cell_size_m: float = 6000.0
    anisotropy: float = 1.6
    advanced_enabled: bool = True
    advanced_amplitude_m: float = 150.0
    advanced_wavelength_m: float = 1800.0
    batch_size: int = 4096

    def __post_init__(self):
        derive_subseed(self.world_seed, "product-ridge")
        for name, lo, hi in (("alpha", 0, 1), ("base_m", -10000, 10000),
                             ("amplitude_m", 0, 10000), ("ridge_power", 0.1, 10),
                             ("ridge_smoothing", 0.001, 1),
                             ("ridge_spacing_m", 500, 100000), ("warp_m", 0, 10000),
                             ("cell_size_m", 500, 100000), ("anisotropy", 1, 3),
                             ("advanced_amplitude_m", 0, 1000),
                             ("advanced_wavelength_m", 100, 100000)):
            v = getattr(self, name)
            if isinstance(v, (bool, np.bool_)) or not isinstance(v, numbers.Real) or not math.isfinite(v) or not lo <= v <= hi:
                raise ValueError(f"invalid {name}")
        if 0 < self.advanced_amplitude_m < 0.001:
            raise ValueError("advanced_amplitude_m must be zero or at least 0.001")
        if not isinstance(self.advanced_enabled, bool):
            raise ValueError("advanced_enabled must be bool")
        if isinstance(self.batch_size, bool) or not isinstance(self.batch_size, numbers.Integral) or not 1 <= self.batch_size <= 65536:
            raise ValueError("invalid batch_size")


def _fields(x, z, c, seeds):
    ridge_seed, warp_seed, site_seed = seeds
    wx = x + c.warp_m * smooth_noise(x, z, 24000.0, warp_seed, 1)
    wz = z + c.warp_m * smooth_noise(x, z, 24000.0, warp_seed, 2)
    # A stretched, rotated domain produces long continuous crests at two scales.
    u = (0.8660254037844386 * wx + 0.5 * wz) / 2.5
    v = -0.5 * wx + 0.8660254037844386 * wz
    n = (0.72 * smooth_noise(u, v, c.ridge_spacing_m, ridge_seed, 1)
         + 0.28 * smooth_noise(u, v, c.ridge_spacing_m / 2, ridge_seed, 2))
    eps = c.ridge_smoothing
    smooth_abs = (np.sqrt(n * n + eps * eps) - eps) / (np.sqrt(1 + eps * eps) - eps)
    ridge = np.clip(1 - smooth_abs, 0, 1)
    gx = (0.8660254037844386 * wx + 0.5 * wz) / (c.cell_size_m * c.anisotropy)
    gz = (-0.5 * wx + 0.8660254037844386 * wz) / c.cell_size_m
    ix, iz = np.floor(gx).astype(np.int64), np.floor(gz).astype(np.int64)
    remainder = np.ones(x.shape)
    for dz in range(-1, 2):
        for dx in range(-1, 2):
            cx, cz = ix + dx, iz + dz
            sx = cx + 0.5 + 0.25 * _hash(cx, cz, site_seed, 1)
            sz = cz + 0.5 + 0.25 * _hash(cx, cz, site_seed, 2)
            distance = np.hypot(gx - sx, gz - sz)
            t = np.clip((distance - 1.0) / 0.25, 0, 1)
            cutoff = 1 - t * t * (3 - 2 * t)
            weight = np.exp(-2.2 * distance * distance) * cutoff
            remainder *= 1 - weight
    volume = 1 - remainder
    macro = c.base_m + c.amplitude_m * ridge ** c.ridge_power * ((1 - c.alpha) + c.alpha * volume)
    return ridge, volume, macro


def sample_product_mountains(x_m, z_m, config=None):
    """Sample stages at broadcast coordinates, bounded per working batch.

    Fixed 30 m central derivatives and 600 m four-neighbor curvature drive
    Advanced. Every input coordinate must retain its complete 600 m halo.
    Arrays have the broadcast shape; no sampling spacing is assumed.
    """
    c = ProductMountainConfig() if config is None else config
    if not isinstance(c, ProductMountainConfig):
        raise ValueError("config must be ProductMountainConfig")
    try:
        x, z = np.broadcast_arrays(np.asarray(x_m, dtype=np.float64), np.asarray(z_m, dtype=np.float64))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("coordinates must be broadcastable real numbers") from exc
    if x.size == 0 or x.size > MAX_SAMPLES or not np.all(np.isfinite(x)) or not np.all(np.isfinite(z)):
        raise ValueError("invalid sample count or nonfinite coordinates")
    if np.any(np.abs(x) > MAX_COORDINATE_M - HALO_M) or np.any(np.abs(z) > MAX_COORDINATE_M - HALO_M):
        raise ValueError("neighborhood exceeds coordinate domain")
    seeds = tuple(derive_subseed(c.world_seed, purpose) for purpose in ("product-ridge", "product-warp", "product-voronoi-sites"))
    keys = ("ridge", "volume", "macro_height_m", "height_m", "delta_m", "slope_x", "slope_z", "fade_target")
    arrays = {key: np.empty(x.size, dtype=np.float64) for key in keys}
    xf, zf = x.ravel(), z.ravel()
    advanced_config = AdvancedFilterConfig(amplitude_m=c.advanced_amplitude_m, wavelength_m=c.advanced_wavelength_m, octaves=3)
    for start in range(0, x.size, c.batch_size):
        end = min(start + c.batch_size, x.size)
        bx, bz = xf[start:end], zf[start:end]
        ridge, volume, macro = _fields(bx, bz, c, seeds)
        def height(dx, dz):
            return _fields(bx + dx, bz + dz, c, seeds)[2]
        sx = (height(30, 0) - height(-30, 0)) / 60
        sz = (height(0, 30) - height(0, -30)) / 60
        neighbors = (height(600, 0) + height(-600, 0) + height(0, 600) + height(0, -600)) * 0.25
        target = np.clip((macro - neighbors) / 120.0, -1, 1)
        if c.advanced_enabled:
            filtered = filter_height(bx, bz, macro, sx, sz, target, world_seed=c.world_seed, config=advanced_config)
            final, delta = filtered["height_m"], filtered["delta_m"]
        else:
            final, delta = macro, np.zeros_like(macro)
        for key, value in zip(keys, (ridge, volume, macro, final, delta, sx, sz, target)):
            arrays[key][start:end] = value
    return {key: value.reshape(x.shape) for key, value in arrays.items()}



# ------------------------------------------------------------------------
# 原 terrain_pipeline/local_volume_mountains.py
# ------------------------------------------------------------------------

LOCAL_VOLUME_ALGORITHM_ID = "local-volume-mountains-v1"


@dataclass(frozen=True)
class LocalVolumeConfig:
    world_seed: int = WORLD_SEED
    k: float = 0.35
    depth_gain: float = 2.4
    cell_size_m: float = 6000.0
    selection_scale_m: float = 24000.0
    cell_threshold_low: float = 0.80
    cell_threshold_high: float = 0.95
    selection_threshold_low: float = 0.70
    selection_threshold_high: float = 0.85
    slope_fade_low: float = 0.02
    slope_fade_high: float = 0.08
    advanced_enabled: bool = True
    batch_size: int = 4096

    def __post_init__(self):
        derive_subseed(self.world_seed, "local-volume-sites")
        for name, lo, hi in (("k", 0, 2), ("depth_gain", 1, 10),
                             ("cell_size_m", 500, 100000),
                             ("selection_scale_m", 500, 1000000),
                             ("cell_threshold_low", 0, 1),
                             ("cell_threshold_high", 0, 1),
                             ("selection_threshold_low", 0, 1),
                             ("selection_threshold_high", 0, 1),
                             ("slope_fade_low", 0, 10),
                             ("slope_fade_high", 0, 10)):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real) or not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f"invalid {name}")
        for low, high in ((self.cell_threshold_low, self.cell_threshold_high),
                          (self.selection_threshold_low, self.selection_threshold_high),
                          (self.slope_fade_low, self.slope_fade_high)):
            if low >= high:
                raise ValueError("thresholds must be strictly increasing")
        if not isinstance(self.advanced_enabled, bool):
            raise ValueError("advanced_enabled must be bool")
        if isinstance(self.batch_size, bool) or not isinstance(self.batch_size, numbers.Integral) or not 1 <= self.batch_size <= 65536:
            raise ValueError("invalid batch_size")


def _smoothstep(value, low, high):
    t = np.clip((value - low) / (high - low), 0, 1)
    return t * t * (3 - 2 * t)


def _local_fields(x, z, c, site_seed, selection_seed):
    gx, gz = x / c.cell_size_m, z / c.cell_size_m
    ix, iz = np.floor(gx).astype(np.int64), np.floor(gz).astype(np.int64)
    remainder = np.ones(x.shape)
    for dz in range(-1, 2):
        for dx in range(-1, 2):
            cx, cz = ix + dx, iz + dz
            sx = cx + 0.5 + 0.25 * _hash(cx, cz, site_seed, 1)
            sz = cz + 0.5 + 0.25 * _hash(cx, cz, site_seed, 2)
            distance = np.hypot(gx - sx, gz - sz)
            cutoff = 1 - _smoothstep(distance, 1.0, 1.25)
            remainder *= 1 - np.exp(-2.2 * distance * distance) * cutoff
    local_v = 1 - remainder
    selection = (smooth_noise(x, z, c.selection_scale_m, selection_seed, 1) + 1) * 0.5
    w = _smoothstep(selection, c.selection_threshold_low, c.selection_threshold_high)
    p = _smoothstep(local_v, c.cell_threshold_low, c.cell_threshold_high) * w
    return local_v, w, p


def sample_local_volume_mountains(x_m, z_m, config=None):
    """Return deterministic stages at broadcast coordinates with bounded batches.

    Inputs must retain a 600 m halo inside the fixed +/-1e9 m domain. The
    returned raw Advanced delta precedes slope fade and negative-only gain.
    """
    c = LocalVolumeConfig() if config is None else config
    if not isinstance(c, LocalVolumeConfig):
        raise ValueError("config must be LocalVolumeConfig")
    try:
        x, z = np.broadcast_arrays(np.asarray(x_m, dtype=np.float64), np.asarray(z_m, dtype=np.float64))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("coordinates must be broadcastable real numbers") from exc
    if x.size == 0 or x.size > MAX_SAMPLES or not np.all(np.isfinite(x)) or not np.all(np.isfinite(z)):
        raise ValueError("invalid sample count or nonfinite coordinates")
    if np.any(np.abs(x) > MAX_COORDINATE_M - HALO_M) or np.any(np.abs(z) > MAX_COORDINATE_M - HALO_M):
        raise ValueError("neighborhood exceeds coordinate domain")
    product_config = ProductMountainConfig(world_seed=c.world_seed, advanced_enabled=False)
    product_seeds = tuple(derive_subseed(c.world_seed, purpose) for purpose in
                          ("product-ridge", "product-warp", "product-voronoi-sites"))
    site_seed = derive_subseed(c.world_seed, "local-volume-sites")
    selection_seed = derive_subseed(c.world_seed, "local-volume-selection")
    advanced_config = AdvancedFilterConfig(amplitude_m=150, wavelength_m=1800, octaves=3)
    keys = ("h0_m", "local_v", "selection_w", "p", "volume_delta_m", "macro_height_m",
            "slope_x", "slope_z", "fade_target", "slope_fade", "raw_advanced_delta_m",
            "final_delta_m", "height_m")
    arrays = {key: np.empty(x.size, dtype=np.float64) for key in keys}
    xf, zf = x.ravel(), z.ravel()
    for start in range(0, x.size, c.batch_size):
        end = min(start + c.batch_size, x.size)
        bx, bz = xf[start:end], zf[start:end]
        def fields(dx, dz):
            xx, zz = bx + dx, bz + dz
            h0 = _fields(xx, zz, product_config, product_seeds)[2]
            v, w, p = _local_fields(xx, zz, c, site_seed, selection_seed)
            delta = c.k * p * np.maximum(h0 - 200.0, 0)
            return h0, v, w, p, delta, h0 + delta
        h0, v, w, p, volume_delta, macro = fields(0, 0)
        sx = (fields(30, 0)[5] - fields(-30, 0)[5]) / 60
        sz = (fields(0, 30)[5] - fields(0, -30)[5]) / 60
        neighbors = (fields(600, 0)[5] + fields(-600, 0)[5] + fields(0, 600)[5] + fields(0, -600)[5]) * 0.25
        target = np.clip((macro - neighbors) / 120, -1, 1)
        fade = _smoothstep(np.hypot(sx, sz), c.slope_fade_low, c.slope_fade_high)
        if c.advanced_enabled:
            raw = filter_height(bx, bz, macro, sx, sz, target, world_seed=c.world_seed, config=advanced_config)["delta_m"]
        else:
            raw = np.zeros_like(macro)
        final_delta = fade * np.where(raw < 0, raw * c.depth_gain, raw)
        for key, value in zip(keys, (h0, v, w, p, volume_delta, macro, sx, sz, target, fade, raw, final_delta, macro + final_delta)):
            arrays[key][start:end] = value
    return {key: value.reshape(x.shape) for key, value in arrays.items()}



# ------------------------------------------------------------------------
# 原 terrain_pipeline/procedural_mountains.py
# ------------------------------------------------------------------------

PROCEDURAL_ALGORITHM = "procedural-mountains-v3"


GRADIENT_STEP_M = 30.0


PROCEDURAL_FAMILIES = ("mixed", "granite_dome", "layered_massif", "glacial_horn")


@dataclass(frozen=True)
class MountainConfig:
    """World seed, morphology family and detail strength 0 or [1e-6, 1]."""

    world_seed: int = WORLD_SEED
    family: str = "mixed"
    detail_strength: float = 0.35

    def __post_init__(self):
        derive_subseed(self.world_seed, "sites")
        if self.family not in PROCEDURAL_FAMILIES:
            raise ValueError("unknown mountain family")
        if isinstance(self.detail_strength, bool) or not isinstance(self.detail_strength, (int, float)):
            raise ValueError("detail_strength must be a number")
        if not math.isfinite(self.detail_strength) or not (self.detail_strength == 0 or 1e-6 <= self.detail_strength <= 1):
            raise ValueError("detail_strength must be zero or in [1e-6, 1]")


def _noise(x, z, scale, seed, salt):
    return smooth_noise(x, z, scale, seed, salt)


def _base(x, z, config):
    """Warped multi-scale ridge field; physical wavelengths are in metres."""
    seed = derive_subseed(config.world_seed, "base-noise")
    wx = x + 2500.0 * _noise(x, z, 19000.0, seed, 1)
    wz = z + 2500.0 * _noise(x, z, 19000.0, seed, 2)
    broad = _noise(wx, wz, 16000.0, seed, 3)
    middle = _noise(wx, wz, 8000.0, seed, 4)
    small = _noise(wx, wz, 4000.0, seed, 5)
    # Product localizes the highest ground at irregular intersections rather
    # than extending a single fixed-direction ridge across the whole view.
    r1 = (1.0 - np.abs(0.78 * broad + 0.22 * middle)) ** 3
    r2 = (1.0 - np.abs(0.72 * middle + 0.28 * small)) ** 2
    return 250.0 + 2200.0 * r1 * (0.35 + 0.65 * r2) + 600.0 * middle + 180.0 * small


def _regional_delta(x, z, base, advanced, config):
    """Regionally recompose independent noise structures around Advanced base."""
    seed = derive_subseed(config.world_seed, "regional-noise")
    angle = 2.0 * np.pi * ((seed % 1000003) / 1000003.0)
    ca, sa = np.cos(angle), np.sin(angle)
    wx = x + 2200.0 * _noise(x, z, 16000.0, seed, 2)
    wz = z + 2200.0 * _noise(x, z, 16000.0, seed, 3)
    a = ca * wx + sa * wz
    b = -sa * wx + ca * wz
    broad = _noise(wx, wz, 11000.0, seed, 4)
    medium = _noise(wx, wz, 5500.0, seed, 5)
    fine = _noise(wx, wz, 2600.0, seed, 6)
    # Billowy coherent pluton-like volumes and rare sharp noise crease edges.
    block = _noise(wx, wz, 8500.0, seed, 7)
    granite_volume = np.clip(0.53 + 0.8 * block + 0.22 * broad, 0.0, 1.0)
    granite_volume = granite_volume * granite_volume * (3.0 - 2.0 * granite_volume)
    crease = np.maximum(0.0, 1.0 - 8.0 * np.abs(_noise(wx, wz, 9000.0, seed, 8)))
    granite_target = 350.0 + 2400.0 * granite_volume + 200.0 * broad - 250.0 * crease
    granite = 0.77 * (granite_target - advanced)
    # Smooth terraces act on structural height, not the fine Advanced result.
    # The monotone smoothstep has 500 m layer spacing and a 200 m transition.
    layer_mass = np.clip(0.45 + 0.8 * broad + 0.2 * medium, 0.0, 1.0)
    structural = 300.0 + 2350.0 * layer_mass + 110.0 * medium
    tilt = 0.018 * b + 220.0 * _noise(a * 0.55, b * 1.6, 18000.0, seed, 9)
    phase = (structural + tilt) / 500.0
    level = np.floor(phase)
    fraction = phase - level
    transition = np.clip((fraction - 0.3) / 0.4, 0.0, 1.0)
    transition = transition * transition * (3.0 - 2.0 * transition)
    layered_target = 500.0 * (level + transition) - tilt + 0.18 * (advanced - base)
    layered = 0.90 * (layered_target - advanced)
    # Nonlinear intersections of two differently oriented warped ridge noises.
    r1 = 1.0 - np.minimum(1.0, 2.0 * np.abs(_noise(a * 0.7, b * 1.4, 7500.0, seed, 10)))
    r2 = 1.0 - np.minimum(1.0, 2.0 * np.abs(_noise(a * 1.5, b * 0.7, 9800.0, seed, 11)))
    horn_target = 280.0 + 2850.0 * (r1 ** 1.5) * (0.35 + 0.65 * r2) + 250.0 * broad + 100.0 * fine
    glacial = 0.78 * (horn_target - advanced)
    if config.family != "mixed":
        return {"granite_dome": granite, "layered_massif": layered, "glacial_horn": glacial}[config.family]
    weights = np.stack([np.exp(6.0 * _noise(x, z, 45000.0, seed, k)) for k in (12, 13, 14)])
    return (weights[0] * granite + weights[1] * layered + weights[2] * glacial) / np.sum(weights, axis=0)


def _procedural_coordinates(x_m, z_m):
    try:
        x, z = np.broadcast_arrays(np.asarray(x_m, dtype=np.float64), np.asarray(z_m, dtype=np.float64))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("coordinates must be broadcastable numbers") from exc
    if x.size > MAX_SAMPLES or x.size == 0:
        raise ValueError("sample count outside permitted range")
    if not np.isfinite(x).all() or not np.isfinite(z).all() or np.any(np.abs(x) > MAX_COORDINATE_M) or np.any(np.abs(z) > MAX_COORDINATE_M):
        raise ValueError("coordinates must be finite and within the supported world extent")
    return x, z


def sample_procedural_stages(x_m, z_m, config=None):
    """Return world-coordinate intermediate elevations and regional noise delta."""
    config = MountainConfig() if config is None else config
    if not isinstance(config, MountainConfig):
        raise ValueError("config must be MountainConfig")
    x, z = _procedural_coordinates(x_m, z_m)
    base = _base(x, z, config)
    if config.detail_strength:

        slope_x = (_base(x + GRADIENT_STEP_M, z, config) - _base(x - GRADIENT_STEP_M, z, config)) / (2 * GRADIENT_STEP_M)
        slope_z = (_base(x, z + GRADIENT_STEP_M, config) - _base(x, z - GRADIENT_STEP_M, config)) / (2 * GRADIENT_STEP_M)
        around = (_base(x + 600.0, z, config) + _base(x - 600.0, z, config) + _base(x, z + 600.0, config) + _base(x, z - 600.0, config)) * 0.25
        target = np.clip((base - around) / 100.0, -1.0, 1.0)
        advanced = filter_height(x, z, base, slope_x, slope_z, target, world_seed=config.world_seed,
                                 config=AdvancedFilterConfig(amplitude_m=1000.0 * config.detail_strength))["height_m"]
    else:
        advanced = base.copy()
    regional = _regional_delta(x, z, base, advanced, config)
    return {"base_noise_m": base, "advanced_base_m": advanced,
            "regional_noise_delta_m": regional, "height_m": advanced + regional}


def sample_procedural_height(x_m, z_m, config=None):
    """Sample elevation metres as float64 at broadcast world coordinates."""
    return np.asarray(sample_procedural_stages(x_m, z_m, config)["height_m"], dtype=np.float64)


def rasterize_procedural(origin_m_xz, shape_zx, spacing_m, config=None):
    """Sample a [z, x] raster. Spacing never changes the underlying field."""

    config = MountainConfig() if config is None else config
    if not isinstance(config, MountainConfig):
        raise ValueError("config must be MountainConfig")
    try:
        origin = np.asarray(origin_m_xz, dtype=np.float64)
        shape = tuple(shape_zx)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid raster origin or shape") from exc
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("origin must contain finite x,z")
    if len(shape) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) or v <= 0 for v in shape):
        raise ValueError("shape must contain two positive integers")
    if shape[0] * shape[1] > MAX_SAMPLES:
        raise ValueError("sample count exceeds budget")
    if isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)) or not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("spacing_m must be finite positive")
    end = origin + np.array([shape[1] - 1, shape[0] - 1]) * spacing_m
    if np.any(np.abs(origin) > MAX_COORDINATE_M) or np.any(np.abs(end) > MAX_COORDINATE_M):
        raise ValueError("raster exceeds supported world extent")
    xs = origin[0] + np.arange(shape[1]) * spacing_m
    zs = origin[1] + np.arange(shape[0]) * spacing_m
    stages = sample_procedural_stages(xs[None, :], zs[:, None], config)
    height = stages["height_m"]
    return {**stages, "metadata": {
        "algorithm": PROCEDURAL_ALGORITHM, "status": "candidate", "world_seed": config.world_seed,
        "subseeds": {**{name: derive_subseed(config.world_seed, name) for name in ("base-noise", "regional-noise")},
                     "advanced-phacelle": int.from_bytes(hashlib.sha256(
                         f"advanced-terrain-filter-v1:{config.world_seed}:phacelle".encode("ascii")
                     ).digest()[:8], "little")},
        "seed_derivation": {"noise": SEED_DERIVATION,
                            "advanced-phacelle": "sha256(advanced-terrain-filter-v1:world_seed:phacelle), first 8 bytes little-endian"},
        "coordinates": "metres; X east, Z south; arrays [z, x]",
        "origin_m_xz": origin.tolist(), "shape_zx": [int(value) for value in shape], "spacing_m": float(spacing_m),
        "config": asdict(config), "advanced_filter": {"algorithm": ADVANCED_ALGORITHM_ID, **asdict(AdvancedFilterConfig(amplitude_m=1000.0 * config.detail_strength))},
        "dependency_bound": "fixed octaves of 4-corner value noise; fixed 30 m slope and 600 m relief offsets; fixed advanced filter kernel",
        "claims": "mechanism-inspired geometric candidate; not a simulated geological history",
        "limitations": "single-valued height field; no caves, overhangs, drainage or naturalness certification",
    }}



# ------------------------------------------------------------------------
# 原 terrain_pipeline/voronoi_mountains.py
# ------------------------------------------------------------------------

VORONOI_ALGORITHM = "voronoi-mountains-v2"


VORONOI_FAMILIES = ("cellular_massif", "ridge_network", "mixed")


@dataclass(frozen=True)
class VoronoiConfig:
    """Protection transition and threshold measure concavity in metres, not horizontal distance."""
    world_seed: int = WORLD_SEED
    family: str = "mixed"
    cell_size_m: float = 6000.0
    amplitude_m: float = 600.0
    warp_m: float = 600.0
    anisotropy: float = 1.3
    protection_radius_m: float = 600.0
    protection_threshold_m: float = 35.0
    protection_transition_m: float = 120.0
    detail_strength: float = 0.35

    def __post_init__(self):
        derive_subseed(self.world_seed, "voronoi-sites")
        if self.family not in VORONOI_FAMILIES:
            raise ValueError("unknown Voronoi family")
        for name, low, high in (("cell_size_m", 500, 100000), ("amplitude_m", 0, 3000),
                                ("warp_m", 0, 10000), ("anisotropy", 1, 3),
                                ("protection_radius_m", 30, 5000),
                                ("protection_threshold_m", 1, 1000),
                                ("protection_transition_m", 1, 2000), ("detail_strength", 0, 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} outside supported range")
        if 0 < self.detail_strength < 1e-6:
            raise ValueError("detail_strength must be zero or at least 1e-6")


def _smooth(value):
    value = np.clip(value, 0, 1)
    return value * value * (3 - 2 * value)


def _structure(x, z, config, seed, warp_seed):
    size = config.cell_size_m
    wx = x + config.warp_m * smooth_noise(x, z, size * 3, warp_seed, 1)
    wz = z + config.warp_m * smooth_noise(x, z, size * 3, warp_seed, 2)
    angle = 2 * np.pi * ((seed % 1000003) / 1000003)
    # Transform first, then search a regular lattice in transformed space.
    gx = (np.cos(angle) * wx + np.sin(angle) * wz) / size / config.anisotropy
    gz = (-np.sin(angle) * wx + np.cos(angle) * wz) / size
    ix, iz = np.floor(gx).astype(np.int64), np.floor(gz).astype(np.int64)
    first = np.full(x.shape, np.inf)
    second = np.full(x.shape, np.inf)
    attribute = np.zeros(x.shape)
    # Each cell owns one site in its central [1/4,3/4]^2. The query's
    # own cell and the cell across its nearest vertical edge each contain a
    # site at distance <= sqrt(1.75^2 + .75^2) < 2.25 cells. Any cell
    # outside this 5x5 neighborhood has its nearest possible site at least
    # 2.25 cells away. Therefore both closest sites are always included.
    for dz in range(-2, 3):
        for dx in range(-2, 3):
            cx, cz = ix + dx, iz + dz
            sx = cx + 0.5 + 0.25 * _hash(cx, cz, seed, 1)
            sz = cz + 0.5 + 0.25 * _hash(cx, cz, seed, 2)
            distance = np.hypot(gx - sx, gz - sz)
            closer = distance < first
            second = np.where(closer, first, np.minimum(second, distance))
            attribute = np.where(closer, _hash(cx, cz, seed, 3), attribute)
            first = np.minimum(first, distance)
    # Site attribute only modulates a term that vanishes at cell boundaries,
    # avoiding discontinuities when nearest-site identity changes.
    interior = _smooth((second - first) / 0.7)
    massif = 1.3 * np.exp(-2.2 * first * first) * (0.8 + 0.2 * attribute * interior) - 0.55
    ridge = 1.35 * np.exp(-5 * (second - first)) - 0.42
    if config.family == "cellular_massif":
        result = massif
    elif config.family == "ridge_network":
        result = ridge
    else:
        blend = _smooth(0.5 + 0.8 * smooth_noise(x, z, size * 7, warp_seed, 3))
        result = blend * massif + (1 - blend) * ridge
    return config.amplitude_m * result


def _sample_batch(x_m, z_m, config=None):
    """Return actual intermediate arrays and provenance for broadcast coordinates."""
    config = VoronoiConfig() if config is None else config
    if not isinstance(config, VoronoiConfig):
        raise ValueError("config must be VoronoiConfig")
    x, z = _procedural_coordinates(x_m, z_m)
    radius = config.protection_radius_m
    if np.any(np.abs(x) + radius > MAX_COORDINATE_M) or np.any(np.abs(z) + radius > MAX_COORDINATE_M):
        raise ValueError("protection neighborhood exceeds supported world extent")
    base_config = MountainConfig(world_seed=config.world_seed, detail_strength=config.detail_strength)
    def advanced(px, pz):
        return sample_procedural_stages(px, pz, base_config)["advanced_base_m"]
    elevation = advanced(x, z)
    neighbors = (advanced(x + radius, z) + advanced(x - radius, z)
                 + advanced(x, z + radius) + advanced(x, z - radius)) * 0.25
    trough_depth = neighbors - elevation
    mask = _smooth((trough_depth - config.protection_threshold_m + config.protection_transition_m)
                   / config.protection_transition_m)
    site_seed = derive_subseed(config.world_seed, "voronoi-sites")
    warp_seed = derive_subseed(config.world_seed, "voronoi-warp")
    delta = _structure(x, z, config, site_seed, warp_seed)
    return {"advanced_base_m": elevation, "structure_delta_m": delta,
            "unprotected_height_m": elevation + delta, "protection_mask": mask,
            "height_m": elevation + (1 - mask) * delta,
            "metadata": {"algorithm": VORONOI_ALGORITHM, "world_seed": config.world_seed,
                         "base_source": {"algorithm": PROCEDURAL_ALGORITHM, "stage": "advanced_base_m",
                                         "advanced_algorithm": ADVANCED_ALGORITHM_ID,
                                         "advanced_filter_config": asdict(AdvancedFilterConfig(amplitude_m=1000.0 * config.detail_strength)),
                                         "advanced_filter_applied": config.detail_strength != 0,
                                         "regional_noise": "computed by reused sampler but discarded"},
                         "config": asdict(config), "subseeds": {"voronoi-sites": site_seed, "voronoi-warp": warp_seed,
                         "base-noise": derive_subseed(config.world_seed, "base-noise"),
                         "regional-noise": derive_subseed(config.world_seed, "regional-noise"),
                         "advanced-phacelle": int.from_bytes(hashlib.sha256(
                             f"advanced-terrain-filter-v1:{config.world_seed}:phacelle".encode("ascii")
                         ).digest()[:8], "little")},
                         "seed_derivation": {"noise": SEED_DERIVATION,
                                             "advanced-phacelle": "sha256(advanced-terrain-filter-v1:world_seed:phacelle), first 8 bytes little-endian"},
                         "protection": "four-neighbor morphological trough; not a drainage network"}}


BATCH_SAMPLES = 16384


def sample_voronoi_stages(x_m, z_m, config=None):
    """Sample in bounded batches, including the protection neighborhood."""
    config = VoronoiConfig() if config is None else config
    if not isinstance(config, VoronoiConfig):
        raise ValueError("config must be VoronoiConfig")
    x, z = _procedural_coordinates(x_m, z_m)
    limit = MAX_COORDINATE_M - config.protection_radius_m
    if np.any(np.abs(x) > limit) or np.any(np.abs(z) > limit):
        raise ValueError("protection neighborhood exceeds supported world extent")
    shape = x.shape
    flat_x, flat_z = x.ravel(), z.ravel()
    keys = ("advanced_base_m", "structure_delta_m", "unprotected_height_m", "protection_mask", "height_m")
    arrays = {key: np.empty(x.size, dtype=np.float64) for key in keys}
    for start in range(0, x.size, BATCH_SAMPLES):
        end = min(start + BATCH_SAMPLES, x.size)
        batch = _sample_batch(flat_x[start:end], flat_z[start:end], config)
        for key in keys:
            arrays[key][start:end] = batch[key]
    result = {key: value.reshape(shape) for key, value in arrays.items()}
    result["metadata"] = batch["metadata"]
    result["metadata"]["valid_coordinate_limit_m"] = limit
    result["metadata"]["batch_samples"] = BATCH_SAMPLES
    return result


def rasterize_voronoi(origin_m_xz, shape_zx, spacing_m, config=None):
    """Sample a [z,x] world-coordinate raster at positive spacing in metres."""
    try:
        origin = np.asarray(origin_m_xz, dtype=float)
        shape = tuple(shape_zx)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid raster arguments") from exc
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("origin must contain finite x,z")
    if len(shape) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) or v <= 0 for v in shape) or shape[0] * shape[1] > MAX_SAMPLES:
        raise ValueError("invalid raster shape")
    if isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)) or not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("invalid spacing")
    x = origin[0] + np.arange(shape[1]) * spacing_m
    z = origin[1] + np.arange(shape[0]) * spacing_m
    result = sample_voronoi_stages(x[None, :], z[:, None], config)
    result["metadata"].update({"origin_m_xz": origin.tolist(), "shape_zx": [int(v) for v in shape], "spacing_m": float(spacing_m)})
    return result



# ------------------------------------------------------------------------
# 原 terrain_pipeline/ridge_breakup.py
# ------------------------------------------------------------------------

RIDGE_BREAKUP_ALGORITHM = "ridge-breakup-v1"


@dataclass(frozen=True)
class RidgeBreakupConfig:
    voronoi: object = field(default_factory=lambda: VoronoiConfig(family="ridge_network"))
    gaussian_sigma_m: float = 500.0
    gaussian_step_m: float = 300.0
    gaussian_truncate: float = 2.0
    warp_m: float = 700.0
    warp_scale_m: float = 3500.0
    gap_strength: float = 1.0
    gap_scale_m: float = 3000.0
    gap_start: float = 0.55
    gap_end: float = 0.75
    detail_amplitude_m: float = 35.0
    detail_scale_m: float = 1100.0

    def __post_init__(self):
        if not isinstance(self.voronoi, VoronoiConfig):
            raise ValueError("voronoi must be VoronoiConfig")
        for name, low, high in (("gaussian_sigma_m", 0, 3000), ("gaussian_step_m", 100, 3000),
                                ("gaussian_truncate", 1, 3), ("warp_m", 0, 3000),
                                ("warp_scale_m", 500, 100000), ("gap_strength", 0, 1),
                                ("gap_scale_m", 500, 100000), ("gap_start", 0, 1), ("gap_end", 0, 1),
                                ("detail_amplitude_m", 0, 200),
                                ("detail_scale_m", 200, 30000)):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not low <= v <= high:
                raise ValueError(f"invalid {name}")
        if self.gaussian_sigma_m and self.gaussian_sigma_m * self.gaussian_truncate / self.gaussian_step_m > 8:
            raise ValueError("Gaussian kernel radius exceeds eight grid steps")
        if self.gap_start >= self.gap_end:
            raise ValueError("gap_start must be below gap_end")


def _kernel(config):
    if config.gaussian_sigma_m == 0:
        return np.array([0]), np.array([1.0])
    radius = int(math.ceil(config.gaussian_truncate * config.gaussian_sigma_m / config.gaussian_step_m))
    offsets = np.arange(-radius, radius + 1)
    weights = np.exp(-0.5 * (offsets * config.gaussian_step_m / config.gaussian_sigma_m) ** 2)
    return offsets, weights / weights.sum()


def _gaussian(x, z, config, structure):
    """Evaluate fixed lattice convolution with no persistent cache or window padding."""
    if config.gaussian_sigma_m == 0:
        return structure(x, z)
    step = config.gaussian_step_m
    gx, gz = x / step, z / step
    ix, iz = np.floor(gx).astype(np.int64), np.floor(gz).astype(np.int64)
    fx, fz = gx - ix, gz - iz
    corners = np.stack([np.column_stack((ix, iz)), np.column_stack((ix + 1, iz)),
                        np.column_stack((ix, iz + 1)), np.column_stack((ix + 1, iz + 1))])
    nodes, inverse = np.unique(corners.reshape(-1, 2), axis=0, return_inverse=True)
    offsets, weights = _kernel(config)
    values = np.zeros(len(nodes))
    # Bound temporaries for arbitrary scattered requests, not just dense rasters.
    for start in range(0, len(nodes), 4096):
        end = min(start + 4096, len(nodes))
        batch = nodes[start:end]
        minimum = batch.min(axis=0) + offsets[0]
        maximum = batch.max(axis=0) + offsets[-1]
        width, height = (maximum - minimum + 1).tolist()
        # Dense world-grid halo only when bounded relative to the sparse work.
        # Sparse or widely separated points fall back to the original loop.
        dense = width * height <= min(300000, len(batch) * len(offsets) ** 2)
        if dense:
            raw_x = (minimum[0] + np.arange(width)) * step
            raw_z = (minimum[1] + np.arange(height)) * step
            xx, zz = np.broadcast_arrays(raw_x[None, :], raw_z[:, None])
            raw = structure(xx.ravel(), zz.ravel()).reshape(height, width)
            column = batch[:, 0] - minimum[0]
            row = batch[:, 1] - minimum[1]
        out = values[start:end]
        for j, wz in zip(offsets, weights):
            for i, wx in zip(offsets, weights):
                if dense:
                    samples = raw[row + j, column + i]
                else:
                    samples = structure((batch[:, 0] + i) * step, (batch[:, 1] + j) * step)
                out += (wx * wz) * samples
    a, b, c, d = values[inverse].reshape(4, -1)
    return (a * (1 - fx) + b * fx) * (1 - fz) + (c * (1 - fx) + d * fx) * fz


def sample_ridge_breakup_stages(x_m, z_m, config=None):
    config = RidgeBreakupConfig() if config is None else config
    if not isinstance(config, RidgeBreakupConfig):
        raise ValueError("config must be RidgeBreakupConfig")
    x, z = _procedural_coordinates(x_m, z_m)
    # Require full physical support inside the base source's documented extent.
    offsets, weights = _kernel(config)
    halo = config.warp_m + (max(abs(offsets)) + 1) * config.gaussian_step_m
    limit = MAX_COORDINATE_M - max(config.voronoi.protection_radius_m, halo)
    if np.any(np.abs(x) > limit) or np.any(np.abs(z) > limit):
        raise ValueError("sampling neighborhood exceeds supported extent")
    underlying = sample_voronoi_stages(x, z, config.voronoi)
    shape = x.shape
    xf, zf = x.ravel(), z.ravel()
    seed = derive_subseed(config.voronoi.world_seed, "voronoi-sites")
    warp_seed = derive_subseed(config.voronoi.world_seed, "voronoi-warp")
    breakup_seed = derive_subseed(config.voronoi.world_seed, "ridge-breakup")
    def structure(px, pz):
        return _structure(px, pz, config.voronoi, seed, warp_seed)
    wx = xf + config.warp_m * smooth_noise(xf, zf, config.warp_scale_m, breakup_seed, 1)
    wz = zf + config.warp_m * smooth_noise(xf, zf, config.warp_scale_m, breakup_seed, 2)
    combined = _gaussian(np.concatenate((xf, wx)), np.concatenate((zf, wz)), config, structure)
    gaussian, warped = np.split(combined, 2)
    # Low continuous modulation attenuates structures into local saddles.
    gap_noise = 0.5 + 0.5 * smooth_noise(xf, zf, config.gap_scale_m, breakup_seed, 3)
    gap = np.clip((gap_noise - config.gap_start) / (config.gap_end - config.gap_start), 0, 1)
    gap = gap * gap * (3 - 2 * gap)
    retention = 1 - config.gap_strength * gap
    cut = np.maximum(warped, 0) * (1 - retention)
    broken = warped - cut
    angle = 2 * np.pi * (breakup_seed % 1000003) / 1000003
    a = np.cos(angle) * xf + np.sin(angle) * zf
    b = -np.sin(angle) * xf + np.cos(angle) * zf
    detail = config.detail_amplitude_m * smooth_noise(a * 0.4, b * 1.8, config.detail_scale_m, breakup_seed, 4)
    final = broken + detail
    gaussian, warped, broken, final, gap, retention, cut = (
        v.reshape(shape) for v in (gaussian, warped, broken, final, gap, retention, cut))
    elevation, mask = underlying["advanced_base_m"], underlying["protection_mask"]
    result = {"advanced_base_m": elevation, "protection_mask": mask,
              "original_delta_m": underlying["structure_delta_m"], "gaussian_delta_m": gaussian,
              "warped_delta_m": warped, "breakup_delta_m": broken, "final_delta_m": final,
              "gap_field": gap, "ridge_retention": retention, "cut_delta_m": cut,
              "original_height_m": underlying["height_m"],
              "gaussian_height_m": elevation + (1 - mask) * gaussian,
              "breakup_height_m": elevation + (1 - mask) * broken,
              "height_m": elevation + (1 - mask) * final}
    result["metadata"] = {"algorithm": RIDGE_BREAKUP_ALGORITHM, "config": asdict(config),
                          "voronoi_source": underlying["metadata"],
                          "subseeds": {"ridge-breakup": breakup_seed},
                          "gaussian": {"grid_origin_m": [0, 0], "interpolation": "bilinear",
                                       "offsets": offsets.tolist(), "weights_1d": weights.tolist(),
                                       "radius_m": int(max(abs(offsets))) * config.gaussian_step_m,
                                       "semantics": "normalized finite separable sampled Gaussian; radius rounded up to grid steps"},
                          "valid_coordinate_limit_m": limit}
    return result


def rasterize_ridge_breakup(origin_m_xz, shape_zx, spacing_m, config=None):
    try:
        origin = np.asarray(origin_m_xz, dtype=float)
        shape = tuple(shape_zx)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid raster arguments") from exc
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("invalid origin")
    if len(shape) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) or v <= 0 for v in shape) or shape[0] * shape[1] > MAX_SAMPLES:
        raise ValueError("invalid shape")
    if isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)) or not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("invalid spacing")
    x = origin[0] + np.arange(shape[1]) * spacing_m
    z = origin[1] + np.arange(shape[0]) * spacing_m
    result = sample_ridge_breakup_stages(x[None, :], z[:, None], config)
    result["metadata"].update({"origin_m_xz": origin.tolist(), "shape_zx": [int(v) for v in shape], "spacing_m": float(spacing_m)})
    return result



# ------------------------------------------------------------------------
# 原 terrain_pipeline/world_mountain_belts.py
# ------------------------------------------------------------------------

SCHEMA = "world-mountain-belts-v1"


ALGORITHM_VERSION = "curved-world-belts-3"


FLOAT_FIELDS = ("raw_elevation_m", "base_elevation_m", "mountain_height_m",
                "basin_depth_m", "elevation_m", "continental_fraction", "crust_thickness_m")


MASK_FIELDS = ("ocean_connected", "inland_depression", "valid")


BASE_FIELDS = ("elevation_m", "continental_fraction", "crust_thickness_m",
               "ocean_connected", "plate_id")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _seed(world_seed, purpose):
    return int.from_bytes(hashlib.sha256(
        (str(world_seed) + ":world-mountain-belts:" + purpose).encode()).digest()[:8], "big")


def _integer(value, minimum):
    return isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)) and value >= minimum


@dataclass(frozen=True)
class WorldMountainConfig:
    spacing_m: float = 5000.0
    world_seed: int = WORLD_SEED
    flatten_base: bool = True
    amplitude_scale: float = 1.0
    thick_crust_threshold_m: float = 40000.0
    min_belt_length_m: float = 40000.0
    max_belts: int = 24
    max_cells: int = 1000000
    max_source_cells: int = 2000000
    max_segments: int = 4096

    def __post_init__(self):
        for name in ("spacing_m", "amplitude_scale", "thick_crust_threshold_m", "min_belt_length_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not np.isfinite(value) or value < 0:
                raise ValueError("invalid " + name)
        if self.spacing_m < 1000 or self.thick_crust_threshold_m <= 0 or self.min_belt_length_m <= 0:
            raise ValueError("spacing must be >=1000 m and physical thresholds positive")
        if not _integer(self.world_seed, 0) or not isinstance(self.flatten_base, bool):
            raise ValueError("invalid seed or base policy")
        for name in ("max_belts", "max_cells", "max_source_cells", "max_segments"):
            if not _integer(getattr(self, name), 1):
                raise ValueError("invalid " + name)


def _immutable(array):
    return np.frombuffer(array.tobytes(order="C"), dtype=array.dtype).reshape(array.shape)


def _summary(array):
    return {"shape": list(array.shape), "dtype": array.dtype.str,
            "sha256": _digest(array.tobytes(order="C"))}


def _belts_coordinates(x_m, z_m, grid):
    x, z = np.broadcast_arrays(np.asarray(x_m, dtype=float), np.asarray(z_m, dtype=float))
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("coordinates must be finite")
    ox, oz = grid["origin_x_m"], grid["origin_z_m"]
    width, height = grid["extent_m"]
    if np.any((x < ox) | (x >= ox + width) | (z < oz) | (z >= oz + height)):
        raise ValueError("query outside prepared finite domain")
    return x, z


def _sample_arrays(arrays, grid, x, z, categorical=()):
    """Clamp BOTH neighbors before indexing; never borrow opposite-edge data."""
    nz, nx = grid["shape"]
    gx = np.clip((x - grid["origin_x_m"]) / grid["spacing_m"] - .5, 0, nx - 1)
    gz = np.clip((z - grid["origin_z_m"]) / grid["spacing_m"] - .5, 0, nz - 1)
    ix, iz = np.floor(gx).astype(np.int64), np.floor(gz).astype(np.int64)
    fx, fz = gx - ix, gz - iz
    right, below = np.minimum(ix + 1, nx - 1), np.minimum(iz + 1, nz - 1)
    result = {}
    for name, array in arrays.items():
        if name in categorical:
            value = array[np.floor(gz + .5).astype(int), np.floor(gx + .5).astype(int)]
        else:
            value = ((1 - fz) * ((1 - fx) * array[iz, ix] + fx * array[iz, right])
                     + fz * ((1 - fx) * array[below, ix] + fx * array[below, right]))
        result[name] = np.array(value, copy=True)
    return result


def _base_grid(config):
    nz, nx = config["shape"]
    spacing = config["cell_size_m"]
    return {"shape": [nz, nx], "spacing_m": spacing,
            "origin_x_m": config["origin_x_m"], "origin_z_m": config["origin_z_m"],
            "extent_m": [nx * spacing, nz * spacing]}


def _candidate(points, weights, evidence, minimum_length, spacing):
    centre = np.average(points, axis=0, weights=weights)
    offset = points - centre
    eigenvalues, vectors = np.linalg.eigh(offset.T @ (offset * weights[:, None]))
    direction = vectors[:, -1]
    if direction[0] < 0 or (direction[0] == 0 and direction[1] < 0):
        direction = -direction
    along = offset @ direction
    span = float(np.ptp(along))
    aspect = float(np.sqrt(max(eigenvalues[-1], 1) / max(eigenvalues[0], 1)))
    record = {**evidence, "point_count": len(points), "span_m": span, "aspect": aspect}
    if span < minimum_length:
        return None, {**record, "reason": "too_short"}
    if evidence["kind"] == "thick_crust_morphology_prior" and aspect < 1.4:
        return None, {**record, "reason": "broad_thick_crust_retained_as_base"}
    # A component has already been split at ocean/gaps; PCA orders that component only.
    bins = min(20, max(3, int(span / (2 * spacing)) + 1))
    edges = np.linspace(float(along.min()) - .01, float(along.max()) + .01, bins + 1)
    vertices = []
    for low, high in zip(edges[:-1], edges[1:]):
        take = (along >= low) & (along < high)
        if np.any(take):
            vertices.append(np.average(points[take], axis=0, weights=weights[take]))
    vertices = np.asarray(vertices)
    vertices = gaussian_filter1d(vertices, .65, axis=0, mode="nearest")
    record["vertices_m"] = vertices.tolist()
    record["strength"] = float(np.average(weights))
    return record, None


def _extract_candidates(base, config):
    arrays = base.arrays
    source = base.manifest["config"]
    ids = arrays["final/plate_id"]
    fraction = arrays["final/continental_fraction"]
    thickness = arrays["final/crust_thickness_m"]
    ocean = arrays["final/ocean_connected"].astype(bool)
    velocity = arrays["final/velocities_m_per_step"]
    spacing = source["cell_size_m"]
    ox, oz = source["origin_x_m"], source["origin_z_m"]
    masks = {}
    counts = {"convergent_faces": 0, "divergent_faces": 0, "transform_faces": 0,
              "continental_convergent_faces": 0}
    for axis, component in ((1, 0), (0, 1)):
        left = (slice(None), slice(None, -1)) if axis == 1 else (slice(None, -1), slice(None))
        right = (slice(None), slice(1, None)) if axis == 1 else (slice(1, None), slice(None))
        a, b = ids[left], ids[right]
        boundary = a != b
        normal = velocity[b, component] - velocity[a, component]
        for name, selected in (("convergent_faces", normal < -1e-10),
                               ("divergent_faces", normal > 1e-10),
                               ("transform_faces", abs(normal) <= 1e-10)):
            counts[name] += int(np.count_nonzero(boundary & selected))
        continental = ((fraction[left] + fraction[right]) * .5 > .5) & (~ocean[left] | ~ocean[right])
        rows, cols = np.nonzero(boundary & (normal < -1e-10) & continental)
        counts["continental_convergent_faces"] += len(rows)
        for row, col in zip(rows, cols):
            pair = tuple(sorted((int(a[row, col]), int(b[row, col]))))
            mask = masks.setdefault(pair, np.zeros(ids.shape, dtype=bool))
            mask[row, col] = True
            mask[row + (axis == 0), col + (axis == 1)] = True
    candidates, rejected = [], []
    for pair, mask in sorted(masks.items()):
        # Eight-neighbor connects stair steps but does not dilate across spatial gaps.
        components, count = label(mask, np.ones((3, 3), dtype=int))
        for index in range(1, count + 1):
            rows, cols = np.nonzero(components == index)
            points = np.column_stack((ox + (cols + .5) * spacing, oz + (rows + .5) * spacing))
            candidate, refusal = _candidate(points, np.ones(len(points)),
                {"kind": "convergent_boundary", "plate_pair": list(pair),
                 "source_id": "convergence-%d-%d-%d" % (*pair, int(rows[0] * ids.shape[1] + cols[0]))},
                config.min_belt_length_m, spacing)
            (candidates if candidate else rejected).append(candidate or refusal)
    thick = (~ocean) & (fraction > .5) & (thickness > config.thick_crust_threshold_m)
    components, count = label(thick)
    counts["thick_crust_cells"] = int(thick.sum())
    counts["thick_crust_components"] = int(count)
    for index in range(1, count + 1):
        rows, cols = np.nonzero(components == index)
        points = np.column_stack((ox + (cols + .5) * spacing, oz + (rows + .5) * spacing))
        weights = np.maximum(1, thickness[rows, cols] / config.thick_crust_threshold_m)
        candidate, refusal = _candidate(points, weights,
            {"kind": "thick_crust_morphology_prior", "threshold_m": config.thick_crust_threshold_m,
             "source_id": "thick-%d" % int(rows[0] * ids.shape[1] + cols[0])},
            config.min_belt_length_m, spacing)
        (candidates if candidate else rejected).append(candidate or refusal)
    candidates.sort(key=lambda c: (-c["span_m"] * min(c["strength"], 2), c["source_id"]))
    rejected.extend({**c, "reason": "belt_budget"} for c in candidates[config.max_belts:])
    return candidates[:config.max_belts], rejected, counts


def _normals(points):
    tangent = np.gradient(points, axis=0)
    tangent /= np.maximum(np.linalg.norm(tangent, axis=1)[:, None], 1)
    return np.column_stack((-tangent[:, 1], tangent[:, 0]))


def _ridge_record(points, source_id, role, width, amplitude, rng, style):
    powers = {"folded_ranges": (1.25, 1.8), "block_plateau_margin": (3.2, 4.2),
              "worn_ranges": (2., 2.6)}
    return {"source_id": source_id, "role": role, "style": style,
            "vertices_m": points.tolist(), "width_m": float(width),
            "amplitude_m": float(amplitude), "peak_spacing_m": float(rng.uniform(45000, 85000)),
            "phase": float(rng.uniform(0, 2 * np.pi)), "cross_power": float(rng.uniform(*powers[style]))}


def _inventory(base, config):
    candidates, rejected, counts = _extract_candidates(base, config)
    ridges, basins, seeds = [], [], {}
    for index, candidate in enumerate(candidates):
        source_id = candidate["source_id"]
        seed = _seed(config.world_seed, source_id)
        seeds[source_id] = seed
        rng = np.random.default_rng(seed)
        points = np.asarray(candidate["vertices_m"])
        normal = _normals(points)
        style = ("folded_ranges", "block_plateau_margin", "worn_ranges")[index % 3]
        width = float(rng.uniform(14000, 22000))
        amplitude = float(rng.uniform(1500, 2600))
        if style == "block_plateau_margin":
            width *= 1.4
            amplitude *= 1.2
        elif style == "worn_ranges":
            width *= 1.3
            amplitude *= .55
        amplitude *= config.amplitude_scale
        t = np.linspace(0, 1, len(points))
        points = points + normal * (np.sin(t * 2 * np.pi + rng.uniform(0, 6)) * width * .25)[:, None]
        # The parent curve follows its actual connected candidate; no end extension.
        ridges.append(_ridge_record(points, source_id, "main", width, amplitude, rng, style))
        normal = _normals(points)
        parallel_sides = (-1,) if style == "block_plateau_margin" else (-1, 1)
        parallel_amplitude = .32 if style == "worn_ranges" else .68
        for side in parallel_sides:
            offset = width * float(rng.uniform(1.65, 2.05))
            parallel = points + side * offset * normal
            ridges.append(_ridge_record(parallel, source_id, "parallel", width * .58,
                                        amplitude * parallel_amplitude, rng, style))
            centre = points[len(points) // 2] + side * offset * .55 * normal[len(points) // 2]
            tangent = points[-1] - points[0]
            tangent /= max(np.linalg.norm(tangent), 1)
            basins.append({"source_id": source_id, "centre_m": centre.tolist(),
                           "axis": tangent.tolist(), "semi_length_m": max(25000., candidate["span_m"] * .19),
                           "semi_width_m": width * .5, "depth_m": amplitude * .22,
                           "kind": "declared_intermontane_lowland_not_lake"})
        for branch_index, position in enumerate((.28, .68)):
            anchor_index = int(position * (len(points) - 1))
            anchor = points[anchor_index]
            tangent = points[min(anchor_index + 1, len(points) - 1)] - points[max(0, anchor_index - 1)]
            tangent /= max(np.linalg.norm(tangent), 1)
            side = 1 if branch_index else -1
            branch_t = np.linspace(0, 1, 5)
            length = min(candidate["span_m"] * .30, width * 4.0)
            branch = (anchor + branch_t[:, None] * length * (.55 * tangent + side * normal[anchor_index])
                      + np.sin(branch_t * np.pi)[:, None] * normal[anchor_index] * width * .25)
            branch_amplitude = .25 if style == "worn_ranges" else .55
            ridges.append(_ridge_record(branch, source_id, "oblique_branch", width * .50,
                                        amplitude * branch_amplitude, rng, style))
    segments = sum(len(r["vertices_m"]) - 1 for r in ridges)
    if segments > config.max_segments:
        raise ValueError("curve segment budget exceeded before geometry evaluation")
    return {"candidates": candidates, "rejected_candidates": rejected, "boundary_counts": counts,
            "ridges": ridges, "basins": basins, "segments": segments,
            "purpose_seeds": seeds,
            "limitation": "raster face normals and thick-crust priors; no reconstructed tectonic history"}


def _ridge_height(ridge, points, x, z):
    """Maximum of continuous segment heights, including their along-axis attributes.

    Selecting only a nearest segment before evaluating peak phase is discontinuous
    on segment bisectors. Each clamped projection here is continuous on its own,
    and a finite maximum of continuous heights remains C0 (not necessarily C1).
    """
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    total = float(lengths.sum())
    height = np.zeros(x.shape)
    if total <= 0:
        return height
    cumulative = 0.
    width = ridge["width_m"]
    power = ridge["cross_power"]
    cutoff = np.exp(-3 ** power)
    for start, stop, length in zip(points[:-1], points[1:], lengths):
        if length <= 0:
            continue
        delta = stop - start
        t = np.clip(((x - start[0]) * delta[0] + (z - start[1]) * delta[1]) / length ** 2, 0, 1)
        distance = np.hypot(x - start[0] - t * delta[0], z - start[1] - t * delta[1])
        along = cumulative + t * length
        profile = np.maximum(0, (np.exp(-(distance / width) ** power) - cutoff) / (1 - cutoff))
        # Clip tiny sine roundoff at the final endpoint before the fractional power.
        end = np.maximum(0, np.sin(np.pi * np.clip(along / total, 0, 1))) ** .45
        peaks = (.62 + .28 * np.cos(along * 2 * np.pi / ridge["peak_spacing_m"] + ridge["phase"])
                 + .10 * np.cos(along * 2 * np.pi / (ridge["peak_spacing_m"] * .47) + ridge["phase"]))
        height = np.maximum(height, ridge["amplitude_m"] * profile * end * peaks)
        cumulative += float(length)
    return height


def _coast_gate(ocean, grid, x, z):
    """Continuous distance to the union of frozen ocean-cell rectangles.

    The gate saturates one source cell inland, so a fixed 3x3 neighborhood
    contains every rectangle able to affect it. Nearest-cell ocean categories
    may switch at a face; this geometric distance is zero on both sides there.
    No ocean beyond this finite source rectangle is invented or wrapped in.
    """
    spacing = grid["spacing_m"]
    nz, nx = grid["shape"]
    ix = np.floor((x - grid["origin_x_m"]) / spacing).astype(int)
    iz = np.floor((z - grid["origin_z_m"]) / spacing).astype(int)
    distance = np.full(x.shape, spacing)
    for row_offset in (-1, 0, 1):
        row = iz + row_offset
        for col_offset in (-1, 0, 1):
            col = ix + col_offset
            inside = (row >= 0) & (row < nz) & (col >= 0) & (col < nx)
            is_ocean = inside & ocean[np.clip(row, 0, nz - 1), np.clip(col, 0, nx - 1)]
            west = grid["origin_x_m"] + col * spacing
            north = grid["origin_z_m"] + row * spacing
            dx = np.maximum(0, np.maximum(west - x, x - west - spacing))
            dz = np.maximum(0, np.maximum(north - z, z - north - spacing))
            distance = np.minimum(distance, np.where(is_ocean, np.hypot(dx, dz), spacing))
    normalized = distance / spacing
    return normalized * normalized * (3 - 2 * normalized)


def _evaluate(base_arrays, grid, config, inventory, x, z):
    values = _sample_arrays(base_arrays, grid, x, z, ("ocean_connected", "plate_id"))
    raw = values.pop("elevation_m")
    ocean = values["ocean_connected"].astype(bool)
    inland_negative = (~ocean) & (raw < 0)
    fraction = values["continental_fraction"]
    coast_distance_gate = _coast_gate(base_arrays["ocean_connected"], grid, x, z)
    # Preserve coastline signs and all sea/negative basin levels. Compress only positive land.
    base_height = raw.copy()
    if config["flatten_base"]:
        compressed = 420 * (1 - np.exp(-np.maximum(raw, 0) / 1800)) + .025 * np.maximum(raw, 0)
        base_height = raw + np.where(raw > 0, coast_distance_gate * (compressed - raw), 0)
    mountain = np.zeros(x.shape)
    basin = np.zeros(x.shape)
    texture_seed = _seed(config["world_seed"], "relief_texture")
    # Noise wavelengths are fixed physical scales; 5 km sampling remains a coarse approximation.
    for ridge in inventory["ridges"]:
        points = np.asarray(ridge["vertices_m"])
        width = ridge["width_m"]
        reach = width * 3
        take = ((x >= points[:, 0].min() - reach) & (x <= points[:, 0].max() + reach)
                & (z >= points[:, 1].min() - reach) & (z <= points[:, 1].max() + reach))
        if not np.any(take):
            continue
        local_x, local_z = x[take], z[take]
        texture = noise_field(local_x, local_z, texture_seed, 71,
                              ((65000., 1.), (25000., .45), (15000., .2)))
        height = _ridge_height(ridge, points, local_x, local_z) * (1 + .18 * texture)
        # A max envelope does not turn crossings into spuriously doubled isolated peaks.
        mountain[take] = np.maximum(mountain[take], height)
    for depression in inventory["basins"]:
        cx, cz = depression["centre_m"]
        ux, uz = depression["axis"]
        dx, dz = x - cx, z - cz
        radial = (((dx * ux + dz * uz) / depression["semi_length_m"]) ** 2
                  + ((-dx * uz + dz * ux) / depression["semi_width_m"]) ** 2)
        depth = depression["depth_m"] * np.maximum(0, 1 - radial) ** 2
        basin = np.maximum(basin, depth)
    gate = np.clip((fraction - .45) / .4, 0, 1)
    gate = gate * gate * (3 - 2 * gate)
    # A continuous coast gate removes added relief near zero without relocating the coast.
    coast_gate = np.clip(np.maximum(raw, 0) / 500., 0, 1)
    coast_gate = coast_gate * coast_gate * (3 - 2 * coast_gate)
    gate *= coast_gate * coast_distance_gate
    mountain *= gate
    basin *= gate
    # Positive land stays positive; original inland negative depressions are preserved.
    basin = np.minimum(basin, np.maximum(base_height + mountain - 1, 0))
    elevation = base_height + mountain - basin
    values.update({"raw_elevation_m": raw, "base_elevation_m": base_height,
                   "mountain_height_m": mountain, "basin_depth_m": basin,
                   "elevation_m": elevation, "ocean_connected": ocean,
                   "inland_depression": inland_negative, "valid": np.ones(x.shape, dtype=bool)})
    return values


class FrozenWorldMountainBelts:
    """Immutable DEM, frozen inventory and small frozen background for geometry checks."""
    def __init__(self, manifest, arrays, base_arrays):
        payload = dict(manifest)
        identity = payload.pop("identity", None)
        if identity != _digest(_json(payload).encode()):
            raise ValueError("world mountain identity mismatch")
        if manifest["schema"] != SCHEMA or manifest["algorithm_version"] != ALGORITHM_VERSION:
            raise ValueError("unsupported world mountain schema or algorithm")
        WorldMountainConfig(**manifest["config"])
        required = set((*FLOAT_FIELDS, *MASK_FIELDS, "plate_id"))
        if set(arrays) != required or set(base_arrays) != set(BASE_FIELDS):
            raise ValueError("world mountain fields mismatch")
        for group, summaries, shape in ((arrays, manifest["arrays"], manifest["grid"]["shape"]),
                                        (base_arrays, manifest["base_arrays"], manifest["base_grid"]["shape"])):
            for name, array in group.items():
                if list(array.shape) != shape or not np.isfinite(array).all() or _summary(array) != summaries[name]:
                    raise ValueError("world mountain array integrity mismatch: " + name)
        if not np.all(arrays["valid"]) or np.any(arrays["mountain_height_m"] < 0) or np.any(arrays["basin_depth_m"] < 0):
            raise ValueError("invalid world mountain field values")
        if np.any(arrays["inland_depression"] & arrays["ocean_connected"]):
            raise ValueError("ocean and inland depression overlap")
        self._manifest_json = _json(manifest)
        self.arrays = MappingProxyType({k: _immutable(v) for k, v in arrays.items()})
        self._base_arrays = MappingProxyType({k: _immutable(v) for k, v in base_arrays.items()})

    @property
    def manifest(self):
        return json.loads(self._manifest_json)

    @property
    def identity(self):
        return self.manifest["identity"]

    def query(self, x_m, z_m):
        grid = self.manifest["grid"]
        x, z = _belts_coordinates(x_m, z_m, grid)
        return _sample_arrays(self.arrays, grid, x, z, (*MASK_FIELDS, "plate_id"))

    def evaluate_geometry(self, x_m, z_m):
        """Read frozen geometry directly; unlike query, recomputes procedural samples."""
        manifest = self.manifest
        x, z = _belts_coordinates(x_m, z_m, manifest["base_grid"])
        return _evaluate(self._base_arrays, manifest["base_grid"], manifest["config"],
                         manifest["source_inventory"], x, z)


def prepare_world_mountain_belts(base, config=WorldMountainConfig()):
    """Explicit bounded preparation. Never evolves, mutates or samples with wrap."""
    if not isinstance(base, FrozenTectonicProduct) or not isinstance(config, WorldMountainConfig):
        raise TypeError("expected a frozen tectonic product and WorldMountainConfig")
    source = base.manifest["config"]
    base_grid = _base_grid(source)
    if np.prod(source["shape"]) > config.max_source_cells:
        raise ValueError("source cell budget exceeded")
    width, height = base_grid["extent_m"]
    nx_float, nz_float = width / config.spacing_m, height / config.spacing_m
    if not np.isclose(nx_float, round(nx_float), atol=1e-9, rtol=0) or not np.isclose(nz_float, round(nz_float), atol=1e-9, rtol=0):
        raise ValueError("spacing must divide the complete source rectangle")
    nx, nz = int(round(nx_float)), int(round(nz_float))
    if nx < 2 or nz < 2 or nx * nz > config.max_cells:
        raise ValueError("output cell budget exceeded or grid too small")
    inventory = _inventory(base, config)
    grid = {**base_grid, "shape": [nz, nx], "spacing_m": config.spacing_m}
    x, z = np.meshgrid(grid["origin_x_m"] + (np.arange(nx) + .5) * config.spacing_m,
                       grid["origin_z_m"] + (np.arange(nz) + .5) * config.spacing_m)
    base_arrays = {name: base.arrays["final/" + name] for name in BASE_FIELDS}
    values = _evaluate(base_arrays, base_grid, asdict(config), inventory, x, z)
    arrays = {k: np.asarray(v, dtype=np.float32 if k in FLOAT_FIELDS else
                            (np.int64 if k == "plate_id" else bool)) for k, v in values.items()}
    manifest = {"schema": SCHEMA, "algorithm_version": ALGORITHM_VERSION,
                "world_seed": config.world_seed, "base_world_seed": source["world_seed"],
                "base_source": {"schema": base.manifest["schema"], "identity": base.identity,
                                "world_seed": source["world_seed"], "state": "final"},
                "source_type": "procedural_world_coarse_geomorphology_non_td",
                "config": asdict(config), "grid": grid, "base_grid": base_grid,
                "coordinates": {"axes": "X east, Z south", "array_order": "z,x", "length_unit": "m",
                                "height_datum_m": 0, "grid_origin": "lower corner; centres at origin+(index+.5)*spacing",
                                "boundary": "finite half-open rectangle; clamped edge interpolation"},
                "source_inventory": inventory,
                "seed_derivation": "SHA256(str(world_seed)+':world-mountain-belts:'+purpose), first 8 bytes big-endian",
                "purpose_seeds": {**inventory["purpose_seeds"], "relief_texture": _seed(config.world_seed, "relief_texture")},
                "base_transform": "positive land 420*(1-exp(-raw/1800))+.025*raw; mix by smooth distance from frozen ocean-cell rectangles over one source spacing; ocean/negative unchanged" if config.flatten_base else "disabled",
                "limitations": ["finite whole-source prepare; no unbounded-world macro coordination",
                                "procedural ranges and lowlands, no erosion or river/lake topology",
                                "query interpolates a DEM; evaluate_geometry directly samples fixed geometry"],
                "arrays": {k: _summary(v) for k, v in arrays.items()},
                "base_arrays": {k: _summary(v) for k, v in base_arrays.items()}}
    manifest["identity"] = _digest(_json(manifest).encode())
    return FrozenWorldMountainBelts(manifest, arrays, base_arrays)


def save_belt_product(product, path):
    """Atomically publish without overwriting; validate a cold read first."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".world-mountains-", suffix=".npz", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            fields = {**product.arrays, **{"base/" + k: v for k, v in product._base_arrays.items()}}
            np.savez_compressed(stream, manifest_json=np.array(_json(product.manifest)), **fields)
            stream.flush()
            os.fsync(stream.fileno())
        loaded = load_belt_product(temporary, expected_identity=product.identity)
        os.link(temporary, path)
        return loaded
    finally:
        Path(temporary).unlink(missing_ok=True)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest field")
        result[key] = value
    return result


def load_belt_product(path, *, expected_identity=None):
    with np.load(path, allow_pickle=False) as archive:
        if len(archive.files) != len(set(archive.files)):
            raise ValueError("duplicate product fields")
        manifest = json.loads(str(archive["manifest_json"]), object_pairs_hook=_unique_object)
        arrays = {k: archive[k] for k in archive.files if k != "manifest_json" and not k.startswith("base/")}
        base_arrays = {k[5:]: archive[k] for k in archive.files if k.startswith("base/")}
    product = FrozenWorldMountainBelts(manifest, arrays, base_arrays)
    if expected_identity is not None and expected_identity != product.identity:
        raise ValueError("unexpected world mountain product identity")
    return product



# ------------------------------------------------------------------------
# 原 terrain_pipeline/procedural_mountain_processes.py
# ------------------------------------------------------------------------

def prepare_process_evidence(origin=(0.0, 0.0), world_seed=20260903):
    """Sample 65x65 at 30 m; model an explicit 9-cell subwindow, never mutate source."""
    cfg = MountainConfig(world_seed=world_seed)
    bed = rasterize_procedural(origin, (65, 65), 30.0, cfg)['height_m'].copy()
    sha = hashlib.sha256(bed.tobytes()).hexdigest()
    terrain = TerrainGrid(bed, np.ones(bed.shape, bool), *origin, 30., 30., 'generated_terrain',
                          'independent_procedural_mountains', sha, generation_seed=world_seed)
    kind = np.full(bed.shape, 'interior', dtype='<U24')
    kind[[0, -1], :] = 'unknown_boundary'
    kind[:, [0, -1]] = 'unknown_boundary'
    boundary = BoundaryGrid(kind, np.zeros(bed.shape, bool), 'unknown perimeter', hashlib.sha256(kind.tobytes()).hexdigest())
    graph = route_diagnostic(terrain, boundary)
    discharge = accumulate_local_discharge(graph, np.full(bed.shape, 0.001))
    floor = bed - 2.0
    after = conservative_diffusion_step(bed, np.ones(bed.shape), np.zeros(bed.shape, dtype=int), floor, .01, 30.)
    delta = after - bed
    x = np.arange(9, dtype=float) * 30.0
    line = bed[32, 28:37].copy()
    glacier = advance_glacier(thickness_start_m=np.full(9, 20.), bed_m=line,
        accumulation_mm=np.full((1, 9), 10.), ablation_mm=np.full((1, 9), 5.),
        time_edges_s=[0., 86400.], x_m=x, width_m=30., bedrock_erodible_m3=np.full(9, 900.))
    gd = glacier['arrays']['bed_delta_m'][-1]
    arrays = {'source_height_m': bed, 'routed_q_m3_s': discharge['routed_q_m3_s'],
              'terminal_q_m3_s': discharge['terminal_q_m3_s'], 'diffused_height_m': after,
              'diffusion_delta_m': delta, 'glacier_source_x_m': origin[0] + np.arange(28, 37) * 30.,
              'glacier_source_z_m': np.full(9, origin[1] + 32 * 30.), 'glacier_before_m': line,
              'glacier_final_bed_delta_m': gd, 'glacier_after_m': line + gd,
              **{'glacier_' + k: v for k, v in glacier['arrays'].items()}}
    metadata = {'world_seed': world_seed, 'source_kind': 'generated_terrain', 'source_sha256': sha,
                'origin_m_xz': list(origin), 'spacing_m': 30., 'shape_zx': [65, 65],
                'routing': {'boundary': 'unknown perimeter', 'local_discharge_m3_s_per_cell': .001,
                            **{k: v for k, v in discharge.items() if not isinstance(v, np.ndarray)}},
                'diffusion': {'operator': 'conservative_diffusion_step', 'coefficient': .01,
                              'sediment_flux': 1., 'initial_mobile_layer_m': 2., 'row_zero_closed': True,
                              'volume_delta_m3': float(delta.sum() * 900.), 'minimum_floor_margin_m': float(np.min(after - floor))},
                'glacier': {'scope': '9 cells, 240 m along-source; finite standalone diagnostic, no coupled valley claim',
                            'initial_thickness_m': 20., 'bedrock_stock_m3_per_cell': 900.,
                            'accumulation_mm_water_equivalent': 10., 'ablation_mm_water_equivalent': 5.,
                            'time_edges_s': [0., 86400.], 'model_metadata': glacier['metadata'], 'ledger': glacier['ledger']}}
    return arrays, metadata

CATEGORY = "A"
