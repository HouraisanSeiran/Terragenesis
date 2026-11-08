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
