"""Local native pool connections without rerouting the saved event."""
import heapq
import json
import os
import time
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
from terrain_pipeline.new_world_game_hydrology import ROOT
from terrain_pipeline.new_world_native_network import section


def wet_path(start, pool, level, labels, bed, shape, max_visits=4096):
    """Shortest 8-neighbour same-pool path to actual wet bed, bounded cut."""
    rows,cols=shape; heap=[(0.,start)]; best={int(start):0.}; parent={}
    while heap and len(best)<=max_visits:
        cost,i=heapq.heappop(heap)
        if cost != best[i]: continue
        z,x=divmod(i,cols)
        if bed[z,x] < level:
            path=[i]
            while path[-1]!=start: path.append(parent[path[-1]])
            return path[::-1]
        for dz in (-1,0,1):
            for dx in (-1,0,1):
                if dx==dz==0: continue
                zz=z+dz; xx=x+dx
                if not (0<=zz<rows and 0<=xx<cols): continue
                j=zz*cols+xx
                if labels[j]!=pool: continue
                midpoint=(float(bed[z,x])+float(bed[zz,xx]))*.5 if dx==0 or dz==0 else (float(bed[z,x])+float(bed[zz,xx])+float(bed[z,xx])+float(bed[zz,x]))*.25
                if max(float(bed[zz,xx]),midpoint)>level+3.95: continue
                nc=cost+(1.41421356237 if dx and dz else 1.)+max(0.,float(bed[zz,xx])-level)*.1
                if nc<best.get(j,float('inf')):
                    best[j]=nc; parent[j]=i; heapq.heappush(heap,(nc,j))
    return None


def build(root=ROOT, output=None):
    root=Path(root); v1=root/'native-network-v1'; out=Path(output or root/'native-network-v2'); out.mkdir(exist_ok=False)
    event=root/'native-event-v1'; d=root/'native-final-routing-v1/derived'; terrain=root/'terrain-v3'; start=time.monotonic()
    load=lambda p:np.load(p,mmap_mode='r',allow_pickle=False)
    m=json.loads((v1/'manifest.json').read_text(encoding='utf8'))
    ids=load(v1/'node_id.npy'); edges=load(v1/'edge_nodes.npy'); kind=load(v1/'node_kind.npy'); q=load(v1/'node_q_m3_s.npy'); stage=load(v1/'node_stage_m.npy'); nodebed=load(v1/'node_bed_m.npy'); width=load(v1/'node_width_m.npy'); status=np.array(load(v1/'edge_status.npy'))
    labels=load(d/'pool_index.npy'); anchors=load(d/'pool_anchor.npy'); capacity=load(d/'pool_capacity_m3.npy'); levels=load(event/'pool_level_m.npy')[2]; storage=load(event/'pool_storage_m3.npy')[2]; bed=load(terrain/'bed_m.npy'); ocean=load(terrain/'ocean_mask.npy').ravel()
    offsets=[0]; points=[]; path_edges=[]; path_pools=[]; path_q=[]; path_kind=[]; notch_volume=[]; notch_depth=[]
    midraw=load(v1/'edge_midpoint_raw_m.npy'); midbed=np.array(load(v1/'edge_midpoint_bed_m.npy'))
    for k in np.flatnonzero(status==2):
        a,b=edges[k]; a=int(a); b=int(b); ia=int(ids[a]); ib=int(ids[b]); pa=int(labels[ia]); pb=int(labels[ib])
        if pb>=0:
            level=float(levels[pb])
            if not np.isfinite(level) or not np.isfinite(stage[a]) or stage[a]+1e-7<level: continue
            path=wet_path(ib,pb,level,labels,bed,bed.shape)
            if not path: continue
            # Entry edge and entire local path use a positive-depth section with <=4 m incision.
            if midraw[k]-(min(midraw[k],(float(stage[a])+level)*.5-.05))>4: continue
            if float(bed.ravel()[ib])-level>3.95: continue
            midbed[k]=min(midraw[k],(float(stage[a])+level)*.5-.05)
            status[k]=4
            points.extend(path); offsets.append(len(points)); path_edges.append(int(k)); path_pools.append(pb); path_q.append(float(q[a])); path_kind.append(1); notch_depth.append(0.); notch_volume.append(0.)
        elif pa>=0 and ia==anchors[pa] and np.isfinite(levels[pa]) and storage[pa]>=capacity[pa]-1e-5 and q[a]>0:
            level=float(levels[pa]); downstream=float(stage[b])
            if not np.isfinite(downstream) or downstream>level+1e-6: continue
            # Cut a finite sill below the unchanged lake surface. Estimate the
            # additional subgrid storage with a triangular 30 m long notch.
            w=float(width[a]); dep=max(.05,float(q[a])/(max(w*.6,1e-6)*5.))
            sill=min(level,downstream)-dep
            cut=float(midraw[k])-sill
            if cut>4 or dep>4 or w<=0: continue
            midbed[k]=min(float(midraw[k]),sill)
            additional=.5*30*w*min(max(cut,0.),dep)
            status[k]=6 if additional>capacity[pa]*.01 else 5
            points.extend([ia,ib]); offsets.append(len(points)); path_edges.append(int(k)); path_pools.append(pa); path_q.append(float(q[a])); path_kind.append(2); notch_depth.append(dep); notch_volume.append(additional)
    # Preserve the original network tables; only statuses and midpoint geometry differ.
    import shutil
    for path in v1.glob('*.npy'):
        if path.name not in ('edge_status.npy','edge_midpoint_bed_m.npy'): shutil.copyfile(path,out/path.name)
    np.save(out/'edge_status.npy',status); np.save(out/'edge_midpoint_bed_m.npy',midbed)
    for name,value,dtype in [('lake_path_offsets',offsets,'i8'),('lake_path_node_id',points,'i8'),('lake_path_edge_index',path_edges,'i8'),('lake_path_pool_index',path_pools,'i8'),('lake_path_q_m3_s',path_q,'f8'),('lake_path_kind',path_kind,'u1'),('sill_depth_m',notch_depth,'f8'),('sill_extra_storage_bound_m3',notch_volume,'f8')]: np.save(out/(name+'.npy'),np.array(value,dtype=dtype))
    # A wet lake raster at day 30 in fixed display window; no inferred flood wetness.
    z0,z1,x0,x1=1382,3049,1176,2843; pool=labels.reshape(bed.shape)[z0:z1,x0:x1]; heights=bed[z0:z1,x0:x1]; wet=np.zeros(pool.shape,bool); present=pool>=0; wet[present]=np.isfinite(levels[pool[present]]) & (heights[present]<levels[pool[present]]); wet &= ~ocean.reshape(bed.shape)[z0:z1,x0:x1]
    np.save(out/'lake_wet_mask.npy',wet)
    stats={str(i):int(np.count_nonzero(status==i)) for i in range(7)}
    m.update(schema='native-network-v2',edge_status_counts=stats,edge_status_meanings={'0':'v1 bounded river section','1':'bounded or velocity failure','2':'unresolved pool contact','3':'unresolved marine section','4':'bounded inlet path to wet pool','5':'finite sill, estimated storage impact <=1% of pool capacity','6':'finite sill storage impact >1% of pool capacity, correction required'},lake_paths=len(path_edges),lake_inlets=int(np.count_nonzero(np.array(path_kind)==1)),lake_sills=int(np.count_nonzero(np.array(path_kind)==2)),sill_extra_storage_bound_sum_m3=float(sum(notch_volume)),wet_mask_window_zx=[z0,z1,x0,x1],runtime_seconds=time.monotonic()-start,limitations='Sill notch storage bound is reported but event storage/flows are unchanged; no dynamic backwater. Pool support paths use same-pool eight-neighbour control cells; geometric sections are subgrid proposals.')
    m.pop('verified_source_q_sum_fraction',None); m.pop('verified_length_m',None)
    tmp=out/'manifest.tmp';tmp.write_text(json.dumps(m,indent=2),encoding='utf8');os.replace(tmp,out/'manifest.json')
    return m



