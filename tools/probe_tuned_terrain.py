"""Sample one real Terrain Diffusion profile without changing its output."""
from pathlib import Path
import argparse
from dataclasses import asdict
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from diffusion.backend import TerrainDiffusionBackend
from diffusion.config import GenerationConfig
from diffusion.paths import configure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("geographic_v1", "geographic_v2", "geographic_v3", "geographic_v4", "geographic_v5"), default="geographic_v2")
    parser.add_argument("--seed", type=int, default=20260927)
    parser.add_argument("--x", type=int, default=11520)
    parser.add_argument("--z", type=int, default=15360)
    parser.add_argument("--size", type=int, default=257)
    parser.add_argument("--label", default="peak")
    parser.add_argument("--elevation-snr", type=float)
    parser.add_argument("--meters-per-height-block", type=float)
    parser.add_argument("--v4-land-base-factor", type=float)
    parser.add_argument("--v4-mountain-relief-factor", type=float)
    parser.add_argument("--v4-ocean-depth-m", type=float)
    parser.add_argument("--v5-base-knee-m", type=float)
    parser.add_argument("--v5-base-headroom-m", type=float)
    args = parser.parse_args()
    if not 2 <= args.size <= 513:
        parser.error("--size must be 2..513")
    if not args.label or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in args.label):
        parser.error("--label must contain only letters, digits, - or _")
    configure()
    output = ROOT / "verification" / "tuned-model"
    output.mkdir(parents=True, exist_ok=True)
    stem = f"{args.label}-{args.profile}-seed{args.seed}-x{args.x}-z{args.z}"
    archive_path = output / f"{stem}.npz"
    result = output / f"{stem}.json"
    if archive_path.exists() or result.exists():
        raise FileExistsError(f"probe output already exists: {stem}")
    overrides = {}
    if args.elevation_snr is not None:
        overrides["cond_snr"] = (args.elevation_snr, 0.1, 1.0, 0.1, 1.0)
    if args.meters_per_height_block is not None:
        overrides["meters_per_height_block"] = args.meters_per_height_block
    for name in ("v4_land_base_factor", "v4_mountain_relief_factor", "v4_ocean_depth_m",
                 "v5_base_knee_m", "v5_base_headroom_m"):
        value = getattr(args, name)
        if value is not None:
            overrides[name] = value
    config = GenerationConfig.for_profile(args.profile, **overrides)
    backend = TerrainDiffusionBackend(config)
    try:
        elevation, climate, metadata = backend.generate(args.seed, args.x, args.z, args.size)
        world_y = 62 + elevation.astype(np.float64) / config.meters_per_height_block
        gradient_z, gradient_x = np.gradient(world_y)
        roughness = np.hypot(gradient_x, gradient_z)
        report = {
            "profile": args.profile, "seed": args.seed, "native_origin": [args.x, args.z],
            "size": args.size, "identity": backend.identity,
            "generation_config": config.record(),
            "world_mapping": {"world_sea_level": 62, "world_y_formula": "62 + elevation_m / meters_per_height_block"},
            "native_resolution_m": metadata["native_resolution_m"],
            "blocks_per_pixel": config.blocks_per_pixel,
            "meters_per_height_block": config.meters_per_height_block,
            "cond_snr": config.cond_snr, "generation_seconds": metadata["seconds"],
            "elevation_m": {"min": float(elevation.min()), "max": float(elevation.max()),
                            "p50": float(np.percentile(elevation, 50)), "p95": float(np.percentile(elevation, 95))},
            "mapped_world_y": {"min": float(world_y.min()), "max": float(world_y.max()),
                               "p50": float(np.percentile(world_y, 50)), "p95": float(np.percentile(world_y, 95)),
                               "above_800_percent": float(np.mean(world_y > 800) * 100),
                               "above_1023_percent": float(np.mean(world_y > 1023) * 100),
                               "below_minus_64_percent": float(np.mean(world_y < -64) * 100)},
            "roughness_world_y_per_native_pixel": {"mean": float(roughness.mean()),
                                                   "p95": float(np.percentile(roughness, 95))},
            "note": "Raw model elevation is unchanged; world Y is a fixed units mapping, not per-tile normalization."
        }
        np.savez_compressed(archive_path, elevation=elevation, climate=climate,
                            metadata=json.dumps(metadata), generation_config=json.dumps(config.record()),
                            world_mapping=json.dumps(report["world_mapping"]))
        result.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(result, flush=True)
    finally:
        backend.close()


if __name__ == "__main__":
    main()
