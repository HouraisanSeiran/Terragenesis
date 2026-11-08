"""Audit saved regional outputs independently; never advance the model."""
from pathlib import Path
import json
import numpy as np
from terrain_pipeline.coastal_delta_evolution import load
from terrain_pipeline.coastal_marine_sediment import classify_ocean
from terrain_pipeline.coastal_delta_branching import mouth_exterior_faces

root = Path(__file__).resolve().parent
names = ('final-initial', 'final-formed', 'final-event')
states = [load(root / name) for name in names]
initial, initial_progress = states[0]
formed, formed_progress = states[1]
final, final_progress = states[2]
offsets = {tuple(n[:2]): n[2] - initial.bed_m[int(n[0]), int(n[1])] for n in initial_progress['hydraulic_sections']['nodes']}
stock_fields = ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')


def stock(state):
    return sum(float(getattr(state, key).sum()) for key in stock_fields) + state.exported_solid_m3 + state.unresolved_solid_m3


stages = []
for name, (state, progress) in zip(names, states):
    sections = {tuple(n[:2]): n for n in progress['hydraulic_sections']['nodes']}
    h = progress.get('river_hydraulics', {})
    nodes = {tuple(n[:2]): n for n in h.get('nodes', [])}
    expected_node_q = {}
    routes = []
    faces = mouth_exterior_faces(state, progress, sea_level_m=h.get('sea_level_m', 0.))
    for index, route in enumerate(progress['routes']):
        cells = [tuple(c) for c in route]
        q = h.get('route_q_m3_s', [0.] * len(progress['routes']))[index]
        for cell in cells:
            expected_node_q[cell] = expected_node_q.get(cell, 0.) + q
        depths = [nodes[c][2] - sections[c][2] for c in cells if c in nodes]
        points = np.asarray(cells)
        routes.append({'q_m3_s': q, 'cells': len(cells),
                       'd4': bool(np.all(np.abs(np.diff(points, axis=0)).sum(axis=1) == 1)),
                       'no_cycles': len(cells) == len(set(cells)),
                       'min_actual_depth_m': min(depths) if depths else None,
                       'actual_wet': bool(q <= 0 or (len(depths) == len(cells) and min(depths) > 0)),
                       'exterior_faces': faces[index]})
    geometry_error = max(abs(n[2] - state.bed_m[int(n[0]), int(n[1])] - offsets.get(tuple(n[:2]), 0.)) for n in sections.values())
    node_error = max((abs(nodes[c][4] - q) for c, q in expected_node_q.items() if c in nodes), default=0.)
    owner = progress['integrated'].get('owner_cells', [])
    stages.append({'name': name, 'source_identity': state.source_identity,
        'finite_stocks': bool(all(np.isfinite(getattr(state, f)).all() and getattr(state, f).min() >= -1e-8 for f in stock_fields)),
        'owner_bounded': bool(all(0 <= row[3+i] <= getattr(state, field)[int(row[0]), int(row[1])] + 1e-7 for row in owner for i, field in enumerate(stock_fields))),
        'source_unchanged': bool(state.source_identity == initial.source_identity and np.array_equal(state.base_bed_m, initial.base_bed_m) and np.array_equal(state.valid_mask, initial.valid_mask)),
        'geometry_residual_m': geometry_error, 'node_q_residual_m3_s': node_error,
        'accepted_q_m3_s': h.get('accepted_q_m3_s', 0.),
        'pending_q_m3_s': h.get('rejected_q_m3_s'),
        'route_q_residual_m3_s': sum(r['q_m3_s'] for r in routes) - h.get('accepted_q_m3_s', 0.),
        'routes': routes})

records = [r for r in final.consumed_packets if r['input_id'] not in {x['input_id'] for x in formed.consumed_packets} and r.get('record_kind') == 'branch_event']
assert len(records) == 1, 'expected one final physical event'
record = records[0]
equivalent_residual = stock(formed) - stock(initial) + formed_progress.get('formation_undelivered_solid_m3', 0.) - formed_progress['supply_solid_m3']
event_residual = stock(final) - stock(formed) + record['undelivered_solid_m3'] - record['solid_m3']
old = {r['input_id']: r for r in initial.consumed_packets}
new = {r['input_id']: r for r in final.consumed_packets}
baseline_ocean = classify_ocean(initial, 0.)[0]
water_residual = record['water_m3'] - record['delivered_water_m3'] - record['undelivered_water_m3']
result = {'stages': stages, 'years': formed_progress['years'],
    'new_physical_duration_s': final.time_s - formed.time_s,
    'equivalent_solid_residual_m3': equivalent_residual, 'event_solid_residual_m3': event_residual,
    'event_water_residual_m3': water_residual,
    'physical_event': {k: record[k] for k in ('input_id', 'water_m3', 'delivered_water_m3', 'undelivered_water_m3', 'solid_m3', 'delivered_solid_m3', 'undelivered_solid_m3')},
    'initial_connected_ocean_new_emergence_km2': [float(np.sum(baseline_ocean & (state.bed_m > 0)) * state.spacing_m**2 / 1e6) for state, _ in states],
    'checks': {}}
result['checks'] = {
    'source': all(s['source_unchanged'] for s in stages),
    'stocks': all(s['finite_stocks'] and s['owner_bounded'] for s in stages),
    'time_separation': formed.time_s == initial.time_s and formed.water_input_m3 == initial.water_input_m3,
    'meaningful_formation_and_event': formed_progress['years'] >= 2 and final.time_s - formed.time_s == 90000,
    'equivalent_budget': abs(equivalent_residual) < 1,
    'physical_budget': abs(event_residual) < 1 and abs(water_residual) < 1 and abs(final.water_input_m3 - formed.water_input_m3 - record['delivered_water_m3']) < 1,
    'shared_geometry': all(s['geometry_residual_m'] < 1e-6 for s in stages),
    'node_and_route_q': all(abs(s['route_q_residual_m3_s']) < 1e-6 and s['node_q_residual_m3_s'] < 1e-6 for s in stages[1:]),
    'actual_wet_routes': all(r['d4'] and r['no_cycles'] and r['actual_wet'] for s in stages[1:] for r in s['routes']),
    'three_actual_outlets': sum(r['q_m3_s'] > 0 and bool(r['exterior_faces']) for r in stages[-1]['routes']) >= 3,
    'old_unknown_records': all(new.get(key) == value for key, value in old.items()),
}
result['pass'] = bool(all(result['checks'].values()))
(root / 'main-case-accept.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k != 'stages'}, indent=2))
raise SystemExit(0 if result['pass'] else 1)
