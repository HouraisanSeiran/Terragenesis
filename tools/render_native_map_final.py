"""Render saved hierarchical native delta and 50 km native network."""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Patch
from terrain_pipeline.channel_geometry import channel_section_cut
from tools.render_world_river_acceptance import BOUNDS, crop_slices, colorize, sha256
R=Path('.scratch/river-upgrade-20261101')

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--output',default='native-map-final-v1')
 parser.add_argument('--event',default='native-event-v3')
 parser.add_argument('--network',default='native-network-v4')
 args=parser.parse_args()
 out=R/args.output;src=R/'terrain-v3';network=R/args.network;m=json.loads((out/'manifest.json').read_text());terrain=json.loads((src/'manifest.json').read_text());net=json.loads((network/'manifest.json').read_text());low=json.loads((R/'native-lowland-v1/manifest.json').read_text());
 if len({m['source_identity'],terrain['identity'],net['source_identity'],low['source_identity']})!=1:raise ValueError('source mismatch')
 d=np.load(out/'delta-v2.npz');center=np.array(m['junctions_xz_m']).mean(axis=0);half=260;xx=np.arange(np.floor(center[0]-half),np.ceil(center[0]+half)+1);zz=np.arange(np.floor(center[1]-half),np.ceil(center[1]+half)+1);x,z=np.meshgrid(xx,zz);coords=[((z+61440)/30).ravel(),((x+61440)/30).ravel()];grid=np.column_stack((x.ravel(),z.ravel()));raw=np.load(src/'bed_m.npy',mmap_mode='r');original_ocean=np.load(src/'ocean_mask.npy',mmap_mode='r');unknown=np.load(src/'unknown_mask.npy',mmap_mode='r');bed=map_coordinates(raw,coords,order=1).reshape(x.shape).astype(float);ocean=map_coordinates(original_ocean.astype(np.uint8),coords,order=0).reshape(x.shape).astype(bool);bad=map_coordinates(unknown.astype(np.uint8),coords,order=0).reshape(x.shape).astype(bool);cut=np.zeros_like(bed);surface=np.full_like(bed,-np.inf)
 sed=np.load(out/'retained-sediment.npz'); upstream=sed['points_xz_m']; upstream_raw=map_coordinates(raw,[(upstream[:,1]+61440)/30,(upstream[:,0]+61440)/30],order=1); all_paths=[upstream];all_stages=[sed['section_stage_m']];all_cuts=[upstream_raw-sed['section_bed_m']];all_widths=[sed['section_width_m']]
 for j,line in enumerate(d['paths_xz_m']):
  valid=np.isfinite(line).all(axis=1);all_paths.append(line[valid]);all_stages.append(d['section_stage_m'][j,valid]);all_cuts.append(d['section_cut_m'][j,valid]);all_widths.append(np.full(valid.sum(),d['width_m'][j]))
 for line,st,c,width in zip(all_paths,all_stages,all_cuts,all_widths):
  station=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))];t=np.linspace(0,station[-1],int(np.ceil(2*station[-1]))+1);dense=np.column_stack([np.interp(t,station,line[:,i]) for i in (0,1)]);distance,near=cKDTree(dense).query(grid);qcut=np.interp(t,station,c)[near];qwidth=np.interp(t,station,width)[near];profile=channel_section_cut(distance,qwidth,qcut).reshape(x.shape);cut=np.maximum(cut,profile);h=np.interp(t,station,st)[near].reshape(x.shape);surface=np.maximum(surface,np.where((distance<=qwidth/2).reshape(x.shape),h,-np.inf))
 derived=bed-cut;wet=np.isfinite(surface)&(surface>derived)&~bad;rgb_local=colorize(derived,ocean,bad,~bad,1.);rgb_local[wet]=(.19,.61,.69);extent_local=(xx[0]-.5,xx[-1]+.5,zz[-1]+.5,zz[0]-.5)
 # Quantitative deposition panel uses actual saved 5 m bed change in mm.
 deposition=d['height_delta_m']*1000;ox,oz=d['origin_xz_m'];spacing=float(d['spacing_m']);dep_extent=(ox-spacing/2,ox+(deposition.shape[1]-.5)*spacing,oz+(deposition.shape[0]-.5)*spacing,oz-spacing/2)
 fig,axs=plt.subplots(1,2,figsize=(13,6.8),layout='constrained');axs[0].imshow(rgb_local,extent=extent_local,origin='upper',interpolation='nearest');axs[0].set(xlim=(xx[0],xx[-1]),ylim=(zz[-1],zz[0]),xlabel='X east (m)',ylabel='Z south (m)',title='Derived bed and modeled wet channels')
 axs[1].imshow(rgb_local,extent=extent_local,origin='upper',interpolation='nearest');masked=np.ma.masked_where(deposition<=0,deposition);im=axs[1].imshow(masked,extent=dep_extent,origin='upper',interpolation='nearest',cmap='magma',vmin=0,vmax=max(float(deposition.max()),.001),alpha=.9);axs[1].set(xlim=(xx[0],xx[-1]),ylim=(zz[-1],zz[0]),xlabel='X east (m)',ylabel='Z south (m)',title='30-day deposited thickness (mm)');axs[0].plot([xx[0]+30,xx[0]+130],[zz[-1]-30,zz[-1]-30],color='white',lw=3);axs[0].text(xx[0]+80,zz[-1]-42,'100 m',ha='center',color='white',fontsize=9,bbox=dict(facecolor='black',alpha=.5,edgecolor='none'));fig.colorbar(im,ax=axs[1],label='mm, 5 m display grid',fraction=.046)
 fig.suptitle('Hierarchical constructed delta | same TD source and native event\n30 m source terrain; interpolated 1 m section portrayal, not new terrain resolution');fig.savefig(out/'native-delta-final-detail.png',dpi=180);plt.close(fig)
 np.savez_compressed(out/'subgrid-portrayal.npz',origin_xz_m=np.array([xx[0],zz[0]]),spacing_m=1.,source_bed_interpolated_m=bed,constructed_bed_m=derived,wet_mask=wet,original_ocean_mask=ocean)
 slices,extent=crop_slices(terrain);crop={k:np.array(np.load(src/(k+'.npy'),mmap_mode='r')[slices],copy=True) for k in ('bed_m','ocean_mask','unknown_mask','valid_mask')};rgb=colorize(crop['bed_m'],crop['ocean_mask'],crop['unknown_mask'],crop['valid_mask'],30.);lake=np.load(network/'lake_wet_mask.npy');
 if lake.shape!=rgb.shape[:2]:raise ValueError('network lake window mismatch')
 rgb[lake]=(.18,.46,.57);nodes=np.load(network/'node_xz_m.npy');edges=np.load(network/'edge_nodes.npy');status=np.load(network/'edge_status.npy');segments=nodes[edges];fig,ax=plt.subplots(figsize=(12,12));fig.subplots_adjust(left=.08,right=.98,bottom=.105,top=.94);ax.imshow(rgb,extent=extent,origin='upper',interpolation='nearest')
 for condition,color,alpha in [(np.isin(status,[0,4,5,8,10,11]),'#4ba0b6',.9)]:
  ax.add_collection(LineCollection(segments[condition],colors=color,linewidths=.55,alpha=alpha))
 # V4 path arrays are control-cell IDs. They represent real shared inlet,
 # wet-pool, corridor and marine paths, not additional simulated water.
 def ragged_segments(prefix):
  offsets=np.load(network/(prefix+'_offsets.npy')); ids=np.load(network/(prefix+'_node_id.npy'));parts=[]
  for k in range(len(offsets)-1):
   values=ids[offsets[k]:offsets[k+1]]
   if len(values)<2:continue
   row,col=np.divmod(values,4096);parts.append(np.column_stack((col*30-61440,row*30-61440)))
  return parts
 for prefix in ('inlet','wet_link','corridor','marine'):
  ax.add_collection(LineCollection(ragged_segments(prefix),colors='#4ba0b6',linewidths=.7,alpha=.95))
 unresolved=np.flatnonzero(np.isin(status,[1,2,3,7]));unresolved_xy=nodes[edges[unresolved,0]]
 ax.scatter(unresolved_xy[:,0],unresolved_xy[:,1],s=18,marker='x',color='#f4a069',linewidths=.9,zorder=5)
 ax.plot(*center,'o',ms=5,mfc='none',mec='#f1daa0');ax.set(xlim=BOUNDS[:2],ylim=(BOUNDS[3],BOUNDS[2]),xlabel='X east (m)',ylabel='Z south (m)',title='Native 30 m rivers, lakes and hierarchical delta | day 30\nRemote-style TD terrain rendering | seven minor links unresolved');ax.text(.02,.98,'N ↑',transform=ax.transAxes,va='top',color='white',bbox=dict(facecolor='black',alpha=.5,edgecolor='none'));ax.plot([10500,20500],[24000,24000],color='white',lw=3);ax.text(15500,23000,'10 km',color='white',ha='center',fontsize=9,bbox=dict(facecolor='black',alpha=.5,edgecolor='none'))
 ax.legend(handles=[Patch(color='#4ba0b6',label='Native sections and actual lake paths'),Patch(color='#bd9270',label='Seven unresolved minor links (x)'),Patch(color='#2e758f',label='Day-30 lake wet cells'),Patch(color='#1f475c',label='Original ocean')],loc='lower right',fontsize=8)
 inset=ax.inset_axes([.025,.025,.31,.31]);inset.imshow(rgb_local,extent=extent_local,origin='upper',interpolation='nearest');
 inset.set_xlim(xx[0],xx[-1]);inset.set_ylim(zz[-1],zz[0]);inset.set_xticks([]);inset.set_yticks([]);inset.set_title('Constructed local wet channels | 520 m',fontsize=8)
 fig.text(.5,.025,'Seed 20261020 · TD c751a09a6f02… · 30 m controls · day 30 uniform-runoff scenario\nRiver lines are enlarged for display; seven minor links are shown as crosses and are not certified.',ha='center',fontsize=8);fig.savefig(out/'native-50km-final.png',dpi=170,facecolor='white');plt.close(fig)
 provenance=dict(source_identity=m['source_identity'],world_seed=20261020,terrain_manifest_sha256=sha256(src/'manifest.json'),terrain_files_sha256=terrain['files'],event_manifest_sha256=sha256(R/args.event/'manifest.json'),network_manifest_sha256=sha256(network/'manifest.json'),event_relative_path=str((R/args.event).as_posix()),network_relative_path=str(network.as_posix()),terrain_relative_path=str(src.as_posix()),lowland_relative_path=str((R/'native-lowland-v1').as_posix()),lowland_manifest_sha256=sha256(R/'native-lowland-v1/manifest.json'),bounds_xz_m=list(BOUNDS),time_seconds=2592000,terrain_spacing_m=30,local_portrayal_spacing_m=1,construction_grid_spacing_m=5,scenario='saved corrected native-event-v3, two 15-day intervals',network_status='v4 accepted prescribed sections and paths; seven unresolved edges marked',figures={n:sha256(out/n) for n in ('native-50km-final.png','native-delta-final-detail.png')})
 (out/'render-provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf8');print(json.dumps(provenance,indent=2))
if __name__=='__main__':main()
