"""Construct one independent scene from the accepted frozen coastal inputs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_variable] = "1"

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_coast_bounded_delta import construct_coast_bounded_scene
from tools.run_integrated_delta import SCENE, SOURCE
from tools.verify_fluvial_channel_remobilization import resource_limits


def inspect_scene(output: Path, compare_scene: Path | None = None):
    """Inspect saved rasters and render actual terrain without candidate lines."""
    resource_limits()
    from scipy.ndimage import label
    from scipy.spatial import cKDTree
    from terrain_pipeline.surface_rivers.metric_coast_bounded_delta import path_station, sample_path
    from tools.run_integrated_delta import connected_water_diagnostics, load_scene
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource, LinearSegmentedColormap

    output = Path(output)
    with np.load(output/"scene.npz") as data:
        a = {key: data[key].copy() for key in data.files if key != "metadata_json"}
        meta = json.loads(data["metadata_json"].item())
    with np.load(meta["source_scene_path"]) as data:
        old = {key: data[key].copy() for key in ("bed_m", "branch_cut_depth_m")}
    origin, spacing = np.asarray(meta["origin_xz_m"]), float(meta["spacing_m"])
    bed, marine, prebed = a["bed_m"], a["open_marine_mask"], a["pre_channel_bed_m"]
    entry_checks = []
    for path in a["branch_paths_xz_m"]:
        s = path_station(path)
        dense = sample_path(path, s, np.linspace(0., s[-1], int(np.ceil(s[-1]/(spacing/4.)))+1))
        cells = np.floor((dense-origin)/spacing+.5).astype(int)
        hits = marine[cells[:, 1], cells[:, 0]]
        entry_checks.append(bool(not hits[:-1].any() and hits[-1]))
    protected_paths_marine = []
    for path in (a["designed_incoming_path_xz_m"], a["trunk_path_xz_m"]):
        s = path_station(path)
        dense = sample_path(path, s, np.linspace(0., s[-1], int(np.ceil(s[-1]/(spacing/4.)))+1))
        cells = np.floor((dense-origin)/spacing+.5).astype(int)
        inside = (cells[:, 0] >= 0) & (cells[:, 0] < bed.shape[1]) & (cells[:, 1] >= 0) & (cells[:, 1] < bed.shape[0])
        cells = cells[inside]
        protected_paths_marine.append(int(np.count_nonzero(marine[cells[:, 1], cells[:, 0]])))
    wet = a["wet_mask"]
    connectivity = connected_water_diagnostics(load_scene(output/"scene.npz"), wet)
    wet_labels, _ = label(wet)
    retained = a["retained_upstream_raster_mask"]
    removed = a["old_branch_groove_removed_mask"]
    old_path = a["branch_candidate_paths_xz_m"][0]
    old_station = path_station(old_path)
    rr, cc = np.nonzero(old["branch_cut_depth_m"][0] > 0.)
    nearest = cKDTree(old_path).query(origin+np.column_stack([cc, rr])*spacing, workers=1)[1]
    old_island = np.zeros_like(removed)
    island_station = (old_station[nearest] >= 4343.6) & (old_station[nearest] <= 5279.5)
    old_island[rr[island_station], cc[island_station]] = True
    new_sections = a["main_section_mask"] | a["trunk_section_mask"] | np.any(a["branch_section_masks"], axis=0)
    # Only old distal land grooves, beyond the first-entry planes, are at issue.
    old_distal = removed & (a["branch_cut_depth_m"].sum(axis=0) == 0.) & (prebed > 0.)
    delta = bed-a["base_bed_m"]
    cut = float(np.maximum(-delta, 0.).sum()*spacing**2)
    fill = float(np.maximum(delta, 0.).sum()*spacing**2)
    net = float(delta.sum()*spacing**2)
    audit = {"branch_only_terminal_is_marine": entry_checks,
        "incoming_and_trunk_marine_samples": protected_paths_marine,
        "marine_bed_exact": bool(np.array_equal(bed[marine], prebed[marine])),
        "marine_channel_cut_bulk_m3": float(np.maximum(prebed-bed, 0.)[marine].sum()*spacing**2),
        "retained_upstream_exact": bool(np.array_equal(bed[retained], old["bed_m"][retained])),
        "old_groove_removed_cells": int(removed.sum()),
        "old_removed_groove_exact_prechannel_cells": int(np.count_nonzero(removed & (bed == prebed))),
        "old_removed_groove_matches_prechannel": bool(np.array_equal(bed[removed], prebed[removed])),
        "old_branch0_island_station_interval_m": [4343.6, 5279.5],
        "old_branch0_island_groove_cells": int(old_island.sum()),
        "old_branch0_island_groove_exact_prechannel_cells": int(np.count_nonzero(old_island & (bed == prebed))),
        "old_branch0_island_groove_matches_prechannel": bool(np.array_equal(bed[old_island], prebed[old_island])),
        "channel_section_marine_overlap_cells": int(np.count_nonzero(new_sections & marine)),
        "old_distal_land_groove_removed_cells": int(old_distal.sum()),
        "old_distal_land_matches_prechannel": bool(np.array_equal(bed[old_distal], prebed[old_distal])),
        "wet_component_count": int(wet_labels.max()), "wet_connectivity": connectivity,
        "construction_cut_bulk_m3": cut, "construction_fill_bulk_m3": fill,
        "construction_net_bulk_m3": net, "construction_residual_m3": fill-cut-net,
        "branch_actual_length_m": a["branch_actual_length_m"].tolist()}
    (output/"geometry-audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    land = LinearSegmentedColormap.from_list("coast_land", ["#9bb879", "#6c965b", "#919a80", "#c5c8c0", "#f1f2ef"])
    sea = LinearSegmentedColormap.from_list("coast_sea", ["#c3e2e6", "#6db8d2", "#286ca1", "#123e72"])
    scale = np.log1p(np.maximum(bed, 0.))/np.log1p(max(float(bed.max()), 1.))
    rgb = land(scale)[..., :3]
    rgb = LightSource(315, 45).shade_rgb(rgb, bed, vert_exag=3., dx=spacing, dy=spacing, blend_mode="soft")
    rgb[wet] = sea(np.clip(a["water_depth_m"][wet]/12., 0., 1.))[..., :3]
    extent = [-spacing/2000., (bed.shape[1]-.5)*spacing/1000.,
              (bed.shape[0]-.5)*spacing/1000., -spacing/2000.]
    terminals = (a["branch_paths_xz_m"][:, -1]-origin)/1000.
    apex = (np.asarray(meta["fan_apex_xz_m"])-origin)/1000.
    def panel(ax, title):
        ax.imshow(rgb, extent=extent, interpolation="nearest")
        ax.contour(bed, levels=[0.], colors="#425e50", linewidths=.45, extent=extent, origin="upper")
        ax.set_title(title)
        ax.set_xlabel("East from scene origin (km)")
        ax.set_ylabel("South from scene origin (km)")
    fig, ax = plt.subplots(figsize=(11, 11), layout="constrained")
    panel(ax, "Coast-bounded constructed terrain | 16 km | 20 m cells")
    ax.set_xlim(0., 16.); ax.set_ylim(16., 0.)
    fig.savefig(output/"scene-16km.png", dpi=180); plt.close(fig)
    fig, axes = plt.subplots(1, len(terminals), figsize=(6*len(terminals), 6), layout="constrained", squeeze=False)
    axes = axes.ravel()
    for index, (ax, terminal) in enumerate(zip(axes, terminals)):
        panel(ax, "First marine outlet "+str(index+1))
        ax.scatter(*terminal, marker="+", s=50, c="#a32532", linewidths=1.)
        ax.set_xlim(terminal[0]-1.2, terminal[0]+1.2)
        ax.set_ylim(terminal[1]+1.2, terminal[1]-1.2)
    fig.savefig(output/"first-outlets-detail.png", dpi=180); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 9), layout="constrained")
    panel(ax, "Constructed lowland and distributary banks")
    lo = np.minimum(apex, terminals.min(axis=0))-1.
    hi = np.maximum(apex, terminals.max(axis=0))+1.
    ax.set_xlim(lo[0], hi[0]); ax.set_ylim(hi[1], lo[1])
    fig.savefig(output/"lowland-detail.png", dpi=180); plt.close(fig)
    if compare_scene is not None:
        with np.load(compare_scene) as previous:
            prior_bed = previous["bed_m"]
            prior_wet = previous["wet_mask"]
            prior_scale = np.log1p(np.maximum(prior_bed, 0.))/np.log1p(max(float(bed.max()), 1.))
            prior_rgb = LightSource(315, 45).shade_rgb(land(prior_scale)[..., :3], prior_bed,
                vert_exag=3., dx=spacing, dy=spacing, blend_mode="soft")
            prior_rgb[prior_wet] = sea(np.clip(previous["water_depth_m"][prior_wet]/12., 0., 1.))[..., :3]
            prior_marine = previous["open_marine_mask"]
            prior_terminals = (previous["branch_paths_xz_m"][:, -1]-origin)/1000.
            prior_weight = previous["platform_weight"].copy()
            original_land = previous["original_land_mask"].copy()
        comparison = {"previous_scene_path": str(Path(compare_scene).resolve()),
            "previous_scene_sha256": file_sha256(Path(compare_scene)),
            "above_sea_land_to_below_sea_area_m2": float(np.count_nonzero((prior_bed > 0.) & (bed <= 0.))*spacing**2),
            "below_sea_to_above_sea_land_area_m2": float(np.count_nonzero((prior_bed <= 0.) & (bed > 0.))*spacing**2),
            "new_open_marine_area_m2": float(np.count_nonzero(marine & ~prior_marine)*spacing**2),
            "removed_open_marine_area_m2": float(np.count_nonzero(prior_marine & ~marine)*spacing**2),
            "previous_effective_fan_area_m2": float(np.count_nonzero(prior_weight > .1)*spacing**2),
            "effective_fan_area_m2": float(np.count_nonzero(a["platform_weight"] > .1)*spacing**2),
            "previous_original_land_platform_area_m2": float(np.count_nonzero(original_land & (prior_weight > .1))*spacing**2),
            "original_land_platform_area_m2": float(np.count_nonzero(original_land & (a["platform_weight"] > .1))*spacing**2)}
        (output/"scene01-comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
        fig, axes = plt.subplots(1, 2, figsize=(16, 10), layout="constrained")
        for ax, color, terrain, outlets, title in zip(axes, (prior_rgb, rgb), (prior_bed, bed),
                (prior_terminals, terminals),
                ("Scene 02 | accepted constructed coast", output.name+" | unequal secondary tree")):
            ax.imshow(color, extent=extent, interpolation="nearest")
            ax.contour(terrain, levels=[0.], colors="#425e50", linewidths=.45, extent=extent, origin="upper")
            ax.set_xlim(6., 12.); ax.set_ylim(12.7, 5.8)
            ax.scatter(outlets[:, 0], outlets[:, 1], marker="+", s=65, c="#a32532", linewidths=1.2,
                label="First sea entry; river calculation ends")
            ax.legend(loc="lower right", fontsize=9)
            ax.set_title(title)
            ax.set_xlabel("East from scene origin (km)"); ax.set_ylabel("South from scene origin (km)")
        fig.savefig(output/"scene01-vs-scene02-coast.png", dpi=180); plt.close(fig)
    return audit


def prepare(source: Path, output: Path):
    resource_limits()
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("independent scene output already exists: "+str(output))
    source_hash = file_sha256(source)
    with np.load(source, allow_pickle=False) as data:
        arrays = {key: data[key].copy() for key in data.files if key != "metadata_json"}
        metadata = json.loads(data["metadata_json"].item())
    supply_path = SOURCE/"feedback_bundle.npz"
    with np.load(supply_path) as supply:
        finite_solid_supply = float(supply["exported_solid_m3"].sum())
    result = construct_coast_bounded_scene(arrays, metadata, finite_solid_supply_m3=finite_solid_supply)
    result["metadata"]["candidate_supply"] = {"path": str(supply_path), "sha256": file_sha256(supply_path),
        "finite_exported_solid_m3": finite_solid_supply}
    result["metadata"]["source_scene_path"] = str(source)
    result["metadata"]["source_scene_sha256"] = source_hash
    result["metadata"]["implementation_hashes"] = {
        "generator_sha256": file_sha256(ROOT/"terrain_pipeline/surface_rivers/metric_coast_bounded_delta.py"),
        "fan_generator_sha256": file_sha256(ROOT/"terrain_pipeline/surface_rivers/metric_stylized_wetland.py"),
        "scene_tool_sha256": file_sha256(Path(__file__)),
    }
    if file_sha256(source) != source_hash:
        raise ValueError("source scene changed during construction")
    output.mkdir(parents=True, exist_ok=False)
    scene_path = output/"scene.npz"
    np.savez_compressed(scene_path, **result["arrays"], metadata_json=json.dumps(result["metadata"], ensure_ascii=True))
    summary = {"scene_path": str(scene_path), "scene_sha256": file_sha256(scene_path),
               "source_scene_path": str(source), "source_scene_sha256": source_hash,
               "metadata": result["metadata"], "construction_audit": result["audit"]}
    (output/"summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SCENE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--compare-scene", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(inspect_scene(args.output, args.compare_scene) if args.inspect else prepare(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
