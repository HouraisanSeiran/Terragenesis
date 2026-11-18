"""Consolidated shallow_water implementations; numeric expressions preserved."""
from __future__ import annotations
import math as _i68_math
import time as _i68_time
import numpy as _i68_np
import numpy as _i73_np
from functools import partial as _i65_partial
import numpy as _i65_np
import math as _i66_math
import time as _i66_time
import numpy as _i66_np
import numpy as _i75_np
import numpy as _i79_np
import math as _i69_math
import time as _i69_time
import numpy as _i69_np
from functools import lru_cache as _i67_lru_cache
from functools import partial as _i67_partial
import math as _i67_math
import numpy as _i67_np
from numba import njit as _i67_njit
import math as _i70_math
import time as _i70_time
import numpy as _i70_np
import numpy as _i77_np
import numpy as _i71_np
import numpy as _i78_np
import numpy as _i72_np
import numpy as _i74_np
import numpy as _i76_np
import numpy as _i80_np
import numpy as _i81_np
from functools import partial as _i83_partial
import numpy as _i83_np
from functools import partial as _i84_partial
import numpy as _i84_np
from functools import partial as _i85_partial
import numpy as _i85_np
from functools import partial as _i86_partial
import numpy as _i86_np
from functools import partial as _i87_partial
import numpy as _i87_np
CATEGORY = 'B'

def advance_no_drag(geometry, *, rhs, model, scope, physical_limitation, initial_depth_m, forcing_interval_s, intervals, forcing_provider, boundary_stage_provider, source_identity, forcing_identity, budget, snapshot_interval_s, interval_observer, momentum_observer, hydraulic_datum_m=None, wave_speed=None, stage_provider=None, face_evaluation_multiplier=1):
    from terrain_pipeline.surface_hydraulics import validate_budget as _x22_validate_budget
    _x22_validate_budget(budget)
    a, meta = (geometry['arrays'], geometry['metadata'])
    bed = a['H2_m']
    initial = _i68_np.asarray(initial_depth_m)
    if initial.dtype != _i68_np.float64 or initial.shape != bed.shape or (not _i68_np.isfinite(initial).all()) or _i68_np.any(initial < 0) or _i68_np.any(initial > budget.max_depth_m):
        raise ValueError('shallow-water initial depth invalid')
    if bed.size > budget.max_cells or intervals + 1 > budget.max_snapshots or intervals * forcing_interval_s > budget.max_duration_s or (snapshot_interval_s != forcing_interval_s):
        raise ValueError('shallow-water domain/time/snapshot budget invalid')
    support_bytes = sum((a[name].nbytes for name in a if 'subcell_' in name or 'segment_' in name))
    segment_work_bytes = 8 * 20 * face_evaluation_multiplier * (len(a['face_left']) + len(a['boundary_cell']))
    estimate = bed.size * 8 * (40 + 10 * (intervals + 1)) + support_bytes + segment_work_bytes
    if estimate > budget.max_bytes:
        raise ValueError('shallow-water saved momentum memory budget exceeded')
    datum = float(bed.min()) if hydraulic_datum_m is None else hydraulic_datum_m
    relative_bed = bed - datum
    state = _i68_np.column_stack((initial.ravel(), _i68_np.zeros((bed.size, 2))))
    spacing, area = (meta['spacing_m'], meta['spacing_m'] ** 2)
    stages = [state.copy()]
    times = [0.0]
    initial_volume = float(initial.sum() * area)
    supplied = imported = exported = 0.0
    ledgers = [[0.0, 0.0, 0.0, initial_volume, 0.0]]
    steps = evaluations = limited = 0
    minimum_dt = _i68_math.inf
    maximum_dt = maximum_speed = 0.0
    started = _i68_time.monotonic()
    last_i = _i68_np.zeros(len(a['face_left']))
    last_b = _i68_np.zeros(len(a['boundary_cell']))
    for interval in range(intervals):
        source = _i68_np.asarray(forcing_provider(interval))
        tailwater = _i68_np.asarray(boundary_stage_provider(interval))
        if source.dtype != _i68_np.float64 or source.shape != bed.shape or (not _i68_np.isfinite(source).all()) or _i68_np.any(source < 0) or (tailwater.dtype != _i68_np.float64) or (tailwater.shape != (len(last_b),)) or (not _i68_np.isfinite(tailwater).all()):
            raise ValueError('shallow-water complete finite forcing/tailwater required')
        source = source.ravel() / area
        tail = tailwater - datum
        start_state = state.copy()
        transfer_i = _i68_np.zeros_like(last_i)
        transfer_b = _i68_np.zeros_like(last_b)
        momentum_transfer_i = _i68_np.zeros((len(last_i), 2))
        momentum_transfer_b = _i68_np.zeros((len(last_b), 2))
        before_i, before_b = (last_i.copy(), last_b.copy())
        bed_impulse = _i68_np.zeros((bed.size, 2))
        drag_impulse = _i68_np.zeros((bed.size, 2))
        supplied_cell = _i68_np.zeros(bed.size)
        current = interval * forcing_interval_s
        end = (interval + 1) * forcing_interval_s
        first = True
        while current < end - 1e-12:
            if steps >= budget.max_substeps or _i68_time.monotonic() - started > budget.max_wall_s:
                raise RuntimeError('shallow-water execution resource budget exceeded')
            velocity = _i68_np.divide(state[:, 1:], state[:, 0, None], out=_i68_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
            speed = float((_i68_np.sum(abs(velocity), axis=1) + 2 * _i68_np.sqrt(budget.gravity_m_s2 * state[:, 0])).max(initial=0))
            if wave_speed is not None:
                speed = max(speed, wave_speed(state, budget.gravity_m_s2))
            external_bed = a['boundary_segment_crest_relative_m'].min(axis=1) if stage_provider is not None else relative_bed.ravel()[a['boundary_cell']]
            external_bed = _i68_np.maximum(external_bed, a['boundary_crest_m'] - datum)
            exterior_stage = _i68_np.where(a['boundary_kind'] == 1, external_bed, tail)
            external_depth = _i68_np.maximum(exterior_stage - external_bed, 0.0)
            speed = max(speed, float(2 * _i68_np.sqrt(budget.gravity_m_s2 * external_depth[a['boundary_kind'] != 0]).max(initial=0)))
            dt = min(budget.max_dt_s, budget.inertial_cfl * spacing / max(speed, 1e-12), end - current)
            rhs1, witness1 = rhs(state, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=dt, boundary_crest=a['boundary_crest_m'] - datum)
            rhs1[:, 0] += source
            trial = state + dt * rhs1
            if _i68_np.any(trial[:, 0] < 0):
                raise RuntimeError('shallow-water first RK positivity refusal')
            rhs2, witness2 = rhs(trial, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=dt, boundary_crest=a['boundary_crest_m'] - datum)
            rhs2[:, 0] += source
            updated = 0.5 * state + 0.5 * (trial + dt * rhs2)
            before_drag = updated[:, 1:].copy()
            wet = updated[:, 0] > 0
            magnitude = _i68_np.linalg.norm(updated[wet, 1:], axis=1)
            depth_power = updated[wet, 0] ** (7 / 3)
            drag_denominator = depth_power + dt * budget.gravity_m_s2 * budget.roughness_s_m_third ** 2 * magnitude
            damping = _i68_np.divide(depth_power, drag_denominator, out=_i68_np.zeros_like(depth_power), where=drag_denominator > 0)
            updated[wet, 1:] *= damping[:, None]
            if not _i68_np.isfinite(updated).all() or _i68_np.any(updated[:, 0] < 0) or _i68_np.any(updated[:, 0] > budget.max_depth_m):
                raise RuntimeError('shallow-water final RK depth refusal; no clipping')
            qi = 0.5 * (witness1['internal_flux'][:, 0] + witness2['internal_flux'][:, 0]) * spacing
            qb = 0.5 * (witness1['boundary_flux'][:, 0] + witness2['boundary_flux'][:, 0]) * spacing
            bed_step = 0.5 * dt * (witness1['bed_source'][:, 1:] + witness2['bed_source'][:, 1:])
            if first:
                momentum_observer(dict(interval=interval, time_start_s=current, dt_s=dt, state_before=state.copy(), state_predictor=trial.copy(), state_after=updated.copy(), forcing_m3_s=source * area, tailwater_m=tailwater.copy(), rk1_internal_flux=witness1['internal_flux'], rk2_internal_flux=witness2['internal_flux'], rk1_boundary_flux=witness1['boundary_flux'], rk2_boundary_flux=witness2['boundary_flux'], rk1_bed_source=witness1['bed_source'], rk2_bed_source=witness2['bed_source'], manning_momentum_change=updated[:, 1:] - before_drag))
                first = False
            transfer_i += dt * qi
            transfer_b += dt * qb
            momentum_transfer_i += 0.5 * dt * spacing * (witness1['internal_flux'][:, 1:] + witness2['internal_flux'][:, 1:])
            momentum_transfer_b += 0.5 * dt * spacing * (witness1['boundary_flux'][:, 1:] + witness2['boundary_flux'][:, 1:])
            bed_impulse += bed_step
            drag_impulse += updated[:, 1:] - before_drag
            supplied_cell += dt * source * area
            supplied += float(dt * source.sum() * area)
            imported += float(dt * _i68_np.maximum(-qb, 0).sum())
            exported += float(dt * _i68_np.maximum(qb, 0).sum())
            limited += witness1['limited_donors'] + witness2['limited_donors']
            state = updated
            current += dt
            steps += 1
            evaluations += 2 * face_evaluation_multiplier * (len(qi) + len(qb))
            if evaluations > budget.max_face_evaluations:
                raise RuntimeError('shallow-water face work budget exceeded')
            minimum_dt = min(minimum_dt, dt)
            maximum_dt = max(maximum_dt, dt)
            maximum_speed = max(maximum_speed, speed)
        _, endpoint = rhs(state, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=0.0, boundary_crest=a['boundary_crest_m'] - datum)
        evaluations += face_evaluation_multiplier * (len(last_i) + len(last_b))
        if evaluations > budget.max_face_evaluations:
            raise RuntimeError('shallow-water endpoint face work budget exceeded')
        last_i = endpoint['internal_flux'][:, 0] * spacing
        last_b = endpoint['boundary_flux'][:, 0] * spacing
        interval_observer(dict(interval=interval, time_start_s=interval * forcing_interval_s, time_end_s=end, depth_before_m=start_state[:, 0], depth_after_m=state[:, 0].copy(), momentum_before=start_state[:, 1:], momentum_after=state[:, 1:].copy(), internal_transfer_m3=transfer_i, boundary_transfer_m3=transfer_b, forcing_volume_m3=supplied_cell, internal_momentum_transfer=momentum_transfer_i, boundary_momentum_transfer=momentum_transfer_b, bed_momentum_change=bed_impulse, manning_momentum_change=drag_impulse, internal_q_before_m3_s=before_i, internal_q_after_m3_s=last_i.copy(), boundary_q_before_m3_s=before_b, boundary_q_after_m3_s=last_b.copy()))
        stages.append(state.copy())
        times.append(end)
        volume = float(state[:, 0].sum() * area)
        ledgers.append([supplied, imported, exported, volume, volume - initial_volume - supplied - imported + exported])
    saved = _i68_np.asarray(stages)
    result = dict(arrays=dict(time_s=_i68_np.asarray(times), depth_m=saved[:, :, 0].reshape(-1, *bed.shape), momentum_x_m2_s=saved[:, :, 1].reshape(-1, *bed.shape), momentum_z_m2_s=saved[:, :, 2].reshape(-1, *bed.shape), initial_depth_m=initial.copy(), ledger=_i68_np.asarray(ledgers), final_internal_q_m3_s=last_i, final_boundary_q_m3_s=last_b), metadata=dict(schema=model, hydraulic_model=model, status='completed', failure=None, budget=vars(budget), source_identity=source_identity, forcing_identity=forcing_identity, requested_time_s=intervals * forcing_interval_s, committed_time_s=intervals * forcing_interval_s, substeps=steps, face_evaluations=evaluations, wall_s=_i68_time.monotonic() - started, initial_volume_m3=initial_volume, final_volume_m3=float(state[:, 0].sum() * area), supplied_m3=supplied, boundary_input_m3=imported, boundary_output_m3=exported, estimated_peak_bytes=estimate, scope=scope), diagnostics=dict(minimum_dt_s=minimum_dt, maximum_dt_s=maximum_dt, maximum_wave_speed_m_s=maximum_speed, limited_donor_count=limited, negative_water_clip_count=0, physical_limitation=physical_limitation))
    if stage_provider is not None:
        result['arrays']['stage_relative_m'] = _i68_np.asarray([stage_provider(item[:, 0]) for item in saved]).reshape(-1, *bed.shape)
    return result
HYDROSTATIC_HLL_MODEL = 'single-domain-hydrostatic-HLL-SSPRK2-v1'

def minmod(first, second):
    return _i73_np.where(first * second > 0, _i73_np.sign(first) * _i73_np.minimum(abs(first), abs(second)), 0.0)

def hydrostatic_hll(left, right, bed_left, bed_right, *, gravity, axis):
    """Audusse hydrostatic reconstruction; side-specific pressure corrections.

    States are [h,hu,hv] and fluxes remain global [mass,xmomentum,zmomentum].
    This first-order source-balanced reference deliberately avoids unbalanced
    MUSCL bed terms. Higher spatial order requires a separate algorithm version.
    """
    hleft, hright = (left[:, 0], right[:, 0])
    crest = _i73_np.maximum(bed_left, bed_right)
    hl = _i73_np.maximum(hleft + bed_left - crest, 0.0)
    hr = _i73_np.maximum(hright + bed_right - crest, 0.0)
    vl = _i73_np.divide(left[:, 1:], hleft[:, None], out=_i73_np.zeros_like(left[:, 1:]), where=hleft[:, None] > 0)
    vr = _i73_np.divide(right[:, 1:], hright[:, None], out=_i73_np.zeros_like(right[:, 1:]), where=hright[:, None] > 0)
    reconstructed_left = _i73_np.column_stack((hl, hl[:, None] * vl))
    reconstructed_right = _i73_np.column_stack((hr, hr[:, None] * vr))
    ul, ur = (vl[:, axis], vr[:, axis])
    cl, cr = (_i73_np.sqrt(gravity * hl), _i73_np.sqrt(gravity * hr))
    sl = _i73_np.minimum(ul - cl, ur - cr)
    sr = _i73_np.maximum(ul + cl, ur + cr)
    fl = reconstructed_left * ul[:, None]
    fr = reconstructed_right * ur[:, None]
    fl[:, axis + 1] += 0.5 * gravity * hl ** 2
    fr[:, axis + 1] += 0.5 * gravity * hr ** 2
    denominator = sr - sl
    flux = _i73_np.divide(sr[:, None] * fl - sl[:, None] * fr + (sl * sr)[:, None] * (reconstructed_right - reconstructed_left), denominator[:, None], out=_i73_np.zeros_like(fl), where=denominator[:, None] > 0)
    flux[sl >= 0] = fl[sl >= 0]
    flux[sr <= 0] = fr[sr <= 0]
    correction_left = 0.5 * gravity * (hleft ** 2 - hl ** 2)
    correction_right = 0.5 * gravity * (hright ** 2 - hr ** 2)
    return (flux, correction_left, correction_right, _i73_np.maximum(abs(sl), abs(sr)))

def shallow_water_rhs_flat(state, bed, *, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
    """Global conservative face flux, well-balanced source, and donor limiter."""
    rows, columns = bed.shape
    count = rows * columns
    grid = _i73_np.arange(count).reshape(rows, columns)
    left = _i73_np.r_[grid[:, :-1].ravel(), grid[:-1, :].ravel()]
    right = _i73_np.r_[grid[:, 1:].ravel(), grid[1:, :].ravel()]
    axis = _i73_np.r_[_i73_np.zeros(rows * (columns - 1), _i73_np.int64), _i73_np.ones((rows - 1) * columns, _i73_np.int64)]
    exterior = _i73_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    normal_axis = _i73_np.r_[_i73_np.zeros(2 * rows, _i73_np.int64), _i73_np.ones(2 * columns, _i73_np.int64)]
    sign = _i73_np.r_[-_i73_np.ones(rows), _i73_np.ones(rows), -_i73_np.ones(columns), _i73_np.ones(columns)]
    flatbed = bed.ravel()
    flux = _i73_np.zeros((len(left), 3))
    correction_l, correction_r = (_i73_np.zeros(len(left)), _i73_np.zeros(len(left)))
    waves = _i73_np.zeros(len(left))
    for direction in (0, 1):
        selection = axis == direction
        f, cl, cr, speed = hydrostatic_hll(state[left[selection]], state[right[selection]], flatbed[left[selection]], flatbed[right[selection]], gravity=gravity, axis=direction)
        flux[selection], correction_l[selection], correction_r[selection], waves[selection] = (f, cl, cr, speed)
    ghost = state[exterior].copy()
    boundary_bed = flatbed[exterior].copy()
    if boundary_crest is not None:
        boundary_bed = _i73_np.maximum(boundary_bed, boundary_crest)
    for direction in (0, 1):
        selected = normal_axis == direction
        closed = selected & (boundary_kind == 0)
        ghost[closed, direction + 1] *= -1
    opened = boundary_kind != 0
    exterior_stage = _i73_np.where(boundary_kind == 1, boundary_bed, tailwater)
    ghost[opened, 0] = _i73_np.maximum(exterior_stage[opened] - boundary_bed[opened], 0.0)
    ghost[opened, 1:] = 0.0
    boundary_flux = _i73_np.zeros_like(ghost)
    boundary_pressure = _i73_np.zeros((len(exterior), 3))
    for direction in (0, 1):
        selection = normal_axis == direction
        cells = exterior[selection]
        first = state[cells].copy()
        second = ghost[selection].copy()
        signs = sign[selection]
        first[:, direction + 1] *= signs
        second[:, direction + 1] *= signs
        f, cl, _, speed = hydrostatic_hll(first, second, flatbed[cells], boundary_bed[selection], gravity=gravity, axis=direction)
        f[:, direction + 1] *= signs
        boundary_pressure[selection, direction + 1] = -cl * signs / spacing
        boundary_flux[selection] = f
        waves = _i73_np.r_[waves, speed]
    outgoing = _i73_np.bincount(left, weights=_i73_np.maximum(flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i73_np.bincount(right, weights=_i73_np.maximum(-flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i73_np.bincount(exterior, weights=_i73_np.maximum(boundary_flux[:, 0], 0) * spacing, minlength=count)
    scales = _i73_np.ones(count)
    limited = outgoing * dt > state[:, 0] * spacing ** 2
    scales[limited] = state[limited, 0] * spacing ** 2 / (dt * outgoing[limited]) * (1 - 1e-12)
    face_scale = _i73_np.where(flux[:, 0] >= 0, scales[left], scales[right])
    boundary_scale = _i73_np.where(boundary_flux[:, 0] >= 0, scales[exterior], 1.0)
    flux *= face_scale[:, None]
    boundary_flux *= boundary_scale[:, None]
    rhs = _i73_np.zeros_like(state)
    for component in range(3):
        _i73_np.add.at(rhs[:, component], left, -flux[:, component] / spacing)
        _i73_np.add.at(rhs[:, component], right, flux[:, component] / spacing)
        _i73_np.add.at(rhs[:, component], exterior, -boundary_flux[:, component] / spacing)
    pressure = _i73_np.zeros_like(state)
    _i73_np.add.at(pressure, (left, axis + 1), -correction_l / spacing)
    _i73_np.add.at(pressure, (right, axis + 1), correction_r / spacing)
    for component in (1, 2):
        _i73_np.add.at(pressure[:, component], exterior, boundary_pressure[:, component])
    rhs += pressure
    return (rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure, maximum_wave_speed=float(waves.max(initial=0)), minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum())))

def reconstruct_independent(stage, velocity, depth, bed, support, boundary_kind, tailwater):
    rows, columns = bed.shape
    fields = _i65_np.column_stack((stage, velocity)).reshape(rows, columns, 3)
    sx, sz = (_i65_np.zeros_like(fields), _i65_np.zeros_like(fields))
    sx[:, 1:-1] = minmod(fields[:, 1:-1] - fields[:, :-2], fields[:, 2:] - fields[:, 1:-1])
    sz[1:-1] = minmod(fields[1:-1] - fields[:-2], fields[2:] - fields[1:-1])
    for axis, side, begin, end in ((0, 0, 0, rows), (0, 1, rows, 2 * rows), (1, 0, 2 * rows, 2 * rows + columns), (1, 1, 2 * rows + columns, 2 * (rows + columns))):
        opened = boundary_kind[begin:end] == 2
        exterior = _i65_np.zeros((end - begin, 3))
        exterior[:, 0] = tailwater[begin:end]
        if axis == 0:
            if columns < 2:
                continue
            edge = fields[:, 0] if side == 0 else fields[:, -1]
            interior = fields[:, 1] - edge if side == 0 else edge - fields[:, -2]
            external = 2 * (edge - exterior) if side == 0 else 2 * (exterior - edge)
            sx[:, 0 if side == 0 else -1][opened] = minmod(interior, external)[opened]
        else:
            if rows < 2:
                continue
            edge = fields[0] if side == 0 else fields[-1]
            interior = fields[1] - edge if side == 0 else edge - fields[-2]
            external = 2 * (edge - exterior) if side == 0 else 2 * (exterior - edge)
            sz[0 if side == 0 else -1][opened] = minmod(interior, external)[opened]
    dry = depth.reshape(rows, columns) == 0
    sx[dry], sz[dry] = (0.0, 0.0)
    available = (stage - support['subcell_bed_relative_m'][:, 0]).reshape(rows, columns)
    for slope in (sx, sz):
        ratio = _i65_np.minimum(1.0, _i65_np.divide(2 * available, abs(slope[:, :, 0]), out=_i65_np.ones_like(available), where=slope[:, :, 0] != 0))
        slope *= ratio[:, :, None]
    return [(fields - 0.5 * sx).reshape(-1, 3), (fields + 0.5 * sx).reshape(-1, 3), (fields - 0.5 * sz).reshape(-1, 3), (fields + 0.5 * sz).reshape(-1, 3)]

def reconstruct_dry_neighbor(stage, velocity, depth, bed, support, boundary_kind, tailwater):
    rows, columns = bed.shape
    fields = _i65_np.column_stack((stage, velocity)).reshape(rows, columns, 3)
    sx, sz = (_i65_np.zeros_like(fields), _i65_np.zeros_like(fields))
    sx[:, 1:-1] = minmod(fields[:, 1:-1] - fields[:, :-2], fields[:, 2:] - fields[:, 1:-1])
    sz[1:-1] = minmod(fields[1:-1] - fields[:-2], fields[2:] - fields[1:-1])
    depth_grid = depth.reshape(rows, columns)
    for axis, side, begin, end in ((0, 0, 0, rows), (0, 1, rows, 2 * rows), (1, 0, 2 * rows, 2 * rows + columns), (1, 1, 2 * rows + columns, 2 * (rows + columns))):
        opened = boundary_kind[begin:end] == 2
        exterior = _i65_np.zeros((end - begin, 3))
        exterior[:, 0] = tailwater[begin:end]
        if axis == 0:
            if columns < 2:
                continue
            edge = fields[:, 0] if side == 0 else fields[:, -1]
            interior = fields[:, 1] - edge if side == 0 else edge - fields[:, -2]
            external = 2 * (edge - exterior) if side == 0 else 2 * (exterior - edge)
            dry_neighbor = depth_grid[:, 1 if side == 0 else -2] == 0
            interior[dry_neighbor, 0] = external[dry_neighbor, 0]
            sx[:, 0 if side == 0 else -1][opened] = minmod(interior, external)[opened]
        else:
            if rows < 2:
                continue
            edge = fields[0] if side == 0 else fields[-1]
            interior = fields[1] - edge if side == 0 else edge - fields[-2]
            external = 2 * (edge - exterior) if side == 0 else 2 * (exterior - edge)
            dry_neighbor = depth_grid[1 if side == 0 else -2] == 0
            interior[dry_neighbor, 0] = external[dry_neighbor, 0]
            sz[0 if side == 0 else -1][opened] = minmod(interior, external)[opened]
    dry = depth.reshape(rows, columns) == 0
    sx[dry], sz[dry] = (0.0, 0.0)
    available = (stage - support['subcell_bed_relative_m'][:, 0]).reshape(rows, columns)
    for slope in (sx, sz):
        ratio = _i65_np.minimum(1.0, _i65_np.divide(2 * available, abs(slope[:, :, 0]), out=_i65_np.ones_like(available), where=slope[:, :, 0] != 0))
        slope *= ratio[:, :, None]
    return [(fields - 0.5 * sx).reshape(-1, 3), (fields + 0.5 * sx).reshape(-1, 3), (fields - 0.5 * sz).reshape(-1, 3), (fields + 0.5 * sz).reshape(-1, 3)]

def make_segmented_rhs(_reconstruct):
    """shallow_water_rhs of support_v5/_v6 for the injected face reconstruction."""
    from terrain_pipeline.fine_subgrid import storage_stages as _x20_storage_stages

    def shallow_water_rhs(state, bed, *, support, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
        rows, columns = bed.shape
        count = bed.size
        grid = _i65_np.arange(count).reshape(rows, columns)
        left = _i65_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
        right = _i65_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
        axes = _i65_np.r_[_i65_np.zeros(rows * (columns - 1), _i65_np.int64), _i65_np.ones((rows - 1) * columns, _i65_np.int64)]
        cells = _i65_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
        boundary_axes = _i65_np.r_[_i65_np.zeros(2 * rows, _i65_np.int64), _i65_np.ones(2 * columns, _i65_np.int64)]
        signs = _i65_np.r_[-_i65_np.ones(rows), _i65_np.ones(rows), -_i65_np.ones(columns), _i65_np.ones(columns)]
        stage = _x20_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
        velocity = _i65_np.divide(state[:, 1:], state[:, 0, None], out=_i65_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
        faces = _reconstruct(stage, velocity, state[:, 0], bed, support, boundary_kind, tailwater)
        crests = support['face_segment_crest_relative_m']
        boundary_crests = support['boundary_segment_crest_relative_m'].copy()
        if boundary_crest is not None:
            opened = boundary_kind != 0
            boundary_crests[opened] = _i65_np.maximum(boundary_crests[opened], boundary_crest[opened, None])
        segments = crests.shape[1]
        flux = _i65_np.zeros((len(left), 3))
        boundary_flux = _i65_np.zeros((len(cells), 3))
        pressure_left, pressure_right = (_i65_np.zeros(len(left)), _i65_np.zeros(len(left)))
        pressure_boundary = _i65_np.zeros(len(cells))
        maximum_speed = 0.0
        for axis in (0, 1):
            mask = axes == axis
            crest = crests[mask].ravel()
            reconstructed_left = faces[1 if axis == 0 else 3][left[mask]]
            reconstructed_right = faces[0 if axis == 0 else 2][right[mask]]
            hl = _i65_np.maximum(reconstructed_left[:, 0, None] - crests[mask], 0.0)
            hr = _i65_np.maximum(reconstructed_right[:, 0, None] - crests[mask], 0.0)
            ul = _i65_np.repeat(reconstructed_left[:, 1:], segments, axis=0)
            ur = _i65_np.repeat(reconstructed_right[:, 1:], segments, axis=0)
            ls = _i65_np.column_stack((hl.ravel(), hl.ravel()[:, None] * ul))
            rs = _i65_np.column_stack((hr.ravel(), hr.ravel()[:, None] * ur))
            f, _, _, speed = hydrostatic_hll(ls, rs, crest, crest, gravity=gravity, axis=axis)
            flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
            pressure_left[mask] = 0.5 * gravity * _i65_np.mean(_i65_np.maximum(stage[left[mask], None] - crests[mask], 0.0) ** 2, axis=1)
            pressure_right[mask] = 0.5 * gravity * _i65_np.mean(_i65_np.maximum(stage[right[mask], None] - crests[mask], 0.0) ** 2, axis=1)
            maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
            mask = boundary_axes == axis
            crest = boundary_crests[mask]
            boundary_state = _i65_np.empty((mask.sum(), 3))
            negative = signs[mask] < 0
            boundary_state[negative] = faces[0 if axis == 0 else 2][cells[mask][negative]]
            boundary_state[~negative] = faces[1 if axis == 0 else 3][cells[mask][~negative]]
            h = _i65_np.maximum(boundary_state[:, 0, None] - crest, 0.0)
            u = _i65_np.repeat(boundary_state[:, 1:], segments, axis=0)
            sign = _i65_np.repeat(signs[mask], segments)
            first = _i65_np.column_stack((h.ravel(), h.ravel()[:, None] * u))
            ghost = first.copy()
            ghost[:, axis + 1] *= -1
            opened = _i65_np.repeat(boundary_kind[mask] != 0, segments)
            exterior_stage = _i65_np.where(boundary_kind[mask, None] == 1, crest, tailwater[mask, None])
            ghost[opened, 0] = _i65_np.maximum(exterior_stage - crest, 0.0).ravel()[opened]
            ghost[opened, 1:] = 0.0
            first[:, axis + 1] *= sign
            ghost[:, axis + 1] *= sign
            f, _, _, speed = hydrostatic_hll(first, ghost, crest.ravel(), crest.ravel(), gravity=gravity, axis=axis)
            f[:, axis + 1] *= sign
            boundary_flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
            pressure_boundary[mask] = 0.5 * gravity * _i65_np.mean(_i65_np.maximum(stage[cells[mask], None] - crest, 0.0) ** 2, axis=1)
            maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
        outgoing = _i65_np.bincount(left, weights=_i65_np.maximum(flux[:, 0], 0) * spacing, minlength=count)
        outgoing += _i65_np.bincount(right, weights=_i65_np.maximum(-flux[:, 0], 0) * spacing, minlength=count)
        outgoing += _i65_np.bincount(cells, weights=_i65_np.maximum(boundary_flux[:, 0], 0) * spacing, minlength=count)
        scales = _i65_np.ones(count)
        limited = outgoing * dt > state[:, 0] * spacing ** 2
        scales[limited] = state[limited, 0] * spacing ** 2 / (outgoing[limited] * dt) * (1 - 1e-12)
        flux *= _i65_np.where(flux[:, 0] >= 0, scales[left], scales[right])[:, None]
        boundary_flux *= _i65_np.where(boundary_flux[:, 0] >= 0, scales[cells], 1.0)[:, None]
        rhs = _i65_np.zeros_like(state)
        for component in range(3):
            _i65_np.add.at(rhs[:, component], left, -flux[:, component] / spacing)
            _i65_np.add.at(rhs[:, component], right, flux[:, component] / spacing)
            _i65_np.add.at(rhs[:, component], cells, -boundary_flux[:, component] / spacing)
        pressure = _i65_np.zeros_like(state)
        _i65_np.add.at(pressure, (left, axes + 1), pressure_left / spacing)
        _i65_np.add.at(pressure, (right, axes + 1), -pressure_right / spacing)
        _i65_np.add.at(pressure, (cells, boundary_axes + 1), signs * pressure_boundary / spacing)
        rhs += pressure
        return (rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure, maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum())))
    return shallow_water_rhs

def prepare_support(bed):
    from terrain_pipeline.fine_subgrid import prepare_subgrid_support as _x19_prepare_subgrid_support
    support, datum = _x19_prepare_subgrid_support(bed)
    canonical = bed['arrays']['canonical_bed_center_m'] - datum
    rows, columns = bed['arrays']['H2_m'].shape
    factor = int(bed['metadata']['spacing_m'])
    support['subcell_bed_position_relative_m'] = canonical.reshape(rows, factor, columns, factor).transpose(0, 2, 1, 3).reshape(rows * columns, factor, factor)
    return (support, datum)

def face_fields(reconstruction, cells, axis, sign, factor):
    coordinate = (_i65_np.arange(factor) + 0.5) / factor - 0.5
    normal = reconstruction['slope_x' if axis == 0 else 'slope_z'][cells]
    tangent = reconstruction['slope_z' if axis == 0 else 'slope_x'][cells]
    return reconstruction['center'][cells, None, :] + sign * 0.5 * normal[:, None, :] + coordinate[None, :, None] * tangent[:, None, :]

def internal_bed_pressure(reconstruction, support, *, spacing, gravity):
    bed = support['subcell_bed_position_relative_m']
    factor = bed.shape[1]
    coordinate = (_i65_np.arange(factor) + 0.5) / factor - 0.5
    interfaces = (_i65_np.arange(factor - 1) + 1) / factor - 0.5
    eta0 = reconstruction['center'][:, 0, None, None]
    sx = reconstruction['slope_x'][:, 0, None, None]
    sz = reconstruction['slope_z'][:, 0, None, None]
    eta_x = eta0 + sx * interfaces[None, None, :] + sz * coordinate[None, :, None]
    eta_z = eta0 + sx * coordinate[None, None, :] + sz * interfaces[None, :, None]
    delta_x = _i65_np.maximum(eta_x - bed[:, :, 1:], 0.0) ** 2 - _i65_np.maximum(eta_x - bed[:, :, :-1], 0.0) ** 2
    delta_z = _i65_np.maximum(eta_z - bed[:, 1:, :], 0.0) ** 2 - _i65_np.maximum(eta_z - bed[:, :-1, :], 0.0) ** 2
    return 0.5 * gravity * _i65_np.column_stack((delta_x.sum(axis=(1, 2)), delta_z.sum(axis=(1, 2)))) / (spacing * factor)

def make_reconstruct(_reconstruct):
    """reconstruct of reconstruction_v8/_v9 for the injected face reconstruction."""
    from terrain_pipeline.fine_subgrid import storage_stages as _x20_storage_stages

    def reconstruct(state, bed, support, boundary_kind, tailwater):
        stage = _x20_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
        velocity = _i65_np.divide(state[:, 1:], state[:, 0, None], out=_i65_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
        faces = _reconstruct(stage, velocity, state[:, 0], bed, support, boundary_kind, tailwater)
        slope_x, slope_z = (faces[1] - faces[0], faces[3] - faces[2])
        factor = support['subcell_bed_position_relative_m'].shape[1]
        coordinate = (_i65_np.arange(factor) + 0.5) / factor - 0.5
        x, z = _i65_np.meshgrid(coordinate, coordinate)
        eta_offset = slope_x[:, 0, None, None] * x + slope_z[:, 0, None, None] * z
        effective_bed = support['subcell_bed_position_relative_m'] - eta_offset
        sorted_effective_bed = _i65_np.sort(effective_bed.reshape(len(state), -1), axis=1)
        eta0 = _x20_storage_stages(state[:, 0], sorted_effective_bed, _i65_np.cumsum(sorted_effective_bed, axis=1))
        subdepth = _i65_np.maximum(eta0[:, None, None] - effective_bed, 0.0)
        velocity_offset = slope_x[:, None, None, 1:] * x[None, :, :, None] + slope_z[:, None, None, 1:] * z[None, :, :, None]
        offset_momentum = _i65_np.mean(subdepth[:, :, :, None] * velocity_offset, axis=(1, 2))
        center_velocity = _i65_np.divide(state[:, 1:] - offset_momentum, state[:, 0, None], out=_i65_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
        return dict(center=_i65_np.column_stack((eta0, center_velocity)), slope_x=slope_x, slope_z=slope_z, subcell_depth=subdepth, subcell_velocity=center_velocity[:, None, None, :] + velocity_offset)
    return reconstruct

def make_linear_stage_rhs(reconstruct, face_fields, internal_bed_pressure):
    """shallow_water_rhs of support_v8/_v9 for the injected reconstruction functions."""

    def shallow_water_rhs(state, bed, *, support, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
        rows, columns = bed.shape
        count = bed.size
        grid = _i65_np.arange(count).reshape(rows, columns)
        left = _i65_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
        right = _i65_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
        axes = _i65_np.r_[_i65_np.zeros(rows * (columns - 1), _i65_np.int64), _i65_np.ones((rows - 1) * columns, _i65_np.int64)]
        cells = _i65_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
        boundary_axes = _i65_np.r_[_i65_np.zeros(2 * rows, _i65_np.int64), _i65_np.ones(2 * columns, _i65_np.int64)]
        signs = _i65_np.r_[-_i65_np.ones(rows), _i65_np.ones(rows), -_i65_np.ones(columns), _i65_np.ones(columns)]
        reconstruction = reconstruct(state, bed, support, boundary_kind, tailwater)
        position_bed = support['subcell_bed_position_relative_m']
        crests = support['face_segment_crest_relative_m']
        boundary_crests = support['boundary_segment_crest_relative_m'].copy()
        if boundary_crest is not None:
            opened = boundary_kind != 0
            boundary_crests[opened] = _i65_np.maximum(boundary_crests[opened], boundary_crest[opened, None])
        segments = crests.shape[1]
        flux = _i65_np.zeros((len(left), 3))
        boundary_flux = _i65_np.zeros((len(cells), 3))
        pressure_left, pressure_right = (_i65_np.zeros(len(left)), _i65_np.zeros(len(left)))
        pressure_boundary = _i65_np.zeros(len(cells))
        maximum_speed = 0.0
        for axis in (0, 1):
            mask = axes == axis
            crest = crests[mask].ravel()
            first_fields = face_fields(reconstruction, left[mask], axis, 1.0, segments)
            second_fields = face_fields(reconstruction, right[mask], axis, -1.0, segments)
            hl = _i65_np.maximum(first_fields[:, :, 0] - crests[mask], 0.0)
            hr = _i65_np.maximum(second_fields[:, :, 0] - crests[mask], 0.0)
            ul = first_fields[:, :, 1:].reshape(-1, 2)
            ur = second_fields[:, :, 1:].reshape(-1, 2)
            ls = _i65_np.column_stack((hl.ravel(), hl.ravel()[:, None] * ul))
            rs = _i65_np.column_stack((hr.ravel(), hr.ravel()[:, None] * ur))
            f, _, _, speed = hydrostatic_hll(ls, rs, crest, crest, gravity=gravity, axis=axis)
            flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
            own_left_bed = position_bed[left[mask], :, -1] if axis == 0 else position_bed[left[mask], -1, :]
            own_right_bed = position_bed[right[mask], :, 0] if axis == 0 else position_bed[right[mask], 0, :]
            pressure_left[mask] = 0.5 * gravity * _i65_np.mean(hl ** 2 - _i65_np.maximum(first_fields[:, :, 0] - own_left_bed, 0.0) ** 2, axis=1)
            pressure_right[mask] = 0.5 * gravity * _i65_np.mean(hr ** 2 - _i65_np.maximum(second_fields[:, :, 0] - own_right_bed, 0.0) ** 2, axis=1)
            maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
            mask = boundary_axes == axis
            crest = boundary_crests[mask]
            fields = _i65_np.empty((mask.sum(), segments, 3))
            negative = signs[mask] < 0
            fields[negative] = face_fields(reconstruction, cells[mask][negative], axis, -1.0, segments)
            fields[~negative] = face_fields(reconstruction, cells[mask][~negative], axis, 1.0, segments)
            h = _i65_np.maximum(fields[:, :, 0] - crest, 0.0)
            u = fields[:, :, 1:].reshape(-1, 2)
            sign = _i65_np.repeat(signs[mask], segments)
            first = _i65_np.column_stack((h.ravel(), h.ravel()[:, None] * u))
            ghost = first.copy()
            ghost[:, axis + 1] *= -1
            opened = _i65_np.repeat(boundary_kind[mask] != 0, segments)
            exterior_stage = _i65_np.where(boundary_kind[mask, None] == 1, crest, tailwater[mask, None])
            ghost[opened, 0] = _i65_np.maximum(exterior_stage - crest, 0.0).ravel()[opened]
            ghost[opened, 1:] = 0.0
            first[:, axis + 1] *= sign
            ghost[:, axis + 1] *= sign
            f, _, _, speed = hydrostatic_hll(first, ghost, crest.ravel(), crest.ravel(), gravity=gravity, axis=axis)
            f[:, axis + 1] *= sign
            boundary_flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
            own_bed = _i65_np.empty_like(crest)
            if axis == 0:
                own_bed[negative] = position_bed[cells[mask][negative], :, 0]
                own_bed[~negative] = position_bed[cells[mask][~negative], :, -1]
            else:
                own_bed[negative] = position_bed[cells[mask][negative], 0, :]
                own_bed[~negative] = position_bed[cells[mask][~negative], -1, :]
            pressure_boundary[mask] = 0.5 * gravity * _i65_np.mean(h ** 2 - _i65_np.maximum(fields[:, :, 0] - own_bed, 0.0) ** 2, axis=1)
            maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
        outgoing = _i65_np.bincount(left, weights=_i65_np.maximum(flux[:, 0], 0) * spacing, minlength=count)
        outgoing += _i65_np.bincount(right, weights=_i65_np.maximum(-flux[:, 0], 0) * spacing, minlength=count)
        outgoing += _i65_np.bincount(cells, weights=_i65_np.maximum(boundary_flux[:, 0], 0) * spacing, minlength=count)
        scales = _i65_np.ones(count)
        limited = outgoing * dt > state[:, 0] * spacing ** 2
        scales[limited] = state[limited, 0] * spacing ** 2 / (outgoing[limited] * dt) * (1 - 1e-12)
        flux *= _i65_np.where(flux[:, 0] >= 0, scales[left], scales[right])[:, None]
        boundary_flux *= _i65_np.where(boundary_flux[:, 0] >= 0, scales[cells], 1.0)[:, None]
        rhs = _i65_np.zeros_like(state)
        for component in range(3):
            _i65_np.add.at(rhs[:, component], left, -flux[:, component] / spacing)
            _i65_np.add.at(rhs[:, component], right, flux[:, component] / spacing)
            _i65_np.add.at(rhs[:, component], cells, -boundary_flux[:, component] / spacing)
        pressure = _i65_np.zeros_like(state)
        pressure[:, 1:] = internal_bed_pressure(reconstruction, support, spacing=spacing, gravity=gravity)
        _i65_np.add.at(pressure, (left, axes + 1), pressure_left / spacing)
        _i65_np.add.at(pressure, (right, axes + 1), -pressure_right / spacing)
        _i65_np.add.at(pressure, (cells, boundary_axes + 1), signs * pressure_boundary / spacing)
        rhs += pressure
        return (rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure, reconstruction_center=reconstruction['center'], reconstruction_slope_x=reconstruction['slope_x'], reconstruction_slope_z=reconstruction['slope_z'], maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum())))
    return shallow_water_rhs

def make_advance_shallow_water(MODEL, shallow_water_rhs):
    """advance_shallow_water of single_domain_shallow_water_v5/_v6 for one support module."""
    from terrain_pipeline.fine_subgrid import storage_stages as _x20_storage_stages

    def advance_shallow_water(geometry, **kwargs):
        arrays = geometry['arrays']
        support = {name: arrays[name] for name in ('subcell_bed_relative_m', 'subcell_prefix_relative_m', 'face_segment_crest_relative_m', 'boundary_segment_crest_relative_m')}

        def wave_speed(state, gravity):
            stage = _x20_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
            maximum_depth = _i65_np.maximum(stage - support['subcell_bed_relative_m'][:, 0], 0.0)
            velocity = _i65_np.divide(state[:, 1:], state[:, 0, None], out=_i65_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
            return float(1.5 * abs(velocity).sum(axis=1).max(initial=0) + 2 * _i65_np.sqrt(gravity * max(float(stage.max() - support['subcell_bed_relative_m'].min()), 0)))
        return advance_no_drag(geometry, rhs=_i65_partial(shallow_water_rhs, support=support), model=MODEL, hydraulic_datum_m=geometry['metadata']['hydraulic_datum_m'], wave_speed=wave_speed, stage_provider=lambda depth: _x20_storage_stages(depth, support['subcell_bed_relative_m'], support['subcell_prefix_relative_m']), face_evaluation_multiplier=support['face_segment_crest_relative_m'].shape[1], scope='independent FV canonical subgrid storage and MUSCL segmented advective HLL; SSPRK2; uncalibrated', physical_limitation='one velocity vector per coarse cell; segmented pressure support; no calibrated natural certification', **kwargs)
    return advance_shallow_water

def advance_hydrostatic_hll(geometry, *, initial_depth_m, forcing_interval_s, intervals, forcing_provider, boundary_stage_provider, source_identity, forcing_identity, budget, snapshot_interval_s, interval_observer, momentum_observer):
    from terrain_pipeline.surface_hydraulics import validate_budget as _x21_validate_budget
    _x21_validate_budget(budget)
    a, meta = (geometry['arrays'], geometry['metadata'])
    bed = a['H2_m']
    initial = _i66_np.asarray(initial_depth_m)
    if initial.dtype != _i66_np.float64 or initial.shape != bed.shape or (not _i66_np.isfinite(initial).all()) or _i66_np.any(initial < 0) or _i66_np.any(initial > budget.max_depth_m):
        raise ValueError('shallow-water initial depth invalid')
    if bed.size > budget.max_cells or intervals + 1 > budget.max_snapshots or intervals * forcing_interval_s > budget.max_duration_s or (snapshot_interval_s != forcing_interval_s):
        raise ValueError('shallow-water domain/time/snapshot budget invalid')
    estimate = bed.size * 8 * (40 + 9 * (intervals + 1))
    if estimate > budget.max_bytes:
        raise ValueError('shallow-water saved momentum memory budget exceeded')
    datum = float(bed.min())
    relative_bed = bed - datum
    state = _i66_np.column_stack((initial.ravel(), _i66_np.zeros((bed.size, 2))))
    spacing, area = (meta['spacing_m'], meta['spacing_m'] ** 2)
    stages = [state.copy()]
    times = [0.0]
    initial_volume = float(initial.sum() * area)
    supplied = imported = exported = 0.0
    ledgers = [[0.0, 0.0, 0.0, initial_volume, 0.0]]
    steps = evaluations = limited = 0
    minimum_dt = _i66_math.inf
    maximum_dt = maximum_speed = 0.0
    started = _i66_time.monotonic()
    last_i = _i66_np.zeros(len(a['face_left']))
    last_b = _i66_np.zeros(len(a['boundary_cell']))
    for interval in range(intervals):
        source = _i66_np.asarray(forcing_provider(interval))
        tailwater = _i66_np.asarray(boundary_stage_provider(interval))
        if source.dtype != _i66_np.float64 or source.shape != bed.shape or (not _i66_np.isfinite(source).all()) or _i66_np.any(source < 0) or (tailwater.dtype != _i66_np.float64) or (tailwater.shape != (len(last_b),)) or (not _i66_np.isfinite(tailwater).all()):
            raise ValueError('shallow-water complete finite forcing/tailwater required')
        source = source.ravel() / area
        tail = tailwater - datum
        start_state = state.copy()
        transfer_i = _i66_np.zeros_like(last_i)
        transfer_b = _i66_np.zeros_like(last_b)
        momentum_transfer_i = _i66_np.zeros((len(last_i), 2))
        momentum_transfer_b = _i66_np.zeros((len(last_b), 2))
        before_i, before_b = (last_i.copy(), last_b.copy())
        bed_impulse = _i66_np.zeros((bed.size, 2))
        drag_impulse = _i66_np.zeros((bed.size, 2))
        supplied_cell = _i66_np.zeros(bed.size)
        current = interval * forcing_interval_s
        end = (interval + 1) * forcing_interval_s
        first = True
        while current < end - 1e-12:
            if steps >= budget.max_substeps or _i66_time.monotonic() - started > budget.max_wall_s:
                raise RuntimeError('shallow-water execution resource budget exceeded')
            velocity = _i66_np.divide(state[:, 1:], state[:, 0, None], out=_i66_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
            speed = float((_i66_np.sum(abs(velocity), axis=1) + 2 * _i66_np.sqrt(budget.gravity_m_s2 * state[:, 0])).max(initial=0))
            external_depth = _i66_np.maximum(tail - relative_bed.ravel()[a['boundary_cell']], 0.0)
            speed = max(speed, float(2 * _i66_np.sqrt(budget.gravity_m_s2 * external_depth[a['boundary_kind'] != 0]).max(initial=0)))
            dt = min(budget.max_dt_s, budget.inertial_cfl * spacing / max(speed, 1e-12), end - current)
            rhs1, witness1 = shallow_water_rhs_flat(state, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=dt, boundary_crest=a['boundary_crest_m'] - datum)
            rhs1[:, 0] += source
            trial = state + dt * rhs1
            if _i66_np.any(trial[:, 0] < 0):
                raise RuntimeError('shallow-water first RK positivity refusal')
            rhs2, witness2 = shallow_water_rhs_flat(trial, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=dt, boundary_crest=a['boundary_crest_m'] - datum)
            rhs2[:, 0] += source
            updated = 0.5 * state + 0.5 * (trial + dt * rhs2)
            before_drag = updated[:, 1:].copy()
            wet = updated[:, 0] > 0
            magnitude = _i66_np.linalg.norm(updated[wet, 1:], axis=1)
            coefficient = budget.gravity_m_s2 * budget.roughness_s_m_third ** 2 * magnitude / updated[wet, 0] ** (7 / 3)
            updated[wet, 1:] /= (1 + dt * coefficient)[:, None]
            if not _i66_np.isfinite(updated).all() or _i66_np.any(updated[:, 0] < 0) or _i66_np.any(updated[:, 0] > budget.max_depth_m):
                raise RuntimeError('shallow-water final RK depth refusal; no clipping')
            qi = 0.5 * (witness1['internal_flux'][:, 0] + witness2['internal_flux'][:, 0]) * spacing
            qb = 0.5 * (witness1['boundary_flux'][:, 0] + witness2['boundary_flux'][:, 0]) * spacing
            bed_step = 0.5 * dt * (witness1['bed_source'][:, 1:] + witness2['bed_source'][:, 1:])
            if first:
                momentum_observer(dict(interval=interval, time_start_s=current, dt_s=dt, state_before=state.copy(), state_predictor=trial.copy(), state_after=updated.copy(), forcing_m3_s=source * area, tailwater_m=tailwater.copy(), rk1_internal_flux=witness1['internal_flux'], rk2_internal_flux=witness2['internal_flux'], rk1_boundary_flux=witness1['boundary_flux'], rk2_boundary_flux=witness2['boundary_flux'], rk1_bed_source=witness1['bed_source'], rk2_bed_source=witness2['bed_source'], manning_momentum_change=updated[:, 1:] - before_drag))
                first = False
            transfer_i += dt * qi
            transfer_b += dt * qb
            momentum_transfer_i += 0.5 * dt * spacing * (witness1['internal_flux'][:, 1:] + witness2['internal_flux'][:, 1:])
            momentum_transfer_b += 0.5 * dt * spacing * (witness1['boundary_flux'][:, 1:] + witness2['boundary_flux'][:, 1:])
            bed_impulse += bed_step
            drag_impulse += updated[:, 1:] - before_drag
            supplied_cell += dt * source * area
            supplied += float(dt * source.sum() * area)
            imported += float(dt * _i66_np.maximum(-qb, 0).sum())
            exported += float(dt * _i66_np.maximum(qb, 0).sum())
            limited += witness1['limited_donors'] + witness2['limited_donors']
            state = updated
            _, endpoint = shallow_water_rhs_flat(state, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=0.0, boundary_crest=a['boundary_crest_m'] - datum)
            last_i = endpoint['internal_flux'][:, 0] * spacing
            last_b = endpoint['boundary_flux'][:, 0] * spacing
            current += dt
            steps += 1
            evaluations += 2 * (len(qi) + len(qb))
            if evaluations > budget.max_face_evaluations:
                raise RuntimeError('shallow-water face work budget exceeded')
            minimum_dt = min(minimum_dt, dt)
            maximum_dt = max(maximum_dt, dt)
            maximum_speed = max(maximum_speed, speed)
        interval_observer(dict(interval=interval, time_start_s=interval * forcing_interval_s, time_end_s=end, depth_before_m=start_state[:, 0], depth_after_m=state[:, 0].copy(), momentum_before=start_state[:, 1:], momentum_after=state[:, 1:].copy(), internal_transfer_m3=transfer_i, boundary_transfer_m3=transfer_b, forcing_volume_m3=supplied_cell, internal_momentum_transfer=momentum_transfer_i, boundary_momentum_transfer=momentum_transfer_b, bed_momentum_change=bed_impulse, manning_momentum_change=drag_impulse, internal_q_before_m3_s=before_i, internal_q_after_m3_s=last_i.copy(), boundary_q_before_m3_s=before_b, boundary_q_after_m3_s=last_b.copy()))
        stages.append(state.copy())
        times.append(end)
        volume = float(state[:, 0].sum() * area)
        ledgers.append([supplied, imported, exported, volume, volume - initial_volume - supplied - imported + exported])
    saved = _i66_np.asarray(stages)
    return dict(arrays=dict(time_s=_i66_np.asarray(times), depth_m=saved[:, :, 0].reshape(-1, *bed.shape), momentum_x_m2_s=saved[:, :, 1].reshape(-1, *bed.shape), momentum_z_m2_s=saved[:, :, 2].reshape(-1, *bed.shape), initial_depth_m=initial.copy(), ledger=_i66_np.asarray(ledgers), final_internal_q_m3_s=last_i, final_boundary_q_m3_s=last_b), metadata=dict(schema=HYDROSTATIC_HLL_MODEL, hydraulic_model=HYDROSTATIC_HLL_MODEL, status='completed', failure=None, budget=vars(budget), source_identity=source_identity, forcing_identity=forcing_identity, requested_time_s=intervals * forcing_interval_s, committed_time_s=intervals * forcing_interval_s, substeps=steps, face_evaluations=evaluations, wall_s=_i66_time.monotonic() - started, initial_volume_m3=initial_volume, final_volume_m3=float(state[:, 0].sum() * area), supplied_m3=supplied, boundary_input_m3=imported, boundary_output_m3=exported, estimated_peak_bytes=estimate, scope='explicit independent FV shallow-water HLL hydrostatic reconstruction; first spatial order, SSPRK2 time; uncalibrated'), diagnostics=dict(minimum_dt_s=minimum_dt, maximum_dt_s=maximum_dt, maximum_wave_speed_m_s=maximum_speed, limited_donor_count=limited, negative_water_clip_count=0, physical_limitation='first spatial order; flat-cell coarse bed; no calibrated natural certification'))
SUBGRID_SEGMENTED_HLL_MODEL = 'single-domain-subgrid-storage-segmented-HLL-SSPRK2-v3'

def subgrid_segmented_hll_rhs(state, bed, *, support, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
    from terrain_pipeline.fine_subgrid import storage_stages as _x29_storage_stages
    rows, columns = bed.shape
    count = bed.size
    grid = _i75_np.arange(count).reshape(rows, columns)
    left = _i75_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    right = _i75_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    axes = _i75_np.r_[_i75_np.zeros(rows * (columns - 1), _i75_np.int64), _i75_np.ones((rows - 1) * columns, _i75_np.int64)]
    cells = _i75_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    boundary_axes = _i75_np.r_[_i75_np.zeros(2 * rows, _i75_np.int64), _i75_np.ones(2 * columns, _i75_np.int64)]
    signs = _i75_np.r_[-_i75_np.ones(rows), _i75_np.ones(rows), -_i75_np.ones(columns), _i75_np.ones(columns)]
    stage = _x29_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
    velocity = _i75_np.divide(state[:, 1:], state[:, 0, None], out=_i75_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    crests = support['face_segment_crest_relative_m']
    boundary_crests = support['boundary_segment_crest_relative_m'].copy()
    if boundary_crest is not None:
        opened = boundary_kind != 0
        boundary_crests[opened] = _i75_np.maximum(boundary_crests[opened], boundary_crest[opened, None])
    segments = crests.shape[1]
    flux = _i75_np.zeros((len(left), 3))
    boundary_flux = _i75_np.zeros((len(cells), 3))
    pressure_left, pressure_right = (_i75_np.zeros(len(left)), _i75_np.zeros(len(left)))
    pressure_boundary = _i75_np.zeros(len(cells))
    maximum_speed = 0.0
    for axis in (0, 1):
        mask = axes == axis
        crest = crests[mask].ravel()
        hl = _i75_np.maximum(stage[left[mask], None] - crests[mask], 0.0)
        hr = _i75_np.maximum(stage[right[mask], None] - crests[mask], 0.0)
        ul = _i75_np.repeat(velocity[left[mask]], segments, axis=0)
        ur = _i75_np.repeat(velocity[right[mask]], segments, axis=0)
        ls = _i75_np.column_stack((hl.ravel(), hl.ravel()[:, None] * ul))
        rs = _i75_np.column_stack((hr.ravel(), hr.ravel()[:, None] * ur))
        f, _, _, speed = hydrostatic_hll(ls, rs, crest, crest, gravity=gravity, axis=axis)
        flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        pressure_left[mask] = 0.5 * gravity * _i75_np.mean(hl ** 2, axis=1)
        pressure_right[mask] = 0.5 * gravity * _i75_np.mean(hr ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
        mask = boundary_axes == axis
        crest = boundary_crests[mask]
        h = _i75_np.maximum(stage[cells[mask], None] - crest, 0.0)
        u = _i75_np.repeat(velocity[cells[mask]], segments, axis=0)
        sign = _i75_np.repeat(signs[mask], segments)
        first = _i75_np.column_stack((h.ravel(), h.ravel()[:, None] * u))
        ghost = first.copy()
        ghost[:, axis + 1] *= -1
        opened = _i75_np.repeat(boundary_kind[mask] != 0, segments)
        exterior_stage = _i75_np.where(boundary_kind[mask, None] == 1, crest, tailwater[mask, None])
        ghost[opened, 0] = _i75_np.maximum(exterior_stage - crest, 0.0).ravel()[opened]
        ghost[opened, 1:] = 0.0
        first[:, axis + 1] *= sign
        ghost[:, axis + 1] *= sign
        f, _, _, speed = hydrostatic_hll(first, ghost, crest.ravel(), crest.ravel(), gravity=gravity, axis=axis)
        f[:, axis + 1] *= sign
        boundary_flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        pressure_boundary[mask] = 0.5 * gravity * _i75_np.mean(h ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
    outgoing = _i75_np.bincount(left, weights=_i75_np.maximum(flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i75_np.bincount(right, weights=_i75_np.maximum(-flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i75_np.bincount(cells, weights=_i75_np.maximum(boundary_flux[:, 0], 0) * spacing, minlength=count)
    scales = _i75_np.ones(count)
    limited = outgoing * dt > state[:, 0] * spacing ** 2
    scales[limited] = state[limited, 0] * spacing ** 2 / (outgoing[limited] * dt) * (1 - 1e-12)
    flux *= _i75_np.where(flux[:, 0] >= 0, scales[left], scales[right])[:, None]
    boundary_flux *= _i75_np.where(boundary_flux[:, 0] >= 0, scales[cells], 1.0)[:, None]
    rhs = _i75_np.zeros_like(state)
    for component in range(3):
        _i75_np.add.at(rhs[:, component], left, -flux[:, component] / spacing)
        _i75_np.add.at(rhs[:, component], right, flux[:, component] / spacing)
        _i75_np.add.at(rhs[:, component], cells, -boundary_flux[:, component] / spacing)
    pressure = _i75_np.zeros_like(state)
    _i75_np.add.at(pressure, (left, axes + 1), pressure_left / spacing)
    _i75_np.add.at(pressure, (right, axes + 1), -pressure_right / spacing)
    _i75_np.add.at(pressure, (cells, boundary_axes + 1), signs * pressure_boundary / spacing)
    rhs += pressure
    return (rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure, maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum())))
CANONICAL_MANNING_MODEL = 'single-domain-subgrid-storage-segmented-HLL-canonical-Manning-SSPRK2-v7'

def manning_damping_canonical(state, dt, gravity, roughness, *, support):
    from terrain_pipeline.fine_subgrid import storage_stages as _x33_storage_stages
    stage = _x33_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
    depth = _i79_np.maximum(stage[:, None] - support['subcell_bed_relative_m'], 0.0)
    inverse = _i79_np.zeros_like(depth)
    _i79_np.power(depth, -1 / 3, out=inverse, where=depth > 0)
    factor = inverse.mean(axis=1)
    depth_squared = state[:, 0] ** 2
    magnitude = _i79_np.hypot(state[:, 1], state[:, 2])
    denominator = depth_squared + dt * gravity * roughness ** 2 * magnitude * factor
    damping = _i79_np.divide(depth_squared, denominator, out=_i79_np.zeros_like(depth_squared), where=denominator > 0)
    return (damping, factor)

def advance_with_drag(geometry, *, rhs, model, scope, physical_limitation, initial_depth_m, forcing_interval_s, intervals, forcing_provider, boundary_stage_provider, source_identity, forcing_identity, budget, snapshot_interval_s, interval_observer, momentum_observer, hydraulic_datum_m=None, wave_speed=None, stage_provider=None, face_evaluation_multiplier=1, drag_provider=None):
    from terrain_pipeline.surface_hydraulics import validate_budget as _x23_validate_budget
    _x23_validate_budget(budget)
    a, meta = (geometry['arrays'], geometry['metadata'])
    bed = a['H2_m']
    initial = _i69_np.asarray(initial_depth_m)
    if initial.dtype != _i69_np.float64 or initial.shape != bed.shape or (not _i69_np.isfinite(initial).all()) or _i69_np.any(initial < 0) or _i69_np.any(initial > budget.max_depth_m):
        raise ValueError('shallow-water initial depth invalid')
    if bed.size > budget.max_cells or intervals + 1 > budget.max_snapshots or intervals * forcing_interval_s > budget.max_duration_s or (snapshot_interval_s != forcing_interval_s):
        raise ValueError('shallow-water domain/time/snapshot budget invalid')
    support_bytes = sum((a[name].nbytes for name in a if 'subcell_' in name or 'segment_' in name))
    segment_work_bytes = 8 * 20 * face_evaluation_multiplier * (len(a['face_left']) + len(a['boundary_cell']))
    estimate = bed.size * 8 * (40 + 10 * (intervals + 1)) + support_bytes + segment_work_bytes
    if estimate > budget.max_bytes:
        raise ValueError('shallow-water saved momentum memory budget exceeded')
    datum = float(bed.min()) if hydraulic_datum_m is None else hydraulic_datum_m
    relative_bed = bed - datum
    state = _i69_np.column_stack((initial.ravel(), _i69_np.zeros((bed.size, 2))))
    spacing, area = (meta['spacing_m'], meta['spacing_m'] ** 2)
    stages = [state.copy()]
    times = [0.0]
    initial_volume = float(initial.sum() * area)
    supplied = imported = exported = 0.0
    ledgers = [[0.0, 0.0, 0.0, initial_volume, 0.0]]
    steps = evaluations = limited = 0
    minimum_dt = _i69_math.inf
    maximum_dt = maximum_speed = 0.0
    started = _i69_time.monotonic()
    last_i = _i69_np.zeros(len(a['face_left']))
    last_b = _i69_np.zeros(len(a['boundary_cell']))
    for interval in range(intervals):
        source = _i69_np.asarray(forcing_provider(interval))
        tailwater = _i69_np.asarray(boundary_stage_provider(interval))
        if source.dtype != _i69_np.float64 or source.shape != bed.shape or (not _i69_np.isfinite(source).all()) or _i69_np.any(source < 0) or (tailwater.dtype != _i69_np.float64) or (tailwater.shape != (len(last_b),)) or (not _i69_np.isfinite(tailwater).all()):
            raise ValueError('shallow-water complete finite forcing/tailwater required')
        source = source.ravel() / area
        tail = tailwater - datum
        start_state = state.copy()
        transfer_i = _i69_np.zeros_like(last_i)
        transfer_b = _i69_np.zeros_like(last_b)
        momentum_transfer_i = _i69_np.zeros((len(last_i), 2))
        momentum_transfer_b = _i69_np.zeros((len(last_b), 2))
        before_i, before_b = (last_i.copy(), last_b.copy())
        bed_impulse = _i69_np.zeros((bed.size, 2))
        drag_impulse = _i69_np.zeros((bed.size, 2))
        supplied_cell = _i69_np.zeros(bed.size)
        current = interval * forcing_interval_s
        end = (interval + 1) * forcing_interval_s
        first = True
        while current < end - 1e-12:
            if steps >= budget.max_substeps or _i69_time.monotonic() - started > budget.max_wall_s:
                raise RuntimeError('shallow-water execution resource budget exceeded')
            velocity = _i69_np.divide(state[:, 1:], state[:, 0, None], out=_i69_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
            speed = float((_i69_np.sum(abs(velocity), axis=1) + 2 * _i69_np.sqrt(budget.gravity_m_s2 * state[:, 0])).max(initial=0))
            if wave_speed is not None:
                speed = max(speed, wave_speed(state, budget.gravity_m_s2))
            external_bed = a['boundary_segment_crest_relative_m'].min(axis=1) if stage_provider is not None else relative_bed.ravel()[a['boundary_cell']]
            external_bed = _i69_np.maximum(external_bed, a['boundary_crest_m'] - datum)
            exterior_stage = _i69_np.where(a['boundary_kind'] == 1, external_bed, tail)
            external_depth = _i69_np.maximum(exterior_stage - external_bed, 0.0)
            speed = max(speed, float(2 * _i69_np.sqrt(budget.gravity_m_s2 * external_depth[a['boundary_kind'] != 0]).max(initial=0)))
            dt = min(budget.max_dt_s, budget.inertial_cfl * spacing / max(speed, 1e-12), end - current)
            rhs1, witness1 = rhs(state, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=dt, boundary_crest=a['boundary_crest_m'] - datum)
            rhs1[:, 0] += source
            trial = state + dt * rhs1
            if _i69_np.any(trial[:, 0] < 0):
                raise RuntimeError('shallow-water first RK positivity refusal')
            rhs2, witness2 = rhs(trial, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=dt, boundary_crest=a['boundary_crest_m'] - datum)
            rhs2[:, 0] += source
            updated = 0.5 * state + 0.5 * (trial + dt * rhs2)
            before_drag = updated[:, 1:].copy()
            damping, friction_factor = drag_provider(updated, dt, budget.gravity_m_s2, budget.roughness_s_m_third)
            updated[:, 1:] *= damping[:, None]
            if not _i69_np.isfinite(updated).all() or _i69_np.any(updated[:, 0] < 0) or _i69_np.any(updated[:, 0] > budget.max_depth_m):
                raise RuntimeError('shallow-water final RK depth refusal; no clipping')
            qi = 0.5 * (witness1['internal_flux'][:, 0] + witness2['internal_flux'][:, 0]) * spacing
            qb = 0.5 * (witness1['boundary_flux'][:, 0] + witness2['boundary_flux'][:, 0]) * spacing
            bed_step = 0.5 * dt * (witness1['bed_source'][:, 1:] + witness2['bed_source'][:, 1:])
            if first:
                momentum_observer(dict(interval=interval, time_start_s=current, dt_s=dt, state_before=state.copy(), state_predictor=trial.copy(), state_after=updated.copy(), forcing_m3_s=source * area, tailwater_m=tailwater.copy(), rk1_internal_flux=witness1['internal_flux'], rk2_internal_flux=witness2['internal_flux'], rk1_boundary_flux=witness1['boundary_flux'], rk2_boundary_flux=witness2['boundary_flux'], rk1_bed_source=witness1['bed_source'], rk2_bed_source=witness2['bed_source'], manning_momentum_change=updated[:, 1:] - before_drag, manning_inverse_depth_third_mean=friction_factor))
                first = False
            transfer_i += dt * qi
            transfer_b += dt * qb
            momentum_transfer_i += 0.5 * dt * spacing * (witness1['internal_flux'][:, 1:] + witness2['internal_flux'][:, 1:])
            momentum_transfer_b += 0.5 * dt * spacing * (witness1['boundary_flux'][:, 1:] + witness2['boundary_flux'][:, 1:])
            bed_impulse += bed_step
            drag_impulse += updated[:, 1:] - before_drag
            supplied_cell += dt * source * area
            supplied += float(dt * source.sum() * area)
            imported += float(dt * _i69_np.maximum(-qb, 0).sum())
            exported += float(dt * _i69_np.maximum(qb, 0).sum())
            limited += witness1['limited_donors'] + witness2['limited_donors']
            state = updated
            current += dt
            steps += 1
            evaluations += 2 * face_evaluation_multiplier * (len(qi) + len(qb))
            if evaluations > budget.max_face_evaluations:
                raise RuntimeError('shallow-water face work budget exceeded')
            minimum_dt = min(minimum_dt, dt)
            maximum_dt = max(maximum_dt, dt)
            maximum_speed = max(maximum_speed, speed)
        _, endpoint = rhs(state, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=0.0, boundary_crest=a['boundary_crest_m'] - datum)
        evaluations += face_evaluation_multiplier * (len(last_i) + len(last_b))
        if evaluations > budget.max_face_evaluations:
            raise RuntimeError('shallow-water endpoint face work budget exceeded')
        last_i = endpoint['internal_flux'][:, 0] * spacing
        last_b = endpoint['boundary_flux'][:, 0] * spacing
        interval_observer(dict(interval=interval, time_start_s=interval * forcing_interval_s, time_end_s=end, depth_before_m=start_state[:, 0], depth_after_m=state[:, 0].copy(), momentum_before=start_state[:, 1:], momentum_after=state[:, 1:].copy(), internal_transfer_m3=transfer_i, boundary_transfer_m3=transfer_b, forcing_volume_m3=supplied_cell, internal_momentum_transfer=momentum_transfer_i, boundary_momentum_transfer=momentum_transfer_b, bed_momentum_change=bed_impulse, manning_momentum_change=drag_impulse, internal_q_before_m3_s=before_i, internal_q_after_m3_s=last_i.copy(), boundary_q_before_m3_s=before_b, boundary_q_after_m3_s=last_b.copy()))
        stages.append(state.copy())
        times.append(end)
        volume = float(state[:, 0].sum() * area)
        ledgers.append([supplied, imported, exported, volume, volume - initial_volume - supplied - imported + exported])
    saved = _i69_np.asarray(stages)
    result = dict(arrays=dict(time_s=_i69_np.asarray(times), depth_m=saved[:, :, 0].reshape(-1, *bed.shape), momentum_x_m2_s=saved[:, :, 1].reshape(-1, *bed.shape), momentum_z_m2_s=saved[:, :, 2].reshape(-1, *bed.shape), initial_depth_m=initial.copy(), ledger=_i69_np.asarray(ledgers), final_internal_q_m3_s=last_i, final_boundary_q_m3_s=last_b), metadata=dict(schema=model, hydraulic_model=model, status='completed', failure=None, budget=vars(budget), source_identity=source_identity, forcing_identity=forcing_identity, requested_time_s=intervals * forcing_interval_s, committed_time_s=intervals * forcing_interval_s, substeps=steps, face_evaluations=evaluations, wall_s=_i69_time.monotonic() - started, initial_volume_m3=initial_volume, final_volume_m3=float(state[:, 0].sum() * area), supplied_m3=supplied, boundary_input_m3=imported, boundary_output_m3=exported, estimated_peak_bytes=estimate, scope=scope), diagnostics=dict(minimum_dt_s=minimum_dt, maximum_dt_s=maximum_dt, maximum_wave_speed_m_s=maximum_speed, limited_donor_count=limited, negative_water_clip_count=0, physical_limitation=physical_limitation))
    if stage_provider is not None:
        result['arrays']['stage_relative_m'] = _i69_np.asarray([stage_provider(item[:, 0]) for item in saved]).reshape(-1, *bed.shape)
    return result

@_i67_njit(cache=True, fastmath=False)
def storage_kernel(depth, bed, prefix):
    stage = _i67_np.empty(len(depth))
    count = bed.shape[1]
    for cell in range(len(depth)):
        volume = depth[cell] * count
        wet = 0
        for index in range(count):
            if volume >= (index + 1) * bed[cell, index] - prefix[cell, index]:
                wet += 1
        wet = max(wet, 1)
        stage[cell] = (volume + prefix[cell, wet - 1]) / wet
    return stage

@_i67_njit(cache=True, fastmath=False, inline='always')
def _hll_accelerated(hl, hr, ul, vl, ur, vr, crest, gravity, axis):
    if hl > 0:
        ul, vl = (hl * ul / hl, hl * vl / hl)
    else:
        ul, vl = (0.0, 0.0)
    if hr > 0:
        ur, vr = (hr * ur / hr, hr * vr / hr)
    else:
        ur, vr = (0.0, 0.0)
    hl = max(hl + crest - crest, 0.0)
    hr = max(hr + crest - crest, 0.0)
    normal_left = ul if axis == 0 else vl
    normal_right = ur if axis == 0 else vr
    lower = min(normal_left - _i67_math.sqrt(gravity * hl), normal_right - _i67_math.sqrt(gravity * hr))
    upper = max(normal_left + _i67_math.sqrt(gravity * hl), normal_right + _i67_math.sqrt(gravity * hr))
    mass, xmomentum, zmomentum = (0.0, 0.0, 0.0)
    for component in range(3):
        first = hl if component == 0 else hl * ul if component == 1 else hl * vl
        second = hr if component == 0 else hr * ur if component == 1 else hr * vr
        fl, fr = (first * normal_left, second * normal_right)
        if component == axis + 1:
            fl += 0.5 * gravity * hl ** 2
            fr += 0.5 * gravity * hr ** 2
        flux = 0.0
        if upper - lower > 0:
            flux = (upper * fl - lower * fr + lower * upper * (second - first)) / (upper - lower)
        if lower >= 0:
            flux = fl
        if upper <= 0:
            flux = fr
        if component == 0:
            mass = flux
        elif component == 1:
            xmomentum = flux
        else:
            zmomentum = flux
    return (mass, xmomentum, zmomentum, max(abs(lower), abs(upper)))

@_i67_lru_cache(maxsize=16)
def _topology_accelerated(rows, columns):
    grid = _i67_np.arange(rows * columns).reshape(rows, columns)
    return (_i67_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()], _i67_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()], _i67_np.r_[_i67_np.zeros(rows * (columns - 1), _i67_np.int64), _i67_np.ones((rows - 1) * columns, _i67_np.int64)], _i67_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]], _i67_np.r_[_i67_np.zeros(2 * rows, _i67_np.int64), _i67_np.ones(2 * columns, _i67_np.int64)], _i67_np.r_[-_i67_np.ones(rows), _i67_np.ones(rows), -_i67_np.ones(columns), _i67_np.ones(columns)])

@_i67_njit(cache=True, fastmath=False)
def rhs_kernel_accelerated(state, subbed, prefix, crests, boundary_crests, left, right, axes, cells, boundary_axes, signs, spacing, gravity, kinds, tailwater, boundary_crest, dt):
    count, segments = (len(state), crests.shape[1])
    stage = storage_kernel(state[:, 0], subbed, prefix)
    velocity = _i67_np.zeros((count, 2))
    for cell in range(count):
        if state[cell, 0] > 0:
            velocity[cell, 0] = state[cell, 1] / state[cell, 0]
            velocity[cell, 1] = state[cell, 2] / state[cell, 0]
    internal, boundary = (_i67_np.zeros((len(left), 3)), _i67_np.zeros((len(cells), 3)))
    first_pressure, second_pressure, exterior_pressure = (_i67_np.zeros(len(left)), _i67_np.zeros(len(left)), _i67_np.zeros(len(cells)))
    maximum_speed = 0.0
    for face in range(len(left)):
        a, b, axis = (left[face], right[face], axes[face])
        for segment in range(segments):
            crest = crests[face, segment]
            hl, hr = (max(stage[a] - crest, 0.0), max(stage[b] - crest, 0.0))
            mass, mx, mz, speed = _hll_accelerated(hl, hr, velocity[a, 0], velocity[a, 1], velocity[b, 0], velocity[b, 1], crest, gravity, axis)
            internal[face, 0] += mass
            internal[face, 1] += mx
            internal[face, 2] += mz
            first_pressure[face] += hl ** 2
            second_pressure[face] += hr ** 2
            maximum_speed = max(maximum_speed, speed)
        for component in range(3):
            internal[face, component] /= segments
        first_pressure[face] = 0.5 * gravity * first_pressure[face] / segments
        second_pressure[face] = 0.5 * gravity * second_pressure[face] / segments
    for face in range(len(cells)):
        cell, axis, sign = (cells[face], boundary_axes[face], signs[face])
        for segment in range(segments):
            crest = boundary_crests[face, segment]
            if kinds[face] != 0:
                crest = max(crest, boundary_crest[face])
            h = max(stage[cell] - crest, 0.0)
            ux, uz = (velocity[cell, 0], velocity[cell, 1])
            gx, gz = (ux, uz)
            if axis == 0:
                gx = -gx
            else:
                gz = -gz
            ghost_h = h
            if kinds[face] != 0:
                exterior_stage = crest if kinds[face] == 1 else tailwater[face]
                ghost_h, gx, gz = (max(exterior_stage - crest, 0.0), 0.0, 0.0)
            if axis == 0:
                ux, gx = (ux * sign, gx * sign)
            else:
                uz, gz = (uz * sign, gz * sign)
            mass, mx, mz, speed = _hll_accelerated(h, ghost_h, ux, uz, gx, gz, crest, gravity, axis)
            boundary[face, 0] += mass
            boundary[face, 1] += mx * sign if axis == 0 else mx
            boundary[face, 2] += mz * sign if axis == 1 else mz
            exterior_pressure[face] += h ** 2
            maximum_speed = max(maximum_speed, speed)
        for component in range(3):
            boundary[face, component] /= segments
        exterior_pressure[face] = 0.5 * gravity * exterior_pressure[face] / segments
    outgoing_left, outgoing_right, outgoing_boundary = (_i67_np.zeros(count), _i67_np.zeros(count), _i67_np.zeros(count))
    for face in range(len(left)):
        outgoing_left[left[face]] += max(internal[face, 0], 0.0) * spacing
        outgoing_right[right[face]] += max(-internal[face, 0], 0.0) * spacing
    for face in range(len(cells)):
        outgoing_boundary[cells[face]] += max(boundary[face, 0], 0.0) * spacing
    scales = _i67_np.ones(count)
    limited = 0
    minimum = 1.0
    for cell in range(count):
        outgoing = outgoing_left[cell] + outgoing_right[cell] + outgoing_boundary[cell]
        if outgoing * dt > state[cell, 0] * spacing ** 2:
            scales[cell] = state[cell, 0] * spacing ** 2 / (outgoing * dt) * (1 - 1e-12)
            minimum = min(minimum, scales[cell])
            limited += 1
    for face in range(len(left)):
        donor = left[face] if internal[face, 0] >= 0 else right[face]
        for component in range(3):
            internal[face, component] *= scales[donor]
    for face in range(len(cells)):
        if boundary[face, 0] >= 0:
            for component in range(3):
                boundary[face, component] *= scales[cells[face]]
    rhs, pressure = (_i67_np.zeros_like(state), _i67_np.zeros_like(state))
    for face in range(len(left)):
        for component in range(3):
            rhs[left[face], component] -= internal[face, component] / spacing
        pressure[left[face], axes[face] + 1] += first_pressure[face] / spacing
    for face in range(len(left)):
        for component in range(3):
            rhs[right[face], component] += internal[face, component] / spacing
        pressure[right[face], axes[face] + 1] -= second_pressure[face] / spacing
    for face in range(len(cells)):
        for component in range(3):
            rhs[cells[face], component] -= boundary[face, component] / spacing
        pressure[cells[face], boundary_axes[face] + 1] += signs[face] * exterior_pressure[face] / spacing
    rhs += pressure
    return (rhs, internal, boundary, pressure, maximum_speed, minimum, limited)

def shallow_water_rhs_accelerated(state, bed, *, support, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
    topology = _topology_accelerated(*bed.shape)
    crest = _i67_np.full(len(boundary_kind), -_i67_np.inf) if boundary_crest is None else boundary_crest
    rhs, internal, boundary, pressure, speed, minimum, limited = rhs_kernel_accelerated(state, support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'], support['face_segment_crest_relative_m'], support['boundary_segment_crest_relative_m'], *topology, spacing, gravity, boundary_kind, tailwater, crest, dt)
    return (rhs, dict(internal_flux=internal, boundary_flux=boundary, bed_source=pressure, maximum_wave_speed=float(speed), minimum_limiter_factor=float(minimum), limited_donors=int(limited)))

@_i67_njit(cache=True, fastmath=False)
def damping_kernel(state, subbed, prefix, dt, gravity, roughness):
    stage = storage_kernel(state[:, 0], subbed, prefix)
    damping, factor = (_i67_np.zeros(len(state)), _i67_np.zeros(len(state)))
    for cell in range(len(state)):
        for index in range(subbed.shape[1]):
            depth = max(stage[cell] - subbed[cell, index], 0.0)
            if depth > 0:
                factor[cell] += depth ** (-1 / 3)
        factor[cell] /= subbed.shape[1]
        squared = state[cell, 0] ** 2
        denominator = squared + dt * gravity * roughness ** 2 * _i67_math.hypot(state[cell, 1], state[cell, 2]) * factor[cell]
        if denominator > 0:
            damping[cell] = squared / denominator
    return (damping, factor)

def manning_damping_accelerated(state, dt, gravity, roughness, *, support):
    return damping_kernel(state, support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'], dt, gravity, roughness)

def advance_shallow_water_accelerated(geometry, **kwargs):
    arrays, metadata = (geometry['arrays'], geometry['metadata'])
    support = {name: arrays[name] for name in ('subcell_bed_relative_m', 'subcell_prefix_relative_m', 'face_segment_crest_relative_m', 'boundary_segment_crest_relative_m')}

    def stage_provider(depth):
        return storage_kernel(depth, support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])

    def wave_speed(state, gravity):
        stage = stage_provider(state[:, 0])
        maximum_depth = _i67_np.maximum(stage - support['subcell_bed_relative_m'][:, 0], 0.0)
        velocity = _i67_np.divide(state[:, 1:], state[:, 0, None], out=_i67_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
        return float((abs(velocity).sum(axis=1) + 2 * _i67_np.sqrt(gravity * maximum_depth)).max(initial=0))
    result = advance_with_drag(geometry, rhs=_i67_partial(shallow_water_rhs_accelerated, support=support), model=CANONICAL_MANNING_MODEL, hydraulic_datum_m=metadata['hydraulic_datum_m'], wave_speed=wave_speed, stage_provider=stage_provider, drag_provider=_i67_partial(manning_damping_accelerated, support=support), face_evaluation_multiplier=support['face_segment_crest_relative_m'].shape[1], scope='independent FV canonical subgrid storage and segmented advective HLL with canonical Manning; SSPRK2; uncalibrated', physical_limitation='one velocity vector per coarse cell; segmented pressure support; no calibrated natural certification', **kwargs)
    result['metadata']['execution_backend'] = 'numba_fastmath_false_v7_reference_control_flow'
    return result

def advance_with_reconstruction_witness(geometry, *, rhs, model, scope, physical_limitation, initial_depth_m, forcing_interval_s, intervals, forcing_provider, boundary_stage_provider, source_identity, forcing_identity, budget, snapshot_interval_s, interval_observer, momentum_observer, hydraulic_datum_m=None, wave_speed=None, stage_provider=None, face_evaluation_multiplier=1, drag_provider=None):
    from terrain_pipeline.surface_hydraulics import validate_budget as _x24_validate_budget
    _x24_validate_budget(budget)
    a, meta = (geometry['arrays'], geometry['metadata'])
    bed = a['H2_m']
    initial = _i70_np.asarray(initial_depth_m)
    if initial.dtype != _i70_np.float64 or initial.shape != bed.shape or (not _i70_np.isfinite(initial).all()) or _i70_np.any(initial < 0) or _i70_np.any(initial > budget.max_depth_m):
        raise ValueError('shallow-water initial depth invalid')
    if bed.size > budget.max_cells or intervals + 1 > budget.max_snapshots or intervals * forcing_interval_s > budget.max_duration_s or (snapshot_interval_s != forcing_interval_s):
        raise ValueError('shallow-water domain/time/snapshot budget invalid')
    support_bytes = sum((a[name].nbytes for name in a if 'subcell_' in name or 'segment_' in name))
    segment_work_bytes = 8 * 20 * face_evaluation_multiplier * (len(a['face_left']) + len(a['boundary_cell']))
    estimate = bed.size * 8 * (40 + 10 * (intervals + 1)) + support_bytes + segment_work_bytes
    if estimate > budget.max_bytes:
        raise ValueError('shallow-water saved momentum memory budget exceeded')
    datum = float(bed.min()) if hydraulic_datum_m is None else hydraulic_datum_m
    relative_bed = bed - datum
    state = _i70_np.column_stack((initial.ravel(), _i70_np.zeros((bed.size, 2))))
    spacing, area = (meta['spacing_m'], meta['spacing_m'] ** 2)
    stages = [state.copy()]
    times = [0.0]
    initial_volume = float(initial.sum() * area)
    supplied = imported = exported = 0.0
    ledgers = [[0.0, 0.0, 0.0, initial_volume, 0.0]]
    steps = evaluations = limited = 0
    minimum_dt = _i70_math.inf
    maximum_dt = maximum_speed = 0.0
    started = _i70_time.monotonic()
    last_i = _i70_np.zeros(len(a['face_left']))
    last_b = _i70_np.zeros(len(a['boundary_cell']))
    for interval in range(intervals):
        source = _i70_np.asarray(forcing_provider(interval))
        tailwater = _i70_np.asarray(boundary_stage_provider(interval))
        if source.dtype != _i70_np.float64 or source.shape != bed.shape or (not _i70_np.isfinite(source).all()) or _i70_np.any(source < 0) or (tailwater.dtype != _i70_np.float64) or (tailwater.shape != (len(last_b),)) or (not _i70_np.isfinite(tailwater).all()):
            raise ValueError('shallow-water complete finite forcing/tailwater required')
        source = source.ravel() / area
        tail = tailwater - datum
        start_state = state.copy()
        transfer_i = _i70_np.zeros_like(last_i)
        transfer_b = _i70_np.zeros_like(last_b)
        momentum_transfer_i = _i70_np.zeros((len(last_i), 2))
        momentum_transfer_b = _i70_np.zeros((len(last_b), 2))
        before_i, before_b = (last_i.copy(), last_b.copy())
        bed_impulse = _i70_np.zeros((bed.size, 2))
        drag_impulse = _i70_np.zeros((bed.size, 2))
        supplied_cell = _i70_np.zeros(bed.size)
        current = interval * forcing_interval_s
        end = (interval + 1) * forcing_interval_s
        first = True
        while current < end - 1e-12:
            if steps >= budget.max_substeps or _i70_time.monotonic() - started > budget.max_wall_s:
                raise RuntimeError('shallow-water execution resource budget exceeded')
            velocity = _i70_np.divide(state[:, 1:], state[:, 0, None], out=_i70_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
            speed = float((_i70_np.sum(abs(velocity), axis=1) + 2 * _i70_np.sqrt(budget.gravity_m_s2 * state[:, 0])).max(initial=0))
            if wave_speed is not None:
                speed = max(speed, wave_speed(state, budget.gravity_m_s2))
            external_bed = a['boundary_segment_crest_relative_m'].min(axis=1) if stage_provider is not None else relative_bed.ravel()[a['boundary_cell']]
            external_bed = _i70_np.maximum(external_bed, a['boundary_crest_m'] - datum)
            exterior_stage = _i70_np.where(a['boundary_kind'] == 1, external_bed, tail)
            external_depth = _i70_np.maximum(exterior_stage - external_bed, 0.0)
            speed = max(speed, float(2 * _i70_np.sqrt(budget.gravity_m_s2 * external_depth[a['boundary_kind'] != 0]).max(initial=0)))
            dt = min(budget.max_dt_s, budget.inertial_cfl * spacing / max(speed, 1e-12), end - current)
            rhs1, witness1 = rhs(state, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=dt, boundary_crest=a['boundary_crest_m'] - datum)
            rhs1[:, 0] += source
            trial = state + dt * rhs1
            if _i70_np.any(trial[:, 0] < 0):
                raise RuntimeError('shallow-water first RK positivity refusal')
            rhs2, witness2 = rhs(trial, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=dt, boundary_crest=a['boundary_crest_m'] - datum)
            rhs2[:, 0] += source
            updated = 0.5 * state + 0.5 * (trial + dt * rhs2)
            before_drag = updated[:, 1:].copy()
            damping, friction_factor = drag_provider(updated, dt, budget.gravity_m_s2, budget.roughness_s_m_third)
            updated[:, 1:] *= damping[:, None]
            if not _i70_np.isfinite(updated).all() or _i70_np.any(updated[:, 0] < 0) or _i70_np.any(updated[:, 0] > budget.max_depth_m):
                raise RuntimeError('shallow-water final RK depth refusal; no clipping')
            qi = 0.5 * (witness1['internal_flux'][:, 0] + witness2['internal_flux'][:, 0]) * spacing
            qb = 0.5 * (witness1['boundary_flux'][:, 0] + witness2['boundary_flux'][:, 0]) * spacing
            bed_step = 0.5 * dt * (witness1['bed_source'][:, 1:] + witness2['bed_source'][:, 1:])
            if first:
                momentum_observer(dict(interval=interval, time_start_s=current, dt_s=dt, state_before=state.copy(), state_predictor=trial.copy(), state_after=updated.copy(), forcing_m3_s=source * area, tailwater_m=tailwater.copy(), rk1_internal_flux=witness1['internal_flux'], rk2_internal_flux=witness2['internal_flux'], rk1_boundary_flux=witness1['boundary_flux'], rk2_boundary_flux=witness2['boundary_flux'], rk1_bed_source=witness1['bed_source'], rk2_bed_source=witness2['bed_source'], manning_momentum_change=updated[:, 1:] - before_drag, manning_inverse_depth_third_mean=friction_factor, rk1_reconstruction_center=witness1['reconstruction_center'], rk2_reconstruction_center=witness2['reconstruction_center'], rk1_reconstruction_slope_x=witness1['reconstruction_slope_x'], rk2_reconstruction_slope_x=witness2['reconstruction_slope_x'], rk1_reconstruction_slope_z=witness1['reconstruction_slope_z'], rk2_reconstruction_slope_z=witness2['reconstruction_slope_z']))
                first = False
            transfer_i += dt * qi
            transfer_b += dt * qb
            momentum_transfer_i += 0.5 * dt * spacing * (witness1['internal_flux'][:, 1:] + witness2['internal_flux'][:, 1:])
            momentum_transfer_b += 0.5 * dt * spacing * (witness1['boundary_flux'][:, 1:] + witness2['boundary_flux'][:, 1:])
            bed_impulse += bed_step
            drag_impulse += updated[:, 1:] - before_drag
            supplied_cell += dt * source * area
            supplied += float(dt * source.sum() * area)
            imported += float(dt * _i70_np.maximum(-qb, 0).sum())
            exported += float(dt * _i70_np.maximum(qb, 0).sum())
            limited += witness1['limited_donors'] + witness2['limited_donors']
            state = updated
            current += dt
            steps += 1
            evaluations += 2 * face_evaluation_multiplier * (len(qi) + len(qb))
            if evaluations > budget.max_face_evaluations:
                raise RuntimeError('shallow-water face work budget exceeded')
            minimum_dt = min(minimum_dt, dt)
            maximum_dt = max(maximum_dt, dt)
            maximum_speed = max(maximum_speed, speed)
        _, endpoint = rhs(state, relative_bed, spacing=spacing, gravity=budget.gravity_m_s2, boundary_kind=a['boundary_kind'], tailwater=tail, roughness=budget.roughness_s_m_third, dt=0.0, boundary_crest=a['boundary_crest_m'] - datum)
        evaluations += face_evaluation_multiplier * (len(last_i) + len(last_b))
        if evaluations > budget.max_face_evaluations:
            raise RuntimeError('shallow-water endpoint face work budget exceeded')
        last_i = endpoint['internal_flux'][:, 0] * spacing
        last_b = endpoint['boundary_flux'][:, 0] * spacing
        interval_observer(dict(interval=interval, time_start_s=interval * forcing_interval_s, time_end_s=end, depth_before_m=start_state[:, 0], depth_after_m=state[:, 0].copy(), momentum_before=start_state[:, 1:], momentum_after=state[:, 1:].copy(), internal_transfer_m3=transfer_i, boundary_transfer_m3=transfer_b, forcing_volume_m3=supplied_cell, internal_momentum_transfer=momentum_transfer_i, boundary_momentum_transfer=momentum_transfer_b, bed_momentum_change=bed_impulse, manning_momentum_change=drag_impulse, internal_q_before_m3_s=before_i, internal_q_after_m3_s=last_i.copy(), boundary_q_before_m3_s=before_b, boundary_q_after_m3_s=last_b.copy()))
        stages.append(state.copy())
        times.append(end)
        volume = float(state[:, 0].sum() * area)
        ledgers.append([supplied, imported, exported, volume, volume - initial_volume - supplied - imported + exported])
    saved = _i70_np.asarray(stages)
    result = dict(arrays=dict(time_s=_i70_np.asarray(times), depth_m=saved[:, :, 0].reshape(-1, *bed.shape), momentum_x_m2_s=saved[:, :, 1].reshape(-1, *bed.shape), momentum_z_m2_s=saved[:, :, 2].reshape(-1, *bed.shape), initial_depth_m=initial.copy(), ledger=_i70_np.asarray(ledgers), final_internal_q_m3_s=last_i, final_boundary_q_m3_s=last_b), metadata=dict(schema=model, hydraulic_model=model, status='completed', failure=None, budget=vars(budget), source_identity=source_identity, forcing_identity=forcing_identity, requested_time_s=intervals * forcing_interval_s, committed_time_s=intervals * forcing_interval_s, substeps=steps, face_evaluations=evaluations, wall_s=_i70_time.monotonic() - started, initial_volume_m3=initial_volume, final_volume_m3=float(state[:, 0].sum() * area), supplied_m3=supplied, boundary_input_m3=imported, boundary_output_m3=exported, estimated_peak_bytes=estimate, scope=scope), diagnostics=dict(minimum_dt_s=minimum_dt, maximum_dt_s=maximum_dt, maximum_wave_speed_m_s=maximum_speed, limited_donor_count=limited, negative_water_clip_count=0, physical_limitation=physical_limitation))
    if stage_provider is not None:
        result['arrays']['stage_relative_m'] = _i70_np.asarray([stage_provider(item[:, 0]) for item in saved]).reshape(-1, *bed.shape)
    return result
DRY_INDEPENDENT_MODEL = 'single-domain-subgrid-MUSCL-storage-segmented-HLL-SSPRK2-v5'

def reconstruct_independent_slope(stage, velocity, depth, bed, support, boundary_kind, tailwater):
    rows, columns = bed.shape
    fields = _i77_np.column_stack((stage, velocity)).reshape(rows, columns, 3)
    sx, sz = (_i77_np.zeros_like(fields), _i77_np.zeros_like(fields))
    sx[:, 1:-1] = minmod(fields[:, 1:-1] - fields[:, :-2], fields[:, 2:] - fields[:, 1:-1])
    sz[1:-1] = minmod(fields[1:-1] - fields[:-2], fields[2:] - fields[1:-1])
    for axis, side, begin, end in ((0, 0, 0, rows), (0, 1, rows, 2 * rows), (1, 0, 2 * rows, 2 * rows + columns), (1, 1, 2 * rows + columns, 2 * (rows + columns))):
        opened = boundary_kind[begin:end] == 2
        exterior = _i77_np.zeros((end - begin, 3))
        exterior[:, 0] = tailwater[begin:end]
        if axis == 0:
            if columns < 2:
                continue
            edge = fields[:, 0] if side == 0 else fields[:, -1]
            interior = fields[:, 1] - edge if side == 0 else edge - fields[:, -2]
            external = 2 * (edge - exterior) if side == 0 else 2 * (exterior - edge)
            sx[:, 0 if side == 0 else -1][opened] = minmod(interior, external)[opened]
        else:
            if rows < 2:
                continue
            edge = fields[0] if side == 0 else fields[-1]
            interior = fields[1] - edge if side == 0 else edge - fields[-2]
            external = 2 * (edge - exterior) if side == 0 else 2 * (exterior - edge)
            sz[0 if side == 0 else -1][opened] = minmod(interior, external)[opened]
    dry = depth.reshape(rows, columns) == 0
    sx[dry], sz[dry] = (0.0, 0.0)
    available = (stage - support['subcell_bed_relative_m'][:, 0]).reshape(rows, columns)
    for slope in (sx, sz):
        ratio = _i77_np.minimum(1.0, _i77_np.divide(2 * available, abs(slope[:, :, 0]), out=_i77_np.ones_like(available), where=slope[:, :, 0] != 0))
        slope *= ratio[:, :, None]
    return [(fields - 0.5 * sx).reshape(-1, 3), (fields + 0.5 * sx).reshape(-1, 3), (fields - 0.5 * sz).reshape(-1, 3), (fields + 0.5 * sz).reshape(-1, 3)]

def dry_independent_rhs(state, bed, *, support, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
    from terrain_pipeline.fine_subgrid import storage_stages as _x31_storage_stages
    rows, columns = bed.shape
    count = bed.size
    grid = _i77_np.arange(count).reshape(rows, columns)
    left = _i77_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    right = _i77_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    axes = _i77_np.r_[_i77_np.zeros(rows * (columns - 1), _i77_np.int64), _i77_np.ones((rows - 1) * columns, _i77_np.int64)]
    cells = _i77_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    boundary_axes = _i77_np.r_[_i77_np.zeros(2 * rows, _i77_np.int64), _i77_np.ones(2 * columns, _i77_np.int64)]
    signs = _i77_np.r_[-_i77_np.ones(rows), _i77_np.ones(rows), -_i77_np.ones(columns), _i77_np.ones(columns)]
    stage = _x31_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
    velocity = _i77_np.divide(state[:, 1:], state[:, 0, None], out=_i77_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    faces = reconstruct_independent_slope(stage, velocity, state[:, 0], bed, support, boundary_kind, tailwater)
    crests = support['face_segment_crest_relative_m']
    boundary_crests = support['boundary_segment_crest_relative_m'].copy()
    if boundary_crest is not None:
        opened = boundary_kind != 0
        boundary_crests[opened] = _i77_np.maximum(boundary_crests[opened], boundary_crest[opened, None])
    segments = crests.shape[1]
    flux = _i77_np.zeros((len(left), 3))
    boundary_flux = _i77_np.zeros((len(cells), 3))
    pressure_left, pressure_right = (_i77_np.zeros(len(left)), _i77_np.zeros(len(left)))
    pressure_boundary = _i77_np.zeros(len(cells))
    maximum_speed = 0.0
    for axis in (0, 1):
        mask = axes == axis
        crest = crests[mask].ravel()
        reconstructed_left = faces[1 if axis == 0 else 3][left[mask]]
        reconstructed_right = faces[0 if axis == 0 else 2][right[mask]]
        hl = _i77_np.maximum(reconstructed_left[:, 0, None] - crests[mask], 0.0)
        hr = _i77_np.maximum(reconstructed_right[:, 0, None] - crests[mask], 0.0)
        ul = _i77_np.repeat(reconstructed_left[:, 1:], segments, axis=0)
        ur = _i77_np.repeat(reconstructed_right[:, 1:], segments, axis=0)
        ls = _i77_np.column_stack((hl.ravel(), hl.ravel()[:, None] * ul))
        rs = _i77_np.column_stack((hr.ravel(), hr.ravel()[:, None] * ur))
        f, _, _, speed = hydrostatic_hll(ls, rs, crest, crest, gravity=gravity, axis=axis)
        flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        pressure_left[mask] = 0.5 * gravity * _i77_np.mean(_i77_np.maximum(stage[left[mask], None] - crests[mask], 0.0) ** 2, axis=1)
        pressure_right[mask] = 0.5 * gravity * _i77_np.mean(_i77_np.maximum(stage[right[mask], None] - crests[mask], 0.0) ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
        mask = boundary_axes == axis
        crest = boundary_crests[mask]
        boundary_state = _i77_np.empty((mask.sum(), 3))
        negative = signs[mask] < 0
        boundary_state[negative] = faces[0 if axis == 0 else 2][cells[mask][negative]]
        boundary_state[~negative] = faces[1 if axis == 0 else 3][cells[mask][~negative]]
        h = _i77_np.maximum(boundary_state[:, 0, None] - crest, 0.0)
        u = _i77_np.repeat(boundary_state[:, 1:], segments, axis=0)
        sign = _i77_np.repeat(signs[mask], segments)
        first = _i77_np.column_stack((h.ravel(), h.ravel()[:, None] * u))
        ghost = first.copy()
        ghost[:, axis + 1] *= -1
        opened = _i77_np.repeat(boundary_kind[mask] != 0, segments)
        exterior_stage = _i77_np.where(boundary_kind[mask, None] == 1, crest, tailwater[mask, None])
        ghost[opened, 0] = _i77_np.maximum(exterior_stage - crest, 0.0).ravel()[opened]
        ghost[opened, 1:] = 0.0
        first[:, axis + 1] *= sign
        ghost[:, axis + 1] *= sign
        f, _, _, speed = hydrostatic_hll(first, ghost, crest.ravel(), crest.ravel(), gravity=gravity, axis=axis)
        f[:, axis + 1] *= sign
        boundary_flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        pressure_boundary[mask] = 0.5 * gravity * _i77_np.mean(_i77_np.maximum(stage[cells[mask], None] - crest, 0.0) ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
    outgoing = _i77_np.bincount(left, weights=_i77_np.maximum(flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i77_np.bincount(right, weights=_i77_np.maximum(-flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i77_np.bincount(cells, weights=_i77_np.maximum(boundary_flux[:, 0], 0) * spacing, minlength=count)
    scales = _i77_np.ones(count)
    limited = outgoing * dt > state[:, 0] * spacing ** 2
    scales[limited] = state[limited, 0] * spacing ** 2 / (outgoing[limited] * dt) * (1 - 1e-12)
    flux *= _i77_np.where(flux[:, 0] >= 0, scales[left], scales[right])[:, None]
    boundary_flux *= _i77_np.where(boundary_flux[:, 0] >= 0, scales[cells], 1.0)[:, None]
    rhs = _i77_np.zeros_like(state)
    for component in range(3):
        _i77_np.add.at(rhs[:, component], left, -flux[:, component] / spacing)
        _i77_np.add.at(rhs[:, component], right, flux[:, component] / spacing)
        _i77_np.add.at(rhs[:, component], cells, -boundary_flux[:, component] / spacing)
    pressure = _i77_np.zeros_like(state)
    _i77_np.add.at(pressure, (left, axes + 1), pressure_left / spacing)
    _i77_np.add.at(pressure, (right, axes + 1), -pressure_right / spacing)
    _i77_np.add.at(pressure, (cells, boundary_axes + 1), signs * pressure_boundary / spacing)
    rhs += pressure
    return (rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure, maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum())))

def prepare_linear_stage_independent_support(bed):
    from terrain_pipeline.fine_subgrid import prepare_subgrid_support as _x25_prepare_subgrid_support
    support, datum = _x25_prepare_subgrid_support(bed)
    canonical = bed['arrays']['canonical_bed_center_m'] - datum
    rows, columns = bed['arrays']['H2_m'].shape
    factor = int(bed['metadata']['spacing_m'])
    support['subcell_bed_position_relative_m'] = canonical.reshape(rows, factor, columns, factor).transpose(0, 2, 1, 3).reshape(rows * columns, factor, factor)
    return (support, datum)

def reconstruct_linear_stage_independent(state, bed, support, boundary_kind, tailwater):
    from terrain_pipeline.fine_subgrid import storage_stages as _x26_storage_stages
    stage = _x26_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
    velocity = _i71_np.divide(state[:, 1:], state[:, 0, None], out=_i71_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    faces = reconstruct_independent_slope(stage, velocity, state[:, 0], bed, support, boundary_kind, tailwater)
    slope_x, slope_z = (faces[1] - faces[0], faces[3] - faces[2])
    factor = support['subcell_bed_position_relative_m'].shape[1]
    coordinate = (_i71_np.arange(factor) + 0.5) / factor - 0.5
    x, z = _i71_np.meshgrid(coordinate, coordinate)
    eta_offset = slope_x[:, 0, None, None] * x + slope_z[:, 0, None, None] * z
    effective_bed = support['subcell_bed_position_relative_m'] - eta_offset
    sorted_effective_bed = _i71_np.sort(effective_bed.reshape(len(state), -1), axis=1)
    eta0 = _x26_storage_stages(state[:, 0], sorted_effective_bed, _i71_np.cumsum(sorted_effective_bed, axis=1))
    subdepth = _i71_np.maximum(eta0[:, None, None] - effective_bed, 0.0)
    velocity_offset = slope_x[:, None, None, 1:] * x[None, :, :, None] + slope_z[:, None, None, 1:] * z[None, :, :, None]
    offset_momentum = _i71_np.mean(subdepth[:, :, :, None] * velocity_offset, axis=(1, 2))
    center_velocity = _i71_np.divide(state[:, 1:] - offset_momentum, state[:, 0, None], out=_i71_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    return dict(center=_i71_np.column_stack((eta0, center_velocity)), slope_x=slope_x, slope_z=slope_z, subcell_depth=subdepth, subcell_velocity=center_velocity[:, None, None, :] + velocity_offset)
DRY_NEIGHBOR_MODEL = 'single-domain-subgrid-MUSCL-storage-segmented-HLL-SSPRK2-v6'

def reconstruct_dry_neighbor_slope(stage, velocity, depth, bed, support, boundary_kind, tailwater):
    rows, columns = bed.shape
    fields = _i78_np.column_stack((stage, velocity)).reshape(rows, columns, 3)
    sx, sz = (_i78_np.zeros_like(fields), _i78_np.zeros_like(fields))
    sx[:, 1:-1] = minmod(fields[:, 1:-1] - fields[:, :-2], fields[:, 2:] - fields[:, 1:-1])
    sz[1:-1] = minmod(fields[1:-1] - fields[:-2], fields[2:] - fields[1:-1])
    depth_grid = depth.reshape(rows, columns)
    for axis, side, begin, end in ((0, 0, 0, rows), (0, 1, rows, 2 * rows), (1, 0, 2 * rows, 2 * rows + columns), (1, 1, 2 * rows + columns, 2 * (rows + columns))):
        opened = boundary_kind[begin:end] == 2
        exterior = _i78_np.zeros((end - begin, 3))
        exterior[:, 0] = tailwater[begin:end]
        if axis == 0:
            if columns < 2:
                continue
            edge = fields[:, 0] if side == 0 else fields[:, -1]
            interior = fields[:, 1] - edge if side == 0 else edge - fields[:, -2]
            external = 2 * (edge - exterior) if side == 0 else 2 * (exterior - edge)
            dry_neighbor = depth_grid[:, 1 if side == 0 else -2] == 0
            interior[dry_neighbor, 0] = external[dry_neighbor, 0]
            sx[:, 0 if side == 0 else -1][opened] = minmod(interior, external)[opened]
        else:
            if rows < 2:
                continue
            edge = fields[0] if side == 0 else fields[-1]
            interior = fields[1] - edge if side == 0 else edge - fields[-2]
            external = 2 * (edge - exterior) if side == 0 else 2 * (exterior - edge)
            dry_neighbor = depth_grid[1 if side == 0 else -2] == 0
            interior[dry_neighbor, 0] = external[dry_neighbor, 0]
            sz[0 if side == 0 else -1][opened] = minmod(interior, external)[opened]
    dry = depth.reshape(rows, columns) == 0
    sx[dry], sz[dry] = (0.0, 0.0)
    available = (stage - support['subcell_bed_relative_m'][:, 0]).reshape(rows, columns)
    for slope in (sx, sz):
        ratio = _i78_np.minimum(1.0, _i78_np.divide(2 * available, abs(slope[:, :, 0]), out=_i78_np.ones_like(available), where=slope[:, :, 0] != 0))
        slope *= ratio[:, :, None]
    return [(fields - 0.5 * sx).reshape(-1, 3), (fields + 0.5 * sx).reshape(-1, 3), (fields - 0.5 * sz).reshape(-1, 3), (fields + 0.5 * sz).reshape(-1, 3)]

def dry_neighbor_rhs(state, bed, *, support, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
    from terrain_pipeline.fine_subgrid import storage_stages as _x32_storage_stages
    rows, columns = bed.shape
    count = bed.size
    grid = _i78_np.arange(count).reshape(rows, columns)
    left = _i78_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    right = _i78_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    axes = _i78_np.r_[_i78_np.zeros(rows * (columns - 1), _i78_np.int64), _i78_np.ones((rows - 1) * columns, _i78_np.int64)]
    cells = _i78_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    boundary_axes = _i78_np.r_[_i78_np.zeros(2 * rows, _i78_np.int64), _i78_np.ones(2 * columns, _i78_np.int64)]
    signs = _i78_np.r_[-_i78_np.ones(rows), _i78_np.ones(rows), -_i78_np.ones(columns), _i78_np.ones(columns)]
    stage = _x32_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
    velocity = _i78_np.divide(state[:, 1:], state[:, 0, None], out=_i78_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    faces = reconstruct_dry_neighbor_slope(stage, velocity, state[:, 0], bed, support, boundary_kind, tailwater)
    crests = support['face_segment_crest_relative_m']
    boundary_crests = support['boundary_segment_crest_relative_m'].copy()
    if boundary_crest is not None:
        opened = boundary_kind != 0
        boundary_crests[opened] = _i78_np.maximum(boundary_crests[opened], boundary_crest[opened, None])
    segments = crests.shape[1]
    flux = _i78_np.zeros((len(left), 3))
    boundary_flux = _i78_np.zeros((len(cells), 3))
    pressure_left, pressure_right = (_i78_np.zeros(len(left)), _i78_np.zeros(len(left)))
    pressure_boundary = _i78_np.zeros(len(cells))
    maximum_speed = 0.0
    for axis in (0, 1):
        mask = axes == axis
        crest = crests[mask].ravel()
        reconstructed_left = faces[1 if axis == 0 else 3][left[mask]]
        reconstructed_right = faces[0 if axis == 0 else 2][right[mask]]
        hl = _i78_np.maximum(reconstructed_left[:, 0, None] - crests[mask], 0.0)
        hr = _i78_np.maximum(reconstructed_right[:, 0, None] - crests[mask], 0.0)
        ul = _i78_np.repeat(reconstructed_left[:, 1:], segments, axis=0)
        ur = _i78_np.repeat(reconstructed_right[:, 1:], segments, axis=0)
        ls = _i78_np.column_stack((hl.ravel(), hl.ravel()[:, None] * ul))
        rs = _i78_np.column_stack((hr.ravel(), hr.ravel()[:, None] * ur))
        f, _, _, speed = hydrostatic_hll(ls, rs, crest, crest, gravity=gravity, axis=axis)
        flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        pressure_left[mask] = 0.5 * gravity * _i78_np.mean(_i78_np.maximum(stage[left[mask], None] - crests[mask], 0.0) ** 2, axis=1)
        pressure_right[mask] = 0.5 * gravity * _i78_np.mean(_i78_np.maximum(stage[right[mask], None] - crests[mask], 0.0) ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
        mask = boundary_axes == axis
        crest = boundary_crests[mask]
        boundary_state = _i78_np.empty((mask.sum(), 3))
        negative = signs[mask] < 0
        boundary_state[negative] = faces[0 if axis == 0 else 2][cells[mask][negative]]
        boundary_state[~negative] = faces[1 if axis == 0 else 3][cells[mask][~negative]]
        h = _i78_np.maximum(boundary_state[:, 0, None] - crest, 0.0)
        u = _i78_np.repeat(boundary_state[:, 1:], segments, axis=0)
        sign = _i78_np.repeat(signs[mask], segments)
        first = _i78_np.column_stack((h.ravel(), h.ravel()[:, None] * u))
        ghost = first.copy()
        ghost[:, axis + 1] *= -1
        opened = _i78_np.repeat(boundary_kind[mask] != 0, segments)
        exterior_stage = _i78_np.where(boundary_kind[mask, None] == 1, crest, tailwater[mask, None])
        ghost[opened, 0] = _i78_np.maximum(exterior_stage - crest, 0.0).ravel()[opened]
        ghost[opened, 1:] = 0.0
        first[:, axis + 1] *= sign
        ghost[:, axis + 1] *= sign
        f, _, _, speed = hydrostatic_hll(first, ghost, crest.ravel(), crest.ravel(), gravity=gravity, axis=axis)
        f[:, axis + 1] *= sign
        boundary_flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        pressure_boundary[mask] = 0.5 * gravity * _i78_np.mean(_i78_np.maximum(stage[cells[mask], None] - crest, 0.0) ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
    outgoing = _i78_np.bincount(left, weights=_i78_np.maximum(flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i78_np.bincount(right, weights=_i78_np.maximum(-flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i78_np.bincount(cells, weights=_i78_np.maximum(boundary_flux[:, 0], 0) * spacing, minlength=count)
    scales = _i78_np.ones(count)
    limited = outgoing * dt > state[:, 0] * spacing ** 2
    scales[limited] = state[limited, 0] * spacing ** 2 / (outgoing[limited] * dt) * (1 - 1e-12)
    flux *= _i78_np.where(flux[:, 0] >= 0, scales[left], scales[right])[:, None]
    boundary_flux *= _i78_np.where(boundary_flux[:, 0] >= 0, scales[cells], 1.0)[:, None]
    rhs = _i78_np.zeros_like(state)
    for component in range(3):
        _i78_np.add.at(rhs[:, component], left, -flux[:, component] / spacing)
        _i78_np.add.at(rhs[:, component], right, flux[:, component] / spacing)
        _i78_np.add.at(rhs[:, component], cells, -boundary_flux[:, component] / spacing)
    pressure = _i78_np.zeros_like(state)
    _i78_np.add.at(pressure, (left, axes + 1), pressure_left / spacing)
    _i78_np.add.at(pressure, (right, axes + 1), -pressure_right / spacing)
    _i78_np.add.at(pressure, (cells, boundary_axes + 1), signs * pressure_boundary / spacing)
    rhs += pressure
    return (rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure, maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum())))

def prepare_linear_stage_support(bed):
    from terrain_pipeline.fine_subgrid import prepare_subgrid_support as _x27_prepare_subgrid_support
    support, datum = _x27_prepare_subgrid_support(bed)
    canonical = bed['arrays']['canonical_bed_center_m'] - datum
    rows, columns = bed['arrays']['H2_m'].shape
    factor = int(bed['metadata']['spacing_m'])
    support['subcell_bed_position_relative_m'] = canonical.reshape(rows, factor, columns, factor).transpose(0, 2, 1, 3).reshape(rows * columns, factor, factor)
    return (support, datum)

def reconstruct_linear_stage(state, bed, support, boundary_kind, tailwater):
    from terrain_pipeline.fine_subgrid import storage_stages as _x28_storage_stages
    stage = _x28_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
    velocity = _i72_np.divide(state[:, 1:], state[:, 0, None], out=_i72_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    faces = reconstruct_dry_neighbor_slope(stage, velocity, state[:, 0], bed, support, boundary_kind, tailwater)
    slope_x, slope_z = (faces[1] - faces[0], faces[3] - faces[2])
    factor = support['subcell_bed_position_relative_m'].shape[1]
    coordinate = (_i72_np.arange(factor) + 0.5) / factor - 0.5
    x, z = _i72_np.meshgrid(coordinate, coordinate)
    eta_offset = slope_x[:, 0, None, None] * x + slope_z[:, 0, None, None] * z
    effective_bed = support['subcell_bed_position_relative_m'] - eta_offset
    sorted_effective_bed = _i72_np.sort(effective_bed.reshape(len(state), -1), axis=1)
    eta0 = _x28_storage_stages(state[:, 0], sorted_effective_bed, _i72_np.cumsum(sorted_effective_bed, axis=1))
    subdepth = _i72_np.maximum(eta0[:, None, None] - effective_bed, 0.0)
    velocity_offset = slope_x[:, None, None, 1:] * x[None, :, :, None] + slope_z[:, None, None, 1:] * z[None, :, :, None]
    offset_momentum = _i72_np.mean(subdepth[:, :, :, None] * velocity_offset, axis=(1, 2))
    center_velocity = _i72_np.divide(state[:, 1:] - offset_momentum, state[:, 0, None], out=_i72_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    return dict(center=_i72_np.column_stack((eta0, center_velocity)), slope_x=slope_x, slope_z=slope_z, subcell_depth=subdepth, subcell_velocity=center_velocity[:, None, None, :] + velocity_offset)
MUSCL_COARSE_BED_MODEL = 'single-domain-MUSCL-hydrostatic-HLL-SSPRK2-v2'

def _slopes(values, axis):
    result = _i74_np.zeros_like(values)
    if axis == 0:
        result[1:-1] = minmod(values[1:-1] - values[:-2], values[2:] - values[1:-1])
    else:
        result[:, 1:-1] = minmod(values[:, 1:-1] - values[:, :-2], values[:, 2:] - values[:, 1:-1])
    return result

def reconstruct_muscl_coarse(state, bed):
    """Return W/E/N/S states and beds, all with nonnegative face depths."""
    rows, columns = bed.shape
    fields = _i74_np.empty((rows, columns, 4))
    fields[:, :, 0] = state[:, 0].reshape(bed.shape) + bed
    fields[:, :, 1] = bed
    fields[:, :, 2:] = _i74_np.divide(state[:, 1:], state[:, 0, None], out=_i74_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0).reshape(rows, columns, 2)
    sx, sz = (_slopes(fields, 1), _slopes(fields, 0))
    depth = state[:, 0].reshape(bed.shape)
    dry = depth == 0
    sx[dry], sz[dry] = (0.0, 0.0)
    for slope in (sx, sz):
        depth_slope = slope[:, :, 0] - slope[:, :, 1]
        factor = _i74_np.minimum(1.0, _i74_np.divide(2 * depth, abs(depth_slope), out=_i74_np.ones_like(depth), where=depth_slope != 0))
        slope *= factor[:, :, None]
    faces = (fields - 0.5 * sx, fields + 0.5 * sx, fields - 0.5 * sz, fields + 0.5 * sz)
    states, beds = ([], [])
    for face in faces:
        h = _i74_np.maximum(face[:, :, 0] - face[:, :, 1], 0.0)
        states.append(_i74_np.column_stack((h.ravel(), (h[:, :, None] * face[:, :, 2:]).reshape(-1, 2))))
        beds.append(face[:, :, 1].ravel())
    return (states, beds)

def muscl_coarse_bed_rhs(state, bed, *, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
    rows, columns = bed.shape
    count = rows * columns
    grid = _i74_np.arange(count).reshape(rows, columns)
    left = _i74_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    right = _i74_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    axes = _i74_np.r_[_i74_np.zeros(rows * (columns - 1), _i74_np.int64), _i74_np.ones((rows - 1) * columns, _i74_np.int64)]
    cells = _i74_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    boundary_axes = _i74_np.r_[_i74_np.zeros(2 * rows, _i74_np.int64), _i74_np.ones(2 * columns, _i74_np.int64)]
    signs = _i74_np.r_[-_i74_np.ones(rows), _i74_np.ones(rows), -_i74_np.ones(columns), _i74_np.ones(columns)]
    face_states, face_beds = reconstruct_muscl_coarse(state, bed)
    flux = _i74_np.zeros((len(left), 3))
    correction_left, correction_right = (_i74_np.zeros(len(left)), _i74_np.zeros(len(left)))
    maximum_speed = 0.0
    for axis, side_left, side_right in ((0, 1, 0), (1, 3, 2)):
        mask = axes == axis
        f, cl, cr, speeds = hydrostatic_hll(face_states[side_left][left[mask]], face_states[side_right][right[mask]], face_beds[side_left][left[mask]], face_beds[side_right][right[mask]], gravity=gravity, axis=axis)
        flux[mask], correction_left[mask], correction_right[mask] = (f, cl, cr)
        maximum_speed = max(maximum_speed, float(speeds.max(initial=0)))
    boundary_flux = _i74_np.zeros((len(cells), 3))
    boundary_source = _i74_np.zeros_like(boundary_flux)
    for axis, side, begin, end in ((0, 0, 0, rows), (0, 1, rows, 2 * rows), (1, 2, 2 * rows, 2 * rows + columns), (1, 3, 2 * rows + columns, len(cells))):
        selection = slice(begin, end)
        ids, sign = (cells[selection], signs[selection])
        first = face_states[side][ids].copy()
        ghost = first.copy()
        ghost[:, axis + 1] *= -1
        first_bed = face_beds[side][ids]
        ghost_bed = first_bed.copy()
        if boundary_crest is not None:
            opened = boundary_kind[selection] != 0
            ghost_bed[opened] = _i74_np.maximum(ghost_bed[opened], boundary_crest[selection][opened])
        opened = boundary_kind[selection] != 0
        exterior = _i74_np.where(boundary_kind[selection] == 1, ghost_bed, tailwater[selection])
        ghost[opened, 0] = _i74_np.maximum(exterior[opened] - ghost_bed[opened], 0.0)
        ghost[opened, 1:] = 0.0
        first[:, axis + 1] *= sign
        ghost[:, axis + 1] *= sign
        f, cl, _, speed = hydrostatic_hll(first, ghost, first_bed, ghost_bed, gravity=gravity, axis=axis)
        f[:, axis + 1] *= sign
        boundary_flux[selection] = f
        boundary_source[selection, axis + 1] = -cl * sign / spacing
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
    outgoing = _i74_np.bincount(left, weights=_i74_np.maximum(flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i74_np.bincount(right, weights=_i74_np.maximum(-flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i74_np.bincount(cells, weights=_i74_np.maximum(boundary_flux[:, 0], 0) * spacing, minlength=count)
    scales = _i74_np.ones(count)
    limited = outgoing * dt > state[:, 0] * spacing ** 2
    scales[limited] = state[limited, 0] * spacing ** 2 / (outgoing[limited] * dt) * (1 - 1e-12)
    flux *= _i74_np.where(flux[:, 0] >= 0, scales[left], scales[right])[:, None]
    boundary_flux *= _i74_np.where(boundary_flux[:, 0] >= 0, scales[cells], 1.0)[:, None]
    rhs = _i74_np.zeros_like(state)
    for component in range(3):
        _i74_np.add.at(rhs[:, component], left, -flux[:, component] / spacing)
        _i74_np.add.at(rhs[:, component], right, flux[:, component] / spacing)
        _i74_np.add.at(rhs[:, component], cells, -boundary_flux[:, component] / spacing)
    pressure = _i74_np.zeros_like(state)
    _i74_np.add.at(pressure, (left, axes + 1), -correction_left / spacing)
    _i74_np.add.at(pressure, (right, axes + 1), correction_right / spacing)
    for component in (1, 2):
        _i74_np.add.at(pressure[:, component], cells, boundary_source[:, component])
    for axis, low, high in ((0, 0, 1), (1, 2, 3)):
        pressure[:, axis + 1] -= gravity * 0.5 * (face_states[low][:, 0] + face_states[high][:, 0]) * (face_beds[high] - face_beds[low]) / spacing
    rhs += pressure
    return (rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure, maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum())))
SUBGRID_MUSCL_SEGMENTED_HLL_MODEL = 'single-domain-subgrid-MUSCL-storage-segmented-HLL-SSPRK2-v4'

def reconstruct_subgrid_muscl(stage, velocity, depth, bed, support):
    rows, columns = bed.shape
    fields = _i76_np.column_stack((stage, velocity)).reshape(rows, columns, 3)
    sx, sz = (_i76_np.zeros_like(fields), _i76_np.zeros_like(fields))
    sx[:, 1:-1] = minmod(fields[:, 1:-1] - fields[:, :-2], fields[:, 2:] - fields[:, 1:-1])
    sz[1:-1] = minmod(fields[1:-1] - fields[:-2], fields[2:] - fields[1:-1])
    dry = depth.reshape(rows, columns) == 0
    sx[dry], sz[dry] = (0.0, 0.0)
    available = (stage - support['subcell_bed_relative_m'][:, 0]).reshape(rows, columns)
    for slope in (sx, sz):
        ratio = _i76_np.minimum(1.0, _i76_np.divide(2 * available, abs(slope[:, :, 0]), out=_i76_np.ones_like(available), where=slope[:, :, 0] != 0))
        slope *= ratio[:, :, None]
    return [(fields - 0.5 * sx).reshape(-1, 3), (fields + 0.5 * sx).reshape(-1, 3), (fields - 0.5 * sz).reshape(-1, 3), (fields + 0.5 * sz).reshape(-1, 3)]

def subgrid_muscl_segmented_hll_rhs(state, bed, *, support, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
    from terrain_pipeline.fine_subgrid import storage_stages as _x30_storage_stages
    rows, columns = bed.shape
    count = bed.size
    grid = _i76_np.arange(count).reshape(rows, columns)
    left = _i76_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    right = _i76_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    axes = _i76_np.r_[_i76_np.zeros(rows * (columns - 1), _i76_np.int64), _i76_np.ones((rows - 1) * columns, _i76_np.int64)]
    cells = _i76_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    boundary_axes = _i76_np.r_[_i76_np.zeros(2 * rows, _i76_np.int64), _i76_np.ones(2 * columns, _i76_np.int64)]
    signs = _i76_np.r_[-_i76_np.ones(rows), _i76_np.ones(rows), -_i76_np.ones(columns), _i76_np.ones(columns)]
    stage = _x30_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
    velocity = _i76_np.divide(state[:, 1:], state[:, 0, None], out=_i76_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    faces = reconstruct_subgrid_muscl(stage, velocity, state[:, 0], bed, support)
    crests = support['face_segment_crest_relative_m']
    boundary_crests = support['boundary_segment_crest_relative_m'].copy()
    if boundary_crest is not None:
        opened = boundary_kind != 0
        boundary_crests[opened] = _i76_np.maximum(boundary_crests[opened], boundary_crest[opened, None])
    segments = crests.shape[1]
    flux = _i76_np.zeros((len(left), 3))
    boundary_flux = _i76_np.zeros((len(cells), 3))
    pressure_left, pressure_right = (_i76_np.zeros(len(left)), _i76_np.zeros(len(left)))
    pressure_boundary = _i76_np.zeros(len(cells))
    maximum_speed = 0.0
    for axis in (0, 1):
        mask = axes == axis
        crest = crests[mask].ravel()
        reconstructed_left = faces[1 if axis == 0 else 3][left[mask]]
        reconstructed_right = faces[0 if axis == 0 else 2][right[mask]]
        hl = _i76_np.maximum(reconstructed_left[:, 0, None] - crests[mask], 0.0)
        hr = _i76_np.maximum(reconstructed_right[:, 0, None] - crests[mask], 0.0)
        ul = _i76_np.repeat(reconstructed_left[:, 1:], segments, axis=0)
        ur = _i76_np.repeat(reconstructed_right[:, 1:], segments, axis=0)
        ls = _i76_np.column_stack((hl.ravel(), hl.ravel()[:, None] * ul))
        rs = _i76_np.column_stack((hr.ravel(), hr.ravel()[:, None] * ur))
        f, _, _, speed = hydrostatic_hll(ls, rs, crest, crest, gravity=gravity, axis=axis)
        flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        pressure_left[mask] = 0.5 * gravity * _i76_np.mean(_i76_np.maximum(stage[left[mask], None] - crests[mask], 0.0) ** 2, axis=1)
        pressure_right[mask] = 0.5 * gravity * _i76_np.mean(_i76_np.maximum(stage[right[mask], None] - crests[mask], 0.0) ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
        mask = boundary_axes == axis
        crest = boundary_crests[mask]
        boundary_state = _i76_np.empty((mask.sum(), 3))
        negative = signs[mask] < 0
        boundary_state[negative] = faces[0 if axis == 0 else 2][cells[mask][negative]]
        boundary_state[~negative] = faces[1 if axis == 0 else 3][cells[mask][~negative]]
        h = _i76_np.maximum(boundary_state[:, 0, None] - crest, 0.0)
        u = _i76_np.repeat(boundary_state[:, 1:], segments, axis=0)
        sign = _i76_np.repeat(signs[mask], segments)
        first = _i76_np.column_stack((h.ravel(), h.ravel()[:, None] * u))
        ghost = first.copy()
        ghost[:, axis + 1] *= -1
        opened = _i76_np.repeat(boundary_kind[mask] != 0, segments)
        exterior_stage = _i76_np.where(boundary_kind[mask, None] == 1, crest, tailwater[mask, None])
        ghost[opened, 0] = _i76_np.maximum(exterior_stage - crest, 0.0).ravel()[opened]
        ghost[opened, 1:] = 0.0
        first[:, axis + 1] *= sign
        ghost[:, axis + 1] *= sign
        f, _, _, speed = hydrostatic_hll(first, ghost, crest.ravel(), crest.ravel(), gravity=gravity, axis=axis)
        f[:, axis + 1] *= sign
        boundary_flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        pressure_boundary[mask] = 0.5 * gravity * _i76_np.mean(_i76_np.maximum(stage[cells[mask], None] - crest, 0.0) ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
    outgoing = _i76_np.bincount(left, weights=_i76_np.maximum(flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i76_np.bincount(right, weights=_i76_np.maximum(-flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i76_np.bincount(cells, weights=_i76_np.maximum(boundary_flux[:, 0], 0) * spacing, minlength=count)
    scales = _i76_np.ones(count)
    limited = outgoing * dt > state[:, 0] * spacing ** 2
    scales[limited] = state[limited, 0] * spacing ** 2 / (outgoing[limited] * dt) * (1 - 1e-12)
    flux *= _i76_np.where(flux[:, 0] >= 0, scales[left], scales[right])[:, None]
    boundary_flux *= _i76_np.where(boundary_flux[:, 0] >= 0, scales[cells], 1.0)[:, None]
    rhs = _i76_np.zeros_like(state)
    for component in range(3):
        _i76_np.add.at(rhs[:, component], left, -flux[:, component] / spacing)
        _i76_np.add.at(rhs[:, component], right, flux[:, component] / spacing)
        _i76_np.add.at(rhs[:, component], cells, -boundary_flux[:, component] / spacing)
    pressure = _i76_np.zeros_like(state)
    _i76_np.add.at(pressure, (left, axes + 1), pressure_left / spacing)
    _i76_np.add.at(pressure, (right, axes + 1), -pressure_right / spacing)
    _i76_np.add.at(pressure, (cells, boundary_axes + 1), signs * pressure_boundary / spacing)
    rhs += pressure
    return (rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure, maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum())))
LINEAR_STAGE_INDEPENDENT_MODEL = 'single-domain-conservative-linear-stage-subgrid-HLL-SSPRK2-v8'

def linear_stage_independent_rhs(state, bed, *, support, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
    rows, columns = bed.shape
    count = bed.size
    grid = _i80_np.arange(count).reshape(rows, columns)
    left = _i80_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    right = _i80_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    axes = _i80_np.r_[_i80_np.zeros(rows * (columns - 1), _i80_np.int64), _i80_np.ones((rows - 1) * columns, _i80_np.int64)]
    cells = _i80_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    boundary_axes = _i80_np.r_[_i80_np.zeros(2 * rows, _i80_np.int64), _i80_np.ones(2 * columns, _i80_np.int64)]
    signs = _i80_np.r_[-_i80_np.ones(rows), _i80_np.ones(rows), -_i80_np.ones(columns), _i80_np.ones(columns)]
    reconstruction = reconstruct_linear_stage_independent(state, bed, support, boundary_kind, tailwater)
    position_bed = support['subcell_bed_position_relative_m']
    crests = support['face_segment_crest_relative_m']
    boundary_crests = support['boundary_segment_crest_relative_m'].copy()
    if boundary_crest is not None:
        opened = boundary_kind != 0
        boundary_crests[opened] = _i80_np.maximum(boundary_crests[opened], boundary_crest[opened, None])
    segments = crests.shape[1]
    flux = _i80_np.zeros((len(left), 3))
    boundary_flux = _i80_np.zeros((len(cells), 3))
    pressure_left, pressure_right = (_i80_np.zeros(len(left)), _i80_np.zeros(len(left)))
    pressure_boundary = _i80_np.zeros(len(cells))
    maximum_speed = 0.0
    for axis in (0, 1):
        mask = axes == axis
        crest = crests[mask].ravel()
        first_fields = face_fields(reconstruction, left[mask], axis, 1.0, segments)
        second_fields = face_fields(reconstruction, right[mask], axis, -1.0, segments)
        hl = _i80_np.maximum(first_fields[:, :, 0] - crests[mask], 0.0)
        hr = _i80_np.maximum(second_fields[:, :, 0] - crests[mask], 0.0)
        ul = first_fields[:, :, 1:].reshape(-1, 2)
        ur = second_fields[:, :, 1:].reshape(-1, 2)
        ls = _i80_np.column_stack((hl.ravel(), hl.ravel()[:, None] * ul))
        rs = _i80_np.column_stack((hr.ravel(), hr.ravel()[:, None] * ur))
        f, _, _, speed = hydrostatic_hll(ls, rs, crest, crest, gravity=gravity, axis=axis)
        flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        own_left_bed = position_bed[left[mask], :, -1] if axis == 0 else position_bed[left[mask], -1, :]
        own_right_bed = position_bed[right[mask], :, 0] if axis == 0 else position_bed[right[mask], 0, :]
        pressure_left[mask] = 0.5 * gravity * _i80_np.mean(hl ** 2 - _i80_np.maximum(first_fields[:, :, 0] - own_left_bed, 0.0) ** 2, axis=1)
        pressure_right[mask] = 0.5 * gravity * _i80_np.mean(hr ** 2 - _i80_np.maximum(second_fields[:, :, 0] - own_right_bed, 0.0) ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
        mask = boundary_axes == axis
        crest = boundary_crests[mask]
        fields = _i80_np.empty((mask.sum(), segments, 3))
        negative = signs[mask] < 0
        fields[negative] = face_fields(reconstruction, cells[mask][negative], axis, -1.0, segments)
        fields[~negative] = face_fields(reconstruction, cells[mask][~negative], axis, 1.0, segments)
        h = _i80_np.maximum(fields[:, :, 0] - crest, 0.0)
        u = fields[:, :, 1:].reshape(-1, 2)
        sign = _i80_np.repeat(signs[mask], segments)
        first = _i80_np.column_stack((h.ravel(), h.ravel()[:, None] * u))
        ghost = first.copy()
        ghost[:, axis + 1] *= -1
        opened = _i80_np.repeat(boundary_kind[mask] != 0, segments)
        exterior_stage = _i80_np.where(boundary_kind[mask, None] == 1, crest, tailwater[mask, None])
        ghost[opened, 0] = _i80_np.maximum(exterior_stage - crest, 0.0).ravel()[opened]
        ghost[opened, 1:] = 0.0
        first[:, axis + 1] *= sign
        ghost[:, axis + 1] *= sign
        f, _, _, speed = hydrostatic_hll(first, ghost, crest.ravel(), crest.ravel(), gravity=gravity, axis=axis)
        f[:, axis + 1] *= sign
        boundary_flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        own_bed = _i80_np.empty_like(crest)
        if axis == 0:
            own_bed[negative] = position_bed[cells[mask][negative], :, 0]
            own_bed[~negative] = position_bed[cells[mask][~negative], :, -1]
        else:
            own_bed[negative] = position_bed[cells[mask][negative], 0, :]
            own_bed[~negative] = position_bed[cells[mask][~negative], -1, :]
        pressure_boundary[mask] = 0.5 * gravity * _i80_np.mean(h ** 2 - _i80_np.maximum(fields[:, :, 0] - own_bed, 0.0) ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
    outgoing = _i80_np.bincount(left, weights=_i80_np.maximum(flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i80_np.bincount(right, weights=_i80_np.maximum(-flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i80_np.bincount(cells, weights=_i80_np.maximum(boundary_flux[:, 0], 0) * spacing, minlength=count)
    scales = _i80_np.ones(count)
    limited = outgoing * dt > state[:, 0] * spacing ** 2
    scales[limited] = state[limited, 0] * spacing ** 2 / (outgoing[limited] * dt) * (1 - 1e-12)
    flux *= _i80_np.where(flux[:, 0] >= 0, scales[left], scales[right])[:, None]
    boundary_flux *= _i80_np.where(boundary_flux[:, 0] >= 0, scales[cells], 1.0)[:, None]
    rhs = _i80_np.zeros_like(state)
    for component in range(3):
        _i80_np.add.at(rhs[:, component], left, -flux[:, component] / spacing)
        _i80_np.add.at(rhs[:, component], right, flux[:, component] / spacing)
        _i80_np.add.at(rhs[:, component], cells, -boundary_flux[:, component] / spacing)
    pressure = _i80_np.zeros_like(state)
    pressure[:, 1:] = internal_bed_pressure(reconstruction, support, spacing=spacing, gravity=gravity)
    _i80_np.add.at(pressure, (left, axes + 1), pressure_left / spacing)
    _i80_np.add.at(pressure, (right, axes + 1), -pressure_right / spacing)
    _i80_np.add.at(pressure, (cells, boundary_axes + 1), signs * pressure_boundary / spacing)
    rhs += pressure
    return (rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure, reconstruction_center=reconstruction['center'], reconstruction_slope_x=reconstruction['slope_x'], reconstruction_slope_z=reconstruction['slope_z'], maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum())))
CONSERVATIVE_LINEAR_STAGE_MODEL = 'single-domain-conservative-linear-stage-subgrid-HLL-SSPRK2-v9'

def linear_stage_rhs(state, bed, *, support, spacing, gravity, boundary_kind, tailwater, roughness, dt, boundary_crest=None):
    rows, columns = bed.shape
    count = bed.size
    grid = _i81_np.arange(count).reshape(rows, columns)
    left = _i81_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    right = _i81_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    axes = _i81_np.r_[_i81_np.zeros(rows * (columns - 1), _i81_np.int64), _i81_np.ones((rows - 1) * columns, _i81_np.int64)]
    cells = _i81_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    boundary_axes = _i81_np.r_[_i81_np.zeros(2 * rows, _i81_np.int64), _i81_np.ones(2 * columns, _i81_np.int64)]
    signs = _i81_np.r_[-_i81_np.ones(rows), _i81_np.ones(rows), -_i81_np.ones(columns), _i81_np.ones(columns)]
    reconstruction = reconstruct_linear_stage(state, bed, support, boundary_kind, tailwater)
    position_bed = support['subcell_bed_position_relative_m']
    crests = support['face_segment_crest_relative_m']
    boundary_crests = support['boundary_segment_crest_relative_m'].copy()
    if boundary_crest is not None:
        opened = boundary_kind != 0
        boundary_crests[opened] = _i81_np.maximum(boundary_crests[opened], boundary_crest[opened, None])
    segments = crests.shape[1]
    flux = _i81_np.zeros((len(left), 3))
    boundary_flux = _i81_np.zeros((len(cells), 3))
    pressure_left, pressure_right = (_i81_np.zeros(len(left)), _i81_np.zeros(len(left)))
    pressure_boundary = _i81_np.zeros(len(cells))
    maximum_speed = 0.0
    for axis in (0, 1):
        mask = axes == axis
        crest = crests[mask].ravel()
        first_fields = face_fields(reconstruction, left[mask], axis, 1.0, segments)
        second_fields = face_fields(reconstruction, right[mask], axis, -1.0, segments)
        hl = _i81_np.maximum(first_fields[:, :, 0] - crests[mask], 0.0)
        hr = _i81_np.maximum(second_fields[:, :, 0] - crests[mask], 0.0)
        ul = first_fields[:, :, 1:].reshape(-1, 2)
        ur = second_fields[:, :, 1:].reshape(-1, 2)
        ls = _i81_np.column_stack((hl.ravel(), hl.ravel()[:, None] * ul))
        rs = _i81_np.column_stack((hr.ravel(), hr.ravel()[:, None] * ur))
        f, _, _, speed = hydrostatic_hll(ls, rs, crest, crest, gravity=gravity, axis=axis)
        flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        own_left_bed = position_bed[left[mask], :, -1] if axis == 0 else position_bed[left[mask], -1, :]
        own_right_bed = position_bed[right[mask], :, 0] if axis == 0 else position_bed[right[mask], 0, :]
        pressure_left[mask] = 0.5 * gravity * _i81_np.mean(hl ** 2 - _i81_np.maximum(first_fields[:, :, 0] - own_left_bed, 0.0) ** 2, axis=1)
        pressure_right[mask] = 0.5 * gravity * _i81_np.mean(hr ** 2 - _i81_np.maximum(second_fields[:, :, 0] - own_right_bed, 0.0) ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
        mask = boundary_axes == axis
        crest = boundary_crests[mask]
        fields = _i81_np.empty((mask.sum(), segments, 3))
        negative = signs[mask] < 0
        fields[negative] = face_fields(reconstruction, cells[mask][negative], axis, -1.0, segments)
        fields[~negative] = face_fields(reconstruction, cells[mask][~negative], axis, 1.0, segments)
        h = _i81_np.maximum(fields[:, :, 0] - crest, 0.0)
        u = fields[:, :, 1:].reshape(-1, 2)
        sign = _i81_np.repeat(signs[mask], segments)
        first = _i81_np.column_stack((h.ravel(), h.ravel()[:, None] * u))
        ghost = first.copy()
        ghost[:, axis + 1] *= -1
        opened = _i81_np.repeat(boundary_kind[mask] != 0, segments)
        exterior_stage = _i81_np.where(boundary_kind[mask, None] == 1, crest, tailwater[mask, None])
        ghost[opened, 0] = _i81_np.maximum(exterior_stage - crest, 0.0).ravel()[opened]
        ghost[opened, 1:] = 0.0
        first[:, axis + 1] *= sign
        ghost[:, axis + 1] *= sign
        f, _, _, speed = hydrostatic_hll(first, ghost, crest.ravel(), crest.ravel(), gravity=gravity, axis=axis)
        f[:, axis + 1] *= sign
        boundary_flux[mask] = f.reshape(-1, segments, 3).mean(axis=1)
        own_bed = _i81_np.empty_like(crest)
        if axis == 0:
            own_bed[negative] = position_bed[cells[mask][negative], :, 0]
            own_bed[~negative] = position_bed[cells[mask][~negative], :, -1]
        else:
            own_bed[negative] = position_bed[cells[mask][negative], 0, :]
            own_bed[~negative] = position_bed[cells[mask][~negative], -1, :]
        pressure_boundary[mask] = 0.5 * gravity * _i81_np.mean(h ** 2 - _i81_np.maximum(fields[:, :, 0] - own_bed, 0.0) ** 2, axis=1)
        maximum_speed = max(maximum_speed, float(speed.max(initial=0)))
    outgoing = _i81_np.bincount(left, weights=_i81_np.maximum(flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i81_np.bincount(right, weights=_i81_np.maximum(-flux[:, 0], 0) * spacing, minlength=count)
    outgoing += _i81_np.bincount(cells, weights=_i81_np.maximum(boundary_flux[:, 0], 0) * spacing, minlength=count)
    scales = _i81_np.ones(count)
    limited = outgoing * dt > state[:, 0] * spacing ** 2
    scales[limited] = state[limited, 0] * spacing ** 2 / (outgoing[limited] * dt) * (1 - 1e-12)
    flux *= _i81_np.where(flux[:, 0] >= 0, scales[left], scales[right])[:, None]
    boundary_flux *= _i81_np.where(boundary_flux[:, 0] >= 0, scales[cells], 1.0)[:, None]
    rhs = _i81_np.zeros_like(state)
    for component in range(3):
        _i81_np.add.at(rhs[:, component], left, -flux[:, component] / spacing)
        _i81_np.add.at(rhs[:, component], right, flux[:, component] / spacing)
        _i81_np.add.at(rhs[:, component], cells, -boundary_flux[:, component] / spacing)
    pressure = _i81_np.zeros_like(state)
    pressure[:, 1:] = internal_bed_pressure(reconstruction, support, spacing=spacing, gravity=gravity)
    _i81_np.add.at(pressure, (left, axes + 1), pressure_left / spacing)
    _i81_np.add.at(pressure, (right, axes + 1), -pressure_right / spacing)
    _i81_np.add.at(pressure, (cells, boundary_axes + 1), signs * pressure_boundary / spacing)
    rhs += pressure
    return (rhs, dict(internal_flux=flux, boundary_flux=boundary_flux, bed_source=pressure, reconstruction_center=reconstruction['center'], reconstruction_slope_x=reconstruction['slope_x'], reconstruction_slope_z=reconstruction['slope_z'], maximum_wave_speed=maximum_speed, minimum_limiter_factor=float(scales.min(initial=1)), limited_donors=int(limited.sum())))

def advance_muscl_coarse_bed(geometry, **kwargs):
    return advance_no_drag(geometry, rhs=muscl_coarse_bed_rhs, model=MUSCL_COARSE_BED_MODEL, scope='independent FV MUSCL HLL with in-cell bed source and SSPRK2; uncalibrated', physical_limitation='limited MUSCL face reconstruction; coarse cell-mean bed; no calibrated natural certification', **kwargs)

def advance_subgrid_segmented_hll(geometry, **kwargs):
    from terrain_pipeline.fine_subgrid import storage_stages as _x34_storage_stages
    arrays = geometry['arrays']
    support = {name: arrays[name] for name in ('subcell_bed_relative_m', 'subcell_prefix_relative_m', 'face_segment_crest_relative_m', 'boundary_segment_crest_relative_m')}

    def wave_speed(state, gravity):
        stage = _x34_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
        maximum_depth = _i83_np.maximum(stage - support['subcell_bed_relative_m'][:, 0], 0.0)
        velocity = _i83_np.divide(state[:, 1:], state[:, 0, None], out=_i83_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
        return float((abs(velocity).sum(axis=1) + 2 * _i83_np.sqrt(gravity * maximum_depth)).max(initial=0))
    return advance_no_drag(geometry, rhs=_i83_partial(subgrid_segmented_hll_rhs, support=support), model=SUBGRID_SEGMENTED_HLL_MODEL, hydraulic_datum_m=geometry['metadata']['hydraulic_datum_m'], wave_speed=wave_speed, stage_provider=lambda depth: _x34_storage_stages(depth, support['subcell_bed_relative_m'], support['subcell_prefix_relative_m']), face_evaluation_multiplier=support['face_segment_crest_relative_m'].shape[1], scope='independent FV canonical subgrid storage and segmented advective HLL; SSPRK2; uncalibrated', physical_limitation='one velocity vector per coarse cell; segmented pressure support; no calibrated natural certification', **kwargs)

def advance_dry_independent(geometry, **kwargs):
    from terrain_pipeline.fine_subgrid import storage_stages as _x35_storage_stages
    arrays = geometry['arrays']
    support = {name: arrays[name] for name in ('subcell_bed_relative_m', 'subcell_prefix_relative_m', 'face_segment_crest_relative_m', 'boundary_segment_crest_relative_m')}

    def wave_speed(state, gravity):
        stage = _x35_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
        maximum_depth = _i84_np.maximum(stage - support['subcell_bed_relative_m'][:, 0], 0.0)
        velocity = _i84_np.divide(state[:, 1:], state[:, 0, None], out=_i84_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
        return float(1.5 * abs(velocity).sum(axis=1).max(initial=0) + 2 * _i84_np.sqrt(gravity * max(float(stage.max() - support['subcell_bed_relative_m'].min()), 0)))
    return advance_no_drag(geometry, rhs=_i84_partial(dry_independent_rhs, support=support), model=DRY_INDEPENDENT_MODEL, hydraulic_datum_m=geometry['metadata']['hydraulic_datum_m'], wave_speed=wave_speed, stage_provider=lambda depth: _x35_storage_stages(depth, support['subcell_bed_relative_m'], support['subcell_prefix_relative_m']), face_evaluation_multiplier=support['face_segment_crest_relative_m'].shape[1], scope='independent FV canonical subgrid storage and MUSCL segmented advective HLL; SSPRK2; uncalibrated', physical_limitation='one velocity vector per coarse cell; segmented pressure support; no calibrated natural certification', **kwargs)

def advance_dry_neighbor(geometry, **kwargs):
    from terrain_pipeline.fine_subgrid import storage_stages as _x36_storage_stages
    arrays = geometry['arrays']
    support = {name: arrays[name] for name in ('subcell_bed_relative_m', 'subcell_prefix_relative_m', 'face_segment_crest_relative_m', 'boundary_segment_crest_relative_m')}

    def wave_speed(state, gravity):
        stage = _x36_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
        maximum_depth = _i85_np.maximum(stage - support['subcell_bed_relative_m'][:, 0], 0.0)
        velocity = _i85_np.divide(state[:, 1:], state[:, 0, None], out=_i85_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
        return float(1.5 * abs(velocity).sum(axis=1).max(initial=0) + 2 * _i85_np.sqrt(gravity * max(float(stage.max() - support['subcell_bed_relative_m'].min()), 0)))
    return advance_no_drag(geometry, rhs=_i85_partial(dry_neighbor_rhs, support=support), model=DRY_NEIGHBOR_MODEL, hydraulic_datum_m=geometry['metadata']['hydraulic_datum_m'], wave_speed=wave_speed, stage_provider=lambda depth: _x36_storage_stages(depth, support['subcell_bed_relative_m'], support['subcell_prefix_relative_m']), face_evaluation_multiplier=support['face_segment_crest_relative_m'].shape[1], scope='independent FV canonical subgrid storage and MUSCL segmented advective HLL; SSPRK2; uncalibrated', physical_limitation='one velocity vector per coarse cell; segmented pressure support; no calibrated natural certification', **kwargs)

def advance_canonical_manning(geometry, **kwargs):
    from terrain_pipeline.fine_subgrid import storage_stages as _x37_storage_stages
    arrays = geometry['arrays']
    support = {name: arrays[name] for name in ('subcell_bed_relative_m', 'subcell_prefix_relative_m', 'face_segment_crest_relative_m', 'boundary_segment_crest_relative_m')}

    def wave_speed(state, gravity):
        stage = _x37_storage_stages(state[:, 0], support['subcell_bed_relative_m'], support['subcell_prefix_relative_m'])
        maximum_depth = _i86_np.maximum(stage - support['subcell_bed_relative_m'][:, 0], 0.0)
        velocity = _i86_np.divide(state[:, 1:], state[:, 0, None], out=_i86_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
        return float((abs(velocity).sum(axis=1) + 2 * _i86_np.sqrt(gravity * maximum_depth)).max(initial=0))
    return advance_with_drag(geometry, rhs=_i86_partial(subgrid_segmented_hll_rhs, support=support), model=CANONICAL_MANNING_MODEL, hydraulic_datum_m=geometry['metadata']['hydraulic_datum_m'], wave_speed=wave_speed, drag_provider=_i86_partial(manning_damping_canonical, support=support), stage_provider=lambda depth: _x37_storage_stages(depth, support['subcell_bed_relative_m'], support['subcell_prefix_relative_m']), face_evaluation_multiplier=support['face_segment_crest_relative_m'].shape[1], scope='independent FV canonical subgrid storage and segmented advective HLL with canonical Manning; SSPRK2; uncalibrated', physical_limitation='one velocity vector per coarse cell; segmented pressure support; no calibrated natural certification', **kwargs)

def advance_linear_stage(geometry, **kwargs):
    from terrain_pipeline.fine_subgrid import storage_stages as _x38_storage_stages
    arrays, metadata = (geometry['arrays'], geometry['metadata'])
    support = {name: arrays[name] for name in ('subcell_bed_relative_m', 'subcell_prefix_relative_m', 'face_segment_crest_relative_m', 'boundary_segment_crest_relative_m', 'subcell_bed_position_relative_m')}
    datum = metadata['hydraulic_datum_m']
    bed = arrays['H2_m'] - datum
    boundary_provider = kwargs['boundary_stage_provider']
    interval_observer = kwargs['interval_observer']
    current_tail = _i87_np.zeros(len(arrays['boundary_kind']))
    saved_profiles = []

    def profile(state):
        return reconstruct_linear_stage(state, bed, support, arrays['boundary_kind'], current_tail)

    def boundary_stages(index):
        nonlocal current_tail
        stage = boundary_provider(index)
        current_tail = _i87_np.asarray(stage) - datum
        if index == 0:
            initial = _i87_np.asarray(kwargs['initial_depth_m']).ravel()
            saved_profiles.append(profile(_i87_np.column_stack((initial, _i87_np.zeros((bed.size, 2))))))
        return stage

    def observe(packet):
        saved_profiles.append(profile(_i87_np.column_stack((packet['depth_after_m'], packet['momentum_after']))))
        interval_observer(packet)

    def drag(state, dt, gravity, roughness):
        depth = profile(state)['subcell_depth']
        inverse = _i87_np.zeros_like(depth)
        _i87_np.power(depth, -1 / 3, out=inverse, where=depth > 0)
        factor = inverse.mean(axis=(1, 2))
        depth_squared = state[:, 0] ** 2
        denominator = depth_squared + dt * gravity * roughness ** 2 * _i87_np.hypot(state[:, 1], state[:, 2]) * factor
        damping = _i87_np.divide(depth_squared, denominator, out=_i87_np.zeros_like(depth_squared), where=denominator > 0)
        return (damping, factor)

    def wave_speed(state, gravity):
        rec = profile(state)
        maximum_depth = float(rec['subcell_depth'].max(initial=0))
        velocity = float(abs(rec['subcell_velocity']).sum(axis=3).max(initial=0))
        return 2 * velocity + 2 * _i87_np.sqrt(2 * gravity * maximum_depth)
    kwargs['boundary_stage_provider'] = boundary_stages
    kwargs['interval_observer'] = observe
    result = advance_with_reconstruction_witness(geometry, rhs=_i87_partial(linear_stage_rhs, support=support), model=CONSERVATIVE_LINEAR_STAGE_MODEL, hydraulic_datum_m=datum, wave_speed=wave_speed, drag_provider=drag, stage_provider=lambda depth: _x38_storage_stages(depth, support['subcell_bed_relative_m'], support['subcell_prefix_relative_m']), face_evaluation_multiplier=support['face_segment_crest_relative_m'].shape[1], scope='independent FV conservative linear stage/velocity canonical storage; segmented HLL; bed-jump pressure; canonical Manning', physical_limitation='canonical midpoint subcell quadrature; linear profiles; uniform coarse-velocity drag approximation; uncalibrated', **kwargs)
    raw = result['arrays']
    raw['storage_equivalent_stage_relative_m'] = raw.pop('stage_relative_m')
    raw['stage_relative_m'] = _i87_np.asarray([rec['center'][:, 0] for rec in saved_profiles]).reshape(-1, *bed.shape)
    raw['reconstruction_velocity_center_m_s'] = _i87_np.asarray([rec['center'][:, 1:] for rec in saved_profiles]).reshape(-1, *bed.shape, 2)
    raw['reconstruction_slope_x'] = _i87_np.asarray([rec['slope_x'] for rec in saved_profiles]).reshape(-1, *bed.shape, 3)
    raw['reconstruction_slope_z'] = _i87_np.asarray([rec['slope_z'] for rec in saved_profiles]).reshape(-1, *bed.shape, 3)
    raw['canonical_subcell_bed_position_relative_m'] = support['subcell_bed_position_relative_m'].copy()
    factor = support['face_segment_crest_relative_m'].shape[1]
    coordinate = (_i87_np.arange(factor) + 0.5) / factor - 0.5
    x, z = _i87_np.meshgrid(coordinate, coordinate)
    raw['canonical_subcell_positions_local_m'] = _i87_np.stack((x, z), axis=2) * metadata['spacing_m']
    result['metadata']['profile_contract'] = 'eta=eta0+sx*xi+sz*zeta; canonical midpoint h integral=H; h-weighted velocity integral=M; stage_relative is eta0'
    return result
from types import MappingProxyType as _MappingProxyType
PROFILES = _MappingProxyType({'hydrostatic-hll-muscl-none': _MappingProxyType(dict(model=HYDROSTATIC_HLL_MODEL, rhs=shallow_water_rhs_flat, advance=advance_hydrostatic_hll)), 'muscl-coarse-bed': _MappingProxyType(dict(model=MUSCL_COARSE_BED_MODEL, rhs=muscl_coarse_bed_rhs, advance=advance_muscl_coarse_bed)), 'subgrid-segmented-hll': _MappingProxyType(dict(model=SUBGRID_SEGMENTED_HLL_MODEL, rhs=subgrid_segmented_hll_rhs, advance=advance_subgrid_segmented_hll)), 'subgrid-muscl-segmented-hll': _MappingProxyType(dict(model=SUBGRID_MUSCL_SEGMENTED_HLL_MODEL, rhs=subgrid_muscl_segmented_hll_rhs)), 'subgrid-muscl-segmented-hll-dry-independent': _MappingProxyType(dict(model=DRY_INDEPENDENT_MODEL, rhs=dry_independent_rhs, advance=advance_dry_independent)), 'subgrid-muscl-segmented-hll-dry-neighbor': _MappingProxyType(dict(model=DRY_NEIGHBOR_MODEL, rhs=dry_neighbor_rhs, advance=advance_dry_neighbor)), 'subgrid-hll-canonical-manning': _MappingProxyType(dict(model=CANONICAL_MANNING_MODEL, rhs=subgrid_segmented_hll_rhs, advance=advance_canonical_manning)), 'conservative-linear-stage-hll-dry-independent': _MappingProxyType(dict(model=LINEAR_STAGE_INDEPENDENT_MODEL, rhs=linear_stage_independent_rhs, reconstruct=reconstruct_linear_stage_independent)), 'conservative-linear-stage-hll': _MappingProxyType(dict(model=CONSERVATIVE_LINEAR_STAGE_MODEL, rhs=linear_stage_rhs, reconstruct=reconstruct_linear_stage, advance=advance_linear_stage))})
DEFAULT_PROFILE = 'conservative-linear-stage-hll'
MODEL = PROFILES[DEFAULT_PROFILE]['model']

def advance_shallow_water(geometry, *, profile=DEFAULT_PROFILE, **kwargs):
    """Advance using the selected profile; conservative linear stage is default."""
    try:
        selected = PROFILES[profile]
    except (KeyError, TypeError) as error:
        raise ValueError('unknown shallow-water profile: ' + str(profile)) from error
    if 'advance' not in selected:
        raise ValueError('shallow-water profile provides RHS/reconstruction only: ' + str(profile))
    return selected['advance'](geometry, **kwargs)
