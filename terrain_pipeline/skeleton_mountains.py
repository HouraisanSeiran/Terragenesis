"""World-anchored curved ridge ribbons and variable asymmetric sections.

Coordinates/heights are metres, slopes metres/metre. Each independent source
has three primary ribbons and three attached secondary ribbons (two levels).
The lateral distance is measured in a curve's nominal frame, not by nearest
Euclidean segment. This avoids nearest-segment switching and tessellation.
There is no global diffusion, drainage solve, persistent cache or input DEM.
Advanced is an appearance filter, not a water/sediment erosion simulation.
"""
from collections import OrderedDict
from dataclasses import dataclass
import math
import numbers

import numpy as np

from diffusion.geographic_noise import _hash, smooth_noise
from terrain_pipeline import mountain_forms as advanced_terrain_filter
from terrain_pipeline import mountain_forms as product_mountains
from terrain_pipeline.common_infra import WORLD_SEED, derive_subseed

ALGORITHM_ID = "skeleton-mountains-v2-ribbons-on-relief"
MAX_COORDINATE_M = 1_000_000_000.0
MAX_SAMPLES = 1_048_576
HALO_M = 600.0
SOURCE_SUPPORT_CELLS = 0.66
CACHE_CAPACITY = 128  # Per sample invocation, discarded on return.
PURPOSES = ("skeleton-sites", "skeleton-curves", "skeleton-profiles", "skeleton-detail")
# Left/right half widths, transverse and longitudinal powers, shoulder width.
# Powers exceed one: both sides have zero derivative on their shared axis.
PROFILES = {
    "granite": (0.135, 0.052, 2.6, 2.2, 1.25),
    "alpine": (0.065, 0.045, 1.35, 1.25, 1.10),
    "asymmetric": (0.155, 0.040, 1.8, 1.65, 1.20),
}


@dataclass(frozen=True)
class SkeletonMountainConfig:
    world_seed: int = WORLD_SEED
    profile: str = "mixed"
    cell_size_m: float = 24000.0
    base_m: float = 200.0
    base_relief_m: float = 600.0
    detail_amplitude_m: float = 45.0
    depth_gain: float = 2.4
    advanced_enabled: bool = True
    batch_size: int = 4096

    def __post_init__(self):
        derive_subseed(self.world_seed, PURPOSES[0])
        if not isinstance(self.profile, str) or self.profile not in (*PROFILES, "mixed"):
            raise ValueError("invalid profile")
        for name, low, high in (("cell_size_m", 8000, 100000),
                                ("base_m", -1000, 1000),
                                ("base_relief_m", 0, 1200),
                                ("detail_amplitude_m", 0, 300),
                                ("depth_gain", 1, 10)):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"invalid {name}")
        if not isinstance(self.advanced_enabled, bool):
            raise ValueError("advanced_enabled must be bool")
        if isinstance(self.batch_size, (bool, np.bool_)) or not isinstance(self.batch_size, numbers.Integral) or not 1 <= self.batch_size <= 65536:
            raise ValueError("invalid batch_size")


def _smoothstep(value, low, high):
    t = np.clip((value - low) / (high - low), 0, 1)
    return t * t * (3 - 2 * t)


def _random(cell_x, cell_z, seed, lane):
    return float(_hash(np.asarray(cell_x, dtype=np.int64), np.asarray(cell_z, dtype=np.int64), seed, lane))


def _curve_position(curve, t):
    """Exact parametric centreline; t is in [0, 1]."""
    u = np.asarray(t) * curve["length_m"]
    v = curve["bend_m"] * np.sin(np.pi * np.asarray(t)) ** 2
    co, si = math.cos(curve["angle_rad"]), math.sin(curve["angle_rad"])
    return curve["start_x_m"] + co * u - si * v, curve["start_z_m"] + si * u + co * v


def _along(t, power):
    return np.maximum(1 - np.clip(t, 0, 1) ** power, 0) ** 2


def describe_skeleton(cell_x, cell_z, config=None):
    """Return reproducible source geometry for inspection, never edited input.

    Geometry is identical for all profile choices. Nominal attachment height
    agrees on the parent/child axes; smooth terrain blending can lower it.
    """
    c = SkeletonMountainConfig() if config is None else config
    if not isinstance(c, SkeletonMountainConfig):
        raise ValueError("config must be SkeletonMountainConfig")
    for value in (cell_x, cell_z):
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral) or abs(value) > math.ceil(MAX_COORDINATE_M / c.cell_size_m) + 2:
            raise ValueError("invalid source cell")
    site_seed, curve_seed, profile_seed = (derive_subseed(c.world_seed, p) for p in PURPOSES[:3])
    rnd = lambda lane: _random(cell_x, cell_z, curve_seed, lane)
    center_x = (cell_x + .5 + .1 * _random(cell_x, cell_z, site_seed, 1)) * c.cell_size_m
    center_z = (cell_z + .5 + .1 * _random(cell_x, cell_z, site_seed, 2)) * c.cell_size_m
    profile = c.profile
    if profile == "mixed":
        lane = (_random(cell_x, cell_z, profile_seed, 1) + 1) * .5
        profile = tuple(PROFILES)[min(2, int(lane * 3))]
    rotation = np.pi * rnd(1)
    curves = []
    for arm in range(3):
        lane = 10 + arm * 10
        primary = {"id": f"primary-{arm}", "level": 1, "parent_id": None,
                   "start_x_m": center_x, "start_z_m": center_z,
                   "angle_rad": float(rotation + arm * 2 * np.pi / 3 + .25 * rnd(lane)),
                   "length_m": c.cell_size_m * (.35 + .05 * rnd(lane + 1)),
                   "bend_m": c.cell_size_m * .04 * rnd(lane + 2),
                   "attach_t": 0., "width_factor": 1.}
        curves.append(primary)
        attach = .38 + .06 * rnd(lane + 3)
        bx, bz = _curve_position(primary, attach)
        dv_du = primary["bend_m"] * np.pi / primary["length_m"] * math.sin(2 * np.pi * attach)
        side = -1 if rnd(lane + 4) < 0 else 1
        curves.append({"id": f"secondary-{arm}", "level": 2, "parent_id": primary["id"],
                       "start_x_m": float(bx), "start_z_m": float(bz),
                       "angle_rad": primary["angle_rad"] + math.atan(dv_du) + side * (.8 + .15 * rnd(lane + 5)),
                       "length_m": c.cell_size_m * (.19 + .04 * rnd(lane + 6)),
                       "bend_m": c.cell_size_m * .03 * rnd(lane + 7),
                       "attach_t": attach, "width_factor": .55})
    return {"cell_x": int(cell_x), "cell_z": int(cell_z), "profile": profile,
            "peak_x_m": center_x, "peak_z_m": center_z,
            "peak_uplift_m": 4000. + 700. * _random(cell_x, cell_z, site_seed, 3),
            "support_radius_m": SOURCE_SUPPORT_CELLS * c.cell_size_m,
            "curves": curves}


def _ribbon(x, z, curve, profile, cell_size):
    left, right, transverse_power, along_power, shoulder = PROFILES[profile]
    co, si = math.cos(curve["angle_rad"]), math.sin(curve["angle_rad"])
    dx, dz = x - curve["start_x_m"], z - curve["start_z_m"]
    u, v = co * dx + si * dz, -si * dx + co * dz
    t = np.clip(u / curve["length_m"], 0, 1)
    lateral = v - curve["bend_m"] * np.sin(np.pi * t) ** 2
    # Wide shoulders taper towards the terminal; squared envelope is C1 there.
    width_scale = (1 - .55 * t) * (1 + (shoulder - 1) * np.sin(np.pi * t) ** 2)
    width = np.where(lateral >= 0, left, right) * cell_size * curve["width_factor"] * width_scale
    ratio = np.abs(lateral) / width
    section = np.maximum(1 - ratio ** transverse_power, 0) ** 2
    back_cap = np.maximum(1 - (np.maximum(-u, 0) / (cell_size * .05)) ** 2, 0) ** 2
    nominal_height = 1.0
    if curve["level"] == 2:
        nominal_height = float(_along(curve["attach_t"], along_power))
    return nominal_height * _along(t, along_power) * back_cap * section


def _source_uplift(x, z, source, cell_size):
    # Contraharmonic soft union sum(u^9)/sum(u^8): zero-preserving, <=max(u),
    # idempotent for equal fields; unlike a summed p-norm it cannot inflate peaks.
    # It is not monotone in every operand: a weak overlapping field can lower it.
    weights = np.zeros_like(x)
    weighted = np.zeros_like(x)
    for curve in source["curves"]:
        value = _ribbon(x, z, curve, source["profile"], cell_size)
        weight = value ** 8
        weights += weight
        weighted += weight * value
    # A low broad pedestal supplies foothills without defining the main summit.
    radius = np.hypot(x - source["peak_x_m"], z - source["peak_z_m"])
    pedestal = .32 * np.maximum(1 - (radius / (.46 * cell_size)) ** 2, 0) ** 2
    weight = pedestal ** 8
    weights += weight
    weighted += weight * pedestal
    union = np.divide(weighted, weights, out=np.zeros_like(x), where=weights > 0)
    return source["peak_uplift_m"] * union


def _macro_fields(x, z, c, cache, detail_seed):
    uplift = np.zeros_like(x)
    cells = np.column_stack((np.floor(x / c.cell_size_m).astype(np.int64), np.floor(z / c.cell_size_m).astype(np.int64)))
    unique, inverse = np.unique(cells, axis=0, return_inverse=True)
    for index, (cell_x, cell_z) in enumerate(unique):
        selected = np.flatnonzero(inverse == index)
        xx, zz = x[selected], z[selected]
        denominator, numerator = np.zeros_like(xx), np.zeros_like(xx)
        for dz in range(-1, 2):
            for dx in range(-1, 2):
                key = (int(cell_x + dx), int(cell_z + dz))
                if key not in cache:
                    cache[key] = describe_skeleton(*key, c)
                    if len(cache) > CACHE_CAPACITY:
                        cache.popitem(last=False)
                source = cache[key]
                cache.move_to_end(key)
                active = np.flatnonzero(np.hypot(xx - source["peak_x_m"], zz - source["peak_z_m"]) <= source["support_radius_m"])
                if active.size:
                    value = _source_uplift(xx[active], zz[active], source, c.cell_size_m) / 4700.
                    weight = value ** 8
                    denominator[active] += weight
                    numerator[active] += weight * value
        uplift[selected] = 4700. * np.divide(numerator, denominator, out=np.zeros_like(xx), where=denominator > 0)
    if c.detail_amplitude_m > 0:
        noise = .65 * smooth_noise(x, z, 850., detail_seed, 1) + .35 * smooth_noise(x, z, 250., detail_seed, 2)
        detail = c.detail_amplitude_m * noise * uplift / 4700.
    else:
        detail = np.zeros_like(x)
    if c.base_relief_m:
        base_config = product_mountains.ProductMountainConfig(world_seed=c.world_seed,
                          base_m=c.base_m, amplitude_m=c.base_relief_m, advanced_enabled=False)
        base_seeds = tuple(derive_subseed(c.world_seed, p) for p in
                           ("product-ridge", "product-warp", "product-voronoi-sites"))
        base = product_mountains._fields(x, z, base_config, base_seeds)[2]
    else:
        base = np.full_like(x, c.base_m)
    skeleton = base + uplift
    return base, skeleton, detail, skeleton + detail


def sample_skeleton_mountains(x_m, z_m, config=None):
    """Sample fixed geometry at broadcast world coordinates, without grid input.

    Each macro point uses at most 3x3 sources, six exact curved ribbons per
    source, two hierarchy levels, plus a compact pedestal. Source support is
    at most 0.66 cells (see task algorithm.md). A source beyond the 3x3 cells
    is >=1.4 cells away, hence absent. Derivative/target halo is fixed 600 m.
    The per-invocation LRU stores at most 128 descriptors; output memory O(N),
    temporary work O(batch_size). Common points are independent of spacing.
    """
    c = SkeletonMountainConfig() if config is None else config
    if not isinstance(c, SkeletonMountainConfig):
        raise ValueError("config must be SkeletonMountainConfig")
    try:
        x, z = np.broadcast_arrays(np.asarray(x_m, dtype=np.float64), np.asarray(z_m, dtype=np.float64))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("coordinates must be broadcastable real numbers") from exc
    if x.size == 0 or x.size > MAX_SAMPLES or not np.all(np.isfinite(x)) or not np.all(np.isfinite(z)):
        raise ValueError("invalid sample count or nonfinite coordinates")
    if np.any(np.abs(x) > MAX_COORDINATE_M - HALO_M) or np.any(np.abs(z) > MAX_COORDINATE_M - HALO_M):
        raise ValueError("neighborhood exceeds coordinate domain")
    keys = ("base_height_m", "skeleton_height_m", "detail_delta_m", "macro_height_m",
            "slope_x", "slope_z", "fade_target", "slope_fade", "raw_advanced_delta_m", "final_delta_m", "height_m")
    result = {key: np.empty(x.size, dtype=np.float64) for key in keys}
    cache = OrderedDict()
    detail_seed = derive_subseed(c.world_seed, "skeleton-detail")
    advanced_config = advanced_terrain_filter.AdvancedFilterConfig(amplitude_m=150., wavelength_m=1800., octaves=3)
    xf, zf = x.ravel(), z.ravel()
    offsets = ((0, 0), (30, 0), (-30, 0), (0, 30), (0, -30), (600, 0), (-600, 0), (0, 600), (0, -600))
    for start in range(0, x.size, c.batch_size):
        end = min(start + c.batch_size, x.size)
        bx, bz = xf[start:end], zf[start:end]
        # Evaluate all derivative points together; same point always has the same
        # ordered 3x3 accumulation, even across batched or sparse requests.
        nx = np.concatenate([bx + dx for dx, _ in offsets])
        nz = np.concatenate([bz + dz for _, dz in offsets])
        bases, skeletons, details, macros = _macro_fields(nx, nz, c, cache, detail_seed)
        count = end - start
        skeleton, detail = skeletons[:count], details[:count]
        macro = macros.reshape(9, count)
        sx, sz = (macro[1] - macro[2]) / 60., (macro[3] - macro[4]) / 60.
        neighbor = (macro[5] + macro[6] + macro[7] + macro[8]) * .25
        target = np.clip((macro[0] - neighbor) / 120., -1, 1)
        fade = _smoothstep(np.hypot(sx, sz), .02, .08) * _smoothstep(skeleton - bases[:count], 0, 1000.)
        if c.advanced_enabled:
            raw = advanced_terrain_filter.filter_height(bx, bz, macro[0], sx, sz, target, world_seed=c.world_seed, config=advanced_config)["delta_m"]
        else:
            raw = np.zeros_like(bx)
        final = fade * np.where(raw < 0, raw * c.depth_gain, raw)
        values = (bases[:count], skeleton, detail, macro[0], sx, sz, target, fade, raw, final, macro[0] + final)
        for key, value in zip(keys, values):
            result[key][start:end] = value
    return {key: value.reshape(x.shape) for key, value in result.items()}
