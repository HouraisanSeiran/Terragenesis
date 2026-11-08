"""Auditable spatial rainfall from absolute metre coordinates."""

from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np

from diffusion.geographic_noise import field
from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from .metric_contracts import RainfallForcing, TerrainGrid


SCHEMA = "metric-spatial-rain-v1"
MAX_BYTES = 1024 * 1024 * 1024
CALIBRATION = "fixed_reference_mean_affine_then_bounded_clip; target_mean_not_guaranteed_if_clipped"


@dataclass(frozen=True)
class SpatialRainRecipe:
    seed: int = 20261002
    scales: tuple = ((3840., .55), (960., .30), (240., .15))
    amplitude: float = .35
    multiplier_min: float = .6
    multiplier_max: float = 1.4
    reference_origin_m_xz: tuple = (-184320., 61440.)
    reference_spacing_m: float = 30.
    reference_shape_zx: tuple = (1024, 1024)

    def __post_init__(self):
        if type(self.seed) is not int or not 0 <= self.seed < 2**64:
            raise ValueError("seed must be uint64")
        if not isinstance(self.scales, (tuple, list)) or not 1 <= len(self.scales) <= 8:
            raise ValueError("one to eight noise scales required")
        weights = []
        for pair in self.scales:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError("scale is (spacing_m, weight)")
            spacing, weight = pair
            if (type(spacing) not in (int, float) or type(weight) not in (int, float)
                    or not math.isfinite(spacing) or not math.isfinite(weight)
                    or not 1. <= spacing <= 1e8 or not 1e-12 <= weight <= 1.):
                raise ValueError("invalid bounded noise scale/weight")
            weights.append(weight)
        if not math.isfinite(sum(weights)) or sum(weights) < 1e-12:
            raise ValueError("invalid total noise weight")
        if (type(self.amplitude) not in (int, float) or not math.isfinite(self.amplitude)
                or not 0. <= self.amplitude <= .9):
            raise ValueError("amplitude must be finite in [0,.9]")
        if (any(type(value) not in (int, float) or not math.isfinite(value) for value in
                (self.multiplier_min, self.multiplier_max, self.reference_spacing_m))
                or not 0. < self.multiplier_min <= 1. <= self.multiplier_max <= 2.
                or not 1. <= self.reference_spacing_m <= 1e5):
            raise ValueError("invalid positive multiplier bounds or reference spacing")
        if (not isinstance(self.reference_origin_m_xz, (tuple, list)) or len(self.reference_origin_m_xz) != 2
                or any(type(value) not in (int, float) or not math.isfinite(value)
                       or abs(value) > 1e12 for value in self.reference_origin_m_xz)):
            raise ValueError("finite bounded reference origin required")
        shape = self.reference_shape_zx
        if (not isinstance(shape, (tuple, list)) or len(shape) != 2
                or any(type(value) is not int or not 1 <= value <= 1024 for value in shape)
                or shape[0] * shape[1] > 1024 * 1024):
            raise ValueError("bounded reference shape required")
        minimum_scale = min(pair[0] for pair in self.scales)
        limit = max(abs(value) for value in self.reference_origin_m_xz) + max(shape) * self.reference_spacing_m
        if limit / minimum_scale > 2**52:
            raise ValueError("noise coordinate precision budget exceeded")
        object.__setattr__(self, "scales", tuple(tuple(pair) for pair in self.scales))
        object.__setattr__(self, "reference_origin_m_xz", tuple(self.reference_origin_m_xz))
        object.__setattr__(self, "reference_shape_zx", tuple(self.reference_shape_zx))


def _noise(x0, z0, dx, dz, shape, recipe):
    z, x = np.indices(shape, dtype=np.float64)
    x = x0 + x * dx
    z = z0 + z * dz
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("nonfinite rain coordinates")
    minimum_scale = min(pair[0] for pair in recipe.scales)
    if max(np.max(np.abs(x)), np.max(np.abs(z))) / minimum_scale > 2**52:
        raise ValueError("noise coordinate precision budget exceeded")
    return field(x, z, recipe.seed, 971, recipe.scales)


def build_spatial_forcing(terrain, time_seconds, base_storm_mm_h, recipe):
    if not isinstance(terrain, TerrainGrid) or not isinstance(recipe, SpatialRainRecipe):
        raise ValueError("TerrainGrid and SpatialRainRecipe required")
    times = np.asarray(time_seconds)
    base = np.asarray(base_storm_mm_h)
    if (times.dtype != np.float64 or times.ndim != 1 or base.dtype != np.float64
            or base.ndim != 1 or base.size != times.size - 1 or not np.isfinite(base).all()
            or np.any(base < 0.) or np.any(base > 1e6)):
        raise ValueError("float64 interval-average base storm required")
    if times.size < 2 or np.any(np.diff(times) != np.diff(times)[0]):
        raise ValueError("uniform physical forcing intervals required")
    reference = _noise(recipe.reference_origin_m_xz[0], recipe.reference_origin_m_xz[1],
                       recipe.reference_spacing_m, recipe.reference_spacing_m,
                       recipe.reference_shape_zx, recipe)
    reference_mean = float(np.mean(reference, dtype=np.float64))
    local_noise = _noise(terrain.x0_m, terrain.z0_m, terrain.dx_m, terrain.dz_m,
                         terrain.valid_mask.shape, recipe)
    multiplier = np.clip(1. + recipe.amplitude * (local_noise - reference_mean) / (1. + abs(reference_mean)),
                         recipe.multiplier_min, recipe.multiplier_max)
    multiplier = np.where(terrain.valid_mask, multiplier, 0.)
    rain = base[:, None, None] * multiplier[None, :, :]
    if not np.isfinite(rain).all() or np.any(rain > 1e6):
        raise ValueError("spatial rain outside forcing bounds")
    record = asdict(recipe)
    recipe_hash = hashlib.sha256(json.dumps(record, sort_keys=True).encode("utf-8")).hexdigest()
    forcing = RainfallForcing(times.copy(), rain, source_id="spatial-rain-" + recipe_hash,
                              source_sha256=recipe_hash)
    arrays = {"multiplier": readonly(multiplier), "valid_mask": terrain.valid_mask,
              "time_seconds": forcing.time_seconds, "base_storm_mm_h": readonly(base),
              "rain_mm_h": forcing.rain_mm_h}
    metadata = {"schema": SCHEMA, "recipe": record, "recipe_sha256": recipe_hash,
                "terrain_identity_sha256": terrain.identity_sha256,
                "forcing_identity_sha256": forcing.identity_sha256,
                "target_origin_m_xz": [float(terrain.x0_m), float(terrain.z0_m)],
                "target_spacing_m_xz": [float(terrain.dx_m), float(terrain.dz_m)],
                "target_shape_zx": list(terrain.valid_mask.shape),
                "noise_algorithm": "diffusion.geographic_noise.field_absolute_metre_v1",
                "reference_noise_mean": reference_mean,
                "valid_multiplier_mean": float(np.mean(multiplier[terrain.valid_mask])),
                "valid_multiplier_min": float(np.min(multiplier[terrain.valid_mask])),
                "valid_multiplier_max": float(np.max(multiplier[terrain.valid_mask])),
                "calibration": CALIBRATION,
                "temporal_semantics": "interval_average", "hydraulic_ready": False}
    package = {"arrays": arrays, "metadata": metadata,
               "identity_sha256": identity(arrays, metadata)}
    validate_spatial_forcing_package(package)
    return forcing, package


def validate_spatial_forcing_package(package):
    arrays, meta = package["arrays"], package["metadata"]
    if (set(arrays) != {"multiplier", "valid_mask", "time_seconds", "base_storm_mm_h", "rain_mm_h"}
            or set(meta) != {"schema", "recipe", "recipe_sha256", "terrain_identity_sha256",
                             "forcing_identity_sha256", "reference_noise_mean",
                             "valid_multiplier_mean", "valid_multiplier_min", "valid_multiplier_max",
                             "target_origin_m_xz", "target_spacing_m_xz", "target_shape_zx", "noise_algorithm",
                             "calibration", "temporal_semantics", "hydraulic_ready"}
            or meta.get("schema") != SCHEMA or meta.get("hydraulic_ready") is not False
            or meta.get("calibration") != CALIBRATION
            or meta.get("temporal_semantics") != "interval_average"
            or meta.get("noise_algorithm") != "diffusion.geographic_noise.field_absolute_metre_v1"
            or package["identity_sha256"] != identity(arrays, meta)):
        raise ValueError("spatial forcing identity/schema mismatch")
    for key in ("recipe_sha256", "terrain_identity_sha256", "forcing_identity_sha256"):
        value = meta[key]
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("invalid forcing identity: " + key)
    reference_mean = meta["reference_noise_mean"]
    if (type(reference_mean) not in (int, float) or not math.isfinite(reference_mean)
            or not -1. <= reference_mean <= 1.):
        raise ValueError("invalid reference noise mean")
    recipe = SpatialRainRecipe(**meta["recipe"])
    expected_recipe_hash = hashlib.sha256(json.dumps(asdict(recipe), sort_keys=True).encode("utf-8")).hexdigest()
    if expected_recipe_hash != meta["recipe_sha256"]:
        raise ValueError("spatial recipe identity mismatch")
    mask, multiplier = arrays["valid_mask"], arrays["multiplier"]
    origin, spacing, shape = (meta[key] for key in
                              ("target_origin_m_xz", "target_spacing_m_xz", "target_shape_zx"))
    if (not isinstance(origin, list) or len(origin) != 2 or
            any(type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e12
                for value in origin) or not isinstance(spacing, list) or len(spacing) != 2 or
            any(type(value) not in (int, float) or not math.isfinite(value) or not 0. < value <= 1e5
                for value in spacing) or not isinstance(shape, list) or len(shape) != 2 or
            any(type(value) is not int or value <= 0 for value in shape) or shape != list(mask.shape)):
        raise ValueError("invalid target coordinate metadata")
    if (mask.dtype != bool or mask.ndim != 2 or multiplier.shape != mask.shape
            or multiplier.dtype != np.float64 or not mask.any() or not np.isfinite(multiplier).all()
            or np.any(multiplier[~mask] != 0.)
            or np.any(multiplier[mask] < recipe.multiplier_min)
            or np.any(multiplier[mask] > recipe.multiplier_max)):
        raise ValueError("invalid saved rainfall multiplier")
    forcing = RainfallForcing(arrays["time_seconds"], arrays["rain_mm_h"],
                              source_id="spatial-rain-" + expected_recipe_hash,
                              source_sha256=expected_recipe_hash)
    if forcing.identity_sha256 != meta["forcing_identity_sha256"]:
        raise ValueError("saved forcing identity mismatch")
    if np.any(forcing.interval_seconds != forcing.interval_seconds[0]):
        raise ValueError("uniform forcing intervals required")
    base = arrays["base_storm_mm_h"]
    if (base.dtype != np.float64 or base.shape != (forcing.rain_mm_h.shape[0],)
            or not np.isfinite(base).all() or np.any(base < 0.)
            or not np.array_equal(forcing.rain_mm_h, base[:, None, None] * multiplier[None, :, :])):
        raise ValueError("saved base storm linkage mismatch")
    for key, expected in (("valid_multiplier_mean", np.mean(multiplier[mask])),
                          ("valid_multiplier_min", np.min(multiplier[mask])),
                          ("valid_multiplier_max", np.max(multiplier[mask]))):
        if meta[key] != float(expected):
            raise ValueError("saved multiplier statistic mismatch")
    return True


def save_spatial_forcing_package(path, package):
    save_bundle(path, package, validator=validate_spatial_forcing_package)


def load_spatial_forcing_package(path, *, expected_sha256, expected_identity):
    package = load_bundle(path, expected_sha256=expected_sha256,
                          validator=validate_spatial_forcing_package, max_bytes=MAX_BYTES)
    if package["identity_sha256"] != expected_identity:
        raise ValueError("external spatial forcing identity mismatch")
    return package
