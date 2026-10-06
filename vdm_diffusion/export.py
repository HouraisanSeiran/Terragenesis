"""Lossless float32 XYZ map + displaced mesh. No height-to-vector postprocessing."""
import json,struct
import numpy as np
from diffusion.paths import inside

def export(folder,vectors,metadata):
    folder=inside(folder);folder.mkdir(parents=True,exist_ok=True)
    vectors=np.asarray(vectors,dtype=np.float32)
    if vectors.ndim!=3 or vectors.shape[0]!=3 or not np.isfinite(vectors).all():raise ValueError('Expected finite XYZ map')
    h,w=vectors.shape[1:];ox,oz=metadata['origin'];spacing=metadata['spacing']
    if not np.isfinite([ox,oz,spacing]).all() or spacing<=0:raise ValueError('Invalid reference coordinates')
    np.savez_compressed(folder/'displacement.npz',vectors=vectors,metadata=json.dumps(metadata))
    # Portable map: magic, width, height, world origin x/z, spacing, reference-y; then interleaved XYZ float32.
    with (folder/'displacement.rmdv').open('wb') as stream:
        stream.write(struct.pack('<4sii4f',b'VDM1',w,h,ox,oz,spacing,72.))
        stream.write(vectors.transpose(1,2,0).astype('<f4').tobytes())
    with (folder/'surface.obj').open('w',encoding='utf-8') as stream:
        stream.write('# Direct diffusion XYZ displacement of reference plane y=72\n')
        for z in range(h):
            for x in range(w):
                dx,dy,dz=vectors[:,z,x];stream.write(f'v {ox+x*spacing+dx:.6f} {72+dy:.6f} {oz+z*spacing+dz:.6f}\n')
        for z in range(h-1):
            for x in range(w-1):
                a=z*w+x+1;b=a+1;c=a+w;d=c+1
                stream.write(f'f {a} {d} {b}\nf {a} {c} {d}\n')
    (folder/'provenance.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf-8')
