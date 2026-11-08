"""Quasi-steady rectangular-channel stages on a shared distributary DAG.

Manning friction and critical-depth controls are engineering approximations;
no floodplain storage, momentum balance or calibrated cross sections are solved.
"""
from dataclasses import dataclass, asdict
import math
import networkx as nx
import numpy as np
from .coastal_delta_product import _width


@dataclass(frozen=True)
class HydraulicConfig:
    upstream_stage_limit_m: float
    roughness: float = .035
    gravity_m_s2: float = 9.81


def solve(state, progress, sea_level_m, config):
    if 'hydraulic_sections' in progress:
        return solve_sections(state, progress, sea_level_m, config)
    from .coastal_delta_branching import mouth_exterior_faces, _allocate_route_shares
    if not np.isfinite([sea_level_m, config.upstream_stage_limit_m, config.roughness,
                        config.gravity_m_s2]).all() or min(config.roughness, config.gravity_m_s2) <= 0:
        raise ValueError('invalid hydraulic boundary or parameters')
    routes = [[tuple(c) for c in route] for route in progress['routes']]
    faces = mouth_exterior_faces(state, progress, sea_level_m=sea_level_m)
    # A crest at or above the available upstream stage cannot pass any
    # positive discharge; remove that branch before redistributing its share.
    eligible = [bool(face) and all(state.bed_m[cell] < config.upstream_stage_limit_m for cell in route)
                for route, face in zip(routes, faces)]
    planned = np.asarray(progress['shares'], float)
    if all(eligible):
        # Retain the original arithmetic when no route is blocked, so existing
        # all-active event checkpoints remain bit-for-bit reproducible.
        shares = np.where(eligible, planned, 0.)
        if shares.sum() > 0:
            shares /= shares.sum()
    else:
        shares = np.asarray(_allocate_route_shares(routes, planned, eligible))
    graph = nx.DiGraph()
    for route, share in zip(routes, shares):
        if share > 0:
            nx.add_path(graph, route)
    if graph and not nx.is_directed_acyclic_graph(graph):
        raise ValueError('river routes must form a DAG')
    bed = state.bed_m
    order = list(nx.topological_sort(graph))
    def stages_for(q):
        edge_q = {}
        node_q = {}
        outlet_q = {}
        for route, share in zip(routes, shares):
            if share <= 0:
                continue
            flow = q * share
            for cell in route:
                node_q[cell] = node_q.get(cell, 0.) + flow
            for a, b in zip(route, route[1:]):
                edge_q[a,b] = edge_q.get((a,b), 0.) + flow
            outlet_q[route[-1]] = outlet_q.get(route[-1], 0.) + flow
        stage = {}
        for cell in reversed(order):
            total = node_q[cell]
            width = _width(total, 0., 0.)
            critical = (total / width / math.sqrt(config.gravity_m_s2))**(2/3)
            constraints = [(stage[b], edge_q[cell,b], state.spacing_m) for b in graph.successors(cell)]
            if cell in outlet_q:
                constraints.append((sea_level_m, outlet_q[cell], state.spacing_m/2))
            def needed(level):
                depth = max(level-bed[cell], 1e-12)
                radius = width*depth/(width+2*depth)
                return max((down + length*(flow*config.roughness/(width*depth*radius**(2/3)))**2
                            for down,flow,length in constraints), default=-math.inf)
            low = float(bed[cell]+critical)
            high = max(low, sea_level_m, *(stage[b] for b in graph.successors(cell))) + 1.
            while high < needed(high):
                high = bed[cell]+2*(high-bed[cell])+1.
                if high > 1e7:
                    raise ValueError('hydraulic stage unresolved')
            for _ in range(35):
                mid = (low+high)/2
                if mid >= needed(mid): high = mid
                else: low = mid
            stage[cell] = high
        return stage, node_q
    accepted = 0.
    stages, flows = {}, {}
    if order:
        total = float(progress['discharge_m3_s'])
        inlet = routes[0][0]
        trial, node_q = stages_for(total)
        if trial[inlet] <= config.upstream_stage_limit_m:
            accepted, stages, flows = total, trial, node_q
        else:
            lo, hi = 0., total
            for _ in range(26):
                mid = (lo+hi)/2
                trial, node_q = stages_for(mid)
                if trial[inlet] <= config.upstream_stage_limit_m:
                    lo = mid; stages, flows = trial, node_q
                else: hi = mid
            accepted = lo
            if accepted <= total*1e-7:
                accepted, stages, flows = 0., {}, {}
    actual = [float(x*accepted/progress['discharge_m3_s']) for x in shares]
    return {'algorithm': 'river-stage-v1', 'parameters': asdict(config), 'sea_level_m': float(sea_level_m),
            'accepted_q_m3_s': accepted, 'rejected_q_m3_s': progress['discharge_m3_s']-accepted,
            'route_q_m3_s': [float(accepted*x) for x in shares], 'actual_shares': actual,
            'active': [bool(x and accepted > 0) for x in eligible],
            'nodes': [[*cell, float(stages[cell]), float(stages[cell]-bed[cell]), float(flows[cell])]
                      for cell in order if cell in stages], 'exterior_faces': faces}


def solve_sections(state, progress, sea_level_m, config):
    """Solve explicit rectangular sections with local, iterated fork resistance."""
    from .coastal_delta_branching import mouth_exterior_faces

    if not np.isfinite([sea_level_m, config.upstream_stage_limit_m, config.roughness,
                        config.gravity_m_s2, state.spacing_m]).all() or min(
                            config.roughness, config.gravity_m_s2, state.spacing_m) <= 0:
        raise ValueError('invalid hydraulic boundary or parameters')
    sections = {}
    for row in progress['hydraulic_sections']['nodes']:
        if len(row) not in (5, 6) or not np.isfinite(row).all():
            raise ValueError('invalid hydraulic section')
        z, x, bed, width, bank = row[:5]
        roughness = row[5] if len(row) == 6 else config.roughness
        if (int(z) != z or int(x) != x or not (0 <= z < state.bed_m.shape[0])
                or not (0 <= x < state.bed_m.shape[1]) or width <= 0
                or roughness <= 0 or bank < bed or (int(z), int(x)) in sections):
            raise ValueError('invalid hydraulic section')
        sections[int(z), int(x)] = (float(bed), float(width), float(roughness))
    routes = [[tuple(c) for c in route] for route in progress['routes']]
    total = float(progress['discharge_m3_s'])
    if not np.isfinite(total) or total <= 0 or not routes or any(not r for r in routes):
        raise ValueError('invalid river routes or discharge')
    if any(route[0] != routes[0][0] or len(set(route)) != len(route) for route in routes):
        raise ValueError('river routes must share an inlet and have no loops')
    faces = mouth_exterior_faces(state, progress, sea_level_m=sea_level_m)
    eligible = [bool(face) and all(c in sections and sections[c][0] < config.upstream_stage_limit_m
                                   for c in route) for route, face in zip(routes, faces)]
    graph = nx.DiGraph()
    for route, live in zip(routes, eligible):
        if live:
            nx.add_path(graph, route)
    if graph and not nx.is_directed_acyclic_graph(graph):
        raise ValueError('river routes must form a DAG')
    # Rejoining routes need a flow-routing model rather than a prefix tree.
    if any(graph.in_degree(c) > 1 for c in graph):
        raise ValueError('section routes must not rejoin after a fork')
    order = list(nx.topological_sort(graph))

    def allocate(stage, previous):
        shares = [0.] * len(routes)
        def visit(indices, depth, fraction):
            live = [i for i in indices if eligible[i]]
            if not live:
                return
            groups = {}
            for i in live:
                key = routes[i][depth] if depth < len(routes[i]) else None
                groups.setdefault(key, []).append(i)
            if len(groups) == 1:
                if next(iter(groups)) is None:
                    for i in live:
                        shares[i] += fraction / len(live)
                else:
                    visit(live, depth + 1, fraction)
                return
            weights = []
            for key, group in groups.items():
                if key is None:
                    weights.append(1.)
                    continue
                # Measure this arm only until its next fork, so a separate
                # downstream fork cannot globally amplify another arm.
                end = depth
                while all(end < len(routes[i]) and routes[i][end] == routes[group[0]][end]
                          for i in group):
                    end += 1
                cells = routes[group[0]][depth:end]
                # A common reference discharge keeps this fork's weights
                # independent of allocations at other forks.
                q = total
                resistance = 0.
                for cell in cells:
                    bed, width, rough = sections[cell]
                    critical = (q / width / math.sqrt(config.gravity_m_s2)) ** (2/3)
                    d = max(sea_level_m - bed, critical, .05)
                    radius = width * d / (width + 2*d)
                    resistance += state.spacing_m * (rough / (width*d*radius**(2/3)))**2
                weights.append(1 / math.sqrt(max(resistance, 1e-30)))
            weight_sum = sum(weights)
            for group, weight in zip(groups.values(), weights):
                visit(group, depth + 1, fraction * weight / weight_sum)
        visit(list(range(len(routes))), 0, 1.)
        return shares

    def stages_for(q, shares):
        edges, flows, outlets = {}, {}, {}
        for route, share in zip(routes, shares):
            if share <= 0:
                continue
            flow = q * share
            for cell in route:
                flows[cell] = flows.get(cell, 0.) + flow
            for a, b in zip(route, route[1:]):
                edges[a, b] = edges.get((a, b), 0.) + flow
            outlets[route[-1]] = outlets.get(route[-1], 0.) + flow
        stages = {}
        for cell in reversed(order):
            bed, width, rough = sections[cell]
            critical = (flows[cell] / width / math.sqrt(config.gravity_m_s2)) ** (2/3)
            constraints = [(stages[b], edges[cell, b], state.spacing_m)
                           for b in graph.successors(cell)]
            if cell in outlets:
                constraints.append((sea_level_m, outlets[cell], state.spacing_m / 2))
            def needed(level):
                depth = max(level-bed, 1e-12)
                radius = width*depth/(width+2*depth)
                return max((down + length*(flow*rough/(width*depth*radius**(2/3)))**2
                            for down, flow, length in constraints), default=-math.inf)
            low = bed + critical
            high = max(low, sea_level_m, *(stages[b] for b in graph.successors(cell))) + 1.
            while high < needed(high):
                high = bed + 2*(high-bed) + 1.
                if high > 1e7:
                    raise ValueError('hydraulic stage unresolved')
            for _ in range(35):
                mid = (low + high)/2
                if mid >= needed(mid):
                    high = mid
                else:
                    low = mid
            stages[cell] = high
        return stages, flows

    shares = [1 / sum(eligible) if live else 0. for live in eligible] if any(eligible) else [0.] * len(routes)
    stages, flows = {}, {}
    if order:
        for _ in range(16):
            stages, flows = stages_for(total, shares)
            proposed = allocate(stages, shares)
            shares = [(a+b)/2 for a, b in zip(shares, proposed)]
        stages, flows = stages_for(total, shares)
    accepted = 0.
    if order and stages[routes[0][0]] <= config.upstream_stage_limit_m:
        accepted = total
    elif order:
        lo, hi = 0., total
        stages, flows = {}, {}
        for _ in range(26):
            mid = (lo+hi)/2
            trial, node_q = stages_for(mid, shares)
            if trial[routes[0][0]] <= config.upstream_stage_limit_m:
                lo, stages, flows = mid, trial, node_q
            else:
                hi = mid
        accepted = lo
        if accepted <= total*1e-7:
            accepted, stages, flows = 0., {}, {}
    return {'algorithm': 'river-sections-v1', 'parameters': asdict(config),
            'sea_level_m': float(sea_level_m), 'accepted_q_m3_s': accepted,
            'rejected_q_m3_s': total-accepted,
            'route_q_m3_s': [float(accepted*s) for s in shares],
            'actual_shares': [float(s*accepted/total) for s in shares],
            'active': [bool(s > 0 and accepted > 0) for s in shares],
            'nodes': [[*cell, float(stages[cell]), float(stages[cell]-sections[cell][0]),
                       float(flows[cell])] for cell in order if cell in stages],
            'exterior_faces': faces}
