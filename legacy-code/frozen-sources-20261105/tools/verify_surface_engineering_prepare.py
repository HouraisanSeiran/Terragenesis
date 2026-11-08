"""Reproduce the fixed accepted two-domain engineering bundle."""

from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline import surface_engineering_prepare as engineering
from terrain_pipeline.surface_domain_prepare import load_surface_domains
from tests.test_surface_engineering_prepare import SOURCE, SOURCE_SHA256, SurfaceEngineeringTests, constant_fixture


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variable-storage", type=Path, help="Frozen same-evaluation variable storage archive")
    arguments = parser.parse_args()
    started = datetime.now(timezone.utc)
    directory = ROOT / "verification/surface-engineering-prepare" / (
        "run-" + started.strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(parents=True, exist_ok=False)
    report = {"started_utc": started.isoformat(), "status": "running",
              "source": str(SOURCE.resolve()), "source_file_sha256": file_hash(SOURCE),
              "algorithm_version": engineering.VERSION, "scope": "declared_rectangular_node_envelope",
              "physical_footprint_complete": False, "natural_outlets_certified": False,
              "full_dynamic_wave_prepared": False, "ready_for_3d": False}
    try:
        if report["source_file_sha256"] != SOURCE_SHA256:
            raise AssertionError("fixed accepted source changed")
        evaluation, outlets, result = constant_fixture()
        if arguments.variable_storage is not None:
            from terrain_pipeline.surface_variable_storage import load_surface_variable_storage
            saved_variable = load_surface_variable_storage(arguments.variable_storage)
            result = engineering.compose_surface_engineering(
                evaluation, result["domain_mosaic"], result["drops"], saved_variable["source"],
                variable_storage=saved_variable)
            report["variable_source_file_sha256"] = file_hash(arguments.variable_storage)
        path = directory / "two-domain-engineering.npz"
        engineering.save_surface_engineering(result, path)
        loaded = engineering.load_surface_engineering(path)
        queried = engineering.query_surface_engineering(loaded)
        if result["identity_sha256"] != loaded["identity_sha256"]:
            raise AssertionError("static reload changed identity")
        dynamic = loaded["dynamic_forest"]["dynamic"]
        report["bundle"] = {"path": str(path.resolve()), "file_sha256": file_hash(path),
                            "identity_sha256": loaded["identity_sha256"]}
        report["evaluation_identity_sha256"] = evaluation["identity_sha256"]
        report["mosaic_identity_sha256"] = loaded["domain_mosaic"]["identity_sha256"]
        report["drop_identity_sha256"] = [drop["identity_sha256"] for drop in loaded["drops"]]
        report["forest_identity_sha256"] = loaded["dynamic_forest"]["identity_sha256"]
        report["domain_ids"] = list(loaded["domain_ids"])
        report["mosaic_bbox_xz_m"] = list(loaded["domain_mosaic"]["grid"]["bbox_xz_m"])
        report["nodes"] = len(loaded["dynamic_forest"]["node_keys"])
        report["edges"] = len(loaded["dynamic_forest"]["edges"])
        report["boundaries"] = int(dynamic["inputs"]["boundary_mask"].sum())
        report["committed_steps"] = dynamic["committed_steps"]
        report["static_terminal_q_m3_s"] = [drop["attachment"]["terminal_q_m3_s"] for drop in loaded["drops"]]
        report["drop_cut_volume_m3"] = [drop["ledger"]["cut_volume_m3"] for drop in loaded["drops"]]
        report["dynamic_local_volume_m3"] = loaded["dynamic_forest"]["domain_ledger_m3"][:, :, 1].sum(axis=0).tolist()
        report["dynamic_initial_internal_storage_m3"] = float(dynamic["storage_m3"][0].sum())
        mesh = loaded["domain_mosaic"]
        triangles = mesh["triangles"][np.repeat(mesh["wet_cells"], 2)]
        positions = np.column_stack((mesh["nodes"]["x_m"], mesh["nodes"]["z_m"]))[triangles]
        first = positions[:, 1] - positions[:, 0]
        second = positions[:, 2] - positions[:, 0]
        areas = np.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0]) / 2
        depth = mesh["nodes"]["water_surface_m"] - mesh["nodes"]["h2_m"]
        geometry_volume = float((areas * depth[triangles].mean(axis=1)).sum())
        if not np.isclose(geometry_volume, 236.01507098278893, atol=1e-9, rtol=0):
            raise AssertionError("independent static geometry volume differs")
        report["independent_static_geometry_volume_m3"] = geometry_volume
        ledgers = loaded["dynamic_forest"]["domain_ledger_m3"]
        residual = ledgers[:, :, 3] - ledgers[:, :, 0] - ledgers[:, :, 1] - ledgers[:, :, 2]
        report["independent_max_domain_residual_m3"] = float(np.abs(residual).max(initial=0))
        if not np.allclose(residual, 0., atol=1e-9, rtol=0):
            raise AssertionError("independent forest ledger differs")
        if loaded["variable_storage"] is not None:
            report["variable_identity_sha256"] = loaded["variable_storage"]["identity_sha256"]
            report["variable_initial_internal_storage_m3"] = float(loaded["variable_storage"]["storage_m3"][0].sum())
            report["variable_committed_steps"] = loaded["variable_storage"]["committed_steps"]
            if not np.isclose(report["variable_initial_internal_storage_m3"], 224.5721879136545,
                              atol=1e-9, rtol=0):
                raise AssertionError("variable initial storage differs")
            variable_ledger = loaded["variable_storage"]["domain_ledger_m3"]
            residual = variable_ledger[:, :, 3] - variable_ledger[:, :, 0] - variable_ledger[:, :, 1] - variable_ledger[:, :, 2]
            report["independent_max_variable_domain_residual_m3"] = float(np.abs(residual).max(initial=0))
            if not np.allclose(residual, 0., atol=1e-9, rtol=0):
                raise AssertionError("variable independent domain ledger differs")
        def display_json(value):
            if isinstance(value, np.ndarray):
                return value.tolist()
            if hasattr(value, "items"):
                return {key: display_json(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [display_json(item) for item in value]
            if isinstance(value, np.generic):
                return value.item()
            return value
        display = {"format": "surface-engineering-review-v1", "identity_sha256": loaded["identity_sha256"],
                   "source_file_sha256": SOURCE_SHA256, "units": "metres, seconds, cubic metres",
                   "coordinate_system": "metric-xz-m; geometry XYZ has Y elevation",
                   "scope": report["scope"], "original_land_pixel_footprint_m2": 9800.,
                   "node_envelope_m2": 7800., "strip_footprint_overlap_z_m": [70., 75.],
                   "physical_footprint_complete": False, "natural_outlets_certified": False,
                   "full_dynamic_wave_prepared": False, "ready_for_3d": False,
                   "state_selectors": {"constant": "state_index", "variable": "variable_state_index",
                                       "independent_time_axes": True},
                   "saved_query": display_json(queried)}
        display_path = directory / "engineering-review.json"
        display_path.write_text(json.dumps(display, allow_nan=False, separators=(",", ":")), encoding="utf8")
        report["display"] = {"path": str(display_path.resolve()), "file_sha256": file_hash(display_path)}
        report["static_reload_without_generation"] = True
        with (directory / "focused-tests.txt").open("x", encoding="utf8") as stream:
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceEngineeringTests)
            tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        report["focused_tests"] = {"run": tests.testsRun, "failures": len(tests.failures),
                                   "errors": len(tests.errors), "file_sha256": file_hash(directory / "focused-tests.txt")}
        if not tests.wasSuccessful() or file_hash(SOURCE) != SOURCE_SHA256:
            raise AssertionError("focused tests or fixed source check failed")
        files = [ROOT / item for item in (
            "terrain_pipeline/surface_engineering_prepare.py", "tests/test_surface_engineering_prepare.py",
            "tools/verify_surface_engineering_prepare.py", "docs/surface-engineering-prepare-v1.md")]
        report["implementation_file_sha256"] = {str(path.resolve()): file_hash(path) for path in files}
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        (directory / "traceback.txt").write_text(traceback.format_exc(), encoding="utf8")
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                        allow_nan=False), encoding="utf8")
        print(directory.resolve())


if __name__ == "__main__":
    main()
