"""Render saved large delta trial bed, water depth and sediment change maps."""
import argparse, json
from pathlib import Path
import sys
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from terrain_pipeline.environment_delta_fv import load
from terrain_pipeline.common_infra import file_sha256

def main():
    p=argparse.ArgumentParser(); p.add_argument('--trial',type=Path,required=True); p.add_argument('--stage',default='growth_12h'); args=p.parse_args()
    case=next(x for x in args.trial.iterdir() if x.is_dir()); state=case/(args.stage+'.npz'); product=load(state,expected_sha256=file_sha256(state)); a=product['arrays'];
    fig,axs=plt.subplots(1,4,figsize=(19,5),constrained_layout=True)
    extent=[0,a['bed_m'].shape[1]*30/1000,0,a['bed_m'].shape[0]*30/1000]
    # The saved face transfer is signed from ``face_left`` to ``face_right``.
    # A cell-wise divergence is dominated by cancellation and made the old
    # fourth panel nearly uniform.  Accumulate absolute face discharge at both
    # adjacent cells so the panel shows where the actual water transport is.
    face_flux=np.zeros_like(a['bed_m'], dtype=float)
    dt=product['metadata']['last_coupling_interval_s']
    if dt:
        q=np.abs(np.asarray(a['internal_last_water_transfer_m3'], dtype=float))/float(dt)
        np.add.at(face_flux.ravel(),a['face_left'],q)
        np.add.at(face_flux.ravel(),a['face_right'],q)
    face_flux=np.ma.masked_where(face_flux <= 0.0, face_flux)
    for ax,data,title,cmap in zip(axs,[a['bed_m'],a['depth_m'],a['bed_m']-a['initial_bed_m'],face_flux],['Bed elevation (m)','Water depth (m)','Bed change (m)','Face discharge magnitude (m3/s)'],['terrain','Blues','RdBu_r','magma']):
        cmap_obj=plt.get_cmap(cmap).copy()
        if np.ma.isMaskedArray(data):
            cmap_obj.set_bad('black')
        im=ax.imshow(data,origin='lower',extent=extent,cmap=cmap_obj); ax.set_title(title); ax.set_xlabel('x (km)'); ax.set_ylabel('z (km)'); fig.colorbar(im,ax=ax,shrink=.8)
    out=args.trial/(case.name+'-'+args.stage+'.png'); fig.savefig(out,dpi=140); print(out)
if __name__=='__main__': main()
