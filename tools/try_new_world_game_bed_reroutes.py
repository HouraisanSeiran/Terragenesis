"""Try a wider existing basin-constrained search on independent over-cap paths."""
import json
from pathlib import Path
import numpy as np
import sys
sys.path.insert(0, str(Path.cwd()))
from terrain_pipeline.new_world_game_river_detail import local_path, required_cut
r=Path('.scratch/river-upgrade-20261101'); a=np.load(r/'game-river-detail-v1/refinement.npz'); load=lambda p: np.load(p,mmap_mode='r')
bed=load(r/'terrain-v3/bed_m.npy'); ocean=load(r/'terrain-v3/ocean_mask.npy'); valid=load(r/'terrain-v3/valid_mask.npy'); unknown=load(r/'terrain-v3/unknown_mask.npy'); coarse=load(r/'game-grade-90m/bed_m.npy'); watershed=load(r/'game-hydro-v1/derived/watershed_id.npy'); pool=load(r/'game-hydro-v1/derived/pool_index.npy'); width=coarse.shape[1]
results=[]
for i in np.flatnonzero(a['status']==1):
    start,end=map(tuple,a['row_col'][[a['offsets'][i],a['offsets'][i+1]-1]])
    basin=watershed[a['source'][i]]
    def allowed(cell):
        cr=min((cell[0]+1)//3,coarse.shape[0]-1); cc=min((cell[1]+1)//3,width-1); ix=cr*width+cc
        return bool(valid[cell] and not unknown[cell] and watershed[ix]==basin and pool[ix]<0)
    path=local_path(bed,ocean,start,end,margin=6,allow_ocean_end=bool(a['mouth_90m'][i]),allowed=allowed)
    maximum=None if path is None else float(np.max(required_cut([bed[x] for x in path])))
    results.append({'source':int(a['source'][i]),'old_max_m':float(a['max_required_cut_m'][i]),'new_max_m':maximum,'within_4m':maximum is not None and maximum<=4})
out=r/'game-river-bed-v1'; (out/'local-reroute-trials.json').write_text(json.dumps(results,indent=2),encoding='utf8')
print('trials',len(results),'within 4m',sum(x['within_4m'] for x in results),'improved',sum(x['new_max_m'] is not None and x['new_max_m']<x['old_max_m']-1e-5 for x in results))
