"""Bounded deposition-triggered trials for multi-cell distributaries."""
from copy import deepcopy

import numpy as np
from scipy import ndimage

from . import coastal_delta_branching as branching
from .coastal_delta_branch_attachment import attach_multicell_branch
from .coastal_delta_hydraulics import solve
from .coastal_delta_graph_hydraulics import HydraulicNumericalError
from .coastal_delta_routes import irregular_valley_path
from terrain_pipeline.drainage import grid_mesh as grid_mesh


def coastal_front(valid, bed, ocean, free, sea_level_m):
    """Unowned cells on either side of the actual land/connected sea interface."""
    land = valid & (bed >= sea_level_m)
    return valid & free & ((land & ndimage.binary_dilation(ocean)) |
                           (ocean & (bed >= sea_level_m-5.) & ndimage.binary_dilation(land)))


def initialize_baseline(progress):
    """Record the current section beds before the first morphology step."""
    if 'avulsion_baseline_sections' not in progress:
        progress['avulsion_baseline_sections'] = deepcopy(progress['hydraulic_sections']['nodes'])


def activate_multicell_candidate(state, progress, *, hydraulic_config, sea_level_m=0.,
                                 min_rise_m=.1, max_cut_m=.5, mouth_radius_m=4000.):
    branching._validate(state, progress)
    if not np.isfinite([sea_level_m, min_rise_m, max_cut_m]).all() or min_rise_m <= 0 or max_cut_m < 0:
        raise ValueError('invalid avulsion settings')
    graph_backend = progress.get('hydraulics_backend') == 'physical_edge_graph'
    dynamic = progress.get('dynamic_plan') if graph_backend else None
    if graph_backend and not dynamic:
        return state, progress, {'activated': False, 'trigger': 'dynamic_not_enrolled'}
    if dynamic:
        policy = dynamic['config']
        from .coastal_delta_network_plan import _dynamic_policy_identity, _shared_upstream_prefix
        if (progress.get('hierarchical_plan', {}).get('config') != policy
                or dynamic.get('policy_identity') != _dynamic_policy_identity(state, progress, policy, hydraulic_config, sea_level_m)):
            return state, progress, {'activated': False, 'trigger': 'dynamic_policy_identity_mismatch'}
        min_rise_m, max_cut_m, mouth_radius_m = policy['min_rise_m'], policy['max_cut_m'], policy['mouth_radius_m']
    if 'avulsion_baseline_sections' not in progress:
        p = deepcopy(progress)
        initialize_baseline(p)
        return branching._record(state, p), p, {'activated': False, 'trigger': 'baseline_recorded'}
    plan = progress.get('hierarchical_plan')
    if not plan:
        return state, progress, {'activated': False, 'trigger': 'missing_hierarchical_plan'}
    cfg = plan['config']
    counts = {'eligible_parents': 0, 'raised_parents': 0, 'front_cells': 0,
              'paths_tested': 0, 'attachment_trials': 0}
    graph_backend = progress.get('hydraulics_backend') == 'physical_edge_graph'
    if len({tuple(r[-1]) for r in progress['routes']}) >= cfg['max_mouths']:
        return state, progress, {'activated': False, 'trigger': 'mouth_limit', 'counts': counts}
    baseline = {tuple(r[:2]): r[2] for r in progress['avulsion_baseline_sections']}
    sections = {tuple(r[:2]): r[2] for r in progress['hydraulic_sections']['nodes']}
    routes = [[tuple(c) for c in route] for route in progress['routes']]
    hydraulic = None
    edge_q = {}
    if dynamic:
        try:
            hydraulic = solve(state, progress, sea_level_m, hydraulic_config)
        except (ValueError, ArithmeticError, HydraulicNumericalError) as exc:
            return state, progress, {'activated': False, 'trigger': 'hydraulic_failure', 'reason': str(exc), 'counts': counts}
        edge_q = {tuple(row[:4]): row[4] for row in hydraulic['edge_q_m3_s']}
    seen_physical = set()
    eligible = []
    for i, route in enumerate(routes):
        if (plan['route_depths'][i] >= cfg['max_depth'] or plan['side_branch_counts'][i] >= cfg['max_side_branches']
                or (not dynamic and progress['shares'][i]*progress['discharge_m3_s']*.5 < cfg['min_design_q_m3_s'])):
            continue
        exclusive = [k for k, cell in enumerate(route[:-1]) if graph_backend or all(cell not in other for j, other in enumerate(routes) if j != i)]
        if dynamic:
            owned = []
            for k in exclusive:
                if _shared_upstream_prefix(routes, i, k):
                    continue
                physical = (*route[k], *route[k+1])
                # One physical continuation is owned by its first saved cover;
                # copied downstream suffixes cannot create extra fork budgets.
                if any(physical in [(*a, *b) for a, b in zip(other, other[1:])] for other in routes[:i]):
                    continue
                if physical in seen_physical:
                    continue
                seen_physical.add(physical)
                if edge_q.get(physical, 0.) >= 2*policy['min_actual_child_q_m3_s']:
                    owned.append(k)
            exclusive = owned
        if not exclusive:
            continue
        counts['eligible_parents'] += 1
        candidates = [(k, max((sections[c]-baseline[c] for c in route[k+1:] if c in baseline), default=0.)) for k in exclusive]
        candidates = [(k, rise) for k, rise in candidates if rise >= min_rise_m]
        if candidates:
            counts['raised_parents'] += 1
            eligible.append((i, candidates))
    if not eligible:
        return state, progress, {'activated': False, 'trigger': 'no_downstream_rise' if counts['eligible_parents'] else 'parent_limits', 'counts': counts}
    try:
        if hydraulic is None:
            hydraulic = solve(state, progress, sea_level_m, hydraulic_config)
    except (ValueError, ArithmeticError, HydraulicNumericalError) as exc:
        return state, progress, {'activated': False, 'trigger': 'hydraulic_failure', 'reason': str(exc), 'counts': counts}
    stages = {tuple(r[:2]): r[2] for r in hydraulic['nodes']}
    shape = state.bed_m.shape
    occupied = np.zeros(shape)
    owned_bed = np.zeros(shape)
    for _, _, parts in progress['node_footprints']:
        for r, c, fraction, bed, *_ in parts:
            occupied[r, c] += fraction
            owned_bed[r, c] += bed
    free = np.maximum(0., 1.-occupied)
    outer_bed = np.full(shape, np.inf)
    mask = free > 1e-8
    outer_bed[mask] = state.base_bed_m[mask] + np.maximum(0., state.bed_solid_m3[mask]-owned_bed[mask])/(free[mask]*state.spacing_m**2*(1-state.porosity[mask]))
    wet = state.valid_mask & (state.bed_m < sea_level_m) & (occupied < 1e-8)
    labels, _ = ndimage.label(wet)
    ids = np.unique(labels[state.ocean_seed_mask & wet])
    ocean = wet & np.isin(labels, ids[ids != 0])
    front = coastal_front(state.valid_mask, state.bed_m, ocean, mask, sea_level_m)
    mesh = grid_mesh(shape, x0_m=state.origin_xz_m[0], z0_m=state.origin_xz_m[1], dx_m=state.spacing_m,
                     world_seed=progress['route_geometry']['seed'])
    vertex = np.asarray(plan['resolved_vertex_xz_m'])
    axis = np.asarray(cfg['sea_axis_xz'], float)
    axis /= np.linalg.norm(axis)
    x = mesh.node_x_m.reshape(shape)-vertex[0]
    z = mesh.node_z_m.reshape(shape)-vertex[1]
    forward = x*axis[0]+z*axis[1]
    angle = np.arctan2(x*axis[1]-z*axis[0], forward)
    fan = ((forward >= 0) & (np.abs(angle) <= np.deg2rad(cfg['fan_half_angle_deg']))
           & (np.hypot(x, z) <= cfg['fan_max_length_m']))
    front &= fan
    for route in routes:
        for cell in route:
            front[cell] = False
    positions = {tuple(r[:2]): np.asarray(r[2:], float) for r in progress['route_geometry']['nodes']}
    mouths = [positions[r[-1]] for r in routes]
    def theta(point):
        d = point-vertex
        return np.arctan2(d[0]*axis[1]-d[1]*axis[0], d @ axis)
    mouth_angles = np.array([theta(m) for m in mouths])
    front_cells = np.argwhere(front)
    counts['front_cells'] = len(front_cells)
    forbidden = ~mask
    forbidden = forbidden.copy()
    for route in routes:
        for cell in route:
            forbidden[cell] = True
    fork_points = [positions[tuple(routes[int(row[0])][int(row[1])])] for row in plan['forks']]
    attempts = []
    parent_counts = {}
    for parent, choices in eligible:
        stats = {'raised_forks': len(choices), 'service_front': 0, 'mouth_spaced': 0,
                 'fork_with_stage': 0, 'fork_spaced_wet': 0, 'target_pairs': 0, 'forward_pairs': 0,
                 'direction_pairs': 0, 'paths_tested': 0}
        parent_counts[str(parent)] = stats
        if dynamic:
            # Coincident mouths form one service group. Every physical arm in
            # that group may reach the front using its own fork and direction.
            served = [tuple(map(int, c)) for c in front_cells
                      if abs(mouth_angles[parent]-angle[tuple(c)]) <= np.min(abs(mouth_angles-angle[tuple(c)]))+1e-12]
        else:
            served = [tuple(map(int, c)) for c in front_cells if int(np.argmin(abs(mouth_angles-angle[tuple(c)]))) == parent]
        stats['service_front'] = len(served)
        def point(c):
            idx = np.ravel_multi_index(c, shape)
            return np.array([mesh.node_x_m[idx], mesh.node_z_m[idx]])
        served = [c for c in served if all(np.linalg.norm(point(c)-m) >= cfg['min_spacing_m'] for m in mouths)]
        stats['mouth_spaced'] = len(served)
        if dynamic:
            served = [c for c in served if outer_bed[c]-max_cut_m < sea_level_m]
        served.sort(key=lambda c: (angle[c], c))
        wet_forks = [(k, rise) for k, rise in choices if routes[parent][k] in stages]
        stats['fork_with_stage'] = len(wet_forks)
        valid_forks = [(k, rise) for k, rise in wet_forks if
                       all(np.linalg.norm(positions[routes[parent][k]]-f) >= cfg['min_spacing_m'] for f in fork_points)]
        stats['fork_spaced_wet'] = len(valid_forks)
        if not served or not valid_forks:
            continue
        fork_samples = min(policy['max_candidates_per_parent'], len(valid_forks)) if dynamic else min(5, len(valid_forks))
        selected = [valid_forks[i] for i in sorted(set(np.linspace(0, len(valid_forks)-1, fork_samples, dtype=int)))]
        for k, rise in selected:
            if dynamic and (counts['paths_tested'] >= policy['max_total_candidates'] or stats['paths_tested'] >= policy['max_candidates_per_parent']):
                break
            start = routes[parent][k]
            upstream = np.asarray([positions[c] for c in routes[parent][:k+1]])
            distances = np.r_[0., np.cumsum(np.linalg.norm(np.diff(upstream, axis=0), axis=1))]
            back = max(0, np.searchsorted(distances, distances[-1]-cfg.get('direction_decay_m', 5000.)))
            incoming = upstream[-1]-upstream[back]
            incoming_length = np.linalg.norm(incoming)
            if incoming_length <= 0:
                continue
            stats['target_pairs'] += len(served)
            forward_targets = [c for c in served if (point(c)-positions[start]) @ axis >= cfg['min_forward_m']]
            stats['forward_pairs'] += len(forward_targets)
            targets = [c for c in forward_targets if np.dot(incoming, point(c)-positions[start]) >=
                       .15*incoming_length*np.linalg.norm(point(c)-positions[start])]
            stats['direction_pairs'] += len(targets)
            if dynamic:
                targets = [c for c in targets if np.linalg.norm(point(c)-positions[start]) <= mouth_radius_m]
                targets.sort(key=lambda c: (np.linalg.norm(point(c)-positions[start]), c))
            target_samples = policy['max_candidates_per_parent'] if dynamic else 3
            targets = [targets[i] for i in sorted(set(np.linspace(0, len(targets)-1, min(target_samples, len(targets)), dtype=int)))] if targets else []
            trial_bed = np.maximum(state.base_bed_m, outer_bed-max_cut_m)
            allowed = state.valid_mask & fan & mask & (trial_bed < hydraulic_config.upstream_stage_limit_m)
            if dynamic:
                radial = np.hypot(mesh.node_x_m.reshape(shape)-positions[start][0],
                                  mesh.node_z_m.reshape(shape)-positions[start][1])
                allowed &= radial <= mouth_radius_m
                targets = [c for c in targets if radial[c] <= mouth_radius_m]
            allowed[start] = True
            blocked = forbidden.copy()
            blocked[start] = False
            for target in targets:
                if dynamic and (counts['paths_tested'] >= policy['max_total_candidates'] or stats['paths_tested'] >= policy['max_candidates_per_parent']):
                    break
                counts['paths_tested'] += 1
                stats['paths_tested'] += 1
                # Search with the same finite per-cell stock and cut limit as attachment.
                bed = trial_bed.copy()
                bed[start] = sections[start]
                # The finite trial bed is searched under the inlet head limit;
                # the actual hydraulic solve validates the resulting arm.
                target_allowed = allowed.copy()
                target_allowed[target] = bed[target] < hydraulic_config.upstream_stage_limit_m
                try:
                    path, xy = irregular_valley_path(bed, target_allowed, start, target, hydraulic_config.upstream_stage_limit_m, state.spacing_m,
                        origin_xz_m=state.origin_xz_m, world_seed=progress['route_geometry']['seed'], mesh=mesh,
                        forbidden=blocked, start_xz_m=positions[start], initial_direction_xz=incoming,
                        max_turn_deg=90., turn_penalty_k=1.,
                        start_directions_xz=[positions[start]-positions[tuple(row[:2])]
                            for row in progress['route_geometry']['edges'] if tuple(row[2:]) == start],
                        direction_weight=cfg.get('direction_weight', 4.),
                        direction_decay_m=cfg.get('direction_decay_m', 5000.),
                        ownership_penalty=1./np.maximum(free, .001)-1.)
                except ValueError as exc:
                    attempts.append({'parent': parent, 'fork_index': k, 'fork_zx': list(start), 'outlet': list(target), 'rise_m': float(rise), 'fork_stage_m': float(stages[start]), 'target_outer_bed_m': float(outer_bed[target]), 'target_depth_m': float(sea_level_m-state.bed_m[target]), 'reason': str(exc)})
                    continue
                projection = (xy-xy[0]) @ axis
                length = np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()
                direct = np.linalg.norm(xy[-1]-xy[0])
                if (projection[-1] < cfg['min_forward_m'] or direct <= 0 or length > cfg['max_detour_ratio']*direct
                        or -np.minimum(np.diff(projection), 0).sum() > cfg['max_backtrack_m']
                        or np.max(np.maximum.accumulate(projection)-projection) > cfg['max_backtrack_m']):
                    attempts.append({'parent': parent, 'fork_index': k, 'outlet': list(target), 'rise_m': float(rise), 'fork_stage_m': float(stages[start]), 'forward_m': float(projection[-1]), 'length_m': float(length), 'direct_m': float(direct), 'reason': 'path violates progress or detour limits'})
                    continue
                travel = np.r_[0., np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
                offset = min(float(travel[-1]), cfg.get('direction_decay_m', 5000.))
                exit_point = np.array([np.interp(offset, travel, xy[:, dim]) for dim in range(2)])
                outgoing = exit_point-xy[0]
                fork_angle = float(np.degrees(np.arccos(np.clip(np.dot(incoming, outgoing)/(incoming_length*np.linalg.norm(outgoing)), -1., 1.))))
                counts['attachment_trials'] += 1
                out, p, report = attach_multicell_branch(state, progress, parent_index=parent, fork_index=k,
                    path_zx=path, path_xz_m=xy, hydraulic_config=hydraulic_config,
                    sea_level_m=sea_level_m, max_cut_m=max_cut_m)
                attempts.append({'parent': parent, 'fork_index': k, 'outlet': list(target), 'rise_m': float(rise),
                                 'fork_stage_m': float(stages[start]), 'path_zx': path.tolist(), 'fork_angle_5km_deg': fork_angle, 'max_outer_bed_m': float(np.max(outer_bed[tuple(path[1:].T)])),
                                 'reason': report['reason']})
                if report['attached']:
                    # Consume the existing trigger while allowing future fresh deposition.
                    p['avulsion_baseline_sections'] = deepcopy(p['hydraulic_sections']['nodes'])
                    p['hierarchical_plan']['current_service_rule'] = 'physical fork direction within nearest mouth group' if dynamic else 'angular nearest current mouth within saved fan'
                    p['hierarchical_plan']['current_service_mouth_angles_rad'] = [float(theta(positions[route[-1]])) for route in routes] + [float(theta(xy[-1]))]
                    result = {'activated': True, 'trigger': 'activated', 'parent': parent, 'fork_index': k,
                              'rise_m': float(rise), 'fork_angle_5km_deg': fork_angle, 'counts': counts, 'parent_counts': parent_counts, 'attachment': report,
                              'route_q_before_m3_s': hydraulic['route_q_m3_s'],
                              'route_q_after_m3_s': p['river_hydraulics']['route_q_m3_s'], 'attempts': attempts,
                              'service_rule': 'physical fork direction within nearest mouth group' if dynamic else 'angular nearest current mouth'}
                    p['history'].append({'event': 'multicell_avulsion', **deepcopy(result)})
                    return branching._record(out, p), p, result
    return state, progress, {'activated': False, 'trigger': 'no_feasible_candidate', 'counts': counts,
                             'attempts': attempts, 'parent_counts': parent_counts, 'service_rule': 'physical fork direction within nearest mouth group' if dynamic else 'angular nearest current mouth'}

