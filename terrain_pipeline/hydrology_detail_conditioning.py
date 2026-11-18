"""Opt-in genuine TD inference with frozen planning changes in elevation only.

The checkpoint has no watershed channel. This candidate is an experiment, never
a claimed drainage certificate, and original physical TD is saved separately.
"""

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from diffusion.geography_physical import make_physical_map_factory
from diffusion.physical_backend import PhysicalTerrainDiffusionBackend
from diffusion.paths import ROOT, inside
from terrain_pipeline.hydrology_detail import _interpolate


ALGORITHM = "frozen-plan-elevation-only-td-conditioning-v1"
RESOURCE_SETTINGS = {"light": {"cache_mib": 64, "threads": 2},
                     "balanced": {"cache_mib": 256, "threads": 4},
                     "large": {"cache_mib": 512, "threads": 8}}


def make_frozen_plan_factory(seed, config, plan):
    """Add frozen macro change to the existing continuous physical condition.

    This preserves the original physical generator between coarse planning
    nodes. The other four real condition channels are unchanged. All sampling
    uses absolute coordinates so window overlap and traversal order agree.
    """
    physical = make_physical_map_factory(seed, config)
    delta = np.asarray(plan["height_m"]) - np.asarray(plan["original_height_m"])
    if delta.ndim != 2 or not np.isfinite(delta).all():
        raise ValueError("finite frozen macro condition change required")
    ox, oz = plan["origin_xz_m"]
    spacing = plan["spacing_m"]

    def sample_raw(x1, z1, x2, z2):
        values = physical.sample_raw(x1, z1, x2, z2)
        east = np.arange(x1, x2)[None, :] * config.conditioning_spacing_m
        south = np.arange(z1, z2)[:, None] * config.conditioning_spacing_m
        x, z = np.broadcast_arrays((east - ox) / spacing, (south - oz) / spacing)
        known = (x >= 0) & (x <= delta.shape[1] - 1) & (z >= 0) & (z <= delta.shape[0] - 1)
        adjustment = _interpolate(delta, np.clip(x, 0, delta.shape[1] - 1), np.clip(z, 0, delta.shape[0] - 1))
        values[0] += np.where(known, adjustment, 0).astype(np.float32)
        return values

    def finalize(values):
        return physical.finalize(values)

    def sample_full(x1, z1, x2, z2):
        import torch

        values = finalize(sample_raw(x1, z1, x2, z2))
        values[0] = np.sign(values[0]) * np.sqrt(np.abs(values[0]))
        return torch.from_numpy(values)

    sample_full.sample_raw = sample_raw
    sample_full.finalize = finalize
    return sample_full


class PlannedTerrainDiffusionBackend(PhysicalTerrainDiffusionBackend):
    """Separate identity and cache for the elevation-conditioned TD candidate."""

    def __init__(self, config, plan, resource_tier="balanced"):
        super().__init__(config)
        if resource_tier not in RESOURCE_SETTINGS:
            raise ValueError("unknown resource scheduling tier")
        self.resource_settings = dict(RESOURCE_SETTINGS[resource_tier])
        self.plan = plan
        parent_identity = self.identity
        self.metadata = dict(self.metadata, schema="hydrology-planned-td-v1",
            parent_generation_identity=parent_identity, algorithm=ALGORITHM,
            plan_identity=plan["identity_sha256"],
            plan_condition_delta_sha256=hashlib.sha256((plan["height_m"] - plan["original_height_m"]).tobytes()).hexdigest(),
            adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            conditioning_contract="frozen global plan delta added only to physical elevation channel; no watershed channel")
        self.identity = hashlib.sha256(json.dumps(self.metadata, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def load(self):
        if self.pipeline is not None:
            return
        model_config = json.loads((inside(self.config.model_dir) / "config.json").read_text(encoding="utf-8"))
        native = model_config["native_resolution"]
        if native != self.config.native_resolution_m or native * model_config["latent_compression"] * 32 != self.config.conditioning_spacing_m:
            raise ValueError("physical checkpoint grid mismatch")
        upstream = json.loads((ROOT / "runtime/upstream.json").read_text(encoding="utf-8"))
        sys.path.insert(0, str(inside(upstream["source"])))
        import torch
        from terrain_diffusion.inference.world_pipeline import WorldPipeline

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA required for genuine planned TD candidate; no fallback")
        plan, config = self.plan, self.config

        class PlannedWorldPipeline(WorldPipeline):
            def _init_conditioning(self):
                self.synthetic_map_factory = (make_physical_map_factory(int(self.seed), config) if plan is None
                                              else make_frozen_plan_factory(int(self.seed), config, plan))

        torch.set_num_threads(self.resource_settings["threads"])
        pipeline = PlannedWorldPipeline.from_pretrained(str(inside(config.model_dir)), seed=0,
            latents_batch_size=1, torch_compile=False, dtype=config.dtype if config.dtype == "fp16" else None,
            caching_strategy="direct", cache_limit=self.resource_settings["cache_mib"] * 1024 * 1024,
            cond_snr=list(config.cond_snr))
        try:
            pipeline.to("cuda")
            pipeline.bind()
        except BaseException:
            pipeline.close()
            raise
        self.pipeline = pipeline


class ResourcePhysicalTerrainDiffusionBackend(PlannedTerrainDiffusionBackend):
    """Same immutable physical generation identity, actual alternate cache sizes."""

    def __init__(self, config, resource_tier="balanced"):
        PhysicalTerrainDiffusionBackend.__init__(self, config)
        if resource_tier not in RESOURCE_SETTINGS:
            raise ValueError("unknown resource scheduling tier")
        self.plan = None
        self.resource_settings = dict(RESOURCE_SETTINGS[resource_tier])


def candidate_change(original, candidate, spacing_m):
    if original.shape != candidate.shape or not np.isfinite(candidate).all():
        raise ValueError("finite aligned original and planned TD candidate required")
    change = candidate.astype(np.float64) - original.astype(np.float64)
    return {"delta_m": change, "ledger": {"maximum_abs_change_m": float(np.abs(change).max()),
            "absolute_change_volume_m3": float(np.abs(change).sum() * spacing_m ** 2),
            "rms_change_m": float(np.sqrt(np.mean(change ** 2)))},
            "semantics": "new genuine TD inference minus immutable original TD; not dynamic erosion",
            "global_hydrology_certified": False, "publishable": False}
