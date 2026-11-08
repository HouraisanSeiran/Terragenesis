"""Finite bed-suspended exchange and conservative excess-slope sand transport."""
from dataclasses import dataclass
import numpy as np

from .metric_fv_coastal_sediment import incident_wave_field, MorphodynamicStepTooLarge


@dataclass(frozen=True)
class ExchangeConfig:
    enabled: bool = True
    erosion_velocity_m_s: float = 1.e-5
    maximum_concentration: float = .03
    slope_enabled: bool = True
    critical_slope_m_m: float = .35
    slope_mobility_m2_s: float = .02

    def validate(self):
        values = [self.erosion_velocity_m_s, self.maximum_concentration, self.critical_slope_m_m, self.slope_mobility_m2_s]
        if (not np.isfinite(values).all() or min(values) < 0. or not 0. < self.maximum_concentration <= .05):
            raise ValueError("finite nonnegative exchange/slope rates and concentration in (0,.05] required")


def equilibrium_concentration(bed, geometry, water, sediment_config, config):
    h = np.asarray(water["depth_after_m"]).ravel()
    momentum = np.asarray(water["momentum_after"])
    velocity = np.divide(momentum, h[:, None], out=np.zeros_like(momentum), where=h[:, None] > sediment_config.dry_depth_m)
    speed = np.linalg.norm(velocity, axis=1)
    current = 9.81 * sediment_config.manning_s_m_third ** 2 * speed[:, None] * velocity
    current /= np.maximum(h, sediment_config.dry_depth_m)[:, None] ** (1. / 3.)
    waves = incident_wave_field(h.reshape(bed.shape), geometry, sediment_config) if sediment_config.wave_height_m else None
    orbital = np.zeros_like(h) if waves is None else waves["wave_orbital_velocity_m_s"].ravel()
    denominator = (sediment_config.sediment_density_kg_m3 / sediment_config.water_density_kg_m3 - 1.) * 9.81 * sediment_config.grain_diameter_m
    excess = np.zeros_like(h)
    for phase in range(sediment_config.wave_phases):
        wave_u = orbital * np.cos(2. * np.pi * (phase + .5) / sediment_config.wave_phases)
        shear = current + .5 * sediment_config.wave_friction_factor * (wave_u * abs(wave_u))[:, None] * np.asarray(sediment_config.wave_direction_xz)
        excess += np.maximum(np.linalg.norm(shear, axis=1) / denominator - sediment_config.critical_shields, 0.) ** 1.5
    excess /= sediment_config.wave_phases
    equilibrium = config.maximum_concentration * excess / (1. + excess)
    equilibrium[h <= sediment_config.dry_depth_m] = 0.
    if not config.enabled:
        equilibrium[:] = 0.
    return equilibrium, excess


def entrain(bed, mass, floor, geometry, water, sediment_config, config, equilibrium_state=None):
    config.validate()
    area = geometry["metadata"]["spacing_m"] ** 2
    h = np.asarray(water["depth_after_m"]).ravel()
    equilibrium, excess = equilibrium_state if equilibrium_state is not None else equilibrium_concentration(bed, geometry, water, sediment_config, config)
    dt = water["time_end_s"] - water["time_start_s"]
    requested = area * dt * config.erosion_velocity_m_s * excess if config.enabled else np.zeros_like(h)
    inventory = np.maximum((bed - floor).ravel(), 0.) * area * (1. - sediment_config.porosity)
    capacity = np.maximum(equilibrium * h * area - mass.ravel(), 0.)
    accepted = np.minimum(np.minimum(requested, inventory), capacity)
    fixed = np.asarray(geometry["arrays"]["fixed_bed_cell"], bool).ravel()
    accepted[fixed | (h <= sediment_config.dry_depth_m)] = 0.
    changed = bed - accepted.reshape(bed.shape) / (area * (1. - sediment_config.porosity))
    if np.max(abs(changed - bed)) > sediment_config.max_bed_change_m * (1. + 1.e-12):
        raise MorphodynamicStepTooLarge("v3 entrainment bed jump too large; retry shorter full interval")
    return changed, mass + accepted.reshape(mass.shape), accepted.reshape(bed.shape), {
        "entrained_solid_m3": float(accepted.sum()), "requested_entrainment_solid_m3": float(requested.sum()),
        "maximum_phase_mean_excess_shields_power": float(excess.max()), "capacity_or_inventory_limited_cells": int(np.count_nonzero(accepted < requested))}


def slope_transport(bed, floor, geometry, dt, sediment_config, config, depth_m):
    config.validate()
    a = geometry["arrays"]
    left, right = a["face_left"], a["face_right"]
    dx = geometry["metadata"]["spacing_m"]
    gradient = (bed.ravel()[left] - bed.ravel()[right]) / dx
    requested = np.sign(gradient) * np.maximum(abs(gradient) - config.critical_slope_m_m, 0.) * config.slope_mobility_m2_s * dx * dt
    if not config.slope_enabled:
        requested[:] = 0.
    fixed = np.asarray(a["fixed_bed_cell"], bool).ravel()
    requested[fixed[left] | fixed[right]] = 0.
    wet = np.asarray(depth_m).ravel() > sediment_config.dry_depth_m
    requested[~(wet[left] | wet[right])] = 0.
    donor, receiver = np.where(requested >= 0., left, right), np.where(requested >= 0., right, left)
    volume = abs(requested)
    # Never move more than pair equalization, even with a large requested dt.
    equalization = .5 * abs(bed.ravel()[left] - bed.ravel()[right]) * dx ** 2 * (1. - sediment_config.porosity)
    volume = np.minimum(volume, equalization)
    demand = np.bincount(donor, weights=volume, minlength=bed.size)
    inventory = np.maximum((bed - floor).ravel(), 0.) * dx ** 2 * (1. - sediment_config.porosity)
    factor = np.minimum(1., np.divide(inventory, demand, out=np.ones_like(inventory), where=demand > 0.))
    accepted = volume * factor[donor]
    transfer = np.sign(requested) * accepted
    change = np.bincount(receiver, weights=accepted, minlength=bed.size) - np.bincount(donor, weights=accepted, minlength=bed.size)
    changed = bed + change.reshape(bed.shape) / (dx ** 2 * (1. - sediment_config.porosity))
    if np.max(abs(changed - bed)) > sediment_config.max_bed_change_m * (1. + 1.e-12):
        raise MorphodynamicStepTooLarge("v3 slope bed jump too large; retry shorter full interval")
    return changed, transfer, {"slope_moved_solid_m3": float(accepted.sum()), "slope_net_residual_solid_m3": float(change.sum())}
