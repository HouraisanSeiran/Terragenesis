"""Independent cold-read checks; no terrain generation or state mutation."""
from pathlib import Path
from collections import defaultdict, deque
import argparse
import hashlib
import json
import numpy as np
from scipy import ndimage
from terrain_pipeline.coastal_delta_product import load_checkpoint
from terrain_pipeline.coastal_delta_branching import segment_fluxes
from terrain_pipeline.coastal_marine_sediment import classify_ocean

p = Path(__file__).parent
parser = argparse.ArgumentParser()
parser.add_argument('--prefix', default='multi-branch-v2')
parser.add_argument('--stage')
args = parser.parse_args()
source, _ = load_checkpoint(p / 'growth-v3-stage10')

def total(state):
    return sum(float(getattr(state, name).sum()) for name in
               ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')) + state.exported_solid_m3 + state.unresolved_solid_m3

def check(state, progress):
    routes = [[tuple(c) for c in route] for route in progress['routes']]
    ocean, _ = classify_ocean(state, 0.)
    occupied = {c for route in routes for c in route}
    free = ocean.copy()
    for c in occupied:
        free[c] = False
    free_labels, _ = ndimage.label(free)
    seed_ids = np.unique(free_labels[state.ocean_seed_mask & free])
    external_ocean = np.isin(free_labels, seed_ids[seed_ids != 0]) & free
    faces = []
    for route in routes:
        r,c = route[-1]
        faces.append(any(0 <= r+dr < free.shape[0] and 0 <= c+dc < free.shape[1] and external_ocean[r+dr,c+dc]
                         for dr,dc in ((1,0),(-1,0),(0,1),(0,-1))))
    edges = segment_fluxes(progress)
    incoming, outgoing, indegree = defaultdict(float), defaultdict(float), defaultdict(int)
    successors = defaultdict(set)
    nodes = set()
    for edge in edges:
        a, b = tuple(edge['from_zx']), tuple(edge['to_zx'])
        assert abs(a[0]-b[0]) + abs(a[1]-b[1]) == 1
        nodes.update((a, b)); successors[a].add(b); indegree[b] += 1
        outgoing[a] += edge['discharge_m3_s']; incoming[b] += edge['discharge_m3_s']
    queue = deque(n for n in nodes if indegree[n] == 0)
    visited = 0
    while queue:
        a = queue.popleft(); visited += 1
        for b in successors[a]:
            indegree[b] -= 1
            if indegree[b] == 0:
                queue.append(b)
    inlet = routes[0][0]; outlets = set(r[-1] for r in routes)
    internal = [abs(incoming[n]-outgoing[n]) for n in nodes if n != inlet and n not in outlets]
    labels, _ = ndimage.label(state.valid_mask & (state.bed_m >= 0))
    old_land_ids = np.unique(labels[source.valid_mask & (source.bed_m >= 0)])
    attached = np.isin(labels, old_land_ids[old_land_ids != 0])
    new_land = state.valid_mask & (source.bed_m < 0) & (state.bed_m >= 0)
    mainland_id = labels[213,400]
    mainland = (labels == mainland_id) & (labels != 0)
    extent = np.ptp(np.array(list(outlets)), axis=0) * state.spacing_m / 1000
    event_records = [r for r in state.consumed_packets if r.get('source_id') == 'branch-event-inlet']
    event_solid = sum(r['delivered_solid_m3'] for r in event_records)
    original_land = source.valid_mask & (source.base_bed_m >= 0)
    return {
        'unique_outlets': len(outlets), 'routes_simple': all(len(r) == len(set(r)) for r in routes),
        'acyclic': visited == len(nodes), 'paths_ocean_connected_at_mean_sea': [all(ocean[c] for c in r) for r in routes],
        'mouth_has_independent_external_ocean_face': faces,
        'path_max_bed_m': [max(float(state.bed_m[c]) for c in r) for r in routes],
        'inlet_Q_m3_s': outgoing[inlet], 'outlet_Q_m3_s': sum(incoming[n]-outgoing[n] for n in outlets),
        'internal_Q_residual_m3_s': max(internal, default=0.), 'shares_sum': sum(progress['shares']),
        'outlet_span_zx_km': extent.tolist(), 'attached_new_land_km2': float((new_land & attached).sum()*state.spacing_m**2/1e6),
        'unattached_new_land_km2': float((new_land & ~attached).sum()*state.spacing_m**2/1e6),
        'new_land_connected_to_mainland_anchor_km2': float((new_land & mainland).sum()*state.spacing_m**2/1e6),
        'new_land_other_than_mainland_anchor_km2': float((new_land & ~mainland).sum()*state.spacing_m**2/1e6),
        'solid_residual_m3': total(state)-total(source)-progress['supply_solid_m3']-event_solid,
        'minimum_stock_m3': min(float(getattr(state, name).min()) for name in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')),
        'finite': all(bool(np.isfinite(getattr(state, name)).all()) for name in ('bed_m', 'bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')),
        'base_exact': bool(np.array_equal(source.base_bed_m, state.base_bed_m)),
        'valid_exact': bool(np.array_equal(source.valid_mask, state.valid_mask)),
        'original_land_max_change_m': float(np.max(np.abs((state.bed_m-source.bed_m)[original_land]), initial=0.)),
        'old_records_unchanged': all(any(r == old for r in state.consumed_packets) for old in source.consumed_packets),
        'formation_record_count': sum(r['input_id'] == progress['input_id'] for r in state.consumed_packets),
        'physical_elapsed_s': state.time_s-source.time_s, 'physical_water_added_m3': state.water_input_m3-source.water_input_m3,
        'equivalent_years': progress['years'], 'event_records': event_records,
        'new_forks': [h['proposal']['path'][0] for h in progress['history'] if h.get('event') == 'split'],
        'finite_cut_solid_m3': [h['excavated_solid_m3'] for h in progress['history'] if h.get('event') == 'split'],
    }

report = {'source_identity': source.source_identity, 'cases': {}}
for name in (args.prefix+'-first', args.stage or args.prefix+'-stage', args.prefix+'-event'):
    if not (p / (name+'.npz')).exists():
        continue
    state, progress = load_checkpoint(p / name)
    report['cases'][name] = check(state, progress)
    report['cases'][name]['npz_sha256'] = hashlib.sha256((p/(name+'.npz')).read_bytes()).hexdigest()
report['pass'] = False
if args.prefix+'-event' in report['cases']:
    final = report['cases'][args.prefix+'-event']
    report['pass'] = bool(final['unique_outlets'] >= 5 and len(set(map(tuple, final['new_forks']))) >= 2
        and all(final['paths_ocean_connected_at_mean_sea']) and all(final['mouth_has_independent_external_ocean_face'])
        and final['acyclic'] and final['routes_simple']
        and final['internal_Q_residual_m3_s'] < 1e-6 and abs(final['solid_residual_m3']) < 1.
        and final['minimum_stock_m3'] >= -1e-6 and final['finite'] and final['base_exact'] and final['valid_exact']
        and final['original_land_max_change_m'] < .05 and final['old_records_unchanged'] and final['formation_record_count'] == 1)
(p / ('main-'+args.prefix+'-accept.json')).write_text(json.dumps(report, indent=2), encoding='utf8')
print(json.dumps(report, indent=2))
