"""Prepare the fixed 64km same-world review; GPU inference is explicit."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.td_source import generate_product, write_preview


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="CPU macro plan only (default)")
    mode.add_argument("--generate", action="store_true", help="Explicit fresh local CUDA TD inference")
    args = parser.parse_args()
    plan = write_preview(args.output)
    result = generate_product(args.output, plan) if args.generate else plan
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
