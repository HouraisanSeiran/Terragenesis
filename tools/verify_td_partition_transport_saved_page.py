"""Cold, transport-only two-second diagnostic of a pinned v10 saved page."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import psutil

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import PRIMARY_PATH as PRIMARY_PATH
from terrain_pipeline.basin_storage import PRIMARY_SHA256 as PRIMARY_SHA256
from terrain_pipeline.basin_storage import storagev10_load_storage as load_storage
from terrain_pipeline.td_native_domain_partition import NativePartition, StageSnapshot
from terrain_pipeline.td_native_partition_transport import transport


RUN = ROOT / "verification/td-basin-generation/A-native-weather-v10-20261002T185307845630Z"
REPORT = RUN / "eastward-2.5s/hour-00/report.json"
STORAGE_SHA256 = "c89756a42ae10b2b14d95cb2951c20ec54a7079ff81bf224ad87d358e290d1c8"
STORAGE_IDENTITY = "11432c57c7ec42acd0f7613e328a8f5edda00327cb0ff27e7a5fe0bf9df2ab80"
HIERARCHY_RECORD = {"path": str(ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz"),
                    "expected_sha256": "36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
                    "expected_identity": "cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998"}
MAX_BYTES = 1073741824


def _snapshot(partition, values, version):
    return StageSnapshot(partition, version, {tile.tile_id: (version,
        values[tile.interior_zx[0]:tile.interior_zx[1], tile.interior_zx[2]:tile.interior_zx[3]])
        for tile in partition.tiles()})


def _reference(bed, depth, valid, opened, faces, spacing_m=30., dt_s=1.):
    area = spacing_m**2
    first, second = faces.T
    boundaries = np.flatnonzero(opened.ravel())
    rows, columns = np.divmod(boundaries, bed.shape[1])
    widths = spacing_m * ((rows == 0).astype(int) + (rows == bed.shape[0]-1)
                          + (columns == 0) + (columns == bed.shape[1]-1))
    bed_flat = bed.ravel()
    current = depth.ravel().copy()
    forward = np.zeros(len(faces))
    reverse = np.zeros(len(faces))
    external = np.zeros(len(boundaries))

    def stage(values):
        first_head = bed_flat[first] + values[first]
        second_head = bed_flat[second] + values[second]
        sill = np.maximum(bed_flat[first], bed_flat[second])
        positive = first_head >= second_head
        rate = np.where(positive, np.maximum(first_head - np.maximum(sill, second_head), 0.),
                        -np.maximum(second_head - np.maximum(sill, first_head), 0.)) * (.6 / spacing_m)
        derivative = np.bincount(second, weights=rate, minlength=values.size)
        derivative -= np.bincount(first, weights=rate, minlength=values.size)
        exit_rate = .6 * widths / area * values[boundaries]
        np.add.at(derivative, boundaries, -exit_rate)
        return derivative, rate, exit_rate

    for _ in range(2):
        derivative0, rate0, exit0 = stage(current)
        stage1 = current + dt_s * derivative0
        if np.any(stage1 < 0):
            raise ValueError("reference first Euler stage negative")
        derivative1, rate1, exit1 = stage(stage1)
        stage2 = stage1 + dt_s * derivative1
        if np.any(stage2 < 0):
            raise ValueError("reference second Euler stage negative")
        current = .5 * (current + stage2)
        forward += .5 * dt_s * area * (np.maximum(rate0, 0) + np.maximum(rate1, 0))
        reverse += .5 * dt_s * area * (np.maximum(-rate0, 0) + np.maximum(-rate1, 0))
        external += .5 * dt_s * area * (exit0 + exit1)
    return current, forward, reverse, boundaries, external


def diagnose():
    tool_before = file_sha256(__file__)
    source_before = file_sha256(PRIMARY_PATH)
    if source_before != PRIMARY_SHA256:
        raise ValueError("original source SHA changed before diagnostic")
    page = json.loads(REPORT.read_text(encoding="utf-8"))
    record = page["storage"]
    if (page.get("hour") != 0 or record.get("path") != str(REPORT.parent / "storage.npz")
            or record.get("expected_sha256") != STORAGE_SHA256
            or record.get("expected_identity") != STORAGE_IDENTITY):
        raise ValueError("baseline hour00 report pin mismatch")
    report_sha = file_sha256(REPORT)
    hierarchy = load_basin_hierarchy(**HIERARCHY_RECORD)
    saved = load_storage(**record)
    topology = hierarchy["arrays"]
    arrays = saved["arrays"]
    if hierarchy["metadata"]["spacing_m"] != 30. or saved["metadata"]["spacing_m"] != 30.:
        raise ValueError("pinned native grid spacing mismatch")
    for name in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells"):
        if not np.array_equal(arrays[name], topology[name]):
            raise ValueError("saved page/hierarchy mismatch: " + name)
    if saved["metadata"]["hierarchy_identity"] != hierarchy["identity_sha256"]:
        raise ValueError("saved hierarchy identity mismatch")
    bed = topology["height_m"]
    depth = arrays["depth_m"][1].reshape(bed.shape)
    valid = topology["valid_mask"]
    opened = topology["open_boundary_mask"]
    if bed.size > 250000 or not np.array_equal(np.flatnonzero(opened), topology["boundary_cells"]):
        raise ValueError("bounded native grid/open perimeter mismatch")
    partition = NativePartition(bed.shape)
    bed_snapshot = _snapshot(partition, bed, "pinned-bed")
    depth_snapshot = _snapshot(partition, depth, "saved-hour00-end-depth")
    first = transport(partition, bed_snapshot, depth_snapshot, valid, opened, spacing_m=30., dt_s=1., steps=2)
    second = transport(partition, bed_snapshot, depth_snapshot, valid, opened, spacing_m=30., dt_s=1., steps=2,
                       tile_order=reversed(range(partition.tile_count)))
    reference = _reference(bed, depth, valid, opened, topology["face_cells"])
    final = np.empty(bed.shape, dtype=np.float64)
    for tile in partition.tiles():
        z0, z1, x0, x1 = tile.interior_zx
        final[z0:z1, x0:x1] = first["final_tile_chunks"][tile.tile_id]
        if not np.array_equal(first["final_tile_chunks"][tile.tile_id], second["final_tile_chunks"][tile.tile_id]):
            raise ValueError("tile order changed final state")
    if not np.array_equal(first["face_cells"], topology["face_cells"]):
        raise ValueError("native canonical face order differs from pinned hierarchy")
    differences = {"depth_m": float(np.max(abs(final.ravel() - reference[0]))),
                   "forward_m3": float(np.max(abs(first["forward_m3"] - reference[1]))),
                   "reverse_m3": float(np.max(abs(first["reverse_m3"] - reference[2]))),
                   "boundary_outflow_m3": float(np.max(abs(first["boundary_outflow_m3"] - reference[4]))) if len(reference[4]) else 0.}
    if (differences["depth_m"] > 1e-12 or max(differences[name] for name in differences if name != "depth_m") > 1e-7
            or not np.array_equal(first["forward_m3"], second["forward_m3"])
            or not np.array_equal(first["reverse_m3"], second["reverse_m3"])
            or not np.array_equal(first["boundary_outflow_m3"], second["boundary_outflow_m3"])
            or not np.array_equal(first["boundary_cells"], reference[3])):
        raise ValueError("independent reference or tile-order mismatch")
    divergence = np.bincount(topology["face_cells"][:, 1], weights=first["forward_m3"]-first["reverse_m3"], minlength=bed.size)
    divergence -= np.bincount(topology["face_cells"][:, 0], weights=first["forward_m3"]-first["reverse_m3"], minlength=bed.size)
    np.add.at(divergence, first["boundary_cells"], -first["boundary_outflow_m3"])
    cell_residual = (final.ravel() - depth.ravel()) * 30.**2 - divergence
    if np.max(abs(cell_residual)) > 1e-7:
        raise ValueError("independent cellwise divergence budget failed")
    source_after = file_sha256(PRIMARY_PATH)
    if (source_after != source_before or file_sha256(record["path"]) != STORAGE_SHA256
            or file_sha256(REPORT) != report_sha
            or file_sha256(HIERARCHY_RECORD["path"]) != HIERARCHY_RECORD["expected_sha256"]
            or file_sha256(__file__) != tool_before):
        raise ValueError("saved source/page changed during diagnostic")
    memory = psutil.Process().memory_info()
    rss = int(getattr(memory, "peak_wset", memory.rss))
    private = getattr(memory, "peak_pagefile", None)
    if type(private) is not int or max(rss, private) > MAX_BYTES:
        raise MemoryError("diagnostic actual peak missing or above 1GiB")
    return {"schema": "td-v10-partition-saved-page-transport-diagnostic-v1",
            "storage": record, "hour_report": {"path": str(REPORT), "expected_sha256": report_sha},
            "hierarchy": HIERARCHY_RECORD, "primary_source_sha256_before": source_before,
            "primary_source_sha256_after": source_after, "shape_zx": list(bed.shape),
            "tile_count": partition.tile_count, "face_count": len(first["face_ids"]),
            "reference_max_abs_differences": differences,
            "max_abs_cellwise_budget_residual_m3": float(np.max(abs(cell_residual))),
            "volume_budget": first["volume_budget"],
            "measured_process_peak_rss_bytes": rss, "measured_process_peak_private_bytes": private,
            "tool_sha256": tool_before,
            "partition_code_sha256": file_sha256(ROOT / "terrain_pipeline/td_native_domain_partition.py"),
            "transport_code_sha256": file_sha256(ROOT / "terrain_pipeline/td_native_partition_transport.py"),
            "transport_only_seconds": 2, "rain_forcing_applied": False,
            "baseline_continuation": False, "full_water_or_full_day_accepted": False,
            "real_cross_tile_validated": partition.tile_count > 1,
            "scope": "real pinned TD hour00 end depth; 256x256 one tile; transport-only 2s diagnostic",
            "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose()
    target = args.output.resolve()
    payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    publish_bytes(target, payload)
    print(json.dumps({"path": str(target), "tile_count": result["tile_count"],
                      "max_abs_cellwise_budget_residual_m3": result["max_abs_cellwise_budget_residual_m3"],
                      "report_sha256": file_sha256(target)}))


if __name__ == "__main__":
    main()
