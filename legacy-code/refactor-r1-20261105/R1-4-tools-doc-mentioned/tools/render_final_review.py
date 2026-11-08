"""Final review image set for the cross-region reach.

Sources, kept strictly separate:

* ``full-grid-bed-01``     coupled 50 m mesh bed (``bed-change-field.npz``),
                           lake stage from its own ``lake-storage.npz``.
* ``floodplain-2d-01``     the saved two-dimensional depth page; only that file
                           is drawn for the inundation frames, so a nodal run is
                           never mixed into a grid-bed picture.

Every panel carries a scale bar, a north arrow, the world seed, the physical
time and the synthetic-render declaration.

    python tools/render_final_review.py \\
        --grid-run .scratch/cross-region-tributary/full-grid-bed-01 \\
        --flood-run .scratch/cross-region-tributary/floodplain-2d-01 \\
        --output .scratch/cross-region-tributary/final-review/remote-sensing
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, TwoSlopeNorm

from tools.render_remote_sensing import (
    DECLARATION, SUN_ALTITUDE_DEG, SUN_AZIMUTH_DEG,
    _annotate, _draw_overlays, _save, _truncated_edges, carved_bed,
    floodplain_depth_state, floodplain_mask_on, lake_state, render,
    surface_rgb, terrain_window,
)

# The saved flood series counts water above 0.02 m; the pictures must use the same
# threshold or the drawn area disagrees with the reported area.
FLOOD_MIN_DEPTH_M = 0.02


def _flood_tint(depth):
    """Log depth tint: 0.02 m shows as shallow cyan, 35 m as near-black blue."""
    floor = np.log10(FLOOD_MIN_DEPTH_M)
    ceiling = np.log10(35.0)
    span = np.clip((np.log10(np.maximum(depth, FLOOD_MIN_DEPTH_M)) - floor) / (ceiling - floor),
                   0.0, 1.0)[..., None]
    return np.array((0.45, 0.72, 0.78)) * (1.0 - span) + np.array((0.03, 0.12, 0.30)) * span


def _window(centre_x, centre_z, span_km_x, span_km_z, pixel_m):
    half_x = span_km_x * 500.0
    half_z = span_km_z * 500.0
    xs = np.arange(centre_x - half_x, centre_x + half_x + pixel_m, pixel_m)
    zs = np.arange(centre_z - half_z, centre_z + half_z + pixel_m, pixel_m)
    return xs, zs


def bed_change_image(grid_run, output, *, world_seed, centre_xz, span_km_x=35.0,
                     span_km_z=35.0, pixel_m=40.0):
    """Diverging map of the coupled bed change (final minus initial carve)."""
    grid_run = Path(grid_run)
    xs, zs = _window(centre_xz[0], centre_xz[1], span_km_x, span_km_z, pixel_m)
    change, mask, _ = carved_bed(grid_run, xs, zs, frame="change")
    final_bed, _, _ = carved_bed(grid_run, xs, zs, frame="final")
    height, spacing, _ = terrain_window(grid_run, xs, zs)
    bed = np.where(np.isfinite(final_bed), final_bed, height)
    shade = LightSource(azdeg=SUN_AZIMUTH_DEG, altdeg=SUN_ALTITUDE_DEG).hillshade(
        bed, vert_exag=6.0, dx=pixel_m, dy=pixel_m)
    grey = np.clip(0.30 + 0.62 * shade, 0.0, 1.0)
    rgb = np.repeat(grey[..., None], 3, axis=2) * 0.55

    change_mm = np.where(np.isfinite(change), change * 1000.0, np.nan)
    with np.load(grid_run / "bed-change-field.npz") as field:
        vertex_change = np.array(field["bed_change_m"], np.float64)
    nonzero_vertices = int(np.count_nonzero(np.abs(vertex_change) > 1e-12))
    total_vertices = int(vertex_change.size)
    limit = float(np.nanpercentile(np.abs(change_mm), 99.5)) or 1.0
    norm = TwoSlopeNorm(vmin=-limit, vcenter=0.0, vmax=limit)
    rgba = plt.get_cmap("RdBu_r")(norm(np.nan_to_num(change_mm, nan=0.0)))
    strength = np.clip(np.abs(np.nan_to_num(change_mm, nan=0.0)) / limit, 0.0, 1.0)
    inside = np.isfinite(change_mm) & (strength > 0.02)
    alpha = np.where(inside, np.clip(0.35 + 0.65 * strength, 0.0, 0.95), 0.0)
    rgb = rgb * (1.0 - alpha[..., None]) + rgba[..., :3] * alpha[..., None]

    fig, ax = plt.subplots(figsize=(12.5, 9.5), facecolor="#0d1117")
    ax.imshow(np.clip(rgb, 0.0, 1.0), extent=[xs[0], xs[-1], zs[-1], zs[0]],
              origin="upper", interpolation="nearest")
    ax.set_facecolor("#0d1117")
    _annotate(ax, xs, zs,
              "床变差异 · 最终减初始切槽",
              "%d 顶点中 %d 个有非零变化（其余为未动支撑顶点）" % (total_vertices, nonzero_vertices),
              ["world_seed=%d" % world_seed,
               "72 h 终态（t = 259 200 s）",
               "红色 = 下切，蓝色 = 淤积，灰底为最终床影像",
               "色标 ±%.2f mm（99.5 百分位）" % limit])
    _draw_overlays(ax, None, _truncated_edges(grid_run))
    bar = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap="RdBu_r"), ax=ax,
                       fraction=0.032, pad=0.015)
    bar.set_label("床面变化 (mm)", color="white", fontsize=9)
    bar.ax.tick_params(colors="white", labelsize=8)
    bar.outline.set_edgecolor("#888888")
    path = Path(output) / "bed-change-difference.png"
    _save(fig, path)
    return {
        "file": str(path),
        "min_mm": float(vertex_change.min() * 1000.0),
        "max_mm": float(vertex_change.max() * 1000.0),
        "nonzero_vertices": nonzero_vertices,
        "total_vertices": total_vertices,
        "colour_limit_mm": limit,
        "source": str(grid_run / "bed-change-field.npz"),
    }


def floodplain_frames(flood_run, output, *, world_seed, times_s, pixel_m=45.0):
    """Draw the saved two-dimensional depth page at the requested times."""
    flood_run = Path(flood_run)
    sidecar = json.loads((flood_run / "floodplain-depth-field.json").read_text(encoding="utf-8"))
    cell_area = float(sidecar["cell_area_m2"])
    series = np.load(flood_run / "flood-series.npz")
    panels = []
    for label, wanted in times_s:
        state = floodplain_depth_state(flood_run, wanted)
        if state is None:
            raise ValueError("no saved floodplain depth field in %s" % flood_run)
        page = state["depth_m"]
        spacing = state["spacing_m"]
        gx = state["origin_xz_m"][0] + np.arange(page.shape[1]) * spacing
        gz = state["origin_xz_m"][1] + np.arange(page.shape[0]) * spacing
        xs, zs = _window(0.5 * (gx[0] + gx[-1]), 0.5 * (gz[0] + gz[-1]),
                         (gx[-1] - gx[0]) / 1000.0 * 1.02,
                         (gz[-1] - gz[0]) / 1000.0 * 1.02, pixel_m)
        depth = floodplain_mask_on(xs, zs, state)
        height, _, _ = terrain_window(flood_run, xs, zs)
        rgb = surface_rgb(height, pixel_m, 6.0)
        wet = depth > FLOOD_MIN_DEPTH_M
        tint = _flood_tint(depth)
        edge = np.clip((depth - FLOOD_MIN_DEPTH_M) / 0.05, 0.0, 1.0)[..., None]
        rgb = np.where(wet[..., None], rgb * (1.0 - edge) + tint * edge, rgb)
        wet_cells = int(np.count_nonzero(page > FLOOD_MIN_DEPTH_M))
        panels.append({
            "label": label,
            "time_seconds": state["time_seconds"],
            "rgb": rgb,
            "xs": xs,
            "zs": zs,
            "wet_area_km2": float(np.interp(state["time_seconds"], series["time_s"],
                                            series["wet_area_m2"])) / 1e6,
            "painted_area_km2": wet_cells * cell_area / 1e6,
            "max_depth_m": float(np.max(page)),
            "depth_threshold_m": FLOOD_MIN_DEPTH_M,
            "overbank_km2": float(np.interp(state["time_seconds"], series["time_s"],
                                            series["overbank_wet_area_m2"])) / 1e6,
        })

    fig, axes = plt.subplots(1, len(panels), figsize=(6.6 * len(panels), 7.0),
                             facecolor="#0d1117", squeeze=False)
    axes = axes[0]
    for ax, panel in zip(axes, panels):
        ax.imshow(panel["rgb"], extent=[panel["xs"][0], panel["xs"][-1],
                                        panel["zs"][-1], panel["zs"][0]],
                  origin="upper", interpolation="nearest")
        ax.set_facecolor("#0d1117")
        ax.set_title("%s\nt = %.0f s" % (panel["label"], panel["time_seconds"]),
                     fontsize=10.5, pad=6)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(0.02, 0.03,
                "淹没 %.2f km²\n槽外 %.2f km²\n最大水深 %.2f m"
                % (panel["wet_area_km2"], panel["overbank_km2"], panel["max_depth_m"]),
                transform=ax.transAxes, color="white", fontsize=8.5, va="bottom",
                bbox=dict(boxstyle="round,pad=0.35", fc="black", alpha=0.6, lw=0))
        # Scale bar and north arrow on every panel.
        span_x = float(panel["xs"][-1] - panel["xs"][0])
        span_z = float(panel["zs"][-1] - panel["zs"][0])
        ax.plot([panel["xs"][0] + span_x * 0.05, panel["xs"][0] + span_x * 0.05 + 5000.0],
                [panel["zs"][-1] - span_z * 0.08] * 2, color="white", lw=4,
                solid_capstyle="butt")
        ax.text(panel["xs"][0] + span_x * 0.05 + 2500.0, panel["zs"][-1] - span_z * 0.13,
                "5 km", color="white", ha="center", va="top", fontsize=8,
                bbox=dict(boxstyle="round,pad=0.15", fc="black", alpha=0.45, lw=0))
        ax.annotate("N", xy=(panel["xs"][-1] - span_x * 0.08, panel["zs"][0] + span_z * 0.10),
                    xytext=(panel["xs"][-1] - span_x * 0.08, panel["zs"][0] + span_z * 0.20),
                    color="white", fontsize=11, ha="center",
                    arrowprops=dict(facecolor="white", width=2.5, headwidth=9,
                                    headlength=9, shrink=0.0))
    fig.suptitle("二维淹没演算 · 终端盆地（地形给定，非观测）", fontsize=14, y=0.985)
    fig.text(0.5, 0.015,
             "world_seed=%d · 90 m 二维格 · 一维→二维单向注入 · 无回流 · %s"
             % (world_seed, DECLARATION), ha="center", fontsize=9, color="#c9d4dc")
    path = Path(output) / "floodplain-series.png"
    _save(fig, path, dpi=160)
    return {
        "file": str(path),
        "source_depth_field": str(flood_run / "floodplain-depth-field.npz"),
        "panels": [{k: v for k, v in panel.items() if k not in ("rgb", "xs", "zs")}
                   for panel in panels],
    }


def run_review(grid_run, flood_run, output, *, world_seed=20261020, centre_xz=(1302500.0, 1282500.0),
               regional_km=115.0, reach_km=35.0, reach_z_km=64.0):
    grid_run = Path(grid_run)
    flood_run = Path(flood_run)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    dynamic = np.load(grid_run / "dynamic-water-sediment-bed.npz")
    times = np.asarray(dynamic["time_seconds"], np.float64)
    peak = int(np.argmax(np.asarray(dynamic["water_volume_m3"], np.float64).sum(axis=1)))
    lake = lake_state(grid_run, float(times[peak]))

    base = render(grid_run, output, world_seed=world_seed, regional_km=regional_km,
                  reach_km=reach_km, reach_z_km=reach_z_km, centre_xz_m=centre_xz,
                  lake=lake, truncated_edges=_truncated_edges(grid_run),
                  bed_frame="final")
    bed_change = bed_change_image(grid_run, output, world_seed=world_seed,
                                  centre_xz=centre_xz)
    flood = floodplain_frames(flood_run, output, world_seed=world_seed,
                              times_s=(("涨水", 3600.0), ("洪峰", 61200.0), ("退水", 259200.0)))

    review = {
        "declaration": DECLARATION,
        "world_seed": int(world_seed),
        "grid_run": str(grid_run),
        "flood_run": str(flood_run),
        "lake_peak_stage_m": None if lake is None else lake["stage_m"],
        "lake_sill_stage_m": None if lake is None else lake["sill_stage_m"],
        "base_render": base,
        "bed_change": bed_change,
        "floodplain": flood,
        "sources": {
            "regional_and_reach_bed": str(grid_run / "bed-change-field.npz") + " [final_bed_m]",
            "regional_and_reach_water": str(grid_run / "dynamic-water-sediment-bed.npz"),
            "regional_and_reach_lake": str(grid_run / "lake-storage.npz"),
            "regional_and_reach_terrain": str(grid_run / "source-terrain-and-forcing.npz"),
            "bed_change_map": str(grid_run / "bed-change-field.npz") + " [bed_change_m]",
            "floodplain_depth": str(flood_run / "floodplain-depth-field.npz"),
            "floodplain_series": str(flood_run / "flood-series.npz"),
        },
    }
    (output / "review.json").write_text(json.dumps(review, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
    return review


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grid-run", required=True)
    parser.add_argument("--flood-run", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--world-seed", type=int, default=20261020)
    parser.add_argument("--centre", nargs=2, type=float, default=(1302500.0, 1282500.0))
    args = parser.parse_args(argv)
    review = run_review(args.grid_run, args.flood_run, args.output,
                        world_seed=args.world_seed, centre_xz=tuple(args.centre))
    files = [review["base_render"]["files"][name] for name in review["base_render"]["files"]]
    files += [review["bed_change"]["file"], review["floodplain"]["file"]]
    print(json.dumps({Path(path).name: Path(path).stat().st_size for path in files}, indent=2))
    print(json.dumps(review["bed_change"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
