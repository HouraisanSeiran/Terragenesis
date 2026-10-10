"""Audit angular saved routing paths without generating or changing terrain."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

from terrain_pipeline.surface_rivers.metric_routing_comparison import (
    decode_routing_comparison, load_routing_comparison,
)


def path_statistics(graph, columns, fill_depth_m):
    """Count directed edge pairs, including distinct incoming arms at junctions."""
    receiver = graph.receiver
    donors = np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    dr = np.zeros(receiver.size, np.int64)
    dc = np.zeros(receiver.size, np.int64)
    dr[donors] = targets // columns - donors // columns
    dc[donors] = targets % columns - donors % columns
    pairs = donors[receiver[targets] >= 0]
    following = receiver[pairs]
    dot = dr[pairs] * dr[following] + dc[pairs] * dc[following]
    cross = dr[pairs] * dc[following] - dc[pairs] * dr[following]
    same = (dr[pairs] == dr[following]) & (dc[pairs] == dc[following])
    flat = graph.edge_slope == 0.
    filled = fill_depth_m.ravel() > 0.
    straight_length = np.zeros(receiver.size, np.float64)
    flat_length = np.zeros(receiver.size, np.float64)
    # The saved downstream-first order makes each receiver's run available.
    for cell in graph.order_downstream_first:
        target = receiver[cell]
        if target < 0:
            continue
        matching = receiver[target] >= 0 and dr[cell] == dr[target] and dc[cell] == dc[target]
        straight_length[cell] = graph.edge_length_m[cell]
        if matching:
            straight_length[cell] += straight_length[target]
        if flat[cell]:
            flat_length[cell] = graph.edge_length_m[cell]
            if matching and flat[target]:
                flat_length[cell] += flat_length[target]
    start = int(np.argmax(flat_length))
    directions = {}
    for row_delta, column_delta in sorted(set(zip(dr[donors].tolist(), dc[donors].tolist()))):
        directions[f"dz={row_delta},dx={column_delta}"] = int(np.count_nonzero(
            (dr[donors] == row_delta) & (dc[donors] == column_delta)))
    return {
        "edge_count": int(donors.size), "direction_histogram": directions,
        "zero_slope_edge_count": int(np.count_nonzero(flat[donors])),
        "filled_source_edge_count": int(np.count_nonzero(filled[donors])),
        "zero_slope_filled_source_edge_count": int(np.count_nonzero((flat & filled)[donors])),
        "consecutive_edge_pair_count": int(pairs.size),
        "straight_pair_count": int(same.sum()),
        "right_angle_pair_count": int(np.count_nonzero(dot == 0)),
        "right_angle_flat_pair_count": int(np.count_nonzero((dot == 0) & flat[pairs] & flat[following])),
        "right_angle_filled_pair_count": int(np.count_nonzero((dot == 0) & filled[pairs] & filled[following])),
        "other_bend_pair_count": int(np.count_nonzero(~same & (dot != 0))),
        "collinear_reverse_pair_count": int(np.count_nonzero((cross == 0) & (dot < 0))),
        "longest_straight_run_m": float(straight_length.max()),
        "longest_zero_slope_straight_run_m": float(flat_length.max()),
        "longest_zero_slope_straight_run_start_cell": start,
        "graph_identity_sha256": graph.identity_sha256,
    }


def audit_saved(directory, output):
    directory, output = Path(directory).resolve(), Path(output).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    pin = manifest["artifacts"]["routing-comparison"]
    comparison = load_routing_comparison(directory / pin["path"], expected_sha256=pin["sha256"],
                                         expected_identity=pin["identity_sha256"])
    graphs = decode_routing_comparison(comparison)
    arrays = comparison["arrays"]
    height, fill = arrays["elevation_m"], arrays["fill_depth_m"]
    rows, columns = height.shape
    summaries = {name: path_statistics(graph, columns, fill) for name, graph in graphs.items()}
    flood = graphs["priority_flood_d8"]
    first = summaries["priority_flood_d8"]["longest_zero_slope_straight_run_start_cell"]
    path = [first]
    target = int(flood.receiver[first])
    if target >= 0:
        direction = (target // columns - first // columns, target % columns - first % columns)
        while target >= 0:
            path.append(target)
            following = int(flood.receiver[target])
            if following < 0 or flood.edge_slope[target] != 0.:
                break
            if (following // columns - target // columns, following % columns - target % columns) != direction:
                break
            target = following
    center = path[len(path) // 2]
    radius = 64
    r0, r1 = max(0, center // columns - radius), min(rows, center // columns + radius + 1)
    c0, c1 = max(0, center % columns - radius), min(columns, center % columns + radius + 1)
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "td-river-path-shape-audit-v1", "comparison_pin": pin,
              "source_sha256": manifest["source_sha256"], "policies": summaries,
              "zoom_window_zx_half_open": [r0, r1, c0, c1],
              "pair_semantics": "one pair per incoming edge whose receiver also has an outgoing edge; junction arms counted separately",
              "preview_edge_selection": "top_3_percent_contributing_cell_count_in_full_graph; not hydraulic_Q",
              "limitations": ["D8/D4 center-to-center topology", "fill plateaus have deterministic BFS directions",
                              "no path smoothing, terrain regeneration, or hydraulic solve performed"]}
    (output / "path-shape-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    spacing = comparison["metadata"]["terrain"]
    dx, dz = spacing["dx_m"], spacing["dz_m"]
    extent = (c0 * dx - dx / 2., c1 * dx - dx / 2., r1 * dz - dz / 2., r0 * dz - dz / 2.)
    fig, axes = plt.subplots(1, 3, figsize=(16, 6), sharex=True, sharey=True)
    for axis, (name, graph) in zip(axes, graphs.items()):
        working = arrays["working_elevation_m"] if name == "priority_flood_d8" else height
        axis.imshow(working[r0:r1, c0:c1], extent=extent, cmap="terrain")
        count = np.ones(height.size, np.float64)
        for cell in graph.order_downstream_first[::-1]:
            target = graph.receiver[cell]
            if target >= 0:
                count[target] += count[cell]
        edges = np.flatnonzero(graph.receiver >= 0)
        threshold = np.percentile(count[edges], 97.)
        selected = edges[(count[edges] >= threshold) & (edges // columns >= r0)
                         & (edges // columns < r1) & (edges % columns >= c0) & (edges % columns < c1)]
        targets = graph.receiver[selected]
        starts = np.column_stack((selected % columns * dx, selected // columns * dz))
        ends = np.column_stack((targets % columns * dx, targets // columns * dz))
        lines = np.stack((starts, ends), axis=1)
        colors = np.where(graph.edge_slope[selected] == 0., "#dd2770", "#0874c4")
        axis.add_collection(LineCollection(lines, colors=colors, linewidths=1.1))
        axis.contour(np.arange(c0, c1) * dx, np.arange(r0, r1) * dz,
                     height[r0:r1, c0:c1], levels=12, colors="black", linewidths=.3, alpha=.3)
        axis.set_title(name.replace("_", " "), fontsize=12)
        axis.set_xlabel("Source-grid X offset (m)")
        axis.set_aspect("equal")
    axes[0].set_ylabel("Source-grid Z offset (m)")
    fig.suptitle("Saved real TD routes: blue downhill edges, pink exactly-flat edges\n"
                 "Raw-bed contours; middle background is filled working surface; 30 m cells", fontsize=13)
    fig.tight_layout(rect=(0., 0., 1., .89))
    fig.savefig(output / "angular-path-closeup.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_saved(args.input, args.output), indent=2))


if __name__ == "__main__":
    main()
