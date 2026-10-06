"""Physical-metre regional landform processing."""

from dataclasses import dataclass
import math

import numpy as np

from .artifacts import ArtifactIdentity, TerrainArtifact


@dataclass(frozen=True)
class RegionRecipe:
    trend_sigma_m: float = 8.0
    trend_radius_m: float = 24.0
    local_sigma_m: float = 2.0
    local_radius_m: float = 6.0
    coast_sigma_m: float = 3.0
    coast_radius_m: float = 9.0
    high_low_m: float = 220.0
    high_high_m: float = 290.0
    relief_low_m: float = 9.0
    relief_high_m: float = 28.0
    slope_low: float = 0.3
    slope_high: float = 0.9
    prominence_low_m: float = 10.0
    prominence_high_m: float = 24.0
    peak_protect_low_m: float = 8.0
    peak_protect_high_m: float = 26.0
    plain_strength: float = 0.90
    hill_strength: float = 0.18
    plateau_strength: float = 0.13

    def __post_init__(self) -> None:
        from dataclasses import asdict
        values = asdict(self)
        strengths = {"plain_strength", "hill_strength", "plateau_strength"}
        if any(type(value) not in (float, int) or not math.isfinite(value) or
               (not 0 <= value <= 1 if name in strengths else value <= 0)
               for name, value in values.items()):
            raise ValueError("recipe scales must be positive and strengths in [0,1]")
        for low, high in ((self.high_low_m, self.high_high_m),
                          (self.relief_low_m, self.relief_high_m),
                          (self.slope_low, self.slope_high),
                          (self.prominence_low_m, self.prominence_high_m),
                          (self.peak_protect_low_m, self.peak_protect_high_m)):
            if low >= high:
                raise ValueError("recipe thresholds must increase")

    def record(self) -> dict[str, float]:
        from dataclasses import asdict
        return asdict(self)

    def required_halo_samples(self, spacing_x_m: float, spacing_z_m: float) -> tuple[int, int]:
        # Trend slope needs one additional sample outside the widest filter.
        radius_m = max(self.trend_radius_m + max(spacing_x_m, spacing_z_m),
                       self.local_radius_m, self.coast_radius_m)
        return (math.ceil(radius_m / spacing_x_m), math.ceil(radius_m / spacing_z_m))


METRIC_30M_RECIPE_V1 = RegionRecipe(
    trend_sigma_m=120, trend_radius_m=360,
    local_sigma_m=60, local_radius_m=180,
    coast_sigma_m=90, coast_radius_m=270,
)


@dataclass(frozen=True)
class RegionResult:
    elevation_m: np.ndarray
    weights: np.ndarray
    dominant_type: np.ndarray


def _smooth(low: float, high: float, value: np.ndarray) -> np.ndarray:
    fraction = np.clip((value - low) / (high - low), 0.0, 1.0)
    return fraction * fraction * (3.0 - 2.0 * fraction)


def _gaussian(data: np.ndarray, spacing_x_m: float, spacing_z_m: float,
              sigma_m: float, radius_m: float) -> np.ndarray:
    result = data
    for axis, spacing in ((1, spacing_x_m), (0, spacing_z_m)):
        radius = math.ceil(radius_m / spacing)
        offsets = np.arange(-radius, radius + 1)
        kernel = np.exp(-0.5 * (offsets * spacing / sigma_m) ** 2)
        kernel[offsets * spacing > radius_m] = 0
        kernel[offsets * spacing < -radius_m] = 0
        kernel /= kernel.sum()
        padded = np.pad(result, [(radius, radius) if dim == axis else (0, 0)
                                 for dim in range(2)], mode="edge")
        result = np.apply_along_axis(lambda row: np.convolve(row, kernel, mode="valid"), axis, padded)
    return result


def process_region(height_m: np.ndarray, sea_level_m: float, spacing_x_m: float,
                   spacing_z_m: float, protection_mask: np.ndarray | None = None,
                   recipe: RegionRecipe = RegionRecipe()) -> RegionResult:
    """Process a supplied grid only; callers crop the declared halo before publishing."""
    raw = np.asarray(height_m, dtype=np.float64)
    if raw.ndim != 2 or min(raw.shape) < 2 or not np.isfinite(raw).all():
        raise ValueError("height must be a finite two-dimensional grid")
    if any(not math.isfinite(v) for v in (sea_level_m, spacing_x_m, spacing_z_m)) or min(spacing_x_m, spacing_z_m) <= 0:
        raise ValueError("invalid metre datum or spacing")
    if protection_mask is None:
        external = np.zeros(raw.shape, dtype=np.float64)
    else:
        external = np.asarray(protection_mask, dtype=np.float64)
        if external.shape != raw.shape or not np.isfinite(external).all() or np.any((external < 0) | (external > 1)):
            raise ValueError("protection mask must contain finite values in [0,1]")

    relative = raw - sea_level_m
    if not np.isfinite(relative).all() or np.max(np.abs(relative)) > 1e150:
        raise ValueError("height magnitude exceeds finite processing range")
    trend = _gaussian(relative, spacing_x_m, spacing_z_m, recipe.trend_sigma_m, recipe.trend_radius_m)
    local = _gaussian(relative, spacing_x_m, spacing_z_m, recipe.local_sigma_m, recipe.local_radius_m)
    squared = _gaussian(relative * relative, spacing_x_m, spacing_z_m,
                        recipe.trend_sigma_m, recipe.trend_radius_m)
    coast = _gaussian((relative <= 0).astype(float), spacing_x_m, spacing_z_m,
                      recipe.coast_sigma_m, recipe.coast_radius_m)
    relief = np.sqrt(np.maximum(0, squared - trend * trend))
    slope_z, slope_x = np.gradient(trend, spacing_z_m, spacing_x_m)
    slope = np.hypot(slope_x, slope_z)
    high = _smooth(recipe.high_low_m, recipe.high_high_m, trend)
    rugged = np.maximum.reduce((_smooth(recipe.relief_low_m, recipe.relief_high_m, relief),
                                _smooth(recipe.slope_low, recipe.slope_high, slope),
                                0.85 * _smooth(recipe.prominence_low_m,
                                               recipe.prominence_high_m, relative - trend)))
    weights = np.stack(((1 - high) * (1 - rugged), (1 - high) * rugged,
                        high * (1 - rugged), high * rugged), axis=-1)
    protect = np.maximum.reduce((external, 0.85 * _smooth(0.01, 0.22, coast),
                                 1 - _smooth(1, 9, relative)))
    blend = (1 - protect) * (1 - _smooth(recipe.peak_protect_low_m,
                                       recipe.peak_protect_high_m, relative - trend))
    delta = blend * (recipe.plain_strength * weights[..., 0] * (trend - relative) +
                     (recipe.hill_strength * weights[..., 1] +
                      recipe.plateau_strength * weights[..., 2]) * (local - relative))
    output = raw + delta
    if not np.isfinite(output).all() or not np.isfinite(weights).all():
        raise ValueError("processing produced non-finite terrain")
    return RegionResult(output.copy(), weights, np.argmax(weights, axis=-1).astype(np.uint8))


def rebase_base_surface(base: TerrainArtifact, new_sea_level_m: float) -> TerrainArtifact:
    """Move the datum and all heights together, preserving sea-relative relief."""
    if base.kind != "base" or base.displacement_type != "none" or base.water is not None:
        raise ValueError("rebase requires a dry base reference surface")
    if not math.isfinite(new_sea_level_m) or new_sea_level_m < 0:
        raise ValueError("sea level must be finite and nonnegative")
    delta = new_sea_level_m - base.sea_level_elevation_m
    return TerrainArtifact(kind="base", identity=ArtifactIdentity(
        backend=base.identity.backend, algorithm="datum_rebase",
        algorithm_version="1", seed=base.identity.seed,
        parameters={"source_content_id": base.content_id,
                    "source_identity": base.identity.record(),
                    "source_grid": base.grid_record(),
                    "target_sea_level_m": new_sea_level_m}),
        reference_elevation_m=base.reference_elevation_m + delta,
        origin_x_m=base.origin_x_m, origin_z_m=base.origin_z_m,
        spacing_x_m=base.spacing_x_m, spacing_z_m=base.spacing_z_m,
        vertical_datum="core bottom = 0 m", sea_level_elevation_m=new_sea_level_m)


