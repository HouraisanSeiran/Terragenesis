from pathlib import Path
import json
import argparse
import numpy as np
from scipy import ndimage
from terrain_pipeline.coastal_delta_product import load_checkpoint

p=Path(__file__).parent
parser=argparse.ArgumentParser()
parser.add_argument('--event',default='tidal-plain-v1-event')
args=parser.parse_args()
source,sp=load_checkpoint(p/'multi-branch-v3-repaired-event')

def inventory(s):
    stock=sum(float(getattr(s,k).sum()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))
    pending=sum(r.get('undelivered_solid_m3',0.) for r in s.consumed_packets)
    return stock+s.exported_solid_m3+s.unresolved_solid_m3+pending

def metrics(s,pr):
    bed=s.bed_m; ref=source.bed_m
    area=s.spacing_m**2/1e6
    result={}
    for name,level in (('low',-1.),('mean',0.),('high',1.)):
        land=s.valid_mask & (bed>=level)
        new=land & (ref<level)
        labels,_=ndimage.label(land)
        anchor=labels[213,400]
        mainland=(labels==anchor)&(labels!=0)
        result[name]={'new_exposed_km2':float(new.sum()*area),
                      'new_exposed_mainland_km2':float((new&mainland).sum()*area),
                      'new_exposed_other_km2':float((new&~mainland).sum()*area)}
    routes=[[tuple(c) for c in r] for r in pr['routes']]
    wet=s.valid_mask & (bed<0.)
    labels,_=ndimage.label(wet)
    ids=np.unique(labels[s.ocean_seed_mask&wet]);ocean=np.isin(labels,ids[ids!=0])&wet
    free=wet.copy()
    for r in routes:
        for c in r:free[c]=False
    labels,_=ndimage.label(free)
    ids=np.unique(labels[s.ocean_seed_mask&free]);external=np.isin(labels,ids[ids!=0])&free
    active=[]
    for r in routes:
        z,x=r[-1]
        face=any(0<=z+dz<bed.shape[0] and 0<=x+dx<bed.shape[1] and external[z+dz,x+dx] for dz,dx in ((1,0),(-1,0),(0,1),(0,-1)))
        active.append(bool(all(ocean[c] for c in r) and face))
    oldids={r['input_id'] for r in source.consumed_packets}
    newrecords=[r for r in s.consumed_packets if r['input_id'] not in oldids]
    supply=pr['supply_solid_m3']-sp['supply_solid_m3']+sum(r['solid_m3'] for r in newrecords)
    original_land=source.valid_mask & (source.base_bed_m>=0.)
    result.update({'years':pr['years'],'source_exact':s.source_identity==source.source_identity,
                   'base_exact':bool(np.array_equal(s.base_bed_m,source.base_bed_m)),
                   'original_land_max_change_m':float(np.abs((bed-ref)[original_land]).max(initial=0.)),
                   'solid_residual_including_pending_m3':inventory(s)-inventory(source)-supply,
                   'physical_elapsed_s':s.time_s-source.time_s,
                   'physical_water_delta_m3':s.water_input_m3-source.water_input_m3,
                   'actual_active':active,'saved_active':pr['active'],
                   'actual_Q_m3_s':[q*pr['discharge_m3_s'] for q in pr.get('actual_shares',pr['shares'])],
                   'min_stock_m3':min(float(getattr(s,k).min()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3')),
                   'new_external_records':newrecords})
    return result

report={'cases':{}}
for name in ('tidal-plain-v1-year10',args.event):
    if (p/(name+'.npz')).exists():
        s,pr=load_checkpoint(p/name);report['cases'][name]=metrics(s,pr)
if len(report['cases'])==2:
    before=report['cases']['tidal-plain-v1-year10'];after=report['cases'][args.event]
    report['mean_new_land_retention']=after['mean']['new_exposed_km2']/before['mean']['new_exposed_km2'] if before['mean']['new_exposed_km2'] else None
    report['pass']=bool(all(c['base_exact'] and c['source_exact'] and abs(c['solid_residual_including_pending_m3'])<1.
                            and c['min_stock_m3']>=-1e-6 for c in (before,after)) and before['physical_elapsed_s']==0.
                        and after['physical_elapsed_s']==90000. and after['saved_active']==after['actual_active'])
(p/('main-'+args.event+'-accept.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
