"""Native network v5: corridors and finishing both read ONE explicit event product.

v4 planned corridors from native-event-v2 and finished with native-event-v3.
v5 takes the event directory name as a parameter (default native-event-v3) for both
phases, records why corridor searches fail, guards pools < 0, and asserts routing and
event-budget invariants before it writes anything.
Units: metres for heights and cuts, cubic metres for volume, seconds for time.
"""
import heapq
import json
import os
import shutil
import time
from pathlib import Path

import numpy as np

from terrain_pipeline.native_product_invariants import check_event_budget, check_routing
from terrain_pipeline.new_world_game_hydrology import ROOT
from terrain_pipeline.new_world_native_network import section

EVENT_DEFAULT = 'native-event-v3'
SECONDS_PER_INTERVAL = 1296000
REASON_LIMIT = 1
REASON_BBOX = 2
REASON_NO_PATH = 3
REASON_INVALID_POOL = 4
REASON_NAMES = {1: 'search node limit exhausted', 2: 'halo bounding box blocks (path exists with wider halo)', 3: 'no path under cut/label constraints', 4: 'inlet pool index < 0'}
NEIGHBOURS = [(dz, dx) for dz in (-1, 0, 1) for dx in (-1, 0, 1) if dz or dx]


def corridor_search(start, end, pool, level, labels, bed, *, max_cut=4., halo=3, limit=60000):
    """Same Dijkstra as v4 corridor(); returns (path or None, reason code or 0)."""
    rows, cols = bed.shape
    z0, x0 = divmod(start, cols)
    z1, x1 = divmod(end, cols)
    zlo = max(0, min(z0, z1) - halo)
    zhi = min(rows, max(z0, z1) + halo + 1)
    xlo = max(0, min(x0, x1) - halo)
    xhi = min(cols, max(x0, x1) + halo + 1)
    heap = [(0., start)]
    dist = {start: 0.}
    parent = {}
    while heap:
        if len(dist) >= limit:
            return None, REASON_LIMIT
        cost, i = heapq.heappop(heap)
        if cost != dist[i]:
            continue
        if i == end:
            result = [i]
            while result[-1] != start:
                result.append(parent[result[-1]])
            return result[::-1], 0
        z, x = divmod(i, cols)
        for dz, dx in NEIGHBOURS:
            zz, xx = z + dz, x + dx
            if not (zlo <= zz < zhi and xlo <= xx < xhi):
                continue
            j = zz * cols + xx
            if int(labels[j]) not in (-1, pool):
                continue
            h = float(bed[zz, xx])
            if not dz or not dx:
                mid = (float(bed[z, x]) + h) * .5
            else:
                mid = (float(bed[z, x]) + h + float(bed[z, xx]) + float(bed[zz, x])) * .25
            cut = max(0., h - level + .05, mid - level + .05)
            if cut > max_cut:
                continue
            nc = cost + (1.4142 if dz and dx else 1.) * (1 + cut * cut * 4)
            if nc < dist.get(j, float('inf')):
                dist[j] = nc
                parent[j] = i
                heapq.heappush(heap, (nc, j))
    return None, REASON_NO_PATH


def classify_failure(start, end, pool, level, labels, bed, max_cut):
    """Diagnostic only: separate bounding-box blockage from true absence of a path."""
    path, reason = corridor_search(start, end, pool, level, labels, bed, max_cut=max_cut, halo=40, limit=400000)
    if path is not None:
        return REASON_BBOX
    return REASON_LIMIT if reason == REASON_LIMIT else REASON_NO_PATH


def corridor_peak(found, level, bed, q):
    """Peak cut above `level`, plan length, and capacity bound; same algorithm as v4 :50-56."""
    cols = bed.shape[1]
    found = np.asarray(found)
    zz = found // cols
    xx = found % cols
    heights = np.asarray(bed[zz, xx], dtype='f8')
    peak = max(0., float(np.max(heights - level + .05)))
    length = 0.
    for a in range(len(found) - 1):
        dz = abs(int(zz[a + 1] - zz[a]))
        dx = abs(int(xx[a + 1] - xx[a]))
        length += 30 * (2 ** .5 if dz and dx else 1.)
        if not dz or not dx:
            mid = (heights[a] + heights[a + 1]) * .5
        else:
            mid = (heights[a] + heights[a + 1] + bed[zz[a], xx[a + 1]] + bed[zz[a + 1], xx[a]]) * .25
        peak = max(peak, float(mid - level + .05))
    width = float(section(np.array([q]))[0][0])
    return peak, length, max(0., peak) * width * length


def _check_inputs(root, event):
    """Fail early on a broken event budget or routing order (-1 tail, bad receiver)."""
    manifest = json.loads((event / 'manifest.json').read_text(encoding='utf8'))
    budget = check_event_budget(manifest)
    if not budget['ok']:
        raise ValueError('event budget invariant failed: %s' % budget['errors'])
    terrain = root / 'terrain-v3'
    routing = root / 'native-final-routing-v1' / 'routing'
    valid = np.load(terrain / 'valid_mask.npy', mmap_mode='r').ravel()
    result = check_routing(np.load(routing / 'order.npy'), np.load(routing / 'receiver.npy'), valid)
    if not result['ok']:
        raise ValueError('routing invariant failed: %s' % result['errors'])
    return manifest


def prepare_corridors(root=ROOT, *, event_name=EVENT_DEFAULT, work_name='native-network-v5-work', base_name='native-network-v3'):
    root = Path(root)
    net = root / base_name
    ev = root / event_name
    d = root / 'native-final-routing-v1/derived'
    _check_inputs(root, ev)
    load = lambda p: np.load(p, mmap_mode='r')
    bed = load(root / 'terrain-v3/bed_m.npy')
    labels = load(d / 'pool_index.npy')
    anchors = load(d / 'pool_anchor.npy')
    levels = load(ev / 'pool_level_m.npy')[2]
    flow = load(ev / 'node_water_m3.npy')[1]
    status = load(net / 'edge_status.npy')
    edge_ids = load(net / 'inlet_edge_index.npy')
    pools = load(net / 'inlet_pool_index.npy')
    offsets = load(net / 'inlet_offsets.npy')
    points = load(net / 'inlet_node_id.npy')
    out = root / work_name
    out.mkdir(exist_ok=False)
    paths = []
    positions = [0]
    edge_out = []
    pool_out = []
    cuts = []
    capacities = []
    rare = []
    failures = []
    failure_reasons = []
    stored = []
    for i, k in enumerate(edge_ids):
        if status[k] != 7:
            continue
        pool = int(pools[i])
        if pool < 0:
            failures.append(int(k))
            failure_reasons.append(REASON_INVALID_POOL)
            continue
        anchor = int(anchors[pool])
        q = float(flow[anchor] / SECONDS_PER_INTERVAL)
        if q <= 0:
            stored.append(int(k))
            continue
        start = int(points[offsets[i + 1] - 1])
        level = float(levels[pool])
        cap = 4.
        found, reason = corridor_search(start, anchor, pool, level, labels, bed, max_cut=4.)
        if found is None:
            cap = 6.
            found, reason = corridor_search(start, anchor, pool, level, labels, bed, max_cut=6.)
        if found is None:
            failures.append(int(k))
            failure_reasons.append(classify_failure(start, anchor, pool, level, labels, bed, 6.) if reason != REASON_LIMIT else REASON_LIMIT)
            continue
        peak, _, volume = corridor_peak(found, level, bed, q)
        paths.extend(found)
        positions.append(len(paths))
        edge_out.append(int(k))
        pool_out.append(pool)
        cuts.append(peak)
        capacities.append(volume)
        rare.append(cap > 4)
    tables = [('corridor_offsets', positions, 'i8'), ('corridor_node_id', paths, 'i8'), ('corridor_edge_index', edge_out, 'i8'), ('corridor_pool_index', pool_out, 'i8'), ('corridor_cut_bound_m', cuts, 'f8'), ('corridor_capacity_bound_m3', capacities, 'f8'), ('corridor_rare_6m', rare, '?'), ('corridor_failure_edges', failures, 'i8'), ('corridor_failure_reason', failure_reasons, 'i1'), ('storage_terminal_edges', stored, 'i8')]
    for name, v, dtype in tables:
        np.save(out / (name + '.npy'), np.asarray(v, dtype=dtype))
    summary = dict(event_product=str(ev), corridors=len(edge_out), stored=len(stored), failures=len(failures), failure_reason_counts={REASON_NAMES[c]: failure_reasons.count(c) for c in REASON_NAMES}, maxcut=max(cuts, default=0), rare=sum(rare), capacity_bound=sum(capacities))
    (out / 'prepare_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf8')
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return out


def reconcile(raw, q, kind, pools, levels, targets, rank, inlet_target, inlet_stage):
    """v4 reconcile with the pools<0 guard on the inlet loop. Returns (..., guarded_count)."""
    stages = np.asarray(raw, dtype='f8').copy()
    wet_pool = (pools >= 0) & np.isfinite(levels[np.maximum(pools, 0)])
    stages[wet_pool] = levels[pools[wet_pool]]
    stages[kind == 2] = 0.
    guarded = 0
    for i, s in zip(inlet_target, inlet_stage):
        p = pools[i]
        if p < 0:
            stages[i] = max(stages[i], s)
            guarded += 1
        else:
            stages[i] = max(stages[i], s) if raw[i] >= levels[p] else levels[p]
    for i in np.argsort(rank):
        j = targets[i]
        if kind[i] == 0 and j >= 0 and np.isfinite(stages[j]):
            stages[i] = max(stages[i], stages[j])
    width, design = section(q)
    design = np.maximum(design, .05)
    beds = np.minimum(raw, stages - design)
    cut = raw - beds
    status = (~np.isfinite(stages)) | (cut > 4.) | ((stages - raw) > 6.)
    beds = np.maximum(beds, raw - 4.)
    return stages, beds, width, status, guarded


def finish(root=ROOT, *, event_name=EVENT_DEFAULT, work_name='native-network-v5-work', out_name='native-network-v5', base_name='native-network-v3'):
    from terrain_pipeline.new_world_native_network_v3 import profile
    root = Path(root)
    prev = root / base_name
    work = root / work_name
    ev = root / event_name
    d = root / 'native-final-routing-v1/derived'
    terrain = root / 'terrain-v3'
    event_manifest = _check_inputs(root, ev)
    prepare_event = json.loads((work / 'prepare_summary.json').read_text(encoding='utf8')).get('event_product')
    if prepare_event != str(ev):
        raise ValueError('work directory was prepared from %s, not %s' % (prepare_event, ev))
    out = root / out_name
    out.mkdir(exist_ok=False)
    started = time.monotonic()
    load = lambda p: np.load(p, mmap_mode='r')
    ids = load(prev / 'node_id.npy')
    edges = load(prev / 'edge_nodes.npy')
    kind = load(prev / 'node_kind.npy')
    raw = load(prev / 'node_raw_bed_m.npy')
    pools = load(prev / 'node_pool_index.npy')
    level = load(ev / 'pool_level_m.npy')[2]
    q = np.asarray(load(ev / 'node_water_m3.npy')[1][ids]) / SECONDS_PER_INTERVAL
    rank = load(root / 'native-final-routing-v1/routing/rank.npy')[ids]
    bed = load(terrain / 'bed_m.npy')
    status = np.array(load(prev / 'edge_status.npy'))
    offsets = load(prev / 'inlet_offsets.npy')
    points = load(prev / 'inlet_node_id.npy')
    entry_edges = load(prev / 'inlet_edge_index.npy')
    entry_pools = load(prev / 'inlet_pool_index.npy')
    inlet_stage = []
    starts = []
    flatstages = []
    invalid = []
    for i, k in enumerate(entry_edges):
        path = points[offsets[i]:offsets[i + 1]]
        pool = int(entry_pools[i])
        ps = profile(path, float(level[pool]), bed, 4096) if pool >= 0 else None
        if ps is None:
            invalid.append(int(k))
            ps = np.full(len(path), np.nan)
        starts.append(int(edges[k, 1]))
        inlet_stage.append(float(ps[0]))
        flatstages.extend(ps)
    targets = np.full(len(ids), -1, dtype='i8')
    targets[edges[:, 0]] = edges[:, 1]
    stage, nodebed, width, bad, guarded = reconcile(raw, q, kind, pools, level, targets, rank, starts, inlet_stage)
    for k in invalid:
        status[k] = 2
    for k in load(work / 'storage_terminal_edges.npy'):
        status[k] = 10
    for k in load(work / 'corridor_edge_index.npy'):
        status[k] = 11
    for k in np.flatnonzero(status == 5):
        if q[edges[k, 0]] <= 0:
            status[k] = 9
    midraw = load(prev / 'edge_midpoint_raw_m.npy')
    midstage = (stage[edges[:, 0]] + stage[edges[:, 1]]) * .5
    depths = stage - nodebed
    middepth = (depths[edges[:, 0]] + depths[edges[:, 1]]) * .5
    midbed = np.minimum(midraw, midstage - middepth)
    regular = status == 0
    fail = regular & ((midraw - midbed > 4) | (stage[edges[:, 0]] + 1e-8 < stage[edges[:, 1]]) | bad[edges[:, 0]] | bad[edges[:, 1]])
    status[fail] = 1
    replaced = ('edge_status.npy', 'node_q_m3_s.npy', 'node_stage_m.npy', 'node_bed_m.npy', 'node_depth_m.npy', 'node_width_m.npy', 'node_status.npy', 'node_velocity_m_s.npy', 'inlet_stage_m.npy', 'edge_midpoint_bed_m.npy', 'lake_wet_mask.npy')
    for f in prev.glob('*.npy'):
        if f.name not in replaced:
            shutil.copyfile(f, out / f.name)
    for f in work.glob('*.npy'):
        shutil.copyfile(f, out / f.name)
    tables = [('edge_status', status), ('node_q_m3_s', q), ('node_stage_m', stage), ('node_bed_m', nodebed), ('node_depth_m', stage - nodebed), ('node_width_m', width), ('node_status', bad), ('inlet_stage_m', np.asarray(flatstages)), ('edge_midpoint_bed_m', midbed)]
    for name, value in tables:
        np.save(out / (name + '.npy'), value)
    ocean = load(terrain / 'ocean_mask.npy')
    labels = load(d / 'pool_index.npy').reshape(bed.shape)
    z0, z1, x0, x1 = 1382, 3049, 1176, 2843
    lp = labels[z0:z1, x0:x1]
    h = bed[z0:z1, x0:x1]
    wet = np.zeros(lp.shape, bool)
    inside = lp >= 0
    wet[inside] = np.isfinite(level[lp[inside]]) & (h[inside] < level[lp[inside]])
    wet &= ~ocean[z0:z1, x0:x1]
    np.save(out / 'lake_wet_mask.npy', wet)
    m = json.loads((prev / 'manifest.json').read_text(encoding='utf8'))
    meanings = {'0': 'bounded river', '1': 'section bound failure', '2': 'inlet failure', '3': 'marine continuation failure', '4': 'wet pool link', '5': 'corrected sill', '7': 'unresolved pool link', '8': 'bounded detour', '9': 'inactive overflow', '10': 'stored water termination', '11': 'bounded pool connecting corridor'}
    m.update(schema='native-network-v5', event_product=str(ev), event_schema=event_manifest.get('schema'), corridor_event_product=prepare_event, world_seed=20261020, edge_status_counts={str(i): int(np.count_nonzero(status == i)) for i in range(12)}, edge_status_meanings=meanings, bad_shared_nodes=int(bad.sum()), recomputed_regular_failures=int(fail.sum()), inlet_pool_negative_guarded=int(guarded), runtime_seconds=time.monotonic() - started, limitations='Geometry approximation; corridors and finishing use one event product; reconciliation audit still advised.')
    tmp = out / 'manifest.tmp'
    tmp.write_text(json.dumps(m, indent=2), encoding='utf8')
    os.replace(tmp, out / 'manifest.json')
    print(json.dumps(m, indent=2), flush=True)
    return m
