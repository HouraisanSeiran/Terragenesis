"""Read saved native beds and water separately; measure finite natural growth."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_propagation, label

DRY_M = 2.e-6
DEPOSITION_M = 1.e-4


def load(directory):
    report = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    with np.load(directory / "result.npz") as saved:
        arrays = {name: saved[name] for name in saved.files}
    return report, arrays


def render_source_context(annual_report, growth_report, arrays, output):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon

    source = annual_report["terrain_initialization"]
    scene = Path(source["source_scene"])
    if hashlib.sha256(scene.read_bytes()).hexdigest() != source["source_sha256"]:
        raise ValueError("original TD source scene differs from annual parent provenance")
    with np.load(scene) as saved:
        base = saved["base_bed_m"].copy()
        metadata = json.loads(str(saved["metadata_json"]))
    world = arrays["local_world_xz_m"]
    across = world[0, 1] - world[0, 0]
    downstream = world[1, 0] - world[0, 0]
    footprint = np.asarray([world[0, 0] - .5 * across - .5 * downstream,
        world[0, -1] + .5 * across - .5 * downstream,
        world[-1, -1] + .5 * across + .5 * downstream,
        world[-1, 0] - .5 * across + .5 * downstream])
    spacing = float(metadata["spacing_m"])
    origin = np.asarray(metadata["origin_xz_m"])
    source_x = origin[0] + np.arange(base.shape[1]) * spacing
    source_z = origin[1] + np.arange(base.shape[0]) * spacing
    extent = [(source_x[0] - spacing / 2.) / 1000., (source_x[-1] + spacing / 2.) / 1000.,
        (source_z[0] - spacing / 2.) / 1000., (source_z[-1] + spacing / 2.) / 1000.]
    fig, axes = plt.subplots(1, 2, figsize=(14, 8), constrained_layout=True, gridspec_kw={"width_ratios": [1.3, 1.]})
    low, high = np.percentile(base, [.5, 99.5])
    background = axes[0].imshow(base, extent=extent, origin="lower", cmap="terrain", vmin=low, vmax=high)
    if base.min() < 0. < base.max():
        axes[0].contour(source_x / 1000., source_z / 1000., base, levels=[0.], colors="#33494d", linewidths=.6)
    axes[0].add_patch(Polygon(footprint / 1000., closed=True, fill=False, edgecolor="#d72b65", linewidth=1.6))
    center = footprint.mean(axis=0) / 1000.
    axes[0].annotate("600 x 800 m actual simulation", xy=center, xytext=(18, 30), textcoords="offset points",
        fontsize=9, color="#9d1749", arrowprops={"arrowstyle": "->", "color": "#9d1749"},
        bbox={"facecolor": "white", "alpha": .85, "edgecolor": "none"})
    axes[0].set_title("Unchanged scene15 base_bed_m source background")
    axes[0].set_xlabel("World x (km)")
    axes[0].set_ylabel("World z (km)")
    fig.colorbar(background, ax=axes[0], shrink=.65, label="Source bed elevation (m)", extend="both")
    bed = arrays["bed_m"][-1]
    detail = axes[1].pcolormesh(world[..., 0], world[..., 1], bed, shading="nearest", cmap="terrain", vmin=-1.5, vmax=1.5)
    levels = [v for v in np.arange(-1.5, 1.51, .25) if bed.min() < v < bed.max()]
    if levels:
        axes[1].contour(world[..., 0], world[..., 1], bed, levels=levels, colors="#555555", linewidths=.4)
    if bed.min() < 0. < bed.max():
        axes[1].contour(world[..., 0], world[..., 1], bed, levels=[0.], colors="#a32038", linewidths=1.)
    axes[1].add_patch(Polygon(footprint, closed=True, fill=False, edgecolor="#d72b65", linewidth=1.2))
    axes[1].set_title(f"Actual local final bed: {growth_report['steps']} new packets\nWorld coordinates; red contour = bed zero datum")
    axes[1].set_xlabel("World x (m)")
    axes[1].set_ylabel("World z (m)")
    axes[1].ticklabel_format(style="plain", useOffset=False)
    fig.colorbar(detail, ax=axes[1], shrink=.65, label="Local bed elevation (m)", extend="both")
    for ax in axes:
        ax.set_aspect("equal")
    annual_solid = float(annual_report["ledger_bulk_m3"]["injected_bulk_m3"]) * (1. - annual_report["config"]["porosity"])
    new_solid = float(arrays["cumulative_new_input_solid_m3"][-1])
    mechanism_time = float(arrays["time_s"][-1])
    fig.suptitle("16 km source context; natural simulation covers only 600 x 800 m at 5 m spacing\n"
        f"Actual finite solid delivered: original {annual_solid:,.1f} + new {new_solid:,.1f} m3; "
        f"cumulative mechanism time {mechanism_time / 86400.:.3f} days\n"
        "Local bed only; source extent is not delta diameter. No 16 km hydrodynamics or seam certification.", fontsize=11)
    fig.savefig(output / "natural-growth-16km-source-context.png", dpi=180)
    plt.close(fig)
    return {"source_scene": str(scene), "source_scene_sha256": source["source_sha256"], "source_field": "base_bed_m",
        "source_grid_spacing_m": spacing, "local_world_footprint_corners_xz_m": footprint.tolist(),
        "actual_local_spacing_m": float(np.linalg.norm(across)), "actual_original_delivered_solid_m3": annual_solid,
        "actual_new_delivered_solid_m3": new_solid, "cumulative_mechanism_time_s": mechanism_time,
        "rendering": "unchanged source background plus exact local polygon and local bed in world coordinates; no resampling or constructed scene bed",
        "scope": "600x800m local natural simulation only; no full-scene hydraulics, delta-diameter interpretation, or seam certification"}


def measure(arrays, initial, previous, dx, porosity):
    bed = arrays["bed_m"][-1].astype(float)
    depth = arrays["depth_m"][-1]
    area = dx ** 2
    eligible = arrays["cell_type"] == 0
    land = (initial >= 0.) & eligible
    sea = (initial < 0.) & eligible
    dry = depth <= DRY_M
    geometric = bed >= 0.
    connected = binary_propagation(land & geometric, mask=geometric & eligible)
    dry_connected = binary_propagation(land & dry, mask=dry & eligible)
    change = bed - initial
    increment = bed - previous
    count = min(5, len(arrays["bed_m"]))
    persistent_dry = np.all(arrays["depth_m"][-count:] <= DRY_M, axis=0)
    persistent_high = np.all(arrays["bed_m"][-count:] >= 0., axis=0)
    persistent_link = binary_propagation(land & persistent_dry, mask=persistent_dry & eligible)
    metrics = {"original_land_deposition_area_m2": float(np.sum(land & (change > DEPOSITION_M)) * area),
        "original_land_positive_deposition_bulk_m3": float(np.maximum(change, 0.)[land].sum() * area),
        "original_land_net_bed_change_bulk_m3": float(change[land].sum() * area),
        "original_sea_positive_deposition_bulk_m3": float(np.maximum(change, 0.)[sea].sum() * area),
        "original_sea_raised_bed_area_m2": float(np.sum(sea & (change > DEPOSITION_M)) * area),
        "original_sea_maximum_bed_rise_m": float(change[sea].max()),
        "original_sea_net_bed_change_bulk_m3": float(change[sea].sum() * area),
        "incremental_positive_deposition_bulk_m3": float(np.maximum(increment, 0.)[eligible].sum() * area),
        "incremental_net_bed_change_bulk_m3": float(increment[eligible].sum() * area),
        "original_sea_final_bed_range_m": [float(bed[sea].min()), float(bed[sea].max())],
        "original_sea_above_zero_area_m2": float(np.sum(sea & geometric) * area),
        "original_sea_above_zero_connected_area_m2": float(np.sum(sea & connected) * area),
        "original_sea_actual_dry_area_m2": float(np.sum(sea & dry) * area),
        "original_sea_actual_dry_connected_area_m2": float(np.sum(sea & dry_connected) * area),
        "original_sea_persistent_dry_connected_area_m2": float(np.sum(sea & persistent_link) * area),
        "persistent_last_saved_frames": count, "porosity": porosity}
    metrics["original_land_positive_deposition_solid_m3"] = metrics["original_land_positive_deposition_bulk_m3"] * (1. - porosity)
    sections = []
    for downstream in np.arange(75., min(400., bed.shape[0] * dx), 25.):
        row = min(int(downstream / dx), bed.shape[0] - 1)
        forward = np.maximum(arrays["qx_m2_s"][-1, row], 0.) * dx
        total = float(forward.sum())
        active = (depth[row] > DRY_M) & (forward > .05 * max(float(forward.max()), 1.e-12)) & eligible[row]
        groups, n = label(active)
        bands = []
        for group in range(1, n + 1):
            cells = np.flatnonzero(groups == group)
            fraction = float(forward[cells].sum() / total) if total else 0.
            if fraction >= .1:
                bands.append({"columns": [int(cells[0]), int(cells[-1])], "positive_flux_fraction": fraction,
                    "cross_stream_range_m": [(float(cells[0]) - bed.shape[1] / 2.) * dx,
                        (float(cells[-1] + 1) - bed.shape[1] / 2.) * dx]})
        separators = []
        for left, right in zip(bands, bands[1:]):
            cols = slice(left["columns"][1] + 1, right["columns"][0])
            gap = bed[row, cols]
            left_cols = slice(left["columns"][0], left["columns"][1] + 1)
            right_cols = slice(right["columns"][0], right["columns"][1] + 1)
            channel_level = max(float(bed[row, left_cols].min()), float(bed[row, right_cols].min()))
            separators.append({"width_m": len(gap) * dx, "max_bed_relief_above_adjacent_band_minima_m": float(gap.max() - channel_level),
                "all_gap_cells_actually_dry": bool(np.all(dry[row, cols])),
                "all_gap_cells_persistently_dry_and_above_zero": bool(np.all(persistent_dry[row, cols] & persistent_high[row, cols]))})
        sections.append({"downstream_m": (row + .5) * dx, "positive_discharge_m3_s": total,
            "flow_bands": bands, "bed_bank_separators": separators})
    metrics["cross_sections"] = sections
    metrics["sustained_distributaries_accepted"] = False
    metrics["branch_interpretation"] = "Flow bands and cross-section bed-bank separators are evidence only; no connected, sustained distributary topology is inferred."
    return metrics


def run(annual, growth, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    annual_report, a = load(annual)
    growth_report, b = load(growth)
    dx = annual_report["config"]["dx_m"]
    if dx != growth_report["config"]["dx_m"]:
        raise ValueError("different native grid spacing")
    initial = a["initial_bed_m"]
    np.testing.assert_array_equal(initial, b["initial_bed_m"])
    np.testing.assert_array_equal(a["bed_m"][-1], b["bed_m"][0])
    np.testing.assert_array_equal(a["source_floor_m"], b["source_floor_m"])
    output.mkdir(parents=True, exist_ok=True)
    shape = initial.shape
    width, length = shape[1] * dx, shape[0] * dx
    extent = [-width / 2., width / 2., length, 0.]
    xx, zz = np.meshgrid((np.arange(shape[1]) + .5) * dx - width / 2., (np.arange(shape[0]) + .5) * dx)
    beds = [initial, a["bed_m"][-1], b["bed_m"][-1]]
    depths = [a["depth_m"][0], a["depth_m"][-1], b["depth_m"][-1]]
    fluxes = [(a["qz_m2_s"][0], a["qx_m2_s"][0]), (a["qz_m2_s"][-1], a["qx_m2_s"][-1]),
        (b["qz_m2_s"][-1], b["qx_m2_s"][-1])]
    titles = ["Initial macro + TD residual bed", "Original annual finite deposition",
        f"New finite +9 m source continuation\n{growth_report['steps']} packets completed"]
    eligible = a["cell_type"] == 0
    flux_reference = max(float(np.percentile(np.hypot(*flux)[eligible], 95)) for flux in fluxes)
    flux_reference = max(flux_reference, .01)
    # A common physical reference keeps arrows comparable; long vectors are capped visually.
    arrow_scale = flux_reference / 20.

    def contours(ax, field, levels, color, width=.65):
        levels = [v for v in levels if field.min() < v < field.max()]
        if levels:
            ax.contour(xx, zz, field, levels=levels, colors=color, linewidths=width)

    def finish(ax, zoom):
        ax.set_xlim((-300., 300.) if zoom else (-width / 2., width / 2.))
        ax.set_ylim((350., 0.) if zoom else (length, 0.))
        ax.set_aspect("equal")
        ax.set_xlabel("Cross-stream (m)")
        ax.set_ylabel("Downstream (m)")

    for kind in ("bed", "water"):
        fig, axes = plt.subplots(2, 3, figsize=(16, 12), constrained_layout=True)
        for col, (bed, depth, flux, title) in enumerate(zip(beds, depths, fluxes, titles)):
            for row in range(2):
                ax = axes[row, col]
                if kind == "bed":
                    image = ax.imshow(bed, extent=extent, cmap="terrain", vmin=-1.5, vmax=1.5)
                    contours(ax, bed, np.arange(-1.5, 1.51, .25), "#555555", .45)
                    contours(ax, bed, [0.], "#a32038", 1.2)
                else:
                    ax.imshow(bed, extent=extent, cmap="Greys", vmin=-1.5, vmax=1.5)
                    image = ax.imshow(np.where(depth > DRY_M, depth, np.nan), extent=extent, cmap="YlGnBu", vmin=0.,
                        vmax=max(1., float(np.percentile(np.concatenate([h.ravel() for h in depths]), 98))))
                    contours(ax, depth, [DRY_M], "#df7f16", 1.)
                    contours(ax, bed, [0.], "#a32038", .7)
                    pick = (slice(4, None, 8), slice(4, None, 8))
                    qx, qz = flux
                    magnitude = np.hypot(qx, qz)
                    factor = np.minimum(1., flux_reference * 1.5 / np.maximum(magnitude, 1.e-12))
                    wet = depth > DRY_M
                    arrows = ax.quiver(xx[pick], zz[pick], np.where(wet, qx * factor, 0.)[pick],
                        np.where(wet, qz * factor, 0.)[pick], angles="xy", scale_units="xy", scale=arrow_scale,
                        color="#a1244e", width=.003)
                    if row == 0 and col == 2:
                        key = ax.quiverkey(arrows, .60, .88, flux_reference, f"{flux_reference:.2g} m2/s", labelpos="E")
                        key.text.set_bbox({"facecolor": "white", "alpha": .8, "edgecolor": "none"})
                finish(ax, row == 1)
                ax.set_title(title if row == 0 else "600 x 350 m mouth detail")
        label_text = "Bed elevation (m); red = zero datum; grey contours every 0.25 m" if kind == "bed" else "Actual native water depth (m); orange = wet/dry edge; red = bed zero datum"
        fig.colorbar(image, ax=axes, shrink=.7, label=label_text)
        fig.savefig(output / f"natural-growth-{kind}.png", dpi=165)
        plt.close(fig)

    changes = [beds[1] - initial, beds[2] - beds[1], beds[2] - initial]
    limit = max(float(np.max(np.abs(field))) for field in changes)
    fig, axes = plt.subplots(2, 3, figsize=(16, 12), constrained_layout=True)
    for col, (field, title) in enumerate(zip(changes, ["Annual minus original", "New continuation minus annual", "Continuation minus original"])):
        for row in range(2):
            ax = axes[row, col]
            image = ax.imshow(field, extent=extent, cmap="RdBu_r", norm=TwoSlopeNorm(0., -max(limit, .01), max(limit, .01)))
            contours(ax, beds[1 if col == 0 else 2], [0.], "black", .7)
            finish(ax, row == 1)
            ax.set_title(title if row == 0 else "600 x 350 m mouth detail")
    fig.colorbar(image, ax=axes, shrink=.7, label="Measured bed change (m); black = final bed zero datum")
    fig.savefig(output / "natural-growth-bed-change.png", dpi=165)
    plt.close(fig)
    report = {"annual": str(annual), "growth": str(growth), "growth_steps": growth_report["steps"],
        "source_context": render_source_context(annual_report, growth_report, b, output),
        "growth_remaining_source_solid_m3": growth_report.get("remaining_new_source_solid_m3"),
        "annual_measurements": measure(a, initial, initial, dx, annual_report["config"]["porosity"]),
        "growth_measurements": measure(b, initial, beds[1], dx, growth_report["config"]["porosity"]),
        "dry_threshold_m": DRY_M, "deposition_area_threshold_m": DEPOSITION_M,
        "full_domain_cross_stream_by_downstream_m": [width, length], "detail_domain_cross_stream_by_downstream_m": [600., 350.],
        "measurement_mask": "mutable cell_type == 0 only; original land >= zero, original sea < zero",
        "native_vector_axes": "saved qz_m2_s -> horizontal cross-stream; saved qx_m2_s -> vertical downstream",
        "arrow_reference_m2_s": flux_reference, "arrow_reference_length_m": 20., "arrow_maximum_display_length_m": 30.,
        "bed_color_range_m": [-1.5, 1.5], "bed_color_saturation": "colour clips outside range; contours and measurements use actual bed",
        "chronology": "native sediment-bearing mechanism steps; no annual-water or permanent tidal-exposure claim",
        "figures": ["natural-growth-bed.png", "natural-growth-water.png", "natural-growth-bed-change.png", "natural-growth-16km-source-context.png"]}
    (output / "measurements.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {key: value for key, value in report.items() if not key.endswith("measurements")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annual", type=Path, required=True)
    parser.add_argument("--growth", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.annual, args.growth, args.output), indent=2))
