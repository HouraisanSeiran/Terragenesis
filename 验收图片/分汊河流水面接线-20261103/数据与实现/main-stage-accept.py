"""Independent cold-read checks for river-stage integration over saved TD."""
from pathlib import Path
import json
import numpy as np
from terrain_pipeline.coastal_delta_product import load_checkpoint
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig, solve
from terrain_pipeline.coastal_delta_branching import segment_fluxes, mouth_exterior_faces

p = Path(__file__).resolve().parent
source, source_progress = load_checkpoint(p/'tidal-plain-v1-year10')
state, progress = load_checkpoint(p/'river-stage-v1-event')
hyd = progress['river_hydraulics']
rebuilt = solve(state, progress, hyd['sea_level_m'], HydraulicConfig(**hyd['parameters']))
nodes = {(z,x):(stage,depth,q) for z,x,stage,depth,q in hyd['nodes']}
incoming, outgoing = {}, {}
for edge in segment_fluxes(progress):
    a, b = tuple(edge['from_zx']), tuple(edge['to_zx'])
    q = edge['discharge_m3_s']
    outgoing[a] = outgoing.get(a,0.)+q
    incoming[b] = incoming.get(b,0.)+q
inlet = tuple(progress['routes'][0][0])
terminal = {}
for route,q in zip(progress['routes'],hyd['route_q_m3_s']):
    c = tuple(route[-1]); terminal[c] = terminal.get(c,0.)+q
residuals = [incoming.get(c,0.)-outgoing.get(c,0.)-terminal.get(c,0.)
             for c in set(incoming)|set(outgoing) if c != inlet]

def inventory(s):
    pending = sum((r.get('undelivered_solid_m3') or 0.)+(r.get('pending_solid_m3') or 0.)
                  for r in s.consumed_packets if r['known'])
    return sum(float(getattr(s,k).sum()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))+s.exported_solid_m3+s.unresolved_solid_m3+pending

old_ids = {r['input_id'] for r in source.consumed_packets}
records = [r for r in state.consumed_packets if r['input_id'] not in old_ids]
solid_residual = inventory(state)-inventory(source)-sum(r['solid_m3'] for r in records)
land = source.valid_mask & (source.base_bed_m>=0.)
report = {'source_identity_exact':state.source_identity==source.source_identity,
    'unknown_records_preserved':[r for r in state.consumed_packets if not r['known']]==[r for r in source.consumed_packets if not r['known']],
    'base_exact':bool(np.array_equal(state.base_bed_m,source.base_bed_m)),
    'physical_elapsed_s':state.time_s-source.time_s,'equivalent_years_change':progress['years']-source_progress['years'],
    'water_input_delta_m3':state.water_input_m3-source.water_input_m3,
    'record_delivered_water_m3':sum(r['delivered_water_m3'] for r in records),
    'external_records':records,'solid_residual_including_pending_m3':solid_residual,
    'min_solid_stock_m3':min(float(getattr(state,k).min()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3')),
    'finite_stocks':bool(all(np.isfinite(getattr(state,k)).all() for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))),
    'hydraulics_reproduce':hyd==rebuilt,'route_q_m3_s':hyd['route_q_m3_s'],
    'accepted_q_m3_s':hyd['accepted_q_m3_s'],'rejected_q_m3_s':hyd['rejected_q_m3_s'],
    'node_q_residual_m3_s':max(map(abs,residuals),default=0.),
    'unique_nodes':len(nodes)==len(hyd['nodes']),
    'min_river_depth_m':min((v[1] for v in nodes.values()),default=None),
    'bed_depth_reconstruct':bool(all(abs(stage-state.bed_m[c]-depth)<1e-8 for c,(stage,depth,q) in nodes.items())),
    'inlet_stage_m':nodes[inlet][0] if inlet in nodes else None,
    'upstream_stage_limit_m':hyd['parameters']['upstream_stage_limit_m'],
    'mouth_exterior_faces':mouth_exterior_faces(state,progress,sea_level_m=hyd['sea_level_m']),
    'original_land_max_change_m':float(np.abs((state.bed_m-source.bed_m)[land]).max(initial=0.))}
report['pass'] = bool(report['source_identity_exact'] and report['unknown_records_preserved'] and report['base_exact'] and report['physical_elapsed_s']==90000.
    and report['equivalent_years_change']==0. and abs(solid_residual)<1.
    and report['finite_stocks'] and report['min_solid_stock_m3']>=0.
    and report['hydraulics_reproduce'] and report['unique_nodes'] and report['bed_depth_reconstruct']
    and report['node_q_residual_m3_s']<1e-6
    and abs(report['water_input_delta_m3']-report['record_delivered_water_m3'])<1e-3
    and (report['inlet_stage_m'] is None or report['inlet_stage_m']<=report['upstream_stage_limit_m']+1e-6))
(p/'main-stage-accept.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
