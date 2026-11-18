"""Conservative dilute suspended supply on archived FV water transfers."""
from dataclasses import dataclass

import numpy as np

from .metric_fv_coastal_sediment import MorphodynamicStepTooLarge


@dataclass(frozen=True)
class SuspendedConfig:
    settling_velocity_m_s: float = .005
    porosity: float = .35
    max_bed_change_m: float = .01
    max_advection_substeps: int = 4096
    max_volume_concentration: float = .05

    def validate(self):
        if (not np.isfinite([self.settling_velocity_m_s, self.porosity, self.max_bed_change_m]).all()
                or self.settling_velocity_m_s < 0. or not 0. <= self.porosity < 1.
                or self.max_bed_change_m <= 0. or type(self.max_advection_substeps) is not int
                or self.max_advection_substeps < 1 or not 0. < self.max_volume_concentration <= .05):
            raise ValueError("finite physical suspended transport parameters required")


def advance_suspended(suspended_solid_m3, bed_m, geometry, water, injected_solid_m3, inlet_cells,
                      config=SuspendedConfig()):
    """Upwind face advection, clear sea inflow, then exponential settling.

    Solid mass is cell inventory, not concentration. Water volume and live
    momentum are unchanged by dilute settling, as in the existing Exner split.
    """
    config.validate()
    bed = np.asarray(bed_m, float)
    mass = np.asarray(suspended_solid_m3, float).ravel().copy()
    n = bed.size
    if (mass.size != n or not np.isfinite(mass).all() or np.any(mass < 0.)
            or not np.isfinite(injected_solid_m3) or injected_solid_m3 < 0.):
        raise ValueError("finite nonnegative suspended inventory and source required")
    cells_in = np.asarray(inlet_cells, int)
    if not len(cells_in) or np.any(cells_in < 0) or np.any(cells_in >= n):
        raise ValueError("valid inlet cells required")
    a = geometry["arrays"]
    left, right, boundary = a["face_left"], a["face_right"], a["boundary_cell"]
    area = float(geometry["metadata"]["spacing_m"]) ** 2
    dt = float(water["time_end_s"] - water["time_start_s"])
    h = .5 * (water["depth_before_m"] + water["depth_after_m"])
    volume = h * area
    internal = np.asarray(water["internal_transfer_m3"], float)
    outward = np.maximum(water["boundary_transfer_m3"], 0.)
    donor = np.where(internal >= 0., left, right)
    receiver = np.where(internal >= 0., right, left)
    moving = abs(internal)
    demand = np.bincount(donor, weights=moving, minlength=n) + np.bincount(boundary, weights=outward, minlength=n)
    turnover = np.divide(demand, volume, out=np.zeros(n), where=volume > 1.e-12)
    if np.any((volume <= 1.e-12) & (demand > 1.e-9)):
        raise MorphodynamicStepTooLarge("water donor without represented wet volume; reduce coupling interval")
    count = max(1, int(np.ceil(turnover.max(initial=0.) / .5)))
    if count > config.max_advection_substeps:
        raise MorphodynamicStepTooLarge("suspended donor turnover exceeds substep budget; reduce coupling interval")
    initial = float(mass.sum())
    exports = np.zeros(len(boundary))
    transfers = np.zeros(len(left))
    limited = 0
    peak_concentration = 0.
    clipped_added = 0.
    def check_dilute(inventory, water_volume):
        if np.any((water_volume <= 1.e-12) & (inventory > 1.e-10)):
            raise MorphodynamicStepTooLarge("suspended inventory without wet volume; reduce input/interval")
        concentration = np.divide(inventory, water_volume, out=np.zeros(n), where=water_volume > 1.e-12)
        maximum = float(concentration.max(initial=0.))
        if maximum > config.max_volume_concentration:
            raise MorphodynamicStepTooLarge("dilute suspended concentration exceeded before settling; reduce source acceleration/interval")
        return maximum
    source = injected_solid_m3 / (len(cells_in) * count)
    for _ in range(count):
        np.add.at(mass, cells_in, source)
        peak_concentration = max(peak_concentration, check_dilute(mass, volume))
        concentration = np.divide(mass, volume, out=np.zeros(n), where=volume > 1.e-12)
        requested = moving / count * concentration[donor]
        boundary_requested = outward / count * concentration[boundary]
        demand_solid = np.bincount(donor, weights=requested, minlength=n)
        demand_solid += np.bincount(boundary, weights=boundary_requested, minlength=n)
        factor = np.minimum(1., np.divide(mass, demand_solid, out=np.ones(n), where=demand_solid > 0.))
        accepted = requested * factor[donor]
        leaving = boundary_requested * factor[boundary]
        mass += np.bincount(receiver, weights=accepted, minlength=n) - np.bincount(donor, weights=accepted, minlength=n)
        mass -= np.bincount(boundary, weights=leaving, minlength=n)
        if mass.min(initial=0.) < -1.e-10:
            raise RuntimeError("negative conservative suspended inventory")
        clipped_added += float(-np.minimum(mass, 0.).sum())
        if clipped_added > 1.e-9:
            raise RuntimeError("roundoff suspended mass correction exceeds explicit 1e-9 solid m3 budget")
        mass = np.maximum(mass, 0.)
        peak_concentration = max(peak_concentration, check_dilute(mass, volume))
        transfers += np.sign(internal) * accepted
        exports += leaving
        limited += int(np.count_nonzero(factor < 1.))
    # Settling stops on fixed computational bed cells. Dry interior cells
    # deposit their entire retained load rather than discard it.
    fixed = np.asarray(a.get("fixed_bed_cell", np.zeros(n, bool)), bool).ravel()
    final_h = np.asarray(water["depth_after_m"], float)
    # Completely dry interior cells settle their load immediately. For wet
    # cells check the final physical volume before settling can hide a peak.
    final_wet = final_h > 1.e-12
    wet_concentration = np.divide(mass, final_h * area, out=np.zeros(n), where=final_wet)
    peak_concentration = max(peak_concentration, float(wet_concentration.max(initial=0.)))
    if peak_concentration > config.max_volume_concentration:
        raise MorphodynamicStepTooLarge("final wet suspended concentration exceeded before settling")
    settling_fraction = -np.expm1(-config.settling_velocity_m_s * dt / np.maximum(final_h, 1.e-12))
    settling_fraction[fixed] = 0.
    deposited = mass * settling_fraction
    mass -= deposited
    final_concentration = np.divide(mass, final_h * area, out=np.zeros(n), where=final_h > 1.e-12)
    if final_concentration.max(initial=0.) > config.max_volume_concentration:
        raise MorphodynamicStepTooLarge("dilute suspended concentration exceeded; reduce input acceleration/interval, do not clip mass")
    bed_change = deposited / (area * (1. - config.porosity))
    if bed_change.max(initial=0.) > config.max_bed_change_m * (1. + 1.e-12):
        raise MorphodynamicStepTooLarge("suspended deposition exceeds maximum bed change; reduce complete water/bed interval")
    residual = float(mass.sum() + deposited.sum() + exports.sum() - initial - injected_solid_m3)
    return {"suspended_solid_m3": mass.reshape(bed.shape), "bed_m": bed + bed_change.reshape(bed.shape),
        "deposited_solid_m3": deposited.reshape(bed.shape), "internal_transfer_solid_m3": transfers,
        "boundary_export_solid_m3": exports, "ledger": {"initial_suspended_solid_m3": initial,
            "injected_solid_m3": float(injected_solid_m3), "final_suspended_solid_m3": float(mass.sum()),
            "deposited_solid_m3": float(deposited.sum()), "exported_solid_m3": float(exports.sum()),
            "residual_solid_m3": residual, "advection_substeps": count, "limited_donor_events": limited,
            "maximum_bed_change_m": float(bed_change.max(initial=0.)),
            "peak_volume_concentration": peak_concentration, "roundoff_added_solid_m3": clipped_added}}


def integrate_schedule(schedule, start_s, duration_s):
    """Integrate a finite remaining schedule, including partially used packets."""
    schedule = np.asarray(schedule, float)
    if duration_s <= 0. or start_s < 0. or not np.isfinite([duration_s, start_s]).all():
        raise ValueError("nonnegative cursor and positive duration required")
    ends = np.cumsum(schedule[:, 4])
    starts = np.r_[0., ends[:-1]]
    overlap = np.maximum(0., np.minimum(ends, start_s + duration_s) - np.maximum(starts, start_s))
    solid = float(np.sum(overlap * schedule[:, 3] / schedule[:, 4]))
    # After source exhaustion, retain the last declared river discharge as
    # clear water, without issuing any additional finite sediment.
    water = float(np.sum(overlap * schedule[:, 2]))
    water += float(max(0., start_s + duration_s - max(start_s, ends[-1])) * schedule[-1, 2])
    return solid, water / duration_s
