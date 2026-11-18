"""Connect explicitly chosen coastal outlets using irregular valley geometry."""
from dataclasses import replace
import numpy as np

from .coastal_delta_branching import _record
from .coastal_delta_evolution import initialize
from .coastal_delta_hydraulics import solve
from .coastal_delta_routes import build_route_geometry, irregular_valley_path
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.channel_geometry import formative_section


def _footprint(state, domain, paths, points, widths, targets, subdivisions):
    """Rasterise the union of variable-width segments with unique sample owners."""
    cells = sorted(widths)
    indices = {cell: i for i, cell in enumerate(cells)}
    point_array = np.concatenate([np.asarray(p) for p in points])
    spacing = state.spacing_m
    origin = np.asarray(state.origin_xz_m)
    radius = max(widths.values()) / 2 + spacing
    lo = np.floor((point_array.min(axis=0)-radius-origin)/spacing).astype(int)
    hi = np.ceil((point_array.max(axis=0)+radius-origin)/spacing).astype(int)
    c0, r0 = max(0, lo[0]), max(0, lo[1])
    c1, r1 = min(domain.shape[1], hi[0]+1), min(domain.shape[0], hi[1]+1)
    shape = ((r1-r0)*subdivisions, (c1-c0)*subdivisions)
    owner = np.full(shape, -1, np.int32)
    score = np.full(shape, np.inf, np.float32)
    step = spacing / subdivisions
    x0 = origin[0] + (c0-.5)*spacing + step/2
    z0 = origin[1] + (r0-.5)*spacing + step/2
    seen = set()
    for path, xy in zip(paths, points):
        for a, b, pa, pb in zip(path, path[1:], xy, xy[1:]):
            a, b = tuple(a), tuple(b)
            if (a, b) in seen:
                continue
            seen.add((a, b))
            pa, pb = np.asarray(pa), np.asarray(pb)
            reach = max(widths[a], widths[b])/2
            left = max(0, int(np.floor((min(pa[0], pb[0])-reach-x0)/step)))
            right = min(shape[1], int(np.ceil((max(pa[0], pb[0])+reach-x0)/step))+1)
            top = max(0, int(np.floor((min(pa[1], pb[1])-reach-z0)/step)))
            bottom = min(shape[0], int(np.ceil((max(pa[1], pb[1])+reach-z0)/step))+1)
            if right <= left or bottom <= top:
                continue
            x = x0 + np.arange(left, right)[None, :]*step
            z = z0 + np.arange(top, bottom)[:, None]*step
            v = pb-pa
            t = np.clip(((x-pa[0])*v[0] + (z-pa[1])*v[1])/np.dot(v, v), 0., 1.)
            d = np.hypot(x-(pa[0]+t*v[0]), z-(pa[1]+t*v[1]))
            half_width = (widths[a]*(1-t)+widths[b]*t)/2
            ratio = d/half_width
            current = score[top:bottom, left:right]
            take = (ratio <= 1) & (ratio < current)
            current[take] = ratio[take]
            selected = np.where(t < .5, indices[a], indices[b])
            owner[top:bottom, left:right][take] = selected[take]
    rr, cc = np.nonzero(owner >= 0)
    rows = r0 + rr//subdivisions
    cols = c0 + cc//subdivisions
    good = domain[rows, cols]
    rows, cols, ids = rows[good], cols[good], owner[rr[good], cc[good]]
    count = np.bincount(rows*domain.shape[1]+cols, minlength=domain.size).reshape(domain.shape)
    fraction = count.astype(float) / subdivisions**2
    area = step**2 * (1-state.porosity[rows, cols])
    target = np.asarray([targets[cell] for cell in cells])[ids]
    before = state.bed_m[rows, cols]
    after = np.maximum(state.base_bed_m[rows, cols], np.minimum(before, target))
    cut_sample = (before-after)*area
    cuts = np.bincount(rows*domain.shape[1]+cols, weights=cut_sample, minlength=domain.size).reshape(domain.shape)
    node_count = np.bincount(ids, minlength=len(cells))
    node_bed = np.bincount(ids, weights=after, minlength=len(cells))
    node_bank = np.bincount(ids, weights=before, minlength=len(cells))
    packed = ids.astype(np.int64)*domain.size + rows*domain.shape[1]+cols
    keys, inverse, sample_counts = np.unique(packed, return_inverse=True, return_counts=True)
    group_cuts = np.bincount(inverse, weights=cut_sample)
    footprint = [[] for _ in cells]
    for key, count_value, cut_value in zip(keys, sample_counts, group_cuts):
        node_id, grid_id = divmod(int(key), domain.size)
        row, col = divmod(grid_id, domain.shape[1])
        part = float(count_value / subdivisions**2)
        cut_value = min(float(cut_value), float(state.bed_solid_m3[row, col]*part))
        footprint[node_id].append([row, col, part, cut_value])
    return cells, fraction, cuts, node_count, node_bed, node_bank, footprint


def construct(state, *, domain, inlet_zx, main_outlet_zx, forks, hydraulic_config,
              input_id, discharge_m3_s, solid_rate_m3_s, depth_m=3.,
              width_m=500., reference_q_m3_s=10000., max_width_m=3000.,
              bed_resistance=.5, bank_resistance=.5, fracture=0., bank_cohesion=.5,
              route_shares=None, subdivisions=8, bed_slope_m_per_m=.00002,
              sea_level_m=0., world_seed=20261020, fork_direction_weight=0.,
              fork_direction_decay_m=5000., prepared_paths=None):
    """Create a tree; forks are (parent route index, parent cell index, outlet).

    Outlets are selected by the caller from actual sea-facing cells. Each arm is
    routed by the existing irregular mesh path finder, avoiding all other arms.
    Bed cuts are limited to existing loose stock and parked in unresolved
    inventory; this construction does not inject them as physical suspension.
    """
    domain = np.asarray(domain, bool) & state.valid_mask
    mesh = grid_mesh(state.bed_m.shape, x0_m=state.origin_xz_m[0], z0_m=state.origin_xz_m[1],
                     dx_m=state.spacing_m, world_seed=world_seed)
    max_stage = hydraulic_config.upstream_stage_limit_m
    if prepared_paths is not None:
        cells_list = prepared_paths['cells']
        points_list = prepared_paths['points_xz']
        if len(cells_list) != len(forks)+1 or len(points_list) != len(cells_list):
            raise ValueError('invalid prepared path count')
        for cells, coordinates in zip(cells_list, points_list):
            cells = np.asarray(cells)
            coordinates = np.asarray(coordinates, float)
            if (cells.ndim != 2 or cells.shape[1] != 2 or len(cells) < 2
                    or coordinates.shape != cells.shape or not np.isfinite(coordinates).all()
                    or not np.equal(cells, np.floor(cells)).all()):
                raise ValueError('invalid prepared path geometry')
            cells = cells.astype(int)
            if (np.any(cells < 0) or np.any(cells[:, 0] >= domain.shape[0])
                    or np.any(cells[:, 1] >= domain.shape[1])):
                raise ValueError('prepared path outside source')
            ids = np.ravel_multi_index(cells.T, domain.shape)
            expected = np.column_stack((mesh.node_x_m[ids], mesh.node_z_m[ids]))
            if (not domain[tuple(cells.T)].all() or not np.allclose(coordinates, expected, rtol=0, atol=1e-8)
                    or len(set(ids)) != len(ids)
                    or any(b not in mesh.indices[mesh.indptr[a]:mesh.indptr[a+1]] for a, b in zip(ids, ids[1:]))):
                raise ValueError('prepared path is not valid source geometry')
    if prepared_paths is None:
        main, points = irregular_valley_path(state.bed_m, domain, inlet_zx, main_outlet_zx,
            max_stage, state.spacing_m, origin_xz_m=state.origin_xz_m, world_seed=world_seed, mesh=mesh)
    else:
        main = np.asarray(prepared_paths['cells'][0], dtype=int)
        points = np.asarray(prepared_paths['points_xz'][0], dtype=float)
        if tuple(main[0]) != tuple(inlet_zx) or tuple(main[-1]) != tuple(main_outlet_zx):
            raise ValueError('prepared main endpoints differ')
    paths = [main.tolist()]
    xy = [points.tolist()]
    for parent_index, fork_index, outlet in forks:
        parent = paths[parent_index]
        if isinstance(fork_index, float):
            if not 0 < fork_index < 1:
                raise ValueError('fractional fork must be between zero and one')
            fork_index = int(round(fork_index * (len(parent) - 1)))
        if not 0 < fork_index < len(parent) - 1:
            raise ValueError('fork must be inside parent route')
        fork = parent[fork_index]
        forbidden = np.zeros(domain.shape, bool)
        for path in paths:
            for cell in path:
                forbidden[tuple(cell)] = True
        forbidden[tuple(fork)] = False
        direction = None
        if fork_direction_weight:
            previous = np.asarray(xy[parent_index][:fork_index+1], float)
            lengths = np.linalg.norm(np.diff(previous, axis=0), axis=1)
            distance = np.r_[0., np.cumsum(lengths[::-1])]
            offset = min(fork_direction_decay_m, distance[-1])
            upstream = np.array([np.interp(offset, distance, previous[::-1, axis]) for axis in range(2)])
            direction = previous[-1]-upstream
        if prepared_paths is None:
            arm, arm_xy = irregular_valley_path(state.bed_m, domain, fork, outlet, max_stage,
                state.spacing_m, origin_xz_m=state.origin_xz_m, world_seed=world_seed,
                mesh=mesh, forbidden=forbidden, initial_direction_xz=direction,
                direction_weight=fork_direction_weight, direction_decay_m=fork_direction_decay_m)
        else:
            child = len(paths)
            planned = prepared_paths['cells'][child]
            planned_xy = prepared_paths['points_xz'][child]
            if (planned[:fork_index+1] != parent[:fork_index+1]
                    or tuple(planned[-1]) != tuple(outlet)):
                raise ValueError('prepared fork differs from parent or outlet')
            arm = np.asarray(planned[fork_index:], dtype=int)
            arm_xy = np.asarray(planned_xy[fork_index:], dtype=float)
        paths.append(parent[:fork_index] + arm.tolist())
        xy.append(xy[parent_index][:fork_index] + arm_xy.tolist())
    if (depth_m <= 0 or width_m <= 0 or not np.isfinite(bed_slope_m_per_m)
            or bed_slope_m_per_m < 0 or not isinstance(subdivisions, int) or subdivisions < 2):
        raise ValueError('invalid channel geometry')
    cells = {tuple(cell) for path in paths for cell in path}
    shares = np.full(len(paths), 1 / len(paths)) if route_shares is None else np.asarray(route_shares, float)
    if (shares.shape != (len(paths),) or not np.isfinite(shares).all()
            or (shares <= 0).any() or not np.isclose(shares.sum(), 1.)):
        raise ValueError('invalid design route shares')
    node_q = {cell: 0. for cell in cells}
    for path, share in zip(paths, shares):
        for cell in path:
            node_q[tuple(cell)] += float(discharge_m3_s * share)
    widths = {cell: float(formative_section(q, bed_resistance, bank_resistance, fracture, bank_cohesion,
                reference_discharge_m3_s=reference_q_m3_s, reference_width_m=width_m,
                max_width_m=max_width_m).width_m) for cell, q in node_q.items()}
    targets = {}
    for path, coordinates in zip(paths, xy):
        lengths = np.linalg.norm(np.diff(np.asarray(coordinates), axis=0), axis=1)
        distance = np.r_[np.cumsum(lengths[::-1])[::-1], 0.]
        for cell, length in zip(path, distance):
            key = tuple(cell)
            target = sea_level_m - depth_m + bed_slope_m_per_m * length
            targets[key] = max(targets.get(key, -np.inf), target)
    ordered, fraction, cuts, node_count, node_bed_sum, node_bank_sum, footprint = _footprint(
        state, domain, paths, xy, widths, targets, subdivisions)
    if np.any(node_count == 0):
        raise ValueError('river section missed by footprint sampling; increase subdivisions')
    cuts = np.minimum(cuts, state.bed_solid_m3 * fraction)
    stock = state.bed_solid_m3 - cuts
    cut = float(cuts.sum())
    out = replace(state, bed_solid_m3=stock, unresolved_solid_m3=state.unresolved_solid_m3 + cut)
    section_bed = {cell: float(node_bed_sum[i] / node_count[i]) for i, cell in enumerate(ordered)}
    section_bank = {cell: max(section_bed[cell], float(node_bank_sum[i] / node_count[i]))
                    for i, cell in enumerate(ordered)}
    main_bed = np.array([section_bed[tuple(c)] for c in main])
    main_width = np.array([widths[tuple(c)] for c in main])
    routes = {'main_cells_zx': main, 'main_points_xz': points,
              'branch_offsets': np.array([0]), 'branch_cells_zx': np.empty((0, 2), int),
              'branch_points_xz': np.empty((0, 2)), 'section_bed_m': main_bed,
              'section_bank_m': np.array([section_bank[tuple(c)] for c in main]),
              'section_width_m': main_width,
              'section_stage_m': np.full(len(main), max_stage)}
    routes['owner_fine_area_fraction'] = fraction
    routes['owner_fine_bed_solid_m3'] = state.bed_solid_m3*fraction-cuts
    routes['owner_outer_bed_solid_m3'] = state.bed_solid_m3*(1-fraction)
    routes['owner_fine_mobile_solid_m3'] = state.mobile_solid_m3*fraction
    routes['owner_outer_mobile_solid_m3'] = state.mobile_solid_m3*(1-fraction)
    routes['owner_fine_stranded_solid_m3'] = state.stranded_solid_m3*fraction
    routes['owner_outer_stranded_solid_m3'] = state.stranded_solid_m3*(1-fraction)
    routes['owner_fine_base_bed_m'] = state.base_bed_m
    routes['owner_outer_base_bed_m'] = state.base_bed_m
    routes['owner_geometry_difference_bulk_m3'] = np.zeros_like(fraction)
    metadata = {'source_identity': state.source_identity,
                'route_geometry_algorithm': 'geological-irregular-valley-v1',
                'route_geometry_seed': world_seed}
    out, progress = initialize(out, routes, metadata, input_id=input_id,
                               discharge_m3_s=discharge_m3_s, solid_rate_m3_s=solid_rate_m3_s)
    progress['routes'] = paths
    progress['shares'] = shares.tolist()
    progress['route_geometry'] = build_route_geometry(out, paths, xy, metadata['route_geometry_algorithm'], world_seed)
    existing = {tuple(row[:2]) for row in progress['hydraulic_sections']['nodes']}
    for cell in sorted(cells - existing):
        b = section_bed[cell]
        progress['hydraulic_sections']['nodes'].append([*cell, b, widths[cell], section_bank[cell]])
    progress['geological_network'] = {'forks': [[int(a), float(b), list(c)] for a, b, c in forks],
                                      'excavated_solid_m3': cut, 'construction': 'explicit initial tree',
                                      'excavated_destination': 'unresolved_solid_m3; not automatically resupplied',
                                      'target_bed_slope_m_per_m': bed_slope_m_per_m,
                                      'design_route_shares': shares.tolist(),
                                      'node_design_q_m3_s': [[*cell, node_q[cell]] for cell in sorted(cells)],
                                      'width_parameters': {'reference_q_m3_s': reference_q_m3_s,
                                          'reference_width_m': width_m, 'max_width_m': max_width_m,
                                          'bed_resistance': bed_resistance, 'bank_resistance': bank_resistance,
                                          'fracture': fracture, 'bank_cohesion': bank_cohesion},
                                      'footprint_subdivisions': subdivisions,
                                      'fork_direction_weight': fork_direction_weight,
                                      'fork_direction_decay_m': fork_direction_decay_m,
                                      'footprint_area_m2': float(fraction.sum()*state.spacing_m**2)}
    progress['node_footprints'] = [[*cell, [[r, c, part,
        float(state.bed_solid_m3[r, c]*part - removed),
        float(state.mobile_solid_m3[r, c]*part),
        float(state.stranded_solid_m3[r, c]*part)] for r, c, part, removed in footprint[i]]]
        for i, cell in enumerate(ordered)]
    hydraulic = solve(out, progress, sea_level_m, hydraulic_config)
    progress['river_hydraulics'] = hydraulic
    return _record(out, progress), progress, hydraulic
