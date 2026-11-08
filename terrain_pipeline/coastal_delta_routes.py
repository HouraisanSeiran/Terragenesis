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


def irregular_valley_path(bed, valid, start, target, max_stage_m, spacing_m, *,
                          origin_xz_m=(0., 0.), world_seed=20261020, forbidden=None,
                          target_mask=None, start_xz_m=None, mesh=None,
                          initial_direction_xz=None, direction_weight=0., direction_decay_m=None,
                          ownership_penalty=None, max_turn_deg=None,
                          start_directions_xz=(), end_directions_xz=(), turn_penalty_k=1.):
    """Return account cells and metric coordinates for a terrain-constrained route.

    A target mask selects the cheapest reachable legal target; otherwise target
    is the fixed endpoint. An exact start must belong to the start account cell.
    A supplied mesh must come from the same shape, metric frame and seed.
    Optional initial_direction_xz is a dimensionless XZ vector. Its nonnegative
    dimensionless weight multiplies edge length and (1-cosine); the influence
    decays exponentially with straight-line distance from the start, in metres.
    It is a soft cost, not a constraint on legal terrain or headings.
    ownership_penalty is an optional dimensionless per-cell additive cost; it
    favours available footprint without changing the bed or forbidding cells.
    max_turn_deg enables a hard metric heading limit, including all supplied
    physical incoming directions at the start and outgoing directions at target.
    """
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.channel_geometry import FrozenPathConfig, _terrain_weighted_path

    bed = np.asarray(bed, float)
    valid = np.asarray(valid, bool)
    origin = np.asarray(origin_xz_m, float)
    if (bed.ndim != 2 or valid.shape != bed.shape or not np.isfinite(max_stage_m)
            or not np.isfinite(spacing_m) or spacing_m <= 0
            or origin.shape != (2,) or not np.isfinite(origin).all()):
        raise ValueError('invalid irregular route source')
    def endpoint(cell):
        try:
            cell = tuple(cell)
            if (len(cell) != 2 or any(int(v) != v for v in cell) or
                    not (0 <= cell[0] < bed.shape[0] and 0 <= cell[1] < bed.shape[1])):
                raise ValueError
            return tuple(map(int, cell))
        except (TypeError, ValueError, OverflowError):
            raise ValueError('invalid endpoint') from None
    start = endpoint(start)
    allowed = valid & np.isfinite(bed) & (bed < max_stage_m)
    if forbidden is not None:
        forbidden = np.asarray(forbidden, bool)
        if forbidden.shape != bed.shape:
            raise ValueError('invalid forbidden mask')
        allowed &= ~forbidden
    if not allowed[start]:
        raise ValueError('endpoint outside legal terrain')
    if target_mask is None:
        target = endpoint(target)
        if not allowed[target]:
            raise ValueError('endpoint outside legal terrain')
        candidates = np.array([np.ravel_multi_index(target, bed.shape)])
    else:
        targets = np.asarray(target_mask, bool)
        if targets.shape != bed.shape:
            raise ValueError('invalid target mask')
        candidates = np.flatnonzero(targets & allowed)
        if not len(candidates):
            raise ValueError('no irregular path within available head')
    if mesh is None:
        mesh = grid_mesh(bed.shape, x0_m=origin[0], z0_m=origin[1],
                         dx_m=spacing_m, world_seed=world_seed)
    elif mesh.shape != bed.shape:
        raise ValueError('mesh shape does not match terrain')
    points = np.column_stack((mesh.node_x_m, mesh.node_z_m))
    first = np.ravel_multi_index(start, bed.shape)
    if start_xz_m is not None:
        exact = np.asarray(start_xz_m, float)
        if (exact.shape != (2,) or not np.isfinite(exact).all() or
                not np.array_equal(np.floor((exact-origin)/spacing_m+.5).astype(int), start[::-1])):
            raise ValueError('exact start outside start cell')
        points[first] = exact
    displacement = None
    if ownership_penalty is not None:
        penalty = np.asarray(ownership_penalty, float)
        if penalty.shape != bed.shape or not np.isfinite(penalty).all() or np.any(penalty < 0):
            raise ValueError('invalid ownership penalty')
        displacement = np.sqrt(penalty / FrozenPathConfig().displacement_cost_per_m2)
    selected = _terrain_weighted_path(mesh, bed, allowed, first, candidates,
        config=FrozenPathConfig(), displacement=displacement, actual_segment_frame=(origin, spacing_m), points=points,
        initial_direction_xz=initial_direction_xz, direction_weight=direction_weight,
        direction_decay_m=direction_decay_m, max_turn_deg=max_turn_deg,
        start_directions_xz=start_directions_xz, end_directions_xz=end_directions_xz,
        turn_penalty_k=turn_penalty_k)
    if selected is None:
        raise ValueError('no irregular path within available head')
    cells = np.column_stack(np.unravel_index(selected, bed.shape)).astype(np.int32)
    return cells, points[selected].copy()


def manning_capacity(depth, width, slope, roughness):
    depth = np.maximum(np.asarray(depth, float), 0.)
    area = width * depth
    radius = area / (width + 2 * depth)
    return area * radius ** (2/3) * np.sqrt(slope) / roughness


def backwater_profile(bed, spacing_m, width_m, q_m3_s, roughness, sea_level_m=0., *, segment_lengths_m=None):
    """Rectangular subgrid conveyance, steady energy-slope integration upstream.

    The prescribed sea level is at an independent face half a cell downstream;
    each cell centre also satisfies a rectangular critical-depth constraint.
    """
    bed = np.asarray(bed, float); n = len(bed)
    if n == 0 or spacing_m <= 0 or width_m <= 0 or roughness <= 0 or q_m3_s < 0:
        raise ValueError('invalid hydraulic geometry or flow')
    lengths = None if segment_lengths_m is None else np.asarray(segment_lengths_m, float)
    if lengths is not None and (lengths.shape != (n-1,) or not np.isfinite(lengths).all() or np.any(lengths <= 0)):
        raise ValueError('invalid segment lengths')
    stage = np.empty(n)
    def friction(depth):
        area = width_m * depth
        radius = area / (width_m + 2*depth)
        return (q_m3_s * roughness / (area * radius**(2/3)))**2
    critical = (q_m3_s / width_m / np.sqrt(9.81))**(2/3)
    for i in range(n-1, -1, -1):
        downstream = sea_level_m if i == n-1 else stage[i+1]
        length = spacing_m / 2 if i == n-1 else (spacing_m if lengths is None else lengths[i])
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


def prepare_routes(state, source_ocean, fine, fine_metadata, *, q_m3_s=150., sea_level_m=0., roughness=.035, irregular=False, world_seed=20260903):
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
    if irregular:
        main, main_xy = irregular_valley_path(search_bed, state.valid_mask, start, None, control_stage, spacing,
            origin_xz_m=origin, world_seed=world_seed, target_mask=ocean, start_xz_m=port)
        lengths = np.linalg.norm(np.diff(main_xy, axis=0), axis=1)
    else:
        main = valley_path(search_bed, state.valid_mask, start, ocean, control_stage, spacing)
        lengths = np.full(len(main)-1, spacing)
    rb = bed[main[:,0],main[:,1]].copy(); rb[0] = fine_port_bed
    fine_start = int(np.searchsorted(fine['section_distance_m'], distance[idx], side='left'))
    fine_distance = fine['section_distance_m'][fine_start:]
    fine_beds = fine['section_bed_m'][fine_start:]
    fine_xz = np.column_stack([np.interp(fine_distance, distance, fine['path_xz_m'][:,axis]) for axis in range(2)])
    control_stage = float(np.interp(fine_distance[0], distance, fine['stage_m']))
    control_bed = float(np.min(fine_beds[0]))
    control_xz = fine_xz[0]
    def solve_flow(flow):
        stage = backwater_profile(rb, spacing, width, flow, roughness, sea_level_m, segment_lengths_m=lengths if irregular else None)
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
    for fraction in (() if irregular else (.3, .6)):
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
    if irregular:
        bank = np.array([max([float(bed[r, c])] + [float(bed[rr, cc]) for rr, cc in
            ((r-1,c),(r+1,c),(r,c-1),(r,c+1)) if 0 <= rr < bed.shape[0] and
            0 <= cc < bed.shape[1] and state.valid_mask[rr, cc]]) for r, c in main])
    slopes = np.maximum((stages[:-1]-stages[1:])/lengths, 0.)
    capacity = np.r_[manning_capacity(stages[:-1]-rb[:-1],width,slopes,roughness),
                     manning_capacity(max(stages[-1]-rb[-1],0),width,max(0., (stages[-1]-sea_level_m)/(spacing/2)),roughness)]
    routes = {'main_cells_zx':main, 'branch_cells_zx':packed, 'branch_offsets':offsets,
              'section_bed_m':rb, 'section_bank_m':bank, 'section_width_m':np.full(len(main),width),
              'section_stage_m':stages, 'section_capacity_m3_s':capacity,
              'section_area_fraction':np.full(len(main),min(1.,width/spacing)),
              'section_distance_m':np.r_[0., np.cumsum(lengths)],
              'fine_section_distance_m':fine['section_distance_m'], 'fine_section_offset_m':fine['section_offset_m'],
              'fine_section_bed_m':fine['section_bed_m'], 'junction_fine_cells_zx':fine_cells,
              'fine_section_world_xz_m':all_fine_xz, 'fine_section_cells_zx':all_fine_cells,
              'junction_fine_distance_m':fine_distance, 'junction_fine_stage_m':fine_stages,
              'historical_cut_bulk_m3':cut_bulk, 'historical_cut_area_fraction':cut_area / spacing**2,
              'fine_owner_area_fraction':fine_owner_fraction, 'fine_owner_bed_m':fine_owner_bed,
              'trial_requested_stage_m':trial_stage, 'trial_requested_fine_stage_m':trial_fine}
    if irregular:
        routes['main_points_xz'] = main_xy
        routes['branch_points_xz'] = np.empty((0, 2))
    ownership = partition_subgrid_stocks(state, routes)
    routes.update({'owner_'+key:value for key,value in ownership.items()})
    meta = {'control':{'fine_section_index':fine_start,'world_xz_m':control_xz.tolist(),'distance_upstream_of_port_m':float(distance[-1]-fine_distance[0]),'old_scenario_stage_m':control_stage,'fine_bed_m':control_bed, 'note':'old imposed scenario stage, not observation; downstream backwater must be recomputed'},
            'port_world_xz_m':port.tolist(),'port_cell_zx':list(start),'sea_cell_zx':main[-1].tolist(),
            'fine_port_bed_m':fine_port_bed, 'coarse_port_bed_m':float(bed[start]),
            'port_fine_owner_area_fraction':float(fine_owner_fraction[start]),
            'sea_world_xz_m':(origin+main[-1,::-1]*spacing).tolist(),'sea_level_m':sea_level_m,
            'q_m3_s':q_m3_s,'solid_rate_m3_s':.08,'width_m':width,'roughness':roughness,
            'main_length_m':float(lengths.sum()),'candidate_count':len(branches),
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
    if irregular:
        meta.update(source_identity=state.source_identity, route_geometry_algorithm='frozen-irregular-valley-v1',
                    route_geometry_seed=int(world_seed), sea_world_xz_m=main_xy[-1].tolist())
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

def build_route_geometry(state, paths, points, algorithm, seed):
    """Validate account coordinates and retain candidate and active edges."""
    if not isinstance(algorithm, str) or not algorithm or seed is None or len(paths) != len(points):
        raise ValueError('irregular geometry requires algorithm and seed')
    nodes, edges = {}, set()
    shape = state.base_bed_m.shape
    for path, xy in zip(paths, points):
        xy = np.asarray(xy, float)
        if xy.shape != (len(path), 2) or not np.isfinite(xy).all() or len(path) < 2:
            raise ValueError('invalid route coordinates')
        cells = [tuple(map(int, c)) for c in path]
        if len(set(cells)) != len(cells):
            raise ValueError('repeated route account')
        for cell, point in zip(cells, xy):
            if (not (0 <= cell[0] < shape[0] and 0 <= cell[1] < shape[1])
                    or not state.valid_mask[cell] or world_to_cell(point, state.origin_xz_m, state.spacing_m, shape) != cell):
                raise ValueError('coordinate outside account cell')
            if cell in nodes and not np.allclose(nodes[cell], point, rtol=0, atol=1e-9):
                raise ValueError('conflicting account coordinates')
            nodes[cell] = point.tolist()
        for a, b in zip(cells, cells[1:]):
            from terrain_pipeline.channel_geometry import _segment_owner_samples
            segment = np.asarray([nodes[a], nodes[b]])
            if np.linalg.norm(segment[0]-segment[1]) <= 0:
                raise ValueError('invalid irregular edge')
            for point in _segment_owner_samples(segment, np.asarray(state.origin_xz_m), state.spacing_m):
                cell = world_to_cell(point, state.origin_xz_m, state.spacing_m, shape)
                if not state.valid_mask[cell]:
                    raise ValueError('irregular edge crosses invalid account')
            edges.add((a, b))
    return {'algorithm': algorithm, 'seed': int(seed),
            'nodes': [[*c, *nodes[c]] for c in sorted(nodes)],
            'edges': [[*a, *b] for a, b in sorted(edges)],
            'exchange_face_distance_m': state.spacing_m / 2}


def route_metrics(progress, spacing):
    """Build transient lengths for the current topology, once per calculation."""
    geometry = progress.get('route_geometry')
    if geometry is None:
        return None
    nodes = {tuple(row[:2]): np.asarray(row[2:], float) for row in geometry['nodes']}
    lengths = {}
    for row in geometry['edges']:
        a, b = tuple(row[:2]), tuple(row[2:])
        if a not in nodes or b not in nodes:
            raise ValueError('missing route geometry edge')
        length = float(np.linalg.norm(nodes[a]-nodes[b]))
        if not np.isfinite(length) or length <= 0:
            raise ValueError('invalid route geometry edge length')
        lengths[a, b] = length
    edges = {(tuple(a), tuple(b)) for route in progress['routes'] for a, b in zip(route, route[1:])}
    controls = {}
    for a, b in edges:
        if (a, b) not in lengths:
            raise ValueError('missing route geometry edge')
        half = lengths[a, b] / 2
        controls[a] = controls.get(a, 0.) + half
        controls[b] = controls.get(b, 0.) + half
    for cell in {tuple(route[-1]) for route in progress['routes']}:
        controls[cell] = controls.get(cell, 0.) + float(geometry['exchange_face_distance_m'])
    return lengths, controls


def edge_length(progress, a, b, spacing, metrics=None):
    if 'route_geometry' not in progress:
        return spacing
    if metrics is None:
        metrics = route_metrics(progress, spacing)
    try:
        return metrics[0][tuple(a), tuple(b)]
    except KeyError:
        raise ValueError('missing route geometry edge') from None


def node_control_length(progress, cell, spacing, metrics=None):
    if 'route_geometry' not in progress:
        return spacing
    if metrics is None:
        metrics = route_metrics(progress, spacing)
    length = metrics[1].get(tuple(cell), 0.)
    if not np.isfinite(length) or length <= 0:
        raise ValueError('invalid node control length')
    return length


def channel_area(progress, cell, width, spacing, metrics=None):
    return min(width * node_control_length(progress, cell, spacing, metrics), spacing ** 2)
