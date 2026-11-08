"""Conservative finite-bed MPM transport using FV water and incident waves.

Straight D4 Airy rays shoal and break, but do not refract or force water
momentum. Symmetric wave phases stir sand; waves add no sediment or water.
"""
from dataclasses import dataclass

import numpy as np


class MorphodynamicStepTooLarge(ValueError):
    """The full requested physical interval must be retried with shorter dt."""


@dataclass(frozen=True)
class BedloadConfig:
    porosity: float = .35
    grain_diameter_m: float = .0003
    sediment_density_kg_m3: float = 2650.
    water_density_kg_m3: float = 1000.
    manning_s_m_third: float = .035
    critical_shields: float = .047
    mpm_coefficient: float = 8.
    wave_height_m: float = .3
    wave_period_s: float = 5.
    wave_direction_xz: tuple = (0, -1)
    wave_friction_factor: float = .02
    breaking_height_depth_ratio: float = .78
    wave_phases: int = 16
    dry_depth_m: float = 1.e-5
    max_bed_change_m: float = .01

    def validate(self):
        for key, value in vars(self).items():
            if key == "wave_direction_xz":
                if tuple(value) not in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    raise ValueError("straight D4 incident wave direction required")
            elif not np.isfinite(value) or value < 0:
                raise ValueError("finite nonnegative bedload parameter: " + key)
        if (not 0 <= self.porosity < 1 or self.grain_diameter_m <= 0 or self.wave_period_s <= 0
                or self.water_density_kg_m3 <= 0 or self.sediment_density_kg_m3 <= self.water_density_kg_m3
                or self.wave_phases < 4 or type(self.wave_phases) is not int or self.wave_phases % 2
                or self.max_bed_change_m <= 0 or self.dry_depth_m <= 0):
            raise ValueError("positive physical parameters and even phase count required")


def incident_wave_field(depth, geometry, config):
    """H^2 Cg flux from wet prescribed-sea entry faces; land blocks each ray."""
    config.validate()
    depth = np.asarray(depth, float)
    omega, gravity = 2. * np.pi / config.wave_period_s, 9.81
    wet = depth > config.dry_depth_m
    h = np.maximum(depth, config.dry_depth_m)
    lo = np.zeros_like(h)
    hi = omega ** 2 / gravity + omega / np.sqrt(gravity * h) + 1.
    for _ in range(50):
        middle = .5 * (lo + hi)
        lower = gravity * middle * np.tanh(middle * h) < omega ** 2
        lo = np.where(lower, middle, lo)
        hi = np.where(lower, hi, middle)
    wave_number = .5 * (lo + hi)
    kh = wave_number * h
    group_speed = .5 * omega / wave_number * (1. + 2. * kh / np.sinh(np.minimum(2. * kh, 700.)))
    dx, dz = config.wave_direction_xz
    rows, cols = depth.shape
    a = geometry["arrays"]
    open_cells = np.zeros(depth.size, bool)
    open_cells[a["boundary_cell"][a["boundary_kind"] == 2]] = True
    open_cells = open_cells.reshape(depth.shape)
    height = np.zeros_like(depth)
    starts = ([(r, 0 if dx > 0 else cols - 1) for r in range(rows)] if dx
        else [(0 if dz > 0 else rows - 1, c) for c in range(cols)])
    for r, c in starts:
        if not open_cells[r, c] or not wet[r, c]:
            continue
        flux = config.wave_height_m ** 2 * group_speed[r, c]
        while 0 <= r < rows and 0 <= c < cols and wet[r, c]:
            height[r, c] = min(np.sqrt(flux / group_speed[r, c]), config.breaking_height_depth_ratio * h[r, c])
            flux = height[r, c] ** 2 * group_speed[r, c]
            r, c = r + dz, c + dx
    orbital = np.pi * height / config.wave_period_s / np.sinh(np.minimum(kh, 700.))
    orbital[~wet] = 0.
    return {"wave_height_m": height, "wave_orbital_velocity_m_s": orbital,
        "wave_number_m_inverse": wave_number, "wave_group_speed_m_s": group_speed}


def _phase_averaged_mpm(velocity, orbital, depth, config):
    gravity = 9.81
    rho = config.water_density_kg_m3
    contrast = config.sediment_density_kg_m3 / rho - 1.
    current_speed = np.linalg.norm(velocity, axis=1)
    current_shear = rho * gravity * config.manning_s_m_third ** 2 * current_speed[:, None] * velocity
    current_shear /= np.maximum(depth, config.dry_depth_m)[:, None] ** (1. / 3.)
    result = np.zeros_like(velocity)
    direction = np.asarray(config.wave_direction_xz)
    scale = config.mpm_coefficient * np.sqrt(contrast * gravity * config.grain_diameter_m ** 3)
    for phase in range(config.wave_phases):
        wave_u = orbital * np.cos(2. * np.pi * (phase + .5) / config.wave_phases)
        wave_shear = .5 * rho * config.wave_friction_factor * (wave_u * abs(wave_u))[:, None] * direction
        shear = current_shear + wave_shear
        magnitude = np.linalg.norm(shear, axis=1)
        shields = magnitude / (rho * contrast * gravity * config.grain_diameter_m)
        rate = scale * np.maximum(shields - config.critical_shields, 0.) ** 1.5
        result += np.divide(shear, magnitude[:, None], out=np.zeros_like(shear), where=magnitude[:, None] > 0) * rate[:, None]
    result /= config.wave_phases
    result[depth <= config.dry_depth_m] = 0.
    # Opposite phase pairs cancel exactly for a motionless current.
    result[current_speed == 0.] = 0.
    return result


def reconstructed_face_hydraulics(bed, geometry, packet, dry_depth_m):
    """Endpoint trapezoid of HLL common-crest wet thickness and momentum.

The denominator for actual integrated face Q and Manning shear is the same
two-sided wet section. It never uses the receiving cell's thin water film.
"""
    a = geometry["arrays"]
    left, right, cells = a["face_left"], a["face_right"], a["boundary_cell"]
    spacing = geometry["metadata"]["spacing_m"]
    dt = packet["time_end_s"] - packet["time_start_s"]
    axes = np.r_[np.zeros(bed.shape[0] * (bed.shape[1] - 1), int), np.ones((bed.shape[0] - 1) * bed.shape[1], int)]
    boundary_axes = np.r_[np.zeros(2 * bed.shape[0], int), np.ones(2 * bed.shape[1], int)]
    signs = np.r_[-np.ones(bed.shape[0]), np.ones(bed.shape[0]), -np.ones(bed.shape[1]), np.ones(bed.shape[1])]
    crest = a["face_crest_m"]
    side_depths, side_momenta = [], []
    boundary_h = []
    boundary_momentum = []
    for depth_key, momentum_key in (("depth_before_m", "momentum_before"), ("depth_after_m", "momentum_after")):
        h = packet[depth_key]
        velocity = np.divide(packet[momentum_key], h[:, None], out=np.zeros_like(packet[momentum_key]), where=h[:, None] > dry_depth_m)
        stage = bed.ravel() + h
        hl = np.maximum(stage[left] - crest, 0.)
        hr = np.maximum(stage[right] - crest, 0.)
        side_depths.append(np.column_stack([hl, hr]))
        side_momenta.append(hl[:, None] * velocity[left] + hr[:, None] * velocity[right])
        hb = np.maximum(stage[cells] - a["boundary_crest_m"], 0.)
        hg = np.maximum(np.asarray(packet.get("tailwater_m", stage[cells])) - a["boundary_crest_m"], 0.)
        boundary_h.append(.5 * (hb + hg))
        boundary_momentum.append(.5 * hb[:, None] * velocity[cells])
    mean_side_depth = .5 * (side_depths[0] + side_depths[1])
    face_h = mean_side_depth.mean(axis=1)
    face_momentum = .25 * (side_momenta[0] + side_momenta[1])
    face_velocity = np.divide(face_momentum, face_h[:, None], out=np.zeros_like(face_momentum), where=face_h[:, None] > dry_depth_m)
    face_velocity[np.arange(len(left)), axes] = np.divide(packet["internal_transfer_m3"], dt * spacing * face_h,
        out=np.zeros(len(left)), where=face_h > dry_depth_m)
    bh = .5 * (boundary_h[0] + boundary_h[1])
    bm = .5 * (boundary_momentum[0] + boundary_momentum[1])
    bv = np.divide(bm, bh[:, None], out=np.zeros_like(bm), where=bh[:, None] > dry_depth_m)
    bv[np.arange(len(cells)), boundary_axes] = signs * np.divide(packet["boundary_transfer_m3"],
        dt * spacing * bh, out=np.zeros(len(cells)), where=bh > dry_depth_m)
    return {"face_effective_depth_m": face_h, "face_velocity_m_s": face_velocity,
        "face_normal_velocity_m_s": face_velocity[np.arange(len(left)), axes],
        "face_reconstructed_side_depth_m": mean_side_depth,
        "boundary_effective_depth_m": bh, "boundary_velocity_m_s": bv,
        "face_axes": axes, "boundary_axes": boundary_axes, "boundary_signs": signs}


def transport_bedload(bed, floor, geometry, packet, config=BedloadConfig()):
    """One explicit conservative Exner step; positive boundary rate exports."""
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
    momentum = .5 * (packet["momentum_before"] + packet["momentum_after"])
    velocity = np.divide(momentum, depth[:, None], out=np.zeros_like(momentum), where=depth[:, None] > config.dry_depth_m)
    waves = incident_wave_field(depth.reshape(bed.shape), geometry, config)
    orbital = waves["wave_orbital_velocity_m_s"].ravel()
    left, right, cells = a["face_left"], a["face_right"], a["boundary_cell"]
    axes = np.r_[np.zeros(bed.shape[0] * (bed.shape[1] - 1), int), np.ones((bed.shape[0] - 1) * bed.shape[1], int)]
    boundary_axes = np.r_[np.zeros(2 * bed.shape[0], int), np.ones(2 * bed.shape[1], int)]
    signs = np.r_[-np.ones(bed.shape[0]), np.ones(bed.shape[0]), -np.ones(bed.shape[1]), np.ones(bed.shape[1])]
    hydraulics = reconstructed_face_hydraulics(bed, geometry, packet, config.dry_depth_m)
    face_depth, face_velocity = hydraulics["face_effective_depth_m"], hydraulics["face_velocity_m_s"]
    bedload = _phase_averaged_mpm(face_velocity, .5 * (orbital[left] + orbital[right]), face_depth, config)
    requested = bedload[np.arange(len(left)), axes] * spacing * dt
    boundary_velocity = hydraulics["boundary_velocity_m_s"]
    boundary_bedload = _phase_averaged_mpm(boundary_velocity, orbital[cells], hydraulics["boundary_effective_depth_m"], config)
    boundary_request = np.maximum(signs * boundary_bedload[np.arange(len(cells)), boundary_axes], 0.) * spacing * dt
    boundary_request[a["boundary_kind"] != 2] = 0.
    donor, receiver = np.where(requested >= 0, left, right), np.where(requested >= 0, right, left)
    fixed = np.asarray(a.get("fixed_bed_cell", np.zeros(bed.size, bool)), bool).ravel()
    sea_edge = np.zeros(bed.size, bool)
    sea_edge[cells[a["boundary_kind"] == 2]] = True
    requested[fixed[donor] | (fixed[receiver] & ~sea_edge[receiver])] = 0.
    boundary_request[fixed[cells]] = 0.
    inventory = np.maximum((bed - floor).ravel(), 0.) * solid_per_m
    demand = np.bincount(donor, weights=abs(requested), minlength=bed.size)
    demand += np.bincount(cells, weights=boundary_request, minlength=bed.size)
    factor = np.minimum(1., np.divide(inventory, demand, out=np.ones_like(inventory), where=demand > 0.))
    transfer = abs(requested) * factor[donor]
    export = boundary_request * factor[cells]
    sink = fixed[receiver] & sea_edge[receiver]
    sink_export = np.bincount(receiver, weights=transfer * sink, minlength=bed.size)
    change = np.bincount(receiver, weights=transfer * ~sink, minlength=bed.size) - np.bincount(donor, weights=transfer, minlength=bed.size)
    change -= np.bincount(cells, weights=export, minlength=bed.size)
    proposed_bed_change = float(abs(change).max() / solid_per_m)
    if proposed_bed_change > config.max_bed_change_m * (1. + 1.e-12):
        suggested = dt * .8 * config.max_bed_change_m / proposed_bed_change
        raise MorphodynamicStepTooLarge(f"full physical interval {dt:g}s gives bed change {proposed_bed_change:g}m "
            f"> {config.max_bed_change_m:g}m; retry complete water/bed run with interval <= {suggested:g}s; no transport-rate scaling applied")
    updated = inventory + change
    if np.min(updated) < -1.e-9:
        raise RuntimeError("negative finite bed inventory")
    final_bed = floor + updated.reshape(bed.shape) / solid_per_m
    residual = float(updated.sum() - inventory.sum() + export.sum() + sink_export.sum())
    return {"bed_m": final_bed, "inventory_solid_m3": updated.reshape(bed.shape),
        "internal_transfer_solid_m3": np.sign(requested) * transfer,
        "boundary_export_solid_m3": export, **waves,
        "fixed_marine_edge_export_solid_m3": sink_export,
        "face_effective_depth_m": face_depth, "face_normal_velocity_m_s": hydraulics["face_normal_velocity_m_s"],
        "face_current_shields": (config.manning_s_m_third ** 2 * np.sum(face_velocity ** 2, axis=1)
            / (np.maximum(face_depth, config.dry_depth_m) ** (1. / 3.)
                * (config.sediment_density_kg_m3 / config.water_density_kg_m3 - 1.) * config.grain_diameter_m)),
        "ledger": {"initial_solid_m3": float(inventory.sum()), "final_solid_m3": float(updated.sum()),
            "exported_solid_m3": float(export.sum() + sink_export.sum()), "external_solid_m3": 0., "residual_solid_m3": residual,
            "gross_internal_transfer_solid_m3": float(transfer.sum()), "transport_time_fraction": 1.,
            "bed_change_limiter_activations": 0, "inventory_limited_donors": int((factor < 1.).sum()),
            "minimum_inventory_donor_factor": float(factor.min()),
            "maximum_abs_bed_change_m": float(abs(final_bed - bed).max())}}
