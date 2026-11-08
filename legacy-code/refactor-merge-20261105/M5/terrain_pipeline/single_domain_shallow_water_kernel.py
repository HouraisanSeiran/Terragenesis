"""Shared single-domain shallow-water kernel (R3 step 1).

Verbatim bodies from single_domain_shallow_water_support_v5/_v6/_v8/_v9,
single_domain_shallow_water_reconstruction_v8/_v9 and single_domain_shallow_water_v5/_v6.
The only difference between those pairs is which slope reconstruction they call, so the
reconstruction is injected: `reconstruct_independent` (v5 policy) or
`reconstruct_dry_neighbor` (v6 policy).  The two policies are NOT numerically equivalent
and must stay separate.  Equivalence: tests/test_hybrid_kernels_equivalence.py.
"""

from functools import partial

import numpy as np

from terrain_pipeline.single_domain_fine_geometry import prepare_subgrid_support, storage_stages
from terrain_pipeline.single_domain_shallow_water_execution import advance_shallow_water as _advance
from terrain_pipeline.single_domain_shallow_water_support import hydrostatic_hll, minmod


def reconstruct_independent(stage, velocity, depth, bed, support, boundary_kind, tailwater):
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


def reconstruct_dry_neighbor(stage, velocity, depth, bed, support, boundary_kind, tailwater):
    rows, columns = bed.shape
    fields = np.column_stack((stage, velocity)).reshape(rows, columns, 3)
    sx, sz = np.zeros_like(fields), np.zeros_like(fields)
    sx[:, 1:-1] = minmod(fields[:, 1:-1]-fields[:, :-2], fields[:, 2:]-fields[:, 1:-1])
    sz[1:-1] = minmod(fields[1:-1]-fields[:-2], fields[2:]-fields[1:-1])
    # Prescribed tailwater is a face value, so its half-cell distance contributes
    # twice the stage difference. Reflecting and drainage boundaries keep zero
    # slope; only kind 2 reservoirs provide a reconstruction constraint.
    depth_grid = depth.reshape(rows, columns)
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
            dry_neighbor = depth_grid[:, 1 if side == 0 else -2] == 0
            # A dry cell has no free surface: its minimum bed is not a stage
            # observation. Use the reservoir face's half-cell slope instead.
            interior[dry_neighbor, 0] = external[dry_neighbor, 0]
            sx[:, 0 if side == 0 else -1][opened] = minmod(interior, external)[opened]
        else:
            if rows < 2:
                continue
            edge = fields[0] if side == 0 else fields[-1]
            interior = fields[1]-edge if side == 0 else edge-fields[-2]
            external = 2*(edge-exterior) if side == 0 else 2*(exterior-edge)
            dry_neighbor = depth_grid[1 if side == 0 else -2] == 0
            interior[dry_neighbor, 0] = external[dry_neighbor, 0]
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


def make_segmented_rhs(_reconstruct):
    """shallow_water_rhs of support_v5/_v6 for the injected face reconstruction."""
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
    return shallow_water_rhs


def prepare_support(bed):
    support, datum = prepare_subgrid_support(bed)
    canonical = bed["arrays"]["canonical_bed_center_m"]-datum
    rows, columns = bed["arrays"]["H2_m"].shape
    factor = int(bed["metadata"]["spacing_m"])
    support["subcell_bed_position_relative_m"] = canonical.reshape(rows, factor, columns, factor).transpose(0, 2, 1, 3).reshape(rows*columns, factor, factor)
    return support, datum


def face_fields(reconstruction, cells, axis, sign, factor):
    coordinate = (np.arange(factor)+.5)/factor-.5
    normal = reconstruction["slope_x" if axis == 0 else "slope_z"][cells]
    tangent = reconstruction["slope_z" if axis == 0 else "slope_x"][cells]
    return reconstruction["center"][cells, None, :]+sign*.5*normal[:, None, :]+coordinate[None, :, None]*tangent[:, None, :]


def internal_bed_pressure(reconstruction, support, *, spacing, gravity):
    bed = support["subcell_bed_position_relative_m"]
    factor = bed.shape[1]
    coordinate = (np.arange(factor)+.5)/factor-.5
    interfaces = (np.arange(factor-1)+1)/factor-.5
    eta0 = reconstruction["center"][:, 0, None, None]
    sx = reconstruction["slope_x"][:, 0, None, None]
    sz = reconstruction["slope_z"][:, 0, None, None]
    eta_x = eta0+sx*interfaces[None, None, :]+sz*coordinate[None, :, None]
    eta_z = eta0+sx*coordinate[None, None, :]+sz*interfaces[None, :, None]
    delta_x = np.maximum(eta_x-bed[:, :, 1:], 0.)**2-np.maximum(eta_x-bed[:, :, :-1], 0.)**2
    delta_z = np.maximum(eta_z-bed[:, 1:, :], 0.)**2-np.maximum(eta_z-bed[:, :-1, :], 0.)**2
    return .5*gravity*np.column_stack((delta_x.sum(axis=(1, 2)), delta_z.sum(axis=(1, 2))))/(spacing*factor)


def make_reconstruct(_reconstruct):
    """reconstruct of reconstruction_v8/_v9 for the injected face reconstruction."""
    def reconstruct(state, bed, support, boundary_kind, tailwater):
        stage = storage_stages(state[:, 0], support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"])
        velocity = np.divide(state[:, 1:], state[:, 0, None], out=np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
        faces = _reconstruct(stage, velocity, state[:, 0], bed, support, boundary_kind, tailwater)
        slope_x, slope_z = faces[1]-faces[0], faces[3]-faces[2]
        factor = support["subcell_bed_position_relative_m"].shape[1]
        coordinate = (np.arange(factor)+.5)/factor-.5
        x, z = np.meshgrid(coordinate, coordinate)
        eta_offset = slope_x[:, 0, None, None]*x+slope_z[:, 0, None, None]*z
        effective_bed = support["subcell_bed_position_relative_m"]-eta_offset
        sorted_effective_bed = np.sort(effective_bed.reshape(len(state), -1), axis=1)
        eta0 = storage_stages(state[:, 0], sorted_effective_bed, np.cumsum(sorted_effective_bed, axis=1))
        subdepth = np.maximum(eta0[:, None, None]-effective_bed, 0.)
        velocity_offset = slope_x[:, None, None, 1:]*x[None, :, :, None]+slope_z[:, None, None, 1:]*z[None, :, :, None]
        offset_momentum = np.mean(subdepth[:, :, :, None]*velocity_offset, axis=(1, 2))
        center_velocity = np.divide(state[:, 1:]-offset_momentum, state[:, 0, None],
            out=np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
        return dict(center=np.column_stack((eta0, center_velocity)), slope_x=slope_x, slope_z=slope_z,
            subcell_depth=subdepth, subcell_velocity=center_velocity[:, None, None, :]+velocity_offset)
    return reconstruct


def make_linear_stage_rhs(reconstruct, face_fields, internal_bed_pressure):
    """shallow_water_rhs of support_v8/_v9 for the injected reconstruction functions."""
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
        reconstruction = reconstruct(state, bed, support, boundary_kind, tailwater)
        position_bed = support["subcell_bed_position_relative_m"]
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
            first_fields = face_fields(reconstruction, left[mask], axis, 1., segments)
            second_fields = face_fields(reconstruction, right[mask], axis, -1., segments)
            hl = np.maximum(first_fields[:, :, 0]-crests[mask], 0.)
            hr = np.maximum(second_fields[:, :, 0]-crests[mask], 0.)
            ul = first_fields[:, :, 1:].reshape(-1, 2)
            ur = second_fields[:, :, 1:].reshape(-1, 2)
            ls = np.column_stack((hl.ravel(), hl.ravel()[:, None]*ul))
            rs = np.column_stack((hr.ravel(), hr.ravel()[:, None]*ur))
            f, _, _, speed = hydrostatic_hll(ls, rs, crest, crest, gravity=gravity, axis=axis)
            flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
            own_left_bed = position_bed[left[mask], :, -1] if axis == 0 else position_bed[left[mask], -1, :]
            own_right_bed = position_bed[right[mask], :, 0] if axis == 0 else position_bed[right[mask], 0, :]
            pressure_left[mask] = .5*gravity*np.mean(hl**2-np.maximum(first_fields[:, :, 0]-own_left_bed, 0.)**2, axis=1)
            pressure_right[mask] = .5*gravity*np.mean(hr**2-np.maximum(second_fields[:, :, 0]-own_right_bed, 0.)**2, axis=1)
            maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
            mask = boundary_axes == axis
            crest = boundary_crests[mask]
            fields = np.empty((mask.sum(), segments, 3))
            negative = signs[mask] < 0
            fields[negative] = face_fields(reconstruction, cells[mask][negative], axis, -1., segments)
            fields[~negative] = face_fields(reconstruction, cells[mask][~negative], axis, 1., segments)
            h = np.maximum(fields[:, :, 0]-crest, 0.)
            u = fields[:, :, 1:].reshape(-1, 2)
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
            own_bed = np.empty_like(crest)
            if axis == 0:
                own_bed[negative] = position_bed[cells[mask][negative], :, 0]
                own_bed[~negative] = position_bed[cells[mask][~negative], :, -1]
            else:
                own_bed[negative] = position_bed[cells[mask][negative], 0, :]
                own_bed[~negative] = position_bed[cells[mask][~negative], -1, :]
            pressure_boundary[mask] = .5*gravity*np.mean(h**2-np.maximum(fields[:, :, 0]-own_bed, 0.)**2, axis=1)
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
        pressure[:, 1:] = internal_bed_pressure(reconstruction, support, spacing=spacing, gravity=gravity)
        np.add.at(pressure, (left, axes+1), pressure_left/spacing)
        np.add.at(pressure, (right, axes+1), -pressure_right/spacing)
        np.add.at(pressure, (cells, boundary_axes+1), signs*pressure_boundary/spacing)
        rhs += pressure
        return rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure,
            reconstruction_center=reconstruction["center"], reconstruction_slope_x=reconstruction["slope_x"], reconstruction_slope_z=reconstruction["slope_z"],
            maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum()))
    return shallow_water_rhs


def make_advance_shallow_water(MODEL, shallow_water_rhs):
    """advance_shallow_water of single_domain_shallow_water_v5/_v6 for one support module."""
    def advance_shallow_water(geometry, **kwargs):
        arrays = geometry["arrays"]
        support = {name: arrays[name] for name in ("subcell_bed_relative_m", "subcell_prefix_relative_m",
            "face_segment_crest_relative_m", "boundary_segment_crest_relative_m")}

        def wave_speed(state, gravity):
            stage = storage_stages(state[:, 0], support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"])
            maximum_depth = np.maximum(stage-support["subcell_bed_relative_m"][:, 0], 0.)
            velocity = np.divide(state[:, 1:], state[:, 0, None], out=np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
            return float(1.5*abs(velocity).sum(axis=1).max(initial=0)+2*np.sqrt(gravity*max(float(stage.max()-support["subcell_bed_relative_m"].min()),0)))

        return _advance(geometry, rhs=partial(shallow_water_rhs, support=support), model=MODEL,
            hydraulic_datum_m=geometry["metadata"]["hydraulic_datum_m"], wave_speed=wave_speed,
            stage_provider=lambda depth: storage_stages(depth, support["subcell_bed_relative_m"], support["subcell_prefix_relative_m"]),
            face_evaluation_multiplier=support["face_segment_crest_relative_m"].shape[1],
            scope="independent FV canonical subgrid storage and MUSCL segmented advective HLL; SSPRK2; uncalibrated",
            physical_limitation="one velocity vector per coarse cell; segmented pressure support; no calibrated natural certification",
            **kwargs)
    return advance_shallow_water
