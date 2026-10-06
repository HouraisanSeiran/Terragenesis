"""Independently compare saved native water mesh, grid volume and OBJ to raw page."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record

MAX_BYTES = 128 * 1024 ** 2


def check_arrays(source, source_metadata, mesh, metadata, source_record):
    bed = source["height_m"]
    valid = source["valid_mask"]
    if (bed.ndim != 2 or bed.size > 250000 or bed.dtype != np.float64 or
            valid.shape != bed.shape or valid.dtype != bool or
            source["depth_m"].shape != (2, bed.size) or
            source["depth_m"].dtype != np.float64 or not np.isfinite(bed).all()):
        raise ValueError("raw native water source grid invalid")
    depth = source["depth_m"][-1].reshape(bed.shape)
    if not np.isfinite(depth).all() or np.any(depth < 0) or np.any(depth[~valid] != 0):
        raise ValueError("raw native depth invalid")
    if (metadata["source_page_sha256"] != source_record["expected_sha256"] or
            metadata["source_page_identity"] != source_record["expected_identity"] or
            metadata["grid_shape"] != list(bed.shape) or
            any(metadata[name] != source_metadata[name] for name in
                ("origin_m_xz", "spacing_m", "start_s", "end_s", "hierarchy_identity", "forcing_identity"))):
        raise ValueError("water mesh raw page lineage/grid/time mismatch")
    threshold = metadata["wet_threshold_m"]
    if type(threshold) not in (float, int) or not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("water mesh display threshold invalid")
    cell_ids = np.flatnonzero(valid)
    np.testing.assert_array_equal(mesh["cell_ids"], cell_ids)
    np.testing.assert_array_equal(mesh["native_bed_m"], bed.ravel()[cell_ids])
    np.testing.assert_array_equal(mesh["hour_end_depth_m"], depth.ravel()[cell_ids])
    wet = valid & (depth >= threshold)
    rows, columns = bed.shape
    global_triangles = []
    drawn_ids = set()
    quads = 0
    for row in range(rows - 1):
        for column in range(columns - 1):
            corners = (row * columns + column, (row + 1) * columns + column,
                       (row + 1) * columns + column + 1, row * columns + column + 1)
            if not all(wet.ravel()[cell] for cell in corners):
                continue
            quads += 1
            drawn_ids.update(corners)
            global_triangles.extend((corners[:3], (corners[0], corners[2], corners[3])))
    vertex_ids = np.array(sorted(drawn_ids), dtype=np.int64)
    local_index = {cell: index for index, cell in enumerate(vertex_ids)}
    expected_triangles = np.array([[local_index[cell] for cell in triangle]
                                   for triangle in global_triangles], np.int64).reshape(-1, 3)
    np.testing.assert_array_equal(mesh["vertex_cell_ids"], vertex_ids)
    np.testing.assert_array_equal(mesh["triangles"], expected_triangles)
    origin = metadata["origin_m_xz"]
    spacing = metadata["spacing_m"]
    vertices = np.column_stack((origin[0] + vertex_ids % columns * spacing,
                                bed.ravel()[vertex_ids] + depth.ravel()[vertex_ids],
                                origin[1] + vertex_ids // columns * spacing))
    np.testing.assert_array_equal(mesh["vertices_xyz_m"], vertices)
    if len(expected_triangles):
        normals = np.cross(vertices[expected_triangles[:, 1]] - vertices[expected_triangles[:, 0]],
                           vertices[expected_triangles[:, 2]] - vertices[expected_triangles[:, 0]])
        if np.any(normals[:, 1] <= 0):
            raise ValueError("native water triangles degenerate or downward")
    undrawn_ids = [int(cell) for cell in np.flatnonzero(wet) if cell not in drawn_ids]
    area = spacing ** 2
    volume = math.fsum(float(depth.ravel()[cell]) for cell in cell_ids) * area
    undrawn = math.fsum(float(depth.ravel()[cell]) for cell in undrawn_ids) * area
    below = math.fsum(float(value) for value in depth[valid & ~wet]) * area
    counts = dict(valid_cell_count=len(cell_ids), wet_cell_count=int(wet.sum()),
                  drawn_quad_count=quads, undrawn_wet_cell_count=len(undrawn_ids))
    if any(metadata[name] != value for name, value in counts.items()):
        raise ValueError("water mesh independent grid counts mismatch")
    for name, value in (("grid_water_volume_m3", volume), ("undrawn_wet_grid_volume_m3", undrawn)):
        if not math.isclose(metadata[name], value, rel_tol=1e-12, abs_tol=1e-8):
            raise ValueError("water mesh independent grid volume mismatch")
    if any(metadata.get(name) is not False for name in
           ("derived_fine_hydraulics", "water_generated", "hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("water surface unsupported certification")
    return dict(**counts, vertices=len(vertex_ids), triangles=len(expected_triangles),
                independently_summed_grid_volume_m3=volume,
                undrawn_wet_grid_volume_m3=undrawn, below_display_threshold_grid_volume_m3=below,
                vertex_covered_grid_volume_m3=volume - undrawn - below,
                source_vertex_values_exact=True, wet_quad_topology_exact=True,
                grid_volume_not_mesh_volume=True)


def audit(report_path, expected_sha256):
    report_path = Path(report_path).resolve(strict=True)
    if report_path.stat().st_size > 1024 ** 2 or file_sha256(report_path) != expected_sha256:
        raise ValueError("water report external pin/budget mismatch")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema") != "td-native-water-surface-prototype-v1":
        raise ValueError("water report schema mismatch")
    source, source_metadata = read_record(report["source_page"])
    mesh, metadata = read_record(report["surface"])
    result = check_arrays(source, source_metadata, mesh, metadata, report["source_page"])
    if metadata != report["metadata"] or report["vertex_count"] != result["vertices"] or report["triangle_count"] != result["triangles"]:
        raise ValueError("water prototype metadata/count mismatch")
    obj = Path(report["obj"]["path"])
    if obj.stat().st_size > MAX_BYTES or file_sha256(obj) != report["obj"]["expected_sha256"]:
        raise ValueError("water OBJ external pin/budget mismatch")
    vertices, triangles = [], []
    with obj.open(encoding="ascii") as handle:
        for line in handle:
            fields = line.split()
            if not fields or fields[0].startswith("#"):
                continue
            if fields[0] == "v" and len(fields) == 4:
                vertices.append([float(value) for value in fields[1:]])
            elif fields[0] == "f" and len(fields) == 4:
                triangles.append([int(value) - 1 for value in fields[1:]])
            else:
                raise ValueError("water OBJ unexpected record")
    np.testing.assert_array_equal(np.asarray(vertices, np.float64).reshape(-1, 3), mesh["vertices_xyz_m"])
    np.testing.assert_array_equal(np.asarray(triangles, np.int64).reshape(-1, 3), mesh["triangles"])
    for record in (report["source_page"], report["surface"], report["obj"],
                   dict(path=str(report_path), expected_sha256=expected_sha256)):
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("native water evidence changed during audit")
    return dict(schema="td-independent-native-water-surface-v1", accepted=True,
                prototype_report=dict(path=str(report_path), expected_sha256=expected_sha256),
                **result, obj_roundtrip_exact=True, derived_fine_hydraulics=False,
                hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
                scope="saved single native 30m hour-end diagnostic surface, not full time-series or fine-bed hydraulics")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    args = parser.parse_args()
    result = audit(args.report, args.report_sha256)
    destination = ROOT / "verification/td-native-water-surface" / ("independent-audit-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(destination, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(destination), expected_sha256=file_sha256(destination), **result)))


if __name__ == "__main__":
    main()
