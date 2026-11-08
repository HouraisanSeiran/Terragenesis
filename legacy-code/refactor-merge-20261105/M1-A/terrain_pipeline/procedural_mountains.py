"""Experimental, bounded, mechanism-inspired mountain height field in metres.

This single-valued geometric construction combines a port of Rune's Advanced
filter with regional processed noise. It is not a geological simulation,
real-site reconstruction, or drainage network.
Absolute X east and Z south coordinates are sampled at the same physical field
regardless of raster resolution; every noise octave visits four lattice corners.
"""

from dataclasses import asdict, dataclass
import hashlib
import math

import numpy as np

from diffusion.geographic_noise import smooth_noise

from terrain_pipeline.common_infra import WORLD_SEED, SEED_DERIVATION, derive_subseed

ALGORITHM = "procedural-mountains-v3"
MAX_SAMPLES = 1_048_576
MAX_COORDINATE_M = 1.0e9
GRADIENT_STEP_M = 30.0
FAMILIES = ("mixed", "granite_dome", "layered_massif", "glacial_horn")


@dataclass(frozen=True)
class MountainConfig:
    """World seed, morphology family and detail strength 0 or [1e-6, 1]."""

    world_seed: int = WORLD_SEED
    family: str = "mixed"
    detail_strength: float = 0.35

    def __post_init__(self):
        derive_subseed(self.world_seed, "sites")
        if self.family not in FAMILIES:
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


def _coordinates(x_m, z_m):
    try:
        x, z = np.broadcast_arrays(np.asarray(x_m, dtype=np.float64), np.asarray(z_m, dtype=np.float64))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("coordinates must be broadcastable numbers") from exc
    if x.size > MAX_SAMPLES or x.size == 0:
        raise ValueError("sample count outside permitted range")
    if not np.isfinite(x).all() or not np.isfinite(z).all() or np.any(np.abs(x) > MAX_COORDINATE_M) or np.any(np.abs(z) > MAX_COORDINATE_M):
        raise ValueError("coordinates must be finite and within the supported world extent")
    return x, z


def sample_stages(x_m, z_m, config=None):
    """Return world-coordinate intermediate elevations and regional noise delta."""
    config = MountainConfig() if config is None else config
    if not isinstance(config, MountainConfig):
        raise ValueError("config must be MountainConfig")
    x, z = _coordinates(x_m, z_m)
    base = _base(x, z, config)
    if config.detail_strength:
        from terrain_pipeline.advanced_terrain_filter import AdvancedFilterConfig, filter_height

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


def sample_height(x_m, z_m, config=None):
    """Sample elevation metres as float64 at broadcast world coordinates."""
    return np.asarray(sample_stages(x_m, z_m, config)["height_m"], dtype=np.float64)


def rasterize(origin_m_xz, shape_zx, spacing_m, config=None):
    """Sample a [z, x] raster. Spacing never changes the underlying field."""
    from terrain_pipeline.advanced_terrain_filter import ALGORITHM_ID, AdvancedFilterConfig

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
    stages = sample_stages(xs[None, :], zs[:, None], config)
    height = stages["height_m"]
    return {**stages, "metadata": {
        "algorithm": ALGORITHM, "status": "candidate", "world_seed": config.world_seed,
        "subseeds": {**{name: derive_subseed(config.world_seed, name) for name in ("base-noise", "regional-noise")},
                     "advanced-phacelle": int.from_bytes(hashlib.sha256(
                         f"advanced-terrain-filter-v1:{config.world_seed}:phacelle".encode("ascii")
                     ).digest()[:8], "little")},
        "seed_derivation": {"noise": SEED_DERIVATION,
                            "advanced-phacelle": "sha256(advanced-terrain-filter-v1:world_seed:phacelle), first 8 bytes little-endian"},
        "coordinates": "metres; X east, Z south; arrays [z, x]",
        "origin_m_xz": origin.tolist(), "shape_zx": [int(value) for value in shape], "spacing_m": float(spacing_m),
        "config": asdict(config), "advanced_filter": {"algorithm": ALGORITHM_ID, **asdict(AdvancedFilterConfig(amplitude_m=1000.0 * config.detail_strength))},
        "dependency_bound": "fixed octaves of 4-corner value noise; fixed 30 m slope and 600 m relief offsets; fixed advanced filter kernel",
        "claims": "mechanism-inspired geometric candidate; not a simulated geological history",
        "limitations": "single-valued height field; no caves, overhangs, drainage or naturalness certification",
    }}
