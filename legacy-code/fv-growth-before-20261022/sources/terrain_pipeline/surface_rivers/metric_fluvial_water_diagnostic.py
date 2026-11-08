"""One-step read-only observations around pinned native water routing calls."""

from contextlib import contextmanager

import numpy as np


class WaterRoutingDiagnostic:
    def __init__(self):
        self.iterations = []

    def begin(self, model):
        rows = model.L - 1
        self.current = {
            "adjacent_positive_counts": np.zeros(rows, dtype=np.int64),
            "adjacent_negative_counts": np.zeros(rows, dtype=np.int64),
            "relocation_positive_counts": np.zeros(rows, dtype=np.int64),
            "relocation_negative_counts": np.zeros(rows, dtype=np.int64),
            "boundary_seen": np.zeros(model._Np_water, dtype=bool),
            "terminal_indices": np.zeros(model._Np_water, dtype=np.int64),
            "relocations": [], "loop_calls": 0,
            "Qp_water_m3_s": float(model.Qp_water),
            "out_of_domain_transitions": [],
            "native_relocations": [], "repair_decisions": [],
            "routing_depth_m": model.depth.copy(),
        }
        self.iterations.append(self.current)

    def crossings(self, model, first, second, prefix):
        invalid = (first < 0) | (second < 0) | (first >= model.L*model.W) | (second >= model.L*model.W)
        for a, b in zip(first[invalid], second[invalid]):
            self.current["out_of_domain_transitions"].append((int(a), int(b)))
        first, second = first % (model.L*model.W), second % (model.L*model.W)
        r0, r1 = first // model.W, second // model.W
        for mask, name in ((r1 > r0, "positive"), (r1 < r0, "negative")):
            lower, upper = np.minimum(r0[mask], r1[mask]), np.maximum(r0[mask], r1[mask])
            differences = np.bincount(lower, minlength=model.L) - np.bincount(upper, minlength=model.L)
            self.current[prefix + "_" + name + "_counts"] += np.cumsum(differences)[:-1]

    def adjacent(self, model, current, proposal):
        active = current > 0
        self.crossings(model, current[active], proposal[active], "adjacent")

    @contextmanager
    def native_loop_calls(self, model):
        import importlib
        native = importlib.import_module("pyDeltaRCM.water_tools")
        original = native._check_for_loops

        def observed(walk, proposal, step, inlet_length, center, stage_above_sea):
            before = proposal.copy()
            returned, flags = original(walk, proposal, step, inlet_length, center, stage_above_sea)
            changed = before != returned
            self.current["loop_calls"] += 1
            self.current["last_step"] = int(step)
            self.current["last_returned"] = returned.copy()
            if changed.any():
                self.crossings(model, before[changed], returned[changed], "relocation")
                for parcel in np.flatnonzero(changed):
                    self.current["relocations"].append((int(step), int(parcel), int(before[parcel]),
                        int(returned[parcel]), int(flags[parcel])))
            return returned, flags

        native._check_for_loops = observed
        try:
            yield
        finally:
            native._check_for_loops = original

    def boundary(self, indices, boundary):
        self.current["boundary_seen"] |= boundary & (indices > 0)
        self.current["terminal_indices"][boundary] = indices[boundary]
        self.current["last_boundary"] = boundary.copy()

    def finish_walk(self, model):
        current = self.current
        current["active_at_end"] = (current["last_returned"] > 0) & ~current["last_boundary"]
        current["terminal_indices"][current["active_at_end"]] = current["last_returned"][current["active_at_end"]]
        current["free_surface_flags"] = model.free_surf_flag.copy()

    def before_flow(self, model):
        for name in ("qxn", "qyn", "qwn", "qx", "qy", "qw"):
            self.current["raw_" + name] = getattr(model, name).copy()

    def after_flow(self, model, iteration):
        for name in ("qxn", "qyn", "qwn", "qx", "qy", "qw"):
            self.current["after_" + name] = getattr(model, name).copy()
        self.current["omega"] = float(model._omega_flow if iteration == 0 else model.omega_flow_iter)

    def archive(self):
        arrays = {}
        for index, iteration in enumerate(self.iterations):
            for name, value in iteration.items():
                columns = 5 if name in ("relocations", "native_relocations") else 2 if name == "out_of_domain_transitions" else 6 if name == "repair_decisions" else None
                dtype = str if name == "repair_decisions" else np.int64
                arrays[f"iteration{index}_" + name] = np.asarray(value, dtype=dtype).reshape(-1, columns) if columns else np.asarray(value)
        return arrays
