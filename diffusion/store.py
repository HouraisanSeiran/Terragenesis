"""Atomic, checksummed raw diffusion tiles. World seed and model settings isolate caches."""
from pathlib import Path
import hashlib,json,os
from .paths import ROOT

class TerrainTileStore:
    def __init__(self,identity):
        self.root=ROOT/'cache/diffusion'/identity;self.root.mkdir(parents=True,exist_ok=True)
    def path(self,seed,tx,tz):
        folder=self.root/str(seed);folder.mkdir(exist_ok=True)
        return folder/f'{tx}_{tz}.npz'
    def read(self,seed,tx,tz):
        import numpy as np
        path=self.path(seed,tx,tz)
        if not path.exists():return None
        try:
            with np.load(path,allow_pickle=False) as data:
                elev=data['elevation'].copy();climate=data['climate'].copy();meta=json.loads(str(data['metadata']))
            digest=hashlib.sha256(elev.tobytes()+climate.tobytes()).hexdigest()
            if digest!=meta['array_sha256']:raise ValueError('Tile checksum mismatch')
            return elev,climate,meta
        except Exception as exc:raise RuntimeError(f'Invalid cached diffusion tile: {path}') from exc
    def write(self,seed,tx,tz,elev,climate,meta):
        import numpy as np
        meta=dict(meta,array_sha256=hashlib.sha256(elev.tobytes()+climate.tobytes()).hexdigest())
        path=self.path(seed,tx,tz);temporary=path.with_suffix('.tmp')
        with temporary.open('wb') as stream:
            np.savez_compressed(stream,elevation=elev,climate=climate,metadata=json.dumps(meta));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        return elev,climate,meta
