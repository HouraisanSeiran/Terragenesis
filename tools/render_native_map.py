"""Render the native-event 50 km terrain, lakes and channel portrayal."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Patch
from tools.render_world_river_acceptance import BOUNDS, crop_slices, colorize, sha256
R=Path('.scratch/river-upgrade-20261101')

def main():
 src=R/'terrain-v3';out=R/'native-map-v1';source=json.loads((src/'manifest.json').read_text(encoding='utf8'));manifest=json.loads((out/'manifest.json').read_text(encoding='utf8'));window=np.load(out/'window-geometry.npz');rep=np.load(out/'representative.npz');slices,extent=crop_slices(source)
 if source['identity']!=manifest['source_identity']:raise ValueError('source mismatch')
 crop={k:np.array(np.load(src/(k+'.npy'),mmap_mode='r')[slices],copy=True) for k in ('bed_m','ocean_mask','unknown_mask','valid_mask')};rgb=colorize(crop['bed_m'],crop['ocean_mask'],crop['unknown_mask'],crop['valid_mask'],30.)
 lake=window['lake_wet_day30'];rgb[lake]=(.18,.46,.57);start=window['channel_source_xz_m'];end=window['channel_target_xz_m'];segments=np.stack((start,end),axis=1);widths=np.clip(.38+window['channel_width_m']*.035,.38,1.25)
 fig,ax=plt.subplots(figsize=(12,12));fig.subplots_adjust(left=.08,right=.98,bottom=.105,top=.94);ax.imshow(rgb,extent=extent,origin='upper',interpolation='nearest');ax.add_collection(LineCollection(segments,colors='#4ba0b6',linewidths=widths,alpha=.95));
 # The representative channel and constructed branches use their saved geometry.
 path=rep['points_xz_m'];ax.plot(path[:,0],path[:,1],color='#8cdded',lw=.9)
 for p in rep['branch_paths_xz_m']:
  p=p[np.isfinite(p).all(axis=1)];ax.plot(p[:,0],p[:,1],color='#8cdded',lw=1.)
 apex=path[-1];ax.plot(*apex,marker='o',ms=5,mec='#f1daa0',mfc='none',mew=1.)
 ax.set(xlim=BOUNDS[:2],ylim=(BOUNDS[3],BOUNDS[2]),xlabel='X east (m)',ylabel='Z south (m)',title='Native 30 m terrain, rivers and lakes | 30-day event\nRemote-style model rendering · representative local delta')
 ax.plot([-24000,-14000],[27000,27000],color='white',lw=3);ax.text(-19000,26000,'10 km',color='white',ha='center',fontsize=9,bbox=dict(facecolor='black',alpha=.5,edgecolor='none'));ax.text(.02,.98,'N ↑',transform=ax.transAxes,va='top',color='white',fontsize=11,bbox=dict(facecolor='black',alpha=.5,edgecolor='none'))
 ax.legend(handles=[Patch(color='#4ba0b6',label='Event-flow channels; cartographic width'),Patch(color='#2e758f',label='Simulated day-30 lake cells'),Patch(color='#1f475c',label='Original ocean'),Patch(color='#8cdded',label='Representative constructed river and delta')],loc='lower right',fontsize=8,framealpha=.9)
 inset=ax.inset_axes([.025,.025,.31,.31]);b=rep['patch_original_bed_m'];o=rep['patch_ocean_mask'];bad=rep['patch_unknown_mask'];origin=rep['patch_origin_xz_m'];prgb=colorize(b,o,bad,~bad,30.);ex=(origin[0]-15,origin[0]+(b.shape[1]-.5)*30,origin[1]+(b.shape[0]-.5)*30,origin[1]-15);inset.imshow(prgb,extent=ex,origin='upper',interpolation='nearest');inset.plot(path[:,0],path[:,1],color='#80d7ea',lw=1.4)
 for p in rep['branch_paths_xz_m']:
  p=p[np.isfinite(p).all(axis=1)];inset.plot(p[:,0],p[:,1],color='#80d7ea',lw=1.4)
 inset.set(xlim=(apex[0]-350,apex[0]+350),ylim=(apex[1]+350,apex[1]-350),xticks=[],yticks=[],title='Constructed local geometry | 700 m')
 fig.text(.5,.025,'TD c751a09a6f02… · seed 20261020 · 30 m control cells · day 30 / uniform runoff scenario\nChannel widths enlarged for display; local equivalent sections do not certify whole-network wet continuity.',ha='center',fontsize=8)
 fig.savefig(out/'native-50km.png',dpi=170,facecolor='white');plt.close(fig)
 fig,ax=plt.subplots(figsize=(9,8),layout='constrained');ax.imshow(prgb,extent=ex,origin='upper',interpolation='nearest');ax.plot(path[:,0],path[:,1],color='#80d7ea',lw=2,label='Derived representative reach')
 for j,p in enumerate(rep['branch_paths_xz_m']):
  p=p[np.isfinite(p).all(axis=1)];ax.plot(p[:,0],p[:,1],color='#80d7ea',lw=2,label='Constructed subgrid branches' if j==0 else None)
 ax.set(xlim=(apex[0]-400,apex[0]+400),ylim=(apex[1]+400,apex[1]-400),xlabel='X east (m)',ylabel='Z south (m)',title=f"Native representative delta | day 30\nConstructed geometry; maximum deposition {manifest['max_deposition_m']*1000:.2f} mm");ax.legend(fontsize=8);fig.savefig(out/'native-delta-detail.png',dpi=180);plt.close(fig)
 provenance=dict(world_seed=source['world_seed'],terrain_manifest_sha256=sha256(src/'manifest.json'),terrain_files_sha256=source['files'],event_manifest_sha256=sha256(R/'native-event-v1/manifest.json'),routing_binding_sha256=sha256(R/'native-final-routing-v1/binding.json'),derived_metadata_sha256=sha256(R/'native-final-routing-v1/derived.json'),event_input_sha256={name:sha256(R/'native-event-v1'/name) for name in ('time_seconds.npy','mouth_water_m3.npy','node_water_m3.npy','pool_level_m.npy','channel_mask.npy')},schema='native-map-render-v1',source_identity=source['identity'],terrain_basis='saved TD terrain-v3',event='native-event-v1',routing='native-final-routing-v1',window_bounds_xz_m=list(BOUNDS),spacing_m=30,time_seconds=2592000,algorithms=['original TD elevation tone and hillshade','day-30 saved pool level above original bed','native event channel selection','representative subgrid river and delta'],channel_display='cartographic line width; not physical width',lake_policy='finite day30 pool level above source bed; dry levels excluded',coverage_status={'terrain':'complete_in_window','lake':'complete_in_window','network':'partial','delta':'mechanism_only'},figures={n:sha256(out/n) for n in ('native-50km.png','native-delta-detail.png')})
 (out/'render-provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf8');print(json.dumps(provenance,indent=2))
if __name__=='__main__':main()
