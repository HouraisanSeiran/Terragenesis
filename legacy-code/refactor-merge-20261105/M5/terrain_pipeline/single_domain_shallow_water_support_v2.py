"""MUSCL hydrostatic shallow-water flux and matching in-cell bed source.

Free surface, bed and velocities share limited slopes. Hydrostatic face pressure
corrections handle jumps; the in-cell pressure integral balances continuous bed
variation. Reconstruction falls back locally at dry cells, without changing mass.
"""

import numpy as np

from terrain_pipeline.single_domain_shallow_water_support import hydrostatic_hll, minmod

MODEL = "single-domain-MUSCL-hydrostatic-HLL-SSPRK2-v2"


def _slopes(values, axis):
    result = np.zeros_like(values)
    if axis == 0:
        result[1:-1] = minmod(values[1:-1]-values[:-2], values[2:]-values[1:-1])
    else:
        result[:, 1:-1] = minmod(values[:, 1:-1]-values[:, :-2], values[:, 2:]-values[:, 1:-1])
    return result


def reconstruct(state, bed):
    """Return W/E/N/S states and beds, all with nonnegative face depths."""
    rows, columns = bed.shape
    fields = np.empty((rows, columns, 4))
    fields[:, :, 0] = state[:, 0].reshape(bed.shape)+bed
    fields[:, :, 1] = bed
    fields[:, :, 2:] = np.divide(state[:, 1:], state[:, 0, None],
        out=np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0).reshape(rows, columns, 2)
    sx, sz = _slopes(fields, 1), _slopes(fields, 0)
    depth = state[:, 0].reshape(bed.shape)
    dry = depth == 0
    sx[dry], sz[dry] = 0., 0.
    # Scale both eta and bed slopes together so the reconstructed difference
    # stays positive; a lake's equal eta/bed differences remain exactly balanced.
    for slope in (sx, sz):
        depth_slope = slope[:, :, 0]-slope[:, :, 1]
        factor = np.minimum(1., np.divide(2*depth, abs(depth_slope),
            out=np.ones_like(depth), where=depth_slope != 0))
        slope *= factor[:, :, None]
    faces = (fields-.5*sx, fields+.5*sx, fields-.5*sz, fields+.5*sz)
    states, beds = [], []
    for face in faces:
        h = np.maximum(face[:, :, 0]-face[:, :, 1], 0.)
        states.append(np.column_stack((h.ravel(), (h[:, :, None]*face[:, :, 2:]).reshape(-1, 2))))
        beds.append(face[:, :, 1].ravel())
    return states, beds


def shallow_water_rhs(state, bed, *, spacing, gravity, boundary_kind, tailwater,
                      roughness, dt, boundary_crest=None):
    rows, columns = bed.shape
    count = rows*columns
    grid = np.arange(count).reshape(rows, columns)
    left = np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    right = np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    axes = np.r_[np.zeros(rows*(columns-1), np.int64), np.ones((rows-1)*columns, np.int64)]
    cells = np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    boundary_axes = np.r_[np.zeros(2*rows, np.int64), np.ones(2*columns, np.int64)]
    signs = np.r_[-np.ones(rows), np.ones(rows), -np.ones(columns), np.ones(columns)]
    face_states, face_beds = reconstruct(state, bed)
    flux = np.zeros((len(left), 3))
    correction_left, correction_right = np.zeros(len(left)), np.zeros(len(left))
    maximum_speed = 0.
    for axis, side_left, side_right in ((0, 1, 0), (1, 3, 2)):
        mask = axes == axis
        f, cl, cr, speeds = hydrostatic_hll(face_states[side_left][left[mask]], face_states[side_right][right[mask]],
            face_beds[side_left][left[mask]], face_beds[side_right][right[mask]], gravity=gravity, axis=axis)
        flux[mask], correction_left[mask], correction_right[mask] = f, cl, cr
        maximum_speed = max(maximum_speed, float(speeds.max(initial=0)))
    boundary_flux = np.zeros((len(cells), 3))
    boundary_source = np.zeros_like(boundary_flux)
    for axis, side, begin, end in ((0, 0, 0, rows), (0, 1, rows, 2*rows),
                                  (1, 2, 2*rows, 2*rows+columns), (1, 3, 2*rows+columns, len(cells))):
        selection = slice(begin, end)
        ids, sign = cells[selection], signs[selection]
        first = face_states[side][ids].copy()
        ghost = first.copy()
        ghost[:, axis+1] *= -1
        first_bed = face_beds[side][ids]
        ghost_bed = first_bed.copy()
        if boundary_crest is not None:
            opened = boundary_kind[selection] != 0
            ghost_bed[opened] = np.maximum(ghost_bed[opened], boundary_crest[selection][opened])
        opened = boundary_kind[selection] != 0
        exterior = np.where(boundary_kind[selection] == 1, ghost_bed, tailwater[selection])
        ghost[opened, 0] = np.maximum(exterior[opened]-ghost_bed[opened], 0.)
        ghost[opened, 1:] = 0.
        first[:, axis+1] *= sign
        ghost[:, axis+1] *= sign
        f, cl, _, speed = hydrostatic_hll(first, ghost, first_bed, ghost_bed, gravity=gravity, axis=axis)
        f[:, axis+1] *= sign
        boundary_flux[selection] = f
        boundary_source[selection, axis+1] = -cl*sign/spacing
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
    np.add.at(pressure, (left, axes+1), -correction_left/spacing)
    np.add.at(pressure, (right, axes+1), correction_right/spacing)
    for component in (1, 2):
        np.add.at(pressure[:, component], cells, boundary_source[:, component])
    for axis, low, high in ((0, 0, 1), (1, 2, 3)):
        pressure[:, axis+1] -= gravity*.5*(face_states[low][:, 0]+face_states[high][:, 0])*(face_beds[high]-face_beds[low])/spacing
    rhs += pressure
    return rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure,
        maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum()))
