import argparse
import json
from pathlib import Path

from terrain_pipeline.surface_rivers.metric_river_release import assemble
from terrain_pipeline.mountain_source_adapter import publish_bytes

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "verification/td-river-milestones/td1024-20261008-01/manifest.json"
OUTPUT = ROOT / "web-preview/data/river-product-v2/product-td-m7.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--comparison", type=Path)
    parser.add_argument("--acceptance", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = assemble(args.source, args.output, args.comparison, acceptance=args.acceptance)
    pin = {"path": args.output.name, "sha256": result["sha256"], "identity_sha256": result["identity_sha256"]}
    publish_bytes(args.output.parent / "manifest.json", (json.dumps({"schema": "terragenesis-river-release-pin-v2", "product": pin}, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
