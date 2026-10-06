"""Versioned model and coordinate contract, shared by training and sampling."""
from dataclasses import dataclass,asdict

@dataclass(frozen=True)
class VdmConfig:
    schema:int=1
    base_channels:int=32
    timesteps:int=1000
    # World-space blocks, with y vertical. Reference is (origin_x+i*spacing,72,origin_z+j*spacing).
    vector_scale:tuple=(16.0,128.0,16.0)
    condition_channels:int=7  # base elevation, temperature, precipitation, four region weights
    def __post_init__(self):
        if self.schema!=1 or self.condition_channels!=7:raise ValueError('Unsupported VDM contract')
        if self.base_channels<8 or self.base_channels%8:raise ValueError('Width must be a multiple of 8')
        if self.timesteps<2:raise ValueError('At least two diffusion steps required')
        if len(self.vector_scale)!=3 or any(not 0<s<10000 for s in self.vector_scale):raise ValueError('Invalid vector scales')
    def as_dict(self):return asdict(self)
