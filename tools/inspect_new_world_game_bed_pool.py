"""Inspect a saved overflowing pool on its local original-grid support."""
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import label
root = Path('.scratch/river-upgrade-20261101'); h = root/'game-hydro-v1'; d = h/'derived'; terrain = root/'terrain-v3'
a = np.load(root/'game-river-detail-v1/refinement.npz'); load = lambda p: np.load(p, mmap_mode='r')
pool = load(d/'pool_index.npy'); anchor = load(d/'pool_anchor.npy'); water = load(h/'node_water_m3.npy'); ids = load(d/'pool_id.npy')
levels = load(h/'pool_level_m.npy'); storage = load(h/'pool_storage_m3.npy'); capacity = load(d/'pool_capacity_m3.npy')
visible = np.unique(np.r_[a['pool_source'], a['pool_target']]); visible = visible[visible >= 0]
active = visible[np.any(water[:, anchor[visible]] > 0, axis=0)]
# Largest observed overflow pool among displayed edges, to focus on main flow.
p = int(active[np.argmax(capacity[active])]); coarse = load(root/'game-grade-90m/bed_m.npy'); cols = coarse.shape[1]
positions = np.flatnonzero(pool == p); rows, columns = positions//cols, positions%cols
r0=max(0,int(rows.min())*3-2); r1=min(load(terrain/'bed_m.npy').shape[0],int(rows.max())*3+3)
c0=max(0,int(columns.min())*3-2); c1=min(load(terrain/'bed_m.npy').shape[1],int(columns.max())*3+3)
if (r1-r0)*(c1-c0)*32 > 500_000_000: raise ValueError('local bbox budget exceeded')
bed = np.asarray(load(terrain/'bed_m.npy')[r0:r1,c0:c1]); ocean = np.asarray(load(terrain/'ocean_mask.npy')[r0:r1,c0:c1]); valid = np.asarray(load(terrain/'valid_mask.npy')[r0:r1,c0:c1]); unknown = np.asarray(load(terrain/'unknown_mask.npy')[r0:r1,c0:c1])
rr = np.minimum((np.arange(r0,r1)+1)//3,coarse.shape[0]-1); cc = np.minimum((np.arange(c0,c1)+1)//3,cols-1)
support = (pool[(rr[:,None]*cols+cc[None,:])] == p) & valid & ~unknown & ~ocean
seed = np.unravel_index(np.argmin(np.where(support,bed,np.inf)),bed.shape)
result = {'pool_index':p,'pool_id':int(ids[p]),'anchor_node_id':int(anchor[p]),'bbox_row_col':[r0,r1,c0,c1], 'seed_row_col':[r0+int(seed[0]),c0+int(seed[1])], 'anchor_outflow_m3':np.asarray(water[:,anchor[p]]).tolist(),'days':[]}
mask_output=[]
for time in (1,2):
    stage=float(levels[time,p]); stored=float(storage[time,p]); wet=support & (bed < stage) if np.isfinite(stage) and stored > 0 else np.zeros(support.shape,bool)
    labels, count=label(wet,structure=np.ones((3,3),bool)); seed_label=labels[seed]; connected=(labels==seed_label) if seed_label else np.zeros_like(wet)
    volume=float(np.sum(np.maximum(stage-bed[connected],0),dtype=np.float64)*900) if np.isfinite(stage) else 0.
    anchor_rc=(int(anchor[p]//cols*3-r0),int(anchor[p]%cols*3-c0)); anchor_wet=bool(0<=anchor_rc[0]<connected.shape[0] and 0<=anchor_rc[1]<connected.shape[1] and connected[anchor_rc])
    result['days'].append({'day':time*15,'coarse_stage_m':stage if np.isfinite(stage) else None,'coarse_storage_m3':stored,'fine_seed_connected_cells':int(connected.sum()),'fine_other_wet_components':int(count-(1 if seed_label else 0)), 'fine_volume_at_coarse_stage_m3':volume,'fine_minus_coarse_m3':volume-stored,'anchor_in_seed_component':anchor_wet})
    mask_output.append(connected)
out=root/'game-river-bed-v1'; (out/'representative-pool.json').write_text(json.dumps(result,indent=2),encoding='utf8')
np.savez_compressed(out/'representative-pool-wet.npz',bbox_row_col=np.array([r0,r1,c0,c1]),wet_day15=mask_output[0],wet_day30=mask_output[1])
print(json.dumps(result,indent=2))
