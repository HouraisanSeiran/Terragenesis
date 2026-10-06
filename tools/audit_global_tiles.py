"""Check shared edges of the real model cache created by global server verification."""
from pathlib import Path
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def audit():
    output=ROOT/'verification/presets-global/tile-edges.json'
    from diffusion.config import GenerationConfig
    identity=GenerationConfig().identity()[0]
    directory=ROOT/'cache/diffusion'/identity/'20260927'
    tiles={}
    for path in directory.glob('*.npz'):
        with np.load(path,allow_pickle=False) as data:
            tiles[tuple(map(int,path.stem.split('_')))]=data['elevation'].copy()
    pairs=0;error=0.
    for (x,z),data in tiles.items():
        if (x+1,z) in tiles:
            error=max(error,float(np.max(np.abs(data[:,-1]-tiles[x+1,z][:,0]))));pairs+=1
        if (x,z+1) in tiles:
            error=max(error,float(np.max(np.abs(data[-1,:]-tiles[x,z+1][0,:]))));pairs+=1
    assert pairs>0
    # GPU inference windows may differ slightly in rounding; measure the actual
    # geometric error rather than pretending the model is bitwise identical.
    blocks=error/GenerationConfig().meters_per_height_block
    assert blocks<.1, f'Real model shared edges differ by {blocks} blocks'
    assert any(x<=-64 and z<=-64 for x,z in tiles),'Negative distant tile missing'
    assert any(x>=64 and z>=64 for x,z in tiles),'Positive distant tile missing'
    output.write_text(json.dumps({'passed':True,'identity':identity,'tiles':len(tiles),'adjacent_pairs':pairs,'max_edge_error_meters':error,'max_edge_error_blocks_upper_bound':blocks,'tolerance_blocks':.1,'bitwise_identical':error==0},indent=2))
    print(output)


if __name__=='__main__':audit()
