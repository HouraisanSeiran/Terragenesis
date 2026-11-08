"""Cold-read active-route budget and reachability acceptance."""
from pathlib import Path
from collections import defaultdict
import json
import numpy as np
from scipy import ndimage
from terrain_pipeline.coastal_delta_product import load_checkpoint

p = Path(__file__).parent
source, _ = load_checkpoint(p/'multi-branch-v3-repaired-long')
state, progress = load_checkpoint(p/'active-routes-v1-event')
bed = state.bed_m
wet = state.valid_mask & (bed < 0.)
labels, _ = ndimage.label(wet)
ids = np.unique(labels[state.ocean_seed_mask & wet]); ocean = np.isin(labels,ids[ids!=0]) & wet
routes = [[tuple(c) for c in r] for r in progress['routes']]
free = wet.copy()
for r in routes:
    for c in r:
        free[c] = False
labels, _ = ndimage.label(free)
ids = np.unique(labels[state.ocean_seed_mask & free]); exterior = np.isin(labels,ids[ids!=0]) & free
active = []
for route in routes:
    r,c = route[-1]
    face = any(0<=r+dr<bed.shape[0] and 0<=c+dc<bed.shape[1] and exterior[r+dr,c+dc]
               for dr,dc in ((1,0),(-1,0),(0,1),(0,-1)))
    active.append(all(ocean[cell] for cell in route) and face)
incoming, outgoing = defaultdict(float), defaultdict(float)
expected = defaultdict(float)
shares = progress.get('actual_shares', progress['shares'])
for route, share in zip(routes, shares):
    for a,b in zip(route,route[1:]):
        expected[(a,b)] += progress['discharge_m3_s']*share
for (a,b), q in expected.items():
    outgoing[a] += q; incoming[b] += q
ends = set(r[-1] for r in routes); inlet = routes[0][0]
residual = max([abs(incoming[n]-outgoing[n]) for n in incoming.keys()|outgoing.keys() if n!=inlet and n not in ends],default=0.)
def total(s):
    return sum(float(getattr(s,k).sum()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3'))+s.exported_solid_m3+s.unresolved_solid_m3
old_ids = {r['input_id'] for r in source.consumed_packets}
new = [r for r in state.consumed_packets if r['input_id'] not in old_ids]
supplied = sum(r['solid_m3'] for r in new)
pending = sum(r.get('undelivered_solid_m3',0.) for r in new)
report = {'active':active, 'saved_active':progress['active'], 'actual_shares':shares,
          'actual_outlet_Q_m3_s':[float(progress['discharge_m3_s']*s) for s in shares],
          'dry_route_Q_zero':all(a or s==0 for a,s in zip(active,shares)),
          'inlet_Q_m3_s':outgoing[inlet], 'outlet_Q_m3_s':sum(incoming[c]-outgoing[c] for c in ends),
          'internal_Q_residual_m3_s':residual,
          'solid_residual_including_pending_m3':total(state)-total(source)+pending-supplied,
          'new_input_count':len(new),'new_inputs':new,'old_inputs_preserved':all(any(r==old for r in state.consumed_packets) for old in source.consumed_packets if old.get('record_kind')!='equivalent_geological_formation'),
          'base_exact':bool(np.array_equal(state.base_bed_m,source.base_bed_m)),
          'source_exact':state.source_identity==source.source_identity,
          'minimum_stock_m3':min(float(getattr(state,k).min()) for k in ('bed_solid_m3','mobile_solid_m3','stranded_solid_m3')),
          'clock_delta_s':state.time_s-source.time_s,
          'activity_history':[h for h in progress['history'] if h.get('event')=='route_activity' and h.get('input_id')=='active-routes-v1-inlet']}
report['pass']=bool(active==progress['active'] and report['dry_route_Q_zero'] and residual<1e-6
    and sum(active)>=2 and abs(sum(shares)-1.)<1e-9
    and abs(report['solid_residual_including_pending_m3'])<1. and report['new_input_count']==1
    and report['base_exact'] and report['source_exact'] and report['minimum_stock_m3']>=-1e-6
    and report['old_inputs_preserved'])
if (p/'active-routes-v1-flush.npz').exists():
    flushed, fp=load_checkpoint(p/'active-routes-v1-flush')
    prior=new[0]
    rec=next(r for r in flushed.consumed_packets if r['input_id']==prior['input_id'])
    amount=prior['undelivered_solid_m3']-rec['undelivered_solid_m3']
    addition=flushed.mobile_solid_m3-state.mobile_solid_m3
    changed=np.argwhere(addition!=0)
    report['flush']={'released_solid_m3':amount,'physical_time_unchanged':flushed.time_s==state.time_s,
        'input_id_count':sum(r['input_id']==prior['input_id'] for r in flushed.consumed_packets),
        'solid_residual_m3':total(flushed)-total(state)-amount,
        'change_only_at_inlet':bool(len(changed)==1 and tuple(changed[0])==inlet),
        'released_to_inlet_m3':float(addition[inlet]),
        'pending_remaining_m3':rec['undelivered_solid_m3'],
        'source_unchanged':rec['solid_m3']==prior['solid_m3']}
(p/'main-active-accept.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
