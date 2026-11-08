"""Bounded control-cell geometry for the saved native window network."""
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates
from terrain_pipeline.new_world_game_hydrology import ROOT, IDENTITY
from terrain_pipeline.channel_geometry import DischargeGeometryConfig


def section(q):
    """Existing default discharge power laws, with default material/exposure."""
    c = DischargeGeometryConfig()
    exposure = 1 - np.exp(-c.generation_exposure)
    width = np.minimum(c.max_width_m, c.width_at_unit_q_m * np.maximum(q, 0)**c.width_q_exponent * 1.75 * 1.25 * exposure)
    depth = np.minimum(c.max_incise_m, c.depth_at_unit_q_m * np.maximum(q, 0)**c.depth_q_exponent * 1.0 * 1.0 * exposure)
    return width, depth


def solve_nodes(raw, q, target, rank, kind, lake_level, max_cut=4., max_raise=6.):
    """Downstream-first shared stages. kind: 0 river, 1 lake, 2 sea."""
    width, depth = section(q)
    depth = np.maximum(depth, .05)
    stage = raw.copy()
    stage[kind == 1] = lake_level[kind == 1]
    stage[kind == 2] = 0.
    status = np.zeros(len(raw), dtype=np.uint8)
    for i in np.argsort(rank):
        j = target[i]
        if kind[i] == 0 and j >= 0:
            stage[i] = max(stage[i], stage[j])
        if kind[i] == 1 and not np.isfinite(stage[i]):
            status[i] = 2
    bed = np.minimum(raw, stage-depth)
    cut = raw-bed
    bad = (cut > max_cut + 1e-9) | (stage-raw > max_raise + 1e-9) | ~np.isfinite(stage)
    status[bad] = 1
    bed[bad] = np.maximum(raw[bad]-max_cut, np.minimum(raw[bad], bed[bad]))
    return stage, bed, width, status


def prepare(root=ROOT, output=None):
    start=time.monotonic(); root=Path(root); terrain=root/'terrain-v3'; event=root/'native-event-v1'; low=root/'native-lowland-v1'; route=root/'native-final-routing-v1'; d=route/'derived'; out=Path(output or root/'native-network-v1')
    manifests=[json.loads((p/'manifest.json').read_text(encoding='utf8')) for p in (terrain,event,low)]
    if any(m['source_identity'] != IDENTITY for m in manifests[1:]) or manifests[0]['identity'] != IDENTITY: raise ValueError('source mismatch')
    out.mkdir(exist_ok=False)
    load=lambda p:np.load(p,mmap_mode='r',allow_pickle=False)
    bed=load(terrain/'bed_m.npy'); ocean=load(terrain/'ocean_mask.npy').ravel(); unknown=load(terrain/'unknown_mask.npy').ravel()
    ch=load(low/'channel_mask.npy'); rec=load(route/'routing/receiver.npy'); rank=load(route/'routing/rank.npy'); labels=load(d/'pool_index.npy'); anchors=load(d/'pool_anchor.npy'); levels=load(event/'pool_level_m.npy')[2]; flow=load(event/'node_water_m3.npy')[1]
    z0,z1,x0,x1=1382,3049,1176,2843
    zz,xx=np.nonzero(ch[z0:z1,x0:x1]); starts=(zz+z0)*4096+xx+x0
    ends=rec[starts]; good=ends>=0; starts=starts[good]; ends=ends[good]
    ids=np.unique(np.concatenate((starts,ends)))
    src=np.searchsorted(ids,starts); dst=np.searchsorted(ids,ends)
    target=np.full(ids.size,-1,dtype=np.int64); target[src]=dst
    raw=bed.ravel()[ids].astype('f8'); q=np.asarray(flow[ids],dtype='f8')/1296000
    label=labels[ids]; kind=np.zeros(ids.size,dtype='u1'); kind[ocean[ids]]=2
    lp=label>=0; kind[lp]=1
    lakelevel=np.full(ids.size,np.nan); lakelevel[lp]=levels[label[lp]]
    # Active overflow anchors keep their true pool surface and are checked as lake nodes.
    stage,nodebed,width,status=solve_nodes(raw,q,target,rank[ids],kind,lakelevel)
    stage[status==2]=np.nan
    depth=stage-nodebed
    x=ids%4096; z=ids//4096; coords=np.column_stack((x*30-61440,z*30-61440)).astype('f8')
    mx=(x[src]+x[dst])/2; mz=(z[src]+z[dst])/2
    midraw=map_coordinates(bed,[mz,mx],order=1,mode='nearest').astype('f8')
    midst=(stage[src]+stage[dst])*.5
    middepth=(depth[src]+depth[dst])*.5
    midbed=np.minimum(midraw,midst-middepth)
    midcut=midraw-midbed
    edge_status=np.zeros(len(src),dtype='u1')
    edge_status[(status[src]!=0)|(status[dst]!=0)|~np.isfinite(midbed)]=1
    edge_status[(midcut>4.) | (midst-midraw>6.) | (stage[src]+1e-8<stage[dst])]=1
    # Pool edges require actual wetness, not precollapse river flow.
    wet=(label>=0)&np.isfinite(lakelevel)&(raw<lakelevel)
    pool_target=(kind[dst]==1)
    edge_status[pool_target | (kind[src]==1)]=2
    velocity=q / np.maximum(width * depth * .6, 1e-12)
    edge_status[(velocity[src]>5.) | (velocity[dst]>5.)]=1
    # Sea edge is accepted only with a positive bounded section; not a raw 37-micrometre depth.
    edge_status[(kind[dst]==2)&((depth[dst]<.05)|(raw[dst]-nodebed[dst]>4))]=3
    arrays=dict(node_id=ids,node_xz_m=coords,node_raw_bed_m=raw,node_bed_m=nodebed,node_stage_m=stage,node_depth_m=depth,node_width_m=width,node_velocity_m_s=velocity,node_q_m3_s=q,node_kind=kind,node_status=status,node_pool_index=label,edge_nodes=np.column_stack((src,dst)),edge_midpoint_xz_m=np.column_stack((mx*30-61440,mz*30-61440)),edge_midpoint_raw_m=midraw,edge_midpoint_bed_m=midbed,edge_status=edge_status)
    for name,array in arrays.items(): np.save(out/(name+'.npy'),array)
    dist=np.linalg.norm(coords[src]-coords[dst],axis=1)
    qsum=float(q[src].sum())
    metadata=dict(schema='native-network-v1',source_identity=IDENTITY, source_paths=dict(terrain=str(terrain),event=str(event),lowland=str(low),routing=str(route)),input_manifest_sha256={name:hashlib.sha256((path/'manifest.json').read_bytes()).hexdigest() for name,path in [('terrain',terrain),('event',event),('lowland',low)]},node_count=len(ids),edge_count=len(src),edge_status_counts={str(i):int(np.count_nonzero(edge_status==i)) for i in range(4)},verified_length_m=float(dist[edge_status==0].sum()),total_length_m=float(dist.sum()),verified_source_q_sum_fraction=float(q[src][edge_status==0].sum()/qsum) if qsum else 0,edge_status_meanings={'0':'bounded prescribed section check only','1':'bounded section or stage check failed','2':'pool connection or overflow sill not yet resolved','3':'marine section failed'},node_kind_meanings={'0':'river','1':'potential pool','2':'ocean'},max_cut_m=4,max_stage_above_raw_m=6,interval=1,stage_model='downstream non-rising prescribed approximation; lake fixed saved level and sea fixed zero; no dynamic backwater',limitations='Pool ingress local paths and positive-overflow sill are not solved; no complete river-lake connectivity claim. Edges with status 0 are not yet a certified full network.',runtime_seconds=time.monotonic()-start)
    tmp=out/'manifest.tmp';tmp.write_text(json.dumps(metadata,indent=2),encoding='utf8');os.replace(tmp,out/'manifest.json')
    return metadata

