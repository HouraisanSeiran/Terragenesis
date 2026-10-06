"""Coordinate-continuous physical conditioning, not model-generated terrain."""
import numpy as np

from .geographic_noise import field
from .physical_config import PhysicalGenerationConfig


def sample_physical(x_m, z_m, seed, config=None):
    config = PhysicalGenerationConfig() if config is None else config
    if not isinstance(config, PhysicalGenerationConfig):
        raise ValueError("PhysicalGenerationConfig required")
    if type(seed) is not int:
        raise ValueError("Explicit integer seed required")
    seed = seed & 0xFFFFFFFFFFFFFFFF
    east = np.asarray(x_m, dtype=np.float64)
    south = np.asarray(z_m, dtype=np.float64)
    shape = np.broadcast_shapes(east.shape, south.shape)
    if np.prod(shape, dtype=object) > 1048576:
        raise ValueError("Physical conditioning sample exceeds 1048576 cells")
    east, south = np.broadcast_arrays(east, south)
    if not np.isfinite(east).all() or not np.isfinite(south).all():
        raise ValueError("Finite metre coordinates required")
    if max(np.max(np.abs(east), initial=0), np.max(np.abs(south), initial=0)) > 1e15:
        raise ValueError("Coordinates exceed supported metre domain")
    east = east / config.geographic_scale_m
    south = south / config.geographic_scale_m
    continent = field(east, south, seed, 101, ((32, 1), (12, .42), (4, .12)))
    mountain_scales = ((6, 1), (2, .42), (1, .12))
    mountain = field(east, south, seed, 211, mountain_scales)
    detail = field(east, south, seed, 307, ((2, 1), (1, .35)))
    ridge = field(east, south, seed, 709, ((5, 1), (2, .35)))
    interruption = field(east, south, seed, 811, ((4, 1), (1, .3)))
    land = continent + .10 * mountain + .02 * detail
    shore = land + .025
    relief = np.minimum(1, np.maximum(0, shore) * 5) * (
        np.maximum(0, ridge - .04) ** 2 * np.clip((interruption + .12) * 2.2, 0, 1)
        * config.ridge_relief_m
        + np.maximum(0, mountain - .08) ** 2 * config.massif_relief_m
        + detail * config.detail_relief_m)
    elevation_m = (np.maximum(0, shore) * config.continental_uplift_m
                   + np.minimum(0, shore) * config.ocean_depth_m + relief)
    maritime = np.exp(-np.abs(shore) * 7)
    latitude = 22 * np.sin(south / 96)
    temperature_c = np.clip(20 - latitude
        + field(east, south, seed, 401, ((30, 1), (9, .25))) * 8
        - .0065 * np.maximum(elevation_m, 0) + maritime * 1.5, -35, 38)
    temperature_std = np.clip(7 + 7 * (1 - maritime)
        + 6 * np.abs(np.sin(south / 96)), 4, 25) * 100
    moisture = field(east, south, seed, 503, ((42, 1), (12, .35)))
    west = field(east - 3, south, seed, 211, mountain_scales)
    eastward = field(east + 3, south, seed, 211, mountain_scales)
    windward = np.clip((mountain - west) * 800, 0, 350)
    lee = np.clip((west - mountain) * 450 + (mountain - eastward) * 120, 0, 270)
    precipitation_mm = np.clip(1050 + moisture * 900 + maritime * 500 + windward - lee
        - np.maximum(elevation_m - 1800, 0) * .08, 100, 3200)
    precipitation_cv = np.clip(.28 + .26 * (1 - maritime)
        + field(east, south, seed, 607, ((24, 1), (5, .25))) * .12, .15, .85) * 100
    return np.stack((elevation_m, temperature_c, temperature_std,
                     precipitation_mm, precipitation_cv), axis=0).astype(np.float32)


def make_physical_map_factory(seed, config=None):
    config = PhysicalGenerationConfig() if config is None else config
    if not isinstance(config, PhysicalGenerationConfig):
        raise ValueError("PhysicalGenerationConfig required")
    if type(seed) is not int:
        raise ValueError("Explicit integer seed required")

    def sample_raw(x1, z1, x2, z2):
        if any(type(value) is not int for value in (x1, z1, x2, z2)) or x2 < x1 or z2 < z1:
            raise ValueError("Integer half-open conditioning window required")
        if ((x2 - x1) * (z2 - z1) > 1048576
                or max(x2 - x1, z2 - z1) > 1048576):
            raise ValueError("Physical conditioning window exceeds resource budget")
        if max(abs(value) for value in (x1, z1, x2, z2)) * config.conditioning_spacing_m > 1e15:
            raise ValueError("Window exceeds supported metre domain")
        east = np.arange(x1, x2, dtype=np.float64)[None, :] * config.conditioning_spacing_m
        south = np.arange(z1, z2, dtype=np.float64)[:, None] * config.conditioning_spacing_m
        return sample_physical(east, south, seed, config)

    def finalize(raw):
        values = np.asarray(raw, dtype=np.float32)
        if values.ndim != 3 or values.shape[0] != 5 or not np.isfinite(values).all():
            raise ValueError("Expected finite physical conditioning [5,H,W]")
        return values.copy()

    def sample_full(x1, z1, x2, z2):
        import torch

        values = finalize(sample_raw(x1, z1, x2, z2))
        values[0] = np.sign(values[0]) * np.sqrt(np.abs(values[0]))
        return torch.from_numpy(values)

    sample_full.sample_raw = sample_raw
    sample_full.finalize = finalize
    return sample_full
