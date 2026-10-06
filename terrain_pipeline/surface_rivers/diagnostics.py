"""Optional first-cause and propagation masks for offline river failures."""

import numpy as np


class RiverDiagnostics:
    def __init__(self, shape):
        self.shape = tuple(shape)
        self.first_cause = np.zeros(shape, dtype=np.uint8)
        self.causes = {}
        self.propagation = {}
        self.required_extra_cut_m = np.zeros(shape, dtype=np.float64)

    def mark(self, name, cells, *, propagated=False):
        mask = np.asarray(cells, dtype=bool)
        if mask.shape != self.shape:
            raise ValueError("diagnostic mask shape differs from river grid")
        target = self.propagation if propagated else self.causes
        if name not in target:
            target[name] = np.zeros(self.shape, dtype=bool)
        target[name] |= mask
        if not propagated:
            code = list(self.causes).index(name) + 1
            self.first_cause[(self.first_cause == 0) & mask] = code

    def mark_cell(self, name, cell, *, propagated=False):
        target = self.propagation if propagated else self.causes
        if name not in target:
            target[name] = np.zeros(self.shape, dtype=bool)
        target[name].flat[cell] = True
        if not propagated and self.first_cause.flat[cell] == 0:
            self.first_cause.flat[cell] = list(self.causes).index(name) + 1

    def summary(self):
        return {"first_cause_codes": {name: index + 1 for index, name in enumerate(self.causes)},
                "first_cause_counts": {name: int(np.count_nonzero(self.first_cause == index + 1))
                                       for index, name in enumerate(self.causes)},
                "cause_counts": {name: int(np.count_nonzero(mask))
                                 for name, mask in self.causes.items()},
                "propagation_counts": {name: int(np.count_nonzero(mask))
                                       for name, mask in self.propagation.items()},
                "required_extra_cut_max_m": float(self.required_extra_cut_m.max())}


def route_cut_lower_bound(height, receiver, order, max_incision, drop_m=0.01):
    """Estimate cut-only need along one fixed route; this is not an optimized channel plan."""
    raw = np.asarray(height, dtype=np.float64)
    if raw.ndim != 2 or raw.size == 0 or not np.isfinite(raw).all():
        raise ValueError("height must be a nonempty finite 2D grid")
    if not np.isfinite(drop_m) or drop_m <= 0 or not np.isfinite(max_incision) or max_incision < 0:
        raise ValueError("drop_m must be positive and max_incision nonnegative; both must be finite")
    from .channel import _validated_route
    downstream, ordered = _validated_route(receiver, order, raw.shape)
    source = raw.reshape(-1)
    needed = source.copy()
    for cell in ordered[::-1]:
        target = downstream[cell]
        if target >= 0:
            needed[target] = min(needed[target], needed[cell] - drop_m)
    cut = (source - needed).reshape(np.shape(height))
    return {"cut_m": cut, "above_cap": cut > max_incision + 1e-9,
            "max_cut_m": float(cut.max()),
            "above_cap_cells": int(np.count_nonzero(cut > max_incision + 1e-9))}
