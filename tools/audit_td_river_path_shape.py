"""Audit angular saved routing paths without generating or changing terrain."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

from terrain_pipeline.drainage import decode_routing_comparison as decode_routing_comparison
from terrain_pipeline.drainage import load_routing_comparison as load_routing_comparison
from terrain_pipeline.drainage import grid_mesh as grid_mesh


def path_statistics(graph, columns, fill_depth_m, mesh):
    """Count directed edge pairs, including distinct incoming arms at junctions."""
    receiver = graph.receiver
    donors = np.flatnonzero(receiver >= 0)
    targets = receiver[donors]
    dr = np.zeros(receiver.size, np.float64)
    dc = np.zeros(receiver.size, np.float64)
    dr[donors] = mesh.node_z_m[targets] - mesh.node_z_m[donors]
    dc[donors] = mesh.node_x_m[targets] - mesh.node_x_m[donors]
    dr[donors] /= graph.edge_length_m[donors]
    dc[donors] /= graph.edge_length_m[donors]
    pairs = donors[receiver[targets] >= 0]
    following = receiver[pairs]
    dot = dr[pairs] * dr[following] + dc[pairs] * dc[following]
    cross = dr[pairs] * dc[following] - dc[pairs] * dr[following]
    same = np.isclose(dot, 1., atol=1e-10, rtol=0.)
    right = np.isclose(dot, 0., atol=1e-10, rtol=0.)
    flat = graph.edge_slope == 0.
    filled = fill_depth_m.ravel() > 0.
    straight_length = np.zeros(receiver.size, np.float64)
    flat_length = np.zeros(receiver.size, np.float64)
    # The saved downstream-first order makes each receiver's run available.
    for cell in graph.order_downstream_first:
        target = receiver[cell]
        if target < 0:
            continue
        matching = (receiver[target] >= 0
                    and abs(dr[cell] * dr[target] + dc[cell] * dc[target] - 1.) <= 1e-10)
        straight_length[cell] = graph.edge_length_m[cell]
        if matching:
            straight_length[cell] += straight_length[target]
        if flat[cell]:
            flat_length[cell] = graph.edge_length_m[cell]
            if matching and flat[target]:
                flat_length[cell] += flat_length[target]
    start = int(np.argmax(flat_length))
    bearings = np.degrees(np.arctan2(dr[donors], dc[donors])) % 360.
    bins, _ = np.histogram(bearings, bins=np.arange(0., 361., 15.))
    directions = {f"bearing_deg=[{15 * index},{15 * (index + 1)})": int(count)
                  for index, count in enumerate(bins)}
    return {
        "edge_count": int(donors.size), "direction_histogram": directions,
        "zero_slope_edge_count": int(np.count_nonzero(flat[donors])),
        "filled_source_edge_count": int(np.count_nonzero(filled[donors])),
        "zero_slope_filled_source_edge_count": int(np.count_nonzero((flat & filled)[donors])),
        "consecutive_edge_pair_count": int(pairs.size),
        "straight_pair_count": int(same.sum()),
        "right_angle_pair_count": int(np.count_nonzero(right)),
        "right_angle_flat_pair_count": int(np.count_nonzero(right & flat[pairs] & flat[following])),
        "right_angle_filled_pair_count": int(np.count_nonzero(right & filled[pairs] & filled[following])),
        "other_bend_pair_count": int(np.count_nonzero(~same & ~right)),
        "collinear_reverse_pair_count": int(np.count_nonzero(np.isclose(cross, 0., atol=1e-10, rtol=0.) & (dot < 0))),
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
    spacing = comparison["metadata"]["terrain"]
    mesh = grid_mesh(height.shape, x0_m=spacing["x0_m"], z0_m=spacing["z0_m"],
                     dx_m=spacing["dx_m"], dz_m=spacing["dz_m"],
                     world_seed=spacing.get("generation_seed") or 20261020)
    summaries = {name: path_statistics(graph, columns, fill, mesh) for name, graph in graphs.items()}
    flood = graphs["priority_flood_irregular"]
    first = summaries["priority_flood_irregular"]["longest_zero_slope_straight_run_start_cell"]
    path = [first]
    target = int(flood.receiver[first])
    if target >= 0:
        direction = np.array([mesh.node_x_m[target] - mesh.node_x_m[first],
                              mesh.node_z_m[target] - mesh.node_z_m[first]]) / flood.edge_length_m[first]
        while target >= 0:
            path.append(target)
            following = int(flood.receiver[target])
            if following < 0 or flood.edge_slope[target] != 0.:
                break
            next_direction = np.array([mesh.node_x_m[following] - mesh.node_x_m[target],
                                       mesh.node_z_m[following] - mesh.node_z_m[target]]) / flood.edge_length_m[target]
            if not np.allclose(next_direction, direction, atol=1e-10, rtol=0.):
                break
            target = following
    center = path[len(path) // 2]
    radius = 64
    r0, r1 = max(0, center // columns - radius), min(rows, center // columns + radius + 1)
    c0, c1 = max(0, center % columns - radius), min(columns, center % columns + radius + 1)
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "td-river-path-shape-audit-v2", "comparison_pin": pin,
              "source_sha256": manifest["source_sha256"], "policies": summaries,
              "zoom_window_zx_half_open": [r0, r1, c0, c1],
              "pair_semantics": "one pair per incoming edge whose receiver also has an outgoing edge; junction arms counted separately",
              "preview_edge_selection": "top_3_percent_contributing_cell_count_in_full_graph; not hydraulic_Q",
              "limitations": ["bounded irregular graph topology", "fill plateaus have deterministic graph flood directions",
                              "no path smoothing, terrain regeneration, or hydraulic solve performed"]}
    (output / "path-shape-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    spacing = comparison["metadata"]["terrain"]
    dx, dz = spacing["dx_m"], spacing["dz_m"]
    extent = (c0 * dx - dx / 2., c1 * dx - dx / 2., r1 * dz - dz / 2., r0 * dz - dz / 2.)
    fig, axes = plt.subplots(1, 3, figsize=(16, 6), sharex=True, sharey=True)
    for axis, (name, graph) in zip(axes, graphs.items()):
        working = arrays["working_elevation_m"] if name == "priority_flood_irregular" else height
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
        starts = np.column_stack((mesh.node_x_m[selected] - spacing["x0_m"],
                                  mesh.node_z_m[selected] - spacing["z0_m"]))
        ends = np.column_stack((mesh.node_x_m[targets] - spacing["x0_m"],
                                mesh.node_z_m[targets] - spacing["z0_m"]))
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
