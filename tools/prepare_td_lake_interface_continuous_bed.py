"""Prepare the lake-interface continuous-bed candidate without solving."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_lake_interface_continuous_bed import (
    build_lake_interface_continuous_bed, save_lake_interface_continuous_bed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--patches", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    geometry = json.loads((args.geometry / "review.json").read_text(encoding="utf-8"))
    geometry["schema"] = "td-watershed-geometry-preparation-v1"
    geometry["identity_sha256"] = geometry.get("identity_sha256") or json.loads(
        (args.geometry / "index.json").read_text(encoding="utf-8"))["review"]["identity_sha256"]
    patches = json.loads((args.patches / "patches.json").read_text(encoding="utf-8"))
    if patches.get("schema") == "td-watershed-interface-patch-preparation-v2":
        patches = json.loads((args.patches / "patches.json").read_text(encoding="utf-8"))
    result = build_lake_interface_continuous_bed(geometry, patches)
    save_lake_interface_continuous_bed(result, args.output / "continuous-bed.json")
    print(json.dumps({"output": str((args.output / "continuous-bed.json").resolve()),
                      "status": result["status"], "summary": result["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
