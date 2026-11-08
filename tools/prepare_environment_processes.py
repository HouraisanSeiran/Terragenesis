"""Prepare or resume a finite environment process product from saved inputs."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline import environment_product as product_api


def _declaration(value):
    if value is None:
        return {}
    text = value if value.lstrip().startswith("{") else Path(value).read_text(encoding="utf-8")
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("declaration must be a JSON object")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--store", type=Path)
    source.add_argument("--resume", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--row", type=int)
    parser.add_argument("--col", type=int)
    parser.add_argument("--size", type=int, default=33)
    parser.add_argument("--initial", help="initial declaration JSON file or object")
    parser.add_argument("--mode", choices=("explicit", "explicit-v2", "seasonal", "seasonal-v2"))
    parser.add_argument("--climate-driver", type=Path)
    parser.add_argument("--climate-driver-sha256")
    parser.add_argument("--seasonal-parameters", help="seasonal configuration JSON file or object")
    parser.add_argument("--forcing", help="forcing declaration JSON file or object")
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--dt-s", type=float, default=3600.)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.steps < 1:
        parser.error("--steps must be positive")
    if args.resume and not args.expected_sha256:
        parser.error("--resume requires --expected-sha256")
    if args.resume and (args.initial is not None or args.row is not None or args.col is not None):
        parser.error("resume inherits its initial state and source window")
    if args.resume and (args.climate_driver is not None or args.seasonal_parameters is not None):
        parser.error("resume inherits its pinned climate driver and seasonal configuration")
    if args.climate_driver is not None and not args.climate_driver_sha256:
        parser.error("--climate-driver requires --climate-driver-sha256")
    if args.store and args.mode in ("seasonal", "seasonal-v2") and args.climate_driver is None:
        parser.error("seasonal initialization requires --climate-driver")
    if args.store and args.mode not in ("seasonal", "seasonal-v2") and (args.climate_driver is not None or args.seasonal_parameters is not None):
        parser.error("climate driver and seasonal configuration require --mode seasonal")
    if args.store and (args.row is None or args.col is None):
        parser.error("--store requires --row and --col")
    output = args.output.resolve()
    if output.exists():
        parser.error("--output must be a new product file")
    if args.store and output.is_relative_to(args.store.resolve()):
        parser.error("--output must be outside the saved source store")
    try:
        forcing = _declaration(args.forcing)
        if args.resume:
            product = product_api.load_product(args.resume, expected_sha256=args.expected_sha256)
            actual_mode = "seasonal" if "seasonal" in product else "explicit"
            if product["algorithm"] == product_api.seasonal_api.ALGORITHM_V2:
                actual_mode = "seasonal-v2"
            if product["algorithm"] == product_api.storage.EXPLICIT_V2_ALGORITHM:
                actual_mode = "explicit-v2"
            if args.mode is not None and args.mode != actual_mode:
                parser.error("resume mode must match the saved product")
        else:
            context, sources = product_api.context_from_store(args.store, args.row, args.col, args.size)
            seasonal_options = {}
            if args.mode == "explicit-v2":
                seasonal_options["mode"] = "explicit-v2"
            if args.mode in ("seasonal", "seasonal-v2"):
                from terrain_pipeline.environment_regional_hydraulics import load_climate_driver
                seasonal_options = {"mode": args.mode,
                                    "climate_driver": load_climate_driver(args.climate_driver,
                                        expected_sha256=args.climate_driver_sha256),
                                    "seasonal_parameters": _declaration(args.seasonal_parameters)}
            product = product_api.initialize(context, sources, _declaration(args.initial), **seasonal_options)
        for _ in range(args.steps):
            product = product_api.advance(product, forcing, args.dt_s)
        digest = product_api.save_product(product, output)
        print(json.dumps({"output": str(output), "sha256": digest,
                          "product_identity": product_api.product_identity(product),
                          "time_s": product["time_s"], "step_index": product["step_index"]},
                         allow_nan=False, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
