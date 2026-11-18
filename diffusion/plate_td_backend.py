"""Explicit spawned, budget-supervised frozen-plate TD inference."""
import hashlib
import json
import multiprocessing as mp
import queue
import time
from pathlib import Path

import numpy as np

from diffusion.physical_config import PhysicalGenerationConfig
from diffusion.plate_td_conditioning import PLATE_IDENTITY, WORLD_SEED, make_plate_factory, conditioning_footprint
from diffusion.world_layout_backend import BUDGETS, BudgetExceeded, _child_rss_mib


def _worker(record, result_queue):
    try:
        import sys
        import torch
        from diffusion.paths import ROOT, inside
        config = PhysicalGenerationConfig.from_record(record["config"])
        factory = make_plate_factory(record["source"], record["plate_identity"], record["seed"], config)
        model = json.loads((inside(config.model_dir) / "config.json").read_text(encoding="utf-8"))
        if model["native_resolution"] != 30 or model["native_resolution"] * model["latent_compression"] * 32 != 7680:
            raise ValueError("checkpoint grid mismatch")
        upstream = json.loads((ROOT / "runtime/upstream.json").read_text(encoding="utf-8"))
        sys.path.insert(0, str(inside(upstream["source"])))
        from terrain_diffusion.inference.world_pipeline import WorldPipeline

        class PlatePipeline(WorldPipeline):
            def _init_conditioning(self):
                self.synthetic_map_factory = factory

        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(min(1.0, BUDGETS["gpu_peak_mib"] * 2**20 / total), device=0)
        torch.set_num_threads(2)
        torch.cuda.reset_peak_memory_stats(0)
        pipeline = PlatePipeline.from_pretrained(str(inside(config.model_dir)), seed=record["seed"],
            latents_batch_size=1, torch_compile=False, dtype=None,
            caching_strategy="direct", cache_limit=64 * 1024 * 1024, cond_snr=list(config.cond_snr))
        try:
            pipeline.to("cuda")
            pipeline.bind()
            x, z = record["origin"]
            side = record["side"]
            with torch.inference_mode():
                out = pipeline.get(z, x, z + side, x + side, with_climate=True)
            elevation = out["elev"].detach().float().cpu().numpy()
            climate = out["climate"].detach().float().cpu().numpy()
        finally:
            pipeline.close()
        result_queue.put({"ok": True, "elevation": elevation, "climate": climate,
                          "allocated_peak_mib": torch.cuda.max_memory_allocated(0) / 2**20,
                          "reserved_peak_mib": torch.cuda.max_memory_reserved(0) / 2**20})
    except BaseException as error:
        import traceback
        result_queue.put({"ok": False, "error": str(error), "traceback": traceback.format_exc()})


def generate(source, origin, side, config, *, expected_identity):
    """Generate one window; no fallback, one worker, fixed FP32 and budgets."""
    if (len(origin) != 2 or any(type(v) is not int for v in origin) or
            type(side) is not int or not 1 <= side <= 1337 or config.dtype != "fp32"):
        raise ValueError("integer origin, side 1..1337 and fp32 required")
    factory = make_plate_factory(source, expected_identity, WORLD_SEED, config)
    footprint = conditioning_footprint(origin, side)
    factory.sample_raw(footprint[0], footprint[1], footprint[2], footprint[3])
    generation_id, generation = config.generation_identity()
    files = [Path(__file__), Path(__file__).with_name("plate_td_conditioning.py"),
             Path(__file__).parents[1] / "terrain_pipeline/tectonic.py",
             Path(__file__).parents[1] / "terrain_pipeline/coastal_terrain.py",
             Path(__file__).with_name("geographic_noise.py")]
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    import psutil
    staging = 300_000_000 + side * side * 160
    if psutil.virtual_memory().available < BUDGETS["host_rss_mib"] * 2**20 + staging:
        raise BudgetExceeded("available_host_memory", psutil.virtual_memory().available,
                             "full worker RSS budget must be available before launch")
    import subprocess
    try:
        query = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5, check=True)
        free_mib = int(query.stdout.splitlines()[0].strip())
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as error:
        raise BudgetExceeded("gpu_free", None, "cannot measure free GPU memory") from error
    if free_mib < BUDGETS["gpu_peak_mib"]:
        raise BudgetExceeded("gpu_free", free_mib, "full worker GPU cap must be free")
    record = {"source": str(Path(source).resolve()), "plate_identity": expected_identity,
              "seed": WORLD_SEED, "origin": list(origin), "side": side, "config": config.record()}
    context = mp.get_context("spawn")
    results = context.Queue()
    process = context.Process(target=_worker, args=(record, results))
    start = time.perf_counter()
    process.start()
    rss = gpu = 0.0
    try:
        result = None
        while result is None:
            if time.perf_counter() - start > BUDGETS["wall_clock_s"]:
                raise BudgetExceeded("wall_clock_s", time.perf_counter() - start, "deadline exceeded")
            try:
                result = results.get(timeout=BUDGETS["poll_interval_s"])
            except queue.Empty:
                if not process.is_alive():
                    raise RuntimeError("worker exited without result")
                rss = max(rss, _child_rss_mib(process.pid))
                if rss > BUDGETS["host_rss_mib"]:
                    raise BudgetExceeded("memory", max(rss, gpu), "worker exceeded budget")
        if not result["ok"]:
            raise RuntimeError(result["error"] + "\n" + result["traceback"])
        for key in ("allocated_peak_mib", "reserved_peak_mib"):
            if not isinstance(result.get(key), (int, float)) or not np.isfinite(result[key]) or not 0 <= result[key] <= BUDGETS["gpu_peak_mib"]:
                raise RuntimeError("missing or excessive allocator peak: " + key)
        elevation, climate = result["elevation"], result["climate"]
        if (elevation.shape != (side, side) or climate.shape != (5, side, side) or
                not np.isfinite(elevation).all() or not np.isfinite(climate).all()):
            raise ValueError("invalid TD output")
        if before != {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}:
            raise RuntimeError("source code changed during inference")
        metadata = {"record": record, "physical_generation_identity": generation_id,
                    "physical_generation": generation, "source_sha256": before,
                    "coordinates": "30m cell centres; x east, z south; arrays [z,x]; sea datum 0m",
                    "boundary": "finite reject; product bilinear interpolation wraps at edge",
                    "peak_child_rss_mib": rss, "gpu_monitor": "allocator",
                    "gpu_scope": "PyTorch allocator only; excludes driver, non-PyTorch allocations and other processes",
                    "allocated_peak_mib": result["allocated_peak_mib"], "reserved_peak_mib": result["reserved_peak_mib"],
                    "wall_clock_s": time.perf_counter() - start, "budgets": dict(BUDGETS, page_side_cells=side)}
        return elevation, climate, metadata
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()
        results.close()
