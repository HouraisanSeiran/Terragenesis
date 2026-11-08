"""Conservative one-domain adaptive leaf HLL and canonical Manning kernels."""

import math

import numpy as np
from numba import njit

from terrain_pipeline.single_domain_shallow_water_accelerated_v7 import _hll


@njit(cache=True, fastmath=False)
def leaf_stages(depth, counts, bed, prefix):
    result = np.empty(len(depth))
    offset = 0
    for cell in range(len(depth)):
        count = counts[cell]
        volume = depth[cell]*count
        wet = 0
        for index in range(count):
            if volume >= (index+1)*bed[offset+index]-prefix[offset+index]:
                wet += 1
        wet = max(wet, 1)
        result[cell] = (volume+prefix[offset+wet-1])/wet
        offset += count
    return result


@njit(cache=True, fastmath=False)
def leaf_rhs_kernel(state, counts, bed, prefix, area, left, right, axes, crests,
                    cells, boundary_axes, signs, kinds, boundary_bed, boundary_crests,
                    tailwater, gravity, dt):
    count = len(state)
    stage = leaf_stages(state[:, 0], counts, bed, prefix)
    velocity = np.zeros((count, 2))
    for cell in range(count):
        if state[cell, 0] > 0:
            velocity[cell, 0] = state[cell, 1]/state[cell, 0]
            velocity[cell, 1] = state[cell, 2]/state[cell, 0]
    flux, boundary_flux = np.zeros((len(left), 3)), np.zeros((len(cells), 3))
    first_pressure, second_pressure, boundary_pressure = np.zeros(len(left)), np.zeros(len(left)), np.zeros(len(cells))
    maximum_speed = 0.
    for face in range(len(left)):
        first, second, axis, crest = left[face], right[face], axes[face], crests[face]
        hl, hr = max(stage[first]-crest, 0.), max(stage[second]-crest, 0.)
        mass, mx, mz, speed = _hll(hl, hr, velocity[first, 0], velocity[first, 1], velocity[second, 0], velocity[second, 1], crest, gravity, axis)
        flux[face, 0], flux[face, 1], flux[face, 2] = mass, mx, mz
        first_pressure[face], second_pressure[face] = .5*gravity*hl**2, .5*gravity*hr**2
        maximum_speed = max(maximum_speed, speed)
    for face in range(len(cells)):
        cell, axis, sign = cells[face], boundary_axes[face], signs[face]
        crest = boundary_bed[face]
        if kinds[face] != 0:
            crest = max(crest, boundary_crests[face])
        h = max(stage[cell]-crest, 0.)
        ux, uz = velocity[cell, 0], velocity[cell, 1]
        gx, gz = ux, uz
        if axis == 0:
            gx = -gx
        else:
            gz = -gz
        ghost_h = h
        if kinds[face] != 0:
            exterior = crest if kinds[face] == 1 else tailwater[face]
            ghost_h, gx, gz = max(exterior-crest, 0.), 0., 0.
        if axis == 0:
            ux, gx = ux*sign, gx*sign
        else:
            uz, gz = uz*sign, gz*sign
        mass, mx, mz, speed = _hll(h, ghost_h, ux, uz, gx, gz, crest, gravity, axis)
        flux_x, flux_z = (mx*sign, mz) if axis == 0 else (mx, mz*sign)
        boundary_flux[face, 0], boundary_flux[face, 1], boundary_flux[face, 2] = mass, flux_x, flux_z
        boundary_pressure[face] = .5*gravity*h**2
        maximum_speed = max(maximum_speed, speed)
    outgoing = np.zeros(count)
    for face in range(len(left)):
        outgoing[left[face]] += max(flux[face, 0], 0.)
        outgoing[right[face]] += max(-flux[face, 0], 0.)
    for face in range(len(cells)):
        outgoing[cells[face]] += max(boundary_flux[face, 0], 0.)
    scales = np.ones(count)
    limited = 0
    for cell in range(count):
        if outgoing[cell]*dt > state[cell, 0]*area[cell]:
            scales[cell] = state[cell, 0]*area[cell]/(outgoing[cell]*dt)*(1-1e-12)
            limited += 1
    for face in range(len(left)):
        donor = left[face] if flux[face, 0] >= 0 else right[face]
        for component in range(3):
            flux[face, component] *= scales[donor]
    for face in range(len(cells)):
        if boundary_flux[face, 0] >= 0:
            for component in range(3):
                boundary_flux[face, component] *= scales[cells[face]]
    rhs, pressure = np.zeros_like(state), np.zeros_like(state)
    for face in range(len(left)):
        first, second, component = left[face], right[face], axes[face]+1
        for quantity in range(3):
            rhs[first, quantity] -= flux[face, quantity]/area[first]
            rhs[second, quantity] += flux[face, quantity]/area[second]
        pressure[first, component] += first_pressure[face]/area[first]
        pressure[second, component] -= second_pressure[face]/area[second]
    for face in range(len(cells)):
        cell, component = cells[face], boundary_axes[face]+1
        for quantity in range(3):
            rhs[cell, quantity] -= boundary_flux[face, quantity]/area[cell]
        pressure[cell, component] += signs[face]*boundary_pressure[face]/area[cell]
    rhs += pressure
    return rhs, flux, boundary_flux, pressure, maximum_speed, limited, scales.min()


def adaptive_rhs(geometry, state, *, tailwater_m, gravity=9.81, dt=0.):
    a, meta = geometry["arrays"], geometry["metadata"]
    tail = np.asarray(tailwater_m)-meta["hydraulic_datum_m"]
    result = leaf_rhs_kernel(state, a["subcell_count"], a["sorted_subcell_bed_relative_m"], a["prefix_subcell_bed_relative_m"],
        a["leaf_area_m2"], a["face_left"], a["face_right"], a["face_axis"], a["face_crest_relative_m"],
        a["boundary_cell"], a["boundary_axis"], a["boundary_sign"], a["boundary_kind"], a["boundary_bed_relative_m"],
        a["boundary_crest_m"]-meta["hydraulic_datum_m"], tail, gravity, dt)
    rhs, flux, boundary, pressure, speed, limited, scale = result
    return rhs, dict(internal_flux_m2_s=flux, boundary_flux_m2_s=boundary, bed_source=pressure,
        maximum_wave_speed_m_s=float(speed), limited_donors=int(limited), minimum_limiter_factor=float(scale))


@njit(cache=True, fastmath=False)
def leaf_damping_kernel(state, counts, bed, prefix, dt, gravity, roughness):
    stage = leaf_stages(state[:, 0], counts, bed, prefix)
    damping, factor = np.zeros(len(state)), np.zeros(len(state))
    offset = 0
    for cell in range(len(state)):
        for index in range(counts[cell]):
            h = max(stage[cell]-bed[offset+index], 0.)
            if h > 0:
                factor[cell] += h**(-1/3)
        factor[cell] /= counts[cell]
        squared = state[cell, 0]**2
        denominator = squared+dt*gravity*roughness**2*math.hypot(state[cell, 1], state[cell, 2])*factor[cell]
        if denominator > 0:
            damping[cell] = squared/denominator
        offset += counts[cell]
    return damping, factor


def adaptive_drag(geometry, state, *, dt, gravity, roughness):
    a = geometry["arrays"]
    return leaf_damping_kernel(state, a["subcell_count"], a["sorted_subcell_bed_relative_m"], a["prefix_subcell_bed_relative_m"], dt, gravity, roughness)


def canonical_inventory(geometry, state):
    """Display/comparison inventory reconstruction, never a hidden fine solve."""
    a = geometry["arrays"]
    stage = leaf_stages(state[:, 0], a["subcell_count"], a["sorted_subcell_bed_relative_m"], a["prefix_subcell_bed_relative_m"])
    owner = a["canonical_owner"]
    h = np.maximum(stage[owner]-(a["canonical_bed_m"]-geometry["metadata"]["hydraulic_datum_m"]), 0.)
    velocity = np.divide(state[:, 1:], state[:, 0, None], out=np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    return h, h[:, :, None]*velocity[owner]
