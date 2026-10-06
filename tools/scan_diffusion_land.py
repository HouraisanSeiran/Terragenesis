"""Scan a few deterministic coarse cells for a land patch before baking the demo."""
import sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from diffusion.paths import configure
configure()
import numpy as np
from diffusion.config import GenerationConfig
from diffusion.backend import TerrainDiffusionBackend

def main():
    backend=TerrainDiffusionBackend(GenerationConfig(dtype='fp32'))
    candidates=[(0,0),(7680,0),(-7680,0),(0,7680),(0,-7680),(7680,7680),(-7680,-7680),(15360,0)]
    report=[]
    try:
        for x,z in candidates:
            started=time.perf_counter();elev,climate,meta=backend.generate(20260927,x,z,65)
            item={'x':x,'z':z,'min':float(elev.min()),'max':float(elev.max()),'mean':float(elev.mean()),'seconds':time.perf_counter()-started}
            report.append(item);print(item,flush=True)
    finally:backend.close()
    (ROOT/'verification/diffusion-land-scan.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
if __name__=='__main__':main()
