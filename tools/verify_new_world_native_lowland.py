import json
from pathlib import Path
import numpy as np
from numba import njit
r=Path('.scratch/river-upgrade-20261101'); o=r/'native-lowland-v1'; d=r/'native-final-routing-v1/derived'; route=r/'native-final-routing-v1/routing'; t=r/'terrain-v3'; e=r/'native-event-v1'
load=lambda p:np.load(p,mmap_mode='r')
@njit
def check(ch,cap,rec,labels,anchors,flow,ocean,unknown,valid):
    bad=0; closure=0; capture=0
    for i in range(ch.size):
        p=labels[i]; j=rec[i]
        eligible=valid[i] and not ocean[i] and not unknown[i] and flow[i]>=.015*1296000 and (p<0 or anchors[p]==i)
        if ch[i] and not eligible: bad+=1
        if ch[i] and j>=0:
            q=labels[j]
            target=valid[j] and not ocean[j] and not unknown[j] and flow[j]>=.015*1296000 and (q<0 or anchors[q]==j)
            if target and not ch[j]: closure+=1
        expected=i if ch[i] else (cap[j] if j>=0 else -1)
        if cap[i]!=expected: capture+=1
    return bad,closure,capture
ch=load(o/'channel_mask.npy').ravel(); cap=load(o/'capture_index.npy').ravel()
result=check(ch,cap,load(route/'receiver.npy'),load(d/'pool_index.npy'),load(d/'pool_anchor.npy'),load(e/'node_water_m3.npy')[1],load(t/'ocean_mask.npy').ravel(),load(t/'unknown_mask.npy').ravel(),load(t/'valid_mask.npy').ravel())
if result!=(0,0,0): raise ValueError(result)
(o/'verification.json').write_text(json.dumps(dict(ineligible_channel_cells=result[0],missing_eligible_downstream_closure=result[1],capture_mismatches=result[2]),indent=2),encoding='utf8')
print(result)
