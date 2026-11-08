import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.basin_topology import save_basin_hierarchy as save_basin_hierarchy
from terrain_pipeline.basin_storage import dispatch_save_storage as save_storage
from terrain_pipeline.td_catchment_dynamic_review import export_catchment_dynamic_review, load_catchment_dynamic_review
from terrain_pipeline.td_surface_reaches import _plain, _hash, make_surface_reaches
from tests.test_basin_storage_io import basin_storage_dispatch_io_fixture as fixture


def inputs(directory, wet=False):
    hierarchy, storage = fixture()
    if wet:
        arrays = storage["arrays"]
        arrays["depth_m"][:] = [1., 2., 3.]
        arrays["soil_mm"][:] = [10., 20., 30.]
        arrays["fast_mm"][:] = [1., 2., 3.]
        arrays["slow_mm"][:] = [4., 5., 6.]
        arrays["wet_pool_count"][:] = 1
        storage["identity_sha256"] = identity(arrays, storage["metadata"])
    records = {}
    for role, bundle, writer in (("hierarchy", hierarchy, save_basin_hierarchy), ("storage", storage, save_storage)):
        path = directory / (role + ".npz")
        writer(path, bundle)
        records[role] = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=bundle["identity_sha256"])
    return records, hierarchy, storage


class DynamicCatchmentTests(unittest.TestCase):
    def test_interval_actual_state_difference_ignores_tampered_saved_change(self):
        from terrain_pipeline.td_catchment_dynamic_review import _pages
        with tempfile.TemporaryDirectory() as directory:
            records, hierarchy, storage = inputs(Path(directory), True)
            storage["arrays"]["storage_change_m3"][0] = [5e-7, 5e-7, 5e-7]
            storage["identity_sha256"] = identity(storage["arrays"], storage["metadata"])
            page = list(_pages(hierarchy, storage))[1]
            diagnostic = page["budget_diagnostic"]["whole_interval"]
            self.assertEqual(diagnostic["actual_state_change_m3"], 0)
            self.assertEqual(diagnostic["residual_m3"], 0)
            self.assertTrue(diagnostic["passed"])
            self.assertNotIn("stored_change_m3", diagnostic)
    def test_numeric_budget_failure_preserves_diagnostic_not_certification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, hierarchy, storage = inputs(root)
            storage["arrays"]["soil_et_m3"][0] = [5e-7, 5e-7, 5e-7]
            storage["arrays"]["balance_residual_m3"][0] = [-5e-7, -5e-7, -5e-7]
            storage["identity_sha256"] = identity(storage["arrays"], storage["metadata"])
            path = root / "numeric.npz"
            save_storage(path, storage)
            records["storage"] = dict(path=str(path), expected_sha256=file_sha256(path), expected_identity=storage["identity_sha256"])
            result = export_catchment_dynamic_review(records, root / "review")
            self.assertFalse(result["budget_acceptance"]["audit_budget_passed"])
            page = json.loads((root / "review/frame-0001.json").read_bytes())
            self.assertFalse(page["budget_diagnostic"]["whole_interval"]["passed"])
            self.assertAlmostEqual(page["budget_diagnostic"]["whole_interval"]["residual_m3"], -1.5e-6)
            self.assertTrue(all("allowed_m3" in leaf["interval_budget"] for leaf in page["leaves"]))

    def test_page_deletion_extra_path_and_malformed_reach_refused(self):
        for mode in ("delete", "extra", "path"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                records, _, _ = inputs(root)
                result = export_catchment_dynamic_review(records, root / "review")
                path = root / "review/index.json"
                index = json.loads(path.read_bytes())
                if mode == "delete":
                    (root / "review/frame-0001.json").unlink()
                elif mode == "extra":
                    (root / "review/frame-9999.json").write_bytes(b"{}")
                else:
                    index["pages"][0]["file"] = "../frame-0000.json"
                    index.pop("identity_sha256")
                    index["identity_sha256"] = _hash(index)
                    path.write_text(json.dumps(index), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_catchment_dynamic_review(path, expected_sha256=file_sha256(path), expected_identity=index["identity_sha256"], records=records)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, hierarchy, storage = inputs(root)
            reaches = _plain(make_surface_reaches(hierarchy, threshold_area_m2=900, expected_hierarchy_identity=hierarchy["identity_sha256"], storage=storage, expected_storage_identity=storage["identity_sha256"]))
            reaches["reaches"][0]["cell_ids"] = [999]
            with self.assertRaises(ValueError):
                export_catchment_dynamic_review(records, root / "bad", reaches=reaches)
    def test_v6_wet_exclusive_inventory_and_no_unified_surface(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, hierarchy, storage = inputs(root, True)
            result = export_catchment_dynamic_review(records, root / "review")
            page = json.loads((root / "review/frame-0000.json").read_bytes())
            self.assertEqual(page["domain_totals"]["surface_volume_m3"], 5400.)
            self.assertEqual(page["domain_totals"]["soil_volume_m3"], 54.)
            self.assertEqual(page["domain_totals"]["fast_volume_m3"], 5.4)
            self.assertEqual(page["domain_totals"]["slow_volume_m3"], 13.5)
            self.assertEqual(sum(leaf["wet_count"] for leaf in page["leaves"]), 3)
            self.assertTrue(any(leaf["water_surface_min_m"] != leaf["water_surface_max_m"] for leaf in page["leaves"]))
            self.assertIsNone(page["interval_s"])
            self.assertFalse(result["flags"]["transient_converged"])

    def test_dry_frame_null_surface_and_actual_interval_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, _, _ = inputs(root)
            export_catchment_dynamic_review(records, root / "review")
            page = json.loads((root / "review/frame-0001.json").read_bytes())
            self.assertEqual(page["interval_s"], [0., 1.])
            self.assertTrue(all(leaf["water_surface_min_m"] is None and leaf["water_surface_max_m"] is None for leaf in page["leaves"]))
            self.assertEqual(page["domain_interval_ledger_m3"]["internal_net_m3"], 0)

    def test_native_reach_vertices_keep_wet_mask_no_mesh(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, hierarchy, storage = inputs(root, True)
            reaches = make_surface_reaches(hierarchy, threshold_area_m2=900, expected_hierarchy_identity=hierarchy["identity_sha256"], storage=storage, expected_storage_identity=storage["identity_sha256"])
            export_catchment_dynamic_review(records, root / "review", reaches=reaches)
            page = json.loads((root / "review/frame-0000.json").read_bytes())
            for record in page["native_reach_vertices"]:
                self.assertEqual(record["bed_plus_depth_m"], [float(hierarchy["arrays"]["height_m"].ravel()[cell] + storage["arrays"]["depth_m"][0, cell]) for cell in record["cell_ids"]])
                self.assertTrue(all(record["wet"]))

    def test_cold_load_no_generation_fresh_subprocess(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, _, _ = inputs(root)
            result = export_catchment_dynamic_review(records, root / "review")
            path = root / "review/index.json"
            with patch("terrain_pipeline.td_catchment_dynamic_review.export_catchment_dynamic_review", side_effect=AssertionError("export")):
                loaded = load_catchment_dynamic_review(path, expected_sha256=file_sha256(path), expected_identity=result["identity_sha256"], records=records)
            self.assertEqual(_plain(loaded), _plain(result))
            code = "import sys,json,importlib.abc\nclass Block(importlib.abc.MetaPathFinder):\n def find_spec(self,fullname,path=None,target=None):\n  if fullname in {'terrain_pipeline.td_basin_storage','terrain_pipeline.td_basin_storage_v6','terrain_pipeline.td_basin_transport_v6'}: raise AssertionError(fullname)\nsys.meta_path.insert(0,Block())\nfrom terrain_pipeline.td_catchment_dynamic_review import load_catchment_dynamic_review\nload_catchment_dynamic_review(sys.argv[1],expected_sha256=sys.argv[2],expected_identity=sys.argv[3],records=json.loads(sys.argv[4]))\n"
            completed = subprocess.run([sys.executable, "-c", code, str(path), file_sha256(path), result["identity_sha256"], json.dumps(records)], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_rehashed_time_coverage_version_and_page_tamper_rejected(self):
        for mutation in ("time", "coverage", "version", "volume"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                records, _, _ = inputs(root)
                export_catchment_dynamic_review(records, root / "review")
                path = root / "review/index.json"
                index = json.loads(path.read_bytes())
                if mutation == "version":
                    index["storage_version"]["algorithm"] = "fake"
                else:
                    page_path = root / "review/frame-0001.json"
                    page = json.loads(page_path.read_bytes())
                    if mutation == "time":
                        page["time_s"] = 99
                    elif mutation == "coverage":
                        page["leaves"].pop()
                    else:
                        page["leaves"][0]["surface_volume_m3"] = 99
                    page_path.write_text(json.dumps(page), encoding="utf-8")
                    index["pages"][1].update(expected_sha256=file_sha256(page_path), expected_identity=_hash(page), bytes=page_path.stat().st_size)
                index.pop("identity_sha256")
                index["identity_sha256"] = _hash(index)
                path.write_text(json.dumps(index), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_catchment_dynamic_review(path, expected_sha256=file_sha256(path), expected_identity=index["identity_sha256"], records=records)

    def test_wrong_input_pins_no_final_index_or_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records, _, _ = inputs(root)
            wrong = json.loads(json.dumps(records))
            wrong["storage"]["expected_identity"] = "0" * 64
            with self.assertRaises(ValueError):
                export_catchment_dynamic_review(wrong, root / "bad")
            self.assertFalse((root / "bad/index.json").exists())
            export_catchment_dynamic_review(records, root / "review")
            with self.assertRaises(FileExistsError):
                export_catchment_dynamic_review(records, root / "review")
