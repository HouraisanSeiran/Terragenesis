"""Terrain-constrained subgrid river connection to the actual window ocean."""
from dataclasses import replace
import hashlib
import heapq
import json
from pathlib import Path

import numpy as np
from scipy import ndimage
from terrain_pipeline.coastal_marine_product import file_hash
from terrain_pipeline.coastal_marine_sediment import load_state
from terrain_pipeline.coastal_delta_window import migrate_volume

ROOT = Path('.scratch/coast-marine-reorganization-20261102')


def world_to_cell(xz, origin, spacing, shape):
    col, row = np.floor((np.asarray(xz) - origin) / spacing + .5).astype(int)
    if not (0 <= row < shape[0] and 0 <= col < shape[1]):
        raise ValueError('point outside grid')
    return int(row), int(col)


def connected_ocean(bed, valid, seeds):
    wet = valid & (bed < 0)
    labels, _ = ndimage.label(wet)
    ids = np.unique(labels[seeds & wet]); ids = ids[ids != 0]
    return wet & np.isin(labels, ids)


def valley_path(bed, valid, start, targets, max_stage_m, spacing_m, forbidden=None):
    """D4 minimax terrain path, then minimum length, within a finite water head."""
    bed = np.asarray(bed, float); valid = np.asarray(valid, bool)
    allowed = valid & np.isfinite(bed) & (bed < max_stage_m)
    if forbidden is not None:
        allowed &= ~np.asarray(forbidden, bool)
    allowed[start] = valid[start]
    ny, nx = bed.shape
    high = np.full(bed.shape, np.inf); dist = np.full(bed.shape, np.inf)
    prev = np.full(bed.shape, -1, np.int64)
    high[start] = bed[start]; dist[start] = 0.
    queue = [(float(high[start]), 0., *start)]
    end = None
    while queue:
        h, length, r, c = heapq.heappop(queue)
        if h != high[r, c] or length != dist[r, c]:
            continue
        if targets[r, c] and (r, c) != start:
            end = (r, c); break
        for dr, dc in ((-1,0),(0,-1),(0,1),(1,0)):
            rr, cc = r+dr, c+dc
            if not (0 <= rr < ny and 0 <= cc < nx and allowed[rr,cc]):
                continue
            nh, nd = max(h, bed[rr,cc]), length + spacing_m
            if nh < high[rr,cc] or (nh == high[rr,cc] and nd < dist[rr,cc]):
                high[rr,cc], dist[rr,cc], prev[rr,cc] = nh, nd, r*nx+c
                heapq.heappush(queue, (nh, nd, rr, cc))
    if end is None:
        raise ValueError('no path within available head')
    result = [end]
    while result[-1] != start:
        result.append(divmod(int(prev[result[-1]]), nx))
    return np.array(result[::-1], dtype=np.int32)


def manning_capacity(depth, width, slope, roughness):
    depth = np.maximum(np.asarray(depth, float), 0.)
    area = width * depth
    radius = area / (width + 2 * depth)
    return area * radius ** (2/3) * np.sqrt(slope) / roughness


def backwater_profile(bed, spacing_m, width_m, q_m3_s, roughness, sea_level_m=0.):
    """Rectangular subgrid conveyance, steady energy-slope integration upstream.

    The prescribed sea level is at an independent face half a cell downstream;
    each cell centre also satisfies a rectangular critical-depth constraint.
    """
    bed = np.asarray(bed, float); n = len(bed)
    if n == 0 or spacing_m <= 0 or width_m <= 0 or roughness <= 0 or q_m3_s < 0:
        raise ValueError('invalid hydraulic geometry or flow')
    stage = np.empty(n)
    def friction(depth):
        area = width_m * depth
        radius = area / (width_m + 2*depth)
        return (q_m3_s * roughness / (area * radius**(2/3)))**2
    critical = (q_m3_s / width_m / np.sqrt(9.81))**(2/3)
    for i in range(n-1, -1, -1):
        downstream = sea_level_m if i == n-1 else stage[i+1]
        length = spacing_m / 2 if i == n-1 else spacing_m
        low = max(downstream, bed[i] + critical, bed[i] + 1e-8)
        high = max(low + 1., bed[i] + 1.)
        def residual(level):
            return level - downstream - length * friction(level-bed[i])
        if residual(low) >= 0:
            stage[i] = low
            continue
        while residual(high) < 0:
            high = bed[i] + 2 * (high-bed[i])
        for _ in range(55):
            mid = (low + high)/2
            if residual(mid) < 0: low = mid
            else: high = mid
        stage[i] = high
    return stage


def partition_subgrid_stocks(state, routes):
    """Partition each solid stock once by historical fine-owner plan area.

    The returned owners sum exactly to the unchanged MarineState. Geometric
    baselines make the stored owner beds and sediment stock mutually consistent.
    """
    fraction = np.asarray(routes['fine_owner_area_fraction'], float)
    fine_bed = np.asarray(routes['fine_owner_bed_m'], float)
    if fraction.shape != state.bed_m.shape or np.any((fraction < 0) | (fraction > 1)):
        raise ValueError('invalid owner fraction')
    if np.any((fraction > 0) & (~state.valid_mask | ~np.isfinite(fine_bed))):
        raise ValueError('fine owner outside valid source')
    coarse = state.bed_m
    outer = coarse.copy()
    result = {'fine_area_fraction': fraction.copy(), 'fine_bed_m': fine_bed.copy(),
              'outer_bed_m': outer,
              'geometry_difference_bulk_m3': (fraction*fine_bed+(1-fraction)*outer-coarse)*state.spacing_m**2}
    area = state.spacing_m**2
    for name in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3'):
        total = getattr(state, name)
        result['fine_'+name] = total*fraction
        result['outer_'+name] = total-result['fine_'+name]
    solid_thickness = state.bed_solid_m3 / (area * (1-state.porosity))
    result['fine_base_bed_m'] = fine_bed-solid_thickness
    result['outer_base_bed_m'] = outer-solid_thickness
    return result


def fine_backwater(section_bed, offsets, distance, downstream_stage, q_m3_s, roughness):
    """Steady backwater over saved transverse profiles, upstream from new port stage."""
    result = np.empty(len(distance)); result[-1] = downstream_stage
    def friction(level, bed):
        depth = np.maximum(level - bed, 0.)
        area = np.trapezoid(depth, offsets)
        perimeter = np.sum(np.hypot(np.diff(offsets), np.diff(bed)) * ((depth[:-1] > 0) | (depth[1:] > 0)))
        if area <= 0 or perimeter <= 0:
            return np.inf
        return (q_m3_s * roughness / (area * (area / perimeter)**(2/3)))**2
    for i in range(len(distance)-2, -1, -1):
        bed = section_bed[i]
        lo = max(result[i+1], float(np.min(bed)) + 1e-8)
        hi = max(lo+1, float(np.max(bed))+1)
        def residual(level):
            return level-result[i+1]-(distance[i+1]-distance[i])*friction(level,bed)
        while residual(hi) < 0:
            hi += max(1., hi-np.min(bed))
        for _ in range(48):
            mid=(lo+hi)/2
            if residual(mid)<0: lo=mid
            else: hi=mid
        result[i]=hi
    return result


def prepare_routes(state, source_ocean, fine, fine_metadata, *, q_m3_s=150., sea_level_m=0., roughness=.035):
    """Return unchanged stock owner, terrain-following routes, and explicit basis."""
    origin = np.asarray(state.origin_xz_m); spacing = state.spacing_m
    width = float(fine_metadata['width_m'])
    distance = fine['distance_m']; idx = int(np.argmin(np.abs(distance - (distance[-1]-600.))))
    control_xz = fine['path_xz_m'][idx]; control_stage = float(fine['stage_m'][idx])
    control_bed = float(fine['target_bed_m'][idx]); port = fine['path_xz_m'][-1]
    start = world_to_cell(port, origin, spacing, state.base_bed_m.shape)
    bed = state.bed_m
    ocean = connected_ocean(bed-sea_level_m, state.valid_mask, state.ocean_seed_mask) & source_ocean
    if not ocean.any(): raise ValueError('no connected external ocean')
    # The old narrow endpoint occupies a subcell; it does not lower the coarse cell.
    fine_spacing = float(fine['spacing_m'])
    fine_origin = tuple(fine['origin_xz_m'])
    port_row = (port[1]-fine_origin[1])/fine_spacing
    port_col = (port[0]-fine_origin[0])/fine_spacing
    fine_port_bed = float(ndimage.map_coordinates(fine['bed_m'], [[port_row], [port_col]], order=1, mode='nearest')[0])
    if not np.isclose(fine_port_bed, fine_metadata['port_bed_m'], atol=1e-5):
        raise ValueError('fine port bed does not match declared geometry')
    search_bed = bed.copy(); search_bed[start] = fine_port_bed
    main = valley_path(search_bed, state.valid_mask, start, ocean, control_stage, spacing)
    rb = bed[main[:,0],main[:,1]].copy(); rb[0] = fine_port_bed
    fine_start = int(np.searchsorted(fine['section_distance_m'], distance[idx], side='left'))
    fine_distance = fine['section_distance_m'][fine_start:]
    fine_beds = fine['section_bed_m'][fine_start:]
    fine_xz = np.column_stack([np.interp(fine_distance, distance, fine['path_xz_m'][:,axis]) for axis in range(2)])
    control_stage = float(np.interp(fine_distance[0], distance, fine['stage_m']))
    control_bed = float(np.min(fine_beds[0]))
    control_xz = fine_xz[0]
    def solve_flow(flow):
        stage = backwater_profile(rb, spacing, width, flow, roughness, sea_level_m)
        fine_stage = fine_backwater(fine_beds, fine['section_offset_m'], fine_distance, stage[0], flow, roughness)
        return stage, fine_stage
    trial_stage, trial_fine = solve_flow(q_m3_s)
    accepted = q_m3_s
    if trial_fine[0] > control_stage:
        lo, hi = 0., q_m3_s
        zero_stage, zero_fine = solve_flow(0.)
        if zero_fine[0] > control_stage:
            accepted = 0.
            stages, fine_stages = zero_stage, zero_fine
        else:
            for _ in range(30):
                mid = (lo+hi)/2
                if solve_flow(mid)[1][0] <= control_stage:
                    lo = mid
                else:
                    hi = mid
            accepted = lo
            stages, fine_stages = solve_flow(accepted)
    else:
        stages, fine_stages = trial_stage, trial_fine
    fine_cells = np.array([world_to_cell(xz, origin, spacing, bed.shape) for xz in fine_xz], dtype=np.int32)
    all_fine_distance = fine['section_distance_m']
    all_fine_xz = np.column_stack([np.interp(all_fine_distance, distance, fine['path_xz_m'][:,axis]) for axis in range(2)])
    all_fine_cells = np.full((len(all_fine_xz), 2), -1, np.int32)
    for j, xz in enumerate(all_fine_xz):
        try:
            all_fine_cells[j] = world_to_cell(xz, origin, spacing, bed.shape)
        except ValueError:
            pass
    fine_cut = np.asarray(fine['cut_m'], dtype=float)
    cut_bulk = migrate_volume(fine_cut * fine_spacing**2, fine_origin, fine_spacing,
                              bed.shape, tuple(origin), spacing)
    cut_area = migrate_volume((fine_cut > 0).astype(float) * fine_spacing**2, fine_origin, fine_spacing,
                              bed.shape, tuple(origin), spacing)
    fine_bed_grid = np.asarray(fine['bed_m'], dtype=float)
    fine_bed_sum = migrate_volume(np.where(fine_cut > 0, fine_bed_grid, 0.) * fine_spacing**2,
                                   fine_origin, fine_spacing, bed.shape, tuple(origin), spacing)
    fine_owner_fraction = np.clip(cut_area / spacing**2, 0., 1.)
    fine_owner_bed = np.divide(fine_bed_sum, cut_area, out=bed.copy(), where=cut_area > 0)
    fine_digest = hashlib.sha256()
    for key in ('origin_xz_m', 'spacing_m', 'bed_m', 'cut_m'):
        fine_digest.update(np.ascontiguousarray(fine[key]).tobytes())
    branches = []
    # Candidates are disjoint after their shared fork and reach a distinct coast.
    for fraction in (.3, .6):
        fork = max(1, min(len(main)-2, int(len(main)*fraction)))
        blocked = np.zeros(bed.shape, bool); blocked[main[:,0],main[:,1]] = True
        for b in branches: blocked[b[1:,0],b[1:,1]] = True
        target = ocean.copy(); target[main[-1,0],main[-1,1]] = False
        try:
            b = valley_path(bed, state.valid_mask, tuple(main[fork]), target, control_stage, spacing, blocked)
        except ValueError:
            continue
        branches.append(b)
    offsets = np.r_[0, np.cumsum([len(b) for b in branches])].astype(np.int32)
    packed = np.concatenate(branches) if branches else np.empty((0,2),np.int32)
    # Ground is the only known extension section; no excavation is inferred.
    # Rectangular effective subgrid prism is a hydraulic approximation, not a measured cross section.
    bank = bed[main[:,0],main[:,1]].copy()
    slopes = np.maximum((stages[:-1]-stages[1:])/spacing, 0.)
    capacity = np.r_[manning_capacity(stages[:-1]-rb[:-1],width,slopes,roughness),
                     manning_capacity(max(stages[-1]-rb[-1],0),width,max(0., (stages[-1]-sea_level_m)/(spacing/2)),roughness)]
    routes = {'main_cells_zx':main, 'branch_cells_zx':packed, 'branch_offsets':offsets,
              'section_bed_m':rb, 'section_bank_m':bank, 'section_width_m':np.full(len(main),width),
              'section_stage_m':stages, 'section_capacity_m3_s':capacity,
              'section_area_fraction':np.full(len(main),min(1.,width/spacing)),
              'section_distance_m':np.arange(len(main))*spacing,
              'fine_section_distance_m':fine['section_distance_m'], 'fine_section_offset_m':fine['section_offset_m'],
              'fine_section_bed_m':fine['section_bed_m'], 'junction_fine_cells_zx':fine_cells,
              'fine_section_world_xz_m':all_fine_xz, 'fine_section_cells_zx':all_fine_cells,
              'junction_fine_distance_m':fine_distance, 'junction_fine_stage_m':fine_stages,
              'historical_cut_bulk_m3':cut_bulk, 'historical_cut_area_fraction':cut_area / spacing**2,
              'fine_owner_area_fraction':fine_owner_fraction, 'fine_owner_bed_m':fine_owner_bed,
              'trial_requested_stage_m':trial_stage, 'trial_requested_fine_stage_m':trial_fine}
    ownership = partition_subgrid_stocks(state, routes)
    routes.update({'owner_'+key:value for key,value in ownership.items()})
    meta = {'control':{'fine_section_index':fine_start,'world_xz_m':control_xz.tolist(),'distance_upstream_of_port_m':float(distance[-1]-fine_distance[0]),'old_scenario_stage_m':control_stage,'fine_bed_m':control_bed, 'note':'old imposed scenario stage, not observation; downstream backwater must be recomputed'},
            'port_world_xz_m':port.tolist(),'port_cell_zx':list(start),'sea_cell_zx':main[-1].tolist(),
            'fine_port_bed_m':fine_port_bed, 'coarse_port_bed_m':float(bed[start]),
            'port_fine_owner_area_fraction':float(fine_owner_fraction[start]),
            'sea_world_xz_m':(origin+main[-1,::-1]*spacing).tolist(),'sea_level_m':sea_level_m,
            'q_m3_s':q_m3_s,'solid_rate_m3_s':.08,'width_m':width,'roughness':roughness,
            'main_length_m':float((len(main)-1)*spacing),'candidate_count':len(branches),
            'extension_port_stage_m':float(stages[0]),'control_stage_m':control_stage,
            'head_feasible':bool(trial_fine[0] <= control_stage),'recomputed_control_stage_m':float(fine_stages[0]),
            'recomputed_control_world_xz_m':fine_xz[0].tolist(),
            'minimum_capacity_m3_s':float(capacity.min()), 'q150_all_sections_feasible':bool(accepted >= q_m3_s*(1-1e-8)),
            'requested_q_m3_s':q_m3_s, 'accepted_q_m3_s':float(accepted), 'pending_q_m3_s':float(q_m3_s-accepted),
            'requested_control_stage_m':float(trial_fine[0]), 'mouth_capacity_m3_s':float(capacity[-1]),
            'exchange_face_stage_m':sea_level_m, 'exchange_face_distance_m':spacing/2,
            'mouth_capacity_note':'Manning capacity uses actual mouth-centre minus external face stage over half cell; critical depth is a lower bound',
            'excavation':{'new_bulk_m3':0.,'new_solid_m3':0.,'new_rock_m3':0.,'destination':'none; no new excavation',
                          'historical_fine_bulk_m3':fine_metadata['removed_bulk_m3'],'historical_fine_destination':'unknown; not new supply'},
            'section_note':'extension is effective rectangular subgrid prism from coarse cell-centre beds; no measured 100m cross sections, no coarse solid modification; floodplain capacity not resolved',
            'fine_section_note':'saved 15m fine bed sections are historical geometry, not excavated again; old stage is not a new backwater solution'}
    meta['excavation']['historical_cut_inside_window_bulk_m3'] = float(cut_bulk.sum())
    meta['excavation']['historical_cut_outside_window_bulk_m3'] = float((fine_cut * fine_spacing**2).sum() - cut_bulk.sum())
    meta['fine_geometry_arrays_sha256'] = fine_digest.hexdigest()
    meta['owner_geometry_difference_bulk_m3'] = float(ownership['geometry_difference_bulk_m3'].sum())
    meta['owner_geometry_difference_abs_bulk_m3'] = float(np.abs(ownership['geometry_difference_bulk_m3']).sum())
    meta['inventory_mapping_note'] = ('Cut-footprint area uniquely owns its fraction of each existing coarse stock; outer owner retains the remainder. '
        'Fine-owner bed is the area-weighted saved fine geometry; outer bed is unchanged coarse bed. '
        'The geometric datum difference is explicitly recorded, with unknown historical material and destination; it is not new supply or erosion.')
    return replace(state), routes, meta


def save_routes(prefix, routes, metadata):
    prefix = Path(prefix)
    np.savez_compressed(str(prefix)+'.npz', **routes)
    metadata = dict(metadata, data_sha256=file_hash(str(prefix)+'.npz'))
    Path(str(prefix)+'.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')


def load_routes(prefix):
    prefix = Path(prefix); meta=json.loads(Path(str(prefix)+'.json').read_text(encoding='utf-8-sig'))
    if file_hash(str(prefix)+'.npz') != meta['data_sha256']: raise ValueError('route hash mismatch')
    with np.load(str(prefix)+'.npz',allow_pickle=False) as data:
        return {k:data[k] for k in data.files}, meta
