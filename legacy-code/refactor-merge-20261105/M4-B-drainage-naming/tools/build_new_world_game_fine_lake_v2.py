import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path.cwd()))
from terrain_pipeline.lake import minimax_cost as minimax_cost
from terrain_pipeline.lake import invert_connected_storage as invert_connected_storage
r=Path('.scratch/river-upgrade-20261101'); h=r/'game-hydro-v1'; d=h/'derived'; terrain=r/'terrain-v3'; out=r/'game-river-bed-v2'
a=np.load(r/'game-river-detail-v1/refinement.npz'); b=np.load(out/'shared-bed.npz'); load=lambda p:np.load(p,mmap_mode='r')
cols=load(r/'game-grade-90m/bed_m.npy').shape[1]; pool=load(d/'pool_index.npy'); ws=load(d/'watershed_id.npy'); anchor=842108; p=13252; n=anchor; lookup={int(s):i for i,s in enumerate(a['source'])}; route=[]
while n in lookup:
    i=lookup[n]; route.append(i)
    if a['mouth_90m'][i]: break
    n=int(a['target'][i])
first=next(i for i in route if b['accepted'][i]); target=tuple(a['row_col'][a['offsets'][first]])
positions=np.flatnonzero(pool==p); rr,cc=positions//cols,positions%cols
margin=60; r0=max(0,min(int(rr.min())*3,int(target[0]))-margin); r1=min(4096,max(int(rr.max())*3,int(target[0]))+margin+1); c0=max(0,min(int(cc.min())*3,int(target[1]))-margin); c1=min(4096,max(int(cc.max())*3,int(target[1]))+margin+1)
bed=np.asarray(load(terrain/'bed_m.npy')[r0:r1,c0:c1],dtype=np.float64); ocean=np.asarray(load(terrain/'ocean_mask.npy')[r0:r1,c0:c1]); valid=np.asarray(load(terrain/'valid_mask.npy')[r0:r1,c0:c1]); unknown=np.asarray(load(terrain/'unknown_mask.npy')[r0:r1,c0:c1]); cr=np.minimum((np.arange(r0,r1)+1)//3,cols-1); cx=np.minimum((np.arange(c0,c1)+1)//3,cols-1); owners=ws[cr[:,None]*cols+cx[None,:]]; allowed=valid & ~unknown & ~ocean & (owners==ws[anchor]); mapped=pool[cr[:,None]*cols+cx[None,:]]==p
seed=np.unravel_index(np.argmin(np.where(mapped & allowed,bed,np.inf)),bed.shape); goal=(int(target[0]-r0),int(target[1]-c0)); cost,prev=minimax_cost(bed,allowed,seed)
print('shape',bed.shape,'seed',seed,'goal',goal,'target spill',cost[goal], 'basin',int(ws[anchor]))
# Reachable local boundary is a competing escape; if lower than the goal, the
# requested outlet is not a certified basin spill and no overflow is routed.
boundary=np.zeros(bed.shape,bool); boundary[[0,-1],:]=True; boundary[:,[0,-1]]=True
boundary_cost=float(np.min(cost[boundary])); print('boundary spill',boundary_cost)
boundary_index = np.unravel_index(np.argmin(np.where(boundary, cost, np.inf)), cost.shape)
def trace(end):
    path = [end]
    while path[-1] != seed:
        node = tuple(map(int, prev[path[-1]]))
        if node[0] < 0:
            raise ValueError('unreachable minimax outlet')
        path.append(node)
    return np.asarray(path[::-1], dtype=np.int32)
escape_path=trace(boundary_index); goal_path=trace(goal)
spill=float(min(cost[goal],boundary_cost)); identity=json.loads((r/'game-river-detail-v1/summary.json').read_text(encoding='utf8'))['source_identity']; store=load(h/'pool_storage_m3.npy'); results=[]; masks=[]
for day,t in [(15,1),(30,2)]:
 stage,retained,excess,capacity,wet=invert_connected_storage(bed,cost,spill,float(store[t,p]),identity); masks.append(wet); results.append(dict(day=day,original_storage_m3=float(store[t,p]),stage_m=stage,retained_m3=retained,excess_m3=excess,capacity_m3=capacity,wet_cells=int(wet.sum())))
print(json.dumps(results,indent=2))
np.savez_compressed(out/'pool13252-fine.npz',bbox=np.array([r0,r1,c0,c1]),wet_day15=masks[0],wet_day30=masks[1],minimax_m=cost,allowed=allowed,seed=np.array(seed)+[r0,c0],target=np.array(target),route_source=a['source'][route],route_target=a['target'][route],route_accepted=b['accepted'][route],escape_path_row_col=escape_path+[r0,c0],accepted_corridor_candidate_row_col=goal_path+[r0,c0])
original_outflow=np.asarray(load(h/'node_water_m3.npy')[:,anchor],float)
excess=np.asarray([entry['excess_m3'] for entry in results]); extra_intervals=np.diff(np.r_[0.,excess]); corrected=original_outflow+extra_intervals
ledger=dict(original_interval_anchor_outflow_m3=original_outflow.tolist(),
            extra_boundary_outflow_interval_m3=extra_intervals.tolist(),
            hypothetical_combined_outflow_interval_m3=corrected.tolist(),
            routing_status='pending: low escape reaches local boundary; receiver and accepted downstream connection unverified')
(out/'pool13252-fine.json').write_text(json.dumps(dict(ledger=ledger,pool_id='12082050988641638586',anchor=anchor,mouth=980127,first_accepted_source=int(a['source'][first]),spill_to_accepted_m=float(cost[goal]),bbox_escape_m=boundary_cost,results=results),indent=2),encoding='utf8')
