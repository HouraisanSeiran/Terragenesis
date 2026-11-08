"""Generate one continuous v4 coastal window for offline watershed screening."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from diffusion.backend import TerrainDiffusionBackend
from diffusion.config import GenerationConfig


OLD = ROOT / ("verification/height-budget-v4/run-20260929T095325080740Z/"
              "holdout-seed20261002/candidate-1/seed20261002-x-16000-z-13952.npz")
OUTPUT_ROOT = ROOT / "verification/river-feasibility"
SEED = 20261002
X, Z = -16000, -13952
SIZE = 1025


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    config = GenerationConfig.for_profile(
        "geographic_v4", v4_land_base_factor=.04,
        v4_mountain_relief_factor=.18, v4_ocean_depth_m=40.)
    identity = config.identity()[0]
    with np.load(OLD, allow_pickle=False) as old:
        previous = old["elevation"].copy()
        old_metadata = json.loads(str(old["metadata"].item()))
        old_config = json.loads(str(old["generation_config"].item()))
    if (old_metadata["identity"] != identity or
            old_config != json.loads(json.dumps(config.record())) or
            old_metadata["seed"] != str(SEED) or old_metadata["native_origin"] != [X, Z]):
        raise ValueError("Prior window does not match the authorized generation identity")
    output = OUTPUT_ROOT / datetime.now(timezone.utc).strftime("extended-%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True)
    backend = TerrainDiffusionBackend(config)
    try:
        elevation, climate, metadata = backend.generate(SEED, X, Z, SIZE)
    finally:
        backend.close()
    if (elevation.shape != (SIZE, SIZE) or climate.shape[-2:] != elevation.shape or
            elevation.dtype != np.float32 or not np.isfinite(elevation).all() or
            metadata["identity"] != identity or metadata["native_resolution_m"] != 30):
        raise ValueError("Extended generation output failed validation")
    raw = output / f"seed{SEED}-x{X}-z{Z}-size{SIZE}.npz"
    np.savez_compressed(raw, elevation=elevation, climate=climate,
                        metadata=json.dumps(metadata),
                        generation_config=json.dumps(config.record()))
    overlap = np.abs(elevation[:513, :513].astype(np.float64) - previous.astype(np.float64))
    report = {"purpose": "one continuous raw v4 1025-square coastal extension",
              "raw_npz": raw.name, "raw_sha256": sha256(raw),
              "prior_npz": str(OLD.relative_to(ROOT)), "prior_sha256": sha256(OLD),
              "seed": SEED, "native_origin": [X, Z], "shape": list(elevation.shape),
              "native_resolution_m": 30, "generation_identity": identity,
              "generation_config": config.record(), "backend_metadata": metadata,
              "overlap_cells": previous.size,
              "overlap_max_abs_m": float(overlap.max()),
              "overlap_mean_abs_m": float(overlap.mean()),
              "overlap_equal_cells": int(np.count_nonzero(overlap == 0)),
              "note": "Raw source only; no processed terrain or publication."}
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    print(output, flush=True)


if __name__ == "__main__":
    main()
