"""Small time-conditioned U-Net: noisy XYZ vectors + conditioning -> three noise channels."""
import math
import torch
from torch import nn
from torch.nn import functional as F

class TimeEmbedding(nn.Module):
    def __init__(self,width):
        super().__init__();self.width=width
        self.projection=nn.Sequential(nn.Linear(width,width*4),nn.SiLU(),nn.Linear(width*4,width*4))
    def forward(self,t):
        frequency=torch.exp(-math.log(10000)*torch.arange(self.width//2,device=t.device)/(self.width//2-1))
        angles=t.float()[:,None]*frequency[None]
        return self.projection(torch.cat([angles.sin(),angles.cos()],dim=1))

class ResidualBlock(nn.Module):
    def __init__(self,in_channels,out_channels,time_channels):
        super().__init__()
        self.first=nn.Sequential(nn.GroupNorm(8,in_channels),nn.SiLU(),nn.Conv2d(in_channels,out_channels,3,padding=1))
        self.time=nn.Linear(time_channels,out_channels*2)
        self.norm=nn.GroupNorm(8,out_channels)
        self.last=nn.Sequential(nn.SiLU(),nn.Conv2d(out_channels,out_channels,3,padding=1))
        self.skip=nn.Conv2d(in_channels,out_channels,1) if in_channels!=out_channels else nn.Identity()
    def forward(self,x,time):
        h=self.first(x);scale,shift=self.time(time).chunk(2,dim=1)
        h=self.norm(h)*(1+scale[:,:,None,None])+shift[:,:,None,None]
        return self.skip(x)+self.last(h)

class VdmDenoiser(nn.Module):
    def __init__(self,config):
        super().__init__();c=config.base_channels
        self.time=TimeEmbedding(c)
        self.input=nn.Conv2d(3+config.condition_channels,c,3,padding=1)
        self.enc1=ResidualBlock(c,c,4*c);self.down1=nn.Conv2d(c,2*c,4,stride=2,padding=1)
        self.enc2=ResidualBlock(2*c,2*c,4*c);self.down2=nn.Conv2d(2*c,4*c,4,stride=2,padding=1)
        self.middle=ResidualBlock(4*c,4*c,4*c)
        self.dec2=ResidualBlock(6*c,2*c,4*c);self.dec1=ResidualBlock(3*c,c,4*c)
        self.output=nn.Sequential(nn.GroupNorm(8,c),nn.SiLU(),nn.Conv2d(c,3,3,padding=1))
    def forward(self,noisy,time,condition):
        if noisy.ndim!=4 or noisy.shape[1]!=3 or condition.shape[0]!=noisy.shape[0] or condition.shape[2:]!=noisy.shape[2:]:
            raise ValueError('Expected aligned BCHW vectors and conditions')
        h,w=noisy.shape[-2:];pad=(0,(-w)%4,0,(-h)%4)
        joined=F.pad(torch.cat([noisy,condition],dim=1),pad,mode='replicate');t=self.time(time)
        a=self.enc1(self.input(joined),t);b=self.enc2(self.down1(a),t);c=self.middle(self.down2(b),t)
        d=self.dec2(torch.cat([F.interpolate(c,size=b.shape[-2:],mode='nearest'),b],dim=1),t)
        e=self.dec1(torch.cat([F.interpolate(d,size=a.shape[-2:],mode='nearest'),a],dim=1),t)
        return self.output(e)[:,:,:h,:w]
