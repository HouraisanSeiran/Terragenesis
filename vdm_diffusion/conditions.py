"""Terrain Diffusion elevation/climate is a condition, not a replacement for denoised XYZ."""
import json
import numpy as np
from diffusion.paths import inside

def prepare(args):
    if not 1<=args.spacing<=16 or not np.isfinite(args.origin).all():raise ValueError('Invalid condition coordinates')
    with np.load(inside(args.tile),allow_pickle=False) as data:
        elevation=data['elevation'];climate=data['climate'];provenance=json.loads(str(data['metadata']))
    height=72+np.where(elevation>=0,225*np.tanh(elevation/30/225),125*np.tanh(elevation/30/125))
    weights=np.zeros((4,*elevation.shape),dtype=np.float32);weights[args.region]=1
    condition=np.concatenate([(height[None]-72)/128,climate[0:1]/40,climate[2:3]/3000,weights]).astype(np.float32)
    metadata={'reference':'world-x-y-z-plane72','origin':list(args.origin),'spacing':args.spacing,
              'base_terrain':provenance,'condition_units':['height_offset/128','celsius/40','mm_per_year/3000'],
              'region_order':['inselberg','rift','karst','pillars']}
    output=inside(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(output,condition=condition,metadata=json.dumps(metadata))
