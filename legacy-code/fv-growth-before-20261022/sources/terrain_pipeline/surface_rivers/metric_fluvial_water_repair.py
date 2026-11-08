"""Explicit native loop-jump flux repair and inlet weight boundary."""

from contextlib import contextmanager
import numpy as np

WATER_REPAIR_MECHANISMS = {
    "loop_relocation": "deterministic-d8-wet-connection-native-flux-v1",
    "inlet_weights": "row0-inlet-upstream-weight-mask-v1",
}


class WaterRoutingRepair:
    """Apply repairs independently of the optional detailed observer."""

    def __init__(self):
        self.iterations = []

    def begin(self, model):
        self.current = {"step_index": int(model.time_iter), "iteration": len(self.iterations) % model._itermax,
            "native_relocations": 0, "accepted_connections": 0, "accepted_d8_steps": 0,
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
                model.dry_depth, model.account_water_relocation_segment)
            self.current["native_relocations"] += len(decisions)
            for decision in decisions:
                if decision[-1] == "accepted":
                    self.current["accepted_connections"] += 1
                    self.current["accepted_d8_steps"] += decision[3]
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


def d8_connection(start, end, width):
    """Chebyshev-minimal deterministic Bresenham connection, endpoints included."""
    row, column = divmod(int(start), width)
    last_row, last_column = divmod(int(end), width)
    dr, dc = abs(last_row - row), abs(last_column - column)
    sr, sc = 1 if row < last_row else -1, 1 if column < last_column else -1
    error = dc - dr
    path = []
    while True:
        path.append((row, column))
        if (row, column) == (last_row, last_column):
            return path
        twice = error * 2
        if twice > -dr:
            error -= dr
            column += sc
        if twice < dc:
            error += dc
            row += sr


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
    for (r0, c0), (r1, c1) in zip(path, path[1:]):
        if r0 != r1 and c0 != c1:
            for row, column in ((r0, c1), (r1, c0)):
                rejected = reason(row, column)
                if rejected:
                    return "diagonal_" + rejected
    return None


def account_connection(path, width, native_update_Q):
    """Add each missing D8 segment through the unchanged native flux updater."""
    for (r0, c0), (r1, c1) in zip(path, path[1:]):
        dr, dc = r1 - r0, c1 - c0
        native_update_Q(np.array([np.hypot(dr, dc)]), np.array([r0 * width + c0], dtype=np.int64),
            np.array([r1 * width + c1], dtype=np.int64), np.array([True]),
            np.array([dr], dtype=np.int64), np.array([dc], dtype=np.int64),
            update_current=True, update_next=True)


def repair_loop_returns(proposal, returned, depth, cell_type, dry_depth, native_update_Q):
    """Keep native flags externally; reject only the unsafe relocation itself."""
    decisions = []
    width = depth.shape[1]
    for parcel in np.flatnonzero(proposal != returned):
        start, end = int(proposal[parcel]), int(returned[parcel])
        path = d8_connection(start, end, width)
        rejected = connection_rejection(path, depth, cell_type, dry_depth)
        if rejected:
            returned[parcel] = start
        else:
            account_connection(path, width, native_update_Q)
        decisions.append((int(parcel), start, end, len(path) - 1, rejected or "accepted"))
    return decisions


def mask_inlet_upstream_weights(weights, jwalk_flat, cell_type):
    """Only row0 inlet cells: forbid upstream D8 choices in every weight branch."""
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
