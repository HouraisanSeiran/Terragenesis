"""Deterministic original-bed D8 routing and instantaneous diagnostic discharge."""

from collections import deque
import heapq
import math

import numpy as np

from .metric_contracts import BoundaryGrid, RoutingGraph, TerrainGrid


_OFFSETS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1),
            (1, -1), (1, 0), (1, 1))
_EXPLICIT_OUTLETS = ("open_outflow", "prescribed_stage", "prescribed_discharge", "unknown_boundary")


def route_diagnostic(terrain: TerrainGrid, boundary: BoundaryGrid) -> RoutingGraph:
    """Route on unchanged bed elevations; closed flats remain lake catchments."""
    if not isinstance(terrain, TerrainGrid) or not isinstance(boundary, BoundaryGrid):
        raise TypeError("TerrainGrid and BoundaryGrid required")
    height = terrain.elevation_m
    valid = terrain.valid_mask
    kind = boundary.kind
    if kind.shape != height.shape:
        raise ValueError("boundary shape differs from terrain")
    if np.any((~valid) & (kind != "unknown_boundary")):
        raise ValueError("invalid terrain cells must be unknown_boundary")

    rows, cols = height.shape
    n = height.size
    flat_height = height.ravel()
    flat_valid = valid.ravel()
    flat_kind = kind.ravel()
    receiver = np.full(n, -1, dtype=np.int64)
    edge_length = np.zeros(n, dtype=np.float64)
    edge_slope = np.zeros(n, dtype=np.float64)
    outlet_kind = np.full(n, "interior", dtype="U24")
    outlet_kind[~flat_valid] = "inactive"
    unknown_contact = np.zeros(n, dtype=bool)
    fringe = np.zeros(n, dtype=bool)

    def neighbors(cell):
        row, col = divmod(cell, cols)
        for dr, dc in _OFFSETS:
            rr, cc = row + dr, col + dc
            if not (0 <= rr < rows and 0 <= cc < cols):
                continue
            target = rr * cols + cc
            if not flat_valid[target]:
                continue
            # A diagonal cannot cross either orthogonal unknown corner cell.
            if dr and dc and (not valid[row + dr, col] or not valid[row, col + dc]):
                continue
            distance = math.hypot(dc * terrain.dx_m, dr * terrain.dz_m)
            yield target, distance

    for cell in np.flatnonzero(flat_valid):
        row, col = divmod(int(cell), cols)
        on_perimeter = row in (0, rows - 1) or col in (0, cols - 1)
        near_unknown = any(0 <= row + dr < rows and 0 <= col + dc < cols
                           and not valid[row + dr, col + dc] for dr, dc in _OFFSETS)
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
    visited = np.zeros(n, dtype=bool)
    for start in np.flatnonzero(flat_valid):
        if visited[start]:
            continue
        component = []
        queue = deque([int(start)])
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
        distance_to_seed = {cell: 0 for cell in seeds}
        queue = deque(sorted(seeds))
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
            candidates = [(target, length) for target, length in neighbors(cell)
                          if flat_height[target] == flat_height[cell]
                          and distance_to_seed[target] == distance - 1]
            target, length = min(candidates)
            receiver[cell] = target
            edge_length[cell] = length

    donors = [[] for _ in range(n)]
    terminals = []
    for cell in np.flatnonzero(flat_valid):
        target = receiver[cell]
        if target < 0:
            terminals.append(int(cell))
        else:
            donors[target].append(int(cell))
    heapq.heapify(terminals)
    order = []
    lake_id = np.full(n, -1, dtype=np.int64)
    while terminals:
        cell = heapq.heappop(terminals)
        order.append(cell)
        if outlet_kind[cell] == "lake_preserved":
            lake_id[cell] = cell
        elif receiver[cell] >= 0:
            lake_id[cell] = lake_id[receiver[cell]]
        for donor in donors[cell]:
            heapq.heappush(terminals, donor)
    if len(order) != int(valid.sum()):
        raise AssertionError("diagnostic receiver graph contains a cycle")
    return RoutingGraph(receiver, np.asarray(order, dtype=np.int64), valid,
                        edge_length, edge_slope, outlet_kind, lake_id,
                        terrain.identity_sha256, boundary.identity_sha256)


def accumulate_local_discharge(graph: RoutingGraph, local_q_m3_s: np.ndarray) -> dict:
    """Instantaneously sum local m3/s along the diagnostic graph."""
    if not isinstance(graph, RoutingGraph):
        raise TypeError("RoutingGraph required")
    local = np.asarray(local_q_m3_s, dtype=np.float64)
    if local.shape != graph.valid_mask.shape or not np.isfinite(local).all() or np.any(local < 0.):
        raise ValueError("local discharge must be finite nonnegative [z,x]")
    if np.any(local[~graph.valid_mask] != 0.):
        raise ValueError("invalid terrain cells cannot contribute discharge")
    flow = local.ravel().copy()
    for cell in graph.order_downstream_first[::-1]:
        target = graph.receiver[cell]
        if target >= 0:
            flow[target] += flow[cell]
    if not np.isfinite(flow).all():
        raise ValueError("routed discharge overflows float64")
    terminal = np.zeros(flow.size, dtype=np.float64)
    mask = graph.valid_mask.ravel() & (graph.receiver == -1)
    terminal[mask] = flow[mask]
    kinds = graph.outlet_kind

    def total(kind):
        value = float(np.sum(terminal[kinds == kind], dtype=np.float64))
        if not math.isfinite(value):
            raise ValueError("terminal discharge budget overflows float64")
        return value

    input_total = float(np.sum(local, dtype=np.float64))
    if not math.isfinite(input_total):
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
