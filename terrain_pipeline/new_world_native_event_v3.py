"""Correct finite reservoir capacity for declared subgrid sill storage."""
import json
import os
import time
from pathlib import Path
import numpy as np
from terrain_pipeline.new_world_game_hydrology import ROOT, levels
from terrain_pipeline.drainage import route_pool_interval as route_pool_interval


def corrected_capacity(capacity, pool_indices, extra):
    adjustment=np.zeros_like(capacity,dtype='f8')
    np.add.at(adjustment,pool_indices,extra)
    if np.any(adjustment<0): raise ValueError('negative notch storage')
    return capacity+adjustment,adjustment


def run_v3(root=ROOT):
    root=Path(root); old=root/'native-event-v1'; route=root/'native-final-routing-v1'; d=route/'derived'; terrain=root/'terrain-v3'; net=root/'native-network-v2'; out=root/'native-event-v3'; out.mkdir(exist_ok=False); started=time.monotonic()
    load=lambda p:np.load(p,mmap_mode='r',allow_pickle=False)
    capacity=load(d/'pool_capacity_m3.npy'); pool=load(net/'lake_path_pool_index.npy'); extra=load(net/'sill_extra_storage_bound_m3.npy'); corr=root/'native-network-v4-work'; pool=np.concatenate((pool,load(corr/'corridor_pool_index.npy'))); extra=np.concatenate((extra,load(corr/'corridor_capacity_bound_m3.npy'))); corrected,delta=corrected_capacity(capacity,pool,extra)
    np.save(out/'pool_capacity_m3.npy',corrected); np.save(out/'pool_notch_capacity_m3.npy',delta)
    order=load(route/'routing/order.npy'); receiver=load(route/'routing/receiver.npy'); labels=load(d/'pool_index.npy'); anchors=load(d/'pool_anchor.npy'); spill=load(d/'pool_spill_m.npy'); bed=load(terrain/'bed_m.npy'); nodes=load(d/'mouth_source.npy'); local=load(old/'local_contribution_m3.npy'); valid=load(terrain/'valid_mask.npy').ravel(); ocean=load(terrain/'ocean_mask.npy').ravel()
    n=len(local); p=len(capacity); mouth=len(nodes)
    flows=np.lib.format.open_memmap(out/'node_water_m3.npy',mode='w+',dtype='f8',shape=(2,n)); mouths=np.lib.format.open_memmap(out/'mouth_water_m3.npy',mode='w+',dtype='f8',shape=(2,mouth)); stores=np.lib.format.open_memmap(out/'pool_storage_m3.npy',mode='w+',dtype='f8',shape=(3,p)); stages=np.lib.format.open_memmap(out/'pool_level_m.npy',mode='w+',dtype='f8',shape=(3,p)); stores[0]=0;stages[0]=np.nan
    budgets=[]
    for i in range(2):
        state=np.array(stores[i]); flow,retained=route_pool_interval(local,order,receiver,labels,anchors,corrected,state)
        flows[i]=flow; mouths[i]=flow[nodes]; stores[i+1]=state
        # Prismatic notch storage grows proportionally to base storage fraction;
        # hence base prism volume is total * original/corrected capacity.
        base=np.divide(state*capacity,corrected,out=np.zeros_like(state),where=corrected>0)
        stages[i+1]=levels(labels,bed.ravel(),spill,base,900.)
        terminal=float(mouths[i].sum())
        for a in range(0,n,262144):
            b=min(a+262144,n); terminal+=float(flow[a:b][(receiver[a:b]<0)&valid[a:b]&~ocean[a:b]].sum())
        total=float(local.sum()); budgets.append(dict(local_m3=total,retained_m3=float(retained),terminal_m3=terminal,residual_m3=total-float(retained)-terminal))
        for f in (flows,mouths,stores,stages): f.flush()
        del flow
    record=json.loads((old/'manifest.json').read_text(encoding='utf8')); record.update(schema='native-event-v3',base_event=str(old),geometry_input=[str(net),str(corr)],notch_storage_model='extra capacity proportional to original prism storage fraction; original source prism volume = total storage * original capacity / corrected capacity',notch_capacity_m3=float(delta.sum()),affected_pools=int(np.count_nonzero(delta)),budgets=budgets,runtime_seconds=time.monotonic()-started)
    tmp=out/'manifest.tmp';tmp.write_text(json.dumps(record,indent=2),encoding='utf8');os.replace(tmp,out/'manifest.json');return record
