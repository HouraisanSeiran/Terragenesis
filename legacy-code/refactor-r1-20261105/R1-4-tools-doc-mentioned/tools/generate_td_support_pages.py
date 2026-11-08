"""Generate the TD support pages the 40 km selection's convergence gate needs.

Why this exists
---------------
`tools/scan_40km_area.py` measures each candidate basin in 513/1025/1537-node windows
placed by **absolute** coordinates. For a basin near the rim of the scanned page, the
largest of those windows leaves that page, so the gate cannot be measured there. The
answer is more of the same terrain -- not a smaller tolerance and not a small basin
that happens to sit mid-page.

Terrain Diffusion is a pure function of `(seed, absolute coordinates)`, so more
terrain is obtainable. What is *not* free: the outermost rings of any generated
window depend on how much terrain the decoder could see, so a cell is only
reproducible when it sits at least `SAFE_INSET_CELLS` inside the window that produced
it (measured, see `scan_40km_area.SAFE_INSET_CELLS`). That is why a 1537-node
convergence window cannot be served by one 1337-node page and this tool generates
full 2049-node pages instead: 2049 - 2*4 = 2041 usable nodes per side.

Provenance
----------
Pages are written in the same schema as `.scratch/fine-terrain-01/td-window-0*.npz`
(`elevation_native` + `metadata_json` with `native_origin`, `world_seed`, ...), so
`scan_40km_area` treats them as the same terrain family and can also verify overlap:
where a new page overlaps an archived one they must agree bitwise inside the safe
interior, and this tool records that measurement in each page's metadata.

Usage
-----
    # dry run: print the plan only
    runtime/venv/Scripts/python.exe -B tools/generate_td_support_pages.py \
        --plan .scratch/fine-terrain-40km/selection-v8/selection.json --dry-run

    # generate (GPU, explicit opt-in)
    runtime/venv/Scripts/python.exe -B tools/generate_td_support_pages.py \
        --plan .scratch/fine-terrain-40km/selection-v8/selection.json --generate
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.scan_40km_area import (  # noqa: E402
    SAFE_INSET_CELLS, SPACING_M, WORLD_SEED, NativePage, PageMosaic,
    plan_support_tiles,
)

DEFAULT_TILE_NODES = 2049          # one `pipeline.get`; the archives were cut this way
DEFAULT_STRIDE = 2000


def gpu_preflight(*, max_used_mib=2048, min_free_mib=6000, max_utilization=10):
    """Refuse while a game holds the GPU or free VRAM is short. No queueing."""
    try:
        tasks = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                               capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("cannot read the process list: " + type(error).__name__)
    if any(name in tasks.stdout.lower() for name in ("aces.exe", "aces64.exe",
                                                     "warthunder.exe")):
        raise RuntimeError("a game (War Thunder) is running; TD inference deferred")
    try:
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free,utilization.gpu",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError("cannot read GPU counters: " + type(error).__name__)
    rows = [[int(part.strip()) for part in line.split(",")]
            for line in gpu.stdout.strip().splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) != 3:
        raise RuntimeError("exactly one CUDA GPU with readable counters required")
    used, free, utilization = rows[0]
    if used > max_used_mib or free < min_free_mib or utilization > max_utilization:
        raise RuntimeError(
            "GPU busy or short of VRAM (used %d MiB, free %d MiB, util %d%%); TD "
            "inference deferred rather than queued" % (used, free, utilization))
    return {"used_mib": used, "free_mib": free, "utilization_percent": utilization}


def needed_windows(plan):
    """Absolute 1537-node rectangles the gate asked for and could not measure."""
    windows = []
    for entry in plan.get("rejected", []):
        if entry.get("reason_code") != "convergence_window_outside_source":
            continue
        needed = entry["needed_window"]
        windows.append((needed["native_column_range"][0], needed["native_row_range"][0],
                        needed["nodes"], needed["nodes"]))
    return windows


def existing_pages(paths):
    pages = []
    for path in paths:
        with np.load(Path(path), allow_pickle=False) as archive:
            elevation = np.asarray(archive["elevation_native"], np.float64)
            metadata = json.loads(str(archive["metadata_json"]))
        native = metadata["native_origin"]
        pages.append(NativePage(
            elevation=elevation, spacing_m=float(metadata.get("spacing_m", SPACING_M)),
            origin_m=(float(native[0]) * SPACING_M, float(native[1]) * SPACING_M),
            metadata=metadata,
            origin_native=(int(round(float(native[0]))), int(round(float(native[1]))))))
    return pages


def verify_against_existing(elevation, origin, known, inset=SAFE_INSET_CELLS):
    """Compare a new page with archived pages inside the shared safe interior.

    Returns a record per archive: the overlap area and the measured difference. Inside
    the safe interior both pages must agree **exactly**; the outer rings are excluded
    because they are the part measured to be window-size dependent.
    """
    column0, row0 = origin
    rows, columns = elevation.shape
    spacing = SPACING_M
    records = []
    for page in known:
        known_column, known_row = page.origin_native
        known_rows, known_columns = page.shape
        lo_column = max(column0 + inset, known_column + inset)
        hi_column = min(column0 + columns - inset, known_column + known_columns - inset)
        lo_row = max(row0 + inset, known_row + inset)
        hi_row = min(row0 + rows - inset, known_row + known_rows - inset)
        if lo_column >= hi_column or lo_row >= hi_row:
            continue
        mine = elevation[lo_row - row0:hi_row - row0, lo_column - column0:hi_column - column0]
        theirs = page.elevation[lo_row - known_row:hi_row - known_row,
                                lo_column - known_column:hi_column - known_column]
        difference = np.abs(mine - theirs)
        records.append({
            "against": [known_column, known_row],
            "safe_overlap_shape": [int(value) for value in mine.shape],
            "safe_overlap_origin": [lo_column, lo_row],
            "max_abs_difference_m": float(difference.max()),
            "differing_cells": int((difference != 0.).sum()),
            "spacing_m": spacing})
    return records


def generate(pages_dir, tiles, *, seed, known, tile_nodes):
    """Generate each planned tile with `pipeline.get` and save it with its provenance.

    `backend.generate` is deliberately *not* used: it caps windows at the declared
    `MAX_WINDOW_CELLS` (1337), and enlarging a declared budget needs its own
    measurement. The archived 2049 pages were cut with `pipeline.get` directly, so
    this follows that documented entry point and records it in the metadata.
    """
    import torch

    from diffusion.physical_backend import PhysicalTerrainDiffusionBackend
    from diffusion.physical_config import PhysicalGenerationConfig

    pages_dir.mkdir(parents=True, exist_ok=True)
    backend = PhysicalTerrainDiffusionBackend(PhysicalGenerationConfig())
    backend.load()
    records = []
    try:
        backend.pipeline.change_seed(int(seed))
        for index, tile in enumerate(tiles):
            column, row = tile["native_origin"]
            nodes = int(tile["nodes"])
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            with torch.inference_mode():
                output = backend.pipeline.get(row, column, row + nodes, column + nodes,
                                              with_climate=False)
            elevation = output["elev"].detach().float().cpu().numpy().astype(np.float64)
            seconds = time.perf_counter() - started
            peak = float(torch.cuda.max_memory_allocated() / 2 ** 20)
            if elevation.shape != (nodes, nodes) or not np.isfinite(elevation).all():
                raise RuntimeError("TD returned an unexpected shape or nonfinite elevation")
            overlap = verify_against_existing(elevation, (column, row), known)
            disagreeing = [record for record in overlap
                           if record["differing_cells"] != 0]
            if disagreeing:
                raise RuntimeError(
                    "new page at %s disagrees with an archived page inside the safe "
                    "interior: %s; refusing to publish a page that is not the same "
                    "terrain" % ([column, row], json.dumps(disagreeing)))
            metadata = {
                "schema": "td-native-page-v1", "index": index,
                "native_origin": [column, row], "size": nodes, "world_seed": int(seed),
                "spacing_m": SPACING_M, "seconds": seconds, "peak_cuda_mib": peak,
                "safe_inset_cells": SAFE_INSET_CELLS,
                "entry_point": ("WorldPipeline.get (the same entry point that produced "
                                ".scratch/fine-terrain-01/td-window-0*.npz; "
                                "PhysicalTerrainDiffusionBackend.generate caps at "
                                "MAX_WINDOW_CELLS=%d, which is not changed here)"
                                % 1337),
                "torch": torch.__version__,
                "device": torch.cuda.get_device_name(0),
                "min_native": float(elevation.min()), "max_native": float(elevation.max()),
                "verified_against_archives": overlap,
            }
            path = pages_dir / ("td-page-%04d-%04d-%d.npz" % (column, row, nodes))
            np.savez(path, elevation_native=elevation.astype(np.float64),
                     metadata_json=np.array(json.dumps(metadata, sort_keys=True)))
            records.append({"path": str(path), **{key: metadata[key] for key in
                                                  ("native_origin", "size", "seconds",
                                                   "peak_cuda_mib", "min_native",
                                                   "max_native")},
                            "verified_against_archives": overlap})
            print("[page %d] origin %s nodes %d  %.1f s  peak %.0f MiB  overlap %s" % (
                index, [column, row], nodes, seconds, peak,
                [(record["against"], record["max_abs_difference_m"])
                 for record in overlap]), flush=True)
    finally:
        backend.close()
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", required=True,
                        help="selection.json from tools/scan_40km_area.py")
    parser.add_argument("--pages-dir", default=".scratch/fine-terrain-40km/td-pages")
    parser.add_argument("--known-page", action="append", default=[],
                        help="archived TD page to verify a new page against (repeatable)")
    parser.add_argument("--tile-nodes", type=int, default=DEFAULT_TILE_NODES)
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    parser.add_argument("--seed", type=int, default=WORLD_SEED)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--generate", action="store_true", default=False)
    args = parser.parse_args(argv)

    if args.seed != WORLD_SEED:
        raise SystemExit("this tool is pinned to world_seed=%d; refusing %d"
                         % (WORLD_SEED, args.seed))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    if int(plan.get("world_seed", -1)) != WORLD_SEED:
        raise SystemExit("plan was produced for another seed")
    windows = needed_windows(plan)
    if not windows:
        print("nothing to generate: the plan has no unmmeasurable candidate")
        return 0
    tiles = plan_support_tiles(windows, tile_nodes=args.tile_nodes, stride=args.stride)
    summary = {"plan": str(args.plan), "unmeasurable_candidates": len(windows),
               "tile_nodes": args.tile_nodes, "stride": args.stride,
               "tiles": tiles, "pages_dir": args.pages_dir}
    if args.dry_run or not args.generate:
        summary["status"] = "dry_run"
        summary["note"] = "pass --generate to run TD inference; nothing was generated"
        print(json.dumps(summary, indent=2))
        return 0

    summary["gpu_preflight"] = gpu_preflight()
    known = existing_pages(args.known_page)
    records = generate(Path(args.pages_dir), tiles, seed=args.seed, known=known,
                       tile_nodes=args.tile_nodes)
    summary.update(status="generated", pages=records)
    (Path(args.pages_dir) / "generation.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in
                      ("status", "unmeasurable_candidates", "tiles", "gpu_preflight")},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
