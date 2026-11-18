"""Consolidated surface_domain implementations; numeric expressions preserved."""
from __future__ import annotations
from terrain_pipeline.surface_identity import _plain, _freeze, geometry_identity
from terrain_pipeline.surface_identity import _plain, _freeze, geometry_identity
from terrain_pipeline.surface_identity import _plain, _freeze, geometry_identity
from dataclasses import dataclass as _i96_dataclass
import math as _i96_math
import numpy as _i96_np
from dataclasses import asdict as _i110_asdict
from dataclasses import dataclass as _i110_dataclass
import json as _i110_json
import math as _i110_math
import os as _i110_os
from pathlib import Path as _i110_Path
import tempfile as _i110_tempfile
from collections import deque as _i110_deque
import numpy as _i110_np
from collections import deque as _i97_deque
from dataclasses import asdict as _i97_asdict
import json as _i97_json
import math as _i97_math
import os as _i97_os
from pathlib import Path as _i97_Path
import tempfile as _i97_tempfile
import zipfile as _i97_zipfile
import numpy as _i97_np
from numpy.lib import format as _i97_npy_format
from dataclasses import asdict as _i111_asdict
from dataclasses import dataclass as _i111_dataclass
import json as _i111_json
import math as _i111_math
import os as _i111_os
from pathlib import Path as _i111_Path
import tempfile as _i111_tempfile
import zipfile as _i111_zipfile
import numpy as _i111_np
from collections import deque as _i108_deque
import hashlib as _i108_hashlib
import json as _i108_json
import math as _i108_math
import os as _i108_os
from pathlib import Path as _i108_Path
import shutil as _i108_shutil
import stat as _i108_stat
import tempfile as _i108_tempfile
from types import MappingProxyType as _i108_MappingProxyType
import zipfile as _i108_zipfile
import numpy as _i108_np
from collections import deque as _i102_deque
from collections.abc import Mapping as _i102_Mapping
from dataclasses import asdict as _i102_asdict
from dataclasses import dataclass as _i102_dataclass
from dataclasses import replace as _i102_replace
import heapq as _i102_heapq
import json as _i102_json
import math as _i102_math
import os as _i102_os
from pathlib import Path as _i102_Path
import tempfile as _i102_tempfile
from types import MappingProxyType as _i102_MappingProxyType
import zipfile as _i102_zipfile
import numpy as _i102_np
from collections.abc import Mapping as _i105_Mapping
from dataclasses import dataclass as _i105_dataclass
import hashlib as _i105_hashlib
import io as _i105_io
import json as _i105_json
import math as _i105_math
import os as _i105_os
from pathlib import Path as _i105_Path
import struct as _i105_struct
import tempfile as _i105_tempfile
from types import MappingProxyType as _i105_MappingProxyType
import zipfile as _i105_zipfile
import numpy as _i105_np
from collections.abc import Mapping as _i98_Mapping
from dataclasses import asdict as _i98_asdict
from dataclasses import dataclass as _i98_dataclass
import hashlib as _i98_hashlib
import io as _i98_io
import json as _i98_json
import math as _i98_math
import os as _i98_os
from pathlib import Path as _i98_Path
import tempfile as _i98_tempfile
from types import MappingProxyType as _i98_MappingProxyType
import zipfile as _i98_zipfile
import numpy as _i98_np
from collections import defaultdict as _i99_defaultdict
from collections.abc import Mapping as _i99_Mapping
from decimal import Decimal as _i99_Decimal
from decimal import InvalidOperation as _i99_InvalidOperation
import hashlib as _i99_hashlib
import json as _i99_json
from collections.abc import Mapping as _i103_Mapping
from dataclasses import asdict as _i103_asdict
from dataclasses import dataclass as _i103_dataclass
from dataclasses import fields as _i103_fields
import io as _i103_io
import json as _i103_json
import math as _i103_math
import os as _i103_os
from pathlib import Path as _i103_Path
import tempfile as _i103_tempfile
import zipfile as _i103_zipfile
import numpy as _i103_np
import hashlib as _i100_hashlib
import json as _i100_json
import os as _i100_os
import stat as _i100_stat
import tempfile as _i100_tempfile
from pathlib import Path as _i100_Path
import numpy as _i100_np
from terrain_pipeline import td_source as _i100_dem_domain
import io as _i101_io
import json as _i101_json
import math as _i101_math
import os as _i101_os
from pathlib import Path as _i101_Path
import tempfile as _i101_tempfile
import zipfile as _i101_zipfile
import numpy as _i101_np
from dataclasses import asdict as _i107_asdict
from dataclasses import dataclass as _i107_dataclass
from dataclasses import fields as _i107_fields
import json as _i107_json
import os as _i107_os
from pathlib import Path as _i107_Path
import tempfile as _i107_tempfile
import zipfile as _i107_zipfile
import numpy as _i107_np
from dataclasses import asdict as _i104_asdict
from dataclasses import dataclass as _i104_dataclass
import ast as _i104_ast
import json as _i104_json
import math as _i104_math
import os as _i104_os
from pathlib import Path as _i104_Path
import tempfile as _i104_tempfile
import zipfile as _i104_zipfile
import numpy as _i104_np
from dataclasses import asdict as _i106_asdict
from dataclasses import dataclass as _i106_dataclass
import json as _i106_json
import math as _i106_math
import os as _i106_os
from pathlib import Path as _i106_Path
import tempfile as _i106_tempfile
import zipfile as _i106_zipfile
import numpy as _i106_np
from dataclasses import dataclass as _i109_dataclass
import hashlib as _i109_hashlib
import json as _i109_json
from pathlib import Path as _i109_Path
import zipfile as _i109_zipfile
import numpy as _i109_np
import hashlib as _i112_hashlib
import json as _i112_json
import math as _i112_math
import os as _i112_os
from pathlib import Path as _i112_Path
import shutil as _i112_shutil
import zipfile as _i112_zipfile
import uuid as _i112_uuid
from types import MappingProxyType as _i112_MappingProxyType
import numpy as _i112_np
from dataclasses import dataclass as _i113_dataclass
from collections.abc import Mapping as _i113_Mapping
import ast as _i113_ast
import json as _i113_json
import math as _i113_math
import os as _i113_os
from pathlib import Path as _i113_Path
import tempfile as _i113_tempfile
import struct as _i113_struct
import zipfile as _i113_zipfile
import numpy as _i113_np
CATEGORY = 'B'

@_i96_dataclass(frozen=True)
class DomainWindow:
    domain_id: int
    interior_zx: tuple
    halo_zx: tuple
    version: str
    bed_m: _i96_np.ndarray
    depth_m: _i96_np.ndarray

def _immutable(array):
    return _i96_np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape)

def partition_saved_window(bed_m, depth_m, leaf_owner, *, row_cuts=(), column_cuts=(), version):
    bed = _i96_np.asarray(bed_m)
    depth = _i96_np.asarray(depth_m)
    leaves = _i96_np.asarray(leaf_owner)
    if bed.dtype != _i96_np.float64 or bed.ndim != 2 or (not bed.size) or (depth.shape != bed.shape) or (depth.dtype != _i96_np.float64) or (leaves.shape != bed.shape) or (leaves.dtype.kind not in 'iu') or (not _i96_np.isfinite(bed).all()) or (not _i96_np.isfinite(depth).all()) or _i96_np.any(depth < 0) or _i96_np.any(leaves < 0) or (type(version) is not str) or (not version):
        raise ValueError('finite canonical bed/depth/leaf ownership and saved version required')
    rows, columns = bed.shape
    boundaries = []
    for extent, cuts in ((rows, row_cuts), (columns, column_cuts)):
        if any((type(value) is not int or not 0 < value < extent for value in cuts)) or list(cuts) != sorted(set(cuts)):
            raise ValueError('strictly ordered interior domain cuts required')
        boundaries.append((0, *cuts, extent))
    owner = _i96_np.empty(bed.shape, _i96_np.int64)
    windows = []
    for row_index in range(len(boundaries[0]) - 1):
        for column_index in range(len(boundaries[1]) - 1):
            row0, row1 = boundaries[0][row_index:row_index + 2]
            col0, col1 = boundaries[1][column_index:column_index + 2]
            domain = len(windows)
            owner[row0:row1, col0:col1] = domain
            halo = (max(0, row0 - 1), min(rows, row1 + 1), max(0, col0 - 1), min(columns, col1 + 1))
            windows.append(DomainWindow(domain, (row0, row1, col0, col1), halo, version, _immutable(bed[halo[0]:halo[1], halo[2]:halo[3]]), _immutable(depth[halo[0]:halo[1], halo[2]:halo[3]])))
    ordered = _i96_np.argsort(leaves.ravel(), kind='stable')
    sorted_leaves, sorted_domains = (leaves.ravel()[ordered], owner.ravel()[ordered])
    if _i96_np.any((sorted_leaves[1:] == sorted_leaves[:-1]) & (sorted_domains[1:] != sorted_domains[:-1])):
        raise ValueError('domain cut splits a saved hydraulic leaf; explicit conservative leaf split required')
    first, second, axis, row, column = ([], [], [], [], [])
    for face_axis in (0, 1):
        if face_axis == 0:
            rz, cx = _i96_np.nonzero(owner[:, :-1] != owner[:, 1:])
            source = rz * columns + cx
            target = source + 1
        else:
            rz, cx = _i96_np.nonzero(owner[:-1] != owner[1:])
            source = rz * columns + cx
            target = source + columns
        first.extend(source.tolist())
        second.extend(target.tolist())
        axis.extend([face_axis] * len(source))
        row.extend(rz.tolist())
        column.extend(cx.tolist())
    first, second, axis = (_i96_np.asarray(values, _i96_np.int64) for values in (first, second, axis))
    face_ids = 2 * first + axis
    if _i96_np.unique(face_ids).size != face_ids.size:
        raise ValueError('duplicate shared canonical face')
    return dict(windows=tuple(windows), owner=_immutable(owner), version=version, face_ids=_immutable(face_ids), first_cell=_immutable(first), second_cell=_immutable(second), face_axis=_immutable(axis), face_row=_immutable(_i96_np.asarray(row, _i96_np.int64)), face_column=_immutable(_i96_np.asarray(column, _i96_np.int64)), face_owner_domain=_immutable(owner.ravel()[first]), neighbor_domain=_immutable(owner.ravel()[second]))

def audit_saved_mosaic(mosaic, bed_m, depth_m, *, spacing_m, version):
    if version != mosaic['version'] or not _i96_math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError('mosaic saved version/metric spacing mismatch')
    bed, depth = (_i96_np.asarray(bed_m), _i96_np.asarray(depth_m))
    owner = mosaic['owner']
    if bed.shape != owner.shape or depth.shape != owner.shape:
        raise ValueError('mosaic source shape mismatch')
    volumes = []
    for window in mosaic['windows']:
        row0, row1, col0, col1 = window.interior_zx
        hz0, hz1, hx0, hx1 = window.halo_zx
        if window.version != version or not _i96_np.array_equal(window.bed_m, bed[hz0:hz1, hx0:hx1]) or (not _i96_np.array_equal(window.depth_m, depth[hz0:hz1, hx0:hx1])):
            raise ValueError('mosaic stale halo or source seam mismatch')
        volumes.append(_i96_math.fsum(depth[row0:row1, col0:col1].ravel()) * spacing_m ** 2)
    total = _i96_math.fsum(depth.ravel()) * spacing_m ** 2
    residual = _i96_math.fsum(volumes) - total
    if abs(residual) > 1e-09 + abs(total) * 1e-12:
        raise ValueError('domain inventory fails canonical volume conservation')
    first, second = (mosaic['first_cell'], mosaic['second_cell'])
    return dict(domain_count=len(volumes), shared_face_segments=len(first), domain_volume_m3=volumes, total_volume_m3=total, mosaic_volume_residual_m3=residual, halo_matches_saved_source=True, unique_shared_faces=True, positive_orientation='first_cell -> second_cell', max_cross_cell_stage_jump_m=float(_i96_np.max(_i96_np.abs((bed + depth).ravel()[first] - (bed + depth).ravel()[second]), initial=0)), solver_advanced=False, independent_domain_hydraulics_verified=False)

def account_shared_transfers(mosaic, signed_volume_m3):
    volumes = _i96_np.asarray(signed_volume_m3)
    if volumes.dtype != _i96_np.float64 or volumes.shape != mosaic['face_ids'].shape or (not _i96_np.isfinite(volumes).all()):
        raise ValueError('one finite signed cumulative volume per shared face required')
    incoming = _i96_np.bincount(mosaic['neighbor_domain'], weights=volumes, minlength=len(mosaic['windows']))
    outgoing = _i96_np.bincount(mosaic['face_owner_domain'], weights=volumes, minlength=len(mosaic['windows']))
    return incoming - outgoing

def bind_saved_leaf_faces(mosaic, geometry):
    rows = geometry['face_canonical_row'] - (geometry['face_axis'] == 1)
    columns = geometry['face_canonical_column'] - (geometry['face_axis'] == 0)
    ids = 2 * (rows * mosaic['owner'].shape[1] + columns) + geometry['face_axis']
    selected = _i96_np.flatnonzero(_i96_np.isin(ids, mosaic['face_ids']))
    order = _i96_np.argsort(ids[selected])
    selected = selected[order]
    if selected.size != mosaic['face_ids'].size or _i96_np.unique(ids[selected]).size != selected.size or (not _i96_np.array_equal(ids[selected], _i96_np.sort(mosaic['face_ids']))):
        raise ValueError('saved segmented hydraulic faces do not uniquely cover shared domain cut')
    return selected[_i96_np.argsort(_i96_np.argsort(mosaic['face_ids']))]

def audit_saved_epoch_exchange(mosaic, geometry, packet):
    from terrain_pipeline.adaptive_mesh import validate_epoch as validate_epoch
    validate_epoch(packet, geometry)
    arrays = geometry['arrays']
    selected = bind_saved_leaf_faces(mosaic, arrays)
    leaf_domains = mosaic['owner'][arrays['leaf_row'], arrays['leaf_column']]
    shared = account_shared_transfers(mosaic, packet['internal_transfer'][selected, 0])
    domain_count = len(mosaic['windows'])
    change = _i96_np.bincount(leaf_domains, weights=(packet['state_after'][:, 0] - packet['state_before'][:, 0]) * arrays['leaf_area_m2'], minlength=domain_count)
    supplied = _i96_np.bincount(leaf_domains, weights=packet['forcing_volume_m3'], minlength=domain_count)
    boundary = _i96_np.bincount(leaf_domains[arrays['boundary_cell']], weights=packet['boundary_transfer'][:, 0], minlength=domain_count)
    residual = change - shared - supplied + boundary
    if _i96_np.max(abs(residual), initial=0) > 1e-09 + 1e-10 * float(_i96_np.sum(abs(change))):
        raise ValueError('saved epoch per-domain exchange closure failed')
    volume = packet['internal_transfer'][selected, 0]
    return dict(time_start_s=packet['time_start_s'], time_end_s=packet['time_end_s'], domain_storage_change_m3=change.tolist(), domain_net_shared_input_m3=shared.tolist(), domain_supplied_m3=supplied.tolist(), domain_boundary_net_output_m3=boundary.tolist(), domain_residual_m3=residual.tolist(), forward_shared_m3=float(_i96_np.maximum(volume, 0).sum()), reverse_shared_m3=float(_i96_np.maximum(-volume, 0).sum()), solver_advanced=False, independent_domain_hydraulics_verified=False, scope='accounting of original saved single-domain adaptive epoch; no independent domain evolution')

def partition_fan_geometry(mosaic, arrays):
    owner = mosaic['owner']
    corners = _i96_np.asarray(arrays['cell_corner_vertex_ids'])
    bed = _i96_np.asarray(arrays['bed_vertices_xyz_m'])
    water = _i96_np.asarray(arrays['water_vertices_xyz_m'])
    bed_triangles = _i96_np.asarray(arrays['bed_triangles'])
    wet_ids = _i96_np.asarray(arrays['wet_cell_ids'])
    water_triangles = _i96_np.asarray(arrays['water_triangles'])
    if corners.shape != (owner.size, 4) or corners.dtype.kind not in 'iu' or bed.ndim != 2 or (bed.shape[1] != 3) or (water.shape != bed.shape) or (not _i96_np.isfinite(bed).all()) or (not _i96_np.isfinite(water).all()) or (bed_triangles.shape != (owner.size * 4, 3)) or (bed_triangles.dtype.kind not in 'iu') or (wet_ids.ndim != 1) or (wet_ids.dtype.kind not in 'iu') or _i96_np.any(wet_ids < 0) or _i96_np.any(wet_ids >= owner.size) or (_i96_np.unique(wet_ids).size != wet_ids.size) or _i96_np.any(corners < 0) or _i96_np.any(corners >= len(bed)) or _i96_np.any(bed_triangles < 0) or _i96_np.any(bed_triangles >= len(bed)) or (not _i96_np.array_equal(water_triangles, bed_triangles.reshape(-1, 4, 3)[wet_ids].reshape(-1, 3))):
        raise ValueError('canonical saved cell fan topology/coordinates required')
    meshes = []
    for window in mosaic['windows']:
        cells = _i96_np.flatnonzero(owner.ravel() == window.domain_id)
        triangles = bed_triangles.reshape(-1, 4, 3)[cells].reshape(-1, 3)
        ids, remapped = _i96_np.unique(triangles, return_inverse=True)
        selected_wet = wet_ids[owner.ravel()[wet_ids] == window.domain_id]
        wet_triangles = bed_triangles.reshape(-1, 4, 3)[selected_wet].reshape(-1, 3)
        meshes.append(dict(domain_id=window.domain_id, global_vertex_ids=_immutable(ids), cell_ids=_immutable(cells), wet_cell_ids=_immutable(selected_wet), bed_vertices_xyz_m=_immutable(bed[ids]), water_vertices_xyz_m=_immutable(water[ids]), bed_triangles=_immutable(remapped.reshape(-1, 3)), water_triangles=_immutable(_i96_np.searchsorted(ids, wet_triangles))))
    maximum_bed, maximum_water = (0.0, 0.0)
    shared_vertices = set()
    for domain in range(len(meshes)):
        for neighbor in range(domain + 1, len(meshes)):
            first, second = (meshes[domain], meshes[neighbor])
            ids, first_index, second_index = _i96_np.intersect1d(first['global_vertex_ids'], second['global_vertex_ids'], return_indices=True)
            shared_vertices.update(ids.tolist())
            for name in ('bed_vertices_xyz_m', 'water_vertices_xyz_m'):
                difference = float(_i96_np.max(abs(first[name][first_index] - second[name][second_index]), initial=0))
                if name.startswith('bed'):
                    maximum_bed = max(maximum_bed, difference)
                else:
                    maximum_water = max(maximum_water, difference)
    first_corners = corners[mosaic['first_cell']]
    second_corners = corners[mosaic['second_cell']]
    matches = _i96_np.any(first_corners[:, :, None] == second_corners[:, None, :], axis=2)
    if _i96_np.any(matches.sum(axis=1) != 2) or maximum_bed != 0 or maximum_water != 0:
        raise ValueError('shared domain fan edge/coordinate seam mismatch')
    report = dict(shared_vertex_count=len(shared_vertices), max_bed_seam_error_m=maximum_bed, max_water_seam_error_m=maximum_water, bed_triangle_count=sum((len(mesh['bed_triangles']) for mesh in meshes)), water_triangle_count=sum((len(mesh['water_triangles']) for mesh in meshes)), wet_cells_omitted=0, geometry_reconstructed=False, independent_domain_hydraulics_verified=False)
    return (tuple(meshes), report)
SURFACE_NETWORK_PREPARE_VERSION = 'surface-network-prepare-v2'

@_i110_dataclass(frozen=True)
class SurfaceNetworkBudget:
    max_bed_cut_m: float
    max_area_m2: float
    max_cut_volume_m3: float
    bed_match_tolerance_m: float = 1e-06

    def __post_init__(self):
        if any((isinstance(v, bool) or not _i110_math.isfinite(v) or v < 0 for v in _i110_asdict(self).values())):
            raise ValueError('budget values must be finite and nonnegative')

def prepare_surface_network(plan, fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m, fine_spacing_z_m, fine_shape_zx, domain_mask, protected_mask, legal_outlet_mask, outlet_stage_m, section_recipe, stage_recipe, inundation_recipe, budget: SurfaceNetworkBudget):
    """Cut one fixed route and run all joint diagnostics on the resulting surface."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i110_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i110_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i110_digest
    from terrain_pipeline.surface_hydraulics import evaluate_inundation as _x68_evaluate_inundation
    from terrain_pipeline.surface_hydraulics import assess_joint as _x69_assess_joint
    from terrain_pipeline.surface_hydraulics import solve_stage as _x70_solve_stage
    from terrain_pipeline.channel_geometry import evaluate_sections as _x71_evaluate_sections
    if not isinstance(budget, SurfaceNetworkBudget):
        raise ValueError('surface network budget required')
    section = _x71_evaluate_sections(plan, fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m, fine_spacing_z_m, fine_shape_zx, protected_mask, section_recipe)
    arrays = section['arrays']
    source = arrays['source_surface_m']
    final = arrays['bounded_surface_m']
    bed_cut = source - final
    changed = bed_cut > 1e-09
    weights = _i110_np.ones(final.shape)
    weights[[0, -1], :] *= 0.5
    weights[:, [0, -1]] *= 0.5
    area_m2 = float(_i110_np.sum(changed * weights) * fine_spacing_x_m * fine_spacing_z_m)
    volume_m3 = float(_i110_np.sum(bed_cut * weights) * fine_spacing_x_m * fine_spacing_z_m)
    budget_failures = {'bed_depth': bool(_i110_np.any(bed_cut > budget.max_bed_cut_m + 1e-09)), 'area': area_m2 > budget.max_area_m2 + 1e-09, 'volume': volume_m3 > budget.max_cut_volume_m3 + 1e-09, 'protected': bool(_i110_np.any(changed & protected_mask)) or section['summary']['protected_conflict_nodes'] > 0, 'section': bool(section['summary']['blocked_by_plan'] or section['summary']['local_budget_conflict_nodes']), 'outside_domain_cut': bool(_i110_np.any(changed & ~_i110_np.asarray(domain_mask)))}
    plan_arrays = plan['arrays']
    params = plan['identity']['parameters']
    z, x = _i110_np.nonzero(plan_arrays['channel_mask'])
    fx = (params['origin_x_m'] + x * params['spacing_x_m'] - fine_origin_x_m) / fine_spacing_x_m
    fz = (params['origin_z_m'] + z * params['spacing_z_m'] - fine_origin_z_m) / fine_spacing_z_m
    ix, iz = (_i110_np.rint(fx).astype(int), _i110_np.rint(fz).astype(int))
    aligned = _i110_np.allclose(fx, ix, atol=1e-08, rtol=0) and _i110_np.allclose(fz, iz, atol=1e-08, rtol=0) and _i110_np.all((ix >= 0) & (ix < final.shape[1]) & (iz >= 0) & (iz < final.shape[0]))
    bed_error = float(_i110_np.max(_i110_np.abs(final[iz, ix] - plan_arrays['bounded_bed_m'][z, x]))) if aligned and len(z) else None
    budget_failures['stage_bed_mismatch'] = bed_error is None or bed_error > budget.bed_match_tolerance_m
    stage = _x70_solve_stage(plan, outlet_stage_m, stage_recipe)
    edge_failure = False
    edge_depth_failure = False
    edge_slope_failure = False
    if aligned:
        receiver = plan_arrays['receiver']
        for donor in _i110_np.flatnonzero(plan_arrays['channel_mask'].ravel() & (receiver >= 0)):
            target = int(receiver[donor])
            if not plan_arrays['channel_mask'].flat[target]:
                continue
            a = (int(_i110_np.rint((params['origin_z_m'] + donor // plan_arrays['channel_mask'].shape[1] * params['spacing_z_m'] - fine_origin_z_m) / fine_spacing_z_m)), int(_i110_np.rint((params['origin_x_m'] + donor % plan_arrays['channel_mask'].shape[1] * params['spacing_x_m'] - fine_origin_x_m) / fine_spacing_x_m)))
            b = (int(_i110_np.rint((params['origin_z_m'] + target // plan_arrays['channel_mask'].shape[1] * params['spacing_z_m'] - fine_origin_z_m) / fine_spacing_z_m)), int(_i110_np.rint((params['origin_x_m'] + target % plan_arrays['channel_mask'].shape[1] * params['spacing_x_m'] - fine_origin_x_m) / fine_spacing_x_m)))
            steps = max(abs(b[0] - a[0]), abs(b[1] - a[1]))
            if steps == 0:
                edge_failure = True
                break
            upstream, downstream = stage['arrays']['stage_m'].flat[[donor, target]]
            previous_bed = None
            for step in range(steps + 1):
                fraction = step / steps
                cell = (round(a[0] + fraction * (b[0] - a[0])), round(a[1] + fraction * (b[1] - a[1])))
                stage_here = upstream + fraction * (downstream - upstream)
                if not (0 <= cell[0] < final.shape[0] and 0 <= cell[1] < final.shape[1]) or stage_here - final[cell] < stage_recipe.min_clearance_m - 1e-09:
                    edge_failure = True
                    break
                if stage_here - final[cell] > stage_recipe.max_depth_m + 1e-09:
                    edge_depth_failure = True
                if previous_bed is not None and final[cell] > previous_bed + 1e-09:
                    edge_slope_failure = True
                previous_bed = final[cell]
            if edge_failure:
                break
    budget_failures['edge_clearance'] = edge_failure or not aligned
    budget_failures['edge_max_depth'] = edge_depth_failure or not aligned
    flood = _x68_evaluate_inundation(plan, section, stage, domain_mask, protected_mask, legal_outlet_mask, inundation_recipe)
    joint = _x69_assess_joint(plan, section, stage, flood)
    publishable = not any(budget_failures.values()) and joint['pass']
    outputs = {'source_surface_m': source.copy(), 'final_surface_m': final.copy(), 'bed_cut_m': bed_cut.copy(), 'water_surface_m': flood['arrays']['water_surface_m'].copy(), 'wet_mask': flood['arrays']['wet_mask'].copy(), 'channel_seed_mask': flood['arrays']['channel_seed_mask'].copy(), 'disconnected_seed_mask': flood['arrays']['disconnected_seed_mask'].copy(), 'boundary_contact_mask': flood['arrays']['boundary_contact_mask'].copy(), 'reach_limited_mask': flood['arrays']['reach_limited_mask'].copy(), 'domain_mask': flood['arrays']['domain_mask'].copy(), 'protected_mask': flood['arrays']['protected_mask'].copy(), 'legal_outlet_mask': flood['arrays']['legal_outlet_mask'].copy()}
    for value in outputs.values():
        value.flags.writeable = False
    summary = {'publishable': publishable, 'area_m2': area_m2, 'cut_volume_m3': volume_m3, 'max_stage_bed_error_m': bed_error, 'valley_cut_m3': 0.0, 'budget_failures': budget_failures, 'joint_blockers': joint['blockers'], 'section': section['summary'], 'stage': stage['summary'], 'inundation': flood['summary'], 'edge_reverse_bed_observed': edge_slope_failure}
    identity = _i110_ArtifactIdentity('Terragenesis', 'surface-network-prepare', SURFACE_NETWORK_PREPARE_VERSION, 0, {**_i110_asdict(budget), 'plan_sha256': plan['identity_sha256'], 'section_sha256': section['identity_sha256'], 'stage_sha256': stage['identity_sha256'], 'flood_sha256': flood['identity_sha256'], 'joint_sha256': joint['identity_sha256'], 'fine_origin_x_m': float(fine_origin_x_m), 'fine_origin_z_m': float(fine_origin_z_m), 'fine_spacing_x_m': float(fine_spacing_x_m), 'fine_spacing_z_m': float(fine_spacing_z_m), 'sea_level_elevation_m': params['sea_level_elevation_m'], 'fine_shape_zx': list(final.shape), 'output_sha256': _i110_digest({name: _i110_array_hash(value) for name, value in outputs.items()}), 'summary_sha256': _i110_digest(summary)})
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': 'prepared' if publishable else 'diagnostic_not_publishable', 'arrays': outputs, 'summary': summary}

def save_surface_network(result, path):
    from terrain_pipeline.artifacts.contracts import array_hash as _i110_array_hash
    if result.get('status') != 'prepared':
        raise ValueError('only jointly accepted surface networks may be published')
    destination = _i110_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    manifest = {key: result[key] for key in ('identity', 'identity_sha256', 'status', 'summary')}
    manifest['format_version'] = 2
    manifest['array_sha256'] = {name: _i110_array_hash(value) for name, value in result['arrays'].items()}
    temporary = None
    try:
        with _i110_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, delete=False, suffix='.npz') as stream:
            temporary = _i110_Path(stream.name)
            _i110_np.savez_compressed(stream, manifest=_i110_json.dumps(manifest, sort_keys=True), **result['arrays'])
        load_surface_network(temporary)
        _i110_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def save_surface_network_diagnostic(result, path):
    """Persist a failed result for inspection, never as a publishable package."""
    from terrain_pipeline.artifacts.contracts import array_hash as _i110_array_hash
    if result.get('status') != 'diagnostic_not_publishable':
        raise ValueError('diagnostic saver requires a failed result')
    destination = _i110_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {'identity': result['identity'], 'identity_sha256': result['identity_sha256'], 'status': result['status'], 'summary': result['summary'], 'format_version': 2, 'array_sha256': {name: _i110_array_hash(value) for name, value in result['arrays'].items()}}
    temporary = None
    try:
        with _i110_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, delete=False, suffix='.npz') as stream:
            temporary = _i110_Path(stream.name)
            _i110_np.savez_compressed(stream, manifest=_i110_json.dumps(record, sort_keys=True), **result['arrays'])
        load_surface_network(temporary, allow_diagnostic=True)
        _i110_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def load_surface_network(path, allow_diagnostic=False):
    expected = {'source_surface_m', 'final_surface_m', 'bed_cut_m', 'water_surface_m', 'wet_mask', 'channel_seed_mask', 'disconnected_seed_mask', 'boundary_contact_mask', 'reach_limited_mask', 'domain_mask', 'protected_mask', 'legal_outlet_mask'}
    with _i110_np.load(path, allow_pickle=False) as archive:
        manifest = _i110_json.loads(str(archive['manifest'].item()))
        if set(archive.files) != expected | {'manifest'} or set(manifest['array_sha256']) != expected:
            raise ValueError('invalid surface network arrays')
        arrays = {name: archive[name].copy() for name in expected}
    return _validate_surface_network_payload(manifest, arrays, allow_diagnostic)

def validate_surface_network(result, allow_diagnostic=False):
    """Apply the load-time geometry, budget and publication gates in memory."""
    from terrain_pipeline.artifacts.contracts import array_hash as _i110_array_hash
    try:
        manifest = {name: result[name] for name in ('identity', 'identity_sha256', 'status', 'summary')}
        manifest['format_version'] = 2
        manifest['array_sha256'] = {name: _i110_array_hash(value) for name, value in result['arrays'].items()}
        return _validate_surface_network_payload(manifest, result['arrays'], allow_diagnostic)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('invalid surface network result') from error

def _validate_surface_network_payload(manifest, arrays, allow_diagnostic):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i110_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i110_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i110_digest
    expected = {'source_surface_m', 'final_surface_m', 'bed_cut_m', 'water_surface_m', 'wet_mask', 'channel_seed_mask', 'disconnected_seed_mask', 'boundary_contact_mask', 'reach_limited_mask', 'domain_mask', 'protected_mask', 'legal_outlet_mask'}
    if set(arrays) != expected or set(manifest['array_sha256']) != expected:
        raise ValueError('invalid surface network arrays')
    identity = _i110_ArtifactIdentity(**manifest['identity'])
    if manifest['format_version'] != 2 or identity.algorithm != 'surface-network-prepare' or identity.algorithm_version != SURFACE_NETWORK_PREPARE_VERSION or (identity.sha256 != manifest['identity_sha256']) or any((_i110_array_hash(arrays[name]) != manifest['array_sha256'][name] for name in expected)) or (_i110_digest({name: _i110_array_hash(value) for name, value in arrays.items()}) != identity.record()['parameters']['output_sha256']):
        raise ValueError('surface network identity mismatch')
    shape = arrays['source_surface_m'].shape
    if len(shape) != 2 or any((arrays[name].shape != shape for name in expected)) or any((arrays[name].dtype != _i110_np.float64 for name in ('source_surface_m', 'final_surface_m', 'bed_cut_m', 'water_surface_m'))) or any((arrays[name].dtype != bool for name in expected - {'source_surface_m', 'final_surface_m', 'bed_cut_m', 'water_surface_m'})) or any((not _i110_np.isfinite(arrays[name]).all() for name in ('source_surface_m', 'final_surface_m', 'bed_cut_m'))) or (not _i110_np.allclose(arrays['source_surface_m'] - arrays['final_surface_m'], arrays['bed_cut_m'], rtol=0, atol=1e-09)):
        raise ValueError('invalid surface network geometry')
    summary = manifest['summary']
    if _i110_digest(summary) != identity.record()['parameters']['summary_sha256']:
        raise ValueError('surface network summary mismatch')
    params = identity.record()['parameters']
    SurfaceNetworkBudget(**{name: params[name] for name in SurfaceNetworkBudget.__dataclass_fields__})
    if params['fine_shape_zx'] != list(shape) or any((not _i110_math.isfinite(params[name]) for name in ('fine_origin_x_m', 'fine_origin_z_m', 'fine_spacing_x_m', 'fine_spacing_z_m', 'sea_level_elevation_m'))) or params['fine_spacing_x_m'] <= 0 or (params['fine_spacing_z_m'] <= 0):
        raise ValueError('invalid surface network grid')
    wet = arrays['wet_mask']
    water = arrays['water_surface_m']
    if not _i110_np.isfinite(water[wet]).all() or not _i110_np.isnan(water[~wet]).all() or _i110_np.any(water[wet] <= arrays['final_surface_m'][wet]) or _i110_np.any(arrays['bed_cut_m'] < -1e-09):
        raise ValueError('invalid surface network water or cut')
    masks = {'wet_nodes': 'wet_mask', 'channel_seed_nodes': 'channel_seed_mask', 'disconnected_seed_nodes': 'disconnected_seed_mask', 'boundary_contact_nodes': 'boundary_contact_mask', 'reach_limited_nodes': 'reach_limited_mask'}
    if any((summary['inundation'][count] != int(_i110_np.count_nonzero(arrays[name])) for count, name in masks.items())) or not _i110_np.all(~wet | arrays['domain_mask']) or _i110_np.any(wet & arrays['protected_mask']) or _i110_np.any((arrays['bed_cut_m'] > 1e-09) & arrays['protected_mask']) or (not _i110_np.all(~arrays['channel_seed_mask'] | wet)) or (not _i110_np.all(~arrays['disconnected_seed_mask'] | arrays['channel_seed_mask'])) or (summary['inundation']['legal_outlet_wet'] != bool(_i110_np.any(wet & arrays['legal_outlet_mask']))):
        raise ValueError('surface network wet masks disagree')
    visited = _i110_np.zeros(shape, bool)
    queue = _i110_deque(map(tuple, _i110_np.argwhere(wet & arrays['legal_outlet_mask'])))
    for cell in queue:
        visited[cell] = True
    while queue:
        z, x = queue.popleft()
        for nz, nx in ((z - 1, x), (z + 1, x), (z, x - 1), (z, x + 1)):
            if 0 <= nz < shape[0] and 0 <= nx < shape[1] and wet[nz, nx] and (not visited[nz, nx]):
                visited[nz, nx] = True
                queue.append((nz, nx))
    if manifest['status'] == 'prepared' and (not _i110_np.array_equal(visited, wet)):
        raise ValueError('surface network has wet cells disconnected from outlet')
    weights = _i110_np.ones(shape)
    weights[[0, -1], :] *= 0.5
    weights[:, [0, -1]] *= 0.5
    cell_area = params['fine_spacing_x_m'] * params['fine_spacing_z_m']
    area = float(_i110_np.sum((arrays['bed_cut_m'] > 1e-09) * weights) * cell_area)
    volume = float(_i110_np.sum(arrays['bed_cut_m'] * weights) * cell_area)
    if not _i110_math.isclose(area, summary['area_m2'], abs_tol=1e-07) or not _i110_math.isclose(volume, summary['cut_volume_m3'], abs_tol=1e-07) or summary['budget_failures']['area'] != (area > params['max_area_m2'] + 1e-09) or (summary['budget_failures']['volume'] != (volume > params['max_cut_volume_m3'] + 1e-09)) or (summary['budget_failures']['bed_depth'] != bool(_i110_np.any(arrays['bed_cut_m'] > params['max_bed_cut_m'] + 1e-09))):
        raise ValueError('surface network budget summary mismatch')
    if summary['budget_failures']['outside_domain_cut'] != bool(_i110_np.any((arrays['bed_cut_m'] > 1e-09) & ~arrays['domain_mask'])) or summary['publishable'] != (not any(summary['budget_failures'].values()) and (not any(summary['joint_blockers'].values()))):
        raise ValueError('surface network gate mismatch')
    valid_status = manifest['status'] == 'prepared' and summary['publishable'] is True or (allow_diagnostic and manifest['status'] == 'diagnostic_not_publishable' and (summary['publishable'] is False))
    if not valid_status:
        raise ValueError('surface network status mismatch')
    for value in arrays.values():
        value.flags.writeable = False
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': manifest['status'], 'arrays': arrays, 'summary': summary}

def slice_surface_network(result, z_slice, x_slice):
    """Read a window from one prepared shared grid without rerouting or resampling."""
    if result['status'] != 'prepared':
        raise ValueError('only prepared networks support read-only slices')
    shape = result['arrays']['final_surface_m'].shape
    for item, limit in ((z_slice, shape[0]), (x_slice, shape[1])):
        if not isinstance(item, slice) or item.step not in (None, 1) or item.start is None or (item.stop is None) or (not 0 <= item.start < item.stop <= limit):
            raise ValueError('slice must be a bounded unit-step window')
    params = result['identity']['parameters']
    arrays = {name: value[z_slice, x_slice] for name, value in result['arrays'].items()}
    for value in arrays.values():
        value.flags.writeable = False
    return {'origin_x_m': params['fine_origin_x_m'] + x_slice.start * params['fine_spacing_x_m'], 'origin_z_m': params['fine_origin_z_m'] + z_slice.start * params['fine_spacing_z_m'], 'spacing_x_m': params['fine_spacing_x_m'], 'spacing_z_m': params['fine_spacing_z_m'], 'source_identity_sha256': result['identity_sha256'], 'arrays': arrays}
VERSION = 'surface-centerline-prepare-v1'
MAX_FINE_NODES = 2000000
MAX_PACKAGE_BYTES = 1000000000
MAX_ARCHIVE_MEMBERS = 100
MAX_GRAPH_NODES = 4096
MAX_EDGE_SAMPLES = 2000000
MAX_MANIFEST_BYTES = 1000000

def _readonly(value):
    return _i97_np.frombuffer(value.tobytes(order='C'), dtype=value.dtype).reshape(value.shape)

def _same(left, right):
    if {key: value for key, value in left.items() if key != 'arrays'} != {key: value for key, value in right.items() if key != 'arrays'}:
        return False
    return set(left['arrays']) == set(right['arrays']) and all((left['arrays'][name].dtype == right['arrays'][name].dtype and _i97_np.array_equal(left['arrays'][name], right['arrays'][name], equal_nan=True) for name in left['arrays']))

def _replay_plan(plan):
    from terrain_pipeline.channel_geometry import ChannelRecipe as _x58_ChannelRecipe
    from terrain_pipeline.channel_geometry import plan_channel as _x59_plan_channel
    if plan.get('status') != 'diagnostic_not_publishable':
        raise ValueError('diagnostic plan required')
    params = plan['identity']['parameters']
    recipe = _x58_ChannelRecipe(**{name: params[name] for name in _x58_ChannelRecipe.__dataclass_fields__})
    arrays = plan['arrays']
    rebuilt = _x59_plan_channel(arrays['source_height_m'], arrays['receiver'], arrays['order'], arrays['outlet_mask'], arrays['discharge_m3_s'], params['spacing_x_m'], params['spacing_z_m'], params['origin_x_m'], params['origin_z_m'], params['sea_level_elevation_m'], params['source_identity'], recipe)
    if not _same(plan, rebuilt):
        raise ValueError('plan replay differs from supplied geometry')
    discharge = arrays['discharge_m3_s'].ravel()
    incoming = _i97_np.zeros(discharge.size)
    receiver = arrays['receiver']
    routed = receiver >= 0
    _i97_np.add.at(incoming, receiver[routed], discharge[routed])
    donor_count = _i97_np.bincount(receiver[routed], minlength=discharge.size)
    roundoff = _i97_np.finfo(float).eps * _i97_np.maximum(discharge, incoming) * (donor_count + 1)
    if not _i97_np.isfinite(incoming).all() or _i97_np.any(incoming - discharge > roundoff):
        raise ValueError('discharge conservation requires nonnegative local inflow at every node')

def _replay_centerline(centerline, plan):
    from terrain_pipeline.channel_geometry import SmoothingRecipe as _x48_SmoothingRecipe
    from terrain_pipeline.channel_geometry import build_centerline as _x49_build_centerline
    from terrain_pipeline.channel_geometry import validate_centerline_for_plan as _x50_validate_centerline_for_plan
    _x50_validate_centerline_for_plan(centerline, plan)
    params = centerline['identity']['parameters']
    recipe = _x48_SmoothingRecipe(params['strength'], params['max_offset_m'], params['min_separation_m'])
    if not _same(centerline, _x49_build_centerline(plan, recipe)):
        raise ValueError('centerline replay differs from supplied geometry')

def _sample(field, x, z, origin_x, origin_z, spacing_x, spacing_z, masks=(), diagnostics=None, mask_names=()):
    fx = (x - origin_x) / spacing_x
    fz = (z - origin_z) / spacing_z
    if not (-1e-09 <= fx <= field.shape[1] - 1 + 1e-09 and -1e-09 <= fz <= field.shape[0] - 1 + 1e-09):
        if diagnostics is not None:
            diagnostics['outside_grid'] += 1
        return (None, False)
    fx = min(max(fx, 0.0), field.shape[1] - 1)
    fz = min(max(fz, 0.0), field.shape[0] - 1)
    x0, z0 = (_i97_math.floor(fx), _i97_math.floor(fz))
    x1, z1 = (min(x0 + 1, field.shape[1] - 1), min(z0 + 1, field.shape[0] - 1))
    tx, tz = (fx - x0, fz - z0)
    corners = ((z0, x0, (1 - tx) * (1 - tz)), (z0, x1, tx * (1 - tz)), (z1, x0, (1 - tx) * tz), (z1, x1, tx * tz))
    corners = [(row, col, weight) for row, col, weight in corners if weight > 0.0]
    invalid = set()
    for row, col, weight in corners:
        if not _i97_math.isfinite(float(field[row, col])):
            invalid.add('unknown')
        for index, mask in enumerate(masks):
            if not mask[row, col]:
                invalid.add(mask_names[index] if mask_names else 'mask')
    if invalid:
        if diagnostics is not None:
            for reason in invalid:
                diagnostics[reason] += 1
        return (None, False)
    return (sum((float(field[row, col]) * weight for row, col, weight in corners)), True)

def _outlet_connected(wet, legal):
    visited = _i97_np.zeros(wet.shape, bool)
    queue = _i97_deque(map(tuple, _i97_np.argwhere(wet & legal)))
    for cell in queue:
        visited[cell] = True
    while queue:
        row, col = queue.popleft()
        for next_row, next_col in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if 0 <= next_row < wet.shape[0] and 0 <= next_col < wet.shape[1] and wet[next_row, next_col] and (not visited[next_row, next_col]):
                visited[next_row, next_col] = True
                queue.append((next_row, next_col))
    return _i97_np.array_equal(visited, wet) and bool(_i97_np.any(wet & legal))

def _geometry_gate(plan, centerline, section, stage, flood, budget, stage_recipe):
    params = section['identity']['parameters']
    origin_x, origin_z = (params['origin_x_m'], params['origin_z_m'])
    spacing_x, spacing_z = (params['spacing_x_m'], params['spacing_z_m'])
    source = section['arrays']['source_surface_m']
    final = section['arrays']['bounded_surface_m']
    cut = source - final
    changed = cut > 1e-09
    weights = _i97_np.ones(final.shape)
    weights[[0, -1], :] *= 0.5
    weights[:, [0, -1]] *= 0.5
    area = float(_i97_np.sum(changed * weights) * spacing_x * spacing_z)
    volume = float(_i97_np.sum(cut * weights) * spacing_x * spacing_z)
    domain = flood['arrays']['domain_mask']
    protected = flood['arrays']['protected_mask']
    wet = flood['arrays']['wet_mask']
    water = flood['arrays']['water_surface_m']
    support_failures = {name: 0 for name in ('outside_grid', 'domain', 'protected', 'unknown', 'dry')}
    nodes = centerline['arrays']['node_flat_index']
    positions = centerline['arrays']['node_world_xz_m']
    lookup = {int(cell): index for index, cell in enumerate(nodes)}
    bed = plan['arrays']['bounded_bed_m'].ravel()
    stages = stage['arrays']['stage_m'].ravel()
    failures = {'bed_depth': bool(_i97_np.any(cut > budget.max_bed_cut_m + 1e-09)), 'area': area > budget.max_area_m2 + 1e-09, 'volume': volume > budget.max_cut_volume_m3 + 1e-09, 'protected': bool(_i97_np.any(changed & protected)) or section['summary']['protected_conflict_nodes'] > 0, 'outside_domain_cut': bool(_i97_np.any(changed & ~domain)), 'section': bool(section['summary']['blocked_by_plan'] or section['summary']['blocked_by_centerline'] or section['summary']['local_budget_conflict_nodes']), 'stage_bed_mismatch': False, 'edge_support': False, 'edge_clearance': False, 'edge_max_depth': False, 'wet_outlet_connectivity': not _outlet_connected(wet, flood['arrays']['legal_outlet_mask'])}
    max_bed_error = 0.0
    max_edge_bed_error = 0.0
    max_reconstruction_error = 0.0
    edge_reverse_bed_observed = False
    sample_count = 0
    for index, cell in enumerate(nodes):
        x, z = positions[index]
        sampled, valid = _sample(final, x, z, origin_x, origin_z, spacing_x, spacing_z, (domain, ~protected), support_failures, ('domain', 'protected'))
        if not valid:
            failures['edge_support'] = True
            continue
        max_bed_error = max(max_bed_error, abs(sampled - bed[cell]))
    failures['stage_bed_mismatch'] = bool(max_bed_error > budget.bed_match_tolerance_m)
    for donor, target in zip(centerline['arrays']['edge_donor_flat_index'], centerline['arrays']['edge_target_flat_index']):
        start, end = (positions[lookup[int(donor)]], positions[lookup[int(target)]])
        steps = max(1, int(_i97_math.ceil(2 * max(abs(end[0] - start[0]) / spacing_x, abs(end[1] - start[1]) / spacing_z))))
        previous_bed = None
        for step in range(steps + 1):
            fraction = step / steps
            x, z = start + fraction * (end - start)
            stage_here = (1 - fraction) * stages[donor] + fraction * stages[target]
            actual_bed, bed_valid = _sample(final, x, z, origin_x, origin_z, spacing_x, spacing_z, (domain, ~protected), support_failures, ('domain', 'protected'))
            actual_water, water_valid = _sample(water, x, z, origin_x, origin_z, spacing_x, spacing_z, (domain, ~protected, wet), support_failures, ('domain', 'protected', 'dry'))
            sample_count += 1
            if not bed_valid or not water_valid:
                failures['edge_support'] = True
                continue
            max_reconstruction_error = max(max_reconstruction_error, abs(actual_water - stage_here))
            ideal_bed = (1 - fraction) * bed[donor] + fraction * bed[target]
            max_edge_bed_error = max(max_edge_bed_error, abs(actual_bed - ideal_bed))
            if min(stage_here, actual_water) - actual_bed < stage_recipe.min_clearance_m - 1e-09:
                failures['edge_clearance'] = True
            if max(stage_here, actual_water) - actual_bed > stage_recipe.max_depth_m + 1e-09:
                failures['edge_max_depth'] = True
            if previous_bed is not None and actual_bed > previous_bed + 1e-09:
                edge_reverse_bed_observed = True
            previous_bed = actual_bed
    return (failures, {'area_m2': area, 'cut_volume_m3': volume, 'max_stage_bed_error_m': float(max_bed_error), 'max_edge_bed_error_m': float(max_edge_bed_error), 'support_failures': support_failures, 'max_water_reconstruction_error_m': float(max_reconstruction_error), 'edge_reverse_bed_observed': edge_reverse_bed_observed, 'edge_samples': sample_count})

def prepare_surface_centerline(plan, centerline, fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m, fine_spacing_z_m, fine_shape_zx, domain_mask, protected_mask, legal_outlet_mask, outlet_stage_m, section_recipe, stage_recipe, inundation_recipe, budget: SurfaceNetworkBudget):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i97_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i97_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i97_digest
    from terrain_pipeline.surface_hydraulics import evaluate_inundation as _x52_evaluate_inundation
    from terrain_pipeline.surface_hydraulics import assess_joint as _x53_assess_joint
    from terrain_pipeline.surface_hydraulics import solve_stage as _x55_solve_stage
    from terrain_pipeline.channel_geometry import evaluate_sections as _x57_evaluate_sections
    if not isinstance(budget, SurfaceNetworkBudget):
        raise ValueError('surface network budget required')
    if len(fine_shape_zx) != 2 or any((type(size) is not int or size < 2 for size in fine_shape_zx)) or _i97_math.prod(fine_shape_zx) > MAX_FINE_NODES:
        raise ValueError('fine grid resource limit exceeded')
    if plan['arrays']['source_height_m'].size > MAX_FINE_NODES:
        raise ValueError('plan grid resource limit exceeded')
    if _i97_np.count_nonzero(plan['arrays']['channel_mask']) > MAX_GRAPH_NODES:
        raise ValueError('active graph resource limit exceeded')
    if any((isinstance(value, bool) or not _i97_math.isfinite(value) for value in (fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m, fine_spacing_z_m))) or min(fine_spacing_x_m, fine_spacing_z_m) <= 0:
        raise ValueError('fine origin and spacing must be finite; spacing positive')
    for mask in (domain_mask, protected_mask, legal_outlet_mask):
        if _i97_np.asarray(mask).dtype != bool or _i97_np.asarray(mask).shape != tuple(fine_shape_zx):
            raise ValueError('fine masks must be boolean and match fine grid')
    _replay_plan(plan)
    _replay_centerline(centerline, plan)
    positions = centerline['arrays']['node_world_xz_m']
    lookup = {int(cell): index for index, cell in enumerate(centerline['arrays']['node_flat_index'])}
    sample_count = 0
    for donor, target in zip(centerline['arrays']['edge_donor_flat_index'], centerline['arrays']['edge_target_flat_index']):
        delta = _i97_np.abs(positions[lookup[int(donor)]] - positions[lookup[int(target)]])
        span = 2 * max(delta[0] / fine_spacing_x_m, delta[1] / fine_spacing_z_m)
        if not _i97_math.isfinite(span) or span > MAX_EDGE_SAMPLES:
            raise ValueError('edge sampling resource limit exceeded')
        sample_count += max(1, _i97_math.ceil(span)) + 1
    if sample_count > MAX_EDGE_SAMPLES:
        raise ValueError('edge sampling resource limit exceeded')
    section = _x57_evaluate_sections(plan, fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m, fine_spacing_z_m, fine_shape_zx, protected_mask, section_recipe, centerline)
    stage = _x55_solve_stage(plan, outlet_stage_m, stage_recipe, centerline)
    flood = _x52_evaluate_inundation(plan, section, stage, domain_mask, protected_mask, legal_outlet_mask, inundation_recipe, centerline)
    joint = _x53_assess_joint(plan, section, stage, flood)
    failures, metrics = _geometry_gate(plan, centerline, section, stage, flood, budget, stage_recipe)
    prepared = not any(failures.values()) and joint['pass']
    summary = {'publishable': prepared, 'budget_failures': failures, 'joint_blockers': joint['blockers'], 'section': section['summary'], 'stage': stage['summary'], 'inundation': flood['summary'], **metrics, 'moved_nodes': centerline['summary']['moved_nodes']}
    summary['needs_finer_grid'] = bool(failures['stage_bed_mismatch'] or joint['blockers']['resolution'])
    components = {'plan': plan, 'centerline': centerline, 'section': section, 'stage': stage, 'flood': flood}
    inputs = {'domain_mask': _i97_np.asarray(domain_mask).copy(), 'protected_mask': _i97_np.asarray(protected_mask).copy(), 'legal_outlet_mask': _i97_np.asarray(legal_outlet_mask).copy(), 'outlet_stage_m': _i97_np.asarray(outlet_stage_m, dtype=_i97_np.float64).copy()}
    arrays = {f'{group}__{name}': value.copy() for group, component in components.items() for name, value in component['arrays'].items()}
    arrays.update(inputs)
    identity = _i97_ArtifactIdentity('Terragenesis', 'surface-centerline-prepare', VERSION, 0, {'budget': _i97_asdict(budget), 'component_sha256': {name: value['identity_sha256'] for name, value in components.items()}, 'joint_sha256': joint['identity_sha256'], 'arrays_sha256': _i97_digest({name: _i97_array_hash(value) for name, value in arrays.items()}), 'summary_sha256': _i97_digest(summary)})
    arrays = {name: _readonly(value) for name, value in arrays.items()}
    return {'identity': identity.record(), 'identity_sha256': identity.sha256, 'status': 'prepared' if prepared else 'diagnostic_not_publishable', 'components': {name: {key: value[key] for key in ('identity', 'identity_sha256', 'status', 'summary') if key in value} for name, value in components.items()}, 'arrays': arrays, 'summary': summary}

def _validate(result, allow_diagnostic):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i97_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import array_hash as _i97_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i97_digest
    from terrain_pipeline.surface_hydraulics import InundationRecipe as _x51_InundationRecipe
    from terrain_pipeline.surface_hydraulics import StageRecipe as _x54_StageRecipe
    from terrain_pipeline.channel_geometry import SectionRecipe as _x56_SectionRecipe
    if len(result['arrays']) >= MAX_ARCHIVE_MEMBERS or any((not isinstance(value, _i97_np.ndarray) or value.dtype.hasobject or value.size > MAX_FINE_NODES * 20 or (value.nbytes > MAX_PACKAGE_BYTES) for value in result['arrays'].values())) or sum((value.nbytes for value in result['arrays'].values())) > MAX_PACKAGE_BYTES:
        raise ValueError('package resource limit exceeded')
    identity = _i97_ArtifactIdentity(**result['identity'])
    if identity.sha256 != result['identity_sha256'] or identity.algorithm != 'surface-centerline-prepare' or identity.algorithm_version != VERSION:
        raise ValueError('invalid prepare identity')
    params = identity.record()['parameters']
    if _i97_digest({name: _i97_array_hash(value) for name, value in result['arrays'].items()}) != params['arrays_sha256'] or _i97_digest(result['summary']) != params['summary_sha256']:
        raise ValueError('prepare hashes disagree')
    components = {}
    for group in ('plan', 'centerline', 'section', 'stage', 'flood'):
        component = result['components'][group]
        components[group] = {**component, 'arrays': {name.split('__', 1)[1]: value for name, value in result['arrays'].items() if name.startswith(group + '__')}}
        if component['identity_sha256'] != params['component_sha256'][group]:
            raise ValueError('component identity mismatch')
    section_params = components['section']['identity']['parameters']
    stage_params = components['stage']['identity']['parameters']
    flood_params = components['flood']['identity']['parameters']
    budget = SurfaceNetworkBudget(**params['budget'])
    if components['section']['arrays']['bounded_surface_m'].size > MAX_FINE_NODES:
        raise ValueError('fine grid resource limit exceeded')
    replayed = prepare_surface_centerline(components['plan'], components['centerline'], section_params['origin_x_m'], section_params['origin_z_m'], section_params['spacing_x_m'], section_params['spacing_z_m'], tuple(components['section']['arrays']['bounded_surface_m'].shape), result['arrays']['domain_mask'], result['arrays']['protected_mask'], result['arrays']['legal_outlet_mask'], result['arrays']['outlet_stage_m'], _x56_SectionRecipe(section_params['max_local_cut_m'], section_params['min_cells_across_width']), _x54_StageRecipe(**{name: stage_params[name] for name in _x54_StageRecipe.__dataclass_fields__}), _x51_InundationRecipe(flood_params['min_water_depth_m'], flood_params['max_lateral_reach_m']), budget)
    if result['status'] != replayed['status'] or result['summary'] != replayed['summary'] or result['identity_sha256'] != replayed['identity_sha256'] or (result['components'] != replayed['components']) or (not _same(result, replayed)):
        raise ValueError('prepare replay differs from saved result')
    if result['status'] != 'prepared' and (not allow_diagnostic):
        raise ValueError('diagnostic package requires explicit opt-in')
    return replayed

def save_surface_centerline(result, path, allow_diagnostic=False):
    result = _validate(result, allow_diagnostic)
    destination = _i97_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    manifest = {key: result[key] for key in ('identity', 'identity_sha256', 'status', 'components', 'summary')}
    manifest['format_version'] = 1
    temporary = None
    try:
        with _i97_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, delete=False, suffix='.npz') as stream:
            temporary = _i97_Path(stream.name)
            _i97_np.savez_compressed(stream, manifest=_i97_json.dumps(manifest, sort_keys=True), **result['arrays'])
        load_surface_centerline(temporary, allow_diagnostic=allow_diagnostic)
        _i97_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def load_surface_centerline(path, allow_diagnostic=False):
    with open(path, 'rb') as package:
        return _load_package(package, allow_diagnostic)

def _load_package(package, allow_diagnostic):
    with _i97_zipfile.ZipFile(package) as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS or len({item.filename for item in members}) != len(members) or sum((item.file_size for item in members)) > MAX_PACKAGE_BYTES or any((item.file_size > MAX_PACKAGE_BYTES or not item.filename.endswith('.npy') or '/' in item.filename or ('\\' in item.filename) for item in members)):
            raise ValueError('package resource limit exceeded')
        if 'manifest.npy' not in {item.filename for item in members}:
            raise ValueError('missing manifest')
        declared_bytes = 0
        for member in members:
            with archive.open(member) as stream:
                version = _i97_npy_format.read_magic(stream)
                if version == (1, 0):
                    shape, _, dtype = _i97_npy_format.read_array_header_1_0(stream)
                elif version == (2, 0):
                    shape, _, dtype = _i97_npy_format.read_array_header_2_0(stream)
                else:
                    raise ValueError('unsupported NPY version')
                elements = _i97_math.prod(shape)
                payload_bytes = elements * dtype.itemsize
                if dtype.hasobject or dtype.itemsize <= 0 or len(shape) > 2 or any((size < 0 for size in shape)) or (elements > MAX_FINE_NODES * 20) or (payload_bytes > MAX_PACKAGE_BYTES):
                    raise ValueError('NPY resource limit exceeded')
                if stream.tell() + payload_bytes != member.file_size:
                    raise ValueError('NPY declared bytes differ from member length')
                if member.filename == 'manifest.npy':
                    if shape != () or dtype.kind != 'U' or payload_bytes > MAX_MANIFEST_BYTES:
                        raise ValueError('invalid manifest NPY')
                elif dtype.kind not in 'bifu':
                    raise ValueError('invalid numeric NPY dtype')
                declared_bytes += payload_bytes
        if declared_bytes > MAX_PACKAGE_BYTES:
            raise ValueError('NPY aggregate resource limit exceeded')
    package.seek(0)
    with _i97_np.load(package, allow_pickle=False) as archive:
        if 'manifest' not in archive.files:
            raise ValueError('missing manifest')
        manifest = _i97_json.loads(str(archive['manifest'].item()))
        if manifest.pop('format_version') != 1:
            raise ValueError('unsupported package format')
        arrays = {name: archive[name].copy() for name in archive.files if name != 'manifest'}
    return _validate({**manifest, 'arrays': arrays}, allow_diagnostic)

def slice_surface_centerline(result, z_slice, x_slice):
    if result['status'] != 'prepared':
        raise ValueError('only prepared surfaces can be sliced')
    shape = result['arrays']['section__bounded_surface_m'].shape
    for selection, limit in ((z_slice, shape[0]), (x_slice, shape[1])):
        if not isinstance(selection, slice) or selection.step not in (None, 1) or selection.start is None or (selection.stop is None) or (not 0 <= selection.start < selection.stop <= limit):
            raise ValueError('bounded unit-step slices required')
    names = ('section__source_surface_m', 'section__bounded_surface_m', 'section__actual_cut_m', 'flood__water_surface_m', 'flood__wet_mask', 'domain_mask', 'protected_mask', 'legal_outlet_mask')
    arrays = {name: result['arrays'][name][z_slice, x_slice] for name in names}
    for value in arrays.values():
        value.flags.writeable = False
    params = result['components']['section']['identity']['parameters']
    return {'origin_x_m': params['origin_x_m'] + x_slice.start * params['spacing_x_m'], 'origin_z_m': params['origin_z_m'] + z_slice.start * params['spacing_z_m'], 'spacing_x_m': params['spacing_x_m'], 'spacing_z_m': params['spacing_z_m'], 'source_identity_sha256': result['identity_sha256'], 'arrays': arrays}
SURFACE_NETWORK_RECOVERY_VERSION = 'surface-network-recovery-v1'
SURFACE_NETWORK_RECOVERY_MAX_BUNDLE_BYTES = 256 * 1024 * 1024

@_i111_dataclass(frozen=True)
class FineGrid:
    """Explicit metre coordinates and frozen full-domain fine-grid masks."""
    origin_x_m: float
    origin_z_m: float
    spacing_x_m: float
    spacing_z_m: float
    shape_zx: tuple
    domain_mask: _i111_np.ndarray
    protected_mask: _i111_np.ndarray
    legal_outlet_mask: _i111_np.ndarray

    def __post_init__(self):
        from terrain_pipeline.channel_geometry import _immutable as _x80_immutable
        for name in ('origin_x_m', 'origin_z_m', 'spacing_x_m', 'spacing_z_m'):
            value = getattr(self, name)
            if isinstance(value, bool) or not _i111_math.isfinite(value) or (name.startswith('spacing') and value <= 0):
                raise ValueError('invalid fine grid coordinates')
        if len(self.shape_zx) != 2 or any((type(size) is not int or size <= 1 for size in self.shape_zx)) or _i111_math.prod(self.shape_zx) > 1000000:
            raise ValueError('invalid or excessive fine grid shape')
        object.__setattr__(self, 'shape_zx', tuple(self.shape_zx))
        for name in ('domain_mask', 'protected_mask', 'legal_outlet_mask'):
            mask = _i111_np.asarray(getattr(self, name))
            if mask.dtype != bool or mask.shape != self.shape_zx:
                raise ValueError('fine masks must be matching boolean grids')
            object.__setattr__(self, name, _x80_immutable(mask))
        if _i111_np.any(self.legal_outlet_mask & (~self.domain_mask | self.protected_mask)):
            raise ValueError('legal outlets conflict with fine domain or protection')

@_i111_dataclass(frozen=True)
class RecoveryRecipe:
    max_attempts: int = 12
    max_sources: int = 8
    anchor_lookahead: int = 8
    max_coarse_cells: int = 250000
    max_fine_cells: int = 1000000
    max_total_fine_cells: int = 4000000
    max_working_bytes: int = 268435456

    def __post_init__(self):
        ceilings = {'max_attempts': 32, 'max_sources': 64, 'anchor_lookahead': 128, 'max_coarse_cells': 250000, 'max_fine_cells': 1000000, 'max_total_fine_cells': 32000000, 'max_working_bytes': 536870912}
        if any((type(value) is not int or not 0 < value <= ceilings[name] for name, value in _i111_asdict(self).items())):
            raise ValueError('invalid recovery resource bounds')

def _surface_network_recovery_tree(value, arrays):
    from terrain_pipeline.artifacts.contracts import array_hash as _i111_array_hash
    if isinstance(value, _i111_np.ndarray):
        key = f'array_{len(arrays):05d}'
        arrays[key] = value
        return {'$array': key, 'sha256': _i111_array_hash(value), 'shape': list(value.shape), 'dtype': value.dtype.str}
    if isinstance(value, dict):
        return {key: _surface_network_recovery_tree(child, arrays) for key, child in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_surface_network_recovery_tree(child, arrays) for child in value]
    if isinstance(value, _i111_np.generic):
        return value.item()
    return value

def _fingerprint(value):
    from terrain_pipeline.artifacts.contracts import digest as _i111_digest
    return _i111_digest(_surface_network_recovery_tree(value, {}))

def _surface_network_recovery_freeze(value):
    from terrain_pipeline.channel_geometry import _immutable as _x80_immutable
    if isinstance(value, _i111_np.ndarray):
        return _x80_immutable(value)
    if isinstance(value, dict):
        return {key: _surface_network_recovery_freeze(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_surface_network_recovery_freeze(child) for child in value]
    return value

def _surface(plan, fine, outlet_stage, section, stage, inundation, budget):
    result = prepare_surface_network(plan, fine.origin_x_m, fine.origin_z_m, fine.spacing_x_m, fine.spacing_z_m, fine.shape_zx, fine.domain_mask, fine.protected_mask, fine.legal_outlet_mask, outlet_stage, section, stage, inundation, budget)
    if result['status'] == 'prepared':
        validate_surface_network(result)
    return result

def _coarse_gate(plan, domain, protected):
    active = plan['arrays']['channel_mask']
    return {'coarse_domain': bool(_i111_np.any(active & ~domain)), 'coarse_protection': bool(_i111_np.any(active & protected))}

def _consistent_masks(plan, domain, protected, fine):
    params = plan['identity']['parameters']
    shape = plan['arrays']['source_height_m'].shape
    axes = []
    for axis, count, origin, spacing in (('z', shape[0], fine.origin_z_m, fine.spacing_z_m), ('x', shape[1], fine.origin_x_m, fine.spacing_x_m)):
        positions = (params[f'origin_{axis}_m'] + _i111_np.arange(count) * params[f'spacing_{axis}_m'] - origin) / spacing
        indices = _i111_np.rint(positions).astype(_i111_np.int64)
        limit = fine.shape_zx[len(axes)]
        if not _i111_np.allclose(positions, indices, rtol=0, atol=1e-08) or indices[0] != 0 or indices[-1] != limit - 1:
            raise ValueError('fine grid must cover and align the full coarse grid')
        axes.append(indices)
    sample = _i111_np.ix_(*axes)
    if not _i111_np.array_equal(domain, fine.domain_mask[sample]) or not _i111_np.array_equal(protected, fine.protected_mask[sample]):
        raise ValueError('coarse and fine domain/protection disagree')

def _failure_nodes(original, surface, domain, protected, fine):
    arrays = original['arrays']
    active = arrays['channel_mask'].ravel()
    receiver = arrays['receiver']
    failed = active & (~domain.ravel() | protected.ravel())
    for name in ('over_budget_mask', 'failed_slope_edge_donor_mask'):
        failed |= arrays[name].ravel() & active
    params = original['identity']['parameters']
    columns = arrays['source_height_m'].shape[1]
    if surface is not None:
        surface_arrays = surface['arrays']
        failures = surface['summary']['budget_failures']
        fine_failure = _i111_np.zeros(fine.shape_zx, bool)
        for name in ('disconnected_seed_mask', 'boundary_contact_mask', 'reach_limited_mask'):
            fine_failure |= surface_arrays[name]
        fine_failure |= (surface_arrays['bed_cut_m'] > 1e-09) & (fine.protected_mask | ~fine.domain_mask)
        if any(failures.values()):
            fine_failure |= surface_arrays['bed_cut_m'] > 1e-09
        for donor in _i111_np.flatnonzero(active & (receiver >= 0)):
            target = int(receiver[donor])
            endpoints = []
            for cell in (donor, target):
                endpoints.append((int(round((params['origin_z_m'] + cell // columns * params['spacing_z_m'] - fine.origin_z_m) / fine.spacing_z_m)), int(round((params['origin_x_m'] + cell % columns * params['spacing_x_m'] - fine.origin_x_m) / fine.spacing_x_m))))
            start, end = endpoints
            steps = max(abs(end[0] - start[0]), abs(end[1] - start[1]), 1)
            for step in range(steps + 1):
                fraction = step / steps
                cell = (int(round(start[0] + fraction * (end[0] - start[0]))), int(round(start[1] + fraction * (end[1] - start[1]))))
                if fine_failure[cell]:
                    failed[donor] = True
                    break
        if any(surface['summary']['joint_blockers'].values()) and (not _i111_np.any(failed)):
            failed |= active & (receiver >= 0)
    return failed

def _failure_sources(original, failed, domain, protected, recipe):
    arrays = original['arrays']
    active = arrays['channel_mask'].ravel()
    receiver = arrays['receiver']
    upstream = [[] for _ in range(receiver.size)]
    for donor in _i111_np.flatnonzero(active & (receiver >= 0)):
        upstream[int(receiver[donor])].append(int(donor))
    candidates = []
    seen = set()
    for failure in _i111_np.flatnonzero(failed):
        queue = list(upstream[int(failure)])
        if domain.flat[failure] and (not protected.flat[failure]):
            queue.append(int(failure))
        position = 0
        while position < len(queue) and len(candidates) < recipe.max_sources:
            cell = queue[position]
            position += 1
            if cell in seen:
                continue
            seen.add(cell)
            queue.extend(upstream[cell])
            if domain.flat[cell] and (not protected.flat[cell]) and (receiver[cell] >= 0):
                candidates.append(cell)
        if len(candidates) >= recipe.max_sources:
            break
    return candidates
from terrain_pipeline.surface_hydraulics import RerouteRecipe as _x73_RerouteRecipe

def recover_surface_network(plan, coarse_domain, coarse_protected, fine, outlet_stage_m, section_recipe, stage_recipe, inundation_recipe, budget, network_recipe, valley_recipe, reroute_recipe=_x73_RerouteRecipe(), recovery_recipe=RecoveryRecipe()):
    """Try original bed, whole-network valley, then failure-driven original-plan routes.

    Legal outlets are caller-supplied boundary conditions, not natural-outlet evidence.
    Failed outcomes diagnose a possible lake requirement; they never publish lake water.
    """
    from terrain_pipeline.artifacts.contracts import array_hash as _i111_array_hash
    from terrain_pipeline.surface_hydraulics import reroute_channel as _x72_reroute_channel
    from terrain_pipeline.surface_hydraulics import _local_discharge as _x74_local_discharge
    from terrain_pipeline.surface_hydraulics import InundationRecipe as _x75_InundationRecipe
    from terrain_pipeline.surface_hydraulics import StageRecipe as _x76_StageRecipe
    from terrain_pipeline.channel_geometry import SectionRecipe as _x77_SectionRecipe
    from terrain_pipeline.channel_geometry import ChannelRecipe as _x78_ChannelRecipe
    from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _x79_NetworkValleyRecipe
    from terrain_pipeline.channel_geometry import _immutable as _x80_immutable
    from terrain_pipeline.channel_geometry import _validated_source_plan as _x81_validated_source_plan
    from terrain_pipeline.channel_geometry import prepare_network_valley as _x82_prepare_network_valley
    from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _x83_ValleyGeometryRecipe
    from terrain_pipeline.channel_geometry import evaluate_fine_valley_ledger as _x84_evaluate_fine_valley_ledger
    expected_types = ((fine, FineGrid), (section_recipe, _x77_SectionRecipe), (stage_recipe, _x76_StageRecipe), (inundation_recipe, _x75_InundationRecipe), (budget, SurfaceNetworkBudget), (network_recipe, _x79_NetworkValleyRecipe), (valley_recipe, _x83_ValleyGeometryRecipe), (reroute_recipe, _x73_RerouteRecipe), (recovery_recipe, RecoveryRecipe))
    if any((not isinstance(value, expected) for value, expected in expected_types)):
        raise ValueError('explicit recovery grids and recipes required')
    shape = _i111_np.asarray(plan['arrays']['source_height_m']).shape
    if len(shape) != 2 or _i111_math.prod(shape) > recovery_recipe.max_coarse_cells:
        raise ValueError('recovery exceeds coarse cell bound')
    if _i111_math.prod(fine.shape_zx) > recovery_recipe.max_fine_cells:
        raise ValueError('recovery exceeds fine cell bound')
    if _i111_math.prod(fine.shape_zx) * 512 + _i111_math.prod(shape) * 1024 > recovery_recipe.max_working_bytes:
        raise ValueError('recovery exceeds working memory bound')
    original = _x81_validated_source_plan(plan)
    _x74_local_discharge(original)
    domain, protected = (_i111_np.asarray(coarse_domain), _i111_np.asarray(coarse_protected))
    if any((mask.shape != shape or mask.dtype != bool for mask in (domain, protected))):
        raise ValueError('coarse masks must be matching boolean grids')
    domain, protected = (_x80_immutable(domain), _x80_immutable(protected))
    _consistent_masks(original, domain, protected, fine)
    original_outlets = original['arrays']['channel_mask'] & original['arrays']['outlet_mask']
    params = original['identity']['parameters']
    outlet_rows, outlet_columns = _i111_np.nonzero(original_outlets)
    fine_rows = _i111_np.rint((params['origin_z_m'] + outlet_rows * params['spacing_z_m'] - fine.origin_z_m) / fine.spacing_z_m).astype(int)
    fine_columns = _i111_np.rint((params['origin_x_m'] + outlet_columns * params['spacing_x_m'] - fine.origin_x_m) / fine.spacing_x_m).astype(int)
    if not _i111_np.all(fine.legal_outlet_mask[fine_rows, fine_columns]):
        raise ValueError('active plan outlets must map to explicit legal fine outlets')
    channel = _x78_ChannelRecipe(**{name: original['identity']['parameters'][name] for name in _x78_ChannelRecipe.__dataclass_fields__})
    if reroute_recipe.max_extra_cut_m > min(channel.max_cut_m, budget.max_bed_cut_m, section_recipe.max_local_cut_m):
        raise ValueError('reroute extra cut exceeds original allowed bed limit')
    outlet_stage = _i111_np.asarray(outlet_stage_m)
    count = int(_i111_np.count_nonzero(original['arrays']['channel_mask'] & original['arrays']['outlet_mask']))
    if outlet_stage.dtype.kind not in 'fiu' or outlet_stage.shape != (count,) or (not _i111_np.isfinite(outlet_stage).all()):
        raise ValueError('outlet stages must match original active outlets')
    inputs = {'plan': original, 'coarse_domain': domain, 'coarse_protected': protected, 'fine': {'origin_x_m': fine.origin_x_m, 'origin_z_m': fine.origin_z_m, 'spacing_x_m': fine.spacing_x_m, 'spacing_z_m': fine.spacing_z_m, 'shape_zx': list(fine.shape_zx), 'domain_mask': fine.domain_mask, 'protected_mask': fine.protected_mask, 'legal_outlet_mask': fine.legal_outlet_mask}, 'outlet_stage_m': _x80_immutable(outlet_stage), 'section_recipe': _i111_asdict(section_recipe), 'stage_recipe': _i111_asdict(stage_recipe), 'inundation_recipe': _i111_asdict(inundation_recipe), 'budget': _i111_asdict(budget), 'network_recipe': _i111_asdict(network_recipe), 'valley_recipe': _i111_asdict(valley_recipe), 'reroute_recipe': _i111_asdict(reroute_recipe), 'recovery_recipe': _i111_asdict(recovery_recipe)}
    attempts = []
    failed_nodes = _failure_nodes(original, None, domain, protected, fine)
    fine_work = 0
    work_exhausted = False
    last = {'plan': original, 'valley': None, 'surface': None, 'fine_ledger': None}
    selected = None

    def evaluate(candidate, method, valley=False, source=None, anchor=None, reroute=None):
        nonlocal last, selected, fine_work, work_exhausted, failed_nodes
        if len(attempts) >= recovery_recipe.max_attempts:
            return False
        if fine_work + _i111_math.prod(fine.shape_zx) > recovery_recipe.max_total_fine_cells:
            work_exhausted = True
            return False
        fine_work += _i111_math.prod(fine.shape_zx)
        attempt = {'index': len(attempts), 'method': method, 'source_grid_zx': source, 'anchor_grid_zx': anchor, 'source_plan_sha256': original['identity_sha256'], 'accepted': False}
        attempts.append(attempt)
        last = {'plan': candidate, 'valley': None, 'surface': None, 'fine_ledger': None}
        outcome = {'plan': candidate, 'valley': None, 'surface': None, 'fine_ledger': None}
        try:
            coarse_failures = _coarse_gate(candidate, domain, protected)
            coarse_failures['active_outlets_changed'] = not _i111_np.array_equal(candidate['arrays']['channel_mask'] & candidate['arrays']['outlet_mask'], original_outlets)
            if valley:
                outcome['valley'] = _x82_prepare_network_valley(candidate, domain, protected, network_recipe, valley_recipe, channel)
                candidate = outcome['valley']['replanned_plan']
                outcome['plan'] = candidate
            outcome['surface'] = _surface(candidate, fine, outlet_stage, section_recipe, stage_recipe, inundation_recipe, budget)
            if valley:
                outcome['fine_ledger'] = _x84_evaluate_fine_valley_ledger(outcome['valley'], outcome['surface'])
            surface = outcome['surface']
            failures = {**coarse_failures, **surface['summary']['budget_failures'], **{f'joint_{name}': value for name, value in surface['summary']['joint_blockers'].items()}}
            if valley:
                failures.update({f'ledger_{name}': value for name, value in outcome['fine_ledger']['summary']['failures'].items()})
            accepted = surface['status'] == 'prepared' and (not any(failures.values()))
            attempt.update({'accepted': accepted, 'failures': failures, 'plan_sha256': candidate['identity_sha256'], 'surface_summary': surface['summary'], 'fine_ledger_summary': None if not valley else outcome['fine_ledger']['summary'], 'reroute_summary': None if reroute is None else reroute['summary'], 'path_grid_zx': None if reroute is None else reroute['path_grid_zx']})
            if accepted:
                selected = method
        except ValueError as error:
            attempt['error'] = str(error)
        last = outcome
        failed_nodes |= _failure_nodes(original, outcome['surface'], domain, protected, fine)
        return attempt['accepted']
    accepted = evaluate(original, 'baseline')
    if not accepted:
        accepted = evaluate(original, 'network_valley', valley=True)
    exhausted_candidates = True
    if not accepted and (not work_exhausted) and (len(attempts) < recovery_recipe.max_attempts):
        sources = _failure_sources(original, failed_nodes, domain, protected, recovery_recipe)
        columns = shape[1]
        for source_id in sources:
            anchor_id = int(original['arrays']['receiver'][source_id])
            for _ in range(recovery_recipe.anchor_lookahead):
                if anchor_id < 0 or accepted:
                    break
                source = [source_id // columns, source_id % columns]
                anchor = [anchor_id // columns, anchor_id % columns]
                if not domain.flat[anchor_id] or protected.flat[anchor_id] or (not original['arrays']['channel_mask'].flat[anchor_id]):
                    anchor_id = int(original['arrays']['receiver'][anchor_id])
                    continue
                if work_exhausted or len(attempts) >= recovery_recipe.max_attempts:
                    exhausted_candidates = False
                    break
                try:
                    reroute = _x72_reroute_channel(original, source, anchor, domain, protected, reroute_recipe)
                except ValueError as error:
                    attempts.append({'index': len(attempts), 'method': 'reroute_search', 'source_grid_zx': source, 'anchor_grid_zx': anchor, 'source_plan_sha256': original['identity_sha256'], 'accepted': False, 'error': str(error)})
                else:
                    accepted = evaluate(reroute['plan'], 'reroute_bed', source=source, anchor=anchor, reroute=reroute)
                    if not accepted:
                        accepted = evaluate(reroute['plan'], 'reroute_valley', valley=True, source=source, anchor=anchor, reroute=reroute)
                anchor_id = int(original['arrays']['receiver'][anchor_id])
            if accepted or work_exhausted or len(attempts) >= recovery_recipe.max_attempts:
                break
    resource_exhausted = not accepted and (work_exhausted or len(attempts) >= recovery_recipe.max_attempts)
    constraint_failure = any((any((value for key, value in attempt.get('failures', {}).items() if any((word in key for word in ('protection', 'domain', 'volume', 'area', 'depth'))))) for attempt in attempts))
    status = 'accepted' if accepted else 'failed' if resource_exhausted or constraint_failure else 'lake_required'
    result = {'algorithm_version': SURFACE_NETWORK_RECOVERY_VERSION, 'inputs': inputs, 'status': status, 'accepted': accepted, 'selected_method': selected, 'attempts': attempts, 'final_plan': last['plan'], 'valley': last['valley'], 'surface': last['surface'], 'fine_ledger': last['fine_ledger'], 'summary': {'attempt_count': len(attempts), 'attempt_limit_reached': resource_exhausted, 'total_fine_cells_evaluated': fine_work, 'fine_work_limit_reached': work_exhausted, 'candidate_search_exhausted': not accepted and exhausted_candidates and (not resource_exhausted), 'outlet_evidence': 'caller_supplied_not_naturally_certified', 'lake_published': False, 'original_height_sha256': _i111_array_hash(original['arrays']['source_height_m'])}}
    result['identity_sha256'] = _fingerprint(result)
    return _surface_network_recovery_freeze(result)

def _replay(inputs):
    from terrain_pipeline.surface_hydraulics import InundationRecipe as _x75_InundationRecipe
    from terrain_pipeline.surface_hydraulics import StageRecipe as _x76_StageRecipe
    from terrain_pipeline.channel_geometry import SectionRecipe as _x77_SectionRecipe
    from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _x79_NetworkValleyRecipe
    from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _x83_ValleyGeometryRecipe
    return recover_surface_network(inputs['plan'], inputs['coarse_domain'], inputs['coarse_protected'], FineGrid(**inputs['fine']), inputs['outlet_stage_m'], _x77_SectionRecipe(**inputs['section_recipe']), _x76_StageRecipe(**inputs['stage_recipe']), _x75_InundationRecipe(**inputs['inundation_recipe']), SurfaceNetworkBudget(**inputs['budget']), _x79_NetworkValleyRecipe(**inputs['network_recipe']), _x83_ValleyGeometryRecipe(**inputs['valley_recipe']), _x73_RerouteRecipe(**inputs['reroute_recipe']), RecoveryRecipe(**inputs['recovery_recipe']))

def validate_surface_network_recovery(result):
    """Replay actual fine water and cumulative ledger, not a trusted saved summary."""
    try:
        if result['algorithm_version'] != SURFACE_NETWORK_RECOVERY_VERSION:
            raise ValueError('unsupported recovery algorithm')
        replayed = _replay(result['inputs'])
        if _fingerprint(result) != _fingerprint(replayed):
            raise ValueError('recovery differs from semantic replay')
        return replayed
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError('invalid recovery bundle') from error

def save_surface_network_recovery(result, path):
    """Atomically create an immutable diagnostic bundle; never replace any file."""
    from terrain_pipeline.artifacts.contracts import digest as _i111_digest
    destination = _i111_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    validated = validate_surface_network_recovery(result)
    arrays = {}
    tree = _surface_network_recovery_tree(validated, arrays)
    manifest = {'format_version': 1, 'tree': tree, 'tree_sha256': _i111_digest(tree)}
    temporary = None
    try:
        with _i111_tempfile.NamedTemporaryFile(mode='wb', dir=destination.parent, suffix='.npz', delete=False) as stream:
            temporary = _i111_Path(stream.name)
            _i111_np.savez_compressed(stream, manifest=_i111_json.dumps(manifest, sort_keys=True), **arrays)
            stream.flush()
            _i111_os.fsync(stream.fileno())
        load_surface_network_recovery(temporary)
        _i111_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def load_surface_network_recovery(path):
    """Check bounded payload hashes and replay every chosen or failed computation."""
    from terrain_pipeline.artifacts.contracts import array_hash as _i111_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i111_digest
    from terrain_pipeline.channel_geometry import _immutable as _x80_immutable
    try:
        with _i111_zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 4096 or sum((item.file_size for item in entries)) > SURFACE_NETWORK_RECOVERY_MAX_BUNDLE_BYTES or len({item.filename for item in entries}) != len(entries):
                raise ValueError('recovery bundle exceeds resource bound')
            for entry in entries:
                with archive.open(entry) as stream:
                    version = _i111_np.lib.format.read_magic(stream)
                    if version == (1, 0):
                        shape, _, dtype = _i111_np.lib.format.read_array_header_1_0(stream)
                    elif version == (2, 0):
                        shape, _, dtype = _i111_np.lib.format.read_array_header_2_0(stream)
                    else:
                        raise ValueError('unsupported bundle array format')
                    if dtype.hasobject or _i111_math.prod(shape) * dtype.itemsize > SURFACE_NETWORK_RECOVERY_MAX_BUNDLE_BYTES or _i111_math.prod(shape) * dtype.itemsize != entry.file_size - stream.tell():
                        raise ValueError('invalid or excessive bundle array header')
                    if entry.filename == 'manifest.npy' and (shape != () or dtype.kind != 'U' or dtype.itemsize > 4 * 1024 * 1024):
                        raise ValueError('recovery manifest must be a bounded Unicode scalar')
        with _i111_np.load(path, allow_pickle=False) as archive:

            def unique_pairs(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('duplicate recovery JSON key')
                    result[key] = value
                return result

            def reject_constant(value):
                raise ValueError('nonfinite recovery JSON constant: ' + value)
            manifest = _i111_json.loads(str(archive['manifest'].item()), object_pairs_hook=unique_pairs, parse_constant=reject_constant)
            if manifest['format_version'] != 1 or _i111_digest(manifest['tree']) != manifest['tree_sha256']:
                raise ValueError('invalid recovery manifest hash')
            used = {'manifest'}

            def decode(value):
                if isinstance(value, dict) and '$array' in value:
                    key = value['$array']
                    if key in used or set(value) != {'$array', 'sha256', 'shape', 'dtype'}:
                        raise ValueError('invalid recovery array reference')
                    used.add(key)
                    array = archive[key]
                    if array.dtype.kind not in 'bifu' or array.dtype.str != value['dtype'] or list(array.shape) != value['shape'] or (_i111_array_hash(array) != value['sha256']):
                        raise ValueError('recovery array hash or shape mismatch')
                    return _x80_immutable(array)
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value
            result = decode(manifest['tree'])
            if used != set(archive.files):
                raise ValueError('unexpected recovery bundle arrays')
        return validate_surface_network_recovery(result)
    except (KeyError, TypeError, OSError, RecursionError, _i111_zipfile.BadZipFile, _i111_json.JSONDecodeError) as error:
        raise ValueError('invalid recovery bundle') from error

def prepare_with_reroute(plan, source_grid_zx, anchor_grid_zx, coarse_domain, coarse_protected, fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m, fine_spacing_z_m, fine_shape_zx, fine_domain, fine_protected, fine_legal_outlet, outlet_stage_m, section_recipe, stage_recipe, inundation_recipe, budget, reroute_recipe=_x73_RerouteRecipe()):
    """Run a changed D8 graph/Q through the same fine geometry and water gate."""
    from terrain_pipeline.surface_hydraulics import reroute_channel as _x72_reroute_channel
    if reroute_recipe.max_extra_cut_m > min(budget.max_bed_cut_m, section_recipe.max_local_cut_m):
        raise ValueError('reroute extra cut exceeds original allowed bed limit')
    candidate = _x72_reroute_channel(plan, source_grid_zx, anchor_grid_zx, coarse_domain, coarse_protected, reroute_recipe)
    result = prepare_surface_network(candidate['plan'], fine_origin_x_m, fine_origin_z_m, fine_spacing_x_m, fine_spacing_z_m, fine_shape_zx, fine_domain, fine_protected, fine_legal_outlet, outlet_stage_m, section_recipe, stage_recipe, inundation_recipe, budget)
    if result['status'] == 'prepared':
        validate_surface_network(result)
    return {'status': result['status'], 'reroute': candidate, 'surface_network': result, 'accepted': result['status'] == 'prepared' and candidate['summary']['bed_plan_feasible']}
SURFACE_NETWORK_CONSUMER_VERSION = 'surface-network-consumer-v1'
SURFACE_NETWORK_CONSUMER_MAX_BYTES = 256 * 1024 * 1024
GEOMETRY = {'source_surface_m', 'valley_surface_m', 'final_surface_m', 'valley_cut_m', 'bed_cut_m', 'total_cut_m', 'water_surface_m', 'wet_mask', 'domain_mask', 'protected_mask', 'legal_outlet_mask'}
GRAPH = {'world_xz_m', 'receiver', 'order', 'discharge_m3_s', 'active_mask', 'outlet_mask', 'local_discharge_m3_s', 'node_stage_m'}
HYDROLOGY = {'geometry_unit': 'm', 'discharge_unit': 'm3/s', 'Q_semantics': 'coarse_node_reach_discharge_not_additive_across_nodes', 'dry_stage_placeholder_m': 0.0, 'natural_outlets_certified': False, 'lake_water_published': False}

def _surface_network_consumer_immutable(value):
    array = _i108_np.ascontiguousarray(value)
    return _i108_np.frombuffer(array.tobytes(), dtype=array.dtype).reshape(array.shape)

def _surface_network_consumer_freeze(value):
    if isinstance(value, _i108_np.ndarray):
        return _surface_network_consumer_immutable(value)
    if isinstance(value, dict):
        return _i108_MappingProxyType({key: _surface_network_consumer_freeze(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple((_surface_network_consumer_freeze(child) for child in value))
    return value

def _surface_network_consumer_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate delivery JSON key')
        result[key] = value
    return result

def _surface_network_consumer_constant(value):
    raise ValueError('nonfinite delivery JSON constant: ' + value)

def _read_json(path):
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('delivery manifest exceeds bound')
    return _i108_json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_surface_network_consumer_pairs, parse_constant=_surface_network_consumer_constant)

def _file_hash(path):
    result = _i108_hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()

def _array_record(arrays):
    from terrain_pipeline.artifacts.contracts import array_hash as _i108_array_hash
    return {name: {'sha256': _i108_array_hash(array), 'shape': list(array.shape), 'dtype': array.dtype.str} for name, array in sorted(arrays.items())}

def _named(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 2048 or (value != value.strip()) or any((ord(char) < 32 for char in value)) or (value.lower() in {'unknown', 'none', 'null', 'nan', 'unspecified', '?'}):
        raise ValueError('explicit ' + name + ' required')
    return value

def _reject_link_chain(path):
    absolute = _i108_Path(_i108_os.path.abspath(path))
    for item in (absolute, *absolute.parents):
        try:
            record = item.lstat()
        except FileNotFoundError:
            continue
        if item.is_symlink() or getattr(record, 'st_file_attributes', 0) & getattr(_i108_stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024):
            raise ValueError('delivery paths must not contain symlinks or junctions')

def _surface_network_consumer_identity(result):
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i108_ArtifactIdentity
    identity = _i108_ArtifactIdentity(**result['identity'])
    if identity.sha256 != result['identity_sha256']:
        raise ValueError('proof algorithm identity mismatch')
    return result['identity']['parameters']

def _local_q(arrays):
    receiver, order = (arrays['receiver'], arrays['order'])
    height = arrays['source_height_m']
    count = height.size
    if height.ndim != 2 or count > 250000 or receiver.shape != (count,) or (order.shape != (count,)) or (receiver.dtype.kind not in 'iu') or (order.dtype.kind not in 'iu') or _i108_np.any((receiver < -1) | (receiver >= count)) or (not _i108_np.array_equal(_i108_np.sort(order), _i108_np.arange(count))):
        raise ValueError('invalid delivered route/order')
    rank = _i108_np.empty(count, dtype=_i108_np.int64)
    rank[order] = _i108_np.arange(count)
    donors = _i108_np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    if _i108_np.any(rank[targets] >= rank[donors]):
        raise ValueError('delivered route is cyclic or not receiver-first')
    discharge = arrays['discharge_m3_s'].ravel()
    if arrays['discharge_m3_s'].shape != height.shape or not _i108_np.isfinite(discharge).all() or _i108_np.any(discharge < 0) or (arrays['channel_mask'].dtype != bool) or (arrays['channel_mask'].shape != height.shape) or (arrays['outlet_mask'].dtype != bool) or (arrays['outlet_mask'].shape != height.shape) or (not _i108_np.array_equal(arrays['outlet_mask'].ravel(), receiver == -1)):
        raise ValueError('invalid delivered Q or outlet masks')
    active = arrays['channel_mask'].ravel()
    if _i108_np.any(active[donors] & ~active[targets]):
        raise ValueError('active channel terminates before its outlet')
    local = discharge.copy()
    _i108_np.subtract.at(local, targets, discharge[donors])
    total = float(discharge[receiver < 0].sum())
    if _i108_np.any(local < -1e-08) or not _i108_math.isclose(float(local.sum()), total, rel_tol=1e-10, abs_tol=1e-08):
        raise ValueError('delivered Q is nonconservative')
    return (local, total)

def _plan_proof(plan):
    from terrain_pipeline.artifacts.contracts import array_hash as _i108_array_hash
    params = _surface_network_consumer_identity(plan)
    arrays = plan['arrays']
    for name in ('spacing_x_m', 'spacing_z_m', 'origin_x_m', 'origin_z_m', 'sea_level_elevation_m'):
        value = params[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i108_math.isfinite(value)) or (name.startswith('spacing') and value <= 0):
            raise ValueError('invalid delivered coarse coordinates')
    for name, parameter in (('source_height_m', 'source_height_sha256'), ('receiver', 'source_route_sha256'), ('order', 'source_order_sha256'), ('outlet_mask', 'source_outlet_sha256'), ('discharge_m3_s', 'source_discharge_sha256')):
        if _i108_array_hash(arrays[name]) != params[parameter]:
            raise ValueError('delivered plan source hash mismatch')
    if not _i108_np.isfinite(arrays['source_height_m']).all():
        raise ValueError('nonfinite delivered coarse source')
    _named(params['source_identity'], 'plan source identity')
    return _local_q(arrays)

def _fine_source(height, coarse, fine):
    rows, columns = fine['shape_zx']
    x = (fine['origin_x_m'] + _i108_np.arange(columns) * fine['spacing_x_m'] - coarse['origin_x_m']) / coarse['spacing_x_m']
    z = (fine['origin_z_m'] + _i108_np.arange(rows) * fine['spacing_z_m'] - coarse['origin_z_m']) / coarse['spacing_z_m']
    if x[0] < -1e-08 or z[0] < -1e-08 or x[-1] > height.shape[1] - 1 + 1e-08 or (z[-1] > height.shape[0] - 1 + 1e-08):
        raise ValueError('delivered fine grid leaves original source')
    x, z = (_i108_np.clip(x, 0, height.shape[1] - 1), _i108_np.clip(z, 0, height.shape[0] - 1))
    left, top = (_i108_np.floor(x).astype(int), _i108_np.floor(z).astype(int))
    right, bottom = (_i108_np.minimum(left + 1, height.shape[1] - 1), _i108_np.minimum(top + 1, height.shape[0] - 1))
    fraction_x, fraction_z = ((x - left)[None, :], (z - top)[:, None])
    return (1 - fraction_x) * (1 - fraction_z) * height[_i108_np.ix_(top, left)] + fraction_x * (1 - fraction_z) * height[_i108_np.ix_(top, right)] + (1 - fraction_x) * fraction_z * height[_i108_np.ix_(bottom, left)] + fraction_x * fraction_z * height[_i108_np.ix_(bottom, right)]

def _grid_indices(plan, fine):
    params = plan['identity']['parameters']
    rows, columns = _i108_np.indices(plan['arrays']['source_height_m'].shape)
    world_x = params['origin_x_m'] + columns.ravel() * params['spacing_x_m']
    world_z = params['origin_z_m'] + rows.ravel() * params['spacing_z_m']
    fine_x, fine_z = ((world_x - fine['origin_x_m']) / fine['spacing_x_m'], (world_z - fine['origin_z_m']) / fine['spacing_z_m'])
    ix, iz = (_i108_np.rint(fine_x).astype(int), _i108_np.rint(fine_z).astype(int))
    if not _i108_np.allclose(fine_x, ix, atol=1e-08, rtol=0) or not _i108_np.allclose(fine_z, iz, atol=1e-08, rtol=0) or _i108_np.any(ix < 0) or _i108_np.any(iz < 0) or _i108_np.any(ix >= fine['shape_zx'][1]) or _i108_np.any(iz >= fine['shape_zx'][0]):
        raise ValueError('delivered graph is not aligned with fine grid')
    return (_i108_np.column_stack((world_x, world_z)), iz, ix)

def _payload(recovery):
    surface, ledger = (recovery['surface'], recovery['fine_ledger'])
    source = surface['arrays']['source_surface_m'] if ledger is None else ledger['arrays']['source_surface_m']
    final = surface['arrays']['final_surface_m'] if ledger is None else ledger['arrays']['final_surface_m']
    valley_surface, wet = (surface['arrays']['source_surface_m'], surface['arrays']['wet_mask'])
    water = _i108_np.where(wet, surface['arrays']['water_surface_m'], 0.0)
    arrays = {'source_surface_m': source, 'valley_surface_m': valley_surface, 'final_surface_m': final, 'valley_cut_m': source - valley_surface, 'bed_cut_m': valley_surface - final, 'total_cut_m': source - final, 'water_surface_m': water, 'wet_mask': wet, **{name: surface['arrays'][name] for name in ('domain_mask', 'protected_mask', 'legal_outlet_mask')}}
    plan, fine = (recovery['final_plan'], recovery['inputs']['fine'])
    positions, rows, columns = _grid_indices(plan, fine)
    local, _ = _local_q(plan['arrays'])
    active = plan['arrays']['channel_mask'].ravel()
    arrays.update(world_xz_m=positions, receiver=plan['arrays']['receiver'], order=plan['arrays']['order'], discharge_m3_s=plan['arrays']['discharge_m3_s'].ravel(), active_mask=active, outlet_mask=plan['arrays']['outlet_mask'].ravel(), local_discharge_m3_s=local, node_stage_m=_i108_np.where(active, water[rows, columns], 0.0))
    return arrays

def _surface_network_consumer_geometry_gate(arrays, recovery):
    from terrain_pipeline.artifacts.contracts import array_hash as _i108_array_hash
    source, valley_surface, final = (arrays[name] for name in ('source_surface_m', 'valley_surface_m', 'final_surface_m'))
    shape = source.shape
    fine = recovery['inputs']['fine']
    for name in ('origin_x_m', 'origin_z_m', 'spacing_x_m', 'spacing_z_m'):
        value = fine[name]
        if isinstance(value, bool) or not _i108_math.isfinite(value) or (name.startswith('spacing') and value <= 0):
            raise ValueError('invalid delivered fine coordinates')
    if shape != tuple(fine['shape_zx']) or source.ndim != 2 or source.size > 1000000:
        raise ValueError('invalid delivered fine shape')
    inputs = recovery['inputs']
    for recipe_name in ('budget', 'valley_recipe', 'stage_recipe', 'inundation_recipe', 'section_recipe'):
        if any((isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i108_math.isfinite(value)) or (value < 0) for value in inputs[recipe_name].values())):
            raise ValueError('invalid delivered numeric recipe')
    for name in GEOMETRY:
        array = arrays[name]
        if array.shape != shape or (name.endswith('mask') and array.dtype != bool):
            raise ValueError('invalid delivered geometry/mask shape')
        if not name.endswith('mask') and (array.dtype.kind not in 'fiu' or not _i108_np.isfinite(array).all()):
            raise ValueError('delivered geometry must be finite')
    for name, expected in (('valley_cut_m', source - valley_surface), ('bed_cut_m', valley_surface - final), ('total_cut_m', source - final)):
        if _i108_np.any(arrays[name] < -1e-09) or not _i108_np.allclose(arrays[name], expected, atol=1e-09, rtol=0):
            raise ValueError('delivered cut is negative or inconsistent')
    wet, water = (arrays['wet_mask'], arrays['water_surface_m'])
    domain, protected, legal = (arrays[name] for name in ('domain_mask', 'protected_mask', 'legal_outlet_mask'))
    changed = arrays['total_cut_m'] > 1e-09
    if not wet.any() or _i108_np.any(water[~wet] != 0) or _i108_np.any(water[wet] <= final[wet]) or _i108_np.any(wet & (~domain | protected)) or _i108_np.any(changed & (~domain | protected)) or _i108_np.any(legal & (~domain | protected)):
        raise ValueError('delivered wet water, domain or protection is invalid')
    boundary = _i108_np.zeros(shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    if _i108_np.any(wet & boundary & ~legal):
        raise ValueError('delivered water touches an undeclared boundary')
    threshold = max(0.5, inputs['inundation_recipe']['min_water_depth_m'] * 10)
    for axis in (0, 1):
        first = [slice(None), slice(None)]
        second = [slice(None), slice(None)]
        first[axis], second[axis] = (slice(None, -1), slice(1, None))
        before, after = (tuple(first), tuple(second))
        adjacent_wet = wet[before] & wet[after]
        if _i108_np.any(adjacent_wet & (_i108_np.abs(water[before] - water[after]) > threshold + 1e-09)):
            raise ValueError('delivered adjacent wet stage transition exceeds original threshold')
    visited = _i108_np.zeros(shape, bool)
    queue = _i108_deque(map(tuple, _i108_np.argwhere(wet & legal)))
    for cell in queue:
        visited[cell] = True
    while queue:
        row, column = queue.popleft()
        for next_row, next_column in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1)):
            if 0 <= next_row < shape[0] and 0 <= next_column < shape[1] and wet[next_row, next_column] and (not visited[next_row, next_column]):
                visited[next_row, next_column] = True
                queue.append((next_row, next_column))
    if not _i108_np.array_equal(visited, wet):
        raise ValueError('delivered wet water is not four-connected to legal outlets')
    original = recovery['inputs']['plan']
    if _i108_array_hash(original['arrays']['source_height_m']) != recovery['summary']['original_height_sha256']:
        raise ValueError('original H0 hash disagrees with delivery provenance')
    h0 = _fine_source(original['arrays']['source_height_m'], original['identity']['parameters'], fine)
    if not _i108_np.allclose(source, h0, atol=1e-08, rtol=0):
        raise ValueError('delivery H0 is not the original source')
    _, rows, columns = _grid_indices(recovery['final_plan'], fine)
    active, outlets = (arrays['active_mask'], arrays['outlet_mask'])
    if _i108_np.any(active & (~inputs['coarse_domain'].ravel() | inputs['coarse_protected'].ravel())) or not _i108_np.array_equal(domain[rows, columns], inputs['coarse_domain'].ravel()) or (not _i108_np.array_equal(protected[rows, columns], inputs['coarse_protected'].ravel())) or (not _i108_np.all(wet[rows[active], columns[active]])) or (not _i108_np.all(legal[rows[active & outlets], columns[active & outlets]])):
        raise ValueError('delivered route, fine masks or active outlets disagree')
    for name in ('domain_mask', 'protected_mask', 'legal_outlet_mask'):
        if not _i108_np.array_equal(arrays[name], fine[name]):
            raise ValueError('delivered fine masks differ from original constraints')
    bounded_bed = recovery['final_plan']['arrays']['bounded_bed_m'].ravel()
    if not _i108_np.allclose(final[rows[active], columns[active]], bounded_bed[active], atol=inputs['budget']['bed_match_tolerance_m'], rtol=0):
        raise ValueError('delivered surface does not match actual channel bed')
    plan_arrays = recovery['final_plan']['arrays']
    for donor in _i108_np.flatnonzero(active & (arrays['receiver'] >= 0)):
        target = int(arrays['receiver'][donor])
        steps = max(abs(rows[target] - rows[donor]), abs(columns[target] - columns[donor]))
        previous_bed = None
        for step in range(steps + 1):
            fraction = step / steps
            row = int(round(rows[donor] + fraction * (rows[target] - rows[donor])))
            column = int(round(columns[donor] + fraction * (columns[target] - columns[donor])))
            stage = arrays['node_stage_m'][donor] * (1 - fraction) + arrays['node_stage_m'][target] * fraction
            depth = stage - final[row, column]
            if not wet[row, column] or depth < inputs['stage_recipe']['min_clearance_m'] - 1e-09 or depth > inputs['stage_recipe']['max_depth_m'] + 1e-09 or (previous_bed is not None and final[row, column] > previous_bed + 1e-09):
                raise ValueError('delivered fine channel edge is dry, blocked or reverse-sloped')
            previous_bed = final[row, column]
    h1 = _fine_source(plan_arrays['source_height_m'], recovery['final_plan']['identity']['parameters'], fine)
    if not _i108_np.allclose(valley_surface, h1, atol=1e-08, rtol=0):
        raise ValueError('delivery H1 differs from actual final plan coarse source')
    if recovery['valley'] is None:
        if not _i108_np.array_equal(original['arrays']['source_height_m'], plan_arrays['source_height_m']):
            raise ValueError('non-valley final plan changed original H0')
    else:
        valley_arrays = recovery['valley']['arrays']
        if not _i108_np.array_equal(valley_arrays['source_height_m'], original['arrays']['source_height_m']) or not _i108_np.array_equal(valley_arrays['valley_surface_m'], plan_arrays['source_height_m']):
            raise ValueError('delivery valley H0/H1 source chain differs')
    weights = _i108_np.ones(shape)
    weights[[0, -1], :] *= 0.5
    weights[:, [0, -1]] *= 0.5
    cell_area = fine['spacing_x_m'] * fine['spacing_z_m']

    def area(cut):
        return float(_i108_np.sum((cut > 1e-09) * weights) * cell_area)

    def volume(cut):
        return float(_i108_np.sum(cut * weights) * cell_area)
    budget = inputs['budget']
    if any((isinstance(value, bool) or not _i108_math.isfinite(value) or value < 0 for value in budget.values())):
        raise ValueError('invalid delivered original budget')
    bed_cut, valley_cut = (arrays['bed_cut_m'], arrays['valley_cut_m'])
    if _i108_np.any(bed_cut > budget['max_bed_cut_m'] + 1e-09) or area(bed_cut) > budget['max_area_m2'] + 1e-09 or volume(bed_cut) > budget['max_cut_volume_m3'] + 1e-09:
        raise ValueError('delivered actual bed exceeds original budget')
    if recovery['valley'] is not None:
        recipe = inputs['valley_recipe']
        if any((isinstance(value, bool) or not _i108_math.isfinite(value) or value < 0 for value in recipe.values())):
            raise ValueError('invalid delivered valley budget')
        if _i108_np.any(valley_cut > recipe['max_valley_depth_m'] + 1e-09) or area(valley_cut) > recipe['max_valley_area_m2'] + 1e-09 or volume(valley_cut) > recipe['max_valley_volume_m3'] + 1e-09 or (area(arrays['total_cut_m']) > recipe['max_total_cut_area_m2'] + 1e-09) or (volume(arrays['total_cut_m']) > recipe['max_total_cut_volume_m3'] + 1e-09):
            raise ValueError('delivered cumulative fine ledger exceeds original budget')

def _proof_gate(recovery, arrays):
    from terrain_pipeline.artifacts.contracts import array_hash as _i108_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i108_digest
    if recovery['accepted'] is not True or recovery['status'] != 'accepted' or (not recovery['attempts']) or (recovery['attempts'][-1]['accepted'] is not True) or (recovery['selected_method'] != recovery['attempts'][-1]['method']) or any(recovery['attempts'][-1]['failures'].values()):
        raise ValueError('delivery requires genuinely accepted recovery proof')
    shape = recovery['inputs']['fine']['shape_zx']
    if not isinstance(shape, list) or len(shape) != 2 or any((type(size) is not int or size <= 1 for size in shape)) or (_i108_math.prod(shape) > 1000000):
        raise ValueError('invalid delivered proof fine shape')
    record = {key: value for key, value in recovery.items() if key != 'identity_sha256'}
    if _fingerprint(record) != recovery['identity_sha256']:
        raise ValueError('recovery proof payload hash mismatch')
    original, final = (recovery['inputs']['plan'], recovery['final_plan'])
    original_local, original_total = _plan_proof(original)
    final_local, final_total = _plan_proof(final)
    if not _i108_np.allclose(original_local, final_local, rtol=0, atol=1e-08) or not _i108_math.isclose(original_total, final_total, abs_tol=1e-08, rel_tol=1e-10) or (not _i108_np.array_equal(original['arrays']['channel_mask'] & original['arrays']['outlet_mask'], final['arrays']['channel_mask'] & final['arrays']['outlet_mask'])):
        raise ValueError('delivered graph changes Q sources or active outlets')
    surface = recovery['surface']
    for name in ('disconnected_seed_mask', 'boundary_contact_mask', 'reach_limited_mask'):
        if surface['arrays'][name].dtype != bool or _i108_np.any(surface['arrays'][name]):
            raise ValueError('delivered prepared surface retains failure masks')
    if any((surface['summary']['inundation'][name] != 0 for name in ('stage_mismatch_nodes', 'reach_limited_nodes', 'disconnected_seed_nodes', 'boundary_contact_nodes'))):
        raise ValueError('delivered prepared surface retains diagnosed failures')
    if _i108_np.any(surface['arrays']['channel_seed_mask'] & ~surface['arrays']['wet_mask']) or surface['summary']['inundation']['channel_seed_nodes'] != int(surface['arrays']['channel_seed_mask'].sum()):
        raise ValueError('delivered surface seeds are not actual wet geometry')
    surface_params = _surface_network_consumer_identity(surface)
    if surface['status'] != 'prepared' or surface['summary']['publishable'] is not True or any(surface['summary']['budget_failures'].values()) or any(surface['summary']['joint_blockers'].values()) or (surface_params['plan_sha256'] != final['identity_sha256']) or (surface_params['summary_sha256'] != _i108_digest(surface['summary'])) or (surface_params['output_sha256'] != _i108_digest({name: _i108_array_hash(value) for name, value in surface['arrays'].items()})):
        raise ValueError('delivered surface acceptance proof is inconsistent')
    if any((surface_params[name] != value for name, value in recovery['inputs']['budget'].items())):
        raise ValueError('delivered surface budget differs from original recipe')
    valley, ledger = (recovery['valley'], recovery['fine_ledger'])
    if (valley is None) != (ledger is None):
        raise ValueError('valley delivery requires cumulative fine ledger')
    if ledger is not None:
        ledger_params, valley_params = (_surface_network_consumer_identity(ledger), _surface_network_consumer_identity(valley))
        if ledger['status'] != 'prepared' or any(ledger['summary']['failures'].values()) or valley['summary']['geometry_feasible'] is not True or any(valley['summary']['failures'].values()) or (ledger_params['surface_identity_sha256'] != surface['identity_sha256']) or (ledger_params['valley_identity_sha256'] != valley['identity_sha256']) or (ledger_params['summary_sha256'] != _i108_digest(ledger['summary'])) or (ledger_params['arrays_sha256'] != _i108_digest({name: _i108_array_hash(value) for name, value in ledger['arrays'].items()})) or (valley_params['replanned_sha256'] != final['identity_sha256']):
            raise ValueError('delivered cumulative fine ledger proof is inconsistent')
        if valley_params['arrays_sha256'] != _i108_digest(_array_record(valley['arrays'])) or valley_params['summary_sha256'] != _i108_digest(valley['summary']) or any((valley_params[name] != value or ledger_params[name] != value for name, value in recovery['inputs']['valley_recipe'].items())):
            raise ValueError('delivered valley arrays or budget proof differs')
        for name in ('source_surface_m', 'valley_surface_m', 'final_surface_m', 'valley_cut_m', 'bed_cut_m', 'total_cut_m'):
            if not _i108_np.allclose(ledger['arrays'][name], arrays[name], atol=1e-08, rtol=0):
                raise ValueError('delivered fine ledger geometry disagrees')
    surface_water, surface_wet = (surface['arrays']['water_surface_m'], surface['arrays']['wet_mask'])
    if not _i108_np.isnan(surface_water[~surface_wet]).all() or not _i108_np.isfinite(surface_water[surface_wet]).all():
        raise ValueError('invalid original surface wet/dry geometry')
    expected = _payload(recovery)
    for name in GEOMETRY | GRAPH:
        actual = arrays[name]
        if actual.dtype != expected[name].dtype or actual.shape != expected[name].shape or (not _i108_np.array_equal(actual, expected[name], equal_nan=True)):
            raise ValueError('delivery payload disagrees with proof: ' + name)
    _surface_network_consumer_geometry_gate(arrays, recovery)

def export_surface_network(recovery, vertical_datum, path, *, source_declaration=None):
    """Replay accepted recovery once; atomically deliver terrain plus node hydrology."""
    from terrain_pipeline.artifacts.contracts import ArtifactIdentity as _i108_ArtifactIdentity
    from terrain_pipeline.artifacts.contracts import TerrainArtifact as _i108_TerrainArtifact
    from terrain_pipeline.artifacts.contracts import canonical_json as _i108_canonical_json
    from terrain_pipeline.artifacts.contracts import digest as _i108_digest
    from terrain_pipeline.common_infra import save_artifact as _i108_save_artifact
    datum = _named(vertical_datum, 'vertical datum')
    declaration = _named(source_declaration, 'source declaration')
    destination = _i108_Path(path)
    _reject_link_chain(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    validated = validate_surface_network_recovery(recovery)
    if validated['accepted'] is not True or validated['status'] != 'accepted':
        raise ValueError('only actually accepted recovery may be delivered')
    arrays = _payload(validated)
    _proof_gate(validated, arrays)
    fine = validated['inputs']['fine']
    grid = {name: fine[name] for name in ('origin_x_m', 'origin_z_m', 'spacing_x_m', 'spacing_z_m')}
    grid.update(vertical_datum=datum, sea_level_elevation_m=validated['inputs']['plan']['identity']['parameters']['sea_level_elevation_m'])
    shared = {'recovery_sha256': validated['identity_sha256'], 'source_declaration': declaration, 'original_height_sha256': validated['summary']['original_height_sha256']}
    base = _i108_TerrainArtifact('base', _i108_ArtifactIdentity('Terragenesis', 'surface-network-base-delivery', SURFACE_NETWORK_CONSUMER_VERSION, 0, shared), arrays['source_surface_m'], **grid)
    displacement = _i108_np.zeros((3, *fine['shape_zx']))
    displacement[1] = arrays['final_surface_m'] - arrays['source_surface_m']
    derived = _i108_TerrainArtifact('derived', _i108_ArtifactIdentity('Terragenesis', 'surface-network-derived-delivery', SURFACE_NETWORK_CONSUMER_VERSION, 0, {**shared, 'base_content_id': base.content_id}), arrays['source_surface_m'], **grid, displacement_type='vertical', displacement_m=displacement, source_artifact_id=base.content_id)
    proof_arrays = {}
    proof = _surface_network_recovery_tree(validated, proof_arrays)
    arrays.update(proof_arrays)
    if sum((array.nbytes for array in arrays.values())) > SURFACE_NETWORK_CONSUMER_MAX_BYTES:
        raise ValueError('delivery payload exceeds resource bound')
    temporary = _i108_Path(_i108_tempfile.mkdtemp(prefix='.' + destination.name + '-', dir=destination.parent))
    try:
        _i108_save_artifact(base, temporary / 'base')
        _i108_save_artifact(derived, temporary / 'derived')
        with (temporary / 'hydro.npz').open('xb') as stream:
            _i108_np.savez_compressed(stream, **arrays)
            stream.flush()
            _i108_os.fsync(stream.fileno())
        files = {name: _file_hash(temporary / name) for name in ('base/manifest.json', 'base/arrays.npz', 'derived/manifest.json', 'derived/arrays.npz', 'hydro.npz')}
        manifest = {'format_version': 1, 'algorithm_version': SURFACE_NETWORK_CONSUMER_VERSION, 'base_content_id': base.content_id, 'derived_content_id': derived.content_id, 'grid': base.grid_record(), 'source_declaration': declaration, 'recovery_sha256': validated['identity_sha256'], 'proof': proof, 'arrays': _array_record(arrays), 'files': files, 'hydrology': HYDROLOGY.copy()}
        manifest['content_id'] = _i108_digest(manifest)
        with (temporary / 'manifest.json').open('x', encoding='utf-8') as stream:
            stream.write(_i108_canonical_json(manifest))
            stream.flush()
            _i108_os.fsync(stream.fileno())
        load_surface_network_delivery(temporary)
        if destination.exists():
            raise FileExistsError(destination)
        _i108_os.rename(temporary, destination)
    finally:
        if temporary.exists():
            resolved = temporary.resolve()
            if resolved.parent != destination.parent.resolve() or not resolved.name.startswith('.' + destination.name + '-'):
                raise ValueError('refusing cleanup outside delivery staging directory')
            _i108_shutil.rmtree(resolved)
    return destination

def _bounded_npz(path):
    with _i108_zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 4096 or len({entry.filename for entry in entries}) != len(entries) or sum((entry.file_size for entry in entries)) > SURFACE_NETWORK_CONSUMER_MAX_BYTES:
            raise ValueError('delivery archive exceeds resource bound')
        for entry in entries:
            with archive.open(entry) as stream:
                version = _i108_np.lib.format.read_magic(stream)
                if version == (1, 0):
                    shape, _, dtype = _i108_np.lib.format.read_array_header_1_0(stream)
                elif version == (2, 0):
                    shape, _, dtype = _i108_np.lib.format.read_array_header_2_0(stream)
                else:
                    raise ValueError('unsupported delivery array format')
                size = _i108_math.prod(shape) * dtype.itemsize
                if dtype.kind not in 'bifu' or dtype.hasobject or size > SURFACE_NETWORK_CONSUMER_MAX_BYTES or (size != entry.file_size - stream.tell()):
                    raise ValueError('invalid delivery array header')
        return sum((entry.file_size for entry in entries))

def load_surface_network_delivery(path):
    """Validate stored arithmetic/provenance only; never recover, prepare or model."""
    from terrain_pipeline.artifacts.contracts import digest as _i108_digest
    from terrain_pipeline.common_infra import load_artifact as _i108_load_artifact
    directory = _i108_Path(path)
    try:
        _reject_link_chain(directory)
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        if directory.is_symlink() or {entry.name for entry in directory.iterdir()} != {'base', 'derived', 'manifest.json', 'hydro.npz'}:
            raise ValueError('invalid delivery directory layout')
        for name in ('base', 'derived', 'manifest.json', 'hydro.npz'):
            item = directory / name
            _reject_link_chain(item)
            if item.is_symlink() or (not item.is_dir() if name in ('base', 'derived') else not item.is_file()):
                raise ValueError('delivery entries must be regular files/directories')
        manifest = _read_json(directory / 'manifest.json')
        expected = {'format_version', 'algorithm_version', 'base_content_id', 'derived_content_id', 'grid', 'source_declaration', 'recovery_sha256', 'proof', 'arrays', 'files', 'hydrology', 'content_id'}
        if set(manifest) != expected or type(manifest['format_version']) is not int or manifest['format_version'] != 1 or (manifest['algorithm_version'] != SURFACE_NETWORK_CONSUMER_VERSION) or (_i108_digest({key: value for key, value in manifest.items() if key != 'content_id'}) != manifest['content_id']):
            raise ValueError('invalid delivery manifest identity')
        _named(manifest['source_declaration'], 'source declaration')
        _named(manifest['grid']['vertical_datum'], 'vertical datum')
        file_names = {'base/manifest.json', 'base/arrays.npz', 'derived/manifest.json', 'derived/arrays.npz', 'hydro.npz'}
        if set(manifest['files']) != file_names:
            raise ValueError('invalid delivery file hash fields')
        if sum(((directory / name).stat().st_size for name in file_names)) > SURFACE_NETWORK_CONSUMER_MAX_BYTES:
            raise ValueError('delivery files exceed total resource bound')
        for name in file_names:
            item = directory / name
            _reject_link_chain(item)
            if not item.is_file() or item.is_symlink() or _file_hash(item) != manifest['files'][name]:
                raise ValueError('delivery file hash mismatch')
        total_bytes = sum((_bounded_npz(directory / name) for name in ('hydro.npz', 'base/arrays.npz', 'derived/arrays.npz')))
        if total_bytes > SURFACE_NETWORK_CONSUMER_MAX_BYTES:
            raise ValueError('delivery archives exceed total uncompressed resource bound')
        base, derived = (_i108_load_artifact(directory / 'base'), _i108_load_artifact(directory / 'derived'))
        derived.verify_source(base)
        if base.kind != 'base' or derived.kind != 'derived' or base.water is not None or (derived.water is not None) or (base.content_id != manifest['base_content_id']) or (derived.content_id != manifest['derived_content_id']) or (base.grid_record() != manifest['grid']) or (derived.grid_record() != manifest['grid']) or (derived.displacement_type != 'vertical'):
            raise ValueError('delivery terrain package chain mismatch')
        with _i108_np.load(directory / 'hydro.npz', allow_pickle=False) as archive:
            if set(archive.files) != set(manifest['arrays']):
                raise ValueError('delivery array fields mismatch')
            arrays = {name: _surface_network_consumer_immutable(archive[name]) for name in archive.files}
        if _array_record(arrays) != manifest['arrays']:
            raise ValueError('delivery array hash mismatch')
        used = set(GEOMETRY | GRAPH)

        def unpack(value):
            if isinstance(value, dict) and '$array' in value:
                name = value['$array']
                if not name.startswith('array_') or set(value) != {'$array', 'sha256', 'shape', 'dtype'}:
                    raise ValueError('invalid delivery proof array reference')
                used.add(name)
                if {key: value[key] for key in ('sha256', 'shape', 'dtype')} != manifest['arrays'][name]:
                    raise ValueError('delivery proof array hash mismatch')
                return arrays[name]
            if isinstance(value, dict):
                return {key: unpack(child) for key, child in value.items()}
            if isinstance(value, list):
                return [unpack(child) for child in value]
            return value
        recovery = unpack(manifest['proof'])
        if used != set(arrays):
            raise ValueError('unused delivery proof arrays')
        if recovery['identity_sha256'] != manifest['recovery_sha256']:
            raise ValueError('delivery recovery source identity mismatch')
        fine = recovery['inputs']['fine']
        if any((manifest['grid'][name] != fine[name] for name in ('origin_x_m', 'origin_z_m', 'spacing_x_m', 'spacing_z_m', 'shape_zx'))) or manifest['grid']['sea_level_elevation_m'] != recovery['inputs']['plan']['identity']['parameters']['sea_level_elevation_m']:
            raise ValueError('delivery grid differs from actual recovery coordinates')
        for artifact, algorithm in ((base, 'surface-network-base-delivery'), (derived, 'surface-network-derived-delivery')):
            params = artifact.identity.record()['parameters']
            if artifact.identity.algorithm != algorithm or artifact.identity.algorithm_version != SURFACE_NETWORK_CONSUMER_VERSION or params['recovery_sha256'] != manifest['recovery_sha256'] or (params['source_declaration'] != manifest['source_declaration']) or (params['original_height_sha256'] != recovery['summary']['original_height_sha256']):
                raise ValueError('delivery artifact provenance mismatch')
        if derived.identity.record()['parameters']['base_content_id'] != base.content_id:
            raise ValueError('delivery derived base provenance mismatch')
        _proof_gate(recovery, arrays)
        if not _i108_np.array_equal(base.reference_elevation_m, arrays['source_surface_m']) or not _i108_np.array_equal(derived.reference_elevation_m, arrays['source_surface_m']) or (not _i108_np.allclose(derived.reference_elevation_m + derived.displacement_m[1], arrays['final_surface_m'], rtol=0, atol=1e-09)):
            raise ValueError('delivery artifacts do not encode actual H0/H2')
        if manifest['hydrology'] != HYDROLOGY:
            raise ValueError('unsupported delivered hydrology semantics')
        return _i108_MappingProxyType({'base': base, 'derived': derived, 'manifest': _surface_network_consumer_freeze(manifest), 'geometry': _i108_MappingProxyType({name: arrays[name] for name in GEOMETRY}), 'centerline': _i108_MappingProxyType({name: arrays[name] for name in GRAPH})})
    except (KeyError, TypeError, OverflowError, RecursionError, _i108_zipfile.BadZipFile, _i108_json.JSONDecodeError) as error:
        raise ValueError('invalid surface network delivery') from error

def slice_surface_network_delivery(delivery, z_slice, x_slice):
    """Return immutable overlapping grid windows without interpolation or rerouting."""
    grid = delivery['manifest']['grid']
    for item, limit in ((z_slice, grid['shape_zx'][0]), (x_slice, grid['shape_zx'][1])):
        if not isinstance(item, slice) or item.step not in (None, 1) or type(item.start) is not int or (type(item.stop) is not int) or (not 0 <= item.start < item.stop <= limit):
            raise ValueError('delivery slice must be a bounded unit-step window')
    arrays = {name: array[z_slice, x_slice] for name, array in delivery['geometry'].items()}
    arrays['water_depth_m'] = _surface_network_consumer_immutable(_i108_np.where(arrays['wet_mask'], arrays['water_surface_m'] - arrays['final_surface_m'], 0.0))
    return _i108_MappingProxyType({'origin_x_m': grid['origin_x_m'] + x_slice.start * grid['spacing_x_m'], 'origin_z_m': grid['origin_z_m'] + z_slice.start * grid['spacing_z_m'], 'spacing_x_m': grid['spacing_x_m'], 'spacing_z_m': grid['spacing_z_m'], 'vertical_datum': grid['vertical_datum'], 'unit': 'm', 'content_id': delivery['manifest']['content_id'], 'arrays': _i108_MappingProxyType(arrays)})

def _world_index(value, origin, spacing, count):
    if isinstance(value, bool) or not isinstance(value, (int, float, _i108_np.integer, _i108_np.floating)) or (not _i108_math.isfinite(value)):
        raise ValueError('world coordinate must be finite metres')
    coordinate = (value - origin) / spacing
    index = round(coordinate)
    if not 0 <= index < count or not _i108_math.isclose(coordinate, index, rel_tol=0, abs_tol=1e-08):
        raise ValueError('world coordinate must address an existing aligned grid node')
    return index

def sample_surface_network(delivery, world_x_m, world_z_m):
    """Read one exact fine node; stage zero is a placeholder only when wet=False."""
    grid = delivery['manifest']['grid']
    column = _world_index(world_x_m, grid['origin_x_m'], grid['spacing_x_m'], grid['shape_zx'][1])
    row = _world_index(world_z_m, grid['origin_z_m'], grid['spacing_z_m'], grid['shape_zx'][0])
    return slice_surface_network_delivery(delivery, slice(row, row + 1), slice(column, column + 1))

def slice_surface_network_world(delivery, bounds_xz_m):
    """Read an inclusive aligned (xmin,zmin,xmax,zmax) world-coordinate window."""
    if not isinstance(bounds_xz_m, (tuple, list)) or len(bounds_xz_m) != 4:
        raise ValueError('world bounds must be xmin,zmin,xmax,zmax')
    grid = delivery['manifest']['grid']
    min_x, min_z, max_x, max_z = bounds_xz_m
    start_x = _world_index(min_x, grid['origin_x_m'], grid['spacing_x_m'], grid['shape_zx'][1])
    end_x = _world_index(max_x, grid['origin_x_m'], grid['spacing_x_m'], grid['shape_zx'][1])
    start_z = _world_index(min_z, grid['origin_z_m'], grid['spacing_z_m'], grid['shape_zx'][0])
    end_z = _world_index(max_z, grid['origin_z_m'], grid['spacing_z_m'], grid['shape_zx'][0])
    return slice_surface_network_delivery(delivery, slice(start_z, end_z + 1), slice(start_x, end_x + 1))
SURFACE_DOMAIN_PREPARE_VERSION = 'surface-domain-prepare-irregular-v2'
LEGACY_VERSION = 'surface-domain-prepare-v1'
MAX_INPUT_CELLS = 1500000

@_i102_dataclass(frozen=True)
class SurfaceDomainResources:
    max_coarse_cells: int = 250000
    max_coarse_work_cells: int = 500000
    max_fine_cells: int = 1000000
    max_fine_work_cells: int = 4000000
    max_attempts: int = 32
    max_retained_bytes: int = SURFACE_NETWORK_CONSUMER_MAX_BYTES
    max_domains: int = 64

    def __post_init__(self):
        ceilings = (MAX_INPUT_CELLS, 8000000, 8000000, 32000000, 256, SURFACE_NETWORK_CONSUMER_MAX_BYTES, 256)
        if any((type(value) is not int or not 0 < value <= ceiling for value, ceiling in zip(_i102_asdict(self).values(), ceilings))):
            raise ValueError('invalid shared domain resource bounds')

@_i102_dataclass(frozen=True)
class DomainFineConfiguration:
    fine: FineGrid
    outlet_stage_m: _i102_np.ndarray
    channel_recipe: _x64_ChannelRecipe
    section_recipe: _x63_SectionRecipe
    stage_recipe: _x62_StageRecipe
    inundation_recipe: _x60_InundationRecipe
    budget: SurfaceNetworkBudget
    network_recipe: _x66_NetworkValleyRecipe
    valley_recipe: _x67_ValleyGeometryRecipe
    reroute_recipe: _x61_RerouteRecipe
    recovery_recipe: RecoveryRecipe

    def __post_init__(self):
        from terrain_pipeline.surface_hydraulics import InundationRecipe as _x60_InundationRecipe
        from terrain_pipeline.surface_hydraulics import RerouteRecipe as _x61_RerouteRecipe
        from terrain_pipeline.surface_hydraulics import StageRecipe as _x62_StageRecipe
        from terrain_pipeline.channel_geometry import SectionRecipe as _x63_SectionRecipe
        from terrain_pipeline.channel_geometry import ChannelRecipe as _x64_ChannelRecipe
        from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _x66_NetworkValleyRecipe
        from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _x67_ValleyGeometryRecipe
        expected = (FineGrid, _i102_np.ndarray, _x64_ChannelRecipe, _x63_SectionRecipe, _x62_StageRecipe, _x60_InundationRecipe, SurfaceNetworkBudget, _x66_NetworkValleyRecipe, _x67_ValleyGeometryRecipe, _x61_RerouteRecipe, RecoveryRecipe)
        if any((not isinstance(value, kind) for value, kind in zip(self.__dict__.values(), expected))):
            raise ValueError('every fine grid, stage and physical recipe must be explicit')
        stage = self.outlet_stage_m
        if stage.ndim != 1 or stage.dtype.kind not in 'fiu' or (not _i102_np.isfinite(stage).all()):
            raise ValueError('outlet stages must be a finite numeric vector')
        object.__setattr__(self, 'outlet_stage_m', _freeze(stage.astype(_i102_np.float64)))

def _encode(value, arrays):
    from terrain_pipeline.artifacts.contracts import array_hash as _i102_array_hash
    if isinstance(value, _i102_np.ndarray):
        key = f'array_{len(arrays):05d}'
        arrays[key] = value
        return {'$array': key, 'sha256': _i102_array_hash(value), 'shape': list(value.shape), 'dtype': value.dtype.str}
    if isinstance(value, _i102_Mapping):
        return {key: _encode(child, arrays) for key, child in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_encode(child, arrays) for child in value]
    if isinstance(value, _i102_np.generic):
        return value.item()
    return value

def _hash(value):
    from terrain_pipeline.artifacts.contracts import digest as _i102_digest
    return _i102_digest(_encode(value, {}))

def _bytes(value):
    arrays = {}
    tree = _encode(value, arrays)
    return sum((array.nbytes for array in arrays.values())) + len(_i102_json.dumps(tree, ensure_ascii=False).encode('utf8'))

def _seal(result):
    result['identity_sha256'] = _hash(result)
    return _freeze(result)

def _input_mesh(inputs):
    from terrain_pipeline.drainage import grid_mesh as _i102_grid_mesh
    return _i102_grid_mesh(inputs['height_m'].shape, x0_m=inputs['origin_x_m'], z0_m=inputs['origin_z_m'], dx_m=inputs['spacing_x_m'], dz_m=inputs['spacing_z_m'])

def _archived_raster_mesh(shape):
    """Read-only v1 topology oracle; never used to generate a new domain."""
    from types import SimpleNamespace
    rows, cols = shape
    indptr, indices = ([0], [])
    for row in range(rows):
        for col in range(cols):
            indices.extend((rr * cols + cc for rr in range(max(0, row - 1), min(rows, row + 2)) for cc in range(max(0, col - 1), min(cols, col + 2)) if (rr, cc) != (row, col)))
            indptr.append(len(indices))
    return SimpleNamespace(indptr=_i102_np.asarray(indptr), indices=_i102_np.asarray(indices))

def _neighbors(cell, shape, allowed, mesh):
    from terrain_pipeline.drainage import segments_clear as _i102_segments_clear
    adjacent = mesh.indices[mesh.indptr[cell]:mesh.indptr[cell + 1]]
    clear = _i102_segments_clear(_i102_np.full(adjacent.size, cell, _i102_np.int64), adjacent, allowed)
    return adjacent[clear]

def _edge_ok(donor, target, shape, allowed, mesh):
    return target in _neighbors(donor, shape, allowed, mesh)

def _ocean_connected(ocean, valid, protected, mesh):
    allowed = ocean & valid & ~protected
    connected = _i102_np.zeros(ocean.shape, bool)
    boundary = _i102_np.zeros(ocean.shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    queue = _i102_deque((int(cell) for cell in _i102_np.flatnonzero(allowed & boundary)))
    connected.flat[list(queue)] = True
    while queue:
        cell = queue.popleft()
        for target in _neighbors(cell, ocean.shape, allowed, mesh):
            if not connected.flat[target]:
                connected.flat[target] = True
                queue.append(target)
    return connected

def _normalize_inputs(height_m, valid_mask, domain_labels, land_mask, ocean_mask, protected_mask, coastal_outlets, runoff_m_s, external_q_m3_s, spacing_x_m, spacing_z_m, origin_x_m, origin_z_m, sea_level_elevation_m, vertical_datum, source_identity, source_kind, boundary_complete, scope, outlet_evidence, resources):
    height = _i102_np.asarray(height_m)
    if height.ndim != 2 or min(height.shape) < 2 or height.size > MAX_INPUT_CELLS or (height.dtype.kind not in 'fiu'):
        raise ValueError('invalid or excessive source grid')
    masks = [_i102_np.asarray(value) for value in (valid_mask, land_mask, ocean_mask, protected_mask)]
    if any((mask.dtype != bool or mask.shape != height.shape for mask in masks)):
        raise ValueError('matching explicit boolean valid/land/ocean/protected masks required')
    valid, land, ocean, protected = masks
    if _i102_np.any(ocean & (~valid | (height > sea_level_elevation_m))):
        raise ValueError('declared ocean must be finite-valid and H0 at or below explicit sea level')
    labels = _i102_np.asarray(domain_labels)
    if labels.shape != height.shape or labels.dtype.kind not in 'iu' or _i102_np.any(labels < -1) or _i102_np.any(land & ocean) or _i102_np.any((labels > 0) & ~land) or _i102_np.any((labels == 0) != ocean) or _i102_np.any(land & (labels == 0)) or _i102_np.any(valid & ~_i102_np.isfinite(height)):
        raise ValueError('inconsistent land/ocean/unknown labels or finite-valid declaration')
    for name, value in (('spacing_x_m', spacing_x_m), ('spacing_z_m', spacing_z_m), ('origin_x_m', origin_x_m), ('origin_z_m', origin_z_m), ('sea_level_elevation_m', sea_level_elevation_m)):
        if isinstance(value, bool) or not _i102_math.isfinite(value) or (name.startswith('spacing') and value <= 0):
            raise ValueError('invalid metric coordinate or sea level')
    if not isinstance(resources, SurfaceDomainResources) or type(boundary_complete) is not bool or scope not in ('complete_grid', 'subdomain') or (outlet_evidence not in ('engineering_declared', 'independently_observed')) or any((not isinstance(value, str) or not value.strip() for value in (vertical_datum, source_identity, source_kind))):
        raise ValueError('source identity/datum/kind, scope, boundary and outlet evidence required')
    rate = _i102_np.broadcast_to(_i102_np.asarray(runoff_m_s), height.shape)
    external = _i102_np.asarray(external_q_m3_s)
    if any((value.shape != height.shape or value.dtype.kind not in 'fiu' or (not _i102_np.isfinite(value).all()) or _i102_np.any(value < 0) for value in (rate, external))):
        raise ValueError('runoff and external Q must be finite nonnegative matching fields')
    if _i102_np.any((rate != 0) & ~land) or _i102_np.any((external != 0) & ~land):
        raise ValueError('water inputs may only be assigned to declared land')
    exits = []
    if not isinstance(coastal_outlets, (tuple, list)):
        raise ValueError('explicit coastal outlet triples required')
    for entry in coastal_outlets:
        if not isinstance(entry, (tuple, list)) or len(entry) != 3 or any((type(value) is not int for value in entry)) or (entry[0] <= 0) or any((not 0 <= value < height.size for value in entry[1:])):
            raise ValueError('coastal outlet must be (domain id, flat land node, flat ocean node)')
        exits.append(list(entry))
    if len({entry[1] for entry in exits}) != len(exits):
        raise ValueError('duplicate coastal land outlet')
    return {'height_m': height.astype(_i102_np.float64), 'valid_mask': valid, 'domain_labels': labels.astype(_i102_np.int64), 'land_mask': land, 'ocean_mask': ocean, 'protected_mask': protected, 'coastal_outlets': sorted(exits), 'runoff_m_s': rate.astype(_i102_np.float64), 'external_q_m3_s': external.astype(_i102_np.float64), 'spacing_x_m': float(spacing_x_m), 'spacing_z_m': float(spacing_z_m), 'origin_x_m': float(origin_x_m), 'origin_z_m': float(origin_z_m), 'sea_level_elevation_m': float(sea_level_elevation_m), 'vertical_datum': vertical_datum, 'source_identity': source_identity, 'source_kind': source_kind, 'boundary_complete': boundary_complete, 'scope': scope, 'outlet_evidence': outlet_evidence, 'resources': _i102_asdict(resources)}

def _declaration_failures(inputs):
    labels, land = (inputs['domain_labels'], inputs['land_mask'])
    failures = []
    if _i102_np.any(labels == -1):
        failures.append('unknown_or_unassigned_cells')
    if _i102_np.any(land & ((labels <= 0) | ~inputs['valid_mask'])):
        failures.append('land_not_uniquely_valid_assigned')
    if _i102_np.any(~inputs['valid_mask']):
        failures.append('invalid_source_cells')
    if _i102_np.any(land & inputs['protected_mask']):
        failures.append('protected_land_cannot_be_routed_without_losing_local_water')
    return failures

def _coast_gate(inputs, mesh=None):
    if not inputs['coastal_outlets']:
        return _i102_np.zeros(inputs['height_m'].shape, bool)
    mesh = _input_mesh(inputs) if mesh is None else mesh
    connected = _ocean_connected(inputs['ocean_mask'], inputs['valid_mask'], inputs['protected_mask'], mesh)
    labels, shape = (inputs['domain_labels'], inputs['height_m'].shape)
    for domain_id, land_cell, ocean_cell in inputs['coastal_outlets']:
        allowed = ((labels == domain_id) | connected) & inputs['valid_mask'] & ~inputs['protected_mask']
        if labels.flat[land_cell] != domain_id or not connected.flat[ocean_cell] or (not allowed.flat[land_cell]) or (not _edge_ok(land_cell, ocean_cell, shape, allowed, mesh)):
            raise ValueError('false coast: land exit needs boundary-connected declared ocean and legal orthogonal supports')
    return connected

def _flood(height, allowed, exits, cancel, mesh):
    receiver = _i102_np.full(height.size, -2, _i102_np.int64)
    working = _i102_np.full(height.size, _i102_np.nan)
    queue = []
    for cell in sorted(exits):
        receiver[cell] = -1
        working[cell] = height.flat[cell]
        _i102_heapq.heappush(queue, (working[cell], cell))
    order = []
    while queue:
        if cancel is not None and cancel():
            return None
        level, cell = _i102_heapq.heappop(queue)
        order.append(cell)
        for donor in _neighbors(cell, height.shape, allowed, mesh):
            if receiver[donor] != -2:
                continue
            receiver[donor] = cell
            working[donor] = max(float(height.flat[donor]), level)
            _i102_heapq.heappush(queue, (working[donor], donor))
    if len(order) != int(allowed.sum()):
        raise ValueError('land component has no supported route to explicit coast exit')
    return (receiver, working, order)

def plan_surface_domains(height_m, valid_mask, domain_labels, land_mask, ocean_mask, protected_mask, coastal_outlets, runoff_m_s, external_q_m3_s, spacing_x_m, spacing_z_m, origin_x_m, origin_z_m, sea_level_elevation_m, vertical_datum, source_identity, source_kind, boundary_complete, scope, outlet_evidence, resources, *, cancel=None):
    """Route all declared land; never present planning as fine terrain completion."""
    if not isinstance(resources, SurfaceDomainResources):
        raise ValueError('explicit shared resources required')
    count = _i102_np.asarray(height_m).size
    if count * 200 + 32768 > resources.max_retained_bytes:
        raise ValueError('retained input evidence resource preflight')
    inputs = _normalize_inputs(height_m, valid_mask, domain_labels, land_mask, ocean_mask, protected_mask, coastal_outlets, runoff_m_s, external_q_m3_s, spacing_x_m, spacing_z_m, origin_x_m, origin_z_m, sea_level_elevation_m, vertical_datum, source_identity, source_kind, boundary_complete, scope, outlet_evidence, resources)
    labels, height = (inputs['domain_labels'], inputs['height_m'])
    mesh = _input_mesh(inputs)
    domain_ids = sorted((int(value) for value in _i102_np.unique(labels[labels > 0])))
    failures = _declaration_failures(inputs)
    _coast_gate(inputs)
    if height.size > resources.max_coarse_cells or len(domain_ids) > resources.max_domains:
        failures.append('coarse_resource_limit')
    local = inputs['runoff_m_s'] * spacing_x_m * spacing_z_m + inputs['external_q_m3_s']
    if not _i102_np.isfinite(local).all():
        raise ValueError('local runoff discharge overflows')
    receiver = _i102_np.full(height.size, -2, _i102_np.int64)
    working = _i102_np.full(height.shape, _i102_np.nan)
    discharge = _i102_np.zeros(height.shape)
    orders, domains = ([], [])
    cancelled = False
    for domain_id in domain_ids:
        allowed = (labels == domain_id) & inputs['valid_mask'] & ~inputs['protected_mask']
        rows, columns = _i102_np.nonzero(labels == domain_id)
        bounds = [int(rows.min()), int(rows.max()) + 1, int(columns.min()), int(columns.max()) + 1]
        for axis in (0, 2):
            if bounds[axis + 1] - bounds[axis] < 2:
                bounds[axis] = max(0, bounds[axis] - 1)
                bounds[axis + 1] = min(height.shape[axis // 2], bounds[axis] + 2)
        record = {'domain_id': domain_id, 'bounds_zx': bounds, 'status': 'pending', 'reason': None}
        domains.append(record)
        if failures or cancelled:
            continue
        if cancel is not None and cancel():
            cancelled = True
            continue
        exits = [entry[1] for entry in inputs['coastal_outlets'] if entry[0] == domain_id]
        try:
            if not exits:
                raise ValueError('domain has no explicit coast exit')
            routed = _flood(height, allowed, exits, cancel, mesh)
            if routed is None:
                cancelled = True
                continue
            routed_receiver, routed_working, order = routed
            receiver[allowed.ravel()] = routed_receiver[allowed.ravel()]
            working[allowed] = routed_working.reshape(height.shape)[allowed]
            discharge[allowed] = local[allowed]
            for donor in reversed(order):
                target = receiver[donor]
                if target >= 0:
                    discharge.flat[target] += discharge.flat[donor]
            if not _i102_np.isfinite(discharge).all():
                raise ValueError('accumulated discharge overflows')
            orders.extend(order)
            record['status'] = 'routed'
        except ValueError as error:
            record.update(status='diagnostic', reason=str(error))
    if cancelled:
        failures.append('cancelled')
    if any((domain['status'] == 'diagnostic' for domain in domains)):
        failures.append('unrouted_domain')
    transfers = [{'domain_id': domain_id, 'land_cell': land_cell, 'ocean_cell': ocean_cell, 'discharge_m3_s': float(discharge.flat[land_cell])} for domain_id, land_cell, ocean_cell in inputs['coastal_outlets']]
    result = {'algorithm_version': SURFACE_DOMAIN_PREPARE_VERSION, 'kind': 'plan', 'status': 'diagnostic' if failures else 'candidate', 'inputs': inputs, 'arrays': {'receiver': receiver, 'order': _i102_np.array(orders, _i102_np.int64), 'working_fill_m': working, 'local_discharge_m3_s': local, 'discharge_m3_s': discharge}, 'domains': domains, 'failures': failures, 'coastal_transfers': transfers, 'unrouted_local_discharge_m3_s': float(local.ravel()[receiver == -2].sum())}
    if _bytes(result) > resources.max_retained_bytes:
        raise ValueError('retained input evidence exceeds limit')
    return _seal(result)

def _domain_arrays(candidate, record):
    inputs, arrays = (candidate['inputs'], candidate['arrays'])
    first_row, last_row, first_column, last_column = record['bounds_zx']
    window = _i102_np.s_[first_row:last_row, first_column:last_column]
    shape = inputs['height_m'][window].shape
    global_cells = _i102_np.arange(inputs['height_m'].size).reshape(inputs['height_m'].shape)[window].ravel()
    local_indices = {int(cell): index for index, cell in enumerate(global_cells)}
    receiver = _i102_np.full(len(global_cells), -1, _i102_np.int64)
    for index, cell in enumerate(global_cells):
        target = int(arrays['receiver'][cell])
        if inputs['domain_labels'].flat[cell] == record['domain_id'] and target >= 0:
            receiver[index] = local_indices[target]
    domain = inputs['domain_labels'][window] == record['domain_id']
    order = [index for index in range(len(receiver)) if not domain.flat[index]]
    order.extend((local_indices[int(cell)] for cell in arrays['order'] if int(cell) in local_indices and domain.flat[local_indices[int(cell)]]))
    discharge = _i102_np.where(domain, arrays['discharge_m3_s'][window], 0.0)
    return (window, domain, receiver, _i102_np.array(order, _i102_np.int64), (receiver == -1).reshape(shape), discharge)

def _fine_binding(candidate, record, fine):
    inputs = candidate['inputs']
    first_row, last_row, first_column, last_column = record['bounds_zx']
    axes = []
    for axis, first, last, size in (('z', first_row, last_row, fine.shape_zx[0]), ('x', first_column, last_column, fine.shape_zx[1])):
        origin = inputs[f'origin_{axis}_m'] + first * inputs[f'spacing_{axis}_m']
        expected_last = origin + (last - first - 1) * inputs[f'spacing_{axis}_m']
        actual_last = getattr(fine, f'origin_{axis}_m') + (size - 1) * getattr(fine, f'spacing_{axis}_m')
        ratio = inputs[f'spacing_{axis}_m'] / getattr(fine, f'spacing_{axis}_m')
        if not _i102_math.isclose(origin, getattr(fine, f'origin_{axis}_m'), abs_tol=1e-08, rel_tol=0) or not _i102_math.isclose(expected_last, actual_last, abs_tol=1e-08, rel_tol=0) or (not _i102_math.isclose(ratio, round(ratio), abs_tol=1e-08, rel_tol=0)) or (ratio < 1):
            raise ValueError('fine grid must exactly cover domain bounding grid at integer refinement')
        axes.append(first + _i102_np.floor(_i102_np.arange(size) / ratio + 0.5).astype(_i102_np.int64))
    sample = _i102_np.ix_(*axes)
    expected_domain = inputs['domain_labels'][sample] == record['domain_id']
    protected = inputs['protected_mask'][sample]
    legal = _i102_np.zeros(inputs['height_m'].shape, bool)
    for domain_id, land_cell, _ in inputs['coastal_outlets']:
        if domain_id == record['domain_id']:
            legal.flat[land_cell] = True
    return (expected_domain, protected, legal[sample] & expected_domain)

def bind_surface_domain_fine(candidate, domain_id, spacing_x_m, spacing_z_m):
    """Derive bound fine masks, without selecting physical recipes or preparing terrain."""
    record = next((item for item in candidate['domains'] if item['domain_id'] == domain_id), None)
    if record is None or record['status'] != 'routed':
        raise ValueError('fine binding requires a fully routed domain')
    inputs = candidate['inputs']
    first_row, last_row, first_column, last_column = record['bounds_zx']
    sizes = []
    for length, coarse, fine_spacing in ((last_row - first_row, inputs['spacing_z_m'], spacing_z_m), (last_column - first_column, inputs['spacing_x_m'], spacing_x_m)):
        if isinstance(fine_spacing, bool) or not _i102_math.isfinite(fine_spacing) or fine_spacing <= 0:
            raise ValueError('invalid explicit fine spacing')
        ratio = coarse / fine_spacing
        if ratio < 1 or not _i102_math.isclose(ratio, round(ratio), abs_tol=1e-08):
            raise ValueError('integer refinement required')
        sizes.append((length - 1) * round(ratio) + 1)
    shape = tuple(sizes)
    if _i102_math.prod(shape) > 1000000:
        raise ValueError('fine shape exceeds existing fine grid bound')
    empty = _i102_np.zeros(shape, bool)
    stub = FineGrid(inputs['origin_x_m'] + first_column * inputs['spacing_x_m'], inputs['origin_z_m'] + first_row * inputs['spacing_z_m'], spacing_x_m, spacing_z_m, shape, empty, empty, empty)
    domain, protected, legal = _fine_binding(candidate, record, stub)
    return _i102_replace(stub, domain_mask=domain, protected_mask=protected, legal_outlet_mask=legal & ~protected)

def _configuration_record(config):
    return {name: {key: _plain(value) for key, value in config.fine.__dict__.items()} if name == 'fine' else config.outlet_stage_m if name == 'outlet_stage_m' else _i102_asdict(getattr(config, name)) for name in config.__dict__}

def _check_fine(candidate, record, fine):
    domain, protected, legal = _fine_binding(candidate, record, fine)
    if not _i102_np.array_equal(domain, fine.domain_mask) or not _i102_np.array_equal(protected, fine.protected_mask) or (not _i102_np.array_equal(legal & ~fine.protected_mask, fine.legal_outlet_mask)):
        raise ValueError('fine/domain/protection/coast masks disagree with complete coarse declaration')

def _config_from_record(record):
    from terrain_pipeline.surface_hydraulics import InundationRecipe as _x60_InundationRecipe
    from terrain_pipeline.surface_hydraulics import RerouteRecipe as _x61_RerouteRecipe
    from terrain_pipeline.surface_hydraulics import StageRecipe as _x62_StageRecipe
    from terrain_pipeline.channel_geometry import SectionRecipe as _x63_SectionRecipe
    from terrain_pipeline.channel_geometry import ChannelRecipe as _x64_ChannelRecipe
    from terrain_pipeline.channel_geometry import NetworkValleyRecipe as _x66_NetworkValleyRecipe
    from terrain_pipeline.channel_geometry import ValleyGeometryRecipe as _x67_ValleyGeometryRecipe
    kinds = {'channel_recipe': _x64_ChannelRecipe, 'section_recipe': _x63_SectionRecipe, 'stage_recipe': _x62_StageRecipe, 'inundation_recipe': _x60_InundationRecipe, 'budget': SurfaceNetworkBudget, 'network_recipe': _x66_NetworkValleyRecipe, 'valley_recipe': _x67_ValleyGeometryRecipe, 'reroute_recipe': _x61_RerouteRecipe, 'recovery_recipe': RecoveryRecipe}
    values = {name: kind(**record[name]) for name, kind in kinds.items()}
    fine = _plain(record['fine'])
    fine['shape_zx'] = tuple(fine['shape_zx'])
    return DomainFineConfiguration(FineGrid(**fine), record['outlet_stage_m'], **values)

def _prepared_gate(candidate, record, config, recovery, *, saved_support=None):
    from terrain_pipeline.drainage import grid_mesh as _i102_grid_mesh
    _check_fine(candidate, record, config.fine)
    arrays = _payload(recovery)
    legacy = candidate['algorithm_version'] == LEGACY_VERSION
    if legacy and saved_support is None:
        pass  # Same-module import resolves directly to its global definition.
        saved_support = _h0_support(recovery)
    if saved_support is None:
        _proof_gate(recovery, arrays)
    else:
        pass  # Same-module import resolves directly to its global definition.
        _static_proof(recovery, saved_support)
    window, domain, receiver, order, outlets, discharge = _domain_arrays(candidate, record)
    original = recovery['inputs']['plan']['arrays']
    if any((not _i102_np.array_equal(original[name], expected) for name, expected in (('source_height_m', candidate['inputs']['height_m'][window]), ('receiver', receiver), ('order', order), ('outlet_mask', outlets), ('discharge_m3_s', discharge)))):
        raise ValueError('fine recovery source differs from complete coarse route/Q/H0')
    fine_inputs = recovery['inputs']
    config_record = _configuration_record(config)
    for name in config_record:
        if name not in ('channel_recipe', 'recovery_recipe') and _hash(config_record[name]) != _hash(fine_inputs[name]):
            raise ValueError('fine recovery changed original configuration or physical budget')
    params = recovery['inputs']['plan']['identity']['parameters']
    if any((params[name] != value for name, value in _i102_asdict(config.channel_recipe).items())):
        raise ValueError('channel recipe changed')
    inputs = candidate['inputs']
    first_row, _, first_column, _ = record['bounds_zx']
    expected_params = {'spacing_x_m': inputs['spacing_x_m'], 'spacing_z_m': inputs['spacing_z_m'], 'origin_x_m': inputs['origin_x_m'] + first_column * inputs['spacing_x_m'], 'origin_z_m': inputs['origin_z_m'] + first_row * inputs['spacing_z_m'], 'sea_level_elevation_m': inputs['sea_level_elevation_m'], 'source_identity': candidate['identity_sha256'] + ':domain:' + str(record['domain_id'])}
    if any((params[name] != value for name, value in expected_params.items())):
        raise ValueError('fine recovery source coordinates, sea level or source identity changed')
    final = recovery['final_plan']['arrays']
    allowed = domain & ~fine_inputs['coarse_protected']
    mesh = _i102_grid_mesh(domain.shape, x0_m=params['origin_x_m'], z0_m=params['origin_z_m'], dx_m=params['spacing_x_m'], dz_m=params['spacing_z_m'], world_seed=params.get('world_seed', 20261020))
    if legacy:
        mesh = _archived_raster_mesh(domain.shape)
    for cell in _i102_np.flatnonzero(domain):
        target = int(final['receiver'][cell])
        if target < 0 and receiver[cell] != -1 or (target >= 0 and (not _edge_ok(int(cell), target, domain.shape, allowed, mesh))):
            raise ValueError('recovered route crosses domain/protection corner or changes legal coast terminals')

def evaluate_surface_domains(candidate, configurations, *, cancel=None):
    """Explicit channel planning and bounded recovery, after joint resource preflight."""
    from terrain_pipeline.channel_geometry import plan_channel as _x65_plan_channel
    validate_surface_domains(candidate, allow_unprepared=True)
    if candidate['algorithm_version'] != SURFACE_DOMAIN_PREPARE_VERSION:
        raise ValueError('archived domain topology is read-only')
    if candidate['kind'] != 'plan':
        raise ValueError('explicit preparation requires a domain plan')
    resources = SurfaceDomainResources(**candidate['inputs']['resources'])
    ids = [record['domain_id'] for record in candidate['domains']]
    if not isinstance(configurations, _i102_Mapping) or set(configurations) != set(ids) or any((type(key) is not int or not isinstance(value, DomainFineConfiguration) for key, value in configurations.items())):
        raise ValueError('every land domain needs explicit fine configuration; no omitted domains')
    configs = {str(key): _configuration_record(value) for key, value in sorted(configurations.items())}
    entries = [{'domain_id': domain_id, 'status': 'pending', 'reason': None, 'recovery': None, 'charged_coarse_cells': 0, 'charged_fine_cells': 0} for domain_id in ids]
    usage = {'coarse_work_cells': 0, 'fine_cells': 0, 'fine_work_cells': 0, 'attempts': 0}
    failures = list(candidate['failures'])
    result = {'algorithm_version': SURFACE_DOMAIN_PREPARE_VERSION, 'kind': 'evaluation', 'status': 'diagnostic', 'candidate': candidate, 'configurations': configs, 'domains': entries, 'usage': usage, 'failures': failures}
    if failures:
        if _bytes(result) > resources.max_retained_bytes:
            raise ValueError('retained diagnostic evidence resource limit')
        return _seal(result)
    sizes = []
    try:
        for record in candidate['domains']:
            config = configurations[record['domain_id']]
            _check_fine(candidate, record, config.fine)
            bounds = record['bounds_zx']
            coarse_count = (bounds[1] - bounds[0]) * (bounds[3] - bounds[2])
            fine_count = _i102_math.prod(config.fine.shape_zx)
            if coarse_count > config.recovery_recipe.max_coarse_cells or fine_count > config.recovery_recipe.max_fine_cells or fine_count > config.recovery_recipe.max_total_fine_cells or (coarse_count * 1024 + fine_count * 512 > config.recovery_recipe.max_working_bytes):
                raise ValueError('original per-domain recovery resource preflight')
            sizes.append((coarse_count, fine_count))
        total_coarse, total_fine = map(sum, zip(*sizes)) if sizes else (0, 0)
        if total_coarse > resources.max_coarse_work_cells or total_fine > resources.max_fine_cells or total_fine > resources.max_fine_work_cells or (len(ids) > resources.max_attempts) or (_bytes(result) * 2 + total_coarse * 2048 + total_fine * 1024 > resources.max_retained_bytes):
            raise ValueError('shared resource preflight: coarse/fine/attempt/retained limit')
    except ValueError as error:
        failures.append(str(error))
        if _bytes(result) > resources.max_retained_bytes:
            raise ValueError('retained resource preflight diagnostic too large')
        return _seal(result)
    for index, (record, entry) in enumerate(zip(candidate['domains'], entries)):
        if cancel is not None and cancel():
            failures.append('cancelled')
            break
        config = configurations[record['domain_id']]
        coarse_count, fine_count = sizes[index]
        reserved_attempts = len(ids) - index - 1
        reserved_fine = sum((size[1] for size in sizes[index + 1:]))
        attempts_left = resources.max_attempts - usage['attempts'] - reserved_attempts
        fine_left = resources.max_fine_work_cells - usage['fine_work_cells'] - reserved_fine
        try:
            if attempts_left <= 0 or fine_left < fine_count:
                raise ValueError('shared recovery work exhausted')
            effective = _i102_replace(config.recovery_recipe, max_attempts=min(config.recovery_recipe.max_attempts, attempts_left), max_total_fine_cells=min(config.recovery_recipe.max_total_fine_cells, fine_left))
            entry['charged_coarse_cells'], entry['charged_fine_cells'] = (coarse_count, fine_count)
            usage['coarse_work_cells'] += coarse_count
            usage['fine_cells'] += fine_count
            window, domain, receiver, order, outlets, discharge = _domain_arrays(candidate, record)
            inputs = candidate['inputs']
            first_row, _, first_column, _ = record['bounds_zx']
            plan = _x65_plan_channel(inputs['height_m'][window], receiver, order, outlets, discharge, inputs['spacing_x_m'], inputs['spacing_z_m'], inputs['origin_x_m'] + first_column * inputs['spacing_x_m'], inputs['origin_z_m'] + first_row * inputs['spacing_z_m'], inputs['sea_level_elevation_m'], candidate['identity_sha256'] + ':domain:' + str(record['domain_id']), config.channel_recipe)
            recovery = recover_surface_network(plan, domain, inputs['protected_mask'][window], config.fine, config.outlet_stage_m, config.section_recipe, config.stage_recipe, config.inundation_recipe, config.budget, config.network_recipe, config.valley_recipe, config.reroute_recipe, effective)
            usage['attempts'] += len(recovery['attempts'])
            usage['fine_work_cells'] += recovery['summary']['total_fine_cells_evaluated']
            entry['recovery'] = recovery
            if recovery['accepted']:
                _prepared_gate(candidate, record, config, recovery)
                entry['status'] = 'prepared'
            else:
                entry.update(status='diagnostic', reason='actual_fine_recovery_' + recovery['status'])
        except ValueError as error:
            entry.update(status='diagnostic', reason=str(error))
        if entry['status'] != 'prepared':
            failures.append('domain_' + str(record['domain_id']) + '_not_prepared')
    if not failures and (not candidate['inputs']['boundary_complete'] or candidate['inputs']['scope'] != 'complete_grid'):
        failures.append('unverified_or_subdomain_boundary_not_system_prepared')
        result['status'] = 'candidate'
    elif not failures and entries:
        result['status'] = 'prepared'
    if _bytes(result) > resources.max_retained_bytes:
        raise ValueError('retained result resource limit')
    return _seal(result)

def _validate_plan(result):
    stored = result['inputs']
    mesh = _archived_raster_mesh(stored['height_m'].shape) if result['algorithm_version'] == LEGACY_VERSION else _input_mesh(stored)
    resources = SurfaceDomainResources(**stored['resources'])
    normalized = _normalize_inputs(**{name: value for name, value in _plain(stored).items() if name != 'resources'}, resources=resources)
    if _hash(normalized) != _hash(stored):
        raise ValueError('noncanonical domain inputs')
    _coast_gate(stored, mesh)
    failures = _declaration_failures(stored)
    if any((reason not in result['failures'] for reason in failures)):
        raise ValueError('complete-land declaration failure concealed')
    labels, arrays = (stored['domain_labels'], result['arrays'])
    expected_ids = sorted((int(value) for value in _i102_np.unique(labels[labels > 0])))
    if [item['domain_id'] for item in result['domains']] != expected_ids:
        raise ValueError('missing or duplicate land domain')
    receiver, order = (arrays['receiver'], arrays['order'])
    if receiver.shape != (labels.size,) or receiver.dtype != _i102_np.int64 or order.ndim != 1 or (order.dtype != _i102_np.int64) or (set(arrays) != {'receiver', 'order', 'working_fill_m', 'local_discharge_m3_s', 'discharge_m3_s'}):
        raise ValueError('invalid masked route arrays')
    for name in ('working_fill_m', 'local_discharge_m3_s', 'discharge_m3_s'):
        if arrays[name].shape != labels.shape or arrays[name].dtype != _i102_np.float64:
            raise ValueError('invalid coarse field shape/dtype')
    local = stored['runoff_m_s'] * stored['spacing_x_m'] * stored['spacing_z_m'] + stored['external_q_m3_s']
    if not _i102_np.array_equal(local, arrays['local_discharge_m3_s']):
        raise ValueError('local runoff area or external Q changed')
    routed = _i102_np.zeros(labels.shape, bool)
    allowed_by_id = {}
    for record in result['domains']:
        rows, columns = _i102_np.nonzero(labels == record['domain_id'])
        bounds = [int(rows.min()), int(rows.max()) + 1, int(columns.min()), int(columns.max()) + 1]
        for axis in (0, 2):
            if bounds[axis + 1] - bounds[axis] < 2:
                bounds[axis] = max(0, bounds[axis] - 1)
                bounds[axis + 1] = min(labels.shape[axis // 2], bounds[axis] + 2)
        if list(record['bounds_zx']) != bounds:
            raise ValueError('domain bounding grid changed')
        if record['status'] == 'routed':
            domain = labels == record['domain_id']
            routed |= domain
            allowed_by_id[record['domain_id']] = domain & stored['valid_mask'] & ~stored['protected_mask']
        elif record['status'] not in ('pending', 'diagnostic'):
            raise ValueError('invalid route domain state')
    cells = _i102_np.flatnonzero(routed)
    if not _i102_np.array_equal(_i102_np.sort(order), cells) or _i102_np.any(receiver[~routed.ravel()] != -2) or _i102_np.any(~_i102_np.isnan(arrays['working_fill_m'][~routed])) or _i102_np.any(arrays['discharge_m3_s'][~routed] != 0):
        raise ValueError('masked coverage or dormant cells disagree')
    rank = _i102_np.full(labels.size, -1, _i102_np.int64)
    rank[order] = _i102_np.arange(len(order))
    working = arrays['working_fill_m'].ravel()
    discharge = arrays['discharge_m3_s'].ravel()
    accumulated = _i102_np.where(routed, local, 0.0).ravel()
    legal = {entry[1] for entry in stored['coastal_outlets']}
    for cell in order:
        target = int(receiver[cell])
        allowed = allowed_by_id[int(labels.flat[cell])]
        if not allowed.flat[cell] or not _i102_math.isfinite(working[cell]):
            raise ValueError('invalid routed land')
        if target == -1:
            if int(cell) not in legal or working[cell] != stored['height_m'].flat[cell]:
                raise ValueError('false coast terminal')
        elif target < 0 or target >= labels.size or rank[target] < 0 or (rank[target] >= rank[cell]) or (not _edge_ok(int(cell), target, labels.shape, allowed, mesh)) or (working[cell] != max(stored['height_m'].flat[cell], working[target])):
            raise ValueError('cross-domain/corner/cyclic route or separate working fill mismatch')
        if int(cell) not in legal:
            for neighbor in _neighbors(int(cell), labels.shape, allowed, mesh):
                if working[cell] > max(stored['height_m'].flat[cell], working[neighbor]):
                    raise ValueError('working fill is not a minimal supported flood')
    for cell in reversed(order):
        target = int(receiver[cell])
        if target >= 0:
            accumulated[target] += accumulated[cell]
    if not _i102_np.isfinite(discharge).all() or not _i102_np.array_equal(discharge, accumulated):
        raise ValueError('domain discharge is not conservative')
    transfers = [{'domain_id': domain_id, 'land_cell': land_cell, 'ocean_cell': ocean_cell, 'discharge_m3_s': float(discharge[land_cell])} for domain_id, land_cell, ocean_cell in stored['coastal_outlets']]
    if _hash(transfers) != _hash(result['coastal_transfers']) or result['unrouted_local_discharge_m3_s'] != float(local.ravel()[receiver == -2].sum()):
        raise ValueError('land-ocean transfer or unprocessed source ledger changed')
    complete = _i102_np.array_equal(routed, stored['land_mask'])
    if result['status'] == 'candidate' and (not complete or result['failures'] or labels.size > resources.max_coarse_cells or (len(expected_ids) > resources.max_domains)):
        raise ValueError('incomplete or resource-limited routing cannot be successful candidate')
    if result['status'] not in ('candidate', 'diagnostic') or (result['status'] == 'diagnostic' and (not result['failures'])):
        raise ValueError('invalid plan state')

def validate_surface_domains(result, *, allow_unprepared=False, saved_support=None):
    """Static topology/geometry/budget gates; never reroute, plan or recover."""
    try:
        record = {key: value for key, value in result.items() if key != 'identity_sha256'}
        if result['algorithm_version'] not in (SURFACE_DOMAIN_PREPARE_VERSION, LEGACY_VERSION) or _hash(record) != result['identity_sha256']:
            raise ValueError('domain bundle identity mismatch')
        if result['kind'] == 'plan':
            if saved_support is not None:
                raise ValueError('saved support is only valid for domain evaluations')
            _validate_plan(result)
            resources = result['inputs']['resources']
        elif result['kind'] == 'evaluation':
            candidate = result['candidate']
            validate_surface_domains(candidate, allow_unprepared=True)
            ids = [item['domain_id'] for item in candidate['domains']]
            if saved_support is not None:
                expected_proofs = {entry['recovery']['identity_sha256'] for entry in result['domains'] if entry['status'] == 'prepared' and entry['recovery'] is not None}
                if not hasattr(saved_support, 'keys') or set(saved_support) != expected_proofs:
                    raise ValueError('saved support must bind every prepared recovery exactly')
            if [item['domain_id'] for item in result['domains']] != ids or set(result['configurations']) != {str(value) for value in ids}:
                raise ValueError('fine preparation omits declared land domain')
            usage = {'coarse_work_cells': 0, 'fine_cells': 0, 'fine_work_cells': 0, 'attempts': 0}
            for index, (domain, entry) in enumerate(zip(candidate['domains'], result['domains'])):
                config = _config_from_record(result['configurations'][str(domain['domain_id'])])
                recovery = entry['recovery']
                bounds = domain['bounds_zx']
                coarse_count = (bounds[1] - bounds[0]) * (bounds[3] - bounds[2])
                fine_count = _i102_math.prod(config.fine.shape_zx)
                charged = (entry['charged_coarse_cells'], entry['charged_fine_cells'])
                if charged not in ((0, 0), (coarse_count, fine_count)) or (recovery is not None and charged != (coarse_count, fine_count)) or (entry['status'] == 'pending' and charged != (0, 0)):
                    raise ValueError('charged coarse/fine sizes differ from actual domain/fine grids')
                if recovery is not None:
                    reserved_attempts = len(ids) - index - 1
                    reserved_fine = sum((_i102_math.prod(result['configurations'][str(value)]['fine']['shape_zx']) for value in ids[index + 1:]))
                    resources = candidate['inputs']['resources']
                    effective = _i102_replace(config.recovery_recipe, max_attempts=min(config.recovery_recipe.max_attempts, resources['max_attempts'] - usage['attempts'] - reserved_attempts), max_total_fine_cells=min(config.recovery_recipe.max_total_fine_cells, resources['max_fine_work_cells'] - usage['fine_work_cells'] - reserved_fine))
                    if _hash(_i102_asdict(effective)) != _hash(recovery['inputs']['recovery_recipe']) or len(recovery['attempts']) > effective.max_attempts or recovery['summary']['attempt_count'] != len(recovery['attempts']) or (recovery['summary']['total_fine_cells_evaluated'] != len(recovery['attempts']) * fine_count) or (recovery['summary']['total_fine_cells_evaluated'] > effective.max_total_fine_cells):
                        raise ValueError('original/effective recovery attempt or fine work bounds changed')
                usage['coarse_work_cells'] += entry['charged_coarse_cells']
                usage['fine_cells'] += entry['charged_fine_cells']
                if recovery is not None:
                    usage['attempts'] += len(recovery['attempts'])
                    usage['fine_work_cells'] += recovery['summary']['total_fine_cells_evaluated']
                    body = {key: value for key, value in recovery.items() if key != 'identity_sha256'}
                    if _hash(body) != recovery['identity_sha256']:
                        raise ValueError('recovery proof identity mismatch')
                if entry['status'] == 'prepared':
                    if domain['status'] != 'routed' or recovery is None:
                        raise ValueError('prepared domain lacks complete route/recovery')
                    support = None if saved_support is None else saved_support[recovery['identity_sha256']]
                    if saved_support is not None and (not hasattr(support, 'keys') or set(support) != {'indices', 'weights'}):
                        raise ValueError('explicit saved proof indices/weights required')
                    _prepared_gate(candidate, domain, config, _plain(recovery), saved_support=support)
                elif entry['status'] not in ('pending', 'diagnostic'):
                    raise ValueError('invalid fine domain state')
            if _hash(usage) != _hash(result['usage']):
                raise ValueError('shared resource ledger disagrees')
            resources = candidate['inputs']['resources']
            if any((type(value) is not int or value < 0 or value > resources['max_' + name] for name, value in usage.items())):
                raise ValueError('shared work exceeds resource cap')
            prepared = all((item['status'] == 'prepared' for item in result['domains'])) and bool(ids)
            if result['status'] == 'prepared' and (not prepared or result['failures'] or candidate['status'] != 'candidate' or (not candidate['inputs']['boundary_complete']) or (candidate['inputs']['scope'] != 'complete_grid')):
                raise ValueError('prepared publication conceals incomplete domains/boundary')
            if result['status'] not in ('candidate', 'diagnostic', 'prepared'):
                raise ValueError('invalid domain product state')
        else:
            raise ValueError('invalid domain bundle kind')
        if _bytes(record) > resources['max_retained_bytes']:
            raise ValueError('retained bundle exceeds original resource cap')
        if not allow_unprepared and result['status'] != 'prepared':
            raise ValueError('candidate/diagnostic is not a prepared complete-land product')
        return result
    except (KeyError, TypeError, IndexError, OverflowError, AttributeError) as error:
        raise ValueError('invalid surface domain bundle') from error

def save_surface_domains(result, path):
    """Atomic self-contained NPZ; explicit candidate/diagnostic allowed, no overwrite."""
    from terrain_pipeline.artifacts.contracts import digest as _i102_digest
    validate_surface_domains(result, allow_unprepared=True)
    destination = _i102_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    arrays = {}
    tree = _encode(result, arrays)
    manifest = _i102_json.dumps({'format_version': 1, 'tree': tree, 'tree_sha256': _i102_digest(tree)}, ensure_ascii=False, allow_nan=False)
    if sum((array.nbytes for array in arrays.values())) + len(manifest.encode('utf8')) > SURFACE_NETWORK_CONSUMER_MAX_BYTES:
        raise ValueError('domain bundle exceeds hard storage bound')
    temporary = None
    try:
        with _i102_tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.npz', delete=False) as stream:
            temporary = _i102_Path(stream.name)
            _i102_np.savez_compressed(stream, manifest=manifest, **arrays)
        load_surface_domains(temporary, allow_unprepared=True)
        _i102_os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination

def _surface_domain_prepare_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate domain manifest JSON key')
        result[key] = value
    return result

def _surface_domain_prepare_constant(value):
    raise ValueError('nonfinite domain JSON constant: ' + value)

def load_surface_domains(path, *, allow_unprepared=False):
    """Bounded read and static semantic validation, never routing/recovery."""
    from terrain_pipeline.artifacts.contracts import array_hash as _i102_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i102_digest
    try:
        with _i102_zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 8192 or sum((item.file_size for item in entries)) > SURFACE_NETWORK_CONSUMER_MAX_BYTES or len({item.filename for item in entries}) != len(entries):
                raise ValueError('duplicate or excessive domain archive members')
            for entry in entries:
                if not entry.filename.endswith('.npy') or '/' in entry.filename or '\\' in entry.filename:
                    raise ValueError('invalid domain archive member')
                with archive.open(entry) as stream:
                    version = _i102_np.lib.format.read_magic(stream)
                    if version == (1, 0):
                        shape, _, dtype = _i102_np.lib.format.read_array_header_1_0(stream)
                    elif version == (2, 0):
                        shape, _, dtype = _i102_np.lib.format.read_array_header_2_0(stream)
                    else:
                        raise ValueError('unsupported domain array format')
                    size = _i102_math.prod(shape) * dtype.itemsize
                    if dtype.hasobject or size > SURFACE_NETWORK_CONSUMER_MAX_BYTES or size != entry.file_size - stream.tell():
                        raise ValueError('invalid or excessive domain array header')
                    if entry.filename == 'manifest.npy' and (shape != () or dtype.kind != 'U' or size > 16 * 1024 * 1024):
                        raise ValueError('domain manifest must be bounded Unicode scalar')
        with _i102_np.load(path, allow_pickle=False) as archive:
            manifest = _i102_json.loads(str(archive['manifest'].item()), object_pairs_hook=_surface_domain_prepare_pairs, parse_constant=_surface_domain_prepare_constant)
            if manifest['format_version'] != 1 or _i102_digest(manifest['tree']) != manifest['tree_sha256']:
                raise ValueError('domain manifest hash mismatch')
            used = {'manifest'}

            def decode(value):
                if isinstance(value, dict) and '$array' in value:
                    key = value['$array']
                    if key in used or set(value) != {'$array', 'sha256', 'shape', 'dtype'}:
                        raise ValueError('invalid domain array reference')
                    used.add(key)
                    array = archive[key]
                    if array.dtype.kind not in 'bifu' or array.dtype.str != value['dtype'] or list(array.shape) != value['shape'] or (_i102_array_hash(array) != value['sha256']):
                        raise ValueError('domain array hash/shape mismatch')
                    return _freeze(array)
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value
            result = decode(manifest['tree'])
            if used != set(archive.files):
                raise ValueError('unexpected domain archive arrays')
        validate_surface_domains(result, allow_unprepared=allow_unprepared)
        return _freeze(result)
    except (OSError, KeyError, TypeError, RecursionError, _i102_zipfile.BadZipFile, _i102_json.JSONDecodeError) as error:
        raise ValueError('invalid domain bundle') from error

def query_surface_domain(result, domain_id, z_slice, x_slice):
    """Read immutable fine windows only from a completely prepared multi-domain product."""
    validate_surface_domains(result)
    if result['status'] != 'prepared' or result['kind'] != 'evaluation':
        raise ValueError('only complete prepared domain products are queryable')
    entry = next((item for item in result['domains'] if item['domain_id'] == domain_id), None)
    if entry is None or entry['status'] != 'prepared':
        raise ValueError('unknown or unprepared domain')
    arrays = _payload(_plain(entry['recovery']))
    names = ('source_surface_m', 'valley_surface_m', 'final_surface_m', 'water_surface_m', 'wet_mask', 'domain_mask', 'protected_mask', 'legal_outlet_mask', 'total_cut_m')
    return _freeze({name: arrays[name][z_slice, x_slice] for name in names})
SURFACE_FINE_MOSAIC_VERSION = 'surface-fine-mosaic-v1.1'
SURFACE_FINE_MOSAIC_MAX_BYTES = 128 * 1024 * 1024

@_i105_dataclass(frozen=True)
class DomainFineSource:
    proof: _i105_Mapping
    domain_id: int
    window_zx: tuple | None = None
    unknown_mask: _i105_np.ndarray | None = None
    protected_mask: _i105_np.ndarray | None = None
    role: str = 'domain'

@_i105_dataclass(frozen=True)
class MosaicResources:
    max_cells: int = 100000
    max_retained_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES
    max_working_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES

    def __post_init__(self):
        for name, ceiling in (('max_cells', 100000), ('max_retained_bytes', SURFACE_FINE_MOSAIC_MAX_BYTES), ('max_working_bytes', SURFACE_FINE_MOSAIC_MAX_BYTES)):
            if type(getattr(self, name)) is not int or not 0 < getattr(self, name) <= ceiling:
                raise ValueError('invalid resource bound: ' + name)

def _make_mosaic_coverage_error(diagnostic):
    error = ValueError('coverage gap: bbox cells lack validated source')
    error.diagnostic = diagnostic
    return error

def _surface_fine_mosaic_json(value):
    return _i105_json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

def _surface_fine_mosaic_tree(value, arrays):
    from terrain_pipeline.artifacts.contracts import array_hash as _i105_array_hash
    if isinstance(value, _i105_np.ndarray):
        name = f'array_{len(arrays):05d}.npy'
        arrays[name] = value
        return {'$array': name, 'dtype': value.dtype.str, 'shape': list(value.shape), 'sha256': _i105_array_hash(value)}
    if isinstance(value, _i105_Mapping):
        return {key: _surface_fine_mosaic_tree(child, arrays) for key, child in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_surface_fine_mosaic_tree(child, arrays) for child in value]
    if isinstance(value, _i105_np.generic):
        return value.item()
    return value

def _identity(value):
    return _i105_hashlib.sha256(_surface_fine_mosaic_json(_surface_fine_mosaic_tree(value, {})).encode('utf8')).hexdigest()

def _surface_fine_mosaic_seal(value):
    value['identity_sha256'] = _identity(value)
    return _freeze(value)

def _surface_fine_mosaic_size(value):
    arrays = {}
    manifest = _surface_fine_mosaic_tree(value, arrays)
    return sum((array.nbytes + 256 for array in arrays.values())) + len(_surface_fine_mosaic_json(manifest).encode('utf8'))

def _surface_fine_mosaic_cancel(cancel):
    if cancel is not None and cancel():
        raise InterruptedError('fine mosaic cancelled')

def sources_from_surface_domains(result):
    pass  # Same-module import resolves directly to its global definition.
    validate_surface_domains(result)
    if result['kind'] != 'evaluation' or result['status'] != 'prepared':
        raise ValueError('statically validated prepared domain evaluation required')
    return tuple((DomainFineSource(entry['recovery'], entry['domain_id']) for entry in result['domains']))

def _source(source):
    if not isinstance(source, DomainFineSource):
        raise ValueError('accepted recovery proof required; plain arrays cannot self-certify')
    if type(source.domain_id) is not int or source.domain_id <= 0 or source.role not in ('domain', 'extension'):
        raise ValueError('invalid explicit source id/role')
    proof = _plain(source.proof)
    arrays = _payload(proof)
    _proof_gate(proof, arrays)
    shape = arrays['source_surface_m'].shape
    window = source.window_zx or (0, shape[0], 0, shape[1])
    if len(window) != 4 or any((type(value) is not int for value in window)) or (not 0 <= window[0] < window[1] <= shape[0]) or (not 0 <= window[2] < window[3] <= shape[1]) or (window[1] - window[0] < 2) or (window[3] - window[2] < 2):
        raise ValueError('invalid proof fine window')
    unknown = _i105_np.zeros(shape, bool) if source.unknown_mask is None else _i105_np.asarray(source.unknown_mask)
    protected = arrays['protected_mask'].copy()
    if source.protected_mask is not None:
        restriction = _i105_np.asarray(source.protected_mask)
        if restriction.dtype != bool or restriction.shape != shape:
            raise ValueError('invalid protected support mask')
        protected |= restriction
    if unknown.dtype != bool or unknown.shape != shape:
        raise ValueError('invalid unknown support mask')
    return (proof, {'domain_id': source.domain_id, 'role': source.role, 'proof_sha256': proof['identity_sha256'], 'window_zx': list(window), 'unknown_mask': unknown, 'protected_mask': protected})

def _surface_fine_mosaic_stencil(row, column, shape):
    top, left = (int(_i105_math.floor(row)), int(_i105_math.floor(column)))
    bottom, right = (min(top + 1, shape[0] - 1), min(left + 1, shape[1] - 1))
    fraction_z, fraction_x = (row - top, column - left)
    indices = _i105_np.array([top * shape[1] + left, top * shape[1] + right, bottom * shape[1] + left, bottom * shape[1] + right], _i105_np.int64)
    weights = _i105_np.array([(1 - fraction_z) * (1 - fraction_x), (1 - fraction_z) * fraction_x, fraction_z * (1 - fraction_x), fraction_z * fraction_x])
    return (indices, weights)

def _h0_support(proof):
    fine = proof['inputs']['fine']
    original = proof['inputs']['plan']
    coarse = original['identity']['parameters']
    shape = original['arrays']['source_height_m'].shape
    fine_shape = fine['shape_zx']
    indices = _i105_np.empty((_i105_math.prod(fine_shape), 4), _i105_np.int64)
    weights = _i105_np.empty(indices.shape)
    for row in range(fine_shape[0]):
        for column in range(fine_shape[1]):
            coarse_row = (fine['origin_z_m'] + row * fine['spacing_z_m'] - coarse['origin_z_m']) / coarse['spacing_z_m']
            coarse_column = (fine['origin_x_m'] + column * fine['spacing_x_m'] - coarse['origin_x_m']) / coarse['spacing_x_m']
            indices[row * fine_shape[1] + column], weights[row * fine_shape[1] + column] = _surface_fine_mosaic_stencil(coarse_row, coarse_column, shape)
    return {'indices': indices, 'weights': weights}

def _surface_fine_mosaic_grid(sources, proofs, metric_grid, resources):
    fine_grids = [proofs[source['proof_sha256']]['inputs']['fine'] for source in sources]
    spacing_x = min((fine['spacing_x_m'] for fine in fine_grids))
    spacing_z = min((fine['spacing_z_m'] for fine in fine_grids))
    bounds = []
    for source, fine in zip(sources, fine_grids):
        for name, spacing in (('spacing_x_m', spacing_x), ('spacing_z_m', spacing_z)):
            ratio = fine[name] / spacing
            if not _i105_math.isclose(ratio, round(ratio), abs_tol=1e-08, rel_tol=0):
                raise ValueError('integer precision ratios required; no coarsening')
        top, bottom, left, right = source['window_zx']
        bounds.append([fine['origin_x_m'] + left * fine['spacing_x_m'], fine['origin_x_m'] + (right - 1) * fine['spacing_x_m'], fine['origin_z_m'] + top * fine['spacing_z_m'], fine['origin_z_m'] + (bottom - 1) * fine['spacing_z_m']])
    bbox = metric_grid.get('bbox_xz_m', [min((item[0] for item in bounds)), max((item[1] for item in bounds)), min((item[2] for item in bounds)), max((item[3] for item in bounds))])
    if len(bbox) != 4 or any((isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i105_math.isfinite(value)) for value in bbox)) or bbox[1] <= bbox[0] or (bbox[3] <= bbox[2]):
        raise ValueError('invalid mosaic bbox')
    columns_f, rows_f = ((bbox[1] - bbox[0]) / spacing_x, (bbox[3] - bbox[2]) / spacing_z)
    if any((not _i105_math.isclose(value, round(value), abs_tol=1e-08, rel_tol=0) for value in (columns_f, rows_f))):
        raise ValueError('bbox not aligned to refinement grid')
    rows, columns = (round(rows_f), round(columns_f))
    if rows * columns > resources.max_cells:
        raise ValueError('mosaic cell resource limit')
    grid = {'coordinate_system': 'metric-xz-m', 'origin_x_m': float(bbox[0]), 'origin_z_m': float(bbox[2]), 'spacing_x_m': spacing_x, 'spacing_z_m': spacing_z, 'shape_cells_zx': [rows, columns], 'bbox_xz_m': list(bbox)}
    rectangles = []
    for bound in bounds:
        rectangle = [(bound[2] - bbox[2]) / spacing_z, (bound[3] - bbox[2]) / spacing_z, (bound[0] - bbox[0]) / spacing_x, (bound[1] - bbox[0]) / spacing_x]
        if any((not _i105_math.isclose(value, round(value), abs_tol=1e-08, rel_tol=0) for value in rectangle)):
            raise ValueError('source origin not aligned to refinement grid')
        rectangles.append([round(value) for value in rectangle])
    return (grid, rectangles)

def _ownership(grid, rectangles):
    rows, columns = grid['shape_cells_zx']
    owner = _i105_np.full((rows, columns), -1, _i105_np.int64)
    for source_id, (top, bottom, left, right) in enumerate(rectangles):
        if bottom <= 0 or right <= 0 or top >= rows or (left >= columns):
            continue
        window = (slice(max(top, 0), min(bottom, rows)), slice(max(left, 0), min(right, columns)))
        if _i105_np.any(owner[window] != -1):
            raise ValueError('source interior cells overlap; ownership must be unique')
        owner[window] = source_id
    return owner

def prepare_fine_mosaic(domains, *, metric_grid, vertical_datum, source_identity, sea_level_elevation_m, source_extensions=(), seam_tolerance_m=1e-08, q_tolerance_m3_s=1e-08, resources=MosaicResources(), cancel=None):
    if isinstance(domains, _i105_Mapping) and domains.get('kind') == 'evaluation':
        entries = list(sources_from_surface_domains(domains))
    else:
        entries = list(domains)
    extensions = list(source_extensions)
    if any((not isinstance(source, DomainFineSource) or source.role != 'extension' for source in extensions)):
        raise ValueError('explicit proof-bound extension source required')
    entries += extensions
    if not entries or len(entries) > 128 or (not isinstance(resources, MosaicResources)):
        raise ValueError('invalid mosaic source/resource count')
    if not isinstance(metric_grid, _i105_Mapping) or metric_grid.get('coordinate_system') != 'metric-xz-m':
        raise ValueError('explicit metric-xz-m grid required')
    if any((not isinstance(value, str) or not value.strip() for value in (vertical_datum, source_identity))):
        raise ValueError('explicit datum/source identity required')
    for value in (sea_level_elevation_m, seam_tolerance_m, q_tolerance_m3_s):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i105_math.isfinite(value)):
            raise ValueError('invalid sea/tolerance')
    if not 0 < seam_tolerance_m <= 1e-08 or not 0 < q_tolerance_m3_s <= 1e-08:
        raise ValueError('tolerances cannot weaken source gates')
    _surface_fine_mosaic_cancel(cancel)
    if _surface_fine_mosaic_size([source.proof for source in entries if isinstance(source, DomainFineSource)]) > resources.max_retained_bytes:
        raise ValueError('retained proof resource preflight limit')
    proofs, sources, support = ({}, [], {})
    for entry in entries:
        _surface_fine_mosaic_cancel(cancel)
        proof, source = _source(entry)
        if proof['inputs']['plan']['identity']['parameters']['sea_level_elevation_m'] != sea_level_elevation_m:
            raise ValueError('source sea datum differs')
        if source['domain_id'] in [item['domain_id'] for item in sources]:
            raise ValueError('source ids must be unique')
        proofs[proof['identity_sha256']] = proof
        sources.append(source)
    grid, rectangles = _surface_fine_mosaic_grid(sources, proofs, metric_grid, resources)
    cell_count = _i105_math.prod(grid['shape_cells_zx'])
    retained_bytes = _surface_fine_mosaic_size({'proofs': proofs, 'sources': sources})
    support_bytes = sum((_i105_math.prod(proof['inputs']['fine']['shape_zx']) * 64 for proof in proofs.values()))
    if retained_bytes + support_bytes + cell_count * 640 > min(resources.max_working_bytes, resources.max_retained_bytes):
        raise ValueError('working/retained resource preflight limit')
    owner = _ownership(grid, rectangles)
    for identity, proof in proofs.items():
        _surface_fine_mosaic_cancel(cancel)
        support[identity] = _h0_support(proof)
    result = {'algorithm_version': SURFACE_FINE_MOSAIC_VERSION, 'status': 'prepared', 'scope': 'accepted_recovery_engineering_bbox_cells', 'vertical_datum': vertical_datum, 'datum_evidence': 'caller_declared_not_independently_certified', 'source_identity': source_identity, 'sea_level_elevation_m': sea_level_elevation_m, 'seam_tolerance_m': float(seam_tolerance_m), 'q_tolerance_m3_s': float(q_tolerance_m3_s), 'resources': vars(resources), 'grid': grid, 'proofs': proofs, 'proof_h0_support': support, 'sources': sources, 'cell_owner': owner, 'full_domain_mosaic_prepared': False, 'natural_outlets_certified': False}
    if _i105_np.any(owner < 0):
        result.update(status='diagnostic', failures=['coverage_gap_without_validated_source'], missing_cell_count=int((owner < 0).sum()))
        raise _make_mosaic_coverage_error(_surface_fine_mosaic_seal(result))
    result.update(_surface_fine_mosaic_assemble(result, cancel))
    result['failures'] = []
    sealed = _surface_fine_mosaic_seal(result)
    validate_fine_mosaic(sealed)
    return sealed

def _evaluate_support(source, arrays, indices, weights, tolerance):
    positive = weights > 0
    if _i105_np.any(source['unknown_mask'].ravel()[indices[positive]]) or not _i105_np.all(arrays['domain_mask'].ravel()[indices[positive]]):
        raise ValueError('unknown or outside-domain positive-weight source support')
    h0 = float(_i105_np.dot(arrays['source_surface_m'].ravel()[indices], weights))
    h2 = float(_i105_np.dot(arrays['final_surface_m'].ravel()[indices], weights))
    protected = bool(_i105_np.any(source['protected_mask'].ravel()[indices[positive]]))
    if protected and _i105_np.any(_i105_np.abs(arrays['total_cut_m'].ravel()[indices[positive]]) > tolerance):
        raise ValueError('protected source support was modified')
    stages = arrays['water_surface_m'].ravel()[indices[positive]]
    wet = bool(_i105_np.all(arrays['wet_mask'].ravel()[indices[positive]]))
    if protected and _i105_np.any(arrays['wet_mask'].ravel()[indices[positive]]):
        raise ValueError('protected source support is wet')
    water = float(_i105_np.dot(stages, weights[positive])) if wet else 0.0
    if not _i105_math.isfinite(h0) or not _i105_math.isfinite(h2) or h2 > h0 + tolerance or (wet and water <= h2):
        raise ValueError('invalid H0/H2 or actual wet support')
    return (h0, h2, wet, water, protected)

def _mesh(grid):
    rows, columns = grid['shape_cells_zx']
    top_left = _i105_np.arange(rows)[:, None] * (columns + 1) + _i105_np.arange(columns)[None, :]
    cells = _i105_np.stack((top_left, top_left + 1, top_left + columns + 2, top_left + columns + 1), axis=-1).reshape(-1, 4)
    triangles = _i105_np.empty((len(cells) * 2, 3), _i105_np.int64)
    triangles[::2], triangles[1::2] = (cells[:, [0, 1, 2]], cells[:, [0, 2, 3]])
    return (cells, triangles)

def _surface_fine_mosaic_assemble(result, cancel):
    grid, sources = (result['grid'], result['sources'])
    rows, columns = grid['shape_cells_zx']
    count, node_count = (rows * columns, (rows + 1) * (columns + 1))
    nodes = {name: _i105_np.zeros(node_count, bool if name.endswith('mask') else float) for name in ('x_m', 'z_m', 'h0_m', 'h2_m', 'wet_mask', 'water_surface_m', 'protected_mask')}
    nodes['x_m'] = _i105_np.tile(grid['origin_x_m'] + _i105_np.arange(columns + 1) * grid['spacing_x_m'], rows + 1)
    nodes['z_m'] = _i105_np.repeat(grid['origin_z_m'] + _i105_np.arange(rows + 1) * grid['spacing_z_m'], columns + 1)
    seen = _i105_np.zeros(node_count, bool)
    cells, triangles = _mesh(grid)
    source_cells = _i105_np.empty((count, 2), _i105_np.int64)
    indices = _i105_np.empty((count, 4, 4), _i105_np.int64)
    weights = _i105_np.empty(indices.shape, float)
    payloads = {identity: _payload(proof) for identity, proof in result['proofs'].items()}
    for cell_id, cell in enumerate(cells):
        if cell_id % columns == 0:
            _surface_fine_mosaic_cancel(cancel)
        source = sources[int(result['cell_owner'].ravel()[cell_id])]
        fine = result['proofs'][source['proof_sha256']]['inputs']['fine']
        arrays = payloads[source['proof_sha256']]
        for corner_id, node_id in enumerate(cell):
            source_row = (nodes['z_m'][node_id] - fine['origin_z_m']) / fine['spacing_z_m']
            source_column = (nodes['x_m'][node_id] - fine['origin_x_m']) / fine['spacing_x_m']
            contributor, weight = _surface_fine_mosaic_stencil(source_row, source_column, tuple(fine['shape_zx']))
            indices[cell_id, corner_id], weights[cell_id, corner_id] = (contributor, weight)
            if corner_id == 0:
                source_cells[cell_id] = (_i105_math.floor(source_row + 1e-10), _i105_math.floor(source_column + 1e-10))
            values = _evaluate_support(source, arrays, contributor, weight, result['seam_tolerance_m'])
            for name, value in zip(('h0_m', 'h2_m', 'wet_mask', 'water_surface_m', 'protected_mask'), values):
                if seen[node_id] and (isinstance(value, bool) and nodes[name][node_id] != value or (not isinstance(value, bool) and abs(nodes[name][node_id] - value) > result['seam_tolerance_m'])):
                    raise ValueError('shared seam conflict in H0/H2/actual wet/protection')
                nodes[name][node_id] = value
            seen[node_id] = True
    output = {'nodes': nodes, 'cells': cells, 'triangles': triangles, 'contributors': {'source_cell_zx': source_cells, 'indices': indices, 'weights': weights}, 'wet_cells': nodes['wet_mask'][cells].all(axis=1)}
    output['q_cuts'], q_summary = _q_cut(result, payloads)
    output['summary'] = _integrals(grid, output, q_summary)
    return output

def _q_cut(result, payloads):
    records, positions_seen = ({}, set())
    total_local, total_out, total_in = (0.0, 0.0, 0.0)
    bbox = result['grid']['bbox_xz_m']
    groups = {}
    for identity, arrays in payloads.items():
        graph_key = _identity({name: arrays[name] for name in ('world_xz_m', 'receiver', 'order', 'discharge_m3_s', 'active_mask', 'outlet_mask', 'local_discharge_m3_s', 'node_stage_m')})
        groups.setdefault(graph_key, []).append(identity)
    for graph_key, identities in groups.items():
        arrays = payloads[identities[0]]
        selected = _i105_np.zeros(arrays['receiver'].shape, bool)
        positions = arrays['world_xz_m']
        for source in result['sources']:
            if source['proof_sha256'] not in identities:
                continue
            fine = result['proofs'][source['proof_sha256']]['inputs']['fine']
            top, bottom, left, right = source['window_zx']
            source_x = (positions[:, 0] - fine['origin_x_m']) / fine['spacing_x_m']
            source_z = (positions[:, 1] - fine['origin_z_m']) / fine['spacing_z_m']
            selected |= (source_z >= top) & (source_z <= bottom - 1) & (source_x >= left) & (source_x <= right - 1)
        selected &= (positions[:, 0] >= bbox[0]) & (positions[:, 0] <= bbox[1]) & (positions[:, 1] >= bbox[2]) & (positions[:, 1] <= bbox[3])
        carries_q = arrays['active_mask'] | (arrays['local_discharge_m3_s'] != 0) | (arrays['discharge_m3_s'] != 0)
        for position in positions[selected & carries_q]:
            key = tuple(position)
            if key in positions_seen:
                raise ValueError('duplicate nonzero Q graph ownership across independent proofs')
            positions_seen.add(key)
        receiver = arrays['receiver']
        internal = receiver >= 0
        target_selected = _i105_np.zeros(selected.shape, bool)
        target_selected[internal] = selected[receiver[internal]]
        outgoing = _i105_np.flatnonzero(selected & ~target_selected)
        incoming = _i105_np.flatnonzero(~selected & target_selected)
        local = float(arrays['local_discharge_m3_s'][selected].sum())
        outflow = float(arrays['discharge_m3_s'][outgoing].sum())
        inflow = float(arrays['discharge_m3_s'][incoming].sum())
        if abs(outflow - inflow - local) > result['q_tolerance_m3_s']:
            raise ValueError('nonconservative local-cut Q')
        records[graph_key] = {'proof_sha256': sorted(identities), 'selected_nodes': _i105_np.flatnonzero(selected), 'outgoing_nodes': outgoing, 'incoming_nodes': incoming, 'local_m3_s': local, 'outgoing_m3_s': outflow, 'incoming_m3_s': inflow, 'terminal_nodes': _i105_np.flatnonzero(selected & arrays['outlet_mask'] & arrays['active_mask'])}
        total_local += local
        total_out += outflow
        total_in += inflow
    return (records, {'q_semantics': 'unique_local_cut_not_sum_accumulated_nodes', 'q_local_m3_s': total_local, 'q_outgoing_m3_s': total_out, 'q_incoming_m3_s': total_in})

def _integrals(grid, output, q_summary):
    nodes, triangles = (output['nodes'], output['triangles'])
    area = grid['spacing_x_m'] * grid['spacing_z_m']
    cut = float(((nodes['h0_m'] - nodes['h2_m'])[triangles].mean(axis=1) * area / 2).sum())
    wet_triangles = triangles[_i105_np.repeat(output['wet_cells'], 2)]
    volume = float(((nodes['water_surface_m'] - nodes['h2_m'])[wet_triangles].mean(axis=1) * area / 2).sum())
    return {'unique_cell_area_m2': len(output['cells']) * area, 'unique_cut_volume_m3': cut, 'actual_wet_water_volume_m3': volume, **q_summary}

def _support_check(indices, weights, source_shape, target_x, target_z, source_grid):
    if indices.dtype != _i105_np.dtype('int64') or weights.dtype != _i105_np.dtype('float64') or indices.shape != weights.shape or (indices.shape != _i105_np.shape(target_x) + (4,)) or _i105_np.any(indices < 0) or _i105_np.any(indices >= _i105_math.prod(source_shape)) or (not _i105_np.isfinite(weights).all()) or _i105_np.any(weights < 0) or (not _i105_np.allclose(weights.sum(axis=-1), 1.0, atol=1e-10, rtol=0)):
        raise ValueError('invalid saved contributor indices/weights')
    target_column = (target_x - source_grid['origin_x_m']) / source_grid['spacing_x_m']
    target_row = (target_z - source_grid['origin_z_m']) / source_grid['spacing_z_m']
    left, top = (_i105_np.floor(target_column + 1e-10).astype(_i105_np.int64), _i105_np.floor(target_row + 1e-10).astype(_i105_np.int64))
    fraction_x, fraction_z = (target_column - left, target_row - top)
    expected_indices = _i105_np.stack((top * source_shape[1] + left, top * source_shape[1] + _i105_np.minimum(left + 1, source_shape[1] - 1), _i105_np.minimum(top + 1, source_shape[0] - 1) * source_shape[1] + left, _i105_np.minimum(top + 1, source_shape[0] - 1) * source_shape[1] + _i105_np.minimum(left + 1, source_shape[1] - 1)), axis=-1)
    expected_weights = _i105_np.stack(((1 - fraction_z) * (1 - fraction_x), (1 - fraction_z) * fraction_x, fraction_z * (1 - fraction_x), fraction_z * fraction_x), axis=-1)
    if not _i105_np.array_equal(indices, expected_indices) or not _i105_np.allclose(weights, expected_weights, atol=1e-10, rtol=0):
        raise ValueError('saved contributors are not original local bilinear support')

def _static_proof(proof, support):
    from terrain_pipeline.artifacts.contracts import array_hash as _i105_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i105_digest
    if _fingerprint({key: value for key, value in proof.items() if key != 'identity_sha256'}) != proof['identity_sha256']:
        raise ValueError('saved recovery source hash mismatch')
    if proof['status'] != 'accepted' or proof['accepted'] is not True or (not proof['attempts']) or (proof['attempts'][-1]['accepted'] is not True) or (proof['selected_method'] != proof['attempts'][-1]['method']) or any(proof['attempts'][-1]['failures'].values()):
        raise ValueError('saved source is not accepted recovery')
    original_local, original_total = _plan_proof(proof['inputs']['plan'])
    final_local, final_total = _plan_proof(proof['final_plan'])
    if not _i105_np.allclose(original_local, final_local, atol=1e-08, rtol=0) or not _i105_math.isclose(original_total, final_total, abs_tol=1e-08, rel_tol=0):
        raise ValueError('saved source changes local/outlet Q')
    surface = proof['surface']
    validate_surface_network(surface)
    params = _surface_network_consumer_identity(surface)
    if surface['status'] != 'prepared' or surface['summary']['publishable'] is not True or any(surface['summary']['budget_failures'].values()) or any(surface['summary']['joint_blockers'].values()) or (params['plan_sha256'] != proof['final_plan']['identity_sha256']) or (params['summary_sha256'] != _i105_digest(surface['summary'])) or (params['output_sha256'] != _i105_digest({name: _i105_array_hash(array) for name, array in surface['arrays'].items()})) or any((params[name] != value for name, value in proof['inputs']['budget'].items())):
        raise ValueError('saved source surface acceptance/budget identity differs')
    arrays = _payload(proof)
    shape = tuple(proof['inputs']['fine']['shape_zx'])
    original = proof['inputs']['plan']
    fine = proof['inputs']['fine']
    target_x = _i105_np.tile(fine['origin_x_m'] + _i105_np.arange(shape[1]) * fine['spacing_x_m'], shape[0])
    target_z = _i105_np.repeat(fine['origin_z_m'] + _i105_np.arange(shape[0]) * fine['spacing_z_m'], shape[1])
    _support_check(support['indices'], support['weights'], original['arrays']['source_height_m'].shape, target_x, target_z, original['identity']['parameters'])
    supported_h0 = (original['arrays']['source_height_m'].ravel()[support['indices']] * support['weights']).sum(axis=1)
    if not _i105_np.allclose(supported_h0, arrays['source_surface_m'].ravel(), atol=1e-08, rtol=0):
        raise ValueError('saved H0 lacks original source support')
    for name in ('source_surface_m', 'valley_surface_m', 'final_surface_m', 'water_surface_m'):
        if arrays[name].shape != shape or not _i105_np.isfinite(arrays[name]).all():
            raise ValueError('invalid saved fine source geometry')
    for name in ('domain_mask', 'protected_mask', 'legal_outlet_mask'):
        if arrays[name].dtype != bool or not _i105_np.array_equal(arrays[name], fine[name]):
            raise ValueError('saved source masks differ from original constraints')
    for name, difference in (('valley_cut_m', arrays['source_surface_m'] - arrays['valley_surface_m']), ('bed_cut_m', arrays['valley_surface_m'] - arrays['final_surface_m']), ('total_cut_m', arrays['source_surface_m'] - arrays['final_surface_m'])):
        if _i105_np.any(difference < -1e-08) or not _i105_np.allclose(arrays[name], difference, atol=1e-08, rtol=0):
            raise ValueError('saved source H0/H2/cuts disagree')
    wet, protected = (arrays['wet_mask'], arrays['protected_mask'])
    if wet.dtype != bool or wet.shape != shape or (not wet.any()) or _i105_np.any(wet & (~arrays['domain_mask'] | protected)) or _i105_np.any(arrays['water_surface_m'][wet] <= arrays['final_surface_m'][wet]) or _i105_np.any(arrays['water_surface_m'][~wet] != 0) or _i105_np.any((arrays['total_cut_m'] > 1e-08) & (~arrays['domain_mask'] | protected)):
        raise ValueError('saved source actual wet/protection invalid')
    for name in ('disconnected_seed_mask', 'boundary_contact_mask', 'reach_limited_mask'):
        if surface['arrays'][name].dtype != bool or _i105_np.any(surface['arrays'][name]):
            raise ValueError('saved source retains failed inundation')
    ledger, valley = (proof['fine_ledger'], proof['valley'])
    if (ledger is None) != (valley is None):
        raise ValueError('saved valley requires cumulative fine ledger')
    if ledger is not None:
        ledger_params, valley_params = (_surface_network_consumer_identity(ledger), _surface_network_consumer_identity(valley))
        if ledger['status'] != 'prepared' or any(ledger['summary']['failures'].values()) or valley['summary']['geometry_feasible'] is not True or any(valley['summary']['failures'].values()) or (ledger_params['surface_identity_sha256'] != surface['identity_sha256']) or (ledger_params['valley_identity_sha256'] != valley['identity_sha256']) or (ledger_params['summary_sha256'] != _i105_digest(ledger['summary'])) or (ledger_params['arrays_sha256'] != _i105_digest({name: _i105_array_hash(array) for name, array in ledger['arrays'].items()})) or (valley_params['replanned_sha256'] != proof['final_plan']['identity_sha256']) or (valley_params['summary_sha256'] != _i105_digest(valley['summary'])) or (valley_params['arrays_sha256'] != _i105_digest({name: {'sha256': _i105_array_hash(array), 'shape': list(array.shape), 'dtype': array.dtype.str} for name, array in sorted(valley['arrays'].items())})) or any((valley_params[name] != value or ledger_params[name] != value for name, value in proof['inputs']['valley_recipe'].items())):
            raise ValueError('saved valley/ledger proof inconsistent')
        for name in ('source_surface_m', 'valley_surface_m', 'final_surface_m', 'valley_cut_m', 'bed_cut_m', 'total_cut_m'):
            if not _i105_np.allclose(ledger['arrays'][name], arrays[name], atol=1e-08, rtol=0):
                raise ValueError('saved cumulative ledger source disagrees')
    active = arrays['active_mask']
    positions = arrays['world_xz_m']
    columns = _i105_np.rint((positions[:, 0] - fine['origin_x_m']) / fine['spacing_x_m']).astype(int)
    rows = _i105_np.rint((positions[:, 1] - fine['origin_z_m']) / fine['spacing_z_m']).astype(int)
    if not _i105_np.all(wet[rows[active], columns[active]]) or not _i105_np.all(arrays['legal_outlet_mask'][rows[active & arrays['outlet_mask']], columns[active & arrays['outlet_mask']]]) or (not _i105_np.allclose(arrays['final_surface_m'][rows[active], columns[active]], proof['final_plan']['arrays']['bounded_bed_m'].ravel()[active], atol=proof['inputs']['budget']['bed_match_tolerance_m'], rtol=0)):
        raise ValueError('saved graph bed/actual wet/terminal support disagrees')
    _static_geometry(proof, arrays, support, rows, columns)
    return arrays

def _static_geometry(proof, arrays, support, rows, columns):
    fine, inputs = (proof['inputs']['fine'], proof['inputs'])
    shape = tuple(fine['shape_zx'])
    original, final = (inputs['plan'], proof['final_plan'])
    weights = support['weights']
    h1 = (final['arrays']['source_height_m'].ravel()[support['indices']] * weights).sum(axis=1)
    if not _i105_np.allclose(h1, arrays['valley_surface_m'].ravel(), atol=1e-08, rtol=0):
        raise ValueError('saved H1 does not match final plan source support')
    if proof['valley'] is None:
        if not _i105_np.array_equal(original['arrays']['source_height_m'], final['arrays']['source_height_m']):
            raise ValueError('non-valley source changed H0')
    else:
        valley = proof['valley']['arrays']
        if not _i105_np.array_equal(valley['source_height_m'], original['arrays']['source_height_m']) or not _i105_np.array_equal(valley['valley_surface_m'], final['arrays']['source_height_m']):
            raise ValueError('saved valley H0/H1 source chain differs')
    active, receiver = (arrays['active_mask'], arrays['receiver'])
    wet, water = (arrays['wet_mask'], arrays['water_surface_m'])
    domain, protected = (arrays['domain_mask'], arrays['protected_mask'])
    if not _i105_np.array_equal(domain[rows, columns], inputs['coarse_domain'].ravel()) or not _i105_np.array_equal(protected[rows, columns], inputs['coarse_protected'].ravel()) or _i105_np.any(active & (~inputs['coarse_domain'].ravel() | inputs['coarse_protected'].ravel())):
        raise ValueError('saved graph masks differ from fine constraints')
    if not _i105_np.array_equal(original['arrays']['channel_mask'] & original['arrays']['outlet_mask'], final['arrays']['channel_mask'] & final['arrays']['outlet_mask']):
        raise ValueError('saved active terminal graph changed')
    for recipe_name in ('budget', 'stage_recipe', 'valley_recipe', 'inundation_recipe', 'section_recipe'):
        if any((isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i105_math.isfinite(value)) or (value < 0) for value in inputs[recipe_name].values())):
            raise ValueError('invalid original numeric recipe')
    min_depth, max_depth = (inputs['stage_recipe']['min_clearance_m'], inputs['stage_recipe']['max_depth_m'])
    stage = arrays['node_stage_m']
    plan_arrays, plan_params = (final['arrays'], final['identity']['parameters'])
    if not _i105_np.array_equal(plan_arrays['channel_mask'], plan_arrays['discharge_m3_s'] >= plan_params['start_discharge_m3_s']) or not _i105_np.array_equal(plan_arrays['outlet_mask'].ravel(), receiver < 0):
        raise ValueError('saved graph channel/terminal masks differ from Q/topology')
    for name, reference, exponent, minimum, maximum in (('nominal_width_m', 'reference_width_m', 'width_exponent', 'min_width_m', 'max_width_m'), ('nominal_depth_m', 'reference_depth_m', 'depth_exponent', 'min_depth_m', 'max_depth_m')):
        expected = _i105_np.clip(plan_params[reference] * (arrays['discharge_m3_s'][active] / plan_params['reference_discharge_m3_s']) ** plan_params[exponent], plan_params[minimum], plan_params[maximum])
        if not _i105_np.allclose(plan_arrays[name].ravel()[active], expected, atol=1e-08, rtol=0):
            raise ValueError('saved nominal section differs from graph Q recipe')
    bed = plan_arrays['bounded_bed_m'].ravel()
    preferred = bed + _i105_np.maximum(plan_arrays['nominal_depth_m'].ravel(), min_depth)
    terminals = _i105_np.flatnonzero(active & arrays['outlet_mask'])
    if not _i105_np.allclose(stage[terminals], inputs['outlet_stage_m'], atol=1e-08, rtol=0):
        raise ValueError('saved terminal stage differs from original boundary')
    if _i105_np.any(stage[active] - bed[active] < min_depth - 1e-09) or _i105_np.any(stage[active] - bed[active] > max_depth + 1e-09) or _i105_np.any(stage[active] > preferred[active] + inputs['stage_recipe']['max_lift_above_nominal_m'] + 1e-09):
        raise ValueError('saved stage depth/lift differs from original recipe')
    for donor in _i105_np.flatnonzero(active & (receiver >= 0)):
        target = int(receiver[donor])
        if not active[target]:
            raise ValueError('active graph edge leaves delivered channel')
        distance = float(_i105_np.linalg.norm(arrays['world_xz_m'][donor] - arrays['world_xz_m'][target]))
        expected_stage = max(preferred[donor], stage[target] + inputs['stage_recipe']['min_stage_slope_m_per_m'] * distance)
        if abs(stage[donor] - expected_stage) > 1e-08:
            raise ValueError('saved source stage violates original static stage equation')
        steps = max(abs(rows[target] - rows[donor]), abs(columns[target] - columns[donor]))
        previous_bed = None
        for step in range(steps + 1):
            fraction = step / steps
            row = int(round(rows[donor] + fraction * (rows[target] - rows[donor])))
            column = int(round(columns[donor] + fraction * (columns[target] - columns[donor])))
            stage_here = stage[donor] * (1 - fraction) + stage[target] * fraction
            bed_here = arrays['final_surface_m'][row, column]
            if not wet[row, column] or stage_here - bed_here < min_depth - 1e-09 or stage_here - bed_here > max_depth + 1e-09 or (previous_bed is not None and bed_here > previous_bed + 1e-09):
                raise ValueError('saved channel edge dry/blocked/reverse or depth budget exceeded')
            previous_bed = bed_here
    boundary = _i105_np.zeros(shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    legal = arrays['legal_outlet_mask']
    if _i105_np.any(wet & boundary & ~legal) or _i105_np.any(legal & (~domain | protected)):
        raise ValueError('saved wet boundary lacks legal outlet support')
    reached = _i105_np.zeros(shape, bool)
    stack = list(map(tuple, _i105_np.argwhere(wet & legal)))
    for row, column in stack:
        reached[row, column] = True
    while stack:
        row, column = stack.pop()
        for next_row, next_column in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1)):
            if 0 <= next_row < shape[0] and 0 <= next_column < shape[1] and wet[next_row, next_column] and (not reached[next_row, next_column]):
                reached[next_row, next_column] = True
                stack.append((next_row, next_column))
    if not _i105_np.array_equal(reached, wet):
        raise ValueError('saved actual wet water disconnected from legal terminals')
    threshold = max(0.5, inputs['inundation_recipe']['min_water_depth_m'] * 10)
    for before, after in ((_i105_np.s_[:-1, :], _i105_np.s_[1:, :]), (_i105_np.s_[:, :-1], _i105_np.s_[:, 1:])):
        adjacent = wet[before] & wet[after]
        if _i105_np.any(adjacent & (_i105_np.abs(water[before] - water[after]) > threshold + 1e-09)):
            raise ValueError('saved actual wet stage transition exceeds source gate')
    quadrature = _i105_np.ones(shape)
    quadrature[[0, -1], :] *= 0.5
    quadrature[:, [0, -1]] *= 0.5
    cell_area = fine['spacing_x_m'] * fine['spacing_z_m']
    budget = inputs['budget']
    bed_cut, valley_cut, total_cut = (arrays[name] for name in ('bed_cut_m', 'valley_cut_m', 'total_cut_m'))

    def area(cut):
        return float(_i105_np.sum((cut > 1e-09) * quadrature) * cell_area)

    def volume(cut):
        return float(_i105_np.sum(cut * quadrature) * cell_area)
    if _i105_np.any(bed_cut > budget['max_bed_cut_m'] + 1e-09) or area(bed_cut) > budget['max_area_m2'] + 1e-09 or volume(bed_cut) > budget['max_cut_volume_m3'] + 1e-09:
        raise ValueError('saved actual bed exceeds original budget')
    if proof['valley'] is not None:
        recipe = inputs['valley_recipe']
        if _i105_np.any(valley_cut > recipe['max_valley_depth_m'] + 1e-09) or area(valley_cut) > recipe['max_valley_area_m2'] + 1e-09 or volume(valley_cut) > recipe['max_valley_volume_m3'] + 1e-09 or (area(total_cut) > recipe['max_total_cut_area_m2'] + 1e-09) or (volume(total_cut) > recipe['max_total_cut_volume_m3'] + 1e-09):
            raise ValueError('saved cumulative fine ledger exceeds original budget')
    if _i105_np.any(bed_cut > inputs['section_recipe']['max_local_cut_m'] + 1e-09):
        raise ValueError('saved source exceeds original local section budget')
    _static_water_support(proof, arrays)

def _static_water_support(proof, arrays):
    """Algebraic source-stage support at saved cells, not an inundation replay."""
    fine, inputs = (proof['inputs']['fine'], proof['inputs'])
    donors = _i105_np.flatnonzero(arrays['active_mask'] & (arrays['receiver'] >= 0))
    targets = arrays['receiver'][donors]
    starts, ends = (arrays['world_xz_m'][donors], arrays['world_xz_m'][targets])
    vectors = ends - starts
    length_squared = (vectors * vectors).sum(axis=1)
    width = proof['final_plan']['arrays']['nominal_width_m'].ravel()
    stages = arrays['node_stage_m']
    shape = tuple(fine['shape_zx'])
    saved_seeds = proof['surface']['arrays']['channel_seed_mask']
    if not len(donors):
        raise ValueError('accepted wet source lacks supporting graph edges')
    for row in range(shape[0]):
        for column in range(shape[1]):
            position = _i105_np.array([fine['origin_x_m'] + column * fine['spacing_x_m'], fine['origin_z_m'] + row * fine['spacing_z_m']])
            fractions = _i105_np.clip(((position - starts) * vectors).sum(axis=1) / length_squared, 0.0, 1.0)
            distances = _i105_np.linalg.norm(position - starts - fractions[:, None] * vectors, axis=1)
            nearest = 0
            for index in range(1, len(donors)):
                if distances[index] < distances[nearest] - 1e-09:
                    nearest = index
            local_stages = stages[donors] * (1 - fractions) + stages[targets] * fractions
            radius = (width[donors] * (1 - fractions) + width[targets] * fractions) / 2
            stage_here = local_stages[nearest]
            seed = bool(_i105_np.any(distances <= _i105_np.maximum(radius / 2, min(fine['spacing_x_m'], fine['spacing_z_m']) / 2))) and stage_here > arrays['final_surface_m'][row, column] + inputs['inundation_recipe']['min_water_depth_m'] and arrays['domain_mask'][row, column] and (not arrays['protected_mask'][row, column])
            if bool(saved_seeds[row, column]) != bool(seed):
                raise ValueError('saved channel seed differs from actual graph/section/stage support')
            if arrays['wet_mask'][row, column] and (abs(arrays['water_surface_m'][row, column] - stage_here) > 1e-08 or stage_here <= arrays['final_surface_m'][row, column] + inputs['inundation_recipe']['min_water_depth_m'] or (not seed and distances[nearest] > inputs['inundation_recipe']['max_lateral_reach_m'] + 1e-09)):
                raise ValueError('saved wet water stage lacks original graph support')

def validate_fine_mosaic(result, *, allow_unprepared=False):
    """Check saved source/contributors/topology/Q without generating a mosaic."""
    try:
        record = _plain(result)
        identity = record.pop('identity_sha256')
        if record['algorithm_version'] != SURFACE_FINE_MOSAIC_VERSION or _identity(record) != identity:
            raise ValueError('fine mosaic identity mismatch')
        if record['full_domain_mosaic_prepared'] is not False or record['natural_outlets_certified'] is not False:
            raise ValueError('engineering cells cannot certify full domains/natural outlets')
        if record['scope'] != 'accepted_recovery_engineering_bbox_cells' or record['datum_evidence'] != 'caller_declared_not_independently_certified' or any((not isinstance(record[name], str) or not record[name].strip() for name in ('vertical_datum', 'source_identity'))):
            raise ValueError('invalid saved scope/datum')
        for name in ('seam_tolerance_m', 'q_tolerance_m3_s'):
            if type(record[name]) not in (int, float) or not 0 < record[name] <= 1e-08:
                raise ValueError('invalid saved tolerance')
        resources = MosaicResources(**record['resources'])
        if _surface_fine_mosaic_size(result) > resources.max_retained_bytes:
            raise ValueError('saved mosaic retained resource limit')
        cell_count = _i105_math.prod(record['grid']['shape_cells_zx'])
        if _surface_fine_mosaic_size(result) + cell_count * 640 > resources.max_working_bytes:
            raise ValueError('saved mosaic working resource limit')
        if not 0 < len(record['sources']) <= 128 or set(record['proofs']) != set(record['proof_h0_support']):
            raise ValueError('saved source/proof set invalid')
        payloads = {}
        for identity, proof in record['proofs'].items():
            if identity != proof['identity_sha256'] or proof['inputs']['plan']['identity']['parameters']['sea_level_elevation_m'] != record['sea_level_elevation_m']:
                raise ValueError('saved proof key/sea mismatch')
            payloads[identity] = _static_proof(proof, record['proof_h0_support'][identity])
        ids = []
        for source in record['sources']:
            if type(source['domain_id']) is not int or source['domain_id'] <= 0 or source['domain_id'] in ids or (source['role'] not in ('domain', 'extension')):
                raise ValueError('saved source id/role invalid')
            ids.append(source['domain_id'])
            arrays = payloads[source['proof_sha256']]
            shape = arrays['source_surface_m'].shape
            for name in ('unknown_mask', 'protected_mask'):
                if source[name].dtype != bool or source[name].shape != shape:
                    raise ValueError('saved source support mask invalid')
            if _i105_np.any(arrays['protected_mask'] & ~source['protected_mask']):
                raise ValueError('saved source removes protection')
            top, bottom, left, right = source['window_zx']
            if any((type(value) is not int for value in source['window_zx'])) or not 0 <= top < bottom <= shape[0] or (not 0 <= left < right <= shape[1]) or (bottom - top < 2) or (right - left < 2):
                raise ValueError('saved source window invalid')
        _validate_coverage(record, resources)
        owner = record['cell_owner']
        if record['status'] == 'diagnostic':
            if not allow_unprepared or not _i105_np.any(owner < 0) or record['missing_cell_count'] != int((owner < 0).sum()) or (record['failures'] != ['coverage_gap_without_validated_source']) or ('nodes' in record):
                raise ValueError('unprepared gap diagnostic cannot be published as mosaic')
            return True
        if record['status'] != 'prepared' or record['failures'] or _i105_np.any(owner < 0):
            raise ValueError('only completely covered bbox cells are prepared')
        _validate_mesh(record, payloads)
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError('invalid fine mosaic semantic record') from error

def _validate_coverage(record, resources):
    grid, owner = (record['grid'], record['cell_owner'])
    rows, columns = grid['shape_cells_zx']
    if type(rows) is not int or type(columns) is not int or rows <= 0 or (columns <= 0) or (rows * columns > resources.max_cells) or (owner.dtype != _i105_np.dtype('int64')) or (owner.shape != (rows, columns)) or _i105_np.any(owner < -1) or _i105_np.any(owner >= len(record['sources'])):
        raise ValueError('saved cell ownership shape/range invalid')
    bbox = grid['bbox_xz_m']
    fine_grids = [record['proofs'][source['proof_sha256']]['inputs']['fine'] for source in record['sources']]
    for axis, count, first, last in (('x', columns, bbox[0], bbox[1]), ('z', rows, bbox[2], bbox[3])):
        spacing = grid['spacing_' + axis + '_m']
        if spacing != min((fine['spacing_' + axis + '_m'] for fine in fine_grids)) or grid['origin_' + axis + '_m'] != first or (not _i105_math.isclose(first + spacing * count, last, abs_tol=1e-08, rel_tol=0)):
            raise ValueError('saved grid is not common finest refinement')
    if grid['coordinate_system'] != 'metric-xz-m':
        raise ValueError('invalid saved coordinate system')
    for row in range(rows):
        for column in range(columns):
            matches = []
            for source_id, (source, fine) in enumerate(zip(record['sources'], fine_grids)):
                top, bottom, left, right = source['window_zx']
                grid_left = (fine['origin_x_m'] + left * fine['spacing_x_m'] - bbox[0]) / grid['spacing_x_m']
                grid_right = (fine['origin_x_m'] + (right - 1) * fine['spacing_x_m'] - bbox[0]) / grid['spacing_x_m']
                grid_top = (fine['origin_z_m'] + top * fine['spacing_z_m'] - bbox[2]) / grid['spacing_z_m']
                grid_bottom = (fine['origin_z_m'] + (bottom - 1) * fine['spacing_z_m'] - bbox[2]) / grid['spacing_z_m']
                for value in (grid_left, grid_right, grid_top, grid_bottom, fine['spacing_x_m'] / grid['spacing_x_m'], fine['spacing_z_m'] / grid['spacing_z_m']):
                    if not _i105_math.isclose(value, round(value), abs_tol=1e-08, rel_tol=0):
                        raise ValueError('saved source precision/origin not integer aligned')
                if round(grid_top) <= row < round(grid_bottom) and round(grid_left) <= column < round(grid_right):
                    matches.append(source_id)
            if len(matches) > 1 or owner[row, column] != (matches[0] if matches else -1):
                raise ValueError('saved coverage/ownership overlaps or disagrees')

def _validate_mesh(record, payloads):
    grid = record['grid']
    rows, columns = grid['shape_cells_zx']
    count, node_count = (rows * columns, (rows + 1) * (columns + 1))
    nodes, cells, triangles = (record['nodes'], record['cells'], record['triangles'])
    if set(nodes) != {'x_m', 'z_m', 'h0_m', 'h2_m', 'wet_mask', 'water_surface_m', 'protected_mask'}:
        raise ValueError('saved node fields invalid')
    for name, array in nodes.items():
        dtype = bool if name.endswith('mask') else _i105_np.dtype('float64')
        if array.dtype != dtype or array.shape != (node_count,) or (not _i105_np.isfinite(array).all()):
            raise ValueError('saved node geometry shape/dtype invalid')
    node_ids = _i105_np.arange(node_count)
    if not _i105_np.allclose(nodes['x_m'], grid['origin_x_m'] + node_ids % (columns + 1) * grid['spacing_x_m'], atol=1e-08, rtol=0) or not _i105_np.allclose(nodes['z_m'], grid['origin_z_m'] + node_ids // (columns + 1) * grid['spacing_z_m'], atol=1e-08, rtol=0):
        raise ValueError('saved shared coordinates not unique/aligned')
    if cells.dtype != _i105_np.dtype('int64') or cells.shape != (count, 4) or triangles.dtype != _i105_np.dtype('int64') or (triangles.shape != (count * 2, 3)):
        raise ValueError('saved topology shape/dtype invalid')
    for cell_id, cell in enumerate(cells):
        top_left = cell_id // columns * (columns + 1) + cell_id % columns
        if tuple(cell) != (top_left, top_left + 1, top_left + columns + 2, top_left + columns + 1) or not _i105_np.array_equal(triangles[2 * cell_id], cell[[0, 1, 2]]) or (not _i105_np.array_equal(triangles[2 * cell_id + 1], cell[[0, 2, 3]])):
            raise ValueError('saved cell/triangle connectivity not continuous unique tessellation')
    contributors = record['contributors']
    indices, weights = (contributors['indices'], contributors['weights'])
    if indices.shape != (count, 4, 4) or weights.shape != indices.shape or contributors['source_cell_zx'].shape != (count, 2) or (contributors['source_cell_zx'].dtype != _i105_np.dtype('int64')):
        raise ValueError('saved cell contributor shape invalid')
    for source_id, source in enumerate(record['sources']):
        selection = _i105_np.flatnonzero(record['cell_owner'].ravel() == source_id)
        fine = record['proofs'][source['proof_sha256']]['inputs']['fine']
        arrays = payloads[source['proof_sha256']]
        selected_cells = cells[selection]
        _support_check(indices[selection], weights[selection], tuple(fine['shape_zx']), nodes['x_m'][selected_cells], nodes['z_m'][selected_cells], fine)
        for cell_id in selection:
            first = cells[cell_id, 0]
            source_cell = (_i105_math.floor((nodes['z_m'][first] - fine['origin_z_m']) / fine['spacing_z_m'] + 1e-10), _i105_math.floor((nodes['x_m'][first] - fine['origin_x_m']) / fine['spacing_x_m'] + 1e-10))
            if tuple(contributors['source_cell_zx'][cell_id]) != source_cell:
                raise ValueError('saved source cell reference disagrees')
            for corner_id, node_id in enumerate(cells[cell_id]):
                values = _evaluate_support(source, arrays, indices[cell_id, corner_id], weights[cell_id, corner_id], record['seam_tolerance_m'])
                for name, value in zip(('h0_m', 'h2_m', 'wet_mask', 'water_surface_m', 'protected_mask'), values):
                    actual = nodes[name][node_id]
                    if isinstance(value, bool) and actual != value or (not isinstance(value, bool) and abs(actual - value) > record['seam_tolerance_m']):
                        raise ValueError('saved node disagrees with source H0/H2/actual wet support')
    wet_cells = nodes['wet_mask'][cells].all(axis=1)
    if record['wet_cells'].dtype != bool or not _i105_np.array_equal(wet_cells, record['wet_cells']):
        raise ValueError('saved actual wet cells disagree')
    q_records, q_summary = _q_cut(record, payloads)
    if _identity(q_records) != _identity(record['q_cuts']) or _identity(_integrals(grid, record, q_summary)) != _identity(record['summary']):
        raise ValueError('saved unique integration/Q ledger disagrees')

def query_fine_mosaic(result, node_ids=None):
    validate_fine_mosaic(result)
    if node_ids is None:
        return _freeze(result['nodes'])
    selection = _i105_np.asarray(node_ids)
    if selection.dtype.kind not in 'iu' or selection.ndim != 1 or _i105_np.any(selection < 0) or _i105_np.any(selection >= len(result['nodes']['x_m'])):
        raise ValueError('invalid query node ids')
    return _freeze({name: array[selection] for name, array in result['nodes'].items()})

def _surface_fine_mosaic_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate mosaic JSON key')
        result[key] = value
    return result

def _surface_fine_mosaic_constant(value):
    raise ValueError('nonfinite mosaic JSON constant: ' + value)

def _preflight_archive(archive):
    entries = archive.infolist()
    names = [entry.filename for entry in entries]
    if not entries or len(entries) > 20000 or len(names) != len(set(names)) or (sum((entry.file_size for entry in entries)) > SURFACE_FINE_MOSAIC_MAX_BYTES) or ('manifest.json' not in names):
        raise ValueError('duplicate/oversized/incomplete mosaic ZIP')
    for entry in entries:
        if entry.flag_bits & 1 or entry.compress_type not in (_i105_zipfile.ZIP_STORED, _i105_zipfile.ZIP_DEFLATED):
            raise ValueError('invalid encrypted/compressed ZIP member')
        if entry.filename == 'manifest.json':
            if entry.file_size > 4 * 1024 * 1024:
                raise ValueError('mosaic manifest too large')
            continue
        if not entry.filename.startswith('array_') or not entry.filename.endswith('.npy') or '/' in entry.filename or ('\\' in entry.filename):
            raise ValueError('invalid mosaic ZIP member')
        with archive.open(entry) as stream:
            version = _i105_np.lib.format.read_magic(stream)
            if version not in ((1, 0), (2, 0)):
                raise ValueError('unsupported NPY version')
            length_size = 2 if version == (1, 0) else 4
            length_bytes = stream.read(length_size)
            if len(length_bytes) != length_size:
                raise ValueError('truncated NPY header length')
            header_length = _i105_struct.unpack('<H' if length_size == 2 else '<I', length_bytes)[0]
            if header_length > 8192 or stream.tell() + header_length > entry.file_size:
                raise ValueError('NPY raw header length exceeds bound')
            stream.seek(8)
            if version == (1, 0):
                shape, fortran, dtype = _i105_np.lib.format.read_array_header_1_0(stream)
            elif version == (2, 0):
                shape, fortran, dtype = _i105_np.lib.format.read_array_header_2_0(stream)
            else:
                raise ValueError('unsupported NPY version')
            if dtype.hasobject or dtype.kind not in 'biuf' or fortran or (len(shape) > 5) or any((type(size) is not int or size < 0 for size in shape)) or (_i105_math.prod(shape) * dtype.itemsize > SURFACE_FINE_MOSAIC_MAX_BYTES) or (stream.tell() + _i105_math.prod(shape) * dtype.itemsize != entry.file_size):
                raise ValueError('invalid NPY shape/dtype/payload size')

def save_fine_mosaic(result, path, *, allow_unprepared=False):
    validate_fine_mosaic(result, allow_unprepared=allow_unprepared)
    destination = _i105_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = _surface_fine_mosaic_tree(result, arrays)
    manifest = {'format_version': 2, 'tree': tree, 'tree_sha256': _identity(tree)}
    descriptor, temporary_name = _i105_tempfile.mkstemp(prefix='.' + destination.name + '-', suffix='.tmp', dir=destination.parent)
    temporary = _i105_Path(temporary_name)
    try:
        with _i105_os.fdopen(descriptor, 'w+b') as stream:
            with _i105_zipfile.ZipFile(stream, 'w', compression=_i105_zipfile.ZIP_STORED) as archive:
                archive.writestr('manifest.json', _surface_fine_mosaic_json(manifest))
                for name, array in arrays.items():
                    with _i105_io.BytesIO() as payload:
                        _i105_np.save(payload, _i105_np.ascontiguousarray(array), allow_pickle=False)
                        archive.writestr(name, payload.getvalue())
            stream.flush()
            _i105_os.fsync(stream.fileno())
        with _i105_zipfile.ZipFile(temporary) as archive:
            _preflight_archive(archive)
        _i105_os.link(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)

def load_fine_mosaic(path, *, allow_unprepared=False):
    from terrain_pipeline.artifacts.contracts import array_hash as _i105_array_hash
    try:
        with _i105_Path(path).open('rb') as retained, _i105_zipfile.ZipFile(retained) as archive:
            if _i105_os.fstat(retained.fileno()).st_size > SURFACE_FINE_MOSAIC_MAX_BYTES:
                raise ValueError('mosaic file exceeds byte cap')
            _preflight_archive(archive)
            manifest = _i105_json.loads(archive.read('manifest.json'), object_pairs_hook=_surface_fine_mosaic_pairs, parse_constant=_surface_fine_mosaic_constant)
            if set(manifest) != {'format_version', 'tree', 'tree_sha256'} or manifest['format_version'] != 2 or manifest['tree_sha256'] != _identity(manifest['tree']):
                raise ValueError('mosaic manifest identity mismatch')
            tree = manifest['tree']
            resources = MosaicResources(**tree['resources'])
            rows, columns = tree['grid']['shape_cells_zx']
            if type(rows) is not int or type(columns) is not int or rows <= 0 or (columns <= 0) or (rows * columns > resources.max_cells) or (sum((entry.file_size for entry in archive.infolist())) > resources.max_retained_bytes) or (sum((entry.file_size for entry in archive.infolist())) + rows * columns * 640 > resources.max_working_bytes):
                raise ValueError('archive JSON resource preflight limit')
            arrays, used = ({}, set())
            for name in archive.namelist():
                if name.endswith('.npy'):
                    with archive.open(name) as stream:
                        arrays[name] = _i105_np.load(stream, allow_pickle=False)

            def decode(value):
                if isinstance(value, dict) and '$array' in value:
                    name = value['$array']
                    if set(value) != {'$array', 'dtype', 'shape', 'sha256'} or name in used or name not in arrays:
                        raise ValueError('invalid/duplicate mosaic array reference')
                    array = arrays[name]
                    if value['dtype'] != array.dtype.str or value['shape'] != list(array.shape) or value['sha256'] != _i105_array_hash(array):
                        raise ValueError('mosaic array hash/shape mismatch')
                    used.add(name)
                    return array
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value
            result = decode(manifest['tree'])
            if used != set(arrays):
                raise ValueError('unreferenced mosaic arrays')
        validate_fine_mosaic(result, allow_unprepared=allow_unprepared)
        return _freeze(result)
    except (OSError, KeyError, TypeError, _i105_json.JSONDecodeError, _i105_zipfile.BadZipFile, EOFError) as error:
        raise ValueError('invalid fine mosaic bundle') from error
build_fine_mosaic = prepare_fine_mosaic
validate_surface_fine_mosaic = validate_fine_mosaic
save_surface_fine_mosaic = save_fine_mosaic
load_surface_fine_mosaic = load_fine_mosaic
query_surface_fine_mosaic = query_fine_mosaic
SURFACE_COAST_DROP_VERSION = 'surface-coast-drop-v1'
MODE = 'engineering-synthetic-straight-strip-not-free-fall'
SOURCE_MODEL = 'nodal-piecewise-linear-triangles-topright-to-bottomleft'
MAX_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_MEMBERS = 2048
MAX_HEADER_BYTES = 2048

def _make_coast_drop_error(reason):
    error = ValueError(reason)
    error.diagnostic = _i98_MappingProxyType({'status': 'rejected', 'reason': reason, 'geometry_published': False})
    return error

def _reject(reason):
    raise _make_coast_drop_error(reason)

def _json(value):
    return _i98_json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def _array_hash(array):
    digest = _i98_hashlib.sha256()
    digest.update(_json([array.dtype.str, list(array.shape)]).encode('ascii'))
    digest.update(array.tobytes(order='C'))
    return digest.hexdigest()

def _tree(value, arrays):
    if isinstance(value, _i98_np.ndarray):
        name = 'array_%04d.npy' % len(arrays)
        arrays[name] = value
        return {'$array': name, 'shape': list(value.shape), 'dtype': value.dtype.str, 'sha256': _array_hash(value)}
    if isinstance(value, _i98_Mapping):
        return {key: _tree(child, arrays) for key, child in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_tree(child, arrays) for child in value]
    if isinstance(value, _i98_np.generic):
        return value.item()
    return value

def fingerprint(value):
    return _i98_hashlib.sha256(_json(_tree(value, {})).encode('ascii')).hexdigest()

def _retained(value, ceiling=MAX_BYTES):
    total = 0
    members = 0

    def visit(child, depth):
        nonlocal total, members
        if depth > 40:
            _reject('source nesting resource cap')
        if isinstance(child, _i98_np.ndarray):
            if child.dtype.kind not in 'bifu' or child.size > 1000000:
                _reject('source array resource/dtype cap')
            total += child.nbytes + MAX_HEADER_BYTES
            members += 1
        elif isinstance(child, _i98_Mapping):
            if len(child) > MAX_MEMBERS:
                _reject('source mapping resource cap')
            for key, item in child.items():
                if not isinstance(key, str):
                    _reject('source keys must be strings')
                total += len(key.encode('utf-8'))
                visit(item, depth + 1)
        elif isinstance(child, (tuple, list)):
            if len(child) > 20000:
                _reject('source sequence resource cap')
            for item in child:
                visit(item, depth + 1)
        elif isinstance(child, str):
            total += len(child.encode('utf-8'))
        elif child is None or isinstance(child, (int, float, bool, _i98_np.generic)):
            total += 32
        else:
            _reject('unsupported source value')
        if total > ceiling or members >= MAX_MEMBERS:
            _reject('retained source resource cap')
    visit(value, 0)
    return total

@_i98_dataclass(frozen=True)
class DropResources:
    max_source_cells: int = 250000
    max_vertices: int = 20000
    max_triangles: int = 40000
    max_work: int = 500000
    max_retained_bytes: int = MAX_BYTES

    def __post_init__(self):
        for name, hard in (('max_source_cells', 250000), ('max_vertices', 20000), ('max_triangles', 40000), ('max_work', 500000), ('max_retained_bytes', MAX_BYTES)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= hard:
                _reject('invalid resource limit ' + name)

@_i98_dataclass(frozen=True)
class DropBudget:
    max_cut_depth_m: float
    max_cut_volume_m3: float

    def __post_init__(self):
        for value in (self.max_cut_depth_m, self.max_cut_volume_m3):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i98_math.isfinite(value)) or (value < 0):
                _reject('invalid explicit drop budget')

@_i98_dataclass(frozen=True)
class RiverAttachment:
    prepared: _i98_Mapping
    domain_id: int
    cross_section_xz_m: _i98_np.ndarray
    center_index: int
    datum: str

    def __post_init__(self):
        _retained(self.prepared)
        points = _i98_np.asarray(self.cross_section_xz_m)
        if points.ndim != 2 or points.shape[1] != 2 or (not 3 <= len(points) <= 256) or (points.dtype.kind not in 'fiu') or (not _i98_np.all(_i98_np.isfinite(points))):
            _reject('invalid explicit upstream cross-section')
        if type(self.domain_id) is not int or self.domain_id <= 0 or type(self.center_index) is not int or (not 0 < self.center_index < len(points) - 1):
            _reject('invalid attachment domain or center index')
        if not isinstance(self.datum, str) or not self.datum.strip() or len(self.datum) > 1024:
            _reject('explicit attachment datum required')
        if not _i98_np.all(points[:, 1] == points[0, 1]) or _i98_np.any(_i98_np.diff(points[:, 0]) <= 0):
            _reject('only increasing-x constant-z straight cross-sections supported')
        object.__setattr__(self, 'prepared', _freeze(self.prepared))
        object.__setattr__(self, 'cross_section_xz_m', _freeze(points.astype('<f8')))

@_i98_dataclass(frozen=True)
class EngineeringSource:
    role: str
    source: str
    datum: str
    origin_x_m: float
    origin_z_m: float
    spacing_x_m: float
    spacing_z_m: float
    h0_m: _i98_np.ndarray
    h2_m: _i98_np.ndarray
    water_m: _i98_np.ndarray
    valid_mask: _i98_np.ndarray
    unknown_mask: _i98_np.ndarray
    protected_mask: _i98_np.ndarray
    wet_mask: _i98_np.ndarray
    ocean_mask: _i98_np.ndarray
    sea_level_m: float
    source_kind: str = 'engineering_synthetic'
    surface_model: str = SOURCE_MODEL

    def __post_init__(self):
        shape = _i98_np.asarray(self.h0_m).shape
        if len(shape) != 2 or min(shape) < 2 or _i98_math.prod(shape) > 250000:
            _reject('engineering source cell resource cap')
        if self.role not in ('corridor', 'sea') or self.source_kind != 'engineering_synthetic' or self.surface_model != SOURCE_MODEL:
            _reject('explicit engineering synthetic corridor/sea source required')
        for name in ('source', 'datum'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 1024:
                _reject('explicit source declaration/datum required')
        for name in ('origin_x_m', 'origin_z_m', 'spacing_x_m', 'spacing_z_m', 'sea_level_m'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i98_math.isfinite(value)) or (name.startswith('spacing') and value <= 0):
                _reject('invalid engineering metric coordinates/sea level')
        for name in ('h0_m', 'h2_m', 'water_m', 'valid_mask', 'unknown_mask', 'protected_mask', 'wet_mask', 'ocean_mask'):
            array = _i98_np.asarray(getattr(self, name))
            if array.shape != shape:
                _reject('engineering source shape mismatch')
            if name.endswith('mask'):
                if array.dtype != bool:
                    _reject('engineering source masks must be boolean')
            elif array.dtype.kind not in 'fiu' or not _i98_np.all(_i98_np.isfinite(array)):
                _reject('engineering source geometry must be finite')
            object.__setattr__(self, name, _freeze(array.astype(bool if name.endswith('mask') else '<f8')))

def _source_record(source):
    if not isinstance(source, EngineeringSource):
        _reject('missing explicit corridor/sea source')
    record = {name: getattr(source, name) for name in source.__dataclass_fields__}
    record['identity_sha256'] = fingerprint(record)
    return record

def _check_source(record, role, datum, resources):
    if not isinstance(record, _i98_Mapping) or set(record) != set(EngineeringSource.__dataclass_fields__) | {'identity_sha256'}:
        _reject('source record schema mismatch')
    if record['identity_sha256'] != fingerprint({key: value for key, value in record.items() if key != 'identity_sha256'}):
        _reject('source content identity mismatch')
    if record['h0_m'].size > resources.max_source_cells:
        _reject('source cell resource cap')
    source = EngineeringSource(**{key: value for key, value in record.items() if key != 'identity_sha256'})
    if source.role != role or source.datum != datum:
        _reject('source role or vertical datum mismatch')
    if _i98_np.any(source.h2_m > source.h0_m + 1e-10):
        _reject('source H2 raises bed above H0')

def _stencil(source, points, shape):
    indices = _i98_np.empty((len(points), 4), dtype=_i98_np.int64)
    weights = _i98_np.empty((len(points), 4), dtype=_i98_np.float64)
    for point_n, (world_x, world_z) in enumerate(points):
        column = (world_x - source['origin_x_m']) / source['spacing_x_m']
        row = (world_z - source['origin_z_m']) / source['spacing_z_m']
        if not 0 <= row <= shape[0] - 1 or not 0 <= column <= shape[1] - 1:
            _reject('source coverage gap; no implicit extrapolation')
        top, left = (int(_i98_math.floor(row)), int(_i98_math.floor(column)))
        bottom, right = (min(top + 1, shape[0] - 1), min(left + 1, shape[1] - 1))
        fraction_z, fraction_x = (row - top, column - left)
        indices[point_n] = [top * shape[1] + left, top * shape[1] + right, bottom * shape[1] + left, bottom * shape[1] + right]
        weights[point_n] = [(1 - fraction_z) * (1 - fraction_x), (1 - fraction_z) * fraction_x, fraction_z * (1 - fraction_x), fraction_z * fraction_x]
    return (indices, weights)

def _surface_coast_drop_sample(array, indices, weights):
    return _i98_np.sum(array.ravel()[indices] * weights, axis=1)

def _support(indices, weights, valid, unknown, protected, wet, ocean=None):
    positive = weights > 0
    for mask, expected, reason in ((valid, True, 'invalid support'), (unknown, False, 'unknown support'), (protected, False, 'protected support'), (wet, True, 'nonwet support')):
        if _i98_np.any((mask.ravel()[indices] != expected) & positive):
            _reject(reason)
    if ocean is not None and _i98_np.any(~ocean.ravel()[indices] & positive):
        _reject('sea attachment lacks explicit ocean support')

def _attachment(record):
    prepared = _plain(record['prepared'])
    validate_surface_domains(prepared)
    if prepared['kind'] != 'evaluation' or prepared['status'] != 'prepared':
        _reject('accepted prepared domain product required')
    if record['datum'] != prepared['candidate']['inputs']['vertical_datum']:
        _reject('attachment datum differs from saved prepared source')
    entry = next((entry for entry in prepared['domains'] if entry['domain_id'] == record['domain_id']), None)
    if entry is None or entry['status'] != 'prepared':
        _reject('unknown or unprepared attachment domain')
    recovery = entry['recovery']
    payload = _payload(recovery)
    _proof_gate(recovery, payload)
    points = record['cross_section_xz_m']
    fine = recovery['inputs']['fine']
    fine_columns = (points[:, 0] - fine['origin_x_m']) / fine['spacing_x_m']
    fine_rows = (points[:, 1] - fine['origin_z_m']) / fine['spacing_z_m']
    if not _i98_np.allclose(fine_columns, _i98_np.round(fine_columns), rtol=0, atol=1e-10) or not _i98_np.allclose(fine_rows, _i98_np.round(fine_rows), rtol=0, atol=1e-10) or (not _i98_np.allclose(_i98_np.diff(points[:, 0]), fine['spacing_x_m'], rtol=0, atol=1e-10)):
        _reject('entire river cross-section must sample contiguous aligned fine nodes')
    indices, weights = _stencil(fine, points, payload['final_surface_m'].shape)
    _support(indices, weights, payload['domain_mask'], _i98_np.zeros_like(payload['wet_mask']), payload['protected_mask'], payload['wet_mask'])
    center = record['center_index']
    nodes = _i98_np.flatnonzero(payload['active_mask'] & payload['outlet_mask'] & _i98_np.all(_i98_np.isclose(payload['world_xz_m'], points[center], rtol=0, atol=1e-10), axis=1))
    if len(nodes) != 1:
        _reject('center must attach to exactly one actual active terminal cut')
    terminal = int(nodes[0])
    discharge = float(payload['discharge_m3_s'][terminal])
    if not _i98_math.isfinite(discharge) or discharge <= 0:
        _reject('positive actual terminal cut Q required')
    fine_shape = payload['final_surface_m'].shape
    full_points = _i98_np.column_stack((_i98_np.tile(fine['origin_x_m'] + _i98_np.arange(fine_shape[1]) * fine['spacing_x_m'], fine_shape[0]), _i98_np.repeat(fine['origin_z_m'] + _i98_np.arange(fine_shape[0]) * fine['spacing_z_m'], fine_shape[1])))
    original = recovery['inputs']['plan']
    source_indices, source_weights = _stencil(original['identity']['parameters'], full_points, original['arrays']['source_height_m'].shape)
    return {'indices': indices, 'weights': weights, 'h0_m': _surface_coast_drop_sample(payload['source_surface_m'], indices, weights), 'h2_m': _surface_coast_drop_sample(payload['final_surface_m'], indices, weights), 'water_m': _surface_coast_drop_sample(payload['water_surface_m'], indices, weights), 'terminal_node': terminal, 'terminal_q_m3_s': discharge, 'fine_spacing_x_m': fine['spacing_x_m'], 'recovery_sha256': recovery['identity_sha256'], 'proof_support': {'payload': payload, 'h0_indices': source_indices, 'h0_weights': source_weights}}

def _saved_support(indices, weights, points, source, shape):
    if indices.dtype != _i98_np.dtype('int64') or weights.dtype != _i98_np.dtype('float64') or indices.shape != (len(points), 4) or (weights.shape != indices.shape) or _i98_np.any(indices < 0) or _i98_np.any(indices >= _i98_math.prod(shape)) or (not _i98_np.all(_i98_np.isfinite(weights))) or _i98_np.any(weights < 0) or (not _i98_np.allclose(weights.sum(axis=1), 1.0, rtol=0, atol=1e-10)):
        _reject('invalid saved support indices/weights')
    for point_n, point in enumerate(points):
        column = (point[0] - source['origin_x_m']) / source['spacing_x_m']
        row = (point[1] - source['origin_z_m']) / source['spacing_z_m']
        if not 0 <= column <= shape[1] - 1 or not 0 <= row <= shape[0] - 1:
            _reject('saved support outside source bounds')
        top, left = (int(_i98_math.floor(row)), int(_i98_math.floor(column)))
        bottom, right = (min(top + 1, shape[0] - 1), min(left + 1, shape[1] - 1))
        fraction_z, fraction_x = (row - top, column - left)
        if not _i98_np.array_equal(indices[point_n], [top * shape[1] + left, top * shape[1] + right, bottom * shape[1] + left, bottom * shape[1] + right]) or not _i98_np.allclose(weights[point_n], [(1 - fraction_z) * (1 - fraction_x), (1 - fraction_z) * fraction_x, fraction_z * (1 - fraction_x), fraction_z * fraction_x], rtol=0, atol=1e-10):
            _reject('saved contributor support algebra mismatch')

def _static_attachment(record, support, indices, weights):
    from terrain_pipeline.drainage import grid_mesh as _i98_grid_mesh
    from terrain_pipeline.artifacts.contracts import array_hash as _i98_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _i98_digest
    prepared = _plain(record['prepared'])
    if prepared['kind'] != 'evaluation' or prepared['status'] != 'prepared' or prepared['identity_sha256'] != _hash({key: value for key, value in prepared.items() if key != 'identity_sha256'}):
        _reject('saved prepared source status/hash mismatch')
    candidate = prepared['candidate']
    if candidate['identity_sha256'] != _hash({key: value for key, value in candidate.items() if key != 'identity_sha256'}) or record['datum'] != candidate['inputs']['vertical_datum']:
        _reject('saved candidate hash/datum mismatch')
    _validate_plan(candidate)
    entry = next((item for item in prepared['domains'] if item['domain_id'] == record['domain_id']), None)
    if entry is None or entry['status'] != 'prepared':
        _reject('saved domain not prepared')
    proof = entry['recovery']
    if proof['identity_sha256'] != _fingerprint({key: value for key, value in proof.items() if key != 'identity_sha256'}) or proof['status'] != 'accepted' or proof['accepted'] is not True or (not proof['attempts']) or (proof['attempts'][-1]['accepted'] is not True) or any(proof['attempts'][-1]['failures'].values()) or (proof['selected_method'] != proof['attempts'][-1]['method']):
        _reject('saved recovery acceptance/hash mismatch')
    original, final = (proof['inputs']['plan'], proof['final_plan'])
    domain_record = next((item for item in candidate['domains'] if item['domain_id'] == record['domain_id']), None)
    if domain_record is None or domain_record['status'] != 'routed':
        _reject('saved candidate domain not routed')
    first_row, last_row, first_column, last_column = domain_record['bounds_zx']
    candidate_inputs = candidate['inputs']
    candidate_arrays = candidate['arrays']
    window = _i98_np.s_[first_row:last_row, first_column:last_column]
    labels = candidate_inputs['domain_labels'][window]
    domain = labels == record['domain_id']
    global_columns = candidate_inputs['height_m'].shape[1]
    local_columns = last_column - first_column
    original_arrays = original['arrays']
    _surface_coast_drop_same(original_arrays['source_height_m'], candidate_inputs['height_m'][window], 'candidate original H0 window')
    _surface_coast_drop_same(original_arrays['discharge_m3_s'], _i98_np.where(domain, candidate_arrays['discharge_m3_s'][window], 0.0), 'candidate original Q window')
    _surface_coast_drop_same(proof['inputs']['coarse_domain'], domain, 'candidate original domain mask')
    _surface_coast_drop_same(proof['inputs']['coarse_protected'], candidate_inputs['protected_mask'][window], 'candidate original protection mask')
    global_to_local = {}
    for local_n in range(domain.size):
        global_n = (first_row + local_n // local_columns) * global_columns + first_column + local_n % local_columns
        global_to_local[global_n] = local_n
        target = int(candidate_arrays['receiver'][global_n])
        expected = -1
        if domain.flat[local_n] and target >= 0:
            expected = (target // global_columns - first_row) * local_columns + target % global_columns - first_column
        if int(original_arrays['receiver'][local_n]) != expected:
            _reject('candidate original receiver binding mismatch')
    expected_order = [local_n for local_n in range(domain.size) if not domain.flat[local_n]]
    expected_order.extend((global_to_local[int(global_n)] for global_n in candidate_arrays['order'] if int(global_n) in global_to_local and domain.flat[global_to_local[int(global_n)]]))
    _surface_coast_drop_same(original_arrays['order'], expected_order, 'candidate original order binding')
    _surface_coast_drop_same(original_arrays['outlet_mask'], (original_arrays['receiver'] == -1).reshape(domain.shape), 'candidate original outlets')
    original_params = original['identity']['parameters']
    for name, expected in {'spacing_x_m': candidate_inputs['spacing_x_m'], 'spacing_z_m': candidate_inputs['spacing_z_m'], 'origin_x_m': candidate_inputs['origin_x_m'] + first_column * candidate_inputs['spacing_x_m'], 'origin_z_m': candidate_inputs['origin_z_m'] + first_row * candidate_inputs['spacing_z_m'], 'sea_level_elevation_m': candidate_inputs['sea_level_elevation_m'], 'source_identity': candidate['identity_sha256'] + ':domain:' + str(record['domain_id'])}.items():
        if original_params[name] != expected:
            _reject('candidate original world metric/source identity binding mismatch')
    config = prepared['configurations'][str(record['domain_id'])]
    for name, expected in config.items():
        if name not in ('channel_recipe', 'recovery_recipe') and _hash(expected) != _hash(proof['inputs'][name]):
            _reject('saved recovery changed configured physical budget or fine support')
    if any((original_params[name] != value for name, value in config['channel_recipe'].items())):
        _reject('saved original channel recipe changed')
    mesh = _archived_raster_mesh(domain.shape) if candidate['algorithm_version'] == LEGACY_VERSION else _i98_grid_mesh(domain.shape, x0_m=original_params['origin_x_m'], z0_m=original_params['origin_z_m'], dx_m=original_params['spacing_x_m'], dz_m=original_params['spacing_z_m'], world_seed=original_params.get('world_seed', 20261020))
    for local_n in _i98_np.flatnonzero(domain):
        target = int(final['arrays']['receiver'][local_n])
        if target < 0 and original_arrays['receiver'][local_n] != -1 or (target >= 0 and (not _edge_ok(int(local_n), target, domain.shape, domain & ~candidate_inputs['protected_mask'][window], mesh))):
            _reject('saved final route changes legal terminal or crosses domain/protection')
    original_local, original_total = _plan_proof(original)
    final_local, final_total = _plan_proof(final)
    _surface_coast_drop_same(original_local, final_local, 'saved original/final local Q')
    _surface_coast_drop_same(original_total, final_total, 'saved total outlet Q')
    _surface_coast_drop_same(original['arrays']['channel_mask'] & original['arrays']['outlet_mask'], final['arrays']['channel_mask'] & final['arrays']['outlet_mask'], 'saved active terminal identity')
    surface = proof['surface']
    validate_surface_network(surface)
    params = _surface_network_consumer_identity(surface)
    if surface['status'] != 'prepared' or surface['summary']['publishable'] is not True or any(surface['summary']['budget_failures'].values()) or any(surface['summary']['joint_blockers'].values()) or (params['plan_sha256'] != final['identity_sha256']) or (params['summary_sha256'] != _i98_digest(surface['summary'])) or (params['output_sha256'] != _i98_digest({name: _i98_array_hash(array) for name, array in surface['arrays'].items()})) or any((params[name] != value for name, value in proof['inputs']['budget'].items())):
        _reject('saved surface acceptance chain mismatch')
    if set(support) != {'payload', 'h0_indices', 'h0_weights'}:
        _reject('saved proof support schema mismatch')
    arrays = support['payload']
    fine = proof['inputs']['fine']
    shape = tuple(fine['shape_zx'])
    coarse_rows = first_row + _i98_np.floor(_i98_np.arange(shape[0]) * fine['spacing_z_m'] / candidate_inputs['spacing_z_m'] + 0.5).astype(_i98_np.int64)
    coarse_columns = first_column + _i98_np.floor(_i98_np.arange(shape[1]) * fine['spacing_x_m'] / candidate_inputs['spacing_x_m'] + 0.5).astype(_i98_np.int64)
    legal = _i98_np.zeros_like(candidate_inputs['land_mask'])
    for domain_id, land_cell, _ in candidate_inputs['coastal_outlets']:
        if domain_id == record['domain_id']:
            legal.flat[land_cell] = True
    sample = _i98_np.ix_(coarse_rows, coarse_columns)
    expected_domain = candidate_inputs['domain_labels'][sample] == record['domain_id']
    expected_protected = candidate_inputs['protected_mask'][sample]
    _surface_coast_drop_same(fine['domain_mask'], expected_domain, 'candidate fine domain binding')
    _surface_coast_drop_same(fine['protected_mask'], expected_protected, 'candidate fine protection binding')
    _surface_coast_drop_same(fine['legal_outlet_mask'], legal[sample] & expected_domain & ~expected_protected, 'candidate fine coast binding')
    for name in ('source_surface_m', 'valley_surface_m', 'final_surface_m', 'water_surface_m'):
        if arrays[name].shape != shape or not _i98_np.all(_i98_np.isfinite(arrays[name])):
            _reject('saved fine source geometry invalid')
    ledger, valley = (proof['fine_ledger'], proof['valley'])
    if (ledger is None) != (valley is None):
        _reject('saved valley lacks ledger')
    raw = surface['arrays'] if ledger is None else ledger['arrays']
    for name in ('source_surface_m', 'final_surface_m'):
        _surface_coast_drop_same(arrays[name], raw[name], 'saved fine payload ' + name)
    _surface_coast_drop_same(arrays['valley_surface_m'], surface['arrays']['source_surface_m'], 'saved H1')
    _surface_coast_drop_same(arrays['water_surface_m'], _i98_np.where(surface['arrays']['wet_mask'], surface['arrays']['water_surface_m'], 0.0), 'saved fine water')
    if ledger is not None:
        ledger_params, valley_params = (_surface_network_consumer_identity(ledger), _surface_network_consumer_identity(valley))
        if ledger['status'] != 'prepared' or any(ledger['summary']['failures'].values()) or valley['summary']['geometry_feasible'] is not True or any(valley['summary']['failures'].values()) or (ledger_params['surface_identity_sha256'] != surface['identity_sha256']) or (ledger_params['valley_identity_sha256'] != valley['identity_sha256']) or (ledger_params['summary_sha256'] != _i98_digest(ledger['summary'])) or (ledger_params['arrays_sha256'] != _i98_digest({name: _i98_array_hash(array) for name, array in ledger['arrays'].items()})) or (valley_params['replanned_sha256'] != final['identity_sha256']) or (valley_params['summary_sha256'] != _i98_digest(valley['summary'])) or (valley_params['arrays_sha256'] != _i98_digest({name: {'sha256': _i98_array_hash(array), 'shape': list(array.shape), 'dtype': array.dtype.str} for name, array in sorted(valley['arrays'].items())})) or any((valley_params[name] != value or ledger_params[name] != value for name, value in proof['inputs']['valley_recipe'].items())):
            _reject('saved valley/ledger acceptance chain mismatch')
        _surface_coast_drop_same(valley['arrays']['source_height_m'], original['arrays']['source_height_m'], 'valley original H0')
        _surface_coast_drop_same(valley['arrays']['valley_surface_m'], final['arrays']['source_height_m'], 'valley coarse H1')
    else:
        _surface_coast_drop_same(original['arrays']['source_height_m'], final['arrays']['source_height_m'], 'unchanged nonvalley H0')
    if _i98_array_hash(original['arrays']['source_height_m']) != proof['summary']['original_height_sha256']:
        _reject('saved original H0 hash mismatch')
    full_points = _i98_np.column_stack((_i98_np.tile(fine['origin_x_m'] + _i98_np.arange(shape[1]) * fine['spacing_x_m'], shape[0]), _i98_np.repeat(fine['origin_z_m'] + _i98_np.arange(shape[0]) * fine['spacing_z_m'], shape[1])))
    _saved_support(support['h0_indices'], support['h0_weights'], full_points, original['identity']['parameters'], original['arrays']['source_height_m'].shape)
    _surface_coast_drop_same(arrays['source_surface_m'].ravel(), (original['arrays']['source_height_m'].ravel()[support['h0_indices']] * support['h0_weights']).sum(axis=1), 'full saved H0 source algebra')
    _surface_coast_drop_same(arrays['valley_surface_m'].ravel(), (final['arrays']['source_height_m'].ravel()[support['h0_indices']] * support['h0_weights']).sum(axis=1), 'full saved H1 source algebra')
    for name in ('domain_mask', 'protected_mask', 'legal_outlet_mask'):
        if arrays[name].dtype != bool or not _i98_np.array_equal(arrays[name], fine[name]):
            _reject('saved proof support masks differ')
    wet = arrays['wet_mask']
    if wet.dtype != bool or not _i98_np.array_equal(wet, surface['arrays']['wet_mask']) or _i98_np.any(wet & (~arrays['domain_mask'] | arrays['protected_mask'])) or _i98_np.any(arrays['water_surface_m'][wet] <= arrays['final_surface_m'][wet]):
        _reject('saved actual wet/protected/depth support mismatch')
    for name, cut in (('valley_cut_m', arrays['source_surface_m'] - arrays['valley_surface_m']), ('bed_cut_m', arrays['valley_surface_m'] - arrays['final_surface_m']), ('total_cut_m', arrays['source_surface_m'] - arrays['final_surface_m'])):
        _surface_coast_drop_same(arrays[name], cut, 'saved source cut ' + name)
        if _i98_np.any(cut < -1e-09) or _i98_np.any((cut > 1e-09) & (~arrays['domain_mask'] | arrays['protected_mask'])):
            _reject('saved source cut violates domain/protection')
    area_weights = _i98_np.ones(shape)
    area_weights[[0, -1], :] *= 0.5
    area_weights[:, [0, -1]] *= 0.5
    cell_area = fine['spacing_x_m'] * fine['spacing_z_m']

    def check_cut(cut, depth_cap, area_cap, volume_cap):
        if _i98_np.max(cut) > depth_cap + 1e-09 or _i98_np.sum((cut > 1e-09) * area_weights) * cell_area > area_cap + 1e-09 or _i98_np.sum(cut * area_weights) * cell_area > volume_cap + 1e-09:
            _reject('saved upstream cut exceeds original budget')
    budget = proof['inputs']['budget']
    check_cut(arrays['bed_cut_m'], budget['max_bed_cut_m'], budget['max_area_m2'], budget['max_cut_volume_m3'])
    if valley is not None:
        recipe = proof['inputs']['valley_recipe']
        check_cut(arrays['valley_cut_m'], recipe['max_valley_depth_m'], recipe['max_valley_area_m2'], recipe['max_valley_volume_m3'])
        check_cut(arrays['total_cut_m'], float('inf'), recipe['max_total_cut_area_m2'], recipe['max_total_cut_volume_m3'])
    coarse = final['identity']['parameters']
    graph_arrays = final['arrays']
    positions = arrays['world_xz_m']
    graph_count = graph_arrays['source_height_m'].size
    graph_columns = graph_arrays['source_height_m'].shape[1]
    _surface_coast_drop_same(positions[:, 0], coarse['origin_x_m'] + _i98_np.arange(graph_count) % graph_columns * coarse['spacing_x_m'], 'saved graph x')
    _surface_coast_drop_same(positions[:, 1], coarse['origin_z_m'] + _i98_np.arange(graph_count) // graph_columns * coarse['spacing_z_m'], 'saved graph z')
    for name, expected in (('receiver', graph_arrays['receiver']), ('order', graph_arrays['order']), ('discharge_m3_s', graph_arrays['discharge_m3_s'].ravel()), ('active_mask', graph_arrays['channel_mask'].ravel()), ('outlet_mask', graph_arrays['outlet_mask'].ravel()), ('local_discharge_m3_s', final_local)):
        _surface_coast_drop_same(arrays[name], expected, 'saved terminal graph ' + name)
    graph_rows = _i98_np.rint((positions[:, 1] - fine['origin_z_m']) / fine['spacing_z_m']).astype(_i98_np.int64)
    graph_columns_fine = _i98_np.rint((positions[:, 0] - fine['origin_x_m']) / fine['spacing_x_m']).astype(_i98_np.int64)
    active = arrays['active_mask']
    graph_sample = (graph_rows, graph_columns_fine)
    _surface_coast_drop_same(arrays['node_stage_m'], _i98_np.where(active, arrays['water_surface_m'][graph_sample], 0.0), 'saved graph stage from actual wet source')
    if not _i98_np.array_equal(arrays['domain_mask'][graph_sample], domain.ravel()) or not _i98_np.array_equal(arrays['protected_mask'][graph_sample], proof['inputs']['coarse_protected'].ravel()) or _i98_np.any(active & (~domain.ravel() | proof['inputs']['coarse_protected'].ravel())) or (not _i98_np.all(wet[graph_rows[active], graph_columns_fine[active]])) or (not _i98_np.all(arrays['legal_outlet_mask'][graph_rows[active & arrays['outlet_mask']], graph_columns_fine[active & arrays['outlet_mask']]])):
        _reject('saved graph lacks domain/wet/legal terminal support')
    graph_bed = graph_arrays['bounded_bed_m'].ravel()
    if not _i98_np.allclose(arrays['final_surface_m'][graph_rows[active], graph_columns_fine[active]], graph_bed[active], atol=budget['bed_match_tolerance_m'], rtol=0):
        _reject('saved actual graph H2 differs from bounded bed')
    stage_recipe = proof['inputs']['stage_recipe']
    min_depth, max_depth = (stage_recipe['min_clearance_m'], stage_recipe['max_depth_m'])
    node_stage = arrays['node_stage_m']
    preferred = graph_bed + _i98_np.maximum(graph_arrays['nominal_depth_m'].ravel(), min_depth)
    if _i98_np.any(node_stage[active] - graph_bed[active] < min_depth - 1e-09) or _i98_np.any(node_stage[active] - graph_bed[active] > max_depth + 1e-09) or _i98_np.any(node_stage[active] > preferred[active] + stage_recipe['max_lift_above_nominal_m'] + 1e-09):
        _reject('saved graph stage exceeds original depth/lift budget')
    terminals = _i98_np.flatnonzero(active & arrays['outlet_mask'])
    _surface_coast_drop_same(node_stage[terminals], proof['inputs']['outlet_stage_m'], 'original terminal boundary stage')
    for donor in _i98_np.flatnonzero(active & (arrays['receiver'] >= 0)):
        target = int(arrays['receiver'][donor])
        distance = float(_i98_np.linalg.norm(positions[donor] - positions[target]))
        expected_stage = max(preferred[donor], node_stage[target] + stage_recipe['min_stage_slope_m_per_m'] * distance)
        if not active[target] or abs(node_stage[donor] - expected_stage) > 1e-08:
            _reject('saved graph stage equation mismatch')
        step_count = max(abs(graph_rows[target] - graph_rows[donor]), abs(graph_columns_fine[target] - graph_columns_fine[donor]))
        previous_bed = None
        for step in range(step_count + 1):
            fraction = step / step_count
            row = int(round(graph_rows[donor] + fraction * (graph_rows[target] - graph_rows[donor])))
            column = int(round(graph_columns_fine[donor] + fraction * (graph_columns_fine[target] - graph_columns_fine[donor])))
            stage_here = node_stage[donor] * (1 - fraction) + node_stage[target] * fraction
            bed_here = arrays['final_surface_m'][row, column]
            if not wet[row, column] or stage_here - bed_here < min_depth - 1e-09 or stage_here - bed_here > max_depth + 1e-09 or (previous_bed is not None and bed_here > previous_bed + 1e-09):
                _reject('saved graph edge wet/depth/bed continuity mismatch')
            previous_bed = bed_here
    _static_water_support(proof, arrays)
    points = record['cross_section_xz_m']
    _saved_support(indices, weights, points, fine, shape)
    if not _i98_np.allclose(_i98_np.diff(points[:, 0]), fine['spacing_x_m'], rtol=0, atol=1e-10) or not _i98_np.allclose((points[:, 0] - fine['origin_x_m']) / fine['spacing_x_m'], _i98_np.round((points[:, 0] - fine['origin_x_m']) / fine['spacing_x_m']), rtol=0, atol=1e-10) or (not _i98_math.isclose((points[0, 1] - fine['origin_z_m']) / fine['spacing_z_m'], round((points[0, 1] - fine['origin_z_m']) / fine['spacing_z_m']), abs_tol=1e-10)):
        _reject('saved cross-section skips or misaligns fine nodes')
    _support(indices, weights, arrays['domain_mask'], _i98_np.zeros(shape, bool), arrays['protected_mask'], wet)
    center = record['center_index']
    terminal_nodes = _i98_np.flatnonzero(arrays['active_mask'] & arrays['outlet_mask'] & _i98_np.all(_i98_np.isclose(positions, points[center], rtol=0, atol=1e-10), axis=1))
    if len(terminal_nodes) != 1:
        _reject('saved attachment lacks unique actual terminal cut')
    terminal = int(terminal_nodes[0])
    terminal_q = float(arrays['discharge_m3_s'][terminal])
    terminal_stage = float(_i98_np.sum(arrays['water_surface_m'].ravel()[indices[center]] * weights[center]))
    if terminal_q <= 0 or not _i98_np.any(_i98_np.isclose(proof['inputs']['outlet_stage_m'], terminal_stage, rtol=0, atol=1e-08)) or abs(terminal_stage - arrays['node_stage_m'][terminal]) > 1e-08:
        _reject('saved actual terminal stage/Q mismatch')
    return {'h2_m': _i98_np.sum(arrays['final_surface_m'].ravel()[indices] * weights, axis=1), 'water_m': _i98_np.sum(arrays['water_surface_m'].ravel()[indices] * weights, axis=1), 'fine_spacing_x_m': fine['spacing_x_m'], 'terminal_node': terminal, 'terminal_q_m3_s': terminal_q, 'recovery_sha256': proof['identity_sha256']}

def _preflight(attachment, corridor, sea, stations, resources):
    if not isinstance(resources, DropResources):
        _reject('explicit DropResources required')
    DropResources(**_i98_asdict(resources))
    section = attachment['cross_section_xz_m']
    station_count = len(stations)
    vertex_count = station_count * len(section)
    triangle_count = 2 * (station_count - 1) * (len(section) - 1)
    if station_count < 2 or vertex_count > resources.max_vertices or triangle_count > resources.max_triangles or (vertex_count * 12 > resources.max_work):
        _reject('mesh vertex/triangle/work resource cap')
    sources = {'attachment': attachment, 'corridor': corridor, 'sea': sea}
    source_bytes = _retained(sources, resources.max_retained_bytes)
    cells = corridor['h0_m'].size + sea['h0_m'].size
    if cells > resources.max_source_cells:
        _reject('aggregate engineering source cell resource cap')
    prepared = attachment['prepared']
    selected = next((entry for entry in prepared['domains'] if entry['domain_id'] == attachment['domain_id']), None)
    if selected is None or selected['recovery'] is None:
        _reject('selected prepared recovery missing')
    proof_cells = _i98_math.prod(selected['recovery']['inputs']['fine']['shape_zx'])
    if proof_cells > resources.max_source_cells:
        _reject('selected proof support cell resource cap')
    output_bound = vertex_count * 256 + triangle_count * 80 + proof_cells * 320 + MAX_METADATA_BYTES
    if source_bytes + output_bound > resources.max_retained_bytes:
        _reject('retained geometry resource cap')
    return {'vertices': vertex_count, 'triangles': triangle_count, 'work': vertex_count * 12, 'retained_bytes_upper_bound': source_bytes + output_bound}

def _corridor_cells(source, section, stations):
    shape = source['h0_m'].shape
    left = (section[0, 0] - source['origin_x_m']) / source['spacing_x_m']
    right = (section[-1, 0] - source['origin_x_m']) / source['spacing_x_m']
    top = (stations[0] - source['origin_z_m']) / source['spacing_z_m']
    bottom = (stations[-1] - source['origin_z_m']) / source['spacing_z_m']
    if left < 0 or top < 0 or right > shape[1] - 1 or (bottom > shape[0] - 1):
        _reject('corridor rectangle coverage gap')
    columns = _i98_np.arange(_i98_math.floor(left), _i98_math.ceil(right) + 1)
    rows = _i98_np.arange(_i98_math.floor(top), _i98_math.ceil(bottom) + 1)
    indices = (rows[:, None] * shape[1] + columns).ravel().astype(_i98_np.int64)
    for name, expected, reason in (('valid_mask', True, 'invalid interior corridor support'), ('unknown_mask', False, 'unknown interior corridor support'), ('protected_mask', False, 'protected interior corridor support'), ('wet_mask', True, 'nonwet interior corridor support')):
        if _i98_np.any(source[name].ravel()[indices] != expected):
            _reject(reason)
    return indices

def _aligned_sources(corridor, sea, section, stations, fine_spacing):
    if not _i98_math.isclose(corridor['spacing_x_m'], fine_spacing, rel_tol=0, abs_tol=1e-10) or not _i98_math.isclose(sea['spacing_x_m'], fine_spacing, rel_tol=0, abs_tol=1e-10) or (not _i98_np.allclose(_i98_np.diff(section[:, 0]), fine_spacing, rtol=0, atol=1e-10)) or (not _i98_np.allclose(_i98_np.diff(stations), corridor['spacing_z_m'], rtol=0, atol=1e-10)):
        _reject('no skipped source cells: exact fine/corridor/sea spacing required')
    for source, points in ((corridor, section), (sea, _i98_np.column_stack((section[:, 0], _i98_np.full(len(section), stations[-1]))))):
        columns = (points[:, 0] - source['origin_x_m']) / source['spacing_x_m']
        rows = (points[:, 1] - source['origin_z_m']) / source['spacing_z_m']
        if not _i98_np.allclose(columns, _i98_np.round(columns), rtol=0, atol=1e-10) or not _i98_np.allclose(rows, _i98_np.round(rows), rtol=0, atol=1e-10):
            _reject('aligned source nodes required; no subcell geometry claims')

def _source_triangles(corridor, xz, triangles):
    columns = _i98_np.rint((xz[:, 0] - corridor['origin_x_m']) / corridor['spacing_x_m']).astype(_i98_np.int64)
    rows = _i98_np.rint((xz[:, 1] - corridor['origin_z_m']) / corridor['spacing_z_m']).astype(_i98_np.int64)
    return (rows * corridor['h0_m'].shape[1] + columns)[triangles]

def _triangles(rows, columns):
    triangles = _i98_np.empty((2 * (rows - 1) * (columns - 1), 3), dtype=_i98_np.int64)
    offset = 0
    for row in range(rows - 1):
        for column in range(columns - 1):
            first = row * columns + column
            triangles[offset] = [first, first + 1, first + columns]
            triangles[offset + 1] = [first + 1, first + columns + 1, first + columns]
            offset += 2
    return triangles

def _mesh_gate(bed_xyz, water_xyz, triangles):
    if not _i98_np.all(_i98_np.isfinite(bed_xyz)) or not _i98_np.all(_i98_np.isfinite(water_xyz)):
        _reject('nonfinite output mesh')
    if _i98_np.any(water_xyz[:, 1] <= bed_xyz[:, 1]):
        _reject('strip must have positive full-width water depth')
    if len(_i98_np.unique(bed_xyz[:, [0, 2]], axis=0)) != len(bed_xyz):
        _reject('duplicate strip vertices')
    for vertices in (bed_xyz, water_xyz):
        corners = vertices[triangles]
        areas = _i98_np.linalg.norm(_i98_np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]), axis=1)
        if _i98_np.any(areas <= 1e-12):
            _reject('degenerate strip triangle')
    if len(_i98_np.unique(triangles)) != len(bed_xyz):
        _reject('unused or disconnected strip vertices')

def _budget_ledger(h0, h2, xz, triangles, budget):
    cut = h0 - h2
    if _i98_np.any(cut < -1e-10):
        _reject('negative engineering cut')
    corners = xz[triangles]
    difference_first = corners[:, 1] - corners[:, 0]
    difference_second = corners[:, 2] - corners[:, 0]
    plan_area = 0.5 * _i98_np.abs(difference_first[:, 0] * difference_second[:, 1] - difference_first[:, 1] * difference_second[:, 0])
    volume = float(_i98_np.sum(plan_area * _i98_np.mean(cut[triangles], axis=1)))
    max_cut = float(_i98_np.max(cut))
    if max_cut > budget.max_cut_depth_m + 1e-10 or volume > budget.max_cut_volume_m3 + 1e-10:
        _reject('explicit original cut depth/volume budget exceeded')
    return {'cut_m': cut, 'triangle_plan_area_m2': plan_area, 'max_cut_depth_m': max_cut, 'cut_volume_m3': volume, 'semantics': 'new_strip_H0_minus_H2_piecewise_linear_prism_no_old_recut'}

def prepare_coast_drop(attachment, corridor, sea, stations_z_m, budget, *, resources=DropResources()):
    """Explicit construction only. Rejection publishes no partial geometry."""
    if not isinstance(attachment, RiverAttachment) or not isinstance(budget, DropBudget):
        _reject('explicit RiverAttachment and original DropBudget required')
    stations = _i98_np.asarray(stations_z_m)
    if stations.ndim != 1 or stations.dtype.kind not in 'fiu' or (not _i98_np.all(_i98_np.isfinite(stations))):
        _reject('explicit finite station vector required')
    attachment_record = {name: getattr(attachment, name) for name in attachment.__dataclass_fields__}
    corridor_record, sea_record = (_source_record(corridor), _source_record(sea))
    usage = _preflight(attachment_record, corridor_record, sea_record, stations, resources)
    _check_source(corridor_record, 'corridor', attachment.datum, resources)
    _check_source(sea_record, 'sea', attachment.datum, resources)
    if stations[0] != attachment.cross_section_xz_m[0, 1] or _i98_np.any(_i98_np.diff(stations) <= 0):
        _reject('stations must begin at actual endpoint and increase strictly')
    upstream = _attachment(attachment_record)
    section = attachment.cross_section_xz_m
    if sea.sea_level_m >= upstream['water_m'][attachment.center_index]:
        _reject('sea level must be below actual river center stage')
    if corridor.sea_level_m != sea.sea_level_m:
        _reject('corridor and sea level disagree')
    _aligned_sources(corridor_record, sea_record, section, stations, upstream['fine_spacing_x_m'])
    if _i98_np.min(_i98_np.diff(section[:, 0])) + 1e-10 < max(corridor.spacing_x_m, sea.spacing_x_m) or _i98_np.min(_i98_np.diff(stations)) + 1e-10 < corridor.spacing_z_m:
        _reject('mesh resolution unsupported by explicit sources')
    xz = _i98_np.column_stack((_i98_np.tile(section[:, 0], len(stations)), _i98_np.repeat(stations, len(section))))
    corridor_indices, corridor_weights = _stencil(corridor_record, xz, corridor.h0_m.shape)
    _support(corridor_indices, corridor_weights, corridor.valid_mask, corridor.unknown_mask, corridor.protected_mask, corridor.wet_mask)
    corridor_cells = _corridor_cells(corridor_record, section, stations)
    sea_points = xz[-len(section):]
    sea_indices, sea_weights = _stencil(sea_record, sea_points, sea.h0_m.shape)
    _support(sea_indices, sea_weights, sea.valid_mask, sea.unknown_mask, sea.protected_mask, sea.wet_mask, sea.ocean_mask)
    sea_bed = _surface_coast_drop_sample(sea.h2_m, sea_indices, sea_weights)
    sea_water = _surface_coast_drop_sample(sea.water_m, sea_indices, sea_weights)
    if not _i98_np.allclose(sea_water, sea.sea_level_m, rtol=0, atol=1e-10):
        _reject('sea source water differs from sea level')
    fraction = (stations - stations[0]) / (stations[-1] - stations[0])
    bed = ((1 - fraction[:, None]) * upstream['h2_m'] + fraction[:, None] * sea_bed).ravel()
    water = ((1 - fraction[:, None]) * upstream['water_m'] + fraction[:, None] * sea_water).ravel()
    supported_bed = _surface_coast_drop_sample(corridor.h2_m, corridor_indices, corridor_weights)
    supported_water = _surface_coast_drop_sample(corridor.water_m, corridor_indices, corridor_weights)
    if not _i98_np.allclose(bed, supported_bed, rtol=0, atol=1e-09) or not _i98_np.allclose(water, supported_water, rtol=0, atol=1e-09):
        _reject('explicit corridor H2/water does not support endpoint interpolation')
    h0 = _surface_coast_drop_sample(corridor.h0_m, corridor_indices, corridor_weights)
    triangles = _triangles(len(stations), len(section))
    source_triangles = _source_triangles(corridor_record, xz, triangles)
    bed_xyz = _i98_np.column_stack((xz[:, 0], bed, xz[:, 1]))
    water_xyz = _i98_np.column_stack((xz[:, 0], water, xz[:, 1]))
    _mesh_gate(bed_xyz, water_xyz, triangles)
    ledger = _budget_ledger(h0, bed, xz, triangles, budget)
    center_indices = _i98_np.arange(len(stations)) * len(section) + attachment.center_index
    result = {'algorithm': SURFACE_COAST_DROP_VERSION, 'mode': MODE, 'status': 'prepared', 'natural_outlet_certified': False, 'inputs': {'attachment': attachment_record, 'corridor': corridor_record, 'sea': sea_record, 'stations_z_m': stations.astype('<f8'), 'budget': _i98_asdict(budget), 'resources': _i98_asdict(resources)}, 'arrays': {'bed_xyz_m': bed_xyz, 'water_xyz_m': water_xyz, 'triangles': triangles, 'h0_m': h0, 'centerline_xyz_m': water_xyz[center_indices], 'corridor_indices': corridor_indices, 'corridor_weights': corridor_weights, 'sea_indices': sea_indices, 'sea_weights': sea_weights, 'river_indices': upstream['indices'], 'river_weights': upstream['weights']}, 'attachment': {'recovery_sha256': upstream['recovery_sha256'], 'terminal_node': upstream['terminal_node'], 'terminal_q_m3_s': upstream['terminal_q_m3_s'], 'river_bed_xyz_m': bed_xyz[:len(section)], 'river_water_xyz_m': water_xyz[:len(section)], 'sea_bed_xyz_m': bed_xyz[-len(section):], 'sea_water_xyz_m': water_xyz[-len(section):]}, 'ledger': ledger, 'usage': usage, 'proof_support': upstream['proof_support']}
    result['arrays']['corridor_support_cells'] = corridor_cells
    result['arrays']['corridor_source_triangles'] = source_triangles
    _retained(result, resources.max_retained_bytes)
    result['identity_sha256'] = fingerprint(result)
    frozen = _freeze(result)
    validate_coast_drop(frozen)
    return frozen

def _surface_coast_drop_same(actual, expected, name):
    if _i98_np.asarray(actual).shape != _i98_np.asarray(expected).shape or not _i98_np.allclose(actual, expected, rtol=0, atol=1e-09):
        _reject('static coast proof mismatch: ' + name)

def validate_coast_drop(result):
    """Read saved geometry and source equations; never invoke construction/recovery."""
    if not isinstance(result, _i98_Mapping):
        _reject('saved coast product required')
    required = {'algorithm', 'mode', 'status', 'natural_outlet_certified', 'inputs', 'arrays', 'attachment', 'ledger', 'usage', 'identity_sha256', 'proof_support'}
    if set(result) != required or result['algorithm'] != SURFACE_COAST_DROP_VERSION or result['mode'] != MODE:
        _reject('coast product schema/version mismatch')
    if result['status'] != 'prepared' or result['natural_outlet_certified'] is not False:
        _reject('only engineered prepared coast geometry is supported')
    inputs = result['inputs']
    if set(inputs) != {'attachment', 'corridor', 'sea', 'stations_z_m', 'budget', 'resources'}:
        _reject('coast input schema mismatch')
    resources = DropResources(**inputs['resources'])
    budget = DropBudget(**inputs['budget'])
    _retained(result, resources.max_retained_bytes)
    attachment = inputs['attachment']
    if set(attachment) != set(RiverAttachment.__dataclass_fields__):
        _reject('attachment schema mismatch')
    RiverAttachment(**attachment)
    corridor, sea = (inputs['corridor'], inputs['sea'])
    stations = inputs['stations_z_m']
    if not isinstance(stations, _i98_np.ndarray) or stations.ndim != 1 or stations.dtype.kind not in 'fiu' or (not _i98_np.all(_i98_np.isfinite(stations))):
        _reject('invalid saved station vector')
    usage = _preflight(attachment, corridor, sea, stations, resources)
    if dict(result['usage']) != usage:
        _reject('saved resource usage mismatch')
    _check_source(corridor, 'corridor', attachment['datum'], resources)
    _check_source(sea, 'sea', attachment['datum'], resources)
    if result['identity_sha256'] != fingerprint({key: value for key, value in result.items() if key != 'identity_sha256'}):
        _reject('coast product identity mismatch')
    section = attachment['cross_section_xz_m']
    center = attachment['center_index']
    rows, columns = (len(stations), len(section))
    if stations[0] != section[0, 1] or _i98_np.any(_i98_np.diff(stations) <= 0):
        _reject('invalid saved station origin/order')
    if _i98_np.min(_i98_np.diff(section[:, 0])) + 1e-10 < max(corridor['spacing_x_m'], sea['spacing_x_m']) or _i98_np.min(_i98_np.diff(stations)) + 1e-10 < corridor['spacing_z_m']:
        _reject('saved mesh exceeds source precision')
    upstream = _static_attachment(attachment, result['proof_support'], result['arrays']['river_indices'], result['arrays']['river_weights'])
    _aligned_sources(corridor, sea, section, stations, upstream['fine_spacing_x_m'])
    if sea['sea_level_m'] >= upstream['water_m'][center] or corridor['sea_level_m'] != sea['sea_level_m']:
        _reject('unsupported high or inconsistent sea level')
    arrays = result['arrays']
    array_keys = {'bed_xyz_m', 'water_xyz_m', 'triangles', 'h0_m', 'centerline_xyz_m', 'corridor_indices', 'corridor_weights', 'sea_indices', 'sea_weights', 'river_indices', 'river_weights', 'corridor_support_cells', 'corridor_source_triangles'}
    if set(arrays) != array_keys:
        _reject('mesh array members mismatch')
    for name, array in arrays.items():
        if not isinstance(array, _i98_np.ndarray) or array.flags.writeable or array.dtype.kind not in 'fiu' or (not _i98_np.all(_i98_np.isfinite(array))):
            _reject('saved output array must be immutable finite numeric: ' + name)
    bed_xyz, water_xyz, triangles = (arrays['bed_xyz_m'], arrays['water_xyz_m'], arrays['triangles'])
    if bed_xyz.shape != (rows * columns, 3) or water_xyz.shape != bed_xyz.shape or triangles.shape != (2 * (rows - 1) * (columns - 1), 3) or (triangles.dtype.kind not in 'iu'):
        _reject('saved mesh shapes/dtype mismatch')
    xz = bed_xyz[:, [0, 2]]
    _surface_coast_drop_same(xz[:, 0], _i98_np.tile(section[:, 0], rows), 'world x')
    _surface_coast_drop_same(xz[:, 1], _i98_np.repeat(stations, columns), 'world z')
    _surface_coast_drop_same(water_xyz[:, [0, 2]], xz, 'bed/water planar registration')
    offset = 0
    for row in range(rows - 1):
        for column in range(columns - 1):
            first = row * columns + column
            if not _i98_np.array_equal(triangles[offset], [first, first + 1, first + columns]) or not _i98_np.array_equal(triangles[offset + 1], [first + 1, first + columns + 1, first + columns]):
                _reject('saved triangles not connected strip topology')
            offset += 2
    _surface_coast_drop_same(bed_xyz[:columns, 1], upstream['h2_m'], 'actual full-width river H2')
    _surface_coast_drop_same(water_xyz[:columns, 1], upstream['water_m'], 'actual transverse river stage')
    for role, points in (('corridor', xz), ('sea', xz[-columns:])):
        source = inputs[role]
        indices, weights = (arrays[role + '_indices'], arrays[role + '_weights'])
        _saved_support(indices, weights, points, source, source['h0_m'].shape)
        _support(indices, weights, source['valid_mask'], source['unknown_mask'], source['protected_mask'], source['wet_mask'], source['ocean_mask'] if role == 'sea' else None)
        saved_bed = bed_xyz[:, 1] if role == 'corridor' else bed_xyz[-columns:, 1]
        saved_water = water_xyz[:, 1] if role == 'corridor' else water_xyz[-columns:, 1]
        _surface_coast_drop_same(saved_bed, _i98_np.sum(source['h2_m'].ravel()[indices] * weights, axis=1), role + ' explicit H2')
        _surface_coast_drop_same(saved_water, _i98_np.sum(source['water_m'].ravel()[indices] * weights, axis=1), role + ' explicit water')
    support_cells = arrays['corridor_support_cells']
    saved_indices = arrays['corridor_indices'][:, 0]
    if not _i98_np.array_equal(support_cells, saved_indices) or len(_i98_np.unique(support_cells)) != rows * columns:
        _reject('saved full-strip source cell/node ownership differs')
    _support(support_cells[:, None], _i98_np.ones((len(support_cells), 1)), corridor['valid_mask'], corridor['unknown_mask'], corridor['protected_mask'], corridor['wet_mask'])
    source_triangles = arrays['corridor_source_triangles']
    if source_triangles.dtype.kind not in 'iu' or not _i98_np.array_equal(source_triangles, saved_indices[triangles]):
        _reject('saved source triangle mapping differs from full strip')
    for name, source_name, mesh_values in (('H0', 'h0_m', arrays['h0_m']), ('H2', 'h2_m', bed_xyz[:, 1]), ('water', 'water_m', water_xyz[:, 1])):
        _surface_coast_drop_same(mesh_values[triangles], corridor[source_name].ravel()[source_triangles], 'full triangle affine source ' + name)
    _surface_coast_drop_same(water_xyz[-columns:, 1], _i98_np.full(columns, sea['sea_level_m']), 'sea level attachment')
    fraction = (stations - stations[0]) / (stations[-1] - stations[0])
    _surface_coast_drop_same(bed_xyz[:, 1].reshape(rows, columns), (1 - fraction[:, None]) * bed_xyz[:columns, 1] + fraction[:, None] * bed_xyz[-columns:, 1], 'longitudinal bed continuity')
    _surface_coast_drop_same(water_xyz[:, 1].reshape(rows, columns), (1 - fraction[:, None]) * water_xyz[:columns, 1] + fraction[:, None] * water_xyz[-columns:, 1], 'longitudinal stage continuity')
    _surface_coast_drop_same(arrays['centerline_xyz_m'], water_xyz[_i98_np.arange(rows) * columns + center], 'centerline XYZ')
    _surface_coast_drop_same(arrays['h0_m'], _i98_np.sum(corridor['h0_m'].ravel()[arrays['corridor_indices']] * arrays['corridor_weights'], axis=1), 'corridor H0')
    _mesh_gate(bed_xyz, water_xyz, triangles)
    expected_ledger = _budget_ledger(arrays['h0_m'], bed_xyz[:, 1], xz, triangles, budget)
    if set(result['ledger']) != set(expected_ledger):
        _reject('ledger schema mismatch')
    for name, expected in expected_ledger.items():
        if isinstance(expected, str):
            if result['ledger'][name] != expected:
                _reject('ledger semantics mismatch')
        else:
            _surface_coast_drop_same(result['ledger'][name], expected, 'cut ledger ' + name)
    attach_output = result['attachment']
    expected_attachment = {'recovery_sha256': upstream['recovery_sha256'], 'terminal_node': upstream['terminal_node'], 'terminal_q_m3_s': upstream['terminal_q_m3_s'], 'river_bed_xyz_m': bed_xyz[:columns], 'river_water_xyz_m': water_xyz[:columns], 'sea_bed_xyz_m': bed_xyz[-columns:], 'sea_water_xyz_m': water_xyz[-columns:]}
    if set(attach_output) != set(expected_attachment):
        _reject('saved full-width attachment schema mismatch')
    for name, expected in expected_attachment.items():
        if isinstance(expected, str):
            if attach_output[name] != expected:
                _reject('saved recovery identity mismatch')
        else:
            _surface_coast_drop_same(attach_output[name], expected, 'attachment ' + name)
    return {'valid': True, 'identity_sha256': result['identity_sha256'], 'static_sources_and_geometry_verified': True, 'terminal_q_m3_s': upstream['terminal_q_m3_s'], 'natural_outlet_certified': False}

def query_coast_drop(result):
    """Generation-free immutable view after static proof."""
    validate_coast_drop(result)
    return _freeze({'arrays': result['arrays'], 'attachment': result['attachment'], 'ledger': result['ledger']})

def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject('duplicate coast JSON key')
        result[key] = value
    return result

def _constant(value):
    _reject('nonfinite coast JSON constant')

def save_coast_drop(result, path):
    validate_coast_drop(result)
    path = _i98_Path(path)
    if path.exists():
        raise FileExistsError(path)
    arrays = {}
    tree = _tree(result, arrays)
    metadata = _json({'format': SURFACE_COAST_DROP_VERSION + '-npy-v1', 'tree': tree}).encode('ascii')
    if len(arrays) + 1 > MAX_MEMBERS or len(metadata) > MAX_METADATA_BYTES:
        _reject('save member/metadata cap')
    descriptor, temporary = _i98_tempfile.mkstemp(prefix='.coast-drop-', dir=path.parent)
    try:
        stream = _i98_os.fdopen(descriptor, 'w+b')
        descriptor = None
        with stream:
            with _i98_zipfile.ZipFile(stream, 'w', compression=_i98_zipfile.ZIP_STORED) as archive:
                archive.writestr('metadata.json', metadata)
                for name, array in arrays.items():
                    with archive.open(name, 'w') as member:
                        _i98_np.lib.format.write_array(member, array, version=(1, 0), allow_pickle=False)
            if stream.tell() > MAX_BYTES:
                _reject('bundle file cap')
            stream.flush()
            _i98_os.fsync(stream.fileno())
        _i98_os.link(temporary, path)
    finally:
        if descriptor is not None:
            _i98_os.close(descriptor)
        _i98_os.unlink(temporary)
    return path

def _read_header(stream, info, spec):
    if _i98_np.lib.format.read_magic(stream) != (1, 0):
        _reject('only coast NPY v1 supported')
    length_bytes = stream.read(2)
    if len(length_bytes) != 2 or int.from_bytes(length_bytes, 'little') > MAX_HEADER_BYTES - 10:
        _reject('coast NPY header cap')
    header_length = int.from_bytes(length_bytes, 'little')
    header = stream.read(header_length)
    if len(header) != header_length:
        _reject('truncated coast header')
    shape, fortran, dtype = _i98_np.lib.format.read_array_header_1_0(_i98_io.BytesIO(length_bytes + header), max_header_size=MAX_HEADER_BYTES)
    payload_bytes = _i98_math.prod(shape) * dtype.itemsize
    if list(shape) != spec['shape'] or dtype.str != spec['dtype'] or dtype.kind not in 'bifu' or fortran or (payload_bytes + stream.tell() != info.file_size) or (payload_bytes > MAX_BYTES):
        _reject('coast header/dtype/exact payload mismatch')
    return (shape, dtype, payload_bytes)

def load_coast_drop(path):
    """Strict bounded static load; no prepare/recover/mesh generator invocation."""
    try:
        with _i98_Path(path).open('rb') as file:
            if _i98_os.fstat(file.fileno()).st_size > MAX_BYTES:
                _reject('coast file resource cap')
            with _i98_zipfile.ZipFile(file) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if len(infos) > MAX_MEMBERS or len(names) != len(set(names)) or any((info.compress_type != _i98_zipfile.ZIP_STORED or info.flag_bits & 1 for info in infos)) or (sum((info.file_size for info in infos)) > MAX_BYTES):
                    _reject('archive duplicate/member/payload cap or unsupported compression')
                if 'metadata.json' not in names or archive.getinfo('metadata.json').file_size > MAX_METADATA_BYTES:
                    _reject('coast metadata missing or resource cap')
                metadata = _i98_json.loads(archive.read('metadata.json'), object_pairs_hook=_pairs, parse_constant=_constant)
                if set(metadata) != {'format', 'tree'} or metadata['format'] != SURFACE_COAST_DROP_VERSION + '-npy-v1':
                    _reject('coast metadata format/schema mismatch')
                specs = {}

                def inspect(value, depth=0):
                    if depth > 40:
                        _reject('coast metadata nesting cap')
                    if isinstance(value, dict) and '$array' in value:
                        if set(value) != {'$array', 'shape', 'dtype', 'sha256'}:
                            _reject('invalid saved array reference')
                        name = value['$array']
                        shape = value['shape']
                        if not isinstance(name, str) or name in specs or '/' in name or ('\\' in name) or (not name.startswith('array_')) or (not name.endswith('.npy')) or (not isinstance(shape, list)) or (len(shape) > 4) or any((type(size) is not int or size < 0 or size > 1000000 for size in shape)) or (_i98_math.prod(shape) > 1000000):
                            _reject('saved array dimensions/name cap')
                        dtype = _i98_np.dtype(value['dtype'])
                        if dtype.kind not in 'bifu' or dtype.itemsize > 8 or _i98_math.prod(shape) * dtype.itemsize > MAX_BYTES:
                            _reject('saved array dtype/payload cap')
                        specs[name] = value
                    elif isinstance(value, dict):
                        for child in value.values():
                            inspect(child, depth + 1)
                    elif isinstance(value, list):
                        for child in value:
                            inspect(child, depth + 1)
                inspect(metadata['tree'])
                if set(names) != {'metadata.json'} | set(specs):
                    _reject('missing/unexpected coast members')
                saved_inputs = metadata['tree']['inputs']
                resource_record = saved_inputs['resources']
                resources = DropResources(**resource_record)
                if sum((_i98_math.prod(spec['shape']) * _i98_np.dtype(spec['dtype']).itemsize for spec in specs.values())) > resources.max_retained_bytes:
                    _reject('saved original retained cap before payload allocation')
                vertex_count = metadata['tree']['arrays']['bed_xyz_m']['shape'][0]
                triangle_count = metadata['tree']['arrays']['triangles']['shape'][0]
                if vertex_count > resources.max_vertices or triangle_count > resources.max_triangles or vertex_count * 12 > resources.max_work or (sum((_i98_math.prod(saved_inputs[role]['h0_m']['shape']) for role in ('corridor', 'sea'))) > resources.max_source_cells):
                    _reject('saved original mesh/source resource cap before allocation')
                payload_total = 0
                for name, spec in specs.items():
                    with archive.open(name) as stream:
                        _, _, size = _read_header(stream, archive.getinfo(name), spec)
                        payload_total += size
                if payload_total > MAX_BYTES:
                    _reject('aggregate coast array cap')
                arrays = {}
                for name, spec in specs.items():
                    with archive.open(name) as stream:
                        shape, dtype, size = _read_header(stream, archive.getinfo(name), spec)
                        payload = stream.read(size + 1)
                        if len(payload) != size:
                            _reject('coast truncated or trailing payload')
                        array = _i98_np.frombuffer(payload, dtype=dtype).reshape(shape)
                        if _array_hash(array) != spec['sha256']:
                            _reject('saved coast array hash mismatch')
                        arrays[name] = array

        def decode(value):
            if isinstance(value, dict) and '$array' in value:
                return arrays[value['$array']]
            if isinstance(value, dict):
                return {key: decode(child) for key, child in value.items()}
            if isinstance(value, list):
                return [decode(child) for child in value]
            return value
        result = _freeze(decode(metadata['tree']))
        validate_coast_drop(result)
        return result
    except (OSError, KeyError, TypeError, RecursionError, _i98_zipfile.BadZipFile, _i98_json.JSONDecodeError) as error:
        raise _make_coast_drop_error('invalid coast bundle') from error
SURFACE_CROSS_DOMAIN_VERSION = 'surface-cross-domain-v1'
TOLERANCE_M = 1e-09

def _number(value, name):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be finite')
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{name} must be finite') from None
    if number != number or abs(number) == float('inf'):
        raise ValueError(f'{name} must be finite')
    return number

def _integer(value, name):
    number = _number(value, name)
    rounded = round(number)
    if abs(number - rounded) > TOLERANCE_M:
        raise ValueError(f'{name} must be integer aligned')
    return int(rounded)

def _coordinate_key(x, z):
    try:
        return (_i99_Decimal(str(x)).normalize(), _i99_Decimal(str(z)).normalize())
    except (_i99_InvalidOperation, ValueError):
        raise ValueError('node coordinate is not finite') from None

def _segment_parts(start, end, finest_x, finest_z, tolerance):
    start_x, start_z = start
    end_x, end_z = end
    delta_x = end_x - start_x
    delta_z = end_z - start_z
    if abs(delta_x) > tolerance and abs(delta_z) > tolerance:
        raise ValueError('cross-domain edges must be axis aligned')
    length = abs(delta_x) + abs(delta_z)
    if length <= tolerance:
        raise ValueError('edge has zero length')
    spacing = finest_x if abs(delta_x) > tolerance else finest_z
    steps = length / spacing
    if abs(steps - round(steps)) > tolerance:
        raise ValueError('edge endpoints are not aligned to finest grid')
    steps = int(round(steps))
    for index in range(steps):
        fraction_start = index / steps
        fraction_end = (index + 1) / steps
        first = (start_x + delta_x * fraction_start, start_z + delta_z * fraction_start)
        second = (start_x + delta_x * fraction_end, start_z + delta_z * fraction_end)
        yield (_coordinate_key(*first), _coordinate_key(*second), 1.0 / steps)

def _normalise_domain(domain):
    if not isinstance(domain, dict) or set(domain) != {'domain_id', 'grid', 'nodes', 'edges'}:
        raise ValueError('domain requires domain_id, grid, nodes and edges')
    domain_id = domain['domain_id']
    if not isinstance(domain_id, str) or not domain_id:
        raise ValueError('domain_id must be a non-empty string')
    grid = domain['grid']
    if not isinstance(grid, dict) or set(grid) != {'origin_x_m', 'origin_z_m', 'spacing_x_m', 'spacing_z_m', 'lod'}:
        raise ValueError('grid requires origin, spacing and lod')
    origin_x = _number(grid['origin_x_m'], 'origin_x_m')
    origin_z = _number(grid['origin_z_m'], 'origin_z_m')
    spacing_x = _number(grid['spacing_x_m'], 'spacing_x_m')
    spacing_z = _number(grid['spacing_z_m'], 'spacing_z_m')
    lod = _integer(grid['lod'], 'lod')
    if spacing_x <= 0 or spacing_z <= 0 or lod < 0:
        raise ValueError('grid spacing and lod must be positive')
    nodes = []
    seen_local = set()
    for raw in domain['nodes']:
        if not isinstance(raw, dict) or set(raw) != {'local_id', 'x_m', 'z_m', 'h0_m', 'unknown', 'protected', 'water_surface_m'}:
            raise ValueError('node fields are incomplete')
        local_id = _integer(raw['local_id'], 'local_id')
        if local_id in seen_local:
            raise ValueError('duplicate local node id')
        seen_local.add(local_id)
        x = _number(raw['x_m'], 'x_m')
        z = _number(raw['z_m'], 'z_m')
        h0 = _number(raw['h0_m'], 'h0_m')
        if type(raw['unknown']) is not bool or type(raw['protected']) is not bool:
            raise ValueError('unknown/protected must be boolean')
        water = raw['water_surface_m']
        if water is not None:
            water = _number(water, 'water_surface_m')
        nodes.append({'local_id': local_id, 'x_m': x, 'z_m': z, 'h0_m': h0, 'unknown': raw['unknown'], 'protected': raw['protected'], 'water_surface_m': water})
    local_ids = {node['local_id'] for node in nodes}
    edges = []
    seen_edges = set()
    for raw in domain['edges']:
        allowed = {'local_id', 'start', 'end', 'flux_m3_s', 'boundary', 'evidence'}
        if not isinstance(raw, dict) or not {'local_id', 'start', 'end', 'flux_m3_s', 'boundary'} <= set(raw) or set(raw) - allowed:
            raise ValueError('edge fields are incomplete')
        edge_id = _integer(raw['local_id'], 'edge local_id')
        start = _integer(raw['start'], 'edge start')
        end = _integer(raw['end'], 'edge end')
        if edge_id in seen_edges or start == end or start not in local_ids or (end not in local_ids):
            raise ValueError('invalid or duplicate local edge')
        seen_edges.add(edge_id)
        if type(raw['boundary']) is not bool:
            raise ValueError('edge boundary must be boolean')
        evidence = raw.get('evidence')
        if evidence is not None and (not isinstance(evidence, dict) or not isinstance(evidence.get('adapter_version'), str) or (not isinstance(evidence.get('face_index'), int))):
            raise ValueError('invalid edge evidence')
        edges.append({'local_id': edge_id, 'start': start, 'end': end, 'flux_m3_s': _number(raw['flux_m3_s'], 'flux_m3_s'), 'boundary': raw['boundary'], 'evidence': evidence})
    return {'domain_id': domain_id, 'grid': {'origin_x_m': origin_x, 'origin_z_m': origin_z, 'spacing_x_m': spacing_x, 'spacing_z_m': spacing_z, 'lod': lod}, 'nodes': nodes, 'edges': edges}

def audit_cross_domain(domains, *, tolerance=TOLERANCE_M):
    """Audit saved domain records without generating geometry, routing or water."""
    if not isinstance(domains, (list, tuple)) or not domains:
        raise ValueError('at least one domain is required')
    if type(tolerance) is not float or not 0 < tolerance < float('inf'):
        raise ValueError('tolerance must be positive float')
    normalised = [_normalise_domain(domain) for domain in domains]
    if len({domain['domain_id'] for domain in normalised}) != len(normalised):
        raise ValueError('domain IDs must be unique')
    finest_x = min((domain['grid']['spacing_x_m'] for domain in normalised))
    finest_z = min((domain['grid']['spacing_z_m'] for domain in normalised))
    base_x = min((node['x_m'] for domain in normalised for node in domain['nodes']))
    base_z = min((node['z_m'] for domain in normalised for node in domain['nodes']))
    for domain in normalised:
        grid = domain['grid']
        for axis, spacing, base in (('x', grid['spacing_x_m'], base_x), ('z', grid['spacing_z_m'], base_z)):
            ratio = spacing / (finest_x if axis == 'x' else finest_z)
            if abs(ratio - round(ratio)) > tolerance:
                raise ValueError('spacing is not aligned to finest grid')
            offset = (grid[f'origin_{axis}_m'] - base) / (finest_x if axis == 'x' else finest_z)
            if abs(offset - round(offset)) > tolerance:
                raise ValueError('domain origin is not aligned to finest grid')
    global_nodes = {}
    for domain in normalised:
        grid = domain['grid']
        for node in domain['nodes']:
            key = _coordinate_key(node['x_m'], node['z_m'])
            expected_x = grid['origin_x_m'] + round((node['x_m'] - grid['origin_x_m']) / grid['spacing_x_m']) * grid['spacing_x_m']
            expected_z = grid['origin_z_m'] + round((node['z_m'] - grid['origin_z_m']) / grid['spacing_z_m']) * grid['spacing_z_m']
            if abs(node['x_m'] - expected_x) > tolerance or abs(node['z_m'] - expected_z) > tolerance:
                raise ValueError('node is not on its declared grid')
            global_nodes.setdefault(key, {'x_m': node['x_m'], 'z_m': node['z_m'], 'members': []})['members'].append((domain['domain_id'], node))
    ordered_keys = sorted(global_nodes)
    node_ids = {key: 'n:' + _i99_hashlib.sha256((str(key[0]) + ':' + str(key[1])).encode()).hexdigest() for key in ordered_keys}
    shared_nodes = []
    barriers = []
    water_conflicts = []
    for key in ordered_keys:
        record = global_nodes[key]
        members = record['members']
        if len(members) > 1:
            reference = members[0][1]
            for domain_id, node in members[1:]:
                if abs(node['h0_m'] - reference['h0_m']) > tolerance or node['unknown'] != reference['unknown'] or node['protected'] != reference['protected']:
                    raise ValueError('shared node H0 or barrier mismatch')
                if reference['water_surface_m'] is not None and node['water_surface_m'] is not None and (abs(node['water_surface_m'] - reference['water_surface_m']) > tolerance):
                    water_conflicts.append({'node_id': node_ids[key], 'domains': [members[0][0], domain_id]})
            shared_nodes.append(node_ids[key])
        if any((node['unknown'] or node['protected'] for _, node in members)):
            barriers.append(node_ids[key])
    if water_conflicts:
        raise ValueError('shared node water surface mismatch')
    edge_records = {}
    boundary_flux = 0.0
    internal_evidence_edges = 0
    shared_edges = []
    internal_flux_residual = 0.0
    for domain in normalised:
        by_id = {node['local_id']: node for node in domain['nodes']}
        for edge in domain['edges']:
            start = (by_id[edge['start']]['x_m'], by_id[edge['start']]['z_m'])
            end = (by_id[edge['end']]['x_m'], by_id[edge['end']]['z_m'])
            parts = tuple(_segment_parts(start, end, finest_x, finest_z, tolerance))
            for start_key, end_key, fraction in parts:
                start_id = node_ids.get(start_key)
                end_id = node_ids.get(end_key)
                if start_id is None or end_id is None:
                    raise ValueError('edge split point is missing from domain node registry')
                if (start_id in barriers or end_id in barriers) and abs(edge['flux_m3_s'] * fraction) > tolerance:
                    raise ValueError('nonzero flux crosses unknown/protected barrier')
                key = tuple(sorted((start_id, end_id)))
                directed = (start_id, end_id)
                record = edge_records.setdefault(key, [])
                record.append((domain['domain_id'], directed, edge['flux_m3_s'] * fraction, edge['boundary'], edge['evidence']))
    unique_edges = []
    for key, records in sorted(edge_records.items()):
        if len(records) > 2:
            raise ValueError('edge belongs to more than two domains')
        if len(records) == 2:
            first, second = records
            if first[0] == second[0]:
                raise ValueError('duplicate geometric edge within one domain')
            if abs(first[2] + second[2]) > tolerance:
                raise ValueError('shared edge flux is not anti-symmetric')
            shared_edges.append({'edge_id': f'e{key[0]}-{key[1]}', 'domains': sorted((first[0], second[0])), 'flux_m3_s': 0.0})
            internal_flux_residual += first[2] + second[2]
        else:
            domain_id, directed, flux, boundary, evidence = records[0]
            if boundary:
                boundary_flux += flux
            else:
                internal_evidence_edges += 1
        unique_edges.append({'edge_id': f'e{key[0]}-{key[1]}', 'global_start': key[0], 'global_end': key[1], 'record_count': len(records)})
    return {'schema': SURFACE_CROSS_DOMAIN_VERSION, 'algorithm_version': SURFACE_CROSS_DOMAIN_VERSION, 'flags': {'readonly': True, 'geometry_generated': False, 'water_generated': False, 'unknown_barrier_preserved': True, 'protected_barrier_preserved': True, 'edge_evidence_complete': False, 'hydraulic_ready': False, 'natural_outlet_verified': False}, 'grid': {'finest_spacing_x_m': finest_x, 'finest_spacing_z_m': finest_z, 'base_x_m': base_x, 'base_z_m': base_z, 'lods': sorted({domain['grid']['lod'] for domain in normalised})}, 'domains': [domain['domain_id'] for domain in normalised], 'global_nodes': [{'global_id': node_ids[key], 'x_m': global_nodes[key]['x_m'], 'z_m': global_nodes[key]['z_m'], 'member_count': len(global_nodes[key]['members'])} for key in ordered_keys], 'shared_boundary_node_ids': shared_nodes, 'barrier_node_ids': barriers, 'global_edges': unique_edges, 'shared_boundary_edges': shared_edges, 'ledger': {'unique_boundary_flux_m3_s': boundary_flux, 'internal_shared_flux_residual_m3_s': internal_flux_residual, 'shared_edge_count': len(shared_edges), 'boundary_edge_count': len(unique_edges) - len(shared_edges) - internal_evidence_edges, 'internal_evidence_edge_count': internal_evidence_edges}, 'flux_semantics': 'control-volume outward normal signed flux; endpoint order is geometric only; coarse face totals split by length', 'water': {'surface_policy': 'shared saved surfaces must match; no surface is generated', 'surface_available': False}, 'limitations': 'Read-only seam and ledger audit. It does not establish a complete river network, hydraulic connectivity, natural outlet, or observed channel geometry.'}

def _saved_nodes(nodes):
    required = {'x_m', 'z_m', 'h0_m', 'protected_mask'}
    if not isinstance(nodes, _i99_Mapping) or not required <= set(nodes):
        raise ValueError('saved mosaic lacks required node fields')
    count = len(nodes['x_m'])
    if any((len(nodes[name]) != count for name in required)):
        raise ValueError('saved mosaic node fields have inconsistent lengths')
    water = nodes.get('water_surface_m')
    wet = nodes.get('wet_mask')
    if water is not None and len(water) != count:
        raise ValueError('saved mosaic water field has inconsistent length')
    if wet is not None and len(wet) != count:
        raise ValueError('saved mosaic wet field has inconsistent length')
    unknown = nodes.get('unknown_mask')
    if unknown is not None and len(unknown) != count:
        raise ValueError('saved mosaic unknown field has inconsistent length')
    records = []
    for index in range(count):
        water_value = None
        if water is not None and (wet is None or bool(wet[index])):
            water_value = float(water[index])
        records.append({'local_id': index, 'x_m': float(nodes['x_m'][index]), 'z_m': float(nodes['z_m'][index]), 'h0_m': float(nodes['h0_m'][index]), 'unknown': bool(unknown[index]) if unknown is not None else False, 'protected': bool(nodes['protected_mask'][index]), 'water_surface_m': water_value})
    return records

def adapt_saved_mosaics(mosaics):
    """Convert loaded saved mosaics into audit records without reconstruction.

    Domain mosaics expose their independently saved domain meshes. Fine mosaics
    expose one saved mesh. Neither format stores a complete river-edge graph;
    the returned diagnostic keeps edges empty and marks that omission explicitly.
    """
    if not isinstance(mosaics, (list, tuple)) or not mosaics:
        raise ValueError('at least one saved mosaic is required')
    domains = []
    diagnostics = []
    for entry in mosaics:
        if not isinstance(entry, dict) or set(entry) != {'mosaic', 'domain_id'}:
            raise ValueError('saved mosaic entry requires mosaic and domain_id')
        mosaic = entry['mosaic']
        domain_id = entry['domain_id']
        if not isinstance(domain_id, str) or not domain_id:
            raise ValueError('domain_id must be a non-empty string')
        if mosaic.get('algorithm_version') == 'surface-domain-mosaic-v1':
            meshes = mosaic.get('domain_meshes')
            if not meshes:
                raise ValueError('domain mosaic has no saved domain meshes')
            for mesh_index, mesh in enumerate(meshes):
                source_id = mesh['sources'][0]['domain_id'] if mesh.get('sources') else f'{domain_id}-{mesh_index}'
                grid = mesh['grid']
                domains.append({'domain_id': str(source_id), 'grid': {'origin_x_m': grid['origin_x_m'], 'origin_z_m': grid['origin_z_m'], 'spacing_x_m': grid['spacing_x_m'], 'spacing_z_m': grid['spacing_z_m'], 'lod': 0}, 'nodes': _saved_nodes(mesh['nodes']), 'edges': []})
                diagnostics.append({'domain_id': str(source_id), 'source_kind': 'saved_domain_mesh', 'edge_evidence_complete': False, 'water_source': 'saved_node_water_surface'})
        elif mosaic.get('algorithm_version') == 'surface-fine-mosaic-v1.1':
            grid = mosaic['grid']
            domains.append({'domain_id': domain_id, 'grid': {'origin_x_m': grid['origin_x_m'], 'origin_z_m': grid['origin_z_m'], 'spacing_x_m': grid['spacing_x_m'], 'spacing_z_m': grid['spacing_z_m'], 'lod': 0}, 'nodes': _saved_nodes(mosaic['nodes']), 'edges': []})
            diagnostics.append({'domain_id': domain_id, 'source_kind': 'saved_fine_mosaic', 'edge_evidence_complete': False, 'water_source': 'saved_node_water_surface'})
        else:
            raise ValueError('unsupported saved mosaic algorithm')
    report = audit_cross_domain(domains)
    report['adapter'] = {'version': 'surface-cross-domain-saved-mosaic-adapter-v1', 'readonly': True, 'prepare_called': False, 'routing_called': False, 'water_generation_called': False, 'diagnostics': diagnostics}
    report['flags']['edge_evidence_complete'] = False
    report['limitations'] += ' Saved mosaic adapter has no river-edge reconstruction; edge ledger is diagnostic only.'
    return report

def save_cross_domain_report(report, path):
    """Atomically publish a report without overwriting an existing artifact."""
    if not isinstance(report, dict) or report.get('schema') != SURFACE_CROSS_DOMAIN_VERSION:
        raise ValueError('unsupported cross-domain report')
    from terrain_pipeline.common_infra import publish_bytes
    payload = _i99_json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False).encode('utf-8')
    publish_bytes(path, payload)

def audit_td_partition(records, *, partition_column, storage_record=None):
    """Cold-read Gibbs face records; audit one explicit vertical control-volume cut."""
    import numpy as np
    from terrain_pipeline.basin_topology import load_basin_hierarchy
    from terrain_pipeline.basin_storage import load_basin_storage
    from terrain_pipeline.td_surface_river_edges import build_td_surface_river_edges

    def load(record, loader):
        if not isinstance(record, dict) or set(record) != {'path', 'expected_sha256', 'expected_identity'}:
            raise ValueError('TD input requires both external pins')
        return loader(record['path'], expected_sha256=record['expected_sha256'], expected_identity=record['expected_identity'])
    hierarchy = load(records, load_basin_hierarchy)
    storage = None if storage_record is None else load(storage_record, load_basin_storage)
    versioned = build_td_surface_river_edges(hierarchy, storage=storage)
    arrays, metadata = (hierarchy['arrays'], hierarchy['metadata'])
    rows, columns = arrays['height_m'].shape
    if type(partition_column) is not int or not 0 < partition_column < columns:
        raise ValueError('partition column outside grid')
    elapsed = None
    if storage is not None:
        elapsed = (storage['arrays']['depth_m'].shape[0] - 1) * storage['metadata']['dt_s']
        if elapsed <= 0:
            raise ValueError('positive saved observation duration required')
    selected = [edge for edge in versioned['records'] if edge['kind'] == 'd4_internal_face' and {cell % columns for cell in edge['cell_ids']} == {partition_column - 1, partition_column}]
    domains = []
    for domain_id, sign in (('left', 1), ('right', -1)):
        nodes = []
        cell_ids = sorted({cell for edge in selected for cell in edge['cell_ids']})
        spacing = metadata['spacing_m']
        origin_x, origin_z = metadata['origin_m_xz']
        for cell in cell_ids:
            row, column = divmod(cell, columns)
            depth = None if storage is None else float(storage['arrays']['depth_m'][-1, cell])
            wet = depth is not None and depth > storage['metadata']['parameters']['wet_threshold_m']
            nodes.append({'local_id': cell, 'x_m': origin_x + column * spacing, 'z_m': origin_z + row * spacing, 'h0_m': float(arrays['height_m'][row, column]), 'unknown': not bool(arrays['valid_mask'][row, column]), 'protected': bool(arrays['protected_mask'][row, column]), 'water_surface_m': float(arrays['height_m'][row, column] + depth) if wet else None})
        edges = []
        for edge in selected:
            first, second = edge['cell_ids']
            evidence = None
            if elapsed is not None:
                evidence = {'adapter_version': versioned['schema'], 'face_index': edge['face_index'], 'hierarchy_identity_sha256': hierarchy['identity_sha256'], 'hydro_identity_sha256': storage['identity_sha256'], 'forward_m3': edge['forward_volume_m3'], 'reverse_m3': edge['reverse_volume_m3'], 'elapsed_s': elapsed}
            edges.append({'local_id': edge['face_index'], 'start': first, 'end': second, 'boundary': False, 'flux_m3_s': 0.0 if evidence is None else sign * (evidence['forward_m3'] - evidence['reverse_m3']) / elapsed, 'evidence': evidence})
        domains.append({'domain_id': domain_id, 'grid': {'origin_x_m': origin_x, 'origin_z_m': origin_z, 'spacing_x_m': spacing, 'spacing_z_m': spacing, 'lod': 0}, 'nodes': nodes, 'edges': edges})
    report = audit_cross_domain(domains)
    report['flags']['edge_evidence_complete'] = False
    report['flags']['partition_flux_evidence_complete'] = elapsed is not None and len(selected) == rows
    report['flags']['diagnostic_only'] = True
    report['td_evidence'] = {'schema': versioned['schema'], 'hierarchy': records, 'storage': storage_record, 'partition_column': partition_column, 'elapsed_s': elapsed, 'face_ids': [edge['face_index'] for edge in selected], 'forward_m3': None if elapsed is None else sum((edge['forward_volume_m3'] for edge in selected)), 'reverse_m3': None if elapsed is None else sum((edge['reverse_volume_m3'] for edge in selected))}
    report['td_evidence']['nonzero_one_direction_face_count'] = None if elapsed is None else sum(((edge['forward_volume_m3'] > 0) != (edge['reverse_volume_m3'] > 0) for edge in selected))
    report['limitations'] += ' TD faces are terrain control-volume exchanges, not observed channels. Only the named cut is audited; exterior per-face evidence and full river coverage are incomplete. No new spacing is synthesized.'
    return report
SURFACE_DYNAMIC_PREPARE_VERSION = 'surface-dynamic-prepare-v1'
AREA_SEMANTICS = 'fixed_lumped_actual_wet_cell_area_nearest_active_node_not_section_V_of_h'

@_i103_dataclass(frozen=True)
class DynamicPrepareResources:
    max_wet_cells: int = 100000
    max_assignment_work: int = 2000000
    max_retained_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES
    max_working_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES

    def __post_init__(self):
        ceilings = (100000, 2000000, SURFACE_FINE_MOSAIC_MAX_BYTES, SURFACE_FINE_MOSAIC_MAX_BYTES)
        for field, ceiling in zip(_i103_fields(self), ceilings):
            value = getattr(self, field.name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError('invalid dynamic prepare resource: ' + field.name)

def _surface_dynamic_prepare_seal(record):
    record['identity_sha256'] = _identity(record)
    return _freeze(record)

def _source_mosaic(source, domain_id, vertical_datum, resources):
    if isinstance(source, _i103_Mapping) and source.get('algorithm_version') == SURFACE_FINE_MOSAIC_VERSION:
        validate_fine_mosaic(source)
        if domain_id is not None:
            raise ValueError('domain selection is only supported for domain evaluations')
        if source['vertical_datum'] != vertical_datum:
            raise ValueError('source mosaic datum differs')
        return source
    if isinstance(source, _i103_Mapping) and source.get('kind') == 'evaluation':
        candidates = sources_from_surface_domains(source)
        if source['candidate']['inputs']['vertical_datum'] != vertical_datum:
            raise ValueError('prepared domain datum differs')
        selected = [item for item in candidates if domain_id is None or item.domain_id == domain_id]
        if len(selected) != 1:
            raise ValueError('select exactly one prepared domain_id')
        bound_source = selected[0]
    elif isinstance(source, DomainFineSource):
        if domain_id is not None:
            raise ValueError('explicit source already declares a domain id')
        bound_source = source
    elif isinstance(source, _i103_Mapping) and source.get('algorithm_version') == SURFACE_NETWORK_RECOVERY_VERSION:
        bound_source = DomainFineSource(source, 1 if domain_id is None else domain_id)
    else:
        raise ValueError('accepted recovery, prepared domain or saved prepared mosaic required')
    proof = bound_source.proof
    sea = proof['inputs']['plan']['identity']['parameters']['sea_level_elevation_m']
    return prepare_fine_mosaic((bound_source,), metric_grid={'coordinate_system': 'metric-xz-m'}, vertical_datum=vertical_datum, source_identity='dynamic-source:' + proof['identity_sha256'], sea_level_elevation_m=sea, resources=MosaicResources(max_cells=resources.max_wet_cells, max_retained_bytes=resources.max_retained_bytes, max_working_bytes=resources.max_working_bytes))

def bind_surface_dynamic_source(source, *, vertical_datum, domain_id=None, resources=DynamicPrepareResources()):
    """Explicit source preparation, never time advancement. Node order is coarse flat id."""
    if not isinstance(resources, DynamicPrepareResources):
        raise ValueError('DynamicPrepareResources required')
    retained_source = source.proof if isinstance(source, DomainFineSource) else source
    if _surface_fine_mosaic_size(retained_source) > resources.max_retained_bytes:
        raise ValueError('source retained resource preflight')
    prepared = _source_mosaic(source, domain_id, vertical_datum, resources)
    if _surface_fine_mosaic_size(prepared) * 2 > min(resources.max_retained_bytes, resources.max_working_bytes):
        raise ValueError('embedded source retained/working resource preflight')
    if len(prepared['proofs']) != 1 or len(prepared['sources']) != 1:
        raise ValueError('dynamic adapter scope requires one complete accepted recovery graph')
    proof_identity, proof = next(iter(prepared['proofs'].items()))
    payload = _payload(_plain(proof))
    node_flat_ids = _i103_np.flatnonzero(payload['active_mask']).astype(_i103_np.int64)
    if not len(node_flat_ids) or len(node_flat_ids) > 4096:
        raise ValueError('active node resource bound')
    lookup = {int(flat_id): index for index, flat_id in enumerate(node_flat_ids)}
    edges = []
    for flat_id in node_flat_ids:
        target = int(payload['receiver'][flat_id])
        if target >= 0:
            if target not in lookup:
                raise ValueError('actual channel edge leaves active source graph')
            edges.append((lookup[int(flat_id)], lookup[target]))
    edges = _i103_np.asarray(edges, _i103_np.int64).reshape(-1, 2)
    boundary = payload['outlet_mask'].ravel()[node_flat_ids]
    if not boundary.any() or boundary.all():
        raise ValueError('actual active outlet and internal storage nodes required')
    coordinates = payload['world_xz_m'][node_flat_ids]
    grid = prepared['grid']
    rows, columns = grid['shape_cells_zx']
    fine_columns = _i103_np.rint((coordinates[:, 0] - grid['origin_x_m']) / grid['spacing_x_m']).astype(_i103_np.int64)
    fine_rows = _i103_np.rint((coordinates[:, 1] - grid['origin_z_m']) / grid['spacing_z_m']).astype(_i103_np.int64)
    if _i103_np.any(fine_columns < 0) or _i103_np.any(fine_columns > columns) or _i103_np.any(fine_rows < 0) or _i103_np.any(fine_rows > rows) or (not _i103_np.allclose(coordinates[:, 0], grid['origin_x_m'] + fine_columns * grid['spacing_x_m'], atol=1e-08, rtol=0)) or (not _i103_np.allclose(coordinates[:, 1], grid['origin_z_m'] + fine_rows * grid['spacing_z_m'], atol=1e-08, rtol=0)):
        raise ValueError('source slice does not cover complete active graph')
    fine_node_ids = fine_rows * (columns + 1) + fine_columns
    wet_cell_ids = _i103_np.flatnonzero(prepared['wet_cells']).astype(_i103_np.int64)
    work = len(wet_cell_ids) * len(node_flat_ids)
    if not len(wet_cell_ids) or len(wet_cell_ids) > resources.max_wet_cells or work > resources.max_assignment_work:
        raise ValueError('wet-cell assignment resource preflight')
    if _surface_fine_mosaic_size(prepared) + len(wet_cell_ids) * 32 + len(node_flat_ids) * 128 > resources.max_working_bytes:
        raise ValueError('source mapping working resource preflight')
    owner = _i103_np.empty(len(wet_cell_ids), _i103_np.int64)
    for index, cell_id in enumerate(wet_cell_ids):
        corners = prepared['cells'][cell_id]
        center = _i103_np.array([prepared['nodes']['x_m'][corners].mean(), prepared['nodes']['z_m'][corners].mean()])
        owner[index] = int(_i103_np.argmin(((coordinates - center) ** 2).sum(axis=1)))
    cell_area = grid['spacing_x_m'] * grid['spacing_z_m']
    area = _i103_np.bincount(owner, minlength=len(node_flat_ids)).astype(float) * cell_area
    if _i103_np.any(area <= 0):
        raise ValueError('A0: active source node has no uniquely assigned actual wet cell')
    nodes = prepared['nodes']
    record = {'algorithm_version': SURFACE_DYNAMIC_PREPARE_VERSION, 'kind': 'binding', 'area_semantics': AREA_SEMANTICS, 'source_mosaic': prepared, 'source_proof_sha256': proof_identity, 'vertical_datum': vertical_datum, 'resources': _i103_asdict(resources), 'node_flat_ids': node_flat_ids, 'fine_node_ids': fine_node_ids, 'coords_xz_m': coordinates, 'edges': edges, 'boundary_mask': boundary, 'wet_cell_ids': wet_cell_ids, 'wet_cell_owner': owner, 'area_m2': area, 'bed_m': nodes['h2_m'][fine_node_ids], 'initial_stage_m': nodes['water_surface_m'][fine_node_ids], 'natural_outlets_certified': False, 'full_dynamic_wave_prepared': False}
    sealed = _surface_dynamic_prepare_seal(record)
    validate_surface_dynamic_binding(sealed)
    return sealed

def _pack_dynamic(result):
    inputs = {field.name: getattr(result.inputs, field.name) for field in _i103_fields(result.inputs)}
    inputs['limits'] = _i103_asdict(result.inputs.limits)
    failed = None if result.failed_step is None else {field.name: getattr(result.failed_step, field.name) for field in _i103_fields(result.failed_step)}
    return {'inputs': inputs, 'status': result.status, 'committed_steps': result.committed_steps, 'stage_m': result.stage_m, 'storage_m3': result.storage_m3, 'qedges_m3_s': result.qedges_m3_s, 'time_s': result.time_s, 'ledger_m3': result.ledger_m3, 'failed_step': failed, 'identity_sha256': result.identity_sha256}

def _unpack_dynamic(record):
    from terrain_pipeline.surface_hydraulics import HydraulicsInput as _x95_HydraulicsInput
    from terrain_pipeline.surface_hydraulics import FailedStep as _x96_FailedStep
    from terrain_pipeline.surface_hydraulics import HydraulicsResult as _x97_HydraulicsResult
    inputs = dict(record['inputs'])
    inputs['limits'] = _x94_ResourceLimits(**inputs['limits'])
    inputs = _x95_HydraulicsInput(**inputs)
    failed = record['failed_step']
    failed = None if failed is None else _x96_FailedStep(**failed)
    return _x97_HydraulicsResult(inputs=inputs, status=record['status'], committed_steps=record['committed_steps'], stage_m=record['stage_m'], storage_m3=record['storage_m3'], qedges_m3_s=record['qedges_m3_s'], time_s=record['time_s'], ledger_m3=record['ledger_m3'], failed_step=failed, identity_sha256=record['identity_sha256'])
from terrain_pipeline.surface_hydraulics import ResourceLimits as _x94_ResourceLimits

def prepare_surface_dynamic(source, *, conductance_m2_s, local_q_m3_s, tailwater_m, dt_s, max_depth_m, vertical_datum=None, domain_id=None, resources=DynamicPrepareResources(), limits=_x94_ResourceLimits(), cancel=None):
    """The only adapter entrypoint that advances time; caller K/Q/tailwater stay explicit."""
    from terrain_pipeline.surface_hydraulics import HydraulicsInput as _x95_HydraulicsInput
    from terrain_pipeline.surface_hydraulics import _preflight as _x98_preflight
    from terrain_pipeline.surface_hydraulics import evaluate as _x99_evaluate
    if isinstance(source, _i103_Mapping) and source.get('kind') == 'binding':
        binding = source
        validate_surface_dynamic_binding(binding)
        if domain_id is not None or (vertical_datum is not None and vertical_datum != binding['vertical_datum']):
            raise ValueError('binding selection/datum differs')
        resources = DynamicPrepareResources(**binding['resources'])
    else:
        binding = bind_surface_dynamic_source(source, vertical_datum=vertical_datum, domain_id=domain_id, resources=resources)
    local = _i103_np.asarray(local_q_m3_s)
    tailwater = _i103_np.asarray(tailwater_m)
    count = len(binding['node_flat_ids'])
    if local.ndim != 2 or local.shape[1] != count:
        raise ValueError('explicit local Q[T,N] in saved node order required')
    if tailwater.shape != (len(local) + 1, int(binding['boundary_mask'].sum())):
        raise ValueError('explicit tailwater[T+1,actual outlets] required')
    usage = _x98_preflight(count, len(binding['edges']), len(local), limits)
    estimate = _surface_fine_mosaic_size(binding) + usage['retained_bytes_upper_bound']
    if estimate * 2 > min(resources.max_retained_bytes, resources.max_working_bytes):
        raise ValueError('dynamic retained/working resource preflight')
    boundary_stage = _i103_np.zeros((len(local) + 1, count))
    boundary_stage[:, binding['boundary_mask']] = tailwater
    inputs = _x95_HydraulicsInput(bed_m=binding['bed_m'], area_m2=binding['area_m2'], initial_stage_m=binding['initial_stage_m'], edges=binding['edges'], conductance_m2_s=conductance_m2_s, local_q_m3_s=local, boundary_mask=binding['boundary_mask'], boundary_stage_m=boundary_stage, dt_s=dt_s, max_depth_m=max_depth_m, valid_mask=_i103_np.ones(count, bool), protected_mask=_i103_np.zeros(count, bool), coords_m=binding['coords_xz_m'], source=binding['identity_sha256'], datum=binding['vertical_datum'], coords='metric-xz-m', limits=limits)
    dynamic = _x99_evaluate(inputs, cancel=cancel)
    record = {'algorithm_version': SURFACE_DYNAMIC_PREPARE_VERSION, 'kind': 'dynamic', 'binding': binding, 'dynamic': _pack_dynamic(dynamic), 'status': dynamic.status, 'caller_tailwater_m': tailwater, 'resources': _i103_asdict(resources), 'natural_outlets_certified': False, 'full_dynamic_wave_prepared': False}
    sealed = _surface_dynamic_prepare_seal(record)
    validate_surface_dynamic(sealed)
    return sealed

def _record_gate(record, kind):
    if record['algorithm_version'] != SURFACE_DYNAMIC_PREPARE_VERSION or record['kind'] != kind or record['natural_outlets_certified'] is not False or (record['full_dynamic_wave_prepared'] is not False) or (record['identity_sha256'] != _identity({key: value for key, value in record.items() if key != 'identity_sha256'})):
        raise ValueError('dynamic prepare identity/scope mismatch')
    resources = DynamicPrepareResources(**record['resources'])
    size = _surface_fine_mosaic_size(record)
    if size > resources.max_retained_bytes or size * 2 > resources.max_working_bytes:
        raise ValueError('dynamic prepare retained/working resource limit')
    return resources

def validate_surface_dynamic_binding(binding):
    """Validate saved ownership algebraically; never construct or resample mappings."""
    try:
        resources = _record_gate(binding, 'binding')
        source = binding['source_mosaic']
        validate_fine_mosaic(source)
        if binding['area_semantics'] != AREA_SEMANTICS or binding['vertical_datum'] != source['vertical_datum'] or len(source['proofs']) != 1 or (len(source['sources']) != 1):
            raise ValueError('dynamic source/area semantics invalid')
        identity, proof = next(iter(source['proofs'].items()))
        if identity != binding['source_proof_sha256']:
            raise ValueError('binding proof identity differs')
        payload = _payload(_plain(proof))
        flat_ids = binding['node_flat_ids']
        count = len(flat_ids)
        if flat_ids.dtype != _i103_np.dtype('int64') or flat_ids.ndim != 1 or (not 0 < count <= 4096) or (not _i103_np.array_equal(flat_ids, _i103_np.flatnonzero(payload['active_mask']))):
            raise ValueError('saved active node ids not complete/unique')
        coordinates = binding['coords_xz_m']
        if coordinates.dtype != _i103_np.dtype('float64') or coordinates.shape != (count, 2) or (not _i103_np.array_equal(coordinates, payload['world_xz_m'][flat_ids])) or (len(set(map(tuple, coordinates))) != count):
            raise ValueError('saved source node coordinates invalid/duplicate')
        boundary = binding['boundary_mask']
        if boundary.dtype != bool or boundary.shape != (count,) or (not _i103_np.array_equal(boundary, payload['outlet_mask'].ravel()[flat_ids])) or (not boundary.any()) or boundary.all():
            raise ValueError('saved boundary is not actual active outlet mask')
        edges = binding['edges']
        edge_count = int(_i103_np.count_nonzero(payload['receiver'][flat_ids] >= 0))
        if edges.dtype != _i103_np.dtype('int64') or edges.shape != (edge_count, 2):
            raise ValueError('saved graph edge shape/dtype invalid')
        edge_index = 0
        for node_id, flat_id in enumerate(flat_ids):
            target = int(payload['receiver'][flat_id])
            if target >= 0:
                if edges[edge_index, 0] != node_id or not 0 <= edges[edge_index, 1] < count or flat_ids[edges[edge_index, 1]] != target:
                    raise ValueError('saved edge differs from actual active source topology')
                edge_index += 1
        fine_ids = binding['fine_node_ids']
        nodes = source['nodes']
        if fine_ids.dtype != _i103_np.dtype('int64') or fine_ids.shape != (count,) or _i103_np.any(fine_ids < 0) or _i103_np.any(fine_ids >= len(nodes['x_m'])) or (len(set(fine_ids.tolist())) != count) or (not _i103_np.array_equal(nodes['x_m'][fine_ids], coordinates[:, 0])) or (not _i103_np.array_equal(nodes['z_m'][fine_ids], coordinates[:, 1])):
            raise ValueError('saved fine node mapping differs from actual source world coordinates')
        if not _i103_np.all(nodes['wet_mask'][fine_ids]) or _i103_np.any(nodes['protected_mask'][fine_ids]):
            raise ValueError('active node has unknown/protected/dry source support')
        if not _i103_np.allclose(nodes['water_surface_m'][fine_ids], payload['node_stage_m'][flat_ids], atol=1e-08, rtol=0) or not _i103_np.allclose(nodes['h2_m'][fine_ids], proof['final_plan']['arrays']['bounded_bed_m'].ravel()[flat_ids], atol=proof['inputs']['budget']['bed_match_tolerance_m'], rtol=0) or _i103_np.any(nodes['water_surface_m'][fine_ids] <= nodes['h2_m'][fine_ids]):
            raise ValueError('saved node actual fine depth/stage/bed differs from source graph')
        for name, actual in (('bed_m', nodes['h2_m'][fine_ids]), ('initial_stage_m', nodes['water_surface_m'][fine_ids])):
            value = binding[name]
            if value.dtype != _i103_np.dtype('float64') or value.shape != (count,) or (not _i103_np.array_equal(value, actual)):
                raise ValueError('saved node bed/stage differs from actual fine H2/water')
        wet_ids, owner = (binding['wet_cell_ids'], binding['wet_cell_owner'])
        if wet_ids.dtype != _i103_np.dtype('int64') or wet_ids.ndim != 1 or (not _i103_np.array_equal(wet_ids, _i103_np.flatnonzero(source['wet_cells']))) or (not len(wet_ids)) or (len(wet_ids) > resources.max_wet_cells) or (len(wet_ids) * count > resources.max_assignment_work) or (owner.dtype != _i103_np.dtype('int64')) or (owner.shape != wet_ids.shape) or _i103_np.any(owner < 0) or _i103_np.any(owner >= count):
            raise ValueError('saved wet cell assignment set/resource/owner invalid')
        for index, cell_id in enumerate(wet_ids):
            corners = source['cells'][cell_id]
            center_x, center_z = (nodes['x_m'][corners].mean(), nodes['z_m'][corners].mean())
            distances = (coordinates[:, 0] - center_x) ** 2 + (coordinates[:, 1] - center_z) ** 2
            chosen = int(owner[index])
            if _i103_np.any(distances < distances[chosen]) or _i103_np.any(distances[:chosen] == distances[chosen]):
                raise ValueError('saved wet cell ownership is not nearest active node with stable tie')
        cell_area = source['grid']['spacing_x_m'] * source['grid']['spacing_z_m']
        expected_area = _i103_np.bincount(owner, minlength=count) * cell_area
        area = binding['area_m2']
        if area.dtype != _i103_np.dtype('float64') or area.shape != (count,) or (not _i103_np.isfinite(area).all()) or _i103_np.any(area <= 0) or (not _i103_np.array_equal(area, expected_area)) or (not _i103_math.isclose(float(area.sum()), len(wet_ids) * cell_area, rel_tol=0, abs_tol=1e-08)):
            raise ValueError('saved A0/area differs from unique actual wet cell ownership')
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError('invalid saved dynamic source binding') from error

def validate_surface_dynamic(result):
    from terrain_pipeline.surface_hydraulics import validate as _x100_validate
    try:
        resources = _record_gate(result, 'dynamic')
        binding = result['binding']
        validate_surface_dynamic_binding(binding)
        if result['resources'] != binding['resources']:
            raise ValueError('dynamic resources differ from binding')
        dynamic = _unpack_dynamic(result['dynamic'])
        usage = _x100_validate(dynamic)
        inputs = dynamic.inputs
        estimate = _surface_fine_mosaic_size(binding) + usage['resources']['retained_bytes_upper_bound']
        if estimate * 2 > min(resources.max_retained_bytes, resources.max_working_bytes):
            raise ValueError('saved dynamic resource upper bound exceeded')
        for name, expected in (('bed_m', binding['bed_m']), ('area_m2', binding['area_m2']), ('initial_stage_m', binding['initial_stage_m']), ('edges', binding['edges']), ('boundary_mask', binding['boundary_mask']), ('coords_m', binding['coords_xz_m'])):
            if not _i103_np.array_equal(getattr(inputs, name), expected):
                raise ValueError('dynamic input differs from source binding: ' + name)
        if inputs.source != binding['identity_sha256'] or inputs.datum != binding['vertical_datum'] or inputs.coords != 'metric-xz-m' or (result['status'] != dynamic.status) or _i103_np.any(inputs.boundary_stage_m[:, ~inputs.boundary_mask] != 0) or (not _i103_np.array_equal(result['caller_tailwater_m'], inputs.boundary_stage_m[:, inputs.boundary_mask])):
            raise ValueError('saved dynamic provenance/status/tailwater differs')
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError('invalid saved dynamic prepare result') from error

def query_surface_dynamic(result, *, state_index=None):
    validate_surface_dynamic(result)
    dynamic = result['dynamic']
    if state_index is not None and (type(state_index) is not int or not 0 <= state_index <= dynamic['committed_steps']):
        raise ValueError('state index outside saved committed prefix')
    selection = slice(None) if state_index is None else state_index
    return _freeze({'stage_m': dynamic['stage_m'][selection], 'storage_m3': dynamic['storage_m3'][selection], 'time_s': dynamic['time_s'][selection], 'node_flat_ids': result['binding']['node_flat_ids'], 'status': result['status']})

def save_surface_dynamic(result, path):
    validate_surface_dynamic(result)
    destination = _i103_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = _surface_fine_mosaic_tree(result, arrays)
    metadata = _surface_fine_mosaic_json({'format_version': 1, 'tree': tree, 'tree_sha256': _identity(tree)})
    descriptor, temporary = _i103_tempfile.mkstemp(prefix='.surface-dynamic-', suffix='.tmp', dir=destination.parent)
    try:
        stream = _i103_os.fdopen(descriptor, 'w+b')
        descriptor = None
        with stream:
            with _i103_zipfile.ZipFile(stream, 'w', compression=_i103_zipfile.ZIP_STORED) as archive:
                archive.writestr('manifest.json', metadata)
                for name, array in arrays.items():
                    with archive.open(name, 'w') as member:
                        _i103_np.lib.format.write_array(member, _i103_np.ascontiguousarray(array), allow_pickle=False)
            if stream.tell() > SURFACE_FINE_MOSAIC_MAX_BYTES:
                raise ValueError('dynamic prepare file cap')
            stream.flush()
            _i103_os.fsync(stream.fileno())
        _i103_os.link(temporary, destination)
        return destination
    finally:
        if descriptor is not None:
            _i103_os.close(descriptor)
        _i103_Path(temporary).unlink(missing_ok=True)

def load_surface_dynamic(path):
    """Static source support, ownership and dynamic equations; no generation/replay."""
    from terrain_pipeline.artifacts.contracts import array_hash as _i105_array_hash
    from terrain_pipeline.surface_hydraulics import _preflight as _x98_preflight
    try:
        with _i103_Path(path).open('rb') as retained:
            if _i103_os.fstat(retained.fileno()).st_size > SURFACE_FINE_MOSAIC_MAX_BYTES:
                raise ValueError('dynamic prepare file cap')
            with _i103_zipfile.ZipFile(retained) as archive:
                _preflight_archive(archive)
                manifest = _i103_json.loads(archive.read('manifest.json'), object_pairs_hook=_surface_fine_mosaic_pairs, parse_constant=_surface_fine_mosaic_constant)
                if set(manifest) != {'format_version', 'tree', 'tree_sha256'} or manifest['format_version'] != 1 or manifest['tree_sha256'] != _identity(manifest['tree']):
                    raise ValueError('dynamic prepare manifest identity differs')
                tree = manifest['tree']
                resources = DynamicPrepareResources(**tree['resources'])
                binding = tree['binding']
                if binding['resources'] != tree['resources'] or tree['algorithm_version'] != SURFACE_DYNAMIC_PREPARE_VERSION or tree['kind'] != 'dynamic':
                    raise ValueError('archive JSON resource/schema mismatch')
                dynamic_inputs = tree['dynamic']['inputs']
                limits = _x94_ResourceLimits(**dynamic_inputs['limits'])
                count = binding['node_flat_ids']['shape'][0]
                wet_count = binding['wet_cell_ids']['shape'][0]
                usage = _x98_preflight(count, binding['edges']['shape'][0], dynamic_inputs['local_q_m3_s']['shape'][0], limits)
                size = sum((entry.file_size for entry in archive.infolist()))
                if wet_count > resources.max_wet_cells or wet_count * count > resources.max_assignment_work or size > resources.max_retained_bytes or (size * 2 > resources.max_working_bytes) or (usage['retained_bytes_upper_bound'] > resources.max_retained_bytes):
                    raise ValueError('dynamic prepare JSON resource preflight')
                references = {}

                def collect(value):
                    if isinstance(value, dict) and '$array' in value:
                        name = value['$array']
                        if set(value) != {'$array', 'shape', 'dtype', 'sha256'} or name in references or name not in archive.namelist() or (not name.endswith('.npy')):
                            raise ValueError('invalid/duplicate dynamic array reference')
                        references[name] = value
                    elif isinstance(value, dict):
                        for child in value.values():
                            collect(child)
                    elif isinstance(value, list):
                        for child in value:
                            collect(child)
                collect(tree)
                if set(references) != set(archive.namelist()) - {'manifest.json'}:
                    raise ValueError('unused dynamic prepare archive arrays')
                for name, reference in references.items():
                    with archive.open(name) as member:
                        version = _i103_np.lib.format.read_magic(member)
                        reader = _i103_np.lib.format.read_array_header_1_0 if version == (1, 0) else _i103_np.lib.format.read_array_header_2_0
                        shape, fortran, dtype = reader(member)
                        if reference['shape'] != list(shape) or reference['dtype'] != dtype.str or fortran:
                            raise ValueError('NPY actual header differs from saved resource metadata')
                arrays = {}
                used = set()

                def decode(value):
                    if isinstance(value, dict) and '$array' in value:
                        name = value['$array']
                        if set(value) != {'$array', 'shape', 'dtype', 'sha256'} or name in used or name not in archive.namelist():
                            raise ValueError('invalid/duplicate dynamic array reference')
                        with archive.open(name) as member:
                            array = _i103_np.load(member, allow_pickle=False)
                        if value['shape'] != list(array.shape) or value['dtype'] != array.dtype.str or value['sha256'] != _i105_array_hash(array):
                            raise ValueError('dynamic prepare array hash/shape differs')
                        used.add(name)
                        arrays[name] = array
                        return array
                    if isinstance(value, dict):
                        return {key: decode(child) for key, child in value.items()}
                    if isinstance(value, list):
                        return [decode(child) for child in value]
                    return value
                result = decode(tree)
                if used != set(archive.namelist()) - {'manifest.json'}:
                    raise ValueError('unused dynamic prepare archive arrays')
        validate_surface_dynamic(result)
        return _freeze(result)
    except (KeyError, TypeError, IndexError, AttributeError, OSError, EOFError, _i103_zipfile.BadZipFile) as error:
        raise ValueError('invalid dynamic prepare bundle') from error
SURFACE_DEVELOPMENT_READINESS_VERSION = 'surface-development-readiness-v1'
KINDS = ('dem', 'domain', 'mosaic', 'drop', 'dynamic')
MAX_BUNDLE_BYTES = 16 * 1024 * 1024
SURFACE_DEVELOPMENT_READINESS_MAX_MANIFEST_BYTES = 64 * 1024
SCOPES = ('static_geometry', 'lumped_storage_linear_conductance', 'full_dynamic_wave')
MODULES = {'dem': (_i100_dem_domain, lambda path: _i100_dem_domain.load_dem_candidate(path, verify_source=False)), 'domain': (__import__('sys').modules[__name__], lambda path: load_surface_domains(path, allow_unprepared=True)), 'mosaic': (__import__('sys').modules[__name__], lambda path: load_fine_mosaic(path, allow_unprepared=True)), 'drop': (__import__('sys').modules[__name__], load_coast_drop), 'dynamic': (__import__('sys').modules[__name__], load_surface_dynamic)}

def _surface_development_readiness_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate readiness JSON key')
        result[key] = value
    return result

def _surface_development_readiness_constant(value):
    raise ValueError('nonfinite readiness JSON value: ' + value)

def _digest(path, limit):
    path = _i100_Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError('missing or linked input: ' + str(path))
    size = path.stat().st_size
    if size <= 0 or size > limit:
        raise ValueError('readiness input size cap: ' + str(path))
    digest = _i100_hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    if path.stat().st_size != size:
        raise ValueError('readiness input changed while hashing')
    return (digest.hexdigest(), size)

def _record(kind, path):
    source = _i100_Path(path).absolute()
    for component in (source, *source.parents):
        attributes = getattr(_i100_os.lstat(component), 'st_file_attributes', 0) if component.exists() else 0
        if component.is_symlink() or attributes & getattr(_i100_stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
            raise ValueError('linked or reparse input path: ' + str(component))
    resolved = source.resolve(strict=True)
    digest, size = _digest(resolved, MAX_BUNDLE_BYTES)
    module, loader = MODULES[kind]
    product = loader(resolved)
    if _digest(resolved, MAX_BUNDLE_BYTES) != (digest, size):
        raise ValueError('readiness input changed while loading')
    identity = product['manifest']['identity_sha256'] if kind == 'dem' else product['identity_sha256']
    if not isinstance(identity, str) or len(identity) != 64:
        raise ValueError('invalid bundle identity')
    module_hash, _ = _digest(_i100_Path(module.__file__), MAX_BUNDLE_BYTES)
    return (product, {'path': str(resolved), 'sha256': digest, 'bytes': size, 'identity_sha256': identity, 'module': module.__name__, 'module_sha256': module_hash})

def _diagnose(products, scope):
    dem = products.get('dem')
    domain = products.get('domain')
    mosaic = products.get('mosaic')
    drop = products.get('drop')
    dynamic = products.get('dynamic')
    blockers = []
    facts = {}
    if dem is None:
        blockers.append('dem_bundle_missing')
    else:
        unknown = int(_i100_np.count_nonzero(dem['arrays']['unknown_mask']))
        facts['dem_unknown_cells'] = unknown
        facts['dem_source_identity'] = dem['manifest']['identity_sha256']
        blockers.append('dem_source_replay_not_performed_and_observation_validator_unsupported')
        if unknown:
            blockers.append('dem_unknown_coverage')
        if dem['manifest']['status'] != 'publishable':
            blockers.append('dem_candidate_not_publishable')
    if domain is None:
        blockers.append('domain_bundle_missing')
    else:
        inputs = domain['candidate']['inputs']
        facts['domain_source_identity'] = inputs['source_identity']
        facts['domain_source_kind'] = inputs['source_kind']
        facts['domain_recovery_ids'] = sorted((item['recovery']['identity_sha256'] for item in domain['domains'] if item['recovery']))
        if domain['status'] != 'prepared':
            blockers.append('domain_not_prepared')
        if inputs['source_kind'] == 'engineering_synthetic':
            blockers.append('domain_engineering_synthetic')
        if dem is not None:
            blockers.append('dem_and_domain_source_graph_not_bound')
    if mosaic is None:
        blockers.append('mosaic_bundle_missing')
    else:
        missing = int(_i100_np.count_nonzero(_i100_np.asarray(mosaic['cell_owner']) < 0))
        facts['mosaic_missing_cells'] = missing
        facts['mosaic_source_identity'] = mosaic['source_identity']
        facts['mosaic_proof_ids'] = sorted(mosaic['proofs'])
        if missing or mosaic['status'] != 'prepared' or (not mosaic['full_domain_mosaic_prepared']):
            blockers.append('full_domain_mosaic_gap_or_unprepared')
        if domain is not None and (not set(facts['domain_recovery_ids']).issubset(mosaic['proofs'])):
            blockers.append('domain_and_mosaic_proof_graph_mismatch')
    if drop is None:
        blockers.append('drop_bundle_missing')
    else:
        facts['drop_mode'] = drop['mode']
        facts['drop_attachment_recovery_id'] = drop['attachment']['recovery_sha256']
        if drop['mode'] != MODE or not drop['natural_outlet_certified']:
            blockers.append('coastline_and_natural_outlet_not_certified')
        if domain is not None and facts['drop_attachment_recovery_id'] not in facts['domain_recovery_ids']:
            blockers.append('drop_and_domain_proof_graph_mismatch')
        if mosaic is not None and facts['drop_attachment_recovery_id'] not in facts['mosaic_proof_ids']:
            blockers.append('drop_and_mosaic_proof_graph_mismatch')
    if dynamic is None:
        facts['dynamic_scope'] = 'not_supplied'
        if scope != 'static_geometry':
            blockers.append('dynamic_bundle_missing_for_scope')
    else:
        binding = dynamic['binding']
        facts['dynamic_scope'] = binding['area_semantics']
        source_mosaic = binding['source_mosaic']
        facts['dynamic_source_mosaic_id'] = source_mosaic['identity_sha256']
        facts['dynamic_source_proof_id'] = binding['source_proof_sha256']
        facts['dynamic_embedded_proof_ids'] = sorted(source_mosaic['proofs'])
        dynamic_proof = facts['dynamic_source_proof_id']
        if domain is not None and dynamic_proof not in facts['domain_recovery_ids']:
            blockers.append('dynamic_and_domain_proof_graph_mismatch')
        if mosaic is not None and dynamic_proof not in facts['mosaic_proof_ids']:
            blockers.append('dynamic_and_mosaic_proof_graph_mismatch')
        if mosaic is not None:
            embedded_proofs = set(facts['dynamic_embedded_proof_ids'])
            external_proofs = set(facts['mosaic_proof_ids'])
            facts['dynamic_mosaic_artifact_different'] = facts['dynamic_source_mosaic_id'] != mosaic['identity_sha256']
            if embedded_proofs < external_proofs:
                blockers.append('dynamic_partial_graph_not_full_mosaic')
            elif not embedded_proofs.issubset(external_proofs):
                blockers.append('dynamic_and_mosaic_proof_graph_mismatch')
        if scope == 'full_dynamic_wave' and (not dynamic['full_dynamic_wave_prepared']):
            blockers.append('full_dynamic_wave_not_prepared')
        if scope != 'static_geometry':
            blockers.append('constant_area_linear_conductance_not_calibrated_section_hydraulics')
    blockers.append('independent_geographic_certification_unsupported')
    return {'ready': False, 'blockers': sorted(set(blockers)), 'facts': facts, 'certification': 'unsupported_no_independent_evidence_validator'}

def _evaluate(paths, dynamic_scope):
    if dynamic_scope not in SCOPES:
        raise ValueError('unsupported dynamic scope')
    if not isinstance(paths, dict) or not paths or set(paths) - set(KINDS):
        raise ValueError('expected at most five named bundle paths')
    products, bindings = ({}, {})
    for kind in KINDS:
        if kind in paths:
            products[kind], bindings[kind] = _record(kind, paths[kind])
    if 'domain' in products and products['domain'].get('kind') != 'evaluation':
        raise ValueError('domain bundle must be an evaluation')
    return {'format': SURFACE_DEVELOPMENT_READINESS_VERSION, 'dynamic_scope': dynamic_scope, 'bundles': bindings, 'diagnosis': _diagnose(products, dynamic_scope)}

def prepare_readiness(paths, *, dynamic_scope='lumped_storage_linear_conductance'):
    return _evaluate(paths, dynamic_scope)

def _canonical_json(value):
    try:
        return _i100_json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError('invalid readiness JSON types') from error

def save_readiness(manifest, path):
    target = _i100_Path(path)
    if target.exists():
        raise FileExistsError(target)
    validated = load_readiness_dict(manifest)
    payload = (_i100_json.dumps(validated, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    if len(payload) > SURFACE_DEVELOPMENT_READINESS_MAX_MANIFEST_BYTES:
        raise ValueError('readiness manifest size cap')
    descriptor, temporary = _i100_tempfile.mkstemp(prefix='.readiness-', suffix='.tmp', dir=target.parent)
    try:
        with _i100_os.fdopen(descriptor, 'wb') as output:
            output.write(payload)
            output.flush()
            _i100_os.fsync(output.fileno())
        stored = _i100_json.loads(_i100_Path(temporary).read_text(encoding='utf-8'), object_pairs_hook=_surface_development_readiness_pairs, parse_constant=_surface_development_readiness_constant)
        if _canonical_json(stored) != _canonical_json(validated):
            raise ValueError('readiness temporary validation failed')
        _i100_os.link(temporary, target)
    finally:
        _i100_Path(temporary).unlink(missing_ok=True)

def load_readiness_dict(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {'format', 'dynamic_scope', 'bundles', 'diagnosis'} or manifest['format'] != SURFACE_DEVELOPMENT_READINESS_VERSION or (manifest['dynamic_scope'] not in SCOPES) or (not isinstance(manifest['bundles'], dict)) or (not manifest['bundles']) or set(manifest['bundles']) - set(KINDS):
        raise ValueError('invalid readiness manifest schema')
    paths = {}
    for kind, binding in manifest['bundles'].items():
        if not isinstance(binding, dict) or set(binding) != {'path', 'sha256', 'bytes', 'identity_sha256', 'module', 'module_sha256'} or (not isinstance(binding['path'], str)) or (not _i100_Path(binding['path']).is_absolute()):
            raise ValueError('invalid readiness bundle binding')
        paths[kind] = binding['path']
    current = _evaluate(paths, manifest['dynamic_scope'])
    if _canonical_json(current) != _canonical_json(manifest):
        raise ValueError('readiness conclusion or bundle identity changed')
    return current

def load_readiness(path):
    source = _i100_Path(path)
    _digest(source, SURFACE_DEVELOPMENT_READINESS_MAX_MANIFEST_BYTES)
    manifest = _i100_json.loads(source.read_text(encoding='utf-8'), object_pairs_hook=_surface_development_readiness_pairs, parse_constant=_surface_development_readiness_constant)
    return load_readiness_dict(manifest)
SURFACE_DOMAIN_MOSAIC_VERSION = 'surface-domain-mosaic-v1'
SOURCE_KINDS = ('accepted_domain_proof', 'original_candidate_h0_dry_bilinear')

def _candidate_grid(candidate):
    inputs = candidate['inputs']
    return {'origin_x_m': inputs['origin_x_m'], 'origin_z_m': inputs['origin_z_m'], 'spacing_x_m': inputs['spacing_x_m'], 'spacing_z_m': inputs['spacing_z_m']}

def _envelope(domain_meshes):
    bounds = [mesh['grid']['bbox_xz_m'] for mesh in domain_meshes]
    return [min((item[0] for item in bounds)), max((item[1] for item in bounds)), min((item[2] for item in bounds)), max((item[3] for item in bounds))]

def _grid(domain_meshes):
    bbox = _envelope(domain_meshes)
    spacing_x = min((mesh['grid']['spacing_x_m'] for mesh in domain_meshes))
    spacing_z = min((mesh['grid']['spacing_z_m'] for mesh in domain_meshes))
    if any((mesh['grid']['spacing_x_m'] != spacing_x or mesh['grid']['spacing_z_m'] != spacing_z for mesh in domain_meshes)):
        raise ValueError('domain precision mismatch')
    dimensions = [(bbox[1] - bbox[0]) / spacing_x, (bbox[3] - bbox[2]) / spacing_z]
    if any((not _i101_math.isclose(value, round(value), abs_tol=1e-08, rel_tol=0) for value in dimensions)):
        raise ValueError('incompatible domain grid envelope')
    if any((not _i101_math.isclose((mesh['grid']['origin_x_m'] - bbox[0]) / spacing_x, round((mesh['grid']['origin_x_m'] - bbox[0]) / spacing_x), abs_tol=1e-08, rel_tol=0) or not _i101_math.isclose((mesh['grid']['origin_z_m'] - bbox[2]) / spacing_z, round((mesh['grid']['origin_z_m'] - bbox[2]) / spacing_z), abs_tol=1e-08, rel_tol=0) for mesh in domain_meshes)):
        raise ValueError('domain origins not aligned')
    return {'coordinate_system': 'metric-xz-m', 'origin_x_m': bbox[0], 'origin_z_m': bbox[2], 'spacing_x_m': spacing_x, 'spacing_z_m': spacing_z, 'shape_cells_zx': [round(dimensions[1]), round(dimensions[0])], 'bbox_xz_m': bbox}

def _extension_value(candidate, x, z, indices, weights):
    inputs = candidate['inputs']
    shape = inputs['height_m'].shape
    _support_check(indices, weights, shape, _i101_np.asarray(x), _i101_np.asarray(z), _candidate_grid(candidate))
    positive = indices[weights > 0]
    if not _i101_np.all(inputs['valid_mask'].ravel()[positive]) or not _i101_np.all(inputs['land_mask'].ravel()[positive]) or _i101_np.any(inputs['ocean_mask'].ravel()[positive]) or _i101_np.any(inputs['domain_labels'].ravel()[positive] <= 0):
        raise ValueError('dry extension requires valid known original land support')
    height = float(_i101_np.dot(inputs['height_m'].ravel()[indices], weights))
    if not _i101_math.isfinite(height):
        raise ValueError('dry extension H0 is not finite')
    return (height, bool(_i101_np.any(inputs['protected_mask'].ravel()[positive])))

def _check_node(nodes, node_id, values, seen, tolerance=1e-08):
    for name, value in values.items():
        previous = nodes[name][node_id]
        if seen[node_id] and (previous != value if isinstance(value, (bool, _i101_np.bool_)) else abs(previous - value) > tolerance):
            raise ValueError('shared seam conflict in H0/H2/wet/stage/protection')
        nodes[name][node_id] = value
    seen[node_id] = True

def _domain_owner(record, cells, nodes, geometry_owner):
    candidate = record['evaluation']['candidate']
    inputs = candidate['inputs']
    labels = inputs['domain_labels']
    center_x = nodes['x_m'][cells].mean(axis=1)
    center_z = nodes['z_m'][cells].mean(axis=1)
    column = _i101_np.floor((center_x - inputs['origin_x_m']) / inputs['spacing_x_m'] + 0.5).astype(int)
    row = _i101_np.floor((center_z - inputs['origin_z_m']) / inputs['spacing_z_m'] + 0.5).astype(int)
    if _i101_np.any(row < 0) or _i101_np.any(row >= labels.shape[0]) or _i101_np.any(column < 0) or _i101_np.any(column >= labels.shape[1]):
        raise ValueError('cell center outside original candidate')
    owners = labels[row, column]
    for source_id, domain in enumerate(record['evaluation']['domains']):
        if _i101_np.any(owners[geometry_owner == source_id] != domain['domain_id']):
            raise ValueError('domain cell center label mismatch')
    if _i101_np.any(owners <= 0):
        raise ValueError('extension has no hydrologic domain owner')
    return owners.astype(_i101_np.int64)

def _assemble(record, cancel=None):
    grid, meshes, candidate = (record['grid'], record['domain_meshes'], record['evaluation']['candidate'])
    rows, columns = grid['shape_cells_zx']
    count, node_count = (rows * columns, (rows + 1) * (columns + 1))
    cells, triangles = _mesh(grid)
    nodes = {name: _i101_np.zeros(node_count, bool if name.endswith('mask') else float) for name in ('x_m', 'z_m', 'h0_m', 'h2_m', 'wet_mask', 'water_surface_m', 'protected_mask')}
    nodes['x_m'] = _i101_np.tile(grid['origin_x_m'] + _i101_np.arange(columns + 1) * grid['spacing_x_m'], rows + 1)
    nodes['z_m'] = _i101_np.repeat(grid['origin_z_m'] + _i101_np.arange(rows + 1) * grid['spacing_z_m'], columns + 1)
    owner = _i101_np.full(count, -1, _i101_np.int64)
    contributors = {'indices': _i101_np.zeros((count, 4, 4), _i101_np.int64), 'weights': _i101_np.zeros((count, 4, 4), float)}
    for source_id, mesh in enumerate(meshes):
        source_grid = mesh['grid']
        source_rows, source_columns = source_grid['shape_cells_zx']
        left = (source_grid['origin_x_m'] - grid['origin_x_m']) / grid['spacing_x_m']
        top = (source_grid['origin_z_m'] - grid['origin_z_m']) / grid['spacing_z_m']
        if not _i101_math.isclose(left, round(left), abs_tol=1e-08) or not _i101_math.isclose(top, round(top), abs_tol=1e-08):
            raise ValueError('incompatible domain grid origin')
        if source_grid['spacing_x_m'] != grid['spacing_x_m'] or source_grid['spacing_z_m'] != grid['spacing_z_m']:
            raise ValueError('domain precision mismatch')
        for row in range(source_rows):
            for column in range(source_columns):
                source_cell = row * source_columns + column
                target_cell = (round(top) + row) * columns + round(left) + column
                if owner[target_cell] != -1:
                    raise ValueError('overlapping domain cells')
                owner[target_cell] = source_id
                contributors['indices'][target_cell] = mesh['contributors']['indices'][source_cell]
                contributors['weights'][target_cell] = mesh['contributors']['weights'][source_cell]
    extension = _i101_np.flatnonzero(owner < 0)
    owner[extension] = len(meshes)
    seen = _i101_np.zeros(node_count, bool)
    for cell_id, cell in enumerate(cells):
        if cell_id % columns == 0:
            _surface_fine_mosaic_cancel(cancel)
        source_id = int(owner[cell_id])
        for corner, node_id in enumerate(cell):
            x, z = (nodes['x_m'][node_id], nodes['z_m'][node_id])
            if source_id == len(meshes):
                source_grid = _candidate_grid(candidate)
                source_shape = candidate['inputs']['height_m'].shape
                source_row = (z - source_grid['origin_z_m']) / source_grid['spacing_z_m']
                source_column = (x - source_grid['origin_x_m']) / source_grid['spacing_x_m']
                indices, weights = _surface_fine_mosaic_stencil(source_row, source_column, source_shape)
                contributors['indices'][cell_id, corner] = indices
                contributors['weights'][cell_id, corner] = weights
                height, protected = _extension_value(candidate, x, z, indices, weights)
                values = {'h0_m': height, 'h2_m': height, 'wet_mask': False, 'water_surface_m': 0.0, 'protected_mask': protected}
            else:
                mesh = meshes[source_id]
                source_grid = mesh['grid']
                source_row = round((z - source_grid['origin_z_m']) / source_grid['spacing_z_m'])
                source_column = round((x - source_grid['origin_x_m']) / source_grid['spacing_x_m'])
                source_node = source_row * (source_grid['shape_cells_zx'][1] + 1) + source_column
                values = {name: mesh['nodes'][name][source_node] for name in ('h0_m', 'h2_m', 'wet_mask', 'water_surface_m', 'protected_mask')}
            _check_node(nodes, node_id, values, seen)
    if _i101_np.any(~seen):
        raise ValueError('unowned nodes')
    wet_cells = nodes['wet_mask'][cells].all(axis=1)
    if _i101_np.any(wet_cells[extension]) or _i101_np.any(_i101_np.abs(nodes['h0_m'][cells[extension]] - nodes['h2_m'][cells[extension]]) > 1e-08):
        raise ValueError('extension wet or cut')
    output = {'nodes': nodes, 'cells': cells, 'triangles': triangles, 'cell_owner': owner.reshape(rows, columns), 'hydrologic_domain_owner': _domain_owner(record, cells, nodes, owner).reshape(rows, columns), 'contributors': contributors, 'wet_cells': wet_cells}
    area = grid['spacing_x_m'] * grid['spacing_z_m']
    cut = float(((nodes['h0_m'] - nodes['h2_m'])[triangles].mean(axis=1) * area / 2).sum())
    wet_triangles = triangles[_i101_np.repeat(wet_cells, 2)]
    water = float(((nodes['water_surface_m'] - nodes['h2_m'])[wet_triangles].mean(axis=1) * area / 2).sum())
    output['summary'] = {'unique_cell_area_m2': count * area, 'unique_cut_volume_m3': cut, 'actual_wet_water_volume_m3': water, 'q_outgoing_m3_s': sum((mesh['summary']['q_outgoing_m3_s'] for mesh in meshes)), 'q_incoming_m3_s': sum((mesh['summary']['q_incoming_m3_s'] for mesh in meshes)), 'q_local_m3_s': sum((mesh['summary']['q_local_m3_s'] for mesh in meshes))}
    output['extension_cell_count'] = len(extension)
    return output

def prepare_domain_mosaic(evaluation, *, resources=MosaicResources(), cancel=None):
    if not isinstance(resources, MosaicResources):
        raise ValueError('invalid resource limits')
    _surface_fine_mosaic_cancel(cancel)
    if _surface_fine_mosaic_size(evaluation) > resources.max_retained_bytes:
        raise ValueError('evaluation retained resource preflight')
    validate_surface_domains(evaluation)
    if evaluation['kind'] != 'evaluation' or len(evaluation['domains']) < 2:
        raise ValueError('prepared multiple domains required')
    candidate = evaluation['candidate']
    inputs = candidate['inputs']
    declared = []
    for domain in evaluation['domains']:
        fine = domain['recovery']['inputs']['fine']
        declared.append({'grid': {'origin_x_m': fine['origin_x_m'], 'origin_z_m': fine['origin_z_m'], 'spacing_x_m': fine['spacing_x_m'], 'spacing_z_m': fine['spacing_z_m'], 'bbox_xz_m': [fine['origin_x_m'], fine['origin_x_m'] + (fine['shape_zx'][1] - 1) * fine['spacing_x_m'], fine['origin_z_m'], fine['origin_z_m'] + (fine['shape_zx'][0] - 1) * fine['spacing_z_m']]}})
    preflight_grid = _grid(declared)
    preflight_cells = _i101_math.prod(preflight_grid['shape_cells_zx'])
    if preflight_cells > resources.max_cells or _surface_fine_mosaic_size(evaluation) + preflight_cells * 800 > min(resources.max_retained_bytes, resources.max_working_bytes):
        raise ValueError('domain mosaic resource preflight')
    meshes = []
    for domain in evaluation['domains']:
        _surface_fine_mosaic_cancel(cancel)
        mesh = prepare_fine_mosaic((DomainFineSource(domain['recovery'], domain['domain_id']),), metric_grid={'coordinate_system': 'metric-xz-m'}, vertical_datum=inputs['vertical_datum'], source_identity=candidate['identity_sha256'] + ':domain:' + str(domain['domain_id']), sea_level_elevation_m=inputs['sea_level_elevation_m'], resources=resources, cancel=cancel)
        meshes.append(mesh)
    grid = _grid(meshes)
    count = _i101_math.prod(grid['shape_cells_zx'])
    if count > resources.max_cells or _surface_fine_mosaic_size({'evaluation': evaluation, 'domain_meshes': meshes}) + count * 800 > min(resources.max_retained_bytes, resources.max_working_bytes):
        raise ValueError('domain mosaic resource preflight')
    record = {'algorithm_version': SURFACE_DOMAIN_MOSAIC_VERSION, 'status': 'prepared', 'scope': 'declared_rectangular_node_envelope', 'evaluation': _plain(evaluation), 'candidate_identity_sha256': candidate['identity_sha256'], 'domain_meshes': [_plain(mesh) for mesh in meshes], 'source_kinds': list(SOURCE_KINDS), 'grid': grid, 'resources': vars(resources), 'declared_node_envelope_complete': True, 'physical_footprint_complete': False, 'natural_outlets_certified': False, 'full_domain_mosaic_prepared': False}
    record.update(_assemble(record, cancel))
    sealed = _surface_fine_mosaic_seal(record)
    validate_domain_mosaic(sealed)
    return sealed

def validate_domain_mosaic(result):
    try:
        record = _plain(result)
        identity = record.pop('identity_sha256')
        if set(record) != {'algorithm_version', 'status', 'scope', 'evaluation', 'candidate_identity_sha256', 'domain_meshes', 'source_kinds', 'grid', 'resources', 'declared_node_envelope_complete', 'physical_footprint_complete', 'natural_outlets_certified', 'full_domain_mosaic_prepared', 'nodes', 'cells', 'triangles', 'cell_owner', 'hydrologic_domain_owner', 'contributors', 'wet_cells', 'summary', 'extension_cell_count'}:
            raise ValueError('invalid domain mosaic schema')
        if _identity(record) != identity or record['algorithm_version'] != SURFACE_DOMAIN_MOSAIC_VERSION or record['status'] != 'prepared':
            raise ValueError('domain mosaic identity/status mismatch')
        if record['scope'] != 'declared_rectangular_node_envelope' or record['source_kinds'] != list(SOURCE_KINDS) or record['declared_node_envelope_complete'] is not True or any((record[name] is not False for name in ('physical_footprint_complete', 'natural_outlets_certified', 'full_domain_mosaic_prepared'))):
            raise ValueError('invalid engineering scope')
        resources = MosaicResources(**record['resources'])
        if set(record['grid']) != {'coordinate_system', 'origin_x_m', 'origin_z_m', 'spacing_x_m', 'spacing_z_m', 'shape_cells_zx', 'bbox_xz_m'} or record['grid']['coordinate_system'] != 'metric-xz-m' or set(record['nodes']) != {'x_m', 'z_m', 'h0_m', 'h2_m', 'wet_mask', 'water_surface_m', 'protected_mask'} or (set(record['contributors']) != {'indices', 'weights'}):
            raise ValueError('invalid grid/node/contributor schema')
        rows, columns = record['grid']['shape_cells_zx']
        if type(rows) is not int or type(columns) is not int or rows <= 0 or (columns <= 0):
            raise ValueError('invalid grid shape')
        if rows * columns > resources.max_cells or _surface_fine_mosaic_size(result) > resources.max_retained_bytes or _surface_fine_mosaic_size(result) + rows * columns * 640 > resources.max_working_bytes:
            raise ValueError('domain mosaic resource limit')
        evaluation = record['evaluation']
        support = {}
        for mesh in record['domain_meshes']:
            for identity, saved in mesh['proof_h0_support'].items():
                if identity in support:
                    raise ValueError('duplicate domain recovery support')
                support[identity] = saved
        validate_surface_domains(evaluation, saved_support=support)
        if record['candidate_identity_sha256'] != evaluation['candidate']['identity_sha256'] or len(record['domain_meshes']) != len(evaluation['domains']):
            raise ValueError('candidate/domain identity mismatch')
        for mesh, domain in zip(record['domain_meshes'], evaluation['domains']):
            validate_fine_mosaic(mesh)
            fine = domain['recovery']['inputs']['fine']
            if len(mesh['sources']) != 1 or mesh['sources'][0]['domain_id'] != domain['domain_id'] or mesh['sources'][0]['proof_sha256'] != domain['recovery']['identity_sha256'] or (mesh['sources'][0]['window_zx'] != [0, fine['shape_zx'][0], 0, fine['shape_zx'][1]]) or (mesh['grid']['bbox_xz_m'] != [fine['origin_x_m'], fine['origin_x_m'] + (fine['shape_zx'][1] - 1) * fine['spacing_x_m'], fine['origin_z_m'], fine['origin_z_m'] + (fine['shape_zx'][0] - 1) * fine['spacing_z_m']]):
                raise ValueError('domain mesh proof binding mismatch')
            if mesh['grid']['spacing_x_m'] != record['grid']['spacing_x_m'] or mesh['grid']['spacing_z_m'] != record['grid']['spacing_z_m']:
                raise ValueError('domain precision mismatch')
        if record['grid'] != _grid(record['domain_meshes']):
            raise ValueError('declared envelope differs from saved domains')
        nodes, cells, triangles = (record['nodes'], record['cells'], record['triangles'])
        count = rows * columns
        if record['cell_owner'].dtype != _i101_np.int64 or record['cell_owner'].shape != (rows, columns) or cells.shape != (count, 4) or (cells.dtype != _i101_np.int64) or (triangles.shape != (2 * count, 3)) or (triangles.dtype != _i101_np.int64):
            raise ValueError('invalid saved topology')
        indices, weights = (record['contributors']['indices'], record['contributors']['weights'])
        if indices.shape != (count, 4, 4) or weights.shape != indices.shape or indices.dtype != _i101_np.int64 or (weights.dtype != _i101_np.float64):
            raise ValueError('invalid contributor arrays')
        for cell_id, cell in enumerate(cells):
            top_left = cell_id // columns * (columns + 1) + cell_id % columns
            if tuple(cell) != (top_left, top_left + 1, top_left + columns + 2, top_left + columns + 1) or tuple(triangles[2 * cell_id]) != tuple(cell[[0, 1, 2]]) or tuple(triangles[2 * cell_id + 1]) != tuple(cell[[0, 2, 3]]):
                raise ValueError('invalid unique cell/triangle topology')
        node_count = (rows + 1) * (columns + 1)
        expected_x = _i101_np.tile(record['grid']['origin_x_m'] + _i101_np.arange(columns + 1) * record['grid']['spacing_x_m'], rows + 1)
        expected_z = _i101_np.repeat(record['grid']['origin_z_m'] + _i101_np.arange(rows + 1) * record['grid']['spacing_z_m'], columns + 1)
        if nodes['x_m'].dtype != _i101_np.float64 or nodes['z_m'].dtype != _i101_np.float64 or nodes['x_m'].shape != (node_count,) or (nodes['z_m'].shape != (node_count,)) or (not _i101_np.array_equal(nodes['x_m'], expected_x)) or (not _i101_np.array_equal(nodes['z_m'], expected_z)):
            raise ValueError('invalid saved node coordinates')
        for name in ('h0_m', 'h2_m', 'wet_mask', 'water_surface_m', 'protected_mask'):
            if nodes[name].shape != (node_count,) or nodes[name].dtype != (bool if name.endswith('mask') else _i101_np.float64) or (not _i101_np.isfinite(nodes[name]).all()):
                raise ValueError('invalid saved node fields')
        seen = _i101_np.zeros(node_count, bool)
        expected_owner = _i101_np.full(count, len(record['domain_meshes']), _i101_np.int64)
        for source_id, mesh in enumerate(record['domain_meshes']):
            source_grid = mesh['grid']
            top = round((source_grid['origin_z_m'] - record['grid']['origin_z_m']) / record['grid']['spacing_z_m'])
            left = round((source_grid['origin_x_m'] - record['grid']['origin_x_m']) / record['grid']['spacing_x_m'])
            source_rows, source_columns = source_grid['shape_cells_zx']
            for row in range(source_rows):
                for column in range(source_columns):
                    cell_id = (top + row) * columns + left + column
                    if expected_owner[cell_id] != len(record['domain_meshes']):
                        raise ValueError('overlapping saved domain footprint')
                    expected_owner[cell_id] = source_id
        if not _i101_np.array_equal(record['cell_owner'].ravel(), expected_owner):
            raise ValueError('saved cell owner differs from domains')
        if record['hydrologic_domain_owner'].dtype != _i101_np.int64 or record['hydrologic_domain_owner'].shape != (rows, columns) or (not _i101_np.array_equal(record['hydrologic_domain_owner'].ravel(), _domain_owner(record, cells, nodes, expected_owner))):
            raise ValueError('saved hydrologic domain owner differs from candidate labels')
        candidate = evaluation['candidate']
        for cell_id, cell in enumerate(cells):
            source_id = int(expected_owner[cell_id])
            for corner, node_id in enumerate(cell):
                x, z = (nodes['x_m'][node_id], nodes['z_m'][node_id])
                if source_id == len(record['domain_meshes']):
                    height, protected = _extension_value(candidate, x, z, indices[cell_id, corner], weights[cell_id, corner])
                    values = {'h0_m': height, 'h2_m': height, 'wet_mask': False, 'water_surface_m': 0.0, 'protected_mask': protected}
                else:
                    mesh = record['domain_meshes'][source_id]
                    source_grid = mesh['grid']
                    source_row = round((z - source_grid['origin_z_m']) / source_grid['spacing_z_m'])
                    source_column = round((x - source_grid['origin_x_m']) / source_grid['spacing_x_m'])
                    cell_top = round((nodes['z_m'][cell[0]] - source_grid['origin_z_m']) / source_grid['spacing_z_m'])
                    cell_left = round((nodes['x_m'][cell[0]] - source_grid['origin_x_m']) / source_grid['spacing_x_m'])
                    source_cell = cell_top * source_grid['shape_cells_zx'][1] + cell_left
                    if not _i101_np.array_equal(indices[cell_id, corner], mesh['contributors']['indices'][source_cell, corner]) or not _i101_np.array_equal(weights[cell_id, corner], mesh['contributors']['weights'][source_cell, corner]):
                        raise ValueError('saved domain contributor differs')
                    source_node = source_row * (source_grid['shape_cells_zx'][1] + 1) + source_column
                    values = {name: mesh['nodes'][name][source_node] for name in ('h0_m', 'h2_m', 'wet_mask', 'water_surface_m', 'protected_mask')}
                for name, value in values.items():
                    if nodes[name][node_id] != value if isinstance(value, (bool, _i101_np.bool_)) else abs(nodes[name][node_id] - value) > 1e-08:
                        raise ValueError('saved node disagrees with domain/extension support')
                seen[node_id] = True
        if not _i101_np.all(seen) or type(record['extension_cell_count']) is not int or record['extension_cell_count'] != int(_i101_np.count_nonzero(expected_owner == len(record['domain_meshes']))):
            raise ValueError('incomplete saved node envelope')
        wet_cells = nodes['wet_mask'][cells].all(axis=1)
        if record['wet_cells'].dtype != bool or record['wet_cells'].shape != (count,) or (not _i101_np.array_equal(record['wet_cells'], wet_cells)) or _i101_np.any(wet_cells[expected_owner == len(record['domain_meshes'])]):
            raise ValueError('extension contains wet cells')
        area = record['grid']['spacing_x_m'] * record['grid']['spacing_z_m']
        cut = float(((nodes['h0_m'] - nodes['h2_m'])[triangles].mean(axis=1) * area / 2).sum())
        wet_triangles = triangles[_i101_np.repeat(wet_cells, 2)]
        water = float(((nodes['water_surface_m'] - nodes['h2_m'])[wet_triangles].mean(axis=1) * area / 2).sum())
        expected_summary = {'unique_cell_area_m2': count * area, 'unique_cut_volume_m3': cut, 'actual_wet_water_volume_m3': water}
        for name in ('q_outgoing_m3_s', 'q_incoming_m3_s', 'q_local_m3_s'):
            expected_summary[name] = sum((mesh['summary'][name] for mesh in record['domain_meshes']))
        if set(record['summary']) != set(expected_summary) or any((not _i101_np.isfinite(record['summary'][name]) or not _i101_np.isclose(record['summary'][name], value, rtol=1e-12, atol=1e-09) for name, value in expected_summary.items())):
            raise ValueError('saved volume or Q ledger differs')
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError('invalid domain mosaic semantic record') from error

def save_domain_mosaic(result, path):
    validate_domain_mosaic(result)
    destination = _i101_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = _surface_fine_mosaic_tree(result, arrays)
    manifest = {'format_version': 3, 'tree': tree, 'tree_sha256': _identity(tree)}
    descriptor, temporary_name = _i101_tempfile.mkstemp(prefix='.' + destination.name + '-', suffix='.tmp', dir=destination.parent)
    temporary = _i101_Path(temporary_name)
    try:
        with _i101_os.fdopen(descriptor, 'w+b') as stream:
            with _i101_zipfile.ZipFile(stream, 'w', compression=_i101_zipfile.ZIP_STORED) as archive:
                archive.writestr('manifest.json', _surface_fine_mosaic_json(manifest))
                for name, array in arrays.items():
                    with _i101_io.BytesIO() as payload:
                        _i101_np.save(payload, _i101_np.ascontiguousarray(array), allow_pickle=False)
                        archive.writestr(name, payload.getvalue())
            stream.flush()
            _i101_os.fsync(stream.fileno())
        with _i101_zipfile.ZipFile(temporary) as archive:
            _preflight_archive(archive)
        _i101_os.link(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)

def load_domain_mosaic(path):
    from terrain_pipeline.artifacts.contracts import array_hash as _i105_array_hash
    try:
        with _i101_Path(path).open('rb') as retained, _i101_zipfile.ZipFile(retained) as archive:
            if _i101_os.fstat(retained.fileno()).st_size > SURFACE_FINE_MOSAIC_MAX_BYTES:
                raise ValueError('domain mosaic file byte cap')
            _preflight_archive(archive)
            manifest = _i101_json.loads(archive.read('manifest.json'), object_pairs_hook=_surface_fine_mosaic_pairs, parse_constant=_surface_fine_mosaic_constant)
            if set(manifest) != {'format_version', 'tree', 'tree_sha256'} or manifest['format_version'] != 3 or manifest['tree_sha256'] != _identity(manifest['tree']):
                raise ValueError('domain mosaic manifest mismatch')
            tree = manifest['tree']
            resources = MosaicResources(**tree['resources'])
            rows, columns = tree['grid']['shape_cells_zx']
            if type(rows) is not int or type(columns) is not int or rows <= 0 or (columns <= 0) or (rows * columns > resources.max_cells) or (sum((entry.file_size for entry in archive.infolist())) > resources.max_retained_bytes) or (sum((entry.file_size for entry in archive.infolist())) + rows * columns * 640 > resources.max_working_bytes):
                raise ValueError('archive JSON resource preflight')
            arrays = {}
            for name in archive.namelist():
                if name.endswith('.npy'):
                    with archive.open(name) as stream:
                        arrays[name] = _i101_np.load(stream, allow_pickle=False)
            used = set()

            def decode(value):
                if isinstance(value, dict) and '$array' in value:
                    name = value['$array']
                    if set(value) != {'$array', 'dtype', 'shape', 'sha256'} or name in used or name not in arrays:
                        raise ValueError('invalid/duplicate array reference')
                    array = arrays[name]
                    if value['dtype'] != array.dtype.str or value['shape'] != list(array.shape) or value['sha256'] != _i105_array_hash(array):
                        raise ValueError('array hash/shape mismatch')
                    used.add(name)
                    return array
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value
            result = decode(tree)
            if used != set(arrays):
                raise ValueError('unreferenced arrays')
        validate_domain_mosaic(result)
        return _freeze(result)
    except (OSError, KeyError, TypeError, _i101_json.JSONDecodeError, _i101_zipfile.BadZipFile, EOFError) as error:
        raise ValueError('invalid domain mosaic bundle') from error
SURFACE_MULTIDOMAIN_DYNAMIC_VERSION = 'surface-multidomain-dynamic-v1'
from terrain_pipeline.surface_hydraulics import LEDGER_COLUMNS as _x101_LEDGER_COLUMNS
LEDGER_COLUMNS = _x101_LEDGER_COLUMNS

@_i107_dataclass(frozen=True)
class ForestResources:
    max_domains: int = 64
    max_wet_cells: int = 100000
    max_assignment_work: int = 2000000
    max_retained_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES
    max_working_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES

    def __post_init__(self):
        ceilings = (64, 100000, 2000000, SURFACE_FINE_MOSAIC_MAX_BYTES, SURFACE_FINE_MOSAIC_MAX_BYTES)
        for field, ceiling in zip(_i107_fields(self), ceilings):
            value = getattr(self, field.name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError('invalid forest resource: ' + field.name)

def _domains(evaluation, resources=None, *, full_validation=False):
    if resources is not None:
        if _surface_fine_mosaic_size(evaluation) > resources.max_retained_bytes:
            raise ValueError('forest source retained bytes exceeded')
        if len(evaluation['domains']) > resources.max_domains:
            raise ValueError('forest domain count exceeded')
    if full_validation:
        validate_surface_domains(evaluation)
    else:
        if _hash({key: value for key, value in evaluation.items() if key != 'identity_sha256'}) != evaluation['identity_sha256']:
            raise ValueError('evaluation identity mismatch')
        validate_surface_domains(evaluation['candidate'], allow_unprepared=True)
    if evaluation['kind'] != 'evaluation' or evaluation['status'] != 'prepared':
        raise ValueError('all declared domains must be prepared')
    domains = evaluation['domains']
    ids = [entry['domain_id'] for entry in domains]
    if not ids or ids != [entry['domain_id'] for entry in evaluation['candidate']['domains']] or set(evaluation['configurations']) != {str(domain_id) for domain_id in ids} or any((type(domain_id) is not int or domain_id <= 0 for domain_id in ids)) or (ids != sorted(set(ids))) or any((entry['status'] != 'prepared' or entry['recovery'] is None or entry['recovery']['accepted'] is not True for entry in domains)):
        raise ValueError('every declared domain requires accepted recovery')
    return ids

def _layout(bindings, ids):
    offsets = [0]
    edge_offsets = [0]
    for binding in bindings:
        offsets.append(offsets[-1] + len(binding['node_flat_ids']))
        edge_offsets.append(edge_offsets[-1] + len(binding['edges']))
    keys = _i107_np.concatenate([_i107_np.column_stack((_i107_np.full(len(binding['node_flat_ids']), domain_id, _i107_np.int64), binding['node_flat_ids'])) for domain_id, binding in zip(ids, bindings)])
    edges = _i107_np.concatenate([binding['edges'] + offsets[index] for index, binding in enumerate(bindings)]).reshape(-1, 2)
    return (_i107_np.asarray(offsets, _i107_np.int64), _i107_np.asarray(edge_offsets, _i107_np.int64), keys, edges)

def _input(bindings, offsets, edges, conductance_m2_s, local_q_m3_s, tailwater_m, dt_s, max_depth_m, limits, source, datum):
    from terrain_pipeline.surface_hydraulics import _preflight as _x102_preflight
    from terrain_pipeline.surface_hydraulics import HydraulicsInput as _x103_HydraulicsInput
    count = int(offsets[-1])
    boundary = _i107_np.concatenate([binding['boundary_mask'] for binding in bindings])
    local = _i107_np.asarray(local_q_m3_s)
    tailwater = _i107_np.asarray(tailwater_m)
    if local.ndim != 2 or local.shape[1] != count or local.shape[0] < 1:
        raise ValueError('explicit local Q[T,globalN] required')
    if tailwater.shape != (len(local) + 1, int(boundary.sum())):
        raise ValueError('explicit tailwater[T+1,all outlets] required')
    _x102_preflight(count, len(edges), len(local), limits)
    boundary_stage = _i107_np.zeros((len(local) + 1, count))
    boundary_stage[:, boundary] = tailwater
    return _x103_HydraulicsInput(bed_m=_i107_np.concatenate([binding['bed_m'] for binding in bindings]), area_m2=_i107_np.concatenate([binding['area_m2'] for binding in bindings]), initial_stage_m=_i107_np.concatenate([binding['initial_stage_m'] for binding in bindings]), edges=edges, conductance_m2_s=conductance_m2_s, local_q_m3_s=local, boundary_mask=boundary, boundary_stage_m=boundary_stage, dt_s=dt_s, max_depth_m=max_depth_m, valid_mask=_i107_np.ones(count, bool), protected_mask=_i107_np.zeros(count, bool), coords_m=_i107_np.concatenate([binding['coords_xz_m'] for binding in bindings]), source=source, datum=datum, coords='metric-xz-m', limits=limits)

def _domain_ledgers(dynamic, offsets, edge_offsets):
    inputs = dynamic.inputs
    rows = _i107_np.empty((dynamic.committed_steps, len(offsets) - 1, 6))
    for step in range(dynamic.committed_steps):
        for index in range(len(offsets) - 1):
            start, stop = (int(offsets[index]), int(offsets[index + 1]))
            first, last = (int(edge_offsets[index]), int(edge_offsets[index + 1]))
            net = _i107_np.zeros(stop - start)
            edges = inputs.edges[first:last] - start
            flux = dynamic.qedges_m3_s[step, first:last]
            _i107_np.add.at(net, edges[:, 0], -flux)
            _i107_np.add.at(net, edges[:, 1], flux)
            before = float(dynamic.storage_m3[step, start:stop].sum())
            after = float(dynamic.storage_m3[step + 1, start:stop].sum())
            boundary = inputs.boundary_mask[start:stop]
            local = float(inputs.dt_s * inputs.local_q_m3_s[step, start:stop][~boundary].sum())
            inward = float(-inputs.dt_s * net[boundary].sum())
            rows[step, index] = (before, local, inward, after, after - before, after - before - local - inward)
    return rows

def _gate(record):
    required = {'algorithm_version', 'kind', 'evaluation', 'bindings', 'resources', 'domain_ids', 'node_offsets', 'edge_offsets', 'node_keys', 'edges', 'dynamic', 'domain_ledger_m3', 'identity_sha256', 'natural_outlets_certified', 'full_dynamic_wave_prepared'}
    if set(record) != required or record['algorithm_version'] != SURFACE_MULTIDOMAIN_DYNAMIC_VERSION or record['kind'] != 'forest' or (record['natural_outlets_certified'] is not False) or (record['full_dynamic_wave_prepared'] is not False) or (record['identity_sha256'] != _identity({key: value for key, value in record.items() if key != 'identity_sha256'})):
        raise ValueError('forest schema/identity mismatch')
    resources = ForestResources(**record['resources'])
    if _surface_fine_mosaic_size(record) > resources.max_retained_bytes or _surface_fine_mosaic_size(record) * 2 > resources.max_working_bytes:
        raise ValueError('forest retained/working bytes exceeded')
    return resources

def validate_surface_multidomain_dynamic(record):
    """Static verification of source, mapping, dynamics, prefix and per-domain accounts."""
    from terrain_pipeline.surface_hydraulics import validate as _x104_validate
    try:
        resources = _gate(record)
        ids = _domains(record['evaluation'], resources)
        bindings = record['bindings']
        if len(ids) > resources.max_domains or len(bindings) != len(ids) or any((type(value) is not int or value <= 0 for value in record['domain_ids'])) or (list(record['domain_ids']) != ids):
            raise ValueError('omitted or duplicate domain')
        datum = record['evaluation']['candidate']['inputs']['vertical_datum']
        wet_count = 0
        assignment_work = 0
        for domain_id, binding, entry in zip(ids, bindings, record['evaluation']['domains']):
            validate_surface_dynamic_binding(binding)
            sources = binding['source_mosaic']['sources']
            if binding['source_proof_sha256'] != entry['recovery']['identity_sha256'] or binding['vertical_datum'] != datum or len(sources) != 1 or (sources[0]['domain_id'] != domain_id) or (binding['source_mosaic']['proofs'][binding['source_proof_sha256']]['identity_sha256'] != entry['recovery']['identity_sha256']):
                raise ValueError('binding does not belong to declared domain/proof')
            wet_count += len(binding['wet_cell_ids'])
            assignment_work += len(binding['wet_cell_ids']) * len(binding['node_flat_ids'])
        if wet_count > resources.max_wet_cells or assignment_work > resources.max_assignment_work:
            raise ValueError('forest wet assignment resource exceeded')
        offsets, edge_offsets, keys, edges = _layout(bindings, ids)
        for name, expected in (('node_offsets', offsets), ('edge_offsets', edge_offsets), ('node_keys', keys), ('edges', edges)):
            actual = record[name]
            if actual.dtype != _i107_np.dtype('int64') or not _i107_np.array_equal(actual, expected):
                raise ValueError('forest mapping differs: ' + name)
        dynamic = _unpack_dynamic(record['dynamic'])
        usage = _x104_validate(dynamic)
        inputs = dynamic.inputs
        if inputs.source != record['evaluation']['identity_sha256'] or inputs.datum != datum:
            raise ValueError('global source/datum mismatch')
        for name, expected in (('bed_m', _i107_np.concatenate([item['bed_m'] for item in bindings])), ('area_m2', _i107_np.concatenate([item['area_m2'] for item in bindings])), ('initial_stage_m', _i107_np.concatenate([item['initial_stage_m'] for item in bindings])), ('boundary_mask', _i107_np.concatenate([item['boundary_mask'] for item in bindings])), ('coords_m', _i107_np.concatenate([item['coords_xz_m'] for item in bindings])), ('edges', edges)):
            if not _i107_np.array_equal(getattr(inputs, name), expected):
                raise ValueError('global input differs from source: ' + name)
        if inputs.coords != 'metric-xz-m' or not _i107_np.all(inputs.valid_mask) or _i107_np.any(inputs.protected_mask) or (record['dynamic']['status'] != dynamic.status):
            raise ValueError('global input geometry/status differs')
        if _i107_np.any(inputs.boundary_stage_m[:, ~inputs.boundary_mask] != 0):
            raise ValueError('non-boundary tailwater')
        expected = _domain_ledgers(dynamic, offsets, edge_offsets)
        actual = record['domain_ledger_m3']
        if actual.dtype != _i107_np.dtype('float64') or actual.shape != expected.shape or (not _i107_np.allclose(actual, expected, atol=1e-10, rtol=0)):
            raise ValueError('per-domain ledger differs')
        if not _i107_np.allclose(actual.sum(axis=1), dynamic.ledger_m3, atol=1e-10, rtol=0):
            raise ValueError('domain ledgers do not sum to global ledger')
        if _surface_fine_mosaic_size(record) + usage['resources']['retained_bytes_upper_bound'] > resources.max_working_bytes:
            raise ValueError('forest dynamic working bytes exceeded')
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError('invalid saved forest') from error
from terrain_pipeline.surface_hydraulics import ResourceLimits as _x105_ResourceLimits

def prepare_surface_multidomain_dynamic(evaluation, *, conductance_m2_s, local_q_m3_s, tailwater_m, dt_s, max_depth_m, resources=ForestResources(), limits=_x105_ResourceLimits(), cancel=None):
    """Bind all accepted domains, then advance one synchronous global graph."""
    from terrain_pipeline.surface_hydraulics import _preflight as _x102_preflight
    from terrain_pipeline.surface_hydraulics import evaluate as _x106_evaluate
    if not isinstance(resources, ForestResources):
        raise ValueError('ForestResources required')
    ids = _domains(evaluation, resources, full_validation=True)
    node_count = 0
    edge_count = 0
    for entry in evaluation['domains']:
        payload = _payload(_plain(entry['recovery']))
        active = _i107_np.flatnonzero(payload['active_mask'])
        node_count += len(active)
        edge_count += int(_i107_np.count_nonzero(payload['receiver'][active] >= 0))
    usage = _x102_preflight(node_count, edge_count, len(_i107_np.asarray(local_q_m3_s)), limits)
    if _surface_fine_mosaic_size(evaluation) + usage['retained_bytes_upper_bound'] > resources.max_working_bytes:
        raise ValueError('forest planned working bytes exceeded')
    datum = evaluation['candidate']['inputs']['vertical_datum']
    bound_resources = DynamicPrepareResources(max_wet_cells=resources.max_wet_cells, max_assignment_work=resources.max_assignment_work, max_retained_bytes=resources.max_retained_bytes, max_working_bytes=resources.max_working_bytes)
    bindings = []
    wet_count = 0
    assignment_work = 0
    for domain_id in ids:
        if cancel is not None and cancel():
            raise InterruptedError('forest binding cancelled')
        bindings.append(bind_surface_dynamic_source(evaluation, domain_id=domain_id, vertical_datum=datum, resources=bound_resources))
        wet_count += len(bindings[-1]['wet_cell_ids'])
        assignment_work += len(bindings[-1]['wet_cell_ids']) * len(bindings[-1]['node_flat_ids'])
        if wet_count > resources.max_wet_cells or assignment_work > resources.max_assignment_work:
            raise ValueError('forest total wet assignment resource exceeded')
        if _surface_fine_mosaic_size({'evaluation': evaluation, 'bindings': bindings}) * 2 > resources.max_working_bytes:
            raise ValueError('forest binding working bytes exceeded')
    offsets, edge_offsets, keys, edges = _layout(bindings, ids)
    usage = _x102_preflight(len(keys), len(edges), len(_i107_np.asarray(local_q_m3_s)), limits)
    if (_surface_fine_mosaic_size({'evaluation': evaluation, 'bindings': bindings}) + usage['retained_bytes_upper_bound']) * 2 > resources.max_working_bytes:
        raise ValueError('forest dynamic working bytes exceeded')
    inputs = _input(bindings, offsets, edges, conductance_m2_s, local_q_m3_s, tailwater_m, dt_s, max_depth_m, limits, evaluation['identity_sha256'], datum)
    dynamic = _x106_evaluate(inputs, cancel=cancel)
    record = {'algorithm_version': SURFACE_MULTIDOMAIN_DYNAMIC_VERSION, 'kind': 'forest', 'evaluation': evaluation, 'bindings': bindings, 'resources': _i107_asdict(resources), 'domain_ids': ids, 'node_offsets': offsets, 'edge_offsets': edge_offsets, 'node_keys': keys, 'edges': edges, 'dynamic': _pack_dynamic(dynamic), 'domain_ledger_m3': _domain_ledgers(dynamic, offsets, edge_offsets), 'natural_outlets_certified': False, 'full_dynamic_wave_prepared': False}
    sealed = _surface_dynamic_prepare_seal(record)
    validate_surface_multidomain_dynamic(sealed)
    return sealed

def query_surface_multidomain_dynamic(record, *, state_index=None):
    validate_surface_multidomain_dynamic(record)
    dynamic = record['dynamic']
    if state_index is not None and (type(state_index) is not int or not 0 <= state_index <= dynamic['committed_steps']):
        raise ValueError('state index outside committed prefix')
    selection = slice(None) if state_index is None else state_index
    return _freeze({'node_keys': record['node_keys'], 'stage_m': dynamic['stage_m'][selection], 'storage_m3': dynamic['storage_m3'][selection], 'time_s': dynamic['time_s'][selection], 'status': dynamic['status']})

def save_surface_multidomain_dynamic(record, path):
    validate_surface_multidomain_dynamic(record)
    destination = _i107_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = _surface_fine_mosaic_tree(record, arrays)
    manifest = _surface_fine_mosaic_json({'format_version': 1, 'tree': tree, 'tree_sha256': _identity(tree)})
    descriptor, temporary = _i107_tempfile.mkstemp(prefix='.forest-', suffix='.tmp', dir=destination.parent)
    try:
        stream = _i107_os.fdopen(descriptor, 'w+b')
        descriptor = None
        with stream:
            with _i107_zipfile.ZipFile(stream, 'w', compression=_i107_zipfile.ZIP_STORED) as archive:
                archive.writestr('manifest.json', manifest)
                for name, array in arrays.items():
                    with archive.open(name, 'w') as member:
                        _i107_np.lib.format.write_array(member, _i107_np.ascontiguousarray(array), version=(1, 0), allow_pickle=False)
            if stream.tell() > SURFACE_FINE_MOSAIC_MAX_BYTES:
                raise ValueError('forest bundle cap')
            stream.flush()
            _i107_os.fsync(stream.fileno())
        _i107_os.link(temporary, destination)
        return destination
    finally:
        if descriptor is not None:
            _i107_os.close(descriptor)
        _i107_Path(temporary).unlink(missing_ok=True)

def load_surface_multidomain_dynamic(path):
    """Bounded static ZIP/NPY read; never bind, prepare or advance."""
    from terrain_pipeline.artifacts.contracts import array_hash as _i105_array_hash
    from terrain_pipeline.surface_hydraulics import _preflight as _x102_preflight
    try:
        with _i107_Path(path).open('rb') as retained, _i107_zipfile.ZipFile(retained) as archive:
            if _i107_os.fstat(retained.fileno()).st_size > SURFACE_FINE_MOSAIC_MAX_BYTES:
                raise ValueError('forest bundle cap')
            _preflight_archive(archive)
            manifest = _i107_json.loads(archive.read('manifest.json'), object_pairs_hook=_surface_fine_mosaic_pairs, parse_constant=_surface_fine_mosaic_constant)
            if set(manifest) != {'format_version', 'tree', 'tree_sha256'} or manifest['format_version'] != 1 or manifest['tree_sha256'] != _identity(manifest['tree']):
                raise ValueError('forest manifest identity mismatch')
            tree = manifest['tree']
            resources = ForestResources(**tree['resources'])
            if set(tree) != {'algorithm_version', 'kind', 'evaluation', 'bindings', 'resources', 'domain_ids', 'node_offsets', 'edge_offsets', 'node_keys', 'edges', 'dynamic', 'domain_ledger_m3', 'identity_sha256', 'natural_outlets_certified', 'full_dynamic_wave_prepared'}:
                raise ValueError('forest tree schema mismatch')
            count = tree['node_keys']['shape'][0]
            edges = tree['edges']['shape'][0]
            steps = tree['dynamic']['inputs']['local_q_m3_s']['shape'][0]
            limits = _x105_ResourceLimits(**tree['dynamic']['inputs']['limits'])
            usage = _x102_preflight(count, edges, steps, limits)
            size = sum((info.file_size for info in archive.infolist()))
            if size > resources.max_retained_bytes or size * 2 > resources.max_working_bytes or usage['retained_bytes_upper_bound'] > resources.max_working_bytes or (len(tree['bindings']) > resources.max_domains):
                raise ValueError('forest JSON resource preflight')
            references = {}

            def collect(value):
                if isinstance(value, dict) and '$array' in value:
                    name = value['$array']
                    if set(value) != {'$array', 'shape', 'dtype', 'sha256'} or name in references:
                        raise ValueError('duplicate/invalid array reference')
                    references[name] = value
                elif isinstance(value, dict):
                    for child in value.values():
                        collect(child)
                elif isinstance(value, list):
                    for child in value:
                        collect(child)
            collect(tree)
            if set(references) != set(archive.namelist()) - {'manifest.json'}:
                raise ValueError('missing/unused array')
            for name, reference in references.items():
                with archive.open(name) as member:
                    if _i107_np.lib.format.read_magic(member) != (1, 0):
                        raise ValueError('NPY v1 required')
                    shape, fortran, dtype = _i107_np.lib.format.read_array_header_1_0(member, max_header_size=8192)
                    if list(shape) != reference['shape'] or dtype.str != reference['dtype'] or fortran or dtype.hasobject or (dtype.kind not in 'biuf') or (member.tell() + int(_i107_np.prod(shape, dtype=_i107_np.int64)) * dtype.itemsize != archive.getinfo(name).file_size):
                        raise ValueError('array header differs')

            def decode(value):
                if isinstance(value, dict) and '$array' in value:
                    with archive.open(value['$array']) as member:
                        array = _i107_np.load(member, allow_pickle=False)
                    if _i105_array_hash(array) != value['sha256']:
                        raise ValueError('array hash differs')
                    return array
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value
            record = decode(tree)
        validate_surface_multidomain_dynamic(record)
        return _freeze(record)
    except (OSError, KeyError, TypeError, IndexError, AttributeError, EOFError, _i107_zipfile.BadZipFile) as error:
        raise ValueError('invalid forest bundle') from error
SURFACE_ENGINEERING_PREPARE_VERSION = 'surface-engineering-prepare-v1'

@_i104_dataclass(frozen=True)
class EngineeringResources:
    max_retained_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES
    max_working_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES
    max_archive_members: int = 2048

    def __post_init__(self):
        for name, ceiling in (('max_retained_bytes', SURFACE_FINE_MOSAIC_MAX_BYTES), ('max_working_bytes', SURFACE_FINE_MOSAIC_MAX_BYTES), ('max_archive_members', 2048)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError('invalid engineering resource: ' + name)

def _cancel(cancel):
    if cancel is not None and cancel():
        raise InterruptedError('engineering prepare cancelled')

def _ids(evaluation, *, full_validation=False, saved_support=None):
    if full_validation:
        validate_surface_domains(evaluation)
    elif saved_support is not None:
        validate_surface_domains(evaluation, saved_support=saved_support)
    else:
        _domains(evaluation, full_validation=False)
    if evaluation['kind'] != 'evaluation' or evaluation['status'] != 'prepared':
        raise ValueError('accepted domain evaluation required')
    ids = [item['domain_id'] for item in evaluation['domains']]
    if not ids or any((type(domain_id) is not int for domain_id in ids)) or ids != sorted(set(ids)) or (ids != [item['domain_id'] for item in evaluation['candidate']['domains']]):
        raise ValueError('all declared domains required')
    return ids

def _size(record):
    return _retained(record, SURFACE_FINE_MOSAIC_MAX_BYTES)

def _strict_header(header):
    try:
        expression = _i104_ast.parse(header.decode('latin1').strip(), mode='eval').body
        if not isinstance(expression, _i104_ast.Dict) or len(expression.keys) != 3:
            raise ValueError('NPY header dictionary required')
        keys = [_i104_ast.literal_eval(key) for key in expression.keys]
        if any((type(key) is not str for key in keys)) or set(keys) != {'descr', 'fortran_order', 'shape'}:
            raise ValueError('NPY header duplicate/unknown keys')
        values = {key: _i104_ast.literal_eval(value) for key, value in zip(keys, expression.values)}
        if type(values['descr']) is not str or type(values['fortran_order']) is not bool or values['fortran_order'] is not False or (type(values['shape']) is not tuple) or (len(values['shape']) > 4) or any((type(size) is not int or not 0 <= size <= 1000000 for size in values['shape'])):
            raise ValueError('NPY strict header types')
        return (values['shape'], values['fortran_order'], _i104_np.dtype(values['descr']))
    except (SyntaxError, TypeError, UnicodeError, RecursionError) as error:
        raise ValueError('invalid NPY header') from error

def _planned_bytes(evaluation, outlets, local_q, variable_forcing):
    from terrain_pipeline import surface_hydraulics as _i107_hydraulics
    source = _size(evaluation)
    declared = []
    fine_cells = nodes = edges = 0
    drop_bytes = 0
    for entry in evaluation['domains']:
        fine = entry['recovery']['inputs']['fine']
        rows, columns = fine['shape_zx']
        fine_cells += (rows - 1) * (columns - 1)
        declared.append({'grid': {'origin_x_m': fine['origin_x_m'], 'origin_z_m': fine['origin_z_m'], 'spacing_x_m': fine['spacing_x_m'], 'spacing_z_m': fine['spacing_z_m'], 'bbox_xz_m': [fine['origin_x_m'], fine['origin_x_m'] + (columns - 1) * fine['spacing_x_m'], fine['origin_z_m'], fine['origin_z_m'] + (rows - 1) * fine['spacing_z_m']]}})
        payload = _payload(entry['recovery'])
        active = _i104_np.flatnonzero(payload['active_mask'])
        nodes += len(active)
        edges += int(_i104_np.count_nonzero(payload['receiver'][active] >= 0))
        supplied = outlets[entry['domain_id']]
        attachment = supplied['attachment']
        record = {'prepared': attachment.prepared, 'domain_id': attachment.domain_id, 'cross_section_xz_m': attachment.cross_section_xz_m, 'center_index': attachment.center_index, 'datum': attachment.datum}
        usage = _preflight(record, _source_record(supplied['corridor']), _source_record(supplied['sea']), _i104_np.asarray(supplied['stations_z_m']), DropResources())
        drop_bytes += usage['retained_bytes_upper_bound']
    cells = _i104_math.prod(_grid(declared)['shape_cells_zx'])
    local = _i104_np.asarray(local_q)
    if local.ndim != 2 or local.shape[1] != nodes or (not len(local)):
        raise ValueError('explicit global local Q required')
    dynamic = _i107_hydraulics._preflight(nodes, edges, len(local), _i107_hydraulics.ResourceLimits())
    mosaic_bytes = 2 * source + (cells + fine_cells) * 800
    forest_bytes = (len(declared) + 1) * source + fine_cells * 800 + dynamic['retained_bytes_upper_bound']
    retained = source + mosaic_bytes + drop_bytes + forest_bytes
    if variable_forcing is not None:
        variable_local = _i104_np.asarray(variable_forcing['local_q_m3_s'])
        if variable_local.ndim != 2 or variable_local.shape[1] != nodes or (not len(variable_local)):
            raise ValueError('explicit variable global local Q required')
        steps = len(variable_local)
        retained += forest_bytes + fine_cells * 6 * 32 + (steps + 1) * nodes * 32
        retained += steps * (edges + 6 * len(declared) + nodes) * 16
        retained += _size({key: _i104_asdict(value) if key == 'resources' else value for key, value in variable_forcing.items()})
    return (retained, retained * 2)

def compose_surface_engineering(evaluation, domain_mosaic, drops, dynamic_forest, *, variable_storage=None, resources=EngineeringResources(), cancel=None):
    """Compose already prepared components without replaying any preparation."""
    _cancel(cancel)
    if not isinstance(resources, EngineeringResources):
        raise ValueError('EngineeringResources required')
    ids = _ids(evaluation, full_validation=True)
    source_size = _size({'evaluation': evaluation, 'mosaic': domain_mosaic, 'drops': drops, 'forest': dynamic_forest, 'variable_storage': variable_storage})
    if source_size > resources.max_retained_bytes or source_size * 2 > resources.max_working_bytes:
        raise ValueError('engineering retained preflight')
    record = {'algorithm_version': SURFACE_ENGINEERING_PREPARE_VERSION, 'status': 'prepared', 'evaluation': evaluation, 'domain_mosaic': domain_mosaic, 'drops': list(drops), 'dynamic_forest': dynamic_forest, 'variable_storage': variable_storage, 'domain_ids': ids, 'resources': _i104_asdict(resources), 'declared_node_envelope_complete': True, 'physical_footprint_complete': False, 'natural_outlets_certified': False, 'full_dynamic_wave_prepared': False, 'ready_for_3d': False}
    sealed = _freeze({**record, 'identity_sha256': fingerprint(record)})
    validate_surface_engineering(sealed)
    _cancel(cancel)
    return sealed

def prepare_surface_engineering(evaluation, outlets, *, conductance_m2_s, local_q_m3_s, tailwater_m, dt_s, max_depth_m, resources=EngineeringResources(), mosaic_resources=None, forest_resources=ForestResources(), variable_forcing=None, cancel=None):
    """Build the complete mosaic, one real coast attachment per domain, and global forest."""
    if not isinstance(resources, EngineeringResources) or (cancel is not None and (not callable(cancel))):
        raise ValueError('invalid engineering resources or cancel')
    _cancel(cancel)
    ids = _ids(evaluation, full_validation=True)
    if not isinstance(outlets, dict) or len(outlets) != len(ids) or any((type(domain_id) is not int for domain_id in outlets)) or (set(outlets) != set(ids)):
        raise ValueError('exactly one explicit outlet per declared domain required')
    if not isinstance(forest_resources, ForestResources) or any((not isinstance(outlets[domain_id], dict) or set(outlets[domain_id]) != {'attachment', 'corridor', 'sea', 'stations_z_m', 'budget'} or (not isinstance(outlets[domain_id]['attachment'], RiverAttachment)) or (outlets[domain_id]['attachment'].domain_id != domain_id) or (outlets[domain_id]['attachment'].prepared['identity_sha256'] != evaluation['identity_sha256']) for domain_id in ids)):
        raise ValueError('explicit same-source outlets and resources required')
    if variable_forcing is not None and (not isinstance(variable_forcing, dict) or not {'conductance_m2_s', 'local_q_m3_s', 'tailwater_m', 'dt_s', 'max_depth_m'} <= set(variable_forcing) or set(variable_forcing) - {'conductance_m2_s', 'local_q_m3_s', 'tailwater_m', 'dt_s', 'max_depth_m', 'resources'}):
        raise ValueError('explicit variable forcing required')
    input_size = _size({'evaluation': evaluation, 'outlets': [{'attachment': outlets[domain_id]['attachment'].prepared, 'corridor': _source_record(outlets[domain_id]['corridor']), 'sea': _source_record(outlets[domain_id]['sea']), 'stations': _i104_np.asarray(outlets[domain_id]['stations_z_m'])} for domain_id in ids], 'conductance': _i104_np.asarray(conductance_m2_s), 'local': _i104_np.asarray(local_q_m3_s), 'tailwater': _i104_np.asarray(tailwater_m)})
    if input_size > resources.max_retained_bytes or input_size * 2 > resources.max_working_bytes:
        raise ValueError('engineering working preflight')
    retained, working = _planned_bytes(evaluation, outlets, local_q_m3_s, variable_forcing)
    if retained > resources.max_retained_bytes or working + input_size > resources.max_working_bytes:
        raise ValueError('engineering generated retained/working preflight')
    _cancel(cancel)
    options = {'cancel': cancel}
    if mosaic_resources is not None:
        options['resources'] = mosaic_resources
    domain_mosaic = prepare_domain_mosaic(evaluation, **options)
    drops = []
    for domain_id in ids:
        _cancel(cancel)
        supplied = outlets[domain_id]
        if set(supplied) != {'attachment', 'corridor', 'sea', 'stations_z_m', 'budget'}:
            raise ValueError('explicit outlet attachment/sources/stations/budget required')
        if supplied['attachment'].domain_id != domain_id:
            raise ValueError('outlet domain mismatch')
        drops.append(prepare_coast_drop(**supplied))
    _cancel(cancel)
    dynamic_forest = prepare_surface_multidomain_dynamic(evaluation, conductance_m2_s=conductance_m2_s, local_q_m3_s=local_q_m3_s, tailwater_m=tailwater_m, dt_s=dt_s, max_depth_m=max_depth_m, resources=forest_resources, cancel=cancel)
    variable_storage = None
    if variable_forcing is not None:
        import terrain_pipeline.surface_domain as variable
        variable_storage = variable.prepare_surface_variable_storage(dynamic_forest, **variable_forcing, cancel=cancel)
    return compose_surface_engineering(evaluation, domain_mosaic, drops, dynamic_forest, variable_storage=variable_storage, resources=resources, cancel=cancel)

def validate_surface_engineering(result):
    """Check nested static proofs and cross-product source, outlet and ledger binding."""
    required = {'algorithm_version', 'status', 'evaluation', 'domain_mosaic', 'drops', 'variable_storage', 'dynamic_forest', 'domain_ids', 'resources', 'declared_node_envelope_complete', 'physical_footprint_complete', 'natural_outlets_certified', 'full_dynamic_wave_prepared', 'ready_for_3d', 'identity_sha256'}
    if set(result) != required or result['algorithm_version'] != SURFACE_ENGINEERING_PREPARE_VERSION or result['status'] != 'prepared' or (result['identity_sha256'] != fingerprint({key: value for key, value in result.items() if key != 'identity_sha256'})):
        raise ValueError('engineering schema/identity mismatch')
    resources = EngineeringResources(**result['resources'])
    if _size(result) > resources.max_retained_bytes or _size(result) * 2 > resources.max_working_bytes:
        raise ValueError('engineering resource exceeded')
    if result['declared_node_envelope_complete'] is not True or any((result[name] is not False for name in ('physical_footprint_complete', 'natural_outlets_certified', 'full_dynamic_wave_prepared', 'ready_for_3d'))):
        raise ValueError('engineering scope mismatch')
    evaluation = result['evaluation']
    saved_support = {}
    for mesh in result['domain_mosaic']['domain_meshes']:
        for identity, support in mesh['proof_h0_support'].items():
            if identity in saved_support:
                raise ValueError('duplicate engineering recovery support')
            saved_support[identity] = support
    ids = _ids(evaluation, saved_support=saved_support)
    if any((type(value) is not int for value in result['domain_ids'])) or list(result['domain_ids']) != ids or len(result['drops']) != len(ids):
        raise ValueError('omitted or duplicate domain')
    validate_domain_mosaic(result['domain_mosaic'])
    validate_surface_multidomain_dynamic(result['dynamic_forest'])
    identity = evaluation['identity_sha256']
    domain_mosaic = result['domain_mosaic']
    dynamic_forest = result['dynamic_forest']
    if domain_mosaic['declared_node_envelope_complete'] is not True or domain_mosaic['physical_footprint_complete'] is not False or domain_mosaic['natural_outlets_certified'] is not False or (dynamic_forest['natural_outlets_certified'] is not False) or (dynamic_forest['full_dynamic_wave_prepared'] is not False):
        raise ValueError('nested engineering scope mismatch')
    if domain_mosaic['evaluation']['identity_sha256'] != identity or dynamic_forest['evaluation']['identity_sha256'] != identity or domain_mosaic['candidate_identity_sha256'] != evaluation['candidate']['identity_sha256'] or (list(dynamic_forest['domain_ids']) != ids):
        raise ValueError('mixed evaluation/candidate source')
    datum = evaluation['candidate']['inputs']['vertical_datum']
    sea_level = evaluation['candidate']['inputs']['sea_level_elevation_m']
    for domain_id, drop, entry in zip(ids, result['drops'], evaluation['domains']):
        validate_coast_drop(drop)
        attachment = drop['inputs']['attachment']
        terminal = drop['attachment']
        if type(attachment['domain_id']) is not int or type(attachment['center_index']) is not int or type(terminal['terminal_node']) is not int or any((type(value) is not int for value in drop['usage'].values())):
            raise ValueError('strict outlet integer identity required')
        if attachment['domain_id'] != domain_id or attachment['datum'] != datum or attachment['prepared']['identity_sha256'] != identity or (terminal['recovery_sha256'] != entry['recovery']['identity_sha256']) or (drop['inputs']['sea']['sea_level_m'] != sea_level) or (drop['inputs']['corridor']['sea_level_m'] != sea_level) or (not _i104_np.allclose(terminal['sea_water_xyz_m'][:, 1], sea_level, atol=1e-09, rtol=0)):
            raise ValueError('mixed domain/proof/datum/sea outlet')
        binding = dynamic_forest['bindings'][ids.index(domain_id)]
        boundary = _i104_np.flatnonzero(binding['boundary_mask'])
        center = attachment['center_index']
        river = terminal['river_water_xyz_m'][center]
        if binding['source_proof_sha256'] != terminal['recovery_sha256'] or len(boundary) != 1 or (not _i104_np.allclose(binding['coords_xz_m'][boundary[0]], river[[0, 2]], atol=1e-09, rtol=0)) or (not _i104_np.isclose(binding['initial_stage_m'][boundary[0]], river[1], atol=1e-09, rtol=0)):
            raise ValueError('forest/drop terminal geometry or stage mismatch')
    if result['variable_storage'] is not None:
        import terrain_pipeline.surface_domain as variable
        variable.validate_surface_variable_storage(result['variable_storage'])
        if result['variable_storage']['source']['identity_sha256'] != dynamic_forest['identity_sha256']:
            raise ValueError('variable storage source differs from forest')
    return True

def query_surface_engineering(result, *, state_index=None, variable_state_index=None):
    validate_surface_engineering(result)
    dynamic = query_surface_multidomain_dynamic(result['dynamic_forest'], state_index=state_index)
    variable_result = None
    if result['variable_storage'] is not None:
        import terrain_pipeline.surface_domain as variable
        variable_result = variable.query_surface_variable_storage(result['variable_storage'], state_index=variable_state_index)
    elif variable_state_index is not None:
        raise ValueError('variable state requested without saved variable storage')
    domain_mosaic = result['domain_mosaic']
    return _freeze({'domain_ids': result['domain_ids'], 'mosaic_summary': domain_mosaic['summary'], 'surface_geometry': {'nodes': domain_mosaic['nodes'], 'cells': domain_mosaic['cells'], 'triangles': domain_mosaic['triangles'], 'wet_cells': domain_mosaic['wet_cells'], 'hydrologic_domain_owner': domain_mosaic['hydrologic_domain_owner']}, 'outlet_geometry': [drop['arrays'] for drop in result['drops']], 'outlets': [drop['attachment'] for drop in result['drops']], 'drop_ledgers': [drop['ledger'] for drop in result['drops']], 'dynamic': dynamic, 'domain_ledger_m3': result['dynamic_forest']['domain_ledger_m3'], 'constant_signed_edge_q_m3_s': result['dynamic_forest']['dynamic']['qedges_m3_s'], 'variable_signed_edge_q_m3_s': None if result['variable_storage'] is None else result['variable_storage']['qedges_m3_s'], 'variable_domain_ledger_m3': None if result['variable_storage'] is None else result['variable_storage']['domain_ledger_m3'], 'node_graph': {'node_keys': result['dynamic_forest']['node_keys'], 'edges': result['dynamic_forest']['edges'], 'coords_xz_m': result['dynamic_forest']['dynamic']['inputs']['coords_m']}, 'variable_storage': variable_result})

def save_surface_engineering(result, path):
    validate_surface_engineering(result)
    destination = _i104_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = _tree(result, arrays)
    metadata = _json({'format': SURFACE_ENGINEERING_PREPARE_VERSION + '-npy-v1', 'tree': tree}).encode('ascii')
    if len(arrays) + 1 > result['resources']['max_archive_members'] or len(metadata) > 8 * 1024 * 1024 or _size(result) > result['resources']['max_retained_bytes'] or (_size(result) * 2 > result['resources']['max_working_bytes']):
        raise ValueError('engineering archive metadata/member cap')
    descriptor, temporary = _i104_tempfile.mkstemp(prefix='.engineering-', dir=destination.parent)
    try:
        with _i104_os.fdopen(descriptor, 'w+b') as stream:
            with _i104_zipfile.ZipFile(stream, 'w', compression=_i104_zipfile.ZIP_STORED) as archive:
                archive.writestr('metadata.json', metadata)
                for name, array in arrays.items():
                    with archive.open(name, 'w') as member:
                        _i104_np.lib.format.write_array(member, array, version=(1, 0), allow_pickle=False)
            if stream.tell() > SURFACE_FINE_MOSAIC_MAX_BYTES:
                raise ValueError('engineering file cap')
            stream.flush()
            _i104_os.fsync(stream.fileno())
        _i104_os.link(temporary, destination)
    finally:
        _i104_Path(temporary).unlink(missing_ok=True)
    return destination

def load_surface_engineering(path):
    """Preflight every ZIP/NPY header before allocating nested array payloads."""
    with _i104_Path(path).open('rb') as retained, _i104_zipfile.ZipFile(retained) as archive:
        if _i104_os.fstat(retained.fileno()).st_size > SURFACE_FINE_MOSAIC_MAX_BYTES:
            raise ValueError('engineering file cap')
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) > 2048 or len(names) != len(set(names)) or any((info.compress_type != _i104_zipfile.ZIP_STORED or info.flag_bits & 1 for info in infos)) or (sum((info.file_size for info in infos)) > SURFACE_FINE_MOSAIC_MAX_BYTES) or ('metadata.json' not in names) or (archive.getinfo('metadata.json').file_size > 8 * 1024 * 1024):
            raise ValueError('engineering ZIP preflight')
        metadata = _i104_json.loads(archive.read('metadata.json'), object_pairs_hook=_pairs, parse_constant=_constant)
        if set(metadata) != {'format', 'tree'} or metadata['format'] != SURFACE_ENGINEERING_PREPARE_VERSION + '-npy-v1':
            raise ValueError('engineering metadata mismatch')
        references = {}

        def inspect(value, depth=0):
            if depth > 80:
                raise ValueError('engineering nesting cap')
            if isinstance(value, dict) and '$array' in value:
                name = value['$array']
                shape = value['shape']
                if set(value) != {'$array', 'shape', 'dtype', 'sha256'} or not isinstance(name, str) or name in references or (not name.startswith('array_')) or (not name.endswith('.npy')) or ('/' in name) or ('\\' in name) or (not isinstance(shape, list)) or (len(shape) > 4) or any((type(size) is not int or size < 0 or size > 1000000 for size in shape)) or (_i104_math.prod(shape) > 1000000):
                    raise ValueError('engineering array reference cap')
                if not isinstance(value['dtype'], str) or not isinstance(value['sha256'], str) or len(value['sha256']) != 64 or any((character not in '0123456789abcdef' for character in value['sha256'])):
                    raise ValueError('engineering dtype/hash metadata mismatch')
                dtype = _i104_np.dtype(value['dtype'])
                if dtype.kind not in 'bifu' or dtype.itemsize > 8:
                    raise ValueError('pickle/object or unsupported dtype')
                references[name] = value
            elif isinstance(value, dict):
                for child in value.values():
                    inspect(child, depth + 1)
            elif isinstance(value, list):
                for child in value:
                    inspect(child, depth + 1)
        inspect(metadata['tree'])
        if set(names) != {'metadata.json'} | set(references):
            raise ValueError('engineering archive members mismatch')
        resources = EngineeringResources(**metadata['tree']['resources'])
        if len(names) > resources.max_archive_members or sum((info.file_size for info in infos)) > resources.max_retained_bytes or sum((info.file_size for info in infos)) * 2 > resources.max_working_bytes:
            raise ValueError('engineering saved resource preflight')
        for name, reference in references.items():
            with archive.open(name) as member:
                if _i104_np.lib.format.read_magic(member) != (1, 0):
                    raise ValueError('NPY v1 required')
                length = member.read(2)
                if len(length) != 2 or int.from_bytes(length, 'little') > 2038:
                    raise ValueError('NPY header cap')
                header = member.read(int.from_bytes(length, 'little'))
                if len(header) != int.from_bytes(length, 'little'):
                    raise ValueError('truncated NPY header')
                shape, fortran, dtype = _strict_header(header)
                if list(shape) != reference['shape'] or dtype.str != reference['dtype'] or dtype.kind not in 'bifu' or fortran or (member.tell() + _i104_math.prod(shape) * dtype.itemsize != archive.getinfo(name).file_size):
                    raise ValueError('NPY header/payload mismatch')
        arrays = {}
        for name, reference in references.items():
            with archive.open(name) as member:
                array = _i104_np.load(member, allow_pickle=False)
            if _array_hash(array) != reference['sha256']:
                raise ValueError('engineering array hash mismatch')
            arrays[name] = array

    def decode(value):
        if isinstance(value, dict) and '$array' in value:
            return arrays[value['$array']]
        if isinstance(value, dict):
            return {key: decode(child) for key, child in value.items()}
        if isinstance(value, list):
            return [decode(child) for child in value]
        return value
    result = _freeze(decode(metadata['tree']))
    validate_surface_engineering(result)
    return result
SURFACE_LAND_COVERAGE_VERSION = 'surface-land-coverage-v1'
INTERPRETATION = 'clamped_engineering_interpretation'
SOURCE_ID = '381e60743e03cee6859c5cce46cb6337c8ea601ed5eb4cc1258e18cf51092860'

@_i106_dataclass(frozen=True)
class CoverageResources:
    max_retained_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES
    max_working_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES
    max_archive_members: int = 2048

    def __post_init__(self):
        for name, ceiling in (('max_retained_bytes', SURFACE_FINE_MOSAIC_MAX_BYTES), ('max_working_bytes', SURFACE_FINE_MOSAIC_MAX_BYTES), ('max_archive_members', 2048)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError('invalid coverage resource: ' + name)

def _surface_land_coverage_cancel(cancel):
    if cancel is not None and cancel():
        raise InterruptedError('land coverage cancelled')

def _surface_land_coverage_preflight(source, resources):
    if not isinstance(resources, CoverageResources):
        raise ValueError('CoverageResources required')
    retained = _retained(source) + 10011 * 600 + 19600 * 64 + 2 * 64 * 256
    if retained > resources.max_retained_bytes or retained * 3 > resources.max_working_bytes:
        raise ValueError('coverage generated retained/working preflight')
    return retained

def _source_gate(source):
    validate_surface_engineering(source)
    if source['identity_sha256'] != SOURCE_ID:
        raise ValueError('fixed frozen engineering bundle required')
    inputs = source['evaluation']['candidate']['inputs']
    if list(source['domain_ids']) != [1, 2] or inputs['height_m'].shape != (9, 16) or tuple(source['domain_mosaic']['grid']['bbox_xz_m']) != (10.0, 140.0, 10.0, 70.0) or (inputs['origin_x_m'] != 0.0) or (inputs['origin_z_m'] != 0.0) or (inputs['spacing_x_m'] != 10.0) or (inputs['spacing_z_m'] != 10.0):
        raise ValueError('unsupported fixed land source geometry')

def _topology():
    rows, columns = _i106_np.indices((70, 140))
    first = (rows * 141 + columns).ravel()
    cells = _i106_np.column_stack((first, first + 1, first + 142, first + 141)).astype(_i106_np.int64)
    triangles = _i106_np.empty((19600, 3), _i106_np.int64)
    triangles[0::2] = cells[:, [0, 1, 2]]
    triangles[1::2] = cells[:, [0, 2, 3]]
    return (cells, triangles)

def _algebra(source):
    inputs = source['evaluation']['candidate']['inputs']
    mesh = source['domain_mosaic']
    xz = _i106_np.column_stack((_i106_np.tile(_i106_np.arange(5.0, 146.0), 71), _i106_np.repeat(_i106_np.arange(5.0, 76.0), 141)))
    clamped = _i106_np.column_stack((_i106_np.clip(xz[:, 0], 10.0, 140.0), _i106_np.clip(xz[:, 1], 10.0, 70.0)))
    coordinates = clamped / 10.0
    left = _i106_np.floor(coordinates[:, 0]).astype(_i106_np.int64)
    top = _i106_np.floor(coordinates[:, 1]).astype(_i106_np.int64)
    fraction_x = coordinates[:, 0] - left
    fraction_z = coordinates[:, 1] - top
    indices = _i106_np.column_stack((top * 16 + left, top * 16 + left + 1, (top + 1) * 16 + left, (top + 1) * 16 + left + 1))
    weights = _i106_np.column_stack(((1 - fraction_x) * (1 - fraction_z), fraction_x * (1 - fraction_z), (1 - fraction_x) * fraction_z, fraction_x * fraction_z))
    positive = weights > 0
    valid_land = inputs['valid_mask'].ravel()[indices] & inputs['land_mask'].ravel()[indices]
    protected_support = inputs['protected_mask'].ravel()[indices]
    if _i106_np.any(positive & ~valid_land):
        raise ValueError('positive interpolation support is not valid land')
    h0 = (inputs['height_m'].ravel()[indices] * weights).sum(axis=1)
    protected = _i106_np.any(positive & protected_support, axis=1)
    h2 = h0.copy()
    water = _i106_np.zeros(10011)
    wet = _i106_np.zeros(10011, bool)
    old_ids = (_i106_np.arange(5, 66)[:, None] * 141 + _i106_np.arange(5, 136)[None, :]).ravel()
    if not _i106_np.allclose(h0[old_ids], mesh['nodes']['h0_m'], atol=1e-12, rtol=0):
        raise ValueError('original candidate H0 differs from interior source')
    for target, name in ((h0, 'h0_m'), (h2, 'h2_m'), (water, 'water_surface_m'), (wet, 'wet_mask'), (protected, 'protected_mask')):
        target[old_ids] = mesh['nodes'][name]
    strip_domain = _i106_np.zeros(10011, _i106_np.int64)
    bank = _i106_np.zeros(10011, bool)
    for domain_id, drop in zip((1, 2), source['drops']):
        bed = drop['arrays']['bed_xyz_m'].reshape(21, 4, 3)
        drop_water = drop['arrays']['water_xyz_m'].reshape(21, 4, 3)
        left_x = 38 if domain_id == 1 else 108
        if not _i106_np.array_equal(bed[:, :, 0], _i106_np.tile(_i106_np.arange(left_x, left_x + 4), (21, 1))):
            raise ValueError('actual outlet strip mismatch')
        for station in range(6):
            node_ids = (65 + station) * 141 + _i106_np.arange(left_x - 5, left_x - 1)
            if station == 0:
                if not _i106_np.array_equal(h2[node_ids], bed[0, :, 1]) or not _i106_np.array_equal(water[node_ids], drop_water[0, :, 1]) or (not _i106_np.all(wet[node_ids])):
                    raise ValueError('original row70 does not match actual full-width drop')
            else:
                h2[node_ids] = bed[station, :, 1]
                water[node_ids] = drop_water[station, :, 1]
                wet[node_ids] = True
            strip_domain[node_ids] = domain_id
        bank_x = _i106_np.array([35, 36, 37, 42, 43]) + (domain_id - 1) * 70
        original_bank_ids = 65 * 141 + bank_x - 5
        delta = h0[original_bank_ids] - h2[original_bank_ids]
        for station in range(1, 6):
            node_ids = (65 + station) * 141 + bank_x - 5
            h2[node_ids] = h0[node_ids] - delta * (1 - station / 5.0)
            bank[node_ids] = True
    cells, triangles = _topology()
    interior = _i106_np.zeros((70, 140), bool)
    interior[5:65, 5:135] = True
    interior = interior.ravel()
    owners = _i106_np.tile(_i106_np.where(_i106_np.arange(140) < 70, 1, 2), 70).astype(_i106_np.int64)
    if not _i106_np.array_equal(owners[interior], mesh['hydrologic_domain_owner'].ravel()):
        raise ValueError('interior domain ownership changed')
    old_to_land = old_ids[mesh['triangles']]
    if not _i106_np.array_equal(triangles[_i106_np.repeat(interior, 2)], old_to_land):
        raise ValueError('interior triangle topology changed')
    nodes = {'xz_m': xz, 'h0_m': h0, 'h2_m': h2, 'water_surface_m': water, 'wet_mask': wet, 'protected_mask': protected}
    audit = {'clamped_xz_m': clamped, 'indices': indices, 'weights': weights, 'positive_mask': positive, 'valid_land_support': valid_land, 'protected_support': protected_support, 'interior_node_ids': old_ids, 'interior_cell_mask': interior, 'engineering_strip_domain': strip_domain, 'dry_cut_bank_mask': bank}
    outside = []
    for domain_id, drop in zip((1, 2), source['drops']):
        left_x = 38 if domain_id == 1 else 108
        bed = drop['arrays']['bed_xyz_m'][20:]
        drop_water = drop['arrays']['water_xyz_m'][20:]
        source_triangles = drop['arrays']['triangles'][30:]
        boundary_ids = 70 * 141 + _i106_np.arange(left_x - 5, left_x - 1)
        outside.append({'domain_id': domain_id, 'source_drop_sha256': drop['identity_sha256'], 'source_node_ids': _i106_np.arange(20, 84, dtype=_i106_np.int64), 'source_triangle_ids': _i106_np.arange(30, 120, dtype=_i106_np.int64), 'bed_xyz_m': bed, 'water_xyz_m': drop_water, 'triangles': source_triangles - 20, 'shared_land_node_ids': boundary_ids.astype(_i106_np.int64), 'terminal_q_m3_s': drop['attachment']['terminal_q_m3_s']})
    return (nodes, cells, triangles, owners, audit, outside)

def _ledger(nodes, cells, triangles, audit, outside):
    cut = nodes['h0_m'] - nodes['h2_m']
    if _i106_np.any(~_i106_np.isfinite(cut)) or _i106_np.min(cut) < -1e-10 or _i106_np.max(cut) > 4.0 + 1e-10 or _i106_np.any(nodes['protected_mask'] & (cut > 1e-10)) or _i106_np.any(nodes['wet_mask'] & (nodes['water_surface_m'] < nodes['h2_m'] - 1e-10)) or _i106_np.any(nodes['water_surface_m'][~nodes['wet_mask']] != 0):
        raise ValueError('land cut/depth/protection/water violation')
    volumes = (cut[triangles].mean(axis=1) * 0.5).reshape(-1, 2).sum(axis=1)
    inner = float(volumes[audit['interior_cell_mask']].sum())
    outer = float(volumes[~audit['interior_cell_mask']].sum())
    if outer > 100.0 + 1e-09:
        raise ValueError('outer land cut budget exceeded: ' + str(outer))
    wet_cells = _i106_np.all(nodes['wet_mask'][cells], axis=1)
    wet_triangles = triangles[_i106_np.repeat(wet_cells, 2)]
    water_volume = float(((nodes['water_surface_m'] - nodes['h2_m'])[wet_triangles].mean(axis=1) * 0.5).sum())
    outside_water = 0.0
    for outlet in outside:
        outside_water += float(((outlet['water_xyz_m'][:, 1] - outlet['bed_xyz_m'][:, 1])[outlet['triangles']].mean(axis=1) * 0.5).sum())
    return {'land_area_m2': 9800.0, 'interior_area_m2': 7800.0, 'outer_land_area_m2': 2000.0, 'outside_attachment_area_m2': 90.0, 'interior_cut_volume_m3': inner, 'outer_cut_volume_m3': outer, 'land_cut_volume_m3': inner + outer, 'land_static_water_volume_m3': water_volume, 'outside_static_water_volume_m3': outside_water, 'max_cut_depth_m': float(cut.max()), 'outer_cut_budget_m3': 100.0, 'land_static_wet_cells': int(wet_cells.sum()), 'source_dynamic_wet_cells': 676, 'cut_depth_limit_m': 4.0, 'static_terminal_q_sum_m3_s': sum((item['terminal_q_m3_s'] for item in outside))}

def prepare_surface_land_coverage(source, *, resources=CoverageResources(), cancel=None):
    """Generate only the fixed clamped engineering footprint; no natural certification."""
    if cancel is not None and (not callable(cancel)):
        raise ValueError('callable cancel required')
    _surface_land_coverage_cancel(cancel)
    _surface_land_coverage_preflight(source, resources)
    _source_gate(source)
    _surface_land_coverage_cancel(cancel)
    nodes, cells, triangles, owners, audit, outside = _algebra(source)
    ledger = _ledger(nodes, cells, triangles, audit, outside)
    result = {'algorithm_version': SURFACE_LAND_COVERAGE_VERSION, 'status': 'prepared', 'interpretation': INTERPRETATION, 'source': source, 'source_identity_sha256': source['identity_sha256'], 'resources': _i106_asdict(resources), 'grid': {'bbox_xz_m': [5.0, 145.0, 5.0, 75.0], 'shape_nodes_zx': [71, 141], 'spacing_m': 1.0}, 'nodes': nodes, 'cells': cells, 'triangles': triangles, 'domain_owner': owners, 'audit': audit, 'outside_outlets': outside, 'ledger': ledger, 'land_pixel_footprint_represented': True, 'natural_outlets_certified': False, 'general_cross_precision': False, 'dynamic_fine': False, 'ready_for_3d': False, 'full_dynamic_wave_prepared': False, 'phase': 'original_land_clamped_h0_with_engineering_bed_water', 'dynamic_boundary_z_m': 70.0, 'static_geometry_coast_z_m': 75.0, 'outlet_dynamic_storage_included': False}
    result['identity_sha256'] = fingerprint(result)
    sealed = _freeze(result)
    validate_surface_land_coverage(sealed)
    _surface_land_coverage_cancel(cancel)
    return sealed

def _equal(actual, expected):
    if isinstance(expected, _i106_np.ndarray):
        if not isinstance(actual, _i106_np.ndarray) or actual.dtype != expected.dtype or actual.shape != expected.shape or (not _i106_np.array_equal(actual, expected)):
            raise ValueError('saved coverage array differs from source algebra')
    elif hasattr(expected, 'items'):
        if not hasattr(actual, 'items') or set(actual) != set(expected):
            raise ValueError('saved coverage schema differs')
        for key, value in expected.items():
            _equal(actual[key], value)
    elif isinstance(expected, (tuple, list)):
        if not isinstance(actual, (tuple, list)) or len(actual) != len(expected):
            raise ValueError('saved coverage sequence differs')
        for item, value in zip(actual, expected):
            _equal(item, value)
    elif type(expected) in (bool, int):
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError('strict saved bool/integer mismatch')
    elif type(expected) is float and type(actual) is not float:
        raise ValueError('strict saved float mismatch')
    elif actual != expected:
        raise ValueError('saved coverage scalar differs')

def _surface_land_coverage_static_geometry(record):
    nodes, cells, triangles, audit = (record['nodes'], record['cells'], record['triangles'], record['audit'])
    source = record['source']
    inputs = source['evaluation']['candidate']['inputs']
    mesh = source['domain_mosaic']
    if set(nodes) != {'xz_m', 'h0_m', 'h2_m', 'water_surface_m', 'wet_mask', 'protected_mask'} or set(audit) != {'clamped_xz_m', 'indices', 'weights', 'positive_mask', 'valid_land_support', 'protected_support', 'interior_node_ids', 'interior_cell_mask', 'engineering_strip_domain', 'dry_cut_bank_mask'}:
        raise ValueError('land node/audit schema')
    specs = [(nodes['xz_m'], (10011, 2), 'float64'), (cells, (9800, 4), 'int64'), (triangles, (19600, 3), 'int64'), (record['domain_owner'], (9800,), 'int64'), (audit['clamped_xz_m'], (10011, 2), 'float64'), (audit['indices'], (10011, 4), 'int64'), (audit['weights'], (10011, 4), 'float64'), (audit['interior_node_ids'], (7991,), 'int64'), (audit['interior_cell_mask'], (9800,), 'bool'), (audit['engineering_strip_domain'], (10011,), 'int64'), (audit['dry_cut_bank_mask'], (10011,), 'bool')]
    for name in ('h0_m', 'h2_m', 'water_surface_m', 'wet_mask', 'protected_mask'):
        specs.append((nodes[name], (10011,), 'bool' if name.endswith('mask') else 'float64'))
    for name in ('positive_mask', 'valid_land_support', 'protected_support'):
        specs.append((audit[name], (10011, 4), 'bool'))
    for array, shape, dtype in specs:
        if not isinstance(array, _i106_np.ndarray) or array.shape != shape or array.dtype != _i106_np.dtype(dtype) or (not _i106_np.all(_i106_np.isfinite(array))):
            raise ValueError('strict coverage shape/dtype/finite check')
    xz = nodes['xz_m']
    node_number = _i106_np.arange(10011)
    if not _i106_np.array_equal(xz[:, 0], node_number % 141 + 5.0) or not _i106_np.array_equal(xz[:, 1], node_number // 141 + 5.0):
        raise ValueError('saved node coordinates/order')
    cell_number = _i106_np.arange(9800)
    start = cell_number // 140 * 141 + cell_number % 140
    if not _i106_np.array_equal(cells[:, 0], start) or not _i106_np.array_equal(cells[:, 1], start + 1) or (not _i106_np.array_equal(cells[:, 2], start + 142)) or (not _i106_np.array_equal(cells[:, 3], start + 141)) or (not _i106_np.array_equal(triangles[0::2], cells[:, [0, 1, 2]])) or (not _i106_np.array_equal(triangles[1::2], cells[:, [0, 2, 3]])):
        raise ValueError('saved unique land topology')
    if not _i106_np.array_equal(record['domain_owner'], _i106_np.where(cell_number % 140 < 70, 1, 2)):
        raise ValueError('saved unique domain owner')
    clamped = audit['clamped_xz_m']
    if not _i106_np.array_equal(clamped[:, 0], _i106_np.clip(xz[:, 0], 10.0, 140.0)) or not _i106_np.array_equal(clamped[:, 1], _i106_np.clip(xz[:, 1], 10.0, 70.0)):
        raise ValueError('saved clamp algebra')
    indices, weights = (audit['indices'], audit['weights'])
    left = _i106_np.floor(clamped[:, 0] / 10).astype(_i106_np.int64)
    top = _i106_np.floor(clamped[:, 1] / 10).astype(_i106_np.int64)
    fraction_x = clamped[:, 0] / 10 - left
    fraction_z = clamped[:, 1] / 10 - top
    expected_indices = (top * 16 + left, top * 16 + left + 1, (top + 1) * 16 + left, (top + 1) * 16 + left + 1)
    expected_weights = ((1 - fraction_x) * (1 - fraction_z), fraction_x * (1 - fraction_z), (1 - fraction_x) * fraction_z, fraction_x * fraction_z)
    for corner in range(4):
        if not _i106_np.array_equal(indices[:, corner], expected_indices[corner]) or not _i106_np.array_equal(weights[:, corner], expected_weights[corner]):
            raise ValueError('saved stencil algebra')
    positive = weights > 0
    valid = inputs['valid_mask'].ravel()[indices] & inputs['land_mask'].ravel()[indices]
    protected_support = inputs['protected_mask'].ravel()[indices]
    if not _i106_np.array_equal(audit['positive_mask'], positive) or not _i106_np.array_equal(audit['valid_land_support'], valid) or _i106_np.any(positive & ~valid) or (not _i106_np.array_equal(audit['protected_support'], protected_support)):
        raise ValueError('saved positive land/protection support')
    interior_nodes = (xz[:, 0] >= 10) & (xz[:, 0] <= 140) & (xz[:, 1] >= 10) & (xz[:, 1] <= 70)
    old_ids = audit['interior_node_ids']
    if not _i106_np.array_equal(old_ids, _i106_np.flatnonzero(interior_nodes)):
        raise ValueError('saved interior node mapping')
    corner_xz = xz[cells[:, 0]]
    interior_cells = (corner_xz[:, 0] >= 10) & (corner_xz[:, 0] < 140) & (corner_xz[:, 1] >= 10) & (corner_xz[:, 1] < 70)
    if not _i106_np.array_equal(audit['interior_cell_mask'], interior_cells) or not _i106_np.array_equal(triangles[_i106_np.repeat(interior_cells, 2)], old_ids[mesh['triangles']]) or (not _i106_np.array_equal(record['domain_owner'][interior_cells], mesh['hydrologic_domain_owner'].ravel())):
        raise ValueError('saved interior cells/triangles changed')
    original_h0 = (inputs['height_m'].ravel()[indices] * weights).sum(axis=1)
    if not _i106_np.allclose(nodes['h0_m'], original_h0, atol=1e-12, rtol=0):
        raise ValueError('original land H0 algebra')
    for name in ('h0_m', 'h2_m', 'water_surface_m', 'wet_mask', 'protected_mask'):
        if not _i106_np.array_equal(nodes[name][old_ids], mesh['nodes'][name]):
            raise ValueError('saved interior array changed')
    if not _i106_np.array_equal(nodes['protected_mask'], _i106_np.any(positive & protected_support, axis=1)):
        raise ValueError('saved protected nodal support')
    strips = audit['engineering_strip_domain']
    bank = audit['dry_cut_bank_mask']
    expected_strip = _i106_np.where((xz[:, 1] >= 70) & (xz[:, 0] >= 38) & (xz[:, 0] <= 41), 1, _i106_np.where((xz[:, 1] >= 70) & (xz[:, 0] >= 108) & (xz[:, 0] <= 111), 2, 0))
    bank_x = _i106_np.isin(xz[:, 0], [35, 36, 37, 42, 43, 105, 106, 107, 112, 113])
    if not _i106_np.array_equal(strips, expected_strip) or not _i106_np.array_equal(bank, bank_x & (xz[:, 1] > 70)):
        raise ValueError('saved engineered strip/bank audit')
    dry = ~interior_nodes & (strips == 0) & ~bank
    if not _i106_np.array_equal(nodes['h2_m'][dry], nodes['h0_m'][dry]) or _i106_np.any(nodes['wet_mask'][dry]) or _i106_np.any(nodes['water_surface_m'][dry] != 0):
        raise ValueError('dry outer rim algebra')
    for domain_id, drop, outlet in zip((1, 2), source['drops'], record['outside_outlets']):
        selected = _i106_np.flatnonzero(strips == domain_id)
        source_ids = (xz[selected, 1].astype(_i106_np.int64) - 70) * 4 + xz[selected, 0].astype(_i106_np.int64) - (38 if domain_id == 1 else 108)
        if not _i106_np.array_equal(nodes['h2_m'][selected], drop['arrays']['bed_xyz_m'][source_ids, 1]) or not _i106_np.array_equal(nodes['water_surface_m'][selected], drop['arrays']['water_xyz_m'][source_ids, 1]) or (not _i106_np.all(nodes['wet_mask'][selected])):
            raise ValueError('saved actual drop bed/water algebra')
        selected_bank = _i106_np.flatnonzero(bank & (xz[:, 0] < 75 if domain_id == 1 else xz[:, 0] > 75))
        original_ids = 65 * 141 + xz[selected_bank, 0].astype(_i106_np.int64) - 5
        delta = nodes['h0_m'][original_ids] - nodes['h2_m'][original_ids]
        expected_bed = nodes['h0_m'][selected_bank] - delta * (1 - (xz[selected_bank, 1] - 70) / 5.0)
        if not _i106_np.array_equal(nodes['h2_m'][selected_bank], expected_bed) or _i106_np.any(nodes['wet_mask'][selected_bank]) or _i106_np.any(nodes['water_surface_m'][selected_bank] != 0):
            raise ValueError('saved tapered bank algebra')
        expected_outlet = {'domain_id': domain_id, 'source_drop_sha256': drop['identity_sha256'], 'source_node_ids': _i106_np.arange(20, 84, dtype=_i106_np.int64), 'source_triangle_ids': _i106_np.arange(30, 120, dtype=_i106_np.int64), 'bed_xyz_m': drop['arrays']['bed_xyz_m'][20:], 'water_xyz_m': drop['arrays']['water_xyz_m'][20:], 'triangles': drop['arrays']['triangles'][30:] - 20, 'shared_land_node_ids': selected[-4:].astype(_i106_np.int64), 'terminal_q_m3_s': drop['attachment']['terminal_q_m3_s']}
        _equal(outlet, expected_outlet)

def validate_surface_land_coverage(record):
    """Recheck saved source algebra, geometry, audit and budgets without preparation."""
    try:
        required = {'algorithm_version', 'status', 'interpretation', 'source', 'source_identity_sha256', 'resources', 'grid', 'nodes', 'cells', 'triangles', 'domain_owner', 'audit', 'outside_outlets', 'ledger', 'land_pixel_footprint_represented', 'natural_outlets_certified', 'general_cross_precision', 'dynamic_fine', 'ready_for_3d', 'identity_sha256', 'full_dynamic_wave_prepared', 'phase', 'dynamic_boundary_z_m', 'static_geometry_coast_z_m', 'outlet_dynamic_storage_included'}
        if set(record) != required or record['algorithm_version'] != SURFACE_LAND_COVERAGE_VERSION or record['status'] != 'prepared' or (record['interpretation'] != INTERPRETATION) or (record['land_pixel_footprint_represented'] is not True) or any((record[name] is not False for name in ('natural_outlets_certified', 'general_cross_precision', 'dynamic_fine', 'ready_for_3d', 'full_dynamic_wave_prepared', 'outlet_dynamic_storage_included'))) or (record['phase'] != 'original_land_clamped_h0_with_engineering_bed_water') or (record['dynamic_boundary_z_m'] != 70.0) or (record['static_geometry_coast_z_m'] != 75.0) or (record['identity_sha256'] != fingerprint({key: value for key, value in record.items() if key != 'identity_sha256'})):
            raise ValueError('coverage schema/identity/scope mismatch')
        resources = CoverageResources(**record['resources'])
        _surface_land_coverage_preflight(record['source'], resources)
        size = _retained(record)
        if size > resources.max_retained_bytes or size * 3 > resources.max_working_bytes:
            raise ValueError('coverage retained/working cap')
        _source_gate(record['source'])
        if record['source_identity_sha256'] != record['source']['identity_sha256']:
            raise ValueError('coverage source chain mismatch')
        _equal(record['grid'], {'bbox_xz_m': [5.0, 145.0, 5.0, 75.0], 'shape_nodes_zx': [71, 141], 'spacing_m': 1.0})
        if len(record['outside_outlets']) != 2:
            raise ValueError('two outside outlets required')
        _surface_land_coverage_static_geometry(record)
        nodes, cells, triangles, audit, outside = (record[name] for name in ('nodes', 'cells', 'triangles', 'audit', 'outside_outlets'))
        _equal(record['ledger'], _ledger(nodes, cells, triangles, audit, outside))
        for outlet in record['outside_outlets']:
            ids = outlet['shared_land_node_ids']
            bed = _i106_np.column_stack((nodes['xz_m'][ids, 0], nodes['h2_m'][ids], nodes['xz_m'][ids, 1]))
            water = _i106_np.column_stack((nodes['xz_m'][ids, 0], nodes['water_surface_m'][ids], nodes['xz_m'][ids, 1]))
            if not _i106_np.array_equal(bed, outlet['bed_xyz_m'][:4]) or not _i106_np.array_equal(water, outlet['water_xyz_m'][:4]):
                raise ValueError('cropped drop shared boundary mismatch')
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError('invalid saved coverage') from error

def query_surface_land_coverage(record):
    validate_surface_land_coverage(record)
    return _freeze({'identity_sha256': record['identity_sha256'], 'interpretation': INTERPRETATION, 'grid': record['grid'], 'nodes': record['nodes'], 'cells': record['cells'], 'triangles': record['triangles'], 'domain_owner': record['domain_owner'], 'engineering_strip_domain': record['audit']['engineering_strip_domain'], 'outside_outlets': record['outside_outlets'], 'ledger': record['ledger'], 'land_pixel_footprint_represented': True, 'natural_outlets_certified': False, 'general_cross_precision': False, 'dynamic_fine': False, 'ready_for_3d': False, 'fixed_dynamic_wet_cells': 676, 'phase': record['phase'], 'dynamic_boundary_z_m': 70.0, 'static_geometry_coast_z_m': 75.0, 'outlet_dynamic_storage_included': False, 'full_dynamic_wave_prepared': False, 'source_identity_sha256': record['source_identity_sha256']})

def save_surface_land_coverage(record, path):
    validate_surface_land_coverage(record)
    destination = _i106_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    metadata = _json({'format': SURFACE_LAND_COVERAGE_VERSION + '-npy-v1', 'tree': _tree(record, arrays)}).encode('ascii')
    if len(metadata) > 8 * 1024 * 1024 or len(arrays) + 1 > record['resources']['max_archive_members']:
        raise ValueError('coverage archive metadata/member cap')
    archive_bound = len(metadata) + sum((array.nbytes + 2048 + 256 for array in arrays.values())) + 256
    if archive_bound > record['resources']['max_retained_bytes'] or archive_bound * 3 > record['resources']['max_working_bytes']:
        raise ValueError('coverage archive byte preflight')
    descriptor, temporary = _i106_tempfile.mkstemp(prefix='.land-coverage-', dir=destination.parent)
    try:
        with _i106_os.fdopen(descriptor, 'w+b') as stream:
            with _i106_zipfile.ZipFile(stream, 'w', compression=_i106_zipfile.ZIP_STORED) as archive:
                archive.writestr('metadata.json', metadata)
                for name, array in arrays.items():
                    with archive.open(name, 'w') as member:
                        _i106_np.lib.format.write_array(member, array, version=(1, 0), allow_pickle=False)
            stream.flush()
            _i106_os.fsync(stream.fileno())
        _i106_os.link(temporary, destination)
    finally:
        _i106_Path(temporary).unlink(missing_ok=True)
    return destination

def load_surface_land_coverage(path):
    """Bound every metadata and NPY header before loading any array payload."""
    with _i106_Path(path).open('rb') as stream:
        if _i106_os.fstat(stream.fileno()).st_size > SURFACE_FINE_MOSAIC_MAX_BYTES:
            raise ValueError('coverage file cap')
        with _i106_zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) > 2048 or len(names) != len(set(names)) or 'metadata.json' not in names or any((info.compress_type != _i106_zipfile.ZIP_STORED or info.flag_bits & 1 for info in infos)) or (sum((info.file_size for info in infos)) > SURFACE_FINE_MOSAIC_MAX_BYTES) or (archive.getinfo('metadata.json').file_size > 8 * 1024 * 1024):
                raise ValueError('coverage ZIP preflight')
            metadata = _i106_json.loads(archive.read('metadata.json'), object_pairs_hook=_pairs, parse_constant=_constant)
            if set(metadata) != {'format', 'tree'} or metadata['format'] != SURFACE_LAND_COVERAGE_VERSION + '-npy-v1':
                raise ValueError('coverage archive format')
            references = {}

            def inspect(value, depth=0):
                if depth > 80:
                    raise ValueError('coverage metadata nesting cap')
                if isinstance(value, dict) and '$array' in value:
                    if set(value) != {'$array', 'shape', 'dtype', 'sha256'}:
                        raise ValueError('coverage array reference schema')
                    name, shape = (value['$array'], value['shape'])
                    if not isinstance(name, str) or name in references or (not name.startswith('array_')) or (not name.endswith('.npy')) or ('/' in name) or ('\\' in name) or (not isinstance(shape, list)) or (len(shape) > 4) or any((type(size) is not int or not 0 <= size <= 1000000 for size in shape)) or (_i106_math.prod(shape) > 1000000) or (not isinstance(value['dtype'], str)) or (not isinstance(value['sha256'], str)) or (len(value['sha256']) != 64) or any((character not in '0123456789abcdef' for character in value['sha256'])):
                        raise ValueError('coverage array reference cap')
                    dtype = _i106_np.dtype(value['dtype'])
                    if dtype.kind not in 'bifu' or dtype.itemsize > 8:
                        raise ValueError('coverage unsupported/object dtype')
                    references[name] = value
                elif isinstance(value, dict):
                    for child in value.values():
                        inspect(child, depth + 1)
                elif isinstance(value, list):
                    for child in value:
                        inspect(child, depth + 1)
            inspect(metadata['tree'])
            resources = CoverageResources(**metadata['tree']['resources'])
            archive_size = sum((info.file_size for info in infos))
            if set(names) != {'metadata.json'} | set(references) or len(names) > resources.max_archive_members or archive_size > resources.max_retained_bytes or (archive_size * 3 > resources.max_working_bytes):
                raise ValueError('coverage saved resource preflight')
            for name, reference in references.items():
                with archive.open(name) as member:
                    if _i106_np.lib.format.read_magic(member) != (1, 0):
                        raise ValueError('coverage NPY v1 required')
                    length = member.read(2)
                    if len(length) != 2 or int.from_bytes(length, 'little') > 2038:
                        raise ValueError('coverage NPY header cap')
                    header = member.read(int.from_bytes(length, 'little'))
                    if len(header) != int.from_bytes(length, 'little'):
                        raise ValueError('coverage truncated header')
                    shape, fortran, dtype = _strict_header(header)
                    if list(shape) != reference['shape'] or dtype.str != reference['dtype'] or fortran or (member.tell() + _i106_math.prod(shape) * dtype.itemsize != archive.getinfo(name).file_size):
                        raise ValueError('coverage NPY payload/header mismatch')
            arrays = {}
            for name, reference in references.items():
                with archive.open(name) as member:
                    array = _i106_np.load(member, allow_pickle=False)
                if _array_hash(array) != reference['sha256']:
                    raise ValueError('coverage array hash mismatch')
                arrays[name] = array

    def decode(value):
        if isinstance(value, dict) and '$array' in value:
            return arrays[value['$array']]
        if isinstance(value, dict):
            return {key: decode(child) for key, child in value.items()}
        if isinstance(value, list):
            return [decode(child) for child in value]
        return value
    result = _freeze(decode(metadata['tree']))
    validate_surface_land_coverage(result)
    return result
SCHEMA = 'surface-network-large-benchmark-v1'
STATIC_SCHEMA = 'surface-network-large-static-D4-v1'
DYNAMIC_SCHEMA = 'surface-network-large-one-step-storage-v1'

@_i109_dataclass(frozen=True)
class LargeBenchmarkBudget:
    tile_cells: int = 256
    max_cells: int = 16777216
    max_resident_bytes: int = 256 * 1024 * 1024
    max_tiles: int = 256
    forcing_interval_s: float = 900.0

def _finite_positive(value, name):
    if type(value) not in (int, float) or not _i109_np.isfinite(value) or value <= 0:
        raise ValueError(name + ' must be finite and positive')

def validate_budget(budget):
    if not isinstance(budget, LargeBenchmarkBudget):
        raise ValueError('LargeBenchmarkBudget required')
    for name in ('tile_cells', 'max_cells', 'max_resident_bytes', 'max_tiles'):
        value = getattr(budget, name)
        if type(value) is not int or value <= 0:
            raise ValueError('positive integer budget: ' + name)
    _finite_positive(budget.forcing_interval_s, 'forcing_interval_s')
    if budget.tile_cells < 16 or budget.tile_cells > 1024:
        raise ValueError('tile span outside bounded range')

def _load_npz(path):
    with _i109_np.load(path, mmap_mode='r', allow_pickle=False) as archive:
        keys = set(archive.files)
        if keys != {'elevation_m'}:
            raise ValueError('Terrain Diffusion NPZ must contain elevation_m only')
        return _i109_np.asarray(archive['elevation_m'])

def load_terrain_diffusion_height(path, *, expected_sha256=None):
    path = _i109_Path(path)
    if not path.is_file() or path.stat().st_size > 2 * 1024 ** 3:
        raise ValueError('missing or oversized Terrain Diffusion height input')
    digest = _i109_hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError('Terrain Diffusion height hash mismatch')
    if path.suffix == '.npy':
        height = _i109_np.load(path, mmap_mode='r', allow_pickle=False)
    elif path.suffix == '.npz':
        height = _load_npz(path)
    else:
        raise ValueError('only .npy or .npz Terrain Diffusion height inputs are supported')
    if not isinstance(height, _i109_np.ndarray) or height.ndim != 2 or height.shape[0] != height.shape[1] or (height.shape[0] < 1024):
        raise ValueError('square Terrain Diffusion height grid of at least 1024 cells required')
    if height.dtype not in (_i109_np.dtype('float32'), _i109_np.dtype('float64')) or not _i109_np.isfinite(height).all():
        raise ValueError('Terrain Diffusion height must be finite float32/float64')
    return {'height_m': height, 'source_sha256': digest, 'shape': list(height.shape), 'source_format': 'terrain_diffusion_height_m_raw_no_fill_no_route'}

def _tile_records(shape, tile_cells):
    rows, columns = shape
    records = []
    tile_id = 0
    for row0 in range(0, rows, tile_cells):
        for column0 in range(0, columns, tile_cells):
            row1, column1 = (min(row0 + tile_cells, rows), min(column0 + tile_cells, columns))
            records.append({'tile_id': tile_id, 'row0': row0, 'row1': row1, 'column0': column0, 'column1': column1, 'owner_key': [row0 // tile_cells, column0 // tile_cells]})
            tile_id += 1
    return records

def _deterministic_receiver(height):
    rows, columns = height.shape
    receiver = _i109_np.full(height.size, -1, _i109_np.int64)
    grid = _i109_np.arange(height.size, dtype=_i109_np.int64).reshape(height.shape)
    candidates = ((-1, 0), (0, -1), (0, 1), (1, 0))
    for row in range(1, rows - 1):
        for column in range(1, columns - 1):
            current = height[row, column]
            best = None
            for delta_row, delta_column in candidates:
                target_row, target_column = (row + delta_row, column + delta_column)
                target_height = height[target_row, target_column]
                if target_height < current and (best is None or target_height < best[0]):
                    best = (target_height, grid[target_row, target_column])
            if best is not None:
                receiver[grid[row, column]] = best[1]
    return receiver

def prepare_large_static(height_m, *, spacing_m=30.0, origin_m_xz=(0.0, 0.0), budget=LargeBenchmarkBudget()):
    validate_budget(budget)
    if not isinstance(height_m, _i109_np.ndarray) or height_m.ndim != 2 or height_m.shape[0] != height_m.shape[1] or (height_m.shape[0] < 1024):
        raise ValueError('large square height grid required')
    if height_m.dtype not in (_i109_np.dtype('float32'), _i109_np.dtype('float64')) or not _i109_np.isfinite(height_m).all():
        raise ValueError('height must be finite Terrain Diffusion float data')
    if height_m.size > budget.max_cells:
        raise ValueError('large static cell budget exceeded')
    _finite_positive(spacing_m, 'spacing_m')
    origin = _i109_np.asarray(origin_m_xz, dtype=_i109_np.float64)
    if origin.shape != (2,) or not _i109_np.isfinite(origin).all():
        raise ValueError('origin must contain two finite coordinates')
    records = _tile_records(height_m.shape, budget.tile_cells)
    if len(records) > budget.max_tiles:
        raise ValueError('tile count budget exceeded')
    receiver = _deterministic_receiver(height_m)
    rows, columns = height_m.shape
    tile_id = _i109_np.empty(height_m.size, _i109_np.int32)
    for record in records:
        tile_id.reshape(height_m.shape)[record['row0']:record['row1'], record['column0']:record['column1']] = record['tile_id']
    receiver_tile = _i109_np.where(receiver >= 0, tile_id[receiver], -1).astype(_i109_np.int32)
    crossings = _i109_np.flatnonzero((receiver >= 0) & (tile_id != receiver_tile))
    tile_pairs = sorted({(int(tile_id[index]), int(receiver_tile[index])) for index in crossings})
    outlets = _i109_np.flatnonzero(receiver < 0).astype(_i109_np.int64)
    edge_faces = []
    for record in records:
        tile = record['tile_id']
        for other in records:
            if other['tile_id'] <= tile:
                continue
            row_touch = record['row1'] == other['row0'] and max(record['column0'], other['column0']) < min(record['column1'], other['column1'])
            column_touch = record['column1'] == other['column0'] and max(record['row0'], other['row0']) < min(record['row1'], other['row1'])
            if row_touch or column_touch:
                edge_faces.append((tile, other['tile_id']))
    return {'arrays': {'height_m': _i109_np.asarray(height_m), 'receiver': receiver, 'tile_id': tile_id, 'receiver_tile_id': receiver_tile, 'outlet_cell': outlets, 'crossing_donor': crossings.astype(_i109_np.int64)}, 'metadata': {'schema': STATIC_SCHEMA, 'shape': [rows, columns], 'spacing_m': float(spacing_m), 'origin_m_xz': origin.tolist(), 'tile_cells': budget.tile_cells, 'tile_count': len(records), 'tiles': records, 'shared_tile_edges': [list(pair) for pair in edge_faces], 'cross_tile_receiver_pairs': [list(pair) for pair in tile_pairs], 'outlet_definition': 'receiver=-1: boundary or deterministic local terminal; not natural outlet certification', 'memory_model': 'full receiver/tile ownership arrays plus one-step tile working set', 'source_evolution': 'raw Terrain Diffusion H0 only; no fill/cut/reassembled regional surface'}}

def validate_large_static(static):
    arrays, meta = (static['arrays'], static['metadata'])
    if meta['schema'] != STATIC_SCHEMA or set(arrays) != {'height_m', 'receiver', 'tile_id', 'receiver_tile_id', 'outlet_cell', 'crossing_donor'}:
        raise ValueError('large static schema')
    shape = tuple(meta['shape'])
    height, receiver, tile_id, receiver_tile = (arrays[key] for key in ('height_m', 'receiver', 'tile_id', 'receiver_tile_id'))
    if height.shape != shape or receiver.shape != (height.size,) or tile_id.shape != receiver.shape or (receiver_tile.shape != receiver.shape):
        raise ValueError('large static shapes')
    if not _i109_np.isfinite(height).all() or receiver.dtype != _i109_np.int64 or tile_id.dtype != _i109_np.int32 or (receiver_tile.dtype != _i109_np.int32):
        raise ValueError('large static dtypes/finite')
    if _i109_np.any((receiver < -1) | (receiver >= height.size)) or not _i109_np.array_equal(receiver_tile, _i109_np.where(receiver >= 0, tile_id[_i109_np.maximum(receiver, 0)], -1)):
        raise ValueError('receiver tile ownership mismatch')
    donors = _i109_np.flatnonzero(receiver >= 0)
    if donors.size and (not _i109_np.all(height.ravel()[receiver[donors]] < height.ravel()[donors])):
        raise ValueError('receiver must be strict downhill')
    if not _i109_np.array_equal(arrays['outlet_cell'], _i109_np.flatnonzero(receiver < 0)) or not _i109_np.array_equal(arrays['crossing_donor'], _i109_np.flatnonzero((receiver >= 0) & (tile_id != receiver_tile))):
        raise ValueError('large outlet/crossing audit')
    return {'cells': int(height.size), 'tile_count': meta['tile_count'], 'outlet_count': int(arrays['outlet_cell'].size), 'cross_tile_edge_count': int(arrays['crossing_donor'].size), 'verified': True}

def run_one_step_storage(static, *, forcing_m3_s=0.0, duration_s=None):
    """Light benchmark: storage and per-tile input only; no 72h routing claim."""
    arrays, meta = (static['arrays'], static['metadata'])
    duration = meta.get('forcing_interval_s', 900.0) if duration_s is None else duration_s
    _finite_positive(forcing_m3_s, 'forcing_m3_s')
    _finite_positive(duration, 'duration_s')
    height = arrays['height_m']
    tile_ids = arrays['tile_id']
    count = meta['tile_count']
    volumes = _i109_np.bincount(tile_ids, minlength=count).astype(_i109_np.float64) * forcing_m3_s * duration
    return {'metadata': {'schema': DYNAMIC_SCHEMA, 'duration_s': float(duration), 'forcing_m3_s': float(forcing_m3_s), 'input_scope': 'uniform source into flat cells; no momentum, no channel cross-section, no long-run routing'}, 'arrays': {'tile_input_volume_m3': volumes, 'total_input_volume_m3': _i109_np.asarray(volumes.sum())}}
SURFACE_NETWORK_TILES_VERSION = 'surface-network-tiles-v1'
SURFACE_NETWORK_TILES_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_WINDOW_CELLS = 65536
MAX_CACHE_BYTES = 64 * 1024 * 1024
MAX_TILE_CELLS = 65536
MAX_TILES = 100000
MAX_SOURCE_BYTES = 512 * 1024 * 1024
SOURCE_FILES = {'manifest.json', 'hydro.npz', 'base/manifest.json', 'base/arrays.npz', 'derived/manifest.json', 'derived/arrays.npz'}

def _surface_network_tiles_plain(value):
    if isinstance(value, (dict, _i112_MappingProxyType)):
        return {key: _surface_network_tiles_plain(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_surface_network_tiles_plain(child) for child in value]
    return value

def _tile_size(tile_cells):
    if type(tile_cells) is not int or not 1 <= tile_cells <= 255 or (tile_cells + 1) ** 2 > MAX_TILE_CELLS:
        raise ValueError('invalid square tile cell span')

def _bounded_hash(path, limit=MAX_FILE_BYTES):
    _reject_link_chain(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('missing or oversized array file')
    return _file_hash(path)

def _records(records, fields, shape=None):
    if set(records) != fields:
        raise ValueError('array fields mismatch')
    total_bytes = 0
    for name, record in records.items():
        if set(record) != {'dtype', 'shape', 'sha256'}:
            raise ValueError('invalid array record')
        dimensions = record['shape']
        if not isinstance(dimensions, (list, tuple)) or not dimensions or any((type(count) is not int or count < 1 for count in dimensions)) or (shape is not None and tuple(dimensions) != tuple(shape)):
            raise ValueError('invalid array dimensions')
        dtype = _i112_np.dtype(record['dtype'])
        if dtype.hasobject or dtype.kind not in 'bifu' or dtype.itemsize > 8:
            raise ValueError('invalid array dtype')
        if name.endswith('mask') and dtype != _i112_np.dtype(bool):
            raise ValueError('invalid mask dtype')
        if name in ('receiver', 'order') and dtype.kind not in 'iu':
            raise ValueError('graph indices must be integers')
        if not isinstance(record['sha256'], str) or len(record['sha256']) != 64:
            raise ValueError('invalid array hash')
        total_bytes += _i112_math.prod(dimensions) * dtype.itemsize
    if total_bytes > MAX_FILE_BYTES:
        raise ValueError('array byte bound exceeded')

def _surface_network_tiles_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result

def _invalid_constant(value):
    raise ValueError('nonfinite JSON constant')

def _surface_network_tiles_json(path):
    if not path.is_file() or path.stat().st_size > SURFACE_NETWORK_TILES_MAX_MANIFEST_BYTES:
        raise ValueError('missing or oversized manifest')
    return _i112_json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_surface_network_tiles_pairs, parse_constant=_invalid_constant)

def _write_json(path, value):
    from terrain_pipeline.artifacts.contracts import canonical_json as _i112_canonical_json
    data = _i112_canonical_json(value)
    if len(data.encode('utf-8')) > SURFACE_NETWORK_TILES_MAX_MANIFEST_BYTES:
        raise ValueError('manifest exceeds bound')
    temporary = path.with_suffix('.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        stream.write(data)
        stream.flush()
        _i112_os.fsync(stream.fileno())
    _i112_os.replace(temporary, path)

def _surface_network_tiles_record(array):
    return {'dtype': array.dtype.str, 'shape': list(array.shape), 'sha256': _i112_hashlib.sha256(_i112_np.ascontiguousarray(array).tobytes()).hexdigest()}

def _read_arrays(path, records, limit=MAX_FILE_BYTES):
    _records(records, set(records))
    _reject_link_chain(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('missing or oversized array file')
    with _i112_zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if sum((entry.file_size for entry in entries)) > limit:
            raise ValueError('total uncompressed array byte bound exceeded')
        if len(entries) != len(records) or {entry.filename for entry in entries} != {name + '.npy' for name in records}:
            raise ValueError('array members mismatch')
        for entry in entries:
            record = records[entry.filename[:-4]]
            if entry.file_size > limit or entry.compress_type != _i112_zipfile.ZIP_STORED:
                raise ValueError('array exceeds bound or is compressed')
            with archive.open(entry) as stream:
                version = _i112_np.lib.format.read_magic(stream)
                if version not in ((1, 0), (2, 0)):
                    raise ValueError('unsupported array header')
                reader = _i112_np.lib.format.read_array_header_1_0 if version == (1, 0) else _i112_np.lib.format.read_array_header_2_0
                shape, fortran, dtype = reader(stream, max_header_size=10000)
                if fortran or dtype.kind not in 'bifu' or dtype.hasobject or (tuple(shape) != tuple(record['shape'])) or (dtype.str != record['dtype']) or (_i112_math.prod(shape) * dtype.itemsize != entry.file_size - stream.tell()):
                    raise ValueError('array header mismatch')
        with _i112_np.load(path, allow_pickle=False) as archive:
            arrays = {name: _surface_network_consumer_immutable(archive[name]) for name in records}
    if {name: _surface_network_tiles_record(array) for name, array in arrays.items()} != _surface_network_tiles_plain(records):
        raise ValueError('array payload mismatch')
    return _i112_MappingProxyType(arrays)

def _geometry(arrays, grid, bounds, source_manifest, graph):
    z0, z1, x0, x1 = bounds
    shape = (z1 - z0, x1 - x0)
    if set(arrays) != GEOMETRY or any((array.shape != shape for array in arrays.values())):
        raise ValueError('tile geometry fields or shape mismatch')
    if any((arrays[name].dtype != bool for name in GEOMETRY if name.endswith('mask'))):
        raise ValueError('invalid mask type')
    if any((not _i112_np.isfinite(arrays[name]).all() for name in GEOMETRY if not name.endswith('mask'))):
        raise ValueError('nonfinite geometry')
    h0, h1, h2 = (arrays[name] for name in ('source_surface_m', 'valley_surface_m', 'final_surface_m'))
    for name, expected in (('valley_cut_m', h0 - h1), ('bed_cut_m', h1 - h2), ('total_cut_m', h0 - h2)):
        if _i112_np.any(arrays[name] < -1e-09) or not _i112_np.allclose(arrays[name], expected, rtol=0, atol=1e-09):
            raise ValueError('H0/H1/H2 cut mismatch')
    wet, water = (arrays['wet_mask'], arrays['water_surface_m'])
    domain, protected, legal = (arrays[name] for name in ('domain_mask', 'protected_mask', 'legal_outlet_mask'))
    if _i112_np.any(water[~wet] != 0) or _i112_np.any(water[wet] <= h2[wet]) or _i112_np.any((wet | (arrays['total_cut_m'] > 1e-09) | legal) & (~domain | protected)):
        raise ValueError('invalid water, domain or protected geometry')
    rows, columns = grid['shape_zx']
    boundary = _i112_np.zeros(shape, bool)
    if z0 == 0:
        boundary[0] = True
    if z1 == rows:
        boundary[-1] = True
    if x0 == 0:
        boundary[:, 0] = True
    if x1 == columns:
        boundary[:, -1] = True
    if _i112_np.any(wet & boundary & ~legal):
        raise ValueError('undeclared wet boundary')
    inputs = source_manifest['proof']['inputs']
    if _i112_np.any(arrays['bed_cut_m'] > inputs['budget']['max_bed_cut_m'] + 1e-09) or _i112_np.any(arrays['valley_cut_m'] > inputs['valley_recipe']['max_valley_depth_m'] + 1e-09):
        raise ValueError('actual tile cut exceeds original depth budget')
    minimum_depth = inputs['inundation_recipe']['min_water_depth_m']
    if _i112_np.any(wet & (water - h2 < minimum_depth - 1e-09)):
        raise ValueError('actual wet depth below original minimum')
    threshold = max(0.5, minimum_depth * 10)
    for axis in (0, 1):
        before = (slice(None, -1), slice(None)) if axis == 0 else (slice(None), slice(None, -1))
        after = (slice(1, None), slice(None)) if axis == 0 else (slice(None), slice(1, None))
        if _i112_np.any(wet[before] & wet[after] & (_i112_np.abs(water[before] - water[after]) > threshold + 1e-09)):
            raise ValueError('adjacent wet stage transition exceeds original threshold')
    positions = graph['world_xz_m']
    columns = _i112_np.rint((positions[:, 0] - grid['origin_x_m']) / grid['spacing_x_m']).astype(int)
    rows = _i112_np.rint((positions[:, 1] - grid['origin_z_m']) / grid['spacing_z_m']).astype(int)
    inside = (rows >= z0) & (rows < z1) & (columns >= x0) & (columns < x1)
    active = graph['active_mask']
    selected = inside & active
    local_rows, local_columns = (rows[selected] - z0, columns[selected] - x0)
    if not _i112_np.all(wet[local_rows, local_columns]) or not _i112_np.allclose(water[local_rows, local_columns], graph['node_stage_m'][selected], atol=1e-08, rtol=0):
        raise ValueError('tile active node wet/stage differs from graph')
    outlets = inside & active & graph['outlet_mask']
    if not _i112_np.all(legal[rows[outlets] - z0, columns[outlets] - x0]):
        raise ValueError('tile active outlet lacks legal boundary')
    for donor in _i112_np.flatnonzero(active & (graph['receiver'] >= 0)):
        target = int(graph['receiver'][donor])
        if max(rows[donor], rows[target]) < z0 or min(rows[donor], rows[target]) >= z1 or max(columns[donor], columns[target]) < x0 or (min(columns[donor], columns[target]) >= x1):
            continue
        steps = max(abs(rows[target] - rows[donor]), abs(columns[target] - columns[donor]))
        previous_bed = None
        for step in range(steps + 1):
            fraction = step / steps
            row = int(round(rows[donor] + fraction * (rows[target] - rows[donor])))
            column = int(round(columns[donor] + fraction * (columns[target] - columns[donor])))
            if not (z0 <= row < z1 and x0 <= column < x1):
                previous_bed = None
                continue
            row -= z0
            column -= x0
            stage = graph['node_stage_m'][donor] * (1 - fraction) + graph['node_stage_m'][target] * fraction
            depth = stage - h2[row, column]
            if not wet[row, column] or depth < inputs['stage_recipe']['min_clearance_m'] - 1e-09 or depth > inputs['stage_recipe']['max_depth_m'] + 1e-09 or (previous_bed is not None and h2[row, column] > previous_bed + 1e-09):
                raise ValueError('tile channel edge is dry, blocked or reverse-sloped')
            previous_bed = h2[row, column]

def _tile_specs(grid, tile_cells):
    rows, columns = grid['shape_zx']
    for z0 in range(0, rows - 1, tile_cells):
        for x0 in range(0, columns - 1, tile_cells):
            yield [z0, min(z0 + tile_cells + 1, rows), x0, min(x0 + tile_cells + 1, columns)]

def _source_files(source, staging, source_manifest):
    copied = staging / 'source'
    _reject_link_chain(copied)
    declared = {'manifest.json': _file_hash(source / 'manifest.json'), **source_manifest['files']}
    if set(declared) != SOURCE_FILES:
        raise ValueError('unexpected source delivery file set')
    total_bytes = 0
    for name in declared:
        path = source / name
        _reject_link_chain(path)
        if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError('source file exceeds bound')
        total_bytes += path.stat().st_size
    if total_bytes > MAX_SOURCE_BYTES:
        raise ValueError('source total byte bound exceeded')
    copied.mkdir(exist_ok=True)
    for name, expected in declared.items():
        path = copied / name
        _reject_link_chain(path)
        path.parent.mkdir(exist_ok=True)
        if path.exists():
            if _file_hash(path) != expected:
                raise ValueError('staged source file differs')
        else:
            _i112_shutil.copyfile(source / name, path)
        if _file_hash(path) != expected:
            raise ValueError('source file changed during copy')
    return copied

def _prepare_unlocked(source_path, destination_path, *, tile_cells=64, max_tiles=None, cancel=None, resume=False):
    """Return False when paused; return destination after a complete atomic publication."""
    from terrain_pipeline.artifacts.contracts import digest as _i112_digest
    source, destination = (_i112_Path(source_path), _i112_Path(destination_path))
    staging = destination.with_name(destination.name + '.staging')
    for path in (source, destination, staging):
        _reject_link_chain(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir() or source.resolve() == staging.resolve():
        raise ValueError('invalid source or destination')
    _tile_size(tile_cells)
    if max_tiles is not None and (type(max_tiles) is not int or max_tiles < 1):
        raise ValueError('invalid work budget')
    delivery = load_surface_network_delivery(source)
    source_manifest = _surface_network_tiles_json(source / 'manifest.json')
    grid = source_manifest['grid']
    if _i112_math.ceil((grid['shape_zx'][0] - 1) / tile_cells) * _i112_math.ceil((grid['shape_zx'][1] - 1) / tile_cells) > MAX_TILES:
        raise ValueError('tile count bound exceeded')
    specs = list(_tile_specs(grid, tile_cells))
    recipe = {'tile_cells': tile_cells, 'grid': grid, 'source_content_id': source_manifest['content_id'], 'source_manifest': source_manifest, 'source_manifest_sha256': _file_hash(source / 'manifest.json'), 'source_windows': [{field: _surface_network_tiles_record(delivery['geometry'][field][bounds[0]:bounds[1], bounds[2]:bounds[3]]) for field in GEOMETRY} for bounds in specs]}
    if (staging / 'progress.json').exists():
        if not resume:
            raise FileExistsError(staging)
        progress = _surface_network_tiles_json(staging / 'progress.json')
        (staging / 'manifest.json').unlink(missing_ok=True)
        if progress['recipe'] != recipe or progress['bounds'] != specs:
            raise ValueError('resume source or recipe changed')
    else:
        if resume:
            raise FileNotFoundError(staging)
        staging.mkdir(exist_ok=True)
        (staging / 'tiles').mkdir()
        (staging / 'proof').mkdir()
        progress = {'recipe': recipe, 'bounds': specs, 'completed': {}}
        _write_json(staging / 'progress.json', progress)
    copied = _source_files(source, staging, source_manifest)
    if _file_hash(copied / 'manifest.json') != recipe['source_manifest_sha256']:
        raise ValueError('staged source manifest differs')
    staged_delivery = load_surface_network_delivery(copied)
    if _surface_network_tiles_plain(staged_delivery['manifest']) != source_manifest:
        raise ValueError('staged source identity differs')
    graph_path = staging / 'graph.npz'
    if not graph_path.exists():
        _i112_np.savez(graph_path, **delivery['centerline'])
    graph_records = {name: _surface_network_tiles_record(array) for name, array in delivery['centerline'].items()}
    graph = _read_arrays(graph_path, graph_records)
    if any((not _i112_np.array_equal(graph[name], delivery['centerline'][name]) for name in GRAPH)):
        raise ValueError('staged graph differs from source')
    expected_names = {f'{index:06d}.npz': (index, bounds) for index, bounds in enumerate(specs)}
    if set(progress['completed']) - set(expected_names):
        raise ValueError('unexpected completed tile')
    for name, expected in progress['completed'].items():
        path = staging / 'tiles' / name
        _reject_link_chain(path)
        if _bounded_hash(path) != expected['sha256']:
            raise ValueError('completed tile damaged; resume refused')
        index, bounds = expected_names[name]
        arrays = _read_arrays(path, expected['arrays'])
        proof = _read_arrays(staging / 'proof' / name, recipe['source_windows'][index])
        _geometry(arrays, grid, bounds, source_manifest, graph)
        if any((not _i112_np.array_equal(arrays[field], proof[field]) or not _i112_np.array_equal(arrays[field], delivery['geometry'][field][bounds[0]:bounds[1], bounds[2]:bounds[3]]) for field in GEOMETRY)):
            raise ValueError('completed tile differs from source; resume refused')
    done = 0
    for index, bounds in enumerate(specs):
        name = f'{index:06d}.npz'
        if name in progress['completed']:
            continue
        if cancel is not None and cancel():
            return False
        if max_tiles is not None and done >= max_tiles:
            return False
        path = staging / 'tiles' / name
        _reject_link_chain(path)
        arrays = {field: delivery['geometry'][field][bounds[0]:bounds[1], bounds[2]:bounds[3]] for field in GEOMETRY}
        _geometry(arrays, grid, bounds, source_manifest, graph)
        proof_path = staging / 'proof' / name
        _reject_link_chain(proof_path)
        with proof_path.with_suffix('.tmp').open('wb') as stream:
            _i112_np.savez(stream, **arrays)
        _i112_os.replace(proof_path.with_suffix('.tmp'), proof_path)
        temporary = path.with_suffix('.tmp')
        with temporary.open('wb') as stream:
            _i112_np.savez(stream, **arrays)
        _i112_os.replace(temporary, path)
        progress['completed'][name] = {'sha256': _file_hash(path), 'arrays': {field: _surface_network_tiles_record(array) for field, array in arrays.items()}}
        _write_json(staging / 'progress.json', progress)
        done += 1
    tiles = [{'path': f'tiles/{index:06d}.npz', 'bounds': bounds, 'proof_sha256': _file_hash(staging / 'proof' / f'{index:06d}.npz'), **progress['completed'][f'{index:06d}.npz']} for index, bounds in enumerate(specs)]
    manifest = {'version': SURFACE_NETWORK_TILES_VERSION, 'recipe': recipe, 'tiles': tiles, 'graph': {'path': 'graph.npz', 'sha256': _file_hash(graph_path), 'arrays': graph_records}, 'source_files': {name: _file_hash(copied / name) for name in sorted(SOURCE_FILES)}, 'limits': {'max_window_cells': MAX_WINDOW_CELLS, 'max_cache_bytes': MAX_CACHE_BYTES, 'max_file_bytes': MAX_FILE_BYTES}}
    manifest['content_id'] = _i112_digest(manifest)
    if cancel is not None and cancel():
        return False
    _write_json(staging / 'manifest.json', manifest)
    if cancel is not None and cancel():
        (staging / 'manifest.json').unlink()
        return False
    verify_all_tiles(load_surface_network_tiles(staging, allow_staging=True))
    if cancel is not None and cancel():
        (staging / 'manifest.json').unlink()
        return False
    if destination.exists():
        raise FileExistsError(destination)
    _i112_os.rename(staging, destination)
    return destination

def prepare_surface_network_tiles(source_path, destination_path, *, tile_cells=64, max_tiles=None, cancel=None, resume=False):
    """Validate a delivery and prepare bounded tiles; resume uses exclusive staging access."""
    destination = _i112_Path(destination_path)
    _tile_size(tile_cells)
    if max_tiles is not None and (type(max_tiles) is not int or max_tiles < 1):
        raise ValueError('invalid work budget')
    if type(resume) is not bool or (cancel is not None and (not callable(cancel))):
        raise ValueError('invalid resume/cancel argument')
    staging = destination.with_name(destination.name + '.staging')
    source = _i112_Path(source_path).resolve()
    if destination.resolve().is_relative_to(source) or staging.resolve().is_relative_to(source):
        raise ValueError('destination must not be inside the immutable source')
    _reject_link_chain(destination)
    _reject_link_chain(staging)
    if destination.exists():
        raise FileExistsError(destination)
    staging.mkdir(exist_ok=True)
    lock = staging / '.prepare.lock'
    token = _i112_uuid.uuid4().hex
    owned = False
    try:
        with lock.open('x') as stream:
            stream.write(token)
        owned = True
        try:
            return _prepare_unlocked(source_path, destination_path, tile_cells=tile_cells, max_tiles=max_tiles, cancel=cancel, resume=resume)
        except Exception:
            (staging / 'manifest.json').unlink(missing_ok=True)
            raise
    finally:
        if owned:
            for candidate in (lock, destination / '.prepare.lock'):
                if candidate.is_file() and candidate.read_text(encoding='utf-8') == token:
                    candidate.unlink()

class SurfaceNetworkTiles:

    def __init__(self, path, manifest, graph):
        self.path = path
        self.manifest = _surface_network_consumer_freeze(manifest)
        self.centerline = graph
        self._cache = {}
        self._cache_bytes = 0

    def _tile(self, index):
        tile = self.manifest['tiles'][index]
        path = self.path / tile['path']
        _reject_link_chain(path)
        if _bounded_hash(path) != tile['sha256']:
            raise ValueError('tile file hash mismatch')
        recipe = self.manifest['recipe']
        proof_path = self.path / 'proof' / f'{index:06d}.npz'
        _reject_link_chain(proof_path)
        if _bounded_hash(proof_path) != tile['proof_sha256']:
            raise ValueError('source window file hash mismatch')
        if index in self._cache:
            return self._cache[index]
        size = sum((_i112_math.prod(record['shape']) * _i112_np.dtype(record['dtype']).itemsize for record in tile['arrays'].values()))
        if size > MAX_CACHE_BYTES:
            raise ValueError('tile exceeds cache bound')
        arrays = _read_arrays(path, tile['arrays'])
        proof = _read_arrays(proof_path, recipe['source_windows'][index])
        if any((not _i112_np.array_equal(arrays[name], proof[name]) for name in GEOMETRY)):
            raise ValueError('tile differs from validated source window')
        _geometry(arrays, recipe['grid'], tile['bounds'], recipe['source_manifest'], self.centerline)
        size = sum((array.nbytes for array in arrays.values()))
        if size > MAX_CACHE_BYTES:
            raise ValueError('tile exceeds cache bound')
        if self._cache_bytes + size > MAX_CACHE_BYTES:
            self._cache.clear()
            self._cache_bytes = 0
        self._cache[index] = arrays
        self._cache_bytes += size
        return arrays

def load_surface_network_tiles(path, *, allow_staging=False):
    """Load the index and graph only; tiles are validated when accessed."""
    from terrain_pipeline.artifacts.contracts import digest as _i112_digest
    directory = _i112_Path(path)
    _reject_link_chain(directory)
    if not allow_staging and ((directory / '.prepare.lock').exists() or ((directory / 'progress.json').exists() and directory.name.endswith('.staging'))):
        raise ValueError('unfinished tile staging directory')
    manifest = _surface_network_tiles_json(directory / 'manifest.json')
    if set(manifest) != {'version', 'recipe', 'tiles', 'graph', 'source_files', 'limits', 'content_id'} or manifest['version'] != SURFACE_NETWORK_TILES_VERSION:
        raise ValueError('invalid tile manifest')
    if _i112_digest({key: value for key, value in manifest.items() if key != 'content_id'}) != manifest['content_id']:
        raise ValueError('tile manifest identity mismatch')
    recipe = manifest['recipe']
    if set(recipe) != {'tile_cells', 'grid', 'source_content_id', 'source_manifest', 'source_manifest_sha256', 'source_windows'}:
        raise ValueError('invalid tile recipe')
    source_manifest = recipe['source_manifest']
    if set(manifest['source_files']) != SOURCE_FILES or manifest['source_files']['manifest.json'] != recipe['source_manifest_sha256'] or {name: value for name, value in manifest['source_files'].items() if name != 'manifest.json'} != source_manifest['files']:
        raise ValueError('source file identity chain mismatch')
    if source_manifest.get('content_id') != recipe['source_content_id'] or _i112_digest({key: value for key, value in source_manifest.items() if key != 'content_id'}) != recipe['source_content_id'] or source_manifest.get('grid') != recipe['grid']:
        raise ValueError('source identity chain mismatch')
    grid = recipe['grid']
    if type(recipe['tile_cells']) is not int or not 1 <= recipe['tile_cells'] <= 255 or len(grid['shape_zx']) != 2 or any((type(count) is not int or count < 2 for count in grid['shape_zx'])) or (_i112_math.prod(grid['shape_zx']) > 1000000) or any((isinstance(grid[name], bool) or not isinstance(grid[name], (int, float)) or (not _i112_math.isfinite(grid[name])) or (name.startswith('spacing') and grid[name] <= 0) for name in ('origin_x_m', 'origin_z_m', 'spacing_x_m', 'spacing_z_m'))):
        raise ValueError('invalid tile grid')
    inputs = source_manifest['proof']['inputs']
    for name in ('budget', 'valley_recipe', 'stage_recipe', 'inundation_recipe'):
        if any((isinstance(value, bool) or not isinstance(value, (int, float)) or (not _i112_math.isfinite(value)) or (value < 0) for value in inputs[name].values())):
            raise ValueError('invalid original numeric constraint')
    if source_manifest['proof']['accepted'] is not True or source_manifest['proof']['status'] != 'accepted':
        raise ValueError('source is not an accepted delivery')
    _tile_size(recipe['tile_cells'])
    if _i112_math.ceil((grid['shape_zx'][0] - 1) / recipe['tile_cells']) * _i112_math.ceil((grid['shape_zx'][1] - 1) / recipe['tile_cells']) > MAX_TILES:
        raise ValueError('tile count bound exceeded')
    specs = list(_tile_specs(grid, recipe['tile_cells']))
    if len(manifest['tiles']) != len(specs) or len(recipe['source_windows']) != len(specs):
        raise ValueError('tile index count mismatch')
    for index, (tile, bounds) in enumerate(zip(manifest['tiles'], specs)):
        if set(tile) != {'path', 'bounds', 'sha256', 'arrays', 'proof_sha256'}:
            raise ValueError('invalid tile record')
        if tile['path'] != f'tiles/{index:06d}.npz' or tile['bounds'] != bounds or set(tile['arrays']) != GEOMETRY:
            raise ValueError('tile index mismatch')
        if any((record['shape'] != [bounds[1] - bounds[0], bounds[3] - bounds[2]] for record in tile['arrays'].values())):
            raise ValueError('tile array shape mismatch')
        shape = (bounds[1] - bounds[0], bounds[3] - bounds[2])
        _records(tile['arrays'], GEOMETRY, shape)
        _records(recipe['source_windows'][index], GEOMETRY, shape)
        if any((tile['arrays'][name]['dtype'] != source_manifest['arrays'][name]['dtype'] for name in GEOMETRY)):
            raise ValueError('tile/source dtype mismatch')
    if manifest['limits'] != {'max_window_cells': MAX_WINDOW_CELLS, 'max_cache_bytes': MAX_CACHE_BYTES, 'max_file_bytes': MAX_FILE_BYTES}:
        raise ValueError('unsupported tile limits')
    graph_info = manifest['graph']
    _reject_link_chain(directory / 'graph.npz')
    _records(graph_info['arrays'], GRAPH)
    count_shape = graph_info['arrays']['receiver']['shape']
    if len(count_shape) != 1 or count_shape[0] > 250000 or any((record['shape'] != ([count_shape[0], 2] if name == 'world_xz_m' else count_shape) for name, record in graph_info['arrays'].items())):
        raise ValueError('invalid coarse graph dimensions')
    if graph_info['arrays'] != {name: source_manifest['arrays'][name] for name in GRAPH}:
        raise ValueError('graph differs from source records')
    if graph_info['path'] != 'graph.npz' or set(graph_info['arrays']) != GRAPH or _bounded_hash(directory / 'graph.npz') != graph_info['sha256']:
        raise ValueError('graph identity mismatch')
    graph = _read_arrays(directory / 'graph.npz', graph_info['arrays'])
    count = graph['receiver'].size
    if count > 250000 or graph['world_xz_m'].shape != (count, 2) or any((graph[name].shape != (count,) for name in GRAPH - {'world_xz_m'})) or any((graph[name].dtype != bool for name in ('active_mask', 'outlet_mask'))) or (not _i112_np.isfinite(graph['world_xz_m']).all()) or any((not _i112_np.isfinite(graph[name]).all() for name in ('discharge_m3_s', 'local_discharge_m3_s', 'node_stage_m'))) or _i112_np.any(graph['discharge_m3_s'] < 0) or _i112_np.any(graph['local_discharge_m3_s'] < -1e-08) or _i112_np.any((graph['receiver'] < -1) | (graph['receiver'] >= count)) or (not _i112_np.array_equal(graph['outlet_mask'], graph['receiver'] == -1)) or (not _i112_np.array_equal(_i112_np.sort(graph['order']), _i112_np.arange(count))):
        raise ValueError('invalid coarse graph size')
    local = graph['discharge_m3_s'].copy()
    donors = _i112_np.flatnonzero(graph['receiver'] >= 0)
    rank = _i112_np.empty(count, dtype=int)
    rank[graph['order']] = _i112_np.arange(count)
    if _i112_np.any(rank[graph['receiver'][donors]] >= rank[donors]):
        raise ValueError('coarse graph order is not topological')
    positions = graph['world_xz_m']
    if len(_i112_np.unique(positions, axis=0)) != count:
        raise ValueError('duplicate graph coordinates')
    for axis, origin, spacing, length in ((0, grid['origin_x_m'], grid['spacing_x_m'], grid['shape_zx'][1]), (1, grid['origin_z_m'], grid['spacing_z_m'], grid['shape_zx'][0])):
        indices = (positions[:, axis] - origin) / spacing
        if _i112_np.any((indices < 0) | (indices > length - 1)) or not _i112_np.allclose(indices, _i112_np.rint(indices), rtol=0, atol=1e-08):
            raise ValueError('coarse graph is not on the fine grid')
    if _i112_np.any(graph['active_mask'][donors] & ~graph['active_mask'][graph['receiver'][donors]]) or _i112_np.any(graph['node_stage_m'][~graph['active_mask']] != 0):
        raise ValueError('invalid active graph/stage')
    _i112_np.subtract.at(local, graph['receiver'][donors], graph['discharge_m3_s'][donors])
    if not _i112_np.allclose(local, graph['local_discharge_m3_s'], atol=1e-08, rtol=0):
        raise ValueError('coarse graph Q mismatch')
    return SurfaceNetworkTiles(directory, manifest, graph)

def slice_surface_network_tiles(store, z_slice, x_slice):
    grid = store.manifest['recipe']['grid']
    for part, length in ((z_slice, grid['shape_zx'][0]), (x_slice, grid['shape_zx'][1])):
        if not isinstance(part, slice) or part.step not in (None, 1) or type(part.start) is not int or (type(part.stop) is not int) or (not 0 <= part.start < part.stop <= length):
            raise ValueError('window requires bounded unit-step slices')
    shape = (z_slice.stop - z_slice.start, x_slice.stop - x_slice.start)
    if _i112_math.prod(shape) > MAX_WINDOW_CELLS:
        raise ValueError('window cell bound exceeded')
    result = {name: _i112_np.empty(shape, dtype=_i112_np.dtype(store.manifest['tiles'][0]['arrays'][name]['dtype'])) for name in GEOMETRY}
    covered = _i112_np.zeros(shape, bool)
    for index, tile in enumerate(store.manifest['tiles']):
        z0, z1, x0, x1 = tile['bounds']
        top, bottom = (max(z0, z_slice.start), min(z1, z_slice.stop))
        left, right = (max(x0, x_slice.start), min(x1, x_slice.stop))
        if top >= bottom or left >= right:
            continue
        arrays = store._tile(index)
        target = _i112_np.s_[top - z_slice.start:bottom - z_slice.start, left - x_slice.start:right - x_slice.start]
        source = _i112_np.s_[top - z0:bottom - z0, left - x0:right - x0]
        overlap = covered[target]
        for name in GEOMETRY:
            if _i112_np.any(overlap) and (not _i112_np.array_equal(result[name][target][overlap], arrays[name][source][overlap])):
                raise ValueError('shared tile seam mismatch')
            result[name][target] = arrays[name][source]
        covered[target] = True
    if not covered.all():
        raise ValueError('tile coverage gap')
    result['water_depth_m'] = _i112_np.where(result['wet_mask'], result['water_surface_m'] - result['final_surface_m'], 0.0)
    return _i112_MappingProxyType({'origin_x_m': grid['origin_x_m'] + x_slice.start * grid['spacing_x_m'], 'origin_z_m': grid['origin_z_m'] + z_slice.start * grid['spacing_z_m'], 'spacing_x_m': grid['spacing_x_m'], 'spacing_z_m': grid['spacing_z_m'], 'vertical_datum': grid['vertical_datum'], 'unit': 'm', 'content_id': store.manifest['content_id'], 'arrays': _i112_MappingProxyType({name: _surface_network_consumer_immutable(array) for name, array in result.items()})})

def sample_surface_network_tiles(store, world_x_m, world_z_m):
    grid = store.manifest['recipe']['grid']
    column = _world_index(world_x_m, grid['origin_x_m'], grid['spacing_x_m'], grid['shape_zx'][1])
    row = _world_index(world_z_m, grid['origin_z_m'], grid['spacing_z_m'], grid['shape_zx'][0])
    return slice_surface_network_tiles(store, slice(row, row + 1), slice(column, column + 1))

def slice_surface_network_tiles_world(store, bounds_xz_m):
    if not isinstance(bounds_xz_m, (tuple, list)) or len(bounds_xz_m) != 4:
        raise ValueError('world bounds require xmin,zmin,xmax,zmax')
    grid = store.manifest['recipe']['grid']
    x0, z0, x1, z1 = bounds_xz_m
    columns, rows = (grid['shape_zx'][1], grid['shape_zx'][0])
    left = _world_index(x0, grid['origin_x_m'], grid['spacing_x_m'], columns)
    right = _world_index(x1, grid['origin_x_m'], grid['spacing_x_m'], columns)
    top = _world_index(z0, grid['origin_z_m'], grid['spacing_z_m'], rows)
    bottom = _world_index(z1, grid['origin_z_m'], grid['spacing_z_m'], rows)
    return slice_surface_network_tiles(store, slice(top, bottom + 1), slice(left, right + 1))

def verify_all_tiles(store):
    """Explicit full source replay, seams and unique-node/global-weight integration."""
    from terrain_pipeline.artifacts.contracts import canonical_json as _i112_canonical_json
    source = store.path / 'source'
    for name, expected in store.manifest['source_files'].items():
        if _i112_Path(name).is_absolute() or '..' in _i112_Path(name).parts or '\\' in name or (':' in name):
            raise ValueError('invalid source proof path')
        path = source / name
        _reject_link_chain(path)
        if _file_hash(path) != expected:
            raise ValueError('source proof file mismatch')
    delivery = load_surface_network_delivery(source)
    if _i112_canonical_json(_surface_network_tiles_plain(delivery['manifest'])) != _i112_canonical_json(_surface_network_tiles_plain(store.manifest['recipe']['source_manifest'])):
        raise ValueError('source manifest mismatch')
    for name in GRAPH:
        if not _i112_np.array_equal(store.centerline[name], delivery['centerline'][name]):
            raise ValueError('coarse graph differs from source')
    grid = store.manifest['recipe']['grid']
    shape = tuple(grid['shape_zx'])
    unique = {name: _i112_np.empty(shape, dtype=delivery['geometry'][name].dtype) for name in GEOMETRY}
    covered = _i112_np.zeros(shape, dtype=bool)
    tile_integrals = {name: {'volume_m3': 0.0, 'area_m2': 0.0} for name in ('valley_cut_m', 'bed_cut_m', 'total_cut_m')}
    cell_area = grid['spacing_x_m'] * grid['spacing_z_m']
    for index, tile in enumerate(store.manifest['tiles']):
        arrays = store._tile(index)
        z0, z1, x0, x1 = tile['bounds']
        target = _i112_np.s_[z0:z1, x0:x1]
        overlap = covered[target]
        for name in GEOMETRY:
            if _i112_np.any(overlap) and (not _i112_np.array_equal(unique[name][target][overlap], arrays[name][overlap])):
                raise ValueError('shared tile seam mismatch')
            if not _i112_np.array_equal(arrays[name], delivery['geometry'][name][z0:z1, x0:x1]):
                raise ValueError('tile differs from validated source')
            unique[name][target] = arrays[name]
        covered[target] = True
        weights = _i112_np.ones((z1 - z0, x1 - x0))
        weights[[0, -1], :] *= 0.5
        weights[:, [0, -1]] *= 0.5
        for name in tile_integrals:
            tile_integrals[name]['volume_m3'] += float(_i112_np.sum(arrays[name] * weights) * cell_area)
            tile_integrals[name]['area_m2'] += float(_i112_np.sum((arrays[name] > 1e-09) * weights) * cell_area)
    if not covered.all():
        raise ValueError('tile coverage gap')
    weights = _i112_np.ones(shape)
    weights[[0, -1], :] *= 0.5
    weights[:, [0, -1]] *= 0.5
    integrals = {name: {'volume_m3': float(_i112_np.sum(unique[name] * weights) * cell_area), 'area_m2': float(_i112_np.sum((unique[name] > 1e-09) * weights) * cell_area)} for name in tile_integrals}
    for name in integrals:
        for quantity in integrals[name]:
            if not _i112_math.isclose(integrals[name][quantity], tile_integrals[name][quantity], rel_tol=1e-12, abs_tol=1e-09):
                raise ValueError('tile/global integral mismatch')
    return _surface_network_consumer_freeze({'verified': True, 'unique_nodes': int(covered.sum()), 'tile_count': len(store.manifest['tiles']), 'integrals': integrals, 'tile_weighted_integrals': tile_integrals, 'source_replayed': True, 'seams_equal': True})
SURFACE_VARIABLE_STORAGE_VERSION = 'surface-variable-storage-v1'
SURFACE_VARIABLE_STORAGE_GEOMETRY = 'wet-cell-triangle-vertex-lumped-prisms'

@_i113_dataclass(frozen=True)
class StorageResources:
    max_nodes: int = 4096
    max_edges: int = 16384
    max_steps: int = 4096
    max_wet_cells: int = 100000
    max_work: int = 2000000
    max_retained_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES
    max_working_bytes: int = SURFACE_FINE_MOSAIC_MAX_BYTES

    def __post_init__(self):
        ceilings = (4096, 16384, 4096, 100000, 2000000, SURFACE_FINE_MOSAIC_MAX_BYTES, SURFACE_FINE_MOSAIC_MAX_BYTES)
        for value, ceiling in zip(vars(self).values(), ceilings):
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError('invalid storage resource')

def _surface_variable_storage_geometry(source):
    beds = []
    weights = []
    owners = []
    offsets = [0]
    for binding in source['bindings']:
        fine = binding['source_mosaic']
        triangle_ids = (2 * binding['wet_cell_ids'][:, None] + _i113_np.arange(2)).ravel()
        corners = fine['triangles'][triangle_ids]
        heights = fine['nodes']['h2_m'][corners].reshape(-1, 6)
        area = fine['grid']['spacing_x_m'] * fine['grid']['spacing_z_m']
        for node in range(len(binding['node_flat_ids'])):
            values = heights[binding['wet_cell_owner'] == node].ravel()
            if not len(values) or not _i113_np.all(_i113_np.isfinite(values)):
                raise ValueError('empty or nonfinite node support')
            beds.append(values)
            weights.append(_i113_np.full(len(values), area / 6))
            owners.append(_i113_np.full(len(values), len(offsets) - 1, _i113_np.int64))
            offsets.append(offsets[-1] + len(values))
    return (_i113_np.asarray(offsets, _i113_np.int64), _i113_np.concatenate(beds).astype(float), _i113_np.concatenate(weights).astype(float), _i113_np.concatenate(owners))

def _knots(offsets, beds, weights):
    stages = []
    volumes = []
    knot_offsets = [0]
    for index in range(len(offsets) - 1):
        start, stop = offsets[index:index + 2]
        node_beds = beds[start:stop]
        node_weights = weights[start:stop]
        unique = _i113_np.unique(node_beds)
        stages.append(unique)
        volumes.append(_i113_np.asarray([volume(stage, node_beds, node_weights) for stage in unique]))
        knot_offsets.append(knot_offsets[-1] + len(unique))
    return (_i113_np.asarray(knot_offsets, _i113_np.int64), _i113_np.concatenate(stages), _i113_np.concatenate(volumes))

def volume(stage, beds, weights):
    return float(_i113_np.dot(weights, _i113_np.maximum(stage - beds, 0)))

def _invert(amount, beds, weights):
    if not _i113_math.isfinite(amount) or amount < 0:
        raise ValueError('nonfinite or negative storage cannot be inverted')
    if amount == 0:
        return float(_i113_np.min(beds))
    order = _i113_np.argsort(beds)
    sorted_beds = beds[order]
    sorted_weights = weights[order]
    active_weight = 0.0
    previous_bed = float(sorted_beds[0])
    accumulated = 0.0
    for bed, weight in zip(sorted_beds, sorted_weights):
        bed = float(bed)
        candidate = accumulated + active_weight * (bed - previous_bed)
        if amount <= candidate and active_weight > 0:
            return previous_bed + (amount - accumulated) / active_weight
        accumulated = candidate
        active_weight += float(weight)
        previous_bed = bed
    return previous_bed + (amount - accumulated) / active_weight

def _inputs(source, conductance_m2_s, local_q_m3_s, tailwater_m, dt_s, max_depth_m, resources):
    if type(dt_s) not in (int, float) or type(max_depth_m) not in (int, float):
        raise ValueError('physical time and maximum depth must be real scalars, not booleans')
    nodes = len(source['node_keys'])
    edges = len(source['edges'])
    local = _i113_np.asarray(local_q_m3_s)
    tailwater = _i113_np.asarray(tailwater_m)
    boundary = source['dynamic']['inputs']['boundary_mask']
    initial = source['dynamic']['inputs']['initial_stage_m']
    conductance = _i113_np.asarray(conductance_m2_s)
    if local.ndim != 2 or local.shape[1] != nodes or (not 1 <= len(local) <= resources.max_steps) or (tailwater.shape != (len(local) + 1, int(boundary.sum()))) or (conductance.shape != (edges,)) or any((value.dtype.kind not in 'fiu' for value in (local, tailwater, conductance))) or (nodes > resources.max_nodes) or (edges > resources.max_edges) or (len(local) * (nodes + edges) > resources.max_work):
        raise ValueError('forcing shape or resource limit')
    if not all((_i113_np.all(_i113_np.isfinite(value)) for value in (local, tailwater, conductance))) or _i113_np.any(conductance <= 0) or _i113_np.any(local[:, boundary] != 0) or (not _i113_np.array_equal(tailwater[0], initial[boundary])) or (type(dt_s) is bool) or (type(max_depth_m) is bool) or (not _i113_math.isfinite(dt_s)) or (dt_s <= 0) or (not _i113_math.isfinite(max_depth_m)) or (max_depth_m <= 0) or (not _i113_math.isfinite(dt_s * len(local))):
        raise ValueError('invalid forcing, tailwater or physical time')
    if sum((len(item['wet_cell_ids']) for item in source['bindings'])) > resources.max_wet_cells:
        raise ValueError('wet-cell resource limit')
    return (_i113_np.asarray(conductance, dtype=float), _i113_np.asarray(local, dtype=float), _i113_np.asarray(tailwater, dtype=float), boundary, initial)

def _surface_variable_storage_preflight(source, local_q_m3_s, resources):
    if not isinstance(source, dict) and (not hasattr(source, 'keys')):
        raise ValueError('saved forest required')
    bindings = source['bindings']
    nodes = len(source['node_keys'])
    edges = len(source['edges'])
    local = _i113_np.asarray(local_q_m3_s)
    if local.ndim != 2:
        raise ValueError('local Q must be two dimensional')
    steps = len(local)
    wet = sum((len(binding['wet_cell_ids']) for binding in bindings))
    if nodes > resources.max_nodes or edges > resources.max_edges or wet > resources.max_wet_cells or (steps > resources.max_steps) or (steps * (nodes + edges) > resources.max_work):
        raise ValueError('storage resource limit')
    source_bytes = _surface_fine_mosaic_size(source)
    support_bytes = wet * 6 * 48 + 2 * (nodes + 1) * 8
    state_bytes = (steps + 1) * nodes * 16 + steps * (edges + 6 * len(bindings)) * 8
    forcing_bytes = steps * nodes * 8 + (steps + 1) * len(bindings) * 8
    if source_bytes + support_bytes + state_bytes + forcing_bytes > resources.max_retained_bytes or 2 * source_bytes + 3 * support_bytes + 2 * state_bytes + 2 * forcing_bytes > resources.max_working_bytes:
        raise ValueError('storage byte resource preflight')

def _advance(source, offsets, beds, weights, conductance, local, tailwater, dt_s, max_depth_m, cancel):
    edges = source['edges']
    boundary = source['dynamic']['inputs']['boundary_mask']
    initial = source['dynamic']['inputs']['initial_stage_m']
    node_bed = source['dynamic']['inputs']['bed_m']
    count = len(initial)
    min_bed = _i113_np.array([beds[offsets[index]:offsets[index + 1]].min() for index in range(count)])
    minimum_area = _i113_np.array([weights[offsets[index]:offsets[index + 1]][beds[offsets[index]:offsets[index + 1]] == min_bed[index]].sum() for index in range(count)])
    incident = _i113_np.zeros(count)
    _i113_np.add.at(incident, edges[:, 0], conductance)
    _i113_np.add.at(incident, edges[:, 1], conductance)
    if _i113_np.any(dt_s * incident[~boundary] / minimum_area[~boundary] > 1):
        raise ValueError('dt*incident K/minimum effective area exceeds one')
    if _i113_np.any(initial < min_bed) or _i113_np.any(initial - node_bed > max_depth_m):
        raise ValueError('initial stage outside support/depth')
    stages = [_i113_np.array(initial, float)]
    storage = _i113_np.array([volume(initial[index], beds[offsets[index]:offsets[index + 1]], weights[offsets[index]:offsets[index + 1]]) for index in range(count)])
    storage[boundary] = 0
    storages = [storage]
    fluxes = []
    ledgers = []
    domain_ledgers = []
    status = 'completed'
    failure = None
    for step in range(len(local)):
        if cancel is not None and cancel():
            status = 'cancelled'
            break
        with _i113_np.errstate(over='ignore', invalid='ignore'):
            flux = conductance * (stages[-1][edges[:, 0]] - stages[-1][edges[:, 1]])
            net = _i113_np.zeros(count)
            _i113_np.add.at(net, edges[:, 0], -flux)
            _i113_np.add.at(net, edges[:, 1], flux)
            next_storage = storages[-1] + dt_s * (local[step] + net)
            next_storage[boundary] = 0
        reason = None
        if not _i113_np.all(_i113_np.isfinite(flux)) or not _i113_np.all(_i113_np.isfinite(next_storage)):
            reason = 'arithmetic_nonfinite'
        elif _i113_np.any(next_storage[~boundary] < 0):
            reason = 'negative_storage'
        next_stage = _i113_np.full(count, _i113_np.nan)
        if reason is None:
            for index in _i113_np.flatnonzero(~boundary):
                start, stop = offsets[index:index + 2]
                next_stage[index] = _invert(next_storage[index], beds[start:stop], weights[start:stop])
            next_stage[boundary] = tailwater[step + 1]
            if not _i113_np.all(_i113_np.isfinite(next_stage)):
                reason = 'arithmetic_nonfinite'
            elif _i113_np.any(next_stage < min_bed) or _i113_np.any(next_stage - node_bed > max_depth_m):
                reason = 'max_depth_or_boundary_bed'
        if reason is not None:
            status = 'failed'
            failure = {'step_n': step, 'reason': reason}
            break
        rows = []
        for domain in range(len(source['domain_ids'])):
            first, last = source['node_offsets'][domain:domain + 2]
            domain_boundary = boundary[first:last]
            before = float(storages[-1][first:last].sum())
            after = float(next_storage[first:last].sum())
            local_volume = float(dt_s * local[step, first:last][~domain_boundary].sum())
            boundary_volume = float(-dt_s * net[first:last][domain_boundary].sum())
            rows.append((before, local_volume, boundary_volume, after, after - before, after - before - local_volume - boundary_volume))
        domain_ledgers.append(rows)
        ledgers.append(_i113_np.sum(rows, axis=0))
        stages.append(next_stage)
        storages.append(next_storage)
        fluxes.append(flux)
    return {'status': status, 'committed_steps': len(fluxes), 'failed_step': failure, 'stage_m': _i113_np.asarray(stages), 'storage_m3': _i113_np.asarray(storages), 'qedges_m3_s': _i113_np.asarray(fluxes).reshape(-1, len(edges)), 'time_s': _i113_np.arange(len(stages), dtype=float) * dt_s, 'ledger_m3': _i113_np.asarray(ledgers).reshape(-1, 6), 'domain_ledger_m3': _i113_np.asarray(domain_ledgers).reshape(-1, len(source['domain_ids']), 6)}

def prepare_surface_variable_storage(source, *, conductance_m2_s, local_q_m3_s, tailwater_m, dt_s, max_depth_m, resources=StorageResources(), cancel=None):
    """Build vertex-prism storage from a validated saved forest, then advance all domains."""
    if not isinstance(resources, StorageResources) or (cancel is not None and (not callable(cancel))):
        raise ValueError('invalid resources or cancel callback')
    _surface_variable_storage_preflight(source, local_q_m3_s, resources)
    validate_surface_multidomain_dynamic(source)
    conductance, local, tailwater, _, _ = _inputs(source, conductance_m2_s, local_q_m3_s, tailwater_m, dt_s, max_depth_m, resources)
    offsets, beds, weights, owners = _surface_variable_storage_geometry(source)
    knot_offsets, knot_stage, knot_volume = _knots(offsets, beds, weights)
    estimate = _surface_fine_mosaic_size(source) + local.nbytes * 4 + tailwater.nbytes + beds.nbytes * 6
    if estimate > resources.max_retained_bytes or estimate * 2 > resources.max_working_bytes:
        raise ValueError('storage retained/working resource limit')
    result = _advance(source, offsets, beds, weights, conductance, local, tailwater, dt_s, max_depth_m, cancel)
    record = {'algorithm_version': SURFACE_VARIABLE_STORAGE_VERSION, 'geometry': SURFACE_VARIABLE_STORAGE_GEOMETRY, 'source': source, 'resources': vars(resources), 'support_offsets': offsets, 'support_bed_m': beds, 'support_weight_m2': weights, 'support_owner': owners, 'knot_offsets': knot_offsets, 'knot_stage_m': knot_stage, 'knot_volume_m3': knot_volume, 'conductance_m2_s': conductance, 'local_q_m3_s': local, 'tailwater_m': tailwater, 'dt_s': float(dt_s), 'max_depth_m': float(max_depth_m), 'natural_outlets_certified': False, 'full_dynamic_wave_prepared': False, **result}
    sealed = _surface_fine_mosaic_seal(record)
    validate_surface_variable_storage(sealed)
    return sealed

def validate_surface_variable_storage(record):
    """Prove saved support and step equations without preparing or advancing."""
    try:
        resources = StorageResources(**record['resources'])
        _surface_variable_storage_preflight(record['source'], record['local_q_m3_s'], resources)
        retained_bytes = _surface_fine_mosaic_size(record)
        if retained_bytes > resources.max_retained_bytes or retained_bytes * 2 > resources.max_working_bytes:
            raise ValueError('storage byte resource limit')
        required = {'algorithm_version', 'geometry', 'source', 'resources', 'support_offsets', 'support_bed_m', 'support_weight_m2', 'support_owner', 'knot_offsets', 'knot_stage_m', 'knot_volume_m3', 'conductance_m2_s', 'local_q_m3_s', 'tailwater_m', 'dt_s', 'max_depth_m', 'natural_outlets_certified', 'full_dynamic_wave_prepared', 'status', 'committed_steps', 'failed_step', 'stage_m', 'storage_m3', 'qedges_m3_s', 'time_s', 'ledger_m3', 'domain_ledger_m3', 'identity_sha256'}
        if set(record) != required or record['algorithm_version'] != SURFACE_VARIABLE_STORAGE_VERSION or record['geometry'] != SURFACE_VARIABLE_STORAGE_GEOMETRY or (record['natural_outlets_certified'] is not False) or (record['full_dynamic_wave_prepared'] is not False) or (record['identity_sha256'] != _identity({key: value for key, value in record.items() if key != 'identity_sha256'})):
            raise ValueError('storage schema or identity mismatch')
        validate_surface_multidomain_dynamic(record['source'])
        source = record['source']
        nodes = len(source['node_keys'])
        offsets = record['support_offsets']
        beds = record['support_bed_m']
        weights = record['support_weight_m2']
        owners = record['support_owner']
        knot_offsets = record['knot_offsets']
        knot_stages = record['knot_stage_m']
        knot_volumes = record['knot_volume_m3']
        wet_count = sum((len(binding['wet_cell_ids']) for binding in source['bindings']))
        if wet_count > resources.max_wet_cells or nodes > resources.max_nodes or len(source['edges']) > resources.max_edges or (offsets.dtype != _i113_np.dtype('int64')) or (offsets.shape != (nodes + 1,)) or (not _i113_np.array_equal(offsets[[0, -1]], [0, 6 * wet_count])) or (beds.dtype != _i113_np.dtype('float64')) or (beds.shape != (6 * wet_count,)) or (weights.dtype != _i113_np.dtype('float64')) or (weights.shape != beds.shape) or (owners.dtype != _i113_np.dtype('int64')) or (owners.shape != beds.shape) or (knot_offsets.dtype != _i113_np.dtype('int64')) or (knot_offsets.shape != offsets.shape) or (knot_stages.dtype != _i113_np.dtype('float64')) or (knot_volumes.dtype != _i113_np.dtype('float64')) or (knot_stages.ndim != 1) or (knot_volumes.shape != knot_stages.shape) or (knot_offsets[0] != 0) or (knot_offsets[-1] != len(knot_stages)) or _i113_np.any(_i113_np.diff(offsets) <= 0) or _i113_np.any(_i113_np.diff(knot_offsets) <= 0) or (not _i113_np.all(_i113_np.isfinite(beds))) or (not _i113_np.all(_i113_np.isfinite(weights))) or (not _i113_np.all(_i113_np.isfinite(knot_stages))) or (not _i113_np.all(_i113_np.isfinite(knot_volumes))):
            raise ValueError('invalid saved support dimensions')
        position = 0
        for binding in source['bindings']:
            fine = binding['source_mosaic']
            triangle_ids = (2 * binding['wet_cell_ids'][:, None] + _i113_np.arange(2)).ravel()
            triangle_beds = fine['nodes']['h2_m'][fine['triangles'][triangle_ids]].reshape(-1, 6)
            area = fine['grid']['spacing_x_m'] * fine['grid']['spacing_z_m']
            for local_node in range(len(binding['node_flat_ids'])):
                start, stop = offsets[position:position + 2]
                contribution = triangle_beds[binding['wet_cell_owner'] == local_node].ravel()
                if not _i113_np.array_equal(beds[start:stop], contribution) or not _i113_np.all(weights[start:stop] == area / 6) or (not _i113_np.all(owners[start:stop] == position)):
                    raise ValueError('saved support differs from source triangles')
                first, last = knot_offsets[position:position + 2]
                stages = knot_stages[first:last]
                curve = knot_volumes[first:last]
                if not _i113_np.array_equal(stages, _i113_np.unique(contribution)) or curve[0] != 0 or (not _i113_np.all(_i113_np.diff(curve) > 0)) or (not _i113_np.allclose(curve, [volume(stage, beds[start:stop], weights[start:stop]) for stage in stages], rtol=1e-12, atol=1e-12)):
                    raise ValueError('saved knot curve differs from support')
                position += 1
        for name in ('conductance_m2_s', 'local_q_m3_s', 'tailwater_m', 'stage_m', 'storage_m3', 'qedges_m3_s', 'time_s', 'ledger_m3', 'domain_ledger_m3'):
            if record[name].dtype != _i113_np.dtype('float64'):
                raise ValueError('storage array dtype mismatch: ' + name)
        if type(record['committed_steps']) is not int or type(record['dt_s']) is not float or type(record['max_depth_m']) is not float:
            raise ValueError('storage scalar type mismatch')
        conductance, local, tailwater, _, _ = _inputs(record['source'], record['conductance_m2_s'], record['local_q_m3_s'], record['tailwater_m'], record['dt_s'], record['max_depth_m'], resources)
        committed = record['committed_steps']
        if not 0 <= committed <= len(local):
            raise ValueError('invalid committed prefix')
        status = record['status']
        failure = record['failed_step']
        if status not in ('completed', 'cancelled', 'failed') or (status == 'completed' and committed != len(local)) or (status == 'cancelled' and committed >= len(local)) or (status == 'failed' and (committed >= len(local) or not isinstance(failure, _i113_Mapping) or set(failure) != {'step_n', 'reason'} or (type(failure['step_n']) is not int) or (failure['step_n'] != committed) or (failure['reason'] not in ('arithmetic_nonfinite', 'negative_storage', 'max_depth_or_boundary_bed')))) or (status != 'failed' and failure is not None):
            raise ValueError('invalid prefix status')
        boundary = source['dynamic']['inputs']['boundary_mask']
        initial = source['dynamic']['inputs']['initial_stage_m']
        node_bed = source['dynamic']['inputs']['bed_m']
        edges = source['edges']
        dt_s = record['dt_s']
        min_bed = _i113_np.array([beds[offsets[index]:offsets[index + 1]].min() for index in range(nodes)])
        min_area = _i113_np.array([weights[offsets[index]:offsets[index + 1]][beds[offsets[index]:offsets[index + 1]] == min_bed[index]].sum() for index in range(nodes)])
        incident = _i113_np.zeros(nodes)
        _i113_np.add.at(incident, edges[:, 0], conductance)
        _i113_np.add.at(incident, edges[:, 1], conductance)
        if _i113_np.any(dt_s * incident[~boundary] / min_area[~boundary] > 1) or _i113_np.any(initial < min_bed) or _i113_np.any(initial - node_bed > record['max_depth_m']):
            raise ValueError('invalid stability or initial support')
        expected_shapes = {'stage_m': (committed + 1, nodes), 'storage_m3': (committed + 1, nodes), 'qedges_m3_s': (committed, len(edges)), 'time_s': (committed + 1,), 'ledger_m3': (committed, 6), 'domain_ledger_m3': (committed, len(source['domain_ids']), 6)}
        if any((record[name].shape != shape for name, shape in expected_shapes.items())):
            raise ValueError('saved state dimensions')
        if not _i113_np.all(_i113_np.isfinite(record['stage_m'])) or not _i113_np.all(_i113_np.isfinite(record['storage_m3'])) or (not _i113_np.all(_i113_np.isfinite(record['qedges_m3_s']))) or _i113_np.any(record['storage_m3'] < 0) or _i113_np.any(record['stage_m'] < min_bed) or _i113_np.any(record['stage_m'] - node_bed > record['max_depth_m']) or (not _i113_np.array_equal(record['time_s'], _i113_np.arange(committed + 1) * dt_s)) or (not _i113_np.array_equal(record['stage_m'][0], initial)) or (not _i113_np.array_equal(record['stage_m'][:, boundary], tailwater[:committed + 1])) or _i113_np.any(record['storage_m3'][:, boundary] != 0):
            raise ValueError('saved stage/time/boundary mismatch')
        for index in range(nodes):
            start, stop = offsets[index:index + 2]
            for stage, amount in zip(record['stage_m'][:, index], record['storage_m3'][:, index]):
                if not boundary[index] and (not _i113_math.isclose(amount, volume(stage, beds[start:stop], weights[start:stop]), abs_tol=1e-10, rel_tol=1e-12)):
                    raise ValueError('saved stage-volume mismatch')
                if not boundary[index] and amount == 0 and (stage != min_bed[index]):
                    raise ValueError('noncanonical dry stage')
        for step in range(committed + (status == 'failed')):
            stage = record['stage_m'][step]
            flux = conductance * (stage[edges[:, 0]] - stage[edges[:, 1]])
            net = _i113_np.zeros(nodes)
            _i113_np.add.at(net, edges[:, 0], -flux)
            _i113_np.add.at(net, edges[:, 1], flux)
            prediction = record['storage_m3'][step] + dt_s * (local[step] + net)
            prediction[boundary] = 0
            if step == committed:
                reason = 'arithmetic_nonfinite' if not _i113_np.all(_i113_np.isfinite(flux)) or not _i113_np.all(_i113_np.isfinite(prediction)) else None
                if reason is None and _i113_np.any(prediction[~boundary] < 0):
                    reason = 'negative_storage'
                if reason is None:
                    predicted_stage = _i113_np.array([_invert(prediction[index], beds[offsets[index]:offsets[index + 1]], weights[offsets[index]:offsets[index + 1]]) if not boundary[index] else tailwater[step + 1, list(_i113_np.flatnonzero(boundary)).index(index)] for index in range(nodes)])
                    if not _i113_np.all(_i113_np.isfinite(predicted_stage)):
                        reason = 'arithmetic_nonfinite'
                    elif _i113_np.any(predicted_stage < min_bed) or _i113_np.any(predicted_stage - node_bed > record['max_depth_m']):
                        reason = 'max_depth_or_boundary_bed'
                if reason != failure['reason']:
                    raise ValueError('failed-step reason mismatch')
                break
            if not _i113_np.allclose(record['qedges_m3_s'][step], flux, atol=1e-12, rtol=1e-12) or not _i113_np.allclose(record['storage_m3'][step + 1], prediction, atol=1e-10, rtol=1e-12):
                raise ValueError('edge flux or Euler volume mismatch')
            rows = []
            for domain in range(len(source['domain_ids'])):
                first, last = source['node_offsets'][domain:domain + 2]
                domain_boundary = boundary[first:last]
                before = float(record['storage_m3'][step, first:last].sum())
                after = float(prediction[first:last].sum())
                local_volume = float(dt_s * local[step, first:last][~domain_boundary].sum())
                inward = float(-dt_s * net[first:last][domain_boundary].sum())
                rows.append((before, local_volume, inward, after, after - before, after - before - local_volume - inward))
            if not _i113_np.allclose(record['domain_ledger_m3'][step], rows, atol=1e-10, rtol=1e-12) or not _i113_np.allclose(record['ledger_m3'][step], _i113_np.sum(rows, axis=0), atol=1e-10, rtol=1e-12):
                raise ValueError('domain or global ledger mismatch')
            if _i113_np.any(_i113_np.abs(record['domain_ledger_m3'][step, :, 5]) > 1e-09) or abs(record['ledger_m3'][step, 5]) > 1e-09:
                raise ValueError('ledger residual exceeds tolerance')
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError('invalid variable storage record') from error

def query_surface_variable_storage(record, *, state_index=None):
    validate_surface_variable_storage(record)
    if state_index is not None and (type(state_index) is not int or not 0 <= state_index <= record['committed_steps']):
        raise ValueError('state index outside committed prefix')
    selection = slice(None) if state_index is None else state_index
    return _freeze({'node_keys': record['source']['node_keys'], 'stage_m': record['stage_m'][selection], 'storage_m3': record['storage_m3'][selection], 'time_s': record['time_s'][selection], 'status': record['status']})

def save_surface_variable_storage(record, path):
    validate_surface_variable_storage(record)
    destination = _i113_Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = _surface_fine_mosaic_tree(record, arrays)
    manifest = _surface_fine_mosaic_json({'format_version': 1, 'tree': tree, 'tree_sha256': _identity(tree)})
    descriptor, temporary = _i113_tempfile.mkstemp(prefix='.variable-storage-', suffix='.tmp', dir=destination.parent)
    try:
        with _i113_os.fdopen(descriptor, 'w+b') as stream:
            with _i113_zipfile.ZipFile(stream, 'w', compression=_i113_zipfile.ZIP_STORED) as archive:
                archive.writestr('manifest.json', manifest)
                for name, array in arrays.items():
                    with archive.open(name, 'w') as member:
                        _i113_np.lib.format.write_array(member, _i113_np.ascontiguousarray(array), version=(1, 0), allow_pickle=False)
            if stream.tell() > SURFACE_FINE_MOSAIC_MAX_BYTES:
                raise ValueError('storage bundle cap')
            stream.flush()
            _i113_os.fsync(stream.fileno())
        _i113_os.link(temporary, destination)
        return destination
    finally:
        _i113_Path(temporary).unlink(missing_ok=True)

def load_surface_variable_storage(path):
    """Read a bounded, strict archive and prove its saved algebra; no generation."""
    from terrain_pipeline.artifacts.contracts import array_hash as _i105_array_hash
    try:
        with _i113_Path(path).open('rb') as retained, _i113_zipfile.ZipFile(retained) as archive:
            if _i113_os.fstat(retained.fileno()).st_size > SURFACE_FINE_MOSAIC_MAX_BYTES:
                raise ValueError('storage bundle cap')
            _preflight_archive(archive)
            manifest = _i113_json.loads(archive.read('manifest.json'), object_pairs_hook=_surface_fine_mosaic_pairs, parse_constant=_surface_fine_mosaic_constant)
            if set(manifest) != {'format_version', 'tree', 'tree_sha256'} or type(manifest['format_version']) is not int or manifest['format_version'] != 1 or (manifest['tree_sha256'] != _identity(manifest['tree'])):
                raise ValueError('storage manifest mismatch')
            tree = manifest['tree']
            if set(tree) != {'algorithm_version', 'geometry', 'source', 'resources', 'support_offsets', 'support_bed_m', 'support_weight_m2', 'support_owner', 'knot_offsets', 'knot_stage_m', 'knot_volume_m3', 'conductance_m2_s', 'local_q_m3_s', 'tailwater_m', 'dt_s', 'max_depth_m', 'natural_outlets_certified', 'full_dynamic_wave_prepared', 'status', 'committed_steps', 'failed_step', 'stage_m', 'storage_m3', 'qedges_m3_s', 'time_s', 'ledger_m3', 'domain_ledger_m3', 'identity_sha256'}:
                raise ValueError('storage tree schema')
            resources = StorageResources(**tree['resources'])
            archive_bytes = sum((info.file_size for info in archive.infolist()))
            if archive_bytes > resources.max_retained_bytes or archive_bytes * 2 > resources.max_working_bytes:
                raise ValueError('storage archive resource')
            references = {}

            def collect(value):
                if isinstance(value, dict) and '$array' in value:
                    name = value['$array']
                    if set(value) != {'$array', 'shape', 'dtype', 'sha256'} or type(name) is not str or name in references or (type(value['shape']) is not list) or (len(value['shape']) > 5) or any((type(size) is not int or size < 0 for size in value['shape'])) or (type(value['dtype']) is not str) or (type(value['sha256']) is not str):
                        raise ValueError('invalid array reference')
                    references[name] = value
                elif isinstance(value, dict):
                    for child in value.values():
                        collect(child)
                elif isinstance(value, list):
                    for child in value:
                        collect(child)
            collect(tree)
            if set(references) != set(archive.namelist()) - {'manifest.json'}:
                raise ValueError('missing or unused array')
            for name, reference in references.items():
                with archive.open(name) as member:
                    shape, fortran, dtype = _surface_variable_storage_strict_header(member, archive.getinfo(name).file_size)
                    if list(shape) != reference['shape'] or dtype.str != reference['dtype'] or fortran or dtype.hasobject or (dtype.kind not in 'biuf') or (member.tell() + _i113_math.prod(shape) * dtype.itemsize != archive.getinfo(name).file_size):
                        raise ValueError('array header mismatch')

            def decode(value):
                if isinstance(value, dict) and '$array' in value:
                    with archive.open(value['$array']) as member:
                        array = _i113_np.load(member, allow_pickle=False)
                    if _i105_array_hash(array) != value['sha256']:
                        raise ValueError('array hash mismatch')
                    return array
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value
            record = decode(tree)
        validate_surface_variable_storage(record)
        return _freeze(record)
    except (OSError, KeyError, TypeError, IndexError, AttributeError, EOFError, OverflowError, RecursionError, SyntaxError, _i113_json.JSONDecodeError, _i113_zipfile.BadZipFile) as error:
        raise ValueError('invalid variable storage bundle') from error

def _surface_variable_storage_strict_header(member, member_bytes):
    if _i113_np.lib.format.read_magic(member) != (1, 0):
        raise ValueError('NPY v1 required')
    raw_length = member.read(2)
    if len(raw_length) != 2:
        raise ValueError('truncated NPY header')
    length = _i113_struct.unpack('<H', raw_length)[0]
    if length > 8192 or member.tell() + length > member_bytes:
        raise ValueError('NPY header resource limit')
    raw = member.read(length)
    if len(raw) != length or not raw.endswith(b'\n'):
        raise ValueError('invalid NPY header framing')
    expression = _i113_ast.parse(raw.decode('latin1').strip(), mode='eval').body
    if not isinstance(expression, _i113_ast.Dict):
        raise ValueError('NPY header must be a literal dictionary')
    keys = [_i113_ast.literal_eval(key) for key in expression.keys]
    if len(keys) != 3 or set(keys) != {'descr', 'fortran_order', 'shape'}:
        raise ValueError('NPY header keys')
    header = _i113_ast.literal_eval(expression)
    shape = header['shape']
    if type(header['fortran_order']) is not bool or header['fortran_order'] is not False or type(shape) is not tuple or (len(shape) > 5) or any((type(size) is not int or size < 0 for size in shape)) or (type(header['descr']) is not str):
        raise ValueError('NPY header types')
    dtype = _i113_np.dtype(header['descr'])
    if dtype.str != header['descr'] or dtype.hasobject or dtype.kind not in 'biuf' or (_i113_math.prod(shape) * dtype.itemsize > SURFACE_FINE_MOSAIC_MAX_BYTES) or (member.tell() + _i113_math.prod(shape) * dtype.itemsize != member_bytes):
        raise ValueError('NPY dtype/payload mismatch')
    return (shape, False, dtype)
