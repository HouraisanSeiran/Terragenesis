"""Atomic, source-relative monotone closure on a sparse directed channel graph."""
from collections import deque
import numpy as np


def solve_shared_bed(source_m, arcs, max_cut_m=4.0):
    """Return bed and component acceptance; an infeasible component has no bed.

    Vertices represent physical sample locations, arcs run downstream. A weak
    component is committed only if every downstream constraint fits the cap.
    """
    source = np.asarray(source_m, dtype=np.float64)
    arcs = np.asarray(arcs, dtype=np.int64).reshape(-1, 2)
    if not np.isfinite(source).all() or not np.isfinite(max_cut_m) or max_cut_m <= 0:
        raise ValueError('finite source and positive cut cap required')
    if arcs.size and (arcs.min() < 0 or arcs.max() >= len(source)):
        raise ValueError('arc vertex out of bounds')
    outgoing = [[] for _ in source]
    adjacent = [[] for _ in source]
    indegree = np.zeros(len(source), dtype=np.int64)
    for a, b in arcs:
        outgoing[a].append(int(b)); adjacent[a].append(int(b)); adjacent[b].append(int(a)); indegree[b] += 1
    component = np.full(len(source), -1, dtype=np.int64)
    result = np.full(len(source), np.nan)
    reasons = []
    for start in range(len(source)):
        if component[start] >= 0:
            continue
        cid = len(reasons); stack = [start]; component[start] = cid; vertices = []
        while stack:
            v = stack.pop(); vertices.append(v)
            for w in adjacent[v]:
                if component[w] < 0:
                    component[w] = cid; stack.append(w)
        degree = {v: int(indegree[v]) for v in vertices}
        queue = deque(v for v in vertices if degree[v] == 0)
        bed = {v: float(source[v]) for v in vertices}; visited = 0
        while queue:
            v = queue.popleft(); visited += 1
            for w in outgoing[v]:
                bed[w] = min(bed[w], bed[v]); degree[w] -= 1
                if degree[w] == 0:
                    queue.append(w)
        if visited != len(vertices):
            reasons.append('directed_cycle')
        elif any(source[v] - bed[v] > max_cut_m + 1e-8 for v in vertices):
            reasons.append('downstream_cut_cap')
        else:
            reasons.append('accepted')
            for v in vertices:
                result[v] = bed[v]
    return result, component, reasons


def solve_shared_bed_scc(source_m, arcs, max_cut_m=4.0):
    """Close geometric inequalities; SCCs are flat, never flow connections.

    Original directed arcs remain the sole hydraulic topology. Any weak
    component whose closure exceeds the source-relative bound is withheld.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    source = np.asarray(source_m, dtype=np.float64)
    arcs = np.asarray(arcs, dtype=np.int64).reshape(-1, 2)
    if not np.isfinite(source).all() or not np.isfinite(max_cut_m) or max_cut_m <= 0:
        raise ValueError('finite source and positive cut cap required')
    if arcs.size and (arcs.min() < 0 or arcs.max() >= len(source)):
        raise ValueError('arc vertex out of bounds')
    graph = coo_matrix((np.ones(len(arcs)), (arcs[:, 0], arcs[:, 1])), shape=(len(source), len(source))).tocsr()
    count, strong = connected_components(graph, directed=True, connection='strong')
    _, weak = connected_components(graph, directed=True, connection='weak')
    strong_source = np.full(count, np.inf)
    np.minimum.at(strong_source, strong, source)
    condensed = np.column_stack((strong[arcs[:, 0]], strong[arcs[:, 1]]))
    condensed = condensed[condensed[:, 0] != condensed[:, 1]]
    strong_bed, _, strong_reasons = solve_shared_bed(strong_source, condensed, max_cut_m=np.finfo(float).max)
    assert all(reason == 'accepted' for reason in strong_reasons)
    candidate = strong_bed[strong]
    # Include the difference between SCC minimum and every source vertex.
    bad = np.zeros(int(weak.max()) + 1 if len(weak) else 0, dtype=bool)
    np.logical_or.at(bad, weak, source - candidate > max_cut_m + 1e-8)
    candidate[bad[weak]] = np.nan
    return candidate, weak, strong, bad


def bounded_monotone_path(bed, allowed, start, end, max_cut_m=4.):
    """Find a path with maximal attainable running bed and bounded cuts."""
    import heapq
    bed = np.asarray(bed, dtype=float)
    allowed = np.asarray(allowed, dtype=bool)
    if not allowed[start] or not allowed[end]:
        return None
    best = {start: float(bed[start])}; previous = {}; queue = [(-best[start], start)]
    while queue:
        neg, cell = heapq.heappop(queue); level = -neg
        if level < best[cell]:
            continue
        if cell == end:
            path = [cell]
            while cell != start:
                cell = previous[cell]; path.append(cell)
            return path[::-1]
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == dc == 0:
                    continue
                nxt = cell[0]+dr, cell[1]+dc
                if not (0 <= nxt[0] < bed.shape[0] and 0 <= nxt[1] < bed.shape[1] and allowed[nxt]):
                    continue
                height = bed[nxt]
                if height - level > max_cut_m + 1e-8:
                    continue
                candidate = min(level, height)
                if candidate > best.get(nxt, -np.inf):
                    best[nxt] = candidate; previous[nxt] = cell; heapq.heappush(queue, (-candidate, nxt))
    return None
