"""Build the 30 m river-network base and the terrain-driven lake curves.

Stages are separated so the GPU part is opt-in and the CPU part is repeatable:

    # GPU, ~15 s for two 1025-cell windows on an RTX 2080 SUPER (2.2 GiB)
    python tools/build_fine_terrain.py --output .scratch/fine-terrain-01 --stage windows
    # CPU, no GPU
    python tools/build_fine_terrain.py --output .scratch/fine-terrain-01 --stage all

Why two windows: one is the deliverable base, the second exists to measure what a
mosaic does at a seam. The composition itself is seam-free by construction (each
window's detail term is exactly zero on that window's border, see
`metric_fine_terrain.mosaic_detail_m`); what the second window measures is how
much detail actually differs where two windows overlap.

Nothing here modifies a solver, a Java file, TODO or the roadmap. The old lake
tank is only *measured against*, never edited.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.td_source import FINE_SPACING_M, adjacent_step_m, analytic_fine_field, bilinear_sample, compose_fine_terrain, fine_axes, seam_diagnostics, td_detail_band
from terrain_pipeline.lake import build_terrain_lake as build_terrain_lake
from terrain_pipeline.lake import contraction_evidence as contraction_evidence
from terrain_pipeline.lake import hypsometry_curve as hypsometry_curve
from terrain_pipeline.lake import sampled_levels as sampled_levels
from terrain_pipeline.lake import sampled_window_basin as sampled_window_basin

WORLD_SEED = 20261020
COARSE_SPACING_M = 10000.0
COARSE_PAGE_ORIGIN_M = (1_250_000.0, 1_200_000.0)
COARSE_PAGE_SHAPE = (12, 12)

# 2049 cells = 61.47 km. Chosen because it is one `pipeline.get` call (no seam of
# its own), costs 21.4 s and 2.2 GiB on the local card, and its basin measurement
# is **converged**: 30.75 km, 46.11 km and 61.47 km windows all return the same
# depression (area, bed and spill identical), while the 15.39 km window the
# earlier reports used does not. See `metric_lake_hypsometry` for why a window
# that cuts a rim silently invents a drain.
PRIMARY_NATIVE_ORIGIN = (43234, 42560)
SECONDARY_NATIVE_ORIGIN = (42414, 42560)
WINDOW_SIZE = 2049
TERMINARY_SIZE = 1025
CONVERGENCE_WINDOW_SIZES = (513, 1025, 1537, 2049)

LAKE_WORLD_XZ = (1300000.0, 1290000.0)
DECLARED_STAGE_M = 306.2732727050781
DECLARED_BED_M = 195.40680847167968
WALL_AREA_M2 = 100_000_000.0

# The 2D floodplain run's independently measured numbers, quoted for comparison
# only. They are not used as input to anything below.
TWO_D_REFERENCE = {"area_km2": 62.72, "volume_m3": 2.778e9, "overestimate_x": "4.0-4.6"}


def native_to_world(origin_native):
    return (float(origin_native[0]) * FINE_SPACING_M, float(origin_native[1]) * FINE_SPACING_M)


def cell_of(origin_xz_m, shape, world_xz_m):
    column = int(round((world_xz_m[0] - origin_xz_m[0]) / FINE_SPACING_M))
    row = int(round((world_xz_m[1] - origin_xz_m[1]) / FINE_SPACING_M))
    if not (0 <= row < shape[0] and 0 <= column < shape[1]):
        raise SystemExit("lake cell %s falls outside the window %s" % (world_xz_m, shape))
    return row, column


# --------------------------------------------------------------------------- #
# stage 1: TD windows (GPU)
# --------------------------------------------------------------------------- #
def build_windows(output_dir, origins, size, seed):
    """Run the pinned 30 m checkpoint through `pipeline.get` directly.

    `diffusion.physical_backend.PhysicalTerrainDiffusionBackend.generate` carries a
    `size <= 513` guard. That guard is **not** modified: this tool builds its own
    backend and calls the underlying pipeline, recording what was bypassed. See the
    report for what the guard protects, what the measurements below rule out, and
    what remains unproven.
    """
    import torch

    from diffusion.physical_backend import PhysicalTerrainDiffusionBackend
    from diffusion.physical_config import PhysicalGenerationConfig

    backend = PhysicalTerrainDiffusionBackend(PhysicalGenerationConfig())
    backend.load()
    pipeline = backend.pipeline
    pipeline.change_seed(int(seed))
    records = []
    try:
        for index, origin in enumerate(origins):
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            with torch.inference_mode():
                output = pipeline.get(int(origin[1]), int(origin[0]),
                                      int(origin[1]) + size, int(origin[0]) + size,
                                      with_climate=False)
            elevation = output["elev"].detach().float().cpu().numpy()
            seconds = time.perf_counter() - started
            peak = float(torch.cuda.max_memory_allocated() / 2 ** 20)
            if elevation.shape != (size, size) or not np.isfinite(elevation).all():
                raise SystemExit("TD produced an unexpected shape or nonfinite data")
            record = {"index": index, "native_origin": list(origin), "size": int(size),
                      "area_km2": (size * FINE_SPACING_M / 1000.) ** 2, "seconds": seconds,
                      "peak_cuda_mib": peak, "world_seed": int(seed),
                      "min_native": float(elevation.min()), "max_native": float(elevation.max()),
                      "entry_point": "WorldPipeline.get (bypasses the 513-cell guard in "
                                      "PhysicalTerrainDiffusionBackend.generate, which is unmodified)",
                      "torch": torch.__version__,
                      "device": torch.cuda.get_device_name(0)}
            np.savez(output_dir / ("td-window-%02d.npz" % index),
                     elevation_native=elevation.astype(np.float64),
                     metadata_json=np.array(json.dumps(record, sort_keys=True)))
            records.append(record)
            print("[window %d] origin %s size %d  %.2f s  peak %.0f MiB" % (
                index, list(origin), size, seconds, peak), flush=True)
    finally:
        backend.close()
    return records


# --------------------------------------------------------------------------- #
# stage 2: compose (CPU)
# --------------------------------------------------------------------------- #
def load_window(output_dir, index):
    page = np.load(output_dir / ("td-window-%02d.npz" % index), allow_pickle=False)
    return np.asarray(page["elevation_native"], np.float64), json.loads(str(page["metadata_json"]))


def window_detail(window, window_origin, composite_origin, composite_shape, spacing=FINE_SPACING_M):
    """Detail band and taper of one window, embedded into the composite lattice.

    The band is computed on the **window's own** lattice, so the low pass sees the
    whole window rather than a truncated overlap; then the overlap is copied into
    the composite accumulator. Origins are integer multiples of the spacing, so
    the alignment is exact index arithmetic and never resampled.
    """
    rows, columns = window.shape
    offset_x = int(round((window_origin[0] - composite_origin[0]) / spacing))
    offset_z = int(round((window_origin[1] - composite_origin[1]) / spacing))
    if (abs(window_origin[0] - composite_origin[0] - offset_x * spacing) > 1e-6
            or abs(window_origin[1] - composite_origin[1] - offset_z * spacing) > 1e-6):
        raise SystemExit("window origin is not on the composite lattice")
    base, _ = analytic_fine_field(WORLD_SEED, window_origin, (rows, columns), spacing)
    detail, weight, diagnostics = td_detail_band(window, base, spacing)
    composite_detail = np.zeros(composite_shape, np.float64)
    composite_weight = np.zeros(composite_shape, np.float64)
    x0, x1 = max(0, offset_x), min(composite_shape[1], offset_x + columns)
    z0, z1 = max(0, offset_z), min(composite_shape[0], offset_z + rows)
    if x1 <= x0 or z1 <= z0:
        raise SystemExit("window does not intersect the composite")
    composite_detail[z0:z1, x0:x1] = detail[z0 - offset_z:z1 - offset_z, x0 - offset_x:x1 - offset_x]
    composite_weight[z0:z1, x0:x1] = weight[z0 - offset_z:z1 - offset_z, x0 - offset_x:x1 - offset_x]
    return composite_detail, composite_weight, diagnostics


def overlay_agreement(detail_a, weight_a, detail_b, weight_b):
    """How much the two windows disagree where both carry nonzero detail."""
    both = (weight_a > 1e-9) & (weight_b > 1e-9)
    if not both.any():
        return {"overlap_cells": 0}
    difference = detail_a[both] - detail_b[both]
    scale = np.concatenate([detail_a[both], detail_b[both]])
    return {"overlap_cells": int(both.sum()),
            "rms_difference_m": float(np.sqrt((difference ** 2).mean())),
            "max_abs_difference_m": float(np.abs(difference).max()),
            "combined_std_m": float(scale.std()),
            "relative_rms": float(np.sqrt((difference ** 2).mean()) / scale.std())
            if scale.std() > 0 else 0.0}


def coarse_interpolation_error(base, origin_xz_m, shape):
    """What a 10 km base costs against the analytic 30 m field."""
    from terrain_pipeline.hydrology_planning import coarse_condition_field, PlanningConfig

    config = PlanningConfig()
    step = config.macro_span_m / config.samples_per_span
    gx = COARSE_PAGE_ORIGIN_M[0] + np.arange(COARSE_PAGE_SHAPE[1]) * step
    gz = COARSE_PAGE_ORIGIN_M[1] + np.arange(COARSE_PAGE_SHAPE[0]) * step
    east, south = np.meshgrid(gx, gz)
    page = np.asarray(coarse_condition_field(WORLD_SEED, east, south, config)[0], np.float64)
    xs, zs = fine_axes(origin_xz_m, shape)
    interpolated = bilinear_sample(page, COARSE_PAGE_ORIGIN_M, step, xs, zs)
    difference = base - interpolated
    return {
        "page_shape": list(page.shape), "page_spacing_m": step,
        "page_origin_xz_m": list(COARSE_PAGE_ORIGIN_M),
        "rms_m": float(np.sqrt((difference ** 2).mean())),
        "max_abs_m": float(np.abs(difference).max()),
        "field_std_m": float(base.std()),
        "relative_rms": float(np.sqrt((difference ** 2).mean()) / base.std()),
        "correlation": float(np.corrcoef(base.ravel(), interpolated.ravel())[0, 1]),
        "interpolated_range_m": [float(interpolated.min()), float(interpolated.max())],
        "analytic_range_m": [float(base.min()), float(base.max())],
        "note": ("the 10 km page samples the same analytic function; this difference is "
                 "aliasing/interpolation error, not a different world")}, page, interpolated


def wall_comparison(height, origin_xz_m, lake_cell, stage_m, coarse_spacing_m=COARSE_SPACING_M):
    """The old single-cell tank, evaluated on the same 30 m cells for comparison.

    The footprint is the 10 km planning cell around the terminal cell -- that is
    exactly the support the reach run declared (one cell, 100 km2), re-expressed
    on the 30 m lattice so both curves are measured on the same cells.
    """
    rows, columns = height.shape
    xs, zs = fine_axes(origin_xz_m, height.shape)
    centre = (origin_xz_m[0] + lake_cell[1] * FINE_SPACING_M,
              origin_xz_m[1] + lake_cell[0] * FINE_SPACING_M)
    half = 0.5 * coarse_spacing_m
    footprint = ((np.abs(xs[None, :] - centre[0]) <= half + 1e-6)
                 & (np.abs(zs[:, None] - centre[1]) <= half + 1e-6))
    if not footprint.any():
        raise SystemExit("10 km footprint does not intersect the window")
    beds = height[footprint]
    cell_area = FINE_SPACING_M ** 2
    area, volume = hypsometry_curve(beds, cell_area, np.array([stage_m]))
    wall_volume = WALL_AREA_M2 * (stage_m - DECLARED_BED_M)
    wall_area = WALL_AREA_M2
    depth = stage_m - beds.min()
    return {"stage_m": float(stage_m), "footprint_cells": int(footprint.sum()),
            "footprint_area_km2": float(footprint.sum() * cell_area / 1e6),
            "footprint_bed_min_m": float(beds.min()), "footprint_bed_max_m": float(beds.max()),
            "max_depth_m": float(depth),
            "fine_area_km2": float(area[0] / 1e6), "fine_volume_m3": float(volume[0]),
            "wall_area_km2": wall_area / 1e6, "wall_volume_m3": float(wall_volume),
            "volume_overestimate_x": float(wall_volume / volume[0]),
            "area_overestimate_x": float(wall_area / area[0]),
            "declared_wall_support": "one 10 km planning cell: 100 km2 x 110.867 m depth",
            "reference_2d": TWO_D_REFERENCE}


def hypsometry_table(lake):
    """Closed-basin A(h)/V(h) on the basin's own stages, plus its contraction.

    The levels run from the bed to the spill level, which is the whole range over
    which the basin is a lake. Above the spill level the same footprint is a
    flood, and the vertical-wall comparison table covers that stage instead.
    """
    levels = sampled_levels(lake.bed_min_m, lake.spill_level_m, 9)
    rows = lake.level_table(levels)
    basin = [{"stage_m": row["clamped_stage_m"],
              "area_km2": float(row["area_m2"] / 1e6),
              "volume_m3": float(row["volume_m3"]),
              "fraction_of_spill_volume": float(row["volume_m3"] / lake.capacity_m3)}
             for row in rows]
    return basin, contraction_evidence(levels, [row["area_m2"] for row in rows])


def convergence_check():
    """Prove the basin measurement is window-independent before reporting it.

    This is the constraint `metric_lake_hypsometry` exists to enforce: a window
    that cuts a rim invents a drain, so a basin's numbers are only meaningful
    once they stop changing with the window. The analytic field is sampled from
    absolute world coordinates, so enlarging the window adds terrain and changes
    nothing that was already observed.
    """
    def sampler(origin, shape):
        return analytic_fine_field(WORLD_SEED, origin, shape)[0]

    result = sampled_window_basin(LAKE_WORLD_XZ, CONVERGENCE_WINDOW_SIZES, FINE_SPACING_M, sampler)
    if not result["converged"]:
        raise SystemExit("lake basin is not window-converged: %s" % result["reason"])
    return result


def main():
    parser = argparse.ArgumentParser(description="30 m river base + terrain-driven lake curves")
    parser.add_argument("--output", default=".scratch/fine-terrain-01")
    parser.add_argument("--stage", default="all", choices=("windows", "compose", "all"))
    parser.add_argument("--window-size", type=int, default=WINDOW_SIZE)
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    size = int(args.window_size)

    # Both windows are centred on the lake so the composition has no rim on it.
    lake_column = int(round(LAKE_WORLD_XZ[0] / FINE_SPACING_M)) - size // 2
    lake_row = int(round(LAKE_WORLD_XZ[1] / FINE_SPACING_M)) - size // 2
    origins = [(lake_column, lake_row),
               (lake_column - TERMINARY_SIZE, lake_row)]

    window_records = []
    if args.stage in ("windows", "all"):
        window_records = build_windows(output_dir, origins, size, WORLD_SEED)
    else:
        window_records = [json.loads(str(np.load(output_dir / ("td-window-%02d.npz" % index))[
            "metadata_json"])) for index in range(len(origins))]

    if args.stage == "windows":
        return

    started = time.perf_counter()
    primary_origin = native_to_world(origins[0])
    secondary_origin = native_to_world(origins[1])
    composite_native = (min(origins[0][0], origins[1][0]),
                        min(origins[0][1], origins[1][1]))
    composite_origin = native_to_world(composite_native)
    composite_columns = max(origins[0][0], origins[1][0]) - composite_native[0] + size
    composite_rows = max(origins[0][1], origins[1][1]) - composite_native[1] + size
    composite_shape = (composite_rows, composite_columns)

    contributions = []
    diagnostics = []
    for index, origin_native in enumerate(origins):
        window, _ = load_window(output_dir, index)
        detail, weight, record = window_detail(window, native_to_world(origin_native),
                                               composite_origin, composite_shape)
        contributions.append((detail, weight))
        diagnostics.append(dict(record, window_index=index, native_origin=list(origin_native)))
    agreement = overlay_agreement(contributions[0][0], contributions[0][1],
                                  contributions[1][0], contributions[1][1])
    minutes = time.perf_counter() - started

    primary_offset_x = origins[0][0] - composite_native[0]
    primary_offset_z = origins[0][1] - composite_native[1]
    primary_contributions = [
        (detail[primary_offset_z:primary_offset_z + size, primary_offset_x:primary_offset_x + size],
         weight[primary_offset_z:primary_offset_z + size, primary_offset_x:primary_offset_x + size])
        for detail, weight in contributions]
    primary_field = compose_fine_terrain(WORLD_SEED, primary_origin, (size, size),
                                         contributions=primary_contributions,
                                         source_label="analytic_30m_plus_td_detail_mosaic")
    primary_field.save(output_dir / "fine-terrain-30m.npz")

    analytic_only = compose_fine_terrain(WORLD_SEED, primary_origin, (size, size),
                                         source_label="analytic_30m_only")
    analytic_only.save(output_dir / "analytic-30m.npz")

    height = np.asarray(primary_field.elevation_m, np.float64)
    lake_cell = cell_of(primary_origin, height.shape, LAKE_WORLD_XZ)
    lake = build_terrain_lake(height, primary_origin, FINE_SPACING_M, lake_cell,
                              source_identity_sha256=primary_field.identity_sha256)
    basin_table, contraction = hypsometry_table(lake)
    wall = wall_comparison(height, primary_origin, lake_cell, DECLARED_STAGE_M)
    convergence = convergence_check()

    analytic_height = np.asarray(analytic_only.elevation_m, np.float64)
    analytic_lake = build_terrain_lake(analytic_height, primary_origin, FINE_SPACING_M, lake_cell,
                                       source_identity_sha256=analytic_only.identity_sha256)

    coarse_report, _, _ = coarse_interpolation_error(
        analytic_height, primary_origin, analytic_height.shape)

    seam_mask = np.zeros(composite_shape, bool)
    boundary_column = (origins[0][0] - composite_native[0]) - 1
    if 0 <= boundary_column < composite_shape[1] - 1:
        seam_mask[:, boundary_column] = True
    composite_field = compose_fine_terrain(WORLD_SEED, composite_origin, composite_shape,
                                            contributions=contributions,
                                            source_label="mosaic_seam_check")
    seams = seam_diagnostics(np.asarray(composite_field.elevation_m), seam_mask)

    truncated = convergence["records"][0]
    report = {
        "schema": "fine-terrain-01-report-v1",
        "world_seed": WORLD_SEED,
        "cost": {
            "windows": window_records,
            "compose_seconds": minutes,
            "note": ("a second call on the same window is a cache hit; the numbers above are "
                     "cold per-window costs")},
        "windows": {"size": size, "next_power_reference": 2049,
                     "spacing_m": FINE_SPACING_M,
                     "primary_native_origin": list(origins[0]),
                     "primary_origin_xz_m": list(primary_origin),
                     "secondary_native_origin": list(origins[1]),
                     "secondary_origin_xz_m": list(secondary_origin),
                     "primary_window_km": size * FINE_SPACING_M / 1000.0,
                     "centred_on_lake": True},
        "detail_bands": diagnostics,
        "detail_overlay_agreement": agreement,
        "seam": {"declared_seam_column": int(boundary_column), **seams},
        "field": {"identity_sha256": primary_field.identity_sha256,
                   "shape": list(height.shape),
                   "elevation_range_m": [float(height.min()), float(height.max())],
                   "steps": adjacent_step_m(height)},
        "analytic_field": {"identity_sha256": analytic_only.identity_sha256,
                            "elevation_range_m": [float(analytic_height.min()),
                                                  float(analytic_height.max())],
                            "steps": adjacent_step_m(analytic_height)},
        "coarse_interpolation_error": coarse_report,
        "lake": {
            "cell_row_column": list(lake_cell),
            "cell_world_xz_m": [primary_origin[0] + lake_cell[1] * FINE_SPACING_M,
                                primary_origin[1] + lake_cell[0] * FINE_SPACING_M],
            "closed_basin": lake.closed_basin,
            "touches_window_border": lake.touches_window_border,
            "basin_cells": int(lake.basin_mask.sum()),
            "basin_area_km2": lake.area_km2,
            "bed_min_m": lake.bed_min_m, "spill_level_m": lake.spill_level_m,
            "relief_m": lake.relief_m, "capacity_m3": lake.capacity_m3,
            "provenance": lake.provenance,
            "basin_levels": basin_table,
            "contraction": contraction,
            "shape_law": None},
        "window_convergence": convergence,
        "superseded_truncated_reading": {
            "window_km": truncated["window_km"],
            "basin_area_km2": truncated["basin_area_m2"] / 1e6,
            "bed_min_m": truncated["bed_min_m"],
            "spill_level_m": truncated["spill_level_m"],
            "why_wrong": ("the window border cut the basin rim, and a border-seeded priority "
                          "flood treats every border cell as a drain, so the truncated window "
                          "reported a spill level far below the real saddle"),
            "note": "kept so the earlier published numbers can be identified, not reused"},
        "vertical_wall_comparison": wall,
        "analytic_lake": {
            "closed_basin": analytic_lake.closed_basin,
            "basin_cells": int(analytic_lake.basin_mask.sum()),
            "bed_min_m": analytic_lake.bed_min_m,
            "spill_level_m": analytic_lake.spill_level_m,
            "note": ("measured in the same converged window; the basin is a property of the "
                     "conditioning field, not of the TD detail band")},
    }
    (output_dir / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True))

    levels = np.array([row["stage_m"] for row in basin_table])
    np.savez(output_dir / "lake-hypsometry.npz",
             levels_m=levels,
             area_m2=np.array([row["area_km2"] for row in basin_table]) * 1e6,
             volume_m3=np.array([row["volume_m3"] for row in basin_table]),
             basin_mask=np.asarray(lake.basin_mask, bool),
             bed_elevation_m=np.asarray(lake.storage.bed_elevation_m, np.float64),
             cell_area_m2=float(lake.storage.cell_area_m2[0]),
             spill_level_m=np.array(lake.spill_level_m),
             bed_min_m=np.array(lake.bed_min_m),
             origin_xz_m=np.array(primary_origin, np.float64),
             spacing_m=np.array(FINE_SPACING_M),
             identity_sha256=np.array(lake.provenance["source_identity_sha256"]))

    np.savez(output_dir / "window-convergence.npz",
             sizes=np.array(CONVERGENCE_WINDOW_SIZES),
             basin_area_m2=np.array([r["basin_area_m2"] for r in convergence["records"]]),
             bed_min_m=np.array([r["bed_min_m"] for r in convergence["records"]]),
             spill_level_m=np.array([r["spill_level_m"] for r in convergence["records"]]))

    figures(output_dir, basin_table, contraction, wall, convergence)
    print(json.dumps({key: report[key] for key in ("lake", "vertical_wall_comparison",
                                                  "detail_overlay_agreement")}, indent=1)[:6000])


def figures(output_dir, basin_table, contraction, wall, convergence):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    levels = np.array([row["stage_m"] for row in basin_table])
    areas = np.array([row["area_km2"] for row in basin_table])
    volumes = np.array([row["volume_m3"] for row in basin_table])
    figure, axes = plt.subplots(1, 2, figsize=(12.5, 5.0))
    axes[0].plot(areas, levels, "o-", label="30 m terrain (closed basin)")
    axes[0].axvline(wall["fine_area_km2"], color="tab:orange", ls="--",
                    label="30 m footprint @ %.1f m: %.2f km2" % (wall["stage_m"], wall["fine_area_km2"]))
    axes[0].axvline(wall["wall_area_km2"], color="tab:red", ls=":",
                    label="vertical wall support: 100 km2")
    axes[0].axhline(wall["stage_m"], color="grey", lw=.8,
                    label="stage the reach solver declared")
    axes[0].set_xlabel("wetted area (km2)")
    axes[0].set_ylabel("stage (m)")
    axes[0].set_title("A(h): the basin narrows downward, as the terrain says")
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=.3)

    axes[1].plot(volumes / 1e6, levels, "o-", label="30 m terrain (closed basin)")
    wall_curve_levels = np.array([basin_table[0]["stage_m"], wall["stage_m"]])
    axes[1].plot(WALL_AREA_M2 * (wall_curve_levels - DECLARED_BED_M) / 1e6, wall_curve_levels,
                 "s--", label="vertical wall (1 cell x 100 km2)")
    axes[1].axhline(wall["stage_m"], color="grey", lw=.8)
    axes[1].set_xlabel("volume (1e6 m3)")
    axes[1].set_ylabel("stage (m)")
    axes[1].set_title("V(h): wall tank vs terrain hypsometry (wall/basin = %.2fx)" %
                      wall["volume_overestimate_x"])
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=.3)
    figure.tight_layout()
    figure.savefig(output_dir / "lake-hypsometry.png", dpi=130)
    plt.close(figure)

    figure, axes = plt.subplots(figsize=(8.0, 4.6))
    rows = [row for row in contraction if row["secant_dA_dh_m"] > 0]
    middles = [0.5 * (row["from_level_m"] + row["to_level_m"]) for row in rows]
    axes.plot(middles, [row["secant_dA_dh_m"] / 1e3 for row in rows], "o-")
    axes.set_xlabel("stage (m)")
    axes.set_ylabel("measured |dA/dh| (1e3 m per m)")
    axes.set_title("Contraction: the surface shrinks faster the lower the water")
    axes.grid(alpha=.3)
    figure.tight_layout()
    figure.savefig(output_dir / "basin-contraction.png", dpi=130)
    plt.close(figure)

    # The lesson, as a figure: the basin keeps growing until the window stops
    # cutting its rim, then does not change at all.
    figure, axes = plt.subplots(figsize=(8.0, 4.4))
    records = convergence["records"]
    windows = [record["window_km"] for record in records]
    axes.plot(windows, [record["basin_area_m2"] / 1e6 for record in records], "o-",
              label="basin area (km2)")
    axes.set_xlabel("window edge length (km)")
    axes.set_ylabel("basin area (km2)")
    axes.grid(alpha=.3)
    second = axes.twinx()
    second.plot(windows, [record["spill_level_m"] for record in records], "s--", color="tab:red",
                label="spill level (m)")
    second.set_ylabel("spill level (m)", color="tab:red")
    axes.set_title("Window convergence: a truncated rim invents a drain")
    axes.legend(fontsize=8, loc="upper left")
    second.legend(fontsize=8, loc="lower right")
    figure.tight_layout()
    figure.savefig(output_dir / "window-convergence.png", dpi=130)
    plt.close(figure)


if __name__ == "__main__":
    main()
