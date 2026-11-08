"""Explicit prepare/advance/query of completed regional hydraulic products."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline import environment_regional_hydraulics as api
from terrain_pipeline import environment_product as process


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--process", required=True)
    prepare.add_argument("--sha256", required=True)
    prepare.add_argument("--source-width", type=int, required=True)
    prepare.add_argument("--handoff-time-start", type=float)
    prepare.add_argument("--output", required=True)
    advance = sub.add_parser("advance")
    advance.add_argument("--checkpoint", required=True)
    advance.add_argument("--sha256", required=True)
    advance.add_argument("--dt-s", type=float, required=True)
    advance.add_argument("--output", required=True)
    query = sub.add_parser("query")
    query.add_argument("--checkpoint", required=True)
    query.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        product = process.load_product(args.process, expected_sha256=args.sha256)
        rows, cols = np.indices(product["context"]["height_m"].shape)
        row, col, _ = product["sources"]["window_row_col_size"]
        ids = ((rows + row) * args.source_width + cols + col).astype(np.int64)
        if args.handoff_time_start is None:
            regions = api.prepare_from_context(product["context"], product["sources"], ids)
        else:
            regions = api.prepare_process_handoff(product, ids, time_start_s=args.handoff_time_start)
    else:
        regions = api.load_checkpoint(args.checkpoint, expected_sha256=args.sha256)
        if args.command == "query":
            print(json.dumps(api.query(regions), sort_keys=True, allow_nan=False))
            return
        regions = api.advance(regions, args.dt_s)
    digest = api.save_checkpoint(args.output, regions)
    print(json.dumps(dict(path=str(Path(args.output).resolve()), sha256=digest)))


if __name__ == "__main__":
    main()
