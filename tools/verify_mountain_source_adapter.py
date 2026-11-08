"""Fixed CPU source verification; real inference requires explicit idle-GPU release."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.common_infra import (
    file_sha256,
    load_legacy_source,
    load_physical_source,
    load_source_bundle,
    publish_bytes,
    save_source,
)


FROZEN_FILES = (
    'terrain_pipeline/runoff.py', 'terrain_pipeline/runoff.py',
    "tools/verify_mountain_rainfall.py", "tools/verify_mountain_runoff_routing.py",
    'tests/test_runoff.py', "tests/test_mountain_rainfall.py", "tests/test_mountain_runoff_routing.py",
    "diffusion/physical_config.py", "diffusion/geography_physical.py", "diffusion/physical_backend.py",
    "tools/verify_physical_generation.py", "tests/test_physical_generation.py",
    "terrain_pipeline/minecraft_preset.py", "tests/test_minecraft_preset.py",
    "diffusion/geographic_noise.py", 'terrain_pipeline/lake.py',
    'terrain_pipeline/surface_domain.py',
)


def snapshot():
    from tools.verify_mountain_rainfall import SOURCE_ROOT, EXPECTED

    paths = [ROOT / name for name in FROZEN_FILES]
    paths.extend(ROOT / name for name in (
        "verification/mountain-rainfall/run-20261001T044308831149Z/report.json",
        "verification/mountain-rainfall/run-20261001T044308831149Z/independent-review.json",
        "verification/mountain-runoff-routing/run-20261001T054707951205Z/report.json",
        "verification/physical-generation-v1-frozen-20261001/cpu-report.json"))
    for name in EXPECTED:
        paths.extend((SOURCE_ROOT / f"{name}.npz", SOURCE_ROOT / f"{name}-provenance.json"))
        provenance = json.loads((SOURCE_ROOT / f"{name}-provenance.json").read_text(encoding="utf-8"))
        paths.append(ROOT / Path(provenance["source_npz"].replace("\\", "/")))
    return {str(path.relative_to(ROOT)).replace("\\", "/"): file_sha256(path) for path in paths}


def assert_unchanged(before):
    after = snapshot()
    changed = [name for name in before if before[name] != after.get(name)]
    if changed:
        raise RuntimeError("frozen/source files changed: " + ", ".join(changed))
    return {"files": len(before), "unchanged": True, "sha256": after}


def write_json(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))


def verify_cpu(destination):
    if destination.exists():
        raise FileExistsError(destination)
    before = snapshot()
    write_json(destination / "frozen-before.json", before)
    report = {"status": "cpu_source_adapter_verified", "gpu_inference_run": False,
        "hydrological_closure_certified": False, "sources": {}}
    try:
        for name in ("normal_mountain", "pressure_mountain"):
            source = load_legacy_source(name)
            path = destination / f"{name}.npz"
            save_source(path, source)
            loaded = load_source_bundle(path, expected_sha256=file_sha256(path),
                expected_identity=source["identity_sha256"], trusted_source=source)
            report["sources"][name] = {"identity_sha256": source["identity_sha256"],
                "archive_sha256": file_sha256(path), "metadata": loaded["metadata"],
                "minimum_m": float(loaded["arrays"]["height_m"].min()),
                "maximum_m": float(loaded["arrays"]["height_m"].max()),
                "shape": list(loaded["arrays"]["height_m"].shape)}
        report["frozen_after"] = assert_unchanged(before)
        write_json(destination / "report.json", report)
        return report
    except BaseException as error:
        write_json(destination / "failure.json", {"exception": type(error).__name__,
            "message": str(error), "traceback": traceback.format_exc(), "gpu_inference_run": False})
        raise


def inference_preflight(*, gpu_released, size=256):
    if gpu_released is not True:
        raise RuntimeError("GPU not released by coordinator; no inference permitted")
    if type(size) is not int or not 1 <= size <= 256:
        raise ValueError("this finite experiment permits at most 256 squared")
    from diffusion.physical_config import PhysicalGenerationConfig

    config = PhysicalGenerationConfig()
    config.generation_identity()
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu",
        "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
    rows = [[int(value.strip()) for value in row.split(",")] for row in gpu.stdout.strip().splitlines()]
    processes = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=True)
    if "limbuscompany" in processes.stdout.lower():
        raise RuntimeError("user game still running; no GPU interference permitted")
    if len(rows) != 1 or rows[0][0] > 1024 or rows[0][1] < 6000 or rows[0][2] > 5:
        raise RuntimeError("GPU resource preflight failed")
    return config, {"used_mib": rows[0][0], "free_mib": rows[0][1], "utilization_percent": rows[0][2],
        "size": size, "batch": 1, "windows": 2, "oom_retry": False,
        "limitation": "request size is not a VRAM guarantee; upstream halo can be larger"}


def generate_overlap(destination, *, gpu_released, seed=20261001, x=0, z=0, size=256):
    if destination.exists():
        raise FileExistsError(destination)
    before = snapshot()
    write_json(destination / "frozen-before.json", before)
    backend = None
    try:
        config, resources = inference_preflight(gpu_released=gpu_released, size=size)
        write_json(destination / "resource-preflight.json", resources)
        from diffusion.paths import configure
        from diffusion.physical_backend import PhysicalTerrainDiffusionBackend

        configure()
        backend = PhysicalTerrainDiffusionBackend(config)
        windows = []
        for label, origin_x in (("primary", x), ("overlap", x + size // 2)):
            elevation, climate, metadata = backend.generate(seed, origin_x, z, size)
            import io

            buffer = io.BytesIO()
            np.savez_compressed(buffer, elevation_m=elevation, climate=climate,
                                metadata_json=np.array(json.dumps(metadata)))
            raw = destination / f"{label}-td-output.npz"
            publish_bytes(raw, buffer.getvalue())
            source = load_physical_source(raw, expected_sha256=file_sha256(raw), boundary={
                "policy": "all_edges_open", "halo_cells": 0,
                "upstream_contribution": "excluded_finite_experiment"})
            save_source(destination / f"{label}-source.npz", source)
            windows.append((elevation, climate, metadata))
        offset = size // 2
        comparisons = {}
        for name, first, second in (("elevation_m", windows[0][0][:, offset:], windows[1][0][:, :size-offset]),
                ("climate", windows[0][1][:, :, offset:], windows[1][1][:, :, :size-offset])):
            absolute = np.abs(first.astype(np.float64) - second)
            relative = absolute / np.maximum(np.maximum(np.abs(first), np.abs(second)), 1e-12)
            comparisons[name] = {"max_absolute": float(absolute.max()), "mean_absolute": float(absolute.mean()),
                "max_relative": float(relative.max()), "exact": bool(np.array_equal(first, second))}
        report = {"gpu_inference_run": True, "windows": [item[2] for item in windows],
            "overlap": comparisons, "frozen_after": assert_unchanged(before),
            "naturalness_certified": False, "hydrological_closure_certified": False}
        write_json(destination / "report.json", report)
        return report
    except BaseException as error:
        write_json(destination / "failure.json", {"exception": type(error).__name__, "message": str(error),
            "traceback": traceback.format_exc(), "no_downloads": True, "no_game_interference": True})
        raise
    finally:
        if backend is not None:
            backend.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--gpu-released", action="store_true")
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--x", type=int, default=0)
    parser.add_argument("--z", type=int, default=0)
    parser.add_argument("--size", type=int, default=256)
    args = parser.parse_args()
    destination = args.output or ROOT / "verification/mountain-source-adapter" / (
        "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    report = generate_overlap(destination, gpu_released=args.gpu_released, seed=args.seed,
        x=args.x, z=args.z, size=args.size) if args.generate else verify_cpu(destination)
    print(json.dumps({"output": str(destination), "status": report.get("status", "actual_td_overlap_recorded")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
