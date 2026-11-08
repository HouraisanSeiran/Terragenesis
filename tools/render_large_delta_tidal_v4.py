"""Render actual saved segmented-delta results; no terrain generation."""
from pathlib import Path
import argparse
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource,TwoSlopeNorm

parser=argparse.ArgumentParser()
parser.add_argument('product', type=Path)
parser.add_argument('--wave-product', type=Path)
args=parser.parse_args()
p=args.product
manifest=json.loads((p/'manifest.json').read_text(encoding='utf8'))
source_path=(p/manifest['source_manifest']).resolve()
source_manifest=json.loads(source_path.read_text(encoding='utf-8-sig'))
network_path=(source_path.parent/source_manifest['references']['network']['path']).resolve()
with np.load(p/'native.npz') as a, np.load(network_path) as net:
    bed=a['bed_m'];initial=net['initial_channel_bed_m'];coverage=a['coverage'];depth=a['water_depth_m'];origin=a['origin_xz_m'];spacing=float(a['spacing_m']);extent=[origin[0]/1000,(origin[0]+bed.shape[1]*spacing)/1000,(origin[1]+bed.shape[0]*spacing)/1000,origin[1]/1000]
    delta=bed-initial;valid=np.isfinite(initial);hill=LightSource(315,45).hillshade(np.nan_to_num(initial),vert_exag=3,dx=spacing,dy=spacing)
    fig,ax=plt.subplots(figsize=(9,9));ax.imshow(initial,extent=extent,cmap='terrain',vmin=-10,vmax=70);ax.imshow(hill,extent=extent,cmap='gray',alpha=.17);ax.imshow(np.ma.masked_where(~coverage|(depth<=0),depth),extent=extent,cmap='Blues',vmin=0,vmax=5,alpha=.7);ax.contour(coverage.astype(float),levels=[.5],extent=extent,colors='yellow',linewidths=.7);ax.set_xlim(-10,40);ax.set_ylim(-10,-60);ax.set_title('30-day tide: 300 m hydro, 30 m terrain\nYellow: partial active coverage');ax.set_xlabel('x (km)');ax.set_ylabel('z (km)');fig.tight_layout();fig.savefig(p/'tidal-overview-50km.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,7),sharex=True,sharey=True)
    for ax,key in zip(axes,['low','high']):
        h=a[key+'_bed_m'];d=a[key+'_depth_m'];t=float(a[key+'_time_s']);ax.imshow(h,extent=extent,cmap='terrain',vmin=-5,vmax=8);ax.imshow(np.ma.masked_where(~coverage|(d<=0),d),extent=extent,cmap='Blues',vmin=0,vmax=4,alpha=.8);ax.set_title(f'{key.capitalize()} tide, day {t/86400:.3f}');ax.set_xlim(16,30);ax.set_ylim(-25,-40);ax.set_xlabel('x (km)')
    axes[0].set_ylabel('z (km)');fig.suptitle('Each phase uses its own saved bed and water');fig.tight_layout();fig.savefig(p/'tidal-low-high.png',dpi=150);plt.close(fig)
    changed=np.abs(delta[coverage]);scale=max(float(np.quantile(changed[changed>0],.99)),1e-6)
    fig,axes=plt.subplots(1,3,figsize=(16,6),sharex=True,sharey=True)
    for ax,field,title in zip(axes[:2],[initial,bed],['Pre-event bed','After 30 days']):ax.imshow(field,extent=extent,cmap='terrain',vmin=-3,vmax=4);ax.set_title(title)
    im=axes[2].imshow(np.ma.masked_where(~coverage,delta),extent=extent,cmap='RdBu_r',norm=TwoSlopeNorm(vmin=-scale,vcenter=0,vmax=scale));axes[2].set_title('Bed change (m)');fig.colorbar(im,ax=axes[2],shrink=.7,label='m; clipped at 99th percentile')
    for ax in axes:ax.set_xlim(16,30);ax.set_ylim(-25,-40);ax.set_xlabel('x (km)')
    axes[0].set_ylabel('z (km)');fig.suptitle('Area-weighted native bed; finite sediment, no morphological acceleration');fig.tight_layout();fig.savefig(p/'tidal-bed-change.png',dpi=150);plt.close(fig)
    if args.wave_product:
        with np.load(args.wave_product/'native.npz') as wave:
            diff=wave['bed_m']-bed
        selected=np.abs(diff[coverage]); scale=max(float(np.quantile(selected,.99)),1e-6)
        fig,ax=plt.subplots(figsize=(8,7))
        im=ax.imshow(np.ma.masked_where(~coverage,diff),extent=extent,cmap='RdBu_r',norm=TwoSlopeNorm(vmin=-scale,vcenter=0,vmax=scale))
        ax.set_xlim(16,30);ax.set_ylim(-25,-40);ax.set_xlabel('x (km)');ax.set_ylabel('z (km)')
        ax.set_title('Wave minus tide bed (m): 300 m hydro, 30 m projection')
        fig.colorbar(im,ax=ax,label='m; clipped at 99th percentile');fig.tight_layout();fig.savefig(p/'wave-minus-tide.png',dpi=150);plt.close(fig)
