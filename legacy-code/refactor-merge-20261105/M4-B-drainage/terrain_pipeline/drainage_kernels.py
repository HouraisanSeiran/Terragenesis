"""Single implementations of the drainage kernels that were copied across modules.

Every function body here is moved verbatim from the first-listed source, so sums
keep their order and ties keep their rule. Nothing in this module changes a
number written by an existing product. Equivalence with each older entry point is
checked by ``tests/test_drainage_kernels_equivalence.py``.

Sources
-------
flood_order / select_receivers / flood_route
    new_world_stage1_flood_phases._flood_order / ._select_receivers,
    new_world_stage1._mapped_route, irregular_drainage._route (all nodes valid)
accumulate_flow / accumulate_inplace
    irregular_drainage._accumulate, new_world_native_lowland.accumulate,
    world_acceptance_processes.route_pool_interval (no pool)
accumulate_with_pools
    world_acceptance_processes.route_pool_interval
native_section
    new_world_native_network.section
lake_wet_window
    lake_wet_mask expression repeated in new_world_native_network_v2/v3/v4 (v5)
file_sha256, canonical_json_digest, canonical_json_digest_compact
    new_world_stage1._digest, new_world_stage1_flood_phases.digest,
    new_world_native_lowland.digest; hydrology_detail(_projection/_td)._digest;
    hydrology_detail_tributaries._digest

Not merged here (different semantics or different numbers):
irregular_grid._strict, native_event.classify,
native_lowland.channels_and_capture, pool_labels vs _label_pools,
new_world_native_geometry.native_lake_wet (also masks unknown cells).
"""
import numpy as np
from numba import njit

from terrain_pipeline.common_infra import (
    NATIVE_GRID, NATIVE_ORIGIN_M, NATIVE_SPACING_M,
    NATIVE_WINDOW_Z0, NATIVE_WINDOW_Z1, NATIVE_WINDOW_X0, NATIVE_WINDOW_X1,
)


# --- priority flood and receiver choice ------------------------------------

@njit(cache=True)
def flood_order(bed, outlets, valid, indptr, indices, filled, order, rank, discovered, heap_level, heap_node):
    n = bed.size
    size = 0
    for node in range(n):
        filled[node] = bed[node]
        discovered[node] = outlets[node] or not valid[node]
        rank[node] = -1
        order[node] = -1
        if outlets[node]:
            pos = size
            size += 1
            while pos:
                parent = (pos - 1) // 2
                if (heap_level[parent] < bed[node] or
                    (heap_level[parent] == bed[node] and heap_node[parent] <= node)):
                    break
                heap_level[pos] = heap_level[parent]
                heap_node[pos] = heap_node[parent]
                pos = parent
            heap_level[pos] = bed[node]
            heap_node[pos] = node
    visited = 0
    while size:
        level = heap_level[0]
        current = heap_node[0]
        size -= 1
        if size:
            last_level = heap_level[size]
            last_node = heap_node[size]
            pos = 0
            while 2 * pos + 1 < size:
                child = 2 * pos + 1
                if child + 1 < size and (heap_level[child + 1] < heap_level[child] or
                    (heap_level[child + 1] == heap_level[child] and heap_node[child + 1] < heap_node[child])):
                    child += 1
                if (last_level < heap_level[child] or
                    (last_level == heap_level[child] and last_node <= heap_node[child])):
                    break
                heap_level[pos] = heap_level[child]
                heap_node[pos] = heap_node[child]
                pos = child
            heap_level[pos] = last_level
            heap_node[pos] = last_node
        rank[current] = visited
        order[visited] = current
        visited += 1
        for edge in range(indptr[current], indptr[current + 1]):
            neighbor = indices[edge]
            if discovered[neighbor]:
                continue
            discovered[neighbor] = True
            new_level = max(bed[neighbor], level)
            filled[neighbor] = new_level
            pos = size
            size += 1
            while pos:
                parent = (pos - 1) // 2
                if (heap_level[parent] < new_level or
                    (heap_level[parent] == new_level and heap_node[parent] <= neighbor)):
                    break
                heap_level[pos] = heap_level[parent]
                heap_node[pos] = heap_node[parent]
                pos = parent
            heap_level[pos] = new_level
            heap_node[pos] = neighbor
    if visited != np.count_nonzero(valid):
        raise ValueError('Graph has a component without an explicit outlet')


@njit(cache=True)
def select_receivers(outlets, valid, x, z, indptr, indices, filled, order, rank, receiver):
    n = valid.size
    receiver[:] = -1
    for k in range(n):
        current = order[k]
        if current < 0:
            continue
        if outlets[current]:
            continue
        best_slope = -1.0
        best_rank = n
        for edge in range(indptr[current], indptr[current + 1]):
            neighbor = indices[edge]
            if not valid[neighbor] or rank[neighbor] >= rank[current] or filled[neighbor] > filled[current]:
                continue
            distance = np.hypot(x[current] - x[neighbor], z[current] - z[neighbor])
            slope = (filled[current] - filled[neighbor]) / distance
            if slope > best_slope or (slope == best_slope and rank[neighbor] < best_rank):
                receiver[current] = neighbor
                best_slope = slope
                best_rank = rank[neighbor]
        if receiver[current] < 0:
            raise ValueError('Non-outlet node has no downstream neighbor')


@njit(cache=True)
def flood_route(bed, outlets, valid, x, z, indptr, indices, filled, order, rank,
                receiver, discovered, heap_level, heap_node):
    """Flood then choose receivers in one call (new_world_stage1._mapped_route)."""
    flood_order(bed, outlets, valid, indptr, indices, filled, order, rank, discovered,
                heap_level, heap_node)
    select_receivers(outlets, valid, x, z, indptr, indices, filled, order, rank, receiver)


def flood_route_arrays(bed, outlets, node_x_m, node_z_m, indptr, indices, valid=None):
    """Allocate working arrays, run ``flood_route``; returns filled, order, rank, receiver.

    Replaces irregular_drainage._route when ``valid`` is omitted (every node valid).
    """
    bed = np.ascontiguousarray(bed, dtype=np.float64).ravel()
    outlets = np.ascontiguousarray(outlets, dtype=np.bool_).ravel()
    n = bed.size
    valid = (np.ones(n, dtype=np.bool_) if valid is None
             else np.ascontiguousarray(valid, dtype=np.bool_).ravel())
    filled = np.empty(n, dtype=np.float64)
    order = np.empty(n, dtype=np.int64)
    rank = np.empty(n, dtype=np.int64)
    receiver = np.empty(n, dtype=np.int64)
    discovered = np.empty(n, dtype=np.bool_)
    heap_level = np.empty(n, dtype=np.float64)
    heap_node = np.empty(n, dtype=np.int64)
    flood_route(bed, outlets, valid, node_x_m, node_z_m, indptr, indices, filled, order,
                rank, receiver, discovered, heap_level, heap_node)
    return filled, order, rank, receiver


# --- flow accumulation ------------------------------------------------------

@njit
def accumulate_inplace(order, receiver, area):
    """Add each donor's total to its receiver, farthest-downstream first (native_lowland.accumulate)."""
    for j in range(order.size - 1, -1, -1):
        i = order[j]
        target = receiver[i]
        if target >= 0:
            area[target] += area[i]


@njit(cache=True)
def accumulate_flow(receiver, order, local):
    """Copying accumulation (irregular_drainage._accumulate); same summation order."""
    flow = local.copy()
    for index in range(order.size - 1, -1, -1):
        current = order[index]
        downstream = receiver[current]
        if downstream >= 0:
            flow[downstream] += flow[current]
    return flow


@njit(cache=True)
def accumulate_with_pools(local_volume, order, receiver, labels, anchors, capacity, storage):
    """Collapse each pool at its downstream flood-rank anchor, releasing overflow."""
    flow = local_volume.copy()
    incoming = np.zeros(capacity.size)
    retained = 0.
    for index in range(order.size - 1, -1, -1):
        cell = order[index]
        label = labels[cell]
        if label >= 0:
            incoming[label] += flow[cell]
            if cell != anchors[label]:
                continue
            available = storage[label] + incoming[label]
            updated = min(capacity[label], available)
            retained += updated - storage[label]
            storage[label] = updated
            flow[cell] = available - updated
        target = receiver[cell]
        if target >= 0:
            flow[target] += flow[cell]
    return flow, retained


# --- river section and lake masks (native 30 m window products) -------------

def native_section(q):
    """Default discharge power laws with default material/exposure (network v1 ``section``)."""
    from terrain_pipeline.surface_rivers.metric_discharge_geometry import DischargeGeometryConfig
    c = DischargeGeometryConfig()
    exposure = 1 - np.exp(-c.generation_exposure)
    width = np.minimum(c.max_width_m, c.width_at_unit_q_m * np.maximum(q, 0)**c.width_q_exponent * 1.75 * 1.25 * exposure)
    depth = np.minimum(c.max_incise_m, c.depth_at_unit_q_m * np.maximum(q, 0)**c.depth_q_exponent * 1.0 * 1.0 * exposure)
    return width, depth


def lake_wet_window(labels_grid, bed_grid, levels, ocean_grid, window=None):
    """Wet lake cells of a window: pool level finite, bed below level, not ocean.

    Does not exclude unknown cells (unlike new_world_native_geometry.native_lake_wet).
    ``labels_grid``/``bed_grid``/``ocean_grid`` are full 2-D grids; ``window`` is
    (z0, z1, x0, x1), default the saved display window.
    """
    z0, z1, x0, x1 = window or (NATIVE_WINDOW_Z0, NATIVE_WINDOW_Z1, NATIVE_WINDOW_X0, NATIVE_WINDOW_X1)
    pool = labels_grid[z0:z1, x0:x1]
    heights = bed_grid[z0:z1, x0:x1]
    wet = np.zeros(pool.shape, bool)
    present = pool >= 0
    wet[present] = np.isfinite(levels[pool[present]]) & (heights[present] < levels[pool[present]])
    wet &= ~ocean_grid[z0:z1, x0:x1]
    return wet
