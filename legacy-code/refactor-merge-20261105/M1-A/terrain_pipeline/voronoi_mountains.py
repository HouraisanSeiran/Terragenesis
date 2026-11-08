"""Continuous Voronoi mountain experiment over the procedural Advanced base.

Coordinates and elevations are metres. Protection estimates morphological troughs,
not a drainage network. Sampling depends only on absolute world coordinates.
"""
from dataclasses import asdict, dataclass
import hashlib
import math

import numpy as np

from diffusion.geographic_noise import _hash, smooth_noise
from terrain_pipeline import procedural_mountains as base
from terrain_pipeline.advanced_terrain_filter import ALGORITHM_ID as ADVANCED_ALGORITHM, AdvancedFilterConfig
from terrain_pipeline.common_infra import WORLD_SEED, SEED_DERIVATION, derive_subseed

ALGORITHM = "voronoi-mountains-v2"
FAMILIES = ("cellular_massif", "ridge_network", "mixed")


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
        if self.family not in FAMILIES:
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
    x, z = base._coordinates(x_m, z_m)
    radius = config.protection_radius_m
    if np.any(np.abs(x) + radius > base.MAX_COORDINATE_M) or np.any(np.abs(z) + radius > base.MAX_COORDINATE_M):
        raise ValueError("protection neighborhood exceeds supported world extent")
    base_config = base.MountainConfig(world_seed=config.world_seed, detail_strength=config.detail_strength)
    def advanced(px, pz):
        return base.sample_stages(px, pz, base_config)["advanced_base_m"]
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
            "metadata": {"algorithm": ALGORITHM, "world_seed": config.world_seed,
                         "base_source": {"algorithm": base.ALGORITHM, "stage": "advanced_base_m",
                                         "advanced_algorithm": ADVANCED_ALGORITHM,
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


def sample_stages(x_m, z_m, config=None):
    """Sample in bounded batches, including the protection neighborhood."""
    config = VoronoiConfig() if config is None else config
    if not isinstance(config, VoronoiConfig):
        raise ValueError("config must be VoronoiConfig")
    x, z = base._coordinates(x_m, z_m)
    limit = base.MAX_COORDINATE_M - config.protection_radius_m
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


def rasterize(origin_m_xz, shape_zx, spacing_m, config=None):
    """Sample a [z,x] world-coordinate raster at positive spacing in metres."""
    try:
        origin = np.asarray(origin_m_xz, dtype=float)
        shape = tuple(shape_zx)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid raster arguments") from exc
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("origin must contain finite x,z")
    if len(shape) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) or v <= 0 for v in shape) or shape[0] * shape[1] > base.MAX_SAMPLES:
        raise ValueError("invalid raster shape")
    if isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)) or not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("invalid spacing")
    x = origin[0] + np.arange(shape[1]) * spacing_m
    z = origin[1] + np.arange(shape[0]) * spacing_m
    result = sample_stages(x[None, :], z[:, None], config)
    result["metadata"].update({"origin_m_xz": origin.tolist(), "shape_zx": [int(v) for v in shape], "spacing_m": float(spacing_m)})
    return result
