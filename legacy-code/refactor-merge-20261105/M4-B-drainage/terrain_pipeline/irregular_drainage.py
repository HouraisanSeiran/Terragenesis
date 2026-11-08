"""Deterministic finite-volume drainage on an irregular Delaunay graph.

Each native cell owns one node and retains its original area and representative
bed elevation. The displaced node is a finite-volume representative position,
not a new terrain sample. Arrays retain native row-major cell account indices.
Window boundaries truncate the triangulation: callers must supply a sufficient
halo and keep unresolved external drainage explicit. Only supplied outlets drain.
"""

from dataclasses import dataclass
import heapq

import numpy as np
from numba import njit
from scipy.sparse import coo_matrix
from scipy.spatial import Delaunay


@dataclass(frozen=True)
class IrregularMesh:
    shape: tuple[int, int]
    origin_native_xz: tuple[int, int]
    spacing_m: float
    world_seed: int
    node_x_m: np.ndarray
    node_z_m: np.ndarray
    indptr: np.ndarray
    indices: np.ndarray
    edge_length_m: np.ndarray


@dataclass(frozen=True)
class GraphRouting:
    filled: np.ndarray
    order: np.ndarray
    rank: np.ndarray
    receiver: np.ndarray


def _mix64(value):
    value = value ^ (value >> np.uint64(30))
    value = value * np.uint64(0xBF58476D1CE4E5B9)
    value = value ^ (value >> np.uint64(27))
    value = value * np.uint64(0x94D049BB133111EB)
    return value ^ (value >> np.uint64(31))


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
    if len(shape) != 2 or any(not isinstance(v, (int, np.integer)) or v < 1 for v in shape):
        raise ValueError("shape must contain two positive integers")
    if len(origin_native_xz) != 2 or any(not isinstance(v, (int, np.integer)) for v in origin_native_xz):
        raise ValueError("origin_native_xz must contain two integers")
    if not np.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("spacing_m must be finite and positive")
    if not isinstance(world_seed, (int, np.integer)):
        raise ValueError("world_seed must be an integer")
    rows, cols = (int(v) for v in shape)
    origin_x, origin_z = (int(v) for v in origin_native_xz)
    native_x = np.tile(np.arange(cols, dtype=np.int64), rows) + origin_x
    native_z = np.repeat(np.arange(rows, dtype=np.int64), cols) + origin_z
    seed = np.uint64(int(world_seed) % (1 << 64))
    key = (_mix64(native_x.view(np.uint64) ^ np.uint64(0x632BE59BD9B4E019))
           ^ _mix64(native_z.view(np.uint64) ^ np.uint64(0x9E3779B97F4A7C15)) ^ seed)
    fraction_x = (_mix64(key ^ np.uint64(0xD1B54A32D192ED03)) >> np.uint64(11)).astype(np.float64) * (2.0 ** -53)
    fraction_z = (_mix64(key ^ np.uint64(0xABC98388FB8FAC03)) >> np.uint64(11)).astype(np.float64) * (2.0 ** -53)
    node_x = (native_x + 0.7 * (fraction_x - 0.5)) * spacing_m
    node_z = (native_z + 0.7 * (fraction_z - 0.5)) * spacing_m
    del native_x, native_z, key, fraction_x, fraction_z
    count = rows * cols
    if count == 1:
        indptr = np.array([0, 0], dtype=np.int32)
        indices = np.empty(0, dtype=np.int32)
    elif count == 2:
        indptr = np.array([0, 1, 2], dtype=np.int32)
        indices = np.array([1, 0], dtype=np.int32)
    elif min(rows, cols) == 1:
        degree = np.full(count, 2, dtype=np.int64)
        degree[0] = degree[-1] = 1
        indptr = np.concatenate((np.zeros(1, dtype=np.int64), np.cumsum(degree)))
        indices = np.empty(int(indptr[-1]), dtype=np.int32)
        indices[indptr[:-1][1:]] = np.arange(count - 1)
        indices[indptr[1:-1] - 1] = np.arange(1, count)
    else:
        indptr, indices = _bounded_adjacency(node_x, node_z, (rows, cols), spacing_m)
    edge_length = _edge_lengths(node_x, node_z, indptr, indices)
    for array in (node_x, node_z, indptr, indices, edge_length):
        array.flags.writeable = False
    return IrregularMesh((rows, cols), (origin_x, origin_z), float(spacing_m),
                         int(world_seed), node_x, node_z, indptr, indices, edge_length)


def _block_neighbors(node_x, node_z, shape, spacing_m, z0, x0, core_size):
    rows, cols = shape
    z1, x1 = min(rows, z0 + core_size), min(cols, x0 + core_size)
    hz0, hx0 = max(0, z0 - 8), max(0, x0 - 8)
    hz1, hx1 = min(rows, z1 + 8), min(cols, x1 + 8)
    local_shape = (hz1 - hz0, hx1 - hx0)
    local_x = node_x.reshape(shape)[hz0:hz1, hx0:hx1].ravel()
    local_z = node_z.reshape(shape)[hz0:hz1, hx0:hx1].ravel()
    points = np.column_stack((local_x - local_x[0], local_z - local_z[0]))
    triangulation = Delaunay(points)
    triangles = triangulation.simplices.copy()
    del triangulation
    first = points[triangles[:, 1]] - points[triangles[:, 0]]
    second = points[triangles[:, 2]] - points[triangles[:, 0]]
    cross = abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0])
    side_product = np.linalg.norm(first, axis=1) * np.linalg.norm(second, axis=1) * np.linalg.norm(first - second, axis=1)
    triangles = triangles[side_product <= 4 * spacing_m * cross]
    source = triangles[:, (0, 1, 1, 2, 2, 0)].ravel()
    target = triangles[:, (1, 0, 2, 1, 0, 2)].ravel()
    adjacency = coo_matrix((np.ones(source.size, dtype=np.uint8), (source, target)),
                           shape=(points.shape[0], points.shape[0])).tocsr()
    local_core = (np.arange(z0 - hz0, z1 - hz0)[:, None] * local_shape[1]
                  + np.arange(x0 - hx0, x1 - hx0)).ravel()
    core = (np.arange(z0, z1)[:, None] * cols + np.arange(x0, x1)).ravel()
    selected = adjacency[local_core]
    neighbors = ((selected.indices // local_shape[1] + hz0) * cols
                 + selected.indices % local_shape[1] + hx0).astype(np.int32)
    return core, np.diff(selected.indptr).astype(np.int64), neighbors


def _bounded_adjacency(node_x, node_z, shape, spacing_m, core_size=256):
    """Two bounded triangulation passes avoid Python objects per global node."""
    rows, cols = shape
    degree = np.empty(rows * cols, dtype=np.int64)
    for z0 in range(0, rows, core_size):
        for x0 in range(0, cols, core_size):
            core, local_degree, _ = _block_neighbors(node_x, node_z, shape, spacing_m,
                                                    z0, x0, core_size)
            degree[core] = local_degree
    indptr = np.concatenate((np.zeros(1, dtype=np.int64), np.cumsum(degree)))
    indices = np.empty(int(indptr[-1]), dtype=np.int32)
    for z0 in range(0, rows, core_size):
        for x0 in range(0, cols, core_size):
            core, local_degree, neighbors = _block_neighbors(node_x, node_z, shape,
                                                             spacing_m, z0, x0, core_size)
            row_start = np.cumsum(local_degree) - local_degree
            destinations = (np.repeat(indptr[core], local_degree) + np.arange(neighbors.size)
                            - np.repeat(row_start, local_degree))
            indices[destinations] = neighbors
    return indptr, indices


@njit(cache=True)
def _edge_lengths(node_x, node_z, indptr, indices):
    lengths = np.empty(indices.size, dtype=np.float64)
    for current in range(node_x.size):
        for edge in range(indptr[current], indptr[current + 1]):
            neighbor = indices[edge]
            lengths[edge] = np.hypot(node_x[current] - node_x[neighbor],
                                    node_z[current] - node_z[neighbor])
    return lengths


@njit(cache=True)
def _route(bed, outlets, indptr, indices, lengths):
    count = bed.size
    filled = bed.copy()
    discovered = outlets.copy()
    heap = [(filled[i], i) for i in range(count) if outlets[i]]
    heapq.heapify(heap)
    order = np.empty(count, dtype=np.int64)
    rank = np.empty(count, dtype=np.int64)
    visited = 0
    while heap:
        level, current = heapq.heappop(heap)
        rank[current] = visited
        order[visited] = current
        visited += 1
        for edge in range(indptr[current], indptr[current + 1]):
            neighbor = indices[edge]
            if discovered[neighbor]:
                continue
            discovered[neighbor] = True
            filled[neighbor] = max(filled[neighbor], level)
            heapq.heappush(heap, (filled[neighbor], np.int64(neighbor)))
    if visited != count:
        raise ValueError("Graph has a component without an explicit outlet")
    receiver = np.full(count, -1, dtype=np.int64)
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


def route_graph(bed, outlets, mesh: IrregularMesh) -> GraphRouting:
    """Flood a working surface and route by metric slope on CSR graph edges.

    Real bed remains unchanged. Equal working levels descend flood rank, making
    receiver edges acyclic; explicit outlets always retain receiver -1.
    """
    raw = np.asarray(bed, dtype=np.float64)
    terminal = np.asarray(outlets, dtype=np.bool_)
    if raw.shape != mesh.shape or terminal.shape != mesh.shape:
        raise ValueError("bed and outlets must match mesh shape")
    if not np.isfinite(raw).all() or not terminal.any():
        raise ValueError("bed must be finite and at least one explicit outlet is required")
    filled, order, rank, receiver = _route(raw.ravel(), terminal.ravel(), mesh.indptr,
                                          mesh.indices, mesh.edge_length_m)
    filled = filled.reshape(mesh.shape)
    for array in (filled, order, rank, receiver):
        array.flags.writeable = False
    return GraphRouting(filled, order, rank, receiver)


@njit(cache=True)
def _accumulate(receiver, order, local):
    flow = local.copy()
    for index in range(order.size - 1, -1, -1):
        current = order[index]
        downstream = receiver[current]
        if downstream >= 0:
            flow[downstream] += flow[current]
    return flow


def accumulate_graph(receiver, order, local_input):
    """Accumulate nonnegative volume/time per native cell without changing area."""
    local = np.asarray(local_input, dtype=np.float64)
    receiver = np.asarray(receiver, dtype=np.int64)
    order = np.asarray(order, dtype=np.int64)
    if receiver.shape != (local.size,) or order.shape != receiver.shape:
        raise ValueError("receiver and order must match local_input size")
    if not np.isfinite(local).all() or (local < 0).any():
        raise ValueError("local_input must be finite and nonnegative")
    if (receiver < -1).any() or (receiver >= local.size).any():
        raise ValueError("receiver indices are out of range")
    if (order < 0).any() or (order >= local.size).any() or np.any(np.bincount(order, minlength=local.size) != 1):
        raise ValueError("order must be a permutation")
    rank = np.empty(local.size, dtype=np.int64)
    rank[order] = np.arange(local.size)
    donors = np.flatnonzero(receiver >= 0)
    if np.any(rank[receiver[donors]] >= rank[donors]):
        raise ValueError("receivers must precede donors")
    flow = _accumulate(receiver, order, local.ravel()).reshape(local.shape)
    if not np.isfinite(flow).all():
        raise ValueError("Accumulated discharge overflows float64")
    return flow
