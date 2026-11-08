"""CLI: generate on-demand river domain products for explicit world points.

Contract 2.2 of `.scratch/river-infinite-world/pipeline-spec.md`.

```
python tools/generate_river_domains.py \\
    --seed 20261020 \\
    --point 1200000 400000 \\
    --output-dir out \\
    --spacing-m 10000 \\
    --report report.json
```

Semantics that must not drift:

* no `--output-dir` is a **dry run**: the products are built and hashed in
  memory, only `--report` is written;
* a refusal is a **legal result**, not an error: it is recorded verbatim in the
  report and the exit code stays 0 (`accepted + refused == requested`);
* exit code is non-zero only for invalid input (no point at all, a malformed
  `--point` / `--points-file`, a negative/invalid `--spacing-m`) or an IO/contract
  failure (a destination that already exists, a product identity mismatch);
* the report is written with the `x` mode (create, never overwrite), the same
  discipline as `tools/audit_river_on_demand_consistency.py --output`.

The CLI adds nothing to the products: it parses points, calls
`resolve_domain_products`, reloads every written product and checks its identity,
and dumps the batch index plus a CLI envelope.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.hydrology_planning import PlanningConfig  # noqa: E402
from terrain_pipeline.surface_rivers.metric_domain_pipeline import (  # noqa: E402
    INDEX_SCHEMA,
    SCHEMA,
    compute_identity,
    load_domain_product,
    resolve_domain_products,
)

CLI_SCHEMA = "river-domain-cli-report-v1"

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_FAILURE = 3


class InputError(ValueError):
    """Invalid CLI input: a non-zero exit with a verbatim message."""


COORDINATE = re.compile(r"^\s*([-+0-9.eE]+)\s*[,;\s]\s*([-+0-9.eE]+)\s*$")


def parse_point(values):
    """Two world coordinates from either `--point X Z` tokens or one string."""
    if len(values) == 1:
        match = COORDINATE.match(values[0])
        if not match:
            raise InputError("--point expects two numbers "
                             "(`--point X Z` or `--point \"X,Z\"`); got %r" % values[0])
        tokens = match.groups()
    elif len(values) == 2:
        tokens = values
    else:
        raise InputError("--point expects exactly two numbers; got %d: %r" % (len(values), values))
    try:
        return float(tokens[0]), float(tokens[1])
    except ValueError:
        raise InputError("--point values are not numbers: %r" % (values,))


def read_points_file(path):
    """World points from a text file: one `x,z` per line, blank lines and comments skipped.

    The contract says `x,z` two columns, so CSV is the documented form; whitespace
    or a semicolon separator is accepted too, because a hand-written file is the
    most likely consumer. A malformed line is an input error, never skipped --
    silently dropping a requested point is exactly how a refusal would get lost.
    """
    source = Path(path)
    if not source.is_file():
        raise InputError("--points-file does not exist: %s" % source)
    points = []
    with source.open("r", encoding="utf-8") as stream:
        for number, line in enumerate(stream, start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            match = COORDINATE.match(text)
            if not match:
                raise InputError("%s line %d is not an `x,z` pair: %r" % (source, number, line.rstrip()))
            points.append((float(match.group(1)), float(match.group(2))))
    if not points:
        raise InputError("--points-file holds no point: %s" % source)
    return points


def collect_points(args):
    points = []
    for values in args.point or []:
        points.append(parse_point(values))
    if args.points_file:
        points.extend(read_points_file(args.points_file))
    if not points:
        raise InputError("no point given: use --point X Z (repeatable) and/or --points-file")
    return points


def build_report(batch, args, points):
    """The CLI envelope: the batch index plus what this invocation did."""
    record = dict(batch.index_record())
    record["schema"] = CLI_SCHEMA
    record["product_schema"] = SCHEMA
    record["index_schema"] = INDEX_SCHEMA
    record["dry_run"] = batch.output_dir is None
    record["output_dir"] = batch.output_dir
    record["report"] = args.report
    record["points_file"] = args.points_file
    record["seed"] = int(args.seed)
    record["spacing_m"] = float(batch.spacing_m)
    record["points"] = [{"x_m": float(x_m), "z_m": float(z_m)} for x_m, z_m in points]
    record["reloaded_products"] = []
    return record


def run(argv=None, *, stdout=None):
    """Run the CLI; returns the exit code (0 unless input/IO/contract failure)."""
    stream = stdout if stdout is not None else sys.stdout
    parser = argparse.ArgumentParser(
        description="Generate on-demand, window-independent river domain products",
        epilog="a refusal is a legal result (exit 0); only invalid input or IO/contract "
               "failure is a non-zero exit")
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--point", nargs="+", action="append", metavar="X",
                        help="world coordinates, repeatable (`--point 1200000 400000`)")
    parser.add_argument("--points-file", help="text file of `x,z` lines")
    parser.add_argument("--output-dir", help="product directory; omitted = dry run")
    parser.add_argument("--spacing-m", type=float, default=None,
                        help="resample spacing of the derived views; must divide the "
                             "planning node spacing (macro_span_m / samples_per_span) "
                             "by a positive integer, so equal to or finer than it")
    parser.add_argument("--report", required=True, help="JSON report path; refuses to overwrite")
    args = parser.parse_args(argv)

    try:
        points = collect_points(args)
        if args.spacing_m is not None and not args.spacing_m > 0:
            raise InputError("--spacing-m must be positive; got %r" % args.spacing_m)
        config = PlanningConfig()
        config.validate()
        report_path = Path(args.report)
        if report_path.exists():
            raise FileExistsError("--report refuses to overwrite an existing file: %s" % report_path)
        batch = resolve_domain_products(args.seed, points, config=config,
                                        spacing_m=args.spacing_m,
                                        output_dir=args.output_dir)
        record = build_report(batch, args, points)
        for key in batch.outlet_keys:
            product = batch.domains[key]
            if product.product_path is None:
                continue
            reloaded = load_domain_product(product.product_path,
                                           expected_identity_sha256=product.identity_sha256)
            record["reloaded_products"].append({
                "outlet_x_m": reloaded.outlet_x_m,
                "outlet_z_m": reloaded.outlet_z_m,
                "product": reloaded.product_name,
                "identity_sha256": product.identity_sha256,
                "reloaded_identity_sha256": compute_identity(reloaded.arrays()),
            })
    except (InputError, ValueError, FileExistsError, OSError) as error:
        print("FAILED: %s" % error, file=stream)
        return EXIT_INPUT if isinstance(error, (InputError, ValueError)) else EXIT_FAILURE

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)

    print("OK written:", args.report, file=stream)
    print("seed:", record["seed"], " config_id:", record["config_id"], file=stream)
    print("requested points:", record["requested_points"],
          " accepted:", record["accepted_points"],
          " refused:", record["refused_points"],
          " domains:", record["domain_count"], file=stream)
    print("reasons:", json.dumps(record["reason_tally"], ensure_ascii=False), file=stream)
    print("product set sha256:", record["product_set_sha256"], file=stream)
    print("dry run:", record["dry_run"], " output dir:", record["output_dir"], file=stream)
    print("reloaded products:", len(record["reloaded_products"]),
          " identity mismatches:",
          sum(1 for entry in record["reloaded_products"]
              if entry["reloaded_identity_sha256"] != entry["identity_sha256"]), file=stream)
    for entry in record["refusals"]:
        print("refused: x=%g z=%g reason=%s resolved=%s"
              % (entry["x_m"], entry["z_m"], entry["reason"], entry["resolved"]), file=stream)
    for entry in record["domains"]:
        print("domain: outlet=(%g, %g) kind=%s cells=%d product=%s identity=%s"
              % (entry["outlet_x_m"], entry["outlet_z_m"], entry["kind"],
                 entry["territory_cells"], entry["product"], entry["identity_sha256"]), file=stream)
    print("exit code:", EXIT_OK, "(a refusal is a legal result, not an error)", file=stream)
    return EXIT_OK


def main(argv=None):
    return run(argv)


if __name__ == "__main__":
    sys.exit(run())
