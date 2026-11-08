"""Immutable generation identity, shared by cache and runtime protocol."""
from dataclasses import dataclass,asdict
from pathlib import Path
import hashlib,json
import math
from .paths import ROOT,inside

@dataclass(frozen=True)
class GenerationConfig:
    model_dir:str='models/terrain-diffusion-30m'
    device:str='cuda'
    dtype:str='fp32'
    blocks_per_pixel:int=2
    meters_per_height_block:float=30.0
    sea_level:int=72
    tile_pixels:int=64
    conditions:str|None=None
    cond_snr:tuple=(0.3,0.1,1.0,0.1,1.0)
    conditioning_mode:str='geographic_v1'
    v4_land_base_factor:float|None=None
    v4_mountain_relief_factor:float|None=None
    v4_ocean_depth_m:float|None=None
    v5_base_knee_m:float|None=None
    v5_base_headroom_m:float|None=None
    def __post_init__(self):
        if self.device not in ('cuda','cpu'):raise ValueError('device must be cuda or cpu')
        if self.dtype not in ('fp16','fp32'):raise ValueError('dtype must be fp16 or fp32')
        if not 1<=self.blocks_per_pixel<=16 or self.tile_pixels!=64:raise ValueError('Unsupported grid scale')
        if not 1<=self.meters_per_height_block<=1000:raise ValueError('Invalid vertical scale')
        if self.sea_level!=72:raise ValueError('Current Minecraft protocol requires sea level 72')
        if len(self.cond_snr)!=5:raise ValueError('Five conditioning strengths required')
        if any(not math.isfinite(value) or value < 0 or value > 100 for value in self.cond_snr):
            raise ValueError('Conditioning strengths must be finite and between 0 and 100')
        if self.conditioning_mode not in ('geographic_v1','geographic_v2','geographic_v3','geographic_v4','geographic_v5','legacy_worldclim'):raise ValueError('Unsupported conditioning mode')
        v4_values=(self.v4_land_base_factor,self.v4_mountain_relief_factor,self.v4_ocean_depth_m)
        if self.conditioning_mode=='geographic_v4':
            if (any(type(v) not in (int,float) or not math.isfinite(v) for v in v4_values) or
                    not 0<self.v4_land_base_factor<=1 or
                    not 0<self.v4_mountain_relief_factor<=1 or
                    not 0<self.v4_ocean_depth_m<=1100):
                raise ValueError('Invalid geographic_v4 metre-scale conditioning parameters')
        elif any(v is not None for v in v4_values):
            raise ValueError('geographic_v4 parameters require geographic_v4')
        v5_values=(self.v5_base_knee_m,self.v5_base_headroom_m)
        if self.conditioning_mode=='geographic_v5':
            if (any(type(v) not in (int,float) or not math.isfinite(v) for v in v5_values) or
                    not 0<self.v5_base_knee_m<=3600 or
                    not 0<self.v5_base_headroom_m<=3600):
                raise ValueError('Invalid geographic_v5 base compression parameters')
        elif any(v is not None for v in v5_values):
            raise ValueError('geographic_v5 parameters require geographic_v5')
        inside(self.model_dir)
        if self.conditions:inside(self.conditions)
    @classmethod
    def for_profile(cls, profile, **overrides):
        if profile=='geographic_v2':
            settings={'conditioning_mode':profile,'meters_per_height_block':6.0,
                      'cond_snr':(0.65,0.1,1.0,0.1,1.0)}
        elif profile=='geographic_v3':
            settings={'conditioning_mode':profile,'meters_per_height_block':1.0,
                      'cond_snr':(0.1,0.1,1.0,0.1,1.0)}
        elif profile=='geographic_v4':
            settings={'conditioning_mode':profile,'meters_per_height_block':1.0,
                      'cond_snr':(0.1,0.1,1.0,0.1,1.0),
                      'v4_land_base_factor':0.12,'v4_mountain_relief_factor':0.18,
                      'v4_ocean_depth_m':80.0}
        elif profile=='geographic_v5':
            settings={'conditioning_mode':profile,'meters_per_height_block':1.0,
                      'cond_snr':(0.1,0.1,1.0,0.1,1.0),
                      'v5_base_knee_m':120.0,'v5_base_headroom_m':80.0}
        else:
            settings={'conditioning_mode':profile}
        settings.update(overrides)
        return cls(**settings)
    def identity(self):
        manifest=inside(self.model_dir)/'manifest.json'
        if not manifest.exists():raise RuntimeError('Model weights missing. Run tools/download_model.py first.')
        metadata=json.loads(manifest.read_text(encoding='utf-8'))
        upstream=json.loads((ROOT/'runtime/upstream.json').read_text())
        config=self.record()
        if self.conditioning_mode=='legacy_worldclim':config.pop('conditioning_mode')
        value={'schema':2,'config':config,'model':metadata,'upstream':upstream['revision']}
        if self.conditioning_mode=='geographic_v1':
            source=b''.join(Path(__file__).with_name(name).read_bytes()
                for name in ('geography.py','geographic_noise.py'))
            value['geography_sha256']=hashlib.sha256(source).hexdigest()
        elif self.conditioning_mode=='geographic_v2':
            source=b''.join(Path(__file__).with_name(name).read_bytes()
                for name in ('geography_v2.py','geographic_noise.py'))
            value['geography_sha256']=hashlib.sha256(source).hexdigest()
        elif self.conditioning_mode=='geographic_v3':
            source=b''.join(Path(__file__).with_name(name).read_bytes()
                for name in ('geography_v3.py','geography_v2.py','geographic_noise.py'))
            value['geography_sha256']=hashlib.sha256(source).hexdigest()
        elif self.conditioning_mode=='geographic_v4':
            source=b''.join(Path(__file__).with_name(name).read_bytes()
                for name in ('geography_v4.py','geography_v2.py','geographic_noise.py'))
            value['geography_sha256']=hashlib.sha256(source).hexdigest()
        elif self.conditioning_mode=='geographic_v5':
            source=b''.join(Path(__file__).with_name(name).read_bytes()
                for name in ('geography_v5.py','geography_v2.py','geographic_noise.py'))
            value['geography_sha256']=hashlib.sha256(source).hexdigest()
        if self.conditions:
            value['condition_sha256']=hashlib.sha256(inside(self.conditions).read_bytes()).hexdigest()
        return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest(),value

    def record(self):
        config=asdict(self)
        if self.conditioning_mode!='geographic_v4':
            for name in ('v4_land_base_factor','v4_mountain_relief_factor','v4_ocean_depth_m'):
                config.pop(name)
        if self.conditioning_mode!='geographic_v5':
            for name in ('v5_base_knee_m','v5_base_headroom_m'):
                config.pop(name)
        return config
