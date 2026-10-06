"""Short synthetic smoke run: training -> checkpoint -> direct XYZ sampling -> specialist cliff -> exports.

This is deliberately NOT a pretrained terrain model or a naturalness evaluation.
"""
import sys,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from diffusion.paths import configure
configure()
import numpy as np
import torch

def main():
    root=ROOT/'verification/vdm-smoke';data=root/'training';data.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(73);z,x=np.mgrid[:32,:32]
    for index in range(8):
        # Explicit synthetic displaced surfaces for execution checks only.
        phase=rng.uniform(-3,3);height=20+8*np.sin(x/9+phase)*np.cos(z/10)
        vectors=np.stack([2*np.sin(z/8+phase),height,2*np.cos(x/8-phase)]).astype(np.float32)
        condition=np.zeros((7,32,32),np.float32);condition[0]=height/128;condition[1]=.5;condition[2]=.4;condition[3+index%4]=1
        metadata={'reference':'world-x-y-z-plane72','origin':[0,0],'spacing':2,'source':'synthetic execution fixture'}
        np.savez_compressed(data/f'{index}.npz',vectors=vectors,condition=condition,metadata=json.dumps(metadata))
    device='cuda' if torch.cuda.is_available() else 'cpu'
    def run(*args):subprocess.run([sys.executable,'-B','-m','vdm_diffusion',*map(str,args)],cwd=ROOT,check=True)
    run('train','--data',data,'--output',root/'fixture.pt','--data-kind','synthetic-fixture','--steps',32,'--batch',2,'--width',8,'--timesteps',32,'--device',device)
    run('sample','--checkpoint',root/'fixture.pt','--condition',data/'0.npz','--output',root/'raw','--steps',16,'--device',device,'--allow-experimental')
    mask=np.sin(np.linspace(0,np.pi,32))[:,None]*np.sin(np.linspace(0,np.pi,32))[None,:]
    np.save(root/'cliff-mask.npy',mask.astype(np.float32))
    run('sculpt-cliff','--input',root/'raw/displacement.npz','--mask',root/'cliff-mask.npy','--output',root/'cliff','--center',32,32,'--normal',1,0)
    with np.load(root/'raw/displacement.npz') as result:vector=result['vectors']
    report={'passed':True,'device':device,'gpu':torch.cuda.get_device_name() if device=='cuda' else None,
            'torch':torch.__version__,'training_steps':32,'shape':list(vector.shape),
            'channel_std':vector.std(axis=(1,2)).tolist(),'max_abs_displacement':np.max(np.abs(vector),axis=(1,2)).tolist(),
            'terrain_quality_passed':False,'quality':'synthetic smoke test only; NOT terrain-quality weights; short training produces unrealistic displacement magnitudes'}
    (root/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)

if __name__=='__main__':main()
