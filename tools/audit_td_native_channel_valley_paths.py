"""Check saved visual paths against raw original graph, stencils and basin owners."""

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


def audit(report_path, expected_sha256):
    report_path = Path(report_path).resolve(strict=True)
    if file_sha256(report_path) != expected_sha256 or report_path.stat().st_size > 1024 ** 2:
        raise ValueError("visual path report external pin/budget mismatch")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    paths, metadata = read_record(report["paths"])
    graph, geometry_metadata = read_record(report["geometry"])
    topology, hierarchy_metadata = read_record(report["hierarchy"])
    if any(metadata[name] != geometry_metadata[name] for name in ("hierarchy_identity", "hour_page_identity", "forcing_identity")):
        raise ValueError("visual path source identity mismatch")
    if metadata["geometry_identity"] != report["geometry"]["expected_identity"] or metadata["hierarchy_identity"] != report["hierarchy"]["expected_identity"]:
        raise ValueError("visual path graph/hierarchy link mismatch")
    origin = np.asarray(hierarchy_metadata["origin_m_xz"])
    spacing = hierarchy_metadata["spacing_m"]
    rows, columns = topology["height_m"].shape
    window = metadata["window"]
    expected = []
    for index in np.flatnonzero(graph["edge_geometry_active"]):
        cells = graph["edge_cell_ids"][index]
        if all(window[0] <= cell % columns <= window[1] and window[2] <= cell // columns <= window[3] for cell in cells):
            expected.append(index)
    np.testing.assert_array_equal(paths["included_active_edge_indices"], expected)
    np.testing.assert_array_equal(np.sort(paths["chain_edge_indices"]), expected)
    np.testing.assert_array_equal(paths["chain_edge_cell_ids"], graph["edge_cell_ids"][paths["chain_edge_indices"]])
    points = paths["points_xyz_m"]
    endpoints_seen = {}
    safe_checks = 0
    corners = 0
    for chain in range(len(paths["chain_accepted"])):
        begin, end = paths["point_offsets"][chain:chain + 2]
        edge_begin, edge_end = paths["chain_edge_offsets"][chain:chain + 2]
        cells = paths["chain_edge_cell_ids"][edge_begin:edge_end]
        np.testing.assert_array_equal(cells[:-1, 1], cells[1:, 0])
        node_cells = np.concatenate((cells[:1, 0], cells[:, 1]))
        original = np.column_stack((origin[0] + node_cells % columns * spacing,
                                    origin[1] + node_cells // columns * spacing))
        local = points[begin:end]
        for cell, point in ((node_cells[0], local[0]), (node_cells[-1], local[-1])):
            expected_xyz = [origin[0] + cell % columns * spacing, topology["height_m"].ravel()[cell], origin[1] + cell // columns * spacing]
            np.testing.assert_array_equal(point, expected_xyz)
            old = endpoints_seen.setdefault(int(cell), point)
            np.testing.assert_array_equal(old, point)
        grid = (local[:, [0, 2]] - origin) / spacing
        lower = np.floor(grid).astype(int)
        if np.any(grid < 0) or np.any(grid[:, 0] > columns - 1) or np.any(grid[:, 1] > rows - 1):
            raise ValueError("visual path outside source extent")
        upper = np.minimum(lower + 1, [columns - 1, rows - 1])
        stencil = np.column_stack((lower[:, 1] * columns + lower[:, 0], lower[:, 1] * columns + upper[:, 0],
                                   upper[:, 1] * columns + lower[:, 0], upper[:, 1] * columns + upper[:, 0]))
        if not topology["valid_mask"].ravel()[stencil].all():
            raise ValueError("visual path unknown interpolation stencil")
        fractions = grid - lower
        bed = topology["height_m"].ravel()[stencil]
        height = (bed[:, 0] * (1 - fractions[:, 0]) * (1 - fractions[:, 1]) +
                  bed[:, 1] * fractions[:, 0] * (1 - fractions[:, 1]) +
                  bed[:, 2] * (1 - fractions[:, 0]) * fractions[:, 1] + bed[:, 3] * fractions[:, 0] * fractions[:, 1])
        np.testing.assert_allclose(height, local[:, 1], atol=2e-12, rtol=0)
        shortest = np.full(len(local), np.inf)
        for start, stop in zip(original[:-1], original[1:]):
            delta = stop - start
            projection = np.clip(np.sum((local[:, [0, 2]] - start) * delta, axis=1) / np.sum(delta ** 2), 0, 1)
            distance = np.linalg.norm(local[:, [0, 2]] - start - projection[:, None] * delta, axis=1)
            shortest = np.minimum(shortest, distance)
        if paths["chain_accepted"][chain]:
            owners = topology["contribution_owner"].ravel()[stencil]
            if (np.any(owners != owners[0, 0]) or np.any(owners < 0) or
                    topology["protected_mask"].ravel()[stencil].any() or topology["open_boundary_mask"].ravel()[stencil].any() or
                    np.max(shortest) > spacing / 4 + 1e-12):
                raise ValueError("accepted curve crossed leaf/barrier/corridor")
            safe_checks += len(local)
            corners += int(paths["chain_original_corner_count"][chain])
        elif np.max(shortest) > 1e-12:
            raise ValueError("fallback path changed original polyline")
    if int(paths["chain_accepted"].sum()) != metadata["accepted_chains"]:
        raise ValueError("visual curve accepted count mismatch")
    if metadata["accepted_smoothed_corners"] != corners:
        raise ValueError("visual curve corner count mismatch")
    for record in (report["paths"], report["geometry"], report["hierarchy"], report["hour_page"]):
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("visual path evidence changed")
    result = dict(schema="td-independent-native-channel-valley-paths-v1", accepted=True,
                  report_record=dict(path=str(report_path), expected_sha256=expected_sha256),
                  included_edges=len(expected), omitted_edges=metadata["omitted_active_edges"],
                  points=len(points), chains=len(paths["chain_accepted"]),
                  accepted_curved_chains=metadata["accepted_curved_chains"], accepted_smoothed_corners=corners,
                  fallback_chains=metadata["fallback_chains"], accepted_curve_point_checks=safe_checks,
                  shared_endpoints_exact=True, native_height_checked=True, active_edge_coverage_exact=True,
                  hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                  scope="saved visual polyline samples; continuous stencil gate implemented separately; not a generated channel bed")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    args = parser.parse_args()
    result = audit(args.report, args.report_sha256)
    destination = ROOT / "verification/td-native-channel-valley-paths" / ("independent-audit-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(destination, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(destination), expected_sha256=file_sha256(destination), **result)))


if __name__ == "__main__":
    main()
