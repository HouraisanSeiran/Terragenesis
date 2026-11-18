"""drainage: merged M4 implementation; source locations precede each statement."""
from __future__ import annotations

from collections import deque as _m4_drainage_deque
from collections import deque as _m4_real_dem_flat_routing_deque
from collections.abc import Mapping as _m4_reference_routing_Mapping
from contextlib import ExitStack as _m4_world_disk_water_ExitStack
from dataclasses import asdict as _m4_reference_routing_asdict
from dataclasses import dataclass as _m4_irregular_drainage_dataclass
from dataclasses import dataclass as _m4_real_dem_surface_network_dataclass
from dataclasses import dataclass as _m4_real_dem_tiled_network_dataclass
from dataclasses import dataclass as _m4_reference_routing_dataclass
from dataclasses import replace as _m4_irregular_grid_replace
from numba import njit as _m4_drainage_kernels_njit
from numba import njit as _m4_irregular_drainage_njit
from numba import njit as _m4_irregular_grid_njit
from numba import njit as _m4_new_world_native_lowland_njit
from numba import njit as _m4_world_acceptance_processes_njit
from numba import njit as _m4_world_disk_catchment_njit
from numba import njit as _m4_world_disk_water_njit
from pathlib import Path as _m4_new_world_native_lowland_Path
from pathlib import Path as _m4_new_world_stage1_flood_phases_Path
from pathlib import Path as _m4_world_disk_catchment_Path
from pathlib import Path as _m4_world_disk_water_Path
from scipy.sparse import coo_matrix as _m4_irregular_drainage_coo_matrix
from scipy.spatial import Delaunay as _m4_irregular_drainage_Delaunay
from terrain_pipeline.common_infra import BoundaryGrid as _m4_drainage_BoundaryGrid
from terrain_pipeline.common_infra import BoundaryGrid as _m4_routing_comparison_BoundaryGrid
from terrain_pipeline.common_infra import RoutingGraph as _m4_drainage_RoutingGraph
from terrain_pipeline.common_infra import RoutingGraph as _m4_routing_comparison_RoutingGraph
from terrain_pipeline.common_infra import TerrainGrid as _m4_drainage_TerrainGrid
from terrain_pipeline.common_infra import TerrainGrid as _m4_routing_comparison_TerrainGrid
from terrain_pipeline.common_infra import readonly as _m4_reference_routing_readonly
from types import MappingProxyType as _m4_reference_routing_MappingProxyType
import hashlib as _m4_new_world_native_lowland_hashlib
import hashlib as _m4_new_world_stage1_flood_phases_hashlib
import heapq as _m4_drainage_heapq
import heapq as _m4_irregular_drainage_heapq
import heapq as _m4_routing_comparison_heapq
import json as _m4_new_world_native_lowland_json
import json as _m4_new_world_stage1_flood_phases_json
import json as _m4_world_disk_water_json
import math as _m4_drainage_math
import math as _m4_network_accumulation_math
import math as _m4_reference_routing_math
import math as _m4_routing_comparison_math
import math as _m4_world_disk_water_math
import numpy as _m4_drainage_kernels_np
import numpy as _m4_drainage_np
import numpy as _m4_irregular_drainage_np
import numpy as _m4_irregular_grid_np
import numpy as _m4_native_product_invariants_np
import numpy as _m4_network_accumulation_np
import numpy as _m4_new_world_native_lowland_np
import numpy as _m4_new_world_stage1_flood_phases_np
import numpy as _m4_real_dem_flat_routing_np
import numpy as _m4_real_dem_surface_network_np
import numpy as _m4_real_dem_tiled_network_np
import numpy as _m4_reference_routing_np
import numpy as _m4_routing_comparison_np
import numpy as _m4_world_acceptance_processes_np
import numpy as _m4_world_disk_catchment_np
import numpy as _m4_world_disk_water_np
import os as _m4_new_world_native_lowland_os
import os as _m4_new_world_stage1_flood_phases_os
import time as _m4_new_world_native_lowland_time

CATEGORY = "B"

# --- terrain_pipeline/drainage_kernels.py:44 ---
@_m4_drainage_kernels_njit(cache=True)
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
    if visited != _m4_drainage_kernels_np.count_nonzero(valid):
        raise ValueError('Graph has a component without an explicit outlet')

# --- terrain_pipeline/drainage_kernels.py:114 ---
@_m4_drainage_kernels_njit(cache=True)
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
            distance = _m4_drainage_kernels_np.hypot(x[current] - x[neighbor], z[current] - z[neighbor])
            slope = (filled[current] - filled[neighbor]) / distance
            if slope > best_slope or (slope == best_slope and rank[neighbor] < best_rank):
                receiver[current] = neighbor
                best_slope = slope
                best_rank = rank[neighbor]
        if receiver[current] < 0:
            raise ValueError('Non-outlet node has no downstream neighbor')

# --- terrain_pipeline/drainage_kernels.py:140 ---
@_m4_drainage_kernels_njit(cache=True)
def flood_route(bed, outlets, valid, x, z, indptr, indices, filled, order, rank,
                receiver, discovered, heap_level, heap_node):
    """Flood then choose receivers in one call (new_world_stage1._mapped_route)."""
    flood_order(bed, outlets, valid, indptr, indices, filled, order, rank, discovered,
                heap_level, heap_node)
    select_receivers(outlets, valid, x, z, indptr, indices, filled, order, rank, receiver)

# --- terrain_pipeline/drainage_kernels.py:148 ---
def flood_route_arrays(bed, outlets, node_x_m, node_z_m, indptr, indices, valid=None):
    """Allocate working arrays, run ``flood_route``; returns filled, order, rank, receiver.

    Replaces irregular_drainage._route when ``valid`` is omitted (every node valid).
    """
    bed = _m4_drainage_kernels_np.ascontiguousarray(bed, dtype=_m4_drainage_kernels_np.float64).ravel()
    outlets = _m4_drainage_kernels_np.ascontiguousarray(outlets, dtype=_m4_drainage_kernels_np.bool_).ravel()
    n = bed.size
    valid = (_m4_drainage_kernels_np.ones(n, dtype=_m4_drainage_kernels_np.bool_) if valid is None
             else _m4_drainage_kernels_np.ascontiguousarray(valid, dtype=_m4_drainage_kernels_np.bool_).ravel())
    filled = _m4_drainage_kernels_np.empty(n, dtype=_m4_drainage_kernels_np.float64)
    order = _m4_drainage_kernels_np.empty(n, dtype=_m4_drainage_kernels_np.int64)
    rank = _m4_drainage_kernels_np.empty(n, dtype=_m4_drainage_kernels_np.int64)
    receiver = _m4_drainage_kernels_np.empty(n, dtype=_m4_drainage_kernels_np.int64)
    discovered = _m4_drainage_kernels_np.empty(n, dtype=_m4_drainage_kernels_np.bool_)
    heap_level = _m4_drainage_kernels_np.empty(n, dtype=_m4_drainage_kernels_np.float64)
    heap_node = _m4_drainage_kernels_np.empty(n, dtype=_m4_drainage_kernels_np.int64)
    flood_route(bed, outlets, valid, node_x_m, node_z_m, indptr, indices, filled, order,
                rank, receiver, discovered, heap_level, heap_node)
    return filled, order, rank, receiver

# --- terrain_pipeline/drainage_kernels.py:173 ---
@_m4_drainage_kernels_njit
def accumulate_inplace(order, receiver, area):
    """Add each donor's total to its receiver, farthest-downstream first (native_lowland.accumulate)."""
    for j in range(order.size - 1, -1, -1):
        i = order[j]
        target = receiver[i]
        if target >= 0:
            area[target] += area[i]

# --- terrain_pipeline/drainage_kernels.py:183 ---
@_m4_drainage_kernels_njit(cache=True)
def accumulate_flow(receiver, order, local):
    """Copying accumulation (irregular_drainage._accumulate); same summation order."""
    flow = local.copy()
    for index in range(order.size - 1, -1, -1):
        current = order[index]
        downstream = receiver[current]
        if downstream >= 0:
            flow[downstream] += flow[current]
    return flow

# --- terrain_pipeline/drainage_kernels.py:195 ---
@_m4_drainage_kernels_njit(cache=True)
def accumulate_with_pools(local_volume, order, receiver, labels, anchors, capacity, storage):
    """Collapse each pool at its downstream flood-rank anchor, releasing overflow."""
    flow = local_volume.copy()
    incoming = _m4_drainage_kernels_np.zeros(capacity.size)
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

# --- terrain_pipeline/drainage_kernels.py:220 ---
def native_section(q):
    """Default discharge power laws with default material/exposure (network v1 ``section``)."""
    from terrain_pipeline.channel_geometry import DischargeGeometryConfig
    c = DischargeGeometryConfig()
    exposure = 1 - _m4_drainage_kernels_np.exp(-c.generation_exposure)
    width = _m4_drainage_kernels_np.minimum(c.max_width_m, c.width_at_unit_q_m * _m4_drainage_kernels_np.maximum(q, 0)**c.width_q_exponent * 1.75 * 1.25 * exposure)
    depth = _m4_drainage_kernels_np.minimum(c.max_incise_m, c.depth_at_unit_q_m * _m4_drainage_kernels_np.maximum(q, 0)**c.depth_q_exponent * 1.0 * 1.0 * exposure)
    return width, depth

# --- terrain_pipeline/drainage_kernels.py:230 ---
def lake_wet_window(labels_grid, bed_grid, levels, ocean_grid, window=None):
    """Wet lake cells of a window: pool level finite, bed below level, not ocean.

    Does not exclude unknown cells (unlike new_world_native_geometry.native_lake_wet).
    ``labels_grid``/``bed_grid``/``ocean_grid`` are full 2-D grids; ``window`` is
    (z0, z1, x0, x1), default the saved display window.
    """
    from terrain_pipeline.common_infra import NATIVE_WINDOW_X0 as _m4_drainage_kernels_NATIVE_WINDOW_X0
    from terrain_pipeline.common_infra import NATIVE_WINDOW_X1 as _m4_drainage_kernels_NATIVE_WINDOW_X1
    from terrain_pipeline.common_infra import NATIVE_WINDOW_Z0 as _m4_drainage_kernels_NATIVE_WINDOW_Z0
    from terrain_pipeline.common_infra import NATIVE_WINDOW_Z1 as _m4_drainage_kernels_NATIVE_WINDOW_Z1
    z0, z1, x0, x1 = window or (_m4_drainage_kernels_NATIVE_WINDOW_Z0, _m4_drainage_kernels_NATIVE_WINDOW_Z1, _m4_drainage_kernels_NATIVE_WINDOW_X0, _m4_drainage_kernels_NATIVE_WINDOW_X1)
    pool = labels_grid[z0:z1, x0:x1]
    heights = bed_grid[z0:z1, x0:x1]
    wet = _m4_drainage_kernels_np.zeros(pool.shape, bool)
    present = pool >= 0
    wet[present] = _m4_drainage_kernels_np.isfinite(levels[pool[present]]) & (heights[present] < levels[pool[present]])
    wet &= ~ocean_grid[z0:z1, x0:x1]
    return wet

# --- terrain_pipeline/irregular_drainage.py:20 ---
@_m4_irregular_drainage_dataclass(frozen=True)
class IrregularMesh:
    shape: tuple[int, int]
    origin_native_xz: tuple[int, int]
    spacing_m: float
    world_seed: int
    node_x_m: _m4_irregular_drainage_np.ndarray
    node_z_m: _m4_irregular_drainage_np.ndarray
    indptr: _m4_irregular_drainage_np.ndarray
    indices: _m4_irregular_drainage_np.ndarray
    edge_length_m: _m4_irregular_drainage_np.ndarray

# --- terrain_pipeline/irregular_drainage.py:33 ---
@_m4_irregular_drainage_dataclass(frozen=True)
class GraphRouting:
    filled: _m4_irregular_drainage_np.ndarray
    order: _m4_irregular_drainage_np.ndarray
    rank: _m4_irregular_drainage_np.ndarray
    receiver: _m4_irregular_drainage_np.ndarray

# --- terrain_pipeline/irregular_drainage.py:40 ---
def _mix64(value):
    value = value ^ (value >> _m4_irregular_drainage_np.uint64(30))
    value = value * _m4_irregular_drainage_np.uint64(0xBF58476D1CE4E5B9)
    value = value ^ (value >> _m4_irregular_drainage_np.uint64(27))
    value = value * _m4_irregular_drainage_np.uint64(0x94D049BB133111EB)
    return value ^ (value >> _m4_irregular_drainage_np.uint64(31))

# --- terrain_pipeline/irregular_drainage.py:48 ---
def build_mesh(shape, origin_native_xz=(0, 0), spacing_m=30.0,
               world_seed=20261020) -> IrregularMesh:
    """Build CSR adjacency without edge duplication or global edge sorting.

    Position substreams use SplitMix64 finalization, absolute signed native
    indices interpreted modulo 2**64, and separate fixed x/z domain constants.
    Nodes occupy the central 70% of their cell; repeat calls and overlapping
    windows have bit-identical world positions. Edges come from Delaunay
    triangles with circumradius at most two cells. A 256-cell core and eight-cell
    halo bound temporary memory and exclude distant convex-hull shortcuts.
    """
    if len(shape) != 2 or any(not isinstance(v, (int, _m4_irregular_drainage_np.integer)) or v < 1 for v in shape):
        raise ValueError("shape must contain two positive integers")
    if len(origin_native_xz) != 2 or any(not isinstance(v, (int, _m4_irregular_drainage_np.integer)) for v in origin_native_xz):
        raise ValueError("origin_native_xz must contain two integers")
    if not _m4_irregular_drainage_np.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("spacing_m must be finite and positive")
    if not isinstance(world_seed, (int, _m4_irregular_drainage_np.integer)):
        raise ValueError("world_seed must be an integer")
    rows, cols = (int(v) for v in shape)
    origin_x, origin_z = (int(v) for v in origin_native_xz)
    native_x = _m4_irregular_drainage_np.tile(_m4_irregular_drainage_np.arange(cols, dtype=_m4_irregular_drainage_np.int64), rows) + origin_x
    native_z = _m4_irregular_drainage_np.repeat(_m4_irregular_drainage_np.arange(rows, dtype=_m4_irregular_drainage_np.int64), cols) + origin_z
    seed = _m4_irregular_drainage_np.uint64(int(world_seed) % (1 << 64))
    key = (_mix64(native_x.view(_m4_irregular_drainage_np.uint64) ^ _m4_irregular_drainage_np.uint64(0x632BE59BD9B4E019))
           ^ _mix64(native_z.view(_m4_irregular_drainage_np.uint64) ^ _m4_irregular_drainage_np.uint64(0x9E3779B97F4A7C15)) ^ seed)
    fraction_x = (_mix64(key ^ _m4_irregular_drainage_np.uint64(0xD1B54A32D192ED03)) >> _m4_irregular_drainage_np.uint64(11)).astype(_m4_irregular_drainage_np.float64) * (2.0 ** -53)
    fraction_z = (_mix64(key ^ _m4_irregular_drainage_np.uint64(0xABC98388FB8FAC03)) >> _m4_irregular_drainage_np.uint64(11)).astype(_m4_irregular_drainage_np.float64) * (2.0 ** -53)
    node_x = (native_x + 0.7 * (fraction_x - 0.5)) * spacing_m
    node_z = (native_z + 0.7 * (fraction_z - 0.5)) * spacing_m
    del native_x, native_z, key, fraction_x, fraction_z
    count = rows * cols
    if count == 1:
        indptr = _m4_irregular_drainage_np.array([0, 0], dtype=_m4_irregular_drainage_np.int32)
        indices = _m4_irregular_drainage_np.empty(0, dtype=_m4_irregular_drainage_np.int32)
    elif count == 2:
        indptr = _m4_irregular_drainage_np.array([0, 1, 2], dtype=_m4_irregular_drainage_np.int32)
        indices = _m4_irregular_drainage_np.array([1, 0], dtype=_m4_irregular_drainage_np.int32)
    elif min(rows, cols) == 1:
        degree = _m4_irregular_drainage_np.full(count, 2, dtype=_m4_irregular_drainage_np.int64)
        degree[0] = degree[-1] = 1
        indptr = _m4_irregular_drainage_np.concatenate((_m4_irregular_drainage_np.zeros(1, dtype=_m4_irregular_drainage_np.int64), _m4_irregular_drainage_np.cumsum(degree)))
        indices = _m4_irregular_drainage_np.empty(int(indptr[-1]), dtype=_m4_irregular_drainage_np.int32)
        indices[indptr[:-1][1:]] = _m4_irregular_drainage_np.arange(count - 1)
        indices[indptr[1:-1] - 1] = _m4_irregular_drainage_np.arange(1, count)
    else:
        indptr, indices = _bounded_adjacency(node_x, node_z, (rows, cols), spacing_m)
    edge_length = _edge_lengths(node_x, node_z, indptr, indices)
    for array in (node_x, node_z, indptr, indices, edge_length):
        array.flags.writeable = False
    return IrregularMesh((rows, cols), (origin_x, origin_z), float(spacing_m),
                         int(world_seed), node_x, node_z, indptr, indices, edge_length)

# --- terrain_pipeline/irregular_drainage.py:102 ---
def _block_neighbors(node_x, node_z, shape, spacing_m, z0, x0, core_size):
    rows, cols = shape
    z1, x1 = min(rows, z0 + core_size), min(cols, x0 + core_size)
    hz0, hx0 = max(0, z0 - 8), max(0, x0 - 8)
    hz1, hx1 = min(rows, z1 + 8), min(cols, x1 + 8)
    local_shape = (hz1 - hz0, hx1 - hx0)
    local_x = node_x.reshape(shape)[hz0:hz1, hx0:hx1].ravel()
    local_z = node_z.reshape(shape)[hz0:hz1, hx0:hx1].ravel()
    points = _m4_irregular_drainage_np.column_stack((local_x - local_x[0], local_z - local_z[0]))
    triangulation = _m4_irregular_drainage_Delaunay(points)
    triangles = triangulation.simplices.copy()
    del triangulation
    first = points[triangles[:, 1]] - points[triangles[:, 0]]
    second = points[triangles[:, 2]] - points[triangles[:, 0]]
    cross = abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0])
    side_product = _m4_irregular_drainage_np.linalg.norm(first, axis=1) * _m4_irregular_drainage_np.linalg.norm(second, axis=1) * _m4_irregular_drainage_np.linalg.norm(first - second, axis=1)
    triangles = triangles[side_product <= 4 * spacing_m * cross]
    source = triangles[:, (0, 1, 1, 2, 2, 0)].ravel()
    target = triangles[:, (1, 0, 2, 1, 0, 2)].ravel()
    adjacency = _m4_irregular_drainage_coo_matrix((_m4_irregular_drainage_np.ones(source.size, dtype=_m4_irregular_drainage_np.uint8), (source, target)),
                           shape=(points.shape[0], points.shape[0])).tocsr()
    local_core = (_m4_irregular_drainage_np.arange(z0 - hz0, z1 - hz0)[:, None] * local_shape[1]
                  + _m4_irregular_drainage_np.arange(x0 - hx0, x1 - hx0)).ravel()
    core = (_m4_irregular_drainage_np.arange(z0, z1)[:, None] * cols + _m4_irregular_drainage_np.arange(x0, x1)).ravel()
    selected = adjacency[local_core]
    neighbors = ((selected.indices // local_shape[1] + hz0) * cols
                 + selected.indices % local_shape[1] + hx0).astype(_m4_irregular_drainage_np.int32)
    return core, _m4_irregular_drainage_np.diff(selected.indptr).astype(_m4_irregular_drainage_np.int64), neighbors

# --- terrain_pipeline/irregular_drainage.py:132 ---
def _bounded_adjacency(node_x, node_z, shape, spacing_m, core_size=256):
    """Two bounded triangulation passes avoid Python objects per global node."""
    rows, cols = shape
    degree = _m4_irregular_drainage_np.empty(rows * cols, dtype=_m4_irregular_drainage_np.int64)
    for z0 in range(0, rows, core_size):
        for x0 in range(0, cols, core_size):
            core, local_degree, _ = _block_neighbors(node_x, node_z, shape, spacing_m,
                                                    z0, x0, core_size)
            degree[core] = local_degree
    indptr = _m4_irregular_drainage_np.concatenate((_m4_irregular_drainage_np.zeros(1, dtype=_m4_irregular_drainage_np.int64), _m4_irregular_drainage_np.cumsum(degree)))
    indices = _m4_irregular_drainage_np.empty(int(indptr[-1]), dtype=_m4_irregular_drainage_np.int32)
    for z0 in range(0, rows, core_size):
        for x0 in range(0, cols, core_size):
            core, local_degree, neighbors = _block_neighbors(node_x, node_z, shape,
                                                             spacing_m, z0, x0, core_size)
            row_start = _m4_irregular_drainage_np.cumsum(local_degree) - local_degree
            destinations = (_m4_irregular_drainage_np.repeat(indptr[core], local_degree) + _m4_irregular_drainage_np.arange(neighbors.size)
                            - _m4_irregular_drainage_np.repeat(row_start, local_degree))
            indices[destinations] = neighbors
    return indptr, indices

# --- terrain_pipeline/irregular_drainage.py:155 ---
@_m4_irregular_drainage_njit(cache=True)
def _edge_lengths(node_x, node_z, indptr, indices):
    lengths = _m4_irregular_drainage_np.empty(indices.size, dtype=_m4_irregular_drainage_np.float64)
    for current in range(node_x.size):
        for edge in range(indptr[current], indptr[current + 1]):
            neighbor = indices[edge]
            lengths[edge] = _m4_irregular_drainage_np.hypot(node_x[current] - node_x[neighbor],
                                    node_z[current] - node_z[neighbor])
    return lengths

# --- terrain_pipeline/irregular_drainage.py:166 ---
@_m4_irregular_drainage_njit(cache=True)
def _route(bed, outlets, indptr, indices, lengths):
    count = bed.size
    filled = bed.copy()
    discovered = outlets.copy()
    heap = [(filled[i], i) for i in range(count) if outlets[i]]
    _m4_irregular_drainage_heapq.heapify(heap)
    order = _m4_irregular_drainage_np.empty(count, dtype=_m4_irregular_drainage_np.int64)
    rank = _m4_irregular_drainage_np.empty(count, dtype=_m4_irregular_drainage_np.int64)
    visited = 0
    while heap:
        level, current = _m4_irregular_drainage_heapq.heappop(heap)
        rank[current] = visited
        order[visited] = current
        visited += 1
        for edge in range(indptr[current], indptr[current + 1]):
            neighbor = indices[edge]
            if discovered[neighbor]:
                continue
            discovered[neighbor] = True
            filled[neighbor] = max(filled[neighbor], level)
            _m4_irregular_drainage_heapq.heappush(heap, (filled[neighbor], _m4_irregular_drainage_np.int64(neighbor)))
    if visited != count:
        raise ValueError("Graph has a component without an explicit outlet")
    receiver = _m4_irregular_drainage_np.full(count, -1, dtype=_m4_irregular_drainage_np.int64)
    for current in order:
        if outlets[current]:
            continue
        best_slope = -1.0
        best_rank = count
        for edge in range(indptr[current], indptr[current + 1]):
            neighbor = indices[edge]
            if rank[neighbor] >= rank[current] or filled[neighbor] > filled[current]:
                continue
            slope = (filled[current] - filled[neighbor]) / lengths[edge]
            if slope > best_slope or (slope == best_slope and rank[neighbor] < best_rank):
                receiver[current] = neighbor
                best_slope = slope
                best_rank = rank[neighbor]
        if receiver[current] < 0:
            raise ValueError("Non-outlet node has no downstream neighbor")
    return filled, order, rank, receiver

# --- terrain_pipeline/irregular_drainage.py:209 ---
def route_graph(bed, outlets, mesh: IrregularMesh) -> GraphRouting:
    """Flood a working surface and route by metric slope on CSR graph edges.

    Real bed remains unchanged. Equal working levels descend flood rank, making
    receiver edges acyclic; explicit outlets always retain receiver -1.
    """
    raw = _m4_irregular_drainage_np.asarray(bed, dtype=_m4_irregular_drainage_np.float64)
    terminal = _m4_irregular_drainage_np.asarray(outlets, dtype=_m4_irregular_drainage_np.bool_)
    if raw.shape != mesh.shape or terminal.shape != mesh.shape:
        raise ValueError("bed and outlets must match mesh shape")
    if not _m4_irregular_drainage_np.isfinite(raw).all() or not terminal.any():
        raise ValueError("bed must be finite and at least one explicit outlet is required")
    filled, order, rank, receiver = _route(raw.ravel(), terminal.ravel(), mesh.indptr,
                                          mesh.indices, mesh.edge_length_m)
    filled = filled.reshape(mesh.shape)
    for array in (filled, order, rank, receiver):
        array.flags.writeable = False
    return GraphRouting(filled, order, rank, receiver)

# --- terrain_pipeline/irregular_drainage.py:230 ---
@_m4_irregular_drainage_njit(cache=True)
def _accumulate(receiver, order, local):
    flow = local.copy()
    for index in range(order.size - 1, -1, -1):
        current = order[index]
        downstream = receiver[current]
        if downstream >= 0:
            flow[downstream] += flow[current]
    return flow

# --- terrain_pipeline/irregular_drainage.py:240 ---
def accumulate_graph(receiver, order, local_input):
    """Accumulate nonnegative volume/time per native cell without changing area."""
    local = _m4_irregular_drainage_np.asarray(local_input, dtype=_m4_irregular_drainage_np.float64)
    receiver = _m4_irregular_drainage_np.asarray(receiver, dtype=_m4_irregular_drainage_np.int64)
    order = _m4_irregular_drainage_np.asarray(order, dtype=_m4_irregular_drainage_np.int64)
    if receiver.shape != (local.size,) or order.shape != receiver.shape:
        raise ValueError("receiver and order must match local_input size")
    if not _m4_irregular_drainage_np.isfinite(local).all() or (local < 0).any():
        raise ValueError("local_input must be finite and nonnegative")
    if (receiver < -1).any() or (receiver >= local.size).any():
        raise ValueError("receiver indices are out of range")
    if (order < 0).any() or (order >= local.size).any() or _m4_irregular_drainage_np.any(_m4_irregular_drainage_np.bincount(order, minlength=local.size) != 1):
        raise ValueError("order must be a permutation")
    rank = _m4_irregular_drainage_np.empty(local.size, dtype=_m4_irregular_drainage_np.int64)
    rank[order] = _m4_irregular_drainage_np.arange(local.size)
    donors = _m4_irregular_drainage_np.flatnonzero(receiver >= 0)
    if _m4_irregular_drainage_np.any(rank[receiver[donors]] >= rank[donors]):
        raise ValueError("receivers must precede donors")
    flow = _accumulate(receiver, order, local.ravel()).reshape(local.shape)
    if not _m4_irregular_drainage_np.isfinite(flow).all():
        raise ValueError("Accumulated discharge overflows float64")
    return flow

# --- terrain_pipeline/irregular_grid.py:10 ---
def grid_mesh(shape, *, x0_m=0., z0_m=0., dx_m=30., dz_m=None, world_seed=20261020):
    """Preserve absolute native account identity and metric node positions."""
    dz_m = dx_m if dz_m is None else dz_m
    if not _m4_irregular_grid_np.isfinite([x0_m, z0_m, dx_m, dz_m]).all() or min(dx_m, dz_m) <= 0.:
        raise ValueError("finite metric frame and positive cell dimensions required")
    origin = (int(_m4_irregular_grid_np.floor(x0_m / dx_m + 1e-9)), int(_m4_irregular_grid_np.floor(z0_m / dz_m + 1e-9)))
    mesh = build_mesh(shape, origin_native_xz=origin, spacing_m=dx_m, world_seed=world_seed)
    x = mesh.node_x_m + (x0_m - origin[0] * dx_m)
    z = mesh.node_z_m * (dz_m / dx_m) + (z0_m - origin[1] * dz_m)
    lengths = _m4_irregular_grid_np.empty(mesh.indices.size, _m4_irregular_grid_np.float64)
    for node in range(x.size):
        section = slice(mesh.indptr[node], mesh.indptr[node + 1])
        targets = mesh.indices[section]
        lengths[section] = _m4_irregular_grid_np.hypot(x[targets] - x[node], z[targets] - z[node])
    return _m4_irregular_grid_replace(mesh, node_x_m=x, node_z_m=z, edge_length_m=lengths)

# --- terrain_pipeline/irregular_grid.py:28 ---
@_m4_irregular_grid_njit(cache=True)
def _strict(height, valid, outlets, indptr, indices, lengths):
    receiver = _m4_irregular_grid_np.full(height.size, -1, _m4_irregular_grid_np.int64)
    edge_length = _m4_irregular_grid_np.zeros(height.size, _m4_irregular_grid_np.float64)
    slope = _m4_irregular_grid_np.zeros(height.size, _m4_irregular_grid_np.float64)
    for node in range(height.size):
        if not valid[node] or outlets[node]:
            continue
        for edge in range(indptr[node], indptr[node + 1]):
            target = indices[edge]
            if not valid[target]:
                continue
            candidate = (height[node] - height[target]) / lengths[edge]
            if candidate > slope[node] or (candidate > 0. and candidate == slope[node]
                                            and target < receiver[node]):
                receiver[node] = target
                edge_length[node] = lengths[edge]
                slope[node] = candidate
    return receiver, edge_length, slope

# --- terrain_pipeline/irregular_grid.py:48 ---
def strict_receivers(height, mesh, *, valid_mask=None, outlet_mask=None):
    """Strict downhill metric graph routing; flats remain explicit sinks."""
    raw = _m4_irregular_grid_np.asarray(height, _m4_irregular_grid_np.float64)
    valid = _m4_irregular_grid_np.ones(raw.shape, bool) if valid_mask is None else _m4_irregular_grid_np.asarray(valid_mask)
    outlets = _m4_irregular_grid_np.zeros(raw.shape, bool) if outlet_mask is None else _m4_irregular_grid_np.asarray(outlet_mask)
    if (raw.shape != mesh.shape or valid.shape != raw.shape or outlets.shape != raw.shape
            or valid.dtype != bool or outlets.dtype != bool or not _m4_irregular_grid_np.isfinite(raw[valid]).all()):
        raise ValueError("finite graph terrain and matching masks required")
    return _strict(raw.ravel(), valid.ravel(), outlets.ravel(), mesh.indptr,
                   mesh.indices, mesh.edge_length_m)

# --- terrain_pipeline/irregular_grid.py:60 ---
def receiver_edges_valid(receiver, mesh):
    """Check the actual graph edge set without fixed raster-neighbor rules."""
    rec = _m4_irregular_grid_np.asarray(receiver).ravel()
    if rec.size != mesh.node_x_m.size or _m4_irregular_grid_np.any(rec < -1) or _m4_irregular_grid_np.any(rec >= rec.size):
        return False
    return all(rec[node] in mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]
               for node in _m4_irregular_grid_np.flatnonzero(rec >= 0))

# --- terrain_pipeline/irregular_grid.py:69 ---
def reverse_donors(receiver):
    """Build reverse CSR for receiver traversal in linear time."""
    rec = _m4_irregular_grid_np.asarray(receiver).ravel()
    donors = _m4_irregular_grid_np.flatnonzero(rec >= 0)
    order = _m4_irregular_grid_np.argsort(rec[donors], kind="stable")
    counts = _m4_irregular_grid_np.bincount(rec[donors], minlength=rec.size)
    return _m4_irregular_grid_np.r_[0, _m4_irregular_grid_np.cumsum(counts)], donors[order]

# --- terrain_pipeline/irregular_grid.py:79 ---
@_m4_irregular_grid_njit(cache=True)
def segments_clear(sources, targets, valid):
    """Conservative control-cell supercover, including unknown corner touches.

    Cell-center account segments define the mask barrier independently of the
    representative displacement. This preserves the rule that a diagonal may
    not slip between two unknown orthogonal cells, for any graph edge length.
    """
    cols = valid.shape[1]
    result = _m4_irregular_grid_np.ones(sources.size, _m4_irregular_grid_np.bool_)
    for edge in range(sources.size):
        row, col = sources[edge] // cols, sources[edge] % cols
        end_row, end_col = targets[edge] // cols, targets[edge] % cols
        dr, dc = end_row - row, end_col - col
        nr, nc = abs(dr), abs(dc)
        sr, sc = (1 if dr > 0 else -1), (1 if dc > 0 else -1)
        ir, ic = 0, 0
        if not valid[row, col] or not valid[end_row, end_col]:
            result[edge] = False
            continue
        while ir < nr or ic < nc:
            cross_x = (2 * ic + 1) * nr
            cross_z = (2 * ir + 1) * nc
            if cross_x == cross_z:
                if not valid[row, col + sc] or not valid[row + sr, col]:
                    result[edge] = False
                    break
                col += sc
                row += sr
                ic += 1
                ir += 1
            elif cross_x < cross_z:
                col += sc
                ic += 1
            else:
                row += sr
                ir += 1
            if not valid[row, col]:
                result[edge] = False
                break
    return result

# --- terrain_pipeline/irregular_grid.py:121 ---
def valid_edge_mask(mesh, valid_mask):
    valid = _m4_irregular_grid_np.asarray(valid_mask)
    if valid.dtype != bool or valid.shape != mesh.shape:
        raise ValueError("matching boolean valid mask required")
    sources = _m4_irregular_grid_np.repeat(_m4_irregular_grid_np.arange(valid.size, dtype=_m4_irregular_grid_np.int64), _m4_irregular_grid_np.diff(mesh.indptr))
    return segments_clear(sources, mesh.indices, valid)

# --- terrain_pipeline/irregular_grid.py:129 ---
def masked_mesh(mesh, valid_mask):
    """Remove graph edges crossing unknown control cells without bridging holes."""
    keep = valid_edge_mask(mesh, valid_mask)
    source = _m4_irregular_grid_np.repeat(_m4_irregular_grid_np.arange(_m4_irregular_grid_np.prod(mesh.shape), dtype=_m4_irregular_grid_np.int64), _m4_irregular_grid_np.diff(mesh.indptr))
    counts = _m4_irregular_grid_np.bincount(source[keep], minlength=int(_m4_irregular_grid_np.prod(mesh.shape)))
    indptr = _m4_irregular_grid_np.r_[0, _m4_irregular_grid_np.cumsum(counts)].astype(_m4_irregular_grid_np.int64)
    return _m4_irregular_grid_replace(mesh, indptr=indptr, indices=mesh.indices[keep],
                   edge_length_m=mesh.edge_length_m[keep])

# --- terrain_pipeline/irregular_grid.py:139 ---
def graph_support_unknown(valid_mask, *, x0_m=0., z0_m=0., dx_m=30., dz_m=None,
                          world_seed=20261020):
    """Cells whose full bounded-radius graph neighbourhood exceeds known support."""
    valid = _m4_irregular_grid_np.asarray(valid_mask)
    if valid.ndim != 2 or valid.dtype != bool:
        raise ValueError("2D boolean valid mask required")
    dz_m = dx_m if dz_m is None else dz_m
    pad = 4
    rows, cols = valid.shape
    extended = grid_mesh((rows + 2 * pad, cols + 2 * pad),
        x0_m=x0_m - pad * dx_m, z0_m=z0_m - pad * dz_m,
        dx_m=dx_m, dz_m=dz_m, world_seed=world_seed)
    supported = valid_edge_mask(extended, _m4_irregular_grid_np.pad(valid, pad, constant_values=False))
    source = _m4_irregular_grid_np.repeat(_m4_irregular_grid_np.arange(_m4_irregular_grid_np.prod(extended.shape), dtype=_m4_irregular_grid_np.int64), _m4_irregular_grid_np.diff(extended.indptr))
    unknown = _m4_irregular_grid_np.bincount(source[~supported], minlength=int(_m4_irregular_grid_np.prod(extended.shape))) > 0
    return valid & unknown.reshape(extended.shape)[pad:pad + rows, pad:pad + cols]

# --- terrain_pipeline/surface_rivers/drainage.py:9 ---
def route(height: _m4_drainage_np.ndarray, outlet_mask: _m4_drainage_np.ndarray, spacing_blocks: float, *,
          origin_native_xz=(0, 0), world_seed=20261020,
          origin_world_xz=None) -> _m4_drainage_RoutingResult:
    """Route native cell accounts over deterministic irregular graph positions.

    The returned order lists receivers before donors. Flat cells use flood order
    as a deterministic descending tie-break, so the receiver graph is acyclic.
    """
    raw = _m4_drainage_np.asarray(height, dtype=_m4_drainage_np.float64)
    outlets = _m4_drainage_np.asarray(outlet_mask, dtype=_m4_drainage_np.bool_)
    if raw.ndim != 2 or min(raw.shape) < 1 or outlets.shape != raw.shape:
        raise ValueError("height and outlet_mask must share a nonempty 2D shape")
    if not _m4_drainage_np.isfinite(raw).all() or not _m4_drainage_np.isfinite(spacing_blocks) or spacing_blocks <= 0:
        raise ValueError("height and spacing_blocks must be finite; spacing must be positive")
    if not outlets.any():
        raise ValueError("At least one explicit outlet is required")

    if origin_world_xz is None:
        mesh = build_mesh(raw.shape, origin_native_xz, spacing_blocks, world_seed)
    else:
        if len(origin_world_xz) != 2:
            raise ValueError("origin_world_xz must contain two finite coordinates")
        from terrain_pipeline.drainage import grid_mesh as grid_mesh
        mesh = grid_mesh(raw.shape, x0_m=origin_world_xz[0], z0_m=origin_world_xz[1],
                         dx_m=spacing_blocks, world_seed=world_seed)
    result = route_graph(raw, outlets, mesh)
    receiver, order, routing_height = result.receiver, result.order, result.filled
    outlet_copy = outlets.copy()
    for array in (receiver, order, routing_height, outlet_copy):
        array.flags.writeable = False
    return _m4_drainage_RoutingResult(receiver, order, routing_height, outlet_copy, float(spacing_blocks))

# --- terrain_pipeline/surface_rivers/drainage.py:42 ---
def accumulate(routing: _m4_drainage_RoutingResult, runoff: _m4_drainage_np.ndarray, spacing_blocks: float,
               external_inflow: _m4_drainage_np.ndarray | None = None) -> _m4_drainage_AccumulationResult:
    """Accumulate runoff depth/time and optional per-cell volume/time inflow."""
    shape = routing.routing_height.shape
    if routing.receiver.shape != (routing.routing_height.size,) or routing.order.shape != routing.receiver.shape:
        raise ValueError("Invalid routing array shape")
    if routing.outlet_mask.shape != shape or not _m4_drainage_np.array_equal(_m4_drainage_np.sort(routing.order), _m4_drainage_np.arange(routing.receiver.size)):
        raise ValueError("Invalid routing order or outlet mask")
    rank = _m4_drainage_np.empty(routing.receiver.size, dtype=_m4_drainage_np.int64)
    rank[routing.order] = _m4_drainage_np.arange(routing.receiver.size)
    if (routing.receiver < -1).any() or (routing.receiver >= routing.receiver.size).any():
        raise ValueError("Invalid routing receiver index")
    for cell, downstream in enumerate(routing.receiver):
        if (downstream == -1) != bool(routing.outlet_mask.flat[cell]):
            raise ValueError("Routing outlets do not match outlet mask")
        if downstream >= 0 and rank[downstream] >= rank[cell]:
            raise ValueError("Routing receiver must precede donor")
    rain = _m4_drainage_np.asarray(runoff, dtype=_m4_drainage_np.float64)
    extra = _m4_drainage_np.zeros(shape, dtype=_m4_drainage_np.float64) if external_inflow is None else _m4_drainage_np.asarray(external_inflow, dtype=_m4_drainage_np.float64)
    if rain.shape != shape or extra.shape != shape or not _m4_drainage_np.isfinite(rain).all() or not _m4_drainage_np.isfinite(extra).all():
        raise ValueError("runoff and external_inflow must be finite arrays matching routing shape")
    if (rain < 0).any() or (extra < 0).any() or not _m4_drainage_np.isfinite(spacing_blocks) or spacing_blocks <= 0:
        raise ValueError("runoff, inflow, and spacing must be nonnegative and finite")
    if spacing_blocks != routing.spacing_blocks:
        raise ValueError("Accumulation spacing differs from routing spacing")
    local = rain * spacing_blocks ** 2 + extra
    flow = local.ravel().copy()
    if not _m4_drainage_np.isfinite(flow).all():
        raise ValueError("Local discharge overflows float64")
    for current in routing.order[::-1]:
        downstream = routing.receiver[current]
        if downstream >= 0:
            flow[downstream] += flow[current]
    if not _m4_drainage_np.isfinite(flow).all():
        raise ValueError("Accumulated discharge overflows float64")
    discharge = flow.reshape(shape)
    outlets = _m4_drainage_np.where(routing.outlet_mask, discharge, 0.0)
    input_total = float(_m4_drainage_np.sum(local, dtype=_m4_drainage_np.float64))
    outlet_total = float(_m4_drainage_np.sum(outlets, dtype=_m4_drainage_np.float64))
    if not _m4_drainage_np.isfinite(input_total) or not _m4_drainage_np.isfinite(outlet_total):
        raise ValueError("Discharge budget overflows float64")
    return _m4_drainage_AccumulationResult(discharge, outlets, input_total, outlet_total,
                              input_total - outlet_total)

# --- terrain_pipeline/surface_rivers/drainage.py:87 ---
def channel_mask(discharge: _m4_drainage_np.ndarray, threshold_q: float) -> _m4_drainage_np.ndarray:
    """Select channels using an absolute discharge threshold, never tile normalization."""
    flow = _m4_drainage_np.asarray(discharge, dtype=_m4_drainage_np.float64)
    if flow.ndim != 2 or not _m4_drainage_np.isfinite(flow).all() or (flow < 0).any():
        raise ValueError("discharge must be a finite nonnegative 2D array")
    if not _m4_drainage_np.isfinite(threshold_q) or threshold_q <= 0:
        raise ValueError("threshold_q must be finite and positive")
    return flow >= threshold_q

# --- terrain_pipeline/world_disk_water.py:21 ---
@_m4_world_disk_water_njit
def accumulate_with_unknown(order, receiver, ocean, flow, unknown, rows, cols, local):
    n = rows * cols
    for i in range(n):
        row, col = i // cols, i % cols
        flow[i] = 0. if ocean[i] else local
        unknown[i] = not ocean[i] and (row < 6 or col < 6 or row >= rows - 6 or col >= cols - 6)
    for i in range(n - 1, -1, -1):
        cell = order[i]
        target = receiver[cell]
        if target >= 0:
            flow[target] += flow[cell]
            unknown[target] |= unknown[cell]

# --- terrain_pipeline/world_disk_water.py:36 ---
@_m4_world_disk_water_njit
def _propagate_unknown(order, receiver, unknown):
    for i in range(order.size - 1, -1, -1):
        cell = order[i]
        target = receiver[cell]
        if target >= 0 and unknown[cell]:
            unknown[target] = 1

# --- terrain_pipeline/world_disk_water.py:45 ---
@_m4_world_disk_water_njit
def _basin_labels(bed, filled, labels, stack, indptr, indices):
    """Label positive-fill components on the drainage mesh."""
    labels[:] = -1
    count = 0
    for start in range(bed.size):
        if labels[start] >= 0 or filled[start] <= bed[start]:
            continue
        labels[start] = count
        stack[0] = start
        size = 1
        while size:
            size -= 1
            cell = stack[size]
            for edge in range(indptr[cell], indptr[cell + 1]):
                target = indices[edge]
                if labels[target] < 0 and filled[target] > bed[target]:
                    labels[target] = count
                    stack[size] = target
                    size += 1
        count += 1
    return count

# --- terrain_pipeline/world_disk_water.py:68 ---
class _DiskBasinStore:
    """Original-bed prism inventory, evaluated in bounded chunks."""

    def __init__(self, bed, labels, label, minimum, maximum):
        self.bed = bed.ravel()
        self.labels = labels
        self.label = label
        self.minimum = minimum
        self.maximum = maximum

    def volume_at_stage(self, stage):
        total = 0.
        for start in range(0, self.labels.size, 65536):
            section = slice(start, min(start + 65536, self.labels.size))
            selected = self.labels[section] == self.label
            total += float(_m4_world_disk_water_np.maximum(stage - self.bed[section][selected], 0.).sum()) * 900.
        return total

    def stage_at_volume(self, volume):
        if volume <= 0.:
            return self.minimum
        low, high = self.minimum, self.maximum
        for _ in range(60):
            middle = (low + high) * .5
            if self.volume_at_stage(middle) < volume:
                low = middle
            else:
                high = middle
        return (low + high) * .5

# --- terrain_pipeline/world_disk_water.py:99 ---
def _mapped(stack, array):
    stack.callback(array._mmap.close)
    return array

# --- terrain_pipeline/world_disk_water.py:104 ---
def route_disk(height_path, outlets_path, work_dir, *, local_q_m3_s=0., ocean_path=None,
               mesh=None, origin_native_xz=(0, 0), world_seed=20261020):
    """Return working mappings owned by the caller, who must close each mapping."""
    with _m4_world_disk_water_ExitStack() as inputs, _m4_world_disk_water_ExitStack() as outputs:
        result = _route_disk(height_path, outlets_path, work_dir, local_q_m3_s, ocean_path, inputs, outputs,
                             mesh, origin_native_xz, world_seed)
        outputs.pop_all()
        return result

# --- terrain_pipeline/world_disk_water.py:114 ---
def _route_disk(height_path, outlets_path, work_dir, local_q_m3_s, ocean_path, inputs, outputs,
                mesh, origin_native_xz, world_seed):
    bed = _mapped(inputs, _m4_world_disk_water_np.load(height_path, mmap_mode="r", allow_pickle=False))
    outlets = _mapped(inputs, _m4_world_disk_water_np.load(outlets_path, mmap_mode="r", allow_pickle=False))
    if bed.ndim != 2 or bed.dtype != _m4_world_disk_water_np.float64 or outlets.shape != bed.shape or outlets.dtype != _m4_world_disk_water_np.bool_:
        raise ValueError("float64 height and matching boolean outlets required")
    if not _m4_world_disk_water_np.isfinite(bed).all() or not outlets.any() or not _m4_world_disk_water_math.isfinite(local_q_m3_s) or local_q_m3_s < 0.:
        raise ValueError("finite terrain, outlet and nonnegative flow required")
    ocean = _mapped(inputs, _m4_world_disk_water_np.load(ocean_path, mmap_mode="r", allow_pickle=False)) if ocean_path else _m4_world_disk_water_np.zeros(bed.shape, bool)
    if ocean.shape != bed.shape or ocean.dtype != _m4_world_disk_water_np.bool_:
        raise ValueError("matching boolean ocean required")
    work = _m4_world_disk_water_Path(work_dir)
    work.mkdir(parents=True, exist_ok=False)
    n = bed.size
    arrays = {}
    for name, dtype in (("filled", "f8"), ("order", "i8"), ("rank", "i8"), ("heap", "i8"),
                        ("receiver", "i8"), ("flow", "f8"), ("unknown", "u1"),
                        ("basin_label", "i8")):
        arrays[name] = _mapped(outputs, _m4_world_disk_water_np.lib.format.open_memmap(work / (name + ".npy"), mode="w+", dtype=dtype, shape=(n,)))
    if mesh is None:
        mesh = build_mesh(bed.shape, origin_native_xz=origin_native_xz, world_seed=world_seed)
    routing = route_graph(bed, outlets, mesh)
    for name in ("filled", "order", "rank", "receiver"):
        arrays[name][:] = getattr(routing, name).ravel()
    accumulate_with_unknown(arrays["order"], arrays["receiver"], ocean.ravel(), arrays["flow"], arrays["unknown"],
                *bed.shape, local_q_m3_s)
    _basin_labels(bed.ravel(), arrays["filled"], arrays["basin_label"], arrays["heap"],
                  mesh.indptr, mesh.indices)
    for array in arrays.values():
        array.flush()
    return arrays

# --- terrain_pipeline/world_disk_water.py:147 ---
def _solve_disk_region(height_path, ocean_path, work_dir, *, stack, origin_native_xz, world_seed=20261020,
                      runoff_m_per_year, duration_seconds, channel_threshold_m3_s,
                      min_lake_area_m2=10000., sea_level_m=0.):
    """Solve a finite rectangle using disk-backed global routing and basin stores."""
    from terrain_pipeline.common_infra import file_sha256 as _m4_world_disk_water_file_sha256
    from terrain_pipeline.lake import LakeStorage as _m4_world_disk_water_LakeStorage
    from terrain_pipeline.lake import MAX_LAKE_CELLS as _m4_world_disk_water_MAX_LAKE_CELLS
    from terrain_pipeline.geology import sample_lithology_points as _m4_world_disk_water_sample_lithology_points
    from terrain_pipeline.surface_hydraulics import transfer_basins as _m4_world_disk_water_transfer_basins
    from terrain_pipeline.world_irregular_channels import build_irregular_channel_geometry

    if (len(origin_native_xz) != 2 or any(type(v) is not int for v in origin_native_xz)
            or not _m4_world_disk_water_math.isfinite(runoff_m_per_year) or runoff_m_per_year < 0.
            or not _m4_world_disk_water_math.isfinite(duration_seconds) or duration_seconds <= 0.
            or not _m4_world_disk_water_math.isfinite(channel_threshold_m3_s) or channel_threshold_m3_s <= 0.
            or not _m4_world_disk_water_math.isfinite(min_lake_area_m2) or min_lake_area_m2 <= 0.
            or not _m4_world_disk_water_math.isfinite(sea_level_m)):
        raise ValueError("invalid finite region or forcing")
    bed = _mapped(stack, _m4_world_disk_water_np.load(height_path, mmap_mode="r", allow_pickle=False))
    ocean = _mapped(stack, _m4_world_disk_water_np.load(ocean_path, mmap_mode="r", allow_pickle=False))
    if bed.ndim != 2 or min(bed.shape) < 4 or ocean.shape != bed.shape or ocean.dtype != _m4_world_disk_water_np.bool_:
        raise ValueError("matching finite 2D terrain and ocean required")
    if _m4_world_disk_water_np.any(bed[ocean] > sea_level_m):
        raise ValueError("ocean bed exceeds sea level")
    root = _m4_world_disk_water_Path(work_dir)
    root.mkdir(parents=True, exist_ok=False)
    rows, cols = bed.shape
    outlets = _mapped(stack, _m4_world_disk_water_np.lib.format.open_memmap(root / "outlets.npy", mode="w+", dtype=_m4_world_disk_water_np.bool_, shape=bed.shape))
    outlets[:] = ocean
    outlets[[0, -1], :] = True
    outlets[:, [0, -1]] = True
    outlets.flush()
    mesh = build_mesh(bed.shape, origin_native_xz=origin_native_xz, world_seed=world_seed)
    local = float(runoff_m_per_year) * 900. / (365.25 * 86400.)
    arrays = route_disk(height_path, root / "outlets.npy", root / "routing", local_q_m3_s=local, ocean_path=ocean_path, mesh=mesh)
    for value in arrays.values():
        _mapped(stack, value)
    labels = arrays["basin_label"]
    filled = arrays["filled"]
    original_receiver = _mapped(stack, _m4_world_disk_water_np.lib.format.open_memmap(root / "spill_receiver_work.npy", mode="w+", dtype=_m4_world_disk_water_np.int64,
                                                   shape=(bed.size,)))
    original_receiver[:] = arrays["receiver"]
    original_receiver.flush()
    basin_count = int(labels.max()) + 1
    counts = _m4_world_disk_water_np.zeros(basin_count, _m4_world_disk_water_np.int64)
    for start in range(0, bed.size, 65536):
        values = labels[start:min(start + 65536, bed.size)]
        counts += _m4_world_disk_water_np.bincount(values[values >= 0], minlength=basin_count)
    basin_ids = [int(i) for i in range(basin_count) if counts[i] * 900. >= min_lake_area_m2]
    raw_catchments = certify_raw_catchments(bed, labels.reshape(bed.shape), root / "raw-catchment", mesh=mesh)
    for start in range(0, bed.size, 65536):
        section = slice(start, min(start + 65536, bed.size))
        outlets.ravel()[section] |= _m4_world_disk_water_np.isin(labels[section], basin_ids)
    outlets.flush()
    spill_arrays = arrays
    arrays = route_disk(height_path, root / "outlets.npy", root / "local-routing", local_q_m3_s=local, ocean_path=ocean_path, mesh=mesh)
    for value in arrays.values():
        _mapped(stack, value)
    receiver = arrays["receiver"]
    geometry_receiver = _m4_world_disk_water_np.array(receiver, copy=True)
    for start in range(0, bed.size, 65536):
        section = slice(start, min(start + 65536, bed.size))
        targets = receiver[section]
        into_ocean = (targets >= 0) & ocean.ravel()[_m4_world_disk_water_np.maximum(targets, 0)]
        targets[into_ocean] = -1
    accumulate_with_unknown(arrays["order"], receiver, ocean.ravel(), arrays["flow"], arrays["unknown"], rows, cols, local)
    basins, stores, paths = [], {}, {}
    source_sha = _m4_world_disk_water_file_sha256(height_path)
    for label in basin_ids:
        cells = _mapped(stack, _m4_world_disk_water_np.lib.format.open_memmap(root / ("members-%d.npy" % label), mode="w+", dtype=_m4_world_disk_water_np.int64,
                                         shape=(int(counts[label]),)))
        position = 0
        for start in range(0, bed.size, 65536):
            indices = _m4_world_disk_water_np.flatnonzero(labels[start:min(start + 65536, bed.size)] == label) + start
            cells[position:position + indices.size] = indices
            position += indices.size
        beds = _mapped(stack, _m4_world_disk_water_np.lib.format.open_memmap(root / ("beds-%d.npy" % label), mode="w+", dtype=_m4_world_disk_water_np.float64,
                                        shape=(cells.size,)))
        for start in range(0, cells.size, 65536):
            section = slice(start, min(start + 65536, cells.size))
            beds[section] = bed.ravel()[cells[section]]
        spill = float(filled[cells].max())
        rim_clear = min(int((cells // cols).min()), int((cells % cols).min()),
                        int(rows - 1 - (cells // cols).max()), int(cols - 1 - (cells % cols).max()))
        raw = raw_catchments[label]
        rim_clear -= 1
        complete = (rim_clear >= 6 and not arrays["unknown"][cells].any()
                    and raw["unknown_cells"] == 0 and raw["leaked_cells"] == 0)
        exits = [int(original_receiver[c]) for c in cells if original_receiver[c] >= 0
                 and labels[original_receiver[c]] != label and abs(filled[original_receiver[c]] - spill) <= 1e-9]
        complete = complete and float(filled[cells].max() - filled[cells].min()) <= 1e-9
        if exits:
            complete = complete and all(min(exit_cell // cols, exit_cell % cols,
                rows - 1 - exit_cell // cols, cols - 1 - exit_cell % cols) >= 6 for exit_cell in exits)
        path = []
        target = None
        if exits:
            current = min(exits, key=lambda c: (int(spill_arrays["rank"][c]), c))
            while current >= 0:
                path.append(current)
                next_label = int(labels[current])
                if next_label in basin_ids or ocean.ravel()[current]:
                    if next_label in basin_ids:
                        target = next_label
                    break
                current = int(original_receiver[current])
        else:
            complete = False
        if cells.size <= _m4_world_disk_water_MAX_LAKE_CELLS:
            store = _m4_world_disk_water_LakeStorage(cell_ids=_m4_world_disk_water_np.array(cells, dtype=_m4_world_disk_water_np.int64), bed_elevation_m=_m4_world_disk_water_np.array(beds),
                cell_area_m2=_m4_world_disk_water_np.full(cells.size, 900., _m4_world_disk_water_np.float64), seed_cell_id=int(cells[_m4_world_disk_water_np.argmin(beds)]),
                max_stage_m=spill + 1., source_identity_sha256=source_sha,
                footprint_policy="joint region positive-fill component")
        else:
            store = _DiskBasinStore(bed, labels, label, float(beds.min()), spill)
        stores[label] = store
        paths[label] = path
        destination = "lake" if target is not None else "ocean" if path and ocean.ravel()[path[-1]] else "unknown"
        basins.append({"label": label, "local_m3": float(arrays["flow"][cells].sum()) * duration_seconds,
                       "capacity_m3": store.volume_at_stage(spill), "downstream": target,
                       "destination": destination, "complete": bool(complete),
                       "raw_unknown_cells": raw["unknown_cells"], "raw_leaked_cells": raw["leaked_cells"],
                       "rim_clearance_cells": rim_clear,
                       "filled_level_range_m": float(filled[cells].max() - filled[cells].min())})
        cells._mmap.close()
        beds._mmap.close()
    spill_seen = _mapped(stack, _m4_world_disk_water_np.lib.format.open_memmap(root / "spill_unknown_work.npy", mode="w+", dtype=_m4_world_disk_water_np.uint8, shape=(bed.size,)))
    while True:
        settled = _m4_world_disk_water_transfer_basins(basins)
        for basin in basins:
            if settled[basin["label"]]["complete"]:
                continue
            members = _mapped(stack, _m4_world_disk_water_np.load(root / ("members-%d.npy" % basin["label"]), mmap_mode="r"))
            for cell in members:
                current = int(original_receiver[cell])
                while current >= 0 and not ocean.ravel()[current] and not spill_seen[current]:
                    spill_seen[current] = 1
                    arrays["unknown"][current] = 1
                    current = int(original_receiver[current])
            members._mmap.close()
        _propagate_unknown(arrays["order"], receiver, arrays["unknown"])
        changed = False
        for basin in basins:
            members = _mapped(stack, _m4_world_disk_water_np.load(root / ("members-%d.npy" % basin["label"]), mmap_mode="r"))
            has_unknown = False
            for start in range(0, members.size, 65536):
                if arrays["unknown"][members[start:start + 65536]].any():
                    has_unknown = True
                    break
            members._mmap.close()
            if basin["complete"] and has_unknown:
                basin["complete"] = False
                changed = True
        if not changed:
            break
    output_names = ("bed_before_m", "ocean_mask", "channel_mask", "protected_shore_mask", "water_surface_m", "lake_mask", "pending_basin_mask", "spill_routed_volume_m3",
                    "spill_edge_volume_m3", "lake_support_mask", "complete_mask", "known_q_m3_s",
                    "channel_width_m", "design_incision_depth_m", "cut_depth_m", "final_bed_m",
                    "bed_hardness", "bank_hardness", "representative_q_m3_s")
    output = {}
    for name in output_names:
        dtype = _m4_world_disk_water_np.bool_ if name in ("ocean_mask", "channel_mask", "protected_shore_mask", "lake_mask", "pending_basin_mask", "lake_support_mask", "complete_mask") else _m4_world_disk_water_np.float64
        output[name] = _mapped(stack, _m4_world_disk_water_np.lib.format.open_memmap(root / (name + ".npy"), mode="w+", dtype=dtype, shape=bed.shape))
    output["water_surface_m"][:] = _m4_world_disk_water_np.nan
    output["complete_mask"][:] = ~arrays["unknown"].reshape(bed.shape).astype(bool)
    output["water_surface_m"][ocean] = sea_level_m
    links = []
    for basin in basins:
        label = basin["label"]
        result = settled[label]
        cells = _mapped(stack, _m4_world_disk_water_np.load(root / ("members-%d.npy" % label), mmap_mode="r"))
        if not result["complete"]:
            output["pending_basin_mask"].ravel()[cells] = True
            output["complete_mask"].ravel()[paths[label]] = False
        else:
            output["lake_support_mask"].ravel()[cells] = True
            stage = stores[label].stage_at_volume(result["stored_m3"])
            wet = cells[bed.ravel()[cells] < stage]
            output["lake_mask"].ravel()[wet] = True
            output["water_surface_m"].ravel()[wet] = stage
            output["spill_routed_volume_m3"].ravel()[paths[label]] += result["outflow_m3"]
            output["spill_edge_volume_m3"].ravel()[paths[label][:-1]] += result["outflow_m3"]
        reason = None if result["complete"] else ("raw_catchment_unknown_or_leaked" if basin["raw_unknown_cells"] or basin["raw_leaked_cells"] else "incomplete_support_or_upstream")
        seed = int(cells[_m4_world_disk_water_np.argmin(bed.ravel()[cells])])
        links.append({**basin, **result, "pending_reason": reason, "reason": reason,
                      "lake_exit_source_node": min((int(cell) for cell in cells if paths[label] and original_receiver[cell] == paths[label][0]), default=None),
                      "status": ("lake" if result["stored_m3"] > 0. else "dry") if result["complete"] else "pending",
                      "water_surface_m": float(stage) if result["complete"] and result["stored_m3"] > 0. else None,
                      "seed_rc": [seed // cols, seed % cols], "area_m2": int(cells.size) * 900.,
                      "path_flat": paths[label]})
        cells._mmap.close()
    from scipy.ndimage import binary_dilation
    q = arrays["flow"].reshape(bed.shape) + output["spill_routed_volume_m3"] / duration_seconds
    pending = ~output["complete_mask"] | output["pending_basin_mask"]
    shore = binary_dilation(output["lake_support_mask"] | output["pending_basin_mask"],
                            structure=_m4_world_disk_water_np.ones((3, 3), bool), iterations=2)
    channel = (~ocean & ~output["lake_support_mask"] & ~output["pending_basin_mask"]
               & ~pending & (q >= channel_threshold_m3_s))
    x = (origin_native_xz[0] + _m4_world_disk_water_np.arange(cols))[None, :] * 30.
    z = (origin_native_xz[1] + _m4_world_disk_water_np.arange(rows))[:, None] * 30.
    rock = _m4_world_disk_water_sample_lithology_points(x, z, world_seed=world_seed)
    geometry = build_irregular_channel_geometry(bed, q, channel, mesh, geometry_receiver,
        bed_hardness=rock["bed_hardness"], bank_hardness=rock["bank_hardness"],
        protected_mask=ocean | shore | pending, complete_mask=output["complete_mask"],
        lake_mask=output["lake_support_mask"], ocean_mask=ocean)
    geom = geometry["arrays"]
    for name in ("channel_width_m", "cut_depth_m", "bed_hardness", "bank_hardness"):
        output[name][:] = geom[name]
    output["design_incision_depth_m"][:] = geom["channel_depth_m"]
    output["bed_before_m"][:] = bed
    output["ocean_mask"][:] = ocean
    output["channel_mask"][:] = channel
    output["protected_shore_mask"][:] = shore
    output["representative_q_m3_s"][:] = _m4_world_disk_water_np.where(pending | ocean, _m4_world_disk_water_np.nan, q)
    output["known_q_m3_s"][:] = q
    original_cut = output["cut_depth_m"].copy()
    if ocean.any():
        eligible = ~ocean & (bed >= sea_level_m)
        output["cut_depth_m"][eligible] = _m4_world_disk_water_np.minimum(output["cut_depth_m"][eligible], bed[eligible] - sea_level_m)
    output["final_bed_m"][:] = bed - output["cut_depth_m"]
    geometry["metadata"]["sea_level_cut_limit"] = {
        "enabled": bool(ocean.any()),
        "limited_cells": int(_m4_world_disk_water_np.count_nonzero(output["cut_depth_m"] < original_cut)),
        "avoided_cut_bulk_m3": float((original_cut - output["cut_depth_m"]).sum()) * 900.}
    removed = float(output["cut_depth_m"].sum()) * 900.
    geometry["metadata"]["material_budget"].update({
        "coarse_raster_edit_bulk_m3": removed, "removed_terrain_bulk_m3": removed,
        "unplaced_excavated_bulk_m3": removed})
    network_path = root / "river-network.npz"
    spill_volume = output["spill_edge_volume_m3"].ravel()
    spill_sources = _m4_world_disk_water_np.flatnonzero((spill_volume > 0.) & (original_receiver >= 0))
    lake_exits = [link for link in links if link["lake_exit_source_node"] is not None
                  and link["outflow_m3"] is not None and link["outflow_m3"] > 0.]
    edge_sources = _m4_world_disk_water_np.concatenate((spill_sources,
        _m4_world_disk_water_np.asarray([link["lake_exit_source_node"] for link in lake_exits], dtype=_m4_world_disk_water_np.int64)))
    edge_targets = _m4_world_disk_water_np.concatenate((_m4_world_disk_water_np.asarray(original_receiver[spill_sources]),
        _m4_world_disk_water_np.asarray([link["path_flat"][0] for link in lake_exits], dtype=_m4_world_disk_water_np.int64)))
    edge_volumes = _m4_world_disk_water_np.concatenate((_m4_world_disk_water_np.asarray(spill_volume[spill_sources]),
        _m4_world_disk_water_np.asarray([link["outflow_m3"] for link in lake_exits], dtype=_m4_world_disk_water_np.float64)))
    geometry["graph"].update(spill_source_node=edge_sources,
        spill_target_node=edge_targets, spill_volume_m3=edge_volumes)
    geometry["graph_metadata"].update(
        schema="irregular-river-network-v1", node_count=bed.size,
        reach_count=int(geometry["graph"]["reach_source"].size),
        active_spill_edge_count=int(edge_sources.size),
        spill_semantics="positive finite actual outflow edges; basin boundary edge identified by transfer link lake_exit_source_node",
        lake_exit_semantics="lake control-cell node to first exterior node; source bed is protected, no invented shoreline sample")
    _m4_world_disk_water_np.savez(network_path, **geometry["graph"])
    for value in output.values():
        value.flush()
    production = terminal_volume = ocean_terminal_volume = 0.
    for start in range(0, bed.size, 65536):
        section = slice(start, min(start + 65536, bed.size))
        is_ocean = ocean.ravel()[section]
        terminal = (receiver[section] < 0) & ~_m4_world_disk_water_np.isin(labels[section], basin_ids)
        flow = arrays["flow"][section]
        production += float((~is_ocean).sum()) * local * duration_seconds
        terminal_volume += float(flow[terminal].sum()) * duration_seconds
        spill_targets = original_receiver[section]
        coastal = (spill_targets >= 0) & ocean.ravel()[_m4_world_disk_water_np.maximum(spill_targets, 0)]
        ocean_terminal_volume += float(flow[terminal & (is_ocean | coastal)].sum()) * duration_seconds
    stored = sum(b["stored_m3"] or 0. for b in links)
    pending_volume = sum(b["inflow_m3"] for b in links if not b["complete"])
    spill_terminal = sum(b["outflow_m3"] or 0. for b in links if b["downstream"] is None)
    ledger = {"local_production_m3": production, "lake_stored_m3": stored,
              "pending_known_inflow_m3": pending_volume, "local_terminal_m3": terminal_volume,
              "spill_terminal_m3": spill_terminal,
              "residual_m3": production - stored - pending_volume - terminal_volume - spill_terminal}
    ledger["local_terminal_ocean_m3"] = ocean_terminal_volume
    ledger["local_terminal_unknown_m3"] = terminal_volume - ledger["local_terminal_ocean_m3"]
    ledger["spill_terminal_ocean_m3"] = sum(b["outflow_m3"] or 0. for b in links if b["downstream"] is None and b["destination"] == "ocean")
    ledger["spill_terminal_unknown_m3"] = spill_terminal - ledger["spill_terminal_ocean_m3"]
    fields = {name: name + ".npy" for name in output_names}
    for name, data in (("receiver", receiver), ("basin_label", labels),
                       ("node_x_m", mesh.node_x_m), ("node_z_m", mesh.node_z_m),
                       ("routing_elevation_m", arrays["filled"]), ("upstream_unknown_mask", arrays["unknown"].astype(bool)),
                       ("local_routed_q_m3_s", arrays["flow"]), ("spill_receiver", original_receiver)):
        field = _mapped(stack, _m4_world_disk_water_np.lib.format.open_memmap(root / (name + ".npy"), mode="w+", dtype=data.dtype, shape=bed.shape))
        field[:] = data.reshape(bed.shape)
        field.flush()
        field._mmap.close()
        fields[name] = name + ".npy"
    for name, data in (("receiver", receiver), ("spill_receiver", original_receiver)):
        for coordinate in ("x", "z"):
            field_name = name + "_native_" + coordinate
            field = _mapped(stack, _m4_world_disk_water_np.lib.format.open_memmap(root / (field_name + ".npy"), mode="w+", dtype=_m4_world_disk_water_np.int64, shape=bed.shape))
            for start in range(0, bed.size, 65536):
                section = slice(start, min(start + 65536, bed.size))
                target = data[section]
                value = target % cols + origin_native_xz[0] if coordinate == "x" else target // cols + origin_native_xz[1]
                field.ravel()[section] = _m4_world_disk_water_np.where(target >= 0, value, -1)
            field.flush()
            field._mmap.close()
            fields[field_name] = field_name + ".npy"
    manifest = {"schema": "world-disk-water-v2", "algorithm": "irregular-delaunay-static-fill-spill-v1",
                "origin_native_xz": list(origin_native_xz),
                "shape_zx": list(bed.shape), "world_seed": world_seed, "sea_level_m": sea_level_m, "basins": links,
                "basin_transfer_links": [{"source_label": link["label"], "target_label": link["downstream"],
                    "path_flat": link["path_flat"], "volume_m3": link["outflow_m3"],
                    "lake_exit_source_node": link["lake_exit_source_node"],
                    "destination": link["destination"]} for link in links],
                "water_ledger": ledger, "source_sha256": source_sha,
                "ocean_sha256": _m4_world_disk_water_file_sha256(ocean_path), "runoff_m_per_year": runoff_m_per_year,
                "duration_seconds": duration_seconds, "channel_threshold_m3_s": channel_threshold_m3_s,
                "scope": "finite joint rectangle; unresolved upstream remains pending",
                "cell_account_area_m2": 900.,
                "terrain_sampling": "one native control-cell representative elevation per displaced graph node",
                "unknown_boundary_band_cells": 6,
                "basin_certification": "global fill constancy, exit and rim clearance, raw catchment and local routed unknown",
                "min_lake_area_m2": min_lake_area_m2,
                "geometry_policy": "continuous irregular graph segments with cross-section incision; lake shore protected; ocean floor",
                "geometry": geometry["metadata"],
                "material_budget": {"coarse_raster_edit_bulk_m3": float(output["cut_depth_m"].sum()) * 900.},
                "spill_exit_policy": "eligible actual basin exit, lowest flood rank then row-major index",
                "field_sha256": {name: _m4_world_disk_water_file_sha256(root / path) for name, path in fields.items()}}
    result = {"fields": fields, "metadata": manifest,
              "network": {"file": network_path.name, "sha256": _m4_world_disk_water_file_sha256(network_path),
                          "metadata": geometry["graph_metadata"]}}
    (root / "manifest.json").write_text(_m4_world_disk_water_json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result

# --- terrain_pipeline/world_disk_water.py:464 ---
def solve_disk_region(height_path, ocean_path, work_dir, *, origin_native_xz, world_seed=20261020,
                      runoff_m_per_year, duration_seconds, channel_threshold_m3_s,
                      min_lake_area_m2=10000., sea_level_m=0.):
    with _m4_world_disk_water_ExitStack() as stack:
        return _solve_disk_region(height_path, ocean_path, work_dir, stack=stack, origin_native_xz=origin_native_xz,
            world_seed=world_seed, runoff_m_per_year=runoff_m_per_year, duration_seconds=duration_seconds,
            channel_threshold_m3_s=channel_threshold_m3_s, min_lake_area_m2=min_lake_area_m2,
            sea_level_m=sea_level_m)

# --- terrain_pipeline/world_disk_catchment.py:11 ---
@_m4_world_disk_catchment_njit
def _assign(bed, labels, owner, stack, indptr, indices, lengths):
    for start in range(bed.size):
        if owner[start] != -2:
            continue
        current = start
        count = 0
        while owner[current] == -2:
            stack[count] = current
            count += 1
            best = 0.0
            target = -1
            for edge in range(indptr[current], indptr[current + 1]):
                neighbour = indices[edge]
                slope = (bed[current] - bed[neighbour]) / lengths[edge]
                if slope > best or (slope == best and slope > 0. and neighbour < target):
                    best = slope
                    target = neighbour
            if target < 0:
                owner[current] = labels[current]
                break
            current = target
        root = owner[current]
        while count:
            count -= 1
            owner[stack[count]] = root

# --- terrain_pipeline/world_disk_catchment.py:39 ---
@_m4_world_disk_catchment_njit
def _counts(labels, owner, rows, cols, unknown, leaked):
    for cell in range(rows * cols):
        label = labels[cell]
        if label >= 0 and owner[cell] != label:
            leaked[label] += 1
        row, col = cell // cols, cell % cols
        root = owner[cell]
        if root >= 0 and (row < 6 or col < 6 or row >= rows - 6 or col >= cols - 6):
            unknown[root] += 1

# --- terrain_pipeline/world_disk_catchment.py:50 ---
def certify_raw_catchments(bed, labels, work_dir, *, mesh=None):
    """Return native-lake raw catchment unknown/leak counts for each label.

    Uses disk-backed owner and traversal-stack arrays. Labels must be dense
    nonnegative integers (or -1 outside basins), matching the basin label grid.
    Input arrays remain open and untouched; all internally opened maps close.
    """
    terrain = _m4_world_disk_catchment_np.asarray(bed)
    basin = _m4_world_disk_catchment_np.asarray(labels)
    if (terrain.ndim != 2 or terrain.dtype != _m4_world_disk_catchment_np.float64 or basin.shape != terrain.shape or
            basin.dtype.kind not in "iu" or not _m4_world_disk_catchment_np.isfinite(terrain).all()):
        raise ValueError("finite float64 terrain and matching integer labels required")
    if basin.dtype.kind == "u" or _m4_world_disk_catchment_np.any(basin < -1):
        raise ValueError("labels must be signed integers with -1 for non-basin cells")
    ids = _m4_world_disk_catchment_np.unique(basin[basin >= 0])
    if ids.size and not _m4_world_disk_catchment_np.array_equal(ids, _m4_world_disk_catchment_np.arange(ids.size)):
        raise ValueError("basin labels must be dense from zero")
    if mesh is None:
        mesh = build_mesh(terrain.shape)
    if mesh.shape != terrain.shape:
        raise ValueError("mesh must match terrain shape")
    directory = _m4_world_disk_catchment_Path(work_dir)
    directory.mkdir(parents=True, exist_ok=False)
    owner = stack = None
    try:
        owner = _m4_world_disk_catchment_np.lib.format.open_memmap(directory / "raw-owner.npy", mode="w+",
                                          dtype=_m4_world_disk_catchment_np.int64, shape=(terrain.size,))
        stack = _m4_world_disk_catchment_np.lib.format.open_memmap(directory / "raw-stack.npy", mode="w+",
                                          dtype=_m4_world_disk_catchment_np.int64, shape=(terrain.size,))
        owner[:] = -2
        _assign(terrain.ravel(), basin.ravel(), owner, stack, mesh.indptr, mesh.indices, mesh.edge_length_m)
        unknown = _m4_world_disk_catchment_np.zeros(ids.size, dtype=_m4_world_disk_catchment_np.int64)
        leaked = _m4_world_disk_catchment_np.zeros(ids.size, dtype=_m4_world_disk_catchment_np.int64)
        _counts(basin.ravel(), owner, *terrain.shape, unknown, leaked)
        owner.flush()
        return {int(label): {"unknown_cells": int(unknown[label]),
                             "leaked_cells": int(leaked[label])} for label in ids}
    finally:
        for array in (owner, stack):
            if array is not None:
                array._mmap.close()

# --- terrain_pipeline/native_product_invariants.py:5 ---
def check_routing(order, receiver, valid):
    """Return a dict of violations; empty 'errors' means the routing is consistent.

    order: valid cells with each receiver BEFORE its sources (downstream first; verified on
    native-final-routing-v1, where all receivers have smaller rank than their source).
    receiver: downstream cell index per cell, -1 for none.
    valid: boolean mask over all cells.
    """
    order = _m4_native_product_invariants_np.asarray(order)
    receiver = _m4_native_product_invariants_np.asarray(receiver)
    valid = _m4_native_product_invariants_np.asarray(valid).ravel().astype(bool)
    errors = []
    n = valid.size
    result = dict(cells=int(n), valid_cells=int(valid.sum()), order_size=int(order.size))
    negative = int(_m4_native_product_invariants_np.count_nonzero(order < 0))
    result['order_negative'] = negative
    if negative:
        errors.append('order contains %d negative entries (unfilled -1 tail)' % negative)
    if int(order.size) != int(valid.sum()):
        errors.append('order size %d != valid cell count %d' % (order.size, int(valid.sum())))
    in_range = order[(order >= 0) & (order < n)]
    if in_range.size != order.size - negative:
        errors.append('order has entries >= n')
    rank = _m4_native_product_invariants_np.full(n, -1, dtype='i8')
    if not negative and in_range.size == order.size:
        if _m4_native_product_invariants_np.unique(in_range).size != in_range.size:
            errors.append('order has duplicate cells')
        elif not _m4_native_product_invariants_np.all(valid[in_range]):
            errors.append('order contains invalid cells')
        else:
            rank[in_range] = _m4_native_product_invariants_np.arange(in_range.size)
            if int(_m4_native_product_invariants_np.count_nonzero(valid & (rank < 0))):
                errors.append('valid cells missing from order')
    if not errors:
        target = receiver[order]
        has = target >= 0
        if _m4_native_product_invariants_np.any(target[has] >= n):
            errors.append('receiver index out of range')
        else:
            src_rank = _m4_native_product_invariants_np.arange(order.size)[has]
            tgt_rank = rank[target[has]]
            bad = int(_m4_native_product_invariants_np.count_nonzero(tgt_rank >= src_rank))
            result['receiver_not_downstream'] = bad
            if bad:
                errors.append('%d receivers do not precede their source in order' % bad)
    result['errors'] = errors
    result['ok'] = not errors
    return result

# --- terrain_pipeline/native_product_invariants.py:55 ---
def check_event_budget(manifest, rtol=1e-9):
    """Check per-interval water budgets in an event manifest dict."""
    errors = []
    budgets = manifest.get('budgets')
    if budgets is None:
        budgets = [dict(local_m3=manifest.get('local_m3'), retained_m3=manifest.get('retained_m3'), terminal_m3=manifest.get('terminal_m3'), residual_m3=manifest.get('residual_m3'))]
    rows = []
    for i, b in enumerate(budgets):
        local = b.get('local_m3')
        residual = b.get('residual_m3')
        if local is None or residual is None:
            errors.append('interval %d lacks local_m3/residual_m3' % i)
            continue
        ratio = abs(residual) / local if local else float('inf') if residual else 0.
        rows.append(dict(interval=i, local_m3=local, residual_m3=residual, relative=ratio))
        if not _m4_native_product_invariants_np.isfinite(local) or not _m4_native_product_invariants_np.isfinite(residual):
            errors.append('interval %d non-finite' % i)
        elif abs(residual) > rtol * abs(local):
            errors.append('interval %d |residual| %.6g exceeds %.1e x local %.6g' % (i, abs(residual), rtol, local))
        for key in ('retained_m3', 'terminal_m3'):
            value = b.get(key)
            if value is not None and not (value >= 0):
                errors.append('interval %d %s negative or NaN: %r' % (i, key, value))
    return dict(intervals=rows, errors=errors, ok=not errors, rtol=rtol)

# --- terrain_pipeline/real_dem_flat_routing.py:17 ---
FLAT_ALGORITHM = "real-dem-equal-irregular-multisource-bfs-closed-min-root-v2"

# --- terrain_pipeline/real_dem_flat_routing.py:18 ---
POLICY = {"algorithm": FLAT_ALGORITHM, "equal_height": "exact_float_equality",
          "flat_receiver_tie": "minimum_global_cell_id", "closed_component": "retain_at_minimum_cell_root",
          "order": "Kahn_FIFO_initial_zero_indegree_sorted_global_id",
          "global_graph_state": True, "terrain_filling": False,
          "natural_outlet_verified": False, "ocean_outlet_certified": False}

# --- terrain_pipeline/real_dem_flat_routing.py:25 ---
def dense_neighbors(shape, mesh=None, valid=None):
    mesh = grid_mesh(shape, dx_m=90.) if mesh is None else mesh
    if valid is not None:
        mesh = masked_mesh(mesh, valid)
    degree = _m4_real_dem_flat_routing_np.diff(mesh.indptr)
    neighbors = _m4_real_dem_flat_routing_np.full((int(_m4_real_dem_flat_routing_np.prod(shape)), max(1, int(degree.max()))), -1, _m4_real_dem_flat_routing_np.int64)
    for node in range(neighbors.shape[0]):
        neighbors[node, :degree[node]] = mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]
    return neighbors

# --- terrain_pipeline/real_dem_flat_routing.py:36 ---
def _equal_neighbors(neighbors, height, valid):
    safe = _m4_real_dem_flat_routing_np.maximum(neighbors, 0)
    equal = (neighbors >= 0) & valid[safe] & valid[:, None] & (height[safe] == height[:, None])
    return _m4_real_dem_flat_routing_np.where(equal, neighbors, -1)

# --- terrain_pipeline/real_dem_flat_routing.py:42 ---
def _risks(neighbors, valid, shape):
    unknown = _m4_real_dem_flat_routing_np.any((neighbors >= 0) & ~valid[_m4_real_dem_flat_routing_np.maximum(neighbors, 0)], axis=1)
    boundary = _m4_real_dem_flat_routing_np.zeros(shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    return boundary.ravel(), unknown

# --- terrain_pipeline/real_dem_flat_routing.py:50 ---
def _order(receiver, valid):
    ids = _m4_real_dem_flat_routing_np.flatnonzero(valid)
    targets = receiver[ids]
    indegree = _m4_real_dem_flat_routing_np.bincount(targets[targets >= 0], minlength=len(valid))
    queue = _m4_real_dem_flat_routing_deque(ids[indegree[ids] == 0].tolist())
    order = []
    while queue:
        source = queue.popleft()
        order.append(source)
        target = int(receiver[source])
        if target >= 0:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(order) != len(ids):
        raise ValueError("receiver cycle")
    return _m4_real_dem_flat_routing_np.asarray(order, _m4_real_dem_flat_routing_np.int64)

# --- terrain_pipeline/real_dem_flat_routing.py:69 ---
def accumulate_forward_unit(receiver, order, valid):
    accumulation = _m4_real_dem_flat_routing_np.zeros(len(valid), _m4_real_dem_flat_routing_np.float64)
    accumulation[valid] = 1.
    for source in order:
        target = receiver[source]
        if target >= 0:
            accumulation[target] += accumulation[source]
    return accumulation

# --- terrain_pipeline/real_dem_flat_routing.py:79 ---
def _record(component_id, cells, seeds, height, boundary, unknown, shape, distance):
    cell_rows, cell_cols = _m4_real_dem_flat_routing_np.divmod(cells, shape[1])
    closed = len(seeds) == 0
    return {"component_id": component_id, "height_m": float(height[cells[0]]), "cell_count": len(cells),
            "row_col_bounds": [int(cell_rows.min()), int(cell_rows.max()) + 1,
                               int(cell_cols.min()), int(cell_cols.max()) + 1],
            "exit_seed_cell_ids": sorted(map(int, seeds)), "root_cell_id": component_id if closed else None,
            "classification": "closed_flat_retention" if closed else "draining_equal_height_component",
            "touches_boundary": bool(boundary[cells].any()), "touches_unknown": bool(unknown[cells].any()),
            "max_distance_to_exit": int(distance[cells].max()),
            "distance_reference": "retention_root_not_observed_outlet" if closed else "nearest_strict_downhill_seed",
            "natural_outlet_verified": False, "ocean_outlet_certified": False}

# --- terrain_pipeline/real_dem_flat_routing.py:93 ---
def flat_summary(height_array, valid, raw, receiver, accumulation, records):
    from terrain_pipeline.artifacts.contracts import array_hash as _m4_real_dem_flat_routing_array_hash
    ids = _m4_real_dem_flat_routing_np.flatnonzero(valid)
    targets = receiver[ids]
    routed = targets >= 0
    height = height_array.ravel()
    strict = int(_m4_real_dem_flat_routing_np.count_nonzero(height[targets[routed]] < height[ids[routed]]))
    terminals = ids[targets == -1]
    return {"raw_terminals": int(_m4_real_dem_flat_routing_np.count_nonzero(raw[ids] == -1)), "resolved_terminals": len(terminals),
            "flat_rerouted_edges": int(_m4_real_dem_flat_routing_np.count_nonzero(receiver[ids] != raw[ids])),
            "strict_downhill_edges": strict, "flat_edges": int(routed.sum()) - strict,
            "closed_component_count": sum(record["root_cell_id"] is not None for record in records),
            "draining_component_count": sum(record["root_cell_id"] is None for record in records),
            "valid_cells": len(ids), "unknown_cells": int((~valid).sum()),
            "contributing_cells_sum": int(accumulation[terminals].sum()),
            "source_height_sha256": _m4_real_dem_flat_routing_array_hash(height_array), "source_height_unchanged": True,
            "algorithm_metadata": dict(POLICY), "natural_outlet_verified": False, "ocean_outlet_certified": False}

# --- terrain_pipeline/real_dem_flat_routing.py:111 ---
def resolve_dem_flats(candidate, *, tile_size=256, tile_order="row_major") -> dict:
    from terrain_pipeline.artifacts.contracts import array_hash as _m4_real_dem_flat_routing_array_hash
    height_array, valid_array = arrays_from_candidate(candidate)
    before = _m4_real_dem_flat_routing_array_hash(height_array)
    raw_network = build_tiled_network(candidate, tile_size=tile_size, tile_order=tile_order)
    height, valid = height_array.ravel(), valid_array.ravel()
    raw = raw_network.receiver.ravel()
    mesh = raw_network.mesh
    neighbors = dense_neighbors(height_array.shape, mesh)
    equal_neighbors = _equal_neighbors(dense_neighbors(height_array.shape, mesh, valid_array), height, valid)
    boundary, unknown = _risks(neighbors, valid, height_array.shape)
    component = _m4_real_dem_flat_routing_np.full(height.size, -1, _m4_real_dem_flat_routing_np.int64)
    distance = _m4_real_dem_flat_routing_np.full(height.size, -1, _m4_real_dem_flat_routing_np.int64)
    receiver = raw.copy()
    records = []
    for start in _m4_real_dem_flat_routing_np.flatnonzero(valid):
        if component[start] >= 0:
            continue
        component[start] = start
        queue = _m4_real_dem_flat_routing_deque([int(start)])
        cells = []
        while queue:
            cell = queue.popleft()
            cells.append(cell)
            for target in equal_neighbors[cell]:
                if target >= 0 and component[target] < 0:
                    component[target] = start
                    queue.append(int(target))
        cells = _m4_real_dem_flat_routing_np.asarray(cells, _m4_real_dem_flat_routing_np.int64)
        seeds = _m4_real_dem_flat_routing_np.sort(cells[raw[cells] >= 0])
        origins = seeds if len(seeds) else _m4_real_dem_flat_routing_np.array([start], _m4_real_dem_flat_routing_np.int64)
        distance[origins] = 0
        queue = _m4_real_dem_flat_routing_deque(origins.tolist())
        while queue:
            cell = queue.popleft()
            for target in equal_neighbors[cell]:
                if target >= 0 and distance[target] < 0:
                    distance[target] = distance[cell] + 1
                    queue.append(int(target))
        for cell in cells[distance[cells] > 0]:
            adjacent = equal_neighbors[cell]
            eligible = adjacent[(adjacent >= 0) & (distance[_m4_real_dem_flat_routing_np.maximum(adjacent, 0)] == distance[cell] - 1)]
            receiver[cell] = eligible.min()
        records.append(_record(int(start), cells, seeds, height, boundary, unknown, height_array.shape, distance))
    order = _order(receiver, valid)
    accumulation = accumulate_forward_unit(receiver, order, valid)
    terminal = valid & (receiver == -1)
    network = RealDemNetwork(receiver.reshape(height_array.shape), order, accumulation.reshape(height_array.shape),
                             (terminal & boundary).reshape(height_array.shape),
                             (terminal & unknown).reshape(height_array.shape), mesh)
    if _m4_real_dem_flat_routing_array_hash(height_array) != before:
        raise ValueError("source height changed")
    return {"network": network, "component_id": component.reshape(height_array.shape),
            "distance_to_exit": distance.reshape(height_array.shape), "components": records,
            "summary": flat_summary(height_array, valid, raw, receiver, accumulation, records)}

# --- terrain_pipeline/real_dem_flat_routing.py:167 ---
def validate_flat_routing(candidate, result) -> dict:
    """Check geometry and local shortest-distance witnesses without solver replay."""
    from terrain_pipeline.artifacts.contracts import canonical_json as _m4_real_dem_flat_routing_canonical_json
    height_array, valid_array = arrays_from_candidate(candidate)
    height, valid = height_array.ravel(), valid_array.ravel()
    shape = height_array.shape
    if not isinstance(result, dict) or set(result) != {"network", "component_id", "distance_to_exit", "components", "summary"}:
        raise ValueError("invalid flat routing result schema")
    network = result["network"]
    if not isinstance(network, RealDemNetwork):
        raise ValueError("RealDemNetwork required")
    for name, dtype in (("receiver", _m4_real_dem_flat_routing_np.int64), ("accumulation_cells", _m4_real_dem_flat_routing_np.float64),
                        ("boundary_outlet", bool), ("unknown_adjacent_terminal", bool)):
        values = getattr(network, name)
        if not isinstance(values, _m4_real_dem_flat_routing_np.ndarray) or values.shape != shape or values.dtype != _m4_real_dem_flat_routing_np.dtype(dtype):
            raise ValueError(f"invalid network {name}")
    for name in ("component_id", "distance_to_exit"):
        values = result[name]
        if not isinstance(values, _m4_real_dem_flat_routing_np.ndarray) or values.shape != shape or values.dtype != _m4_real_dem_flat_routing_np.dtype(_m4_real_dem_flat_routing_np.int64):
            raise ValueError(f"invalid {name}")
    component, distance = result["component_id"].ravel(), result["distance_to_exit"].ravel()
    receiver = network.receiver.ravel()
    ids = _m4_real_dem_flat_routing_np.flatnonzero(valid)
    if (_m4_real_dem_flat_routing_np.any(component[~valid] != -1) or _m4_real_dem_flat_routing_np.any(distance[~valid] != -1)
            or _m4_real_dem_flat_routing_np.any((component[ids] < 0) | (component[ids] >= height.size)) or _m4_real_dem_flat_routing_np.any(distance[ids] < 0)
            or _m4_real_dem_flat_routing_np.any(receiver[~valid] != -1) or _m4_real_dem_flat_routing_np.any((receiver < -1) | (receiver >= height.size))):
        raise ValueError("invalid unknown/range/component distance")
    mesh = network.mesh if network.mesh is not None else candidate_mesh(candidate)
    neighbors = dense_neighbors(shape, mesh)
    legal_neighbors = dense_neighbors(shape, mesh, valid_array)
    equal_neighbors = _equal_neighbors(legal_neighbors, height, valid)
    boundary, unknown = _risks(neighbors, valid, shape)
    raw, _, _ = strict_receivers(height_array, masked_mesh(mesh, valid_array), valid_mask=valid_array)
    routed_sources = ids[receiver[ids] >= 0]
    targets = receiver[routed_sources]
    if (_m4_real_dem_flat_routing_np.any(~valid[targets]) or _m4_real_dem_flat_routing_np.any(height[targets] > height[routed_sources])
            or _m4_real_dem_flat_routing_np.any(~_m4_real_dem_flat_routing_np.any(legal_neighbors[routed_sources] == targets[:, None], axis=1))):
        raise ValueError("receiver must be a valid non-uphill irregular edge")
    if _m4_real_dem_flat_routing_np.any(receiver[raw >= 0] != raw[raw >= 0]):
        raise ValueError("raw strictly downhill receiver must be preserved")
    flat = height[targets] == height[routed_sources]
    if (_m4_real_dem_flat_routing_np.any(component[targets[flat]] != component[routed_sources[flat]])
            or _m4_real_dem_flat_routing_np.any(distance[targets[flat]] != distance[routed_sources[flat]] - 1)):
        raise ValueError("flat receiver distance/rank must decrease")
    visited = _m4_real_dem_flat_routing_np.zeros(height.size, bool)
    records = []
    for start in ids:
        if visited[start]:
            continue
        queue = _m4_real_dem_flat_routing_deque([int(start)])
        visited[start] = True
        cells = []
        while queue:
            cell = queue.popleft()
            cells.append(cell)
            if component[cell] != start:
                raise ValueError("equal-height component geometry/minimum ID mismatch")
            adjacent = equal_neighbors[cell]
            adjacent = adjacent[adjacent >= 0]
            if _m4_real_dem_flat_routing_np.any(abs(distance[adjacent] - distance[cell]) > 1):
                raise ValueError("distance is not shortest BFS distance")
            for target in adjacent:
                if not visited[target]:
                    visited[target] = True
                    queue.append(int(target))
        cells = _m4_real_dem_flat_routing_np.asarray(cells, _m4_real_dem_flat_routing_np.int64)
        seeds = _m4_real_dem_flat_routing_np.sort(cells[raw[cells] >= 0])
        origins = seeds if len(seeds) else _m4_real_dem_flat_routing_np.array([start], _m4_real_dem_flat_routing_np.int64)
        if not _m4_real_dem_flat_routing_np.array_equal(_m4_real_dem_flat_routing_np.sort(cells[distance[cells] == 0]), origins):
            raise ValueError("distance zero seeds/closed root mismatch")
        for cell in cells[distance[cells] > 0]:
            adjacent = equal_neighbors[cell]
            eligible = adjacent[(adjacent >= 0) & (distance[_m4_real_dem_flat_routing_np.maximum(adjacent, 0)] == distance[cell] - 1)]
            if not len(eligible) or receiver[cell] != eligible.min():
                raise ValueError("flat BFS witness/receiver minimum-ID tie mismatch")
        if not len(seeds) and receiver[start] != -1:
            raise ValueError("closed retention root must remain terminal")
        records.append(_record(int(start), cells, seeds, height, boundary, unknown, shape, distance))
    if _m4_real_dem_flat_routing_canonical_json(result["components"]) != _m4_real_dem_flat_routing_canonical_json(records):
        raise ValueError("component records/risk/seed semantics mismatch")
    order = network.order
    if (not isinstance(order, _m4_real_dem_flat_routing_np.ndarray) or order.dtype != _m4_real_dem_flat_routing_np.dtype(_m4_real_dem_flat_routing_np.int64) or order.ndim != 1
            or not _m4_real_dem_flat_routing_np.array_equal(_m4_real_dem_flat_routing_np.sort(order), ids)):
        raise ValueError("invalid order coverage")
    rank = _m4_real_dem_flat_routing_np.full(height.size, -1, _m4_real_dem_flat_routing_np.int64)
    rank[order] = _m4_real_dem_flat_routing_np.arange(len(order))
    if _m4_real_dem_flat_routing_np.any(rank[routed_sources] >= rank[targets]):
        raise ValueError("order/rank must be upstream first")
    if not _m4_real_dem_flat_routing_np.array_equal(order, _order(receiver, valid)):
        raise ValueError("order must match deterministic Kahn FIFO")
    accumulation = accumulate_forward_unit(receiver, order, valid)
    if not _m4_real_dem_flat_routing_np.array_equal(network.accumulation_cells.ravel(), accumulation):
        raise ValueError("accumulation/contribution mismatch")
    terminal = valid & (receiver == -1)
    if (not _m4_real_dem_flat_routing_np.array_equal(network.boundary_outlet.ravel(), terminal & boundary)
            or not _m4_real_dem_flat_routing_np.array_equal(network.unknown_adjacent_terminal.ravel(), terminal & unknown)):
        raise ValueError("terminal risk mismatch")
    summary = flat_summary(height_array, valid, raw, receiver, accumulation, records)
    if summary["contributing_cells_sum"] != len(ids) or _m4_real_dem_flat_routing_canonical_json(result["summary"]) != _m4_real_dem_flat_routing_canonical_json(summary):
        raise ValueError("summary/source height/conservation mismatch")
    return {"verified": True, "summary": summary, "natural_outlet_verified": False,
            "ocean_outlet_certified": False, "global_graph_state": True}

# --- terrain_pipeline/real_dem_tiled_network.py:11 ---
TILED_ALGORITHM = "real-dem-array-tiles-global-irregular-graph-v2"

# --- terrain_pipeline/real_dem_tiled_network.py:12 ---
MAX_TILE_SIZE = 1024

# --- terrain_pipeline/real_dem_tiled_network.py:15 ---
def require_positive_integer(value, name, maximum=None):
    if type(value) is not int or value <= 0 or (maximum is not None and value > maximum):
        raise ValueError(f"{name} must be a positive integer" + (f" <= {maximum}" if maximum else ""))
    return value

# --- terrain_pipeline/real_dem_tiled_network.py:21 ---
def arrays_from_candidate(candidate):
    from terrain_pipeline.td_source import DEM_MAX_CELLS as _m4_real_dem_tiled_network_MAX_CELLS
    from terrain_pipeline.td_source import validate_dem_candidate as _m4_real_dem_tiled_network_validate_dem_candidate
    if not isinstance(candidate, dict) or "arrays" not in candidate:
        raise ValueError("candidate arrays required")
    arrays = candidate["arrays"]
    height, valid = arrays.get("height_m"), arrays.get("valid_mask")
    if (not isinstance(height, _m4_real_dem_tiled_network_np.ndarray) or height.ndim != 2 or height.dtype != _m4_real_dem_tiled_network_np.dtype("float64")
            or not isinstance(valid, _m4_real_dem_tiled_network_np.ndarray) or valid.dtype != _m4_real_dem_tiled_network_np.dtype(bool) or valid.shape != height.shape):
        raise ValueError("height_m/valid_mask shape or dtype mismatch")
    for value, name in zip(height.shape, ("rows", "cols")):
        require_positive_integer(value, name)
    if height.size > _m4_real_dem_tiled_network_MAX_CELLS:
        raise ValueError("candidate exceeds global graph cell budget")
    if not valid.any() or not _m4_real_dem_tiled_network_np.array_equal(valid, _m4_real_dem_tiled_network_np.isfinite(height)) or not _m4_real_dem_tiled_network_np.isnan(height[~valid]).all():
        raise ValueError("invalid finite height/unknown semantics or empty valid mask")
    if "unknown_mask" in arrays and not _m4_real_dem_tiled_network_np.array_equal(arrays["unknown_mask"], ~valid):
        raise ValueError("unknown_mask mismatch")
    if "manifest" in candidate:
        _m4_real_dem_tiled_network_validate_dem_candidate(candidate, verify_source=False)
    return height, valid

# --- terrain_pipeline/real_dem_tiled_network.py:42 ---
def candidate_mesh(candidate):
    height, _ = arrays_from_candidate(candidate)
    grid = candidate.get("manifest", {}).get("identity", {}).get("grid", candidate.get("grid", {}))
    return grid_mesh(height.shape, x0_m=grid.get("origin_x_m", 0.), z0_m=grid.get("origin_z_m", 0.),
        dx_m=grid.get("spacing_x_m", 90.), dz_m=grid.get("spacing_z_m", 90.))

# --- terrain_pipeline/real_dem_tiled_network.py:50 ---
@_m4_real_dem_tiled_network_dataclass(frozen=True)
class DemTile:
    core_bounds: tuple
    window_bounds: tuple
    height_m: _m4_real_dem_tiled_network_np.ndarray
    valid_mask: _m4_real_dem_tiled_network_np.ndarray

# --- terrain_pipeline/real_dem_tiled_network.py:57 ---
class CandidateTileReader:
    """Resident-array views; tile counters do not bound global graph memory."""
    def __init__(self, candidate, *, tile_size=256):
        self.tile_size = require_positive_integer(tile_size, "tile_size", MAX_TILE_SIZE)
        self.height_m, self.valid_mask = arrays_from_candidate(candidate)
        self.shape = self.height_m.shape
        self.read_windows = self.peak_window_cells = 0

    def read_window(self, row_start, row_stop, col_start, col_stop):
        bounds = (row_start, row_stop, col_start, col_stop)
        if any(type(value) is not int for value in bounds):
            raise ValueError("window bounds must be integers, not bool")
        if not (0 <= row_start < row_stop <= self.shape[0] and 0 <= col_start < col_stop <= self.shape[1]):
            raise ValueError("window outside candidate or empty")
        height = self.height_m[row_start:row_stop, col_start:col_stop].view()
        valid = self.valid_mask[row_start:row_stop, col_start:col_stop].view()
        height.flags.writeable = valid.flags.writeable = False
        self.read_windows += 1
        self.peak_window_cells = max(self.peak_window_cells, height.size)
        return {"height_m": height, "valid_mask": valid}

    def iter_tiles(self, *, tile_order="row_major"):
        if tile_order not in ("row_major", "reversed"):
            raise ValueError("tile_order must be row_major or reversed")
        rows, cols = self.shape
        cores = [(row, min(rows, row + self.tile_size), col, min(cols, col + self.tile_size))
                 for row in range(0, rows, self.tile_size) for col in range(0, cols, self.tile_size)]
        if tile_order == "reversed":
            cores.reverse()
        for core in cores:
            r0, r1, c0, c1 = core
            window = (max(0, r0 - 1), min(rows, r1 + 1), max(0, c0 - 1), min(cols, c1 + 1))
            values = self.read_window(*window)
            yield DemTile(core, window, values["height_m"], values["valid_mask"])

    def statistics(self):
        return dict(read_windows=self.read_windows, peak_window_cells=self.peak_window_cells,
            storage="read_only_views_of_resident_candidate_arrays", halo_cells=1,
            disk_streamed_full_state=False)

# --- terrain_pipeline/real_dem_tiled_network.py:98 ---
def build_tiled_network(candidate, *, tile_size=256, tile_order="row_major") -> RealDemNetwork:
    reader = CandidateTileReader(candidate, tile_size=tile_size)
    # The complete supplied window owns topology; a tile halo is only a read window.
    for _ in reader.iter_tiles(tile_order=tile_order):
        pass
    return build_real_dem_network(reader.height_m, reader.valid_mask, mesh=candidate_mesh(candidate))

# --- terrain_pipeline/real_dem_tiled_network.py:106 ---
def validate_tiled_network(candidate, network, *, tile_size=256) -> dict:
    """Audit actual graph receivers, order, accumulation and terminal risks."""
    reader = CandidateTileReader(candidate, tile_size=tile_size)
    height, valid = reader.height_m, reader.valid_mask
    if not isinstance(network, RealDemNetwork):
        raise ValueError("RealDemNetwork required")
    for name, dtype in (("receiver", _m4_real_dem_tiled_network_np.int64), ("accumulation_cells", _m4_real_dem_tiled_network_np.float64),
                        ("boundary_outlet", bool), ("unknown_adjacent_terminal", bool)):
        value = getattr(network, name)
        if not isinstance(value, _m4_real_dem_tiled_network_np.ndarray) or value.shape != height.shape or value.dtype != _m4_real_dem_tiled_network_np.dtype(dtype):
            raise ValueError(f"invalid {name} shape/dtype")
    ids = _m4_real_dem_tiled_network_np.flatnonzero(valid.ravel())
    expected_order = ids[_m4_real_dem_tiled_network_np.argsort(-height.ravel()[ids], kind="stable")]
    if (not isinstance(network.order, _m4_real_dem_tiled_network_np.ndarray) or network.order.dtype != _m4_real_dem_tiled_network_np.dtype(_m4_real_dem_tiled_network_np.int64)
            or not _m4_real_dem_tiled_network_np.array_equal(network.order, expected_order)):
        raise ValueError("order must be stable descending valid height")
    audit = validate_real_dem_network(network, height, valid)
    mesh = network.mesh if network.mesh is not None else candidate_mesh(candidate)
    rec = network.receiver.ravel()
    if _m4_real_dem_tiled_network_np.any(rec[~valid.ravel()] != -1):
        raise ValueError("unknown cells must remain terminal")
    expected = _m4_real_dem_tiled_network_np.zeros(height.size)
    expected[ids] = 1.
    for node in network.order:
        if rec[node] >= 0:
            expected[rec[node]] += expected[node]
    if not _m4_real_dem_tiled_network_np.array_equal(network.accumulation_cells.ravel(), expected):
        raise ValueError("contributing accumulation mismatch")
    boundary = _m4_real_dem_tiled_network_np.zeros(height.shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    unknown = _m4_real_dem_tiled_network_np.zeros(height.size, bool)
    for node in ids:
        adjacent = mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]
        unknown[node] = _m4_real_dem_tiled_network_np.any(~valid.ravel()[adjacent])
    terminal = valid & (network.receiver < 0)
    if (not _m4_real_dem_tiled_network_np.array_equal(network.boundary_outlet, terminal & boundary)
            or not _m4_real_dem_tiled_network_np.array_equal(network.unknown_adjacent_terminal, terminal & unknown.reshape(height.shape))):
        raise ValueError("terminal boundary/unknown risk mismatch")
    contribution = expected[ids[rec[ids] < 0]].sum()
    if contribution != ids.size:
        raise ValueError("terminal contributions do not cover valid cells")
    for _ in reader.iter_tiles():
        pass
    graph_bytes = {name: int(getattr(network, name).nbytes) for name in
        ("receiver", "order", "accumulation_cells", "boundary_outlet", "unknown_adjacent_terminal")}
    return dict(audit, algorithm=TILED_ALGORITHM, tile_size=tile_size, contributing_cells_sum=int(contribution),
        reader=reader.statistics(), global_graph_state=True, graph_array_nbytes=graph_bytes,
        graph_arrays_nbytes=sum(graph_bytes.values()), memory_scope="graph payload excludes mesh and sort temporaries",
        disk_streamed_full_state=False)

# --- terrain_pipeline/real_dem_surface_network.py:15 ---
SURFACE_NETWORK_ALGORITHM = "real-dem-irregular-strict-metric-graph-v2"

# --- terrain_pipeline/real_dem_surface_network.py:19 ---
@_m4_real_dem_surface_network_dataclass(frozen=True)
class RealDemNetwork:
    receiver: _m4_real_dem_surface_network_np.ndarray
    order: _m4_real_dem_surface_network_np.ndarray
    accumulation_cells: _m4_real_dem_surface_network_np.ndarray
    boundary_outlet: _m4_real_dem_surface_network_np.ndarray
    unknown_adjacent_terminal: _m4_real_dem_surface_network_np.ndarray
    mesh: object = None

# --- terrain_pipeline/real_dem_surface_network.py:28 ---
def build_real_dem_network(height_m, valid_mask, *, origin_xz_m=(0., 0.), spacing_m=90., world_seed=20261020, mesh=None):
    height = _m4_real_dem_surface_network_np.asarray(height_m, dtype=_m4_real_dem_surface_network_np.float64)
    valid = _m4_real_dem_surface_network_np.asarray(valid_mask, dtype=bool)
    if height.ndim != 2 or valid.shape != height.shape:
        raise ValueError("height and valid_mask shape mismatch")
    if _m4_real_dem_surface_network_np.any(valid & ~_m4_real_dem_surface_network_np.isfinite(height)):
        raise ValueError("valid DEM cells must be finite")
    if not valid.any():
        raise ValueError("DEM has no valid cells")
    if mesh is None:
        mesh = grid_mesh(height.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1],
                         dx_m=spacing_m, world_seed=world_seed)
    rows, cols = height.shape
    flat_height = height.ravel()
    flat_valid = valid.ravel()
    receiver, _, _ = strict_receivers(height, masked_mesh(mesh, valid), valid_mask=valid)
    valid_ids = _m4_real_dem_surface_network_np.flatnonzero(flat_valid)
    order = valid_ids[_m4_real_dem_surface_network_np.argsort(-flat_height[valid_ids], kind="stable")]
    accumulation = _m4_real_dem_surface_network_np.zeros(height.size, dtype=_m4_real_dem_surface_network_np.float64)
    accumulation[valid_ids] = 1.0
    for source_id in order:
        target_id = receiver[source_id]
        if target_id >= 0:
            accumulation[target_id] += accumulation[source_id]
    boundary = _m4_real_dem_surface_network_np.zeros((rows, cols), dtype=bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    unknown_adjacent = _m4_real_dem_surface_network_np.zeros((rows, cols), dtype=bool)
    for node in _m4_real_dem_surface_network_np.flatnonzero(flat_valid):
        neighbors = mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]
        unknown_adjacent.ravel()[node] = _m4_real_dem_surface_network_np.any(~flat_valid[neighbors])
    return RealDemNetwork(receiver.reshape(height.shape), order,
                           accumulation.reshape(height.shape),
                           boundary & valid & (receiver.reshape(height.shape) < 0),
                           valid & unknown_adjacent & (receiver.reshape(height.shape) < 0), mesh)

# --- terrain_pipeline/real_dem_surface_network.py:65 ---
def validate_real_dem_network(network: RealDemNetwork, height_m, valid_mask):
    height = _m4_real_dem_surface_network_np.asarray(height_m, dtype=_m4_real_dem_surface_network_np.float64)
    valid = _m4_real_dem_surface_network_np.asarray(valid_mask, dtype=bool)
    receiver = _m4_real_dem_surface_network_np.asarray(network.receiver)
    if receiver.shape != height.shape or valid.shape != height.shape:
        raise ValueError("network shape mismatch")
    flat_receiver = receiver.ravel()
    flat_height = height.ravel()
    valid_ids = _m4_real_dem_surface_network_np.flatnonzero(valid.ravel())
    targets = flat_receiver[valid_ids]
    if _m4_real_dem_surface_network_np.any((targets < -1) | (targets >= height.size)):
        raise ValueError("receiver outside grid")
    routed = targets >= 0
    if _m4_real_dem_surface_network_np.any(~valid.ravel()[targets[routed]]):
        raise ValueError("receiver points into unknown DEM")
    if _m4_real_dem_surface_network_np.any(flat_height[targets[routed]] >= flat_height[valid_ids[routed]]):
        raise ValueError("receiver is not strictly downhill")
    mesh = network.mesh if network.mesh is not None else grid_mesh(height.shape, dx_m=90.)
    expected, _, _ = strict_receivers(height, masked_mesh(mesh, valid), valid_mask=valid)
    if not _m4_real_dem_surface_network_np.array_equal(flat_receiver, expected):
        raise ValueError("receiver must follow the irregular steepest metric edge")
    if _m4_real_dem_surface_network_np.unique(network.order).size != valid_ids.size or set(network.order.tolist()) != set(valid_ids.tolist()):
        raise ValueError("topological order does not cover valid cells")
    return {
        "verified": True,
        "algorithm": SURFACE_NETWORK_ALGORITHM,
        "valid_cells": int(valid.sum()),
        "unknown_cells": int((~valid).sum()),
        "downhill_edges": int(routed.sum()),
        "terminal_cells": int(_m4_real_dem_surface_network_np.count_nonzero(valid & (receiver < 0))),
        "boundary_outlet_candidates": int(network.boundary_outlet.sum()),
        "unknown_adjacent_terminals": int(network.unknown_adjacent_terminal.sum()),
        "natural_outlet_verified": False,
        "status": "real_dem_candidate_not_publishable",
    }

# --- terrain_pipeline/surface_rivers/metric_drainage.py:13 ---
_EXPLICIT_OUTLETS = ("open_outflow", "prescribed_stage", "prescribed_discharge", "unknown_boundary")

# --- terrain_pipeline/surface_rivers/metric_drainage.py:16 ---
def diagnostic_mesh(terrain, *, unmasked=False):
    mesh = grid_mesh(terrain.elevation_m.shape, x0_m=terrain.x0_m,
        z0_m=terrain.z0_m, dx_m=terrain.dx_m, dz_m=terrain.dz_m,
        world_seed=terrain.generation_seed if terrain.generation_seed is not None else 20261020)
    return mesh if unmasked else masked_mesh(mesh, terrain.valid_mask)

# --- terrain_pipeline/surface_rivers/metric_drainage.py:23 ---
def unknown_contacts(valid, mesh):
    """Valid cells with a graph edge touching an unknown control cell."""
    supported = valid_edge_mask(mesh, valid)
    source = _m4_drainage_np.repeat(_m4_drainage_np.arange(valid.size, dtype=_m4_drainage_np.int64), _m4_drainage_np.diff(mesh.indptr))
    counts = _m4_drainage_np.bincount(source[~supported], minlength=valid.size)
    return valid & (counts.reshape(valid.shape) > 0)

# --- terrain_pipeline/surface_rivers/metric_drainage.py:31 ---
def route_diagnostic(terrain: _m4_drainage_TerrainGrid, boundary: _m4_drainage_BoundaryGrid, *, flat_distance_strategy="hop_count") -> _m4_drainage_RoutingGraph:
    """Route on unchanged bed elevations; closed flats remain lake catchments."""
    if not isinstance(terrain, _m4_drainage_TerrainGrid) or not isinstance(boundary, _m4_drainage_BoundaryGrid):
        raise TypeError("TerrainGrid and BoundaryGrid required")
    if flat_distance_strategy not in ("hop_count", "metric_distance"):
        raise ValueError("unknown flat distance strategy")
    height = terrain.elevation_m
    valid = terrain.valid_mask
    kind = boundary.kind
    if kind.shape != height.shape:
        raise ValueError("boundary shape differs from terrain")
    if _m4_drainage_np.any((~valid) & (kind != "unknown_boundary")):
        raise ValueError("invalid terrain cells must be unknown_boundary")

    rows, cols = height.shape
    n = height.size
    flat_height = height.ravel()
    flat_valid = valid.ravel()
    flat_kind = kind.ravel()
    receiver = _m4_drainage_np.full(n, -1, dtype=_m4_drainage_np.int64)
    edge_length = _m4_drainage_np.zeros(n, dtype=_m4_drainage_np.float64)
    edge_slope = _m4_drainage_np.zeros(n, dtype=_m4_drainage_np.float64)
    outlet_kind = _m4_drainage_np.full(n, "interior", dtype="U24")
    outlet_kind[~flat_valid] = "inactive"
    unknown_contact = _m4_drainage_np.zeros(n, dtype=bool)
    fringe = _m4_drainage_np.zeros(n, dtype=bool)
    full_mesh = diagnostic_mesh(terrain, unmasked=True)
    mesh = masked_mesh(full_mesh, valid)
    contacts = unknown_contacts(valid, full_mesh).ravel()

    def neighbors(cell):
        for edge in range(mesh.indptr[cell], mesh.indptr[cell + 1]):
            yield int(mesh.indices[edge]), float(mesh.edge_length_m[edge])

    for cell in _m4_drainage_np.flatnonzero(flat_valid):
        row, col = divmod(int(cell), cols)
        on_perimeter = row in (0, rows - 1) or col in (0, cols - 1)
        near_unknown = bool(contacts[cell])
        fringe[cell] = on_perimeter or near_unknown
        unknown_contact[cell] = near_unknown
        if on_perimeter and flat_kind[cell] == "interior":
            raise ValueError("valid perimeter cells require an explicit boundary kind")
        if flat_kind[cell] != "interior" and not fringe[cell]:
            raise ValueError("boundary kind requires perimeter or unknown contact")
        if flat_kind[cell] in _EXPLICIT_OUTLETS:
            outlet_kind[cell] = flat_kind[cell]
            continue
        best = None
        for target, distance in neighbors(int(cell)):
            drop = flat_height[cell] - flat_height[target]
            if drop <= 0.:
                continue
            slope = drop / distance
            candidate = (-slope, target, distance)
            if best is None or candidate < best:
                best = candidate
        if best is not None:
            receiver[cell] = best[1]
            edge_length[cell] = best[2]
            edge_slope[cell] = -best[0]

    # Each equal-height component drains toward its lower or explicit seed.
    # An unseeded component touching unknown is unresolved; a fully closed one
    # has a single deterministic lake terminal at its smallest cell ID.
    visited = _m4_drainage_np.zeros(n, dtype=bool)
    for start in _m4_drainage_np.flatnonzero(flat_valid):
        if visited[start]:
            continue
        component = []
        queue = _m4_drainage_deque([int(start)])
        visited[start] = True
        while queue:
            cell = queue.popleft()
            component.append(cell)
            for target, _ in neighbors(cell):
                if not visited[target] and flat_height[target] == flat_height[cell]:
                    visited[target] = True
                    queue.append(target)
        seeds = [cell for cell in component if receiver[cell] >= 0 or outlet_kind[cell] != "interior"]
        if not seeds:
            seeds = [cell for cell in component if unknown_contact[cell]]
            for cell in seeds:
                outlet_kind[cell] = "unknown_boundary"
        if not seeds:
            terminal = min(component)
            outlet_kind[terminal] = "lake_preserved"
            seeds = [terminal]
        seed_set = set(seeds)
        distance_to_seed = {cell: 0. for cell in seeds}
        if flat_distance_strategy == "metric_distance":
            pending = [(0., cell) for cell in seeds]
            _m4_drainage_heapq.heapify(pending)
            while pending:
                distance, cell = _m4_drainage_heapq.heappop(pending)
                if distance != distance_to_seed[cell]:
                    continue
                for target, length in neighbors(cell):
                    proposed = distance + length
                    if flat_height[target] != flat_height[cell] or proposed >= distance_to_seed.get(target, _m4_drainage_math.inf):
                        continue
                    distance_to_seed[target] = proposed
                    _m4_drainage_heapq.heappush(pending, (proposed, target))
        else:
            queue = _m4_drainage_deque(sorted(seeds))
            while queue:
                cell = queue.popleft()
                for target, _ in neighbors(cell):
                    if flat_height[target] != flat_height[cell] or target in distance_to_seed:
                        continue
                    distance_to_seed[target] = distance_to_seed[cell] + 1
                    queue.append(target)
        for cell in component:
            if cell in seed_set:
                continue
            distance = distance_to_seed[cell]
            if flat_distance_strategy == "metric_distance":
                candidates = [(target, length) for target, length in neighbors(cell)
                              if flat_height[target] == flat_height[cell]
                              and distance_to_seed[target] < distance
                              and _m4_drainage_math.isclose(distance_to_seed[target] + length, distance, rel_tol=1e-12, abs_tol=1e-12)]
            else:
                candidates = [(target, length) for target, length in neighbors(cell)
                              if flat_height[target] == flat_height[cell]
                              and distance_to_seed[target] == distance - 1]
            target, length = min(candidates)
            receiver[cell] = target
            edge_length[cell] = length

    donors = [[] for _ in range(n)]
    terminals = []
    for cell in _m4_drainage_np.flatnonzero(flat_valid):
        target = receiver[cell]
        if target < 0:
            terminals.append(int(cell))
        else:
            donors[target].append(int(cell))
    _m4_drainage_heapq.heapify(terminals)
    order = []
    lake_id = _m4_drainage_np.full(n, -1, dtype=_m4_drainage_np.int64)
    while terminals:
        cell = _m4_drainage_heapq.heappop(terminals)
        order.append(cell)
        if outlet_kind[cell] == "lake_preserved":
            lake_id[cell] = cell
        elif receiver[cell] >= 0:
            lake_id[cell] = lake_id[receiver[cell]]
        for donor in donors[cell]:
            _m4_drainage_heapq.heappush(terminals, donor)
    if len(order) != int(valid.sum()):
        raise AssertionError("diagnostic receiver graph contains a cycle")
    return _m4_drainage_RoutingGraph(receiver, _m4_drainage_np.asarray(order, dtype=_m4_drainage_np.int64), valid,
                        edge_length, edge_slope, outlet_kind, lake_id,
                        terrain.identity_sha256, boundary.identity_sha256,
                        policy="original_bed_irregular_plateau_metric_distance_v2" if flat_distance_strategy == "metric_distance" else "original_bed_irregular_plateau_bfs_v2")

# --- terrain_pipeline/surface_rivers/metric_drainage.py:187 ---
def accumulate_local_discharge(graph: _m4_drainage_RoutingGraph, local_q_m3_s: _m4_drainage_np.ndarray) -> dict:
    """Instantaneously sum local m3/s along the diagnostic graph."""
    if not isinstance(graph, _m4_drainage_RoutingGraph):
        raise TypeError("RoutingGraph required")
    local = _m4_drainage_np.asarray(local_q_m3_s, dtype=_m4_drainage_np.float64)
    if local.shape != graph.valid_mask.shape or not _m4_drainage_np.isfinite(local).all() or _m4_drainage_np.any(local < 0.):
        raise ValueError("local discharge must be finite nonnegative [z,x]")
    if _m4_drainage_np.any(local[~graph.valid_mask] != 0.):
        raise ValueError("invalid terrain cells cannot contribute discharge")
    flow = local.ravel().copy()
    for cell in graph.order_downstream_first[::-1]:
        target = graph.receiver[cell]
        if target >= 0:
            flow[target] += flow[cell]
    if not _m4_drainage_np.isfinite(flow).all():
        raise ValueError("routed discharge overflows float64")
    terminal = _m4_drainage_np.zeros(flow.size, dtype=_m4_drainage_np.float64)
    mask = graph.valid_mask.ravel() & (graph.receiver == -1)
    terminal[mask] = flow[mask]
    kinds = graph.outlet_kind

    def total(kind):
        value = float(_m4_drainage_np.sum(terminal[kinds == kind], dtype=_m4_drainage_np.float64))
        if not _m4_drainage_math.isfinite(value):
            raise ValueError("terminal discharge budget overflows float64")
        return value

    input_total = float(_m4_drainage_np.sum(local, dtype=_m4_drainage_np.float64))
    if not _m4_drainage_math.isfinite(input_total):
        raise ValueError("input discharge budget overflows float64")
    open_outflow = total("open_outflow")
    lake_retained = total("lake_preserved")
    unknown_pending = total("unknown_boundary")
    prescribed = total("prescribed_stage") + total("prescribed_discharge")
    residual = input_total - open_outflow - lake_retained - unknown_pending - prescribed
    return {"routed_q_m3_s": flow.reshape(local.shape),
            "terminal_q_m3_s": terminal.reshape(local.shape),
            "input_total_m3_s": input_total,
            "open_outflow_m3_s": open_outflow,
            "lake_retained_m3_s": lake_retained,
            "unknown_pending_m3_s": unknown_pending,
            "prescribed_boundary_candidate_m3_s": prescribed,
            "residual_m3_s": residual}

# --- terrain_pipeline/surface_rivers/metric_network_accumulation.py:13 ---
MAX_NETWORK_CELLS = 16_777_216

# --- terrain_pipeline/surface_rivers/metric_network_accumulation.py:16 ---
def accumulate_network_discharge(receiver, local_q_m3_s, valid_mask, *,
                                 terminal_kind, upstream_unknown_mask=None,
                                 max_cells=MAX_NETWORK_CELLS):
    """Sum each valid cell's local m3/s once over the finite joint topology.

    ``upstream_unknown_mask`` marks missing external contributions; it propagates
    downstream without inventing water. ``terminal_kind`` describes where known
    water ends, independently of whether its upstream catchment is complete.
    Inputs are never modified; illegal topology, budgets and overflow are refused.
    """
    if type(max_cells) is not int or max_cells <= 0:
        raise ValueError('max_cells must be a positive integer')
    if (not isinstance(receiver, _m4_network_accumulation_np.ndarray) or receiver.dtype != _m4_network_accumulation_np.int64
            or receiver.ndim != 2 or not 1 <= receiver.size <= max_cells):
        raise ValueError('bounded nonempty int64 [z,x] receiver required')
    shape = receiver.shape
    for array, dtype, label in ((local_q_m3_s, _m4_network_accumulation_np.float64, 'local_q_m3_s'),
                                (valid_mask, _m4_network_accumulation_np.bool_, 'valid_mask')):
        if not isinstance(array, _m4_network_accumulation_np.ndarray) or array.dtype != dtype or array.shape != shape:
            raise ValueError(label + ' must have matching shape and exact dtype')
    if (not isinstance(terminal_kind, _m4_network_accumulation_np.ndarray) or terminal_kind.shape != shape
            or terminal_kind.dtype.kind != 'U'):
        raise ValueError('matching Unicode terminal_kind array required')
    if not valid_mask.any():
        raise ValueError('at least one valid cell required')
    if not _m4_network_accumulation_np.isfinite(local_q_m3_s).all() or _m4_network_accumulation_np.any(local_q_m3_s < 0):
        raise ValueError('local_q_m3_s must be finite and nonnegative')
    if _m4_network_accumulation_np.any(local_q_m3_s[~valid_mask] != 0) or _m4_network_accumulation_np.any(receiver[~valid_mask] != -1):
        raise ValueError('inactive cells must have zero local Q and receiver -1')
    if upstream_unknown_mask is None:
        dirty = _m4_network_accumulation_np.zeros(receiver.size, bool)
    else:
        if (not isinstance(upstream_unknown_mask, _m4_network_accumulation_np.ndarray)
                or upstream_unknown_mask.dtype != _m4_network_accumulation_np.bool_
                or upstream_unknown_mask.shape != shape):
            raise ValueError('matching boolean upstream_unknown_mask required')
        if _m4_network_accumulation_np.any(upstream_unknown_mask[~valid_mask]):
            raise ValueError('inactive cells cannot seed unknown upstream')
        dirty = upstream_unknown_mask.ravel().copy()

    rec = receiver.ravel()
    valid = valid_mask.ravel()
    kinds = terminal_kind.ravel()
    n = rec.size
    if _m4_network_accumulation_np.any(rec < -1) or _m4_network_accumulation_np.any(rec >= n):
        raise ValueError('receiver index outside grid')
    live = valid & (rec >= 0)
    sources = _m4_network_accumulation_np.flatnonzero(live)
    targets = rec[sources]
    if _m4_network_accumulation_np.any(sources == targets) or _m4_network_accumulation_np.any(~valid[targets]):
        raise ValueError('self receiver or inactive receiver target')
    terminal = valid & ~live
    if _m4_network_accumulation_np.any(kinds[~valid] != 'inactive') or _m4_network_accumulation_np.any(kinds[live] != 'interior'):
        raise ValueError('inactive and nonterminal policy mismatch')
    if not _m4_network_accumulation_np.isin(kinds[terminal], ('retained', 'open_outflow', 'unknown_boundary')).all():
        raise ValueError('terminal destination must be declared')

    def finite_sum(values, label):
        with _m4_network_accumulation_np.errstate(over='ignore', invalid='ignore'):
            total = float(_m4_network_accumulation_np.sum(values, dtype=_m4_network_accumulation_np.float64))
        if not _m4_network_accumulation_math.isfinite(total):
            raise ValueError(label + ' overflows float64')
        return total

    input_total = finite_sum(local_q_m3_s, 'input total')
    flow = local_q_m3_s.ravel().copy()
    pending = _m4_network_accumulation_np.bincount(targets, minlength=n).astype(_m4_network_accumulation_np.int64, copy=False)
    frontier = _m4_network_accumulation_np.flatnonzero(valid & (pending == 0))
    processed = 0
    while frontier.size:
        processed += int(frontier.size)
        src = frontier[rec[frontier] >= 0]
        dst = rec[src]
        if not src.size:
            break
        # Sources are settled before receivers. Repeated confluences must count
        # every donor; fancy-index -= silently drops duplicate decrements.
        with _m4_network_accumulation_np.errstate(over='ignore', invalid='ignore'):
            _m4_network_accumulation_np.add.at(flow, dst, flow[src])
        if not _m4_network_accumulation_np.isfinite(flow[dst]).all():
            raise ValueError('routed known discharge overflows float64')
        _m4_network_accumulation_np.logical_or.at(dirty, dst, dirty[src])
        _m4_network_accumulation_np.subtract.at(pending, dst, 1)
        frontier = _m4_network_accumulation_np.unique(dst[pending[dst] == 0])
    valid_count = int(valid.sum())
    if processed != valid_count:
        raise ValueError('receiver graph contains a cycle')

    terminal_q = _m4_network_accumulation_np.where(terminal, flow, 0.)
    totals = {kind: finite_sum(terminal_q[kinds == kind], kind)
              for kind in ('retained', 'open_outflow', 'unknown_boundary')}
    # Subtract individually: adding the terminal totals first can overflow even
    # when each input total and the physically zero residual are representable.
    residual = input_total
    for kind in ('retained', 'open_outflow', 'unknown_boundary'):
        residual -= totals[kind]
    if not _m4_network_accumulation_math.isfinite(residual):
        raise ValueError('water balance residual overflows float64')
    return {
        'known_routed_q_m3_s': flow.reshape(shape),
        'complete_mask': (valid & ~dirty).reshape(shape),
        'terminal_q_m3_s': terminal_q.reshape(shape),
        'input_total_m3_s': input_total,
        'open_outflow_m3_s': totals['open_outflow'],
        'retained_m3_s': totals['retained'],
        'unknown_pending_m3_s': totals['unknown_boundary'],
        'residual_m3_s': residual,
        'valid_cells': valid_count,
        'processed_cells': processed,
        'policy': 'finite_joint_graph_known_discharge_canonical_waves_v1',
    }

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:14 ---
REFERENCE_SCHEMA = "terragenesis-reference-routing-v2"

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:15 ---
BACKEND_VERSION = "1"

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:16 ---
ARRAY_NAMES = ("receiver", "order_downstream_first", "valid_mask", "upstream_area_m2",
               "basin_id", "stream_order", "outlet_kind")

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:18 ---
CAPABILITIES = ("hydraulic_ready", "natural_outlet_verified", "publishable")

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:19 ---
TERMINALS = ("open_outflow", "prescribed_stage", "prescribed_discharge", "unknown_boundary",
             "lake_preserved", "reference_edge_exit", "reference_pit")

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:31 ---
def _number(value, name):
    if isinstance(value, (bool, _m4_reference_routing_np.bool_)) or not isinstance(value, (int, float, _m4_reference_routing_np.integer, _m4_reference_routing_np.floating)):
        raise ValueError(name + " must be numeric")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(name + " must be finite") from error
    if not _m4_reference_routing_math.isfinite(result):
        raise ValueError(name + " must be finite")
    return result

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:43 ---
def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("lowercase SHA256 identity required")

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:48 ---
def _freeze(value):
    if isinstance(value, _m4_reference_routing_Mapping):
        return _m4_reference_routing_MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:56 ---
def _plain(value):
    if isinstance(value, _m4_reference_routing_Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:65 ---
@_m4_reference_routing_dataclass(frozen=True)
class ReferenceRoutingConfig:
    backend: str = "irregular_graph"
    max_depth: float = -1.0
    outlets: str = "edge"
    nodata: float = -9999.0

    def __post_init__(self):
        if self.backend != "irregular_graph" or self.outlets not in ("edge", "min"):
            raise ValueError("irregular_graph with edge or min outlets required")
        depth = _number(self.max_depth, "max_depth")
        if depth != -1.0 and depth <= 0.0:
            raise ValueError("max_depth must be -1 or positive; zero-depth routing is unsupported")
        object.__setattr__(self, "max_depth", depth)
        object.__setattr__(self, "nodata", _number(self.nodata, "nodata"))

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:81 ---
def _check_arrays(arrays, cell_area_m2):
    from terrain_pipeline.common_infra import GRID_MAX_CELLS as _m4_reference_routing_MAX_CELLS
    valid = arrays["valid_mask"]
    if (not isinstance(valid, _m4_reference_routing_np.ndarray) or valid.dtype != _m4_reference_routing_np.bool_ or valid.ndim != 2
            or not 1 < valid.size <= _m4_reference_routing_MAX_CELLS or not valid.any()):
        raise ValueError("bounded nonempty boolean grid mask required")
    mask = valid.ravel()
    size = valid.size
    for name in ("receiver", "basin_id", "stream_order", "upstream_area_m2"):
        dtype = _m4_reference_routing_np.dtype(_m4_reference_routing_np.float64 if name == "upstream_area_m2" else _m4_reference_routing_np.int64)
        value = arrays[name]
        if not isinstance(value, _m4_reference_routing_np.ndarray) or value.dtype != dtype or value.shape != (size,):
            raise ValueError(name + " must be " + dtype.name + " [N]")
        if not _m4_reference_routing_np.isfinite(value).all():
            raise ValueError(name + " must be finite")
    order = arrays["order_downstream_first"]
    if (not isinstance(order, _m4_reference_routing_np.ndarray) or order.dtype != _m4_reference_routing_np.int64 or order.ndim != 1
            or not _m4_reference_routing_np.array_equal(_m4_reference_routing_np.sort(order), _m4_reference_routing_np.flatnonzero(mask))):
        raise ValueError("downstream order must contain each valid cell exactly once")
    receiver = arrays["receiver"]
    if _m4_reference_routing_np.any(receiver < -1) or _m4_reference_routing_np.any(receiver >= size) or _m4_reference_routing_np.any(receiver[~mask] != -1):
        raise ValueError("reference receiver outside valid domain")
    donors = _m4_reference_routing_np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    if _m4_reference_routing_np.any(~mask[targets]):
        raise ValueError("reference receiver crosses nodata")
    if _m4_reference_routing_np.any(targets == donors):
        raise ValueError("reference receiver cannot be its own neighbour")
    rank = _m4_reference_routing_np.full(size, -1, dtype=_m4_reference_routing_np.int64)
    rank[order] = _m4_reference_routing_np.arange(order.size)
    if _m4_reference_routing_np.any(rank[targets] >= rank[donors]):
        raise ValueError("reference graph is cyclic or downstream order is invalid")
    kinds = arrays["outlet_kind"]
    terminal = mask & (receiver == -1)
    if (not isinstance(kinds, _m4_reference_routing_np.ndarray) or kinds.shape != (size,) or kinds.dtype.kind != "U"
            or not _m4_reference_routing_np.isin(kinds[terminal], TERMINALS).all()
            or _m4_reference_routing_np.any(kinds[donors] != "interior") or _m4_reference_routing_np.any(kinds[~mask] != "inactive")):
        raise ValueError("reference terminal kinds differ from topology")
    area = arrays["upstream_area_m2"]
    if _m4_reference_routing_np.any(area[~mask] != 0.) or _m4_reference_routing_np.any(area[mask] < cell_area_m2):
        raise ValueError("reference contributing area or nodata area invalid")
    expected = mask * cell_area_m2 + _m4_reference_routing_np.bincount(targets, weights=area[donors], minlength=size)
    if not _m4_reference_routing_np.allclose(area, expected, rtol=1e-10, atol=1e-8):
        raise ValueError("reference upstream area does not close at every node")
    if not _m4_reference_routing_math.isclose(float(area[terminal].sum()), int(mask.sum()) * cell_area_m2,
                        rel_tol=1e-10, abs_tol=1e-8):
        raise ValueError("reference terminal areas do not cover the domain")
    basins = arrays["basin_id"]
    if (_m4_reference_routing_np.any(basins[~mask] != -1) or _m4_reference_routing_np.any(basins[mask] < 0) or _m4_reference_routing_np.any(basins[mask] >= size)
            or not _m4_reference_routing_np.array_equal(basins[terminal], _m4_reference_routing_np.flatnonzero(terminal))
            or _m4_reference_routing_np.any(basins[donors] != basins[targets])):
        raise ValueError("basin_id must be the downstream terminal cell ID")
    streams = arrays["stream_order"]
    if _m4_reference_routing_np.any(streams[~mask] != 0) or _m4_reference_routing_np.any(streams[mask] < 1):
        raise ValueError("invalid Strahler stream order")
    maximum = _m4_reference_routing_np.zeros(size, dtype=_m4_reference_routing_np.int64)
    _m4_reference_routing_np.maximum.at(maximum, targets, streams[donors])
    tied = targets[streams[donors] == maximum[targets]]
    multiplicity = _m4_reference_routing_np.bincount(tied, minlength=size)
    expected_order = _m4_reference_routing_np.maximum(maximum, 1) + (multiplicity >= 2)
    if _m4_reference_routing_np.any(streams[mask] != expected_order[mask]):
        raise ValueError("reference Strahler order disagrees with donor branches")

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:145 ---
@_m4_reference_routing_dataclass(frozen=True)
class ReferenceRoutingResult:
    backend: str
    version: str
    config: ReferenceRoutingConfig
    receiver: _m4_reference_routing_np.ndarray
    order_downstream_first: _m4_reference_routing_np.ndarray
    upstream_area_m2: _m4_reference_routing_np.ndarray
    basin_id: _m4_reference_routing_np.ndarray
    stream_order: _m4_reference_routing_np.ndarray
    terrain_identity: str
    boundary_identity: str
    valid_mask: _m4_reference_routing_np.ndarray
    cell_area_m2: float
    outlet_kind: _m4_reference_routing_np.ndarray
    metadata: _m4_reference_routing_Mapping

    def __post_init__(self):
        if self.backend != "irregular_graph" or self.version != BACKEND_VERSION:
            raise ValueError("reference backend must be irregular_graph==" + BACKEND_VERSION)
        if not isinstance(self.config, ReferenceRoutingConfig):
            raise ValueError("ReferenceRoutingConfig required")
        _sha(self.terrain_identity)
        _sha(self.boundary_identity)
        area = _number(self.cell_area_m2, "cell_area_m2")
        if area <= 0.:
            raise ValueError("positive cell area required")
        arrays = {name: getattr(self, name) for name in ARRAY_NAMES}
        _check_arrays(arrays, area)
        for name, value in arrays.items():
            object.__setattr__(self, name, _m4_reference_routing_readonly(value))
        object.__setattr__(self, "cell_area_m2", area)
        if not isinstance(self.metadata, _m4_reference_routing_Mapping):
            raise ValueError("reference metadata mapping required")
        details = _plain(self.metadata)
        if details.get("mode") == "preserved_td_graph":
            _sha(details.get("source_graph_identity_sha256"))
        elif details.get("mode") != "recomputed_dem_policy":
            raise ValueError("reference mode must declare whether TD topology is retained")
        object.__setattr__(self, "metadata", _freeze(details))

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:186 ---
def _inputs(terrain, boundary):
    from terrain_pipeline.common_infra import BoundaryGrid as _m4_reference_routing_BoundaryGrid
    from terrain_pipeline.common_infra import TerrainGrid as _m4_reference_routing_TerrainGrid
    if not isinstance(terrain, _m4_reference_routing_TerrainGrid) or not isinstance(boundary, _m4_reference_routing_BoundaryGrid):
        raise TypeError("TerrainGrid and BoundaryGrid required")
    if terrain.elevation_m.shape != boundary.kind.shape or terrain.elevation_m.size < 2:
        raise ValueError("matching grid with at least two cells required")

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:193 ---
def _transform(terrain):
    from affine import Affine
    return Affine(terrain.dx_m, 0., terrain.x0_m - terrain.dx_m / 2.,
                  0., -terrain.dz_m, -terrain.z0_m + terrain.dz_m / 2.)

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:199 ---
def _analyze(terrain, boundary, receiver, order, kinds, config, details):
    mask = terrain.valid_mask.ravel()
    size = mask.size
    upstream = mask.astype(_m4_reference_routing_np.float64) * terrain.cell_area_m2
    basin = _m4_reference_routing_np.full(size, -1, _m4_reference_routing_np.int64)
    stream = mask.astype(_m4_reference_routing_np.int64)
    maximum = _m4_reference_routing_np.zeros(size, _m4_reference_routing_np.int64)
    multiplicity = _m4_reference_routing_np.zeros(size, _m4_reference_routing_np.int64)
    for cell in order:
        target = receiver[cell]
        basin[cell] = cell if target < 0 else basin[target]
    for cell in order[::-1]:
        stream[cell] = max(1, maximum[cell]) + (multiplicity[cell] >= 2)
        target = receiver[cell]
        if target >= 0:
            upstream[target] += upstream[cell]
            if stream[cell] > maximum[target]:
                maximum[target], multiplicity[target] = stream[cell], 1
            elif stream[cell] == maximum[target]:
                multiplicity[target] += 1
    details = dict(details, transform=list(_transform(terrain)),
        coordinates="native metric control-cell accounts on irregular graph",
        accumulation="exact sum of dx_m*dz_m per valid original control cell",
        basin_id_semantics="downstream terminal cell_id; not wet lake footprint")
    return ReferenceRoutingResult("irregular_graph", BACKEND_VERSION, config,
        _m4_reference_routing_np.asarray(receiver, _m4_reference_routing_np.int64), _m4_reference_routing_np.asarray(order, _m4_reference_routing_np.int64), upstream, basin, stream,
        terrain.identity_sha256, boundary.identity_sha256, terrain.valid_mask,
        terrain.cell_area_m2, kinds, details)

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:229 ---
def analyze_td_graph(terrain, boundary, graph):
    """Preserve arbitrary verified receiver edges without raster encoding."""
    from terrain_pipeline.common_infra import RoutingGraph as _m4_reference_routing_RoutingGraph
    _inputs(terrain, boundary)
    if not isinstance(graph, _m4_reference_routing_RoutingGraph):
        raise TypeError("RoutingGraph required")
    if (graph.terrain_identity_sha256 != terrain.identity_sha256
            or graph.boundary_identity_sha256 != boundary.identity_sha256
            or not _m4_reference_routing_np.array_equal(graph.valid_mask, terrain.valid_mask)):
        raise ValueError("graph source, boundary or valid mask differs")
    return _analyze(terrain, boundary, graph.receiver, graph.order_downstream_first,
        graph.outlet_kind, ReferenceRoutingConfig(),
        {"mode": "preserved_td_graph", "api": "shared_irregular_graph_analysis",
         "source_graph_identity_sha256": graph.identity_sha256, "routing_policy": graph.policy,
         "boundary_policy": "receiver and terminal kinds preserved"})

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:245 ---
def run_reference_routing(terrain, boundary, config=ReferenceRoutingConfig()):
    """Route the declared explicit boundary with the shared irregular core."""
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import route_graph as route_graph
    _inputs(terrain, boundary)
    if not isinstance(config, ReferenceRoutingConfig):
        raise TypeError("ReferenceRoutingConfig required")
    if not terrain.valid_mask.all():
        raise ValueError("masked nodata requires preserved graph analysis")
    perimeter = _m4_reference_routing_np.zeros(terrain.valid_mask.shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    if (_m4_reference_routing_np.any(boundary.kind[perimeter] != "open_outflow")
            or _m4_reference_routing_np.any(boundary.kind[~perimeter] != "interior")):
        raise ValueError("reference routing requires an explicitly open perimeter")
    if config.max_depth != -1.:
        raise ValueError("bounded-depth external routing was retired")
    if _m4_reference_routing_np.any(terrain.elevation_m == config.nodata):
        raise ValueError("nodata sentinel collides with a valid elevation")
    outlets = perimeter.copy()
    if config.outlets == "min":
        cells = _m4_reference_routing_np.flatnonzero(perimeter)
        outlets[:] = False
        outlets.ravel()[cells[_m4_reference_routing_np.argmin(terrain.elevation_m.ravel()[cells])]] = True
    mesh = grid_mesh(terrain.valid_mask.shape, x0_m=terrain.x0_m, z0_m=terrain.z0_m,
        dx_m=terrain.dx_m, dz_m=terrain.dz_m,
        world_seed=terrain.generation_seed if terrain.generation_seed is not None else 20261020)
    routed = route_graph(terrain.elevation_m, outlets, mesh)
    kinds = _m4_reference_routing_np.full(terrain.elevation_m.size, "interior", dtype="U24")
    kinds[outlets.ravel()] = "reference_edge_exit"
    return _analyze(terrain, boundary, routed.receiver, routed.order, kinds, config,
        {"mode": "recomputed_dem_policy", "api": "irregular_drainage.route_graph",
         "source_graph_identity_sha256": None, "routing_policy": "irregular_priority_flood_v1",
         "boundary_policy": "declared edge/min explicit outlets", "work_surface_only": True})

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:281 ---
def metadata(result):
    return _plain(result.metadata)

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:285 ---
def result_to_record(result):
    from terrain_pipeline.common_infra import identity as _m4_reference_routing_identity
    arrays = {name: getattr(result, name) for name in ARRAY_NAMES}
    meta = {"schema": REFERENCE_SCHEMA, "backend": result.backend, "version": result.version,
            "config": _m4_reference_routing_asdict(result.config), "cell_area_m2": result.cell_area_m2,
            "terrain_identity_sha256": result.terrain_identity,
            "boundary_identity_sha256": result.boundary_identity,
            "details": metadata(result), **dict.fromkeys(CAPABILITIES, False)}
    return {"arrays": arrays, "metadata": meta, "identity_sha256": _m4_reference_routing_identity(arrays, meta)}

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:295 ---
def validate_reference_record(record):
    from terrain_pipeline.common_infra import identity as _m4_reference_routing_identity
    arrays, meta = record["arrays"], record["metadata"]
    keys = {"schema", "backend", "version", "config", "cell_area_m2", "terrain_identity_sha256",
            "boundary_identity_sha256", "details", *CAPABILITIES}
    if (set(meta) != keys or set(arrays) != set(ARRAY_NAMES) or meta["schema"] != REFERENCE_SCHEMA
            or any(meta[name] is not False for name in CAPABILITIES)
            or record["identity_sha256"] != _m4_reference_routing_identity(arrays, meta)):
        raise ValueError("reference record schema, identity or capability mismatch")
    ReferenceRoutingResult(backend=meta["backend"], version=meta["version"],
                           config=ReferenceRoutingConfig(**meta["config"]),
                           terrain_identity=meta["terrain_identity_sha256"],
                           boundary_identity=meta["boundary_identity_sha256"],
                           cell_area_m2=meta["cell_area_m2"], metadata=meta["details"], **arrays)

# --- terrain_pipeline/surface_rivers/metric_reference_routing.py:310 ---
def compare_reference_to_td(reference, td_graph):
    from terrain_pipeline.common_infra import RoutingGraph as _m4_reference_routing_RoutingGraph
    if not isinstance(reference, ReferenceRoutingResult) or not isinstance(td_graph, _m4_reference_routing_RoutingGraph):
        raise TypeError("ReferenceRoutingResult and RoutingGraph required")
    if reference.terrain_identity != td_graph.terrain_identity_sha256:
        raise ValueError("terrain identity differs")
    if reference.boundary_identity != td_graph.boundary_identity_sha256:
        raise ValueError("boundary identity differs")
    if not _m4_reference_routing_np.array_equal(reference.valid_mask, td_graph.valid_mask):
        raise ValueError("valid mask or grid shape differs")
    flat_valid = reference.valid_mask.ravel()
    area = flat_valid.astype(_m4_reference_routing_np.float64) * reference.cell_area_m2
    terminal = _m4_reference_routing_np.full(area.size, -1, dtype=_m4_reference_routing_np.int64)
    for cell in td_graph.order_downstream_first:
        target = td_graph.receiver[cell]
        terminal[cell] = cell if target < 0 else terminal[target]
    for cell in td_graph.order_downstream_first[::-1]:
        target = td_graph.receiver[cell]
        if target >= 0:
            area[target] += area[cell]
    differences = {"receiver": reference.receiver != td_graph.receiver,
                   "terminal_cell": reference.basin_id != terminal,
                   "upstream_area_m2": ~_m4_reference_routing_np.isclose(reference.upstream_area_m2, area, rtol=1e-10, atol=1e-8)}
    counts = {name: int(_m4_reference_routing_np.count_nonzero(difference & flat_valid)) for name, difference in differences.items()}
    return {"status": "diagnostic_comparison_not_td_certification",
            "reference_mode": reference.metadata["mode"], "td_policy": td_graph.policy,
            "valid_cells": int(flat_valid.sum()), "mismatch_counts": counts,
            "mismatch_ratios": {name: value / int(flat_valid.sum()) for name, value in counts.items()},
            "maximum_area_difference_m2": float(_m4_reference_routing_np.max(abs(reference.upstream_area_m2 - area))),
            "orders_valid": True, "order_comparison": "topological permutations need not be identical",
            "equivalent_boundary_policy": reference.metadata["mode"] == "preserved_td_graph"}

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:16 ---
COMPARISON_SCHEMA = "terragenesis-metric-routing-comparison-v2"

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:17 ---
POLICIES = ("original_bed_irregular", "priority_flood_irregular", "metric_flat_irregular")

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:18 ---
KINDS = ("interior", "inactive", "open_outflow", "closed_wall", "prescribed_stage",
         "prescribed_discharge", "unknown_boundary", "lake_preserved")

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:20 ---
_CODES = {name: index for index, name in enumerate(KINDS)}

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:21 ---
_KNOWN_OUTLETS = ("open_outflow", "prescribed_stage", "prescribed_discharge")

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:22 ---
_EXPLICIT = _KNOWN_OUTLETS + ("unknown_boundary",)

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:23 ---
def comparison_neighbors(cell, mesh):
    for edge in range(mesh.indptr[cell], mesh.indptr[cell + 1]):
        yield int(mesh.indices[edge]), float(mesh.edge_length_m[edge])

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:28 ---
def route_priority_flood(terrain: _m4_routing_comparison_TerrainGrid, boundary: _m4_routing_comparison_BoundaryGrid) -> dict:
    """Fill only a working surface toward known outlets, then diagnose its irregular graph."""
    from terrain_pipeline.common_infra import RoutingGraph as _m4_routing_comparison_RoutingGraph
    from terrain_pipeline.common_infra import readonly as _m4_routing_comparison_readonly
    original = route_diagnostic(terrain, boundary)
    mesh = diagnostic_mesh(terrain)
    raw = terrain.elevation_m
    valid = terrain.valid_mask
    working = raw.copy()
    visited = _m4_routing_comparison_np.zeros(valid.size, bool)
    unknown_catchment = _m4_routing_comparison_np.zeros(valid.size, bool)
    for cell in original.order_downstream_first:
        target = original.receiver[cell]
        unknown_catchment[cell] = (original.outlet_kind[cell] == "unknown_boundary"
                                   if target < 0 else unknown_catchment[target])
    heap = []
    for cell in _m4_routing_comparison_np.flatnonzero(valid.ravel() & _m4_routing_comparison_np.isin(boundary.kind.ravel(), _KNOWN_OUTLETS)):
        visited[cell] = True
        _m4_routing_comparison_heapq.heappush(heap, (float(raw.ravel()[cell]), int(cell)))
    flat = working.ravel()
    while heap:
        level, cell = _m4_routing_comparison_heapq.heappop(heap)
        for target, _ in comparison_neighbors(cell, mesh):
            if visited[target] or unknown_catchment[target]:
                continue
            visited[target] = True
            flat[target] = max(float(flat[target]), level)
            _m4_routing_comparison_heapq.heappush(heap, (float(flat[target]), target))
    # Unvisited components lack a known exit. Their original beds remain intact.
    revised = _m4_routing_comparison_TerrainGrid(working, valid, **{name: getattr(terrain, name)
                           for name in _m4_routing_comparison_TerrainGrid.__dataclass_fields__
                           if name not in ("elevation_m", "valid_mask")})
    graph = route_diagnostic(revised, boundary)
    graph = _m4_routing_comparison_RoutingGraph(graph.receiver, graph.order_downstream_first, graph.valid_mask,
                         graph.edge_length_m, graph.edge_slope, graph.outlet_kind, graph.lake_id,
                         terrain.identity_sha256, boundary.identity_sha256,
                         policy="priority_flood_working_bed_irregular_v2")
    fill = working - raw
    return {"working_elevation_m": _m4_routing_comparison_readonly(working), "fill_depth_m": _m4_routing_comparison_readonly(fill),
            "flood_reached_mask": _m4_routing_comparison_readonly(visited.reshape(valid.shape)),
            "unknown_catchment_excluded_mask": _m4_routing_comparison_readonly(unknown_catchment.reshape(valid.shape)),
            "graph": graph,
            "metadata": {"policy": graph.policy,
                         "original_bed_graph_identity_sha256": original.identity_sha256,
                         "terrain_identity_sha256": terrain.identity_sha256,
                         "boundary_identity_sha256": boundary.identity_sha256,
                         "flood_reached_valid_cells": int(visited.sum()),
                         "unreached_valid_cells": int(valid.sum() - visited.sum()),
                         "unknown_catchment_excluded_cells": int(unknown_catchment.sum()),
                         "unknown_catchment_policy": "preserve_original_bed_and_exclude_from_known_outlet_flood",
                         "filled_cell_count": int(_m4_routing_comparison_np.count_nonzero(fill > 0.)),
                         "maximum_fill_m": float(fill.max()),
                         "filled_volume_m3": float(_m4_routing_comparison_np.sum(fill[valid], dtype=_m4_routing_comparison_np.float64)
                                                   * terrain.cell_area_m2),
                         "work_surface_only": True, "natural_outlet_verified": False}}

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:83 ---
def _route_metric_flat(terrain, boundary):
    """Original bed with metric shortest-path plateau routing on the same graph."""
    return route_diagnostic(terrain, boundary, flat_distance_strategy="metric_distance")

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:87 ---
def _encode(kinds):
    if not _m4_routing_comparison_np.isin(kinds, KINDS).all():
        raise ValueError("unsupported boundary or outlet kind")
    return _m4_routing_comparison_np.fromiter((_CODES[str(value)] for value in kinds.ravel()),
                       dtype=_m4_routing_comparison_np.uint8, count=kinds.size).reshape(kinds.shape)

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:94 ---
def _decode(codes):
    if codes.dtype != _m4_routing_comparison_np.uint8 or _m4_routing_comparison_np.any(codes >= len(KINDS)):
        raise ValueError("invalid kind codes")
    return _m4_routing_comparison_np.asarray(KINDS, dtype="U24")[codes]

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:100 ---
def _graph_arrays(prefix, graph):
    receiver = graph.receiver
    donor_ids = _m4_routing_comparison_np.flatnonzero(receiver >= 0).astype(_m4_routing_comparison_np.int64)
    donor_ids = donor_ids[_m4_routing_comparison_np.argsort(receiver[donor_ids], kind="stable")]
    offsets = _m4_routing_comparison_np.zeros(receiver.size + 1, _m4_routing_comparison_np.int64)
    offsets[1:] = _m4_routing_comparison_np.cumsum(_m4_routing_comparison_np.bincount(receiver[donor_ids], minlength=receiver.size))
    return {prefix + "_receiver": receiver,
            prefix + "_order": graph.order_downstream_first,
            prefix + "_edge_length_m": graph.edge_length_m,
            prefix + "_edge_slope": graph.edge_slope,
            prefix + "_outlet_kind_code": _encode(graph.outlet_kind),
            prefix + "_lake_id": graph.lake_id,
            prefix + "_donor_offsets": offsets,
            prefix + "_donor_ids": donor_ids}

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:116 ---
def comparison_summary(graph):
    kinds = graph.outlet_kind
    return {name: int(_m4_routing_comparison_np.count_nonzero(kinds == name)) for name in
            ("open_outflow", "prescribed_stage", "prescribed_discharge",
             "unknown_boundary", "lake_preserved")}

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:123 ---
def compare_routing_policies(terrain: _m4_routing_comparison_TerrainGrid, boundary: _m4_routing_comparison_BoundaryGrid) -> dict:
    """Save raw-bed, flood working-bed, and metric plateau irregular routing."""
    from terrain_pipeline.common_infra import identity as _m4_routing_comparison_identity
    original = route_diagnostic(terrain, boundary)
    flooded = route_priority_flood(terrain, boundary)
    graphs = {"original_bed_irregular": original, "priority_flood_irregular": flooded["graph"],
              "metric_flat_irregular": _route_metric_flat(terrain, boundary)}
    arrays = {"elevation_m": terrain.elevation_m, "valid_mask": terrain.valid_mask,
              "boundary_kind_code": _encode(boundary.kind),
              "boundary_allow_inflow": boundary.allow_inflow,
              "working_elevation_m": flooded["working_elevation_m"],
              "fill_depth_m": flooded["fill_depth_m"],
              "flood_reached_mask": flooded["flood_reached_mask"],
              "unknown_catchment_excluded_mask": flooded["unknown_catchment_excluded_mask"]}
    for field in ("stage_m", "discharge_m3_s"):
        value = getattr(boundary, field)
        if value is not None:
            arrays["boundary_" + field] = value
    for name, graph in graphs.items():
        arrays.update(_graph_arrays(name, graph))
    policies = {name: {"policy": graph.policy,
                       "graph_identity_sha256": graph.identity_sha256,
                       "terminal_counts": comparison_summary(graph),
                       "tie_break": "steepest_metric_slope_then_cell_id; plateau_bfs_distance_then_cell_id"
                       if name != "metric_flat_irregular" else
                       "steepest_metric_slope_then_cell_id; plateau_metric_distance_then_cell_id",
                       "adjacency": "restricted_Delaunay_unknown_supercover" if name == "metric_flat_irregular"
                       else "restricted_Delaunay_unknown_supercover",
                       "relation_to_frozen_td_d4":
                       "independent_metric_plateau_not_frozen_td_hierarchy" if name == "metric_flat_irregular"
                       else "independent_diagnostic"} for name, graph in graphs.items()}
    metadata = {"schema": COMPARISON_SCHEMA, "terrain": terrain.metadata(),
                "terrain_identity_sha256": terrain.identity_sha256,
                "boundary": {"source_id": boundary.source_id,
                             "source_sha256": boundary.source_sha256},
                "boundary_identity_sha256": boundary.identity_sha256,
                "policies": policies, "flood": flooded["metadata"],
                "flood_heap_tie_break": "working_height_then_cell_id",
                "fill_is_working_surface_only": True,
                "lake_id_semantics": "contributing_catchment_not_wet_lake_footprint",
                "hydraulic_ready": False, "natural_outlet_verified": False,
                "publishable": False}
    return {"arrays": arrays, "metadata": metadata,
            "identity_sha256": _m4_routing_comparison_identity(arrays, metadata)}

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:168 ---
def _terrain_boundary(bundle):
    from terrain_pipeline.common_infra import BoundaryGrid as _m4_routing_comparison_BoundaryGrid
    from terrain_pipeline.common_infra import TerrainGrid as _m4_routing_comparison_TerrainGrid
    arrays, meta = bundle["arrays"], bundle["metadata"]
    terrain = _m4_routing_comparison_TerrainGrid(arrays["elevation_m"], arrays["valid_mask"], **{
        key: value for key, value in meta["terrain"].items()
        if key in _m4_routing_comparison_TerrainGrid.__dataclass_fields__ and key not in ("elevation_m", "valid_mask")})
    boundary = _m4_routing_comparison_BoundaryGrid(_decode(arrays["boundary_kind_code"]),
                            arrays["boundary_allow_inflow"], meta["boundary"]["source_id"],
                            meta["boundary"]["source_sha256"],
                            stage_m=arrays.get("boundary_stage_m"),
                            discharge_m3_s=arrays.get("boundary_discharge_m3_s"))
    return terrain, boundary

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:181 ---
def decode_routing_comparison(bundle) -> dict[str, _m4_routing_comparison_RoutingGraph]:
    """Reconstruct pinned graphs without running any routing algorithm."""
    arrays, meta = bundle["arrays"], bundle["metadata"]
    terrain, boundary = _terrain_boundary(bundle)
    result = {}
    for name in POLICIES:
        policy = meta["policies"][name]
        graph = _m4_routing_comparison_RoutingGraph(arrays[name + "_receiver"], arrays[name + "_order"],
                             arrays["valid_mask"], arrays[name + "_edge_length_m"],
                             arrays[name + "_edge_slope"],
                             _decode(arrays[name + "_outlet_kind_code"]),
                             arrays[name + "_lake_id"], terrain.identity_sha256,
                             boundary.identity_sha256, policy=policy["policy"])
        if graph.identity_sha256 != policy["graph_identity_sha256"]:
            raise ValueError("saved graph identity mismatch: " + name)
        result[name] = graph
    return result

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:200 ---
def validate_routing_comparison(bundle):
    from terrain_pipeline.common_infra import identity as _m4_routing_comparison_identity
    arrays, meta = bundle["arrays"], bundle["metadata"]
    metadata_keys = {"schema", "terrain", "terrain_identity_sha256", "boundary",
                     "boundary_identity_sha256", "policies", "flood", "flood_heap_tie_break",
                     "fill_is_working_surface_only", "lake_id_semantics", "hydraulic_ready",
                     "natural_outlet_verified", "publishable"}
    required = {"elevation_m", "valid_mask", "boundary_kind_code",
                "boundary_allow_inflow", "working_elevation_m", "fill_depth_m",
                "flood_reached_mask", "unknown_catchment_excluded_mask"}
    for name in POLICIES:
        required.update(name + "_" + field for field in
                        ("receiver", "order", "edge_length_m", "edge_slope",
                         "outlet_kind_code", "lake_id", "donor_offsets", "donor_ids"))
    optional = {"boundary_stage_m", "boundary_discharge_m3_s"}
    if (set(meta) != metadata_keys or meta.get("schema") != COMPARISON_SCHEMA
            or set(meta.get("policies", {})) != set(POLICIES)
            or not required.issubset(arrays) or set(arrays) - required - optional
            or any(meta.get(key) is not False for key in
                   ("hydraulic_ready", "natural_outlet_verified", "publishable"))
            or meta.get("fill_is_working_surface_only") is not True
            or meta.get("lake_id_semantics") != "contributing_catchment_not_wet_lake_footprint"
            or meta.get("flood_heap_tie_break") != "working_height_then_cell_id"
            or bundle["identity_sha256"] != _m4_routing_comparison_identity(arrays, meta)):
        raise ValueError("routing comparison metadata or identity mismatch")
    terrain, boundary = _terrain_boundary(bundle)
    if (meta["terrain_identity_sha256"] != terrain.identity_sha256
            or meta["boundary_identity_sha256"] != boundary.identity_sha256
            or meta["terrain"] != terrain.metadata()):
        raise ValueError("routing comparison terrain or boundary linkage mismatch")
    working, fill = arrays["working_elevation_m"], arrays["fill_depth_m"]
    reached = arrays["flood_reached_mask"]
    excluded = arrays["unknown_catchment_excluded_mask"]
    if (working.shape != terrain.elevation_m.shape or working.dtype != _m4_routing_comparison_np.float64
            or fill.shape != working.shape or fill.dtype != _m4_routing_comparison_np.float64
            or reached.shape != working.shape or reached.dtype != bool
            or excluded.shape != working.shape or excluded.dtype != bool
            or not _m4_routing_comparison_np.isfinite(working).all() or not _m4_routing_comparison_np.isfinite(fill).all()
            or _m4_routing_comparison_np.any(fill < 0.) or not _m4_routing_comparison_np.allclose(fill, working - terrain.elevation_m,
                                                   rtol=0., atol=1e-10)
            or _m4_routing_comparison_np.any(reached & ~terrain.valid_mask)
            or _m4_routing_comparison_np.any(reached & excluded)
            or _m4_routing_comparison_np.any(excluded & ~terrain.valid_mask)
            or _m4_routing_comparison_np.any(reached & (boundary.kind == "unknown_boundary"))
            or _m4_routing_comparison_np.any(fill[~reached] != 0.)):
        raise ValueError("working surface or fill depth differs from original bed")
    known = terrain.valid_mask & _m4_routing_comparison_np.isin(boundary.kind, _KNOWN_OUTLETS)
    flood = meta["flood"]
    if (_m4_routing_comparison_np.any(known & ~reached)
            or flood.get("policy") != "priority_flood_working_bed_irregular_v2"
            or flood.get("terrain_identity_sha256") != terrain.identity_sha256
            or flood.get("boundary_identity_sha256") != boundary.identity_sha256
            or flood.get("flood_reached_valid_cells") != int(reached.sum())
            or flood.get("unreached_valid_cells") != int(terrain.valid_mask.sum() - reached.sum())
            or flood.get("unknown_catchment_excluded_cells") != int(excluded.sum())
            or flood.get("unknown_catchment_policy")
            != "preserve_original_bed_and_exclude_from_known_outlet_flood"
            or flood.get("filled_cell_count") != int(_m4_routing_comparison_np.count_nonzero(fill > 0.))
            or flood.get("maximum_fill_m") != float(fill.max())
            or not _m4_routing_comparison_math.isclose(flood.get("filled_volume_m3", float("nan")),
                                float(_m4_routing_comparison_np.sum(fill[terrain.valid_mask], dtype=_m4_routing_comparison_np.float64)
                                      * terrain.cell_area_m2), rel_tol=1e-12, abs_tol=1e-9)
            or flood.get("work_surface_only") is not True
            or flood.get("natural_outlet_verified") is not False):
        raise ValueError("saved flood reachability or fill accounting differs")
    graphs = decode_routing_comparison(bundle)
    mesh = diagnostic_mesh(terrain)
    contact = unknown_contacts(terrain.valid_mask, diagnostic_mesh(terrain, unmasked=True)).ravel()
    original = graphs["original_bed_irregular"]
    if flood.get("original_bed_graph_identity_sha256") != original.identity_sha256:
        raise ValueError("flood original-bed policy identity differs")
    expected_excluded = _m4_routing_comparison_np.zeros(original.receiver.size, bool)
    for cell in original.order_downstream_first:
        target = original.receiver[cell]
        expected_excluded[cell] = (original.outlet_kind[cell] == "unknown_boundary"
                                   if target < 0 else expected_excluded[target])
    if not _m4_routing_comparison_np.array_equal(excluded.ravel(), expected_excluded):
        raise ValueError("unknown catchment exclusion differs from original-bed graph")
    valid = terrain.valid_mask.ravel()
    explicit = valid & _m4_routing_comparison_np.isin(boundary.kind.ravel(), _EXPLICIT)
    for name, graph in graphs.items():
        prefix = name + "_"
        policy = meta["policies"][name]
        expected_policy = ("original_bed_irregular_plateau_bfs_v2" if name == "original_bed_irregular"
                           else "priority_flood_working_bed_irregular_v2" if name == "priority_flood_irregular"
                           else "original_bed_irregular_plateau_metric_distance_v2")
        expected_tie = ("steepest_metric_slope_then_cell_id; plateau_metric_distance_then_cell_id"
                        if name == "metric_flat_irregular" else
                        "steepest_metric_slope_then_cell_id; plateau_bfs_distance_then_cell_id")
        if (policy["policy"] != expected_policy or policy.get("tie_break") != expected_tie
                or policy.get("adjacency") != ("restricted_Delaunay_unknown_supercover" if name == "metric_flat_irregular"
                                                  else "restricted_Delaunay_unknown_supercover")):
            raise ValueError("saved routing policy declaration differs")
        donor_ids = arrays[prefix + "donor_ids"]
        offsets = arrays[prefix + "donor_offsets"]
        expected = _graph_arrays(name, graph)
        if (donor_ids.dtype != _m4_routing_comparison_np.int64 or offsets.dtype != _m4_routing_comparison_np.int64
                or not _m4_routing_comparison_np.array_equal(donor_ids, expected[prefix + "donor_ids"])
                or not _m4_routing_comparison_np.array_equal(offsets, expected[prefix + "donor_offsets"])
                or comparison_summary(graph) != meta["policies"][name]["terminal_counts"]):
            raise ValueError("saved donor CSR or terminal counts differ")
        if (_m4_routing_comparison_np.any(graph.receiver[explicit] != -1)
                or _m4_routing_comparison_np.any(graph.outlet_kind[explicit] != boundary.kind.ravel()[explicit])):
            raise ValueError("explicit boundary terminal differs")
        terminal = valid & (graph.receiver < 0)
        implicit = _m4_routing_comparison_np.flatnonzero(terminal & ~explicit)
        rows, cols = terrain.elevation_m.shape
        valid_grid = terrain.valid_mask
        for cell in implicit:
            if graph.outlet_kind[cell] not in ("lake_preserved", "unknown_boundary"):
                raise ValueError("implicit terminal claims open outflow")
            if graph.outlet_kind[cell] == "unknown_boundary":
                touching = bool(contact[cell])
                if not touching:
                    raise ValueError("unknown terminal has no unknown terrain contact")
        lake_terminals = implicit[graph.outlet_kind[implicit] == "lake_preserved"]
        if (_m4_routing_comparison_np.any(graph.lake_id[lake_terminals] != lake_terminals)
                or _m4_routing_comparison_np.any(graph.lake_id[terminal & (graph.outlet_kind != "lake_preserved")] != -1)):
            raise ValueError("lake terminal ID differs from contributing basin")
        donors = _m4_routing_comparison_np.flatnonzero(graph.receiver >= 0)
        targets = graph.receiver[donors]
        if _m4_routing_comparison_np.any(graph.lake_id[donors] != graph.lake_id[targets]):
            raise ValueError("lake catchment ID differs from downstream terminal")
        if not receiver_edges_valid(graph.receiver, mesh):
            raise ValueError("saved routing edge is absent from the masked irregular graph")
        bed = working.ravel() if name == "priority_flood_irregular" else terrain.elevation_m.ravel()
        distance = _m4_routing_comparison_np.hypot(mesh.node_x_m[targets] - mesh.node_x_m[donors],
                            mesh.node_z_m[targets] - mesh.node_z_m[donors])
        drop = bed[donors] - bed[targets]
        if (_m4_routing_comparison_np.any(drop < -1e-10)
                or not _m4_routing_comparison_np.allclose(graph.edge_length_m[donors], distance, rtol=0., atol=1e-10)
                or not _m4_routing_comparison_np.allclose(graph.edge_slope[donors], drop / distance,
                                   rtol=1e-12, atol=1e-12)):
            raise ValueError("saved graph disagrees with its declared bed geometry")
    if (meta["policies"]["metric_flat_irregular"]["relation_to_frozen_td_d4"]
            != "independent_metric_plateau_not_frozen_td_hierarchy"):
        raise ValueError("metric plateau policy falsely claims frozen hierarchy identity")

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:338 ---
def save_routing_comparison(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _m4_routing_comparison_save_bundle
    _m4_routing_comparison_save_bundle(path, bundle, validator=validate_routing_comparison)

# --- terrain_pipeline/surface_rivers/metric_routing_comparison.py:342 ---
def load_routing_comparison(path, *, expected_sha256, expected_identity=None):
    from terrain_pipeline.common_infra import load_bundle as _m4_routing_comparison_load_bundle
    bundle = _m4_routing_comparison_load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_routing_comparison, max_bytes=512 * 1024 * 1024)
    if expected_identity is not None and bundle["identity_sha256"] != expected_identity:
        raise ValueError("routing comparison identity differs from external pin")
    return bundle

# --- terrain_pipeline/new_world_native_lowland.py:24 ---
@_m4_new_world_native_lowland_njit
def channels_and_capture(order, receiver, labels, anchors, area, lowland, ocean, unknown, valid, flow, channel, capture):
    for j in range(order.size - 1, -1, -1):
        i = order[j]
        p = labels[i]
        eligible = valid[i] and not ocean[i] and not unknown[i] and flow[i] >= .015 * 1296000 and (p < 0 or anchors[p] == i)
        if eligible:
            threshold = 4000000 if lowland[i] else 810000
            if area[i] * 900 >= threshold:
                channel[i] = True
            if channel[i]:
                target = receiver[i]
                if target >= 0:
                    channel[target] = True
        else:
            channel[i] = False
    for j in range(order.size):
        i = order[j]
        if channel[i]:
            capture[i] = i
        elif receiver[i] >= 0:
            capture[i] = capture[receiver[i]]
        else:
            capture[i] = -1

# --- terrain_pipeline/new_world_native_lowland.py:49 ---
def lowland_digest(path):
    return _m4_new_world_native_lowland_hashlib.sha256(_m4_new_world_native_lowland_Path(path).read_bytes()).hexdigest()

# --- terrain_pipeline/new_world_native_lowland.py:53 ---
_m4_default_native_lowland_root = object()

def run(*, root=_m4_default_native_lowland_root, output=None):
    if root is _m4_default_native_lowland_root:
        from terrain_pipeline.new_world_game_hydrology import ROOT
        root = ROOT
    from terrain_pipeline.new_world_game_hydrology import IDENTITY as _m4_new_world_native_lowland_IDENTITY
    from terrain_pipeline.runoff import LowlandRunoffConfig as _m4_new_world_native_lowland_LowlandRunoffConfig
    from terrain_pipeline.runoff import lowland_geometry as _m4_new_world_native_lowland_lowland_geometry
    start = _m4_new_world_native_lowland_time.monotonic()
    root = _m4_new_world_native_lowland_Path(root)
    terrain = root / 'terrain-v3'; event = root / 'native-event-v1'; route = root / 'native-final-routing-v1'
    source = _m4_new_world_native_lowland_json.loads((terrain / 'manifest.json').read_text(encoding='utf8'))
    water = _m4_new_world_native_lowland_json.loads((event / 'manifest.json').read_text(encoding='utf8'))
    if source['identity'] != _m4_new_world_native_lowland_IDENTITY or water['source_identity'] != _m4_new_world_native_lowland_IDENTITY or water['spacing_m'] != 30:
        raise ValueError('source binding mismatch')
    out = _m4_new_world_native_lowland_Path(output or root / 'native-lowland-v1')
    out.mkdir(exist_ok=False)
    load = lambda p: _m4_new_world_native_lowland_np.load(p, mmap_mode='r', allow_pickle=False)
    bed = load(terrain / 'bed_m.npy'); shape = bed.shape; n = bed.size
    ocean, unknown, valid = (load(terrain / (x + '.npy')).ravel() for x in ('ocean_mask','unknown_mask','valid_mask'))
    order, receiver = (load(route / 'routing' / (x+'.npy')) for x in ('order','receiver'))
    labels, anchors = (load(route / 'derived' / (x+'.npy')) for x in ('pool_index','pool_anchor'))
    flow = load(event / 'node_water_m3.npy')[1]
    lowland = _m4_new_world_native_lowland_np.lib.format.open_memmap(out/'lowland_mask.npy',mode='w+',dtype='?',shape=shape)
    config = _m4_new_world_native_lowland_LowlandRunoffConfig(upland_initiation_area_m2=810000.)
    halo = int(_m4_new_world_native_lowland_np.ceil(config.relief_radius_m / 30)) + 1
    for a in range(0,shape[0],128):
        b = min(a+128,shape[0]); lo = max(0,a-halo); hi = min(shape[0],b+halo)
        _, _, mask = _m4_new_world_native_lowland_lowland_geometry(_m4_new_world_native_lowland_np.asarray(bed[lo:hi]),30,config)
        lowland[a:b] = mask[a-lo:b-lo]
    lowland.flush()
    area = _m4_new_world_native_lowland_np.lib.format.open_memmap(out/'contributing_cells.npy',mode='w+',dtype='i4',shape=(n,))
    for a in range(0,n,262144):
        b = min(a+262144,n)
        area[a:b] = valid[a:b] & ~ocean[a:b] & ~unknown[a:b]
    accumulate_inplace(order,receiver,area); area.flush()
    channel = _m4_new_world_native_lowland_np.lib.format.open_memmap(out/'channel_mask.npy',mode='w+',dtype='?',shape=shape)
    capture = _m4_new_world_native_lowland_np.lib.format.open_memmap(out/'capture_index.npy',mode='w+',dtype='i4',shape=shape)
    channels_and_capture(order,receiver,labels,anchors,area,lowland.ravel(),ocean,unknown,valid,flow,channel.ravel(),capture.ravel())
    channel.flush(); capture.flush()
    # Fixed physical window uses inclusive control-cell centers.
    x0,x1,z0,z1 = 1176,2843,1382,3049
    sl = _m4_new_world_native_lowland_np.s_[z0:z1,x0:x1]
    land_count = 0; captured = 0; terminal_area = 0
    for a in range(0,n,262144):
        b=min(a+262144,n); land=valid[a:b] & ~ocean[a:b] & ~unknown[a:b]
        land_count += int(land.sum()); captured += int(_m4_new_world_native_lowland_np.count_nonzero(land & (capture.ravel()[a:b] >= 0)))
        dest=receiver[a:b]; target=_m4_new_world_native_lowland_np.maximum(dest,0); terminal=(dest<0) | ocean[target] | unknown[target] | ~valid[target]
        terminal_area += int(area[a:b][land & terminal].sum(dtype=_m4_new_world_native_lowland_np.int64))
    record = dict(schema='native-lowland-v1',source_identity=_m4_new_world_native_lowland_IDENTITY,terrain_manifest_sha256=lowland_digest(terrain/'manifest.json'),event_manifest_sha256=lowland_digest(event/'manifest.json'),routing_binding_sha256=lowland_digest(route/'binding.json'), source_paths=dict(terrain=str(terrain),event=str(event),routing=str(route)),shape_zx=list(shape),spacing_m=30,origin_center_m=[-61440,-61440],cell_area_m2=900,interval=1,config=dict(upland_initiation_area_m2=810000,lowland_initiation_area_m2=4000000,relief_radius_m=300,lowland_relief_m=20,lowland_slope=.025,q_threshold_m3_s=.015),window_bounds_xz_m=[-26170,23830,-19990,30010],window_counts=dict(channel_cells=int(channel[sl].sum()),lowland_cells=int(lowland[sl].sum()),lowland_land_cells=int(_m4_new_world_native_lowland_np.count_nonzero(lowland[sl] & valid.reshape(shape)[sl] & ~ocean.reshape(shape)[sl] & ~unknown.reshape(shape)[sl]))),counts=dict(channel_cells=int(channel.sum()),land_cells=land_count,captured_land_cells=captured,terminal_contributing_cells=terminal_area),budgets_unchanged=water['budgets'],algorithm='saved receiver area initiation and downstream closure gated by actual interval 2 flow; pool interiors excluded except overflow anchor',runtime_seconds=_m4_new_world_native_lowland_time.monotonic()-start)
    if terminal_area != land_count: raise ValueError('contributing area does not close')
    tmp=out/'manifest.tmp'; tmp.write_text(_m4_new_world_native_lowland_json.dumps(record,indent=2),encoding='utf8'); _m4_new_world_native_lowland_os.replace(tmp,out/'manifest.json')
    return record

# --- terrain_pipeline/new_world_stage1_flood_phases.py:111 ---
def flood_phase_digest(path):
    h = _m4_new_world_stage1_flood_phases_hashlib.sha256()
    with _m4_new_world_stage1_flood_phases_Path(path).open('rb') as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()

# --- terrain_pipeline/new_world_stage1_flood_phases.py:119 ---
def atomic_json(path, data):
    path = _m4_new_world_stage1_flood_phases_Path(path)
    temp = path.with_suffix('.tmp')
    with temp.open('w', encoding='utf8') as f:
        _m4_new_world_stage1_flood_phases_json.dump(data, f, indent=2, sort_keys=True)
        f.flush()
        _m4_new_world_stage1_flood_phases_os.fsync(f.fileno())
    _m4_new_world_stage1_flood_phases_os.replace(temp, path)

# --- terrain_pipeline/new_world_stage1_flood_phases.py:129 ---
def authenticate(terrain, graph, expected):
    terrain, graph = _m4_new_world_stage1_flood_phases_Path(terrain), _m4_new_world_stage1_flood_phases_Path(graph)
    source = _m4_new_world_stage1_flood_phases_json.loads((terrain / 'manifest.json').read_text(encoding='utf8'))
    gm = _m4_new_world_stage1_flood_phases_json.loads((graph / 'manifest.json').read_text(encoding='utf8'))
    if source['identity'] != expected or gm['source_identity'] != expected or gm['source_manifest_sha256'] != flood_phase_digest(terrain / 'manifest.json'):
        raise ValueError('source identity mismatch')
    if source['shape_zx'] != gm['shape_zx'] or source['origin_native_xz'] != gm['origin_native_xz']:
        raise ValueError('graph source mismatch')
    for name in ('bed_m', 'valid_mask', 'ocean_mask', 'unknown_mask'):
        if flood_phase_digest(terrain / (name + '.npy')) != source['files'][name]:
            raise ValueError('source hash mismatch: ' + name)
    for name, expected_hash in gm['files_sha256'].items():
        if flood_phase_digest(graph / name) != expected_hash:
            raise ValueError('graph hash mismatch: ' + name)
    return source, gm

# --- terrain_pipeline/new_world_stage1_flood_phases.py:146 ---
def mapped(root, name, mode='r'):
    return _m4_new_world_stage1_flood_phases_np.load(_m4_new_world_stage1_flood_phases_Path(root) / (name + '.npy'), mmap_mode=mode, allow_pickle=False)

# --- terrain_pipeline/new_world_stage1_flood_phases.py:150 ---
def create(root, name, dtype, n):
    return _m4_new_world_stage1_flood_phases_np.lib.format.open_memmap(_m4_new_world_stage1_flood_phases_Path(root) / (name + '.npy'), mode='w+', dtype=dtype, shape=(n,))

# --- terrain_pipeline/new_world_stage1_flood_phases.py:154 ---
def close(*arrays):
    for a in arrays:
        if a.flags.writeable:
            a.flush()
        a._mmap.close()

# --- terrain_pipeline/new_world_stage1_flood_phases.py:161 ---
def phase_a(terrain, graph, root, expected):
    source, gm = authenticate(terrain, graph, expected)
    root = _m4_new_world_stage1_flood_phases_Path(root)
    root.mkdir(parents=True, exist_ok=True)
    shape = source['shape_zx']
    n = int(_m4_new_world_stage1_flood_phases_np.prod(shape))
    bed, valid, ocean, unknown = (mapped(terrain, name) for name in ('bed_m', 'valid_mask', 'ocean_mask', 'unknown_mask'))
    outlets = create(root, 'outlets', '?', n)
    for start in range(0, n, 65536):
        end = min(start + 65536, n)
        outlets[start:end] = (ocean.flat[start:end] | unknown.flat[start:end]) & valid.flat[start:end]
    o = outlets.reshape(shape)
    o[0, :] |= valid[0, :]; o[-1, :] |= valid[-1, :]
    o[:, 0] |= valid[:, 0]; o[:, -1] |= valid[:, -1]
    close(ocean, unknown)
    ptr, edges = (mapped(graph, name) for name in ('indptr', 'indices'))
    filled, order, rank, discovered, heap_level, heap_node = (create(root, name, dtype, n) for name, dtype in
        [('filled','f8'), ('order','i8'), ('rank','i8'), ('discovered','?'), ('heap_level','f8'), ('heap_node','i8')])
    flood_order(bed.reshape(-1), outlets, valid.reshape(-1), ptr, edges, filled, order, rank, discovered, heap_level, heap_node)
    close(bed, valid, ptr, edges, outlets, filled, order, rank, discovered, heap_level, heap_node)
    names = ('outlets', 'filled', 'order', 'rank', 'discovered', 'heap_level', 'heap_node')
    record = {'phase': 'A', 'source_manifest': flood_phase_digest(_m4_new_world_stage1_flood_phases_Path(terrain) / 'manifest.json'), 'graph_manifest': flood_phase_digest(_m4_new_world_stage1_flood_phases_Path(graph) / 'manifest.json'), 'files': {name: flood_phase_digest(root / (name + '.npy')) for name in names}}
    atomic_json(root / 'phase_a.json', record)
    validate_a(terrain, graph, root, expected)
    for name in ('discovered', 'heap_level', 'heap_node'):
        if flood_phase_digest(root / (name + '.npy')) != record['files'][name]:
            raise ValueError('checkpoint hash mismatch: ' + name)
    for name in ('discovered', 'heap_level', 'heap_node'):
        (root / (name + '.npy')).unlink()

# --- terrain_pipeline/new_world_stage1_flood_phases.py:192 ---
def validate_a(terrain, graph, root, expected):
    authenticate(terrain, graph, expected)
    root = _m4_new_world_stage1_flood_phases_Path(root)
    record = _m4_new_world_stage1_flood_phases_json.loads((root / 'phase_a.json').read_text(encoding='utf8'))
    if record['source_manifest'] != flood_phase_digest(_m4_new_world_stage1_flood_phases_Path(terrain) / 'manifest.json') or record['graph_manifest'] != flood_phase_digest(_m4_new_world_stage1_flood_phases_Path(graph) / 'manifest.json'):
        raise ValueError('checkpoint provenance mismatch')
    for name in ('outlets', 'filled', 'order', 'rank'):
        if flood_phase_digest(root / (name + '.npy')) != record['files'][name]:
            raise ValueError('checkpoint hash mismatch: ' + name)

# --- terrain_pipeline/new_world_stage1_flood_phases.py:203 ---
def phase_b(terrain, graph, root, expected):
    validate_a(terrain, graph, root, expected)
    root = _m4_new_world_stage1_flood_phases_Path(root)
    valid = mapped(terrain, 'valid_mask')
    outlets, filled, order, rank = (mapped(root, name) for name in ('outlets', 'filled', 'order', 'rank'))
    x, z, ptr, edges = (mapped(graph, name) for name in ('node_x_m', 'node_z_m', 'indptr', 'indices'))
    receiver = create(root, 'receiver', 'i8', valid.size)
    select_receivers(outlets, valid.reshape(-1), x, z, ptr, edges, filled, order, rank, receiver)
    close(valid, outlets, filled, order, rank, x, z, ptr, edges, receiver)
    atomic_json(root / 'phase_b.json', {'phase': 'B', 'files': {name: flood_phase_digest(root / (name + '.npy')) for name in ('filled', 'order', 'rank', 'receiver')}, 'implementation_sha256': flood_phase_digest(__file__), 'reference_sha256': flood_phase_digest(_m4_new_world_stage1_flood_phases_Path(__file__).with_name('new_world_stage1.py'))})

# --- terrain_pipeline/world_acceptance_processes.py:157 ---
@_m4_world_acceptance_processes_njit(cache=True)
def pool_labels(bed, filled, indptr, indices):
    """Connected equal-spill-level positive-fill cells are level pools."""
    labels = _m4_world_acceptance_processes_np.full(bed.size, -1, _m4_world_acceptance_processes_np.int64)
    stack = _m4_world_acceptance_processes_np.empty(bed.size, _m4_world_acceptance_processes_np.int64)
    count = 0
    for start in range(bed.size):
        if labels[start] >= 0 or filled[start] <= bed[start]:
            continue
        labels[start] = count
        stack[0] = start
        size = 1
        while size:
            size -= 1
            cell = stack[size]
            for edge in range(indptr[cell], indptr[cell + 1]):
                target = indices[edge]
                if (labels[target] < 0 and filled[target] > bed[target]
                        and filled[target] == filled[start]):
                    labels[target] = count
                    stack[size] = target
                    size += 1
        count += 1
    return labels, count

# --- terrain_pipeline/world_acceptance_processes.py:183 ---
@_m4_world_acceptance_processes_njit(cache=True)
def route_pool_interval(local_volume, order, receiver, labels, anchors, capacity, storage):
    """Collapse each pool at its downstream flood-rank anchor, releasing overflow."""
    flow = local_volume.copy()
    incoming = _m4_world_acceptance_processes_np.zeros(capacity.size)
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

def label_pools(bed, filled, indptr, indices, *, valid=None, ocean=None,
                unknown=None, exclude_ocean=False, exclude_unknown=False,
                require_equal_level=True, labels=None, stack=None):
    """Label positive-fill components with the caller's original exclusion rules.

    A supplied valid mask always excludes invalid cells. Ocean and unknown masks
    are consulted only when their explicit exclusion flags are set.
    """
    import numpy as np
    bed = np.asarray(bed).reshape(-1)
    filled = np.asarray(filled).reshape(-1)
    eligible = filled > bed
    if valid is not None:
        eligible &= np.asarray(valid).reshape(-1)
    if exclude_ocean and ocean is not None:
        eligible &= ~np.asarray(ocean).reshape(-1)
    if exclude_unknown and unknown is not None:
        eligible &= ~np.asarray(unknown).reshape(-1)
    if labels is None:
        labels = np.full(bed.size, -1, np.int64)
    else:
        labels[:] = -1
    if stack is None:
        stack = np.empty(bed.size, np.int64)
    count = 0
    for start in range(bed.size):
        if labels[start] >= 0 or not eligible[start]:
            continue
        labels[start] = count
        stack[0] = start
        size = 1
        while size:
            size -= 1
            cell = stack[size]
            for edge in range(indptr[cell], indptr[cell + 1]):
                target = indices[edge]
                if (labels[target] < 0 and eligible[target]
                        and (not require_equal_level or filled[target] == filled[start])):
                    labels[target] = count
                    stack[size] = target
                    size += 1
        count += 1
    return labels, count

# The surface_rivers package re-exports route/accumulate during initialization.
# Resolve its result classes only after those declarations exist.
from terrain_pipeline.surface_rivers.contracts import AccumulationResult as _m4_drainage_AccumulationResult
from terrain_pipeline.surface_rivers.contracts import RoutingResult as _m4_drainage_RoutingResult
