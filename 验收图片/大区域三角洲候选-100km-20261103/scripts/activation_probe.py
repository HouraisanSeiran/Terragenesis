"""Trial finite-sediment activation against actual mean-sea-level hydraulics."""
import json
from pathlib import Path
from terrain_pipeline.coastal_delta_evolution import load, save
from terrain_pipeline.coastal_delta_hydraulics import HydraulicConfig, solve
from terrain_pipeline.coastal_delta_avulsion import activate_candidate
P=Path('.scratch/delta-large-acceptance-20261103')
s,p=load(P/'final-formed')
cfg=HydraulicConfig(p['integrated']['route_metadata']['extension_port_stage_m'])
baseline={tuple(v[:2]):v for v in p['avulsion_baseline_sections']}
print('max rise',max(n[2]-baseline[tuple(n[:2])][2] for n in p['hydraulic_sections']['nodes'] if tuple(n[:2]) in baseline),flush=True)
reports=[]
for i in range(2):
    s,p,r=activate_candidate(s,p,hydraulic_config=cfg,min_rise_m=.0001)
    reports.append(r)
    print('activation',i,r.get('trigger'),r.get('actual_Q_m3_s'),flush=True)
    if not r['activated']: break
save(P/'activation-probe',s,p)
(P/'activation-probe-report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
print('flow',solve(s,p,0.,cfg)['route_q_m3_s'],flush=True)
