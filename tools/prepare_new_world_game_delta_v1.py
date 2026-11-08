"""Prepare one representative 30-day subgrid game delta from frozen inputs."""
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree
from terrain_pipeline.new_world_game_delta import (bounded_subgrid_channel, route_subgrid_distributaries,
    retained_sediment_supply, retained_geometry_identity, validate_retained_supply)
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.channel_geometry import build_discharge_geometry
from terrain_pipeline.common_infra import identity

ROOT=Path('.scratch/river-upgrade-20261101')
SID='c751a09a6f02e8c336b6b9b8fb4b11b5dc67386e9a8470b0b1d90858bf1ffb72'

def main():
    src=ROOT/'terrain-v3'; hydro=ROOT/'game-hydro-v1'; out=ROOT/'game-delta-v1'
    if out.exists(): raise ValueError('destination exists; do not overwrite product')
    reach=np.load(ROOT/'game-delta-local-derived/reach.npz'); bed=np.load(src/'bed_m.npy',mmap_mode='r'); ocean=np.load(src/'ocean_mask.npy',mmap_mode='r'); unknown=np.load(src/'unknown_mask.npy',mmap_mode='r')
    source_manifest=json.loads((src/'manifest.json').read_text(encoding='utf8')); hydromanifest=json.loads((hydro/'manifest.json').read_text(encoding='utf8'))
    if source_manifest['identity']!=SID or hydromanifest['source_identity']!=SID: raise ValueError('source mismatch')
    m=int(np.flatnonzero(np.load(hydro/'derived/mouth_source.npy')==1112508)[0]); mouth=np.load(hydro/'mouth_world_xz_m.npy')[m]
    mid=str(np.load(hydro/'derived/mouth_id.npy')[m]); assert mid=='13966664223735675838'
    time=np.load(hydro/'time_seconds.npy'); water=np.load(hydro/'mouth_water_m3.npy')[:,m]
    # The first three graph edges end exactly at the saved mouth node. The
    # fourth historical control volume lay downstream and is excluded entirely.
    edges=np.r_[0.,np.cumsum(reach['length_m'][:3])]; terminal=edges[-1]
    k=int(np.searchsorted(reach['station_m'],terminal,side='left'))
    station=np.r_[reach['station_m'][:k],terminal]
    def trimmed(name):
        values=reach[name]
        return np.r_[values[:k],np.interp(terminal,reach['station_m'],values)]
    points=np.vstack((reach['points_xz_m'][:k],mouth)); apex=mouth.copy()
    upstream_bed=trimmed('channel_bed_m'); upstream_stage=trimmed('channel_stage_m')
    upstream_width=trimmed('section_width_m'); upstream_cut=trimmed('cut_m')
    stage0=float(upstream_stage[-1]); bed0=float(upstream_bed[-1])
    # Each finite control volume carries its saved downstream-node outflow.
    control_water=np.asarray(reach['node_water_m3'][:,1:4])
    if not np.array_equal(control_water[:,-1],water): raise ValueError('mouth water mismatch')
    supply=retained_sediment_supply(station_m=station,points_xz_m=points,bed_m=upstream_bed,
        stage_m=upstream_stage,width_m=upstream_width,control_edges_m=edges,
        control_water_m3=control_water,time_seconds=time,source_identity=SID,mouth_id=mid,
        inlet_xz_m=apex,material=MaterialParameters(provenance='local bounded scenario, uncalibrated'))
    retained_id=retained_geometry_identity(station,points,upstream_bed,upstream_stage,upstream_width,
        edges,apex,source_identity=SID,mouth_id=mid)
    solid=validate_retained_supply(supply,geometry_identity=retained_id,inlet_xz_m=apex,
        mouth_id=mid,time_seconds=time,mouth_water_m3=water)
    if stage0<=bed0 or stage0>=3.994326114654541: raise ValueError('invalid junction')
    rc=np.rint((apex[::-1]+61440)/30).astype(int); r0,c0=rc-35; r1,c1=rc+36; origin=np.array([c0*30-61440,r0*30-61440]); b=np.array(bed[r0:r1,c0:c1],float); o=np.array(ocean[r0:r1,c0:c1],bool); u=np.array(unknown[r0:r1,c0:c1],bool)
    rr,cc=np.nonzero(o); sea=np.column_stack((cc*30+origin[0],rr*30+origin[1])); distances=np.linalg.norm(sea-apex,axis=1); sea=sea[distances<250];
    if len(sea)<3: raise ValueError('insufficient nearby sea cells')
    # Separate terminal targets are actual ocean cells; construction stops at first ocean contact.
    sea=sea[np.argsort(sea[:,0])]; targets=sea[[0,len(sea)//2,-1]]
    design=build_discharge_geometry(np.zeros((1,1)),np.array([[water.sum()/np.diff(time).sum()/3]]),np.ones((1,1),bool),30.)['arrays']; width=float(design['channel_width_m'][0,0]); depth=float(design['channel_depth_m'][0,0])
    paths=[]; profiles=[]; stages=[]; cuts=[]; lengths=[]; masks=[]; construction=0.; contacts=[]
    gridr,gridc=np.indices(b.shape); grid=np.column_stack((gridc.ravel()*30+origin[0],gridr.ravel()*30+origin[1])); unknown_tree=u.ravel()
    for target in targets:
        total=np.linalg.norm(target-apex); t=np.linspace(0.,1.,int(np.ceil(total/4))+1); line=apex[None,:]+t[:,None]*(target-apex); cell=np.rint((line-origin)/30).astype(int); hit=np.flatnonzero(o[cell[:,1],cell[:,0]])
        if not len(hit) or hit[0]<2: raise ValueError('invalid first marine contact')
        line=line[:hit[0]+1]; cell=cell[:hit[0]+1]; branch_station=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))]
        if np.any(u[cell[:,1],cell[:,0]]): raise ValueError('unknown terrain')
        source=map_coordinates(b,[(line[:,1]-origin[1])/30,(line[:,0]-origin[0])/30],order=1).astype(float)
        source[0]=float(np.interp(terminal,reach['station_m'],reach['source_bed_m'])); source[-1]=b[cell[-1,1],cell[-1,0]]
        if source[-1]>=0: raise ValueError('marine boundary above sea')
        stage=stage0*(1-branch_station/branch_station[-1]); dep=np.full(len(line),depth); dep[0]=stage0-bed0; dep[-1]=min(depth,-source[-1]); section=bounded_subgrid_channel(source,stage,np.full(len(line),width),dep,branch_station)
        if abs(section['bed_m'][0]-bed0)>1e-7 or section['cut_m'][-1]>1e-8: raise ValueError('junction or ocean bed mismatch')
        # Only submerged original nearshore cells within 120 m of this channel are eligible.
        dist, near=cKDTree(line).query(grid); ds=stage[np.minimum(near,len(stage)-1)]; eligible=(dist<=120)&(~unknown_tree)&(grid[:,0]>=origin[0]); eligible &= b.ravel()<ds; eligible &= np.abs(b.ravel())<6
        eligible &= np.linalg.norm(grid-line[-1],axis=1)<250
        paths.append(line);profiles.append(section['bed_m']);stages.append(stage);cuts.append(section['cut_m']);lengths.append(branch_station[-1]);masks.append(eligible.reshape(b.shape));construction+=section['construction_bulk_m3'];contacts.append(line[-1])
    routed=route_subgrid_distributaries(water,solid,np.diff(time),lengths,np.full(3,width),np.full(3,depth),np.array(masks),900.)
    if not np.allclose(routed['branch_water_m3'].sum(axis=1),water) or not np.isclose(routed['stored_solid_m3'].sum()+routed['exported_solid_m3'].sum()+routed['escrow_solid_m3'].sum(),solid.sum()): raise ArithmeticError('mass balance')
    if any(max(c)>6 for c in cuts): raise ValueError('cut cap exceeded')
    maxn=max(map(len,paths)); pack=lambda arrays: np.array([np.pad(a,((0,maxn-len(a)),(0,0)),constant_values=np.nan) if a.ndim==2 else np.pad(a,(0,maxn-len(a)),constant_values=np.nan) for a in arrays])
    geom_id=identity({'paths':pack(paths),'bed_profiles':pack(profiles),'stages':pack(stages),'upstream_points':points,'upstream_bed':upstream_bed,'upstream_stage':upstream_stage}, {'source_identity':SID,'algorithm':'bounded-kinematic-subgrid-v1'})
    out.mkdir(); np.savez_compressed(out/'sediment.npz',control_edges_m=edges,control_water_m3=control_water,station_m=station,points_xz_m=points,section_bed_m=upstream_bed,section_stage_m=upstream_stage,section_width_m=upstream_width,upstream_node_ids=reach['node_ids'],**supply['result']['arrays']); np.savez_compressed(out/'delta.npz',original_bed_m=b,final_bed_m=b+routed['height_delta_m'],ocean_mask=o,unknown_mask=u,origin_xz_m=origin,eligible_masks=np.array(masks),paths_xz_m=pack(paths),section_bed_m=pack(profiles),section_stage_m=pack(stages),section_cut_m=pack(cuts),upstream_points_xz_m=points,upstream_bed_m=upstream_bed,upstream_stage_m=upstream_stage,upstream_cut_m=upstream_cut,upstream_width_m=upstream_width,branch_lengths_m=np.array(lengths),branch_width_m=np.full(3,width),time_seconds=time,mouth_water_m3=water,mouth_solid_m3=solid,**routed)
    report=dict(schema='game-delta-v1',stage1_status='incomplete; local intermediate diagnostic',source_identity=SID,mouth_id=mid,geometry_identity=geom_id,hydraulic_identity=supply['hydraulic_identity'],sediment_identity=supply['result']['identity_sha256'],sediment_geometry_identity=retained_id,sediment_terminal='branch inlet',sediment_residual_m3=supply['result']['metadata']['global_residual'],control_edges_m=edges.tolist(),control_water_m3=control_water.tolist(),interval_ids=['0-1296000s','1296000-2592000s'],hydraulic_model='saved game-hydro-v1 volumes plus imposed kinematic branch stages',time_seconds=time.tolist(),mouth_water_m3=water.tolist(),mouth_solid_m3=solid.tolist(),lake_stage_m=3.994326114654541,junction_stage_m=stage0,junction_bed_m=bed0,branch_width_m=width,branch_lengths_m=lengths,contacts_xz_m=np.array(contacts).tolist(),construction_bulk_m3=construction,upstream_construction_bulk_m3=float(np.trapezoid(.8*upstream_width*upstream_cut, station)),max_cut_m=max(float(max(c)) for c in cuts),stored_solid_m3=float(routed['stored_solid_m3'].sum()),exported_solid_m3=float(routed['exported_solid_m3'].sum()),escrow_solid_m3=float(routed['escrow_solid_m3'].sum()),max_deposition_m=float(routed['height_delta_m'].max()),physical_model='prescribed wet subgrid profile and kinematic width-proportional split, travel-time settling; no momentum or backwater solve',limitations=['one representative mouth; unknown upstream solids omitted','constructed branch geometry, not naturally matured','construction volume is sum of narrow-section estimates and can overcount overlaps','subgrid cross-sections; original 30m ocean mask preserved','local water volumes used once; original hydrology unchanged'])
    (out/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
if __name__=='__main__': main()
