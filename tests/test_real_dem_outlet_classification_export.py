import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import from_origin

from terrain_pipeline.dem_domain import prepare_dem_candidate, save_dem_candidate
from tools import verify_real_dem_outlet_classification as exporter


class OutletClassificationExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        root_patch = patch.object(exporter, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        source = self.root / "source.tif"
        with rasterio.open(source, "w", driver="GTiff", width=160, height=160,
                           count=1, dtype="float32", crs="EPSG:4326",
                           transform=from_origin(121.35, 29.47, .001, .001),
                           nodata=-32768.) as output:
            output.write(np.full((160, 160), 10., dtype=np.float32), 1)
        candidate = prepare_dem_candidate(
            source, (121.40, 29.40, 121.42, 29.42), target_crs="EPSG:32651",
            spacing_m=90., halo_m=180., sea_level_m=0., sea_datum="unknown numeric zero",
            source_declaration="synthetic test elevation assumed metres; local research only")
        self.candidate_path = self.root / "candidate.npz"
        save_dem_candidate(candidate, self.candidate_path)
        self.source = source
        archive = self.root / "HydroRIVERS_v10_as_shp.zip"
        archive.write_bytes(b"synthetic archive; no scan required")
        basin = self.root / "basin.shp"
        basin.write_bytes(b"synthetic coarse basin")
        self.archive = archive
        self.basin = basin
        self.audit = {"sources": []}
        for path in (archive, basin):
            record = exporter.source_record(path)
            self.audit["sources"].append({"path": record["path"], "bytes": record["bytes"],
                                          "sha256_before": record["sha256"],
                                          "sha256_after": record["sha256"], "unchanged": True})
        self.vectors = {"source_archive_sha256": exporter.file_sha256(archive),
                        "policy": {"natural_mouth_verified": False}, "rivers": []}
        self.audit_path = self.root / "audit.json"
        self.vectors_path = self.root / "vectors.json"
        self.write_inputs()
        self.report = {"summary": {"classification_counts": {"unresolved": 1},
                                   "matched_terminal_count": 0},
                       "terminals": [{"natural_mouth_verified": False}]}
        self.module = SimpleNamespace(
            __file__=__file__, build_outlet_classification=self.build_report,
            validate_outlet_classification=lambda *args: {"valid": True},
            classification_geojson=lambda report: {"type": "FeatureCollection", "features": []})
        original_import = exporter.importlib.import_module

        def import_classifier(name, *args, **kwargs):
            if name == "terrain_pipeline.real_dem_outlet_classification":
                return self.module
            return original_import(name, *args, **kwargs)

        module_patch = patch.object(exporter.importlib, "import_module", side_effect=import_classifier)
        module_patch.start()
        self.addCleanup(module_patch.stop)
        self.options = {"candidate_path": self.candidate_path, "vectors_path": self.vectors_path,
                        "audit_path": self.audit_path, "match_distance_m": 180.0}
        self.output_root = self.root / "verification" / "exports"

    def build_report(self, candidate, vectors, audit, *, match_distance_m):
        self.assertIn("arrays", candidate)
        self.assertEqual(vectors, self.vectors)
        self.assertEqual(audit, self.audit)
        self.assertEqual(match_distance_m, 180.)
        return copy.deepcopy(self.report)

    def write_inputs(self):
        self.audit_path.write_bytes(exporter.canonical_bytes(self.audit))
        self.vectors_path.write_bytes(exporter.canonical_bytes(self.vectors))

    def export(self):
        return exporter.export_package(output_root=self.output_root, **self.options)[0]

    def rehash_artifact(self, output, name, value):
        payload = exporter.canonical_bytes(value)
        (output / name).write_bytes(payload)
        manifest = exporter.read_json(output / "manifest.json")
        manifest["artifacts"][name]["sha256"] = hashlib.sha256(payload).hexdigest()
        manifest["artifacts"][name]["bytes"] = len(payload)
        (output / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))

    def test_round_trip_new_runs_and_read_only_verification(self):
        first = self.export()
        before = {path.name: path.read_bytes() for path in first.iterdir()}
        second = self.export()
        self.assertNotEqual(first, second)
        self.assertEqual(before, {path.name: path.read_bytes() for path in second.iterdir()})
        directories = set(self.output_root.iterdir())
        self.assertEqual(exporter.verify_package(first, **self.options), self.report)
        self.assertEqual(directories, set(self.output_root.iterdir()))
        self.assertEqual(before, {path.name: path.read_bytes() for path in first.iterdir()})
        manifest = exporter.read_json(first / "manifest.json")
        self.assertEqual(len(manifest["source_files"]), 3)
        self.assertIn(str(self.source), [record["path"] for record in manifest["source_files"]])
        self.assertTrue(manifest["source_unchanged"])

    def test_cli_verify_uses_explicit_bound_inputs(self):
        output = self.export()
        with patch("builtins.print") as print_result:
            exporter.main(["--candidate", str(self.candidate_path), "--vectors", str(self.vectors_path),
                           "--audit", str(self.audit_path), "--verify-package", str(output)])
        result = json.loads(print_result.call_args.args[0])
        self.assertTrue(result["verified"])
        self.assertTrue(result["source_unchanged"])

    def test_rehashed_natural_claims_rejected_in_every_product(self):
        for name in exporter.PRODUCTS:
            with self.subTest(name=name):
                output = self.export()
                value = exporter.read_json(output / name)
                value["natural_mouth_verified"] = True
                self.rehash_artifact(output, name, value)
                with self.assertRaises(ValueError):
                    exporter.verify_package(output, **self.options)

    def test_rehashed_non_natural_forgery_rejected(self):
        output = self.export()
        value = exporter.read_json(output / "classification.json")
        value["summary"]["matched_terminal_count"] = 999
        self.rehash_artifact(output, "classification.json", value)
        with self.assertRaises(ValueError):
            exporter.verify_package(output, **self.options)

    def test_manifest_input_paths_are_not_authority(self):
        output = self.export()
        manifest = exporter.read_json(output / "manifest.json")
        manifest["inputs"]["candidate"]["path"] = str(self.root / "nonexistent.npz")
        (output / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))
        with self.assertRaises(ValueError):
            exporter.verify_package(output, **self.options)

    def test_rebound_inputs_require_external_binding(self):
        output = self.export()
        other = self.root / "other-vectors.json"
        other.write_bytes(self.vectors_path.read_bytes())
        with self.assertRaises(ValueError):
            exporter.verify_package(output, **{**self.options, "vectors_path": other})

    def test_manifest_path_traversal_and_fake_hash_rejected(self):
        for key, value in (("path", "../classification.json"), ("sha256", "not-a-hash")):
            output = self.export()
            manifest = exporter.read_json(output / "manifest.json")
            manifest["artifacts"]["classification.json"][key] = value
            (output / "manifest.json").write_bytes(exporter.canonical_bytes(manifest))
            with self.assertRaises(ValueError):
                exporter.verify_package(output, **self.options)

    def test_extra_package_file_rejected(self):
        output = self.export()
        (output / "extra.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            exporter.verify_package(output, **self.options)

    def test_duplicate_and_nonfinite_json_rejected(self):
        for payload in ('{"duplicate":1,"duplicate":2}', '{"value":NaN}',
                        '{"value":Infinity}', '{"value":1e999}'):
            with self.subTest(payload=payload):
                self.vectors_path.write_text(payload, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.export()
                self.assertFalse(self.output_root.exists())

    def test_all_audit_sources_hashed_not_only_archive(self):
        self.basin.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "audit source mismatch"):
            self.export()
        self.assertFalse(self.output_root.exists())

    def test_archive_binding_and_audit_before_after_required(self):
        self.vectors["source_archive_sha256"] = "0" * 64
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "archive binding"):
            self.export()
        self.vectors["source_archive_sha256"] = exporter.file_sha256(self.archive)
        self.audit["sources"][1]["sha256_after"] = "0" * 64
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "audit source mismatch"):
            self.export()

    def test_changed_dem_source_rejected(self):
        with self.source.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "candidate/source binding"):
            self.export()

    def test_source_mutation_during_compute_prevents_publication(self):
        original = self.module.build_outlet_classification

        def changing_report(*args, **kwargs):
            report = original(*args, **kwargs)
            self.basin.write_bytes(b"changed during compute")
            return report

        self.module.build_outlet_classification = changing_report
        with self.assertRaisesRegex(ValueError, "source changed"):
            self.export()
        self.assertEqual(list(self.output_root.iterdir()), [])

    def test_write_failure_leaves_no_partial_run(self):
        with patch.object(Path, "write_bytes", side_effect=OSError("simulated write failure")):
            with self.assertRaises(OSError):
                self.export()
        self.assertEqual(list(self.output_root.iterdir()), [])

    def test_invalid_distances_and_external_output_rejected(self):
        for distance in (0., -1., float("nan"), float("inf"), True):
            with self.subTest(distance=distance), self.assertRaises(ValueError):
                exporter.export_package(output_root=self.output_root,
                                        **{**self.options, "match_distance_m": distance})
        with self.assertRaisesRegex(ValueError, "inside workspace/verification"):
            exporter.export_package(output_root=self.root.parent / "outside", **self.options)

    def test_output_root_rejects_data_and_verification_root(self):
        for output in (self.root / "data", self.root, self.root / "verification"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                exporter.export_package(output_root=output, **self.options)
        self.assertFalse(self.output_root.exists())

    def test_output_root_rejects_input_directory_and_ancestors(self):
        directory = self.root / "verification" / "inputs" / "frozen"
        directory.mkdir(parents=True)
        candidate = directory / "candidate.npz"
        candidate.write_bytes(self.candidate_path.read_bytes())
        for output in (directory, directory.parent):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "contains an input"):
                exporter.export_package(output_root=output,
                                        **{**self.options, "candidate_path": candidate})
            self.assertEqual(list(directory.iterdir()), [candidate])

    def test_output_root_rejects_source_directory_and_ancestors(self):
        directory = self.root / "verification" / "sources" / "frozen"
        directory.mkdir(parents=True)
        archive = directory / self.archive.name
        archive.write_bytes(self.archive.read_bytes())
        self.audit["sources"][0]["path"] = str(archive)
        self.write_inputs()
        for output in (directory, directory.parent):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "contains an input or source"):
                exporter.export_package(output_root=output, **self.options)
            self.assertEqual(list(directory.iterdir()), [archive])

    def test_natural_input_and_classifier_claims_rejected(self):
        self.vectors["policy"]["natural_mouth_verified"] = True
        self.write_inputs()
        with self.assertRaisesRegex(ValueError, "natural certification"):
            self.export()
        self.vectors["policy"]["natural_mouth_verified"] = False
        self.write_inputs()
        self.report["terminals"][0]["natural_mouth_verified"] = True
        with self.assertRaisesRegex(ValueError, "natural certification"):
            self.export()


if __name__ == "__main__":
    unittest.main()
