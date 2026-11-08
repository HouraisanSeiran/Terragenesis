"""Prepare the bounded M8 river product from saved evidence without solving."""
import argparse
import json
from pathlib import Path

from terrain_pipeline.surface_rivers.metric_river_release import ROOT, assemble_results
from terrain_pipeline.mountain_source_adapter import publish_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=ROOT / "web-preview/data/river-product-v1/product-td-m7.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    pin = assemble_results(args.base, args.output,
        geometry_report=ROOT / "verification/td-river-geometry/m5-20261008-06/acceptance.json",
        sediment_report=ROOT / "verification/td-river-sediment/m6-20261008-03/acceptance.json",
        valley_report=ROOT / "verification/td-shaped-valley/td1024-20261010-01/manifest.json")
    local_pin = {"path": args.output.name, "sha256": pin["sha256"], "identity_sha256": pin["identity_sha256"]}
    manifest = {"schema": "terragenesis-river-release-pin-v2", "product": local_pin}
    publish_bytes(args.output.parent / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    print(json.dumps(pin))


if __name__ == "__main__":
    main()
