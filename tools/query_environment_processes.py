"""Read one cell of a completed environment process product without advancing it."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.environment_product import load_product, query_product


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--row", type=int, required=True)
    parser.add_argument("--col", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        product = load_product(args.product, expected_sha256=args.expected_sha256)
        result = query_product(product, args.row, args.col)
        result["read_only"] = True
        print(json.dumps(result, allow_nan=False, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
