"""Plan or explicitly generate a real 1024-square physical TD source."""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from diffusion.physical_config import PhysicalGenerationConfig
from diffusion.paths import inside

SOURCE_SIZE = 1024
TILE_SIZE = 513
TILE_CORE = 512
SEAM_DIAGNOSTIC_MAX_M = .25


def _digest(path):
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def _save_npz(path, **arrays):
    payload = io.BytesIO()
    np.savez_compressed(payload, **arrays)
    with Path(path).open("xb") as stream:
        stream.write(payload.getvalue())


def stitch_tiles(tiles, *, seam_tolerance_m=SEAM_DIAGNOSTIC_MAX_M):
    """Own each northwest core; retain shared halo only for seam evidence."""
    if set(tiles) != {(0, 0), (0, 1), (1, 0), (1, 1)}:
        raise ValueError("four indexed TD windows required")
    if not np.isfinite(seam_tolerance_m) or seam_tolerance_m < 0.:
        raise ValueError("nonnegative finite diagnostic seam tolerance required")
    first = np.asarray(tiles[0, 0][0])
    if first.ndim != 2 or first.shape[0] != first.shape[1] or first.shape[0] < 2:
        raise ValueError("square TD window including one halo cell required")
    side = first.shape[0]
    core = side - 1
    clean = {}
    for key in sorted(tiles):
        elevation, climate = (np.asarray(value) for value in tiles[key])
        if (elevation.shape != (side, side) or climate.shape != (5, side, side)
                or elevation.dtype not in (np.float32, np.float64)
                or climate.dtype not in (np.float32, np.float64)
                or not np.isfinite(elevation).all() or not np.isfinite(climate).all()):
            raise ValueError("finite float TD elevation [n,n] and climate [5,n,n] required")
        clean[key] = (elevation, climate)
    height = np.empty((2 * core, 2 * core), dtype=first.dtype)
    climate = np.empty((5, 2 * core, 2 * core), dtype=clean[0, 0][1].dtype)
    for (row, col), (elevation, conditions) in clean.items():
        z = slice(row * core, (row + 1) * core)
        x = slice(col * core, (col + 1) * core)
        height[z, x] = elevation[:core, :core]
        climate[:, z, x] = conditions[:, :core, :core]

    comparisons = {"elevation_m": [], "climate": []}
    for row in range(2):
        left, right = clean[row, 0], clean[row, 1]
        comparisons["elevation_m"].append(np.abs(left[0][:core, core].astype(np.float64)
                                                   - right[0][:core, 0]))
        comparisons["climate"].append(np.abs(left[1][:, :core, core].astype(np.float64)
                                               - right[1][:, :core, 0]))
    for col in range(2):
        north, south = clean[0, col], clean[1, col]
        comparisons["elevation_m"].append(np.abs(north[0][core, :core].astype(np.float64)
                                                   - south[0][0, :core]))
        comparisons["climate"].append(np.abs(north[1][:, core, :core].astype(np.float64)
                                               - south[1][:, 0, :core]))
    stats = {}
    for name, strips in comparisons.items():
        stats[name] = {"max_abs": max(float(strip.max()) for strip in strips),
                       "mean_abs": float(sum(float(strip.sum()) for strip in strips)
                                         / sum(strip.size for strip in strips)),
                       "individual_max_abs": [float(strip.max()) for strip in strips],
                       "strip_order": ["north_vertical", "south_vertical", "west_horizontal", "east_horizontal"]}
    accepted = stats["elevation_m"]["max_abs"] <= seam_tolerance_m
    audit = {"ownership": "northwest_512_core_per_513_tile",
             "comparison": "shared_halo_values_only_no_blend_or_resample",
             "diagnostic_seam_max_m": float(seam_tolerance_m),
             "elevation_m": stats["elevation_m"], "climate": stats["climate"],
             "accepted": accepted, "status": "diagnostic_seam_within_limit" if accepted else "seam_unverified",
             "hydrologic_seam_certified": False}
    return height, climate, audit


def _verify_model(config):
    model = inside(config.model_dir)
    manifest_path = model / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative, record in manifest["files"].items():
        target = (model / relative).resolve()
        if not target.is_relative_to(model) or target.stat().st_size != record["bytes"]:
            raise ValueError("model file missing or byte count differs: " + relative)
        if _digest(target) != record["sha256"]:
            raise ValueError("model file SHA256 differs: " + relative)
    return manifest, _digest(manifest_path)


def _gpu_preflight():
    games = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, check=True)
    if any(name in games.stdout.lower() for name in ("aces.exe", "aces64.exe", "warthunder.exe")):
        raise RuntimeError("War Thunder is running; TD GPU inference deferred")
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu",
                          "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
    rows = [[int(part.strip()) for part in line.split(",")]
            for line in gpu.stdout.strip().splitlines()]
    if len(rows) != 1 or len(rows[0]) != 3:
        raise RuntimeError("one CUDA GPU with readable resource counters required")
    used, free, utilization = rows[0]
    if used > 2048 or free < 6000 or utilization > 10:
        raise RuntimeError("GPU busy or free VRAM below 6000 MiB; TD inference deferred")
    return {"used_mib": used, "free_mib": free, "utilization_percent": utilization,
            "free_mib_minimum": 6000, "utilization_percent_maximum": 10}


def generate_source(destination, plan, config):
    manifest, manifest_sha = _verify_model(config)
    gpu = _gpu_preflight()
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1")
    from diffusion.paths import configure
    from diffusion.physical_backend import PhysicalTerrainDiffusionBackend

    configure()
    backend = PhysicalTerrainDiffusionBackend(config)
    tiles = {}
    records = []
    try:
        for row in range(2):
            for col in range(2):
                origin_x = plan["origin_native_xz"][0] + col * TILE_CORE
                origin_z = plan["origin_native_xz"][1] + row * TILE_CORE
                elevation, climate, metadata = backend.generate(plan["seed"], origin_x, origin_z, TILE_SIZE)
                # Validate before recording a raw source as a complete TD window.
                if (elevation.shape != (TILE_SIZE, TILE_SIZE) or climate.shape != (5, TILE_SIZE, TILE_SIZE)
                        or not np.isfinite(elevation).all() or not np.isfinite(climate).all()):
                    raise ValueError("TD window shape or finite-value check failed")
                tile_path = destination / f"tile-z{row}-x{col}.npz"
                _save_npz(tile_path, elevation_m=elevation, climate=climate,
                          metadata_json=np.array(json.dumps(metadata, allow_nan=False)))
                tiles[row, col] = (elevation, climate)
                records.append({"row": row, "column": col, "path": tile_path.name,
                                "sha256": _digest(tile_path), "native_origin_xz": [origin_x, origin_z],
                                "shape": [TILE_SIZE, TILE_SIZE], "generation_metadata": metadata})
    finally:
        backend.close()
    height, climate, seam = stitch_tiles(tiles, seam_tolerance_m=plan["diagnostic_seam_max_m"])
    generation_identity, _ = config.generation_identity()
    metadata = {"schema": "td-1024-source-v1", "source_kind": "generated_terrain",
                "artifact_kind": "terrain_diffusion_original_bed_stitched", "seed": plan["seed"],
                "origin_native_xz": plan["origin_native_xz"], "origin_m_xz": [
                    value * config.native_resolution_m for value in plan["origin_native_xz"]],
                "spacing_m": config.native_resolution_m, "shape": [SOURCE_SIZE, SOURCE_SIZE],
                "generation_identity": generation_identity, "physical_config": config.record(),
                "model_revision": manifest["revision"], "model_manifest_sha256": manifest_sha,
                "all_model_files_sha_verified": True, "tiles": records, "seam_audit": seam,
                "seam_accepted": seam["accepted"], "seam_status": seam["status"],
                "hydraulic_ready": False, "natural_outlet_verified": False,
                "hydrologic_seam_certified": False, "publishable": False,
                "gpu_preflight": gpu}
    source = destination / "source.npz"
    _save_npz(source, elevation_m=height, climate=climate,
              metadata_json=np.array(json.dumps(metadata, ensure_ascii=False, allow_nan=False)))
    _write_json(destination / "manifest.json", {"status": "generated_unverified",
                                                "source": source.name, "source_sha256": _digest(source),
                                                "metadata": metadata})
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--generate", action="store_true", help="Explicit CUDA inference")
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--x", type=int, default=-6144, help="native east pixel origin")
    parser.add_argument("--z", type=int, default=2048, help="native south pixel origin")
    parser.add_argument("--diagnostic-seam-max-m", type=float, default=SEAM_DIAGNOSTIC_MAX_M)
    args = parser.parse_args(argv)
    if not np.isfinite(args.diagnostic_seam_max_m) or args.diagnostic_seam_max_m < 0.:
        parser.error("diagnostic seam maximum must be finite and nonnegative")
    destination = args.output or (ROOT / "verification" / "td-1024-source" /
                                  ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")))
    destination = destination.resolve()
    if not destination.is_relative_to(ROOT) and args.output is None:
        raise ValueError("default output must stay inside workspace")
    if destination.exists() and (not args.generate or set(p.name for p in destination.iterdir()) != {"plan.json"}):
        raise FileExistsError(destination)
    destination.mkdir(parents=True, exist_ok=True)
    config = PhysicalGenerationConfig()
    plan = {"schema": "td-1024-generation-plan-v1", "gpu_inference_run": False,
            "seed": args.seed, "origin_native_xz": [args.x, args.z],
            "shape": [SOURCE_SIZE, SOURCE_SIZE], "spacing_m": config.native_resolution_m,
            "tile_shape": [TILE_SIZE, TILE_SIZE], "tile_origins_native_xz": [
                [args.x + col * TILE_CORE, args.z + row * TILE_CORE]
                for row in range(2) for col in range(2)],
            "diagnostic_seam_max_m": args.diagnostic_seam_max_m,
            "physical_config": config.record(), "requires_explicit_generate": True,
            "output": str(destination)}
    if not (destination / "plan.json").exists():
        _write_json(destination / "plan.json", plan)
    else:
        saved = json.loads((destination / "plan.json").read_text(encoding="utf-8"))
        if saved != plan:
            raise ValueError("generation parameters differ from saved plan")
    if not args.generate:
        print(json.dumps({"status": "planned_no_gpu", "plan": str(destination / "plan.json")}))
        return plan
    try:
        metadata = generate_source(destination, plan, config)
    except BaseException as error:
        _write_json(destination / "failure.json", {"status": "failed", "exception": type(error).__name__,
                                                   "message": str(error), "traceback": traceback.format_exc(),
                                                   "no_success_manifest": not (destination / "manifest.json").exists()})
        raise
    print(json.dumps({"status": "generated_unverified", "source": str(destination / "source.npz"),
                      "seam_accepted": metadata["seam_accepted"]}))
    return metadata


if __name__ == "__main__":
    main()
