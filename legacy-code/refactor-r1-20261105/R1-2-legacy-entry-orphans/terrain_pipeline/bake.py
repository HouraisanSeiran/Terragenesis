"""Embed a documented real model sample for GPU-free first-playable Minecraft testing."""
import json,struct,hashlib
import numpy as np
from diffusion.paths import ROOT

def bake(elevation,climate,metadata,spacing=2,origin=-256):
    n=elevation.shape[0]
    if elevation.shape!=(n,n) or climate.shape!=(4,n,n):raise ValueError('Unexpected model grid')
    values=np.stack([elevation,climate[0],climate[2]],axis=-1).astype('<f4')
    if not np.isfinite(values).all():raise ValueError('Invalid baked values')
    payload=struct.pack('<4siii',b'RMB1',n,spacing,origin)+values.tobytes()
    directory=ROOT/'src/main/resources/assets/remotemountains/terrain';directory.mkdir(parents=True,exist_ok=True)
    (directory/'demo.rmb').write_bytes(payload)
    provenance=dict(metadata,baked_sha256=hashlib.sha256(payload).hexdigest(),origin=[origin,origin],spacing=spacing,
                    collar_blocks=64,outside='flat ocean floor y48',fixed_terrain_seed=True)
    (directory/'demo.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    return provenance
