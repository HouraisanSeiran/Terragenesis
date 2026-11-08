"""Export real height samples, source geometry and comparable mountain views."""
import argparse
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline import mountain_forms as advanced
from terrain_pipeline.mountain_forms import LocalVolumeConfig, sample_local_volume_mountains
from terrain_pipeline.skeleton_mountains import (
    ALGORITHM_ID, CACHE_CAPACITY, HALO_M, PURPOSES, SOURCE_SUPPORT_CELLS,
    SkeletonMountainConfig, describe_skeleton, sample_skeleton_mountains,
)
from terrain_pipeline.terrain_map_style import physical_hillshade
from terrain_pipeline.common_infra import WORLD_SEED, derive_subseed
from tools.prepare_local_volume_mountains import LOW, HIGH, digest, save_height
from tools.prepare_procedural_mountains import measured


def cases():
    return [("previous", LocalVolumeConfig()),
            ("skeleton_bare", SkeletonMountainConfig(base_relief_m=0, detail_amplitude_m=0, advanced_enabled=False))] + [
                (p, SkeletonMountainConfig(profile=p)) for p in ("granite", "alpine", "asymmetric", "mixed")]


def sample(config, x, z):
    if isinstance(config, LocalVolumeConfig):
        return sample_local_volume_mountains(x, z, config)
    return sample_skeleton_mountains(x, z, config)


def plot_results(directory, window, data, spacing, origin):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    size = next(iter(data.values()))["height_m"].shape[0]
    span = (size-1) * spacing
    extent = [origin[0]/1000, (origin[0]+span)/1000, (origin[1]+span)/1000, origin[1]/1000]
    names = list(data)
    cols = 3 if len(names) > 1 else 1
    rows = math.ceil(len(names)/cols)
    for kind in ("gray", "hillshade"):
        fig, axes = plt.subplots(rows, cols, figsize=(5*cols, 4.7*rows), squeeze=False, constrained_layout=True)
        for ax, name in zip(axes.flat, names):
            h = data[name]["height_m"]
            values, low, high = (h, LOW, HIGH) if kind == "gray" else (physical_hillshade(h, spacing), 0, 1)
            ax.imshow(values, cmap="gray", vmin=low, vmax=high, extent=extent)
            ax.set_title(name); ax.set_xlabel("X east (km)"); ax.set_ylabel("Z south (km)")
        for ax in list(axes.flat)[len(names):]:
            ax.set_visible(False)
        fig.suptitle(f"{window}: real sampled heights | " + ("fixed -500 to 6000 m" if kind == "gray" else "same physical hillshade"))
        fig.savefig(directory / f"{window}_{kind}_comparison.png", dpi=130)
        plt.close(fig)
    # Equal physical axis scaling for all views, with explicit striding.
    show = [n for n in ("granite", "alpine", "asymmetric", "mixed") if n in data]
    if not show:
        show = names
    stride = max(1, math.ceil(size / 140))
    fig = plt.figure(figsize=(5*len(show), 9), constrained_layout=True)
    for row, azimuth in enumerate((-60, 125)):
        for i, name in enumerate(show):
            ax = fig.add_subplot(2, len(show), row*len(show)+i+1, projection="3d")
            h = data[name]["height_m"][::stride, ::stride] / 1000
            zz, xx = np.mgrid[0:size:stride, 0:size:stride] * spacing / 1000
            ax.plot_surface(xx + origin[0]/1000, zz + origin[1]/1000, h,
                            cmap="gray", vmin=LOW/1000, vmax=HIGH/1000, linewidth=0,
                            rcount=h.shape[0], ccount=h.shape[1])
            ax.set_zlim(LOW/1000, HIGH/1000)
            ax.set_box_aspect((span/1000, span/1000, (HIGH-LOW)/1000))
            ax.view_init(elev=30, azim=azimuth)
            ax.set_title(f"{name} | azimuth {azimuth}"); ax.set_xlabel("X km"); ax.set_ylabel("Z km"); ax.set_zlabel("height km")
    fig.suptitle(f"Bare geometry | vertical exaggeration 1.00x | stride {stride} ({stride*spacing:g} m display samples)")
    fig.savefig(directory / f"{window}_bare_views.png", dpi=130)
    plt.close(fig)
    if window == "main":
        # Review silhouette changes with both detail stages removed, on the
        # same fixed background and crop around the procedural primary peak.
        peak = describe_skeleton(0, 0)
        world_x = origin[0] + np.arange(size)*spacing
        world_z = origin[1] + np.arange(size)*spacing
        ix = np.flatnonzero(np.abs(world_x-peak["peak_x_m"]) <= 4500.)
        iz = np.flatnonzero(np.abs(world_z-peak["peak_z_m"]) <= 4500.)
        if len(ix) > 1 and len(iz) > 1:
            fig = plt.figure(figsize=(5*len(show), 9), constrained_layout=True)
            crop_stride = max(1, math.ceil(max(len(ix), len(iz))/100))
            ix, iz = ix[::crop_stride], iz[::crop_stride]
            xx, zz = np.meshgrid(world_x[ix]/1000, world_z[iz]/1000)
            for i, name in enumerate(show):
                h = data[name]["skeleton_height_m"][np.ix_(iz, ix)]
                ax = fig.add_subplot(2, len(show), i+1)
                ax.imshow(physical_hillshade(h, spacing*crop_stride), cmap="gray", vmin=0, vmax=1,
                          extent=[world_x[ix[0]]/1000, world_x[ix[-1]]/1000, world_z[iz[-1]]/1000, world_z[iz[0]]/1000])
                ax.set_title(name + " | no detail / Advanced"); ax.set_xlabel("X km"); ax.set_ylabel("Z km")
                ax = fig.add_subplot(2, len(show), len(show)+i+1, projection="3d")
                ax.plot_surface(xx, zz, h/1000, cmap="gray", vmin=LOW/1000, vmax=HIGH/1000,
                                linewidth=0, rcount=h.shape[0], ccount=h.shape[1])
                ax.set_zlim(LOW/1000, HIGH/1000)
                ax.set_box_aspect(((world_x[ix[-1]]-world_x[ix[0]])/1000,
                                   (world_z[iz[-1]]-world_z[iz[0]])/1000, (HIGH-LOW)/1000))
                ax.view_init(elev=24, azim=-60)
                ax.set_title(name); ax.set_xlabel("X km"); ax.set_ylabel("Z km"); ax.set_zlabel("height km")
            fig.suptitle(f"Shared peak crop +/-4.5 km | skeleton + common background only | 1.00x vertical | display step {crop_stride*spacing:g} m")
            fig.savefig(directory / "main_peak_macro_views.png", dpi=130)
            plt.close(fig)
    # The mixed skeleton is procedural output; these colored lines are not rivers.
    fig, ax = plt.subplots(figsize=(9, 8), constrained_layout=True)
    h = data["mixed"]["height_m"]
    ax.imshow(physical_hillshade(h, spacing), cmap="gray", vmin=0, vmax=1, extent=extent)
    c = SkeletonMountainConfig()
    sources = []
    lo = np.floor(np.asarray(origin) / c.cell_size_m).astype(int)-1
    hi = np.floor((np.asarray(origin)+span) / c.cell_size_m).astype(int)+1
    for cz in range(lo[1], hi[1]+1):
        for cx in range(lo[0], hi[0]+1):
            source = describe_skeleton(cx, cz, c)
            sources.append(source)
            ax.scatter(source["peak_x_m"]/1000, source["peak_z_m"]/1000, marker="^", c="red", s=25)
            for curve in source["curves"]:
                t = np.linspace(0, 1, 65)
                u, v = t*curve["length_m"], curve["bend_m"]*np.sin(np.pi*t)**2
                co, si = math.cos(curve["angle_rad"]), math.sin(curve["angle_rad"])
                x = curve["start_x_m"] + co*u - si*v
                z = curve["start_z_m"] + si*u + co*v
                ax.plot(x/1000, z/1000, color="orange" if curve["level"] == 1 else "cyan", linewidth=1.2)
    ax.set_xlim(extent[:2]); ax.set_ylim(extent[2:]); ax.set_xlabel("X east (km)"); ax.set_ylabel("Z south (km)")
    ax.set_title("Procedural skeleton: red peak, orange primary, cyan secondary (not rivers)")
    fig.savefig(directory / f"{window}_skeleton_overlay.png", dpi=140)
    plt.close(fig)
    (directory / f"{window}_skeleton.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def plot_sections(directory):
    import matplotlib.pyplot as plt
    source = describe_skeleton(0, 0)
    parent = source["curves"][0]
    co, si = math.cos(parent["angle_rad"]), math.sin(parent["angle_rad"])
    distance = np.linspace(-6000, 6000, 401)
    saved = {"distance_m": distance}
    fig, axes = plt.subplots(1, 2, figsize=(15, 5), constrained_layout=True)
    for ax, t, label in zip(axes, (0., .38), ("through primary peak", "across primary shoulder")):
        u, v = t*parent["length_m"], parent["bend_m"]*math.sin(np.pi*t)**2
        px = parent["start_x_m"] + co*u - si*v
        pz = parent["start_z_m"] + si*u + co*v
        x, z = px - si*distance, pz + co*distance
        prefix = "peak" if t == 0 else "shoulder"
        saved[prefix+"_x_m"], saved[prefix+"_z_m"] = x, z
        for name, c in cases():
            fields = sample(c, x, z)
            for key in ("height_m", "macro_height_m"):
                saved[f"{prefix}_{name}_{key}"] = fields[key]
            if name != "skeleton_bare":
                ax.plot(distance/1000, fields["height_m"], label=name, linewidth=1.2)
        ax.set_title(label + f" | centre ({px:.1f}, {pz:.1f}) m")
        ax.set_xlabel("nominal cross-ridge distance (km)"); ax.set_ylabel("sampled height (m)")
        ax.set_ylim(LOW, HIGH); ax.grid(True); ax.legend()
    fig.suptitle("Exact world-coordinate sections; no interpolation from image pixels")
    fig.savefig(directory / "main_peak_sections.png", dpi=140)
    plt.close(fig)
    np.savez_compressed(directory / "sections.npz", **saved)


def generate(output, size=121, spacing=200., benchmark=False):
    target = Path(output).resolve()
    if target.exists():
        raise FileExistsError(target)
    if isinstance(size, bool) or not isinstance(size, int) or size < 2 or size > 1024 or not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("invalid grid")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="." + target.name + "-", dir=target.parent))
    try:
        sources = ["terrain_pipeline/skeleton_mountains.py", "terrain_pipeline/local_volume_mountains.py",
                   "terrain_pipeline/product_mountains.py", "terrain_pipeline/advanced_terrain_filter.py",
                   "terrain_pipeline/common_infra.py", "diffusion/geographic_noise.py", "terrain_pipeline/terrain_map_style.py",
                   "tools/prepare_skeleton_mountains.py", "tools/prepare_local_volume_mountains.py", "tools/prepare_procedural_mountains.py"]
        manifest = {"algorithm_id": ALGORITHM_ID, "world_seed": WORLD_SEED,
                    "source_sha256": {p: digest(ROOT/p) for p in sources},
                    "subseed_derivation": "terrain_pipeline.world_seed.derive_subseed",
                    "subseeds": {p: derive_subseed(WORLD_SEED, p) for p in PURPOSES + ("product-ridge", "product-warp", "product-voronoi-sites", "local-volume-sites", "local-volume-selection")},
                    "advanced_filter": {"algorithm_id": advanced.ADVANCED_ALGORITHM_ID,
                                        "stable_seed": int.from_bytes(hashlib.sha256(f"advanced-terrain-filter-v1:{WORLD_SEED}:phacelle".encode("ascii")).digest()[:8], "little"),
                                        "config": asdict(advanced.AdvancedFilterConfig(amplitude_m=150., wavelength_m=1800., octaves=3))},
                    "mapping": {"minimum_m": LOW, "maximum_m": HIGH, "encoding": "round(clip((h+500)/6500,0,1)*65535)"},
                    "coordinate_convention": "row Z south, column X east; origin + index * spacing; metres",
                    "dependencies": {"macro_neighbor_cells": "3x3", "source_support_cells": SOURCE_SUPPORT_CELLS,
                                     "hierarchy_levels": 2, "curves_per_source": 6, "curve_distance": "analytic nominal-frame lateral offset; not exact Euclidean distance",
                                     "sample_halo_m": HALO_M, "cache_capacity_descriptors": CACHE_CAPACITY, "cache_scope": "per invocation, discarded"},
                    "plot_geometry": {"stride": max(1, math.ceil(size/140)), "vertical_exaggeration": 1.},
                    "stages": {"base_height_m": "product v2 macro, base=200 m / amplitude=600 m / alpha=.65; bare case uses flat 200 m",
                               "skeleton_height_m": "base plus source/curve contraharmonic soft union; no detail or Advanced",
                               "macro_height_m": "skeleton plus 45 m amplitude noise scaled by skeleton uplift/4700",
                               "final_delta_m": "slope fade(.02,.08) * skeleton uplift fade(0,1000 m) * negative-only gain2.4",
                               "skeleton_bare": "mixed geometry; base relief, detail and Advanced all off; not the previous baseline"},
                    "environment": {"python": sys.version, "numpy": np.__version__, "platform": platform.platform(), "processor": platform.processor()},
                    "cases": [], "benchmark": [], "timings_seconds": {"generation": 0., "save": 0., "plot": 0.}}
        for window, origin, choices in (("main", (0., 0.), cases()), ("negative", (-24000., -24000.), [("mixed", SkeletonMountainConfig())])):
            x, z = np.meshgrid(origin[0] + np.arange(size)*spacing, origin[1]+np.arange(size)*spacing)
            data = {}
            for name, config in choices:
                begin = time.perf_counter()
                f = sample(config, x, z)
                manifest["timings_seconds"]["generation"] += time.perf_counter()-begin
                begin = time.perf_counter()
                npz = stage / f"{window}_{name}.npz"
                np.savez_compressed(npz, **f)
                item = {"name": f"{window}_{name}", "algorithm_id": "local-volume-mountains-v1" if name == "previous" else ALGORITHM_ID,
                        "config": asdict(config), "shape_zx": [size, size], "spacing_m": spacing, "origin_xz_m": list(origin),
                        "npz": npz.name, "npz_sha256": digest(npz),
                        "height_images": {key: save_height(stage / f"{window}_{name}_{key}.png", f[key]) for key in ("macro_height_m", "height_m")},
                        "max_abs_detail_m": float(np.max(np.abs(f.get("detail_delta_m", np.zeros(1))))),
                        "final_delta_range_m": [float(f["final_delta_m"].min()), float(f["final_delta_m"].max())]}
                manifest["cases"].append(item)
                manifest["timings_seconds"]["save"] += time.perf_counter()-begin
                data[name] = f
            begin = time.perf_counter()
            plot_results(stage, window, data, spacing, origin)
            manifest["timings_seconds"]["plot"] += time.perf_counter()-begin
        begin = time.perf_counter()
        plot_sections(stage)
        manifest["timings_seconds"]["plot"] += time.perf_counter()-begin
        if benchmark:
            for location, origin in (("near", (0., 0.)), ("far", (500000000., -500000000.))):
                x, z = np.meshgrid(origin[0] + np.arange(512)*60., origin[1]+np.arange(512)*60.)
                _, stats = measured(lambda: sample_skeleton_mountains(x, z))
                manifest["benchmark"].append({"location": location, "origin_xz_m": list(origin), "shape_zx": [512, 512], "spacing_m": 60., **stats})
            manifest["benchmark_scope"] = "wall time with tracemalloc; sampled whole-process RSS every 10ms can miss peaks; includes process baseline, excludes interpreter startup"
        manifest["files_sha256"] = {p.name: digest(p) for p in sorted(stage.iterdir()) if p.is_file()}
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        os.rename(stage, target)
    except BaseException:
        # This is only the exact temporary directory returned by mkdtemp above.
        # It is a sibling of the requested target, not a computed workspace root.
        if stage.parent != target.parent or not stage.name.startswith("."+target.name+"-"):
            raise RuntimeError("unexpected staging path")
        shutil.rmtree(stage)
        raise
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--size", type=int, default=121)
    parser.add_argument("--spacing", type=float, default=200.)
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    print(generate(args.output, args.size, args.spacing, args.benchmark))


if __name__ == "__main__":
    main()
