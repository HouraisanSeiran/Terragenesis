"""Render saved tidal experiment against its frozen TD source."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, TwoSlopeNorm

BASE=Path('.scratch/delta-tides-bars-20261102')
P=BASE/'tidal-coupled-v3'
with np.load(P/'native.npz') as a, np.load('.scratch/large-delta-20261101/active-network-v12/network.npz') as n:
    bed=a['bed_m']; initial=n['initial_channel_bed_m']; low=a['low_stage_m']; high=a['high_stage_m']; final=a['water_stage_m']; lo=float(a['low_time_s']); hi=float(a['high_time_s'])
    origin=a['origin_xz_m']; spacing=float(a['spacing_m'])
    extent=[origin[0]/1000,(origin[0]+bed.shape[1]*spacing)/1000,(origin[1]+bed.shape[0]*spacing)/1000,origin[1]/1000]
    change=bed-initial
    hill=LightSource(azdeg=315,altdeg=45).hillshade(initial,vert_exag=3,dx=spacing,dy=spacing)
    fig,ax=plt.subplots(figsize=(10,10)); ax.imshow(initial,extent=extent,cmap='terrain',vmin=-10,vmax=70,interpolation='nearest'); ax.imshow(hill,extent=extent,cmap='gray',alpha=.19,interpolation='nearest'); ax.imshow(np.ma.masked_invalid(final),extent=extent,cmap='Blues',vmin=-2,vmax=3,alpha=.6,interpolation='nearest'); ax.set_xlim(-10,40); ax.set_ylim(-10,-60); ax.set_xlabel('x (km)'); ax.set_ylabel('z (km)'); ax.set_title('TD source, 30-day tidal scenario | 50 km view\nwater: coarse storage stage projected to 30 m'); fig.tight_layout();fig.savefig(P/'tidal-overview-50km.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,7),sharex=True,sharey=True)
    for ax,surface,title,t in zip(axes,[low,high],['Low sea stage','High sea stage'],[lo,hi]):
        ax.imshow(bed,extent=extent,cmap='terrain',vmin=-5,vmax=8,interpolation='nearest');ax.imshow(np.ma.masked_invalid(surface),extent=extent,cmap='Blues',vmin=-2,vmax=3,alpha=.8,interpolation='nearest');ax.set_xlim(16.5,29.5);ax.set_ylim(-25.5,-40);ax.set_title(f'{title}, t={t/86400:.2f} d');ax.set_xlabel('x (km)')
    axes[0].set_ylabel('z (km)');fig.suptitle('Same bed and domain: computed water storage, projected to native terrain');fig.tight_layout();fig.savefig(P/'tidal-low-high.png',dpi=160);plt.close(fig)
    vmax=max(float(np.percentile(np.abs(change[change!=0]),99)),1e-5)
    fig,axes=plt.subplots(1,3,figsize=(16,6),sharex=True,sharey=True)
    for ax,field,title in zip(axes[:2],[initial,bed],['Pre-event bed','After 30 days']):
        ax.imshow(field,extent=extent,cmap='terrain',vmin=-3,vmax=4,interpolation='nearest');ax.set_title(title)
    im=axes[2].imshow(change,extent=extent,cmap='RdBu_r',norm=TwoSlopeNorm(vmin=-vmax,vcenter=0,vmax=vmax),interpolation='nearest');axes[2].set_title('Actual bed change (m)');fig.colorbar(im,ax=axes[2],shrink=.7,label='m; color scale clipped at 99th percentile')
    for ax in axes: ax.set_xlim(16.5,29.5);ax.set_ylim(-25.5,-40);ax.set_xlabel('x (km)')
    axes[0].set_ylabel('z (km)');fig.suptitle('Finite-stock reworking; 300 m coastal changes mapped to native grid');fig.tight_layout();fig.savefig(P/'tidal-bed-change.png',dpi=160);plt.close(fig)
