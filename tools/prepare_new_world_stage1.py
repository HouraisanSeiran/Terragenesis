"""Preflight or publish an immutable native stage-1 product."""
import argparse
import json
from terrain_pipeline import new_world_stage1 as stage1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('terrain')
    parser.add_argument('output')
    parser.add_argument('--expected-terrain-identity', required=True)
    parser.add_argument('--block-size', type=int, default=128)
    parser.add_argument('--generate', action='store_true')
    parser.add_argument('--checkpointed', action='store_true', help='run monitored resumable phase workers')
    parser.add_argument('--resume', action='store_true', help='resume an existing checkpointed pending directory')
    parser.add_argument('--stop-after', choices=('source', 'graph', 'flood', 'derived', 'verified'))
    args = parser.parse_args()
    if (args.resume or args.stop_after) and not args.checkpointed:
        parser.error('--resume and --stop-after require --checkpointed')
    budget = stage1.preflight(args.terrain, args.output, args.expected_terrain_identity, block_size=args.block_size)
    if args.generate:
        if args.checkpointed:
            from terrain_pipeline import new_world_stage1_checkpoint as checkpoint
            product = checkpoint.prepare(args.terrain, args.output, expected_terrain_identity=args.expected_terrain_identity,
                block_size=args.block_size, resume=args.resume, stop_after=args.stop_after)
        else:
            product = stage1.prepare(args.terrain, args.output, expected_terrain_identity=args.expected_terrain_identity, block_size=args.block_size)
        print(json.dumps({'identity': product[0]['identity'] if product else None, 'status': 'complete' if product else 'checkpointed', 'budget': budget}, indent=2))
    else:
        print(json.dumps({'status': 'dry-run', 'budget': budget}, indent=2))


if __name__ == '__main__':
    main()
