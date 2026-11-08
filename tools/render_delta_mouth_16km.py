"""Render saved river-mouth geography and the true-scale 4096 local experiment."""
import json
import os
from pathlib import Path
import sys

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.hydrology_planning import load_plan
from terrain_pipeline.common_infra import file_sha256
from tools.compare_hydrology_projection_naturalness import fixed_hillshade
from tools.verify_fluvial_channel_remobilization import resource_limits, refined_origin

BASE = ROOT / "verification/hydrological-planning-domain"
PLAN = BASE / "v5-lake-20261014-02/plan.npz"
TD = BASE / "large-td-confluence-20261014-03/native-routing.npz"
DETAIL = BASE / "full-edges-v5-20261014-03/edge-8470-8600-v7-shared-sections-owned-halo2/detail.npz"
LOCAL = ROOT / "verification/fluvial-delta/morphodynamics-20261015-04/batch-3968-4096-v5/detail.npz"
OUTPUT = ROOT / "verification/fluvial-delta/mouth-16km-20261015-01"


def read(path, keys):
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in keys}
        metadata = json.loads(archive["metadata_json"].item())
    return arrays, metadata


def extent(origin, shape, spacing):
    return [origin[0] - spacing / 2, origin[0] + (shape[1] - .5) * spacing,
            origin[1] + (shape[0] - .5) * spacing, origin[1] - spacing / 2]


def terrain_rgb(height, ocean, spacing, water_depth=None):
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    land = LinearSegmentedColormap.from_list("saved_land", ["#b5c982", "#76995c", "#9a9d71", "#d3d5ce", "#f7f7f3"])
    water = LinearSegmentedColormap.from_list("saved_ocean", ["#b1e0e4", "#60b4d1", "#286aab", "#173f7f"])
    rgb = land(Normalize(0, 550, clip=True)(height))[..., :3]
    rgb *= (.65 + .45 * fixed_hillshade(height, spacing)[..., None])
    depth = np.maximum(-height, 0) if water_depth is None else water_depth
    rgb[ocean] = water(Normalize(0, 35, clip=True)(depth[ocean]))[..., :3]
    return np.clip(rgb, 0, 1)


def scalebar(ax, length, label):
    left, right = ax.get_xlim()
    bottom, top = ax.get_ylim()
    x, z = left + .06 * (right-left), bottom + .07 * (top-bottom)
    ax.plot([x, x+length], [z, z], color="white", linewidth=7, solid_capstyle="butt", zorder=20)
    ax.plot([x, x+length], [z, z], color="#172b35", linewidth=3, solid_capstyle="butt", zorder=21)
    ax.text(x+length/2, z+.018*(top-bottom), label, ha="center", va="bottom", fontsize=11,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": .8, "pad": 2}, zorder=22)


def main():
    resource_limits()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Rectangle
    from matplotlib.lines import Line2D
    from matplotlib.colors import TwoSlopeNorm

    plt.rcParams.update({"font.size": 12, "axes.titlesize": 17, "axes.labelsize": 12})
    plan = load_plan(PLAN)
    td, tm = read(TD, ["original_td_m"])
    detail, dm = read(DETAIL, ["derived_height_m", "ocean_mask", "local_channel_delta_m", "actual_receiver"])
    local, lm = read(LOCAL, ["final_bed_m", "depths_m", "backend_ocean_mask", "backend_valid_mask", "cell_type"])
    assert plan["identity_sha256"] == lm["source"]["plan_identity"] == dm["plan_identity"]
    assert lm["mapping"]["transpose"] is True
    fx, fz = refined_origin(dm["origin_xz_m"], lm["source"]["crop_rows_columns"], 6)
    r0, r1, c0, c1 = lm["mapping"]["source_rows_columns"]
    local_origin = [fx+c0*5, fz+r0*5]
    bed = local["final_bed_m"].T
    depth = local["depths_m"][-1].T
    local_ext = extent(local_origin, bed.shape, 5)
    center = [(local_ext[0]+local_ext[1])/2, (local_ext[2]+local_ext[3])/2]
    window = [center[0]-8000, center[0]+8000, center[1]+8000, center[1]-8000]
    assert window[1]-window[0] == window[2]-window[3] == 16000
    ox, oz = tm["origin_xz_m"]
    h = td["original_td_m"]
    xx = ox + np.arange(h.shape[1])*30
    zz = oz + np.arange(h.shape[0])*30
    px = np.rint((xx-plan["origin_xz_m"][0])/plan["spacing_m"]).astype(int)
    pz = np.rint((zz-plan["origin_xz_m"][1])/plan["spacing_m"]).astype(int)
    ocean = np.asarray(plan["ocean_mask"])[np.ix_(pz, px)]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(13, 13), layout="constrained")
    ax.imshow(terrain_rgb(h, ocean, 30), extent=np.array(extent([ox, oz], h.shape, 30))/1000,
              interpolation="nearest")
    de = extent(dm["origin_xz_m"], detail["derived_height_m"].shape, 30)
    ax.imshow(terrain_rgb(detail["derived_height_m"], detail["ocean_mask"], 30),
              extent=np.array(de)/1000, interpolation="nearest")
    rec = np.asarray(plan["receiver"]).ravel()
    ids = np.flatnonzero(np.asarray(plan["river_mask"]).ravel() & (rec >= 0))
    targets = rec[ids]
    width = plan["height_m"].shape[1]
    def coords(indices):
        return np.c_[plan["origin_xz_m"][0]+indices%width*plan["spacing_m"],
                     plan["origin_xz_m"][1]+indices//width*plan["spacing_m"]]/1000
    lines = np.stack([coords(ids), coords(targets)], axis=1)
    ax.add_collection(LineCollection(lines, colors="white", linewidths=3.5, alpha=.8, linestyles="dashed"))
    ax.add_collection(LineCollection(lines, colors="#14629b", linewidths=1.8, linestyles="dashed"))
    # Plot saved local channel routing only where the actual channel cut exists.
    drec = detail["actual_receiver"].ravel()
    dids = np.flatnonzero((detail["local_channel_delta_m"].ravel() < -.03) &
                         (~detail["ocean_mask"].ravel()) & (drec >= 0))
    dw = detail["derived_height_m"].shape[1]
    def dcoords(indices):
        return np.c_[dm["origin_xz_m"][0]+indices%dw*30, dm["origin_xz_m"][1]+indices//dw*30]/1000
    ax.add_collection(LineCollection(np.stack([dcoords(dids), dcoords(drec[dids])], axis=1),
                                    colors="#135888", linewidths=.65, alpha=.85))
    actual_wet = depth > 2e-6
    ax.imshow(terrain_rgb(bed, actual_wet, 5, water_depth=depth), extent=np.array(local_ext)/1000,
              interpolation="nearest", zorder=7)
    ax.add_patch(Rectangle((de[0]/1000, de[3]/1000), (de[1]-de[0])/1000, (de[2]-de[3])/1000,
                           fill=False, edgecolor="#4b4e55", linewidth=1, linestyle="--", zorder=8))
    ax.add_patch(Rectangle((local_ext[0]/1000, local_ext[3]/1000), .705, .720,
                           fill=False, edgecolor="#b82445", linewidth=2, zorder=9))
    ax.annotate("4096-step local experiment\n705 m x 720 m", xy=(center[0]/1000, center[1]/1000),
                xytext=(center[0]/1000+2, center[1]/1000+2), fontsize=12, color="#8a1232",
                bbox={"facecolor": "white", "edgecolor": "#b82445", "alpha": .95},
                arrowprops={"arrowstyle": "->", "color": "#b82445"}, zorder=12)
    ax.set(xlim=np.array(window[:2])/1000, ylim=np.array(window[2:])/1000,
           xlabel="World X east (km)", ylabel="World Z south (km)", aspect="equal",
           title="River-mouth overview | 16 km x 16 km")
    ax.grid(alpha=.16, color="#23313c", linewidth=.5)
    scalebar(ax, 2, "2 km")
    handles = [Line2D([], [], color="#14629b", lw=2, ls="--", label="Macro river reference (10 km plan; not local channel)"),
               Line2D([], [], color="#135888", lw=.8, label="Saved detailed channel route"),
               Line2D([], [], color="#4b4e55", ls="--", label="Saved 30 m terrain detail boundary"),
               Line2D([], [], color="#b82445", lw=2, label="Actual 5 m local simulation footprint")]
    ax.legend(handles=handles, loc="upper left", fontsize=10, framealpha=.95)
    fig.get_layout_engine().set(rect=(0, .045, 1, .955))
    fig.text(.5, .022, "Outside dashed boundary: TD + macro ocean; inside: saved derived terrain/ocean; local overlay: actual native wet area.\nLocal experiment is shown at true scale; a 16 km delta has not been simulated.", ha="center", fontsize=10)
    fig.savefig(OUTPUT/"overview-16km.png", dpi=260)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(16, 9), layout="constrained")
    im = axes[0].imshow(bed, extent=np.array(local_ext)/1000, cmap="terrain",
                        vmin=-8, vmax=4, interpolation="nearest")
    fig.colorbar(im, ax=axes[0], label="Saved bed elevation (m)", shrink=.72)
    near = axes[1].imshow(bed, extent=np.array(local_ext)/1000, cmap="RdYlBu_r",
                         norm=TwoSlopeNorm(vmin=-.25, vcenter=0, vmax=.25), interpolation="nearest")
    fig.colorbar(near, ax=axes[1], label="Bed relative to fixed sea level (m)", shrink=.72)
    x = local_origin[0]/1000 + np.arange(bed.shape[1])*.005
    z = local_origin[1]/1000 + np.arange(bed.shape[0])*.005
    for ax in axes:
        ax.contour(x, z, bed, levels=[0], colors="#101b20", linewidths=.65)
        ax.set(xlabel="World X east (km)", ylabel="World Z south (km)", aspect="equal")
        ax.ticklabel_format(useOffset=False, style="plain")
        scalebar(ax, .1, "100 m")
    valid_ocean = local["backend_ocean_mask"].T & local["backend_valid_mask"].T & (local["cell_type"].T != -2)
    dry = (bed > 0) & (depth <= 2e-6) & valid_ocean
    assert int(dry.sum()) == 1
    rows, cols = np.where(dry)
    axes[1].scatter(x[cols], z[rows], s=30, marker="s", facecolors="none", edgecolors="#ec00ba", label="Actual dry above-sea cell")
    axes[1].legend(loc="lower right", fontsize=9)
    axes[0].set_title("Actual saved bed | step 4096")
    axes[1].set_title("Near-sea bed | actual dry cell marked")
    fig.suptitle("Local river-mouth experiment | 705 m x 720 m", fontsize=20)
    fig.get_layout_engine().set(rect=(0, .075, 1, .925))
    fig.text(.5, .035, "Black contour: fixed sea-level bed elevation. Above-sea bed can remain submerged beneath native water stage.\nMaterial chain passed; morphology failed. Actual dry above-sea: 25 m2, isolated; connected actual dry: 0 m2.", ha="center", fontsize=11)
    fig.savefig(OUTPUT/"delta-4096-detail.png", dpi=240)
    plt.close(fig)
    metadata = {"sources": [{"path": str(p), "sha256": file_sha256(p)} for p in [PLAN, TD, DETAIL, LOCAL]],
                "plan_identity": plan["identity_sha256"], "coordinates": "world X east, Z south; metres; origins are cell centres",
                "overview_edges_xmin_xmax_zmax_zmin_m": window, "overview_size_m": [16000, 16000],
                "local_backend_shape": list(local["final_bed_m"].shape), "local_map_shape_zx": list(bed.shape),
                "local_cell_center_origin_xz_m": local_origin, "local_edges_xmin_xmax_zmax_zmin_m": local_ext,
                "local_size_xz_m": [local_ext[1]-local_ext[0], local_ext[2]-local_ext[3]],
                "mapping": lm["mapping"], "detail_edges_xmin_xmax_zmax_zmin_m": de,
                "macro_ocean_sampling": "nearest frozen 10km plan node, identical rint convention as saved detail",
                "macro_rivers": "frozen plan river_mask to receiver, no invented branches",
                "detail_rivers": "saved actual_receiver edges restricted to channel cut below -0.03m and non-ocean source cells",
                "terrain_layers": "original TD background, saved derived_height_m detail overlay, actual 4096 final_bed_m local overlay",
                "local_overview_water_display": "actual native depth > 2e-6 m, colored by actual water depth; actual dry original land retains terrain color",
                "actual_dry_marker": "bed > 0, native depth <= 2e-6, original ocean, valid and cell_type != -2",
                "actual_dry_original_ocean_cell_count": int(dry.sum()),
                "new_simulation": False, "overall_morphology_passed": False, "naturalness_certified": False,
                "resources": {"max_cpu_cores": 2, "priority": "BelowNormal", "numeric_threads": 1},
                "figures": [{"path": "overview-16km.png", "pixels": [3380, 3380]},
                            {"path": "delta-4096-detail.png", "pixels": [3840, 2160]}]}
    (OUTPUT/"metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "window_m": window, "local_m": local_ext}))


if __name__ == "__main__":
    main()
