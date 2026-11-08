"""Render saved tidal delta terrain and distinguish reachability from prism state."""

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
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, PowerNorm
import numpy as np
from scipy.ndimage import uniform_filter

from terrain_pipeline.complete_delta import load_run, sha256
from terrain_pipeline.terrain_map_style import LAND_COLORS, ocean_colormap
from tools.render_complete_delta import detail_limits, load_arrays, map_axis, terrain_rgb
from tools.render_delta_comparison import configure_labels


def mask_limits(mask, spacing_km, extent, margin_km=.45):
    rows, columns = np.where(mask)
    if not rows.size:
        raise ValueError("Tidal geometry footprint is empty")
    return [max(extent[0], columns.min()*spacing_km-margin_km),
            min(extent[1], columns.max()*spacing_km+margin_km),
            min(extent[2], rows.max()*spacing_km+margin_km),
            max(extent[3], rows.min()*spacing_km-margin_km)]


def window_mask(shape, spacing_km, limits):
    rows, columns = shape
    x = np.arange(columns)*spacing_km
    z = np.arange(rows)*spacing_km
    return ((x[None, :] >= limits[0]) & (x[None, :] <= limits[1])
            & (z[:, None] >= limits[3]) & (z[:, None] <= limits[2]))


def render(run_dir: Path, tides_dir: Path, output: Path, before_dir: Path):
    saved = load_run(run_dir)
    previous = load_run(before_dir)
    arrays, before = saved["arrays"], previous["arrays"]
    scene = load_arrays(run_dir / "scene.npz")
    tides = load_arrays(tides_dir / "tides.npz")
    tide_summary = json.loads((tides_dir / "summary.json").read_text(encoding="utf-8"))
    tide_source_checks = {
        "tides_sha256": sha256(tides_dir / "tides.npz"),
        "source_result_sha256": sha256(run_dir / "result.npz"),
        "source_scene_sha256": sha256(run_dir / "scene.npz"),
    }
    for key, actual in tide_source_checks.items():
        if tide_summary[key] != actual:
            raise ValueError(f"Tidal validation source mismatch: {key}")
    bed = arrays["final_bed_m"]
    shape = bed.shape
    spacing = float(arrays["spacing_m"])
    spacing_km = spacing/1000.
    origin = arrays["origin_xz_m"]
    for item, bed_key in ((before, "final_bed_m"), (tides, "bed_m")):
        if (item[bed_key].shape != shape or float(item["spacing_m"]) != spacing
                or not np.array_equal(item["origin_xz_m"], origin)):
            raise ValueError("Saved annual, baseline and tide grids must match")
    if not np.array_equal(tides["bed_m"], bed):
        raise ValueError("Tide states must use the saved final annual bed")
    rows, columns = shape
    extent = np.asarray([-.5, columns-.5, rows-.5, -.5])*spacing_km
    footprint = (scene["tidal_shore_footprint_mask"].astype(bool)
                 | scene["tidal_creek_footprint_mask"].astype(bool))
    tidal_limits = mask_limits(footprint, spacing_km, extent)
    branch_limits = detail_limits(arrays, scene, extent)
    limits = [min(tidal_limits[0], branch_limits[0]), max(tidal_limits[1], branch_limits[1]),
              max(tidal_limits[2], branch_limits[2]), min(tidal_limits[3], branch_limits[3])]
    creeks = scene["tidal_creek_mask"].astype(bool)
    box_pixels = max(1, round(3.2/spacing_km))
    density = uniform_filter(creeks.astype(np.float32), size=box_pixels, mode="constant")
    row, column = np.unravel_index(np.argmax(density), shape)
    half = 2.1
    zoom = [max(extent[0], column*spacing_km-half), min(extent[1], column*spacing_km+half),
            min(extent[2], row*spacing_km+half), max(extent[3], row*spacing_km-half)]
    local = window_mask(shape, spacing_km, limits)
    wet = arrays["wet_mask"].astype(bool)
    before_wet = before["wet_mask"].astype(bool)
    lands = np.concatenate([bed[local & ~wet], before["final_bed_m"][local & ~before_wet]])
    tide_depth = tides["snapshot_water_m3"]/spacing**2
    visible_depth = float(tides["snapshot_visible_depth_threshold_m"])
    static_depth = np.maximum(tides["tide_levels_m"][:, None, None]-bed, 0.)
    land_norm = PowerNorm(.35, min(0., float(lands.min())), max(1., float(lands.max())), clip=True)
    max_depth = max(1., float(arrays["water_depth_m"][local].max()),
                    float(before["water_depth_m"][local].max()), float(tide_depth[:, local].max()),
                    float(static_depth[:, local].max()))
    water_norm = PowerNorm(.35, 0., max_depth, clip=True)
    chinese = configure_labels()
    label = lambda zh, en: zh if chinese else en
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 12, "figure.facecolor": "white"})
    output.mkdir(parents=True, exist_ok=True)
    images = []

    def setup(axis, window):
        map_axis(axis, extent, window)
        axis.set(xlabel=label("相对场景原点 x (km)", "Scene-relative x (km)"),
                 ylabel=label("相对场景原点 z (km)", "Scene-relative z (km)"))

    def paint(axis, current_bed, depth, current_wet, window, title, excluded_mask=None):
        rgb = terrain_rgb(current_bed, depth, current_wet, spacing, land_norm, water_norm)
        if excluded_mask is not None:
            rgb[excluded_mask] = .72
        axis.imshow(rgb, extent=extent, interpolation="nearest")
        setup(axis, window)
        axis.set_title(title)

    def legends(fig, axes):
        def ticks(maximum):
            return [0.] + [value for value in (1., 3., 10., 30.) if value < maximum*.8] + [maximum]

        fig.colorbar(ScalarMappable(norm=land_norm,
                     cmap=LinearSegmentedColormap.from_list("tidal-land", LAND_COLORS)),
                     ticks=ticks(land_norm.vmax), format="%.3g",
                     ax=axes, label=label("干地床面高程 (m，非线性色阶)", "Dry bed elevation (m, power scale)"), shrink=.62, pad=.025)
        fig.colorbar(ScalarMappable(norm=water_norm, cmap=ocean_colormap()), ax=axes,
                     ticks=ticks(water_norm.vmax), format="%.3g",
                     label=label("水深 (m，非线性色阶)", "Water depth (m, power scale)"), shrink=.62, pad=.025)

    def save(fig, name):
        path = output / name
        fig.savefig(path, dpi=190)
        plt.close(fig)
        images.append(str(path))

    note = label("保存的床面与水体像元；未添加河线；原始地形经重采样。",
                 "Saved bed and water pixels; no added channel lines; source terrain resampled.")
    for name, window, title in (
            ("overview.png", limits, label("全洲缘：破碎岸线与潮沟", "Delta fringe: tidal creeks and fragmented coast")),
            ("tidal-creeks-detail.png", zoom, label("密集潮沟：年度末床面与实际水体", "Dense tidal creeks: annual final bed and saved water"))):
        fig, axis = plt.subplots(figsize=(13, 10), layout="constrained")
        paint(axis, bed, arrays["water_depth_m"], wet, window, title)
        legends(fig, [axis])
        fig.supxlabel(note)
        save(fig, name)

    fig, axes = plt.subplots(2, 2, figsize=(16, 14), layout="constrained")
    tide_excluded = ~tides["tidal_valid_mask"].astype(bool)
    for column_index, phase in enumerate((0, 2)):
        phase_label = label("低潮", "Low tide") if phase == 0 else label("高潮", "High tide")
        level = float(tides["tide_levels_m"][phase])
        paint(axes[0, column_index], bed, static_depth[phase],
              tides["bed_reachable_masks"][phase].astype(bool), limits,
              phase_label + label("：床面静态可达范围", ": static bed-reachable extent") + f" ({level:+.2f} m)",
              excluded_mask=tide_excluded)
        hours = float(tides["snapshot_time_s"][phase])/3600.
        paint(axes[1, column_index], bed, tide_depth[phase],
              tides["snapshot_wet_masks"][phase].astype(bool), limits,
              phase_label + label("：实际棱柱水量状态", ": saved prism water state") + f" (t={hours:.2f} h)",
              excluded_mask=tide_excluded)
    legends(fig, list(axes.flat))
    fig.suptitle(label("低潮 / 高潮：静态范围与实际保存状态", "Low / high tide: static reachability and saved state"), fontsize=17)
    fig.supxlabel(label("上：潮位下的连通床面容量；下：有限水量棱柱状态。均非二维动量模拟。",
                       "Top: connected bed capacity. Bottom: finite-water prism state. Neither is a 2D momentum simulation.")
                  + "\n" + label(f"实际可见水体阈值：水深 ≥ {visible_depth:g} m；水量未裁剪。",
                                   f"Visible water: depth >= {visible_depth:g} m; saved water volume is not clipped.")
                  + "\n" + label("灰色：主河保护区，未参与本潮汐试验。",
                                    "Gray: protected main-river area, excluded from this tidal experiment."))
    save(fig, "low-high-tide.png")

    fig, axes = plt.subplots(1, 2, figsize=(17, 9), layout="constrained")
    paint(axes[0], before["final_bed_m"], before["water_depth_m"], before_wet, limits,
          label("修改前：年度末床面与实际水体", "Before: annual final bed and saved water"))
    paint(axes[1], bed, arrays["water_depth_m"], wet, limits,
          label("修改后：年度末床面与实际水体", "After: annual final bed and saved water"))
    scene_metadata = json.loads(str(scene["metadata_json"]))
    inflow_direction = np.asarray(scene_metadata["river_direction_xz"], dtype=float)
    inflow_direction /= np.linalg.norm(inflow_direction)
    arrow_start = np.array([.12, .20])
    arrow_end = arrow_start + .14*np.array([inflow_direction[0], -inflow_direction[1]])
    axes[1].annotate("", xy=arrow_end, xytext=arrow_start, xycoords="axes fraction",
                     arrowprops={"arrowstyle": "->", "color": "#202020", "linewidth": 2.})
    axes[1].text(.04, .24, label("原主河方向\n（方向示意，非流速）", "Original main-river direction\n(direction only, not velocity)"),
                 transform=axes[1].transAxes, fontsize=9,
                 bbox={"facecolor": "white", "alpha": .85, "edgecolor": "none"})
    legends(fig, list(axes))
    fig.suptitle(label("新旧岸线：相同窗口、比例与色阶", "Coast comparison: identical window, scale and colors"), fontsize=17)
    fig.supxlabel(note)
    save(fig, "coast-comparison.png")
    metadata = {
        "run": str(run_dir), "before_run": str(before_dir), "tides": str(tides_dir),
        "annual_source_file_sha256": saved["summary"]["file_sha256"],
        "before_source_file_sha256": previous["summary"]["file_sha256"],
        "tide_schema": tide_summary["schema"], "images": images,
        "verified_tide_source_sha256": tide_source_checks,
        "raster_shape": list(shape), "spacing_m": spacing, "origin_xz_m": origin.tolist(),
        "overview_extent_relative_km": limits, "dense_creek_extent_relative_km": zoom,
        "window_method": "Union of tidal shore/creek footprints and distributary envelope; 450 m tidal margin",
        "dense_window_method": "4.2 km window at maximum 3.2 km creek-mask pixel density",
        "coordinate_convention": "Grid centres: columns +x, rows +z; km relative to scene origin; geographic orientation unbound",
        "shared_land_limits_m": [land_norm.vmin, land_norm.vmax],
        "shared_water_depth_limits_m": [0., max_depth],
        "color_limits_method": "Full extrema inside overview window, no percentile clipping",
        "color_normalization": {"type": "PowerNorm", "gamma": .35,
                                "reason": "Resolve shallow creeks while retaining full deep-ocean and land ranges"},
        "interpolation": "nearest", "added_channel_lines": False,
        "original_main_river_direction_arrow_xz": inflow_direction.tolist(),
        "direction_arrow_note": "Single orientation marker in revised comparison panel; not a velocity vector",
        "static_display": "Connected bed-reachable mask and max(tide level - saved bed, 0)",
        "actual_tide_display": "Saved snapshot wet mask and finite snapshot water volume / cell area",
        "tidal_excluded_display": "Neutral gray where tidal_valid_mask is false; protected main-river area excluded from tidal experiment",
        "actual_visible_water_depth_threshold_m": visible_depth,
        "tide_model_note": "Connected finite-water prism model, not 2D momentum simulation",
        "label_language": "zh" if chinese else "en",
    }
    (output / "render-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--tides", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--before", type=Path,
                        default=ROOT / ".scratch/delta-natural-shape-20261031/run-v1")
    args = parser.parse_args()
    print(json.dumps(render(args.run.resolve(), args.tides.resolve(), args.output.resolve(),
                            args.before.resolve()), indent=2))


if __name__ == "__main__":
    main()
