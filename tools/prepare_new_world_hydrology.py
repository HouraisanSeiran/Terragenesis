"""Prepare an immutable finite hydrology product."""
import argparse
import json
from pathlib import Path
from terrain_pipeline.new_world_hydrology import prepare, route_event


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('terrain')
    parser.add_argument('output')
    parser.add_argument('--expected-terrain-identity', required=True)
    parser.add_argument('--event-depth-m', type=float)
    parser.add_argument('--event-duration-s', type=float)
    parser.add_argument('--event-source')
    parser.add_argument('--event-output')
    args = parser.parse_args()
    event_args = (args.event_depth_m, args.event_duration_s, args.event_source, args.event_output)
    if any(v is not None for v in event_args) and any(v is None for v in event_args):
        parser.error('all event arguments are required together')
    if args.event_output and Path(args.event_output).exists():
        parser.error('event output already exists')
    manifest, _ = prepare(args.terrain, args.output, expected_terrain_identity=args.expected_terrain_identity)
    print(manifest['identity'])
    if args.event_output:
        event = route_event((manifest, _), args.event_depth_m, args.event_duration_s, input_source=args.event_source)
        event['declared_uniform_depth_m'] = args.event_depth_m
        Path(args.event_output).write_text(json.dumps(event, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
