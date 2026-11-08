"""Render saved raw model samples with one shared elevation color scale."""
from pathlib import Path
import argparse
import json

import numpy as np
from PIL import Image, ImageDraw


def render_surface(fields, output, low, high):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(6 * len(fields), 5))
    for index, (name, values) in enumerate(fields, start=1):
        axis = figure.add_subplot(1, len(fields), index, projection="3d")
        step = max(1, values.shape[0] // 128)
        rows, cols = values.shape
        x, z = np.meshgrid(np.arange(0, cols, step), np.arange(0, rows, step))
        axis.plot_surface(x, z, values[::step, ::step], cmap="terrain", vmin=low, vmax=high,
                          linewidth=0, antialiased=False)
        axis.set(xlim=(0, cols), ylim=(0, rows), zlim=(low, high),
                 xlabel="model X pixels", ylabel="model Z pixels", zlabel="meters", title=name[:45])
        axis.view_init(elev=35, azim=-60)
        axis.set_box_aspect((1, 1, .55))
    figure.suptitle("Raw model elevation, shared camera and meter scale (not a Minecraft screenshot)")
    figure.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(figure)


def render_world_surface(fields, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    mapped = [(label, 62 + values / config["meters_per_height_block"], config["blocks_per_pixel"])
              for label, values, config in fields]
    minimum = min(float(values.min()) for _, values, _ in mapped)
    maximum = max(float(values.max()) for _, values, _ in mapped)
    zlow, zhigh = min(62, minimum), max(800, maximum)
    land_cmap = LinearSegmentedColormap.from_list("land", ("#65a04e", "#9ba866", "#827e70", "#e8e7de"))
    figure = plt.figure(figsize=(6 * len(mapped), 5))
    for index, (label, values, blocks_per_pixel) in enumerate(mapped, start=1):
        axis = figure.add_subplot(1, len(mapped), index, projection="3d")
        rows, cols = values.shape
        step = max(1, rows // 128)
        x, z = np.meshgrid(np.arange(0, cols, step) * blocks_per_pixel,
                           np.arange(0, rows, step) * blocks_per_pixel)
        sampled = values[::step, ::step]
        land_tone = np.clip((sampled - 62) / max(zhigh - 62, 1), 0, 1)
        colors = land_cmap(land_tone)
        colors[sampled < 62] = (0.13, 0.35, 0.62, 1)
        axis.plot_surface(x, z, sampled, facecolors=colors,
                          linewidth=0, antialiased=False)
        xspan = (cols - 1) * blocks_per_pixel
        zspan = (rows - 1) * blocks_per_pixel
        axis.set(xlim=(0, xspan), ylim=(0, zspan), zlim=(zlow, zhigh),
                 xlabel="world X blocks", ylabel="world Z blocks", zlabel="world Y blocks", title=label)
        axis.view_init(elev=35, azim=-60)
        axis.set_box_aspect((xspan, zspan, zhigh - zlow))
    figure.suptitle("Model elevation mapped to world blocks; shared camera/height range; not a game screenshot")
    figure.savefig(output, dpi=160, bbox_inches="tight")
    plt.close(figure)


def summarize(fields):
    results = {}
    for label, values, config in fields:
        world_y = 62 + values / config["meters_per_height_block"]
        rows, cols = world_y.shape
        radius_pixels = round(128 / config["blocks_per_pixel"])
        center_z, center_x = rows // 2, cols // 2
        center = world_y[max(0, center_z - radius_pixels):min(rows, center_z + radius_pixels + 1),
                         max(0, center_x - radius_pixels):min(cols, center_x + radius_pixels + 1)]
        center_land = center[center >= 62]
        regional_land = world_y[world_y >= 62]
        dz, dx = np.gradient(world_y, config["blocks_per_pixel"])
        slope = np.hypot(dx, dz)
        results[label] = {
            "center_radius_world_blocks": 128,
            "center_window_pixels": list(center.shape[::-1]),
            "water_filter": "world_y >= 62 for relief; slope includes all pixels",
            "center_land_p90_minus_p10_world_blocks": float(np.percentile(center_land, 90) - np.percentile(center_land, 10)) if center_land.size else None,
            "regional_land_p90_minus_p10_world_blocks": float(np.percentile(regional_land, 90) - np.percentile(regional_land, 10)) if regional_land.size else None,
            "slope_blocks_per_block": {"mean": float(slope.mean()), "p95": float(np.percentile(slope, 95))},
        }
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("samples", nargs="+", type=Path, help="One or more probe .npz files")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    fields = []
    for path in args.samples:
        with np.load(path, allow_pickle=False) as sample:
            config = json.loads(str(sample["generation_config"])) if "generation_config" in sample else json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))["generation_config"]
            label = path.stem.split("-geographic_")[0]
            fields.append((label, sample["elevation"].copy(), config))
    shapes = {values.shape for _, values, _ in fields}
    if len(shapes) != 1:
        parser.error("all samples must have the same shape")
    height, width = next(iter(shapes))
    low = min(float(values.min()) for _, values, _ in fields)
    high = max(float(values.max()) for _, values, _ in fields)
    span = max(high - low, 1)
    canvas = Image.new("RGB", (width * len(fields), height + 50), "#172330")
    draw = ImageDraw.Draw(canvas)
    for index, (name, values, _) in enumerate(fields):
        tone = np.clip((values - low) / span, 0, 1)
        rgb = np.stack((45 + 190 * tone, 65 + 150 * tone, 110 + 100 * tone), axis=-1)
        rgb[values < 0] = (35, 82, 147)
        canvas.paste(Image.fromarray(rgb.astype(np.uint8), "RGB"), (index * width, 0))
        draw.text((index * width + 4, height + 5), name[:35], fill="white")
    draw.text((4, height + 28), f"Raw model elevation (meters), shared scale {low:.0f} to {high:.0f}; not a Minecraft screenshot", fill="#bed4e1")
    output = args.output or args.samples[0].parent / "model-elevation.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    render_surface([(name, values) for name, values, _ in fields], output.with_name("model-surface.png"), low, high)
    render_world_surface(fields, output.with_name("model-surface-world.png"))
    (output.with_name("summary.json")).write_text(json.dumps(summarize(fields), indent=2), encoding="utf-8")
    (output.with_suffix(".json")).write_text(json.dumps({"source_samples": [str(path) for path in args.samples],
                                                        "shared_elevation_m": [low, high]}, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
