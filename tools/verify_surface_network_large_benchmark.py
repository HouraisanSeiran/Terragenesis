"""Static/one-step 1024+ benchmark with no long hydraulic integration."""

from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.surface_network_large_benchmark import (
    LargeBenchmarkBudget, load_terrain_diffusion_height, prepare_large_static,
    run_one_step_storage, validate_large_static)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("height", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--tile-cells", type=int, default=256)
    args = parser.parse_args()
    source = load_terrain_diffusion_height(args.height, expected_sha256=args.expected_sha256)
    budget = LargeBenchmarkBudget(tile_cells=args.tile_cells)
    static = prepare_large_static(source["height_m"], spacing_m=30., origin_m_xz=[0., 0.], budget=budget)
    audit = validate_large_static(static)
    dynamic = run_one_step_storage(static, forcing_m3_s=.001, duration_s=900.)
    args.output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(args.output / "static-arrays.npz", **static["arrays"])
    np.savez_compressed(args.output / "one-step-arrays.npz", **dynamic["arrays"])
    source_record = {key: value for key, value in source.items() if key != "height_m"}
    metadata = {"schema": "surface-network-large-benchmark-delivery-v1", "source": source_record,
        "static": static["metadata"], "static_audit": audit, "dynamic": dynamic["metadata"],
        "budget": vars(budget), "source_evolution": "raw Terrain Diffusion height only; no fill/cut", 
        "scope": "deterministic_D4_static_tile_and_one_step_storage_not_72h_hydrodynamic_solution",
        "files": {name: hashlib.sha256((args.output / name).read_bytes()).hexdigest() for name in ("static-arrays.npz", "one-step-arrays.npz")}}
    (args.output / "manifest.json").write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
