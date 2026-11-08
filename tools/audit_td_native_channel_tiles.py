"""Audit saved fine tiles against raw coarse elevations and bounded channel supports."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record


def assemble(records, geometry_identity):
    tiles = [read_record(record) for record in records]
    if not tiles or len(tiles) > 64:
        raise ValueError("bounded nonempty tile set required")
    first = tiles[0][1]
    windows = [metadata["window"] for arrays, metadata in tiles]
    bounds = [min(window[0] for window in windows), max(window[1] for window in windows),
              min(window[2] for window in windows), max(window[3] for window in windows)]
    shape = (bounds[3] - bounds[2] + 1, bounds[1] - bounds[0] + 1)
    if min(shape) < 2 or max(shape) > 1024:
        raise ValueError("assembled lattice budget/extent exceeded")
    combined = {name: np.full(shape, np.nan) for name in
                ("native_bilinear_bed_m", "candidate_cut_m", "candidate_bed_m")}
    counts = np.zeros(shape, dtype=np.int16)
    shared_count = 0
    for arrays, metadata in tiles:
        if (metadata["schema"] != "td-native-channel-tile-v1" or
                metadata["geometry_identity"] != geometry_identity or
                any(metadata[name] != first[name] for name in ("recipe", "origin_m_xz", "coarse_spacing_m")) or
                any(metadata[name] is not False for name in ("hydraulic_ready", "natural_outlet_verified", "publishable"))):
            raise ValueError("tile identity/grid/certification chain mismatch")
        window = metadata["window"]
        lattice_x, lattice_z = np.meshgrid(np.arange(window[0], window[1] + 1),
                                          np.arange(window[2], window[3] + 1))
        np.testing.assert_array_equal(arrays["lattice_x"], lattice_x)
        np.testing.assert_array_equal(arrays["lattice_z"], lattice_z)
        selection = np.s_[window[2] - bounds[2]:window[3] - bounds[2] + 1,
                          window[0] - bounds[0]:window[1] - bounds[0] + 1]
        overlapping = counts[selection] > 0
        shared_count += int(overlapping.sum())
        for name, grid in combined.items():
            values = arrays[name]
            if values.shape != lattice_x.shape or values.dtype != np.float64 or not np.isfinite(values).all():
                raise ValueError("tile sample shape/type/finite mismatch")
            if not np.array_equal(grid[selection][overlapping], values[overlapping]):
                raise ValueError("shared boundary conflict")
            grid[selection] = values
        counts[selection] += 1
    if np.any(counts == 0):
        raise ValueError("uncovered lattice hole")
    if np.any(combined["candidate_cut_m"] < 0):
        raise ValueError("negative incision")
    np.testing.assert_array_equal(combined["candidate_bed_m"],
                                  combined["native_bilinear_bed_m"] - combined["candidate_cut_m"])
    return combined, first, bounds, shared_count


def sample_reference(topology, topology_metadata, geometry, tile_metadata, bounds, grids):
    spacing = tile_metadata["recipe"]["sample_spacing_m"]
    origin = topology_metadata["origin_m_xz"]
    if (origin != tile_metadata["origin_m_xz"] or
            topology_metadata["spacing_m"] != tile_metadata["coarse_spacing_m"]):
        raise ValueError("native coordinate chain mismatch")
    lattice_x, lattice_z = np.meshgrid(np.arange(bounds[0], bounds[1] + 1),
                                      np.arange(bounds[2], bounds[3] + 1))
    grid_x = lattice_x * spacing / topology_metadata["spacing_m"]
    grid_z = lattice_z * spacing / topology_metadata["spacing_m"]
    height = topology["height_m"]
    lower_x, lower_z = np.floor(grid_x).astype(int), np.floor(grid_z).astype(int)
    if np.any(lower_x < 0) or np.any(lower_z < 0) or np.any(grid_x > height.shape[1] - 1) or np.any(grid_z > height.shape[0] - 1):
        raise ValueError("sample outside native grid")
    upper_x = np.minimum(lower_x + 1, height.shape[1] - 1)
    upper_z = np.minimum(lower_z + 1, height.shape[0] - 1)
    for sample_x, sample_z in ((lower_x, lower_z), (upper_x, lower_z), (lower_x, upper_z), (upper_x, upper_z)):
        if not topology["valid_mask"][sample_z, sample_x].all():
            raise ValueError("unknown native interpolation stencil")
    fraction_x, fraction_z = grid_x - lower_x, grid_z - lower_z
    reference = (height[lower_z, lower_x] * (1 - fraction_x) * (1 - fraction_z) +
                 height[lower_z, upper_x] * fraction_x * (1 - fraction_z) +
                 height[upper_z, lower_x] * (1 - fraction_x) * fraction_z +
                 height[upper_z, upper_x] * fraction_x * fraction_z)
    native_error = float(np.max(np.abs(reference - grids["native_bilinear_bed_m"])))
    if native_error > 2e-12:
        raise ValueError("native interpolation differs from raw source")
    chosen = np.unique(np.concatenate((np.linspace(0, reference.size - 1, min(1024, reference.size), dtype=int),
                                       np.argsort(grids["candidate_cut_m"].ravel())[-64:])))
    points = np.column_stack((origin[0] + lattice_x.ravel()[chosen] * spacing,
                              origin[1] + lattice_z.ravel()[chosen] * spacing))
    incision = np.zeros(len(chosen))
    node_positions = {int(cell): position for position, cell in enumerate(geometry["node_cell_ids"])}
    active_ids = np.flatnonzero(geometry["edge_geometry_active"])
    for edge_id in active_ids:
        cell_ids = geometry["edge_cell_ids"][edge_id]
        indices = [node_positions[int(cell)] for cell in cell_ids]
        endpoints = geometry["node_world_xyz_m"][indices][:, [0, 2]]
        widths = geometry["node_width_m"][indices]
        cuts = geometry["node_candidate_incision_m"][indices]
        if (np.any(points.max(axis=0) < endpoints.min(axis=0) - max(widths) / 2) or
                np.any(points.min(axis=0) > endpoints.max(axis=0) + max(widths) / 2)):
            continue
        direction = endpoints[1] - endpoints[0]
        length = float(np.linalg.norm(direction))
        tangent = direction / length
        distance_along = (points - endpoints[0]) @ tangent
        fraction = np.clip(distance_along / length, 0, 1)
        closest = endpoints[0] + fraction[:, None] * direction
        radial_distance = np.linalg.norm(points - closest, axis=1)
        half_width = np.interp(fraction, [0., 1.], widths) / 2
        local_cut = np.zeros(len(chosen))
        supported = radial_distance < half_width
        local_cut[supported] = np.interp(fraction[supported], [0., 1.], cuts) * np.cos(
            np.pi * radial_distance[supported] / (2 * half_width[supported])) ** 2
        incision = np.maximum(incision, local_cut)
    cut_error = float(np.max(np.abs(incision - grids["candidate_cut_m"].ravel()[chosen])))
    if cut_error > 2e-12:
        raise ValueError("sampled incision differs from active channel support")
    return dict(native_samples=reference.size, native_max_error_m=native_error,
                independent_cut_samples=len(chosen), cut_max_error_m=cut_error,
                active_edges_considered=len(active_ids))


def audit(report_path, report_sha256, geometry_report_path, geometry_report_sha256):
    paths = [(Path(report_path), report_sha256), (Path(geometry_report_path), geometry_report_sha256)]
    for path, digest in paths:
        if path.stat().st_size > 1024 ** 2 or file_sha256(path) != digest:
            raise ValueError("external prototype pin/budget mismatch")
    report, geometry_report = [json.loads(path.read_text(encoding="utf-8")) for path, digest in paths]
    if report["geometry"] != geometry_report["geometry"]:
        raise ValueError("prototype geometry chain mismatch")
    geometry, geometry_metadata = read_record(report["geometry"])
    topology, topology_metadata = read_record(geometry_report["inputs"]["hierarchy"])
    if geometry_metadata["hierarchy_identity"] != geometry_report["inputs"]["hierarchy"]["expected_identity"]:
        raise ValueError("hierarchy geometry link mismatch")
    grids, metadata, bounds, shared_count = assemble(report["tiles"], report["geometry"]["expected_identity"])
    reverse, reverse_metadata, reverse_bounds, reverse_shared = assemble(list(reversed(report["tiles"])), report["geometry"]["expected_identity"])
    for name in grids:
        np.testing.assert_array_equal(grids[name], reverse[name])
    reference = sample_reference(topology, topology_metadata, geometry, metadata, bounds, grids)
    for path, digest in paths:
        if file_sha256(path) != digest:
            raise ValueError("prototype changed during audit")
    return dict(schema="td-independent-native-channel-tiles-v1", accepted=True,
                tile_report=dict(path=str(paths[0][0].resolve()), expected_sha256=report_sha256),
                geometry_report=dict(path=str(paths[1][0].resolve()), expected_sha256=geometry_report_sha256),
                tiles=report["tiles"], window=bounds, shape=list(grids["candidate_bed_m"].shape),
                duplicate_sample_checks=shared_count, shared_boundaries_exact=True,
                loading_order_independent=True, maximum_cut_m=float(grids["candidate_cut_m"].max()),
                **reference, hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                scope="raw native bilinear elevations verified at all points; channel cut verified at stated samples; expression only")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--geometry-report", type=Path, required=True)
    parser.add_argument("--geometry-report-sha256", required=True)
    arguments = parser.parse_args()
    result = audit(arguments.report, arguments.report_sha256, arguments.geometry_report, arguments.geometry_report_sha256)
    directory = ROOT / "verification/td-native-channel-tiles" / ("independent-audit-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / "report.json"
    publish_bytes(path, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(path), sha256=file_sha256(path), **result), ensure_ascii=True))


if __name__ == "__main__":
    main()
