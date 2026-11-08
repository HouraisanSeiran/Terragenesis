"""Finite geological fan initialization on the approved derived TD shelf."""
import argparse,hashlib,json
from dataclasses import asdict
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from terrain_pipeline.large_delta_suite import load_source,Scenario
from terrain_pipeline.large_delta_forward import initialize_forward,forward_network,attach_source_reach
from terrain_pipeline.drainage import route as route
from terrain_pipeline.drainage import accumulate as accumulate


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('shelf',type=Path);p.add_argument('original',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 if a.output.exists():raise FileExistsError(a.output)
 m,(bed,valid,ocean)=load_source(a.shelf);original_m,(original,ov,oo)=load_source(a.original)
 if m['shelf_scenario']['parent_source_identity']!=original_m['source_identity'] or not np.array_equal(valid,ov) or not np.array_equal(ocean,oo):raise ValueError('shelf/source mismatch')
 origin=m['origin_xz_m'];h=m['spacing_m'];apex=(159,176);xy=np.array([-140160.,-27480.]);d=np.array([-4200.,8400.]);d/=np.linalg.norm(d);side=np.array([d[1],-d[0]])
 lobes=[]
 for distance,offset,radius in [(30000,0,35000),(65000,11000,40000),(97000,-8000,36000)]:
  pos=xy+d*distance+side*offset;lobes.append((float(pos[0]),float(pos[1]),radius))
 q=644.4*1e6*.5/31536000;frames=[];stats=[]
 for count in (1,2,3):
  scenario=Scenario('shelf-fan',tuple(xy),130000,644.4,300,.5,q,toe_depth_m=30,lobes_xzr_m=tuple(lobes[:count]))
  f=initialize_forward(bed,valid,ocean,origin,h,scenario,d,half_angle_tangent=.6);frames.append(f['bed_m']);stats.append({'lobe_count':count,'retained_solid_m3':f['retained_solid_m3'],'unplaced_solid_m3':f['unplaced_solid_m3'],'area_km2':f['landform_area_m2']/1e6,'forward_extent_km':float(f['forward_m'][f['landform']].max()/1000),'core_2km_area_km2':f['core_2km_area_m2']/1e6})
 if any(np.any(frames[i+1]<frames[i]-1e-9) for i in (0,1)):raise ValueError('formation stages cannot remove prior deposit')
 sea=ocean&(f['bed_m']<0);n=forward_network(f['bed_m'],bed,f['landform'],valid,sea,origin,h,apex,d,q,outlet_count=6)
 edge=np.zeros(bed.shape,bool);edge[0,:]=edge[-1,:]=True;edge[:,0]=edge[:,-1]=True
 routing=route(np.where(valid,original,0),ocean|~valid|edge,h,origin_world_xz=origin);area=accumulate(routing,(valid&~ocean).astype(float),h).discharge;cell=apex[0]*bed.shape[1]+apex[1];chain=[cell]
 while len(chain)<round(5000/h):
  donors=np.flatnonzero(routing.receiver==cell)
  if not len(donors):break
  cell=int(donors[np.argmax(area.ravel()[donors])]);chain.append(cell)
 chain=np.column_stack(np.unravel_index(chain[::-1],bed.shape));n=attach_source_reach(n,chain,f['bed_m'],origin,h,q)
 a.output.mkdir(parents=True);np.savez_compressed(a.output/'product.npz',source_bed_m=bed,original_td_m=original,geological_bed_m=f['bed_m'],final_bed_m=n['bed_m'],valid=valid,source_ocean=ocean,ocean=sea,landform=f['landform'],deposit_m=f['deposit_m'],river=n['river'],sections=n['sections'],parent=n['parent'],reach_length_m=n['length_m'],source_path_zx=chain,geological_stages_m=np.array(frames))
 report={'source':str(a.shelf),'source_identity':m['source_identity'],'source_manifest_sha256':hashlib.sha256((a.shelf/'manifest.json').read_bytes()).hexdigest(),'parent_td_identity':original_m['source_identity'],'scenario':asdict(scenario),'formation_stages':stats,'outlets_zx':[[int(x) for x in p] for p in n['outlet_zx']],'path_forward_ratio':n['path_forward_ratio'],'formation_assumptions':'three sequential geometric lobe supports; 300 m catchment denudation and 0.5 delivery define finite geological solid inventory, no implied physical duration; source shelf is separately declared tectonic scenario. 0.5 m/year runoff is declared scenario.','limitations':'geological initialization, not time-resolved lobe growth; narrow sections subgrid; short tidal event not geological forcing'}
 (a.output/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 fig,ax=plt.subplots(1,4,figsize=(17,5));extent=(origin[0]/1000,(origin[0]+bed.shape[1]*h)/1000,(origin[1]+bed.shape[0]*h)/1000,origin[1]/1000)
 for i,b in enumerate([bed,*frames]):
  ax[i].imshow(np.ma.masked_where(~valid,b),extent=extent,cmap='terrain',vmin=-30,vmax=30);ax[i].set(xlim=(-220,-100),ylim=(105,-40),title=['Shelf','Formation 1','Formation 2','Formation 3'][i],xlabel='world x km')
  if i==3:
   for j in range(len(n['parent'])):
    rows=n['sections'][n['sections'][:,0]==j];ax[i].plot(rows[:,1]/1000,rows[:,2]/1000,color='navy',lw=.6)
 ax[0].set_ylabel('world z km');fig.tight_layout();fig.savefig(a.output/'formation-stages.png',dpi=150);plt.close(fig)
 print(json.dumps(stats,indent=2))


if __name__=='__main__':main()
