"""Check actual saved native hierarchical delta without replaying water."""
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import binary_propagation
from terrain_pipeline.new_world_game_delta import retained_geometry_identity
from terrain_pipeline.common_infra import identity
from tools.render_world_river_acceptance import sha256
R=Path('.scratch/river-upgrade-20261101')

def main():
 out=R/'native-map-final-v1';terrain=R/'terrain-v3';source_manifest=json.loads((terrain/'manifest.json').read_text());assert sha256(terrain/'bed_m.npy')==source_manifest['files']['bed_m'];assert sha256(terrain/'ocean_mask.npy')==source_manifest['files']['ocean_mask'];m=json.loads((out/'manifest.json').read_text());d=np.load(out/'delta-v2.npz');s=np.load(out/'retained-sediment.npz');n=R/'native-network-v4';ids=np.load(n/'node_id.npy');idx=int(np.flatnonzero(ids==m['mouth_node'])[0]);stage=float(np.load(n/'node_stage_m.npy')[idx]);bed=float(np.load(n/'node_bed_m.npy')[idx]);width=float(np.load(n/'node_width_m.npy')[idx]);assert np.isclose(stage,d['section_stage_m'][0,0]) and np.isclose(bed,d['section_bed_m'][0,0]) and np.isclose(width,d['width_m'][0]); assert np.isclose(stage,s['section_stage_m'][-1]) and np.isclose(bed,s['section_bed_m'][-1]);
 parents=d['parents'];paths=d['paths_xz_m'];stages=d['section_stage_m'];beds=d['section_bed_m'];cut=d['section_cut_m'];leaves=d['leaf_indices'];root=d['mouth_water_m3'];assert np.array_equal(parents,[-1,0,0,2,2]);split=np.unique(parents[parents>=0]);assert len(split)>=2
 depth=[];connected=binary_propagation(d['original_ocean_mask'],mask=d['original_ocean_mask']|d['wet_channel_mask'],structure=np.ones((3,3),bool))
 for i,path in enumerate(paths):
  valid=np.isfinite(path).all(axis=1);points=path[valid];cells=np.rint((points-d['origin_xz_m'])/float(d['spacing_m'])).astype(int);assert connected[cells[:,1],cells[:,0]].all();depth.append(float(np.min(stages[i,valid]-d['final_bed_m'][cells[:,1],cells[:,0]])))
  if parents[i]>=0:
   j=int(parents[i]);pj=paths[j];last=np.flatnonzero(np.isfinite(pj).all(axis=1))[-1];assert np.allclose(points[0],pj[last]) and np.isclose(stages[i,0],stages[j,last]) and np.isclose(beds[i,0],beds[j,last])
  if i in leaves:assert d['original_ocean_mask'][cells[-1,1],cells[-1,0]] and stages[i,valid][-1]-beds[i,valid][-1]>=.4-1e-9
 assert min(depth)>0 and np.nanmax(cut)<=6.;assert np.allclose(d['edge_water_m3'][:,0],root) and np.allclose(d['edge_water_m3'][:,leaves].sum(axis=1),root);assert np.isclose(d['stored_solid_m3'].sum()+d['edge_solid_out_m3'][:,leaves].sum(),d['mouth_solid_m3'].sum());assert np.array_equal(d['mouth_solid_m3'],s['exported_solid_m3'][:,-1]);
 geom=retained_geometry_identity(s['station_m'],s['points_xz_m'],s['section_bed_m'],s['section_stage_m'],s['section_width_m'],s['control_edges_m'],s['points_xz_m'][-1],source_identity=m['source_identity'],mouth_id=m['mouth_id']);assert geom==m['retained_geometry_identity'];event=R/'native-event-v3';de=R/'native-final-routing-v1/derived';mi=np.flatnonzero(np.load(de/'mouth_id.npy')==int(m['mouth_id']))[0];assert np.array_equal(root,np.load(event/'mouth_water_m3.npy')[:,mi]); network_ids=np.load(n/'node_id.npy'); control_nodes=[]
 for point in s['points_xz_m'][1:]:
  c,r=np.rint((point+61440)/30).astype(int);control_nodes.append(r*4096+c)
 assert np.array_equal(s['control_water_m3'],np.load(event/'node_water_m3.npy',mmap_mode='r')[:,control_nodes]);
 assert m['construction_bulk_m3']<=m.get('construction_bulk_budget_m3',1000.)
 assert m['representative_chain_edge_status'][0]==5
 pool=m['pool_index'];levels=np.load(event/'pool_level_m.npy')[:,pool];assert np.array_equal(levels[1:],np.asarray(m['lake_stage_m']))
 pool_records=np.flatnonzero(np.load(n/'inlet_pool_index.npy')==pool);offset=np.load(n/'wet_link_offsets.npy');values=np.load(n/'wet_link_node_id.npy');connected_pool=np.load(n/'wet_link_connected.npy');anchor=int(np.load(R/'native-final-routing-v1/derived/pool_anchor.npy')[pool]);assert any(connected_pool[k] and anchor in values[offset[k]:offset[k+1]] for k in pool_records)
 statuses=np.load(n/'edge_status.npy');bad_edges=np.flatnonzero(np.isin(statuses,[1,2,3,7]));assert len(bad_edges)==7
 edge_nodes=np.load(n/'edge_nodes.npy');world=np.load(n/'node_xz_m.npy');unresolved=[dict(edge_index=int(i),status=int(statuses[i]),source_xz_m=world[edge_nodes[i,0]].tolist(),target_xz_m=world[edge_nodes[i,1]].tolist()) for i in bad_edges]
 (out/'unresolved-edges.json').write_text(json.dumps(unresolved,indent=2),encoding='utf8')

 dg=identity(dict(paths_xz=paths,bed=beds,stage=stages,cut=cut,width=d['width_m'],parents=parents),dict(source=m['source_identity'],mouth=m['mouth_id'],algorithm='terrain-cost-hierarchical-v2'));assert dg==m['geometry_identity']
 result=dict(source_bed_and_ocean_sha256_unchanged=True,split_nodes=len(split),split_separation_m=float(np.linalg.norm(np.array(m['junctions_xz_m'][0])-m['junctions_xz_m'][1])),leaves=len(leaves),minimum_post_deposition_channel_depth_m=min(depth),maximum_sample_cut_m=float(np.nanmax(cut)),root_stage_m=stage,root_bed_m=bed,root_width_m=width,water_balance_residual_m3=(root-d['edge_water_m3'][:,leaves].sum(axis=1)).tolist(),solid_balance_residual_m3=float(d['mouth_solid_m3'].sum()-d['stored_solid_m3'].sum()-d['edge_solid_out_m3'][:,leaves].sum()),network_spill_status=int(m['representative_chain_edge_status'][0]),network_spill_storage_correction='native-event-v3 proportional capacity correction')
 (out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
