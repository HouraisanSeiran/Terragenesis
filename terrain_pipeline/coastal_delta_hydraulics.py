"""Quasi-steady rectangular-channel stages on a shared distributary DAG.

Manning friction and critical-depth controls are engineering approximations;
no floodplain storage, momentum balance or calibrated cross sections are solved.
"""
from dataclasses import dataclass, asdict
import math
import networkx as nx
import numpy as np
from .coastal_delta_product import _width
from .coastal_delta_routes import edge_length, route_metrics


@dataclass(frozen=True)
class HydraulicConfig:
    upstream_stage_limit_m: float
    roughness: float = .035
    gravity_m_s2: float = 9.81


def solve(state, progress, sea_level_m, config):
    if 'hydraulic_sections' in progress:
        return solve_sections(state, progress, sea_level_m, config)
    if progress.get('hydraulics_backend') == 'physical_edge_graph':
        raise ValueError('physical_edge_graph requires explicit hydraulic sections')
    from .coastal_delta_branching import mouth_exterior_faces, _allocate_route_shares
    if not np.isfinite([sea_level_m, config.upstream_stage_limit_m, config.roughness,
                        config.gravity_m_s2]).all() or min(config.roughness, config.gravity_m_s2) <= 0:
        raise ValueError('invalid hydraulic boundary or parameters')
    routes = [[tuple(c) for c in route] for route in progress['routes']]
    metrics = route_metrics(progress, state.spacing_m)
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
            constraints = [(stage[b], edge_q[cell,b], edge_length(progress, cell, b, state.spacing_m, metrics)) for b in graph.successors(cell)]
            if cell in outlet_q:
                # The ocean exchange is a separate half-cell face, not a mesh edge.
                constraints.append((sea_level_m, outlet_q[cell],
                    progress['route_geometry']['exchange_face_distance_m'] if metrics is not None else state.spacing_m/2))
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
    """Solve effective-width rectangular conveyance and report historical bank status.

    The bank remains the original floodplain elevation when a bed aggrades above
    it. A filled section conveys water over its owned footprint as an effective
    rectangular sheet; it is not a confined channel. Lateral exchange is handled
    separately by the multicell floodplain consumer, without adding conveyance
    from unowned land or assuming floodplain storage.
    """
    from .coastal_delta_branching import mouth_exterior_faces

    if not np.isfinite([sea_level_m, config.upstream_stage_limit_m, config.roughness,
                        config.gravity_m_s2, state.spacing_m]).all() or min(
                            config.roughness, config.gravity_m_s2, state.spacing_m) <= 0:
        raise ValueError('invalid hydraulic boundary or parameters')
    sections = {}
    shape = state.base_bed_m.shape
    for row in progress['hydraulic_sections']['nodes']:
        if len(row) not in (5, 6) or not np.isfinite(row).all():
            raise ValueError('invalid hydraulic section')
        z, x, bed, width, bank = row[:5]
        roughness = row[5] if len(row) == 6 else config.roughness
        if (int(z) != z or int(x) != x or not (0 <= z < shape[0])
                or not (0 <= x < shape[1]) or width <= 0
                or roughness <= 0 or (int(z), int(x)) in sections):
            raise ValueError('invalid hydraulic section')
        sections[int(z), int(x)] = (float(bed), float(width), float(roughness))
    routes = [[tuple(c) for c in route] for route in progress['routes']]
    metrics = route_metrics(progress, state.spacing_m)
    total = float(progress['discharge_m3_s'])
    if not np.isfinite(total) or total <= 0 or not routes or any(not r for r in routes):
        raise ValueError('invalid river routes or discharge')
    if any(route[0] != routes[0][0] or len(set(route)) != len(route) for route in routes):
        raise ValueError('river routes must share an inlet and have no loops')
    faces = mouth_exterior_faces(state, progress, sea_level_m=sea_level_m)
    if progress.get('hydraulics_backend') == 'physical_edge_graph':
        from .coastal_delta_graph_hydraulics import solve_graph
        return solve_graph(state, progress, sea_level_m, config, sections, faces)
    eligible = [bool(face) and all(c in sections and sections[c][0] < config.upstream_stage_limit_m
                                   for c in route) for route, face in zip(routes, faces)]
    graph = nx.DiGraph()
    for route, live in zip(routes, eligible):
        if live:
            nx.add_path(graph, route)
    if graph and not nx.is_directed_acyclic_graph(graph):
        raise ValueError('river routes must form a DAG')
    order = list(nx.topological_sort(graph))

    def stages_for(q, shares):
        edges, flows, outlets = {}, {}, {}
        for route, share, live in zip(routes, shares, eligible):
            if not live:
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
            constraints = [(stages[b], edges[cell, b], edge_length(progress, cell, b, state.spacing_m, metrics))
                           for b in graph.successors(cell)]
            if cell in outlets:
                constraints.append((sea_level_m, outlets[cell], (progress['route_geometry']['exchange_face_distance_m'] if metrics is not None else state.spacing_m / 2)))
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

    # Pairwise flow exchanges equalise the controlling head at each fork.
    # Path flows sum on shared edges and at confluences; thus a common mouth
    # and its downstream reach are counted only once.
    from scipy.optimize import minimize_scalar
    pairs = []
    for i in range(len(routes)):
        for j in range(i + 1, len(routes)):
            if not (eligible[i] and eligible[j]):
                continue
            common = 0
            while (common < min(len(routes[i]), len(routes[j]))
                   and routes[i][common] == routes[j][common]):
                common += 1
            if common:
                pairs.append((i, j, routes[i][common-1]))

    def balanced(q, initial):
        shares = list(initial)
        for _ in range(3):
            change = 0.
            for i, j, fork in pairs:
                available = shares[i] + shares[j]
                if available <= 1e-12:
                    continue
                def head(value):
                    trial = shares.copy()
                    trial[i], trial[j] = value, available-value
                    return stages_for(q, trial)[0][fork]
                result = minimize_scalar(head, bounds=(0., available), method='bounded',
                                         options={'xatol': max(available*1e-5, 1e-8), 'maxiter': 24})
                choices = [(result.fun, result.x), (head(0.), 0.), (head(available), available)]
                value = min(choices)[1]
                change = max(change, abs(value-shares[i]))
                shares[i], shares[j] = value, available-value
            if change < 1e-5:
                break
        stages, flows = stages_for(q, shares)
        return shares, stages, flows

    shares = [1 / sum(eligible) if live else 0. for live in eligible] if any(eligible) else [0.] * len(routes)
    stages, flows = {}, {}
    accepted = 0.
    if order:
        shares, stages, flows = balanced(total, shares)
        if stages[routes[0][0]] <= config.upstream_stage_limit_m:
            accepted = total
        else:
            lo, hi = 0., total
            best = (shares, {}, {})
            for _ in range(20):
                mid = (lo+hi)/2
                candidate, trial, node_q = balanced(mid, shares)
                if trial[routes[0][0]] <= config.upstream_stage_limit_m:
                    lo = mid
                    best = (candidate, trial, node_q)
                else:
                    hi = mid
            accepted = lo
            shares, stages, flows = best
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
            'section_states': [[int(row[0]), int(row[1]),
                                'filled' if row[2] >= row[4] else 'channel',
                                bool(tuple(map(int, row[:2])) in stages and
                                     stages[tuple(map(int, row[:2]))] > row[4])]
                               for row in progress['hydraulic_sections']['nodes']],
            'exterior_faces': faces}
