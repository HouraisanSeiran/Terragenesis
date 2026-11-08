"""Storage-consistent subgrid shallow water with advective segmented HLL flux.

Each coarse cell evolves mean water volume and both momentum components. Its
free surface comes from canonical hypsometry; face depths use canonical segment
crests. Side-specific hydrostatic pressure integrals balance a uniform stage.
"""

import numpy as np

from terrain_pipeline.single_domain_fine_geometry import storage_stages
from terrain_pipeline.single_domain_shallow_water_support import hydrostatic_hll

MODEL = "single-domain-subgrid-storage-segmented-HLL-SSPRK2-v3"


def shallow_water_rhs(state, bed, *, support, spacing, gravity, boundary_kind, tailwater,
                      roughness, dt, boundary_crest=None):
    rows, columns = bed.shape
    count = bed.size
    grid = np.arange(count).reshape(rows, columns)
    left = np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    right = np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    axes = np.r_[np.zeros(rows*(columns-1), np.int64), np.ones((rows-1)*columns, np.int64)]
    cells = np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    boundary_axes = np.r_[np.zeros(2*rows, np.int64), np.ones(2*columns, np.int64)]
    signs = np.r_[-np.ones(rows), np.ones(rows), -np.ones(columns), np.ones(columns)]
    stage = storage_stages(state[:, 0], support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"])
    velocity = np.divide(state[:, 1:], state[:, 0, None], out=np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    crests = support["face_segment_crest_relative_m"]
    boundary_crests = support["boundary_segment_crest_relative_m"].copy()
    if boundary_crest is not None:
        opened = boundary_kind != 0
        boundary_crests[opened] = np.maximum(boundary_crests[opened], boundary_crest[opened, None])
    segments = crests.shape[1]
    flux = np.zeros((len(left), 3))
    boundary_flux = np.zeros((len(cells), 3))
    pressure_left, pressure_right = np.zeros(len(left)), np.zeros(len(left))
    pressure_boundary = np.zeros(len(cells))
    maximum_speed = 0.
    for axis in (0, 1):
        mask = axes == axis
        crest = crests[mask].ravel()
        hl = np.maximum(stage[left[mask], None]-crests[mask], 0.)
        hr = np.maximum(stage[right[mask], None]-crests[mask], 0.)
        ul = np.repeat(velocity[left[mask]], segments, axis=0)
        ur = np.repeat(velocity[right[mask]], segments, axis=0)
        ls = np.column_stack((hl.ravel(), hl.ravel()[:, None]*ul))
        rs = np.column_stack((hr.ravel(), hr.ravel()[:, None]*ur))
        f, _, _, speed = hydrostatic_hll(ls, rs, crest, crest, gravity=gravity, axis=axis)
        flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        pressure_left[mask] = .5*gravity*np.mean(hl**2, axis=1)
        pressure_right[mask] = .5*gravity*np.mean(hr**2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
        mask = boundary_axes == axis
        crest = boundary_crests[mask]
        h = np.maximum(stage[cells[mask], None]-crest, 0.)
        u = np.repeat(velocity[cells[mask]], segments, axis=0)
        sign = np.repeat(signs[mask], segments)
        first = np.column_stack((h.ravel(), h.ravel()[:, None]*u))
        ghost = first.copy()
        ghost[:, axis+1] *= -1
        opened = np.repeat(boundary_kind[mask] != 0, segments)
        exterior_stage = np.where(boundary_kind[mask, None] == 1, crest, tailwater[mask, None])
        ghost[opened, 0] = np.maximum(exterior_stage-crest, 0.).ravel()[opened]
        ghost[opened, 1:] = 0.
        first[:, axis+1] *= sign
        ghost[:, axis+1] *= sign
        f, _, _, speed = hydrostatic_hll(first, ghost, crest.ravel(), crest.ravel(), gravity=gravity, axis=axis)
        f[:, axis+1] *= sign
        boundary_flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        pressure_boundary[mask] = .5*gravity*np.mean(h**2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
    outgoing = np.bincount(left, weights=np.maximum(flux[:, 0], 0)*spacing, minlength=count)
    outgoing += np.bincount(right, weights=np.maximum(-flux[:, 0], 0)*spacing, minlength=count)
    outgoing += np.bincount(cells, weights=np.maximum(boundary_flux[:, 0], 0)*spacing, minlength=count)
    scales = np.ones(count)
    limited = outgoing*dt > state[:, 0]*spacing**2
    scales[limited] = state[limited, 0]*spacing**2/(outgoing[limited]*dt)*(1-1e-12)
    flux *= np.where(flux[:, 0] >= 0, scales[left], scales[right])[:, None]
    boundary_flux *= np.where(boundary_flux[:, 0] >= 0, scales[cells], 1.)[:, None]
    rhs = np.zeros_like(state)
    for component in range(3):
        np.add.at(rhs[:, component], left, -flux[:, component]/spacing)
        np.add.at(rhs[:, component], right, flux[:, component]/spacing)
        np.add.at(rhs[:, component], cells, -boundary_flux[:, component]/spacing)
    pressure = np.zeros_like(state)
    np.add.at(pressure, (left, axes+1), pressure_left/spacing)
    np.add.at(pressure, (right, axes+1), -pressure_right/spacing)
    np.add.at(pressure, (cells, boundary_axes+1), signs*pressure_boundary/spacing)
    rhs += pressure
    return rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure,
        maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum()))
