"""Finite MPM bedload confined to a same-direction net-carrier layer.

The moving layer is no thicker than the wetted carrier section, has solid
fraction <= 1-porosity, and has normal grain speed <= carrier speed. Thus
solid crossing <= (1-porosity)*same-direction water crossing. This net-flow
model does not represent wave-driven counterflow or oscillatory gross flux.
"""
import numpy as np

from .metric_fv_coastal_sediment import BedloadConfig, MorphodynamicStepTooLarge, reconstructed_face_hydraulics, _phase_averaged_mpm
from .metric_fv_incident_wave_vectorized import incident_wave_field


def transport_bedload(bed, floor, geometry, packet, config=BedloadConfig(), *, wave_field=None):
    """Frozen MPM requests, then carrier capacity and finite donor inventory."""
    config.validate()
    bed, floor = np.asarray(bed, float), np.asarray(floor, float)
    if bed.shape != floor.shape or not np.isfinite([bed, floor]).all() or np.min(bed - floor) < -2.e-6:
        raise ValueError("matching finite bed and original finite-source floor required")
    dt = packet["time_end_s"] - packet["time_start_s"]
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("positive physical transport interval required")
    a = geometry["arrays"]
    spacing = geometry["metadata"]["spacing_m"]
    solid_per_m = spacing ** 2 * (1. - config.porosity)
    depth = .5 * (packet["depth_before_m"] + packet["depth_after_m"])
    provider = incident_wave_field if wave_field is None else wave_field
    waves = provider(depth.reshape(bed.shape), geometry, config)
    orbital = waves["wave_orbital_velocity_m_s"].ravel()
    left, right, cells = a["face_left"], a["face_right"], a["boundary_cell"]
    hydraulics = reconstructed_face_hydraulics(bed, geometry, packet, config.dry_depth_m)
    axes, boundary_axes, signs = hydraulics["face_axes"], hydraulics["boundary_axes"], hydraulics["boundary_signs"]
    face_depth, face_velocity = hydraulics["face_effective_depth_m"], hydraulics["face_velocity_m_s"]
    bedload = _phase_averaged_mpm(face_velocity, .5 * (orbital[left] + orbital[right]), face_depth, config)
    requested = bedload[np.arange(len(left)), axes] * spacing * dt
    boundary_bedload = _phase_averaged_mpm(hydraulics["boundary_velocity_m_s"], orbital[cells], hydraulics["boundary_effective_depth_m"], config)
    boundary_request = np.maximum(signs * boundary_bedload[np.arange(len(cells)), boundary_axes], 0.) * spacing * dt
    boundary_request[a["boundary_kind"] != 2] = 0.
    donor, receiver = np.where(requested >= 0, left, right), np.where(requested >= 0, right, left)
    fixed = np.asarray(a.get("fixed_bed_cell", np.zeros(bed.size, bool)), bool).ravel()
    sea_edge = np.zeros(bed.size, bool)
    sea_edge[cells[a["boundary_kind"] == 2]] = True
    requested[fixed[donor] | (fixed[receiver] & ~sea_edge[receiver])] = 0.
    boundary_request[fixed[cells]] = 0.
    water = np.asarray(packet["internal_transfer_m3"])
    boundary_water = np.asarray(packet["boundary_transfer_m3"])
    same_direction = requested * water > 0.
    capacity = (1. - config.porosity) * abs(water)
    accepted_carrier = np.where(same_direction, np.minimum(abs(requested), capacity), 0.)
    boundary_capacity = (1. - config.porosity) * np.maximum(boundary_water, 0.)
    accepted_boundary_carrier = np.minimum(boundary_request, boundary_capacity)
    inventory = np.maximum((bed - floor).ravel(), 0.) * solid_per_m
    demand = np.bincount(donor, weights=accepted_carrier, minlength=bed.size)
    demand += np.bincount(cells, weights=accepted_boundary_carrier, minlength=bed.size)
    factor = np.minimum(1., np.divide(inventory, demand, out=np.ones_like(inventory), where=demand > 0.))
    transfer = accepted_carrier * factor[donor]
    export = accepted_boundary_carrier * factor[cells]
    sink = fixed[receiver] & sea_edge[receiver]
    sink_export = np.bincount(receiver, weights=transfer * sink, minlength=bed.size)
    change = np.bincount(receiver, weights=transfer * ~sink, minlength=bed.size) - np.bincount(donor, weights=transfer, minlength=bed.size)
    change -= np.bincount(cells, weights=export, minlength=bed.size)
    proposed_bed_change = float(abs(change).max() / solid_per_m)
    if proposed_bed_change > config.max_bed_change_m * (1. + 1.e-12):
        suggested = dt * .8 * config.max_bed_change_m / proposed_bed_change
        raise MorphodynamicStepTooLarge(f"v4 carrier-bounded interval {dt:g}s gives bed change {proposed_bed_change:g}m > {config.max_bed_change_m:g}m; retry <= {suggested:g}s")
    updated = inventory + change
    if np.min(updated) < -1.e-9:
        raise RuntimeError("negative finite bed inventory")
    final_bed = floor + updated.reshape(bed.shape) / solid_per_m
    residual = float(updated.sum() - inventory.sum() + export.sum() + sink_export.sum())
    return {"bed_m": final_bed, "inventory_solid_m3": updated.reshape(bed.shape),
        "internal_transfer_solid_m3": np.sign(requested) * transfer,
        "boundary_export_solid_m3": export, **waves,
        "fixed_marine_edge_export_solid_m3": sink_export,
        "mpm_internal_requested_solid_m3": requested,
        "carrier_internal_capacity_solid_m3": capacity,
        "carrier_internal_accepted_solid_m3": np.sign(requested) * accepted_carrier,
        "mpm_boundary_requested_solid_m3": boundary_request,
        "carrier_boundary_capacity_solid_m3": boundary_capacity,
        "carrier_boundary_accepted_solid_m3": accepted_boundary_carrier,
        "face_effective_depth_m": face_depth,
        "face_normal_velocity_m_s": hydraulics["face_normal_velocity_m_s"],
        "face_current_shields": (config.manning_s_m_third ** 2 * np.sum(face_velocity ** 2, axis=1)
            / (np.maximum(face_depth, config.dry_depth_m) ** (1. / 3.)
                * (config.sediment_density_kg_m3 / config.water_density_kg_m3 - 1.) * config.grain_diameter_m)),
        "ledger": {"initial_solid_m3": float(inventory.sum()), "final_solid_m3": float(updated.sum()),
            "exported_solid_m3": float(export.sum() + sink_export.sum()), "external_solid_m3": 0., "residual_solid_m3": residual,
            "gross_internal_transfer_solid_m3": float(transfer.sum()), "transport_time_fraction": 1.,
            "bed_change_limiter_activations": 0, "inventory_limited_donors": int((factor < 1.).sum()),
            "minimum_inventory_donor_factor": float(factor.min()),
            "maximum_abs_bed_change_m": float(abs(final_bed - bed).max()),
            "mpm_requested_internal_solid_m3": float(abs(requested).sum()),
            "carrier_accepted_internal_solid_m3": float(accepted_carrier.sum()),
            "carrier_capacity_limited_faces": int(np.count_nonzero(same_direction & (abs(requested) > capacity))),
            "carrier_direction_rejected_faces": int(np.count_nonzero((requested != 0.) & ~same_direction)),
            "carrier_direction_rejected_solid_m3": float(abs(requested[~same_direction]).sum()),
            "carrier_capacity_rejected_solid_m3": float(np.maximum(abs(requested[same_direction]) - capacity[same_direction], 0.).sum()),
            "mpm_requested_boundary_solid_m3": float(boundary_request.sum()),
            "carrier_accepted_boundary_solid_m3": float(accepted_boundary_carrier.sum()),
            "carrier_capacity_limited_boundary_faces": int(np.count_nonzero(boundary_request > boundary_capacity)),
            "carrier_boundary_rejected_solid_m3": float((boundary_request - accepted_boundary_carrier).sum())}}
