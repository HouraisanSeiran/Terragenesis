"""Render actual 50 km TD terrain, day-30 lake state and representative delta."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Patch
from tools.render_world_river_acceptance import BOUNDS, crop_slices, colorize, sha256
R=Path('.scratch/river-upgrade-20261101'); S=R/'terrain-v3'; H=R/'game-hydro-v1'; G=R/'game-grade-90m'; L=R/'game-grade-lowland'; D=R/'game-delta-v1'

def main():
    m=json.loads((S/'manifest.json').read_text(encoding='utf8')); delta=json.loads((D/'manifest.json').read_text(encoding='utf8')); assert m['identity']==delta['source_identity']
    maximum_mm=delta['max_deposition_m']*1000
    ds=np.load(D/'delta.npz'); reach=np.load(R/'game-delta-local-derived/reach.npz'); slices,extent=crop_slices(m)
    crop={k:np.array(np.load(S/(k+'.npy'),mmap_mode='r')[slices],copy=True) for k in ('bed_m','ocean_mask','unknown_mask','valid_mask')}
    rgb=colorize(crop['bed_m'],crop['ocean_mask'],crop['unknown_mask'],crop['valid_mask'],30.)
    # Saved pool membership and day-30 levels on the 90 m source grid.
    pools=np.load(H/'derived/pool_index.npy',mmap_mode='r').reshape(1366,1366); levels=np.load(H/'pool_level_m.npy',mmap_mode='r')[-1]; bed90=np.load(G/'bed_m.npy',mmap_mode='r'); ocean90=np.load(G/'ocean_mask.npy',mmap_mode='r'); wet=np.zeros(pools.shape,bool); active=pools>=0; wet[active]=np.isfinite(levels[pools[active]]) & (bed90[active]<levels[pools[active]]); wet &= ~ocean90
    overlay=np.zeros((*wet.shape,4),np.float32); overlay[wet]=(.20,.55,.72,.85)
    channel=np.load(L/'channel_mask.npy',mmap_mode='r').ravel(); rec=np.load(G/'routing/receiver.npy',mmap_mode='r'); x=np.load(G/'graph/node_x_m.npy',mmap_mode='r')*3-61440; z=np.load(G/'graph/node_z_m.npy',mmap_mode='r')*3-61440
    selected=channel & (rec>=0)&(x>=BOUNDS[0]-200)&(x<=BOUNDS[1]+200)&(z>=BOUNDS[2]-200)&(z<=BOUNDS[3]+200); ids=np.flatnonzero(selected); dest=rec[ids]; seg=np.stack((np.stack((x[ids],z[ids]),axis=1),np.stack((x[dest],z[dest]),axis=1)),axis=1)
    fig,ax=plt.subplots(figsize=(12,12),layout='constrained'); ax.imshow(rgb,extent=extent,origin='upper',interpolation='nearest'); ax.imshow(overlay,extent=(-61485,61455,61455,-61485),origin='upper',interpolation='nearest'); ax.add_collection(LineCollection(seg,colors='#65d0f2',linewidths=.55,alpha=.85))
    for path in ds['paths_xz_m']:
        path=path[np.isfinite(path).all(axis=1)]; ax.plot(path[:,0],path[:,1],color='#ffee83',lw=1.)
    apex=ds['paths_xz_m'][0,0];ax.plot(*apex,marker='o',ms=5,mfc='none',mec='yellow',mew=1.2)
    ax.set(xlim=BOUNDS[:2],ylim=(BOUNDS[3],BOUNDS[2]),ylabel='Z south (m)',title='INTERMEDIATE: stage 1 incomplete | 50 km terrain, lakes and candidate channels')
    ax.legend(handles=[Patch(color='#65d0f2',label='Saved lowland channel network (90 m)'),Patch(color='#338cb8',label='Simulated day-30 lake wet cells (90 m)'),Patch(color='#ffee83',label='Constructed subgrid diagnostic, enlarged in inset')],loc='lower right',fontsize=8)
    inset=ax.inset_axes([.025,.025,.34,.34]); patch=ds['original_bed_m']; po=ds['origin_xz_m']; pocean=ds['ocean_mask']; valid=~ds['unknown_mask']; prgb=colorize(patch,pocean,ds['unknown_mask'],valid,30.)
    pextent=(po[0]-15,po[0]+(patch.shape[1]-.5)*30,po[1]+(patch.shape[0]-.5)*30,po[1]-15)
    inset.imshow(prgb,extent=pextent,origin='upper',interpolation='nearest')
    for path in ds['paths_xz_m']:
        path=path[np.isfinite(path).all(axis=1)];inset.plot(path[:,0],path[:,1],color='#ffdc63',lw=1.6)
    inlet=ds['upstream_points_xz_m'];inset.plot(inlet[:,0],inlet[:,1],color='#67d8ff',lw=1.5)
    inset.set(xlim=(apex[0]-400,apex[0]+400),ylim=(apex[1]+400,apex[1]-400),title='Constructed subgrid branches | 800 m',xticks=[],yticks=[])
    fig.text(.5,.005,f'Seed 20261020 | TD c751a09a6f02… | 30 m display; 90 m lake and network | 30-day scenario\nInset line width enlarged for visibility; maximum modeled deposition {maximum_mm:.3f} mm, not a matured natural delta.',ha='center',fontsize=8)
    fig.savefig(D/'river-delta-50km.png',dpi=160,facecolor='white');plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,8),layout='constrained');ax.imshow(prgb,extent=pextent,origin='upper',interpolation='nearest')
    for n,path in enumerate(ds['paths_xz_m']):
        path=path[np.isfinite(path).all(axis=1)];ax.plot(path[:,0],path[:,1],lw=2,color='#ffd65a',label='Constructed branches (display width enlarged)' if n==0 else None)
    ax.plot(inlet[:,0],inlet[:,1],color='#67d8ff',lw=2,label='Derived spill-to-mouth subgrid river'); ax.plot(*apex,'wo',ms=4)
    ax.set(xlim=(apex[0]-500,apex[0]+500),ylim=(apex[1]+500,apex[1]-500),xlabel='X east (m)',ylabel='Z south (m)',title=f"INTERMEDIATE: stage 1 incomplete | day 30\nConstructed sections; max deposition {maximum_mm:.3f} mm")
    ax.legend(loc='lower right',fontsize=8);fig.savefig(D/'delta-detail.png',dpi=180,facecolor='white');plt.close(fig)
    info=dict(stage1_status='incomplete; intermediate diagnostic',source_identity=m['identity'],bounds_xz_m=list(BOUNDS),time_seconds=2592000,source_lake='pool_index with simulated day-30 pool level above 90 m original bed',channels='game-grade-lowland/channel_mask',subgrid_drawing='branch line widths enlarged in inset; 30-day deposition not enhanced',figures={n:sha256(D/n) for n in ('river-delta-50km.png','delta-detail.png')})
    (D/'render-provenance.json').write_text(json.dumps(info,indent=2),encoding='utf8');print(json.dumps(info,indent=2))
if __name__=='__main__':main()
