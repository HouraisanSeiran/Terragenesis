"""Export unmodified model output, slope and provenance before any erosion."""
from .paths import ROOT
import json

def export(service,seed,tx,tz):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    elev,climate,meta=service.tile(seed,tx,tz)
    spacing=meta['native_resolution_m']
    dz,dx=np.gradient(elev,spacing,spacing);slope=np.degrees(np.arctan(np.hypot(dx,dz)))
    folder=ROOT/'preview/diffusion'/f'{seed}_{tx}_{tz}';folder.mkdir(parents=True,exist_ok=True)
    np.save(folder/'raw-elevation-meters.npy',elev)
    fig,axes=plt.subplots(1,3,figsize=(15,5),constrained_layout=True)
    for ax,data,title in zip(axes,[elev,slope,climate[2]],['Raw diffusion elevation (m)','Slope (degrees)','Annual precipitation (mm)']):
        im=ax.imshow(data,cmap='terrain' if 'elevation' in title else 'viridis');ax.set_title(title);fig.colorbar(im,ax=ax,shrink=.7)
    fig.suptitle('Terrain Diffusion • native model output • no erosion / no procedural mountain replacement')
    fig.savefig(folder/'raw-diffusion.png',dpi=150);plt.close(fig)
    (folder/'provenance.json').write_text(json.dumps({'generation':meta,'model':service.backend.metadata},indent=2),encoding='utf-8')
    print('Raw diffusion preview:',folder,flush=True)
