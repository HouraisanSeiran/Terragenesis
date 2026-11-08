"""Render a local one-metre representation of native derived sections."""
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from terrain_pipeline.channel_geometry import channel_section_cut
from tools.render_world_river_acceptance import colorize, sha256
R=Path('.scratch/river-upgrade-20261101')

def main():
 out=R/'native-map-v1';a=np.load(out/'representative.npz');meta=json.loads((out/'manifest.json').read_text(encoding='utf8'));center=a['points_xz_m'][-1];xx=np.arange(center[0]-250,center[0]+251);zz=np.arange(center[1]-250,center[1]+251);x,z=np.meshgrid(xx,zz);points=np.column_stack((x.ravel(),z.ravel()));coords=[((z+61440)/30).ravel(),((x+61440)/30).ravel()];source=R/'terrain-v3';bed=np.load(source/'bed_m.npy',mmap_mode='r');ocean=np.load(source/'ocean_mask.npy',mmap_mode='r');bad=np.load(source/'unknown_mask.npy',mmap_mode='r');base=map_coordinates(bed,coords,order=1).reshape(x.shape).astype(float);marine=map_coordinates(ocean.astype(np.uint8),coords,order=0).reshape(x.shape).astype(bool);unknown=map_coordinates(bad.astype(np.uint8),coords,order=0).reshape(x.shape).astype(bool);derived=base.copy();wet=np.zeros(x.shape,bool)
 paths=[a['points_xz_m']];stages=[a['stage_m']];cuts=[a['cut_m']];widths=[a['width_m']]
 for j in range(3):
  valid=np.isfinite(a['branch_stage_m'][j]);paths.append(a['branch_paths_xz_m'][j,valid]);stages.append(a['branch_stage_m'][j,valid]);cuts.append(a['branch_cut_m'][j,valid]);widths.append(np.full(valid.sum(),a['branch_width_m'][j]))
 for path,stage,cut,width in zip(paths,stages,cuts,widths):
  arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))];sample=np.linspace(0,arc[-1],int(np.ceil(2*arc[-1]))+1);line=np.column_stack([np.interp(sample,arc,path[:,j]) for j in range(2)]);dist,near=cKDTree(line).query(points);w=np.interp(sample,arc,width)[near];c=np.interp(sample,arc,cut)[near];h=np.interp(sample,arc,stage)[near];change=channel_section_cut(dist,w,c).reshape(x.shape);local=base-change;derived=np.minimum(derived,np.where(marine,base,local));wet |= (dist.reshape(x.shape)<=w.reshape(x.shape)/2)&(h.reshape(x.shape)>local)&~marine&~unknown
 rgb=colorize(base,marine,unknown,~unknown,1);rgb[wet]=(.14,.67,.78);fig,ax=plt.subplots(figsize=(9,9),layout='constrained');ax.imshow(rgb,extent=(xx[0]-.5,xx[-1]+.5,zz[-1]+.5,zz[0]-.5),origin='upper',interpolation='nearest');ax.set(xlabel='X east (m)',ylabel='Z south (m)',title='Native representative delta | bounded wet sections\n30 m TD terrain interpolated for 1 m portrayal');ax.text(.02,.03,f"Prescribed stage; original ocean mask.\n30-day max deposition {meta['max_deposition_m']*1000:.2f} mm.",transform=ax.transAxes,color='white',fontsize=8,bbox=dict(facecolor='black',alpha=.65));fig.savefig(out/'native-delta-subgrid.png',dpi=180);plt.close(fig)
 np.savez_compressed(out/'native-delta-subgrid.npz',origin_xz_m=np.array([xx[0],zz[0]]),spacing_m=1.,source_bed_interpolated_m=base,derived_bed_m=derived,wet_subgrid_mask=wet,ocean_mask=marine);provenance_path=out/'render-provenance.json'
 if provenance_path.exists():
  provenance=json.loads(provenance_path.read_text(encoding='utf8'));provenance['figures']['native-delta-subgrid.png']=sha256(out/'native-delta-subgrid.png');provenance['representation_note']='30 m terrain interpolated to 1 m for portrayal; no new terrain resolution';provenance_path.write_text(json.dumps(provenance,indent=2),encoding='utf8')
 print(json.dumps(dict(wet_cells=int(wet.sum()),figure_sha256=sha256(out/'native-delta-subgrid.png')),indent=2))
if __name__=='__main__':main()
