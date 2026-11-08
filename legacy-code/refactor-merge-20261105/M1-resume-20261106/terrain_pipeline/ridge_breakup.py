"""World-anchored finite Gaussian and noise breakup for Voronoi structures.

The Gaussian is a normalized sampled finite kernel on a world-anchored grid,
followed by bilinear interpolation, not an infinite continuous convolution.
Only the structure moves: Advanced base and its protection mask stay fixed.
"""
from dataclasses import asdict, dataclass, field
import math

import numpy as np

from diffusion.geographic_noise import smooth_noise
from terrain_pipeline import procedural_mountains as base
from terrain_pipeline import voronoi_mountains as voronoi
from terrain_pipeline.common_infra import derive_subseed

ALGORITHM = "ridge-breakup-v1"


@dataclass(frozen=True)
class RidgeBreakupConfig:
    voronoi: object = field(default_factory=lambda: voronoi.VoronoiConfig(family="ridge_network"))
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
        if not isinstance(self.voronoi, voronoi.VoronoiConfig):
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


def sample_stages(x_m, z_m, config=None):
    config = RidgeBreakupConfig() if config is None else config
    if not isinstance(config, RidgeBreakupConfig):
        raise ValueError("config must be RidgeBreakupConfig")
    x, z = base._coordinates(x_m, z_m)
    # Require full physical support inside the base source's documented extent.
    offsets, weights = _kernel(config)
    halo = config.warp_m + (max(abs(offsets)) + 1) * config.gaussian_step_m
    limit = base.MAX_COORDINATE_M - max(config.voronoi.protection_radius_m, halo)
    if np.any(np.abs(x) > limit) or np.any(np.abs(z) > limit):
        raise ValueError("sampling neighborhood exceeds supported extent")
    underlying = voronoi.sample_stages(x, z, config.voronoi)
    shape = x.shape
    xf, zf = x.ravel(), z.ravel()
    seed = derive_subseed(config.voronoi.world_seed, "voronoi-sites")
    warp_seed = derive_subseed(config.voronoi.world_seed, "voronoi-warp")
    breakup_seed = derive_subseed(config.voronoi.world_seed, "ridge-breakup")
    def structure(px, pz):
        return voronoi._structure(px, pz, config.voronoi, seed, warp_seed)
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
    result["metadata"] = {"algorithm": ALGORITHM, "config": asdict(config),
                          "voronoi_source": underlying["metadata"],
                          "subseeds": {"ridge-breakup": breakup_seed},
                          "gaussian": {"grid_origin_m": [0, 0], "interpolation": "bilinear",
                                       "offsets": offsets.tolist(), "weights_1d": weights.tolist(),
                                       "radius_m": int(max(abs(offsets))) * config.gaussian_step_m,
                                       "semantics": "normalized finite separable sampled Gaussian; radius rounded up to grid steps"},
                          "valid_coordinate_limit_m": limit}
    return result


def rasterize(origin_m_xz, shape_zx, spacing_m, config=None):
    try:
        origin = np.asarray(origin_m_xz, dtype=float)
        shape = tuple(shape_zx)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid raster arguments") from exc
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("invalid origin")
    if len(shape) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) or v <= 0 for v in shape) or shape[0] * shape[1] > base.MAX_SAMPLES:
        raise ValueError("invalid shape")
    if isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)) or not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("invalid spacing")
    x = origin[0] + np.arange(shape[1]) * spacing_m
    z = origin[1] + np.arange(shape[0]) * spacing_m
    result = sample_stages(x[None, :], z[:, None], config)
    result["metadata"].update({"origin_m_xz": origin.tolist(), "shape_zx": [int(v) for v in shape], "spacing_m": float(spacing_m)})
    return result
