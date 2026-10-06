"""Opt-in local TD inference; no legacy runtime or game-coordinate conversion."""
import json
import sys
import time

from .geography_physical import make_physical_map_factory
from .paths import ROOT, inside
from .physical_config import PhysicalGenerationConfig


class PhysicalTerrainDiffusionBackend:
    def __init__(self, config):
        if not isinstance(config, PhysicalGenerationConfig):
            raise ValueError("PhysicalGenerationConfig required")
        self.config = config
        self.pipeline = None
        self.seed = None
        self.identity, self.metadata = config.generation_identity()

    def load(self):
        if self.pipeline is not None:
            return
        model_config = json.loads((inside(self.config.model_dir) / "config.json").read_text())
        native_resolution = model_config["native_resolution"]
        coarse_spacing = native_resolution * model_config["latent_compression"] * 32
        if (native_resolution != self.config.native_resolution_m
                or coarse_spacing != self.config.conditioning_spacing_m):
            raise ValueError("Physical grid must match checkpoint native/coarse metre spacing")
        upstream = json.loads((ROOT / "runtime/upstream.json").read_text())
        sys.path.insert(0, str(inside(upstream["source"])))
        import torch
        from terrain_diffusion.inference.world_pipeline import WorldPipeline

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA required; no silent procedural fallback")
        config = self.config

        class PhysicalWorldPipeline(WorldPipeline):
            def _init_conditioning(self):
                self.synthetic_map_factory = make_physical_map_factory(int(self.seed), config)

        torch.set_num_threads(4)
        pipeline = PhysicalWorldPipeline.from_pretrained(str(inside(config.model_dir)), seed=0,
            latents_batch_size=1, torch_compile=False,
            dtype=config.dtype if config.dtype == "fp16" else None,
            caching_strategy="direct", cache_limit=256 * 1024 * 1024,
            cond_snr=list(config.cond_snr))
        try:
            pipeline.to("cuda")
            pipeline.bind()
        except BaseException:
            pipeline.close()
            raise
        self.pipeline = pipeline

    def generate(self, seed, x, z, size):
        if any(type(value) is not int for value in (seed, x, z, size)) or not 1 <= size <= 513:
            raise ValueError("Integer seed/native window required; size must be 1..513")
        import numpy as np
        import torch

        self.load()
        normalized = seed & 0xFFFFFFFFFFFFFFFF
        if normalized != self.seed:
            self.pipeline.change_seed(normalized)
            self.seed = normalized
        started = time.perf_counter()
        with torch.inference_mode():
            output = self.pipeline.get(z, x, z + size, x + size, with_climate=True)
        elevation = output["elev"].detach().float().cpu().numpy()
        climate = output["climate"].detach().float().cpu().numpy()
        if (elevation.shape != (size, size) or climate.shape != (5, size, size)
                or not np.isfinite(elevation).all() or not np.isfinite(climate).all()):
            raise RuntimeError("TD produced invalid physical shape/channels or nonfinite data")
        metadata = dict(self.metadata, identity=self.identity, seed=str(normalized),
            native_origin=[x, z], shape=[size, size], native_resolution_m=self.config.native_resolution_m,
            artifact_kind="terrain_diffusion_output", seconds=time.perf_counter() - started)
        return elevation, climate, metadata

    def close(self):
        if self.pipeline is not None:
            self.pipeline.close()
            self.pipeline = None
            self.seed = None
