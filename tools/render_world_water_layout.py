"""Render a CPU-only overview of a finite world layout."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.world_water_layout import LayoutSpec, classify_points
from diffusion.world_layout_conditioning import WorldLayoutGenerationConfig, layout_elevation_m


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset", choices=("earth", "archipelago", "lakes"), required=True)
    parser.add_argument("--water", type=float)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--frame-side-m", type=float, default=12_288_000.0)
    parser.add_argument("--frame-origin-m", type=float, nargs=2, default=(0.0, 0.0))
    parser.add_argument("--region-side-m", type=float)
    parser.add_argument("--pixels", type=int, default=512)
    parser.add_argument("--view-origin-m", type=float, nargs=2)
    parser.add_argument("--view-side-m", type=float)
    parser.add_argument("--layer", choices=("classes", "conditioning"), default="classes")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.water is None:
        args.water = {"earth": 0.62, "archipelago": 0.8, "lakes": 0.12}[args.preset]
    if not 2 <= args.pixels <= 2048:
        parser.error("pixels must be between 2 and 2048")
    spec = LayoutSpec(args.preset, args.water, world_seed=args.seed,
                      layout_id="large-world-first-pass", mode="finite",
                      frame_origin_m=args.frame_origin_m, frame_side_m=args.frame_side_m,
                      region_side_m=args.region_side_m)
    view_origin = args.view_origin_m or args.frame_origin_m
    view_side = args.view_side_m or args.frame_side_m
    if view_side <= 0:
        parser.error("view-side-m must be positive")
    spacing = view_side / args.pixels
    axis = (np.arange(args.pixels) + 0.5) * spacing
    x, z = np.meshgrid(view_origin[0] + axis, view_origin[1] + axis)
    classes = classify_points(spec, x, z)
    colors = np.array([[109, 153, 104], [55, 102, 152], [86, 158, 193]], dtype=np.uint8)
    if args.output.exists():
        parser.error("output already exists")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.layer == "conditioning":
        import matplotlib.pyplot as plt
        elevation = layout_elevation_m(spec, WorldLayoutGenerationConfig.from_layout(spec), x, z)
        fig, ax = plt.subplots()
        shown = ax.imshow(elevation, cmap="terrain", origin="upper",
                          extent=(view_origin[0] / 1000, (view_origin[0] + view_side) / 1000,
                                  (view_origin[1] + view_side) / 1000, view_origin[1] / 1000))
        ax.set_xlabel("x east (km)")
        ax.set_ylabel("z south (km)")
        fig.colorbar(shown, ax=ax, label="conditioning elevation (m)")
        fig.savefig(args.output, dpi=160, bbox_inches="tight")
        plt.close(fig)
    else:
        Image.fromarray(colors[classes]).save(args.output)
    from scipy import ndimage
    selected = classes == (2 if args.preset == "lakes" else 0)
    labels, count = ndimage.label(selected)
    sizes = np.bincount(labels.ravel())[1:] * (spacing / 1000.0) ** 2
    regional_fractions = [[float(block.mean()) for block in np.array_split(row, 4, axis=1)]
                          for row in np.array_split(selected, 4, axis=0)]
    record = {"layout": spec.parameters(), "layout_identity": spec.identity(),
              "spacing_m": spacing, "pixels": args.pixels, "layer": args.layer,
              "view_origin_m": list(view_origin), "view_side_m": view_side,
              "measured_water_fraction": float(np.mean(classes != 0)),
              "water_fraction_error": float(np.mean(classes != 0) - args.water),
              "component_class": "lake" if args.preset == "lakes" else "land",
              "component_connectivity": 4, "component_count": int(count),
              "component_class_coverage_by_4x4_region": regional_fractions,
              "component_area_km2_percentiles": (np.percentile(sizes, [10, 50, 90, 100]).tolist()
                                                  if sizes.size else []),
              "sampling_note": "sampled macro classes; smaller features may be missed; no topology certification",
              "claim_level": "macro_layout_diagnostic_only",
              "production_spacing_m": 30.0, "conditioning_spacing_m": 7680.0}
    args.output.with_suffix(".json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
