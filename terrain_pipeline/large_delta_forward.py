"""Forward-constrained delta formation on an explicitly surveyed coastal outlet.

Geological initialization is a finite-volume scenario, not a time simulation.
"""
from dataclasses import replace
import numpy as np
from scipy import ndimage
from skimage.graph import MCP_Geometric

from terrain_pipeline.large_delta_suite import initialize
from terrain_pipeline.channel_geometry import formative_section
from terrain_pipeline.channel_geometry import channel_section_cut


def forward_fields(shape, origin_xz_m, spacing_m, apex_xz_m, direction_xz):
    direction = np.asarray(direction_xz, dtype=float)
    if direction.shape != (2,) or not np.isfinite(direction).all() or np.linalg.norm(direction) == 0:
        raise ValueError('finite nonzero downstream direction required')
    direction /= np.linalg.norm(direction)
    x = origin_xz_m[0] + np.arange(shape[1])*spacing_m - apex_xz_m[0]
    z = origin_xz_m[1] + np.arange(shape[0])*spacing_m - apex_xz_m[1]
    forward = x[None,:]*direction[0] + z[:,None]*direction[1]
    lateral = x[None,:]*direction[1] - z[:,None]*direction[0]
    return forward, lateral


def initialize_forward(bed_m, valid, ocean, origin_xz_m, spacing_m, scenario, direction_xz,
                       *, half_angle_tangent=0.8):
    """Use existing finite-inventory shelf initialization inside a forward sector."""
    if not np.isfinite(half_angle_tangent) or half_angle_tangent <= 0:
        raise ValueError('positive sector angle required')
    forward, lateral = forward_fields(bed_m.shape, origin_xz_m, spacing_m,
                                      scenario.anchor_xz_m, direction_xz)
    sector = (forward >= -spacing_m) & (np.abs(lateral) <= np.maximum(forward, 0)*half_angle_tangent + 2*spacing_m)
    # Explicit source ocean only; no imaginary shelf or unknown-cell filling.
    result = initialize(bed_m, valid, np.asarray(ocean, bool) & sector,
                        origin_xz_m, spacing_m, scenario)
    result['sector'] = sector
    result['forward_m'] = forward
    return result


def forward_network(bed_m, original_m, landform, valid, ocean, origin_xz_m, spacing_m,
                    apex_zx, direction_xz, discharge_m3_s, *, outlet_count=4,
                    material=(.35, .35, 0., .25), max_width_m=2000.):
    """Build a rooted, forward-progressing shortest-path tree and exact metric sections.

    The sampled centreline cuts preserve sub-grid section widths; they do not claim
    that an unresolved channel's raster area is a resolved wet surface.
    """
    bed=np.asarray(bed_m,float); original=np.asarray(original_m,float)
    valid=np.asarray(valid,bool); ocean=np.asarray(ocean,bool); plain=np.asarray(landform,bool)
    if (bed.ndim != 2 or any(a.shape != bed.shape for a in (original,valid,ocean,plain))
        or not np.isfinite(bed[valid]).all() or not np.isfinite(original[valid]).all()
        or not np.isfinite(discharge_m3_s) or discharge_m3_s <= 0 or spacing_m <= 0
        or not 2 <= outlet_count <= 20):
        raise ValueError('invalid forward network inputs')
    start=tuple(int(v) for v in apex_zx)
    if len(start)!=2 or any(v<0 or v>=n for v,n in zip(start,bed.shape)) or not valid[start] or ocean[start]:
        raise ValueError('apex must be valid land')
    apex=(origin_xz_m[0]+start[1]*spacing_m, origin_xz_m[1]+start[0]*spacing_m)
    forward,lateral=forward_fields(bed.shape,origin_xz_m,spacing_m,apex,direction_xz)
    # Allow a short source-ground bridge between the surveyed mouth and deposit.
    bridge=valid & ~ocean & (original < 3.) & (forward >= -2*spacing_m) & (forward <= 4*spacing_m)
    land=valid & ~ocean & (plain | bridge) & (forward >= -2*spacing_m) & (np.abs(lateral) <= np.maximum(forward, 0)*.8 + 3*spacing_m)
    land[start]=True
    coast=land & ndimage.binary_dilation(ocean,structure=np.ones((3,3)))
    costs=np.full(bed.shape,np.inf)
    costs[land]=1.+np.maximum(bed[land],0.)*.15
    mcp=MCP_Geometric(costs,fully_connected=True)
    dist,_=mcp.find_costs([start])
    candidates=np.argwhere(coast & np.isfinite(dist) & (forward >= 4*spacing_m))
    proposals=[]
    for p in candidates[::max(1,len(candidates)//600)]:
        p=tuple(p); path=mcp.traceback(p)
        coords=np.asarray(path); f=forward[coords[:,0],coords[:,1]]
        length=np.linalg.norm(np.diff(coords,axis=0),axis=1).sum()*spacing_m
        if len(path)<5 or length<=0 or f[-1]/length < .55 or np.min(np.diff(f)) < -1.5*spacing_m:
            continue
        proposals.append((p,path,float(f[-1]),float(lateral[p]),length))
    if len(proposals)<2:
        raise ValueError('fewer than two seaward-progressing outlet candidates')
    chosen=[]
    while len(chosen)<outlet_count:
        options=[]
        for item in proposals:
            p,path,f,side,length=item
            if any(p in v[1] or v[0] in path for v in chosen): continue
            if chosen:
                sep=min(np.linalg.norm(np.subtract(p,v[0]))*spacing_m for v in chosen)
                if sep < 3*spacing_m: continue
                score=sep+f*.2
            else: score=f
            options.append((score,item))
        if not options: break
        chosen.append(max(options,key=lambda v:v[0])[1])
    if len(chosen)<2: raise ValueError('not enough separated seaward outlets')
    children={}
    for _,path,_,_,_ in chosen:
        for a,b in zip(path,path[1:]): children.setdefault(tuple(a),set()).add(tuple(b))
    terminals={tuple(v[0]) for v in chosen}
    nodes={start}|terminals|{p for p,c in children.items() if len(c)>1}
    edges=[]
    def walk(node,parent):
        for child in sorted(children.get(node,())):
            points=[node,child]
            while child not in nodes:
                child=next(iter(children[child])); points.append(child)
            i=len(edges); edges.append(dict(parent=parent,points=points)); walk(child,i)
    walk(start,-1)
    if not edges: raise ValueError('empty network')
    descendants=np.zeros(len(edges))
    for i in reversed(range(len(edges))):
        downstream=[j for j,e in enumerate(edges) if e['parent']==i]
        descendants[i]=sum(descendants[j] for j in downstream) if downstream else 1.
    carved=bed.copy(); river=np.zeros(bed.shape,bool); rows=[]; lengths=[]
    for i,e in enumerate(edges):
        parent=e['parent']; siblings=[j for j,v in enumerate(edges) if v['parent']==parent]
        incoming=discharge_m3_s if parent<0 else edges[parent]['q']
        q=incoming*descendants[i]/sum(descendants[j] for j in siblings); e['q']=q
        width=float(formative_section(q,*material,max_width_m=max_width_m).width_m)
        depth=min(3.,.6*q**.28581553)
        points=np.asarray(e['points'])
        lengths.append(float(np.linalg.norm(np.diff(points,axis=0),axis=1).sum()*spacing_m))
        for z,x in e['points']:
            stage=min(float(bed[z,x]), max(.5, float(bed[start])-max(forward[z,x],0.)*.0002))
            incision=float(channel_section_cut(0.,width,depth))
            target=min(bed[z,x],stage-incision)
            if target < original[z,x]-3.:
                raise ValueError('channel exceeds original-material incision limit')
            carved[z,x]=min(carved[z,x],target); river[z,x]=True
            rows.append((i,origin_xz_m[0]+x*spacing_m,origin_xz_m[1]+z*spacing_m,z,x,stage,width,depth,q,carved[z,x]))
    sections=np.asarray(rows,float)
    # Junction cells are shared; ensure every saved bed value matches final DEM.
    sections[:,9]=carved[sections[:,3].astype(int),sections[:,4].astype(int)]
    return dict(bed_m=carved,river=river,sections=sections,parent=np.array([e['parent'] for e in edges]),
                length_m=np.asarray(lengths), inlet_zx=start,outlet_zx=[v[0] for v in chosen],
                path_forward_ratio=[v[2]/v[4] for v in chosen],
                width_provenance='formative_section baseline; sediment unknown',material=material)




def attach_source_reach(network, source_path_zx, geological_bed_m, origin_xz_m, spacing_m,
                        discharge_m3_s, *, material=(.35,.35,0.,.25), max_width_m=2000.):
    """Attach an observed receiver-chain segment upstream of the delta root.

    source_path_zx is ordered upstream to downstream and ends exactly at inlet.
    Source-relative section cuts are initialized independently of tidal dynamics.
    """
    path=np.asarray(source_path_zx,dtype=int)
    if path.ndim!=2 or path.shape[1]!=2 or len(path)<2 or tuple(path[-1]) != tuple(network['inlet_zx']):
        raise ValueError('source path must end at the delta inlet')
    if np.any(np.max(np.abs(np.diff(path,axis=0)),axis=1)!=1):
        raise ValueError('source path must be an adjacent receiver chain')
    bed=np.asarray(geological_bed_m,float); carved=network['bed_m'].copy()
    if np.any(path<0) or np.any(path[:,0]>=bed.shape[0]) or np.any(path[:,1]>=bed.shape[1]):
        raise ValueError('source path outside bed')
    q=float(discharge_m3_s)
    width=float(formative_section(q,*material,max_width_m=max_width_m).width_m)
    depth=min(3.,.6*q**.28581553)
    rows=[]
    for z,x in path:
        stage=float(bed[z,x])
        carved[z,x]=min(carved[z,x],bed[z,x]-float(channel_section_cut(0.,width,depth)))
        rows.append((0,origin_xz_m[0]+x*spacing_m,origin_xz_m[1]+z*spacing_m,z,x,stage,width,depth,q,carved[z,x]))
    old=network['sections'].copy(); old[:,0]+=1
    sections=np.vstack((np.asarray(rows),old))
    sections[:,9]=carved[sections[:,3].astype(int),sections[:,4].astype(int)]
    parent=np.asarray(network['parent'])+1
    parent[parent==0]=0
    river=network['river'].copy(); river[path[:,0],path[:,1]]=True
    length=float(np.linalg.norm(np.diff(path,axis=0),axis=1).sum()*spacing_m)
    return {**network,'bed_m':carved,'river':river,'sections':sections,
            'parent':np.r_[-1,parent], 'length_m':np.r_[length,network['length_m']],
            'source_path_zx':path}


