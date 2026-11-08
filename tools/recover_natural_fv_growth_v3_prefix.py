"""Explicit frozen-v3 completed-prefix recovery; current runs use current checkpoints."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))


def recover(source, through_checkpoint, parameters_from, output, *, checkpoint_sha256, parameters_sha256):
    from tools.replay_natural_fv_growth_legacy import recover_legacy_prefix
    return recover_legacy_prefix(source,through_checkpoint,parameters_from,output,
        checkpoint_sha256=checkpoint_sha256,parameters_sha256=parameters_sha256)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-v3-replay',action='store_true')
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--through-checkpoint',type=Path,required=True)
    parser.add_argument('--checkpoint-sha256',required=True)
    parser.add_argument('--parameters-from',type=Path,required=True)
    parser.add_argument('--parameters-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.legacy_v3_replay:
        raise ValueError('historical prefix recovery requires explicit --legacy-v3-replay')
    print(json.dumps(recover(args.source,args.through_checkpoint,args.parameters_from,args.output,
        checkpoint_sha256=args.checkpoint_sha256,parameters_sha256=args.parameters_sha256),indent=2))
