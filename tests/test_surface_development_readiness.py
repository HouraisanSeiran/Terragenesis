import copy
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from terrain_pipeline import surface_development_readiness as readiness
from terrain_pipeline import dem_domain, surface_domain_prepare, surface_fine_mosaic
from terrain_pipeline import surface_coast_drop, surface_dynamic_prepare


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "verification"
PATHS = {
    "dem": EVIDENCE / "dem-domain/run-20260930T062026836139Z/dem-candidate.npz",
    "domain": EVIDENCE / "surface-domain-prepare/run-20260930T103111870204Z/two-domain-prepared.npz",
    "mosaic": EVIDENCE / "surface-fine-mosaic/run-20260930T123659.258177Z/old-two-domain-gap.npz",
    "drop": EVIDENCE / "surface-coast-drop/run-20260930T125523.932019Z/actual-river-engineering-coast.npz",
    "dynamic": EVIDENCE / "surface-dynamic-prepare/run-20260930T130638.804119Z/saved-old-prepared-domain1.npz",
}


class ReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = readiness.prepare_readiness(PATHS, dynamic_scope="lumped_storage_linear_conductance")

    def test_actual_bundles_are_diagnostic(self):
        diagnosis = self.manifest["diagnosis"]
        self.assertFalse(diagnosis["ready"])
        self.assertEqual(diagnosis["facts"]["dem_unknown_cells"], 33454)
        self.assertEqual(diagnosis["facts"]["mosaic_missing_cells"], 600)
        self.assertIn("dynamic_partial_graph_not_full_mosaic", diagnosis["blockers"])
        self.assertTrue(diagnosis["facts"]["dynamic_mosaic_artifact_different"])
        self.assertEqual(len(diagnosis["facts"]["dynamic_embedded_proof_ids"]), 1)
        self.assertNotIn("dynamic_and_mosaic_proof_graph_mismatch", diagnosis["blockers"])
        self.assertIn("coastline_and_natural_outlet_not_certified", diagnosis["blockers"])

    def test_identity_difference_alone_is_not_partial(self):
        proof = "a" * 64
        products = {
            "mosaic": {"cell_owner": np.zeros((1, 1), dtype=int), "source_identity": "source",
                       "proofs": {proof: {}}, "identity_sha256": "b" * 64,
                       "status": "prepared", "full_domain_mosaic_prepared": True},
            "dynamic": {"binding": {"area_semantics": "constant_area", "source_proof_sha256": proof,
                                    "source_mosaic": {"identity_sha256": "c" * 64,
                                                      "proofs": {proof: {}}}},
                        "full_dynamic_wave_prepared": False},
        }
        diagnosis = readiness._diagnose(products, "lumped_storage_linear_conductance")
        self.assertTrue(diagnosis["facts"]["dynamic_mosaic_artifact_different"])
        self.assertNotIn("dynamic_partial_graph_not_full_mosaic", diagnosis["blockers"])

    def test_saved_static_load_with_generation_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "readiness.json"
            readiness.save_readiness(self.manifest, path)
            with patch.object(readiness, "prepare_readiness", side_effect=AssertionError("generation called")), \
                 patch.object(dem_domain, "prepare_dem_candidate", create=True, side_effect=AssertionError("DEM generation called")), \
                 patch.object(surface_domain_prepare, "evaluate_surface_domains", side_effect=AssertionError("domain generation called")), \
                 patch.object(surface_fine_mosaic, "prepare_fine_mosaic", side_effect=AssertionError("mosaic generation called")), \
                 patch.object(surface_coast_drop, "prepare_coast_drop", side_effect=AssertionError("drop generation called")), \
                 patch.object(surface_dynamic_prepare, "prepare_surface_dynamic", side_effect=AssertionError("dynamic advance called")):
                self.assertEqual(readiness.load_readiness(path), self.manifest)

    def test_save_failure_leaves_no_target_or_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "readiness.json"
            with patch.object(readiness.os, "link", side_effect=OSError("publish failed")):
                with self.assertRaises(OSError):
                    readiness.save_readiness(self.manifest, target)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_rehashed_conclusion_and_identity_bypass_rejected(self):
        for change in (lambda value: value["diagnosis"].update(ready=True),
                       lambda value: value["diagnosis"].update(blockers=[]),
                       lambda value: value["bundles"]["mosaic"].update(sha256="0" * 64),
                       lambda value: value["bundles"]["dem"].update(identity_sha256="0" * 64)):
            modified = copy.deepcopy(self.manifest)
            change(modified)
            with self.subTest(modified=modified["diagnosis"]["ready"]):
                with self.assertRaises(ValueError):
                    readiness.load_readiness_dict(modified)

    def test_bad_bundle_and_missing_input(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "bad.npz"
            invalid.write_bytes(b"not a bundle")
            with self.assertRaises((ValueError, OSError)):
                readiness.prepare_readiness({"mosaic": invalid})
            diagnostic = readiness.prepare_readiness({"dem": PATHS["dem"]})
            self.assertIn("mosaic_bundle_missing", diagnostic["diagnosis"]["blockers"])

    def test_strict_json_types_rejected(self):
        changes = {
            "ready_integer": lambda value: value["diagnosis"].update(ready=0),
            "unknown_float": lambda value: value["diagnosis"]["facts"].update(dem_unknown_cells=33454.0),
            "bytes_boolean": lambda value: value["bundles"]["dem"].update(bytes=True),
            "bytes_float": lambda value: value["bundles"]["dem"].update(bytes=float(value["bundles"]["dem"]["bytes"])),
            "artifact_integer": lambda value: value["diagnosis"]["facts"].update(dynamic_mosaic_artifact_different=1),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "typed-forgery.json"
            for name, change in changes.items():
                modified = copy.deepcopy(self.manifest)
                change(modified)
                path.write_text(json.dumps(modified), encoding="utf-8")
                with self.subTest(change=name):
                    with self.assertRaises(ValueError):
                        readiness.load_readiness(path)

    def test_json_key_order_is_irrelevant(self):
        reordered = dict(reversed(list(self.manifest.items())))
        reordered["diagnosis"] = dict(reversed(list(reordered["diagnosis"].items())))
        self.assertEqual(readiness.load_readiness_dict(reordered), self.manifest)

    def test_ancestor_reparse_input_rejected(self):
        ancestor = PATHS["dem"].parent
        original_lstat = os.lstat

        def reparse_lstat(path, *args, **kwargs):
            actual = original_lstat(path, *args, **kwargs)
            if Path(path) == ancestor:
                fields = {name: getattr(actual, name) for name in dir(actual) if name.startswith("st_")}
                fields["st_file_attributes"] = getattr(actual, "st_file_attributes", 0) | stat.FILE_ATTRIBUTE_REPARSE_POINT
                return SimpleNamespace(**fields)
            return actual

        with patch.object(readiness.os, "lstat", side_effect=reparse_lstat):
            with self.assertRaisesRegex(ValueError, "linked or reparse"):
                readiness.prepare_readiness({"dem": PATHS["dem"]})

    def test_linked_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            linked = Path(directory) / "linked.npz"
            try:
                linked.symlink_to(PATHS["dem"])
            except OSError as error:
                self.skipTest("Windows symlink privilege unavailable: " + str(error))
            with self.assertRaisesRegex(ValueError, "linked or reparse"):
                readiness.prepare_readiness({"dem": linked})

    def test_json_forgery_and_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forged.json"
            path.write_text('{"format":1,"format":2}', encoding="utf-8")
            with self.assertRaises(ValueError):
                readiness.load_readiness(path)
        with self.assertRaises(ValueError):
            readiness.prepare_readiness(PATHS, dynamic_scope="anything")


if __name__ == "__main__":
    unittest.main()
