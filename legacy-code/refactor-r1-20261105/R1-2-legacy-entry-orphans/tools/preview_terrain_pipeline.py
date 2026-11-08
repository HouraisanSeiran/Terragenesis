"""Generate a real pretrained Terrain Diffusion sample and a separately sculpted VDM preview."""
import sys,json,argparse,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from diffusion.paths import configure
configure()
import numpy as np
from diffusion.config import GenerationConfig
from diffusion.backend import TerrainDiffusionBackend
from terrain_pipeline.conversion import height_to_vdm
from terrain_pipeline.render import render_comparison
from vdm_diffusion.landforms import CliffOperator,CliffSettings
from vdm_diffusion.export import export
from terrain_pipeline.bake import bake

def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,default=20260927)
    p.add_argument('--size',type=int,default=513);p.add_argument('--x',type=int,default=0);p.add_argument('--z',type=int,default=0)
    args=p.parse_args();folder=ROOT/'preview/terrain-pipeline'/f'{args.seed}_{args.x}_{args.z}_{args.size}'
    folder.mkdir(parents=True,exist_ok=True);raw=folder/'model-output.npz'
    config=GenerationConfig(dtype='fp32');backend=TerrainDiffusionBackend(config)
    if raw.exists():
        with np.load(raw,allow_pickle=False) as data:
            elev=data['elevation'];climate=data['climate'];meta=json.loads(str(data['metadata']))
        if meta['identity']!=backend.identity:raise ValueError('Preview model settings changed')
    else:
        try:elev,climate,meta=backend.generate(args.seed,args.x,args.z,args.size)
        finally:backend.close()
        if not np.isfinite(elev).all():raise ValueError('Non-finite model output')
        np.savez_compressed(raw,elevation=elev,climate=climate,metadata=json.dumps(meta))
    base=height_to_vdm(elev);n=base.shape[1];spacing=2
    origin=-256
    metadata={'reference':'world-x-y-z-plane72','origin':[origin,origin],'spacing':spacing,'base_terrain':meta,
              'generator':'TerrainDiffusion -> height-to-VDM','meters_per_height_block':30,
              'note':'XYZ neural diffusion experiments are not used in this pipeline'}
    export(folder/'base',base,metadata)
    zz,xx=np.mgrid[:n,:n];cx=256;cz=256
    radius=np.sqrt(((origin+xx*spacing-256)/144)**2+((origin+zz*spacing-256)/164)**2)
    mask=np.clip(1-radius,0,1);mask=mask*mask*(3-2*mask)
    settings=CliffSettings((cx,cz),(1,.35),height=42,transition=5,overhang=8)
    sculpted=CliffOperator(settings).apply(base,metadata,mask)
    export(folder/'sculpted',sculpted,dict(metadata,postprocess='local fault scarp: height42 width5 overhang8; smooth finite mask'))
    render_comparison(folder,base,sculpted,spacing)
    baked=bake(elev,climate,meta,spacing,origin)
    report={'passed':True,'model':meta,'shape':list(elev.shape),'raw_range_m':[float(elev.min()),float(elev.max())],
            'base_height_blocks':[float(base[1].min()+72),float(base[1].max()+72)],
            'horizontal_displacement_max':float(np.hypot(sculpted[0],sculpted[2]).max()),
            'outside_mask_unchanged':bool(np.array_equal(base[:,mask==0],sculpted[:,mask==0])),
            'caves_included':False,'minecraft_server_verified':False,'baked':baked}
    (folder/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True);print(folder/'comparison.png',flush=True)

if __name__=='__main__':main()
