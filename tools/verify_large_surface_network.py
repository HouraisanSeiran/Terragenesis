"""Create and verify independent large static network evidence."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrain_pipeline.large_surface_network_validation import (
    build_large_surface_network,
    manifest_json,
    preflight_large_network,
    validate_large_surface_network,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--tile-cells", type=int, default=128)
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if args.preflight_only:
        result = {"verified": True, "mode": "preflight_only",
                  "resource": preflight_large_network(args.size, args.tile_cells)}
        (args.output / "verification.json").write_text(json.dumps(result, ensure_ascii=False,
                                                                    indent=2) + "\n",
                                                         encoding="utf-8", newline="\n")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    network = build_large_surface_network(args.size, args.seed, args.tile_cells)
    result = validate_large_surface_network(network)
    (args.output / "manifest.json").write_text(manifest_json(network), encoding="utf-8", newline="\n")
    (args.output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                                       encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
