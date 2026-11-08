"""Metric heading checks and edge-state search for river paths."""
import heapq

import numpy as np


def turn_allowed(incoming, outgoing, max_turn_deg=90.):
    """Zero is straight ahead; the maximum angle is excluded."""
    incoming, outgoing = np.asarray(incoming, float), np.asarray(outgoing, float)
    scale = np.linalg.norm(incoming) * np.linalg.norm(outgoing)
    return bool(scale > 0 and incoming @ outgoing >
                scale * (np.cos(np.radians(max_turn_deg)) + 1e-12))


def turn_penalty(incoming, outgoing, k=1.):
    """0 through 45 degrees, k*(theta-45)/(90-theta) thereafter; >=90 forbidden."""
    if not np.isfinite(k) or k < 0:
        raise ValueError('invalid river turn penalty strength')
    incoming, outgoing = np.asarray(incoming, float), np.asarray(outgoing, float)
    scale = np.linalg.norm(incoming) * np.linalg.norm(outgoing)
    if scale <= 0 or not np.isfinite(scale):
        raise ValueError('invalid river heading vector')
    angle = float(np.degrees(np.arccos(np.clip(incoming @ outgoing / scale, -1., 1.))))
    if angle >= 90.-1e-10:
        return float('inf')
    return 0. if angle <= 45. else k*(angle-45.)/(90.-angle)


def heading_path(sources, ends, cost, points, start, targets, *,
                 max_turn_deg, start_directions=(), end_directions=(), turn_penalty_k=1.):
    """Dijkstra over directed edges, retaining distinct arrivals at each node.

    Endpoint directions represent every existing incoming/outgoing physical
    edge. They constrain the first/last edge without inventing extra vertices.
    """
    if not np.isfinite(max_turn_deg) or not 0 <= max_turn_deg <= 180:
        raise ValueError('invalid maximum river turn')
    directions = []
    for values in (start_directions, end_directions):
        value = np.asarray(values, float)
        if value.size == 0:
            value = np.empty((0, points.shape[1]))
        if (value.ndim != 2 or value.shape[1] != points.shape[1] or
                not np.isfinite(value).all() or np.any(np.linalg.norm(value, axis=1) == 0)):
            raise ValueError('invalid endpoint river directions')
        directions.append(value)
    initial, final = directions
    turn_penalty((1., 0.), (1., 0.), turn_penalty_k)
    def penalty(incoming, outgoing):
        if not turn_allowed(incoming, outgoing, max_turn_deg):
            return float('inf')
        return turn_penalty(incoming, outgoing, turn_penalty_k)
    vectors = points[ends] - points[sources]
    outgoing = {}
    for edge, node in enumerate(sources):
        outgoing.setdefault(int(node), []).append(edge)
    targets = set(map(int, targets))
    distances = np.full(len(ends), np.inf)
    previous = np.full(len(ends), -1, np.int64)
    queue = []
    for edge in outgoing.get(int(start), ()):
        extra = max((penalty(direction, vectors[edge]) for direction in initial), default=0.)
        if np.isfinite(extra):
            distances[edge] = cost[edge]*(1+extra)
            heapq.heappush(queue, (float(distances[edge]), edge))
    best_distance, best_edge = float('inf'), None
    while queue:
        distance, edge = heapq.heappop(queue)
        if distance != distances[edge]:
            continue
        if distance >= best_distance:
            break
        node = int(ends[edge])
        if node in targets:
            extra = max((penalty(vectors[edge], direction) for direction in final), default=0.)
            finish_distance = distance + cost[edge]*extra
            if finish_distance < best_distance:
                best_distance, best_edge = finish_distance, edge
            continue
        for next_edge in outgoing.get(node, ()):
            extra = penalty(vectors[edge], vectors[next_edge])
            if not np.isfinite(extra):
                continue
            # A heading loop must not turn a forbidden reversal into a river
            # route by revisiting a previously traversed account vertex.
            ancestor = edge
            repeated = False
            while ancestor != -1:
                if sources[ancestor] == ends[next_edge]:
                    repeated = True
                    break
                ancestor = int(previous[ancestor])
            if repeated:
                continue
            candidate = distance + cost[next_edge]*(1+extra)
            if candidate < distances[next_edge]:
                distances[next_edge] = candidate
                previous[next_edge] = edge
                heapq.heappush(queue, (float(candidate), next_edge))
    if best_edge is None:
        return None
    path = [int(ends[best_edge])]
    while best_edge != -1:
        path.append(int(sources[best_edge]))
        best_edge = int(previous[best_edge])
    return np.asarray(path[::-1], np.int64)
