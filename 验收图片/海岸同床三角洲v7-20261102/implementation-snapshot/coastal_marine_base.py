"""Regional, source-bound coast-following geological scenario (no sediment)."""
from dataclasses import dataclass
import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter, binary_dilation


@dataclass(frozen=True)
class MarineBaseParameters:
    min_width_m: float = 18000.0
    max_width_m: float = 55000.0
    break_depth_m: float = 160.0
    relief_limit_m: float = 55.0
    context_scale_m: float = 12000.0
    edge_fade_m: float = 12000.0


def reorganize(bed, valid, ocean, unknown_wet, spacing_m, params=MarineBaseParameters(), *, continental_fraction=None, crust_thickness_m=None):
    """Prepare once on full coverage; diagnostics are scenario targets, not observations."""
    bed = np.asarray(bed, dtype=np.float32)
    valid = np.asarray(valid, dtype=bool)
    ocean = np.asarray(ocean, dtype=bool)
    unknown_wet = np.asarray(unknown_wet, dtype=bool)
    if bed.ndim != 2 or any(a.shape != bed.shape for a in (valid, ocean, unknown_wet)) or not np.isfinite(bed[valid]).all() or spacing_m <= 0:
        raise ValueError('invalid source grid')
    if np.any(ocean & (~valid | (bed >= 0) | unknown_wet)) or not ocean.any():
        raise ValueError('invalid source ocean')
    if not (0 < params.min_width_m < params.max_width_m and params.break_depth_m > 0 and params.relief_limit_m > 0 and params.context_scale_m > 0 and params.edge_fade_m > 0):
        raise ValueError('invalid parameters')
    land = valid & (bed >= 0)
    if not land.any():
        raise ValueError('coast requires land')
    distance = distance_transform_edt(~land) * spacing_m
    # Normalized convolution prevents invalid cells influencing context.
    sigma = params.context_scale_m / spacing_m
    weight = gaussian_filter(valid.astype(float), sigma, mode='nearest')
    context = gaussian_filter(np.where(valid, bed, 0).astype(float), sigma, mode='nearest') / np.maximum(weight, 1e-6)
    # Fields are model-derived tectonic context, not observations. Their
    # combined effect is an explicit game scenario, not geological inference.
    if continental_fraction is None and crust_thickness_m is None:
        continental_fraction = np.full(bed.shape, 0.5)
        crust_thickness_m = np.full(bed.shape, 21000.0)
    continental_fraction = np.asarray(continental_fraction, dtype=float)
    crust_thickness_m = np.asarray(crust_thickness_m, dtype=float)
    if (continental_fraction.shape != bed.shape or crust_thickness_m.shape != bed.shape
            or not np.isfinite(continental_fraction).all() or not np.isfinite(crust_thickness_m).all()
            or np.any((continental_fraction < 0) | (continental_fraction > 1))
            or np.any(crust_thickness_m < 0)):
        raise ValueError('invalid tectonic context')
    morphology = np.clip((context + 2800.0) / 4000.0, 0, 1)
    continental = gaussian_filter(continental_fraction, sigma, mode='nearest')
    crust = gaussian_filter(np.clip((crust_thickness_m - 7000) / 35000, 0, 1), sigma, mode='nearest')
    factor = np.clip(0.45 * morphology + 0.35 * continental + 0.20 * crust, 0, 1)
    factor = gaussian_filter(factor, sigma / 2, mode='nearest')
    width = params.min_width_m + (params.max_width_m - params.min_width_m) * factor
    break_depth = params.break_depth_m * (0.8 + 0.4 * (1 - factor))
    t = distance / width
    target_depth = np.where(t <= 1, break_depth * (0.4 * t + 0.6 * t ** 1.25),
                            break_depth + (distance - width) * (0.018 + 0.012 * (1 - factor)))
    # Retain bounded fine TD submarine relief, vanishing smoothly at shore.
    detail_sigma = max(1, 4000 / spacing_m)
    detail_weight = gaussian_filter(valid.astype(float), detail_sigma, mode="nearest")
    detail_mean = gaussian_filter(np.where(valid, bed, 0).astype(float), detail_sigma, mode="nearest") / np.maximum(detail_weight, 1e-6)
    detail = np.where(valid, bed - detail_mean, 0)
    residual = np.clip(detail, -params.relief_limit_m, params.relief_limit_m)
    shore_taper = np.clip(distance / 5000.0, 0, 1)
    residual = np.minimum(residual * shore_taper, 0.45 * target_depth)
    target = -target_depth + residual
    target = np.minimum(target, -0.5)
    # Blend back to original bed with zero derivative at both ends.
    u = np.clip((t - 1.0) / 2.5, 0, 1)
    influence = 1 - u * u * (3 - 2 * u)
    # Unknown/finite coverage is not treated as coastline. Fade changes before
    # the coverage boundary so the saved domain rejoins the source smoothly.
    interior = valid.copy()
    interior[[0, -1], :] = False
    interior[:, [0, -1]] = False
    edge_distance = distance_transform_edt(interior) * spacing_m
    e = np.clip(edge_distance / params.edge_fade_m, 0, 1)
    influence *= e * e * (3 - 2 * e)
    change = np.where(ocean, influence * (target - bed), 0)
    base = np.where(ocean, np.minimum(bed + change, np.maximum(bed, -0.5)), bed).astype(np.float32)
    classification = np.zeros(bed.shape, np.uint8)
    classification[valid & (bed >= 0)] = 1
    classification[valid & (bed < 0) & ~unknown_wet] = 3
    classification[ocean] = 2
    shore = (classification == 1) & binary_dilation(ocean)
    def marine_field(a):
        return np.where(ocean, a, 0).astype(np.float32)
    return {'source_bed': bed.copy(), 'derived_base_bed': base, 'final_bed': base.copy(),
            'valid': valid.copy(), 'source_ocean': ocean.copy(), 'classification': classification,
            'shoreline': shore, 'coast_distance_m': marine_field(distance),
            'shelf_width_m': marine_field(width), 'shelf_break_depth_m': marine_field(break_depth),
            'shelf_slope': marine_field(break_depth / width), 'base_change_m': (base - bed).astype(np.float32),
            'continental_fraction': continental_fraction.astype(np.float32),
            'crust_thickness_m': crust_thickness_m.astype(np.float32)}


