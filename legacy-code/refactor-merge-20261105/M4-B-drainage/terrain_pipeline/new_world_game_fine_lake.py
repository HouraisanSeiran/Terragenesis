"""Bounded minimax basin support and volume-conserving snapshot inversion."""
import heapq
import numpy as np
from terrain_pipeline.surface_rivers.metric_lake_storage import LakeStorage


def minimax_cost(bed, allowed, seed):
    bed = np.asarray(bed, float); allowed = np.asarray(allowed, bool)
    if bed.shape != allowed.shape or not allowed[seed]:
        raise ValueError('seed must be inside finite allowed support')
    cost = np.full(bed.shape, np.inf); cost[seed] = bed[seed]
    previous = np.full((*bed.shape, 2), -1, np.int32)
    queue = [(float(bed[seed]), *seed)]
    while queue:
        h, r, c = heapq.heappop(queue)
        if h != cost[r, c]:
            continue
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == dc == 0:
                    continue
                y, x = r + dr, c + dc
                if not (0 <= y < bed.shape[0] and 0 <= x < bed.shape[1] and allowed[y, x]):
                    continue
                v = max(h, bed[y, x])
                if v < cost[y, x]:
                    cost[y, x] = v; previous[y, x] = (r, c); heapq.heappush(queue, (v, y, x))
    return cost, previous


def invert_connected_storage(bed, cost, spill_m, volume_m3, identity):
    """Invert on seed-connected pre-spill cells; return storage and excess."""
    support = np.isfinite(cost) & (cost < spill_m) & (bed < spill_m)
    indices = np.flatnonzero(support)
    if not len(indices):
        raise ValueError('no connected pre-spill support')
    values = np.asarray(bed.flat[indices], dtype=np.float64)
    seed_id = int(indices[np.argmin(values)])
    lake = LakeStorage(indices.astype(np.int64), values, np.full(len(indices), 900., dtype=np.float64), seed_id,
                       float(spill_m), identity, 'minimax-connected-pre-spill-30m')
    retained = min(float(volume_m3), lake.capacity_m3)
    stage = lake.stage_at_volume(retained)
    # Cells gated by a saddle above stage must not be filled, so this inversion
    # is valid only if all cells below stage are reachable at that stage.
    if np.any((values < stage) & (cost.flat[indices] >= stage)):
        raise ValueError('internal saddle requires connected dynamic inversion')
    mask = np.zeros(bed.shape, bool); mask.flat[indices] = lake.wet_mask_at_stage(stage)
    return stage, retained, float(volume_m3)-retained, lake.capacity_m3, mask
