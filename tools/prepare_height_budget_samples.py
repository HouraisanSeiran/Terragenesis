"""Prepare checked, immutable metre-scale highland samples from real model output."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from diffusion.config import GenerationConfig
from diffusion.geography_v3 import POSITIVE_ELEVATION_FACTOR
from terrain_pipeline.artifacts import ArtifactIdentity, TerrainArtifact
from terrain_pipeline.metric_region_storage import prepare_metric_region
from terrain_pipeline.minecraft_export import (SOFT_TARGET_SURFACE_Y,
                                                export_metric_minecraft,
                                                validate_minecraft_surface_heights)


SAMPLES = {
    "plateau": (20260927, -16000, -13952),
    "highland": (20260928, 384, 15488),
}
SOURCE_DIR = ROOT / "verification/tuned-model"
OUTPUT_DIR = ROOT / "verification/height-budget-v3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = OUTPUT_DIR / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir()
    config = GenerationConfig.for_profile("geographic_v3")
    identity, _ = config.identity()
    report = {"profile": "geographic_v3", "generation_identity": identity,
              "positive_elevation_factor": POSITIVE_ELEVATION_FACTOR,
              "elevation_snr": config.cond_snr[0],
              "soft_target_surface_y": SOFT_TARGET_SURFACE_Y,
              "hard_surface_y_bounds": [-64, 1022],
              "samples": {}}
    for label, (seed, x, z) in SAMPLES.items():
        stem = f"height-budget-{label}-geographic_v3-seed{seed}-x{x}-z{z}"
        path = SOURCE_DIR / f"{stem}.npz"
        source_hash = sha256(path)
        with np.load(path, allow_pickle=False) as archive:
            elevation = archive["elevation"].copy()
            metadata = json.loads(str(archive["metadata"].item()))
            recorded_config = json.loads(str(archive["generation_config"].item()))
        if (elevation.shape != (513, 513) or elevation.dtype != np.float32 or
                not np.isfinite(elevation).all() or metadata["identity"] != identity or
                int(metadata["seed"]) != seed or metadata["native_origin"] != [x, z] or
                metadata["native_resolution_m"] != 30 or
                recorded_config != json.loads(json.dumps(config.record()))):
            raise ValueError(f"source does not match pinned v3 generation: {label}")
        raw_game_y = validate_minecraft_surface_heights(elevation, 0)
        base = TerrainArtifact(
            kind="base", identity=ArtifactIdentity(
                backend="TerrainDiffusion/WorldPipeline", algorithm="geographic_v3_metric_import",
                algorithm_version="1", seed=seed,
                parameters={"generation_identity": identity, "source_sha256": source_hash,
                            "source_metadata": metadata, "generation_config": recorded_config}),
            reference_elevation_m=elevation.astype(np.float64) + 126,
            origin_x_m=x * 30, origin_z_m=z * 30,
            spacing_x_m=30, spacing_z_m=30,
            vertical_datum="core bottom = 0 m", sea_level_elevation_m=126)
        region_path = run_dir / f"{label}-region"
        snapshot_path = run_dir / f"{label}.tgmc"
        prepared = prepare_metric_region(base, region_path)
        game_y = validate_minecraft_surface_heights(prepared.reconstructed_elevation_m(),
                                                    prepared.base.sea_level_elevation_m)
        peak = float(game_y.max())
        export_metric_minecraft(region_path, snapshot_path)
        if sha256(path) != source_hash:
            raise ValueError(f"source changed while preparing: {label}")
        report["samples"][label] = {
            "raw_npz": str(path.relative_to(ROOT)), "raw_sha256": source_hash,
            "raw_elevation_min_m": float(elevation.min()),
            "raw_elevation_max_m": float(elevation.max()),
            "raw_game_y_max": float(raw_game_y.max()),
            "raw_above_y800_percent": float(np.mean(raw_game_y > SOFT_TARGET_SURFACE_Y) * 100),
            "processed_game_y_min": float(game_y.min()),
            "processed_game_y_max": peak,
            "processed_above_y800_percent": float(np.mean(game_y > SOFT_TARGET_SURFACE_Y) * 100),
            "top_margin_to_1024_blocks": 1024 - peak,
            "base_content_id": prepared.base.content_id,
            "derived_content_id": prepared.derived.content_id,
            "snapshot": str(snapshot_path.relative_to(ROOT)),
            "snapshot_sha256": sha256(snapshot_path),
        }
    destination = run_dir / "report.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
