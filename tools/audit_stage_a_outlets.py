"""Independent checks and scientific map for the stage A outlet package."""

import argparse
import copy
import json
import math
from pathlib import Path
import sys

import numpy as np
from rasterio.warp import transform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.artifacts.contracts import digest
from terrain_pipeline.td_source import load_dem_candidate
from terrain_pipeline.real_dem_outlet_classification import validate_outlet_classification
from terrain_pipeline.drainage import build_real_dem_network as build_real_dem_network
from tools.verify_real_dem_outlet_classification import (
    DEFAULT_AUDIT, DEFAULT_CANDIDATE, DEFAULT_VECTORS, read_json, verify_package,
)


def nearest_segment(point, vectors):
    best_distance = math.inf
    best_id = None
    for river in sorted(vectors["rivers"], key=lambda record: record["attributes"]["HYRIV_ID"]):
        river_id = river["attributes"]["HYRIV_ID"]
        for part in river["parts_lon_lat"]:
            east, north = transform("EPSG:4326", "EPSG:32651",
                                    [vertex[0] for vertex in part],
                                    [vertex[1] for vertex in part])
            for index in range(len(part) - 1):
                start_x, start_y = east[index], north[index]
                delta_x, delta_y = east[index + 1] - start_x, north[index + 1] - start_y
                squared_length = delta_x * delta_x + delta_y * delta_y
                fraction = 0.0 if squared_length == 0 else max(0.0, min(1.0,
                    ((point[0] - start_x) * delta_x + (point[1] - start_y) * delta_y) / squared_length))
                distance = math.hypot(point[0] - start_x - fraction * delta_x,
                                      point[1] - start_y - fraction * delta_y)
                if distance < best_distance:
                    best_distance, best_id = distance, river_id
    return best_id, best_distance


def plot_map(candidate, report, vectors, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    grid = candidate["manifest"]["identity"]["grid"]
    height = candidate["arrays"]["height_m"]
    valid = candidate["arrays"]["valid_mask"]
    bounds = grid["target_bounds_en_m"]
    extent = [bounds[0] / 1000, bounds[2] / 1000, bounds[1] / 1000, bounds[3] / 1000]
    figure, axes = plt.subplots(1, 2, figsize=(14, 8), constrained_layout=True)
    cmap = plt.get_cmap("terrain").copy()
    cmap.set_bad("#42464b")
    for axis in axes:
        axis.imshow(np.ma.array(height, mask=~valid), extent=extent, cmap=cmap,
                    origin="upper", vmin=-5, vmax=910)
        axis.set_xlabel("UTM easting (km)")
        axis.set_ylabel("UTM northing (km)")
        axis.set_aspect("equal")
    for category, color in (("internal_sink", "#f0cf42"), ("boundary_clip", "#df2935"),
                            ("unknown_adjacent", "#b94aff")):
        points = np.asarray([record["projected_xy_m"] for record in report["outlets"]
                             if record["classification"] == category])
        if len(points):
            axes[0].scatter(points[:, 0] / 1000, points[:, 1] / 1000,
                            s=3 if category == "internal_sink" else 12,
                            c=color, label=f"{category}: {len(points)}", alpha=0.7)
    lines = []
    for river in vectors["rivers"]:
        for part in river["parts_lon_lat"]:
            east, north = transform("EPSG:4326", "EPSG:32651",
                                    [vertex[0] for vertex in part], [vertex[1] for vertex in part])
            lines.append(np.column_stack((east, north)) / 1000)
    axes[1].add_collection(LineCollection(lines, colors="#045cff", linewidths=0.8))
    matched = np.asarray([record["projected_xy_m"] for record in report["outlets"]
                          if record["nearest_hydrovector"]["matched"]])
    if len(matched):
        axes[1].scatter(matched[:, 0] / 1000, matched[:, 1] / 1000,
                        s=6, c="#ff2d65", label=f"within 180 m: {len(matched)}")
    for axis in axes:
        axis.set_xlim(extent[:2])
        axis.set_ylim(extent[2:])
        axis.legend(loc="lower left", fontsize=8)
    axes[0].set_title("Raw downhill terminals; dark gray = unknown DEM")
    axes[1].set_title("HydroRIVERS cross-reference; ocean certification = 0")
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify_package(args.package)
    candidate = load_dem_candidate(DEFAULT_CANDIDATE)
    vectors, audit = read_json(DEFAULT_VECTORS), read_json(DEFAULT_AUDIT)
    height, valid = candidate["arrays"]["height_m"], candidate["arrays"]["valid_mask"]
    network = build_real_dem_network(height, valid)
    terminal_ids = np.flatnonzero((valid & (network.receiver < 0)).ravel())
    assert terminal_ids.tolist() == [record["cell_id"] for record in report["outlets"]]
    counts = {"unknown_adjacent": 0, "boundary_clip": 0, "internal_sink": 0}
    overlap = 0
    for record in report["outlets"]:
        row, col = record["row_col"]
        unknown = bool((~valid[max(0, row - 1):row + 2, max(0, col - 1):col + 2]).any())
        boundary = row in (0, valid.shape[0] - 1) or col in (0, valid.shape[1] - 1)
        category = "unknown_adjacent" if unknown else "boundary_clip" if boundary else "internal_sink"
        assert record["classification"] == category
        assert record["is_unknown_adjacent"] == unknown and record["is_boundary_clip"] == boundary
        assert record["contributing_cells"] == network.accumulation_cells[row, col]
        assert not record["natural_outlet_verified"] and not record["ocean_outlet_certified"]
        counts[category] += 1
        overlap += int(unknown and boundary)
    assert counts == {"unknown_adjacent": 1193, "boundary_clip": 287, "internal_sink": 12891}
    assert overlap == 9
    assert sum(record["contributing_cells"] for record in report["outlets"]) == int(valid.sum())
    sample_ids = set(np.linspace(0, len(report["outlets"]) - 1, 24, dtype=int).tolist())
    for category in counts:
        sample_ids.add(next(index for index, record in enumerate(report["outlets"])
                            if record["classification"] == category))
    max_distance_error = 0.0
    for index in sorted(sample_ids):
        record = report["outlets"][index]
        river_id, distance = nearest_segment(record["projected_xy_m"], vectors)
        assert river_id == record["nearest_hydrovector"]["HYRIV_ID"]
        error = abs(distance - record["nearest_hydrovector"]["distance_m"])
        assert error < 1e-7
        max_distance_error = max(max_distance_error, error)
    tampered = copy.deepcopy(report)
    tampered["outlets"][0]["natural_outlet_verified"] = True
    tampered["content_sha256"] = digest({name: value for name, value in tampered.items()
                                         if name != "content_sha256"})
    try:
        validate_outlet_classification(tampered, candidate, vectors, audit)
    except ValueError:
        forgery_rejected = True
    else:
        raise AssertionError("rehashed natural claim accepted")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "verification") or output.exists():
        raise ValueError("new verification output directory required")
    output.mkdir(parents=True)
    review = {"package": str(args.package.resolve()), "all_terminals_checked": len(terminal_ids),
              "classification_counts": counts, "overlapping_unknown_boundary": overlap,
              "terminal_contribution_sum": int(valid.sum()), "distance_samples": len(sample_ids),
              "maximum_distance_error_m": max_distance_error,
              "rehashed_natural_claim_rejected": forgery_rejected,
              "natural_outlet_verified": False, "summary": report["summary"]}
    (output / "independent-review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    plot_map(candidate, report, vectors, output / "terminal-review.png")
    print(json.dumps(review, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
