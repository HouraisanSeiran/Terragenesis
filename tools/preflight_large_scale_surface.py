"""Report safe run gates for 1024² and larger surface-network tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.large_scale_resource_preflight import report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, action="append", default=[])
    parser.add_argument("--max-mib", type=int, default=512)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sizes = args.size or [1024, 2048, 4096]
    result = {str(size): report(size, max_mib=args.max_mib) for size in sizes}
    encoded = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
