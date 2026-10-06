"""Reproducible offline surface-river preview; never edits source height caches."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from terrain_pipeline.surface_rivers import GridInput, route
from terrain_pipeline.surface_rivers.pipeline import process, save


DEFAULT_SAMPLE = Path("verification/region-processing/plains-geographic_v2-seed20260927-x2176-z8832-derived.npz")
DEFAULT_OUTPUT = Path("verification/surface-rivers/current")


def y_confluence() -> GridInput:
    """Two upper valleys join a central lower reach; runoff is blocks per second."""
    z, x = np.mgrid[:49, :49]
    center = 24.0
    left_axis = center - np.maximum(24 - z, 0) * .65
    right_axis = center + np.maximum(24 - z, 0) * .65
    upper_valley = np.minimum((x - left_axis) ** 2, (x - right_axis) ** 2)
    lower_valley = (x - center) ** 2
    cross_section = np.where(z <= 24, upper_valley, lower_valley)
    height = 130.0 - .18 * z + .12 * cross_section
    outlet = np.zeros(height.shape, dtype=bool)
    outlet[-1, 24] = True
    return GridInput(height, 2.0, (-48.0, -48.0),
                     np.full(height.shape, .01, dtype=np.float64), outlet)


def real_window(path: Path) -> GridInput:
    with np.load(path, allow_pickle=False) as archive:
        height = archive["processed_height"].astype(np.float64)
        origin = tuple(float(v) for v in archive["origin_world"])
        spacing = float(archive["spacing_blocks"])
    # This window is not a watershed. Its lowest boundary sample is only a test outlet.
    edge = np.zeros(height.shape, dtype=bool)
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True
    edge_height = np.where(edge, height, np.inf)
    outlet = np.zeros(height.shape, dtype=bool)
    outlet[np.unravel_index(int(np.argmin(edge_height)), height.shape)] = True
    return GridInput(height, spacing, origin,
                     np.full(height.shape, .001, dtype=np.float64), outlet)


def profile_indices(receiver: np.ndarray, flowline: np.ndarray, outlet: np.ndarray) -> np.ndarray:
    """Trace the longest active upstream path ending at the explicit outlet."""
    downstream = np.asarray(receiver).reshape(-1)
    active = np.asarray(flowline).reshape(-1)
    target = int(np.flatnonzero(outlet.reshape(-1))[0])
    donors = [[] for _ in range(downstream.size)]
    for cell, next_cell in enumerate(downstream):
        if next_cell >= 0 and active[cell]:
            donors[next_cell].append(cell)
    length = np.zeros(downstream.size, dtype=np.int64)
    stack = [(target, False)]
    while stack:
        cell, ready = stack.pop()
        if ready:
            length[cell] = 1 + max((length[donor] for donor in donors[cell]), default=0)
        else:
            stack.append((cell, True))
            stack.extend((donor, False) for donor in donors[cell])
    path = [target]
    while donors[path[-1]]:
        path.append(max(donors[path[-1]], key=lambda cell: (length[cell], -cell)))
    return np.array(path[::-1], dtype=np.int64)


def export_case(name: str, grid: GridInput, threshold_q: float, output: Path,
                artificial_outlet: bool, source_path: str) -> dict:
    result = process(grid, threshold_q)
    result.metadata.update({"source_height": source_path,
        "artificial_boundary_outlet": artificial_outlet,
        "not_a_natural_watershed": artificial_outlet,
        "runoff_units": "vertical blocks per second",
        "discharge_units": "cubic blocks per second"})
    routing = route(grid.height, grid.outlet_mask, grid.spacing_blocks)
    flowline = result.flowline_mask
    width = result.width_blocks
    npz = output / f"{name}.npz"
    if npz.exists():
        with np.load(npz, allow_pickle=False) as previous:
            expected = {"input_height": result.input_height, "processed_height": result.height,
                "vdm_dy": result.vdm_dy, "water_surface": result.water_surface,
                "discharge": result.discharge, "receiver": result.receiver,
                "channel_mask": result.channel_mask, "flowline_mask": result.flowline_mask,
                "width_blocks": result.width_blocks, "unresolved_mask": result.unresolved_mask,
                "outlet_mask": result.outlet_mask,
                "metadata": np.array(json.dumps(result.metadata, sort_keys=True))}
            for field, value in expected.items():
                if field not in previous or not np.array_equal(previous[field], value, equal_nan=True
                        if np.issubdtype(np.asarray(value).dtype, np.number) else False):
                    raise RuntimeError(f"Existing preview {field} differs: {npz}; choose a new output directory")
    else:
        save(npz, result)
    indices = profile_indices(routing.receiver, flowline, grid.outlet_mask)
    profile_z, profile_x = np.unravel_index(indices, grid.height.shape)
    distance = np.zeros(indices.size, dtype=np.float64)
    distance[1:] = np.cumsum(np.hypot(np.diff(profile_z), np.diff(profile_x)) * grid.spacing_blocks)
    raw_profile = grid.height[profile_z, profile_x]
    bed_profile = result.height[profile_z, profile_x]
    water_profile = result.water_surface[profile_z, profile_x]

    fig, axes = plt.subplots(2, 3, figsize=(16, 9), constrained_layout=True)
    fields = ((grid.height, "Input height", "terrain"),
              (result.height, "Derived channel bed", "terrain"),
              (np.log10(np.maximum(result.discharge, 1e-12)), "log10 discharge Q", "viridis"),
              (width, "Channel width (blocks)", "viridis"),
              (result.water_surface, "Safe water surface", "Blues"))
    for ax, (values, title, palette) in zip(axes.flat[:5], fields):
        image = ax.imshow(values, cmap=palette, origin="lower")
        ax.set_title(title)
        ax.contour(result.unresolved_mask, levels=[.5], colors="red", linewidths=.8, origin="lower")
        fig.colorbar(image, ax=ax, shrink=.75)
    ax = axes.flat[5]
    ax.plot(distance, raw_profile, label="input")
    ax.plot(distance, bed_profile, label="bed")
    ax.plot(distance, water_profile, label="water")
    unresolved_profile = result.unresolved_mask[profile_z, profile_x]
    ax.scatter(distance[unresolved_profile], bed_profile[unresolved_profile], c="red", s=8,
               label="unresolved")
    ax.set_title("Upstream to outlet profile")
    ax.set_xlabel("Route distance (blocks)")
    ax.set_ylabel("Minecraft Y")
    ax.legend(fontsize=8)
    fig.suptitle(f"{name}: red = unresolved; outlet={'artificial boundary' if artificial_outlet else 'fixture'}")
    fig.savefig(output / f"{name}.png", dpi=140)
    plt.close(fig)

    return {"case": name, "source_height": source_path,
            "shape": list(grid.height.shape), "origin_world_xz": list(grid.origin),
            "spacing_blocks": grid.spacing_blocks, "runoff_units": "vertical blocks per second",
            "discharge_units": "cubic blocks per second", "threshold_q": threshold_q,
            "outlet_grid_zx": [int(v) for v in np.argwhere(grid.outlet_mask)[0]],
            "artificial_boundary_outlet": artificial_outlet,
            "not_a_natural_watershed": artificial_outlet,
            "input_total_q": float(result.metadata["input_total"]),
            "outlet_total_q": float(result.metadata["outlet_total"]),
            "budget_residual_q": float(result.metadata["residual"]),
            "flowline_cells": int(np.count_nonzero(flowline)),
            "unresolved_cells": int(np.count_nonzero(result.unresolved_mask)),
            "max_width_blocks": float(np.max(width)),
            "profile_cells": int(indices.size),
            "profile_unresolved_cells": int(np.count_nonzero(unresolved_profile))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"y_confluence": export_case("y_confluence", y_confluence(), 2.0, args.output,
                                           False, "synthetic:y_confluence_v1"),
              "real_window": export_case("real_window", real_window(args.sample), .5, args.output,
                                          True, str(args.sample))}
    (args.output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
