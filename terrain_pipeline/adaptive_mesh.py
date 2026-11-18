"""Consolidated adaptive_mesh implementations; numeric expressions preserved."""
from __future__ import annotations
from terrain_pipeline.surface_identity import _plain, _freeze, geometry_identity
from terrain_pipeline.surface_identity import _plain, _freeze, geometry_identity
from terrain_pipeline.surface_identity import _plain, _freeze, geometry_identity
import hashlib as _i89_hashlib
import json as _i89_json
import numpy as _i89_np
from numba import njit as _i89_njit
import math as _i90_math
import numpy as _i90_np
from numba import njit as _i90_njit
import numpy as _i93_np
from scipy.ndimage import maximum_filter as _i93_maximum_filter
import os as _i94_os
from pathlib import Path as _i94_Path
import tempfile as _i94_tempfile
from collections.abc import Mapping as _i92_Mapping
from collections.abc import Sequence as _i92_Sequence
import io as _i92_io
import json as _i92_json
from pathlib import Path as _i92_Path
import zipfile as _i92_zipfile
import numpy as _i92_np
import math as _i88_math
import time as _i88_time
import numpy as _i88_np
import hashlib as _i91_hashlib
import json as _i91_json
import math as _i91_math
from collections.abc import Mapping as _i91_Mapping
from collections.abc import Sequence as _i91_Sequence
from functools import lru_cache as _i91_lru_cache
from pathlib import Path as _i91_Path
import numpy as _i91_np
import math as _i95_math
import numpy as _i95_np
CATEGORY = 'B'
MODEL = 'single-domain-adaptive-canonical-HLL-Manning-SSPRK2-v1'

@_i89_njit(cache=True, fastmath=False)
def _aligned_partition(requested):
    rows, columns = requested.shape
    leaves = _i89_np.empty((requested.size, 3), _i89_np.int64)
    count = 0
    for row in range(0, rows, 4):
        for column in range(0, columns, 4):
            if requested[row:row + 4, column:column + 4].min() >= 4:
                leaves[count] = (row, column, 4)
                count += 1
                continue
            for dz in (0, 2):
                for dx in (0, 2):
                    r, c = (row + dz, column + dx)
                    if requested[r:r + 2, c:c + 2].min() >= 2:
                        leaves[count] = (r, c, 2)
                        count += 1
                    else:
                        for fine_z in (0, 1):
                            for fine_x in (0, 1):
                                leaves[count] = (r + fine_z, c + fine_x, 1)
                                count += 1
    return leaves[:count].copy()

@_i89_njit(cache=True, fastmath=False)
def _compact_support(bed, leaves, offsets, datum):
    owner = _i89_np.full(bed.shape, -1, _i89_np.int64)
    sorted_bed = _i89_np.zeros(bed.size)
    prefix = _i89_np.zeros(bed.size)
    for index in range(len(leaves)):
        row, column, size = leaves[index]
        samples = _i89_np.empty(size * size)
        position = 0
        for dz in range(size):
            for dx in range(size):
                owner[row + dz, column + dx] = index
                samples[position] = bed[row + dz, column + dx] - datum
                position += 1
        samples.sort()
        total = 0.0
        for position in range(size * size):
            sorted_bed[offsets[index] + position] = samples[position]
            total += samples[position]
            prefix[offsets[index] + position] = total
    return (owner, sorted_bed, prefix)

@_i89_njit(cache=True, fastmath=False)
def _coverage_valid(owner, leaf_row, leaf_column, leaf_spacing):
    coverage = _i89_np.zeros_like(owner)
    for cell in range(len(leaf_row)):
        row, column, size = (leaf_row[cell], leaf_column[cell], leaf_spacing[cell])
        for dz in range(size):
            for dx in range(size):
                if owner[row + dz, column + dx] != cell:
                    return False
                coverage[row + dz, column + dx] += 1
    return _i89_np.all(coverage == 1)

def build_adaptive_geometry(canonical_bed_m, requested_spacing_m, *, origin_m_xz=(0.0, 0.0), boundary_kind=None, boundary_crest_m=None):
    bed = _i89_np.asarray(canonical_bed_m)
    requested = _i89_np.asarray(requested_spacing_m)
    if bed.dtype != _i89_np.float64 or bed.ndim != 2 or (not _i89_np.isfinite(bed).all()) or bed.shape[0] % 4 or bed.shape[1] % 4 or (requested.shape != bed.shape) or (not _i89_np.isin(requested, [1, 2, 4]).all()):
        raise ValueError('finite 1m canonical bed, multiples-of-four extent and explicit 1/2/4m spacing map required')
    rows, columns = bed.shape
    leaves = _aligned_partition(requested)
    count = len(leaves)
    datum = float(bed.min())
    offsets = _i89_np.r_[0, _i89_np.cumsum(leaves[:-1, 2] ** 2)].astype(_i89_np.int64)
    owner, sorted_bed, prefix = _compact_support(bed, leaves, offsets, datum)
    left_x, right_x = (owner[:, :-1], owner[:, 1:])
    left_z, right_z = (owner[:-1], owner[1:])
    mask_x, mask_z = (left_x != right_x, left_z != right_z)
    zx, xx = _i89_np.nonzero(mask_x)
    zz, xz = _i89_np.nonzero(mask_z)
    left = _i89_np.r_[left_x[mask_x], left_z[mask_z]]
    right = _i89_np.r_[right_x[mask_x], right_z[mask_z]]
    axis = _i89_np.r_[_i89_np.zeros(mask_x.sum(), _i89_np.int64), _i89_np.ones(mask_z.sum(), _i89_np.int64)]
    crest = _i89_np.r_[_i89_np.maximum(bed[:, :-1], bed[:, 1:])[mask_x], _i89_np.maximum(bed[:-1], bed[1:])[mask_z]] - datum
    boundary_cells = _i89_np.r_[owner[:, 0], owner[:, -1], owner[0], owner[-1]]
    boundary_bed = _i89_np.r_[bed[:, 0], bed[:, -1], bed[0], bed[-1]]
    kinds = _i89_np.zeros(len(boundary_cells), _i89_np.int64) if boundary_kind is None else _i89_np.asarray(boundary_kind)
    boundary_crest = boundary_bed.copy() if boundary_crest_m is None else _i89_np.asarray(boundary_crest_m)
    if kinds.dtype != _i89_np.int64 or kinds.shape != boundary_cells.shape or (not _i89_np.isin(kinds, [0, 1, 2]).all()) or (boundary_crest.dtype != _i89_np.float64) or (boundary_crest.shape != boundary_cells.shape) or (not _i89_np.isfinite(boundary_crest).all()) or _i89_np.any(boundary_crest < boundary_bed):
        raise ValueError('complete canonical boundary kind and finite no-lower crest required')
    arrays = dict(canonical_bed_m=bed.copy(), requested_spacing_m=requested.astype(_i89_np.int64), leaf_row=leaves[:, 0], leaf_column=leaves[:, 1], leaf_spacing_m=leaves[:, 2], leaf_area_m2=leaves[:, 2].astype(_i89_np.float64) ** 2, canonical_owner=owner, subcell_count=leaves[:, 2] ** 2, subcell_offset=offsets, sorted_subcell_bed_relative_m=sorted_bed, prefix_subcell_bed_relative_m=prefix, face_left=left, face_right=right, face_axis=axis, face_canonical_row=_i89_np.r_[zx, zz + 1], face_canonical_column=_i89_np.r_[xx + 1, xz], face_crest_relative_m=crest, boundary_cell=boundary_cells, boundary_axis=_i89_np.r_[_i89_np.zeros(2 * rows, _i89_np.int64), _i89_np.ones(2 * columns, _i89_np.int64)], boundary_sign=_i89_np.r_[-_i89_np.ones(rows), _i89_np.ones(rows), -_i89_np.ones(columns), _i89_np.ones(columns)], boundary_kind=kinds.copy(), boundary_crest_m=boundary_crest.copy(), boundary_bed_relative_m=boundary_bed - datum)
    metadata = dict(model=MODEL, origin_m_xz=list(origin_m_xz), canonical_shape=list(bed.shape), hydraulic_datum_m=datum, finest_spacing_m=int(leaves[:, 2].min()), leaf_counts={str(size): int(_i89_np.sum(leaves[:, 2] == size)) for size in (1, 2, 4)}, leaf_area_m2={str(size): int(_i89_np.sum(leaves[:, 2] == size)) * size ** 2 for size in (1, 2, 4)}, leaf_count=count, total_area_m2=bed.size, internal_segment_count=len(left), boundary_segment_count=len(boundary_cells), face_length_m=1.0, full_selected_window_covered=True, uniform_coarse_convergence_claim=False)
    result = dict(arrays=arrays, metadata=metadata, identity_sha256=geometry_identity(arrays, metadata))
    validate_adaptive_geometry(result)
    return result

def validate_adaptive_geometry(geometry):
    a = geometry['arrays']
    owner = a['canonical_owner']
    if not _coverage_valid(owner, a['leaf_row'], a['leaf_column'], a['leaf_spacing_m']) or int(a['leaf_area_m2'].sum()) != owner.size:
        raise ValueError('canonical tiles must be covered exactly once')
    tuples = _i89_np.column_stack((a['face_axis'], a['face_canonical_row'], a['face_canonical_column']))
    if len(_i89_np.unique(tuples, axis=0)) != len(tuples):
        raise ValueError('internal canonical segments must be unique')
    expected = int(_i89_np.sum(owner[:, :-1] != owner[:, 1:]) + _i89_np.sum(owner[:-1] != owner[1:]))
    if len(tuples) != expected or _i89_np.any(a['face_left'] == a['face_right']):
        raise ValueError('all neighboring leaves must share exactly one canonical segment per interface position')
    for axis in (0, 1):
        mask = a['face_axis'] == axis
        row, column = (a['face_canonical_row'][mask], a['face_canonical_column'][mask])
        first = owner[row, column - 1] if axis == 0 else owner[row - 1, column]
        second = owner[row, column]
        if not _i89_np.array_equal(first, a['face_left'][mask]) or not _i89_np.array_equal(second, a['face_right'][mask]):
            raise ValueError('canonical segment incidence invalid')
    return True

def initial_leaf_state(geometry, canonical_depth_m, canonical_momentum=None):
    a = geometry['arrays']
    depth = _i89_np.asarray(canonical_depth_m)
    if depth.dtype != _i89_np.float64 or depth.shape != a['canonical_owner'].shape or (not _i89_np.isfinite(depth).all()) or _i89_np.any(depth < 0):
        raise ValueError('finite nonnegative canonical initial depth required')
    momentum = _i89_np.zeros((*depth.shape, 2)) if canonical_momentum is None else _i89_np.asarray(canonical_momentum)
    if momentum.shape != (*depth.shape, 2) or not _i89_np.isfinite(momentum).all():
        raise ValueError('finite canonical initial momentum required')
    owner, area = (a['canonical_owner'].ravel(), a['leaf_area_m2'])
    return _i89_np.column_stack((_i89_np.bincount(owner, weights=depth.ravel(), minlength=len(area)) / area, _i89_np.bincount(owner, weights=momentum[:, :, 0].ravel(), minlength=len(area)) / area, _i89_np.bincount(owner, weights=momentum[:, :, 1].ravel(), minlength=len(area)) / area))

@_i90_njit(cache=True, fastmath=False)
def leaf_stages(depth, counts, bed, prefix):
    result = _i90_np.empty(len(depth))
    offset = 0
    for cell in range(len(depth)):
        count = counts[cell]
        volume = depth[cell] * count
        wet = 0
        for index in range(count):
            if volume >= (index + 1) * bed[offset + index] - prefix[offset + index]:
                wet += 1
        wet = max(wet, 1)
        result[cell] = (volume + prefix[offset + wet - 1]) / wet
        offset += count
    return result
from terrain_pipeline.shallow_water import _hll_accelerated as _x40_hll

@_i90_njit(cache=True, fastmath=False)
def leaf_rhs_kernel(state, counts, bed, prefix, area, left, right, axes, crests, cells, boundary_axes, signs, kinds, boundary_bed, boundary_crests, tailwater, gravity, dt):
    count = len(state)
    stage = leaf_stages(state[:, 0], counts, bed, prefix)
    velocity = _i90_np.zeros((count, 2))
    for cell in range(count):
        if state[cell, 0] > 0:
            velocity[cell, 0] = state[cell, 1] / state[cell, 0]
            velocity[cell, 1] = state[cell, 2] / state[cell, 0]
    flux, boundary_flux = (_i90_np.zeros((len(left), 3)), _i90_np.zeros((len(cells), 3)))
    first_pressure, second_pressure, boundary_pressure = (_i90_np.zeros(len(left)), _i90_np.zeros(len(left)), _i90_np.zeros(len(cells)))
    maximum_speed = 0.0
    for face in range(len(left)):
        first, second, axis, crest = (left[face], right[face], axes[face], crests[face])
        hl, hr = (max(stage[first] - crest, 0.0), max(stage[second] - crest, 0.0))
        mass, mx, mz, speed = _x40_hll(hl, hr, velocity[first, 0], velocity[first, 1], velocity[second, 0], velocity[second, 1], crest, gravity, axis)
        flux[face, 0], flux[face, 1], flux[face, 2] = (mass, mx, mz)
        first_pressure[face], second_pressure[face] = (0.5 * gravity * hl ** 2, 0.5 * gravity * hr ** 2)
        maximum_speed = max(maximum_speed, speed)
    for face in range(len(cells)):
        cell, axis, sign = (cells[face], boundary_axes[face], signs[face])
        crest = boundary_bed[face]
        if kinds[face] != 0:
            crest = max(crest, boundary_crests[face])
        h = max(stage[cell] - crest, 0.0)
        ux, uz = (velocity[cell, 0], velocity[cell, 1])
        gx, gz = (ux, uz)
        if axis == 0:
            gx = -gx
        else:
            gz = -gz
        ghost_h = h
        if kinds[face] != 0:
            exterior = crest if kinds[face] == 1 else tailwater[face]
            ghost_h, gx, gz = (max(exterior - crest, 0.0), 0.0, 0.0)
        if axis == 0:
            ux, gx = (ux * sign, gx * sign)
        else:
            uz, gz = (uz * sign, gz * sign)
        mass, mx, mz, speed = _x40_hll(h, ghost_h, ux, uz, gx, gz, crest, gravity, axis)
        flux_x, flux_z = (mx * sign, mz) if axis == 0 else (mx, mz * sign)
        boundary_flux[face, 0], boundary_flux[face, 1], boundary_flux[face, 2] = (mass, flux_x, flux_z)
        boundary_pressure[face] = 0.5 * gravity * h ** 2
        maximum_speed = max(maximum_speed, speed)
    outgoing = _i90_np.zeros(count)
    for face in range(len(left)):
        outgoing[left[face]] += max(flux[face, 0], 0.0)
        outgoing[right[face]] += max(-flux[face, 0], 0.0)
    for face in range(len(cells)):
        outgoing[cells[face]] += max(boundary_flux[face, 0], 0.0)
    scales = _i90_np.ones(count)
    limited = 0
    for cell in range(count):
        if outgoing[cell] * dt > state[cell, 0] * area[cell]:
            scales[cell] = state[cell, 0] * area[cell] / (outgoing[cell] * dt) * (1 - 1e-12)
            limited += 1
    for face in range(len(left)):
        donor = left[face] if flux[face, 0] >= 0 else right[face]
        for component in range(3):
            flux[face, component] *= scales[donor]
    for face in range(len(cells)):
        if boundary_flux[face, 0] >= 0:
            for component in range(3):
                boundary_flux[face, component] *= scales[cells[face]]
    rhs, pressure = (_i90_np.zeros_like(state), _i90_np.zeros_like(state))
    for face in range(len(left)):
        first, second, component = (left[face], right[face], axes[face] + 1)
        for quantity in range(3):
            rhs[first, quantity] -= flux[face, quantity] / area[first]
            rhs[second, quantity] += flux[face, quantity] / area[second]
        pressure[first, component] += first_pressure[face] / area[first]
        pressure[second, component] -= second_pressure[face] / area[second]
    for face in range(len(cells)):
        cell, component = (cells[face], boundary_axes[face] + 1)
        for quantity in range(3):
            rhs[cell, quantity] -= boundary_flux[face, quantity] / area[cell]
        pressure[cell, component] += signs[face] * boundary_pressure[face] / area[cell]
    rhs += pressure
    return (rhs, flux, boundary_flux, pressure, maximum_speed, limited, scales.min())

def adaptive_rhs(geometry, state, *, tailwater_m, gravity=9.81, dt=0.0):
    a, meta = (geometry['arrays'], geometry['metadata'])
    tail = _i90_np.asarray(tailwater_m) - meta['hydraulic_datum_m']
    result = leaf_rhs_kernel(state, a['subcell_count'], a['sorted_subcell_bed_relative_m'], a['prefix_subcell_bed_relative_m'], a['leaf_area_m2'], a['face_left'], a['face_right'], a['face_axis'], a['face_crest_relative_m'], a['boundary_cell'], a['boundary_axis'], a['boundary_sign'], a['boundary_kind'], a['boundary_bed_relative_m'], a['boundary_crest_m'] - meta['hydraulic_datum_m'], tail, gravity, dt)
    rhs, flux, boundary, pressure, speed, limited, scale = result
    return (rhs, dict(internal_flux_m2_s=flux, boundary_flux_m2_s=boundary, bed_source=pressure, maximum_wave_speed_m_s=float(speed), limited_donors=int(limited), minimum_limiter_factor=float(scale)))

@_i90_njit(cache=True, fastmath=False)
def leaf_damping_kernel(state, counts, bed, prefix, dt, gravity, roughness):
    stage = leaf_stages(state[:, 0], counts, bed, prefix)
    damping, factor = (_i90_np.zeros(len(state)), _i90_np.zeros(len(state)))
    offset = 0
    for cell in range(len(state)):
        for index in range(counts[cell]):
            h = max(stage[cell] - bed[offset + index], 0.0)
            if h > 0:
                factor[cell] += h ** (-1 / 3)
        factor[cell] /= counts[cell]
        squared = state[cell, 0] ** 2
        denominator = squared + dt * gravity * roughness ** 2 * _i90_math.hypot(state[cell, 1], state[cell, 2]) * factor[cell]
        if denominator > 0:
            damping[cell] = squared / denominator
        offset += counts[cell]
    return (damping, factor)

def adaptive_drag(geometry, state, *, dt, gravity, roughness):
    a = geometry['arrays']
    return leaf_damping_kernel(state, a['subcell_count'], a['sorted_subcell_bed_relative_m'], a['prefix_subcell_bed_relative_m'], dt, gravity, roughness)

def canonical_inventory(geometry, state):
    """Display/comparison inventory reconstruction, never a hidden fine solve."""
    a = geometry['arrays']
    stage = leaf_stages(state[:, 0], a['subcell_count'], a['sorted_subcell_bed_relative_m'], a['prefix_subcell_bed_relative_m'])
    owner = a['canonical_owner']
    h = _i90_np.maximum(stage[owner] - (a['canonical_bed_m'] - geometry['metadata']['hydraulic_datum_m']), 0.0)
    velocity = _i90_np.divide(state[:, 1:], state[:, 0, None], out=_i90_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    return (h, h[:, :, None] * velocity[owner])

def anticipated_spacing_map(canonical_depth_m, *, max_leaf_spacing_m=4, halo_m=8, activity_depth_m=1e-08, canonical_forcing_m3_s=None, forcing_prediction_dt_s=0.025, boundary_kind=None, tailwater_m=None, canonical_bed_m=None, prescribed_mask=None):
    if max_leaf_spacing_m not in (1, 2, 4) or type(halo_m) is not int or halo_m < 2 or (activity_depth_m <= 0):
        raise ValueError('explicit leaf spacing, at-least-two-meter halo and positive activity threshold required')
    depth = _i93_np.asarray(canonical_depth_m)
    if depth.ndim != 2 or not _i93_np.isfinite(depth).all() or _i93_np.any(depth < 0):
        raise ValueError('finite nonnegative canonical tagging depth required')
    active = depth > activity_depth_m
    if canonical_forcing_m3_s is not None:
        forcing = _i93_np.asarray(canonical_forcing_m3_s)
        if forcing.shape != depth.shape or not _i93_np.isfinite(forcing).all() or _i93_np.any(forcing < 0):
            raise ValueError('complete finite nonnegative forcing tag required')
        active |= forcing * forcing_prediction_dt_s > activity_depth_m
    if prescribed_mask is not None:
        mask = _i93_np.asarray(prescribed_mask)
        if mask.dtype != bool or mask.shape != depth.shape:
            raise ValueError('explicit canonical initial refinement mask required')
        active |= mask
    if boundary_kind is not None:
        rows, columns = depth.shape
        kinds, tail, bed = (_i93_np.asarray(boundary_kind), _i93_np.asarray(tailwater_m), _i93_np.asarray(canonical_bed_m))
        if kinds.shape != (2 * (rows + columns),) or tail.shape != kinds.shape or bed.shape != depth.shape:
            raise ValueError('complete canonical reservoir pretag data required')
        potential = (kinds == 2) & (tail > _i93_np.r_[bed[:, 0], bed[:, -1], bed[0], bed[-1]])
        active[:, 0] |= potential[:rows]
        active[:, -1] |= potential[rows:2 * rows]
        active[0] |= potential[2 * rows:2 * rows + columns]
        active[-1] |= potential[2 * rows + columns:]
    buffered = _i93_maximum_filter(active.astype(_i93_np.uint8), size=2 * halo_m + 1, mode='constant') > 0
    requested = _i93_np.full(depth.shape, max_leaf_spacing_m, _i93_np.int64)
    requested[buffered] = 1
    return requested

def refine_adaptive_state(geometry, state, requested_spacing_m):
    """Refine only; transfer the represented stage/velocity and preserve means."""
    a, meta = (geometry['arrays'], geometry['metadata'])
    actual = a['leaf_spacing_m'][a['canonical_owner']]
    request = _i93_np.minimum(actual, _i93_np.asarray(requested_spacing_m))
    if _i93_np.array_equal(request, actual):
        return (geometry, state, None)
    next_geometry = build_adaptive_geometry(a['canonical_bed_m'], request, origin_m_xz=meta['origin_m_xz'], boundary_kind=a['boundary_kind'], boundary_crest_m=a['boundary_crest_m'])
    next_a = next_geometry['arrays']
    h, momentum = canonical_inventory(geometry, state)
    parent = a['canonical_owner'][next_a['leaf_row'], next_a['leaf_column']]
    next_state = _i93_np.empty((len(parent), 3))
    unchanged = next_a['leaf_spacing_m'] == a['leaf_spacing_m'][parent]
    next_state[unchanged] = state[parent[unchanged]]
    for child in _i93_np.flatnonzero(~unchanged):
        row, column, size = (next_a['leaf_row'][child], next_a['leaf_column'][child], next_a['leaf_spacing_m'][child])
        patch = (slice(row, row + size), slice(column, column + size))
        next_state[child, 0] = h[patch].mean()
        next_state[child, 1:] = momentum[patch].mean(axis=(0, 1))
    before = state * a['leaf_area_m2'][:, None]
    after = next_state * next_a['leaf_area_m2'][:, None]
    grouped = _i93_np.zeros_like(before)
    _i93_np.add.at(grouped, parent, after)
    residual = grouped - before
    tolerance = 2e-11 * _i93_np.maximum(1.0, abs(before))
    if _i93_np.any(abs(residual) > tolerance):
        raise RuntimeError('adaptive refinement does not conserve represented water and momentum')
    changed_parent = _i93_np.unique(parent[~unchanged])
    changed_child = _i93_np.flatnonzero(~unchanged)
    witness = dict(before_geometry_identity=geometry['identity_sha256'], after_geometry_identity=next_geometry['identity_sha256'], unchanged_parent_leaf_id=parent[unchanged], unchanged_child_leaf_id=_i93_np.flatnonzero(unchanged), parent_leaf_id=parent[changed_child], refined_parent_leaf_id=changed_parent, refined_child_leaf_id=changed_child, parent_inventory_m3_m4_s=before[changed_parent], child_inventory_m3_m4_s=after[changed_child], parent_grouped_residual=residual[changed_parent], refined_parent_count=int(len(changed_parent)), added_leaf_count=len(parent) - len(state), maximum_inventory_residual=float(abs(residual).max(initial=0)))
    return (next_geometry, next_state, witness)

class SegmentedWorkspaceSpool:

    def __init__(self, directory, *, memory_limit_bytes=8 * 1024 ** 2, segment_limit_bytes=128 * 1024 ** 2):
        if not 0 < memory_limit_bytes <= segment_limit_bytes <= 256 * 1024 ** 2:
            raise ValueError('adaptive spool requires positive RAM and at-most-256MiB segments')
        self._directory = _i94_Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._memory_limit = memory_limit_bytes
        self._segment_limit = segment_limit_bytes
        self._files, self._lengths = ([], [])
        self._length = self._position = 0
        self._released_segments = 0

    def seek(self, offset, whence=0):
        position = offset if whence == 0 else self._position + offset if whence == 1 else self._length + offset if whence == 2 else -1
        if not 0 <= position <= self._length:
            raise ValueError('adaptive spool seek outside saved bytes')
        self._position = position
        return position

    def write(self, payload):
        if self._position != self._length:
            raise ValueError('adaptive history is immutable and append-only')
        view = memoryview(payload)
        written = 0
        while written < len(view):
            index, offset = divmod(self._position, self._segment_limit)
            if index == len(self._files):
                self._files.append(_i94_tempfile.SpooledTemporaryFile(max_size=self._memory_limit, dir=self._directory, prefix='adaptive-history-segment-'))
                self._lengths.append(0)
            count = min(len(view) - written, self._segment_limit - offset)
            self._files[index].seek(offset)
            self._files[index].write(view[written:written + count])
            self._lengths[index] += count
            self._position += count
            self._length += count
            written += count
        return written

    def read(self, length=-1):
        length = min(self._length - self._position, length) if length >= 0 else self._length - self._position
        blocks = []
        remaining = length
        while remaining:
            index, offset = divmod(self._position, self._segment_limit)
            count = min(remaining, self._lengths[index] - offset)
            if index < self._released_segments:
                raise RuntimeError('adaptive payload was archived; use its immutable saved record')
            self._files[index].seek(offset)
            block = self._files[index].read(count)
            if len(block) != count:
                raise RuntimeError('adaptive segmented history payload truncated')
            blocks.append(block)
            remaining -= count
            self._position += count
        return b''.join(blocks)

    def flush(self):
        for file in self._files[self._released_segments:]:
            file.flush()

    @property
    def resident_nbytes(self):
        return sum((length for length in self._lengths[self._released_segments:] if length <= self._memory_limit))

    @property
    def temporary_storage_nbytes(self):
        return sum((_i94_os.fstat(file.fileno()).st_size for file, length in zip(self._files[self._released_segments:], self._lengths[self._released_segments:]) if length > self._memory_limit))

    def release_before(self, archived_offset):
        while self._released_segments < len(self._files):
            index = self._released_segments
            segment_end = index * self._segment_limit + self._lengths[index]
            if segment_end > archived_offset:
                break
            self._files[index].close()
            self._released_segments += 1

    def close(self):
        for file in self._files:
            file.close()

    def __del__(self):
        if hasattr(self, '_files'):
            self.close()

def _encode(record):
    arrays = {key: value for key, value in record.items() if isinstance(value, _i92_np.ndarray)}
    metadata = {key: value for key, value in record.items() if not isinstance(value, _i92_np.ndarray)}
    serialized = _i92_json.dumps(metadata, sort_keys=True, allow_nan=False, separators=(',', ':')).encode('utf-8')
    arrays['_record_metadata_json'] = _i92_np.frombuffer(serialized, _i92_np.uint8)
    buffer = _i92_io.BytesIO()
    with _i92_zipfile.ZipFile(buffer, 'w', compression=_i92_zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for name, value in arrays.items():
            with archive.open(name + '.npy', 'w', force_zip64=True) as entry:
                _i92_np.lib.format.write_array(entry, value, allow_pickle=False)
    return buffer.getvalue()

def _decode(payload):
    with _i92_np.load(_i92_io.BytesIO(payload), allow_pickle=False) as saved:
        result = _i92_json.loads(saved['_record_metadata_json'].tobytes().decode('utf-8'))
        result.update({key: saved[key].copy() for key in saved.files if key != '_record_metadata_json'})
    return result

class CompressedRecordList(_i92_Sequence):

    def __init__(self, directory=None, memory_limit_bytes=8 * 1024 ** 2, append_observer=None, segment_limit_bytes=128 * 1024 ** 2):
        directory = _i92_Path(directory if directory is not None else '.scratch/adaptive-history')
        directory.mkdir(parents=True, exist_ok=True)
        self._memory_limit = memory_limit_bytes
        self._file = SegmentedWorkspaceSpool(directory, memory_limit_bytes=memory_limit_bytes, segment_limit_bytes=segment_limit_bytes)
        self._offsets = []
        self._length = 0
        self._maximum_payload = 0
        self._saved = {}
        self._saved_loader = None
        self._archived_prefix_count = 0
        self._append_observer = append_observer

    def append(self, record):
        self._append_payload(_encode(record))

    def _append_payload(self, payload):
        if self._saved:
            raise RuntimeError('adaptive archived record collection cannot append')
        if len(payload) > 256 * 1024 ** 2:
            raise RuntimeError('adaptive single compressed record exceeds artifact budget')
        self._file.seek(self._length)
        self._file.write(payload)
        self._offsets.append((self._length, len(payload)))
        self._length += len(payload)
        if self._length > self._memory_limit:
            self._file.flush()
        self._maximum_payload = max(self._maximum_payload, len(payload))
        if self._append_observer is not None:
            self._append_observer()

    def _payload(self, index):
        offset, length = self._offsets[index]
        self._file.seek(offset)
        payload = self._file.read(length)
        if len(payload) != length:
            raise RuntimeError('adaptive immutable history payload truncated')
        return payload

    @property
    def storage_nbytes(self):
        resident = self._file.resident_nbytes
        return resident + 64 * len(self._offsets) + self._maximum_payload

    @property
    def temporary_storage_nbytes(self):
        return self._file.temporary_storage_nbytes

    @property
    def serialized_nbytes(self):
        return self._length

    def __len__(self):
        return len(self._offsets)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[position] for position in range(*index.indices(len(self)))]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError('adaptive history record index outside collection')
        if index in self._saved:
            return self._saved_loader(self._saved[index])
        return _decode(self._payload(index))

    def bind_saved_record(self, index, pin, loader):
        if not 0 <= index < len(self) or index in self._saved:
            raise ValueError('adaptive saved-record binding must replace a unique original record')
        self._saved[index] = dict(pin)
        self._saved_loader = loader
        while self._archived_prefix_count in self._saved:
            self._archived_prefix_count += 1
        if self._archived_prefix_count:
            offset, length = self._offsets[self._archived_prefix_count - 1]
            self._file.release_before(offset + length)

    def close(self):
        self._file.close()

    def __del__(self):
        if hasattr(self, '_file'):
            self._file.close()

class CompressedGeometryHistory(_i92_Mapping):

    def __init__(self, directory=None, memory_limit_bytes=8 * 1024 ** 2, append_observer=None):
        self._indices = {}
        self._records = CompressedRecordList(directory, memory_limit_bytes, append_observer)

    def register(self, geometry):
        identity = geometry['identity_sha256']
        payload = _encode(dict(geometry['arrays'], metadata=geometry['metadata'], identity_sha256=identity))
        if identity in self._indices:
            if self._records._payload(self._indices[identity]) != payload:
                raise ValueError('immutable geometry history identity collision')
            return
        self._indices[identity] = len(self._records)
        self._records._append_payload(payload)

    @property
    def storage_nbytes(self):
        return self._records.storage_nbytes + 128 * len(self._indices)

    @property
    def temporary_storage_nbytes(self):
        return self._records.temporary_storage_nbytes

    @property
    def serialized_nbytes(self):
        return self._records.serialized_nbytes

    def __len__(self):
        return len(self._indices)

    def __iter__(self):
        return iter(self._indices)

    def bind_saved_geometry(self, identity, pin, loader):

        def original_record(pin):
            geometry = loader(pin)
            return dict(geometry['arrays'], metadata=geometry['metadata'], identity_sha256=geometry['identity_sha256'])
        self._records.bind_saved_record(self._indices[identity], pin, original_record)

    def __getitem__(self, identity):
        record = self._records[self._indices[identity]]
        metadata, saved_identity = (record.pop('metadata'), record.pop('identity_sha256'))
        if saved_identity != identity:
            raise ValueError('saved geometry history identity binding invalid')
        pass
        if geometry_identity(record, metadata) != identity:
            raise ValueError('decoded geometry history content identity mismatch')
        return dict(arrays=record, metadata=metadata, identity_sha256=saved_identity)

def advance_adaptive_surface(geometry, *, initial_depth_m, forcing_interval_s, intervals, forcing_provider, boundary_stage_provider, budget, dynamic_refinement=True, halo_m=8, activity_depth_m=1e-08, step_observer=None, refinement_observer=None, geometry_observer=None, history_directory=None, resource_observer=None):
    from terrain_pipeline.surface_hydraulics import validate_budget as _x39_validate_budget
    _x39_validate_budget(budget)
    if type(intervals) is not int or intervals < 1 or (not _i88_math.isfinite(forcing_interval_s)) or (forcing_interval_s <= 0) or (intervals + 1 > budget.max_snapshots) or (intervals * forcing_interval_s > budget.max_duration_s):
        raise ValueError('adaptive interval/time/snapshot budget invalid')
    canonical_shape = geometry['arrays']['canonical_owner'].shape
    estimate = _i88_np.prod(canonical_shape) * 8 * (100 + 10 * (intervals + 1))
    if estimate > budget.max_bytes:
        raise ValueError('adaptive predeclared memory budget exceeded')
    state = initial_leaf_state(geometry, initial_depth_m)
    if _i88_np.any(state[:, 0] > budget.max_depth_m):
        raise ValueError('adaptive initial depth budget exceeded')
    started = _i88_time.monotonic()
    initial_volume = float(_i88_np.sum(state[:, 0] * geometry['arrays']['leaf_area_m2']))
    supplied = imported = exported = 0.0
    steps = evaluations = limited = refinements = 0
    minimum_dt, maximum_dt, maximum_speed = (_i88_math.inf, 0.0, 0.0)
    snapshots, transactions, interval_ledgers = (CompressedRecordList(history_directory, append_observer=resource_observer), CompressedRecordList(history_directory, append_observer=resource_observer), [])
    geometries = CompressedGeometryHistory(history_directory, append_observer=resource_observer)
    geometries.register(geometry)
    if geometry_observer is not None:
        geometry_observer(geometry)
    first_packets = CompressedRecordList(history_directory, append_observer=resource_observer)
    epoch_packets = CompressedRecordList(history_directory, append_observer=resource_observer)
    max_leaf_count = len(state)

    def retained_bytes(value):
        if hasattr(value, 'storage_nbytes'):
            return value.storage_nbytes
        if isinstance(value, _i88_np.ndarray):
            return value.nbytes
        if isinstance(value, dict):
            return sum((retained_bytes(item) for item in value.values()))
        if isinstance(value, (list, tuple)):
            return sum((retained_bytes(item) for item in value))
        return 0
    observed_peak_bytes = 0
    peak_work_disk_bytes = 0

    def check_memory():
        nonlocal observed_peak_bytes, peak_work_disk_bytes
        retained = retained_bytes(geometry) + retained_bytes(geometries) + retained_bytes(snapshots) + retained_bytes(transactions) + retained_bytes(first_packets) + retained_bytes(epoch_packets)
        scratch = state.nbytes * 18 + len(geometry['arrays']['face_left']) * 8 * 20
        observed_peak_bytes = max(observed_peak_bytes, retained + scratch)
        peak_work_disk_bytes = max(peak_work_disk_bytes, sum((item.temporary_storage_nbytes for item in (geometries, snapshots, transactions, first_packets, epoch_packets))))
        if peak_work_disk_bytes > 2 * 1024 ** 3:
            raise RuntimeError('adaptive temporary history disk budget exceeded')
        if observed_peak_bytes > budget.max_bytes:
            raise RuntimeError('adaptive geometry/history/ledger memory budget exceeded')

    def begin_epoch(physical_time):
        a = geometry['arrays']
        return dict(interval=interval, time_start_s=physical_time, geometry_identity=geometry['identity_sha256'], state_before=state.copy(), internal_transfer=_i88_np.zeros((len(a['face_left']), 3)), boundary_transfer=_i88_np.zeros((len(a['boundary_cell']), 3)), bed_impulse=_i88_np.zeros((len(state), 2)), manning_impulse=_i88_np.zeros((len(state), 2)), forcing_volume_m3=_i88_np.zeros(len(state)))

    def finish_epoch(physical_time):
        nonlocal evaluations
        if physical_time <= epoch['time_start_s']:
            return
        epoch.update(time_end_s=physical_time, state_after=state.copy())
        _, endpoint = adaptive_rhs(geometry, state, tailwater_m=tailwater, gravity=budget.gravity_m_s2, dt=0.0)
        epoch['internal_q_after_m3_s'] = endpoint['internal_flux_m2_s'][:, 0]
        epoch['boundary_q_after_m3_s'] = endpoint['boundary_flux_m2_s'][:, 0]
        evaluations += len(geometry['arrays']['face_left']) + len(geometry['arrays']['boundary_cell'])
        if evaluations > budget.max_face_evaluations:
            raise RuntimeError('adaptive endpoint face-work budget exceeded')
        epoch_packets.append(epoch)
        check_memory()

    def save_snapshot(physical_time):
        h, momentum = canonical_inventory(geometry, state)
        a = geometry['arrays']
        stage = leaf_stages(state[:, 0], a['subcell_count'], a['sorted_subcell_bed_relative_m'], a['prefix_subcell_bed_relative_m'])
        snapshots.append(dict(time_s=physical_time, geometry_identity=geometry['identity_sha256'], state=state.copy(), leaf_row=a['leaf_row'].copy(), leaf_column=a['leaf_column'].copy(), leaf_spacing_m=a['leaf_spacing_m'].copy(), canonical_owner=a['canonical_owner'].copy(), leaf_stage_relative_m=stage, canonical_depth_m=h, canonical_momentum_m2_s=momentum, leaf_counts=geometry['metadata']['leaf_counts'].copy(), leaf_area_m2=geometry['metadata']['leaf_area_m2'].copy()))
    save_snapshot(0.0)
    ledger = [[0.0, 0.0, 0.0, initial_volume, 0.0]]
    for interval in range(intervals):
        forcing = _i88_np.asarray(forcing_provider(interval))
        tailwater = _i88_np.asarray(boundary_stage_provider(interval))
        if forcing.dtype != _i88_np.float64 or forcing.shape != canonical_shape or (not _i88_np.isfinite(forcing).all()) or _i88_np.any(forcing < 0) or (tailwater.dtype != _i88_np.float64) or (tailwater.shape != geometry['arrays']['boundary_cell'].shape) or (not _i88_np.isfinite(tailwater).all()):
            raise ValueError('complete finite canonical forcing and prescribed boundary stage required')
        current, end = (interval * forcing_interval_s, (interval + 1) * forcing_interval_s)
        imported_interval, exported_interval, supplied_interval = (0.0, 0.0, 0.0)
        first = True
        epoch = begin_epoch(current)
        while current < end - 1e-12:
            if steps >= budget.max_substeps or _i88_time.monotonic() - started > budget.max_wall_s:
                raise RuntimeError('adaptive physical execution resource budget exceeded')
            if dynamic_refinement and geometry['arrays']['leaf_spacing_m'].max() > 1:
                h, _ = canonical_inventory(geometry, state)
                a = geometry['arrays']
                desired = anticipated_spacing_map(h, max_leaf_spacing_m=int(a['leaf_spacing_m'].max()), halo_m=halo_m, activity_depth_m=activity_depth_m, canonical_forcing_m3_s=forcing, forcing_prediction_dt_s=budget.max_dt_s, boundary_kind=a['boundary_kind'], tailwater_m=tailwater, canonical_bed_m=a['canonical_bed_m'])
                next_geometry, next_state, transaction = refine_adaptive_state(geometry, state, desired)
                if transaction is not None:
                    finish_epoch(current)
                    transaction.update(time_s=current, interval=interval)
                    transactions.append(transaction)
                    if refinement_observer is not None:
                        refinement_observer(transaction)
                    geometry, state = (next_geometry, next_state)
                    geometries.register(geometry)
                    if geometry_observer is not None:
                        geometry_observer(geometry)
                    refinements += transaction['refined_parent_count']
                    epoch = begin_epoch(current)
                    check_memory()
            a, meta = (geometry['arrays'], geometry['metadata'])
            max_leaf_count = max(max_leaf_count, len(state))
            if len(state) > budget.max_cells:
                raise RuntimeError('adaptive active-leaf budget exceeded')
            stage = leaf_stages(state[:, 0], a['subcell_count'], a['sorted_subcell_bed_relative_m'], a['prefix_subcell_bed_relative_m'])
            velocity = _i88_np.divide(state[:, 1:], state[:, 0, None], out=_i88_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
            maximum_h = _i88_np.maximum(stage - a['sorted_subcell_bed_relative_m'][a['subcell_offset']], 0.0)
            local_speed = abs(velocity).sum(axis=1) + 2 * _i88_np.sqrt(budget.gravity_m_s2 * maximum_h)
            exterior_bed = _i88_np.maximum(a['boundary_bed_relative_m'], a['boundary_crest_m'] - meta['hydraulic_datum_m'])
            exterior_stage = _i88_np.where(a['boundary_kind'] == 1, exterior_bed, tailwater - meta['hydraulic_datum_m'])
            exterior_h = _i88_np.maximum(exterior_stage - exterior_bed, 0.0)
            speed = max(float(local_speed.max(initial=0)), float(2 * _i88_np.sqrt(budget.gravity_m_s2 * exterior_h[a['boundary_kind'] != 0]).max(initial=0)))
            dt = min(budget.max_dt_s, budget.inertial_cfl * float(a['leaf_spacing_m'].min()) / max(speed, 1e-12), end - current)
            source = _i88_np.bincount(a['canonical_owner'].ravel(), weights=forcing.ravel(), minlength=len(state)) / a['leaf_area_m2']
            before = state.copy()
            rhs1, witness1 = adaptive_rhs(geometry, state, tailwater_m=tailwater, gravity=budget.gravity_m_s2, dt=dt)
            rhs1[:, 0] += source
            trial = state + dt * rhs1
            if _i88_np.any(trial[:, 0] < 0):
                raise RuntimeError('adaptive first RK positivity refusal')
            rhs2, witness2 = adaptive_rhs(geometry, trial, tailwater_m=tailwater, gravity=budget.gravity_m_s2, dt=dt)
            rhs2[:, 0] += source
            updated = 0.5 * state + 0.5 * (trial + dt * rhs2)
            before_drag = updated[:, 1:].copy()
            damping, drag_factor = adaptive_drag(geometry, updated, dt=dt, gravity=budget.gravity_m_s2, roughness=budget.roughness_s_m_third)
            updated[:, 1:] *= damping[:, None]
            if not _i88_np.isfinite(updated).all() or _i88_np.any(updated[:, 0] < 0) or _i88_np.any(updated[:, 0] > budget.max_depth_m):
                raise RuntimeError('adaptive final RK depth refusal; no clipping')
            boundary_q = 0.5 * (witness1['boundary_flux_m2_s'][:, 0] + witness2['boundary_flux_m2_s'][:, 0])
            step_imported, step_exported = (float(dt * _i88_np.maximum(-boundary_q, 0.0).sum()), float(dt * _i88_np.maximum(boundary_q, 0.0).sum()))
            step_supplied = float(dt * forcing.sum())
            imported += step_imported
            exported += step_exported
            supplied += step_supplied
            imported_interval += step_imported
            exported_interval += step_exported
            supplied_interval += step_supplied
            limited += witness1['limited_donors'] + witness2['limited_donors']
            epoch['internal_transfer'] += 0.5 * dt * (witness1['internal_flux_m2_s'] + witness2['internal_flux_m2_s'])
            epoch['boundary_transfer'] += 0.5 * dt * (witness1['boundary_flux_m2_s'] + witness2['boundary_flux_m2_s'])
            epoch['bed_impulse'] += 0.5 * dt * (witness1['bed_source'][:, 1:] + witness2['bed_source'][:, 1:]) * a['leaf_area_m2'][:, None]
            epoch['manning_impulse'] += (updated[:, 1:] - before_drag) * a['leaf_area_m2'][:, None]
            epoch['forcing_volume_m3'] += dt * source * a['leaf_area_m2']
            if first or step_observer is not None:
                packet = dict(interval=interval, time_start_s=current, dt_s=dt, geometry_identity=geometry['identity_sha256'], state_before=before, state_predictor=trial, state_after=updated.copy(), rk1_internal_flux=witness1['internal_flux_m2_s'], rk2_internal_flux=witness2['internal_flux_m2_s'], rk1_boundary_flux=witness1['boundary_flux_m2_s'], rk2_boundary_flux=witness2['boundary_flux_m2_s'], rk1_bed_source=witness1['bed_source'], rk2_bed_source=witness2['bed_source'], manning_momentum_change=updated[:, 1:] - before_drag, manning_inverse_depth_third_mean=drag_factor, leaf_area_m2=a['leaf_area_m2'].copy(), face_left=a['face_left'].copy(), face_right=a['face_right'].copy(), face_axis=a['face_axis'].copy(), face_crest_relative_m=a['face_crest_relative_m'].copy(), boundary_cell=a['boundary_cell'].copy(), forcing_m3_s=source * a['leaf_area_m2'], tailwater_m=tailwater.copy())
                if first:
                    first_packets.append(packet)
                if step_observer is not None:
                    step_observer(packet)
                first = False
            state = updated
            current += dt
            steps += 1
            evaluations += 2 * (len(a['face_left']) + len(a['boundary_cell']))
            if evaluations > budget.max_face_evaluations:
                raise RuntimeError('adaptive face-work budget exceeded')
            minimum_dt, maximum_dt = (min(minimum_dt, dt), max(maximum_dt, dt))
            maximum_speed = max(maximum_speed, speed)
        finish_epoch(end)
        volume = float(_i88_np.sum(state[:, 0] * geometry['arrays']['leaf_area_m2']))
        ledger.append([supplied, imported, exported, volume, volume - initial_volume - supplied - imported + exported])
        interval_ledgers.append(dict(interval=interval, supplied_m3=supplied_interval, boundary_input_m3=imported_interval, boundary_output_m3=exported_interval, final_volume_m3=volume))
        save_snapshot(end)
        check_memory()
    return dict(geometry=geometry, geometries=geometries, snapshots=snapshots, refinement_transactions=transactions, first_rk_packets=first_packets, epoch_packets=epoch_packets, ledger=_i88_np.asarray(ledger), interval_ledgers=interval_ledgers, metadata=dict(model=MODEL, execution_backend='numba_scalar_components_fastmath_false_lossless_npz_level1_workspace_segmented_spool', status='completed', wall_s=_i88_time.monotonic() - started, substeps=steps, face_evaluations=evaluations, initial_volume_m3=initial_volume, final_volume_m3=float(ledger[-1][3]), boundary_input_m3=imported, boundary_output_m3=exported, supplied_m3=supplied, maximum_active_leaf_count=max_leaf_count, finest_spacing_m=int(geometry['arrays']['leaf_spacing_m'].min()), minimum_dt_s=minimum_dt, maximum_dt_s=maximum_dt, maximum_wave_speed_m_s=maximum_speed, limited_donors=limited, refined_parent_count=refinements, dynamic_refinement=dynamic_refinement, halo_m=halo_m, activity_depth_m=activity_depth_m, estimated_peak_bytes=int(estimate), observed_peak_bytes_estimate=int(observed_peak_bytes), uniform_coarse_convergence_claim=False, peak_work_disk_bytes=int(peak_work_disk_bytes), history_serialized_bytes=int(sum((item.serialized_nbytes for item in (geometries, snapshots, transactions, first_packets, epoch_packets)))), scope='single-domain adaptive independent leaf evolution; canonical inventory reconstruction is not a hidden 1m solve', limitation='refinement only; active depth threshold predeclared; coarse represented stage/velocity uniform; engineering boundaries uncalibrated'))
FLAGS = ('hydraulic_ready', 'natural_outlet_verified', 'publishable')
MAX_BYTES = 268435456

def near(actual, expected, label):
    if _i91_np.shape(actual) != _i91_np.shape(expected) or not _i91_np.isfinite(actual).all() or (not _i91_np.isfinite(expected).all()) or (not _i91_np.allclose(actual, expected, atol=2e-09, rtol=2e-11)):
        raise ValueError('adaptive saved ' + label + ' mismatch')

def validate_geometry(geometry):
    a, m = (geometry['arrays'], geometry['metadata'])
    if m.get('model') != MODEL or geometry_identity(a, m) != geometry['identity_sha256']:
        raise ValueError('adaptive raw geometry model/identity mismatch')
    bed = a['canonical_bed_m']
    if bed.dtype != _i91_np.float64 or bed.ndim != 2 or (not _i91_np.isfinite(bed).all()) or (bed.size > 65536) or any((size % 4 for size in bed.shape)):
        raise ValueError('adaptive canonical geometry budget/type mismatch')
    rows, columns = bed.shape
    n = len(a['leaf_row'])
    expected_names = {'canonical_bed_m', 'requested_spacing_m', 'leaf_row', 'leaf_column', 'leaf_spacing_m', 'leaf_area_m2', 'canonical_owner', 'subcell_count', 'subcell_offset', 'sorted_subcell_bed_relative_m', 'prefix_subcell_bed_relative_m', 'face_left', 'face_right', 'face_axis', 'face_canonical_row', 'face_canonical_column', 'face_crest_relative_m', 'boundary_cell', 'boundary_axis', 'boundary_sign', 'boundary_kind', 'boundary_crest_m', 'boundary_bed_relative_m'}
    if set(a) != expected_names or m['hydraulic_datum_m'] != float(bed.min()) or (not 1 <= n <= bed.size):
        raise ValueError('adaptive exact geometry fields/datum mismatch')
    integers = {'requested_spacing_m', 'leaf_row', 'leaf_column', 'leaf_spacing_m', 'canonical_owner', 'subcell_count', 'subcell_offset', 'face_left', 'face_right', 'face_axis', 'face_canonical_row', 'face_canonical_column', 'boundary_cell', 'boundary_axis', 'boundary_kind'}
    if any((value.dtype != (_i91_np.int64 if name in integers else _i91_np.float64) or not _i91_np.isfinite(value).all() for name, value in a.items())) or not _i91_np.isin(a['face_axis'], [0, 1]).all():
        raise ValueError('adaptive exact geometry dtypes/axes/finite mismatch')
    if any((a[name].shape != (n,) for name in ('leaf_row', 'leaf_column', 'leaf_spacing_m', 'leaf_area_m2', 'subcell_count', 'subcell_offset'))):
        raise ValueError('adaptive exact leaf field shape mismatch')
    owner = _i91_np.full(bed.shape, -1, _i91_np.int64)
    coverage = _i91_np.zeros(bed.shape, _i91_np.int64)
    sorted_bed, prefix = (_i91_np.zeros(bed.size), _i91_np.zeros(bed.size))
    offsets = _i91_np.r_[0, _i91_np.cumsum(a['subcell_count'])[:-1]]
    if not _i91_np.array_equal(a['subcell_offset'], offsets):
        raise ValueError('adaptive compact canonical offsets mismatch')
    for leaf, (row, column, size) in enumerate(zip(a['leaf_row'], a['leaf_column'], a['leaf_spacing_m'])):
        if size not in (1, 2, 4) or row < 0 or column < 0 or row % size or column % size or (row + size > rows) or (column + size > columns):
            raise ValueError('adaptive aligned leaf bounds mismatch')
        patch = (slice(row, row + size), slice(column, column + size))
        coverage[patch] += 1
        owner[patch] = leaf
        samples = _i91_np.sort((bed[patch] - m['hydraulic_datum_m']).ravel())
        offset = offsets[leaf]
        sorted_bed[offset:offset + size * size] = samples
        prefix[offset:offset + size * size] = _i91_np.cumsum(samples)
    if _i91_np.any(coverage != 1) or not _i91_np.array_equal(owner, a['canonical_owner']):
        raise ValueError('adaptive entire canonical leaf partition mismatch')
    if not _i91_np.array_equal(a['subcell_count'], a['leaf_spacing_m'] ** 2) or not _i91_np.array_equal(a['leaf_area_m2'], a['leaf_spacing_m'].astype(float) ** 2):
        raise ValueError('adaptive exact leaf area/count mismatch')
    near(a['sorted_subcell_bed_relative_m'], sorted_bed, 'canonical sorted support')
    near(a['prefix_subcell_bed_relative_m'], prefix, 'canonical prefix support')
    requests = a['requested_spacing_m']
    if requests.shape != bed.shape or requests.dtype != _i91_np.int64 or (not _i91_np.isin(requests, [1, 2, 4]).all()):
        raise ValueError('adaptive requested spacing declaration mismatch')
    for direction in (0, 1):
        before, after = (owner[:, :-1], owner[:, 1:]) if direction == 0 else (owner[:-1], owner[1:])
        mask = before != after
        row, column = _i91_np.nonzero(mask)
        selected = a['face_axis'] == direction
        expected_row, expected_column = (row, column + 1) if direction == 0 else (row + 1, column)
        for name, expected in (('face_left', before[mask]), ('face_right', after[mask]), ('face_canonical_row', expected_row), ('face_canonical_column', expected_column)):
            if not _i91_np.array_equal(a[name][selected], expected):
                raise ValueError('adaptive unique complete canonical segment ' + name + ' mismatch')
        adjacent_first, adjacent_second = (bed[:, :-1], bed[:, 1:]) if direction == 0 else (bed[:-1], bed[1:])
        near(a['face_crest_relative_m'][selected], _i91_np.maximum(adjacent_first, adjacent_second)[mask] - m['hydraulic_datum_m'], 'canonical segment crest')
    boundary = _i91_np.r_[owner[:, 0], owner[:, -1], owner[0], owner[-1]]
    bbed = _i91_np.r_[bed[:, 0], bed[:, -1], bed[0], bed[-1]]
    for name, expected in (('boundary_cell', boundary), ('boundary_axis', _i91_np.r_[_i91_np.zeros(2 * rows, _i91_np.int64), _i91_np.ones(2 * columns, _i91_np.int64)]), ('boundary_sign', _i91_np.r_[-_i91_np.ones(rows), _i91_np.ones(rows), -_i91_np.ones(columns), _i91_np.ones(columns)])):
        if not _i91_np.array_equal(a[name], expected):
            raise ValueError('adaptive canonical boundary incidence mismatch')
    near(a['boundary_bed_relative_m'], bbed - m['hydraulic_datum_m'], 'boundary bed')
    if a['boundary_kind'].dtype != _i91_np.int64 or a['boundary_kind'].shape != boundary.shape or (not _i91_np.isin(a['boundary_kind'], [0, 1, 2]).all()) or _i91_np.any(a['boundary_crest_m'] < bbed):
        raise ValueError('adaptive complete boundary declaration mismatch')
    for size in (1, 2, 4):
        count = int(_i91_np.sum(a['leaf_spacing_m'] == size))
        if m['leaf_counts'][str(size)] != count or m['leaf_area_m2'][str(size)] != count * size ** 2:
            raise ValueError('adaptive leaf occupancy metadata mismatch')
    for name, expected in (('leaf_count', n), ('total_area_m2', bed.size), ('internal_segment_count', len(a['face_left'])), ('boundary_segment_count', len(boundary)), ('canonical_shape', list(bed.shape))):
        if m[name] != expected:
            raise ValueError('adaptive complete geometry metadata mismatch')
    if m.get('full_selected_window_covered') is not True or m.get('uniform_coarse_convergence_claim') is not False:
        raise ValueError('adaptive unsupported geometry claim')
    return True

def storage_stage(depth, geometry):
    a = geometry['arrays']
    answer = _i91_np.empty(len(depth))
    counts, offsets = (a['subcell_count'], a['subcell_offset'])
    bed, prefix = (a['sorted_subcell_bed_relative_m'], a['prefix_subcell_bed_relative_m'])
    for count in _i91_np.unique(counts):
        cells = _i91_np.flatnonzero(counts == count)
        if count == 1:
            answer[cells] = depth[cells] + prefix[offsets[cells]]
            continue
        indices = offsets[cells, None] + _i91_np.arange(count)
        volume = depth[cells] * count
        wet = _i91_np.maximum(_i91_np.count_nonzero(volume[:, None] >= _i91_np.arange(1, count + 1) * bed[indices] - prefix[indices], axis=1), 1)
        answer[cells] = (volume + prefix[indices[_i91_np.arange(len(cells)), wet - 1]]) / wet
    return answer

def validate_snapshot(snapshot, geometry):
    a = geometry['arrays']
    n, shape = (len(a['leaf_row']), a['canonical_bed_m'].shape)
    expected = {'state': (n, 3), 'leaf_row': (n,), 'leaf_column': (n,), 'leaf_spacing_m': (n,), 'canonical_owner': shape, 'leaf_stage_relative_m': (n,), 'canonical_depth_m': shape, 'canonical_momentum_m2_s': (*shape, 2)}
    arrays = {name: value for name, value in snapshot.items() if isinstance(value, _i91_np.ndarray)}
    if set(arrays) != set(expected) or any((value.shape != expected[name] or not _i91_np.isfinite(value).all() for name, value in arrays.items())):
        raise ValueError('adaptive exact snapshot layout mismatch')
    if snapshot['geometry_identity'] != geometry['identity_sha256'] or _i91_np.any(snapshot['state'][:, 0] < 0):
        raise ValueError('adaptive snapshot source/depth mismatch')
    if snapshot['leaf_counts'] != geometry['metadata']['leaf_counts'] or snapshot['leaf_area_m2'] != geometry['metadata']['leaf_area_m2']:
        raise ValueError('adaptive snapshot leaf occupancy declaration mismatch')
    for name in ('leaf_row', 'leaf_column', 'leaf_spacing_m', 'canonical_owner'):
        if arrays[name].dtype != _i91_np.int64 or not _i91_np.array_equal(arrays[name], a[name]):
            raise ValueError('adaptive exact snapshot leaf geometry mismatch')
    for name in set(arrays) - {'leaf_row', 'leaf_column', 'leaf_spacing_m', 'canonical_owner'}:
        if arrays[name].dtype != _i91_np.float64:
            raise ValueError('adaptive exact snapshot floating type mismatch')
    state = snapshot['state']
    stage = storage_stage(state[:, 0], geometry)
    near(snapshot['leaf_stage_relative_m'], stage, 'snapshot inverse storage')
    owner = a['canonical_owner']
    depth = _i91_np.maximum(stage[owner] - (a['canonical_bed_m'] - geometry['metadata']['hydraulic_datum_m']), 0)
    velocity = _i91_np.divide(state[:, 1:], state[:, 0, None], out=_i91_np.zeros_like(state[:, 1:]), where=state[:, 0, None] > 0)
    near(snapshot['canonical_depth_m'], depth, 'snapshot canonical inventory')
    near(snapshot['canonical_momentum_m2_s'], depth[:, :, None] * velocity[owner], 'snapshot canonical momentum inventory')
    near(_i91_np.bincount(owner.ravel(), weights=depth.ravel(), minlength=len(state)), state[:, 0] * a['leaf_area_m2'], 'snapshot leaf storage')
    return True

def _bundle(item, schema):
    from terrain_pipeline.common_infra import identity as _i91_identity
    arrays = {name: value for name, value in item.items() if isinstance(value, _i91_np.ndarray)}
    metadata = {name: value for name, value in item.items() if not isinstance(value, _i91_np.ndarray)}
    metadata.update(schema=schema, **{name: False for name in FLAGS})
    return dict(arrays=arrays, metadata=metadata, identity_sha256=_i91_identity(arrays, metadata))

def _unpack(bundle):
    return dict(bundle['metadata'], **bundle['arrays'])

def _record(path, bundle):
    from terrain_pipeline.common_infra import file_sha256 as _i91_file_sha256
    return dict(path=str(path.resolve()), expected_sha256=_i91_file_sha256(path), expected_identity=bundle['identity_sha256'])

def _headers(headers):
    for name, (shape, dtype) in headers.items():
        if name == 'manifest':
            if dtype != _i91_np.uint8 or len(shape) != 1 or _i91_math.prod(shape) > 1048576:
                raise ValueError('adaptive bounded manifest required')
        elif dtype not in (_i91_np.dtype('float64'), _i91_np.dtype('int64'), _i91_np.dtype('bool')) or _i91_math.prod(shape) > 2000000:
            raise ValueError('adaptive bounded array headers required')

def _load(record, root, expected_name, schema):
    from terrain_pipeline.common_infra import load_bundle as _i91_load_bundle
    path = _i91_Path(record['path']).resolve(strict=True)
    if path != (root / expected_name).resolve(strict=True) or not path.is_relative_to(root):
        raise ValueError('adaptive exact saved layout mismatch')
    result = _i91_load_bundle(path, expected_sha256=record['expected_sha256'], max_bytes=MAX_BYTES, header_validator=_headers, validator=lambda item: True)
    if result['identity_sha256'] != record['expected_identity'] or result['metadata'].get('schema') != schema or any((result['metadata'].get(name) is not False for name in FLAGS)) or any((not _i91_np.isfinite(value).all() for value in result['arrays'].values())):
        raise ValueError('adaptive saved identity/schema/finite/flags mismatch')
    return result

def _source_binding(source, canonical, forcing, snapshots, first_geometry):
    """Bind copied schedules to the original saved fine run, with explicit lake override."""
    from terrain_pipeline.common_infra import load_bundle as _i91_load_bundle
    from terrain_pipeline.runoff import _strict_json as _i91__strict_json
    source_path = _i91_Path(source['path'])
    if source_path.suffix != '.json':
        return 'external canonical source; independent provenance audit required'
    original = _i91__strict_json(source_path.read_text(encoding='utf-8'))
    if original.get('schema') != 'single-domain-fine-run-index-v1':
        return 'external canonical source; independent provenance audit required'

    def read(record):
        result = _i91_load_bundle(record['path'], expected_sha256=record['expected_sha256'], max_bytes=MAX_BYTES, header_validator=_headers, validator=lambda item: True)
        if result['identity_sha256'] != record['expected_identity']:
            raise ValueError('adaptive original fine source identity mismatch')
        return result
    bed = read(original['bed_record'])
    if not _i91_np.array_equal(bed['arrays']['canonical_bed_center_m'], canonical['arrays']['canonical_bed_m']):
        raise ValueError('adaptive original canonical bed witness mismatch')
    source_forcing, source_states, source_geometry = (read(original['forcing']), read(original['states']), read(original['geometry']))
    shape = first_geometry['arrays']['canonical_bed_m'].shape
    near(snapshots[0]['canonical_depth_m'], source_states['arrays']['initial_depth_m'].reshape(shape), 'original canonical initial inventory')
    near(forcing['tailwater_m'], source_forcing['arrays']['boundary_stage_m'], 'original prescribed stage schedule')
    near(_i91_np.asarray(forcing['dt_s']), _i91_np.asarray(source_forcing['metadata']['dt_s']), 'original forcing interval')
    original_q = source_forcing['arrays']['local_q_m3_s'].reshape(forcing['forcing_m3_s'].shape)
    if _i91_np.array_equal(forcing['forcing_m3_s'], original_q) and _i91_np.array_equal(first_geometry['arrays']['boundary_kind'], source_geometry['arrays']['boundary_kind']):
        return 'original saved canonical source/time schedule'
    if _i91_np.all(forcing['forcing_m3_s'] == 0) and _i91_np.all(first_geometry['arrays']['boundary_kind'] == 0):
        return 'explicit zero-source closed lake correction of prior soil-release case'
    raise ValueError('adaptive original hydraulic forcing/boundary schedule changed')

class SavedGeometryMapping(_i91_Mapping):
    """Load at most two historical meshes, keeping cold-read memory bounded."""

    def __init__(self, records, root):
        self.records, self.root = (records, root)
    __hash__ = object.__hash__

    def __len__(self):
        return len(self.records)

    def __iter__(self):
        return iter(self.records)

    @_i91_lru_cache(maxsize=2)
    def __getitem__(self, key):
        record = self.records[key]
        name = _i91_Path(record['path']).name
        if not name.startswith('geometry-') or not name.endswith('.npz'):
            raise ValueError('adaptive geometry history filename mismatch')
        bundle = _load(record, self.root, name, 'surface-adaptive-geometry-v1')
        geometry = dict(arrays=bundle['arrays'], metadata=bundle['metadata']['raw_geometry_metadata'], identity_sha256=bundle['metadata']['raw_geometry_identity'])
        if key != geometry['identity_sha256']:
            raise ValueError('adaptive historical geometry binding mismatch')
        validate_geometry(geometry)
        return geometry

class SavedRecordSequence(_i91_Sequence):

    def __init__(self, records, root, prefix, schema, digits):
        self.records, self.root, self.prefix, self.schema, self.digits = (records, root, prefix, schema, digits)

    def __len__(self):
        return len(self.records)

    def __getitem__(self, number):
        if isinstance(number, slice):
            return [self[index] for index in range(*number.indices(len(self)))]
        if number < 0:
            number += len(self)
        record = self.records[number]
        return _unpack(_load(record, self.root, f'{self.prefix}-{number:0{self.digits}d}.npz', self.schema))

def validate_epoch(packet, geometry):
    a = geometry['arrays']
    n, f, b = (len(a['leaf_row']), len(a['face_left']), len(a['boundary_cell']))
    shapes = dict(state_before=(n, 3), state_after=(n, 3), internal_transfer=(f, 3), boundary_transfer=(b, 3), bed_impulse=(n, 2), manning_impulse=(n, 2), forcing_volume_m3=(n,), internal_q_after_m3_s=(f,), boundary_q_after_m3_s=(b,))
    arrays = {name: value for name, value in packet.items() if isinstance(value, _i91_np.ndarray)}
    if set(arrays) != set(shapes) or any((value.dtype != _i91_np.float64 or value.shape != shapes[name] or (not _i91_np.isfinite(value).all()) for name, value in arrays.items())):
        raise ValueError('adaptive exact epoch arrays mismatch')
    if packet['geometry_identity'] != geometry['identity_sha256'] or not packet['time_start_s'] < packet['time_end_s'] or _i91_np.any(packet['state_before'][:, 0] < 0) or _i91_np.any(packet['state_after'][:, 0] < 0) or _i91_np.any(packet['forcing_volume_m3'] < 0):
        raise ValueError('adaptive epoch identity/time/depth mismatch')
    change = _i91_np.zeros((n, 3))
    _i91_np.add.at(change, a['face_left'], -packet['internal_transfer'])
    _i91_np.add.at(change, a['face_right'], packet['internal_transfer'])
    _i91_np.add.at(change, a['boundary_cell'], -packet['boundary_transfer'])
    change[:, 0] += packet['forcing_volume_m3']
    change[:, 1:] += packet['bed_impulse'] + packet['manning_impulse']
    near((packet['state_after'] - packet['state_before']) * a['leaf_area_m2'][:, None], change, 'complete epoch water/momentum closure')
    closed = a['boundary_kind'] == 0
    if _i91_np.any(packet['boundary_transfer'][closed, 0] != 0) or _i91_np.any(packet['boundary_q_after_m3_s'][closed] != 0):
        raise ValueError('adaptive closed boundary mass transfer')
    return True

def apply_transaction(packet, before_geometry, after_geometry, before_state):
    a, b = (before_geometry['arrays'], after_geometry['arrays'])
    if packet['before_geometry_identity'] != before_geometry['identity_sha256'] or packet['after_geometry_identity'] != after_geometry['identity_sha256'] or (not _i91_np.array_equal(a['canonical_bed_m'], b['canonical_bed_m'])):
        raise ValueError('adaptive refinement original geometry binding mismatch')
    parent = a['canonical_owner'][b['leaf_row'], b['leaf_column']]
    unchanged = b['leaf_spacing_m'] == a['leaf_spacing_m'][parent]
    child_ids = _i91_np.flatnonzero(~unchanged)
    parent_ids = _i91_np.unique(parent[~unchanged])
    for name, expected in (('parent_leaf_id', parent[~unchanged]), ('refined_parent_leaf_id', parent_ids), ('refined_child_leaf_id', child_ids), ('unchanged_parent_leaf_id', parent[unchanged]), ('unchanged_child_leaf_id', _i91_np.flatnonzero(unchanged))):
        if not _i91_np.array_equal(packet[name], expected):
            raise ValueError('adaptive sparse refinement mapping mismatch')
    if _i91_np.any(b['leaf_spacing_m'] > a['leaf_spacing_m'][parent]):
        raise ValueError('adaptive refinement cannot coarsen')
    stage = storage_stage(before_state[:, 0], before_geometry)
    depth = _i91_np.maximum(stage[a['canonical_owner']] - (a['canonical_bed_m'] - before_geometry['metadata']['hydraulic_datum_m']), 0)
    velocity = _i91_np.divide(before_state[:, 1:], before_state[:, 0, None], out=_i91_np.zeros_like(before_state[:, 1:]), where=before_state[:, 0, None] > 0)
    momentum = depth[:, :, None] * velocity[a['canonical_owner']]
    next_state = _i91_np.empty((len(parent), 3))
    next_state[unchanged] = before_state[parent[unchanged]]
    for child in child_ids:
        row, column, size = (b['leaf_row'][child], b['leaf_column'][child], b['leaf_spacing_m'][child])
        patch = (slice(row, row + size), slice(column, column + size))
        next_state[child, 0] = depth[patch].mean()
        next_state[child, 1:] = momentum[patch].mean(axis=(0, 1))
    before_inventory = before_state * a['leaf_area_m2'][:, None]
    after_inventory = next_state * b['leaf_area_m2'][:, None]
    near(packet['parent_inventory_m3_m4_s'], before_inventory[parent_ids], 'refinement saved parent inventory')
    near(packet['child_inventory_m3_m4_s'], after_inventory[child_ids], 'refinement saved child inventory')
    grouped = _i91_np.zeros_like(before_inventory)
    _i91_np.add.at(grouped, parent, after_inventory)
    near(grouped, before_inventory, 'refinement complete inventory conservation')
    near(packet['parent_grouped_residual'], (grouped - before_inventory)[parent_ids], 'refinement declared residual')
    return next_state

def save_adaptive_run(path, result, *, forcing_m3_s, tailwater_m, forcing_interval_s, budget, source_record, code_sha256, code_records=None, resource_observer=None):
    """Save only snapshots, geometry epochs and sampled steps, never all substeps."""
    from terrain_pipeline.common_infra import save_bundle as _i91_save_bundle
    from terrain_pipeline.common_infra import file_sha256 as _i91_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i91_publish_bytes
    root = _i91_Path(path).resolve()
    root.mkdir(parents=True, exist_ok=False)
    geometries = result['geometries']
    records = {}

    def write(name, item, schema):
        bundle = _bundle(item, schema)
        target = root / name
        _i91_save_bundle(target, bundle, validator=lambda value: True)
        record = _record(target, bundle)
        _load(record, root, name, schema)
        if resource_observer is not None:
            resource_observer()
        return record

    def load_original_record(record, schema):
        item = _unpack(_load(record, root, _i91_Path(record['path']).name, schema))
        for name in ('schema', *FLAGS):
            item.pop(name, None)
        return item

    def bind_record(collection, number, record, schema):
        if hasattr(collection, 'bind_saved_record'):
            collection.bind_saved_record(number, record, lambda pin: load_original_record(pin, schema))
            if resource_observer is not None:
                resource_observer()

    def load_original_geometry(record):
        bundle = _load(record, root, _i91_Path(record['path']).name, 'surface-adaptive-geometry-v1')
        geometry = dict(arrays=bundle['arrays'], metadata=bundle['metadata']['raw_geometry_metadata'], identity_sha256=bundle['metadata']['raw_geometry_identity'])
        if geometry_identity(geometry['arrays'], geometry['metadata']) != geometry['identity_sha256']:
            raise ValueError('adaptive archived original geometry identity mismatch')
        return geometry
    for number, (key, geometry) in enumerate(geometries.items()):
        validate_geometry(geometry)
        if key != geometry['identity_sha256']:
            raise ValueError('adaptive geometry history key mismatch')
        records[key] = write(f'geometry-{number:04d}.npz', dict(geometry['arrays'], raw_geometry_metadata=geometry['metadata'], raw_geometry_identity=key), 'surface-adaptive-geometry-v1')
        if hasattr(geometries, 'bind_saved_geometry'):
            geometries.bind_saved_geometry(key, records[key], load_original_geometry)
            if resource_observer is not None:
                resource_observer()
    snapshots = []
    for number, item in enumerate(result['snapshots']):
        validate_snapshot(item, geometries[item['geometry_identity']])
        record = write(f'snapshot-{number:03d}.npz', item, 'surface-adaptive-canonical-snapshot-v1')
        snapshots.append(record)
        bind_record(result['snapshots'], number, record, 'surface-adaptive-canonical-snapshot-v1')
    epochs = []
    for number, item in enumerate(result['epoch_packets']):
        validate_epoch(item, geometries[item['geometry_identity']])
        record = write(f'epoch-{number:04d}.npz', item, 'surface-adaptive-epoch-v1')
        epochs.append(record)
        bind_record(result['epoch_packets'], number, record, 'surface-adaptive-epoch-v1')

    def write_sequence(collection, prefix, schema, digits):
        records = []
        for number, item in enumerate(collection):
            record = write(f'{prefix}-{number:0{digits}d}.npz', item, schema)
            records.append(record)
            bind_record(collection, number, record, schema)
        return records
    transactions = write_sequence(result['refinement_transactions'], 'refinement', 'surface-adaptive-refinement-v1', 4)
    steps = write_sequence(result['first_rk_packets'], 'step', 'surface-adaptive-first-step-v1', 3)
    forcing = write('forcing.npz', dict(forcing_m3_s=_i91_np.asarray(forcing_m3_s), tailwater_m=_i91_np.asarray(tailwater_m), dt_s=forcing_interval_s), 'surface-adaptive-forcing-v1')
    first_geometry = geometries[result['snapshots'][0]['geometry_identity']]
    canonical_source = write('canonical-source.npz', dict(canonical_bed_m=first_geometry['arrays']['canonical_bed_m'], origin_m_xz=first_geometry['metadata']['origin_m_xz'], source_record=source_record), 'surface-adaptive-canonical-source-v1')
    states = write('ledger.npz', dict(ledger=result['ledger'], solver_metadata=result['metadata'], interval_ledgers=result['interval_ledgers']), 'surface-adaptive-ledger-v1')
    if sum((target.stat().st_size for target in root.iterdir())) > 2147483648:
        raise ValueError('adaptive saved output exceeds 2GiB')
    index = dict(schema='surface-adaptive-run-index-v1', model=MODEL, geometries=records, snapshots=snapshots, epochs=epochs, refinements=transactions, first_steps=steps, forcing=forcing, canonical_source=canonical_source, states=states, budget=vars(budget) if hasattr(budget, '__dict__') else budget, source_record=source_record, code_sha256=code_sha256, equations_sampled=True, all_substep_states_saved=False, stage_accepted=False, uniform_coarse_convergence_claim=False, **{name: False for name in FLAGS})
    if code_records is not None:
        index['code_records'] = code_records
    target = root / 'index.json'
    _i91_publish_bytes(target, (_i91_json.dumps(index, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    if resource_observer is not None:
        resource_observer()
    pin = dict(path=str(target), expected_sha256=_i91_file_sha256(target))
    load_adaptive_run(target, expected_sha256=pin['expected_sha256'])
    return pin

def load_adaptive_run(path, *, expected_sha256, repository_root=None):
    from terrain_pipeline.common_infra import file_sha256 as _i91_file_sha256
    from terrain_pipeline.runoff import _strict_json as _i91__strict_json
    path = _i91_Path(path).resolve(strict=True)
    if path.stat().st_size > 8 * 1024 ** 2 or _i91_file_sha256(path) != expected_sha256:
        raise ValueError('adaptive index external hash/budget mismatch')
    index = _i91__strict_json(path.read_text(encoding='utf-8'))
    root = path.parent
    if index.get('schema') != 'surface-adaptive-run-index-v1' or index.get('model') != MODEL or any((index.get(name) is not False for name in FLAGS)) or (index.get('stage_accepted') is not False) or (index.get('uniform_coarse_convergence_claim') is not False):
        raise ValueError('adaptive unsupported index schema/claim')
    if not isinstance(index.get('code_sha256'), dict) or not index['code_sha256'] or (not index['geometries']):
        raise ValueError('adaptive frozen implementation and historical geometry pins required')
    records = list(index['geometries'].values()) + index['snapshots'] + index['epochs'] + index['refinements'] + index['first_steps'] + [index['forcing'], index['canonical_source'], index['states']]
    if sum((_i91_Path(record['path']).stat().st_size for record in records)) > 2147483648 or any((_i91_Path(record['path']).stat().st_size > MAX_BYTES for record in records)):
        raise ValueError('adaptive saved archive output/artifact budgets exceeded')
    from terrain_pipeline.fine_subgrid import _validate_code_records
    if 'code_records' in index:
        _validate_code_records(index['code_sha256'], index['code_records'], root.parent)
    else:
        repository = _i91_Path(repository_root).resolve() if repository_root is not None else _i91_Path(__file__).resolve().parents[1]
        for name, digest in index['code_sha256'].items():
            relative = _i91_Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('implementation code path escapes repository')
            target = (repository / relative).resolve()
            if not target.is_relative_to(repository):
                raise ValueError('implementation code path escapes repository')
            current = _i91_file_sha256(target) if target.is_file() else None
            from terrain_pipeline.common_infra import published_algorithm_matches
            if not published_algorithm_matches('surface_adaptive', {name: digest}, {name: current} if current is not None else {}):
                raise ValueError('historical implementation is not registered')
    source = index['source_record']
    if _i91_file_sha256(source['path']) != source['expected_sha256']:
        raise ValueError('adaptive original canonical source hash mismatch')
    geometries = SavedGeometryMapping(index['geometries'], root)
    canonical_source = _load(index['canonical_source'], root, 'canonical-source.npz', 'surface-adaptive-canonical-source-v1')
    for key in geometries:
        geometry = geometries[key]
        if not _i91_np.array_equal(geometry['arrays']['canonical_bed_m'], canonical_source['arrays']['canonical_bed_m']) or geometry['metadata']['origin_m_xz'] != canonical_source['metadata']['origin_m_xz'] or canonical_source['metadata']['source_record'] != source:
            raise ValueError('adaptive complete geometry original canonical source mismatch')

    def read_sequence(role, prefix, schema):
        return SavedRecordSequence(index[role], root, prefix, schema, 3 if role in ('snapshots', 'first_steps') else 4)
    snapshots = read_sequence('snapshots', 'snapshot', 'surface-adaptive-canonical-snapshot-v1')
    epochs = read_sequence('epochs', 'epoch', 'surface-adaptive-epoch-v1')
    transactions = read_sequence('refinements', 'refinement', 'surface-adaptive-refinement-v1')
    steps = read_sequence('first_steps', 'step', 'surface-adaptive-first-step-v1')
    forcing = _unpack(_load(index['forcing'], root, 'forcing.npz', 'surface-adaptive-forcing-v1'))
    states = _unpack(_load(index['states'], root, 'ledger.npz', 'surface-adaptive-ledger-v1'))
    n = len(steps)
    first_geometry = geometries[snapshots[0]['geometry_identity']]
    shape = first_geometry['arrays']['canonical_bed_m'].shape
    dt = forcing['dt_s']
    if not 1 <= n <= 48 or len(snapshots) != n + 1 or forcing['forcing_m3_s'].dtype != _i91_np.float64 or (forcing['tailwater_m'].dtype != _i91_np.float64) or _i91_np.any(forcing['forcing_m3_s'] < 0) or (forcing['forcing_m3_s'].shape != (n, *shape)) or (forcing['tailwater_m'].shape != (n, 2 * sum(shape))) or (not 0 < dt <= 3600):
        raise ValueError('adaptive complete bounded forcing/snapshot coverage mismatch')
    for number, snapshot in enumerate(snapshots):
        near(_i91_np.asarray(snapshot['time_s']), _i91_np.asarray(number * dt), 'snapshot physical time')
        validate_snapshot(snapshot, geometries[snapshot['geometry_identity']])
        if _i91_np.any(snapshot['state'][:, 0] > index['budget']['max_depth_m']) or len(snapshot['state']) > index['budget']['max_cells']:
            raise ValueError('adaptive snapshot depth/active-leaf budget exceeded')
    _verify_chain(index, geometries, snapshots, epochs, transactions, steps, forcing, states)
    source_semantics = _source_binding(source, canonical_source, forcing, snapshots, first_geometry)
    if _i91_file_sha256(path) != expected_sha256:
        raise ValueError('adaptive index changed during load')
    return dict(index=index, geometries=geometries, snapshots=snapshots, epochs=epochs, refinements=transactions, first_steps=steps, forcing=forcing, canonical_source=canonical_source, states=states, source_semantics=source_semantics, solver_advanced=False, equations_sampled=True)

def _verify_chain(index, geometries, snapshots, epochs, transactions, steps, forcing, states):
    dt, n = (forcing['dt_s'], len(steps))
    budget = index['budget']
    if budget['max_wall_s'] > 1800 or budget['max_bytes'] > MAX_BYTES or budget['max_cells'] > 65536:
        raise ValueError('adaptive predeclared budget mismatch')
    metadata = states['solver_metadata']
    if metadata['status'] != 'completed' or metadata['model'] != MODEL or metadata['wall_s'] > 1800 or (metadata['substeps'] > budget['max_substeps']) or (metadata['face_evaluations'] > budget['max_face_evaluations']):
        raise ValueError('adaptive complete solver work mismatch')
    key = snapshots[0]['geometry_identity']
    current = snapshots[0]['state']
    time = 0.0
    transaction_number = 0
    seen_intervals = set()
    supplies = _i91_np.zeros(n)
    boundaries = _i91_np.zeros(n)
    for epoch in epochs:
        interval = epoch['interval']
        if type(interval) is not int or not 0 <= interval < n or abs(epoch['time_start_s'] - time) > 1e-09 or (epoch['time_end_s'] > (interval + 1) * dt + 1e-09):
            raise ValueError('adaptive uninterrupted epoch timeline mismatch')
        while transaction_number < len(transactions) and abs(transactions[transaction_number]['time_s'] - time) <= 1e-09:
            transaction = transactions[transaction_number]
            if transaction['interval'] != interval or transaction['before_geometry_identity'] != key:
                raise ValueError('adaptive transaction time/source chain mismatch')
            after_key = transaction['after_geometry_identity']
            current = apply_transaction(transaction, geometries[key], geometries[after_key], current)
            key = after_key
            transaction_number += 1
        if epoch['geometry_identity'] != key:
            raise ValueError('adaptive epoch geometry chain mismatch')
        geometry = geometries[key]
        validate_epoch(epoch, geometry)
        near(epoch['state_before'], current, 'epoch original state continuity')
        a = geometry['arrays']
        duration = epoch['time_end_s'] - epoch['time_start_s']
        source = _i91_np.bincount(a['canonical_owner'].ravel(), weights=forcing['forcing_m3_s'][interval].ravel(), minlength=len(current))
        near(epoch['forcing_volume_m3'], duration * source, 'epoch complete canonical forcing')
        supplies[interval] += epoch['forcing_volume_m3'].sum()
        boundaries[interval] += epoch['boundary_transfer'][:, 0].sum()
        if interval not in seen_intervals:
            step = steps[interval]
            if step['interval'] != interval or step['geometry_identity'] != key or abs(step['time_start_s'] - time) > 1e-09:
                raise ValueError('adaptive complete first-step source/time binding')
            near(step['state_before'], current, 'first-step original epoch state')
            near(step['forcing_m3_s'], source, 'first-step forcing')
            near(step['tailwater_m'], forcing['tailwater_m'][interval], 'first-step tailwater')
            _validate_step_algebra(step, geometry, budget)
            seen_intervals.add(interval)
        current, time = (epoch['state_after'], epoch['time_end_s'])
        if abs(time - (interval + 1) * dt) <= 1e-09:
            snapshot = snapshots[interval + 1]
            if snapshot['geometry_identity'] != key:
                raise ValueError('adaptive interval end original geometry mismatch')
            near(snapshot['state'], current, 'interval end original snapshot state')
    if abs(time - n * dt) > 1e-09 or transaction_number != len(transactions) or seen_intervals != set(range(n)):
        raise ValueError('adaptive full epoch/refinement/interval coverage mismatch')
    ledger = states['ledger']
    if ledger.dtype != _i91_np.float64 or ledger.shape != (n + 1, 5):
        raise ValueError('adaptive exact cumulative ledger shape mismatch')
    volumes = _i91_np.array([_i91_np.sum(snapshot['state'][:, 0] * geometries[snapshot['geometry_identity']]['arrays']['leaf_area_m2']) for snapshot in snapshots])
    near(ledger[:, 0], _i91_np.r_[0, _i91_np.cumsum(supplies)], 'complete ledger supply')
    near(ledger[:, 3], volumes, 'snapshot ledger volume')
    near(_i91_np.diff(ledger[:, 2]) - _i91_np.diff(ledger[:, 1]), boundaries, 'signed boundary ledger')
    near(ledger[:, 4], volumes - volumes[0] - ledger[:, 0] - ledger[:, 1] + ledger[:, 2], 'ledger residual')
    near(ledger[:, 4], _i91_np.zeros(n + 1), 'whole water budget')

def _validate_step_algebra(packet, geometry, budget):
    a = geometry['arrays']
    n, f, b = (len(a['leaf_row']), len(a['face_left']), len(a['boundary_cell']))
    shapes = dict(state_before=(n, 3), state_predictor=(n, 3), state_after=(n, 3), manning_momentum_change=(n, 2), manning_inverse_depth_third_mean=(n,), leaf_area_m2=(n,), face_left=(f,), face_right=(f,), face_axis=(f,), face_crest_relative_m=(f,), boundary_cell=(b,), forcing_m3_s=(n,), tailwater_m=(b,))
    for rk in (1, 2):
        shapes.update({f'rk{rk}_internal_flux': (f, 3), f'rk{rk}_boundary_flux': (b, 3), f'rk{rk}_bed_source': (n, 3)})
    arrays = {name: value for name, value in packet.items() if isinstance(value, _i91_np.ndarray)}
    if set(arrays) != set(shapes) or any((value.shape != shapes[name] or not _i91_np.isfinite(value).all() for name, value in arrays.items())):
        raise ValueError('adaptive exact first-step arrays mismatch')
    for name, value in arrays.items():
        expected_dtype = _i91_np.int64 if name in ('face_left', 'face_right', 'face_axis', 'boundary_cell') else _i91_np.float64
        if value.dtype != expected_dtype:
            raise ValueError('adaptive exact first-step array dtype mismatch')
    if any((_i91_np.any(packet[name][:, 0] < 0) or _i91_np.any(packet[name][:, 0] > budget['max_depth_m']) for name in ('state_before', 'state_predictor', 'state_after'))):
        raise ValueError('adaptive sampled nonnegative/bounded depth mismatch')
    for name in ('leaf_area_m2', 'face_left', 'face_right', 'face_axis', 'face_crest_relative_m', 'boundary_cell'):
        if not _i91_np.array_equal(packet[name], a[name]):
            raise ValueError('adaptive first-step saved incidence mismatch')
    dt = packet['dt_s']
    if not 0 < dt <= budget['max_dt_s']:
        raise ValueError('adaptive first-step dt mismatch')
    area = a['leaf_area_m2']
    equations = []
    for rk in (1, 2):
        source = packet[f'rk{rk}_bed_source']
        if _i91_np.any(source[:, 0] != 0) or _i91_np.any(packet[f'rk{rk}_boundary_flux'][a['boundary_kind'] == 0, 0] != 0):
            raise ValueError('adaptive sampled closed mass or bed source mismatch')
        rhs = source.copy()
        _i91_np.add.at(rhs, a['face_left'], -packet[f'rk{rk}_internal_flux'] / area[a['face_left'], None])
        _i91_np.add.at(rhs, a['face_right'], packet[f'rk{rk}_internal_flux'] / area[a['face_right'], None])
        _i91_np.add.at(rhs, a['boundary_cell'], -packet[f'rk{rk}_boundary_flux'] / area[a['boundary_cell'], None])
        rhs[:, 0] += packet['forcing_m3_s'] / area
        equations.append(rhs)
    near(packet['state_predictor'], packet['state_before'] + dt * equations[0], 'saved predictor equation')
    undamped = 0.5 * packet['state_before'] + 0.5 * (packet['state_predictor'] + dt * equations[1])
    near(packet['state_after'][:, 0], undamped[:, 0], 'saved RK mass equation')
    stage = storage_stage(undamped[:, 0], geometry)
    factor = _i91_np.zeros(n)
    for cell, count in enumerate(a['subcell_count']):
        offset = a['subcell_offset'][cell]
        h = _i91_np.maximum(stage[cell] - a['sorted_subcell_bed_relative_m'][offset:offset + count], 0)
        factor[cell] = _i91_np.sum(h[h > 0] ** (-1 / 3)) / count
    near(packet['manning_inverse_depth_third_mean'], factor, 'saved canonical Manning integral')
    squared = undamped[:, 0] ** 2
    denominator = squared + dt * budget['gravity_m_s2'] * budget['roughness_s_m_third'] ** 2 * _i91_np.hypot(undamped[:, 1], undamped[:, 2]) * factor
    damping = _i91_np.divide(squared, denominator, out=_i91_np.zeros_like(squared), where=denominator > 0)
    expected = undamped[:, 1:] * damping[:, None]
    near(packet['state_after'][:, 1:], expected, 'saved canonical Manning equation')
    near(packet['manning_momentum_change'], expected - undamped[:, 1:], 'saved Manning change')
SCHEMA = 'surface-adaptive-canonical-water-fan-v1'
EXTRA = {'cell_depth_m', 'corner_depth_m', 'center_depth_m', 'water_vertices_xyz_m', 'water_triangles', 'wet_cell_ids', 'cell_volume_m3'}
SEMANTICS = 'conservative canonical inventory visualization; no hydraulic order claim'

def snapshot_record(bundle):
    from terrain_pipeline.common_infra import identity as _i95_identity
    from terrain_pipeline.fine_subgrid import FLAGS as _x42_FLAGS
    if bundle['identity_sha256'] != _i95_identity(bundle['arrays'], bundle['metadata']) or bundle['metadata'].get('schema') != 'surface-adaptive-canonical-snapshot-v1' or any((bundle['metadata'].get(flag) is not False for flag in _x42_FLAGS)):
        raise ValueError('adaptive water requires an authenticated saved snapshot')
    return dict(bundle['metadata'], **bundle['arrays'])

def bind_sources(bed, snapshot_bundle, geometry):
    from terrain_pipeline.fine_subgrid import validate_fine_geometry as _x47_validate_fine_geometry
    _x47_validate_fine_geometry(bed)
    validate_geometry(geometry)
    snapshot = snapshot_record(snapshot_bundle)
    validate_snapshot(snapshot, geometry)
    if bed['metadata']['spacing_m'] != 1.0 or not _i95_np.array_equal(bed['arrays']['H2_m'], geometry['arrays']['canonical_bed_m']) or bed['metadata']['origin_m_xz'] != geometry['metadata']['origin_m_xz']:
        raise ValueError('adaptive water canonical bed/origin binding mismatch')
    return snapshot

def build_adaptive_water_frame(bed, snapshot_bundle, geometry, *, state_index):
    from terrain_pipeline.fine_subgrid import COORDINATES as _x41_COORDINATES
    from terrain_pipeline.fine_subgrid import FLAGS as _x42_FLAGS
    from terrain_pipeline.fine_subgrid import _freeze as _x44_freeze
    from terrain_pipeline.fine_subgrid import _water_arrays as _x46_water_arrays
    snapshot = bind_sources(bed, snapshot_bundle, geometry)
    if type(state_index) is not int or state_index < 0:
        raise ValueError('adaptive water saved state index invalid')
    arrays, diagnostics = _x46_water_arrays(bed, snapshot['canonical_depth_m'])
    metadata = dict(schema=SCHEMA, algorithm='saved-adaptive-canonical-inventory-shared-fan-v1', coordinates=_x41_COORDINATES, representation=SEMANTICS, bed_identity=bed['identity_sha256'], geometry_metadata=bed['metadata'], adaptive_snapshot_identity=snapshot_bundle['identity_sha256'], adaptive_geometry_identity=geometry['identity_sha256'], state_index=state_index, time_s=float(snapshot['time_s']), canonical_spacing_m=1.0, leaf_counts=geometry['metadata']['leaf_counts'], leaf_count=geometry['metadata']['leaf_count'], water_generated=False, solver_advanced=False, continuous_shared_surface=True, limitation='centre depth may reach 3x canonical mean; shared fan stage differs from hydraulic leaf stage', **diagnostics, **{flag: False for flag in _x42_FLAGS})
    frame = _x44_freeze(arrays, metadata)
    validate_bound_adaptive_water_frame(frame, bed, snapshot_bundle, geometry)
    return frame

def validate_adaptive_water_frame(frame):
    from terrain_pipeline.common_infra import identity as _i95_identity
    from terrain_pipeline.fine_subgrid import COORDINATES as _x41_COORDINATES
    from terrain_pipeline.fine_subgrid import FLAGS as _x42_FLAGS
    from terrain_pipeline.fine_subgrid import _equal as _x43_equal
    from terrain_pipeline.fine_subgrid import _sha as _x45_sha
    from terrain_pipeline.fine_subgrid import _water_arrays as _x46_water_arrays
    from terrain_pipeline.fine_subgrid import validate_fine_geometry as _x47_validate_fine_geometry
    arrays, meta = (frame['arrays'], frame['metadata'])
    if frame['identity_sha256'] != _i95_identity(arrays, meta) or meta.get('schema') != SCHEMA or meta.get('algorithm') != 'saved-adaptive-canonical-inventory-shared-fan-v1' or (meta.get('representation') != SEMANTICS) or (meta.get('coordinates') != _x41_COORDINATES) or (meta.get('water_generated') is not False) or (meta.get('solver_advanced') is not False) or (meta.get('continuous_shared_surface') is not True) or (meta.get('canonical_spacing_m') != 1.0) or any((meta.get(flag) is not False for flag in _x42_FLAGS)):
        raise ValueError('adaptive water schema/identity/semantics mismatch')
    for name in ('bed_identity', 'adaptive_snapshot_identity', 'adaptive_geometry_identity'):
        _x45_sha(meta[name])
    if type(meta['state_index']) is not int or meta['state_index'] < 0 or (not _i95_math.isfinite(meta['time_s'])):
        raise ValueError('adaptive water saved time/index mismatch')
    bed = dict(arrays={name: value for name, value in arrays.items() if name not in EXTRA}, metadata=meta['geometry_metadata'], identity_sha256=meta['bed_identity'])
    _x47_validate_fine_geometry(bed)
    expected, diagnostics = _x46_water_arrays(bed, arrays['cell_depth_m'])
    _x43_equal(arrays, expected)
    if any((meta.get(name) != value for name, value in diagnostics.items())):
        raise ValueError('adaptive water conservative fan diagnostics mismatch')
    return True

def validate_bound_adaptive_water_frame(frame, bed, snapshot_bundle, geometry):
    validate_adaptive_water_frame(frame)
    snapshot = bind_sources(bed, snapshot_bundle, geometry)
    meta = frame['metadata']
    if meta['bed_identity'] != bed['identity_sha256'] or meta['adaptive_snapshot_identity'] != snapshot_bundle['identity_sha256'] or meta['adaptive_geometry_identity'] != geometry['identity_sha256'] or (meta['time_s'] != snapshot['time_s']) or (meta['leaf_counts'] != geometry['metadata']['leaf_counts']) or (meta['leaf_count'] != geometry['metadata']['leaf_count']) or (not _i95_np.array_equal(frame['arrays']['cell_depth_m'], snapshot['canonical_depth_m'])):
        raise ValueError('adaptive water original snapshot/leaf inventory binding mismatch')
    return True

def save_adaptive_water_frame(path, frame):
    from terrain_pipeline.common_infra import save_bundle as _i95_save_bundle
    _i95_save_bundle(path, frame, validator=validate_adaptive_water_frame)

def load_adaptive_water_frame(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _i95_load_bundle
    frame = _i95_load_bundle(path, expected_sha256=expected_sha256, max_bytes=MAX_BYTES, validator=validate_adaptive_water_frame)
    if frame['identity_sha256'] != expected_identity:
        raise ValueError('adaptive water external identity mismatch')
    return frame

def load_consumer_adaptive_frame(context, *, scenario, frame_index):
    """Load and bind a relocated consumer frame using only allowlisted payloads."""
    from terrain_pipeline.common_infra import load_bundle as _i95_load_bundle
    from terrain_pipeline.fine_subgrid import FLAGS as _x42_FLAGS
    manifest = context['manifest']
    if manifest.get('backend') != 'adaptive-saved-canonical-fan':
        raise ValueError('adaptive frame requires an adaptive consumer context')
    frames = manifest['scenarios'][scenario]['frames']
    if type(frame_index) is not int or not 0 <= frame_index < len(frames):
        raise ValueError('adaptive consumer frame index invalid')
    items = {item['path']: item for item in manifest['artifacts']}

    def load(name):
        item = items[name]
        bundle = _i95_load_bundle(context['allowlist'][name], expected_sha256=item['sha256'], max_bytes=MAX_BYTES, validator=lambda value: True)
        if bundle['identity_sha256'] != item['identity_sha256']:
            raise ValueError('adaptive consumer external payload identity mismatch')
        return bundle
    entry = frames[frame_index]
    bed = load(manifest['scenarios'][scenario]['geometry'])
    frame, snapshot, saved_geometry = (load(entry[name]) for name in ('artifact', 'snapshot', 'adaptive_geometry'))
    if saved_geometry['metadata'].get('schema') != 'surface-adaptive-geometry-v1' or any((saved_geometry['metadata'].get(flag) is not False for flag in _x42_FLAGS)):
        raise ValueError('adaptive consumer raw geometry schema/flags mismatch')
    geometry = dict(arrays=saved_geometry['arrays'], metadata=saved_geometry['metadata']['raw_geometry_metadata'], identity_sha256=saved_geometry['metadata']['raw_geometry_identity'])
    validate_bound_adaptive_water_frame(frame, bed, snapshot, geometry)
    if frame['metadata']['state_index'] != frame_index or frame['metadata']['time_s'] != entry['time_s']:
        raise ValueError('adaptive consumer manifest original frame/time binding mismatch')
    return dict(frame=frame, bed=bed, snapshot=snapshot, geometry=geometry, solver_advanced=False)
