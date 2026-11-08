"""Explicit entry point for the finite complete engineered delta."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[name] = '1'

from terrain_pipeline.complete_delta import DEFAULT_SCENE, run, resume


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scene',type=Path,default=DEFAULT_SCENE)
    parser.add_argument('--forcing',type=Path)
    parser.add_argument('--resume',type=Path)
    args = parser.parse_args()
    forcing = json.loads(args.forcing.read_text(encoding='utf-8')) if args.forcing else None
    if args.resume and forcing is None:
        parser.error('--resume requires --forcing containing only additional monthly inputs')
    result = resume(args.resume,args.output,forcing) if args.resume else run(args.output,args.scene,forcing)
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
