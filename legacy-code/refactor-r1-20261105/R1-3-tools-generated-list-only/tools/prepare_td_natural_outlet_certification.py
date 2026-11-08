"""Prepare the natural-outlet evidence gate without running a solver."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_natural_outlet_certification import (
    build_natural_outlet_certification,
    save_natural_outlet_certification,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geography-root", type=Path, default=Path("D:/geography"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_natural_outlet_certification(args.geography_root)
    save_natural_outlet_certification(report, args.output)
    print(json.dumps({"output": str(args.output.resolve()), "status": report["status"],
                      "gates": report["gates"], "failure_reasons": report["failure_reasons"],
                      "natural_outlet_verified": report["natural_outlet_verified"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
