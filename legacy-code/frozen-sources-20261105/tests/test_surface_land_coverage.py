"""Fixed physical land footprint, immutable source and static archive proofs."""

from contextlib import ExitStack
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import warnings
from unittest.mock import patch
import zipfile

import numpy as np

from terrain_pipeline import surface_coast_drop as coast
from terrain_pipeline import surface_engineering_prepare as engineering
from terrain_pipeline import surface_land_coverage as coverage

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "verification/surface-engineering-prepare/run-20260930T193214454541Z/two-domain-engineering.npz"
SOURCE_SHA256 = "30f011385e72d346475ec1f6f0c71f74da216a238f38628c4b0668741628097e"


@lru_cache(maxsize=1)
def fixture():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise AssertionError("frozen source changed")
    source = engineering.load_surface_engineering(SOURCE)
    return source, coverage.prepare_surface_land_coverage(source)


class SurfaceLandCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.result = fixture()

    def test_unique_footprint_and_original_interior(self):
        record = self.result
        self.assertEqual(record["nodes"]["xz_m"].shape, (10011, 2))
        self.assertEqual(record["triangles"].shape, (19600, 3))
        self.assertEqual(record["ledger"]["land_area_m2"], 9800.)
        np.testing.assert_array_equal(np.bincount(record["domain_owner"])[1:], [4900, 4900])
        self.assertEqual(int((record["nodes"]["xz_m"][:, 0] == 75).sum()), 71)
        for name in self.source["domain_mosaic"]["nodes"]:
            if name in record["nodes"]:
                np.testing.assert_array_equal(record["nodes"][name][record["audit"]["interior_node_ids"]],
                                              self.source["domain_mosaic"]["nodes"][name])
        self.assertAlmostEqual(record["ledger"]["outer_cut_volume_m3"], 70.77028762295504)
        self.assertAlmostEqual(record["ledger"]["interior_cut_volume_m3"], 576.8710544290027)
        self.assertEqual(record["ledger"]["land_static_wet_cells"], 706)
        self.assertEqual(record["ledger"]["source_dynamic_wet_cells"], 676)

    def test_half_pixel_source_support_no_positive_ocean(self):
        audit = self.result["audit"]
        self.assertFalse(np.any(audit["positive_mask"] & ~audit["valid_land_support"]))
        np.testing.assert_allclose(audit["weights"].sum(axis=1), 1., atol=1e-14)
        for domain_id, drop in zip((1, 2), self.source["drops"]):
            selected = self.result["audit"]["engineering_strip_domain"] == domain_id
            self.assertEqual(int(selected.sum()), 24)
            h0 = self.result["nodes"]["h0_m"][selected].reshape(6, 4)
            self.assertFalse(np.array_equal(h0, drop["arrays"]["h0_m"][:24].reshape(6, 4)))

    def test_crop_and_shared_xyz_no_duplicate_area_or_q(self):
        for outlet in self.result["outside_outlets"]:
            ids = outlet["shared_land_node_ids"]
            nodes = self.result["nodes"]
            np.testing.assert_array_equal(outlet["bed_xyz_m"][:4, 1], nodes["h2_m"][ids])
            np.testing.assert_array_equal(outlet["water_xyz_m"][:4, 1], nodes["water_surface_m"][ids])
            self.assertEqual(outlet["triangles"].shape, (90, 3))
            self.assertTrue(np.all(outlet["bed_xyz_m"][:, 2] >= 75))
            self.assertAlmostEqual(outlet["terminal_q_m3_s"], .200049)
        self.assertEqual(self.result["ledger"]["outside_attachment_area_m2"], 90.)

    def test_static_roundtrip_no_assembly_or_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "land.npz"
            coverage.save_surface_land_coverage(self.result, path)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(FileExistsError):
                coverage.save_surface_land_coverage(self.result, path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            with ExitStack() as stack:
                for name in ("_algebra", "_topology", "prepare_surface_land_coverage"):
                    stack.enter_context(patch.object(coverage, name, side_effect=AssertionError("assembly")))
                for target in ("terrain_pipeline.surface_network_recovery.recover_surface_network",
                               "terrain_pipeline.surface_domain_mosaic._assemble",
                               "terrain_pipeline.surface_coast_drop._sample",
                               "terrain_pipeline.surface_coast_drop._attachment",
                               "terrain_pipeline.surface_dynamic_prepare.bind_surface_dynamic_source",
                               "terrain_pipeline.dynamic_surface_hydraulics.evaluate",
                               "terrain_pipeline.surface_variable_storage._advance",
                               "terrain_pipeline.surface_variable_storage._geometry"):
                    stack.enter_context(patch(target, side_effect=AssertionError("generation")))
                loaded = coverage.load_surface_land_coverage(path)
                query = coverage.query_surface_land_coverage(loaded)
            self.assertEqual(loaded["identity_sha256"], self.result["identity_sha256"])
            self.assertEqual(query["fixed_dynamic_wet_cells"], 676)
            with self.assertRaises(ValueError):
                query["nodes"]["h2_m"].setflags(write=True)

    def test_coherent_hash_forgeries_rejected(self):
        for mode in ("stencil", "owner", "bed", "water", "crop", "ledger", "scope", "shape"):
            record = deepcopy(coast._plain(self.result))
            if mode == "stencil":
                record["audit"]["weights"][0, 0] += .1
            elif mode == "owner":
                record["domain_owner"][0] = 2
            elif mode == "bed":
                record["nodes"]["h2_m"][-1] -= .2
            elif mode == "water":
                record["nodes"]["water_surface_m"][0] = 1.
            elif mode == "crop":
                record["outside_outlets"][0]["shared_land_node_ids"][0] += 1
            elif mode == "ledger":
                record["ledger"]["outer_cut_volume_m3"] = 0.
            elif mode == "scope":
                record["land_pixel_footprint_represented"] = 1
            else:
                record["grid"]["shape_nodes_zx"][0] = 71.
            record["identity_sha256"] = coast.fingerprint({key: value for key, value in record.items()
                                                           if key != "identity_sha256"})
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                coverage.validate_surface_land_coverage(coast._freeze(record))

    def test_resource_and_cancellation_preflight(self):
        for value in (True, 1024.):
            with self.assertRaises(ValueError):
                coverage.CoverageResources(max_working_bytes=value)
        with patch.object(coverage, "_algebra", side_effect=AssertionError("allocated")):
            with self.assertRaises(ValueError):
                coverage.prepare_surface_land_coverage(self.source,
                    resources=coverage.CoverageResources(max_working_bytes=1024))
            with self.assertRaises(InterruptedError):
                coverage.prepare_surface_land_coverage(self.source, cancel=lambda: True)

    def test_archive_strict_headers_before_load(self):
        headers = ["{'descr':'<f8','fortran_order':False,'shape':(1.0,)}",
                   "{'descr':'<f8','fortran_order':False,'shape':(True,)}",
                   "{'descr':'<f8','fortran_order':0,'shape':(1,)}",
                   "{'descr':'<f8','fortran_order':False,'shape':(1,),'shape':(1,)}"]
        with tempfile.TemporaryDirectory() as directory:
            for index, header in enumerate(headers):
                path = Path(directory) / (str(index) + ".npz")
                raw = header.encode("latin1") + b"\n"
                spec = {"$array": "array_0.npy", "shape": [1], "dtype": "<f8", "sha256": "0" * 64}
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("metadata.json", json.dumps({"format": coverage.VERSION + "-npy-v1",
                        "tree": {"resources": {}, "array": spec}}))
                    archive.writestr("array_0.npy", b"\x93NUMPY\x01\x00" + len(raw).to_bytes(2, "little") + raw + b"\0" * 8)
                with self.subTest(header=header), patch.object(np, "load", side_effect=AssertionError("allocated")), \
                     self.assertRaises(ValueError):
                    coverage.load_surface_land_coverage(path)

    def test_atomic_publication_race_preserves_winner_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "land.npz"
            winner = b"another writer's completed artifact"
            def competing_writer(temporary, target):
                self.assertTrue(Path(temporary).is_file())
                Path(target).write_bytes(winner)
                raise FileExistsError(target)
            with patch.object(coverage.os, "link", side_effect=competing_writer), self.assertRaises(FileExistsError):
                coverage.save_surface_land_coverage(self.result, destination)
            self.assertEqual(destination.read_bytes(), winner)
            self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_final_prepare_cancel_leaves_source_immutable(self):
        calls = 0
        before = coast.fingerprint(self.source)
        def final_cancel():
            nonlocal calls
            calls += 1
            return calls == 3
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(coverage, "save_surface_land_coverage", side_effect=AssertionError("published")), \
             self.assertRaises(InterruptedError):
            coverage.prepare_surface_land_coverage(self.source, cancel=final_cancel)
            self.fail("final cancellation returned a product")
        self.assertEqual(calls, 3)
        self.assertEqual(coast.fingerprint(self.source), before)
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), SOURCE_SHA256)

    def test_archive_duplicate_compressed_unused_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.npz"
            coverage.save_surface_land_coverage(self.result, original)
            for mode in ("duplicate", "compressed", "unused"):
                path = Path(directory) / (mode + ".npz")
                with zipfile.ZipFile(original) as source, zipfile.ZipFile(path, "w") as target:
                    for name in source.namelist():
                        target.writestr(name, source.read(name), compress_type=
                            zipfile.ZIP_DEFLATED if mode == "compressed" and name == "metadata.json"
                            else zipfile.ZIP_STORED)
                    if mode == "duplicate":
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", UserWarning)
                            target.writestr("metadata.json", source.read("metadata.json"))
                    elif mode == "unused":
                        target.writestr("unused.npy", b"not referenced")
                with self.subTest(mode=mode), patch.object(np, "load", side_effect=AssertionError("allocated")), \
                     self.assertRaises(ValueError):
                    coverage.load_surface_land_coverage(path)


if __name__ == "__main__":
    unittest.main()
