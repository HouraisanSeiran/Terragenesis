from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from terrain_pipeline.coastal_delta_product import load_checkpoint
p=Path('.scratch/coast-marine-reorganization-20261102')
s,progress=load_checkpoint(p/'river-stage-v1-event'); h=progress['river_hydraulics']; nodes={(r,c):(stage,depth,q) for r,c,stage,depth,q in h['nodes']}
fig,axs=plt.subplots(1,2,figsize=(14,6),constrained_layout=True)
colors=plt.rcParams['axes.prop_cycle'].by_key()['color']
ax=axs[0]; extent=[s.origin_xz_m[0]/1000,(s.origin_xz_m[0]+s.bed_m.shape[1]*s.spacing_m)/1000,(s.origin_xz_m[1]+s.bed_m.shape[0]*s.spacing_m)/1000,s.origin_xz_m[1]/1000]
ax.imshow(s.bed_m,origin='upper',extent=extent,cmap='terrain',vmin=-6,vmax=3)
for i,route in enumerate(progress['routes']):
 q=np.array(route); ax.plot((q[:,1]+.5)*s.spacing_m/1000+s.origin_xz_m[0]/1000,(q[:,0]+.5)*s.spacing_m/1000+s.origin_xz_m[1]/1000,lw=1,color=colors[i],label=f"{i+1}: {h['route_q_m3_s'][i]:.1f} m³/s")
ax.set_xlim(-20,25);ax.set_ylim(25,-15);ax.set_xlabel('X east (km)');ax.set_ylabel('Z south (km)');ax.set_title('TD, 600 m: final bed and routes');ax.legend(fontsize=8)
ax=axs[1]
for i,route in enumerate(progress['routes']):
 if not h['active'][i]: continue
 cells=[tuple(x) for x in route]; dist=np.arange(len(cells))*s.spacing_m/1000
 ax.plot(dist,[s.bed_m[c] for c in cells],lw=.7,alpha=.65,color=colors[i])
 ax.plot(dist,[nodes[c][0] for c in cells],lw=1.2,color=colors[i],label=f'route {i+1}')
ax.axhline(h['sea_level_m'],color='black',ls='--',lw=.8,label='ocean boundary')
ax.set_xlabel('distance along route (km)');ax.set_ylabel('elevation (m)');ax.set_title('bed (thin) and river surface (thick)');ax.legend(fontsize=8)
fig.suptitle('river-stage-v1: assumed upstream maximum 3 m; final physical time, tide and waves')
fig.savefig(p/'river-stage-v1-event.png',dpi=140)
