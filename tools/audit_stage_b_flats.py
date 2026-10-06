"""Independent sparse connectivity and distance audit of the flat work graph."""

import argparse
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.artifacts.contracts import array_hash
from terrain_pipeline.dem_domain import load_dem_candidate
from tools.verify_real_dem_outlet_classification import DEFAULT_CANDIDATE, canonical_bytes, source_record


def independent_graph(candidate, arrays):
    height_grid = candidate["arrays"]["height_m"]
    valid_grid = candidate["arrays"]["valid_mask"]
    rows, cols = height_grid.shape
    height, valid = height_grid.ravel(), valid_grid.ravel()
    ids_grid = np.arange(height.size).reshape(height_grid.shape)
    source_parts, target_parts = [], []
    raw = np.full(height.size, -1, np.int64)
    best = height.copy()
    unknown = np.zeros(height.size, bool)
    for delta_row, delta_col in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1),
                                 (1, -1), (1, 0), (1, 1)):
        source_rows = slice(max(0, -delta_row), min(rows, rows - delta_row))
        source_cols = slice(max(0, -delta_col), min(cols, cols - delta_col))
        target_rows = slice(max(0, delta_row), min(rows, rows + delta_row))
        target_cols = slice(max(0, delta_col), min(cols, cols + delta_col))
        source = ids_grid[source_rows, source_cols].ravel()
        target = ids_grid[target_rows, target_cols].ravel()
        unknown[source] |= valid[source] & ~valid[target]
        lower = valid[source] & valid[target] & (height[target] < best[source])
        raw[source[lower]] = target[lower]
        best[source[lower]] = height[target[lower]]
        equal = valid[source] & valid[target] & (height[source] == height[target])
        source_parts.append(source[equal])
        target_parts.append(target[equal])
    equal_source, equal_target = np.concatenate(source_parts), np.concatenate(target_parts)
    graph = coo_matrix((np.ones(equal_source.size, np.int8), (equal_source, equal_target)),
                       shape=(height.size, height.size)).tocsr()
    count, labels = connected_components(graph, directed=False)
    minimum = np.full(count, height.size, np.int64)
    np.minimum.at(minimum, labels[valid], np.flatnonzero(valid))
    components = np.where(valid, minimum[labels], -1)
    np.testing.assert_array_equal(arrays["component_id"].ravel(), components)
    component_seeds = np.zeros(height.size, np.int64)
    np.add.at(component_seeds, components[raw >= 0], 1)
    roots = np.flatnonzero(valid & (components == np.arange(height.size)) & (component_seeds == 0))
    seeds = np.sort(np.concatenate((np.flatnonzero(raw >= 0), roots)))
    distance = np.full(height.size, -1, np.int64)
    distance[seeds] = 0
    queue = deque(seeds.tolist())
    while queue:
        cell = queue.popleft()
        for target in graph.indices[graph.indptr[cell]:graph.indptr[cell + 1]]:
            if distance[target] < 0:
                distance[target] = distance[cell] + 1
                queue.append(int(target))
    np.testing.assert_array_equal(arrays["distance_to_exit"].ravel(), distance)
    receiver = raw.copy()
    for cell in np.flatnonzero(valid & (distance > 0)):
        neighbors = graph.indices[graph.indptr[cell]:graph.indptr[cell + 1]]
        receiver[cell] = np.min(neighbors[distance[neighbors] == distance[cell] - 1])
    np.testing.assert_array_equal(arrays["receiver"].ravel(), receiver)
    valid_ids = np.flatnonzero(valid)
    independent_order = valid_ids[np.lexsort((valid_ids, -distance[valid], -height[valid]))]
    accumulation = np.zeros(height.size, np.float64)
    accumulation[valid] = 1
    for cell in independent_order:
        if receiver[cell] >= 0:
            accumulation[receiver[cell]] += accumulation[cell]
    np.testing.assert_array_equal(arrays["accumulation_cells"].ravel(), accumulation)
    boundary = np.zeros(height_grid.shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    component_unknown = np.zeros(height.size, bool)
    component_boundary = np.zeros(height.size, bool)
    np.logical_or.at(component_unknown, components[valid], unknown[valid])
    np.logical_or.at(component_boundary, components[valid], boundary.ravel()[valid])
    terminals = np.flatnonzero(valid & (receiver == -1))
    categories = np.where(component_unknown[terminals], "unknown_boundary",
                          np.where(component_boundary[terminals], "engineering_boundary_candidate", "internal_retention"))
    risk_counts = {name: int(np.count_nonzero(categories == name)) for name in
                   ("unknown_boundary", "engineering_boundary_candidate", "internal_retention")}
    contributions = {name: int(accumulation[terminals[categories == name]].sum()) for name in risk_counts}
    root_only_unknown = unknown[terminals]
    root_only_boundary = boundary.ravel()[terminals]
    return {"independent_method": "scipy_sparse_equal_D8_components_and_global_multisource_BFS",
            "valid_cells": int(valid.sum()), "unknown_cells": int((~valid).sum()),
            "equal_components": int(np.count_nonzero(minimum < height.size)),
            "raw_terminals": int(np.count_nonzero(valid & (raw == -1))),
            "resolved_terminals": len(terminals), "flat_rerouted_edges": int(np.count_nonzero(receiver != raw)),
            "terminal_risk_counts": risk_counts, "terminal_risk_contributing_cells": contributions,
            "contributing_cells_sum": int(accumulation[terminals].sum()),
            "unknown_risks_missed_by_root_only": int(np.count_nonzero(component_unknown[terminals] & ~root_only_unknown)),
            "boundary_risks_missed_by_root_only": int(np.count_nonzero(component_boundary[terminals] & ~root_only_boundary)),
            "source_height_sha256": array_hash(height_grid),
            "natural_outlet_verified": False, "ocean_outlet_certified": False,
            "exact_receiver_component_distance_accumulation_equal": True}


def plot(candidate, raw, resolved, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    valid = candidate["arrays"]["valid_mask"]
    height = candidate["arrays"]["height_m"]
    bounds = candidate["manifest"]["identity"]["grid"]["target_bounds_en_m"]
    extent = [bounds[0] / 1000, bounds[2] / 1000, bounds[1] / 1000, bounds[3] / 1000]
    figure, axes = plt.subplots(1, 2, figsize=(14, 8), constrained_layout=True)
    background = plt.get_cmap("gray").copy()
    background.set_bad("#343840")
    for axis, arrays, title in zip(axes, (raw, resolved), ("Raw strict D8", "Equal-height connectivity; no terrain edits")):
        axis.imshow(np.ma.array(height, mask=~valid), extent=extent, origin="upper", cmap=background, alpha=.7)
        accumulation = arrays["accumulation_cells"]
        rivers = np.ma.array(np.log10(np.maximum(accumulation, 1)), mask=~valid | (accumulation < 100))
        axis.imshow(rivers, extent=extent, origin="upper", cmap="winter", vmin=2, vmax=5)
        terminal = valid & (arrays["receiver"] < 0)
        cell_rows, cell_cols = np.nonzero(terminal)
        east = bounds[0] + (cell_cols + .5) * 90
        north = bounds[3] - (cell_rows + .5) * 90
        axis.scatter(east / 1000, north / 1000, s=2, c="#ff9c35", alpha=.5)
        axis.set_title(f"{title}\n{terminal.sum()} unresolved terminals (orange)")
        axis.set_xlabel("UTM easting (km)")
        axis.set_ylabel("UTM northing (km)")
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flat-package", type=Path, required=True)
    parser.add_argument("--raw-package", type=Path, default=ROOT / "verification/real-dem-tiled-network/run-20261001T153332885702Z")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    args = parser.parse_args()
    from tools.verify_real_dem_flat_routing import verify_package
    verify_package(args.flat_package, candidate_path=args.candidate)
    sources = [source_record(args.candidate), source_record(args.flat_package / "manifest.json"),
               source_record(args.raw_package / "manifest.json")]
    candidate = load_dem_candidate(args.candidate, verify_source=True)
    with np.load(args.flat_package / "network.npz", allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    with np.load(args.raw_package / "network.npz", allow_pickle=False) as archive:
        raw = {name: archive[name] for name in archive.files}
    report = independent_graph(candidate, arrays)
    report["inputs"] = sources
    output = ROOT / "verification/real-dem-flat-independent-review" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True)
    plot(candidate, raw, arrays, output / "connectivity-comparison.png")
    if sources != [source_record(record["path"]) for record in sources]:
        raise ValueError("source changed during independent audit")
    (output / "independent-review.json").write_bytes(canonical_bytes(report))
    print(json.dumps({"output": str(output), **report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
