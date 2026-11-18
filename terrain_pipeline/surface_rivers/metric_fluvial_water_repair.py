"""Explicit native loop-jump flux repair and inlet weight boundary."""

from contextlib import contextmanager
import heapq
from functools import lru_cache

from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import segments_clear as segments_clear
import numpy as np

WATER_REPAIR_MECHANISMS = {
    "loop_relocation": "irregular-graph-wet-connection-native-flux-v2",
    "inlet_weights": "row0-inlet-upstream-weight-mask-v1",
}


class WaterRoutingRepair:
    """Apply repairs independently of the optional detailed observer."""

    def __init__(self):
        self.iterations = []

    def begin(self, model):
        self.current = {"step_index": int(model.time_iter), "iteration": len(self.iterations) % model._itermax,
            "native_relocations": 0, "accepted_connections": 0, "accepted_graph_steps": 0,
            "rejected_connections": {}, "out_of_domain_transitions": 0, "steps": 0}
        self.boundary_seen = np.zeros(model._Np_water, dtype=bool)
        self.iterations.append(self.current)

    def adjacent(self, model, current, proposal):
        active = current > 0
        invalid = (proposal < 0) | (proposal >= model.L * model.W)
        self.current["out_of_domain_transitions"] += int(np.count_nonzero(active & invalid))

    def boundary(self, indices, boundary):
        self.boundary_seen |= boundary & (indices > 0)
        self.last_boundary = boundary

    @contextmanager
    def native_loop_calls(self, model):
        import importlib
        native = importlib.import_module("pyDeltaRCM.water_tools")
        original = native._check_for_loops

        def repaired(walk, proposal, step, inlet_length, center, stage_above_sea):
            before = proposal.copy()
            returned, flags = original(walk, proposal, step, inlet_length, center, stage_above_sea)
            observer = getattr(model, "water_routing_diagnostic", None)
            if observer is not None:
                for parcel in np.flatnonzero(before != returned):
                    observer.current["native_relocations"].append((int(step), int(parcel),
                        int(before[parcel]), int(returned[parcel]), int(flags[parcel])))
            decisions = repair_loop_returns(before, returned, model.depth, model.cell_type,
                model.dry_depth, model.account_water_relocation_segment,
                mesh=_repair_mesh(tuple(model.depth.shape), int(getattr(model, "seed", 20261020))))
            self.current["native_relocations"] += len(decisions)
            for decision in decisions:
                if decision[-1] == "accepted":
                    self.current["accepted_connections"] += 1
                    self.current["accepted_graph_steps"] += decision[3]
                else:
                    rejected = self.current["rejected_connections"]
                    rejected[decision[-1]] = rejected.get(decision[-1], 0) + 1
            if observer is not None:
                observer.current["repair_decisions"].extend((int(step), *decision) for decision in decisions)
            self.current["steps"] = int(step)
            self.last_returned = returned.copy()
            return returned, flags

        native._check_for_loops = repaired
        try:
            yield
        finally:
            native._check_for_loops = original

    def finish(self):
        self.current["boundary_parcels"] = int(self.boundary_seen.sum())
        self.current["active_at_end"] = int(np.count_nonzero((self.last_returned > 0) & ~self.last_boundary))


@lru_cache(maxsize=4)
def _repair_mesh(shape, world_seed):
    return grid_mesh(shape, dx_m=1., world_seed=world_seed)


def graph_connection(start, end, width, *, shape, mesh=None):
    """Deterministic metric shortest connection on actual graph edges."""
    mesh = _repair_mesh(tuple(shape), 20261020) if mesh is None else mesh
    if not 0 <= start < np.prod(shape) or not 0 <= end < np.prod(shape):
        return [divmod(int(start), width), divmod(int(end), width)]
    distance = {int(start): 0.}
    previous = {}
    queue = [(0., int(start))]
    while queue:
        length, node = heapq.heappop(queue)
        if length != distance[node]:
            continue
        if node == end:
            path = [node]
            while path[-1] != start:
                path.append(previous[path[-1]])
            return [divmod(int(cell), width) for cell in reversed(path)]
        for edge in range(mesh.indptr[node], mesh.indptr[node + 1]):
            target = int(mesh.indices[edge])
            candidate = length + float(mesh.edge_length_m[edge])
            if candidate < distance.get(target, np.inf):
                distance[target], previous[target] = candidate, node
                heapq.heappush(queue, (candidate, target))
    raise ValueError("irregular connection has no path")




def connection_rejection(path, depth, cell_type, dry_depth):
    def reason(row, column):
        if not (0 <= row < depth.shape[0] and 0 <= column < depth.shape[1]):
            return "outside_domain"
        if cell_type[row, column] == -2:
            return "wall_or_invalid"
        if not depth[row, column] > dry_depth:
            return "dry"
        return None

    for row, column in path:
        rejected = reason(row, column)
        if rejected:
            return rejected
    nodes = np.asarray([row * depth.shape[1] + column for row, column in path], np.int64)
    if not np.all(segments_clear(nodes[:-1], nodes[1:], cell_type != -2)):
        return "crossed_wall_or_invalid"
    if not np.all(segments_clear(nodes[:-1], nodes[1:], depth > dry_depth)):
        return "crossed_dry"
    return None


def account_connection(path, width, native_update_Q, mesh):
    """Account continuous graph segments through the native flux updater."""
    for (r0, c0), (r1, c1) in zip(path, path[1:]):
        first, second = r0 * width + c0, r1 * width + c1
        dr = mesh.node_z_m[second] - mesh.node_z_m[first]
        dc = mesh.node_x_m[second] - mesh.node_x_m[first]
        native_update_Q(np.array([np.hypot(dr, dc)]), np.array([r0 * width + c0], dtype=np.int64),
            np.array([r1 * width + c1], dtype=np.int64), np.array([True]),
            np.array([dr]), np.array([dc]),
            update_current=True, update_next=True)


def repair_loop_returns(proposal, returned, depth, cell_type, dry_depth, native_update_Q, *, mesh=None):
    """Keep native flags externally; reject only the unsafe relocation itself."""
    decisions = []
    width = depth.shape[1]
    mesh = _repair_mesh(tuple(depth.shape), 20261020) if mesh is None else mesh
    for parcel in np.flatnonzero(proposal != returned):
        start, end = int(proposal[parcel]), int(returned[parcel])
        path = graph_connection(start, end, width, shape=depth.shape, mesh=mesh)
        rejected = connection_rejection(path, depth, cell_type, dry_depth)
        if rejected:
            returned[parcel] = start
        else:
            account_connection(path, width, native_update_Q, mesh)
        decisions.append((int(parcel), start, end, len(path) - 1, rejected or "accepted"))
    return decisions


def mask_inlet_upstream_weights(weights, jwalk_flat, cell_type):
    """Only row0 inlet cells: forbid upstream native weight choices in every weight branch."""
    columns = np.flatnonzero(cell_type[0] == 1)
    upstream = jwalk_flat < 0
    changed_cells = 0
    removed_weight = 0.
    staged = np.empty((len(columns), weights.shape[2]), dtype=weights.dtype)
    for index, column in enumerate(columns):
        staged[index] = weights[0, column]
    for index, column in enumerate(columns):
        row_weights = staged[index]
        if not np.all(np.isfinite(row_weights)) or not np.all(row_weights >= 0.):
            raise ValueError("row0 inlet has non-finite or negative water weight")
        removed = float(row_weights[upstream].sum())
        changed_cells += int(removed > 0.)
        removed_weight += removed
        row_weights[upstream] = 0.
        total = float(row_weights.sum())
        if not total > 0. or not np.isfinite(total):
            raise ValueError("row0 inlet has no legal non-upstream water weight")
        row_weights /= total
    for index, column in enumerate(columns):
        weights[0, column] = staged[index]
    return {"inlet_cells": len(columns), "changed_cells": changed_cells,
            "removed_upstream_weight_sum": removed_weight}
