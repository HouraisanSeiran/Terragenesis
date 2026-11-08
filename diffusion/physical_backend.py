"""Opt-in local TD inference; no legacy runtime or game-coordinate conversion."""
import json
import sys
import time

from .geography_physical import make_physical_map_factory
from .paths import ROOT, inside
from .physical_config import PhysicalGenerationConfig

# Declared window budget: the largest `size` (nodes per side, i.e. cells per side
# of the returned array) this backend will request from a single `pipeline.get`.
#
# This is a declared resource budget, not a property of the checkpoint: the
# decoder tiles its own work (`TensorWindow(size=512, stride=384)`) and the
# latent/conditioning lookups are padded and cropped, so any node count is
# arithmetically valid. What actually bounds the request is host memory and wall
# clock. Measurements on this workstation (RTX 2080 SUPER, 8 GiB), recorded in
# `.scratch/fine-terrain-01/td-window-0*.npz` by `tools/build_fine_terrain.py`:
#
#     1025 nodes   ~2.2 GiB peak, ~10 s (warm)
#     2049 nodes   2.2 GiB peak, 10.2 s / 43.1 s (two runs)
#
# The comment block in `tools/build_fine_terrain.py` quotes 21.4 s for 2049; the
# two recorded runs bracket that, so the order of magnitude is not in doubt.
#
# 1337 is the largest side this project currently asks for: 1336 intervals of
# 30 m = 40.08 km, the bounded acceptance window of the 30 m test baseline. Its
# 1.79e6 cells are 0.43x the 4.20e6 cells of the measured 2049 window, so the
# measurements above bound it with margin. Peak memory is dominated by the model
# and the conditioning pages rather than by the window, which is why the 1025 and
# 2049 runs peak at the same 2.2 GiB.
#
# Raising this constant requires a new measurement of the same kind, not an
# argument. Exceeding it must stay a rejection: no silent downscale, no automatic
# tiling.
MAX_WINDOW_CELLS = 1337

# Reference measurements quoted in the rejection message and in the metadata of
# every generated window. `None` means "not recorded for that size".
WINDOW_BUDGET_REFERENCE = {
    "window_cells": [1025, 2049],
    "peak_cuda_mib": 2180.77,
    "wall_seconds_by_size": {1025: "~10 (warm, not archived)", 2049: [43.0718, 10.2134]},
    "device": "NVIDIA GeForce RTX 2080 SUPER (8 GiB)",
    "torch": "2.9.1+cu126",
    "recorded_in": ".scratch/fine-terrain-01/td-window-0*.npz",
    "measured_by": "tools/build_fine_terrain.py::build_windows",
}

# Reason codes. They are stable strings so callers and reports can match on them
# instead of on prose.
WINDOW_NOT_INTEGER = "window_size_not_integer"
WINDOW_NOT_POSITIVE = "window_size_not_positive"
WINDOW_BUDGET_EXCEEDED = "window_budget_exceeded"


def window_budget(size):
    """Validate an explicit window budget and return the numbers it implies.

    Rejects with a reason code; never resizes, clamps or tiles on the caller's
    behalf.
    """
    if type(size) is not int:
        raise ValueError(WINDOW_NOT_INTEGER + ": size must be a plain int node count, got "
                         + type(size).__name__)
    if size < 1:
        raise ValueError(WINDOW_NOT_POSITIVE + ": size must be a positive node count, got "
                         + str(size))
    if size > MAX_WINDOW_CELLS:
        raise ValueError(
            WINDOW_BUDGET_EXCEEDED + ": requested %d nodes/side (%d cells) exceeds the declared "
            "MAX_WINDOW_CELLS=%d; measured reference: 2049 nodes = 2.2 GiB peak / 10-43 s on %s. "
            "Enlarging the budget needs a new measurement; this call is refused rather than "
            "downscaled or split" % (size, size * size, MAX_WINDOW_CELLS,
                                     WINDOW_BUDGET_REFERENCE["device"]))
    return {"max_window_cells": MAX_WINDOW_CELLS, "window_cells": size,
            "cells": size * size, "cell_fraction_of_max": (size * size)
            / float(MAX_WINDOW_CELLS * MAX_WINDOW_CELLS),
            "declared_reference": dict(WINDOW_BUDGET_REFERENCE)}


def _peak_cuda_mib():
    """Peak allocated MiB since the last reset, or (None, reason) without CUDA."""
    try:
        import torch
        if not torch.cuda.is_available():
            return None, "cuda_unavailable"
        return float(torch.cuda.max_memory_allocated() / 2 ** 20), "measured_since_reset"
    except BaseException as error:  # no CUDA build, driver error, teardown race
        return None, "peak_memory_unavailable: " + type(error).__name__


def _reset_peak_cuda():
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            return True
    except BaseException:
        pass
    return False


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
        """Generate one window; `size > 513` is allowed up to `MAX_WINDOW_CELLS`.

        The 513 limit used to be enforced here. It is now an explicit, declared
        budget (`window_budget`), because it was a guard and not a model limit:
        larger windows work and have been measured. Anything above the declared
        budget is refused with a reason code instead of being resized or split.

        This module is one of the files hashed by
        `PhysicalGenerationConfig.identity()`, so this change *necessarily* gives
        every new window a new generation identity. Windows written by the older
        code keep their recorded identity and are not re-certified here.
        """
        if any(type(value) is not int for value in (seed, x, z)):
            raise ValueError("Integer seed/native window required")
        budget = window_budget(size)
        import numpy as np
        import torch

        self.load()
        normalized = seed & 0xFFFFFFFFFFFFFFFF
        if normalized != self.seed:
            self.pipeline.change_seed(normalized)
            self.seed = normalized
        peak_reset = _reset_peak_cuda()
        started = time.perf_counter()
        with torch.inference_mode():
            output = self.pipeline.get(z, x, z + size, x + size, with_climate=True)
        elevation = output["elev"].detach().float().cpu().numpy()
        climate = output["climate"].detach().float().cpu().numpy()
        seconds = time.perf_counter() - started
        if (elevation.shape != (size, size) or climate.shape != (5, size, size)
                or not np.isfinite(elevation).all() or not np.isfinite(climate).all()):
            raise RuntimeError("TD produced invalid physical shape/channels or nonfinite data")
        peak_cuda_mib, peak_status = _peak_cuda_mib()
        metadata = dict(self.metadata, identity=self.identity, seed=str(normalized),
            native_origin=[x, z], shape=[size, size], native_resolution_m=self.config.native_resolution_m,
            artifact_kind="terrain_diffusion_output", seconds=seconds,
            window_budget=budget, peak_cuda_mib=peak_cuda_mib,
            peak_memory_status=peak_status,
            peak_memory_measured_since_reset=peak_reset)
        return elevation, climate, metadata

    def close(self):
        if self.pipeline is not None:
            self.pipeline.close()
            self.pipeline = None
            self.seed = None
