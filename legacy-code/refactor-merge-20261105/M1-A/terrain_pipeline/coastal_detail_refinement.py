"""Static recovery of suppressed TD detail; distances are cell-centre raster proxies.

Connectivity and distance support belong to the full baseline domain. Offset
windows must slice that shared support and supply a radius-cell filtering halo.
Only the inner core of such a window is guaranteed independent of its edges.
"""
from dataclasses import dataclass
import numpy as np
from scipy.ndimage import gaussian_filter, distance_transform_edt, binary_dilation


@dataclass(frozen=True)
class DetailParameters:
    spacing_m: float = 30.0
    sigma_short_m: float = 60.0
    sigma_long_m: float = 180.0
    radius_m: float = 720.0
    coast_band_m: float = 240.0
    elevation_band_m: float = 40.0
    sign_band_m: float = 90.0
    cap_m: float = 6.0
    strength: float = 1.0

    def validate(self):
        values = np.array(list(self.__dict__.values()), dtype=float)
        if not np.isfinite(values).all() or min(values[:-1]) <= 0 or not 0 <= self.strength <= 1:
            raise ValueError("invalid detail parameters")
        if not self.sigma_short_m < self.sigma_long_m <= self.radius_m <= 720 or self.coast_band_m > 240 or self.elevation_band_m > 40 or self.sign_band_m > min(90, self.coast_band_m) or self.cap_m > 6:
            raise ValueError("detail parameters exceed bounded support")
        cells = self.radius_m / self.spacing_m
        if cells < 1 or abs(cells - round(cells)) > 1e-9:
            raise ValueError("filter radius must be whole cells")
        return int(round(cells))


def _smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def detail_support(bed, valid, classification, shoreline, params=DetailParameters()):
    """Prepare once on the full classified baseline, then slice for windows.

    Unknown and enclosed wet cells never change. Full filter support must lie
    within the valid domain; its edge clearance also has a smooth one-cell ramp.
    """
    params.validate()
    bed = np.asarray(bed)
    if bed.ndim != 2 or any(np.asarray(a).shape != bed.shape for a in (valid, classification, shoreline)) or valid.dtype != np.bool_ or shoreline.dtype != np.bool_ or classification.dtype != np.uint8 or not np.isfinite(bed).all() or not np.isin(classification, [0, 1, 2, 3]).all():
        raise ValueError("invalid baseline support fields")
    if np.any(shoreline & ((classification != 1) | ~valid)):
        raise ValueError("invalid marine shoreline")
    distance = np.full(bed.shape, params.coast_band_m, np.float32)
    if shoreline.any():
        distance[:] = np.minimum(distance_transform_edt(~shoreline) * params.spacing_m, params.coast_band_m)
    # Pad explicitly: scipy's all-true EDT otherwise has an implicit asymmetric edge.
    clearance = distance_transform_edt(np.pad(valid, 1, constant_values=False))[1:-1, 1:-1] * params.spacing_m
    weight = _smooth(1 - distance / params.coast_band_m)
    weight *= _smooth(1 - np.abs(bed) / params.elevation_band_m)
    weight *= _smooth((clearance - params.radius_m) / params.spacing_m)
    weight *= valid & ((classification == 1) | (classification == 2))
    # Keep a dry guard around nonmarine wet components so restoration cannot
    # connect a previously unknown/enclosed water body to the marine anchor.
    protected_wet = valid & (bed < 0) & (classification != 2)
    weight[binary_dilation(protected_wet)] = 0
    return {"distance_m": distance, "weight": weight.astype(np.float32)}


def refine(raw, bed, *, support, params=DetailParameters()):
    """Return bed and actual float32 delta, without mutating any input.

    Difference of bandpasses equals the bandpass of raw minus baseline. The
    finite Gaussian radius is explicit, with no noise or stochastic state.
    """
    radius = params.validate()
    raw, bed = np.asarray(raw), np.asarray(bed)
    if bed.dtype != np.float32 or raw.ndim != 2 or raw.shape != bed.shape or min(bed.shape) <= 2 * radius or not np.isfinite(raw).all() or not np.isfinite(bed).all():
        raise ValueError("finite aligned raw/float32 baseline with halo required")
    if set(support) != {"distance_m", "weight"}:
        raise ValueError("shared full-domain support required")
    distance, weight = support["distance_m"], support["weight"]
    if any(a.shape != bed.shape or a.dtype != np.float32 or not np.isfinite(a).all() for a in (distance, weight)) or np.any((weight < 0) | (weight > 1)) or np.any((distance < 0) | (distance > params.coast_band_m)) or np.any((weight > 0) & ((distance >= params.coast_band_m) | (np.abs(bed) >= params.elevation_band_m))):
        raise ValueError("invalid shared support")
    if params.strength == 0:
        return bed.copy(), np.zeros_like(bed)
    residual = raw.astype(np.float32) - bed
    if not np.isfinite(residual).all():
        raise ValueError("unrepresentable raw/baseline residual")
    short = gaussian_filter(residual, params.sigma_short_m / params.spacing_m, radius=radius, mode="nearest")
    long = gaussian_filter(residual, params.sigma_long_m / params.spacing_m, radius=radius, mode="nearest")
    delta = (short - long) * (params.strength * weight)
    # Smoothly reduce the allowed crossing as the sign-change boundary approaches.
    crossing = _smooth(1 - distance / params.sign_band_m) * params.cap_m
    delta = np.clip(delta, -params.cap_m, params.cap_m)
    delta = np.where(bed >= 0, np.maximum(delta, -bed - crossing), np.minimum(delta, -bed + crossing))
    result = (bed + delta).astype(np.float32)
    locked_wet = (distance >= params.sign_band_m) & (bed < 0)
    result[locked_wet] = np.minimum(result[locked_wet], np.nextafter(np.float32(0), np.float32(-1)))
    result[weight == 0] = bed[weight == 0]
    return result, (result - bed).astype(np.float32)
