"""Consolidated surface_hydraulics implementations; numeric expressions preserved."""
from __future__ import annotations
from dataclasses import dataclass as _i53_dataclass
import math as _i53_math
import time as _i53_time
import numpy as _i53_np
from collections import deque as _i54_deque
from dataclasses import asdict as _i54_asdict
from dataclasses import dataclass as _i54_dataclass
import json as _i54_json
import math as _i54_math
import os as _i54_os
from pathlib import Path as _i54_Path
import tempfile as _i54_tempfile
import heapq as _i54_heapq
import numpy as _i54_np
from dataclasses import dataclass as _i56_dataclass
import heapq as _i56_heapq
import math as _i56_math
import numpy as _i56_np
from dataclasses import asdict as _i57_asdict
from dataclasses import dataclass as _i57_dataclass
import json as _i57_json
import math as _i57_math
import os as _i57_os
from pathlib import Path as _i57_Path
import tempfile as _i57_tempfile
import numpy as _i57_np
from dataclasses import asdict as _i58_asdict
from dataclasses import dataclass as _i58_dataclass
from dataclasses import fields as _i58_fields
import hashlib as _i58_hashlib
import io as _i58_io
import json as _i58_json
import math as _i58_math
import os as _i58_os
from pathlib import Path as _i58_Path
import tempfile as _i58_tempfile
import zipfile as _i58_zipfile
import numpy as _i58_np
import math as _i59_math
import types as _i59_types
import numpy as _i59_np
from numba import njit as _i59_njit
from dataclasses import asdict as _i60_asdict
import numpy as _i60_np
from copy import deepcopy as _i61_deepcopy
import math as _i61_math
import numpy as _i61_np
from dataclasses import dataclass as _i62_dataclass
import math as _i62_math
import numpy as _i62_np
from collections import deque as _i63_deque
import math as _i63_math
import numpy as _i64_np
CATEGORY = 'B'
SCHEMA = 'regional-surface-flat-cell-geometry-v1'
INERTIAL_SCHEMA = 'regional-surface-local-inertial-D4-implicit-new-q-drag-v2'

@_i53_dataclass(frozen=True)
class SurfaceBudget:
    roughness_s_m_third: float = 0.035
    max_dt_s: float = 30.0
    max_cells: int = 65536
    max_substeps: int = 1000000
    max_face_evaluations: int = 100000000000
    max_bytes: int = 256 * 1024 * 1024
    max_duration_s: float = 259200.0
    max_wall_s: float = 7200.0
    max_depth_m: float = 20.0
    max_snapshots: int = 50
    gravity_m_s2: float = 9.81
    inertial_cfl: float = 0.45

def validate_budget(budget):
    if not isinstance(budget, SurfaceBudget):
        raise ValueError('SurfaceBudget required')
    integer_fields = ('max_cells', 'max_substeps', 'max_face_evaluations', 'max_bytes', 'max_snapshots')
    for name in integer_fields:
        value = getattr(budget, name)
        if type(value) is not int or value <= 0:
            raise ValueError('positive integer budget: ' + name)
    for name in set(vars(budget)) - set(integer_fields):
        value = getattr(budget, name)
        if type(value) not in (int, float) or not _i53_math.isfinite(value) or value <= 0:
            raise ValueError('finite positive numeric budget: ' + name)
    if budget.max_snapshots < 3:
        raise ValueError('snapshot/CFL budget')
    if budget.inertial_cfl > 0.45:
        raise ValueError('inertial CFL ceiling')

def prepare_surface_geometry(height_m, *, spacing_m, origin_m_xz, source_identity, boundary_kind=None, boundary_crest_m=None):
    """Every cell and each D4 face retained; boundary sides W/E/N/S are explicit."""
    if not isinstance(height_m, _i53_np.ndarray) or height_m.dtype != _i53_np.float64 or height_m.ndim != 2 or (not 1 <= height_m.size <= 65536) or (not _i53_np.isfinite(height_m).all()) or (type(spacing_m) not in (int, float)) or (not _i53_math.isfinite(spacing_m)) or (spacing_m <= 0):
        raise ValueError('bounded finite original bed and metric spacing required')
    rows, columns = height_m.shape
    origin = _i53_np.asarray(origin_m_xz)
    if origin.shape != (2,) or not _i53_np.isfinite(origin).all() or (not isinstance(source_identity, str)) or (not source_identity):
        raise ValueError('finite center origin and explicit source identity')
    grid = _i53_np.arange(height_m.size, dtype=_i53_np.int64).reshape(height_m.shape)
    donor = _i53_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    receiver = _i53_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    exterior = _i53_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    kinds = _i53_np.zeros(exterior.size, _i53_np.int64) if boundary_kind is None else _i53_np.asarray(boundary_kind)
    crests = height_m.ravel()[exterior].copy() if boundary_crest_m is None else _i53_np.asarray(boundary_crest_m)
    if kinds.shape != exterior.shape or kinds.dtype != _i53_np.int64 or (not _i53_np.isin(kinds, [0, 1, 2]).all()):
        raise ValueError('boundary 0 closed/1 engineering drainage/2 prescribed stage')
    if crests.shape != exterior.shape or crests.dtype != _i53_np.float64 or (not _i53_np.isfinite(crests).all()) or (crests < height_m.ravel()[exterior]).any():
        raise ValueError('boundary crest cannot be below original bed')
    return {'arrays': {'H0_m': height_m.copy(), 'H2_m': height_m.copy(), 'face_left': donor, 'face_right': receiver, 'face_crest_m': _i53_np.maximum(height_m.ravel()[donor], height_m.ravel()[receiver]), 'boundary_cell': exterior, 'boundary_kind': kinds.copy(), 'boundary_crest_m': crests.copy()}, 'metadata': {'schema': SCHEMA, 'spacing_m': float(spacing_m), 'origin_m_xz': list(origin_m_xz), 'source_identity': source_identity, 'shape': list(height_m.shape), 'area_m2': height_m.size * spacing_m ** 2, 'scope': 'full_finite_window_30m_flat_cells_not_natural_basin_or_subgrid_channel', 'boundary_types': ['closed', 'engineering_drainage', 'prescribed_external_stage']}}

def validate_surface_geometry(geometry, *, trusted_height, source_identity):
    arrays, meta = (geometry['arrays'], geometry['metadata'])
    expected_keys = {'H0_m', 'H2_m', 'face_left', 'face_right', 'face_crest_m', 'boundary_cell', 'boundary_kind', 'boundary_crest_m'}
    if set(arrays) != expected_keys:
        raise ValueError('exact geometry array schema')
    if trusted_height.dtype != _i53_np.float64 or trusted_height.ndim != 2 or (not 1 <= trusted_height.size <= 65536) or (not _i53_np.isfinite(trusted_height).all()):
        raise ValueError('trusted finite bounded original bed')
    if meta['schema'] != SCHEMA or meta['source_identity'] != source_identity:
        raise ValueError('regional geometry source mismatch')
    if not _i53_np.array_equal(arrays['H0_m'], trusted_height) or not _i53_np.array_equal(arrays['H2_m'], trusted_height):
        raise ValueError('regional original bed identity')
    rows, columns = trusted_height.shape
    grid = _i53_np.arange(trusted_height.size, dtype=_i53_np.int64).reshape(trusted_height.shape)
    left = _i53_np.r_[grid[:, :-1].ravel(), grid[:-1].ravel()]
    right = _i53_np.r_[grid[:, 1:].ravel(), grid[1:].ravel()]
    if not _i53_np.array_equal(arrays['face_left'], left) or not _i53_np.array_equal(arrays['face_right'], right):
        raise ValueError('all unique D4 shared faces required')
    if not _i53_np.array_equal(arrays['face_crest_m'], _i53_np.maximum(trusted_height.ravel()[left], trusted_height.ravel()[right])):
        raise ValueError('regional shared crest forged')
    boundary = _i53_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]
    shapes = {'H0_m': trusted_height.shape, 'H2_m': trusted_height.shape, 'face_left': left.shape, 'face_right': left.shape, 'face_crest_m': left.shape, 'boundary_cell': boundary.shape, 'boundary_kind': boundary.shape, 'boundary_crest_m': boundary.shape}
    for key, value in arrays.items():
        dtype = _i53_np.int64 if key in {'face_left', 'face_right', 'boundary_cell', 'boundary_kind'} else _i53_np.float64
        if not isinstance(value, _i53_np.ndarray) or value.shape != shapes[key] or value.dtype != dtype:
            raise ValueError('geometry exact shape/dtype: ' + key)
    if type(meta['spacing_m']) not in (int, float) or not _i53_math.isfinite(meta['spacing_m']) or meta['spacing_m'] <= 0:
        raise ValueError('geometry finite metric spacing')
    origin = _i53_np.asarray(meta['origin_m_xz'])
    if origin.shape != (2,) or not _i53_np.isfinite(origin).all():
        raise ValueError('geometry finite center origin')
    if not _i53_np.array_equal(arrays['boundary_cell'], boundary):
        raise ValueError('regional all boundary faces required')
    for value in arrays.values():
        if not isinstance(value, _i53_np.ndarray) or not _i53_np.isfinite(value).all():
            raise ValueError('regional finite arrays')
    if not _i53_np.isin(arrays['boundary_kind'], [0, 1, 2]).all() or (arrays['boundary_crest_m'] < trusted_height.ravel()[boundary]).any():
        raise ValueError('regional boundary certificate')
    if meta['shape'] != list(trusted_height.shape) or meta['area_m2'] != trusted_height.size * meta['spacing_m'] ** 2:
        raise ValueError('regional full area identity')

def _net_flux(geometry, internal, boundary):
    arrays = geometry['arrays']
    count = arrays['H0_m'].size
    net = _i53_np.bincount(arrays['face_right'], weights=internal, minlength=count)
    net -= _i53_np.bincount(arrays['face_left'], weights=internal, minlength=count)
    net -= _i53_np.bincount(arrays['boundary_cell'], weights=boundary, minlength=count)
    return net

def inertial_face_flux(stage_left, stage_right, crest, previous_q, dt_s, spacing_m, distance_m, budget):
    """Actual stage gradient; analytic implicit new-discharge Manning drag."""
    flow_depth = _i53_np.maximum(_i53_np.maximum(stage_left, stage_right) - crest, 0.0)
    wet = flow_depth > 0
    discharge_per_width = previous_q / spacing_m
    updated = _i53_np.zeros_like(previous_q)
    numerator = discharge_per_width[wet] - budget.gravity_m_s2 * flow_depth[wet] * dt_s * (stage_right[wet] - stage_left[wet]) / distance_m
    friction = budget.gravity_m_s2 * dt_s * budget.roughness_s_m_third ** 2 / flow_depth[wet] ** (7 / 3)
    updated[wet] = spacing_m * 2 * numerator / (1 + _i53_np.sqrt(1 + 4 * friction * _i53_np.abs(numerator)))
    return (updated, flow_depth)

def limited_inertial_fluxes(geometry, depth, previous_internal, previous_boundary, tailwater, forcing, dt_s, budget):
    arrays = geometry['arrays']
    stage = arrays['H2_m'].ravel() + depth
    spacing = geometry['metadata']['spacing_m']
    left, right, cells = (arrays['face_left'], arrays['face_right'], arrays['boundary_cell'])
    internal, _ = inertial_face_flux(stage[left], stage[right], arrays['face_crest_m'], previous_internal, dt_s, spacing, spacing, budget)
    exterior = _i53_np.where(arrays['boundary_kind'] == 1, arrays['boundary_crest_m'], tailwater)
    boundary, _ = inertial_face_flux(stage[cells], exterior, arrays['boundary_crest_m'], previous_boundary, dt_s, spacing, spacing / 2, budget)
    boundary[arrays['boundary_kind'] == 0] = 0.0
    outgoing = _i53_np.bincount(left, weights=_i53_np.maximum(internal, 0), minlength=depth.size)
    outgoing += _i53_np.bincount(right, weights=_i53_np.maximum(-internal, 0), minlength=depth.size)
    outgoing += _i53_np.bincount(cells, weights=_i53_np.maximum(boundary, 0), minlength=depth.size)
    available = depth * spacing ** 2 + dt_s * forcing
    factor = _i53_np.ones(depth.size)
    limiting = outgoing * dt_s > available
    factor[limiting] = available[limiting] / (outgoing[limiting] * dt_s)
    factor[limiting] *= 1 - 1e-12
    raw_internal, raw_boundary = (internal.copy(), boundary.copy())
    internal *= _i53_np.where(internal >= 0, factor[left], factor[right])
    boundary *= _i53_np.where(boundary >= 0, factor[cells], 1.0)
    removed = float((_i53_np.abs(raw_internal - internal).sum() + _i53_np.abs(raw_boundary - boundary).sum()) * dt_s)
    raw_volume = float((_i53_np.abs(raw_internal).sum() + _i53_np.abs(raw_boundary).sum()) * dt_s)
    return (internal, boundary, {'limited_donors': int(limiting.sum()), 'removed_transfer_m3': removed, 'raw_transfer_m3': raw_volume, 'minimum_factor': float(factor.min()), 'trigger': 'sum_outgoing_dt_exceeds_donor_volume_plus_local_input'})

def advance_inertial_surface(geometry, *, initial_depth_m, forcing_interval_s, intervals, forcing_provider, boundary_stage_provider, source_identity, forcing_identity, budget=SurfaceBudget(), snapshot_interval_s=900.0, interval_observer=None, momentum_observer=None):
    """Full-grid local inertia, no advective momentum, conservative limited shared Q."""
    validate_budget(budget)
    arrays, meta = (geometry['arrays'], geometry['metadata'])
    validate_surface_geometry(geometry, trusted_height=arrays['H0_m'], source_identity=source_identity)
    if type(intervals) is not int or intervals < 1 or type(forcing_interval_s) not in (int, float) or (not _i53_math.isfinite(forcing_interval_s)) or (forcing_interval_s <= 0):
        raise ValueError('inertial forcing time dimensions')
    duration = intervals * forcing_interval_s
    if duration > budget.max_duration_s or arrays['H0_m'].size > budget.max_cells:
        raise ValueError('inertial duration/cell budget')
    if type(snapshot_interval_s) not in (int, float) or not _i53_math.isfinite(snapshot_interval_s) or snapshot_interval_s <= 0:
        raise ValueError('inertial snapshot interval')
    initial = _i53_np.asarray(initial_depth_m)
    if initial.shape != arrays['H0_m'].shape or initial.dtype != _i53_np.float64 or (not _i53_np.isfinite(initial).all()) or (initial < 0).any() or (initial > budget.max_depth_m).any():
        raise ValueError('inertial initial water shape/finite/depth')
    snapshot_interval_s = max(snapshot_interval_s, duration / (budget.max_snapshots - 2))
    estimate = (budget.max_snapshots * 2 + 40) * initial.size * 8
    if estimate > budget.max_bytes:
        raise ValueError('inertial memory preflight')
    depth = initial.ravel().copy()
    internal = _i53_np.zeros(arrays['face_left'].size)
    boundary = _i53_np.zeros(arrays['boundary_cell'].size)
    spacing = meta['spacing_m']
    area = spacing ** 2
    time_s = 0.0
    next_snapshot = snapshot_interval_s
    snapshots, times = ([depth.copy()], [0.0])
    initial_volume = float(depth.sum() * area)
    supplied = imported = exported = 0.0
    ledgers = [[0.0, 0.0, 0.0, initial_volume, 0.0]]
    accepted = evaluations = rejected = 0
    limiter_count = 0
    removed_total = raw_total = 0.0
    minimum_factor = 1.0
    minimum_dt = _i53_math.inf
    maximum_dt = maximum_depth = max_cell_error = absolute_cell_error = 0.0
    max_velocity = max_froude = 0.0
    high_froude_faces = shallow_faces = 0
    wall = _i53_time.monotonic()
    failure = None
    for interval in range(intervals):
        forcing = _i53_np.asarray(forcing_provider(interval))
        tailwater = _i53_np.asarray(boundary_stage_provider(interval))
        if forcing.shape != initial.shape or forcing.dtype != _i53_np.float64 or (not _i53_np.isfinite(forcing).all()) or (forcing < 0).any():
            raise ValueError('full-grid m3/s forcing required')
        if tailwater.shape != boundary.shape or tailwater.dtype != _i53_np.float64 or (not _i53_np.isfinite(tailwater).all()):
            raise ValueError('inertial tailwater finite shape')
        forcing = forcing.ravel()
        start_depth = depth.copy()
        start_time = time_s
        transfers = _i53_np.zeros_like(internal)
        external_transfers = _i53_np.zeros_like(boundary)
        delivered = _i53_np.zeros_like(depth)
        before_q, before_boundary = (internal.copy(), boundary.copy())
        interval_end = (interval + 1) * forcing_interval_s
        while time_s < interval_end - 1e-09:
            face_count = internal.size + boundary.size
            if accepted >= budget.max_substeps or evaluations + face_count > budget.max_face_evaluations or _i53_time.monotonic() - wall >= budget.max_wall_s:
                failure = {'reason': 'inertial_resource_budget_refused', 'time_s': time_s, 'interval': interval}
                break
            stage = arrays['H2_m'].ravel() + depth
            exterior = _i53_np.where(arrays['boundary_kind'] == 1, arrays['boundary_crest_m'], tailwater)
            boundary_depth = _i53_np.maximum(exterior - arrays['boundary_crest_m'], 0.0)
            max_wet_depth = max(float(depth.max()), float(boundary_depth[arrays['boundary_kind'] != 0].max(initial=0)))
            gravity_dt = budget.inertial_cfl * (spacing / 2) / _i53_math.sqrt(budget.gravity_m_s2 * max_wet_depth) if max_wet_depth else _i53_math.inf
            dt = min(budget.max_dt_s, gravity_dt, interval_end - time_s, next_snapshot - time_s)
            if dt <= 0 or not _i53_math.isfinite(dt):
                failure = {'reason': 'inertial_timestep_failure', 'time_s': time_s}
                break
            next_internal, next_boundary, limiting = limited_inertial_fluxes(geometry, depth, internal, boundary, tailwater, forcing, dt, budget)
            evaluations += face_count
            flow_depth = _i53_np.maximum(_i53_np.maximum(stage[arrays['face_left']], stage[arrays['face_right']]) - arrays['face_crest_m'], 0.0)
            evaluable = flow_depth >= 0.001
            if evaluable.any():
                velocity = _i53_np.abs(next_internal[evaluable]) / (spacing * flow_depth[evaluable])
                froude = velocity / _i53_np.sqrt(budget.gravity_m_s2 * flow_depth[evaluable])
                max_velocity = max(max_velocity, float(velocity.max()))
                max_froude = max(max_froude, float(froude.max()))
                high_froude_faces += int((froude > 1).sum())
            shallow_faces += int(((flow_depth > 0) & ~evaluable).sum())
            net = _net_flux(geometry, next_internal, next_boundary)
            updated = depth + dt * (forcing + net) / area
            if not _i53_np.isfinite(updated).all() or (updated < 0).any() or (updated > budget.max_depth_m).any():
                failure = {'reason': 'inertial_depth_or_positivity_refused_no_clip', 'time_s': time_s, 'attempted_max_depth_m': float(updated.max())}
                rejected += 1
                break
            residual = area * (updated - depth) - dt * (forcing + net)
            if momentum_observer is not None and time_s == start_time:
                momentum_observer({'interval': interval, 'time_start_s': time_s, 'dt_s': dt, 'depth_before_m': depth.copy(), 'depth_after_m': updated.copy(), 'forcing_m3_s': forcing.copy(), 'tailwater_m': tailwater.copy(), 'internal_q_before_m3_s': internal.copy(), 'boundary_q_before_m3_s': boundary.copy(), 'internal_q_after_m3_s': next_internal.copy(), 'boundary_q_after_m3_s': next_boundary.copy(), 'limiter': limiting.copy()})
            max_cell_error = max(max_cell_error, float(_i53_np.abs(residual).max()))
            absolute_cell_error += float(_i53_np.abs(residual).sum())
            limiter_count += limiting['limited_donors']
            removed_total += limiting['removed_transfer_m3']
            raw_total += limiting['raw_transfer_m3']
            minimum_factor = min(minimum_factor, limiting['minimum_factor'])
            depth, internal, boundary = (updated, next_internal, next_boundary)
            transfers += dt * internal
            external_transfers += dt * boundary
            delivered += dt * forcing
            supplied += float(forcing.sum() * dt)
            imported += float(_i53_np.maximum(-boundary, 0).sum() * dt)
            exported += float(_i53_np.maximum(boundary, 0).sum() * dt)
            time_s += dt
            accepted += 1
            minimum_dt = min(minimum_dt, dt)
            maximum_dt = max(maximum_dt, dt)
            maximum_depth = max(maximum_depth, float(depth.max()))
            if time_s >= next_snapshot - 1e-09:
                snapshots.append(depth.copy())
                times.append(time_s)
                volume = float(depth.sum() * area)
                ledgers.append([supplied, imported, exported, volume, volume - initial_volume - supplied - imported + exported])
                next_snapshot += snapshot_interval_s
        if interval_observer is not None and time_s > start_time:
            interval_observer({'interval': interval, 'time_start_s': start_time, 'time_end_s': time_s, 'depth_before_m': start_depth, 'depth_after_m': depth.copy(), 'internal_transfer_m3': transfers, 'boundary_transfer_m3': external_transfers, 'forcing_volume_m3': delivered, 'internal_q_before_m3_s': before_q, 'internal_q_after_m3_s': internal.copy(), 'boundary_q_before_m3_s': before_boundary, 'boundary_q_after_m3_s': boundary.copy()})
        if failure is not None:
            break
    if times[-1] != time_s:
        snapshots.append(depth.copy())
        times.append(time_s)
        volume = float(depth.sum() * area)
        ledgers.append([supplied, imported, exported, volume, volume - initial_volume - supplied - imported + exported])
    return {'metadata': {'schema': INERTIAL_SCHEMA, 'source_identity': source_identity, 'forcing_identity': forcing_identity, 'status': 'completed' if failure is None else 'refused', 'failure': failure, 'budget': vars(budget), 'requested_time_s': duration, 'committed_time_s': time_s, 'substeps': accepted, 'face_evaluations': evaluations, 'wall_s': _i53_time.monotonic() - wall, 'estimated_peak_bytes': estimate, 'initial_volume_m3': initial_volume, 'supplied_m3': supplied, 'boundary_input_m3': imported, 'boundary_output_m3': exported, 'final_volume_m3': float(depth.sum() * area), 'scope': 'full_finite_computational_region_local_inertia_no_advection_not_full_Saint_Venant'}, 'arrays': {'time_s': _i53_np.asarray(times), 'depth_m': _i53_np.asarray(snapshots).reshape(-1, *initial.shape), 'initial_depth_m': initial.copy(), 'ledger': _i53_np.asarray(ledgers), 'final_internal_q_m3_s': internal, 'final_boundary_q_m3_s': boundary}, 'diagnostics': {'minimum_dt_s': minimum_dt if accepted else None, 'maximum_dt_s': maximum_dt, 'maximum_depth_m': maximum_depth, 'max_cell_residual_m3': max_cell_error, 'sum_absolute_cell_residual_m3': absolute_cell_error, 'limited_donor_count': limiter_count, 'removed_transfer_m3': removed_total, 'raw_transfer_m3': raw_total, 'removed_fraction': removed_total / raw_total if raw_total else 0.0, 'minimum_limiter_factor': minimum_factor, 'negative_water_clip_count': 0, 'rejected_trials': rejected, 'max_face_velocity_m_s': max_velocity, 'max_face_froude': max_froude, 'supercritical_face_evaluations': high_froude_faces, 'shallow_face_evaluations': shallow_faces, 'froude_minimum_evaluation_depth_m': 0.001, 'physical_limitation': 'no_advective_momentum_steep_supercritical_flow_not_full_shallow_water_certification'}}
VERSION = 'channel-inundation-v1'

@_i54_dataclass(frozen=True)
class InundationRecipe:
    min_water_depth_m: float = 0.01
    max_lateral_reach_m: float = 30.0

    def __post_init__(self):
        if not _i54_math.isfinite(self.min_water_depth_m) or self.min_water_depth_m <= 0 or (not _i54_math.isfinite(self.max_lateral_reach_m)) or (self.max_lateral_reach_m <= 0):
            raise ValueError('inundation depth and reach must be finite and positive')

def _shared_stage_fields(plan, section, stage, centerline, reach_m):
    """Nearest shared segment supplies a local stage ceiling and wet channel seeds."""
    params = section['identity']['parameters']
    coarse = plan['identity']['parameters']
    shape = section['arrays']['bounded_surface_m'].shape
    gx, gz = _i54_np.meshgrid(params['origin_x_m'] + _i54_np.arange(shape[1]) * params['spacing_x_m'], params['origin_z_m'] + _i54_np.arange(shape[0]) * params['spacing_z_m'])
    node_stage = stage['arrays']['stage_m'].ravel()
    active = stage['arrays']['channel_mask'].ravel()
    receiver = plan['arrays']['receiver']
    width = plan['arrays']['nominal_width_m'].ravel()
    cols = plan['arrays']['source_height_m'].shape[1]
    if centerline is None:
        positions = _i54_np.column_stack((coarse['origin_x_m'] + _i54_np.arange(receiver.size) % cols * coarse['spacing_x_m'], coarse['origin_z_m'] + _i54_np.arange(receiver.size) // cols * coarse['spacing_z_m']))
    else:
        from terrain_pipeline.channel_geometry import validate_centerline_for_plan as validate_centerline_for_plan
        validate_centerline_for_plan(centerline, plan)
        positions = _i54_np.full((receiver.size, 2), _i54_np.nan)
        positions[centerline['arrays']['node_flat_index']] = centerline['arrays']['node_world_xz_m']
    nearest_distance = _i54_np.full(shape, _i54_np.inf)
    ceiling = _i54_np.full(shape, -_i54_np.inf)
    nearest_radius = _i54_np.zeros(shape)
    seed = _i54_np.zeros(shape, bool)
    for cell in _i54_np.flatnonzero(active):
        target = int(receiver[cell])
        if target < 0 or not active[target]:
            continue
        ax, az = positions[cell]
        bx, bz = positions[target]
        radius = max(width[cell], width[target]) / 2
        reach = radius + reach_m
        if max(ax, bx) + reach < gx[0, 0] or min(ax, bx) - reach > gx[0, -1] or max(az, bz) + reach < gz[0, 0] or (min(az, bz) - reach > gz[-1, 0]):
            continue
        length2 = (bx - ax) ** 2 + (bz - az) ** 2
        t = _i54_np.clip(((gx - ax) * (bx - ax) + (gz - az) * (bz - az)) / length2, 0.0, 1.0)
        distance = _i54_np.hypot(gx - (ax + t * (bx - ax)), gz - (az + t * (bz - az)))
        local_stage = (1 - t) * node_stage[cell] + t * node_stage[target]
        nearer = distance < nearest_distance - 1e-09
        nearest_distance[nearer] = distance[nearer]
        ceiling[nearer] = local_stage[nearer]
        local_radius = ((1 - t) * width[cell] + t * width[target]) / 2
        nearest_radius[nearer] = local_radius[nearer]
        seed |= distance <= _i54_np.maximum(local_radius / 2, min(params['spacing_x_m'], params['spacing_z_m']) / 2)
    graph_samples = []
    graph_covered = True
    for cell in _i54_np.flatnonzero(active):
        px, pz = positions[cell]
        if px < gx[0, 0] - 1e-09 or px > gx[0, -1] + 1e-09 or pz < gz[0, 0] - 1e-09 or (pz > gz[-1, 0] + 1e-09):
            graph_covered = False
            break
    if graph_covered:
        for cell in _i54_np.flatnonzero(active):
            target = int(receiver[cell])
            if target < 0 or not active[target]:
                continue
            ax, az = positions[cell]
            bx, bz = positions[target]
            samples = max(2, int(_i54_math.ceil(_i54_math.hypot(bx - ax, bz - az) / min(params['spacing_x_m'], params['spacing_z_m']))))
            for t in _i54_np.linspace(0.0, 1.0, samples + 1):
                x = int(round((ax + t * (bx - ax) - params['origin_x_m']) / params['spacing_x_m']))
                z = int(round((az + t * (bz - az) - params['origin_z_m']) / params['spacing_z_m']))
                if not (0 <= x < shape[1] and 0 <= z < shape[0] and seed[z, x]):
                    graph_covered = False
                    break
                graph_samples.append((z, x))
            if not graph_covered:
                break
    return (ceiling, seed, nearest_distance, nearest_radius, graph_covered, graph_samples)

def evaluate_inundation(plan, section, stage, domain_mask, protected_mask, legal_outlet_mask, recipe: InundationRecipe, centerline=None):
    """Solve full fine-grid flood once, gating lateral water by local river stage."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i54_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i54_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i54_digest
    if not isinstance(recipe, InundationRecipe):
        raise ValueError('inundation recipe required')
    section_identity = _i54_ArtifactIdentity(**section['identity'])
    stage_identity = _i54_ArtifactIdentity(**stage['identity'])
    if section_identity.sha256 != section['identity_sha256'] or stage_identity.sha256 != stage['identity_sha256']:
        raise ValueError('section or stage identity mismatch')
    surface = section['arrays']['bounded_surface_m']
    shape = surface.shape
    domain = _i54_np.asarray(domain_mask)
    protected = _i54_np.asarray(protected_mask)
    legal_outlet = _i54_np.asarray(legal_outlet_mask)
    if domain.shape != shape or protected.shape != shape or domain.dtype != bool or (protected.dtype != bool) or (legal_outlet.shape != shape) or (legal_outlet.dtype != bool) or (not _i54_np.isfinite(surface).all()):
        raise ValueError('domain, protection and bounded surface must match finite full grid')
    if section['identity']['parameters']['plan_identity_sha256'] != plan['identity_sha256'] or stage['identity']['parameters']['plan_identity_sha256'] != plan['identity_sha256'] or (centerline is None) != (section['identity']['parameters'].get('centerline_identity_sha256') is None) or (centerline is not None and section['identity']['parameters']['centerline_identity_sha256'] != centerline['identity_sha256']) or (stage['identity']['parameters'].get('centerline_identity_sha256') != (centerline['identity_sha256'] if centerline is not None else None)):
        raise ValueError('section, stage and centerline must use the same shared plan')
    if stage['arrays']['channel_mask'].shape != plan['arrays']['source_height_m'].shape:
        raise ValueError('stage and plan grid mismatch')
    section_arrays = section['arrays']
    section_params = section_identity.record()['parameters']
    section_recipe_cap = section_params['max_local_cut_m']
    source = section_arrays['source_surface_m']
    actual = section_arrays['actual_cut_m']
    required = section_arrays['required_cut_m']
    if source.shape != shape or actual.shape != shape or required.shape != shape or (_i54_array_hash(source) != section_params['source_surface_sha256']) or (not _i54_np.isfinite(source).all()) or (not _i54_np.isfinite(actual).all()) or (not _i54_np.isfinite(required).all()) or _i54_np.any(actual < -1e-09) or _i54_np.any(actual > required + 1e-09) or _i54_np.any(actual > section_recipe_cap + 1e-09) or _i54_np.any(actual[section_arrays['protected_mask']] > 1e-09) or (not _i54_np.allclose(surface, source - actual, atol=1e-09, rtol=0)):
        raise ValueError('section bounded surface differs from validated cut')
    stage_params = stage_identity.record()['parameters']
    stage_arrays = stage['arrays']
    if _i54_digest({name: _i54_array_hash(_i54_np.ascontiguousarray(value)) for name, value in stage_arrays.items()}) != stage_params['stage_output_sha256']:
        raise ValueError('stage output differs from identity')
    ceiling, seed, distance, radius, whole_graph_covered, graph_samples = _shared_stage_fields(plan, section, stage, centerline, recipe.max_lateral_reach_m)
    rows, cols = shape
    potential_seed = seed & (ceiling > surface + recipe.min_water_depth_m)
    seed = potential_seed & domain & ~protected
    water = _i54_np.full(shape, _i54_np.nan)
    reachable = _i54_np.zeros(shape, bool)
    protected_conflict = potential_seed & protected
    boundary_contact = _i54_np.zeros(shape, bool)
    queue = _i54_deque(map(tuple, _i54_np.argwhere(seed)))
    for z, x in queue:
        reachable[z, x] = True
    while queue:
        z, x = queue.popleft()
        for nz, nx in ((z - 1, x), (z + 1, x), (z, x - 1), (z, x + 1)):
            if not (0 <= nz < rows and 0 <= nx < cols):
                if not legal_outlet[z, x]:
                    boundary_contact[z, x] = True
                continue
            if distance[nz, nx] > recipe.max_lateral_reach_m + 1e-09:
                continue
            if ceiling[nz, nx] <= surface[nz, nx] + recipe.min_water_depth_m:
                continue
            if not domain[nz, nx]:
                boundary_contact[nz, nx] = True
                continue
            if protected[nz, nx]:
                protected_conflict[nz, nx] = True
                continue
            if not reachable[nz, nx]:
                reachable[nz, nx] = True
                queue.append((nz, nx))
    water[reachable] = ceiling[reachable]
    boundary = _i54_np.zeros(shape, bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    boundary_contact |= reachable & boundary & ~legal_outlet
    reach_limited = _i54_np.zeros(shape, bool)
    for z, x in _i54_np.argwhere(reachable):
        for nz, nx in ((z - 1, x), (z + 1, x), (z, x - 1), (z, x + 1)):
            if 0 <= nz < rows and 0 <= nx < cols and (distance[nz, nx] > recipe.max_lateral_reach_m + 1e-09) and (ceiling[nz, nx] > surface[nz, nx] + recipe.min_water_depth_m) and domain[nz, nx] and (not protected[nz, nx]):
                reach_limited[z, x] = True
    outlet_covered = bool(_i54_np.any(reachable & legal_outlet))
    wet_to_outlet = _i54_np.zeros(shape, bool)
    queue = _i54_deque(map(tuple, _i54_np.argwhere(reachable & legal_outlet)))
    for z, x in queue:
        wet_to_outlet[z, x] = True
    while queue:
        z, x = queue.popleft()
        for nz, nx in ((z - 1, x), (z + 1, x), (z, x - 1), (z, x + 1)):
            if 0 <= nz < rows and 0 <= nx < cols and reachable[nz, nx] and (not wet_to_outlet[nz, nx]):
                wet_to_outlet[nz, nx] = True
                queue.append((nz, nx))
    disconnected_seed = seed & ~wet_to_outlet
    whole_graph_covered &= all((wet_to_outlet[z, x] for z, x in graph_samples))
    high_to_low_incompatibility = _i54_np.zeros(shape, bool)
    for dz, dx in ((1, 0), (0, 1)):
        first = reachable[:rows - dz, :cols - dx]
        second = reachable[dz:, dx:]
        mismatch = first & second & (_i54_np.abs(ceiling[:rows - dz, :cols - dx] - ceiling[dz:, dx:]) > max(0.5, recipe.min_water_depth_m * 10))
        high_to_low_incompatibility[:rows - dz, :cols - dx] |= mismatch
    identity = _i54_ArtifactIdentity('Terragenesis', 'channel-inundation', VERSION, 0, {**_i54_asdict(recipe), 'section_identity_sha256': section['identity_sha256'], 'stage_identity_sha256': stage['identity_sha256'], 'domain_sha256': _i54_array_hash(domain), 'protected_sha256': _i54_array_hash(protected), 'legal_outlet_sha256': _i54_array_hash(legal_outlet), 'water_sha256': _i54_array_hash(water), 'section_arrays_sha256': _i54_digest({name: _i54_array_hash(_i54_np.ascontiguousarray(value)) for name, value in section_arrays.items()}), 'stage_output_sha256': stage_params['stage_output_sha256'], 'whole_graph_covered': whole_graph_covered})
    overbank = reachable & (distance > radius + 1e-09)
    arrays = {'water_surface_m': water, 'wet_mask': reachable, 'overbank_mask': overbank, 'protected_conflict_mask': protected_conflict, 'boundary_contact_mask': boundary_contact, 'reach_limited_mask': reach_limited, 'disconnected_seed_mask': disconnected_seed, 'stage_mismatch_mask': high_to_low_incompatibility, 'domain_mask': domain.copy(), 'protected_mask': protected.copy(), 'legal_outlet_mask': legal_outlet.copy(), 'channel_seed_mask': seed}
    identity_params = identity.record()['parameters']
    identity_params['all_arrays_sha256'] = _i54_digest({name: _i54_array_hash(_i54_np.ascontiguousarray(value)) for name, value in arrays.items()})
    identity = _i54_ArtifactIdentity('Terragenesis', 'channel-inundation', VERSION, 0, identity_params)
    for value in arrays.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': 'diagnostic_not_publishable', 'arrays': arrays, 'summary': {'wet_nodes': int(_i54_np.count_nonzero(reachable)), 'overbank_nodes': int(_i54_np.count_nonzero(overbank)), 'protected_conflict_nodes': int(_i54_np.count_nonzero(protected_conflict)), 'boundary_contact_nodes': int(_i54_np.count_nonzero(boundary_contact)), 'reach_limited_nodes': int(_i54_np.count_nonzero(reach_limited)), 'stage_mismatch_nodes': int(_i54_np.count_nonzero(high_to_low_incompatibility)), 'channel_seed_nodes': int(_i54_np.count_nonzero(seed)), 'disconnected_seed_nodes': int(_i54_np.count_nonzero(disconnected_seed)), 'whole_graph_covered': whole_graph_covered, 'legal_outlet_wet': outlet_covered, 'coverage_complete': whole_graph_covered and outlet_covered and (not bool(_i54_np.any(disconnected_seed | boundary_contact | reach_limited)))}}

def slice_inundation(result, z_slice, x_slice):
    """Read-only storage window from one full-grid inundation result."""
    return {name: value[z_slice, x_slice] for name, value in result['arrays'].items()}

def save_inundation(result, path):
    from terrain_pipeline.artifacts.contracts import array_hash as _i54_array_hash
    destination = _i54_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ('identity', 'identity_sha256', 'status', 'summary')}
    record['format_version'] = 1
    record['array_sha256'] = {name: _i54_array_hash(_i54_np.ascontiguousarray(value)) for name, value in result['arrays'].items()}
    temporary = None
    try:
        with _i54_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, prefix=f'.{destination.name}-', suffix='.npz', delete=False) as stream:
            temporary = _i54_Path(stream.name)
            _i54_np.savez_compressed(stream, manifest=_i54_json.dumps(record, sort_keys=True), **result['arrays'])
        load_inundation(temporary)
        _i54_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def load_inundation(path):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i54_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i54_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i54_digest
    expected = {'water_surface_m', 'wet_mask', 'overbank_mask', 'protected_conflict_mask', 'boundary_contact_mask', 'reach_limited_mask', 'stage_mismatch_mask', 'disconnected_seed_mask', 'domain_mask', 'protected_mask', 'legal_outlet_mask', 'channel_seed_mask'}
    with _i54_np.load(path, allow_pickle=False) as archive:
        record = _i54_json.loads(str(archive['manifest'].item()))
        if set(archive.files) != expected | {'manifest'} or set(record['array_sha256']) != expected:
            raise ValueError('invalid inundation array set')
        arrays = {name: archive[name].copy() for name in expected}
    identity = _i54_ArtifactIdentity(**record['identity'])
    if identity.sha256 != record['identity_sha256'] or identity.algorithm != 'channel-inundation' or identity.algorithm_version != VERSION or (record['format_version'] != 1) or (record['status'] != 'diagnostic_not_publishable') or any((_i54_array_hash(_i54_np.ascontiguousarray(arrays[name])) != hash_value for name, hash_value in record['array_sha256'].items())):
        raise ValueError('invalid inundation identity or hashes')
    shape = arrays['water_surface_m'].shape
    if len(shape) != 2 or min(shape) < 2 or arrays['water_surface_m'].dtype != _i54_np.float64 or any((arrays[name].shape != shape or arrays[name].dtype != bool for name in expected - {'water_surface_m'})) or (not _i54_np.isfinite(arrays['water_surface_m'][arrays['wet_mask']]).all()):
        raise ValueError('invalid inundation arrays')
    params = identity.record()['parameters']
    InundationRecipe(params['min_water_depth_m'], params['max_lateral_reach_m'])
    if _i54_array_hash(arrays['domain_mask']) != params['domain_sha256'] or _i54_array_hash(arrays['protected_mask']) != params['protected_sha256'] or _i54_array_hash(arrays['legal_outlet_mask']) != params['legal_outlet_sha256'] or (_i54_array_hash(arrays['water_surface_m']) != params['water_sha256']):
        raise ValueError('inundation domain or protection differs from identity')
    if _i54_digest({name: _i54_array_hash(_i54_np.ascontiguousarray(value)) for name, value in arrays.items()}) != params['all_arrays_sha256']:
        raise ValueError('inundation arrays differ from identity')
    summary = record['summary']
    if summary['wet_nodes'] != int(_i54_np.count_nonzero(arrays['wet_mask'])) or summary['overbank_nodes'] != int(_i54_np.count_nonzero(arrays['overbank_mask'])) or summary['protected_conflict_nodes'] != int(_i54_np.count_nonzero(arrays['protected_conflict_mask'])) or (summary['boundary_contact_nodes'] != int(_i54_np.count_nonzero(arrays['boundary_contact_mask']))) or (summary['reach_limited_nodes'] != int(_i54_np.count_nonzero(arrays['reach_limited_mask']))) or (summary['stage_mismatch_nodes'] != int(_i54_np.count_nonzero(arrays['stage_mismatch_mask']))) or (summary['disconnected_seed_nodes'] != int(_i54_np.count_nonzero(arrays['disconnected_seed_mask']))) or (summary['channel_seed_nodes'] != int(_i54_np.count_nonzero(arrays['channel_seed_mask']))) or (summary['legal_outlet_wet'] != bool(_i54_np.any(arrays['wet_mask'] & arrays['legal_outlet_mask']))):
        raise ValueError('inundation summary mismatch')
    expected_complete = params['whole_graph_covered'] and summary['legal_outlet_wet'] and (not bool(_i54_np.any(arrays['disconnected_seed_mask'] | arrays['boundary_contact_mask'] | arrays['reach_limited_mask'])))
    if summary['whole_graph_covered'] != params['whole_graph_covered'] or summary['coverage_complete'] != expected_complete:
        raise ValueError('inundation coverage summary mismatch')
    for value in arrays.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': record['status'], 'arrays': arrays, 'summary': summary}
CHANNEL_JOINT_VERSION = 'channel-joint-v1'

def assess_joint(plan, sections, stage, inundation):
    """A pass requires the full shared domain and every diagnosed constraint."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i55_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i55_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i55_digest
    params = inundation['identity']['parameters']
    if sections['identity']['parameters']['plan_identity_sha256'] != plan['identity_sha256'] or stage['identity']['parameters']['plan_identity_sha256'] != plan['identity_sha256'] or params['section_identity_sha256'] != sections['identity_sha256'] or (params['stage_identity_sha256'] != stage['identity_sha256']):
        raise ValueError('joint inputs do not share their saved plan and stages')
    if _i55_digest({name: _i55_array_hash(value) for name, value in sections['arrays'].items()}) != params['section_arrays_sha256']:
        raise ValueError('joint section arrays differ from inundation source')
    if _i55_ArtifactIdentity(**stage['identity']).sha256 != stage['identity_sha256'] or _i55_ArtifactIdentity(**inundation['identity']).sha256 != inundation['identity_sha256'] or _i55_digest({name: _i55_array_hash(value) for name, value in stage['arrays'].items()}) != stage['identity']['parameters']['stage_output_sha256'] or (_i55_array_hash(inundation['arrays']['water_surface_m']) != params['water_sha256']) or (_i55_digest({name: _i55_array_hash(value) for name, value in inundation['arrays'].items()}) != params['all_arrays_sha256']):
        raise ValueError('joint stage or water arrays differ from identity')
    if stage['summary']['stage_feasible'] != (not bool((stage['arrays']['invalid_depth_mask'] | stage['arrays']['excessive_lift_mask'] | stage['arrays']['inherited_failure_mask']).any())):
        raise ValueError('stage feasibility summary disagrees with masks')
    flood_arrays = inundation['arrays']
    flood_summary = inundation['summary']
    checks = {'wet_nodes': 'wet_mask', 'overbank_nodes': 'overbank_mask', 'protected_conflict_nodes': 'protected_conflict_mask', 'boundary_contact_nodes': 'boundary_contact_mask', 'reach_limited_nodes': 'reach_limited_mask', 'stage_mismatch_nodes': 'stage_mismatch_mask', 'channel_seed_nodes': 'channel_seed_mask', 'disconnected_seed_nodes': 'disconnected_seed_mask'}
    for count_name, mask_name in checks.items():
        if flood_summary[count_name] != int(flood_arrays[mask_name].sum()):
            raise ValueError('inundation summary disagrees with masks')
    complete = params['whole_graph_covered'] and bool((flood_arrays['wet_mask'] & flood_arrays['legal_outlet_mask']).any()) and (not bool((flood_arrays['disconnected_seed_mask'] | flood_arrays['boundary_contact_mask'] | flood_arrays['reach_limited_mask']).any()))
    if flood_summary['whole_graph_covered'] != params['whole_graph_covered'] or flood_summary['coverage_complete'] != complete or flood_summary['legal_outlet_wet'] != bool((flood_arrays['wet_mask'] & flood_arrays['legal_outlet_mask']).any()):
        raise ValueError('inundation coverage summary mismatch')
    section_summary = sections['summary']
    stage_summary = stage['summary']
    flood_summary = inundation['summary']
    blockers = {'plan': section_summary['blocked_by_plan'], 'centerline': section_summary.get('blocked_by_centerline', False), 'stage': not stage_summary['stage_feasible'], 'local_budget': section_summary['local_budget_conflict_nodes'] > 0, 'protection': section_summary['protected_conflict_nodes'] > 0 or flood_summary['protected_conflict_nodes'] > 0, 'resolution': section_summary['needs_refinement_nodes'] > 0 or section_summary['potentially_unsampled_segments'] > 0, 'terrain_coverage': not flood_summary['coverage_complete'] or bool((sections['arrays']['clipped_boundary_mask'] & ~inundation['arrays']['legal_outlet_mask']).any()), 'stage_transition': flood_summary['stage_mismatch_nodes'] > 0, 'legal_outlet': not flood_summary['legal_outlet_wet'], 'wet_connectivity': flood_summary['disconnected_seed_nodes'] > 0}
    identity = _i55_ArtifactIdentity('Terragenesis', 'channel-joint', CHANNEL_JOINT_VERSION, 0, {'plan_identity_sha256': plan['identity_sha256'], 'section_identity_sha256': sections['identity_sha256'], 'stage_identity_sha256': stage['identity_sha256'], 'inundation_identity_sha256': inundation['identity_sha256']})
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': 'diagnostic_not_publishable', 'pass': not any(blockers.values()), 'blockers': blockers}

@_i56_dataclass(frozen=True)
class RerouteRecipe:
    max_path_cells: int = 200
    max_expansions: int = 10000
    max_extra_cut_m: float = 4.0
    max_cells: int = 250000

    def __post_init__(self):
        if type(self.max_path_cells) is not int or not 0 < self.max_path_cells <= 1000000 or type(self.max_expansions) is not int or (not 0 < self.max_expansions <= 1000000) or (type(self.max_cells) is not int) or (not 0 < self.max_cells <= 1000000) or isinstance(self.max_extra_cut_m, bool) or (not _i56_math.isfinite(self.max_extra_cut_m)) or (self.max_extra_cut_m < 0):
            raise ValueError('invalid reroute bounds')

def _integer_pair(value):
    if not isinstance(value, (tuple, list, _i56_np.ndarray)) or len(value) != 2 or any((isinstance(item, (bool, _i56_np.bool_)) or not isinstance(item, (int, _i56_np.integer)) for item in value)):
        raise ValueError('reroute endpoints must be integer pairs')
    return tuple((int(item) for item in value))

def _local_discharge(plan):
    arrays = plan['arrays']
    discharge = arrays['discharge_m3_s'].ravel()
    local = discharge.copy()
    receiver = arrays['receiver']
    donors = _i56_np.flatnonzero(receiver >= 0)
    _i56_np.subtract.at(local, receiver[donors], discharge[donors])
    if _i56_np.any(local < -1e-08):
        raise ValueError('source discharge is not conservative')
    local = _i56_np.maximum(local, 0.0)
    total = float(discharge[receiver < 0].sum())
    if not _i56_math.isclose(float(local.sum()), total, rel_tol=1e-10, abs_tol=1e-08):
        raise ValueError('outlet discharge is not conservative')
    return (local, total)

def reroute_channel(plan, source_grid_zx, downstream_anchor_grid_zx, domain_mask, protected_mask, recipe=RerouteRecipe()):
    """Search an explicit local path, replace one receiver edge, then replan Q/bed."""
    from terrain_pipeline.drainage import grid_mesh as _i56_grid_mesh
    from terrain_pipeline.drainage import masked_mesh as _i56_masked_mesh
    from terrain_pipeline.channel_geometry import ChannelRecipe as _x3_ChannelRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _x4_plan_channel
    from terrain_pipeline.channel_geometry import _validate_route as _x5_validate_route
    from terrain_pipeline.channel_geometry import _validated_source_plan as _x6_validated_source_plan
    if not isinstance(recipe, RerouteRecipe):
        raise ValueError('reroute recipe required')
    if _i56_np.asarray(plan['arrays']['source_height_m']).size > recipe.max_cells:
        raise ValueError('reroute exceeds cell bound')
    plan = _x6_validated_source_plan(plan)
    arrays = plan['arrays']
    params = plan['identity']['parameters']
    if recipe.max_extra_cut_m > params['max_cut_m']:
        raise ValueError('reroute extra cut exceeds original bed limit')
    local_q, outlet_total = _local_discharge(plan)
    height = arrays['source_height_m']
    shape = height.shape
    domain, protected = (_i56_np.asarray(domain_mask), _i56_np.asarray(protected_mask))
    if domain.shape != shape or protected.shape != shape or domain.dtype != bool or (protected.dtype != bool):
        raise ValueError('invalid reroute masks')
    start = _integer_pair(source_grid_zx)
    anchor = _integer_pair(downstream_anchor_grid_zx)
    if any((not (0 <= point[0] < shape[0] and 0 <= point[1] < shape[1]) for point in (start, anchor))):
        raise ValueError('reroute endpoints outside grid')
    if not arrays['channel_mask'][start] or not arrays['channel_mask'][anchor] or start == anchor:
        raise ValueError('reroute endpoints must be distinct active nodes')
    receiver = arrays['receiver'].copy()
    start_id = _i56_np.ravel_multi_index(start, shape)
    anchor_id = _i56_np.ravel_multi_index(anchor, shape)
    old_chain = set()
    cell = start_id
    while cell >= 0 and cell not in old_chain:
        old_chain.add(cell)
        cell = int(receiver[cell])
    if anchor_id not in old_chain:
        raise ValueError('anchor must be downstream of source')
    allowed = domain & ~protected
    old_upstream = _i56_np.zeros(height.size, bool)
    upstream = [[] for _ in range(receiver.size)]
    for donor, target in enumerate(receiver):
        if target >= 0:
            upstream[int(target)].append(donor)
    stack = [start_id]
    while stack:
        current = stack.pop()
        if old_upstream[current]:
            continue
        old_upstream[current] = True
        stack.extend(upstream[current])
    allowed.ravel()[old_upstream] = False
    allowed[start] = domain[start] and (not protected[start])
    allowed[anchor] = domain[anchor] and (not protected[anchor])
    if not allowed[start] or not allowed[anchor]:
        raise ValueError('reroute endpoint blocked')
    spacing = plan['identity']['parameters']
    mesh = _i56_grid_mesh(shape, x0_m=spacing['origin_x_m'], z0_m=spacing['origin_z_m'], dx_m=spacing['spacing_x_m'], dz_m=spacing['spacing_z_m'], world_seed=spacing.get('world_seed', 20261020))
    mesh = _i56_masked_mesh(mesh, allowed)
    distances = {start: 0.0}
    previous = {start: None}
    heap = [(0.0, start)]
    expansions = 0
    while heap:
        cost, cell = _i56_heapq.heappop(heap)
        if cost != distances[cell]:
            continue
        expansions += 1
        if expansions > recipe.max_expansions:
            raise ValueError('reroute search exceeds expansion bound')
        if cell == anchor:
            break
        current_id = cell[0] * shape[1] + cell[1]
        for edge in range(mesh.indptr[current_id], mesh.indptr[current_id + 1]):
            target_id = int(mesh.indices[edge])
            nxt = divmod(target_id, shape[1])
            if nxt != anchor and arrays['outlet_mask'][nxt] and (arrays['discharge_m3_s'][nxt] > 0):
                continue
            distance = float(mesh.edge_length_m[edge])
            required_cut = max(0.0, height[nxt] - height[cell] + spacing['min_bed_slope_m_per_m'] * distance)
            if required_cut > recipe.max_extra_cut_m + 1e-09:
                continue
            next_cost = cost + distance + required_cut * distance
            if next_cost < distances.get(nxt, _i56_math.inf):
                distances[nxt] = next_cost
                previous[nxt] = cell
                _i56_heapq.heappush(heap, (next_cost, nxt))
    if anchor not in previous:
        raise ValueError('no bounded legal reroute')
    path = []
    cell = anchor
    while cell is not None:
        path.append(cell)
        cell = previous[cell]
    path.reverse()
    if len(path) > recipe.max_path_cells:
        raise ValueError('reroute exceeds path bound')
    for current, nxt in zip(path, path[1:]):
        receiver[_i56_np.ravel_multi_index(current, shape)] = _i56_np.ravel_multi_index(nxt, shape)
    order = []
    seen = _i56_np.zeros(receiver.size, _i56_np.int8)
    for start_cell in range(receiver.size):
        chain = []
        cell = start_cell
        while cell >= 0 and seen[cell] == 0:
            seen[cell] = 1
            chain.append(cell)
            cell = int(receiver[cell])
        if cell >= 0 and seen[cell] == 1:
            raise ValueError('reroute creates a cycle')
        for cell in reversed(chain):
            seen[cell] = 2
            order.append(cell)
    order = _i56_np.array(order, dtype=_i56_np.int64)
    outlets = (receiver == -1).reshape(shape)
    route_mesh = _i56_grid_mesh(shape, x0_m=spacing['origin_x_m'], z0_m=spacing['origin_z_m'], dx_m=spacing['spacing_x_m'], dz_m=spacing['spacing_z_m'], world_seed=spacing.get('world_seed', 20261020))
    _x5_validate_route(receiver, order, shape, outlets, route_mesh)
    q = local_q.copy()
    for cell in order[::-1]:
        target = receiver[cell]
        if target >= 0:
            q[target] += q[cell]
    if not _i56_math.isclose(float(q[receiver < 0].sum()), outlet_total, rel_tol=1e-10, abs_tol=1e-08):
        raise ValueError('rerouted outlet discharge is not conservative')
    channel_recipe = _x3_ChannelRecipe(**{name: spacing[name] for name in _x3_ChannelRecipe.__dataclass_fields__})
    replanned = _x4_plan_channel(height, receiver, order, outlets, q.reshape(shape), spacing['spacing_x_m'], spacing['spacing_z_m'], spacing['origin_x_m'], spacing['origin_z_m'], spacing['sea_level_elevation_m'], plan['identity_sha256'], channel_recipe)
    if _i56_np.any(replanned['arrays']['channel_mask'] & ~domain) or _i56_np.any(replanned['arrays']['channel_mask'] & protected):
        raise ValueError('rerouted channel violates domain or protection')
    feasible = not bool(_i56_np.any(replanned['arrays']['over_budget_mask'] | replanned['arrays']['failed_slope_edge_donor_mask']))
    return {'status': 'diagnostic_not_publishable', 'path_grid_zx': [list(cell) for cell in path], 'source_plan_sha256': plan['identity_sha256'], 'plan': replanned, 'summary': {'path_cells': len(path), 'new_plan_over_budget_nodes': int(replanned['arrays']['over_budget_mask'].sum()), 'new_failed_slope_edges': int(replanned['arrays']['failed_slope_edge_donor_mask'].sum()), 'bed_plan_feasible': feasible, 'search_expansions': expansions}}
CHANNEL_STAGE_VERSION = 'channel-stage-v1'

@_i57_dataclass(frozen=True)
class StageRecipe:
    min_clearance_m: float = 0.15
    max_depth_m: float = 3.0
    max_lift_above_nominal_m: float = 1.0
    min_stage_slope_m_per_m: float = 0.0

    def __post_init__(self):
        for name in ('min_clearance_m', 'max_depth_m', 'max_lift_above_nominal_m', 'min_stage_slope_m_per_m'):
            value = getattr(self, name)
            if isinstance(value, bool) or not _i57_math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be finite and nonnegative')
        if self.min_clearance_m <= 0 or self.max_depth_m < self.min_clearance_m:
            raise ValueError('stage depth limits are inconsistent')

def solve_stage(plan, outlet_stage_m, recipe: StageRecipe, centerline=None):
    """A deterministic static feasibility surface, not a hydraulic solver."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i57_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i57_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i57_digest
    from terrain_pipeline.channel_geometry import _mesh_from_parameters as _x7_mesh_from_parameters
    from terrain_pipeline.channel_geometry import _validate_route as _x8_validate_route
    if not isinstance(recipe, StageRecipe) or plan.get('status') != 'diagnostic_not_publishable':
        raise ValueError('diagnostic plan and stage recipe required')
    identity = _i57_ArtifactIdentity(**plan['identity'])
    if identity.sha256 != plan['identity_sha256'] or identity.algorithm != 'metric-channel-plan':
        raise ValueError('invalid plan identity')
    arrays = plan['arrays']
    params = identity.record()['parameters']
    shape = arrays['source_height_m'].shape
    for name, field in (('source_height_m', 'source_height_sha256'), ('discharge_m3_s', 'source_discharge_sha256'), ('receiver', 'source_route_sha256'), ('order', 'source_order_sha256'), ('outlet_mask', 'source_outlet_sha256')):
        if _i57_array_hash(_i57_np.ascontiguousarray(arrays[name])) != params[field]:
            raise ValueError('plan input differs from identity')
    if len(shape) != 2 or min(shape) < 1 or any((arrays[name].shape != shape for name in ('bounded_bed_m', 'nominal_depth_m', 'channel_mask', 'over_budget_mask', 'failed_slope_edge_donor_mask'))) or any((not _i57_np.isfinite(arrays[name]).all() for name in ('source_height_m', 'bounded_bed_m', 'nominal_depth_m'))) or _i57_np.any(arrays['nominal_depth_m'] < 0) or any((arrays[name].dtype != bool for name in ('channel_mask', 'outlet_mask', 'over_budget_mask', 'failed_slope_edge_donor_mask'))):
        raise ValueError('invalid plan geometry or masks')
    receiver, order = _x8_validate_route(arrays['receiver'], arrays['order'], shape, arrays['outlet_mask'], _x7_mesh_from_parameters(params, shape), historical_saved_graph=identity.algorithm_version == 'metric-channel-plan-v1')
    active = arrays['channel_mask'].ravel()
    bounded = arrays['bounded_bed_m'].ravel()
    nominal_depth = arrays['nominal_depth_m'].ravel()
    outlets = _i57_np.flatnonzero(arrays['outlet_mask'].ravel() & active)
    supplied = _i57_np.asarray(outlet_stage_m, dtype=_i57_np.float64)
    if supplied.shape != (len(outlets),) or not _i57_np.isfinite(supplied).all():
        raise ValueError('one finite fixed stage per active explicit outlet required')
    if centerline is not None:
        from terrain_pipeline.channel_geometry import validate_centerline_for_plan as validate_centerline_for_plan
        validate_centerline_for_plan(centerline, plan)
        coords = _i57_np.full((bounded.size, 2), _i57_np.nan)
        coords[centerline['arrays']['node_flat_index']] = centerline['arrays']['node_world_xz_m']
    else:
        cols = shape[1]
        cells = _i57_np.arange(bounded.size)
        coords = _i57_np.column_stack((params['origin_x_m'] + cells % cols * params['spacing_x_m'], params['origin_z_m'] + cells // cols * params['spacing_z_m']))
    stage = _i57_np.full(bounded.size, _i57_np.nan)
    stage[outlets] = supplied
    preferred = bounded + _i57_np.maximum(nominal_depth, recipe.min_clearance_m)
    for cell in order:
        if not active[cell] or receiver[cell] < 0:
            continue
        target = receiver[cell]
        if not active[target]:
            raise ValueError('active channel ends before outlet')
        distance = _i57_np.linalg.norm(coords[cell] - coords[target])
        stage[cell] = max(preferred[cell], stage[target] + recipe.min_stage_slope_m_per_m * distance)
    invalid_depth = active & ((stage - bounded < recipe.min_clearance_m - 1e-09) | (stage - bounded > recipe.max_depth_m + 1e-09))
    excessive_lift = active & (stage > preferred + recipe.max_lift_above_nominal_m + 1e-09)
    inherited = (arrays['over_budget_mask'].ravel() | arrays['failed_slope_edge_donor_mask'].ravel()).copy()
    if centerline is not None:
        nodes = centerline['arrays']['node_flat_index']
        inherited[nodes] |= centerline['arrays']['slope_failed_donor_mask'] | centerline['arrays']['local_budget_failed_mask']
    if not _i57_np.isfinite(stage[active]).all():
        raise ValueError('stage propagation did not reach explicit outlet')
    result = {'stage_m': stage.reshape(shape), 'channel_mask': arrays['channel_mask'].copy(), 'outlet_stage_m': supplied.copy(), 'outlet_flat_index': outlets.astype(_i57_np.int64), 'invalid_depth_mask': invalid_depth.reshape(shape), 'excessive_lift_mask': excessive_lift.reshape(shape), 'inherited_failure_mask': inherited.reshape(shape)}
    stage_identity = _i57_ArtifactIdentity('Terragenesis', 'channel-stage', CHANNEL_STAGE_VERSION, 0, {**_i57_asdict(recipe), 'plan_identity_sha256': plan['identity_sha256'], 'bounded_bed_sha256': _i57_array_hash(arrays['bounded_bed_m']), 'nominal_depth_sha256': _i57_array_hash(arrays['nominal_depth_m']), 'channel_mask_sha256': _i57_array_hash(arrays['channel_mask']), 'outlet_stage_sha256': _i57_array_hash(supplied), 'centerline_identity_sha256': centerline['identity_sha256'] if centerline else None, 'stage_output_sha256': _i57_digest({name: _i57_array_hash(_i57_np.ascontiguousarray(value)) for name, value in result.items()})})
    for value in result.values():
        value.flags.writeable = False
    return {'identity': stage_identity.record(), 'identity_sha256': stage_identity.sha256, 'status': 'diagnostic_not_publishable', 'arrays': result, 'summary': {'active_nodes': int(_i57_np.count_nonzero(active)), 'invalid_depth_nodes': int(_i57_np.count_nonzero(invalid_depth)), 'excessive_lift_nodes': int(_i57_np.count_nonzero(excessive_lift)), 'inherited_failure_nodes': int(_i57_np.count_nonzero(inherited)), 'stage_feasible': not bool(_i57_np.any(invalid_depth | excessive_lift | inherited))}}

def save_stage(result, path):
    from terrain_pipeline.artifacts.contracts import array_hash as _i57_array_hash
    destination = _i57_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ('identity', 'identity_sha256', 'status', 'summary')}
    record['format_version'] = 1
    record['array_sha256'] = {name: _i57_array_hash(_i57_np.ascontiguousarray(value)) for name, value in result['arrays'].items()}
    temporary = None
    try:
        with _i57_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, prefix=f'.{destination.name}-', suffix='.npz', delete=False) as stream:
            temporary = _i57_Path(stream.name)
            _i57_np.savez_compressed(stream, manifest=_i57_json.dumps(record, sort_keys=True), **result['arrays'])
        load_stage(temporary)
        _i57_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def load_stage(path):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i57_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i57_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i57_digest
    expected = {'stage_m', 'channel_mask', 'outlet_stage_m', 'outlet_flat_index', 'invalid_depth_mask', 'excessive_lift_mask', 'inherited_failure_mask'}
    with _i57_np.load(path, allow_pickle=False) as archive:
        record = _i57_json.loads(str(archive['manifest'].item()))
        if set(archive.files) != expected | {'manifest'} or set(record['array_sha256']) != expected:
            raise ValueError('invalid stage array set')
        arrays = {name: archive[name].copy() for name in expected}
    identity = _i57_ArtifactIdentity(**record['identity'])
    if record['format_version'] != 1 or record['status'] != 'diagnostic_not_publishable' or identity.algorithm != 'channel-stage' or (identity.algorithm_version != CHANNEL_STAGE_VERSION) or (identity.sha256 != record['identity_sha256']) or any((_i57_array_hash(_i57_np.ascontiguousarray(arrays[name])) != expected_hash for name, expected_hash in record['array_sha256'].items())):
        raise ValueError('invalid stage identity or hashes')
    params = identity.record()['parameters']
    StageRecipe(**{name: params[name] for name in StageRecipe.__dataclass_fields__})
    if _i57_digest({name: _i57_array_hash(_i57_np.ascontiguousarray(value)) for name, value in arrays.items()}) != params['stage_output_sha256']:
        raise ValueError('stage output differs from identity')
    shape = arrays['stage_m'].shape
    if len(shape) != 2 or min(shape) < 1 or any((arrays[name].shape != shape or arrays[name].dtype != bool for name in ('channel_mask', 'invalid_depth_mask', 'excessive_lift_mask', 'inherited_failure_mask'))) or (arrays['stage_m'].dtype != _i57_np.float64) or (not _i57_np.isfinite(arrays['stage_m'][arrays['channel_mask']]).all()) or (arrays['outlet_stage_m'].dtype != _i57_np.float64) or (not _i57_np.isfinite(arrays['outlet_stage_m']).all()) or (arrays['outlet_flat_index'].dtype != _i57_np.int64) or (arrays['outlet_stage_m'].shape != arrays['outlet_flat_index'].shape):
        raise ValueError('invalid stage shapes or values')
    summary = record['summary']
    if summary['active_nodes'] != int(_i57_np.count_nonzero(arrays['channel_mask'])) or summary['invalid_depth_nodes'] != int(_i57_np.count_nonzero(arrays['invalid_depth_mask'])) or summary['excessive_lift_nodes'] != int(_i57_np.count_nonzero(arrays['excessive_lift_mask'])) or (summary['inherited_failure_nodes'] != int(_i57_np.count_nonzero(arrays['inherited_failure_mask']))):
        raise ValueError('stage summary mismatch')
    if summary['stage_feasible'] != (not bool(_i57_np.any(arrays['invalid_depth_mask'] | arrays['excessive_lift_mask'] | arrays['inherited_failure_mask']))):
        raise ValueError('stage feasibility summary mismatch')
    for value in arrays.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': record['status'], 'arrays': arrays, 'summary': summary}
ALGORITHM = 'dynamic-surface-storage-conductance-v1'
FORMAT = 'dynamic-surface-hydraulics-npy-v1'
GEOMETRY_MODE = 'explicit-storage-graph-not-legacy-integrated'
LEDGER_COLUMNS = ('storage_before_m3', 'local_volume_m3', 'boundary_into_storage_m3', 'storage_after_m3', 'storage_change_m3', 'residual_m3')
MAX_METADATA_BYTES = 16384
MAX_HEADER_BYTES = 2048
MAX_MEMBERS = 24
MAX_FILE_BYTES = 65 * 1024 * 1024

@_i58_dataclass(frozen=True)
class ResourceLimits:
    max_nodes: int = 4096
    max_edges: int = 16384
    max_steps: int = 4096
    max_work: int = 2000000
    max_retained_bytes: int = 64 * 1024 * 1024

    def __post_init__(self):
        hard = (4096, 16384, 4096, 2000000, 64 * 1024 * 1024)
        for field, ceiling in zip(_i58_fields(self), hard):
            value = getattr(self, field.name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError('invalid resource limit: ' + field.name)

def _preflight(node_count, edge_count, step_count, limits):
    if not isinstance(limits, ResourceLimits):
        raise ValueError('limits must be ResourceLimits')
    ResourceLimits(**_i58_asdict(limits))
    if not 1 <= node_count <= limits.max_nodes:
        raise ValueError('node resource cap')
    if not 0 <= edge_count <= limits.max_edges:
        raise ValueError('edge resource cap')
    if not 1 <= step_count <= limits.max_steps:
        raise ValueError('time resource cap')
    work = step_count * (node_count + edge_count)
    if work > limits.max_work:
        raise ValueError('work resource cap')
    input_bytes = 8 * (5 * node_count + edge_count + (2 * step_count + 1) * node_count) + 16 * edge_count + 3 * node_count
    state_bytes = 8 * ((step_count + 1) * (2 * node_count + 1) + step_count * (edge_count + 6))
    failure_bytes = 8 * (3 * node_count + edge_count + 6)
    retained_bytes = input_bytes + state_bytes + failure_bytes + MAX_METADATA_BYTES
    if retained_bytes > limits.max_retained_bytes:
        raise ValueError('retained resource cap')
    return {'nodes': node_count, 'edges': edge_count, 'steps': step_count, 'work': work, 'retained_bytes_upper_bound': retained_bytes}

def _immutable(value, dtype=None):
    array = _i58_np.asarray(value, dtype=dtype, order='C')
    return _i58_np.frombuffer(array.tobytes(order='C'), dtype=array.dtype).reshape(array.shape)

def _finite_scalar(value, name):
    if isinstance(value, (bool, _i58_np.bool_)) or not isinstance(value, (int, float, _i58_np.number)):
        raise ValueError(name + ' must be a finite positive scalar')
    if not _i58_math.isfinite(value) or value <= 0:
        raise ValueError(name + ' must be a finite positive scalar')
    return float(value)

@_i58_dataclass(frozen=True)
class HydraulicsInput:
    bed_m: _i58_np.ndarray
    area_m2: _i58_np.ndarray
    initial_stage_m: _i58_np.ndarray
    edges: _i58_np.ndarray
    conductance_m2_s: _i58_np.ndarray
    local_q_m3_s: _i58_np.ndarray
    boundary_mask: _i58_np.ndarray
    boundary_stage_m: _i58_np.ndarray
    dt_s: float
    max_depth_m: float
    valid_mask: _i58_np.ndarray
    protected_mask: _i58_np.ndarray
    coords_m: _i58_np.ndarray
    source: str
    datum: str
    coords: str
    limits: ResourceLimits = ResourceLimits()
    geometry_mode: str = GEOMETRY_MODE

    def __post_init__(self):
        bed = _i58_np.asarray(self.bed_m)
        edges = _i58_np.asarray(self.edges)
        local = _i58_np.asarray(self.local_q_m3_s)
        if bed.ndim != 1 or edges.ndim != 2 or edges.shape[1] != 2 or (local.ndim != 2):
            raise ValueError('expected bed[N], edges[E,2], local_q[T,N]')
        node_count, edge_count, step_count = (len(bed), len(edges), len(local))
        _preflight(node_count, edge_count, step_count, self.limits)
        expected = {'bed_m': (node_count,), 'area_m2': (node_count,), 'initial_stage_m': (node_count,), 'edges': (edge_count, 2), 'conductance_m2_s': (edge_count,), 'local_q_m3_s': (step_count, node_count), 'boundary_mask': (node_count,), 'boundary_stage_m': (step_count + 1, node_count), 'valid_mask': (node_count,), 'protected_mask': (node_count,), 'coords_m': (node_count, 2)}
        frozen = {}
        for name, shape in expected.items():
            array = _i58_np.asarray(getattr(self, name))
            if array.shape != shape:
                raise ValueError(name + ' shape mismatch')
            if name.endswith('mask'):
                if array.dtype != _i58_np.dtype(bool):
                    raise ValueError(name + ' must be boolean')
                dtype = _i58_np.dtype(bool)
            elif name == 'edges':
                if array.dtype.kind not in 'iu' or _i58_np.any(array < 0) or _i58_np.any(array >= node_count):
                    raise ValueError('edges must be in-range integer indices')
                dtype = _i58_np.dtype('<i8')
            else:
                if array.dtype.kind not in 'fiu' or not _i58_np.all(_i58_np.isfinite(array)):
                    raise ValueError(name + ' must be finite real numbers')
                dtype = _i58_np.dtype('<f8')
            frozen[name] = _immutable(array, dtype)
        for name, value in frozen.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, 'dt_s', _finite_scalar(self.dt_s, 'dt_s'))
        object.__setattr__(self, 'max_depth_m', _finite_scalar(self.max_depth_m, 'max_depth_m'))
        for name in ('source', 'datum', 'coords'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > 1024:
                raise ValueError('explicit provenance required: ' + name)
        if self.geometry_mode != GEOMETRY_MODE:
            raise ValueError('only explicit storage graph geometry is supported')
        if not _i58_np.all(self.valid_mask) or _i58_np.any(self.protected_mask):
            raise ValueError('unknown or protected support is unsupported')
        if _i58_np.all(self.boundary_mask):
            raise ValueError('at least one internal storage node is required')
        if _i58_np.any(self.area_m2 <= 0) or _i58_np.any(self.conductance_m2_s <= 0):
            raise ValueError('area and conductance must be positive')
        if _i58_np.any(self.edges[:, 0] == self.edges[:, 1]):
            raise ValueError('selfloop is not allowed')
        unique_edges = _i58_np.sort(self.edges, axis=1)
        if len(_i58_np.unique(unique_edges, axis=0)) != edge_count:
            raise ValueError('duplicate undirected edge')
        depth = self.initial_stage_m - self.bed_m
        if _i58_np.any(depth < 0) or _i58_np.any(depth > self.max_depth_m):
            raise ValueError('initial depth outside [0,max_depth_m]')
        if not _i58_np.array_equal(self.initial_stage_m[self.boundary_mask], self.boundary_stage_m[0, self.boundary_mask]):
            raise ValueError('initial stage must equal time-zero boundary stage')
        if _i58_np.any(self.local_q_m3_s[:, self.boundary_mask] != 0):
            raise ValueError('signed local Q is only supported on internal storage nodes')
        sum_conductance = _i58_np.zeros(node_count)
        with _i58_np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            _i58_np.add.at(sum_conductance, self.edges[:, 0], self.conductance_m2_s)
            _i58_np.add.at(sum_conductance, self.edges[:, 1], self.conductance_m2_s)
            ratio = self.dt_s * sum_conductance / self.area_m2
            initial_storage = self.area_m2 * depth
            final_time = self.dt_s * step_count
        if not _i58_np.all(_i58_np.isfinite(ratio)) or _i58_np.any(ratio[~self.boundary_mask] > 1):
            raise ValueError('diffusive stability requires dt*sumK/area <= 1 (not CFL)')
        if not _i58_np.all(_i58_np.isfinite(initial_storage)) or not _i58_math.isfinite(final_time):
            raise ValueError('initial storage or time arithmetic is nonfinite')

@_i58_dataclass(frozen=True)
class FailedStep:
    step_n: int
    reason: str
    previous_stage_m: _i58_np.ndarray
    next_stage_m: _i58_np.ndarray
    next_storage_m3: _i58_np.ndarray
    qedges_m3_s: _i58_np.ndarray
    ledger_m3: _i58_np.ndarray

    def __post_init__(self):
        if type(self.step_n) is not int or not 0 <= self.step_n < 4096:
            raise ValueError('invalid failed step index')
        if self.reason not in ('negative_depth', 'max_depth', 'arithmetic_nonfinite'):
            raise ValueError('invalid failed reason')
        previous = _i58_np.asarray(self.previous_stage_m)
        if previous.ndim != 1 or not 1 <= len(previous) <= 4096:
            raise ValueError('failed node resource cap')
        for name in ('next_stage_m', 'next_storage_m3'):
            if _i58_np.asarray(getattr(self, name)).shape != previous.shape:
                raise ValueError('failed candidate node shape mismatch')
        flux = _i58_np.asarray(self.qedges_m3_s)
        if flux.ndim != 1 or len(flux) > 16384 or _i58_np.asarray(self.ledger_m3).shape != (6,):
            raise ValueError('failed edge cap or ledger shape mismatch')
        for field in _i58_fields(self):
            if field.name not in ('step_n', 'reason'):
                object.__setattr__(self, field.name, _immutable(getattr(self, field.name), '<f8'))

@_i58_dataclass(frozen=True)
class HydraulicsResult:
    inputs: HydraulicsInput
    status: str
    committed_steps: int
    stage_m: _i58_np.ndarray
    storage_m3: _i58_np.ndarray
    qedges_m3_s: _i58_np.ndarray
    time_s: _i58_np.ndarray
    ledger_m3: _i58_np.ndarray
    failed_step: FailedStep | None = None
    identity_sha256: str = ''

    def __post_init__(self):
        if not isinstance(self.inputs, HydraulicsInput):
            raise ValueError('result requires HydraulicsInput')
        _preflight(len(self.inputs.bed_m), len(self.inputs.edges), len(self.inputs.local_q_m3_s), self.inputs.limits)
        expected = _array_specs(len(self.inputs.bed_m), len(self.inputs.edges), len(self.inputs.local_q_m3_s), self.committed_steps, self.failed_step is not None)
        for name in ('stage_m', 'storage_m3', 'qedges_m3_s', 'time_s', 'ledger_m3'):
            if _i58_np.asarray(getattr(self, name)).shape != expected[name][0]:
                raise ValueError(name + ' result shape mismatch')
        for name in ('stage_m', 'storage_m3', 'qedges_m3_s', 'time_s', 'ledger_m3'):
            object.__setattr__(self, name, _immutable(getattr(self, name), '<f8'))
        if not self.identity_sha256:
            object.__setattr__(self, 'identity_sha256', fingerprint(self))

def _arrays(result):
    arrays = {}
    for field in _i58_fields(result.inputs):
        value = getattr(result.inputs, field.name)
        if isinstance(value, _i58_np.ndarray):
            arrays['input_' + field.name] = value
    for name in ('stage_m', 'storage_m3', 'qedges_m3_s', 'time_s', 'ledger_m3'):
        arrays[name] = getattr(result, name)
    if result.failed_step is not None:
        for field in _i58_fields(result.failed_step):
            value = getattr(result.failed_step, field.name)
            if isinstance(value, _i58_np.ndarray):
                arrays['failed_' + field.name] = value
    return arrays

def _metadata(result):
    inputs = result.inputs
    return {'algorithm': ALGORITHM, 'format': FORMAT, 'geometry_mode': inputs.geometry_mode, 'source': inputs.source, 'datum': inputs.datum, 'coords': inputs.coords, 'dt_s': inputs.dt_s, 'max_depth_m': inputs.max_depth_m, 'limits': _i58_asdict(inputs.limits), 'nodes': len(inputs.bed_m), 'edges': len(inputs.edges), 'steps': len(inputs.local_q_m3_s), 'status': result.status, 'committed_steps': result.committed_steps, 'failed_step': None if result.failed_step is None else {'step_n': result.failed_step.step_n, 'reason': result.failed_step.reason}}

def fingerprint(result):
    digest = _i58_hashlib.sha256()
    digest.update(_i58_json.dumps(_metadata(result), sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8'))
    for name, array in sorted(_arrays(result).items()):
        digest.update(_i58_json.dumps([name, array.dtype.str, list(array.shape)], separators=(',', ':')).encode('ascii'))
        digest.update(array.tobytes(order='C'))
    return digest.hexdigest()

def _ledger(previous_storage, next_storage, local_q, net_q, inputs):
    internal = ~inputs.boundary_mask
    before = float(_i58_np.sum(previous_storage))
    after = float(_i58_np.sum(next_storage))
    local = float(inputs.dt_s * _i58_np.sum(local_q[internal]))
    boundary = float(-inputs.dt_s * _i58_np.sum(net_q[inputs.boundary_mask]))
    change = after - before
    return _i58_np.array([before, local, boundary, after, change, change - local - boundary])

def _failure_reason(stage, storage, flux, ledger, inputs):
    if not all((_i58_np.all(_i58_np.isfinite(array)) for array in (stage, storage, flux, ledger))):
        return 'arithmetic_nonfinite'
    depth = stage - inputs.bed_m
    if _i58_np.any(depth < 0) or _i58_np.any(storage < 0):
        return 'negative_depth'
    if _i58_np.any(depth > inputs.max_depth_m):
        return 'max_depth'
    return None

def evaluate(inputs, *, cancel=None):
    """Advance synchronously; rejected steps and cancellation never commit state."""
    if not isinstance(inputs, HydraulicsInput):
        raise ValueError('inputs must be HydraulicsInput')
    if cancel is not None and (not callable(cancel)):
        raise ValueError('cancel must be a callable')
    inputs = HydraulicsInput(**{field.name: getattr(inputs, field.name) for field in _i58_fields(inputs)})
    node_count, edge_count, step_count = (len(inputs.bed_m), len(inputs.edges), len(inputs.local_q_m3_s))
    stages = _i58_np.empty((step_count + 1, node_count))
    storages = _i58_np.empty_like(stages)
    fluxes = _i58_np.empty((step_count, edge_count))
    ledgers = _i58_np.empty((step_count, 6))
    stages[0] = inputs.initial_stage_m
    storages[0] = inputs.area_m2 * (stages[0] - inputs.bed_m)
    storages[0, inputs.boundary_mask] = 0
    committed = 0
    status = 'completed'
    failed = None
    for step_n in range(step_count):
        if cancel is not None and cancel():
            status = 'cancelled'
            break
        with _i58_np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            flux = inputs.conductance_m2_s * (stages[step_n, inputs.edges[:, 0]] - stages[step_n, inputs.edges[:, 1]])
            net_q = _i58_np.zeros(node_count)
            _i58_np.add.at(net_q, inputs.edges[:, 0], -flux)
            _i58_np.add.at(net_q, inputs.edges[:, 1], flux)
            next_storage = storages[step_n] + inputs.dt_s * (inputs.local_q_m3_s[step_n] + net_q)
            next_storage[inputs.boundary_mask] = 0
            next_stage = inputs.bed_m + next_storage / inputs.area_m2
            next_stage[inputs.boundary_mask] = inputs.boundary_stage_m[step_n + 1, inputs.boundary_mask]
            ledger = _ledger(storages[step_n], next_storage, inputs.local_q_m3_s[step_n], net_q, inputs)
            reason = _failure_reason(next_stage, next_storage, flux, ledger, inputs)
        if reason is not None:
            status = 'failed'
            failed = FailedStep(step_n, reason, stages[step_n], next_stage, next_storage, flux, ledger)
            break
        stages[step_n + 1] = next_stage
        storages[step_n + 1] = next_storage
        fluxes[step_n] = flux
        ledgers[step_n] = ledger
        committed += 1
    result = HydraulicsResult(inputs, status, committed, stages[:committed + 1], storages[:committed + 1], fluxes[:committed], _i58_np.arange(committed + 1, dtype=float) * inputs.dt_s, ledgers[:committed], failed)
    validate(result)
    return result

def _array_specs(node_count, edge_count, step_count, committed, failed):
    if type(committed) is not int or not 0 <= committed <= step_count:
        raise ValueError('invalid committed step count')
    float_type = _i58_np.dtype('<f8')
    specs = {}
    for name in ('bed_m', 'area_m2', 'initial_stage_m'):
        specs['input_' + name] = ((node_count,), float_type)
    for name in ('boundary_mask', 'valid_mask', 'protected_mask'):
        specs['input_' + name] = ((node_count,), _i58_np.dtype(bool))
    specs.update({'input_edges': ((edge_count, 2), _i58_np.dtype('<i8')), 'input_conductance_m2_s': ((edge_count,), float_type), 'input_local_q_m3_s': ((step_count, node_count), float_type), 'input_boundary_stage_m': ((step_count + 1, node_count), float_type), 'input_coords_m': ((node_count, 2), float_type), 'stage_m': ((committed + 1, node_count), float_type), 'storage_m3': ((committed + 1, node_count), float_type), 'qedges_m3_s': ((committed, edge_count), float_type), 'time_s': ((committed + 1,), float_type), 'ledger_m3': ((committed, 6), float_type)})
    if failed:
        for name in ('previous_stage_m', 'next_stage_m', 'next_storage_m3'):
            specs['failed_' + name] = ((node_count,), float_type)
        specs['failed_qedges_m3_s'] = ((edge_count,), float_type)
        specs['failed_ledger_m3'] = ((6,), float_type)
    return specs

def _same(actual, expected, name, *, nonfinite=False):
    if not _i58_np.allclose(actual, expected, rtol=1e-12, atol=1e-12, equal_nan=nonfinite):
        raise ValueError('static equation mismatch: ' + name)

def _prove_step(inputs, step_n, previous_stage, previous_storage, next_stage, next_storage, flux, ledger, *, failed=False):
    internal = ~inputs.boundary_mask
    with _i58_np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        expected_flux = inputs.conductance_m2_s * (previous_stage[inputs.edges[:, 0]] - previous_stage[inputs.edges[:, 1]])
        _same(flux, expected_flux, 'edge conductance', nonfinite=failed)
        incidence_q = _i58_np.zeros(len(inputs.bed_m))
        _i58_np.add.at(incidence_q, inputs.edges[:, 0], -flux)
        _i58_np.add.at(incidence_q, inputs.edges[:, 1], flux)
        expected_storage = _i58_np.zeros(len(inputs.bed_m))
        expected_storage[internal] = previous_storage[internal] + inputs.dt_s * (inputs.local_q_m3_s[step_n, internal] + incidence_q[internal])
        _same(next_storage, expected_storage, 'Euler storage', nonfinite=failed)
        expected_stage = inputs.bed_m + next_storage / inputs.area_m2
        expected_stage[inputs.boundary_mask] = inputs.boundary_stage_m[step_n + 1, inputs.boundary_mask]
        _same(next_stage, expected_stage, 'next stage/boundary indexing', nonfinite=failed)
        before = float(previous_storage.sum())
        after = float(next_storage.sum())
        local = float(inputs.dt_s * inputs.local_q_m3_s[step_n, internal].sum())
        external = float(-inputs.dt_s * incidence_q[inputs.boundary_mask].sum())
        expected_ledger = [before, local, external, after, after - before, after - before - local - external]
        _same(ledger, expected_ledger, 'ledger', nonfinite=failed)
        reason = _failure_reason(next_stage, next_storage, flux, ledger, inputs)
    if not failed:
        if reason is not None:
            raise ValueError('illegal committed state: ' + reason)
        scale = max(1.0, abs(before), abs(after), abs(local), abs(external))
        if abs(ledger[5]) > 1e-12 * scale:
            raise ValueError('volume conservation residual')
    return reason

def validate(result):
    """Static proof against saved prev/next states. Never calls evaluate/advance."""
    if not isinstance(result, HydraulicsResult):
        raise ValueError('expected HydraulicsResult')
    inputs = HydraulicsInput(**{field.name: getattr(result.inputs, field.name) for field in _i58_fields(result.inputs)})
    node_count, edge_count, step_count = (len(inputs.bed_m), len(inputs.edges), len(inputs.local_q_m3_s))
    _preflight(node_count, edge_count, step_count, inputs.limits)
    committed = result.committed_steps
    specs = _array_specs(node_count, edge_count, step_count, committed, result.failed_step is not None)
    arrays = _arrays(result)
    if set(arrays) != set(specs):
        raise ValueError('array members mismatch')
    for name, array in arrays.items():
        shape, dtype = specs[name]
        if array.shape != shape or array.dtype != dtype or array.flags.writeable:
            raise ValueError('array contract mismatch: ' + name)
        if not name.startswith('failed_') and (not _i58_np.all(_i58_np.isfinite(array))):
            raise ValueError('nonfinite committed/input array: ' + name)
    if result.status not in ('completed', 'failed', 'cancelled'):
        raise ValueError('invalid result status')
    if result.status == 'completed' and (committed != step_count or result.failed_step is not None):
        raise ValueError('incomplete completed result')
    if result.status != 'completed' and committed >= step_count:
        raise ValueError('terminal prefix exceeds horizon')
    if (result.status == 'failed') != (result.failed_step is not None):
        raise ValueError('failed record/status mismatch')
    if not isinstance(result.identity_sha256, str) or result.identity_sha256 != fingerprint(result):
        raise ValueError('identity hash mismatch')
    _same(result.stage_m[0], inputs.initial_stage_m, 'initial stage')
    initial_storage = inputs.area_m2 * (inputs.initial_stage_m - inputs.bed_m)
    initial_storage[inputs.boundary_mask] = 0
    _same(result.storage_m3[0], initial_storage, 'initial storage')
    _same(result.time_s, _i58_np.arange(committed + 1) * inputs.dt_s, 'physical time')
    for step_n in range(committed):
        _prove_step(inputs, step_n, result.stage_m[step_n], result.storage_m3[step_n], result.stage_m[step_n + 1], result.storage_m3[step_n + 1], result.qedges_m3_s[step_n], result.ledger_m3[step_n])
    if result.failed_step is not None:
        failed = result.failed_step
        if type(failed.step_n) is not int or failed.step_n != committed:
            raise ValueError('failed step is not immediately after committed prefix')
        _same(failed.previous_stage_m, result.stage_m[-1], 'failed previous state')
        reason = _prove_step(inputs, committed, failed.previous_stage_m, result.storage_m3[-1], failed.next_stage_m, failed.next_storage_m3, failed.qedges_m3_s, failed.ledger_m3, failed=True)
        if reason is None or reason != failed.reason:
            raise ValueError('failed reason not supported by saved equations')
    return {'valid': True, 'identity_sha256': result.identity_sha256, 'committed_steps': committed, 'static_equations_verified': True, 'resources': _preflight(node_count, edge_count, step_count, inputs.limits)}

def save(result, path):
    """Validate, fsync, publish with atomic no-overwrite hardlink; always close fd."""
    validate(result)
    path = _i58_Path(path)
    if path.exists():
        raise FileExistsError(path)
    metadata = _metadata(result)
    metadata['identity_sha256'] = result.identity_sha256
    payload = _i58_json.dumps(metadata, sort_keys=True, allow_nan=False).encode('utf-8')
    if len(payload) > MAX_METADATA_BYTES:
        raise ValueError('metadata cap')
    descriptor, temporary = _i58_tempfile.mkstemp(prefix='.dynamic-hydro-', dir=path.parent)
    try:
        stream = _i58_os.fdopen(descriptor, 'w+b')
        descriptor = None
        with stream:
            with _i58_zipfile.ZipFile(stream, 'w', compression=_i58_zipfile.ZIP_STORED) as archive:
                archive.writestr('metadata.json', payload)
                for name, array in _arrays(result).items():
                    with archive.open(name + '.npy', 'w') as member:
                        _i58_np.lib.format.write_array(member, array, version=(1, 0), allow_pickle=False)
            if stream.tell() > MAX_FILE_BYTES:
                raise ValueError('bundle cap')
            stream.flush()
            _i58_os.fsync(stream.fileno())
        _i58_os.link(temporary, path)
    finally:
        if descriptor is not None:
            _i58_os.close(descriptor)
        _i58_os.unlink(temporary)
    return path

def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result

def _reject_constant(value):
    raise ValueError('nonfinite JSON constant: ' + value)

def _read_header(stream, info, shape, dtype):
    if _i58_np.lib.format.read_magic(stream) != (1, 0):
        raise ValueError('only NPY v1 headers supported')
    length_bytes = stream.read(2)
    if len(length_bytes) != 2 or int.from_bytes(length_bytes, 'little') > MAX_HEADER_BYTES - 10:
        raise ValueError('NPY header byte cap')
    header_length = int.from_bytes(length_bytes, 'little')
    header_payload = stream.read(header_length)
    if len(header_payload) != header_length:
        raise ValueError('truncated NPY header')
    header_stream = _i58_io.BytesIO(length_bytes + header_payload)
    actual_shape, fortran, actual_dtype = _i58_np.lib.format.read_array_header_1_0(header_stream, max_header_size=MAX_HEADER_BYTES)
    if actual_shape != shape or fortran or actual_dtype != dtype or actual_dtype.hasobject:
        raise ValueError('NPY header shape/dtype/order mismatch')
    payload_bytes = _i58_math.prod(shape) * dtype.itemsize
    if stream.tell() > MAX_HEADER_BYTES or info.file_size != stream.tell() + payload_bytes:
        raise ValueError('NPY exact payload size mismatch')
    return payload_bytes

def load(path):
    """Bounded static read: all headers inspected before payload arrays are allocated."""
    with _i58_Path(path).open('rb') as file:
        if _i58_os.fstat(file.fileno()).st_size > MAX_FILE_BYTES:
            raise ValueError('bundle file cap')
        with _i58_zipfile.ZipFile(file) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(infos) > MAX_MEMBERS or len(set(names)) != len(names):
                raise ValueError('duplicate members or member cap')
            if any((info.compress_type != _i58_zipfile.ZIP_STORED or info.flag_bits & 1 or info.is_dir() for info in infos)):
                raise ValueError('only unencrypted stored file members supported')
            if sum((info.file_size for info in infos)) > MAX_FILE_BYTES:
                raise ValueError('bundle payload cap')
            if 'metadata.json' not in names or archive.getinfo('metadata.json').file_size > MAX_METADATA_BYTES:
                raise ValueError('metadata absent or cap exceeded')
            meta = _i58_json.loads(archive.read('metadata.json'), object_pairs_hook=_unique_json, parse_constant=_reject_constant)
            keys = {'algorithm', 'format', 'geometry_mode', 'source', 'datum', 'coords', 'dt_s', 'max_depth_m', 'limits', 'nodes', 'edges', 'steps', 'status', 'committed_steps', 'failed_step', 'identity_sha256'}
            if not isinstance(meta, dict) or set(meta) != keys:
                raise ValueError('metadata schema mismatch')
            if meta['algorithm'] != ALGORITHM or meta['format'] != FORMAT:
                raise ValueError('algorithm/format mismatch')
            identity = meta['identity_sha256']
            if not isinstance(identity, str) or len(identity) != 64 or any((character not in '0123456789abcdef' for character in identity)):
                raise ValueError('invalid identity hash')
            if any((type(meta[name]) is not int for name in ('nodes', 'edges', 'steps'))):
                raise ValueError('dimensions must be integers')
            if not isinstance(meta['limits'], dict) or set(meta['limits']) != {field.name for field in _i58_fields(ResourceLimits)}:
                raise ValueError('limits schema mismatch')
            limits = ResourceLimits(**meta['limits'])
            _preflight(meta['nodes'], meta['edges'], meta['steps'], limits)
            failed_meta = meta['failed_step']
            if failed_meta is not None and (not isinstance(failed_meta, dict) or set(failed_meta) != {'step_n', 'reason'}):
                raise ValueError('failed metadata schema mismatch')
            specs = _array_specs(meta['nodes'], meta['edges'], meta['steps'], meta['committed_steps'], failed_meta is not None)
            if set(names) != {'metadata.json'} | {name + '.npy' for name in specs}:
                raise ValueError('unexpected or missing archive members')
            for name, (shape, dtype) in specs.items():
                info = archive.getinfo(name + '.npy')
                with archive.open(info) as stream:
                    _read_header(stream, info, shape, dtype)
            arrays = {}
            for name, (shape, dtype) in specs.items():
                info = archive.getinfo(name + '.npy')
                with archive.open(info) as stream:
                    payload_bytes = _read_header(stream, info, shape, dtype)
                    payload = stream.read(payload_bytes + 1)
                    if len(payload) != payload_bytes:
                        raise ValueError('NPY truncated or trailing payload')
                    arrays[name] = _i58_np.frombuffer(payload, dtype=dtype).reshape(shape)
    kwargs = {name.removeprefix('input_'): array for name, array in arrays.items() if name.startswith('input_')}
    kwargs.update({name: meta[name] for name in ('source', 'datum', 'coords', 'dt_s', 'max_depth_m', 'geometry_mode')})
    inputs = HydraulicsInput(**kwargs, limits=limits)
    failed = None
    if failed_meta is not None:
        failed = FailedStep(**failed_meta, **{name.removeprefix('failed_'): array for name, array in arrays.items() if name.startswith('failed_')})
    result = HydraulicsResult(inputs, meta['status'], meta['committed_steps'], **{name: arrays[name] for name in ('stage_m', 'storage_m3', 'qedges_m3_s', 'time_s', 'ledger_m3')}, failed_step=failed, identity_sha256=meta['identity_sha256'])
    validate(result)
    return result

@_i59_njit(fastmath=False, cache=True)
def face_kernel(stage_left, stage_right, crest, previous_q, dt, width, distance, gravity, roughness):
    result = _i59_np.zeros(previous_q.size)
    depths = _i59_np.zeros(previous_q.size)
    for index in range(previous_q.size):
        depth = max(max(stage_left[index], stage_right[index]) - crest[index], 0.0)
        depths[index] = depth
        if depth > 0:
            old = previous_q[index] / width
            rhs = old - gravity * depth * dt * (stage_right[index] - stage_left[index]) / distance
            drag = gravity * dt * roughness ** 2 / depth ** (7 / 3)
            result[index] = width * 2 * rhs / (1 + _i59_math.sqrt(1 + 4 * drag * abs(rhs)))
    return (result, depths)

def regional_surface_hydraulics_accelerated_inertial_face_flux(stage_left, stage_right, crest, previous_q, dt_s, spacing_m, distance_m, budget):
    return face_kernel(stage_left, stage_right, crest, previous_q, dt_s, spacing_m, distance_m, budget.gravity_m_s2, budget.roughness_s_m_third)

@_i59_njit(fastmath=False, cache=True)
def limiter_kernel(depth, forcing, internal, boundary, left, right, cells, dt, area):
    outgoing_left = _i59_np.zeros(depth.size)
    outgoing_right = _i59_np.zeros(depth.size)
    outgoing_boundary = _i59_np.zeros(depth.size)
    for index in range(internal.size):
        outgoing_left[left[index]] += max(internal[index], 0.0)
    for index in range(internal.size):
        outgoing_right[right[index]] += max(-internal[index], 0.0)
    for index in range(boundary.size):
        outgoing_boundary[cells[index]] += max(boundary[index], 0.0)
    factors = _i59_np.ones(depth.size)
    count = 0
    minimum = 1.0
    for index in range(depth.size):
        outgoing = outgoing_left[index] + outgoing_right[index] + outgoing_boundary[index]
        available = depth[index] * area + dt * forcing[index]
        if outgoing * dt > available:
            factors[index] = available / (outgoing * dt) * (1 - 1e-12)
            count += 1
            minimum = min(minimum, factors[index])
    removed_internal = raw_internal = removed_boundary = raw_boundary = 0.0
    for index in range(internal.size):
        raw = internal[index]
        factor = factors[left[index]] if raw >= 0 else factors[right[index]]
        internal[index] *= factor
        removed_internal += abs(raw - internal[index])
        raw_internal += abs(raw)
    for index in range(boundary.size):
        raw = boundary[index]
        if raw >= 0:
            boundary[index] *= factors[cells[index]]
        removed_boundary += abs(raw - boundary[index])
        raw_boundary += abs(raw)
    return (count, (removed_internal + removed_boundary) * dt, (raw_internal + raw_boundary) * dt, minimum)

def regional_surface_hydraulics_accelerated_limited_inertial_fluxes(geometry, depth, previous_internal, previous_boundary, tailwater, forcing, dt_s, budget):
    arrays = geometry['arrays']
    stage = arrays['H2_m'].ravel() + depth
    spacing = geometry['metadata']['spacing_m']
    left, right, cells = (arrays['face_left'], arrays['face_right'], arrays['boundary_cell'])
    internal, _ = regional_surface_hydraulics_accelerated_inertial_face_flux(stage[left], stage[right], arrays['face_crest_m'], previous_internal, dt_s, spacing, spacing, budget)
    exterior = _i59_np.where(arrays['boundary_kind'] == 1, arrays['boundary_crest_m'], tailwater)
    boundary, _ = regional_surface_hydraulics_accelerated_inertial_face_flux(stage[cells], exterior, arrays['boundary_crest_m'], previous_boundary, dt_s, spacing, spacing / 2, budget)
    boundary[arrays['boundary_kind'] == 0] = 0.0
    raw_internal, raw_boundary = (internal.copy(), boundary.copy())
    count, removed, raw, minimum = limiter_kernel(depth, forcing, internal, boundary, left, right, cells, dt_s, spacing ** 2)
    removed = float((_i59_np.abs(raw_internal - internal).sum() + _i59_np.abs(raw_boundary - boundary).sum()) * dt_s)
    raw = float((_i59_np.abs(raw_internal).sum() + _i59_np.abs(raw_boundary).sum()) * dt_s)
    return (internal, boundary, {'limited_donors': count, 'removed_transfer_m3': removed, 'raw_transfer_m3': raw, 'minimum_factor': minimum, 'trigger': 'sum_outgoing_dt_exceeds_donor_volume_plus_local_input'})

def advance_accelerated_surface(*args, **kwargs):
    namespace = dict(advance_inertial_surface.__globals__)
    namespace['limited_inertial_fluxes'] = regional_surface_hydraulics_accelerated_limited_inertial_fluxes
    advance = _i59_types.FunctionType(advance_inertial_surface.__code__, namespace, advance_inertial_surface.__name__, advance_inertial_surface.__defaults__)
    advance.__kwdefaults__ = advance_inertial_surface.__kwdefaults__
    result = advance(*args, **kwargs)
    result['metadata']['execution_backend'] = 'numba_face_limiter_fastmath_false_v1_reference_control_flow'
    return result
METRIC_CHANNEL_SOLVER_ALGORITHM = 'manning-rectangular-explicit-v2'
MAX_TRACE_BYTES = 128 * 1024 * 1024

def _hydraulics(network, volume):
    area = volume / network.length_m
    depth = area / network.width_m
    perimeter = network.width_m + 2.0 * depth
    q = _i60_np.zeros_like(volume)
    wave = _i60_np.zeros_like(volume)
    active = (volume > 0.0) & _i60_np.isin(network.terminal_kind, ('interior', 'open_outflow'))
    with _i60_np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        q[active] = area[active] * (area[active] / perimeter[active]) ** (2.0 / 3.0) * _i60_np.sqrt(network.bed_slope[active]) / network.roughness[active]
        wave[active] = q[active] / area[active] * (5.0 / 3.0 - 4.0 * depth[active] / (3.0 * perimeter[active]))
    return (area, depth, q, wave)

def solve_channel(network, forcing, initial_volume_m3=None, config=None):
    """Route local inputs on a DAG; return complete or committed failed-prefix trace."""
    from terrain_pipeline.channel_geometry import ChannelConfig as _x9_ChannelConfig
    from terrain_pipeline.channel_geometry import ChannelForcing as _x10_ChannelForcing
    from terrain_pipeline.channel_geometry import ChannelNetwork as _x11_ChannelNetwork
    from terrain_pipeline.channel_geometry import _float_array as _x12_float_array
    from terrain_pipeline.channel_geometry import validate_channel_geometry_identity as _x13_validate_channel_geometry_identity
    if not isinstance(network, _x11_ChannelNetwork) or not isinstance(forcing, _x10_ChannelForcing):
        raise ValueError('ChannelNetwork and ChannelForcing required')
    _x13_validate_channel_geometry_identity(network.receiver, network.bed_elevation_m, network.bed_slope, network.receiver_distance_m)
    if config is None:
        config = _x9_ChannelConfig()
    if not isinstance(config, _x9_ChannelConfig):
        raise ValueError('ChannelConfig required')
    n = network.receiver.size
    if forcing.local_q_m3_s.shape[1] != n:
        raise ValueError('forcing node count does not match network')
    if initial_volume_m3 is None:
        volume = _i60_np.zeros(n, dtype=_i60_np.float64)
    else:
        volume = _x12_float_array(initial_volume_m3, (n,), 'initial_volume_m3', nonnegative=True).copy()
    capacity = network.length_m * network.width_m * network.max_depth_m
    if not _i60_np.isfinite(capacity).all() or _i60_np.any(volume > capacity):
        raise ValueError('initial volume or channel capacity outside depth limit')
    times = [float(forcing.time_seconds[0])]
    volumes = [volume.copy()]
    inflows, outflows, locals_, boundaries, residuals, cfls = ([], [], [], [], [], [])
    state_area, state_depth, state_q, state_wave = _hydraulics(network, volume)
    initial_stage = network.bed_elevation_m + state_depth
    if not all((_i60_np.isfinite(value).all() for value in (state_area, state_depth, state_q, state_wave, initial_stage))):
        raise ValueError('initial hydraulic state must be finite')
    areas = [state_area]
    depths = [state_depth]
    end_q = [state_q]
    stage = [initial_stage]
    failure = None
    interval = 0
    receiver = network.receiver
    interior = receiver >= 0
    outlet = network.terminal_kind == 'open_outflow'
    end_time = float(forcing.time_seconds[-1])
    trace_limit = MAX_TRACE_BYTES // (8 * (28 * n + 4))
    while times[-1] < end_time:
        if len(inflows) >= config.max_steps:
            failure = 'maximum step count exceeded'
            break
        if len(inflows) >= trace_limit:
            failure = 'trace byte budget exceeded'
            break
        now = times[-1]
        while interval + 1 < forcing.time_seconds.size - 1 and now >= forcing.time_seconds[interval + 1]:
            interval += 1
        segment_end = float(forcing.time_seconds[interval + 1])
        local = forcing.local_q_m3_s[interval]
        q = end_q[-1]
        wave = state_wave
        dt = min(config.max_dt_seconds, segment_end - now)
        moving = wave > 0.0
        if _i60_np.any(moving):
            dt = min(dt, float(_i60_np.min(config.cfl * network.length_m[moving] / wave[moving])))
        draining = q > 0.0
        if _i60_np.any(draining):
            dt = min(dt, float(_i60_np.min(config.cfl * volume[draining] / q[draining])))
        if not _i60_np.isfinite(dt) or dt <= 0.0 or (dt < config.min_dt_seconds and segment_end - now > config.min_dt_seconds):
            failure = 'minimum internal step required or nonfinite time step'
            break
        if now + dt == now:
            failure = 'time resolution exhausted'
            break
        next_time = segment_end if now + dt >= segment_end else now + dt
        if next_time - now > dt:
            next_time = float(_i60_np.nextafter(next_time, now))
        if next_time <= now:
            failure = 'time resolution exhausted'
            break
        actual_dt = next_time - now
        if actual_dt > config.max_dt_seconds * (1.0 + 1e-12):
            failure = 'maximum internal step exceeded at time resolution'
            break
        donor = _i60_np.zeros(n, dtype=_i60_np.float64)
        _i60_np.add.at(donor, receiver[interior], q[interior])
        with _i60_np.errstate(over='ignore', invalid='ignore'):
            next_volume = volume + actual_dt * (local + donor - q)
        if not _i60_np.isfinite(next_volume).all() or _i60_np.any(next_volume < -1e-12 * _i60_np.maximum(1.0, capacity)):
            failure = 'nonfinite or negative volume'
            break
        next_volume = _i60_np.maximum(next_volume, 0.0)
        if _i60_np.any(next_volume > capacity + 1e-12 * _i60_np.maximum(1.0, capacity)):
            failure = 'depth limit exceeded'
            break
        next_area, next_depth, next_q, next_wave = _hydraulics(network, next_volume)
        next_stage = network.bed_elevation_m + next_depth
        if not all((_i60_np.isfinite(value).all() for value in (next_area, next_depth, next_q, next_wave, next_stage))):
            failure = 'nonfinite hydraulic state'
            break
        boundary = actual_dt * _i60_np.where(outlet, q, 0.0)
        residual = next_volume - volume - actual_dt * (local + donor - q)
        cfl_number = float(_i60_np.max(wave * actual_dt / network.length_m))
        if not _i60_np.isfinite(boundary).all() or not _i60_np.isfinite(residual).all():
            failure = 'nonfinite water ledger'
            break
        if not _i60_np.isfinite(cfl_number) or cfl_number > config.cfl * (1.0 + 1e-12):
            failure = 'CFL bound exceeded at time resolution'
            break
        times.append(next_time)
        volumes.append(next_volume.copy())
        inflows.append(donor.copy())
        outflows.append(q.copy())
        locals_.append(local.copy())
        boundaries.append(boundary)
        residuals.append(residual)
        cfls.append(cfl_number)
        areas.append(next_area)
        depths.append(next_depth)
        stage.append(next_stage)
        end_q.append(next_q)
        volume = next_volume
        state_wave = next_wave
    step_shape = (len(inflows), n)
    result = {'arrays': {'time_seconds': _i60_np.asarray(times, _i60_np.float64), 'volume_m3': _i60_np.stack(volumes), 'inflow_q_m3_s': _i60_np.stack(inflows) if inflows else _i60_np.empty(step_shape), 'outflow_q_m3_s': _i60_np.stack(outflows) if outflows else _i60_np.empty(step_shape), 'local_q_m3_s': _i60_np.stack(locals_) if locals_ else _i60_np.empty(step_shape), 'outflow_end_q_m3_s': _i60_np.stack(end_q), 'depth_m': _i60_np.stack(depths), 'stage_m': _i60_np.stack(stage), 'area_m2': _i60_np.stack(areas), 'boundary_outflow_volume_m3': _i60_np.stack(boundaries) if boundaries else _i60_np.empty(step_shape), 'balance_residual_m3': _i60_np.stack(residuals) if residuals else _i60_np.empty(step_shape), 'cfl_number': _i60_np.asarray(cfls, _i60_np.float64)}, 'metadata': {'algorithm': METRIC_CHANNEL_SOLVER_ALGORITHM, 'status': 'failed_prefix' if failure else 'complete', 'failure_reason': failure, 'requested_end_time_seconds': end_time, 'last_time_seconds': times[-1], 'config': _i60_asdict(config)}}
    return result
METRIC_DOMAIN_CHANNEL_HYDRAULICS_SCHEMA = 'river-domain-channel-hydraulics-candidate-v1'
METRIC_DOMAIN_CHANNEL_HYDRAULICS_ALGORITHM = 'raw-domain-local-release-kinematic-bridge-v3-irregular-metric'
MAX_BYTES = 256 * 1024 * 1024
LIMITATIONS = ('raw_conditioning face only; R6 carved channel geometry is not consumed', 'kinematic-wave candidate only; no dynamic backwater', 'no conservative floodplain inundation or lake evolution', 'no cross-tile accumulated upstream inflow certification', 'outside-core cells have no local production in this source; not a complete natural catchment', 'explicit engineering parameters are not calibrated hydraulic parameters', 'not complete R7 certification and not stage-one certification')
TOPOLOGY_FIELDS = ('receiver', 'terminal', 'height_m', 'ocean', 'ocean_terminal', 'accepted', 'unresolved', 'in_core')
PARAMETER_SOURCES = ('width_m', 'control_length_m', 'max_depth_m', 'roughness')

def _volume_sum(volume):
    """Canonical interval-major/node-major binary64 sum, independent of NumPy reductions."""
    return _i61_math.fsum((float(value) for value in volume.ravel(order='C')))

def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + ' requires explicit provenance text')
    return value

def _array(value, dtype, shape, name):
    value = _i61_np.asarray(value)
    if value.dtype != _i61_np.dtype(dtype) or value.shape != shape:
        raise ValueError(name + ' has invalid dtype/shape')
    if value.dtype.kind == 'f' and (not _i61_np.isfinite(value).all()):
        raise ValueError(name + ' must be finite')
    return value

def _source(arrays, metadata):
    """Reconstruct terrain and audit the persisted production/topology relationship."""
    from terrain_pipeline.common_infra import TerrainGrid as _i61_TerrainGrid
    from terrain_pipeline.channel_geometry import validate_receiver_acyclic as _x18_validate_receiver_acyclic
    terrain = _i61_TerrainGrid(arrays['source_height_m'], arrays['source_valid_mask'], **metadata['terrain_metadata'])
    if terrain.identity_sha256 != metadata['terrain_identity_sha256']:
        raise ValueError('terrain identity mismatch')
    shape = terrain.elevation_m.shape
    size = terrain.elevation_m.size
    frame = metadata['topology_frame']
    if frame['shape'] != list(shape) or frame['spacing_m'] != terrain.dx_m or frame['spacing_m'] != terrain.dz_m or (frame['origin_x_m'] != terrain.x0_m) or (frame['origin_z_m'] != terrain.z0_m):
        raise ValueError('topology and terrain metric frame differ')
    for key in TOPOLOGY_FIELDS:
        dtype = _i61_np.float64 if key == 'height_m' else _i61_np.int64 if key in ('receiver', 'terminal') else bool
        _array(arrays['topology_' + key], dtype, shape, key)
    if not _i61_np.array_equal(arrays['topology_height_m'], terrain.elevation_m):
        raise ValueError('topology and terrain height differ')
    receiver = arrays['topology_receiver'].ravel()
    terminal = arrays['topology_terminal'].ravel()
    if _i61_np.any((receiver < -1) | (receiver >= size)) or _i61_np.any((terminal < 0) | (terminal >= size)):
        raise ValueError('invalid original receiver/terminal')
    _x18_validate_receiver_acyclic(receiver)
    interior = receiver >= 0
    if not _i61_np.array_equal(terminal[interior], terminal[receiver[interior]]) or not _i61_np.array_equal(terminal[~interior], _i61_np.flatnonzero(~interior)):
        raise ValueError('original terminal does not match receiver closure')
    ocean = arrays['topology_ocean'].ravel()
    if not _i61_np.array_equal(arrays['topology_ocean_terminal'].ravel(), ocean[terminal]):
        raise ValueError('original ocean terminal classification mismatch')
    accepted = arrays['topology_accepted'].ravel()
    unresolved = arrays['topology_unresolved'].ravel()
    if _i61_np.any(accepted & (unresolved | ocean)):
        raise ValueError('accepted production cannot be ocean or unresolved')
    producing = arrays['producing_cell_ids']
    expected = _i61_np.flatnonzero(accepted & arrays['topology_in_core'].ravel())
    _array(producing, _i61_np.int64, expected.shape, 'producing_cell_ids')
    if not _i61_np.array_equal(producing, expected):
        raise ValueError('producing cells must equal accepted core production')
    count, dt = (metadata['interval_count'], metadata['dt_s'])
    if type(count) is not int or not 1 <= count <= 60 or type(dt) not in (int, float) or (not _i61_np.isfinite(dt)) or (dt <= 0.0):
        raise ValueError('invalid source physical interval count/dt_s')
    release = _array(arrays['released_per_interval_grid_m3'], _i61_np.float64, (count,) + shape, 'released_per_interval_grid_m3')
    total = _array(arrays['released_grid_m3'], _i61_np.float64, shape, 'released_grid_m3')
    if _i61_np.any(release < 0.0) or _i61_np.any(release.reshape(count, -1)[:, ~_i61_np.isin(_i61_np.arange(size), producing)] != 0.0) or (not _i61_np.allclose(release.sum(axis=0), total, rtol=1e-12, atol=1e-10)):
        raise ValueError('interval production must match totals and producing support')
    return terrain

def _selection(arrays, metadata, terrain):
    from terrain_pipeline.common_infra import identity as _i61_identity
    from terrain_pipeline.drainage import diagnostic_mesh as _i61_diagnostic_mesh
    from terrain_pipeline.channel_geometry import ChannelForcing as _x15_ChannelForcing
    from terrain_pipeline.channel_geometry import ChannelNetwork as _x16_ChannelNetwork
    from terrain_pipeline.channel_geometry import MAX_CHANNEL_NODES as _x17_MAX_CHANNEL_NODES
    from terrain_pipeline.channel_geometry import validate_receiver_acyclic as _x18_validate_receiver_acyclic
    ids = arrays['node_cell_ids']
    if ids.dtype != _i61_np.int64 or ids.ndim != 1 or (not 1 <= ids.size <= _x17_MAX_CHANNEL_NODES):
        raise ValueError('bounded int64 selected ids required')
    n = ids.size
    if _i61_np.unique(ids).size != n or _i61_np.any((ids < 0) | (ids >= terrain.elevation_m.size)):
        raise ValueError('invalid selected ids')
    if not terrain.valid_mask.ravel()[ids].all() or arrays['topology_unresolved'].ravel()[ids].any():
        raise ValueError('unknown selected terrain/topology')
    receiver = _array(arrays['selected_receiver'], _i61_np.int64, (n,), 'selected_receiver')
    if _i61_np.any((receiver < -1) | (receiver >= n)):
        raise ValueError('receiver outside selected graph: rejected unresolved_border')
    original = _array(arrays['original_receiver_cell_ids'], _i61_np.int64, (n,), 'original_receiver_cell_ids')
    if not _i61_np.array_equal(original, arrays['topology_receiver'].ravel()[ids]):
        raise ValueError('original receiver snapshot mismatch')
    links = receiver >= 0
    if _i61_np.any((original >= 0) != links) or not _i61_np.array_equal(original[links], ids[receiver[links]]):
        raise ValueError('omitted or changed receiver: rejected unresolved_border')
    _x18_validate_receiver_acyclic(receiver)
    missing = _i61_np.setdiff1d(arrays['producing_cell_ids'], ids)
    if missing.size:
        _text(metadata['coverage_note'], 'missing upstream contributions coverage_note')
    elif metadata['coverage_note'] is not None:
        _text(metadata['coverage_note'], 'coverage_note')
    policies = metadata['terminal_policy']
    expected_keys = {str(int(cell)) for cell in ids[~links]}
    if not isinstance(policies, dict) or set(policies) != expected_keys:
        raise ValueError('explicit policy required for every original terminal only')
    kind = _i61_np.full(n, 'interior', dtype='U24')
    slope = _i61_np.zeros(n, _i61_np.float64)
    for node in _i61_np.flatnonzero(~links):
        policy = policies[str(int(ids[node]))]
        if not isinstance(policy, dict) or set(policy) != {'classification', 'kind', 'slope', 'source'}:
            raise ValueError('terminal policy requires classification/kind/slope/source')
        _text(policy['source'], 'terminal policy source')
        ocean = bool(arrays['topology_ocean'].ravel()[ids[node]])
        if arrays['topology_terminal'].ravel()[ids[node]] != ids[node]:
            raise ValueError('negative local receiver is not an original terminal')
        if (policy['classification'], policy['kind']) != (('ocean', 'open_outflow') if ocean else ('closed_basin', 'closed_wall')):
            raise ValueError('terminal policy disagrees with known ocean/closed basin')
        value = policy['slope']
        if type(value) not in (int, float) or not _i61_np.isfinite(value) or (value <= 0.0 if ocean else value != 0.0):
            raise ValueError('explicit positive ocean slope or zero closed-wall slope required')
        kind[node] = policy['kind']
        slope[node] = value
    mesh = _i61_diagnostic_mesh(terrain, unmasked=True)
    points = _i61_np.column_stack((mesh.node_x_m[ids], mesh.node_z_m[ids]))
    bed = terrain.elevation_m.ravel()[ids]
    distance = _i61_np.zeros(n, _i61_np.float64)
    distance[links] = _i61_np.linalg.norm(points[links] - points[receiver[links]], axis=1)
    slope[links] = (bed[links] - bed[receiver[links]]) / distance[links]
    sources = metadata['parameter_sources']
    if not isinstance(sources, dict) or set(sources) != set(PARAMETER_SOURCES):
        raise ValueError('explicit parameter_sources required')
    for name in PARAMETER_SOURCES:
        _text(sources[name], name)
    _text(metadata['geometry_source'], 'geometry_source')
    network_identity = _i61_identity({key: arrays[key] for key in ('node_cell_ids', 'selected_receiver', 'original_receiver_cell_ids', 'width_m', 'control_length_m', 'max_depth_m', 'roughness')}, {'terrain_identity_sha256': terrain.identity_sha256, 'terminal_policy': policies, 'parameter_sources': sources, 'geometry_source': metadata['geometry_source'], 'source_face': 'raw_conditioning'})
    network = _x16_ChannelNetwork(receiver, arrays['control_length_m'], arrays['width_m'], bed, slope, arrays['roughness'], arrays['max_depth_m'], kind, network_identity, metadata['geometry_source'], sources['roughness'], distance)
    time = _i61_np.arange(metadata['interval_count'] + 1, dtype=_i61_np.float64) * metadata['dt_s']
    volume = arrays['released_per_interval_grid_m3'].reshape(metadata['interval_count'], -1)[:, ids]
    source_identity = _i61_identity({'time_seconds': time, 'selected_local_volume_m3': volume, 'producing_cell_ids': arrays['producing_cell_ids'], 'node_cell_ids': ids}, {'source_flow_identity_sha256': metadata['source_flow_identity_sha256']})
    forcing = _x15_ChannelForcing(time, _i61_np.asarray(volume / metadata['dt_s'], _i61_np.float64), source_identity)
    missing_upstream = missing[_i61_np.isin(arrays['topology_terminal'].ravel()[missing], ids[~links])]
    coverage = {'missing_producing_cell_count': int(missing.size), 'missing_upstream_contributing_cell_count': int(missing_upstream.size), 'missing_upstream_contributing_release_m3': _volume_sum(arrays['released_per_interval_grid_m3'].reshape(metadata['interval_count'], -1)[:, missing_upstream]), 'missing_producing_release_m3': _volume_sum(arrays['released_per_interval_grid_m3'].reshape(metadata['interval_count'], -1)[:, missing]), 'selected_input_volume_m3': _volume_sum(volume), 'current_production_downstream_closure_complete': missing.size == 0, 'upstream_contributions_status': 'not_certified', 'cross_tile_inflow_status': 'not_certified'}
    return (network, forcing, coverage)

def _flow_identity(arrays, metadata):
    from terrain_pipeline.common_infra import identity as _i61_identity
    names = {'topology_' + key for key in TOPOLOGY_FIELDS} | {'producing_cell_ids', 'released_per_interval_grid_m3', 'released_grid_m3'}
    return _i61_identity({key: arrays[key] for key in names}, {key: metadata[key] for key in ('topology_frame', 'dt_s', 'interval_count')})

def build_domain_channel_hydraulics(terrain, flow_topology, *, node_cell_ids, receiver, width_m, control_length_m, max_depth_m, roughness, parameter_sources, terminal_policy, geometry_source, coverage_note, config, initial_volume_m3=None):
    """Route actual interval local releases once on an explicit original-bed graph.

    Policies are keyed by original flat terminal id (string), each containing
    classification, kind, slope, source. Only ocean/open_outflow with an explicit
    positive engineering slope and closed_basin/closed_wall with zero slope are
    supported. Omitted producing cells require coverage_note; missing receivers
    are always rejected. Even full current production closure is not a certified
    natural catchment. Width/control length/depth/roughness arrays are float64.
    """
    from terrain_pipeline.common_infra import identity as _i61_identity
    from terrain_pipeline.common_infra import readonly as _i61_readonly
    from terrain_pipeline.common_infra import TerrainGrid as _i61_TerrainGrid
    from terrain_pipeline.surface_rivers.metric_channel_product import make_channel_product as _i61_make_channel_product
    from terrain_pipeline.channel_geometry import ChannelConfig as _x14_ChannelConfig
    if not isinstance(terrain, _i61_TerrainGrid) or not isinstance(flow_topology, dict):
        raise ValueError('TerrainGrid and explicit domain_flow_topology result required')
    if not isinstance(config, _x14_ChannelConfig):
        raise ValueError('explicit ChannelConfig required')
    source_keys = {'topology', 'producing_flat', 'released_per_interval_grid_m3', 'released_grid_m3', 'dt_s', 'interval_count'}
    if not source_keys.issubset(flow_topology):
        raise ValueError('incomplete domain_flow_topology result')
    topology = flow_topology['topology']
    if not isinstance(topology, dict) or not (set(TOPOLOGY_FIELDS) | {'shape', 'spacing_m', 'origin_x_m', 'origin_z_m'}).issubset(topology):
        raise ValueError('incomplete original domain topology')
    arrays = {'topology_' + key: _i61_np.asarray(topology[key]).copy() for key in TOPOLOGY_FIELDS}
    arrays.update(source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(), producing_cell_ids=_i61_np.asarray(flow_topology['producing_flat']).copy(), released_per_interval_grid_m3=_i61_np.asarray(flow_topology['released_per_interval_grid_m3']).copy(), released_grid_m3=_i61_np.asarray(flow_topology['released_grid_m3']).copy())
    for key, value in (('node_cell_ids', node_cell_ids), ('selected_receiver', receiver), ('width_m', width_m), ('control_length_m', control_length_m), ('max_depth_m', max_depth_m), ('roughness', roughness)):
        arrays[key] = _i61_np.asarray(value).copy()
    ids = arrays['node_cell_ids']
    if ids.dtype != _i61_np.int64 or ids.ndim != 1 or _i61_np.any((ids < 0) | (ids >= terrain.elevation_m.size)):
        raise ValueError('valid int64 node_cell_ids required')
    arrays['original_receiver_cell_ids'] = arrays['topology_receiver'].ravel()[ids].copy()
    metadata = {'schema': METRIC_DOMAIN_CHANNEL_HYDRAULICS_SCHEMA, 'algorithm': METRIC_DOMAIN_CHANNEL_HYDRAULICS_ALGORITHM, 'terrain_metadata': {key: getattr(terrain, key) for key in terrain.__dataclass_fields__ if key not in ('elevation_m', 'valid_mask')}, 'terrain_identity_sha256': terrain.identity_sha256, 'topology_frame': {'shape': list(topology['shape']), 'spacing_m': topology['spacing_m'], 'origin_x_m': topology['origin_x_m'], 'origin_z_m': topology['origin_z_m']}, 'dt_s': flow_topology['dt_s'], 'interval_count': flow_topology['interval_count'], 'parameter_sources': dict(parameter_sources), 'terminal_policy': _i61_deepcopy(terminal_policy), 'geometry_source': geometry_source, 'coverage_note': coverage_note, 'source_face': 'raw_conditioning', 'r6_carving_consumed': False, 'limitations': list(LIMITATIONS), 'hydraulic_ready': False, 'natural_outlet_verified': False, 'publishable': False}
    _source(arrays, metadata)
    metadata['source_flow_identity_sha256'] = _flow_identity(arrays, metadata)
    network, forcing, coverage = _selection(arrays, metadata, terrain)
    child = _i61_make_channel_product(network, forcing, solve_channel(network, forcing, initial_volume_m3, config))
    metadata.update(coverage=coverage, geometry_identity_sha256=network.source_identity_sha256, channel_identity_sha256=child['identity_sha256'], channel_metadata=child['metadata'])
    arrays.update({'channel_' + key: value for key, value in child['arrays'].items()})
    arrays = {key: _i61_readonly(value.copy()) for key, value in arrays.items()}
    record = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i61_identity(arrays, metadata)}
    validate_domain_channel_hydraulics(record)
    return record

def validate_domain_channel_hydraulics(record):
    """Cold-check parent/child topology, local forcing and summaries, not only hashes."""
    from terrain_pipeline.common_infra import identity as _i61_identity
    from terrain_pipeline.surface_rivers.metric_channel_product import validate_channel_product as _i61_validate_channel_product
    if not isinstance(record, dict) or set(record) != {'arrays', 'metadata', 'identity_sha256'}:
        raise ValueError('invalid domain hydraulic bundle')
    arrays, meta = (record['arrays'], record['metadata'])
    if meta.get('schema') != METRIC_DOMAIN_CHANNEL_HYDRAULICS_SCHEMA or meta.get('algorithm') != METRIC_DOMAIN_CHANNEL_HYDRAULICS_ALGORITHM or meta.get('source_face') != 'raw_conditioning' or (meta.get('r6_carving_consumed') is not False) or (meta.get('limitations') != list(LIMITATIONS)) or any((meta.get(key) is not False for key in ('hydraulic_ready', 'natural_outlet_verified', 'publishable'))) or (sum((value.nbytes for value in arrays.values())) > MAX_BYTES) or (record['identity_sha256'] != _i61_identity(arrays, meta)):
        raise ValueError('domain hydraulic identity/schema/scope mismatch')
    terrain = _source(arrays, meta)
    if meta['source_flow_identity_sha256'] != _flow_identity(arrays, meta):
        raise ValueError('source flow identity mismatch')
    network, forcing, coverage = _selection(arrays, meta, terrain)
    if meta['coverage'] != coverage or meta['geometry_identity_sha256'] != network.source_identity_sha256:
        raise ValueError('coverage or geometry summary mismatch')
    child = {'arrays': {key[len('channel_'):]: value for key, value in arrays.items() if key.startswith('channel_')}, 'metadata': meta['channel_metadata'], 'identity_sha256': meta['channel_identity_sha256']}
    _i61_validate_channel_product(child)
    ca, cm = (child['arrays'], child['metadata'])
    for name in ('receiver', 'length_m', 'width_m', 'bed_elevation_m', 'bed_slope', 'roughness', 'max_depth_m', 'terminal_kind', 'receiver_distance_m'):
        if not _i61_np.array_equal(ca['network_' + name], getattr(network, name)):
            raise ValueError('nested channel geometry disagrees with original selected graph: ' + name)
    if not _i61_np.array_equal(ca['forcing_time_seconds'], forcing.time_seconds) or not _i61_np.array_equal(ca['forcing_local_q_m3_s'], forcing.local_q_m3_s) or cm['network_source_identity_sha256'] != network.source_identity_sha256 or (cm['forcing_source_identity_sha256'] != forcing.source_identity_sha256) or (cm['section_source'] != network.section_source) or (cm['roughness_source'] != network.roughness_source):
        raise ValueError('nested channel source/local forcing relationship mismatch')
    expected = {'topology_' + key for key in TOPOLOGY_FIELDS} | {'source_height_m', 'source_valid_mask', 'producing_cell_ids', 'released_per_interval_grid_m3', 'released_grid_m3', 'node_cell_ids', 'selected_receiver', 'original_receiver_cell_ids', 'width_m', 'control_length_m', 'max_depth_m', 'roughness'}
    if set(arrays) != expected | {'channel_' + key for key in ca}:
        raise ValueError('unexpected domain hydraulic arrays')
    return True

def save_domain_channel_hydraulics(path, record):
    from terrain_pipeline.common_infra import save_bundle as _i61_save_bundle
    _i61_save_bundle(path, record, validator=validate_domain_channel_hydraulics)

def load_domain_channel_hydraulics(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _i61_load_bundle
    record = _i61_load_bundle(path, expected_sha256=expected_sha256, validator=validate_domain_channel_hydraulics, max_bytes=MAX_BYTES)
    if record['identity_sha256'] != expected_identity:
        raise ValueError('external domain hydraulic identity mismatch')
    return record
WORLD_FLOODPLAIN_2D_SCHEMA = 'world-floodplain-two-dimensional-adapter-v1'
BOUNDARY_CLOSED = 0
BOUNDARY_DRAINAGE = 1
BOUNDARY_PRESCRIBED = 2
CARVED_EPSILON_M = 0.01

@_i62_dataclass(frozen=True)
class FloodplainWindow:
    """A regular sub-page of a fine terrain field, in absolute world metres."""
    origin_m_xz: tuple
    spacing_m: float
    block_cells: int = 1

    def validate(self):
        origin = _i62_np.asarray(self.origin_m_xz, _i62_np.float64)
        if origin.shape != (2,) or not _i62_np.isfinite(origin).all():
            raise ValueError('finite window origin')
        if type(self.spacing_m) not in (int, float) or not _i62_math.isfinite(self.spacing_m) or self.spacing_m <= 0:
            raise ValueError('positive finite fine spacing')
        if type(self.block_cells) is not int or self.block_cells < 1:
            raise ValueError('positive integer block aggregation')

def aggregate_fine_field(height_m, block_cells):
    """Block-mean aggregation of a fine page; the trailing partial row/column is dropped.

    Block mean (not block minimum) is used because the local-inertial solver needs one
    water column per cell, and a block minimum would exaggerate the conveyance of a
    cell that is mostly high ground.
    """
    height = _i62_np.asarray(height_m, _i62_np.float64)
    if height.ndim != 2 or not _i62_np.isfinite(height).all():
        raise ValueError('finite two-dimensional fine field required')
    if type(block_cells) is not int or block_cells < 1:
        raise ValueError('positive integer block aggregation')
    if block_cells == 1:
        return height.copy()
    rows = height.shape[0] // block_cells
    columns = height.shape[1] // block_cells
    if rows < 2 or columns < 2:
        raise ValueError('aggregated page too small')
    trimmed = height[:rows * block_cells, :columns * block_cells]
    return trimmed.reshape(rows, block_cells, columns, block_cells).mean(axis=(1, 3))

def cell_centres(window, shape):
    """Absolute world cell-centre coordinates of the aggregated page."""
    window.validate()
    xs = window.origin_m_xz[0] + (_i62_np.arange(shape[1]) * window.block_cells + window.block_cells / 2.0) * window.spacing_m
    zs = window.origin_m_xz[1] + (_i62_np.arange(shape[0]) * window.block_cells + window.block_cells / 2.0) * window.spacing_m
    return (xs, zs)

def window_extent(window, shape):
    """Outer world extent covered by the aggregated page (cell edges, not centres)."""
    window.validate()
    step = window.spacing_m * window.block_cells
    x0 = float(window.origin_m_xz[0])
    z0 = float(window.origin_m_xz[1])
    return (x0, x0 + shape[1] * step, z0, z0 + shape[0] * step)

def contains_points(window, shape, points_xz):
    """Boolean mask of reach nodes lying inside the window extent."""
    x0, x1, z0, z1 = window_extent(window, shape)
    points = _i62_np.asarray(points_xz, _i62_np.float64)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError('node coordinates require shape (n, 2)')
    return (points[:, 0] >= x0) & (points[:, 0] <= x1) & (points[:, 1] >= z0) & (points[:, 1] <= z1)

def crossing_edges(window, shape, node_xz_m, receiver):
    """Reach edges that cross the window boundary, with their crossing point.

    An edge "crosses" when exactly one of its two nodes is inside the window. The
    crossing point is where the edge segment meets the window extent, so the source
    sits on the domain boundary rather than smeared over the interior.
    """
    nodes = _i62_np.asarray(node_xz_m, _i62_np.float64)
    receiver = _i62_np.asarray(receiver, _i62_np.int64)
    if nodes.ndim != 2 or nodes.shape[1] != 2:
        raise ValueError('node coordinates require shape (n, 2)')
    if receiver.shape != (nodes.shape[0],):
        raise ValueError('receiver must be one index per node')
    inside = contains_points(window, shape, nodes)
    x0, x1, z0, z1 = window_extent(window, shape)
    found = []
    for donor in range(nodes.shape[0]):
        target = int(receiver[donor])
        if target < 0:
            continue
        if inside[donor] == inside[target]:
            continue
        start = nodes[donor]
        segment = nodes[target] - start
        hits = []
        for axis, low, high in ((0, x0, x1), (1, z0, z1)):
            if segment[axis] == 0.0:
                continue
            for plane, name in ((low, 'min'), (high, 'max')):
                t = (plane - start[axis]) / segment[axis]
                if not 0.0 <= t <= 1.0:
                    continue
                point = start + t * segment
                if x0 - 1e-06 <= point[0] <= x1 + 1e-06 and z0 - 1e-06 <= point[1] <= z1 + 1e-06:
                    hits.append((t, axis, name, point))
        if not hits:
            continue
        hits.sort(key=lambda item: item[0])
        _, axis, name, point = hits[0]
        found.append({'donor': int(donor), 'receiver': target, 'inflow': not bool(inside[donor]), 'axis': 'x' if axis == 0 else 'z', 'side': name, 'point_m_xz': (float(point[0]), float(point[1]))})
    found.sort(key=lambda item: (item['axis'], item['side'], item['point_m_xz']))
    return found

def _cell_of(window, shape, point):
    step = window.spacing_m * window.block_cells
    column = int(_i62_math.floor((point[0] - window.origin_m_xz[0]) / step))
    row = int(_i62_math.floor((point[1] - window.origin_m_xz[1]) / step))
    return (min(max(row, 0), shape[0] - 1), min(max(column, 0), shape[1] - 1))

def source_locations(window, shape, crossings, node_width_m):
    """Map each crossing edge to the boundary cells that receive its water.

    A crossing carries the donor node's own declared channel width, so the inflow is
    spread over the boundary cells that lie within one half-width either side of the
    crossing point. Spreading it over the *carved* run instead is wrong here: the
    carve follows the reach centreline, which can run along the domain edge for
    kilometres, and that would smear a point inflow across the whole border.
    """
    widths = _i62_np.asarray(node_width_m, _i62_np.float64)
    if not _i62_np.isfinite(widths).all() or (widths <= 0.0).any():
        raise ValueError('every donor needs a positive declared width')
    step = window.spacing_m * window.block_cells
    rows, columns = shape
    locations = []
    for crossing in crossings:
        half = 0.5 * float(widths[crossing['donor']])
        point = crossing['point_m_xz']
        if crossing['axis'] == 'x':
            candidates = [(row, 0) if crossing['side'] == 'min' else (row, columns - 1) for row in range(rows)]
            distance = _i62_np.abs(window.origin_m_xz[1] + (_i62_np.arange(rows) * window.block_cells + window.block_cells / 2.0) * window.spacing_m - point[1])
        else:
            candidates = [(0, column) if crossing['side'] == 'min' else (rows - 1, column) for column in range(columns)]
            distance = _i62_np.abs(window.origin_m_xz[0] + (_i62_np.arange(columns) * window.block_cells + window.block_cells / 2.0) * window.spacing_m - point[0])
        chosen = [cell for cell, gap in zip(candidates, distance) if gap <= half + step]
        if not chosen:
            row, column = _cell_of(window, shape, point)
            chosen = [(row, column)]
        locations.append({'crossing': crossing, 'cells': chosen, 'weights': _i62_np.full(len(chosen), 1.0 / len(chosen)), 'stated_width_m': float(widths[crossing['donor']]), 'receptor_span_m': float(len(chosen) * step)})
    return locations

def source_matrix(shape, locations):
    """Row-stochastic (crossing x cell) matrix so a volume lands exactly once."""
    matrix = _i62_np.zeros((len(locations), shape[0] * shape[1]), _i62_np.float64)
    for index, location in enumerate(locations):
        for cell, weight in zip(location['cells'], location['weights']):
            matrix[index, cell[0] * shape[1] + cell[1]] += float(weight)
    if locations and (not _i62_np.allclose(matrix.sum(axis=1), 1.0, atol=1e-12)):
        raise ValueError('source weights must sum to one per crossing edge')
    return matrix

def boundary_cells(shape):
    """Boundary cells in `prepare_surface_geometry` order (west, east, north, south)."""
    grid = _i62_np.arange(int(_i62_np.prod(shape)), dtype=_i62_np.int64).reshape(shape)
    return _i62_np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]

def boundary_cell_coordinates(shape):
    """Row/column of each boundary cell, in the same order as `boundary_cells`.

    The order must match `prepare_surface_geometry`'s
    ``np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]``: the whole west column,
    then the whole east column, then the north row, then the south row.
    """
    rows, columns = shape
    coordinates = [(row, 0) for row in range(rows)]
    coordinates += [(row, columns - 1) for row in range(rows)]
    coordinates += [(0, column) for column in range(columns)]
    coordinates += [(rows - 1, column) for column in range(columns)]
    return coordinates

def rim_outlet_cells(shape, height_m, *, margin_cells=2, exclude=()):
    """Boundary cells through which the aggregated page actually spills.

    The rim is the lowest boundary cell that is **not** an injection receptor: letting
    the outflow share a cell with the inflow would short-circuit the inflow straight
    back out of the domain before it could spread over the terrain. Only the lowest
    run plus a small margin is opened, so the other edges stay closed.
    """
    height = _i62_np.asarray(height_m, _i62_np.float64)
    if height.shape != tuple(shape):
        raise ValueError('height must match the declared shape')
    excluded = set(exclude)
    coordinates = boundary_cell_coordinates(shape)
    values = _i62_np.asarray([height[row, column] for row, column in coordinates], _i62_np.float64)
    allowed = _i62_np.array([cell not in excluded for cell in coordinates])
    if not allowed.any():
        raise ValueError('every boundary cell is an injection receptor; cannot place a rim outlet')
    lowest = float(values[allowed].min())
    chosen = [cell for cell, value, ok in zip(coordinates, values, allowed) if ok and value <= lowest + 1e-09]
    rows, columns = shape
    opened = set(chosen)
    for row, column in chosen:
        for offset in range(1, int(margin_cells) + 1):
            neighbours = []
            if row == 0:
                neighbours = [(0, column + offset), (0, column - offset)]
            elif row == rows - 1:
                neighbours = [(rows - 1, column + offset), (rows - 1, column - offset)]
            elif column == 0:
                neighbours = [(row + offset, 0), (row - offset, 0)]
            elif column == columns - 1:
                neighbours = [(row + offset, columns - 1), (row - offset, columns - 1)]
            for cell_row, cell_column in neighbours:
                if 0 <= cell_row < rows and 0 <= cell_column < columns:
                    opened.add((cell_row, cell_column))
    opened -= excluded
    return (sorted(opened), lowest, [])

def boundary_certificate(shape, height_m, *, outlet_cells=None):
    """Boundary kinds/crests for the local-inertial solver.

    Everything is closed except the declared rim outlet, which is an engineering
    drainage face whose crest is the terrain elevation there: a basin cannot hold
    water above its own rim, so the surplus has to be able to leave and be counted.
    """
    height = _i62_np.asarray(height_m, _i62_np.float64)
    if height.shape != tuple(shape):
        raise ValueError('height must match the declared shape')
    exterior = boundary_cells(shape)
    coordinates = boundary_cell_coordinates(shape)
    kinds = _i62_np.zeros(exterior.size, _i62_np.int64)
    crests = height.ravel()[exterior].copy()
    position = {cell: index for index, cell in enumerate(coordinates)}
    opened = set(outlet_cells or ())
    missing = opened - set(position)
    if missing:
        raise ValueError('declared outlet must lie on the domain boundary')
    for cell in opened:
        kinds[position[cell]] = BOUNDARY_DRAINAGE
    return (kinds, crests, exterior)

def build_domain(window, height_m, *, source_identity, outlet_cells=None, margin_cells=2, injection_cells=()):
    """Assemble the geometry the frozen solver expects, plus its boundary certificate."""
    window.validate()
    height = _i62_np.asarray(height_m, _i62_np.float64)
    if height.ndim != 2 or not _i62_np.isfinite(height).all():
        raise ValueError('finite two-dimensional aggregated page required')
    shape = height.shape
    rim_cells, rim_elevation, rim_shares_inflow = rim_outlet_cells(shape, height, margin_cells=margin_cells, exclude=injection_cells)
    if outlet_cells is None:
        outlet_cells = rim_cells
    kinds, crests, exterior = boundary_certificate(shape, height, outlet_cells=outlet_cells)
    geometry = prepare_surface_geometry(height, spacing_m=float(window.spacing_m * window.block_cells), origin_m_xz=window.origin_m_xz, source_identity=source_identity, boundary_kind=kinds, boundary_crest_m=crests)
    validate_surface_geometry(geometry, trusted_height=height, source_identity=source_identity)
    return {'geometry': geometry, 'shape': shape, 'exterior': exterior, 'outlet_cells': sorted(outlet_cells), 'rim_elevation_m': float(rim_elevation), 'rim_candidate_cells': rim_cells, 'rim_shares_inflow_cells': rim_shares_inflow, 'closed_faces': int((kinds == BOUNDARY_CLOSED).sum()), 'drainage_faces': int((kinds == BOUNDARY_DRAINAGE).sum())}

def hydrograph(volumes_per_interval, interval_s):
    """Per-interval volume -> mean discharge, refusing negative water."""
    volumes = _i62_np.asarray(volumes_per_interval, _i62_np.float64)
    if volumes.ndim != 2:
        raise ValueError('injection volumes require shape (intervals, crossings)')
    if not _i62_np.isfinite(volumes).all() or (volumes < 0).any():
        raise ValueError('injection volumes must be finite and non-negative')
    if type(interval_s) not in (int, float) or not _i62_math.isfinite(interval_s) or interval_s <= 0:
        raise ValueError('positive finite interval')
    return volumes / float(interval_s)

def interval_forcing(shape, matrix, discharge_per_crossing):
    """m3/s per cell for one interval, conserving each crossing edge exactly."""
    rates = _i62_np.asarray(discharge_per_crossing, _i62_np.float64)
    if rates.shape[-1] != matrix.shape[0]:
        raise ValueError('one discharge rate per crossing edge required')
    return (matrix.T @ rates).reshape(shape).astype(_i62_np.float64)

def run_domain(domain, *, initial_depth_m, interval_s, intervals, discharge_per_interval, source_identity, forcing_identity, outfall_stage_m=None, budget=None, snapshot_interval_s=3600.0, interval_observer=None):
    """Advance the frozen local-inertial solver over the assembled domain."""
    shape = domain['shape']
    matrix = domain['source_matrix']
    geometry = domain['geometry']
    arrays = geometry['arrays']
    drainage = arrays['boundary_kind'] == BOUNDARY_DRAINAGE
    crest = arrays['boundary_crest_m']
    if outfall_stage_m is None:
        tailwater = crest.copy()
    else:
        tailwater = _i62_np.where(drainage, _i62_np.maximum(crest, float(outfall_stage_m)), crest)
    rates = _i62_np.asarray(discharge_per_interval, _i62_np.float64)
    expected = (intervals, matrix.shape[0])
    if rates.shape != expected:
        raise ValueError('discharge_per_interval must have shape %r, got %r' % (expected, rates.shape))

    def forcing_provider(index):
        return interval_forcing(shape, matrix, rates[index])
    return advance_inertial_surface(geometry, initial_depth_m=_i62_np.asarray(initial_depth_m, _i62_np.float64), forcing_interval_s=float(interval_s), intervals=int(intervals), forcing_provider=forcing_provider, boundary_stage_provider=lambda index: tailwater, source_identity=source_identity, forcing_identity=forcing_identity, budget=budget or SurfaceBudget(), snapshot_interval_s=float(snapshot_interval_s), interval_observer=interval_observer)

def domain_ledger(result, *, spacing_m, declared_injection_m3):
    """Closed two-dimensional ledger with an explicit no-double-count statement."""
    arrays = result['arrays']
    depth = _i62_np.asarray(arrays['depth_m'], _i62_np.float64)
    area = float(spacing_m) ** 2
    initial = float(_i62_np.asarray(arrays['initial_depth_m'], _i62_np.float64).sum() * area)
    final = float(depth[-1].sum() * area)
    supplied = float(_i62_np.asarray(arrays['ledger'], _i62_np.float64)[-1, 0])
    imported = float(_i62_np.asarray(arrays['ledger'], _i62_np.float64)[-1, 1])
    exported = float(_i62_np.asarray(arrays['ledger'], _i62_np.float64)[-1, 2])
    residual = final - initial - supplied - imported + exported
    return {'initial_storage_m3': initial, 'injected_m3': supplied, 'boundary_input_m3': imported, 'boundary_output_m3': exported, 'final_storage_m3': final, 'storage_change_m3': final - initial, 'residual_m3': residual, 'residual_relative': residual / max(abs(supplied) + abs(initial), 1.0), 'declared_injection_m3': float(declared_injection_m3), 'injection_matches_source': bool(abs(supplied - float(declared_injection_m3)) <= 1e-09 * max(abs(float(declared_injection_m3)), 1.0)), 'ledger_algebra': 'final = initial + injected + boundary_input - boundary_output + residual', 'per_snapshot_residual_m3': _i62_np.asarray(arrays['ledger'], _i62_np.float64)[:, 4].tolist(), 'no_double_count_statement': 'each injected cubic metre is a line item the one-dimensional donor already removed from its own ledger; the two-dimensional ledger closes on its own and the reach ledger is not adjusted'}

def extent_statistics(depth_m, *, spacing_m, carved_depth_m, threshold_m=0.02):
    """Wetted area, overbank area and depth statistics for one depth field."""
    depth = _i62_np.asarray(depth_m, _i62_np.float64)
    if depth.ndim != 2 or not _i62_np.isfinite(depth).all() or (depth < 0).any():
        raise ValueError('finite non-negative depth field required')
    area = float(spacing_m) ** 2
    wet = depth > float(threshold_m)
    carved = _i62_np.asarray(carved_depth_m, _i62_np.float64) > CARVED_EPSILON_M
    if carved.shape != depth.shape:
        raise ValueError('carved depth must match the depth field')
    overbank = wet & ~carved
    channel = wet & carved
    return {'threshold_m': float(threshold_m), 'wet_cells': int(wet.sum()), 'wet_area_m2': float(wet.sum() * area), 'channel_wet_area_m2': float(channel.sum() * area), 'overbank_wet_area_m2': float(overbank.sum() * area), 'overbank_fraction_of_wet': float(overbank.sum() / wet.sum()) if wet.any() else 0.0, 'max_depth_m': float(depth.max()), 'mean_depth_over_wet_m': float(depth[wet].mean()) if wet.any() else 0.0, 'volume_m3': float(depth.sum() * area)}

def residual_wetland(depth_m, *, spacing_m, carved_depth_m, threshold_m=0.02):
    """Water left standing outside the carved cross-section once the flood recedes."""
    depth = _i62_np.asarray(depth_m, _i62_np.float64)
    carved = _i62_np.asarray(carved_depth_m, _i62_np.float64) > CARVED_EPSILON_M
    wet = depth > float(threshold_m)
    standing = wet & ~carved
    area = float(spacing_m) ** 2
    return {'threshold_m': float(threshold_m), 'residual_cells': int(standing.sum()), 'residual_area_m2': float(standing.sum() * area), 'residual_volume_m3': float(depth[standing].sum() * area), 'max_residual_depth_m': float(depth[standing].max()) if standing.any() else 0.0, 'cells_above_source_capacity': int((depth > _i62_np.asarray(depth_m, _i62_np.float64).max() + 1.0).sum())}

def transfer_basins(basins):
    """Settle known input in topological order; unresolved sources propagate unknown.

    Each item supplies label, local_m3, capacity_m3, downstream (label or None),
    destination (lake/ocean/unknown), and complete. This is a finite-volume
    fill-and-spill approximation, not a time-resolved weir calculation.
    """
    by_label = {item['label']: item for item in basins}
    if len(by_label) != len(basins):
        raise ValueError('duplicate basin label')
    donors = {label: 0 for label in by_label}
    for item in basins:
        for name in ('local_m3', 'capacity_m3'):
            if not _i63_math.isfinite(item[name]) or item[name] < 0.0:
                raise ValueError('finite nonnegative basin volume required')
        target = item['downstream']
        if target is not None:
            if target not in by_label or target == item['label']:
                raise ValueError('invalid basin destination')
            donors[target] += 1
    ready = _i63_deque(sorted((label for label, count in donors.items() if count == 0)))
    incoming = {label: 0.0 for label in by_label}
    uncertain = {label: not bool(item['complete']) for label, item in by_label.items()}
    results = {}
    while ready:
        label = ready.popleft()
        item = by_label[label]
        total = item['local_m3'] + incoming[label]
        if uncertain[label]:
            stored = spill = None
        else:
            stored = min(total, item['capacity_m3'])
            spill = total - stored
        results[label] = {'local_m3': item['local_m3'], 'upstream_m3': incoming[label], 'inflow_m3': total, 'stored_m3': stored, 'outflow_m3': spill, 'residual_m3': None if stored is None else total - stored - spill, 'complete': not uncertain[label], 'destination': item['destination']}
        target = item['downstream']
        if target is not None:
            if spill is None:
                uncertain[target] = True
            else:
                incoming[target] += spill
            donors[target] -= 1
            if donors[target] == 0:
                ready.append(target)
    for label in by_label.keys() - results.keys():
        item = by_label[label]
        results[label] = {'local_m3': item['local_m3'], 'upstream_m3': incoming[label], 'inflow_m3': item['local_m3'] + incoming[label], 'stored_m3': None, 'outflow_m3': None, 'residual_m3': None, 'complete': False, 'destination': item['destination']}
    return results

def form_connected_region(composition, origin_native_xz, *, world_seed=20261020, runoff_m_per_year, duration_seconds, channel_threshold_m3_s, tile_side_cells=128, min_lake_area_m2=10000.0):
    from terrain_pipeline.common_infra import identity as _i64_identity
    from terrain_pipeline.world_water_formation import form_water_and_rivers as _i64_form_water_and_rivers
    if type(tile_side_cells) is not int or tile_side_cells <= 0:
        raise ValueError('positive integer tile_side_cells required')
    if not isinstance(composition, dict) or not isinstance(composition.get('metadata'), dict):
        raise ValueError('composition and metadata required')
    metadata = composition['metadata']
    expected_origin = metadata.get('crop_origin_native_xz', metadata.get('origin_native_xz'))
    if list(origin_native_xz) != expected_origin or metadata.get('world_seed') != world_seed:
        raise ValueError('composition origin and world seed must match')
    height = _i64_np.asarray(composition['composed_elevation_m'], dtype=_i64_np.float64)
    valid = _i64_np.asarray(composition['valid_mask'])
    if valid.dtype != _i64_np.bool_ or valid.shape != height.shape or (not valid.all()):
        raise ValueError('composition region must be fully resolved')
    ocean = composition.get('ocean_mask')
    if ocean is None:
        ocean = _i64_np.zeros(height.shape, bool)
    result = _i64_form_water_and_rivers(height, ocean, origin_native_xz, world_seed, metadata, runoff_m_per_year=runoff_m_per_year, duration_seconds=duration_seconds, channel_threshold_m3_s=channel_threshold_m3_s, sea_level_m=metadata.get('sea_level_m') if metadata.get('sea_level_m') is not None else 0.0, min_lake_area_m2=min_lake_area_m2)
    arrays = result['arrays']
    receiver = arrays['receiver']
    rows, cols = receiver.shape
    z, x = _i64_np.indices((rows, cols), dtype=_i64_np.int64)
    native_x = x + origin_native_xz[0]
    native_z = z + origin_native_xz[1]
    live = receiver >= 0
    safe = _i64_np.maximum(receiver, 0)
    arrays['receiver_native_x'] = _i64_np.where(live, native_x.ravel()[safe], -1)
    arrays['receiver_native_z'] = _i64_np.where(live, native_z.ravel()[safe], -1)
    spill_receiver = arrays['spill_receiver']
    spill_live = spill_receiver >= 0
    spill_safe = _i64_np.maximum(spill_receiver, 0)
    arrays['spill_receiver_native_x'] = _i64_np.where(spill_live, native_x.ravel()[spill_safe], -1)
    arrays['spill_receiver_native_z'] = _i64_np.where(spill_live, native_z.ravel()[spill_safe], -1)
    spill_active = spill_live & (arrays['spill_edge_volume_m3'] > 0.0)
    spill_crossed = spill_active & ((native_x // tile_side_cells != arrays['spill_receiver_native_x'] // tile_side_cells) | (native_z // tile_side_cells != arrays['spill_receiver_native_z'] // tile_side_cells))
    crossed = live & ((native_x // tile_side_cells != arrays['receiver_native_x'] // tile_side_cells) | (native_z // tile_side_cells != arrays['receiver_native_z'] // tile_side_cells))
    complete = arrays['complete_mask']
    channel = arrays['channel_mask']
    channel_edge = live & channel & channel.ravel()[safe]
    paths = _terminal_categories(arrays)
    selected = channel & complete
    stats = {'routing_cross_tile_edges': int(crossed.sum()), 'complete_routing_cross_tile_edges': int((crossed & complete).sum()), 'channel_cross_tile_edges': int((crossed & channel_edge).sum()), 'complete_channel_cross_tile_edges': int((crossed & channel_edge & complete).sum()), 'active_spill_edges': int(spill_active.sum()), 'active_spill_cross_tile_edges': int(spill_crossed.sum()), 'complete_channel_cells_by_terminal': {name: int((selected & (paths == name)).sum()) for name in ('ocean', 'lake', 'unknown', 'pending', 'other')}}
    result_metadata = {'schema': 'world-connected-water-v1', 'formation': result['metadata'], 'formation_identity_sha256': result['identity_sha256'], 'tile_side_cells': tile_side_cells, 'tile_grid': 'absolute native coordinates; floor division by tile_side_cells', 'receiver_coordinates': 'world native x/z; each receiver<0 identifies its terminal; spill edges are active only with positive spill_edge_volume_m3', 'spill_chain_destinations': _spill_destinations(result['metadata']['basin_transfer_links']), 'statistics': stats, 'scope': 'one finite joint region; tile crossings do not certify world connectivity', 'path_count_semantics': 'complete channel source cells grouped by downstream terminal; paths may overlap'}
    product = {'arrays': arrays, 'metadata': result_metadata}
    if result.get('network') is not None:
        product['network'] = result['network']
        result_metadata['network'] = result['metadata']['network']
        result_metadata['network_identity_sha256'] = _i64_identity(result['network'], result_metadata['network'])
    product['identity_sha256'] = _i64_identity(arrays, result_metadata)
    return product

def _spill_destinations(links):
    by_label = {link['source_label']: link for link in links}
    result = []
    for link in links:
        labels = []
        current = link
        while current is not None and current['source_label'] not in labels:
            labels.append(current['source_label'])
            if current['volume_m3'] is None or current['volume_m3'] <= 0:
                destination = 'pending' if current['volume_m3'] is None else 'retained'
                break
            target = current['target_label']
            if target is None:
                destination = current['destination']
                break
            current = by_label.get(target)
            if current is None:
                destination = 'unknown'
                break
        else:
            destination = 'cycle'
        result.append({'source_label': link['source_label'], 'labels': labels, 'destination': destination})
    return result

def _terminal_categories(arrays):
    receiver = arrays['receiver'].ravel()
    labels = arrays['basin_label'].ravel()
    kinds = arrays['terminal_kind'].ravel()
    pending = arrays['pending_basin_mask'].ravel()
    lake = arrays['lake_support_mask'].ravel()
    categories = _i64_np.full(receiver.size, '', dtype='U8')
    for start in range(receiver.size):
        if categories[start]:
            continue
        path = []
        current = start
        while receiver[current] >= 0 and (not categories[current]):
            path.append(current)
            current = int(receiver[current])
        if categories[current]:
            category = categories[current]
        elif pending[current]:
            category = 'pending'
        elif lake[current] and labels[current] >= 0:
            category = 'lake'
        elif kinds[current] == 'open_outflow':
            category = 'ocean'
        elif kinds[current] == 'unknown_boundary':
            category = 'unknown'
        else:
            category = 'other'
        categories[current] = category
        categories[path] = category
    return categories.reshape(arrays['receiver'].shape)
