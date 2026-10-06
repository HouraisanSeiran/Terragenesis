"""Independently check saved mesh against source tiles and manifold edge counts."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_native_channel_tiles import assemble


def audit(path, expected_sha256):
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > 1024 ** 2 or file_sha256(path) != expected_sha256:
        raise ValueError("surface external report pin/budget mismatch")
    report = json.loads(path.read_text(encoding="utf-8"))
    grids, tile_metadata, bounds, repeated = assemble(report["tiles"], report["geometry"]["expected_identity"])
    arrays, metadata = read_record(report["surface"])
    geometry, geometry_metadata = read_record(report["geometry"])
    if metadata["candidate_tile_identities"] != sorted(record["expected_identity"] for record in report["tiles"]):
        raise ValueError("surface tile identity chain mismatch")
    for name in ("hierarchy_identity", "forcing_identity", "hour_page_identity"):
        if metadata[name] != geometry_metadata[name]:
            raise ValueError("surface geometry lineage mismatch")
    if metadata["geometry_identity"] != report["geometry"]["expected_identity"] or metadata["window"] != bounds:
        raise ValueError("surface geometry/window chain mismatch")
    rows, columns = grids["candidate_bed_m"].shape
    lattice_x, lattice_z = np.meshgrid(np.arange(bounds[0], bounds[1] + 1), np.arange(bounds[2], bounds[3] + 1))
    lattice = np.column_stack((lattice_x.ravel(), lattice_z.ravel()))
    np.testing.assert_array_equal(arrays["vertex_lattice_xz"], lattice)
    np.testing.assert_array_equal(arrays["vertices_xyz_m"][:, 0], tile_metadata["origin_m_xz"][0] + lattice[:, 0])
    np.testing.assert_array_equal(arrays["vertices_xyz_m"][:, 2], tile_metadata["origin_m_xz"][1] + lattice[:, 1])
    np.testing.assert_array_equal(arrays["vertices_xyz_m"][:, 1], grids["candidate_bed_m"].ravel())
    for name in ("native_bilinear_bed_m", "candidate_cut_m"):
        np.testing.assert_array_equal(arrays[name], grids[name].ravel())
    triangles = arrays["triangles"]
    if triangles.shape != (2 * (rows - 1) * (columns - 1), 3) or triangles.dtype != np.int64:
        raise ValueError("surface triangle count/type mismatch")
    expected = []
    for row in range(rows - 1):
        for column in range(columns - 1):
            first = row * columns + column
            expected.extend(((first, first + columns, first + columns + 1),
                             (first, first + columns + 1, first + 1)))
    np.testing.assert_array_equal(triangles, np.asarray(expected))
    vertices = arrays["vertices_xyz_m"]
    crossed = np.cross(vertices[triangles[:, 1]] - vertices[triangles[:, 0]], vertices[triangles[:, 2]] - vertices[triangles[:, 0]])
    if np.any(crossed[:, 1] <= 0):
        raise ValueError("surface downward or degenerate winding")
    normals = crossed / np.linalg.norm(crossed, axis=1)[:, None]
    np.testing.assert_allclose(normals, arrays["face_normals_xyz"], atol=2e-15, rtol=0)
    summed = np.zeros_like(vertices)
    for corner in range(3):
        np.add.at(summed, triangles[:, corner], crossed)
    summed /= np.linalg.norm(summed, axis=1)[:, None]
    np.testing.assert_allclose(summed, arrays["vertex_normals_xyz"], atol=2e-15, rtol=0)
    pairs = np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]))
    unique_edges, counts = np.unique(np.sort(pairs, axis=1), axis=0, return_counts=True)
    if np.any((counts < 1) | (counts > 2)):
        raise ValueError("nonmanifold surface edge")
    boundary = unique_edges[counts == 1]
    endpoints = lattice[boundary]
    boundary_on_outer = ((endpoints[:, :, 0] == bounds[0]).all(axis=1) |
                         (endpoints[:, :, 0] == bounds[1]).all(axis=1) |
                         (endpoints[:, :, 1] == bounds[2]).all(axis=1) |
                         (endpoints[:, :, 1] == bounds[3]).all(axis=1))
    if not boundary_on_outer.all() or len(boundary) != 2 * (rows + columns - 2):
        raise ValueError("surface internal seam or incorrect perimeter")
    if len(vertices) - len(unique_edges) + len(triangles) != 1:
        raise ValueError("surface rectangular disk Euler topology mismatch")
    obj_path = Path(report["obj"]["path"])
    if file_sha256(obj_path) != report["obj"]["expected_sha256"] or obj_path.stat().st_size > 128 * 1024 ** 2:
        raise ValueError("surface OBJ pin/budget mismatch")
    obj_vertices, obj_normals, obj_faces = [], [], []
    with obj_path.open(encoding="ascii") as stream:
        for line in stream:
            if line.startswith("v "):
                obj_vertices.append(list(map(float, line.split()[1:])))
            elif line.startswith("vn "):
                obj_normals.append(list(map(float, line.split()[1:])))
            elif line.startswith("f "):
                indices = [value.split("//") for value in line.split()[1:]]
                if any(len(value) != 2 or value[0] != value[1] for value in indices):
                    raise ValueError("surface OBJ normals indexing mismatch")
                obj_faces.append([int(value[0]) - 1 for value in indices])
    np.testing.assert_array_equal(np.asarray(obj_vertices), vertices)
    np.testing.assert_array_equal(np.asarray(obj_normals), arrays["vertex_normals_xyz"])
    np.testing.assert_array_equal(np.asarray(obj_faces), triangles)
    if metadata["water_generated"] is not False or any(metadata[name] is not False for name in ("hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("surface unsupported certification")
    if file_sha256(path) != expected_sha256:
        raise ValueError("surface report changed")
    return dict(schema="td-independent-native-channel-surface-v1", accepted=True,
                prototype_report=dict(path=str(path), expected_sha256=expected_sha256),
                vertices=len(vertices), triangles=len(triangles), unique_edges=len(unique_edges),
                internal_edges_with_two_faces=int((counts == 2).sum()), boundary_edges_with_one_face=len(boundary),
                euler_characteristic=1, shared_tile_sample_checks=repeated, source_vertex_values_exact=True,
                obj_roundtrip_exact=True, water_generated=False, hydraulic_ready=False,
                natural_outlet_verified=False, publishable=False,
                scope="joined derived bed geometry only; no high-resolution terrain or solved water certification")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    args = parser.parse_args()
    result = audit(args.report, args.report_sha256)
    destination = ROOT / "verification/td-native-channel-surface" / ("independent-audit-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(destination, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(destination), expected_sha256=file_sha256(destination), **result)))


if __name__ == "__main__":
    main()
