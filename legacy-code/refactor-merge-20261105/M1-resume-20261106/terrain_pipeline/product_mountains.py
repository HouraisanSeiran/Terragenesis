"""Continuous product mountain fields, in world metres.

Sites lie in the central half of each cell. Sites outside the 3x3
neighborhood are at least 1.25 cells away and contribute zero: each
smooth compact kernel vanishes at that radius. Their bounded union
is continuously differentiable across site and lattice boundaries.
The Advanced stage is an appearance filter, not a water/sediment model.
"""
from dataclasses import dataclass
import math
import numbers

import numpy as np

from diffusion.geographic_noise import _hash, smooth_noise
from terrain_pipeline import advanced_terrain_filter
from terrain_pipeline.common_infra import WORLD_SEED, derive_subseed

ALGORITHM_ID = "product-mountains-v2-smooth-mass"
MAX_COORDINATE_M = 1_000_000_000.0
HALO_M = 600.0
MAX_SAMPLES = 1_048_576


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
    advanced_config = advanced_terrain_filter.AdvancedFilterConfig(amplitude_m=c.advanced_amplitude_m, wavelength_m=c.advanced_wavelength_m, octaves=3)
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
            filtered = advanced_terrain_filter.filter_height(bx, bz, macro, sx, sz, target, world_seed=c.world_seed, config=advanced_config)
            final, delta = filtered["height_m"], filtered["delta_m"]
        else:
            final, delta = macro, np.zeros_like(macro)
        for key, value in zip(keys, (ridge, volume, macro, final, delta, sx, sz, target)):
            arrays[key][start:end] = value
    return {key: value.reshape(x.shape) for key, value in arrays.items()}
