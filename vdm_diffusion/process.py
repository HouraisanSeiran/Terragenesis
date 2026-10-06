"""DDPM epsilon training and deterministic DDIM reverse sampling of all XYZ channels."""
import math
import torch

class VectorDiffusion:
    def __init__(self,config,device):
        t=torch.linspace(0,1,config.timesteps+1,device=device,dtype=torch.float64)
        curve=torch.cos((t+.008)/1.008*math.pi/2).square();curve=curve/curve[0]
        beta=(1-curve[1:]/curve[:-1]).clamp(max=.999)
        self.alpha=torch.cumprod(1-beta,dim=0).float();self.timesteps=config.timesteps
    def add_noise(self,clean,t,noise):
        a=self.alpha[t][:,None,None,None]
        return a.sqrt()*clean+(1-a).sqrt()*noise
    def loss(self,model,clean,condition,generator=None):
        t=torch.randint(self.timesteps,(clean.shape[0],),device=clean.device,generator=generator)
        noise=torch.randn(clean.shape,device=clean.device,generator=generator)
        predicted=model(self.add_noise(clean,t,noise),t,condition)
        return (predicted-noise).square().mean()
    @torch.inference_mode()
    def sample(self,model,condition,seed,steps=50):
        if not 2<=steps<=self.timesteps:raise ValueError('Sampling steps outside schedule')
        generator=torch.Generator(device=condition.device).manual_seed(seed&0x7fffffffffffffff)
        x=torch.randn((condition.shape[0],3,*condition.shape[-2:]),device=condition.device,generator=generator)
        schedule=torch.linspace(self.timesteps-1,0,steps,device=condition.device).round().long()
        model.eval()
        for index,t in enumerate(schedule):
            a=self.alpha[t];epsilon=model(x,t.expand(x.shape[0]),condition)
            clean=(x-(1-a).sqrt()*epsilon)/a.sqrt()
            next_a=self.alpha[schedule[index+1]] if index+1<len(schedule) else torch.ones_like(a)
            x=next_a.sqrt()*clean+(1-next_a).sqrt()*epsilon
        if not torch.isfinite(x).all():raise RuntimeError('Non-finite VDM sampling result')
        return x
