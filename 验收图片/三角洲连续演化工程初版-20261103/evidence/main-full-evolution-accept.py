"""Independent cold-read acceptance of a saved, same-source delta evolution."""
import argparse
import json
from pathlib import Path
import numpy as np
from terrain_pipeline.coastal_delta_evolution import load
from terrain_pipeline.coastal_marine_sediment import load_state, classify_ocean

parser=argparse.ArgumentParser()
parser.add_argument('--prefix',default='full-integrated')
parser.add_argument('--output',default='main-full-evolution-accept.json')
args=parser.parse_args()
root=Path(__file__).parent
source=load_state(root/'window100-v2/state.npz')
states=[load(root/f'{args.prefix}-{name}') for name in ('initial','formed','event1','event2')]
initial,pi=states[0]
formed,pf=states[1]
final,pe=states[-1]

def stock(s):
    return sum(float(getattr(s,k).sum()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))+s.exported_solid_m3+s.unresolved_solid_m3

def hydraulic(p):
    h=p.get('river_hydraulics',{})
    nodes={tuple(n[:2]):n for n in h.get('nodes',[])}
    positive=True
    unique=True
    qsum=sum(h.get('route_q_m3_s',[]))
    routes=[]
    expected_node_q={}
    for route,q in zip(p['routes'],h.get('route_q_m3_s',[])):
        a=np.asarray(route)
        d4=bool(np.all(np.abs(np.diff(a,axis=0)).sum(axis=1)==1))
        unique &= len(np.unique(a,axis=0))==len(a)
        depths=[nodes.get(tuple(c),[0,0,0,-1,0])[3] for c in a]
        if q>0:
            positive &= bool(min(depths)>0)
            for c in a:
                key=tuple(c)
                expected_node_q[key]=expected_node_q.get(key,0.)+q
        routes.append({'q_m3_s':q,'cells':len(route),'d4':d4,'minimum_depth_m':min(depths)})
    return {'accepted_q_m3_s':h.get('accepted_q_m3_s',0),'rejected_q_m3_s':h.get('rejected_q_m3_s'),
       'route_q_sum_residual_m3_s':qsum-h.get('accepted_q_m3_s',0),
       'routes':routes,'positive_active_depths':positive,'unique_route_cells':unique,
       'node_flow_residual_m3_s':max((abs(nodes.get(c,[0,0,0,0,0])[4]-v) for c,v in expected_node_q.items()),default=0.),
       'unique_hydraulic_nodes':len(nodes)==len(h.get('nodes',[])),
       'real_exterior_faces':h.get('exterior_faces',[])}

report={'source_identity':source.source_identity,'spacing_m':source.spacing_m,
        'years':pf['years'],'physical_duration_s':final.time_s-initial.time_s,
        'formation_did_not_advance_physical_time':formed.time_s==initial.time_s,
        'formation_did_not_book_physical_water':formed.water_input_m3==initial.water_input_m3,
        'stages':[], 'events':[], 'avulsions':[x for x in pe['history'] if x.get('event')=='candidate_avulsion'],
        'mouth_extensions':[x for x in pe['history'] if x.get('event')=='mouth_extension'],
        'equivalent_solid_residual_m3':stock(formed)-stock(initial)+pf.get('formation_undelivered_solid_m3',0)-pf['supply_solid_m3'],
        'equivalent_water_residual_m3':pf['integrated']['equivalent_water_m3']-pf['integrated']['accepted_water_m3']-pf['integrated']['pending_water_m3'],
        'old_records_preserved':True, 'all_finite_nonnegative_stocks':True, 'source_grid_and_base_unchanged':True}
for label,(s,p) in zip(('initial','formed','event1','event2'),states):
    old={r['input_id']:r for r in source.consumed_packets}
    now={r['input_id']:r for r in s.consumed_packets}
    report['old_records_preserved'] &= all(now.get(k)==v for k,v in old.items())
    report['source_grid_and_base_unchanged'] &= bool(s.source_identity==source.source_identity and np.array_equal(s.base_bed_m,source.base_bed_m) and np.array_equal(s.valid_mask,source.valid_mask) and s.origin_xz_m==source.origin_xz_m and s.spacing_m==source.spacing_m)
    for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'):
        values=getattr(s,k)
        report['all_finite_nonnegative_stocks'] &= bool(np.isfinite(values).all() and values.min()>=-1e-8)
    owners=p.get('integrated',{}).get('owner_cells',[])
    owner_valid=all(0<=row[3+i]<=getattr(s,k)[int(row[0]),int(row[1])]+1e-7 for row in owners for i,k in enumerate(('bed_solid_m3','mobile_solid_m3','stranded_solid_m3')))
    original_offsets={tuple(n[:2]):n[2]-initial.bed_m[int(n[0]),int(n[1])] for n in pi['hydraulic_sections']['nodes']}
    geometry_error=max((abs(n[2]-s.bed_m[int(n[0]),int(n[1])]-original_offsets.get(tuple(n[:2]),0.)) for n in p['hydraulic_sections']['nodes']),default=0.)
    report['stages'].append({'name':label,'physical_s':s.time_s,'years':p['years'],'owner_stocks_bounded':owner_valid,'section_geometry_residual_m':float(geometry_error),'hydraulic':hydraulic(p)})
for index in (2,3):
    before,pp=states[index-1]
    s,p=states[index]
    new_records=[r for r in s.consumed_packets if r.get('record_kind')=='branch_event' and r['input_id'] not in {x['input_id'] for x in before.consumed_packets}]
    record=new_records[0] if len(new_records)==1 else {}
    report['events'].append({'input_id':record.get('input_id'),'duration_s':s.time_s-before.time_s,
       'delivered_water_m3':record.get('delivered_water_m3',0),'pending_water_m3':record.get('undelivered_water_m3',0),
       'water_residual_m3':record.get('water_m3',0)-record.get('delivered_water_m3',0)-record.get('undelivered_water_m3',0),
       'solid_residual_m3':stock(s)-stock(before)+record.get('undelivered_solid_m3',0)-record.get('solid_m3',0),
       'physical_water_book_residual_m3':s.water_input_m3-before.water_input_m3-record.get('delivered_water_m3',0)})
baseline_ocean=classify_ocean(initial,0.)[0]
report['new_above_mean_sea_km2']=float(np.sum(baseline_ocean&(formed.bed_m>0))*formed.spacing_m**2/1e6)
report['floodplain_deposited_solid_m3']=pf['integrated'].get('floodplain_deposited_solid_m3',0)
report['checks']={
    'source':report['source_grid_and_base_unchanged'] and report['old_records_preserved'],
    'finite_stocks':report['all_finite_nonnegative_stocks'] and all(s['owner_stocks_bounded'] for s in report['stages']),
    'time_and_water_separated':report['formation_did_not_advance_physical_time'] and report['formation_did_not_book_physical_water'],
    'equivalent_budget':abs(report['equivalent_solid_residual_m3'])<1 and abs(report['equivalent_water_residual_m3'])<1,
    'new_actual_route':any(a.get('actual_Q_m3_s',0)>0 for a in report['avulsions']),
    'floodplain_deposition':report['floodplain_deposited_solid_m3']>0,
    'same_committed_geometry':all(s['section_geometry_residual_m']<1e-6 for s in report['stages']),
    'two_physical_events':len(report['events'])==2 and all(e['duration_s']==90000 and e['delivered_water_m3']>0 and abs(e['solid_residual_m3'])<1 and abs(e['water_residual_m3'])<1 and abs(e['physical_water_book_residual_m3'])<1 for e in report['events']),
    'wet_routes':all(s['hydraulic']['positive_active_depths'] and s['hydraulic']['unique_hydraulic_nodes'] and all(r['d4'] for r in s['hydraulic']['routes']) and abs(s['hydraulic']['route_q_sum_residual_m3_s'])<1e-6 and s['hydraulic']['node_flow_residual_m3_s']<1e-6 for s in report['stages'][1:]),
}
report['pass']=all(report['checks'].values())
(root/args.output).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('stages','avulsions','mouth_extensions')},indent=2,ensure_ascii=False))
raise SystemExit(0 if report['pass'] else 1)
