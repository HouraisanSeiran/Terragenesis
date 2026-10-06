"""Run the large tiled surface river benchmark and write its JSON proof."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.large_scale_surface_tiles import LargeScaleSpec, run_benchmark, write_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--tile-size", type=int, default=128)
    parser.add_argument("--max-windows", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_benchmark(LargeScaleSpec(rows=args.size, cols=args.size, tile_size=args.tile_size), args.max_windows)
    if report["peak_windows"] > args.max_windows or not report["conservation_passed"]:
        raise SystemExit("large scale acceptance failed")
    write_report(args.output, report)
    print(f"passed: {args.size}x{args.size}, cross_tile_edges={report['cross_tile_edges']}, "
          f"outlets={report['outlet_count']}, residual={report['propagation']['residual_m3']:.6g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
