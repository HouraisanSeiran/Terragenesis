"""Train three-channel denoising from paired, world-space VDM maps."""
import hashlib
import torch
from torch.utils.data import DataLoader
from .config import VdmConfig
from .network import VdmDenoiser
from .process import VectorDiffusion
from .data import VdmDataset
from .checkpoint import save

def train(args):
    if args.steps<1 or args.batch<1:raise ValueError('Positive training steps/batch required')
    torch.manual_seed(args.seed);torch.set_num_threads(4)
    config=VdmConfig(base_channels=args.width,timesteps=args.timesteps)
    dataset=VdmDataset(args.data,config)
    from .data import load_pair
    if args.data_kind=='measured-vdm':
        for path in dataset.files:
            _,_,meta=load_pair(path)
            if meta.get('data_kind')!='measured-vdm' or not meta.get('source'):
                raise ValueError('Measured data must declare data_kind=measured-vdm and source per sample')
    digest=hashlib.sha256()
    for path in dataset.files:
        digest.update(path.name.encode());digest.update(path.read_bytes())
    loader=DataLoader(dataset,batch_size=args.batch,shuffle=True,num_workers=0)
    model=VdmDenoiser(config).to(args.device);process=VectorDiffusion(config,args.device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=args.learning_rate)
    iterator=iter(loader);model.train()
    for step in range(1,args.steps+1):
        try:clean,condition=next(iterator)
        except StopIteration:iterator=iter(loader);clean,condition=next(iterator)
        clean=clean.to(args.device);condition=condition.to(args.device)
        optimizer.zero_grad(set_to_none=True);loss=process.loss(model,clean,condition)
        if not torch.isfinite(loss):raise RuntimeError('Non-finite training loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1);optimizer.step()
        if step==1 or step%25==0 or step==args.steps:print(f'Step {step}/{args.steps}: epsilon MSE={loss.item():.6f}',flush=True)
    save(args.output,model,config,args.steps,args.data_kind,digest.hexdigest())
