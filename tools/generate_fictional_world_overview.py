"""CLI: build one finite fictional-world overview (three continents + islands).

```
python tools/generate_fictional_world_overview.py \\
    --seed 20261020 --extent-km 1600 --grid-size 1024 \\
    --output-dir .scratch/fictional-world-overview/run-01
```

Semantics that must not drift:

* the defaults are the user's declared request (1600 km frame, seed 20261020,
  1024 x 1024 cell-centre samples, i.e. 1562.5 m node spacing);
* the same arguments reproduce byte-identical arrays -- every random decision
  comes from ``sha256`` sub-seeds of ``--seed`` and absolute metre coordinates;
* the output directory is **created, never overwritten**: an existing directory or
  an existing file is an error with a non-zero exit code and nothing written;
* a refused layout (``LayoutRefused``) is a legal, reported outcome: the reasons
  are printed and the exit code is 4, never papered over by relaxing a gate;
* exit code 2 is invalid input, 3 is an IO/contract failure, 0 is success.

Every array produced here is a low-resolution *overview* product.  It is not the
30 m Terrain Diffusion grid, carries no hydraulics, and must not be fed to the
TD river-network interfaces or used in place of the default 30 m terrain.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.fictional_world_overview import (  # noqa: E402
    DEFAULT_EXTENT_KM,
    DEFAULT_GRID_SIZE,
    DEFAULT_WORLD_SEED,
    MIN_STRAIT_KM,
    LayoutRefused,
    OutputExistsError,
    OverviewError,
    OverviewRequest,
    generate_overview,
    write_overview,
)

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_FAILURE = 3
EXIT_REFUSED = 4


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate one finite fictional-world overview "
                    "(three continents, islands, mountains, diagnostic rivers).")
    parser.add_argument("--seed", type=int, default=DEFAULT_WORLD_SEED,
                        help="world seed (default %(default)s); sub-seeds are sha256-derived")
    parser.add_argument("--extent-km", type=float, default=DEFAULT_EXTENT_KM,
                        help="square frame side in kilometres (default %(default)s)")
    parser.add_argument("--grid-size", type=int, default=DEFAULT_GRID_SIZE,
                        help="cell-centre samples per side (default %(default)s)")
    parser.add_argument("--min-strait-km", type=float, default=MIN_STRAIT_KM,
                        help="minimum open water between landmasses (default %(default)s)")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="destination directory; must not exist yet")
    parser.add_argument("--no-png", action="store_true",
                        help="skip the review image (the npz and JSON are still written)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        request = OverviewRequest(seed=args.seed, extent_km=args.extent_km,
                                  grid_size=args.grid_size,
                                  min_strait_km=args.min_strait_km)
    except OverviewError as error:
        print("invalid request: %s" % error, file=sys.stderr)
        return EXIT_INPUT

    if args.output_dir.exists():
        print("refusing to overwrite existing path: %s" % args.output_dir, file=sys.stderr)
        return EXIT_INPUT

    try:
        result = generate_overview(request)
    except LayoutRefused as refusal:
        print("layout refused: %s" % refusal, file=sys.stderr)
        for record in refusal.attempts:
            print("  attempt %d: %s" % (record["attempt"], record["reason"]), file=sys.stderr)
        return EXIT_REFUSED
    except OverviewError as error:
        print("generation failed: %s" % error, file=sys.stderr)
        return EXIT_FAILURE

    try:
        written = write_overview(result, args.output_dir, render=not args.no_png)
    except OutputExistsError as error:
        print(str(error), file=sys.stderr)
        return EXIT_INPUT
    except OSError as error:
        print("write failed: %s" % error, file=sys.stderr)
        return EXIT_FAILURE

    report = written["report"]
    summary = {
        "output_dir": written["output_dir"],
        "files": written["files"],
        "report": str(Path(written["output_dir"]) / "overview-report.json"),
        "node_spacing_m": report["grid_contract"]["node_spacing_m"],
        "continent_areas_km2": report["results"]["continent_areas_km2"],
        "continent_frame_fractions": report["results"]["continent_frame_fractions"],
        "island_count": report["results"]["island_count"],
        "land_fraction": report["results"]["land_fraction"],
        "river_count": report["checks"]["rivers"]["count"],
        "border_is_all_ocean": report["checks"]["border"]["border_is_all_ocean"],
        "receiver_graph_is_acyclic": report["checks"]["receiver_graph"]["receiver_graph_is_acyclic"],
        "elevation_range_m": [report["checks"]["elevation"]["elevation_min_m"],
                              report["checks"]["elevation"]["elevation_max_m"]],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
