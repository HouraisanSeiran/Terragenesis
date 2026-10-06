"""Storage-consistent subgrid shallow water with advective segmented HLL flux.

Each coarse cell evolves mean water volume and both momentum components. Its
free surface comes from canonical hypsometry; face depths use canonical segment
crests. Side-specific hydrostatic pressure integrals balance a uniform stage.
"""

import numpy as np

from terrain_pipeline.single_domain_fine_geometry import storage_stages
from terrain_pipeline.single_domain_shallow_water_support import hydrostatic_hll, minmod

MODEL = "single-domain-subgrid-MUSCL-storage-segmented-HLL-SSPRK2-v5"


def _reconstruct(stage, velocity, depth, bed, support, boundary_kind, tailwater):
    rows, columns = bed.shape
    fields = np.column_stack((stage, velocity)).reshape(rows, columns, 3)
    sx, sz = np.zeros_like(fields), np.zeros_like(fields)
    sx[:, 1:-1] = minmod(fields[:, 1:-1]-fields[:, :-2], fields[:, 2:]-fields[:, 1:-1])
    sz[1:-1] = minmod(fields[1:-1]-fields[:-2], fields[2:]-fields[1:-1])
    # Prescribed tailwater is a face value, so its half-cell distance contributes
    # twice the stage difference. Reflecting and drainage boundaries keep zero
    # slope; only kind 2 reservoirs provide a reconstruction constraint.
    for axis, side, begin, end in ((0, 0, 0, rows), (0, 1, rows, 2*rows),
                                  (1, 0, 2*rows, 2*rows+columns), (1, 1, 2*rows+columns, 2*(rows+columns))):
        opened = boundary_kind[begin:end] == 2
        exterior = np.zeros((end-begin, 3))
        exterior[:, 0] = tailwater[begin:end]
        if axis == 0:
            if columns < 2:
                continue
            edge = fields[:, 0] if side == 0 else fields[:, -1]
            interior = fields[:, 1]-edge if side == 0 else edge-fields[:, -2]
            external = 2*(edge-exterior) if side == 0 else 2*(exterior-edge)
            sx[:, 0 if side == 0 else -1][opened] = minmod(interior, external)[opened]
        else:
            if rows < 2:
                continue
            edge = fields[0] if side == 0 else fields[-1]
            interior = fields[1]-edge if side == 0 else edge-fields[-2]
            external = 2*(edge-exterior) if side == 0 else 2*(exterior-edge)
            sz[0 if side == 0 else -1][opened] = minmod(interior, external)[opened]
    dry = depth.reshape(rows, columns) == 0
    sx[dry], sz[dry] = 0., 0.
    available = (stage-support["subcell_bed_relative_m"][:, 0]).reshape(rows, columns)
    for slope in (sx, sz):
        ratio = np.minimum(1., np.divide(2*available, abs(slope[:, :, 0]),
            out=np.ones_like(available), where=slope[:, :, 0] != 0))
        slope *= ratio[:, :, None]
    return [(fields-.5*sx).reshape(-1, 3), (fields+.5*sx).reshape(-1, 3),
        (fields-.5*sz).reshape(-1, 3), (fields+.5*sz).reshape(-1, 3)]


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
    faces = _reconstruct(stage, velocity, state[:, 0], bed, support, boundary_kind, tailwater)
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
        reconstructed_left = faces[1 if axis == 0 else 3][left[mask]]
        reconstructed_right = faces[0 if axis == 0 else 2][right[mask]]
        hl = np.maximum(reconstructed_left[:, 0, None]-crests[mask], 0.)
        hr = np.maximum(reconstructed_right[:, 0, None]-crests[mask], 0.)
        ul = np.repeat(reconstructed_left[:, 1:], segments, axis=0)
        ur = np.repeat(reconstructed_right[:, 1:], segments, axis=0)
        ls = np.column_stack((hl.ravel(), hl.ravel()[:, None]*ul))
        rs = np.column_stack((hr.ravel(), hr.ravel()[:, None]*ur))
        f, _, _, speed = hydrostatic_hll(ls, rs, crest, crest, gravity=gravity, axis=axis)
        flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        pressure_left[mask] = .5*gravity*np.mean(np.maximum(stage[left[mask], None]-crests[mask], 0.)**2, axis=1)
        pressure_right[mask] = .5*gravity*np.mean(np.maximum(stage[right[mask], None]-crests[mask], 0.)**2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
        mask = boundary_axes == axis
        crest = boundary_crests[mask]
        boundary_state = np.empty((mask.sum(), 3))
        negative = signs[mask] < 0
        boundary_state[negative] = faces[0 if axis == 0 else 2][cells[mask][negative]]
        boundary_state[~negative] = faces[1 if axis == 0 else 3][cells[mask][~negative]]
        h = np.maximum(boundary_state[:, 0, None]-crest, 0.)
        u = np.repeat(boundary_state[:, 1:], segments, axis=0)
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
        pressure_boundary[mask] = .5*gravity*np.mean(np.maximum(stage[cells[mask], None]-crest, 0.)**2, axis=1)
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




