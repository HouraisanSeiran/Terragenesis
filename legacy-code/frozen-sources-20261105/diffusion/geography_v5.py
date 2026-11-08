"""Coordinate-continuous soft-knee base conditioning with separate relief."""

from __future__ import annotations

import math
import numpy as np

from .geographic_noise import field
from .geography_v2 import (CONTINENT_SCALES, MOUNTAIN_SCALES, DETAIL_SCALES,
                           RIDGE_SCALES, GAP_SCALES)


GEOGRAPHY_VERSION = "geographic_v5"
BASE_FACTOR = 0.18
RELIEF_FACTOR = 0.18
OCEAN_DEPTH_M = 40.0


def compress_positive_base(base_m, knee_m, headroom_m):
    if (any(type(v) not in (int, float) or not math.isfinite(v)
            for v in (knee_m, headroom_m)) or
            not 0 < knee_m <= 3600 or not 0 < headroom_m <= 3600):
        raise ValueError("Invalid geographic_v5 base compression parameters")
    base = np.asarray(base_m, dtype=np.float64)
    if not np.isfinite(base).all() or np.any(base < 0):
        raise ValueError("base metres must be finite and nonnegative")
    excess = np.maximum(base - knee_m, 0)
    return np.minimum(base, knee_m) + headroom_m * -np.expm1(-excess / headroom_m)


def _components(x, z, seed, knee_m, headroom_m):
    continent = field(x, z, seed, 101, CONTINENT_SCALES)
    mountain = field(x, z, seed, 211, MOUNTAIN_SCALES)
    detail = field(x, z, seed, 307, DETAIL_SCALES)
    ridge = field(x, z, seed, 709, RIDGE_SCALES)
    interruption = field(x, z, seed, 811, GAP_SCALES)
    land = continent + .10 * mountain + .02 * detail
    shore = land + .025
    ridge_envelope = np.maximum(0, ridge - .04) ** 2
    gaps = np.clip((interruption + .12) * 2.2, 0, 1)
    relief = np.minimum(1, np.maximum(0, shore) * 5) * (
        ridge_envelope * gaps * 2400
        + np.maximum(0, mountain - .08) ** 2 * 1050 + detail * 90)
    base = np.maximum(0, shore) * 3600 * BASE_FACTOR
    compressed_base = compress_positive_base(base, knee_m, headroom_m)
    scaled_relief = relief * RELIEF_FACTOR
    ocean = -OCEAN_DEPTH_M * np.tanh(np.maximum(0, -shore) * 8)
    elevation = compressed_base + scaled_relief + ocean
    return land, mountain, elevation, base, compressed_base, scaled_relief, ocean


def _geography(x, z, seed, knee_m, headroom_m):
    land, mountain, elevation, _, _, _, _ = _components(x, z, seed, knee_m, headroom_m)
    latitude = 22 * np.sin(z / 96)
    maritime = np.exp(-np.abs(land + .025) * 7)
    temperature = (20 - latitude + field(x, z, seed, 401, ((30, 1), (9, .25))) * 8
                   - .0065 * np.maximum(elevation, 0) + maritime * 1.5)
    temperature = np.clip(temperature, -35, 38)
    temperature_std = np.clip(7 + 7 * (1 - maritime) + 6 * np.abs(np.sin(z / 96)), 4, 25) * 100
    moisture = field(x, z, seed, 503, ((42, 1), (12, .35)))
    west = field(x - 3, z, seed, 211, MOUNTAIN_SCALES)
    east = field(x + 3, z, seed, 211, MOUNTAIN_SCALES)
    windward = np.clip((mountain - west) * 800, 0, 350)
    lee = np.clip((west - mountain) * 450 + (mountain - east) * 120, 0, 270)
    precipitation = np.clip(1050 + moisture * 900 + maritime * 500 + windward - lee
                            - np.maximum(elevation - 1800, 0) * .08, 100, 3200)
    precipitation_cv = np.clip(.28 + .26 * (1 - maritime)
                               + field(x, z, seed, 607, ((24, 1), (5, .25))) * .12,
                               .15, .85) * 100
    return np.stack((elevation, temperature, temperature_std,
                     precipitation, precipitation_cv), axis=0).astype(np.float32)


def make_geographic_map_factory(frequency_mult=None, seed=None, drop_water_pct=0.0,
                                base_knee_m=120.0, base_headroom_m=80.0):
    if seed is None:
        raise ValueError("Geographic conditioning requires an explicit seed")
    if frequency_mult is not None and list(frequency_mult) not in ([1.0] * 5, [1.5, 3, 3, 3, 3]):
        raise ValueError("geographic_v5 uses fixed spatial scales")
    if drop_water_pct not in (0.0, 0.5):
        raise ValueError("geographic_v5 derives sea area from the seed")
    if (any(type(v) not in (int, float) or not math.isfinite(v)
            for v in (base_knee_m, base_headroom_m)) or
            not 0 < base_knee_m <= 3600 or not 0 < base_headroom_m <= 3600):
        raise ValueError("Invalid geographic_v5 base compression parameters")
    seed = int(seed) & 0xFFFFFFFFFFFFFFFF

    def coordinates(i1, j1, i2, j2):
        if i2 < i1 or j2 < j1:
            raise ValueError("Invalid geographic window")
        x = np.arange(i1, i2, dtype=np.float64)[None, :]
        z = np.arange(j1, j2, dtype=np.float64)[:, None]
        return np.broadcast_arrays(x, z)

    def sample_raw(i1, j1, i2, j2):
        xx, zz = coordinates(i1, j1, i2, j2)
        return _geography(xx, zz, seed, base_knee_m, base_headroom_m)

    def sample_components(i1, j1, i2, j2):
        xx, zz = coordinates(i1, j1, i2, j2)
        _, _, elevation, base, compressed, relief, ocean = _components(
            xx, zz, seed, base_knee_m, base_headroom_m)
        return {"base_m": base, "compressed_base_m": compressed,
                "relief_m": relief, "ocean_m": ocean, "condition_elevation_m": elevation}

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
    sample_full.sample_components = sample_components
    sample_full.finalize = finalize
    return sample_full
