"""Conservative native coastal water relaxation; this is not a momentum solver.

Inputs use metres and square metres. River water is a separate stock and must
not be passed here. Positive-area native cells are connected by their faces.
"""
import numpy as np
from numba import njit


@njit
def _relax(bed, area, volume, iterations):
    rows, cols = bed.shape
    for iteration in range(iterations):
        # Alternating sweep direction limits directional bias.
        for axis in range(2):
            for k in range(rows * cols):
                i = k if iteration % 2 == 0 else rows * cols - 1 - k
                r, c = i // cols, i % cols
                rr, cc = r + (axis == 0), c + (axis == 1)
                if rr >= rows or cc >= cols or area[r, c] <= 0 or area[rr, cc] <= 0:
                    continue
                a, b = area[r, c], area[rr, cc]
                ha = bed[r, c] + volume[r, c] / a
                hb = bed[rr, cc] + volume[rr, cc] / b
                crest = max(bed[r, c], bed[rr, cc])
                if ha > hb and ha > crest:
                    transfer = min(volume[r, c], (ha - hb) / (1. / a + 1. / b))
                    volume[r, c] -= transfer
                    volume[rr, cc] += transfer
                elif hb > ha and hb > crest:
                    transfer = min(volume[rr, cc], (hb - ha) / (1. / a + 1. / b))
                    volume[rr, cc] -= transfer
                    volume[r, c] += transfer
    return volume


def reconstruct_coastal_water(bed_m, area_m2, depth_m, *, iterations=40, return_stats=False):
    """Redistribute coastal water locally across passable native faces.

    Conserves total volume, not individual coarse-cell volumes. Dry cells can
    receive water only across a face below the donor surface. Zero-area cells
    are impermeable. Previously wet donors may drain completely.
    """
    bed = np.asarray(bed_m, dtype=np.float64)
    area = np.asarray(area_m2, dtype=np.float64)
    depth = np.asarray(depth_m, dtype=np.float64)
    if bed.ndim != 2 or bed.shape != area.shape or bed.shape != depth.shape:
        raise ValueError('bed, area and depth must be matching 2D arrays')
    if (not np.isfinite(bed).all() or not np.isfinite(area).all()
            or not np.isfinite(depth).all() or np.any(area < 0)
            or np.any(depth < 0) or np.any((area == 0) & (depth > 0))
            or not isinstance(iterations, int) or iterations < 0):
        raise ValueError('invalid coastal reconstruction input')
    volume = area * depth
    result = _relax(bed, area, volume.copy(), iterations)
    output = np.divide(result, area, out=np.zeros_like(result), where=area > 0)
    if return_stats:
        return output, {'volume_residual_m3': float(result.sum() - volume.sum())}
    return output
