"""Inspect saved terrain against its declared layout water classification."""
from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256


def inspect_page(page_dir, water_level_m=None):
    page_dir = Path(page_dir)
    metadata = json.loads((page_dir / "page.json").read_text(encoding="utf-8"))
    elevation = np.load(page_dir / "elevation.npy", allow_pickle=False)
    classes = np.load(page_dir / "layout-classes.npy", allow_pickle=False)
    if (elevation.ndim != 2 or not elevation.size or elevation.dtype.kind not in "fiu"
            or not np.isfinite(elevation).all() or classes.shape != elevation.shape
            or classes.dtype != np.uint8 or not np.isin(classes, [0, 1, 2]).all()):
        raise ValueError("finite 2D elevation and matching uint8 layout classes 0, 1, 2 required")
    origin = metadata.get("origin_native_xz")
    if (not isinstance(origin, list) or len(origin) != 2
            or any(type(value) is not int for value in origin)
            or metadata.get("page_side_cells") != elevation.shape[0]
            or elevation.shape[0] != elevation.shape[1]):
        raise ValueError("page metadata origin or shape does not match arrays")
    declared = metadata.get("conditioning_parameters", {}).get("sea_datum_m")
    if water_level_m is None:
        water_level_m = declared
        level_source = "page.json:conditioning_parameters.sea_datum_m"
    else:
        level_source = "explicit CLI argument"
    if isinstance(water_level_m, bool) or not isinstance(water_level_m, (int, float)) or not math.isfinite(water_level_m):
        raise ValueError("water level missing or invalid; supply --water-level-m")
    below = elevation < water_level_m
    water = classes != 0
    stats = {}
    for label, value in (("land", 0), ("sea", 1), ("lake", 2)):
        mask = classes == value
        selected = elevation[mask]
        stats[label] = {"cells": int(selected.size),
                        "min_m": float(selected.min()) if selected.size else None,
                        "max_m": float(selected.max()) if selected.size else None,
                        "mean_m": float(selected.mean()) if selected.size else None,
                        "fraction_below_water_level": float(below[mask].mean()) if selected.size else None}
    report = {"schema": "world-water-layout-page-inspection-v1", "source_directory": str(page_dir.resolve()),
              "source_sha256": {name: file_sha256(page_dir / name) for name in
                                ("elevation.npy", "layout-classes.npy", "page.json")},
              "origin_native_xz": origin, "shape_zx": list(elevation.shape), "spacing_m": 30.,
              "layout_identity": metadata.get("layout_identity"),
              "conditioning_identity": metadata.get("conditioning_identity"),
              "water_level_m": float(water_level_m), "water_level_source": level_source,
              "classification_statistics": stats,
              "design_water_vs_below_level_agreement_fraction": float((water == below).mean()),
              "design_water_above_or_at_level_cells": int((water & ~below).sum()),
              "design_land_below_level_cells": int((~water & below).sum()),
              "limitations": "Design masks are not observed lake basins; no closure or spillway certification."}
    return elevation, classes, below, report


def render(elevation, classes, below, report):
    import matplotlib.pyplot as plt
    from matplotlib.colors import BoundaryNorm, ListedColormap, TwoSlopeNorm
    from matplotlib.patches import Patch
    from terrain_pipeline.terrain_map_style import relief_colormap

    rows, cols = elevation.shape
    x, z = report["origin_native_xz"]
    extent = [(x - .5) * .03, (x + cols - .5) * .03,
              (z + rows - .5) * .03, (z - .5) * .03]
    water_level = report["water_level_m"]
    delta = max(float(np.max(np.abs(elevation - water_level))), 1e-6)
    norm = TwoSlopeNorm(vmin=water_level - delta, vcenter=water_level, vmax=water_level + delta)
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6), constrained_layout=True)
    image = axes[0].imshow(elevation, origin="upper", extent=extent, cmap=relief_colormap(), norm=norm)
    fig.colorbar(image, ax=axes[0], label="Elevation (m)", shrink=.75)
    axes[0].set_title("Terrain elevation; water level %.2f m" % water_level)
    cmap = ListedColormap(["#d9d5c6", "#397ba6", "#63b8b4"])
    axes[1].imshow(classes, origin="upper", extent=extent, cmap=cmap,
                   norm=BoundaryNorm([-.5, .5, 1.5, 2.5], cmap.N))
    axes[1].set_title("Design classification")
    axes[1].legend(handles=[Patch(color=cmap(i), label=name) for i, name in enumerate(("Land", "Sea", "Lake"))],
                   loc="lower left", fontsize="small")
    comparison = np.where(classes != 0, np.where(below, 1, 2), np.where(below, 3, 0))
    compare_cmap = ListedColormap(["#d9d5c6", "#397ba6", "#e07a5f", "#d6a63a"])
    axes[2].imshow(comparison, origin="upper", extent=extent, cmap=compare_cmap,
                   norm=BoundaryNorm([-.5, .5, 1.5, 2.5, 3.5], compare_cmap.N))
    axes[2].set_title("Design versus actual elevation")
    axes[2].legend(handles=[Patch(color=compare_cmap(i), label=name) for i, name in enumerate(
        ("Land at/above", "Water below", "Water at/above", "Land below"))], loc="lower left", fontsize="small")
    for axis in axes:
        axis.set_xlabel("World X (km)")
        axis.set_ylabel("World Z (km, south)")
    output = io.BytesIO()
    fig.savefig(output, format="png", dpi=140)
    plt.close(fig)
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page_dir")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--water-level-m", type=float)
    args = parser.parse_args()
    destination = Path(args.output_dir)
    if destination.exists():
        raise FileExistsError(destination)
    elevation, classes, below, report = inspect_page(args.page_dir, args.water_level_m)
    figure = render(elevation, classes, below, report)
    destination.mkdir(parents=True)
    (destination / "inspection.png").write_bytes(figure)
    (destination / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
