"""Consolidated channel_geometry implementations; numeric expressions preserved."""
from __future__ import annotations
from dataclasses import asdict as _i4_asdict
from dataclasses import dataclass as _i4_dataclass
import json as _i4_json
import math as _i4_math
import os as _i4_os
from pathlib import Path as _i4_Path
import tempfile as _i4_tempfile
import numpy as _i4_np
from dataclasses import asdict as _i0_asdict
from dataclasses import dataclass as _i0_dataclass
import json as _i0_json
import math as _i0_math
import os as _i0_os
from pathlib import Path as _i0_Path
import tempfile as _i0_tempfile
import numpy as _i0_np
from dataclasses import asdict as _i1_asdict
from dataclasses import dataclass as _i1_dataclass
import numpy as _i1_np
from scipy import sparse as _i1_sparse
from scipy.sparse.csgraph import dijkstra as _i1_dijkstra
from numba import njit as _i1_njit
from dataclasses import asdict as _i23_asdict
from dataclasses import dataclass as _i23_dataclass
import math as _i23_math
import numpy as _i23_np
from scipy.spatial import cKDTree as _i23_cKDTree
from dataclasses import asdict as _i41_asdict
import math as _i41_math
import numpy as _i41_np
from dataclasses import asdict as _i43_asdict
import math as _i43_math
import numpy as _i43_np
from dataclasses import asdict as _i34_asdict
import math as _i34_math
import numpy as _i34_np
from scipy.optimize import linprog as _i34_linprog
from scipy.sparse import coo_matrix as _i34_coo_matrix
import numpy as _i27_np
import warnings as _i27_warnings
from dataclasses import asdict as _i27_asdict
from scipy.optimize import linprog as _i27_linprog
from scipy.optimize import OptimizeWarning as _i27_OptimizeWarning
from scipy.sparse import coo_matrix as _i27_coo_matrix
from scipy.spatial import cKDTree as _i27_cKDTree
from types import SimpleNamespace as _i27_SimpleNamespace
import hashlib as _i2_hashlib
import numpy as _i2_np
from dataclasses import asdict as _i3_asdict
from dataclasses import dataclass as _i3_dataclass
import json as _i3_json
import math as _i3_math
import os as _i3_os
from pathlib import Path as _i3_Path
import tempfile as _i3_tempfile
import numpy as _i3_np
import math as _i5_math
import numpy as _i5_np
import math as _i7_math
import json as _i7_json
import os as _i7_os
from pathlib import Path as _i7_Path
import tempfile as _i7_tempfile
import zipfile as _i7_zipfile
import numpy as _i7_np
from scipy import ndimage as _i7_ndimage
import numpy as _i6_np
import numpy as _i9_np
from scipy import ndimage as _i9_ndimage
import numpy as _i8_np
import math as _i11_math
import io as _i11_io
import numpy as _i11_np
from scipy.optimize import least_squares as _i11_least_squares
import numpy as _i10_np
from dataclasses import asdict as _i52_asdict
from dataclasses import dataclass as _i52_dataclass
import json as _i52_json
import math as _i52_math
import os as _i52_os
from pathlib import Path as _i52_Path
import tempfile as _i52_tempfile
import numpy as _i52_np
from dataclasses import asdict as _i12_asdict
from dataclasses import dataclass as _i12_dataclass
from copy import deepcopy as _i12_deepcopy
import json as _i12_json
import math as _i12_math
import os as _i12_os
from pathlib import Path as _i12_Path
import tempfile as _i12_tempfile
import numpy as _i12_np
from collections import deque as _i13_deque
import numpy as _i13_np
from dataclasses import dataclass as _i19_dataclass
import numpy as _i19_np
from dataclasses import dataclass as _i24_dataclass
import math as _i24_math
import numpy as _i24_np
import hashlib as _i16_hashlib
import json as _i16_json
from pathlib import Path as _i16_Path
import numpy as _i16_np
from scipy.optimize import brentq as _i16_brentq
import json as _i14_json
import os as _i14_os
import shutil as _i14_shutil
import tempfile as _i14_tempfile
from pathlib import Path as _i14_Path
import numpy as _i14_np
import numpy as _i15_np
import heapq as _i17_heapq
import numpy as _i17_np
from dataclasses import dataclass as _i18_dataclass
from collections import deque as _i18_deque
import numpy as _i18_np
from dataclasses import dataclass as _i20_dataclass
import hashlib as _i20_hashlib
import json as _i20_json
import math as _i20_math
import numpy as _i20_np
import hashlib as _i21_hashlib
from pathlib import Path as _i21_Path
import numpy as _i21_np
from scipy.ndimage import label as _i21_label
from scipy.ndimage import find_objects as _i21_find_objects
from dataclasses import replace as _i21_replace
from collections import deque as _i21_deque
from scipy.sparse import csr_matrix as _i21_csr_matrix
from scipy.sparse.csgraph import connected_components as _i21_connected_components
from dataclasses import asdict as _i40_asdict
from dataclasses import dataclass as _i40_dataclass
import math as _i40_math
import numpy as _i40_np
import numpy as _i22_np
from dataclasses import dataclass as _i25_dataclass
import hashlib as _i25_hashlib
import json as _i25_json
import math as _i25_math
import numpy as _i25_np
from dataclasses import asdict as _i26_asdict
from dataclasses import dataclass as _i26_dataclass
import math as _i26_math
import numpy as _i26_np
from dataclasses import asdict as _i28_asdict
from dataclasses import dataclass as _i28_dataclass
import math as _i28_math
import numpy as _i28_np
from scipy.ndimage import distance_transform_edt as _i28_distance_transform_edt
from pathlib import Path as _i29_Path
import numpy as _i29_np
from dataclasses import dataclass as _i30_dataclass
import hashlib as _i30_hashlib
import json as _i30_json
import math as _i30_math
import numpy as _i30_np
from types import SimpleNamespace as _i33_SimpleNamespace
import numpy as _i33_np
from scipy.optimize import linprog as _i33_linprog
from scipy.sparse import coo_matrix as _i33_coo_matrix
from scipy.sparse import hstack as _i33_hstack
from scipy.sparse import vstack as _i33_vstack
import numpy as _i31_np
import numpy as _i39_np
import time as _i38_time
from collections import deque as _i38_deque
import numpy as _i38_np
import numpy as _i32_np
import hashlib as _i35_hashlib
import numpy as _i35_np
from scipy.interpolate import CubicSpline as _i35_CubicSpline
from scipy.spatial import cKDTree as _i35_cKDTree
from dataclasses import asdict as _i36_asdict
from dataclasses import dataclass as _i36_dataclass
import numpy as _i36_np
import numpy as _i37_np
from dataclasses import asdict as _i42_asdict
from dataclasses import dataclass as _i42_dataclass
from types import SimpleNamespace as _i42_SimpleNamespace
import math as _i42_math
import numpy as _i42_np
import math as _i44_math
import numpy as _i44_np
from dataclasses import asdict as _i45_asdict
from dataclasses import dataclass as _i45_dataclass
import math as _i45_math
import numpy as _i45_np
from collections import Counter as _i46_Counter
from collections import OrderedDict as _i46_OrderedDict
from collections import defaultdict as _i46_defaultdict
from collections import deque as _i46_deque
from bisect import bisect_right as _i46_bisect_right
from copy import deepcopy as _i46_deepcopy
import gc as _i46_gc
import hashlib as _i46_hashlib
import json as _i46_json
import math as _i46_math
from pathlib import Path as _i46_Path
import tempfile as _i46_tempfile
import numpy as _i46_np
import psutil as _i46_psutil
from collections import Counter as _i47_Counter
from collections import defaultdict as _i47_defaultdict
from copy import deepcopy as _i47_deepcopy
import gc as _i47_gc
import json as _i47_json
import math as _i47_math
from pathlib import Path as _i47_Path
import tempfile as _i47_tempfile
import numpy as _i47_np
from copy import deepcopy as _i48_deepcopy
import hashlib as _i48_hashlib
import json as _i48_json
import math as _i48_math
from pathlib import Path as _i48_Path
import numpy as _i48_np
from collections import deque as _i49_deque
from copy import deepcopy as _i49_deepcopy
import hashlib as _i49_hashlib
import json as _i49_json
import math as _i49_math
from pathlib import Path as _i49_Path
import numpy as _i49_np
from collections import deque as _i50_deque
from copy import deepcopy as _i50_deepcopy
from dataclasses import asdict as _i50_asdict
import hashlib as _i50_hashlib
import json as _i50_json
import math as _i50_math
from pathlib import Path as _i50_Path
import numpy as _i50_np
from dataclasses import asdict as _i51_asdict
from dataclasses import dataclass as _i51_dataclass
import math as _i51_math
import numpy as _i51_np
CATEGORY = 'B'
PLAN_VERSION = 'metric-channel-plan-v2-irregular'

def _mesh_from_parameters(parameters, shape):
    from terrain_pipeline.drainage import grid_mesh as _i4_grid_mesh
    return _i4_grid_mesh(shape, x0_m=parameters['origin_x_m'], z0_m=parameters['origin_z_m'], dx_m=parameters['spacing_x_m'], dz_m=parameters['spacing_z_m'], world_seed=parameters.get('world_seed', 20261020))

@_i4_dataclass(frozen=True)
class ChannelRecipe:
    start_discharge_m3_s: float = 0.05
    reference_discharge_m3_s: float = 0.05
    reference_width_m: float = 3.0
    reference_depth_m: float = 0.8
    width_exponent: float = 0.5
    depth_exponent: float = 0.3
    min_width_m: float = 1.0
    max_width_m: float = 30.0
    min_depth_m: float = 0.2
    max_depth_m: float = 3.0
    min_bed_slope_m_per_m: float = 0.0001
    max_cut_m: float = 4.0
    min_cells_across_width: float = 2.0

    def __post_init__(self):
        positive = ('start_discharge_m3_s', 'reference_discharge_m3_s', 'reference_width_m', 'reference_depth_m', 'min_width_m', 'max_width_m', 'min_depth_m', 'max_depth_m', 'min_bed_slope_m_per_m', 'min_cells_across_width')
        for name in positive:
            value = getattr(self, name)
            if isinstance(value, bool) or not _i4_math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        for name in ('width_exponent', 'depth_exponent', 'max_cut_m'):
            value = getattr(self, name)
            if isinstance(value, bool) or not _i4_math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be finite and nonnegative')
        if self.max_width_m < self.min_width_m or self.max_depth_m < self.min_depth_m:
            raise ValueError('maximum width and depth must exceed minimum')

def _validate_route(receiver, order, shape, outlet_mask, mesh=None, *, historical_saved_graph=False):
    from terrain_pipeline.drainage import grid_mesh as _i4_grid_mesh
    from terrain_pipeline.drainage import receiver_edges_valid as _i4_receiver_edges_valid
    count = int(_i4_np.prod(shape))
    receiver = _i4_np.asarray(receiver)
    order = _i4_np.asarray(order)
    outlets = _i4_np.asarray(outlet_mask)
    if receiver.dtype.kind not in 'iu' or order.dtype.kind not in 'iu' or receiver.size != count or (order.size != count) or (outlets.shape != shape) or (outlets.dtype != bool):
        raise ValueError('invalid route arrays')
    receiver = receiver.reshape(-1).astype(_i4_np.int64)
    order = order.reshape(-1).astype(_i4_np.int64)
    if _i4_np.any((receiver < -1) | (receiver >= count)) or not _i4_np.array_equal(_i4_np.sort(order), _i4_np.arange(count)) or (not _i4_np.array_equal(receiver == -1, outlets.ravel())):
        raise ValueError('invalid route topology or outlets')
    rank = _i4_np.empty(count, dtype=_i4_np.int64)
    rank[order] = _i4_np.arange(count)
    if _i4_np.any((receiver >= 0) & (rank[_i4_np.maximum(receiver, 0)] >= rank)):
        raise ValueError('route receiver must precede donor')
    if historical_saved_graph:
        return (receiver, order)
    if mesh is None:
        mesh = _i4_grid_mesh(shape)
    if not _i4_receiver_edges_valid(receiver, mesh):
        raise ValueError('route must use actual irregular graph edges')
    return (receiver, order)

def plan_channel(height_m, receiver, order, outlet_mask, discharge_m3_s, spacing_x_m, spacing_z_m, origin_x_m, origin_z_m, sea_level_elevation_m, source_identity, recipe: ChannelRecipe, *, world_seed=20261020):
    """Return a separate plan; no source array or routed product is changed."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i4_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i4_array_hash
    from terrain_pipeline.drainage import grid_mesh as _i4_grid_mesh
    if not isinstance(recipe, ChannelRecipe) or not isinstance(source_identity, str) or (not source_identity):
        raise ValueError('recipe and nonempty source identity are required')
    height = _i4_np.asarray(height_m, dtype=_i4_np.float64)
    q = _i4_np.asarray(discharge_m3_s, dtype=_i4_np.float64)
    if height.ndim != 2 or height.size == 0 or q.shape != height.shape or (not _i4_np.isfinite(height).all()) or (not _i4_np.isfinite(q).all()) or _i4_np.any(q < 0):
        raise ValueError('height and nonnegative discharge must be finite matching 2D arrays')
    for name, value in (('spacing_x_m', spacing_x_m), ('spacing_z_m', spacing_z_m)):
        if isinstance(value, bool) or not _i4_math.isfinite(value) or value <= 0:
            raise ValueError(f'{name} must be finite and positive')
    if any((not _i4_math.isfinite(value) for value in (origin_x_m, origin_z_m, sea_level_elevation_m))):
        raise ValueError('origin and sea datum must be finite')
    mesh = _i4_grid_mesh(height.shape, x0_m=origin_x_m, z0_m=origin_z_m, dx_m=spacing_x_m, dz_m=spacing_z_m, world_seed=world_seed)
    downstream, ordered = _validate_route(receiver, order, height.shape, outlet_mask, mesh)
    active = q >= recipe.start_discharge_m3_s
    active_flat = active.ravel()
    for cell in _i4_np.flatnonzero(active_flat):
        next_cell = downstream[cell]
        if next_cell >= 0 and (not active_flat[next_cell]):
            raise ValueError('active channel terminates before explicit outlet')
    ratio = q[active] / recipe.reference_discharge_m3_s
    width = _i4_np.zeros(height.shape, dtype=_i4_np.float64)
    depth = _i4_np.zeros(height.shape, dtype=_i4_np.float64)
    width[active] = _i4_np.clip(recipe.reference_width_m * ratio ** recipe.width_exponent, recipe.min_width_m, recipe.max_width_m)
    depth[active] = _i4_np.clip(recipe.reference_depth_m * ratio ** recipe.depth_exponent, recipe.min_depth_m, recipe.max_depth_m)
    if not _i4_np.isfinite(width).all() or not _i4_np.isfinite(depth).all():
        raise ValueError('nominal width or depth overflows')
    target = height.ravel().copy()
    target[active.ravel()] -= depth.ravel()[active.ravel()]
    cols = height.shape[1]
    for cell in ordered[::-1]:
        next_cell = downstream[cell]
        if next_cell < 0 or not active.flat[cell] or (not active.flat[next_cell]):
            continue
        dz = mesh.node_z_m[cell] - mesh.node_z_m[next_cell]
        dx = mesh.node_x_m[cell] - mesh.node_x_m[next_cell]
        drop = recipe.min_bed_slope_m_per_m * _i4_math.hypot(dx, dz)
        target[next_cell] = min(target[next_cell], target[cell] - drop)
    target = target.reshape(height.shape)
    required_cut = _i4_np.maximum(0.0, height - target)
    if not _i4_np.isfinite(target).all() or not _i4_np.isfinite(required_cut).all():
        raise ValueError('planned bed or cut overflows')
    allowed_cut = _i4_np.minimum(required_cut, recipe.max_cut_m)
    bounded_bed = height - allowed_cut
    over_budget = active & (required_cut > recipe.max_cut_m + 1e-09)
    failed_edge = _i4_np.zeros(height.shape, dtype=bool)
    for cell in ordered[::-1]:
        next_cell = downstream[cell]
        if next_cell < 0 or not active.flat[cell] or (not active.flat[next_cell]):
            continue
        dz = mesh.node_z_m[cell] - mesh.node_z_m[next_cell]
        dx = mesh.node_x_m[cell] - mesh.node_x_m[next_cell]
        drop = recipe.min_bed_slope_m_per_m * _i4_math.hypot(dx, dz)
        if bounded_bed.flat[next_cell] > bounded_bed.flat[cell] - drop + 1e-09:
            failed_edge.flat[cell] = True
    needs_refinement = active & (width < recipe.min_cells_across_width * max(spacing_x_m, spacing_z_m))
    params = {**_i4_asdict(recipe), 'world_seed': world_seed, 'routing': 'irregular_graph_v1', 'spacing_x_m': float(spacing_x_m), 'spacing_z_m': float(spacing_z_m), 'origin_x_m': float(origin_x_m), 'origin_z_m': float(origin_z_m), 'sea_level_elevation_m': float(sea_level_elevation_m), 'source_identity': source_identity, 'source_height_sha256': _i4_array_hash(_i4_np.ascontiguousarray(height, dtype='<f8')), 'source_discharge_sha256': _i4_array_hash(_i4_np.ascontiguousarray(q, dtype='<f8')), 'source_route_sha256': _i4_array_hash(_i4_np.ascontiguousarray(downstream)), 'source_order_sha256': _i4_array_hash(_i4_np.ascontiguousarray(ordered)), 'source_outlet_sha256': _i4_array_hash(_i4_np.ascontiguousarray(outlet_mask))}
    identity = _i4_ArtifactIdentity('Terragenesis', 'metric-channel-plan', PLAN_VERSION, 0, params)
    arrays = {'source_height_m': height.copy(), 'discharge_m3_s': q.copy(), 'receiver': downstream.copy(), 'order': ordered.copy(), 'outlet_mask': _i4_np.asarray(outlet_mask, dtype=bool).copy(), 'channel_mask': active, 'nominal_width_m': width, 'nominal_depth_m': depth, 'target_bed_m': target, 'bounded_bed_m': bounded_bed, 'required_cut_m': required_cut, 'over_budget_mask': over_budget, 'needs_refinement_mask': needs_refinement}
    arrays['failed_slope_edge_donor_mask'] = failed_edge
    for value in arrays.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': 'diagnostic_not_publishable', 'arrays': arrays}

def save_plan(plan, path):
    from terrain_pipeline.artifacts.contracts import array_hash as _i4_array_hash
    destination = _i4_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    arrays = plan['arrays']
    record = {'format_version': 1, 'status': plan['status'], 'identity': plan['identity'], 'identity_sha256': plan['identity_sha256'], 'array_sha256': {name: _i4_array_hash(_i4_np.ascontiguousarray(value)) for name, value in arrays.items()}}
    temporary = None
    try:
        with _i4_tempfile.NamedTemporaryFile(mode='wb', prefix=f'.{destination.name}-', suffix='.npz', dir=destination.parent, delete=False) as stream:
            temporary = _i4_Path(stream.name)
            _i4_np.savez_compressed(stream, manifest=_i4_json.dumps(record, sort_keys=True), **arrays)
        load_plan(temporary)
        _i4_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def load_plan(path):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i4_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i4_array_hash
    with _i4_np.load(path, allow_pickle=False) as archive:
        record = _i4_json.loads(str(archive['manifest'].item()))
        expected = {'source_height_m', 'discharge_m3_s', 'receiver', 'order', 'outlet_mask', 'channel_mask', 'nominal_width_m', 'nominal_depth_m', 'target_bed_m', 'bounded_bed_m', 'required_cut_m', 'over_budget_mask', 'needs_refinement_mask', 'failed_slope_edge_donor_mask'}
        if set(record['array_sha256']) != expected or set(archive.files) != expected | {'manifest'}:
            raise ValueError('invalid plan array set')
        arrays = {name: archive[name].copy() for name in record['array_sha256']}
    identity = _i4_ArtifactIdentity(**record['identity'])
    if record['format_version'] != 1 or record['status'] != 'diagnostic_not_publishable' or identity.sha256 != record['identity_sha256'] or any((_i4_array_hash(_i4_np.ascontiguousarray(arrays[name])) != expected for name, expected in record['array_sha256'].items())):
        raise ValueError('invalid plan identity or arrays')
    shape = arrays['source_height_m'].shape
    if len(shape) != 2 or any((size == 0 for size in shape)) or any((arrays[name].shape != shape for name in expected - {'receiver', 'order'})) or (arrays['receiver'].shape != (arrays['source_height_m'].size,)) or (arrays['order'].shape != arrays['receiver'].shape):
        raise ValueError('invalid plan shapes')
    params = identity.record()['parameters']
    float_fields = {'source_height_m', 'discharge_m3_s', 'nominal_width_m', 'nominal_depth_m', 'target_bed_m', 'bounded_bed_m', 'required_cut_m'}
    bool_fields = {'outlet_mask', 'channel_mask', 'over_budget_mask', 'needs_refinement_mask', 'failed_slope_edge_donor_mask'}
    for name in float_fields:
        if arrays[name].dtype != _i4_np.dtype('float64') or not _i4_np.isfinite(arrays[name]).all():
            raise ValueError('invalid finite float plan array')
    for name in bool_fields:
        if arrays[name].dtype != _i4_np.dtype(bool):
            raise ValueError('invalid boolean plan array')
    for name in ('receiver', 'order'):
        if arrays[name].dtype != _i4_np.dtype('int64'):
            raise ValueError('invalid route index dtype')
    historical = identity.algorithm_version == 'metric-channel-plan-v1'
    mesh = None if historical else _mesh_from_parameters(params, shape)
    _validate_route(arrays['receiver'], arrays['order'], shape, arrays['outlet_mask'], mesh, historical_saved_graph=historical)
    ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})
    for name, field in (('source_height_m', 'source_height_sha256'), ('discharge_m3_s', 'source_discharge_sha256'), ('receiver', 'source_route_sha256'), ('order', 'source_order_sha256'), ('outlet_mask', 'source_outlet_sha256')):
        if _i4_array_hash(_i4_np.ascontiguousarray(arrays[name])) != params[field]:
            raise ValueError('plan input differs from identity')
    for value in arrays.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': record['status'], 'arrays': arrays}
VERSION = 'channel-centerline-v1'

@_i0_dataclass(frozen=True)
class SmoothingRecipe:
    strength: float = 0.2
    max_offset_m: float = 5.0
    min_separation_m: float = 0.0

    def __post_init__(self):
        for name in ('strength', 'max_offset_m', 'min_separation_m'):
            value = getattr(self, name)
            if isinstance(value, bool) or not _i0_math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be finite and nonnegative')
        if self.strength > 0.5:
            raise ValueError('strength must not exceed .5')

def _point_segment_distance(point, start, end):
    vector = end - start
    fraction = _i0_np.clip(_i0_np.dot(point - start, vector) / _i0_np.dot(vector, vector), 0.0, 1.0)
    return float(_i0_np.linalg.norm(point - start - fraction * vector))

def _orientation(a, b, c):
    ab = b - a
    ac = c - a
    return float(ab[0] * ac[1] - ab[1] * ac[0])

def _segments_cross(a, b, c, d):
    o1, o2 = (_orientation(a, b, c), _orientation(a, b, d))
    o3, o4 = (_orientation(c, d, a), _orientation(c, d, b))
    if o1 * o2 < -1e-12 and o3 * o4 < -1e-12:
        return True
    for point, start, end, orientation in ((c, a, b, o1), (d, a, b, o2), (a, c, d, o3), (b, c, d, o4)):
        if abs(orientation) <= 1e-09 and min(start[0], end[0]) - 1e-09 <= point[0] <= max(start[0], end[0]) + 1e-09 and (min(start[1], end[1]) - 1e-09 <= point[1] <= max(start[1], end[1]) + 1e-09):
            return True
    return False

def _shared_edge_overlap(a, b, c, d, shared):
    other_a = b if _i0_np.array_equal(a, shared) else a
    other_b = d if _i0_np.array_equal(c, shared) else c
    if abs(_orientation(shared, other_a, other_b)) > 1e-09:
        return False
    return _i0_np.dot(other_a - shared, other_b - shared) > 1e-09

def _sample_height(height, position, params):
    x = (position[0] - params['origin_x_m']) / params['spacing_x_m']
    z = (position[1] - params['origin_z_m']) / params['spacing_z_m']
    if x < 0 or z < 0 or x > height.shape[1] - 1 or (z > height.shape[0] - 1):
        raise ValueError('smoothed node leaves source height grid')
    x0, z0 = (_i0_math.floor(x), _i0_math.floor(z))
    x1, z1 = (min(x0 + 1, height.shape[1] - 1), min(z0 + 1, height.shape[0] - 1))
    tx, tz = (x - x0, z - z0)
    return float((1 - tx) * (1 - tz) * height[z0, x0] + tx * (1 - tz) * height[z0, x1] + (1 - tx) * tz * height[z1, x0] + tx * tz * height[z1, x1])

def build_centerline(plan, recipe: SmoothingRecipe):
    """Keep graph topology and node bed/width values; move degree-2 bends only."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i0_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i0_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i0_digest
    if not isinstance(recipe, SmoothingRecipe) or plan.get('status') != 'diagnostic_not_publishable':
        raise ValueError('diagnostic plan and smoothing recipe required')
    identity = _i0_ArtifactIdentity(**plan['identity'])
    if identity.sha256 != plan['identity_sha256'] or identity.algorithm != 'metric-channel-plan':
        raise ValueError('invalid plan identity')
    arrays = plan['arrays']
    params = identity.record()['parameters']
    height = arrays['source_height_m']
    receiver, order = _validate_route(arrays['receiver'], arrays['order'], height.shape, arrays['outlet_mask'], _mesh_from_parameters(params, height.shape), historical_saved_graph=identity.algorithm_version == 'metric-channel-plan-v1')
    for name, field in (('source_height_m', 'source_height_sha256'), ('discharge_m3_s', 'source_discharge_sha256'), ('receiver', 'source_route_sha256'), ('order', 'source_order_sha256'), ('outlet_mask', 'source_outlet_sha256')):
        if _i0_array_hash(_i0_np.ascontiguousarray(arrays[name])) != params[field]:
            raise ValueError('plan source differs from identity')
    active = _i0_np.asarray(arrays['channel_mask'])
    bed = _i0_np.asarray(arrays['target_bed_m'])
    width = _i0_np.asarray(arrays['nominal_width_m'])
    if active.shape != height.shape or active.dtype != bool or bed.shape != height.shape or (width.shape != height.shape) or (not _i0_np.isfinite(bed).all()) or (not _i0_np.isfinite(width).all()) or _i0_np.any(width[active] <= 0):
        raise ValueError('invalid plan geometry')
    cols = height.shape[1]
    nodes = _i0_np.flatnonzero(active.ravel())
    if nodes.size == 0:
        raise ValueError('centerline requires an active channel')
    coords = _i0_np.column_stack((params['origin_x_m'] + nodes % cols * params['spacing_x_m'], params['origin_z_m'] + nodes // cols * params['spacing_z_m']))
    original = _i0_np.full((height.size, 2), _i0_np.nan)
    original[nodes] = coords
    moved = original.copy()
    donors = _i0_np.full(height.size, -1, dtype=_i0_np.int64)
    donor_count = _i0_np.zeros(height.size, dtype=_i0_np.int16)
    edges = []
    for cell in nodes:
        target = int(receiver[cell])
        if target >= 0 and active.flat[target]:
            edges.append((int(cell), target))
            donors[target] = cell
            donor_count[target] += 1
    anchors = _i0_np.zeros(height.size, dtype=bool)
    anchors[nodes] = donor_count[nodes] != 1
    anchors[nodes] |= receiver[nodes] < 0
    for cell in nodes:
        target = int(receiver[cell])
        if target < 0 or donor_count[cell] != 1:
            continue
        donor = int(donors[cell])
        suggested = original[cell] + recipe.strength * ((original[donor] + original[target]) / 2 - original[cell])
        offset = float(_i0_np.linalg.norm(suggested - original[cell]))
        if offset > recipe.max_offset_m + 1e-09:
            raise ValueError('smoothed node exceeds original route corridor')
        moved[cell] = suggested
    bucket_size = max(params['spacing_x_m'], params['spacing_z_m'])
    buckets = {}
    for edge_index, (cell, target) in enumerate(edges):
        a, b = (moved[cell], moved[target])
        margin = recipe.min_separation_m
        x0, x1 = (_i0_math.floor((min(a[0], b[0]) - margin) / bucket_size), _i0_math.floor((max(a[0], b[0]) + margin) / bucket_size))
        z0, z1 = (_i0_math.floor((min(a[1], b[1]) - margin) / bucket_size), _i0_math.floor((max(a[1], b[1]) + margin) / bucket_size))
        nearby = set()
        for bx in range(x0, x1 + 1):
            for bz in range(z0, z1 + 1):
                nearby.update(buckets.get((bx, bz), ()))
        for other_index in nearby:
            other_cell, other_target = edges[other_index]
            c, d = (moved[other_cell], moved[other_target])
            shared = {cell, target} & {other_cell, other_target}
            if shared:
                if _shared_edge_overlap(a, b, c, d, moved[next(iter(shared))]):
                    raise ValueError('smoothing overlaps adjacent channel edges')
                continue
            if _segments_cross(a, b, c, d):
                raise ValueError('smoothing introduces a channel crossing')
            if recipe.min_separation_m > 0 and min(_point_segment_distance(a, c, d), _point_segment_distance(b, c, d), _point_segment_distance(c, a, b), _point_segment_distance(d, a, b)) < recipe.min_separation_m:
                raise ValueError('smoothing violates channel separation')
        for bx in range(x0, x1 + 1):
            for bz in range(z0, z1 + 1):
                buckets.setdefault((bx, bz), []).append(edge_index)
    slope_failed = _i0_np.zeros(height.size, dtype=bool)
    for cell, target in edges:
        distance = float(_i0_np.linalg.norm(moved[cell] - moved[target]))
        if bed.flat[cell] - bed.flat[target] + 1e-09 < params['min_bed_slope_m_per_m'] * distance:
            slope_failed[cell] = True
    local_budget_failed = _i0_np.zeros(height.size, dtype=bool)
    for cell in nodes:
        local_budget_failed[cell] = _sample_height(height, moved[cell], params) - bed.flat[cell] > params['max_cut_m'] + 1e-09
    geometry_hash = _i0_digest({name: _i0_array_hash(_i0_np.ascontiguousarray(arrays[name])) for name in ('target_bed_m', 'nominal_width_m', 'channel_mask')})
    result_arrays = {'node_world_xz_m': moved[nodes].copy(), 'original_world_xz_m': original[nodes].copy(), 'node_flat_index': nodes.astype(_i0_np.int64), 'edge_donor_flat_index': _i0_np.array([e[0] for e in edges], dtype=_i0_np.int64), 'edge_target_flat_index': _i0_np.array([e[1] for e in edges], dtype=_i0_np.int64), 'node_bed_m': bed.ravel()[nodes].copy(), 'node_width_m': width.ravel()[nodes].copy(), 'anchor_mask': anchors[nodes].copy(), 'slope_failed_donor_mask': slope_failed[nodes].copy(), 'local_budget_failed_mask': local_budget_failed[nodes].copy()}
    result_geometry_hash = _i0_digest({name: _i0_array_hash(_i0_np.ascontiguousarray(value)) for name, value in result_arrays.items()})
    result_identity = _i0_ArtifactIdentity('Terragenesis', 'channel-centerline', VERSION, 0, {**_i0_asdict(recipe), 'plan_identity_sha256': plan['identity_sha256'], 'plan_geometry_sha256': geometry_hash, 'result_geometry_sha256': result_geometry_hash})
    for value in result_arrays.values():
        value.flags.writeable = False
    return {'identity': result_identity.record(), 'identity_sha256': result_identity.sha256, 'status': 'diagnostic_not_publishable', 'arrays': result_arrays, 'summary': {'nodes': len(nodes), 'edges': len(edges), 'moved_nodes': int(_i0_np.count_nonzero(_i0_np.linalg.norm(moved[nodes] - original[nodes], axis=1) > 1e-09)), 'max_offset_m': float(_i0_np.max(_i0_np.linalg.norm(moved[nodes] - original[nodes], axis=1))) if len(nodes) else 0.0, 'slope_failed_edges': int(_i0_np.count_nonzero(slope_failed)), 'local_budget_failed_nodes': int(_i0_np.count_nonzero(local_budget_failed))}}

def save_centerline(result, path):
    from terrain_pipeline.artifacts.contracts import array_hash as _i0_array_hash
    destination = _i0_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ('identity', 'identity_sha256', 'status', 'summary')}
    record['format_version'] = 1
    record['array_sha256'] = {key: _i0_array_hash(value) for key, value in result['arrays'].items()}
    temporary = None
    try:
        with _i0_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, prefix=f'.{destination.name}-', suffix='.npz', delete=False) as stream:
            temporary = _i0_Path(stream.name)
            _i0_np.savez_compressed(stream, manifest=_i0_json.dumps(record, sort_keys=True), **result['arrays'])
        load_centerline(temporary)
        _i0_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def load_centerline(path):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i0_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i0_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i0_digest
    with _i0_np.load(path, allow_pickle=False) as archive:
        record = _i0_json.loads(str(archive['manifest'].item()))
        arrays = {name: archive[name].copy() for name in record['array_sha256']}
        expected = {'node_world_xz_m', 'original_world_xz_m', 'node_flat_index', 'edge_donor_flat_index', 'edge_target_flat_index', 'node_bed_m', 'node_width_m', 'anchor_mask', 'slope_failed_donor_mask', 'local_budget_failed_mask'}
        if set(arrays) != expected or set(archive.files) != expected | {'manifest'}:
            raise ValueError('invalid centerline arrays')
    identity = _i0_ArtifactIdentity(**record['identity'])
    if identity.sha256 != record['identity_sha256'] or record['format_version'] != 1 or record['status'] != 'diagnostic_not_publishable' or any((_i0_array_hash(arrays[name]) != expected for name, expected in record['array_sha256'].items())):
        raise ValueError('invalid centerline identity or hashes')
    if identity.algorithm != 'channel-centerline' or identity.algorithm_version != VERSION:
        raise ValueError('wrong centerline algorithm')
    params = identity.record()['parameters']
    SmoothingRecipe(params['strength'], params['max_offset_m'], params['min_separation_m'])
    if _i0_digest({name: _i0_array_hash(_i0_np.ascontiguousarray(value)) for name, value in arrays.items()}) != params['result_geometry_sha256']:
        raise ValueError('centerline geometry differs from identity')
    node_count = arrays['node_flat_index'].size
    edge_count = arrays['edge_donor_flat_index'].size
    if node_count == 0 or arrays['node_flat_index'].shape != (node_count,) or arrays['edge_target_flat_index'].shape != (edge_count,) or (arrays['node_world_xz_m'].shape != (node_count, 2)) or (arrays['original_world_xz_m'].shape != (node_count, 2)) or any((arrays[name].shape != (node_count,) for name in ('node_bed_m', 'node_width_m', 'anchor_mask', 'slope_failed_donor_mask', 'local_budget_failed_mask'))):
        raise ValueError('invalid centerline array shapes')
    for name in ('node_world_xz_m', 'original_world_xz_m', 'node_bed_m', 'node_width_m'):
        if arrays[name].dtype != _i0_np.float64 or not _i0_np.isfinite(arrays[name]).all():
            raise ValueError('invalid centerline finite geometry')
    for name in ('node_flat_index', 'edge_donor_flat_index', 'edge_target_flat_index'):
        if arrays[name].dtype != _i0_np.int64:
            raise ValueError('invalid centerline index dtype')
    for name in ('anchor_mask', 'slope_failed_donor_mask', 'local_budget_failed_mask'):
        if arrays[name].dtype != bool:
            raise ValueError('invalid centerline mask dtype')
    nodes = arrays['node_flat_index']
    if not _i0_np.array_equal(nodes, _i0_np.unique(nodes)) or not set(arrays['edge_donor_flat_index']).issubset(set(nodes)) or (not set(arrays['edge_target_flat_index']).issubset(set(nodes))) or _i0_np.any(arrays['node_width_m'] <= 0) or _i0_np.any(arrays['anchor_mask'] & _i0_np.any(arrays['node_world_xz_m'] != arrays['original_world_xz_m'], axis=1)) or _i0_np.any(_i0_np.linalg.norm(arrays['node_world_xz_m'] - arrays['original_world_xz_m'], axis=1) > params['max_offset_m'] + 1e-09):
        raise ValueError('invalid centerline topology or corridor')
    if record['summary']['nodes'] != node_count or record['summary']['edges'] != edge_count or record['summary']['slope_failed_edges'] != int(_i0_np.count_nonzero(arrays['slope_failed_donor_mask'])) or (record['summary']['local_budget_failed_nodes'] != int(_i0_np.count_nonzero(arrays['local_budget_failed_mask']))):
        raise ValueError('centerline summary mismatch')
    for value in arrays.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': record['status'], 'arrays': arrays, 'summary': record['summary']}

def validate_centerline_for_plan(centerline, plan):
    """Reject a centerline from another plan or with changed graph/geometry arrays."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i0_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i0_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i0_digest
    identity = _i0_ArtifactIdentity(**centerline['identity'])
    if identity.sha256 != centerline['identity_sha256'] or identity.algorithm != 'channel-centerline' or centerline.get('status') != 'diagnostic_not_publishable':
        raise ValueError('invalid centerline identity')
    params = identity.record()['parameters']
    if _i0_digest({name: _i0_array_hash(_i0_np.ascontiguousarray(value)) for name, value in centerline['arrays'].items()}) != params['result_geometry_sha256']:
        raise ValueError('centerline result differs from identity')
    arrays = plan['arrays']
    geometry_hash = _i0_digest({name: _i0_array_hash(_i0_np.ascontiguousarray(arrays[name])) for name in ('target_bed_m', 'nominal_width_m', 'channel_mask')})
    if params['plan_identity_sha256'] != plan['identity_sha256'] or params['plan_geometry_sha256'] != geometry_hash:
        raise ValueError('centerline source plan mismatch')
    result = centerline['arrays']
    nodes = result['node_flat_index']
    expected_nodes = _i0_np.flatnonzero(arrays['channel_mask'].ravel())
    if nodes.dtype != _i0_np.int64 or not _i0_np.array_equal(nodes, expected_nodes):
        raise ValueError('centerline node set differs from plan')
    index = {int(cell): pos for pos, cell in enumerate(nodes)}
    expected_edges = [(int(cell), int(arrays['receiver'][cell])) for cell in nodes if arrays['receiver'][cell] >= 0 and arrays['channel_mask'].flat[arrays['receiver'][cell]]]
    edges = list(zip(result['edge_donor_flat_index'], result['edge_target_flat_index']))
    if edges != expected_edges:
        raise ValueError('centerline edge set differs from plan')
    positions = result['node_world_xz_m']
    if positions.shape != (len(nodes), 2) or not _i0_np.isfinite(positions).all():
        raise ValueError('invalid centerline positions')
    source = result['original_world_xz_m']
    if source.shape != positions.shape or not _i0_np.isfinite(source).all():
        raise ValueError('invalid original positions')
    base = plan['identity']['parameters']
    cols = arrays['source_height_m'].shape[1]
    expected_source = _i0_np.column_stack((base['origin_x_m'] + nodes % cols * base['spacing_x_m'], base['origin_z_m'] + nodes // cols * base['spacing_z_m']))
    if not _i0_np.array_equal(source, expected_source):
        raise ValueError('centerline original geometry differs from plan')
    donor_counts = _i0_np.zeros(arrays['source_height_m'].size, dtype=_i0_np.int32)
    for _, target in expected_edges:
        donor_counts[target] += 1
    expected_anchors = _i0_np.array([donor_counts[cell] != 1 or arrays['receiver'][cell] < 0 for cell in nodes], dtype=bool)
    if not _i0_np.array_equal(result['anchor_mask'], expected_anchors):
        raise ValueError('centerline anchors differ from plan topology')
    for cell, pos in index.items():
        if result['anchor_mask'][pos] and (not _i0_np.array_equal(positions[pos], source[pos])) or _i0_np.linalg.norm(positions[pos] - source[pos]) > params['max_offset_m'] + 1e-09:
            raise ValueError('centerline anchor or corridor violation')
    if not _i0_np.array_equal(result['node_bed_m'], arrays['target_bed_m'].ravel()[nodes]) or not _i0_np.array_equal(result['node_width_m'], arrays['nominal_width_m'].ravel()[nodes]):
        raise ValueError('centerline bed or width differs from plan')
    return True
ALGORITHM = 'frozen-edge-td-irregular-corridor-dijkstra-v2'

@_i1_dataclass(frozen=True)
class FrozenPathConfig:
    corridor_m: float = 500.0
    maximum_nodes: int = 200000
    elevation_cost_per_m: float = 0.01
    uphill_cost_m_per_m: float = 8.0
    displacement_cost_per_m2: float = 2e-06

    def __post_init__(self):
        if any((not _i1_np.isfinite(value) or value <= 0 for value in _i1_asdict(self).values())):
            raise ValueError('positive finite frozen path parameters required')

def _sample(height, points, origin, spacing):
    local = (points - origin) / spacing
    maximum = _i1_np.array(height.shape)[::-1] - 1
    if _i1_np.any(local < 0) or _i1_np.any(local > maximum):
        raise ValueError('whole frozen path leaves genuine source support')
    cell = _i1_np.minimum(_i1_np.floor(local).astype(int), maximum.astype(int) - 1)
    weight = local - cell
    x, z = cell.T
    wx, wz = weight.T
    return (1 - wz) * ((1 - wx) * height[z, x] + wx * height[z, x + 1]) + wz * ((1 - wx) * height[z + 1, x] + wx * height[z + 1, x + 1])

def _segment_samples(points, spacing):
    samples = []
    for first, second in zip(points[:-1], points[1:]):
        count = max(1, int(_i1_np.ceil(_i1_np.linalg.norm(second - first) / spacing)))
        samples.append(first + _i1_np.linspace(0, 1, count + 1)[:, None] * (second - first))
    return _i1_np.concatenate(samples)

def _segment_owner_samples(points, origin, spacing):
    """Visit every constant nearest-node ownership interval, including corners."""
    samples = []
    for first, second in zip(points[:-1], points[1:]):
        parameters = [0.0, 1.0]
        for axis in (0, 1):
            if abs(second[axis] - first[axis]) <= 1e-12:
                continue
            low, high = sorted((first[axis], second[axis]))
            boundaries = origin[axis] + spacing * (_i1_np.arange(int(_i1_np.floor((low - origin[axis]) / spacing - 0.5)) + 1, int(_i1_np.floor((high - origin[axis]) / spacing - 0.5)) + 1) + 0.5)
            parameters.extend(((boundaries - first[axis]) / (second[axis] - first[axis])).tolist())
        parameters = _i1_np.unique(_i1_np.clip(parameters, 0.0, 1.0))
        parameters = _i1_np.sort(_i1_np.r_[parameters, (parameters[:-1] + parameters[1:]) / 2])
        samples.append(first + parameters[:, None] * (second - first))
    return _i1_np.concatenate(samples)

@_i1_njit(cache=True)
def _actual_segments_clear(sources, targets, points, origin, spacing, valid):
    """Check every nearest-cell ownership interval along actual graph edges."""
    result = _i1_np.ones(len(sources), _i1_np.bool_)
    for i in range(len(sources)):
        first, second = (points[sources[i]], points[targets[i]])
        parameters = [0.0, 1.0]
        for axis in range(2):
            delta = second[axis] - first[axis]
            if abs(delta) <= 1e-12:
                continue
            low, high = (min(first[axis], second[axis]), max(first[axis], second[axis]))
            begin = int(_i1_np.floor((low - origin[axis]) / spacing - 0.5)) + 1
            end = int(_i1_np.floor((high - origin[axis]) / spacing - 0.5)) + 1
            for boundary in range(begin, end):
                t = (origin[axis] + spacing * (boundary + 0.5) - first[axis]) / delta
                parameters.append(min(1.0, max(0.0, t)))
        ts = _i1_np.sort(_i1_np.array(parameters))
        for j in range(len(ts) * 2 - 1):
            t = ts[j // 2] if j % 2 == 0 else (ts[j // 2] + ts[j // 2 + 1]) / 2
            x = int(_i1_np.floor((first[0] + t * (second[0] - first[0]) - origin[0]) / spacing + 0.5))
            z = int(_i1_np.floor((first[1] + t * (second[1] - first[1]) - origin[1]) / spacing + 0.5))
            if x < 0 or z < 0 or z >= valid.shape[0] or (x >= valid.shape[1]) or (not valid[z, x]):
                result[i] = False
                break
    return result

def _terrain_weighted_path(mesh, height, valid, start, targets, *, config, displacement=None, actual_segment_frame=None, points=None, initial_direction_xz=None, direction_weight=0.0, direction_decay_m=None, max_turn_deg=None, start_directions_xz=(), end_directions_xz=(), turn_penalty_k=1.0):
    """Shared directed terrain-cost search; return flattened account node IDs."""
    from terrain_pipeline.drainage import masked_mesh
    allowed = masked_mesh(mesh, valid)
    sources = _i1_np.repeat(_i1_np.arange(height.size), _i1_np.diff(allowed.indptr))
    ends = allowed.indices
    keep = valid.ravel()[sources] & valid.ravel()[ends]
    sources, ends = (sources[keep], ends[keep])
    lengths = allowed.edge_length_m[keep]
    if points is None:
        points = _i1_np.column_stack((mesh.node_x_m, mesh.node_z_m))
    if actual_segment_frame is not None:
        origin, spacing = actual_segment_frame
        keep = _actual_segments_clear(sources, ends, points, origin, spacing, valid)
        sources, ends = (sources[keep], ends[keep])
        lengths = _i1_np.linalg.norm(points[ends] - points[sources], axis=1)
    ids = _i1_np.full(height.size, -1, _i1_np.int64)
    ids[valid.ravel()] = _i1_np.arange(valid.sum())
    floor = float(height[valid].min())
    multiplier = 1 + config.elevation_cost_per_m * ((height.ravel()[sources] + height.ravel()[ends]) / 2 - floor)
    if displacement is not None:
        multiplier += config.displacement_cost_per_m2 * (displacement.ravel()[sources] ** 2 + displacement.ravel()[ends] ** 2) / 2
    cost = lengths * multiplier
    cost += config.uphill_cost_m_per_m * _i1_np.maximum(0, height.ravel()[ends] - height.ravel()[sources])
    if initial_direction_xz is not None:
        direction = _i1_np.array(initial_direction_xz, dtype=float, copy=True)
        if direction.shape != (2,) or not _i1_np.isfinite(direction).all() or _i1_np.linalg.norm(direction) == 0 or (not _i1_np.isfinite(direction_weight)) or (direction_weight < 0) or (direction_decay_m is None) or (not _i1_np.isfinite(direction_decay_m)) or (direction_decay_m <= 0):
            raise ValueError('invalid initial direction cost')
        direction /= _i1_np.linalg.norm(direction)
        edges = points[ends] - points[sources]
        alignment = _i1_np.clip(edges @ direction / lengths, -1.0, 1.0)
        distance = _i1_np.linalg.norm((points[sources] + points[ends]) / 2 - points[start], axis=1)
        cost += lengths * direction_weight * (1 - alignment) * _i1_np.exp(-distance / direction_decay_m)
    if max_turn_deg is not None:
        pass
        return heading_path(sources, ends, cost, points, start, targets, max_turn_deg=max_turn_deg, start_directions=start_directions_xz, end_directions=end_directions_xz, turn_penalty_k=turn_penalty_k)
    count = int(valid.sum())
    graph = _i1_sparse.coo_matrix((cost, (ids[sources], ids[ends])), shape=(count, count)).tocsr()
    first = int(ids[start])
    distances, previous = _i1_dijkstra(graph, directed=True, indices=first, return_predecessors=True)
    candidates = _i1_np.asarray(targets, dtype=_i1_np.int64)
    candidate_ids = ids[candidates]
    finish = int(candidate_ids[_i1_np.argmin(distances[candidate_ids])])
    if not _i1_np.isfinite(distances[finish]):
        return None
    selected = [finish]
    while selected[-1] != first:
        selected.append(int(previous[selected[-1]]))
        if selected[-1] < 0 or len(selected) > count:
            raise ValueError('terrain path reconstruction failed')
    return _i1_np.flatnonzero(valid.ravel())[_i1_np.asarray(selected[::-1])]

def _no_crossing(points, existing_paths):
    for existing in existing_paths:
        other = _i1_np.asarray(existing, float)
        for first, second in zip(points[:-1], points[1:]):
            starts, ends = (other[:-1], other[1:])

            def cross(a, b):
                return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]
            a = cross(second - first, starts - first)
            b = cross(second - first, ends - first)
            c = cross(ends - starts, first - starts)
            d = cross(ends - starts, second - starts)
            overlap = (_i1_np.maximum(_i1_np.minimum(first, second), _i1_np.minimum(starts, ends)) <= _i1_np.minimum(_i1_np.maximum(first, second), _i1_np.maximum(starts, ends)) + 1e-08).all(axis=1)
            contacts = overlap & (a * b <= 1e-12) & (c * d <= 1e-12)
            for index in _i1_np.flatnonzero(contacts):
                shared = [anchor for anchor in (points[0], points[-1]) if (_i1_np.array_equal(anchor, other[0]) or _i1_np.array_equal(anchor, other[-1])) and (_i1_np.array_equal(anchor, first) or _i1_np.array_equal(anchor, second)) and (_i1_np.array_equal(anchor, starts[index]) or _i1_np.array_equal(anchor, ends[index]))]
                collinear = abs(a[index]) + abs(b[index]) + abs(c[index]) + abs(d[index]) <= 1e-08
                if not shared or collinear:
                    raise ValueError('frozen candidate crosses or overlaps another represented edge')

def prepare_frozen_edge_path(plan, source_edge, height_m, origin_xz_m, spacing_m, source_identity, *, owner_domain_id, protected_mask=None, config=FrozenPathConfig(), existing_paths=()):
    """Route a complete registered edge; reject partial support or owner gaps."""
    from terrain_pipeline.common_infra import identity as _i1_identity
    height = _i1_np.asarray(height_m, float)
    owner = _i1_np.asarray(owner_domain_id)
    origin = _i1_np.asarray(origin_xz_m, float)
    protected = _i1_np.zeros(height.shape, bool) if protected_mask is None else _i1_np.asarray(protected_mask, bool)
    edge = _i1_np.asarray(source_edge, _i1_np.int64)
    if height.ndim != 2 or min(height.shape) < 2 or owner.shape != height.shape or (protected.shape != height.shape) or (not _i1_np.isfinite(height).all()) or (origin.shape != (2,)) or (not _i1_np.isfinite(origin).all()) or (not _i1_np.isfinite(spacing_m)) or (spacing_m <= 0) or (edge.shape != (2,)):
        raise ValueError('aligned finite frozen path source required')
    receiver = _i1_np.asarray(plan['receiver']).ravel()
    if _i1_np.any(edge < 0) or _i1_np.any(edge >= len(receiver)) or receiver[edge[0]] != edge[1] or (not _i1_np.asarray(plan['river_mask']).ravel()[edge[0]]):
        raise ValueError('registered frozen river edge required')
    coarse_owner = _i1_np.asarray(plan['owner_domain_id']).ravel()
    domain = int(coarse_owner[edge[0]])
    if domain < 0 or coarse_owner[edge[1]] != domain:
        raise ValueError('whole dry frozen path requires same declared owner endpoints')
    columns = _i1_np.asarray(plan['height_m']).shape[1]
    anchors = _i1_np.asarray(plan['origin_xz_m']) + plan['spacing_m'] * _i1_np.column_stack((edge % columns, edge // columns))
    _sample(height, anchors, origin, spacing_m)
    vector = anchors[1] - anchors[0]
    length = _i1_np.linalg.norm(vector)
    z, x = _i1_np.indices(height.shape)
    points = origin + spacing_m * _i1_np.stack((x, z), axis=-1)
    progress = _i1_np.sum((points - anchors[0]) * vector, axis=-1) / length ** 2
    distance = _i1_np.linalg.norm(points - anchors[0] - _i1_np.clip(progress, 0, 1)[..., None] * vector, axis=-1)
    valid = (distance <= config.corridor_m) & (progress >= 0) & (progress <= 1) & (owner == domain) & ~protected
    endpoint_cells = _i1_np.rint((anchors - origin) / spacing_m).astype(int)
    if _i1_np.any(endpoint_cells < 0) or _i1_np.any(endpoint_cells >= _i1_np.array(height.shape)[::-1]):
        raise ValueError('frozen endpoint native attachment leaves source')
    for cx, cz in endpoint_cells:
        if owner[cz, cx] != domain or protected[cz, cx] or distance[cz, cx] > config.corridor_m:
            raise ValueError('frozen endpoint attachment crosses owner or protection')
        valid[cz, cx] = True
    count = int(valid.sum())
    if count > config.maximum_nodes:
        raise ValueError('whole-edge path node budget exceeded')
    from terrain_pipeline.drainage import grid_mesh
    mesh = grid_mesh(height.shape, x0_m=origin[0], z0_m=origin[1], dx_m=spacing_m, world_seed=int(plan.get('seed', 20261020)))
    start, finish = [int(cz * height.shape[1] + cx) for cx, cz in endpoint_cells]
    selected = _terrain_weighted_path(mesh, height, valid, start, [finish], config=config, displacement=distance)
    if selected is None:
        raise ValueError('no legal complete frozen-edge corridor path')
    graph_points = _i1_np.column_stack((mesh.node_x_m, mesh.node_z_m))
    native_points = graph_points[selected].copy()
    native_points[0], native_points[-1] = (anchors[0], anchors[1])
    full = _i1_np.vstack((anchors[0], native_points, anchors[1]))
    full = full[_i1_np.r_[True, _i1_np.linalg.norm(_i1_np.diff(full, axis=0), axis=1) > 1e-08]]
    samples = _segment_owner_samples(full, origin, spacing_m)
    _sample(height, samples, origin, spacing_m)
    cells = _i1_np.rint((samples - origin) / spacing_m).astype(int)
    if _i1_np.any(owner[cells[:, 1], cells[:, 0]] != domain) or _i1_np.any(protected[cells[:, 1], cells[:, 0]]):
        raise ValueError('frozen path segment crosses owner or protection')
    _no_crossing(full, existing_paths)
    arc = _i1_np.r_[0.0, _i1_np.cumsum(_i1_np.linalg.norm(_i1_np.diff(full, axis=0), axis=1))]
    profile_arc = _i1_np.unique(_i1_np.r_[arc, _i1_np.linspace(0.0, arc[-1], int(_i1_np.ceil(arc[-1])) + 1)])
    profile_points = _i1_np.column_stack([_i1_np.interp(profile_arc, arc, full[:, axis]) for axis in (0, 1)])
    arrays = {'points_xz_m': full, 'arclength_m': arc, 'source_height_m': _sample(height, full, origin, spacing_m), 'profile_arclength_m': profile_arc, 'profile_source_m': _sample(height, profile_points, origin, spacing_m)}
    metadata = {'algorithm': ALGORITHM, 'plan_identity': plan['identity_sha256'], 'source_identity': source_identity, 'source_edge': edge.tolist(), 'owner_domain_id': domain, 'config': _i1_asdict(config), 'source_origin_xz_m': origin.tolist(), 'source_shape': list(height.shape), 'source_spacing_m': float(spacing_m), 'complete_edge': True, 'node_count': count, 'represented_length_m': float(arc[-1]), 'anchor_policy': 'exact frozen endpoints attached to source-frame irregular graph corridor', 'world_seed': int(plan.get('seed', 20261020)), 'cost_units': 'edge cost m; elevation multiplier 1/m; uphill m/m; displacement multiplier 1/m2', 'protection_identity': _i1_identity({'owner_domain_id': owner, 'protected_mask': protected}, {}), 'bed_certified': False, 'hydraulic_certified': False}
    return {'arrays': arrays, 'metadata': metadata, 'identity': _i1_identity(arrays, metadata)}

def clip_frozen_edge_path(path, start_arclength_m, end_arclength_m):
    """Clip by global arc length, never reroute or recompute a window identity."""
    from terrain_pipeline.common_infra import identity as _i1_identity
    arrays, metadata = (path['arrays'], path['metadata'])
    if path['identity'] != _i1_identity(arrays, metadata):
        raise ValueError('whole frozen path identity differs')
    arc, points = (arrays['arclength_m'], arrays['points_xz_m'])
    if not 0 <= start_arclength_m < end_arclength_m <= arc[-1]:
        raise ValueError('bounded increasing whole-path arc interval required')
    selected = _i1_np.r_[start_arclength_m, arc[(arc > start_arclength_m) & (arc < end_arclength_m)], end_arclength_m]
    clipped = _i1_np.column_stack([_i1_np.interp(selected, arc, points[:, axis]) for axis in (0, 1)])
    return {'whole_path_identity': path['identity'], 'source_edge': metadata['source_edge'], 'points_xz_m': clipped, 'arclength_m': selected, 'edge_fractions': selected / arc[-1]}

def validate_frozen_path_nodes(path, plan, points, source_edges, fractions, receiver=None):
    """Prove bed nodes and every represented chord belong to the frozen polyline."""
    from terrain_pipeline.common_infra import identity as _i1_identity
    arrays, metadata = (path['arrays'], path['metadata'])
    if path['identity'] != _i1_identity(arrays, metadata) or metadata['plan_identity'] != plan['identity_sha256']:
        raise ValueError('whole frozen path or plan identity differs')
    edge = _i1_np.asarray(metadata['source_edge'], int)
    if not _i1_np.all(_i1_np.asarray(source_edges) == edge):
        raise ValueError('bed nodes refer to another whole frozen edge')
    arc = arrays['arclength_m']
    whole_points = arrays['points_xz_m']
    positions = _i1_np.asarray(fractions) * arc[-1]
    expected = _i1_np.column_stack([_i1_np.interp(positions, arc, whole_points[:, axis]) for axis in (0, 1)])
    if not _i1_np.allclose(points, expected, rtol=0, atol=1e-07):
        raise ValueError('bed nodes differ from whole frozen path arc clipping')
    if receiver is not None:
        for node in _i1_np.flatnonzero(_i1_np.asarray(receiver) >= 0):
            other = receiver[node]
            chord = _i1_np.linalg.norm(_i1_np.asarray(points)[other] - _i1_np.asarray(points)[node])
            if positions[other] <= positions[node] or abs(chord - (positions[other] - positions[node])) > 1e-07:
                raise ValueError('bed piece shortcuts a represented frozen path bend')

def frozen_path_profiles(plan, paths, height_m, origin_xz_m, spacing_m, *, sample_spacing_m=1.0, clip_origin_xz_m=None, clip_shape=None):
    """Use one whole-source bed profile, then clip it to the computational window."""
    height = _i1_np.asarray(height_m, float)
    source_origin = _i1_np.asarray(origin_xz_m, float)
    origin = source_origin if clip_origin_xz_m is None else _i1_np.asarray(clip_origin_xz_m, float)
    shape = height.shape if clip_shape is None else tuple(clip_shape)
    maximum = origin + (_i1_np.array(shape)[::-1] - 1) * spacing_m
    profiles = []
    for path in paths:
        arrays, metadata = (path['arrays'], path['metadata'])
        validate_frozen_path_nodes(path, plan, arrays['points_xz_m'], _i1_np.tile(metadata['source_edge'], (len(arrays['points_xz_m']), 1)), arrays['arclength_m'] / arrays['arclength_m'][-1])
        intervals = []
        for index, (start, finish) in enumerate(zip(arrays['points_xz_m'][:-1], arrays['points_xz_m'][1:])):
            vector = finish - start
            low, high = (0.0, 1.0)
            for axis in (0, 1):
                if abs(vector[axis]) < 1e-12:
                    if not origin[axis] <= start[axis] <= maximum[axis]:
                        high = -1.0
                else:
                    limits = sorted(((origin[axis] - start[axis]) / vector[axis], (maximum[axis] - start[axis]) / vector[axis]))
                    low, high = (max(low, limits[0]), min(high, limits[1]))
            if high > low:
                base = arrays['arclength_m'][index]
                length = arrays['arclength_m'][index + 1] - base
                intervals.append((base + low * length, base + high * length))
        if not intervals:
            continue
        if any((abs(first[1] - second[0]) > 1e-07 for first, second in zip(intervals[:-1], intervals[1:]))):
            raise ValueError('whole frozen path reenters this window; explicit disconnected clips required')
        low, high = (intervals[0][0], intervals[-1][1])
        full_arc = arrays['profile_arclength_m']
        full_source = arrays['profile_source_m']
        full_bed = _i1_np.minimum.accumulate(full_source + 0.001 * full_arc) - 0.001 * full_arc - 0.5
        arc = _i1_np.unique(_i1_np.r_[low, high, arrays['arclength_m'][(arrays['arclength_m'] > low) & (arrays['arclength_m'] < high)], _i1_np.linspace(low, high, int(_i1_np.ceil((high - low) / sample_spacing_m)) + 1)])
        points = _i1_np.column_stack([_i1_np.interp(arc, arrays['arclength_m'], arrays['points_xz_m'][:, axis]) for axis in (0, 1)])
        source = _sample(height, points, source_origin, spacing_m)
        profiles.append({'source_edge': metadata['source_edge'], 'fractions': arc / arrays['arclength_m'][-1], 'points_xz_m': points, 'source_m': source, 'bed_m': _i1_np.interp(arc, full_arc, full_bed), 'length_m': float(high - low), 'full_coarse_edge_length_m': float(arrays['arclength_m'][-1]), 'whole_path_identity': path['identity'], 'whole_path_arclength_m': arc})
    return profiles
METRIC_CHANNEL_GEOMETRY_SCHEMA = 'terragenesis-metric-channel-geometry-v1'
METRIC_CHANNEL_GEOMETRY_ALGORITHM = 'original-bed-canonical-fan4-max-cut-v2'
METRIC_CHANNEL_GEOMETRY_MAX_BYTES = 128 * 1024 * 1024
BANK_SLOPE = 2.0
LIMITATIONS = ['fixed original-bed heightfield; no overhangs or below-grid detail', 'cut volume exact only for represented piecewise-linear mesh', 'one-hop neighboring reaches may share max-cut support; distant shortcuts refused', 'no hydraulic, material, natural-mouth, or lake-merger certification']
ARRAYS = ('source_node_cell_ids', 'receiver', 'original_node_xz_m', 'node_xz_m', 'node_source_elevation_m', 'width_m', 'depth_m', 'anchor_mask', 'vertices_xz_m', 'source_elevation_m', 'cut_depth_m', 'bed_elevation_m', 'triangles', 'source_cell_ids', 'source_height_m', 'source_valid_mask', 'owner_grid', 'corridor_mask', 'lake_mask', 'canonical_port_edge_node_indices', 'canonical_port_xz_m', 'canonical_port_profile_xz_m', 'canonical_port_triangle_ids', 'canonical_port_barycentric', 'canonical_port_cut_depth_m')

@_i23_dataclass(frozen=True)
class GeometryConfig:
    fine_spacing_m: float = 1.0
    width_resolution: float = 4.0
    max_cut_m: float = 4.0
    max_offset_m: float = 6.0
    smoothing_iterations: int = 12
    curvature_weight: float = 0.25
    valley_weight: float = 1.0
    max_vertices: int = 262144

    def __post_init__(self):
        for name in ('fine_spacing_m', 'width_resolution', 'max_cut_m', 'max_offset_m', 'curvature_weight', 'valley_weight'):
            value = getattr(self, name)
            if isinstance(value, (bool, _i23_np.bool_)) or not isinstance(value, (int, float, _i23_np.integer, _i23_np.floating)) or (not _i23_math.isfinite(value)) or (value < 0.0):
                raise ValueError(name + ' must be finite nonnegative')
            object.__setattr__(self, name, float(value))
        if self.fine_spacing_m <= 0.0 or self.width_resolution < 2.0 or self.max_cut_m <= 0.0 or (self.valley_weight <= 0.0):
            raise ValueError('geometry spacing/resolution/cut/valley weight outside bounds')
        if any((getattr(self, name) > 1000000.0 for name in ('fine_spacing_m', 'width_resolution', 'max_cut_m', 'max_offset_m', 'curvature_weight', 'valley_weight'))):
            raise ValueError('geometry numeric parameter resource bound exceeded')
        if type(self.smoothing_iterations) is not int or not 0 <= self.smoothing_iterations <= 100:
            raise ValueError('bounded smoothing_iterations required')
        if type(self.max_vertices) is not int or not 1 <= self.max_vertices <= 262144:
            raise ValueError('bounded max_vertices required')

def _metric_channel_geometry_sample(height, xz, terrain, *, require_valid=True):
    points = _i23_np.asarray(xz, _i23_np.float64).reshape(-1, 2)
    gx = (points[:, 0] - terrain.x0_m) / terrain.dx_m
    gz = (points[:, 1] - terrain.z0_m) / terrain.dz_m
    rows, cols = height.shape
    if rows < 2 or cols < 2 or (not _i23_np.isfinite(points).all()) or _i23_np.any(gx < -1e-10) or _i23_np.any(gz < -1e-10) or _i23_np.any(gx > cols - 1 + 1e-10) or _i23_np.any(gz > rows - 1 + 1e-10):
        raise ValueError('geometry leaves finite source grid')
    gx, gz = (_i23_np.clip(gx, 0.0, cols - 1), _i23_np.clip(gz, 0.0, rows - 1))
    x0 = _i23_np.minimum(_i23_np.floor(gx).astype(_i23_np.int64), cols - 2)
    z0 = _i23_np.minimum(_i23_np.floor(gz).astype(_i23_np.int64), rows - 2)
    u, v = (gx - x0, gz - z0)
    if require_valid:
        mask = terrain.valid_mask
        if not _i23_np.all(mask[z0, x0] & mask[z0, x0 + 1] & mask[z0 + 1, x0] & mask[z0 + 1, x0 + 1]):
            raise ValueError('unknown original-bed interpolation stencil')
    value = (1.0 - u) * (1.0 - v) * height[z0, x0] + u * (1.0 - v) * height[z0, x0 + 1] + (1.0 - u) * v * height[z0 + 1, x0] + u * v * height[z0 + 1, x0 + 1]
    return (value, z0 * cols + x0)

def _segment_points(a, b, terrain):
    cuts = [0.0, 1.0]
    for axis, origin, spacing in ((0, terrain.x0_m, terrain.dx_m), (1, terrain.z0_m, terrain.dz_m)):
        delta = b[axis] - a[axis]
        if delta == 0.0:
            continue
        lo = _i23_math.floor((min(a[axis], b[axis]) - origin) / spacing)
        hi = _i23_math.ceil((max(a[axis], b[axis]) - origin) / spacing)
        for index in range(lo, hi + 1):
            t = (origin + index * spacing - a[axis]) / delta
            if 1e-12 < t < 1.0 - 1e-12:
                cuts.append(t)
    cuts = _i23_np.unique(_i23_np.asarray(cuts))
    return (a + cuts[:, None] * (b - a), cuts)

def _route_slope(points, receiver, terrain):
    for start, target in enumerate(receiver):
        if target < 0:
            continue
        samples, parameter = _segment_points(points[start], points[target], terrain)
        height, _ = _metric_channel_geometry_sample(terrain.elevation_m, samples, terrain)
        if _i23_np.any(_i23_np.diff(height) >= -1e-10):
            raise ValueError('candidate crosses original-bed flat or uphill segment')
        for k in range(len(parameter) - 1):
            t0, t1 = parameter[k:k + 2]
            middle = points[start] + (t0 + t1) / 2.0 * (points[target] - points[start])
            hm = _metric_channel_geometry_sample(terrain.elevation_m, middle, terrain)[0][0]
            left = (4.0 * hm - 3.0 * height[k] - height[k + 1]) / (t1 - t0)
            right = (height[k] + 3.0 * height[k + 1] - 4.0 * hm) / (t1 - t0)
            if left >= -1e-10 or right >= -1e-10:
                raise ValueError('candidate has uphill original-bed derivative')

def _minimum_source_slope(points, receiver, terrain):
    minimum = _i23_math.inf
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = (points[i], points[j])
        samples, parameter = _segment_points(a, b, terrain)
        height = _metric_channel_geometry_sample(terrain.elevation_m, samples, terrain)[0]
        length = float(_i23_np.linalg.norm(b - a))
        for k in range(len(parameter) - 1):
            t0, t1 = parameter[k:k + 2]
            middle = a + (t0 + t1) / 2.0 * (b - a)
            hm = _metric_channel_geometry_sample(terrain.elevation_m, middle, terrain)[0][0]
            left = (4.0 * hm - 3.0 * height[k] - height[k + 1]) / ((t1 - t0) * length)
            right = (height[k] + 3.0 * height[k + 1] - 4.0 * hm) / ((t1 - t0) * length)
            minimum = min(minimum, -left, -right)
    return minimum

def _metric_channel_geometry_orientation(a, b, c):
    ab, ac = (b - a, c - a)
    return float(ab[0] * ac[1] - ab[1] * ac[0])

def _segments_intersect(a, b, c, d):
    p = _i23_np.array([_metric_channel_geometry_orientation(a, b, c), _metric_channel_geometry_orientation(a, b, d), _metric_channel_geometry_orientation(c, d, a), _metric_channel_geometry_orientation(c, d, b)])
    if p[0] * p[1] < 0.0 and p[2] * p[3] < 0.0:
        return True
    for point, start, end, cross in ((c, a, b, p[0]), (d, a, b, p[1]), (a, c, d, p[2]), (b, c, d, p[3])):
        if abs(cross) <= 1e-10 and _i23_np.all(point >= _i23_np.minimum(start, end) - 1e-10) and _i23_np.all(point <= _i23_np.maximum(start, end) + 1e-10):
            return True
    return False

def _route_crossings(points, receiver):
    edges = [(i, int(j)) for i, j in enumerate(receiver) if j >= 0]
    for index, (i, j) in enumerate(edges):
        for k, l in edges[index + 1:]:
            shared = {i, j} & {k, l}
            if shared:
                common = points[next(iter(shared))]
                other1 = points[j if i in shared else i] - common
                other2 = points[l if k in shared else k] - common
                if abs(_metric_channel_geometry_orientation(_i23_np.zeros(2), other1, other2)) <= 1e-10 and _i23_np.dot(other1, other2) > 0.0:
                    raise ValueError('adjacent centerline backtracking')
            elif _segments_intersect(points[i], points[j], points[k], points[l]):
                raise ValueError('nonadjacent centerline crossing')

def _segment_box_distance(a, b, low, high):
    delta = b - a
    if _i23_np.all(a >= low) and _i23_np.all(a <= high) or (_i23_np.all(b >= low) and _i23_np.all(b <= high)):
        return 0.0
    for axis in (0, 1):
        if delta[axis] == 0.0:
            continue
        for boundary in (low[axis], high[axis]):
            t = (boundary - a[axis]) / delta[axis]
            if 0.0 <= t <= 1.0 and low[1 - axis] <= a[1 - axis] + t * delta[1 - axis] <= high[1 - axis]:
                return 0.0
    endpoint = min((_i23_np.linalg.norm(_i23_np.maximum(low - p, _i23_np.maximum(p - high, 0.0))) for p in (a, b)))
    corners = (_i23_np.array([x, z]) for x in (low[0], high[0]) for z in (low[1], high[1]))
    return min(endpoint, *(_i23_np.linalg.norm(c - (a + _i23_np.clip(_i23_np.dot(c - a, delta) / _i23_np.dot(delta, delta), 0.0, 1.0) * delta)) for c in corners))

def _footprint(points, receiver, width, depth, terrain, owner, corridor, lake, original_owner, fine_spacing):
    rows, cols = terrain.elevation_m.shape
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = (points[i], points[j])
        radius = max(width[i] / 2.0 + BANK_SLOPE * depth[i], width[j] / 2.0 + BANK_SLOPE * depth[j])
        if _i23_np.any(_i23_np.minimum(a, b) - radius < [terrain.x0_m, terrain.z0_m]) or _i23_np.any(_i23_np.maximum(a, b) + radius > [terrain.x0_m + (cols - 1) * terrain.dx_m, terrain.z0_m + (rows - 1) * terrain.dz_m]):
            raise ValueError('complete bank footprint leaves source terrain')
        x0 = max(0, _i23_math.floor((min(a[0], b[0]) - radius - terrain.x0_m) / terrain.dx_m))
        x1 = min(cols - 2, _i23_math.floor((max(a[0], b[0]) + radius - terrain.x0_m) / terrain.dx_m))
        z0 = max(0, _i23_math.floor((min(a[1], b[1]) - radius - terrain.z0_m) / terrain.dz_m))
        z1 = min(rows - 2, _i23_math.floor((max(a[1], b[1]) + radius - terrain.z0_m) / terrain.dz_m))
        source_owner = original_owner[i]
        if source_owner < 0:
            raise ValueError('unknown source owner')
        for z in range(z0, z1 + 1):
            for x in range(x0, x1 + 1):
                low = _i23_np.array([terrain.x0_m + x * terrain.dx_m, terrain.z0_m + z * terrain.dz_m])
                high = low + [terrain.dx_m, terrain.dz_m]
                if _segment_box_distance(a, b, low, high) > radius + 1e-10:
                    continue
                stencil = _i23_np.s_[z:z + 2, x:x + 2]
                if not terrain.valid_mask[stencil].all() or not corridor[stencil].all() or _i23_np.any(owner[stencil] != source_owner):
                    raise ValueError('bank footprint crosses unknown, divide, corridor, or lake')

def _wet_guard(samples, lake, terrain):
    """Protect every native source cell touching known wet support, including mixed cells."""
    wet_cells = lake[:-1, :-1] | lake[:-1, 1:] | lake[1:, :-1] | lake[1:, 1:]
    gx = (samples[:, 0] - terrain.x0_m) / terrain.dx_m
    gz = (samples[:, 1] - terrain.z0_m) / terrain.dz_m
    ix = _i23_np.floor(gx + 1e-10).astype(_i23_np.int64)
    iz = _i23_np.floor(gz + 1e-10).astype(_i23_np.int64)
    on_x = _i23_np.abs(gx - _i23_np.round(gx)) <= 1e-10
    on_z = _i23_np.abs(gz - _i23_np.round(gz)) <= 1e-10
    protected = _i23_np.zeros(len(samples), bool)
    for x in (ix, ix - 1):
        for z in (iz, iz - 1):
            valid = (x >= 0) & (x < wet_cells.shape[1]) & (z >= 0) & (z < wet_cells.shape[0])
            valid &= (x == ix) | on_x
            valid &= (z == iz) | on_z
            protected[valid] |= wet_cells[z[valid], x[valid]]
    return protected

def _cut(points, receiver, width, depth, samples, *, lake=None, terrain=None):
    cut = _i23_np.zeros(len(samples), _i23_np.float64)
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = (points[i], points[j])
        delta = b - a
        fraction = _i23_np.clip((samples - a) @ delta / _i23_np.dot(delta, delta), 0.0, 1.0)
        distance = _i23_np.linalg.norm(samples - (a + fraction[:, None] * delta), axis=1)
        half_width = ((1.0 - fraction) * width[i] + fraction * width[j]) / 2.0
        local_depth = (1.0 - fraction) * depth[i] + fraction * depth[j]
        bank = BANK_SLOPE * local_depth
        envelope = _i23_np.where(distance <= half_width, local_depth, _i23_np.maximum(0.0, (half_width + bank - distance) / BANK_SLOPE))
        cut = _i23_np.maximum(cut, envelope)
    if lake is not None and lake.any():
        wet_cells = lake[:-1, :-1] | lake[:-1, 1:] | lake[1:, :-1] | lake[1:, 1:]
        rows, cols = _i23_np.nonzero(wet_cells)
        centers = _i23_np.column_stack((terrain.x0_m + (cols + 0.5) * terrain.dx_m, terrain.z0_m + (rows + 0.5) * terrain.dz_m))
        distance = _i23_cKDTree(centers).query(samples)[0]
        lower_bound = _i23_np.maximum(0.0, distance - _i23_math.hypot(terrain.dx_m, terrain.dz_m) / 2.0)
        taper_rate = _minimum_source_slope(points, receiver, terrain) * 0.25
        cut = _i23_np.minimum(cut, lower_bound * taper_rate)
        cut[_wet_guard(samples, lake, terrain)] = 0.0
    return cut

def _metric_channel_geometry_point_segment_distance(point, start, end):
    delta = end - start
    fraction = _i23_np.clip(_i23_np.dot(point - start, delta) / _i23_np.dot(delta, delta), 0.0, 1.0)
    return float(_i23_np.linalg.norm(point - start - fraction * delta))

def _cut_overlap(points, receiver, width, depth):
    edges = [(i, int(j)) for i, j in enumerate(receiver) if j >= 0]
    adjacent = {frozenset((i, j)) for i, j in edges}
    for index, (i, j) in enumerate(edges):
        for other, (k, l) in enumerate(edges[index + 1:], start=index + 1):
            nearby = bool({i, j} & {k, l}) or any((frozenset((a, b)) in adjacent for a in (i, j) for b in (k, l)))
            if nearby:
                continue
            radius1 = max(width[i] / 2.0 + BANK_SLOPE * depth[i], width[j] / 2.0 + BANK_SLOPE * depth[j])
            radius2 = max(width[k] / 2.0 + BANK_SLOPE * depth[k], width[l] / 2.0 + BANK_SLOPE * depth[l])
            distance = min((_metric_channel_geometry_point_segment_distance(p, points[k], points[l]) for p in (points[i], points[j])))
            distance = min(distance, *(_metric_channel_geometry_point_segment_distance(p, points[i], points[j]) for p in (points[k], points[l])))
            if distance <= radius1 + radius2 + 1e-10:
                raise ValueError('nonadjacent cut supports overlap')

def _modified_bed_slope(points, receiver, vertices, triangles, bed, spacing):
    origin = vertices[0]
    nx = int(triangles[2, 1])
    nz = int(triangles[0, 2]) // nx
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = (points[i], points[j])
        delta = b - a
        parameters = [0.0, 1.0]
        for axis in (0, 1):
            if abs(delta[axis]) <= 1e-15:
                continue
            for index in range(int(_i23_math.floor((min(a[axis], b[axis]) - origin[axis]) / spacing)), int(_i23_math.ceil((max(a[axis], b[axis]) - origin[axis]) / spacing)) + 1):
                t = (origin[axis] + index * spacing - a[axis]) / delta[axis]
                if 1e-12 < t < 1.0 - 1e-12:
                    parameters.append(t)
        grid_breaks = _i23_np.unique(parameters)
        for t0, t1 in zip(grid_breaks[:-1], grid_breaks[1:]):
            middle = a + (t0 + t1) / 2.0 * delta
            col = min(max(int(_i23_math.floor((middle[0] - origin[0]) / spacing)), 0), nx - 2)
            row = min(max(int(_i23_math.floor((middle[1] - origin[1]) / spacing)), 0), nz - 2)
            low = origin + _i23_np.array([col, row]) * spacing
            for normal, constant in ((_i23_np.array([1.0, -1.0]), 0.0), (_i23_np.array([1.0, 1.0]), spacing)):
                divisor = float(_i23_np.dot(normal, delta))
                if abs(divisor) <= 1e-15:
                    continue
                t = (constant - _i23_np.dot(normal, a - low)) / divisor
                if t0 + 1e-12 < t < t1 - 1e-12:
                    parameters.append(t)
        parameters = _i23_np.unique(parameters)
        for t0, t1 in zip(parameters[:-1], parameters[1:]):
            middle = a + (t0 + t1) / 2.0 * delta
            col = min(max(int(_i23_math.floor((middle[0] - origin[0]) / spacing)), 0), nx - 2)
            row = min(max(int(_i23_math.floor((middle[1] - origin[1]) / spacing)), 0), nz - 2)
            cell = row * (nx - 1) + col
            for tri_id in range(4 * cell, 4 * cell + 4):
                ids = triangles[tri_id]
                triangle = vertices[ids]
                matrix = _i23_np.column_stack((triangle[1] - triangle[0], triangle[2] - triangle[0]))
                uv = _i23_np.linalg.solve(matrix, middle - triangle[0])
                if min(1.0 - uv.sum(), uv[0], uv[1]) < -1e-09:
                    continue
                h = []
                for t in (t0, t1):
                    uv = _i23_np.linalg.solve(matrix, a + t * delta - triangle[0])
                    h.append(bed[ids[0]] + uv @ (bed[ids[1:]] - bed[ids[0]]))
                if h[1] - h[0] >= -1e-10 * (t1 - t0):
                    raise ValueError('canonical cut bed is flat or uphill')
                break
            else:
                raise ValueError('centerline leaves canonical mesh')

def _mesh(points, receiver, width, depth, terrain, config):
    radius = float(_i23_np.max(width / 2.0 + BANK_SLOPE * depth))
    spacing = config.fine_spacing_m
    first = _i23_np.floor((_i23_np.min(points, axis=0) - radius - [terrain.x0_m, terrain.z0_m]) / spacing).astype(int)
    last = _i23_np.ceil((_i23_np.max(points, axis=0) + radius - [terrain.x0_m, terrain.z0_m]) / spacing).astype(int)
    first = _i23_np.maximum(first, 0)
    last = _i23_np.minimum(last, _i23_np.array([(terrain.elevation_m.shape[1] - 1) * int(round(terrain.dx_m / spacing)), (terrain.elevation_m.shape[0] - 1) * int(round(terrain.dz_m / spacing))]))
    nx, nz = (int(last[0] - first[0] + 1), int(last[1] - first[1] + 1))
    if nx < 2 or nz < 2 or nx * nz + (nx - 1) * (nz - 1) > config.max_vertices:
        raise ValueError('geometry vertex budget exceeded')
    x = terrain.x0_m + _i23_np.arange(first[0], last[0] + 1) * spacing
    z = terrain.z0_m + _i23_np.arange(first[1], last[1] + 1) * spacing
    xx, zz = _i23_np.meshgrid(x, z)
    corners = _i23_np.column_stack((xx.ravel(), zz.ravel()))
    centers = _i23_np.column_stack(((xx[:-1, :-1] + spacing / 2.0).ravel(), (zz[:-1, :-1] + spacing / 2.0).ravel()))
    vertices = _i23_np.vstack((corners, centers))
    triangles = _i23_np.empty((4 * (nx - 1) * (nz - 1), 3), _i23_np.int64)
    cell = 0
    for row in range(nz - 1):
        for col in range(nx - 1):
            sw = row * nx + col
            se, nw, ne = (sw + 1, sw + nx, sw + nx + 1)
            center = nx * nz + cell
            triangles[4 * cell:4 * cell + 4] = ((sw, se, center), (se, ne, center), (ne, nw, center), (nw, sw, center))
            cell += 1
    return (vertices, triangles)

def _validate_fan_mesh(vertices, triangles, points, width, depth, terrain, config):
    if vertices.dtype != _i23_np.float64 or vertices.ndim != 2 or vertices.shape[1] != 2 or (not _i23_np.isfinite(vertices).all()) or (vertices.shape[0] > config.max_vertices) or (triangles.dtype != _i23_np.int64) or (triangles.ndim != 2) or (triangles.shape[1] != 3) or (len(triangles) < 4) or (len(triangles) % 4):
        raise ValueError('invalid canonical fan4 arrays')
    corner_count = int(triangles[0, 2])
    nx = int(triangles[2, 1])
    if nx < 2 or corner_count % nx:
        raise ValueError('invalid canonical fan4 dimensions')
    nz = corner_count // nx
    if nz < 2 or corner_count + (nx - 1) * (nz - 1) != len(vertices) or len(triangles) != 4 * (nx - 1) * (nz - 1):
        raise ValueError('invalid canonical fan4 dimensions')
    spacing = config.fine_spacing_m
    first = vertices[0]
    radius = float(_i23_np.max(width / 2.0 + BANK_SLOPE * depth))
    lower = _i23_np.maximum(_i23_np.floor((_i23_np.min(points, axis=0) - radius - [terrain.x0_m, terrain.z0_m]) / spacing).astype(int), 0)
    upper = _i23_np.minimum(_i23_np.ceil((_i23_np.max(points, axis=0) + radius - [terrain.x0_m, terrain.z0_m]) / spacing).astype(int), [(terrain.elevation_m.shape[1] - 1) * int(round(terrain.dx_m / spacing)), (terrain.elevation_m.shape[0] - 1) * int(round(terrain.dz_m / spacing))])
    if nx != upper[0] - lower[0] + 1 or nz != upper[1] - lower[1] + 1 or (not _i23_np.allclose(first, [terrain.x0_m + lower[0] * spacing, terrain.z0_m + lower[1] * spacing], rtol=0.0, atol=1e-10)):
        raise ValueError('canonical mesh does not cover declared channel support')
    for row in range(nz):
        for col in range(nx):
            expected = first + [col * spacing, row * spacing]
            if not _i23_np.allclose(vertices[row * nx + col], expected, rtol=0.0, atol=1e-10):
                raise ValueError('canonical fan4 corner coordinate mismatch')
    for row in range(nz - 1):
        for col in range(nx - 1):
            cell = row * (nx - 1) + col
            sw = row * nx + col
            se, nw, ne = (sw + 1, sw + nx, sw + nx + 1)
            center = corner_count + cell
            if not _i23_np.allclose(vertices[center], vertices[sw] + spacing / 2.0, rtol=0.0, atol=1e-10):
                raise ValueError('canonical fan4 center coordinate mismatch')
            expected = ((sw, se, center), (se, ne, center), (ne, nw, center), (nw, sw, center))
            if not _i23_np.array_equal(triangles[4 * cell:4 * cell + 4], expected):
                raise ValueError('canonical fan4 triangle incidence mismatch')

def _mesh_volume(vertices, triangles, heights, *, datum=0.0):
    xy = vertices[triangles]
    area = _i23_np.abs((xy[:, 1, 0] - xy[:, 0, 0]) * (xy[:, 2, 1] - xy[:, 0, 1]) - (xy[:, 2, 0] - xy[:, 0, 0]) * (xy[:, 1, 1] - xy[:, 0, 1])) / 2.0
    return float(_i23_np.sum(area * _i23_np.mean(heights[triangles] - datum, axis=1)))

def _port_observations(points, receiver, width, depth, vertices, triangles, cut):
    edges = _i23_np.array([(i, int(j)) for i, j in enumerate(receiver) if j >= 0], _i23_np.int64).reshape(-1, 2)
    profile = _i23_np.empty((len(edges), 4, 2), _i23_np.float64)
    midpoint = _i23_np.empty((len(edges), 2), _i23_np.float64)
    triangle_ids = _i23_np.empty((len(edges), 4), _i23_np.int64)
    barycentric = _i23_np.empty((len(edges), 4, 3), _i23_np.float64)
    cuts = _i23_np.empty((len(edges), 4), _i23_np.float64)
    x0, z0 = _i23_np.min(vertices, axis=0)
    xs = _i23_np.unique(vertices[:, 0])
    zs = _i23_np.unique(vertices[:, 1])
    spacing = 2.0 * (xs[1] - xs[0])
    nx = int(round((xs[-1] - xs[0]) / spacing)) + 1
    nz = int(round((zs[-1] - zs[0]) / spacing)) + 1
    for edge_index, (i, j) in enumerate(edges):
        a, b = (points[i], points[j])
        center = (a + b) / 2.0
        flow = (b - a) / _i23_np.linalg.norm(b - a)
        normal = _i23_np.array([-flow[1], flow[0]])
        half = (width[i] + width[j]) / 4.0
        bank = BANK_SLOPE * (depth[i] + depth[j]) / 2.0
        offsets = (-half - bank, -half, half, half + bank)
        midpoint[edge_index] = center
        for k, offset in enumerate(offsets):
            p = center + offset * normal
            profile[edge_index, k] = p
            cx = min(max(_i23_math.floor((p[0] - x0) / spacing), 0), nx - 2)
            cz = min(max(_i23_math.floor((p[1] - z0) / spacing), 0), nz - 2)
            square = cz * (nx - 1) + cx
            found = False
            for tri_id in range(4 * square, 4 * square + 4):
                triangle = vertices[triangles[tri_id]]
                matrix = _i23_np.column_stack((triangle[1] - triangle[0], triangle[2] - triangle[0]))
                uv = _i23_np.linalg.solve(matrix, p - triangle[0])
                weights = _i23_np.array([1.0 - uv.sum(), uv[0], uv[1]])
                if _i23_np.min(weights) >= -1e-09:
                    triangle_ids[edge_index, k] = tri_id
                    barycentric[edge_index, k] = weights
                    cuts[edge_index, k] = weights @ cut[triangles[tri_id]]
                    found = True
                    break
            if not found:
                raise ValueError('canonical port leaves represented mesh')
    return (edges, midpoint, profile, triangle_ids, barycentric, cuts)

def _terrain_metadata(terrain):
    return {key: getattr(terrain, key) for key in terrain.__dataclass_fields__ if key not in ('elevation_m', 'valid_mask')}

def _constraints_identity(arrays, terrain_identity):
    from terrain_pipeline.common_infra import identity as _i23_identity
    return _i23_identity({key: arrays[key] for key in ('owner_grid', 'corridor_mask', 'lake_mask', 'anchor_mask')}, {'terrain_identity_sha256': terrain_identity, 'provenance': 'explicit_caller_supplied_unverified_source_masks'})

def _topology(ids, receiver, terrain):
    n = len(ids)
    if ids.dtype != _i23_np.int64 or ids.shape != (n,) or (not 2 <= n <= 128) or (_i23_np.unique(ids).size != n) or _i23_np.any(ids < 0) or _i23_np.any(ids >= terrain.elevation_m.size) or (not terrain.valid_mask.ravel()[ids].all()) or (receiver.dtype != _i23_np.int64) or (receiver.shape != (n,)) or _i23_np.any((receiver < -1) | (receiver >= n) | (receiver == _i23_np.arange(n))):
        raise ValueError('invalid bounded selected source graph')
    for start in range(n):
        seen = set()
        current = start
        while current >= 0:
            if current in seen:
                raise ValueError('selected channel graph cycle')
            seen.add(current)
            current = int(receiver[current])

def _inputs(terrain, ids, receiver, width, depth, owner, corridor, lake, anchors, config, lake_stage):
    from terrain_pipeline.common_infra import TerrainGrid as _i23_TerrainGrid
    if not isinstance(terrain, _i23_TerrainGrid) or not isinstance(config, GeometryConfig):
        raise ValueError('TerrainGrid and GeometryConfig required')
    _topology(ids, receiver, terrain)
    n = len(ids)
    for name, value in (('width_m', width), ('depth_m', depth)):
        if not isinstance(value, _i23_np.ndarray) or value.dtype != _i23_np.float64 or value.shape != (n,) or (not _i23_np.isfinite(value).all()) or _i23_np.any(value <= 0.0):
            raise ValueError('finite positive physical ' + name + ' required')
    if _i23_np.any(depth > config.max_cut_m):
        raise ValueError('requested channel cut exceeds max_cut_m')
    if not _i23_np.isfinite(width / 2.0 + BANK_SLOPE * depth).all():
        raise ValueError('nonfinite bank support radius')
    shape = terrain.elevation_m.shape
    if not isinstance(owner, _i23_np.ndarray) or owner.dtype != _i23_np.int64 or owner.shape != shape or (not isinstance(corridor, _i23_np.ndarray)) or (corridor.dtype != bool) or (corridor.shape != shape) or (not isinstance(lake, _i23_np.ndarray)) or (lake.dtype != bool) or (lake.shape != shape) or (not isinstance(anchors, _i23_np.ndarray)) or (anchors.dtype != bool) or (anchors.shape != (n,)):
        raise ValueError('source owner/corridor/lake/anchor arrays required')
    if lake_stage is not None and (isinstance(lake_stage, bool) or not isinstance(lake_stage, (int, float)) or (not _i23_math.isfinite(lake_stage))):
        raise ValueError('finite explicit lake_stage_m required')
    if lake.ravel()[ids].any() and lake_stage is None:
        raise ValueError('lake endpoint requires explicit lake stage')
    if _i23_np.any(lake.ravel()[ids] & (receiver >= 0)):
        raise ValueError('interior centerline cannot enter lake support')
    if not _i23_np.any(receiver >= 0):
        raise ValueError('selected channel requires at least one original-bed edge')
    selected_owner = owner.ravel()[ids]
    if _i23_np.any(selected_owner < 0) or _i23_np.any(~corridor.ravel()[ids]) or _i23_np.any((receiver >= 0) & (selected_owner != selected_owner[_i23_np.maximum(receiver, 0)])):
        raise ValueError('selected source nodes cross owner or corridor')
    if lake.ravel()[ids].any() and lake_stage < _i23_np.max(terrain.elevation_m.ravel()[ids[lake.ravel()[ids]]]):
        raise ValueError('lake stage does not cover original wet terminal bed')
    if not _i23_math.isclose(terrain.dx_m / config.fine_spacing_m, round(terrain.dx_m / config.fine_spacing_m), abs_tol=1e-10) or not _i23_math.isclose(terrain.dz_m / config.fine_spacing_m, round(terrain.dz_m / config.fine_spacing_m), abs_tol=1e-10):
        raise ValueError('fine spacing must divide both native grid spacings')
    if config.fine_spacing_m > _i23_np.min(width) / config.width_resolution:
        raise ValueError('channel width underresolved by fine lattice')

def build_channel_geometry(terrain, node_cell_ids, receiver, width_m, depth_m, *, owner_grid, corridor_mask, lake_mask, anchor_mask, config=None, lake_stage_m=None):
    from terrain_pipeline.common_infra import identity as _i23_identity
    from terrain_pipeline.common_infra import readonly as _i23_readonly
    if config is None:
        config = GeometryConfig()
    _inputs(terrain, node_cell_ids, receiver, width_m, depth_m, owner_grid, corridor_mask, lake_mask, anchor_mask, config, lake_stage_m)
    cols = terrain.elevation_m.shape[1]
    original = _i23_np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m, terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    effective_depth = depth_m.copy()
    effective_depth[lake_mask.ravel()[node_cell_ids]] = 0.0
    original_owner = owner_grid.ravel()[node_cell_ids]
    points = original.copy()
    donors = _i23_np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    lake_nodes = lake_mask.ravel()[node_cell_ids]
    fixed = anchor_mask | (donors != 1) | (receiver < 0) | lake_nodes
    fixed |= (receiver >= 0) & lake_nodes[_i23_np.maximum(receiver, 0)]
    _route_slope(points, receiver, terrain)
    _route_crossings(points, receiver)
    for iteration in range(config.smoothing_iterations):
        changed = False
        step = config.max_offset_m / 2.0 ** (iteration // 4 + 1)
        if step <= 0.0:
            break
        for i in _i23_np.flatnonzero(~fixed):
            donor = int(_i23_np.flatnonzero(receiver == i)[0])
            target = int(receiver[i])
            bend = (points[donor] + points[target]) / 2.0
            scale = min(terrain.dx_m, terrain.dz_m)

            def objective(p):
                height = _metric_channel_geometry_sample(terrain.elevation_m, p, terrain)[0][0]
                return config.valley_weight * height + config.curvature_weight * _i23_np.linalg.norm(p - bend) ** 2 / scale
            best = points[i].copy()
            best_score = objective(best)
            for offset in ((step, 0.0), (-step, 0.0), (0.0, step), (0.0, -step)):
                candidate = points[i] + offset
                if _i23_np.linalg.norm(candidate - original[i]) > config.max_offset_m:
                    continue
                trial = points.copy()
                trial[i] = candidate
                try:
                    _metric_channel_geometry_sample(terrain.elevation_m, candidate, terrain)
                    _route_slope(trial, receiver, terrain)
                    _route_crossings(trial, receiver)
                    _footprint(trial, receiver, width_m, effective_depth, terrain, owner_grid, corridor_mask, lake_mask, original_owner, config.fine_spacing_m)
                except ValueError:
                    continue
                score = objective(candidate)
                if score < best_score - 1e-12:
                    best, best_score = (candidate, score)
            if not _i23_np.array_equal(best, points[i]):
                points[i] = best
                changed = True
        if not changed and iteration >= 4:
            break
    _route_slope(points, receiver, terrain)
    _route_crossings(points, receiver)
    _footprint(points, receiver, width_m, effective_depth, terrain, owner_grid, corridor_mask, lake_mask, original_owner, config.fine_spacing_m)
    vertices, triangles = _mesh(points, receiver, width_m, effective_depth, terrain, config)
    _cut_overlap(points, receiver, width_m, effective_depth)
    source, source_cell_ids = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)
    cut = _cut(points, receiver, width_m, effective_depth, vertices, lake=lake_mask, terrain=terrain)
    if not _i23_np.isfinite(cut).all() or _i23_np.any(cut < 0.0) or _i23_np.any(cut > config.max_cut_m + 1e-12):
        raise ValueError('invalid represented cut depth')
    bed = source - cut
    _modified_bed_slope(points, receiver, vertices, triangles, bed, config.fine_spacing_m)
    edges, midpoint, profile, port_tri, bary, port_cut = _port_observations(points, receiver, width_m, effective_depth, vertices, triangles, cut)
    volume = _mesh_volume(vertices, triangles, cut)
    datum = float(source[0])
    source_volume = _mesh_volume(vertices, triangles, source, datum=datum)
    final_volume = _mesh_volume(vertices, triangles, bed, datum=datum)
    arrays = dict(source_node_cell_ids=node_cell_ids.copy(), receiver=receiver.copy(), original_node_xz_m=original, node_xz_m=points, node_source_elevation_m=_metric_channel_geometry_sample(terrain.elevation_m, points, terrain)[0], width_m=width_m.copy(), depth_m=depth_m.copy(), anchor_mask=anchor_mask.copy(), vertices_xz_m=vertices, source_elevation_m=source, cut_depth_m=cut, bed_elevation_m=bed, triangles=triangles, source_cell_ids=source_cell_ids, source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(), owner_grid=owner_grid.copy(), corridor_mask=corridor_mask.copy(), lake_mask=lake_mask.copy(), canonical_port_edge_node_indices=edges, canonical_port_xz_m=midpoint, canonical_port_profile_xz_m=profile, canonical_port_triangle_ids=port_tri, canonical_port_barycentric=bary, canonical_port_cut_depth_m=port_cut)
    metadata = dict(schema=METRIC_CHANNEL_GEOMETRY_SCHEMA, algorithm=METRIC_CHANNEL_GEOMETRY_ALGORITHM, terrain_metadata=_terrain_metadata(terrain), source_identity_sha256=terrain.identity_sha256, constraints_identity_sha256=_constraints_identity(arrays, terrain.identity_sha256), constraints_provenance='explicit_caller_supplied_unverified_source_masks', config=_i23_asdict(config), lake_stage_m=lake_stage_m, lake_cut_policy='zero_on_native_cells_touching_known_wet_nodes', bank_slope_h_per_v=BANK_SLOPE, geometry_measure='canonical_piecewise_linear_heightfield', cut_volume_m3=volume, deposition_bulk_m3=0.0, original_mesh_volume_m3=source_volume, final_mesh_volume_m3=final_volume, geometry_verified=True, hydraulic_ready=False, natural_outlet_verified=False, publishable=False, limitations=list(LIMITATIONS))
    arrays = {name: _i23_readonly(value) for name, value in arrays.items()}
    bundle = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i23_identity(arrays, metadata)}
    validate_channel_geometry(bundle)
    return bundle

def validate_channel_geometry(bundle):
    from terrain_pipeline.common_infra import identity as _i23_identity
    from terrain_pipeline.common_infra import TerrainGrid as _i23_TerrainGrid
    if not isinstance(bundle, dict) or set(bundle) != {'arrays', 'metadata', 'identity_sha256'}:
        raise ValueError('invalid channel geometry bundle')
    arrays, meta = (bundle['arrays'], bundle['metadata'])
    if set(arrays) != set(ARRAYS) or set(meta) != {'schema', 'algorithm', 'terrain_metadata', 'source_identity_sha256', 'constraints_identity_sha256', 'constraints_provenance', 'config', 'lake_stage_m', 'lake_cut_policy', 'bank_slope_h_per_v', 'geometry_measure', 'cut_volume_m3', 'deposition_bulk_m3', 'original_mesh_volume_m3', 'final_mesh_volume_m3', 'geometry_verified', 'hydraulic_ready', 'natural_outlet_verified', 'publishable', 'limitations'} or meta['schema'] != METRIC_CHANNEL_GEOMETRY_SCHEMA or (meta['algorithm'] != METRIC_CHANNEL_GEOMETRY_ALGORITHM) or (meta['bank_slope_h_per_v'] != BANK_SLOPE) or (meta['geometry_measure'] != 'canonical_piecewise_linear_heightfield') or (meta['lake_cut_policy'] != 'zero_on_native_cells_touching_known_wet_nodes') or (meta['limitations'] != LIMITATIONS) or (meta['geometry_verified'] is not True) or (meta['constraints_provenance'] != 'explicit_caller_supplied_unverified_source_masks') or (meta['constraints_identity_sha256'] != _constraints_identity(arrays, meta['source_identity_sha256'])) or any((meta[key] is not False for key in ('hydraulic_ready', 'natural_outlet_verified', 'publishable'))) or (bundle['identity_sha256'] != _i23_identity(arrays, meta)) or (sum((value.nbytes for value in arrays.values())) > METRIC_CHANNEL_GEOMETRY_MAX_BYTES):
        raise ValueError('geometry schema, scope, identity, or budget mismatch')
    config = GeometryConfig(**meta['config'])
    terrain = _i23_TerrainGrid(arrays['source_height_m'], arrays['source_valid_mask'], **meta['terrain_metadata'])
    if terrain.identity_sha256 != meta['source_identity_sha256']:
        raise ValueError('source identity mismatch')
    ids, receiver, width, depth = (arrays[key] for key in ('source_node_cell_ids', 'receiver', 'width_m', 'depth_m'))
    _inputs(terrain, ids, receiver, width, depth, arrays['owner_grid'], arrays['corridor_mask'], arrays['lake_mask'], arrays['anchor_mask'], config, meta['lake_stage_m'])
    cols = terrain.elevation_m.shape[1]
    original = _i23_np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m, terrain.z0_m + ids // cols * terrain.dz_m))
    points = arrays['node_xz_m']
    donors = _i23_np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    lake_nodes = arrays['lake_mask'].ravel()[ids]
    fixed = arrays['anchor_mask'] | (donors != 1) | (receiver < 0) | lake_nodes
    fixed |= (receiver >= 0) & lake_nodes[_i23_np.maximum(receiver, 0)]
    if points.dtype != _i23_np.float64 or points.shape != original.shape or (not _i23_np.isfinite(points).all()) or (not _i23_np.array_equal(arrays['original_node_xz_m'], original)) or (not _i23_np.array_equal(points[fixed], original[fixed])) or _i23_np.any(_i23_np.linalg.norm(points - original, axis=1) > config.max_offset_m + 1e-10):
        raise ValueError('invalid candidate centerline anchors or offsets')
    source_node = _metric_channel_geometry_sample(terrain.elevation_m, points, terrain)[0]
    if not _i23_np.allclose(arrays['node_source_elevation_m'], source_node, rtol=0.0, atol=1e-09):
        raise ValueError('candidate centerline original-bed samples mismatch')
    _route_slope(points, receiver, terrain)
    _route_crossings(points, receiver)
    effective_depth = depth.copy()
    effective_depth[arrays['lake_mask'].ravel()[ids]] = 0.0
    _footprint(points, receiver, width, effective_depth, terrain, arrays['owner_grid'], arrays['corridor_mask'], arrays['lake_mask'], arrays['owner_grid'].ravel()[ids], config.fine_spacing_m)
    vertices, triangles = (arrays['vertices_xz_m'], arrays['triangles'])
    _validate_fan_mesh(vertices, triangles, points, width, effective_depth, terrain, config)
    source, source_cells = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)
    _cut_overlap(points, receiver, width, effective_depth)
    cut = _cut(points, receiver, width, effective_depth, vertices, lake=arrays['lake_mask'], terrain=terrain)
    if not _i23_np.array_equal(arrays['source_cell_ids'], source_cells) or not _i23_np.allclose(arrays['source_elevation_m'], source, rtol=0.0, atol=1e-09) or (not _i23_np.allclose(arrays['cut_depth_m'], cut, rtol=0.0, atol=1e-09)) or (not _i23_np.allclose(arrays['bed_elevation_m'], source - cut, rtol=0.0, atol=1e-09)):
        raise ValueError('original-source interpolation or cut field mismatch')
    _modified_bed_slope(points, receiver, vertices, triangles, source - cut, config.fine_spacing_m)
    port_fields = ('canonical_port_edge_node_indices', 'canonical_port_xz_m', 'canonical_port_profile_xz_m', 'canonical_port_triangle_ids', 'canonical_port_barycentric', 'canonical_port_cut_depth_m')
    expected = _port_observations(points, receiver, width, effective_depth, vertices, triangles, cut)
    if any((not _i23_np.allclose(arrays[key], value, rtol=0.0, atol=1e-09) for key, value in zip(port_fields, expected))):
        raise ValueError('canonical shared mesh port mismatch')
    volume = _mesh_volume(vertices, triangles, cut)
    datum = float(source[0])
    source_volume = _mesh_volume(vertices, triangles, source, datum=datum)
    final_volume = _mesh_volume(vertices, triangles, source - cut, datum=datum)
    if not _i23_np.isfinite([volume, source_volume]).all() or volume < 0.0 or (not _i23_math.isclose(meta['cut_volume_m3'], volume, rel_tol=1e-10, abs_tol=1e-08)) or (meta['deposition_bulk_m3'] != 0.0) or (not _i23_math.isclose(meta['original_mesh_volume_m3'], source_volume, rel_tol=1e-10, abs_tol=1e-08)) or (not _i23_math.isclose(meta['final_mesh_volume_m3'], final_volume, rel_tol=1e-10, abs_tol=1e-08)):
        raise ValueError('canonical cut volume ledger mismatch')
    return True

def save_channel_geometry(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _i23_save_bundle
    _i23_save_bundle(path, bundle, validator=validate_channel_geometry)

def load_channel_geometry(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _i23_load_bundle
    bundle = _i23_load_bundle(path, expected_sha256=expected_sha256, validator=validate_channel_geometry, max_bytes=METRIC_CHANNEL_GEOMETRY_MAX_BYTES)
    if bundle['identity_sha256'] != expected_identity:
        raise ValueError('external geometry identity mismatch')
    return bundle
METRIC_VALLEY_INCISION_SCHEMA = 'terragenesis-metric-valley-incision-v1'
METRIC_VALLEY_INCISION_ALGORITHM = 'fixed-xz-running-min-original-bilinear-incision-v3'
EPSILON_SLOPE_M_PER_M = 1e-05
METRIC_VALLEY_INCISION_ARRAYS = ('source_node_cell_ids', 'receiver', 'node_xz_m', 'width_m', 'base_depth_m', 'source_height_m', 'source_valid_mask', 'owner_grid', 'corridor_mask', 'lake_mask', 'profile_offsets', 'profile_t', 'profile_source_m', 'profile_center_bed_m', 'vertices_xz_m', 'source_elevation_m', 'cut_depth_m', 'bed_elevation_m', 'triangles', 'source_cell_ids', 'canonical_port_edge_node_indices', 'canonical_port_xz_m', 'canonical_port_profile_xz_m', 'canonical_port_triangle_ids', 'canonical_port_barycentric', 'canonical_port_cut_depth_m')

def _metadata_terrain(terrain):
    return {key: getattr(terrain, key) for key in terrain.__dataclass_fields__ if key not in ('elevation_m', 'valid_mask')}

def _profile(points, receiver, depth, terrain, max_cut_m):
    offsets = [0]
    parameters = []
    sources = []
    beds = []
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = (points[i], points[j])
        samples, knots = _segment_points(a, b, terrain)
        values = _metric_channel_geometry_sample(terrain.elevation_m, samples, terrain)[0]
        length = float(_i41_np.linalg.norm(b - a))
        extra = []
        for k in range(len(knots) - 1):
            t0, t1 = knots[k:k + 2]
            tm = (t0 + t1) / 2.0
            vm = _metric_channel_geometry_sample(terrain.elevation_m, a + tm * (b - a), terrain)[0][0]
            curvature = 2.0 * (values[k] + values[k + 1] - 2.0 * vm) / (t1 - t0) ** 2
            left_derivative = (values[k + 1] - values[k]) / (t1 - t0) - curvature * (t1 - t0)
            tilted_derivative = left_derivative - (depth[j] - depth[i]) + EPSILON_SLOPE_M_PER_M * length
            stationary = t0 - tilted_derivative / (2.0 * curvature) if abs(curvature) > 1e-14 else -1.0
            if t0 + 1e-12 < stationary < t1 - 1e-12:
                extra.append(stationary)
        knots = _i41_np.unique(_i41_np.r_[knots, extra])
        crossings = []
        current_min = _i41_math.inf
        for k in range(len(knots) - 1):
            t0, t1 = knots[k:k + 2]
            ts = _i41_np.array([t0, (t0 + t1) / 2.0, t1])
            values3 = _metric_channel_geometry_sample(terrain.elevation_m, a + ts[:, None] * (b - a), terrain)[0]
            tilted3 = values3 - ((1.0 - ts) * depth[i] + ts * depth[j]) + EPSILON_SLOPE_M_PER_M * length * ts
            current_min = min(current_min, float(tilted3[0]))
            du = t1 - t0
            curvature = 2.0 * (tilted3[0] + tilted3[2] - 2.0 * tilted3[1]) / du ** 2
            linear = (tilted3[2] - tilted3[0]) / du - curvature * du
            constant = tilted3[0] - current_min
            roots = _i41_np.roots([curvature, linear, constant]) if abs(curvature) > 1e-14 else _i41_np.array([-constant / linear]) if abs(linear) > 1e-14 else _i41_np.empty(0)
            for root in roots:
                if abs(_i41_np.imag(root)) <= 1e-10 and 1e-12 < _i41_np.real(root) < du - 1e-12:
                    crossings.append(t0 + float(_i41_np.real(root)))
            current_min = min(current_min, float(tilted3[2]))
        knots = _i41_np.unique(_i41_np.r_[knots, crossings])
        samples = a + knots[:, None] * (b - a)
        values = _metric_channel_geometry_sample(terrain.elevation_m, samples, terrain)[0]
        baseline = values - ((1.0 - knots) * depth[i] + knots * depth[j])
        tilted = baseline + EPSILON_SLOPE_M_PER_M * length * knots
        center_bed = _i41_np.minimum.accumulate(tilted) - EPSILON_SLOPE_M_PER_M * length * knots
        if center_bed[0] != baseline[0] or center_bed[-1] < baseline[-1] - 1e-09:
            raise ValueError('fixed endpoint needs additional shared-node incision')
        maximum_cut = float(_i41_np.max(values - center_bed))
        for k in range(len(knots) - 1):
            t0, t1 = knots[k:k + 2]
            middle = (t0 + t1) / 2.0
            source_middle = _metric_channel_geometry_sample(terrain.elevation_m, a + middle * (b - a), terrain)[0][0]
            curvature = 2.0 * (values[k] + values[k + 1] - 2.0 * source_middle) / (t1 - t0) ** 2
            source_left_derivative = (values[k + 1] - values[k]) / (t1 - t0) - curvature * (t1 - t0)
            bed_derivative = (center_bed[k + 1] - center_bed[k]) / (t1 - t0)
            stationary = t0 - (source_left_derivative - bed_derivative) / (2.0 * curvature) if abs(curvature) > 1e-14 else -1.0
            if t0 < stationary < t1:
                height = _metric_channel_geometry_sample(terrain.elevation_m, a + stationary * (b - a), terrain)[0][0]
                target = _i41_np.interp(stationary, knots[k:k + 2], center_bed[k:k + 2])
                maximum_cut = max(maximum_cut, float(height - target))
        if maximum_cut > max_cut_m + 1e-09:
            raise ValueError('continuous centerline incision exceeds configured maximum')
        parameters.extend(knots)
        sources.extend(values)
        beds.extend(center_bed)
        offsets.append(len(parameters))
    return (_i41_np.asarray(offsets, _i41_np.int64), _i41_np.asarray(parameters, _i41_np.float64), _i41_np.asarray(sources, _i41_np.float64), _i41_np.asarray(beds, _i41_np.float64))

def _profile_cut(points, receiver, width, profile, samples, terrain, lake):
    offsets, knots, _, center_bed = profile
    cut = _i41_np.zeros(len(samples), _i41_np.float64)
    edge = 0
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = (points[i], points[j])
        delta = b - a
        t = _i41_np.clip((samples - a) @ delta / _i41_np.dot(delta, delta), 0.0, 1.0)
        position = a + t[:, None] * delta
        distance = _i41_np.linalg.norm(samples - position, axis=1)
        source_at_center = _metric_channel_geometry_sample(terrain.elevation_m, position, terrain)[0]
        lo, hi = offsets[edge:edge + 2]
        target = _i41_np.interp(t, knots[lo:hi], center_bed[lo:hi])
        depth = _i41_np.maximum(source_at_center - target, 0.0)
        half = ((1.0 - t) * width[i] + t * width[j]) / 2.0
        envelope = _i41_np.where(distance <= half, depth, _i41_np.maximum(0.0, (half + BANK_SLOPE * depth - distance) / BANK_SLOPE))
        cut = _i41_np.maximum(cut, envelope)
        edge += 1
    if lake.any():
        guarded = _wet_guard(samples, lake, terrain)
        if _i41_np.any(cut[guarded] > 1e-10):
            raise ValueError('incision enters protected known-wet source cells')
    return cut

def _profile_max_cut_per_edge(points, receiver, profile, terrain):
    """Maximum original bilinear source minus linear profile bed on each edge."""
    offsets, knots, source, bed = profile
    maximum = []
    edge = 0
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        lo, hi = offsets[edge:edge + 2]
        amount = float(_i41_np.max(source[lo:hi] - bed[lo:hi]))
        a, b = (points[i], points[j])
        for k in range(lo, hi - 1):
            t0, t1 = knots[k:k + 2]
            middle = (t0 + t1) / 2.0
            source_middle = float(_metric_channel_geometry_sample(terrain.elevation_m, a + middle * (b - a), terrain)[0][0])
            span = t1 - t0
            curvature = 2.0 * (source[k] + source[k + 1] - 2.0 * source_middle) / span ** 2
            if curvature >= -1e-14:
                continue
            derivative = (source[k + 1] - source[k]) / span - curvature * span - (bed[k + 1] - bed[k]) / span
            local_t = -derivative / (2.0 * curvature)
            if 0.0 < local_t < span:
                candidate = source[k] - bed[k] + derivative * local_t + curvature * local_t ** 2
                amount = max(amount, float(candidate))
        maximum.append(max(0.0, amount))
        edge += 1
    return _i41_np.asarray(maximum, _i41_np.float64)

def _profile_overlap(points, receiver, width, profile, terrain):
    edges = [(i, int(j)) for i, j in enumerate(receiver) if j >= 0]
    adjacency = {frozenset((i, j)) for i, j in edges}
    maximum_cut = _profile_max_cut_per_edge(points, receiver, profile, terrain)
    radii = []
    for edge, (i, j) in enumerate(edges):
        radii.append(max(width[i], width[j]) / 2.0 + BANK_SLOPE * maximum_cut[edge])
    for index, (i, j) in enumerate(edges):
        for other in range(index + 1, len(edges)):
            k, l = edges[other]
            near = bool({i, j} & {k, l}) or any((frozenset((a, b)) in adjacency for a in (i, j) for b in (k, l)))
            if near:
                continue
            distance = min((_metric_channel_geometry_point_segment_distance(p, points[k], points[l]) for p in (points[i], points[j])))
            distance = min(distance, *(_metric_channel_geometry_point_segment_distance(p, points[i], points[j]) for p in (points[k], points[l])))
            if distance <= radii[index] + radii[other] + 1e-10:
                raise ValueError('nonlocal actual incision envelopes may overlap')

def _check_inputs(terrain, ids, receiver, width, depth, owner, corridor, lake, config):
    from terrain_pipeline.common_infra import TerrainGrid as _i41_TerrainGrid
    if not isinstance(terrain, _i41_TerrainGrid) or not isinstance(config, GeometryConfig):
        raise ValueError('TerrainGrid and GeometryConfig required')
    _topology(ids, receiver, terrain)
    n = len(ids)
    for name, value in (('width_m', width), ('base_depth_m', depth)):
        if value.dtype != _i41_np.float64 or value.shape != (n,) or (not _i41_np.isfinite(value).all()) or _i41_np.any(value <= 0.0):
            raise ValueError('positive physical ' + name + ' required')
    if _i41_np.any(depth > config.max_cut_m) or config.max_cut_m > 4.0:
        raise ValueError('fixed 4m maximum incision exceeded')
    shape = terrain.elevation_m.shape
    if owner.dtype != _i41_np.int64 or owner.shape != shape or corridor.dtype != bool or (corridor.shape != shape) or (lake.dtype != bool) or (lake.shape != shape):
        raise ValueError('original owner, corridor and known-wet masks required')
    if _i41_np.any(lake.ravel()[ids]):
        raise ValueError('known wet lake terminal cannot be incised')
    if _i41_np.any(owner.ravel()[ids] < 0) or _i41_np.any(~corridor.ravel()[ids]):
        raise ValueError('source nodes outside owner corridor')
    for i, j in enumerate(receiver):
        if j >= 0 and owner.ravel()[ids[i]] != owner.ravel()[ids[j]]:
            raise ValueError('source edge crosses owner divide')
    if config.fine_spacing_m > _i41_np.min(width) / config.width_resolution:
        raise ValueError('channel width underresolved')
    if not _i41_math.isclose(terrain.dx_m / config.fine_spacing_m, round(terrain.dx_m / config.fine_spacing_m), abs_tol=1e-10) or not _i41_math.isclose(terrain.dz_m / config.fine_spacing_m, round(terrain.dz_m / config.fine_spacing_m), abs_tol=1e-10):
        raise ValueError('fine spacing must divide native source spacing')

def build_valley_incision(terrain, node_cell_ids, receiver, width_m, base_depth_m, *, owner_grid, corridor_mask, lake_mask, config=None):
    from terrain_pipeline.common_infra import identity as _i41_identity
    from terrain_pipeline.common_infra import readonly as _i41_readonly
    config = config or GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0)
    _check_inputs(terrain, node_cell_ids, receiver, width_m, base_depth_m, owner_grid, corridor_mask, lake_mask, config)
    cols = terrain.elevation_m.shape[1]
    points = _i41_np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m, terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, base_depth_m, terrain, config.max_cut_m)
    _footprint(points, receiver, width_m, _i41_np.full(len(points), config.max_cut_m), terrain, owner_grid, corridor_mask, lake_mask, owner_grid.ravel()[node_cell_ids], config.fine_spacing_m)
    _profile_overlap(points, receiver, width_m, profile, terrain)
    vertices, triangles = _mesh(points, receiver, width_m, _i41_np.full(len(points), config.max_cut_m), terrain, config)
    source, source_cells = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)
    cut = _profile_cut(points, receiver, width_m, profile, vertices, terrain, lake_mask)
    if not _i41_np.isfinite(cut).all() or _i41_np.any(cut < 0.0) or _i41_np.any(cut > config.max_cut_m + 1e-10):
        raise ValueError('represented incision exceeds declared depth')
    if _i41_np.any(cut[_wet_guard(vertices, lake_mask, terrain)] > 0.0):
        raise ValueError('known wet support would be incised')
    bed = source - cut
    _modified_bed_slope(points, receiver, vertices, triangles, bed, config.fine_spacing_m)
    ports = _port_observations(points, receiver, width_m, base_depth_m, vertices, triangles, cut)
    arrays = dict(source_node_cell_ids=node_cell_ids.copy(), receiver=receiver.copy(), node_xz_m=points, width_m=width_m.copy(), base_depth_m=base_depth_m.copy(), source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(), owner_grid=owner_grid.copy(), corridor_mask=corridor_mask.copy(), lake_mask=lake_mask.copy(), profile_offsets=profile[0], profile_t=profile[1], profile_source_m=profile[2], profile_center_bed_m=profile[3], vertices_xz_m=vertices, source_elevation_m=source, cut_depth_m=cut, bed_elevation_m=bed, triangles=triangles, source_cell_ids=source_cells, canonical_port_edge_node_indices=ports[0], canonical_port_xz_m=ports[1], canonical_port_profile_xz_m=ports[2], canonical_port_triangle_ids=ports[3], canonical_port_barycentric=ports[4], canonical_port_cut_depth_m=ports[5])
    metadata = dict(schema=METRIC_VALLEY_INCISION_SCHEMA, algorithm=METRIC_VALLEY_INCISION_ALGORITHM, terrain_metadata=_metadata_terrain(terrain), source_identity_sha256=terrain.identity_sha256, config=_i41_asdict(config), epsilon_slope_m_per_m=EPSILON_SLOPE_M_PER_M, cut_volume_m3=_mesh_volume(vertices, triangles, cut), geometry_measure='canonical_piecewise_linear_heightfield', fixed_xz=True, original_bed_may_rise_within_edge=True, geometry_verified=True, hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    arrays = {key: _i41_readonly(value) for key, value in arrays.items()}
    bundle = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i41_identity(arrays, metadata)}
    validate_valley_incision(bundle)
    return bundle

def validate_valley_incision(bundle):
    from terrain_pipeline.common_infra import identity as _i41_identity
    from terrain_pipeline.common_infra import TerrainGrid as _i41_TerrainGrid
    if not isinstance(bundle, dict) or set(bundle) != {'arrays', 'metadata', 'identity_sha256'}:
        raise ValueError('invalid valley incision bundle')
    a, m = (bundle['arrays'], bundle['metadata'])
    expected_meta = {'schema', 'algorithm', 'terrain_metadata', 'source_identity_sha256', 'config', 'epsilon_slope_m_per_m', 'cut_volume_m3', 'geometry_measure', 'fixed_xz', 'original_bed_may_rise_within_edge', 'geometry_verified', 'hydraulic_ready', 'natural_outlet_verified', 'publishable'}
    if set(a) != set(METRIC_VALLEY_INCISION_ARRAYS) or set(m) != expected_meta or m['schema'] != METRIC_VALLEY_INCISION_SCHEMA or (m['algorithm'] != METRIC_VALLEY_INCISION_ALGORITHM) or (m['epsilon_slope_m_per_m'] != EPSILON_SLOPE_M_PER_M) or (m['geometry_measure'] != 'canonical_piecewise_linear_heightfield') or any((m[k] is not True for k in ('fixed_xz', 'original_bed_may_rise_within_edge', 'geometry_verified'))) or any((m[k] is not False for k in ('hydraulic_ready', 'natural_outlet_verified', 'publishable'))) or (sum((value.nbytes for value in a.values())) > METRIC_CHANNEL_GEOMETRY_MAX_BYTES) or (bundle['identity_sha256'] != _i41_identity(a, m)):
        raise ValueError('valley incision schema/identity/scope mismatch')
    terrain = _i41_TerrainGrid(a['source_height_m'], a['source_valid_mask'], **m['terrain_metadata'])
    if terrain.identity_sha256 != m['source_identity_sha256']:
        raise ValueError('source identity mismatch')
    config = GeometryConfig(**m['config'])
    ids, receiver, width, depth = (a[key] for key in ('source_node_cell_ids', 'receiver', 'width_m', 'base_depth_m'))
    _check_inputs(terrain, ids, receiver, width, depth, a['owner_grid'], a['corridor_mask'], a['lake_mask'], config)
    cols = terrain.elevation_m.shape[1]
    points = _i41_np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m, terrain.z0_m + ids // cols * terrain.dz_m))
    if not _i41_np.array_equal(points, a['node_xz_m']):
        raise ValueError('fixed source node coordinates mismatch')
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, depth, terrain, config.max_cut_m)
    if any((not _i41_np.allclose(a[key], expected, atol=1e-10, rtol=0.0) for key, expected in zip(('profile_offsets', 'profile_t', 'profile_source_m', 'profile_center_bed_m'), profile))):
        raise ValueError('original-bilinear incision profile mismatch')
    maxdepth = _i41_np.full(len(points), config.max_cut_m)
    _footprint(points, receiver, width, maxdepth, terrain, a['owner_grid'], a['corridor_mask'], a['lake_mask'], a['owner_grid'].ravel()[ids], config.fine_spacing_m)
    _profile_overlap(points, receiver, width, profile, terrain)
    vertices, triangles = (a['vertices_xz_m'], a['triangles'])
    _validate_fan_mesh(vertices, triangles, points, width, maxdepth, terrain, config)
    source, cells = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)
    cut = _profile_cut(points, receiver, width, profile, vertices, terrain, a['lake_mask'])
    if _i41_np.any(cut > config.max_cut_m + 1e-10) or not _i41_np.array_equal(a['source_cell_ids'], cells) or (not _i41_np.allclose(a['source_elevation_m'], source, rtol=0.0, atol=1e-09)) or (not _i41_np.allclose(a['cut_depth_m'], cut, rtol=0.0, atol=1e-09)) or (not _i41_np.allclose(a['bed_elevation_m'], source - cut, rtol=0.0, atol=1e-09)):
        raise ValueError('represented original-source incision mismatch')
    if _i41_np.any(cut[_wet_guard(vertices, a['lake_mask'], terrain)] > 0.0):
        raise ValueError('known wet source support cut')
    _modified_bed_slope(points, receiver, vertices, triangles, source - cut, config.fine_spacing_m)
    ports = _port_observations(points, receiver, width, depth, vertices, triangles, cut)
    port_names = ('canonical_port_edge_node_indices', 'canonical_port_xz_m', 'canonical_port_profile_xz_m', 'canonical_port_triangle_ids', 'canonical_port_barycentric', 'canonical_port_cut_depth_m')
    if any((not _i41_np.allclose(a[key], value, rtol=0.0, atol=1e-09) for key, value in zip(port_names, ports))):
        raise ValueError('shared canonical port mismatch')
    if not _i41_math.isclose(m['cut_volume_m3'], _mesh_volume(vertices, triangles, cut), rel_tol=1e-10, abs_tol=1e-08):
        raise ValueError('represented cut volume mismatch')
    return True

def save_valley_incision(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _i41_save_bundle
    _i41_save_bundle(path, bundle, validator=validate_valley_incision)

def load_valley_incision(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _i41_load_bundle
    bundle = _i41_load_bundle(path, expected_sha256=expected_sha256, validator=validate_valley_incision, max_bytes=METRIC_CHANNEL_GEOMETRY_MAX_BYTES)
    if bundle['identity_sha256'] != expected_identity:
        raise ValueError('external valley incision identity mismatch')
    return bundle
METRIC_VALLEY_UNION_SCHEMA = 'terragenesis-sparse-valley-union-v1'
METRIC_VALLEY_UNION_ALGORITHM = 'aligned-sparse-fan4-global-max-incision-v2'

def _sparse_cells(points, receiver, width, profile, config, terrain, *, support_radius_m=None):
    spacing = config.fine_spacing_m
    origin = _i43_np.array([terrain.x0_m, terrain.z0_m])
    maximum = _i43_np.array([(terrain.elevation_m.shape[1] - 1) * round(terrain.dx_m / spacing), (terrain.elevation_m.shape[0] - 1) * round(terrain.dz_m / spacing)], _i43_np.int64)
    cells = set()
    if support_radius_m is None:
        maximum_cut = _profile_max_cut_per_edge(points, receiver, profile, terrain)
    else:
        support_radius_m = _i43_np.asarray(support_radius_m, dtype=_i43_np.float64)
        if support_radius_m.shape != (_i43_np.count_nonzero(receiver >= 0),) or not _i43_np.all(_i43_np.isfinite(support_radius_m)) or _i43_np.any(support_radius_m <= 0.0):
            raise ValueError('positive finite support radius required for every represented edge')
    edge = 0
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        radius = max(width[i], width[j]) / 2.0 + BANK_SLOPE * maximum_cut[edge] if support_radius_m is None else support_radius_m[edge]
        edge += 1
        a, b = (points[i], points[j])
        first = _i43_np.maximum(_i43_np.floor((_i43_np.minimum(a, b) - radius - origin) / spacing).astype(int), 0)
        last = _i43_np.minimum(_i43_np.ceil((_i43_np.maximum(a, b) + radius - origin) / spacing).astype(int), maximum)
        candidate_count = int(_i43_np.prod(_i43_np.maximum(last - first, 0)))
        if candidate_count > config.max_vertices:
            raise ValueError('sparse footprint preflight vertex budget exceeded')
        columns = int(last[0] - first[0])
        for start in range(0, candidate_count, 65536):
            flat = _i43_np.arange(start, min(start + 65536, candidate_count))
            candidates = _i43_np.column_stack((first[0] + flat % columns, first[1] + flat // columns))
            low = origin + spacing * candidates
            selected = _segment_boxes_distance(a, b, low, low + spacing) <= radius + 1e-10
            cells.update(map(tuple, candidates[selected]))
        if len(cells) > config.max_vertices:
            raise ValueError('sparse union cell budget exceeded before meshing')
    if not cells:
        raise ValueError('no sparse channel support cells')
    return _i43_np.asarray(sorted(cells, key=lambda item: (item[1], item[0])), _i43_np.int64)

def _segment_boxes_distance(a, b, low, high):
    """Batch the scalar endpoint, four-corner and edge-intersection predicate."""
    delta = b - a
    intersects = _i43_np.zeros(len(low), bool)
    for endpoint in (a, b):
        intersects |= _i43_np.all(endpoint >= low, axis=1) & _i43_np.all(endpoint <= high, axis=1)
    for axis in (0, 1):
        if delta[axis] == 0.0:
            continue
        other = 1 - axis
        for boundary in (low[:, axis], high[:, axis]):
            t = (boundary - a[axis]) / delta[axis]
            cross = a[other] + t * delta[other]
            intersects |= (t >= 0.0) & (t <= 1.0) & (cross >= low[:, other]) & (cross <= high[:, other])
    distances = _i43_np.full(len(low), _i43_np.inf)
    for endpoint in (a, b):
        separation = _i43_np.maximum(low - endpoint, _i43_np.maximum(endpoint - high, 0.0))
        distances = _i43_np.minimum(distances, _i43_np.linalg.norm(separation, axis=1))
    denominator = float(delta @ delta)
    if denominator == 0.0:
        return distances
    for x in (low[:, 0], high[:, 0]):
        for z in (low[:, 1], high[:, 1]):
            corner = _i43_np.column_stack((x, z))
            t = _i43_np.clip(_i43_np.sum((corner - a) * delta, axis=1) / denominator, 0.0, 1.0)
            separation = corner - (a + t[:, None] * delta)
            distances = _i43_np.minimum(distances, _i43_np.linalg.norm(separation, axis=1))
    distances[intersects] = 0.0
    return distances

def _sparse_mesh(cells, terrain, spacing, max_vertices):
    if not len(cells):
        if max_vertices < 0:
            raise ValueError('sparse canonical mesh vertex budget exceeded')
        return (_i43_np.empty(0, _i43_np.float64), _i43_np.empty((0, 3), _i43_np.int64))
    cells = _i43_np.asarray(cells, _i43_np.int64)
    minimum = cells.min(axis=0)
    stride = int(cells[:, 0].max() - minimum[0]) + 2
    cell_keys = (cells[:, 1] - minimum[1]) * stride + cells[:, 0] - minimum[0]
    corners = _i43_np.unique(_i43_np.concatenate([cell_keys, cell_keys + 1, cell_keys + stride + 1, cell_keys + stride]))
    count = len(corners) + len(cells)
    if count > max_vertices:
        raise ValueError('sparse canonical mesh vertex budget exceeded')
    origin = _i43_np.array([terrain.x0_m, terrain.z0_m])
    vertices = _i43_np.empty((count, 2), _i43_np.float64)
    vertices[:len(corners), 0] = origin[0] + spacing * (corners % stride + minimum[0])
    vertices[:len(corners), 1] = origin[1] + spacing * (corners // stride + minimum[1])
    vertices[len(corners):] = origin + spacing * (cells + 0.5)
    triangles = _i43_np.empty((4 * len(cells), 3), _i43_np.int64)
    for start in range(0, len(cells), 200000):
        keys = cell_keys[start:start + 200000]
        corner_ids = _i43_np.searchsorted(corners, keys[:, None] + [0, 1, stride + 1, stride])
        faces = triangles[4 * start:4 * (start + len(keys))].reshape(-1, 4, 3)
        faces[:, :, 0] = corner_ids
        faces[:, :, 1] = corner_ids[:, [1, 2, 3, 0]]
        faces[:, :, 2] = (len(corners) + _i43_np.arange(start, start + len(keys)))[:, None]
    return (vertices, triangles)

def _mesh_height(point, cell, vertices, triangles, bed):
    for face in range(4 * cell, 4 * cell + 4):
        ids = triangles[face]
        tri = vertices[ids]
        matrix = _i43_np.column_stack((tri[1] - tri[0], tri[2] - tri[0]))
        uv = _i43_np.linalg.solve(matrix, point - tri[0])
        if min(1.0 - uv.sum(), uv[0], uv[1]) >= -1e-09:
            return float(bed[ids[0]] + uv @ (bed[ids[1:]] - bed[ids[0]]))
    raise ValueError('line point outside sparse canonical triangle')

def _sparse_ports(points, receiver, width, profile_data, cells, vertices, triangles, cut, spacing, terrain):
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = _i43_np.array([terrain.x0_m, terrain.z0_m])
    edges = _i43_np.array([(i, int(j)) for i, j in enumerate(receiver) if j >= 0], _i43_np.int64)
    middle = _i43_np.empty((len(edges), 2), _i43_np.float64)
    profile = _i43_np.empty((len(edges), 4, 2), _i43_np.float64)
    face_ids = _i43_np.empty((len(edges), 4), _i43_np.int64)
    bary = _i43_np.empty((len(edges), 4, 3), _i43_np.float64)
    cut_values = _i43_np.empty((len(edges), 4), _i43_np.float64)
    for index, (i, j) in enumerate(edges):
        a, b = (points[i], points[j])
        center = (a + b) / 2.0
        flow = (b - a) / _i43_np.linalg.norm(b - a)
        normal = _i43_np.array([-flow[1], flow[0]])
        half = (width[i] + width[j]) / 4.0
        lo, hi = profile_data[0][index:index + 2]
        center_cut = float(_i43_np.interp(0.5, profile_data[1][lo:hi], profile_data[2][lo:hi] - profile_data[3][lo:hi]))
        bank = BANK_SLOPE * center_cut
        middle[index] = center
        for k, offset in enumerate((-half - bank, -half, half, half + bank)):
            p = center + offset * normal
            profile[index, k] = p
            cell_xy = _i43_np.floor((p - origin) / spacing).astype(int)
            found = False
            for x in (cell_xy[0], cell_xy[0] - 1):
                for z in (cell_xy[1], cell_xy[1] - 1):
                    cell = lookup.get((x, z))
                    if cell is None:
                        continue
                    for face in range(4 * cell, 4 * cell + 4):
                        ids = triangles[face]
                        tri = vertices[ids]
                        matrix = _i43_np.column_stack((tri[1] - tri[0], tri[2] - tri[0]))
                        uv = _i43_np.linalg.solve(matrix, p - tri[0])
                        weights = _i43_np.array([1.0 - uv.sum(), uv[0], uv[1]])
                        if _i43_np.min(weights) >= -1e-09:
                            face_ids[index, k] = face
                            bary[index, k] = weights
                            cut_values[index, k] = weights @ cut[ids]
                            found = True
                            break
                    if found:
                        break
                if found:
                    break
            if not found:
                raise ValueError('shared sparse port outside canonical mesh')
    return (edges, middle, profile, face_ids, bary, cut_values)

def _cut_source_constraints(vertices, source_cells, cut, terrain, owner_grid, corridor_mask, lake_mask, source_owner):
    cols = terrain.elevation_m.shape[1]
    for cell, amount in zip(source_cells, cut):
        if amount <= 1e-10:
            continue
        gz, gx = divmod(int(cell), cols)
        stencil = _i43_np.s_[gz:gz + 2, gx:gx + 2]
        if not terrain.valid_mask[stencil].all() or not corridor_mask[stencil].all() or _i43_np.any(owner_grid[stencil] != source_owner) or lake_mask[stencil].any():
            raise ValueError('sparse cut crosses unknown, owner, corridor or known wet support')

def _cell_at_point(point, lookup, origin, spacing):
    coordinate = (point - origin) / spacing
    first = _i43_np.floor(coordinate).astype(_i43_np.int64)
    key = tuple(first)
    if key in lookup:
        return key
    touching = []
    for axis in range(2):
        candidates = [first[axis], first[axis] - 1]
        nearest = int(_i43_np.rint(coordinate[axis]))
        if abs(coordinate[axis] - nearest) <= 1e-09 and nearest not in candidates:
            candidates.append(nearest)
        touching.append(candidates)
    for x in touching[0]:
        for z in touching[1]:
            candidate = (int(x), int(z))
            if candidate in lookup and _i43_np.all(coordinate >= [x - 1e-09, z - 1e-09]) and _i43_np.all(coordinate <= [x + 1.0 + 1e-09, z + 1.0 + 1e-09]):
                return candidate
    raise ValueError('centerline leaves sparse mesh support')

def _coalesce_line_breaks(values, a, b, spacing):
    values = _i43_np.unique(values)
    resolution = max(spacing * 1e-10, 8.0 * _i43_np.spacing(max(1.0, float(_i43_np.abs(_i43_np.r_[a, b]).max()))))
    tolerance = resolution / _i43_np.linalg.norm(b - a)
    result = []
    group = [float(values[0])]
    for value in values[1:]:
        if value - group[-1] <= tolerance:
            group.append(float(value))
        else:
            result.append(0.0 if group[0] == 0.0 else float(_i43_np.mean(group)))
            group = [float(value)]
    result.append(1.0 if group[-1] == 1.0 else float(_i43_np.mean(group)))
    return _i43_np.asarray(result)

def _mesh_directional_weights(point, cell, vertices, triangles, direction):
    candidates = []
    for face in range(4 * cell, 4 * cell + 4):
        ids = triangles[face]
        tri = vertices[ids]
        matrix = _i43_np.column_stack((tri[1] - tri[0], tri[2] - tri[0]))
        uv = _i43_np.linalg.solve(matrix, point - tri[0])
        weights = _i43_np.r_[1.0 - uv.sum(), uv]
        candidates.append((float(weights.min()), ids, matrix))
    margin, ids, matrix = max(candidates, key=lambda item: item[0])
    if margin < -1e-08:
        raise ValueError('line midpoint outside sparse canonical triangle')
    uv_direction = _i43_np.linalg.solve(matrix, direction)
    return (ids, _i43_np.r_[-uv_direction.sum(), uv_direction])

def _sparse_slope(points, receiver, cells, vertices, triangles, bed, spacing, terrain):
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = _i43_np.array([terrain.x0_m, terrain.z0_m])
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = (points[i], points[j])
        delta = b - a
        breaks = [0.0, 1.0]
        for axis in (0, 1):
            if abs(delta[axis]) <= 1e-15:
                continue
            for grid in range(int(_i43_math.floor((min(a[axis], b[axis]) - origin[axis]) / spacing)), int(_i43_math.ceil((max(a[axis], b[axis]) - origin[axis]) / spacing)) + 1):
                t = (origin[axis] + grid * spacing - a[axis]) / delta[axis]
                if 1e-12 < t < 1.0 - 1e-12:
                    breaks.append(t)
        grid_breaks = _coalesce_line_breaks(breaks, a, b, spacing)
        for t0, t1 in zip(grid_breaks[:-1], grid_breaks[1:]):
            midpoint = a + (t0 + t1) / 2.0 * delta
            key = _cell_at_point(midpoint, lookup, origin, spacing)
            low = origin + spacing * _i43_np.asarray(key)
            for normal, constant in ((_i43_np.array([1.0, -1.0]), 0.0), (_i43_np.array([1.0, 1.0]), spacing)):
                denominator = float(normal @ delta)
                if abs(denominator) <= 1e-15:
                    continue
                t = (constant - normal @ (a - low)) / denominator
                if t0 + 1e-12 < t < t1 - 1e-12:
                    breaks.append(t)
        breaks = _coalesce_line_breaks(breaks, a, b, spacing)
        for t0, t1 in zip(breaks[:-1], breaks[1:]):
            midpoint = a + (t0 + t1) / 2.0 * delta
            key = _cell_at_point(midpoint, lookup, origin, spacing)
            cell = lookup[key]
            ids, direction_weights = _mesh_directional_weights(midpoint, cell, vertices, triangles, delta / _i43_np.linalg.norm(delta))
            gradient = float(direction_weights[1:] @ (bed[ids[1:]] - bed[ids[0]]))
            if gradient >= 0.0:
                raise ValueError(f'sparse canonical bed is flat or uphill: edge={i}->{j}, dt={t1 - t0:.17g}, length={_i43_np.linalg.norm(delta) * (t1 - t0):.17g}m, directional_gradient={gradient:.17g}m/m')

def build_valley_union(terrain, node_cell_ids, receiver, width_m, base_depth_m, *, owner_grid, corridor_mask, lake_mask, source_plan_identity_sha256, config=None):
    from terrain_pipeline.common_infra import identity as _i43_identity
    from terrain_pipeline.common_infra import readonly as _i43_readonly
    config = config or GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0)
    _check_inputs(terrain, node_cell_ids, receiver, width_m, base_depth_m, owner_grid, corridor_mask, lake_mask, config)
    if not isinstance(source_plan_identity_sha256, str) or len(source_plan_identity_sha256) != 64 or any((c not in '0123456789abcdef' for c in source_plan_identity_sha256)):
        raise ValueError('source network plan SHA256 identity required')
    if _i43_np.unique(owner_grid.ravel()[node_cell_ids]).size != 1:
        raise ValueError('sparse union component must have one source owner')
    cols = terrain.elevation_m.shape[1]
    points = _i43_np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m, terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, base_depth_m, terrain, config.max_cut_m)
    maxdepth = _i43_np.full(len(points), config.max_cut_m)
    _footprint(points, receiver, width_m, maxdepth, terrain, owner_grid, corridor_mask, lake_mask, owner_grid.ravel()[node_cell_ids], config.fine_spacing_m)
    _profile_overlap(points, receiver, width_m, profile, terrain)
    cells = _sparse_cells(points, receiver, width_m, profile, config, terrain)
    vertices, triangles = _sparse_mesh(cells, terrain, config.fine_spacing_m, config.max_vertices)
    source, source_cells = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)
    cut = _profile_cut(points, receiver, width_m, profile, vertices, terrain, lake_mask)
    if not _i43_np.isfinite(cut).all() or _i43_np.any(cut < 0.0) or _i43_np.any(cut > config.max_cut_m + 1e-10):
        raise ValueError('sparse union cut exceeds maximum')
    bed = source - cut
    _sparse_slope(points, receiver, cells, vertices, triangles, bed, config.fine_spacing_m, terrain)
    _cut_source_constraints(vertices, source_cells, cut, terrain, owner_grid, corridor_mask, lake_mask, owner_grid.ravel()[node_cell_ids[0]])
    ports = _sparse_ports(points, receiver, width_m, profile, cells, vertices, triangles, cut, config.fine_spacing_m, terrain)
    arrays = dict(source_node_cell_ids=node_cell_ids.copy(), receiver=receiver.copy(), node_xz_m=points, width_m=width_m.copy(), base_depth_m=base_depth_m.copy(), source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(), owner_grid=owner_grid.copy(), corridor_mask=corridor_mask.copy(), lake_mask=lake_mask.copy(), profile_offsets=profile[0], profile_t=profile[1], profile_source_m=profile[2], profile_center_bed_m=profile[3], sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles, source_elevation_m=source, source_cell_ids=source_cells, cut_depth_m=cut, bed_elevation_m=bed, port_edge_node_indices=ports[0], port_xz_m=ports[1], port_profile_xz_m=ports[2], port_triangle_ids=ports[3], port_barycentric=ports[4], port_cut_depth_m=ports[5])
    metadata = dict(schema=METRIC_VALLEY_UNION_SCHEMA, algorithm=METRIC_VALLEY_UNION_ALGORITHM, terrain_metadata=_metadata_terrain(terrain), source_identity_sha256=terrain.identity_sha256, config=_i43_asdict(config), source_plan_identity_sha256=source_plan_identity_sha256, cut_volume_m3=_mesh_volume(vertices, triangles, cut), mesh_measure='unique_sparse_aligned_fan4_piecewise_linear', global_component_only=True, cross_component_verified=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    arrays = {key: _i43_readonly(value) for key, value in arrays.items()}
    bundle = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i43_identity(arrays, metadata)}
    validate_valley_union(bundle)
    return bundle

def validate_valley_union(bundle):
    from terrain_pipeline.common_infra import identity as _i43_identity
    from terrain_pipeline.common_infra import TerrainGrid as _i43_TerrainGrid
    if not isinstance(bundle, dict) or set(bundle) != {'arrays', 'metadata', 'identity_sha256'} or bundle['identity_sha256'] != _i43_identity(bundle['arrays'], bundle['metadata']) or (sum((value.nbytes for value in bundle['arrays'].values())) > METRIC_CHANNEL_GEOMETRY_MAX_BYTES):
        raise ValueError('sparse union identity or byte budget mismatch')
    a, m = (bundle['arrays'], bundle['metadata'])
    expected_arrays = {'source_node_cell_ids', 'receiver', 'node_xz_m', 'width_m', 'base_depth_m', 'source_height_m', 'source_valid_mask', 'owner_grid', 'corridor_mask', 'lake_mask', 'profile_offsets', 'profile_t', 'profile_source_m', 'profile_center_bed_m', 'sparse_cell_xy', 'vertices_xz_m', 'triangles', 'source_elevation_m', 'source_cell_ids', 'cut_depth_m', 'bed_elevation_m', 'port_edge_node_indices', 'port_xz_m', 'port_profile_xz_m', 'port_triangle_ids', 'port_barycentric', 'port_cut_depth_m'}
    expected_meta = {'schema', 'algorithm', 'terrain_metadata', 'source_identity_sha256', 'config', 'source_plan_identity_sha256', 'cut_volume_m3', 'mesh_measure', 'global_component_only', 'cross_component_verified', 'hydraulic_ready', 'natural_outlet_verified', 'publishable'}
    if set(a) != expected_arrays or set(m) != expected_meta or m.get('schema') != METRIC_VALLEY_UNION_SCHEMA or (m.get('algorithm') != METRIC_VALLEY_UNION_ALGORITHM) or (m.get('mesh_measure') != 'unique_sparse_aligned_fan4_piecewise_linear') or (m.get('global_component_only') is not True) or any((m.get(key) is not False for key in ('cross_component_verified', 'hydraulic_ready', 'natural_outlet_verified', 'publishable'))):
        raise ValueError('sparse union schema or scope mismatch')
    float_fields = ('node_xz_m', 'width_m', 'base_depth_m', 'source_height_m', 'profile_t', 'profile_source_m', 'profile_center_bed_m', 'vertices_xz_m', 'source_elevation_m', 'cut_depth_m', 'bed_elevation_m', 'port_xz_m', 'port_profile_xz_m', 'port_barycentric', 'port_cut_depth_m')
    int_fields = ('source_node_cell_ids', 'receiver', 'owner_grid', 'profile_offsets', 'sparse_cell_xy', 'triangles', 'source_cell_ids', 'port_edge_node_indices', 'port_triangle_ids')
    bool_fields = ('source_valid_mask', 'corridor_mask', 'lake_mask')
    if any((not isinstance(a[key], _i43_np.ndarray) or a[key].dtype != _i43_np.float64 for key in float_fields)) or any((not isinstance(a[key], _i43_np.ndarray) or a[key].dtype != _i43_np.int64 for key in int_fields)) or any((not isinstance(a[key], _i43_np.ndarray) or a[key].dtype != bool for key in bool_fields)):
        raise ValueError('sparse union array dtype mismatch')
    pin = m.get('source_plan_identity_sha256')
    if not isinstance(pin, str) or len(pin) != 64 or any((c not in '0123456789abcdef' for c in pin)):
        raise ValueError('source network plan identity missing')
    terrain = _i43_TerrainGrid(a['source_height_m'], a['source_valid_mask'], **m['terrain_metadata'])
    if terrain.identity_sha256 != m['source_identity_sha256']:
        raise ValueError('sparse union source identity mismatch')
    config = GeometryConfig(**m['config'])
    ids, receiver, width, depth = (a[key] for key in ('source_node_cell_ids', 'receiver', 'width_m', 'base_depth_m'))
    _check_inputs(terrain, ids, receiver, width, depth, a['owner_grid'], a['corridor_mask'], a['lake_mask'], config)
    if _i43_np.unique(a['owner_grid'].ravel()[ids]).size != 1:
        raise ValueError('sparse union component spans owners')
    cols = terrain.elevation_m.shape[1]
    points = _i43_np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m, terrain.z0_m + ids // cols * terrain.dz_m))
    if not _i43_np.array_equal(a['node_xz_m'], points):
        raise ValueError('sparse union fixed node position mismatch')
    profile = _profile(points, receiver, depth, terrain, config.max_cut_m)
    maxdepth = _i43_np.full(len(points), config.max_cut_m)
    _footprint(points, receiver, width, maxdepth, terrain, a['owner_grid'], a['corridor_mask'], a['lake_mask'], a['owner_grid'].ravel()[ids], config.fine_spacing_m)
    _profile_overlap(points, receiver, width, profile, terrain)
    for key, expected in zip(('profile_offsets', 'profile_t', 'profile_source_m', 'profile_center_bed_m'), profile):
        if not _i43_np.allclose(a[key], expected, rtol=0.0, atol=1e-09):
            raise ValueError('sparse union profile mismatch')
    cells = _sparse_cells(points, receiver, width, profile, config, terrain)
    vertices, triangles = _sparse_mesh(cells, terrain, config.fine_spacing_m, config.max_vertices)
    if a['sparse_cell_xy'].shape != cells.shape or a['vertices_xz_m'].shape != vertices.shape or a['triangles'].shape != triangles.shape:
        raise ValueError('sparse union mesh shape mismatch')
    if not _i43_np.array_equal(a['sparse_cell_xy'], cells) or not _i43_np.array_equal(a['vertices_xz_m'], vertices) or (not _i43_np.array_equal(a['triangles'], triangles)):
        raise ValueError('unique sparse fan4 incidence mismatch')
    source, source_cells = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)
    cut = _profile_cut(points, receiver, width, profile, vertices, terrain, a['lake_mask'])
    if _i43_np.any(cut > config.max_cut_m + 1e-10) or not _i43_np.array_equal(a['source_cell_ids'], source_cells) or (not _i43_np.allclose(a['source_elevation_m'], source, rtol=0.0, atol=1e-09)) or (not _i43_np.allclose(a['cut_depth_m'], cut, rtol=0.0, atol=1e-09)) or (not _i43_np.allclose(a['bed_elevation_m'], source - cut, rtol=0.0, atol=1e-09)):
        raise ValueError('sparse union source/cut field mismatch')
    _cut_source_constraints(vertices, source_cells, cut, terrain, a['owner_grid'], a['corridor_mask'], a['lake_mask'], a['owner_grid'].ravel()[ids[0]])
    _sparse_slope(points, receiver, cells, vertices, triangles, source - cut, config.fine_spacing_m, terrain)
    ports = _sparse_ports(points, receiver, width, profile, cells, vertices, triangles, cut, config.fine_spacing_m, terrain)
    port_keys = ('port_edge_node_indices', 'port_xz_m', 'port_profile_xz_m', 'port_triangle_ids', 'port_barycentric', 'port_cut_depth_m')
    if any((not _i43_np.allclose(a[key], value, rtol=0.0, atol=1e-09) for key, value in zip(port_keys, ports))) or not _i43_math.isclose(m['cut_volume_m3'], _mesh_volume(vertices, triangles, cut), rel_tol=1e-10, abs_tol=1e-08):
        raise ValueError('sparse shared port or material ledger mismatch')
    return True

def save_valley_union(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _i43_save_bundle
    _i43_save_bundle(path, bundle, validator=validate_valley_union)

def load_valley_union(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _i43_load_bundle
    bundle = _i43_load_bundle(path, expected_sha256=expected_sha256, validator=validate_valley_union, max_bytes=METRIC_CHANNEL_GEOMETRY_MAX_BYTES)
    if bundle['identity_sha256'] != expected_identity:
        raise ValueError('external sparse union identity mismatch')
    return bundle
METRIC_MONOTONE_UNION_SCHEMA = 'terragenesis-monotone-sparse-valley-union-v1'
METRIC_MONOTONE_UNION_ALGORITHM = 'aligned-sparse-fan4-global-max-lp-monotone-closure-v1'
SHAPED_ALGORITHM = 'anchored-original-valley-sparse-monotone-closure-v1'

def _barycentric(point, cell, vertices, triangles):
    scale = max(1.0, float(_i34_np.abs(point).max()))
    span = _i34_np.linalg.norm(vertices[triangles[4 * cell, 1]] - vertices[triangles[4 * cell, 0]])
    tolerance = max(1e-09, 8.0 * _i34_np.spacing(scale) / span)
    for face in range(4 * cell, 4 * cell + 4):
        ids = triangles[face]
        tri = vertices[ids]
        matrix = _i34_np.column_stack((tri[1] - tri[0], tri[2] - tri[0]))
        uv = _i34_np.linalg.solve(matrix, point - tri[0])
        weights = _i34_np.array([1.0 - uv.sum(), uv[0], uv[1]])
        if _i34_np.min(weights) >= -tolerance:
            return (ids, weights)
    raise ValueError('centerline point outside sparse triangles')

def _line_constraints(points, receiver, cells, vertices, triangles, terrain, spacing):
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = _i34_np.array([terrain.x0_m, terrain.z0_m])
    segments = []
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = (points[i], points[j])
        delta = b - a
        breaks = [0.0, 1.0]
        for axis in range(2):
            if abs(delta[axis]) <= 1e-15:
                continue
            first = int(_i34_math.floor((min(a[axis], b[axis]) - origin[axis]) / spacing))
            last = int(_i34_math.ceil((max(a[axis], b[axis]) - origin[axis]) / spacing))
            for grid in range(first, last + 1):
                t = (origin[axis] + grid * spacing - a[axis]) / delta[axis]
                if 1e-12 < t < 1.0 - 1e-12:
                    breaks.append(t)
        grid_breaks = _coalesce_line_breaks(breaks, a, b, spacing)
        for t0, t1 in zip(grid_breaks[:-1], grid_breaks[1:]):
            midpoint = a + (t0 + t1) / 2.0 * delta
            key = _cell_at_point(midpoint, lookup, origin, spacing)
            low = origin + spacing * _i34_np.asarray(key)
            for normal, constant in ((_i34_np.array([1.0, -1.0]), 0.0), (_i34_np.array([1.0, 1.0]), spacing)):
                denominator = float(normal @ delta)
                if abs(denominator) <= 1e-15:
                    continue
                t = (constant - normal @ (a - low)) / denominator
                if t0 + 1e-12 < t < t1 - 1e-12:
                    breaks.append(t)
        all_breaks = _coalesce_line_breaks(breaks, a, b, spacing)
        for t0, t1 in zip(all_breaks[:-1], all_breaks[1:]):
            midpoint = a + (t0 + t1) / 2.0 * delta
            key = _cell_at_point(midpoint, lookup, origin, spacing)
            cell = lookup.get(key)
            if cell is None:
                raise ValueError('centerline leaves sparse mesh support')
            start = _barycentric(a + t0 * delta, cell, vertices, triangles)
            end = _barycentric(a + t1 * delta, cell, vertices, triangles)
            segments.append((start, end, float(t1 - t0), i, int(j)))
    return segments

def _close_bed(points, receiver, cells, vertices, triangles, source, original_cut, terrain, spacing, max_cut_m, *, minimum_slope_m_per_m=None):
    segments = _line_constraints(points, receiver, cells, vertices, triangles, terrain, spacing)
    if minimum_slope_m_per_m is not None:
        return _close_physical_bed(points, segments, cells, vertices, triangles, source, original_cut, terrain, spacing, max_cut_m, minimum_slope_m_per_m)
    active = _i34_np.unique(_i34_np.concatenate([_i34_np.r_[start[0], end[0]] for start, end, _, _, _ in segments]))
    if active.size == 0:
        raise ValueError('monotone closure has no centerline support')
    mapping = _i34_np.full(len(vertices), -1, _i34_np.int64)
    mapping[active] = _i34_np.arange(len(active))
    base_bed = source - original_cut
    rows, columns, coefficients, limits = ([], [], [], [])
    for row, (start, end, dt, edge_source, edge_target) in enumerate(segments):
        h0 = float(start[1] @ base_bed[start[0]])
        h1 = float(end[1] @ base_bed[end[0]])
        for vertex, weight in zip(start[0], start[1]):
            rows.append(row)
            columns.append(int(mapping[vertex]))
            coefficients.append(float(weight))
        for vertex, weight in zip(end[0], end[1]):
            rows.append(row)
            columns.append(int(mapping[vertex]))
            coefficients.append(float(-weight))
        minimum_drop = 1e-07 * dt if minimum_slope_m_per_m is None else minimum_slope_m_per_m * _i34_np.linalg.norm(points[edge_target] - points[edge_source]) * dt
        limits.append(-minimum_drop - (h1 - h0))
    matrix = _i34_coo_matrix((coefficients, (rows, columns)), shape=(len(segments), len(active))).tocsr()
    bounds = [(0.0, float(max_cut_m - original_cut[vertex])) for vertex in active]
    result = _i34_linprog(_i34_np.ones(len(active)), A_ub=matrix, b_ub=_i34_np.asarray(limits), bounds=bounds, method='highs', options={} if minimum_slope_m_per_m is None else {'primal_feasibility_tolerance': 1e-09})
    if not result.success:
        raise ValueError('shared monotone closure exceeds 4m cut or is infeasible: ' + result.message)
    cut = original_cut.copy()
    cut[active] += result.x
    residual = matrix @ result.x - limits
    if _i34_np.max(residual) > 1e-07 or _i34_np.max(cut) > max_cut_m + 1e-08:
        raise ValueError('shared monotone closure residual or maximum cut exceeded')
    return (cut, dict(extra_cut_vertices=int(_i34_np.count_nonzero(result.x > 1e-09)), extra_cut_sum_m=float(_i34_np.sum(result.x)), maximum_constraint_residual_m=float(_i34_np.max(residual)), centerline_segments=len(segments)))

def _close_physical_bed(points, segments, cells, vertices, triangles, source, original_cut, terrain, spacing, max_cut_m, minimum_slope):
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = _i34_np.array([terrain.x0_m, terrain.z0_m])
    base_bed = source - original_cut
    constraints = []
    for start, end, dt, i, j in segments:
        midpoint = (start[1] @ vertices[start[0]] + end[1] @ vertices[end[0]]) / 2.0
        key = _cell_at_point(midpoint, lookup, origin, spacing)
        delta = points[j] - points[i]
        ids, weights = _mesh_directional_weights(midpoint, lookup[key], vertices, triangles, delta / _i34_np.linalg.norm(delta))
        base_gradient = float(weights[1:] @ (base_bed[ids[1:]] - base_bed[ids[0]]))
        constraints.append((ids, -weights, -minimum_slope - base_gradient))
    active = _i34_np.unique(_i34_np.concatenate([ids for ids, _, _ in constraints]))
    mapping = _i34_np.full(len(vertices), -1, _i34_np.int64)
    mapping[active] = _i34_np.arange(len(active))
    rows = []
    columns = []
    coefficients = []
    limits = []
    for row, (ids, weights, limit) in enumerate(constraints):
        rows.extend([row] * 3)
        columns.extend(mapping[ids])
        coefficients.extend(weights)
        limits.append(limit)
    matrix = _i34_coo_matrix((coefficients, (rows, columns)), shape=(len(constraints), len(active))).tocsr()
    bounds = [(0.0, float(max_cut_m - original_cut[vertex])) for vertex in active]
    result = _i34_linprog(_i34_np.ones(len(active)), A_ub=matrix, b_ub=_i34_np.asarray(limits), bounds=bounds, method='highs', options={'primal_feasibility_tolerance': 1e-09, 'dual_feasibility_tolerance': 1e-09})
    if not result.success:
        raise ValueError('shared physical-slope closure exceeds 4m cut or is infeasible: ' + result.message)
    residual = matrix @ result.x - limits
    if _i34_np.max(residual) > 1e-08:
        raise ValueError('shared physical-slope closure residual exceeds tolerance')
    cut = original_cut.copy()
    cut[active] += result.x
    return (cut, dict(extra_cut_vertices=int(_i34_np.count_nonzero(result.x > 1e-09)), extra_cut_sum_m=float(_i34_np.sum(result.x)), maximum_constraint_residual_m_per_m=float(_i34_np.max(residual)), constraint_units='m/m', centerline_segments=len(segments), physical_triangle_plane_gradient=True))

def _geometry(terrain, ids, receiver, width, depth, points, owner, corridor, lake, config):
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, depth, terrain, config.max_cut_m)
    _footprint(points, receiver, width, _i34_np.full(len(points), config.max_cut_m), terrain, owner, corridor, lake, owner.ravel()[ids], config.fine_spacing_m)
    _profile_overlap(points, receiver, width, profile, terrain)
    cells = _sparse_cells(points, receiver, width, profile, config, terrain)
    vertices, triangles = _sparse_mesh(cells, terrain, config.fine_spacing_m, config.max_vertices)
    source, source_cells = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)
    base_cut = _profile_cut(points, receiver, width, profile, vertices, terrain, lake)
    cut, closure = _close_bed(points, receiver, cells, vertices, triangles, source, base_cut, terrain, config.fine_spacing_m, config.max_cut_m)
    _sparse_slope(points, receiver, cells, vertices, triangles, source - cut, config.fine_spacing_m, terrain)
    _cut_source_constraints(vertices, source_cells, cut, terrain, owner, corridor, lake, owner.ravel()[ids[0]])
    ports = _sparse_ports(points, receiver, width, profile, cells, vertices, triangles, cut, config.fine_spacing_m, terrain)
    return (profile, cells, vertices, triangles, source, source_cells, cut, ports, closure)

def build_monotone_union(terrain, node_cell_ids, receiver, width_m, base_depth_m, *, owner_grid, corridor_mask, lake_mask, source_plan_identity_sha256, config=None, centerline=None):
    from terrain_pipeline.common_infra import identity as _i34_identity
    from terrain_pipeline.common_infra import readonly as _i34_readonly
    config = config or GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0)
    _check_inputs(terrain, node_cell_ids, receiver, width_m, base_depth_m, owner_grid, corridor_mask, lake_mask, config)
    if not isinstance(source_plan_identity_sha256, str) or len(source_plan_identity_sha256) != 64 or any((ch not in '0123456789abcdef' for ch in source_plan_identity_sha256)):
        raise ValueError('source network plan identity required')
    if _i34_np.unique(owner_grid.ravel()[node_cell_ids]).size != 1:
        raise ValueError('shared component spans original source owners')
    cols = terrain.elevation_m.shape[1]
    points = _i34_np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m, terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    if centerline is not None:
        pass
        validate_valley_centerline(centerline)
        ca, cm = (centerline['arrays'], centerline['metadata'])
        if cm['source_identity_sha256'] != terrain.identity_sha256 or cm['source_plan_identity_sha256'] != source_plan_identity_sha256 or any((not _i34_np.array_equal(ca[key], value) for key, value in (('source_node_cell_ids', node_cell_ids), ('receiver', receiver), ('width_m', width_m), ('base_depth_m', base_depth_m), ('owner_grid', owner_grid), ('corridor_mask', corridor_mask), ('lake_mask', lake_mask)))):
            raise ValueError('shaped bed and centerline source graph mismatch')
        points = ca['node_xz_m']
    profile, cells, vertices, triangles, source, source_cells, cut, ports, closure = _geometry(terrain, node_cell_ids, receiver, width_m, base_depth_m, points, owner_grid, corridor_mask, lake_mask, config)
    arrays = dict(source_node_cell_ids=node_cell_ids.copy(), receiver=receiver.copy(), node_xz_m=points, width_m=width_m.copy(), base_depth_m=base_depth_m.copy(), source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(), owner_grid=owner_grid.copy(), corridor_mask=corridor_mask.copy(), lake_mask=lake_mask.copy(), profile_offsets=profile[0], profile_t=profile[1], profile_source_m=profile[2], profile_center_bed_m=profile[3], sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles, source_elevation_m=source, source_cell_ids=source_cells, cut_depth_m=cut, bed_elevation_m=source - cut, port_edge_node_indices=ports[0], port_xz_m=ports[1], port_profile_xz_m=ports[2], port_triangle_ids=ports[3], port_barycentric=ports[4], port_cut_depth_m=ports[5])
    metadata = dict(schema=METRIC_MONOTONE_UNION_SCHEMA, algorithm=METRIC_MONOTONE_UNION_ALGORITHM, terrain_metadata=_metadata_terrain(terrain), source_identity_sha256=terrain.identity_sha256, source_plan_identity_sha256=source_plan_identity_sha256, config=_i34_asdict(config), closure=closure, cut_volume_m3=_mesh_volume(vertices, triangles, cut), global_component_only=True, cross_component_verified=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    if centerline is not None:
        arrays.update(original_node_xz_m=ca['original_node_xz_m'].copy(), anchor_mask=ca['anchor_mask'].copy())
        metadata.update(algorithm=SHAPED_ALGORITHM, centerline_recipe=cm['recipe'])
    arrays = {key: _i34_readonly(value) for key, value in arrays.items()}
    bundle = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i34_identity(arrays, metadata)}
    validate_monotone_union(bundle)
    return bundle

def validate_monotone_union(bundle):
    from terrain_pipeline.common_infra import identity as _i34_identity
    from terrain_pipeline.common_infra import TerrainGrid as _i34_TerrainGrid
    if not isinstance(bundle, dict) or set(bundle) != {'arrays', 'metadata', 'identity_sha256'} or bundle['identity_sha256'] != _i34_identity(bundle['arrays'], bundle['metadata']) or (sum((value.nbytes for value in bundle['arrays'].values())) > METRIC_CHANNEL_GEOMETRY_MAX_BYTES):
        raise ValueError('monotone union identity or byte budget mismatch')
    a, m = (bundle['arrays'], bundle['metadata'])
    expected_arrays = {'source_node_cell_ids', 'receiver', 'node_xz_m', 'width_m', 'base_depth_m', 'source_height_m', 'source_valid_mask', 'owner_grid', 'corridor_mask', 'lake_mask', 'profile_offsets', 'profile_t', 'profile_source_m', 'profile_center_bed_m', 'sparse_cell_xy', 'vertices_xz_m', 'triangles', 'source_elevation_m', 'source_cell_ids', 'cut_depth_m', 'bed_elevation_m', 'port_edge_node_indices', 'port_xz_m', 'port_profile_xz_m', 'port_triangle_ids', 'port_barycentric', 'port_cut_depth_m'}
    expected_meta = {'schema', 'algorithm', 'terrain_metadata', 'source_identity_sha256', 'source_plan_identity_sha256', 'config', 'closure', 'cut_volume_m3', 'global_component_only', 'cross_component_verified', 'hydraulic_ready', 'natural_outlet_verified', 'publishable'}
    float_fields = {'node_xz_m', 'width_m', 'base_depth_m', 'source_height_m', 'profile_t', 'profile_source_m', 'profile_center_bed_m', 'vertices_xz_m', 'source_elevation_m', 'cut_depth_m', 'bed_elevation_m', 'port_xz_m', 'port_profile_xz_m', 'port_barycentric', 'port_cut_depth_m'}
    int_fields = {'source_node_cell_ids', 'receiver', 'owner_grid', 'profile_offsets', 'sparse_cell_xy', 'triangles', 'source_cell_ids', 'port_edge_node_indices', 'port_triangle_ids'}
    bool_fields = {'source_valid_mask', 'corridor_mask', 'lake_mask'}
    shaped = m.get('algorithm') == SHAPED_ALGORITHM
    if shaped:
        expected_arrays.update(('original_node_xz_m', 'anchor_mask'))
        expected_meta.add('centerline_recipe')
        float_fields.add('original_node_xz_m')
        bool_fields.add('anchor_mask')
    pin = m.get('source_plan_identity_sha256')
    if set(a) != expected_arrays or set(m) != expected_meta or any((not isinstance(a[key], _i34_np.ndarray) or a[key].dtype != _i34_np.float64 for key in float_fields)) or any((not isinstance(a[key], _i34_np.ndarray) or a[key].dtype != _i34_np.int64 for key in int_fields)) or any((not isinstance(a[key], _i34_np.ndarray) or a[key].dtype != bool for key in bool_fields)) or (not isinstance(pin, str)) or (len(pin) != 64) or any((ch not in '0123456789abcdef' for ch in pin)) or (m.get('schema') != METRIC_MONOTONE_UNION_SCHEMA) or (m.get('algorithm') not in (METRIC_MONOTONE_UNION_ALGORITHM, SHAPED_ALGORITHM)) or (m.get('global_component_only') is not True) or any((m.get(key) is not False for key in ('cross_component_verified', 'hydraulic_ready', 'natural_outlet_verified', 'publishable'))):
        raise ValueError('monotone union schema or scope mismatch')
    terrain = _i34_TerrainGrid(a['source_height_m'], a['source_valid_mask'], **m['terrain_metadata'])
    if terrain.identity_sha256 != m['source_identity_sha256']:
        raise ValueError('monotone union source mismatch')
    config = GeometryConfig(**m['config'])
    ids, receiver, width, depth = (a[key] for key in ('source_node_cell_ids', 'receiver', 'width_m', 'base_depth_m'))
    _check_inputs(terrain, ids, receiver, width, depth, a['owner_grid'], a['corridor_mask'], a['lake_mask'], config)
    if _i34_np.unique(a['owner_grid'].ravel()[ids]).size != 1:
        raise ValueError('monotone union component spans owners')
    cols = terrain.elevation_m.shape[1]
    points = _i34_np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m, terrain.z0_m + ids // cols * terrain.dz_m))
    if shaped:
        pass
        pass
        pass
        anchors = _anchors(receiver)
        if not _i34_np.array_equal(points, a['original_node_xz_m']) or not _i34_np.array_equal(anchors, a['anchor_mask']):
            raise ValueError('shaped bed original graph or anchors mismatch')
        _validate_shape(a['node_xz_m'], points, anchors, receiver, width, depth, terrain, a['owner_grid'], a['corridor_mask'], a['lake_mask'], config, CenterlineRecipe(**m['centerline_recipe']))
        points = a['node_xz_m']
    elif not _i34_np.array_equal(points, a['node_xz_m']):
        raise ValueError('monotone union fixed source node mismatch')
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, depth, terrain, config.max_cut_m)
    _footprint(points, receiver, width, _i34_np.full(len(points), config.max_cut_m), terrain, a['owner_grid'], a['corridor_mask'], a['lake_mask'], a['owner_grid'].ravel()[ids], config.fine_spacing_m)
    _profile_overlap(points, receiver, width, profile, terrain)
    cells = _sparse_cells(points, receiver, width, profile, config, terrain)
    vertices, triangles = _sparse_mesh(cells, terrain, config.fine_spacing_m, config.max_vertices)
    source, source_cells = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)
    base_cut = _profile_cut(points, receiver, width, profile, vertices, terrain, a['lake_mask'])
    cut = a['cut_depth_m']
    if cut.shape != base_cut.shape or not _i34_np.isfinite(cut).all() or _i34_np.any(cut < base_cut - 1e-09) or _i34_np.any(cut > config.max_cut_m + 1e-08):
        raise ValueError('monotone closure cut violates base envelope or maximum')
    _cut_source_constraints(vertices, source_cells, cut, terrain, a['owner_grid'], a['corridor_mask'], a['lake_mask'], a['owner_grid'].ravel()[ids[0]])
    _sparse_slope(points, receiver, cells, vertices, triangles, source - cut, config.fine_spacing_m, terrain)
    ports = _sparse_ports(points, receiver, width, profile, cells, vertices, triangles, cut, config.fine_spacing_m, terrain)
    expected = dict(profile_offsets=profile[0], profile_t=profile[1], profile_source_m=profile[2], profile_center_bed_m=profile[3], sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles, source_elevation_m=source, source_cell_ids=source_cells, cut_depth_m=cut, bed_elevation_m=source - cut, port_edge_node_indices=ports[0], port_xz_m=ports[1], port_profile_xz_m=ports[2], port_triangle_ids=ports[3], port_barycentric=ports[4], port_cut_depth_m=ports[5])
    for key, value in expected.items():
        if a[key].shape != value.shape or not _i34_np.allclose(a[key], value, rtol=0.0, atol=1e-08):
            raise ValueError('monotone union field mismatch: ' + key)
    extra = cut - base_cut
    closure = m['closure']
    segments = _line_constraints(points, receiver, cells, vertices, triangles, terrain, config.fine_spacing_m)
    if set(closure) != {'extra_cut_vertices', 'extra_cut_sum_m', 'maximum_constraint_residual_m', 'centerline_segments'} or closure['extra_cut_vertices'] != int(_i34_np.count_nonzero(extra > 1e-09)) or (not _i34_math.isclose(closure['extra_cut_sum_m'], float(_i34_np.sum(extra)), abs_tol=1e-08)) or (closure['centerline_segments'] != len(segments)) or (not _i34_math.isfinite(closure['maximum_constraint_residual_m'])) or (closure['maximum_constraint_residual_m'] > 1e-07) or (not _i34_math.isclose(m['cut_volume_m3'], _mesh_volume(vertices, triangles, cut), rel_tol=1e-10, abs_tol=1e-07)):
        raise ValueError('monotone closure material ledger mismatch')
    return True

def save_monotone_union(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _i34_save_bundle
    _i34_save_bundle(path, bundle, validator=validate_monotone_union)

def load_monotone_union(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _i34_load_bundle
    bundle = _i34_load_bundle(path, expected_sha256=expected_sha256, validator=validate_monotone_union, max_bytes=METRIC_CHANNEL_GEOMETRY_MAX_BYTES)
    if bundle['identity_sha256'] != expected_identity:
        raise ValueError('external monotone union identity mismatch')
    return bundle
DESIGN_BED_CONSTRAINT_MODEL = 'fan4-physical-gradient-profile-actual-transverse-exterior-node-cone-v1'

def shared_section_constraints(sections, cells, vertices, triangles, source, terrain, spacing):
    """Fix the complete affine trace, including every represented triangle crossing."""
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = _i27_np.array([terrain.x0_m, terrain.z0_m])
    rows = []
    for section in sections:
        position = _i27_np.asarray(section['position_xz_m'], float)
        normal = _i27_np.asarray(section['normal_xz'], float)
        offsets = _i27_np.asarray(section['offsets_m'], float)
        bed = _i27_np.asarray(section['bed_elevation_m'], float)
        if position.shape != (2,) or normal.shape != (2,) or offsets.ndim != 1 or (len(offsets) < 2) or (bed.shape != offsets.shape) or _i27_np.any(_i27_np.diff(offsets) <= 0) or (not all((_i27_np.isfinite(value).all() for value in (position, normal, offsets, bed)))) or (not _i27_np.isclose(_i27_np.linalg.norm(normal), 1.0, atol=1e-10, rtol=0)):
            raise ValueError('finite ordered shared fan4 cross-section required')
        ends = position + offsets[[0, -1], None] * normal
        segments = _line_constraints(ends, _i27_np.array([1, -1]), cells, vertices, triangles, terrain, spacing)
        samples = list(position + offsets[:, None] * normal)
        for start, end, _, _, _ in segments:
            samples.extend((start[1] @ vertices[start[0]], end[1] @ vertices[end[0]]))
        for point in samples:
            offset = float((point - position) @ normal)
            target = float(_i27_np.interp(offset, offsets, bed))
            key = _cell_at_point(point, lookup, origin, spacing)
            ids, weights = _barycentric(point, lookup[key], vertices, triangles)
            cut = float(weights @ source[ids] - target)
            rows.extend(((ids, weights, cut, 'shared_section'), (ids, -weights, -cut, 'shared_section')))
    return rows

def interior_support_boundary_vertices(cells, vertices, terrain, spacing):
    """Return exposed mesh corners inside the known domain that must reconnect."""
    origin = _i27_np.array([terrain.x0_m, terrain.z0_m])
    vertex_keys = _i27_np.rint((vertices - origin) * 2.0 / spacing).astype(_i27_np.int64)
    minimum = cells.min(axis=0) - 1
    stride = int(cells[:, 0].max() - minimum[0]) + 3
    cell_keys = (cells[:, 1] - minimum[1]) * stride + cells[:, 0] - minimum[0]
    sorted_cells = _i27_np.sort(cell_keys)
    vertex_stride = 2 * stride
    encoded_vertices = (vertex_keys[:, 1] - 2 * minimum[1]) * vertex_stride + vertex_keys[:, 0] - 2 * minimum[0]
    vertex_order = _i27_np.argsort(encoded_vertices)
    sorted_vertices = encoded_vertices[vertex_order]
    maximum = _i27_np.rint(_i27_np.array([(terrain.elevation_m.shape[1] - 1) * terrain.dx_m, (terrain.elevation_m.shape[0] - 1) * terrain.dz_m]) / spacing).astype(int)
    boundary = _i27_np.zeros(len(vertices), bool)
    for start in range(0, len(cells), 200000):
        block = cells[start:start + 200000]
        keys = cell_keys[start:start + len(block)]
        faces = ((-1, ((0, 0), (0, 1)), block[:, 0] > 0), (1, ((1, 0), (1, 1)), block[:, 0] + 1 < maximum[0]), (-stride, ((0, 0), (1, 0)), block[:, 1] > 0), (stride, ((0, 1), (1, 1)), block[:, 1] + 1 < maximum[1]))
        for offset, corners, interior in faces:
            neighbors = keys + offset
            positions = _i27_np.searchsorted(sorted_cells, neighbors)
            present = sorted_cells[_i27_np.minimum(positions, len(sorted_cells) - 1)] == neighbors
            exposed = block[interior & ~present]
            for corner in corners:
                xy = 2 * (exposed + corner - minimum)
                encoded = xy[:, 1] * vertex_stride + xy[:, 0]
                boundary[vertex_order[_i27_np.searchsorted(sorted_vertices, encoded)]] = True
    return _i27_np.flatnonzero(boundary)

def build_design_geometry(points, receiver, width, design_depth, profile, terrain, spacing, max_cut, minimum_slope, *, transverse_bottom_slope=0.02, center_lowest=False, continuous_center_lowest=False, shared_sections=None):
    """Build known-domain support for the conservative bottom and zero bank edge."""
    support_guard = (_i27_np.sqrt(2.0) + 1.0) * spacing
    edge_nodes = _i27_np.flatnonzero(receiver >= 0)
    support_radius = _i27_np.maximum(width[edge_nodes], width[receiver[edge_nodes]]) / 2.0 + support_guard + 2.0 * max_cut
    options = _i27_SimpleNamespace(fine_spacing_m=spacing, max_cut_m=max_cut, max_vertices=8000000)
    cells = _sparse_cells(points, receiver, width, profile, options, terrain, support_radius_m=support_radius)
    vertices, triangles = _sparse_mesh(cells, terrain, spacing, options.max_vertices)
    source, source_cells = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)
    lower, upper, padding = design_cut_bounds(points, receiver, width, design_depth, cells, vertices, triangles, terrain, spacing, max_cut)
    boundary = interior_support_boundary_vertices(cells, vertices, terrain, spacing)
    if _i27_np.any(lower[boundary] > 1e-10):
        raise ValueError('continuous design bank does not reconnect within known support')
    upper[boundary] = 0.0
    cut, closure = solve_design_bed(points, receiver, cells, vertices, triangles, source, lower, upper, terrain, spacing, profile, minimum_slope, width=width, transverse_bottom_slope=transverse_bottom_slope, center_lowest=center_lowest, continuous_center_lowest=continuous_center_lowest, shared_sections=shared_sections)
    if _i27_np.any(_i27_np.abs(cut[boundary]) > 1e-10):
        raise ValueError('actual design bed has nonzero interior support boundary cut')
    closure.update(interior_support_boundary_vertices=len(boundary), maximum_interior_support_boundary_cut_m=float(_i27_np.max(_i27_np.abs(cut[boundary]), initial=0.0)))
    return (cells, vertices, triangles, source, source_cells, cut, closure, lower, upper, padding, boundary)

def merge_design_bundles(terrain, bundles, config, network_design_depth):
    """Preserve legacy cuts while recomputing necessary new design incision once."""
    from terrain_pipeline.common_infra import identity as _i27_identity
    spacing = config.fine_spacing_m
    cells = _i27_np.unique(_i27_np.concatenate([b['arrays']['sparse_cell_xy'] for b in bundles]), axis=0)
    cells = cells[_i27_np.lexsort((cells[:, 0], cells[:, 1]))]
    vertex_budget = sum((len(b['arrays']['vertices_xz_m']) for b in bundles))
    vertices, triangles = _sparse_mesh(cells, terrain, spacing, vertex_budget)
    source, source_cells = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)
    origin = _i27_np.array([terrain.x0_m, terrain.z0_m])
    keys = _i27_np.rint((vertices - origin) * 2.0 / spacing).astype(_i27_np.int64)
    minimum = cells.min(axis=0)
    stride = int(cells[:, 0].max() - minimum[0]) + 2
    vertex_keys = (keys[:, 1] - 2 * minimum[1]) * (2 * stride) + keys[:, 0] - 2 * minimum[0]
    vertex_order = _i27_np.argsort(vertex_keys)
    sorted_vertex_keys = vertex_keys[vertex_order]
    cell_keys = (cells[:, 1] - minimum[1]) * stride + cells[:, 0] - minimum[0]
    del keys, vertex_keys
    lower = _i27_np.zeros(len(vertices))
    legacy_lower = _i27_np.zeros(len(vertices))
    reference_cut = _i27_np.zeros(len(vertices))
    padding = _i27_np.zeros(len(vertices))
    vertex_mask = _i27_np.zeros(len(vertices), bool)
    triangle_mask = _i27_np.zeros(len(triangles), bool)
    node_masks, receivers, ids, points, widths, depths = ([], [], [], [], [], [])
    component_supports = []
    all_new = all(('design_minimum_cut_m' in b['arrays'] for b in bundles))
    offsets, parameters, profile_source, profile_bed = ([0], [], [], [])
    node_offset = 0
    for bundle in bundles:
        a = bundle['arrays']
        local_keys = _i27_np.rint((a['vertices_xz_m'] - origin) * 2.0 / spacing).astype(_i27_np.int64)
        encoded = (local_keys[:, 1] - 2 * minimum[1]) * (2 * stride) + local_keys[:, 0] - 2 * minimum[0]
        mapping = vertex_order[_i27_np.searchsorted(sorted_vertex_keys, encoded)]
        local_cells = a['sparse_cell_xy']
        cell_ids = _i27_np.searchsorted(cell_keys, (local_cells[:, 1] - minimum[1]) * stride + local_cells[:, 0] - minimum[0])
        del local_keys, encoded
        new = 'design_minimum_cut_m' in a
        if all_new:
            face_ids = (4 * cell_ids[:, None] + _i27_np.arange(4)).ravel()
            same_mesh = _i27_np.array_equal(triangles[face_ids], mapping[a['triangles']]) and bundle.get('metadata', {}).get('config') == _i27_asdict(config) and (bundle.get('metadata', {}).get('source_identity_sha256') == terrain.identity_sha256)
            component_supports.append((bundle, mapping, same_mesh))
        necessary = a['design_minimum_cut_m'] if new else a['cut_depth_m']
        _i27_np.maximum.at(lower, mapping, necessary)
        _i27_np.maximum.at(reference_cut, mapping, a['cut_depth_m'])
        if new:
            vertex_mask[mapping] = True
            _i27_np.maximum.at(padding, mapping, a['source_interpolation_padding_m'])
            triangle_mask.reshape(-1, 4)[cell_ids] = True
        else:
            _i27_np.maximum.at(legacy_lower, mapping, necessary)
        node_masks.append(_i27_np.full(len(a['receiver']), new, bool))
        receivers.append(_i27_np.where(a['receiver'] >= 0, a['receiver'] + node_offset, -1))
        ids.append(a['source_node_cell_ids'])
        points.append(a['node_xz_m'])
        widths.append(a['width_m'])
        depths.append(a['base_depth_m'])
        offsets.extend(a['profile_offsets'][1:] + offsets[-1])
        parameters.extend(a['profile_t'])
        profile_source.extend(a['profile_source_m'])
        profile_bed.extend(a['profile_center_bed_m'])
        node_offset += len(a['receiver'])
    receiver = _i27_np.concatenate(receivers)
    points = _i27_np.concatenate(points)
    ids = _i27_np.concatenate(ids)
    node_mask = _i27_np.concatenate(node_masks)
    profile = (_i27_np.asarray(offsets, _i27_np.int64), _i27_np.asarray(parameters), _i27_np.asarray(profile_source), _i27_np.asarray(profile_bed))
    del vertex_order, sorted_vertex_keys, cell_keys, mapping
    upper = _i27_np.full(len(vertices), config.max_cut_m)
    upper[vertex_mask] -= padding[vertex_mask]
    boundary = interior_support_boundary_vertices(cells, vertices, terrain, spacing)
    zero_mask = _i27_np.zeros(len(vertices), bool)
    zero_mask[boundary] = vertex_mask[boundary] & (legacy_lower[boundary] == 0.0)
    upper[zero_mask] = 0.0
    cut, closure = solve_design_bed(points, receiver, cells, vertices, triangles, source, lower, upper, terrain, spacing, profile, 1e-05, node_mask, width=_i27_np.concatenate(widths), transverse_bottom_slope=getattr(config, 'transverse_bottom_slope_m_per_m', 0.02), component_supports=component_supports if all_new else None)
    arrays = dict(source_height_m=terrain.elevation_m, source_valid_mask=terrain.valid_mask, source_node_cell_ids=ids, receiver=receiver, node_xz_m=points, width_m=_i27_np.concatenate(widths), base_depth_m=_i27_np.concatenate(depths), design_base_depth_m=network_design_depth[ids], design_constraint_node_mask=node_mask, design_constraint_vertex_mask=vertex_mask, design_constraint_triangle_mask=triangle_mask, design_zero_boundary_vertex_mask=zero_mask, design_minimum_cut_m=lower, design_maximum_cut_m=upper, source_interpolation_padding_m=padding, sparse_cell_xy=cells, vertices_xz_m=vertices, triangles=triangles, source_elevation_m=source, source_cell_ids=source_cells, cut_depth_m=cut, bed_elevation_m=source - cut, profile_offsets=profile[0], profile_t=profile[1], profile_source_m=profile[2], profile_center_bed_m=profile[3])
    metadata = dict(schema='td-generated-component-bed-v1', algorithm='unique-mixed-legacy-and-transverse-coupled-design-bed-v2', terrain_metadata=terrain.metadata(), source_identity_sha256=terrain.identity_sha256, config=_i27_asdict(config), cut_volume_m3=_mesh_volume_chunked(vertices, triangles, cut), preclosure_cut_volume_m3=_mesh_volume_chunked(vertices, triangles, lower), component_max_cut_reference_volume_m3=_mesh_volume_chunked(vertices, triangles, reference_cut), maximum_cut_m=float(cut.max()), closure=closure, minimum_bed_slope_m_per_m=1e-05, design_bed_policy=dict(certificate_scope='masked new component support only; legacy actual cut locked', bottom_triangle_guard_m=_i27_np.sqrt(2.0) * spacing, bank_slope=2.0, design_depth_policy='edge endpoint maximum', source_padding='maximum incident new fan4 triangle bilinear error', profile_constraint_policy='mesh triangle boundaries union profile knots', necessary_lower_policy='maximum legacy actual cut and new design minimum; new solved cut is not locked', known_domain_boundary_cut_policy='zero new exposed interior bank vertices with zero legacy necessary cut', transverse_bed_policy='actual solved center bed coupled across full bottom; bounded transverse bottom slope and bank ceiling relative to projected center', transverse_bottom_slope_m_per_m=getattr(config, 'transverse_bottom_slope_m_per_m', 0.02), transverse_bank_horizontal_per_vertical=2.0, transverse_bottom_guard_m=_i27_np.sqrt(2.0) * spacing, transverse_node_cap_policy='all incident unit-direction dot distances <= 1e-10m; actual node bed coupled', transverse_node_cap_dot_tolerance_m=1e-10), natural_outlet_verified=False, hydraulic_ready=False, publishable=False)
    return dict(arrays=arrays, metadata=metadata, identity_sha256=_i27_identity(arrays, metadata))

def _mesh_volume_chunked(vertices, triangles, heights, *, datum=0.0):
    """Integrate the same piecewise-linear field without expanding the full mesh."""
    volume = 0.0
    for start in range(0, len(triangles), 200000):
        faces = triangles[start:start + 200000]
        xy = vertices[faces]
        area = _i27_np.abs((xy[:, 1, 0] - xy[:, 0, 0]) * (xy[:, 2, 1] - xy[:, 0, 1]) - (xy[:, 2, 0] - xy[:, 0, 0]) * (xy[:, 1, 1] - xy[:, 0, 1])) / 2.0
        volume += float(_i27_np.sum(area * _i27_np.mean(heights[faces] - datum, axis=1)))
    return volume

def source_interpolation_padding(cells, vertices, triangles, terrain, spacing):
    """Exact fan4 error bound for a fine cell within one bilinear source cell."""
    if not _i27_np.isfinite(spacing) or spacing <= 0.0:
        raise ValueError('positive finite fine spacing required')
    ratios = _i27_np.array([terrain.dx_m, terrain.dz_m]) / spacing
    if not _i27_np.all(_i27_np.isfinite(ratios)) or _i27_np.any(ratios < 1.0) or (not _i27_np.allclose(ratios, _i27_np.rint(ratios), rtol=0.0, atol=1e-10)):
        raise ValueError('continuous design requires aligned native and fine grids')
    middle = (cells + 0.5) * spacing
    x = _i27_np.floor(middle[:, 0] / terrain.dx_m).astype(_i27_np.int64)
    z = _i27_np.floor(middle[:, 1] / terrain.dz_m).astype(_i27_np.int64)
    height = terrain.elevation_m
    cross = height[z + 1, x + 1] - height[z + 1, x] - height[z, x + 1] + height[z, x]
    cell_padding = _i27_np.abs(cross) * spacing ** 2 / (16.0 * terrain.dx_m * terrain.dz_m)
    padding = _i27_np.zeros(len(vertices))
    _i27_np.maximum.at(padding, triangles.ravel(), _i27_np.repeat(cell_padding, 12))
    return padding

def design_cut_bounds(points, receiver, width, design_depth, cells, vertices, triangles, terrain, spacing, max_cut):
    """Cover each design-bottom triangle with a conservative constant depth."""
    padding = source_interpolation_padding(cells, vertices, triangles, terrain, spacing)
    lower = _i27_np.zeros(len(vertices))
    tree = _i27_cKDTree(vertices)
    guard = _i27_np.sqrt(2.0) * spacing
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        a, b = (points[i], points[j])
        delta = b - a
        depth = max(float(design_depth[i]), float(design_depth[j]))
        half = max(float(width[i]), float(width[j])) / 2.0 + guard
        near = _i27_np.asarray(tree.query_ball_point((a + b) / 2.0, _i27_np.linalg.norm(delta) / 2.0 + half + 2.0 * depth), _i27_np.int64)
        t = _i27_np.clip((vertices[near] - a) @ delta / _i27_np.dot(delta, delta), 0.0, 1.0)
        distance = _i27_np.linalg.norm(vertices[near] - (a + t[:, None] * delta), axis=1)
        amount = _i27_np.minimum(depth, _i27_np.maximum(0.0, (half + 2.0 * depth - distance) / 2.0))
        lower[near] = _i27_np.maximum(lower[near], amount)
    lower += _i27_np.where(lower > 0.0, padding, 0.0)
    upper = max_cut - padding
    if _i27_np.any(lower > upper + 1e-10):
        raise ValueError('continuous design depth exceeds original-source cut budget')
    return (lower, upper, padding)

def bed_constraints(points, receiver, cells, vertices, triangles, source, terrain, spacing, profile, minimum_slope, profile_node_mask=None):
    """Build physical gradients and the union of mesh and profile breakpoints."""
    segments = _line_constraints(points, receiver, cells, vertices, triangles, terrain, spacing)
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = _i27_np.array([terrain.x0_m, terrain.z0_m])
    edge_by_node = _i27_np.full(len(receiver), -1, _i27_np.int64)
    edge_by_node[receiver >= 0] = _i27_np.arange(_i27_np.count_nonzero(receiver >= 0))
    if profile_node_mask is None:
        profile_node_mask = _i27_np.ones(len(receiver), bool)
    rows = []
    for start, end, _, i, j in segments:
        midpoint = (start[1] @ vertices[start[0]] + end[1] @ vertices[end[0]]) / 2.0
        cell = lookup[_cell_at_point(midpoint, lookup, origin, spacing)]
        delta = points[j] - points[i]
        ids, weights = _mesh_directional_weights(midpoint, cell, vertices, triangles, delta / _i27_np.linalg.norm(delta))
        source_gradient = float(weights[1:] @ (source[ids[1:]] - source[ids[0]]))
        rows.append((ids, -weights, -minimum_slope - source_gradient, 'gradient'))
        if not profile_node_mask[i]:
            continue
        edge = edge_by_node[i]
        lo, hi = profile[0][edge:edge + 2]
        for ids, weights in (start, end):
            point = weights @ vertices[ids]
            t = float(_i27_np.clip((point - points[i]) @ delta / _i27_np.dot(delta, delta), 0.0, 1.0))
            target = _i27_np.interp(t, profile[1][lo:hi], profile[3][lo:hi])
            rows.append((ids, -weights, float(target - weights @ source[ids]), 'profile'))
    for i, j in enumerate(receiver):
        if j < 0 or not profile_node_mask[i]:
            continue
        lo, hi = profile[0][edge_by_node[i]:edge_by_node[i] + 2]
        for t, target in zip(profile[1][lo:hi], profile[3][lo:hi]):
            point = points[i] + t * (points[j] - points[i])
            cell = lookup[_cell_at_point(point, lookup, origin, spacing)]
            ids, weights = _barycentric(point, cell, vertices, triangles)
            rows.append((ids, -weights, float(target - weights @ source[ids]), 'profile'))
    return rows

def _barycentric_batch(points, cells, vertices, triangles):
    """Keep scalar fan4 tolerance and first-face selection with stacked solves."""
    indices = _i27_np.empty((len(points), 3), _i27_np.int64)
    weights = _i27_np.empty((len(points), 3))
    if not len(points):
        return (indices, weights)
    scale = _i27_np.maximum(1.0, _i27_np.max(_i27_np.abs(points), axis=1))
    first = triangles[4 * cells]
    span = _i27_np.linalg.norm(vertices[first[:, 1]] - vertices[first[:, 0]], axis=1)
    tolerance = _i27_np.maximum(1e-09, 8.0 * _i27_np.spacing(scale) / span)
    pending = _i27_np.ones(len(points), bool)
    for face in range(4):
        rows = _i27_np.flatnonzero(pending)
        if not len(rows):
            break
        ids = triangles[4 * cells[rows] + face]
        tri = vertices[ids]
        matrix = _i27_np.stack((tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=2)
        uv = _i27_np.linalg.solve(matrix, (points[rows] - tri[:, 0])[:, :, None])[:, :, 0]
        bary = _i27_np.column_stack((1.0 - uv.sum(axis=1), uv[:, 0], uv[:, 1]))
        accepted = _i27_np.min(bary, axis=1) >= -tolerance[rows]
        selected = rows[accepted]
        indices[selected], weights[selected] = (ids[accepted], bary[accepted])
        pending[selected] = False
    if pending.any():
        raise ValueError('centerline point outside sparse triangles')
    return (indices, weights)

def transverse_bed_constraints(points, receiver, width, cells, vertices, triangles, source, terrain, spacing, maximum_cut, node_mask=None, transverse_bottom_slope=0.02, center_lowest=False, internal_port_mask=None):
    """Couple bottom and bank elevations to the actual variable center bed."""
    if width.shape != (len(points),) or _i27_np.any(width <= 0.0) or (not _i27_np.isfinite(width).all()):
        raise ValueError('positive finite bottom width required at every node')
    if not _i27_np.isfinite(transverse_bottom_slope) or not 0.0 <= transverse_bottom_slope < 0.5:
        raise ValueError('transverse bottom slope must be finite and in [0, 0.5)')
    if node_mask is None:
        node_mask = _i27_np.ones(len(points), bool)
    tree = _i27_cKDTree(vertices)
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = _i27_np.array([terrain.x0_m, terrain.z0_m])
    guard = _i27_np.sqrt(2.0) * spacing
    index_batches, weight_batches, limit_batches = ([], [], [])
    maximum_depth = float(_i27_np.max(maximum_cut))
    incident_directions = [[] for _ in points]
    incident_width = width.copy()
    enabled_incident = _i27_np.zeros(len(points), bool)
    for i, j in enumerate(receiver):
        if j < 0:
            continue
        direction = points[j] - points[i]
        direction = direction / _i27_np.linalg.norm(direction)
        incident_directions[i].append(direction)
        incident_directions[j].append(-direction)
        edge_width = max(float(width[i]), float(width[j]))
        incident_width[i] = max(incident_width[i], edge_width)
        incident_width[j] = max(incident_width[j], edge_width)
        if node_mask[i]:
            enabled_incident[i] = enabled_incident[j] = True
    for i, j in enumerate(receiver):
        if j < 0 or not node_mask[i]:
            continue
        a, b = (points[i], points[j])
        delta = b - a
        half = max(float(width[i]), float(width[j])) / 2.0 + guard
        radius = half + 2.0 * maximum_depth
        near = _i27_np.asarray(tree.query_ball_point((a + b) / 2.0, _i27_np.linalg.norm(delta) / 2.0 + radius), _i27_np.int64)
        t = (vertices[near] - a) @ delta / (delta @ delta)
        projected = a + t[:, None] * delta
        distance = _i27_np.linalg.norm(vertices[near] - projected, axis=1)
        selected = (distance > 1e-10) & (distance <= radius) & (t >= 0.0) & (t <= 1.0)
        near, projected, distance = (near[selected], projected[selected], distance[selected])
        indices = _i27_np.empty((len(near), 4), _i27_np.int64)
        weights = _i27_np.empty((len(near), 4))
        indices[:, 0], weights[:, 0] = (near, -1.0)
        cell_ids = _i27_np.asarray([lookup[_cell_at_point(center, lookup, origin, spacing)] for center in projected], _i27_np.int64)
        indices[:, 1:], weights[:, 1:] = _barycentric_batch(projected, cell_ids, vertices, triangles)
        rise = _i27_np.minimum(distance, half) * transverse_bottom_slope + _i27_np.maximum(0.0, distance - half) / 2.0
        limits = rise + _i27_np.sum(weights * source[indices], axis=1)
        index_batches.append(indices)
        weight_batches.append(weights)
        limit_batches.append(limits)
        if center_lowest:
            closest = distance.copy()
            for first, second in enumerate(receiver):
                if second < 0:
                    continue
                vector = points[second] - points[first]
                fraction = _i27_np.clip((vertices[near] - points[first]) @ vector / (vector @ vector), 0, 1)
                closest = _i27_np.minimum(closest, _i27_np.linalg.norm(vertices[near] - points[first] - fraction[:, None] * vector, axis=1))
            owned = distance <= closest + 1e-08
            index_batches.append(indices[owned])
            weight_batches.append(-weights[owned])
            limit_batches.append(-_i27_np.sum(weights[owned] * source[indices[owned]], axis=1))
    cap_count = 0
    for node, directions in enumerate(incident_directions):
        if not directions or not node_mask[node] or (not enabled_incident[node]):
            continue
        if internal_port_mask is not None and internal_port_mask[node]:
            continue
        half = incident_width[node] / 2.0 + guard
        radius = half + 2.0 * maximum_depth
        near = _i27_np.asarray(tree.query_ball_point(points[node], radius), _i27_np.int64)
        displacement = vertices[near] - points[node]
        distance = _i27_np.linalg.norm(displacement, axis=1)
        selected = (distance > 1e-10) & _i27_np.all(displacement @ _i27_np.asarray(directions).T <= 1e-10, axis=1)
        near, distance = (near[selected], distance[selected])
        cell = lookup[_cell_at_point(points[node], lookup, origin, spacing)]
        ids, bary = _barycentric(points[node], cell, vertices, triangles)
        indices = _i27_np.empty((len(near), 4), _i27_np.int64)
        weights = _i27_np.empty((len(near), 4))
        indices[:, 0], weights[:, 0] = (near, -1.0)
        indices[:, 1:], weights[:, 1:] = (ids, bary)
        rise = _i27_np.minimum(distance, half) * transverse_bottom_slope + _i27_np.maximum(0.0, distance - half) / 2.0
        limits = rise + _i27_np.sum(weights * source[indices], axis=1)
        index_batches.append(indices)
        weight_batches.append(weights)
        limit_batches.append(limits)
        cap_count += len(near)
    if not index_batches:
        return (_i27_np.empty((0, 4), _i27_np.int64), _i27_np.empty((0, 4)), _i27_np.empty(0), 0)
    return (_i27_np.concatenate(index_batches), _i27_np.concatenate(weight_batches), _i27_np.concatenate(limit_batches), cap_count)

def _clip_floor_polygon(polygon, normal, limit):
    """Clip an affine mesh region against one closed half-plane."""
    if len(polygon) == 0:
        return polygon
    output = []
    previous = polygon[-1]
    previous_value = float(previous @ normal - limit)
    for current in polygon:
        current_value = float(current @ normal - limit)
        if (current_value <= 1e-10) != (previous_value <= 1e-10):
            fraction = _i27_np.clip(previous_value / (previous_value - current_value), 0.0, 1.0)
            output.append(previous + fraction * (current - previous))
        if current_value <= 1e-10:
            output.append(current)
        previous, previous_value = (current, current_value)
    return _i27_np.asarray(output).reshape(-1, 2)

def _shared_junction_floor_regions(polygon, own_normal, junction, rays):
    """Cover nearest finite-segment regions; distant end caps are conservative."""
    regions = [polygon]
    for ray, length in rays:
        other_normal = _i27_np.array([-ray[1], ray[0]])
        following = []
        for region in regions:
            before = _clip_floor_polygon(region, ray, float(junction @ ray))
            beyond = _clip_floor_polygon(region, -ray, -float(junction @ ray) - length)
            if len(before) >= 3:
                following.append(before)
            if len(beyond) >= 3:
                following.append(beyond)
            interior = _clip_floor_polygon(region, -ray, -float(junction @ ray))
            interior = _clip_floor_polygon(interior, ray, float(junction @ ray) + length)
            for own_sign in (-1, 1):
                for other_sign in (-1, 1):
                    part = _clip_floor_polygon(interior, -own_sign * own_normal, -float(junction @ (own_sign * own_normal)))
                    part = _clip_floor_polygon(part, -other_sign * other_normal, -float(junction @ (other_sign * other_normal)))
                    difference = own_sign * own_normal - other_sign * other_normal
                    part = _clip_floor_polygon(part, difference, float(junction @ difference))
                    if len(part) >= 3:
                        following.append(part)
        regions = following
    return regions

def _edge_continuous_floor_constraints(node, points, receiver, width, cells, vertices, triangles, source, terrain, spacing, maximum_cut, junction=None):
    other = int(receiver[node])
    a, b = (points[node], points[other])
    delta = b - a
    length = float(_i27_np.linalg.norm(delta))
    unit = delta / length
    normal = _i27_np.array([-unit[1], unit[0]])
    line = _line_constraints(points, receiver, cells, vertices, triangles, terrain, spacing)
    knots = [0.0, length]
    for start, end, _, first, _ in line:
        if first != node:
            continue
        knots.extend([float((weights @ vertices[ids] - a) @ unit) for ids, weights in (start, end)])
    knots = _i27_np.unique(_i27_np.clip(knots, 0.0, length))
    query_points = []
    for face in triangles:
        polygon = vertices[face] - a
        along = polygon @ unit
        if along.max() < 0 or along.min() > length:
            continue
        if len(polygon) < 3:
            continue
        lo = max(0, int(_i27_np.searchsorted(knots, along.min(), side='right')) - 1)
        hi = min(len(knots) - 1, int(_i27_np.searchsorted(knots, along.max(), side='left')) + 1)
        for index in range(lo, hi):
            region = _clip_floor_polygon(polygon, -unit, -knots[index])
            region = _clip_floor_polygon(region, unit, knots[index + 1])
            regions = [region]
            if junction is not None:
                rays = []
                for first in _i27_np.flatnonzero(receiver >= 0):
                    if first == node:
                        continue
                    second = int(receiver[first])
                    endpoint = points[second] if first == junction else points[first]
                    vector = endpoint - points[junction]
                    other_length = float(_i27_np.linalg.norm(vector))
                    rays.append((vector / other_length, other_length))
                regions = _shared_junction_floor_regions(region, normal, points[junction] - a, rays)
            for part in regions:
                if len(part) >= 3:
                    query_points.extend(part + a)
        if len(query_points) > 2500000:
            raise ValueError('continuous center-floor polygon work budget exceeded')
    if not query_points:
        raise ValueError('continuous center-floor has no represented strip')
    side = _i27_np.unique(_i27_np.round(_i27_np.asarray(query_points) - a, decimals=10), axis=0) + a
    center = a + ((side - a) @ unit)[:, None] * unit
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = _i27_np.array([terrain.x0_m, terrain.z0_m])
    side_cells = _i27_np.asarray([lookup[_cell_at_point(point, lookup, origin, spacing)] for point in side], _i27_np.int64)
    center_cells = _i27_np.asarray([lookup[_cell_at_point(point, lookup, origin, spacing)] for point in center], _i27_np.int64)
    side_ids, side_weights = _barycentric_batch(side, side_cells, vertices, triangles)
    center_ids, center_weights = _barycentric_batch(center, center_cells, vertices, triangles)
    indices = _i27_np.column_stack((center_ids, side_ids))
    weights = _i27_np.column_stack((-center_weights, side_weights))
    limits = _i27_np.sum(weights * source[indices], axis=1)
    return (indices, weights, limits)

def continuous_center_floor_constraints(points, receiver, width, cells, vertices, triangles, source, terrain, spacing, maximum_cut):
    """Prove floor on each affine region, with conservative finite-end ownership."""
    edges = _i27_np.flatnonzero(receiver >= 0)
    junction = None
    if len(edges) > 1:
        common = set([int(edges[0]), int(receiver[edges[0]])])
        for first in edges[1:]:
            common &= {int(first), int(receiver[first])}
        if len(common) != 1 or len(edges) > 4:
            raise ValueError('continuous center-floor requires one edge or at most four arms at one shared junction')
        junction = common.pop()
    results = [_edge_continuous_floor_constraints(int(node), points, receiver, width, cells, vertices, triangles, source, terrain, spacing, maximum_cut, junction) for node in edges]
    if not results or sum((len(record[2]) for record in results)) > 2500000:
        raise ValueError('continuous center-floor polygon work budget exceeded')
    return tuple((_i27_np.concatenate([record[index] for record in results]) for index in range(3)))

def _vertex_volume_weights(vertices, triangles):
    weights = _i27_np.zeros(len(vertices))
    for start in range(0, len(triangles), 200000):
        faces = triangles[start:start + 200000]
        tri = vertices[faces]
        delta1, delta2 = (tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        area = _i27_np.abs(delta1[:, 0] * delta2[:, 1] - delta1[:, 1] * delta2[:, 0]) / 2.0
        _i27_np.add.at(weights, faces.ravel(), _i27_np.repeat(area / 3.0, 3))
    return weights

def _design_support_groups(component_supports, vertex_count, active, matrix):
    parent = _i27_np.arange(len(component_supports))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return int(index)

    def join(first, second):
        first, second = (root(first), root(second))
        parent[max(first, second)] = min(first, second)
    owner = _i27_np.full(vertex_count, -1, _i27_np.int32)
    for index, (_, mapping, _) in enumerate(component_supports):
        for previous in _i27_np.unique(owner[mapping]):
            if previous >= 0:
                join(index, int(previous))
        owner[mapping] = index
    roots = _i27_np.asarray([root(i) for i in range(len(parent))])
    active_owner = roots[owner[active]]
    counts = _i27_np.diff(matrix.indptr)
    nonempty = counts > 0
    row_min = _i27_np.full(matrix.shape[0], -1, _i27_np.int32)
    row_max = row_min.copy()
    starts = matrix.indptr[:-1][nonempty]
    row_min[nonempty] = _i27_np.minimum.reduceat(active_owner[matrix.indices], starts)
    row_max[nonempty] = _i27_np.maximum.reduceat(active_owner[matrix.indices], starts)
    for row in _i27_np.flatnonzero(row_min != row_max):
        groups = _i27_np.unique(active_owner[matrix.indices[matrix.indptr[row]:matrix.indptr[row + 1]]])
        for group in groups[1:]:
            join(int(groups[0]), int(group))
    roots = _i27_np.asarray([root(i) for i in range(len(parent))])
    active_owner = roots[owner[active]]
    row_owner = _i27_np.full(matrix.shape[0], int(roots[0]), _i27_np.int32)
    row_owner[nonempty] = active_owner[matrix.indices[starts]]
    return (roots, active_owner, row_owner)

def _saved_design_optimum(bundle, mapping, same_mesh, source, minimum_cut, maximum_cut, volume_weights, minimum_slope, bottom_slope):
    a, metadata = (bundle['arrays'], bundle.get('metadata', {}))
    closure = metadata.get('closure', {})
    if not same_mesh or closure.get('constraint_model') != DESIGN_BED_CONSTRAINT_MODEL or metadata.get('minimum_bed_slope_m_per_m') != minimum_slope or (closure.get('transverse_bottom_slope_m_per_m') != bottom_slope) or (not all((closure.get(key) is True for key in ('minimum_volume_objective', 'physical_triangle_plane_gradient', 'profile_mesh_breakpoint_union', 'transverse_bed_coupling')))):
        return False
    for actual, name in ((source[mapping], 'source_elevation_m'), (minimum_cut[mapping], 'design_minimum_cut_m'), (maximum_cut[mapping], 'design_maximum_cut_m')):
        if name not in a or not _i27_np.array_equal(actual, a[name]):
            return False
    old_weights = _vertex_volume_weights(a['vertices_xz_m'], a['triangles'])
    return _i27_np.array_equal(volume_weights[mapping], old_weights)

def solve_design_bed(points, receiver, cells, vertices, triangles, source, minimum_cut, maximum_cut, terrain, spacing, profile, minimum_slope, profile_node_mask=None, *, width=None, transverse_bottom_slope=0.02, center_lowest=False, continuous_center_lowest=False, component_supports=None, shared_sections=None):
    """Minimize unique cut volume without locking an unnecessary max envelope."""
    if minimum_cut.shape != (len(vertices),) or maximum_cut.shape != (len(vertices),) or (not _i27_np.all(_i27_np.isfinite(minimum_cut))) or (not _i27_np.all(_i27_np.isfinite(maximum_cut))) or _i27_np.any(minimum_cut < 0.0) or _i27_np.any(minimum_cut > maximum_cut + 1e-10):
        raise ValueError('finite ordered nonnegative cut bounds required for all vertices')
    constraints = bed_constraints(points, receiver, cells, vertices, triangles, source, terrain, spacing, profile, minimum_slope, profile_node_mask)
    if shared_sections:
        constraints.extend(shared_section_constraints(shared_sections, cells, vertices, triangles, source, terrain, spacing))
    if continuous_center_lowest:
        if width is None or not center_lowest:
            raise ValueError('continuous center-floor requires center-lowest width contract')
        floor = continuous_center_floor_constraints(points, receiver, width, cells, vertices, triangles, source, terrain, spacing, maximum_cut)
        constraints.extend(((ids, weights, limit, 'continuous_floor') for ids, weights, limit in zip(*floor)))
    transverse = (_i27_np.empty((0, 4), _i27_np.int64), _i27_np.empty((0, 4)), _i27_np.empty(0), 0)
    if width is not None:
        internal_ports = _i27_np.array([any((_i27_np.allclose(point, section['position_xz_m'], atol=1e-08, rtol=0) for section in shared_sections or [])) for point in points])
        transverse = transverse_bed_constraints(points, receiver, width, cells, vertices, triangles, source, terrain, spacing, maximum_cut, profile_node_mask, transverse_bottom_slope, center_lowest, internal_port_mask=internal_ports)
    active = _i27_np.unique(_i27_np.concatenate([_i27_np.concatenate([ids for ids, _, _, _ in constraints]), transverse[0].ravel()]))
    mapping = _i27_np.full(len(vertices), -1, _i27_np.int64)
    mapping[active] = _i27_np.arange(len(active))
    rr, cc, vv, limits = ([], [], [], [])
    for row, (ids, weights, limit, _) in enumerate(constraints):
        rr.extend([row] * len(ids))
        cc.extend(mapping[ids])
        vv.extend(weights)
        limits.append(limit)
    base_count, transverse_count = (len(constraints), len(transverse[2]))
    cap_count = transverse[3]
    rr = _i27_np.concatenate((_i27_np.asarray(rr, _i27_np.int64), _i27_np.repeat(_i27_np.arange(base_count, base_count + transverse_count), 4)))
    cc = _i27_np.concatenate((_i27_np.asarray(cc, _i27_np.int64), mapping[transverse[0]].ravel()))
    vv = _i27_np.concatenate((_i27_np.asarray(vv), transverse[1].ravel()))
    limits = _i27_np.concatenate((_i27_np.asarray(limits), transverse[2]))
    matrix = _i27_coo_matrix((vv, (rr, cc)), shape=(base_count + transverse_count, len(active))).tocsr()
    matrix.eliminate_zeros()
    del rr, cc, vv, transverse
    volume_weights = _vertex_volume_weights(vertices, triangles)
    bounds = _i27_np.column_stack((minimum_cut[active], maximum_cut[active]))
    if component_supports is None:
        roots = _i27_np.array([0])
        active_owner = _i27_np.zeros(len(active), _i27_np.int32)
        row_owner = _i27_np.zeros(len(limits), _i27_np.int32)
    else:
        roots, active_owner, row_owner = _design_support_groups(component_supports, len(vertices), active, matrix)
    solution = _i27_np.empty(len(active))
    reused_components, solved_groups = (0, 0)
    for group in _i27_np.unique(roots):
        columns = _i27_np.flatnonzero(active_owner == group)
        rows = _i27_np.flatnonzero(row_owner == group)
        block = matrix if len(_i27_np.unique(roots)) == 1 else matrix[rows][:, columns]
        block_limits = limits[rows]
        members = _i27_np.flatnonzero(roots == group)
        candidate = None
        if component_supports is not None and len(members) == 1 and (not center_lowest):
            bundle, mapping, same_mesh = component_supports[members[0]]
            if _saved_design_optimum(bundle, mapping, same_mesh, source, minimum_cut, maximum_cut, volume_weights, minimum_slope, transverse_bottom_slope):
                order = _i27_np.argsort(mapping)
                local_ids = order[_i27_np.searchsorted(mapping[order], active[columns])]
                trial = bundle['arrays']['cut_depth_m'][local_ids]
                if _i27_np.isfinite(trial).all() and _i27_np.all(trial >= bounds[columns, 0] - 1e-10) and _i27_np.all(trial <= bounds[columns, 1] + 1e-10) and (_i27_np.max(block @ trial - block_limits, initial=0.0) <= 1e-08):
                    candidate = trial
        if candidate is not None:
            solution[columns] = candidate
            reused_components += 1
            continue
        with _i27_warnings.catch_warnings():
            _i27_warnings.filterwarnings('ignore', message='Unrecognized options detected:.*threads.*parallel.*', category=_i27_OptimizeWarning)
            result = _i27_linprog(volume_weights[active[columns]], A_ub=block, b_ub=block_limits, bounds=bounds[columns], method='highs', options={'primal_feasibility_tolerance': 1e-08 if shared_sections else 1e-09, 'dual_feasibility_tolerance': 1e-09, 'threads': 1, 'parallel': False})
        solved_groups += 1
        if not result.success:
            raise ValueError('continuous design/profile physical bed exceeds configured cut bounds or is infeasible: ' + result.message)
        solution[columns] = result.x
    cut = minimum_cut.copy()
    cut[active] = solution
    residual = matrix @ solution - limits
    gradient_rows = _i27_np.concatenate((_i27_np.array([kind == 'gradient' for _, _, _, kind in constraints]), _i27_np.zeros(transverse_count, bool)))
    transverse_rows = _i27_np.arange(base_count + transverse_count) >= base_count
    profile_rows = ~(gradient_rows | transverse_rows)
    if _i27_np.max(residual[gradient_rows]) > 1e-08 or _i27_np.max(residual[~gradient_rows]) > 1e-08:
        raise ValueError('continuous design/profile closure residual exceeds tolerance')
    return (cut, dict(constraint_model='fan4-continuous-bed-v5-continuous-center-floor' if continuous_center_lowest else 'fan4-continuous-bed-v4-center-lowest' if center_lowest else DESIGN_BED_CONSTRAINT_MODEL, closure_policy='minimum unique volume with continuous design bottom, profile and actual transverse bed coupling', physical_triangle_plane_gradient=True, profile_mesh_breakpoint_union=True, minimum_volume_objective=True, support_group_count=int(len(_i27_np.unique(roots))), solved_support_groups=solved_groups, reused_optimal_components=reused_components, decomposition_policy='shared support vertices and complete global constraint rows; singleton optimum reused only with identical bounds and volume weights and feasible global rows', gradient_constraints=int(gradient_rows.sum()), profile_constraints=int(profile_rows.sum()), transverse_bed_coupling=width is not None, center_lowest=bool(center_lowest), continuous_center_lowest=bool(continuous_center_lowest), shared_section_constraints=sum((kind == 'shared_section' for _, _, _, kind in constraints)), internal_port_cap_policy='shared two-sided source-mesh sections omit physical endpoint cone; all strip and floor constraints retained', internal_port_node_indices=_i27_np.flatnonzero(internal_ports).tolist() if width is not None else [], continuous_center_floor_constraints=sum((kind == 'continuous_floor' for _, _, _, kind in constraints)), transverse_constraints=int(transverse_rows.sum()), transverse_node_cap_constraints=int(cap_count), transverse_bottom_slope_m_per_m=transverse_bottom_slope if width is not None else None, transverse_bank_ceiling_horizontal_per_vertical=2.0 if width is not None else None, active_solver_vertices=int(len(active)), solver_constraint_nonzeros=int(matrix.nnz), maximum_transverse_residual_m=float(_i27_np.max(residual[transverse_rows], initial=0.0)), maximum_gradient_residual_m_per_m=float(_i27_np.max(residual[gradient_rows])), maximum_profile_residual_m=float(_i27_np.max(residual[profile_rows], initial=0.0)), centerline_segments=int(gradient_rows.sum())))

def frozen_shared_sections(detail, specification, *, piece_indices=None, complete_adjacent_pieces=False):
    """Return identical section records to every piece sharing a subdivision node."""
    pieces = split_frozen_window_component(specification)
    sections = [[] for _ in pieces]
    occurrences = {}
    for index, piece in enumerate(pieces):
        for local, parent in enumerate(piece['parent_node_ids']):
            occurrences.setdefault(parent, []).append((index, local))
    for parent in sorted(occurrences):
        shared = occurrences[parent]
        if len(shared) < 2:
            continue
        if piece_indices is not None and (not any((index in piece_indices for index, _ in shared))):
            continue
        index, local = shared[0]
        piece = pieces[index]
        point = _i2_np.asarray(piece['points_xz_m'][local])
        receiver = _i2_np.asarray(piece['receiver'])
        neighbors = _i2_np.flatnonzero(receiver == local).tolist()
        if receiver[local] >= 0:
            neighbors.append(int(receiver[local]))
        vector = _i2_np.asarray(piece['points_xz_m'][neighbors[0]]) - point
        normal = _i2_np.array([-vector[1], vector[0]]) / _i2_np.linalg.norm(vector)
        if normal[0] < 0 or (normal[0] == 0 and normal[1] < 0):
            normal = -normal
        section = solved_shared_section(detail, specification, parent, normal, complete_adjacent_pieces=complete_adjacent_pieces)
        section['parent_node_id'] = int(parent)
        for index, _ in shared:
            sections[index].append(section)
    return sections

def solved_shared_section(detail, specification, node, normal, *, complete_adjacent_pieces=False):
    """Freeze a feasible trace from a deterministic bounded two-sided seam solve."""
    from terrain_pipeline.common_infra import TerrainGrid as _i2_TerrainGrid
    pass
    meta = detail['metadata']
    height = detail['arrays']['derived_height_m']
    terrain = _i2_TerrainGrid(height, _i2_np.ones(height.shape, bool), *meta['origin_xz_m'], meta['spacing_m'], meta['spacing_m'], 'conditioned_terrain', 'seam-local', meta['identity'])
    points = _i2_np.asarray(specification['points_xz_m'], float)
    receivers = _i2_np.asarray(specification['receiver'], int)
    upstream = _i2_np.flatnonzero(receivers == node)
    if len(upstream) != 1 or receivers[node] < 0:
        raise ValueError('bounded shared section requires one upstream and downstream edge')
    first, last = (int(upstream[0]), int(receivers[node]))
    edge_indices = {int(parent): index for index, parent in enumerate(_i2_np.flatnonzero(receivers >= 0))}
    frozen = specification['centerline_profile']
    local_points, local_width, local_bed = ([], [], [])
    profile = [[0], [], [], []]
    extents = []
    for ordinal, (a, b) in enumerate(((first, node), (node, last))):
        length = _i2_np.linalg.norm(points[b] - points[a])
        if complete_adjacent_pieces and (length <= 0 or length > 500.0 + 1e-08):
            raise ValueError('complete adjacent shared section requires each parent piece within 500m')
        extent = length if complete_adjacent_pieces else min(30.0, length)
        lo, hi = (1.0 - extent / length, 1.0) if ordinal == 0 else (0.0, extent / length)
        start, end = frozen['offsets'][edge_indices[a]:edge_indices[a] + 2]
        times = _i2_np.asarray(frozen['t'][start:end])
        samples = _i2_np.r_[lo, times[(times > lo) & (times < hi)], hi]
        coords = points[a] + samples[:, None] * (points[b] - points[a])
        beds = _i2_np.interp(samples, times, frozen['bed_m'][start:end])
        source, _ = _metric_channel_geometry_sample(height, coords, terrain)
        profile[1].extend(((samples - lo) / (hi - lo)).tolist())
        profile[2].extend(source.tolist())
        profile[3].extend(beds.tolist())
        profile[0].append(len(profile[1]))
        widths = _i2_np.interp([lo, hi], [0.0, 1.0], _i2_np.asarray(specification['width_m'])[[a, b]])
        if ordinal == 0:
            local_points.append(coords[0])
            local_width.append(widths[0])
            local_bed.append(beds[0])
        local_points.append(coords[-1])
        local_width.append(widths[-1])
        local_bed.append(beds[-1])
        extents.append(float(extent))
    local_points = _i2_np.asarray(local_points)
    local_bed = _i2_np.asarray(local_bed)
    parent_source, _ = _metric_channel_geometry_sample(height, points[[first, node, last]], terrain)
    parent_bed = _i2_np.asarray(specification['bed_target_m'])[[first, node, last]]
    inherited_depth = float(_i2_np.max(_i2_np.minimum(0.5, parent_source - parent_bed)))
    mesh = build_design_geometry(local_points, _i2_np.array([1, 2, -1]), _i2_np.asarray(local_width), _i2_np.full(3, inherited_depth), tuple((_i2_np.asarray(value) for value in profile)), terrain, 1.0, 4.0, 1e-05, center_lowest=True, continuous_center_lowest=True)
    cells, vertices, triangles, original, _, cut = mesh[:6]
    audit = _audit_mesh(cells, vertices, triangles, original, cut, local_points, _i2_np.array([1, 2, -1]), _i2_np.asarray(local_width), terrain, 1.0, center_lowest=True, continuous_center_lowest=True)
    if not audit['accepted']:
        raise ValueError('bounded shared-section source mesh failed independent geometry audit')
    half = specification['width_m'][node] / 2.0
    radius = half + _i2_np.sqrt(2.0) + 1.0 + 8.0
    ends = points[node] + _i2_np.array([-radius, radius])[:, None] * normal
    segments = _line_constraints(ends, _i2_np.array([1, -1]), cells, vertices, triangles, terrain, 1.0)
    values = []
    for start, end, _, _, _ in segments:
        for ids, weights in (start, end):
            values.append((float((weights @ vertices[ids] - points[node]) @ normal), float(weights @ original[ids]), float(weights @ (original - cut)[ids])))
    values.sort()
    unique = []
    for value in values:
        if not unique or value[0] - unique[-1][0] > 1e-08:
            unique.append(value)
    offsets, original_trace, bed = _i2_np.asarray(unique).T
    design_cap = float(specification['bed_target_m'][node])
    center = float(_i2_np.interp(0.0, offsets, bed))
    if center > design_cap + 1e-08:
        raise ValueError('bounded shared section exceeds frozen design ceiling')
    algorithm = 'bounded-complete-adjacent-feasible-fan4-section-v3' if complete_adjacent_pieces else 'bounded-two-sided-30m-feasible-fan4-section-v2'
    return {'algorithm': algorithm, 'parent_detail_identity': meta['identity'], 'fine_spacing_m': 1.0, 'position_xz_m': points[node].tolist(), 'normal_xz': _i2_np.asarray(normal).tolist(), 'half_width_m': float(half), 'center_bed_m': center, 'design_center_ceiling_m': design_cap, 'realized_center_below_design_ceiling_m': design_cap - center, 'radius_m': float(radius), 'offsets_m': offsets.tolist(), 'source_elevation_m': original_trace.tolist(), 'bed_elevation_m': bed.tolist(), 'maximum_cut_m': float(_i2_np.max(original_trace - bed)), 'longitudinal_support_m': extents, 'longitudinal_support_scope': 'two complete adjacent parent pieces, each at most 500m' if complete_adjacent_pieces else 'two independently clipped 30m parent portions', 'inherited_parent_bottom_design_depth_m': inherited_depth, 'minimum_cut_provenance': 'maximum endpoint design depth from both adjacent complete parent pieces, capped at 0.5m; original-source interpolation padding retained', 'source_mesh_geometry_audit': audit, 'local_solve_closure': mesh[6], 'local_mesh_witness': {'cells': cells.tolist(), 'vertices_xz_m': vertices.tolist(), 'triangles': triangles.tolist(), 'original_macro_bed_m': original.tolist(), 'local_cut_m': cut.tolist(), 'node_xz_m': local_points.tolist(), 'receiver': [1, 2, -1], 'width_m': list(map(float, local_width))}, 'trace_contract': 'actual independently audited local LP bed at every global fan4 triangle crossing'}

def frozen_window_profiles(plan, height_m, origin_xz_m, spacing_m, *, sample_spacing_m=1.0, clip_origin_xz_m=None, clip_shape=None, source_edges=None, frozen_paths=None):
    """Exact frozen-edge/window intersections and one shared terrain-following bed.

    Window boundaries are computational clips, never hydrological outlets.
    A profile is defined over this immutable source before any mesh subdivision.
    """
    from terrain_pipeline.common_infra import TerrainGrid as _i2_TerrainGrid
    if frozen_paths is not None:
        pass
        if source_edges is not None and {tuple(path['metadata']['source_edge']) for path in frozen_paths} != set(map(tuple, source_edges)):
            raise ValueError('frozen path set differs from requested source edges')
        return frozen_path_profiles(plan, frozen_paths, height_m, origin_xz_m, spacing_m, sample_spacing_m=sample_spacing_m, clip_origin_xz_m=clip_origin_xz_m, clip_shape=clip_shape)
    height = _i2_np.asarray(height_m, dtype=float)
    origin = _i2_np.asarray(origin_xz_m, dtype=float)
    maximum = origin + (_i2_np.array(height.shape)[::-1] - 1) * spacing_m
    terrain = _i2_TerrainGrid(height, _i2_np.ones(height.shape, bool), *origin, spacing_m, spacing_m, 'conditioned_terrain', 'frozen-window-profile', _i2_hashlib.sha256(height.tobytes()).hexdigest())
    if clip_origin_xz_m is not None:
        clip_origin = _i2_np.asarray(clip_origin_xz_m, dtype=float)
        clip_maximum = clip_origin + (_i2_np.array(clip_shape)[::-1] - 1) * spacing_m
        if _i2_np.any(clip_origin < origin) or _i2_np.any(clip_maximum > maximum):
            raise ValueError('declared frozen profile window leaves genuine source support')
        origin, maximum = (clip_origin, clip_maximum)
    columns = _i2_np.asarray(plan['height_m']).shape[1]
    receivers = _i2_np.asarray(plan['receiver']).ravel()
    river = _i2_np.asarray(plan.get('river_mask', _i2_np.zeros_like(plan['height_m'], bool))).ravel()
    profiles = []
    edges = [(int(first), int(receivers[first])) for first in _i2_np.flatnonzero(river & (receivers >= 0))] if source_edges is None else source_edges
    for first, second in edges:
        if not 0 <= first < receivers.size or not 0 <= second < receivers.size or receivers[first] != second:
            raise ValueError('profile line is not an actual frozen receiver edge')
        start = _i2_np.asarray(plan['origin_xz_m']) + _i2_np.array([first % columns, first // columns]) * plan['spacing_m']
        finish = _i2_np.asarray(plan['origin_xz_m']) + _i2_np.array([second % columns, second // columns]) * plan['spacing_m']
        vector = finish - start
        lo, hi = (0.0, 1.0)
        for axis in range(2):
            if vector[axis] == 0:
                if not origin[axis] <= start[axis] <= maximum[axis]:
                    hi = -1.0
                    break
            else:
                limits = sorted(((origin[axis] - start[axis]) / vector[axis], (maximum[axis] - start[axis]) / vector[axis]))
                lo, hi = (max(lo, limits[0]), min(hi, limits[1]))
        if hi <= lo:
            continue
        length = _i2_np.linalg.norm(vector) * (hi - lo)
        fractions = _i2_np.linspace(lo, hi, int(_i2_np.ceil(length / sample_spacing_m)) + 1)
        points = _i2_np.clip(start + fractions[:, None] * vector, origin, maximum)
        source, _ = _metric_channel_geometry_sample(height, points, terrain)
        distance = (fractions - lo) * _i2_np.linalg.norm(vector)
        bed = _i2_np.minimum.accumulate(source + 0.001 * distance) - 0.001 * distance - 0.5
        profiles.append({'source_edge': [int(first), second], 'fractions': fractions, 'points_xz_m': points, 'source_m': source, 'bed_m': bed, 'length_m': float(length), 'full_coarse_edge_length_m': float(_i2_np.linalg.norm(vector))})
    node_beds = {}
    for profile in profiles:
        for endpoint, fraction in ((0, 0), (-1, 1)):
            if profile['fractions'][endpoint] == fraction:
                node = profile['source_edge'][fraction]
                node_beds[node] = min(node_beds.get(node, _i2_np.inf), profile['bed_m'][endpoint])
    for profile in profiles:
        for endpoint, fraction in ((0, 0), (-1, 1)):
            if profile['fractions'][endpoint] == fraction:
                profile['bed_m'][endpoint] = node_beds[profile['source_edge'][fraction]]
    pending = list(range(len(profiles)))
    while pending:
        ready = [index for index in pending if not any((profiles[upstream]['source_edge'][1] == profiles[index]['source_edge'][0] and profiles[upstream]['fractions'][-1] == 1 and (profiles[index]['fractions'][0] == 0) for upstream in pending))]
        if not ready:
            raise ValueError('frozen window river profile contains a cycle')
        for index in ready:
            profile = profiles[index]
            upstream_profiles = [other for other in profiles if other['source_edge'][1] == profile['source_edge'][0] and other['fractions'][-1] == 1 and (profile['fractions'][0] == 0)]
            if upstream_profiles:
                shared_bed = min([profile['bed_m'][0]] + [other['bed_m'][-1] for other in upstream_profiles])
                for other in upstream_profiles:
                    other['bed_m'][-1] = shared_bed
                distance = (profile['fractions'] - profile['fractions'][0]) * profile['full_coarse_edge_length_m']
                profile['bed_m'] = _i2_np.minimum(profile['bed_m'], shared_bed - 0.001 * distance)
            pending.remove(index)
    return profiles

def select_frozen_window_component(plan, detail, window, *, width_m=8.0, maximum_segment_length_m=500.0, tributary_declaration=None, highest_lake_level_m=None, lake_mask=None, junction_length_m=120.0):
    """Request the entire represented window intersection of a selected edge.

    The profile is computed once before subdivisions, whose shared endpoints
    therefore have identical beds. Full coarse-edge coverage is reported.
    """
    from terrain_pipeline.common_infra import TerrainGrid as _i2_TerrainGrid
    if window['kind'] not in ('river', 'mouth', 'confluence') or not 4 <= width_m <= 64:
        raise ValueError('full-window selection requires a frozen river component, width 4..64m')
    if not 30 <= maximum_segment_length_m <= 1000:
        raise ValueError('bounded full-window segment length 30..1000m required')
    if window['kind'] == 'confluence':
        return _select_frozen_window_confluence(plan, detail, window, width_m=width_m, maximum_segment_length_m=maximum_segment_length_m, junction_length_m=junction_length_m, tributary_declaration=tributary_declaration, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    meta = detail['metadata']
    profiles = frozen_window_profiles(plan, detail['arrays']['derived_height_m'], meta['origin_xz_m'], meta['spacing_m'], clip_origin_xz_m=window.get('origin_xz_m'), clip_shape=window.get('shape'))
    edge = list(window['selection_edge_cell_ids'])
    profile = next((profile for profile in profiles if profile['source_edge'] == edge), None)
    if profile is None:
        raise ValueError('selected frozen edge does not intersect represented window')
    segment_count = int(_i2_np.ceil(profile['length_m'] / maximum_segment_length_m))
    if segment_count + 1 > 16:
        raise ValueError('full-window request exceeds bounded 16-node component')
    fractions = _i2_np.linspace(profile['fractions'][0], profile['fractions'][-1], segment_count + 1)
    points = _i2_np.column_stack([_i2_np.interp(fractions, profile['fractions'], profile['points_xz_m'][:, axis]) for axis in range(2)])
    target = _i2_np.interp(fractions, profile['fractions'], profile['bed_m'])
    offsets, parameters, sources, beds = ([0], [], [], [])
    height = detail['arrays']['derived_height_m']
    terrain = _i2_TerrainGrid(height, _i2_np.ones(height.shape, bool), *meta['origin_xz_m'], meta['spacing_m'], meta['spacing_m'], 'conditioned_terrain', 'full-window-component', meta['identity'])
    for lo, hi in zip(fractions[:-1], fractions[1:]):
        knots = _i2_np.r_[lo, profile['fractions'][(profile['fractions'] > lo) & (profile['fractions'] < hi)], hi]
        parameters.extend((knots - lo) / (hi - lo))
        sample_points = _i2_np.column_stack([_i2_np.interp(knots, profile['fractions'], profile['points_xz_m'][:, axis]) for axis in range(2)])
        sampled_source, _ = _metric_channel_geometry_sample(height, sample_points, terrain)
        sources.extend(sampled_source)
        beds.extend(_i2_np.interp(knots, profile['fractions'], profile['bed_m']))
        offsets.append(len(parameters))
    return {'points_xz_m': points.tolist(), 'receiver': list(range(1, segment_count + 1)) + [-1], 'width_m': [width_m] * len(points), 'bed_target_m': target.tolist(), 'fine_spacing_m': 1.0, 'node_source_edges': [edge] * len(points), 'node_edge_fractions': fractions.tolist(), 'centerline_profile': {'offsets': offsets, 't': list(parameters), 'source_m': list(sources), 'bed_m': list(beds), 'parent_detail_identity': meta['identity']}, 'selection_semantics': 'exact complete frozen-edge/window intersection; shared terrain-following profile before mesh subdivision', 'coverage': {'scope': 'entire represented window intersection, not entire frozen coarse edge', 'profile_semantics': 'local_clipped_component; shared frozen profile within this declared window only', 'represented_length_m': profile['length_m'], 'full_coarse_edge_length_m': profile['full_coarse_edge_length_m'], 'edge_fraction_interval': fractions[[0, -1]].tolist(), 'entire_coarse_edge_covered': bool(fractions[0] == 0 and fractions[-1] == 1), 'boundary_policy': 'computational clip; finite-width mesh may require genuine source halo'}}

def _select_frozen_window_confluence(plan, detail, window, *, width_m, maximum_segment_length_m, junction_length_m, tributary_declaration, highest_lake_level_m, lake_mask):
    from terrain_pipeline.common_infra import TerrainGrid as _i2_TerrainGrid
    if tributary_declaration is None or not 30 <= junction_length_m <= min(500, maximum_segment_length_m):
        raise ValueError('full-window confluence needs an explicit sidecar and bounded shared junction arms')
    from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_source_edges
    source_edges = [record['source_edge'] for record in tributary_declaration['edges']]
    validation = validate_local_tributary_source_edges(plan, tributary_declaration, source_edges, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    junction = tributary_declaration['junction_id']
    if window['coarse_cell'] != junction or window.get('declared_source_edge_cell_ids') != source_edges:
        raise ValueError('full-window confluence differs from its frozen three-edge declaration')
    meta, height = (detail['metadata'], detail['arrays']['derived_height_m'])
    profiles = frozen_window_profiles(plan, height, meta['origin_xz_m'], meta['spacing_m'], clip_origin_xz_m=window.get('origin_xz_m'), clip_shape=window.get('shape'), source_edges=source_edges)
    by_edge = {tuple(profile['source_edge']): profile for profile in profiles}
    if len(by_edge) != 3:
        raise ValueError('full-window source does not represent all three declared confluence edges')
    outgoing = by_edge[tuple(source_edges[2])]
    if outgoing['fractions'][0] != 0:
        raise ValueError('declared confluence junction is outside its full-window source')
    points = [outgoing['points_xz_m'][0]]
    targets = [outgoing['bed_m'][0]]
    edges, fractions, receivers = ([source_edges[2]], [0.0], [-1])
    segment_profiles = {}
    coverage = []
    for edge in source_edges:
        profile = by_edge[tuple(edge)]
        incoming = edge[1] == junction
        lo, hi = profile['fractions'][[0, -1]]
        if incoming and hi != 1:
            raise ValueError('incoming sidecar branch does not reach the shared junction')
        count = int(_i2_np.ceil(profile['length_m'] / maximum_segment_length_m))
        cut = 1 - junction_length_m / profile['full_coarse_edge_length_m'] if incoming else junction_length_m / profile['full_coarse_edge_length_m']
        knots = _i2_np.unique(_i2_np.r_[_i2_np.linspace(lo, hi, count + 1), _i2_np.clip(cut, lo, hi)])
        ids = []
        for fraction in knots:
            if incoming and fraction == 1 or (not incoming and fraction == 0):
                ids.append(0)
                continue
            ids.append(len(points))
            points.append(_i2_np.array([_i2_np.interp(fraction, profile['fractions'], profile['points_xz_m'][:, axis]) for axis in range(2)]))
            targets.append(float(_i2_np.interp(fraction, profile['fractions'], profile['bed_m'])))
            edges.append(edge)
            fractions.append(float(fraction))
            receivers.append(-1)
        for index, (first, second) in enumerate(zip(ids[:-1], ids[1:])):
            receivers[first] = second
            segment_profiles[first] = (profile, knots[index], knots[index + 1])
        coverage.append({'source_edge': edge, 'edge_fraction_interval': [float(lo), float(hi)], 'represented_length_m': profile['length_m'], 'full_coarse_edge_length_m': profile['full_coarse_edge_length_m'], 'entire_coarse_edge_covered': bool(lo == 0 and hi == 1)})
    if len(points) > 16:
        raise ValueError('full-window confluence exceeds bounded 16-node component')
    terrain = _i2_TerrainGrid(height, _i2_np.ones(height.shape, bool), *meta['origin_xz_m'], meta['spacing_m'], meta['spacing_m'], 'conditioned_terrain', 'full-window-confluence', meta['identity'])
    offsets, parameters, sources, beds = ([0], [], [], [])
    for node in _i2_np.flatnonzero(_i2_np.asarray(receivers) >= 0):
        profile, lo, hi = segment_profiles[int(node)]
        knots = _i2_np.r_[lo, profile['fractions'][(profile['fractions'] > lo) & (profile['fractions'] < hi)], hi]
        parameters.extend((knots - lo) / (hi - lo))
        sample_points = _i2_np.column_stack([_i2_np.interp(knots, profile['fractions'], profile['points_xz_m'][:, axis]) for axis in range(2)])
        source, _ = _metric_channel_geometry_sample(height, sample_points, terrain)
        sources.extend(source)
        beds.extend(_i2_np.interp(knots, profile['fractions'], profile['bed_m']))
        offsets.append(len(parameters))
    return {'points_xz_m': _i2_np.asarray(points).tolist(), 'receiver': receivers, 'width_m': [width_m] * len(points), 'bed_target_m': targets, 'node_source_edges': edges, 'node_edge_fractions': fractions, 'fine_spacing_m': 1.0, 'centerline_profile': {'offsets': offsets, 't': list(parameters), 'source_m': list(sources), 'bed_m': list(beds), 'parent_detail_identity': meta['identity']}, 'junction_node_index': 0, 'junction_length_m': junction_length_m, 'local_tributary_sidecar_validation': validation, 'selection_semantics': 'complete declared two-in/one-out receiver graph/window intersections; one shared junction bed before subdivision', 'coverage': {'scope': 'all three local tributary edge/window intersections; not entire coarse edges', 'profile_semantics': 'local_clipped_component; shared three-edge DAG profile within declared source', 'source_edges': coverage, 'represented_length_m': sum((record['represented_length_m'] for record in coverage)), 'entire_coarse_edge_covered': all((record['entire_coarse_edge_covered'] for record in coverage)), 'boundary_policy': 'computational clips; genuine source halo required for finite-width support'}}

def select_frozen_component(plan, detail, window, *, length_m=120.0, width_m=8.0, tributary_declaration=None, highest_lake_level_m=None, lake_mask=None):
    """Prepare an inspectable finite piece of actual frozen river edges.

    This selects coordinates and fixed bed targets only. The continuous solver
    and independent represented-bed audit still decide success or refusal.
    """
    from terrain_pipeline.common_infra import TerrainGrid as _i2_TerrainGrid
    if window['kind'] not in ('river', 'confluence', 'mouth'):
        raise ValueError('fine component selection supports ordinary, confluence and mouth reaches')
    if not 30 <= length_m <= 500 or not 4 <= width_m <= 64:
        raise ValueError('finite selection length 30..500m and width 4..64m required')
    columns = plan['height_m'].shape[1]
    frozen_receiver = plan['receiver'].ravel()
    river = plan['river_mask'].ravel()
    if tributary_declaration is not None:
        from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_source_edges
        sidecar_edges = [record['source_edge'] for record in tributary_declaration['edges']]
        validate_local_tributary_source_edges(plan, tributary_declaration, sidecar_edges, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
        river = river.copy()
        river[_i2_np.asarray(sidecar_edges)[:, 0]] = True
    owner = plan['owner_domain_id'].ravel()
    coarse_origin = _i2_np.asarray(plan['origin_xz_m'])
    coarse_spacing = plan['spacing_m']

    def point(edge, fraction):
        first, second = edge
        start = coarse_origin + _i2_np.array([first % columns, first // columns]) * coarse_spacing
        finish = coarse_origin + _i2_np.array([second % columns, second // columns]) * coarse_spacing
        return start + fraction * (finish - start)
    points, edges, fractions, receivers = ([], [], [], [])
    if window['kind'] == 'confluence':
        junction = window['coarse_cell']
        downstream = int(frozen_receiver[junction])
        incoming = _i2_np.flatnonzero(river & (frozen_receiver == junction) & (owner == owner[junction]))
        if len(incoming) < 2 or downstream < 0:
            raise ValueError('selected confluence lacks two genuine incoming and one outgoing frozen edges')
        out_edge = [junction, downstream]
        points.append(point(out_edge, 0.0))
        edges.append(out_edge)
        fractions.append(0.0)
        receivers.append(1)
        fraction = min(1.0, length_m / _i2_np.linalg.norm(point(out_edge, 1) - point(out_edge, 0)))
        points.append(point(out_edge, fraction))
        edges.append(out_edge)
        fractions.append(fraction)
        receivers.append(-1)
        for upstream in incoming[:3]:
            edge = [int(upstream), junction]
            fraction = max(0.0, 1 - length_m / _i2_np.linalg.norm(point(edge, 1) - point(edge, 0)))
            points.append(point(edge, fraction))
            edges.append(edge)
            fractions.append(fraction)
            receivers.append(0)
    else:
        edge = window['selection_edge_cell_ids']
        vector_length = _i2_np.linalg.norm(point(edge, 1) - point(edge, 0))
        if window['kind'] == 'mouth':
            heights = plan['height_m'].ravel()[edge]
            middle = float(-heights[0] / (heights[1] - heights[0]))
        else:
            middle = 0.5
        half = length_m / (2 * vector_length)
        for fraction in (max(0.0, middle - half), min(1.0, middle + half)):
            points.append(point(edge, fraction))
            edges.append(edge)
            fractions.append(fraction)
        receivers = [1, -1]
    points = _i2_np.asarray(points)
    metadata = detail['metadata']
    terrain = _i2_TerrainGrid(detail['arrays']['derived_height_m'], _i2_np.ones(detail['arrays']['derived_height_m'].shape, bool), *metadata['origin_xz_m'], metadata['spacing_m'], metadata['spacing_m'], 'conditioned_terrain', 'component-request', metadata['identity'])
    source, _ = _metric_channel_geometry_sample(terrain.elevation_m, points, terrain)
    target = source - 0.5
    pending = set(range(len(points)))
    while pending:
        ready = [node for node in pending if not any((receivers[upstream] == node for upstream in pending))]
        if not ready:
            raise ValueError('selected finite river component contains a cycle')
        for node in ready:
            downstream = receivers[node]
            if downstream >= 0:
                length = _i2_np.linalg.norm(points[downstream] - points[node])
                target[downstream] = min(target[downstream], target[node] - 0.001 * length)
            pending.remove(node)
    return {'points_xz_m': points.tolist(), 'receiver': receivers, 'width_m': [width_m] * len(points), 'bed_target_m': target.tolist(), 'fine_spacing_m': 1.0, 'node_source_edges': edges, 'node_edge_fractions': fractions, 'selection_semantics': 'exact frozen graph clipping; 0.5m initial depth and globally declared 0.001 downhill grade; no hydraulic certification'}

def split_frozen_window_component(specification):
    """Bound solver memory by reusing, rather than resetting, the full profile."""
    profile = specification['centerline_profile']
    receivers = _i2_np.asarray(specification['receiver'])
    edge_nodes = _i2_np.flatnonzero(receivers >= 0).tolist()
    edge_index = {node: index for index, node in enumerate(edge_nodes)}
    groups = []
    junction = specification.get('junction_node_index')
    if junction is not None:
        central = [node for node in edge_nodes if node == junction or receivers[node] == junction]
        if len(central) != 3:
            raise ValueError('shared confluence component needs the complete two-in/one-out junction')
        groups.append(central)
    groups.extend([[node] for node in edge_nodes if not groups or node not in groups[0]])
    if specification.get('joint_component_solve', False):
        indegree = _i2_np.bincount(receivers[receivers >= 0], minlength=len(receivers))
        retained = [node for node in range(len(receivers)) if indegree[node] != 1 or receivers[node] < 0]
        remap = {node: index for index, node in enumerate(retained)}
        piece = {key: [specification[key][node] for node in retained] for key in ('points_xz_m', 'width_m', 'bed_target_m', 'node_source_edges', 'node_edge_fractions')}
        joint_profile = {'offsets': [0], 'parent_detail_identity': profile['parent_detail_identity'], 't': [], 'source_m': [], 'bed_m': []}
        joint_receiver = []
        positions = _i2_np.asarray(specification['points_xz_m'])
        for node in retained:
            if receivers[node] < 0:
                joint_receiver.append(-1)
                continue
            chain, current = ([], node)
            while True:
                chain.append(current)
                current = int(receivers[current])
                if current in remap:
                    break
            vector = positions[current] - positions[node]
            length = _i2_np.linalg.norm(vector)
            for ordinal, first in enumerate(chain):
                second = int(receivers[first])
                lo, hi = profile['offsets'][edge_index[first]:edge_index[first] + 2]
                local_t = _i2_np.asarray(profile['t'][lo:hi])
                coords = positions[first] + local_t[:, None] * (positions[second] - positions[first])
                offsets = coords - positions[node]
                transverse = (vector[0] * offsets[:, 1] - vector[1] * offsets[:, 0]) / length
                if _i2_np.max(_i2_np.abs(transverse)) > 1e-07:
                    raise ValueError('joint bounded component requires collinear subdivisions per arm')
                use = slice(1, None) if ordinal else slice(None)
                mapped = _i2_np.clip((coords - positions[node]) @ vector / length ** 2, 0.0, 1.0)
                if ordinal == 0:
                    mapped[0] = 0.0
                if ordinal == len(chain) - 1:
                    mapped[-1] = 1.0
                joint_profile['t'].extend(mapped[use].tolist())
                for key in ('source_m', 'bed_m'):
                    joint_profile[key].extend(profile[key][lo:hi][use])
            joint_profile['offsets'].append(len(joint_profile['t']))
            joint_receiver.append(remap[current])
        filtered = {'offsets': [0], 'parent_detail_identity': profile['parent_detail_identity'], 't': [], 'source_m': [], 'bed_m': []}
        for lo, hi in zip(joint_profile['offsets'][:-1], joint_profile['offsets'][1:]):
            values = _i2_np.asarray(joint_profile['t'][lo:hi])
            keep = _i2_np.r_[True, _i2_np.diff(values) > 1e-12]
            for key in ('t', 'source_m', 'bed_m'):
                filtered[key].extend(_i2_np.asarray(joint_profile[key][lo:hi])[keep].tolist())
            filtered['offsets'].append(len(filtered['t']))
        joint_profile = filtered
        piece.update(receiver=joint_receiver, parent_node_ids=retained, junction_piece=True, joint_component=True, fine_spacing_m=specification['fine_spacing_m'], centerline_profile=joint_profile, coverage={**specification['coverage'], 'scope': 'joint solve of complete declared clipped three-arm component'})
        return [piece]
    pieces = []
    for group in groups:
        nodes = sorted(set(group + [int(receivers[node]) for node in group]))
        node_index = {node: index for index, node in enumerate(nodes)}
        piece = {key: [specification[key][node] for node in nodes] for key in ('points_xz_m', 'width_m', 'bed_target_m', 'node_source_edges', 'node_edge_fractions')}
        clipped_profile = {'offsets': [0], 'parent_detail_identity': profile['parent_detail_identity'], 't': [], 'source_m': [], 'bed_m': []}
        for node in nodes:
            if node not in group:
                continue
            lo, hi = profile['offsets'][edge_index[node]:edge_index[node] + 2]
            for key in ('t', 'source_m', 'bed_m'):
                clipped_profile[key].extend(profile[key][lo:hi])
            clipped_profile['offsets'].append(len(clipped_profile['t']))
        piece.update({'receiver': [node_index[int(receivers[node])] if node in group else -1 for node in nodes], 'parent_node_ids': nodes, 'junction_piece': junction is not None and junction in group, 'fine_spacing_m': specification['fine_spacing_m'], 'centerline_profile': clipped_profile, 'coverage': {**specification['coverage'], 'piece_index': len(pieces), 'scope': 'one subdivision of shared declared full-window component'}})
        pieces.append(piece)
    return pieces

def represented_section_offsets(result, position, normal, radius):
    """All affine trace breakpoints of one saved mesh on a physical section."""
    from types import SimpleNamespace
    pass
    arrays = result['arrays']
    terrain = SimpleNamespace(x0_m=result['mesh_origin_xz_m'][0], z0_m=result['mesh_origin_xz_m'][1])
    ends = position + _i2_np.array([-radius, radius])[:, None] * normal
    records = _line_constraints(ends, _i2_np.array([1, -1]), arrays['cells'], arrays['vertices_xz_m'], arrays['triangles'], terrain, result['fine_spacing_m'])
    return [float((weights @ arrays['vertices_xz_m'][ids] - position) @ normal) for start, end, _, _, _ in records for ids, weights in (start, end)]

def audit_frozen_window_seams(results, specification, *, center_lowest=False):
    """Cold-check both represented finite beds at every shared full-width seam."""
    pieces = split_frozen_window_component(specification)
    if len(results) != len(pieces) or any((not result.get('arrays') for result in results)):
        return {'accepted': False, 'reason': 'full_window_mesh_coverage_incomplete'}
    maximum = 0.0
    transverse_residual = 0.0
    center_minimum_residual = 0.0
    center_lowest = bool(center_lowest or any((result.get('center_lowest', False) for result in results)))
    count = 0
    lookups = [{tuple(cell): index for index, cell in enumerate(result['arrays']['cells'])} for result in results]

    def sample(result_index, point):
        result = results[result_index]
        arrays = result['arrays']
        cells, vertices, triangles = (arrays['cells'], arrays['vertices_xz_m'], arrays['triangles'])
        origin = _i2_np.asarray(result['mesh_origin_xz_m'])
        key = tuple(_i2_np.floor((point - origin) / result['fine_spacing_m']).astype(int))
        lookup = lookups[result_index]
        if key not in lookup:
            raise ValueError('full-width seam leaves represented finite mesh')
        return _mesh_height(point, lookup[key], vertices, triangles, arrays['bed_elevation_m'])
    try:
        occurrences = {}
        for index, (result, piece) in enumerate(zip(results, pieces)):
            if not _i2_np.allclose(result['arrays']['node_xz_m'], piece['points_xz_m'], atol=1e-08, rtol=0) or not _i2_np.allclose(result['arrays']['node_bed_target_m'], piece['bed_target_m'], atol=1e-08, rtol=0) or (not _i2_np.array_equal(result['arrays']['receiver'], piece['receiver'])):
                return {'accepted': False, 'reason': 'full_window_piece_does_not_match_shared_profile'}
            for local_node, parent_node in enumerate(piece['parent_node_ids']):
                occurrences.setdefault(parent_node, []).append((index, local_node))
        for shared in occurrences.values():
            if len(shared) < 2:
                continue
            first_piece, local_node = shared[0]
            piece = pieces[first_piece]
            position = _i2_np.asarray(piece['points_xz_m'][local_node])
            local_receivers = _i2_np.asarray(piece['receiver'])
            neighbors = _i2_np.flatnonzero(local_receivers == local_node).tolist()
            if local_receivers[local_node] >= 0:
                neighbors.append(int(local_receivers[local_node]))
            direction = _i2_np.asarray(piece['points_xz_m'][neighbors[0]]) - position
            normal = _i2_np.array([-direction[1], direction[0]]) / _i2_np.linalg.norm(direction)
            for other_piece, _ in shared[1:]:
                center_heights = [sample(first_piece, position), sample(other_piece, position)]
                half = piece['width_m'][local_node] / 2
                first_sections = results[first_piece].get('shared_sections') or []
                other_sections = results[other_piece].get('shared_sections') or []
                section = next((item for item in first_sections if _i2_np.allclose(item['position_xz_m'], position, atol=1e-08, rtol=0)), None)
                radius = half + (_i2_np.sqrt(2.0) + 1.0) * max(results[first_piece]['fine_spacing_m'], results[other_piece]['fine_spacing_m']) + 8.0
                offsets = [0.0, -half, half, -radius, radius]
                if section is not None:
                    other = next((item for item in other_sections if item.get('parent_node_id') == section.get('parent_node_id')), None)
                    if other != section:
                        return {'accepted': False, 'reason': 'shared_cross_section_contracts_differ'}
                    normal = _i2_np.asarray(section['normal_xz'])
                    radius = section['radius_m']
                    offsets.extend(section['offsets_m'])
                offsets = _i2_np.unique(_i2_np.r_[offsets, represented_section_offsets(results[first_piece], position, normal, radius), represented_section_offsets(results[other_piece], position, normal, radius)])
                for offset in offsets:
                    point = position + offset * normal
                    heights = [sample(first_piece, point), sample(other_piece, point)]
                    maximum = max(maximum, abs(heights[0] - heights[1]))
                    if section is not None:
                        target = _i2_np.interp(offset, section['offsets_m'], section['bed_elevation_m'])
                        maximum = max(maximum, max((abs(height - target) for height in heights)))
                    if abs(offset) <= half + 1e-08:
                        transverse_residual = max(transverse_residual, max((height - center - abs(offset) * 0.02 for height, center in zip(heights, center_heights))))
                    center_minimum_residual = max(center_minimum_residual, max((center - height for height, center in zip(heights, center_heights))))
                    count += 1
    except ValueError as error:
        return {'accepted': False, 'reason': str(error)}
    return {'accepted': bool(maximum <= 1e-06 and transverse_residual <= 1e-06 and (not center_lowest or center_minimum_residual <= 1e-06)), 'maximum_shared_full_width_bed_difference_m': float(maximum), 'maximum_full_width_seam_transverse_residual_m': float(transverse_residual), 'center_lowest_required': center_lowest, 'center_minimum_max_residual_m': float(center_minimum_residual), 'junction_component_count': sum((piece['junction_piece'] for piece in pieces)), 'full_width_seam_samples': count, 'piece_count': len(pieces), 'continuous_affine_trace_verified': bool(maximum <= 1e-06), 'trace_breakpoints': 'union of all triangle crossings in both represented meshes, complete bottom and bank support', 'scope': 'complete declared clipped component; both finite represented beds at every seam'}

def _audit_mesh(cells, vertices, triangles, source, cut, points, receiver, widths, terrain, spacing, *, center_lowest=False, continuous_center_lowest=False):
    """Independently sample represented bed, not just solver feasibility flags."""
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    bed = source - cut
    pass
    gradient_rows = bed_constraints(points, receiver, cells, vertices, triangles, source, terrain, spacing, (_i2_np.zeros(_i2_np.count_nonzero(receiver >= 0) + 1, int), [], [], []), 1e-05, profile_node_mask=_i2_np.zeros(len(receiver), bool))
    gradient_residual = max((float(weights @ cut[ids] - limit) for ids, weights, limit, _ in gradient_rows), default=0.0)
    longitudinal_residual = 0.0
    transverse_residual = 0.0
    samples = 0
    center_minimum_residual = 0.0
    unreconnected_banks = 0
    internal_junction_sections = 0
    bank_sections = 0
    minimum_reconnected_bank_rise = _i2_np.inf

    def sample(point, values=bed):
        key = tuple(_i2_np.floor((point - [terrain.x0_m, terrain.z0_m]) / spacing).astype(int))
        if key not in lookup:
            raise ValueError('independent represented bed sample outside finite mesh support')
        return _mesh_height(point, lookup[key], vertices, triangles, values)

    def belongs_to_strip(point, distance):
        for first in _i2_np.flatnonzero(receiver >= 0):
            vector = points[receiver[first]] - points[first]
            t = _i2_np.clip((point - points[first]) @ vector / (vector @ vector), 0, 1)
            if _i2_np.linalg.norm(point - points[first] - t * vector) < distance - 1e-08:
                return False
        return True
    for node in _i2_np.flatnonzero(receiver >= 0):
        other = receiver[node]
        vector = points[other] - points[node]
        length = _i2_np.linalg.norm(vector)
        direction = vector / length
        normal = _i2_np.array([-direction[1], direction[0]])
        parameters = _i2_np.linspace(0.0, 1.0, max(3, int(_i2_np.ceil(length / spacing)) + 1))
        center = _i2_np.array([sample(points[node] + value * vector) for value in parameters])
        slope_residual = _i2_np.diff(center) + _i2_np.diff(parameters) * length * 1e-05
        longitudinal_residual = max(longitudinal_residual, float(slope_residual.max(initial=0.0)))
        for value, center_height in zip(parameters[1:-1], center[1:-1]):
            width = widths[node] * (1 - value) + widths[other] * value
            position = points[node] + value * vector
            for offset in _i2_np.linspace(-width / 2, width / 2, 9):
                actual = sample(position + offset * normal)
                transverse_residual = max(transverse_residual, actual - center_height - abs(offset) * 0.02)
                if center_lowest and belongs_to_strip(position + offset * normal, abs(offset)):
                    center_minimum_residual = max(center_minimum_residual, center_height - actual)
                samples += 1
            if center_lowest:
                radius = width / 2 + (_i2_np.sqrt(2) + 1.0) * spacing + 8.0
                for side in (-1, 1):
                    distances = _i2_np.linspace(width / 2, radius, int(_i2_np.ceil((radius - width / 2) / spacing)) + 1)
                    cuts, rises = ([], [])
                    crossed_other_arm = False
                    for distance in distances:
                        point = position + side * distance * normal
                        if not belongs_to_strip(point, distance):
                            crossed_other_arm = True
                            continue
                        actual = sample(point)
                        source_height = sample(point, source)
                        center_minimum_residual = max(center_minimum_residual, center_height - actual)
                        cuts.append(source_height - actual)
                        rises.append(actual - center_height)
                    if not cuts:
                        continue
                    if continuous_center_lowest and _i2_np.count_nonzero(receiver >= 0) > 1 and crossed_other_arm:
                        internal_junction_sections += 1
                        continue
                    bank_sections += 1
                    returned = _i2_np.asarray(cuts) <= 1e-08
                    if not returned.any():
                        unreconnected_banks += 1
                    else:
                        minimum_reconnected_bank_rise = min(minimum_reconnected_bank_rise, float(_i2_np.asarray(rises)[returned].max()))
    exact_floor_residual = None
    exact_floor_count = 0
    union_boundary_count = 0
    union_boundary_cut = None
    unknown_union_boundary = False
    if continuous_center_lowest:
        ids, coefficients, _ = continuous_center_floor_constraints(points, receiver, widths, cells, vertices, triangles, source, terrain, spacing, _i2_np.full(len(source), 4.0))
        exact_floor_residual = float(_i2_np.max(-_i2_np.sum(coefficients * bed[ids], axis=1), initial=0.0))
        exact_floor_count = len(ids)
        if _i2_np.count_nonzero(receiver >= 0) > 1:
            boundary = interior_support_boundary_vertices(cells, vertices, terrain, spacing)
            union_boundary_count = len(boundary)
            union_boundary_cut = float(_i2_np.max(_i2_np.abs(cut[boundary]), initial=0.0))
            origin = _i2_np.array([terrain.x0_m, terrain.z0_m])
            maximum = origin + _i2_np.array([terrain.elevation_m.shape[1] - 1, terrain.elevation_m.shape[0] - 1]) * _i2_np.array([terrain.dx_m, terrain.dz_m])
            unknown_union_boundary = bool(_i2_np.any(vertices <= origin + 1e-08) or _i2_np.any(vertices >= maximum - 1e-08))
    accepted = _i2_np.isfinite(bed).all() and cut.min(initial=0.0) >= -1e-08 and (cut.max(initial=0.0) <= 4.0 + 1e-08) and (longitudinal_residual <= 1e-06) and (gradient_residual <= 1e-08) and (transverse_residual <= 1e-06) and (not center_lowest or (center_minimum_residual <= 1e-06 and (not unreconnected_banks) and (minimum_reconnected_bank_rise >= -1e-06))) and (exact_floor_residual is None or exact_floor_residual <= 1e-06) and (not unknown_union_boundary) and (union_boundary_cut is None or union_boundary_cut <= 1e-08)
    return {'accepted': bool(accepted), 'longitudinal_max_residual_m': longitudinal_residual, 'physical_triangle_gradient_max_residual_m_per_m': float(gradient_residual), 'physical_triangle_gradient_constraint_count': len(gradient_rows), 'continuous_longitudinal_gradient_verified': bool(gradient_residual <= 1e-08), 'continuous_longitudinal_gradient_scope': 'all triangle planes crossed by the represented centerline paths; downstream directional slope on those crossings, not all mesh faces or arbitrary off-centerline points', 'transverse_max_residual_m': float(transverse_residual), 'transverse_sample_count': samples, 'maximum_cut_m': float(cut.max(initial=0.0)), 'minimum_cut_m': float(cut.min(initial=0.0)), 'center_lowest_required': bool(center_lowest), 'bank_support_radius_policy': 'half width plus (sqrt(2)+1) fine spacing plus 8m; same represented support as design builder', 'continuous_center_floor_max_residual_m': exact_floor_residual, 'continuous_center_floor_polygon_vertex_count': exact_floor_count, 'continuous_center_floor_scope': 'all represented triangle/projection partition vertices; shared-junction nearest-ray polygons include conservative distant-end supersets' if continuous_center_lowest else None, 'internal_junction_bank_sections': internal_junction_sections, 'union_exterior_boundary_vertex_count': union_boundary_count, 'union_exterior_boundary_maximum_cut_m': union_boundary_cut, 'union_exterior_touches_unknown_source_boundary': unknown_union_boundary, 'center_minimum_max_residual_m': float(center_minimum_residual), 'unreconnected_bank_sections': unreconnected_banks, 'bank_section_count': bank_sections, 'minimum_reconnected_bank_rise_m': None if not _i2_np.isfinite(minimum_reconnected_bank_rise) else float(minimum_reconnected_bank_rise), 'scope': 'represented finite fan4 mesh; samples every fine spacing and nine bottom offsets'}

def audit_saved_continuous_bed(result, detail, *, center_lowest=True, continuous_center_lowest=None, centerline_profile=None, frozen_path=None, frozen_plan=None):
    """Reassess saved geometry against the explicit actual-channel contract."""
    from terrain_pipeline.common_infra import TerrainGrid as _i2_TerrainGrid
    arrays, meta = (result['arrays'], detail['metadata'])
    if result['parent_detail_identity'] != meta['identity']:
        raise ValueError('saved continuous bed source parent identity mismatch')
    height = detail['arrays']['derived_height_m']
    terrain = _i2_TerrainGrid(height, _i2_np.ones(height.shape, bool), *meta['origin_xz_m'], meta['spacing_m'], meta['spacing_m'], 'conditioned_terrain', 'saved-bed-assessment', meta['identity'])
    try:
        if result.get('frozen_path_identity') is not None:
            pass
            if frozen_path is None or frozen_plan is None or result['frozen_path_identity'] != frozen_path['identity']:
                raise ValueError('saved path bed requires its complete frozen path and plan')
            validate_frozen_path_nodes(frozen_path, frozen_plan, arrays['node_xz_m'], arrays['node_source_edges'], arrays['node_edge_fractions'], arrays['receiver'])
        sampled_source, _ = _metric_channel_geometry_sample(height, arrays['vertices_xz_m'], terrain)
        if not _i2_np.allclose(sampled_source, arrays['original_macro_bed_m'], rtol=0, atol=1e-08):
            raise ValueError('saved original macro bed differs from immutable detail at mesh vertices')
        for section in result.get('shared_sections') or []:
            if section['algorithm'] in ('bounded-two-sided-30m-feasible-fan4-section-v1', 'bounded-two-sided-30m-feasible-fan4-section-v2', 'bounded-complete-adjacent-feasible-fan4-section-v3'):
                witness = {key: _i2_np.asarray(value) for key, value in section['local_mesh_witness'].items()}
                sampled, _ = _metric_channel_geometry_sample(height, witness['vertices_xz_m'], terrain)
                if not _i2_np.allclose(sampled, witness['original_macro_bed_m'], atol=1e-08, rtol=0):
                    raise ValueError('shared-section local witness differs from immutable source')
                witness_audit = _audit_mesh(witness['cells'], witness['vertices_xz_m'], witness['triangles'], witness['original_macro_bed_m'], witness['local_cut_m'], witness['node_xz_m'], witness['receiver'], witness['width_m'], terrain, result['fine_spacing_m'], center_lowest=True, continuous_center_lowest=True)
                pass
                rows = shared_section_constraints([section], witness['cells'], witness['vertices_xz_m'], witness['triangles'], sampled, terrain, result['fine_spacing_m'])
                if not witness_audit['accepted'] or max((float(weights @ witness['local_cut_m'][ids] - limit) for ids, weights, limit, _ in rows)) > 1e-08:
                    raise ValueError('shared-section local source mesh witness rejected')
                if abs(_i2_np.interp(0.0, section['offsets_m'], section['bed_elevation_m']) - section['center_bed_m']) > 1e-08:
                    raise ValueError('shared-section center differs from explicit frozen target')
                continue
            raise ValueError('unsupported shared-section algorithm; source mesh witness required')
        audit = _audit_mesh(arrays['cells'], arrays['vertices_xz_m'], arrays['triangles'], arrays['original_macro_bed_m'], arrays['local_cut_m'], arrays['node_xz_m'], arrays['receiver'], arrays['width_m'], terrain, result['fine_spacing_m'], center_lowest=center_lowest, continuous_center_lowest=result.get('continuous_center_lowest', False) if continuous_center_lowest is None else continuous_center_lowest)
        audit['immutable_source_at_vertices_verified'] = True
        profile_keys = ('offsets', 't', 'source_m', 'bed_m')
        if centerline_profile is not None:
            profile = tuple((_i2_np.asarray(centerline_profile[key]) for key in profile_keys))
        elif all(('centerline_profile_' + key in arrays for key in profile_keys)):
            profile = tuple((arrays['centerline_profile_' + key] for key in profile_keys))
        else:
            profile = None
        if profile is not None:
            pass
            rows = bed_constraints(arrays['node_xz_m'], arrays['receiver'], arrays['cells'], arrays['vertices_xz_m'], arrays['triangles'], arrays['original_macro_bed_m'], terrain, result['fine_spacing_m'], profile, 1e-05)
            residual = max((float(weights @ arrays['local_cut_m'][ids] - limit) for ids, weights, limit, kind in rows if kind == 'profile'), default=0.0)
            audit.update(frozen_profile_ceiling_max_residual_m=residual, frozen_profile_ceiling_verified=residual <= 1e-08, frozen_profile_constraint_count=sum((kind == 'profile' for _, _, _, kind in rows)))
            audit['accepted'] = bool(audit['accepted'] and residual <= 1e-08)
        else:
            audit.update(frozen_profile_ceiling_verified=False, frozen_profile_ceiling_scope='source profile not supplied or archived')
        if result.get('shared_sections'):
            pass
            rows = shared_section_constraints(result['shared_sections'], arrays['cells'], arrays['vertices_xz_m'], arrays['triangles'], arrays['original_macro_bed_m'], terrain, result['fine_spacing_m'])
            residual = max((float(weights @ arrays['local_cut_m'][ids] - limit) for ids, weights, limit, _ in rows), default=0.0)
            audit.update(shared_section_affine_max_residual_m=residual, shared_section_constraint_count=len(rows), shared_section_continuous_trace_verified=residual <= 1e-08)
            audit['accepted'] = bool(audit['accepted'] and residual <= 1e-08)
        return audit
    except ValueError as error:
        return {'accepted': False, 'reason': str(error), 'center_lowest_required': bool(center_lowest)}

def derive_continuous_bed(detail, points_xz_m, receiver, width_m, bed_target_m, *, fine_spacing_m=1.0, frozen_plan=None, node_source_edges=None, node_edge_fractions=None, centerline_profile=None, tributary_declaration=None, highest_lake_level_m=None, lake_mask=None, center_lowest=False, continuous_center_lowest=False, joint_component=False, shared_sections=None, frozen_path=None):
    """Explicit component only: no local rerouting, invented ports, or widening budget.

    A successful mesh remains locally geometric, not a hydraulic certificate.
    Macro-grid D8 evidence and fine triangle bed evidence remain distinct.
    """
    from terrain_pipeline.common_infra import TerrainGrid as _i2_TerrainGrid
    arrays, meta = (detail['arrays'], detail['metadata'])
    height = arrays['derived_height_m']
    origin = meta['origin_xz_m']
    terrain = _i2_TerrainGrid(height, _i2_np.ones(height.shape, dtype=bool), origin[0], origin[1], meta['spacing_m'], meta['spacing_m'], 'conditioned_terrain', 'hydrology-detail', meta['identity'])
    points = _i2_np.asarray(points_xz_m, dtype=_i2_np.float64)
    receiver = _i2_np.asarray(receiver, dtype=_i2_np.int64)
    width = _i2_np.asarray(width_m, dtype=_i2_np.float64)
    target = _i2_np.asarray(bed_target_m, dtype=_i2_np.float64)
    if points.ndim != 2 or points.shape[1] != 2 or (not 2 <= len(points) <= 16) or (receiver.shape != (len(points),)) or (width.shape != receiver.shape) or (target.shape != receiver.shape) or (not _i2_np.isfinite(points).all()) or (not _i2_np.isfinite(width).all()) or (not _i2_np.isfinite(target).all()) or _i2_np.any(width < 4) or _i2_np.any(width > 64) or _i2_np.any(receiver < -1) or _i2_np.any(receiver >= len(points)):
        raise ValueError('bounded 2..16 node frozen component with widths 4..64m required')
    if not 0.5 <= fine_spacing_m <= 2.0:
        raise ValueError('finite fine spacing must be 0.5..2m')
    if frozen_plan is None or node_source_edges is None or node_edge_fractions is None:
        return {'status': 'rejected', 'reason': 'component_missing_frozen_drainage_graph_provenance', 'arrays': {}}
    if frozen_plan.get('identity_sha256') != meta['plan_identity']:
        raise ValueError('fine component frozen-plan identity mismatch')
    if shared_sections and any((section.get('parent_detail_identity') != meta['identity'] or section.get('fine_spacing_m') != fine_spacing_m for section in shared_sections)):
        raise ValueError('shared-section source parent or fine spacing mismatch')
    source_edges = _i2_np.asarray(node_source_edges, dtype=_i2_np.int64)
    fractions = _i2_np.asarray(node_edge_fractions, dtype=_i2_np.float64)
    if source_edges.shape != (len(points), 2) or fractions.shape != (len(points),) or (not _i2_np.isfinite(fractions).all()) or _i2_np.any(fractions < 0) or _i2_np.any(fractions > 1):
        raise ValueError('each clipped node needs an actual frozen edge and fraction 0..1')
    frozen_receivers = _i2_np.asarray(frozen_plan['receiver']).ravel()
    frozen_rivers = _i2_np.asarray(frozen_plan['river_mask']).ravel()
    if _i2_np.any(source_edges < 0) or _i2_np.any(source_edges >= frozen_receivers.size):
        raise ValueError('invalid frozen source-edge cell ids')
    tributary_validation = None
    if tributary_declaration is not None:
        from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_source_edges
        tributary_validation = validate_local_tributary_source_edges(frozen_plan, tributary_declaration, source_edges, highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    if not _i2_np.all(frozen_receivers[source_edges[:, 0]] == source_edges[:, 1]) or (tributary_validation is None and (not _i2_np.all(frozen_rivers[source_edges[:, 0]]))):
        raise ValueError('component edges are not genuine frozen river graph edges')
    frozen_owners = _i2_np.asarray(frozen_plan['owner_domain_id']).ravel()
    coastal_domains = {domain['domain_id'] for domain in frozen_plan['domains'] if domain.get('kind') == 'coastal'}
    mouth_component = bool(_i2_np.any((frozen_owners[source_edges[:, 1]] == -1) & _i2_np.isin(frozen_owners[source_edges[:, 0]], list(coastal_domains))))
    columns = _i2_np.asarray(frozen_plan['height_m']).shape[1]
    source_xz = _i2_np.stack((source_edges % columns, source_edges // columns), axis=-1).astype(float)
    expected_points = _i2_np.asarray(frozen_plan['origin_xz_m']) + frozen_plan['spacing_m'] * (source_xz[:, 0, :] * (1 - fractions[:, None]) + source_xz[:, 1, :] * fractions[:, None])
    if frozen_path is None:
        if not _i2_np.allclose(points, expected_points, atol=1e-07, rtol=0):
            raise ValueError('component node coordinates differ from frozen graph clipping')
    else:
        pass
        validate_frozen_path_nodes(frozen_path, frozen_plan, points, source_edges, fractions, receiver)
    maximum = _i2_np.asarray(origin) + (_i2_np.array(height.shape)[::-1] - 1) * meta['spacing_m']
    if _i2_np.any(points < origin) or _i2_np.any(points > maximum):
        raise ValueError('component leaves finite genuine TD source')
    edges = _i2_np.flatnonzero(receiver >= 0)
    if not len(edges):
        raise ValueError('component needs a frozen directed edge')
    for node in edges:
        other = receiver[node]
        same_edge = _i2_np.array_equal(source_edges[node], source_edges[other]) and fractions[node] < fractions[other]
        shared_node = source_edges[node, 1] == source_edges[other, 0] and fractions[other] == 0
        if not same_edge and (not shared_node):
            raise ValueError('fine component joins unrelated frozen river edges')
    for node in range(len(points)):
        seen = set()
        while node >= 0:
            if node in seen:
                raise ValueError('frozen component cycle')
            seen.add(node)
            node = int(receiver[node])
    source, _ = _metric_channel_geometry_sample(height, points, terrain)
    if _i2_np.any(source - target > 4) or _i2_np.any(source - target < 0):
        return {'status': 'rejected', 'reason': 'continuous_bed_target_exceeds_original_4m_cut', 'arrays': {}}
    length = _i2_np.linalg.norm(points[edges] - points[receiver[edges]], axis=1)
    maximum_length = 3000 if joint_component and tributary_validation is not None and (len(points) == 4) else 1000
    if _i2_np.any(length <= 0) or _i2_np.any(length > maximum_length) or _i2_np.any(target[edges] - target[receiver[edges]] < length * 1e-05):
        return {'status': 'rejected', 'reason': 'non_descending_or_unbounded_frozen_component', 'arrays': {}}
    gx = _i2_np.rint((points[:, 0] - origin[0]) / meta['spacing_m']).astype(int)
    gz = _i2_np.rint((points[:, 1] - origin[1]) / meta['spacing_m']).astype(int)
    owner = arrays['owner_domain_id'][gz, gx]
    if _i2_np.any((owner[edges] != owner[receiver[edges]]) & (owner[receiver[edges]] >= 0)):
        return {'status': 'rejected', 'reason': 'frozen_component_crosses_shared_divide', 'arrays': {}}
    for node in edges:
        other = receiver[node]
        count = max(2, int(_i2_np.ceil(length[list(edges).index(node)] / min(meta['spacing_m'], fine_spacing_m))) + 1)
        samples = points[node] + _i2_np.linspace(0, 1, count)[:, None] * (points[other] - points[node])
        sx = _i2_np.rint((samples[:, 0] - origin[0]) / meta['spacing_m']).astype(int)
        sz = _i2_np.rint((samples[:, 1] - origin[1]) / meta['spacing_m']).astype(int)
        actual_owners = arrays['owner_domain_id'][sz, sx]
        same_domain = actual_owners == frozen_owners[source_edges[node, 0]]
        certified_ocean = (actual_owners == -1) & arrays['ocean_mask'][sz, sx] & (height[sz, sx] < 0) & mouth_component
        if not _i2_np.all(same_domain | certified_ocean):
            return {'status': 'rejected', 'reason': 'frozen_segment_interior_leaves_owner', 'arrays': {}}
    profile = (_i2_np.arange(0, 2 * len(edges) + 1, 2), _i2_np.tile([0.0, 1.0], len(edges)), _i2_np.column_stack((source[edges], source[receiver[edges]])).ravel(), _i2_np.column_stack((target[edges], target[receiver[edges]])).ravel())
    if centerline_profile is not None:
        if centerline_profile.get('parent_detail_identity') != meta['identity']:
            raise ValueError('full-window profile parent identity mismatch')
        profile = tuple((_i2_np.asarray(centerline_profile[key], dtype=int if key == 'offsets' else float) for key in ('offsets', 't', 'source_m', 'bed_m')))
        if profile[0].shape != (len(edges) + 1,) or profile[0][0] != 0 or profile[0][-1] != len(profile[1]) or _i2_np.any(_i2_np.diff(profile[0]) < 2) or (profile[2].shape != profile[1].shape) or (profile[3].shape != profile[1].shape) or (not all((_i2_np.isfinite(value).all() for value in profile))):
            raise ValueError('finite complete full-window profile required')
        for edge_index, node in enumerate(edges):
            lo, hi = profile[0][edge_index:edge_index + 2]
            t = profile[1][lo:hi]
            bed = profile[3][lo:hi]
            other = receiver[node]
            if t[0] != 0 or t[-1] != 1 or _i2_np.any(_i2_np.diff(t) <= 0) or (_i2_np.max(_i2_np.diff(t)) * length[edge_index] > fine_spacing_m * 1.01) or (not _i2_np.allclose(bed[[0, -1]], target[[node, other]], atol=1e-08, rtol=0)) or _i2_np.any(_i2_np.diff(bed) > -_i2_np.diff(t) * length[edge_index] * 1e-05 + 1e-08):
                raise ValueError('full-window profile must cover every segment with shared descending node beds')
            actual, _ = _metric_channel_geometry_sample(height, points[node] + t[:, None] * (points[other] - points[node]), terrain)
            if not _i2_np.allclose(actual, profile[2][lo:hi], atol=0.0001, rtol=0):
                raise ValueError('full-window profile source differs from parent terrain')
            if _i2_np.any(actual - bed > 4 + 1e-08) or _i2_np.any(actual - bed < -1e-08):
                return {'status': 'rejected', 'reason': 'full_window_profile_exceeds_original_4m_cut', 'arrays': {}}
    try:
        mesh = build_design_geometry(points, receiver, width, _i2_np.minimum(0.5, source - target), profile, terrain, fine_spacing_m, 4.0, 1e-05, transverse_bottom_slope=0.02, center_lowest=center_lowest, continuous_center_lowest=continuous_center_lowest, shared_sections=shared_sections)
    except ValueError as error:
        return {'status': 'rejected', 'reason': str(error), 'arrays': {}}
    cells, vertices, triangles, original, _, cut, closure = mesh[:7]
    if _i2_np.any(vertices < origin) or _i2_np.any(vertices > maximum):
        return {'status': 'rejected', 'reason': 'continuous_mesh_leaves_genuine_td_support', 'arrays': {}}
    vx = _i2_np.rint((vertices[:, 0] - origin[0]) / meta['spacing_m']).astype(int)
    vz = _i2_np.rint((vertices[:, 1] - origin[1]) / meta['spacing_m']).astype(int)
    vertex_owners = arrays['owner_domain_id'][vz, vx]
    same_domain = vertex_owners == frozen_owners[source_edges[edges[0], 0]]
    certified_ocean = (vertex_owners == -1) & arrays['ocean_mask'][vz, vx] & (height[vz, vx] < 0) & mouth_component
    if not _i2_np.all(same_domain | certified_ocean):
        return {'status': 'rejected', 'reason': 'continuous_mesh_enters_unknown_or_other_domain', 'arrays': {}}
    if _i2_np.any(arrays['shared_boundary_protected'][vz, vx] & (cut > 1e-10)):
        return {'status': 'rejected', 'reason': 'continuous_bed_support_touches_shared_divide', 'arrays': {}}
    try:
        audit = _audit_mesh(cells, vertices, triangles, original, cut, points, receiver, width, terrain, fine_spacing_m, center_lowest=center_lowest, continuous_center_lowest=continuous_center_lowest)
    except ValueError as error:
        return {'status': 'rejected', 'reason': str(error), 'arrays': {}}
    if not audit['accepted']:
        return {'status': 'rejected', 'reason': 'independent_continuous_bed_audit_failed', 'audit': audit, 'arrays': {}}
    original_td, _ = _metric_channel_geometry_sample(arrays['original_td_m'], vertices, terrain)
    macro_delta = original - original_td
    total_delta = original - cut - original_td
    ledger = {'local_max_cut_m': float(cut.max(initial=0.0)), 'local_cut_volume_m3': _mesh_volume_chunked(vertices, triangles, cut), 'macro_max_abs_m': float(_i2_np.abs(macro_delta).max(initial=0.0)), 'total_max_abs_m': float(_i2_np.abs(total_delta).max(initial=0.0)), 'total_absolute_volume_upper_bound_m3': _mesh_volume_chunked(vertices, triangles, _i2_np.abs(total_delta)), 'volume_semantics': 'exact linear cut integration; absolute total integration upper bound when sign crosses a triangle'}
    if ledger['total_max_abs_m'] > meta['budget']['total_max_abs_m'] or ledger['total_absolute_volume_upper_bound_m3'] > meta['budget']['total_absolute_volume_m3']:
        return {'status': 'rejected', 'reason': 'continuous_mesh_total_change_budget_exceeded', 'ledger': ledger, 'arrays': {}}
    return {'status': 'local_continuous_geometry_global_unverified', 'closure': closure, 'algorithm': 'frozen-continuous-bed-v9-whole-path-arclength' if frozen_path is not None else 'frozen-continuous-bed-v8-complete-adjacent-shared-sections' if shared_sections and all((section['algorithm'] == 'bounded-complete-adjacent-feasible-fan4-section-v3' for section in shared_sections)) else 'frozen-continuous-bed-v7-bounded-feasible-shared-sections' if shared_sections else 'frozen-continuous-bed-v5-continuous-center-floor' if continuous_center_lowest else 'frozen-continuous-bed-v4-center-lowest' if center_lowest else 'frozen-continuous-bed-v3-ceiling-only', 'center_lowest': bool(center_lowest), 'continuous_center_lowest': bool(continuous_center_lowest), 'shared_sections': shared_sections, 'independent_geometry_audit': audit, 'ledger': ledger, 'global_hydrology_certified': False, 'publishable': False, 'parent_detail_identity': meta['identity'], 'fine_spacing_m': fine_spacing_m, 'mesh_origin_xz_m': list(origin), 'frozen_plan_identity': frozen_plan['identity_sha256'], **({'frozen_path_identity': frozen_path['identity'], 'frozen_path_source_identity': frozen_path['metadata']['source_identity']} if frozen_path is not None else {}), 'local_tributary_sidecar_validation': tributary_validation, 'component_boundary_policy': 'clipped frozen graph; outside component hydraulics unknown', 'certified_coastal_ocean_support': mouth_component, 'arrays': {'cells': cells, 'vertices_xz_m': vertices, 'triangles': triangles, 'original_macro_bed_m': original, 'local_cut_m': cut, 'bed_elevation_m': original - cut, 'original_td_m': original_td, 'macro_delta_m': macro_delta, 'local_channel_delta_m': -cut, 'total_delta_m': total_delta, 'node_xz_m': points, 'node_bed_target_m': target, 'receiver': receiver, 'width_m': width, 'node_source_edges': source_edges, 'node_edge_fractions': fractions, **{'centerline_profile_' + key: value for key, value in zip(('offsets', 't', 'source_m', 'bed_m'), profile)}}}
LOCAL_CHANNEL_SECTIONS_VERSION = 'local-channel-sections-v1'

@_i3_dataclass(frozen=True)
class SectionRecipe:
    max_local_cut_m: float = 4.0
    min_cells_across_width: float = 2.0

    def __post_init__(self):
        if isinstance(self.max_local_cut_m, bool) or not _i3_math.isfinite(self.max_local_cut_m) or self.max_local_cut_m < 0:
            raise ValueError('max_local_cut_m must be finite and nonnegative')
        if isinstance(self.min_cells_across_width, bool) or not _i3_math.isfinite(self.min_cells_across_width) or self.min_cells_across_width <= 0:
            raise ValueError('min_cells_across_width must be finite and positive')

def _source_surface(height, fx, fz):
    x0 = _i3_np.floor(fx).astype(int)
    z0 = _i3_np.floor(fz).astype(int)
    x1 = _i3_np.minimum(x0 + 1, height.shape[1] - 1)
    z1 = _i3_np.minimum(z0 + 1, height.shape[0] - 1)
    tx = fx - x0
    tz = fz - z0
    return (1 - tx) * (1 - tz) * height[z0, x0] + tx * (1 - tz) * height[z0, x1] + (1 - tx) * tz * height[z1, x0] + tx * tz * height[z1, x1]

def _sweep_sections(plan, gx, gz, spacing_x_m, spacing_z_m, recipe, centerline=None):
    arrays = plan['arrays']
    params = plan['identity']['parameters']
    shape = gx.shape
    source = _source_surface(arrays['source_height_m'], _i3_np.clip((gx - params['origin_x_m']) / params['spacing_x_m'], 0, arrays['source_height_m'].shape[1] - 1), _i3_np.clip((gz - params['origin_z_m']) / params['spacing_z_m'], 0, arrays['source_height_m'].shape[0] - 1))
    required = _i3_np.zeros(shape, dtype=_i3_np.float64)
    refinement = _i3_np.zeros(shape, dtype=bool)
    aliased = 0
    width = arrays['nominal_width_m'].ravel()
    bed = arrays['target_bed_m'].ravel()
    active = arrays['channel_mask'].ravel()
    receiver = arrays['receiver']
    coarse_dx = params['spacing_x_m']
    coarse_dz = params['spacing_z_m']
    cols = arrays['source_height_m'].shape[1]
    if centerline is None:
        segments = ((params['origin_x_m'] + cell % cols * coarse_dx, params['origin_z_m'] + cell // cols * coarse_dz, params['origin_x_m'] + target % cols * coarse_dx, params['origin_z_m'] + target // cols * coarse_dz, width[cell], width[target], bed[cell], bed[target]) for cell in _i3_np.flatnonzero(active) for target in (int(receiver[cell]),) if target >= 0 and active[target])
    else:
        nodes = centerline['arrays']['node_flat_index']
        positions = centerline['arrays']['node_world_xz_m']
        node_lookup = {int(cell): index for index, cell in enumerate(nodes)}
        segments = ((positions[node_lookup[int(cell)], 0], positions[node_lookup[int(cell)], 1], positions[node_lookup[int(target)], 0], positions[node_lookup[int(target)], 1], width[cell], width[target], bed[cell], bed[target]) for cell, target in zip(centerline['arrays']['edge_donor_flat_index'], centerline['arrays']['edge_target_flat_index']))
    for ax, az, bx, bz, width_a, width_b, bed_a, bed_b in segments:
        radius = max(width_a, width_b) / 2
        if max(ax, bx) + radius < gx[0, 0] or min(ax, bx) - radius > gx[0, -1] or max(az, bz) + radius < gz[0, 0] or (min(az, bz) - radius > gz[-1, 0]):
            continue
        length2 = (bx - ax) ** 2 + (bz - az) ** 2
        t = _i3_np.clip(((gx - ax) * (bx - ax) + (gz - az) * (bz - az)) / length2, 0.0, 1.0)
        distance = _i3_np.hypot(gx - (ax + t * (bx - ax)), gz - (az + t * (bz - az)))
        local_radius = ((1 - t) * width_a + t * width_b) / 2
        inside = distance < local_radius
        if not _i3_np.any(inside):
            aliased += 1
            continue
        refinement |= inside & (2 * local_radius < recipe.min_cells_across_width * max(spacing_x_m, spacing_z_m))
        taper = _i3_np.zeros(shape)
        taper[inside] = 0.5 * (1 + _i3_np.cos(_i3_np.pi * distance[inside] / local_radius[inside]))
        bedline = (1 - t) * bed_a + t * bed_b
        required = _i3_np.maximum(required, _i3_np.maximum(0.0, source - bedline) * taper)
    return (source, required, refinement, aliased)

def evaluate_sections(plan, x0_m, z0_m, spacing_x_m, spacing_z_m, shape_zx, protected_mask, recipe: SectionRecipe, centerline=None):
    """Sweep cosine-tapered full-width cuts; overlapping segments use the deepest cut."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i3_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i3_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i3_digest
    if not isinstance(recipe, SectionRecipe) or plan.get('status') != 'diagnostic_not_publishable':
        raise ValueError('validated diagnostic plan and section recipe required')
    arrays = plan['arrays']
    params = plan['identity']['parameters']
    if _i3_ArtifactIdentity(**plan['identity']).sha256 != plan['identity_sha256']:
        raise ValueError('plan identity mismatch')
    if plan['identity']['algorithm'] != 'metric-channel-plan':
        raise ValueError('wrong plan algorithm')
    for name, field in (('source_height_m', 'source_height_sha256'), ('discharge_m3_s', 'source_discharge_sha256'), ('receiver', 'source_route_sha256'), ('order', 'source_order_sha256'), ('outlet_mask', 'source_outlet_sha256')):
        if _i3_array_hash(_i3_np.ascontiguousarray(arrays[name])) != params[field]:
            raise ValueError('plan input differs from identity')
    source_shape = arrays['source_height_m'].shape
    if len(source_shape) != 2 or min(source_shape) < 2 or arrays['channel_mask'].shape != source_shape or (arrays['target_bed_m'].shape != source_shape) or (arrays['nominal_width_m'].shape != source_shape) or (not _i3_np.isfinite(arrays['source_height_m']).all()) or (not _i3_np.isfinite(arrays['target_bed_m']).all()) or (not _i3_np.isfinite(arrays['nominal_width_m']).all()):
        raise ValueError('invalid plan geometry arrays')
    _validate_route(arrays['receiver'], arrays['order'], source_shape, arrays['outlet_mask'], _mesh_from_parameters(params, source_shape), historical_saved_graph=plan['identity']['algorithm_version'] == 'metric-channel-plan-v1')
    if _i3_np.any(arrays['nominal_width_m'][arrays['channel_mask']] <= 0) or _i3_np.any(arrays['target_bed_m'] > arrays['source_height_m'] + 1e-09):
        raise ValueError('invalid active width or bed target')
    geometry_hash = _i3_digest({name: _i3_array_hash(_i3_np.ascontiguousarray(arrays[name])) for name in ('target_bed_m', 'nominal_width_m', 'channel_mask')})
    if centerline is not None:
        pass
        validate_centerline_for_plan(centerline, plan)
    if len(shape_zx) != 2 or any((type(size) is not int or size < 2 for size in shape_zx)):
        raise ValueError('local grid needs at least 2x2 nodes')
    if any((isinstance(value, bool) or not _i3_math.isfinite(value) for value in (x0_m, z0_m, spacing_x_m, spacing_z_m))) or min(spacing_x_m, spacing_z_m) <= 0:
        raise ValueError('local origin and spacing must be finite; spacing positive')
    protected = _i3_np.asarray(protected_mask)
    if protected.shape != tuple(shape_zx) or protected.dtype != bool:
        raise ValueError('protected_mask must be boolean and match local grid')
    coarse_dx = params['spacing_x_m']
    coarse_dz = params['spacing_z_m']
    rows, cols = arrays['source_height_m'].shape
    fine_x = x0_m + _i3_np.arange(shape_zx[1]) * spacing_x_m
    fine_z = z0_m + _i3_np.arange(shape_zx[0]) * spacing_z_m
    fx = (fine_x - params['origin_x_m']) / coarse_dx
    fz = (fine_z - params['origin_z_m']) / coarse_dz
    if min(fx) < -1e-09 or max(fx) > cols - 1 + 1e-09 or min(fz) < -1e-09 or (max(fz) > rows - 1 + 1e-09):
        raise ValueError('local grid extends outside shared source plan')
    gx, gz = _i3_np.meshgrid(fine_x, fine_z)
    source, required, needs_refinement, aliased_segments = _sweep_sections(plan, gx, gz, spacing_x_m, spacing_z_m, recipe, centerline)
    if not _i3_np.isfinite(source).all() or not _i3_np.isfinite(required).all():
        raise ValueError('local section geometry overflows')
    over_budget = required > recipe.max_local_cut_m + 1e-09
    protected_conflict = protected & (required > 1e-09)
    actual = _i3_np.minimum(required, recipe.max_local_cut_m)
    actual[protected] = 0.0
    boundary = _i3_np.zeros(shape_zx, dtype=bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    clipped = boundary & (required > 1e-09)
    node_weight = _i3_np.ones(shape_zx)
    node_weight[[0, -1], :] *= 0.5
    node_weight[:, [0, -1]] *= 0.5
    volume = float(_i3_np.sum(actual * node_weight) * spacing_x_m * spacing_z_m)
    if not _i3_math.isfinite(volume):
        raise ValueError('local cut volume overflows')
    section_version = LOCAL_CHANNEL_SECTIONS_VERSION if centerline is None else 'local-channel-sections-centerline-v1'
    identity_params = {**_i3_asdict(recipe), 'plan_identity_sha256': plan['identity_sha256'], 'plan_geometry_sha256': geometry_hash, 'origin_x_m': float(x0_m), 'origin_z_m': float(z0_m), 'spacing_x_m': float(spacing_x_m), 'spacing_z_m': float(spacing_z_m), 'protected_mask_sha256': _i3_array_hash(protected), 'source_surface_sha256': _i3_array_hash(source)}
    if centerline is not None:
        identity_params['centerline_identity_sha256'] = centerline['identity_sha256']
        identity_params['centerline_geometry_sha256'] = _i3_digest({name: _i3_array_hash(_i3_np.ascontiguousarray(centerline['arrays'][name])) for name in ('node_world_xz_m', 'edge_donor_flat_index', 'edge_target_flat_index')})
    identity = _i3_ArtifactIdentity('Terragenesis', 'local-channel-sections', section_version, 0, identity_params)
    outputs = {'source_surface_m': source, 'required_cut_m': required, 'bounded_surface_m': source - actual, 'actual_cut_m': actual, 'over_budget_mask': over_budget, 'protected_mask': protected.copy(), 'protected_conflict_mask': protected_conflict, 'clipped_boundary_mask': clipped, 'needs_refinement_mask': needs_refinement}
    for value in outputs.values():
        value.flags.writeable = False
    plan_blocked = bool(_i3_np.any(arrays['over_budget_mask']) or _i3_np.any(arrays['failed_slope_edge_donor_mask']))
    centerline_slope_failures = int(_i3_np.count_nonzero(centerline['arrays']['slope_failed_donor_mask'])) if centerline is not None else 0
    centerline_budget_failures = int(_i3_np.count_nonzero(centerline['arrays']['local_budget_failed_mask'])) if centerline is not None else 0
    summary = {'actual_cut_volume_m3': volume, 'plan_over_budget_cells': int(_i3_np.count_nonzero(arrays['over_budget_mask'])), 'plan_failed_slope_edges': int(_i3_np.count_nonzero(arrays['failed_slope_edge_donor_mask'])), 'blocked_by_plan': plan_blocked, 'local_budget_conflict_nodes': int(_i3_np.count_nonzero(over_budget)), 'needs_refinement_nodes': int(_i3_np.count_nonzero(needs_refinement)), 'clipped_boundary_nodes': int(_i3_np.count_nonzero(clipped)), 'requires_shared_fine_extension': bool(_i3_np.any(clipped)), 'potentially_unsampled_segments': aliased_segments, 'protected_conflict_nodes': int(_i3_np.count_nonzero(protected_conflict))}
    if centerline is not None:
        summary.update({'centerline_slope_failed_edges': centerline_slope_failures, 'centerline_budget_failed_nodes': centerline_budget_failures, 'blocked_by_centerline': bool(centerline_slope_failures or centerline_budget_failures)})
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': 'diagnostic_not_publishable', 'arrays': outputs, 'summary': summary}

def save_sections(result, path):
    from terrain_pipeline.artifacts.contracts import array_hash as _i3_array_hash
    destination = _i3_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ('identity', 'identity_sha256', 'status', 'summary')}
    record['format_version'] = 1
    record['array_sha256'] = {name: _i3_array_hash(value) for name, value in result['arrays'].items()}
    temporary = None
    try:
        with _i3_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, prefix=f'.{destination.name}-', suffix='.npz', delete=False) as stream:
            temporary = _i3_Path(stream.name)
            _i3_np.savez_compressed(stream, manifest=_i3_json.dumps(record, sort_keys=True), **result['arrays'])
        load_sections(temporary)
        _i3_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def load_sections(path):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i3_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i3_array_hash
    with _i3_np.load(path, allow_pickle=False) as archive:
        record = _i3_json.loads(str(archive['manifest'].item()))
        arrays = {name: archive[name].copy() for name in record['array_sha256']}
        expected = {'source_surface_m', 'required_cut_m', 'bounded_surface_m', 'actual_cut_m', 'over_budget_mask', 'protected_mask', 'protected_conflict_mask', 'clipped_boundary_mask', 'needs_refinement_mask'}
        if set(arrays) != expected or set(archive.files) != expected | {'manifest'}:
            raise ValueError('unexpected section arrays')
    identity = _i3_ArtifactIdentity(**record['identity'])
    if identity.sha256 != record['identity_sha256'] or record['status'] != 'diagnostic_not_publishable' or record['format_version'] != 1:
        raise ValueError('invalid section identity')
    if any((_i3_array_hash(arrays[name]) != expected for name, expected in record['array_sha256'].items())):
        raise ValueError('section array hash mismatch')
    params = identity.record()['parameters']
    recipe = SectionRecipe(params['max_local_cut_m'], params['min_cells_across_width'])
    if any((not _i3_math.isfinite(params[name]) or params[name] <= 0 for name in ('spacing_x_m', 'spacing_z_m'))):
        raise ValueError('invalid section spacing')
    if _i3_array_hash(arrays['protected_mask']) != params['protected_mask_sha256'] or _i3_array_hash(arrays['source_surface_m']) != params['source_surface_sha256']:
        raise ValueError('section source or protection differs from identity')
    shape = arrays['source_surface_m'].shape
    if len(shape) != 2 or min(shape) < 2 or any((value.shape != shape for value in arrays.values())):
        raise ValueError('invalid section array shape')
    for name in ('source_surface_m', 'required_cut_m', 'bounded_surface_m', 'actual_cut_m'):
        if arrays[name].dtype != _i3_np.float64 or not _i3_np.isfinite(arrays[name]).all():
            raise ValueError('invalid section float array')
    for name in set(arrays) - {'source_surface_m', 'required_cut_m', 'bounded_surface_m', 'actual_cut_m'}:
        if arrays[name].dtype != bool:
            raise ValueError('invalid section mask array')
    if not _i3_np.allclose(arrays['source_surface_m'] - arrays['actual_cut_m'], arrays['bounded_surface_m'], atol=1e-09, rtol=0) or _i3_np.any(arrays['actual_cut_m'] < -1e-09) or _i3_np.any(arrays['actual_cut_m'] > arrays['required_cut_m'] + 1e-09) or _i3_np.any(arrays['protected_mask'] & (arrays['actual_cut_m'] > 1e-09)):
        raise ValueError('inconsistent section cut arrays')
    expected_over = arrays['required_cut_m'] > recipe.max_local_cut_m + 1e-09
    expected_protection = arrays['protected_mask'] & (arrays['required_cut_m'] > 1e-09)
    expected_actual = _i3_np.minimum(arrays['required_cut_m'], recipe.max_local_cut_m)
    expected_actual[arrays['protected_mask']] = 0.0
    edge = _i3_np.zeros(shape, dtype=bool)
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True
    expected_clipped = edge & (arrays['required_cut_m'] > 1e-09)
    if not _i3_np.array_equal(arrays['over_budget_mask'], expected_over) or not _i3_np.array_equal(arrays['protected_conflict_mask'], expected_protection) or (not _i3_np.array_equal(arrays['clipped_boundary_mask'], expected_clipped)) or (not _i3_np.allclose(arrays['actual_cut_m'], expected_actual, atol=1e-09, rtol=0)):
        raise ValueError('section masks or bounded cut disagree with required geometry')
    summary = record['summary']
    if summary['local_budget_conflict_nodes'] != int(_i3_np.count_nonzero(expected_over)) or summary['protected_conflict_nodes'] != int(_i3_np.count_nonzero(expected_protection)) or summary['clipped_boundary_nodes'] != int(_i3_np.count_nonzero(expected_clipped)) or (summary['needs_refinement_nodes'] != int(_i3_np.count_nonzero(arrays['needs_refinement_mask']))) or (summary['requires_shared_fine_extension'] != bool(_i3_np.any(expected_clipped))):
        raise ValueError('section summary disagrees with masks')
    weight = _i3_np.ones(shape)
    weight[[0, -1], :] *= 0.5
    weight[:, [0, -1]] *= 0.5
    volume = float(_i3_np.sum(arrays['actual_cut_m'] * weight) * params['spacing_x_m'] * params['spacing_z_m'])
    if not _i3_math.isclose(volume, record['summary']['actual_cut_volume_m3'], abs_tol=1e-07):
        raise ValueError('section volume summary mismatch')
    for value in arrays.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': record['status'], 'arrays': arrays, 'summary': record['summary']}
FINE_SPACING_M = 1.0
WIDTH_M = 10.0
MAX_ATTEMPTS = 64
MAX_FINE_CELLS = 250000
MAX_CHAIN_SEGMENTS = 16
MIN_CHAIN_SEGMENTS = 3

def _mountain_fine_geometry_sample(height, column, row):
    left = _i5_np.floor(column).astype(_i5_np.int64)
    top = _i5_np.floor(row).astype(_i5_np.int64)
    right = _i5_np.minimum(left + 1, height.shape[1] - 1)
    bottom = _i5_np.minimum(top + 1, height.shape[0] - 1)
    fraction_x = column - left
    fraction_z = row - top
    return (1 - fraction_z) * ((1 - fraction_x) * height[top, left] + fraction_x * height[top, right]) + fraction_z * ((1 - fraction_x) * height[bottom, left] + fraction_x * height[bottom, right])

def prepare_fine_segment(result, donor, *, fine_spacing_m=FINE_SPACING_M, width_m=WIDTH_M):
    """Return complete strip evidence or refusal, not a whole-network certification."""
    from terrain_pipeline.lake import GeometryBudget as _i5_GeometryBudget
    arrays, metadata = (result['arrays'], result['metadata'])
    height = arrays['H0_m']
    if type(donor) is not int or not 0 <= donor < height.size:
        raise ValueError('invalid donor')
    if fine_spacing_m != FINE_SPACING_M or width_m != WIDTH_M:
        raise ValueError('fixed fine budget cannot be retuned after trial')
    receiver = int(arrays['receiver'][donor])
    if receiver < 0 or not arrays['accepted_mask'].flat[donor] or (not arrays['accepted_mask'].flat[receiver]):
        raise ValueError('accepted connected segment required')
    if arrays['lake_mask'].flat[donor] or arrays['lake_mask'].flat[receiver]:
        raise ValueError('lake/spill requires separate fine seam design')
    spacing = metadata['spacing_m']
    donor_row, donor_column = divmod(donor, height.shape[1])
    receiver_row, receiver_column = divmod(receiver, height.shape[1])
    delta_row = receiver_row - donor_row
    delta_column = receiver_column - donor_column
    if abs(delta_row) + abs(delta_column) != 1:
        raise ValueError('fine strip requires D4 full-edge segment')
    if spacing / fine_spacing_m % 1 or width_m / fine_spacing_m % 1:
        raise ValueError('strip dimensions must contain whole fine intervals')
    along = _i5_np.arange(int(spacing / fine_spacing_m) + 1) * fine_spacing_m
    across = _i5_np.arange(int(width_m / fine_spacing_m) + 1) * fine_spacing_m - width_m / 2
    if along.size * across.size > MAX_FINE_CELLS:
        raise ValueError('fine strip allocation resource limit')
    columns = donor_column + along[:, None] / spacing * delta_column - across[None, :] / spacing * delta_row
    rows = donor_row + along[:, None] / spacing * delta_row + across[None, :] / spacing * delta_column
    if (columns < 0).any() or (columns > height.shape[1] - 1).any() or (rows < 0).any() or (rows > height.shape[0] - 1).any():
        return {'status': 'refused', 'reason': 'fine_strip_leaves_original_window', 'donor': donor, 'receiver': receiver}
    original = _mountain_fine_geometry_sample(height, columns, rows)
    nearest_rows = _i5_np.floor(rows + 0.5).astype(_i5_np.int64)
    nearest_columns = _i5_np.floor(columns + 0.5).astype(_i5_np.int64)
    if (arrays['protected_mask'][nearest_rows, nearest_columns] | arrays['lake_mask'][nearest_rows, nearest_columns] | ~arrays['accepted_mask'][nearest_rows, nearest_columns]).any():
        return {'status': 'refused', 'reason': 'fine_strip_crosses_protection_lake_or_unaccepted_group', 'donor': donor, 'receiver': receiver}
    donor_cut = float(arrays['cut_depth_m'].flat[donor])
    receiver_cut = float(arrays['cut_depth_m'].flat[receiver])
    center_cut = donor_cut + along / spacing * (receiver_cut - donor_cut)
    taper = 0.5 * (1 + _i5_np.cos(_i5_np.pi * across / (width_m / 2)))
    cut = center_cut[:, None] * taper[None, :]
    bed = original - cut
    center = across.size // 2
    center_bed = bed[:, center]
    flags = []
    budget = _i5_GeometryBudget(**metadata['budget'])
    if _i5_np.min(center_cut) <= 0:
        flags.append('zero_depth_endpoint')
    if (_i5_np.diff(center_bed) > 1e-09).any():
        flags.append('fine_center_bed_uphill')
    if (bed < center_bed[:, None] - 1e-09).any():
        flags.append('cross_section_not_valley_minimum')
    if cut.max() > budget.max_total_cut_m + 1e-09:
        flags.append('fine_cut_depth_budget')
    weights = _i5_np.ones(cut.shape)
    weights[0, :] *= 0.5
    weights[-1, :] *= 0.5
    weights[:, 0] *= 0.5
    weights[:, -1] *= 0.5
    volume = float((cut * weights).sum() * fine_spacing_m ** 2)
    remaining = budget.max_cut_volume_m3
    if volume > remaining + 1e-09:
        flags.append('independent_fine_volume_budget')
    origin_x, origin_z = metadata['origin_m_xz']
    return {'status': 'accepted_fine_local_geometry' if not flags else 'refused', 'reason_flags': flags, 'donor': donor, 'receiver': receiver, 'width_m': width_m, 'fine_spacing_m': fine_spacing_m, 'fine_cells': int(cut.size), 'cut_volume_m3': volume, 'remaining_coarse_budget_m3': remaining, 'scope': 'independent_alternative_local_strip_not_added_to_or_merged_into_coarse_surface', 'arrays': {'along_m': along, 'across_m': across, 'world_x_m': origin_x + columns * spacing, 'world_z_m': origin_z + rows * spacing, 'H0_m': original, 'H1_m': original.copy(), 'H2_m': bed, 'cut_depth_m': cut, 'quadrature_area_m2': weights * fine_spacing_m ** 2, 'center_bed_m': center_bed}}

def select_fine_geometry(result):
    """Deterministic depth-first ranking; retain all failed attempted segments."""
    arrays = result['arrays']
    receiver = arrays['receiver']
    donors = _i5_np.flatnonzero(arrays['accepted_mask'].ravel() & arrays['dry_channel_mask'].ravel() & (arrays['cut_depth_m'].ravel() > 0) & (receiver >= 0))
    targets = receiver[donors]
    eligible = ~arrays['lake_mask'].ravel()[targets] & (arrays['cut_depth_m'].ravel()[targets] > 0)
    donors = donors[eligible]
    ranking = _i5_np.lexsort((donors, -arrays['contributing_area_m2'].ravel()[donors]))
    evidence = []
    spent = 0
    accepted = None
    for donor in donors[ranking][:MAX_ATTEMPTS]:
        trial = prepare_fine_segment(result, int(donor))
        spent += trial.get('fine_cells', 0)
        if spent > MAX_FINE_CELLS:
            raise ValueError('fine attempt resource budget exceeded')
        evidence.append({key: value for key, value in trial.items() if key != 'arrays'})
        if trial['status'] == 'accepted_fine_local_geometry':
            accepted = trial
            break
    return {'attempts': evidence, 'fine_cells': spent, 'max_attempts': MAX_ATTEMPTS, 'max_fine_cells': MAX_FINE_CELLS, 'accepted': accepted}

def select_continuous_fine_geometry(result):
    """Straight D4 chain, exact shared cross sections and explicit local receiving seam."""
    arrays = result['arrays']
    receiver = arrays['receiver']
    donors = _i5_np.flatnonzero(arrays['accepted_mask'].ravel() & arrays['dry_channel_mask'].ravel() & (arrays['cut_depth_m'].ravel() > 0) & (receiver >= 0))
    ranking = _i5_np.lexsort((donors, -arrays['contributing_area_m2'].ravel()[donors]))
    candidates = []
    for start in donors[ranking]:
        chain = [int(start)]
        direction = int(receiver[start] - start)
        while len(chain) <= MAX_CHAIN_SEGMENTS:
            target = int(receiver[chain[-1]])
            if target < 0 or target - chain[-1] != direction or arrays['lake_mask'].flat[target] or (not arrays['accepted_mask'].flat[target]) or (arrays['cut_depth_m'].flat[target] <= 0):
                break
            chain.append(target)
        if len(chain) - 1 >= MIN_CHAIN_SEGMENTS:
            candidates.append(chain)
        if len(candidates) >= MAX_ATTEMPTS:
            break
    attempts = []
    spent = 0
    for chain in candidates:
        strips = []
        flags = []
        for cell in chain[:-1]:
            trial = prepare_fine_segment(result, cell)
            spent += trial.get('fine_cells', 0)
            if spent > MAX_FINE_CELLS:
                flags.append('total_fine_resource_limit')
                break
            if trial['status'] != 'accepted_fine_local_geometry':
                flags.extend(trial.get('reason_flags', [trial.get('reason', 'refused')]))
                break
            strips.append(trial)
        if flags:
            attempts.append({'chain_cells': chain, 'status': 'refused', 'reason_flags': flags})
            if 'total_fine_resource_limit' in flags:
                break
            continue
        for before, after in zip(strips[:-1], strips[1:]):
            for key in ('world_x_m', 'world_z_m', 'H0_m', 'H1_m', 'H2_m'):
                if not _i5_np.allclose(before['arrays'][key][-1], after['arrays'][key][0], rtol=0.0, atol=1e-10):
                    raise ValueError('continuous chain shared section mismatch')
        fields = {}
        for key in ('world_x_m', 'world_z_m', 'H0_m', 'H1_m', 'H2_m', 'cut_depth_m'):
            fields[key] = _i5_np.concatenate([strip['arrays'][key][:-1] for strip in strips] + [strips[-1]['arrays'][key][-1:]], axis=0)
        fields['across_m'] = strips[0]['arrays']['across_m'].copy()
        fields['along_m'] = _i5_np.arange(fields['H0_m'].shape[0]) * FINE_SPACING_M
        fields['chain_cells'] = _i5_np.asarray(chain, dtype=_i5_np.int64)
        weights = _i5_np.ones(fields['H0_m'].shape)
        weights[0] *= 0.5
        weights[-1] *= 0.5
        weights[:, 0] *= 0.5
        weights[:, -1] *= 0.5
        fields['quadrature_area_m2'] = weights * FINE_SPACING_M ** 2
        volume = float((fields['cut_depth_m'] * fields['quadrature_area_m2']).sum())
        fields['shared_node_section_rows'] = _i5_np.arange(1, len(chain) - 1, dtype=_i5_np.int64) * int(result['metadata']['spacing_m'] / FINE_SPACING_M)
        accepted = {'status': 'accepted_continuous_local_fine_chain', 'arrays': fields, 'segments': len(chain) - 1, 'length_m': float(fields['along_m'][-1]), 'cut_volume_m3': volume, 'width_m': WIDTH_M, 'fine_spacing_m': FINE_SPACING_M, 'receiving_cell': chain[-1], 'receiving_type': 'explicit_local_geometry_seam_not_hydrologic_outlet', 'scope': 'independent_fine_alternative_not_added_to_coarse_or_certified_as_full_forest', 'full_window_upstream_area_m2': float(arrays['contributing_area_m2'].flat[chain[0]])}
        attempts.append({'chain_cells': chain, 'status': accepted['status'], 'reason_flags': []})
        return {'accepted': accepted, 'attempts': attempts, 'fine_cells': spent, 'max_attempts': MAX_ATTEMPTS, 'max_chain_segments': MAX_CHAIN_SEGMENTS}
    return {'accepted': None, 'attempts': attempts, 'fine_cells': spent, 'max_attempts': MAX_ATTEMPTS, 'max_chain_segments': MAX_CHAIN_SEGMENTS}

def validate_fine_chain(chain, geometry):
    """Static original-source sampling and cut equations; never select or prepare."""
    source, metadata = (geometry['arrays'], geometry['metadata'])
    arrays = chain['arrays']
    expected_keys = {'world_x_m', 'world_z_m', 'H0_m', 'H1_m', 'H2_m', 'cut_depth_m', 'across_m', 'along_m', 'chain_cells', 'quadrature_area_m2', 'shared_node_section_rows'}
    if set(arrays) != expected_keys or chain['fine_spacing_m'] != FINE_SPACING_M or chain['width_m'] != WIDTH_M:
        raise ValueError('fixed fine chain schema')
    cells = arrays['chain_cells']
    if cells.dtype != _i5_np.dtype('int64') or cells.ndim != 1 or (not MIN_CHAIN_SEGMENTS <= cells.size - 1 <= MAX_CHAIN_SEGMENTS):
        raise ValueError('bounded chain node identities')
    if chain['segments'] != cells.size - 1 or chain['length_m'] != (cells.size - 1) * metadata['spacing_m'] or chain['receiving_cell'] != int(cells[-1]):
        raise ValueError('fine metadata segment/length/receiver identity')
    if (cells < 0).any() or (cells >= source['H0_m'].size).any() or (not _i5_np.array_equal(source['receiver'][cells[:-1]], cells[1:])):
        raise ValueError('fine chain source topology')
    width = source['H0_m'].shape[1]
    delta_rows = _i5_np.diff(cells // width)
    delta_columns = _i5_np.diff(cells % width)
    if (_i5_np.abs(delta_rows) + _i5_np.abs(delta_columns) != 1).any() or _i5_np.ptp(delta_rows) or _i5_np.ptp(delta_columns):
        raise ValueError('straight full-D4 chain required')
    if (source['lake_mask'].ravel()[cells] | source['protected_mask'].ravel()[cells] | ~source['accepted_mask'].ravel()[cells]).any():
        raise ValueError('fine chain source acceptance/protection')
    spacing = metadata['spacing_m']
    along = _i5_np.arange(int((cells.size - 1) * spacing / FINE_SPACING_M) + 1) * FINE_SPACING_M
    across = _i5_np.arange(int(WIDTH_M / FINE_SPACING_M) + 1) * FINE_SPACING_M - WIDTH_M / 2
    if along.size * across.size > MAX_FINE_CELLS:
        raise ValueError('fine chain resource limit')

    def equal(actual, expected, name):
        if actual.shape != expected.shape or not _i5_np.allclose(actual, expected, rtol=0.0, atol=1e-10):
            raise ValueError('static fine chain mismatch: ' + name)
    equal(arrays['along_m'], along, 'longitudinal coordinates')
    equal(arrays['across_m'], across, 'transverse coordinates')
    start_row, start_column = divmod(int(cells[0]), width)
    columns = start_column + along[:, None] / spacing * delta_columns[0] - across[None, :] / spacing * delta_rows[0]
    rows = start_row + along[:, None] / spacing * delta_rows[0] + across[None, :] / spacing * delta_columns[0]
    if (columns < 0).any() or (columns > width - 1).any() or (rows < 0).any() or (rows > source['H0_m'].shape[0] - 1).any():
        raise ValueError('fine chain leaves original sample')
    equal(arrays['world_x_m'], metadata['origin_m_xz'][0] + columns * spacing, 'source X')
    equal(arrays['world_z_m'], metadata['origin_m_xz'][1] + rows * spacing, 'source Z')
    nearest_rows = _i5_np.floor(rows + 0.5).astype(_i5_np.int64)
    nearest_columns = _i5_np.floor(columns + 0.5).astype(_i5_np.int64)
    if (source['protected_mask'][nearest_rows, nearest_columns] | source['lake_mask'][nearest_rows, nearest_columns] | ~source['accepted_mask'][nearest_rows, nearest_columns]).any():
        raise ValueError('full strip source protection/lake/acceptance mask')
    original = _mountain_fine_geometry_sample(source['H0_m'], columns, rows)
    equal(arrays['H0_m'], original, 'true bilinear H0')
    equal(arrays['H1_m'], original, 'unchanged fine H1')
    center_cut = _i5_np.interp(along, _i5_np.arange(cells.size) * spacing, source['cut_depth_m'].ravel()[cells])
    taper = 0.5 * (1 + _i5_np.cos(_i5_np.pi * across / (WIDTH_M / 2)))
    expected_cut = center_cut[:, None] * taper[None, :]
    equal(arrays['cut_depth_m'], expected_cut, 'cosine cut and shared node endpoints')
    equal(arrays['H2_m'], original - expected_cut, 'source-linked bed')
    weights = _i5_np.ones(original.shape)
    weights[0] *= 0.5
    weights[-1] *= 0.5
    weights[:, 0] *= 0.5
    weights[:, -1] *= 0.5
    equal(arrays['quadrature_area_m2'], weights * FINE_SPACING_M ** 2, 'unique quadrature')
    equal(arrays['shared_node_section_rows'], _i5_np.arange(1, cells.size - 1) * int(spacing / FINE_SPACING_M), 'shared section identities')
    center = original.shape[1] // 2
    if (_i5_np.diff(arrays['H2_m'][:, center]) > 1e-09).any() or (arrays['H2_m'] < arrays['H2_m'][:, center:center + 1] - 1e-09).any():
        raise ValueError('fine longitudinal or transverse geometry failure')
    volume = float((expected_cut * arrays['quadrature_area_m2']).sum())
    if abs(volume - chain['cut_volume_m3']) > 1e-09 or volume > metadata['budget']['max_cut_volume_m3'] or expected_cut.max() > metadata['budget']['max_total_cut_m']:
        raise ValueError('fine independent budget failure')
    return {'cut_volume_m3': volume, 'length_m': float(along[-1]), 'minimum_endpoint_bank_margin_m': float(_i5_np.min(_i5_np.minimum(arrays['H2_m'][:, 0], arrays['H2_m'][:, -1]) - arrays['H2_m'][:, center]))}
MAX_STEPS = 4096
MAX_SUPPORT = 250000
MAX_WORK = 2000000
CONDUCTANCE_M2_S = 0.01
MAX_DT_S = 10.0
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024

def fine_storage_support(chain):
    """Partition longitudinal quadrature exactly once across shared fine nodes."""
    from terrain_pipeline.lake import _hash as _i7__hash
    arrays = chain['arrays']
    bed = arrays['H2_m']
    area = arrays['quadrature_area_m2']
    if bed.shape != area.shape or bed.size > MAX_SUPPORT or (not _i7_np.isfinite(bed).all()) or (area <= 0).any():
        raise ValueError('invalid fine support/resource')
    nodes = chain['segments'] + 1
    rows = bed.shape[0]
    samples_per_segment = (rows - 1) // chain['segments']
    owner = _i7_np.minimum(_i7_np.floor(_i7_np.arange(rows) / samples_per_segment + 0.5).astype(_i7_np.int64), nodes - 1)
    beds = []
    weights = []
    offsets = [0]
    min_bed = _i7_np.zeros(nodes)
    max_stage = _i7_np.zeros(nodes)
    min_bank = _i7_np.zeros(nodes)
    event_counts = _i7_np.zeros(nodes, dtype=_i7_np.int64)
    for node in range(nodes):
        selected = owner == node
        values = bed[selected].ravel()
        support = area[selected].ravel()
        beds.append(values)
        weights.append(support)
        offsets.append(offsets[-1] + values.size)
        min_bed[node] = float(values.min())
        min_bank[node] = float(_i7_np.minimum(bed[selected, 0], bed[selected, -1]).min())
        max_stage[node] = min_bank[node] - 1e-06
        levels = _i7_np.unique(bed[selected][bed[selected] <= max_stage[node]])
        event_counts[node] = levels.size
        for level in levels:
            if _i7_ndimage.label(bed[selected] <= level, _i7_ndimage.generate_binary_structure(2, 1))[1] > 1:
                raise ValueError('fine support contains disconnected initial pools below valid banks')
    interfaces = _i7_np.flatnonzero(_i7_np.diff(owner) != 0)
    sill = _i7_np.r_[bed[0].min(), _i7_np.maximum(bed[interfaces].min(axis=1), bed[interfaces + 1].min(axis=1)), bed[-1].min()]
    return {'offsets': _i7_np.asarray(offsets, dtype=_i7_np.int64), 'beds_m': _i7_np.concatenate(beds), 'weights_m2': _i7_np.concatenate(weights), 'row_owner': owner, 'min_bed_m': min_bed, 'max_stage_m': max_stage, 'min_bank_m': min_bank, 'side_margin_m': min_bank - min_bed, 'interface_before_rows': interfaces.astype(_i7_np.int64), 'interface_sill_m': sill, 'single_pool_event_count': event_counts, 'source_H2_sha256': _i7__hash(bed), 'source_area_sha256': _i7__hash(area)}

def map_chain_upstream_runoff(geometry, chain, *, local_q_m3_s, cell_owner, hru_area_m2):
    """Full new-receiver donor subtree, excluding upstream lake storage shortcuts."""
    arrays = geometry['arrays']
    start = int(chain['arrays']['chain_cells'][0])
    upstream = _i7_np.zeros(arrays['receiver'].size, dtype=bool)
    upstream[start] = True
    for cell in arrays['order']:
        target = arrays['receiver'][cell]
        if target >= 0 and upstream[target]:
            upstream[cell] = True
    mask = upstream.reshape(arrays['H0_m'].shape)
    upstream_lakes = _i7_np.unique(arrays['lake_id'][mask])
    upstream_lakes = upstream_lakes[upstream_lakes > 0]
    counts = _i7_np.bincount(cell_owner[mask], minlength=hru_area_m2.size)
    q = local_q_m3_s @ (counts * geometry['metadata']['spacing_m'] ** 2 / hru_area_m2)
    return {'subtree_mask': mask, 'allocation_counts': counts, 'upstream_lake_ids': upstream_lakes, 'rainfall_only_instantaneous_local_q_m3_s': q, 'status': 'requires_upstream_lake_outflow_binding' if upstream_lakes.size else 'complete_dry_upstream_subtree', 'area_m2': float(mask.sum() * geometry['metadata']['spacing_m'] ** 2), 'limitation': 'instantaneous_local_runoff_sum_is_not_a_routed_lake_or_hillslope_hydrograph'}

def prepare_fine_storage(chain, geometry, *, initial_stage_m, local_q_m3_s, upstream_stage_m, tailwater_stage_m, dt_s, conductance_m2_s=CONDUCTANCE_M2_S):
    """Wet/dry sill gating and signed flux; donor-limited explicit volume update."""
    from terrain_pipeline.surface_domain import volume as _x0_volume
    from terrain_pipeline.surface_domain import _invert as _x1_invert
    validate_fine_chain(chain, geometry)
    support = fine_storage_support(chain)
    nodes = support['min_bed_m'].size
    if not isinstance(local_q_m3_s, _i7_np.ndarray) or local_q_m3_s.ndim != 2:
        raise ValueError('resource-checkable forcing required')
    steps = local_q_m3_s.shape[0]
    if not 1 <= steps <= MAX_STEPS or local_q_m3_s.shape[1] != nodes or steps * (nodes + support['beds_m'].size) > MAX_WORK:
        raise ValueError('fine dynamic resource ceiling')
    if isinstance(dt_s, bool) or not _i7_math.isfinite(dt_s) or (not 0 < dt_s <= MAX_DT_S) or (conductance_m2_s != CONDUCTANCE_M2_S):
        raise ValueError('fixed fine dynamic dt/conductance ceiling')
    initial = _i7_np.asarray(initial_stage_m)
    upstream = _i7_np.asarray(upstream_stage_m)
    tailwater = _i7_np.asarray(tailwater_stage_m)
    if initial.shape != (nodes,) or upstream.shape != (steps + 1,) or tailwater.shape != (steps + 1,):
        raise ValueError('explicit open seam heads required')
    if not all((_i7_np.isfinite(values).all() for values in (initial, upstream, tailwater, local_q_m3_s))) or (local_q_m3_s < 0).any():
        raise ValueError('invalid fine forcing')
    offsets, beds, weights = (support['offsets'], support['beds_m'], support['weights_m2'])
    stages = [initial.copy()]
    storage = _i7_np.array([_x0_volume(initial[index], beds[offsets[index]:offsets[index + 1]], weights[offsets[index]:offsets[index + 1]]) for index in range(nodes)])
    storages = [storage]
    fluxes = []
    ledgers = []
    failure = None
    if (initial < support['min_bed_m'] - 1e-09).any() or (initial > support['max_stage_m'] + 1e-09).any():
        failure = {'step': -1, 'reason': 'initial_outside_bed_or_bank'}
    for step in range(steps):
        if failure is not None:
            break
        current = stages[-1]
        heads = _i7_np.r_[upstream[step], current, tailwater[step]]
        sill = support['interface_sill_m']
        effective = _i7_np.maximum(heads[:-1], sill) - _i7_np.maximum(heads[1:], sill)
        flux = conductance_m2_s * effective
        for node in range(nodes):
            outgoing = max(0.0, -flux[node]) + max(0.0, flux[node + 1])
            available = storage[node] + dt_s * local_q_m3_s[step, node]
            if outgoing * dt_s > available and outgoing > 0:
                factor = available / (outgoing * dt_s)
                if flux[node] < 0:
                    flux[node] *= factor
                if flux[node + 1] > 0:
                    flux[node + 1] *= factor
        after = storage + dt_s * (local_q_m3_s[step] + flux[:-1] - flux[1:])
        if (after < -1e-10).any():
            failure = {'step': step, 'reason': 'negative_storage'}
            break
        after = _i7_np.maximum(after, 0.0)
        next_stage = _i7_np.array([_x1_invert(float(after[index]), beds[offsets[index]:offsets[index + 1]], weights[offsets[index]:offsets[index + 1]]) for index in range(nodes)])
        if (next_stage > support['max_stage_m'] + 1e-09).any():
            failure = {'step': step, 'reason': 'resolved_bank_overtopped', 'nodes': _i7_np.flatnonzero(next_stage > support['max_stage_m'] + 1e-09).tolist()}
            break
        residual = after.sum() - storage.sum() - dt_s * (local_q_m3_s[step].sum() + flux[0] - flux[-1])
        ledgers.append([storage.sum(), dt_s * local_q_m3_s[step].sum(), dt_s * flux[0], dt_s * flux[-1], after.sum(), residual])
        stages.append(next_stage)
        storages.append(after)
        fluxes.append(flux)
        storage = after
    return {'status': 'fine_storage_completed' if failure is None else 'fine_storage_refused', 'scope': 'fine_local_chain_engineering_storage_conductance_not_Saint_Venant_or_complete_forest', 'failure': failure, 'committed_steps': len(fluxes), 'requested_steps': steps, 'dt_s': float(dt_s), 'conductance_m2_s': conductance_m2_s, 'support': support, 'arrays': {'initial_stage_m': initial.copy(), 'local_q_m3_s': local_q_m3_s.copy(), 'upstream_stage_m': upstream.copy(), 'tailwater_stage_m': tailwater.copy(), 'stage_m': _i7_np.asarray(stages), 'storage_m3': _i7_np.asarray(storages), 'qedges_m3_s': _i7_np.asarray(fluxes).reshape(-1, nodes + 1), 'ledger_m3': _i7_np.asarray(ledgers).reshape(-1, 6)}}

def validate_fine_storage(saved, chain, geometry):
    """Static source geometry, V(h), signed local flux and per-node continuity."""
    from terrain_pipeline.lake import _hash as _i7__hash
    support = saved['support']
    validate_fine_chain(chain, geometry)
    source = chain['arrays']
    if support['source_H2_sha256'] != _i7__hash(source['H2_m']) or support['source_area_sha256'] != _i7__hash(source['quadrature_area_m2']):
        raise ValueError('fine support source binding')
    owner = support['row_owner']
    rows = source['H2_m'].shape[0]
    nodes = chain['segments'] + 1
    expected_owner = _i7_np.minimum(_i7_np.floor(_i7_np.arange(rows) / ((rows - 1) // chain['segments']) + 0.5).astype(_i7_np.int64), nodes - 1)
    if not _i7_np.array_equal(owner, expected_owner):
        raise ValueError('fine row partition forged')
    offsets = support['offsets']
    if offsets.shape != (nodes + 1,) or offsets.dtype != _i7_np.dtype('int64') or offsets[0] != 0 or (offsets[-1] != support['beds_m'].size) or (_i7_np.diff(offsets) <= 0).any():
        raise ValueError('fine support offsets')
    for node in range(nodes):
        values = source['H2_m'][owner == node].ravel()
        weights = source['quadrature_area_m2'][owner == node].ravel()
        begin, end = offsets[node:node + 2]
        if not _i7_np.array_equal(support['beds_m'][begin:end], values) or not _i7_np.array_equal(support['weights_m2'][begin:end], weights):
            raise ValueError('fine saved support local source sampling')
        bank = float(_i7_np.minimum(source['H2_m'][owner == node, 0], source['H2_m'][owner == node, -1]).min())
        if support['min_bed_m'][node] != values.min() or support['min_bank_m'][node] != bank or support['max_stage_m'][node] != bank - 1e-06:
            raise ValueError('fine saved bank envelope')
        if support['side_margin_m'][node] != bank - values.min():
            raise ValueError('fine side margin forged')
        local_bed = source['H2_m'][owner == node]
        levels = _i7_np.unique(local_bed[local_bed <= bank - 1e-06])
        if support['single_pool_event_count'][node] != levels.size:
            raise ValueError('fine event certificate forged')
        for level in levels:
            if _i7_ndimage.label(local_bed <= level, _i7_ndimage.generate_binary_structure(2, 1))[1] > 1:
                raise ValueError('fine sub-bank initial pools disconnected')
    interfaces = _i7_np.flatnonzero(_i7_np.diff(owner) != 0)
    bed = source['H2_m']
    sill = _i7_np.r_[bed[0].min(), _i7_np.maximum(bed[interfaces].min(axis=1), bed[interfaces + 1].min(axis=1)), bed[-1].min()]
    if not _i7_np.array_equal(support['interface_before_rows'], interfaces) or not _i7_np.array_equal(support['interface_sill_m'], sill):
        raise ValueError('real shared-section sill forgery')
    arrays = saved['arrays']
    requested = saved['requested_steps']
    committed = saved['committed_steps']
    if type(requested) is not int or type(committed) is not int or (not 0 <= committed <= requested <= MAX_STEPS):
        raise ValueError('fine step metadata')
    if requested * (nodes + support['beds_m'].size) > MAX_WORK or support['beds_m'].size > MAX_SUPPORT:
        raise ValueError('fine static work ceiling')
    if saved['status'] == 'fine_storage_completed':
        if committed != requested or saved['failure'] is not None:
            raise ValueError('fine completed status forgery')
    elif saved['status'] == 'fine_storage_refused':
        if saved['failure'] is None or committed == requested or saved['failure']['step'] not in (-1, committed):
            raise ValueError('fine failure status forgery')
    else:
        raise ValueError('fine unknown status')
    specs = {'initial_stage_m': (nodes,), 'local_q_m3_s': (requested, nodes), 'upstream_stage_m': (requested + 1,), 'tailwater_stage_m': (requested + 1,), 'stage_m': (committed + 1, nodes), 'storage_m3': (committed + 1, nodes), 'qedges_m3_s': (committed, nodes + 1), 'ledger_m3': (committed, 6)}
    if set(arrays) != set(specs):
        raise ValueError('fine state exact schema')
    for key, shape in specs.items():
        value = arrays[key]
        if not isinstance(value, _i7_np.ndarray) or value.dtype != _i7_np.dtype('float64') or value.shape != shape or (not _i7_np.isfinite(value).all()):
            raise ValueError('fine state dtype/shape/finite: ' + key)
    stages, storage = (arrays['stage_m'], arrays['storage_m3'])
    if stages.shape != storage.shape or stages.shape[0] != saved['committed_steps'] + 1:
        raise ValueError('fine state shapes')
    if not _i7_np.array_equal(stages[0], arrays['initial_stage_m']):
        raise ValueError('fine initial stage mismatch')
    offsets, beds, weights = (support['offsets'], support['beds_m'], support['weights_m2'])
    for node in range(stages.shape[1]):
        volumes = _i7_np.maximum(stages[:, node, None] - beds[None, offsets[node]:offsets[node + 1]], 0) @ weights[offsets[node]:offsets[node + 1]]
        if not _i7_np.allclose(storage[:, node], volumes, rtol=1e-12, atol=1e-09):
            raise ValueError('fine V(h) forgery')
    initial_failure = saved['failure'] is not None and saved['failure']['step'] == -1
    if ((stages > support['max_stage_m'] + 1e-09).any() or (stages < support['min_bed_m'] - 1e-09).any()) and (not initial_failure):
        raise ValueError('fine bank/negative water')
    if (storage < 0).any() or (arrays['local_q_m3_s'] < 0).any():
        raise ValueError('fine negative quantity')
    steps = saved['committed_steps']
    flux = arrays['qedges_m3_s']
    if saved['conductance_m2_s'] != CONDUCTANCE_M2_S or not 0 < saved['dt_s'] <= MAX_DT_S:
        raise ValueError('fixed dynamic identity')
    heads = _i7_np.column_stack((arrays['upstream_stage_m'][:steps], stages[:-1], arrays['tailwater_stage_m'][:steps]))
    expected_flux = CONDUCTANCE_M2_S * (_i7_np.maximum(heads[:, :-1], sill) - _i7_np.maximum(heads[:, 1:], sill))
    for node in range(nodes):
        outgoing = _i7_np.maximum(0.0, -expected_flux[:, node]) + _i7_np.maximum(0.0, expected_flux[:, node + 1])
        available = storage[:-1, node] + saved['dt_s'] * arrays['local_q_m3_s'][:steps, node]
        limited = outgoing * saved['dt_s'] > available
        factor = _i7_np.ones(steps)
        factor[limited] = available[limited] / (outgoing[limited] * saved['dt_s'])
        left_negative = expected_flux[:, node] < 0
        right_positive = expected_flux[:, node + 1] > 0
        expected_flux[left_negative, node] *= factor[left_negative]
        expected_flux[right_positive, node + 1] *= factor[right_positive]
    if not _i7_np.allclose(flux, expected_flux, rtol=1e-12, atol=1e-12):
        raise ValueError('signed wet-connected limited flux forged')
    residual = _i7_np.diff(storage, axis=0) - saved['dt_s'] * (arrays['local_q_m3_s'][:steps] + flux[:, :-1] - flux[:, 1:])
    if not _i7_np.allclose(residual, 0, rtol=0, atol=1e-09):
        raise ValueError('fine local continuity forgery')
    expected_ledger = _i7_np.column_stack((storage[:-1].sum(axis=1), saved['dt_s'] * arrays['local_q_m3_s'][:steps].sum(axis=1), saved['dt_s'] * flux[:, 0], saved['dt_s'] * flux[:, -1], storage[1:].sum(axis=1), storage[1:].sum(axis=1) - storage[:-1].sum(axis=1) - saved['dt_s'] * (arrays['local_q_m3_s'][:steps].sum(axis=1) + flux[:, 0] - flux[:, -1])))
    if not _i7_np.allclose(arrays['ledger_m3'], expected_ledger, rtol=0.0, atol=1e-09):
        raise ValueError('fine ledger component forgery')
    return {'max_node_residual_m3': float(_i7_np.abs(residual).max(initial=0)), 'minimum_bank_margin_m': float(_i7_np.min(support['side_margin_m'])), 'final_storage_m3': float(storage[-1].sum())}

def save_fine_storage(path, saved, chain, geometry):
    from terrain_pipeline.lake import _hash as _i7__hash
    from terrain_pipeline.lake import depression_json as _i7__json
    validate_fine_storage(saved, chain, geometry)
    metadata = {key: value for key, value in saved.items() if key not in ('arrays', 'support')}
    support_meta = {key: value for key, value in saved['support'].items() if not isinstance(value, _i7_np.ndarray)}
    payload = {'state__' + key: value for key, value in saved['arrays'].items()}
    payload.update({'support__' + key: value for key, value in saved['support'].items() if isinstance(value, _i7_np.ndarray)})
    manifest = {'metadata': metadata, 'support_metadata': support_meta, 'geometry_source_binding': geometry['metadata']['source_binding'], 'hashes': {key: _i7__hash(value) for key, value in payload.items()}}
    encoded = _i7__json(manifest).encode('ascii')
    if len(encoded) > 65536 or sum((value.nbytes for value in payload.values())) > MAX_ARCHIVE_BYTES:
        raise ValueError('fine storage publication resource ceiling')
    target = _i7_Path(path)
    if target.exists():
        raise FileExistsError(target)
    descriptor, temporary = _i7_tempfile.mkstemp(prefix='.mountain-fine-storage-', suffix='.npz', dir=target.parent)
    try:
        with _i7_os.fdopen(descriptor, 'wb') as stream:
            _i7_np.savez_compressed(stream, manifest=_i7_np.frombuffer(encoded, dtype=_i7_np.uint8), **payload)
            stream.flush()
            _i7_os.fsync(stream.fileno())
        _i7_os.link(temporary, target)
    finally:
        _i7_os.unlink(temporary)

def load_fine_storage(path, chain, geometry):
    from terrain_pipeline.lake import _hash as _i7__hash
    state_keys = {'initial_stage_m', 'local_q_m3_s', 'upstream_stage_m', 'tailwater_stage_m', 'stage_m', 'storage_m3', 'qedges_m3_s', 'ledger_m3'}
    support_keys = {'offsets', 'beds_m', 'weights_m2', 'row_owner', 'min_bed_m', 'max_stage_m', 'min_bank_m', 'side_margin_m', 'interface_before_rows', 'interface_sill_m', 'single_pool_event_count'}
    names = {'state__' + key + '.npy' for key in state_keys} | {'support__' + key + '.npy' for key in support_keys} | {'manifest.npy'}
    with open(path, 'rb') as stream:
        with _i7_zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            if len(members) != len(names) or {member.filename for member in members} != names:
                raise ValueError('strict fine storage archive schema')
            if sum((member.file_size for member in members)) > MAX_ARCHIVE_BYTES:
                raise ValueError('fine storage archive resource ceiling')
            headers = {}
            for member in members:
                with archive.open(member) as item:
                    if _i7_np.lib.format.read_magic(item) != (1, 0):
                        raise ValueError('fine NPY version')
                    shape, fortran, dtype = _i7_np.lib.format.read_array_header_1_0(item)
                    key = member.filename[:-4]
                    headers[key] = shape
                    expected_dtype = _i7_np.dtype('uint8' if key == 'manifest' else 'int64' if key in {'support__' + name for name in ('offsets', 'row_owner', 'interface_before_rows', 'single_pool_event_count')} else 'float64')
                    if dtype != expected_dtype or fortran or _i7_math.prod(shape) * dtype.itemsize + item.tell() != member.file_size:
                        raise ValueError('fine header dtype/size')
                    if len(shape) not in (1, 2) or _i7_math.prod(shape) > max(MAX_SUPPORT, MAX_STEPS * 17):
                        raise ValueError('fine header dimensions')
                    if key == 'manifest' and shape[0] > 65536:
                        raise ValueError('fine manifest limit')
            nodes = chain['segments'] + 1
            if not 4 <= nodes <= 17:
                raise ValueError('fine node ceiling')
            requested_shape = headers['state__local_q_m3_s']
            state_shape = headers['state__stage_m']
            if len(requested_shape) != 2 or len(state_shape) != 2:
                raise ValueError('fine forcing/state header dimensions')
            requested = requested_shape[0]
            committed = state_shape[0] - 1
            if not 1 <= requested <= MAX_STEPS or not 0 <= committed <= requested:
                raise ValueError('fine steps header ceiling')
            rows, columns = chain['arrays']['H2_m'].shape
            exact_shapes = {'state__initial_stage_m': (nodes,), 'state__local_q_m3_s': (requested, nodes), 'state__upstream_stage_m': (requested + 1,), 'state__tailwater_stage_m': (requested + 1,), 'state__stage_m': (committed + 1, nodes), 'state__storage_m3': (committed + 1, nodes), 'state__qedges_m3_s': (committed, nodes + 1), 'state__ledger_m3': (committed, 6), 'support__offsets': (nodes + 1,), 'support__beds_m': (rows * columns,), 'support__weights_m2': (rows * columns,), 'support__row_owner': (rows,), 'support__interface_before_rows': (nodes - 1,), 'support__interface_sill_m': (nodes + 1,)}
            exact_shapes.update({'support__' + key: (nodes,) for key in ('min_bed_m', 'max_stage_m', 'min_bank_m', 'side_margin_m', 'single_pool_event_count')})
            for key, shape in exact_shapes.items():
                if headers[key] != shape:
                    raise ValueError('fine exact header shape: ' + key)
        stream.seek(0)
        with _i7_np.load(stream, allow_pickle=False) as archive:
            manifest = _i7_json.loads(archive['manifest'].tobytes().decode('ascii'))
            arrays = {key: archive[key].copy() for key in archive.files if key != 'manifest'}
    if manifest['geometry_source_binding'] != geometry['metadata']['source_binding'] or set(manifest['hashes']) != set(arrays):
        raise ValueError('fine source external trust mismatch')
    for key, value in arrays.items():
        if manifest['hashes'][key] != _i7__hash(value):
            raise ValueError('fine integrity mismatch')
    saved = dict(manifest['metadata'])
    saved['arrays'] = {key[len('state__'):]: value for key, value in arrays.items() if key.startswith('state__')}
    saved['support'] = dict(manifest['support_metadata'], **{key[len('support__'):]: value for key, value in arrays.items() if key.startswith('support__')})
    validate_fine_storage(saved, chain, geometry)
    for branch in (saved['arrays'], saved['support']):
        for key, value in branch.items():
            if isinstance(value, _i7_np.ndarray):
                branch[key] = _i7_np.frombuffer(value.tobytes(), dtype=value.dtype).reshape(value.shape)
    return saved

def export_fine_mesh(chain, saved, geometry):
    """No solver or geometry preparation: saved water supports retain exact weights."""
    from terrain_pipeline.lake import _hash as _i6__hash
    validate_fine_chain(chain, geometry)
    validation = validate_fine_storage(saved, chain, geometry)
    source = chain['arrays']
    rows, columns = source['H2_m'].shape
    grid = _i6_np.arange(rows * columns, dtype=_i6_np.int64).reshape(rows, columns)
    lower_left = grid[:-1, :-1].ravel()
    lower_right = grid[:-1, 1:].ravel()
    upper_left = grid[1:, :-1].ravel()
    upper_right = grid[1:, 1:].ravel()
    triangles = _i6_np.concatenate((_i6_np.column_stack((lower_left, lower_right, upper_right)), _i6_np.column_stack((lower_left, upper_right, upper_left))), axis=0)
    origin = _i6_np.array([source['world_x_m'].flat[0], float(source['H0_m'].min()), source['world_z_m'].flat[0]])
    original = _i6_np.column_stack((source['world_x_m'].ravel(), source['H0_m'].ravel(), source['world_z_m'].ravel()))
    bed = original.copy()
    bed[:, 1] = source['H2_m'].ravel()
    local_bed = bed - origin
    local_original = original - origin
    area2 = _i6_np.linalg.norm(_i6_np.cross(local_bed[triangles[:, 1]] - local_bed[triangles[:, 0]], local_bed[triangles[:, 2]] - local_bed[triangles[:, 0]]), axis=1)
    if (area2 <= 0).any():
        raise ValueError('degenerate fine mesh triangle')
    normals = _i6_np.cross(local_bed[triangles[:, 1]] - local_bed[triangles[:, 0]], local_bed[triangles[:, 2]] - local_bed[triangles[:, 0]])
    if (normals[:, 1] <= 0).any():
        raise ValueError('bed mesh triangle winding is not upward')
    support = saved['support']
    row_owner = support['row_owner']
    owner = _i6_np.repeat(row_owner, columns)
    stage = saved['arrays']['stage_m'][:, owner]
    depth = _i6_np.maximum(stage - bed[None, :, 1], 0.0)
    weights = source['quadrature_area_m2'].ravel()
    water_volume = depth @ weights
    solver_volume = saved['arrays']['storage_m3'].sum(axis=1)
    difference = water_volume - solver_volume
    if not _i6_np.allclose(difference, 0.0, rtol=0.0, atol=1e-08):
        raise ValueError('wet prism support differs from solver V(h)')
    shared_rows = source['shared_node_section_rows']
    shared_ids = grid[shared_rows].copy()
    return {'arrays': {'origin_world_xyz_m': origin, 'vertices_H0_local_xyz_m': local_original, 'vertices_H2_local_xyz_m': local_bed, 'triangles': triangles, 'shared_section_vertex_ids': shared_ids, 'support_owner': owner, 'support_area_m2': weights, 'stage_m': stage, 'water_depth_m': depth, 'wet_mask': depth > 0.0, 'water_volume_m3': water_volume, 'solver_volume_m3': solver_volume, 'display_volume_difference_m3': difference, 'time_s': _i6_np.arange(stage.shape[0], dtype=_i6_np.float64) * saved['dt_s'], 'qedges_m3_s': saved['arrays']['qedges_m3_s'].copy(), 'ledger_m3': saved['arrays']['ledger_m3'].copy()}, 'metadata': {'schema': 'mountain-fine-wet-support-prisms-v1', 'source_binding': geometry['metadata']['source_binding'], 'fine_H0_sha256': _i6__hash(source['H0_m']), 'fine_H2_sha256': _i6__hash(source['H2_m']), 'saved_stage_sha256': _i6__hash(saved['arrays']['stage_m']), 'water_representation': 'weighted_discrete_wet_support_prisms_not_interpolated_triangle_water_surface', 'coordinates': 'local_X_Y_elevation_Z_metres_plus_saved_origin_no_hidden_vertical_exaggeration', 'upstream_boundary': 'explicit_artificial_local_head', 'downstream_boundary': 'explicit_artificial_tailwater', 'scope': saved['scope'], 'state_count': int(stage.shape[0]), 'committed_steps': saved['committed_steps'], 'failure': saved['failure'], 'max_display_volume_difference_m3': float(_i6_np.abs(difference).max(initial=0)), 'validation': validation}}
SCHEMA = 'mountain-explicit-tributary-manning-geometry-v1'
MOUNTAIN_MANNING_GEOMETRY_MAX_SUPPORT = 1001
CHAIN_CELLS = (219142, 219143, 219144, 219145)
GROUP = 1378
SHALLOW_CUT_M = 0.25
MAX_CUT_M = 2.0
MAX_CUT_VOLUME_M3 = 200000.0
ARRAY_SHAPES = {'chain_cells': (4,), 'along_m': (91,), 'across_m': (11,), 'world_x_m': (91, 11), 'world_z_m': (91, 11), 'H0_m': (91, 11), 'H2_m': (91, 11), 'cut_depth_m': (91, 11), 'support_area_m2': (91, 11), 'row_owner': (91,), 'interface_before_rows': (3,), 'interface_section_bed_m': (5, 11), 'interface_crest_m': (5,), 'min_bed_m': (4,), 'max_stage_m': (4,), 'node_along_m': (4,), 'edge_distance_m': (5,)}

def prepare_tributary_geometry(geometry, *, chain_cells=CHAIN_CELLS, group=GROUP):
    """Explicit fixed study selection; no edits to coarse flowlines or accepted mask."""
    from terrain_pipeline.lake import _hash as _i9__hash
    source, metadata = (geometry['arrays'], geometry['metadata'])
    if tuple(chain_cells) != CHAIN_CELLS or group != GROUP or metadata['spacing_m'] != 30.0:
        raise ValueError('fixed independent tributary identity required')
    cells = _i9_np.asarray(chain_cells, dtype=_i9_np.int64)
    width = source['H0_m'].shape[1]
    along = _i9_np.arange(91.0, dtype=_i9_np.float64)
    across = _i9_np.arange(-5.0, 6.0, dtype=_i9_np.float64)
    row, column = divmod(int(cells[0]), width)
    delta_row = cells[1] // width - row
    delta_column = cells[1] % width - column
    grid_rows = row + along[:, None] / 30 * delta_row + across[None, :] / 30 * delta_column
    grid_columns = column + along[:, None] / 30 * delta_column - across[None, :] / 30 * delta_row
    original = _mountain_fine_geometry_sample(source['H0_m'], grid_columns, grid_rows)
    cut = _i9_np.broadcast_to(SHALLOW_CUT_M * (0.5 * (1 + _i9_np.cos(_i9_np.pi * across / 5)))[None, :], original.shape).copy()
    weights = _i9_np.ones(original.shape)
    weights[0] *= 0.5
    weights[-1] *= 0.5
    weights[:, 0] *= 0.5
    weights[:, -1] *= 0.5
    row_owner = _i9_np.minimum(_i9_np.floor(along / 30 + 0.5).astype(_i9_np.int64), 3)
    interfaces = _i9_np.flatnonzero(_i9_np.diff(row_owner) != 0)
    bed = original - cut
    minimum = _i9_np.array([bed[row_owner == node].min() for node in range(4)])
    bank = _i9_np.array([_i9_np.minimum(bed[row_owner == node, 0], bed[row_owner == node, -1]).min() for node in range(4)])
    section_bed = _i9_np.vstack((bed[0], _i9_np.maximum(bed[interfaces], bed[interfaces + 1]), bed[-1]))
    arrays = {'chain_cells': cells, 'along_m': along, 'across_m': across, 'world_x_m': metadata['origin_m_xz'][0] + grid_columns * 30, 'world_z_m': metadata['origin_m_xz'][1] + grid_rows * 30, 'H0_m': original, 'H2_m': bed, 'cut_depth_m': cut, 'support_area_m2': weights, 'row_owner': row_owner, 'interface_before_rows': interfaces, 'interface_section_bed_m': section_bed, 'interface_crest_m': section_bed.min(axis=1), 'min_bed_m': minimum, 'max_stage_m': bank - 1e-06, 'node_along_m': _i9_np.array([0.0, 30.0, 60.0, 90.0]), 'edge_distance_m': _i9_np.array([15.0, 30.0, 30.0, 30.0, 15.0])}
    record = {'arrays': arrays, 'metadata': {'schema': SCHEMA, 'group': group, 'source_binding': metadata['source_binding'], 'source_H0_sha256': _i9__hash(source['H0_m']), 'source_receiver_sha256': _i9__hash(source['receiver']), 'origin_m_xz': metadata['origin_m_xz'], 'fine_spacing_m': 1.0, 'width_m': WIDTH_M, 'shallow_cut_m': SHALLOW_CUT_M, 'cut_volume_m3': float((cut * weights).sum()), 'scope': 'explicit_independent_small_tributary_study_not_legacy_1km2_channel_or_construction_certificate', 'selection': 'preflight_max_solved_upstream_pool_count_then_complete_subtree_area_then_flat_id', 'coarse_channel_threshold_unchanged_m2': 1000000.0, 'subcell_limitation': '1m_bilinear_interpolation_of_30m_TD_not_new_terrain_resolution'}}
    validate_tributary_geometry(record, geometry)
    return record

def validate_tributary_geometry(record, geometry):
    """Static original samples, full strip masks, sections and bank-limited wet events."""
    from terrain_pipeline.lake import _hash as _i9__hash
    arrays, meta = (record['arrays'], record['metadata'])
    source, source_meta = (geometry['arrays'], geometry['metadata'])
    if set(arrays) != set(ARRAY_SHAPES):
        raise ValueError('exact tributary geometry schema')
    for key, shape in ARRAY_SHAPES.items():
        if not isinstance(arrays[key], _i9_np.ndarray) or arrays[key].shape != shape:
            raise ValueError('tributary exact shape: ' + key)
    if meta['schema'] != SCHEMA or meta['group'] != GROUP or meta['source_binding'] != source_meta['source_binding'] or (meta['source_H0_sha256'] != _i9__hash(source['H0_m'])) or (meta['source_receiver_sha256'] != _i9__hash(source['receiver'])):
        raise ValueError('independent geometry source binding mismatch')
    if meta['origin_m_xz'] != source_meta['origin_m_xz'] or meta['fine_spacing_m'] != 1.0 or meta['width_m'] != WIDTH_M or (meta['shallow_cut_m'] != SHALLOW_CUT_M) or (meta['coarse_channel_threshold_unchanged_m2'] != 1000000.0) or (meta['scope'] != 'explicit_independent_small_tributary_study_not_legacy_1km2_channel_or_construction_certificate'):
        raise ValueError('fixed tributary parameter/scope identity')
    cells = arrays['chain_cells']
    if not _i9_np.array_equal(cells, CHAIN_CELLS) or cells.dtype != _i9_np.dtype('int64') or (not _i9_np.array_equal(source['receiver'][cells[:-1]], cells[1:])):
        raise ValueError('fixed selected chain topology')
    if not _i9_np.array_equal(source['outlet_owner'].ravel()[cells], _i9_np.full(4, GROUP)):
        raise ValueError('chain leaves complete contribution group')
    if arrays['H0_m'].shape != (91, 11) or arrays['H0_m'].size > MOUNTAIN_MANNING_GEOMETRY_MAX_SUPPORT:
        raise ValueError('independent strip resource ceiling')
    for key, value in arrays.items():
        dtype = _i9_np.dtype('int64' if key in ('chain_cells', 'row_owner', 'interface_before_rows') else 'float64')
        if not isinstance(value, _i9_np.ndarray) or value.dtype != dtype or (not _i9_np.isfinite(value).all()):
            raise ValueError('typed finite tributary arrays required')
    origin_x, origin_z = source_meta['origin_m_xz']
    grid_columns = (arrays['world_x_m'] - origin_x) / 30
    grid_rows = (arrays['world_z_m'] - origin_z) / 30
    if (grid_columns < 0).any() or (grid_columns > source['H0_m'].shape[1] - 1).any() or (grid_rows < 0).any() or (grid_rows > source['H0_m'].shape[0] - 1).any():
        raise ValueError('strip exceeds original source')
    row, column = divmod(CHAIN_CELLS[0], source['H0_m'].shape[1])
    expected_columns = _i9_np.broadcast_to(column + _i9_np.arange(91.0)[:, None] / 30, (91, 11))
    expected_rows = _i9_np.broadcast_to(row + _i9_np.arange(-5.0, 6.0)[None, :] / 30, (91, 11))

    def equal(actual, expected, name):
        if actual.shape != expected.shape or not _i9_np.allclose(actual, expected, atol=1e-10, rtol=0):
            raise ValueError('static tributary mismatch: ' + name)
    equal(grid_columns, expected_columns, 'source X coordinate')
    equal(grid_rows, expected_rows, 'source Z coordinate')
    equal(arrays['along_m'], _i9_np.arange(91.0), 'along')
    equal(arrays['across_m'], _i9_np.arange(-5.0, 6.0), 'across')
    original = _mountain_fine_geometry_sample(source['H0_m'], grid_columns, grid_rows)
    equal(arrays['H0_m'], original, 'original sampled H0')
    expected_cut = _i9_np.broadcast_to(0.25 * (0.5 * (1 + _i9_np.cos(_i9_np.pi * arrays['across_m'] / 5)))[None, :], original.shape)
    equal(arrays['cut_depth_m'], expected_cut, 'fixed cosine shallow cut')
    equal(arrays['H2_m'], original - expected_cut, 'original source bed')
    nearest_rows = _i9_np.floor(grid_rows + 0.5).astype(_i9_np.int64)
    nearest_columns = _i9_np.floor(grid_columns + 0.5).astype(_i9_np.int64)
    if ((source['outlet_owner'][nearest_rows, nearest_columns] != GROUP) | source['lake_mask'][nearest_rows, nearest_columns] | source['protected_mask'][nearest_rows, nearest_columns]).any():
        raise ValueError('full strip leaves group or crosses lake/protection')
    owner = _i9_np.minimum(_i9_np.floor(_i9_np.arange(91.0) / 30 + 0.5).astype(_i9_np.int64), 3)
    equal(arrays['row_owner'], owner, 'support partition')
    weights = _i9_np.ones(original.shape)
    weights[0] *= 0.5
    weights[-1] *= 0.5
    weights[:, 0] *= 0.5
    weights[:, -1] *= 0.5
    equal(arrays['support_area_m2'], weights, 'unique support quadrature')
    bed = arrays['H2_m']
    if (_i9_np.diff(bed[:, 5]) > 1e-09).any() or (bed < bed[:, 5:6] - 1e-09).any():
        raise ValueError('longitudinal or transverse bed not legal')
    interfaces = _i9_np.flatnonzero(_i9_np.diff(owner) != 0)
    equal(arrays['interface_before_rows'], interfaces, 'shared interface rows')
    sections = _i9_np.vstack((bed[0], _i9_np.maximum(bed[interfaces], bed[interfaces + 1]), bed[-1]))
    equal(arrays['interface_section_bed_m'], sections, 'real conservative section crest')
    equal(arrays['interface_crest_m'], sections.min(axis=1), 'interface crest')
    for node in range(4):
        local_bed = bed[owner == node]
        bank = float(_i9_np.minimum(local_bed[:, 0], local_bed[:, -1]).min()) - 1e-06
        if arrays['min_bed_m'][node] != local_bed.min() or arrays['max_stage_m'][node] != bank:
            raise ValueError('bank or bed certificate forged')
        for level in _i9_np.unique(local_bed[local_bed <= bank]):
            if _i9_ndimage.label(local_bed <= level, _i9_ndimage.generate_binary_structure(2, 1))[1] > 1:
                raise ValueError('support wet events disconnected')
    equal(arrays['node_along_m'], _i9_np.array([0.0, 30.0, 60.0, 90.0]), 'node positions')
    equal(arrays['edge_distance_m'], _i9_np.array([15.0, 30.0, 30.0, 30.0, 15.0]), 'diffusive distances')
    volume = float((expected_cut * weights).sum())
    if volume != meta['cut_volume_m3'] or volume > MAX_CUT_VOLUME_M3 or expected_cut.max() > MAX_CUT_M:
        raise ValueError('independent cut budget')
    return {'cut_volume_m3': volume, 'minimum_bank_margin_m': float(_i9_np.min(arrays['max_stage_m'] - arrays['min_bed_m'])), 'scope': meta['scope']}

def section_hydraulics(across_m, bed_m, stage_m):
    """Exact clipped linear transverse segments: wetted A, P, R and top width."""
    depth = stage_m - bed_m
    lengths = _i9_np.diff(across_m)
    left = depth[:-1]
    right = depth[1:]
    both = (left > 0) & (right > 0)
    one = (left > 0) ^ (right > 0)
    fraction = _i9_np.zeros(lengths.size)
    fraction[both] = 1.0
    fraction[one] = _i9_np.maximum(left[one], right[one]) / _i9_np.maximum(_i9_np.abs(left[one] - right[one]), 1e-30)
    area = float(_i9_np.sum(lengths[both] * (left[both] + right[both]) * 0.5) + _i9_np.sum(lengths[one] * fraction[one] * _i9_np.maximum(left[one], right[one]) * 0.5))
    perimeter = float(_i9_np.sum(_i9_np.hypot(lengths, _i9_np.diff(bed_m)) * fraction))
    top_width = float(_i9_np.dot(lengths, fraction))
    return {'area_m2': area, 'wetted_perimeter_m': perimeter, 'hydraulic_radius_m': area / perimeter if perimeter > 0 else 0.0, 'top_width_m': top_width}

def bind_saved_releases(coupling, source, topology, geometry, selection, record, *, dt_s):
    """No model advancement, bare accumulated runoff, or invented A river water level."""
    from terrain_pipeline.lake import validate_coupling as _i8_validate_coupling
    from terrain_pipeline.common_infra import identity as _i8_identity
    validate_tributary_geometry(record, geometry)
    _i8_validate_coupling(coupling, source=source, topology=topology, geometry=geometry, selection=selection)
    arrays, meta = (coupling['arrays'], coupling['metadata'])
    if dt_s not in (15.0, 30.0) or meta['runoff_metadata']['dt_s'] != 900.0:
        raise ValueError('fixed conservative 900s to 15/30s replay required')
    cells = record['arrays']['chain_cells']
    nodes = arrays['anchor_node'].ravel()[cells]
    if (nodes < 0).any() or len(set(nodes.tolist())) != 4:
        raise ValueError('A must explicitly anchor every study node')
    if any((meta['node_kind'][node] != 'river' for node in nodes)):
        raise ValueError('study chain crosses A lake or terminal')
    if not _i8_np.array_equal(arrays['node_downstream'][nodes[:-1]], nodes[1:]):
        raise ValueError('A river topology differs from study chain')
    if not _i8_np.array_equal(arrays['receiver'].ravel()[cells[:-1]], cells[1:]):
        raise ValueError('A geometric seam mismatch')
    intervals = 96
    if arrays['outflow_volume_m3'].shape[0] < intervals:
        raise ValueError('24h saved releases required; no extrapolation')
    inlet = arrays['outflow_volume_m3'][:intervals, nodes[0]].copy()
    lateral = _i8_np.zeros((intervals, 4), _i8_np.float64)
    side_nodes = []
    for index in range(1, 4):
        incoming = _i8_np.flatnonzero(arrays['node_downstream'] == nodes[index])
        external = incoming[incoming != nodes[index - 1]]
        if any((int(node) in nodes for node in external)):
            raise ValueError('side release double counts chain')
        lateral[:, index] = arrays['lateral_volume_m3'][:intervals, nodes[index]]
        if external.size:
            lateral[:, index] += arrays['outflow_volume_m3'][:intervals, external].sum(axis=1)
        side_nodes.append(external.tolist())
    repeat = int(900 / dt_s)
    initial = record['arrays']['min_bed_m'].copy()
    forcing = {'initial_stage_m': initial, 'inlet_q_m3_s': _i8_np.repeat(inlet / 900.0, repeat), 'lateral_q_m3_s': _i8_np.repeat(lateral / 900.0, repeat, axis=0), 'tailwater_stage_m': _i8_np.full(intervals * repeat + 1, initial[-1]), 'dt_s': dt_s}
    if not _i8_np.allclose(forcing['inlet_q_m3_s'].reshape(intervals, repeat).sum(axis=1) * dt_s, inlet, atol=1e-10, rtol=1e-14):
        raise ValueError('inlet interval conservation')
    if not _i8_np.allclose(forcing['lateral_q_m3_s'].reshape(intervals, repeat, 4).sum(axis=1) * dt_s, lateral, atol=1e-10, rtol=1e-14):
        raise ValueError('side interval conservation')
    upstream = _i8_np.zeros(arrays['node_downstream'].size, bool)
    upstream[nodes[0]] = True
    for node in arrays['node_order'][::-1]:
        target = arrays['node_downstream'][node]
        if target >= 0 and upstream[target]:
            upstream[node] = True
    upstream_cells = upstream[_i8_np.maximum(arrays['cell_node'], 0)] & arrays['hydrology_mask']
    partition = _i8_np.full(arrays['node_downstream'].size, -1, _i8_np.int64)
    partition[nodes] = _i8_np.arange(4)
    for node in arrays['node_order'][::-1]:
        target = arrays['node_downstream'][node]
        if partition[node] < 0 and target >= 0:
            partition[node] = partition[target]
    cell_partition = _i8_np.full(arrays['cell_node'].shape, -1, _i8_np.int64)
    active = arrays['hydrology_mask'] & (arrays['cell_node'] >= 0)
    cell_partition[active] = partition[arrays['cell_node'][active]]
    flat, receiver = (cell_partition.ravel(), arrays['receiver'].ravel())
    moving = _i8_np.flatnonzero((flat >= 0) & (receiver >= 0))
    nonanchors = moving[~_i8_np.isin(moving, cells)]
    if not _i8_np.array_equal(flat[nonanchors], flat[receiver[nonanchors]]):
        raise ValueError('saved contribution partition local recurrence')
    if not _i8_np.array_equal(flat[cells], _i8_np.arange(4)) or not _i8_np.array_equal(cell_partition == 0, upstream_cells):
        raise ValueError('first subtree partition identity')
    last_subtree = _i8_np.zeros(partition.size, bool)
    last_subtree[nodes[-1]] = True
    for node in arrays['node_order'][::-1]:
        target = arrays['node_downstream'][node]
        if target >= 0 and last_subtree[target]:
            last_subtree[node] = True
    if not _i8_np.array_equal(partition >= 0, last_subtree):
        raise ValueError('complete last-chain subtree not closed')
    result = {'forcing': forcing, 'arrays': {'inlet_interval_volume_m3': inlet, 'lateral_interval_volume_m3': lateral, 'upstream_cell_mask': upstream_cells, 'cell_partition': cell_partition, 'node_partition': partition, 'partition_counts': _i8_np.bincount(flat[flat >= 0], minlength=4)}, 'metadata': {'schema': 'mountain-A-releases-to-tributary-v1', 'source_identity': source['identity_sha256'], 'A_coupling_identity': coupling['identity_sha256'], 'study_geometry_identity': _i8_identity(record['arrays'], record['metadata']), 'inlet_node': int(nodes[0]), 'chain_nodes': nodes.tolist(), 'side_nodes': side_nodes, 'upstream_cells': int(upstream_cells.sum()), 'upstream_lake_nodes': [int(node) for node in _i8_np.flatnonzero(upstream) if meta['node_kind'][node] == 'lake'], 'inlet_includes_first_A_river_storage': True, 'inlet_seam': 'A_first_node_downstream_release_offline_alternative_with_extra_fine_residence_not_strict_replacement', 'scope': 'offline_one_way_nested_replay_not_joint_A_fine_solution', 'storage_accounting': 'independent alternative; never sum duplicated downstream A river storage with fine storage', 'tailwater': 'prescribed_last_support_minbed_engineering_diffusive_boundary_not_free_fall', 'duration_s': 86400.0, 'dt_s': dt_s}}
    validate_saved_binding(result, coupling, record)
    return result

def validate_saved_binding(bound, coupling, record):
    """Local saved partition recurrences and exact releases; never reassign ownership."""
    from terrain_pipeline.common_infra import identity as _i8_identity
    arrays, state, meta = (bound['arrays'], coupling['arrays'], bound['metadata'])
    if meta['schema'] != 'mountain-A-releases-to-tributary-v1' or meta['scope'] != 'offline_one_way_nested_replay_not_joint_A_fine_solution':
        raise ValueError('saved binding scope/schema mismatch')
    nodes = state['anchor_node'].ravel()[record['arrays']['chain_cells']]
    if meta['A_coupling_identity'] != coupling['identity_sha256'] or meta['study_geometry_identity'] != _i8_identity(record['arrays'], record['metadata']):
        raise ValueError('saved binding source mismatch')
    partition = arrays['node_partition']
    if partition.shape != state['node_downstream'].shape or partition.dtype != _i8_np.int64 or ((partition < -1) | (partition > 3)).any():
        raise ValueError('saved node partition schema')
    if not _i8_np.array_equal(partition[nodes], _i8_np.arange(4)):
        raise ValueError('chain partition anchors')
    nonanchors = _i8_np.setdiff1d(_i8_np.arange(partition.size), nodes)
    target = state['node_downstream'][nonanchors]
    expected = _i8_np.full(nonanchors.size, -1, _i8_np.int64)
    expected[target >= 0] = partition[target[target >= 0]]
    if not _i8_np.array_equal(partition[nonanchors], expected):
        raise ValueError('saved node partition local recurrence')
    grid = arrays['cell_partition']
    active = state['hydrology_mask']
    if grid.dtype != _i8_np.int64 or grid.shape != active.shape or (grid[~active] != -1).any():
        raise ValueError('saved cell partition schema')
    if not _i8_np.array_equal(grid[active], partition[state['cell_node'][active]]):
        raise ValueError('saved cell/node partition provenance')
    counts = _i8_np.bincount(grid[grid >= 0], minlength=4)
    if not _i8_np.array_equal(arrays['partition_counts'], counts) or not _i8_np.array_equal(arrays['upstream_cell_mask'], grid == 0):
        raise ValueError('saved complete subtree counts')
    if meta['inlet_node'] != int(nodes[0]) or meta['upstream_cells'] != counts[0] or meta['source_identity'] != coupling['metadata']['source_identity']:
        raise ValueError('saved binding anchor/area/source mismatch')
    lake_nodes = [int(node) for node in _i8_np.flatnonzero(partition == 0) if coupling['metadata']['node_kind'][node] == 'lake']
    if meta['upstream_lake_nodes'] != lake_nodes:
        raise ValueError('saved upstream lake inclusion mismatch')
    dt = meta['dt_s']
    if dt not in (15.0, 30.0) or meta['duration_s'] != 86400.0 or meta['chain_nodes'] != nodes.tolist():
        raise ValueError('saved binding time/chain identity')
    inlet = state['outflow_volume_m3'][:96, nodes[0]]
    lateral = _i8_np.zeros((96, 4))
    feeders = []
    for index in range(1, 4):
        external = _i8_np.flatnonzero((state['node_downstream'] == nodes[index]) & (_i8_np.arange(partition.size) != nodes[index - 1]))
        feeders.append(external.tolist())
        lateral[:, index] = state['lateral_volume_m3'][:96, nodes[index]] + state['outflow_volume_m3'][:96, external].sum(axis=1)
    if meta['side_nodes'] != feeders or not _i8_np.array_equal(arrays['inlet_interval_volume_m3'], inlet) or (not _i8_np.array_equal(arrays['lateral_interval_volume_m3'], lateral)):
        raise ValueError('saved release provenance mismatch')
    forcing = bound['forcing']
    repeat = int(900 / dt)
    expected_forcing = {'initial_stage_m': record['arrays']['min_bed_m'], 'inlet_q_m3_s': _i8_np.repeat(inlet / 900.0, repeat), 'lateral_q_m3_s': _i8_np.repeat(lateral / 900.0, repeat, axis=0), 'tailwater_stage_m': _i8_np.full(96 * repeat + 1, record['arrays']['min_bed_m'][-1])}
    for key, expected in expected_forcing.items():
        if not _i8_np.array_equal(forcing[key], expected):
            raise ValueError('saved forcing provenance mismatch: ' + key)
    if forcing['dt_s'] != dt:
        raise ValueError('forcing timestep mismatch')
    return {'partition_cells': int(counts.sum()), 'partition_counts': counts.tolist(), 'inlet_volume_m3': float(inlet.sum()), 'side_volume_m3': lateral.sum(axis=0).tolist()}
ROUGHNESS_S_M_THIRD = 0.035
MOUNTAIN_MANNING_STORAGE_MAX_STEPS = 6000
MAX_DURATION_S = 86400.0
MAX_EVALUATIONS = 2000000
MAX_STEP_EVALUATIONS = 64
MAX_STEP_RESIDUAL_CALLS = MAX_STEP_EVALUATIONS * 9 + 2
MAX_BYTES = 64 * 1024 * 1024
ABS_VOLUME_TOLERANCE_M3 = 1e-06
REL_VOLUME_TOLERANCE = 1e-10

def support_volume(record, node, stage):
    arrays = record['arrays']
    selected = arrays['row_owner'] == node
    return float((_i11_np.maximum(stage - arrays['H2_m'][selected], 0.0) * arrays['support_area_m2'][selected]).sum())

def manning_flux(record, stages, tailwater_stage_m):
    """Signed upwind section conveyance with actual shared dry-interface crest."""
    arrays = record['arrays']
    heads = _i11_np.r_[stages, tailwater_stage_m]
    flux = _i11_np.zeros(4, dtype=_i11_np.float64)
    for edge in range(4):
        section = arrays['interface_section_bed_m'][edge + 1]
        crest = arrays['interface_crest_m'][edge + 1]
        left = max(float(heads[edge]), crest)
        right = max(float(heads[edge + 1]), crest)
        difference = left - right
        if difference == 0:
            continue
        donor_stage = float(heads[edge] if difference > 0 else heads[edge + 1])
        hydraulics = section_hydraulics(arrays['across_m'], section, donor_stage)
        conveyance = hydraulics['area_m2'] * hydraulics['hydraulic_radius_m'] ** (2 / 3) / ROUGHNESS_S_M_THIRD
        flux[edge] = _i11_math.copysign(conveyance * _i11_math.sqrt(abs(difference) / arrays['edge_distance_m'][edge + 1]), difference)
    return flux

def preflight(steps, dt_s):
    if type(steps) is not int or not 1 <= steps <= MOUNTAIN_MANNING_STORAGE_MAX_STEPS or type(dt_s) not in (int, float) or (not _i11_math.isfinite(dt_s)) or (dt_s not in (15.0, 30.0)):
        raise ValueError('fixed 15/30s step and bounded forcing required')
    if steps * dt_s > MAX_DURATION_S:
        raise ValueError('Manning work/duration ceiling before allocation')
    estimate = (steps + 1) * 4 * 8 * 20 + 65536
    if estimate > MAX_BYTES:
        raise ValueError('Manning byte ceiling')
    return {'steps': steps, 'dt_s': dt_s, 'estimated_bytes': estimate, 'worst_case_requested_residual_calls': steps * MAX_STEP_RESIDUAL_CALLS, 'max_residual_evaluations': min(MAX_EVALUATIONS, steps * MAX_STEP_RESIDUAL_CALLS), 'per_step_residual_call_limit': MAX_STEP_RESIDUAL_CALLS, 'budget_policy': 'bounded_prefix_refusal_not_guaranteed_full_duration'}

def capacity_bound(record, *, inlet_q_m3_s, lateral_q_m3_s, tailwater_stage_m, dt_s):
    """Necessary dry-start volume bound using the greatest legal outlet conveyance."""
    arrays = record['arrays']
    capacities = _i11_np.array([support_volume(record, node, arrays['max_stage_m'][node]) for node in range(4)])
    upper_stages = arrays['max_stage_m'].copy()
    maximum_q = _i11_np.array([max(0.0, manning_flux(record, upper_stages, float(stage))[-1]) for stage in tailwater_stage_m[1:]])
    volume_in = _i11_np.cumsum((inlet_q_m3_s + lateral_q_m3_s.sum(axis=1)) * dt_s)
    maximum_out = _i11_np.cumsum(maximum_q * dt_s)
    exceed = volume_in - maximum_out > capacities.sum() + ABS_VOLUME_TOLERANCE_M3
    cumulative_net = _i11_np.r_[0.0, volume_in - maximum_out]
    interval_drawup = cumulative_net[1:] - _i11_np.minimum.accumulate(cumulative_net[:-1])
    interval_exceed = interval_drawup > capacities.sum() + ABS_VOLUME_TOLERANCE_M3
    return {'capacity_m3': capacities, 'max_outflow_q_m3_s': maximum_q, 'cumulative_input_m3': volume_in, 'cumulative_max_outflow_m3': maximum_out, 'exceeded_mask': exceed, 'first_exceed_step': int(_i11_np.flatnonzero(exceed)[0]) if exceed.any() else None, 'any_interval_drawup_m3': interval_drawup, 'any_interval_first_exceed_step': int(_i11_np.flatnonzero(interval_exceed)[0]) if interval_exceed.any() else None, 'bound_scope': 'necessary_only_null_is_inconclusive_no_virtual_early_drainage_credit'}

def prepare_manning_storage(record, geometry, *, initial_stage_m, inlet_q_m3_s, lateral_q_m3_s, tailwater_stage_m, dt_s):
    """Bounded four-control-volume implicit stage solve, preserving failed prefix."""
    validate_tributary_geometry(record, geometry)
    if not isinstance(inlet_q_m3_s, _i11_np.ndarray) or inlet_q_m3_s.ndim != 1:
        raise ValueError('resource-checkable inlet required')
    steps = inlet_q_m3_s.size
    resources = preflight(steps, dt_s)
    arrays = record['arrays']
    initial = _i11_np.asarray(initial_stage_m)
    if initial.shape != (4,) or lateral_q_m3_s.shape != (steps, 4) or tailwater_stage_m.shape != (steps + 1,):
        raise ValueError('Manning input shapes')
    for values in (initial, inlet_q_m3_s, lateral_q_m3_s, tailwater_stage_m):
        if values.dtype != _i11_np.dtype('float64') or not _i11_np.isfinite(values).all():
            raise ValueError('finite float64 Manning forcing required')
    if (inlet_q_m3_s < 0).any() or (lateral_q_m3_s < 0).any():
        raise ValueError('negative supplied inflow')
    lower, upper = (arrays['min_bed_m'], arrays['max_stage_m'])
    if (initial < lower).any() or (initial > upper).any():
        raise ValueError('initial stage outside source bank support')
    initial_storage = _i11_np.array([support_volume(record, node, initial[node]) for node in range(4)])
    stages = [initial.copy()]
    storages = [initial_storage]
    fluxes = []
    residuals = []
    iterations = []
    failure = None
    spent = 0
    for step in range(steps):
        step_start = spent
        before = storages[-1]
        external = lateral_q_m3_s[step].copy()
        external[0] += inlet_q_m3_s[step]
        tolerance = ABS_VOLUME_TOLERANCE_M3 + REL_VOLUME_TOLERANCE * (before + dt_s * external)

        def residual(stage):
            nonlocal spent
            if spent >= MAX_EVALUATIONS or spent - step_start >= MAX_STEP_RESIDUAL_CALLS:
                raise RuntimeError('Manning residual evaluation ceiling')
            spent += 1
            volume = _i11_np.array([support_volume(record, node, stage[node]) for node in range(4)])
            flux = manning_flux(record, stage, float(tailwater_stage_m[step + 1]))
            internal = _i11_np.r_[0.0, flux[:-1]] - flux
            return volume - before - dt_s * (external + internal)
        try:
            initial_error = residual(stages[-1])
            if _i11_np.max(_i11_np.abs(initial_error)) == 0:
                next_stage = stages[-1].copy()
                evaluation_count = 1
            else:

                def depth_residual(depth):
                    return residual(lower + depth)
                solved = _i11_least_squares(depth_residual, _i11_np.clip(stages[-1] - lower, 1e-10, upper - lower - 1e-10), bounds=(_i11_np.zeros(4), upper - lower), max_nfev=MAX_STEP_EVALUATIONS, ftol=1e-12, xtol=1e-12, gtol=1e-12, jac='3-point', x_scale='jac')
                next_stage = lower + solved.x
                evaluation_count = int(solved.nfev)
            error = residual(next_stage)
        except RuntimeError as exc:
            if str(exc) != 'Manning residual evaluation ceiling':
                raise
            failure = {'step': step, 'reason': 'residual_evaluation_budget_exhausted'}
            break
        if (_i11_np.abs(error) > tolerance).any():
            failure = {'step': step, 'reason': 'bank_limited_implicit_residual_or_solver_limit', 'max_residual_m3': float(_i11_np.abs(error).max()), 'nfev': evaluation_count, 'near_upper_bank_nodes': _i11_np.flatnonzero(upper - next_stage < 1e-07).tolist()}
            break
        flux = manning_flux(record, next_stage, float(tailwater_stage_m[step + 1]))
        volume = _i11_np.array([support_volume(record, node, next_stage[node]) for node in range(4)])
        stages.append(next_stage.copy())
        storages.append(volume)
        fluxes.append(flux)
        residuals.append(error)
        iterations.append(evaluation_count)
    committed = len(fluxes)
    saved = {'metadata': {'schema': 'mountain-manning-diffusive-storage-v1', 'dt_s': float(dt_s), 'roughness_s_m_third': ROUGHNESS_S_M_THIRD, 'status': 'completed' if failure is None else 'refused', 'failure': failure, 'committed_steps': committed, 'requested_steps': steps, 'resources': resources, 'residual_evaluations': spent, 'scope': 'independent_local_implicit_Manning_diffusive_no_momentum_not_Saint_Venant', 'source_binding': record['metadata']['source_binding']}, 'arrays': {'initial_stage_m': initial.copy(), 'inlet_q_m3_s': inlet_q_m3_s.copy(), 'lateral_q_m3_s': lateral_q_m3_s.copy(), 'tailwater_stage_m': tailwater_stage_m.copy(), 'stage_m': _i11_np.asarray(stages), 'storage_m3': _i11_np.asarray(storages), 'qedges_m3_s': _i11_np.asarray(fluxes).reshape(-1, 4), 'node_residual_m3': _i11_np.asarray(residuals).reshape(-1, 4), 'solver_evaluations': _i11_np.asarray(iterations, dtype=_i11_np.int64)}}
    validate_manning_storage(saved, record, geometry)
    return saved

def validate_manning_storage(saved, record, geometry):
    """Static bank, source, V(h), exact signed Manning and volume equations."""
    validate_tributary_geometry(record, geometry)
    meta, state = (saved['metadata'], saved['arrays'])
    if meta['schema'] != 'mountain-manning-diffusive-storage-v1' or meta['scope'] != 'independent_local_implicit_Manning_diffusive_no_momentum_not_Saint_Venant':
        raise ValueError('Manning schema/scope identity')
    requested, committed = (meta['requested_steps'], meta['committed_steps'])
    if meta['status'] not in ('completed', 'refused') or type(committed) is not int:
        raise ValueError('unknown Manning status or prefix type')
    if type(meta['residual_evaluations']) is not int or not 0 <= meta['residual_evaluations'] <= MAX_EVALUATIONS:
        raise ValueError('Manning residual work budget')
    if meta['resources'] != preflight(requested, meta['dt_s']) or not 0 <= committed <= requested:
        raise ValueError('Manning resource metadata')
    if meta['roughness_s_m_third'] != ROUGHNESS_S_M_THIRD or meta['source_binding'] != record['metadata']['source_binding']:
        raise ValueError('roughness/source identity mismatch')
    if meta['status'] == 'completed' and (committed != requested or meta['failure'] is not None) or (meta['status'] == 'refused' and (committed == requested or meta['failure'] is None or meta['failure']['step'] != committed)):
        raise ValueError('Manning status prefix')
    specs = {'initial_stage_m': (4,), 'inlet_q_m3_s': (requested,), 'lateral_q_m3_s': (requested, 4), 'tailwater_stage_m': (requested + 1,), 'stage_m': (committed + 1, 4), 'storage_m3': (committed + 1, 4), 'qedges_m3_s': (committed, 4), 'node_residual_m3': (committed, 4), 'solver_evaluations': (committed,)}
    if set(state) != set(specs):
        raise ValueError('Manning exact saved schema')
    for key, shape in specs.items():
        values = state[key]
        dtype = _i11_np.dtype('int64' if key == 'solver_evaluations' else 'float64')
        if values.shape != shape or values.dtype != dtype or (not _i11_np.isfinite(values).all()):
            raise ValueError('Manning saved dtype/shape/finite')
    if not _i11_np.array_equal(state['stage_m'][0], state['initial_stage_m']):
        raise ValueError('Manning initial stage identity')
    if (state['inlet_q_m3_s'] < 0).any() or (state['lateral_q_m3_s'] < 0).any():
        raise ValueError('negative external Manning forcing')
    if ((state['solver_evaluations'] < 1) | (state['solver_evaluations'] > MAX_STEP_EVALUATIONS)).any():
        raise ValueError('Manning solver step budget')
    source = record['arrays']
    if (state['stage_m'] < source['min_bed_m'] - 1e-09).any() or (state['stage_m'] > source['max_stage_m'] + 1e-09).any() or (state['storage_m3'] < 0).any():
        raise ValueError('Manning bank/dry positivity')
    for node in range(4):
        selected = source['row_owner'] == node
        beds = source['H2_m'][selected].ravel()
        weights = source['support_area_m2'][selected].ravel()
        volumes = _i11_np.maximum(state['stage_m'][:, node, None] - beds[None, :], 0) @ weights
        if not _i11_np.allclose(state['storage_m3'][:, node], volumes, rtol=0, atol=1e-08):
            raise ValueError('Manning storage support forgery')
    expected_flux = _i11_np.array([manning_flux(record, stage, float(tail)) for stage, tail in zip(state['stage_m'][1:], state['tailwater_stage_m'][1:committed + 1])]).reshape(-1, 4)
    if not _i11_np.allclose(state['qedges_m3_s'], expected_flux, rtol=1e-12, atol=1e-12):
        raise ValueError('Manning signed section flux forged')
    external = state['lateral_q_m3_s'][:committed].copy()
    external[:, 0] += state['inlet_q_m3_s'][:committed]
    net = _i11_np.column_stack((_i11_np.zeros(committed), expected_flux[:, :-1])) - expected_flux
    residual = _i11_np.diff(state['storage_m3'], axis=0) - meta['dt_s'] * (external + net)
    tolerance = ABS_VOLUME_TOLERANCE_M3 + REL_VOLUME_TOLERANCE * (state['storage_m3'][:-1] + external * meta['dt_s'])
    if not _i11_np.allclose(state['node_residual_m3'], residual, rtol=0, atol=1e-08) or (_i11_np.abs(residual) > tolerance * 1.01).any():
        raise ValueError('Manning per-node balance')
    return {'max_node_residual_m3': float(_i11_np.abs(residual).max(initial=0)), 'final_storage_m3': float(state['storage_m3'][-1].sum()), 'signed_external_outflow_m3': float(expected_flux[:, -1].sum() * meta['dt_s'])}

def save_manning_storage(path, saved, record, geometry):
    from terrain_pipeline.common_infra import identity as _i11_identity
    from terrain_pipeline.common_infra import publish_bytes as _i11_publish_bytes
    from terrain_pipeline.runoff import _json as _i11__json
    validate_manning_storage(saved, record, geometry)
    manifest = {'metadata': saved['metadata'], 'identity_sha256': _i11_identity(saved['arrays'], saved['metadata']), 'geometry_identity': _i11_identity(record['arrays'], record['metadata'])}
    encoded = _i11__json(manifest).encode('utf-8')
    if len(encoded) > 65536:
        raise ValueError('Manning manifest budget')
    stream = _i11_io.BytesIO()
    _i11_np.savez_compressed(stream, manifest=_i11_np.frombuffer(encoded, dtype=_i11_np.uint8), **saved['arrays'])
    if stream.tell() > MAX_BYTES:
        raise ValueError('Manning archive byte ceiling')
    _i11_publish_bytes(path, stream.getvalue())

def load_manning_storage(path, record, geometry, *, expected_sha256, trusted_forcing):
    from terrain_pipeline.common_infra import checked_archive as _i11_checked_archive
    from terrain_pipeline.common_infra import identity as _i11_identity
    from terrain_pipeline.common_infra import readonly as _i11_readonly
    from terrain_pipeline.runoff import _strict_json as _i11__strict_json

    def headers(specs):
        keys = {'initial_stage_m', 'inlet_q_m3_s', 'lateral_q_m3_s', 'tailwater_stage_m', 'stage_m', 'storage_m3', 'qedges_m3_s', 'node_residual_m3', 'solver_evaluations', 'manifest'}
        if set(specs) != keys:
            raise ValueError('exact Manning archive keys')
        requested_shape = specs['inlet_q_m3_s'][0]
        state_shape = specs['stage_m'][0]
        if len(requested_shape) != 1 or len(state_shape) != 2:
            raise ValueError('Manning header axes')
        requested, committed = (requested_shape[0], state_shape[0] - 1)
        if not 1 <= requested <= MOUNTAIN_MANNING_STORAGE_MAX_STEPS or not 0 <= committed <= requested:
            raise ValueError('Manning header steps')
        shapes = {'initial_stage_m': (4,), 'inlet_q_m3_s': (requested,), 'lateral_q_m3_s': (requested, 4), 'tailwater_stage_m': (requested + 1,), 'stage_m': (committed + 1, 4), 'storage_m3': (committed + 1, 4), 'qedges_m3_s': (committed, 4), 'node_residual_m3': (committed, 4), 'solver_evaluations': (committed,)}
        for key, shape in shapes.items():
            dtype = _i11_np.dtype('int64' if key == 'solver_evaluations' else 'float64')
            if specs[key] != (shape, dtype):
                raise ValueError('Manning exact header: ' + key)
        shape, dtype = specs['manifest']
        if len(shape) != 1 or not 1 <= shape[0] <= 65536 or dtype != _i11_np.dtype('uint8'):
            raise ValueError('Manning manifest header')
    arrays = _i11_checked_archive(path, expected_sha256=expected_sha256, max_bytes=MAX_BYTES, header_validator=headers)
    manifest = _i11__strict_json(arrays.pop('manifest').tobytes().decode('utf-8'))
    if set(manifest) != {'metadata', 'identity_sha256', 'geometry_identity'}:
        raise ValueError('Manning manifest schema')
    if manifest['geometry_identity'] != _i11_identity(record['arrays'], record['metadata']) or manifest['identity_sha256'] != _i11_identity(arrays, manifest['metadata']):
        raise ValueError('Manning geometry/integrity mismatch')
    if set(trusted_forcing) != {'initial_stage_m', 'inlet_q_m3_s', 'lateral_q_m3_s', 'tailwater_stage_m', 'dt_s'}:
        raise ValueError('external Manning forcing trust required')
    for key, value in trusted_forcing.items():
        if key == 'dt_s':
            if manifest['metadata'][key] != value:
                raise ValueError('external timestep mismatch')
        elif not _i11_np.array_equal(arrays[key], value):
            raise ValueError('external forcing mismatch: ' + key)
    saved = {'metadata': manifest['metadata'], 'arrays': arrays}
    validate_manning_storage(saved, record, geometry)
    saved['arrays'] = {key: _i11_readonly(value) for key, value in arrays.items()}
    return saved
MAX_DISPLAY_STATES = 100

def export_manning_mesh(record, saved, geometry):
    from terrain_pipeline.common_infra import identity as _i10_identity
    from terrain_pipeline.runoff import _hash as _i10__hash
    validate_manning_storage(saved, record, geometry)
    source = record['arrays']
    state = saved['arrays']
    count = state['stage_m'].shape[0]
    peak = int(state['storage_m3'].sum(axis=1).argmax())
    indices = _i10_np.unique(_i10_np.r_[_i10_np.linspace(0, count - 1, min(97, count)).astype(_i10_np.int64), peak])
    rows, columns = source['H2_m'].shape
    grid = _i10_np.arange(rows * columns, dtype=_i10_np.int64).reshape(rows, columns)
    lower_left, lower_right = (grid[:-1, :-1].ravel(), grid[:-1, 1:].ravel())
    upper_left, upper_right = (grid[1:, :-1].ravel(), grid[1:, 1:].ravel())
    triangles = _i10_np.concatenate((_i10_np.column_stack((lower_left, lower_right, upper_right)), _i10_np.column_stack((lower_left, upper_right, upper_left))))
    original = _i10_np.column_stack((source['world_x_m'].ravel(), source['H0_m'].ravel(), source['world_z_m'].ravel()))
    bed = original.copy()
    bed[:, 1] = source['H2_m'].ravel()
    origin = _i10_np.array([original[0, 0], original[:, 1].min(), original[0, 2]])
    owner = _i10_np.repeat(source['row_owner'], columns)
    depth = _i10_np.maximum(state['stage_m'][indices][:, owner] - bed[None, :, 1], 0.0)
    weights = source['support_area_m2'].ravel()
    volume = depth @ weights
    selected_flux = _i10_np.zeros((indices.size, 4))
    positive = indices > 0
    selected_flux[positive] = state['qedges_m3_s'][indices[positive] - 1]
    mesh = {'arrays': {'origin_world_xyz_m': origin, 'vertices_H0_local_xyz_m': original - origin, 'vertices_H2_local_xyz_m': bed - origin, 'triangles': triangles, 'shared_section_vertex_ids': grid[[0, 30, 60, 90]], 'support_owner': owner, 'support_area_m2': weights, 'saved_state_indices': indices, 'time_s': indices.astype(_i10_np.float64) * saved['metadata']['dt_s'], 'water_depth_m': depth, 'wet_mask': depth > 0.0, 'water_volume_m3': volume, 'solver_volume_m3': state['storage_m3'][indices].sum(axis=1), 'display_volume_difference_m3': volume - state['storage_m3'][indices].sum(axis=1), 'qedges_m3_s': selected_flux}, 'metadata': {'schema': 'mountain-manning-weighted-wet-support-mesh-v1', 'geometry_identity': _i10_identity(record['arrays'], record['metadata']), 'saved_stage_sha256': _i10__hash(state['stage_m']), 'source_binding': record['metadata']['source_binding'], 'state_count': int(indices.size), 'full_committed_state_count': count, 'peak_saved_state': peak, 'failure': saved['metadata']['failure'], 'water_representation': 'weighted_discrete_wet_support_points_not_interpolated_triangle_water_surface', 'scope': 'offline_A_release_replay_engineering_diffusive_prescribed_tailwater_not_natural_outlet', 'display_sampling': 'at_most_98_saved_states_including_initial_last_storage_peak_no_new_time_interpolation'}}
    validate_manning_mesh(mesh, record, saved, geometry)
    return mesh

def validate_manning_mesh(mesh, record, saved, geometry):
    from terrain_pipeline.common_infra import identity as _i10_identity
    from terrain_pipeline.runoff import _hash as _i10__hash
    validate_manning_storage(saved, record, geometry)
    arrays, meta = (mesh['arrays'], mesh['metadata'])
    source, state = (record['arrays'], saved['arrays'])
    if set(arrays) != {'origin_world_xyz_m', 'vertices_H0_local_xyz_m', 'vertices_H2_local_xyz_m', 'triangles', 'shared_section_vertex_ids', 'support_owner', 'support_area_m2', 'saved_state_indices', 'time_s', 'water_depth_m', 'wet_mask', 'water_volume_m3', 'solver_volume_m3', 'display_volume_difference_m3', 'qedges_m3_s'}:
        raise ValueError('exact Manning mesh schema')
    if meta['geometry_identity'] != _i10_identity(source, record['metadata']) or meta['saved_stage_sha256'] != _i10__hash(state['stage_m']):
        raise ValueError('Manning mesh source identity')
    indices = arrays['saved_state_indices']
    if indices.dtype != _i10_np.int64 or indices.ndim != 1 or (not 1 <= indices.size <= MAX_DISPLAY_STATES):
        raise ValueError('Manning mesh display resource budget')
    if indices[0] != 0 or indices[-1] != state['stage_m'].shape[0] - 1 or (_i10_np.diff(indices) <= 0).any():
        raise ValueError('Manning mesh saved state selection')
    shapes = {'origin_world_xyz_m': (3,), 'vertices_H0_local_xyz_m': (1001, 3), 'vertices_H2_local_xyz_m': (1001, 3), 'triangles': (1800, 3), 'shared_section_vertex_ids': (4, 11), 'support_owner': (1001,), 'support_area_m2': (1001,), 'saved_state_indices': (indices.size,), 'time_s': (indices.size,), 'water_depth_m': (indices.size, 1001), 'wet_mask': (indices.size, 1001), 'water_volume_m3': (indices.size,), 'solver_volume_m3': (indices.size,), 'display_volume_difference_m3': (indices.size,), 'qedges_m3_s': (indices.size, 4)}
    for key, shape in shapes.items():
        value = arrays[key]
        dtype = _i10_np.dtype('bool' if key == 'wet_mask' else 'int64' if key in ('triangles', 'shared_section_vertex_ids', 'support_owner', 'saved_state_indices') else 'float64')
        if value.shape != shape or value.dtype != dtype or (not _i10_np.isfinite(value).all()):
            raise ValueError('Manning mesh exact shape/dtype/finite: ' + key)
    peak = int(state['storage_m3'].sum(axis=1).argmax())
    if meta['schema'] != 'mountain-manning-weighted-wet-support-mesh-v1' or meta['state_count'] != indices.size or meta['full_committed_state_count'] != state['stage_m'].shape[0] or (meta['peak_saved_state'] != peak) or (peak not in indices) or (meta['failure'] != saved['metadata']['failure']):
        raise ValueError('Manning mesh status/peak identity')
    grid = _i10_np.arange(1001, dtype=_i10_np.int64).reshape(91, 11)
    expected_triangles = _i10_np.concatenate((_i10_np.column_stack((grid[:-1, :-1].ravel(), grid[:-1, 1:].ravel(), grid[1:, 1:].ravel())), _i10_np.column_stack((grid[:-1, :-1].ravel(), grid[1:, 1:].ravel(), grid[1:, :-1].ravel()))))
    if not _i10_np.array_equal(arrays['triangles'], expected_triangles) or not _i10_np.array_equal(arrays['shared_section_vertex_ids'], grid[[0, 30, 60, 90]]):
        raise ValueError('Manning mesh fixed triangles/shared IDs')
    for key in ('H0', 'H2'):
        world = arrays[f'vertices_{key}_local_xyz_m'] + arrays['origin_world_xyz_m']
        expected = _i10_np.column_stack((source['world_x_m'].ravel(), source[key + '_m'].ravel(), source['world_z_m'].ravel()))
        if not _i10_np.allclose(world, expected, atol=1e-10, rtol=0):
            raise ValueError('Manning mesh coordinate forgery')
    triangles = arrays['triangles']
    bed = arrays['vertices_H2_local_xyz_m']
    if triangles.dtype != _i10_np.int64 or triangles.shape != (1800, 3) or (triangles < 0).any() or (triangles >= 1001).any():
        raise ValueError('Manning mesh triangle schema')
    normals = _i10_np.cross(bed[triangles[:, 1]] - bed[triangles[:, 0]], bed[triangles[:, 2]] - bed[triangles[:, 0]])
    if (normals[:, 1] <= 0).any():
        raise ValueError('Manning mesh winding')
    edges = _i10_np.sort(_i10_np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]])), axis=1)
    _, counts = _i10_np.unique(edges, axis=0, return_counts=True)
    if (counts > 2).any() or _i10_np.count_nonzero(counts == 1) != 200 or 1001 - counts.size + 1800 != 1:
        raise ValueError('Manning mesh topology')
    expected_owner = _i10_np.repeat(source['row_owner'], 11)
    if not _i10_np.array_equal(arrays['support_owner'], expected_owner) or not _i10_np.array_equal(arrays['support_area_m2'], source['support_area_m2'].ravel()):
        raise ValueError('Manning mesh support provenance')
    depth = _i10_np.maximum(state['stage_m'][indices][:, expected_owner] - source['H2_m'].ravel(), 0.0)
    if not _i10_np.array_equal(arrays['water_depth_m'], depth) or not _i10_np.array_equal(arrays['wet_mask'], depth > 0):
        raise ValueError('Manning mesh water provenance')
    volume = depth @ source['support_area_m2'].ravel()
    if not _i10_np.allclose(volume, state['storage_m3'][indices].sum(axis=1), atol=1e-08, rtol=0):
        raise ValueError('Manning mesh V(h) mismatch')
    if not _i10_np.array_equal(arrays['water_volume_m3'], volume) or not _i10_np.array_equal(arrays['time_s'], indices * saved['metadata']['dt_s']):
        raise ValueError('Manning mesh volume/time forgery')
    expected_volume = state['storage_m3'][indices].sum(axis=1)
    expected_flux = _i10_np.zeros((indices.size, 4))
    positive = indices > 0
    expected_flux[positive] = state['qedges_m3_s'][indices[positive] - 1]
    if not _i10_np.array_equal(arrays['solver_volume_m3'], expected_volume) or not _i10_np.array_equal(arrays['display_volume_difference_m3'], volume - expected_volume) or (not _i10_np.array_equal(arrays['qedges_m3_s'], expected_flux)):
        raise ValueError('Manning mesh saved volume/flux mismatch')
    return {'boundary_edges': 200, 'Euler': 1, 'minimum_normal_Y': float(normals[:, 1].min()), 'max_display_volume_error_m3': float(_i10_np.abs(volume - state['storage_m3'][indices].sum(axis=1)).max())}
VALLEY_GEOMETRY_VERSION = 'valley-geometry-v1'

@_i52_dataclass(frozen=True)
class ValleyGeometryRecipe:
    max_valley_depth_m: float
    max_valley_area_m2: float
    max_valley_volume_m3: float
    max_total_cut_volume_m3: float
    max_total_cut_area_m2: float = 1000000000000.0

    def __post_init__(self):
        if any((isinstance(v, bool) or not _i52_math.isfinite(v) or v < 0 for v in _i52_asdict(self).values())):
            raise ValueError('valley budgets must be finite and nonnegative')

def prepare_valley_geometry(plan, centerline_world_xz_m, floor_elevation_m, width_m, domain_mask, protected_mask, valley_recipe: ValleyGeometryRecipe, channel_recipe: ChannelRecipe):
    """Create H1 from an independent floor profile, then replan the bed on H1."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i52_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i52_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i52_digest
    if not isinstance(valley_recipe, ValleyGeometryRecipe) or not isinstance(channel_recipe, ChannelRecipe):
        raise ValueError('valley and channel recipes required')
    if _i52_ArtifactIdentity(**plan['identity']).sha256 != plan['identity_sha256'] or plan['identity']['algorithm'] != 'metric-channel-plan':
        raise ValueError('invalid source plan identity')
    source = _i52_np.asarray(plan['arrays']['source_height_m'])
    shape = source.shape
    source_params = plan['identity']['parameters']
    for name, field in (('source_height_m', 'source_height_sha256'), ('discharge_m3_s', 'source_discharge_sha256'), ('receiver', 'source_route_sha256'), ('order', 'source_order_sha256'), ('outlet_mask', 'source_outlet_sha256')):
        if _i52_array_hash(_i52_np.ascontiguousarray(plan['arrays'][name])) != source_params[field]:
            raise ValueError('source plan inputs differ from identity')
    points = _i52_np.asarray(centerline_world_xz_m, dtype=_i52_np.float64)
    floors = _i52_np.asarray(floor_elevation_m, dtype=_i52_np.float64)
    widths = _i52_np.asarray(width_m, dtype=_i52_np.float64)
    domain = _i52_np.asarray(domain_mask)
    protected = _i52_np.asarray(protected_mask)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 2 or (floors.shape != (len(points),)) or (widths.shape != floors.shape) or (not _i52_np.isfinite(points).all()) or (not _i52_np.isfinite(floors).all()) or (not _i52_np.isfinite(widths).all()) or _i52_np.any(widths <= 0) or (domain.shape != shape) or (protected.shape != shape) or (domain.dtype != bool) or (protected.dtype != bool):
        raise ValueError('invalid explicit valley geometry or masks')
    params = plan['identity']['parameters']
    requested = _rasterize_valley_edges(source, params, _i52_np.stack((points[:-1], points[1:]), axis=1), _i52_np.stack((floors[:-1], floors[1:]), axis=1), _i52_np.stack((widths[:-1], widths[1:]), axis=1))
    arrays, replanned, summary = _prepare_valley_cut(plan, requested, domain, protected, valley_recipe, channel_recipe, plan['identity_sha256'])
    identity = _i52_ArtifactIdentity('Terragenesis', 'valley-geometry', VALLEY_GEOMETRY_VERSION, 0, {**_i52_asdict(valley_recipe), 'source_plan_sha256': plan['identity_sha256'], 'replanned_sha256': replanned['identity_sha256'], 'centerline_sha256': _i52_array_hash(points), 'floor_sha256': _i52_array_hash(floors), 'width_sha256': _i52_array_hash(widths), 'domain_sha256': _i52_array_hash(domain), 'protected_sha256': _i52_array_hash(protected), 'arrays_sha256': _i52_digest({name: _i52_array_hash(value) for name, value in arrays.items()}), 'summary_sha256': _i52_digest(summary)})
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': 'diagnostic_not_publishable', 'arrays': arrays, 'replanned_plan': replanned, 'summary': summary}

def _rasterize_valley_edges(source, params, edges, floors, widths, local_bounds=False):
    """Rasterize independent metric segments using the maximum cut on overlaps."""
    shape = source.shape
    grid_x = params['origin_x_m'] + _i52_np.arange(shape[1]) * params['spacing_x_m']
    grid_z = params['origin_z_m'] + _i52_np.arange(shape[0]) * params['spacing_z_m']
    requested = _i52_np.zeros(shape, dtype=_i52_np.float64)
    for points, edge_floors, edge_widths in zip(edges, floors, widths):
        ax, az = points[0]
        bx, bz = points[1]
        length2 = (bx - ax) ** 2 + (bz - az) ** 2
        if length2 <= 0:
            raise ValueError('valley centerline has duplicate points')
        if local_bounds:
            reach = 0.5 * max(edge_widths)
            start_x = _i52_np.searchsorted(grid_x, min(ax, bx) - reach, side='left')
            stop_x = _i52_np.searchsorted(grid_x, max(ax, bx) + reach, side='right')
            start_z = _i52_np.searchsorted(grid_z, min(az, bz) - reach, side='left')
            stop_z = _i52_np.searchsorted(grid_z, max(az, bz) + reach, side='right')
            region = (slice(start_z, stop_z), slice(start_x, stop_x))
        else:
            region = (slice(None), slice(None))
        gx, gz = _i52_np.meshgrid(grid_x[region[1]], grid_z[region[0]])
        t = _i52_np.clip(((gx - ax) * (bx - ax) + (gz - az) * (bz - az)) / length2, 0.0, 1.0)
        distance = _i52_np.hypot(gx - (ax + t * (bx - ax)), gz - (az + t * (bz - az)))
        radius = 0.5 * ((1 - t) * edge_widths[0] + t * edge_widths[1])
        inside = distance < radius
        floor = (1 - t) * edge_floors[0] + t * edge_floors[1]
        cut = _i52_np.zeros(gx.shape, dtype=_i52_np.float64)
        cut[inside] = _i52_np.maximum(0.0, source[region][inside] - floor[inside]) * (0.5 * (1 + _i52_np.cos(_i52_np.pi * distance[inside] / radius[inside])))
        requested[region] = _i52_np.maximum(requested[region], cut)
    return requested

def _prepare_valley_cut(plan, requested, domain, protected, valley_recipe, channel_recipe, parent_identity):
    """Shared H0/H1/H2 coarse diagnostic; requested cuts are never budget-clipped."""
    source = plan['arrays']['source_height_m']
    shape = source.shape
    params = plan['identity']['parameters']
    changed = requested > 1e-09
    cell_area = params['spacing_x_m'] * params['spacing_z_m']
    weights = _i52_np.ones(shape)
    weights[[0, -1], :] *= 0.5
    weights[:, [0, -1]] *= 0.5
    area = float(_i52_np.sum(changed * weights) * cell_area)
    valley_volume = float(_i52_np.sum(requested * weights) * cell_area)
    valley_surface = source - requested
    replanned = plan_channel(valley_surface, plan['arrays']['receiver'], plan['arrays']['order'], plan['arrays']['outlet_mask'], plan['arrays']['discharge_m3_s'], params['spacing_x_m'], params['spacing_z_m'], params['origin_x_m'], params['origin_z_m'], params['sea_level_elevation_m'], parent_identity, channel_recipe)
    bed_cut = valley_surface - replanned['arrays']['bounded_bed_m']
    total = requested + bed_cut
    total_volume = float(_i52_np.sum(total * weights) * cell_area)
    total_area = float(_i52_np.sum((total > 1e-09) * weights) * cell_area)
    failures = {'valley_depth': bool(_i52_np.any(requested > valley_recipe.max_valley_depth_m + 1e-09)), 'valley_area': area > valley_recipe.max_valley_area_m2 + 1e-09, 'valley_volume': valley_volume > valley_recipe.max_valley_volume_m3 + 1e-09, 'total_volume': total_volume > valley_recipe.max_total_cut_volume_m3 + 1e-09, 'domain': bool(_i52_np.any(changed & ~domain)), 'protection': bool(_i52_np.any(changed & protected)), 'bed_domain': bool(_i52_np.any((bed_cut > 1e-09) & ~domain)), 'bed_protection': bool(_i52_np.any((bed_cut > 1e-09) & protected)), 'bed_depth': bool(_i52_np.any(bed_cut > channel_recipe.max_cut_m + 1e-09)), 'bed_plan': bool(_i52_np.any(replanned['arrays']['over_budget_mask'] | replanned['arrays']['failed_slope_edge_donor_mask']))}
    arrays = {'source_height_m': source.copy(), 'valley_surface_m': valley_surface, 'final_bed_m': replanned['arrays']['bounded_bed_m'].copy(), 'valley_cut_m': requested, 'bed_cut_m': bed_cut, 'total_cut_m': total}
    for value in arrays.values():
        value.flags.writeable = False
    summary = {'valley_area_m2': area, 'valley_cut_volume_m3': valley_volume, 'bed_cut_volume_m3': float(_i52_np.sum(bed_cut * weights) * cell_area), 'total_cut_volume_m3': total_volume, 'total_cut_area_m2': total_area, 'geometry_scope': 'coarse_node_diagnostic_only', 'failures': failures, 'geometry_feasible': not any(failures.values())}
    return (arrays, replanned, summary)

def evaluate_fine_valley_ledger(valley_result, surface_result):
    """Account H0/H1/H2 on the same fine grid after the replanned bed sweep."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i52_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i52_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i52_digest
    if valley_result['identity']['algorithm'] == 'network-valley':
        pass
        from terrain_pipeline.surface_domain import validate_surface_network as validate_surface_network
        validate_network_valley(valley_result)
        validate_surface_network(surface_result, allow_diagnostic=True)
    if valley_result['replanned_plan']['identity_sha256'] != surface_result['identity']['parameters']['plan_sha256']:
        raise ValueError('surface preparation did not use the replanned valley bed')
    params = surface_result['identity']['parameters']
    coarse = valley_result['replanned_plan']['identity']['parameters']
    shape = surface_result['arrays']['final_surface_m'].shape
    x = params['fine_origin_x_m'] + _i52_np.arange(shape[1]) * params['fine_spacing_x_m']
    z = params['fine_origin_z_m'] + _i52_np.arange(shape[0]) * params['fine_spacing_z_m']
    gx, gz = _i52_np.meshgrid(x, z)
    fx = (gx - coarse['origin_x_m']) / coarse['spacing_x_m']
    fz = (gz - coarse['origin_z_m']) / coarse['spacing_z_m']
    coarse_shape = valley_result['arrays']['source_height_m'].shape
    if _i52_np.any(fx < -1e-08) or _i52_np.any(fx > coarse_shape[1] - 1 + 1e-08) or _i52_np.any(fz < -1e-08) or _i52_np.any(fz > coarse_shape[0] - 1 + 1e-08):
        raise ValueError('fine grid leaves valley source extent')
    fx = _i52_np.clip(fx, 0, coarse_shape[1] - 1)
    fz = _i52_np.clip(fz, 0, coarse_shape[0] - 1)
    h0 = _source_surface(valley_result['arrays']['source_height_m'], fx, fz)
    h1 = _source_surface(valley_result['arrays']['valley_surface_m'], fx, fz)
    h2 = surface_result['arrays']['final_surface_m']
    if not _i52_np.allclose(h1, surface_result['arrays']['source_surface_m'], rtol=0, atol=1e-08):
        raise ValueError('fine bed source is not the valley surface')
    valley_cut = h0 - h1
    bed_cut = h1 - h2
    total = h0 - h2
    if _i52_np.any(valley_cut < -1e-08) or _i52_np.any(bed_cut < -1e-08):
        raise ValueError('fine valley or bed raises terrain')
    weights = _i52_np.ones(shape)
    weights[[0, -1], :] *= 0.5
    weights[:, [0, -1]] *= 0.5
    area_unit = params['fine_spacing_x_m'] * params['fine_spacing_z_m']
    recipe = valley_result['identity']['parameters']
    valley_area = float(_i52_np.sum((valley_cut > 1e-09) * weights) * area_unit)
    valley_volume = float(_i52_np.sum(valley_cut * weights) * area_unit)
    bed_volume = float(_i52_np.sum(bed_cut * weights) * area_unit)
    total_volume = float(_i52_np.sum(total * weights) * area_unit)
    total_area = float(_i52_np.sum((total > 1e-09) * weights) * area_unit)
    fine_domain = surface_result['arrays']['domain_mask']
    coarse_valley_cells = _i52_np.argwhere(valley_result['arrays']['valley_cut_m'] > 1e-09)
    if len(coarse_valley_cells):
        min_z, min_x = coarse_valley_cells.min(axis=0)
        max_z, max_x = coarse_valley_cells.max(axis=0)
        support_min_x, support_min_z = (max(0, min_x - 1), max(0, min_z - 1))
        support_max_x = min(coarse_shape[1] - 1, max_x + 1)
        support_max_z = min(coarse_shape[0] - 1, max_z + 1)
        if params['fine_origin_x_m'] > coarse['origin_x_m'] + support_min_x * coarse['spacing_x_m'] + 1e-08 or params['fine_origin_z_m'] > coarse['origin_z_m'] + support_min_z * coarse['spacing_z_m'] + 1e-08 or x[-1] < coarse['origin_x_m'] + support_max_x * coarse['spacing_x_m'] - 1e-08 or (z[-1] < coarse['origin_z_m'] + support_max_z * coarse['spacing_z_m'] - 1e-08):
            raise ValueError('fine grid omits requested valley geometry')
    failures = {'valley_depth': bool(_i52_np.any(valley_cut > recipe['max_valley_depth_m'] + 1e-09)), 'valley_area': valley_area > recipe['max_valley_area_m2'] + 1e-09, 'valley_volume': valley_volume > recipe['max_valley_volume_m3'] + 1e-09, 'total_volume': total_volume > recipe['max_total_cut_volume_m3'] + 1e-09, 'total_area': total_area > recipe['max_total_cut_area_m2'] + 1e-09, 'valley_domain': bool(_i52_np.any((valley_cut > 1e-09) & ~fine_domain)), 'valley_protection': bool(_i52_np.any((valley_cut > 1e-09) & surface_result['arrays']['protected_mask'])), 'coarse_valley': not valley_result['summary']['geometry_feasible'], 'surface_joint': surface_result['status'] != 'prepared'}
    summary = {'valley_area_m2': valley_area, 'valley_cut_volume_m3': valley_volume, 'bed_cut_volume_m3': bed_volume, 'total_cut_volume_m3': total_volume, 'total_cut_area_m2': total_area, 'failures': failures}
    arrays = {'source_surface_m': h0, 'valley_surface_m': h1, 'final_surface_m': h2, 'valley_cut_m': valley_cut, 'bed_cut_m': bed_cut, 'total_cut_m': total}
    if valley_result['identity']['algorithm'] == 'network-valley':
        arrays = {name: _i52_np.frombuffer(value.tobytes(), dtype=value.dtype).reshape(value.shape) for name, value in arrays.items()}
    identity = _i52_ArtifactIdentity('Terragenesis', 'valley-fine-ledger', 'valley-fine-ledger-v1', 0, {'valley_identity_sha256': valley_result['identity_sha256'], 'surface_identity_sha256': surface_result['identity_sha256'], 'origin_x_m': params['fine_origin_x_m'], 'origin_z_m': params['fine_origin_z_m'], 'spacing_x_m': params['fine_spacing_x_m'], 'spacing_z_m': params['fine_spacing_z_m'], 'shape_zx': list(shape), 'max_valley_depth_m': recipe['max_valley_depth_m'], 'max_valley_area_m2': recipe['max_valley_area_m2'], 'max_valley_volume_m3': recipe['max_valley_volume_m3'], 'max_total_cut_area_m2': recipe['max_total_cut_area_m2'], 'max_total_cut_volume_m3': recipe['max_total_cut_volume_m3'], 'summary_sha256': _i52_digest(summary), 'arrays_sha256': _i52_digest({name: _i52_array_hash(value) for name, value in arrays.items()})})
    return {'status': 'diagnostic_not_publishable' if any(failures.values()) else 'prepared', 'identity': identity.record(), 'identity_sha256': identity.sha256, 'summary': summary, 'arrays': arrays}

def save_fine_valley_ledger(result, path):
    from terrain_pipeline.artifacts.contracts import array_hash as _i52_array_hash
    if result['status'] != 'prepared':
        raise ValueError('failed fine valley ledger cannot be published')
    destination = _i52_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ('identity', 'identity_sha256', 'status', 'summary')}
    record['format_version'] = 1
    record['array_sha256'] = {name: _i52_array_hash(value) for name, value in result['arrays'].items()}
    temporary = None
    try:
        with _i52_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, delete=False, suffix='.npz') as stream:
            temporary = _i52_Path(stream.name)
            _i52_np.savez_compressed(stream, manifest=_i52_json.dumps(record, sort_keys=True), **result['arrays'])
        load_fine_valley_ledger(temporary)
        _i52_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def load_fine_valley_ledger(path):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i52_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i52_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i52_digest
    expected = {'source_surface_m', 'valley_surface_m', 'final_surface_m', 'valley_cut_m', 'bed_cut_m', 'total_cut_m'}
    with _i52_np.load(path, allow_pickle=False) as archive:
        record = _i52_json.loads(str(archive['manifest'].item()))
        if set(archive.files) != expected | {'manifest'} or set(record['array_sha256']) != expected:
            raise ValueError('invalid fine valley array set')
        arrays = {name: archive[name].copy() for name in expected}
    identity = _i52_ArtifactIdentity(**record['identity'])
    if record['format_version'] != 1 or record['status'] != 'prepared' or identity.algorithm != 'valley-fine-ledger' or (identity.algorithm_version != 'valley-fine-ledger-v1') or (identity.sha256 != record['identity_sha256']) or any((_i52_array_hash(arrays[name]) != record['array_sha256'][name] for name in expected)) or (_i52_digest({name: _i52_array_hash(value) for name, value in arrays.items()}) != identity.record()['parameters']['arrays_sha256']) or (_i52_digest(record['summary']) != identity.record()['parameters']['summary_sha256']):
        raise ValueError('invalid fine valley identity or hashes')
    shape = arrays['source_surface_m'].shape
    if len(shape) != 2 or any((arrays[name].shape != shape or arrays[name].dtype != _i52_np.float64 or (not _i52_np.isfinite(arrays[name]).all()) for name in expected)) or any((_i52_np.any(arrays[name] < -1e-09) for name in ('valley_cut_m', 'bed_cut_m', 'total_cut_m'))) or (not _i52_np.allclose(arrays['source_surface_m'] - arrays['valley_surface_m'], arrays['valley_cut_m'], rtol=0, atol=1e-08)) or (not _i52_np.allclose(arrays['valley_surface_m'] - arrays['final_surface_m'], arrays['bed_cut_m'], rtol=0, atol=1e-08)) or (not _i52_np.allclose(arrays['valley_cut_m'] + arrays['bed_cut_m'], arrays['total_cut_m'], rtol=0, atol=1e-08)) or any(record['summary']['failures'].values()):
        raise ValueError('invalid fine valley ledger')
    params = identity.record()['parameters']
    if params['shape_zx'] != list(shape) or params['spacing_x_m'] <= 0 or params['spacing_z_m'] <= 0 or any((not _i52_math.isfinite(params[name]) for name in ('origin_x_m', 'origin_z_m', 'spacing_x_m', 'spacing_z_m'))):
        raise ValueError('invalid fine valley grid')
    weights = _i52_np.ones(shape)
    weights[[0, -1], :] *= 0.5
    weights[:, [0, -1]] *= 0.5
    cell_area = params['spacing_x_m'] * params['spacing_z_m']
    summary = record['summary']
    computed = {'valley_area_m2': float(_i52_np.sum((arrays['valley_cut_m'] > 1e-09) * weights) * cell_area), 'valley_cut_volume_m3': float(_i52_np.sum(arrays['valley_cut_m'] * weights) * cell_area), 'bed_cut_volume_m3': float(_i52_np.sum(arrays['bed_cut_m'] * weights) * cell_area), 'total_cut_volume_m3': float(_i52_np.sum(arrays['total_cut_m'] * weights) * cell_area), 'total_cut_area_m2': float(_i52_np.sum((arrays['total_cut_m'] > 1e-09) * weights) * cell_area)}
    if any((not _i52_math.isclose(value, summary[name], abs_tol=1e-07) for name, value in computed.items())):
        raise ValueError('fine valley accounting mismatch')
    if _i52_np.any(arrays['valley_cut_m'] > params['max_valley_depth_m'] + 1e-09) or computed['valley_area_m2'] > params['max_valley_area_m2'] + 1e-09 or computed['valley_cut_volume_m3'] > params['max_valley_volume_m3'] + 1e-09 or (computed['total_cut_area_m2'] > params['max_total_cut_area_m2'] + 1e-09) or (computed['total_cut_volume_m3'] > params['max_total_cut_volume_m3'] + 1e-09):
        raise ValueError('fine valley exceeds budget')
    for value in arrays.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': record['status'], 'summary': record['summary'], 'arrays': arrays}

def save_valley_geometry(result, path):
    from terrain_pipeline.artifacts.contracts import array_hash as _i52_array_hash
    destination = _i52_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ('identity', 'identity_sha256', 'status', 'summary')}
    record['format_version'] = 1
    record['array_sha256'] = {name: _i52_array_hash(value) for name, value in result['arrays'].items()}
    temporary = None
    try:
        with _i52_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, delete=False, suffix='.npz') as stream:
            temporary = _i52_Path(stream.name)
            _i52_np.savez_compressed(stream, manifest=_i52_json.dumps(record, sort_keys=True), **result['arrays'])
        load_valley_geometry(temporary)
        _i52_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def load_valley_geometry(path):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i52_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i52_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i52_digest
    expected = {'source_height_m', 'valley_surface_m', 'final_bed_m', 'valley_cut_m', 'bed_cut_m', 'total_cut_m'}
    with _i52_np.load(path, allow_pickle=False) as archive:
        record = _i52_json.loads(str(archive['manifest'].item()))
        if set(archive.files) != expected | {'manifest'} or set(record['array_sha256']) != expected:
            raise ValueError('invalid valley array set')
        arrays = {name: archive[name].copy() for name in expected}
    identity = _i52_ArtifactIdentity(**record['identity'])
    if record['format_version'] != 1 or record['status'] != 'diagnostic_not_publishable' or identity.algorithm != 'valley-geometry' or (identity.algorithm_version != VALLEY_GEOMETRY_VERSION) or (identity.sha256 != record['identity_sha256']) or any((_i52_array_hash(arrays[name]) != record['array_sha256'][name] for name in expected)) or (_i52_digest({name: _i52_array_hash(value) for name, value in arrays.items()}) != identity.record()['parameters']['arrays_sha256']) or (_i52_digest(record['summary']) != identity.record()['parameters']['summary_sha256']):
        raise ValueError('invalid valley identity or hashes')
    shape = arrays['source_height_m'].shape
    if len(shape) != 2 or any((arrays[name].shape != shape or arrays[name].dtype != _i52_np.float64 or (not _i52_np.isfinite(arrays[name]).all()) for name in expected)) or any((_i52_np.any(arrays[name] < -1e-09) for name in ('valley_cut_m', 'bed_cut_m', 'total_cut_m'))) or (not _i52_np.allclose(arrays['source_height_m'] - arrays['valley_surface_m'], arrays['valley_cut_m'], rtol=0, atol=1e-09)) or (not _i52_np.allclose(arrays['valley_surface_m'] - arrays['final_bed_m'], arrays['bed_cut_m'], rtol=0, atol=1e-09)) or (not _i52_np.allclose(arrays['valley_cut_m'] + arrays['bed_cut_m'], arrays['total_cut_m'], rtol=0, atol=1e-09)):
        raise ValueError('invalid valley geometry ledger')
    for value in arrays.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': record['status'], 'arrays': arrays, 'summary': record['summary']}
NETWORK_VALLEY_VERSION = 'network-valley-irregular-v2'
PLANNING_VERSION = 'network-valley-planning-irregular-v2'

@_i12_dataclass(frozen=True)
class NetworkValleyRecipe:
    """Widths are nominal channel widths times a ratio, bounded in metres."""
    width_multiplier: float
    min_width_m: float
    max_width_m: float
    min_floor_slope_m_per_m: float

    def __post_init__(self):
        for name, value in _i12_asdict(self).items():
            if isinstance(value, bool) or not _i12_math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if self.min_width_m > self.max_width_m:
            raise ValueError('valley width limits must be ordered')

def _array_digest(arrays):
    from terrain_pipeline.artifacts.contracts import array_hash as _i12_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i12_digest
    return _i12_digest({name: {'sha256': _i12_array_hash(value), 'shape': list(value.shape), 'dtype': value.dtype.str} for name, value in arrays.items()})

def _immutable(value):
    contiguous = _i12_np.ascontiguousarray(value)
    return _i12_np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)

def _freeze_plan(plan):
    plan['arrays'] = {name: _immutable(value) for name, value in plan['arrays'].items()}
    return plan

def _validated_source_plan(plan, recipe=None):
    """Recompute every derived field: legacy plan identities hash only sources."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i12_ArtifactIdentity
    try:
        identity = _i12_ArtifactIdentity(**plan['identity'])
        params = identity.record()['parameters']
        source_recipe = ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})
        if identity.algorithm != 'metric-channel-plan' or identity.algorithm_version != PLAN_VERSION or identity.backend != 'Terragenesis' or (identity.sha256 != plan['identity_sha256']) or (plan['status'] != 'diagnostic_not_publishable'):
            raise ValueError('invalid source plan identity')
        if recipe is not None and _i12_asdict(source_recipe) != _i12_asdict(recipe):
            raise ValueError('channel recipe mismatch with source plan')
        arrays = plan['arrays']
        expected = plan_channel(arrays['source_height_m'], arrays['receiver'], arrays['order'], arrays['outlet_mask'], arrays['discharge_m3_s'], params['spacing_x_m'], params['spacing_z_m'], params['origin_x_m'], params['origin_z_m'], params['sea_level_elevation_m'], params['source_identity'], source_recipe)
        if expected['identity_sha256'] != identity.sha256 or set(arrays) != set(expected['arrays']):
            raise ValueError('source plan inputs differ from identity')
        for name, expected_array in expected['arrays'].items():
            actual = _i12_np.asarray(arrays[name])
            if actual.shape != expected_array.shape or actual.dtype != expected_array.dtype or (not _i12_np.array_equal(actual, expected_array)):
                raise ValueError(f'source plan field differs from recomputed plan: {name}')
        return _freeze_plan(expected)
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError('invalid source plan') from error

def _plan_nodes(plan, recipe, channel_recipe):
    arrays = plan['arrays']
    params = plan['identity']['parameters']
    source = arrays['source_height_m']
    active = arrays['channel_mask'].ravel()
    receiver = arrays['receiver']
    donors = _i12_np.flatnonzero(active & (receiver >= 0))
    if not len(donors):
        raise ValueError('network valley requires at least one active graph edge')
    edges = _i12_np.column_stack((donors, receiver[donors])).astype(_i12_np.int64)
    columns = source.shape[1]
    delta_x = (edges[:, 1] % columns - edges[:, 0] % columns) * params['spacing_x_m']
    delta_z = (edges[:, 1] // columns - edges[:, 0] // columns) * params['spacing_z_m']
    lengths = _i12_np.hypot(delta_x, delta_z)
    floor = source.ravel().copy()
    depth = arrays['nominal_depth_m'].ravel()
    for donor in arrays['order'][::-1]:
        target = receiver[donor]
        if target < 0 or not active[donor]:
            continue
        length = _i12_math.hypot((target % columns - donor % columns) * params['spacing_x_m'], (target // columns - donor // columns) * params['spacing_z_m'])
        floor_limit = floor[donor] - recipe.min_floor_slope_m_per_m * length
        bed_limit = floor[donor] - depth[donor] + depth[target] - channel_recipe.min_bed_slope_m_per_m * length
        floor[target] = min(floor[target], floor_limit, bed_limit)
    width = _i12_np.zeros(source.shape, dtype=_i12_np.float64)
    with _i12_np.errstate(over='ignore', invalid='ignore'):
        scaled = arrays['nominal_width_m'].ravel()[active] * recipe.width_multiplier
    if not _i12_np.isfinite(scaled).all() or not _i12_np.isfinite(floor).all() or (not _i12_np.isfinite(lengths).all()):
        raise ValueError('network valley geometry overflows')
    width.ravel()[active] = _i12_np.clip(scaled, recipe.min_width_m, recipe.max_width_m)
    return {'floor_elevation_m': floor.reshape(source.shape), 'width_m': width, 'active_mask': active.reshape(source.shape).copy(), 'active_edges': edges, 'edge_length_m': lengths}

def prepare_network_valley(plan, domain_mask, protected_mask, network_recipe, valley_recipe, channel_recipe):
    """Return a coarse diagnostic compatible with evaluate_fine_valley_ledger.

    Every active donor/receiver segment is rasterized independently in its local
    bounding box. Node floors start at H0 and propagate both floor and nominal-bed
    slope constraints upstream to downstream, sharing a single floor and width at
    each confluence. The cosine cut envelope is a union, not a summed excavation.
    Budget, domain and protection failures remain diagnostics, never clipped passes.
    No outlet legality is inferred here; only fine joint acceptance can publish.
    """
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i12_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i12_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i12_digest
    if not isinstance(network_recipe, NetworkValleyRecipe) or not isinstance(valley_recipe, ValleyGeometryRecipe) or (not isinstance(channel_recipe, ChannelRecipe)):
        raise ValueError('network, valley and channel recipes required')
    source_plan = _validated_source_plan(plan, channel_recipe)
    source = source_plan['arrays']['source_height_m']
    domain = _i12_np.asarray(domain_mask)
    protected = _i12_np.asarray(protected_mask)
    if domain.shape != source.shape or protected.shape != source.shape or domain.dtype != bool or (protected.dtype != bool):
        raise ValueError('domain and protected masks must be matching boolean grids')
    domain = _immutable(domain)
    protected = _immutable(protected)
    network = _plan_nodes(source_plan, network_recipe, channel_recipe)
    params = source_plan['identity']['parameters']
    edges = network['active_edges']
    points = _i12_np.stack((params['origin_x_m'] + edges % source.shape[1] * params['spacing_x_m'], params['origin_z_m'] + edges // source.shape[1] * params['spacing_z_m']), axis=2)
    if not _i12_np.isfinite(points).all():
        raise ValueError('network world coordinates overflow')
    requested = _rasterize_valley_edges(source, params, points, network['floor_elevation_m'].ravel()[edges], network['width_m'].ravel()[edges], local_bounds=True)
    if not _i12_np.isfinite(requested).all():
        raise ValueError('network valley cut overflows')
    network['domain_mask'] = domain
    network['protected_mask'] = protected
    network = {name: _immutable(value) for name, value in network.items()}
    planning = _i12_ArtifactIdentity('Terragenesis', 'network-valley-planning', PLANNING_VERSION, 0, {'network_recipe': _i12_asdict(network_recipe), 'valley_recipe': _i12_asdict(valley_recipe), 'geometry_coordinates': 'legacy_native_cell_anchors_with_irregular_graph_topology', 'channel_recipe': _i12_asdict(channel_recipe), 'source_plan_sha256': source_plan['identity_sha256'], 'source_plan_identity': source_plan['identity'], 'source_arrays_sha256': _array_digest(source_plan['arrays']), 'network_sha256': _array_digest(network), 'requested_cut_sha256': _i12_array_hash(requested)})
    arrays, replanned, summary = _prepare_valley_cut(source_plan, requested, domain, protected, valley_recipe, channel_recipe, planning.sha256)
    failures = summary['failures']
    failures['total_area'] = summary['total_cut_area_m2'] > valley_recipe.max_total_cut_area_m2 + 1e-09
    failures['active_domain'] = bool(_i12_np.any(network['active_mask'] & ~domain))
    failures['active_protection'] = bool(_i12_np.any(network['active_mask'] & protected))
    summary['geometry_feasible'] = not any(failures.values())
    arrays = {name: _immutable(value) for name, value in arrays.items()}
    replanned = _freeze_plan(replanned)
    identity = _i12_ArtifactIdentity('Terragenesis', 'network-valley', NETWORK_VALLEY_VERSION, 0, {**_i12_asdict(valley_recipe), 'source_plan_sha256': source_plan['identity_sha256'], 'planning_identity_sha256': planning.sha256, 'replanned_sha256': replanned['identity_sha256'], 'network_sha256': _array_digest(network), 'arrays_sha256': _array_digest(arrays), 'replanned_arrays_sha256': _array_digest(replanned['arrays']), 'summary_sha256': _i12_digest(summary)})
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'planning_identity': planning.record(), 'planning_identity_sha256': planning.sha256, 'status': 'diagnostic_not_publishable', 'arrays': arrays, 'network': network, 'replanned_plan': replanned, 'summary': summary}

def validate_network_valley(result):
    """Reject altered automatic geometry, planning provenance or replanned fields."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i12_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i12_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i12_digest
    try:
        identity = _i12_ArtifactIdentity(**result['identity'])
        planning = _i12_ArtifactIdentity(**result['planning_identity'])
        params = identity.record()['parameters']
        planned = planning.record()['parameters']
        replanned = _validated_source_plan(result['replanned_plan'])
        source_identity = _i12_ArtifactIdentity(**planned['source_plan_identity'])
        source_params = source_identity.record()['parameters']
        channel_recipe = ChannelRecipe(**planned['channel_recipe'])
        NetworkValleyRecipe(**planned['network_recipe'])
        ValleyGeometryRecipe(**planned['valley_recipe'])
        original = plan_channel(result['arrays']['source_height_m'], replanned['arrays']['receiver'], replanned['arrays']['order'], replanned['arrays']['outlet_mask'], replanned['arrays']['discharge_m3_s'], source_params['spacing_x_m'], source_params['spacing_z_m'], source_params['origin_x_m'], source_params['origin_z_m'], source_params['sea_level_elevation_m'], source_params['source_identity'], channel_recipe)
        if identity.algorithm != 'network-valley' or identity.algorithm_version != NETWORK_VALLEY_VERSION or identity.sha256 != result['identity_sha256'] or (planning.algorithm != 'network-valley-planning') or (planning.algorithm_version != PLANNING_VERSION) or (planning.sha256 != result['planning_identity_sha256']) or (source_identity.sha256 != planned['source_plan_sha256']) or (source_identity.sha256 != params['source_plan_sha256']) or (original['identity_sha256'] != source_identity.sha256) or (_array_digest(original['arrays']) != planned['source_arrays_sha256']) or any((params[name] != value for name, value in planned['valley_recipe'].items())) or (_i12_array_hash(result['arrays']['valley_cut_m']) != planned['requested_cut_sha256']) or (params['planning_identity_sha256'] != planning.sha256) or (replanned['identity']['parameters']['source_identity'] != planning.sha256) or (params['replanned_sha256'] != replanned['identity_sha256']) or (params['replanned_arrays_sha256'] != _array_digest(replanned['arrays'])) or (params['network_sha256'] != _array_digest(result['network'])) or (planned['network_sha256'] != params['network_sha256']) or (params['arrays_sha256'] != _array_digest(result['arrays'])) or (params['summary_sha256'] != _i12_digest(result['summary'])) or (result['status'] != 'diagnostic_not_publishable'):
            raise ValueError('network valley identity or arrays mismatch')
        if not _i12_np.array_equal(result['arrays']['valley_surface_m'], replanned['arrays']['source_height_m']) or not _i12_np.array_equal(result['arrays']['final_bed_m'], replanned['arrays']['bounded_bed_m']):
            raise ValueError('network valley replan source mismatch')
        expected = prepare_network_valley(original, result['network']['domain_mask'], result['network']['protected_mask'], NetworkValleyRecipe(**planned['network_recipe']), ValleyGeometryRecipe(**planned['valley_recipe']), channel_recipe)
        if expected['identity_sha256'] != identity.sha256 or expected['planning_identity_sha256'] != planning.sha256:
            raise ValueError('network valley geometry or budget semantics mismatch')
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('invalid network valley result') from error

def save_network_valley(result, path):
    """Atomically save a validated diagnostic bundle, never overwrite or publish."""
    destination = _i12_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    snapshot = _i12_deepcopy(result)
    validate_network_valley(snapshot)
    record = {name: snapshot[name] for name in ('identity', 'identity_sha256', 'planning_identity', 'planning_identity_sha256', 'status', 'summary')}
    record['format_version'] = 1
    record['replanned_plan'] = {name: snapshot['replanned_plan'][name] for name in ('identity', 'identity_sha256', 'status')}
    payload = {f'{group}__{name}': value for group, arrays in (('geometry', snapshot['arrays']), ('network', snapshot['network']), ('replanned', snapshot['replanned_plan']['arrays'])) for name, value in arrays.items()}
    record['payload_sha256'] = _array_digest(payload)
    temporary = None
    try:
        with _i12_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, prefix=f'.{destination.name}-', suffix='.npz', delete=False) as stream:
            temporary = _i12_Path(stream.name)
            _i12_np.savez_compressed(stream, manifest=_i12_json.dumps(record, sort_keys=True), **payload)
        load_network_valley(temporary)
        _i12_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def load_network_valley(path):
    """Load immutable H0/H1/H2, complete network and replan with semantic checks."""
    try:
        with _i12_np.load(path, allow_pickle=False) as archive:
            record = _i12_json.loads(str(archive['manifest'].item()))
            payload = {name: archive[name].copy() for name in archive.files if name != 'manifest'}
        if record['format_version'] != 1 or record['payload_sha256'] != _array_digest(payload):
            raise ValueError('invalid network valley archive format or payload')
        groups = {name: {} for name in ('geometry', 'network', 'replanned')}
        for key, value in payload.items():
            group, separator, name = key.partition('__')
            if group not in groups or not separator or (not name):
                raise ValueError('invalid network valley archive fields')
            groups[group][name] = _immutable(value)
        result = {name: record[name] for name in ('identity', 'identity_sha256', 'planning_identity', 'planning_identity_sha256', 'status', 'summary')}
        result['arrays'] = groups['geometry']
        result['network'] = groups['network']
        result['replanned_plan'] = {**record['replanned_plan'], 'arrays': groups['replanned']}
        validate_network_valley(result)
        return result
    except (KeyError, TypeError, AttributeError, _i12_json.JSONDecodeError) as error:
        raise ValueError('invalid network valley archive') from error

def solve_shared_bed(source_m, arcs, max_cut_m=4.0):
    """Return bed and component acceptance; an infeasible component has no bed.

    Vertices represent physical sample locations, arcs run downstream. A weak
    component is committed only if every downstream constraint fits the cap.
    """
    source = _i13_np.asarray(source_m, dtype=_i13_np.float64)
    arcs = _i13_np.asarray(arcs, dtype=_i13_np.int64).reshape(-1, 2)
    if not _i13_np.isfinite(source).all() or not _i13_np.isfinite(max_cut_m) or max_cut_m <= 0:
        raise ValueError('finite source and positive cut cap required')
    if arcs.size and (arcs.min() < 0 or arcs.max() >= len(source)):
        raise ValueError('arc vertex out of bounds')
    outgoing = [[] for _ in source]
    adjacent = [[] for _ in source]
    indegree = _i13_np.zeros(len(source), dtype=_i13_np.int64)
    for a, b in arcs:
        outgoing[a].append(int(b))
        adjacent[a].append(int(b))
        adjacent[b].append(int(a))
        indegree[b] += 1
    component = _i13_np.full(len(source), -1, dtype=_i13_np.int64)
    result = _i13_np.full(len(source), _i13_np.nan)
    reasons = []
    for start in range(len(source)):
        if component[start] >= 0:
            continue
        cid = len(reasons)
        stack = [start]
        component[start] = cid
        vertices = []
        while stack:
            v = stack.pop()
            vertices.append(v)
            for w in adjacent[v]:
                if component[w] < 0:
                    component[w] = cid
                    stack.append(w)
        degree = {v: int(indegree[v]) for v in vertices}
        queue = _i13_deque((v for v in vertices if degree[v] == 0))
        bed = {v: float(source[v]) for v in vertices}
        visited = 0
        while queue:
            v = queue.popleft()
            visited += 1
            for w in outgoing[v]:
                bed[w] = min(bed[w], bed[v])
                degree[w] -= 1
                if degree[w] == 0:
                    queue.append(w)
        if visited != len(vertices):
            reasons.append('directed_cycle')
        elif any((source[v] - bed[v] > max_cut_m + 1e-08 for v in vertices)):
            reasons.append('downstream_cut_cap')
        else:
            reasons.append('accepted')
            for v in vertices:
                result[v] = bed[v]
    return (result, component, reasons)

def solve_shared_bed_scc(source_m, arcs, max_cut_m=4.0):
    """Close geometric inequalities; SCCs are flat, never flow connections.

    Original directed arcs remain the sole hydraulic topology. Any weak
    component whose closure exceeds the source-relative bound is withheld.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    source = _i13_np.asarray(source_m, dtype=_i13_np.float64)
    arcs = _i13_np.asarray(arcs, dtype=_i13_np.int64).reshape(-1, 2)
    if not _i13_np.isfinite(source).all() or not _i13_np.isfinite(max_cut_m) or max_cut_m <= 0:
        raise ValueError('finite source and positive cut cap required')
    if arcs.size and (arcs.min() < 0 or arcs.max() >= len(source)):
        raise ValueError('arc vertex out of bounds')
    graph = coo_matrix((_i13_np.ones(len(arcs)), (arcs[:, 0], arcs[:, 1])), shape=(len(source), len(source))).tocsr()
    count, strong = connected_components(graph, directed=True, connection='strong')
    _, weak = connected_components(graph, directed=True, connection='weak')
    strong_source = _i13_np.full(count, _i13_np.inf)
    _i13_np.minimum.at(strong_source, strong, source)
    condensed = _i13_np.column_stack((strong[arcs[:, 0]], strong[arcs[:, 1]]))
    condensed = condensed[condensed[:, 0] != condensed[:, 1]]
    strong_bed, _, strong_reasons = solve_shared_bed(strong_source, condensed, max_cut_m=_i13_np.finfo(float).max)
    assert all((reason == 'accepted' for reason in strong_reasons))
    candidate = strong_bed[strong]
    bad = _i13_np.zeros(int(weak.max()) + 1 if len(weak) else 0, dtype=bool)
    _i13_np.logical_or.at(bad, weak, source - candidate > max_cut_m + 1e-08)
    candidate[bad[weak]] = _i13_np.nan
    return (candidate, weak, strong, bad)

def bounded_monotone_path(bed, allowed, start, end, max_cut_m=4.0):
    """Find a path with maximal attainable running bed and bounded cuts."""
    import heapq
    bed = _i13_np.asarray(bed, dtype=float)
    allowed = _i13_np.asarray(allowed, dtype=bool)
    if not allowed[start] or not allowed[end]:
        return None
    best = {start: float(bed[start])}
    previous = {}
    queue = [(-best[start], start)]
    while queue:
        neg, cell = heapq.heappop(queue)
        level = -neg
        if level < best[cell]:
            continue
        if cell == end:
            path = [cell]
            while cell != start:
                cell = previous[cell]
                path.append(cell)
            return path[::-1]
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == dc == 0:
                    continue
                nxt = (cell[0] + dr, cell[1] + dc)
                if not (0 <= nxt[0] < bed.shape[0] and 0 <= nxt[1] < bed.shape[1] and allowed[nxt]):
                    continue
                height = bed[nxt]
                if height - level > max_cut_m + 1e-08:
                    continue
                candidate = min(level, height)
                if candidate > best.get(nxt, -_i13_np.inf):
                    best[nxt] = candidate
                    previous[nxt] = cell
                    heapq.heappush(queue, (-candidate, nxt))
    return None

@_i19_dataclass(frozen=True)
class FormativeSection:
    width_m: _i19_np.ndarray
    baseline_width_m: _i19_np.ndarray
    deposited_solid_m3: _i19_np.ndarray | None
    eroded_solid_m3: _i19_np.ndarray | None

def formative_section(formative_q_m3_s, bed_resistance, bank_resistance, fracture, bank_cohesion, *, reference_discharge_m3_s=1.0, reference_width_m=4.0, min_width_m=0.0, max_width_m=120.0, width_exponent=0.45, sediment_supply_solid_m3=None, transport_capacity_solid_m3=None, erodible_solid_m3=None):
    """Formative incision width and bounded interval exchange; volumes are solid m³.

    Resistance may already include fracture: in that case pass fracture=0 to
    avoid counting it twice. Exchange is a scenario estimate, not a routed ledger.
    """
    q, bed, bank, frac, cohesion = _i19_np.broadcast_arrays(*[_i19_np.asarray(v, dtype=float) for v in (formative_q_m3_s, bed_resistance, bank_resistance, fracture, bank_cohesion)])
    if not _i19_np.isfinite(q).all() or _i19_np.any(q < 0):
        raise ValueError('formative discharge must be finite and nonnegative')
    for value in (bed, bank, frac, cohesion):
        if not _i19_np.isfinite(value).all() or _i19_np.any((value < 0) | (value > 1)):
            raise ValueError('material indices must be finite and in [0, 1]')
    params = _i19_np.asarray([reference_discharge_m3_s, reference_width_m, min_width_m, max_width_m, width_exponent], dtype=float)
    if not _i19_np.isfinite(params).all() or params[0] <= 0 or params[1] <= 0 or (params[2] < 0) or (params[3] < params[2]) or (params[4] <= 0):
        raise ValueError('invalid width parameters')
    effective_bank = bank * (1 - 0.5 * frac)
    raw = reference_width_m * (q / reference_discharge_m3_s) ** width_exponent * (1 + 1.5 * bed) * (0.5 + 1.5 * (1 - effective_bank)) * (1 - 0.35 * cohesion)
    baseline = _i19_np.where(q > 0, _i19_np.clip(raw, min_width_m, max_width_m), 0.0)
    supplied = (sediment_supply_solid_m3, transport_capacity_solid_m3, erodible_solid_m3)
    if all((v is None for v in supplied)):
        return FormativeSection(baseline, baseline, None, None)
    if any((v is None for v in supplied)):
        raise ValueError('supply, capacity and inventory must be known together')
    supply, capacity, inventory, _ = _i19_np.broadcast_arrays(*[_i19_np.asarray(v, dtype=float) for v in supplied], q)
    for value in (supply, capacity, inventory):
        if not _i19_np.isfinite(value).all() or _i19_np.any(value < 0):
            raise ValueError('sediment volumes must be finite and nonnegative')
    deposited = _i19_np.maximum(supply - capacity, 0.0)
    eroded = _i19_np.minimum(_i19_np.maximum(capacity - supply, 0.0), inventory)
    scale = capacity + supply + inventory
    feedback = _i19_np.divide(eroded - deposited, scale, out=_i19_np.zeros_like(scale), where=scale > 0)
    width = _i19_np.where(q > 0, _i19_np.clip(raw * (1 + 0.4 * feedback), min_width_m, max_width_m), 0.0)
    return FormativeSection(width, baseline, deposited, eroded)

def section_from_routed_budget(formative_q_m3_s, bed_resistance, bank_resistance, fracture, bank_cohesion, *, incoming_solid_m3, external_solid_m3, capacity_solid_m3, eroded_loose_solid_m3, eroded_rock_m3, deposited_solid_m3, initial_mobile_solid_m3=0.0, **width_parameters):
    """Apply already committed routed exchange to a *next* formative section.

    All volumes refer to one solver interval; no stock is changed or charged here.
    The solver remains authoritative for mass balance. This lagged update is not a
    re-solve of the hydraulics or sediment under the resulting new section.
    """
    base = formative_section(formative_q_m3_s, bed_resistance, bank_resistance, fracture, bank_cohesion, **width_parameters)
    values = _i19_np.broadcast_arrays(*[_i19_np.asarray(v, dtype=float) for v in (base.baseline_width_m, incoming_solid_m3, external_solid_m3, capacity_solid_m3, eroded_loose_solid_m3, eroded_rock_m3, deposited_solid_m3, initial_mobile_solid_m3)])
    baseline, incoming, external, capacity, loose, rock, deposited, mobile = values
    for value in values[1:]:
        if not _i19_np.isfinite(value).all() or _i19_np.any(value < 0):
            raise ValueError('routed interval volumes must be finite and nonnegative')
    eroded = loose + rock
    scale = incoming + external + mobile + capacity + eroded + deposited
    feedback = _i19_np.divide(eroded - deposited, scale, out=_i19_np.zeros_like(scale), where=scale > 0)
    low = width_parameters.get('min_width_m', 0.0)
    high = width_parameters.get('max_width_m', 120.0)
    width = _i19_np.where(baseline > 0, _i19_np.clip(baseline * (1 + 0.4 * feedback), low, high), 0.0)
    return FormativeSection(width, baseline, deposited.copy(), eroded.copy())
MAX_CHANNEL_NODES = 4096
MAX_FORCING_BYTES = 128 * 1024 * 1024
TERMINAL_KINDS = ('interior', 'open_outflow', 'closed_wall', 'unknown_boundary')
GEOMETRY_SEMANTICS = {'length_m': 'storage_control_length_not_receiver_distance', 'receiver_distance_m': 'positive_horizontal_receiver_distance_zero_at_terminals', 'bed_slope': 'interior_bed_drop_over_receiver_distance', 'open_outflow_slope': 'prescribed_positive_boundary_gradient_no_receiver'}

def receiver_distances(node_xz_m, receiver):
    distance = _i24_np.zeros(receiver.size, _i24_np.float64)
    interior = receiver >= 0
    distance[interior] = _i24_np.linalg.norm(node_xz_m[interior] - node_xz_m[receiver[interior]], axis=1)
    return distance

def validate_receiver_acyclic(receiver):
    """Visit each receiver once, including DAGs whose indices are not sorted."""
    color = _i24_np.zeros(receiver.size, _i24_np.uint8)
    for start in range(receiver.size):
        node = start
        path = []
        while node >= 0 and color[node] == 0:
            color[node] = 1
            path.append(node)
            node = int(receiver[node])
        if node >= 0 and color[node] == 1:
            raise ValueError('receiver graph must be acyclic')
        color[path] = 2

def validate_channel_geometry_identity(receiver, bed, slope, distance):
    """Check physical edges, not finite-volume storage control lengths."""
    if not isinstance(distance, _i24_np.ndarray) or distance.dtype != _i24_np.float64 or distance.shape != receiver.shape or (not _i24_np.isfinite(distance).all()):
        raise ValueError('finite float64 receiver_distance_m required')
    interior = receiver >= 0
    if _i24_np.any(distance[interior] <= 0.0) or _i24_np.any(distance[~interior] != 0.0):
        raise ValueError('receiver distance must be positive on edges and zero at terminals')
    with _i24_np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        drop = bed[interior] - bed[receiver[interior]]
        expected = drop / distance[interior]
    if not _i24_np.isfinite(expected).all() or _i24_np.any(drop <= 0.0):
        raise ValueError('channel receiver bed must be strictly downhill')
    if not _i24_np.allclose(slope[interior], expected, rtol=1e-09, atol=0.0):
        raise ValueError('channel bed slope inconsistent with receiver geometry')

def _metric_channel_state_sha(value):
    if not isinstance(value, str) or len(value) != 64 or any((c not in '0123456789abcdef' for c in value)):
        raise ValueError('lowercase SHA256 required')

def _float_array(value, shape, name, *, positive=False, nonnegative=False):
    from terrain_pipeline.common_infra import readonly as _i24_readonly
    if not isinstance(value, _i24_np.ndarray) or value.dtype != _i24_np.float64 or value.shape != shape:
        raise ValueError(name + ' must be float64 with shape ' + str(shape))
    if not _i24_np.isfinite(value).all() or (positive and _i24_np.any(value <= 0.0)) or (nonnegative and _i24_np.any(value < 0.0)):
        raise ValueError(name + ' must contain finite physical values')
    return _i24_readonly(value)

@_i24_dataclass(frozen=True)
class ChannelNetwork:
    receiver: _i24_np.ndarray
    length_m: _i24_np.ndarray
    width_m: _i24_np.ndarray
    bed_elevation_m: _i24_np.ndarray
    bed_slope: _i24_np.ndarray
    roughness: _i24_np.ndarray
    max_depth_m: _i24_np.ndarray
    terminal_kind: _i24_np.ndarray
    source_identity_sha256: str
    section_source: str
    roughness_source: str
    receiver_distance_m: _i24_np.ndarray | None = None

    def __post_init__(self):
        from terrain_pipeline.common_infra import readonly as _i24_readonly
        receiver = self.receiver
        if not isinstance(receiver, _i24_np.ndarray) or receiver.dtype != _i24_np.int64 or receiver.ndim != 1 or (not 1 <= receiver.size <= MAX_CHANNEL_NODES):
            raise ValueError('bounded int64 receiver array required')
        n = receiver.size
        if _i24_np.any((receiver < -1) | (receiver >= n) | (receiver == _i24_np.arange(n))):
            raise ValueError('invalid channel receiver')
        for name in ('length_m', 'width_m', 'bed_elevation_m', 'bed_slope', 'roughness', 'max_depth_m'):
            value = _float_array(getattr(self, name), (n,), name, positive=name in ('length_m', 'width_m', 'roughness', 'max_depth_m'), nonnegative=name == 'bed_slope')
            object.__setattr__(self, name, value)
        kind = self.terminal_kind
        if not isinstance(kind, _i24_np.ndarray) or kind.shape != (n,) or kind.dtype.kind != 'U':
            raise ValueError('Unicode terminal_kind array required')
        if not _i24_np.isin(kind, TERMINAL_KINDS).all():
            raise ValueError('unrecognized terminal_kind')
        if _i24_np.any((receiver == -1) != (kind != 'interior')):
            raise ValueError('terminal_kind must match receiver topology')
        if _i24_np.any((self.bed_slope <= 0.0) & _i24_np.isin(kind, ('interior', 'open_outflow'))):
            raise ValueError('positive slope required for active transport and open outflow')
        validate_receiver_acyclic(receiver)
        _metric_channel_state_sha(self.source_identity_sha256)
        for name in ('section_source', 'roughness_source'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(name + ' provenance required')
        object.__setattr__(self, 'receiver', _i24_readonly(receiver))
        object.__setattr__(self, 'terminal_kind', _i24_readonly(kind.astype('U24')))
        distance = self.receiver_distance_m
        if distance is None:
            distance = _i24_np.where(receiver >= 0, self.length_m, 0.0)
        validate_channel_geometry_identity(receiver, self.bed_elevation_m, self.bed_slope, distance)
        object.__setattr__(self, 'receiver_distance_m', _i24_readonly(distance))

@_i24_dataclass(frozen=True)
class ChannelForcing:
    time_seconds: _i24_np.ndarray
    local_q_m3_s: _i24_np.ndarray
    source_identity_sha256: str

    def __post_init__(self):
        from terrain_pipeline.common_infra import readonly as _i24_readonly
        time = self.time_seconds
        if not isinstance(time, _i24_np.ndarray) or time.dtype != _i24_np.float64 or time.ndim != 1 or (not 2 <= time.size <= 100001) or (not _i24_np.isfinite(time).all()) or _i24_np.any(time < 0.0) or (not _i24_np.isfinite(_i24_np.diff(time)).all()) or _i24_np.any(_i24_np.diff(time) <= 0.0):
            raise ValueError('strictly increasing finite float64 physical times required')
        q = self.local_q_m3_s
        if not isinstance(q, _i24_np.ndarray) or q.dtype != _i24_np.float64 or q.ndim != 2 or (q.shape[0] != time.size - 1) or (not 1 <= q.shape[1] <= MAX_CHANNEL_NODES):
            raise ValueError('local discharge must be float64 [interval,node]')
        if q.nbytes + time.nbytes > MAX_FORCING_BYTES or not _i24_np.isfinite(q).all() or _i24_np.any(q < 0.0):
            raise ValueError('local discharge exceeds resource or physical bounds')
        _metric_channel_state_sha(self.source_identity_sha256)
        object.__setattr__(self, 'time_seconds', _i24_readonly(time))
        object.__setattr__(self, 'local_q_m3_s', _i24_readonly(q))

@_i24_dataclass(frozen=True)
class ChannelConfig:
    max_dt_seconds: float = 1.0
    cfl: float = 0.8
    max_steps: int = 100000
    min_dt_seconds: float = 1e-08

    def __post_init__(self):
        for name in ('max_dt_seconds', 'cfl', 'min_dt_seconds'):
            value = getattr(self, name)
            if isinstance(value, (bool, _i24_np.bool_)) or not isinstance(value, (int, float, _i24_np.integer, _i24_np.floating)) or (not _i24_math.isfinite(value)) or (value <= 0.0):
                raise ValueError(name + ' must be finite positive')
            object.__setattr__(self, name, float(value))
        if self.cfl > 1.0 or self.min_dt_seconds > self.max_dt_seconds:
            raise ValueError('CFL or step bounds invalid')
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 1000000:
            raise ValueError('max_steps must be a bounded positive integer')

def file_sha256(path):
    digest = _i16_hashlib.sha256()
    with _i16_Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def select_saved_reach(edges, status, bed, q, *, minimum_nodes=60):
    """Choose the highest-Q upstream start with >= minimum bounded river nodes."""
    edges = _i16_np.asarray(edges)
    good = (status == 0) & (bed[edges[:, 0]] > bed[edges[:, 1]] + 1e-08) & (q[edges[:, 0]] > 0) & (q[edges[:, 1]] >= q[edges[:, 0]])
    receiver = {int(a): int(b) for a, b in edges[good]}
    best = None
    for start in receiver:
        path = []
        seen = set()
        node = start
        while node in receiver and node not in seen:
            path.append(node)
            seen.add(node)
            node = receiver[node]
        if node in seen:
            continue
        path.append(node)
        if len(path) >= minimum_nodes and (best is None or (q[start], len(path)) > (q[best[0]], len(best))):
            best = path
    if best is None:
        raise ValueError('no qualifying bounded native network reach')
    return _i16_np.asarray(best, dtype=_i16_np.int64)

def _normal_depth(q, width, slope, roughness):

    def discharge(depth):
        area = width * depth
        return area * (area / (width + 2 * depth)) ** (2 / 3) * slope ** 0.5 / roughness
    upper = 1.0
    while discharge(upper) < q:
        upper *= 2.0
    return _i16_brentq(lambda h: discharge(h) - q, 0.0, upper)

def construct_saved_width_reach(root, *, minimum_nodes=60, network_directory='native-network-v4', event_directory='native-event-v3', event_time_directory='native-event-v1', terrain_directory='terrain-v3'):
    """Return arrays and metadata for a saved TD/native-event connected reach.

    Saved interval-2 Q is a fixed formative scenario, not historical bankfull.
    Homogeneous sediment stocks and inlet supply are explicit scenarios. The
    sediment replay uses baseline sections and frozen, normal-flow hydraulics.
    """
    from terrain_pipeline.common_infra import identity as _i16_identity
    from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters as _i16_MaterialParameters
    from terrain_pipeline.surface_rivers.metric_upstream_sediment import route_daily_sediment as _i16_route_daily_sediment
    from terrain_pipeline.geology import sample_lithology_points as _i16_sample_lithology_points
    root = _i16_Path(root)
    network_dir = root / network_directory
    event_dir = root / event_directory
    names = ('node_id', 'node_xz_m', 'node_bed_m', 'node_raw_bed_m', 'node_q_m3_s', 'edge_nodes', 'edge_status')
    data = {name: _i16_np.load(network_dir / (name + '.npy'), mmap_mode='r') for name in names}
    manifest = _i16_json.loads((network_dir / 'manifest.json').read_text(encoding='utf8'))
    event_manifest = _i16_json.loads((event_dir / 'manifest.json').read_text(encoding='utf8'))
    if manifest['source_identity'] != event_manifest['source_identity']:
        raise ValueError('terrain/event identities differ')
    selected = select_saved_reach(data['edge_nodes'], data['edge_status'], data['node_bed_m'], data['node_q_m3_s'], minimum_nodes=minimum_nodes)
    xz = _i16_np.asarray(data['node_xz_m'][selected], dtype=_i16_np.float64)
    bed = _i16_np.asarray(data['node_bed_m'][selected], dtype=_i16_np.float64)
    raw = _i16_np.asarray(data['node_raw_bed_m'][selected], dtype=_i16_np.float64)
    q = _i16_np.asarray(data['node_q_m3_s'][selected], dtype=_i16_np.float64)
    n = len(selected)
    distance = _i16_np.linalg.norm(_i16_np.diff(xz, axis=0), axis=1)
    length = _i16_np.r_[distance, distance[-1]]
    slope = _i16_np.r_[(bed[:-1] - bed[1:]) / distance, (bed[-2] - bed[-1]) / distance[-1]]
    receiver = _i16_np.r_[_i16_np.arange(1, n, dtype=_i16_np.int64), _i16_np.int64(-1)]
    lith = _i16_sample_lithology_points(xz[:, 0], xz[:, 1], world_seed=20261020)
    bh, bank = (lith['bed_hardness'], lith['bank_hardness'])
    baseline = formative_section(q, bh, bank, 0.0, 0.25, max_width_m=300.0)
    roughness = 0.035
    old_depth = _i16_np.array([_normal_depth(qi, wi, si, roughness) for qi, wi, si in zip(q, baseline.width_m, slope)])
    time = _i16_np.asarray(_i16_np.load(root / event_time_directory / 'time_seconds.npy'), dtype=_i16_np.float64)[1:3]
    event_flow = _i16_np.load(event_dir / 'node_water_m3.npy', mmap_mode='r')
    event_q = _i16_np.asarray(event_flow[1, data['node_id'][selected]], dtype=_i16_np.float64) / (time[1] - time[0])
    if not _i16_np.allclose(q, event_q, rtol=1e-12, atol=0.0):
        raise ValueError('saved network Q differs from native event interval')
    scenario = dict(initial_alluvium_bulk_depth_m=0.015, rock_reserve_depth_m=0.5, external_inlet_solid_m3_s=1e-05, initial_mobile_solid_m3=0.0, bank_cohesion=0.25, manning_n=roughness)
    alluvium = baseline.width_m * length * scenario['initial_alluvium_bulk_depth_m']
    rock_floor = bed - scenario['initial_alluvium_bulk_depth_m'] - scenario['rock_reserve_depth_m']
    external = _i16_np.zeros((1, n), dtype=_i16_np.float64)
    external[0, 0] = scenario['external_inlet_solid_m3_s']
    forcing_id = _i16_identity({'time_seconds': time, 'q_m3_s': q}, {'source': manifest['source_identity'], 'kind': 'saved-network-interval-2-formative-scenario'})
    geom_id = _i16_identity({'xz_m': xz, 'bed_m': bed, 'width_m': baseline.width_m}, {'source': manifest['source_identity']})
    material = _i16_MaterialParameters(sediment_erodibility_m_s_pa=1e-08, rock_erodibility_m_s_pa=1e-10, settling_velocity_m_s=0.0001, provenance='declared homogeneous finite sediment scenario')
    routed = _i16_route_daily_sediment(receiver=receiver, length_m=length, width_m=baseline.width_m, bed_elevation_m=bed, water_depth_m=old_depth[None, :], water_q_m3_s=q[None, :], friction_slope=slope[None, :], time_seconds=time, rock_floor_m=rock_floor, initial_alluvium_bulk_m3=alluvium, hardness=bh, material=material, external_solid_m3_s=external, initial_mobile_solid_m3=_i16_np.zeros(n), geometry_identity_sha256=geom_id, hydraulic_identity_sha256=forcing_id, material_provenance=material.provenance)
    s = routed['arrays']
    section = section_from_routed_budget(q, bh, bank, 0.0, 0.25, incoming_solid_m3=s['incoming_solid_m3'][0], external_solid_m3=s['external_solid_m3'][0], capacity_solid_m3=s['capacity_solid_m3'][0], eroded_loose_solid_m3=s['eroded_loose_solid_m3'][0], eroded_rock_m3=s['eroded_rock_m3'][0], deposited_solid_m3=s['deposited_solid_m3'][0], initial_mobile_solid_m3=s['initial_mobile_solid_m3'], max_width_m=300.0)
    final_bed = s['trace_bed_m'][-1].copy()
    final_slope = _i16_np.r_[(final_bed[:-1] - final_bed[1:]) / distance, (final_bed[-2] - final_bed[-1]) / distance[-1]]
    if _i16_np.any(final_slope <= 0.0) or _i16_np.any(final_bed > raw):
        raise ValueError('sediment replay requires a new bounded bed reconciliation')
    depth = _i16_np.array([_normal_depth(qi, wi, si, roughness) for qi, wi, si in zip(q, section.width_m, final_slope)])
    final_id = _i16_identity({'xz_m': xz, 'bed_m': final_bed, 'width_m': section.width_m}, {'source': manifest['source_identity'], 'sediment': routed['identity_sha256']})
    kinds = _i16_np.full(n, 'interior', dtype='U24')
    kinds[-1] = 'open_outflow'
    channel = ChannelNetwork(receiver=receiver, length_m=length, width_m=_i16_np.asarray(section.width_m), bed_elevation_m=final_bed, bed_slope=final_slope, roughness=_i16_np.full(n, roughness), max_depth_m=_i16_np.maximum(depth * 2.0, 1.0), terminal_kind=kinds, source_identity_sha256=final_id, section_source='lagged routed formative width', roughness_source='declared Manning scenario', receiver_distance_m=_i16_np.r_[distance, 0.0])
    water_lateral = _i16_np.r_[q[0], _i16_np.diff(q)]
    arrays = dict(node_id=_i16_np.asarray(data['node_id'][selected]), network_index=selected, xz_m=xz, receiver=receiver, length_m=length, raw_td_m=raw, baseline_bed_m=bed, bed_m=final_bed, formative_q_m3_s=q, water_inflow_m3_s=water_lateral, bed_slope=final_slope, bed_resistance=bh, bank_resistance=bank, baseline_width_m=baseline.width_m, width_m=channel.width_m, baseline_depth_m=old_depth, water_depth_m=depth, storage_m3=channel.width_m * channel.length_m * depth, max_depth_m=channel.max_depth_m, time_seconds=time, **{'sediment_' + k: v for k, v in s.items()})
    sources = {name: file_sha256(network_dir / (name + '.npy')) for name in names}
    sources.update(network_manifest=file_sha256(network_dir / 'manifest.json'), event_manifest=file_sha256(event_dir / 'manifest.json'), event_water=file_sha256(event_dir / 'node_water_m3.npy'), terrain_manifest=file_sha256(root / terrain_directory / 'manifest.json'), event_time=file_sha256(root / event_time_directory / 'time_seconds.npy'))
    metadata = dict(schema='native-formative-width-reach-v1', terrain_identity=manifest['source_identity'], world_seed=20261020, source_file_sha256=sources, source_network=str(network_dir), source_event=str(event_dir), baseline_geometry_sha256=geom_id, formative_flow_sha256=forcing_id, sediment_sha256=routed['identity_sha256'], final_geometry_sha256=final_id, scenario=scenario, sediment_metadata=routed['metadata'], water_policy='saved interval-2 Q held as formative flow; incoming plus nonnegative incremental tributary flow equals node Q; outside headwater unknown, assigned scenario boundary', history='historical climate and bankfull recurrence unknown', sediment_policy='finite replay on baseline geometry; committed final bed and interval exchange update next geometry once', storage_policy='rectangular Manning storage; width equals incision top width; trapezoid incision is not the same cross-sectional area', depth_policy='normal depth from fixed Q, width, slope and scenario Manning n; not observed seasonal water level')
    return {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i16_identity(arrays, metadata)}

def build_native_width_network(root, output, *, sediment_reach=None, network_directory='native-network-v4', event_directory='native-event-v3', routing_directory='native-final-routing-v1', width_algorithm_path=None):
    """Build a new product from v4; source products and default world stay immutable.

    Known committed reach budgets, if supplied, are applied once. Other river
    nodes use the material/flow baseline with an explicit false known mask.
    """
    from terrain_pipeline.new_world_native_network import section as _i14_section
    from terrain_pipeline.new_world_native_network_v4 import reconcile as _i14_reconcile
    from terrain_pipeline.geology import sample_lithology_points as _i14_sample_lithology_points
    from terrain_pipeline.geology import rock_table_identity as _i14_rock_table_identity
    root, output = (_i14_Path(root), _i14_Path(output))
    if output.exists():
        raise FileExistsError(output)
    source = root / network_directory
    manifest = _i14_json.loads((source / 'manifest.json').read_text(encoding='utf8'))
    if manifest['schema'] != 'native-network-v4':
        raise ValueError('native-network-v4 required')
    load = lambda name: _i14_np.load(source / (name + '.npy'), mmap_mode='r', allow_pickle=False)
    ids, xz, q, kind = (load(n) for n in ('node_id', 'node_xz_m', 'node_q_m3_s', 'node_kind'))
    raw, pools, edges = (load(n) for n in ('node_raw_bed_m', 'node_pool_index', 'edge_nodes'))
    lith = _i14_sample_lithology_points(xz[:, 0], xz[:, 1], world_seed=20261020)
    bed, bank = (lith['bed_hardness'], lith['bank_hardness'])
    eligible = (kind == 0) & (q > 0.0)
    previous_width, design_depth = _i14_section(q)
    width = previous_width.copy()
    width[eligible] = formative_section(q[eligible], bed[eligible], bank[eligible], 0.0, 0.25).width_m
    known = _i14_np.zeros(len(ids), dtype=bool)
    budget_names = ('incoming_solid_m3', 'external_solid_m3', 'capacity_solid_m3', 'eroded_loose_solid_m3', 'eroded_rock_m3', 'deposited_solid_m3')
    budgets = {name: _i14_np.full(len(ids), _i14_np.nan) for name in budget_names}
    initial_mobile = _i14_np.full(len(ids), _i14_np.nan)
    final_loose = _i14_np.full(len(ids), _i14_np.nan)
    final_mobile = _i14_np.full(len(ids), _i14_np.nan)
    rock_floor = _i14_np.full(len(ids), _i14_np.nan)
    committed_bed = _i14_np.full(len(ids), _i14_np.nan)
    sediment_identity = None
    if sediment_reach is not None:
        sediment_reach = _i14_Path(sediment_reach)
        info = _i14_json.loads(sediment_reach.with_suffix('.json').read_text(encoding='utf8'))
        if info['terrain_identity'] != manifest['source_identity'] or info['npz_sha256'] != file_sha256(sediment_reach):
            raise ValueError('sediment reach source or archive identity mismatch')
        with _i14_np.load(sediment_reach, allow_pickle=False) as reach:
            indices = _i14_np.searchsorted(ids, reach['node_id'])
            if _i14_np.any(indices >= len(ids)) or not _i14_np.array_equal(ids[indices], reach['node_id']):
                raise ValueError('sediment reach is not a subset of network')
            if not _i14_np.all(eligible[indices]) or not _i14_np.allclose(q[indices], reach['formative_q_m3_s'], rtol=1e-12, atol=0.0):
                raise ValueError('sediment reach Q or node eligibility mismatch')
            if not _i14_np.allclose(bed[indices], reach['bed_resistance']) or not _i14_np.allclose(bank[indices], reach['bank_resistance']):
                raise ValueError('sediment reach material mismatch')
            for name in budget_names:
                budgets[name][indices] = reach['sediment_' + name][0]
            initial_mobile[indices] = reach['sediment_initial_mobile_solid_m3']
            final_loose[indices] = reach['sediment_trace_loose_solid_m3'][-1]
            final_mobile[indices] = reach['sediment_trace_mobile_solid_m3'][-1]
            rock_floor[indices] = reach['sediment_rock_floor_m']
            committed_bed[indices] = reach['bed_m']
            updated = section_from_routed_budget(q[indices], bed[indices], bank[indices], 0.0, 0.25, **{name: budgets[name][indices] for name in budget_names}, initial_mobile_solid_m3=initial_mobile[indices])
            if not _i14_np.allclose(updated.width_m, reach['width_m'], rtol=1e-12, atol=1e-12):
                raise ValueError('routed section disagrees with saved reach')
            width[indices] = updated.width_m
            known[indices] = True
            sediment_identity = info['sediment_sha256']
    levels = _i14_np.load(root / event_directory / 'pool_level_m.npy', mmap_mode='r')[2]
    rank = _i14_np.load(root / routing_directory / 'routing/rank.npy', mmap_mode='r')[ids]
    target = _i14_np.full(len(ids), -1, dtype=_i14_np.int64)
    target[edges[:, 0]] = edges[:, 1]
    inlet_edges, offsets, inlet_stages = (load(n) for n in ('inlet_edge_index', 'inlet_offsets', 'inlet_stage_m'))
    starts = edges[inlet_edges, 1]
    first_stages = inlet_stages[offsets[:-1]]
    stage, node_bed, _, bad = _i14_reconcile(raw, q, kind, pools, levels, target, rank, starts, first_stages, section_override=(width, design_depth))
    for name, actual in (('node_stage_m', stage), ('node_bed_m', node_bed), ('node_status', bad)):
        if not _i14_np.allclose(load(name), actual, equal_nan=True, rtol=0.0, atol=1e-10):
            raise ValueError('cached reconciliation changed: ' + name)
    node_bed[known] = committed_bed[known]
    node_depth = stage - node_bed
    if _i14_np.any(node_depth[known] < 0.0) or _i14_np.any(raw[known] - node_bed[known] > 4.0):
        raise ValueError('committed sediment bed violates stage or cut bound')
    midpoint_raw = load('edge_midpoint_raw_m')
    midpoint_stage = (stage[edges[:, 0]] + stage[edges[:, 1]]) * 0.5
    midpoint_depth = (node_depth[edges[:, 0]] + node_depth[edges[:, 1]]) * 0.5
    midpoint_bed = _i14_np.minimum(midpoint_raw, midpoint_stage - midpoint_depth)
    status = _i14_np.array(load('edge_status'))
    affected = known[edges[:, 0]] | known[edges[:, 1]]
    failed = affected & (status == 0) & ((midpoint_raw - midpoint_bed > 4.0) | (stage[edges[:, 0]] + 1e-08 < stage[edges[:, 1]]) | bad[edges[:, 0]] | bad[edges[:, 1]])
    status[failed] = 1
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = _i14_Path(_i14_tempfile.mkdtemp(prefix=output.name + '-pending-', dir=output.parent))
    try:
        frozen_bounds = {'corridor_capacity_bound_m3.npy', 'sill_extra_storage_bound_m3.npy', 'sill_depth_m.npy'}
        for path in source.iterdir():
            if not path.is_file() or path.name in ('manifest.json', 'node_velocity_m_s.npy'):
                continue
            name = 'source_event_' + path.name if path.name in frozen_bounds else path.name
            _i14_shutil.copyfile(path, temporary / name)
        _i14_np.save(temporary / 'node_width_m.npy', width)
        _i14_np.save(temporary / 'node_bed_m.npy', node_bed)
        _i14_np.save(temporary / 'node_depth_m.npy', node_depth)
        _i14_np.save(temporary / 'edge_midpoint_bed_m.npy', midpoint_bed)
        _i14_np.save(temporary / 'edge_status.npy', status)
        for name, value in dict(node_bed_resistance=bed, node_bank_resistance=bank, node_fracture_additional=_i14_np.zeros(len(ids)), node_bank_cohesion=_i14_np.full(len(ids), 0.25), node_width_eligible=eligible, node_sediment_known=known, node_sediment_initial_mobile_solid_m3=initial_mobile, node_sediment_final_loose_solid_m3=final_loose, node_sediment_final_mobile_solid_m3=final_mobile, node_sediment_rock_floor_m=rock_floor, **{'node_sediment_' + k: v for k, v in budgets.items()}).items():
            _i14_np.save(temporary / (name + '.npy'), value)
        width_code = _i14_Path(width_algorithm_path) if width_algorithm_path is not None else _i14_Path(__file__)
        metadata = dict(manifest)
        if 'sill_extra_storage_bound_sum_m3' in metadata:
            metadata['source_event_sill_extra_storage_bound_sum_m3'] = metadata.pop('sill_extra_storage_bound_sum_m3')
        metadata.update(schema='native-network-width-v1', parent_product=str(source), parent_manifest_sha256=file_sha256(source / 'manifest.json'), width_algorithm='formative-section-routed-budget-v2', width_algorithm_sha256=file_sha256(width_code), lithology_table_sha256=_i14_rock_table_identity(), world_seed=20261020, width_parameters=dict(reference_discharge_m3_s=1.0, reference_width_m=4.0, min_width_m=0.0, max_width_m=120.0, width_exponent=0.45, bank_cohesion=0.25, additional_fracture=0.0), formative_flow='native-event-v3 interval 2 mean, fixed formative scenario; historical recurrence unknown', sediment_policy='committed reach budget once where known; unknown elsewhere, baseline width', sediment_identity_sha256=sediment_identity, sediment_reach_sha256=file_sha256(sediment_reach) if sediment_reach is not None else None, sediment_known_nodes=int(known.sum()), eligible_river_nodes=int(eligible.sum()), other_node_policy='retain v4 lake/ocean and zero-flow widths', stage_bed_policy='v4 stage/lake reconciliation; committed sediment bed on known nodes, with updated depth and midpoint; widths may be subgrid', velocity_policy='unavailable: no velocity array is copied or inferred; current widths and cached stages are not a solved hydraulic state', source_event_storage_bounds='source_event_* bounds and sill depth use the old section and reproduce the frozen source event; they are not recomputed for the new section', hydraulics_scope='cached v4 event and stage; current-width network has not been dynamically solved', edge_status_counts={str(i): int(_i14_np.count_nonzero(status == i)) for i in range(12)}, committed_bed_new_edge_failures=int(failed.sum()), source_q_sha256=file_sha256(source / 'node_q_m3_s.npy'), result_width_sha256=file_sha256(temporary / 'node_width_m.npy'))
        (temporary / 'manifest.json').write_text(_i14_json.dumps(metadata, indent=2, ensure_ascii=False), encoding='utf8')
        _i14_os.rename(temporary, output)
    except BaseException:
        _i14_shutil.rmtree(temporary)
        raise
    return metadata

def continue_width_reach(a, geometry_identity_sha256, *, duration_s=60.0):
    """Carry committed stocks and saved water volume into rectangular new section."""
    from terrain_pipeline.common_infra import identity as _i15_identity
    from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters as _i15_MaterialParameters
    from terrain_pipeline.surface_rivers.metric_sediment import SedimentDomain as _i15_SedimentDomain
    from terrain_pipeline.surface_rivers.metric_sediment import SedimentForcing as _i15_SedimentForcing
    from terrain_pipeline.surface_rivers.metric_sediment import SedimentConfig as _i15_SedimentConfig
    from terrain_pipeline.surface_rivers.metric_sediment import solve_sediment as _i15_solve_sediment
    from terrain_pipeline.surface_hydraulics import solve_channel as _x2_solve_channel
    n = len(a['receiver'])
    kinds = _i15_np.full(n, 'interior', dtype='U24')
    kinds[-1] = 'open_outflow'
    network = ChannelNetwork(receiver=a['receiver'], length_m=a['length_m'], width_m=a['width_m'], bed_elevation_m=a['bed_m'], bed_slope=a['bed_slope'], roughness=_i15_np.full(n, 0.035), max_depth_m=a['max_depth_m'], terminal_kind=kinds, source_identity_sha256=geometry_identity_sha256, section_source='rectangular formative section, committed prior sediment', roughness_source='scenario Manning n=.035', receiver_distance_m=_i15_np.r_[a['length_m'][:-1], 0.0])
    t0 = float(a['time_seconds'][-1])
    forcing = ChannelForcing(_i15_np.array([t0, t0 + duration_s]), a['water_inflow_m3_s'][None, :], geometry_identity_sha256)
    water = _x2_solve_channel(network, forcing, a['storage_m3'], ChannelConfig(max_dt_seconds=1.0))
    if water['metadata']['status'] != 'complete':
        raise ValueError('water continuation failed: ' + str(water['metadata']['failure_reason']))
    h = water['arrays']
    hydraulic_id = _i15_identity(h, water['metadata'])
    material = _i15_MaterialParameters(sediment_erodibility_m_s_pa=1e-08, rock_erodibility_m_s_pa=1e-10, settling_velocity_m_s=0.0001, provenance='declared homogeneous finite sediment scenario')
    loose = a['sediment_trace_loose_solid_m3'][-1]
    mobile = a['sediment_trace_mobile_solid_m3'][-1]
    domain = _i15_SedimentDomain(network.receiver, network.length_m * network.width_m, network.width_m, network.bed_elevation_m, a['sediment_rock_floor_m'], loose / (1 - material.porosity), _i15_np.zeros(n, dtype=bool), _i15_np.arange(n) == n - 1, geometry_identity_sha256, 'prior committed mobile and alluvium stocks, finite rock floor')
    external = _i15_np.zeros_like(h['outflow_q_m3_s'])
    external[:, 0] = 1e-05
    sediment_forcing = _i15_SedimentForcing(h['time_seconds'], h['volume_m3'][:-1], h['depth_m'][:-1], h['outflow_q_m3_s'], _i15_np.broadcast_to(network.bed_slope, external.shape).copy(), external, hydraulic_id, geometry_identity_sha256, 'actual new-section water continuation')
    sediment = _i15_solve_sediment(domain, sediment_forcing, material, mobile, _i15_SedimentConfig(max_dt_seconds=1.0))
    if sediment['metadata']['status'] != 'complete':
        raise ValueError('sediment continuation failed: ' + str(sediment['metadata']['failure_reason']))
    return (water, sediment)

def turn_allowed(incoming, outgoing, max_turn_deg=90.0):
    """Zero is straight ahead; the maximum angle is excluded."""
    incoming, outgoing = (_i17_np.asarray(incoming, float), _i17_np.asarray(outgoing, float))
    scale = _i17_np.linalg.norm(incoming) * _i17_np.linalg.norm(outgoing)
    return bool(scale > 0 and incoming @ outgoing > scale * (_i17_np.cos(_i17_np.radians(max_turn_deg)) + 1e-12))

def turn_penalty(incoming, outgoing, k=1.0):
    """0 through 45 degrees, k*(theta-45)/(90-theta) thereafter; >=90 forbidden."""
    if not _i17_np.isfinite(k) or k < 0:
        raise ValueError('invalid river turn penalty strength')
    incoming, outgoing = (_i17_np.asarray(incoming, float), _i17_np.asarray(outgoing, float))
    scale = _i17_np.linalg.norm(incoming) * _i17_np.linalg.norm(outgoing)
    if scale <= 0 or not _i17_np.isfinite(scale):
        raise ValueError('invalid river heading vector')
    angle = float(_i17_np.degrees(_i17_np.arccos(_i17_np.clip(incoming @ outgoing / scale, -1.0, 1.0))))
    if angle >= 90.0 - 1e-10:
        return float('inf')
    return 0.0 if angle <= 45.0 else k * (angle - 45.0) / (90.0 - angle)

def heading_path(sources, ends, cost, points, start, targets, *, max_turn_deg, start_directions=(), end_directions=(), turn_penalty_k=1.0):
    """Dijkstra over directed edges, retaining distinct arrivals at each node.

    Endpoint directions represent every existing incoming/outgoing physical
    edge. They constrain the first/last edge without inventing extra vertices.
    """
    if not _i17_np.isfinite(max_turn_deg) or not 0 <= max_turn_deg <= 180:
        raise ValueError('invalid maximum river turn')
    directions = []
    for values in (start_directions, end_directions):
        value = _i17_np.asarray(values, float)
        if value.size == 0:
            value = _i17_np.empty((0, points.shape[1]))
        if value.ndim != 2 or value.shape[1] != points.shape[1] or (not _i17_np.isfinite(value).all()) or _i17_np.any(_i17_np.linalg.norm(value, axis=1) == 0):
            raise ValueError('invalid endpoint river directions')
        directions.append(value)
    initial, final = directions
    turn_penalty((1.0, 0.0), (1.0, 0.0), turn_penalty_k)

    def penalty(incoming, outgoing):
        if not turn_allowed(incoming, outgoing, max_turn_deg):
            return float('inf')
        return turn_penalty(incoming, outgoing, turn_penalty_k)
    vectors = points[ends] - points[sources]
    outgoing = {}
    for edge, node in enumerate(sources):
        outgoing.setdefault(int(node), []).append(edge)
    targets = set(map(int, targets))
    distances = _i17_np.full(len(ends), _i17_np.inf)
    previous = _i17_np.full(len(ends), -1, _i17_np.int64)
    queue = []
    for edge in outgoing.get(int(start), ()):
        extra = max((penalty(direction, vectors[edge]) for direction in initial), default=0.0)
        if _i17_np.isfinite(extra):
            distances[edge] = cost[edge] * (1 + extra)
            _i17_heapq.heappush(queue, (float(distances[edge]), edge))
    best_distance, best_edge = (float('inf'), None)
    while queue:
        distance, edge = _i17_heapq.heappop(queue)
        if distance != distances[edge]:
            continue
        if distance >= best_distance:
            break
        node = int(ends[edge])
        if node in targets:
            extra = max((penalty(vectors[edge], direction) for direction in final), default=0.0)
            finish_distance = distance + cost[edge] * extra
            if finish_distance < best_distance:
                best_distance, best_edge = (finish_distance, edge)
            continue
        for next_edge in outgoing.get(node, ()):
            extra = penalty(vectors[edge], vectors[next_edge])
            if not _i17_np.isfinite(extra):
                continue
            ancestor = edge
            repeated = False
            while ancestor != -1:
                if sources[ancestor] == ends[next_edge]:
                    repeated = True
                    break
                ancestor = int(previous[ancestor])
            if repeated:
                continue
            candidate = distance + cost[next_edge] * (1 + extra)
            if candidate < distances[next_edge]:
                distances[next_edge] = candidate
                previous[next_edge] = edge
                _i17_heapq.heappush(queue, (float(candidate), next_edge))
    if best_edge is None:
        return None
    path = [int(ends[best_edge])]
    while best_edge != -1:
        path.append(int(sources[best_edge]))
        best_edge = int(previous[best_edge])
    return _i17_np.asarray(path[::-1], _i17_np.int64)

@_i18_dataclass(frozen=True)
class ChannelResult:
    height: _i18_np.ndarray
    water_surface: _i18_np.ndarray
    channel_mask: _i18_np.ndarray
    flowline_mask: _i18_np.ndarray
    width_blocks: _i18_np.ndarray
    incision: _i18_np.ndarray
    unresolved_mask: _i18_np.ndarray

def _validated_route(receiver, order, shape):
    count = int(_i18_np.prod(shape))
    original_receiver = _i18_np.asarray(receiver)
    original_order = _i18_np.asarray(order)
    if original_receiver.dtype.kind not in 'iu' or original_order.dtype.kind not in 'iu':
        raise ValueError('Route indices must be integers')
    downstream = original_receiver.reshape(-1).astype(_i18_np.int64)
    ordered = original_order.reshape(-1).astype(_i18_np.int64)
    if downstream.size != count or ordered.size != count:
        raise ValueError('Invalid route dimensions')
    if _i18_np.any((downstream < -1) | (downstream >= count)):
        raise ValueError('Invalid receiver index')
    if not _i18_np.array_equal(_i18_np.sort(ordered), _i18_np.arange(count)):
        raise ValueError('Order must be a permutation')
    position = _i18_np.empty(count, dtype=_i18_np.int64)
    position[ordered] = _i18_np.arange(count)
    for cell, target in enumerate(downstream):
        if target >= 0 and position[target] >= position[cell]:
            raise ValueError('Receiver must precede donor')
    return (downstream, ordered)

def _channel_geometry(flowline, discharge, receiver, spacing, threshold):
    from terrain_pipeline.surface_rivers.bridge import flow_tangent as _i18_flow_tangent
    rows, cols = flowline.shape
    corridor = flowline.copy()
    donors = [[] for _ in range(rows * cols)]
    for cell, target in enumerate(receiver):
        if target >= 0 and flowline.flat[cell]:
            donors[target].append(cell)
    width = _i18_np.zeros(flowline.shape, dtype=_i18_np.float32)
    width[flowline] = _i18_np.minimum(5 * spacing, spacing * _i18_np.maximum(1, _i18_np.sqrt(discharge[flowline] / threshold)))
    for z, x in zip(*_i18_np.nonzero(flowline)):
        target = receiver[z * cols + x]
        if target < 0:
            incoming = donors[z * cols + x]
            if not incoming:
                continue
            donor = max(incoming, key=lambda cell: discharge.flat[cell])
            uz, ux = divmod(donor, cols)
            dz, dx = (z - uz, x - ux)
        else:
            tz, tx = divmod(int(target), cols)
            dz, dx = (tz - z, tx - x)
        edge_dz, edge_dx = (dz, dx)
        dz, dx = _i18_flow_tangent(z * cols + x, receiver, donors, cols, discharge)
        length = _i18_np.hypot(dz, dx)
        if length == 0.0:
            continue
        grid_length = max(abs(dz), abs(dx))
        normal_z, normal_x = (dx / grid_length, -dz / grid_length)
        radius = min(2, int(_i18_np.floor(width[z, x] / (2 * spacing))))
        samples = max(1, int(_i18_np.ceil(_i18_np.hypot(edge_dz, edge_dx) * 2.0))) if target >= 0 else 1
        for sample in range(samples + 1):
            along = sample / samples if target >= 0 else 0.0
            for step in range(-radius, radius + 1):
                nz = int(round(z + along * edge_dz + step * normal_z))
                nx = int(round(x + along * edge_dx + step * normal_x))
                if 0 <= nz < rows and 0 <= nx < cols:
                    corridor[nz, nx] = True
    return (corridor, width)

def _carve_beds(source, corridor, flowline, receiver, order, discharge, threshold, max_incision, diagnostics=None):
    carved = source.copy()
    lower_limit = source.reshape(-1) - max_incision
    q_depth = _i18_np.minimum(max_incision, 0.8 + 0.55 * _i18_np.log1p(discharge / threshold))
    carved[corridor] -= _i18_np.minimum(max_incision, _i18_np.maximum(0.4, q_depth[corridor] * 0.7))
    carved[flowline] = source[flowline] - q_depth[flowline]
    bed = carved.reshape(-1)
    active = flowline.reshape(-1)
    unresolved = _i18_np.zeros(source.size, dtype=bool)
    for cell in order[::-1]:
        target = receiver[cell]
        if not active[cell] or target < 0 or (not active[target]):
            continue
        required = bed[cell] - 0.01
        if bed[target] > required:
            bed[target] = max(lower_limit[target], required)
            if bed[target] > required + 1e-09:
                unresolved[cell] = unresolved.reshape(-1)[target] = True
                if diagnostics is not None:
                    diagnostics.mark_cell('bed_cut_cap', int(target))
                    diagnostics.mark_cell('bed_cut_cap_donor', int(cell), propagated=True)
                    diagnostics.required_extra_cut_m.flat[target] = max(diagnostics.required_extra_cut_m.flat[target], bed[target] - required)
    incision = source - carved
    if (incision < -1e-08).any() or (incision > max_incision + 1e-08).any():
        raise AssertionError('Channel incision must only cut within its cap')
    return (carved, incision, unresolved)

def carve_channels(height, receiver, order, discharge, spacing_blocks, threshold, max_incision=4.0, diagnostics=None) -> ChannelResult:
    """Carve a Q-scaled cross-section; unresolved flowline cells remain dry."""
    from terrain_pipeline.surface_rivers.water import safe_water as _i18_safe_water
    from terrain_pipeline.surface_rivers.bridge import bridge_diagonals as _i18_bridge_diagonals
    source = _i18_np.asarray(height, dtype=_i18_np.float64)
    q = _i18_np.asarray(discharge, dtype=_i18_np.float64)
    if source.ndim != 2 or q.shape != source.shape or (not _i18_np.isfinite(source).all()):
        raise ValueError('Expected finite height and matching discharge grids')
    if not _i18_np.isfinite(q).all() or (q < 0).any():
        raise ValueError('Discharge must be finite and nonnegative')
    if not _i18_np.isfinite(spacing_blocks) or spacing_blocks <= 0:
        raise ValueError('Positive grid spacing required')
    if not _i18_np.isfinite(threshold) or threshold <= 0 or (not _i18_np.isfinite(max_incision)) or (max_incision <= 0):
        raise ValueError('Positive threshold and incision cap required')
    downstream, ordered = _validated_route(receiver, order, source.shape)
    flowline = q >= threshold
    corridor, width = _channel_geometry(flowline, q, downstream, spacing_blocks, threshold)
    carved, incision, unresolved = _carve_beds(source, corridor, flowline, downstream, ordered, q, threshold, max_incision, diagnostics)
    water, unresolved = _i18_safe_water(source, carved, corridor, flowline, downstream, unresolved, max_incision, diagnostics)
    carved, water, corridor, bad_edges = _i18_bridge_diagonals(source, carved, water, corridor, flowline, downstream, max_incision, diagnostics)
    for donor, target in bad_edges:
        unresolved.reshape(-1)[donor] = True
        unresolved.reshape(-1)[target] = True
        if diagnostics is not None:
            diagnostics.mark_cell('diagonal_bridge_failed', donor, propagated=True)
            diagnostics.mark_cell('diagonal_bridge_failed', target, propagated=True)
    flat_water = water.reshape(-1)
    flat_unresolved = unresolved.reshape(-1)
    todo = _i18_deque(map(tuple, _i18_np.argwhere(_i18_np.isfinite(water))))
    while todo:
        z, x = todo.popleft()
        for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nz, nx = (z + dz, x + dx)
            if 0 <= nz < source.shape[0] and 0 <= nx < source.shape[1] and corridor[nz, nx] and (not unresolved[nz, nx]) and (not _i18_np.isfinite(water[nz, nx])) and (source[nz, nx] - max_incision < water[z, x] - 0.15):
                carved[nz, nx] = min(carved[nz, nx], water[z, x] - 0.15)
                water[nz, nx] = water[z, x]
                todo.append((nz, nx))
    for z, x in zip(*_i18_np.nonzero(_i18_np.isfinite(water))):
        for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nz, nx = (z + dz, x + dx)
            if 0 <= nz < source.shape[0] and 0 <= nx < source.shape[1] and (not _i18_np.isfinite(water[nz, nx])):
                water[z, x] = min(water[z, x], carved[nz, nx] - 0.05)
        carved[z, x] = max(source[z, x] - max_incision, min(carved[z, x], water[z, x] - 0.15))
        if water[z, x] <= carved[z, x] + 1e-06:
            unresolved[z, x] = True
    for cell in ordered[::-1]:
        target = downstream[cell]
        if target >= 0 and _i18_np.isfinite(flat_water[cell]) and _i18_np.isfinite(flat_water[target]):
            if flat_water[target] > flat_water[cell] + 1e-06:
                lowered = min(flat_water[target], flat_water[cell])
                carved.reshape(-1)[target] = max(source.reshape(-1)[target] - max_incision, min(carved.reshape(-1)[target], lowered - 0.15))
                if lowered <= carved.reshape(-1)[target] + 1e-06:
                    flat_unresolved[cell] = flat_unresolved[target] = True
                    if diagnostics is not None:
                        diagnostics.mark_cell('stage_repair_no_clearance', cell)
                        diagnostics.mark_cell('stage_repair_no_clearance', target)
                else:
                    flat_water[target] = lowered
    flat_water[flat_unresolved] = _i18_np.nan
    incision = source - carved
    if (incision < -1e-08).any() or (incision > max_incision + 1e-08).any():
        raise AssertionError('Channel incision must remain cut-only and capped')
    return ChannelResult(carved, water, corridor, flowline, width, incision, unresolved)

def _positive(value, name, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i20_math.isfinite(value)) or (value <= 0.0):
        raise ValueError(name + ' must be finite positive')
    if maximum is not None and value > maximum:
        raise ValueError(name + ' exceeds bound')
    return float(value)

def _nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i20_math.isfinite(value)) or (value < 0.0):
        raise ValueError(name + ' must be finite nonnegative')
    return float(value)

def _sha(value, name):
    if not isinstance(value, str) or len(value) != 64 or any((char not in '0123456789abcdef' for char in value)):
        raise ValueError(name + ' must be a lowercase SHA256')

def _mask(value, shape, name):
    if not isinstance(value, _i20_np.ndarray) or value.dtype != bool or value.shape != shape:
        raise ValueError(name + ' must be a matching boolean array')

def _event_id(kind, graph, geometry, parameters):
    body = {'kind': kind, 'graph': graph, 'geometry': geometry, 'parameters': parameters}
    digest = _i20_hashlib.sha256(_i20_json.dumps(body, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    return kind + '-' + digest

@_i20_dataclass(frozen=True)
class BankPointbarConfig:
    max_erosion_depth_m: float = 0.25
    max_deposit_depth_m: float = 0.25
    porosity: float = 0.35
    influence_radius_m: float = 0.0

    def __post_init__(self):
        _positive(self.max_erosion_depth_m, 'max_erosion_depth_m', 1000.0)
        _positive(self.max_deposit_depth_m, 'max_deposit_depth_m', 1000.0)
        if isinstance(self.porosity, bool) or not isinstance(self.porosity, (int, float)) or (not _i20_math.isfinite(self.porosity)) or (not 0.0 <= self.porosity < 1.0):
            raise ValueError('porosity must be in [0, 1)')
        radius = self.influence_radius_m
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or (not _i20_math.isfinite(radius)) or (radius < 0.0):
            raise ValueError('influence_radius_m must be finite nonnegative')
        object.__setattr__(self, 'max_erosion_depth_m', float(self.max_erosion_depth_m))
        object.__setattr__(self, 'max_deposit_depth_m', float(self.max_deposit_depth_m))
        object.__setattr__(self, 'porosity', float(self.porosity))
        object.__setattr__(self, 'influence_radius_m', float(radius))

@_i20_dataclass(frozen=True)
class BraidedConfig:
    max_candidates: int = 3
    branch_offset_cells: int = 1
    max_deposit_depth_m: float = 0.2
    porosity: float = 0.35
    branch_fraction: float = 0.25

    def __post_init__(self):
        if type(self.max_candidates) is not int or self.max_candidates not in (2, 3):
            raise ValueError('max_candidates must be two or three')
        if type(self.branch_offset_cells) is not int or self.branch_offset_cells < 1 or self.branch_offset_cells > 8:
            raise ValueError('branch_offset_cells must be between one and eight')
        _positive(self.max_deposit_depth_m, 'max_deposit_depth_m', 1000.0)
        if isinstance(self.porosity, bool) or not isinstance(self.porosity, (int, float)) or (not _i20_math.isfinite(self.porosity)) or (not 0.0 <= self.porosity < 1.0):
            raise ValueError('porosity must be in [0, 1)')
        if isinstance(self.branch_fraction, bool) or not isinstance(self.branch_fraction, (int, float)) or (not _i20_math.isfinite(self.branch_fraction)) or (not 0.0 < self.branch_fraction < 0.5):
            raise ValueError('branch_fraction must be in (0, 0.5)')
        object.__setattr__(self, 'max_deposit_depth_m', float(self.max_deposit_depth_m))
        object.__setattr__(self, 'porosity', float(self.porosity))
        object.__setattr__(self, 'branch_fraction', float(self.branch_fraction))

def _terrain_cell(terrain, point):
    x, z = (float(point[0]), float(point[1]))
    column = int(round((x - terrain.x0_m) / terrain.dx_m))
    row = int(round((z - terrain.z0_m) / terrain.dz_m))
    if not (0 <= row < terrain.elevation_m.shape[0] and 0 <= column < terrain.elevation_m.shape[1]):
        raise ValueError('path point leaves terrain')
    if not terrain.valid_mask[row, column]:
        raise ValueError('path crosses unknown terrain')
    return (row, column)

def _validate_centerline(terrain, points):
    if not isinstance(points, _i20_np.ndarray) or points.dtype != _i20_np.float64 or points.ndim != 2 or (points.shape[1] != 2) or (len(points) < 3):
        raise ValueError('centerline must be float64 [N,2] with at least three points')
    if not _i20_np.isfinite(points).all() or _i20_np.any(_i20_np.linalg.norm(_i20_np.diff(points, axis=0), axis=1) <= 0.0):
        raise ValueError('centerline must contain finite distinct points')
    for point in points:
        _terrain_cell(terrain, point)

def _side_cell(terrain, point, tangent, side):
    normal = _i20_np.array((tangent[1], -tangent[0]), dtype=_i20_np.float64)
    normal /= max(float(_i20_np.linalg.norm(normal)), 1e-12)
    distance = max(terrain.dx_m, terrain.dz_m)
    return _terrain_cell(terrain, point + side * distance * normal)

def build_bank_pointbar_candidate(terrain, centerline_xz_m, parent_graph_identity_sha256, parent_geometry_identity_sha256, sediment_solid_m3, config=None):
    from terrain_pipeline.common_infra import TerrainGrid as _i20_TerrainGrid
    from terrain_pipeline.surface_rivers.metric_morphology_events import MorphologyEvent as _i20_MorphologyEvent
    if not isinstance(terrain, _i20_TerrainGrid):
        raise ValueError('TerrainGrid required')
    config = BankPointbarConfig() if config is None else config
    if not isinstance(config, BankPointbarConfig):
        raise ValueError('BankPointbarConfig required')
    points = centerline_xz_m
    _validate_centerline(terrain, points)
    _sha(parent_graph_identity_sha256, 'parent graph identity')
    _sha(parent_geometry_identity_sha256, 'parent geometry identity')
    sediment = _nonnegative(sediment_solid_m3, 'sediment_solid_m3')
    shape = terrain.elevation_m.shape
    erosion_mask = _i20_np.zeros(shape, dtype=bool)
    deposit_mask = _i20_np.zeros(shape, dtype=bool)
    erosion = _i20_np.zeros(shape, dtype=_i20_np.float64)
    deposit = _i20_np.zeros(shape, dtype=_i20_np.float64)
    curvature_records = []
    for index in range(1, len(points) - 1):
        incoming = points[index] - points[index - 1]
        outgoing = points[index + 1] - points[index]
        cross = float(incoming[0] * outgoing[1] - incoming[1] * outgoing[0])
        scale = max(float(_i20_np.linalg.norm(incoming) * _i20_np.linalg.norm(outgoing)), 1e-12)
        curvature = cross / scale
        if abs(curvature) <= 1e-12:
            continue
        tangent = incoming / max(float(_i20_np.linalg.norm(incoming)), 1e-12) + outgoing / max(float(_i20_np.linalg.norm(outgoing)), 1e-12)
        tangent /= max(float(_i20_np.linalg.norm(tangent)), 1e-12)
        outer = 1 if curvature > 0.0 else -1
        try:
            outer_cell = _side_cell(terrain, points[index], tangent, outer)
            inner_cell = _side_cell(terrain, points[index], tangent, -outer)
        except ValueError:
            continue
        outer_row, outer_column = outer_cell
        inner_row, inner_column = inner_cell
        if terrain.valid_mask[outer_cell]:
            erosion_mask[outer_cell] = True
            erosion[outer_cell] = max(erosion[outer_cell], config.max_erosion_depth_m)
        if terrain.valid_mask[inner_cell] and (not erosion_mask[inner_cell]):
            deposit_mask[inner_cell] = True
            deposit[inner_cell] = max(deposit[inner_cell], config.max_deposit_depth_m)
        curvature_records.append((index, round(curvature, 12), outer_cell, inner_cell))
    erosion_volume = float(erosion.sum() * terrain.cell_area_m2)
    available = sediment + erosion_volume
    requested_fill = float((deposit * terrain.cell_area_m2).sum())
    deposited = min(available, requested_fill * (1.0 - config.porosity))
    if requested_fill > 0.0 and deposited < requested_fill * (1.0 - config.porosity):
        deposit *= deposited / (requested_fill * (1.0 - config.porosity))
    height_delta = deposit - erosion
    actual_deposit_volume = float((deposit * terrain.cell_area_m2 * (1.0 - config.porosity)).sum())
    unresolved = max(0.0, available - actual_deposit_volume)
    ledger = {'input_solid_m3': sediment, 'eroded_solid_m3': erosion_volume, 'deposited_solid_m3': actual_deposit_volume, 'exported_solid_m3': 0.0, 'unresolved_solid_m3': unresolved}
    config_record = {'max_erosion_depth_m': config.max_erosion_depth_m, 'max_deposit_depth_m': config.max_deposit_depth_m, 'porosity': config.porosity, 'influence_radius_m': config.influence_radius_m}
    parameters = {'algorithm': 'bank-pointbar-v1', 'config': config_record, 'curvature_records': [list(record) for record in curvature_records]}
    event = _i20_MorphologyEvent(_event_id('bank-migration', parent_graph_identity_sha256, parent_geometry_identity_sha256, parameters), 'bank_migration', parent_graph_identity_sha256, parent_geometry_identity_sha256, (), (), (), 0.0, sediment, {'deposited_solid_m3': actual_deposit_volume, 'exported_solid_m3': 0.0, 'unresolved_solid_m3': unresolved, 'cut_rock_m3': erosion_volume, 'fill_m3': float((deposit * terrain.cell_area_m2).sum()), 'porous_deposit_m3': float((deposit * terrain.cell_area_m2).sum())}, parameters)
    return {'schema': 'terragenesis-bank-pointbar-candidate-v1', 'status': 'candidate', 'height_delta_m': height_delta, 'erosion_mask': erosion_mask, 'deposit_mask': deposit_mask, 'solid_ledger': ledger, 'material_ledger': ledger, 'event': event, 'candidate': True, 'hydraulic': False, 'publishable': False}

def _validate_cells(terrain, path):
    if isinstance(path, _i20_np.ndarray):
        if path.dtype != _i20_np.float64 or path.ndim != 2 or path.shape[1] != 2:
            raise ValueError('main_path points must be float64 [N,2]')
        values = tuple((path[index] for index in range(len(path))))
    elif isinstance(path, (tuple, list)):
        values = tuple(path)
    else:
        values = ()
    if len(values) < 2:
        raise ValueError('main_path requires at least two cells or points')
    cells = []
    for value in values:
        if isinstance(value, tuple) and len(value) == 2 and all((type(item) is int for item in value)):
            row, column = value
            if not (0 <= row < terrain.elevation_m.shape[0] and 0 <= column < terrain.elevation_m.shape[1]):
                raise ValueError('main_path cell outside terrain')
            cell = (row, column)
        else:
            array = _i20_np.asarray(value)
            if array.dtype != _i20_np.float64 or array.shape != (2,) or (not _i20_np.isfinite(array).all()):
                raise ValueError('main_path points must be float64 [2]')
            cell = _terrain_cell(terrain, array)
        if not terrain.valid_mask[cell]:
            raise ValueError('main_path crosses unknown terrain')
        cells.append(cell)
    if any((max(abs(a[0] - b[0]), abs(a[1] - b[1])) != 1 for a, b in zip(cells, cells[1:]))):
        raise ValueError('main_path must use 8-neighbor steps')
    return tuple(cells)

def build_braided_candidate(terrain, main_path, water_mask, parent_graph_identity_sha256, parent_geometry_identity_sha256, discharge_m3_s, sediment_solid_m3, config=None):
    from terrain_pipeline.common_infra import TerrainGrid as _i20_TerrainGrid
    from terrain_pipeline.surface_rivers.metric_morphology_events import MorphologyEvent as _i20_MorphologyEvent
    if not isinstance(terrain, _i20_TerrainGrid):
        raise ValueError('TerrainGrid required')
    config = BraidedConfig() if config is None else config
    if not isinstance(config, BraidedConfig):
        raise ValueError('BraidedConfig required')
    _mask(water_mask, terrain.elevation_m.shape, 'water_mask')
    if _i20_np.any(water_mask & ~terrain.valid_mask):
        raise ValueError('water_mask includes unknown terrain')
    path = _validate_cells(terrain, main_path)
    if any((not water_mask[cell] for cell in path)):
        raise ValueError('main_path must remain in legal wet water')
    _sha(parent_graph_identity_sha256, 'parent graph identity')
    _sha(parent_geometry_identity_sha256, 'parent geometry identity')
    discharge = _nonnegative(discharge_m3_s, 'discharge_m3_s')
    sediment = _nonnegative(sediment_solid_m3, 'sediment_solid_m3')
    direction = _i20_np.array((path[-1][0] - path[0][0], path[-1][1] - path[0][1]), dtype=_i20_np.float64)
    if _i20_np.linalg.norm(direction) == 0.0:
        raise ValueError('main_path direction is undefined')
    direction /= _i20_np.linalg.norm(direction)
    lateral = _i20_np.array((-direction[1], direction[0]))
    candidates = []
    for branch_index in range(config.max_candidates):
        offset = 0 if branch_index == 0 else -1 if branch_index == 1 else 1
        candidate = []
        for path_index, (row, column) in enumerate(path):
            if path_index in (0, len(path) - 1) or offset == 0:
                candidate.append((row, column))
                continue
            point = _i20_np.array((terrain.x0_m + column * terrain.dx_m, terrain.z0_m + row * terrain.dz_m))
            shifted = point + offset * config.branch_offset_cells * _i20_np.array((lateral[1] * terrain.dx_m, lateral[0] * terrain.dz_m))
            try:
                shifted_cell = _terrain_cell(terrain, shifted)
            except ValueError:
                shifted_cell = (row, column)
            candidate.append(shifted_cell if water_mask[shifted_cell] else (row, column))
        candidate = tuple(candidate)
        if any((not water_mask[cell] for cell in candidate)) or any((max(abs(a[0] - b[0]), abs(a[1] - b[1])) != 1 for a, b in zip(candidate, candidate[1:]))):
            continue
        if candidate not in [item['path_cells'] for item in candidates]:
            candidates.append({'path_cells': candidate, 'offset': offset})
    if len(candidates) < 2:
        raise ValueError('fewer than two legal braided candidates')
    fractions = [1.0 - (len(candidates) - 1) * config.branch_fraction] + [config.branch_fraction] * (len(candidates) - 1)
    bar_mask = _i20_np.zeros(terrain.elevation_m.shape, dtype=bool)
    for first, second in zip(candidates, candidates[1:]):
        bar_mask[first['path_cells'][-1]] = True
        bar_mask[second['path_cells'][-1]] = True
    capacity = terrain.cell_area_m2 * config.max_deposit_depth_m * (1.0 - config.porosity)
    deposited = min(sediment, capacity * float(_i20_np.count_nonzero(bar_mask)))
    unresolved = sediment - deposited
    height_delta = _i20_np.zeros(terrain.elevation_m.shape, dtype=_i20_np.float64)
    if _i20_np.count_nonzero(bar_mask):
        height_delta[bar_mask] = deposited / _i20_np.count_nonzero(bar_mask) / terrain.cell_area_m2 / (1.0 - config.porosity)
    fractions_record = [round(value, 12) for value in fractions]
    parameters = {'algorithm': 'braided-v1', 'candidate_count': len(candidates), 'flow_fractions': fractions_record, 'discharge_m3_s': discharge}
    event = _i20_MorphologyEvent(_event_id('bifurcation', parent_graph_identity_sha256, parent_geometry_identity_sha256, parameters), 'bifurcation', parent_graph_identity_sha256, parent_geometry_identity_sha256, (), tuple(('braid-' + str(index) for index in range(1, len(candidates)))), (), discharge, sediment, {'deposited_solid_m3': deposited, 'exported_solid_m3': 0.0, 'unresolved_solid_m3': unresolved, 'cut_rock_m3': 0.0, 'fill_m3': deposited / (1.0 - config.porosity), 'porous_deposit_m3': deposited / (1.0 - config.porosity)}, parameters)
    return {'schema': 'terragenesis-braided-candidate-v1', 'status': 'candidate', 'candidate_paths': tuple((item['path_cells'] for item in candidates)), 'braid_candidates': tuple(candidates), 'flow_split': tuple(fractions), 'bar_mask': bar_mask, 'deposit_mask': bar_mask.copy(), 'height_delta_m': height_delta, 'solid_ledger': {'input_solid_m3': sediment, 'deposited_solid_m3': deposited, 'exported_solid_m3': 0.0, 'unresolved_solid_m3': unresolved}, 'event': event, 'candidate': True, 'hydraulic': False, 'routing_graph_written': False, 'publishable': False}
TERMINAL_STATUS_CODES = {'inactive': 0, 'interior': 1, 'unresolved_closed_domain': 2, 'unresolved_domain_boundary': 3, 'unknown_boundary': 4, 'frozen_outlet_candidate': 5, 'unresolved_deep_depression': 6, 'unresolved_fill_budget': 7, 'unresolved_unknown_owner': 8}

def _terrain_mesh(terrain):
    from terrain_pipeline.drainage import grid_mesh as _i21_grid_mesh
    from terrain_pipeline.drainage import masked_mesh as _i21_masked_mesh
    return _i21_masked_mesh(_i21_grid_mesh(terrain.valid_mask.shape, x0_m=terrain.x0_m, z0_m=terrain.z0_m, dx_m=terrain.dx_m, dz_m=terrain.dz_m, world_seed=terrain.generation_seed if terrain.generation_seed is not None else 20261020), terrain.valid_mask)

class _GraphAnalysis:

    def __init__(self, receiver, order):
        self.receiver, self.order = (receiver, order)

    def accuflux(self, local, nodata=None):
        flow = _i21_np.asarray(local, _i21_np.float64).ravel().copy()
        for cell in self.order[::-1]:
            target = self.receiver[cell]
            if target >= 0:
                flow[target] += flow[cell]
        return flow.reshape(_i21_np.asarray(local).shape)

def _routing(backend, terrain, receiver):
    """Analyze arbitrary graph edges without encoding raster direction codes."""
    valid = terrain.valid_mask.ravel()
    donors = [[] for _ in range(receiver.size)]
    pending = _i21_deque()
    for node in _i21_np.flatnonzero(valid):
        target = int(receiver[node])
        if target < 0:
            pending.append(int(node))
        else:
            donors[target].append(int(node))
    order = []
    while pending:
        node = pending.popleft()
        order.append(node)
        pending.extend(donors[node])
    if len(order) != int(valid.sum()):
        raise ValueError('candidate receiver contains a cycle or missing valid cells')
    order = _i21_np.asarray(order, _i21_np.int64)
    return (_GraphAnalysis(receiver, order), order)

def _check_receiver(receiver, valid, owner, mesh):
    from terrain_pipeline.drainage import receiver_edges_valid as _i21_receiver_edges_valid
    size = valid.size
    if not isinstance(receiver, _i21_np.ndarray) or receiver.dtype != _i21_np.int64 or receiver.shape != (size,) or _i21_np.any(receiver < -1) or _i21_np.any(receiver >= size) or _i21_np.any(receiver[~valid.ravel()] != -1):
        raise ValueError('baseline_receiver must be int64 [N] inside valid terrain')
    sources = _i21_np.flatnonzero(receiver >= 0)
    targets = receiver[sources]
    if _i21_np.any(~valid.ravel()[targets]) or not _i21_receiver_edges_valid(receiver, mesh):
        raise ValueError('baseline receiver must join valid irregular graph neighbors')
    return sources[owner[sources] != owner[targets]]

def _restore_steepest_descent(terrain, owner_grid, receiver, work, eligible, mesh=None):
    mesh = _terrain_mesh(terrain) if mesh is None else mesh
    original = receiver.copy()
    owner = owner_grid.ravel()
    for node in _i21_np.flatnonzero(eligible.ravel() & (receiver >= 0)):
        best = 0.0
        for edge in range(mesh.indptr[node], mesh.indptr[node + 1]):
            target = mesh.indices[edge]
            if owner[target] != owner[node]:
                continue
            slope = (work[node] - work[target]) / mesh.edge_length_m[edge]
            if slope > best:
                receiver[node], best = (target, slope)
    return int(_i21_np.count_nonzero(receiver != original))

def bounded_confluence_candidate(terrain, boundary, frozen_owner_domain_id, *, baseline_receiver=None, frozen_outlet_mask=None, max_fill_depth_m=4.0, local_q_m3_s=None):
    """Return graph, work surface, metadata and an explicit unresolved-state ledger.

    Only existing cross-owner contacts, original unknown-boundary terminals and
    explicitly supplied frozen outlets seed the library. Other owner boundaries
    are walls. Components without a seed retain their restricted baseline DAG.
    Negative owner labels remain distinct routing regions without outlet claims.
    """
    from terrain_pipeline.common_infra import identity as _i21_identity
    from terrain_pipeline.common_infra import RoutingGraph as _i21_RoutingGraph
    from terrain_pipeline.drainage import segments_clear as _i21_segments_clear
    from terrain_pipeline.drainage import route_graph as _i21_route_graph
    if isinstance(max_fill_depth_m, (bool, _i21_np.bool_)) or not isinstance(max_fill_depth_m, (int, float, _i21_np.integer, _i21_np.floating)) or (not _i21_np.isfinite(max_fill_depth_m)) or (max_fill_depth_m <= 0):
        raise ValueError('positive finite max_fill_depth_m required')
    height, valid = (terrain.elevation_m, terrain.valid_mask)
    if height.shape != boundary.kind.shape or terrain.dx_m != terrain.dz_m:
        raise ValueError('matching boundary and square metric cells required')
    owner_grid = _i21_np.asarray(frozen_owner_domain_id)
    if owner_grid.shape != height.shape or owner_grid.dtype.kind not in 'iu':
        raise ValueError('frozen_owner_domain_id must be a matching integer grid')
    owner = owner_grid.ravel()
    if frozen_outlet_mask is None:
        frozen_outlet_mask = _i21_np.zeros(height.shape, bool)
    if not isinstance(frozen_outlet_mask, _i21_np.ndarray) or frozen_outlet_mask.dtype != bool or frozen_outlet_mask.shape != height.shape or _i21_np.any(frozen_outlet_mask & ~valid):
        raise ValueError('frozen_outlet_mask must select valid cells')
    if local_q_m3_s is not None:
        local_q_m3_s = _i21_np.asarray(local_q_m3_s, _i21_np.float64)
        if local_q_m3_s.size != height.size or local_q_m3_s.shape not in (height.shape, (height.size,)) or (not _i21_np.isfinite(local_q_m3_s).all()) or _i21_np.any(local_q_m3_s < 0) or _i21_np.any(local_q_m3_s.ravel()[~valid.ravel()] != 0):
            raise ValueError('finite nonnegative local discharge on valid cells required')
    if baseline_receiver is None:
        from terrain_pipeline.drainage import route_diagnostic
        baseline_receiver = route_diagnostic(terrain, boundary, flat_distance_strategy='metric_distance').receiver
    mesh = _terrain_mesh(terrain)
    crossings = _check_receiver(baseline_receiver, valid, owner, mesh)
    backend = None
    _routing(backend, terrain, baseline_receiver)
    receiver = baseline_receiver.copy()
    receiver[crossings] = -1
    status = _i21_np.full(height.size, TERMINAL_STATUS_CODES['interior'], dtype=_i21_np.uint8)
    status[~valid.ravel()] = TERMINAL_STATUS_CODES['inactive']
    status[valid.ravel() & (receiver < 0)] = TERMINAL_STATUS_CODES['unresolved_closed_domain']
    status[crossings] = TERMINAL_STATUS_CODES['unresolved_domain_boundary']
    unknown_boundary = (boundary.kind.ravel() == 'unknown_boundary') & valid.ravel() & (baseline_receiver < 0)
    status[unknown_boundary] = TERMINAL_STATUS_CODES['unknown_boundary']
    status[frozen_outlet_mask.ravel()] = TERMINAL_STATUS_CODES['frozen_outlet_candidate']
    seeds = _i21_np.zeros(height.size, bool)
    seeds[crossings] = True
    seeds |= unknown_boundary | frozen_outlet_mask.ravel()
    receiver[seeds] = -1
    descent_eligible = _i21_np.zeros(height.shape, bool)
    component_records = []
    source_nodes = _i21_np.repeat(_i21_np.arange(height.size), _i21_np.diff(mesh.indptr))
    keep = (owner[source_nodes] == owner[mesh.indices]) & valid.ravel()[source_nodes] & valid.ravel()[mesh.indices]
    for label in _i21_np.unique(owner[valid.ravel()]):
        positions = _i21_np.flatnonzero(keep & (owner[source_nodes] == label))
        keep[positions] &= _i21_segments_clear(source_nodes[positions], mesh.indices[positions], valid & (owner_grid == label))
    counts = _i21_np.bincount(source_nodes[keep], minlength=height.size)
    domain_mesh = _i21_replace(mesh, indptr=_i21_np.r_[0, _i21_np.cumsum(counts)], indices=mesh.indices[keep], edge_length_m=mesh.edge_length_m[keep])
    adjacency = _i21_csr_matrix((_i21_np.ones(domain_mesh.indices.size), domain_mesh.indices, domain_mesh.indptr), shape=(height.size, height.size))
    _, components = _i21_connected_components(adjacency, directed=False)
    for component_id in _i21_np.unique(components[valid.ravel()]):
        global_ids = _i21_np.flatnonzero((components == component_id) & valid.ravel())
        component_seeds = seeds[global_ids]
        record = dict(owner_domain_id=int(owner[global_ids[0]]), cell_count=int(global_ids.size), seed_count=int(component_seeds.sum()))
        if not component_seeds.any():
            record['policy'] = 'restricted_baseline_no_fill_no_invented_outlet'
            component_records.append(record)
            continue
        descent_eligible.ravel()[global_ids] = True
        lookup = _i21_np.full(height.size, -1, _i21_np.int64)
        lookup[global_ids] = _i21_np.arange(global_ids.size)
        edge_ids = _i21_np.concatenate([_i21_np.arange(domain_mesh.indptr[node], domain_mesh.indptr[node + 1]) for node in global_ids])
        degree = _i21_np.diff(domain_mesh.indptr)[global_ids]
        local_mesh = _i21_replace(domain_mesh, shape=(1, global_ids.size), node_x_m=mesh.node_x_m[global_ids], node_z_m=mesh.node_z_m[global_ids], indptr=_i21_np.r_[0, _i21_np.cumsum(degree)], indices=lookup[domain_mesh.indices[edge_ids]], edge_length_m=domain_mesh.edge_length_m[edge_ids])
        local_height = height.ravel()[global_ids].reshape(1, -1)
        local_outlets = component_seeds.reshape(1, -1).copy()
        while True:
            routed = _i21_route_graph(local_height, local_outlets, local_mesh)
            deep = routed.filled - local_height >= max_fill_depth_m
            added = deep & ~local_outlets
            if not added.any():
                break
            local_outlets |= added
        local_receiver = routed.receiver
        terminal = local_receiver < 0
        receiver[global_ids] = _i21_np.where(terminal, -1, global_ids[_i21_np.maximum(local_receiver, 0)])
        status[global_ids] = TERMINAL_STATUS_CODES['interior']
        status[global_ids[terminal]] = TERMINAL_STATUS_CODES['unresolved_deep_depression']
        record['policy'] = 'shared_irregular_graph_explicit_contact_seeds'
        component_records.append(record)
    receiver[seeds] = -1
    status[crossings] = TERMINAL_STATUS_CODES['unresolved_domain_boundary']
    status[unknown_boundary] = TERMINAL_STATUS_CODES['unknown_boundary']
    status[frozen_outlet_mask.ravel()] = TERMINAL_STATUS_CODES['frozen_outlet_candidate']
    sources = _i21_np.flatnonzero(receiver >= 0)
    targets = receiver[sources]
    columns = height.shape[1]
    blocked = _i21_np.zeros(sources.size, bool)
    _, order = _routing(backend, terrain, receiver)
    work = height.ravel().copy()
    budget_cut_count = 0
    for cell in order:
        target = receiver[cell]
        if target < 0:
            continue
        required = max(work[cell], work[target])
        if required - height.ravel()[cell] > max_fill_depth_m:
            receiver[cell] = -1
            status[cell] = TERMINAL_STATUS_CODES['unresolved_fill_budget']
            budget_cut_count += 1
        else:
            work[cell] = required
    descent_changed_count = _restore_steepest_descent(terrain, owner_grid, receiver, work, descent_eligible, domain_mesh)
    routing, order = _routing(backend, terrain, receiver)
    terminal = valid.ravel() & (receiver < 0)
    kinds = _i21_np.full(height.size, 'interior', dtype='U16')
    kinds[~valid.ravel()] = 'inactive'
    kinds[terminal] = 'lake_preserved'
    unresolved_port = _i21_np.isin(status, [TERMINAL_STATUS_CODES['unresolved_domain_boundary'], TERMINAL_STATUS_CODES['frozen_outlet_candidate']])
    kinds[terminal & ((owner < 0) | unknown_boundary | unresolved_port)] = 'unknown_boundary'
    terminal_owner = _i21_np.full(height.size, -1, _i21_np.int64)
    for cell in order:
        terminal_owner[cell] = cell if receiver[cell] < 0 else terminal_owner[receiver[cell]]
    lake_id = _i21_np.full(height.size, -1, _i21_np.int64)
    terminal_is_internal = kinds[terminal_owner[valid.ravel()]] == 'lake_preserved'
    active_cells = _i21_np.flatnonzero(valid)
    lake_id[active_cells[terminal_is_internal]] = terminal_owner[active_cells[terminal_is_internal]]
    sources = _i21_np.flatnonzero(receiver >= 0)
    targets = receiver[sources]
    length, slope = (_i21_np.zeros(height.size), _i21_np.zeros(height.size))
    length[sources] = _i21_np.hypot(mesh.node_z_m[targets] - mesh.node_z_m[sources], mesh.node_x_m[targets] - mesh.node_x_m[sources])
    slope[sources] = (work[sources] - work[targets]) / length[sources]
    graph = _i21_RoutingGraph(receiver, order, valid, length, slope, kinds, lake_id, terrain.identity_sha256, boundary.identity_sha256, policy='frozen_owner_bounded_confluence_candidate_v3_irregular')
    area = _i21_np.asarray(routing.accuflux(valid.astype(_i21_np.float64) * terrain.cell_area_m2, nodata=-9999.0), _i21_np.float64).ravel()
    area[~valid.ravel()] = 0
    raises = (work - height.ravel()).reshape(height.shape)
    audit_arrays = dict(terminal_status=status, terminal_owner=terminal_owner, terminal_owner_known=terminal & (owner >= 0), contributing_area_m2=area, working_raise_m=raises, baseline_cross_owner_source_ids=crossings, frozen_seed_mask=seeds.reshape(height.shape))
    if local_q_m3_s is not None:
        discharge = _i21_np.asarray(routing.accuflux(local_q_m3_s.reshape(height.shape), nodata=-9999.0), _i21_np.float64).ravel()
        discharge[~valid.ravel()] = 0
        audit_arrays['routed_q_m3_s'] = discharge
    metadata = dict(schema='bounded-confluence-candidate-v2', algorithm='frozen_owner_bounded_confluence_candidate_v3_irregular', backend='irregular_graph', version='1', max_fill_depth_m=float(max_fill_depth_m), maximum_fill_m=float(raises.max()), filled_volume_m3=float(raises.sum() * terrain.cell_area_m2), raised_cell_count=int(_i21_np.count_nonzero(raises)), budget_rejected_edge_count=budget_cut_count, baseline_receiver_identity_sha256=_i21_identity({'receiver': baseline_receiver}, {}), frozen_owner_identity_sha256=_i21_identity({'frozen_owner_domain_id': owner_grid}, {}), original_boundary_identity_sha256=boundary.identity_sha256, baseline_cross_owner_contact_count=int(crossings.size), blocked_diagonal_contact_count=int(blocked.sum()), component_records=component_records, steepest_descent_changed_edge_count=descent_changed_count, descent_policy='seeded components only: strictly lower same-owner graph neighbor with maximum drop/distance; ties by cell ID; equal-height spill receiver retained; terminals frozen', terminal_status_counts={name: int(_i21_np.count_nonzero(status[terminal] == code)) for name, code in TERMINAL_STATUS_CODES.items() if _i21_np.any(status[terminal] == code)}, terminal_status_codes=TERMINAL_STATUS_CODES, unknown_owner_terminal_count=int(_i21_np.count_nonzero(terminal & (owner < 0))), seed_policy='original cross-owner upstream contacts and original unknown-boundary terminals; optional explicit frozen outlet candidates', owner_boundary_policy='closed except explicit seeds; all owner labels isolated including negative labels', no_seed_policy='restricted original receiver retained; no fill or invented outlet', unknown_owner_policy='negative owner IDs remain separate; all their terminals uncertified, never inferred sea', fill_policy='float64 minimum monotone receiver surface; over-budget edges terminate unresolved', graph_lake_preserved_semantics='compatibility placeholder for unresolved terminal; no accepted lake or wet footprint', budget_semantics='routing-only shallow fill cap; independent of any bed-cut budget', work_surface_only=True, natural_outlet_verified=False, hydraulic_ready=False, publishable=False)
    validate_bounded_confluence(terrain, owner_grid, graph, work.reshape(height.shape), audit_arrays, max_fill_depth_m=max_fill_depth_m)
    return (graph, work.reshape(height.shape), metadata, audit_arrays)

def validate_bounded_confluence(terrain, frozen_owner_domain_id, graph, work, audit_arrays, *, max_fill_depth_m=4.0):
    """Check owner isolation, actual fill, terminal ledger and full area closure."""
    owner = _i21_np.asarray(frozen_owner_domain_id).ravel()
    sources = _i21_np.flatnonzero(graph.receiver >= 0)
    targets = graph.receiver[sources]
    if _i21_np.any(owner[sources] != owner[targets]):
        raise ValueError('candidate receiver crosses frozen owner domains')
    raises = work - terrain.elevation_m
    if not _i21_np.isfinite(work).all() or _i21_np.any(raises < 0) or _i21_np.any(raises > max_fill_depth_m):
        raise ValueError('actual routing fill outside declared budget')
    if _i21_np.any(work.ravel()[sources] < work.ravel()[targets]):
        raise ValueError('working receiver edge is uphill')
    if not _i21_np.array_equal(raises, audit_arrays['working_raise_m']):
        raise ValueError('routing fill ledger differs from actual work surface')
    area = audit_arrays['contributing_area_m2']
    expected = terrain.valid_mask.ravel() * terrain.cell_area_m2 + _i21_np.bincount(targets, weights=area[sources], minlength=graph.receiver.size)
    if not _i21_np.allclose(area, expected, rtol=1e-10, atol=1e-08):
        raise ValueError('contributing area does not close at every node')
    terminal = terrain.valid_mask.ravel() & (graph.receiver < 0)
    if _i21_np.any(audit_arrays['terminal_status'][terminal] == TERMINAL_STATUS_CODES['interior']):
        raise ValueError('candidate terminal lacks an explicit classification')
    if not _i21_np.isclose(area[terminal].sum(), terrain.valid_mask.sum() * terrain.cell_area_m2):
        raise ValueError('terminal area does not cover valid source terrain')
METRIC_VALLEY_CENTERLINE_SCHEMA = 'terragenesis-metric-valley-centerline-v1'
METRIC_VALLEY_CENTERLINE_ALGORITHM = 'anchored-bounded-original-valley-laplacian-v1'

@_i40_dataclass(frozen=True)
class CenterlineRecipe:
    strength: float = 0.25
    max_node_offset_m: float = 2.0
    max_source_rise_m: float = 0.5
    iterations: int = 2

    def __post_init__(self):
        if not 0.0 < self.strength <= 0.5 or self.max_node_offset_m < 0.0 or self.max_source_rise_m < 0.0 or (self.iterations < 1) or (self.iterations > 16) or any((not _i40_math.isfinite(v) for v in (self.strength, self.max_node_offset_m, self.max_source_rise_m))):
            raise ValueError('invalid bounded centerline recipe')

def _anchors(receiver):
    degree = _i40_np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    return (degree != 1) | (receiver < 0)

def _turn_energy(points, receiver):
    incoming = _i40_np.full(len(receiver), -1, _i40_np.int64)
    for i, j in enumerate(receiver):
        if j >= 0 and incoming[j] < 0:
            incoming[j] = i
    total = 0.0
    for i, j in enumerate(receiver):
        if j < 0 or incoming[i] < 0:
            continue
        first = points[i] - points[incoming[i]]
        second = points[j] - points[i]
        cosine = float(first @ second / (_i40_np.linalg.norm(first) * _i40_np.linalg.norm(second)))
        total += (1.0 - _i40_np.clip(cosine, -1.0, 1.0)) ** 2
    return total

def _validate_shape(points, original, anchors, receiver, width, depth, terrain, owner, corridor, lake, config, recipe):
    if points.dtype != _i40_np.float64 or points.shape != original.shape or (not _i40_np.isfinite(points).all()) or (not _i40_np.array_equal(points[anchors], original[anchors])):
        raise ValueError('source, junction or terminal anchor moved')
    offset = _i40_np.linalg.norm(points - original, axis=1)
    if _i40_np.any(offset > recipe.max_node_offset_m + 1e-09):
        raise ValueError('centerline exceeds original node offset')
    source, cells = _metric_channel_geometry_sample(terrain.elevation_m, points, terrain)
    original_source = _metric_channel_geometry_sample(terrain.elevation_m, original, terrain)[0]
    if _i40_np.any(source - original_source > recipe.max_source_rise_m + 1e-09) or _i40_np.any(~terrain.valid_mask.ravel()[cells]) or _i40_np.any(~corridor.ravel()[cells]) or _i40_np.any(lake.ravel()[cells]):
        raise ValueError('centerline leaves known original valley corridor')
    source_owner = owner.ravel()[_metric_channel_geometry_sample(terrain.elevation_m, original, terrain)[1]]
    if _i40_np.any(owner.ravel()[cells] != source_owner):
        raise ValueError('centerline crosses original source owner')
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, depth, terrain, config.max_cut_m)
    _footprint(points, receiver, width, _i40_np.full(len(points), config.max_cut_m), terrain, owner, corridor, lake, source_owner, config.fine_spacing_m)
    _profile_overlap(points, receiver, width, profile, terrain)
    return profile

def build_valley_centerline(terrain, node_cell_ids, receiver, width_m, base_depth_m, *, owner_grid, corridor_mask, lake_mask, source_plan_identity_sha256, config=None, recipe=None):
    from terrain_pipeline.common_infra import identity as _i40_identity
    from terrain_pipeline.common_infra import readonly as _i40_readonly
    config = config or GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0)
    recipe = recipe or CenterlineRecipe()
    _check_inputs(terrain, node_cell_ids, receiver, width_m, base_depth_m, owner_grid, corridor_mask, lake_mask, config)
    if not isinstance(recipe, CenterlineRecipe) or not isinstance(source_plan_identity_sha256, str) or len(source_plan_identity_sha256) != 64 or any((ch not in '0123456789abcdef' for ch in source_plan_identity_sha256)):
        raise ValueError('centerline source plan identity and recipe required')
    cols = terrain.elevation_m.shape[1]
    original = _i40_np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m, terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    anchors = _anchors(receiver)
    _validate_shape(original, original, anchors, receiver, width_m, base_depth_m, terrain, owner_grid, corridor_mask, lake_mask, config, recipe)
    incoming = _i40_np.full(len(receiver), -1, _i40_np.int64)
    for i, j in enumerate(receiver):
        if j >= 0:
            incoming[j] = i
    points = original.copy()
    refusals = []
    for iteration in range(recipe.iterations):
        old_energy = _turn_energy(points, receiver)
        accepted = False
        for power in range(5):
            trial = points.copy()
            strength = recipe.strength / 2 ** power
            for i, j in enumerate(receiver):
                if not anchors[i]:
                    trial[i] += strength * ((points[incoming[i]] + points[j]) / 2.0 - points[i])
            try:
                _validate_shape(trial, original, anchors, receiver, width_m, base_depth_m, terrain, owner_grid, corridor_mask, lake_mask, config, recipe)
                if _turn_energy(trial, receiver) >= old_energy - 1e-12:
                    raise ValueError('turn energy does not decrease')
            except ValueError as error:
                refusals.append({'iteration': iteration, 'step': power, 'reason': str(error)})
                continue
            points = trial
            accepted = True
            break
        if not accepted:
            break
    arrays = dict(source_node_cell_ids=node_cell_ids.copy(), receiver=receiver.copy(), original_node_xz_m=original, node_xz_m=points, anchor_mask=anchors, width_m=width_m.copy(), base_depth_m=base_depth_m.copy(), source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(), owner_grid=owner_grid.copy(), corridor_mask=corridor_mask.copy(), lake_mask=lake_mask.copy())
    metadata = dict(schema=METRIC_VALLEY_CENTERLINE_SCHEMA, algorithm=METRIC_VALLEY_CENTERLINE_ALGORITHM, terrain_metadata=_metadata_terrain(terrain), source_identity_sha256=terrain.identity_sha256, source_plan_identity_sha256=source_plan_identity_sha256, config=_i40_asdict(config), recipe=_i40_asdict(recipe), initial_turn_energy=_turn_energy(original, receiver), final_turn_energy=_turn_energy(points, receiver), moved_nodes=int(_i40_np.count_nonzero(_i40_np.linalg.norm(points - original, axis=1) > 1e-09)), refused_steps=refusals, hydraulic_ready=False, publishable=False)
    arrays = {key: _i40_readonly(value) for key, value in arrays.items()}
    bundle = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i40_identity(arrays, metadata)}
    validate_valley_centerline(bundle)
    return bundle

def validate_valley_centerline(bundle):
    from terrain_pipeline.common_infra import identity as _i40_identity
    from terrain_pipeline.common_infra import TerrainGrid as _i40_TerrainGrid
    if not isinstance(bundle, dict) or set(bundle) != {'arrays', 'metadata', 'identity_sha256'} or bundle['identity_sha256'] != _i40_identity(bundle['arrays'], bundle['metadata']) or (sum((value.nbytes for value in bundle['arrays'].values())) > METRIC_CHANNEL_GEOMETRY_MAX_BYTES):
        raise ValueError('centerline identity or byte budget mismatch')
    a, m = (bundle['arrays'], bundle['metadata'])
    if set(a) != {'source_node_cell_ids', 'receiver', 'original_node_xz_m', 'node_xz_m', 'anchor_mask', 'width_m', 'base_depth_m', 'source_height_m', 'source_valid_mask', 'owner_grid', 'corridor_mask', 'lake_mask'} or set(m) != {'schema', 'algorithm', 'terrain_metadata', 'source_identity_sha256', 'source_plan_identity_sha256', 'config', 'recipe', 'initial_turn_energy', 'final_turn_energy', 'moved_nodes', 'refused_steps', 'hydraulic_ready', 'publishable'} or m['schema'] != METRIC_VALLEY_CENTERLINE_SCHEMA or (m['algorithm'] != METRIC_VALLEY_CENTERLINE_ALGORITHM) or (m['hydraulic_ready'] is not False) or (m['publishable'] is not False):
        raise ValueError('centerline schema or scope mismatch')
    terrain = _i40_TerrainGrid(a['source_height_m'], a['source_valid_mask'], **m['terrain_metadata'])
    if terrain.identity_sha256 != m['source_identity_sha256']:
        raise ValueError('centerline original terrain identity mismatch')
    config = GeometryConfig(**m['config'])
    recipe = CenterlineRecipe(**m['recipe'])
    ids, receiver, width, depth = (a[key] for key in ('source_node_cell_ids', 'receiver', 'width_m', 'base_depth_m'))
    _check_inputs(terrain, ids, receiver, width, depth, a['owner_grid'], a['corridor_mask'], a['lake_mask'], config)
    cols = terrain.elevation_m.shape[1]
    original = _i40_np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m, terrain.z0_m + ids // cols * terrain.dz_m))
    anchors = _anchors(receiver)
    if not _i40_np.array_equal(a['original_node_xz_m'], original) or not _i40_np.array_equal(a['anchor_mask'], anchors):
        raise ValueError('centerline original node or anchor mismatch')
    _validate_shape(a['node_xz_m'], original, anchors, receiver, width, depth, terrain, a['owner_grid'], a['corridor_mask'], a['lake_mask'], config, recipe)
    initial = _turn_energy(original, receiver)
    final = _turn_energy(a['node_xz_m'], receiver)
    moved = int(_i40_np.count_nonzero(_i40_np.linalg.norm(a['node_xz_m'] - original, axis=1) > 1e-09))
    if not _i40_math.isclose(m['initial_turn_energy'], initial, abs_tol=1e-10) or not _i40_math.isclose(m['final_turn_energy'], final, abs_tol=1e-10) or final > initial + 1e-10 or (m['moved_nodes'] != moved):
        raise ValueError('centerline turn or movement ledger mismatch')
    return True

def save_valley_centerline(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _i40_save_bundle
    _i40_save_bundle(path, bundle, validator=validate_valley_centerline)

def load_valley_centerline(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _i40_load_bundle
    bundle = _i40_load_bundle(path, expected_sha256=expected_sha256, validator=validate_valley_centerline, max_bytes=METRIC_CHANNEL_GEOMETRY_MAX_BYTES)
    if bundle['identity_sha256'] != expected_identity:
        raise ValueError('external centerline identity mismatch')
    return bundle

def repair_budget_centerline(points, receiver, profile, *, evaluate, validate, certify, max_cut_m, max_trials=256, max_rounds=24, max_trials_per_round=32, causal_nodes=None, source_height=None, max_causal_nodes=4, max_causal_certificates_per_node=3):
    """Use local proxy bounds, then certify the complete profile and cut bounds.

    evaluate(points, profile, focus_nodes) returns category maxima/counts and
    hotspot node indices. certify(points) returns the complete highest profile.
    No mesh or LP is constructed by this search.
    """
    points = points.copy()
    anchors = _anchors(receiver)
    donors = [[] for _ in points]
    for source, target in enumerate(receiver):
        if target >= 0:
            donors[target].append(source)
    evaluation = evaluate(points, profile, None)
    initial = evaluation
    trials, accepted, complete_certificates = (0, [], 0)

    def score(values):
        return (max(0.0, values['maxima'][0] - max_cut_m), values['counts'][0], max(0.0, max(values['maxima']) - max_cut_m), sum(values['counts']))
    for round_index in range(max_rounds):
        if not sum(evaluation['counts']) or trials >= max_trials:
            break
        ranked = sorted(evaluation['hotspots'], key=lambda h: (h['category'] != 'physical_half_bottom', -h['maximum_required_cut_m']))
        node_order = []
        for hotspot in ranked:
            candidates = [hotspot['node_index']] if 'node_index' in hotspot else [hotspot['source_node_index'], hotspot['target_node_index']]
            for node in candidates:
                if not anchors[node] and node not in node_order:
                    node_order.append(node)
        proposals = []
        round_trial_limit = min(max_trials, trials + max_trials_per_round)
        for node in node_order:
            upstream, downstream = (donors[node][0], int(receiver[node]))
            tangent = points[downstream] - points[upstream]
            normal = _i22_np.array([-tangent[1], tangent[0]]) / _i22_np.linalg.norm(tangent)
            neighbors = [n for n in [upstream, downstream] if not anchors[n]]
            groups = [[node], [node] + neighbors]
            for group in groups:
                focus = set(group)
                for member in group:
                    focus.update(donors[member])
                    if receiver[member] >= 0:
                        focus.add(int(receiver[member]))
                old_local = evaluate(points, profile, focus)
                for offset_m in (-0.5, 0.5, -1.0, 1.0, -2.0, 2.0, -4.0, 4.0, -8.0, 8.0):
                    if trials >= round_trial_limit:
                        break
                    trials += 1
                    candidate = points.copy()
                    candidate[group] += offset_m * normal
                    try:
                        validate(candidate)
                        proxy = evaluate(candidate, profile, focus)
                    except ValueError:
                        continue
                    if score(proxy) >= score(old_local):
                        continue
                    if any((new > old + 1e-08 for new, old in zip(proxy['maxima'], evaluation['maxima']))):
                        continue
                    improvement = tuple((new - old for new, old in zip(score(proxy), score(old_local))))
                    proposals.append((improvement, candidate, group, offset_m))
                if trials >= round_trial_limit:
                    break
            if trials >= round_trial_limit:
                break
        chosen = False
        for _, candidate, group, offset_m in sorted(proposals, key=lambda proposal: proposal[0]):
            try:
                complete_certificates += 1
                certified_profile = certify(candidate)
                complete = evaluate(candidate, certified_profile, None)
            except ValueError:
                continue
            if score(complete) >= score(evaluation) or any((new > old + 1e-08 for new, old in zip(complete['maxima'], evaluation['maxima']))):
                continue
            accepted.append(dict(round=round_index, node_indices=group, offset_m=offset_m, before_maxima=evaluation['maxima'], after_maxima=complete['maxima'], before_counts=evaluation['counts'], after_counts=complete['counts']))
            points, profile, evaluation = (candidate, certified_profile, complete)
            chosen = True
            break
        if not chosen:
            break
    causal_trials = 0
    if sum(evaluation['counts']) and causal_nodes is not None:
        movable_causal_nodes = [node for node in causal_nodes(points, profile, evaluation) if not anchors[node]]
        for node in movable_causal_nodes[:max_causal_nodes]:
            if anchors[node] or not sum(evaluation['counts']):
                continue
            upstream, downstream = (donors[node][0], int(receiver[node]))
            tangent = points[downstream] - points[upstream]
            normal = _i22_np.array([-tangent[1], tangent[0]]) / _i22_np.linalg.norm(tangent)
            neighbors = [n for n in [upstream, downstream] if not anchors[n]]
            proposals = []
            for group in ([node], [node] + neighbors):
                for offset_m in (-0.5, 0.5, -1.0, 1.0, -2.0, 2.0, -4.0, 4.0, -8.0, 8.0):
                    causal_trials += 1
                    candidate = points.copy()
                    candidate[group] += offset_m * normal
                    try:
                        validate(candidate)
                    except ValueError:
                        continue
                    gain = float(source_height(candidate[node]) - source_height(points[node]))
                    if gain > 0.0:
                        proposals.append((-gain, candidate, group, offset_m))
            certified_proposals = []
            for _, candidate, group, offset_m in sorted(proposals, key=lambda proposal: proposal[0])[:max_causal_certificates_per_node]:
                try:
                    complete_certificates += 1
                    certified_profile = certify(candidate)
                    complete = evaluate(candidate, certified_profile, None)
                except ValueError:
                    continue
                if score(complete) >= score(evaluation) or any((new > old + 1e-08 for new, old in zip(complete['maxima'], evaluation['maxima']))):
                    continue
                certified_proposals.append((score(complete), candidate, group, offset_m, certified_profile, complete))
            if certified_proposals:
                _, candidate, group, offset_m, certified_profile, complete = min(certified_proposals, key=lambda proposal: proposal[0])
                accepted.append(dict(stage='controlling_upstream', node_indices=group, offset_m=offset_m, before_maxima=evaluation['maxima'], after_maxima=complete['maxima'], before_counts=evaluation['counts'], after_counts=complete['counts']))
                points, profile, evaluation = (candidate, certified_profile, complete)
    return (points, profile, dict(algorithm='finite-physical-budget-hotspot-best-proxy-and-upstream-search-v3', maximum_trials=max_trials, attempted_trials=trials, maximum_rounds=max_rounds, maximum_trials_per_round=max_trials_per_round, maximum_cut_m=max_cut_m, causal_attempted_trials=causal_trials, maximum_causal_nodes=max_causal_nodes, maximum_causal_certificates_per_node=max_causal_certificates_per_node, complete_profile_and_budget_certificates=complete_certificates, accepted_moves=accepted, initial_maxima=initial['maxima'], final_maxima=evaluation['maxima'], initial_counts=initial['counts'], final_counts=evaluation['counts'], status='necessary_bounds_clear' if not sum(evaluation['counts']) else 'necessary_budget_conflicts_remain', anchors_fixed=True, constraint_parameters_changed=False))

@_i25_dataclass(frozen=True)
class CutoffConfig:
    neck_distance_m: float = 32.0
    min_loop_length_m: float = 64.0
    min_node_gap: int = 2
    max_candidates: int = 256
    max_bed_rise_m: float = 0.0
    seed: int = 0

    def __post_init__(self):
        for name in ('neck_distance_m', 'min_loop_length_m'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i25_math.isfinite(value)) or (value <= 0.0):
                raise ValueError(name + ' must be finite positive')
            object.__setattr__(self, name, float(value))
        if type(self.min_node_gap) is not int or self.min_node_gap < 2:
            raise ValueError('min_node_gap must be an integer of at least two')
        if type(self.max_candidates) is not int or not 1 <= self.max_candidates <= 100000:
            raise ValueError('max_candidates must be bounded positive integer')
        if isinstance(self.max_bed_rise_m, bool) or not isinstance(self.max_bed_rise_m, (int, float)) or (not _i25_math.isfinite(self.max_bed_rise_m)) or (self.max_bed_rise_m < 0.0):
            raise ValueError('max_bed_rise_m must be finite nonnegative')
        object.__setattr__(self, 'max_bed_rise_m', float(self.max_bed_rise_m))
        if type(self.seed) is not int or not 0 <= self.seed <= 4294967295:
            raise ValueError('seed must be uint32')

def _finite_transfer(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, _i25_np.integer, _i25_np.floating)) or (not _i25_math.isfinite(value)) or (value < 0.0):
        raise ValueError(name + ' must be finite nonnegative')
    return float(value)

def _sample_grid(terrain, points):
    height = terrain.elevation_m
    rows, columns = height.shape
    points = _i25_np.asarray(points, dtype=_i25_np.float64)
    rows_position = (points[:, 1] - terrain.z0_m) / terrain.dz_m
    columns_position = (points[:, 0] - terrain.x0_m) / terrain.dx_m
    if not _i25_np.isfinite(points).all() or _i25_np.any(rows_position < -1e-09) or _i25_np.any(columns_position < -1e-09) or _i25_np.any(rows_position > rows - 1 + 1e-09) or _i25_np.any(columns_position > columns - 1 + 1e-09):
        return None
    row0 = _i25_np.floor(_i25_np.clip(rows_position, 0.0, rows - 1.0)).astype(_i25_np.int64)
    column0 = _i25_np.floor(_i25_np.clip(columns_position, 0.0, columns - 1.0)).astype(_i25_np.int64)
    row1 = _i25_np.minimum(row0 + 1, rows - 1)
    column1 = _i25_np.minimum(column0 + 1, columns - 1)
    valid = terrain.valid_mask[row0, column0] & terrain.valid_mask[row1, column0] & terrain.valid_mask[row0, column1] & terrain.valid_mask[row1, column1]
    row_fraction = rows_position - row0
    column_fraction = columns_position - column0
    values = (1.0 - row_fraction) * (1.0 - column_fraction) * height[row0, column0] + row_fraction * (1.0 - column_fraction) * height[row1, column0] + (1.0 - row_fraction) * column_fraction * height[row0, column1] + row_fraction * column_fraction * height[row1, column1]
    if _i25_np.any(~valid) or not _i25_np.isfinite(values).all():
        return None
    return values

def _dense_segment(start, end, spacing):
    length = float(_i25_np.linalg.norm(end - start))
    count = max(1, int(_i25_math.ceil(length / spacing)))
    return _i25_np.linspace(start, end, count + 1, dtype=_i25_np.float64)

def _metric_cutoff_orientation(first, second, third):
    first_delta = second - first
    second_delta = third - first
    value = float(first_delta[0] * second_delta[1] - first_delta[1] * second_delta[0])
    if abs(value) <= 1e-10:
        return 0
    return 1 if value > 0.0 else -1

def _metric_cutoff_segments_intersect(first, second, third, fourth):
    orientations = (_metric_cutoff_orientation(first, second, third), _metric_cutoff_orientation(first, second, fourth), _metric_cutoff_orientation(third, fourth, first), _metric_cutoff_orientation(third, fourth, second))
    if orientations[0] * orientations[1] < 0 and orientations[2] * orientations[3] < 0:
        return True

    def on_segment(start, end, point):
        if _metric_cutoff_orientation(start, end, point) != 0:
            return False
        return min(start[0], end[0]) - 1e-10 <= point[0] <= max(start[0], end[0]) + 1e-10 and min(start[1], end[1]) - 1e-10 <= point[1] <= max(start[1], end[1]) + 1e-10
    return on_segment(first, second, third) or on_segment(first, second, fourth) or on_segment(third, fourth, first) or on_segment(third, fourth, second)

def _crosses_centerline(shortcut_start, shortcut_end, centerline, start_index, end_index):
    for index in range(len(centerline) - 1):
        if index in (start_index - 1, start_index, end_index - 1, end_index):
            continue
        if _metric_cutoff_segments_intersect(shortcut_start, shortcut_end, centerline[index], centerline[index + 1]):
            return True
    return False

def _edge_span(edge_ids, start_index, end_index):
    return tuple(edge_ids[start_index:end_index])

def _candidate_event(parent_graph, parent_geometry, edge_ids, start, end, loop_length, shortcut_length, sinuosity_before, water_transfer, sediment_transfer, config):
    from terrain_pipeline.surface_rivers.metric_morphology_events import MorphologyEvent as _i25_MorphologyEvent
    body = {'parent_graph_identity_sha256': parent_graph, 'parent_geometry_identity_sha256': parent_geometry, 'edge_ids': list(edge_ids), 'start': start, 'end': end, 'seed': config.seed}
    digest = _i25_hashlib.sha256(_i25_json.dumps(body, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    added_edge = 'cutoff-' + digest[:24]
    loop_edges = _edge_span(edge_ids, start, end)
    event = _i25_MorphologyEvent('cutoff-' + digest, 'cutoff', parent_graph, parent_geometry, loop_edges, (added_edge,), loop_edges, water_transfer, sediment_transfer, {}, {'algorithm': 'cutoff-v1', 'neck_distance_m': config.neck_distance_m, 'min_loop_length_m': config.min_loop_length_m, 'min_node_gap': config.min_node_gap, 'max_bed_rise_m': config.max_bed_rise_m, 'seed': config.seed, 'neck_indices': [start, end], 'loop_length_m': loop_length, 'shortcut_length_m': shortcut_length, 'sinuosity_before': sinuosity_before, 'sinuosity_after': 1.0, 'lake_candidate': True})
    return event

def find_cutoff_candidate(terrain: _i25_TerrainGrid, centerline_xz_m: _i25_np.ndarray, edge_ids: tuple[str, ...], parent_graph_identity_sha256: str, parent_geometry_identity_sha256: str, water_transfer_m3, sediment_transfer_solid_m3, config=None) -> dict:
    from terrain_pipeline.common_infra import TerrainGrid as _i25_TerrainGrid
    if not isinstance(terrain, _i25_TerrainGrid):
        raise ValueError('TerrainGrid required')
    if config is None:
        config = CutoffConfig()
    if not isinstance(config, CutoffConfig):
        raise ValueError('CutoffConfig required')
    points = _i25_np.asarray(centerline_xz_m)
    if points.dtype != _i25_np.float64 or points.ndim != 2 or points.shape[1] != 2 or (len(points) < 5):
        raise ValueError('centerline must be float64 [N,2] with at least five points')
    if not _i25_np.isfinite(points).all():
        raise ValueError('centerline must be finite')
    if _i25_np.any(_i25_np.linalg.norm(_i25_np.diff(points, axis=0), axis=1) <= 0.0):
        raise ValueError('centerline adjacent nodes must be distinct')
    if not isinstance(edge_ids, tuple) or len(edge_ids) != len(points) - 1 or any((not isinstance(value, str) or not value for value in edge_ids)):
        raise ValueError('edge_ids must contain one unique nonempty ID per centerline edge')
    if len(set(edge_ids)) != len(edge_ids):
        raise ValueError('edge_ids must be unique')
    water_transfer = _finite_transfer(water_transfer_m3, 'water_transfer_m3')
    sediment_transfer = _finite_transfer(sediment_transfer_solid_m3, 'sediment_transfer_solid_m3')
    if not isinstance(parent_graph_identity_sha256, str) or len(parent_graph_identity_sha256) != 64 or any((c not in '0123456789abcdef' for c in parent_graph_identity_sha256)):
        raise ValueError('parent graph identity must be lowercase SHA256')
    if not isinstance(parent_geometry_identity_sha256, str) or len(parent_geometry_identity_sha256) != 64 or any((c not in '0123456789abcdef' for c in parent_geometry_identity_sha256)):
        raise ValueError('parent geometry identity must be lowercase SHA256')
    centerline_bed = _sample_grid(terrain, points)
    if centerline_bed is None:
        raise ValueError('centerline leaves terrain valid mask')
    cumulative = _i25_np.r_[0.0, _i25_np.cumsum(_i25_np.linalg.norm(_i25_np.diff(points, axis=0), axis=1))]
    spacing = min(terrain.dx_m, terrain.dz_m) * 0.25
    candidates = []
    for start in range(len(points) - config.min_node_gap):
        for end in range(start + config.min_node_gap, len(points)):
            neck_length = float(_i25_np.linalg.norm(points[end] - points[start]))
            loop_length = float(cumulative[end] - cumulative[start])
            shortcut_length = neck_length
            if neck_length > config.neck_distance_m or loop_length - shortcut_length < config.min_loop_length_m:
                continue
            shortcut = _dense_segment(points[start], points[end], spacing)
            shortcut_bed = _sample_grid(terrain, shortcut)
            if shortcut_bed is None or float(_i25_np.max(shortcut_bed) - max(centerline_bed[start], centerline_bed[end])) > config.max_bed_rise_m + 1e-09:
                continue
            if _crosses_centerline(points[start], points[end], points, start, end):
                continue
            candidates.append((loop_length - shortcut_length, start, end, loop_length, shortcut_length, shortcut))
    candidates.sort(key=lambda value: (-value[0], value[1], value[2]))
    candidates = candidates[:config.max_candidates]
    if not candidates:
        return {'status': 'rejected', 'reason': 'no_valid_cutoff_neck', 'event': None, 'capabilities': {'topology_mutation': False, 'hydrodynamics': False, 'sediment_recompute': False}}
    saving, start, end, loop_length, shortcut_length, shortcut = candidates[0]
    loop = points[start:end + 1].copy()
    event = _candidate_event(parent_graph_identity_sha256, parent_geometry_identity_sha256, edge_ids, start, end, loop_length, shortcut_length, loop_length / shortcut_length, water_transfer, sediment_transfer, config)
    return {'status': 'candidate', 'shortcut_xz_m': shortcut, 'loop_xz_m': loop, 'neck_indices': (start, end), 'sinuosity_before': loop_length / shortcut_length, 'sinuosity_after': 1.0, 'lake_candidate': True, 'event': event, 'capabilities': {'topology_mutation': False, 'hydrodynamics': False, 'sediment_recompute': False}, 'saving_m': saving}
METRIC_CUTOFF_PRODUCT_SCHEMA = 'terragenesis-cutoff-material-candidate-v1'
REVALIDATION = ('topology', 'geometry', 'hydraulics', 'sediment', 'outlet')

@_i26_dataclass(frozen=True)
class CutoffMaterialConfig:
    corridor_half_width_m: float = 15.0
    shortcut_cut_depth_m: float = 0.1
    old_channel_fill_depth_m: float = 0.02
    porosity: float = 0.35

    def __post_init__(self):
        for name in ('corridor_half_width_m', 'shortcut_cut_depth_m', 'old_channel_fill_depth_m'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i26_math.isfinite(value)) or (value < 0.0):
                raise ValueError(name + ' must be finite nonnegative')
        if self.corridor_half_width_m <= 0.0 or isinstance(self.porosity, bool) or (not _i26_math.isfinite(self.porosity)) or (not 0.0 <= self.porosity < 1.0):
            raise ValueError('positive corridor and porosity in [0,1) required')

def _corridor(terrain, points, half_width):
    rows, cols = _i26_np.indices(terrain.elevation_m.shape)
    xz = _i26_np.stack((terrain.x0_m + cols * terrain.dx_m, terrain.z0_m + rows * terrain.dz_m), axis=-1)
    nearest = _i26_np.full(rows.shape, _i26_np.inf)
    for start, end in zip(points, points[1:]):
        delta = end - start
        fraction = _i26_np.clip(_i26_np.sum((xz - start) * delta, axis=-1) / float(delta @ delta), 0.0, 1.0)
        nearest = _i26_np.minimum(nearest, _i26_np.linalg.norm(xz - start - fraction[..., None] * delta, axis=-1))
    return (nearest <= half_width + 1e-09) & terrain.valid_mask

def _build(terrain, centerline, edge_ids, old_water_depth_m, old_mobile_solid_m3, alluvium_bulk_depth_m, rock_floor_m, cutoff_config, material_config):
    from terrain_pipeline.common_infra import identity as _i26_identity
    from terrain_pipeline.common_infra import readonly as _i26_readonly
    from terrain_pipeline.lake import LakeStorage as _i26_LakeStorage
    from terrain_pipeline.surface_rivers.metric_morphology_events import MorphologyEvent as _i26_MorphologyEvent
    shape = terrain.elevation_m.shape
    if not isinstance(centerline, _i26_np.ndarray) or centerline.dtype != _i26_np.float64 or centerline.ndim != 2 or (centerline.shape[1] != 2) or (len(centerline) < 5) or (not _i26_np.isfinite(centerline).all()) or _i26_np.any(_i26_np.linalg.norm(_i26_np.diff(centerline, axis=0), axis=1) <= 0.0):
        raise ValueError('finite distinct float64 cutoff centerline required')
    inputs = (old_water_depth_m, old_mobile_solid_m3, alluvium_bulk_depth_m, rock_floor_m)
    for value in inputs:
        if not isinstance(value, _i26_np.ndarray) or value.dtype != _i26_np.float64 or value.shape != shape or (not _i26_np.isfinite(value).all()):
            raise ValueError('finite float64 native inventory grids required')
    if any((_i26_np.any(value < 0.0) for value in inputs[:3])):
        raise ValueError('negative cutoff inventory')
    if _i26_np.any(rock_floor_m > terrain.elevation_m - alluvium_bulk_depth_m + 1e-10):
        raise ValueError('alluvium penetrates geological rock floor')
    graph_id = _i26_identity({'centerline_xz_m': centerline}, {'edge_ids': list(edge_ids), 'terrain_identity_sha256': terrain.identity_sha256, 'status': 'caller_supplied_centerline_graph_not_certified_routing'})
    old = _corridor(terrain, centerline, material_config.corridor_half_width_m)
    if _i26_np.any(((old_water_depth_m != 0.0) | (old_mobile_solid_m3 != 0.0)) & ~old):
        raise ValueError('old water/mobile inventory outside declared old channel')
    geometry_id = _i26_identity({'old_channel_mask': old, 'terrain_elevation_m': terrain.elevation_m, 'alluvium_bulk_depth_m': alluvium_bulk_depth_m, 'rock_floor_m': rock_floor_m}, {'graph_identity_sha256': graph_id, 'material_config': _i26_asdict(material_config)})
    result = find_cutoff_candidate(terrain, centerline, edge_ids, graph_id, geometry_id, 0.0, 0.0, cutoff_config)
    arrays = {'terrain_elevation_m': terrain.elevation_m, 'terrain_valid_mask': terrain.valid_mask, 'centerline_xz_m': centerline, 'old_channel_mask': old, 'initial_water_depth_m': old_water_depth_m, 'initial_mobile_solid_m3': old_mobile_solid_m3, 'initial_alluvium_bulk_depth_m': alluvium_bulk_depth_m, 'rock_floor_m': rock_floor_m}
    meta = {'schema': METRIC_CUTOFF_PRODUCT_SCHEMA, 'terrain_metadata': {name: getattr(terrain, name) for name in terrain.__dataclass_fields__ if name not in ('elevation_m', 'valid_mask')}, 'terrain_identity_sha256': terrain.identity_sha256, 'parent_graph_identity_sha256': graph_id, 'parent_geometry_identity_sha256': geometry_id, 'edge_ids': list(edge_ids), 'cutoff_config': _i26_asdict(cutoff_config), 'material_config': _i26_asdict(material_config), 'status': result['status'], 'failure_reason': result.get('reason'), 'event_record': None, 'revalidation_required': list(REVALIDATION), 'capabilities': {'topology_mutation': False, 'hydrodynamics': False, 'dynamic_inventory_migration': False, 'natural_outlet': False, 'publishable': False}, 'inventory_provenance': 'explicit native-cell stock scenario; not a solved ChannelState migration', 'geometry_provenance': 'explicit native-cell corridor, depth incision and old-channel fill proposal; longitudinal hydraulics unvalidated'}
    if result['status'] == 'candidate':
        shortcut = _corridor(terrain, result['shortcut_xz_m'], material_config.corridor_half_width_m)
        residual = _corridor(terrain, result['loop_xz_m'], material_config.corridor_half_width_m) & ~shortcut
        if not _i26_np.any(shortcut) or not _i26_np.any(residual):
            meta.update(status='rejected', failure_reason='no_disjoint_shortcut_and_residual_native_support')
        else:
            area, solid_fraction = (terrain.cell_area_m2, 1.0 - material_config.porosity)
            cut = _i26_np.where(shortcut, _i26_np.minimum(material_config.shortcut_cut_depth_m, _i26_np.maximum(terrain.elevation_m - rock_floor_m, 0.0)), 0.0)
            loose_cut_bulk = _i26_np.minimum(cut, alluvium_bulk_depth_m) * area
            rock_cut = cut * area - loose_cut_bulk
            cut_solid = loose_cut_bulk * solid_fraction + rock_cut
            fill_requested = residual * material_config.old_channel_fill_depth_m * area
            requested_solid = float(fill_requested.sum()) * solid_fraction
            excavated = float(cut_solid.sum())
            fill_scale = min(1.0, excavated / requested_solid) if requested_solid else 1.0
            fill_bulk = fill_requested * fill_scale
            fill_solid = fill_bulk * solid_fraction
            unresolved_excavation = excavated - float(fill_solid.sum())
            after_bed = terrain.elevation_m - cut + fill_bulk / area
            water_volume = old_water_depth_m * area
            residual_water = _i26_np.where(residual, water_volume, 0.0)
            surviving_water = water_volume - residual_water
            residual_mobile = _i26_np.where(residual, old_mobile_solid_m3, 0.0)
            surviving_mobile = old_mobile_solid_m3 - residual_mobile
            ids = _i26_np.flatnonzero(residual).astype(_i26_np.int64)
            lake = _i26_LakeStorage(ids, after_bed.ravel()[ids], _i26_np.full(len(ids), area), int(ids[_i26_np.argmin(after_bed.ravel()[ids])]), float(_i26_np.max(after_bed.ravel()[ids]) + 10.0 + residual_water.sum() / area), terrain.identity_sha256, 'disjoint residual old-channel native cells; candidate level pool, no port coupling')
            stage = lake.stage_at_volume(float(residual_water.sum()))
            arrays.update(shortcut_mask=shortcut, residual_mask=residual, shortcut_xz_m=result['shortcut_xz_m'], loop_xz_m=result['loop_xz_m'], cut_depth_m=cut, cut_alluvium_bulk_m3=loose_cut_bulk, cut_rock_m3=rock_cut, cut_solid_m3=cut_solid, fill_bulk_m3=fill_bulk, fill_solid_m3=fill_solid, after_bed_m=after_bed, after_alluvium_solid_m3=(alluvium_bulk_depth_m * area - loose_cut_bulk) * solid_fraction + fill_solid, residual_water_m3=residual_water, surviving_water_m3=surviving_water, residual_mobile_solid_m3=residual_mobile, surviving_mobile_solid_m3=surviving_mobile, residual_lake_cell_ids=ids, residual_lake_hypsometry_stage_m=_i26_np.array([lake.min_stage_m, stage, lake.max_stage_m]), residual_lake_hypsometry_volume_m3=_i26_np.array([0.0, lake.volume_at_stage(stage), lake.capacity_m3]))
            ledger = {'deposited_solid_m3': float(fill_solid.sum()), 'exported_solid_m3': 0.0, 'unresolved_solid_m3': unresolved_excavation, 'cut_rock_m3': float(rock_cut.sum()), 'fill_m3': float(fill_bulk.sum()), 'porous_deposit_m3': float(fill_bulk.sum())}
            event = _i26_MorphologyEvent(result['event'].event_id, 'cutoff', graph_id, geometry_id, result['event'].affected_edges, result['event'].added_edges, result['event'].retired_edges, 0.0, excavated, ledger, {**result['event'].to_record()['parameters'], 'topology_status': 'candidate_not_written', 'stock_proposal_identity_sha256': _i26_identity({'water_depth_m': old_water_depth_m, 'mobile_solid_m3': old_mobile_solid_m3}, {'terrain_identity_sha256': terrain.identity_sha256}), 'residual_water_m3': float(residual_water.sum()), 'surviving_water_m3': float(surviving_water.sum()), 'residual_mobile_solid_m3': float(residual_mobile.sum()), 'unresolved_dynamic_water_m3': float(water_volume.sum()), 'unresolved_dynamic_mobile_solid_m3': float(old_mobile_solid_m3.sum()), 'residual_level_pool_stage_m': stage, 'residual_connectivity_status': 'native_volume_support_only; wet connectivity and oxbow ports unvalidated', 'unfunded_fill_bulk_m3': float(fill_requested.sum() - fill_bulk.sum())}, REVALIDATION)
            meta['event_record'] = event.to_record()
            meta['material_ledger'] = ledger
    arrays = {name: _i26_readonly(_i26_np.ascontiguousarray(value)) for name, value in arrays.items()}
    bundle = {'arrays': arrays, 'metadata': meta, 'identity_sha256': _i26_identity(arrays, meta)}
    return bundle

def build_cutoff_material_candidate(terrain, centerline, edge_ids, old_water_depth_m, old_mobile_solid_m3, alluvium_bulk_depth_m, rock_floor_m, cutoff_config=None, material_config=None):
    return _build(terrain, centerline, edge_ids, old_water_depth_m, old_mobile_solid_m3, alluvium_bulk_depth_m, rock_floor_m, cutoff_config or CutoffConfig(), material_config or CutoffMaterialConfig())

def validate_cutoff_material_candidate(bundle):
    from terrain_pipeline.common_infra import identity as _i26_identity
    from terrain_pipeline.common_infra import TerrainGrid as _i26_TerrainGrid
    from terrain_pipeline.surface_rivers.metric_morphology_events import event_from_record as _i26_event_from_record
    a, m = (bundle['arrays'], bundle['metadata'])
    if bundle['identity_sha256'] != _i26_identity(a, m) or m.get('schema') != METRIC_CUTOFF_PRODUCT_SCHEMA:
        raise ValueError('cutoff material identity/schema mismatch')
    terrain = _i26_TerrainGrid(a['terrain_elevation_m'], a['terrain_valid_mask'], **m['terrain_metadata'])
    rebuilt = _build(terrain, a['centerline_xz_m'], tuple(m['edge_ids']), a['initial_water_depth_m'], a['initial_mobile_solid_m3'], a['initial_alluvium_bulk_depth_m'], a['rock_floor_m'], CutoffConfig(**m['cutoff_config']), CutoffMaterialConfig(**m['material_config']))
    if rebuilt['identity_sha256'] != bundle['identity_sha256']:
        raise ValueError('cutoff material/native stock proposal not reproducible')
    if m['status'] == 'candidate':
        _i26_event_from_record(m['event_record'])
        if _i26_np.any(a['shortcut_mask'] & a['residual_mask']):
            raise ValueError('cutoff supports overlap')
        expected = a['initial_water_depth_m'] * terrain.cell_area_m2
        if not _i26_np.allclose(a['residual_water_m3'] + a['surviving_water_m3'], expected, rtol=0.0, atol=1e-10):
            raise ValueError('cutoff residual/surviving water budget mismatch')
        if not _i26_np.allclose(a['residual_mobile_solid_m3'] + a['surviving_mobile_solid_m3'], a['initial_mobile_solid_m3'], rtol=0.0, atol=1e-10):
            raise ValueError('cutoff mobile stock budget mismatch')
        if not _i26_math.isclose(float(a['cut_solid_m3'].sum()), float(a['fill_solid_m3'].sum()) + m['material_ledger']['unresolved_solid_m3'], rel_tol=0.0, abs_tol=1e-08):
            raise ValueError('cutoff excavation/fill solid budget mismatch')
    return True

def save_cutoff_material_candidate(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _i26_save_bundle
    _i26_save_bundle(path, bundle, validator=validate_cutoff_material_candidate)

def load_cutoff_material_candidate(path, *, expected_sha256):
    from terrain_pipeline.common_infra import load_bundle as _i26_load_bundle
    return _i26_load_bundle(path, expected_sha256=expected_sha256, validator=validate_cutoff_material_candidate)
METRIC_DISCHARGE_GEOMETRY_ALGORITHM = 'monthly_discharge_material_trapezoid_v2'

@_i28_dataclass(frozen=True)
class DischargeGeometryConfig:
    generation_exposure: float = 3.0
    width_at_unit_q_m: float = 4.0
    depth_at_unit_q_m: float = 0.6
    width_q_exponent: float = 0.45
    depth_q_exponent: float = 0.3
    max_width_m: float = 120.0
    max_incise_m: float = 4.0
    bottom_width_fraction: float = 0.6

    def __post_init__(self):
        for name, value in _i28_asdict(self).items():
            if isinstance(value, (bool, _i28_np.bool_)) or not isinstance(value, (int, float, _i28_np.integer, _i28_np.floating)) or (not _i28_math.isfinite(value)):
                raise ValueError(name + ' must be a finite number')
        if not 0.0 <= self.generation_exposure <= 100.0:
            raise ValueError('generation_exposure must be dimensionless in [0, 100]')
        for name in ('width_at_unit_q_m', 'depth_at_unit_q_m', 'max_width_m'):
            if not 0.0 < getattr(self, name) <= 10000.0:
                raise ValueError(name + ' must be in (0, 10000]')
        if not 0.0 < self.max_incise_m <= 4.0:
            raise ValueError('max_incise_m must be in (0, 4] metres below source TD')
        if not 0.0 < self.bottom_width_fraction < 1.0:
            raise ValueError('bottom_width_fraction must be in (0, 1)')
        if not 0.0 < self.width_q_exponent <= 1.0 or not 0.0 < self.depth_q_exponent <= 1.0:
            raise ValueError('discharge exponents must be in (0, 1]')

def channel_section_cut(offset_m, width_m, depth_m, *, bottom_width_fraction=0.6):
    """Return incision metres at signed lateral offsets in a parametric section.

    Width is the top incision width; depth is source-relative cutting, never a
    water depth. The flat bottom occupies bottom_width_fraction of top width.
    """
    offset, width, depth = _i28_np.broadcast_arrays(_i28_np.asarray(offset_m, _i28_np.float64), _i28_np.asarray(width_m, _i28_np.float64), _i28_np.asarray(depth_m, _i28_np.float64))
    if not _i28_np.isfinite(offset).all() or not _i28_np.isfinite(width).all() or (not _i28_np.isfinite(depth).all()) or _i28_np.any(width < 0.0) or _i28_np.any(depth < 0.0) or (not _i28_np.isfinite(bottom_width_fraction)) or (not 0.0 < bottom_width_fraction < 1.0):
        raise ValueError('finite offsets, nonnegative dimensions and bottom fraction required')
    bank_run = width * (1.0 - bottom_width_fraction) / 2.0
    weight = _i28_np.zeros_like(offset)
    _i28_np.divide(width / 2.0 - _i28_np.abs(offset), bank_run, out=weight, where=bank_run > 0.0)
    return depth * _i28_np.clip(weight, 0.0, 1.0)

def _hardness(value, shape, name):
    array = _i28_np.asarray(value, _i28_np.float64)
    if array.ndim == 0:
        array = _i28_np.full(shape, float(array))
    if array.shape != shape or not _i28_np.isfinite(array).all() or _i28_np.any(array < 0.0) or _i28_np.any(array > 1.0):
        raise ValueError(name + ' must be scalar or matching field in [0, 1]')
    return array

def build_discharge_geometry(source_elevation_m, discharge_q_m3_s, channel_mask, spacing_m, *, bed_hardness=0.5, bank_hardness=0.5, protected_mask=None, config=None):
    """Derive a separate geometry field while preserving the caller's TD/DAG.

    Discharge may be an already averaged 2D Q field or 12 monthly Q fields.
    Raster cuts use the nearest active channel's section in its Voronoi region.
    This is a deterministic coarse heightfield projection, not a hydraulic or
    sediment simulation. Subgrid sections remain available as width/depth fields.
    """
    from terrain_pipeline.runoff import MONTH_SECONDS as _i28_MONTH_SECONDS
    config = DischargeGeometryConfig() if config is None else config
    if not isinstance(config, DischargeGeometryConfig):
        raise ValueError('DischargeGeometryConfig required')
    source = _i28_np.asarray(source_elevation_m, _i28_np.float64)
    discharge = _i28_np.asarray(discharge_q_m3_s, _i28_np.float64)
    channel = _i28_np.asarray(channel_mask)
    if source.ndim != 2 or not 1 <= source.size <= 4000000 or discharge.shape not in (source.shape, (12, *source.shape)) or (channel.shape != source.shape) or (channel.dtype.kind != 'b') or (not _i28_np.isfinite(source).all()) or (not _i28_np.isfinite(discharge).all()) or _i28_np.any(discharge < 0.0):
        raise ValueError('finite bounded terrain, representative or 12 monthly Q fields and boolean channel mask required')
    if isinstance(spacing_m, (bool, _i28_np.bool_)) or not _i28_np.isfinite(spacing_m) or (not 0.0 < spacing_m <= 10000.0):
        raise ValueError('spacing_m must be in (0, 10000]')
    protected = _i28_np.zeros(source.shape, bool) if protected_mask is None else _i28_np.asarray(protected_mask)
    if protected.shape != source.shape or protected.dtype.kind != 'b':
        raise ValueError('protected_mask must be a matching boolean field')
    bed = _hardness(bed_hardness, source.shape, 'bed_hardness')
    bank = _hardness(bank_hardness, source.shape, 'bank_hardness')
    q = discharge.copy() if discharge.ndim == 2 else _i28_np.einsum('m,mij->ij', _i28_MONTH_SECONDS / _i28_MONTH_SECONDS.sum(), discharge)
    if not _i28_np.isfinite(q).all():
        raise ValueError('representative monthly discharge overflow')
    active = channel & (q > 0.0)
    raster_cut_active = active & ~protected
    width = _i28_np.zeros(source.shape, _i28_np.float64)
    depth = _i28_np.zeros(source.shape, _i28_np.float64)
    exposure = -_i28_math.expm1(-config.generation_exposure)
    width[active] = _i28_np.minimum(config.max_width_m, config.width_at_unit_q_m * q[active] ** config.width_q_exponent * (1.0 + 1.5 * bed[active]) * (0.5 + 1.5 * (1.0 - bank[active]))) * exposure
    depth[active] = _i28_np.minimum(config.max_incise_m, config.depth_at_unit_q_m * q[active] ** config.depth_q_exponent * (0.4 + 1.2 * (1.0 - bed[active])) * (0.8 + 0.4 * bank[active])) * exposure
    cut = _i28_np.zeros(source.shape, _i28_np.float64)
    if raster_cut_active.any() and exposure > 0.0:
        distance, nearest = _i28_distance_transform_edt(~raster_cut_active, sampling=float(spacing_m), return_indices=True)
        nearest_width = width[nearest[0], nearest[1]]
        nearest_depth = depth[nearest[0], nearest[1]]
        cut = channel_section_cut(distance, nearest_width, nearest_depth, bottom_width_fraction=config.bottom_width_fraction)
        cut[protected] = 0.0
    removed = float(cut.sum(dtype=_i28_np.float64) * float(spacing_m) ** 2)
    if not _i28_math.isfinite(removed):
        raise ValueError('removed material volume overflow')
    arrays = dict(representative_q_m3_s=q, channel_width_m=width, bottom_width_m=width * config.bottom_width_fraction, channel_depth_m=depth, cut_depth_m=cut, bed_elevation_m=source - cut, bed_hardness=bed.copy(), bank_hardness=bank.copy(), channel_mask=channel.copy())
    metadata = dict(algorithm=METRIC_DISCHARGE_GEOMETRY_ALGORITHM, config=_i28_asdict(config), spacing_m=float(spacing_m), representative_discharge='caller_supplied_mean_m3_s' if discharge.ndim == 2 else 'calendar_duration_weighted_monthly_mean_m3_s', exposure_units='dimensionless_generation_budget_not_physical_years', width_definition='top_source_relative_incision_width_m', depth_definition='incision_below_immutable_TD_not_water_depth_m', raster_projection='nearest_unprotected_active_channel_Voronoi_trapezoid', protected_water_policy='retain_design_sections_exclude_cut_seeds_zero_raster_cut', volume_measure='coarse_raster_edit_sum_cut_times_cell_area_not_subgrid_channel_volume', subgrid_sections_resolved=False, hydraulic_solution=False, material_budget=dict(coarse_raster_edit_bulk_m3=removed, removed_terrain_bulk_m3=removed, unplaced_excavated_bulk_m3=removed, redeposited_bulk_m3=0.0, sediment_export_solved=False), limitations=['parametric sections may be narrower than the source grid', 'raster edit volume is not the unresolved parametric channel excavation volume', 'nearest-channel projection does not resolve overlapping sections', 'excavation retained as unplaced budget; sediment routing unsolved'])
    return dict(arrays=arrays, metadata=metadata)
METRIC_DOMAIN_CHANNEL_GEOMETRY_SCHEMA = 'river-domain-channel-geometry-adapter-v1'
METRIC_DOMAIN_CHANNEL_GEOMETRY_ALGORITHM = 'domain-channel-geometry-adapter-v1'
METRIC_DOMAIN_CHANNEL_GEOMETRY_LIMITATIONS = ('finite world-anchored tile and selected core domain only', 'receivers outside the selected core are refused as unresolved_border', 'does not certify an infinite or cross-tile main river network', 'underlying channel geometry remains hydraulic_ready=false and publishable=false')

def build_domain_channel_geometry(terrain: _i29_TerrainGrid, topology: dict, *, node_cell_ids, receiver, width_m, depth_m, owner_xz_m, owner_grid, corridor_mask, lake_mask, anchor_mask, outlet_x_m, outlet_z_m, terminal_kind, config=None, lake_stage_m=None):
    """Build one finite domain's canonical channel geometry.

    ``node_cell_ids`` are flattened ``[z,x]`` ids in ``terrain`` and must be the
    accepted core cells of one outlet.  All masks and ``owner_xz_m`` are explicit
    same-shape inputs; the adapter refuses to infer lake or border semantics from
    labels.  ``receiver`` is local to that node list; use ``-1`` only for a known
    terminal.  A receiver omitted from the selected domain is unresolved, not a mouth.
    """
    from terrain_pipeline.common_infra import identity as _i29_identity
    from terrain_pipeline.common_infra import TerrainGrid as _i29_TerrainGrid
    if not isinstance(terrain, _i29_TerrainGrid) or not isinstance(topology, dict):
        raise ValueError('TerrainGrid and topology mapping required')
    ids = _i29_np.asarray(node_cell_ids, _i29_np.int64).reshape(-1)
    local_receiver = _i29_np.asarray(receiver, _i29_np.int64).reshape(-1)
    width = _i29_np.asarray(width_m, _i29_np.float64).reshape(-1)
    depth = _i29_np.asarray(depth_m, _i29_np.float64).reshape(-1)
    n = ids.size
    if n < 2 or any((a.size != n for a in (local_receiver, width, depth))):
        raise ValueError('domain channel arrays must have the same size and at least two nodes')
    if _i29_np.any(ids < 0) or _i29_np.any(ids >= terrain.elevation_m.size) or _i29_np.unique(ids).size != n:
        raise ValueError('node_cell_ids must be unique terrain cell ids')
    if not (_i29_np.isfinite(width).all() and _i29_np.isfinite(depth).all()) or _i29_np.any(width <= 0) or _i29_np.any(depth < 0):
        raise ValueError('width must be positive and depth nonnegative')
    if _i29_np.any(local_receiver >= n) or _i29_np.any(local_receiver < -1):
        raise ValueError('receiver outside selected domain: unresolved_border')
    if terminal_kind not in {'ocean', 'closed_basin'}:
        raise ValueError('unsupported terminal classification: %s' % terminal_kind)
    shape = terrain.elevation_m.shape
    if not _i29_np.array_equal(_i29_np.asarray(topology.get('height_m')), terrain.elevation_m):
        raise ValueError('topology height and TerrainGrid height differ')
    accepted = _i29_np.asarray(topology.get('accepted'), bool)
    if accepted.shape != shape:
        raise ValueError('topology.accepted shape mismatch')
    if not accepted.reshape(-1)[ids].all():
        raise ValueError('domain nodes must be accepted core cells')
    accepted = _i29_np.asarray(topology.get('accepted'), bool)
    topology_owner_x = _i29_np.asarray(topology.get('owner_outlet_x_m'), _i29_np.float64)
    topology_owner_z = _i29_np.asarray(topology.get('owner_outlet_z_m'), _i29_np.float64)
    ocean_terminal = _i29_np.asarray(topology.get('ocean_terminal'), bool)
    if any((a.shape != shape for a in (accepted, topology_owner_x, topology_owner_z, ocean_terminal))):
        raise ValueError('topology accepted/owner/ocean arrays must match TerrainGrid')
    if not accepted.reshape(-1)[ids].all():
        raise ValueError('domain nodes must be accepted core cells (out_of_tile or refused cells rejected)')
    owner_points = _i29_np.asarray(owner_xz_m, _i29_np.float64)
    owner = _i29_np.asarray(owner_grid, _i29_np.int64)
    corridor = _i29_np.asarray(corridor_mask)
    lake = _i29_np.asarray(lake_mask)
    anchor = _i29_np.asarray(anchor_mask)
    if owner_points.shape != (n, 2) or not _i29_np.isfinite(owner_points).all() or owner.shape != shape or (corridor.dtype != bool) or (corridor.shape != shape) or (lake.dtype != bool) or (lake.shape != shape) or (anchor.dtype != bool) or (anchor.shape != (n,)):
        raise ValueError('explicit owner/corridor/lake/anchor inputs must match terrain and nodes')
    domain_key = (float(outlet_x_m), float(outlet_z_m))
    if not _i29_np.isfinite(domain_key).all():
        raise ValueError('finite outlet world coordinates required')
    if not _i29_np.all(topology_owner_x.reshape(-1)[ids] == domain_key[0]) or not _i29_np.all(topology_owner_z.reshape(-1)[ids] == domain_key[1]) or (not _i29_np.all(owner_points == domain_key)):
        raise ValueError('nodes do not share the requested topology outlet identity')
    actual_ocean = ocean_terminal.reshape(-1)[ids[local_receiver < 0]]
    if actual_ocean.size and _i29_np.any(actual_ocean != (terminal_kind == 'ocean')):
        raise ValueError('terminal classification disagrees with topology (ocean/coastal/closed_basin)')
    if terminal_kind == 'ocean' and lake.reshape(-1)[ids[local_receiver < 0]].any():
        raise ValueError('ocean terminals cannot be inferred as lakes; supply geometry-specific policy')
    if terminal_kind == 'closed_basin' and (not lake.reshape(-1)[ids[local_receiver < 0]].all()):
        raise ValueError('closed-basin terminal requires explicit lake support')
    topology_receiver = _i29_np.asarray(topology.get('receiver'), _i29_np.int64).reshape(-1)
    if topology_receiver.size != terrain.elevation_m.size:
        raise ValueError('topology.receiver shape mismatch')
    links = _i29_np.flatnonzero(local_receiver >= 0)
    if links.size and (not _i29_np.array_equal(topology_receiver[ids[links]], ids[local_receiver[links]])):
        raise ValueError('local receiver differs from domain topology')
    if links.size:
        receiver_ids = ids[local_receiver[links]]
        if _i29_np.any(owner.reshape(-1)[receiver_ids] != owner.reshape(-1)[ids[links]]):
            raise ValueError('receiver crosses domain ownership')
    geometry = build_channel_geometry(terrain, ids, local_receiver, width, depth, owner_grid=owner, corridor_mask=corridor, lake_mask=lake, anchor_mask=anchor, config=config, lake_stage_m=lake_stage_m)
    metadata = {'schema': METRIC_DOMAIN_CHANNEL_GEOMETRY_SCHEMA, 'algorithm': METRIC_DOMAIN_CHANNEL_GEOMETRY_ALGORITHM, 'source_terrain_identity_sha256': terrain.identity_sha256, 'channel_geometry_identity_sha256': geometry['identity_sha256'], 'outlet_x_m': domain_key[0], 'outlet_z_m': domain_key[1], 'terminal_kind': terminal_kind, 'node_count': int(n), 'topology_shape_zx': [int(terrain.elevation_m.shape[0]), int(terrain.elevation_m.shape[1])], 'channel_metadata': geometry['metadata'], 'limitations': list(METRIC_DOMAIN_CHANNEL_GEOMETRY_LIMITATIONS), 'hydraulic_ready': False, 'publishable': False}
    arrays = {'channel_' + key: value for key, value in geometry['arrays'].items()}
    record = {'arrays': arrays, 'metadata': metadata}
    record['identity_sha256'] = _i29_identity(arrays, metadata)
    return record

def validate_domain_channel_geometry(record):
    from terrain_pipeline.common_infra import identity as _i29_identity
    if not isinstance(record, dict) or set(record) != {'arrays', 'metadata', 'identity_sha256'}:
        raise ValueError('invalid domain channel geometry bundle')
    arrays = record['arrays']
    metadata = record['metadata']
    if metadata.get('schema') != METRIC_DOMAIN_CHANNEL_GEOMETRY_SCHEMA or metadata.get('algorithm') != METRIC_DOMAIN_CHANNEL_GEOMETRY_ALGORITHM:
        raise ValueError('domain channel geometry schema mismatch')
    geometry_arrays = {key[len('channel_'):]: value for key, value in arrays.items() if key.startswith('channel_')}
    geometry = {'arrays': geometry_arrays, 'metadata': metadata.get('channel_metadata'), 'identity_sha256': metadata.get('channel_geometry_identity_sha256')}
    validate_channel_geometry(geometry)
    if tuple(metadata.get('limitations', ())) != METRIC_DOMAIN_CHANNEL_GEOMETRY_LIMITATIONS:
        raise ValueError('domain channel geometry limitations mismatch')
    if metadata.get('hydraulic_ready') is not False or metadata.get('publishable') is not False:
        raise ValueError('domain channel geometry cannot claim hydraulic or publishable status')
    if _i29_identity(arrays, metadata) != record['identity_sha256']:
        raise ValueError('domain channel geometry identity mismatch')
    return True

def save_domain_channel_geometry(path, record):
    from terrain_pipeline.common_infra import save_bundle as _i29_save_bundle
    _i29_save_bundle(path, record, validator=validate_domain_channel_geometry)

def load_domain_channel_geometry(path, *, expected_sha256):
    from terrain_pipeline.common_infra import load_bundle as _i29_load_bundle
    return _i29_load_bundle(path, expected_sha256=expected_sha256, validator=validate_domain_channel_geometry)

def _number(value, name, nonnegative=False, positive=False):
    if isinstance(value, (bool, _i30_np.bool_)) or not isinstance(value, (int, float, _i30_np.integer, _i30_np.floating)):
        raise ValueError(name + ' must be numeric')
    value = float(value)
    if not _i30_math.isfinite(value) or (nonnegative and value < 0.0) or (positive and value <= 0.0):
        raise ValueError(name + ' outside finite bounds')
    return value

def _metric_fan_floodplain_sha(value, name):
    if not isinstance(value, str) or len(value) != 64 or any((character not in '0123456789abcdef' for character in value)):
        raise ValueError(name + ' must be a lowercase SHA256')

def _point(value, name):
    if not isinstance(value, (tuple, list, _i30_np.ndarray)) or len(value) != 2:
        raise ValueError(name + ' must be an XZ point')
    point = tuple((_number(item, name + ' coordinate') for item in value))
    if not _i30_np.isfinite(point).all():
        raise ValueError(name + ' must be finite')
    return point

def _polyline(value, name):
    if not isinstance(value, (tuple, list, _i30_np.ndarray)) or len(value) < 2:
        raise ValueError(name + ' requires at least two points')
    return tuple((_point(point, name + ' point') for point in value))

def _config_record(config):
    return {name: getattr(config, name) for name in config.__dataclass_fields__}

def _nearest_cell(terrain, point, name):
    column = int(round((point[0] - terrain.x0_m) / terrain.dx_m))
    row = int(round((point[1] - terrain.z0_m) / terrain.dz_m))
    if not (0 <= row < terrain.elevation_m.shape[0] and 0 <= column < terrain.elevation_m.shape[1]):
        raise ValueError(name + ' outside terrain')
    if not terrain.valid_mask[row, column]:
        raise ValueError(name + ' lies on unknown terrain')
    return (row, column)

def _metric_fan_floodplain_event_id(event_type, parent_graph, parent_geometry, parameters, ledger):
    payload = _i30_json.dumps({'event_type': event_type, 'parent_graph': parent_graph, 'parent_geometry': parent_geometry, 'parameters': parameters, 'ledger': ledger}, sort_keys=True, separators=(',', ':')).encode()
    return event_type + '-' + _i30_hashlib.sha256(payload).hexdigest()

def _capabilities():
    return {'hydraulic': False, 'natural_outlet': False, 'publishable': False}

@_i30_dataclass(frozen=True)
class FanFloodplainConfig:
    max_fan_radius_m: float = 32.0
    fan_half_angle_deg: float = 55.0
    max_deposit_depth_m: float = 1.0
    porosity: float = 0.35
    bank_height_m: float = 2.0
    max_floodplain_half_width_m: float = 24.0

    def __post_init__(self):
        for name in ('max_fan_radius_m', 'max_deposit_depth_m', 'bank_height_m', 'max_floodplain_half_width_m'):
            value = _number(getattr(self, name), name, positive=True)
            if value > 1000000.0:
                raise ValueError(name + ' exceeds resource bound')
            object.__setattr__(self, name, value)
        angle = _number(self.fan_half_angle_deg, 'fan_half_angle_deg', positive=True)
        if angle >= 90.0:
            raise ValueError('fan_half_angle_deg must be below 90 degrees')
        object.__setattr__(self, 'fan_half_angle_deg', angle)
        porosity = _number(self.porosity, 'porosity', nonnegative=True)
        if porosity >= 1.0:
            raise ValueError('porosity must be below one')
        object.__setattr__(self, 'porosity', porosity)

def _fan_cells(terrain, apex, direction, config):
    rows, columns = terrain.elevation_m.shape
    apex_height = terrain.elevation_m[_nearest_cell(terrain, apex, 'apex')]
    direction = _i30_np.asarray(direction, dtype=_i30_np.float64)
    length = float(_i30_np.linalg.norm(direction))
    if length <= 0.0:
        raise ValueError('flow_direction_xz must be nonzero')
    direction /= length
    half_angle = _i30_math.radians(config.fan_half_angle_deg)
    cells = []
    for row in range(rows):
        for column in range(columns):
            if not terrain.valid_mask[row, column]:
                continue
            point = _i30_np.array((terrain.x0_m + column * terrain.dx_m, terrain.z0_m + row * terrain.dz_m))
            offset = point - _i30_np.asarray(apex)
            distance = float(_i30_np.linalg.norm(offset))
            if distance <= 0.0 or distance > config.max_fan_radius_m:
                continue
            forward = float(_i30_np.dot(offset, direction))
            if forward <= 0.0 or forward / distance < _i30_math.cos(half_angle):
                continue
            if terrain.elevation_m[row, column] > apex_height + 1e-10:
                continue
            slope_factor = max(0.0, (apex_height - terrain.elevation_m[row, column]) / max(apex_height - _i30_np.min(terrain.elevation_m[terrain.valid_mask]), 1e-09))
            weight = max(1e-12, forward / config.max_fan_radius_m) * (0.25 + slope_factor)
            cells.append(((row, column), weight))
    return tuple(cells)

def _allocate(cells, capacity, total):
    allocation = {cell: 0.0 for cell, _ in cells}
    active = {cell for cell, _ in cells}
    weights = dict(cells)
    remaining = float(total)
    tolerance = 1e-12 * max(1.0, remaining)
    while active and remaining > tolerance:
        weight_sum = _i30_math.fsum((weights[cell] for cell in sorted(active)))
        if weight_sum <= 0.0 or not _i30_math.isfinite(weight_sum):
            break
        saturated = []
        for cell in sorted(active):
            share = remaining * weights[cell] / weight_sum
            room = capacity - allocation[cell]
            if share >= room - tolerance:
                allocation[cell] += max(0.0, room)
                saturated.append(cell)
        if not saturated:
            for cell in sorted(active):
                allocation[cell] += remaining * weights[cell] / weight_sum
            break
        remaining = float(total) - _i30_math.fsum(allocation.values())
        for cell in saturated:
            active.remove(cell)
    return allocation

def build_alluvial_fan_candidate(terrain, apex_xz_m, flow_direction_xz, sediment_solid_m3, parent_graph_identity_sha256, parent_geometry_identity_sha256, config=FanFloodplainConfig()):
    from terrain_pipeline.common_infra import TerrainGrid as _i30_TerrainGrid
    from terrain_pipeline.surface_rivers.metric_morphology_events import MorphologyEvent as _i30_MorphologyEvent
    if not isinstance(terrain, _i30_TerrainGrid) or not isinstance(config, FanFloodplainConfig):
        raise ValueError('TerrainGrid and FanFloodplainConfig required')
    apex = _point(apex_xz_m, 'apex_xz_m')
    direction = _point(flow_direction_xz, 'flow_direction_xz')
    sediment = _number(sediment_solid_m3, 'sediment_solid_m3', nonnegative=True)
    _metric_fan_floodplain_sha(parent_graph_identity_sha256, 'parent graph identity')
    _metric_fan_floodplain_sha(parent_geometry_identity_sha256, 'parent geometry identity')
    cells = _fan_cells(terrain, apex, direction, config)
    capacity = terrain.cell_area_m2 * config.max_deposit_depth_m * (1.0 - config.porosity)
    allocation = _allocate(cells, capacity, sediment)
    shape = terrain.elevation_m.shape
    footprint = _i30_np.zeros(shape, dtype=bool)
    deposit_mask = _i30_np.zeros(shape, dtype=bool)
    height_delta = _i30_np.zeros(shape, dtype=_i30_np.float64)
    for cell, _ in cells:
        footprint[cell] = True
        if allocation[cell] > 0.0:
            deposit_mask[cell] = True
            height_delta[cell] = allocation[cell] / ((1.0 - config.porosity) * terrain.cell_area_m2)
    deposited = _i30_math.fsum(allocation.values())
    unresolved = max(0.0, sediment - deposited)
    ledger = {'deposited_solid_m3': deposited, 'exported_solid_m3': 0.0, 'unresolved_solid_m3': unresolved, 'cut_rock_m3': 0.0, 'fill_m3': 0.0, 'porous_deposit_m3': deposited / (1.0 - config.porosity)}
    parameters = {'apex_xz_m': list(apex), 'flow_direction_xz': list(direction), 'config': _config_record(config), 'footprint_cell_count': int(footprint.sum()), 'geometry_status': 'bounded_candidate_only'}
    event = _i30_MorphologyEvent(_metric_fan_floodplain_event_id('alluvial_fan', parent_graph_identity_sha256, parent_geometry_identity_sha256, parameters, ledger), 'alluvial_fan', parent_graph_identity_sha256, parent_geometry_identity_sha256, (), (), (), 0.0, sediment, ledger, parameters)
    return {'schema': 'terragenesis-metric-fan-candidate-v1', 'status': 'candidate', 'apex_xz_m': apex, 'height_delta_m': height_delta, 'deposit_mask': deposit_mask, 'footprint': footprint, 'material_ledger': ledger, 'event': event, 'hydraulic': False, 'natural_outlet': False, 'publishable': False, 'capabilities': _capabilities()}

def _segment_distance(point, start, end):
    vector = end - start
    length_squared = float(_i30_np.dot(vector, vector))
    if length_squared == 0.0:
        return (float(_i30_np.linalg.norm(point - start)), 0.0)
    fraction = float(_i30_np.clip(_i30_np.dot(point - start, vector) / length_squared, 0.0, 1.0))
    return (float(_i30_np.linalg.norm(point - (start + fraction * vector))), fraction)

def build_floodplain_candidate(terrain, centerline_xz_m, water_depth_m, parent_graph_identity_sha256, parent_geometry_identity_sha256, config=FanFloodplainConfig()):
    from terrain_pipeline.common_infra import TerrainGrid as _i30_TerrainGrid
    from terrain_pipeline.surface_rivers.metric_morphology_events import MorphologyEvent as _i30_MorphologyEvent
    if not isinstance(terrain, _i30_TerrainGrid) or not isinstance(config, FanFloodplainConfig):
        raise ValueError('TerrainGrid and FanFloodplainConfig required')
    centerline = _polyline(centerline_xz_m, 'centerline_xz_m')
    depth = _number(water_depth_m, 'water_depth_m', nonnegative=True)
    _metric_fan_floodplain_sha(parent_graph_identity_sha256, 'parent graph identity')
    _metric_fan_floodplain_sha(parent_geometry_identity_sha256, 'parent geometry identity')
    for start, end in zip(centerline, centerline[1:]):
        distance = float(_i30_np.linalg.norm(_i30_np.asarray(end) - _i30_np.asarray(start)))
        if distance <= 0.0:
            raise ValueError('centerline must not repeat points')
        for fraction in _i30_np.linspace(0.0, 1.0, max(2, int(_i30_math.ceil(distance / min(terrain.dx_m, terrain.dz_m))) + 1)):
            _nearest_cell(terrain, tuple(_i30_np.asarray(start) + fraction * (_i30_np.asarray(end) - _i30_np.asarray(start))), 'centerline')
    shape = terrain.elevation_m.shape
    inundation = _i30_np.zeros(shape, dtype=bool)
    height_delta = _i30_np.zeros(shape, dtype=_i30_np.float64)
    storage = 0.0
    effective_depth = min(depth, config.bank_height_m)
    points = [_i30_np.asarray(point, dtype=_i30_np.float64) for point in centerline]
    for row in range(shape[0]):
        for column in range(shape[1]):
            if not terrain.valid_mask[row, column]:
                continue
            point = _i30_np.array((terrain.x0_m + column * terrain.dx_m, terrain.z0_m + row * terrain.dz_m))
            nearest_distance = _i30_math.inf
            bed = None
            for start, end in zip(points, points[1:]):
                distance, fraction = _segment_distance(point, start, end)
                if distance < nearest_distance:
                    nearest_distance = distance
                    first = _nearest_cell(terrain, tuple(start), 'centerline')
                    second = _nearest_cell(terrain, tuple(end), 'centerline')
                    bed = (1.0 - fraction) * terrain.elevation_m[first] + fraction * terrain.elevation_m[second]
            if nearest_distance > config.max_floodplain_half_width_m or bed is None:
                continue
            local_depth = effective_depth + bed - terrain.elevation_m[row, column]
            if local_depth <= 0.0 or local_depth > config.bank_height_m + 1e-10:
                continue
            inundation[row, column] = True
            storage += local_depth * terrain.cell_area_m2
    parameters = {'centerline_xz_m': [list(point) for point in centerline], 'water_depth_m': depth, 'effective_depth_m': effective_depth, 'config': _config_record(config), 'geometry_status': 'bounded_wet_footprint_only'}
    ledger = {'deposited_solid_m3': 0.0, 'exported_solid_m3': 0.0, 'unresolved_solid_m3': 0.0, 'cut_rock_m3': 0.0, 'fill_m3': 0.0, 'porous_deposit_m3': 0.0}
    event = _i30_MorphologyEvent(_metric_fan_floodplain_event_id('floodplain_inundation', parent_graph_identity_sha256, parent_geometry_identity_sha256, parameters, ledger), 'floodplain_inundation', parent_graph_identity_sha256, parent_geometry_identity_sha256, (), (), (), 0.0, 0.0, ledger, parameters)
    return {'schema': 'terragenesis-metric-floodplain-candidate-v1', 'status': 'candidate', 'inundation_mask': inundation, 'height_delta_m': height_delta, 'storage_proxy_m3': float(storage), 'event': event, 'material_ledger': ledger, 'hydraulic': False, 'natural_outlet': False, 'publishable': False, 'capabilities': _capabilities()}

def _row_inside(ids, weights, retained):
    unique, inverse = _i33_np.unique(ids, return_inverse=True)
    combined = _i33_np.bincount(inverse, weights=weights)
    return bool(_i33_np.all(retained[unique[combined != 0.0]]))

def build_local(points, receiver, width, depth, profile, terrain, window, *, spacing, max_cut, bottom_slope, minimum_slope, maximum_depth=None):
    """Build original constraints whose combined support lies in a square.

    Bounds use the complete topology and all incident source cells. The default
    transverse radius is a lower witness of the full maximum upper cut, so it
    only omits full rows. ``maximum_depth`` may instead supply that exact full
    maximum, when already known; an arbitrary larger value is not a relaxation.
    """
    center, side = (_i33_np.asarray(window['center_xz_m']), window['side_m'])
    edges = _i33_np.flatnonzero(receiver >= 0)
    radius = _i33_np.maximum(width[edges], width[receiver[edges]]) / 2.0 + (_i33_np.sqrt(2.0) + 1.0) * spacing + 2.0 * max_cut
    lo = _i33_np.minimum(points[edges], points[receiver[edges]]) - radius[:, None]
    hi = _i33_np.maximum(points[edges], points[receiver[edges]]) + radius[:, None]
    selected = _i33_np.all((hi >= center - side / 2.0 - 2.0 * spacing) & (lo <= center + side / 2.0 + 2.0 * spacing), axis=1)
    partial_receiver = receiver.copy()
    partial_receiver[edges[~selected]] = -1
    offsets = _i33_np.r_[0, _i33_np.cumsum(_i33_np.diff(profile[0])[selected])]
    subset_profile = [offsets]
    for values in profile[1:]:
        parts = [values[profile[0][k]:profile[0][k + 1]] for k in _i33_np.flatnonzero(selected)]
        subset_profile.append(_i33_np.concatenate(parts) if parts else values[:0])
    subset_profile = tuple(subset_profile)
    options = _i33_SimpleNamespace(fine_spacing_m=spacing, max_vertices=8000000)
    cells = _sparse_cells(points, partial_receiver, width, subset_profile, options, terrain, support_radius_m=radius[selected])
    vertices, triangles = _sparse_mesh(cells, terrain, spacing, options.max_vertices)
    source = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)[0]
    lower, upper, padding = design_cut_bounds(points, receiver, width, depth, cells, vertices, triangles, terrain, spacing, max_cut)
    retained = _i33_np.all(_i33_np.abs(vertices - center) <= side / 2.0, axis=1)
    partial_boundary = interior_support_boundary_vertices(cells, vertices, terrain, spacing)
    interior_retained = retained.copy()
    interior_retained[partial_boundary] = False
    radius_policy = 'explicit full-model maximum upper'
    if maximum_depth is None:
        maximum_depth = float(_i33_np.max(upper[interior_retained], initial=0.0))
        radius_policy = 'maximum upper of non-boundary retained vertices; omission relaxation'
    base = bed_constraints(points, partial_receiver, cells, vertices, triangles, source, terrain, spacing, subset_profile, minimum_slope)
    node_mask = _i33_np.zeros(len(receiver), bool)
    node_mask[edges[selected]] = True
    terminal = receiver < 0
    node_mask[terminal] = _i33_np.all(_i33_np.abs(points[terminal] - center) <= side / 2.0 + _i33_np.max(radius, initial=0.0), axis=1)
    transverse = transverse_bed_constraints(points, receiver, width, cells, vertices, triangles, source, terrain, spacing, _i33_np.array([maximum_depth]), node_mask, bottom_slope)
    row_ids, columns, coefficients, limits, kinds = ([], [], [], [], [])

    def append(ids, weights, limit, kind):
        if not _row_inside(ids, weights, retained):
            return
        row_ids.extend([len(limits)] * len(ids))
        columns.extend(ids)
        coefficients.extend(weights)
        limits.append(limit)
        kinds.append(kind)
    for ids, weights, limit, kind in base:
        append(ids, weights, limit, kind)
    strip_count = len(transverse[2]) - transverse[3]
    for row, (ids, weights, limit) in enumerate(zip(*transverse[:3])):
        append(ids, weights, limit, 'strip' if row < strip_count else 'cap')
    matrix = _i33_coo_matrix((coefficients, (row_ids, columns)), shape=(len(limits), len(vertices))).tocsr()
    matrix.eliminate_zeros()
    active = _i33_np.unique(matrix.indices)
    return dict(matrix=matrix[:, active], limits=_i33_np.asarray(limits), kinds=_i33_np.asarray(kinds), vertices=vertices[active], source=source[active], bounds=_i33_np.column_stack((lower[active], upper[active])), source_padding=padding[active], selected_edges=int(selected.sum()), construction_vertices=len(vertices), transverse_maximum_depth=maximum_depth, transverse_radius_policy=radius_policy, boundary_policy='window boundary never locked; true full boundary upper=0 may be relaxed')

def assess_local(model, *, time_limit=120.0, feasibility_tolerance=1e-09):
    """Solve only the supplied local relaxation; time limits remain unknown."""
    variables = model['matrix'].shape[1]
    matrix, limits, bounds = (model['matrix'], model['limits'], model['bounds'])
    if limits.shape != (matrix.shape[0],) or bounds.shape != (variables, 2) or (not all((_i33_np.all(_i33_np.isfinite(value)) for value in (matrix.data, limits, bounds)))) or _i33_np.any(bounds[:, 0] > bounds[:, 1]):
        raise ValueError('local assessment needs finite consistent rows and bounds')
    options = dict(time_limit=time_limit, primal_feasibility_tolerance=feasibility_tolerance, dual_feasibility_tolerance=feasibility_tolerance)
    result = _i33_linprog(_i33_np.zeros(variables), A_ub=matrix, b_ub=limits, bounds=bounds, method='highs', options=options)
    outcome = 'infeasible' if result.status == 2 else 'clear' if result.status == 0 else 'unknown'
    assessment = dict(status=int(result.status), outcome=outcome, message=result.message, variable_count=variables, row_count=matrix.shape[0], solver_calls=1, interpretation='clear is local feasibility only; unknown excludes no path')
    if result.status == 0:
        solution = getattr(result, 'x', None)
        if solution is None or _i33_np.shape(solution) != (variables,) or (not _i33_np.all(_i33_np.isfinite(solution))):
            assessment.update(outcome='unknown', primal_valid=False)
            return assessment
        residual = max(float(_i33_np.max(matrix @ solution - limits, initial=0.0)), float(_i33_np.max(bounds[:, 0] - solution, initial=0.0)), float(_i33_np.max(solution - bounds[:, 1], initial=0.0)))
        assessment.update(primal_valid=residual <= 1e-08, primal_residual_m=residual)
        if residual > 1e-08:
            assessment['outcome'] = 'unknown'
    if result.status != 2:
        return assessment
    boundary = bounds[:, 1] == 0.0
    adjustable = _i33_np.flatnonzero(~boundary)
    ceilings = _i33_coo_matrix((_i33_np.r_[_i33_np.ones(variables), -_i33_np.ones(len(adjustable))], (_i33_np.r_[_i33_np.arange(variables), adjustable], _i33_np.r_[_i33_np.arange(variables), _i33_np.full(len(adjustable), variables)])), shape=(variables, variables + 1)).tocsr()
    relaxed_matrix = _i33_vstack((_i33_hstack((matrix, _i33_coo_matrix((matrix.shape[0], 1)))), ceilings), format='csr')
    relaxed_limits = _i33_np.r_[limits, bounds[:, 1]]
    relaxed_bounds = _i33_np.column_stack((bounds[:, 0], _i33_np.full(variables, _i33_np.inf)))
    relaxed_bounds[boundary, 1] = 0.0
    relaxed_bounds = _i33_np.vstack((relaxed_bounds, [0.0, _i33_np.inf]))
    objective = _i33_np.r_[_i33_np.zeros(variables), 1.0]
    relaxed = _i33_linprog(objective, A_ub=relaxed_matrix, b_ub=relaxed_limits, bounds=relaxed_bounds, method='highs', options=options)
    assessment['solver_calls'] = 2
    extra = dict(status=int(relaxed.status), message=relaxed.message, certificate_valid=False, dual_finite=False)
    assessment['extra_cut'] = extra
    if relaxed.status != 0:
        return assessment
    row_duals = relaxed.ineqlin.marginals
    lower_duals, upper_duals = (relaxed.lower.marginals, relaxed.upper.marginals)
    dual_finite = all((_i33_np.all(_i33_np.isfinite(value)) for value in (row_duals, lower_duals, upper_duals)))
    primal_finite = bool(_i33_np.all(_i33_np.isfinite(relaxed.x)))
    extra['dual_finite'] = dual_finite
    if not dual_finite or not primal_finite:
        return assessment
    finite_upper = _i33_np.isfinite(relaxed_bounds[:, 1])
    primal_residual = max(float(_i33_np.max(relaxed_matrix @ relaxed.x - relaxed_limits, initial=0.0)), float(_i33_np.max(relaxed_bounds[:, 0] - relaxed.x, initial=0.0)), float(_i33_np.max(relaxed.x[finite_upper] - relaxed_bounds[finite_upper, 1], initial=0.0)))
    stationarity = objective - relaxed_matrix.T @ row_duals - lower_duals - upper_duals
    dual_value = float(relaxed_limits @ row_duals + relaxed_bounds[:, 0] @ lower_duals + relaxed_bounds[finite_upper, 1] @ upper_duals[finite_upper])
    dual_residual = max(float(_i33_np.max(_i33_np.abs(stationarity), initial=0.0)), float(_i33_np.max(row_duals, initial=0.0)), float(_i33_np.max(-lower_duals, initial=0.0)), float(_i33_np.max(upper_duals, initial=0.0)), float(_i33_np.max(_i33_np.abs(upper_duals[~finite_upper]), initial=0.0)))
    gap = abs(float(relaxed.x[-1]) - dual_value)
    valid = primal_residual <= 1e-08 and dual_residual <= 1e-08 and (gap <= 1e-08)
    extra.update(certificate_valid=valid, primal_residual_m=primal_residual, dual_residual=dual_residual, primal_dual_gap_m=gap)
    if valid:
        roots = _i33_np.flatnonzero(lower_duals[:variables] > 1e-09)
        extra.update(minimum_extra_ceiling_m=float(relaxed.x[-1]), root_vertex_indices=roots.tolist(), root_lower_bound_duals=lower_duals[roots].tolist(), root_vertices_xz_m=model['vertices'][roots].tolist())
        extra['root_records'] = [dict(index=int(index), xz_m=model['vertices'][index].tolist(), lower_bound_dual=float(lower_duals[index]), lower_cut_m=float(bounds[index, 0]), source_padding_m=float(model['source_padding'][index])) for index in roots]
    return assessment

def design_support_edges(point, points, receiver, width, depth, spacing, lower_cut, source_padding):
    """Return every edge attaining this vertex's original design cut lower bound."""
    edges = _i31_np.flatnonzero(receiver >= 0)
    if not len(edges) or lower_cut <= 0.0:
        return []
    delta = points[receiver[edges]] - points[edges]
    t = _i31_np.clip(_i31_np.sum((point - points[edges]) * delta, axis=1) / _i31_np.sum(delta * delta, axis=1), 0.0, 1.0)
    distance = _i31_np.linalg.norm(point - (points[edges] + t[:, None] * delta), axis=1)
    design = _i31_np.maximum(depth[edges], depth[receiver[edges]])
    half = _i31_np.maximum(width[edges], width[receiver[edges]]) / 2.0 + _i31_np.sqrt(2.0) * spacing
    amount = _i31_np.minimum(design, _i31_np.maximum(0.0, (half + 2.0 * design - distance) / 2.0))
    maximum = float(_i31_np.max(amount, initial=0.0))
    if maximum <= 0.0 or abs(maximum + source_padding - lower_cut) > 1e-08:
        return []
    return [(int(source), int(receiver[source]), float(amount[index])) for index, source in enumerate(edges) if abs(amount[index] - maximum) <= 1e-10]

def assess_local_bed(points, receiver, width, depth, profile, terrain, window, *, spacing, max_cut, bottom_slope, minimum_slope, time_limit=120.0, feasibility_tolerance=1e-09):
    """Build and assess the actual local relaxation without a second LP layer.

    A clear result permits route search only. The complete bed solver remains
    responsible for global feasibility and final acceptance.
    """
    model = build_local(points, receiver, width, depth, profile, terrain, window, spacing=spacing, max_cut=max_cut, bottom_slope=bottom_slope, minimum_slope=minimum_slope)
    result = assess_local(model, time_limit=time_limit, feasibility_tolerance=feasibility_tolerance)
    assessment = dict(status=result['outcome'], solver_status=result['status'], message=result['message'], variables=result['variable_count'], rows=result['row_count'], solver_calls=result.get('solver_calls', 1), radius_policy=model['transverse_radius_policy'], boundary_policy=model['boundary_policy'])
    for name in ('maximum_row_residual_m', 'maximum_bound_residual_m'):
        if name in result:
            assessment[name] = result[name]
    extra = result.get('extra_cut')
    if assessment['status'] != 'infeasible' or extra is None or (not extra.get('certificate_valid', False)):
        return assessment
    assessment['extra_cut'] = extra['minimum_extra_ceiling_m']
    contributions, roots = ({}, [])
    for position, vertex in enumerate(extra['root_vertex_indices']):
        vertex = int(vertex)
        dual = float(extra['root_lower_bound_duals'][position])
        supporting = design_support_edges(model['vertices'][vertex], points, receiver, width, depth, spacing, model['bounds'][vertex, 0], model['source_padding'][vertex])
        roots.append(dict(vertex_xz_m=model['vertices'][vertex].tolist(), dual=dual, lower_cut_m=float(model['bounds'][vertex, 0]), source_padding_m=float(model['source_padding'][vertex]), supporting_edges=[[source, target] for source, target, _ in supporting]))
        for source, target, amount in supporting:
            edge = (source, target)
            contributions[edge] = contributions.get(edge, 0.0) + dual * amount
    assessment['dual_roots'] = roots
    assessment['contributing_edges'] = sorted(contributions, key=lambda edge: (-contributions[edge], edge))
    return assessment

def evaluate_necessary_budget(points, receiver, widths, profile, terrain, ids, spacing, max_cut, bottom_slope, focus=None):
    hotspots = []
    bounds = necessary_bounds(points, receiver, widths, profile, terrain, ids, spacing, max_cut, bottom_slope, focus_nodes=focus, hotspot_records=hotspots)
    maxima, counts = ([], [])
    for category in ('physical_half_bottom', 'bottom_guard_shell', 'bank'):
        buckets = [bounds[kind][category] for kind in ('edge_strip', 'node_cap')]
        maxima.append(max((bucket['maximum_required_cut_m'] for bucket in buckets)))
        counts.append(sum((bucket['violations'] for bucket in buckets)))
    return dict(maxima=maxima, counts=counts, hotspots=hotspots, bounds=bounds)

def budget_hotspot_targets(evaluation):
    targets = []
    for category in ('physical_half_bottom', 'bottom_guard_shell', 'bank'):
        hotspots = [hotspot for hotspot in evaluation['hotspots'] if hotspot['category'] == category]
        if not hotspots:
            continue
        worst = max(hotspots, key=lambda hotspot: hotspot['maximum_required_cut_m'])
        nodes = [worst['node_index']] if 'node_index' in worst else [worst['source_node_index'], worst['target_node_index']]
        for node in nodes:
            if node not in targets:
                targets.append(node)
    return targets

def controlling_upstream_nodes(points, receiver, depths, profile, target_nodes, minimum_slope):
    """Find edge endpoints controlling the highest bed at the supplied nodes."""
    donors = [[] for _ in points]
    for source, target in enumerate(receiver):
        if target >= 0:
            donors[target].append(source)
    edge_order = {int(source): edge for edge, source in enumerate(_i39_np.flatnonzero(receiver >= 0))}
    result = []
    for node in target_nodes:
        distance = {node: 0.0}
        pending = [node]
        for downstream in pending:
            for upstream in donors[downstream]:
                distance[upstream] = distance[downstream] + float(_i39_np.linalg.norm(points[upstream] - points[downstream]))
                pending.append(upstream)
        best = None
        for source in pending:
            if source not in edge_order:
                continue
            target = int(receiver[source])
            if target not in distance:
                continue
            edge = edge_order[source]
            start, end = profile[0][edge:edge + 2]
            knot_t = profile[1][start:end]
            source_height = profile[2][start:end]
            design_depth = (1.0 - knot_t) * depths[source] + knot_t * depths[target]
            remaining = distance[target] + (1.0 - knot_t) * _i39_np.linalg.norm(points[target] - points[source])
            upper = source_height - design_depth - minimum_slope * remaining
            knot = int(_i39_np.argmin(upper))
            if best is None or upper[knot] < best[0]:
                best = (float(upper[knot]), source, target, float(knot_t[knot]))
        if best is not None:
            _, source, target, knot_t = best
            for endpoint in [source, target] if knot_t <= 0.5 else [target, source]:
                if endpoint not in result:
                    result.append(endpoint)
    return result

def local_vertices(low, high, terrain, spacing):
    origin = _i39_np.array([terrain.x0_m, terrain.z0_m])
    domain_high = origin + _i39_np.array([(terrain.elevation_m.shape[1] - 1) * terrain.dx_m, (terrain.elevation_m.shape[0] - 1) * terrain.dz_m])
    first = _i39_np.floor((_i39_np.maximum(low, origin) - origin) / spacing).astype(int)
    last = _i39_np.ceil((_i39_np.minimum(high, domain_high) - origin) / spacing).astype(int)
    batches = []
    for offset in (0.0, 0.5):
        x = _i39_np.arange(first[0], last[0] + 1) + offset
        z = _i39_np.arange(first[1], last[1] + 1) + offset
        xx, zz = _i39_np.meshgrid(x, z)
        points = origin + _i39_np.column_stack((xx.ravel(), zz.ravel())) * spacing
        inside = _i39_np.all((points >= origin) & (points <= domain_high), axis=1)
        batches.append(points[inside])
    return _i39_np.concatenate(batches)

def necessary_bounds(points, receiver, widths, profile, terrain, ids, spacing=1.0, max_cut=4.0, bottom_slope=0.02, *, focus_nodes=None, hotspot_records=None):
    names = ('physical_half_bottom', 'bottom_guard_shell', 'bank')
    result = {kind: {name: dict(constraint_vertex_tests=0, violations=0, maximum_required_cut_m=0.0, worst=None) for name in names} for kind in ('edge_strip', 'node_cap')}
    edges = _i39_np.flatnonzero(receiver >= 0)
    incident = [[] for _ in points]
    incident_width = widths.copy()
    node_upper = _i39_np.full(len(points), _i39_np.inf)
    for edge, source in enumerate(edges):
        target = receiver[source]
        direction = points[target] - points[source]
        direction /= _i39_np.linalg.norm(direction)
        incident[source].append(direction)
        incident[target].append(-direction)
        width = max(widths[source], widths[target])
        incident_width[source] = max(incident_width[source], width)
        incident_width[target] = max(incident_width[target], width)
        start, end = profile[0][edge:edge + 2]
        node_upper[source] = min(node_upper[source], profile[3][start])
        node_upper[target] = min(node_upper[target], profile[3][end - 1])

    def record(kind, vertices, distances, upper, real_half, descriptor):
        heights = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)[0]
        guarded_half = real_half + _i39_np.sqrt(2.0) * spacing
        rise = _i39_np.minimum(distances, guarded_half) * bottom_slope + _i39_np.maximum(0.0, distances - guarded_half) / 2.0
        required = heights - upper - rise
        masks = (distances <= real_half, (distances > real_half) & (distances <= guarded_half), distances > guarded_half)
        for name, mask in zip(names, masks):
            values = required[mask]
            if not len(values):
                continue
            bucket = result[kind][name]
            bucket['constraint_vertex_tests'] += int(mask.sum())
            bucket['violations'] += int(_i39_np.count_nonzero(values > max_cut + 1e-08))
            worst_index = _i39_np.flatnonzero(mask)[_i39_np.argmax(values)]
            if hotspot_records is not None and values.max() > max_cut + 1e-08:
                hotspot_records.append(dict(descriptor, kind=kind, category=name, maximum_required_cut_m=float(values.max()), violating_tests=int(_i39_np.count_nonzero(values > max_cut + 1e-08))))
            if values.max() > bucket['maximum_required_cut_m']:
                bucket['maximum_required_cut_m'] = float(values.max())
                bucket['worst'] = dict(descriptor, vertex_xz_m=vertices[worst_index].tolist(), lateral_distance_m=float(distances[worst_index]), physical_half_bottom_m=float(real_half), source_height_m=float(heights[worst_index]), highest_center_bed_m=float(_i39_np.broadcast_to(upper, heights.shape)[worst_index]), transverse_rise_m=float(rise[worst_index]), necessary_cut_m=float(required[worst_index]), excess_over_four_m=float(required[worst_index] - max_cut))
    for edge, source in enumerate(edges):
        target = receiver[source]
        if focus_nodes is not None and source not in focus_nodes and (target not in focus_nodes):
            continue
        a, b = (points[source], points[target])
        delta = b - a
        real_half = max(widths[source], widths[target]) / 2.0
        radius = real_half + _i39_np.sqrt(2.0) * spacing + 2.0 * max_cut
        vertices = local_vertices(_i39_np.minimum(a, b) - radius, _i39_np.maximum(a, b) + radius, terrain, spacing)
        t = (vertices - a) @ delta / (delta @ delta)
        distance = _i39_np.linalg.norm(vertices - (a + t[:, None] * delta), axis=1)
        selected = (t >= 0.0) & (t <= 1.0) & (distance > 1e-10) & (distance <= radius)
        vertices, t, distance = (vertices[selected], t[selected], distance[selected])
        start, end = profile[0][edge:edge + 2]
        upper = _i39_np.interp(t, profile[1][start:end], profile[3][start:end])
        record('edge_strip', vertices, distance, upper, real_half, dict(edge_index=int(edge), source_node_index=int(source), target_node_index=int(target), source_node_cell_id=int(ids[source]), target_node_cell_id=int(ids[target]), source_xz_m=a.tolist(), target_xz_m=b.tolist()))
    for node, directions in enumerate(incident):
        if not directions:
            continue
        if focus_nodes is not None and node not in focus_nodes:
            continue
        real_half = incident_width[node] / 2.0
        radius = real_half + _i39_np.sqrt(2.0) * spacing + 2.0 * max_cut
        vertices = local_vertices(points[node] - radius, points[node] + radius, terrain, spacing)
        displacement = vertices - points[node]
        distance = _i39_np.linalg.norm(displacement, axis=1)
        selected = (distance > 1e-10) & (distance <= radius)
        selected &= _i39_np.all(displacement @ _i39_np.asarray(directions).T <= 1e-10, axis=1)
        record('node_cap', vertices[selected], distance[selected], node_upper[node], real_half, dict(node_index=node, node_cell_id=int(ids[node]), node_xz_m=points[node].tolist(), incident_edge_count=len(directions)))
    return result
DISPLACEMENT_COST_M_PER_M2 = 0.0002
SMOOTH_SOURCE_RISE_M = 0.25
METRIC_TERRAIN_CENTERLINE_ALGORITHM = 'anchored-staged-terrain-branch-certified-ordinary-sweep-analytic-turn-bound-v7'
SUPERSEDES_ALGORITHM = 'anchored-staged-terrain-branch-certified-ordinary-sweep-v6'
ANALYTIC_TURN_BOUND_DEGREES = {'ordinary': 90.0, 'junction': 90.0}
TURN_BOUND_POLICY = 'fixed analytic per-segment maximum turn bound; identical for every entry, so a saved reference path can never tighten or loosen the searched space'
ENTRY_POLICY = 'search always starts from the deterministic legacy eight-pass six-metre initialization; a supplied reference path is acceptance-alignment evidence only and is never a search start'

def initialize_centerline(original, receiver, terrain, *, validate, certify=None):
    """Deterministically reproduce the legacy eight-pass, six-metre initializer."""
    points = original.copy()
    anchors = _anchors(receiver)
    moving = _i38_np.flatnonzero(~anchors)
    incoming = _i38_np.full(len(receiver), -1, _i38_np.int64)
    for source, target in enumerate(receiver):
        if target >= 0:
            incoming[target] = source
    original_source = _metric_channel_geometry_sample(terrain.elevation_m, original, terrain)[0]
    if certify is not None:
        certify(points)
    for _ in range(8 if len(moving) else 0):
        energy = _turn_energy(points, receiver)
        chosen = False
        for strength in (0.35, 0.175, 0.0875, 0.04375, 0.021875):
            candidate = points.copy()
            candidate[moving] += strength * ((points[incoming[moving]] + points[receiver[moving]]) / 2.0 - points[moving])
            offset = _i38_np.linalg.norm(candidate - original, axis=1)
            excessive = offset > 6.0
            candidate[excessive] = original[excessive] + (candidate[excessive] - original[excessive]) * (6.0 / offset[excessive, None])
            sampled = _metric_channel_geometry_sample(terrain.elevation_m, candidate, terrain)[0]
            too_high = sampled - original_source > 0.5
            candidate[too_high] = points[too_high]
            try:
                validate(candidate)
                if certify is not None:
                    certify(candidate)
            except ValueError:
                continue
            if _turn_energy(candidate, receiver) < energy - 1e-12:
                points = candidate
                chosen = True
                break
        if not chosen:
            break
    return points

def path_turns(points, receiver):
    """Represent every donor -> node -> receiver turn, including all junction arms."""
    donors = _i38_np.flatnonzero(receiver >= 0)
    nodes = receiver[donors]
    continuing = receiver[nodes] >= 0
    donors, nodes = (donors[continuing], nodes[continuing])
    first = points[nodes] - points[donors]
    second = points[receiver[nodes]] - points[nodes]
    cosine = _i38_np.sum(first * second, axis=1) / (_i38_np.linalg.norm(first, axis=1) * _i38_np.linalg.norm(second, axis=1))
    angles = _i38_np.arccos(_i38_np.clip(cosine, -1.0, 1.0))
    degree = _i38_np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    return (angles, degree[nodes] > 1)

def turn_summary(points, receiver):
    angles, junction = path_turns(points, receiver)
    result = {}
    for name, mask in (('ordinary', ~junction), ('junction', junction)):
        degrees = _i38_np.degrees(angles[mask])
        result[name] = dict(count=len(degrees), maximum_degrees=float(degrees.max()) if len(degrees) else 0.0, p95_degrees=float(_i38_np.percentile(degrees, 95)) if len(degrees) else 0.0)
    result['all_donor_turn_energy'] = float(_i38_np.sum((1.0 - _i38_np.cos(angles)) ** 2))
    return result

def node_turns(points, receiver):
    """Per-node turn angles with donor, receiver and junction identity.

    Every donor -> node -> receiver turn is represented, including all junction arms.
    """
    anchors = _anchors(receiver)
    donors = _i38_np.flatnonzero(receiver >= 0)
    nodes = receiver[donors]
    continuing = receiver[nodes] >= 0
    donors, nodes = (donors[continuing], nodes[continuing])
    first = points[nodes] - points[donors]
    second = points[receiver[nodes]] - points[nodes]
    cosine = _i38_np.sum(first * second, axis=1) / (_i38_np.linalg.norm(first, axis=1) * _i38_np.linalg.norm(second, axis=1))
    angles = _i38_np.arccos(_i38_np.clip(cosine, -1.0, 1.0))
    degree = _i38_np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    return dict(node_indices=nodes, donor_indices=donors, angles=angles, junction=degree[nodes] > 1, movable=~anchors[nodes])

def movable_turn_maxima(points, receiver):
    """Maximum single-segment turn per category over nodes the search may actually move."""
    detail = node_turns(points, receiver)
    degrees = _i38_np.degrees(detail['angles'])
    movable, junction = (detail['movable'], detail['junction'])
    result = {}
    for kind, mask in (('ordinary', movable & ~junction), ('junction', movable & junction)):
        result[kind] = float(degrees[mask].max()) if mask.any() else 0.0
    return result

def turn_ceiling(baseline, receiver):
    """Fixed, entry-independent turn ceiling for a search started from `baseline`.

    The declared analytic bound is a *cap on strictness*, not a one-shot hard wall: the
    effective ceiling is the looser of the fixed analytic bound and the baseline's own
    movable maximum. Two properties follow, and both are the point of the whole change:

    1. the ceiling never depends on any caller-supplied saved reference path, so two entries
       carrying different references search exactly the same feasible set;
    2. a deterministic initializer that is still dirty keeps enough headroom for the search to
       descend monotonically instead of being blocked before its first step.

    p95 needs no separate number: p95 <= maximum over the same node set, so bounding the
    maximum bounds p95. This deliberately removes the four-number global mutex.
    """
    observed = movable_turn_maxima(baseline, receiver)
    return {kind: max(ANALYTIC_TURN_BOUND_DEGREES[kind], observed[kind]) for kind in observed}

def enforce_turn_ceiling(points, receiver, ceiling):
    """Reject a candidate whose movable turn exceeds a ceiling from `turn_ceiling`."""
    observed = movable_turn_maxima(points, receiver)
    for kind, limit in ceiling.items():
        if observed[kind] > limit + 1e-07:
            raise ValueError(kind + ' maximum_degrees exceeds analytic turn ceiling')
    return observed

def anchor_turn_exemption(points, receiver):
    """Diagnostics for turns the search cannot control because the node is anchored."""
    detail = node_turns(points, receiver)
    degrees = _i38_np.degrees(detail['angles'])
    exempt = ~detail['movable']
    return dict(exempt_turn_count=int(exempt.sum()), exempt_maximum_degrees=float(degrees[exempt].max()) if exempt.any() else 0.0, exempt_node_indices=sorted((int(node) for node in _i38_np.unique(detail['node_indices'][exempt]))))

def shape_centerline(points, receiver, terrain, *, iterations, corridor_m, validate, certify=None, reference_points=None):
    """Search with cheap geometric checks; certify only final bounded candidates."""
    started = _i38_time.perf_counter()
    original = points.copy()
    anchors = _anchors(receiver)
    moving = _i38_np.flatnonzero(~anchors)
    certificate_calls = 0

    def run_certificate(candidate):
        nonlocal certificate_calls
        certificate_calls += 1
        certify(candidate)
    reference_turn = None
    if reference_points is not None:
        if reference_points.shape != original.shape or not _i38_np.isfinite(reference_points).all() or (not _i38_np.array_equal(reference_points[anchors], original[anchors])):
            raise ValueError('reference centerline anchor or node mismatch')
        reference_turn = turn_summary(reference_points, receiver)
    if iterations:
        points = initialize_centerline(original, receiver, terrain, validate=validate, certify=run_certificate if certify is not None else None)
        offset = _i38_np.linalg.norm(points - original, axis=1)
        excessive = offset > corridor_m
        points[excessive] = original[excessive] + (points[excessive] - original[excessive]) * (corridor_m / offset[excessive, None])
    else:
        points = original.copy()
    original_turn = turn_summary(original, receiver)
    baseline = points.copy()
    baseline_turn = turn_summary(baseline, receiver)
    original_source = _metric_channel_geometry_sample(terrain.elevation_m, original, terrain)[0]
    baseline_source = _metric_channel_geometry_sample(terrain.elevation_m, baseline, terrain)[0]
    reference_source = baseline_source if reference_points is None else _metric_channel_geometry_sample(terrain.elevation_m, reference_points, terrain)[0]
    turn_ceiling_degrees = turn_ceiling(baseline, receiver)
    declared_ceiling_degrees = dict(ANALYTIC_TURN_BOUND_DEGREES)
    incoming = _i38_np.full(len(receiver), -1, _i38_np.int64)
    for source, target in enumerate(receiver):
        if target >= 0:
            incoming[target] = source
    refused = []
    accepted = {'terrain': 0, 'smooth': 0, 'local': 0}
    smooth_trials = 0
    smooth_trial_limit = 8 * len(moving)
    smooth_node_acceptances = {}
    smooth_node_visits = {}
    certified_terrain = baseline.copy()
    salvage_certificates = 0
    salvage_certificate_limit = 128
    salvage_accepted_nodes = []
    salvage_unattempted_nodes = []
    salvage_rejected_nodes = []
    initial_certificate_batches = 0
    if certify is not None:
        run_certificate(baseline)

    def admissible(candidate, source_ceiling):
        if _i38_np.any(_i38_np.linalg.norm(candidate - original, axis=1) > corridor_m + 1e-08):
            raise ValueError('original source corridor offset')
        sampled, cells = _metric_channel_geometry_sample(terrain.elevation_m, candidate, terrain)
        if _i38_np.any(sampled > source_ceiling + 1e-09) or _i38_np.any(~terrain.valid_mask.ravel()[cells]):
            raise ValueError('source elevation or validity corridor')
        enforce_turn_ceiling(candidate, receiver, turn_ceiling_degrees)
        turns = turn_summary(candidate, receiver)
        validate(candidate)
        return (sampled, turns)
    baseline_movable = movable_turn_maxima(baseline, receiver)
    baseline_exceeds_declared_bound = sorted((kind for kind, limit in ANALYTIC_TURN_BOUND_DEGREES.items() if baseline_movable[kind] > limit + 1e-07))
    refused.append(dict(phase='baseline_turn_state', reason='baseline movable turns measured', baseline_movable_maxima_degrees=baseline_movable, exceeds_declared_analytic_bound=baseline_exceeds_declared_bound, effective_ceiling_degrees=dict(turn_ceiling_degrees)))
    low = _i38_np.array([terrain.x0_m, terrain.z0_m])
    high = low + _i38_np.array([(terrain.elevation_m.shape[1] - 1) * terrain.dx_m, (terrain.elevation_m.shape[0] - 1) * terrain.dz_m])
    for phase in ('terrain', 'smooth'):
        if phase == 'terrain':
            ceiling = original_source + 0.5
        else:
            if certify is not None and (not _i38_np.array_equal(points, baseline)):
                try:
                    run_certificate(points)
                except ValueError as error:
                    refused.append(dict(phase='terrain_certificate', reason=str(error)))
                    points = baseline.copy()
            certified_terrain = points.copy()
            floor_source = _metric_channel_geometry_sample(terrain.elevation_m, points, terrain)[0]
            ceiling = _i38_np.minimum(original_source + 0.5, floor_source + SMOOTH_SOURCE_RISE_M)
            first = points[moving] - points[incoming[moving]]
            second = points[receiver[moving]] - points[moving]
            cosine = _i38_np.sum(first * second, axis=1) / (_i38_np.linalg.norm(first, axis=1) * _i38_np.linalg.norm(second, axis=1))
            angles = _i38_np.arccos(_i38_np.clip(cosine, -1.0, 1.0))
            smooth_order = sorted(range(len(moving)), key=lambda index: (-angles[index], int(moving[index])))
            smooth_batch_size = max(1, (len(moving) + max(1, iterations) - 1) // max(1, iterations))
        for iteration in range(iterations if len(moving) else 0):
            current_source = _metric_channel_geometry_sample(terrain.elevation_m, points, terrain)[0]
            current_turn = turn_summary(points, receiver)['all_donor_turn_energy']
            if phase == 'smooth':
                first_index = iteration * smooth_batch_size
                for index in smooth_order[first_index:first_index + smooth_batch_size]:
                    node = int(moving[index])
                    smooth_node_visits[node] = smooth_node_visits.get(node, 0) + 1
                    neighbors = [int(incoming[node]), int(receiver[node])]
                    groups = [[node], [node] + [neighbor for neighbor in neighbors if not anchors[neighbor]]]
                    node_chosen = False
                    for group in groups:
                        group = _i38_np.array(group)
                        target = (points[incoming[group]] + points[receiver[group]]) / 2.0
                        for strength in (0.5, 0.25, 0.125, 0.0625):
                            if smooth_trials >= smooth_trial_limit:
                                break
                            smooth_trials += 1
                            trial = points.copy()
                            trial[group] += strength * (target - points[group])
                            try:
                                sampled, turns = admissible(trial, ceiling)
                            except ValueError as error:
                                refused.append(dict(phase=phase, iteration=iteration, strength=strength, local=True, node_indices=group.tolist(), reason=str(error)))
                                continue
                            if turns['all_donor_turn_energy'] >= current_turn - 1e-10:
                                continue
                            points = trial
                            current_turn = turns['all_donor_turn_energy']
                            accepted['smooth'] += 1
                            accepted['local'] += 1
                            smooth_node_acceptances[node] = smooth_node_acceptances.get(node, 0) + 1
                            node_chosen = True
                            break
                        if node_chosen or smooth_trials >= smooth_trial_limit:
                            break
                continue
            tangent = points[receiver[moving]] - points[incoming[moving]]
            normal = _i38_np.column_stack((-tangent[:, 1], tangent[:, 0])) / _i38_np.linalg.norm(tangent, axis=1)[:, None]
            offsets = _i38_np.linspace(-corridor_m, corridor_m, 25)
            samples = points[moving, None, :] + offsets[None, :, None] * normal[:, None, :]
            bounded = _i38_np.clip(samples, low, high)
            heights, cells = _metric_channel_geometry_sample(terrain.elevation_m, bounded.reshape(-1, 2), terrain)
            heights = heights.reshape(len(moving), -1)
            displacement = _i38_np.linalg.norm(samples - original[moving, None, :], axis=2)
            valid = _i38_np.all((samples >= low) & (samples <= high), axis=2)
            valid &= terrain.valid_mask.ravel()[cells].reshape(len(moving), -1)
            valid &= (displacement <= corridor_m + 1e-09) & (heights <= ceiling[moving, None])
            costs = heights + DISPLACEMENT_COST_M_PER_M2 * displacement ** 2
            costs[~valid] = _i38_np.inf
            target = bounded[_i38_np.arange(len(moving)), _i38_np.argmin(costs, axis=1)]
            chosen = False
            for strength in (0.5, 0.25, 0.125, 0.0625):
                candidate = points.copy()
                candidate[moving] += strength * (target - points[moving])
                offset = _i38_np.linalg.norm(candidate - original, axis=1)
                excessive = offset > corridor_m
                candidate[excessive] = original[excessive] + (candidate[excessive] - original[excessive]) * (corridor_m / offset[excessive, None])
                trials = [candidate]
                groups = [_i38_np.array([moving[(iteration * 16 + index) % len(moving)]]) for index in range(min(16, len(moving)))]
                for group in groups:
                    local = points.copy()
                    local[group] = candidate[group]
                    trials.append(local)
                for number, trial in enumerate(trials):
                    try:
                        sampled, turns = admissible(trial, ceiling)
                    except ValueError as error:
                        refused.append(dict(phase=phase, iteration=iteration, strength=strength, local=number > 0, reason=str(error)))
                        continue
                    if float(_i38_np.mean(current_source - sampled)) <= 1e-10:
                        continue
                    points = trial
                    accepted[phase] += 1
                    accepted['local'] += int(number > 0)
                    chosen = True
                    break
                if chosen:
                    break
            if not chosen:
                break
    search_seconds = _i38_time.perf_counter() - started
    if certify is not None and (not _i38_np.array_equal(points, baseline)):
        final = points.copy()
        try:
            admissible(final, ceiling)
            run_certificate(final)
        except ValueError as error:
            refused.append(dict(phase='final_certificate', reason=str(error)))
            points = certified_terrain.copy()
            changed = _i38_np.linalg.norm(final - certified_terrain, axis=1) > 1e-12
            pending = []
            visited = _i38_np.zeros(len(points), bool)
            for start in moving:
                if not anchors[incoming[start]]:
                    continue
                chain = []
                node = int(start)
                while not anchors[node] and (not visited[node]):
                    visited[node] = True
                    if changed[node]:
                        chain.append(node)
                    node = int(receiver[node])
                pending.extend((chain[index:index + 64] for index in range(0, len(chain), 64)))
            for node in moving[~visited[moving] & changed[moving]]:
                pending.append([int(node)])
            if len(pending) > 64:
                packed = [[] for _ in range(64)]
                for index, group in enumerate(pending):
                    packed[index % 64].extend(group)
                pending = packed
            initial_certificate_batches = len(pending)
            pending = _i38_deque(pending)
            while pending:
                group = pending.popleft()
                if salvage_certificates >= salvage_certificate_limit:
                    salvage_unattempted_nodes.extend(group)
                    continue
                trial = points.copy()
                trial[group] = final[group]
                try:
                    admissible(trial, ceiling)
                    salvage_certificates += 1
                    run_certificate(trial)
                except ValueError as error:
                    refused.append(dict(phase='local_final_certificate', node_indices=group, reason=str(error)))
                    if len(group) > 1:
                        middle = len(group) // 2
                        pending.extend((group[:middle], group[middle:]))
                    else:
                        salvage_rejected_nodes.extend(group)
                    continue
                points = trial
                salvage_accepted_nodes.extend(group)
    final_turn = turn_summary(points, receiver)
    policy = dict(algorithm=METRIC_TERRAIN_CENTERLINE_ALGORITHM, supersedes_algorithm=SUPERSEDES_ALGORITHM, corridor_m=corridor_m, maximum_original_source_rise_m=0.5, smoothing_source_rise_budget_m=SMOOTH_SOURCE_RISE_M, valley_displacement_cost_m_per_m2=DISPLACEMENT_COST_M_PER_M2, coefficient_status='uncalibrated bounded engineering settings', objective_policy='terrain projection then all-donor dimensionless turn energy; ordinary and junction maximum turn cannot exceed the fixed entry-independent ceiling derived from the declared analytic bound', turn_bound_policy=TURN_BOUND_POLICY, declared_analytic_turn_bound_degrees=declared_ceiling_degrees, effective_turn_ceiling_degrees=dict(turn_ceiling_degrees), baseline_movable_turn_maxima_degrees=baseline_movable, baseline_exceeds_declared_analytic_bound=baseline_exceeds_declared_bound, entry_policy=ENTRY_POLICY, mean_source_height_policy='observed diagnostic only; smoothing acceptance uses local source ceilings, geometry, turn limits and complete physical profile certification', reference_policy='saved reference actual nodes recorded as acceptance-alignment diagnostics only; never a search start' if reference_points is not None else 'no saved reference supplied; deterministic legacy eight-pass six-metre initialization', original_turns=original_turn, baseline_turns=baseline_turn, final_turns=final_turn, accepted_steps=accepted, refused_steps=refused, smooth_candidate_trials=smooth_trials, maximum_smooth_candidate_trials=smooth_trial_limit, smooth_coverage_policy='one curvature-ordered finite sweep of every movable ordinary node when iterations > 0', smooth_eligible_node_count=len(moving), smooth_visited_node_indices=sorted(smooth_node_visits), smooth_complete_ordinary_coverage=len(smooth_node_visits) == len(moving), smooth_accepted_node_indices=sorted(smooth_node_acceptances), continuous_certificate_calls=certificate_calls, final_certificate_recovery_policy='certified terrain base; at most 64 initial branch batches; FIFO binary splitting and 128 complete profile calls; preserve accepted batches', local_final_certificate_calls=salvage_certificates, maximum_local_final_certificate_calls=salvage_certificate_limit, initial_local_final_certificate_batches=initial_certificate_batches, local_final_accepted_node_indices=sorted(salvage_accepted_nodes), local_final_unattempted_node_indices=sorted(salvage_unattempted_nodes), local_final_rejected_node_indices=sorted(salvage_rejected_nodes), path_search_seconds=search_seconds, total_path_seconds=_i38_time.perf_counter() - started, original_mean_source_height_m=float(original_source.mean()), initialized_baseline_mean_source_height_m=float(baseline_source.mean()), reference_mean_source_height_m=float(reference_source.mean()), final_mean_source_height_m=float(_metric_channel_geometry_sample(terrain.elevation_m, points, terrain)[0].mean()), anchors='source, confluence and terminal nodes fixed exactly', reference_mean_source_height_semantics='mean sampled source height of the caller-supplied saved reference path when one was supplied; otherwise the deterministic initialized search baseline (no saved reference)')
    if reference_turn is not None:
        policy['reference_turns'] = reference_turn
        policy['reference_turn_regression'] = sorted((kind + ' ' + metric for kind in ('ordinary', 'junction') for metric in ('maximum_degrees', 'p95_degrees') if final_turn[kind][metric] > reference_turn[kind][metric] + 1e-07))
    policy['turn_bound_satisfied'] = all((final_turn[kind]['maximum_degrees'] <= limit + 1e-07 for kind, limit in ANALYTIC_TURN_BOUND_DEGREES.items()))
    policy['anchor_turn_exemption'] = anchor_turn_exemption(points, receiver)
    return (points, policy)

def search_local_candidates(points, receiver, contributing_edges, windows, *, gate, evaluate, turn_score, max_candidates=32, max_refinements=4):
    """evaluate returns status clear/unknown/infeasible and optional extra_cut.

    Contributing edges are ordered by dual contribution by the caller. Windows
    include the failed window and every previously clear window. Only candidates
    clear in every supplied window can be selected. Counts include gate refusals.
    """
    if not windows:
        raise ValueError('at least one failed window is required')
    degree = _i32_np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    anchors = (degree != 1) | (receiver < 0)
    records, feasible = ([], [])
    groups_seen = set()
    baseline_extra = None
    window_evaluations = 0
    refine_attempts = 0
    if windows:
        baseline = evaluate(points, windows[0])
        window_evaluations += 1
        baseline_extra = baseline.get('extra_cut') if baseline['status'] == 'infeasible' else None

    def attempt(node, group, offset, stage):
        nonlocal window_evaluations
        if len(records) >= max_candidates:
            return None
        donor = int(_i32_np.flatnonzero(receiver == node)[0])
        tangent = points[receiver[node]] - points[donor]
        normal = _i32_np.array([-tangent[1], tangent[0]]) / _i32_np.linalg.norm(tangent)
        candidate = points.copy()
        candidate[group] += offset * normal
        record = dict(node=node, group=group, offset_m=offset, stage=stage, index=len(records), window_results=[])
        records.append(record)
        try:
            gate(candidate)
        except ValueError as error:
            record.update(status='gate_refused', reason=str(error))
            return record
        record['status'] = 'clear'
        for window in windows:
            result = evaluate(candidate, window)
            window_evaluations += 1
            if result['status'] not in ('clear', 'unknown', 'infeasible'):
                raise ValueError('unsupported local evaluation status')
            record['window_results'].append(dict(window=window, **result))
            if result['status'] != 'clear':
                record['status'] = result['status']
                break
        if record['status'] == 'clear':
            record['turn_score'] = turn_score(candidate)
            feasible.append((record['turn_score'], record['index'], candidate))
        return record
    for source, target in contributing_edges:
        movable = [int(node) for node in (source, target) if not anchors[node]]
        if not movable:
            continue
        root = movable[0]
        donor = int(_i32_np.flatnonzero(receiver == root)[0])
        adjacent = [node for node in (donor, int(receiver[root])) if not anchors[node]]
        groups = [(node, [node]) for node in movable]
        groups.append((root, list(dict.fromkeys([root] + adjacent))))
        root_records = []
        for node, group in groups[:3]:
            key = (node, tuple(group))
            if key in groups_seen:
                continue
            groups_seen.add(key)
            for offset in (-0.5, 0.5, -2.0, 2.0, -4.0, 4.0):
                record = attempt(node, group, offset, 'coarse')
                if record is not None:
                    root_records.append(record)
        improving = [record for record in root_records if record['status'] == 'infeasible' and record['window_results'] and (record['window_results'][0]['status'] == 'infeasible') and (record['window_results'][0].get('extra_cut') is not None) and (baseline_extra is not None) and (record['window_results'][0]['extra_cut'] < baseline_extra)]
        if improving:
            best = min(improving, key=lambda record: record['window_results'][0]['extra_cut'])
            for delta in (-0.5, 0.5, -0.25, 0.25):
                if refine_attempts >= max_refinements:
                    break
                record = attempt(best['node'], best['group'], best['offset_m'] + delta, 'refine')
                if record is not None:
                    refine_attempts += 1
        if len(records) >= max_candidates:
            break
    selected = min(feasible, key=lambda item: (item[0], item[1])) if feasible else None
    return (selected[2] if selected else points.copy(), dict(candidate_limit=max_candidates, attempted_candidates=len(records), records=records, selected_index=selected[1] if selected else None, status='local_windows_clear_needs_full_bed' if selected else 'no_clear_candidate', maximum_window_evaluations=1 + max_candidates * len(windows), window_evaluations=window_evaluations, refine_attempts=refine_attempts))

def worst_windows(evaluation, side_m=512.0):
    ranked = []
    for kind in ('edge_strip', 'node_cap'):
        for category in ('physical_half_bottom', 'bottom_guard_shell', 'bank'):
            worst = evaluation['bounds'][kind][category]['worst']
            if worst is None:
                continue
            ranked.append((worst['necessary_cut_m'], kind, category, worst))
    windows = []
    for required, kind, category, worst in sorted(ranked, key=lambda item: (-item[0], item[1], item[2])):
        center = _i32_np.asarray(worst['vertex_xz_m'])
        if all((_i32_np.linalg.norm(center - window['center_xz_m']) > side_m / 2.0 for window in windows)):
            windows.append(dict(center_xz_m=center.tolist(), side_m=side_m, origin_kind=kind, origin_category=category, necessary_cut_m=required))
        if len(windows) == 6:
            break
    return windows

def repair_local_conflicts(terrain, points, receiver, width, depth, profile, ids, *, validate, certify, assess, spacing, max_cut, bottom_slope, minimum_slope, max_candidates=32, max_local_solves=None, budget_evaluate=None):
    """Return a locally checked route requiring complete original-bed validation.

    assess receives the exact physical configuration as keyword arguments and
    reports clear/infeasible/unknown, solver_calls, and optional dual route roots.
    """
    if max_local_solves is None:
        max_local_solves = 2 * (max_candidates + 1) * 6
    if budget_evaluate is None:
        budget_evaluate = lambda candidate, candidate_profile: evaluate_necessary_budget(candidate, receiver, width, candidate_profile, terrain, ids, spacing, max_cut, bottom_slope)
    current = points.copy()
    current_profile = profile
    history, records = ([], [])
    solves, refinements = (0, 0)
    cached = {}

    def window_key(window):
        return (tuple(window['center_xz_m']), window['side_m'])

    def evaluation(candidate, window):
        nonlocal solves
        key = (candidate.tobytes(), window_key(window))
        if key in cached:
            return cached[key]
        if solves + 2 > max_local_solves:
            return dict(status='unknown', reason='component local solver budget exhausted')
        candidate_profile = certify(candidate)
        result = assess(candidate, receiver, width, depth, candidate_profile, terrain, window, spacing=spacing, max_cut=max_cut, bottom_slope=bottom_slope, minimum_slope=minimum_slope)
        solves += result.get('solver_calls', 1)
        cached[key] = result
        return result

    def gate(candidate):
        validate(candidate)
        candidate_profile = certify(candidate)
        budget = budget_evaluate(candidate, candidate_profile)
        if sum(budget['counts']):
            raise ValueError('global necessary budget conflicts')
    windows = worst_windows(budget_evaluate(current, current_profile))
    while True:
        assessments = [evaluation(current, window) for window in windows]
        history.append(dict(windows=windows, assessments=assessments))
        failed = next((index for index, result in enumerate(assessments) if result['status'] == 'infeasible'), None)
        unknown = any((result['status'] == 'unknown' for result in assessments))
        if failed is None:
            status = 'unknown_needs_full_bed' if unknown or not windows else 'local_windows_clear_needs_full_bed'
            break
        if len(records) >= max_candidates:
            status = 'local_conflicts_remain'
            break
        contributing = assessments[failed].get('contributing_edges', [])
        if not contributing:
            status = 'local_conflict_without_dual_route_witness'
            break
        ordered_windows = [windows[failed]] + [window for index, window in enumerate(windows) if index != failed]
        candidate, policy = search_local_candidates(current, receiver, contributing, ordered_windows, gate=gate, evaluate=evaluation, turn_score=lambda route: turn_summary(route, receiver)['all_donor_turn_energy'], max_candidates=max_candidates - len(records), max_refinements=4 - refinements)
        records.extend(policy['records'])
        refinements += policy['refine_attempts']
        if policy['selected_index'] is None:
            status = 'local_conflicts_remain'
            break
        current, current_profile = (candidate, certify(candidate))
    return (current, current_profile, dict(status=status, candidate_limit=max_candidates, attempted_candidates=len(records), refine_attempts=refinements, local_solver_calls=solves, maximum_local_solver_calls=max_local_solves, history=history, records=records, window_policy='freeze initial spatially separated necessary-worst windows; recheck all after every selected candidate', maximum_windows=6, interpretation='Local windows are original-row relaxations; full bed and cold audit remain required'))

def derived_seed(world_seed, purpose):
    return int.from_bytes(_i35_hashlib.sha256(f'{int(world_seed)}:{purpose}'.encode('ascii')).digest()[:4], 'little')

def _station(path):
    return _i35_np.r_[0.0, _i35_np.cumsum(_i35_np.linalg.norm(_i35_np.diff(path, axis=0), axis=1))]

def _metric_natural_construction_sample(path, stations):
    s = _station(path)
    return _i35_np.column_stack([_i35_np.interp(stations, s, path[:, axis]) for axis in range(2)])

def flowing_path(start, direction, length, slope, rng, count=1201, *, bend_amplitude=310.0, initial_lateral_slope=0.0):
    """Monotone downstream progression with a prescribed initial lateral slope."""
    direction = _i35_np.asarray(direction, float)
    direction = direction / _i35_np.linalg.norm(direction)
    normal = _i35_np.array([-direction[1], direction[0]])
    distance = _i35_np.linspace(0.0, length, count)
    knots = _i35_np.r_[0.0, _i35_np.cumsum(rng.uniform(0.75, 1.3, 7))]
    knots *= length / knots[-1]
    offsets = rng.uniform(-bend_amplitude, bend_amplitude, len(knots))
    offsets[0] = 0.0
    bends = _i35_CubicSpline(knots, offsets, bc_type=((1, 0.0), (1, 0.0)))(distance)
    turn_length = rng.uniform(650.0, 1000.0)
    ramp = _i35_np.clip(distance / 900.0, 0.0, 1.0)
    ramp = ramp * ramp * (3.0 - 2.0 * ramp)
    cross = slope * (distance - turn_length * (1.0 - _i35_np.exp(-distance / turn_length))) + bends * ramp + initial_lateral_slope * distance * _i35_np.exp(-distance / 600.0)
    return start + distance[:, None] * direction + cross[:, None] * normal

def natural_distributary_geometry(trunk, world_seed):
    rng = _i35_np.random.default_rng(derived_seed(world_seed, 'delta/branch-geometry/v1'))
    trunk = _i35_np.asarray(trunk, float)
    direction = trunk[-1] - trunk[-8]
    extension = flowing_path(trunk[-1], direction, 1050.0, rng.uniform(-0.03, 0.03), rng, len(trunk), bend_amplitude=8.0)
    extended = _i35_np.vstack([trunk, extension[1:]])
    extended = _metric_natural_construction_sample(extended, _i35_np.linspace(0.0, _station(extended)[-1], len(trunk)))
    s = _station(extended)
    fractions = _i35_np.array([0.32, 0.76, 1.0, 0.22]) + rng.uniform(-0.025, 0.025, 4)
    fractions[2] = 1.0
    slopes = _i35_np.array([-0.63, -0.19, 0.22, 0.71]) * rng.uniform(0.92, 1.08, 4)
    paths = []
    direction = direction / _i35_np.linalg.norm(direction)
    normal = _i35_np.array([-direction[1], direction[0]])
    anchor = extended[0]
    trunk_u, trunk_v = ((extended - anchor) @ direction, (extended - anchor) @ normal)
    baseline = _i35_CubicSpline(trunk_u, trunk_v, bc_type='natural')
    phase = rng.uniform(0.0, 2.0 * _i35_np.pi)

    def centerline(u):
        beyond = _i35_np.maximum(u - trunk_u[-1], 0.0)
        taper = 1.0 - _i35_np.exp(-(beyond / 600.0) ** 2)
        bend = 210.0 * _i35_np.sin(beyond / 620.0 + phase) * taper
        return baseline(_i35_np.minimum(u, trunk_u[-1])) + baseline(trunk_u[-1], 1) * beyond + bend
    for split, slope in zip(fractions * s[-1], slopes):
        start = _metric_natural_construction_sample(extended, [split])[0]
        distance = _i35_np.linspace(0.0, rng.uniform(6500.0, 7000.0), 1201)
        u = (start - anchor) @ direction + distance
        separation = slope * distance ** 2 / (distance + 800.0)
        knots = _i35_np.linspace(0.0, distance[-1], 9)
        factors = _i35_CubicSpline(knots, rng.uniform(-0.12, 0.12, len(knots)), bc_type='natural')(distance)
        v = centerline(u) + separation * (1.0 + factors)
        branch = anchor + u[:, None] * direction + v[:, None] * normal
        branch[0] = start
        paths.append(branch)
    return (extended, _i35_np.asarray(paths), fractions * s[-1])

def natural_secondary(parent, marine, origin, spacing, world_seed):
    rng = _i35_np.random.default_rng(derived_seed(world_seed, 'delta/secondary-geometry/v1'))
    s = _station(parent)
    cells = _i35_np.floor((parent - origin) / spacing + 0.5).astype(int)
    inside = (cells[:, 0] >= 0) & (cells[:, 0] < marine.shape[1]) & (cells[:, 1] >= 0) & (cells[:, 1] < marine.shape[0])
    hits = _i35_np.flatnonzero(inside & marine[cells[:, 1].clip(0, marine.shape[0] - 1), cells[:, 0].clip(0, marine.shape[1] - 1)])
    if not len(hits):
        return (None, {'reason': 'no_open_marine_entry'})
    split_s = float(s[hits[0]] * rng.uniform(0.38, 0.47))
    start = _metric_natural_construction_sample(parent, [split_s])[0]
    direction = parent[20] - parent[0]
    direction /= _i35_np.linalg.norm(direction)
    normal = _i35_np.array([-direction[1], direction[0]])
    pu, pv = ((parent - parent[0]) @ direction, (parent - parent[0]) @ normal)
    baseline = _i35_CubicSpline(pu, pv, bc_type='natural')
    distance = _i35_np.linspace(0.0, min(5300.0, pu[-1] - (start - parent[0]) @ direction), len(parent))
    u = (start - parent[0]) @ direction + distance
    clearance = 0.5 * (170.0 + 102.0) + 2.0 * spacing
    landward_run = max(float(s[hits[0]]) - split_s, spacing)
    separation_slope = 2.0 * clearance * (landward_run + 650.0) / landward_run ** 2
    v = baseline(u) - separation_slope * distance ** 2 / (distance + 650.0)
    child = parent[0] + u[:, None] * direction + v[:, None] * normal
    child[0] = start
    return (child, {'reason': 'selected', 'parent_split_station_m': split_s, 'parent_first_marine_station_m': float(s[hits[0]]), 'required_distinct_channel_clearance_m': clearance})

def channel_organized_relief(prebed, fan, paths, origin, spacing, world_seed):
    """Curved interdistributary lobes constrained by adjacent channel corridors."""
    rng = _i35_np.random.default_rng(derived_seed(world_seed, 'delta/island-relief/v1'))
    zz, xx = _i35_np.indices(prebed.shape)
    points = _i35_np.stack([origin[0] + xx * spacing, origin[1] + zz * spacing], axis=-1)
    relief = _i35_np.zeros_like(prebed)
    bodies = []
    direction, normal = (fan['direction_xz'], fan['normal_xz'])
    anchor = fan['apex_xz_m']
    local = points - anchor
    along, across = (local @ direction, local @ normal)
    coordinates = [((path - anchor) @ direction, (path - anchor) @ normal) for path in paths]
    coordinates.sort(key=lambda item: item[1][-1])
    for index, (left, right) in enumerate(zip(coordinates[:-1], coordinates[1:])):
        start = max(left[0][0], right[0][0]) + rng.uniform(180.0, 330.0)
        end = min(left[0][-1], right[0][-1], rng.uniform(4200.0, 5400.0))
        t = _i35_np.clip((along - start) / (end - start), 0.0, 1.0)
        low = _i35_np.interp(along, left[0], left[1])
        high = _i35_np.interp(along, right[0], right[1])
        center_fraction = rng.uniform(0.42, 0.58)
        center = low + (high - low) * center_fraction
        longitudinal = _i35_np.maximum(4.0 * t * (1.0 - t), 0.0)
        half_width = _i35_np.maximum((high - low) * rng.uniform(0.3, 0.4) - 70.0, 1.0)
        half_width *= _i35_np.sqrt(longitudinal)
        offset = across - center
        asymmetry = 1.0 + 0.16 * _i35_np.tanh(offset / 200.0) * (2.0 * t - 1.0)
        transverse = _i35_np.maximum(1.0 - (offset / (_i35_np.maximum(half_width, 1.0) * asymmetry)) ** 2, 0.0)
        height = rng.uniform(2.2, 3.5)
        body = longitudinal * transverse ** 2
        apron = longitudinal * _i35_np.maximum(1.0 - (offset / _i35_np.maximum(half_width * 1.65, 1.0)) ** 2, 0.0) ** 2
        relief += height * body + 0.55 * apron
        bodies.append(dict(sorted_corridor_positions=[index, index + 1], start_downstream_m=start, end_downstream_m=end, center_fraction=center_fraction, height_m=height, boundary='interpolated adjacent channel centerlines with channel clearance and asymmetric shallow apron'))
    forward = fan['u_m'] - fan['parameters']['apex_u_m']

    def smooth(v):
        v = _i35_np.clip(v, 0.0, 1.0)
        return v * v * (3.0 - 2.0 * v)
    envelope = fan['weight'] * smooth((forward - 650.0) / 1000.0) * (1.0 - smooth((_i35_np.abs(prebed) - 3.0) / 5.0))
    return (relief * envelope, bodies)

def construct_mouth_transitions(prebed, marine, candidates, paths, junctions, widths, incoming_bed, origin, spacing, transition_length_m=650.0):
    """Explicit initial nearshore excavation grading channel beds into the sea."""
    bed = prebed.copy()
    zz, xx = _i35_np.indices(bed.shape)
    points = _i35_np.stack([origin[0] + xx * spacing, origin[1] + zz * spacing], axis=-1)
    support = _i35_np.zeros_like(marine)
    for candidate, path, junction, width in zip(candidates, paths, junctions, widths):
        station = _station(candidate)
        segments = _i35_np.diff(candidate, axis=0)
        fraction = _i35_np.clip(_i35_np.sum((path[-1] - candidate[:-1]) * segments, axis=1) / _i35_np.sum(segments * segments, axis=1), 0.0, 1.0)
        projected = candidate[:-1] + fraction[:, None] * segments
        index = _i35_np.argmin(_i35_np.linalg.norm(projected - path[-1], axis=1))
        coast_s = float(station[index] + fraction[index] * _i35_np.linalg.norm(segments[index]))
        samples = _i35_np.linspace(max(0.0, coast_s - 2.0 * spacing), min(station[-1], coast_s + transition_length_m), 301)
        line = _metric_natural_construction_sample(candidate, samples)
        distance, nearest = _i35_cKDTree(line).query(points.reshape(-1, 2), workers=1)
        distance, nearest = (distance.reshape(bed.shape), nearest.reshape(bed.shape))
        tangent_start, tangent_end = (line[1] - line[0], line[-1] - line[-2])
        active = marine & ((points - line[0]) @ tangent_start >= 0.0) & ((points - line[-1]) @ tangent_end <= 0.0)
        lateral = _i35_np.clip((1.0 - distance / (0.5 * width)) / 0.4, 0.0, 1.0)
        offshore = _i35_np.clip((samples[nearest] - coast_s) / transition_length_m, 0.0, 1.0)
        blend = offshore * offshore * (3.0 - 2.0 * offshore)
        coast_bed = float(incoming_bed) - 0.00038 * (junction + _station(path)[-1])
        target = coast_bed * (1.0 - blend) + prebed * blend
        proposal = bed + lateral * active * (_i35_np.minimum(target, bed) - bed)
        support |= proposal < bed
        bed = proposal
    return (bed, support)
METRIC_NETWORK_GEOMETRY_SCHEMA = 'terragenesis-network-geometry-plan-v1'
METRIC_NETWORK_GEOMETRY_ALGORITHM = 'native-area-edge-disjoint-patches-v1'

@_i36_dataclass(frozen=True)
class NetworkGeometryConfig:
    min_contributing_area_m2: float = 1000000.0
    max_patch_edges: int = 6
    design_runoff_mm_h: float = 1.0
    minimum_width_m: float = 6.0
    width_coefficient_m_per_sqrt_cms: float = 4.0
    minimum_depth_m: float = 0.25
    depth_coefficient_m_per_cuberoot_cms: float = 0.2

    def __post_init__(self):
        for name in ('min_contributing_area_m2', 'design_runoff_mm_h', 'minimum_width_m', 'width_coefficient_m_per_sqrt_cms', 'minimum_depth_m', 'depth_coefficient_m_per_cuberoot_cms'):
            value = getattr(self, name)
            if isinstance(value, (bool, _i36_np.bool_)) or not _i36_np.isscalar(value) or (not _i36_np.isfinite(value)) or (value <= 0.0):
                raise ValueError(name + ' must be finite positive')
        if type(self.max_patch_edges) is not int or not 1 <= self.max_patch_edges <= 32:
            raise ValueError('max_patch_edges outside bounded patch budget')

def _catalogue(terrain, graph, config):
    from terrain_pipeline.common_infra import RoutingGraph as _i36_RoutingGraph
    from terrain_pipeline.common_infra import TerrainGrid as _i36_TerrainGrid
    if not isinstance(terrain, _i36_TerrainGrid) or not isinstance(graph, _i36_RoutingGraph):
        raise ValueError('TerrainGrid and RoutingGraph required')
    if graph.terrain_identity_sha256 != terrain.identity_sha256:
        raise ValueError('graph terrain identity must match the original source')
    if graph.valid_mask.shape != terrain.valid_mask.shape or not _i36_np.array_equal(graph.valid_mask, terrain.valid_mask):
        raise ValueError('graph must cover the exact original terrain validity')
    if 'irregular' in graph.policy:
        from terrain_pipeline.drainage import diagnostic_mesh
        from terrain_pipeline.drainage import receiver_edges_valid
        mesh = diagnostic_mesh(terrain)
        if not receiver_edges_valid(graph.receiver, mesh):
            raise ValueError('receiver is not an edge of the declared metric irregular graph')
        sources = _i36_np.flatnonzero(graph.receiver >= 0)
        targets = graph.receiver[sources]
        lengths = _i36_np.hypot(mesh.node_x_m[targets] - mesh.node_x_m[sources], mesh.node_z_m[targets] - mesh.node_z_m[sources])
        if not _i36_np.allclose(graph.edge_length_m[sources], lengths, rtol=1e-12, atol=1e-12):
            raise ValueError('graph lengths disagree with continuous metric node positions')
    rec = graph.receiver
    area = _i36_np.zeros(rec.size, _i36_np.float64)
    area[terrain.valid_mask.ravel()] = terrain.cell_area_m2
    owner = _i36_np.full(rec.size, -1, _i36_np.int64)
    for cell in graph.order_downstream_first:
        target = rec[cell]
        owner[cell] = cell if target < 0 else owner[target]
    for cell in graph.order_downstream_first[::-1]:
        if rec[cell] >= 0:
            area[rec[cell]] += area[cell]
    selected = (area >= config.min_contributing_area_m2) & (rec >= 0)
    ids = _i36_np.flatnonzero(selected)
    donors = _i36_np.bincount(rec[ids], minlength=rec.size)
    patch_owner = _i36_np.full(rec.size, -1, _i36_np.int64)
    patch_edges = []
    starts = ids[donors[ids] != 1]
    for first in starts:
        cell = int(first)
        while selected[cell] and patch_owner[cell] < 0:
            edges = []
            while selected[cell] and patch_owner[cell] < 0:
                edges.append(cell)
                patch_owner[cell] = len(patch_edges)
                target = int(rec[cell])
                if len(edges) == config.max_patch_edges or not selected[target] or donors[target] != 1:
                    break
                cell = target
            patch_edges.append(edges)
            cell = target
    if _i36_np.any(patch_owner[ids] < 0):
        raise ValueError('selected source graph is not an acyclic downstream catalogue')
    offsets = _i36_np.r_[0, _i36_np.cumsum([len(edges) for edges in patch_edges])].astype(_i36_np.int64)
    edge_ids = _i36_np.concatenate([_i36_np.asarray(edges, _i36_np.int64) for edges in patch_edges]) if patch_edges else _i36_np.empty(0, _i36_np.int64)
    design_q = area * config.design_runoff_mm_h / 1000.0 / 3600.0
    widths = _i36_np.maximum(config.minimum_width_m, config.width_coefficient_m_per_sqrt_cms * _i36_np.sqrt(design_q))
    depths = _i36_np.maximum(config.minimum_depth_m, config.depth_coefficient_m_per_cuberoot_cms * _i36_np.cbrt(design_q))
    return dict(contributing_area_m2=area, terminal_owner=owner, selected_edge_source_ids=ids, selected_edge_target_ids=rec[ids], patch_offsets=offsets, patch_edge_source_ids=edge_ids, edge_patch_id=patch_owner[ids], selected_design_q_m3_s=design_q[ids], selected_width_m=widths[ids], selected_depth_m=depths[ids])

def build_network_geometry_plan(terrain, graph, config=None):
    from terrain_pipeline.common_infra import identity as _i36_identity
    from terrain_pipeline.common_infra import readonly as _i36_readonly
    config = config or NetworkGeometryConfig()
    if not isinstance(config, NetworkGeometryConfig):
        raise ValueError('NetworkGeometryConfig required')
    catalogue = _catalogue(terrain, graph, config)
    arrays = {'source_elevation_m': terrain.elevation_m, 'source_valid_mask': terrain.valid_mask, **{'graph_' + name: getattr(graph, name) for name in ('receiver', 'order_downstream_first', 'valid_mask', 'edge_length_m', 'edge_slope', 'outlet_kind', 'lake_id')}, **catalogue}
    metadata = dict(schema=METRIC_NETWORK_GEOMETRY_SCHEMA, algorithm=METRIC_NETWORK_GEOMETRY_ALGORITHM, config=_i36_asdict(config), terrain_metadata={key: getattr(terrain, key) for key in terrain.__dataclass_fields__ if key not in ('elevation_m', 'valid_mask')}, terrain_identity_sha256=terrain.identity_sha256, graph_metadata={'terrain_identity_sha256': graph.terrain_identity_sha256, 'boundary_identity_sha256': graph.boundary_identity_sha256, 'policy': graph.policy}, graph_identity_sha256=graph.identity_sha256, selection='original_graph_edges_above_native_contributing_area_threshold', section_policy='explicit_uncalibrated_monotone_design_discharge_scenario', source_assignment='native_local_sources_require_upstream_aggregation_once', status='complete_selection_catalogue_geometry_pending', geometry_verified=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False)
    arrays = {key: _i36_readonly(value) for key, value in arrays.items()}
    result = dict(arrays=arrays, metadata=metadata, identity_sha256=_i36_identity(arrays, metadata))
    validate_network_geometry_plan(result)
    return result

def validate_network_geometry_plan(bundle):
    from terrain_pipeline.common_infra import identity as _i36_identity
    from terrain_pipeline.common_infra import RoutingGraph as _i36_RoutingGraph
    from terrain_pipeline.common_infra import TerrainGrid as _i36_TerrainGrid
    a, m = (bundle['arrays'], bundle['metadata'])
    if m.get('schema') != METRIC_NETWORK_GEOMETRY_SCHEMA or m.get('algorithm') != METRIC_NETWORK_GEOMETRY_ALGORITHM or _i36_identity(a, m) != bundle['identity_sha256']:
        raise ValueError('network plan schema or identity mismatch')
    terrain = _i36_TerrainGrid(a['source_elevation_m'], a['source_valid_mask'], **m['terrain_metadata'])
    graph = _i36_RoutingGraph(**{name: a['graph_' + name] for name in ('receiver', 'order_downstream_first', 'valid_mask', 'edge_length_m', 'edge_slope', 'outlet_kind', 'lake_id')}, **m['graph_metadata'])
    if terrain.identity_sha256 != m['terrain_identity_sha256'] or graph.identity_sha256 != m['graph_identity_sha256']:
        raise ValueError('network source identities mismatch')
    expected = _catalogue(terrain, graph, NetworkGeometryConfig(**m['config']))
    for key, value in expected.items():
        if not _i36_np.array_equal(a[key], value):
            raise ValueError('network catalogue mismatch: ' + key)
    ids = a['selected_edge_source_ids']
    if not _i36_np.array_equal(_i36_np.sort(a['patch_edge_source_ids']), ids):
        raise ValueError('patches duplicate or omit selected edges')
    if any((m.get(key) is not False for key in ('geometry_verified', 'hydraulic_ready', 'natural_outlet_verified', 'publishable'))):
        raise ValueError('catalogue cannot certify geometry or hydraulics')
    return True

def save_network_geometry_plan(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _i36_save_bundle
    return _i36_save_bundle(path, bundle, validator=validate_network_geometry_plan)

def load_network_geometry_plan(path, *, expected_sha256):
    from terrain_pipeline.common_infra import load_bundle as _i36_load_bundle
    return _i36_load_bundle(path, expected_sha256=expected_sha256, validator=validate_network_geometry_plan, max_bytes=512 * 1024 * 1024)

def _piece_geometry(record):
    if not isinstance(record, dict):
        raise ValueError('record must be a dict')
    identity = record.get('identity')
    parent_detail_identity = record.get('parent_detail_identity')
    frozen_plan_identity = record.get('frozen_plan_identity')
    if not isinstance(identity, str) or not identity:
        raise ValueError('identity must be non-empty str')
    if not isinstance(parent_detail_identity, str) or not parent_detail_identity:
        raise ValueError('parent_detail_identity must be non-empty str')
    if not isinstance(frozen_plan_identity, str) or not frozen_plan_identity:
        raise ValueError('frozen_plan_identity must be non-empty str')
    source_path = record.get('source_path')
    archive_sha256 = record.get('archive_sha256')
    if not isinstance(source_path, str) or not source_path:
        raise ValueError('source_path must be non-empty str')
    if not isinstance(archive_sha256, str) or not archive_sha256:
        raise ValueError('archive_sha256 must be non-empty str')
    spacing_m = record.get('fine_spacing_m')
    if isinstance(spacing_m, (bool, _i37_np.bool_)) or not isinstance(spacing_m, (int, float, _i37_np.integer, _i37_np.floating)):
        raise ValueError('fine_spacing_m must be a positive finite float')
    spacing_m = float(spacing_m)
    if not _i37_np.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError('fine_spacing_m must be a positive finite float')
    origin = record.get('mesh_origin_xz_m')
    origin = _i37_np.asarray(origin, dtype=_i37_np.float64)
    if origin.shape != (2,) or not _i37_np.all(_i37_np.isfinite(origin)):
        raise ValueError('mesh_origin_xz_m must be finite float[2]')
    if not isinstance(record.get('shared_sections'), list):
        raise ValueError('shared_sections must be a list')
    shared_sections = record['shared_sections']
    arrays = record.get('arrays')
    if not isinstance(arrays, dict):
        raise ValueError('arrays must be a dict')
    cells = arrays.get('cells')
    if cells is None:
        raise ValueError('cells missing')
    if not isinstance(cells, _i37_np.ndarray) or cells.dtype.kind not in 'iu':
        raise ValueError('cells must be integer ndarray')
    if cells.ndim != 2 or cells.shape[1] != 2 or cells.shape[0] <= 0:
        raise ValueError('cells must be integer[n,2], n>0')
    cells = cells.astype(_i37_np.int64, copy=False)
    if _i37_np.unique(cells, axis=0).shape[0] != cells.shape[0]:
        raise ValueError('cells must be unique')
    n = cells.shape[0]
    vertices = arrays.get('vertices_xz_m')
    if vertices is None:
        raise ValueError('vertices_xz_m missing')
    if not isinstance(vertices, _i37_np.ndarray):
        raise ValueError('vertices_xz_m must be ndarray')
    vertices = vertices.astype(_i37_np.float64, copy=False)
    if vertices.ndim != 2 or vertices.shape[1] != 2:
        raise ValueError('vertices_xz_m must be float[v,2]')
    v = vertices.shape[0]
    if v <= 0:
        raise ValueError('vertices_xz_m must have v>0')
    if not _i37_np.all(_i37_np.isfinite(vertices)):
        raise ValueError('vertices_xz_m must be finite')
    triangles = arrays.get('triangles')
    if triangles is None:
        raise ValueError('triangles missing')
    if not isinstance(triangles, _i37_np.ndarray) or triangles.dtype.kind not in 'iu':
        raise ValueError('triangles must be integer ndarray')
    if triangles.shape != (4 * n, 3):
        raise ValueError('triangles must be integer[4n,3]')
    triangles = triangles.astype(_i37_np.int64, copy=False)
    if triangles.min() < 0 or triangles.max() >= v:
        raise ValueError('triangles indices out of bounds')
    bed = arrays.get('bed_elevation_m')
    if bed is None:
        raise ValueError('bed_elevation_m missing')
    if not isinstance(bed, _i37_np.ndarray):
        raise ValueError('bed_elevation_m must be ndarray')
    bed = bed.astype(_i37_np.float64, copy=False)
    if bed.shape != (v,):
        raise ValueError('bed_elevation_m must be float[v]')
    if not _i37_np.all(_i37_np.isfinite(bed)):
        raise ValueError('bed_elevation_m must be finite')
    node_xz = arrays.get('node_xz_m')
    if node_xz is None:
        raise ValueError('node_xz_m missing')
    if not isinstance(node_xz, _i37_np.ndarray):
        raise ValueError('node_xz_m must be ndarray')
    node_xz = node_xz.astype(_i37_np.float64, copy=False)
    if node_xz.shape != (2, 2):
        raise ValueError('node_xz_m must be float[2,2]')
    if not _i37_np.all(_i37_np.isfinite(node_xz)):
        raise ValueError('node_xz_m must be finite')
    node_source_edges = arrays.get('node_source_edges')
    if node_source_edges is None:
        raise ValueError('node_source_edges missing')
    if not isinstance(node_source_edges, _i37_np.ndarray) or node_source_edges.dtype.kind not in 'iu':
        raise ValueError('node_source_edges must be integer ndarray')
    if node_source_edges.shape != (2, 2):
        raise ValueError('node_source_edges must be integer[2,2]')
    node_source_edges = node_source_edges.astype(_i37_np.int64, copy=False)
    if not (isinstance(node_source_edges, _i37_np.ndarray) and node_source_edges.shape == (2, 2) and (node_source_edges.dtype == _i37_np.int64)):
        raise ValueError('node_source_edges must be an int64 np.ndarray of shape (2, 2)')
    if not _i37_np.array_equal(node_source_edges[0], node_source_edges[1]):
        raise ValueError('node_source_edges rows must be equal')
    if node_source_edges[0, 0] == node_source_edges[0, 1]:
        raise ValueError('node_source_edges first-row ids must differ')
    if not _i37_np.all(node_source_edges >= 0):
        raise ValueError('all node_source_edges ids must be >= 0')
    node_edge_fractions = arrays.get('node_edge_fractions')
    if node_edge_fractions is None:
        raise ValueError('node_edge_fractions missing')
    if not isinstance(node_edge_fractions, _i37_np.ndarray):
        raise ValueError('node_edge_fractions must be ndarray')
    node_edge_fractions = node_edge_fractions.astype(_i37_np.float64, copy=False)
    if node_edge_fractions.shape != (2,):
        raise ValueError('node_edge_fractions must be float[2]')
    if not _i37_np.all(_i37_np.isfinite(node_edge_fractions)):
        raise ValueError('node_edge_fractions must be finite')
    lo, hi = (float(node_edge_fractions[0]), float(node_edge_fractions[1]))
    if not 0.0 <= lo < hi <= 1.0:
        raise ValueError('node_edge_fractions must satisfy 0<=lo<hi<=1')
    receiver = arrays.get('receiver')
    if receiver is None:
        raise ValueError('receiver missing')
    if not isinstance(receiver, _i37_np.ndarray) or receiver.dtype.kind not in 'iu':
        raise ValueError('receiver must be integer ndarray')
    if receiver.shape != (2,):
        raise ValueError('receiver must be integer[2]')
    receiver = receiver.astype(_i37_np.int64, copy=False)
    if not (receiver[0] == 1 and receiver[1] == -1):
        raise ValueError('receiver must be [1,-1]')
    if node_xz[0, 0] == node_xz[1, 0] and node_xz[0, 1] == node_xz[1, 1]:
        raise ValueError('node_xz_m points must be distinct')
    bbox_min = vertices.min(axis=0)
    bbox_max = vertices.max(axis=0)
    return {'identity': identity, 'parent_detail_identity': parent_detail_identity, 'frozen_plan_identity': frozen_plan_identity, 'source_path': source_path, 'archive_sha256': archive_sha256, 'spacing_m': spacing_m, 'origin_xz_m': origin, 'cells': cells, 'vertices_xz_m': vertices, 'triangles': triangles, 'bed_elevation_m': bed, 'node_xz_m': node_xz, 'node_source_edges': node_source_edges, 'node_edge_fractions': node_edge_fractions, 'receiver': receiver, 'shared_sections': shared_sections, 'lookup': {(int(cell[0]), int(cell[1])): row_index for row_index, cell in enumerate(cells)}, 'bbox_min_xz_m': bbox_min, 'bbox_max_xz_m': bbox_max}

def _sample_piece_points(piece, points):
    pts = _i37_np.asarray(points, dtype=_i37_np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError('points must have shape (N, 2)')
    if not _i37_np.all(_i37_np.isfinite(pts)):
        raise ValueError('points must be finite')
    N = pts.shape[0]
    if N == 0:
        return (_i37_np.empty(0, dtype=_i37_np.float64), _i37_np.empty(0, dtype=bool))
    bmin = _i37_np.asarray(piece['bbox_min_xz_m'], dtype=_i37_np.float64)
    bmax = _i37_np.asarray(piece['bbox_max_xz_m'], dtype=_i37_np.float64)
    maxabs = float(_i37_np.max(_i37_np.abs(_i37_np.concatenate([bmin, bmax]))))
    pad = 8.0 * _i37_np.spacing(maxabs) if maxabs > 0 else 0.0
    lo = bmin - pad
    hi = bmax + pad
    inside = _i37_np.all(pts >= lo, axis=1) & _i37_np.all(pts <= hi, axis=1)
    lookup = piece['lookup']
    origin = _i37_np.asarray(piece['origin_xz_m'], dtype=_i37_np.float64)
    spacing = piece['spacing_m']
    cell_rows = []
    supported_idx = []
    for i in _i37_np.nonzero(inside)[0]:
        try:
            key = _cell_at_point(pts[i], lookup, origin, spacing)
        except ValueError as exc:
            if str(exc) == 'centerline leaves sparse mesh support':
                continue
            raise
        row = lookup.get(key)
        if row is None:
            continue
        supported_idx.append(int(i))
        cell_rows.append(int(row))
    values = _i37_np.full(N, _i37_np.nan, dtype=_i37_np.float64)
    mask = _i37_np.zeros(N, dtype=bool)
    if not supported_idx:
        return (values, mask)
    sup = _i37_np.asarray(supported_idx, dtype=_i37_np.int64)
    rows = _i37_np.asarray(cell_rows, dtype=_i37_np.int64)
    ids, weights = _barycentric_batch(pts[sup], rows, piece['vertices_xz_m'], piece['triangles'])
    bed = piece['bed_elevation_m']
    sampled = _i37_np.sum(bed[ids] * weights, axis=1)
    values[sup] = sampled
    mask[sup] = True
    return (values, mask)

def _ordered_pieces(pieces):
    if not isinstance(pieces, (list, tuple)) or not pieces:
        raise ValueError('pieces must be a non-empty list or tuple')
    normalized = [_piece_geometry(p) for p in pieces]
    keyed = [(tuple((float(v) for v in n['node_edge_fractions'])), i, n) for i, n in enumerate(normalized)]
    keyed.sort(key=lambda t: (t[0][0], t[2]['identity']))
    ids = [n['identity'] for _, _, n in keyed]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate piece identity')
    parent = keyed[0][2]['parent_detail_identity']
    frozen = keyed[0][2]['frozen_plan_identity']
    all_nodes = _i37_np.concatenate([n['node_xz_m'] for _, _, n in keyed], axis=0)
    max_abs = float(_i37_np.max(_i37_np.abs(all_nodes))) if all_nodes.size else 0.0
    world_scale = max(1e-09, 8.0 * float(_i37_np.spacing(max(1.0, max_abs))))
    edge_start = _i37_np.asarray(keyed[0][2]['node_xz_m'][0], dtype=float).copy()
    edge_end = _i37_np.asarray(keyed[-1][2]['node_xz_m'][1], dtype=float).copy()
    delta = edge_end - edge_start
    edge_length = float(_i37_np.hypot(delta[0], delta[1]))
    if not (_i37_np.isfinite(edge_length) and edge_length > 0.0):
        raise ValueError('global edge must have positive finite length')
    frac_tol = world_scale / edge_length
    if frac_tol <= 0.0 or not _i37_np.isfinite(frac_tol):
        raise ValueError('invalid fraction tolerance')
    if keyed[0][0][0] > frac_tol:
        raise ValueError('fraction gap or overlap')
    if abs(keyed[-1][0][1] - 1.0) > frac_tol:
        raise ValueError('fraction gap or overlap')
    source_edge = keyed[0][2]['node_source_edges'][0]
    if _i37_np.any(source_edge[0] == source_edge[1]):
        raise ValueError('source edge node IDs must be distinct')
    ordered = []
    prev_hi = None
    for fracs, _, n in keyed:
        if n['parent_detail_identity'] != parent:
            raise ValueError('parent_detail_identity mismatch')
        if n['frozen_plan_identity'] != frozen:
            raise ValueError('frozen_plan_identity mismatch')
        se = n['node_source_edges']
        if not (_i37_np.array_equal(se[0], source_edge) and _i37_np.array_equal(se[1], source_edge)):
            raise ValueError('source edge mismatch')
        lo, hi = fracs
        if lo > hi:
            raise ValueError('invalid fraction order')
        if prev_hi is not None:
            if abs(lo - prev_hi) > frac_tol:
                raise ValueError('fraction gap or overlap')
        prev_hi = hi
        pts = _i37_np.asarray(n['node_xz_m'], dtype=float)
        expected = edge_start[None, :] + _i37_np.asarray([lo, hi])[:, None] * delta[None, :]
        if not _i37_np.all(_i37_np.abs(pts - expected) <= world_scale):
            raise ValueError('piece endpoint not on global edge')
        ordered.append(n)
    for i in range(len(ordered) - 1):
        a = _i37_np.asarray(ordered[i]['node_xz_m'][1], dtype=float)
        b = _i37_np.asarray(ordered[i + 1]['node_xz_m'][0], dtype=float)
        if not _i37_np.all(_i37_np.abs(a - b) <= world_scale):
            raise ValueError('fraction gap or overlap')
    return (ordered, edge_start, edge_end, frac_tol)

def _audit_shared_sections(ordered, edge_start, edge_end, fraction_tol):
    import numpy as np
    if not ordered or len(ordered) < 2:
        return ([], 0.0)

    def _metric_tol_for(coord):
        scale = max(1.0, float(np.max(np.abs(coord))) if np.size(coord) else 1.0)
        return max(1e-09, 8.0 * np.spacing(scale))
    sections = []
    max_abs_bed_diff = 0.0
    for i in range(len(ordered) - 1):
        left = ordered[i]
        right = ordered[i + 1]
        shared_pos = np.asarray(left['node_xz_m'][-1], dtype=float)
        tol_pos = _metric_tol_for(shared_pos)

        def _select_section(piece):
            parent = piece['parent_detail_identity']
            candidates = []
            for sec in piece.get('shared_sections', []) or []:
                if sec.get('parent_detail_identity') != parent:
                    continue
                p = np.asarray(sec.get('position_xz_m'), dtype=float)
                if p.shape != (2,) or not np.all(np.isfinite(p)):
                    continue
                if np.all(np.abs(p - shared_pos) <= tol_pos):
                    candidates.append(sec)
            if len(candidates) != 1:
                raise ValueError('expected exactly one matching shared section per piece')
            return candidates[0]
        left_sec = _select_section(left)
        right_sec = _select_section(right)
        for piece, sec in ((left, left_sec), (right, right_sec)):
            parent = piece['parent_detail_identity']
            if sec.get('parent_detail_identity') != parent:
                raise ValueError('shared section parent identity mismatch')
            p = np.asarray(sec['position_xz_m'], dtype=float)
            n = np.asarray(sec['normal_xz'], dtype=float)
            if p.shape != (2,) or not np.all(np.isfinite(p)):
                raise ValueError('invalid section position')
            if n.shape != (2,) or not np.all(np.isfinite(n)):
                raise ValueError('invalid section normal')
            n_norm = float(np.linalg.norm(n))
            if abs(n_norm - 1.0) > 1e-06:
                raise ValueError('section normal not unit length')
            r = float(sec['radius_m'])
            if not np.isfinite(r) or r <= 0.0:
                raise ValueError('invalid section radius')
            edge_vec = np.asarray(edge_end, dtype=float) - np.asarray(edge_start, dtype=float)
            e_norm = float(np.linalg.norm(edge_vec))
            if e_norm == 0.0:
                raise ValueError('degenerate edge for perpendicularity check')
            e_hat = edge_vec / e_norm
            if abs(float(np.dot(n, e_hat))) > 1e-06:
                raise ValueError('section normal not perpendicular to edge')
            offs = np.asarray(sec['offsets_m'], dtype=float)
            if offs.ndim != 1 or offs.size < 2:
                raise ValueError('invalid section offsets')
            if not np.all(np.isfinite(offs)):
                raise ValueError('non-finite section offsets')
            if np.any(np.diff(offs) <= 0.0):
                raise ValueError('section offsets must be strictly ascending')
            if offs[0] < -r - tol_pos or offs[-1] > r + tol_pos:
                raise ValueError('section offsets out of radius bounds')
            near_center = np.any(np.abs(offs) <= tol_pos)
            near_neg = np.any(np.abs(offs + r) <= tol_pos)
            near_pos = np.any(np.abs(offs - r) <= tol_pos)
            if not (near_center and near_neg and near_pos):
                raise ValueError('section offsets missing required endpoints/center')
        lp = np.asarray(left_sec['position_xz_m'], dtype=float)
        rp = np.asarray(right_sec['position_xz_m'], dtype=float)
        if not np.all(np.abs(lp - rp) <= tol_pos):
            raise ValueError('shared section positions differ')
        ln = np.asarray(left_sec['normal_xz'], dtype=float)
        rn = np.asarray(right_sec['normal_xz'], dtype=float)
        if np.any(np.abs(ln - rn) > 1e-06):
            raise ValueError('shared section normals differ')
        lr = float(left_sec['radius_m'])
        rr = float(right_sec['radius_m'])
        if abs(lr - rr) > tol_pos:
            raise ValueError('shared section radii differ')
        loff = np.asarray(left_sec['offsets_m'], dtype=float)
        roff = np.asarray(right_sec['offsets_m'], dtype=float)
        union = np.union1d(loff, roff)
        must = [-lr, 0.0, lr]
        for req in must:
            if not np.any(np.abs(union - req) <= tol_pos):
                union = np.concatenate([union, [req]])
        union = np.unique(union)
        if not (union[0] >= -lr - tol_pos and union[-1] <= lr + tol_pos):
            raise ValueError('union offsets out of radius bounds')
        normal = ln
        position = lp
        points = position[None, :] + union[:, None] * normal[None, :]
        left_vals, left_mask = _sample_piece_points(left, points)
        right_vals, right_mask = _sample_piece_points(right, points)
        if not np.all(left_mask) or not np.all(right_mask):
            raise ValueError('shared section offsets fall outside both pieces')
        left_bed = np.asarray(left_vals)
        right_bed = np.asarray(right_vals)
        if left_bed.shape != right_bed.shape:
            raise ValueError('shared section bed shapes differ')
        diff = np.abs(left_bed - right_bed)
        finite = np.isfinite(diff)
        if not np.all(finite):
            raise ValueError('shared section beds differ beyond tolerance')
        local_max = float(np.max(diff))
        if local_max > 1e-06:
            raise ValueError('shared section beds differ beyond tolerance')
        max_abs_bed_diff = max(max_abs_bed_diff, local_max)
        frac = float(left['node_edge_fractions'][-1])
        rfrac = float(right['node_edge_fractions'][0])
        if abs(frac - rfrac) > fraction_tol:
            raise ValueError('shared section endpoint fractions differ')
        sections.append({'left_index': i, 'right_index': i + 1, 'fraction': frac, 'position_xz_m': np.array(position, dtype=float, copy=True), 'normal_xz': np.array(normal, dtype=float, copy=True), 'radius_m': float(lr)})
    return (sections, max_abs_bed_diff)

def sample_saved_bed_grid(pieces, *, origin_xz_m, shape_zx, spacing_m):
    import numpy as np
    if isinstance(shape_zx, (list, tuple)):
        shape = list(shape_zx)
    elif isinstance(shape_zx, np.ndarray):
        shape = shape_zx.tolist()
    else:
        raise TypeError('shape_zx must be list, tuple, or ndarray')
    if len(shape) != 2:
        raise ValueError('shape_zx must have length 2')
    for v in shape:
        if isinstance(v, bool) or not isinstance(v, (int, np.integer)):
            raise TypeError('shape_zx entries must be integers')
        if v <= 0:
            raise ValueError('shape_zx entries must be positive')
    nz, nx = (int(shape[0]), int(shape[1]))
    if nz * nx > 65536:
        raise ValueError('shape_zx product must be <= 65536')
    if isinstance(origin_xz_m, (list, tuple)):
        origin = list(origin_xz_m)
    elif isinstance(origin_xz_m, np.ndarray):
        origin = origin_xz_m.tolist()
    else:
        raise TypeError('origin_xz_m must be list, tuple, or ndarray')
    if len(origin) != 2:
        raise ValueError('origin_xz_m must have length 2')
    for v in origin:
        if isinstance(v, bool) or not isinstance(v, (int, float, np.integer, np.floating)):
            raise TypeError('origin entries must be numeric')
        if not np.isfinite(float(v)):
            raise ValueError('origin entries must be finite')
    ox, oz = (float(origin[0]), float(origin[1]))
    if isinstance(spacing_m, bool):
        raise TypeError('spacing_m must not be bool')
    if isinstance(spacing_m, str):
        raise TypeError('spacing_m must not be string')
    if not isinstance(spacing_m, (int, float, np.integer, np.floating)):
        raise TypeError('spacing_m must be numeric')
    spacing = float(spacing_m)
    if not np.isfinite(spacing) or spacing <= 0.0:
        raise ValueError('spacing_m must be positive finite')
    zs = oz + np.arange(nz, dtype=np.float64) * spacing
    xs = ox + np.arange(nx, dtype=np.float64) * spacing
    zz, xx = np.meshgrid(zs, xs, indexing='ij')
    points = np.stack([xx.ravel(), zz.ravel()], axis=1)
    if not np.all(np.isfinite(points)):
        raise ValueError('computed target coordinates must be finite')
    N = points.shape[0]
    ordered, edge_start, edge_end, fraction_tol = _ordered_pieces(pieces)
    sections, max_shared_diff = _audit_shared_sections(ordered, edge_start, edge_end, fraction_tol)
    bed = np.full(N, np.nan, dtype=np.float64)
    mask = np.zeros(N, dtype=bool)
    owner = np.full(N, -1, dtype=np.int64)
    edge_delta = edge_end - edge_start
    denom = float(np.dot(edge_delta, edge_delta))
    if denom == 0.0:
        raise ValueError('degenerate global edge')
    frac = (points - edge_start) @ edge_delta / denom
    at_lo = np.abs(frac - 0.0) <= fraction_tol
    at_hi = np.abs(frac - 1.0) <= fraction_tol
    valid_frac_range = (frac > 0.0) & (frac < 1.0)
    endpoint_ok = (at_lo | at_hi) & np.isfinite(frac)
    usable = valid_frac_range | endpoint_ok
    n_pieces = len(ordered)
    for i, piece in enumerate(ordered):
        lo, hi = piece['node_edge_fractions']
        lo = float(lo)
        hi = float(hi)
        is_first = i == 0
        is_last = i == n_pieces - 1
        lo_lo = lo - (fraction_tol if is_first else 0.0)
        hi_hi = hi + (fraction_tol if is_last else 0.0)
        if is_last:
            sel = (frac >= lo_lo) & (frac <= hi_hi) & usable
        else:
            sel = (frac >= lo_lo) & (frac < hi) & usable
        idx = np.nonzero(sel)[0]
        if idx.size == 0:
            continue
        vals, supported = _sample_piece_points(piece, points[idx])
        vals = np.asarray(vals, dtype=np.float64)
        supported = np.asarray(supported, dtype=bool)
        write = idx[supported]
        bed[write] = vals[supported]
        mask[write] = True
        owner[write] = i
    metric_tol = max(1e-09, 8.0 * np.spacing(max(1.0, float(np.max(np.abs(edge_start))))))
    max_shared_bed_diff = float(max_shared_diff)
    for sec in sections:
        sec_frac = float(sec['fraction'])
        sec_pos = np.asarray(sec['position_xz_m'], dtype=np.float64)
        sec_nrm = np.asarray(sec['normal_xz'], dtype=np.float64)
        radius = float(sec['radius_m'])
        li = int(sec['left_index'])
        ri = int(sec['right_index'])
        on_line = np.abs(frac - sec_frac) <= fraction_tol
        if not np.any(on_line):
            continue
        cand = np.nonzero(on_line)[0]
        bed[cand] = np.nan
        mask[cand] = False
        owner[cand] = -1
        p = points[cand]
        perp = np.abs((p - sec_pos) @ sec_nrm)
        along = np.abs((p - sec_pos) @ edge_delta / np.sqrt(denom))
        rows = cand[(perp <= radius + metric_tol) & (along <= metric_tol)]
        if rows.size == 0:
            continue
        left_vals, left_ok = _sample_piece_points(ordered[li], points[rows])
        right_vals, right_ok = _sample_piece_points(ordered[ri], points[rows])
        left_ok = np.asarray(left_ok, dtype=bool)
        right_ok = np.asarray(right_ok, dtype=bool)
        both = left_ok & right_ok
        if not np.any(both):
            continue
        lv = np.asarray(left_vals, dtype=np.float64)[both]
        rv = np.asarray(right_vals, dtype=np.float64)[both]
        if not np.all(np.isfinite(lv)) or not np.all(np.isfinite(rv)):
            raise ValueError('shared-section sampled bed must be finite')
        diff = np.abs(lv - rv)
        if np.any(diff > 1e-06):
            raise ValueError('shared section bed mismatch exceeds 1e-6')
        d = float(np.max(diff))
        if d > max_shared_bed_diff:
            max_shared_bed_diff = d
        write_rows = rows[both]
        bed[write_rows] = rv
        mask[write_rows] = True
        owner[write_rows] = ri
    canonical_pieces = []
    for i, piece in enumerate(ordered):
        canonical_pieces.append({'identity': piece['identity'], 'parent_detail_identity': piece['parent_detail_identity'], 'frozen_plan_identity': piece['frozen_plan_identity'], 'source_path': piece['source_path'], 'archive_sha256': piece['archive_sha256'], 'spacing_m': float(piece['spacing_m']), 'origin_xz_m': [float(piece['origin_xz_m'][0]), float(piece['origin_xz_m'][1])], 'node_edge_fractions': [float(piece['node_edge_fractions'][0]), float(piece['node_edge_fractions'][1])], 'node_xz_m': [[float(piece['node_xz_m'][0][0]), float(piece['node_xz_m'][0][1])], [float(piece['node_xz_m'][1][0]), float(piece['node_xz_m'][1][1])]], 'source_spacing_m': float(piece['spacing_m']), 'fraction_interval': [float(piece['node_edge_fractions'][0]), float(piece['node_edge_fractions'][1])]})
    provenance = {'schema': 'saved-bed-grid-v1', 'canonical_pieces': canonical_pieces, 'source_path': [p['source_path'] for p in ordered], 'archive_hash': [p['archive_sha256'] for p in ordered], 'parent_ids': [p['parent_detail_identity'] for p in ordered], 'source_spacing_m': [float(p['spacing_m']) for p in ordered], 'fraction_interval': [[float(p['node_edge_fractions'][0]), float(p['node_edge_fractions'][1])] for p in ordered], 'target_params': {'origin_xz_m': [ox, oz], 'shape_zx': [nz, nx], 'spacing_m': spacing}, 'support_count': int(np.count_nonzero(mask)), 'maximum_shared_section_difference_m': float(max_shared_bed_diff), 'point_samples_not_cell_average': True, 'hydraulics_coupled': False, 'cross_edge_endpoint_continuity_verified': False, 'global_hydrology_certified': False, 'publishable': False}
    return {'bed_m': bed.reshape(nz, nx), 'supported_mask': mask.reshape(nz, nx), 'owner_piece_index': owner.reshape(nz, nx), 'provenance': provenance}
METRIC_VALLEY_TILED_UNION_SCHEMA = 'terragenesis-tiled-shared-valley-union-v1'
METRIC_VALLEY_TILED_UNION_ALGORITHM = 'whole-component-profile-envelope-monotone-closure-tiled-v1'
MAX_GLOBAL_CELLS = 8000000

@_i42_dataclass(frozen=True)
class TileBudget:
    max_cells: int = 32768
    max_vertices: int = 262144
    max_bytes: int = METRIC_CHANNEL_GEOMETRY_MAX_BYTES

    def __post_init__(self):
        if type(self.max_cells) is not int or self.max_cells < 1 or type(self.max_vertices) is not int or (self.max_vertices < 5) or (type(self.max_bytes) is not int) or (self.max_bytes < 1):
            raise ValueError('invalid tiled valley resource budget')
        if self.max_vertices > 262144 or self.max_bytes > METRIC_CHANNEL_GEOMETRY_MAX_BYTES:
            raise ValueError('tiled valley resource budget exceeds fixed limit')

def _large_config(config, spacing):
    """Duck-typed config for the sparse field helpers, with no global tile cap."""
    limit = min(MAX_GLOBAL_CELLS * 5, 40000000)
    return _i42_SimpleNamespace(fine_spacing_m=float(spacing), max_vertices=limit, max_cut_m=float(config.max_cut_m))

def _expected_arrays():
    return {'source_height_m', 'source_valid_mask', 'owner_grid', 'corridor_mask', 'lake_mask', 'source_node_cell_ids', 'receiver', 'node_xz_m', 'width_m', 'base_depth_m', 'profile_offsets', 'profile_t', 'profile_source_m', 'profile_center_bed_m', 'global_cell_xy', 'global_vertex_xz_m', 'global_source_elevation_m', 'global_source_cell_ids', 'global_cut_depth_m', 'global_bed_elevation_m', 'global_triangles', 'tile_offsets', 'tile_vertex_offsets', 'tile_triangle_offsets', 'tile_cell_global_index', 'tile_cell_xy', 'tile_vertices_xz_m', 'tile_source_elevation_m', 'tile_source_cell_ids', 'tile_cut_depth_m', 'tile_bed_elevation_m', 'tile_triangles', 'port_edge_node_indices', 'port_xz_m', 'port_profile_xz_m', 'port_triangle_ids', 'port_barycentric', 'port_cut_depth_m'}

def _tile_bytes(arrays, lo_cell, hi_cell, lo_vertex, hi_vertex, lo_tri, hi_tri):
    fields = (('tile_cell_xy', lo_cell, hi_cell), ('tile_cell_global_index', lo_cell, hi_cell), ('tile_vertices_xz_m', lo_vertex, hi_vertex), ('tile_source_elevation_m', lo_vertex, hi_vertex), ('tile_source_cell_ids', lo_vertex, hi_vertex), ('tile_cut_depth_m', lo_vertex, hi_vertex), ('tile_bed_elevation_m', lo_vertex, hi_vertex), ('tile_triangles', lo_tri, hi_tri))
    total = 0
    for name, low, high in fields:
        value = arrays.get(name)
        if value is None:
            continue
        total += int(value[low:high].nbytes)
    return total

def _tile_from_cells(cell_indices, global_arrays, tile_id, source_plan, budget):
    from terrain_pipeline.common_infra import identity as _i42_identity
    from terrain_pipeline.common_infra import readonly as _i42_readonly
    cells = global_arrays['global_cell_xy'][cell_indices]
    triangles = global_arrays['global_triangles'][_i42_np.concatenate([_i42_np.arange(4 * index, 4 * index + 4, dtype=_i42_np.int64) for index in cell_indices])]
    vertex_ids = _i42_np.unique(triangles.reshape(-1))
    local_map = _i42_np.full(len(global_arrays['global_vertex_xz_m']), -1, _i42_np.int64)
    local_map[vertex_ids] = _i42_np.arange(len(vertex_ids), dtype=_i42_np.int64)
    local_triangles = local_map[triangles]
    arrays = {'tile_cell_xy': cells.copy(), 'tile_cell_global_index': cell_indices.copy(), 'tile_vertices_xz_m': global_arrays['global_vertex_xz_m'][vertex_ids].copy(), 'tile_source_elevation_m': global_arrays['global_source_elevation_m'][vertex_ids].copy(), 'tile_source_cell_ids': global_arrays['global_source_cell_ids'][vertex_ids].copy(), 'tile_cut_depth_m': global_arrays['global_cut_depth_m'][vertex_ids].copy(), 'tile_bed_elevation_m': global_arrays['global_bed_elevation_m'][vertex_ids].copy(), 'tile_triangles': local_triangles.copy()}
    arrays = {key: _i42_readonly(value) for key, value in arrays.items()}
    tile_meta = {'schema': METRIC_VALLEY_TILED_UNION_SCHEMA + '.tile', 'algorithm': METRIC_VALLEY_TILED_UNION_ALGORITHM, 'tile_id': int(tile_id), 'source_plan_identity_sha256': source_plan, 'cell_count': int(len(cells)), 'vertex_count': int(len(vertex_ids)), 'triangle_count': int(len(local_triangles)), 'global_cell_index_start': int(cell_indices[0]), 'global_cell_index_stop': int(cell_indices[-1]) + 1, 'byte_count': int(sum((value.nbytes for value in arrays.values()))), 'budget': _i42_asdict(budget)}
    if tile_meta['cell_count'] > budget.max_cells:
        raise ValueError('tiled valley cell budget exceeded')
    if tile_meta['vertex_count'] > budget.max_vertices:
        raise ValueError('tiled valley vertex budget exceeded')
    if tile_meta['byte_count'] > budget.max_bytes:
        raise ValueError('tiled valley byte budget exceeded')
    tile_meta['identity_sha256'] = _i42_identity(arrays, tile_meta)
    return (arrays, tile_meta)

def _partition(global_arrays, budget):
    cells = global_arrays['global_cell_xy']
    total = len(cells)
    chunks = []
    start = 0
    while start < total:
        end = start
        corner_ids = set()
        while end < total:
            x, z = map(int, cells[end])
            candidate = corner_ids | {(x, z), (x + 1, z), (x + 1, z + 1), (x, z + 1)}
            candidate_vertices = len(candidate) + (end - start + 1)
            if end > start and (end - start + 1 > budget.max_cells or candidate_vertices > budget.max_vertices):
                break
            corners = candidate
            if end - start + 1 > budget.max_cells or candidate_vertices > budget.max_vertices:
                raise ValueError('single tiled valley cell exceeds resource budget')
            end += 1
            corner_ids = corners
        chunks.append(_i42_np.arange(start, end, dtype=_i42_np.int64))
        start = end
    return chunks

def _prepare_field(terrain, node_cell_ids, receiver, width_m, base_depth_m, owner_grid, corridor_mask, lake_mask, config, spacing):
    local = _large_config(config, spacing)
    cols = terrain.elevation_m.shape[1]
    points = _i42_np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m, terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, base_depth_m, terrain, local.max_cut_m)
    _footprint(points, receiver, width_m, _i42_np.full(len(points), local.max_cut_m), terrain, owner_grid, corridor_mask, lake_mask, owner_grid.ravel()[node_cell_ids], spacing)
    pass
    _profile_overlap(points, receiver, width_m, profile, terrain)
    cells = _sparse_cells(points, receiver, width_m, profile, local, terrain)
    if len(cells) > MAX_GLOBAL_CELLS:
        raise ValueError('whole-component shared field exceeds global cell budget')
    vertices, triangles = _sparse_mesh(cells, terrain, spacing, local.max_vertices)
    source, source_cells = _metric_channel_geometry_sample(terrain.elevation_m, vertices, terrain)
    base_cut = _profile_cut(points, receiver, width_m, profile, vertices, terrain, lake_mask)
    return (local, points, profile, cells, vertices, triangles, source, source_cells, base_cut)

def _build_field(terrain, node_cell_ids, receiver, width_m, base_depth_m, owner_grid, corridor_mask, lake_mask, source_plan, config, spacing):
    local, points, profile, cells, vertices, triangles, source, source_cells, base_cut = _prepare_field(terrain, node_cell_ids, receiver, width_m, base_depth_m, owner_grid, corridor_mask, lake_mask, config, spacing)
    cut, closure = _close_bed(points, receiver, cells, vertices, triangles, source, original_cut=base_cut, terrain=terrain, spacing=spacing, max_cut_m=local.max_cut_m)
    _cut_source_constraints(vertices, source_cells, cut, terrain, owner_grid, corridor_mask, lake_mask, owner_grid.ravel()[node_cell_ids[0]])
    _sparse_slope(points, receiver, cells, vertices, triangles, source - cut, spacing, terrain)
    ports = _sparse_ports(points, receiver, width_m, profile, cells, vertices, triangles, cut, spacing, terrain)
    return (profile, cells, vertices, triangles, source, source_cells, base_cut, cut, closure, ports)

def build_tiled_monotone_union(terrain, node_cell_ids, receiver, width_m, base_depth_m, *, owner_grid, corridor_mask, lake_mask, source_plan_identity_sha256, config=None, budget=None):
    """Build one shared field, then export deterministic bounded tiles."""
    from terrain_pipeline.common_infra import identity as _i42_identity
    from terrain_pipeline.common_infra import readonly as _i42_readonly
    config = config or GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0)
    budget = budget or TileBudget()
    _check_inputs(terrain, node_cell_ids, receiver, width_m, base_depth_m, owner_grid, corridor_mask, lake_mask, config)
    if not isinstance(source_plan_identity_sha256, str) or len(source_plan_identity_sha256) != 64 or any((c not in '0123456789abcdef' for c in source_plan_identity_sha256)):
        raise ValueError('source network plan identity required')
    if _i42_np.unique(owner_grid.ravel()[node_cell_ids]).size != 1:
        raise ValueError('shared component spans original source owners')
    result = _build_field(terrain, _i42_np.asarray(node_cell_ids, _i42_np.int64), _i42_np.asarray(receiver, _i42_np.int64), _i42_np.asarray(width_m, _i42_np.float64), _i42_np.asarray(base_depth_m, _i42_np.float64), owner_grid, corridor_mask, lake_mask, source_plan_identity_sha256, config, config.fine_spacing_m)
    profile, cells, vertices, triangles, source, source_cells, base_cut, cut, closure, ports = result
    global_arrays = {'global_cell_xy': cells, 'global_vertex_xz_m': vertices, 'global_source_elevation_m': source, 'global_source_cell_ids': source_cells, 'global_cut_depth_m': cut, 'global_bed_elevation_m': source - cut, 'global_triangles': triangles}
    chunks = _partition(global_arrays, budget)
    tile_arrays, tile_records = ([], [])
    for tile_id, chunk in enumerate(chunks):
        arrays, record = _tile_from_cells(chunk, global_arrays, tile_id, source_plan_identity_sha256, budget)
        tile_arrays.append(arrays)
        tile_records.append(record)
    cat = {}
    for key in tile_arrays[0]:
        cat[key] = _i42_readonly(_i42_np.concatenate([part[key] for part in tile_arrays], axis=0))
    cell_offsets = _i42_np.cumsum([0] + [record['cell_count'] for record in tile_records], dtype=_i42_np.int64)
    vertex_offsets = _i42_np.cumsum([0] + [record['vertex_count'] for record in tile_records], dtype=_i42_np.int64)
    tri_offsets = _i42_np.cumsum([0] + [record['triangle_count'] for record in tile_records], dtype=_i42_np.int64)
    arrays = {'source_height_m': _i42_readonly(_i42_np.asarray(terrain.elevation_m, _i42_np.float64)), 'source_valid_mask': _i42_readonly(_i42_np.asarray(terrain.valid_mask, bool)), 'owner_grid': _i42_readonly(_i42_np.asarray(owner_grid, _i42_np.int64)), 'corridor_mask': _i42_readonly(_i42_np.asarray(corridor_mask, bool)), 'lake_mask': _i42_readonly(_i42_np.asarray(lake_mask, bool)), 'source_node_cell_ids': _i42_readonly(_i42_np.asarray(node_cell_ids, _i42_np.int64)), 'receiver': _i42_readonly(_i42_np.asarray(receiver, _i42_np.int64)), 'node_xz_m': _i42_readonly(_i42_np.column_stack((terrain.x0_m + node_cell_ids % terrain.elevation_m.shape[1] * terrain.dx_m, terrain.z0_m + node_cell_ids // terrain.elevation_m.shape[1] * terrain.dz_m))), 'width_m': _i42_readonly(_i42_np.asarray(width_m, _i42_np.float64)), 'base_depth_m': _i42_readonly(_i42_np.asarray(base_depth_m, _i42_np.float64)), 'profile_offsets': _i42_readonly(profile[0]), 'profile_t': _i42_readonly(profile[1]), 'profile_source_m': _i42_readonly(profile[2]), 'profile_center_bed_m': _i42_readonly(profile[3]), **{key: _i42_readonly(value) for key, value in global_arrays.items()}, 'tile_offsets': cell_offsets, 'tile_vertex_offsets': vertex_offsets, 'tile_triangle_offsets': tri_offsets, **cat, 'port_edge_node_indices': _i42_readonly(ports[0]), 'port_xz_m': _i42_readonly(ports[1]), 'port_profile_xz_m': _i42_readonly(ports[2]), 'port_triangle_ids': _i42_readonly(ports[3]), 'port_barycentric': _i42_readonly(ports[4]), 'port_cut_depth_m': _i42_readonly(ports[5])}
    metadata = {'schema': METRIC_VALLEY_TILED_UNION_SCHEMA, 'algorithm': METRIC_VALLEY_TILED_UNION_ALGORITHM, 'terrain_metadata': _metadata_terrain(terrain), 'source_identity_sha256': terrain.identity_sha256, 'source_plan_identity_sha256': source_plan_identity_sha256, 'config': _i42_asdict(config), 'budget': _i42_asdict(budget), 'closure': closure, 'base_cut_volume_m3': _mesh_volume(vertices, triangles, base_cut), 'cut_volume_m3': _mesh_volume(vertices, triangles, cut), 'tile_records': tile_records, 'tile_count': len(tile_records), 'rejections': [], 'budget_refusals': [], 'unresolved_coverage': [], 'global_cell_count': len(cells), 'global_vertex_count': len(vertices), 'cross_tile_centerline_validated': True, 'global_unique_cell_ownership': True, 'spatial_refinement_relative': None, 'hydraulic_ready': False, 'natural_outlet_verified': False, 'publishable': False}
    bundle = {'arrays': arrays, 'metadata': metadata, 'identity_sha256': _i42_identity(arrays, metadata)}
    validate_tiled_monotone_union(bundle)
    return bundle

def build_tiled_refinement_pair(*args, **kwargs):
    """Build .5/.25 shared fields and apply the unchanged two percent gate."""
    from terrain_pipeline.common_infra import identity as _i42_identity
    base_config = kwargs.pop('config', None) or GeometryConfig(fine_spacing_m=0.5, smoothing_iterations=0)
    coarse_config = GeometryConfig(**{**_i42_asdict(base_config), 'fine_spacing_m': 0.5})
    fine_config = GeometryConfig(**{**_i42_asdict(base_config), 'fine_spacing_m': 0.25})
    coarse = build_tiled_monotone_union(*args, config=coarse_config, **kwargs)
    fine = build_tiled_monotone_union(*args, config=fine_config, **kwargs)
    relative = abs(coarse['metadata']['cut_volume_m3'] - fine['metadata']['cut_volume_m3'])
    relative /= max(fine['metadata']['cut_volume_m3'], 1e-12)
    if relative > 0.02:
        raise ValueError('tiled shared-field spatial refinement exceeds fixed 2% gate')
    coarse['metadata']['spatial_refinement_relative'] = float(relative)
    fine['metadata']['spatial_refinement_relative'] = float(relative)
    coarse['identity_sha256'] = _i42_identity(coarse['arrays'], coarse['metadata'])
    fine['identity_sha256'] = _i42_identity(fine['arrays'], fine['metadata'])
    return {'coarse': coarse, 'fine': fine, 'spatial_refinement_relative': float(relative)}

def _check_tile(bundle, index):
    from terrain_pipeline.common_infra import identity as _i42_identity
    from terrain_pipeline.common_infra import readonly as _i42_readonly
    a, m = (bundle['arrays'], bundle['metadata'])
    rec = m['tile_records'][index]
    expected_record = {'schema', 'algorithm', 'tile_id', 'source_plan_identity_sha256', 'cell_count', 'vertex_count', 'triangle_count', 'global_cell_index_start', 'global_cell_index_stop', 'byte_count', 'budget', 'identity_sha256'}
    if set(rec) != expected_record or rec['source_plan_identity_sha256'] != m['source_plan_identity_sha256']:
        raise ValueError('tiled valley tile manifest mismatch')
    c0, c1 = map(int, a['tile_offsets'][index:index + 2])
    v0, v1 = map(int, a['tile_vertex_offsets'][index:index + 2])
    t0, t1 = map(int, a['tile_triangle_offsets'][index:index + 2])
    arrays = {key: _i42_readonly(a[key][low:high]) for key, low, high in (('tile_cell_xy', c0, c1), ('tile_cell_global_index', c0, c1), ('tile_vertices_xz_m', v0, v1), ('tile_source_elevation_m', v0, v1), ('tile_source_cell_ids', v0, v1), ('tile_cut_depth_m', v0, v1), ('tile_bed_elevation_m', v0, v1), ('tile_triangles', t0, t1))}
    if rec['identity_sha256'] != _i42_identity(arrays, {key: rec[key] for key in ('schema', 'algorithm', 'tile_id', 'source_plan_identity_sha256', 'cell_count', 'vertex_count', 'triangle_count', 'global_cell_index_start', 'global_cell_index_stop', 'byte_count', 'budget')}):
        raise ValueError('tiled valley tile identity mismatch')
    if rec['byte_count'] != sum((value.nbytes for value in arrays.values())):
        raise ValueError('tiled valley tile byte ledger mismatch')
    if rec['byte_count'] > int(m['budget']['max_bytes']):
        raise ValueError('tiled valley tile byte budget mismatch')
    return (c0, c1, v0, v1, t0, t1, arrays, rec)

def validate_tiled_monotone_union(bundle):
    """Cold validator. It recomputes profiles, source/cut envelopes and PL guards."""
    from terrain_pipeline.common_infra import identity as _i42_identity
    from terrain_pipeline.common_infra import TerrainGrid as _i42_TerrainGrid
    if not isinstance(bundle, dict) or set(bundle) != {'arrays', 'metadata', 'identity_sha256'} or bundle['identity_sha256'] != _i42_identity(bundle['arrays'], bundle['metadata']):
        raise ValueError('tiled valley identity mismatch')
    a, m = (bundle['arrays'], bundle['metadata'])
    expected_meta = {'schema', 'algorithm', 'terrain_metadata', 'source_identity_sha256', 'source_plan_identity_sha256', 'config', 'budget', 'closure', 'base_cut_volume_m3', 'cut_volume_m3', 'tile_records', 'tile_count', 'rejections', 'budget_refusals', 'unresolved_coverage', 'global_cell_count', 'global_vertex_count', 'cross_tile_centerline_validated', 'global_unique_cell_ownership', 'spatial_refinement_relative', 'hydraulic_ready', 'natural_outlet_verified', 'publishable'}
    if set(a) != _expected_arrays() or set(m) != expected_meta or m.get('schema') != METRIC_VALLEY_TILED_UNION_SCHEMA or (m.get('algorithm') != METRIC_VALLEY_TILED_UNION_ALGORITHM):
        raise ValueError('tiled valley schema mismatch')
    if not 1 <= int(m['tile_count']) == len(m['tile_records']):
        raise ValueError('tiled valley tile manifest mismatch')
    terrain = _i42_TerrainGrid(a['source_height_m'], a['source_valid_mask'], **m['terrain_metadata'])
    if terrain.identity_sha256 != m['source_identity_sha256']:
        raise ValueError('tiled valley source identity mismatch')
    config = GeometryConfig(**m['config'])
    budget = TileBudget(**m['budget'])
    source_plan = m['source_plan_identity_sha256']
    if not isinstance(source_plan, str) or len(source_plan) != 64 or any((char not in '0123456789abcdef' for char in source_plan)) or (m['cross_tile_centerline_validated'] is not True) or (m['global_unique_cell_ownership'] is not True) or any((m[key] is not False for key in ('hydraulic_ready', 'natural_outlet_verified', 'publishable'))) or (m['rejections'] != []) or (m['budget_refusals'] != []) or (m['unresolved_coverage'] != []):
        raise ValueError('tiled valley scope or refusal ledger mismatch')
    ids, receiver, width, depth = (a[key] for key in ('source_node_cell_ids', 'receiver', 'width_m', 'base_depth_m'))
    float_fields = {'source_height_m', 'node_xz_m', 'width_m', 'base_depth_m', 'profile_t', 'profile_source_m', 'profile_center_bed_m', 'global_vertex_xz_m', 'global_source_elevation_m', 'global_cut_depth_m', 'global_bed_elevation_m', 'tile_vertices_xz_m', 'tile_source_elevation_m', 'tile_cut_depth_m', 'tile_bed_elevation_m', 'port_xz_m', 'port_profile_xz_m', 'port_barycentric', 'port_cut_depth_m'}
    int_fields = {'owner_grid', 'source_node_cell_ids', 'receiver', 'profile_offsets', 'global_cell_xy', 'global_source_cell_ids', 'global_triangles', 'tile_offsets', 'tile_vertex_offsets', 'tile_triangle_offsets', 'tile_cell_global_index', 'tile_cell_xy', 'tile_source_cell_ids', 'tile_triangles', 'port_edge_node_indices', 'port_triangle_ids'}
    bool_fields = {'source_valid_mask', 'corridor_mask', 'lake_mask'}
    if any((a[key].dtype != _i42_np.float64 for key in float_fields)) or any((a[key].dtype != _i42_np.int64 for key in int_fields)) or any((a[key].dtype != bool for key in bool_fields)):
        raise ValueError('tiled valley array dtype mismatch')
    _check_inputs(terrain, ids, receiver, width, depth, a['owner_grid'], a['corridor_mask'], a['lake_mask'], config)
    if _i42_np.unique(a['owner_grid'].ravel()[ids]).size != 1:
        raise ValueError('tiled valley component spans source owners')
    _, points, profile, cells, vertices, triangles, source, source_cells, base_cut = _prepare_field(terrain, ids, receiver, width, depth, a['owner_grid'], a['corridor_mask'], a['lake_mask'], config, config.fine_spacing_m)
    if not _i42_np.array_equal(a['node_xz_m'], points):
        raise ValueError('tiled valley fixed source node mismatch')
    cut = a['global_cut_depth_m']
    _cut_source_constraints(vertices, source_cells, cut, terrain, a['owner_grid'], a['corridor_mask'], a['lake_mask'], a['owner_grid'].ravel()[ids[0]])
    _sparse_slope(_i42_np.asarray(a['node_xz_m']), receiver, cells, vertices, triangles, source - cut, config.fine_spacing_m, terrain)
    ports = _sparse_ports(_i42_np.asarray(a['node_xz_m']), receiver, width, profile, cells, vertices, triangles, cut, config.fine_spacing_m, terrain)
    for key, value in (('global_cell_xy', cells), ('global_vertex_xz_m', vertices), ('global_source_elevation_m', source), ('global_source_cell_ids', source_cells), ('global_cut_depth_m', cut), ('global_bed_elevation_m', source - cut), ('global_triangles', triangles)):
        if not _i42_np.array_equal(a[key], value):
            raise ValueError('tiled valley global field mismatch: ' + key)
    for key, value in zip(('profile_offsets', 'profile_t', 'profile_source_m', 'profile_center_bed_m'), profile):
        if not _i42_np.array_equal(a[key], value):
            raise ValueError('tiled valley profile mismatch')
    for key, value in zip(('port_edge_node_indices', 'port_xz_m', 'port_profile_xz_m', 'port_triangle_ids', 'port_barycentric', 'port_cut_depth_m'), ports):
        if not _i42_np.allclose(a[key], value, rtol=0.0, atol=1e-09):
            raise ValueError('tiled valley port mismatch')
    if _i42_np.any(cut < base_cut - 1e-09) or _i42_np.any(cut > config.max_cut_m + 1e-08):
        raise ValueError('tiled valley cut envelope mismatch')
    closure = m['closure']
    extra = cut - base_cut
    if set(closure) != {'extra_cut_vertices', 'extra_cut_sum_m', 'maximum_constraint_residual_m', 'centerline_segments'} or closure['extra_cut_vertices'] != int(_i42_np.count_nonzero(extra > 1e-09)) or (not _i42_math.isclose(closure['extra_cut_sum_m'], float(_i42_np.sum(extra)), abs_tol=1e-08)):
        raise ValueError('tiled valley closure ledger mismatch')
    segments = _line_constraints(_i42_np.asarray(a['node_xz_m']), receiver, cells, vertices, triangles, terrain, config.fine_spacing_m)
    if closure['centerline_segments'] != len(segments):
        raise ValueError('tiled valley centerline ledger mismatch')
    bed = source - cut
    residuals = []
    for start, end, dt, _, _ in segments:
        h0 = float(start[1] @ bed[start[0]])
        h1 = float(end[1] @ bed[end[0]])
        residuals.append(h1 - h0 + 1e-07 * dt)
    residual = float(max(residuals, default=0.0))
    if not _i42_math.isfinite(residual) or residual > 1e-07 or (not _i42_math.isclose(closure['maximum_constraint_residual_m'], residual, abs_tol=1e-07)):
        raise ValueError('tiled valley monotone closure residual mismatch')
    if not _i42_math.isclose(m['cut_volume_m3'], _mesh_volume(vertices, triangles, cut), rel_tol=1e-10, abs_tol=1e-07):
        raise ValueError('tiled valley volume ledger mismatch')
    if m['global_cell_count'] != len(cells) or m['global_vertex_count'] != len(vertices) or int(a['tile_offsets'][-1]) != len(cells) or (int(a['tile_vertex_offsets'][-1]) != sum((record['vertex_count'] for record in m['tile_records']))) or (int(a['tile_triangle_offsets'][-1]) != sum((record['triangle_count'] for record in m['tile_records']))):
        raise ValueError('tiled valley offset ledger mismatch')
    if not _i42_math.isclose(m['base_cut_volume_m3'], _mesh_volume(vertices, triangles, base_cut), rel_tol=1e-10, abs_tol=1e-07):
        raise ValueError('tiled valley base material ledger mismatch')
    seen = []
    for index in range(m['tile_count']):
        c0, c1, v0, v1, t0, t1, ta, rec = _check_tile(bundle, index)
        if rec['tile_id'] != index or rec['cell_count'] != c1 - c0 or rec['vertex_count'] != v1 - v0 or (rec['triangle_count'] != t1 - t0) or (rec['global_cell_index_start'] != c0) or (rec['global_cell_index_stop'] != c1):
            raise ValueError('tiled valley tile shape mismatch')
        if rec['cell_count'] > budget.max_cells or rec['vertex_count'] > budget.max_vertices:
            raise ValueError('tiled valley tile budget mismatch')
        if _i42_np.any(ta['tile_triangles'] < 0) or _i42_np.any(ta['tile_triangles'] >= rec['vertex_count']):
            raise ValueError('tiled valley local triangle range mismatch')
        global_ids = ta['tile_cell_global_index']
        if not _i42_np.array_equal(ta['tile_cell_xy'], cells[global_ids]):
            raise ValueError('tiled valley tile cell mismatch')
        expected_ids = _i42_np.unique(triangles[_i42_np.concatenate([_i42_np.arange(4 * int(value), 4 * int(value) + 4, dtype=_i42_np.int64) for value in global_ids])])
        if not _i42_np.array_equal(ta['tile_vertices_xz_m'], vertices[expected_ids]):
            raise ValueError('tiled valley shared corner mismatch')
        seen.extend(global_ids.tolist())
    if not _i42_np.array_equal(_i42_np.asarray(seen, _i42_np.int64), _i42_np.arange(len(cells), dtype=_i42_np.int64)):
        raise ValueError('tiled valley global cell ownership is not unique')
    return True

def save_tiled_monotone_union(path, bundle):
    from terrain_pipeline.common_infra import save_bundle as _i42_save_bundle
    _i42_save_bundle(path, bundle, validator=validate_tiled_monotone_union)

def load_tiled_monotone_union(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _i42_load_bundle
    bundle = _i42_load_bundle(path, expected_sha256=expected_sha256, validator=validate_tiled_monotone_union, max_bytes=METRIC_CHANNEL_GEOMETRY_MAX_BYTES * 4)
    if bundle['identity_sha256'] != expected_identity:
        raise ValueError('external tiled valley identity mismatch')
    return bundle
build_tiled_shared_field = build_tiled_monotone_union
validate_tiled_shared_field = validate_tiled_monotone_union
save_tiled_shared_field = save_tiled_monotone_union
load_tiled_shared_field = load_tiled_monotone_union
_CELL_SIZE_M = 30.0
_EQUIVALENT_RUNOFF_MM_H = 1.0
_ALLOWED_PARAM_KEYS = ('world_seed', 'manning_n', 'max_depth_m', 'min_width_m', 'max_width_m', 'reference_width_m', 'reference_discharge_m3_s', 'resample_stride')
_DEFAULTS = {'world_seed': 20261020, 'manning_n': 0.035, 'max_depth_m': 3.0, 'min_width_m': 30.0, 'max_width_m': 3000.0, 'reference_width_m': 45.0, 'reference_discharge_m3_s': 27.77777777777778, 'resample_stride': 3}
_MANNING_TOL = 1e-08
_MAX_SAMPLES = 128

def _is_bool(x) -> bool:
    return isinstance(x, (bool, _i44_np.bool_))

def _as_finite_positive_scalar(x, name):
    if _is_bool(x):
        raise TypeError(f'{name} must not be boolean')
    if not isinstance(x, (int, float, _i44_np.integer, _i44_np.floating)):
        raise ValueError(f'{name} must be a real numeric scalar')
    try:
        v = float(x)
    except (TypeError, ValueError) as exc:
        raise TypeError(f'{name} must be a finite number') from exc
    if not _i44_math.isfinite(v) or v <= 0.0:
        raise ValueError(f'{name} must be finite and > 0')
    return v

def _validate_parameters(section_parameters):
    if not isinstance(section_parameters, dict):
        raise TypeError('section_parameters must be an explicit dict')
    unknown = set(section_parameters) - set(_ALLOWED_PARAM_KEYS)
    if unknown:
        raise KeyError(f'unknown section_parameters keys: {sorted(unknown)}')
    params = dict(_DEFAULTS)
    params.update(section_parameters)
    seed = params['world_seed']
    if _is_bool(seed) or not isinstance(seed, (int, _i44_np.integer)):
        raise TypeError('world_seed must be an integer')
    seed = int(seed)
    if seed < 0:
        raise ValueError('world_seed must be >= 0')
    stride = params['resample_stride']
    if _is_bool(stride) or not isinstance(stride, (int, _i44_np.integer)):
        raise TypeError('resample_stride must be an integer')
    stride = int(stride)
    if stride < 1:
        raise ValueError('resample_stride must be >= 1')
    manning_n = _as_finite_positive_scalar(params['manning_n'], 'manning_n')
    max_depth_m = _as_finite_positive_scalar(params['max_depth_m'], 'max_depth_m')
    min_width_m = _as_finite_positive_scalar(params['min_width_m'], 'min_width_m')
    max_width_m = _as_finite_positive_scalar(params['max_width_m'], 'max_width_m')
    if max_width_m < min_width_m:
        raise ValueError('max_width_m must be >= min_width_m')
    reference_width_m = _as_finite_positive_scalar(params['reference_width_m'], 'reference_width_m')
    reference_discharge_m3_s = _as_finite_positive_scalar(params['reference_discharge_m3_s'], 'reference_discharge_m3_s')
    actual = {'world_seed': seed, 'manning_n': manning_n, 'max_depth_m': max_depth_m, 'min_width_m': min_width_m, 'max_width_m': max_width_m, 'reference_width_m': reference_width_m, 'reference_discharge_m3_s': reference_discharge_m3_s, 'resample_stride': stride}
    return actual

def _validate_selection(selection):
    if not isinstance(selection, dict):
        raise TypeError('selection must be a dict')
    if 'chosen' not in selection:
        raise KeyError("selection must contain 'chosen'")
    chosen = selection['chosen']
    if not isinstance(chosen, dict):
        raise TypeError("selection['chosen'] must be a dict")
    if 'stem_flat_cells' not in chosen:
        raise KeyError("chosen must contain 'stem_flat_cells'")
    stem = _i44_np.asarray(chosen['stem_flat_cells'])
    if stem.ndim != 1:
        raise ValueError('stem_flat_cells must be a 1-D vector')
    if not _i44_np.issubdtype(stem.dtype, _i44_np.integer):
        raise TypeError('stem_flat_cells must be an integer vector')
    stem = stem.astype(_i44_np.int64, copy=False)
    if stem.size < 2:
        raise ValueError('stem_flat_cells must contain at least 2 nodes')
    if _i44_np.unique(stem).size != stem.size:
        raise ValueError('stem_flat_cells must not contain duplicates')
    return stem

def _validate_elevation(elevation_m):
    arr = _i44_np.asarray(elevation_m)
    if arr.ndim != 2:
        raise ValueError('elevation_m must be a 2-D array')
    if not isinstance(elevation_m, _i44_np.ndarray) or arr.dtype != _i44_np.float64:
        raise ValueError('elevation_m must be a float64 ndarray')
    if not arr.size:
        raise ValueError('elevation_m must not be empty')
    return arr

def _validate_origin(origin_native_xz):
    if origin_native_xz is None:
        raise TypeError('origin_native_xz must be provided')
    try:
        ox, oz = origin_native_xz
    except (TypeError, ValueError) as exc:
        raise TypeError('origin_native_xz must be a length-2 sequence') from exc
    for name, v in (('origin x', ox), ('origin z', oz)):
        if _is_bool(v) or not isinstance(v, (int, _i44_np.integer)):
            raise TypeError(f'{name} must be a signed integer')
    return (int(ox), int(oz))

def _validate_design_q(design_q_m3_s):
    if _is_bool(design_q_m3_s):
        raise TypeError('design_q_m3_s must not be boolean')
    if not isinstance(design_q_m3_s, (int, float, _i44_np.integer, _i44_np.floating)):
        raise ValueError('design_q_m3_s must be a real numeric scalar')
    q = float(design_q_m3_s)
    if not _i44_math.isfinite(q) or q <= 0.0:
        raise ValueError('design_q_m3_s must be finite and > 0')
    return q

def build_section(elevation_m, selection, design_q_m3_s, *, origin_native_xz, section_parameters) -> dict:
    from terrain_pipeline.geology import sample_lithology_points as _i44_sample_lithology_points
    from terrain_pipeline.lake import channel_width_from_lithology_m as _i44_channel_width_from_lithology_m
    from terrain_pipeline.surface_rivers.metric_dynamic_feedback import normal_depth as _i44_normal_depth
    params = _validate_parameters(section_parameters)
    stem = _validate_selection(selection)
    field = _validate_elevation(elevation_m)
    ox, oz = _validate_origin(origin_native_xz)
    design_q = _validate_design_q(design_q_m3_s)
    rows, cols = _i44_np.divmod(stem, field.shape[1])
    if _i44_np.any(rows < 0) or _i44_np.any(rows >= field.shape[0]):
        raise ValueError('stem_flat_cells contains out-of-range row indices')
    node_cell_ids = (rows * field.shape[1] + cols).astype(_i44_np.int64)
    source_bed_m = _i44_np.asarray(field[rows, cols], dtype=_i44_np.float64)
    if not _i44_np.all(_i44_np.isfinite(source_bed_m)):
        raise ValueError('selected elevation nodes must be finite')
    for i in range(stem.size - 1):
        if not source_bed_m[i] > source_bed_m[i + 1]:
            raise ValueError('source elevation along stem must strictly decrease downstream')
    stride = params['resample_stride']
    n = int(stem.size)
    indices = _i44_np.unique(_i44_np.r_[_i44_np.arange(0, n - 1, stride, dtype=_i44_np.int64), _i44_np.int64(n - 1)])
    if indices.size > _MAX_SAMPLES or indices.size < 2:
        raise ValueError('resampled stem must contain between 2 and 128 nodes')
    actual_stride = float(stride)
    sub_rows = rows[indices]
    sub_cols = cols[indices]
    node_xz_m = _i44_np.stack([(ox + sub_cols.astype(_i44_np.float64)) * _CELL_SIZE_M, (oz + sub_rows.astype(_i44_np.float64)) * _CELL_SIZE_M], axis=1)
    source_bed_sub = source_bed_m[indices]
    dx = _i44_np.diff(node_xz_m[:, 0])
    dz = _i44_np.diff(node_xz_m[:, 1])
    seg_len = _i44_np.sqrt(dx * dx + dz * dz).astype(_i44_np.float64)
    if not _i44_np.all(_i44_np.isfinite(seg_len)) or _i44_np.any(seg_len <= 0.0):
        raise ValueError('resampled stem contains zero or non-finite segment length')
    slope_seg = (source_bed_sub[:-1] - source_bed_sub[1:]) / seg_len
    source_slope_per_m = _i44_np.empty_like(source_bed_sub)
    source_slope_per_m[:-1] = slope_seg
    source_slope_per_m[-1] = slope_seg[-1]
    length = seg_len
    full_stem_length_m = float(_i44_np.sum(seg_len))
    lith = _i44_sample_lithology_points(node_xz_m[:, 0], node_xz_m[:, 1], world_seed=params['world_seed'])
    bed_hardness = _i44_np.asarray(lith['bed_hardness'], dtype=_i44_np.float64)
    bank_hardness = _i44_np.asarray(lith['bank_hardness'], dtype=_i44_np.float64)
    equivalent_area_m2 = design_q / (_EQUIVALENT_RUNOFF_MM_H / 1000.0 / 3600.0)
    width_m = _i44_np.empty_like(source_bed_sub)
    normal_depth_m = _i44_np.empty_like(source_bed_sub)
    design_q_per_node = _i44_np.full_like(source_bed_sub, design_q)
    for i in range(source_bed_sub.size):
        w, _q = _i44_channel_width_from_lithology_m(_i44_np.array([equivalent_area_m2], dtype=_i44_np.float64), _i44_np.array([bed_hardness[i]], dtype=_i44_np.float64), _i44_np.array([bank_hardness[i]], dtype=_i44_np.float64), reference_discharge_m3_s=params['reference_discharge_m3_s'], reference_width_m=params['reference_width_m'], min_width_m=params['min_width_m'], max_width_m=params['max_width_m'], design_runoff_mm_h=_EQUIVALENT_RUNOFF_MM_H)
        w = float(w[0])
        if not _i44_math.isfinite(w) or w <= 0.0:
            raise ValueError('invalid_width_from_lithology')
        depth = _i44_normal_depth(float(design_q_per_node[i]), w, float(source_slope_per_m[i]), params['manning_n'])
        depth = float(depth)
        if not _i44_math.isfinite(depth) or depth <= 0.0:
            raise ValueError('depth_budget_exceeded')
        if depth > float(params['max_depth_m']):
            raise ValueError('depth_budget_exceeded')
        width_m[i] = w
        normal_depth_m[i] = depth
    for i in range(source_bed_sub.size):
        w = float(width_m[i])
        d = float(normal_depth_m[i])
        if w <= 0.0 or d <= 0.0:
            raise ValueError('invalid_hydraulic_section')
        slope = float(source_slope_per_m[i])
        q_check = 1.0 / float(params['manning_n']) * w * d * (w * d / (w + 2.0 * d)) ** (2.0 / 3.0) * _i44_math.sqrt(max(slope, 0.0))
        q_target = float(design_q_per_node[i])
        if q_target == 0.0:
            if abs(q_check) > 1e-08:
                raise ValueError('manning_roundtrip_mismatch')
        else:
            rel_err = abs(q_check - q_target) / abs(q_target)
            if not rel_err <= 1e-08:
                raise ValueError('manning_roundtrip_mismatch')
    full_rows = rows
    full_cols = cols
    full_stem_length_m = 0.0
    if full_rows.size >= 2:
        dx = _i44_np.diff(full_rows.astype(_i44_np.float64))
        dz = _i44_np.diff(full_cols.astype(_i44_np.float64))
        seg = _i44_np.hypot(dx, dz) * float(_CELL_SIZE_M)
        full_stem_length_m = float(seg.sum())
    sampled_stem_length_m = float(seg_len.sum())
    length_difference_m = float(full_stem_length_m - sampled_stem_length_m)
    receiver = _i44_np.r_[_i44_np.arange(1, len(indices), dtype=_i44_np.int64), _i44_np.int64(-1)].astype(_i44_np.int64)
    arrays = {'node_cell_ids': node_cell_ids[indices], 'node_xz_m': node_xz_m, 'source_bed_m': source_bed_sub, 'source_slope_per_m': source_slope_per_m, 'width_m': width_m, 'normal_depth_m': normal_depth_m, 'design_q_m3_s': design_q_per_node, 'bed_hardness': bed_hardness, 'bank_hardness': bank_hardness, 'receiver': receiver}
    metadata = {'world_seed': params['world_seed'], 'origin_native_xz': origin_native_xz, 'actual_parameters': params, 'actual_stride': params['resample_stride'], 'full_stem_length_m': full_stem_length_m, 'sampled_stem_length_m': sampled_stem_length_m, 'length_difference_m': length_difference_m, 'equivalent_area_not_physical_catchment': True, 'normal_depth_not_bankfull': True, 'generation_section_not_dynamic_erosion': True, 'hydraulic_ready': False, 'natural_outlet_certified': False}
    return {'arrays': arrays, 'metadata': metadata}
TD_NATURAL_CHANNEL_GEOMETRY_SCHEMA = 'td-natural-channel-geometry-v1'
WINDOW_SCHEMA = 'td-natural-channel-window-v1'
FLAGS = ('hydraulic_ready', 'natural_outlet_verified', 'publishable')
ARRAY_NAMES = {'node_cell_ids', 'edge_cell_ids', 'node_world_xz_m', 'node_world_xyz_m', 'edge_centerline_xyz_m', 'edge_sections_xyz_m', 'node_native_xz_m', 'node_bed_m', 'node_width_m', 'node_depth_m', 'node_representative_q_m3_s', 'node_anchor_mask', 'edge_requires_refinement', 'node_over_budget_mask', 'edge_slope_failed_mask', 'source_height_m', 'valid_mask', 'protected_mask', 'open_boundary_mask', 'bounded_bed_m', 'required_cut_m'}

@_i45_dataclass(frozen=True)
class NaturalGeometryRecipe:
    smoothing_strength: float = 0.2
    max_offset_m: float = 5.0
    max_cut_m: float = 4.0
    min_bed_slope_m_per_m: float = 0.0001
    max_window_span_m: float = 240.0
    min_cells_across_width: float = 2.0

    def __post_init__(self):
        for name, value in _i45_asdict(self).items():
            if isinstance(value, bool) or not _i45_math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be finite and nonnegative')
        if self.smoothing_strength > 0.5 or not 0 < self.max_window_span_m <= 240 or self.min_cells_across_width <= 0:
            raise ValueError('invalid smoothing or window resolution policy')

def _network_fields(network):
    from terrain_pipeline.td_natural_river_network import validate_natural_river_network as _i45_validate_natural_river_network
    _i45_validate_natural_river_network(network)
    arrays, metadata = (network['arrays'], network['metadata'])
    required = ('source_height_m', 'valid_mask', 'protected_mask', 'open_boundary_mask', 'receiver', 'routing_order', 'selected_basin_mask', 'edge_cell_ids', 'node_cell_ids', 'node_native_xyz_m', 'node_width_m', 'node_depth_m', 'node_representative_q_m3_s', 'edge_requires_refinement')
    if any((name not in arrays for name in required)):
        raise ValueError('natural network core arrays required')
    height = _i45_np.asarray(arrays['source_height_m'])
    if height.ndim != 2 or list(height.shape) != list(metadata['grid_shape']):
        raise ValueError('network grid shape mismatch')
    nodes = _i45_np.asarray(arrays['node_cell_ids'])
    edges = _i45_np.asarray(arrays['edge_cell_ids'])
    if nodes.dtype != _i45_np.int64 or edges.dtype != _i45_np.int64 or edges.shape != (len(edges), 2) or (not _i45_np.array_equal(nodes, _i45_np.unique(nodes))) or (not _i45_np.array_equal(_i45_np.unique(edges.ravel()), nodes)) or (not _i45_np.array_equal(arrays['receiver'][edges[:, 0]], edges[:, 1])):
        raise ValueError('network edge and node topology mismatch')
    if _i45_np.any(~arrays['selected_basin_mask'].ravel()[nodes]) or _i45_np.any(~arrays['valid_mask'].ravel()[nodes]):
        raise ValueError('network nodes outside usable selected basin')
    if _i45_np.any(arrays['protected_mask'].ravel()[nodes]):
        raise ValueError('network node lies in protection')
    return (arrays, metadata)

def _make_plan(network, recipe):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i45_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i45_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i45_digest
    arrays, metadata = _network_fields(network)
    shape = arrays['source_height_m'].shape
    nodes = arrays['node_cell_ids']
    receiver = _i45_np.asarray(arrays['receiver'], dtype=_i45_np.int64)
    discharge = _i45_np.zeros(shape, _i45_np.float64)
    discharge.ravel()[nodes] = _i45_np.asarray(arrays['node_representative_q_m3_s'])
    positive = discharge.ravel()[nodes]
    if not _i45_np.isfinite(positive).all() or _i45_np.any(positive <= 0):
        raise ValueError('network node discharge must be positive')
    natural = metadata['recipe']
    width = _i45_np.asarray(arrays['node_width_m'])
    depth = _i45_np.asarray(arrays['node_depth_m'])
    if _i45_np.any(~_i45_np.isfinite(width)) or _i45_np.any(~_i45_np.isfinite(depth)) or _i45_np.any(width <= 0) or _i45_np.any(depth <= 0):
        raise ValueError('network width and depth must be finite positive')
    plan_recipe = ChannelRecipe(start_discharge_m3_s=float(positive.min()), reference_discharge_m3_s=float(natural['reference_q_m3_s']), reference_width_m=float(natural['reference_width_m']), reference_depth_m=float(natural['reference_depth_m']), width_exponent=float(natural['width_exponent']), depth_exponent=float(natural['depth_exponent']), min_width_m=float(natural['minimum_width_m']), max_width_m=float(natural['maximum_width_m']), min_depth_m=float(natural['minimum_depth_m']), max_depth_m=float(natural['maximum_depth_m']), min_bed_slope_m_per_m=recipe.min_bed_slope_m_per_m, max_cut_m=recipe.max_cut_m, min_cells_across_width=recipe.min_cells_across_width)
    outlet = receiver == -1
    spacing = float(metadata['spacing_m'])
    origin_x, origin_z = metadata['origin_m_xz']
    plan = plan_channel(arrays['source_height_m'], receiver, arrays['routing_order'], outlet.reshape(shape), discharge, spacing, spacing, float(origin_x), float(origin_z), 0.0, network['identity_sha256'], plan_recipe)
    result = {name: value.copy() for name, value in plan['arrays'].items()}
    result['nominal_width_m'].ravel()[nodes] = width
    result['nominal_depth_m'].ravel()[nodes] = depth
    native = _i45_np.asarray(arrays['node_native_xyz_m'])
    if native.shape != (len(nodes), 3) or not _i45_np.isfinite(native).all():
        raise ValueError('invalid native node positions')
    expected_xz = _i45_np.column_stack((origin_x + nodes % shape[1] * spacing, origin_z + nodes // shape[1] * spacing))
    if not _i45_np.allclose(native[:, (0, 2)], expected_xz, atol=1e-08, rtol=0):
        raise ValueError('native node positions differ from route grid')
    if not _i45_np.allclose(native[:, 1], arrays['source_height_m'].ravel()[nodes], atol=1e-08, rtol=0):
        raise ValueError('native node heights differ from source')
    target = result['source_height_m'].ravel().copy()
    target[nodes] -= depth
    active = result['channel_mask'].ravel()
    for donor in _i45_np.asarray(arrays['routing_order'])[::-1]:
        downstream = int(receiver[donor])
        if downstream >= 0 and active[donor] and active[downstream]:
            target[downstream] = min(target[downstream], target[donor] - recipe.min_bed_slope_m_per_m * spacing)
    required = _i45_np.maximum(0.0, result['source_height_m'].ravel() - target)
    bounded = result['source_height_m'].ravel() - _i45_np.minimum(required, recipe.max_cut_m)
    over = active & (required > recipe.max_cut_m + 1e-09)
    failed = _i45_np.zeros(receiver.size, bool)
    for donor, downstream in arrays['edge_cell_ids']:
        if bounded[downstream] > bounded[donor] - recipe.min_bed_slope_m_per_m * spacing + 1e-09:
            failed[donor] = True
    result['target_bed_m'] = target.reshape(shape)
    result['required_cut_m'] = required.reshape(shape)
    result['bounded_bed_m'] = bounded.reshape(shape)
    result['over_budget_mask'] = over.reshape(shape)
    result['failed_slope_edge_donor_mask'] = failed.reshape(shape)
    result['needs_refinement_mask'] = result['channel_mask'] & (result['nominal_width_m'] < recipe.min_cells_across_width * spacing)
    params = dict(plan['identity']['parameters'])
    params['natural_network_identity_sha256'] = network['identity_sha256']
    params['natural_geometry_sha256'] = _i45_digest({name: _i45_array_hash(_i45_np.ascontiguousarray(result[name])) for name in ('nominal_width_m', 'nominal_depth_m', 'target_bed_m', 'bounded_bed_m')})
    plan_identity = _i45_ArtifactIdentity('Terragenesis', 'metric-channel-plan', 'metric-channel-plan-v1', 0, params)
    for value in result.values():
        value.flags.writeable = False
    return {'identity': plan_identity.record(), 'identity_sha256': plan_identity.sha256, 'status': 'diagnostic_not_publishable', 'arrays': result}

def _blocked_contact(cell, arrays, shape):
    row, column = divmod(int(cell), shape[1])
    blocked = ~arrays['valid_mask'] | arrays['protected_mask']
    if row in (0, shape[0] - 1) or column in (0, shape[1] - 1):
        return True
    return bool(blocked[row - 1:row + 2, column - 1:column + 2].any() or arrays['open_boundary_mask'][row, column])

def _reject_crossings(nodes, edges, positions, bucket_size):
    index = {int(cell): place for place, cell in enumerate(nodes)}
    buckets = {}
    for edge_index, (donor, downstream) in enumerate(edges):
        first, second = (positions[index[int(donor)]], positions[index[int(downstream)]])
        x0, x1 = (_i45_math.floor(min(first[0], second[0]) / bucket_size), _i45_math.floor(max(first[0], second[0]) / bucket_size))
        z0, z1 = (_i45_math.floor(min(first[1], second[1]) / bucket_size), _i45_math.floor(max(first[1], second[1]) / bucket_size))
        nearby = set()
        for column in range(x0, x1 + 1):
            for row in range(z0, z1 + 1):
                nearby.update(buckets.get((column, row), ()))
        for other_index in nearby:
            other_donor, other_downstream = edges[other_index]
            if {int(donor), int(downstream)} & {int(other_donor), int(other_downstream)}:
                continue
            if _segments_cross(first, second, positions[index[int(other_donor)]], positions[index[int(other_downstream)]]):
                raise ValueError('channel centerline self-intersects')
        for column in range(x0, x1 + 1):
            for row in range(z0, z1 + 1):
                buckets.setdefault((column, row), []).append(edge_index)

def _make_centerline(plan, network, recipe):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i45_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i45_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i45_digest
    arrays = network['arrays']
    line = build_centerline(plan, SmoothingRecipe(recipe.smoothing_strength, recipe.max_offset_m))
    values = {name: value.copy() for name, value in line['arrays'].items()}
    nodes = values['node_flat_index']
    shape = arrays['source_height_m'].shape
    anchored = _i45_np.array([_blocked_contact(cell, arrays, shape) for cell in nodes])
    anchored |= values['anchor_mask']
    values['node_world_xz_m'][anchored] = values['original_world_xz_m'][anchored]
    positions = values['node_world_xz_m']
    index = {int(cell): place for place, cell in enumerate(nodes)}
    edges = _i45_np.asarray(arrays['edge_cell_ids'])
    for donor, downstream in edges:
        first, second = (positions[index[int(donor)]], positions[index[int(downstream)]])
        if _i45_np.linalg.norm(first - second) <= 1e-09:
            raise ValueError('zero-length channel edge')
        for fraction in _i45_np.linspace(0.0, 1.0, 9):
            x, z = first * (1 - fraction) + second * fraction
            column = int(round((x - plan['identity']['parameters']['origin_x_m']) / plan['identity']['parameters']['spacing_x_m']))
            row = int(round((z - plan['identity']['parameters']['origin_z_m']) / plan['identity']['parameters']['spacing_z_m']))
            if row < 0 or column < 0 or row >= shape[0] or (column >= shape[1]) or (not arrays['valid_mask'][row, column]) or arrays['protected_mask'][row, column]:
                raise ValueError('channel crosses protected or unknown gap')
        if values['node_bed_m'][index[int(donor)]] - values['node_bed_m'][index[int(downstream)]] + 1e-09 < recipe.min_bed_slope_m_per_m * _i45_np.linalg.norm(first - second):
            raise ValueError('smoothed channel reverses bed slope')
    _reject_crossings(nodes, edges, positions, plan['identity']['parameters']['spacing_x_m'])
    parameters = plan['identity']['parameters']
    values['local_budget_failed_mask'] = _i45_np.array([_sample_height(plan['arrays']['source_height_m'], position, parameters) - bed > recipe.max_cut_m + 1e-09 for position, bed in zip(positions, values['node_bed_m'])], bool)
    values['slope_failed_donor_mask'] = _i45_np.zeros(len(nodes), bool)
    line_parameters = dict(line['identity']['parameters'])
    line_parameters['result_geometry_sha256'] = _i45_digest({name: _i45_array_hash(_i45_np.ascontiguousarray(value)) for name, value in values.items()})
    line_identity = _i45_ArtifactIdentity('Terragenesis', 'channel-centerline', 'channel-centerline-v1', 0, line_parameters)
    for value in values.values():
        value.flags.writeable = False
    adjusted = {'identity': line_identity.record(), 'identity_sha256': line_identity.sha256, 'status': 'diagnostic_not_publishable', 'arrays': values}
    validate_centerline_for_plan(adjusted, plan)
    return (adjusted, anchored)

def build_natural_channel_geometry(network, recipe=NaturalGeometryRecipe()):
    """Build shared node bed and centerline from a validated natural network."""
    from terrain_pipeline.common_infra import identity as _i45_identity
    from terrain_pipeline.common_infra import readonly as _i45_readonly
    if not isinstance(recipe, NaturalGeometryRecipe):
        raise ValueError('natural geometry recipe required')
    arrays, metadata = _network_fields(network)
    plan = _make_plan(network, recipe)
    centerline, anchored = _make_centerline(plan, network, recipe)
    nodes = arrays['node_cell_ids']
    edges = arrays['edge_cell_ids']
    plan_arrays = plan['arrays']
    line_arrays = centerline['arrays']
    node_index = {int(cell): index for index, cell in enumerate(nodes)}
    edge_slope_failed = _i45_np.array([plan_arrays['failed_slope_edge_donor_mask'].flat[donor] for donor, _ in edges], bool)
    geometry_arrays = {'node_cell_ids': nodes.copy(), 'edge_cell_ids': edges.copy(), 'node_world_xz_m': line_arrays['node_world_xz_m'].copy(), 'node_native_xz_m': line_arrays['original_world_xz_m'].copy(), 'node_bed_m': line_arrays['node_bed_m'].copy(), 'node_width_m': line_arrays['node_width_m'].copy(), 'node_depth_m': _i45_np.asarray(arrays['node_depth_m']).copy(), 'node_representative_q_m3_s': _i45_np.asarray(arrays['node_representative_q_m3_s']).copy(), 'node_anchor_mask': anchored, 'edge_requires_refinement': _i45_np.asarray(arrays['edge_requires_refinement']).copy(), 'node_over_budget_mask': line_arrays['local_budget_failed_mask'].copy(), 'edge_slope_failed_mask': edge_slope_failed, 'source_height_m': plan_arrays['source_height_m'].copy(), 'valid_mask': _i45_np.asarray(arrays['valid_mask']).copy(), 'protected_mask': _i45_np.asarray(arrays['protected_mask']).copy(), 'open_boundary_mask': _i45_np.asarray(arrays['open_boundary_mask']).copy(), 'bounded_bed_m': plan_arrays['bounded_bed_m'].copy(), 'required_cut_m': plan_arrays['required_cut_m'].copy()}
    geometry_arrays['node_world_xyz_m'] = _i45_np.column_stack((geometry_arrays['node_world_xz_m'][:, 0], geometry_arrays['node_bed_m'], geometry_arrays['node_world_xz_m'][:, 1]))
    edge_centers = _i45_np.empty((len(edges), 2, 3), _i45_np.float64)
    edge_sections = _i45_np.empty((len(edges), 6, 3), _i45_np.float64)
    source_flat = geometry_arrays['source_height_m'].ravel()
    for edge_index, (donor, downstream) in enumerate(edges):
        endpoint_indices = (node_index[int(donor)], node_index[int(downstream)])
        edge_centers[edge_index] = geometry_arrays['node_world_xyz_m'][list(endpoint_indices)]
        direction = edge_centers[edge_index, 1, [0, 2]] - edge_centers[edge_index, 0, [0, 2]]
        direction /= _i45_np.linalg.norm(direction)
        normal = _i45_np.array([-direction[1], direction[0]])
        for endpoint, (cell, node_index_value) in enumerate(zip((donor, downstream), endpoint_indices)):
            center = edge_centers[edge_index, endpoint]
            bank = _i45_np.array([center[0], source_flat[cell], center[2]])
            half_width = geometry_arrays['node_width_m'][node_index_value] / 2
            left, right = (bank.copy(), bank.copy())
            left[[0, 2]] -= normal * half_width
            right[[0, 2]] += normal * half_width
            edge_sections[edge_index, endpoint * 3:endpoint * 3 + 3] = (left, center, right)
    geometry_arrays['edge_centerline_xyz_m'] = edge_centers
    geometry_arrays['edge_sections_xyz_m'] = edge_sections
    summary = {'node_count': len(nodes), 'edge_count': len(edges), 'moved_nodes': int(_i45_np.count_nonzero(_i45_np.linalg.norm(geometry_arrays['node_world_xz_m'] - geometry_arrays['node_native_xz_m'], axis=1) > 1e-09)), 'over_budget_nodes': int(geometry_arrays['node_over_budget_mask'].sum()), 'native_plan_over_budget_nodes': int(plan_arrays['over_budget_mask'].ravel()[nodes].sum()), 'failed_slope_edges': int(edge_slope_failed.sum()), 'needs_refinement_edges': int(geometry_arrays['edge_requires_refinement'].sum()), 'diagnostic_failure': bool(geometry_arrays['node_over_budget_mask'].any() or edge_slope_failed.any())}
    result_metadata = {'schema': TD_NATURAL_CHANNEL_GEOMETRY_SCHEMA, 'algorithm': TD_NATURAL_CHANNEL_GEOMETRY_SCHEMA, 'status': 'diagnostic_failure' if summary['diagnostic_failure'] else 'diagnostic_not_publishable', 'network_identity_sha256': network['identity_sha256'], 'grid_shape': list(metadata['grid_shape']), 'spacing_m': float(metadata['spacing_m']), 'origin_m_xz': list(metadata['origin_m_xz']), 'recipe': _i45_asdict(recipe), 'plan_parameters': plan['identity']['parameters'], 'plan_identity_sha256': plan['identity_sha256'], 'centerline_identity_sha256': centerline['identity_sha256'], 'summary': summary, 'coordinates': 'arrays [z,x]; world XYZ metres', **{flag: False for flag in FLAGS}}
    result = {'arrays': {name: _i45_readonly(value) for name, value in geometry_arrays.items()}, 'metadata': result_metadata}
    result['identity_sha256'] = _i45_identity(result['arrays'], result_metadata)
    validate_natural_channel_geometry(result)
    return result

def validate_natural_channel_geometry(geometry):
    """Validate stored geometry without rebuilding its source network."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i45_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i45_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i45_digest
    from terrain_pipeline.common_infra import identity as _i45_identity
    arrays, metadata = (geometry['arrays'], geometry['metadata'])
    if metadata.get('schema') != TD_NATURAL_CHANNEL_GEOMETRY_SCHEMA or metadata.get('algorithm') != TD_NATURAL_CHANNEL_GEOMETRY_SCHEMA or set(arrays) != ARRAY_NAMES or any((metadata.get(flag) is not False for flag in FLAGS)) or (geometry.get('identity_sha256') != _i45_identity(arrays, metadata)):
        raise ValueError('natural geometry identity/schema invalid')
    shape = tuple(metadata['grid_shape'])
    if len(shape) != 2 or min(shape) < 2 or shape[0] * shape[1] > 250000 or any((arrays[name].shape != shape for name in ('source_height_m', 'valid_mask', 'protected_mask', 'open_boundary_mask', 'bounded_bed_m', 'required_cut_m'))):
        raise ValueError('natural geometry grid invalid')
    nodes, edges = (arrays['node_cell_ids'], arrays['edge_cell_ids'])
    if nodes.dtype != _i45_np.int64 or edges.dtype != _i45_np.int64 or edges.shape != (len(edges), 2) or (not _i45_np.array_equal(nodes, _i45_np.unique(nodes))) or (not _i45_np.array_equal(nodes, _i45_np.unique(edges))) or _i45_np.any(nodes < 0) or _i45_np.any(nodes >= _i45_math.prod(shape)) or (len(set((int(cell) for cell in edges[:, 0]))) != len(edges)):
        raise ValueError('natural geometry graph invalid')
    count = len(nodes)
    for name in ('node_world_xz_m', 'node_native_xz_m'):
        if arrays[name].shape != (count, 2) or arrays[name].dtype != _i45_np.float64:
            raise ValueError('natural geometry position invalid')
    if arrays['node_world_xyz_m'].shape != (count, 3) or arrays['edge_centerline_xyz_m'].shape != (len(edges), 2, 3) or arrays['edge_sections_xyz_m'].shape != (len(edges), 6, 3) or any((arrays[name].dtype != _i45_np.float64 or not _i45_np.isfinite(arrays[name]).all() for name in ('node_world_xyz_m', 'edge_centerline_xyz_m', 'edge_sections_xyz_m'))):
        raise ValueError('natural geometry XYZ arrays invalid')
    for name in ('node_bed_m', 'node_width_m', 'node_depth_m', 'node_representative_q_m3_s'):
        if arrays[name].shape != (count,) or arrays[name].dtype != _i45_np.float64 or (not _i45_np.isfinite(arrays[name]).all()):
            raise ValueError('natural geometry node metric invalid')
    for name, length in (('node_anchor_mask', count), ('node_over_budget_mask', count), ('edge_requires_refinement', len(edges)), ('edge_slope_failed_mask', len(edges))):
        if arrays[name].shape != (length,) or arrays[name].dtype != bool:
            raise ValueError('natural geometry diagnostic mask invalid')
    if any((arrays[name].dtype != bool for name in ('valid_mask', 'protected_mask', 'open_boundary_mask'))) or any((arrays[name].dtype != _i45_np.float64 or not _i45_np.isfinite(arrays[name]).all() for name in ('source_height_m', 'bounded_bed_m', 'required_cut_m'))):
        raise ValueError('natural geometry terrain invalid')
    if _i45_np.any(arrays['node_width_m'] <= 0) or _i45_np.any(arrays['node_depth_m'] <= 0) or _i45_np.any(arrays['node_representative_q_m3_s'] <= 0) or _i45_np.any(arrays['protected_mask'].ravel()[nodes]) or _i45_np.any(~arrays['valid_mask'].ravel()[nodes]):
        raise ValueError('natural geometry node constraints invalid')
    max_cut = metadata['recipe']['max_cut_m']
    inactive = _i45_np.ones(_i45_math.prod(shape), bool)
    inactive[nodes] = False
    if _i45_np.any(arrays['required_cut_m'].ravel()[inactive] != 0) or _i45_np.any(arrays['required_cut_m'].ravel()[nodes] + 1e-09 < arrays['node_depth_m']) or (not _i45_np.allclose(arrays['bounded_bed_m'], arrays['source_height_m'] - _i45_np.minimum(arrays['required_cut_m'], max_cut), atol=1e-09, rtol=0)) or (not _i45_np.allclose(arrays['node_bed_m'], arrays['source_height_m'].ravel()[nodes] - arrays['required_cut_m'].ravel()[nodes], atol=1e-09, rtol=0)):
        raise ValueError('natural geometry bed/cut ledger invalid')
    plan_parameters = metadata['plan_parameters']
    if plan_parameters['source_height_sha256'] != _i45_array_hash(_i45_np.ascontiguousarray(arrays['source_height_m'])) or plan_parameters['natural_network_identity_sha256'] != metadata['network_identity_sha256'] or _i45_ArtifactIdentity('Terragenesis', 'metric-channel-plan', 'metric-channel-plan-v1', 0, plan_parameters).sha256 != metadata['plan_identity_sha256']:
        raise ValueError('natural geometry source plan identity invalid')
    nominal_width = _i45_np.zeros(shape, _i45_np.float64)
    nominal_depth = _i45_np.zeros(shape, _i45_np.float64)
    nominal_width.ravel()[nodes] = arrays['node_width_m']
    nominal_depth.ravel()[nodes] = arrays['node_depth_m']
    target_bed = arrays['source_height_m'] - arrays['required_cut_m']
    geometry_hash = _i45_digest({name: _i45_array_hash(_i45_np.ascontiguousarray(value)) for name, value in (('nominal_width_m', nominal_width), ('nominal_depth_m', nominal_depth), ('target_bed_m', target_bed), ('bounded_bed_m', arrays['bounded_bed_m']))})
    if geometry_hash != plan_parameters['natural_geometry_sha256']:
        raise ValueError('natural geometry plan metrics differ from identity')
    spacing = metadata['spacing_m']
    origin_x, origin_z = metadata['origin_m_xz']
    expected = _i45_np.column_stack((origin_x + nodes % shape[1] * spacing, origin_z + nodes // shape[1] * spacing))
    if not _i45_np.allclose(arrays['node_native_xz_m'], expected, atol=1e-08, rtol=0) or not _i45_np.array_equal(arrays['node_world_xz_m'][arrays['node_anchor_mask']], arrays['node_native_xz_m'][arrays['node_anchor_mask']]):
        raise ValueError('natural geometry anchor mismatch')
    index = {int(cell): position for position, cell in enumerate(nodes)}
    donor_count = _i45_np.bincount(edges[:, 1], minlength=_i45_math.prod(shape))
    outgoing = set((int(cell) for cell in edges[:, 0]))
    expected_anchors = _i45_np.array([donor_count[cell] != 1 or int(cell) not in outgoing or _blocked_contact(cell, arrays, shape) for cell in nodes], bool)
    if not _i45_np.array_equal(arrays['node_anchor_mask'], expected_anchors):
        raise ValueError('natural geometry graph/protection anchors invalid')
    expected_xyz = _i45_np.column_stack((arrays['node_world_xz_m'][:, 0], arrays['node_bed_m'], arrays['node_world_xz_m'][:, 1]))
    if not _i45_np.array_equal(arrays['node_world_xyz_m'], expected_xyz):
        raise ValueError('natural geometry shared node bed mismatch')
    _reject_crossings(nodes, edges, arrays['node_world_xz_m'], spacing)
    slope = NaturalGeometryRecipe(**metadata['recipe']).min_bed_slope_m_per_m
    params = {'origin_x_m': origin_x, 'origin_z_m': origin_z, 'spacing_x_m': spacing, 'spacing_z_m': spacing}
    budget = _i45_np.array([_sample_height(arrays['source_height_m'], point, params) - bed > max_cut + 1e-09 for point, bed in zip(arrays['node_world_xz_m'], arrays['node_bed_m'])], bool)
    if not _i45_np.array_equal(budget, arrays['node_over_budget_mask']):
        raise ValueError('natural geometry moved-node budget mismatch')
    for edge_index, (donor, target) in enumerate(edges):
        first, second = (index[int(donor)], index[int(target)])
        if not _i45_np.array_equal(arrays['edge_centerline_xyz_m'][edge_index], arrays['node_world_xyz_m'][[first, second]]) or not _i45_np.array_equal(arrays['edge_sections_xyz_m'][edge_index, (1, 4)], arrays['node_world_xyz_m'][[first, second]]):
            raise ValueError('natural geometry edge does not share node bed')
        start, end = arrays['node_world_xyz_m'][[first, second]]
        horizontal = end[[0, 2]] - start[[0, 2]]
        horizontal /= _i45_np.linalg.norm(horizontal)
        normal = _i45_np.array([-horizontal[1], horizontal[0]])
        for endpoint, (cell, node_position) in enumerate(((donor, first), (target, second))):
            bank = _i45_np.array([arrays['node_world_xyz_m'][node_position, 0], arrays['source_height_m'].ravel()[cell], arrays['node_world_xyz_m'][node_position, 2]])
            half_width = arrays['node_width_m'][node_position] / 2
            for side, sign in ((0, -1), (2, 1)):
                expected_bank = bank.copy()
                expected_bank[[0, 2]] += sign * normal * half_width
                if not _i45_np.array_equal(arrays['edge_sections_xyz_m'][edge_index, endpoint * 3 + side], expected_bank):
                    raise ValueError('natural geometry bank section differs from node width')
        distance = _i45_np.linalg.norm(arrays['node_world_xz_m'][first] - arrays['node_world_xz_m'][second])
        if distance <= 0 or arrays['node_bed_m'][first] - arrays['node_bed_m'][second] + 1e-09 < slope * distance:
            raise ValueError('natural geometry edge reverses slope')
        bounded = arrays['bounded_bed_m'].ravel()
        failed = bounded[target] > bounded[donor] - slope * spacing + 1e-09
        if failed != arrays['edge_slope_failed_mask'][edge_index]:
            raise ValueError('natural geometry bounded slope diagnostic mismatch')
    if _i45_np.any(arrays['bounded_bed_m'] > arrays['source_height_m'] + 1e-09) or _i45_np.any(arrays['required_cut_m'] < -1e-09) or metadata['summary']['edge_count'] != len(edges) or (metadata['summary']['over_budget_nodes'] != int(budget.sum())) or (metadata['summary']['failed_slope_edges'] != int(arrays['edge_slope_failed_mask'].sum())) or (metadata['summary']['diagnostic_failure'] != bool(budget.any() or arrays['edge_slope_failed_mask'].any())):
        raise ValueError('natural geometry budget summary invalid')
    if metadata['status'] != ('diagnostic_failure' if metadata['summary']['diagnostic_failure'] else 'diagnostic_not_publishable'):
        raise ValueError('natural geometry status invalid')
    return True

def save_natural_channel_geometry(path, geometry):
    from terrain_pipeline.common_infra import save_bundle as _i45_save_bundle
    _i45_save_bundle(path, geometry, validator=validate_natural_channel_geometry)

def load_natural_channel_geometry(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _i45_load_bundle
    result = _i45_load_bundle(path, expected_sha256=expected_sha256, validator=validate_natural_channel_geometry)
    if result['identity_sha256'] != expected_identity:
        raise ValueError('natural geometry external identity mismatch')
    return result

def evaluate_natural_channel_window(geometry, network, *, window_origin_m_xz, spacing_m, shape_zx, recipe=None):
    """Sweep shared centerline sections into one bounded refinement window."""
    from terrain_pipeline.artifacts.contracts import array_hash as _i45_array_hash
    from terrain_pipeline.common_infra import identity as _i45_identity
    from terrain_pipeline.common_infra import readonly as _i45_readonly
    validate_natural_channel_geometry(geometry)
    arrays, _ = _network_fields(network)
    if geometry['metadata']['network_identity_sha256'] != network['identity_sha256']:
        raise ValueError('geometry and network identity mismatch')
    settings = NaturalGeometryRecipe(**geometry['metadata']['recipe'])
    if recipe is not None and recipe != settings:
        raise ValueError('window recipe must match shared geometry')
    if len(shape_zx) != 2 or any((type(size) is not int or size < 2 for size in shape_zx)) or _i45_math.prod(shape_zx) > 250000 or (not _i45_math.isfinite(spacing_m)) or (spacing_m <= 0) or (max(((size - 1) * spacing_m for size in shape_zx)) > settings.max_window_span_m):
        raise ValueError('window exceeds bounded refinement policy')
    plan = _make_plan(network, settings)
    centerline, _ = _make_centerline(plan, network, settings)
    if centerline['identity_sha256'] != geometry['metadata']['centerline_identity_sha256']:
        raise ValueError('stored geometry differs from rebuilt centerline')
    origin_x, origin_z = window_origin_m_xz
    source_origin_x, source_origin_z = geometry['metadata']['origin_m_xz']
    coarse_spacing = geometry['metadata']['spacing_m']
    x = origin_x + _i45_np.arange(shape_zx[1]) * spacing_m
    z = origin_z + _i45_np.arange(shape_zx[0]) * spacing_m
    fine_columns = (x - source_origin_x) / coarse_spacing
    fine_rows = (z - source_origin_z) / coarse_spacing
    if fine_columns.min() < -1e-09 or fine_rows.min() < -1e-09 or fine_columns.max() > arrays['valid_mask'].shape[1] - 1 + 1e-09 or (fine_rows.max() > arrays['valid_mask'].shape[0] - 1 + 1e-09):
        raise ValueError('window exceeds source domain')
    column_low = _i45_np.floor(_i45_np.clip(fine_columns, 0, arrays['valid_mask'].shape[1] - 1)).astype(int)
    row_low = _i45_np.floor(_i45_np.clip(fine_rows, 0, arrays['valid_mask'].shape[0] - 1)).astype(int)
    column_high = _i45_np.ceil(_i45_np.clip(fine_columns - 1e-12, 0, arrays['valid_mask'].shape[1] - 1)).astype(int)
    row_high = _i45_np.ceil(_i45_np.clip(fine_rows - 1e-12, 0, arrays['valid_mask'].shape[0] - 1)).astype(int)
    protected = _i45_np.zeros(tuple(shape_zx), bool)
    unknown = _i45_np.zeros(tuple(shape_zx), bool)
    for row_ids in (row_low, row_high):
        for column_ids in (column_low, column_high):
            protected |= arrays['protected_mask'][_i45_np.ix_(row_ids, column_ids)]
            unknown |= ~arrays['valid_mask'][_i45_np.ix_(row_ids, column_ids)]
    blocked = protected | unknown
    section = evaluate_sections(plan, float(origin_x), float(origin_z), float(spacing_m), float(spacing_m), tuple(shape_zx), blocked, SectionRecipe(settings.max_cut_m, settings.min_cells_across_width), centerline=centerline)
    output_arrays = {**section['arrays'], 'unknown_mask': _i45_readonly(unknown)}
    output_metadata = {'schema': WINDOW_SCHEMA, 'algorithm': WINDOW_SCHEMA, 'geometry_identity_sha256': geometry['identity_sha256'], 'network_identity_sha256': network['identity_sha256'], 'section_identity_sha256': section['identity_sha256'], 'source_surface_sha256': _i45_array_hash(section['arrays']['source_surface_m']), 'required_cut_sha256': _i45_array_hash(section['arrays']['required_cut_m']), 'origin_m_xz': [float(origin_x), float(origin_z)], 'spacing_m': float(spacing_m), 'shape_zx': list(shape_zx), 'max_cut_m': settings.max_cut_m, 'summary': {**section['summary'], 'blocked_by_protection_or_unknown': bool(_i45_np.any(section['arrays']['protected_conflict_mask'])), 'trapezoid_cut_volume_m3': section['summary']['actual_cut_volume_m3']}, **{flag: False for flag in FLAGS}}
    output_metadata['status'] = 'diagnostic_failure' if geometry['metadata']['summary']['diagnostic_failure'] or section['summary']['blocked_by_plan'] or section['summary']['blocked_by_centerline'] or output_metadata['summary']['blocked_by_protection_or_unknown'] or section['summary']['requires_shared_fine_extension'] or (section['summary']['needs_refinement_nodes'] > 0) else 'diagnostic_not_publishable'
    output = {'arrays': {name: _i45_readonly(value) for name, value in output_arrays.items()}, 'metadata': output_metadata}
    output['identity_sha256'] = _i45_identity(output['arrays'], output_metadata)
    validate_natural_channel_window(output)
    return output

def validate_natural_channel_window(window):
    from terrain_pipeline.artifacts.contracts import array_hash as _i45_array_hash
    from terrain_pipeline.common_infra import identity as _i45_identity
    arrays, metadata = (window['arrays'], window['metadata'])
    expected = {'source_surface_m', 'required_cut_m', 'bounded_surface_m', 'actual_cut_m', 'over_budget_mask', 'protected_mask', 'protected_conflict_mask', 'clipped_boundary_mask', 'needs_refinement_mask', 'unknown_mask'}
    if metadata.get('schema') != WINDOW_SCHEMA or metadata.get('algorithm') != WINDOW_SCHEMA or set(arrays) != expected or any((metadata.get(flag) is not False for flag in FLAGS)) or (window.get('identity_sha256') != _i45_identity(arrays, metadata)):
        raise ValueError('natural window identity/schema invalid')
    shape = tuple(metadata['shape_zx'])
    if len(shape) != 2 or min(shape) < 2 or _i45_math.prod(shape) > 250000 or any((value.shape != shape for value in arrays.values())):
        raise ValueError('natural window shape invalid')
    for name in ('source_surface_m', 'required_cut_m', 'bounded_surface_m', 'actual_cut_m'):
        if arrays[name].dtype != _i45_np.float64 or not _i45_np.isfinite(arrays[name]).all():
            raise ValueError('natural window elevation/cut invalid')
    for name in expected - {'source_surface_m', 'required_cut_m', 'bounded_surface_m', 'actual_cut_m'}:
        if arrays[name].dtype != bool:
            raise ValueError('natural window mask invalid')
    if not _i45_np.allclose(arrays['bounded_surface_m'], arrays['source_surface_m'] - arrays['actual_cut_m'], atol=1e-09, rtol=0) or _i45_np.any(arrays['actual_cut_m'] < 0) or _i45_np.any(arrays['actual_cut_m'] - arrays['required_cut_m'] > 1e-09) or _i45_np.any(arrays['actual_cut_m'][arrays['protected_mask']] != 0) or _i45_np.any(arrays['unknown_mask'] & ~arrays['protected_mask']):
        raise ValueError('natural window material ledger invalid')
    cap = metadata['max_cut_m']
    if not _i45_math.isfinite(cap) or cap < 0:
        raise ValueError('natural window cut cap invalid')
    expected_actual = _i45_np.minimum(arrays['required_cut_m'], cap).copy()
    expected_actual[arrays['protected_mask']] = 0.0
    boundary = _i45_np.zeros(shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    if not _i45_np.allclose(arrays['actual_cut_m'], expected_actual, atol=1e-09, rtol=0) or not _i45_np.array_equal(arrays['over_budget_mask'], arrays['required_cut_m'] > cap + 1e-09) or (not _i45_np.array_equal(arrays['protected_conflict_mask'], arrays['protected_mask'] & (arrays['required_cut_m'] > 1e-09))) or (not _i45_np.array_equal(arrays['clipped_boundary_mask'], boundary & (arrays['required_cut_m'] > 1e-09))):
        raise ValueError('natural window cut diagnostics invalid')
    if metadata['source_surface_sha256'] != _i45_array_hash(arrays['source_surface_m']) or metadata['required_cut_sha256'] != _i45_array_hash(arrays['required_cut_m']):
        raise ValueError('natural window source/cut identity mismatch')
    spacing = metadata['spacing_m']
    if not _i45_math.isfinite(spacing) or spacing <= 0:
        raise ValueError('natural window spacing invalid')
    weights = _i45_np.ones(shape)
    weights[[0, -1], :] *= 0.5
    weights[:, [0, -1]] *= 0.5
    volume = float(_i45_np.sum(arrays['actual_cut_m'] * weights) * spacing ** 2)
    if not _i45_math.isclose(volume, metadata['summary']['trapezoid_cut_volume_m3'], abs_tol=1e-07):
        raise ValueError('natural window trapezoid ledger mismatch')
    return True

def save_natural_channel_window(path, window):
    from terrain_pipeline.common_infra import save_bundle as _i45_save_bundle
    _i45_save_bundle(path, window, validator=validate_natural_channel_window)

def load_natural_channel_window(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _i45_load_bundle
    result = _i45_load_bundle(path, expected_sha256=expected_sha256, validator=validate_natural_channel_window)
    if result['identity_sha256'] != expected_identity:
        raise ValueError('natural window external identity mismatch')
    return result
TD_SOURCE_CONFORMING_BANKS_SCHEMA = 'td-source-conforming-banks-v2'
TD_SOURCE_CONFORMING_BANKS_ALGORITHM = 'native-bilinear-minus-shared-knot-affine-depth-fan-v2'
TD_SOURCE_CONFORMING_BANKS_FLAGS = ('hydraulic_ready', 'hydraulic_solved', 'natural_outlet_certified', 'publish_ready', 'full_river_verified', 'cross_domain_verified', 'vdm_verified', 'bed_changed', 'water_generated', 'full_watershed_fine_verified', 'cross_shard_hydraulics_verified')
MAX_RSS = 1024 ** 3
MAX_FILES = 4096
MAX_SAMPLE_CACHE = 65536
MAX_PATCH_CACHE = 8192
GEOMETRY_TOLERANCE_M = 1e-08
FUNCTION_TOLERANCE_M = 1e-09

def _json_fragments(record):
    encoder = _i46_json.JSONEncoder(sort_keys=True, allow_nan=False, separators=(',', ':'))
    for fragment in encoder.iterencode(record):
        yield fragment.encode('utf-8')

def _record_identity(record):
    digest = _i46_hashlib.sha256()
    for fragment in _json_fragments(record):
        digest.update(fragment)
    return digest.hexdigest()

def _record_bytes(record):
    return sum((len(fragment) for fragment in _json_fragments(record)))

def _write_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle:
        for fragment in _json_fragments(record):
            handle.write(fragment)

def _seal(record):
    record['identity_sha256'] = _record_identity(record)
    return record

def _check_identity(record):
    if record.get('identity_sha256') != _record_identity({key: value for key, value in record.items() if key != 'identity_sha256'}):
        raise ValueError('source-conforming content identity mismatch')

def _rss_guard(callback=None, *, phase=None, counters=None):
    if callback is not None:
        if phase is not None and hasattr(callback, '__dict__'):
            callback.phase = phase
            callback.counters = counters or {}
        callback()
    memory = _i46_psutil.Process().memory_info()
    if max(memory.rss, getattr(memory, 'peak_wset', 0)) > MAX_RSS:
        raise MemoryError('source-conforming hard 1GiB peak RSS exceeded')

def _source_sample(context, x_m, z_m):
    from terrain_pipeline.td_fine_bed_raster import _sample as _i46__sample
    cache = context.setdefault('bank_sample_cache', _i46_OrderedDict())
    key = (x_m, z_m)
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    value = _i46__sample(context, x_m, z_m)
    cache[key] = value
    if len(cache) > MAX_SAMPLE_CACHE:
        cache.popitem(last=False)
    return value

def _line_key(points):
    first, second = (_i46_np.asarray(points[0], float), _i46_np.asarray(points[1], float))
    direction = second - first
    length = float(_i46_np.linalg.norm(direction))
    if length <= GEOMETRY_TOLERANCE_M:
        raise ValueError('degenerate projected edge')
    direction /= length
    if direction[0] < -1e-12 or (abs(direction[0]) <= 1e-12 and direction[1] < 0):
        direction *= -1
    normal = _i46_np.array([-direction[1], direction[0]])
    offset = float(normal @ first)
    return (round(float(direction[0]), 10), round(float(direction[1]), 10), round(offset, 7))

def _edge_record(triangle, edge_index):
    points = _i46_np.asarray(triangle['vertices_xyz_m'], float)
    first, second = (points[edge_index], points[(edge_index + 1) % 3])
    return {'triangle_id': triangle['triangle_id'], 'edge_index': edge_index, 'points_xyz_m': [first.tolist(), second.tolist()]}

def _interval(edge, anchor, direction):
    points = _i46_np.asarray(edge['points_xyz_m'], float)[:, [0, 2]]
    delta = points - anchor
    distance = _i46_np.abs(delta[:, 0] * direction[1] - delta[:, 1] * direction[0])
    if _i46_np.max(distance) > GEOMETRY_TOLERANCE_M:
        raise ValueError('rounded edge key is not a verified common line')
    coordinates = delta @ direction
    return (float(min(coordinates)), float(max(coordinates)))

def _edge_y(edge, point):
    vertices = _i46_np.asarray(edge['points_xyz_m'], float)
    vector = vertices[1, [0, 2]] - vertices[0, [0, 2]]
    fraction = float((point - vertices[0, [0, 2]]) @ vector / (vector @ vector))
    return float(vertices[0, 1] + fraction * (vertices[1, 1] - vertices[0, 1]))

def _native_patch(context, point):
    position = (_i46_np.asarray(point) - context['origin']) / context['spacing']
    rows, columns = context['height'].shape
    if not (0 <= position[0] <= columns - 1 and 0 <= position[1] <= rows - 1):
        raise ValueError('outside_native_dem')
    column = min(int(_i46_math.floor(position[0])), columns - 2)
    row = min(int(_i46_math.floor(position[1])), rows - 2)
    cache = context.setdefault('bank_patch_cache', _i46_OrderedDict())
    key = (row, column)
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    values = [float(context['height'][row + vertical, column + horizontal]) for vertical, horizontal in ((0, 0), (0, 1), (1, 0), (1, 1))]
    if not all((_i46_math.isfinite(value) for value in values)):
        raise ValueError('nonfinite_native_height')
    coefficients = [values[0], values[1] - values[0], values[2] - values[0], values[3] - values[2] - values[1] + values[0]]
    patch = {'patch_row_column': [row, column], 'native_cell_ids': [row * columns + column, row * columns + column + 1, (row + 1) * columns + column, (row + 1) * columns + column + 1], 'native_height_m': values, 'bilinear_coefficients_m': coefficients, 'patch_origin_m_xz': (context['origin'] + _i46_np.array([column, row]) * context['spacing']).tolist(), 'native_spacing_m': context['spacing']}
    cache[key] = patch
    if len(cache) > MAX_PATCH_CACHE:
        cache.popitem(last=False)
    return patch

def source_segment_polynomial(context, start_xz, end_xz):
    """Coefficients in normalized t in [0,1]; a diagonal can be quadratic."""
    start, end = (_i46_np.asarray(start_xz, float), _i46_np.asarray(end_xz, float))
    patch = _native_patch(context, (start + end) / 2)
    native_origin, spacing = (_i46_np.asarray(patch['patch_origin_m_xz']), patch['native_spacing_m'])
    horizontal, vertical = (start - native_origin) / spacing
    delta_horizontal, delta_vertical = (end - start) / spacing
    constant, horizontal_term, vertical_term, mixed = patch['bilinear_coefficients_m']
    coefficients = [constant + horizontal_term * horizontal + vertical_term * vertical + mixed * horizontal * vertical, horizontal_term * delta_horizontal + vertical_term * delta_vertical + mixed * (horizontal * delta_vertical + vertical * delta_horizontal), mixed * delta_horizontal * delta_vertical]
    return {**patch, 'source_coefficients_m_t012': [float(value) for value in coefficients]}

def _iter_segments(groups, context):
    segment_number = 0
    for group_key in sorted(groups):
        edges = groups[group_key]
        anchor = _i46_np.asarray(edges[0]['points_xyz_m'][0], float)[[0, 2]]
        direction = _i46_np.asarray(edges[0]['points_xyz_m'][1], float)[[0, 2]] - anchor
        direction /= _i46_np.linalg.norm(direction)
        if direction[0] < -1e-12 or (abs(direction[0]) <= 1e-12 and direction[1] < 0):
            direction *= -1
        intervals = [_interval(edge, anchor, direction) for edge in edges]
        minimum, maximum = (min((pair[0] for pair in intervals)), max((pair[1] for pair in intervals)))
        knots = [value for pair in intervals for value in pair]
        endpoint_records = []
        for edge in edges:
            for vertex in edge['points_xyz_m']:
                coordinate = float((_i46_np.asarray(vertex)[[0, 2]] - anchor) @ direction)
                endpoint_records.append((coordinate, {'triangle_id': edge['triangle_id'], 'edge_index': edge['edge_index'], 'xyz_m': vertex}))
        mesh_knots = []
        for coordinate, reference in sorted(endpoint_records, key=lambda pair: pair[0]):
            if not mesh_knots or coordinate - mesh_knots[-1]['coordinate_m'] > GEOMETRY_TOLERANCE_M:
                mesh_knots.append({'coordinate_m': coordinate, 'xz_m': (anchor + coordinate * direction).tolist(), 'original_vertex_refs': []})
            mesh_knots[-1]['original_vertex_refs'].append(reference)
        mesh_coordinates = [knot['coordinate_m'] for knot in mesh_knots]
        for axis in range(2):
            if abs(direction[axis]) < 1e-12:
                continue
            ends = [float((anchor + value * direction)[axis]) for value in (minimum, maximum)]
            lower = _i46_math.ceil((min(ends) - context['origin'][axis]) / context['spacing'])
            upper = _i46_math.floor((max(ends) - context['origin'][axis]) / context['spacing'])
            if upper - lower > 1024:
                raise MemoryError('edge native-grid knot budget exceeded')
            for native_index in range(lower, upper + 1):
                knots.append(float((context['origin'][axis] + native_index * context['spacing'] - anchor[axis]) / direction[axis]))
        ordered = []
        for value in sorted(knots):
            if not ordered or value - ordered[-1] > GEOMETRY_TOLERANCE_M:
                ordered.append(value)
        starts = sorted(((pair[0], number) for number, pair in enumerate(intervals)))
        ends = sorted(((pair[1], number) for number, pair in enumerate(intervals)))
        start_index = end_index = 0
        active = set()
        for first, second in zip(ordered, ordered[1:]):
            midpoint = (first + second) / 2
            while start_index < len(starts) and starts[start_index][0] < midpoint:
                active.add(starts[start_index][1])
                start_index += 1
            while end_index < len(ends) and ends[end_index][0] < midpoint:
                active.discard(ends[end_index][1])
                end_index += 1
            if not active:
                continue
            start, end = (anchor + first * direction, anchor + second * direction)
            support_index = min(max(0, _i46_bisect_right(mesh_coordinates, midpoint) - 1), len(mesh_knots) - 2)
            record = {'segment_id': 'segment:' + str(segment_number), 'start_xz_m': start.tolist(), 'end_xz_m': end.tolist(), 'sides': [edges[index] for index in sorted(active)], 'depth_support_knots': mesh_knots[support_index:support_index + 2]}
            segment_number += 1
            yield record

def _segments(groups, context):
    return list(_iter_segments(groups, context))

def _components(triangles, segments, seeds):
    parent = {identifier: identifier for identifier in triangles}

    def root(identifier):
        while parent[identifier] != identifier:
            parent[identifier] = parent[parent[identifier]]
            identifier = parent[identifier]
        return identifier
    for segment in segments:
        identifiers = [side['triangle_id'] for side in segment['sides'] if side['triangle_id'] in parent]
        for identifier in identifiers[1:]:
            parent[root(identifier)] = root(identifiers[0])
    selected_roots = {root(identifier) for identifier in seeds}
    members = _i46_defaultdict(list)
    for identifier in sorted(triangles):
        if root(identifier) in selected_roots:
            members[root(identifier)].append(identifier)
    return {'component:' + str(number): identifiers for number, identifiers in enumerate(sorted(members.values()))}

def _clip_polygon(polygon, axis, bound, keep_above):
    result = []
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        first_inside = first[axis] >= bound if keep_above else first[axis] <= bound
        second_inside = second[axis] >= bound if keep_above else second[axis] <= bound
        if first_inside:
            result.append(first)
        if first_inside != second_inside:
            fraction = (bound - first[axis]) / (second[axis] - first[axis])
            result.append([first[index] + fraction * (second[index] - first[index]) for index in range(2)])
    return result

def _patch_polygons(context, vertices_xz):
    points = _i46_np.asarray(vertices_xz, float)
    native = (points - context['origin']) / context['spacing']
    rows, columns = context['height'].shape
    if (native < 0).any() or (native[:, 0] > columns - 1).any() or (native[:, 1] > rows - 1).any():
        raise ValueError('outside_native_dem')
    low = _i46_np.floor(native.min(axis=0)).astype(int)
    high = _i46_np.minimum(_i46_np.floor(native.max(axis=0)).astype(int), [columns - 2, rows - 2])
    if _i46_math.prod((high - low + 1).tolist()) > 4096:
        raise MemoryError('fan native patch budget exceeded')
    result = []
    for row in range(low[1], high[1] + 1):
        for column in range(low[0], high[0] + 1):
            corner = context['origin'] + _i46_np.array([column, row]) * context['spacing']
            polygon = points.tolist()
            for axis in range(2):
                polygon = _clip_polygon(polygon, axis, float(corner[axis]), True) if polygon else []
                polygon = _clip_polygon(polygon, axis, float(corner[axis] + context['spacing']), False) if polygon else []
            if len(polygon) < 3:
                continue
            area = abs(_i46_math.fsum((first[0] * second[1] - second[0] * first[1] for first, second in zip(_i46_np.asarray(polygon) - corner, _i46_np.roll(_i46_np.asarray(polygon) - corner, -1, axis=0))))) / 2
            if area <= 1e-14:
                continue
            patch = _native_patch(context, _i46_np.mean(polygon, axis=0))
            source_gate = _source_sample(context, float(corner[0] + context['spacing'] / 2), float(corner[1] + context['spacing'] / 2))
            if source_gate['rejection_reasons']:
                raise ValueError('native_patch_gate:' + ','.join(source_gate['rejection_reasons']))
            result.append({**patch, 'polygon_xz_m': polygon, 'projected_area_m2': area})
    return result

def _proof(segment, context):
    from terrain_pipeline.td_fine_bed_raster import _digest as _i46__digest
    start, end = (_i46_np.asarray(segment['start_xz_m']), _i46_np.asarray(segment['end_xz_m']))
    samples = [_source_sample(context, float(point[0]), float(point[1])) for point in (start, end)]
    reasons = set((reason for sample in samples for reason in sample['rejection_reasons']))
    support_depths, support_provenance = ([], [])
    for knot in segment['depth_support_knots']:
        values, records = ([], [])
        for reference in knot['original_vertex_refs']:
            vertex = reference['xyz_m']
            source_sample = _source_sample(context, vertex[0], vertex[2])
            reasons.update(source_sample['rejection_reasons'])
            value = None if source_sample['height_m'] is None else source_sample['height_m'] - vertex[1]
            values.append(value)
            records.append({**reference, 'source_sample': source_sample, 'cut_depth_m': value})
        if any((value is None or value < 0 for value in values)):
            reasons.add('original_shared_knot_fill_or_unknown')
            support_depths.append(None)
        else:
            if max(values) - min(values) > FUNCTION_TOLERANCE_M:
                reasons.add('shared_original_vertex_depth_mismatch')
            support_depths.append(values[0])
        support_provenance.append(records)
    canonical_depths = [None, None]
    if all((value is not None for value in support_depths)):
        first_support, second_support = [_i46_np.asarray(knot['xz_m']) for knot in segment['depth_support_knots']]
        vector = second_support - first_support
        canonical_depths = [float((1 - fraction) * support_depths[0] + fraction * support_depths[1]) for fraction in [float((point - first_support) @ vector / (vector @ vector)) for point in (start, end)]]
    zero_boundary = False
    original_endpoint_depths = []
    if len(segment['sides']) == 1 and segment['sides'][0].get('zero_depth_boundary_eligible'):
        for vertex in segment['sides'][0]['points_xyz_m']:
            sample = _source_sample(context, vertex[0], vertex[2])
            original_endpoint_depths.append(None if sample['height_m'] is None else sample['height_m'] - vertex[1])
            reasons.update(sample['rejection_reasons'])
        zero_boundary = original_endpoint_depths == [0.0, 0.0]
    side_depths = []
    for side in segment['sides']:
        values = [0.0, 0.0] if zero_boundary else canonical_depths
        side_endpoint_depths = []
        for vertex in side['points_xyz_m']:
            sample = _source_sample(context, vertex[0], vertex[2])
            value = None if sample['height_m'] is None else sample['height_m'] - vertex[1]
            side_endpoint_depths.append(value)
            reasons.update(sample['rejection_reasons'])
        if any((value is None or value < 0 for value in side_endpoint_depths)):
            reasons.add('original_edge_vertex_fill_or_unknown')
        for knot in segment['depth_support_knots']:
            if any((abs(reference['xyz_m'][1] - _edge_y(side, _i46_np.asarray(knot['xz_m']))) > FUNCTION_TOLERANCE_M for reference in knot['original_vertex_refs'])):
                reasons.add('T_junction_original_profile_mismatch')
        if any((value is None or value < 0 for value in values)):
            reasons.add('boundary_knot_fill_or_unknown')
        side_depths.append({'triangle_id': side['triangle_id'], 'edge_index': side['edge_index'], 'depth_knots_m': values, 'original_endpoint_cut_depth_m': side_endpoint_depths, 'new_common_knot_function_adopted': True})
    if not reasons:
        if any((max((values['depth_knots_m'][index] for values in side_depths)) - min((values['depth_knots_m'][index] for values in side_depths)) > FUNCTION_TOLERANCE_M for index in range(2))):
            reasons.add('shared_depth_knot_mismatch')
    source = None
    try:
        source = source_segment_polynomial(context, start, end)
    except ValueError as error:
        reasons.add(str(error))
    depth = None if reasons else side_depths[0]['depth_knots_m']
    coefficients = None if depth is None else [depth[0], depth[1] - depth[0]]
    if not reasons:
        if any((side['triangle_id'].startswith('legacy06:') for side in segment['sides'])):
            for side in segment['sides']:
                if not side['triangle_id'].startswith('legacy06:'):
                    continue
                legacy_start = _edge_y(side, start)
                legacy_end = _edge_y(side, end)
                difference = [source['source_coefficients_m_t012'][0] - coefficients[0] - legacy_start, source['source_coefficients_m_t012'][1] - coefficients[1] - (legacy_end - legacy_start), source['source_coefficients_m_t012'][2]]
                if max((abs(value) for value in difference)) > FUNCTION_TOLERANCE_M:
                    reasons.add('unchanged_neighbor_quadratic_function_mismatch')
        elif len(segment['sides']) == 1 and max(depth) > FUNCTION_TOLERANCE_M:
            reasons.add('uncovered_boundary_has_nonzero_depth')
        if len([side for side in segment['sides'] if not side['triangle_id'].startswith('legacy06:')]) > 2:
            reasons.add('nonmanifold_shared_segment')
    if reasons:
        depth = coefficients = None
    return _seal({'kind': 'edge_function_proof', **segment, 'source': source, 'source_samples': samples, 'side_depth_knots': side_depths, 'depth_support_knot_source_provenance': support_provenance, 'support_cut_depth_m': support_depths, 'depth_coefficients_m_t01': coefficients, 'common_function_identity_sha256': None if depth is None else _i46__digest({'start_xz_m': start.tolist(), 'end_xz_m': end.tolist(), 'source': source, 'depth_coefficients_m_t01': coefficients}), 'boundary_condition': 'explicit_source_bank_zero_depth_v2' if zero_boundary else 'unified_original_vertex_depth_knots_v2', 'original_edge_endpoint_cut_depth_m': original_endpoint_depths, 'old_absolute_edge_changed': bool(zero_boundary), 'status': 'refused' if reasons else 'candidate', 'rejection_reasons': sorted(reasons), 'proof_method': 'same_native_patch_quadratic_source_and_linear_depth'})

def _port_proofs(transitions, sections, proofs, triangle_components, reasons_by_component):
    from terrain_pipeline.td_fine_bed_raster import _digest as _i46__digest
    edge_sections = {item['arc_id']: item for item in sections['edge_sections']}
    result = []
    for entry_index, entry in enumerate(transitions['entries']):
        if entry['status'] != 'candidate':
            continue
        entry_triangles = {side['triangle_id'] for proof in proofs for side in proof['sides'] if side['triangle_id'].startswith(f'09:{entry_index}:')}
        components = {triangle_components[identifier] for identifier in entry_triangles if identifier in triangle_components}
        if not components:
            continue
        reasons, matched = (set(), [])
        port = entry.get('accepted_port_xyz_m', [])
        owner = edge_sections.get(entry.get('accepted_port_arc_id'))
        if len(port) != 4 or owner is None or port not in owner.get('cross_section_xyz_m', []):
            reasons.add('port_parent_profile_not_exactly_bound')
        else:
            for first, second in zip(port, port[1:]):
                first_xz, second_xz = (_i46_np.asarray(first)[[0, 2]], _i46_np.asarray(second)[[0, 2]])
                vector = second_xz - first_xz
                length = float(_i46_np.linalg.norm(vector))
                intervals = []
                for proof in proofs:
                    if not any((side['triangle_id'] in entry_triangles for side in proof['sides'])):
                        continue
                    start, end = (_i46_np.asarray(proof['start_xz_m']), _i46_np.asarray(proof['end_xz_m']))
                    cross = [(point[0] - first_xz[0]) * vector[1] - (point[1] - first_xz[1]) * vector[0] for point in (start, end)]
                    if max((abs(value) for value in cross)) > GEOMETRY_TOLERANCE_M * length:
                        continue
                    values = sorted((float((point - first_xz) @ vector / (vector @ vector)) for point in (start, end)))
                    if values[0] < -1e-08 or values[1] > 1 + 1e-08:
                        continue
                    sides = proof['sides']
                    has_06 = any((side['triangle_id'] == '06:' + str(index) for side in sides for index in owner['triangle_indices']))
                    has_09 = any((side['triangle_id'] in entry_triangles for side in sides))
                    if not has_06 or not has_09 or proof['status'] != 'candidate':
                        reasons.add('port_piece_missing_two_sided_function')
                    intervals.append(values)
                    matched.append(proof['segment_id'])
                cursor = 0.0
                for lower, upper in sorted(intervals):
                    if lower > cursor + 1e-08 or lower < cursor - 1e-08:
                        reasons.add('port_piece_gap_or_duplicate')
                    cursor = max(cursor, upper)
                if abs(cursor - 1) > 1e-08:
                    reasons.add('port_piece_incomplete')
        for component in components:
            reasons_by_component[component].update(reasons)
        result.append(_seal({'kind': 'port_function_proof', 'entry_id': entry['entry_id'], 'source_entry_index': entry_index, 'accepted_port_arc_id': entry.get('accepted_port_arc_id'), 'original_four_point_port_xyz_m': port, 'segment_ids': sorted(set(matched)), 'component_ids': sorted(components), 'status': 'refused' if reasons else 'candidate', 'rejection_reasons': sorted(reasons), 'port_function_identity_sha256': None if reasons else _i46__digest([proof['common_function_identity_sha256'] for proof in proofs if proof['segment_id'] in set(matched)]), 'legacy_port_function_preserved': False, 'old_absolute_expression_verified': False}))
    return result

def _function(triangle, edge_proofs, context, parameters):
    vertices = _i46_np.asarray(triangle['vertices_xyz_m'], float)
    samples = [_source_sample(context, float(point[0]), float(point[2])) for point in vertices]
    reasons = set((reason for sample in samples for reason in sample['rejection_reasons']))
    depths = [None if sample['height_m'] is None else sample['height_m'] - point[1] for sample, point in zip(samples, vertices)]
    if any((value is None or value < 0 for value in depths)):
        reasons.add('original_vertex_fill_or_unknown')
    if any((value is not None and value > parameters['max_cut_m'] + parameters['conflict_tolerance_m'] for value in depths)):
        reasons.add('original_vertex_cut_depth_exceeded')
    if any((value is not None and value > parameters['conflict_tolerance_m'] and sample['wet_source_support'] for sample, value in zip(samples, depths))):
        reasons.add('lake_wet_vertex_cut_refused')
    if any((proof['status'] != 'candidate' for proof in edge_proofs)):
        reasons.add('boundary_function_unproved')
    center = vertices[:, [0, 2]].mean(axis=0)
    center_sample = _source_sample(context, float(center[0]), float(center[1]))
    reasons.update(center_sample['rejection_reasons'])
    center_depth = None if any((value is None for value in depths)) else _i46_math.fsum(depths) / 3
    fans = []
    if not reasons:
        for proof in edge_proofs:
            start, end = (proof['start_xz_m'], proof['end_xz_m'])
            edge_depth = proof['depth_coefficients_m_t01']
            fan_xz = [center.tolist(), start, end]
            fan_depth = [center_depth, edge_depth[0], edge_depth[0] + edge_depth[1]]
            if min(fan_depth) < 0:
                reasons.add('negative_fan_depth')
                break
            if max(fan_depth) > parameters['max_cut_m'] + parameters['conflict_tolerance_m']:
                reasons.add('fan_cut_depth_exceeded')
                break
            local = _i46_np.asarray(fan_xz) - center
            matrix = _i46_np.column_stack((_i46_np.ones(3), local))
            try:
                coefficients = _i46_np.linalg.solve(matrix, _i46_np.asarray(fan_depth))
                patches = _patch_polygons(context, fan_xz)
            except (ValueError, _i46_np.linalg.LinAlgError) as error:
                reasons.add('fan_source_or_geometry_refused:' + str(error))
                break
            fans.append({'fan_id': triangle['triangle_id'] + ':fan:' + str(len(fans)), 'vertices_xz_m': fan_xz, 'depth_at_vertices_m': fan_depth, 'depth_origin_xz_m': center.tolist(), 'depth_coefficients_m_1xz': coefficients.tolist(), 'boundary_segment_id': proof['segment_id'], 'native_patches': patches})
    projected_area = abs(float(_i46_np.linalg.det(_i46_np.column_stack((vertices[1, [0, 2]] - vertices[0, [0, 2]], vertices[2, [0, 2]] - vertices[0, [0, 2]]))))) / 2
    fan_area = _i46_math.fsum((patch['projected_area_m2'] for fan in fans for patch in fan['native_patches']))
    if not reasons and abs(fan_area - projected_area) > max(1e-10, projected_area * 1e-09):
        reasons.add('fan_area_coverage_incomplete')
    return _seal({'kind': 'source_relative_triangle_function', 'triangle_id': triangle['triangle_id'], 'original_triangle': triangle, 'original_vertex_source_samples': samples, 'original_vertex_cut_depth_m': depths, 'center_source_sample': center_sample, 'center_cut_depth_m': center_depth, 'center_rule': 'arithmetic_mean_original_vertex_cut_depths', 'fans': fans, 'projected_area_m2': projected_area, 'fan_projected_area_m2': fan_area, 'expression': 'native_bilinear_source_minus_piecewise_affine_nonnegative_cut_depth', 'old_edge_function_may_change': True, 'status': 'refused' if reasons else 'candidate', 'rejection_reasons': sorted(reasons)})

def evaluate_bank_function(function, x_m, z_m, source_height_m):
    from terrain_pipeline.td_fine_bed_raster import _weights as _i46__weights
    if function['status'] != 'candidate':
        raise ValueError('refused function cannot be evaluated')
    values = []
    for fan in function['fans']:
        points = _i46_np.array([[point[0], 0.0, point[1]] for point in fan['vertices_xz_m']])
        weights = _i46__weights(points, x_m, z_m)
        if weights is not None:
            depth = float(weights @ _i46_np.asarray(fan['depth_at_vertices_m']))
            values.append((depth, fan['fan_id']))
    if not values or max((value[0] for value in values)) - min((value[0] for value in values)) > FUNCTION_TOLERANCE_M:
        raise ValueError('fan coverage or internal depth continuity failed')
    depth, fan_id = values[0]
    if depth < 0:
        raise ValueError('negative evaluated cut depth')
    return {'bed_m': float(source_height_m - depth), 'cut_depth_m': depth, 'fan_id': fan_id, 'function_identity_sha256': function['identity_sha256']}

def _connection_queue(transitions, paths, sections, readiness, component_by_triangle, components):
    nodes = {node['node_id']: node for node in paths['nodes']}
    arcs = {arc['arc_id']: arc for arc in paths['arcs']}
    graph = _i46_defaultdict(list)
    engineering = {identifier for identifier, node in nodes.items() if 'engineering' in node['kinds']}
    for arc in arcs.values():
        for first, second in zip(arc['node_ids'], arc['node_ids'][1:]):
            if first in nodes and second in nodes:
                graph[first].append((second, arc['arc_id']))
                graph[second].append((first, arc['arc_id']))
    parents = {}
    pending = _i46_deque(sorted(engineering))
    for identifier in engineering:
        parents[identifier] = None
    while pending:
        identifier = pending.popleft()
        for neighbor, arc_id in sorted(graph[identifier]):
            if neighbor not in parents:
                parents[neighbor] = (identifier, arc_id)
                pending.append(neighbor)
    requests = {item['entry_id']: item for item in readiness['requests']}
    node_sections = {item['node_id']: (index, item) for index, item in enumerate(sections.get('node_sections', []))}
    rows = []
    for entry_index, entry in enumerate(transitions['entries']):
        previous = requests.get(entry['entry_id'], {'status': 'unknown_parent_readiness'})
        if previous['status'] not in {'parent_refused', 'pending'}:
            continue
        actual_arc = arcs.get(entry['entry_id'])
        node_ids = actual_arc['node_ids'] if actual_arc is not None else []
        chain = []
        reachable = next((identifier for identifier in node_ids if identifier in parents), None)
        node_walk = [] if reachable is None else [reachable]
        while reachable is not None and parents[reachable] is not None:
            reachable, arc_id = parents[reachable]
            chain.append(arc_id)
            node_walk.append(reachable)
        affected = sorted({component for identifier, component in component_by_triangle.items() if identifier.startswith(f'09:{entry_index}:')})
        reasons = list(entry.get('rejection_reasons', [])) if entry['status'] != 'candidate' else list(previous.get('cell_refusals', {}))
        component_reasons = sorted({reason for component in affected for reason in components[component]['rejection_reasons']})
        classification = 'missing_geometry_parent' if entry['status'] != 'candidate' else 'source_conforming_candidate' if affected and all((components[item]['status'] == 'candidate' for item in affected)) else 'shared_function_or_source_gate_pending'
        source_node_ids = sorted(set(node_ids).union((entry[name] for name in ('upstream_node_id', 'anchor_node_id', 'wet_node_id') if name in entry)))
        flow_references = []
        for node_id in source_node_ids:
            if node_id in node_sections:
                section_index, section = node_sections[node_id]
                flow_references.append({'node_id': node_id, 'source_node_section_index': section_index, 'representative_q_m3_s': section.get('representative_q_m3_s'), 'local_runoff_q_m3_s': section.get('local_runoff_q_m3_s'), 'incoming_exchange_q_m3_s': section.get('incoming_exchange_q_m3_s'), 'ordinary_identity_sha256': sections.get('ordinary_identity_sha256'), 'semantics': 'unchanged ordinary-event mean proxy, not instantaneous Q'})
        rows.append({'entry_id': entry['entry_id'], 'source_entry_index': entry_index, 'parent_status': previous['status'], 'parent_reasons': reasons, 'parent_reason_class': 'ambiguous_or_missing_port' if 'missing_or_ambiguous_accepted_port' in reasons else 'ambiguous_or_missing_land_predecessor' if 'missing_or_ambiguous_land_predecessor' in reasons else 'engineering_boundary' if 'engineering_boundary_contact' in reasons else 'saved_cell_gate', 'classification': classification, 'component_ids': affected, 'v2_rejection_reasons': component_reasons, 'actual_entry_arc_id': None if actual_arc is None else actual_arc['arc_id'], 'actual_node_ids': node_ids, 'actual_support_path_to_engineering_arc_ids': chain, 'actual_support_path_to_engineering_node_ids': node_walk, 'source_node_references': [_i46_deepcopy(nodes[node_id]) for node_id in source_node_ids if node_id in nodes], 'source_arc_reference': _i46_deepcopy(actual_arc), 'ordinary_flow_references': flow_references, 'accepted_port_arc_reference': _i46_deepcopy(arcs.get(entry.get('accepted_port_arc_id'))), 'land_arc_reference': _i46_deepcopy(arcs.get(entry.get('land_arc_id'))), 'flow_reference_missing': not flow_references, 'undirected_support_reaches_engineering': bool(node_walk), 'directed_hydraulic_connection_proved': False, 'fabricated_arc_count': 0})
    rows.sort(key=lambda item: (not item['undirected_support_reaches_engineering'], item['classification'] != 'source_conforming_candidate', item['entry_id']))
    return _seal({'schema': TD_SOURCE_CONFORMING_BANKS_SCHEMA + '-connection-queue', 'requests': rows, 'paths_identity_sha256': paths['identity_sha256'], 'sections_identity_sha256': sections['identity_sha256'], 'transitions_identity_sha256': transitions['identity_sha256'], 'semantics': 'priority uses actual undirected support graph, not a proved river or downstream flow', 'parent_status_counts': dict(_i46_Counter((item['parent_status'] for item in rows))), **{flag: False for flag in TD_SOURCE_CONFORMING_BANKS_FLAGS}})

def _chunks(kind, records, max_bytes, parent_identity):
    chunks, current, size = ([], [], 1024)
    for record in records:
        length = _record_bytes(record) + 1
        if length + 1024 > max_bytes:
            raise MemoryError('single ' + kind + ' record exceeds shard budget')
        if current and (size + length > max_bytes or len(current) >= 2048):
            chunks.append(_seal({'schema': TD_SOURCE_CONFORMING_BANKS_SCHEMA + '-' + kind, 'parent_identity_sha256': parent_identity, 'chunk_id': kind + '-' + str(len(chunks)).zfill(4), 'records': current}))
            current, size = ([], 1024)
        current.append(record)
        size += length
    if current:
        chunks.append(_seal({'schema': TD_SOURCE_CONFORMING_BANKS_SCHEMA + '-' + kind, 'parent_identity_sha256': parent_identity, 'chunk_id': kind + '-' + str(len(chunks)).zfill(4), 'records': current}))
    return chunks
from terrain_pipeline.td_fine_bed_raster import MAX_BYTES as _i46_MAX_BYTES
from terrain_pipeline.td_fine_bed_raster import MAX_CELLS as _i46_MAX_CELLS

def build_source_conforming_banks(base, shard_package, hierarchy, sections, transitions, paths, readiness, *, input_pins=None, max_cells=_i46_MAX_CELLS, max_shard_bytes=_i46_MAX_BYTES, resource_check=None):
    """Reuse saved centers. Reject a whole changed component if any gate fails."""
    from terrain_pipeline.td_fine_bed_raster import LEDGER_KEYS as _i46_LEDGER_KEYS
    from terrain_pipeline.td_fine_bed_raster import _context as _i46__context
    from terrain_pipeline.td_fine_bed_raster import _digest as _i46__digest
    from terrain_pipeline.td_fine_bed_shards import _cut as _i46__cut
    from terrain_pipeline.td_fine_bed_shards import _evaluate as _i46__evaluate
    from terrain_pipeline.td_fine_bed_shards import _ledger as _i46__ledger
    from terrain_pipeline.td_fine_bed_shards import iter_merged_cells as _i46_iter_merged_cells
    if type(max_cells) is not int or not 1 <= max_cells <= _i46_MAX_CELLS or type(max_shard_bytes) is not int or (not 4096 <= max_shard_bytes <= _i46_MAX_BYTES):
        raise ValueError('invalid source-conforming resource budget')
    _rss_guard(resource_check, phase='parent_linkage')
    for name, record in (('hierarchy', hierarchy), ('sections', sections), ('transitions', transitions)):
        if base[name + '_identity_sha256'] != record['identity_sha256']:
            raise ValueError('immutable ' + name + ' linkage mismatch')
    if paths['identity_sha256'] != transitions['paths_identity_sha256'] or shard_package['manifest']['base_identity_sha256'] != base['identity_sha256'] or base['source_identity_sha256'] != hierarchy['metadata']['source_identity_sha256']:
        raise ValueError('immutable source/paths/shards linkage mismatch')
    parent_identity = shard_package['manifest']['identity_sha256']
    context = _i46__context(hierarchy, base['selected_leaf_ids'], base['wet_protection'])
    cells = {key: (cell, owner) for key, cell, owner in _i46_iter_merged_cells(base, shard_package['shards'])}
    if len(cells) > max_cells:
        raise MemoryError('merged parent exceeds unique-cell budget')
    _rss_guard(resource_check, phase='readonly_parent_cells', counters={'cells': len(cells)})
    triangles = {item['triangle_id']: item for item in base['triangles']}
    triangles.update({item['triangle_id']: item for item in shard_package['raw']['triangles']})
    if len(triangles) != len(base['triangles']):
        raise ValueError('parent triangle indices are duplicated or shard raw introduced new triangles')
    for triangle in triangles.values():
        mesh = sections['mesh'] if triangle['source_package'] == '06' else transitions['entries'][triangle['source_entry_index']]
        original_indices = mesh['triangles'][triangle['source_triangle_index']]
        if original_indices != triangle['source_vertex_indices'] or [mesh['vertices_xyz_m'][index] for index in original_indices] != triangle['vertices_xyz_m']:
            raise ValueError('original triangle indices/source XYZ chain mismatch')
    seeds = {proposal['triangle_id'] for cell, owner in cells.values() if 'fill_without_material' in cell['rejection_reasons'] for proposal in cell['triangle_sources']}
    if not seeds.issubset(triangles):
        raise ValueError('saved fill proposals missing original provenance')
    groups = _i46_defaultdict(list)
    bank_points = {tuple(point) for edge in sections['edge_sections'] for profile in edge.get('cross_section_xyz_m', []) for point in (profile[0], profile[-1])}
    for triangle in triangles.values():
        for edge_index in range(3):
            edge = _edge_record(triangle, edge_index)
            if triangle['source_package'] == '06':
                edge['zero_depth_boundary_eligible'] = all((tuple(point) in bank_points for point in edge['points_xyz_m']))
            else:
                entry = transitions['entries'][triangle['source_entry_index']]
                first_index = triangle['source_vertex_indices'][edge_index]
                second_index = triangle['source_vertex_indices'][(edge_index + 1) % 3]
                edge['zero_depth_boundary_eligible'] = first_index % 5 == second_index % 5 and first_index % 5 in (0, 4) or min(first_index, second_index) >= len(entry['vertices_xyz_m']) - 5
            groups[_line_key(_i46_np.asarray(edge['points_xyz_m'])[:, [0, 2]])].append(edge)
    original_mesh = sections['mesh']
    for index, indices in enumerate(original_mesh['triangles']):
        if '06:' + str(index) in triangles:
            continue
        legacy = {'triangle_id': 'legacy06:' + str(index), 'vertices_xyz_m': [original_mesh['vertices_xyz_m'][vertex] for vertex in indices]}
        for edge_index in range(3):
            edge = _edge_record(legacy, edge_index)
            key = _line_key(_i46_np.asarray(edge['points_xyz_m'])[:, [0, 2]])
            if key in groups:
                groups[key].append(edge)
    _rss_guard(resource_check, phase='edge_groups', counters={'groups': len(groups)})
    member_sets = _components(triangles, _iter_segments(groups, context), seeds)
    component_by_triangle = {identifier: component for component, members in member_sets.items() for identifier in members}
    reasons_by_component = _i46_defaultdict(set)
    _rss_guard(resource_check, phase='component_selection', counters={'triangles': len(component_by_triangle)})
    proofs = []
    by_triangle = _i46_defaultdict(list)
    for segment in _iter_segments(groups, context):
        if not any((side['triangle_id'] in component_by_triangle for side in segment['sides'])):
            continue
        if len(proofs) % 256 == 0:
            _rss_guard(resource_check, phase='selected_proofs', counters={'proofs': len(proofs)})
        proof = _proof(segment, context)
        proofs.append(proof)
        for side in segment['sides']:
            identifier = side['triangle_id']
            by_triangle[identifier].append(proof)
            if identifier in component_by_triangle:
                reasons_by_component[component_by_triangle[identifier]].update(proof['rejection_reasons'])
    del groups, bank_points
    _i46_gc.collect()
    _rss_guard(resource_check, phase='selected_proofs_complete', counters={'proofs': len(proofs)})
    port_proofs = _port_proofs(transitions, sections, proofs, component_by_triangle, reasons_by_component)
    functions = {}
    for number, identifier in enumerate(sorted(component_by_triangle)):
        if number % 128 == 0:
            _rss_guard(resource_check, phase='raw_functions', counters={'functions': number, 'proofs': len(proofs)})
        function = _function(triangles[identifier], by_triangle[identifier], context, base['parameters'])
        functions[identifier] = function
        component = component_by_triangle[identifier]
        reasons_by_component[component].update(function['rejection_reasons'])
        if triangles[identifier]['status'] not in {'rasterized', 'no_center_coverage'}:
            reasons_by_component[component].add('parent_triangle_coverage_incomplete')
    context.get('bank_sample_cache', {}).clear()
    context.get('bank_patch_cache', {}).clear()
    del by_triangle
    _i46_gc.collect()
    _rss_guard(resource_check, phase='raw_functions_complete', counters={'functions': len(functions)})
    census = _i46_Counter((proposal['triangle_id'] for cell, owner in cells.values() for proposal in cell['triangle_sources']))
    for identifier, component in component_by_triangle.items():
        if census[identifier] != triangles[identifier].get('covered_centers', 0):
            reasons_by_component[component].add('saved_triangle_center_census_mismatch')
    affected_cells = [(key, cell, owner) for key, (cell, owner) in cells.items() if any((proposal['triangle_id'] in component_by_triangle for proposal in cell['triangle_sources']))]
    parent_cell_count = len(cells)
    original_fill_count = sum(('fill_without_material' in cell['rejection_reasons'] for cell, owner in cells.values()))
    del cells, census
    effects = []
    origin, spacing = (_i46_np.asarray(base['grid']['origin_m_xz']), base['grid']['spacing_m'])
    for number, (key, cell, owner) in enumerate(sorted(affected_cells)):
        if number % 4096 == 0:
            _rss_guard(resource_check, phase='effects', counters={'visited_cells': number, 'effects': len(effects)})
        components = {component_by_triangle[proposal['triangle_id']] for proposal in cell['triangle_sources'] if proposal['triangle_id'] in component_by_triangle}
        if any((reasons_by_component[component] for component in components)):
            continue
        point = origin + (_i46_np.array([key[1], key[0]]) + base['grid']['center_offset_cells']) * spacing
        source_height = cell['source_sample']['height_m']
        if source_height is None:
            for component in components:
                reasons_by_component[component].add('saved_source_unknown')
            continue
        proposals = []
        try:
            for original in cell['triangle_sources']:
                proposal = dict(original)
                if original['triangle_id'] in functions:
                    value = evaluate_bank_function(functions[original['triangle_id']], float(point[0]), float(point[1]), source_height)
                    proposal['legacy_absolute_bed_m'] = original['bed_m']
                    proposal.update(value)
                proposals.append(proposal)
            after = _i46__evaluate(cell['source_sample'], proposals, cell['local_index'], base['parameters'])
            if after['status'] != 'candidate':
                for component in components:
                    reasons_by_component[component].update(('v2_cell_gate:' + reason for reason in after['rejection_reasons']))
                continue
        except ValueError as error:
            for component in components:
                reasons_by_component[component].add('v2_cell_function:' + str(error))
            continue
        before_cut, after_cut = (_i46__cut(cell, spacing), _i46__cut(after, spacing))
        effects.append({'global_key_row_column': list(key), 'operation': 'replace', 'logical_owner': owner, 'component_ids': sorted(components), 'before_sha256': _i46__digest(cell), 'cell': after, 'before_cut_m3': before_cut, 'after_cut_m3': after_cut, 'cut_delta_m3': after_cut - before_cut, 'source_sample_reused': True})
    changed = True
    while changed:
        changed = False
        for key, cell, owner in affected_cells:
            components = {component_by_triangle[item['triangle_id']] for item in cell['triangle_sources'] if item['triangle_id'] in component_by_triangle}
            if any((reasons_by_component[component] for component in components)):
                for component in components:
                    if not reasons_by_component[component]:
                        reasons_by_component[component].add('overlapping_refused_component')
                        changed = True
    effects = [effect for effect in effects if not any((reasons_by_component[item] for item in effect['component_ids']))]
    components = {component: {'component_id': component, 'triangle_ids': members, 'status': 'refused' if reasons_by_component[component] else 'candidate', 'rejection_reasons': sorted(reasons_by_component[component]), 'seed_triangle_ids': sorted(set(members).intersection(seeds)), 'union_method': 'entire_parent_shared_edge_component_including_T_junction_overlaps'} for component, members in member_sets.items()}
    queue = _connection_queue(transitions, paths, sections, readiness, component_by_triangle, components)
    before_ledger = _i46_deepcopy(shard_package['manifest']['material_ledger_merged'])
    delta = _i46__ledger(_i46_math.fsum((effect['cut_delta_m3'] for effect in effects)))
    after_ledger = {name: before_ledger[name] + delta[name] for name in _i46_LEDGER_KEYS}
    package = {'raw': _chunks('raw', list(functions.values()), max_shard_bytes, parent_identity), 'proofs': _chunks('proofs', proofs + port_proofs, max_shard_bytes, parent_identity), 'effects': _chunks('effects', effects, max_shard_bytes, parent_identity), 'queue': queue}
    package['manifest'] = _seal({'schema': TD_SOURCE_CONFORMING_BANKS_SCHEMA, 'algorithm': TD_SOURCE_CONFORMING_BANKS_ALGORITHM, 'inputs': dict(input_pins or {}), 'parent_identity_sha256': parent_identity, 'base_identity_sha256': base['identity_sha256'], 'hierarchy_identity_sha256': hierarchy['identity_sha256'], 'source_identity_sha256': base['source_identity_sha256'], 'sections_identity_sha256': sections['identity_sha256'], 'transitions_identity_sha256': transitions['identity_sha256'], 'paths_identity_sha256': paths['identity_sha256'], 'grid': _i46_deepcopy(base['grid']), 'selected_leaf_ids': list(base['selected_leaf_ids']), 'wet_protection': _i46_deepcopy(base['wet_protection']), 'parameters': _i46_deepcopy(base['parameters']), 'budgets': {'max_cells': max_cells, 'max_shard_bytes': max_shard_bytes, 'max_rss_bytes': MAX_RSS}, 'proof_tolerances': {'geometry_m': GEOMETRY_TOLERANCE_M, 'function_m': FUNCTION_TOLERANCE_M}, 'components': list(components.values()), 'affected_global_keys_row_column': [list(item[0]) for item in sorted(affected_cells)], 'summary': {'parent_unique_cells': parent_cell_count, 'original_fill_refused_cells': original_fill_count, 'seed_triangles': len(seeds), 'affected_triangles': len(functions), 'affected_cells': len(affected_cells), 'replace_cells': len(effects), 'unchanged_parent_cells': parent_cell_count - len(effects), 'candidate_components': sum((item['status'] == 'candidate' for item in components.values())), 'refused_components': sum((item['status'] == 'refused' for item in components.values())), 'center_source_resamples': 0, 'new_lattice_cells': 0, 'water_solves': 0}, 'material_ledger_parent': before_ledger, 'material_ledger_delta': delta, 'material_ledger_candidate': after_ledger, 'chunk_identities': {kind: [chunk['identity_sha256'] for chunk in package[kind]] for kind in ('raw', 'proofs', 'effects')}, 'queue_identity_sha256': queue['identity_sha256'], 'old_mesh_passed': False, 'old_port_preservation_claimed': False, 'independent_audit_passed': False, **{flag: False for flag in TD_SOURCE_CONFORMING_BANKS_FLAGS}})
    _rss_guard(resource_check, phase='candidate_chunks_complete')
    validate_source_conforming_banks(package)
    return package

def validate_source_conforming_banks(package, *, base=None, shard_package=None, hierarchy=None):
    """Cold identity/unique-effect/ledger check; independent function audit stays separate."""
    from terrain_pipeline.td_fine_bed_raster import LEDGER_KEYS as _i46_LEDGER_KEYS
    from terrain_pipeline.td_fine_bed_raster import _context as _i46__context
    from terrain_pipeline.td_fine_bed_raster import _digest as _i46__digest
    from terrain_pipeline.td_fine_bed_shards import _cut as _i46__cut
    from terrain_pipeline.td_fine_bed_shards import _ledger as _i46__ledger
    from terrain_pipeline.td_fine_bed_shards import iter_merged_cells as _i46_iter_merged_cells
    manifest = package['manifest']
    _check_identity(manifest)
    _check_identity(package['queue'])
    budgets = manifest['budgets']
    if manifest['schema'] != TD_SOURCE_CONFORMING_BANKS_SCHEMA or manifest['algorithm'] != TD_SOURCE_CONFORMING_BANKS_ALGORITHM or (not 1 <= budgets['max_cells'] <= _i46_MAX_CELLS) or (not 4096 <= budgets['max_shard_bytes'] <= _i46_MAX_BYTES) or (budgets['max_rss_bytes'] != MAX_RSS) or any((manifest.get(flag) is not False for flag in TD_SOURCE_CONFORMING_BANKS_FLAGS)) or (manifest['old_mesh_passed'] is not False) or (manifest['independent_audit_passed'] is not False):
        raise ValueError('source-conforming schema/budget/certification mismatch')
    if package['queue']['identity_sha256'] != manifest['queue_identity_sha256']:
        raise ValueError('connection queue pin mismatch')
    parents = None
    if base is not None and shard_package is not None:
        if base['identity_sha256'] != manifest['base_identity_sha256'] or shard_package['manifest']['identity_sha256'] != manifest['parent_identity_sha256'] or base['grid'] != manifest['grid'] or (shard_package['manifest']['material_ledger_merged'] != manifest['material_ledger_parent']):
            raise ValueError('cold immutable parent linkage mismatch')
        parents = {key: (cell, owner) for key, cell, owner in _i46_iter_merged_cells(base, shard_package['shards'])}
    keys, deltas, functions, edge_proofs = (set(), [], {}, {})
    component_by_triangle = {identifier: component for component in manifest['components'] for identifier in component['triangle_ids']}
    for kind in ('raw', 'proofs', 'effects'):
        if len(package[kind]) > MAX_FILES or [item['identity_sha256'] for item in package[kind]] != manifest['chunk_identities'][kind]:
            raise ValueError('chunk identity census mismatch')
        for chunk in package[kind]:
            _check_identity(chunk)
            if chunk['parent_identity_sha256'] != manifest['parent_identity_sha256'] or _record_bytes(chunk) > budgets['max_shard_bytes']:
                raise ValueError('chunk parent pin/byte limit mismatch')
            for record in chunk['records']:
                if kind == 'raw':
                    _check_identity(record)
                    identifier = record['triangle_id']
                    if identifier in functions or identifier not in component_by_triangle:
                        raise ValueError('duplicate/unselected raw triangle')
                    functions[identifier] = record
                    if record['status'] == 'candidate' and any((depth < 0 for fan in record['fans'] for depth in fan['depth_at_vertices_m'])):
                        raise ValueError('negative candidate depth')
                elif kind == 'proofs':
                    _check_identity(record)
                    if record['kind'] == 'edge_function_proof':
                        if record['segment_id'] in edge_proofs:
                            raise ValueError('duplicate edge proof')
                        edge_proofs[record['segment_id']] = record
                else:
                    key = tuple(record['global_key_row_column'])
                    if key in keys or record['operation'] != 'replace' or (not record['source_sample_reused']):
                        raise ValueError('duplicate/new center transaction')
                    keys.add(key)
                    cell = record['cell']
                    if any((component_by_triangle[item['triangle_id']]['status'] != 'candidate' for item in cell['triangle_sources'] if item['triangle_id'] in component_by_triangle)):
                        raise ValueError('effect applied refused component')
                    if parents is not None:
                        before, owner = parents[key]
                        if _i46__digest(before) != record['before_sha256'] or owner != record['logical_owner'] or before['source_sample'] != cell['source_sample'] or (abs(_i46__cut(before, manifest['grid']['spacing_m']) - record['before_cut_m3']) > 1e-10):
                            raise ValueError('effect parent/source/owner mismatch')
                    cut = _i46__cut(cell, manifest['grid']['spacing_m'])
                    if abs(cut - record['after_cut_m3']) > 1e-10 or abs(cut - record['before_cut_m3'] - record['cut_delta_m3']) > 1e-10:
                        raise ValueError('signed effect material mismatch')
                    deltas.append(record['cut_delta_m3'])
    if set(functions) != set(component_by_triangle) or len(keys) != manifest['summary']['replace_cells']:
        raise ValueError('complete affected union/effect census mismatch')
    if len(manifest['affected_global_keys_row_column']) != manifest['summary']['affected_cells']:
        raise ValueError('affected center census mismatch')
    if manifest['summary']['parent_unique_cells'] > budgets['max_cells'] or not keys.issubset({tuple(key) for key in manifest['affected_global_keys_row_column']}):
        raise ValueError('effect outside bounded affected union')
    expected_delta = _i46__ledger(_i46_math.fsum(deltas))
    for name in _i46_LEDGER_KEYS:
        if abs(expected_delta[name] - manifest['material_ledger_delta'][name]) > 1e-09 or abs(manifest['material_ledger_parent'][name] + expected_delta[name] - manifest['material_ledger_candidate'][name]) > 1e-09:
            raise ValueError('signed material ledger double count')
    if hierarchy is not None:
        if hierarchy['identity_sha256'] != manifest['hierarchy_identity_sha256']:
            raise ValueError('cold source identity mismatch')
        context = _i46__context(hierarchy, manifest['selected_leaf_ids'], manifest['wet_protection'])
        for proof in edge_proofs.values():
            expected = _proof({name: proof[name] for name in ('segment_id', 'start_xz_m', 'end_xz_m', 'sides', 'depth_support_knots')}, context)
            if proof != expected:
                raise ValueError('cold full edge function proof mismatch')
        for identifier, function in functions.items():
            expected = _function(function['original_triangle'], [proof for proof in edge_proofs.values() if any((side['triangle_id'] == identifier for side in proof['sides']))], context, manifest['parameters'])
            if expected != function:
                raise ValueError('cold source-relative raw function mismatch')
    return package

def save_source_conforming_banks(package, directory, *, resource_check=None):
    validate_source_conforming_banks(package)
    target = _i46_Path(directory)
    if target.exists():
        raise FileExistsError(target)
    files = {'manifest.json': package['manifest'], 'connection-queue.json': package['queue']}
    for kind in ('raw', 'proofs', 'effects'):
        files.update({kind + '/' + chunk['chunk_id'] + '.json': chunk for chunk in package[kind]})
    if len(files) > MAX_FILES:
        raise MemoryError('source-conforming file count budget exceeded')
    for name, record in files.items():
        _rss_guard(resource_check)
        if _record_bytes(record) > package['manifest']['budgets']['max_shard_bytes']:
            raise MemoryError('new candidate file exceeds bounded byte budget: ' + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _i46_tempfile.TemporaryDirectory(prefix='.source-conforming-', dir=target.parent) as staging:
        staging_path = _i46_Path(staging) / 'package'
        for name, record in files.items():
            _rss_guard(resource_check)
            _write_record(staging_path / name, record)
        _rss_guard(resource_check)
        staging_path.rename(target)
    return target

def load_source_conforming_banks(directory, *, expected_manifest_sha256, expected_manifest_identity, **parents):
    from terrain_pipeline.common_infra import file_sha256 as _i46_file_sha256
    target = _i46_Path(directory)

    def read(path):
        if path.stat().st_size > _i46_MAX_BYTES:
            raise MemoryError('saved source-conforming file exceeds 64MiB')
        return _i46_json.loads(path.read_bytes())
    if _i46_file_sha256(target / 'manifest.json') != expected_manifest_sha256:
        raise ValueError('external manifest SHA mismatch')
    manifest = read(target / 'manifest.json')
    if manifest['identity_sha256'] != expected_manifest_identity:
        raise ValueError('external manifest identity mismatch')
    package = {'manifest': manifest, 'queue': read(target / 'connection-queue.json')}
    for kind in ('raw', 'proofs', 'effects'):
        if len(manifest['chunk_identities'][kind]) > MAX_FILES:
            raise MemoryError('saved chunk count exceeded')
        package[kind] = [read(target / kind / (kind + '-' + str(index).zfill(4) + '.json')) for index in range(len(manifest['chunk_identities'][kind]))]
    return validate_source_conforming_banks(package, **parents)
TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_SCHEMA = 'td-source-conforming-banks-v3'
TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_ALGORITHM = 'native-bilinear-minus-legacy-matched-shared-knot-affine-depth-fan-v3'
TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_FLAGS = TD_SOURCE_CONFORMING_BANKS_FLAGS
TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_BYTES, MAX_CELLS, TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_RSS = (_i46_MAX_BYTES, _i46_MAX_CELLS, MAX_RSS)
POLICY = {'algorithm': TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_ALGORITHM, 'legacy_depth': 'native_segment_source_minus_unchanged_legacy_line_whole_coefficients', 'legacy_quadratic': 'refuse_nonzero_source_quadratic_no_joint_neighbor_version', 'incident_knots': 'legacy_constraint_propagates_to_all_incident_edges_before_fan_build', 'interior_depth': 'original_shared_T_vertex_interpolation_unless_legacy_constrained', 'uncovered_nonzero': 'classify_from_original_sections_paths_but_refuse_without_bound_BC', 'nonnegative': 'strict_no_clamp', 'gates': 'unchanged_v2_maxcut_wet_source_coverage_atomic_signed_material'}
POLICY_IDENTITY_SHA256 = _record_identity(POLICY)
td_source_conforming_banks_mechanism_3_evaluate_bank_function = evaluate_bank_function

def _td_source_conforming_banks_mechanism_3_seal(record):
    record.pop('identity_sha256', None)
    record['policy_identity_sha256'] = POLICY_IDENTITY_SHA256
    return _seal(record)

def _bucket(point):
    return tuple((int(_i47_np.floor(value / GEOMETRY_TOLERANCE_M)) for value in point))

def _constraint(context, point):
    registry = context.setdefault('v3_legacy_knots', {})
    bucket = _bucket(point)
    found = []
    for horizontal in (-1, 0, 1):
        for vertical in (-1, 0, 1):
            for record in registry.get((bucket[0] + horizontal, bucket[1] + vertical), []):
                if max((abs(first - second) for first, second in zip(point, record['xz_m']))) <= GEOMETRY_TOLERANCE_M:
                    found.append(record)
    return found

def _register_legacy_knots(segment, context):
    start, end = (_i47_np.asarray(segment['start_xz_m']), _i47_np.asarray(segment['end_xz_m']))
    legacy = [side for side in segment['sides'] if side['triangle_id'].startswith('legacy06:')]
    if not legacy:
        return
    for side in legacy:
        for point in (start, end):
            sample = _source_sample(context, *map(float, point))
            if sample['height_m'] is None:
                continue
            depth = sample['height_m'] - _edge_y(side, point)
            existing = _constraint(context, point)
            if existing:
                if abs(existing[0]['cut_depth_m'] - depth) > FUNCTION_TOLERANCE_M:
                    existing[0]['conflicting_legacy_depth'] = True
                continue
            record = {'xz_m': point.tolist(), 'cut_depth_m': float(depth), 'legacy_triangle_id': side['triangle_id'], 'legacy_edge_index': side['edge_index'], 'legacy_segment_id': segment['segment_id'], 'conflicting_legacy_depth': False}
            context['v3_legacy_knots'].setdefault(_bucket(point), []).append(record)

def _boundary_evidence(sections, paths):
    incoming = _i47_defaultdict(list)
    arcs = {arc['arc_id']: arc for arc in paths.get('arcs', [])}
    nodes = {node['node_id']: node for node in sections.get('node_sections', [])}
    for arc in arcs.values():
        for first, second in zip(arc['node_ids'], arc['node_ids'][1:]):
            incoming[second].append({'arc_id': arc['arc_id'], 'from_node_id': first})
    evidence = {}
    mesh = sections['mesh']
    for section_index, section in enumerate(sections['edge_sections']):
        profiles = section.get('cross_section_xyz_m', [])
        if not profiles or not section.get('node_ids'):
            continue
        node_id = section['node_ids'][0]
        arc = arcs.get(section['arc_id'])
        node = nodes.get(node_id)
        bound = arc is not None and arc['node_ids'][:2] == section['node_ids'][:2] and (node is not None) and (node.get('cross_section_xyz_m') == profiles[0]) and (not node.get('rejection_reasons', [])) and _i47_np.isfinite(node.get('representative_q_m3_s', _i47_np.nan)) and (node.get('representative_q_m3_s', 0.0) > 0.0)
        for triangle_index in section['triangle_indices']:
            indices = mesh['triangles'][triangle_index]
            for edge_index in range(3):
                points = [mesh['vertices_xyz_m'][indices[edge_index]], mesh['vertices_xyz_m'][indices[(edge_index + 1) % 3]]]
                if not any((points == [first, second] or points == [second, first] for first, second in zip(profiles[0], profiles[0][1:]))):
                    continue
                evidence['06:' + str(triangle_index) + ':' + str(edge_index)] = {'classification': 'upstream_profile_without_bound_BC' if bound and (not incoming[node_id]) else 'truncated_bank', 'sections_identity_sha256': sections['identity_sha256'], 'paths_identity_sha256': paths['identity_sha256'], 'section_index': section_index, 'arc_id': section['arc_id'], 'node_id': node_id, 'profile_index': 0, 'original_edge_xyz_m': points, 'original_profile_xyz_m': profiles[0], 'ordinary_identity_sha256': sections.get('ordinary_identity_sha256'), 'representative_q_m3_s': None if node is None else node.get('representative_q_m3_s'), 'incoming_path_steps': incoming[node_id], 'section_path_profile_bound': bool(bound), 'boundary_condition_bound': False, 'hydraulic_inflow_claimed': False}
    return evidence

def _td_source_conforming_banks_mechanism_3_proof(segment, context):
    from terrain_pipeline.td_fine_bed_raster import _digest as _i46__digest
    original = _proof(segment, context)
    reasons = set(original['rejection_reasons'])
    reasons.difference_update({'unchanged_neighbor_quadratic_function_mismatch', 'uncovered_boundary_has_nonzero_depth', 'boundary_knot_fill_or_unknown', 'shared_depth_knot_mismatch'})
    parameters = context['v3_parameters']
    source = original['source']
    points = [_i47_np.asarray(segment[name]) for name in ('start_xz_m', 'end_xz_m')]
    legacy = [side for side in segment['sides'] if side['triangle_id'].startswith('legacy06:')]
    neighbors, differences = ([], [])
    depths = list(original['side_depth_knots'][0]['depth_knots_m'])
    constraints = []
    for endpoint, point in enumerate(points):
        records = _constraint(context, point)
        constraint = records[0] if records else None
        constraints.append(None if constraint is None else dict(constraint))
        if constraint is not None:
            depths[endpoint] = constraint['cut_depth_m']
            if constraint['conflicting_legacy_depth'] or any((abs(record['cut_depth_m'] - depths[endpoint]) > FUNCTION_TOLERANCE_M for record in records)):
                reasons.add('incident_legacy_knot_depth_conflict')
    coefficients = None
    if source is not None and legacy:
        native = source['source_coefficients_m_t012']
        if abs(native[2]) > FUNCTION_TOLERANCE_M:
            reasons.add('legacy_source_quadratic_requires_joint_version')
        for side in legacy:
            bed_start, bed_end = [_edge_y(side, point) for point in points]
            bed = [bed_start, bed_end - bed_start, 0.0]
            neighbors.append({'triangle_id': side['triangle_id'], 'edge_index': side['edge_index'], 'bed_coefficients_m_t012': bed})
        bed = neighbors[0]['bed_coefficients_m_t012']
        matching_depths = [sample['height_m'] - _edge_y(legacy[0], point) if sample['height_m'] is not None else None for sample, point in zip(original['source_samples'], points)]
        coefficients = None if any((depth is None for depth in matching_depths)) else [matching_depths[0], matching_depths[1] - matching_depths[0]]
        if any((depth is not None and depth < 0 for depth in matching_depths)):
            reasons.add('legacy_matching_negative_depth')
        if any((depth is None or value is None or abs(depth - value) > FUNCTION_TOLERANCE_M for depth, value in zip(depths, matching_depths))):
            reasons.add('incident_legacy_knot_depth_conflict')
        for neighbor in neighbors:
            if coefficients is None:
                continue
            difference = [native[0] - coefficients[0] - neighbor['bed_coefficients_m_t012'][0], native[1] - coefficients[1] - neighbor['bed_coefficients_m_t012'][1], native[2]]
            differences.append({'triangle_id': neighbor['triangle_id'], 'edge_index': neighbor['edge_index'], 'difference_coefficients_m_t012': difference})
            if max((abs(value) for value in difference)) > FUNCTION_TOLERANCE_M:
                reasons.add('legacy_whole_coefficient_mismatch')
        depths = matching_depths
    elif all((depth is not None for depth in depths)):
        coefficients = [depths[0], depths[1] - depths[0]]
    if any((depth is None or not _i47_np.isfinite(depth) or depth < 0 for depth in depths)):
        reasons.add('boundary_knot_fill_or_unknown')
    if any((depth is not None and depth > parameters['max_cut_m'] + parameters['conflict_tolerance_m'] for depth in depths)):
        reasons.add('boundary_knot_cut_depth_exceeded')
    for sample, depth in zip(original['source_samples'], depths):
        if depth is not None and depth > parameters['conflict_tolerance_m'] and sample['wet_source_support']:
            reasons.add('lake_wet_boundary_knot_cut_refused')
    zero_boundary = original['boundary_condition'] == 'explicit_source_bank_zero_depth_v2'
    if zero_boundary and any((depth is not None and abs(depth) > FUNCTION_TOLERANCE_M for depth in depths)):
        reasons.add('source_bank_zero_depth_incident_conflict')
    boundary_evidence = None
    if len([side for side in segment['sides'] if not side['triangle_id'].startswith('legacy06:')]) > 2:
        reasons.add('nonmanifold_shared_segment')
    if len(segment['sides']) == 1:
        side = segment['sides'][0]
        boundary_evidence = context.get('v3_boundary_evidence', {}).get(side['triangle_id'] + ':' + str(side['edge_index']), {'classification': 'truncated_bank', 'boundary_condition_bound': False, 'hydraulic_inflow_claimed': False})
        if any((depth is not None and depth > FUNCTION_TOLERANCE_M for depth in depths)):
            reasons.add('uncovered_boundary_has_nonzero_depth')
    original['side_depth_knots'] = [{**side, 'depth_knots_m': depths} for side in original['side_depth_knots']]
    original['depth_coefficients_m_t01'] = None if reasons else coefficients
    original['common_function_identity_sha256'] = None if reasons else _i46__digest({'start_xz_m': points[0].tolist(), 'end_xz_m': points[1].tolist(), 'source': source, 'depth_coefficients_m_t01': coefficients, 'policy_identity_sha256': POLICY_IDENTITY_SHA256})
    original['boundary_condition'] = 'explicit_source_bank_zero_depth_v3' if zero_boundary else 'unchanged_legacy_whole_linear_match_v3' if legacy else 'unbound_uncovered_boundary_v3' if len(segment['sides']) == 1 else 'shared_incident_native_knot_depth_v3'
    original['boundary_evidence'] = boundary_evidence
    original['v3proof'] = {'policy_identity_sha256': POLICY_IDENTITY_SHA256, 'depth_rule': 'native_source_minus_legacy_line_v3' if legacy else 'shared_incident_native_knot_depth_v3', 'unchanged_neighbor_polynomials': neighbors, 'whole_coefficient_differences_m_t012': differences, 'knot_constraints': constraints, 'proposed_depth_coefficients_m_t01': coefficients}
    original['proof_method'] = 'whole_native_source_coefficients_and_incident_shared_affine_depth_v3'
    original['status'] = 'refused' if reasons else 'candidate'
    original['rejection_reasons'] = sorted(reasons)
    return _td_source_conforming_banks_mechanism_3_seal(original)

def build_edge_proofs(segments, context, parameters):
    """Prebind all legacy constraints before proving any incident edge."""
    context['v3_parameters'] = parameters
    context['v3_legacy_knots'] = {}
    for segment in segments:
        _register_legacy_knots(segment, context)
    return [_td_source_conforming_banks_mechanism_3_proof(segment, context) for segment in segments]

def build_triangle_function(triangle, edge_proofs, context, parameters):
    function = _function(triangle, edge_proofs, context, parameters)
    vertices = {}
    reasons = set(function['rejection_reasons'])
    for fan in function['fans']:
        for point, depth in zip(fan['vertices_xz_m'], fan['depth_at_vertices_m']):
            bucket = _bucket(point)
            for horizontal in (-1, 0, 1):
                for vertical in (-1, 0, 1):
                    for prior_point, prior_depth in vertices.get((bucket[0] + horizontal, bucket[1] + vertical), []):
                        if max((abs(first - second) for first, second in zip(point, prior_point))) <= GEOMETRY_TOLERANCE_M:
                            if abs(depth - prior_depth) > FUNCTION_TOLERANCE_M:
                                reasons.add('incident_fan_vertex_depth_discontinuity')
            vertices.setdefault(bucket, []).append((point, depth))
    function['status'] = 'refused' if reasons else 'candidate'
    function['rejection_reasons'] = sorted(reasons)
    function['incident_fan_vertex_depth_verified'] = not reasons
    return _td_source_conforming_banks_mechanism_3_seal(function)

def _td_source_conforming_banks_mechanism_3_chunks(kind, records, max_bytes, parent_identity):
    chunks, current, size = ([], [], 1024)
    for record in records:
        record['policy_identity_sha256'] = POLICY_IDENTITY_SHA256
        record_size = _record_bytes(record) + 1
        if record_size + 1024 > max_bytes:
            raise MemoryError('single v3 record exceeds bounded byte budget')
        if current and size + record_size > max_bytes:
            chunks.append(_td_source_conforming_banks_mechanism_3_seal({'schema': TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_SCHEMA + '-' + kind, 'parent_identity_sha256': parent_identity, 'chunk_id': kind + '-' + str(len(chunks)).zfill(4), 'records': current}))
            current, size = ([], 1024)
        current.append(record)
        size += record_size
    if current:
        chunks.append(_td_source_conforming_banks_mechanism_3_seal({'schema': TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_SCHEMA + '-' + kind, 'parent_identity_sha256': parent_identity, 'chunk_id': kind + '-' + str(len(chunks)).zfill(4), 'records': current}))
    if len(chunks) > MAX_FILES:
        raise MemoryError('v3 chunk count budget exceeded')
    return chunks

def td_source_conforming_banks_mechanism_3_build_source_conforming_banks(base, shard_package, hierarchy, sections, transitions, paths, readiness, *, input_pins=None, max_cells=MAX_CELLS, max_shard_bytes=TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_BYTES, resource_check=None):
    """Build a separate v3 candidate; original parent triangles and centers stay immutable."""
    from terrain_pipeline.td_fine_bed_raster import LEDGER_KEYS as _i46_LEDGER_KEYS
    from terrain_pipeline.td_fine_bed_raster import _context as _i46__context
    from terrain_pipeline.td_fine_bed_raster import _digest as _i46__digest
    from terrain_pipeline.td_fine_bed_shards import _cut as _i46__cut
    from terrain_pipeline.td_fine_bed_shards import _evaluate as _i46__evaluate
    from terrain_pipeline.td_fine_bed_shards import _ledger as _i46__ledger
    from terrain_pipeline.td_fine_bed_shards import iter_merged_cells as _i46_iter_merged_cells
    if type(max_cells) is not int or not 1 <= max_cells <= MAX_CELLS or type(max_shard_bytes) is not int or (not 4096 <= max_shard_bytes <= TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_BYTES):
        raise ValueError('invalid source-conforming resource budget')
    _rss_guard(resource_check, phase='parent_linkage')
    for name, record in (('hierarchy', hierarchy), ('sections', sections), ('transitions', transitions)):
        if base[name + '_identity_sha256'] != record['identity_sha256']:
            raise ValueError('immutable ' + name + ' linkage mismatch')
    if paths['identity_sha256'] != transitions['paths_identity_sha256'] or shard_package['manifest']['base_identity_sha256'] != base['identity_sha256'] or base['source_identity_sha256'] != hierarchy['metadata']['source_identity_sha256']:
        raise ValueError('immutable source/paths/shards linkage mismatch')
    parent_identity = shard_package['manifest']['identity_sha256']
    context = _i46__context(hierarchy, base['selected_leaf_ids'], base['wet_protection'])
    evidence = _boundary_evidence(sections, paths)
    context['v3_parameters'] = base['parameters']
    context['v3_boundary_evidence'] = evidence
    cells = {key: (cell, owner) for key, cell, owner in _i46_iter_merged_cells(base, shard_package['shards'])}
    if len(cells) > max_cells:
        raise MemoryError('merged parent exceeds unique-cell budget')
    _rss_guard(resource_check, phase='readonly_parent_cells', counters={'cells': len(cells)})
    triangles = {item['triangle_id']: item for item in base['triangles']}
    triangles.update({item['triangle_id']: item for item in shard_package['raw']['triangles']})
    if len(triangles) != len(base['triangles']):
        raise ValueError('parent triangle indices are duplicated or shard raw introduced new triangles')
    for triangle in triangles.values():
        mesh = sections['mesh'] if triangle['source_package'] == '06' else transitions['entries'][triangle['source_entry_index']]
        original_indices = mesh['triangles'][triangle['source_triangle_index']]
        if original_indices != triangle['source_vertex_indices'] or [mesh['vertices_xyz_m'][index] for index in original_indices] != triangle['vertices_xyz_m']:
            raise ValueError('original triangle indices/source XYZ chain mismatch')
    seeds = {proposal['triangle_id'] for cell, owner in cells.values() if 'fill_without_material' in cell['rejection_reasons'] for proposal in cell['triangle_sources']}
    if not seeds.issubset(triangles):
        raise ValueError('saved fill proposals missing original provenance')
    groups = _i47_defaultdict(list)
    bank_points = {tuple(point) for edge in sections['edge_sections'] for profile in edge.get('cross_section_xyz_m', []) for point in (profile[0], profile[-1])}
    for triangle in triangles.values():
        for edge_index in range(3):
            edge = _edge_record(triangle, edge_index)
            if triangle['source_package'] == '06':
                edge['zero_depth_boundary_eligible'] = all((tuple(point) in bank_points for point in edge['points_xyz_m']))
            else:
                entry = transitions['entries'][triangle['source_entry_index']]
                first_index = triangle['source_vertex_indices'][edge_index]
                second_index = triangle['source_vertex_indices'][(edge_index + 1) % 3]
                edge['zero_depth_boundary_eligible'] = first_index % 5 == second_index % 5 and first_index % 5 in (0, 4) or min(first_index, second_index) >= len(entry['vertices_xyz_m']) - 5
            groups[_line_key(_i47_np.asarray(edge['points_xyz_m'])[:, [0, 2]])].append(edge)
    original_mesh = sections['mesh']
    for index, indices in enumerate(original_mesh['triangles']):
        if '06:' + str(index) in triangles:
            continue
        legacy = {'triangle_id': 'legacy06:' + str(index), 'vertices_xyz_m': [original_mesh['vertices_xyz_m'][vertex] for vertex in indices]}
        for edge_index in range(3):
            edge = _edge_record(legacy, edge_index)
            key = _line_key(_i47_np.asarray(edge['points_xyz_m'])[:, [0, 2]])
            if key in groups:
                groups[key].append(edge)
    _rss_guard(resource_check, phase='edge_groups', counters={'groups': len(groups)})
    member_sets = _components(triangles, _iter_segments(groups, context), seeds)
    component_by_triangle = {identifier: component for component, members in member_sets.items() for identifier in members}
    reasons_by_component = _i47_defaultdict(set)
    _rss_guard(resource_check, phase='component_selection', counters={'triangles': len(component_by_triangle)})
    for number, segment in enumerate(_iter_segments(groups, context)):
        if number % 1024 == 0:
            _rss_guard(resource_check, phase='legacy_native_knot_prepass', counters={'visited_segments': number})
        if any((side['triangle_id'] in component_by_triangle for side in segment['sides'])):
            _register_legacy_knots(segment, context)
    proofs = []
    by_triangle = _i47_defaultdict(list)
    for segment in _iter_segments(groups, context):
        if not any((side['triangle_id'] in component_by_triangle for side in segment['sides'])):
            continue
        if len(proofs) % 256 == 0:
            _rss_guard(resource_check, phase='selected_proofs', counters={'proofs': len(proofs)})
        proof = _td_source_conforming_banks_mechanism_3_proof(segment, context)
        proofs.append(proof)
        for side in segment['sides']:
            identifier = side['triangle_id']
            by_triangle[identifier].append(proof)
            if identifier in component_by_triangle:
                reasons_by_component[component_by_triangle[identifier]].update(proof['rejection_reasons'])
    del groups, bank_points
    _i47_gc.collect()
    _rss_guard(resource_check, phase='selected_proofs_complete', counters={'proofs': len(proofs)})
    port_proofs = [_td_source_conforming_banks_mechanism_3_seal(record) for record in _port_proofs(transitions, sections, proofs, component_by_triangle, reasons_by_component)]
    functions = {}
    for number, identifier in enumerate(sorted(component_by_triangle)):
        if number % 128 == 0:
            _rss_guard(resource_check, phase='raw_functions', counters={'functions': number, 'proofs': len(proofs)})
        function = build_triangle_function(triangles[identifier], by_triangle[identifier], context, base['parameters'])
        functions[identifier] = function
        component = component_by_triangle[identifier]
        reasons_by_component[component].update(function['rejection_reasons'])
        if triangles[identifier]['status'] not in {'rasterized', 'no_center_coverage'}:
            reasons_by_component[component].add('parent_triangle_coverage_incomplete')
    context.get('bank_sample_cache', {}).clear()
    context.get('bank_patch_cache', {}).clear()
    context.get('v3_legacy_knots', {}).clear()
    del by_triangle
    _i47_gc.collect()
    _rss_guard(resource_check, phase='raw_functions_complete', counters={'functions': len(functions)})
    census = _i47_Counter((proposal['triangle_id'] for cell, owner in cells.values() for proposal in cell['triangle_sources']))
    for identifier, component in component_by_triangle.items():
        if census[identifier] != triangles[identifier].get('covered_centers', 0):
            reasons_by_component[component].add('saved_triangle_center_census_mismatch')
    affected_cells = [(key, cell, owner) for key, (cell, owner) in cells.items() if any((proposal['triangle_id'] in component_by_triangle for proposal in cell['triangle_sources']))]
    parent_cell_count = len(cells)
    original_fill_count = sum(('fill_without_material' in cell['rejection_reasons'] for cell, owner in cells.values()))
    del cells, census
    effects = []
    origin, spacing = (_i47_np.asarray(base['grid']['origin_m_xz']), base['grid']['spacing_m'])
    for number, (key, cell, owner) in enumerate(sorted(affected_cells)):
        if number % 4096 == 0:
            _rss_guard(resource_check, phase='effects', counters={'visited_cells': number, 'effects': len(effects)})
        components = {component_by_triangle[proposal['triangle_id']] for proposal in cell['triangle_sources'] if proposal['triangle_id'] in component_by_triangle}
        if any((reasons_by_component[component] for component in components)):
            continue
        point = origin + (_i47_np.array([key[1], key[0]]) + base['grid']['center_offset_cells']) * spacing
        source_height = cell['source_sample']['height_m']
        if source_height is None:
            for component in components:
                reasons_by_component[component].add('saved_source_unknown')
            continue
        proposals = []
        try:
            for original in cell['triangle_sources']:
                proposal = dict(original)
                if original['triangle_id'] in functions:
                    value = td_source_conforming_banks_mechanism_3_evaluate_bank_function(functions[original['triangle_id']], float(point[0]), float(point[1]), source_height)
                    proposal['legacy_absolute_bed_m'] = original['bed_m']
                    proposal.update(value)
                proposals.append(proposal)
            after = _i46__evaluate(cell['source_sample'], proposals, cell['local_index'], base['parameters'])
            if after['status'] != 'candidate':
                for component in components:
                    reasons_by_component[component].update(('v3_cell_gate:' + reason for reason in after['rejection_reasons']))
                continue
        except ValueError as error:
            for component in components:
                reasons_by_component[component].add('v3_cell_function:' + str(error))
            continue
        before_cut, after_cut = (_i46__cut(cell, spacing), _i46__cut(after, spacing))
        effects.append({'global_key_row_column': list(key), 'operation': 'replace', 'logical_owner': owner, 'component_ids': sorted(components), 'before_sha256': _i46__digest(cell), 'cell': after, 'before_cut_m3': before_cut, 'after_cut_m3': after_cut, 'cut_delta_m3': after_cut - before_cut, 'source_sample_reused': True, 'policy_identity_sha256': POLICY_IDENTITY_SHA256})
    changed = True
    while changed:
        changed = False
        for key, cell, owner in affected_cells:
            components = {component_by_triangle[item['triangle_id']] for item in cell['triangle_sources'] if item['triangle_id'] in component_by_triangle}
            if any((reasons_by_component[component] for component in components)):
                for component in components:
                    if not reasons_by_component[component]:
                        reasons_by_component[component].add('overlapping_refused_component')
                        changed = True
    effects = [effect for effect in effects if not any((reasons_by_component[item] for item in effect['component_ids']))]
    components = {component: {'component_id': component, 'triangle_ids': members, 'status': 'refused' if reasons_by_component[component] else 'candidate', 'rejection_reasons': sorted(reasons_by_component[component]), 'seed_triangle_ids': sorted(set(members).intersection(seeds)), 'union_method': 'entire_parent_shared_edge_component_including_T_junction_overlaps'} for component, members in member_sets.items()}
    queue = _connection_queue(transitions, paths, sections, readiness, component_by_triangle, components)
    queue['schema'] = TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_SCHEMA + '-connection-queue'
    _td_source_conforming_banks_mechanism_3_seal(queue)
    before_ledger = _i47_deepcopy(shard_package['manifest']['material_ledger_merged'])
    delta = _i46__ledger(_i47_math.fsum((effect['cut_delta_m3'] for effect in effects)))
    after_ledger = {name: before_ledger[name] + delta[name] for name in _i46_LEDGER_KEYS}
    package = {'raw': _td_source_conforming_banks_mechanism_3_chunks('raw', list(functions.values()), max_shard_bytes, parent_identity), 'proofs': _td_source_conforming_banks_mechanism_3_chunks('proofs', proofs + port_proofs, max_shard_bytes, parent_identity), 'effects': _td_source_conforming_banks_mechanism_3_chunks('effects', effects, max_shard_bytes, parent_identity), 'queue': queue}
    package['manifest'] = _td_source_conforming_banks_mechanism_3_seal({'schema': TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_SCHEMA, 'algorithm': TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_ALGORITHM, 'inputs': dict(input_pins or {}), 'policy': dict(POLICY), 'boundary_evidence': evidence, 'parent_identity_sha256': parent_identity, 'base_identity_sha256': base['identity_sha256'], 'hierarchy_identity_sha256': hierarchy['identity_sha256'], 'source_identity_sha256': base['source_identity_sha256'], 'sections_identity_sha256': sections['identity_sha256'], 'transitions_identity_sha256': transitions['identity_sha256'], 'paths_identity_sha256': paths['identity_sha256'], 'grid': _i47_deepcopy(base['grid']), 'selected_leaf_ids': list(base['selected_leaf_ids']), 'wet_protection': _i47_deepcopy(base['wet_protection']), 'parameters': _i47_deepcopy(base['parameters']), 'budgets': {'max_cells': max_cells, 'max_shard_bytes': max_shard_bytes, 'max_rss_bytes': TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_RSS}, 'proof_tolerances': {'geometry_m': GEOMETRY_TOLERANCE_M, 'function_m': FUNCTION_TOLERANCE_M}, 'components': list(components.values()), 'affected_global_keys_row_column': [list(item[0]) for item in sorted(affected_cells)], 'summary': {'parent_unique_cells': parent_cell_count, 'original_fill_refused_cells': original_fill_count, 'seed_triangles': len(seeds), 'affected_triangles': len(functions), 'affected_cells': len(affected_cells), 'replace_cells': len(effects), 'unchanged_parent_cells': parent_cell_count - len(effects), 'candidate_components': sum((item['status'] == 'candidate' for item in components.values())), 'refused_components': sum((item['status'] == 'refused' for item in components.values())), 'center_source_resamples': 0, 'new_lattice_cells': 0, 'water_solves': 0}, 'material_ledger_parent': before_ledger, 'material_ledger_delta': delta, 'material_ledger_candidate': after_ledger, 'chunk_identities': {kind: [chunk['identity_sha256'] for chunk in package[kind]] for kind in ('raw', 'proofs', 'effects')}, 'queue_identity_sha256': queue['identity_sha256'], 'old_mesh_passed': False, 'old_port_preservation_claimed': False, 'independent_audit_passed': False, **{flag: False for flag in TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_FLAGS}})
    _rss_guard(resource_check, phase='candidate_chunks_complete')
    td_source_conforming_banks_mechanism_3_validate_source_conforming_banks(package)
    return package

def td_source_conforming_banks_mechanism_3_validate_source_conforming_banks(package, *, base=None, shard_package=None, hierarchy=None, sections=None, paths=None):
    from terrain_pipeline.td_fine_bed_raster import LEDGER_KEYS as _i46_LEDGER_KEYS
    from terrain_pipeline.td_fine_bed_raster import _context as _i46__context
    from terrain_pipeline.td_fine_bed_raster import _digest as _i46__digest
    from terrain_pipeline.td_fine_bed_shards import _cut as _i46__cut
    from terrain_pipeline.td_fine_bed_shards import _ledger as _i46__ledger
    from terrain_pipeline.td_fine_bed_shards import iter_merged_cells as _i46_iter_merged_cells
    manifest = package['manifest']
    if manifest.get('policy') != POLICY or manifest.get('policy_identity_sha256') != POLICY_IDENTITY_SHA256:
        raise ValueError('v3 policy identity mismatch')
    if (sections is None) != (paths is None):
        raise ValueError('both sections and paths required for cold BC evidence')
    evidence = manifest['boundary_evidence']
    if sections is not None and evidence != _boundary_evidence(sections, paths):
        raise ValueError('v3 original section/path boundary evidence mismatch')
    proofs = [record for chunk in package['proofs'] for record in chunk['records'] if record['kind'] == 'edge_function_proof']
    for kind in ('raw', 'proofs', 'effects'):
        for chunk in package[kind]:
            if chunk.get('policy_identity_sha256') != POLICY_IDENTITY_SHA256:
                raise ValueError('v3 chunk policy mismatch')
            for record in chunk['records']:
                if record.get('policy_identity_sha256') != POLICY_IDENTITY_SHA256:
                    raise ValueError('v3 record policy mismatch')
    _check_identity(manifest)
    _check_identity(package['queue'])
    budgets = manifest['budgets']
    if manifest['schema'] != TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_SCHEMA or manifest['algorithm'] != TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_ALGORITHM or (not 1 <= budgets['max_cells'] <= MAX_CELLS) or (not 4096 <= budgets['max_shard_bytes'] <= TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_BYTES) or (budgets['max_rss_bytes'] != TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_RSS) or any((manifest.get(flag) is not False for flag in TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_FLAGS)) or (manifest['old_mesh_passed'] is not False) or (manifest['independent_audit_passed'] is not False):
        raise ValueError('source-conforming schema/budget/certification mismatch')
    if package['queue']['identity_sha256'] != manifest['queue_identity_sha256'] or package['queue']['schema'] != TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_SCHEMA + '-connection-queue':
        raise ValueError('connection queue pin/schema mismatch')
    parents = None
    if base is not None and shard_package is not None:
        if base['identity_sha256'] != manifest['base_identity_sha256'] or shard_package['manifest']['identity_sha256'] != manifest['parent_identity_sha256'] or base['grid'] != manifest['grid'] or (shard_package['manifest']['material_ledger_merged'] != manifest['material_ledger_parent']):
            raise ValueError('cold immutable parent linkage mismatch')
        parents = {key: (cell, owner) for key, cell, owner in _i46_iter_merged_cells(base, shard_package['shards'])}
    keys, deltas, functions, edge_proofs = (set(), [], {}, {})
    component_by_triangle = {identifier: component for component in manifest['components'] for identifier in component['triangle_ids']}
    if len(component_by_triangle) != sum((len(component['triangle_ids']) for component in manifest['components'])):
        raise ValueError('duplicate component triangle ownership')
    for kind in ('raw', 'proofs', 'effects'):
        if len(package[kind]) > MAX_FILES or [item['identity_sha256'] for item in package[kind]] != manifest['chunk_identities'][kind]:
            raise ValueError('chunk identity census mismatch')
        for chunk in package[kind]:
            _check_identity(chunk)
            if chunk['schema'] != TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_SCHEMA + '-' + kind or chunk['parent_identity_sha256'] != manifest['parent_identity_sha256'] or _record_bytes(chunk) > budgets['max_shard_bytes']:
                raise ValueError('chunk parent pin/schema/byte limit mismatch')
            for record in chunk['records']:
                if kind in ('raw', 'proofs'):
                    _check_identity(record)
                    if record['status'] not in {'candidate', 'refused'} or bool(record['rejection_reasons']) != (record['status'] == 'refused'):
                        raise ValueError('v3 status/reason mismatch')
                if kind == 'raw':
                    identifier = record['triangle_id']
                    if identifier in functions or identifier not in component_by_triangle:
                        raise ValueError('duplicate/unselected raw triangle')
                    functions[identifier] = record
                    if record['status'] == 'candidate' and any((depth < 0 for fan in record['fans'] for depth in fan['depth_at_vertices_m'])):
                        raise ValueError('negative candidate depth')
                elif kind == 'proofs':
                    if record['kind'] == 'edge_function_proof':
                        if record['segment_id'] in edge_proofs:
                            raise ValueError('duplicate edge proof')
                        edge_proofs[record['segment_id']] = record
                else:
                    key = tuple(record['global_key_row_column'])
                    if key in keys or record['operation'] != 'replace' or (not record['source_sample_reused']):
                        raise ValueError('duplicate/new center transaction')
                    keys.add(key)
                    cell = record['cell']
                    if any((component_by_triangle[item['triangle_id']]['status'] != 'candidate' for item in cell['triangle_sources'] if item['triangle_id'] in component_by_triangle)):
                        raise ValueError('effect applied refused component')
                    if parents is not None:
                        before, owner = parents[key]
                        if _i46__digest(before) != record['before_sha256'] or owner != record['logical_owner'] or before['source_sample'] != cell['source_sample'] or (abs(_i46__cut(before, manifest['grid']['spacing_m']) - record['before_cut_m3']) > 1e-10):
                            raise ValueError('effect parent/source/owner mismatch')
                    cut = _i46__cut(cell, manifest['grid']['spacing_m'])
                    if abs(cut - record['after_cut_m3']) > 1e-10 or abs(cut - record['before_cut_m3'] - record['cut_delta_m3']) > 1e-10:
                        raise ValueError('signed effect material mismatch')
                    deltas.append(record['cut_delta_m3'])
    if set(functions) != set(component_by_triangle) or len(keys) != manifest['summary']['replace_cells']:
        raise ValueError('complete affected union/effect census mismatch')
    if len(manifest['affected_global_keys_row_column']) != manifest['summary']['affected_cells']:
        raise ValueError('affected center census mismatch')
    if manifest['summary']['parent_unique_cells'] > budgets['max_cells'] or not keys.issubset({tuple(key) for key in manifest['affected_global_keys_row_column']}):
        raise ValueError('effect outside bounded affected union')
    expected_delta = _i46__ledger(_i47_math.fsum(deltas))
    for name in _i46_LEDGER_KEYS:
        if abs(expected_delta[name] - manifest['material_ledger_delta'][name]) > 1e-09 or abs(manifest['material_ledger_parent'][name] + expected_delta[name] - manifest['material_ledger_candidate'][name]) > 1e-09:
            raise ValueError('signed material ledger double count')
    for component in manifest['components']:
        if component['status'] not in {'candidate', 'refused'} or bool(component['rejection_reasons']) != (component['status'] == 'refused'):
            raise ValueError('component status/reason mismatch')
        if component['status'] == 'candidate' and any((functions[identifier]['status'] != 'candidate' for identifier in component['triangle_ids'])):
            raise ValueError('candidate component has refused raw function')
    if hierarchy is not None:
        if hierarchy['identity_sha256'] != manifest['hierarchy_identity_sha256']:
            raise ValueError('cold source identity mismatch')
        context = _i46__context(hierarchy, manifest['selected_leaf_ids'], manifest['wet_protection'])
        context['v3_parameters'] = manifest['parameters']
        context['v3_boundary_evidence'] = evidence
        for proof in edge_proofs.values():
            _register_legacy_knots(proof, context)
        by_triangle = _i47_defaultdict(list)
        for proof in edge_proofs.values():
            expected = _td_source_conforming_banks_mechanism_3_proof({name: proof[name] for name in ('segment_id', 'start_xz_m', 'end_xz_m', 'sides', 'depth_support_knots')}, context)
            if proof != expected:
                raise ValueError('cold full edge function proof mismatch: ' + proof['segment_id'])
            for side in proof['sides']:
                by_triangle[side['triangle_id']].append(proof)
        for identifier, function in functions.items():
            expected = build_triangle_function(function['original_triangle'], by_triangle[identifier], context, manifest['parameters'])
            if expected != function:
                raise ValueError('cold source-relative raw function mismatch')
    return package

def td_source_conforming_banks_mechanism_3_save_source_conforming_banks(package, directory, *, resource_check=None):
    td_source_conforming_banks_mechanism_3_validate_source_conforming_banks(package)
    target = _i47_Path(directory)
    if target.exists():
        raise FileExistsError(target)
    files = {'manifest.json': package['manifest'], 'connection-queue.json': package['queue']}
    for kind in ('raw', 'proofs', 'effects'):
        files.update({kind + '/' + chunk['chunk_id'] + '.json': chunk for chunk in package[kind]})
    if len(files) > MAX_FILES:
        raise MemoryError('source-conforming file count budget exceeded')
    for name, record in files.items():
        _rss_guard(resource_check)
        if _record_bytes(record) > package['manifest']['budgets']['max_shard_bytes']:
            raise MemoryError('new candidate file exceeds bounded byte budget: ' + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _i47_tempfile.TemporaryDirectory(prefix='.source-conforming-v3-', dir=target.parent) as staging:
        staging_path = _i47_Path(staging) / 'package'
        for name, record in files.items():
            _rss_guard(resource_check)
            _write_record(staging_path / name, record)
        _rss_guard(resource_check)
        staging_path.rename(target)
    return target

def td_source_conforming_banks_mechanism_3_load_source_conforming_banks(directory, *, expected_manifest_sha256, expected_manifest_identity, **parents):
    from terrain_pipeline.common_infra import file_sha256 as _i46_file_sha256
    target = _i47_Path(directory)

    def read(path):
        if path.stat().st_size > TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_BYTES:
            raise MemoryError('saved source-conforming file exceeds 64MiB')
        return _i47_json.loads(path.read_bytes())
    if _i46_file_sha256(target / 'manifest.json') != expected_manifest_sha256:
        raise ValueError('external manifest SHA mismatch')
    manifest = read(target / 'manifest.json')
    if manifest['identity_sha256'] != expected_manifest_identity:
        raise ValueError('external manifest identity mismatch')
    package = {'manifest': manifest, 'queue': read(target / 'connection-queue.json')}
    for kind in ('raw', 'proofs', 'effects'):
        if len(manifest['chunk_identities'][kind]) > MAX_FILES:
            raise MemoryError('saved chunk count exceeded')
        package[kind] = [read(target / kind / (kind + '-' + str(index).zfill(4) + '.json')) for index in range(len(manifest['chunk_identities'][kind]))]
    return td_source_conforming_banks_mechanism_3_validate_source_conforming_banks(package, **parents)
TD_WATERSHED_INTERFACE_PATCHES_SCHEMA = 'td-watershed-interface-patches-v1'
MAX_PATCHES = 100000
MAX_VERTICES = 1000000
MAX_TRIANGLES = 2000000
TD_WATERSHED_INTERFACE_PATCHES_MAX_BYTES = 32 * 1024 * 1024
TD_WATERSHED_INTERFACE_PATCHES_MAX_CUT_M = 4.0
EPS = 1e-09
FALSE_FLAGS = ('bed_changed', 'bed_rasterized', 'water_surface_meshed', 'hydraulic_solved', 'natural_outlet_certified', 'flow_regime_certified', 'publish_ready')

def _plain(value):
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, _i48_np.ndarray):
        return value.tolist()
    if isinstance(value, (_i48_np.integer, _i48_np.floating, _i48_np.bool_)):
        return value.item()
    return value

def _encoded(value):
    return _i48_json.dumps(_plain(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def _digest(value):
    return _i48_hashlib.sha256(_encoded(value)).hexdigest()

def _identity_payload(record):
    return {key: value for key, value in record.items() if key != 'identity_sha256'}

def _shape_payload(record):
    return [{key: patch[key] for key in ('patch_id', 'kind', 'node_ids', 'source_arc_ids', 'endpoint_xyz_m', 'shared_bed_m', 'cross_sections', 'vertices_xyz_m', 'triangles', 'boundary_edges', 'required_cut_m', 'status', 'rejection_reasons')} for patch in record['patches']]

def _finite_points(points, name):
    array = _i48_np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3 or (not _i48_np.isfinite(array).all()):
        raise ValueError(f'{name} must be finite Nx3')
    return array

def _point_equal(first, second):
    return _i48_np.allclose(_i48_np.asarray(first, dtype=float), _i48_np.asarray(second, dtype=float), atol=1e-08, rtol=0)

def _projected_area(vertices, triangle):
    points = _i48_np.asarray(vertices, dtype=float)[list(triangle)]
    first = points[1, [0, 2]] - points[0, [0, 2]]
    second = points[2, [0, 2]] - points[0, [0, 2]]
    return float(first[0] * second[1] - first[1] * second[0])

def _mesh_check(vertices, triangles):
    points = _finite_points(vertices, 'patch vertices') if vertices else _i48_np.empty((0, 3))
    edge_counts = {}
    signs = []
    for triangle in triangles:
        if len(triangle) != 3 or len(set(triangle)) != 3 or any((type(index) is not int for index in triangle)):
            return ('degenerate_or_invalid_triangle', 0)
        if any((index < 0 or index >= len(points) for index in triangle)):
            return ('triangle_vertex_out_of_range', 0)
        area = _projected_area(points, triangle)
        if abs(area) <= EPS:
            return ('degenerate_projected_triangle', 0)
        signs.append(area)
        for first, second in zip(triangle, triangle[1:] + triangle[:1]):
            edge = tuple(sorted((first, second)))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
            if edge_counts[edge] > 2:
                return ('nonmanifold_mesh_edge', max(edge_counts.values()))
    if signs and min(signs) < 0 < max(signs):
        return ('inconsistent_mesh_orientation', max(edge_counts.values(), default=0))
    return (None, max(edge_counts.values(), default=0))

def _node_maps(paths, sections):
    nodes = {item['node_id']: item for item in paths.get('nodes', [])}
    section_map = {item['node_id']: item for item in sections.get('node_sections', [])}
    if len(nodes) != len(paths.get('nodes', [])) or len(section_map) != len(sections.get('node_sections', [])):
        raise ValueError('duplicate path or section node')
    if set(nodes) - set(section_map):
        raise ValueError('paths contain nodes absent from sections')
    for node_id, node in nodes.items():
        section = section_map[node_id]
        if node['xyz_m'] != section['source_xyz_m']:
            raise ValueError('section source XYZ differs from shared path node')
        if not _i48_math.isfinite(float(section['bed_m'])):
            raise ValueError('nonfinite section bed')
    return (nodes, section_map)

def _land_incidence(paths):
    incidence = {}
    for arc in paths.get('arcs', []):
        if arc.get('kind') != 'land_channel' or len(arc.get('node_ids', [])) != 2:
            continue
        first, second = arc['node_ids']
        incidence.setdefault(first, []).append(arc)
        incidence.setdefault(second, []).append(arc)
    return incidence

def _patch_base(patch_id, kind, node_ids, arcs, endpoint_xyz, shared_bed, reasons=None):
    return {'patch_id': patch_id, 'kind': kind, 'node_ids': list(node_ids), 'source_arc_ids': sorted({arc['arc_id'] for arc in arcs}), 'endpoint_xyz_m': _i48_deepcopy(endpoint_xyz), 'shared_bed_m': float(shared_bed), 'cross_sections': [], 'vertices_xyz_m': [], 'triangles': [], 'boundary_edges': [], 'required_cut_m': 0.0, 'finite_length_m': 0.0, 'status': 'rejected', 'rejection_reasons': sorted(set(reasons or [])), 'parametric_only': True, 'source_bed_unchanged': True, 'generation_requested': False}

def _section_at_arc(node_id, arc, section_map):
    positions = [index for index, item in enumerate(arc['node_ids']) if item == node_id]
    if not positions:
        return None
    index = positions[0]
    section = section_map[node_id]
    cross = section.get('cross_section_xyz_m', [])
    if len(cross) != 4 or any((len(point) != 3 for point in cross)):
        return None
    return (_i48_np.asarray(cross, dtype=float), index)

def _make_junction(node_id, arcs, nodes, section_map):
    node = nodes[node_id]
    section = section_map[node_id]
    reasons = []
    if any((set(nodes[item]['kinds']) & {'lake_covered', 'protected', 'lake_terminal'} for item in [node_id])):
        reasons.append('protected_or_lake_covered_node')
    if section.get('anchor') or 'anchor_cut_conflict' in section.get('rejection_reasons', []):
        reasons.append('lake_anchor_overlap')
    profiles = []
    for arc in arcs:
        result = _section_at_arc(node_id, arc, section_map)
        if result is None:
            reasons.append('missing_shared_cross_section')
        else:
            profiles.append(result[0])
    patch = _patch_base('junction:' + node_id, 'junction', [node_id], arcs, [node['xyz_m']], section['bed_m'], reasons)
    hard_reasons = [reason for reason in reasons if reason != 'missing_shared_cross_section']
    if hard_reasons:
        patch['rejection_reasons'] = sorted(set(hard_reasons))
        return patch
    if len(profiles) < 3:
        patch['rejection_reasons'] = ['junction_requires_three_land_arms']
        return patch
    center = _i48_np.asarray(node['xyz_m'], dtype=float).copy()
    center[1] = float(section['bed_m'])
    width = max(float(section.get('width_m', 0.0)), 0.7)
    bank_height = max(float(section.get('depth_m', 0.0)), 0.0)
    ring = []
    for arc in arcs:
        first, second = arc['node_ids']
        other_id = second if first == node_id else first
        other = _i48_np.asarray(nodes[other_id]['xyz_m'], dtype=float)
        direction = other[[0, 2]] - center[[0, 2]]
        length = float(_i48_np.linalg.norm(direction))
        if length <= EPS:
            patch['rejection_reasons'].append('zero_length_junction_arm')
            return patch
        direction /= length
        normal = _i48_np.asarray([-direction[1], direction[0]])
        arm_length = min(0.45 * length, max(width, 1.0))
        midpoint = center[[0, 2]] + direction * arm_length
        bank_y = max(float(section['bed_m']), float(center[1] + bank_height))
        ring.extend([[float(midpoint[0] - normal[0] * width / 2.0), bank_y, float(midpoint[1] - normal[1] * width / 2.0)], [float(midpoint[0] + normal[0] * width / 2.0), bank_y, float(midpoint[1] + normal[1] * width / 2.0)]])
    order = _i48_np.argsort(_i48_np.arctan2(_i48_np.asarray(ring)[:, 2] - center[2], _i48_np.asarray(ring)[:, 0] - center[0]))
    ring = [ring[int(index)] for index in order]
    vertices = [center.tolist()] + ring
    triangles = [[0, 1 + index, 1 + (index + 1) % len(ring)] for index in range(len(ring))]
    if any((_projected_area(vertices, triangle) < 0.0 for triangle in triangles)):
        triangles = [triangle[::-1] for triangle in triangles]
    problem, incidence = _mesh_check(vertices, triangles)
    if problem:
        patch['rejection_reasons'].append(problem)
        return patch
    if any((float(point[1]) < float(section['bed_m']) - EPS for point in vertices)):
        patch['rejection_reasons'].append('junction_below_shared_bed')
        return patch
    patch.update({'cross_sections': [profile.tolist() for profile in profiles], 'vertices_xyz_m': vertices, 'triangles': triangles, 'boundary_edges': [[1 + index, 1 + (index + 1) % len(ring)] for index in range(len(ring))], 'status': 'candidate', 'mesh_edge_incidence_max': incidence})
    return patch

def _make_anchor(node_id, arcs, nodes, section_map, max_cut_m):
    node = nodes[node_id]
    section = section_map[node_id]
    patch = _patch_base('anchor:' + node_id, 'lake_anchor_transition', [node_id], arcs, [node['xyz_m']], section['bed_m'])
    if 'lake_covered' in node['kinds'] or 'protected' in node['kinds']:
        patch['rejection_reasons'].append('protected_or_lake_covered_node')
    if not arcs:
        patch['rejection_reasons'].append('no_land_channel_anchor_arm')
        return patch
    result = _section_at_arc(node_id, arcs[0], section_map)
    if result is None:
        patch['rejection_reasons'].append('missing_anchor_cross_section')
        return patch
    profile = result[0]
    source_bed = float(node['xyz_m'][1])
    if abs(float(section['bed_m']) - source_bed) > 1e-08 or float(section.get('depth_m', 0.0)) != 0.0:
        patch['rejection_reasons'].append('anchor_does_not_return_to_original_bed')
        return patch
    max_cut = max((source_bed - float(point[1]) for point in profile))
    if max_cut > max_cut_m + EPS:
        patch['rejection_reasons'].append('anchor_cut_budget_exceeded')
        return patch
    if any((float(point[1]) < source_bed - max_cut_m - EPS for point in profile)):
        patch['rejection_reasons'].append('anchor_source_bed_conflict')
        return patch
    anchor = _i48_np.asarray([point[:] for point in profile], dtype=float)
    anchor[:, 1] = source_bed
    first, second = arcs[0]['node_ids']
    other_id = second if first == node_id else first
    direction = _i48_np.asarray(nodes[other_id]['xyz_m'], dtype=float)[[0, 2]] - _i48_np.asarray(node['xyz_m'], dtype=float)[[0, 2]]
    length = float(_i48_np.linalg.norm(direction))
    if length <= EPS:
        patch['rejection_reasons'].append('zero_length_anchor_arm')
        return patch
    direction /= length
    transition_length = min(length * 0.45, max(float(section.get('width_m', 0.0)), 1.0))
    candidate = profile.copy()
    candidate[:, 0] += direction[0] * transition_length
    candidate[:, 2] += direction[1] * transition_length
    vertices = anchor.tolist() + candidate.tolist()
    triangles = []
    for index in range(3):
        triangles.extend(([index, 4 + index, index + 1], [index + 1, 4 + index, 4 + index + 1]))
    problem, incidence = _mesh_check(vertices, triangles)
    if problem:
        patch['rejection_reasons'].append(problem)
        return patch
    patch.update({'cross_sections': [anchor.tolist(), candidate.tolist()], 'vertices_xyz_m': vertices, 'triangles': triangles, 'boundary_edges': [[index, index + 1] for index in range(3)] + [[4 + index, 4 + index + 1] for index in range(3)], 'required_cut_m': float(max_cut), 'finite_length_m': transition_length, 'status': 'candidate', 'mesh_edge_incidence_max': incidence})
    return patch

def _make_corner(node_id, arcs, nodes, section_map):
    patch = _patch_base('corner:' + node_id, 'corner_transition', [node_id], arcs, [nodes[node_id]['xyz_m']], section_map[node_id]['bed_m'])
    if len(arcs) != 2:
        patch['rejection_reasons'].append('corner_requires_two_land_arms')
        return patch
    profiles = [_section_at_arc(node_id, arc, section_map) for arc in arcs]
    if any((item is None for item in profiles)):
        patch['rejection_reasons'].append('missing_corner_cross_section')
        return patch
    first, second = (item[0] for item in profiles)
    center = (first + second) / 2.0
    shifted = []
    for arc in arcs:
        start, end = arc['node_ids']
        other_id = end if start == node_id else start
        direction = _i48_np.asarray(nodes[other_id]['xyz_m'], dtype=float)[[0, 2]] - _i48_np.asarray(nodes[node_id]['xyz_m'], dtype=float)[[0, 2]]
        length = float(_i48_np.linalg.norm(direction))
        if length <= EPS:
            patch['rejection_reasons'].append('zero_length_corner_arm')
            return patch
        direction /= length
        distance = min(length * 0.35, max(float(section_map[node_id].get('width_m', 0.0)), 1.0))
        candidate = center.copy()
        candidate[:, 0] += direction[0] * distance
        candidate[:, 2] += direction[1] * distance
        shifted.append(candidate)
    vertices = center.tolist() + shifted[0].tolist() + shifted[1].tolist()
    triangles = []
    for first_offset, second_offset in ((0, 4), (4, 8)):
        for index in range(3):
            triangles.extend(([first_offset + index, second_offset + index, first_offset + index + 1], [first_offset + index + 1, second_offset + index, second_offset + index + 1]))
    for start in (0, 6):
        if _projected_area(vertices, triangles[start]) < 0.0:
            for index in range(start, start + 6):
                triangles[index] = triangles[index][::-1]
    problem, incidence = _mesh_check(vertices, triangles)
    if problem:
        patch['rejection_reasons'].append(problem)
        return patch
    patch.update({'cross_sections': [center.tolist(), shifted[0].tolist(), shifted[1].tolist()], 'vertices_xyz_m': vertices, 'triangles': triangles, 'boundary_edges': [[index, index + 1] for index in range(3)] + [[8 + index, 8 + index + 1] for index in range(3)], 'status': 'candidate', 'mesh_edge_incidence_max': incidence})
    return patch

def build_watershed_interface_patches(paths, sections, *, max_cut_m=TD_WATERSHED_INTERFACE_PATCHES_MAX_CUT_M):
    """Build bounded local candidates from saved task06 records only."""
    if paths.get('schema') != 'td-watershed-paths-v1' or sections.get('schema') != 'td-watershed-sections-v1':
        raise ValueError('task06 paths/sections records required')
    if type(max_cut_m) not in (int, float) or not _i48_math.isfinite(max_cut_m) or max_cut_m <= 0:
        raise ValueError('positive finite max_cut_m required')
    nodes, section_map = _node_maps(paths, sections)
    incidence = _land_incidence(paths)
    patches = []
    for node_id in sorted(incidence):
        node = nodes[node_id]
        section = section_map[node_id]
        kinds = set(node['kinds'])
        if len(incidence[node_id]) >= 3 or section.get('junction') or 'needs_junction_patch' in section.get('rejection_reasons', []):
            patches.append(_make_junction(node_id, incidence[node_id], nodes, section_map))
        elif section.get('anchor') or kinds.intersection({'lake_entry', 'lake_interface'}):
            patches.append(_make_anchor(node_id, incidence[node_id], nodes, section_map, float(max_cut_m)))
        elif len(incidence[node_id]) == 2:
            patches.append(_make_corner(node_id, incidence[node_id], nodes, section_map))
    if len(patches) > MAX_PATCHES:
        raise MemoryError('interface patch budget exceeded')
    result = {'schema': TD_WATERSHED_INTERFACE_PATCHES_SCHEMA, 'algorithm': 'saved-watershed-local-interface-patches-v1', 'coordinate_system': 'model_xyz_m_original_bed', 'source_identity_sha256': paths['source_identity_sha256'], 'hierarchy_identity_sha256': paths['hierarchy_identity_sha256'], 'topology_identity_sha256': paths['topology_identity_sha256'], 'ordinary_identity_sha256': paths['ordinary_identity_sha256'], 'composite_parent_identity': {'paths': paths.get('identity_sha256'), 'sections': sections.get('identity_sha256')}, 'parameters': {'max_cut_m': float(max_cut_m)}, 'patches': patches, 'shape_identity_sha256': _digest(_shape_payload({'patches': patches})), 'summary': {'total': len(patches), 'candidate': sum((item['status'] == 'candidate' for item in patches)), 'rejected': sum((item['status'] == 'rejected' for item in patches)), 'by_kind': {kind: sum((item['kind'] == kind for item in patches)) for kind in ('junction', 'lake_anchor_transition', 'corner_transition')}}, 'budgets': {'max_patches': MAX_PATCHES, 'max_vertices': MAX_VERTICES, 'max_triangles': MAX_TRIANGLES, 'max_json_bytes': TD_WATERSHED_INTERFACE_PATCHES_MAX_BYTES}, 'parametric_only': True, 'source_bed_unchanged': True, 'candidate_semantics': 'local_geometry_candidate_with_open_boundaries; no bed mutation or hydraulic solve', **{name: False for name in FALSE_FLAGS}}
    result['identity_sha256'] = _digest(_identity_payload(result))
    validate_watershed_interface_patches(result)
    return result

def validate_watershed_interface_patches(record):
    """Validate finite local geometry, pins, flags, and resource limits."""
    if record.get('schema') != TD_WATERSHED_INTERFACE_PATCHES_SCHEMA or record.get('algorithm') != 'saved-watershed-local-interface-patches-v1':
        raise ValueError('patch schema mismatch')
    if record.get('identity_sha256') != _digest(_identity_payload(record)):
        raise ValueError('patch identity mismatch')
    if record.get('shape_identity_sha256') != _digest(_shape_payload(record)):
        raise ValueError('patch shape identity mismatch')
    if any((record.get(name) is not False for name in FALSE_FLAGS)) or record.get('parametric_only') is not True:
        raise ValueError('patch candidate flags must remain false')
    if len(record.get('patches', [])) > MAX_PATCHES:
        raise ValueError('patch count budget exceeded')
    vertices = triangles = 0
    for patch in record['patches']:
        if patch['status'] not in {'candidate', 'rejected'} or patch['parametric_only'] is not True:
            raise ValueError('invalid patch status or semantics')
        points = _finite_points(patch['vertices_xyz_m'], 'patch vertices') if patch['vertices_xyz_m'] else _i48_np.empty((0, 3))
        vertices += len(points)
        triangles += len(patch['triangles'])
        if patch['status'] == 'rejected' and patch['triangles']:
            raise ValueError('rejected patch contains mesh')
        if patch['status'] == 'candidate':
            if not patch['triangles'] or patch['rejection_reasons']:
                raise ValueError('candidate patch must have a clean mesh')
            problem, incidence = _mesh_check(patch['vertices_xyz_m'], patch['triangles'])
            if problem or incidence > 2:
                raise ValueError('candidate patch mesh invalid')
            if patch.get('mesh_edge_incidence_max') != incidence:
                raise ValueError('patch incidence summary mismatch')
        if float(patch['required_cut_m']) > float(record['parameters']['max_cut_m']) + EPS:
            raise ValueError('patch cut budget exceeded')
        if any((not _i48_math.isfinite(float(value)) for value in patch['endpoint_xyz_m'][0])):
            raise ValueError('nonfinite patch endpoint')
    if vertices > MAX_VERTICES or triangles > MAX_TRIANGLES:
        raise ValueError('patch geometry budget exceeded')
    expected = record['summary']
    if expected['total'] != len(record['patches']):
        raise ValueError('patch summary total mismatch')
    if expected['candidate'] != sum((item['status'] == 'candidate' for item in record['patches'])):
        raise ValueError('patch summary candidate mismatch')
    if expected['rejected'] != sum((item['status'] == 'rejected' for item in record['patches'])):
        raise ValueError('patch summary rejected mismatch')
    return record

def save_watershed_interface_patches(record, path):
    validate_watershed_interface_patches(record)
    payload = _encoded(record)
    if len(payload) > TD_WATERSHED_INTERFACE_PATCHES_MAX_BYTES:
        raise ValueError('patch JSON byte budget exceeded')
    target = _i48_Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target

def load_watershed_interface_patches(path, *, expected_sha256=None, expected_identity=None):
    target = _i48_Path(path)
    if target.stat().st_size > TD_WATERSHED_INTERFACE_PATCHES_MAX_BYTES:
        raise ValueError('patch JSON byte budget exceeded')
    payload = target.read_bytes()
    if expected_sha256 is not None and _i48_hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError('patch file hash mismatch')
    record = _i48_json.loads(payload)
    validate_watershed_interface_patches(record)
    if expected_identity is not None and record['identity_sha256'] != expected_identity:
        raise ValueError('patch identity mismatch')
    return record
build_interface_patches = build_watershed_interface_patches
validate_interface_patches = validate_watershed_interface_patches
save_interface_patches = save_watershed_interface_patches
load_interface_patches = load_watershed_interface_patches
TD_WATERSHED_PATHS_SCHEMA = 'td-watershed-paths-v1'
TD_WATERSHED_PATHS_ALGORITHM = 'native-receiver-local-area-retained-lake-support-v1'
TD_WATERSHED_PATHS_MAX_BYTES = 32 * 1024 ** 2
TD_WATERSHED_PATHS_MAX_CELLS = 250000
MAX_ARCS = 250000
MAX_PATH_SAMPLES = 1000000
TD_WATERSHED_PATHS_FLAGS = ('hydraulic_ready', 'hydraulic_verified', 'natural_outlet_verified', 'publishable', 'permanent_trunk_ready', 'permanent_river_verified', 'transient_converged', 'solver_advanced', 'bed_changed', 'water_generated')
INTERFACES = {'lake_entry', 'lake_interface', 'spill', 'engineering', 'lake_terminal'}
SUPPORT_KINDS = {'source_lake_approach', 'cross_face', 'downhill_terrain_approach', 'engineering_outlet_support', 'lake_entry_support', 'lake_receiver_support'}

def _td_watershed_paths_positive(value, name):
    if type(value) not in (float, int) or not _i49_math.isfinite(value) or value <= 0:
        raise ValueError('invalid ' + name)
    return float(value)

def _pin(record, name):
    value = record.get(name)
    if not isinstance(value, str) or len(value) != 64 or any((character not in '0123456789abcdef' for character in value)):
        raise ValueError('invalid identity: ' + name)
    return value

def _payload(record):
    payload = _i49_json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if len(payload) > TD_WATERSHED_PATHS_MAX_BYTES:
        raise MemoryError('watershed paths exceed 32MiB')
    return payload

def _td_watershed_paths_inputs(graph, hierarchy, ordinary):
    from terrain_pipeline.common_infra import identity as _i49_identity
    from terrain_pipeline.basin_topology import validate_basin_hierarchy as _i49_validate_basin_hierarchy
    from terrain_pipeline.basin_topology import build_outlet_forest as _i49_build_outlet_forest
    from terrain_pipeline.basin_topology import digest as _i49_digest
    _i49_validate_basin_hierarchy(hierarchy)
    if graph.get('schema') != 'td-lake-spill-graph-v1' or graph.get('identity_sha256') != _i49_digest({key: value for key, value in graph.items() if key != 'identity_sha256'}):
        raise ValueError('graph identity/schema mismatch')
    if any((graph.get(name) is not False for name in ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'permanent_trunk_ready', 'solver_advanced', 'bed_changed', 'water_generated'))):
        raise ValueError('graph certification or mutation claim')
    metadata = ordinary['metadata']
    if metadata.get('schema') != 'td-basin-runoff-exchange-v1' or ordinary.get('identity_sha256') != _i49_identity(ordinary['arrays'], metadata) or graph['event_identity_sha256']['ordinary'] != ordinary['identity_sha256'] or (metadata['topology_identity_sha256'] != graph['topology_identity_sha256']) or (metadata['hierarchy_identity_sha256'] != hierarchy['identity_sha256']) or (graph['hierarchy_identity_sha256'] != hierarchy['identity_sha256']) or (metadata['source_identity_sha256'] != hierarchy['metadata']['source_identity_sha256']) or (graph['source_identity_sha256'] != metadata['source_identity_sha256']):
        raise ValueError('ordinary/graph/hierarchy/source identity mismatch')
    if any((metadata.get(name) is not False for name in ('hydraulic_ready', 'transient_converged', 'natural_outlet_verified', 'publishable'))):
        raise ValueError('ordinary certification claim')
    for values in ordinary['arrays'].values():
        if not isinstance(values, _i49_np.ndarray) or not _i49_np.isfinite(values).all():
            raise ValueError('ordinary contains nonfinite/nonarray data')
    arrays = hierarchy['arrays']
    owner = arrays['contribution_owner'].ravel()
    valid = arrays['valid_mask'].ravel()
    leaves = [int(leaf) for leaf in _i49_np.unique(owner[valid])]
    if [node['leaf_id'] for node in graph['nodes']] != leaves:
        raise ValueError('graph nodes differ from actual contribution leaf order')
    stages = ordinary['arrays']['stage_m']
    if stages.ndim != 2 or stages.shape != (metadata['steps'] + 1, len(leaves)) or (not _i49_np.isfinite(stages).all()) or (metadata['duration_s'] != 86400.0) or (metadata['timestep_s'] != 300.0):
        raise ValueError('ordinary full saved-stage dimensions/time mismatch')
    spacing = float(hierarchy['metadata']['spacing_m'])
    blocked = []
    for position, node in enumerate(graph['nodes']):
        leaf = leaves[position]
        cells = _i49_np.flatnonzero(valid & (owner == leaf))
        sinks = cells[arrays['receiver'][cells] < 0]
        if len(sinks) != 1 or node['terminal_cell_id'] != int(sinks[0]) or node['exclusive_area_m2'] != len(cells) * spacing ** 2 or (node['ordinary_stage_max_m'] != float(stages[:, position].max())):
            raise ValueError('graph basin differs from actual bed/stages')
        reasons = []
        if arrays['node_unknown_contact'][leaf]:
            reasons.append('unknown_contact')
        if arrays['protected_mask'].ravel()[cells].any():
            reasons.append('protected_basin')
        if node['blocked_reasons'] != reasons:
            raise ValueError('graph basin protection/unknown mismatch')
        if reasons:
            blocked.append(leaf)
    edges = [{'face_id': edge['face_id'], 'source_leaf_id': edge['source_leaf_id'], 'receiver_leaf_id': edge['receiver_leaf_id'], 'net_m3': abs(edge['ordinary']['net_m3'])} for edge in graph['edges'] if edge['routing_eligible']]
    outlets = [{'leaf_id': outlet['leaf_id'], 'cell_id': outlet['cell_id'], 'outflow_m3': outlet['outflow_m3']} for outlet in graph['outlets'] if outlet['routing_eligible']]
    forest = _i49_build_outlet_forest(leaves, [node['exclusive_area_m2'] for node in graph['nodes']], edges, outlets, blocked_leaf_ids=blocked)
    if forest != graph['routing_forest']:
        raise ValueError('graph parent/main paths differ from deterministic forest')
    primary = forest['primary_component']
    if primary is None:
        raise ValueError('graph has no primary outlet component')
    return (forest, leaves, stages)

def _td_watershed_paths_build(graph, hierarchy, ordinary, minimum_area_m2):
    from terrain_pipeline.basin_topology import trace_engineering_outlet as _i49_trace_engineering_outlet
    from terrain_pipeline.basin_topology import trace_spill_connection as _i49_trace_spill_connection
    from terrain_pipeline.basin_topology import digest as _i49_digest
    from terrain_pipeline.basin_topology import sampled_stage as _i49_sampled_stage
    minimum_area = _td_watershed_paths_positive(minimum_area_m2, 'minimum_area_m2')
    forest, leaves, stages = _td_watershed_paths_inputs(graph, hierarchy, ordinary)
    primary = forest['primary_component']
    selected = primary['leaf_ids']
    selected_set = set(selected)
    arrays = hierarchy['arrays']
    bed = arrays['height_m'].ravel()
    owner = arrays['contribution_owner'].ravel()
    receiver = arrays['receiver']
    valid = arrays['valid_mask'].ravel()
    protected = arrays['protected_mask'].ravel()
    cell_owner = arrays['cell_owner'].ravel()
    unknown = arrays['node_unknown_contact']
    spacing = float(hierarchy['metadata']['spacing_m'])
    origin = hierarchy['metadata']['origin_m_xz']
    columns = arrays['height_m'].shape[1]
    cells = _i49_np.flatnonzero(valid & _i49_np.isin(owner, selected))
    if len(bed) > TD_WATERSHED_PATHS_MAX_CELLS or len(cells) > TD_WATERSHED_PATHS_MAX_CELLS:
        raise MemoryError('native cell budget exceeded')
    if protected[cells].any() or unknown[cell_owner[cells]].any() or unknown[selected].any():
        raise ValueError('primary component touches protected/unknown cells')
    active = _i49_np.zeros(len(bed), bool)
    active[cells] = True
    incoming = _i49_np.zeros(len(bed), _i49_np.int64)
    for cell in cells:
        target = int(receiver[cell])
        if target >= 0:
            if not active[target]:
                raise ValueError('receiver leaves selected contribution cells')
            incoming[target] += 1
    pending = incoming.copy()
    area = _i49_np.zeros(len(bed), _i49_np.float64)
    area[cells] = spacing ** 2
    queue = _i49_deque((int(cell) for cell in cells if pending[cell] == 0))
    visited = 0
    while queue:
        cell = queue.popleft()
        visited += 1
        target = int(receiver[cell])
        if target >= 0:
            area[target] += area[cell]
            pending[target] -= 1
            if pending[target] == 0:
                queue.append(target)
    if visited != len(cells) or not _i49_np.isfinite(area[cells]).all():
        raise ValueError('receiver cycle/nonfinite local accumulation')
    maximum_stage = {leaf: float(stages[:, leaves.index(leaf)].max()) for leaf in selected}
    main_faces = set(forest['main_path_face_ids'])
    main_receiver_pairs = set()
    for edge in graph['edges']:
        if edge['face_id'] in main_faces:
            route = edge['geometry']['downhill_terrain_approach']['cell_ids']
            main_receiver_pairs.update(zip(route, route[1:]))
    nodes = {}
    arcs = []
    sample_count = 0

    def node(cell, kind):
        cell = int(cell)
        if not 0 <= cell < len(bed) or not active[cell]:
            raise ValueError('support cell outside selected valid cells')
        if cell not in nodes:
            row, column = divmod(cell, columns)
            nodes[cell] = {'node_id': f'cell:{cell}', 'cell_id': cell, 'xyz_m': [float(origin[0] + column * spacing), float(bed[cell]), float(origin[1] + row * spacing)], 'kinds': set(), 'leaf_id': int(owner[cell]), 'local_upstream_area_m2': float(area[cell])}
        nodes[cell]['kinds'].add(kind)
        if bed[cell] <= maximum_stage[int(owner[cell])]:
            nodes[cell]['kinds'].add('lake_covered')
        if incoming[cell] >= 2:
            nodes[cell]['kinds'].add('confluence')
        return nodes[cell]

    def arc(arc_id, kind, route, leaf, face_id=None, main=False, support=None, sample=None):
        nonlocal sample_count
        route = [int(cell) for cell in route]
        if not route:
            raise ValueError('empty path')
        sample_count += len(route)
        if len(arcs) >= MAX_ARCS or sample_count > MAX_PATH_SAMPLES:
            raise MemoryError('arc/path sample budget exceeded')
        points = [node(cell, kind) for cell in route]
        for first, second in zip(route, route[1:]):
            if abs(first // columns - second // columns) + abs(first % columns - second % columns) != 1:
                raise ValueError('non D4 arc')
        item = {'arc_id': arc_id, 'kind': kind, 'node_ids': [point['node_id'] for point in points], 'cell_ids': route, 'xyz_m': [point['xyz_m'][:] for point in points], 'leaf_id': int(leaf), 'face_id': face_id, 'is_main_path': bool(main), 'channel_candidate': kind == 'land_channel', 'local_upstream_area_m2': float(area[route[0]])}
        if support is not None:
            if support['xyz_m'] != item['xyz_m']:
                raise ValueError('saved support coordinates differ from actual bed')
            item['source_geometry'] = _i49_deepcopy(support)
        if sample is not None:
            item['sampled_source_stage'] = _i49_deepcopy(sample)
        arcs.append(item)
        return item
    lakes = []
    graph_nodes = {item['leaf_id']: item for item in graph['nodes']}
    for leaf in selected:
        terminal = graph_nodes[leaf]['terminal_cell_id']
        node(terminal, 'lake_terminal')
        leaf_cells = cells[owner[cells] == leaf]
        covered = leaf_cells[bed[leaf_cells] <= maximum_stage[leaf]]
        lakes.append({'leaf_id': leaf, 'terminal_node_id': f'cell:{terminal}', 'terminal_cell_id': terminal, 'ordinary_stage_max_m': maximum_stage[leaf], 'stage_semantics': 'maximum over all ordinary saved stages; not simultaneous water geometry', 'covered_cell_ids': [int(cell) for cell in covered], 'exclusive_area_m2': len(leaf_cells) * spacing ** 2, 'local_terminal_upstream_area_m2': float(area[terminal]), 'entry_node_ids': [], 'entry_interfaces': [], 'spill_node_ids': [], 'engineering_node_ids': []})
    lake_lookup = {lake['leaf_id']: lake for lake in lakes}
    for cell in cells:
        target = int(receiver[cell])
        if target < 0 or area[cell] < minimum_area:
            continue
        leaf = int(owner[cell])
        dry_source = bed[cell] > maximum_stage[leaf]
        dry_target = bed[target] > maximum_stage[leaf]
        if dry_source and dry_target:
            kind = 'land_channel'
        elif dry_source:
            kind = 'lake_entry_support'
        else:
            kind = 'lake_receiver_support'
        item = arc(f'receiver:{int(cell)}:{target}', kind, [cell, target], leaf, main=(int(cell), target) in main_receiver_pairs)
        if dry_source and (not dry_target):
            node(cell, 'lake_entry')
            node(target, 'lake_entry')
            node(cell, 'lake_interface')
            node(target, 'lake_interface')
            interface = {'land_node_id': f'cell:{int(cell)}', 'wet_node_id': f'cell:{target}', 'support_arc_id': item['arc_id']}
            item['lake_interface'] = _i49_deepcopy(interface)
            item['interface_node_ids'] = [interface['land_node_id'], interface['wet_node_id']]
            lake_lookup[leaf]['entry_interfaces'].append(interface)
    parent_records = {record['leaf_id']: record for record in forest['records']}
    edge_lookup = {edge['face_id']: (position, edge) for position, edge in enumerate(graph['edges'])}
    for leaf in selected:
        parent = parent_records[leaf]
        if parent['parent_leaf_id'] is None:
            continue
        position, edge = edge_lookup[parent['parent_face_id']]
        if edge['source_leaf_id'] != leaf or edge['receiver_leaf_id'] != parent['parent_leaf_id'] or edge['receiver_leaf_id'] not in selected_set:
            raise ValueError('selected parent face orientation mismatch')
        directional = edge['ordinary']['direction'] * (ordinary['arrays']['face_forward_m3'][:, position] - ordinary['arrays']['face_reverse_m3'][:, position])
        sample = _i49_sampled_stage(ordinary, leaves.index(leaf), directional)
        if sample is None or edge['sampled_source_stage'] != sample:
            raise ValueError('source active maximum sampled stage mismatch')
        expected = _i49_trace_spill_connection(hierarchy, edge, leaf, edge['receiver_leaf_id'], source_stage_m=sample['stage_m'])
        if expected['status'] != 'accepted' or expected != edge['geometry']:
            raise ValueError('selected saved geometry differs from actual receiver/face')
        for kind in ('source_lake_approach', 'cross_face', 'downhill_terrain_approach'):
            support = expected[kind]
            support_leaf = edge['receiver_leaf_id'] if kind == 'downhill_terrain_approach' else leaf
            arc(f"face:{edge['face_id']}:{kind}", kind, support['cell_ids'], support_leaf, edge['face_id'], edge['face_id'] in main_faces, support, sample)
        for cell in expected['cross_face']['cell_ids']:
            node(cell, 'spill')
    roots = [(position, outlet) for position, outlet in enumerate(graph['outlets']) if outlet['routing_eligible'] and outlet['leaf_id'] == primary['root_leaf_id'] and (outlet['cell_id'] == primary['root_boundary_cell_id'])]
    if len(roots) != 1:
        raise ValueError('primary root engineering outlet mismatch')
    position, outlet = roots[0]
    sample = _i49_sampled_stage(ordinary, leaves.index(outlet['leaf_id']), ordinary['arrays']['engineering_boundary_outflow_m3'][:, position])
    if sample is None or sample != outlet['sampled_source_stage']:
        raise ValueError('root maximum sampled stage mismatch')
    expected = _i49_trace_engineering_outlet(hierarchy, outlet, source_stage_m=sample['stage_m'])
    if expected['status'] != 'accepted' or expected != outlet['geometry']:
        raise ValueError('root geometry differs from actual engineering perimeter')
    support = expected['source_lake_approach']
    arc(f"outlet:{outlet['cell_id']}", 'engineering_outlet_support', support['cell_ids'], outlet['leaf_id'], main=True, support=support, sample=sample)
    node(outlet['cell_id'], 'engineering')
    for lake in lakes:
        for kind, field in (('lake_entry', 'entry_node_ids'), ('spill', 'spill_node_ids'), ('engineering', 'engineering_node_ids')):
            lake[field] = [nodes[cell]['node_id'] for cell in sorted(nodes) if nodes[cell]['leaf_id'] == lake['leaf_id'] and kind in nodes[cell]['kinds']]
    for point in nodes.values():
        point['kinds'] = sorted(point['kinds'])
        point['lake_interfaces'] = sorted(INTERFACES.intersection(point['kinds']))
    result = {'schema': TD_WATERSHED_PATHS_SCHEMA, 'algorithm': TD_WATERSHED_PATHS_ALGORITHM, 'coordinate_system': 'model_xyz_m_original_bed', 'grid_shape': list(arrays['height_m'].shape), 'spacing_m': spacing, 'origin_m_xz': [float(value) for value in origin], 'graph_identity_sha256': graph['identity_sha256'], 'source_identity_sha256': graph['source_identity_sha256'], 'hierarchy_identity_sha256': hierarchy['identity_sha256'], 'ordinary_identity_sha256': ordinary['identity_sha256'], 'topology_identity_sha256': graph['topology_identity_sha256'], 'parameters': {'minimum_area_m2': minimum_area}, 'selected_leaf_ids': list(selected), 'nodes': [nodes[cell] for cell in sorted(nodes)], 'arcs': sorted(arcs, key=lambda item: item['arc_id']), 'lakes': lakes, 'budget': {'max_cells': TD_WATERSHED_PATHS_MAX_CELLS, 'max_arcs': MAX_ARCS, 'max_path_samples': MAX_PATH_SAMPLES, 'max_bytes': TD_WATERSHED_PATHS_MAX_BYTES, 'selected_valid_cells': len(cells), 'path_samples': sample_count}, 'semantics': 'local area is native receiver upstream cell area, not forest event support; support arcs never authorize carving', **{name: False for name in TD_WATERSHED_PATHS_FLAGS}}
    result['identity_sha256'] = _i49_digest(result)
    _payload(result)
    return result

def build_watershed_paths(graph, hierarchy, ordinary, *, minimum_area_m2=3600.0):
    """Return a source-pinned JSON record; never modify inputs or invoke a solver."""
    result = _td_watershed_paths_build(graph, hierarchy, ordinary, minimum_area_m2)
    validate_watershed_paths(result)
    return result

def validate_watershed_paths(paths, graph=None, hierarchy=None, ordinary=None):
    """Validate stored structure; with all parents, verify exact source geometry."""
    from terrain_pipeline.basin_topology import digest as _i49_digest
    _payload(paths)
    if paths.get('schema') != TD_WATERSHED_PATHS_SCHEMA or paths.get('algorithm') != TD_WATERSHED_PATHS_ALGORITHM or paths.get('identity_sha256') != _i49_digest({key: value for key, value in paths.items() if key != 'identity_sha256'}) or any((paths.get(name) is not False for name in TD_WATERSHED_PATHS_FLAGS)):
        raise ValueError('watershed paths schema/identity/flags mismatch')
    for name in ('identity_sha256', 'graph_identity_sha256', 'source_identity_sha256', 'hierarchy_identity_sha256', 'ordinary_identity_sha256', 'topology_identity_sha256'):
        _pin(paths, name)
    minimum = _td_watershed_paths_positive(paths['parameters']['minimum_area_m2'], 'minimum_area_m2')
    spacing = _td_watershed_paths_positive(paths['spacing_m'], 'spacing_m')
    shape = paths['grid_shape']
    origin = paths['origin_m_xz']
    if len(shape) != 2 or any((type(size) is not int or size <= 0 for size in shape)) or _i49_math.prod(shape) > TD_WATERSHED_PATHS_MAX_CELLS or (len(origin) != 2) or any((type(value) not in (int, float) or not _i49_math.isfinite(value) for value in origin)):
        raise ValueError('invalid native grid geometry')
    selected = paths['selected_leaf_ids']
    if not selected or any((type(leaf) is not int or leaf < 0 for leaf in selected)) or selected != sorted(set(selected)):
        raise ValueError('invalid selected leaves')
    if len(paths['nodes']) > TD_WATERSHED_PATHS_MAX_CELLS or len(paths['arcs']) > MAX_ARCS:
        raise MemoryError('node/arc budget exceeded')
    nodes = {}
    for point in paths['nodes']:
        cell = point['cell_id']
        kinds = point['kinds']
        if type(cell) is not int or not 0 <= cell < _i49_math.prod(shape) or point['node_id'] != f'cell:{cell}' or (point['node_id'] in nodes) or (point['leaf_id'] not in selected) or (not kinds) or any((not isinstance(kind, str) for kind in kinds)) or (kinds != sorted(set(kinds))) or (point['lake_interfaces'] != sorted(INTERFACES.intersection(kinds))) or (len(point['xyz_m']) != 3) or any((type(value) not in (int, float) or not _i49_math.isfinite(value) for value in point['xyz_m'])):
            raise ValueError('invalid/duplicate shared cell node')
        _td_watershed_paths_positive(point['local_upstream_area_m2'], 'local_upstream_area_m2')
        if point['xyz_m'][0] != origin[0] + cell % shape[1] * spacing or point['xyz_m'][2] != origin[1] + cell // shape[1] * spacing:
            raise ValueError('node coordinate differs from native cell')
        nodes[point['node_id']] = point
    lake_lookup = {}
    for lake in paths['lakes']:
        leaf = lake['leaf_id']
        terminal = nodes.get(lake['terminal_node_id'])
        if leaf not in selected or leaf in lake_lookup or terminal is None or (terminal['leaf_id'] != leaf) or ('lake_terminal' not in terminal['kinds']) or (type(lake['ordinary_stage_max_m']) not in (int, float)) or (not _i49_math.isfinite(lake['ordinary_stage_max_m'])):
            raise ValueError('invalid retained lake terminal/stage')
        lake_lookup[leaf] = lake
        for kind, field in (('lake_entry', 'entry_node_ids'), ('spill', 'spill_node_ids'), ('engineering', 'engineering_node_ids')):
            expected = [point['node_id'] for point in paths['nodes'] if point['leaf_id'] == leaf and kind in point['kinds']]
            if lake[field] != expected:
                raise ValueError('lake interface node mismatch')
    if set(lake_lookup) != set(selected):
        raise ValueError('missing retained lake')
    arc_ids = set()
    samples = 0
    for item in paths['arcs']:
        kind = item['kind']
        if not isinstance(item['arc_id'], str) or not item['arc_id'] or item['arc_id'] in arc_ids or (kind not in SUPPORT_KINDS | {'land_channel'}) or (item['leaf_id'] not in selected) or (type(item['is_main_path']) is not bool) or (item['channel_candidate'] is not (kind == 'land_channel')) or (not item['node_ids']) or (len(item['node_ids']) != len(item['cell_ids'])) or (len(item['node_ids']) != len(item['xyz_m'])):
            raise ValueError('invalid typed arc')
        arc_ids.add(item['arc_id'])
        samples += len(item['cell_ids'])
        for node_id, cell, xyz in zip(item['node_ids'], item['cell_ids'], item['xyz_m']):
            point = nodes.get(node_id)
            if point is None or point['cell_id'] != cell or point['xyz_m'] != xyz or (kind not in point['kinds']):
                raise ValueError('arc does not reference shared actual node')
        for first, second in zip(item['cell_ids'], item['cell_ids'][1:]):
            if abs(first // shape[1] - second // shape[1]) + abs(first % shape[1] - second % shape[1]) != 1:
                raise ValueError('non D4 stored path')
        if kind == 'land_channel':
            stage = lake_lookup[item['leaf_id']]['ordinary_stage_max_m']
            if len(item['node_ids']) != 2 or item['face_id'] is not None or item['local_upstream_area_m2'] != nodes[item['node_ids'][0]]['local_upstream_area_m2'] or (item['local_upstream_area_m2'] < minimum) or any((nodes[node_id]['leaf_id'] != item['leaf_id'] for node_id in item['node_ids'])) or any((xyz[1] <= stage for xyz in item['xyz_m'])) or (item['xyz_m'][1][1] > item['xyz_m'][0][1]):
                raise ValueError('land channel violates dry/nonascending/local-area contract')
        if 'lake_interface' in item:
            interface = item['lake_interface']
            interface_ids = [interface['land_node_id'], interface['wet_node_id']]
            if kind != 'lake_entry_support' or interface['support_arc_id'] != item['arc_id'] or item['node_ids'] != interface_ids or (item['interface_node_ids'] != interface_ids) or any(('lake_entry' not in nodes[node_id]['kinds'] or 'lake_interface' not in nodes[node_id]['kinds'] for node_id in interface_ids)) or (item['xyz_m'][0][1] <= lake_lookup[item['leaf_id']]['ordinary_stage_max_m']) or (item['xyz_m'][1][1] > lake_lookup[item['leaf_id']]['ordinary_stage_max_m']):
                raise ValueError('land/wet lake interface mismatch')
    for lake in paths['lakes']:
        expected = [item['lake_interface'] for item in paths['arcs'] if item['leaf_id'] == lake['leaf_id'] and 'lake_interface' in item]
        if sorted(lake['entry_interfaces'], key=lambda item: item['support_arc_id']) != expected:
            raise ValueError('structured lake entry interfaces mismatch')
    if samples > MAX_PATH_SAMPLES or paths['budget']['path_samples'] != samples:
        raise ValueError('path sample budget mismatch')
    budget = paths['budget']
    if budget['max_cells'] != TD_WATERSHED_PATHS_MAX_CELLS or budget['max_arcs'] != MAX_ARCS or budget['max_path_samples'] != MAX_PATH_SAMPLES or (budget['max_bytes'] != TD_WATERSHED_PATHS_MAX_BYTES) or (type(budget['selected_valid_cells']) is not int) or (not len(nodes) <= budget['selected_valid_cells'] <= TD_WATERSHED_PATHS_MAX_CELLS):
        raise ValueError('native geometry budget mismatch')
    parents = (graph, hierarchy, ordinary)
    if any((parent is not None for parent in parents)):
        if any((parent is None for parent in parents)):
            raise ValueError('exact validation requires graph, hierarchy and ordinary together')
        if paths != _td_watershed_paths_build(graph, hierarchy, ordinary, minimum):
            raise ValueError('watershed paths differ from actual pinned parents')
    return True

def save_watershed_paths(paths, path):
    """Atomically publish a finite, budgeted JSON artifact."""
    from terrain_pipeline.common_infra import publish_bytes as _i49_publish_bytes
    validate_watershed_paths(paths)
    _i49_publish_bytes(path, _payload(paths))

def load_watershed_paths(path, *, expected_sha256, expected_identity, graph=None, hierarchy=None, ordinary=None):
    """Cold-read a pinned artifact, optionally validating against all parents."""
    path = _i49_Path(path)
    if path.stat().st_size > TD_WATERSHED_PATHS_MAX_BYTES:
        raise MemoryError('watershed paths exceed 32MiB')
    payload = path.read_bytes()
    if len(payload) > TD_WATERSHED_PATHS_MAX_BYTES:
        raise MemoryError('watershed paths exceed 32MiB')
    if _i49_hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError('external watershed file SHA256 mismatch')
    paths = _i49_json.loads(payload)
    if paths.get('identity_sha256') != expected_identity:
        raise ValueError('external watershed identity mismatch')
    validate_watershed_paths(paths, graph, hierarchy, ordinary)
    return paths
TD_WATERSHED_SECTIONS_SCHEMA = 'td-watershed-sections-v1'
MAX_WINDOW_CELLS = 250000
TD_WATERSHED_SECTIONS_MAX_FINE_CELLS = 2000000
TD_WATERSHED_SECTIONS_FLAGS = ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'permanent_trunk_ready', 'material_budget_verified', 'new_bed_hydrology_verified', 'flow_regime_certified', 'junction_patch_ready')
ANCHORS = {'lake_entry', 'spill', 'engineering', 'lake_terminal'}

def _td_watershed_sections_encoded(value):
    return _i50_json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')

def _td_watershed_sections_digest(value):
    return _i50_hashlib.sha256(_td_watershed_sections_encoded(value)).hexdigest()

def _shape_identity(record):
    fields = ('schema', 'source_identity_sha256', 'hierarchy_identity_sha256', 'topology_identity_sha256', 'ordinary_identity_sha256', 'parameters', 'selected_leaf_ids', 'node_sections', 'mesh', 'edge_sections', 'support_arcs', 'reach_diagnostics', 'fine_requests', 'exchange_injections')
    return _td_watershed_sections_digest({field: record[field] for field in fields})

def _finite_array(value, shape, name, nonnegative=False):
    array = _i50_np.asarray(value, dtype=float)
    if array.shape != shape or not _i50_np.isfinite(array).all():
        raise ValueError(f'invalid {name}')
    if nonnegative and _i50_np.any(array < 0):
        raise ValueError(f'negative {name}')
    return array

def _carriers(hierarchy, topology, ordinary):
    arrays = hierarchy['arrays']
    height = _i50_np.asarray(arrays['height_m'])
    if height.ndim != 2 or not 0 < height.size <= TD_WATERSHED_PATHS_MAX_CELLS:
        raise ValueError('source grid budget exceeded')
    spacing = float(hierarchy['metadata']['spacing_m'])
    if not _i50_math.isfinite(spacing) or spacing <= 0:
        raise ValueError('invalid spacing')
    duration = float(ordinary['metadata']['duration_s'])
    if not _i50_math.isfinite(duration) or duration <= 0:
        raise ValueError('invalid ordinary duration')
    if topology.get('metadata', {}).get('hierarchy_identity_sha256', hierarchy['identity_sha256']) != hierarchy['identity_sha256']:
        raise ValueError('topology hierarchy mismatch')
    for parent, key in ((hierarchy, 'hierarchy_identity_sha256'), (topology, 'topology_identity_sha256')):
        if ordinary['metadata'].get(key, parent['identity_sha256']) != parent['identity_sha256']:
            raise ValueError('ordinary parent mismatch')
    leaves = [int(value) for value in topology['arrays']['leaf_ids']]
    lookup = {leaf: index for index, leaf in enumerate(leaves)}
    if len(lookup) != len(leaves):
        raise ValueError('duplicate leaves')
    effective_area = _finite_array(topology['arrays']['leaf_area_m2'], (len(leaves),), 'leaf area', True)
    if _i50_np.any(effective_area <= 0):
        raise ValueError('empty effective basin')
    event = ordinary['arrays']
    runoff = _i50_np.asarray(event['outflow_volume_m3'], dtype=float)
    if runoff.ndim != 2 or runoff.shape[1] != len(leaves) or (not len(runoff)):
        raise ValueError('invalid runoff shape')
    _finite_array(runoff, runoff.shape, 'runoff', True)
    stages = _i50_np.asarray(event['stage_m'], dtype=float)
    if stages.ndim != 2 or stages.shape[1] != len(leaves) or (not len(stages)):
        raise ValueError('invalid stages')
    _finite_array(stages, stages.shape, 'stages')
    owner = _i50_np.asarray(arrays['contribution_owner']).ravel()
    valid = _i50_np.asarray(arrays['valid_mask'], dtype=bool).ravel()
    protected = _i50_np.asarray(arrays['protected_mask'], dtype=bool).ravel()
    receiver = _i50_np.asarray(arrays['receiver']).ravel()
    if any((len(value) != height.size for value in (owner, valid, protected, receiver))):
        raise ValueError('source array shape mismatch')
    usable = valid & ~protected & _i50_np.isin(owner, leaves)
    if not _i50_np.isfinite(height.ravel()[usable]).all():
        raise ValueError('nonfinite usable heights')
    local_area = _i50_np.where(usable, spacing ** 2, 0.0)
    local_q = _i50_np.zeros(height.size)
    incoming_q = _i50_np.zeros(height.size)
    for leaf, position in lookup.items():
        cells = usable & (owner == leaf)
        if not _i50_math.isclose(float(cells.sum()) * spacing ** 2, effective_area[position], rel_tol=1e-09, abs_tol=1e-07):
            raise ValueError('effective area differs from usable source cells')
        local_q[cells] = float(runoff[:, position].sum()) / duration / effective_area[position] * spacing ** 2
    faces = topology['faces']
    forward = _finite_array(event['face_forward_m3'], (len(runoff), len(faces)), 'forward', True)
    reverse = _finite_array(event['face_reverse_m3'], forward.shape, 'reverse', True)
    seen = set()
    injections = []
    for position, face in enumerate(faces):
        if face['face_id'] in seen:
            raise ValueError('duplicate physical incoming face')
        seen.add(face['face_id'])
        signed = float((forward[:, position] - reverse[:, position]).sum())
        if signed == 0:
            continue
        receiver_leaf = int(face['leaf_ids'][1 if signed > 0 else 0])
        source_leaf = int(face['leaf_ids'][0 if signed > 0 else 1])
        cells = [int(cell) for cell in face['cell_ids']]
        if len(cells) != 2 or any((not 0 <= cell < height.size for cell in cells)):
            raise ValueError('invalid physical face')
        actual = _i50_np.asarray(arrays['face_cells'])[int(face['face_index'])].tolist()
        if cells != actual or sorted((int(owner[cell]) for cell in cells)) != list(face['leaf_ids']):
            raise ValueError('physical face ownership mismatch')
        target = next((cell for cell in cells if int(owner[cell]) == receiver_leaf))
        if not usable[target]:
            raise ValueError('incoming face not on usable receiver')
        incoming_q[target] += abs(signed) / duration
        injections.append({'face_id': face['face_id'], 'source_leaf_id': source_leaf, 'receiver_leaf_id': receiver_leaf, 'receiver_cell_id': target, 'net_volume_m3': abs(signed), 'representative_q_m3_s': abs(signed) / duration, 'semantics': 'actual_net_exchange_not_source_attribution'})
    indegree = _i50_np.zeros(height.size, dtype=_i50_np.int64)
    downstream = _i50_np.full(height.size, -1, dtype=_i50_np.int64)
    columns = height.shape[1]
    for cell in _i50_np.flatnonzero(usable):
        target = int(receiver[cell])
        if target == -1:
            continue
        if not 0 <= target < height.size or not usable[target] or owner[cell] != owner[target]:
            raise ValueError('receiver leaves usable contribution basin')
        row, column = divmod(int(cell), columns)
        target_row, target_column = divmod(target, columns)
        if abs(row - target_row) + abs(column - target_column) != 1:
            raise ValueError('non-D4 receiver')
        downstream[cell] = target
        indegree[target] += 1
    queue = _i50_deque((int(cell) for cell in _i50_np.flatnonzero(usable & (indegree == 0))))
    order = []
    while queue:
        cell = queue.popleft()
        order.append(cell)
        target = int(downstream[cell])
        if target >= 0:
            local_area[target] += local_area[cell]
            local_q[target] += local_q[cell]
            incoming_q[target] += incoming_q[cell]
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(order) != int(usable.sum()):
        raise ValueError('receiver cycle')
    return {'height': height, 'spacing': spacing, 'owner': owner, 'usable': usable, 'receiver': downstream, 'area': local_area, 'local_q': local_q, 'incoming_q': incoming_q, 'order': order, 'lookup': lookup, 'stage_max': stages.max(axis=0), 'injections': injections, 'duration': duration}

def _td_watershed_sections_sample(context, hierarchy, x_m, z_m):
    origin = hierarchy['metadata']['origin_m_xz']
    column = (x_m - float(origin[0])) / context['spacing']
    row = (z_m - float(origin[1])) / context['spacing']
    rows, columns = context['height'].shape
    if not 0 <= row <= rows - 1 or not 0 <= column <= columns - 1:
        raise ValueError('outside_source_coverage')
    row0, column0 = (_i50_math.floor(row), _i50_math.floor(column))
    row1, column1 = (min(row0 + 1, rows - 1), min(column0 + 1, columns - 1))
    corners = [row0 * columns + column0, row0 * columns + column1, row1 * columns + column0, row1 * columns + column1]
    valid = hierarchy['arrays']['valid_mask'].ravel()
    protected = hierarchy['arrays']['protected_mask'].ravel()
    if any((not valid[cell] for cell in corners)):
        raise ValueError('unknown_source_coverage')
    if any((protected[cell] for cell in corners)):
        raise ValueError('protected_source_coverage')
    if any((int(context['owner'][cell]) not in context['selected_leaves'] for cell in corners)):
        raise ValueError('outside_selected_component')
    fraction_row, fraction_column = (row - row0, column - column0)
    weights = [(1 - fraction_row) * (1 - fraction_column), (1 - fraction_row) * fraction_column, fraction_row * (1 - fraction_column), fraction_row * fraction_column]
    return float(sum((weight * context['height'].ravel()[cell] for weight, cell in zip(weights, corners))))

def _level(area, discharge, width, depth, recipe):
    from terrain_pipeline.td_natural_river_network import _level_value as _i50__level_value
    areas = (recipe.minimum_area_m2, recipe.seasonal_area_m2, recipe.perennial_area_m2, recipe.mainstem_area_m2)
    flows = (recipe.minimum_q_m3_s * (1.2 - 0.4 * recipe.material_erodibility), recipe.seasonal_q_m3_s, recipe.perennial_q_m3_s, recipe.mainstem_q_m3_s)
    level = None
    for index in range(4):
        if area >= areas[index] and discharge >= flows[index] and (width >= _i50__level_value(recipe, index, 'min_width_m')) and (depth >= _i50__level_value(recipe, index, 'min_depth_m')):
            level = index
    return level

def _triangle_buckets(points, spacing):
    first_column = _i50_math.floor(min((point[0] for point in points)) / spacing)
    last_column = _i50_math.floor(max((point[0] for point in points)) / spacing)
    first_row = _i50_math.floor(min((point[2] for point in points)) / spacing)
    last_row = _i50_math.floor(max((point[2] for point in points)) / spacing)
    return [(column, row) for column in range(first_column, last_column + 1) for row in range(first_row, last_row + 1)]

def _triangle_overlap(first, second):
    for triangle in (first, second):
        for index in range(3):
            start, end = (triangle[index], triangle[(index + 1) % 3])
            axis = [end[2] - start[2], start[0] - end[0]]
            length = _i50_math.hypot(*axis)
            if length < 1e-12:
                continue
            first_projection = [(point[0] * axis[0] + point[2] * axis[1]) / length for point in first]
            second_projection = [(point[0] * axis[0] + point[2] * axis[1]) / length for point in second]
            if min(max(first_projection), max(second_projection)) - max(min(first_projection), min(second_projection)) <= 1e-09:
                return False
    return True

def _register_triangles(vertices, triangles, incidence, buckets, spacing):
    staged_edges = {}
    staged_triangles = []
    staged_buckets = {}
    for triangle in triangles:
        points = [vertices[index] for index in triangle]
        signed_area = ((points[1][0] - points[0][0]) * (points[2][2] - points[0][2]) - (points[1][2] - points[0][2]) * (points[2][0] - points[0][0])) / 2
        if signed_area <= 1e-09:
            return 'nonpositive_projected_triangle_area'
        for first, second in zip(triangle, triangle[1:] + triangle[:1]):
            key = tuple(sorted((first, second)))
            directions = incidence.get(key, []) + staged_edges.get(key, [])
            if len(directions) >= 2:
                return 'nonmanifold_mesh_edge'
            if directions and directions[0] != (second, first):
                return 'inconsistent_mesh_edge_orientation'
            staged_edges.setdefault(key, []).append((first, second))
        keys = _triangle_buckets(points, spacing)
        nearby = {}
        for key in keys:
            for other in buckets.get(key, []) + staged_buckets.get(key, []):
                nearby[tuple(other)] = other
        for other in nearby.values():
            if _triangle_overlap(points, [vertices[index] for index in other]):
                return 'overlapping_mesh_triangles'
        staged_triangles.append((triangle, keys))
        for key in keys:
            staged_buckets.setdefault(key, []).append(triangle)
    for key, directions in staged_edges.items():
        incidence.setdefault(key, []).extend(directions)
    for triangle, keys in staged_triangles:
        for key in keys:
            buckets.setdefault(key, []).append(triangle)
    return None

def _fine_request(identifier, points, width, depth, level, reasons, context, hierarchy, remaining):
    from terrain_pipeline.td_natural_river_network import _level_value as _i50__level_value
    spacing = min(width / max(2.0, 2.0 * float('junction' in reasons or 'spill' in reasons or 'outlet' in reasons)), _i50__level_value(context['recipe'], level or 0, 'required_spacing_m'))
    margin = width / 2 + depth * _i50__level_value(context['recipe'], level or 0, 'bank_slope_h_per_v')
    margin += _i50__level_value(context['recipe'], level or 0, 'protection_distance_m')
    bbox = [min((point[0] for point in points)) - margin, min((point[2] for point in points)) - margin, max((point[0] for point in points)) + margin, max((point[2] for point in points)) + margin]
    extent = [_i50_math.floor(bbox[0] / spacing), _i50_math.floor(bbox[1] / spacing), _i50_math.ceil(bbox[2] / spacing), _i50_math.ceil(bbox[3] / spacing)]
    bbox = [extent[0] * spacing, extent[1] * spacing, extent[2] * spacing, extent[3] * spacing]
    shape = [extent[3] - extent[1] + 1, extent[2] - extent[0] + 1]
    cells = shape[0] * shape[1]
    refusal = []
    origin = hierarchy['metadata']['origin_m_xz']
    rows, columns = context['height'].shape
    first_column = _i50_math.floor((bbox[0] - origin[0]) / context['spacing'])
    last_column = _i50_math.ceil((bbox[2] - origin[0]) / context['spacing'])
    first_row = _i50_math.floor((bbox[1] - origin[1]) / context['spacing'])
    last_row = _i50_math.ceil((bbox[3] - origin[1]) / context['spacing'])
    if first_column < 0 or first_row < 0 or last_column >= columns or (last_row >= rows):
        refusal.append('outside_source_coverage')
    selection = _i50_np.s_[max(0, first_row):min(rows, last_row + 1), max(0, first_column):min(columns, last_column + 1)]
    arrays = hierarchy['arrays']
    if not arrays['valid_mask'][selection].all():
        refusal.append('unknown_source_coverage')
    if arrays['protected_mask'][selection].any():
        refusal.append('protected_source_coverage')
    if not _i50_np.isin(arrays['contribution_owner'][selection], list(context['selected_leaves'])).all():
        refusal.append('outside_selected_component')
    if arrays['open_boundary_mask'][selection].any():
        refusal.append('engineering_open_boundary_contact')
    if cells > MAX_WINDOW_CELLS:
        refusal.append('window_cell_budget_exceeded')
    if cells > remaining:
        refusal.append('total_fine_cell_budget_exceeded')
    return {'request_id': identifier, 'bbox_m_xz': bbox, 'window_bbox_m_xz': bbox, 'grid_extent': extent, 'grid_shape': shape, 'target_spacing_m': spacing, 'width_m': width, 'estimated_cells': cells, 'estimated_bytes': cells * 32, 'reasons': sorted(set(reasons)), 'refusal_reasons': refusal, 'status': 'refused' if refusal else 'requested', 'generation_requested': False, 'fine_dem_available': False, 'source_spacing_m': context['spacing'], 'semantics': 'spatial_resolution_requirement_not_resampled_fine_DEM'}

def build_watershed_sections(paths, hierarchy, topology, ordinary, recipe=None):
    """Build shared bank/bed candidates and explicit, budgeted fine requirements."""
    from terrain_pipeline.td_natural_river_network import LEVELS as _i50_LEVELS
    from terrain_pipeline.td_natural_river_network import NaturalNetworkRecipe as _i50_NaturalNetworkRecipe
    from terrain_pipeline.td_natural_river_network import _level_value as _i50__level_value
    from terrain_pipeline.td_natural_river_network import _width_depth as _i50__width_depth
    recipe = _i50_NaturalNetworkRecipe() if recipe is None else recipe
    if not isinstance(recipe, _i50_NaturalNetworkRecipe):
        raise ValueError('NaturalNetworkRecipe required')
    context = _carriers(hierarchy, topology, ordinary)
    context['recipe'] = recipe
    context['selected_leaves'] = set(paths['selected_leaf_ids'])
    nodes = {node['node_id']: node for node in paths['nodes']}
    if len(nodes) != len(paths['nodes']) or len(nodes) > TD_WATERSHED_PATHS_MAX_CELLS or len(paths['arcs']) > TD_WATERSHED_PATHS_MAX_CELLS:
        raise ValueError('path node/arc budget or uniqueness failure')
    for key, expected in (('hierarchy_identity_sha256', hierarchy['identity_sha256']), ('ordinary_identity_sha256', ordinary['identity_sha256'])):
        if paths.get(key, expected) != expected:
            raise ValueError('path parent mismatch')
    origin = hierarchy['metadata']['origin_m_xz']
    columns = context['height'].shape[1]
    for identifier, node in nodes.items():
        cell = node['cell_id']
        if type(cell) is not int or not 0 <= cell < context['height'].size or identifier != f'cell:{cell}':
            raise ValueError('invalid shared node')
        expected = [origin[0] + cell % columns * context['spacing'], float(context['height'].ravel()[cell]), origin[1] + cell // columns * context['spacing']]
        point = _finite_array(node['xyz_m'], (3,), 'node xyz')
        if not _i50_np.allclose(point, expected, atol=1e-08, rtol=0) or int(context['owner'][cell]) != node['leaf_id']:
            raise ValueError('node differs from native source')
        if not _i50_math.isclose(node['local_upstream_area_m2'], context['area'][cell], rel_tol=1e-09, abs_tol=1e-07):
            raise ValueError('node local receiver area mismatch')
    arcs = sorted(paths['arcs'], key=lambda arc: arc['arc_id'])
    if len({arc['arc_id'] for arc in arcs}) != len(arcs):
        raise ValueError('duplicate arc')
    land = []
    diagnostics = []
    support = []
    for arc in arcs:
        if arc['node_ids'] != [f'cell:{cell}' for cell in arc['cell_ids']]:
            raise ValueError('arc nodes differ from cells')
        if any((identifier not in nodes for identifier in arc['node_ids'])):
            raise ValueError('arc refers to missing node')
        if arc['xyz_m'] != [nodes[identifier]['xyz_m'] for identifier in arc['node_ids']]:
            raise ValueError('arc differs from original XYZ')
        if arc['kind'] != 'land_channel':
            if arc['channel_candidate']:
                raise ValueError('support arc cannot cut bed')
            support.append(_i50_deepcopy(arc))
            continue
        reasons = []
        cells = arc['cell_ids']
        if len(cells) != 2:
            raise ValueError('land arc must be a two-node receiver edge')
        first, second = cells
        if context['receiver'][first] != second:
            reasons.append('not_actual_receiver_D4')
        leaf = arc['leaf_id']
        if leaf not in context['lookup'] or any((context['owner'][cell] != leaf for cell in cells)):
            reasons.append('land_leaf_mismatch')
        elif any((context['height'].ravel()[cell] <= context['stage_max'][context['lookup'][leaf]] for cell in cells)):
            reasons.append('ordinary_lake_stage_contact')
        if not arc['channel_candidate'] or not context['usable'][cells].all():
            reasons.append('not_usable_land_candidate')
        diagnostic = {'arc_id': arc['arc_id'], 'node_ids': list(arc['node_ids']), 'kind': arc['kind'], 'is_main_path': arc['is_main_path'], 'rejection_reasons': reasons, 'status': 'rejected' if reasons else 'candidate', 'parametric_only': True, 'bed_rasterized': False}
        diagnostics.append(diagnostic)
        if not reasons:
            land.append((arc, diagnostic))
    incident = {}
    donors = {}
    for arc, diagnostic in land:
        first, second = arc['node_ids']
        incident.setdefault(first, []).append(arc)
        incident.setdefault(second, []).append(arc)
        donors.setdefault(second, set()).add(first)
    sections = {}
    for identifier in sorted(incident):
        node = nodes[identifier]
        cell = node['cell_id']
        discharge = float(context['local_q'][cell] + context['incoming_q'][cell])
        target = int(context['receiver'][cell])
        slope = max(0.0, float((context['height'].ravel()[cell] - context['height'].ravel()[target]) / context['spacing'])) if target >= 0 else 0.0
        width, depth = _i50__width_depth(discharge, slope, recipe)
        level = _level(context['area'][cell], discharge, width, depth, recipe)
        evidence = []
        if level is None:
            evidence.append('area_or_ordinary_carrier_geometry_threshold_unmet')
        if level is not None and level >= 2:
            evidence.append('perennial_frequency_baseflow_and_duration_unmeasured')
        sections[identifier] = {'node_id': identifier, 'cell_id': cell, 'source_xyz_m': list(node['xyz_m']), 'bed_m': node['xyz_m'][1] - depth, 'width_m': width, 'depth_m': depth, 'representative_q_m3_s': discharge, 'local_runoff_q_m3_s': float(context['local_q'][cell]), 'incoming_exchange_q_m3_s': float(context['incoming_q'][cell]), 'local_upstream_area_m2': float(context['area'][cell]), 'level': _i50_LEVELS[level] + '_proxy' if level is not None else 'needs_evidence', 'geometry_threshold_level': _i50_LEVELS[level] if level is not None else None, 'needs_evidence': True, 'evidence_reasons': evidence or ['uncalibrated_ordinary_event_carrier'], 'anchor': bool(set(node['kinds']) & ANCHORS), 'junction': len(donors.get(identifier, ())) > 1, 'cross_section_xyz_m': [], 'rejection_reasons': [], 'parametric_only': True, 'bed_rasterized': False, 'flow_regime_certified': False, 'level_semantics': 'ordinary_event_geometry_threshold_proxy_not_certified_flow_regime', '_level': level}
    for cell in context['order']:
        identifier = f'cell:{cell}'
        target_id = f"cell:{int(context['receiver'][cell])}"
        if identifier not in sections or target_id not in sections:
            continue
        section, target = (sections[identifier], sections[target_id])
        target['width_m'] = max(target['width_m'], section['width_m'])
        target['depth_m'] = max(target['depth_m'], section['depth_m'])
        target['representative_q_m3_s'] = max(target['representative_q_m3_s'], section['representative_q_m3_s'])
        target['bed_m'] = min(target['source_xyz_m'][1] - target['depth_m'], section['bed_m'] - 0.0001 * context['spacing'])
    for identifier, section in sections.items():
        node = nodes[identifier]
        if section['anchor']:
            section['bed_m'] = node['xyz_m'][1]
            section['depth_m'] = 0.0
            section['rejection_reasons'].append('anchor_cut_conflict')
        if section['junction'] or len(incident[identifier]) >= 3:
            section['rejection_reasons'].append('needs_junction_patch')
        section['junction_patch_ready'] = False
        cut = node['xyz_m'][1] - section['bed_m']
        section['required_cut_m'] = cut
        if cut > 4.0 + 1e-09:
            section['rejection_reasons'].append('four_metre_cut_budget_exceeded')
        outgoing = [arc for arc in incident[identifier] if arc['node_ids'][0] == identifier]
        reference = outgoing[0] if outgoing else incident[identifier][0]
        points = reference['xyz_m']
        direction = _i50_np.asarray(points[1])[[0, 2]] - _i50_np.asarray(points[0])[[0, 2]]
        norm = float(_i50_np.linalg.norm(direction))
        normal = [-float(direction[1]) / norm, float(direction[0]) / norm]
        section['transverse_unit_xz'] = normal
        run = section['depth_m'] * _i50__level_value(recipe, section['_level'] or 0, 'bank_slope_h_per_v')
        offsets = [-section['width_m'] / 2 - run, -section['width_m'] / 2, section['width_m'] / 2, section['width_m'] / 2 + run]
        try:
            for index, offset in enumerate(offsets):
                x_m = node['xyz_m'][0] + normal[0] * offset
                z_m = node['xyz_m'][2] + normal[1] * offset
                source_bank = _td_watershed_sections_sample(context, hierarchy, x_m, z_m)
                if source_bank < section['bed_m'] - 1e-09:
                    raise ValueError('bank_below_candidate_bed')
                if source_bank - section['bed_m'] > 4.0 + 1e-09 and index in (1, 2):
                    raise ValueError('transverse_four_metre_cut_budget_exceeded')
                section['cross_section_xyz_m'].append([x_m, source_bank if index in (0, 3) else section['bed_m'], z_m])
        except ValueError as error:
            section['rejection_reasons'].append(str(error))
            section['cross_section_xyz_m'] = []
    for identifier, node in sorted(nodes.items()):
        if identifier in sections:
            continue
        cell = node['cell_id']
        sections[identifier] = {'node_id': identifier, 'cell_id': cell, 'source_xyz_m': list(node['xyz_m']), 'bed_m': node['xyz_m'][1], 'width_m': 0.0, 'depth_m': 0.0, 'required_cut_m': 0.0, 'representative_q_m3_s': float(context['local_q'][cell] + context['incoming_q'][cell]), 'local_runoff_q_m3_s': float(context['local_q'][cell]), 'incoming_exchange_q_m3_s': float(context['incoming_q'][cell]), 'local_upstream_area_m2': float(context['area'][cell]), 'level': 'source_support_only', 'geometry_threshold_level': None, 'level_semantics': 'unchanged_source_support_not_channel_geometry', 'flow_regime_certified': False, 'needs_evidence': True, 'evidence_reasons': ['support_cannot_modify_bed'], 'anchor': bool(set(node['kinds']) & ANCHORS), 'junction': False, 'cross_section_xyz_m': [], 'rejection_reasons': [], 'parametric_only': True, 'bed_rasterized': False, '_level': None}
    mesh = {'vertices_xyz_m': [], 'triangles': [], 'node_vertex_indices': {}, 'triangle_arc_ids': [], 'parametric_only': True, 'bed_rasterized': False, 'junction_patch_ready': False, 'edge_incidence_max': 0, 'positive_projected_area': True, 'nonoverlapping_projection': True}
    incidence, triangle_buckets = ({}, {})
    edges = []
    for arc, diagnostic in land:
        first, second = (sections[identifier] for identifier in arc['node_ids'])
        reasons = diagnostic['rejection_reasons']
        reasons.extend(sorted(set(first['rejection_reasons'] + second['rejection_reasons'])))
        if first['_level'] is None or second['_level'] is None:
            reasons.append('insufficient_ordinary_supply_or_area')
        if first['bed_m'] - second['bed_m'] < 0.0001 * context['spacing'] - 1e-09:
            reasons.append('candidate_bed_slope_failed')
        if not reasons:
            signs = []
            vertices = first['cross_section_xyz_m'] + second['cross_section_xyz_m']
            for index in range(3):
                for triangle in ((index, index + 4, index + 1), (index + 1, index + 4, index + 5)):
                    points = [vertices[vertex] for vertex in triangle]
                    signed = (points[1][0] - points[0][0]) * (points[2][2] - points[0][2]) - (points[1][2] - points[0][2]) * (points[2][0] - points[0][0])
                    signs.append(signed)
            if min((abs(value) for value in signs)) < 1e-09 or min(signs) < 0 < max(signs):
                reasons.append('folded_or_degenerate_bank_geometry')
        diagnostic.update(status='rejected' if reasons else 'geometry_candidate', representative_q_m3_s=max(first['representative_q_m3_s'], second['representative_q_m3_s']), level=first['level'], needs_evidence=True, flow_regime_certified=False)
        if reasons:
            continue
        proposed_vertices = list(mesh['vertices_xyz_m'])
        proposed_indices = dict(mesh['node_vertex_indices'])
        for section in (first, second):
            identifier = section['node_id']
            if identifier not in proposed_indices:
                start = len(proposed_vertices)
                proposed_indices[identifier] = list(range(start, start + 4))
                proposed_vertices.extend(_i50_deepcopy(section['cross_section_xyz_m']))
        first_indices, second_indices = (proposed_indices[identifier] for identifier in arc['node_ids'])
        proposed_triangles = []
        for index in range(3):
            triangles = [[first_indices[index], second_indices[index], first_indices[index + 1]], [first_indices[index + 1], second_indices[index], second_indices[index + 1]]]
            if signs[0] < 0:
                triangles = [triangle[::-1] for triangle in triangles]
            proposed_triangles.extend(triangles)
        problem = _register_triangles(proposed_vertices, proposed_triangles, incidence, triangle_buckets, context['spacing'])
        if problem:
            reasons.append(problem)
            diagnostic['status'] = 'rejected'
            continue
        triangle_indices = list(range(len(mesh['triangles']), len(mesh['triangles']) + 6))
        mesh['vertices_xyz_m'] = proposed_vertices
        mesh['node_vertex_indices'] = proposed_indices
        mesh['triangles'].extend(proposed_triangles)
        mesh['triangle_arc_ids'].extend([arc['arc_id']] * 6)
        edges.append({'arc_id': arc['arc_id'], 'node_ids': list(arc['node_ids']), 'cross_section_xyz_m': [_i50_deepcopy(first['cross_section_xyz_m']), _i50_deepcopy(second['cross_section_xyz_m'])], 'triangle_indices': triangle_indices})
    mesh['edge_incidence_max'] = max((len(directions) for directions in incidence.values()), default=0)
    fine = []
    remaining = TD_WATERSHED_SECTIONS_MAX_FINE_CELLS
    for arc, diagnostic in land:
        first, second = (sections[identifier] for identifier in arc['node_ids'])
        reasons = ['land_channel', 'width_resolution']
        if arc['is_main_path']:
            reasons.append('mainline')
        if first['junction'] or second['junction']:
            reasons.append('junction')
        request = _fine_request(arc['arc_id'], arc['xyz_m'], min(first['width_m'], second['width_m']), max(first['depth_m'], second['depth_m']), first['_level'], reasons, context, hierarchy, remaining)
        fine.append(request)
        if request['status'] == 'requested':
            remaining -= request['estimated_cells']
    for identifier, node in sorted(nodes.items()):
        kinds = set(node['kinds'])
        if not kinds & {'spill', 'engineering', 'lake_entry'}:
            continue
        discharge = float(context['local_q'][node['cell_id']] + context['incoming_q'][node['cell_id']])
        width, depth = _i50__width_depth(discharge, 0.0, recipe)
        reasons = sorted(kinds & ANCHORS)
        if 'engineering' in kinds:
            reasons.append('outlet')
        request = _fine_request(identifier, [node['xyz_m']], width, depth, None, reasons, context, hierarchy, remaining)
        fine.append(request)
        if request['status'] == 'requested':
            remaining -= request['estimated_cells']
    for arc in support:
        if not arc['is_main_path']:
            continue
        for index in range(max(1, len(arc['xyz_m']) - 1)):
            points = arc['xyz_m'][index:index + 2]
            cell = arc['cell_ids'][index]
            discharge = float(context['local_q'][cell] + context['incoming_q'][cell])
            width, depth = _i50__width_depth(discharge, 0.0, recipe)
            reasons = ['mainline', 'unchanged_source_support', 'width_resolution']
            if arc['kind'] == 'cross_face':
                reasons.append('spill')
            if arc['kind'] == 'engineering_outlet_support':
                reasons.append('outlet')
            request = _fine_request(f"{arc['arc_id']}:window:{index}", points, width, depth, None, reasons, context, hierarchy, remaining)
            request['parent_arc_id'] = arc['arc_id']
            fine.append(request)
            if request['status'] == 'requested':
                remaining -= request['estimated_cells']
    priorities = ('outlet', 'spill', 'junction', 'mainline')
    fine.sort(key=lambda request: (next((index for index, reason in enumerate(priorities) if reason in request['reasons']), len(priorities)), request['request_id']))
    remaining = TD_WATERSHED_SECTIONS_MAX_FINE_CELLS
    for request in fine:
        refusal = [reason for reason in request['refusal_reasons'] if reason != 'total_fine_cell_budget_exceeded']
        if request['estimated_cells'] > remaining:
            refusal.append('total_fine_cell_budget_exceeded')
        request['refusal_reasons'] = refusal
        request['status'] = 'refused' if refusal else 'requested'
        if not refusal:
            remaining -= request['estimated_cells']
    for section in sections.values():
        del section['_level']
    result = {'schema': TD_WATERSHED_SECTIONS_SCHEMA, 'source_identity_sha256': hierarchy['metadata']['source_identity_sha256'], 'hierarchy_identity_sha256': hierarchy['identity_sha256'], 'topology_identity_sha256': topology['identity_sha256'], 'ordinary_identity_sha256': ordinary['identity_sha256'], 'composite_parent_identity': {'paths': paths.get('identity_sha256'), 'graph': paths.get('graph_identity_sha256')}, 'selected_leaf_ids': list(paths['selected_leaf_ids']), 'parameters': _i50_asdict(recipe), 'node_sections': list(sections.values()), 'mesh': mesh, 'edge_sections': edges, 'support_arcs': support, 'fine_requests': fine, 'reach_diagnostics': diagnostics, 'exchange_injections': context['injections'], 'summary': {'land_edges': len(land), 'mesh_edges': len(edges), 'rejected_edges': sum((bool(item['rejection_reasons']) for item in diagnostics)), 'fine_requested_cells': TD_WATERSHED_SECTIONS_MAX_FINE_CELLS - remaining, 'fine_refused_windows': sum((item['status'] == 'refused' for item in fine))}, 'budgets': {'max_json_bytes': TD_WATERSHED_INTERFACE_PATCHES_MAX_BYTES, 'max_window_cells': MAX_WINDOW_CELLS, 'max_fine_cells': TD_WATERSHED_SECTIONS_MAX_FINE_CELLS}, 'coordinate_system': 'model_xyz_m', 'parametric_only': True, 'bed_rasterized': False, 'bed_changed': False, 'source': {'bed_changed': False}, 'candidate_changed': 'geometry_only', 'supply_semantics': 'ordinary_event_mean_carrier_proxy_not_instantaneous_Q_or_multiyear_flow; uncalibrated_uniform_basin_spatial_allocation; actual_net_exchange_not_source_attribution; no_water_created', 'ordinary_duration_s': context['duration'], 'source_spacing_m': context['spacing'], 'exchange_scope': 'all_topology_faces_including_nonforest_inputs; each_positive_cumulative_directional_net_once_on_receiver_then_to_sink; engineering_export_not_attributed_to_forest', 'level_semantics': 'existing_four_area_Q_width_depth_thresholds_only; perennial_supply_unverified; no_permanent_mainstem_claim', 'bank_sampling': 'original_coarse_bilinear_height_for_parametric_bank_geometry_not_fine_DEM', 'continuity_semantics': 'source_centerline_support_continuity_is_not_candidate_channel_bed_continuity; accepted_mesh_only_on_nonrejected_land_edges; lake_interfaces_depth_zero_with_incident_cut_edges_refused; junction_strips_omitted_pending_patch', 'calibration': 'uncalibrated prototype; USGS PP252 (1953), doi:10.3133/pp252; existing NaturalNetworkRecipe unchanged', **{flag: False for flag in TD_WATERSHED_SECTIONS_FLAGS}}
    result['candidate_shape_identity_sha256'] = _shape_identity(result)
    result['identity_sha256'] = _td_watershed_sections_digest(result)
    validate_watershed_sections(result)
    return result

def validate_watershed_sections(record):
    """Validate finite JSON, diagnostic flags, shared mesh and resource budgets."""
    payload = _td_watershed_sections_encoded(record)
    if len(payload) > TD_WATERSHED_INTERFACE_PATCHES_MAX_BYTES or record.get('schema') != TD_WATERSHED_SECTIONS_SCHEMA:
        raise ValueError('sections schema or JSON byte budget failure')
    if any((record.get(flag) is not False for flag in TD_WATERSHED_SECTIONS_FLAGS)):
        raise ValueError('sections cannot grant certification')
    if record.get('parametric_only') is not True or record.get('bed_rasterized') is not False or record.get('bed_changed') is not False or (record.get('source', {}).get('bed_changed') is not False) or (record.get('candidate_changed') != 'geometry_only'):
        raise ValueError('invalid geometry-only status')
    unsigned = {key: value for key, value in record.items() if key != 'identity_sha256'}
    if record.get('identity_sha256') != _td_watershed_sections_digest(unsigned):
        raise ValueError('sections identity mismatch')
    if record.get('candidate_shape_identity_sha256') != _shape_identity(record):
        raise ValueError('candidate output shape identity mismatch')
    sections = {section['node_id']: section for section in record['node_sections']}
    if len(sections) != len(record['node_sections']) or len(sections) > TD_WATERSHED_PATHS_MAX_CELLS:
        raise ValueError('duplicate or excessive sections')
    for section in sections.values():
        if section['flow_regime_certified'] is not False or section['parametric_only'] is not True or section['bed_rasterized'] is not False:
            raise ValueError('section cannot grant certification')
        if any((section[name] < 0 for name in ('width_m', 'depth_m', 'representative_q_m3_s', 'required_cut_m'))):
            raise ValueError('negative section geometry or supply')
        if section['anchor'] and (section['depth_m'] != 0 or section['bed_m'] != section['source_xyz_m'][1]):
            raise ValueError('anchor differs from unchanged source bed')
        points = section['cross_section_xyz_m']
        if points:
            _finite_array(points, (4, 3), 'cross section')
            if points[1][1] != section['bed_m'] or points[2][1] != section['bed_m']:
                raise ValueError('cross section differs from shared bed')
    mesh = record['mesh']
    if mesh['junction_patch_ready'] is not False or mesh['parametric_only'] is not True or mesh['bed_rasterized'] is not False:
        raise ValueError('invalid candidate mesh flags')
    vertices = _finite_array(mesh['vertices_xyz_m'], (len(mesh['vertices_xyz_m']), 3), 'mesh vertices') if mesh['vertices_xyz_m'] else _i50_np.empty((0, 3))
    for identifier, indices in mesh['node_vertex_indices'].items():
        if identifier not in sections or len(indices) != 4 or any((type(index) is not int or not 0 <= index < len(vertices) for index in indices)):
            raise ValueError('invalid shared mesh node')
        if vertices[indices].tolist() != sections[identifier]['cross_section_xyz_m']:
            raise ValueError('mesh differs from shared node section')
    if len(mesh['triangles']) != len(mesh['triangle_arc_ids']):
        raise ValueError('triangle provenance mismatch')
    for triangle in mesh['triangles']:
        if len(triangle) != 3 or len(set(triangle)) != 3 or any((type(index) is not int or not 0 <= index < len(vertices) for index in triangle)):
            raise ValueError('invalid triangle')
    incidence, buckets = ({}, {})
    problem = _register_triangles(mesh['vertices_xyz_m'], mesh['triangles'], incidence, buckets, record['source_spacing_m'])
    if problem:
        raise ValueError(problem)
    if mesh['edge_incidence_max'] != max((len(directions) for directions in incidence.values()), default=0):
        raise ValueError('mesh incidence summary mismatch')
    diagnostics = {item['arc_id']: item for item in record['reach_diagnostics']}
    for edge in record['edge_sections']:
        if edge['arc_id'] not in diagnostics or diagnostics[edge['arc_id']]['rejection_reasons']:
            raise ValueError('rejected reach cannot enter saved mesh')
        if edge['cross_section_xyz_m'] != [sections[identifier]['cross_section_xyz_m'] for identifier in edge['node_ids']]:
            raise ValueError('edge differs from shared node sections')
        for index in edge['triangle_indices']:
            if not 0 <= index < len(mesh['triangles']) or mesh['triangle_arc_ids'][index] != edge['arc_id']:
                raise ValueError('edge triangle provenance mismatch')
    requested = 0
    for request in record['fine_requests']:
        spacing = request['target_spacing_m']
        if spacing <= 0 or spacing > request['width_m'] / 2 + 1e-12:
            raise ValueError('fine spacing must resolve width')
        extent = request['grid_extent']
        if len(extent) != 4 or any((type(value) is not int for value in extent)):
            raise ValueError('invalid fine extent')
        shape = [extent[3] - extent[1] + 1, extent[2] - extent[0] + 1]
        cells = shape[0] * shape[1]
        if min(shape) <= 0 or shape != request['grid_shape'] or cells != request['estimated_cells'] or (cells * 32 != request['estimated_bytes']):
            raise ValueError('fine budget estimate mismatch')
        if request['fine_dem_available'] is not False or request['generation_requested'] is not False:
            raise ValueError('fine requests cannot claim generated DEM')
        if request['status'] == 'requested':
            if request['refusal_reasons'] or cells > MAX_WINDOW_CELLS:
                raise ValueError('invalid accepted fine budget')
            requested += cells
        elif request['status'] != 'refused' or not request['refusal_reasons']:
            raise ValueError('invalid fine refusal')
    if requested > TD_WATERSHED_SECTIONS_MAX_FINE_CELLS or requested != record['summary']['fine_requested_cells']:
        raise ValueError('fine total budget mismatch')
    return record

def save_watershed_sections(record, path):
    from terrain_pipeline.common_infra import publish_bytes as _i50_publish_bytes
    validate_watershed_sections(record)
    _i50_publish_bytes(_i50_Path(path), _td_watershed_sections_encoded(record))
    return _i50_Path(path)

def load_watershed_sections(path, *, expected_sha256=None, expected_identity=None):
    path = _i50_Path(path)
    if path.stat().st_size > TD_WATERSHED_INTERFACE_PATCHES_MAX_BYTES:
        raise ValueError('sections JSON byte budget exceeded')
    payload = path.read_bytes()
    if expected_sha256 is not None and _i50_hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError('sections file hash mismatch')
    record = _i50_json.loads(payload)
    validate_watershed_sections(record)
    if expected_identity is not None and record['identity_sha256'] != expected_identity:
        raise ValueError('sections expected identity mismatch')
    return record
VALLEY_BUDGET_VERSION = 'valley-budget-v1'

@_i51_dataclass(frozen=True)
class ValleyRecipe:
    valley_cut_m: float = 8.0
    bed_cut_m: float = 4.0
    total_area_cells: int = 10000
    protected_cut_m: float = 0.0

    def __post_init__(self):
        for name in ('valley_cut_m', 'bed_cut_m', 'protected_cut_m'):
            value = getattr(self, name)
            if isinstance(value, bool) or not _i51_math.isfinite(value) or value < 0:
                raise ValueError(f'{name} must be finite and nonnegative')
        if type(self.total_area_cells) is not int or self.total_area_cells <= 0:
            raise ValueError('total_area_cells must be positive')

def allocate_valley_budget(plan, protected_mask=None, joint=None, recipe=ValleyRecipe()):
    """Allocate bounded valley cuts around the planned bed without editing the source."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i51_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i51_array_hash
    if not isinstance(recipe, ValleyRecipe) or plan.get('status') != 'diagnostic_not_publishable':
        raise ValueError('diagnostic plan and recipe required')
    arrays = plan['arrays']
    source = arrays['source_height_m']
    shape = source.shape
    protected = _i51_np.zeros(shape, dtype=bool) if protected_mask is None else _i51_np.asarray(protected_mask)
    if protected.shape != shape or protected.dtype != bool:
        raise ValueError('protected mask must match plan grid')
    if not _i51_np.isfinite(source).all() or not _i51_np.isfinite(arrays['target_bed_m']).all():
        raise ValueError('plan heights must be finite')
    active = arrays['channel_mask']
    requested_valley = _i51_np.zeros(shape, dtype=_i51_np.float64)
    requested_valley[active] = _i51_np.maximum(0.0, source[active] - arrays['target_bed_m'][active])
    requested_bed = _i51_np.zeros(shape, dtype=_i51_np.float64)
    requested_bed[active] = _i51_np.minimum(recipe.bed_cut_m, requested_valley[active])
    protected_conflict = protected & (requested_valley > recipe.protected_cut_m + 1e-09)
    available = max(0, recipe.total_area_cells - int(_i51_np.count_nonzero(protected_conflict)))
    candidates = _i51_np.argwhere((requested_valley > 0) & ~protected)
    if len(candidates) > available:
        candidates = candidates[:available]
    selected = _i51_np.zeros(shape, dtype=bool)
    selected[tuple(candidates.T)] = True
    valley_allocation = _i51_np.where(selected, _i51_np.minimum(requested_valley, recipe.valley_cut_m), 0.0)
    bed_allocation = _i51_np.where(selected, _i51_np.minimum(requested_bed, recipe.bed_cut_m), 0.0)
    bed_remaining = _i51_np.maximum(0.0, requested_bed - bed_allocation)
    over_budget = (requested_valley > recipe.valley_cut_m + 1e-09) | (requested_bed > recipe.bed_cut_m + 1e-09) | (requested_valley > 0) & ~selected
    inherited = _i51_np.zeros(shape, dtype=bool)
    if joint is not None:
        inherited |= bool(not joint.get('pass', False))
    identity = _i51_ArtifactIdentity('Terragenesis', 'valley-budget', VALLEY_BUDGET_VERSION, 0, {**_i51_asdict(recipe), 'plan_identity_sha256': plan['identity_sha256'], 'source_height_sha256': _i51_array_hash(source), 'target_bed_sha256': _i51_array_hash(arrays['target_bed_m']), 'protected_sha256': _i51_array_hash(protected)})
    outputs = {'requested_valley_cut_m': requested_valley, 'requested_bed_cut_m': requested_bed, 'valley_allocation_m': valley_allocation, 'bed_allocation_m': bed_allocation, 'remaining_bed_budget_m': bed_remaining, 'over_budget_mask': over_budget, 'protected_conflict_mask': protected_conflict, 'selected_area_mask': selected}
    for value in outputs.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': 'diagnostic_not_publishable', 'arrays': outputs, 'summary': {'requested_nodes': int(_i51_np.count_nonzero(requested_valley)), 'selected_nodes': int(_i51_np.count_nonzero(selected)), 'protected_conflict_nodes': int(_i51_np.count_nonzero(protected_conflict)), 'over_budget_nodes': int(_i51_np.count_nonzero(over_budget)), 'remaining_bed_budget_max_m': float(bed_remaining.max()), 'inherited_joint_blocker': bool(joint is not None and (not joint.get('pass', False)))}}

def plan_recovery(plan, blockers, candidate_routes=None, lake_spills=None):
    """Rank explicit recovery options; never alters the route or source terrain."""
    if plan is None or not isinstance(blockers, dict):
        raise ValueError('blockers must be a mapping')
    plan_identity = plan.get('identity_sha256')
    options = []
    if candidate_routes:
        for route in candidate_routes:
            bound = route.get('plan_identity_sha256') == plan_identity
            options.append({'kind': 'reroute', 'candidate': route, 'eligible': bound and (not bool(route.get('crosses_protection', False))), 'reason': 'candidate route is explicit and protection-compatible'})
    if lake_spills:
        for spill in lake_spills:
            bound = spill.get('plan_identity_sha256') == plan_identity
            options.append({'kind': 'lake_spill', 'candidate': spill, 'eligible': bound and bool(spill.get('legal_outlet', False)), 'reason': 'requires an explicit legal outlet and balance check'})
    options.append({'kind': 'failure', 'candidate': None, 'eligible': True, 'reason': 'retain diagnostics when no explicit recovery satisfies constraints'})
    eligible = [option for option in options if option['eligible']]
    chosen = eligible[0] if eligible else options[-1]
    return {'status': 'diagnostic_not_publishable', 'chosen': chosen, 'options': options, 'blockers': dict(blockers), 'selection_reason': 'first explicit eligible option; no hidden route or source mutation'}
