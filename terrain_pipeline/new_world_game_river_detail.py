"""Local 30 m projection of saved 90 m receiver edges.

The search stays in a small box around the two control cells.  It does not
change the receiver graph or infer water levels.  Its cost prefers low uphill
steps; the subsequent cumulative-rise check is the actual cut bound.
"""
import heapq
import math

import numpy as np


def local_path(bed, ocean, start, end, *, margin=3, allow_ocean_end=False, allowed=None):
    """Return an eight-connected local path, or None if the box is blocked."""
    r0 = max(0, min(start[0], end[0]) - margin)
    r1 = min(bed.shape[0], max(start[0], end[0]) + margin + 1)
    c0 = max(0, min(start[1], end[1]) - margin)
    c1 = min(bed.shape[1], max(start[1], end[1]) + margin + 1)
    dist = {start: 0.0}
    prev = {}
    queue = [(0.0, start)]
    while queue:
        cost, cell = heapq.heappop(queue)
        if cost != dist[cell]:
            continue
        if cell == end:
            path = [cell]
            while cell != start:
                cell = prev[cell]
                path.append(cell)
            return path[::-1]
        height = float(bed[cell])
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if not (dr or dc):
                    continue
                nxt = cell[0] + dr, cell[1] + dc
                if not (r0 <= nxt[0] < r1 and c0 <= nxt[1] < c1):
                    continue
                if ocean[nxt] and not (allow_ocean_end and nxt == end):
                    continue
                if nxt != end and allowed is not None and not allowed(nxt):
                    continue
                value = float(bed[nxt])
                if not math.isfinite(value):
                    continue
                new = cost + math.hypot(dr, dc) + 4 * max(0.0, value-height)
                if new < dist.get(nxt, math.inf):
                    dist[nxt] = new
                    prev[nxt] = cell
                    heapq.heappush(queue, (new, nxt))
    return None


def required_cut(profile):
    """Cut for a non-increasing profile with the upstream sample fixed."""
    values = np.asarray(profile, dtype=np.float64)
    return values - np.minimum.accumulate(values)
