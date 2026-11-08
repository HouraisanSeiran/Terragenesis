"""Pinned upstream model adapter. One seed at a time; caller serializes access."""
import json,sys,time
from .paths import ROOT,inside

class TerrainDiffusionBackend:
    def __init__(self,config):
        self.config=config;self.pipeline=None;self.seed=None;self.identity,self.metadata=config.identity()
    def load(self):
        if self.pipeline is not None:return
        upstream=json.loads((ROOT/'runtime/upstream.json').read_text())
        sys.path.insert(0,str(inside(upstream['source'])))
        import torch
        from terrain_diffusion.inference.world_pipeline import WorldPipeline
        if self.config.conditioning_mode in ('geographic_v1','geographic_v2','geographic_v3','geographic_v4','geographic_v5'):
            config=self.config
            if self.config.conditioning_mode=='geographic_v5':
                from .geography_v5 import make_geographic_map_factory
            elif self.config.conditioning_mode=='geographic_v4':
                from .geography_v4 import make_geographic_map_factory
            elif self.config.conditioning_mode=='geographic_v3':
                from .geography_v3 import make_geographic_map_factory
            elif self.config.conditioning_mode=='geographic_v2':
                from .geography_v2 import make_geographic_map_factory
            else:
                from .geography import make_geographic_map_factory
            class GeographicWorldPipeline(WorldPipeline):
                def _init_conditioning(self):
                    options={'seed':self.seed,'frequency_mult':self.kwargs['frequency_mult'],
                             'drop_water_pct':self.kwargs['drop_water_pct']}
                    if config.conditioning_mode=='geographic_v4':
                        options.update(land_base_factor=config.v4_land_base_factor,
                                       mountain_relief_factor=config.v4_mountain_relief_factor,
                                       ocean_depth_m=config.v4_ocean_depth_m)
                    elif config.conditioning_mode=='geographic_v5':
                        options.update(base_knee_m=config.v5_base_knee_m,
                                       base_headroom_m=config.v5_base_headroom_m)
                    self.synthetic_map_factory=make_geographic_map_factory(**options)
            pipeline_type=GeographicWorldPipeline
        else:
            pipeline_type=WorldPipeline
        if self.config.device=='cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable; refusing silent CPU/procedural fallback')
        torch.set_num_threads(4)
        self.pipeline=pipeline_type.from_pretrained(str(inside(self.config.model_dir)),seed=0,
            latents_batch_size=1,torch_compile=False,dtype=self.config.dtype if self.config.dtype=='fp16' else None,
            caching_strategy='direct',cache_limit=256*1024*1024,cond_snr=list(self.config.cond_snr))
        self.pipeline.to(self.config.device)
        if self.config.conditions:
            self._install_conditions()
        self.pipeline.bind()
    def _install_conditions(self):
        import numpy as np
        # Existing checkpoints understand these five physical channels, not arbitrary landform labels.
        names=('elevation','temperature','temperature_std','precipitation','precipitation_cv')
        with np.load(inside(self.config.conditions),allow_pickle=False) as data:
            origin=data['origin'].astype(int)
            for channel,name in enumerate(names):
                if name in data:
                    self.pipeline.set_custom_conditioning_import(channel,data[name],int(origin[0]),int(origin[1]),rebuild=False)
    def generate(self,seed,x,z,size):
        import torch
        self.load()
        normalized=seed&0xffffffffffffffff
        if normalized!=self.seed:
            self.pipeline.change_seed(normalized);self.seed=normalized
        started=time.perf_counter()
        with torch.inference_mode():
            output=self.pipeline.get(z,x,z+size,x+size,with_climate=True)
        elev=output['elev'].detach().float().cpu().numpy()
        # Upstream additionally returns temperature lapse rate; the public tile contract keeps BIO1/4/12/15.
        climate=output['climate'][:4].detach().float().cpu().numpy()
        return elev,climate,{'seconds':time.perf_counter()-started,'native_resolution_m':self.pipeline.native_resolution,
            'backend':'TerrainDiffusion/WorldPipeline','identity':self.identity,'seed':str(seed),'native_origin':[x,z]}
    def close(self):
        if self.pipeline is not None:self.pipeline.close()
