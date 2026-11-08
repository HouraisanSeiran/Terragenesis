"""Prepare the explicitly selected saved-TD coastal derivative on CPU."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.coastal_terrain import prepare_terrain_bed as prepare

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for option in ("raw", "macro", "metadata", "output"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--plate")
    parser.add_argument("--plate-identity")
    parser.add_argument("--memory-budget-bytes", type=int, default=850_000_000)
    args = parser.parse_args()
    manifest, _ = prepare(args.raw, args.macro, args.metadata, args.output, plate_path=args.plate, plate_identity=args.plate_identity, memory_budget_bytes=args.memory_budget_bytes)
    print(manifest["macro_identity"])
