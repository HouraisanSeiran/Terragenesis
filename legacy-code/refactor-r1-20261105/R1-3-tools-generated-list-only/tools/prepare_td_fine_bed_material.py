"""Prepare task08 from the two immutable task06/07 packages."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_fine_bed_material import build_fine_bed_material, save_fine_bed_material


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--patches", type=Path, required=True)
    parser.add_argument("--corridors", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    geometry = args.geometry
    patch_dir = args.patches
    paths = json.loads((geometry / "paths.json").read_text(encoding="utf-8"))
    sections = json.loads((geometry / "sections.json").read_text(encoding="utf-8"))
    patches = json.loads((patch_dir / "patches.json").read_text(encoding="utf-8"))
    if patches.get("schema") == "td-watershed-interface-patch-preparation-v2":
        core_path = patch_dir / "patches.json"
        patches = json.loads(core_path.read_text(encoding="utf-8"))
    corridors = None
    if args.corridors:
        corridors = json.loads((args.corridors / "corridors.json").read_text(encoding="utf-8"))
    record = build_fine_bed_material(paths, sections, patches, corridors=corridors)
    args.output.mkdir(parents=True, exist_ok=True)
    save_fine_bed_material(record, args.output / "fine-bed-material.json")
    (args.output / "review.json").write_text(json.dumps({"schema": "td-fine-bed-material-review-v1", "summary": record["summary"], "identity_sha256": record["identity_sha256"], "flags": {name: record[name] for name in ("hydraulic_solved", "natural_outlet_certified", "publish_ready", "bed_changed", "water_surface_meshed", "material_ledger_certified")}}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
