"""Independent conservative linear subgrid storage, HLL and Manning evolution."""

from functools import partial

import numpy as np

from terrain_pipeline.single_domain_fine_geometry import storage_stages
from terrain_pipeline.single_domain_shallow_water_execution_v8 import advance_shallow_water as _advance
from terrain_pipeline.single_domain_shallow_water_reconstruction_v9 import reconstruct
from terrain_pipeline.single_domain_shallow_water_support_v9 import MODEL, shallow_water_rhs


def advance_shallow_water(geometry, **kwargs):
    arrays, metadata = geometry["arrays"], geometry["metadata"]
    support = {name: arrays[name] for name in ("subcell_bed_relative_m", "subcell_prefix_relative_m",
        "face_segment_crest_relative_m", "boundary_segment_crest_relative_m", "subcell_bed_position_relative_m")}
    datum = metadata["hydraulic_datum_m"]
    bed = arrays["H2_m"]-datum
    boundary_provider = kwargs["boundary_stage_provider"]
    interval_observer = kwargs["interval_observer"]
    current_tail = np.zeros(len(arrays["boundary_kind"]))
    saved_profiles = []

    def profile(state):
        return reconstruct(state, bed, support, arrays["boundary_kind"], current_tail)

    def boundary_stages(index):
        nonlocal current_tail
        stage = boundary_provider(index)
        current_tail = np.asarray(stage)-datum
        if index == 0:
            initial = np.asarray(kwargs["initial_depth_m"]).ravel()
            saved_profiles.append(profile(np.column_stack((initial, np.zeros((bed.size, 2))))))
        return stage

    def observe(packet):
        saved_profiles.append(profile(np.column_stack((packet["depth_after_m"], packet["momentum_after"]))))
        interval_observer(packet)

    def drag(state, dt, gravity, roughness):
        depth = profile(state)["subcell_depth"]
        inverse = np.zeros_like(depth)
        np.power(depth, -1/3, out=inverse, where=depth > 0)
        factor = inverse.mean(axis=(1, 2))
        depth_squared = state[:, 0]**2
        denominator = depth_squared+dt*gravity*roughness**2*np.hypot(state[:, 1], state[:, 2])*factor
        damping = np.divide(depth_squared, denominator, out=np.zeros_like(depth_squared), where=denominator > 0)
        return damping, factor

    def wave_speed(state, gravity):
        rec = profile(state)
        maximum_depth = float(rec["subcell_depth"].max(initial=0))
        velocity = float(abs(rec["subcell_velocity"]).sum(axis=3).max(initial=0))
        return 2*velocity+2*np.sqrt(2*gravity*maximum_depth)

    kwargs["boundary_stage_provider"] = boundary_stages
    kwargs["interval_observer"] = observe
    result = _advance(geometry, rhs=partial(shallow_water_rhs, support=support), model=MODEL,
        hydraulic_datum_m=datum, wave_speed=wave_speed, drag_provider=drag,
        stage_provider=lambda depth: storage_stages(depth, support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"]),
        face_evaluation_multiplier=support["face_segment_crest_relative_m"].shape[1],
        scope="independent FV conservative linear stage/velocity canonical storage; segmented HLL; bed-jump pressure; canonical Manning",
        physical_limitation="canonical midpoint subcell quadrature; linear profiles; uniform coarse-velocity drag approximation; uncalibrated",
        **kwargs)
    raw = result["arrays"]
    raw["storage_equivalent_stage_relative_m"] = raw.pop("stage_relative_m")
    raw["stage_relative_m"] = np.asarray([rec["center"][:, 0] for rec in saved_profiles]).reshape(-1, *bed.shape)
    raw["reconstruction_velocity_center_m_s"] = np.asarray([rec["center"][:, 1:] for rec in saved_profiles]).reshape(-1, *bed.shape, 2)
    raw["reconstruction_slope_x"] = np.asarray([rec["slope_x"] for rec in saved_profiles]).reshape(-1, *bed.shape, 3)
    raw["reconstruction_slope_z"] = np.asarray([rec["slope_z"] for rec in saved_profiles]).reshape(-1, *bed.shape, 3)
    raw["canonical_subcell_bed_position_relative_m"] = support["subcell_bed_position_relative_m"].copy()
    factor = support["face_segment_crest_relative_m"].shape[1]
    coordinate = (np.arange(factor)+.5)/factor-.5
    x, z = np.meshgrid(coordinate, coordinate)
    raw["canonical_subcell_positions_local_m"] = np.stack((x, z), axis=2)*metadata["spacing_m"]
    result["metadata"]["profile_contract"] = "eta=eta0+sx*xi+sz*zeta; canonical midpoint h integral=H; h-weighted velocity integral=M; stage_relative is eta0"
    return result


