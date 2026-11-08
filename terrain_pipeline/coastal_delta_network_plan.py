"""Deterministic, bounded distributary planning on a connected coastal plain.

The resulting forks and route shares are inputs to geological_network.construct.
Depth counts every split on a route, including continuation of the parent.
"""
from dataclasses import dataclass, asdict

import numpy as np
from scipy import ndimage

from .coastal_delta_routes import connected_ocean, irregular_valley_path
from terrain_pipeline.drainage import grid_mesh as grid_mesh


@dataclass(frozen=True)
class PlanConfig:
    max_depth: int = 3
    max_side_branches: int = 2
    max_mouths: int = 8
    min_spacing_m: float = 6000.
    min_design_q_m3_s: float = 1000.
    min_fraction: float = .2
    parent_width_m: float = 1000.
    direction_weight: float = 4.
    direction_decay_m: float = 5000.
    vertex_zx: tuple | None = None
    sea_axis_xz: tuple = (0., 1.)
    fan_half_angle_deg: float = 65.
    fan_max_length_m: float = 100000.
    min_forward_m: float = 3000.
    max_backtrack_m: float = 3000.
    max_detour_ratio: float = 1.6


@dataclass(frozen=True)
class DynamicPlanConfig(PlanConfig):
    """Explicit policy for deposition-triggered physical graph attachments."""
    min_rise_m: float = .1
    max_cut_m: float = .5
    min_actual_child_q_m3_s: float = 40.
    min_effective_width_m: float = 50.
    max_total_candidates: int = 6
    max_candidates_per_parent: int = 3
    max_successes_per_call: int = 1
    mouth_radius_m: float = 4000.


def _dynamic_policy_identity(state, progress, config, hydraulic_config, sea_level_m):
    import hashlib
    import json
    data = {'config': config, 'source': progress['source_state_fingerprint'],
            'grid': [list(state.bed_m.shape), list(state.origin_xz_m), state.spacing_m],
            'hydraulic_config': asdict(hydraulic_config), 'sea_level_m': sea_level_m}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _shared_upstream_prefix(routes, parent_index, fork_index):
    """A new upstream split must not silently deepen an existing child."""
    prefix = routes[parent_index][:fork_index+1]
    return any(i != parent_index and len(route) > fork_index+1
               and route[:fork_index+1] == prefix for i, route in enumerate(routes))


def _replay_lineage(progress):
    """Replay append-only construction and actual attachments, never infer shares."""
    routes = [[tuple(c) for c in r] for r in progress['routes']]
    construction = progress['geological_network']['forks']
    initial_count = len(construction) + 1
    history = [h for h in progress['history'] if h.get('event') == 'branch_attachment' and h.get('attached')]
    if len(routes) != initial_count + len(history):
        raise ValueError('missing attachment history for saved route cover')
    depths, counts, lineage, forks = [0], [0], [], []
    events = []
    for child, (parent, fork, outlet) in enumerate(construction, 1):
        parent = int(parent)
        if not 0 <= parent < child:
            raise ValueError('invalid construction parent')
        if isinstance(fork, float) and 0 < fork < 1:
            common = 0
            for a, b in zip(routes[parent], routes[child]):
                if a != b:
                    break
                common += 1
            if common < 2 or common >= min(len(routes[parent]), len(routes[child])):
                raise ValueError('ambiguous fractional construction fork')
            fork = common-1
        fork = int(fork)
        if routes[child][:fork+1] != routes[parent][:fork+1]:
            raise ValueError('construction prefix differs from saved route')
        events.append((child, parent, fork, None, 'construction'))
    for child, h in enumerate(history, initial_count):
        if h.get('route_index') != child:
            raise ValueError('attachment history route order differs')
        path = [tuple(c) for c in h['path_zx']]
        candidates = []
        for parent in range(child):
            if path[0] not in routes[parent]:
                continue
            fork = routes[parent].index(path[0])
            rejoin = h.get('rejoin_index')
            if rejoin is not None:
                rejoin = int(rejoin)
                if not fork < rejoin < len(routes[parent]) or routes[parent][rejoin] != path[-1]:
                    continue
            expected = routes[parent][:fork+1] + path[1:]
            if rejoin is not None:
                expected += routes[parent][rejoin+1:]
            # Mouth extension can append geometry after the historic new mouth.
            if routes[child][:len(expected)] != expected:
                continue
            if 'parent_index' in h and (h['parent_index'] != parent or h.get('fork_index') != fork):
                continue
            candidates.append((parent, fork, rejoin))
        if len(candidates) != 1:
            raise ValueError('missing or ambiguous attachment parent/fork history')
        parent, fork, rejoin = candidates[0]
        events.append((child, parent, fork, rejoin, 'attachment'))
    for child, parent, fork, rejoin, source in events:
        if child != len(depths):
            raise ValueError('nonsequential lineage')
        depths[parent] += 1
        depths.append(depths[parent])
        counts[parent] += 1
        counts.append(0)
        forks.append([parent, fork, list(routes[child][-1])])
        lineage.append({'route_index': child, 'parent_index': parent, 'fork_index': fork,
                        'fork_zx': list(routes[parent][fork]), 'rejoin_index': rejoin, 'source': source})
    return depths, counts, forks, lineage


def enroll_dynamic_plan(state, progress, *, config, hydraulic_config, sea_level_m, input_id):
    """Register real existing topology and section beds without changing the terrain.

    Failed enrollment is transactional. Legacy products remain unenrolled until
    this explicit call, and repeat calls preserve the original consumed baseline.
    """
    from copy import deepcopy
    import hashlib
    import json
    from . import coastal_delta_branching as branching
    from .coastal_delta_hydraulics import solve
    from .coastal_delta_graph_hydraulics import HydraulicNumericalError

    def reject(reason):
        return state, progress, {'enrolled': False, 'reason': reason}

    try:
        branching._validate(state, progress)
        if not isinstance(config, DynamicPlanConfig) or not input_id:
            return reject('explicit DynamicPlanConfig and input_id required')
        cfg = json.loads(json.dumps(asdict(config)))
        values = [v for v in cfg.values() if isinstance(v, (float, int))]
        if (not np.isfinite(values).all() or not np.isfinite(sea_level_m)
                or any(not isinstance(v, int) for v in (config.max_depth, config.max_side_branches, config.max_mouths, config.max_total_candidates, config.max_candidates_per_parent, config.max_successes_per_call)) or config.min_rise_m <= 0 or not 0 <= config.max_cut_m <= .5
                or config.min_actual_child_q_m3_s <= 0 or config.min_effective_width_m <= 0
                or config.max_total_candidates < 1 or config.max_candidates_per_parent < 1
                or config.max_successes_per_call != 1 or config.max_total_candidates > 6
                or config.max_candidates_per_parent > 3 or config.max_depth < 0
                or config.max_side_branches < 0 or config.max_mouths < 1
                or config.min_spacing_m <= 0 or config.min_forward_m <= 0
                or config.mouth_radius_m <= 0 or config.direction_decay_m <= 0
                or not 0 < config.fan_half_angle_deg < 90 or config.fan_max_length_m <= 0
                or config.max_backtrack_m < 0 or config.max_detour_ratio < 1):
            return reject('invalid dynamic policy')
        axis = np.asarray(config.sea_axis_xz, float)
        if axis.shape != (2,) or not np.isfinite(axis).all() or np.linalg.norm(axis) <= 0:
            return reject('invalid sea axis')
        if progress.get('hydraulics_backend') != 'physical_edge_graph':
            return reject('dynamic enrollment requires physical_edge_graph')
        saved = progress.get('dynamic_plan')
        if saved:
            if (saved['config'] != cfg or saved['input_id'] != input_id
                    or saved.get('policy_identity') != _dynamic_policy_identity(state, progress, cfg, hydraulic_config, sea_level_m)):
                return reject('dynamic policy identity differs')
            return state, progress, {'enrolled': True, 'reason': 'already_enrolled', 'identity': saved['identity']}
        from .coastal_delta_node_inventory import ChannelInventory
        pool = ChannelInventory(state, progress)
        if any(not np.isclose(row[2], pool.section_bed(tuple(row[:2])), rtol=0, atol=1e-8)
               for row in progress['hydraulic_sections']['nodes']):
            return reject('section beds differ from actual owned inventory')
        depths, counts, forks, lineage = _replay_lineage(progress)
        solve(state, progress, sea_level_m, hydraulic_config)
        identity_data = {'config': cfg, 'input_id': input_id,
                         'source': progress['source_state_fingerprint'],
                         'grid': [list(state.bed_m.shape), list(state.origin_xz_m), state.spacing_m],
                         'geometry': progress['route_geometry'], 'lineage': lineage,
                         'hydraulic_config': asdict(hydraulic_config), 'sea_level_m': sea_level_m}
        identity = hashlib.sha256(json.dumps(identity_data, sort_keys=True).encode()).hexdigest()
        p = deepcopy(progress)
        inlet = tuple(p['routes'][0][0])
        positions = {tuple(r[:2]): r[2:] for r in p['route_geometry']['nodes']}
        if config.vertex_zx is None or tuple(config.vertex_zx) == inlet:
            vertex = positions[inlet]
        else:
            vertex = (np.asarray(state.origin_xz_m) + np.asarray(config.vertex_zx)[::-1]*state.spacing_m).tolist()
        p['hierarchical_plan'] = {'config': cfg, 'route_depths': depths, 'side_branch_counts': counts,
                                  'forks': forks, 'resolved_vertex_xz_m': vertex,
                                  'route_shares': list(p['shares']),
                                  'design_q_m3_s': [p['discharge_m3_s']*s for s in p['shares']]}
        p['dynamic_plan'] = {'algorithm': 'actual-deposition-graph-avulsion-v1',
                             'input_id': input_id, 'identity': identity, 'config': cfg,
                             'policy_identity': _dynamic_policy_identity(state, progress, cfg, hydraulic_config, sea_level_m),
                             'source_identity': identity_data['source'], 'lineage': lineage}
        p['avulsion_baseline_sections'] = deepcopy(p['hydraulic_sections']['nodes'])
        p['history'].append({'event': 'dynamic_plan_enrollment', 'identity': identity, 'input_id': input_id})
        return branching._record(state, p), p, {'enrolled': True, 'reason': 'enrolled',
                                               'identity': identity, 'route_depths': depths,
                                               'side_branch_counts': counts, 'lineage': lineage}
    except (ValueError, ArithmeticError, KeyError, TypeError, IndexError, HydraulicNumericalError) as exc:
        return reject(str(exc))


def plan(state, *, domain, inlet_zx, discharge_m3_s, max_stage_m,
         config=PlanConfig(), world_seed=20261020):
    """Plan reachable binary splits; return a construct-compatible plan.

    Candidate front is connected land adjacent to seeded ocean. Candidates are
    ordered by angular coverage; forks are scored on measured incoming direction,
    terrain, separation and remaining length. Failed routes are discarded.
    """
    c = config
    if (c.max_depth < 0 or c.max_side_branches < 0 or c.max_mouths < 1
            or c.min_spacing_m <= 0 or c.parent_width_m <= 0
            or c.min_design_q_m3_s <= 0 or not 0 < c.min_fraction <= .5
            or discharge_m3_s < c.min_design_q_m3_s):
        raise ValueError('invalid planning limits')
    domain = np.asarray(domain, bool) & state.valid_mask
    labels, _ = ndimage.label(domain)
    label = labels[tuple(inlet_zx)]
    if not label:
        raise ValueError('inlet outside domain')
    domain = labels == label
    axis_xz = np.asarray(c.sea_axis_xz, float)
    if (axis_xz.shape != (2,) or not np.isfinite(axis_xz).all() or np.linalg.norm(axis_xz) == 0
            or not 0 < c.fan_half_angle_deg < 90 or c.fan_max_length_m <= 0
            or c.min_forward_m <= 0 or c.max_backtrack_m < 0 or c.max_detour_ratio < 1):
        raise ValueError('invalid fan or progress limits')
    axis_xz /= np.linalg.norm(axis_xz)
    vertex = np.asarray(inlet_zx if c.vertex_zx is None else c.vertex_zx, float)
    if vertex.shape != (2,) or not np.isfinite(vertex).all():
        raise ValueError('invalid fan vertex')
    mesh = grid_mesh(state.bed_m.shape, x0_m=state.origin_xz_m[0], z0_m=state.origin_xz_m[1],
                     dx_m=state.spacing_m, world_seed=world_seed)
    vertex_xz = np.asarray(state.origin_xz_m) + vertex[::-1]*state.spacing_m
    if np.array_equal(vertex, inlet_zx):
        inlet_node = np.ravel_multi_index(tuple(inlet_zx), domain.shape)
        vertex_xz = np.array([mesh.node_x_m[inlet_node], mesh.node_z_m[inlet_node]])
    dx = mesh.node_x_m.reshape(domain.shape)-vertex_xz[0]
    dz = mesh.node_z_m.reshape(domain.shape)-vertex_xz[1]
    forward = dx*axis_xz[0] + dz*axis_xz[1]
    cross = dx*axis_xz[1] - dz*axis_xz[0]
    fan = ((forward >= 0) & (np.abs(cross) <= forward*np.tan(np.deg2rad(c.fan_half_angle_deg)))
           & (np.hypot(dx, dz) <= c.fan_max_length_m))
    domain &= fan
    if not domain[tuple(inlet_zx)]:
        raise ValueError('inlet outside fan')
    ocean = connected_ocean(state.bed_m, state.valid_mask, state.ocean_seed_mask)
    front = domain & ndimage.binary_dilation(ocean)
    candidates = np.argwhere(front)
    delta = candidates - np.asarray(inlet_zx)
    if len(delta) == 0:
        raise ValueError('no connected ocean front')
    axis = axis_xz[::-1]
    along = delta @ axis
    candidates = candidates[along > max(2., min(10., c.min_spacing_m / state.spacing_m))]
    if not len(candidates):
        raise ValueError('no downstream ocean front')
    delta = candidates - np.asarray(inlet_zx)
    lateral = delta[:, 1]*axis[0] - delta[:, 0]*axis[1]
    angle = np.arctan2(lateral, delta @ axis)
    # Bins represent front service areas, rather than selecting coordinate extrema.
    edges = np.linspace(np.quantile(angle, .08), np.quantile(angle, .92), 10)
    pool = []
    for lo, hi in zip(edges, edges[1:]):
        ids = np.flatnonzero((angle >= lo) & (angle <= hi))
        if not len(ids):
            continue
        mid = (lo + hi) / 2
        # Prefer low coastal land within each angular service bin.
        cost = np.abs(angle[ids]-mid) + .004*np.maximum(state.bed_m[tuple(candidates[ids].T)], 0)
        pool.append(tuple(map(int, candidates[ids[np.argmin(cost)]])))
    pool = list(dict.fromkeys(pool))
    def route(start, end, forbidden=None, direction=None):
        return irregular_valley_path(state.bed_m, domain, start, end, max_stage_m, state.spacing_m,
            origin_xz_m=state.origin_xz_m, world_seed=world_seed, mesh=mesh, forbidden=forbidden,
            initial_direction_xz=direction, direction_weight=c.direction_weight if direction is not None else 0.,
            direction_decay_m=c.direction_decay_m)
    pool.sort(key=lambda p: (np.arctan2((p[1]-inlet_zx[1])*axis[0]-(p[0]-inlet_zx[0])*axis[1],
                                        np.dot(np.asarray(p)-inlet_zx, axis)), p))
    # The first mouth serves the centre of one half; its first child serves
    # the other half. Further splits divide only the parent's service range.
    main_order = sorted(pool, key=lambda p: (abs(pool.index(p)-(len(pool)-1)*.25), p))
    def acceptable(points):
        pts = np.asarray(points, float)
        edges = np.diff(pts, axis=0)
        length = np.linalg.norm(edges, axis=1).sum()
        direct = np.linalg.norm(pts[-1]-pts[0])
        projection = (pts-pts[0]) @ axis_xz
        backward = -np.minimum(np.diff(projection), 0).sum()
        drawdown = np.max(np.maximum.accumulate(projection)-projection)
        return (projection[-1] >= c.min_forward_m and direct > 0
                and length <= c.max_detour_ratio*direct
                and backward <= c.max_backtrack_m and drawdown <= c.max_backtrack_m)
    main = None
    for mouth in main_order:
        try:
            main, main_xy = route(inlet_zx, mouth)
            if not acceptable(main_xy):
                main = None
                continue
            break
        except ValueError:
            continue
    if main is None:
        raise ValueError('no reachable front candidate')
    paths, coords = [main.tolist()], [main_xy.tolist()]
    mouths, forks, flows = [mouth], [], [float(discharge_m3_s)]
    depths, branch_counts, last_fork = [0], [0], [0]
    services = [list(pool)]
    rejected = []
    spacing = max(c.min_spacing_m, 3*c.parent_width_m)
    while len(paths) < c.max_mouths:
        choices = []
        for j, (path, xy) in enumerate(zip(paths, coords)):
            if depths[j] >= c.max_depth or branch_counts[j] >= c.max_side_branches:
                continue
            if flows[j]*min(.5, 1-c.min_fraction) < c.min_design_q_m3_s:
                continue
            xy = np.asarray(xy)
            dist = np.r_[0., np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
            service = services[j]
            split = len(service)//2
            if split == 0:
                continue
            halves = (service[:split], service[split:])
            parent_half = 0 if mouths[j] in halves[0] else 1
            child_service = halves[1-parent_half]
            parent_service = halves[parent_half]
            child_mid = (len(child_service)-1)/2
            for target in child_service:
                if target in mouths or min(np.linalg.norm(np.asarray(target)-m)*state.spacing_m for m in mouths) < spacing:
                    continue
                target_xz = np.asarray(state.origin_xz_m) + np.asarray(target)[::-1]*state.spacing_m
                for i in range(max(1, last_fork[j]+1), len(path)-1):
                    if dist[i]-dist[last_fork[j]] < spacing or dist[-1]-dist[i] < spacing:
                        continue
                    # A fork must lie on this leaf's unique continuation.
                    if any(k != j and path[i:i+2] == other[i:i+2] for k, other in enumerate(paths)):
                        continue
                    side = target_xz-xy[i]
                    length = np.linalg.norm(side)
                    if length < spacing or np.dot(side, axis_xz) < c.min_forward_m:
                        continue
                    back = max(0, np.searchsorted(dist, dist[i]-c.direction_decay_m))
                    incoming = xy[i]-xy[back]
                    cosine = np.dot(incoming, side)/(np.linalg.norm(incoming)*length)
                    if cosine < .15:
                        continue
                    # Prefer later splits for nearby mouths and moderate divergence.
                    separation = np.linalg.norm(target_xz-xy[-1])
                    coverage = min(np.linalg.norm(np.asarray(target)-m)*state.spacing_m for m in mouths)
                    score = (length + .7*abs(length-separation*1.5) - 1.2*coverage +
                             10000*(1-cosine) + 500*max(0., state.bed_m[tuple(path[i])]))
                    priority = (depths[j], abs(child_service.index(target)-child_mid))
                    choices.append((priority, score, j, i, target, incoming, parent_service, child_service))
        if not choices:
            break
        success = False
        forbidden = np.zeros(domain.shape, bool)
        for path in paths:
            forbidden[tuple(np.asarray(path).T)] = True
        for _, _, j, i, target, incoming, parent_service, child_service in sorted(choices, key=lambda x: (x[0], x[1], x[2], x[3], x[4])):
            fork = tuple(paths[j][i])
            forbidden[fork] = False
            try:
                arm, arm_xy = route(fork, target, forbidden, incoming)
                if not acceptable(arm_xy):
                    raise ValueError('excessive reverse motion or detour')
            except ValueError as error:
                rejected.append({'parent': j, 'fork_index': i, 'outlet_zx': list(target),
                                 'reason': str(error)})
                forbidden[fork] = True
                continue
            forbidden[fork] = True
            forks.append((j, i, list(target)))
            paths.append(paths[j][:i]+arm.tolist())
            coords.append(coords[j][:i]+arm_xy.tolist())
            mouths.append(target)
            flows[j] *= .5
            flows.append(flows[j])
            depths[j] += 1
            depths.append(depths[j])
            branch_counts[j] += 1
            branch_counts.append(0)
            last_fork[j] = i
            last_fork.append(i)
            services[j] = parent_service
            services.append(child_service)
            success = True
            break
        if not success:
            break
    return {'main_outlet_zx': list(mouths[0]), 'forks': forks,
            'route_shares': (np.asarray(flows)/discharge_m3_s).tolist(),
            'design_q_m3_s': flows, 'route_depths': depths,
            'side_branch_counts': branch_counts, 'config': asdict(c),
            'failed_candidates': rejected, 'candidate_count': len(pool),
            'resolved_vertex_xz_m': vertex_xz.tolist(),
            'prepared_paths': {'cells': paths, 'points_xz': coords},
            'service_mouth_candidates': services,
            'rules': 'fan-constrained connected ocean front; recursively divided angular service areas; binary equal split'}
