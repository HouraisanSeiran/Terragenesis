"""Pinned native routing with source availability in its erosion exchange."""

from functools import lru_cache

import numpy as np


OBSERVATION_COUNT_FIELDS = ("exchange_visits", "deposition_limit_calls", "deposition_limited_calls", "erosion_limit_calls")
OBSERVATION_VALUE_FIELDS = ("pre_depth_sum_m", "pre_stage_sum_m", "pre_speed_sum_m_s",
                            "deposition_proposed_bulk_m3", "deposition_native_accepted_bulk_m3", "erosion_actual_bulk_m3")
OBSERVATION_DEPTH_BOUNDS_M = (float(np.float32(.01)), float(np.float32(.1)))


@lru_cache(maxsize=4)
def source_limited_router_classes(observe_native_exchange=False, quantized_native_exchange=False):
    """Reuse every 2.3.0 router method, specializing its exchange limiter."""
    from numba import float64, int64
    from numba.experimental import jitclass
    from pyDeltaRCM.sed_tools import MudRouter, SandRouter
    observe = observe_native_exchange
    quantized = quantized_native_exchange
    lower_depth, upper_depth = OBSERVATION_DEPTH_BOUNDS_M

    def specialize(native, name):
        native_exchange = native.class_type.jit_methods["_deposit_or_erode"]
        native_limit = native.class_type.jit_methods["_limit_Vp_change"]

        def exchange(self, px, py):
            self.px, self.py = px, py
            if observe:
                depth = self.depth[px, py]
                category = 0 if depth <= lower_depth else 1 if depth <= upper_depth else 2
                self.observation_category = category
                self.observation_counts[category, 0, px, py] += 1
                self.observation_values[category, 0, px, py] += depth
                self.observation_values[category, 1, px, py] += self.stage[px, py]
                self.observation_values[category, 2, px, py] += self.uw[px, py]
            native_exchange(self, px, py)

        def limit(self, Vp, stage, eta, dx, dep_ero, mod_stable_weight):
            proposed = native_limit(self, Vp, stage, eta, dx, dep_ero, mod_stable_weight)
            if observe and dep_ero == 0:
                category, px, py = self.observation_category, self.px, self.py
                self.observation_counts[category, 1, px, py] += 1
                if proposed < Vp:
                    self.observation_counts[category, 2, px, py] += 1
                self.observation_values[category, 3, px, py] += Vp
                self.observation_values[category, 4, px, py] += proposed
            accepted = proposed
            if dep_ero == 1:
                available = max(0., (eta - self.source_floor_m[self.px, self.py]) * dx * dx)
                accepted = min(proposed, available)
                if accepted < proposed:
                    self.source_floor_limited_bulk_m3 += proposed - accepted
                    self.source_floor_limited_exchange_count += 1
            if quantized:
                if accepted < 0. or not np.isfinite(accepted):
                    raise ValueError("finite nonnegative exchange cap required before quantization")
                area = np.float64(dx) * np.float64(dx)
                old = np.float32(eta)
                target = np.float32(np.float64(old) + (accepted if dep_ero == 0 else -accepted) / area)
                actual = (np.float64(target) - np.float64(old)) * area
                if abs(actual) > accepted:
                    target = np.nextafter(target, old)
                    actual = (np.float64(target) - np.float64(old)) * area
                accepted = abs(actual)
            if observe and dep_ero == 1:
                category, px, py = self.observation_category, self.px, self.py
                self.observation_counts[category, 3, px, py] += 1
                self.observation_values[category, 5, px, py] += accepted
            return accepted

        # Numba exposes the pinned methods and their exact field specification.
        # Their original Python functions compile against the specialized type.
        methods = {key: value.py_func for key, value in native.class_type.jit_methods.items()}
        methods["_deposit_or_erode"] = exchange
        methods["_limit_Vp_change"] = limit
        fields = list(native.class_type.struct.items()) + [
            ("source_floor_m", float64[:, :]),
            ("source_floor_limited_bulk_m3", float64),
            ("source_floor_limited_exchange_count", int64),
        ]
        if quantized:
            fields = [(key, float64 if key in ("Vp_sed", "Vp_res", "Vp_exported", "Vp_lost") else
                       float64[:, :] if key in ("Vp_dep_sand", "Vp_dep_mud") else kind) for key, kind in fields]
        if observe:
            fields += [("observation_category", int64), ("observation_counts", int64[:, :, :, :]),
                       ("observation_values", float64[:, :, :, :])]
        return jitclass(fields)(type(name, (), methods))

    return specialize(MudRouter, "SourceLimitedMudRouter"), specialize(SandRouter, "SourceLimitedSandRouter")


def initialize_source_limited_routers(model, floor_m, *, observe_native_exchange=False, quantized_native_exchange=False):
    """Use native constructor arguments; share the fixed original-source floor."""
    MudRouter, SandRouter = source_limited_router_classes(observe_native_exchange, quantized_native_exchange)
    if quantized_native_exchange:
        model.Vp_dep_sand = model.Vp_dep_sand.astype(np.float64)
        model.Vp_dep_mud = model.Vp_dep_mud.astype(np.float64)
    model._mr = MudRouter(model._dt, model._dx, model.Vp_sed, model.u_max,
        model.U_dep_mud, model.U_ero_mud, model.ivec_flat, model.jvec_flat,
        model.iwalk_flat, model.jwalk_flat, model.distances_flat, model.dry_depth,
        model._lambda, model._beta, model.stepmax, model.force_deposit, model.theta_mud, model.mod_erosion)
    model._sr = SandRouter(model._dt, model._dx, model.Vp_sed, model.u_max,
        model.qs0, model._u0, model.U_ero_sand, model._f_bedload, model.ivec_flat,
        model.jvec_flat, model.iwalk_flat, model.jwalk_flat, model.distances_flat,
        model.dry_depth, model._beta, model.stepmax, model.force_deposit, model.theta_sand, model.mod_erosion)
    floor = np.array(floor_m, dtype=np.float64, order="C", copy=True)
    for router in (model._mr, model._sr):
        router.source_floor_m = floor
        router.source_floor_limited_bulk_m3 = 0.
        router.source_floor_limited_exchange_count = 0
        if observe_native_exchange:
            router.observation_category = 0
            router.observation_counts = np.zeros((3, len(OBSERVATION_COUNT_FIELDS), *floor.shape), dtype=np.int64)
            router.observation_values = np.zeros((3, len(OBSERVATION_VALUE_FIELDS), *floor.shape), dtype=np.float64)
