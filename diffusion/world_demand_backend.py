"""Explicit, supervised generation of fixed physical-TD source pages."""
from __future__ import annotations

import hashlib
import json
import math
import multiprocessing as mp
import os
import queue
import tempfile
import time
from pathlib import Path

from diffusion.physical_config import PhysicalGenerationConfig
from diffusion.world_layout_backend import BUDGETS, BudgetExceeded, _child_rss_mib, preflight

PAGE_SIDE = 513
CORE_STRIDE = 464
PAGE_MARGIN = 24
SOURCE_FAMILY = "physical-default-v1"


def plan_source_pages(origin_native_xz, shape_zx):
    """Return fixed source-page origins for the half-open target window."""
    if (not isinstance(origin_native_xz, (list, tuple)) or len(origin_native_xz) != 2 or
            not isinstance(shape_zx, (list, tuple)) or len(shape_zx) != 2 or
            any(type(v) is not int for v in (*origin_native_xz, *shape_zx)) or
            any(v <= 0 for v in shape_zx)):
        raise ValueError("origin and shape must be integer pairs with positive shape")
    x, z = origin_native_xz
    rows, cols = shape_zx
    return [[i * CORE_STRIDE - PAGE_MARGIN, j * CORE_STRIDE - PAGE_MARGIN]
            for j in range(z // CORE_STRIDE, (z + rows - 1) // CORE_STRIDE + 1)
            for i in range(x // CORE_STRIDE, (x + cols - 1) // CORE_STRIDE + 1)]


def _worker(payload, result_queue):
    try:
        import torch
        from diffusion.physical_backend import PhysicalTerrainDiffusionBackend

        total = torch.cuda.get_device_properties(0).total_memory
        torch.cuda.set_per_process_memory_fraction(min(1.0, 4096 * 2 ** 20 / total), device=0)
        backend = PhysicalTerrainDiffusionBackend(PhysicalGenerationConfig.from_record(payload["config"]))
        try:
            x, z = payload["origin"]
            elevation, _, metadata = backend.generate(payload["seed"], x, z, PAGE_SIDE)
            reserved = float(torch.cuda.max_memory_reserved() / 2 ** 20)
        finally:
            backend.close()
        result_queue.put({"ok": True, "elevation": elevation, "generation": metadata,
                          "peak_allocator_reserved_mib": reserved})
    except BaseException as error:
        import traceback
        result_queue.put({"ok": False, "error": "%s: %s" % (type(error).__name__, error),
                          "traceback": traceback.format_exc()})


def _supervise(payload):
    context = mp.get_context("spawn")
    result_queue = context.Queue()
    process = context.Process(target=_worker, args=(payload, result_queue))
    started = time.perf_counter()
    process.start()
    peak_rss = 0.0
    result = None
    try:
        while True:
            elapsed = time.perf_counter() - started
            if elapsed > BUDGETS["wall_clock_s"]:
                raise BudgetExceeded("wall_clock_s", elapsed, "source page exceeded 120 s")
            try:
                result = result_queue.get(timeout=BUDGETS["poll_interval_s"])
                if time.perf_counter() - started > BUDGETS["wall_clock_s"]:
                    raise BudgetExceeded("wall_clock_s", time.perf_counter() - started,
                                         "source page exceeded 120 s")
                break
            except queue.Empty:
                if not process.is_alive():
                    break
                peak_rss = max(peak_rss, _child_rss_mib(process.pid))
                if peak_rss > BUDGETS["host_rss_mib"]:
                    raise BudgetExceeded("host_rss_mib", peak_rss, "source page exceeded 4 GiB RSS")
        if result is None:
            raise RuntimeError("source worker exited without a result")
        if not result.get("ok"):
            raise RuntimeError("source worker failed: %s\n%s" %
                               (result.get("error"), result.get("traceback", "")))
        peak = result.get("peak_allocator_reserved_mib")
        if not isinstance(peak, (int, float)) or not math.isfinite(peak) or not 0 <= peak <= 4096:
            raise BudgetExceeded("gpu_peak_mib", peak, "allocator peak unavailable or above 4 GiB")
        result["peak_child_rss_mib"] = peak_rss
        result["wall_clock_s"] = time.perf_counter() - started
        return result
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join()
        result_queue.close()


def run_source_page(origin_native_xz, *, model_dir, output_dir, world_seed=20261020):
    """Generate or resume one fixed source page; failures are recorded, never retried."""
    import numpy as np
    from terrain_pipeline.surface_rivers.native_30m_source import _read_page

    if (not isinstance(origin_native_xz, (list, tuple)) or len(origin_native_xz) != 2 or
            any(type(v) is not int or (v + PAGE_MARGIN) % CORE_STRIDE for v in origin_native_xz)):
        raise ValueError("source origin must lie on the fixed source page grid")
    if type(world_seed) is not int or world_seed < 1:
        raise ValueError("world_seed must be a positive integer")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = "td-%d-%d-%d" % (*origin_native_xz, PAGE_SIDE)
    page_path = directory / (stem + ".npz")
    record_path = directory / (stem + ".json")
    failure_path = directory / (stem + ".failure.json")
    if failure_path.exists():
        raise RuntimeError("previous source page failure exists: %s" % failure_path)
    try:
        config = PhysicalGenerationConfig(model_dir=str(model_dir))
        generation_identity, generation = config.generation_identity()
    except Exception as error:
        with failure_path.open("x", encoding="utf-8") as output:
            json.dump({"error": "%s: %s" % (type(error).__name__, error),
                       "origin_native_xz": list(origin_native_xz), "world_seed": world_seed,
                       "source_family": SOURCE_FAMILY}, output, indent=2)
        raise
    if page_path.exists() or record_path.exists():
        if not page_path.is_file() or not record_path.is_file():
            raise RuntimeError("incomplete existing source page; refusing overwrite")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        page, metadata, origin = _read_page({"path": str(page_path), "sha256": record["sha256"]},
                                             seed=world_seed)
        if (origin != list(origin_native_xz) or page.shape != (PAGE_SIDE, PAGE_SIDE) or
                metadata.get("source_family") != SOURCE_FAMILY or
                metadata.get("physical_generation_identity") != generation_identity):
            raise ValueError("existing source page identity does not match request")
        return {"path": str(page_path.resolve()), "sha256": record["sha256"], "metadata": metadata}
    try:
        preflight(model_dir, gpu_monitor="allocator")
        result = _supervise({"config": config.record(), "origin": list(origin_native_xz),
                             "seed": world_seed})
        elevation = np.asarray(result["elevation"], dtype=np.float64)
        if elevation.shape != (PAGE_SIDE, PAGE_SIDE) or not np.isfinite(elevation).all():
            raise RuntimeError("source worker returned invalid elevation")
        if result["generation"]["identity"] != generation_identity:
            raise RuntimeError("worker physical generation identity changed")
        metadata = {"schema": "td-native-page-v1", "native_origin": list(origin_native_xz),
                    "size": PAGE_SIDE, "spacing_m": 30.0, "world_seed": world_seed,
                    "source_family": SOURCE_FAMILY,
                    "physical_generation_identity": generation_identity,
                    "physical_conditioning_identity": generation["conditioning_identity"],
                    "gpu_limit_scope": "pytorch_allocator_only_excludes_driver_and_other_processes",
                    "peak_allocator_reserved_mib": result["peak_allocator_reserved_mib"],
                    "peak_child_rss_mib": result["peak_child_rss_mib"],
                    "wall_clock_s": result["wall_clock_s"]}
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".npz", delete=False) as temp:
            temp_path = Path(temp.name)
        try:
            np.savez(temp_path, elevation_native=elevation,
                     metadata_json=np.array(json.dumps(metadata, sort_keys=True)))
            digest = hashlib.sha256(temp_path.read_bytes()).hexdigest()
            record = {"path": str(page_path.resolve()), "sha256": digest, "metadata": metadata}
            with record_path.open("x", encoding="utf-8") as output:
                json.dump(record, output, indent=2)
            try:
                os.link(temp_path, page_path)
            except Exception:
                record_path.unlink(missing_ok=True)
                raise
        finally:
            temp_path.unlink(missing_ok=True)
        return record
    except Exception as error:
        with failure_path.open("x", encoding="utf-8") as output:
            json.dump({"error": "%s: %s" % (type(error).__name__, error),
                       "origin_native_xz": list(origin_native_xz), "world_seed": world_seed,
                       "source_family": SOURCE_FAMILY}, output, indent=2)
        raise
