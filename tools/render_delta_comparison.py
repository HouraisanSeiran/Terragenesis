"""Compare verified saved delta rasters on one window and shared color scales."""

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
from matplotlib import font_manager
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, ListedColormap, Normalize
import numpy as np

from terrain_pipeline.complete_delta import load_run
from terrain_pipeline.terrain_map_style import LAND_COLORS, ocean_colormap
from tools.render_complete_delta import detail_limits, load_arrays, map_axis, terrain_rgb


def configure_labels():
    available = {font.name for font in font_manager.fontManager.ttflist}
    for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC"):
        if candidate in available:
            plt.rcParams["font.family"] = candidate
            plt.rcParams["axes.unicode_minus"] = False
            return True
    return False


def render(before_dir: Path, after_dir: Path, output: Path):
    runs = [load_run(before_dir), load_run(after_dir)]
    arrays = [run["arrays"] for run in runs]
    spacing = float(arrays[0]["spacing_m"])
    origin = arrays[0]["origin_xz_m"]
    shape = arrays[0]["final_bed_m"].shape
    if any(item["final_bed_m"].shape != shape
           or float(item["spacing_m"]) != spacing
           or not np.array_equal(item["origin_xz_m"], origin) for item in arrays[1:]):
        raise ValueError("Comparison requires identical saved grid shape, origin and spacing")
    rows, cols = shape
    extent = np.asarray([-.5, cols-.5, rows-.5, -.5])*spacing/1000.
    windows = [detail_limits(item, load_arrays(directory / "scene.npz"), extent)
               for item, directory in zip(arrays, (before_dir, after_dir))]
    limits = [min(window[0] for window in windows), max(window[1] for window in windows),
              max(window[2] for window in windows), min(window[3] for window in windows)]
    local_x = np.arange(cols)*spacing/1000.
    local_z = np.arange(rows)*spacing/1000.
    local = ((local_x[None, :] >= limits[0]) & (local_x[None, :] <= limits[1])
             & (local_z[:, None] >= limits[3]) & (local_z[:, None] <= limits[2]))
    beds = [item["final_bed_m"] for item in arrays]
    depths = [item["water_depth_m"] for item in arrays]
    wets = [item["wet_mask"].astype(bool) for item in arrays]
    land_values = np.concatenate([bed[local & ~wet] for bed, wet in zip(beds, wets)])
    water_values = np.concatenate([depth[local & wet] for depth, wet in zip(depths, wets)])
    land_min = min(0., float(land_values.min())) if land_values.size else 0.
    land_norm = Normalize(land_min, max(1., float(land_values.max()) if land_values.size else 1.), clip=True)
    water_norm = Normalize(0., max(1., float(water_values.max()) if water_values.size else 1.), clip=True)
    land_cmap = LinearSegmentedColormap.from_list("comparison-land", LAND_COLORS)
    wet_cmap = ListedColormap(["#dededb", "#14779b"])
    rgb = [terrain_rgb(bed, depth, wet, spacing, land_norm, water_norm)
           for bed, depth, wet in zip(beds, depths, wets)]
    chinese = configure_labels()
    label = lambda zh, en: zh if chinese else en
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 12, "figure.facecolor": "white"})

    def setup_axis(axis):
        map_axis(axis, extent, limits)
        if chinese:
            axis.set(xlabel="距场景原点向东 (km)", ylabel="距场景原点向南 (km)")

    title = label("三角洲河口：已保存结果的同尺度对照", "Delta mouth: saved rasters at identical scale")
    note = label("实际床面、水深和干湿掩膜；未添加河线；原始地形经重采样。",
                 "Actual saved bed, depth and wet mask; no added river lines. Source terrain is resampled.")
    fig, axes = plt.subplots(3, 2, figsize=(15, 16), layout="constrained")
    for index in range(2):
        version = label("修改前", "Before") if index == 0 else label("修改后", "After")
        axes[0, index].imshow(rgb[index], extent=extent, interpolation="nearest")
        axes[0, index].set_title(version + label("：最终床面与实际水体", ": final terrain and saved water"))
        axes[1, index].set_facecolor("#dededb")
        axes[1, index].imshow(np.where(wets[index], depths[index], np.nan), extent=extent,
                              cmap=ocean_colormap(), norm=water_norm, interpolation="nearest")
        axes[1, index].set_title(version + label("：实际水深，灰色为干地", ": water depth; gray = dry"))
        axes[2, index].imshow(wets[index], extent=extent, cmap=wet_cmap,
                              vmin=0, vmax=1, interpolation="nearest")
        axes[2, index].set_title(version + label("：实际干湿掩膜", ": actual wet mask"))
    for axis in axes.flat:
        setup_axis(axis)
    fig.colorbar(ScalarMappable(norm=land_norm, cmap=land_cmap), ax=list(axes[0]),
                 label=label("干地床面高程 (m)", "Dry bed elevation (m)"), shrink=.75)
    fig.colorbar(ScalarMappable(norm=water_norm, cmap=ocean_colormap()), ax=list(axes[1]),
                 label=label("水深 (m)", "Water depth (m)"), shrink=.75)
    wet_bar = fig.colorbar(ScalarMappable(norm=Normalize(0, 1), cmap=wet_cmap),
                           ax=list(axes[2]), ticks=[.25, .75], shrink=.75)
    wet_bar.ax.set_yticklabels([label("干地", "Dry"), label("水体", "Wet")])
    fig.suptitle(title, fontsize=18)
    fig.supxlabel(note, fontsize=10)
    output.mkdir(parents=True, exist_ok=True)
    comparison_path = output / "comparison.png"
    fig.savefig(comparison_path, dpi=170)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(11, 10), layout="constrained")
    axis.imshow(rgb[1], extent=extent, interpolation="nearest")
    setup_axis(axis)
    axis.set_title(label("新版三角洲河口：最终床面与实际水体", "Revised delta mouth: final bed and actual water"), fontsize=16)
    fig.colorbar(ScalarMappable(norm=land_norm, cmap=land_cmap), ax=axis,
                 label=label("干地床面高程 (m)", "Dry bed elevation (m)"), shrink=.65, pad=.03)
    fig.colorbar(ScalarMappable(norm=water_norm, cmap=ocean_colormap()), ax=axis,
                 label=label("水深 (m)", "Water depth (m)"), shrink=.65, pad=.02)
    fig.supxlabel(note, fontsize=10)
    after_path = output / "after-mouth.png"
    fig.savefig(after_path, dpi=190)
    plt.close(fig)
    metadata = {
        "before_run": str(before_dir), "after_run": str(after_dir),
        "verification": "Both products passed load_run manifest SHA-256 verification before rendering",
        "source_file_sha256": [run["summary"]["file_sha256"] for run in runs],
        "images": [str(comparison_path), str(after_path)], "raster_shape": list(shape),
        "spacing_m": spacing, "origin_xz_m": origin.tolist(),
        "coordinate_convention": "Grid centres: columns +x/east, rows +z/south; displayed km from shared scene origin",
        "detail_extent_relative_km": limits,
        "window_method": "Union of both distributary detail envelopes including existing 600 m margin",
        "shared_land_limits_m": [land_norm.vmin, land_norm.vmax],
        "shared_water_depth_limits_m": [water_norm.vmin, water_norm.vmax],
        "color_limits_method": "Full extrema within common window, with at least 0 to 1 m range; no percentile clipping",
        "interpolation": "nearest", "added_channel_lines": False,
        "display_arrays": ["final_bed_m", "water_depth_m", "wet_mask"],
        "label_language": "zh" if chinese else "en",
        "source_resolution_note": "Source terrain resampled; saved spacing does not establish source detail.",
    }
    (output / "render-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(render(args.before.resolve(), args.after.resolve(), args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
