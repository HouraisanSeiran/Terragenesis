"""Source-bound segmented tidal model with partitioned subgrid storage."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import argparse
import json
import time
import numpy as np
from numba import njit
from scipy.ndimage import binary_propagation
from terrain_pipeline.large_delta_tidal_source import load_source
from terrain_pipeline.large_delta_tidal_reconstruction import reconstruct_coastal_water
from terrain_pipeline.large_delta_tidal_dynamics import Geometry, State, bed_elevation, step, tide_stage, save_checkpoint, load_checkpoint
from terrain_pipeline.surface_rivers.metric_coastal_transport import _face_transfer


@dataclass(frozen=True)
class Config:
    block: int = 10
    reach_length_m: float = 180.
    dt_s: int = 15
    tide: bool = True
    waves: bool = False
    coastal_conductance_m2_s: float = 280.
    # Least-squares fit to source branch discharge and end-stage drops.
    river_conductance_per_width_m_s: float = 13.473374756873183
    sea_conductance_m2_s: float = 280.
    wave_height_m: float = .4
    wave_period_s: float = 5.
    wave_direction_xz: tuple = (1, 0)
    wave_rate_s: float = 1.e-7


@njit
def volume_stage(sorted_bed, sorted_area, water, shift):
    result=np.empty(len(water)); wetted=np.empty(len(water))
    for i in range(len(water)):
        volume=max(water[i],0.)
        area=0.; previous=sorted_bed[i,0]+shift[i]
        level=previous
        for j in range(sorted_bed.shape[1]):
            elevation=sorted_bed[i,j]+shift[i]
            required=area*(elevation-previous)
            if area > 0 and volume < required:
                level=previous+volume/area
                break
            volume-=required
            area+=sorted_area[i,j]
            previous=elevation
            level=elevation
        else:
            if area>0: level=previous+volume/area
        result[i]=level
        wetted[i]=max(area,1.)
    return result,wetted


def prepare(source, config=Config()):
    b=config.block
    if config.dt_s <= 0 or (config.waves and 300 % config.dt_s != 0):
        raise ValueError('wave mode requires a positive timestep dividing 300 seconds')
    z0,z1,x0,x1=source['manifest']['patches']['coastal_band_z0_z1_x0_x1']
    # Extra perimeter gives tide water a real path from open ocean to the mouths.
    z0=max(0,(z0//b)*b-10*b);x0=max(0,(x0//b)*b-10*b)
    z1=min(2000,((z1+b-1)//b)*b+10*b);x1=min(2000,((x1+b-1)//b)*b+10*b)
    nz,nx=(z1-z0)//b,(x1-x0)//b; n=nz*nx
    bed_native=source['initial_bed_m'][z0:z1,x0:x1]
    floor_native=source['active_layer']['floor_m'][z0:z1,x0:x1]
    valid_native=source['valid'][z0:z1,x0:x1]
    ocean_native=source['source_ocean'][z0:z1,x0:x1]
    def cells(a): return a.reshape(nz,b,nx,b).transpose(0,2,1,3).reshape(n,b*b)
    # Deduplicate shared junction cells. Each assigned pixel is split into a
    # subpixel channel footprint and complementary coastal area.
    owner=np.full(bed_native.shape,-1,np.int32); fraction=np.zeros(bed_native.shape)
    river_nodes=[]; branch_nodes=[]; branch=source['reach_segments']; widths=source['network']['branch_width_m']
    centreline=np.zeros(bed_native.shape,bool)
    for section in branch:
        rr=np.rint((section[:,3]-source['z_m'][0])/30).astype(int)-z0
        cc=np.rint((section[:,2]-source['x_m'][0])/30).astype(int)-x0
        centreline[rr,cc]=True
    for bi,section in enumerate(branch):
        rows=np.rint((section[:,3]-source['z_m'][0])/30).astype(int)-z0
        cols=np.rint((section[:,2]-source['x_m'][0])/30).astype(int)-x0
        if np.any((rows<0)|(rows>=bed_native.shape[0])|(cols<0)|(cols>=bed_native.shape[1])): raise ValueError('channel outside domain')
        distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(section[:,2:4],axis=0),axis=1))]
        bins=np.floor(distance/config.reach_length_m).astype(int)
        nodes=[]
        for group in np.unique(bins):
            idx=np.flatnonzero(bins==group); rr=rows[idx];cc=cols[idx]
            keep=owner[rr,cc]<0;rr=rr[keep];cc=cc[keep]
            if not len(rr): continue
            node=len(river_nodes); owner[rr,cc]=node
            # For widths above one native pixel, place the remaining analytic
            # area in an adjacent, non-centreline subpixel footprint.
            fraction[rr,cc]=min(float(widths[bi])/30.,1.)
            extra=max(float(widths[bi])/30.-1.,0.)
            if extra:
                accepted=[]
                for j,(r,c) in enumerate(zip(rr,cc)):
                    sample=idx[keep][j]; lo=max(sample-1,0);hi=min(sample+1,len(section)-1)
                    dx=section[hi,2]-section[lo,2];dz=section[hi,3]-section[lo,3]
                    offsets=((-1,0),(1,0),(0,-1),(0,1)) if abs(dx)>=abs(dz) else ((0,-1),(0,1),(-1,0),(1,0))
                    for dr,dc in offsets:
                        r2,c2=r+dr,c+dc
                        if 0<=r2<owner.shape[0] and 0<=c2<owner.shape[1] and valid_native[r2,c2] and owner[r2,c2]<0 and not centreline[r2,c2]:
                            owner[r2,c2]=node;fraction[r2,c2]=extra;accepted.append((r2,c2));break
                    else: raise ValueError('no free subpixel channel footprint')
                if accepted:
                    addition=np.asarray(accepted);rr=np.r_[rr,addition[:,0]];cc=np.r_[cc,addition[:,1]]
            river_nodes.append((bi,rr,cc,section[idx[keep]]))
            nodes.append(node)
        if not nodes: raise ValueError('empty branch')
        branch_nodes.append(nodes)
    # Raster supercover samples include diagonal steps; normalize each
    # branch footprint to its saved analytic width times saved length.
    for bi,nodes in enumerate(branch_nodes):
        mask=np.isin(owner,nodes)
        measured=fraction[mask].sum()*900.
        target=widths[bi]*source['network']['branch_length_m'][bi]
        fraction[mask]*=target/measured
        if np.any(fraction[mask]>1.+1.e-12): raise ValueError('channel footprint exceeds available native area')
    channel_area=fraction*900.; coast_area=(1.-fraction)*900.*valid_native
    coast_cells_area=cells(coast_area); coast_cells_bed=cells(bed_native); coast_cells_floor=cells(floor_native)
    area_coast=coast_cells_area.sum(1)
    if np.any(area_coast<=0): raise ValueError('invalid empty coastal block')
    mean_bed=(coast_cells_bed*coast_cells_area).sum(1)/area_coast
    mean_floor=(coast_cells_floor*coast_cells_area).sum(1)/area_coast
    node_area=[];node_bed=[];node_floor=[];node_stage=[]
    for bi,rr,cc,section in river_nodes:
        weights=channel_area[rr,cc]; a=weights.sum();node_area.append(a)
        node_bed.append(np.dot(bed_native[rr,cc],weights)/a);node_floor.append(np.dot(floor_native[rr,cc],weights)/a)
        node_stage.append(np.mean(section[:,5]))
    area=np.r_[area_coast,node_area];base_bed=np.r_[mean_bed,node_bed];floor=np.r_[mean_floor,node_floor]
    stock=(base_bed-floor)*area*.6
    ocean=cells(ocean_native).any(1).reshape(nz,nx); valid=cells(valid_native).all(1).reshape(nz,nx)
    seed=np.zeros((nz,nx),bool);seed[0,:]=seed[-1,:]=True;seed[:,0]=seed[:,-1]=True
    connected=binary_propagation(seed&ocean,mask=ocean&valid)
    # Deep-water cells are an offshore open-boundary reservoir, connected
    # through source-classified ocean to the domain perimeter. Mouth cells
    # are never selected by location or outlet identity.
    boundary=np.flatnonzero(((seed | (mean_bed.reshape(nz,nx)<-40.))&connected).ravel())
    if not len(boundary): raise ValueError('no connected ocean perimeter')
    left=[];right=[];cond=[];offset=[]; wave_x=[]; wave_z=[]
    # A lower quantile supplies a bounded subcell face sill; local relief is
    # otherwise represented by the volume-height curve, not mean-bed filling.
    sill=np.quantile(coast_cells_bed,.2,axis=1)
    for z in range(nz):
        for x in range(nx):
            if not valid[z,x]: continue
            for dz,dx in ((0,1),(1,0)):
                zz,xx=z+dz,x+dx
                if zz<nz and xx<nx and valid[zz,xx]:
                    a=z*nx+x;c=zz*nx+xx;left.append(a);right.append(c);cond.append(config.coastal_conductance_m2_s)
                    offset.append(max(sill[a],sill[c])-max(mean_bed[a],mean_bed[c]));wave_x.append(dx);wave_z.append(dz)
    coast_faces=len(left)
    def face(a,c,width):
        def half_length(node):
            if node < n: return 15.*b
            river=node-n; branch_id=river_nodes[river][0]
            return .5*area[node]/widths[branch_id]
        distance=half_length(a)+half_length(c)
        conductance=width*config.river_conductance_per_width_m_s*config.reach_length_m/max(distance,30.)
        left.append(a);right.append(c);cond.append(conductance);offset.append(0.)
    for bi,nodes in enumerate(branch_nodes):
        for a,c in zip(nodes[:-1],nodes[1:]):face(n+a,n+c,widths[bi])
        parent=int(source['parent'][bi])
        if parent>=0: face(n+branch_nodes[parent][-1],n+nodes[0],min(widths[bi],widths[parent]))
    outlet_faces=[]
    for bi in source['leaf_indices']:
        node=branch_nodes[bi][-1];section=branch[bi];row=int(round((section[-1,3]-source['z_m'][0])/30))-z0;col=int(round((section[-1,2]-source['x_m'][0])/30))-x0
        coast=(row//b)*nx+col//b;outlet_faces.append(len(left));face(n+node,coast,widths[bi])
    # Exchange with the local floodplain once the adjacent native bank is
    # overtopped. The bank sill is the median non-channel D4 neighbour bed.
    for i, (_, rr, cc, _) in enumerate(river_nodes):
        neighbours = []
        for r, c in zip(rr, cc):
            for dr, dc in ((-1,0),(1,0),(0,-1),(0,1)):
                y, x = r+dr, c+dc
                if 0 <= y < owner.shape[0] and 0 <= x < owner.shape[1] and owner[y,x] < 0 and valid_native[y,x]:
                    neighbours.append((y,x))
        if not neighbours:
            continue
        coords = np.asarray(neighbours)
        coast = int(np.bincount((coords[:,0]//b)*nx+coords[:,1]//b).argmax())
        sill_height = float(np.median(bed_native[coords[:,0],coords[:,1]]))
        left.append(n+i); right.append(coast)
        cond.append(config.coastal_conductance_m2_s)
        offset.append(sill_height-max(base_bed[n+i],base_bed[coast]))
    geometry=Geometry(area,floor,np.asarray(left,int),np.asarray(right,int),np.asarray(cond),boundary,np.full(len(boundary),config.sea_conductance_m2_s))
    water_coast=(np.maximum(-coast_cells_bed,0)*coast_cells_area*cells(ocean_native)).sum(1)
    water=np.r_[water_coast,np.maximum(np.asarray(node_stage)-node_bed,0)*node_area]
    order=np.argsort(coast_cells_bed,axis=1); sorted_bed=np.take_along_axis(coast_cells_bed,order,axis=1);sorted_area=np.take_along_axis(coast_cells_area,order,axis=1)
    state=State(0.,water,stock.copy(),np.zeros(len(area)))
    return dict(config=config,geometry=geometry,state=state,bounds=(z0,z1,x0,x1),shape=(nz,nx),ncoast=n,owner=owner,channel_area=channel_area,coast_area=coast_area,river_nodes=river_nodes,branch_nodes=branch_nodes,outlet_faces=np.array(outlet_faces),initial_bed=base_bed,initial_stock=stock.copy(),initial_water=water.sum(),initial_solid=stock.sum(),sorted_bed=sorted_bed,sorted_area=sorted_area,face_offset=np.array(offset),ocean=ocean,valid=valid,coast_faces=coast_faces,boundary=boundary)


def stages(p,s):
    g=p['geometry'];n=p['ncoast'];bed=bed_elevation(g,s);stage=bed+s.water_m3/g.area_m2
    stage[:n],wet_area=volume_stage(p['sorted_bed'],p['sorted_area'],s.water_m3[:n],bed[:n]-p['initial_bed'][:n])
    return stage,np.r_[wet_area,g.area_m2[n:]]


def wave_step(p,s,dt):
    """Adapt donor-limited D4 face transfer from metric_coastal_transport.

    Prescribed longshore drift, with activity bounded to wet shallow cells;
    directional flux moves existing bed inventory and never supplies solid.
    """
    c=p['config'];n=p['ncoast'];shape=p['shape'];stage=stages(p,s)[0][:n];bed=bed_elevation(p['geometry'],s)[:n]
    depth=np.maximum(stage-bed,0).reshape(shape); wet=depth>0.05
    activity=np.clip((c.wave_height_m/np.maximum(depth,.05))**2,0,1)*wet
    drift=np.asarray(c.wave_direction_xz,float);norm=np.linalg.norm(drift)
    if norm==0: return 0.
    drift=drift/norm
    inventory=s.bed_solid_m3[:n].reshape(shape)
    fraction=np.full(shape,c.wave_rate_s*dt*(c.wave_height_m/.4)**2*(5./c.wave_period_s))
    updated,_,gross=_face_transfer(inventory,np.full(shape,drift[0]),np.full(shape,drift[1]),fraction,activity,wet,wet)
    s.bed_solid_m3[:n]=updated.ravel()
    return gross


def run(p,source,end_s,state=None,sample_s=3600):
    g=p['geometry'];c=p['config'];s=p['state'] if state is None else state
    times=source['forcing']['time_seconds'];qw=source['forcing']['interval_water_q_m3_s'];qs=source['forcing']['interval_delivered_solid_m3_s']
    if end_s>times[-1] or end_s<s.time_s: raise ValueError('outside finite source event')
    records=[];low=None;high=None;wave_gross=0.;t0=time.perf_counter();next_sample=s.time_s
    source_node=p['ncoast']+p['branch_nodes'][0][0]
    while s.time_s<end_s-1e-8:
        day=min(np.searchsorted(times,s.time_s,side='right')-1,len(qw)-1);dt=min(c.dt_s,end_s-s.time_s,times[day+1]-s.time_s)
        sea=tide_stage(s.time_s+dt/2) if c.tide else 0.
        stage,storage=stages(p,s)
        packet=step(g,s,dt,sea,source_node,qw[day],qs[day],stage_override=stage,face_crest_offset=p['face_offset'],storage_area=storage)
        if c.waves and abs(s.time_s % 300.) < 1.e-8:
            moved=wave_step(p,s,300.);wave_gross+=moved;s.wave_bed_transfer_m3+=moved
        if s.time_s>=next_sample-1e-8:
            st=stages(p,s)[0];f=p['outlet_faces']; records.append(np.r_[s.time_s,sea,packet['internal_water_m3'][f]/dt,packet['internal_solid_m3'][f]/dt,st[g.left[f]],st[g.right[f]]])
            next_sample+=sample_s
            if s.time_s>=end_s-86400:
                snap=(sea,s.time_s,s.water_m3.copy(),s.bed_solid_m3.copy())
                if low is None or sea<low[0]:low=snap
                if high is None or sea>high[0]:high=snap
    return dict(state=s,records=np.array(records),low=low,high=high,elapsed_s=time.perf_counter()-t0,wave_gross_m3=s.wave_bed_transfer_m3)


def native_fields(source,p,water,stock):
    """Project partitioned graph stocks and volumes to native area-weighted fields."""
    z0,z1,x0,x1=p['bounds'];nz,nx=p['shape'];b=p['config'].block;n=p['ncoast'];g=p['geometry']
    initial=source['initial_bed_m'];local=initial[z0:z1,x0:x1];floor=source['active_layer']['floor_m'][z0:z1,x0:x1]
    layer=np.maximum(local-floor,0.);ca=p['coast_area'];ra=p['channel_area'];owner=p['owner'];
    def cells(a):return a.reshape(nz,b,nx,b).transpose(0,2,1,3).reshape(n,b*b)
    def expand(a):return np.repeat(np.repeat(a.reshape(nz,nx),b,0),b,1)
    diff=stock[:n]-p['initial_stock'][:n];den=p['initial_stock'][:n]
    factor=np.divide(np.minimum(diff,0),den,out=np.zeros_like(diff),where=den>0)
    coast_delta=layer*expand(factor)+expand(np.maximum(diff,0)/(g.area_m2[:n]*.6))
    river_delta=np.zeros_like(local);idx=owner>=0;idx_node=owner[idx]+n
    rdiff=stock[idx_node]-p['initial_stock'][idx_node];rstock=p['initial_stock'][idx_node]
    rf=np.divide(np.minimum(rdiff,0),rstock,out=np.zeros_like(rdiff),where=rstock>0)
    river_delta[idx]=layer[idx]*rf+np.maximum(rdiff,0)/(g.area_m2[idx_node]*.6)
    # One native bed is the area-weighted combined subpixel surface; the two
    # constituent surfaces are retained when calculating the water volume.
    bed=initial.copy(); bed[z0:z1,x0:x1]=local+(coast_delta*ca+river_delta*ra)/900.
    coast_bed=local+coast_delta; cb=cells(coast_bed);areas=cells(ca)
    order=np.argsort(cb,axis=1);sb=np.take_along_axis(cb,order,axis=1);sa=np.take_along_axis(areas,order,axis=1)
    levels,_=volume_stage(sb,sa,water[:n],np.zeros(n));coast_level=expand(levels)
    coast_depth=np.maximum(coast_level-coast_bed,0.)
    river_depth=np.zeros_like(local);river_surface=np.full_like(local,np.nan)
    for i,(_,rr,cc,_) in enumerate(p['river_nodes']):
        weights=ra[rr,cc];heights=local[rr,cc]+river_delta[rr,cc];order=np.argsort(heights)
        lvl,_=volume_stage(heights[order][None,:],weights[order][None,:],np.array([water[n+i]]),np.zeros(1))
        river_depth[rr,cc]=np.maximum(lvl[0]-heights,0.);river_surface[rr,cc]=lvl[0]
    depth=np.zeros(initial.shape,np.float32);depth[z0:z1,x0:x1]=((coast_depth*ca+river_depth*ra)/900.).astype(np.float32)
    coverage=np.zeros(initial.shape,bool);coverage[z0:z1,x0:x1]=source['valid'][z0:z1,x0:x1]
    coast_stage=np.full(initial.shape,np.nan,np.float32);coast_stage[z0:z1,x0:x1]=np.where(coast_depth>0,coast_level,np.nan)
    river_stage=np.full(initial.shape,np.nan,np.float32);river_stage[z0:z1,x0:x1]=np.where(river_depth>0,river_surface,np.nan)
    fraction=np.zeros(initial.shape,np.float32);fraction[z0:z1,x0:x1]=ra/900.
    return dict(bed_m=bed,water_depth_m=depth,coast_stage_m=coast_stage,river_stage_m=river_stage,channel_fraction=fraction,coverage=coverage)



def project_native_snapshots(native, bounds, ocean_seed, iterations=120):
    """Conservative face-local subgrid representation; mixed pixels are fixed."""
    z0,z1,x0,x1=bounds; region=np.s_[z0:z1,x0:x1]
    area=np.where(native['coverage'][region] & (native['channel_fraction'][region] == 0),900.,0.)
    for name,bed_key,depth_key in (('final','bed_m','water_depth_m'),('low','low_bed_m','low_depth_m'),('high','high_bed_m','high_depth_m')):
        if depth_key not in native: continue
        native[depth_key]=native[depth_key].astype(np.float64)
        bed=native[bed_key][region]; old=native[depth_key][region]
        depth=reconstruct_coastal_water(bed,area,np.where(area>0,old,0.),iterations=iterations)
        native[depth_key][region]=np.where(area>0,depth,old)
        stage_key='coast_stage_m' if name=='final' else name+'_coast_stage_m'
        if stage_key not in native: native[stage_key]=np.full(native['coverage'].shape,np.nan,np.float32)
        stage=native[stage_key][region]
        stage[area>0]=np.where(depth[area>0]>0,bed[area>0]+depth[area>0],np.nan)
        wet=(native[depth_key]>0)&native['coverage']
        # Equivalent area-weighted surface, including fixed mixed pixels.
        native['water_stage_m' if name=='final' else name+'_stage_m']=np.where(wet,native[bed_key]+native[depth_key],np.nan).astype(np.float32)
        sea=binary_propagation(ocean_seed&wet,mask=wet)
        native['water_class' if name=='final' else name+'_water_class']=np.where(sea,1,np.where(wet,2,0)).astype(np.uint8)
    return native

def save_product(path,source,p,result,source_path):
    import os
    path=Path(path);path.mkdir(parents=True,exist_ok=False);s=result['state'];native=native_fields(source,p,s.water_m3,s.bed_solid_m3)
    for name in ('low','high'):
        snap=result[name]
        if snap is not None:
            fields=native_fields(source,p,snap[2],snap[3]); native[name+'_bed_m']=fields['bed_m'];native[name+'_depth_m']=fields['water_depth_m'];native[name+'_time_s']=snap[1]
    wet=(native['water_depth_m']>0)&native['coverage'];ocean_seed=np.zeros(wet.shape,bool)
    z0,z1,x0,x1=p['bounds']; local=np.zeros(p['shape'],bool);local.ravel()[p['boundary']]=True
    ocean_seed[z0:z1,x0:x1]=np.repeat(np.repeat(local,p['config'].block,0),p['config'].block,1)&source['source_ocean'][z0:z1,x0:x1]
    project_native_snapshots(native,p['bounds'],ocean_seed)
    native['origin_xz_m']=[source['x_m'][0],source['z_m'][0]];native['spacing_m']=30.
    np.savez_compressed(path/'native.npz',**native)
    np.savez_compressed(path/'series.npz',records=result['records'],outlet_branch=source['leaf_indices'])
    np.savez_compressed(path/'geometry.npz',area_m2=p['geometry'].area_m2,floor_m=p['geometry'].floor_m,left=p['geometry'].left,right=p['geometry'].right,conductance=p['geometry'].conductance_m2_s,boundary=p['boundary'],boundary_conductance=p['geometry'].boundary_conductance_m2_s,face_offset=p['face_offset'],initial_bed=p['initial_bed'],initial_stock=p['initial_stock'],owner=p['owner'],channel_area=p['channel_area'],sorted_bed=p['sorted_bed'],sorted_area=p['sorted_area'],outlet_faces=p['outlet_faces'])
    save_checkpoint(path/'checkpoint.npz',s)
    led=dict(initial_water_m3=float(p['initial_water']),initial_solid_m3=float(p['initial_solid']),final_water_m3=float(s.water_m3.sum()),final_bed_solid_m3=float(s.bed_solid_m3.sum()),final_mobile_solid_m3=float(s.mobile_solid_m3.sum()),source_water_m3=s.source_water_m3,source_solid_m3=s.source_solid_m3,sea_water_in_m3=s.sea_water_in_m3,sea_water_out_m3=s.sea_water_out_m3,sea_solid_out_m3=s.sea_solid_out_m3)
    led['water_residual_m3']=led['initial_water_m3']+led['source_water_m3']+led['sea_water_in_m3']-led['sea_water_out_m3']-led['final_water_m3']
    led['solid_residual_m3']=led['initial_solid_m3']+led['source_solid_m3']-led['sea_solid_out_m3']-led['final_bed_solid_m3']-led['final_mobile_solid_m3']
    led['native_water_m3']=float(native['water_depth_m'].sum(dtype=np.float64)*900.)
    led['native_bed_delta_solid_m3']=float((native['bed_m']-source['initial_bed_m']).sum(dtype=np.float64)*900*.6)
    led['graph_bed_delta_solid_m3']=float((s.bed_solid_m3-p['initial_stock']).sum())
    led['wave_gross_transfer_m3']=result['wave_gross_m3']
    m=dict(schema='segmented-tidal-v6',projection=dict(algorithm='crest-gated-native-face-exchange-v1',iterations=120,mixed_cells='held fixed'),source_identity=source['manifest']['source_identity'],world_seed=source['manifest']['world_seed'],source_manifest=os.path.relpath(Path(source_path).resolve(),path.resolve()).replace('\\','/'),config=asdict(p['config']),bounds_z0_z1_x0_x1=p['bounds'],coastal_shape=p['shape'],river_node_count=len(p['river_nodes']),elapsed_s=result['elapsed_s'],time_s=s.time_s,ledger=led,records_columns='time_s, sea_stage_m, three signed outlet water m3/s, three signed outlet solid m3/s, three reach stages m, three coast stages m',limitations='reduced head driven storage without momentum; 300m coast and approximately 180m channel reaches; native water depth area weighted over channel and coast; clear water sea; unknown external river inputs excluded, not asserted zero; native coastal projection is local conservative cross-block redistribution, not a 30m hydrodynamic solve; mixed cells fixed; checkpoint and series unchanged')
    (path/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf8');return m


def read_product(path):
    """Read existing files only; no simulation or preparation."""
    path=Path(path)
    with np.load(path/'native.npz') as a, np.load(path/'series.npz') as b, np.load(path/'geometry.npz') as c:
        return dict(native=dict(a),series=dict(b),geometry=dict(c),manifest=json.loads((path/'manifest.json').read_text(encoding='utf8')),checkpoint=load_checkpoint(path/'checkpoint.npz'))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('output');parser.add_argument('--days',type=float,default=30);parser.add_argument('--dt',type=int,default=15);parser.add_argument('--calm',action='store_true');parser.add_argument('--waves',action='store_true');parser.add_argument('--resume',help='existing product directory checkpoint');args=parser.parse_args()
    src=load_source(args.source);p=prepare(src,Config(dt_s=args.dt,tide=not args.calm,waves=args.waves))
    previous=None;state=None
    if args.resume:
        previous=read_product(args.resume)
        if previous['manifest']['config'] != json.loads(json.dumps(asdict(p['config']))) or previous['manifest']['source_identity'] != src['manifest']['source_identity']:
            raise ValueError('resume source or config differs')
        state=previous['checkpoint'];resume_time=state.time_s
    r=run(p,src,args.days*86400,state)
    if previous is not None:
        prior=previous['series']['records'];r['records']=np.concatenate((prior,r['records'][r['records'][:,0]>resume_time])) if len(r['records']) else prior
    print(json.dumps(save_product(args.output,src,p,r,args.source),indent=2))

if __name__=='__main__':main()
