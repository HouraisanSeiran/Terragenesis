from copy import deepcopy
from dataclasses import replace

import numpy as np

from . import coastal_delta_branching as branching
from .coastal_delta_hydraulics import solve
from .coastal_delta_graph_hydraulics import HydraulicNumericalError
from .coastal_delta_node_inventory import ChannelInventory
from .coastal_delta_routes import node_control_length, route_metrics
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from .coastal_delta_geological_network import _footprint
from terrain_pipeline.channel_geometry import formative_section
from terrain_pipeline.channel_geometry import turn_allowed

_FIELDS = ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')


def _crosses(a, b, c, d):
    def orient(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def on(p, q, r):
        return (min(p[0], q[0])-1e-8 <= r[0] <= max(p[0], q[0])+1e-8
                and min(p[1], q[1])-1e-8 <= r[1] <= max(p[1], q[1])+1e-8)
    u, v, w, x = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return ((u*v < 0 and w*x < 0) or
            (abs(u) < 1e-8 and on(a, b, c)) or (abs(v) < 1e-8 and on(a, b, d)) or
            (abs(w) < 1e-8 and on(c, d, a)) or (abs(x) < 1e-8 and on(c, d, b)))


def _illegal_intersection(a, b, c, d, positions):
    """Allow a common endpoint, but not a shared or overlapping segment."""
    common = {a, b} & {c, d}
    if not common:
        return _crosses(positions[a], positions[b], positions[c], positions[d])
    if len(common) == 2:
        return True
    node = next(iter(common))
    first = np.asarray(positions[b if a == node else a]) - positions[node]
    second = np.asarray(positions[d if c == node else c]) - positions[node]
    cross = first[0]*second[1] - first[1]*second[0]
    return abs(cross) < 1e-8 and float(np.dot(first, second)) > 0


def attach_multicell_branch(state, progress, *, parent_index, fork_index, path_zx,
                            path_xz_m, hydraulic_config, sea_level_m=0.,
                            max_cut_m=.5, design_fraction=.5, rejoin_index=None):
    """Trial an explicitly supplied irregular mesh arm; return state, progress, report.

    Failure returns the original objects. The supplied arm starts at the fork;
    Its interior vertices must be unoccupied mesh vertices. With rejoin_index,
    the final vertex is the indicated downstream parent node and the existing
    downstream route and inventory are shared. Width is limited by actual
    remaining ownership area, not the nominal design width.
    """
    def fail(reason):
        return state, progress, {'attached': False, 'reason': reason}

    try:
        branching._validate(state, progress)
        if not np.isfinite([sea_level_m, max_cut_m, design_fraction]).all() or max_cut_m < 0 or not 0 < design_fraction < 1:
            return fail('invalid attachment settings')
        routes = progress['routes']
        if (not isinstance(parent_index, (int, np.integer)) or not 0 <= parent_index < len(routes)
                or not isinstance(fork_index, (int, np.integer)) or not 0 <= fork_index < len(routes[parent_index])-1):
            return fail('invalid parent or fork index')
        parent = routes[parent_index]
        fork = tuple(parent[fork_index])
        graph_backend = progress.get('hydraulics_backend') == 'physical_edge_graph'
        if not graph_backend and any(fork in map(tuple, route) for i, route in enumerate(routes) if i != parent_index):
            return fail('fork must lie on the exclusive parent leaf segment')
        raw = np.asarray(path_zx)
        xy = np.asarray(path_xz_m, dtype=float)
        if (raw.ndim != 2 or raw.shape[1] != 2 or len(raw) < 2 or xy.shape != raw.shape
                or not np.isfinite(raw.astype(float)).all() or not np.isfinite(xy).all()
                or not np.equal(raw, np.floor(raw.astype(float))).all()):
            return fail('invalid path geometry')
        path = raw.astype(int)
        cells = [tuple(map(int, c)) for c in path]
        if (cells[0] != fork or len(set(cells)) != len(cells)
                or np.any(path < 0) or np.any(path[:, 0] >= state.bed_m.shape[0])
                or np.any(path[:, 1] >= state.bed_m.shape[1])
                or not state.valid_mask[tuple(path.T)].all()):
            return fail('invalid path prefix, cells or domain')
        occupied_nodes = {tuple(c) for route in routes for c in route}
        rejoin = rejoin_index is not None
        if rejoin and (not isinstance(rejoin_index, (int, np.integer))
                       or not fork_index < rejoin_index < len(parent)
                       or cells[-1] != tuple(parent[rejoin_index])):
            return fail('invalid downstream rejoin')
        new_cells = cells[1:-1] if rejoin else cells[1:]
        if not new_cells or any(c in occupied_nodes for c in new_cells) or (not rejoin and cells[-1] in occupied_nodes):
            return fail('path intersects existing network')
        geometry = progress['route_geometry']
        mesh = grid_mesh(state.bed_m.shape, x0_m=state.origin_xz_m[0], z0_m=state.origin_xz_m[1],
                         dx_m=state.spacing_m, world_seed=geometry['seed'])
        ids = np.ravel_multi_index(path.T, state.bed_m.shape)
        expected = np.column_stack((mesh.node_x_m[ids], mesh.node_z_m[ids]))
        if (not np.allclose(xy, expected, rtol=0, atol=1e-8)
                or any(b not in mesh.indices[mesh.indptr[a]:mesh.indptr[a+1]] for a, b in zip(ids, ids[1:]))):
            return fail('path is not valid irregular mesh geometry')
        saved_xy = next(row[2:] for row in geometry['nodes'] if tuple(row[:2]) == fork)
        if not np.allclose(xy[0], saved_xy, rtol=0, atol=1e-8):
            return fail('fork coordinates differ from existing geometry')
        positions = {tuple(row[:2]): row[2:] for row in geometry['nodes']}
        if rejoin and not np.allclose(xy[-1], positions[cells[-1]], rtol=0, atol=1e-8):
            return fail('rejoin coordinates differ from existing geometry')
        edges = [(tuple(row[:2]), tuple(row[2:])) for row in geometry['edges']]
        trial_positions = dict(positions)
        trial_positions.update({cell: point for cell, point in zip(cells, xy)})
        for i, (a, b) in enumerate(zip(cells, cells[1:])):
            for c, d in edges:
                if _illegal_intersection(a, b, c, d, trial_positions):
                    return fail('path crosses existing network')
            for j in range(i-1):
                if _crosses(xy[i], xy[i+1], xy[j], xy[j+1]):
                    return fail('path crosses itself')
        dynamic = progress.get('dynamic_plan') if graph_backend else None
        policy = dynamic['config'] if dynamic else {}
        if dynamic:
            from .coastal_delta_network_plan import _dynamic_policy_identity, _shared_upstream_prefix
            if _shared_upstream_prefix(routes, parent_index, fork_index):
                return fail('dynamic fork lies on existing child upstream prefix')
            if dynamic.get('policy_identity') != _dynamic_policy_identity(state, progress, policy, hydraulic_config, sea_level_m):
                return fail('dynamic policy identity differs')
        new_edges = set(zip(cells, cells[1:]))
        combined_edges = set(edges) | new_edges
        for a, b in combined_edges:
            for c, d in combined_edges:
                if b != c or ((a, b) not in new_edges and (c, d) not in new_edges):
                    continue
                if not turn_allowed(np.asarray(trial_positions[b])-trial_positions[a],
                                    np.asarray(trial_positions[d])-trial_positions[c]):
                    return fail(f'river turn reaches or exceeds 90 degrees at {b}')
        plan = progress.get('hierarchical_plan')
        if dynamic and (not plan or plan.get('config') != policy or max_cut_m > policy['max_cut_m']):
            return fail('dynamic policy identity or cut limit differs')
        if plan:
            cfg = plan.get('config', {})
            if ((not rejoin and len({tuple(r[-1]) for r in routes}) >= cfg.get('max_mouths', float('inf')))
                    or plan['route_depths'][parent_index] >= cfg.get('max_depth', float('inf'))
                    or plan['side_branch_counts'][parent_index] >= cfg.get('max_side_branches', float('inf'))
                    or min(design_fraction, 1-design_fraction) < cfg.get('min_fraction', 0)
                    or (not dynamic and progress['discharge_m3_s']*progress['shares'][parent_index]*min(design_fraction, 1-design_fraction) < cfg.get('min_design_q_m3_s', 0))):
                return fail('hierarchical plan limits exceeded')
        ChannelInventory(state, progress)
        p = deepcopy(progress)
        occupied = np.zeros(state.bed_m.shape)
        stocks = {f: np.zeros_like(occupied) for f in _FIELDS}
        for _, _, parts in p['node_footprints']:
            for r, c, fraction, *amounts in parts:
                occupied[r, c] += fraction
                for field, amount in zip(_FIELDS, amounts):
                    stocks[field][r, c] += amount
        free = np.maximum(0., 1-occupied)
        outer = {f: np.maximum(0., getattr(state, f)-stocks[f]) for f in _FIELDS}
        section = next(row for row in p['hydraulic_sections']['nodes'] if tuple(row[:2]) == fork)
        params = p.get('geological_network', {}).get('width_parameters', {})
        design_q = p['discharge_m3_s'] * p['shares'][parent_index] * design_fraction
        if dynamic:
            before = solve(state, progress, sea_level_m, hydraulic_config)
            physical_q = {tuple(row[:4]): row[4] for row in before['edge_q_m3_s']}
            parent_q = physical_q.get((*fork, *parent[fork_index+1]), 0.)
            if parent_q < 2*policy['min_actual_child_q_m3_s']:
                return fail('actual parent flow below two-arm minimum')
            design_q = parent_q*design_fraction
        nominal_width = float(formative_section(
            design_q, params.get('bed_resistance', .5), params.get('bank_resistance', .5),
            params.get('fracture', 0.), params.get('bank_cohesion', .5),
            reference_discharge_m3_s=params.get('reference_q_m3_s', p['discharge_m3_s']),
            reference_width_m=params.get('reference_width_m', section[3]),
            max_width_m=params.get('max_width_m', max(section[3], 1.))).width_m)
        widths_by_node = {cell: nominal_width for cell in cells}
        targets = {cell: float(state.bed_m[cell]) for cell in cells}
        subdivisions = p.get('geological_network', {}).get('footprint_subdivisions', 8)
        ordered, _, _, _, _, _, footprints = _footprint(
            state, state.valid_mask, [cells], [xy], widths_by_node, targets, subdivisions)
        candidates = {node: parts for node, parts in zip(ordered, footprints) if node in new_cells}
        requested = np.zeros_like(free)
        for parts in candidates.values():
            for r, c, fraction, _ in parts:
                requested[r, c] += fraction
        bed_grid = state.bed_solid_m3.copy()
        mobile_grid = state.mobile_solid_m3.copy()
        cut_total = 0.
        owners = {tuple(row[:2]): row for row in p['integrated']['owner_cells']}
        for cell in new_cells:
            parts = []
            for r, c, wanted, _ in candidates[cell]:
                fraction = wanted * min(1., free[r, c] / requested[r, c])
                if fraction <= 1e-12:
                    continue
                amounts = [float(outer[f][r, c] * fraction / free[r, c]) for f in _FIELDS]
                area_solid = fraction * state.spacing_m**2 * (1-state.porosity[r, c])
                cut = min(amounts[0], max_cut_m * area_solid)
                amounts[0] -= cut
                amounts[1] += cut
                bed_grid[r, c] -= cut
                mobile_grid[r, c] += cut
                cut_total += cut
                parts.append([r, c, fraction, *amounts])
                owner = owners.get((r, c))
                if owner is None:
                    base = float(state.base_bed_m[r, c])
                    owner = [r, c, 0., 0., 0., 0., base, base, 0.]
                    p['integrated']['owner_cells'].append(owner)
                    owners[r, c] = owner
                owner[2] += fraction
                for i, amount in enumerate(amounts):
                    owner[3+i] += amount
            if not parts:
                return fail('path has no unowned corridor area')
            p['node_footprints'].append([*cell, parts])
            # The grid mean may include an existing neighbouring channel cut.
            # A new arm owns only the previously unowned parts: their actual
            # pre-cut sediment surface is its bank reference.
            bank_area = sum(part[2] for part in parts)
            bank = sum(part[2] * (state.base_bed_m[part[0], part[1]] +
                outer['bed_solid_m3'][part[0], part[1]] /
                (free[part[0], part[1]] * state.spacing_m**2 *
                 (1-state.porosity[part[0], part[1]]))) for part in parts) / bank_area
            p['hydraulic_sections']['nodes'].append([*cell, float(state.bed_m[cell]), nominal_width, float(bank)])
        trial_state = replace(state, bed_solid_m3=bed_grid, mobile_solid_m3=mobile_grid)
        suffix = deepcopy(parent[rejoin_index+1:]) if rejoin else []
        p['routes'].append(deepcopy(parent[:fork_index+1])+path[1:].tolist()+suffix)
        share = p['shares'][parent_index]*design_fraction
        p['shares'][parent_index] -= share
        p['shares'].append(share)
        geometry = p['route_geometry']
        geometry['nodes'].extend([[*cell, *map(float, point)] for cell, point in zip(cells[1:], xy[1:]) if cell in new_cells])
        geometry['edges'].extend([[*a, *b] for a, b in zip(cells, cells[1:])])
        if plan:
            plan = p['hierarchical_plan']
            plan['forks'].append([parent_index, fork_index, list(cells[-1])])
            plan['route_depths'][parent_index] += 1
            plan['route_depths'].append(plan['route_depths'][parent_index])
            plan['side_branch_counts'][parent_index] += 1
            plan['side_branch_counts'].append(0)
            plan['route_shares'] = list(p['shares'])
            plan['design_q_m3_s'] = [p['discharge_m3_s']*s for s in p['shares']]
            if 'prepared_paths' in plan:
                plan.setdefault('initial_prepared_paths', plan.pop('prepared_paths'))
            nodes_xy = {tuple(row[:2]): row[2:] for row in geometry['nodes']}
            plan['current_paths'] = {'cells': deepcopy(p['routes']), 'points_xz': [[nodes_xy[tuple(c)] for c in route] for route in p['routes']]}
        fixed = p.setdefault('fixed_channel_footprint', {})
        fixed['design_route_shares'] = list(p['shares'])
        node_q = {tuple(c) for route in p['routes'] for c in route}
        fixed['node_design_q_m3_s'] = [[*c, p['discharge_m3_s']*sum(s for route, s in zip(p['routes'], p['shares']) if list(c) in route)] for c in sorted(node_q)]
        if 'geological_network' in p:
            p['geological_network']['design_route_shares'] = list(p['shares'])
            p['geological_network']['node_design_q_m3_s'] = deepcopy(fixed['node_design_q_m3_s'])
        pool = ChannelInventory(trial_state, p)
        metrics = route_metrics(p, state.spacing_m)
        design = fixed.setdefault('design_width_m', {})
        widths = []
        for node in p['hydraulic_sections']['nodes']:
            key = tuple(node[:2])
            reference = design.setdefault(str(key), node[3])
            node[3] = min(reference, pool.area(key)/node_control_length(p, key, state.spacing_m, metrics))
            if key in new_cells:
                widths.append(node[3])
        main_widths = p['integrated']['sections']['section_width_m']
        for i, node in enumerate(p['hydraulic_sections']['nodes'][:len(main_widths)]):
            main_widths[i] = node[3]
        trial_state, p = pool.commit(trial_state, p)
        if not branching.mouth_exterior_faces(trial_state, p, sea_level_m=sea_level_m)[-1]:
            return fail('new mouth has no actual exterior ocean face')
        solution = solve(trial_state, p, sea_level_m, hydraulic_config)
        if solution['accepted_q_m3_s'] <= 0:
            return fail('network has no available hydraulic flow')
        actual_arm = None
        if graph_backend:
            edge_q = {tuple(row[:4]): float(row[4]) for row in solution['edge_q_m3_s']}
            wet = {tuple(row[:2]): float(row[3]) for row in solution['nodes']}
            minimum_q = policy.get('min_actual_child_q_m3_s', p['discharge_m3_s']*1e-7)
            minimum_width = policy.get('min_effective_width_m', 0.)
            arm_q = [edge_q.get((*a, *b), 0.) for a, b in zip(cells, cells[1:])]
            retained = tuple(parent[fork_index+1])
            retained_q = edge_q.get((*fork, *retained), 0.)
            effective = {tuple(row[:2]): row[3] for row in p['hydraulic_sections']['nodes']}
            if (not arm_q or min(arm_q) < minimum_q or any(wet.get(c, 0.) <= 0 for c in cells)):
                return fail('new arm lacks continuous actual wet flow')
            if dynamic and (retained_q < minimum_q or wet.get(retained, 0.) <= 0):
                return fail(f'retained parent arm lacks actual wet flow: q={retained_q:.9g}, minimum={minimum_q:.9g}')
            if any(effective[c] < minimum_width for c in new_cells) or (dynamic and effective[retained] < minimum_width):
                return fail('actual effective owned width below minimum')
            actual_arm = {'min_new_edge_q_m3_s': min(arm_q), 'retained_parent_q_m3_s': retained_q,
                          'min_new_effective_width_m': min(effective[c] for c in new_cells)}
        p['river_hydraulics'] = solution
        p['actual_shares'] = solution['actual_shares']
        p['active'] = solution['active']
        p['segments'] = branching.segment_fluxes(p)
        if 'control_references' in p:
            p['control_references'].append(branching._control_reference(trial_state, p['routes'][-1]))
        report = {'attached': True, 'reason': 'attached', 'route_index': len(p['routes'])-1,
                  'widths_m': widths, 'nominal_width_m': nominal_width, 'solid_cut_m3': float(cut_total),
                  'path_zx': path.tolist(), 'path_xz_m': xy.tolist(), 'rejoin_index': rejoin_index,
                  'parent_index': int(parent_index), 'fork_index': int(fork_index),
                  'fork_zx': list(fork), 'rejoin_zx': list(cells[-1]) if rejoin else None,
                  'actual_arm': actual_arm}
        if dynamic:
            p['dynamic_plan']['lineage'].append({'route_index': len(p['routes'])-1,
                'parent_index': int(parent_index), 'fork_index': int(fork_index),
                'fork_zx': list(fork), 'rejoin_index': rejoin_index, 'source': 'attachment'})
        p['history'].append({'event': 'branch_attachment', **deepcopy(report)})
        return branching._record(trial_state, p), p, report
    except (ValueError, ArithmeticError, KeyError, StopIteration, TypeError, IndexError, HydraulicNumericalError) as exc:
        return fail(f'attachment rejected: {exc}')
