"""Freeze and independently account the fixed clamped land coverage artifact."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import traceback
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline import surface_land_coverage as coverage
from tests.test_surface_land_coverage import SOURCE, SOURCE_SHA256, SurfaceLandCoverageTests, fixture


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if hasattr(value, "items"):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def independent(record):
    nodes, triangles = record["nodes"], record["triangles"]
    positions = nodes["xz_m"][triangles]
    first = positions[:, 1] - positions[:, 0]
    second = positions[:, 2] - positions[:, 0]
    area = np.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]) / 2
    if not np.all(area == .5) or float(area.sum()) != 9800.:
        raise AssertionError("independent land area failed")
    outer = ~np.repeat(record["audit"]["interior_cell_mask"], 2)
    cut = nodes["h0_m"] - nodes["h2_m"]
    outer_cut = float((cut[triangles].mean(axis=1) * area)[outer].sum())
    outside_area = 0.
    outside_water = 0.
    for outlet in record["outside_outlets"]:
        positions = outlet["bed_xyz_m"][outlet["triangles"]][:, :, [0, 2]]
        first = positions[:, 1] - positions[:, 0]
        second = positions[:, 2] - positions[:, 0]
        outlet_areas = np.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]) / 2
        outside_area += float(outlet_areas.sum())
        outlet_depth = outlet["water_xyz_m"][:, 1] - outlet["bed_xyz_m"][:, 1]
        outside_water += float((outlet_depth[outlet["triangles"]].mean(axis=1) * outlet_areas).sum())
    if outside_area != 90. or not np.isclose(outer_cut, 70.77028762295504, atol=1e-9, rtol=0):
        raise AssertionError("independent outer cut/crop area failed")
    if not np.array_equal(np.bincount(record["domain_owner"])[1:], [4900, 4900]):
        raise AssertionError("independent domain areas failed")
    wet_cells = nodes["wet_mask"][record["cells"]].all(axis=1)
    wet_triangles = np.repeat(wet_cells, 2)
    depth = nodes["water_surface_m"] - nodes["h2_m"]
    land_water = float((depth[triangles[wet_triangles]].mean(axis=1) * area[wet_triangles]).sum())
    if (int(wet_cells.sum()) != 706 or not np.isclose(land_water, 252.72852290299738, atol=1e-9, rtol=0) or
            not np.isclose(outside_water, 47.257489257730654, atol=1e-9, rtol=0)):
        raise AssertionError("independent saved triangle water integral failed")
    return {"land_area_m2": float(area.sum()), "domain_area_m2": [4900., 4900.],
            "outside_attachment_area_m2": outside_area, "outer_cut_volume_m3": outer_cut,
            "shared_domain_nodes": int((nodes["xz_m"][:, 0] == 75).sum()),
            "static_q_count": len(record["outside_outlets"]), "static_wet_cells": int(wet_cells.sum()),
            "land_static_water_volume_m3": land_water, "outside_static_water_volume_m3": outside_water}


def main():
    started = datetime.now(timezone.utc)
    directory = ROOT / "verification/surface-land-coverage" / ("run-" + started.strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(parents=True, exist_ok=False)
    report = {"started_utc": started.isoformat(), "status": "running", "source_path": str(SOURCE.resolve()),
              "source_file_sha256": file_hash(SOURCE), "algorithm_version": coverage.VERSION,
              "interpretation": coverage.INTERPRETATION, "natural_outlets_certified": False,
              "general_cross_precision": False, "dynamic_fine": False, "full_dynamic_wave_prepared": False,
              "ready_for_3d": False, "dynamic_boundary_z_m": 70., "static_geometry_coast_z_m": 75.,
              "outlet_dynamic_storage_included": False, "independent_coordinator_review": "pending"}
    try:
        source, record = fixture()
        report["precalculation"] = independent(record)
        report["ledger"] = plain(record["ledger"])
        path = directory / "two-domain-land-coverage.npz"
        coverage.save_surface_land_coverage(record, path)
        loaded = coverage.load_surface_land_coverage(path)
        query = coverage.query_surface_land_coverage(loaded)
        report["bundle"] = {"path": str(path.resolve()), "file_sha256": file_hash(path),
                            "identity_sha256": loaded["identity_sha256"]}
        report["source_identity_sha256"] = source["identity_sha256"]
        report["original_source_preserved"] = file_hash(SOURCE) == SOURCE_SHA256
        report["fixed_dynamic_wet_cells"] = 676
        display = directory / "land-coverage-review.json"
        display.write_text(json.dumps({"format": "surface-land-coverage-review-v1", "units": "metres, cubic metres",
            "source_file_sha256": SOURCE_SHA256, "saved_query": plain(query)}, allow_nan=False, separators=(",", ":")), encoding="utf8")
        report["display"] = {"path": str(display.resolve()), "file_sha256": file_hash(display)}
        with (directory / "focused-tests.txt").open("x", encoding="utf8") as stream:
            tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceLandCoverageTests))
        report["focused_tests"] = {"run": tests.testsRun, "failures": len(tests.failures), "errors": len(tests.errors),
                                   "file_sha256": file_hash(directory / "focused-tests.txt")}
        if not tests.wasSuccessful() or not report["original_source_preserved"]:
            raise AssertionError("focused tests or immutable source failed")
        report["implementation_sha256"] = {str((ROOT / name).resolve()): file_hash(ROOT / name) for name in
            ("terrain_pipeline/surface_land_coverage.py", "tests/test_surface_land_coverage.py",
             "tools/verify_surface_land_coverage.py", "docs/surface-land-coverage-v1.md")}
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        (directory / "traceback.txt").write_text(traceback.format_exc(), encoding="utf8")
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf8")
        print(directory.resolve())


if __name__ == "__main__":
    main()
