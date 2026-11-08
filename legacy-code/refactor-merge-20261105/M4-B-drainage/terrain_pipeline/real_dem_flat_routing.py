"""Raw-height irregular-graph routing with explicit closed-flat retention.

Global component and graph state are resident in memory. Tile access only
constructs the frozen strict-downhill baseline; no filling or terrain edits.
"""

from collections import deque

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, canonical_json
from terrain_pipeline.real_dem_surface_network import RealDemNetwork
from terrain_pipeline.real_dem_tiled_network import _arrays, build_tiled_network, candidate_mesh
from terrain_pipeline.irregular_grid import grid_mesh, masked_mesh, strict_receivers


ALGORITHM = "real-dem-equal-irregular-multisource-bfs-closed-min-root-v2"
POLICY = {"algorithm": ALGORITHM, "equal_height": "exact_float_equality",
          "flat_receiver_tie": "minimum_global_cell_id", "closed_component": "retain_at_minimum_cell_root",
          "order": "Kahn_FIFO_initial_zero_indegree_sorted_global_id",
          "global_graph_state": True, "terrain_filling": False,
          "natural_outlet_verified": False, "ocean_outlet_certified": False}


def _neighbors(shape, mesh=None, valid=None):
    mesh = grid_mesh(shape, dx_m=90.) if mesh is None else mesh
    if valid is not None:
        mesh = masked_mesh(mesh, valid)
    degree = np.diff(mesh.indptr)
    neighbors = np.full((int(np.prod(shape)), max(1, int(degree.max()))), -1, np.int64)
    for node in range(neighbors.shape[0]):
        neighbors[node, :degree[node]] = mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]
    return neighbors


def _equal_neighbors(neighbors, height, valid):
    safe = np.maximum(neighbors, 0)
    equal = (neighbors >= 0) & valid[safe] & valid[:, None] & (height[safe] == height[:, None])
    return np.where(equal, neighbors, -1)


def _risks(neighbors, valid, shape):
    unknown = np.any((neighbors >= 0) & ~valid[np.maximum(neighbors, 0)], axis=1)
    boundary = np.zeros(shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    return boundary.ravel(), unknown


def _order(receiver, valid):
    ids = np.flatnonzero(valid)
    targets = receiver[ids]
    indegree = np.bincount(targets[targets >= 0], minlength=len(valid))
    queue = deque(ids[indegree[ids] == 0].tolist())
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
    return np.asarray(order, np.int64)


def _accumulate(receiver, order, valid):
    accumulation = np.zeros(len(valid), np.float64)
    accumulation[valid] = 1.
    for source in order:
        target = receiver[source]
        if target >= 0:
            accumulation[target] += accumulation[source]
    return accumulation


def _record(component_id, cells, seeds, height, boundary, unknown, shape, distance):
    cell_rows, cell_cols = np.divmod(cells, shape[1])
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


def _summary(height_array, valid, raw, receiver, accumulation, records):
    ids = np.flatnonzero(valid)
    targets = receiver[ids]
    routed = targets >= 0
    height = height_array.ravel()
    strict = int(np.count_nonzero(height[targets[routed]] < height[ids[routed]]))
    terminals = ids[targets == -1]
    return {"raw_terminals": int(np.count_nonzero(raw[ids] == -1)), "resolved_terminals": len(terminals),
            "flat_rerouted_edges": int(np.count_nonzero(receiver[ids] != raw[ids])),
            "strict_downhill_edges": strict, "flat_edges": int(routed.sum()) - strict,
            "closed_component_count": sum(record["root_cell_id"] is not None for record in records),
            "draining_component_count": sum(record["root_cell_id"] is None for record in records),
            "valid_cells": len(ids), "unknown_cells": int((~valid).sum()),
            "contributing_cells_sum": int(accumulation[terminals].sum()),
            "source_height_sha256": array_hash(height_array), "source_height_unchanged": True,
            "algorithm_metadata": dict(POLICY), "natural_outlet_verified": False, "ocean_outlet_certified": False}


def resolve_dem_flats(candidate, *, tile_size=256, tile_order="row_major") -> dict:
    height_array, valid_array = _arrays(candidate)
    before = array_hash(height_array)
    raw_network = build_tiled_network(candidate, tile_size=tile_size, tile_order=tile_order)
    height, valid = height_array.ravel(), valid_array.ravel()
    raw = raw_network.receiver.ravel()
    mesh = raw_network.mesh
    neighbors = _neighbors(height_array.shape, mesh)
    equal_neighbors = _equal_neighbors(_neighbors(height_array.shape, mesh, valid_array), height, valid)
    boundary, unknown = _risks(neighbors, valid, height_array.shape)
    component = np.full(height.size, -1, np.int64)
    distance = np.full(height.size, -1, np.int64)
    receiver = raw.copy()
    records = []
    for start in np.flatnonzero(valid):
        if component[start] >= 0:
            continue
        component[start] = start
        queue = deque([int(start)])
        cells = []
        while queue:
            cell = queue.popleft()
            cells.append(cell)
            for target in equal_neighbors[cell]:
                if target >= 0 and component[target] < 0:
                    component[target] = start
                    queue.append(int(target))
        cells = np.asarray(cells, np.int64)
        seeds = np.sort(cells[raw[cells] >= 0])
        origins = seeds if len(seeds) else np.array([start], np.int64)
        distance[origins] = 0
        queue = deque(origins.tolist())
        while queue:
            cell = queue.popleft()
            for target in equal_neighbors[cell]:
                if target >= 0 and distance[target] < 0:
                    distance[target] = distance[cell] + 1
                    queue.append(int(target))
        for cell in cells[distance[cells] > 0]:
            adjacent = equal_neighbors[cell]
            eligible = adjacent[(adjacent >= 0) & (distance[np.maximum(adjacent, 0)] == distance[cell] - 1)]
            receiver[cell] = eligible.min()
        records.append(_record(int(start), cells, seeds, height, boundary, unknown, height_array.shape, distance))
    order = _order(receiver, valid)
    accumulation = _accumulate(receiver, order, valid)
    terminal = valid & (receiver == -1)
    network = RealDemNetwork(receiver.reshape(height_array.shape), order, accumulation.reshape(height_array.shape),
                             (terminal & boundary).reshape(height_array.shape),
                             (terminal & unknown).reshape(height_array.shape), mesh)
    if array_hash(height_array) != before:
        raise ValueError("source height changed")
    return {"network": network, "component_id": component.reshape(height_array.shape),
            "distance_to_exit": distance.reshape(height_array.shape), "components": records,
            "summary": _summary(height_array, valid, raw, receiver, accumulation, records)}


def validate_flat_routing(candidate, result) -> dict:
    """Check geometry and local shortest-distance witnesses without solver replay."""
    height_array, valid_array = _arrays(candidate)
    height, valid = height_array.ravel(), valid_array.ravel()
    shape = height_array.shape
    if not isinstance(result, dict) or set(result) != {"network", "component_id", "distance_to_exit", "components", "summary"}:
        raise ValueError("invalid flat routing result schema")
    network = result["network"]
    if not isinstance(network, RealDemNetwork):
        raise ValueError("RealDemNetwork required")
    for name, dtype in (("receiver", np.int64), ("accumulation_cells", np.float64),
                        ("boundary_outlet", bool), ("unknown_adjacent_terminal", bool)):
        values = getattr(network, name)
        if not isinstance(values, np.ndarray) or values.shape != shape or values.dtype != np.dtype(dtype):
            raise ValueError(f"invalid network {name}")
    for name in ("component_id", "distance_to_exit"):
        values = result[name]
        if not isinstance(values, np.ndarray) or values.shape != shape or values.dtype != np.dtype(np.int64):
            raise ValueError(f"invalid {name}")
    component, distance = result["component_id"].ravel(), result["distance_to_exit"].ravel()
    receiver = network.receiver.ravel()
    ids = np.flatnonzero(valid)
    if (np.any(component[~valid] != -1) or np.any(distance[~valid] != -1)
            or np.any((component[ids] < 0) | (component[ids] >= height.size)) or np.any(distance[ids] < 0)
            or np.any(receiver[~valid] != -1) or np.any((receiver < -1) | (receiver >= height.size))):
        raise ValueError("invalid unknown/range/component distance")
    mesh = network.mesh if network.mesh is not None else candidate_mesh(candidate)
    neighbors = _neighbors(shape, mesh)
    legal_neighbors = _neighbors(shape, mesh, valid_array)
    equal_neighbors = _equal_neighbors(legal_neighbors, height, valid)
    boundary, unknown = _risks(neighbors, valid, shape)
    raw, _, _ = strict_receivers(height_array, masked_mesh(mesh, valid_array), valid_mask=valid_array)
    routed_sources = ids[receiver[ids] >= 0]
    targets = receiver[routed_sources]
    if (np.any(~valid[targets]) or np.any(height[targets] > height[routed_sources])
            or np.any(~np.any(legal_neighbors[routed_sources] == targets[:, None], axis=1))):
        raise ValueError("receiver must be a valid non-uphill irregular edge")
    if np.any(receiver[raw >= 0] != raw[raw >= 0]):
        raise ValueError("raw strictly downhill receiver must be preserved")
    flat = height[targets] == height[routed_sources]
    if (np.any(component[targets[flat]] != component[routed_sources[flat]])
            or np.any(distance[targets[flat]] != distance[routed_sources[flat]] - 1)):
        raise ValueError("flat receiver distance/rank must decrease")
    visited = np.zeros(height.size, bool)
    records = []
    for start in ids:
        if visited[start]:
            continue
        queue = deque([int(start)])
        visited[start] = True
        cells = []
        while queue:
            cell = queue.popleft()
            cells.append(cell)
            if component[cell] != start:
                raise ValueError("equal-height component geometry/minimum ID mismatch")
            adjacent = equal_neighbors[cell]
            adjacent = adjacent[adjacent >= 0]
            if np.any(abs(distance[adjacent] - distance[cell]) > 1):
                raise ValueError("distance is not shortest BFS distance")
            for target in adjacent:
                if not visited[target]:
                    visited[target] = True
                    queue.append(int(target))
        cells = np.asarray(cells, np.int64)
        seeds = np.sort(cells[raw[cells] >= 0])
        origins = seeds if len(seeds) else np.array([start], np.int64)
        if not np.array_equal(np.sort(cells[distance[cells] == 0]), origins):
            raise ValueError("distance zero seeds/closed root mismatch")
        for cell in cells[distance[cells] > 0]:
            adjacent = equal_neighbors[cell]
            eligible = adjacent[(adjacent >= 0) & (distance[np.maximum(adjacent, 0)] == distance[cell] - 1)]
            if not len(eligible) or receiver[cell] != eligible.min():
                raise ValueError("flat BFS witness/receiver minimum-ID tie mismatch")
        if not len(seeds) and receiver[start] != -1:
            raise ValueError("closed retention root must remain terminal")
        records.append(_record(int(start), cells, seeds, height, boundary, unknown, shape, distance))
    if canonical_json(result["components"]) != canonical_json(records):
        raise ValueError("component records/risk/seed semantics mismatch")
    order = network.order
    if (not isinstance(order, np.ndarray) or order.dtype != np.dtype(np.int64) or order.ndim != 1
            or not np.array_equal(np.sort(order), ids)):
        raise ValueError("invalid order coverage")
    rank = np.full(height.size, -1, np.int64)
    rank[order] = np.arange(len(order))
    if np.any(rank[routed_sources] >= rank[targets]):
        raise ValueError("order/rank must be upstream first")
    if not np.array_equal(order, _order(receiver, valid)):
        raise ValueError("order must match deterministic Kahn FIFO")
    accumulation = _accumulate(receiver, order, valid)
    if not np.array_equal(network.accumulation_cells.ravel(), accumulation):
        raise ValueError("accumulation/contribution mismatch")
    terminal = valid & (receiver == -1)
    if (not np.array_equal(network.boundary_outlet.ravel(), terminal & boundary)
            or not np.array_equal(network.unknown_adjacent_terminal.ravel(), terminal & unknown)):
        raise ValueError("terminal risk mismatch")
    summary = _summary(height_array, valid, raw, receiver, accumulation, records)
    if summary["contributing_cells_sum"] != len(ids) or canonical_json(result["summary"]) != canonical_json(summary):
        raise ValueError("summary/source height/conservation mismatch")
    return {"verified": True, "summary": summary, "natural_outlet_verified": False,
            "ocean_outlet_certified": False, "global_graph_state": True}
