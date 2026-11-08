"""Explicit driver for one layout-conditioned native page.

Refuses to overwrite, refuses to run without the model directory, and runs exactly one
129x129 page. Every budget breach is written to a failure record and the process exits
non-zero -- a breach is a recorded failure, never a silent empty result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from diffusion.world_layout_backend import (  # noqa: E402
    BudgetExceeded,
    PAGE_SIDE_CELLS,
    describe_budgets,
    preflight,
    run_single_page,
)
from diffusion.world_layout_conditioning import (  # noqa: E402
    WorldLayoutGenerationConfig,
    select_nonempty_window,
)
from terrain_pipeline.world_water_layout import LayoutSpec, classify_points  # noqa: E402

EXIT_OK = 0
EXIT_INPUT = 2
EXIT_BUDGET = 3
EXIT_FAILURE = 4


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate ONE layout-conditioned native 30 m page.")
    parser.add_argument("--preset", default="lakes", choices=("earth", "archipelago", "lakes"))
    parser.add_argument("--water", type=float)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--frame-side-m", type=float, default=12_288_000.0)
    parser.add_argument("--frame-origin-m", type=float, nargs=2, default=(0.0, 0.0))
    parser.add_argument("--region-side-m", type=float)
    parser.add_argument("--origin-native-xz", type=int, nargs=2)
    parser.add_argument("--prefer", choices=("coast", "lake", "any"),
                        help="which feature the page must contain; selected by declared rule")
    parser.add_argument("--model-dir", default="models/terrain-diffusion-30m")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--gpu-monitor", choices=("pid", "allocator"), default="pid")
    parser.add_argument("--dtype", default="fp32", choices=("fp32", "fp16"))
    parser.add_argument("--dry-run", action="store_true",
                        help="select the window and print budgets; no inference")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.water is None:
        args.water = {"earth": 0.62, "archipelago": 0.8, "lakes": 0.12}[args.preset]
    if args.prefer is None:
        args.prefer = "lake" if args.preset == "lakes" else "coast"
    destination = Path(args.output_dir)
    if destination.exists():
        print(json.dumps({"error": "output directory exists: %s" % destination}))
        return EXIT_FAILURE

    spec = LayoutSpec(args.preset, args.water, world_seed=args.seed,
                      layout_id="large-world-first-pass", mode="finite",
                      frame_origin_m=args.frame_origin_m, frame_side_m=args.frame_side_m,
                      region_side_m=args.region_side_m)
    config = WorldLayoutGenerationConfig.from_layout(spec)
    try:
        window = (select_nonempty_window(spec, PAGE_SIDE_CELLS, prefer=args.prefer)
                  if args.origin_native_xz is None else None)
    except BaseException as error:  # reported with the rule that failed
        print(json.dumps({"error": "window selection failed: %s" % error,
                          "prefer": args.prefer, "page_cells": PAGE_SIDE_CELLS},
                         indent=2))
        return EXIT_INPUT

    origin_native = (tuple(args.origin_native_xz) if window is None else
                     (int(round(window["origin_m"][0] / 30.0)),
                      int(round(window["origin_m"][1] / 30.0))))
    plan = {"preset": args.preset, "water": args.water, "seed": args.seed,
            "page_side_cells": PAGE_SIDE_CELLS,
            "origin_native_xz": list(origin_native),
            "origin_world_m": [origin_native[0] * 30.0, origin_native[1] * 30.0],
            "window": window, "layout_identity": config.layout_identity,
            "conditioning_identity": config.identity(),
            "gpu_monitor": args.gpu_monitor,
            "gpu_limit_scope": ("pytorch_allocator_only_excludes_driver_and_other_processes"
                                if args.gpu_monitor == "allocator"
                                else "child_process_gpu_memory"),
            "budgets": describe_budgets(args.gpu_monitor)}
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True, default=float))
        return EXIT_OK

    try:
        preflight(ROOT / args.model_dir, gpu_monitor=args.gpu_monitor)
        result = run_single_page(spec, config, origin_native_xz=origin_native,
                                 model_dir=ROOT / args.model_dir, seed=args.seed,
                                 device=args.device, dtype=args.dtype,
                                 gpu_monitor=args.gpu_monitor)
    except BudgetExceeded as breach:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "failure.json").write_text(
            json.dumps({"status": "budget_exceeded", "breach": str(breach),
                        "budget": breach.budget, "observed": breach.observed,
                        "plan": plan}, indent=2, default=float), encoding="utf-8")
        print(json.dumps({"status": "budget_exceeded", "breach": str(breach)}))
        return EXIT_BUDGET
    except BaseException as error:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "failure.json").write_text(
            json.dumps({"status": "failed", "error": "%s: %s"
                                        % (type(error).__name__, error),
                        "plan": plan}, indent=2, default=float), encoding="utf-8")
        print(json.dumps({"status": "failed", "error": str(error)}))
        return EXIT_FAILURE

    destination.mkdir(parents=True, exist_ok=True)
    import numpy as np
    np.save(destination / "elevation.npy", result["elevation"])
    np.save(destination / "climate.npy", result["climate"])
    axis = np.arange(PAGE_SIDE_CELLS, dtype=np.float64) * 30.0
    x, z = np.meshgrid(origin_native[0] * 30.0 + axis,
                       origin_native[1] * 30.0 + axis)
    np.save(destination / "layout-classes.npy", classify_points(spec, x, z))
    metadata = {"schema": "td-native-page-v1", "native_origin": list(origin_native),
                "size": PAGE_SIDE_CELLS, "spacing_m": 30.0,
                "world_seed": args.seed, "layout_identity": config.layout_identity,
                "conditioning_identity": config.identity(),
                "entry_point": "Terrain Diffusion WorldPipeline.get"}
    page_path = destination / "native-page.npz"
    np.savez(page_path, elevation_native=result["elevation"].astype(np.float64),
             metadata_json=np.array(json.dumps(metadata, sort_keys=True)))
    digest = hashlib.sha256(page_path.read_bytes()).hexdigest()
    (destination / "page-record.json").write_text(
        json.dumps({"path": str(page_path.resolve()), "sha256": digest}, indent=2),
        encoding="utf-8")
    (destination / "page.json").write_text(
        json.dumps({"plan": plan, "layout_parameters": spec.parameters(),
                    "conditioning_parameters": config.record(),
                    **result["metadata"]}, indent=2, default=float),
        encoding="utf-8")
    print(json.dumps({"status": "ok", "written": str(destination)}))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
