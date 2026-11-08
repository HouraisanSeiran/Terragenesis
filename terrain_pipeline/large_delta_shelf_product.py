"""Saved pre-event forward delta on the explicit, pinned shelf scenario."""
from collections import deque
from dataclasses import asdict, replace
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from scipy import ndimage
from terrain_pipeline.large_delta_suite import load_source, Scenario
from terrain_pipeline.large_delta_forward import initialize_forward, forward_network, attach_source_reach, forward_fields
from terrain_pipeline.channel_geometry import solve_shared_bed
from terrain_pipeline.drainage import route as route
from terrain_pipeline.drainage import accumulate as accumulate

SOURCE = Path('.scratch/river-width-delta-20261102/shelf-source-v3')
SOURCE_ID = 'd1db67bbcaf6335916cb6fc76a482ef702fa3be9236bba02f46fee0f0b5fd2d3'
APEX = (159,176)
DIRECTION = (-4200.,8400.)
SCENARIO = Scenario(name='shelf-local-fan-proposal',anchor_xz_m=(-140160.,-27480.),radius_m=130000.,
    catchment_km2=644.4,denudation_m=300.,delivery_fraction=.5,
    discharge_m3_s=644.4e6*.5/31536000,porosity=.4,toe_depth_m=30.)


def _sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def _source_chain(bed,valid,ocean,origin,spacing,apex,steps=8):
    boundary=np.zeros(bed.shape,dtype=bool)
    boundary[[0,-1],:]=True;boundary[:,[0,-1]]=True
    routing=route(bed,ocean|~valid|boundary,spacing,origin_world_xz=origin)
    accumulation=accumulate(routing,(valid&~ocean).astype(float),spacing).discharge.ravel()
    current=int(apex[0]*bed.shape[1]+apex[1]);chain=[current]
    for _ in range(steps):
        donors=np.flatnonzero(routing.receiver==current)
        if not len(donors):break
        current=int(donors[np.argmax(accumulation[donors])]);chain.append(current)
    chain=np.asarray(chain[::-1],dtype=np.int64)
    if len(chain)<2:
        raise ValueError('no observed upstream receiver chain')
    if not np.array_equal(routing.receiver[chain[:-1]],chain[1:]):
        raise ValueError('receiver chain inconsistent')
    return np.column_stack(np.unravel_index(chain,bed.shape))


def _bounded_bed(network,formed_bed,spacing,*, max_cut_m=7., min_drop_per_edge_m=.001):
    """Close all shared cells with strictly downstream node beds under a cut cap."""
    sections=network['sections'].copy();cols=formed_bed.shape[1]
    flat=sections[:,3].astype(np.int64)*cols+sections[:,4].astype(np.int64)
    cells,inverse=np.unique(flat,return_inverse=True)
    arcs=[]
    for i in range(len(network['parent'])):
        nodes=inverse[sections[:,0]==i]
        arcs.extend(zip(nodes[:-1],nodes[1:]))
    arcs=np.asarray(arcs,dtype=np.int64).reshape(-1,2)
    outgoing=[[] for _ in cells]; indegree=np.zeros(len(cells),dtype=np.int64)
    for a,b in arcs:
        outgoing[a].append(int(b));indegree[b]+=1
    queue=deque(np.flatnonzero(indegree==0).tolist());rank=np.zeros(len(cells),dtype=np.int64);visited=0
    while queue:
        i=queue.popleft();visited+=1
        for j in outgoing[i]:
            rank[j]=max(rank[j],rank[i]+1);indegree[j]-=1
            if indegree[j]==0:queue.append(j)
    if visited != len(cells):raise ValueError('cyclic section graph')
    # Rank shift turns minimum drop per edge into the existing monotone closure.
    before=network['bed_m'].ravel()[cells]
    shifted=before+rank*min_drop_per_edge_m
    closed,_,reasons=solve_shared_bed(shifted,arcs,max_cut_m=1e6)
    if any(r!='accepted' for r in reasons):raise ValueError('section closure failed')
    closed-=rank*min_drop_per_edge_m
    cuts=formed_bed.ravel()[cells]-closed
    if np.any(cuts>max_cut_m+1e-8) or np.any(cuts< -1e-8):
        raise ValueError('closure exceeds formed-surface cut bound')
    final=network['bed_m'].copy();final.ravel()[cells]=closed
    sections[:,9]=final.ravel()[flat]
    if len(arcs) and np.any(closed[arcs[:,1]]>closed[arcs[:,0]]-min_drop_per_edge_m+1e-8):
        raise ValueError('downstream closure failed')
    return {**network,'bed_m':final,'sections':sections},float(cuts.max()),len(arcs)


def build_shelf_fan(source_path,output_path):
    """Build and atomically publish finite formation plus bounded channel graph."""
    source_path,output_path=Path(source_path),Path(output_path)
    if output_path.exists():raise FileExistsError(output_path)
    sm,(source,valid,source_ocean)=load_source(source_path)
    if sm['source_identity'] != SOURCE_ID:raise ValueError('accepted shelf source identity required')
    unknown=np.load(source_path/'unknown_wet.npy',allow_pickle=False)
    original=np.load(source_path/'original_bed_m.npy',allow_pickle=False)
    if _sha(source_path/'unknown_wet.npy')!=sm['files_sha256']['unknown_wet']:
        raise ValueError('unknown mask identity mismatch')
    if _sha(source_path/'original_bed_m.npy')!=sm['shelf_scenario']['file_sha256']['original_bed_m']:
        raise ValueError('raw TD identity mismatch')
    if not np.array_equal(source[~source_ocean|~valid|unknown],original[~source_ocean|~valid|unknown]):
        raise ValueError('shelf changed protected source cells')
    origin=sm['origin_xz_m'];spacing=sm['spacing_m']; ocean=source_ocean & ~unknown & valid
    snapshots=[source.copy()];progress=[dict(fraction=0.,retained_solid_m3=0.,unplaced_solid_m3=0.)]
    final=None
    for fraction in (.25,.5,.75,1.):
        scenario=replace(SCENARIO,denudation_m=SCENARIO.denudation_m*fraction)
        final=initialize_forward(source,valid,ocean,origin,spacing,scenario,DIRECTION,half_angle_tangent=.6)
        snapshots.append(final['bed_m'].copy())
        progress.append(dict(fraction=fraction,retained_solid_m3=final['retained_solid_m3'],
            unplaced_solid_m3=final['unplaced_solid_m3']))
    formed=final['bed_m']; sea=ocean&(formed<0.)
    labels,_=ndimage.label(sea,structure=np.ones((3,3)))
    edge_labels=np.unique(np.r_[labels[0,:],labels[-1,:],labels[:,0],labels[:,-1]])
    connected_sea=sea & np.isin(labels,edge_labels[edge_labels>0])
    n=forward_network(formed,source,final['landform'],valid,connected_sea,origin,spacing,
        APEX,DIRECTION,SCENARIO.discharge_m3_s,outlet_count=4)
    chain=_source_chain(source,valid & ~unknown,ocean,origin,spacing,APEX)
    n=attach_source_reach(n,chain,formed,origin,spacing,SCENARIO.discharge_m3_s)
    n,maxcut,arc_count=_bounded_bed(n,formed,spacing)
    section=n['sections']; final_bed=n['bed_m']; cuts=formed-final_bed
    if np.any(cuts< -1e-8) or np.any(source-final_bed>3.+1e-8):
        raise ValueError('channel cut exceeds underlying source bound')
    ocean_final=ocean&(final_bed<0.)
    sea_labels,_=ndimage.label(ocean_final,structure=np.ones((3,3)))
    ocean_ids=np.unique(np.r_[sea_labels[0,:],sea_labels[-1,:],sea_labels[:,0],sea_labels[:,-1]])
    ocean_final &= np.isin(sea_labels,ocean_ids[ocean_ids>0])
    adjacent=ndimage.binary_dilation(ocean_final,structure=np.ones((3,3)))
    if not all(adjacent[tuple(p)] for p in n['outlet_zx']):
        raise ValueError('outlet not adjacent to boundary-connected sea')
    f,l=forward_fields(source.shape,origin,spacing,SCENARIO.anchor_xz_m,DIRECTION)
    land=final['landform']; actual_land=land&(final_bed>=0.)
    inward=ndimage.distance_transform_edt(np.pad(actual_land,1))[1:-1,1:-1]*spacing
    core=actual_land&(inward>=2000.)
    out_f=[float(f[tuple(p)]/1000) for p in n['outlet_zx']]
    bounds=lambda mask:dict(area_km2=float(mask.sum()*spacing**2/1e6),
        forward_extent_km=float(f[mask].max()/1000) if mask.any() else 0.,
        lateral_span_km=float(np.ptp(l[mask])/1000) if mask.any() else 0.)
    # Raster excavation is a coarse representation, not a resolved channel prism.
    cut_deposit=np.minimum(cuts,final['deposit_m']); cut_source=cuts-cut_deposit
    audit=dict(formed_land=bounds(land),post_cut_land=bounds(actual_land),post_cut_core_2km=bounds(core),
        outlet_forward_km=out_f,path_forward_ratio=[float(x) for x in n['path_forward_ratio']],
        outlet_zx=[list(map(int,p)) for p in n['outlet_zx']],outlet_count=len(n['outlet_zx']),
        max_cut_from_formed_m=maxcut,max_cut_below_shelf_m=float(np.max(source-final_bed)),
        downstream_arcs=arc_count,min_bed_drop_per_arc_m=.001,
        coarse_raster_excavated_bulk_m3=float(cuts.sum()*spacing**2),
        coarse_raster_removed_formation_solid_m3=float(cut_deposit.sum()*spacing**2*(1-SCENARIO.porosity)),
        coarse_raster_removed_source_bulk_m3=float(cut_source.sum()*spacing**2),
        excavation_destination='unplaced, not recycled into formation stock',
        section_water_stage='generator estimate; not reconciled after bed closure and not a solved hydraulic surface')
    arrays=dict(source_bed_m=source,original_td_bed_m=original,geological_bed_m=formed,
        final_bed_m=final_bed,valid=valid,source_ocean=source_ocean,ocean=ocean_final,
        unknown_wet=unknown,landform=land,post_cut_land=actual_land,core_2km=core,river=n['river'],
        deposit_m=final['deposit_m'],sections=section,parent=n['parent'],reach_length_m=n['length_m'],
        source_path_zx=chain,progress_bed_m=np.stack(snapshots),progress_fraction=np.array([0.,.25,.5,.75,1.]))
    output_path.parent.mkdir(parents=True,exist_ok=True)
    tmp=Path(tempfile.mkdtemp(prefix=output_path.name+'-pending-',dir=output_path.parent))
    try:
        np.savez_compressed(tmp/'product.npz',**arrays)
        metadata=dict(schema='shelf-forward-fan-formation-v1',source=str(source_path),
            source_identity=sm['source_identity'],source_manifest_sha256=_sha(source_path/'manifest.json'),
            source_original_td_identity=sm['shelf_scenario']['parent_source_identity'],
            product_sha256=_sha(tmp/'product.npz'),scenario=asdict(SCENARIO),
            formation=dict(inventory_solid_m3=SCENARIO.solid_inventory_m3,
                required_solid_m3=final['required_solid_m3'],retained_solid_m3=final['retained_solid_m3'],
                unplaced_solid_m3=final['unplaced_solid_m3'],porosity=SCENARIO.porosity,
                progress=progress,progress_policy='independent inventory-fraction initializations, not physical time',
                shelf_uplift_bulk_m3=sm['shelf_scenario']['bathymetry_uplift_bulk_m3'],
                shelf_uplift_policy='separate assumed geological bathymetry, not fluvial solid'),
            source_reach=dict(apex_zx=list(APEX),direction_xz=list(DIRECTION),source_chain_zx=chain.tolist(),
                provenance='largest donor chain on existing priority-routed source; cropped boundary, unknown external inflow'),
            audit=audit,world_seed=20261020,
            limitations='Scenario formation, source-relative bounded excavation and subgrid sections; no dynamic water or sediment event, channel excavation unplaced, water stages not certified, floodplain/ocean revalidation required.')
        (tmp/'manifest.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
        os.rename(tmp,output_path)
    except BaseException:
        shutil.rmtree(tmp);raise
    return metadata


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default=str(SOURCE));parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(json.dumps(build_shelf_fan(args.source,args.output),indent=2))


if __name__=='__main__':main()
