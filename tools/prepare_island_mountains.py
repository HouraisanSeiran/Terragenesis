"""Prepare a CPU plan: exposed area strictly >25km2 by default. No TD/GPU.

Width filtering is disabled by default. Coast ramps protect blending, not
qualification. Fixed 1km cell-centre area is approximate near the threshold.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.ocean_islands import load_product
from terrain_pipeline.island_mountains import IslandMountainConfig, analyze_island_mountains, save_mountain_plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--islands', required=True)
    parser.add_argument('--expected-island-identity', required=True)
    parser.add_argument('--out', required=True)
    for name, default in asdict(IslandMountainConfig()).items():
        if name == 'analysis_bounds_m':
            parser.add_argument('--analysis-bounds-m', nargs=4, type=float, default=None,
                                help='Fixed source-aligned full-support group window; never a query window')
            continue
        help_text = {
            'min_area_km2':f'Strict lower bound: area must be greater, not equal (default:{default:g})',
            'min_usable_width_m':'Optional buffered-interior width filter;0 disables it (default)',
            'coast_buffer_m':'Zero-weight blend buffer; not an area-only qualification requirement',
            'max_analysis_cells':'Fixed-grid cell budget; reject larger domains without silently coarsening',
        }.get(name)
        parser.add_argument('--'+name.replace('_','-'), type=type(default), default=default, help=help_text)
    args = parser.parse_args(argv)
    if Path(args.out).exists():
        raise FileExistsError(args.out)
    product = load_product(args.islands, args.expected_island_identity)
    config = IslandMountainConfig(**{k:getattr(args,k) for k in asdict(IslandMountainConfig())})
    plan = analyze_island_mountains(product, config)
    save_mountain_plan(plan,args.out)
    print(json.dumps(dict(identity=plan.identity, empty=plan.empty, manifest=plan.manifest),indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
