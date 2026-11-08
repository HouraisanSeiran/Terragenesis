"""Implicit, finite-time 2-D marine solid transport on a shared MarineState.

Velocity is a prescribed depth-averaged scenario (m/s), diffusivity is in
m²/s, and settling velocity is in m/s. This is not a hydrodynamic solver.
Only explicitly marked ocean seed cells exchange material with the exterior.
"""
from dataclasses import dataclass, replace

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve

from .coastal_marine_sediment import classify_ocean, _park_and_release, _plume_field, _wet_receiver


@dataclass(frozen=True)
class LongtermConfig:
    sea_level_m: float = 0.
    velocity_x_m_s: float = .01
    velocity_z_m_s: float = .002
    diffusivity_m2_s: float = 30.
    settling_velocity_m_s: float = .00001
    minimum_depth_m: float = 1.
    boundary_rate_s: float = .00001
    max_step_s: float = 365.25 * 86400
    max_rise_m: float = 1.
    source_relocation_cells: int = 3
    boundary_transport: str = 'exchange_only'


def normalize_forcing_parameters(parameters):
    """Copy a saved forcing identity, filling only the old boundary default."""
    if parameters is None:
        return None
    normalized = dict(parameters)
    normalized.setdefault('boundary_transport', LongtermConfig.boundary_transport)
    return normalized


def _nearby_receivers(wet, allowed, steps):
    """Map dry original-ocean cells to water through at most steps D4 faces."""
    rows, cols = np.indices(wet.shape)
    target_row = np.where(wet, rows, -1)
    target_col = np.where(wet, cols, -1)
    reached = wet.copy()
    for _ in range(steps):
        previous = reached.copy()
        for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            dst = (slice(max(0, -dr), min(wet.shape[0], wet.shape[0]-dr)),
                   slice(max(0, -dc), min(wet.shape[1], wet.shape[1]-dc)))
            src = (slice(max(0, dr), min(wet.shape[0], wet.shape[0]+dr)),
                   slice(max(0, dc), min(wet.shape[1], wet.shape[1]+dc)))
            take = allowed[dst] & ~reached[dst] & previous[src]
            target_row[dst][take] = target_row[src][take]
            target_col[dst][take] = target_col[src][take]
            reached[dst][take] = True
    return target_row, target_col


def _solve(mobile, source, wet, depth, seeds, spacing, dt, capacity, cfg, velocity=None, mixing=None):
    """Backward Euler with an active set for finite bed accommodation."""
    indices = np.full(wet.shape, -1, dtype=np.int32)
    indices[wet] = np.arange(wet.sum())
    count = int(wet.sum())
    if not count:
        return mobile.copy(), np.zeros_like(mobile), np.zeros_like(mobile)
    diagonal = np.ones(count)
    rows, cols, values = [], [], []
    for axis in (1, 0):
        left = [slice(None), slice(None)]
        right = [slice(None), slice(None)]
        left[axis] = slice(None, -1)
        right[axis] = slice(1, None)
        left, right = tuple(left), tuple(right)
        face = wet[left] & wet[right]
        a, b = indices[left][face], indices[right][face]
        if velocity is not None:
            field = velocity[0 if axis == 1 else 1]
            face_velocity = (field[left][face] + field[right][face]) * .5
        else:
            face_velocity = cfg.velocity_x_m_s if axis == 1 else cfg.velocity_z_m_s
        diffusion = cfg.diffusivity_m2_s / spacing**2
        if mixing is not None:
            weight = mixing[0 if axis == 1 else 1]
            diffusion = diffusion * (1. + .5 * (weight[left][face] + weight[right][face]))
        for donor, receiver, rate in ((a, b, diffusion + np.maximum(face_velocity, 0.) / spacing),
                                      (b, a, diffusion + np.maximum(-face_velocity, 0.) / spacing)):
            np.add.at(diagonal, donor, dt * rate)
            rows.append(receiver); cols.append(donor)
            values.append(np.broadcast_to(-dt * rate, (len(donor),)))
    boundary = cfg.boundary_rate_s * seeds[wet]
    if cfg.boundary_transport == 'advective_outflow':
        # Interior advection already debits its upwind donor. Complete the same
        # flux through explicitly open exterior faces; no unknown inflow source.
        vx = np.full(wet.shape, cfg.velocity_x_m_s) if velocity is None else velocity[0]
        vz = np.full(wet.shape, cfg.velocity_z_m_s) if velocity is None else velocity[1]
        out_rate = np.zeros(wet.shape)
        out_rate[:, 0] += np.maximum(-vx[:, 0], 0.) / spacing
        out_rate[:, -1] += np.maximum(vx[:, -1], 0.) / spacing
        out_rate[0, :] += np.maximum(-vz[0, :], 0.) / spacing
        out_rate[-1, :] += np.maximum(vz[-1, :], 0.) / spacing
        boundary += out_rate[wet] * seeds[wet]
    diagonal += dt * boundary
    if rows:
        offdiag = sparse.coo_matrix((np.concatenate(values),
            (np.concatenate(rows), np.concatenate(cols))), shape=(count, count)).tocsr()
    else:
        offdiag = sparse.csr_matrix((count, count))
    rhs = mobile[wet] + dt * source[wet]
    k = cfg.settling_velocity_m_s / np.maximum(depth[wet], cfg.minimum_depth_m)
    cap = capacity[wet]
    k_eff = np.where(cap > 0, k, 0.)
    fixed = np.zeros(count)
    # Once an unconstrained solve exceeds capacity, fix that cell's sink at
    # its available volume. Removing the excess sink increases the remaining
    # mobile solution, so a capped cell stays capped in subsequent solves.
    for _ in range(100):
        result = spsolve(offdiag + sparse.diags(diagonal + dt * k_eff), rhs-fixed)
        if not np.isfinite(result).all() or np.min(result) < -1e-8:
            raise RuntimeError('implicit marine solve failed')
        result = np.maximum(result, 0.)
        deposit = fixed + dt * k_eff * result
        excess = deposit > cap + np.maximum(1e-8, cap * 1e-10)
        if not excess.any():
            break
        fixed[excess] = cap[excess]
        k_eff[excess] = 0.
    else:
        raise RuntimeError('marine accommodation iteration did not converge')
    moved = np.zeros_like(mobile); moved[wet] = result
    settled = np.zeros_like(mobile); settled[wet] = deposit
    exported = np.zeros_like(mobile); exported[wet] = dt * boundary * result
    return moved, settled, exported


def advance(state, duration_s, config=LongtermConfig(), *, source_rate_m3_s=None,
            bed_ceiling_m=None, allowed_mask=None, wet_mask=None, park_and_release=None, mouth_forcing=None):
    """Advance shared stocks; source rate is an external solid volume flux.

    bed_ceiling_m and allowed_mask constrain new deposits, not flow. The
    optional wet_mask supports explicitly closed laboratory domains; production
    callers normally use connected ocean classification. Time is physical seconds.
    mouth_forcing supplies massless MouthForcing boundaries: their local plume
    velocity and transverse mixing overlay the prescribed background current.
    """
    cfg = config
    if cfg.boundary_transport not in ('exchange_only', 'advective_outflow'):
        raise ValueError('invalid marine boundary transport')
    numbers = [duration_s, cfg.sea_level_m, cfg.velocity_x_m_s, cfg.velocity_z_m_s,
               cfg.diffusivity_m2_s, cfg.settling_velocity_m_s, cfg.minimum_depth_m,
               cfg.boundary_rate_s, cfg.max_step_s, cfg.max_rise_m]
    if (not np.isfinite(numbers).all() or duration_s <= 0 or cfg.max_step_s <= 0
            or cfg.minimum_depth_m <= 0 or cfg.max_rise_m <= 0
            or min(cfg.diffusivity_m2_s, cfg.settling_velocity_m_s, cfg.boundary_rate_s) < 0
            or not isinstance(cfg.source_relocation_cells, int) or cfg.source_relocation_cells < 0):
        raise ValueError('invalid longterm forcing')
    shape = state.base_bed_m.shape
    source = np.broadcast_to(np.asarray(0. if source_rate_m3_s is None else source_rate_m3_s, float), shape)
    ceiling = np.broadcast_to(np.asarray(cfg.sea_level_m if bed_ceiling_m is None else bed_ceiling_m, float), shape)
    allowed = np.broadcast_to(np.asarray(True if allowed_mask is None else allowed_mask, bool), shape) & state.valid_mask
    if not np.isfinite(source).all() or (source < 0).any() or not np.isfinite(ceiling).all():
        raise ValueError('invalid source or ceiling')
    if mouth_forcing is not None:
        mouth_forcing = tuple(mouth_forcing)
        for mouth in mouth_forcing:
            direction = np.asarray(mouth.direction_xz, float)
            position = np.asarray(mouth.position_xz_m, float)
            if (not isinstance(mouth.row, int) or not isinstance(mouth.col, int)
                    or not (0 <= mouth.row < shape[0] and 0 <= mouth.col < shape[1])
                    or not state.valid_mask[mouth.row, mouth.col]
                    or direction.shape != (2,) or not np.isfinite(direction).all() or np.linalg.norm(direction) == 0
                    or position.shape != (2,) or not np.isfinite(position).all()
                    or not np.isfinite([mouth.discharge_m3_s, mouth.width_m, mouth.depth_m]).all()
                    or mouth.discharge_m3_s < 0 or min(mouth.width_m, mouth.depth_m) <= 0):
                raise ValueError('invalid mouth forcing')
    stock = state.bed_solid_m3.copy()
    mobile = state.mobile_solid_m3.copy()
    stranded = np.zeros(shape) if state.stranded_solid_m3 is None else state.stranded_solid_m3.copy()
    area = state.spacing_m**2 * (1. - state.porosity)
    exported = state.exported_solid_m3
    elapsed = 0.
    steps = 0
    while elapsed < duration_s:
        current = replace(state, bed_solid_m3=stock)
        wet = classify_ocean(current, cfg.sea_level_m)[0] if wet_mask is None else (
            np.asarray(wet_mask, bool) & state.valid_mask & (current.bed_m < cfg.sea_level_m))
        (_park_and_release if park_and_release is None else park_and_release)(mobile, stranded, wet)
        # A fixed interval release can outlive its wet cell. Remap locally
        # through original ocean cells, never across original land. Unreachable
        # releases remain explicitly stranded instead of disappearing.
        target_row, target_col = _nearby_receivers(wet, allowed, cfg.source_relocation_cells)
        relocate = (~wet) & (target_row >= 0) & (stranded > 0)
        np.add.at(mobile, (target_row[relocate], target_col[relocate]), stranded[relocate])
        stranded[relocate] = 0.
        step_source = np.where(wet, source, 0.)
        dry_source = np.zeros(shape)
        dry = (source > 0) & ~wet
        relocated = dry & (target_row >= 0)
        np.add.at(step_source, (target_row[relocated], target_col[relocated]), source[relocated])
        dry_source[dry & ~relocated] = source[dry & ~relocated]
        depth = np.maximum(cfg.sea_level_m-current.bed_m, 0.)
        capacity = np.maximum(ceiling-current.bed_m, 0.) * area * allowed
        velocity = mixing = None
        if mouth_forcing:
            sources = [(m.position_xz_m[0], m.position_xz_m[1], m.direction_xz,
                        m.discharge_m3_s, m.width_m, m.depth_m) for m in mouth_forcing
                       if m.discharge_m3_s > 0 and _wet_receiver(wet, m.row, m.col, m.direction_xz) is not None]
            px, pz, mx, mz = _plume_field(state, wet, sources)
            velocity = (px + cfg.velocity_x_m_s, pz + cfg.velocity_z_m_s)
            mixing = (mx, mz)
        dt = min(cfg.max_step_s, duration_s-elapsed)
        while True:
            moved, deposited, out = _solve(mobile, step_source, wet, depth, state.ocean_seed_mask,
                                           state.spacing_m, dt, capacity, cfg, velocity, mixing)
            if np.max(deposited / area) <= cfg.max_rise_m * (1 + 1e-9):
                break
            dt *= .5
            if dt <= duration_s * 1e-14:
                raise RuntimeError('morphological step underflow')
        stock += deposited
        mobile = moved
        stranded += dry_source * dt
        exported += float(out.sum())
        elapsed += dt
        steps += 1
    final = replace(state, bed_solid_m3=stock, mobile_solid_m3=mobile,
                    stranded_solid_m3=stranded, exported_solid_m3=exported,
                    time_s=state.time_s+duration_s)
    return final, {'physical_duration_s': duration_s, 'morphological_steps': steps,
                   'boundary_transport': cfg.boundary_transport,
                   'deposited_solid_m3': float((stock-state.bed_solid_m3).sum()),
                   'exported_solid_m3': exported-state.exported_solid_m3}
