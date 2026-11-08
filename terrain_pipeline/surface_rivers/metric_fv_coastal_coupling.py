"""Operator-split FV water/finite bedload, preserving the live hydraulic state.

Updates the existing v7 support arrays in place at interval boundaries. The
existing execution retains h, hu, hv; next interval pressure and fluxes see
the updated bed. This adapter does not modify the shared solver modules.
"""
from functools import partial

import numpy as np

from terrain_pipeline.shallow_water import shallow_water_rhs_accelerated as shallow_water_rhs, storage_kernel, manning_damping_accelerated as manning_damping
from terrain_pipeline.shallow_water import advance_with_drag as advance_shallow_water
from .metric_fv_coastal_sediment import BedloadConfig, transport_bedload, MorphodynamicStepTooLarge


def advance_coupled(geometry, *, floor_m, initial_depth_m, source_m3_s, sea_stage_provider,
                    intervals, interval_s, budget, config=BedloadConfig(), interval_observer=None,
                    momentum_observer=None, initial_momentum_m2_s=None, failure_observer=None):
    config.validate()
    a = geometry["arrays"]
    bed = a["H2_m"]
    datum = float(bed.min())
    support = {"subcell_bed_relative_m": (bed - datum).reshape(-1, 1).copy(),
        "subcell_prefix_relative_m": (bed - datum).reshape(-1, 1).copy(),
        "face_segment_crest_relative_m": (a["face_crest_m"] - datum)[:, None].copy(),
        "boundary_segment_crest_relative_m": (a["boundary_crest_m"] - datum)[:, None].copy()}
    a.update(support)
    geometry["metadata"]["hydraulic_datum_m"] = datum
    beds = [bed.copy()]
    sediment_ledgers = []
    wave_heights = []
    stages = [bed + initial_depth_m]
    initial_momentum = (np.zeros((bed.size, 2)) if initial_momentum_m2_s is None
        else np.asarray(initial_momentum_m2_s, float).copy())
    if initial_momentum.shape != (bed.size, 2) or not np.isfinite(initial_momentum).all():
        raise ValueError("finite [cell,2] initial momentum required")
    if np.any(initial_momentum[initial_depth_m.ravel() == 0.] != 0.):
        raise ValueError("dry initial cells cannot carry momentum")
    state_initialized = False
    last_sea_stage = None

    def sea_stage(index):
        nonlocal last_sea_stage
        last_sea_stage = np.asarray(sea_stage_provider(index)).copy()
        return last_sea_stage

    def update_bed(packet):
        packet["tailwater_m"] = last_sea_stage.copy()
        if packet["interval"] == 0:
            packet["momentum_before"] = initial_momentum.copy()
        try:
            sediment = transport_bedload(bed, floor_m, geometry, packet, config)
        except MorphodynamicStepTooLarge as error:
            if failure_observer is not None:
                failure_observer(packet, bed.copy(), str(error))
            raise
        bed[:] = sediment["bed_m"]
        flat = bed.ravel()
        a["face_crest_m"][:] = np.maximum(flat[a["face_left"]], flat[a["face_right"]])
        a["boundary_crest_m"][:] = flat[a["boundary_cell"]]
        support["subcell_bed_relative_m"][:, 0] = flat - datum
        support["subcell_prefix_relative_m"][:, 0] = flat - datum
        support["face_segment_crest_relative_m"][:, 0] = a["face_crest_m"] - datum
        support["boundary_segment_crest_relative_m"][:, 0] = a["boundary_crest_m"] - datum
        beds.append(bed.copy())
        stages.append(bed + packet["depth_after_m"].reshape(bed.shape))
        sediment_ledgers.append(sediment["ledger"])
        wave_heights.append(sediment["wave_height_m"])
        if interval_observer is not None:
            interval_observer(packet, sediment)

    def stage_provider(depth):
        return storage_kernel(depth, support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"])

    def wave_speed(state, gravity):
        nonlocal state_initialized
        # The frozen execution exposes its live state before its first RHS via
        # this callback. Initialize momentum here, before CFL and RK evaluation.
        if not state_initialized:
            state[:, 1:] = initial_momentum
            state_initialized = True
        maximum_depth = np.maximum(stage_provider(state[:, 0]) - support["subcell_bed_relative_m"][:, 0], 0.)
        velocity = np.divide(state[:, 1:], state[:, :1], out=np.zeros_like(state[:, 1:]), where=state[:, :1] > 0)
        return float((abs(velocity).sum(axis=1) + 2. * np.sqrt(gravity * maximum_depth)).max(initial=0.))

    result = advance_shallow_water(geometry, rhs=partial(shallow_water_rhs, support=support),
        model="FV-HLL-v7-finite-MPM-Airy-operator-split-v1", scope="physical-time water and finite-bed sediment; live hydraulic momentum retained between Exner steps",
        physical_limitation="uncalibrated first-order flow/MPM bedload; straight Airy rays; no wave radiation stress, refraction, suspended load or bank failure",
        initial_depth_m=initial_depth_m, forcing_interval_s=interval_s, intervals=intervals,
        forcing_provider=lambda index: source_m3_s, boundary_stage_provider=sea_stage,
        source_identity=geometry["metadata"]["source_identity"], forcing_identity="explicit-river-sea-and-incident-wave-boundaries",
        budget=budget, snapshot_interval_s=interval_s, interval_observer=update_bed,
        momentum_observer=momentum_observer or (lambda packet: None), hydraulic_datum_m=datum,
        wave_speed=wave_speed, stage_provider=stage_provider, face_evaluation_multiplier=1,
        drag_provider=partial(manning_damping, support=support))
    # The shared execution reconstructs all snapshots with the final support;
    # replace that convenience array using the actual bed at each saved time.
    result["arrays"]["bed_m"] = np.asarray(beds)
    result["arrays"]["stage_m"] = np.asarray(stages)
    result["arrays"]["stage_relative_m"] = np.asarray(stages) - datum
    result["arrays"]["source_floor_m"] = np.asarray(floor_m).copy()
    result["arrays"]["momentum_x_m2_s"][0] = initial_momentum[:, 0].reshape(bed.shape)
    result["arrays"]["momentum_z_m2_s"][0] = initial_momentum[:, 1].reshape(bed.shape)
    result["arrays"]["wave_height_m"] = np.asarray(wave_heights)
    result["sediment_ledgers"] = sediment_ledgers
    result["metadata"]["bed_water_handoff"] = "Exner changes bed/support only; exact live depth and momentum remain in the same execution state; next hydraulic interval recomputes pressure and fluxes"
    return result
