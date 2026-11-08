"""Render saved complete-delta arrays without adding schematic river lines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm
from matplotlib.cm import ScalarMappable
import numpy as np

from terrain_pipeline.terrain_map_style import (
    LAND_COLORS, apply_hillshade, draw_scale_bar, nice_scale_length_km,
    ocean_colormap,
)
from terrain_pipeline.complete_delta import load_run


def load_arrays(path):
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key].copy() for key in archive.files}


def map_axis(axis, extent, limits=None):
    axis.set(xlabel="East from scene origin (km)", ylabel="South from scene origin (km)",
             aspect="equal", xlim=extent[:2], ylim=extent[2:])
    if limits is not None:
        axis.set(xlim=limits[:2], ylim=limits[2:])
    draw_scale_bar(axis, nice_scale_length_km(axis.get_xlim()[1] - axis.get_xlim()[0]))


def terrain_rgb(bed, depth, wet, spacing, land_norm, water_norm):
    land = LinearSegmentedColormap.from_list("delta-land", LAND_COLORS)
    rgb = apply_hillshade(land(land_norm(bed))[..., :3], bed, spacing)
    rgb[wet] = ocean_colormap()(water_norm(depth[wet]))[..., :3]
    return rgb


def detail_limits(arrays, scene, extent):
    origin = arrays["origin_xz_m"]
    for key in ("branch_paths_xz_m", "distributary_paths_xz_m"):
        if key in scene:
            points = scene[key].reshape(-1, 2)
            points = points[np.isfinite(points).all(axis=1)]
            points = (points - origin) / 1000.
            if len(points):
                low = points.min(axis=0) - .6
                high = points.max(axis=0) + .6
                return [max(extent[0], low[0]), min(extent[1], high[0]),
                        min(extent[2], high[1]), max(extent[3], low[1])]
    changed = np.abs(arrays["height_delta_m"]) > 1.e-8
    rows, cols = np.where(changed)
    if not rows.size:
        return extent
    spacing = float(arrays["spacing_m"]) / 1000.
    return [max(extent[0], cols.min()*spacing - .7),
            min(extent[1], cols.max()*spacing + .7),
            min(extent[2], rows.max()*spacing + .7),
            max(extent[3], rows.min()*spacing - .7)]


def render(run_dir: Path):
    saved = load_run(run_dir)
    arrays = saved["arrays"]
    scene = load_arrays(run_dir / "scene.npz")
    summary = saved["summary"]
    images = run_dir / "images"
    images.mkdir(parents=True, exist_ok=True)
    bed = arrays["final_bed_m"]
    initial = arrays["initial_bed_m"]
    depth = arrays["water_depth_m"]
    wet = arrays["wet_mask"].astype(bool)
    spacing = float(arrays["spacing_m"])
    rows, cols = bed.shape
    extent = np.asarray([-.5, cols-.5, rows-.5, -.5])*spacing/1000.
    limits = detail_limits(arrays, scene, extent)
    land_norm = Normalize(0., max(10., float(np.nanpercentile(bed[~wet], 99.7))), clip=True)
    water_norm = Normalize(0., max(5., float(np.nanpercentile(depth[wet], 99.7))), clip=True)
    rgb = terrain_rgb(bed, depth, wet, spacing, land_norm, water_norm)
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 12, "figure.facecolor": "white"})
    fig, axes = plt.subplots(1, 2, figsize=(16, 8), layout="constrained")
    axes[0].imshow(rgb, extent=extent, interpolation="nearest")
    axes[0].set_title("Final terrain and actual saved water extent")
    axes[1].imshow(apply_hillshade(np.full((*bed.shape, 3), .87), bed, spacing),
                   extent=extent, interpolation="nearest")
    image = axes[1].imshow(np.where(wet, depth, np.nan), extent=extent,
                           cmap=ocean_colormap(), norm=water_norm, interpolation="nearest")
    axes[1].set_title("Actual connected water depth; gray = dry")
    for axis in axes:
        map_axis(axis, extent)
    fig.colorbar(ScalarMappable(norm=land_norm, cmap=LinearSegmentedColormap.from_list("land-legend", LAND_COLORS)),
                 ax=axes[0], label="Dry bed elevation above sea datum (m)", shrink=.65, extend="max")
    fig.colorbar(image, ax=axes[1], label="Saved water depth (m)", shrink=.65, extend="max")
    fig.suptitle(f"Complete 16 km delta | saved raster {cols} x {rows} at {spacing:g} m", fontsize=17)
    fig.supxlabel("Constructed initial distributaries; saved final bed and water. Source TD is resampled; grid spacing is not source detail.", fontsize=10)
    fig.savefig(images / "overview.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(14, 12), layout="constrained")
    local_columns = np.arange(cols)*spacing/1000.
    local_rows = np.arange(rows)*spacing/1000.
    local_mask = ((local_columns[None, :] >= limits[0]) & (local_columns[None, :] <= limits[1])
                  & (local_rows[:, None] >= limits[3]) & (local_rows[:, None] <= limits[2]))
    land_values = np.r_[initial[local_mask & (initial >= 0.)], bed[local_mask & ~wet]]
    local_land_norm = Normalize(0., max(1., float(np.percentile(land_values, 99.7))), clip=True)
    local_water_values = np.r_[depth[local_mask & wet], np.maximum(-initial[local_mask], 0.)]
    local_water_norm = Normalize(0., max(1., float(np.percentile(local_water_values, 99.7))), clip=True)
    init_rgb = terrain_rgb(initial, np.maximum(-initial, 0.), initial < 0., spacing, local_land_norm, local_water_norm)
    local_rgb = terrain_rgb(bed, depth, wet, spacing, local_land_norm, local_water_norm)
    axes[0, 0].imshow(init_rgb, extent=extent, interpolation="nearest")
    axes[0, 0].set_title("Initial constructed bed; blue = below sea datum")
    axes[0, 1].imshow(local_rgb, extent=extent, interpolation="nearest")
    axes[0, 1].set_title("Final terrain and actual saved water")
    image = axes[1, 0].imshow(np.where(wet, depth, np.nan), extent=extent,
                             cmap=ocean_colormap(), norm=local_water_norm, interpolation="nearest")
    axes[1, 0].set_facecolor("#dededb")
    axes[1, 0].set_title("Actual final water depth; gray = dry")
    fig.colorbar(image, ax=axes[1, 0], label="Water depth (m)", shrink=.8, extend="max")
    change = arrays["height_delta_m"]
    maximum = max(float(np.abs(change).max()), 1.e-6)
    image = axes[1, 1].imshow(change, extent=extent, cmap="RdBu_r",
                             norm=TwoSlopeNorm(vmin=-maximum, vcenter=0., vmax=maximum),
                             interpolation="nearest")
    axes[1, 1].set_title("Actual morphodynamic bed change; construction excluded")
    fig.colorbar(image, ax=axes[1, 1], label="Final minus initial bed (m)", shrink=.8)
    for axis in axes.flat:
        map_axis(axis, extent, limits)
    fig.suptitle("Delta mouth detail | saved pixels, no added channel lines", fontsize=17)
    fig.supxlabel(f"Local shared color ranges: dry bed 0-{local_land_norm.vmax:.2f} m; water depth 0-{local_water_norm.vmax:.2f} m. Source TD resampled.", fontsize=10)
    fig.savefig(images / "detail.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(15, 10), layout="constrained")
    q = arrays["monthly_terminal_q_m3_s"]
    months = np.arange(1, len(q)+1)
    total_q = q.sum(axis=1)
    fractions = np.divide(q, total_q[:, None], out=np.zeros_like(q), where=total_q[:, None] > 0.)
    for index in range(q.shape[1]):
        axes[0, 0].plot(months, fractions[:, index], marker=".", label=f"Outlet {index+1}")
    axes[0, 0].set(xlabel="Month", ylabel="Terminal discharge fraction", ylim=(0., 1.),
                   title="Hydraulic flow partition")
    axes[0, 0].legend(ncol=3, fontsize=8)
    water_in = arrays["monthly_water_m3"]
    water_out = total_q*arrays["month_seconds"]
    axes[0, 1].plot(months, water_in/1.e6, marker="o", label="Boundary input")
    axes[0, 1].plot(months, water_out/1.e6, marker="x", linestyle="--", label="Terminal output")
    axes[0, 1].set(xlabel="Month", ylabel="Water volume (million m3)", title="Monthly water throughput")
    axes[0, 1].legend()
    solid_in = arrays["monthly_solid_m3"]
    solid_out = arrays["monthly_terminal_export_solid_m3"]
    if solid_out.ndim > 1:
        solid_out = solid_out.sum(axis=1)
    axes[1, 0].bar(months, solid_in, color="#b76732", label="Finite supplied solid")
    axes[1, 0].plot(months, solid_out, color="#174c69", marker="o", label="Terminal export")
    axes[1, 0].set(xlabel="Month", ylabel="Solid volume (m3)", title="Monthly sediment budget")
    axes[1, 0].legend()
    axes[1, 1].axis("off")
    ledger = summary["solid_ledger"]
    lines = ["Saved model ledger (solid m3)"]
    lines.extend(f"{key}: {value:,.6g}" for key, value in ledger.items()
                 if isinstance(value, (int, float)))
    lines += ["", f"Maximum actual bed rise: {change.max():.6g} m",
              f"Maximum actual bed lowering: {change.min():.6g} m",
              f"Saved raster: {cols} x {rows} at {spacing:g} m",
              "", "Initial earthwork and channel geometry are construction.",
              "Only final minus initial bed is modelled deposition / erosion."]
    axes[1, 1].text(.02, .98, "\n".join(lines), va="top", fontsize=10, linespacing=1.6)
    fig.suptitle("Flow and material diagnostics | construction excluded from sediment supply", fontsize=16)
    fig.savefig(images / "diagnostics.png", dpi=160)
    plt.close(fig)
    return {"images": [str(images / name) for name in ("overview.png", "detail.png", "diagnostics.png")],
            "source_result": str(run_dir / "result.npz"), "raster_shape": [rows, cols],
            "spacing_m": spacing, "detail_extent_relative_km": list(limits),
            "interpolation": "nearest", "added_channel_lines": False,
            "land_color_limits_m": [land_norm.vmin, land_norm.vmax],
            "water_color_limits_m": [water_norm.vmin, water_norm.vmax],
            "detail_land_color_limits_m": [local_land_norm.vmin, local_land_norm.vmax],
            "detail_water_color_limits_m": [local_water_norm.vmin, local_water_norm.vmax],
            "source_resolution_note": "Source TD is resampled; saved spacing does not establish source detail."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    result = render(args.run.resolve())
    (args.run / "images" / "render-metadata.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
