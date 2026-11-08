"""Construct one source-bound multi-junction delta on a 5 m depiction grid."""
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates,distance_transform_edt
from scipy.spatial import cKDTree
from skimage.graph import MCP_Geometric
from terrain_pipeline.new_world_game_delta import bounded_subgrid_channel, retained_sediment_supply, validate_retained_supply, retained_geometry_identity
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.native_hierarchical_delta import route_tree
from terrain_pipeline.channel_geometry import channel_section_cut
from terrain_pipeline.common_infra import identity
R=Path('.scratch/river-upgrade-20261101')

def main():
 old=R/'native-map-v1';out=R/'native-map-v2'
 if out.exists():raise FileExistsError(out)
 m=json.loads((old/'manifest.json').read_text());a=np.load(old/'representative.npz'); network=R/'native-network-v2'; netmeta=json.loads((network/'manifest.json').read_text());
 if netmeta['source_identity']!=m['source_identity']:raise ValueError('network source mismatch')
 net_ids=np.load(network/'node_id.npy'); index=np.array([np.flatnonzero(net_ids==v)[0] for v in a['node_ids']]); upstream_bed=np.load(network/'node_bed_m.npy')[index]; upstream_stage=np.load(network/'node_stage_m.npy')[index]; upstream_width=np.load(network/'node_width_m.npy')[index]
 if abs(upstream_stage[0]-m['lake_stage_m'][-1])>1e-8:raise ValueError('network lake head mismatch')
 event_water=np.load(R/'native-event-v1/node_water_m3.npy',mmap_mode='r')[:,a['node_ids'][1:]];time=np.asarray(a['time_seconds']);domain=a['station_m'];points=a['points_xz_m'];source_id=m['source_identity'];mouth_id=m['mouth_id']
 supply=retained_sediment_supply(station_m=domain,points_xz_m=points,bed_m=upstream_bed,stage_m=upstream_stage,width_m=upstream_width,control_edges_m=domain,control_water_m3=event_water,time_seconds=time,source_identity=source_id,mouth_id=mouth_id,inlet_xz_m=points[-1],material=MaterialParameters(provenance='declared local finite scenario'))
 domain_id=retained_geometry_identity(domain,points,upstream_bed,upstream_stage,upstream_width,domain,points[-1],source_identity=source_id,mouth_id=mouth_id)
 solid=validate_retained_supply(supply,geometry_identity=domain_id,inlet_xz_m=points[-1],mouth_id=mouth_id,time_seconds=time,mouth_water_m3=a['mouth_water_m3'])
 source=R/'terrain-v3';root=points[-1];step=5.;half=500.;x=np.arange(root[0]-half,root[0]+half+step,step);z=np.arange(root[1]-half,root[1]+half+step,step);xx,zz=np.meshgrid(x,z);grid=np.column_stack((xx.ravel(),zz.ravel()));coord=[((zz+61440)/30).ravel(),((xx+61440)/30).ravel()];raw=np.load(source/'bed_m.npy',mmap_mode='r');sea=np.load(source/'ocean_mask.npy',mmap_mode='r');unknown=np.load(source/'unknown_mask.npy',mmap_mode='r');pool=np.load(R/'native-final-routing-v1/derived/pool_index.npy',mmap_mode='r').reshape(4096,4096)
 bed=map_coordinates(raw,coord,order=1).reshape(xx.shape).astype(float);ocean=map_coordinates(sea.astype(np.uint8),coord,order=0).reshape(xx.shape).astype(bool);bad=map_coordinates(unknown.astype(np.uint8),coord,order=0).reshape(xx.shape).astype(bool);poolcells=map_coordinates(pool,coord,order=0).reshape(xx.shape);land=~ocean & ~bad & (poolcells<0);coast=distance_transform_edt(land)*step; start=(len(z)//2,len(x)//2);land[start]=True
 # Search near-coast land southeast of this mouth; source elevation and shore
 # distance penalize disruptive inland cuts. No random geometry or elevation fill.
 rr,cc=np.indices(bed.shape);dz=(rr-start[0])*step;dx=(cc-start[1])*step;candidate=land & (coast>=5)&(coast<=35)&(dz>=130)&(dz<=260)&(np.abs(dx)<160)&(bed<3.)
 if not candidate.any():raise ValueError('no suitable bounded coastal trunk')
 landcost=np.where(land,1.+np.maximum(bed,0.)*.8+coast*.025,np.inf);landcost[start]=1.;mcp=MCP_Geometric(landcost,fully_connected=True);dist,_=mcp.find_costs([start]);score=np.where(candidate,dist+np.abs(dz-185)*.3,np.inf);target=np.unravel_index(np.argmin(score),score.shape);trunk=mcp.traceback(target)
 if len(trunk)<20:raise ValueError('trunk cannot support separated junctions')
 j1=int(len(trunk)*.38);j2=int(len(trunk)*.78);junction1=tuple(trunk[j1]);junction2=tuple(trunk[j2]);trunk=trunk[:j2+1]
 # Three terrain-cost paths to separated actual-ocean cells. The original
 # ocean classification is fixed; shallow ocean beds may be cut locally.
 paths_used=np.zeros(bed.shape,bool)
 for cell in trunk:paths_used[cell]=True
 deep=distance_transform_edt(ocean)*step; sinks=ocean & (deep>=20.) & ~bad
 paths=[]
 for branch,desired in enumerate(((-95,40),(45,55),(125,100))):
  start_cell=junction1 if branch==0 else junction2;blocked=paths_used.copy();blocked[start_cell]=False
  # Keep a small departure neighborhood open at the shared junction.
  y0,x0=start_cell;blocked[max(0,y0-1):y0+2,max(0,x0-1):x0+2]=False
  allowed=~bad & (poolcells<0) & ~blocked;allowed[start_cell]=True
  cost=np.where(allowed,1.+np.maximum(bed,0.)*.8+np.maximum(-bed-1.,0.)*.15,np.inf)
  search=MCP_Geometric(cost,fully_connected=True);ds,_=search.find_costs([start_cell]);desired_xy=np.array([root[0]+desired[0],root[1]+desired[1]]);penalty=np.hypot(xx-desired_xy[0],zz-desired_xy[1])*.35;sc=np.where(sinks,ds+penalty,np.inf)
  if not np.isfinite(sc).any():raise ValueError('no separated wet marine path')
  end=np.unravel_index(np.argmin(sc),sc.shape);branch_path=search.traceback(end)
  if len(branch_path)<3:raise ValueError('branch too short')
  paths.append(branch_path)
  for cell in branch_path[2:]:paths_used[cell]=True
 def world(cells):return np.array([[x[c],z[r]] for r,c in cells],float)
 # tree: root trunk, early distributary, trunk continuation, two late distributaries
 lines=[world(trunk[:j1+1]),world(paths[0]),world(trunk[j1:]),world(paths[1]),world(paths[2])];parents=np.array([-1,0,0,2,2]);lengths=np.array([np.linalg.norm(np.diff(line,axis=0),axis=1).sum() for line in lines]);width=np.array([float(upstream_width[-1]),3.3,4.3,2.5,2.6]);depth=np.full(5,.4);head0=float(upstream_stage[-1]);heads=[(head0,head0*.65),(head0*.65,0.),(head0*.65,head0*.3),(head0*.3,0.),(head0*.3,0.)]
 if head0<=0:raise ValueError('no freshwater head')
 profiles=[];stages=[];cuts=[];masks=[];raster_cut=np.zeros_like(bed);water_stage=np.full_like(bed,-np.inf);eligible_heads=np.full_like(bed,-np.inf);bulk=0.
 for j,line in enumerate(lines):
  cells=np.rint((line-np.array([x[0],z[0]]))/step).astype(int);source_bed=bed[cells[:,1],cells[:,0]].copy();arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))];stage=heads[j][0]+(heads[j][1]-heads[j][0])*arc/arc[-1]
  if j==0: source_bed[0]=float(a['source_bed_m'][-1])
  # Common 0.4 m depth yields the identical stage and bed on every junction.
  profile=bounded_subgrid_channel(source_bed,stage,np.full(len(line),width[j]),np.full(len(line),depth[j]),arc)
  if j==0 and abs(profile['bed_m'][0]-upstream_bed[-1])>1e-8:
   # Preserve the upstream section at root and taper to the shared 0.4 m depth.
   d=np.full(len(line),depth[j]);d[0]=stage[0]-upstream_bed[-1];profile=bounded_subgrid_channel(source_bed,stage,np.full(len(line),width[j]),d,arc)
  if j>0:
   parent=int(parents[j]); expected=profiles[parent][-1]
   if abs(profile['bed_m'][0]-expected)>1e-8:raise ValueError('junction bed mismatch')
  # Rasterize actual section operator at 5 m, preserving initial TD samples.
  dist,near=cKDTree(line).query(grid);cut=channel_section_cut(dist,width[j],profile['cut_m'][near]).reshape(bed.shape);raster_cut=np.maximum(raster_cut,cut);inside=(dist<=width[j]/2).reshape(bed.shape);water_stage=np.maximum(water_stage,np.where(inside,stage[near].reshape(bed.shape),-np.inf))
  eligible=(dist.reshape(bed.shape)<35)&~bad&(bed<stage[near].reshape(bed.shape)-.01)&(np.hypot(xx-line[-1,0],zz-line[-1,1])<150)
  eligible_heads=np.maximum(eligible_heads,np.where(eligible,stage[near].reshape(bed.shape),-np.inf));masks.append(eligible);profiles.append(profile['bed_m']);stages.append(stage);cuts.append(profile['cut_m']);bulk+=profile['construction_bulk_m3']
 if bulk>1000.:raise ValueError('construction bulk budget exceeded')
 # Outlet water must enter actual ocean and have a physically finite section.
 for j in (1,3,4):
  end=np.rint((lines[j][-1]-np.array([x[0],z[0]]))/step).astype(int)
  if not ocean[end[1],end[0]] or stages[j][-1]-profiles[j][-1]<.39:raise ValueError('marine outlet dry')
 water=np.asarray(a['mouth_water_m3']);result=route_tree(water,solid,np.diff(time),parents,lengths,width,depth,np.array(masks),step**2)
 velocity=result['edge_water_m3']/np.diff(time)[:,None]/(width*depth)
 if np.max(velocity)>3:raise ValueError('section velocity exceeds 3 m/s')
 final=bed-raster_cut+result['height_delta_m'];deposited=result['stored_solid_m3']>0
 if np.any(final[deposited]>=eligible_heads[deposited]):raise ValueError('deposition exceeds stage')
 wet=(water_stage>bed-raster_cut)&np.isfinite(water_stage)&~bad;count=max(map(len,lines));pack=lambda seq:np.array([np.pad(v,((0,count-len(v)),(0,0)),constant_values=np.nan) if v.ndim==2 else np.pad(v,(0,count-len(v)),constant_values=np.nan) for v in seq])
 gid=identity(dict(paths_xz=pack(lines),bed=pack(profiles),stage=pack(stages),cut=pack(cuts),width=width,parents=parents),dict(source=m['source_identity'],mouth=m['mouth_id'],algorithm='terrain-cost-hierarchical-v2'))
 out.mkdir();np.savez_compressed(out/'retained-sediment.npz',control_edges_m=domain,control_water_m3=event_water,station_m=domain,points_xz_m=points,section_bed_m=upstream_bed,section_stage_m=upstream_stage,section_width_m=upstream_width,**supply['result']['arrays']);np.savez_compressed(out/'delta-v2.npz',origin_xz_m=np.array([x[0],z[0]]),spacing_m=step,original_bed_m=bed,constructed_bed_m=bed-raster_cut,final_bed_m=final,original_ocean_mask=ocean,unknown_mask=bad,wet_channel_mask=wet,water_stage_m=water_stage,paths_xz_m=pack(lines),section_bed_m=pack(profiles),section_stage_m=pack(stages),section_cut_m=pack(cuts),parents=parents,length_m=lengths,width_m=width,depth_m=depth,eligible_masks=np.array(masks),time_seconds=time,mouth_water_m3=water,mouth_solid_m3=solid,**result)
 report=dict(schema='native-delta-v2',source_identity=m['source_identity'],mouth_id=m['mouth_id'],mouth_node=m['mouth_node'],lake_stage_m=m['lake_stage_m'],hydraulic_source='native-event-v1',network_source='native-network-v2',retained_sediment_identity=supply['result']['identity_sha256'],retained_geometry_identity=domain_id,retained_sediment_residual_m3=supply['result']['metadata']['global_residual'],geometry_identity=gid,junctions_xz_m=[lines[0][-1].tolist(),lines[2][-1].tolist()],parents=parents.tolist(),lengths_m=lengths.tolist(),width_m=width.tolist(),marine_leaf_indices=result['leaf_indices'].tolist(),water_m3=water.tolist(),solid_m3=solid.tolist(),stored_solid_m3=float(result['stored_solid_m3'].sum()),exported_solid_m3=float(result['edge_solid_out_m3'][:,result['leaf_indices']].sum()),max_deposition_m=float(result['height_delta_m'].max()),construction_bulk_m3=float(bulk),construction_bulk_budget_m3=1000.,max_cut_m=float(max(np.max(c) for c in cuts)),max_velocity_m_s=float(velocity.max()),outlet_depth_m=.4,method='terrain-cost coastal trunk and separated connected branches; prescribed stage, subgrid cut; kinematic tree and finite settling',limitations=['initial constructed tree not natural long-term delta','unknown upstream solid remains unknown','finite local sediment scenario, no backwater momentum solution','overlapping section excavation estimates may overcount','5m view interpolates 30m TD','upstream network spill edge status 6 has uncorrected lake-storage impact; not certified'])
 (out/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
