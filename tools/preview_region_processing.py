"""Run the Java processor on saved NPZ terrain and plot its interior output."""
import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np


def percentile(values, q):
    return float(np.percentile(values, q))


def slope(height):
    return np.hypot(np.gradient(height, 2, axis=0), np.gradient(height, 2, axis=1))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", nargs="+", type=Path)
    parser.add_argument("--classes", type=Path, default=Path("build/region-processing-test"))
    parser.add_argument("--java", default="java")
    parser.add_argument("--output", type=Path, default=Path("verification/region-processing"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    reports = {}
    for path in args.samples:
        with np.load(path, allow_pickle=False) as archive:
            config = json.loads(str(archive["generation_config"]))
            mapping = json.loads(str(archive["world_mapping"]))
            spacing = int(config["blocks_per_pixel"])
            if spacing != 2 or int(mapping["world_sea_level"]) != 62:
                raise ValueError("Processor requires 2 blocks/pixel and Minecraft sea level 62")
            meters_per_block = float(config["meters_per_height_block"])
            raw = (float(mapping["world_sea_level"]) + archive["elevation"].astype(np.float32)
                   / meters_per_block).astype(np.float32)
            metadata = json.loads(str(archive["metadata"]))
        match = re.search(r"-x(-?\d+)-z(-?\d+)", path.stem)
        x, z = map(int, match.groups()) if match else metadata["native_origin"]
        x *= spacing
        z *= spacing
        seed = int(metadata["seed"])
        h, w = raw.shape
        if h <= 50 or w <= 50:
            raise ValueError("Sample needs at least 25 halo pixels on each side")
        with tempfile.TemporaryDirectory(dir=args.output) as temp:
            source, target = Path(temp) / "input.bin", Path(temp) / "output.bin"
            raw.astype(">f4").tofile(source)
            completed = subprocess.run([args.java, "-cp", str(args.classes.absolute()),
                            "com.remotemountains.region.processing.RegionProcessingCli",
                            str(source), str(target), str(w), str(h), str(x), str(z), str(seed)],
                           check=True, capture_output=True, text=True)
            algorithm_id, elapsed_ms = completed.stdout.strip().split()
            payload = target.read_bytes()
        count = h * w
        derived = np.frombuffer(payload, dtype=">f4", count=count).reshape(h, w).astype(np.float32)
        weights = np.frombuffer(payload, dtype=">f4", count=4 * count,
                                offset=4 * count).reshape(h, w, 4).astype(np.float32)
        types = np.frombuffer(payload, dtype="u1", count=count,
                              offset=20 * count).reshape(h, w)
        core = np.s_[25:-25, 25:-25]
        before, after, labels, wcore = raw[core], derived[core], types[core], weights[core]
        sb, sa = slope(before), slope(after)
        land = before > 62
        sb_land, sa_land = sb[land], sa[land]
        report = {"algorithm_id": algorithm_id, "processing_ms": float(elapsed_ms),
                  "shape": list(before.shape), "origin_world": [x + 50, z + 50], "seed": seed,
                  "land_fraction": float(np.mean(land)),
                  "raw_land_slope_p50_p95": [percentile(sb_land, 50), percentile(sb_land, 95)],
                  "derived_land_slope_p50_p95": [percentile(sa_land, 50), percentile(sa_land, 95)],
                  "low_land_slope_fraction_raw_0.3": float(np.mean(sb_land < .3)),
                  "low_land_slope_fraction_derived_0.3": float(np.mean(sa_land < .3)),
                  "dominant_type_fraction": [float(np.mean(labels == k)) for k in range(4)],
                  "mean_weights": [float(v) for v in wcore.mean(axis=(0, 1))],
                  "maximum_raw_and_delta": [float(before.max()),
                                            float(after.flat[np.argmax(before)] - before.max())],
                  "raw_height_range": [float(before.min()), float(before.max())],
                  "derived_height_range": [float(after.min()), float(after.max())]}
        reports[path.stem] = report
        np.savez_compressed(args.output / f"{path.stem}-derived.npz", raw_height=before,
                            processed_height=after, weights=wcore, dominant_type=labels,
                            origin_world=np.array([x + 50, z + 50], dtype=np.int32),
                            spacing_blocks=np.int32(spacing), algorithm_id=algorithm_id)
        fig, axes = plt.subplots(1, 4, figsize=(18, 4.5), constrained_layout=True)
        scale = dict(vmin=float(before.min()), vmax=float(before.max()), cmap="gist_earth")
        axes[0].imshow(before, **scale); axes[0].set_title("Raw height (Minecraft Y)")
        axes[1].imshow(after, **scale); axes[1].set_title("Processed height (Minecraft Y)")
        axes[2].imshow(after - before, cmap="RdBu_r", vmin=-12, vmax=12); axes[2].set_title("Processed - raw")
        palette = ListedColormap(["#91ca73", "#cba56b", "#6e94b8", "#8a6387"])
        axes[3].imshow(labels, cmap=palette, vmin=-.5, vmax=3.5)
        axes[3].set_title("Dominant landform")
        for ax in axes: ax.axis("off")
        fig.legend([plt.Rectangle((0, 0), 1, 1, color=color) for color in palette.colors],
                   ["plain", "hill", "plateau", "mountain"], loc="lower center", ncol=4)
        fig.suptitle("Heightfield comparison; not a game screenshot")
        fig.savefig(args.output / f"{path.stem}.png", dpi=150)
        plt.close(fig)
        step = 4
        yy, xx = np.mgrid[0:before.shape[0]:step, 0:before.shape[1]:step]
        xx *= spacing
        yy *= spacing
        fig = plt.figure(figsize=(14, 6), constrained_layout=True)
        for index, (surface, title) in enumerate(((before, "Raw"), (after, "Processed")), 1):
            ax = fig.add_subplot(1, 2, index, projection="3d")
            ax.plot_surface(xx, yy, surface[::step, ::step], cmap="gist_earth", linewidth=0,
                            antialiased=False, vmin=float(before.min()), vmax=float(before.max()))
            ax.set_title(title)
            ax.set_zlim(float(before.min()), float(before.max()))
            ax.set_xlabel("X (world blocks)")
            ax.set_ylabel("Z (world blocks)")
            ax.set_zlabel("Minecraft Y")
            ax.set_box_aspect((float(xx.max()), float(yy.max()), float(before.max() - before.min())))
            ax.view_init(elev=38, azim=-65)
        fig.suptitle("Heightfield comparison; true XYZ proportions, not a game screenshot")
        fig.savefig(args.output / f"{path.stem}-3d.png", dpi=120)
        plt.close(fig)
    (args.output / "report.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
