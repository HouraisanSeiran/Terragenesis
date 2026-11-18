"""Consolidated fine_subgrid implementations; numeric expressions preserved."""
from __future__ import annotations
import math as _i114_math
import re as _i114_re
import numpy as _i114_np
from dataclasses import asdict as _i115_asdict
import math as _i115_math
import time as _i115_time
import numpy as _i115_np
import json as _i116_json
import math as _i116_math
from pathlib import Path as _i116_Path
import numpy as _i116_np
import math as _i117_math
import re as _i117_re
import numpy as _i117_np
CATEGORY = 'B'
MAX_NATIVE_CELLS = 250000
MAX_FINE_CELLS = 62500
MAX_BYTES = 256 * 1024 ** 2
FLAGS = ('hydraulic_ready', 'natural_outlet_verified', 'publishable')
GEOMETRY_SCHEMA = 'single-domain-fine-geometry-v1'
WATER_SCHEMA = 'single-domain-fine-water-fan-v1'
COORDINATES = 'physical metres [x,y,z]; x east, y up, z south; raster [z,x]'
GEOMETRY_SEMANTICS = 'native bilinear corners minus protected 8m-wide 1m-deep max-union cosine capsules; shared corner-centre fans'
WATER_SEMANTICS = 'corner depth=min adjacent cell depth; centre depth=3*cell depth-0.5*corner depth sum; exact per-cell fan volume'
SCOPE_SEMANTICS = dict(protection_semantics='any native bilinear stencil protection forbids cut; preserves original corner heights', boundary_semantics='explicit finite engineering window; external receiver crossings retained; no inferred upstream completion', fine_detail_semantics='bilinear source landform plus declared artificial channels; no new Terrain Diffusion detail', fv_bed_semantics='canonical 1m area mean; fan centre=3*FV bed-0.5*corner sum, so exact fan area mean equals FV bed')

def _sha(value):
    if not isinstance(value, str) or _i114_re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('fine source SHA/identity invalid')

def _limits(window, spacing, native_shape):
    if not isinstance(window, (list, tuple)) or len(window) != 4 or any((type(value) is not int for value in window)) or (type(spacing) not in (int, float)) or (spacing not in (1.0, 2.0, 4.0)):
        raise ValueError('explicit integer native window and declared 1/2/4m spacing required')
    x0, x1, z0, z1 = window
    if not (0 <= x0 < x1 < native_shape[1] and 0 <= z0 < z1 < native_shape[0]):
        raise ValueError('fine window leaves native sample extent')
    lengths = ((z1 - z0) * 30.0, (x1 - x0) * 30.0)
    if any((length / spacing % 1 for length in lengths)):
        raise ValueError('fine window must contain complete cells')
    shape = tuple((int(length / spacing) for length in lengths))
    if _i114_math.prod(shape) > MAX_FINE_CELLS:
        raise ValueError('fine cell budget exceeded before allocation')
    return shape

def coarsen_cell_field(fine_field, *, factor):
    """Transfer a cell-centred extensive/intensive field by exact area mean."""
    if not isinstance(fine_field, _i114_np.ndarray) or fine_field.dtype != _i114_np.float64 or fine_field.ndim != 2:
        raise ValueError('fine cell field must be finite float64 2D')
    if type(factor) is not int or factor not in (2, 4) or any((size % factor for size in fine_field.shape)):
        raise ValueError('coarsening factor must evenly divide both fine axes')
    if not _i114_np.isfinite(fine_field).all():
        raise ValueError('fine cell field nonfinite')
    rows, columns = fine_field.shape
    return fine_field.reshape(rows // factor, factor, columns // factor, factor).mean(axis=(1, 3))

def _bilinear(height, columns, rows):
    left, top = (_i114_np.floor(columns).astype(_i114_np.int64), _i114_np.floor(rows).astype(_i114_np.int64))
    right, bottom = (_i114_np.minimum(left + 1, height.shape[1] - 1), _i114_np.minimum(top + 1, height.shape[0] - 1))
    u, v = (columns - left, rows - top)
    return (1 - v) * ((1 - u) * height[top, left] + u * height[top, right]) + v * ((1 - u) * height[bottom, left] + u * height[bottom, right])

def _stencil_mask(mask, columns, rows):
    left, top = (_i114_np.floor(columns).astype(_i114_np.int64), _i114_np.floor(rows).astype(_i114_np.int64))
    right, bottom = (_i114_np.minimum(left + 1, mask.shape[1] - 1), _i114_np.minimum(top + 1, mask.shape[0] - 1))
    return mask[top, left] | mask[top, right] | mask[bottom, left] | mask[bottom, right]

def _fan(corner, spacing, origin):
    rows, columns = (corner.shape[0] - 1, corner.shape[1] - 1)
    x, z = _i114_np.meshgrid(origin[0] + _i114_np.arange(columns + 1) * spacing, origin[1] + _i114_np.arange(rows + 1) * spacing)
    centre = (corner[:-1, :-1] + corner[1:, :-1] + corner[1:, 1:] + corner[:-1, 1:]) / 4.0
    corner_xyz = _i114_np.column_stack((x.ravel(), corner.ravel(), z.ravel()))
    centre_xyz = _i114_np.column_stack(((x[:-1, :-1] + spacing / 2).ravel(), centre.ravel(), (z[:-1, :-1] + spacing / 2).ravel()))
    grid = _i114_np.arange(corner.size, dtype=_i114_np.int64).reshape(corner.shape)
    nw = grid[:-1, :-1].ravel()
    corners = _i114_np.column_stack((nw, nw + columns + 1, nw + columns + 2, nw + 1))
    centres = _i114_np.arange(rows * columns, dtype=_i114_np.int64) + corner.size
    triangles = _i114_np.empty((rows * columns, 4, 3), _i114_np.int64)
    triangles[:, :, 0] = corners
    triangles[:, :, 1] = corners[:, [1, 2, 3, 0]]
    triangles[:, :, 2] = centres[:, None]
    return (centre, _i114_np.concatenate((corner_xyz, centre_xyz)), triangles.reshape(-1, 3), corners, centres)

def _capsule_cut(world_x, world_z, selected, origin, native_shape):
    cut = _i114_np.zeros_like(world_x, dtype=_i114_np.float64)
    for first, second in selected:
        start = _i114_np.array([origin[0] + first % native_shape[1] * 30.0, origin[1] + first // native_shape[1] * 30.0])
        end = _i114_np.array([origin[0] + second % native_shape[1] * 30.0, origin[1] + second // native_shape[1] * 30.0])
        delta = end - start
        fraction = _i114_np.clip(((world_x - start[0]) * delta[0] + (world_z - start[1]) * delta[1]) / 900.0, 0.0, 1.0)
        distance = _i114_np.hypot(world_x - start[0] - fraction * delta[0], world_z - start[1] - fraction * delta[1])
        capsule = _i114_np.where(distance < 4.0, 0.5 * (1 + _i114_np.cos(_i114_np.pi * _i114_np.minimum(distance / 4.0, 1.0))), 0.0)
        _i114_np.maximum(cut, capsule, out=cut)
    return cut

def _native_topology(height, valid, receiver):
    if height.dtype != _i114_np.float64 or height.ndim != 2 or height.size > MAX_NATIVE_CELLS or (not _i114_np.isfinite(height).all()) or (valid.dtype != bool) or (valid.shape != height.shape) or (receiver.dtype != _i114_np.int64) or (receiver.shape != (height.size,)) or _i114_np.any(receiver < -1) or _i114_np.any(receiver >= height.size) or _i114_np.any(receiver[~valid.ravel()] != -1):
        raise ValueError('native fine source arrays invalid')
    source = _i114_np.flatnonzero(receiver >= 0)
    target = receiver[source]
    columns = height.shape[1]
    if not valid.ravel()[source].all() or not valid.ravel()[target].all() or _i114_np.any(abs(source // columns - target // columns) + abs(source % columns - target % columns) != 1):
        raise ValueError('native source requires valid D4 receivers')
    done = _i114_np.zeros(height.size, bool)
    for start in _i114_np.flatnonzero(valid):
        cell, path = (int(start), set())
        while cell >= 0 and (not done[cell]):
            if cell in path:
                raise ValueError('native receiver cycle')
            path.add(cell)
            cell = int(receiver[cell])
        done[list(path)] = True
    return (source, target)

def _geometry_arrays(native, metadata, selected):
    height, valid, protected, receiver = (native[name] for name in ('native_height_m', 'native_valid_mask', 'native_protected_mask', 'native_receiver'))
    source, target = _native_topology(height, valid, receiver)
    if protected.dtype != bool or protected.shape != height.shape:
        raise ValueError('native protection shape/type invalid')
    window, spacing = (metadata['native_window'], metadata['spacing_m'])
    rows, columns = _limits(window, spacing, height.shape)
    x0, x1, z0, z1 = window
    origin = metadata['native_origin_m_xz']
    if metadata['native_spacing_m'] != 30.0 or len(origin) != 2 or any((type(value) not in (int, float) or not _i114_math.isfinite(value) for value in origin)):
        raise ValueError('fixed native metre coordinates required')
    corner_origin = [origin[0] + x0 * 30.0, origin[1] + z0 * 30.0]
    if metadata['origin_m_xz'] != corner_origin or metadata['corner_origin_m_xz'] != corner_origin or metadata['cell_center_origin_m_xz'] != [value + spacing / 2 for value in corner_origin] or (metadata['grid_shape'] != [rows, columns]):
        raise ValueError('fine coordinate/shape binding invalid')
    local_mask = _i114_np.zeros(height.size, bool)
    coarse_x, coarse_z = _i114_np.meshgrid(_i114_np.arange(x0, x1 + 1), _i114_np.arange(z0, z1 + 1))
    node_ids = (coarse_z * height.shape[1] + coarse_x).ravel().astype(_i114_np.int64)
    if not valid.ravel()[node_ids].all():
        raise ValueError('entire finite window must have known native support')
    local_mask[node_ids] = True
    internal = local_mask[source] & local_mask[target]
    all_edges = _i114_np.column_stack((source[internal], target[internal])).astype(_i114_np.int64)
    edge_set = {tuple(pair) for pair in all_edges}
    if selected.dtype != _i114_np.int64 or selected.ndim != 2 or selected.shape[1] != 2 or (len(selected) > len(all_edges)) or (len({tuple(pair) for pair in selected}) != len(selected)) or any((tuple(pair) not in edge_set for pair in selected)):
        raise ValueError('selected edge cells must be unique internal native receiver links')
    if len(selected) and (not _i114_np.array_equal(selected, selected[_i114_np.lexsort((selected[:, 1], selected[:, 0]))])):
        raise ValueError('selected edge cells must be sorted')
    lattice_x, lattice_z = _i114_np.meshgrid(_i114_np.arange(columns + 1), _i114_np.arange(rows + 1))
    native_x, native_z = (x0 + lattice_x * spacing / 30.0, z0 + lattice_z * spacing / 30.0)
    if _stencil_mask(~valid, native_x, native_z).any():
        raise ValueError('unknown native bilinear stencil in finite window')
    original = _bilinear(height, native_x, native_z)
    protection = _stencil_mask(protected, native_x, native_z)
    world_x, world_z = (corner_origin[0] + lattice_x * spacing, corner_origin[1] + lattice_z * spacing)
    cut = _capsule_cut(world_x, world_z, selected, origin, height.shape)
    cut[protection] = 0.0
    channel = cut > 0
    bank = _i114_np.zeros_like(channel)
    bank[:, :-1] |= channel[:, 1:]
    bank[:, 1:] |= channel[:, :-1]
    bank[:-1, :] |= channel[1:, :]
    bank[1:, :] |= channel[:-1, :]
    bank &= ~channel
    bed_corner = original - cut
    bed_centre, vertices, triangles, corners, centres = _fan(bed_corner, spacing, corner_origin)
    fine_x, fine_z = _i114_np.meshgrid(corner_origin[0] + _i114_np.arange(columns * int(spacing)) + 0.5, corner_origin[1] + _i114_np.arange(rows * int(spacing)) + 0.5)
    reference_cut = _capsule_cut(fine_x, fine_z, selected, origin, height.shape)
    reference_source_x, reference_source_z = _i114_np.meshgrid(x0 + (_i114_np.arange(columns * int(spacing)) + 0.5) / 30.0, z0 + (_i114_np.arange(rows * int(spacing)) + 0.5) / 30.0)
    reference_source = _bilinear(height, reference_source_x, reference_source_z)
    reference_source = _i114_np.asarray(reference_source)
    reference_protection = _stencil_mask(protected, reference_source_x, reference_source_z)
    reference_cut[reference_protection] = 0.0
    canonical_bed_center = reference_source - reference_cut
    if spacing == 1.0:
        integrated_bed = canonical_bed_center
    else:
        factor = int(spacing)
        integrated_bed = canonical_bed_center.reshape(rows, factor, columns, factor).mean(axis=(1, 3))
    bed_centre = integrated_bed
    corner_sum = bed_corner[:-1, :-1] + bed_corner[1:, :-1] + bed_corner[1:, 1:] + bed_corner[:-1, 1:]
    fan_centre = 3 * bed_centre - 0.5 * corner_sum
    vertices[centres, 1] = fan_centre.ravel()
    node_x, node_z = ((node_ids % height.shape[1] - x0) * 30.0 / spacing, (node_ids // height.shape[1] - z0) * 30.0 / spacing)
    node_bed = _bilinear(bed_corner, node_x, node_z)
    node_left, node_top = (_i114_np.floor(node_x).astype(_i114_np.int64), _i114_np.floor(node_z).astype(_i114_np.int64))
    at_fan_centre = (node_x - node_left == 0.5) & (node_z - node_top == 0.5)
    node_bed[at_fan_centre] = fan_centre[node_top[at_fan_centre], node_left[at_fan_centre]]
    node_xyz = _i114_np.column_stack((origin[0] + node_ids % height.shape[1] * 30.0, node_bed, origin[1] + node_ids // height.shape[1] * 30.0))
    outbound = _i114_np.column_stack((source[local_mask[source] & ~local_mask[target]], target[local_mask[source] & ~local_mask[target]])).astype(_i114_np.int64)
    inbound = _i114_np.column_stack((source[~local_mask[source] & local_mask[target]], target[~local_mask[source] & local_mask[target]])).astype(_i114_np.int64)
    native_target = receiver[node_ids]
    return dict(native, selected_edge_cell_ids=selected.copy(), node_cell_ids=node_ids, node_receiver_cell_ids=native_target.copy(), node_xyz_m=node_xyz, edge_node_indices=_i114_np.searchsorted(node_ids, selected).astype(_i114_np.int64), internal_sink_mask=native_target < 0, outgoing_boundary_edge_cell_ids=outbound, incoming_boundary_edge_cell_ids=inbound, all_internal_edge_cell_ids=all_edges, native_bilinear_corner_m=original, canonical_bed_center_m=canonical_bed_center, canonical_cut_center_m=reference_cut, canonical_protected_center_mask=reference_protection, protected_corner_mask=protection, artificial_channel_corner_mask=channel, artificial_bank_corner_mask=bank, cut_corner_m=cut, bed_corner_m=bed_corner, bed_center_m=bed_centre, H2_m=bed_centre.copy(), bed_fan_center_m=fan_centre, bed_vertices_xyz_m=vertices, bed_triangles=triangles, cell_corner_vertex_ids=corners, cell_center_vertex_ids=centres, cell_fan_vertex_ids=_i114_np.column_stack((corners, centres)))

def _freeze(arrays, metadata):
    from terrain_pipeline.common_infra import identity as _i114_identity
    from terrain_pipeline.common_infra import readonly as _i114_readonly
    if sum((value.nbytes for value in arrays.values())) > MAX_BYTES:
        raise ValueError('fine artifact byte budget exceeded')
    return dict(arrays={name: _i114_readonly(value) for name, value in arrays.items()}, metadata=metadata, identity_sha256=_i114_identity(arrays, metadata))

def build_fine_geometry(hierarchy, *, native_window, source_hierarchy_sha256, spacing_m=1.0, selected_edge_cell_ids=None, width_m=8.0, incision_m=1.0):
    from terrain_pipeline.basin_topology import validate_basin_hierarchy as _i114_validate_basin_hierarchy
    _i114_validate_basin_hierarchy(hierarchy)
    _sha(source_hierarchy_sha256)
    if width_m != 8.0 or incision_m != 1.0 or hierarchy['metadata']['spacing_m'] != 30.0:
        raise ValueError('declared native 30m / width8m / incision1m recipe required')
    source = hierarchy['arrays']
    rows, columns = _limits(native_window, spacing_m, source['height_m'].shape)
    x0, _, z0, _ = native_window
    native_origin = list(hierarchy['metadata']['origin_m_xz'])
    corner_origin = [native_origin[0] + x0 * 30.0, native_origin[1] + z0 * 30.0]
    metadata = dict(schema=GEOMETRY_SCHEMA, algorithm='protected-native-canonical-integral-fan-v2', coordinates=COORDINATES, representation=GEOMETRY_SEMANTICS, hierarchy_identity=hierarchy['identity_sha256'], source_hierarchy_sha256=source_hierarchy_sha256, source_identity=hierarchy['metadata']['source_identity_sha256'], native_window=list(native_window), native_spacing_m=30.0, native_origin_m_xz=native_origin, grid_shape=[rows, columns], spacing_m=float(spacing_m), origin_m_xz=corner_origin, corner_origin_m_xz=corner_origin, cell_center_origin_m_xz=[value + spacing_m / 2 for value in corner_origin], width_m=8.0, incision_m=1.0, water_generated=False, artificial_channels=True, natural_banks_verified=False, full_native_domain_covered=False, **SCOPE_SEMANTICS, **{name: False for name in FLAGS})
    native = dict(native_height_m=source['height_m'].copy(), native_valid_mask=source['valid_mask'].copy(), native_protected_mask=source['protected_mask'].copy(), native_receiver=source['receiver'].copy())
    if selected_edge_cell_ids is None:
        ids = _i114_np.arange(source['height_m'].size)
        target = source['receiver']
        mask = (ids % source['height_m'].shape[1] >= native_window[0]) & (ids % source['height_m'].shape[1] <= native_window[1])
        mask &= (ids // source['height_m'].shape[1] >= native_window[2]) & (ids // source['height_m'].shape[1] <= native_window[3])
        internal = (target >= 0) & mask
        internal[internal] &= mask[target[internal]]
        selected = _i114_np.column_stack((ids[internal], target[internal])).astype(_i114_np.int64)
    else:
        selected = _i114_np.asarray(selected_edge_cell_ids)
        if selected.dtype != _i114_np.int64:
            raise ValueError('selected native edges require int64')
        selected = selected.reshape(-1, 2)
    arrays = _geometry_arrays(native, metadata, selected)
    metadata['cut_volume_m3'] = float(_i114_np.sum(arrays['canonical_cut_center_m'], dtype=_i114_np.float64))
    metadata['maximum_cut_m'] = float(arrays['cut_corner_m'].max(initial=0))
    corners = arrays['bed_corner_m']
    corner_stack = _i114_np.stack((corners[:-1, :-1], corners[1:, :-1], corners[1:, 1:], corners[:-1, 1:]))
    fan = arrays['bed_fan_center_m']
    cut = arrays['cut_corner_m']
    corner_cut_mean = (cut[:-1, :-1] + cut[1:, :-1] + cut[1:, 1:] + cut[:-1, 1:]) / 4
    metadata.update(hydraulic_integral_cut_volume_m3=metadata['cut_volume_m3'], corner_trapezoid_cut_volume_m3=float(corner_cut_mean.sum() * spacing_m ** 2), fan_center_minimum_elevation_m=float(fan.min()), fan_center_maximum_elevation_m=float(fan.max()), fan_center_maximum_corner_undershoot_m=float(_i114_np.maximum(corner_stack.min(axis=0) - fan, 0.0).max(initial=0)), fan_center_maximum_corner_overshoot_m=float(_i114_np.maximum(fan - corner_stack.max(axis=0), 0.0).max(initial=0)), fan_center_maximum_corner_mean_correction_m=float(abs(fan - corner_stack.mean(axis=0)).max(initial=0)), hydraulic_cut_semantics='integral of canonical protected 1m center incision; cell mean and fan triangle integral agree', fan_shape_limitation='integral correction may create center excursions beyond adjacent corner range')
    result = _freeze(arrays, metadata)
    validate_fine_geometry(result)
    return result

def _check(result, schema):
    from terrain_pipeline.common_infra import identity as _i114_identity
    arrays, metadata = (result['arrays'], result['metadata'])
    if metadata.get('schema') != schema or metadata.get('coordinates') != COORDINATES or any((metadata.get(name) is not False for name in FLAGS)) or (result['identity_sha256'] != _i114_identity(arrays, metadata)):
        raise ValueError('fine schema/coordinates/certification/identity mismatch')
    if sum((value.nbytes for value in arrays.values())) > MAX_BYTES or any((not _i114_np.isfinite(value).all() for value in arrays.values())):
        raise ValueError('fine nonfinite/byte budget invalid')
    return (arrays, metadata)

def _equal(actual, expected):
    if set(actual) != set(expected):
        raise ValueError('fine array fields mismatch')
    for name, value in expected.items():
        if actual[name].dtype != value.dtype or not _i114_np.array_equal(actual[name], value):
            raise ValueError('fine source/derivation mismatch: ' + name)

def validate_fine_geometry(result):
    arrays, metadata = _check(result, GEOMETRY_SCHEMA)
    if metadata.get('algorithm') != 'protected-native-canonical-integral-fan-v2' or metadata.get('representation') != GEOMETRY_SEMANTICS or metadata.get('width_m') != 8.0 or (metadata.get('incision_m') != 1.0) or (metadata.get('natural_banks_verified') is not False) or (metadata.get('water_generated') is not False) or (metadata.get('artificial_channels') is not True) or (metadata.get('full_native_domain_covered') is not False) or any((metadata.get(name) != value for name, value in SCOPE_SEMANTICS.items())):
        raise ValueError('fine artificial recipe/scope invalid')
    for name in ('hierarchy_identity', 'source_hierarchy_sha256', 'source_identity'):
        _sha(metadata[name])
    height, valid, protected, receiver = (arrays[name] for name in ('native_height_m', 'native_valid_mask', 'native_protected_mask', 'native_receiver'))
    sources, targets = _native_topology(height, valid, receiver)
    rows, columns = _limits(metadata['native_window'], metadata['spacing_m'], height.shape)
    spacing = metadata['spacing_m']
    corner = arrays['bed_corner_m']
    canonical = arrays['canonical_bed_center_m']
    expected_shapes = dict(native_bilinear_corner_m=(rows + 1, columns + 1), protected_corner_mask=(rows + 1, columns + 1), cut_corner_m=(rows + 1, columns + 1), bed_corner_m=(rows + 1, columns + 1), bed_center_m=(rows, columns), H2_m=(rows, columns), bed_fan_center_m=(rows, columns), canonical_bed_center_m=(rows * int(spacing), columns * int(spacing)), canonical_cut_center_m=(rows * int(spacing), columns * int(spacing)), canonical_protected_center_mask=(rows * int(spacing), columns * int(spacing)))
    if any((arrays[name].shape != shape for name, shape in expected_shapes.items())):
        raise ValueError('fine saved lattice field shape mismatch')
    if _i114_np.any(arrays['cut_corner_m'] < 0) or _i114_np.any(arrays['cut_corner_m'] > 1) or _i114_np.any(arrays['canonical_cut_center_m'] < 0) or _i114_np.any(arrays['canonical_cut_center_m'] > 1) or _i114_np.any(arrays['cut_corner_m'][arrays['protected_corner_mask']] != 0) or _i114_np.any(arrays['canonical_cut_center_m'][arrays['canonical_protected_center_mask']] != 0) or (not _i114_np.array_equal(corner, arrays['native_bilinear_corner_m'] - arrays['cut_corner_m'])):
        raise ValueError('fine saved protection/no-fill relation invalid')
    expected_bed = canonical if spacing == 1.0 else coarsen_cell_field(canonical, factor=int(spacing))
    if not _i114_np.array_equal(arrays['H2_m'], expected_bed) or not _i114_np.array_equal(arrays['bed_center_m'], expected_bed):
        raise ValueError('fine saved canonical area restriction invalid')
    corner_sum = corner[:-1, :-1] + corner[1:, :-1] + corner[1:, 1:] + corner[:-1, 1:]
    if not _i114_np.array_equal(arrays['bed_fan_center_m'], 3 * expected_bed - 0.5 * corner_sum):
        raise ValueError('fine saved triangle fan area mean invalid')
    _, vertices, triangles, corners, centres = _fan(corner, spacing, metadata['origin_m_xz'])
    vertices[centres, 1] = arrays['bed_fan_center_m'].ravel()
    for name, expected in (('bed_vertices_xyz_m', vertices), ('bed_triangles', triangles), ('cell_corner_vertex_ids', corners), ('cell_center_vertex_ids', centres), ('cell_fan_vertex_ids', _i114_np.column_stack((corners, centres)))):
        if not _i114_np.array_equal(arrays[name], expected):
            raise ValueError('fine saved shared lattice/fan topology mismatch: ' + name)
    x0, x1, z0, z1 = metadata['native_window']
    local = _i114_np.zeros(height.size, bool)
    node_x, node_z = _i114_np.meshgrid(_i114_np.arange(x0, x1 + 1), _i114_np.arange(z0, z1 + 1))
    node_ids = (node_z * height.shape[1] + node_x).ravel().astype(_i114_np.int64)
    local[node_ids] = True
    expected_all = _i114_np.column_stack((sources[local[sources] & local[targets]], targets[local[sources] & local[targets]]))
    selected = arrays['selected_edge_cell_ids']
    if selected.dtype != _i114_np.int64 or selected.shape != (len(selected), 2) or len({tuple(pair) for pair in selected}) != len(selected) or any((tuple(pair) not in {tuple(pair) for pair in expected_all} for pair in selected)):
        raise ValueError('fine saved selected native topology invalid')
    expected_out = _i114_np.column_stack((sources[local[sources] & ~local[targets]], targets[local[sources] & ~local[targets]]))
    expected_in = _i114_np.column_stack((sources[~local[sources] & local[targets]], targets[~local[sources] & local[targets]]))
    for name, expected in (('node_cell_ids', node_ids), ('node_receiver_cell_ids', receiver[node_ids]), ('edge_node_indices', _i114_np.searchsorted(node_ids, selected)), ('internal_sink_mask', receiver[node_ids] < 0), ('all_internal_edge_cell_ids', expected_all), ('outgoing_boundary_edge_cell_ids', expected_out), ('incoming_boundary_edge_cell_ids', expected_in)):
        if not _i114_np.array_equal(arrays[name], expected):
            raise ValueError('fine saved receiver/boundary relation invalid')
    fx, fz = ((node_ids % height.shape[1] - x0) * 30.0 / spacing, (node_ids // height.shape[1] - z0) * 30.0 / spacing)
    node_bed = _bilinear(corner, fx, fz)
    left, top = (_i114_np.floor(fx).astype(_i114_np.int64), _i114_np.floor(fz).astype(_i114_np.int64))
    at_centre = (fx - left == 0.5) & (fz - top == 0.5)
    node_bed[at_centre] = arrays['bed_fan_center_m'][top[at_centre], left[at_centre]]
    expected_xyz = _i114_np.column_stack((metadata['origin_m_xz'][0] + fx * spacing, node_bed, metadata['origin_m_xz'][1] + fz * spacing))
    if not _i114_np.array_equal(arrays['node_xyz_m'], expected_xyz):
        raise ValueError('fine saved shared junction XYZ mismatch')
    cut = arrays['cut_corner_m']
    if metadata['cut_volume_m3'] != float(_i114_np.sum(arrays['canonical_cut_center_m'], dtype=_i114_np.float64)) or metadata['maximum_cut_m'] != float(cut.max(initial=0)):
        raise ValueError('fine cut volume audit invalid')
    return True

def _water_arrays(geometry, depth):
    source, meta = (geometry['arrays'], geometry['metadata'])
    shape = source['H2_m'].shape
    if depth.dtype != _i114_np.float64 or depth.shape != shape or (not _i114_np.isfinite(depth).all()) or _i114_np.any(depth < 0):
        raise ValueError('new-bed fine cell depth invalid')
    corner_depth = _i114_np.full((shape[0] + 1, shape[1] + 1), _i114_np.inf)
    for selection in (_i114_np.s_[:-1, :-1], _i114_np.s_[1:, :-1], _i114_np.s_[1:, 1:], _i114_np.s_[:-1, 1:]):
        _i114_np.minimum(corner_depth[selection], depth, out=corner_depth[selection])
    sums = corner_depth[:-1, :-1] + corner_depth[1:, :-1] + corner_depth[1:, 1:] + corner_depth[:-1, 1:]
    centre_depth = 3 * depth - 0.5 * sums
    if _i114_np.any(centre_depth < 0):
        raise ValueError('conservative water centre depth negative')
    vertex_depth = _i114_np.concatenate((corner_depth.ravel(), centre_depth.ravel()))
    vertices = source['bed_vertices_xyz_m'].copy()
    vertices[:, 1] += vertex_depth
    wet_ids = _i114_np.flatnonzero(depth.ravel() > 0).astype(_i114_np.int64)
    triangles = source['bed_triangles'].reshape(-1, 4, 3)[wet_ids].reshape(-1, 3).copy()
    points = vertices[source['bed_triangles']][:, :, [0, 2]]
    delta1, delta2 = (points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    area = abs(delta1[:, 0] * delta2[:, 1] - delta1[:, 1] * delta2[:, 0]) / 2
    volumes = (area * vertex_depth[source['bed_triangles']].mean(axis=1)).reshape(-1, 4).sum(axis=1).reshape(shape)
    fv_volume = depth * meta['spacing_m'] ** 2
    discrepancy = volumes - fv_volume
    if not _i114_np.allclose(discrepancy, 0.0, rtol=0.0, atol=1e-10):
        raise ValueError('continuous fan per-cell volume differs from new-bed FV state')
    corner_stage = source['bed_corner_m'] + corner_depth
    centre_stage = source['bed_fan_center_m'] + centre_depth
    fv_stage = source['H2_m'] + depth
    corner_offsets = _i114_np.stack((corner_stage[:-1, :-1], corner_stage[1:, :-1], corner_stage[1:, 1:], corner_stage[:-1, 1:]), axis=-1) - fv_stage[:, :, None]
    diagnostics = dict(raster_volume_m3=float(_i114_np.sum(fv_volume, dtype=_i114_np.float64)), triangulated_volume_m3=float(_i114_np.sum(volumes, dtype=_i114_np.float64)), max_cell_volume_difference_m3=float(abs(discrepancy).max(initial=0)), wet_cell_count=int(len(wet_ids)), represented_wet_cell_count=int(len(wet_ids)), omitted_wet_cell_count=0, minimum_vertex_depth_m=float(vertex_depth.min(initial=0)), max_center_stage_offset_m=float(abs(centre_stage - fv_stage).max(initial=0)), max_corner_stage_offset_m=float(abs(corner_offsets).max(initial=0)))
    arrays = {name: value.copy() for name, value in source.items()}
    arrays.update(cell_depth_m=depth.copy(), corner_depth_m=corner_depth, center_depth_m=centre_depth, water_vertices_xyz_m=vertices, water_triangles=triangles, wet_cell_ids=wet_ids, cell_volume_m3=volumes)
    return (arrays, diagnostics)

def build_fine_water_frame(geometry, states, *, state_index):
    """Consume an identity-bound saved new-bed hydraulic state, never native water."""
    from terrain_pipeline.common_infra import identity as _i114_identity
    validate_fine_geometry(geometry)
    if states['identity_sha256'] != _i114_identity(states['arrays'], states['metadata']) or states['metadata'].get('bed_identity') != geometry['identity_sha256'] or states['metadata'].get('schema') != 'single-domain-fine-states-v1':
        raise ValueError('saved new-bed hydraulic state binding invalid')
    times = states['arrays']['time_s']
    if type(state_index) is not int or not 0 <= state_index < len(times):
        raise ValueError('saved fine state index invalid')
    depth = states['arrays']['depth_m'][state_index].reshape(geometry['arrays']['H2_m'].shape)
    arrays, diagnostics = _water_arrays(geometry, depth)
    metadata = dict(schema=WATER_SCHEMA, algorithm='per-cell-conservative-shared-water-fan-v1', coordinates=COORDINATES, representation=WATER_SEMANTICS, bed_identity=geometry['identity_sha256'], geometry_metadata=geometry['metadata'], hydraulic_state_identity=states['identity_sha256'], state_index=state_index, time_s=float(times[state_index]), water_generated=False, continuous_shared_surface=True, reconstruction_order_claim='conservative visualization only; no hydraulic order claim', limitation='centre depth may reach 3x FV cell depth; shared corner/centre stage differs from FV cell stage', **diagnostics, **{name: False for name in FLAGS})
    result = _freeze(arrays, metadata)
    validate_fine_water_frame(result)
    return result

def validate_fine_water_frame(result):
    arrays, metadata = _check(result, WATER_SCHEMA)
    if metadata.get('algorithm') != 'per-cell-conservative-shared-water-fan-v1' or metadata.get('representation') != WATER_SEMANTICS or metadata.get('water_generated') is not False or (metadata.get('continuous_shared_surface') is not True) or (metadata.get('reconstruction_order_claim') != 'conservative visualization only; no hydraulic order claim') or (metadata.get('limitation') != 'centre depth may reach 3x FV cell depth; shared corner/centre stage differs from FV cell stage'):
        raise ValueError('fine water conservative reconstruction semantics invalid')
    for name in ('bed_identity', 'hydraulic_state_identity'):
        _sha(metadata[name])
    if type(metadata['state_index']) is not int or metadata['state_index'] < 0 or (not _i114_math.isfinite(metadata['time_s'])):
        raise ValueError('fine water saved time invalid')
    extra = {'cell_depth_m', 'corner_depth_m', 'center_depth_m', 'water_vertices_xyz_m', 'water_triangles', 'wet_cell_ids', 'cell_volume_m3'}
    geometry = dict(arrays={name: value for name, value in arrays.items() if name not in extra}, metadata=metadata['geometry_metadata'], identity_sha256=metadata['bed_identity'])
    validate_fine_geometry(geometry)
    expected, diagnostics = _water_arrays(geometry, arrays['cell_depth_m'])
    _equal(arrays, expected)
    if any((metadata.get(name) != value for name, value in diagnostics.items())):
        raise ValueError('fine water per-cell volume/stage diagnostics invalid')
    return True

def save_fine_geometry(path, result):
    from terrain_pipeline.common_infra import save_bundle as _i114_save_bundle
    _i114_save_bundle(path, result, validator=validate_fine_geometry)

def save_fine_water_frame(path, result):
    from terrain_pipeline.common_infra import save_bundle as _i114_save_bundle
    _i114_save_bundle(path, result, validator=validate_fine_water_frame)

def _load(path, expected_sha256, expected_identity, validator):
    from terrain_pipeline.common_infra import load_bundle as _i114_load_bundle
    _sha(expected_sha256)
    _sha(expected_identity)
    result = _i114_load_bundle(path, expected_sha256=expected_sha256, validator=validator, max_bytes=MAX_BYTES)
    if result['identity_sha256'] != expected_identity:
        raise ValueError('external fine identity mismatch')
    return result

def load_fine_geometry(path, *, expected_sha256, expected_identity):
    return _load(path, expected_sha256, expected_identity, validate_fine_geometry)

def load_fine_water_frame(path, *, expected_sha256, expected_identity):
    return _load(path, expected_sha256, expected_identity, validate_fine_water_frame)
SUBGRID_MODEL = 'canonical-subcell-storage-segmented-face-local-inertia-v1'

def prepare_subgrid_support(bed):
    """Canonical bed samples define coarse hypsometry and segmented face support."""
    canonical = bed['arrays']['canonical_bed_center_m']
    rows, columns = bed['arrays']['H2_m'].shape
    factor = int(bed['metadata']['spacing_m'])
    if canonical.shape != (rows * factor, columns * factor):
        raise ValueError('canonical subcell support shape mismatch')
    datum = float(canonical.min())
    relative = canonical - datum
    subbed = relative.reshape(rows, factor, columns, factor).transpose(0, 2, 1, 3).reshape(rows * columns, factor ** 2)
    subbed = _i114_np.sort(subbed, axis=1)
    prefix = _i114_np.cumsum(subbed, axis=1)
    x_support = _i114_np.maximum(relative[:, :-1], relative[:, 1:])[:, factor - 1::factor]
    x_support = x_support.reshape(rows, factor, columns - 1).transpose(0, 2, 1).reshape(-1, factor)
    z_support = _i114_np.maximum(relative[:-1], relative[1:])[factor - 1::factor]
    z_support = z_support.reshape(rows - 1, columns, factor).reshape(-1, factor)
    boundary = _i114_np.concatenate((relative[:, 0].reshape(rows, factor), relative[:, -1].reshape(rows, factor), relative[0].reshape(columns, factor), relative[-1].reshape(columns, factor)))
    return (dict(subcell_bed_relative_m=subbed, subcell_prefix_relative_m=prefix, face_segment_crest_relative_m=_i114_np.concatenate((x_support, z_support)), boundary_segment_crest_relative_m=boundary), datum)

def storage_stages(mean_depth_m, subcell_bed_relative_m, subcell_prefix_relative_m):
    """Invert V=sum(max(stage-z,0)) for each independently solved coarse cell."""
    depth = _i114_np.asarray(mean_depth_m).ravel()
    bed, prefix = (subcell_bed_relative_m, subcell_prefix_relative_m)
    if depth.dtype != _i114_np.float64 or depth.shape != (len(bed),) or _i114_np.any(depth < 0):
        raise ValueError('subgrid mean volume depth invalid')
    count = bed.shape[1]
    volume = depth * count
    levels_volume = _i114_np.arange(1, count + 1)[None, :] * bed - prefix
    wet_count = _i114_np.maximum(_i114_np.sum(volume[:, None] >= levels_volume, axis=1), 1)
    positions = _i114_np.arange(len(depth))
    return (volume + prefix[positions, wet_count - 1]) / wet_count

def stage_depths(relative_stage_m, subcell_bed_relative_m):
    return _i114_np.maximum(relative_stage_m[:, None] - subcell_bed_relative_m, 0.0).mean(axis=1)

def segmented_flux(geometry, depth, internal_before, boundary_before, tailwater, forcing, dt_s, budget):
    """Pure coarse local-inertia momentum and donor limiter; no execution imports."""
    arrays, meta = (geometry['arrays'], geometry['metadata'])
    stage = storage_stages(depth, arrays['subcell_bed_relative_m'], arrays['subcell_prefix_relative_m'])
    left, right, cells = (arrays['face_left'], arrays['face_right'], arrays['boundary_cell'])
    spacing, datum = (meta['spacing_m'], meta['hydraulic_datum_m'])
    exterior = _i114_np.broadcast_to((tailwater - datum)[:, None], boundary_before.shape).copy()
    exterior[arrays['boundary_kind'] == 1] = arrays['boundary_segment_crest_relative_m'][arrays['boundary_kind'] == 1]

    def momentum(first, second, crests, previous, distance):
        if second.ndim == 1:
            second = second[:, None]
        flow_depth = _i114_np.maximum(_i114_np.maximum(first[:, None], second) - crests, 0.0)
        wet = flow_depth > 0
        rhs = previous - budget.gravity_m_s2 * flow_depth * dt_s * (second - first[:, None]) / distance
        drag = _i114_np.zeros_like(flow_depth)
        drag[wet] = budget.gravity_m_s2 * dt_s * budget.roughness_s_m_third ** 2 / flow_depth[wet] ** (7 / 3)
        result = _i114_np.zeros_like(previous)
        result[wet] = 2 * rhs[wet] / (1 + _i114_np.sqrt(1 + 4 * drag[wet] * abs(rhs[wet])))
        return result
    internal = momentum(stage[left], stage[right], arrays['face_segment_crest_relative_m'], internal_before, spacing)
    boundary = momentum(stage[cells], exterior, arrays['boundary_segment_crest_relative_m'], boundary_before, spacing / 2)
    boundary[arrays['boundary_kind'] == 0] = 0.0
    outgoing = _i114_np.bincount(left, weights=_i114_np.maximum(internal, 0).sum(axis=1), minlength=len(depth))
    outgoing += _i114_np.bincount(right, weights=_i114_np.maximum(-internal, 0).sum(axis=1), minlength=len(depth))
    outgoing += _i114_np.bincount(cells, weights=_i114_np.maximum(boundary, 0).sum(axis=1), minlength=len(depth))
    available = depth * spacing ** 2 + dt_s * forcing
    limited = outgoing * dt_s > available
    factors = _i114_np.ones(len(depth))
    factors[limited] = available[limited] / (outgoing[limited] * dt_s) * (1 - 1e-12)
    raw_internal, raw_boundary = (internal.copy(), boundary.copy())
    internal *= _i114_np.where(internal >= 0, factors[left, None], factors[right, None])
    boundary *= _i114_np.where(boundary >= 0, factors[cells, None], 1.0)
    limiter = dict(limited_donors=int(_i114_np.count_nonzero(limited)), minimum_scale=float(factors.min(initial=1)), limited_volume_m3=float(dt_s * (abs(raw_internal - internal).sum() + abs(raw_boundary - boundary).sum())))
    return (internal, boundary, limiter)
LIMITATIONS = ['D4 local inertia with Manning drag omits advective momentum; not full Saint-Venant certification.', 'Each FV bed is the area mean of the same continuous triangle fan; subcell wetted storage requires separate geometric reconstruction and validation.', 'Conceptual terrestrial soil rain infiltration applies to every cell; surface water re-infiltration and material permeability are not modelled.', 'Fine terrain is interpolation and explicitly derived channels, not new Terrain Diffusion source information.', 'Prescribed stage and drainage faces are engineering boundaries, not verified natural outlets.', 'Signed boundary transfers independently verify net exterior exchange; gross import/export snapshot totals have no independent per-substep directional witness.']

def _advance_subgrid(geometry, *, initial_depth_m, forcing_interval_s, intervals, forcing_provider, boundary_stage_provider, source_identity, forcing_identity, budget, snapshot_interval_s, interval_observer, momentum_observer):
    """One independently evolved coarse volume per cell; canonical segmented Q."""
    from terrain_pipeline.surface_hydraulics import validate_budget as _x88_validate_budget
    a, meta = (geometry['arrays'], geometry['metadata'])
    _x88_validate_budget(budget)
    initial = _i115_np.asarray(initial_depth_m)
    if initial.dtype != _i115_np.float64 or initial.shape != a['H2_m'].shape or _i115_np.any(initial < 0) or _i115_np.any(initial > budget.max_depth_m) or (not _i115_np.isfinite(initial).all()):
        raise ValueError('subgrid initial mean depth invalid')
    if initial.size > budget.max_cells or intervals * forcing_interval_s > budget.max_duration_s:
        raise ValueError('subgrid predeclared domain/duration exceeded')
    if snapshot_interval_s != forcing_interval_s or intervals + 1 > budget.max_snapshots:
        raise ValueError('subgrid saves exactly one snapshot per forcing interval')
    estimate = sum((value.nbytes for value in a.values()))
    estimate += initial.size * 8 * (2 * (intervals + 1) + 30)
    estimate += (a['face_segment_crest_relative_m'].size + a['boundary_segment_crest_relative_m'].size) * 8 * (12 + 8 * intervals)
    if estimate > budget.max_bytes:
        raise ValueError('subgrid memory preflight exceeded')
    depth = initial.ravel().copy()
    internal = _i115_np.zeros_like(a['face_segment_crest_relative_m'])
    boundary = _i115_np.zeros_like(a['boundary_segment_crest_relative_m'])
    left, right, cells = (a['face_left'], a['face_right'], a['boundary_cell'])
    area, datum = (meta['spacing_m'] ** 2, meta['hydraulic_datum_m'])
    times, snapshots, stage_snapshots = ([0.0], [initial.copy()], [])
    initial_volume = float(depth.sum() * area)
    supplied = imported = exported = 0.0
    ledgers = [[0.0, 0.0, 0.0, initial_volume, 0.0]]
    accepted = evaluations = limiter_count = 0
    minimum_dt, maximum_dt, max_froude = (_i115_math.inf, 0.0, 0.0)
    residual_max = residual_sum = removed_total = raw_total = 0.0
    minimum_factor = 1.0
    started = _i115_time.monotonic()
    current_time = 0.0
    stage_snapshots.append(storage_stages(depth, a['subcell_bed_relative_m'], a['subcell_prefix_relative_m']).reshape(initial.shape))
    for interval in range(intervals):
        forcing = _i115_np.asarray(forcing_provider(interval)).ravel()
        tailwater = _i115_np.asarray(boundary_stage_provider(interval))
        if forcing.dtype != _i115_np.float64 or forcing.shape != depth.shape or (not _i115_np.isfinite(forcing).all()) or _i115_np.any(forcing < 0) or (tailwater.dtype != _i115_np.float64) or (tailwater.shape != (len(cells),)) or (not _i115_np.isfinite(tailwater).all()):
            raise ValueError('subgrid finite complete forcing/tailwater required')
        before_depth, before_i, before_b = (depth.copy(), internal.copy(), boundary.copy())
        transfer_i, transfer_b, delivered = (_i115_np.zeros_like(internal), _i115_np.zeros_like(boundary), _i115_np.zeros_like(depth))
        start_time, end_time = (interval * forcing_interval_s, (interval + 1) * forcing_interval_s)
        first = True
        while current_time < end_time:
            if accepted >= budget.max_substeps or evaluations + internal.size + boundary.size > budget.max_face_evaluations or _i115_time.monotonic() - started >= budget.max_wall_s:
                raise RuntimeError('subgrid execution resource budget exceeded')
            stage = storage_stages(depth, a['subcell_bed_relative_m'], a['subcell_prefix_relative_m'])
            flow_depth = _i115_np.maximum(_i115_np.maximum(stage[left], stage[right])[:, None] - a['face_segment_crest_relative_m'], 0.0)
            exterior = _i115_np.broadcast_to((tailwater - datum)[:, None], boundary.shape).copy()
            exterior[a['boundary_kind'] == 1] = a['boundary_segment_crest_relative_m'][a['boundary_kind'] == 1]
            boundary_depth = _i115_np.maximum(_i115_np.maximum(stage[cells, None], exterior) - a['boundary_segment_crest_relative_m'], 0.0)
            deepest = max(float(flow_depth.max(initial=0)), float(boundary_depth[a['boundary_kind'] != 0].max(initial=0)))
            cfl = budget.inertial_cfl * meta['spacing_m'] / 2 / _i115_math.sqrt(budget.gravity_m_s2 * deepest) if deepest else _i115_math.inf
            dt = min(budget.max_dt_s, cfl, end_time - current_time)
            next_i, next_b, limiter = segmented_flux(geometry, depth, internal, boundary, tailwater, forcing, dt, budget)
            qi, qb = (next_i.sum(axis=1), next_b.sum(axis=1))
            net = _i115_np.bincount(right, weights=qi, minlength=len(depth)) - _i115_np.bincount(left, weights=qi, minlength=len(depth))
            net -= _i115_np.bincount(cells, weights=qb, minlength=len(depth))
            updated = depth + dt * (forcing + net) / area
            if not _i115_np.isfinite(updated).all() or _i115_np.any(updated < 0) or _i115_np.any(updated > budget.max_depth_m):
                raise RuntimeError('subgrid positivity/depth refusal; no clipping')
            residual = area * (updated - depth) - dt * (forcing + net)
            residual_max = max(residual_max, float(abs(residual).max(initial=0)))
            residual_sum += float(abs(residual).sum())
            if first:
                momentum_observer(dict(interval=interval, time_start_s=current_time, dt_s=dt, depth_before_m=depth.copy(), depth_after_m=updated.copy(), forcing_m3_s=forcing.copy(), tailwater_m=tailwater.copy(), internal_q_before_m3_s=internal.sum(axis=1), internal_q_after_m3_s=qi, boundary_q_before_m3_s=boundary.sum(axis=1), boundary_q_after_m3_s=qb, internal_segment_q_before_m3_s=internal.copy(), internal_segment_q_after_m3_s=next_i.copy(), boundary_segment_q_before_m3_s=boundary.copy(), boundary_segment_q_after_m3_s=next_b.copy(), limiter=limiter))
                first = False
            wet = flow_depth >= 0.001
            if wet.any():
                froude = abs(next_i[wet]) / flow_depth[wet] / _i115_np.sqrt(budget.gravity_m_s2 * flow_depth[wet])
                max_froude = max(max_froude, float(froude.max(initial=0)))
            limiter_count += limiter['limited_donors']
            minimum_factor = min(minimum_factor, limiter['minimum_scale'])
            removed_total += limiter['limited_volume_m3']
            raw_total += dt * (abs(next_i).sum() + abs(next_b).sum())
            transfer_i += dt * next_i
            transfer_b += dt * next_b
            delivered += dt * forcing
            supplied += float(dt * forcing.sum())
            imported += float(dt * _i115_np.maximum(-next_b, 0).sum())
            exported += float(dt * _i115_np.maximum(next_b, 0).sum())
            depth, internal, boundary = (updated, next_i, next_b)
            current_time = end_time if dt == end_time - current_time else current_time + dt
            accepted += 1
            evaluations += internal.size + boundary.size
            minimum_dt, maximum_dt = (min(minimum_dt, dt), max(maximum_dt, dt))
        interval_observer(dict(interval=interval, time_start_s=start_time, time_end_s=end_time, depth_before_m=before_depth, depth_after_m=depth.copy(), internal_transfer_m3=transfer_i.sum(axis=1), boundary_transfer_m3=transfer_b.sum(axis=1), forcing_volume_m3=delivered, internal_segment_transfer_m3=transfer_i, boundary_segment_transfer_m3=transfer_b, internal_q_before_m3_s=before_i.sum(axis=1), internal_q_after_m3_s=internal.sum(axis=1), boundary_q_before_m3_s=before_b.sum(axis=1), boundary_q_after_m3_s=boundary.sum(axis=1), internal_segment_q_before_m3_s=before_i, internal_segment_q_after_m3_s=internal.copy(), boundary_segment_q_before_m3_s=before_b, boundary_segment_q_after_m3_s=boundary.copy()))
        volume = float(depth.sum() * area)
        ledgers.append([supplied, imported, exported, volume, volume - initial_volume - supplied - imported + exported])
        times.append(end_time)
        snapshots.append(depth.reshape(initial.shape).copy())
        stage_snapshots.append(storage_stages(depth, a['subcell_bed_relative_m'], a['subcell_prefix_relative_m']).reshape(initial.shape))
    return dict(arrays=dict(time_s=_i115_np.asarray(times), depth_m=_i115_np.asarray(snapshots), initial_depth_m=initial.copy(), ledger=_i115_np.asarray(ledgers), stage_relative_m=_i115_np.asarray(stage_snapshots), final_internal_q_m3_s=internal.sum(axis=1), final_boundary_q_m3_s=boundary.sum(axis=1), final_internal_segment_q_m3_s=internal, final_boundary_segment_q_m3_s=boundary), metadata=dict(schema=SUBGRID_MODEL, source_identity=source_identity, forcing_identity=forcing_identity, status='completed', failure=None, budget=vars(budget), requested_time_s=intervals * forcing_interval_s, committed_time_s=current_time, substeps=accepted, face_evaluations=evaluations, estimated_peak_bytes=estimate, wall_s=_i115_time.monotonic() - started, initial_volume_m3=initial_volume, supplied_m3=supplied, boundary_input_m3=imported, boundary_output_m3=exported, final_volume_m3=float(depth.sum() * area), hydraulic_model=SUBGRID_MODEL, scope='coarse independent volume/stage; canonical subcell storage and segmented face Q; no advection'), diagnostics=dict(minimum_dt_s=minimum_dt, maximum_dt_s=maximum_dt, max_face_froude=max_froude, limited_donor_count=limiter_count, minimum_limiter_factor=minimum_factor, removed_transfer_m3=removed_total, raw_transfer_m3=raw_total, max_cell_residual_m3=residual_max, sum_absolute_cell_residual_m3=residual_sum, negative_water_clip_count=0, physical_limitation='no advective momentum; supercritical front convergence not guaranteed'))

def _bundle(arrays, metadata):
    from terrain_pipeline.common_infra import identity as _i115_identity
    return dict(arrays=arrays, metadata=metadata, identity_sha256=_i115_identity(arrays, metadata))
from terrain_pipeline.runoff import RunoffParameters as _i115_RunoffParameters

def run_fine_hydraulics(bed, *, rain_mm_h, boundary_stage_m, forcing_interval_s, boundary_kind, boundary_crest_m=None, initial_depth_m=None, runoff_parameters=_i115_RunoffParameters(), budget=None, backend='accelerated'):
    """Execute existing kernels on a newly bound bed; retain complete interval evidence."""
    from terrain_pipeline.common_infra import identity as _i115_identity
    from terrain_pipeline.runoff import simulate_rainfall_runoff as _i115_simulate_rainfall_runoff
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _x85_SurfaceBudget
    from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _x86_prepare_surface_geometry
    from terrain_pipeline.surface_hydraulics import advance_inertial_surface as _x87_advance_inertial_surface
    arrays, metadata = (bed['arrays'], bed['metadata'])
    if bed.get('identity_sha256') != _i115_identity(arrays, metadata):
        raise ValueError('fine bed content identity mismatch')
    height = arrays['bed_center_m']
    spacing = metadata['spacing_m']
    origin = [value + spacing / 2 for value in metadata['origin_m_xz']]
    if not isinstance(rain_mm_h, _i115_np.ndarray) or rain_mm_h.dtype != _i115_np.float64 or rain_mm_h.ndim != 3 or (rain_mm_h.shape[1:] != height.shape) or (not _i115_np.isfinite(rain_mm_h).all()) or _i115_np.any(rain_mm_h < 0):
        raise ValueError('fine complete finite rainfall grid required')
    steps = len(rain_mm_h)
    if not 1 <= steps <= 48 or steps * height.size > 1000000:
        raise ValueError('fine runoff saved-state resource budget exceeded')
    if type(forcing_interval_s) not in (int, float) or not _i115_math.isfinite(forcing_interval_s) or (not 0 < forcing_interval_s <= 3600):
        raise ValueError('fine physical forcing interval required')
    if budget is None:
        budget = _x85_SurfaceBudget(max_dt_s=0.1, max_cells=65536, max_snapshots=steps + 2, max_wall_s=1800.0, max_duration_s=600.0, max_depth_m=10.0)
    if budget.max_snapshots < steps + 2 or budget.max_wall_s > 1800 or budget.max_bytes > 268435456:
        raise ValueError('fine snapshot/wall/artifact predeclaration rejected')
    geometry = _x86_prepare_surface_geometry(height, spacing_m=spacing, origin_m_xz=origin, source_identity=bed['identity_sha256'], boundary_kind=boundary_kind, boundary_crest_m=boundary_crest_m)
    geometry['metadata']['scope'] = 'explicit_fine_same_area_mean_bed_D4_FV_not_subcell_triangle_hydraulics'
    subgrid = backend in ('subgrid', 'shallow_water_subgrid', 'shallow_water_subgrid_manning', 'shallow_water_subgrid_manning_accelerated')
    if subgrid and 'canonical_bed_center_m' not in arrays:
        raise ValueError('explicit subgrid backend requires canonical hydraulic support')
    if subgrid:
        support, datum = prepare_subgrid_support(bed)
        if boundary_crest_m is not None:
            support['boundary_segment_crest_relative_m'] = _i115_np.maximum(support['boundary_segment_crest_relative_m'], _i115_np.asarray(boundary_crest_m)[:, None] - datum)
        geometry['arrays'].update(support)
        geometry['metadata'].update(hydraulic_model=SUBGRID_MODEL, hydraulic_datum_m=datum, subcell_spacing_m=1.0, coarse_independent_unknowns=height.size, explicit_boundary_crest=boundary_crest_m is not None)
    geometry = _bundle(geometry['arrays'], geometry['metadata'])
    boundary_stage_m = _i115_np.asarray(boundary_stage_m)
    boundaries = len(geometry['arrays']['boundary_cell'])
    if boundary_stage_m.shape != (steps, boundaries) or boundary_stage_m.dtype != _i115_np.float64 or (not _i115_np.isfinite(boundary_stage_m).all()):
        raise ValueError('fine explicit complete engineering tailwater required')
    initial = _i115_np.zeros(height.shape) if initial_depth_m is None else initial_depth_m
    runoff = _i115_simulate_rainfall_runoff(rain_mm_h.reshape(steps, height.size), _i115_np.full(height.size, spacing ** 2), dt_s=forcing_interval_s, source_id=bed['identity_sha256'], parameters=runoff_parameters)
    runoff_arrays = {key: value for key, value in runoff.items() if key != 'metadata'}
    forcing_metadata = dict(schema='single-domain-fine-forcing-v1', bed_identity=bed['identity_sha256'], grid_shape=list(height.shape), spacing_m=spacing, origin_m_xz=origin, runoff_metadata=runoff['metadata'], steps=steps, dt_s=forcing_interval_s, rain_semantics='all-cell conceptual terrestrial soil infiltration; release enters surface exactly once', q_semantics='local_q timestep average; face_q saved endpoint instantaneous discharge', hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    runoff_arrays['boundary_stage_m'] = boundary_stage_m.copy()
    forcing = _bundle(runoff_arrays, forcing_metadata)
    intervals, momenta = ([], [])

    def observe(packet, target, schema):
        info = {key: value for key, value in packet.items() if not isinstance(value, _i115_np.ndarray)}
        fields = {key: value for key, value in packet.items() if isinstance(value, _i115_np.ndarray)}
        info.update(schema=schema, bed_identity=bed['identity_sha256'], geometry_identity=geometry['identity_sha256'], forcing_identity=forcing['identity_sha256'], hydraulic_ready=False, natural_outlet_verified=False, publishable=False, hydraulic_model=geometry['metadata'].get('hydraulic_model', 'flat-cell-local-inertia'))
        target.append(_bundle(fields, info))
    if backend in ('shallow_water_subgrid_manning', 'shallow_water_subgrid_manning_accelerated'):
        if backend == 'shallow_water_subgrid_manning_accelerated':
            from terrain_pipeline.shallow_water import advance_shallow_water_accelerated as advance_shallow_water
        else:
            from terrain_pipeline.shallow_water import advance_canonical_manning as advance_shallow_water
        from terrain_pipeline.shallow_water import CANONICAL_MANNING_MODEL as MODEL
        geometry['metadata']['hydraulic_model'] = MODEL
        geometry['metadata']['scope'] = 'independent_subgrid_storage_segmented_HLL_canonical_Manning'
        geometry = _bundle(geometry['arrays'], geometry['metadata'])
        advance = advance_shallow_water
    elif backend == 'shallow_water_subgrid':
        from terrain_pipeline.shallow_water import advance_subgrid_segmented_hll as advance_shallow_water
        from terrain_pipeline.shallow_water import SUBGRID_SEGMENTED_HLL_MODEL as MODEL
        geometry['metadata']['hydraulic_model'] = MODEL
        geometry['metadata']['scope'] = 'independent_subgrid_storage_segmented_advective_HLL'
        geometry = _bundle(geometry['arrays'], geometry['metadata'])
        advance = advance_shallow_water
    elif backend == 'shallow_water':
        from terrain_pipeline.shallow_water import advance_hydrostatic_hll as advance_shallow_water
        from terrain_pipeline.shallow_water import HYDROSTATIC_HLL_MODEL as MODEL
        geometry['metadata']['hydraulic_model'] = MODEL
        geometry = _bundle(geometry['arrays'], geometry['metadata'])
        advance = advance_shallow_water
    elif subgrid:
        advance = _advance_subgrid
    elif backend == 'accelerated':
        from terrain_pipeline.surface_hydraulics import advance_accelerated_surface as advance_accelerated_surface
        advance = advance_accelerated_surface
    elif backend == 'reference':
        advance = _x87_advance_inertial_surface
    else:
        raise ValueError('unknown fine execution backend')
    evolved = advance(geometry, initial_depth_m=initial, forcing_interval_s=forcing_interval_s, intervals=steps, forcing_provider=lambda index: runoff['local_q_m3_s'][index].reshape(height.shape), boundary_stage_provider=lambda index: boundary_stage_m[index], source_identity=bed['identity_sha256'], forcing_identity=forcing['identity_sha256'], budget=budget, snapshot_interval_s=forcing_interval_s, interval_observer=lambda packet: observe(packet, intervals, 'single-domain-fine-interval-v1'), momentum_observer=lambda packet: observe(packet, momenta, 'single-domain-fine-momentum-v1'))
    if evolved['metadata']['status'] != 'completed' or len(intervals) != steps or len(momenta) != steps:
        raise RuntimeError('fine hydraulic resource/positivity refusal: ' + str(evolved['metadata']['failure']))
    state_metadata = dict(schema='single-domain-fine-states-v1', bed_identity=bed['identity_sha256'], geometry_identity=geometry['identity_sha256'], forcing_identity=forcing['identity_sha256'], solver_metadata=evolved['metadata'], diagnostics=evolved['diagnostics'], interval_count=steps, hydraulic_ready=False, natural_outlet_verified=False, publishable=False, limitations=list(LIMITATIONS), hydraulic_model=evolved['metadata'].get('hydraulic_model', 'flat-cell-local-inertia'))
    states = _bundle(evolved['arrays'], state_metadata)
    return dict(bed=bed, geometry=geometry, forcing=forcing, states=states, intervals=intervals, momenta=momenta, runoff_parameters=_i115_asdict(runoff_parameters), limitations=list(LIMITATIONS))
SINGLE_DOMAIN_FINE_IO_MAX_BYTES = 268435456
SHALLOW_MODEL = 'single-domain-hydrostatic-HLL-SSPRK2-v1'
SHALLOW_MODEL_V2 = 'single-domain-MUSCL-hydrostatic-HLL-SSPRK2-v2'
SHALLOW_SUBGRID_MODEL = 'single-domain-subgrid-storage-segmented-HLL-SSPRK2-v3'
SHALLOW_SUBGRID_MANNING_MODEL = 'single-domain-subgrid-storage-segmented-HLL-canonical-Manning-SSPRK2-v7'
SHALLOW_SUBGRID_MODELS = (SHALLOW_SUBGRID_MODEL, SHALLOW_SUBGRID_MANNING_MODEL)
SHALLOW_MODELS = (SHALLOW_MODEL, SHALLOW_MODEL_V2, *SHALLOW_SUBGRID_MODELS)
INTERVAL_ARRAYS = ('depth_before_m', 'depth_after_m', 'internal_transfer_m3', 'boundary_transfer_m3', 'forcing_volume_m3', 'internal_q_before_m3_s', 'internal_q_after_m3_s', 'boundary_q_before_m3_s', 'boundary_q_after_m3_s')

def _single_domain_fine_io_check(result, schema):
    from terrain_pipeline.common_infra import identity as _i116_identity
    if result.get('identity_sha256') != _i116_identity(result['arrays'], result['metadata']) or result['metadata'].get('schema') != schema or any((result['metadata'].get(name) is not False for name in FLAGS)) or any((not _i116_np.isfinite(value).all() for value in result['arrays'].values())):
        raise ValueError('fine saved schema/identity/flags/finite mismatch')
    return (result['arrays'], result['metadata'])

def _near(actual, expected, label):
    actual, expected = (_i116_np.asarray(actual), _i116_np.asarray(expected))
    if actual.shape != expected.shape or not _i116_np.isfinite(actual).all() or (not _i116_np.isfinite(expected).all()) or _i116_np.any(abs(actual - expected) > 1e-08 + 2e-11 * abs(expected)):
        raise ValueError('fine independent account mismatch: ' + label)

def canonical_bed_fields(bed):
    """Evaluate declared source/cut/protection math without geometry construction."""
    arrays, meta = (bed['arrays'], bed['metadata'])
    height, mask = (arrays['native_height_m'], arrays['native_protected_mask'])
    x0, x1, z0, z1 = meta['native_window']
    x, z = _i116_np.meshgrid(x0 + (_i116_np.arange((x1 - x0) * 30) + 0.5) / 30.0, z0 + (_i116_np.arange((z1 - z0) * 30) + 0.5) / 30.0)
    ix, iz = (_i116_np.floor(x).astype(int), _i116_np.floor(z).astype(int))
    jx, jz = (_i116_np.minimum(ix + 1, height.shape[1] - 1), _i116_np.minimum(iz + 1, height.shape[0] - 1))
    tx, tz = (x - ix, z - iz)
    native = (height[iz, ix] * (1 - tx) + height[iz, jx] * tx) * (1 - tz) + (height[jz, ix] * (1 - tx) + height[jz, jx] * tx) * tz
    cut = _i116_np.zeros(native.shape)
    for first, second in arrays['selected_edge_cell_ids']:
        if arrays['native_receiver'][first] != second:
            raise ValueError('fine canonical cut edge source mismatch')
        ax, az = (first % height.shape[1], first // height.shape[1])
        bx, bz = (second % height.shape[1], second // height.shape[1])
        length = (bx - ax) ** 2 + (bz - az) ** 2
        if length != 1:
            raise ValueError('fine canonical cut requires D4 receiver segment')
        fraction = _i116_np.clip(((x - ax) * (bx - ax) + (z - az) * (bz - az)) / length, 0, 1)
        distance = 30 * _i116_np.hypot(x - ax - fraction * (bx - ax), z - az - fraction * (bz - az))
        cut = _i116_np.maximum(cut, _i116_np.where(distance < 4, 0.5 * (1 + _i116_np.cos(_i116_np.pi * _i116_np.minimum(distance / 4, 1))), 0))
    protected = mask[iz, ix] | mask[iz, jx] | mask[jz, ix] | mask[jz, jx]
    cut[protected] = 0
    return (native - cut, protected)

def validate_canonical_bed(bed):
    arrays, meta = (bed['arrays'], bed['metadata'])
    if meta.get('scope') == 'synthetic_fixture' and 'canonical_bed_center_m' not in arrays:
        return True
    if 'canonical_bed_center_m' not in arrays:
        raise ValueError('fine saved canonical bed witness required')
    canonical = arrays['canonical_bed_center_m']
    if canonical.dtype != _i116_np.float64 or not _i116_np.isfinite(canonical).all():
        raise ValueError('fine saved canonical bed finite/type mismatch')
    factor = int(meta['spacing_m'])
    rows, columns = arrays['bed_center_m'].shape
    if canonical.shape != (rows * factor, columns * factor):
        raise ValueError('fine canonical complete footprint mismatch')
    _near(arrays['bed_center_m'], canonical.reshape(rows, factor, columns, factor).mean(axis=(1, 3)), 'canonical area restriction')
    points = arrays['bed_vertices_xyz_m'][arrays['bed_triangles']]
    normals = _i116_np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    if _i116_np.any(normals[:, 1] <= 0) or len(points) != 4 * rows * columns:
        raise ValueError('fine triangle bed winding/coverage mismatch')
    areas = normals[:, 1] / 2
    integrated = (areas * points[:, :, 1].mean(axis=1)).reshape(rows, columns, 4).sum(axis=2) / meta['spacing_m'] ** 2
    _near(integrated, arrays['bed_center_m'], 'actual triangle area-mean bed')
    return True

def validate_initial_contract(states, *, bed, lake_stage_m, initial_kind):
    canonical = bed['arrays']['canonical_bed_center_m']
    factor = int(bed['metadata']['spacing_m'])
    rows, columns = bed['arrays']['bed_center_m'].shape
    expected = _i116_np.zeros((rows, columns)) if initial_kind == 'rain' else _i116_np.maximum(lake_stage_m - canonical, 0).reshape(rows, factor, columns, factor).mean(axis=(1, 3))
    _near(states['arrays']['initial_depth_m'], expected, 'canonical initial water contract')
    return True

def _segment_momentum_witness(geometry, depth, internal_before, boundary_before, tailwater, forcing, dt, budget, stage):
    """Independent saved-step equation certificate; no solver helper or advancement."""
    arrays, meta = (geometry['arrays'], geometry['metadata'])
    left, right, cells = (arrays['face_left'], arrays['face_right'], arrays['boundary_cell'])
    exterior = _i116_np.broadcast_to((tailwater - meta['hydraulic_datum_m'])[:, None], boundary_before.shape).copy()
    drainage = arrays['boundary_kind'] == 1
    exterior[drainage] = arrays['boundary_segment_crest_relative_m'][drainage]
    answers = []
    for first, second, crest, previous, distance in ((stage[left, None], stage[right, None], arrays['face_segment_crest_relative_m'], internal_before, meta['spacing_m']), (stage[cells, None], exterior, arrays['boundary_segment_crest_relative_m'], boundary_before, meta['spacing_m'] / 2)):
        wet_depth = _i116_np.maximum(_i116_np.maximum(first, second) - crest, 0)
        wet = wet_depth > 0
        rhs = previous - budget.gravity_m_s2 * wet_depth * dt * (second - first) / distance
        drag = _i116_np.zeros_like(wet_depth)
        drag[wet] = budget.gravity_m_s2 * dt * budget.roughness_s_m_third ** 2 / wet_depth[wet] ** (7 / 3)
        answer = _i116_np.zeros_like(previous)
        answer[wet] = 2 * rhs[wet] / (1 + _i116_np.sqrt(1 + 4 * drag[wet] * abs(rhs[wet])))
        answers.append(answer)
    internal, boundary = answers
    boundary[arrays['boundary_kind'] == 0] = 0
    outgoing = _i116_np.bincount(left, weights=_i116_np.maximum(internal, 0).sum(axis=1), minlength=len(depth))
    outgoing += _i116_np.bincount(right, weights=_i116_np.maximum(-internal, 0).sum(axis=1), minlength=len(depth))
    outgoing += _i116_np.bincount(cells, weights=_i116_np.maximum(boundary, 0).sum(axis=1), minlength=len(depth))
    available = depth * meta['spacing_m'] ** 2 + dt * forcing
    limited = outgoing * dt > available
    factors = _i116_np.ones(len(depth))
    factors[limited] = available[limited] / (outgoing[limited] * dt) * (1 - 1e-12)
    raw_internal, raw_boundary = (internal.copy(), boundary.copy())
    internal *= _i116_np.where(internal >= 0, factors[left, None], factors[right, None])
    boundary *= _i116_np.where(boundary >= 0, factors[cells, None], 1.0)
    limiter = dict(limited_donors=int(limited.sum()), minimum_scale=float(factors.min(initial=1)), limited_volume_m3=float(dt * (abs(raw_internal - internal).sum() + abs(raw_boundary - boundary).sum())))
    return (internal, boundary, limiter)

def single_domain_fine_io_validate_fine_geometry(geometry, *, bed):
    from terrain_pipeline.common_infra import identity as _i116_identity
    from terrain_pipeline.surface_hydraulics import validate_surface_geometry as _x89_validate_surface_geometry
    if bed['identity_sha256'] != _i116_identity(bed['arrays'], bed['metadata']):
        raise ValueError('fine original bed content identity mismatch')
    if geometry['identity_sha256'] != _i116_identity(geometry['arrays'], geometry['metadata']):
        raise ValueError('fine hydraulic geometry identity mismatch')
    validate_canonical_bed(bed)
    height = bed['arrays']['bed_center_m']
    subgrid = geometry['metadata'].get('hydraulic_model') in (SUBGRID_MODEL, *SHALLOW_SUBGRID_MODELS)
    shallow = geometry['metadata'].get('hydraulic_model') == SHALLOW_MODEL
    support_names = {'subcell_bed_relative_m', 'subcell_prefix_relative_m', 'face_segment_crest_relative_m', 'boundary_segment_crest_relative_m'}
    base_arrays = {name: value for name, value in geometry['arrays'].items() if name not in support_names}
    _x89_validate_surface_geometry(dict(arrays=base_arrays, metadata=geometry['metadata']), trusted_height=height, source_identity=bed['identity_sha256'])
    spacing = bed['metadata']['spacing_m']
    center = [value + spacing / 2 for value in bed['metadata']['origin_m_xz']]
    if geometry['metadata']['spacing_m'] != spacing or geometry['metadata']['origin_m_xz'] != center:
        raise ValueError('fine hydraulic cell-center coordinate binding mismatch')
    if subgrid:
        canonical = bed['arrays']['canonical_bed_center_m']
        rows, columns = height.shape
        factor = int(spacing)
        datum = float(canonical.min())
        relative = canonical - datum
        subbed = _i116_np.sort(relative.reshape(rows, factor, columns, factor).transpose(0, 2, 1, 3).reshape(rows * columns, factor ** 2), axis=1)
        face_x = _i116_np.maximum(relative[:, :-1], relative[:, 1:])[:, factor - 1::factor].reshape(rows, factor, columns - 1).transpose(0, 2, 1).reshape(-1, factor)
        face_z = _i116_np.maximum(relative[:-1], relative[1:])[factor - 1::factor].reshape(rows - 1, columns, factor).reshape(-1, factor)
        boundary = _i116_np.concatenate((relative[:, 0].reshape(rows, factor), relative[:, -1].reshape(rows, factor), relative[0, :].reshape(columns, factor), relative[-1, :].reshape(columns, factor)))
        expected = dict(subcell_bed_relative_m=subbed, subcell_prefix_relative_m=_i116_np.cumsum(subbed, axis=1), face_segment_crest_relative_m=_i116_np.concatenate((face_x, face_z)), boundary_segment_crest_relative_m=boundary)
        if set(geometry['arrays']) - set(base_arrays) != support_names or geometry['metadata']['hydraulic_datum_m'] != datum or geometry['metadata']['subcell_spacing_m'] != 1.0 or (geometry['metadata']['coarse_independent_unknowns'] != height.size):
            raise ValueError('subgrid canonical support metadata mismatch')
        for name, values in expected.items():
            _near(geometry['arrays'][name], values, 'independent canonical segmented support ' + name)
    elif set(geometry['arrays']) != set(base_arrays):
        raise ValueError('flat hydraulic model cannot carry subgrid support')
    return True

def validate_fine_forcing(forcing, *, bed):
    from terrain_pipeline.runoff import RUNOFF_ARRAY_KEYS as _i116_ARRAY_KEYS
    from terrain_pipeline.runoff import validate_rainfall_runoff_result as _i116_validate_rainfall_runoff_result
    arrays, metadata = _single_domain_fine_io_check(forcing, 'single-domain-fine-forcing-v1')
    shape = bed['arrays']['bed_center_m'].shape
    steps = metadata['steps']
    if type(steps) is not int or not 1 <= steps <= 48 or steps * _i116_math.prod(shape) > 1000000 or (metadata['bed_identity'] != bed['identity_sha256']) or (metadata['grid_shape'] != list(shape)) or (metadata['spacing_m'] != bed['metadata']['spacing_m']) or (metadata['origin_m_xz'] != [value + metadata['spacing_m'] / 2 for value in bed['metadata']['origin_m_xz']]) or (set(arrays) != set(_i116_ARRAY_KEYS) | {'boundary_stage_m'}):
        raise ValueError('fine forcing exact source/grid/fields mismatch')
    runoff = {key: arrays[key] for key in _i116_ARRAY_KEYS}
    runoff['metadata'] = metadata['runoff_metadata']
    _i116_validate_rainfall_runoff_result(runoff)
    if runoff['metadata']['source_id'] != bed['identity_sha256'] or runoff['metadata']['dt_s'] != metadata['dt_s']:
        raise ValueError('fine forcing runoff source/time mismatch')
    if not _i116_np.array_equal(arrays['area_m2'], _i116_np.full(_i116_math.prod(shape), metadata['spacing_m'] ** 2)):
        raise ValueError('fine forcing exact support area mismatch')
    boundaries = 2 * sum(shape)
    if arrays['boundary_stage_m'].dtype != _i116_np.float64 or arrays['boundary_stage_m'].shape != (steps, boundaries):
        raise ValueError('fine forcing complete tailwater coverage mismatch')
    return True

def validate_fine_states(states, *, bed, geometry, forcing):
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _x90_SurfaceBudget
    from terrain_pipeline.surface_hydraulics import validate_budget as _x91_validate_budget
    arrays, metadata = _single_domain_fine_io_check(states, 'single-domain-fine-states-v1')
    single_domain_fine_io_validate_fine_geometry(geometry, bed=bed)
    validate_fine_forcing(forcing, bed=bed)
    steps, dt = (forcing['metadata']['steps'], forcing['metadata']['dt_s'])
    shape = bed['arrays']['bed_center_m'].shape
    solver = metadata['solver_metadata']
    subgrid = geometry['metadata'].get('hydraulic_model') == SUBGRID_MODEL
    model = geometry['metadata'].get('hydraulic_model')
    shallow = model in SHALLOW_MODELS
    extra_names = {'stage_relative_m', 'final_internal_segment_q_m3_s', 'final_boundary_segment_q_m3_s'} if subgrid else {'momentum_x_m2_s', 'momentum_z_m2_s'} if shallow else set()
    if model in SHALLOW_SUBGRID_MODELS:
        extra_names.add('stage_relative_m')
    if metadata['bed_identity'] != bed['identity_sha256'] or metadata['geometry_identity'] != geometry['identity_sha256'] or metadata['forcing_identity'] != forcing['identity_sha256'] or (metadata['interval_count'] != steps) or (solver['status'] != 'completed') or (solver['failure'] is not None) or (solver['source_identity'] != bed['identity_sha256']) or (solver['forcing_identity'] != forcing['identity_sha256']) or (abs(solver['committed_time_s'] - steps * dt) > 1e-09) or (solver['requested_time_s'] != steps * dt) or (set(arrays) != {'time_s', 'depth_m', 'initial_depth_m', 'ledger', 'final_internal_q_m3_s', 'final_boundary_q_m3_s'} | extra_names):
        raise ValueError('fine complete states binding mismatch')
    if arrays['depth_m'].shape != (steps + 1, *shape) or arrays['time_s'].shape != (steps + 1,) or _i116_np.any(arrays['depth_m'] < 0) or (not _i116_np.allclose(arrays['time_s'], _i116_np.arange(steps + 1) * dt, rtol=0, atol=1e-09)) or (not _i116_np.array_equal(arrays['initial_depth_m'], arrays['depth_m'][0])):
        raise ValueError('fine complete snapshot time/depth mismatch')
    expected_shapes = dict(time_s=(steps + 1,), depth_m=(steps + 1, *shape), initial_depth_m=shape, ledger=(steps + 1, 5), final_internal_q_m3_s=(len(geometry['arrays']['face_left']),), final_boundary_q_m3_s=(len(geometry['arrays']['boundary_cell']),))
    if shallow and (solver.get('schema') != model or solver.get('hydraulic_model') != model):
        raise ValueError('shallow-water saved solver model mismatch')
    if shallow:
        expected_shapes.update(momentum_x_m2_s=(steps + 1, *shape), momentum_z_m2_s=(steps + 1, *shape))
        if _i116_np.any(arrays['momentum_x_m2_s'][0] != 0) or _i116_np.any(arrays['momentum_z_m2_s'][0] != 0):
            raise ValueError('shallow-water initial momentum mismatch')
    if model in SHALLOW_SUBGRID_MODELS:
        expected_shapes['stage_relative_m'] = (steps + 1, *shape)
        for stage, depth in zip(arrays['stage_relative_m'], arrays['depth_m']):
            _near(_i116_np.maximum(stage.ravel()[:, None] - geometry['arrays']['subcell_bed_relative_m'], 0).mean(axis=1).reshape(shape), depth, 'subgrid shallow V(stage)')
    if subgrid:
        factor = int(geometry['metadata']['spacing_m'])
        expected_shapes.update(stage_relative_m=(steps + 1, *shape), final_internal_segment_q_m3_s=(expected_shapes['final_internal_q_m3_s'][0], factor), final_boundary_segment_q_m3_s=(expected_shapes['final_boundary_q_m3_s'][0], factor))
        if solver.get('schema') != SUBGRID_MODEL or solver.get('hydraulic_model') != SUBGRID_MODEL:
            raise ValueError('subgrid saved solver physical model mismatch')
        for stage, depth in zip(arrays['stage_relative_m'], arrays['depth_m']):
            implied = _i116_np.maximum(stage.ravel()[:, None] - geometry['arrays']['subcell_bed_relative_m'], 0).mean(axis=1).reshape(shape)
            _near(implied, depth, 'subgrid V(stage) exact mean depth')
        for kind in ('internal', 'boundary'):
            _near(arrays[f'final_{kind}_segment_q_m3_s'].sum(axis=1), arrays[f'final_{kind}_q_m3_s'], 'subgrid final segment discharge sum')
    if any((values.dtype != _i116_np.float64 or values.shape != expected_shapes[name] for name, values in arrays.items())):
        raise ValueError('fine states exact dtype/shape mismatch')
    budget = _x90_SurfaceBudget(**solver['budget'])
    _x91_validate_budget(budget)
    if _i116_np.any(arrays['depth_m'] > budget.max_depth_m) or type(solver['substeps']) is not int or (not 0 < solver['substeps'] <= budget.max_substeps) or (budget.max_wall_s > 1800) or (budget.max_bytes > SINGLE_DOMAIN_FINE_IO_MAX_BYTES) or (budget.max_cells > 65536) or (type(solver['face_evaluations']) is not int) or (not 0 < solver['face_evaluations'] <= budget.max_face_evaluations) or (type(solver['wall_s']) not in (int, float)) or (not 0 <= solver['wall_s'] <= 1800):
        raise ValueError('fine saved solver depth/work budget mismatch')
    volumes = arrays['depth_m'].sum(axis=(1, 2)) * geometry['metadata']['spacing_m'] ** 2
    ledger = arrays['ledger']
    if ledger.shape != (steps + 1, 5) or _i116_np.any(ledger[:, :3] < 0) or _i116_np.any(_i116_np.diff(ledger[:, :3], axis=0) < -1e-08):
        raise ValueError('fine cumulative surface ledger mismatch')
    _near(ledger[:, 3], volumes, 'surface snapshots')
    expected_supply = _i116_np.r_[0.0, _i116_np.cumsum(forcing['arrays']['outflow_volume_m3'].sum(axis=1))]
    _near(ledger[:, 0], expected_supply, 'surface supplied runoff exactly once')
    residual = volumes - volumes[0] - ledger[:, 0] - ledger[:, 1] + ledger[:, 2]
    _near(ledger[:, 4], residual, 'surface saved residual')
    _near(residual, _i116_np.zeros_like(residual), 'surface whole budget')
    soil = sum((forcing['arrays'][name] for name in ('soil_mm', 'fast_mm', 'slow_mm'))) * geometry['metadata']['spacing_m'] ** 2 / 1000
    total = soil.sum(axis=1) + volumes
    rain = _i116_np.r_[0.0, _i116_np.cumsum(forcing['arrays']['rain_volume_m3'].sum(axis=1))]
    et = _i116_np.r_[0.0, _i116_np.cumsum(forcing['arrays']['et_volume_m3'].sum(axis=1))]
    _near(total - total[0], rain - et + ledger[:, 1] - ledger[:, 2], 'four-compartment whole budget')
    return True

def validate_fine_momentum(packet, *, bed, geometry, forcing, states, interval, interval_packet):
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _x90_SurfaceBudget
    from terrain_pipeline.surface_hydraulics import limited_inertial_fluxes as _x92_limited_inertial_fluxes
    from terrain_pipeline.surface_hydraulics import _net_flux as _x93_net_flux
    arrays, metadata = _single_domain_fine_io_check(packet, 'single-domain-fine-momentum-v1')
    if geometry['metadata'].get('hydraulic_model') in SHALLOW_MODELS:
        return _validate_shallow_momentum(arrays, metadata, bed, geometry, forcing, states, interval, interval_packet)
    fields = {'depth_before_m', 'depth_after_m', 'forcing_m3_s', 'tailwater_m', 'internal_q_before_m3_s', 'internal_q_after_m3_s', 'boundary_q_before_m3_s', 'boundary_q_after_m3_s'}
    subgrid = geometry['metadata'].get('hydraulic_model') == SUBGRID_MODEL
    shallow = geometry['metadata'].get('hydraulic_model') == SHALLOW_MODEL
    if subgrid:
        fields |= {f'{kind}_segment_q_{endpoint}_m3_s' for kind in ('internal', 'boundary') for endpoint in ('before', 'after')}
    if set(arrays) != fields:
        raise ValueError('fine exact first-substep momentum fields required')
    cells = bed['arrays']['bed_center_m'].size
    faces, boundaries = (len(geometry['arrays']['face_left']), len(geometry['arrays']['boundary_cell']))
    for name, values in arrays.items():
        count = boundaries if name.startswith('boundary_') or name == 'tailwater_m' else faces if name.startswith('internal_') else cells
        shape = (count, int(geometry['metadata']['spacing_m'])) if '_segment_' in name else (count,)
        if values.dtype != _i116_np.float64 or values.shape != shape:
            raise ValueError('fine momentum exact array shape/type mismatch')
    dt, cadence = (metadata['dt_s'], forcing['metadata']['dt_s'])
    budget = _x90_SurfaceBudget(**states['metadata']['solver_metadata']['budget'])
    if metadata['bed_identity'] != bed['identity_sha256'] or metadata['geometry_identity'] != geometry['identity_sha256'] or metadata['forcing_identity'] != forcing['identity_sha256'] or (type(metadata['interval']) is not int) or (metadata['interval'] != interval) or (abs(metadata['time_start_s'] - interval * cadence) > 1e-09) or (type(dt) not in (int, float)) or (not 0 < dt <= budget.max_dt_s):
        raise ValueError('fine sampled momentum time/source mismatch')
    for name in ('depth_before_m', 'internal_q_before_m3_s', 'boundary_q_before_m3_s'):
        if not _i116_np.array_equal(arrays[name], interval_packet['arrays'][name]):
            raise ValueError('fine sampled momentum interval endpoint mismatch')
    _near(arrays['forcing_m3_s'], forcing['arrays']['local_q_m3_s'][interval], 'sampled runoff Q')
    _near(arrays['tailwater_m'], forcing['arrays']['boundary_stage_m'][interval], 'sampled tailwater')
    kinds, crest = (geometry['arrays']['boundary_kind'], geometry['arrays']['boundary_crest_m'])
    exterior = _i116_np.where(kinds == 1, crest, arrays['tailwater_m'])
    if subgrid:
        pass
        g = geometry['arrays']
        stage = storage_stages(arrays['depth_before_m'], g['subcell_bed_relative_m'], g['subcell_prefix_relative_m'])
        flow_depth = _i116_np.maximum(_i116_np.maximum(stage[g['face_left']], stage[g['face_right']])[:, None] - g['face_segment_crest_relative_m'], 0)
        boundary_depth = _i116_np.maximum(arrays['tailwater_m'][:, None] - geometry['metadata']['hydraulic_datum_m'] - g['boundary_segment_crest_relative_m'], 0)
        deepest = max(float(flow_depth.max(initial=0)), float(boundary_depth[kinds != 0].max(initial=0)))
    else:
        deepest = max(float(arrays['depth_before_m'].max()), float(_i116_np.maximum(exterior - crest, 0)[kinds != 0].max(initial=0)))
    cfl = budget.inertial_cfl * geometry['metadata']['spacing_m'] / 2 / _i116_math.sqrt(budget.gravity_m_s2 * deepest) if deepest else _i116_math.inf
    if dt > cfl + 1e-12:
        raise ValueError('fine sampled momentum gravity CFL mismatch')
    if subgrid:
        internal_segments, boundary_segments, limiter = _segment_momentum_witness(geometry, arrays['depth_before_m'], arrays['internal_segment_q_before_m3_s'], arrays['boundary_segment_q_before_m3_s'], arrays['tailwater_m'], arrays['forcing_m3_s'], dt, budget, stage)
        for kind, expected in (('internal', internal_segments), ('boundary', boundary_segments)):
            _near(arrays[f'{kind}_segment_q_after_m3_s'], expected, 'subgrid sampled segment momentum')
            for endpoint in ('before', 'after'):
                _near(arrays[f'{kind}_segment_q_{endpoint}_m3_s'].sum(axis=1), arrays[f'{kind}_q_{endpoint}_m3_s'], 'subgrid sampled total Q')
            if not _i116_np.array_equal(arrays[f'{kind}_segment_q_before_m3_s'], interval_packet['arrays'][f'{kind}_segment_q_before_m3_s']):
                raise ValueError('subgrid sampled segment checkpoint continuity mismatch')
        internal, boundary = (internal_segments.sum(axis=1), boundary_segments.sum(axis=1))
    else:
        internal, boundary, limiter = _x92_limited_inertial_fluxes(geometry, arrays['depth_before_m'], arrays['internal_q_before_m3_s'], arrays['boundary_q_before_m3_s'], arrays['tailwater_m'], arrays['forcing_m3_s'], dt, budget)
    _near(arrays['internal_q_after_m3_s'], internal, 'sampled momentum internal Q')
    _near(arrays['boundary_q_after_m3_s'], boundary, 'sampled momentum boundary Q')
    expected = arrays['depth_before_m'] + dt * (arrays['forcing_m3_s'] + _x93_net_flux(geometry, internal, boundary)) / geometry['metadata']['spacing_m'] ** 2
    _near(arrays['depth_after_m'], expected, 'sampled momentum water depth')
    if metadata['limiter'] != limiter:
        raise ValueError('fine sampled momentum donor limiter mismatch')
    return True

def _saved_flux_divergence(geometry, internal, boundary):
    arrays = geometry['arrays']
    result = _i116_np.zeros((geometry['arrays']['H2_m'].size, internal.shape[1]))
    _i116_np.add.at(result, arrays['face_left'], -internal)
    _i116_np.add.at(result, arrays['face_right'], internal)
    _i116_np.add.at(result, arrays['boundary_cell'], -boundary)
    return result

def _validate_shallow_momentum(arrays, metadata, bed, geometry, forcing, states, interval, interval_packet):
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _x90_SurfaceBudget
    cells = bed['arrays']['bed_center_m'].size
    faces, boundaries = (len(geometry['arrays']['face_left']), len(geometry['arrays']['boundary_cell']))
    shapes = dict(state_before=(cells, 3), state_predictor=(cells, 3), state_after=(cells, 3), forcing_m3_s=(cells,), tailwater_m=(boundaries,), manning_momentum_change=(cells, 2))
    canonical_manning = geometry['metadata'].get('hydraulic_model') == SHALLOW_SUBGRID_MANNING_MODEL
    if canonical_manning:
        shapes['manning_inverse_depth_third_mean'] = (cells,)
    for rk in (1, 2):
        shapes.update({f'rk{rk}_internal_flux': (faces, 3), f'rk{rk}_boundary_flux': (boundaries, 3), f'rk{rk}_bed_source': (cells, 3)})
    if set(arrays) != set(shapes) or any((value.dtype != _i116_np.float64 or value.shape != shapes[name] for name, value in arrays.items())):
        raise ValueError('shallow exact sampled momentum layout mismatch')
    dt, cadence = (metadata['dt_s'], forcing['metadata']['dt_s'])
    budget = _x90_SurfaceBudget(**states['metadata']['solver_metadata']['budget'])
    if metadata.get('hydraulic_model') != geometry['metadata'].get('hydraulic_model') or metadata['bed_identity'] != bed['identity_sha256'] or metadata['geometry_identity'] != geometry['identity_sha256'] or (metadata['forcing_identity'] != forcing['identity_sha256']) or (type(metadata['interval']) is not int) or (metadata['interval'] != interval) or (abs(metadata['time_start_s'] - interval * cadence) > 1e-09) or (type(dt) not in (int, float)) or (not 0 < dt <= min(cadence, budget.max_dt_s)):
        raise ValueError('shallow sampled momentum model/time/source mismatch')
    before, predictor, after = (arrays[name] for name in ('state_before', 'state_predictor', 'state_after'))
    if any((_i116_np.any(value[:, 0] < 0) or _i116_np.any(value[:, 0] > budget.max_depth_m) for value in (before, predictor, after))):
        raise ValueError('shallow sampled depth range mismatch')
    _near(before[:, 0], interval_packet['arrays']['depth_before_m'], 'shallow first substep depth')
    _near(before[:, 1:], interval_packet['arrays']['momentum_before'], 'shallow first substep momentum')
    _near(arrays['forcing_m3_s'], forcing['arrays']['local_q_m3_s'][interval], 'shallow sampled runoff')
    _near(arrays['tailwater_m'], forcing['arrays']['boundary_stage_m'][interval], 'shallow sampled tailwater')
    spacing = geometry['metadata']['spacing_m']
    rhs = []
    for rk in (1, 2):
        source = arrays[f'rk{rk}_bed_source']
        if _i116_np.any(source[:, 0] != 0):
            raise ValueError('shallow bed source must not create water')
        flux = _saved_flux_divergence(geometry, arrays[f'rk{rk}_internal_flux'], arrays[f'rk{rk}_boundary_flux']) / spacing + source
        flux[:, 0] += arrays['forcing_m3_s'] / spacing ** 2
        rhs.append(flux)
        if _i116_np.any(arrays[f'rk{rk}_boundary_flux'][geometry['arrays']['boundary_kind'] == 0, 0] != 0):
            raise ValueError('shallow closed wall sampled mass flux')
    _near(predictor, before + dt * rhs[0], 'shallow SSPRK2 predictor')
    undamped = 0.5 * before + 0.5 * (predictor + dt * rhs[1])
    _near(after[:, 0], undamped[:, 0], 'shallow SSPRK2 mass endpoint')
    expected_momentum = undamped[:, 1:].copy()
    wet = undamped[:, 0] > 0
    if canonical_manning:
        stage = _saved_storage_stage(undamped[:, 0], geometry['arrays']['subcell_bed_relative_m'])
        subdepth = _i116_np.maximum(stage[:, None] - geometry['arrays']['subcell_bed_relative_m'], 0)
        inverse = _i116_np.zeros_like(subdepth)
        _i116_np.power(subdepth, -1 / 3, out=inverse, where=subdepth > 0)
        factor = inverse.mean(axis=1)
        _near(arrays['manning_inverse_depth_third_mean'], factor, 'canonical Manning wet-subcell integral')
        hsquared = undamped[:, 0] ** 2
        denominator = hsquared + dt * budget.gravity_m_s2 * budget.roughness_s_m_third ** 2 * _i116_np.linalg.norm(expected_momentum, axis=1) * factor
        expected_momentum = _i116_np.divide(expected_momentum * hsquared[:, None], denominator[:, None], out=_i116_np.zeros_like(expected_momentum), where=denominator[:, None] > 0)
    else:
        hpower = undamped[wet, 0] ** (7 / 3)
        denominator = hpower + dt * budget.gravity_m_s2 * budget.roughness_s_m_third ** 2 * _i116_np.linalg.norm(expected_momentum[wet], axis=1)
        expected_momentum[wet] = _i116_np.divide(expected_momentum[wet] * hpower[:, None], denominator[:, None], out=_i116_np.zeros_like(expected_momentum[wet]), where=denominator[:, None] > 0)
    _near(after[:, 1:], expected_momentum, 'shallow implicit Manning momentum')
    _near(arrays['manning_momentum_change'], after[:, 1:] - undamped[:, 1:], 'shallow Manning impulse witness')
    velocity = _i116_np.divide(before[:, 1:], before[:, 0, None], out=_i116_np.zeros_like(before[:, 1:]), where=before[:, 0, None] > 0)
    speed = float((abs(velocity).sum(axis=1) + 2 * _i116_np.sqrt(budget.gravity_m_s2 * before[:, 0])).max(initial=0))
    if geometry['metadata'].get('hydraulic_model') in SHALLOW_SUBGRID_MODELS:
        stage = _saved_storage_stage(before[:, 0], geometry['arrays']['subcell_bed_relative_m'])
        deepest = _i116_np.maximum(stage - geometry['arrays']['subcell_bed_relative_m'][:, 0], 0)
        speed = max(speed, float((abs(velocity).sum(axis=1) + 2 * _i116_np.sqrt(budget.gravity_m_s2 * deepest)).max(initial=0)))
    boundary_bed = _i116_np.maximum(geometry['arrays']['H2_m'].ravel()[geometry['arrays']['boundary_cell']], geometry['arrays']['boundary_crest_m'])
    if geometry['metadata'].get('hydraulic_model') in SHALLOW_SUBGRID_MODELS:
        boundary_bed = _i116_np.maximum(geometry['arrays']['boundary_segment_crest_relative_m'].min(axis=1) + geometry['metadata']['hydraulic_datum_m'], geometry['arrays']['boundary_crest_m'])
    exterior_stage = _i116_np.where(geometry['arrays']['boundary_kind'] == 1, boundary_bed, arrays['tailwater_m'])
    external_depth = _i116_np.maximum(exterior_stage - boundary_bed, 0)
    speed = max(speed, float((2 * _i116_np.sqrt(budget.gravity_m_s2 * external_depth[geometry['arrays']['boundary_kind'] != 0])).max(initial=0)))
    if dt > budget.inertial_cfl * spacing / max(speed, 1e-12) + 1e-12:
        raise ValueError('shallow sampled advective gravity CFL mismatch')
    return True

def _saved_storage_stage(depth, subbed):
    count = subbed.shape[1]
    prefix = _i116_np.cumsum(subbed, axis=1)
    candidate = (depth[:, None] * count + prefix) / _i116_np.arange(1, count + 1)
    valid = candidate >= subbed
    index = valid.sum(axis=1) - 1
    return candidate[_i116_np.arange(len(depth)), index]

def validate_fine_interval(packet, *, bed, geometry, forcing, interval, previous=None):
    from terrain_pipeline.surface_hydraulics import _net_flux as _x93_net_flux
    arrays, metadata = _single_domain_fine_io_check(packet, 'single-domain-fine-interval-v1')
    shape = bed['arrays']['bed_center_m'].shape
    cells, faces = (_i116_math.prod(shape), len(geometry['arrays']['face_left']))
    boundaries = len(geometry['arrays']['boundary_cell'])
    expected_shapes = {name: (faces if name.startswith('internal_') else boundaries if name.startswith('boundary_') else cells,) for name in INTERVAL_ARRAYS}
    subgrid = geometry['metadata'].get('hydraulic_model') == SUBGRID_MODEL
    shallow = geometry['metadata'].get('hydraulic_model') in SHALLOW_MODELS
    if subgrid:
        factor = int(geometry['metadata']['spacing_m'])
        for kind, count in (('internal', faces), ('boundary', boundaries)):
            expected_shapes[f'{kind}_segment_transfer_m3'] = (count, factor)
            for endpoint in ('before', 'after'):
                expected_shapes[f'{kind}_segment_q_{endpoint}_m3_s'] = (count, factor)
    if shallow:
        expected_shapes.update(momentum_before=(cells, 2), momentum_after=(cells, 2), internal_momentum_transfer=(faces, 2), boundary_momentum_transfer=(boundaries, 2), bed_momentum_change=(cells, 2), manning_momentum_change=(cells, 2))
    if set(arrays) != set(expected_shapes) or any((arrays[name].shape != expected_shapes[name] or arrays[name].dtype != _i116_np.float64 for name in arrays)):
        raise ValueError('fine interval exact array layout mismatch')
    dt = forcing['metadata']['dt_s']
    if metadata['bed_identity'] != bed['identity_sha256'] or metadata['geometry_identity'] != geometry['identity_sha256'] or metadata['forcing_identity'] != forcing['identity_sha256'] or (type(metadata['interval']) is not int) or (metadata['interval'] != interval) or (abs(metadata['time_start_s'] - interval * dt) > 1e-09) or (abs(metadata['time_end_s'] - (interval + 1) * dt) > 1e-09):
        raise ValueError('fine interval time/source binding mismatch')
    if _i116_np.any(arrays['depth_before_m'] < 0) or _i116_np.any(arrays['depth_after_m'] < 0):
        raise ValueError('fine interval negative water')
    if previous is not None:
        for name in ('depth', 'internal_q', 'boundary_q'):
            unit = 'm' if name == 'depth' else 'm3_s'
            if not _i116_np.array_equal(arrays[f'{name}_before_{unit}'], previous['arrays'][f'{name}_after_{unit}']):
                raise ValueError('fine interval exact depth/momentum continuity mismatch')
    elif interval == 0 and any((_i116_np.any(arrays[name] != 0) for name in ('internal_q_before_m3_s', 'boundary_q_before_m3_s'))):
        raise ValueError('fine declared initial zero momentum mismatch')
    _near(arrays['forcing_volume_m3'], forcing['arrays']['outflow_volume_m3'][interval], 'complete runoff forcing')
    change = geometry['metadata']['spacing_m'] ** 2 * (arrays['depth_after_m'] - arrays['depth_before_m'])
    _near(change, arrays['forcing_volume_m3'] + _x93_net_flux(geometry, arrays['internal_transfer_m3'], arrays['boundary_transfer_m3']), 'signed face cell continuity')
    if _i116_np.any(arrays['boundary_transfer_m3'][geometry['arrays']['boundary_kind'] == 0] != 0):
        raise ValueError('fine closed exterior transfer')
    closed = geometry['arrays']['boundary_kind'] == 0
    if _i116_np.any(arrays['boundary_q_before_m3_s'][closed] != 0) or _i116_np.any(arrays['boundary_q_after_m3_s'][closed] != 0):
        raise ValueError('fine closed exterior endpoint discharge')
    if subgrid:
        for kind in ('internal', 'boundary'):
            _near(arrays[f'{kind}_segment_transfer_m3'].sum(axis=1), arrays[f'{kind}_transfer_m3'], 'subgrid signed segment transfer sum')
            for endpoint in ('before', 'after'):
                _near(arrays[f'{kind}_segment_q_{endpoint}_m3_s'].sum(axis=1), arrays[f'{kind}_q_{endpoint}_m3_s'], 'subgrid segment endpoint discharge sum')
            before = arrays[f'{kind}_segment_q_before_m3_s']
            if previous is None and _i116_np.any(before != 0) or (previous is not None and (not _i116_np.array_equal(before, previous['arrays'][f'{kind}_segment_q_after_m3_s']))):
                raise ValueError('subgrid exact segment momentum chain mismatch')
        if _i116_np.any(arrays['boundary_segment_transfer_m3'][closed] != 0):
            raise ValueError('subgrid closed boundary segment transfer')
    if shallow:
        if metadata.get('hydraulic_model') != geometry['metadata'].get('hydraulic_model'):
            raise ValueError('shallow interval model binding mismatch')
        expected_before = previous['arrays']['momentum_after'] if previous is not None else _i116_np.zeros((cells, 2))
        _near(arrays['momentum_before'], expected_before, 'shallow momentum continuity')
        momentum_change = _saved_flux_divergence(geometry, arrays['internal_momentum_transfer'], arrays['boundary_momentum_transfer']) / geometry['metadata']['spacing_m'] ** 2
        momentum_change += arrays['bed_momentum_change'] + arrays['manning_momentum_change']
        _near(arrays['momentum_after'] - arrays['momentum_before'], momentum_change, 'shallow interval momentum closure')
        if _i116_np.any(arrays['boundary_transfer_m3'][closed] != 0):
            raise ValueError('shallow closed boundary transfer')
    return True

def _headers(headers):
    if 'manifest' not in headers or len(headers) > 64:
        raise ValueError('fine exact bounded archive headers required')
    for name, (shape, dtype) in headers.items():
        if name == 'manifest':
            if dtype != _i116_np.uint8 or len(shape) != 1 or _i116_math.prod(shape) > 1048576:
                raise ValueError('fine bounded manifest allocation')
        elif dtype not in (_i116_np.dtype('float64'), _i116_np.dtype('int64'), _i116_np.dtype('bool')) or _i116_math.prod(shape) > 2000000:
            raise ValueError('fine bounded numeric allocation')

def _single_domain_fine_io_load(record, validator):
    from terrain_pipeline.common_infra import load_bundle as _i116_load_bundle
    result = _i116_load_bundle(record['path'], expected_sha256=record['expected_sha256'], max_bytes=SINGLE_DOMAIN_FINE_IO_MAX_BYTES, header_validator=_headers, validator=validator)
    if result['identity_sha256'] != record['expected_identity']:
        raise ValueError('fine external content identity mismatch')
    return result

def save_fine_run(path, result, *, bed_record, code_sha256, code_records=None):
    from terrain_pipeline.common_infra import save_bundle as _i116_save_bundle
    from terrain_pipeline.common_infra import file_sha256 as _i116_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i116_publish_bytes
    root = _i116_Path(path).resolve()
    root.mkdir(parents=True, exist_ok=False)
    bed, geometry, forcing, states = (result[name] for name in ('bed', 'geometry', 'forcing', 'states'))
    records = {}
    validators = dict(geometry=lambda item: single_domain_fine_io_validate_fine_geometry(item, bed=bed), forcing=lambda item: validate_fine_forcing(item, bed=bed), states=lambda item: validate_fine_states(item, bed=bed, geometry=geometry, forcing=forcing))
    for role in ('geometry', 'forcing', 'states'):
        target = root / (role + '.npz')
        _i116_save_bundle(target, result[role], validator=validators[role])
        records[role] = dict(path=str(target), expected_sha256=_i116_file_sha256(target), expected_identity=result[role]['identity_sha256'])
    interval_records = []
    previous = None
    for interval, packet in enumerate(result['intervals']):
        target = root / f'interval-{interval:03d}.npz'
        _i116_save_bundle(target, packet, validator=lambda item: validate_fine_interval(item, bed=bed, geometry=geometry, forcing=forcing, interval=interval, previous=previous))
        interval_records.append(dict(path=str(target), expected_sha256=_i116_file_sha256(target), expected_identity=packet['identity_sha256']))
        previous = packet
    momentum_records = []
    for interval, packet in enumerate(result['momenta']):
        target = root / f'momentum-{interval:03d}.npz'
        _i116_save_bundle(target, packet, validator=lambda item: validate_fine_momentum(item, bed=bed, geometry=geometry, forcing=forcing, states=states, interval=interval, interval_packet=result['intervals'][interval]))
        momentum_records.append(dict(path=str(target), expected_sha256=_i116_file_sha256(target), expected_identity=packet['identity_sha256']))
    if sum((target.stat().st_size for target in root.iterdir() if target.is_file())) > 2147483648:
        raise ValueError('fine run output exceeds 2 GiB')
    index = dict(schema='single-domain-fine-run-index-v1', bed_record=bed_record, **records, intervals=interval_records, momenta=momentum_records, code_sha256=code_sha256, hydraulic_ready=False, natural_outlet_verified=False, publishable=False, limitations=result['limitations'])
    if code_records is not None:
        _validate_code_records(code_sha256, code_records, root.parent)
        index['code_records'] = code_records
    target = root / 'index.json'
    _i116_publish_bytes(target, (_i116_json.dumps(index, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8'))
    return dict(path=str(target), expected_sha256=_i116_file_sha256(target))

def _validate_code_records(code_sha256, code_records, stage_root):
    from terrain_pipeline.common_infra import file_sha256 as _i116_file_sha256
    stage_root = stage_root.resolve(strict=True)
    snapshot_root = (stage_root / 'execution-code').resolve(strict=True)
    if not snapshot_root.is_relative_to(stage_root):
        raise ValueError('fine immutable implementation snapshot root escaped stage')
    if not isinstance(code_records, dict) or set(code_records) != set(code_sha256):
        raise ValueError('fine frozen code record names mismatch')
    for name, digest in code_sha256.items():
        record = code_records[name]
        expected_path = (snapshot_root / name).resolve(strict=True)
        path = _i116_Path(record['path']).resolve(strict=True)
        if not expected_path.is_relative_to(snapshot_root) or path != expected_path or record['expected_sha256'] != digest or (_i116_file_sha256(path) != digest):
            raise ValueError('fine immutable implementation snapshot pin mismatch')

def load_fine_run(path, *, expected_sha256, bed, repository_root=None):
    from terrain_pipeline.common_infra import file_sha256 as _i116_file_sha256
    from terrain_pipeline.td_native_weather_storage_io import _json as _i116__json
    from terrain_pipeline.td_native_weather_storage_io import _layout as _i116__layout
    index = _i116__json(dict(path=str(path), expected_sha256=expected_sha256))
    root = _i116_Path(path).resolve().parent
    if index.get('schema') != 'single-domain-fine-run-index-v1' or any((index.get(name) is not False for name in FLAGS)):
        raise ValueError('fine run index schema/flags mismatch')
    if index['bed_record']['expected_identity'] != bed['identity_sha256'] or _i116_file_sha256(index['bed_record']['path']) != index['bed_record']['expected_sha256']:
        raise ValueError('fine external bed binding mismatch')
    code_root = _i116_Path(repository_root).resolve() if repository_root is not None else _i116_Path(__file__).resolve().parents[1]
    if not isinstance(index.get('code_sha256'), dict) or not index['code_sha256']:
        raise ValueError('fine frozen implementation pins required')
    if 'code_records' in index:
        _validate_code_records(index['code_sha256'], index['code_records'], root.parent)
    else:
        for name, digest in index['code_sha256'].items():
            relative = _i116_Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('implementation code path escapes repository')
            target = (code_root / relative).resolve()
            if not target.is_relative_to(code_root):
                raise ValueError('implementation code path escapes repository')
            current = _i116_file_sha256(target) if target.is_file() else None
            from terrain_pipeline.common_infra import published_algorithm_matches
            if not published_algorithm_matches('single_domain_fine', {name: digest}, {name: current} if current is not None else {}):
                raise ValueError('historical implementation is not registered')
    for role in ('geometry', 'forcing', 'states'):
        _i116__layout(index[role], root / (role + '.npz'))
    geometry = _single_domain_fine_io_load(index['geometry'], lambda item: single_domain_fine_io_validate_fine_geometry(item, bed=bed))
    forcing = _single_domain_fine_io_load(index['forcing'], lambda item: validate_fine_forcing(item, bed=bed))
    states = _single_domain_fine_io_load(index['states'], lambda item: validate_fine_states(item, bed=bed, geometry=geometry, forcing=forcing))
    steps = forcing['metadata']['steps']
    if len(index['intervals']) != steps or len(index['momenta']) != steps:
        raise ValueError('fine complete interval/momentum coverage required')
    previous = None
    for interval, record in enumerate(index['intervals']):
        _i116__layout(record, root / f'interval-{interval:03d}.npz')
        packet = _single_domain_fine_io_load(record, lambda item: validate_fine_interval(item, bed=bed, geometry=geometry, forcing=forcing, interval=interval, previous=previous))
        momentum_record = index['momenta'][interval]
        _i116__layout(momentum_record, root / f'momentum-{interval:03d}.npz')
        _single_domain_fine_io_load(momentum_record, lambda item: validate_fine_momentum(item, bed=bed, geometry=geometry, forcing=forcing, states=states, interval=interval, interval_packet=packet))
        if not _i116_np.array_equal(packet['arrays']['depth_before_m'], states['arrays']['depth_m'][interval].ravel()) or not _i116_np.array_equal(packet['arrays']['depth_after_m'], states['arrays']['depth_m'][interval + 1].ravel()):
            raise ValueError('fine interval/snapshot original depth mismatch')
        if geometry['metadata'].get('hydraulic_model') in SHALLOW_MODELS:
            for endpoint, number in (('before', interval), ('after', interval + 1)):
                momentum = _i116_np.column_stack((states['arrays']['momentum_x_m2_s'][number].ravel(), states['arrays']['momentum_z_m2_s'][number].ravel()))
                if not _i116_np.array_equal(packet['arrays']['momentum_' + endpoint], momentum):
                    raise ValueError('shallow interval/snapshot momentum endpoint mismatch')
        ledger = states['arrays']['ledger']
        actual_boundary_net = float(packet['arrays']['boundary_transfer_m3'].sum())
        _near(_i116_np.asarray(ledger[interval + 1, 2] - ledger[interval, 2] - ledger[interval + 1, 1] + ledger[interval, 1]), _i116_np.asarray(actual_boundary_net), 'exterior net vs gross ledger difference')
        previous = packet
    if not _i116_np.array_equal(previous['arrays']['internal_q_after_m3_s'], states['arrays']['final_internal_q_m3_s']) or not _i116_np.array_equal(previous['arrays']['boundary_q_after_m3_s'], states['arrays']['final_boundary_q_m3_s']):
        raise ValueError('fine final momentum endpoint mismatch')
    if geometry['metadata'].get('hydraulic_model') == SUBGRID_MODEL:
        for kind in ('internal', 'boundary'):
            if not _i116_np.array_equal(previous['arrays'][f'{kind}_segment_q_after_m3_s'], states['arrays'][f'final_{kind}_segment_q_m3_s']):
                raise ValueError('subgrid final segment checkpoint mismatch')
    if _i116_file_sha256(path) != expected_sha256:
        raise ValueError('fine run index changed during cold load')
    return dict(index=index, bed=bed, geometry=geometry, forcing=forcing, states=states, intervals_verified=steps, solver_advanced=False)
MAX_CELLS = 250000
STATIC = ('height_m', 'valid_mask', 'receiver', 'face_cells', 'boundary_cells')
ALGORITHM = 'native-dual-cell-support-v1'
SINGLE_DOMAIN_SURFACE_GEOMETRY_GEOMETRY_SEMANTICS = dict(bed_semantics='original native cell-centred samples, flat independent dual-cell supports; no incision', topology_semantics='all valid static D4 receiver links; shared indexed native-bed XYZ junctions; not actual hydraulic flow')
FRAME_SEMANTICS = dict(water_semantics='saved native cell bed + depth; all depth > 0 supports, without wet threshold', volume_semantics='projected triangle area times owning cell depth; compared with native raster area*depth', support_side_semantics='wet/dry and outer support perimeter walls; not certified natural river banks', limitation='piecewise constant discontinuous cell surfaces; no smoothed junction water surface or 3D hydraulic certification')

def _single_domain_surface_geometry_sha(value):
    if not isinstance(value, str) or _i117_re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('external SHA/identity invalid')

def _single_domain_surface_geometry_check(result, schema):
    from terrain_pipeline.common_infra import identity as _i117_identity
    arrays, metadata = (result['arrays'], result['metadata'])
    if metadata.get('schema') != schema or any((metadata.get(name) is not False for name in FLAGS)):
        raise ValueError('surface schema/certification invalid')
    semantics = SINGLE_DOMAIN_SURFACE_GEOMETRY_GEOMETRY_SEMANTICS if schema == 'single-domain-native-surface-geometry-v1' else FRAME_SEMANTICS
    if metadata.get('algorithm') != ALGORITHM or metadata.get('coordinates') != COORDINATES or any((metadata.get(name) != value for name, value in semantics.items())):
        raise ValueError('surface algorithm/coordinate/representation semantics invalid')
    if sum((value.nbytes for value in arrays.values())) > MAX_BYTES:
        raise ValueError('surface byte budget exceeded')
    if _i117_identity(arrays, metadata) != result['identity_sha256']:
        raise ValueError('surface identity mismatch')
    if any((not _i117_np.isfinite(value).all() for value in arrays.values())):
        raise ValueError('nonfinite surface array')
    return (arrays, metadata)

def _finish(arrays, metadata):
    from terrain_pipeline.common_infra import identity as _i117_identity
    from terrain_pipeline.common_infra import readonly as _i117_readonly
    if sum((value.nbytes for value in arrays.values())) > MAX_BYTES:
        raise ValueError('surface byte budget exceeded')
    return dict(arrays={name: _i117_readonly(value) for name, value in arrays.items()}, metadata=metadata, identity_sha256=_i117_identity(arrays, metadata))

def _native(arrays, metadata):
    height, valid, receiver = (arrays[name] for name in ('height_m', 'valid_mask', 'receiver'))
    shape = height.shape
    if height.dtype != _i117_np.float64 or height.ndim != 2 or min(shape) < 2 or (height.size > MAX_CELLS) or (valid.dtype != bool) or (valid.shape != shape) or (receiver.dtype != _i117_np.int64) or (receiver.shape != (height.size,)) or (not valid.any()) or (not _i117_np.isfinite(height).all()) or _i117_np.any(receiver[~valid.ravel()] != -1):
        raise ValueError('native bed/mask/receiver invalid')
    spacing, origin = (metadata['spacing_m'], metadata['origin_m_xz'])
    if type(spacing) not in (int, float) or not _i117_math.isfinite(spacing) or spacing <= 0 or (not isinstance(origin, list)) or (len(origin) != 2) or any((type(value) not in (int, float) or not _i117_math.isfinite(value) for value in origin)) or (metadata['grid_shape'] != list(shape)):
        raise ValueError('native metric coordinates invalid')
    ids = _i117_np.flatnonzero(valid).astype(_i117_np.int64)
    active = receiver[ids] >= 0
    targets = receiver[ids][active]
    if _i117_np.any(receiver < -1) or _i117_np.any(targets >= height.size) or (not valid.ravel()[targets].all()):
        raise ValueError('receiver leaves valid native support')
    sources = ids[active]
    if _i117_np.any(abs(sources // shape[1] - targets // shape[1]) + abs(sources % shape[1] - targets % shape[1]) != 1):
        raise ValueError('receiver must be D4')
    completed = _i117_np.zeros(height.size, bool)
    for start in ids:
        path = set()
        cell = int(start)
        while cell >= 0 and (not completed[cell]):
            if cell in path:
                raise ValueError('receiver cycle')
            path.add(cell)
            cell = int(receiver[cell])
        completed[list(path)] = True
    row, column = _i117_np.nonzero(valid[:, :-1] & valid[:, 1:])
    horizontal = _i117_np.column_stack((row * shape[1] + column, row * shape[1] + column + 1))
    row, column = _i117_np.nonzero(valid[:-1, :] & valid[1:, :])
    vertical = _i117_np.column_stack((row * shape[1] + column, (row + 1) * shape[1] + column))
    expected_faces = _i117_np.concatenate((horizontal, vertical)).astype(_i117_np.int64)
    faces = arrays['face_cells']
    if faces.dtype != _i117_np.int64 or faces.shape != expected_faces.shape or (not _i117_np.array_equal(faces[_i117_np.lexsort((faces[:, 1], faces[:, 0]))], expected_faces[_i117_np.lexsort((expected_faces[:, 1], expected_faces[:, 0]))])):
        raise ValueError('native D4 faces missing, duplicated or invalid')
    boundary = arrays['boundary_cells']
    if boundary.dtype != _i117_np.int64 or boundary.ndim != 1 or _i117_np.any(boundary < 0) or _i117_np.any(boundary >= height.size) or _i117_np.any(_i117_np.diff(boundary) <= 0) or (not valid.ravel()[boundary].all()):
        raise ValueError('engineering boundary cells invalid')
    xyz = _i117_np.column_stack((origin[0] + ids % shape[1] * spacing, height.ravel()[ids], origin[1] + ids // shape[1] * spacing))
    edges = _i117_np.searchsorted(ids, _i117_np.column_stack((sources, targets))).astype(_i117_np.int64)
    return (ids, xyz, edges)

def _quads(ids, heights, shape, spacing, origin):
    offsets = _i117_np.array([[-0.5, -0.5], [-0.5, 0.5], [0.5, 0.5], [0.5, -0.5]]) * spacing
    centres = _i117_np.column_stack((origin[0] + ids % shape[1] * spacing, origin[1] + ids // shape[1] * spacing))
    vertices = _i117_np.empty((len(ids), 4, 3), _i117_np.float64)
    vertices[:, :, 0] = centres[:, None, 0] + offsets[:, 0]
    vertices[:, :, 2] = centres[:, None, 1] + offsets[:, 1]
    vertices[:, :, 1] = heights[:, None]
    corners = _i117_np.arange(len(ids) * 4, dtype=_i117_np.int64).reshape(-1, 4)
    triangles = _i117_np.empty((len(ids) * 2, 3), _i117_np.int64)
    triangles[::2] = corners[:, [0, 1, 2]]
    triangles[1::2] = corners[:, [0, 2, 3]]
    return (vertices.reshape(-1, 3), triangles)

def _single_domain_surface_geometry_geometry_arrays(static, metadata):
    ids, xyz, edges = _native(static, metadata)
    bed, triangles = _quads(ids, xyz[:, 1], static['height_m'].shape, metadata['spacing_m'], metadata['origin_m_xz'])
    boundary = _i117_np.isin(ids, static['boundary_cells'])
    receiver = static['receiver'][ids]
    uphill = _i117_np.zeros(len(ids), bool)
    active = receiver >= 0
    uphill[active] = static['height_m'].ravel()[receiver[active]] > xyz[active, 1]
    return dict(static, node_cell_ids=ids, node_xyz_m=xyz, edge_node_indices=edges, node_engineering_boundary=boundary, node_internal_sink=(receiver < 0) & ~boundary, node_receiver_uphill=uphill, bed_vertices_xyz_m=bed, bed_triangles=triangles)

def build_geometry(hierarchy, *, source_hierarchy_sha256):
    from terrain_pipeline.basin_topology import validate_basin_hierarchy as _i117_validate_basin_hierarchy
    _i117_validate_basin_hierarchy(hierarchy)
    _single_domain_surface_geometry_sha(source_hierarchy_sha256)
    source = hierarchy['metadata']
    metadata = dict(schema='single-domain-native-surface-geometry-v1', algorithm=ALGORITHM, hierarchy_identity=hierarchy['identity_sha256'], source_hierarchy_sha256=source_hierarchy_sha256, source_identity=source['source_identity_sha256'], grid_shape=list(hierarchy['arrays']['height_m'].shape), spacing_m=source['spacing_m'], origin_m_xz=list(source['origin_m_xz']), coordinates=COORDINATES, **SINGLE_DOMAIN_SURFACE_GEOMETRY_GEOMETRY_SEMANTICS, candidate_bed_used=False, continuous_surface=False, **{name: False for name in FLAGS})
    arrays = _single_domain_surface_geometry_geometry_arrays({name: hierarchy['arrays'][name].copy() for name in STATIC}, metadata)
    result = _finish(arrays, metadata)
    validate_geometry(result)
    return result

def _equal_arrays(actual, expected):
    if set(actual) != set(expected):
        raise ValueError('surface array fields invalid')
    for name, value in expected.items():
        if actual[name].dtype != value.dtype or not _i117_np.array_equal(actual[name], value):
            raise ValueError('surface geometry/source mismatch: ' + name)

def validate_geometry(result):
    arrays, metadata = _single_domain_surface_geometry_check(result, 'single-domain-native-surface-geometry-v1')
    for name in ('hierarchy_identity', 'source_hierarchy_sha256', 'source_identity'):
        _single_domain_surface_geometry_sha(metadata[name])
    if metadata.get('candidate_bed_used') is not False or metadata.get('continuous_surface') is not False:
        raise ValueError('native bed representation invalid')
    _equal_arrays(arrays, _single_domain_surface_geometry_geometry_arrays({name: arrays[name] for name in STATIC}, metadata))
    return True

def _frame_arrays(geometry, depth):
    arrays, metadata = (geometry['arrays'], geometry['metadata'])
    shape = arrays['height_m'].shape
    ids = arrays['node_cell_ids']
    if depth.dtype != _i117_np.float64 or depth.shape != (len(ids),) or _i117_np.any(depth < 0) or (not _i117_np.isfinite(depth).all()):
        raise ValueError('native state depth invalid')
    wet = ids[depth > 0]
    levels = arrays['height_m'].ravel()[wet] + depth[depth > 0]
    vertices, triangles = _quads(wet, levels, shape, metadata['spacing_m'], metadata['origin_m_xz'])
    wet_mask = _i117_np.zeros(_i117_math.prod(shape), bool)
    wet_mask[wet] = True
    perimeter = []
    columns = shape[1]
    for index, cell in enumerate(wet):
        row, column = divmod(int(cell), columns)
        neighbors = (cell - 1 if column else -1, cell + columns if row + 1 < shape[0] else -1, cell + 1 if column + 1 < columns else -1, cell - columns if row else -1)
        for side, neighbor in enumerate(neighbors):
            if neighbor < 0 or not wet_mask[neighbor]:
                perimeter.append((index, side))
    side_vertices = _i117_np.empty((len(perimeter), 4, 3), _i117_np.float64)
    top = vertices.reshape(-1, 4, 3)
    for index, (wet_index, side) in enumerate(perimeter):
        first, second = (top[wet_index, side], top[wet_index, (side + 1) % 4])
        side_vertices[index] = [first, second, second, first]
        side_vertices[index, 2:, 1] = arrays['height_m'].ravel()[wet[wet_index]]
    corners = _i117_np.arange(len(perimeter) * 4, dtype=_i117_np.int64).reshape(-1, 4)
    side_triangles = _i117_np.empty((len(perimeter) * 2, 3), _i117_np.int64)
    side_triangles[::2] = corners[:, [0, 1, 2]]
    side_triangles[1::2] = corners[:, [0, 2, 3]]
    output = {name: value.copy() for name, value in arrays.items()}
    output.update(native_depth_m=depth.copy(), wet_cell_ids=wet, water_vertices_xyz_m=vertices, water_triangles=triangles, support_side_vertices_xyz_m=side_vertices.reshape(-1, 3), support_side_triangles=side_triangles)
    points = vertices[triangles][:, :, [0, 2]]
    delta1, delta2 = (points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    areas = abs(delta1[:, 0] * delta2[:, 1] - delta1[:, 1] * delta2[:, 0]) / 2
    triangle_volume = float(_i117_np.sum(areas * _i117_np.repeat(depth[depth > 0], 2), dtype=_i117_np.float64))
    full_depth = _i117_np.zeros(_i117_math.prod(shape), _i117_np.float64)
    full_depth[ids] = depth
    faces = arrays['face_cells']
    both_wet = wet_mask[faces].all(axis=1)
    level = arrays['height_m'].ravel() + full_depth
    steps = abs(level[faces[both_wet, 0]] - level[faces[both_wet, 1]])
    raster_volume = float(_i117_np.sum(depth, dtype=_i117_np.float64) * metadata['spacing_m'] ** 2)
    diagnostics = dict(wet_cell_count=int(len(wet)), represented_wet_cell_count=int(len(wet)), omitted_wet_cell_count=0, omitted_wet_volume_m3=0.0, wet_count_coverage_fraction=1.0, raster_volume_m3=raster_volume, triangulated_support_volume_m3=triangle_volume, volume_difference_m3=triangle_volume - raster_volume, represented_area_m2=float(_i117_np.sum(areas)), raster_wet_area_m2=float(len(wet) * metadata['spacing_m'] ** 2), max_wet_neighbor_surface_jump_m=float(steps.max(initial=0)), support_perimeter_segment_count=len(perimeter))
    if not _i117_math.isclose(triangle_volume, raster_volume, rel_tol=1e-10, abs_tol=1e-08):
        raise ValueError('triangulated native volume differs from raster storage')
    return (output, diagnostics)

def build_water_frame(geometry, page, *, source_page_sha256, state_index=1):
    from terrain_pipeline.basin_storage import validate_storage as _i117_validate_storage
    validate_geometry(geometry)
    _i117_validate_storage(page)
    _single_domain_surface_geometry_sha(source_page_sha256)
    if type(state_index) is not int or state_index not in (0, 1):
        raise ValueError('saved state_index must be 0 or 1')
    gmeta, pmeta = (geometry['metadata'], page['metadata'])
    if pmeta['hierarchy_identity'] != gmeta['hierarchy_identity']:
        raise ValueError('saved page hierarchy identity mismatch')
    for name in STATIC:
        if not _i117_np.array_equal(page['arrays'][name], geometry['arrays'][name]):
            raise ValueError('saved page native static mismatch: ' + name)
    if any((pmeta[name] != gmeta[name] for name in ('spacing_m', 'origin_m_xz'))):
        raise ValueError('saved page coordinate mismatch')
    depth = page['arrays']['depth_m'][state_index, geometry['arrays']['node_cell_ids']]
    arrays, diagnostics = _frame_arrays(geometry, depth)
    metadata = dict(schema='single-domain-saved-water-frame-v1', algorithm=ALGORITHM, geometry_identity=geometry['identity_sha256'], geometry_metadata=gmeta, source_page_sha256=source_page_sha256, source_page_identity=page['identity_sha256'], forcing_identity=pmeta['forcing_identity'], state_index=state_index, start_s=pmeta['start_s'], end_s=pmeta['end_s'], time_s=pmeta['start_s'] if state_index == 0 else pmeta['end_s'], water_generated=False, candidate_bed_used=False, continuous_surface=False, **FRAME_SEMANTICS, coordinates=COORDINATES, **diagnostics, **{name: False for name in FLAGS})
    result = _finish(arrays, metadata)
    validate_water_frame(result)
    return result

def validate_water_frame(result):
    arrays, metadata = _single_domain_surface_geometry_check(result, 'single-domain-saved-water-frame-v1')
    for name in ('geometry_identity', 'source_page_sha256', 'source_page_identity', 'forcing_identity'):
        _single_domain_surface_geometry_sha(metadata[name])
    if any((metadata.get(name) is not False for name in ('water_generated', 'candidate_bed_used', 'continuous_surface'))):
        raise ValueError('saved native frame semantics invalid')
    geometry_names = set(STATIC) | {'node_cell_ids', 'node_xyz_m', 'edge_node_indices', 'bed_vertices_xyz_m', 'bed_triangles', 'node_engineering_boundary', 'node_internal_sink', 'node_receiver_uphill'}
    geometry = dict(arrays={name: arrays[name] for name in geometry_names}, metadata=metadata['geometry_metadata'], identity_sha256=metadata['geometry_identity'])
    validate_geometry(geometry)
    state = metadata['state_index']
    if type(state) is not int or state not in (0, 1) or (not _i117_math.isfinite(metadata['start_s'])) or (metadata['end_s'] - metadata['start_s'] != 3600) or (metadata['time_s'] != (metadata['start_s'] if state == 0 else metadata['end_s'])):
        raise ValueError('saved frame time invalid')
    expected, diagnostics = _frame_arrays(geometry, arrays['native_depth_m'])
    _equal_arrays(arrays, expected)
    if any((metadata.get(name) != value for name, value in diagnostics.items())):
        raise ValueError('saved frame coverage/volume audit invalid')
    return True

def save_geometry(path, result):
    from terrain_pipeline.common_infra import save_bundle as _i117_save_bundle
    _i117_save_bundle(path, result, validator=validate_geometry)

def save_water_frame(path, result):
    from terrain_pipeline.common_infra import save_bundle as _i117_save_bundle
    _i117_save_bundle(path, result, validator=validate_water_frame)

def _single_domain_surface_geometry_load(path, expected_sha256, expected_identity, validator):
    from terrain_pipeline.common_infra import load_bundle as _i117_load_bundle
    _single_domain_surface_geometry_sha(expected_sha256)
    _single_domain_surface_geometry_sha(expected_identity)
    result = _i117_load_bundle(path, expected_sha256=expected_sha256, validator=validator, max_bytes=MAX_BYTES)
    if result['identity_sha256'] != expected_identity:
        raise ValueError('external surface identity mismatch')
    return result

def load_geometry(path, *, expected_sha256, expected_identity):
    return _single_domain_surface_geometry_load(path, expected_sha256, expected_identity, validate_geometry)

def load_water_frame(path, *, expected_sha256, expected_identity):
    return _single_domain_surface_geometry_load(path, expected_sha256, expected_identity, validate_water_frame)
