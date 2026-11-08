"""Cold-read a native-coordinate cell from a river geometry product."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.surface_rivers.large_world_river_geometry import load, query


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("product")
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--x", type=int, required=True)
    parser.add_argument("--z", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(query(load(args.product, args.sha256), args.x, args.z), indent=2))


if __name__ == "__main__":
    main()
