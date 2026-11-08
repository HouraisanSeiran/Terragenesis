"""Audit five major known native mouth/pool chains with bounded equivalent beds."""
import json
from pathlib import Path
import numpy as np
from terrain_pipeline.new_world_game_delta import bounded_subgrid_channel
from terrain_pipeline.channel_geometry import build_discharge_geometry
R=Path('.scratch/river-upgrade-20261101')

def main():
 e=R/'native-event-v1';d=R/'native-final-routing-v1/derived';t=R/'terrain-v3';routing=R/'native-final-routing-v1/routing';out=R/'native-map-v1';xy=np.load(e/'mouth_world_xz_m.npy');w=np.load(e/'mouth_water_m3.npy');u=np.load(e/'mouth_unknown.npy');sel=(xy[:,0]>=-26170)&(xy[:,0]<=23830)&(xy[:,1]>=-19990)&(xy[:,1]<=30010)&~u;ids=np.flatnonzero(sel);ids=ids[np.argsort(w[:,ids].sum(axis=0))[::-1]][:5];sources=np.load(d/'mouth_source.npy');mouth_ids=np.load(d/'mouth_id.npy');ocean=np.load(t/'ocean_mask.npy',mmap_mode='r').ravel();bed=np.load(t/'bed_m.npy',mmap_mode='r').ravel();rec=np.load(routing/'receiver.npy',mmap_mode='r');pool=np.load(d/'pool_index.npy',mmap_mode='r');anchor=np.load(d/'pool_anchor.npy');levels=np.load(e/'pool_level_m.npy');water=np.load(e/'node_water_m3.npy',mmap_mode='r');results=[]
 for i in ids:
  n=int(sources[i]);chain=[n]
  for _ in range(1000):
   z,x=divmod(n,4096);parents=[y*4096+c for y in range(max(0,z-1),min(4096,z+2)) for c in range(max(0,x-1),min(4096,x+2)) if y*4096+c!=n and rec[y*4096+c]==n]
   if not parents:break
   n=max(parents,key=lambda p:water[-1,p]);chain.append(n)
   if pool[n]>=0:break
  chain=np.array(chain[::-1]);p=int(pool[chain[0]]);down=int(rec[chain[-1]]);row,col=np.divmod(np.r_[chain,down],4096);xy2=np.column_stack((col*30-61440,row*30-61440));s=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(xy2,axis=0),axis=1))];b=np.asarray(bed[np.r_[chain,down]],float);stage=np.minimum(levels[1,p],levels[2,p])*(1-s/s[-1]);q=np.r_[np.mean(water[:,chain],axis=0)/1296000.,np.mean(w[:,i])/1296000.];g=build_discharge_geometry(np.zeros((1,len(q))),q[None,:],np.ones((1,len(q)),bool),30.)['arrays'];width=g['channel_width_m'][0];depth=g['channel_depth_m'][0];depth[0]=stage[0]-b[0];depth[-1]=min(depth[-1],-b[-1]);entry=dict(mouth_id=str(mouth_ids[i]),mouth_node=int(chain[-1]),pool_index=p,anchor_node=int(chain[0]),is_anchor=bool(anchor[p]==chain[0]),pool_levels_m=levels[1:,p].tolist(),anchor_overflow_m3=water[:,chain[0]].tolist(),mouth_water_m3=w[:,i].tolist(),ocean_contact=bool(ocean[down]),samples=len(chain))
  try:
   profile=bounded_subgrid_channel(b,stage,width,depth,s);entry.update(max_cut_m=float(profile['cut_m'].max()),min_depth_m=float(profile['depth_m'].min()),endpoint_cut_m=[float(profile['cut_m'][0]),float(profile['cut_m'][-1])],bounded_section=True)
  except ValueError as ex:entry.update(bounded_section=False,reason=str(ex))
  results.append(entry)
 (out/'chain-audit.json').write_text(json.dumps(results,indent=2),encoding='utf8');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
