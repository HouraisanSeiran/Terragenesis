"""Opt-in frozen-v3 MPM diagnostic; never runs the current algorithm implicitly."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--legacy-v3-replay',action='store_true')
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--checkpoint-sha256',required=True)
    parser.add_argument('--parameters-from',type=Path,required=True)
    parser.add_argument('--parameters-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--interval-s',type=float,default=.0625)
    parser.add_argument('--duration-s',type=float,default=.125)
    parser.add_argument('--captured-input',type=Path)
    parser.add_argument('--captured-input-sha256')
    args=parser.parse_args()
    if not args.legacy_v3_replay:
        raise ValueError('historical MPM diagnostic requires explicit --legacy-v3-replay')
    from tools.replay_natural_fv_growth_legacy import replay_legacy_diagnostic
    result=replay_legacy_diagnostic(checkpoint=args.checkpoint,checkpoint_sha256=args.checkpoint_sha256,
        parameters=args.parameters_from,parameters_sha256=args.parameters_sha256,output=args.output,
        interval_s=args.interval_s,duration_s=args.duration_s,captured_input=args.captured_input,
        captured_input_sha256=args.captured_input_sha256)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
