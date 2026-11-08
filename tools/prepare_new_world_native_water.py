import argparse
import json
from terrain_pipeline import new_world_native_water as water


def main():
    parser = argparse.ArgumentParser(description='Route a finite declared land runoff event over an authenticated native planner')
    parser.add_argument('planner')
    parser.add_argument('output')
    parser.add_argument('--expected-terrain-identity', required=True)
    parser.add_argument('--expected-planner-identity', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--runoff-depth-m', required=True, type=float)
    parser.add_argument('--duration-s', required=True, type=float)
    parser.add_argument('--partitions', type=int, choices=(1, 2, 4), default=1)
    parser.add_argument('--previous')
    parser.add_argument('--generate', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--stop-after', choices=('send', 'receive'))
    args = parser.parse_args()
    if (args.resume or args.stop_after) and not args.generate:
        parser.error('--resume and --stop-after require --generate')
    common = dict(expected_terrain_identity=args.expected_terrain_identity, expected_planner_identity=args.expected_planner_identity)
    if args.generate:
        m, _ = water.prepare(args.planner, args.output, **common, source=args.source, runoff_depth_m=args.runoff_depth_m, duration_s=args.duration_s, partitions=args.partitions, previous=args.previous, resume=args.resume, stop_after=args.stop_after)
        print(json.dumps(m, indent=2))
    else:
        _, budget = water.preflight(args.planner, args.output, **common)
        print(json.dumps(budget, indent=2))


if __name__ == '__main__':
    main()
