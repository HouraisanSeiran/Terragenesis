"""Saved-event native network: bounded inlet and actual lake-support paths."""
import heapq
import json
import os
import shutil
import time
from collections import deque
from pathlib import Path
import numpy as np
from terrain_pipeline.new_world_game_hydrology import ROOT


def local_path(start, pool, level, labels, bed, goal=None, wet_only=False, limit=12000):
    rows,cols=bed.shape; costs={int(start):0.}; parent={}; heap=[(0.,int(start))]
    while heap and len(costs)<=limit:
        cost,i=heapq.heappop(heap)
        if cost!=costs[i]: continue
        z,x=divmod(i,cols)
        if (goal is not None and i==goal) or (goal is None and bed[z,x]<level):
            path=[i]
            while path[-1]!=start: path.append(parent[path[-1]])
            return path[::-1]
        for dz in (-1,0,1):
            for dx in (-1,0,1):
                if not (dx or dz): continue
                zz,xx=z+dz,x+dx
                if not (0<=zz<rows and 0<=xx<cols): continue
                j=zz*cols+xx
                if labels[j]!=pool: continue
                high=float(bed[zz,xx]); mid=(float(bed[z,x])+high)*.5 if not dx or not dz else (float(bed[z,x])+high+float(bed[z,xx])+float(bed[zz,x]))*.25
                if wet_only and (high>=level or mid>=level): continue
                if not wet_only and high-float(bed[z,x])>3.8: continue
                nc=cost+(1.4142 if dx and dz else 1.)+max(0.,high-float(bed[z,x]))
                if nc<costs.get(j,float('inf')): costs[j]=nc;parent[j]=i;heapq.heappush(heap,(nc,j))
    return None


def profile(path, level, bed, cols):
    z=np.asarray(path)//cols; x=np.asarray(path)%cols; raw=bed[z,x].astype('f8'); stage=np.empty(len(path)); stage[-1]=level
    for i in range(len(path)-2,-1,-1): stage[i]=max(raw[i]-.5,stage[i+1])
    if np.any(stage-raw>6) or np.any(raw-(stage-.05)>4): return None
    for i in range(len(path)-1):
        mid=(raw[i]+raw[i+1])*.5 if x[i]==x[i+1] or z[i]==z[i+1] else (raw[i]+raw[i+1]+bed[z[i],x[i+1]]+bed[z[i+1],x[i]])*.25
        if mid-(stage[i]+stage[i+1])*.5+.05>4: return None
    return stage


def build(root=ROOT):
    root=Path(root); base=root/'native-network-v1'; prev=root/'native-network-v2'; ev=root/'native-event-v2'; ter=root/'terrain-v3'; d=root/'native-final-routing-v1/derived'; out=root/'native-network-v3'; out.mkdir(exist_ok=False); started=time.monotonic()
    load=lambda p:np.load(p,mmap_mode='r',allow_pickle=False)
    m=json.loads((prev/'manifest.json').read_text(encoding='utf8')); ids=load(base/'node_id.npy'); edges=load(base/'edge_nodes.npy'); oldstatus=load(base/'edge_status.npy'); status=np.array(oldstatus); raw=load(base/'node_raw_bed_m.npy'); stage=load(base/'node_stage_m.npy'); midraw=load(base/'edge_midpoint_raw_m.npy'); labels=load(d/'pool_index.npy'); anchors=load(d/'pool_anchor.npy'); bed=load(ter/'bed_m.npy'); ocean=load(ter/'ocean_mask.npy').ravel(); levels=load(ev/'pool_level_m.npy')[2]; flow=load(ev/'node_water_m3.npy')[1]; q=np.asarray(flow[ids])/1296000
    # Inlets are selected by pool membership, never by a legacy status.
    entry=(labels[ids[edges[:,1]]] >= 0) & (labels[ids[edges[:,0]]] < 0)
    offsets=[0]; points=[]; stages=[]; path_edge=[]; pool_ids=[]; link_status=[]; wet_offsets=[0]; wet_points=[]
    failed=[]
    for k in np.flatnonzero(entry):
        a,b=edges[k]; pool=int(labels[ids[b]]); lv=float(levels[pool]); start=int(ids[b])
        if not np.isfinite(lv): status[k]=2; failed.append(int(k)); continue
        path=local_path(start,pool,lv,labels,bed)
        if path is None: status[k]=2;failed.append(int(k));continue
        ps=profile(path,lv,bed,bed.shape[1])
        if ps is None or raw[a]-(max(raw[a]-.5,ps[0])-.05)>4: status[k]=2;failed.append(int(k));continue
        # Check source-to-entry physical midpoint against interpolated stage.
        source_stage=max(float(raw[a]),float(ps[0])); midstage=(source_stage+ps[0])*.5
        if midraw[k]-midstage+.05>4: status[k]=2;failed.append(int(k));continue
        anchor=int(anchors[pool]); ap=(bed.ravel()[anchor]<lv)
        wet=local_path(path[-1],pool,lv,labels,bed,goal=anchor,wet_only=True) if ap else None
        status[k]=4 if wet else 7
        points.extend(path);stages.extend(ps.tolist());offsets.append(len(points));path_edge.append(int(k));pool_ids.append(pool);link_status.append(1 if wet else 0)
        if wet: wet_points.extend(wet)
        wet_offsets.append(len(wet_points))
    # Sills retain v2 physical sections; water has been rerouted for all declared added capacities.
    v2status=load(prev/'edge_status.npy'); sill=(v2status==5)|(v2status==6); status[sill]=5
    for k in np.flatnonzero(sill):
        if q[edges[k,0]]<=0: status[k]=9
    # Repair diagonal saddle with either physical orthogonal control cell.
    detour_edges=[]; detour_cells=[]; detour_stages=[]
    for k in np.flatnonzero(status==1):
        a,b=edges[k]; za,xa=divmod(int(ids[a]),4096); zb,xb=divmod(int(ids[b]),4096)
        if abs(za-zb)!=1 or abs(xa-xb)!=1: continue
        for z,x in ((za,xb),(zb,xa)):
            cell=z*4096+x
            if ocean[cell] or labels[cell]>=0: continue
            h=float(bed[z,x]); cs=max(float(stage[b]),h-.5)
            if cs>stage[a] or cs-h>6 or h-(cs-.05)>4: continue
            m1=(float(raw[a])+h)*.5; m2=(h+float(raw[b]))*.5
            if m1-(float(stage[a])+cs)*.5+.05>4 or m2-(cs+float(stage[b]))*.5+.05>4: continue
            status[k]=8;detour_edges.append(int(k));detour_cells.append(cell);detour_stages.append(cs);break
    for name,value,dtype in [('detour_edge_index',detour_edges,'i8'),('detour_node_id',detour_cells,'i8'),('detour_stage_m',detour_stages,'f8')]: np.save(out/(name+'.npy'),np.asarray(value,dtype=dtype))
    # Continue each coastal receiver through genuinely wet ocean cells, requiring
    # the bilinear midpoint to remain below sea level.
    marine_offsets=[0]; marine_nodes=[]; marine_edge=[]
    for k in np.flatnonzero(ocean[ids[edges[:,1]]]):
        target=int(ids[edges[k,1]]); seen={target}; parent={}; queue=deque([target]); goal=None
        while queue and len(seen)<10000:
            cell=queue.popleft(); z,x=divmod(cell,4096)
            if bed[z,x]<=-.05: goal=cell;break
            for dz,dx in ((-1,0),(1,0),(0,-1),(0,1)):
                zz,xx=z+dz,x+dx
                if not (0<=zz<4096 and 0<=xx<4096):continue
                j=zz*4096+xx
                if j in seen or not ocean[j] or bed[zz,xx]>=0:continue
                seen.add(j);parent[j]=cell;queue.append(j)
        if goal is None: status[k]=3;continue
        path=[goal]
        while path[-1]!=target:path.append(parent[path[-1]])
        marine_nodes.extend(path[::-1]);marine_offsets.append(len(marine_nodes));marine_edge.append(int(k))
    for name,value in [('marine_offsets',marine_offsets),('marine_node_id',marine_nodes),('marine_edge_index',marine_edge)]: np.save(out/(name+'.npy'),np.asarray(value,dtype='i8'))
    for f in base.glob('*.npy'):
        if f.name not in ('edge_status.npy','node_q_m3_s.npy','edge_midpoint_bed_m.npy'): shutil.copyfile(f,out/f.name)
    np.save(out/'edge_status.npy',status);np.save(out/'node_q_m3_s.npy',q);np.save(out/'edge_midpoint_bed_m.npy',load(prev/'edge_midpoint_bed_m.npy'))
    for name,value,dtype in [('inlet_offsets',offsets,'i8'),('inlet_node_id',points,'i8'),('inlet_stage_m',stages,'f8'),('inlet_edge_index',path_edge,'i8'),('inlet_pool_index',pool_ids,'i8'),('wet_link_offsets',wet_offsets,'i8'),('wet_link_node_id',wet_points,'i8'),('wet_link_connected',link_status,'?')]: np.save(out/(name+'.npy'),np.asarray(value,dtype=dtype))
    for name in ('lake_path_offsets','lake_path_node_id','lake_path_edge_index','lake_path_pool_index','lake_path_kind','sill_depth_m','sill_extra_storage_bound_m3'): shutil.copyfile(prev/(name+'.npy'),out/(name+'.npy'))
    z0,z1,x0,x1=1382,3049,1176,2843; pool=labels.reshape(bed.shape)[z0:z1,x0:x1]; heights=bed[z0:z1,x0:x1]; wet=np.zeros(pool.shape,bool);present=pool>=0;wet[present]=np.isfinite(levels[pool[present]])&(heights[present]<levels[pool[present]]);wet &= ~ocean.reshape(bed.shape)[z0:z1,x0:x1];np.save(out/'lake_wet_mask.npy',wet)
    m.update(schema='native-network-v3',event_product=str(ev),edge_status_counts={str(i):int(np.count_nonzero(status==i)) for i in range(10)},edge_status_meanings={'0':'bounded river section','1':'unresolved prior bound','2':'unresolved inlet','3':'marine unresolved','4':'inlet and wet link to anchor','5':'sill with corrected storage','7':'inlet wet but anchor wet path unresolved','8':'bounded orthogonal detour','9':'dry overflow after event correction'},inlet_count=len(path_edge),wet_links=int(sum(link_status)),detour_count=len(detour_edges),marine_continuations=len(marine_edge),runtime_seconds=time.monotonic()-started,limitations='Wet paths require wet bilinear midpoint; no assumed subgrid excavation. Legacy nonpool failures and marine continuation remain unresolved pending checks.')
    tmp=out/'manifest.tmp';tmp.write_text(json.dumps(m,indent=2),encoding='utf8');os.replace(tmp,out/'manifest.json');return m
