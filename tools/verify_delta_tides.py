"""Validate real physical tidal periods independently of the annual river run."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[name] = '1'

from terrain_pipeline.delta_tidal_validation import verify_saved_run


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summary = verify_saved_run(args.run, args.output)
    print(json.dumps({key:summary[key] for key in ('checks','tidal','creek_connectivity')}, indent=2))
