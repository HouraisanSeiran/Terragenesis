"""CLI validator for deterministic 1024+ static surface-network routing."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrain_pipeline.large_scale_surface_network import (
    LargeScaleBudget, build_large_scale_network, synthetic_terrain_diffusion_height,
    validate_large_scale_network)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--tile-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--max-resident-mib", type=int, default=512)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    budget = LargeScaleBudget(args.tile_size, args.size * args.size,
                              args.max_resident_mib * 1024 * 1024)
    height = synthetic_terrain_diffusion_height(args.size, args.seed)
    first = build_large_scale_network(height, budget=budget)
    second = build_large_scale_network(height, budget=budget)
    report = validate_large_scale_network(first, budget=budget)
    if first["metadata"]["identity_sha256"] != second["metadata"]["identity_sha256"]:
        raise RuntimeError("determinism check failed")
    report.update({"schema": first["schema"], "size": args.size, "seed": args.seed,
                   "deterministic": True, "metadata": first["metadata"]})
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
