"""Bounded lake corridors and shared-node reconciliation for native v4."""
import heapq
import json
import os
import time
from pathlib import Path
import numpy as np
from terrain_pipeline.new_world_game_hydrology import ROOT
from terrain_pipeline.new_world_native_network import section


def corridor(start, end, pool, level, labels, bed, *, max_cut=4., halo=3, limit=60000):
    rows,cols=bed.shape; z0,x0=divmod(start,cols); z1,x1=divmod(end,cols)
    zlo=max(0,min(z0,z1)-halo); zhi=min(rows,max(z0,z1)+halo+1); xlo=max(0,min(x0,x1)-halo); xhi=min(cols,max(x0,x1)+halo+1)
    heap=[(0.,start)]; dist={start:0.}; parent={}
    while heap and len(dist)<limit:
        cost,i=heapq.heappop(heap)
        if cost!=dist[i]:continue
        if i==end:
            result=[i]
            while result[-1]!=start:result.append(parent[result[-1]])
            return result[::-1]
        z,x=divmod(i,cols)
        for dz in (-1,0,1):
            for dx in (-1,0,1):
                if not (dx or dz):continue
                zz,xx=z+dz,x+dx
                if not(zlo<=zz<zhi and xlo<=xx<xhi):continue
                j=zz*cols+xx; lp=int(labels[j])
                if lp not in (-1,pool):continue
                h=float(bed[zz,xx]); mid=(float(bed[z,x])+h)*.5 if not dz or not dx else (float(bed[z,x])+h+float(bed[z,xx])+float(bed[zz,x]))*.25
                cut=max(0.,h-level+.05,mid-level+.05)
                if cut>max_cut:continue
                nc=cost+(1.4142 if dz and dx else 1.)*(1+cut*cut*4)
                if nc<dist.get(j,float('inf')):dist[j]=nc;parent[j]=i;heapq.heappush(heap,(nc,j))
    return None


def prepare_corridors(root=ROOT):
    root=Path(root); net=root/'native-network-v3'; ev=root/'native-event-v2'; d=root/'native-final-routing-v1/derived'; bed=np.load(root/'terrain-v3/bed_m.npy',mmap_mode='r'); load=lambda p:np.load(p,mmap_mode='r'); labels=load(d/'pool_index.npy'); anchors=load(d/'pool_anchor.npy'); levels=load(ev/'pool_level_m.npy')[2]; flow=load(ev/'node_water_m3.npy')[1]; ids=load(net/'node_id.npy'); edges=load(net/'edge_nodes.npy'); status=load(net/'edge_status.npy'); edge_ids=load(net/'inlet_edge_index.npy'); pools=load(net/'inlet_pool_index.npy'); offsets=load(net/'inlet_offsets.npy'); points=load(net/'inlet_node_id.npy')
    out=root/'native-network-v4-work';out.mkdir(exist_ok=False); paths=[]; positions=[0]; edge_out=[]; pool_out=[]; cuts=[]; capacities=[]; rare=[]; failures=[]; stored=[]
    for i,k in enumerate(edge_ids):
        if status[k]!=7:continue
        pool=int(pools[i]); anchor=int(anchors[pool]); q=float(flow[anchor]/1296000)
        if q<=0:stored.append(int(k));continue
        start=int(points[offsets[i+1]-1]); level=float(levels[pool]); found=corridor(start,anchor,pool,level,labels,bed,max_cut=4.)
        cap=4.
        if found is None:found=corridor(start,anchor,pool,level,labels,bed,max_cut=6.);cap=6.
        if found is None:failures.append(int(k));continue
        zz=np.asarray(found)//bed.shape[1];xx=np.asarray(found)%bed.shape[1]; heights=np.asarray(bed[zz,xx],dtype='f8');maxcut=max(0.,float(np.max(heights-level+.05)))
        length=0.; peak=maxcut
        for a in range(len(found)-1):
            dz=abs(int(zz[a+1]-zz[a])); dx=abs(int(xx[a+1]-xx[a])); length+=30*(2**.5 if dz and dx else 1.)
            mid=(heights[a]+heights[a+1])*.5 if not dz or not dx else (heights[a]+heights[a+1]+bed[zz[a],xx[a+1]]+bed[zz[a+1],xx[a]])*.25
            peak=max(peak,float(mid-level+.05))
        width=float(section(np.array([q]))[0][0]); volume=max(0.,peak)*width*length
        paths.extend(found);positions.append(len(paths));edge_out.append(int(k));pool_out.append(pool);cuts.append(peak);capacities.append(volume);rare.append(cap>4)
    for name,v,dtype in [('corridor_offsets',positions,'i8'),('corridor_node_id',paths,'i8'),('corridor_edge_index',edge_out,'i8'),('corridor_pool_index',pool_out,'i8'),('corridor_cut_bound_m',cuts,'f8'),('corridor_capacity_bound_m3',capacities,'f8'),('corridor_rare_6m',rare,'?'),('corridor_failure_edges',failures,'i8'),('storage_terminal_edges',stored,'i8')]:np.save(out/(name+'.npy'),np.asarray(v,dtype=dtype))
    print(json.dumps(dict(corridors=len(edge_out),stored=len(stored),failures=len(failures),maxcut=max(cuts,default=0),rare=sum(rare),capacity_bound=sum(capacities)),indent=2),flush=True)
    return out


def reconcile(raw, q, kind, pools, levels, targets, rank, inlet_target, inlet_stage, *, section_override=None):
    """Produce one stage per physical node, anchored to corrected pool levels."""
    from terrain_pipeline.new_world_native_network import section
    stages=np.asarray(raw,dtype='f8').copy(); wet_pool=(pools>=0)&np.isfinite(levels[np.maximum(pools,0)])
    stages[wet_pool]=levels[pools[wet_pool]]
    stages[kind==2]=0.
    for i,s in zip(inlet_target,inlet_stage):stages[i]=max(stages[i],s) if raw[i]>=levels[pools[i]] else levels[pools[i]]
    for i in np.argsort(rank):
        j=targets[i]
        if kind[i]==0 and j>=0 and np.isfinite(stages[j]):stages[i]=max(stages[i],stages[j])
    width,design=section(q) if section_override is None else section_override
    design=np.maximum(design,.05)
    beds=np.minimum(raw,stages-design); cut=raw-beds
    status=(~np.isfinite(stages)) | (cut>4.) | ((stages-raw)>6.)
    beds=np.maximum(beds,raw-4.)
    return stages,beds,width,status


def finish(root=ROOT):
    import shutil
    from terrain_pipeline.new_world_native_network_v3 import profile
    root=Path(root); prev=root/'native-network-v3';work=root/'native-network-v4-work';ev=root/'native-event-v3';d=root/'native-final-routing-v1/derived';terrain=root/'terrain-v3';out=root/'native-network-v4';out.mkdir(exist_ok=False);started=time.monotonic();load=lambda p:np.load(p,mmap_mode='r')
    ids=load(prev/'node_id.npy');edges=load(prev/'edge_nodes.npy');kind=load(prev/'node_kind.npy');raw=load(prev/'node_raw_bed_m.npy');pools=load(prev/'node_pool_index.npy');level=load(ev/'pool_level_m.npy')[2];q=np.asarray(load(ev/'node_water_m3.npy')[1][ids])/1296000;rank=load(root/'native-final-routing-v1/routing/rank.npy')[ids];bed=load(terrain/'bed_m.npy');status=np.array(load(prev/'edge_status.npy'));offsets=load(prev/'inlet_offsets.npy');points=load(prev/'inlet_node_id.npy');entry_edges=load(prev/'inlet_edge_index.npy');entry_pools=load(prev/'inlet_pool_index.npy')
    inlet_stage=[]; starts=[]; flatstages=[]; invalid=[]
    for i,k in enumerate(entry_edges):
        path=points[offsets[i]:offsets[i+1]]; ps=profile(path,float(level[entry_pools[i]]),bed,4096)
        if ps is None: invalid.append(int(k));ps=np.full(len(path),np.nan)
        starts.append(int(edges[k,1]));inlet_stage.append(float(ps[0]));flatstages.extend(ps)
    targets=np.full(len(ids),-1,dtype='i8');targets[edges[:,0]]=edges[:,1]
    # Sea terminal discharge is the sum at the saved ocean receiver.
    stage,nodebed,width,bad=reconcile(raw,q,kind,pools,level,targets,rank,starts,inlet_stage)
    for k in invalid:status[k]=2
    for k in load(work/'storage_terminal_edges.npy'):status[k]=10
    for k in load(work/'corridor_edge_index.npy'):status[k]=11
    # A previously known overflow cannot be shown if its corrected flow vanished.
    for k in np.flatnonzero(status==5):
        if q[edges[k,0]]<=0:status[k]=9
    # Recheck all original unmodified nonpool edge sections at midpoint.
    midraw=load(prev/'edge_midpoint_raw_m.npy'); midstage=(stage[edges[:,0]]+stage[edges[:,1]])*.5; depths=stage-nodebed;middepth=(depths[edges[:,0]]+depths[edges[:,1]])*.5;midbed=np.minimum(midraw,midstage-middepth)
    regular=(status==0);fail=regular & ((midraw-midbed>4)|(stage[edges[:,0]]+1e-8<stage[edges[:,1]])|bad[edges[:,0]]|bad[edges[:,1]])
    status[fail]=1
    for f in prev.glob('*.npy'):
        if f.name not in ('edge_status.npy','node_q_m3_s.npy','node_stage_m.npy','node_bed_m.npy','node_depth_m.npy','node_width_m.npy','node_status.npy','node_velocity_m_s.npy','inlet_stage_m.npy','edge_midpoint_bed_m.npy','lake_wet_mask.npy'):shutil.copyfile(f,out/f.name)
    for f in work.glob('*.npy'):shutil.copyfile(f,out/f.name)
    for name,value in [('edge_status',status),('node_q_m3_s',q),('node_stage_m',stage),('node_bed_m',nodebed),('node_depth_m',stage-nodebed),('node_width_m',width),('node_status',bad),('inlet_stage_m',np.asarray(flatstages)),('edge_midpoint_bed_m',midbed)]:np.save(out/(name+'.npy'),value)
    ocean=load(terrain/'ocean_mask.npy');labels=load(d/'pool_index.npy').reshape(bed.shape);z0,z1,x0,x1=1382,3049,1176,2843; lp=labels[z0:z1,x0:x1]; h=bed[z0:z1,x0:x1];wet=np.zeros(lp.shape,bool);valid=lp>=0;wet[valid]=np.isfinite(level[lp[valid]])&(h[valid]<level[lp[valid]]);wet &= ~ocean[z0:z1,x0:x1];np.save(out/'lake_wet_mask.npy',wet)
    m=json.loads((prev/'manifest.json').read_text(encoding='utf8'));m.update(schema='native-network-v4',event_product=str(ev),edge_status_counts={str(i):int(np.count_nonzero(status==i)) for i in range(12)},edge_status_meanings={'0':'bounded river','1':'section bound failure','2':'inlet failure','3':'marine continuation failure','4':'wet pool link','5':'corrected sill','7':'unresolved pool link','8':'bounded detour','9':'inactive overflow','10':'stored water termination','11':'bounded pool connecting corridor'},bad_shared_nodes=int(bad.sum()),recomputed_regular_failures=int(fail.sum()),runtime_seconds=time.monotonic()-started,limitations='Geometry approximation; candidate corridors require reconciliation audit after corrected levels.')
    tmp=out/'manifest.tmp';tmp.write_text(json.dumps(m,indent=2),encoding='utf8');os.replace(tmp,out/'manifest.json');print(json.dumps(m,indent=2),flush=True);return m
