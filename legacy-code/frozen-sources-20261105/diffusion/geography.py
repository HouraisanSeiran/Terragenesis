"""Seeded geographic conditioning for the unchanged five-channel diffusion model.

Coordinates are the upstream conditioning grid, not Minecraft blocks. The field is
sampled from absolute coordinates so tile order and boundaries cannot change it.
"""
from __future__ import annotations

import numpy as np
from .geographic_noise import field

GEOGRAPHY_VERSION = "geographic_v1"


def _geography(x, z, seed):
    # Tectonic scale determines coast and mountain mass; shorter scales add drainage.
    continent = field(x, z, seed, 101, ((64, 1), (24, .42), (8, .12)))
    mountain = field(x, z, seed, 211, ((18, 1), (7, .42), (2, .12)))
    detail = field(x, z, seed, 307, ((4, 1), (1, .35)))
    land = continent + .12 * mountain + .025 * detail
    shore = land + .02
    # Every contribution reaches zero at the shore, including short-scale relief.
    elevation = (np.maximum(0, shore) * 3300 + np.minimum(0, shore) * 2200
                 + np.minimum(1, np.maximum(0, shore) * 5)
                 * (np.maximum(0, mountain - .12) ** 2 * 1300 + detail * 95))
    elevation = np.clip(elevation, -1100, 4300)

    # Z acts as latitude; noise displaces isotherms without tying climate to a map file.
    latitude = 22 * np.sin(z / 96)
    maritime = np.exp(-np.abs(land + .02) * 7)
    temperature = (20 - latitude + field(x, z, seed, 401, ((30, 1), (9, .25))) * 8
                   - .0065 * np.maximum(elevation, 0) + maritime * 1.5)
    temperature = np.clip(temperature, -35, 38)
    # BIO4 is temperature standard deviation in centi-degrees in model units.
    temperature_std = np.clip(7 + 7 * (1 - maritime) + 6 * np.abs(np.sin(z / 96)), 4, 25) * 100

    moisture = field(x, z, seed, 503, ((42, 1), (12, .35)))
    # Prevailing westerly wind: western slope gains rain; eastern lee is drier.
    west = field(x - 3, z, seed, 211, ((18, 1), (7, .42), (2, .12)))
    east = field(x + 3, z, seed, 211, ((18, 1), (7, .42), (2, .12)))
    windward = np.clip((mountain - west) * 800, 0, 350)
    lee = np.clip((west - mountain) * 450 + (mountain - east) * 120, 0, 270)
    precipitation = np.clip(1050 + moisture * 900 + maritime * 500 + windward - lee
                            - np.maximum(elevation - 1800, 0) * .08, 100, 3200)
    # BIO15 is percentage coefficient of variation, not a fraction.
    precipitation_cv = np.clip(.28 + .26 * (1 - maritime)
                               + field(x, z, seed, 607, ((24, 1), (5, .25))) * .12,
                               .15, .85) * 100
    return np.stack((elevation, temperature, temperature_std,
                     precipitation, precipitation_cv), axis=0).astype(np.float32)


def make_geographic_map_factory(frequency_mult=None, seed=None, drop_water_pct=0.0):
    """Drop-in WorldPipeline factory with fixed v1 scales and no external raster reads."""
    if seed is None:
        raise ValueError("Geographic conditioning requires an explicit seed")
    if frequency_mult is not None and list(frequency_mult) not in ([1.0] * 5, [1.5, 3, 3, 3, 3]):
        raise ValueError("geographic_v1 uses fixed spatial scales; frequency_mult is unsupported")
    if drop_water_pct not in (0.0, 0.5):
        raise ValueError("geographic_v1 derives sea area from the seed; drop_water_pct is unsupported")
    seed = int(seed) & 0xFFFFFFFFFFFFFFFF

    def sample_raw(i1, j1, i2, j2):
        if i2 < i1 or j2 < j1:
            raise ValueError("Invalid geographic window")
        x = np.arange(i1, i2, dtype=np.float64)[None, :]
        z = np.arange(j1, j2, dtype=np.float64)[:, None]
        xx, zz = np.broadcast_arrays(x, z)
        return _geography(xx, zz, seed)

    def finalize(raw):
        raw = np.asarray(raw, dtype=np.float32)
        if raw.ndim != 3 or raw.shape[0] != 5 or not np.isfinite(raw).all():
            raise ValueError("Expected finite geographic conditioning [5,H,W]")
        return raw.copy()

    def sample_full(i1, j1, i2, j2):
        import torch
        result = finalize(sample_raw(i1, j1, i2, j2))
        result[0] = np.sign(result[0]) * np.sqrt(np.abs(result[0]))
        return torch.from_numpy(result)

    sample_full.sample_raw = sample_raw
    sample_full.finalize = finalize
    return sample_full
