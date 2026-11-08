"""Render the saved bounded subgrid sections on a local 1 m portrayal grid."""
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

ROOT=Path('.scratch/river-upgrade-20261101')

def main():
    out=ROOT/'game-delta-v1'; d=np.load(out/'delta.npz'); m=json.loads((out/'manifest.json').read_text(encoding='utf8'))
    apex=d['upstream_points_xz_m'][-1]; half=240; xx=np.arange(np.floor(apex[0]-half),np.ceil(apex[0]+half)+1); zz=np.arange(np.floor(apex[1]-half),np.ceil(apex[1]+half)+1)
    x,z=np.meshgrid(xx,zz); coords=np.vstack((((z+61440)/30).ravel(),((x+61440)/30).ravel()))
    source=np.load(ROOT/'terrain-v3/bed_m.npy',mmap_mode='r'); marine=np.load(ROOT/'terrain-v3/ocean_mask.npy',mmap_mode='r'); unknown=np.load(ROOT/'terrain-v3/unknown_mask.npy',mmap_mode='r')
    base=map_coordinates(source,coords,order=1).reshape(x.shape).astype(float); ocean=map_coordinates(marine.astype(np.uint8),coords,order=0).reshape(x.shape).astype(bool); bad=map_coordinates(unknown.astype(np.uint8),coords,order=0).reshape(x.shape).astype(bool)
    xy=np.column_stack((x.ravel(),z.ravel())); derived=base.copy(); wet=np.zeros(x.shape,bool)
    paths=[d['upstream_points_xz_m']]; beds=[d['upstream_bed_m']]; stages=[d['upstream_stage_m']]; cuts=[d['upstream_cut_m']]; widths=[d['upstream_width_m']]
    for i in range(3):
        valid=np.isfinite(d['section_bed_m'][i]);paths.append(d['paths_xz_m'][i,valid]);beds.append(d['section_bed_m'][i,valid]);stages.append(d['section_stage_m'][i,valid]);cuts.append(d['section_cut_m'][i,valid]);widths.append(np.full(valid.sum(),d['branch_width_m'][i]))
    for path,bed,stage,cut,width in zip(paths,beds,stages,cuts,widths):
        # Interpolate the saved operator densely enough for a 1 m portrayal.
        arc=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(path,axis=0),axis=1))]; st=np.linspace(0,arc[-1],int(np.ceil(arc[-1]*2))+1); dense=np.column_stack([np.interp(st,arc,path[:,j]) for j in range(2)])
        dist,idx=cKDTree(dense).query(xy); w=np.interp(st,arc,width)[idx]; c=np.interp(st,arc,cut)[idx]; h=np.interp(st,arc,stage)[idx]; op=channel_section_cut(dist,w,c).reshape(x.shape); local=base-op; derived=np.minimum(derived,np.where(ocean,base,local)); wet |= (dist.reshape(x.shape)<=w.reshape(x.shape)/2)&(h.reshape(x.shape)>local)&~ocean&~bad
    rgb=colorize(base,ocean,bad,~bad,1.); rgb[wet]=(.12,.68,.82)
    fig,ax=plt.subplots(figsize=(9,9),layout='constrained');ax.imshow(rgb,extent=(xx[0]-.5,xx[-1]+.5,zz[-1]+.5,zz[0]-.5),origin='upper',interpolation='nearest');ax.set(xlabel='X east (m)',ylabel='Z south (m)',title='INTERMEDIATE | modeled wet subgrid sections\n30 m TD source, interpolated portrayal at 1 m; stage 1 incomplete')
    ax.text(.02,.03,f"Bounded sections and prescribed stage; original ocean mask.\n30-day deposition max {m['max_deposition_m']*1000:.3f} mm; not visible at this scale.", transform=ax.transAxes, fontsize=8, color='white', bbox=dict(facecolor='black',alpha=.65))
    fig.savefig(out/'subgrid-local-1m.png',dpi=180);plt.close(fig)
    np.savez_compressed(out/'subgrid-local-1m.npz',origin_xz_m=np.array([xx[0],zz[0]]),spacing_m=1.,source_bed_interpolated_m=base,derived_bed_m=derived,wet_subgrid_mask=wet,ocean_mask=ocean)
    print(json.dumps(dict(portrayal_spacing_m=1,terrain_source_spacing_m=30,wet_cells=int(wet.sum()),figure_sha256=sha256(out/'subgrid-local-1m.png')),indent=2))
if __name__=='__main__': main()
