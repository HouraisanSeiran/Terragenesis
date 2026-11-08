"""Opt-in native router specialization separating load from erosion capacity.

Actual parcel starts retain their actual injected volume, including zero.
Reference concentration sets capacity and a potential erosion volume only;
the source-limited quantized exchange still debits the finite bed column.
This module is intentionally independent of the frozen routing-depth run.
"""
from functools import lru_cache

import numpy as np

from .metric_fluvial_native_routers import source_limited_router_classes


ALGORITHM = "native-independent-reference-capacity-erosion-v1"


def reference_scales(water_q_m3_s, duration_s, concentration, parcel_count, inlet_width_m):
    values = [water_q_m3_s, duration_s, concentration, inlet_width_m]
    if not np.isfinite(values).all() or min(values) <= 0. or parcel_count <= 0:
        raise ValueError("positive finite reference scales required")
    return (water_q_m3_s*concentration/inlet_width_m,
        water_q_m3_s*concentration*duration_s/parcel_count)


@lru_cache(maxsize=1)
def reference_router_classes():
    from numba import float64
    from numba.experimental import jitclass
    Mud, Sand = source_limited_router_classes(False, True)

    def specialize(base, name):
        methods = {key: value.py_func for key, value in base.class_type.jit_methods.items()}
        def independent_erosion(self, Vp_sed, U_loc, U_ero, beta, mod_erosion):
            # Pinned native erosion law, with independent reference packet only.
            return mod_erosion*self.reference_erosion_packet_bulk_m3*(U_loc**beta-U_ero**beta)/U_ero**beta

        methods["_compute_Vp_ero"] = independent_erosion
        fields = list(base.class_type.struct.items())+[("reference_erosion_packet_bulk_m3", float64)]
        return jitclass(fields)(type(name, (), methods))
    return specialize(Mud, "ReferenceMudRouter"), specialize(Sand, "ReferenceSandRouter")


def initialize_reference_routers(model, floor_m, reference_bulk_concentration):
    """Drop-in opt-in initialization; leaves model Qs0/Vp_sed unchanged."""
    capacity, packet = reference_scales(model.Qw0, model._dt, reference_bulk_concentration,
        model._Np_sed, model.N0*model._dx)
    Mud, Sand = reference_router_classes()
    model.Vp_dep_sand = model.Vp_dep_sand.astype(np.float64)
    model.Vp_dep_mud = model.Vp_dep_mud.astype(np.float64)
    model._mr = Mud(model._dt, model._dx, model.Vp_sed, model.u_max,
        model.U_dep_mud, model.U_ero_mud, model.ivec_flat, model.jvec_flat,
        model.iwalk_flat, model.jwalk_flat, model.distances_flat, model.dry_depth,
        model._lambda, model._beta, model.stepmax, model.force_deposit, model.theta_mud, model.mod_erosion)
    model._sr = Sand(model._dt, model._dx, model.Vp_sed, model.u_max,
        capacity, model._u0, model.U_ero_sand, model._f_bedload, model.ivec_flat,
        model.jvec_flat, model.iwalk_flat, model.jwalk_flat, model.distances_flat,
        model.dry_depth, model._beta, model.stepmax, model.force_deposit, model.theta_sand, model.mod_erosion)
    for router in (model._mr, model._sr):
        router.reference_erosion_packet_bulk_m3 = packet
        router.source_floor_m = np.array(floor_m, dtype=np.float64, order="C", copy=True)
        router.source_floor_limited_bulk_m3 = 0.
        router.source_floor_limited_exchange_count = 0
    return {"algorithm": ALGORITHM, "reference_bulk_concentration": reference_bulk_concentration,
        "reference_capacity_unit_bulk_m2_s": capacity, "reference_potential_erosion_packet_bulk_m3": packet,
        "actual_injected_packet_bulk_m3": model.Vp_sed, "actual_external_bulk_rate_m3_s": model.Qs0}
