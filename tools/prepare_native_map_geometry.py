"""Read-only native event to bounded representative channel and delta."""
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree
from terrain_pipeline.common_infra import identity
from terrain_pipeline.new_world_game_delta import bounded_subgrid_channel,retained_sediment_supply,validate_retained_supply,retained_geometry_identity,route_subgrid_distributaries
from terrain_pipeline.channel_geometry import build_discharge_geometry
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters

ROOT=Path('.scratch/river-upgrade-20261101')
SID='c751a09a6f02e8c336b6b9b8fb4b11b5dc67386e9a8470b0b1d90858bf1ffb72'

def main():
    event=ROOT/'native-event-v1'; source=ROOT/'terrain-v3'; routing=ROOT/'native-final-routing-v1'; derived=routing/'derived'; out=ROOT/'native-map-v1'
    if out.exists(): raise FileExistsError(out)
    meta=json.loads((event/'manifest.json').read_text(encoding='utf8'))
    if meta['source_identity']!=SID: raise ValueError('source mismatch')
    water=np.load(event/'mouth_water_m3.npy');xy=np.load(event/'mouth_world_xz_m.npy');uncertain=np.load(event/'mouth_unknown.npy')
    within=(xy[:,0]>=-26170)&(xy[:,0]<=23830)&(xy[:,1]>=-19990)&(xy[:,1]<=30010)&~uncertain
    candidates=np.flatnonzero(within);mouth=int(candidates[np.argmax(water[:,candidates].sum(axis=0))]); mouth_id=str(np.load(derived/'mouth_id.npy')[mouth]); source_node=int(np.load(derived/'mouth_source.npy')[mouth]); ocean_node=int(np.load(derived/'mouth_ocean_receiver.npy')[mouth]);
    bed=np.load(source/'bed_m.npy',mmap_mode='r');ocean=np.load(source/'ocean_mask.npy',mmap_mode='r');unknown=np.load(source/'unknown_mask.npy',mmap_mode='r'); receiver=np.load(routing/'routing/receiver.npy',mmap_mode='r'); pools=np.load(derived/'pool_index.npy',mmap_mode='r'); node_water=np.load(event/'node_water_m3.npy',mmap_mode='r');time=np.load(event/'time_seconds.npy').astype(float)
    if int(receiver[source_node])!=ocean_node or not ocean.ravel()[ocean_node]: raise ValueError('ocean receiver mismatch')
    chain=[source_node]
    for _ in range(2048):
        n=chain[-1];z,x=divmod(n,4096);parents=[r*4096+c for r in range(max(0,z-1),min(4096,z+2)) for c in range(max(0,x-1),min(4096,x+2)) if r*4096+c!=n and receiver[r*4096+c]==n]
        if not parents: raise ValueError('no upstream pool')
        parent=max(parents,key=lambda p:node_water[-1,p]);chain.append(parent)
        if pools[parent]>=0:break
    ids=np.asarray(chain[::-1]);pool=int(pools[ids[0]]);anchor=int(np.load(derived/'pool_anchor.npy')[pool]);level=np.load(event/'pool_level_m.npy')[:,pool]
    if ids[0]!=anchor or np.any(~np.isfinite(level[1:])) or np.any(node_water[:,anchor]<=0):raise ValueError('pool has no known overflow')
    r,c=np.divmod(ids,4096);points=np.column_stack((c*30-61440,r*30-61440)).astype(float);oz,ox=divmod(ocean_node,4096); sea=np.array([ox*30-61440,oz*30-61440],float)
    nodes_bed=np.asarray(bed.ravel()[ids],float);sea_bed=float(bed.ravel()[ocean_node]); seg=np.linalg.norm(np.diff(np.vstack((points,sea)),axis=0),axis=1);stations=np.r_[0.,np.cumsum(seg)];mouth_station=stations[-2]
    stage=np.minimum(level[1],level[2])*(1-stations/stations[-1]);volumes=np.asarray(node_water[:,ids],float);mouth_water=np.asarray(water[:,mouth]);
    if not np.array_equal(volumes[:,-1],mouth_water) or sea_bed>=0: raise ValueError('invalid mouth boundary')
    q=volumes/np.diff(time)[:,None];q_nodes=np.r_[q.mean(axis=0),q.mean(axis=0)[-1]];shape=(1,len(q_nodes));design=build_discharge_geometry(np.zeros(shape),q_nodes[None,:],np.ones(shape,bool),30.)['arrays'];width=design['channel_width_m'][0];depth=design['channel_depth_m'][0]
    source_bed=np.r_[nodes_bed,sea_bed];depth[0]=stage[0]-source_bed[0];depth[-1]=min(depth[-1],-sea_bed)
    if depth[0]<=0 or depth[-1]<=0:raise ValueError('lake or sea endpoint dry')
    profile=bounded_subgrid_channel(source_bed,stage,width,depth,stations)
    if profile['cut_m'][0]>1e-8 or profile['cut_m'][-1]>1e-8:raise ValueError('lake or marine bed cut')
    # Three+ controls are graph edges to the inlet, with each saved downstream outflow.
    inlet_points=points;inlet_station=stations[:-1];inlet_bed=profile['bed_m'][:-1];inlet_stage=stage[:-1];inlet_width=width[:-1];edge_water=volumes[:,1:]
    supplied=retained_sediment_supply(station_m=inlet_station,points_xz_m=inlet_points,bed_m=inlet_bed,stage_m=inlet_stage,width_m=inlet_width,control_edges_m=inlet_station,control_water_m3=edge_water,time_seconds=time,source_identity=SID,mouth_id=mouth_id,inlet_xz_m=points[-1],material=MaterialParameters(provenance='declared local finite scenario'))
    geom=retained_geometry_identity(inlet_station,inlet_points,inlet_bed,inlet_stage,inlet_width,inlet_station,points[-1],source_identity=SID,mouth_id=mouth_id)
    solid=validate_retained_supply(supplied,geometry_identity=geom,inlet_xz_m=points[-1],mouth_id=mouth_id,time_seconds=time,mouth_water_m3=mouth_water)
    # Use actual nearby marine cells, protected from excavation. Each path ends at first contact.
    cz,cx=divmod(source_node,4096);r0,c0=cz-30,cx-30;r1,c1=cz+31,cx+31;origin=np.array([c0*30-61440,r0*30-61440]);patch=np.array(bed[r0:r1,c0:c1],float);marine=np.array(ocean[r0:r1,c0:c1],bool);bad=np.array(unknown[r0:r1,c0:c1],bool)
    yy,xx=np.nonzero(marine);candidate=np.column_stack((xx*30+origin[0],yy*30+origin[1]));candidate=candidate[np.linalg.norm(candidate-points[-1],axis=1)<250];candidate=candidate[np.argsort(candidate[:,0])];
    if len(candidate)<3:raise ValueError('insufficient nearby ocean')
    targets=candidate[[0,len(candidate)//2,-1]]
    design_branch=build_discharge_geometry(np.zeros((1,1)),np.array([[mouth_water.sum()/np.diff(time).sum()/3]]),np.ones((1,1),bool),30.)['arrays'];bw=float(design_branch['channel_width_m'][0,0]);bd=float(design_branch['channel_depth_m'][0,0]);paths=[];beds=[];stages=[];cuts=[];lengths=[];masks=[];construction=0.; eligible_heads=np.full(patch.size,-np.inf)
    gr,gc=np.indices(patch.shape);grid=np.column_stack((gc.ravel()*30+origin[0],gr.ravel()*30+origin[1]));
    for target in targets:
        distance=np.linalg.norm(target-points[-1]);line=np.linspace(points[-1],target,max(3,int(np.ceil(distance/5))+1));cells=np.rint((line-origin)/30).astype(int);hit=np.flatnonzero(marine[cells[:,1],cells[:,0]])
        if not len(hit) or hit[0]<2:raise ValueError('invalid branch contact')
        line=line[:hit[0]+1];cells=cells[:hit[0]+1];s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))];raw=map_coordinates(patch,[(line[:,1]-origin[1])/30,(line[:,0]-origin[0])/30],order=1).astype(float);raw[0]=nodes_bed[-1];raw[-1]=patch[cells[-1,1],cells[-1,0]]
        if raw[-1]>=0 or np.any(bad[cells[:,1],cells[:,0]]):raise ValueError('bad marine or unknown endpoint')
        surface=inlet_stage[-1]*(1-s/s[-1]);dep=np.full(len(s),bd);dep[0]=surface[0]-inlet_bed[-1];dep[-1]=min(dep[-1],-raw[-1]);section=bounded_subgrid_channel(raw,surface,np.full(len(s),bw),dep,s)
        if abs(section['bed_m'][0]-inlet_bed[-1])>1e-7 or section['cut_m'][-1]>1e-8:raise ValueError('junction mismatch')
        dist,near=cKDTree(line).query(grid);eligible=(dist<=120)&~bad.ravel()&(patch.ravel()<surface[near]-.002)&(np.abs(patch.ravel())<6)&(np.linalg.norm(grid-line[-1],axis=1)<250)
        eligible_heads=np.maximum(eligible_heads,np.where(eligible,surface[near],-np.inf))
        paths.append(line);beds.append(section['bed_m']);stages.append(surface);cuts.append(section['cut_m']);lengths.append(s[-1]);masks.append(eligible.reshape(patch.shape));construction+=section['construction_bulk_m3']
    delta=route_subgrid_distributaries(mouth_water,solid,np.diff(time),lengths,np.full(3,bw),np.full(3,bd),np.array(masks),900.)
    if not np.allclose(delta['branch_water_m3'].sum(axis=1),mouth_water) or not np.isclose(delta['stored_solid_m3'].sum()+delta['exported_solid_m3'].sum()+delta['escrow_solid_m3'].sum(),solid.sum()): raise ArithmeticError('delta mass failure')
    deposited=delta['stored_solid_m3'].ravel()>0
    if np.any((patch+delta['height_delta_m']).ravel()[deposited] >= eligible_heads[deposited]):raise ValueError('deposition exceeds local water stage')
    nmax=max(map(len,paths));pack=lambda arrays:np.array([np.pad(a,((0,nmax-len(a)),(0,0)),constant_values=np.nan) if a.ndim==2 else np.pad(a,(0,nmax-len(a)),constant_values=np.nan) for a in arrays])
    out.mkdir();np.savez_compressed(out/'representative.npz',node_ids=ids,points_xz_m=inlet_points,station_m=inlet_station,bed_m=inlet_bed,stage_m=inlet_stage,width_m=inlet_width,source_bed_m=nodes_bed,cut_m=profile['cut_m'][:-1],node_water_m3=volumes,lake_level_m=level,sea_xz_m=sea,sea_bed_m=sea_bed,branch_paths_xz_m=pack(paths),branch_bed_m=pack(beds),branch_stage_m=pack(stages),branch_cut_m=pack(cuts),branch_width_m=np.full(3,bw),patch_origin_xz_m=origin,patch_original_bed_m=patch,patch_final_bed_m=patch+delta['height_delta_m'],patch_ocean_mask=marine,patch_unknown_mask=bad,eligible_masks=np.array(masks),time_seconds=time,mouth_water_m3=mouth_water,mouth_solid_m3=solid,**delta)
    np.savez_compressed(out/'sediment.npz',control_edges_m=inlet_station,control_water_m3=edge_water,station_m=inlet_station,points_xz_m=inlet_points,section_bed_m=inlet_bed,section_stage_m=inlet_stage,section_width_m=inlet_width,**supplied['result']['arrays'])
    report=dict(schema='native-map-v1',source_identity=SID,source_event=str(event),mouth_id=mouth_id,mouth_node=source_node,ocean_node=ocean_node,pool_index=pool,pool_anchor=anchor,node_ids=ids.tolist(),lake_stage_m=level[1:].tolist(),anchor_overflow_m3=volumes[:,0].tolist(),mouth_water_m3=mouth_water.tolist(),mouth_solid_m3=solid.tolist(),sediment_geometry_identity=geom,sediment_identity=supplied['result']['identity_sha256'],sediment_residual_m3=supplied['result']['metadata']['global_residual'],inlet_xz_m=points[-1].tolist(),junction_stage_m=float(inlet_stage[-1]),junction_bed_m=float(inlet_bed[-1]),river_length_m=float(mouth_station),river_max_cut_m=float(profile['cut_m'].max()),river_construction_bulk_m3=float(np.trapezoid(.8*width[:-1]*profile['cut_m'][:-1],inlet_station)),branch_construction_bulk_m3=construction,branch_width_m=bw,branch_lengths_m=lengths,stored_solid_m3=float(delta['stored_solid_m3'].sum()),exported_solid_m3=float(delta['exported_solid_m3'].sum()),escrow_solid_m3=float(delta['escrow_solid_m3'].sum()),max_deposition_m=float(delta['height_delta_m'].max()),scenario=meta['forcing'],limitations=['representative reach and predesigned branching, not all-mouth or natural matured delta','prescribed linearly interpolated subgrid stage, no momentum/backwater solution','local finite alluvium scenario, unknown upstream sediment excluded','subgrid construction volumes may overlap and are not sediment','pool and sea endpoint beds preserved'])
    (out/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
