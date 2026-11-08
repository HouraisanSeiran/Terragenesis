"""Independent shared-node, metric-coordinate and OBJ geometry audit."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.dem_domain import load_dem_candidate
from tools.verify_real_dem_outlet_classification import DEFAULT_CANDIDATE, canonical_bytes, check_unchanged, read_json, source_record
from tools.verify_real_dem_rainfall_routing import DEFAULT_FLAT


def independent_audit(candidate, geometry, flat):
    ids = geometry["node_ids"]
    if not np.array_equal(ids, np.unique(ids)):
        raise ValueError("node IDs must be globally unique and sorted")
    valid = candidate["arrays"]["valid_mask"].ravel()
    height = candidate["arrays"]["height_m"].ravel()
    expected_ids = np.flatnonzero(valid & (flat["accumulation_cells"].ravel() >= 100))
    np.testing.assert_array_equal(ids, expected_ids)
    grid = candidate["manifest"]["identity"]["grid"]
    rows, cols = np.divmod(ids, candidate["arrays"]["height_m"].shape[1])
    expected_xyz = np.column_stack((grid["origin_x_m"] + cols * grid["spacing_x_m"], height[ids],
                                    grid["origin_z_m"] + rows * grid["spacing_z_m"]))
    np.testing.assert_array_equal(geometry["node_xyz"], expected_xyz)
    targets = flat["receiver"].ravel()[ids]
    expected_edges = np.column_stack((ids[targets >= 0], targets[targets >= 0]))
    np.testing.assert_array_equal(geometry["edges"], expected_edges)
    np.testing.assert_array_equal(geometry["edge_ids"], expected_edges[:, 0])
    source, target = np.searchsorted(ids, expected_edges[:, 0]), np.searchsorted(ids, expected_edges[:, 1])
    if np.any(expected_xyz[target, 1] > expected_xyz[source, 1]):
        raise ValueError("uphill reference edge")
    donors = np.bincount(target, minlength=len(ids))
    np.testing.assert_array_equal(donors, geometry["donor_count"])
    np.testing.assert_array_equal(geometry["junctions"], donors > 1)
    sections = geometry["cross_sections"]
    np.testing.assert_array_equal(sections, np.tile([20., 1., 20.], (len(ids), 1)))
    vertices = geometry["vertices"]
    if vertices.shape != (2 * len(ids), 3):
        raise ValueError("shared bank vertex cardinality mismatch")
    banks = vertices.reshape(len(ids), 2, 3)
    np.testing.assert_allclose(banks.mean(axis=1), expected_xyz - [0., 1., 0.], rtol=0, atol=1e-8)
    np.testing.assert_allclose(np.linalg.norm(banks[:, 0] - banks[:, 1], axis=1), 20., rtol=0, atol=1e-8)
    faces = geometry["faces"]
    expected_faces = np.empty((len(expected_edges) * 2, 3), np.int64)
    expected_faces[0::2] = np.column_stack((2 * source, 2 * source + 1, 2 * target))
    expected_faces[1::2] = np.column_stack((2 * source + 1, 2 * target + 1, 2 * target))
    np.testing.assert_array_equal(faces, expected_faces)
    triangle = vertices[faces]
    areas = np.linalg.norm(np.cross(triangle[:, 1] - triangle[:, 0], triangle[:, 2] - triangle[:, 0]), axis=1) / 2
    np.testing.assert_array_equal(geometry["degenerate_face_ids"], np.flatnonzero(areas <= 5e-11))
    seams = {}
    for tile_size in (128, 256, 512):
        source_rows, source_cols = np.divmod(expected_edges[:, 0], candidate["arrays"]["height_m"].shape[1])
        target_rows, target_cols = np.divmod(expected_edges[:, 1], candidate["arrays"]["height_m"].shape[1])
        seams[str(tile_size)] = int(np.count_nonzero((source_rows // tile_size != target_rows // tile_size)
                                                   | (source_cols // tile_size != target_cols // tile_size)))
    return {"method": "independent_global_ID_coordinate_D8_shared_bank_and_triangle_checks",
            "node_count": len(ids), "edge_count": len(expected_edges), "head_count": int((donors == 0).sum()),
            "junction_count": int((donors > 1).sum()), "terminal_count": int((targets == -1).sum()),
            "shared_vertices": len(vertices), "triangle_count": len(faces),
            "degenerate_triangles": int((areas <= 5e-11).sum()), "cross_tile_edges": seams,
            "source_height_equal": True, "no_unknown_nodes": True,
            "width_depth_area_m": [20., 1., 20.], "hydraulic_ready": False,
            "natural_outlet_verified": False, "publishable": False}


def plot_junction(candidate, geometry, flat, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    ids = geometry["node_ids"]
    junctions = np.flatnonzero(geometry["junctions"])
    if not len(junctions):
        raise ValueError("real prototype lacks a two-tributary junction")
    accumulation = flat["accumulation_cells"].ravel()[ids]
    junction = int(junctions[np.argmax(accumulation[junctions])])
    edges = geometry["edges"]
    source, target = np.searchsorted(ids, edges[:, 0]), np.searchsorted(ids, edges[:, 1])
    downstream = {int(start): int(end) for start, end in zip(source, target)}
    donors = {int(end): [] for end in target}
    for start, end in zip(source, target):
        donors[int(end)].append(int(start))
    selected = {junction}
    for branch in sorted(donors[junction], key=lambda cell: -accumulation[cell])[:2]:
        current = branch
        for unused in range(40):
            selected.add(current)
            upstream = donors.get(current, [])
            if not upstream:
                break
            current = max(upstream, key=lambda cell: accumulation[cell])
    current = junction
    for unused in range(40):
        selected.add(current)
        if current not in downstream:
            break
        current = downstream[current]
    edge_mask = np.isin(source, list(selected)) & np.isin(target, list(selected))
    face_mask = np.repeat(edge_mask, 2)
    vertices = geometry["vertices"] - geometry["node_xyz"][junction]
    xyz = geometry["node_xyz"] - geometry["node_xyz"][junction]
    figure = plt.figure(figsize=(12, 8))
    axis = figure.add_subplot(111, projection="3d")
    triangle = vertices[geometry["faces"][face_mask]][:, :, [0, 2, 1]]
    axis.add_collection3d(Poly3DCollection(triangle, alpha=.6, facecolor="#4388b4", edgecolor="#2b5266", linewidth=.3))
    for start, end in zip(source[edge_mask], target[edge_mask]):
        points = xyz[[start, end]]
        axis.plot(points[:, 0], points[:, 2], points[:, 1], color="#b7472a", linewidth=1.5)
    chosen = xyz[list(selected)]
    axis.auto_scale_xyz(chosen[:, 0], chosen[:, 2], chosen[:, 1])
    axis.set_xlabel("East offset (m)")
    axis.set_ylabel("South offset (m)")
    axis.set_zlabel("Elevation offset (m)")
    axis.set_title("Real DEM main stem + two tributaries\nIllustrative shared-bank bed ribbon: width20m/depth1m; no solved water surface")
    figure.tight_layout()
    figure.savefig(output, dpi=150)
    plt.close(figure)
    return {"junction_global_cell_id": int(ids[junction]), "display_nodes": len(selected),
            "display_edges": int(edge_mask.sum()), "scope": "selected_two_tributary_neighborhood_not_whole_network"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry-package", type=Path, required=True)
    args = parser.parse_args()
    manifest = read_json(args.geometry_package / "manifest.json")
    records = list(manifest["inputs"])
    for name, declaration in manifest["artifacts"].items():
        record = source_record(args.geometry_package / name)
        if record["sha256"] != declaration["sha256"] or record["bytes"] != declaration["bytes"]:
            raise ValueError("geometry source artifact hash mismatch")
        records.append(record)
    check_unchanged(records)
    candidate = load_dem_candidate(DEFAULT_CANDIDATE, verify_source=True)
    with np.load(args.geometry_package / "geometry.npz", allow_pickle=False) as archive:
        geometry = {name: archive[name] for name in archive.files}
    with np.load(DEFAULT_FLAT / "network.npz", allow_pickle=False) as archive:
        flat = {name: archive[name] for name in archive.files}
    result = independent_audit(candidate, geometry, flat)
    output = ROOT / "verification/real-dem-3d-independent-review" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True)
    result["display_selection"] = plot_junction(candidate, geometry, flat, output / "two-tributary-prototype.png")
    result["inputs"] = records
    check_unchanged(records)
    (output / "independent-review.json").write_bytes(canonical_bytes(result))
    print(str(output))


if __name__ == "__main__":
    main()
