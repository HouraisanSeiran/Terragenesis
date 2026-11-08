"""Finite DAG stage/flow approximation with one discharge per physical edge."""
from dataclasses import asdict
import networkx as nx
import numpy as np
from scipy.optimize import least_squares
from .coastal_delta_routes import edge_length, route_metrics

SPARSE_NODE_THRESHOLD = 128


class HydraulicNumericalError(RuntimeError):
    """A trial failed the numerical residual criterion, not a dry-flow result."""

    def __init__(self, residual, evaluations):
        self.residual = float(residual)
        self.evaluations = int(evaluations)
        super().__init__(f'graph hydraulic numerical solve failed: residual={residual:.6g}, evaluations={evaluations}')


def _lateral_exchange(progress, active_nodes):
    """Validate explicit node exchanges; sink fractions use accepted inlet Q."""
    exchange = progress['river_lateral_exchange']
    if not isinstance(exchange, dict) or set(exchange) - {'sink_fraction', 'source_q_m3_s'}:
        raise ValueError('invalid river lateral exchange')
    values = []
    for field in ('sink_fraction', 'source_q_m3_s'):
        rows = exchange.get(field, [])
        if not isinstance(rows, (list, tuple)):
            raise ValueError('invalid river lateral exchange rows')
        nodes = {}
        for row in rows:
            try:
                data = np.asarray(row, dtype=float)
                if (data.shape != (3,) or not np.isfinite(data).all()
                        or any(int(v) != v for v in data[:2]) or data[2] < 0):
                    raise ValueError
                node = tuple(map(int, data[:2]))
            except (TypeError, ValueError, OverflowError):
                raise ValueError('invalid river lateral exchange row') from None
            if node in nodes:
                raise ValueError('duplicate river lateral exchange node')
            if node not in active_nodes:
                raise ValueError('river lateral exchange requires a reachable active node')
            nodes[node] = float(data[2])
        values.append(nodes)
    if sum(values[0].values()) > .2 + 1e-12:
        raise ValueError('river lateral sink fractions must sum to at most 0.2')
    if not np.isfinite(sum(values[1].values())):
        raise ValueError('invalid river lateral source total')
    return values


def solve_graph(state, progress, sea_level_m, config, sections, faces):
    if (not np.isfinite([sea_level_m, config.upstream_stage_limit_m, config.roughness]).all()
            or config.roughness <= 0 or len(faces) != len(progress['routes'])):
        raise ValueError('invalid hydraulic boundary, parameters or exterior faces')
    if any(len(v) < 3 or not np.isfinite(v[:3]).all() or v[1] <= 0 or v[2] <= 0
           for v in sections.values()):
        raise ValueError('invalid hydraulic section')
    routes = [[tuple(c) for c in route] for route in progress['routes']]
    total = float(progress['discharge_m3_s'])
    if not np.isfinite(total) or total <= 0 or not routes or any(len(r) < 2 for r in routes):
        raise ValueError('invalid river routes or discharge')
    if any(r[0] != routes[0][0] or len(set(r)) != len(r) for r in routes):
        raise ValueError('river routes must share an inlet and have no loops')
    graph = nx.DiGraph()
    for route in routes:
        nx.add_path(graph, route)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError('river routes must form a DAG')
    all_edges = sorted(graph.edges)
    if set(graph) - set(sections):
        raise ValueError('missing hydraulic sections for graph nodes')
    metrics = route_metrics(progress, state.spacing_m)
    mouths = {route[-1] for route, face in zip(routes, faces) if face}
    allowed = {n for n in graph if n in sections and sections[n][0] < config.upstream_stage_limit_m}
    live = graph.subgraph(allowed).copy()
    mouths &= set(live)
    inlet = routes[0][0]
    reachable = set(nx.descendants(live, inlet)) | {inlet} if inlet in live else set()
    drains = set(mouths)
    for mouth in mouths:
        drains.update(nx.ancestors(live, mouth))
    live = live.subgraph(reachable & drains).copy()
    order = list(nx.lexicographical_topological_sort(live))
    mouths &= set(order)
    if sea_level_m >= config.upstream_stage_limit_m:
        order = []
    has_lateral = 'river_lateral_exchange' in progress
    sink_fraction, source_q = _lateral_exchange(progress, set(order)) if has_lateral else ({}, {})
    lateral_sink_flow = {}
    edge_rows = [[*a, *b, 0.] for a, b in all_edges]
    stages, edge_flow, outlet_flow = {}, {}, {}
    residual = 0.
    evaluations = 0
    equation_residual = 0.
    accepted = 0.
    converged = True
    sparse = False
    if order and inlet in live and mouths:
        index = {n: i for i, n in enumerate(order)}
        edges = sorted(live.edges)
        src = np.array([index[a] for a, b in edges], int)
        dst = np.array([index[b] for a, b in edges], int)
        mi = np.array([index[n] for n in sorted(mouths)], int)
        bed = np.array([sections[n][0] for n in order])
        width = np.array([sections[n][1] for n in order])
        rough = np.array([sections[n][2] for n in order])
        lengths = np.array([edge_length(progress, a, b, state.spacing_m, metrics) for a, b in edges])
        if not np.isfinite(lengths).all() or np.any(lengths <= 0):
            raise ValueError('invalid graph edge length')
        exchange = progress.get('route_geometry', {}).get('exchange_face_distance_m', state.spacing_m/2)
        if not np.isfinite(exchange) or exchange <= 0:
            raise ValueError('invalid exchange length')
        # Solve discharge and stage together. A head-loss complementarity
        # equation remains well behaved when a branch closes: q >= 0 and
        # downstream head + friction loss - upstream head >= 0.
        count = len(edges) + len(mi)
        destinations = np.concatenate((dst, mi))
        sources = np.concatenate((src, mi))
        edge_len = np.concatenate((lengths, np.full(len(mi), exchange)))
        scale_q = max(total, 1.)
        if source_q:
            scale_q = max(scale_q, sum(source_q.values()))
        lateral_fraction = np.array([sink_fraction.get(n, 0.) for n in order])
        lateral_source = np.array([source_q.get(n, 0.) for n in order])
        stage_scale = max(1., float(np.ptp(bed)), abs(float(sea_level_m)))
        def equations(x, demand):
            h = x[:len(order)]
            q = x[len(order):] * scale_q
            depth = np.maximum(h-bed, 1e-8)
            radius = width*depth/(width+2*depth)
            convey = width*depth*np.power(radius, 2/3)/rough
            target = np.concatenate((h[dst], np.full(len(mi), sea_level_m)))
            loss = edge_len * np.square(q / convey[sources])
            slack = (target + loss - h[sources])/stage_scale
            flow = q/scale_q
            complement = np.hypot(flow, slack)-flow-slack
            bal = np.bincount(src, weights=q[:len(edges)], minlength=len(order))-np.bincount(dst, weights=q[:len(edges)], minlength=len(order))
            np.add.at(bal, mi, q[len(edges):])
            bal[index[inlet]] -= demand
            if has_lateral:
                bal += lateral_fraction*demand-lateral_source
            return np.concatenate((bal/scale_q, complement))
        def sparse_jacobian(x, demand):
            from scipy.sparse import coo_matrix
            h=x[:len(order)]
            flow=x[len(order):]
            q=flow*scale_q
            depth=np.maximum(h-bed,1e-8)
            radius=width*depth/(width+2*depth)
            convey=width*depth*np.power(radius,2/3)/rough
            loss=edge_len*np.square(q/convey[sources])
            target=np.concatenate((h[dst],np.full(len(mi),sea_level_m)))
            slack=(target+loss-h[sources])/stage_scale
            norm=np.maximum(np.hypot(flow,slack),1e-30)
            ds=slack/norm-1.
            df=flow/norm-1.
            logarithmic=np.where(h-bed>1e-8,5/(3*depth)-4/(3*(width+2*depth)),0.)
            source_derivative=ds*(-1.-2*loss*logarithmic[sources])/stage_scale
            q_derivative=df+ds*(2*edge_len*flow*np.square(scale_q/convey[sources]))/stage_scale
            n=len(order)
            equation=n+np.arange(count)
            columns=n+np.arange(count)
            rows=np.concatenate((src,dst,mi,equation,equation[:len(edges)],equation))
            cols=np.concatenate((n+np.arange(len(edges)),n+np.arange(len(edges)),
                n+len(edges)+np.arange(len(mi)),sources,dst,columns))
            values=np.concatenate((np.ones(len(edges)),-np.ones(len(edges)),np.ones(len(mi)),
                source_derivative,ds[:len(edges)]/stage_scale,q_derivative))
            return coo_matrix((values,(rows,cols)),shape=(n+count,n+count)).tocsr()
        # A wet initial profile and positive edge flows avoid the singular
        # dry-bed limit; all later capacity decisions use converged solutions.
        initial_h = np.maximum(bed + 1., sea_level_m + 1.)
        initial_h += np.arange(len(order), 0, -1) * .01
        x0 = np.concatenate((initial_h, np.full(count, 1./max(count, 1))))
        lower = np.concatenate((bed + 1e-9, np.zeros(count)))
        upper = np.full(len(order)+count, np.inf)
        sparse = len(order)>=SPARSE_NODE_THRESHOLD
        solver_options = ({'jac':sparse_jacobian,'x_scale':'jac','tr_options':
            {'atol':1e-12,'btol':1e-12,'maxiter':max(1000,len(order)+count)}} if sparse else {})
        previous=progress.get('river_hydraulics',{}) if sparse else {}
        if previous.get('algorithm')=='river-physical-edge-flux-dag-v1':
            previous_h={tuple(row[:2]):row[2] for row in previous.get('nodes',[])}
            previous_q={(tuple(row[:2]),tuple(row[2:4])):row[4] for row in previous.get('edge_q_m3_s',[])}
            previous_m={tuple(row[:2]):row[2] for row in previous.get('mouth_q_m3_s',[])}
            x0=np.array([previous_h.get(node,x0[i]) for i,node in enumerate(order)]+
                [previous_q.get(edge,x0[len(order)+i]*scale_q)/scale_q for i,edge in enumerate(edges)]+
                [previous_m.get(node,x0[len(order)+len(edges)+i]*scale_q)/scale_q for i,node in enumerate(sorted(mouths))])
            x0=np.maximum(x0,lower+1e-12)
        evaluations = 0
        def attempt(demand, guess):
            nonlocal evaluations
            result = least_squares(equations, guess, args=(demand,), bounds=(lower, upper),
                                   xtol=1e-11, ftol=1e-11, gtol=1e-11, max_nfev=600,**solver_options)
            evaluations += result.nfev
            # Lock an edge whose receiving sill is demonstrably above its
            # source stage. This removes the degenerate zero-flow corner.
            for _ in range(3):
                h = result.x[:len(order)]
                closed = np.flatnonzero((result.x[len(order):len(order)+len(edges)] < 2e-4) & (h[src] <= h[dst] + 1e-4))
                if not len(closed):
                    break
                active_graph = live.copy()
                active_graph.remove_edges_from(edges[i] for i in closed)
                wet_reachable = nx.descendants(active_graph, inlet) | {inlet}
                for node, source in source_q.items():
                    if source > 0:
                        wet_reachable.update(nx.descendants(active_graph, node) | {node})
                inactive = [i for i, (a, _) in enumerate(edges) if a not in wet_reachable]
                inactive_mouths = [len(edges) + i for i, n in enumerate(sorted(mouths)) if n not in wet_reachable]
                refined_upper = upper.copy()
                refined_upper[len(order) + np.array(list(closed) + inactive + inactive_mouths, dtype=int)] = 1e-12
                seed = np.minimum(result.x, refined_upper - 1e-14)
                result = least_squares(equations, seed, args=(demand,), bounds=(lower, refined_upper),
                                       xtol=1e-11, ftol=1e-11, gtol=1e-11, max_nfev=600,**solver_options)
                evaluations += result.nfev
                break
            error = float(np.max(np.abs(equations(result.x, demand))))
            if not np.isfinite(error) or error > 1e-4:
                raise HydraulicNumericalError(error, result.nfev)
            return result
        result = attempt(total, x0)
        if result.x[index[inlet]] <= config.upstream_stage_limit_m:
            accepted = total
        else:
            lo, hi = 0., total
            best = None
            guess = result.x
            for _ in range(20):
                mid = (lo+hi)/2
                trial = attempt(mid, guess)
                guess = trial.x
                if trial.x[index[inlet]] <= config.upstream_stage_limit_m:
                    lo, best = mid, trial
                else:
                    hi = mid
            accepted = lo
            if best is not None:
                result = best
            elif any(source_q.values()):
                result = attempt(0., guess)
                if result.x[index[inlet]] > config.upstream_stage_limit_m:
                    raise ValueError('river lateral source exceeds upstream stage limit')
        if accepted > total*1e-7 or any(source_q.values()):
            q = result.x[len(order):len(order)+len(edges)] * scale_q
            qm = result.x[len(order)+len(edges):] * scale_q
            residual = float(np.max(np.abs(equations(result.x, accepted)[:len(order)]))*scale_q)
            equation_residual = float(np.max(np.abs(equations(result.x, accepted))))
            stages = {n: float(result.x[i]) for i, n in enumerate(order)}
            edge_flow = {(a, b): float(v) for (a, b), v in zip(edges, q)}
            outlet_flow = {n: float(v) for n, v in zip(sorted(mouths), qm)}
            edge_rows = [[*a, *b, edge_flow.get((a, b), 0.)] for a, b in all_edges]
            lateral_sink_flow = {n: fraction*accepted for n, fraction in sink_fraction.items()}
        else:
            accepted = 0.
    node_q = {n: sum(edge_flow.get((n, b), 0.) for b in graph.successors(n)) + outlet_flow.get(n, 0.) for n in stages}
    if has_lateral:
        node_q = {n: q+lateral_sink_flow.get(n, 0.) for n, q in node_q.items()}
    # Compatibility values are independent outlet totals, assigned once.
    route_q = []
    assigned = set()
    for route in routes:
        end = route[-1]
        route_q.append(outlet_flow.get(end, 0.) if end not in assigned else 0.)
        assigned.add(end)
    output = {'algorithm': 'river-physical-edge-flux-dag-v1', 'parameters': asdict(config),
            'numerical_linearization': 'analytic sparse Jacobian' if sparse else 'dense finite differences',
            'sea_level_m': float(sea_level_m), 'accepted_q_m3_s': accepted,
            'rejected_q_m3_s': total-accepted, 'edge_q_m3_s': edge_rows,
            'mouth_q_m3_s': [[*n, q] for n, q in sorted(outlet_flow.items())],
            'route_q_m3_s': route_q, 'route_q_semantics': 'independent mouth totals assigned once; not path flux',
            'actual_shares': [q/total for q in route_q],
            'active': [all(edge_flow.get((a, b), 0.) > total*1e-7 for a, b in zip(r, r[1:]))
                       and outlet_flow.get(r[-1], 0.) > total*1e-7 for r in routes],
            'active_semantics': 'all physical route edges and its mouth convey positive flow; route_q is not route activity',
            'nodes': [[*n, stages[n], max(0., stages[n]-sections[n][0]), node_q[n]] for n in order if n in stages],
            'section_states': [[int(row[0]), int(row[1]), 'filled' if row[2] >= row[4] else 'channel',
                                bool(tuple(map(int, row[:2])) in stages and stages[tuple(map(int, row[:2]))] > row[4])]
                               for row in progress['hydraulic_sections']['nodes']],
            'exterior_faces': faces, 'max_node_residual_m3_s': residual,
            'max_scaled_equation_residual': equation_residual, 'converged': converged, 'physical_blocked': not bool(order and inlet in live and mouths), 'function_evaluations': evaluations}
    if has_lateral:
        output.update(lateral_sink_q_m3_s=[[*n, sink_fraction[n]*accepted] for n in sorted(sink_fraction)],
                      lateral_source_q_m3_s=[[*n, source_q[n]] for n in sorted(source_q)],
                      lateral_water_balance_residual_m3_s=float(
                          sum(outlet_flow.values())+sum(sink_fraction.values())*accepted
                          -accepted-sum(source_q.values())))
    return output

