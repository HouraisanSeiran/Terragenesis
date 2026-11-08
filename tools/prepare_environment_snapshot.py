"""Export a completed seasonal-v2 process to the existing same-anchor world product."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.soil_water import prepare_snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--arrays", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        snapshot = prepare_snapshot(args.product, expected_sha256=args.expected_sha256,
                                    arrays_path=args.arrays, record_path=args.record)
        print(json.dumps({"arrays": str(args.arrays.resolve()), "record": str(args.record.resolve()),
                          "cells": snapshot.cells, "world_identity": snapshot.world_identity,
                          "source_identity": snapshot.source_identity, "time_identity": snapshot.time_identity}))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
