"""Explicit CPU derivative of the user-approved old Coastal v1 saved TD."""
import argparse
from dataclasses import replace
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.coastal_terrain import DetailParameters
from terrain_pipeline.coastal_terrain import prepare_detail as prepare


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--strength", type=float, default=1.0)
    parser.add_argument("--memory-budget-bytes", type=int, default=1_000_000_000)
    args = parser.parse_args()
    manifest = prepare(args.baseline, args.output, params=replace(DetailParameters(), strength=args.strength), memory_budget_bytes=args.memory_budget_bytes)
    print(manifest["identity"])
