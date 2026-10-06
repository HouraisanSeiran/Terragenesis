"""Explicit provenance prevents untrained/synthetic checkpoints masquerading as terrain models."""
import os
import torch
from .config import VdmConfig
from .network import VdmDenoiser
from diffusion.paths import inside

def save(path,model,config,steps,data_kind,dataset_hash):
    path=inside(path);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.tmp')
    torch.save({'format':'remote-vdm-diffusion-v1','config':config.as_dict(),'model':model.state_dict(),
                'training_steps':steps,'data_kind':data_kind,'dataset_sha256':dataset_hash},temporary)
    os.replace(temporary,path)

def load(path,device,allow_experimental=False):
    data=torch.load(inside(path),map_location=device,weights_only=True)
    if data.get('format')!='remote-vdm-diffusion-v1' or data.get('training_steps',0)<1:raise ValueError('Not a trained VDM checkpoint')
    if data.get('data_kind')!='measured-vdm' and not allow_experimental:
        raise ValueError('Synthetic checkpoint: use --allow-experimental only for algorithm tests')
    config=VdmConfig(**data['config']);model=VdmDenoiser(config).to(device)
    model.load_state_dict(data['model'],strict=True);model.eval()
    provenance={k:data[k] for k in ('format','training_steps','data_kind','dataset_sha256')}
    return model,config,provenance
