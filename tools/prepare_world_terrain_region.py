"""Plan or prepare one persistent, connected finite-world region."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_source import make_spec, open_region_registry as open_registry, plan_region_store as plan, prepare_region_store as prepare
from terrain_pipeline.td_source import compose_window, inspect_window_support
from terrain_pipeline.surface_hydraulics import form_connected_region
from tools.prepare_world_terrain_water import render


def generate_page(request, support, args):
    from diffusion.world_demand_backend import (plan_source_pages, run_source_page, SOURCE_FAMILY,
                                                PAGE_SIDE)
    from terrain_pipeline.surface_rivers.native_30m_source import BORDER_BAND_CELLS
    import numpy as np

    if args.source_family != SOURCE_FAMILY:
        raise ValueError("generated pages require source family " + SOURCE_FAMILY)
    mask = support["missing_mask"].copy()
    hx, hz = support["support_origin_native_xz"]
    origins = set()
    def select(origin):
        x, z = origin
        left = max(0, x + BORDER_BAND_CELLS - hx)
        top = max(0, z + BORDER_BAND_CELLS - hz)
        right = min(mask.shape[1], x + PAGE_SIDE - BORDER_BAND_CELLS - hx)
        bottom = min(mask.shape[0], z + PAGE_SIDE - BORDER_BAND_CELLS - hz)
        if left < right and top < bottom and mask[top:bottom, left:right].any():
            origins.add(tuple(origin))
            mask[top:bottom, left:right] = False

    for origin in plan_source_pages(request["origin_native_xz"], request["shape_zx"]):
        select(origin)
    for row in range(mask.shape[0]):
        edges = np.diff(np.r_[False, mask[row], False].astype(np.int8))
        for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
            for origin in plan_source_pages([hx + int(start), hz + row], [1, int(end - start)]):
                select(origin)
    records = []
    for origin in sorted(origins):
        result = run_source_page(list(origin), model_dir=args.model_dir,
                                 output_dir=Path(args.store) / "source-pages", world_seed=20261020)
        records.append({"path": result["path"], "sha256": result["sha256"]})
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--pages-json")
    parser.add_argument("--source-family", required=True)
    parser.add_argument("--preset", choices=("lakes", "earth", "archipelago"), default="lakes")
    parser.add_argument("--water", type=float)
    parser.add_argument("--origin", nargs=2, type=int, required=True)
    parser.add_argument("--shape", nargs=2, type=int, required=True)
    parser.add_argument("--sigma-cells", type=float, default=6.)
    parser.add_argument("--runoff-m-per-year", type=float, required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--channel-threshold-m3-s", type=float, required=True)
    parser.add_argument("--min-lake-area-m2", type=float, default=10000.)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--generate-missing", action="store_true")
    parser.add_argument("--model-dir", default="models/terrain-diffusion-30m")
    parser.add_argument("--disk-store", action="store_true")
    parser.add_argument("--disk-budget-gib", type=float, default=8.)
    args = parser.parse_args(argv)
    spec = make_spec(args.preset, args.water)
    forcing = {"runoff_m_per_year": args.runoff_m_per_year, "duration_seconds": args.duration_seconds,
               "channel_threshold_m3_s": args.channel_threshold_m3_s, "min_lake_area_m2": args.min_lake_area_m2}
    if args.disk_store:
        from terrain_pipeline import td_source as disk
        registry = disk.open_disk_registry(args.store, spec, args.source_family, forcing, args.sigma_cells)
    else:
        registry = open_registry(args.store, spec, args.source_family, forcing, args.sigma_cells)
    supplied = json.loads(Path(args.pages_json).read_text(encoding="utf-8")) if args.pages_json else []
    pages_by_path = {p["path"]: p for p in registry["pages"]}
    for page in supplied:
        if page["path"] in pages_by_path and pages_by_path[page["path"]] != page:
            raise ValueError("registered source page pin changed")
        pages_by_path[page["path"]] = page
    pages = list(pages_by_path.values())

    def coverage(origin, shape, records):
        return inspect_window_support(spec, records, origin, shape, sigma_cells=args.sigma_cells,
                                      source_family=args.source_family)

    if args.disk_store:
        request = disk.plan_disk_region(registry, args.origin, args.shape)
        reports = []
        if request["hit"] is None:
            for tile_origin, tile_shape in disk.tiles(request["origin_native_xz"], request["shape_zx"]):
                support = coverage(tile_origin, tile_shape, pages)
                reports.append((tile_origin, tile_shape, support["missing_cells"]))
        if args.plan_only:
            print(json.dumps({"request": request, "tiles": [{"origin_native_xz": o, "shape_zx": s,
                "missing_cells": c} for o, s, c in reports]}, indent=2))
            return
        if args.generate_missing:
            for tile_origin, tile_shape, missing in reports:
                support = coverage(tile_origin, tile_shape, pages)
                if support["missing_cells"]:
                    for page in generate_page({"origin_native_xz": tile_origin, "shape_zx": tile_shape}, support, args):
                        pages_by_path[page["path"]] = page
                    pages = list(pages_by_path.values())
        from terrain_pipeline.drainage import solve_disk_region as solve_disk_region
        component = disk.prepare_disk_region(args.store, registry, request, pages, spec, compose=compose_window,
                                 solve=solve_disk_region, disk_budget_gib=args.disk_budget_gib)
        print(json.dumps({"component": component, "prepared_cells": registry["prepared_cells"],
                          "world_cells": registry["world_cells"], "cache_hit": request["hit"] is not None}, indent=2))
        return
    request = plan(registry, args.origin, args.shape, pages, coverage)
    report = {key: value for key, value in request.items() if key != "coverage"}
    support = request["coverage"]
    report["coverage"] = {key: value for key, value in support.items() if key != "missing_mask"}
    if "missing_mask" in support:
        import numpy as np
        mask = support["missing_mask"]
        spans = []
        for row in range(mask.shape[0]):
            edges = np.diff(np.r_[False, mask[row], False].astype(np.int8))
            for start, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
                spans.append([int(start + support["support_origin_native_xz"][0]),
                              int(row + support["support_origin_native_xz"][1]),
                              int(end + support["support_origin_native_xz"][0])])
        report["coverage"]["missing_row_spans_xzx_exclusive"] = spans
    if args.plan_only:
        print(json.dumps(report, indent=2))
        return
    if args.generate_missing and support["missing_cells"]:
        for page in generate_page(request, support, args):
            pages_by_path[page["path"]] = page
        pages = list(pages_by_path.values())
        request = plan(registry, args.origin, args.shape, pages, coverage)
    component = prepare(args.store, registry, request, pages, spec, compose=compose_window,
                        form=form_connected_region, render=render)
    print(json.dumps({"component": component, "prepared_cells": registry["prepared_cells"],
                      "source_support_cells": registry["source_support_cells"],
                      "world_cells": registry["world_cells"], "cache_hit": request["hit"] is not None}, indent=2))


if __name__ == "__main__":
    main()
