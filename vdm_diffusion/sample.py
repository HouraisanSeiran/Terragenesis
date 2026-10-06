"""Generate XYZ directly by reverse diffusion; never substitute displacement rules."""
import hashlib
import numpy as np
import torch
from diffusion.paths import inside
from .checkpoint import load
from .data import load_pair
from .process import VectorDiffusion
from .export import export

def sample(args):
    torch.set_num_threads(4)
    model,config,provenance=load(args.checkpoint,args.device,args.allow_experimental)
    _,condition,metadata=load_pair(inside(args.condition),require_vectors=False)
    tensor=torch.from_numpy(condition)[None].to(args.device)
    normalized=VectorDiffusion(config,args.device).sample(model,tensor,args.seed,args.steps)[0].cpu().numpy()
    vectors=normalized*np.asarray(config.vector_scale,dtype=np.float32)[:,None,None]
    # Dataset metadata cannot override checkpoint provenance.
    provenance=dict(metadata,**provenance)
    provenance.update(generator='direct-xyz-conditional-ddim',seed=args.seed,sampling_steps=args.steps,
                      checkpoint_sha256=hashlib.sha256(inside(args.checkpoint).read_bytes()).hexdigest(),
                      condition_sha256=hashlib.sha256(inside(args.condition).read_bytes()).hexdigest(),
                      quality='unvalidated-research-output')
    export(args.output,vectors,provenance)
    print('Direct XYZ diffusion output:',inside(args.output),flush=True)
