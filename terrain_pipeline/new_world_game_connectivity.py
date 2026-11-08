import math
import numpy as np


def audit_edges(bed, ocean, x, z, sources, targets, *, origin_m=-61440., spacing_m=30.):
    """Sample every crossed nearest-cell interval, downstream, on the finite segment.

    Returns per-edge bed rises and exact cell/entry location of the largest rise
    above any earlier sample. Ocean crossings use the original raster mask.
    A geometric pass is not evidence of flowing water.
    """
    n = len(sources)
    rise = np.zeros(n, np.float32)
    step = np.zeros(n, np.float32)
    blocker = np.full((n, 2), -1, np.int32)
    blocker_xz = np.full((n, 2), np.nan, np.float64)
    bed_max = np.full(n, -np.inf, np.float32)
    endpoint_bed = np.empty((n, 2), np.float32)
    ocean_hits = np.zeros(n, np.bool_)
    ocean_end = np.zeros(n, np.bool_)
    for i, (a, b) in enumerate(zip(sources, targets)):
        ax, az, bx, bz = x[a], z[a], x[b], z[b]
        gx, gz = (ax-origin_m)/spacing_m+.5, (az-origin_m)/spacing_m+.5
        hx, hz = (bx-origin_m)/spacing_m+.5, (bz-origin_m)/spacing_m+.5
        ts = [0., 1.]
        for u, v in ((gx, hx), (gz, hz)):
            if u != v:
                ts.extend((k-u)/(v-u) for k in range(math.floor(min(u,v))+1, math.ceil(max(u,v))) if 0 < (k-u)/(v-u) < 1)
        ts = sorted(set(ts))
        points = [(0., 0.)] + [((u+v)*.5, u) for u,v in zip(ts,ts[1:])] + [(1., 1.)]
        low = math.inf
        previous = None
        for t, entry in points:
            col = math.floor(gx+t*(hx-gx)); row = math.floor(gz+t*(hz-gz))
            if not (0 <= row < bed.shape[0] and 0 <= col < bed.shape[1]):
                raise ValueError('segment leaves source raster')
            value = float(bed[row, col])
            if not math.isfinite(value):
                raise ValueError('nonfinite source bed')
            bed_max[i] = max(bed_max[i], value)
            if t == 0.:
                endpoint_bed[i, 0] = value
            if t == 1.:
                endpoint_bed[i, 1] = value
            if previous is not None:
                step[i] = max(step[i], value-previous)
            if value-low > rise[i]:
                rise[i] = value-low
                blocker[i] = row, col
                blocker_xz[i] = ax+entry*(bx-ax), az+entry*(bz-az)
            low = min(low, value); previous = value
            ocean_hits[i] |= ocean[row, col]
            if t == 1.:
                ocean_end[i] = ocean[row, col]
    return dict(max_rise_m=rise, max_step_m=step, blocker_row_col=blocker,
                blocker_entry_xz_m=blocker_xz, bed_max_m=bed_max, endpoint_bed_m=endpoint_bed,
                ocean_crossing=ocean_hits, ocean_at_target=ocean_end)
