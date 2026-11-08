"""Local smooth cellular mountain uplift and slope-faded appearance carving.

All coordinates and heights are metres; slopes are metres per metre.  The
600 m halo covers both the fixed 30 m derivative and curvature neighborhoods.
This experimental source is independent of the default world pipeline.
"""
from dataclasses import dataclass
import math
import numbers

import numpy as np

from diffusion.geographic_noise import _hash, smooth_noise
from terrain_pipeline import advanced_terrain_filter, product_mountains
from terrain_pipeline.common_infra import WORLD_SEED, derive_subseed

ALGORITHM_ID = "local-volume-mountains-v1"
MAX_COORDINATE_M = product_mountains.MAX_COORDINATE_M
MAX_SAMPLES = product_mountains.MAX_SAMPLES
HALO_M = 600.0


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
    product_config = product_mountains.ProductMountainConfig(world_seed=c.world_seed, advanced_enabled=False)
    product_seeds = tuple(derive_subseed(c.world_seed, purpose) for purpose in
                          ("product-ridge", "product-warp", "product-voronoi-sites"))
    site_seed = derive_subseed(c.world_seed, "local-volume-sites")
    selection_seed = derive_subseed(c.world_seed, "local-volume-selection")
    advanced_config = advanced_terrain_filter.AdvancedFilterConfig(amplitude_m=150, wavelength_m=1800, octaves=3)
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
            h0 = product_mountains._fields(xx, zz, product_config, product_seeds)[2]
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
            raw = advanced_terrain_filter.filter_height(bx, bz, macro, sx, sz, target, world_seed=c.world_seed, config=advanced_config)["delta_m"]
        else:
            raw = np.zeros_like(macro)
        final_delta = fade * np.where(raw < 0, raw * c.depth_gain, raw)
        for key, value in zip(keys, (h0, v, w, p, volume_delta, macro, sx, sz, target, fade, raw, final_delta, macro + final_delta)):
            arrays[key][start:end] = value
    return {key: value.reshape(x.shape) for key, value in arrays.items()}

