"""Single-page layout-driven Terrain Diffusion backend, supervised by real budgets.

What this is
------------
One page of native terrain whose **conditioning** comes from the constructive layout
(:mod:`diffusion.world_layout_conditioning`) instead of the frozen physical conditioner.
New source ⇒ new config, new identity; nothing here touches ``PhysicalGenerationConfig``,
``geography_physical`` or any frozen page.

Why the budgets are enforced in a parent process
------------------------------------------------
Measuring after the fact is not a limit. ``torch.cuda.max_memory_allocated`` and an RSS
snapshot can only tell you what already happened, and on Windows ``resource`` does not
exist while ``psutil`` gives a sampled value, not a peak. So the page runs in a **child
process** and the parent:

* polls the child's RSS and device memory at a fixed interval and kills the tree the moment
  either exceeds its ceiling;
* enforces wall clock with a hard deadline on the same loop;
* treats "cannot measure" as a **preflight refusal**, not as "fine";
* reports the breach and leaves no product -- the run is recorded as failed.

Hook and index semantics (verified in the vendored pipeline)
-----------------------------------------------------------
``WorldPipeline._init_conditioning`` (``world_pipeline.py:685``) is the real override point
and assigns ``self.synthetic_map_factory``. ``_conditioning_model_input`` calls it as
``self.synthetic_map_factory(cj0, ci0, cj1, ci1)`` -- **columns first**, half-open -- so the
factory's four arguments are ``(j1, i1, j2, i2)``. ``get(i1, j1, i2, j2)`` takes native
cell indices, half-open, ``i`` rows / ``j`` columns. Indices are native 30 m cells; the
*conditioning* grid is 7680 m, so the factory converts.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from pathlib import Path

__all__ = [
    "BUDGETS",
    "BudgetExceeded",
    "PAGE_SIDE_CELLS",
    "NATIVE_RESOLUTION_M",
    "CONDITIONING_SPACING_M",
    "DEFAULT_SEED",
    "preflight",
    "run_single_page",
    "describe_budgets",
]

#: One page of native cells per side, as authorised.
PAGE_SIDE_CELLS = 129

#: TD native sampling/routing spacing, metres.
NATIVE_RESOLUTION_M = 30.0

#: Conditioning-grid spacing for the 30 m checkpoint (``latent_compression 8 * 32``).
CONDITIONING_SPACING_M = NATIVE_RESOLUTION_M * 8 * 32

#: The fixed world seed. Recorded in the report and actually passed to the pipeline.
DEFAULT_SEED = 20261020

#: Hard budgets. Exceeding any of these kills the run and records a failure.
BUDGETS = {
    "page_side_cells": PAGE_SIDE_CELLS,
    "gpu_peak_mib": 4 * 1024,
    "host_rss_mib": 4 * 1024,
    "wall_clock_s": 120.0,
    "output_mib": 64,
    "pages_per_call": 1,
    "poll_interval_s": 0.25,
}


class BudgetExceeded(RuntimeError):
    """A declared hard budget was exceeded; the run is recorded as failed."""

    def __init__(self, budget, observed, message):
        super().__init__("%s: %s (observed %r, budget %r)"
                         % (budget, message, observed, BUDGETS.get(budget)))
        self.budget = budget
        self.observed = observed


def describe_budgets(gpu_monitor="pid"):
    gpu_enforcement = ("child PyTorch allocator ceiling and reported reserved peak; "
                       "excludes driver and other processes" if gpu_monitor == "allocator"
                       else "parent polls child process GPU memory")
    return {"page_side_cells": PAGE_SIDE_CELLS, "budgets": dict(BUDGETS),
            "enforcement": "parent polls child RSS and wall clock; " + gpu_enforcement,
            "retry_policy": "none; a breach fails and is recorded, never retried",
            "native_resolution_m": NATIVE_RESOLUTION_M,
            "conditioning_spacing_m": CONDITIONING_SPACING_M,
            "default_seed": DEFAULT_SEED, "pages_per_call": 1}


def _device_memory_mib():
    """Allocated device memory right now, or raise if it cannot be measured."""
    import torch
    if not torch.cuda.is_available():
        return 0.0
    return float(torch.cuda.memory_allocated() / 2 ** 20)


def _child_rss_mib(pid):
    """Sampled RSS of the child process, or raise if it cannot be measured."""
    import psutil
    return float(psutil.Process(pid).memory_info().rss) / (1024.0 ** 2)


def _child_gpu_mib(pid):
    """Device memory used by **the child process**, read from NVML via nvidia-smi.

    ``torch.cuda.memory_allocated`` in the parent measures the parent's context, which for
    a spawned child is zero -- it is not a supervisor. This reads per-process usage from
    ``nvidia-smi --query-compute-apps`` instead. If that cannot be read the caller must
    refuse rather than assume the child is under budget.
    """
    import subprocess
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=False)
    except BaseException as error:
        raise BudgetExceeded("measurement", type(error).__name__,
                             "cannot query nvidia-smi for the child's device memory; "
                             "refusing rather than reporting the parent's zero") from None
    if completed.returncode != 0:
        raise BudgetExceeded("measurement", completed.returncode,
                             "nvidia-smi failed while supervising the child")
    total = 0.0
    found = False
    for line in completed.stdout.splitlines():
        parts = [piece.strip() for piece in line.split(",")]
        if len(parts) != 2:
            continue
        try:
            if int(parts[0]) == int(pid):
                total += float(parts[1])
                found = True
        except ValueError:
            if parts[0] == str(pid):
                raise BudgetExceeded("measurement", parts[1],
                                     "child GPU memory is unavailable") from None
    del found
    return total


def _collect_result(process, queue, timeout_s):
    """Drain the queue before joining so large payloads do not block the feeder."""
    import queue as queue_module
    try:
        result = queue.get(timeout=float(timeout_s))
    except queue_module.Empty:
        return None
    process.join(timeout=1.0)
    return result


def _check_driver_monitoring():
    """Reject Windows WDDM, which does not expose per-process GPU memory."""
    if os.name != "nt":
        return
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_model.current",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BudgetExceeded("measurement", str(error),
                             "cannot determine Windows GPU driver model") from None
    if result.returncode != 0 or not result.stdout.strip():
        raise BudgetExceeded("measurement", result.stderr.strip(),
                             "cannot determine Windows GPU driver model")
    if any(line.strip().upper() == "WDDM" for line in result.stdout.splitlines()):
        raise BudgetExceeded("measurement", "WDDM",
                             "per-process GPU memory is unavailable under WDDM")


def preflight(model_dir, *, gpu_monitor="pid"):
    """Refuse before any work if the budget cannot actually be measured.

    "Cannot measure" must never be treated as "within budget".
    """
    if gpu_monitor not in ("pid", "allocator"):
        raise ValueError("gpu_monitor must be 'pid' or 'allocator'")
    if gpu_monitor == "pid":
        _check_driver_monitoring()
    try:
        import psutil  # noqa: F401
    except BaseException as error:
        raise BudgetExceeded("measurement", type(error).__name__,
                             "cannot measure host RSS (psutil unavailable); refusing "
                             "rather than running unsupervised") from None
    try:
        import torch
        if not torch.cuda.is_available():
            raise BudgetExceeded("device", None,
                                 "CUDA is required for a native page; refusing")
        _device_memory_mib()
    except BudgetExceeded:
        raise
    except BaseException as error:
        raise BudgetExceeded("measurement", type(error).__name__,
                             "cannot read device memory; refusing rather than running "
                             "unsupervised") from None
    if not os.path.isdir(str(model_dir)):
        raise BudgetExceeded("model_dir", str(model_dir),
                             "model directory is missing; nothing is downloaded here")
    return {"psutil": True, "device_memory": True, "model_dir": str(model_dir),
            "budgets": dict(BUDGETS)}


def _page_worker(payload, queue):
    """Child process: rebuild the factory from plain records, then generate one page.

    ``spec`` and ``config`` are passed as **plain records** and the factory is rebuilt
    inside the child. A closure cannot cross a Windows ``spawn`` boundary -- pickling it
    fails -- so nothing callable is ever put in the payload.
    """
    try:
        import sys
        import torch

        sys.path.insert(0, payload["upstream_source"])
        sys.path.insert(0, payload["repo_root"])
        from terrain_diffusion.inference.world_pipeline import WorldPipeline
        from diffusion.world_layout_conditioning import (
            WorldLayoutGenerationConfig,
            make_conditioning_map,
        )
        from terrain_pipeline.world_water_layout import LayoutSpec

        spec = LayoutSpec(**payload["spec_record"])
        config = WorldLayoutGenerationConfig(**payload["config_record"])
        factory = make_conditioning_map(spec, config,
                                        origin_world_m=(0.0, 0.0),
                                        conditioning_spacing_m=payload["conditioning_spacing_m"])

        class LayoutWorldPipeline(WorldPipeline):
            def _init_conditioning(self):
                self.synthetic_map_factory = factory

        # Hard per-process device ceiling, enforced inside the process that allocates.
        fraction = payload["gpu_fraction"]
        if torch.cuda.is_available():
            total = torch.cuda.get_device_properties(0).total_memory
            ceiling = min(1.0, BUDGETS["gpu_peak_mib"] * 2 ** 20 / total)
            torch.cuda.set_per_process_memory_fraction(
                ceiling if fraction is None else min(fraction, ceiling), device=0)

        pipeline = LayoutWorldPipeline.from_pretrained(
            payload["model_dir"], seed=int(payload["seed"]), latents_batch_size=1,
            torch_compile=False,
            dtype=payload["dtype"] if payload["dtype"] == "fp16" else None,
            caching_strategy="direct", cache_limit=256 * 1024 * 1024,
            cond_snr=list(payload["cond_snr"]))
        pipeline.to(payload["device"])
        pipeline.bind()
        try:
            row0, col0 = payload["origin_native_rc"]
            side = int(payload["side"])
            with torch.inference_mode():
                out = pipeline.get(row0, col0, row0 + side, col0 + side, with_climate=True)
        finally:
            pipeline.close()
        elevation = out["elev"].detach().float().cpu().numpy()
        climate = out["climate"][:4].detach().float().cpu().numpy()
        reserved = None
        if torch.cuda.is_available():
            reserved = float(torch.cuda.max_memory_reserved() / 2 ** 20)
        queue.put({"ok": True, "elevation": elevation, "climate": climate,
                   "peak_reserved_mib": reserved})
    except BaseException as error:  # reported, never swallowed
        import traceback
        queue.put({"ok": False, "error": "%s: %s" % (type(error).__name__, error),
                   "traceback": traceback.format_exc()})


def run_single_page(spec, config, *, origin_native_xz, model_dir,
                    seed=DEFAULT_SEED, device="cuda", dtype="fp32",
                    cond_snr=(0.65, 0.1, 1.0, 0.1, 1.0), gpu_fraction=None,
                    gpu_monitor="pid"):
    """Generate **one** native page under real parent-process supervision.

    ``origin_native_xz`` is the page origin in **native 30 m cells** (integers), used
    verbatim: the page's world position is ``origin * 30 m``. It does **not** have to land
    on the 7680 m conditioning grid -- the factory converts indices itself, so forcing a
    conditioning-grid origin would reject legitimate coast pages for no reason.
    """
    from diffusion.world_layout_conditioning import WorldLayoutGenerationConfig

    if not isinstance(config, WorldLayoutGenerationConfig):
        raise ValueError("WorldLayoutGenerationConfig required")
    if config.layout_identity != spec.identity():
        raise ValueError("conditioning identity does not match the layout")
    for value, name in zip(origin_native_xz, ("origin_x", "origin_z")):
        if type(value) is not int:
            raise ValueError("%s must be an integer native cell index" % name)
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if seed != spec.world_seed:
        raise ValueError("page seed must match the layout world seed")

    preflight(model_dir, gpu_monitor=gpu_monitor)

    # `origin_native_xz` is (x, z) worldspeak; `get` wants (row=i, col=j) = (z, x).
    origin_x_cell, origin_z_cell = int(origin_native_xz[0]), int(origin_native_xz[1])
    origin_world = (origin_x_cell * NATIVE_RESOLUTION_M, origin_z_cell * NATIVE_RESOLUTION_M)
    origin_native_rc = (origin_z_cell, origin_x_cell)
    if spec.mode == "finite":
        end_x = origin_world[0] + (PAGE_SIDE_CELLS - 1) * NATIVE_RESOLUTION_M
        end_z = origin_world[1] + (PAGE_SIDE_CELLS - 1) * NATIVE_RESOLUTION_M
        fx, fz = spec.frame_origin_m
        if not (fx <= origin_world[0] and fz <= origin_world[1] and
                end_x < fx + spec.frame_side_m and end_z < fz + spec.frame_side_m):
            raise ValueError("native page lies outside the finite world")

    repo_root = Path(__file__).resolve().parents[1]
    upstream = json.loads((repo_root / "runtime/upstream.json").read_text())
    upstream_source = str((repo_root / upstream["source"]).resolve())

    # Nothing callable crosses the spawn boundary: the factory is rebuilt in the child
    # from these two plain records. Only relative geometry is passed, so the child
    # rebuilds the identical world.
    payload = {"spec_record": spec_parameters(spec),
               "config_record": config_record(config),
               "model_dir": str(model_dir), "seed": int(seed),
               "device": device, "dtype": dtype, "cond_snr": tuple(cond_snr),
               "origin_world_m": [origin_world[0], origin_world[1]],
               "conditioning_spacing_m": CONDITIONING_SPACING_M,
               "origin_native_rc": [origin_native_rc[0], origin_native_rc[1]],
               "side": PAGE_SIDE_CELLS, "upstream_source": upstream_source,
               "repo_root": str(repo_root), "gpu_fraction": gpu_fraction}

    context = mp.get_context("spawn")
    queue = context.Queue()
    started = time.perf_counter()
    process = context.Process(target=_page_worker, args=(payload, queue))
    process.start()

    import queue as queue_module
    breach = None
    result = None
    peak_rss = 0.0
    peak_device = 0.0
    while process.is_alive():
        try:
            result = queue.get_nowait()
            break
        except queue_module.Empty:
            pass
        try:
            peak_rss = max(peak_rss, _child_rss_mib(process.pid))
            if gpu_monitor == "pid":
                peak_device = max(peak_device, _child_gpu_mib(process.pid))
        except BudgetExceeded as error:
            breach = error
            break
        except BaseException as error:
            breach = BudgetExceeded("measurement", type(error).__name__,
                                    "measurement failed while the page was running")
            break
        if peak_rss > BUDGETS["host_rss_mib"]:
            breach = BudgetExceeded("host_rss_mib", peak_rss, "child RSS exceeded 4 GiB")
            break
        if peak_device > BUDGETS["gpu_peak_mib"]:
            breach = BudgetExceeded("gpu_peak_mib", peak_device,
                                    "device memory exceeded 4 GiB")
            break
        if time.perf_counter() - started > BUDGETS["wall_clock_s"]:
            breach = BudgetExceeded("wall_clock_s", time.perf_counter() - started,
                                    "wall clock exceeded 120 s")
            break
        time.sleep(BUDGETS["poll_interval_s"])

    if breach is not None:
        process.terminate()
        process.join(timeout=30)
        if process.is_alive():
            process.kill()
        raise breach

    # Drain the result before joining: the queue feeder can block on a large array.
    if result is None:
        try:
            result = queue.get(timeout=2.0)
        except queue_module.Empty:
            result = None
    process.join(timeout=5.0)
    if process.is_alive():
        process.terminate()
        process.join()
    elapsed = time.perf_counter() - started
    if result is None:
        raise BudgetExceeded("worker", process.exitcode,
                             "worker exited without a readable result; recorded as a "
                             "failure rather than an empty success")
    if not result.get("ok"):
        raise RuntimeError("page generation failed: %s\n%s"
                           % (result.get("error"), result.get("traceback", "")))

    reserved = result.get("peak_reserved_mib")
    if gpu_monitor == "allocator":
        if not isinstance(reserved, (int, float)) or not 0 <= reserved < float("inf"):
            raise BudgetExceeded("measurement", reserved,
                                 "child allocator peak is unavailable")
        if reserved > BUDGETS["gpu_peak_mib"]:
            raise BudgetExceeded("gpu_peak_mib", reserved,
                                 "PyTorch allocator peak exceeded 4 GiB")

    elevation = result["elevation"]
    climate = result["climate"]
    if elevation.shape != (PAGE_SIDE_CELLS, PAGE_SIDE_CELLS):
        raise RuntimeError("unexpected elevation shape %r" % (elevation.shape,))
    output_mib = (elevation.nbytes + climate.nbytes) / (1024.0 ** 2)
    if output_mib > BUDGETS["output_mib"]:
        raise BudgetExceeded("output_mib", output_mib, "output exceeded 64 MiB")

    return {"elevation": elevation, "climate": climate,
            "metadata": {"schema": "world-layout-single-page-v1",
                         "layout_identity": config.layout_identity,
                         "conditioning_identity": config.identity(),
                         "page_side_cells": PAGE_SIDE_CELLS,
                         "origin_native_xz": [origin_x_cell, origin_z_cell],
                         "origin_world_m": list(origin_world),
                         "conditioning_spacing_m": CONDITIONING_SPACING_M,
                         "native_resolution_m": NATIVE_RESOLUTION_M,
                         "seed": int(seed), "device": device, "dtype": dtype,
                         "wall_clock_s": elapsed,
                         "peak_child_rss_mib": peak_rss,
                         "peak_device_mib": peak_device if gpu_monitor == "pid" else None,
                         "gpu_monitor": gpu_monitor,
                         "peak_allocator_reserved_mib": reserved,
                         "gpu_limit_scope": (
                             "pytorch_allocator_only_excludes_driver_and_other_processes"
                             if gpu_monitor == "allocator" else "child_process_gpu_memory"),
                         "output_mib": output_mib, "budgets": dict(BUDGETS),
                         "claim_level": "single_page_native_30m_layout_conditioned",
                         "not_claimed": ["multi-page assembly", "natural outlet",
                                         "hydraulics", "1 m measurement accuracy",
                                         "climate channels (declared placeholders)"]}}


def spec_parameters(spec):
    """Plain, picklable constructor arguments for a ``LayoutSpec``.

    The child rebuilds the spec from these so no closure ever crosses a spawn boundary.
    """
    record = {"preset": spec.preset, "total_water_fraction": spec.total_water_fraction,
              "world_seed": spec.world_seed, "layout_id": spec.layout_id,
              "mode": spec.mode, "region_side_m": spec.region_side_m,
              "w_geom_m": spec.w_geom_m, "b_geom_m": spec.b_geom_m,
              "h_design_m": spec.h_design_m, "epsilon_m": spec.epsilon_m}
    if spec.mode == "finite":
        record["frame_origin_m"] = list(spec.frame_origin_m)
        record["frame_side_m"] = spec.frame_side_m
    return record


def config_record(config):
    """Plain, picklable constructor arguments for ``WorldLayoutGenerationConfig``."""
    return {"layout_identity": config.layout_identity, "preset": config.preset,
            "mode": config.mode,
            "target_water_fraction": config.target_water_fraction,
            "native_resolution_m": config.native_resolution_m,
            "sea_datum_m": config.sea_datum_m,
            "land_base_m": config.land_base_m,
            "land_relief_m": config.land_relief_m,
            "ocean_depth_m": config.ocean_depth_m,
            "lake_bed_offset_m": config.lake_bed_offset_m,
            "borrowed_from_base": dict(config.borrowed_from_base)}
