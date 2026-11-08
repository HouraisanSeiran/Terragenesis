"""Saved release behavior and linked evidence validation."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.surface_rivers import metric_river_release as release
from terrain_pipeline.surface_rivers.metric_river_release import (
    ROOT, SCHEMA, LEGACY_SCHEMA, _identity, assemble, assemble_results,
    export_release, load_release, resolve_release_pin,
)


class RiverReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.path = Path(cls.directory.name) / "product.json"
        with patch.object(release, "M3", Path(cls.directory.name) / "unavailable-acceptance.json"):
            cls.pin = assemble(ROOT / "verification/td-river-milestones/td1024-20261008-01/manifest.json", cls.path,
                               acceptance=ROOT / "verification/td-river-channel/m3-20261008-02/acceptance.json")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_real_td_layers_and_missing_m7(self):
        product = load_release(self.path, expected_sha256=self.pin["sha256"], expected_identity=self.pin["identity_sha256"])
        self.assertIn("m7_resolution_exchange_missing", product["gates"]["unresolved"])
        self.assertFalse(product["publishable"])
        layers = product["layers"]
        self.assertNotEqual(layers["original_bed"], layers["diagnostic_topology"])
        self.assertEqual(len(layers["flow_intervals"]["stages"]), len(layers["flow_intervals"]["signedEdgeQ"]) + 1)
        self.assertEqual(layers["accepted_geometry"]["status"], "unresolved")

    def test_edited_saved_stage_rejected(self):
        product = json.loads(self.path.read_text(encoding="utf-8"))
        product["layers"]["flow_intervals"]["stages"][0][0] += 1
        edited = self.path.parent / "edited.json"
        edited.write_text(json.dumps(product), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            load_release(edited)
        with self.assertRaisesRegex(ValueError, "external river product hash mismatch"):
            load_release(edited, expected_sha256=self.pin["sha256"])

    def test_linked_evidence_tamper_rejected(self):
        product = json.loads(self.path.read_text(encoding="utf-8"))
        product["pins"]["source_product"]["sha256"] = "0" * 64
        product["identity_sha256"] = _identity(product)
        edited = self.path.parent / "wrong-pin.json"
        edited.write_text(json.dumps(product), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "linked evidence hash mismatch"):
            load_release(edited)

    def test_publication_does_not_overwrite(self):
        with self.assertRaises(FileExistsError):
            assemble(ROOT / "verification/td-river-milestones/td1024-20261008-01/manifest.json", self.path)

    def test_final_m7_product_cold_loads_complete_traces_and_honest_gates(self):
        directory = ROOT / "web-preview/data/river-product-v1"
        pin = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))["product"]
        product = load_release(directory / pin["path"], expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
        self.assertEqual(product["gates"]["m7"]["cold_audit"]["status"], "accepted_conservative_1d_exchange")
        self.assertEqual(set(product["m7_comparison"]["cases"]), {"native", "uniform", "local_amr"})
        self.assertNotIn("m7_resolution_exchange_missing", product["gates"]["unresolved"])
        self.assertIn("m7_resolution_agreement_measured_unresolved", product["gates"]["unresolved"])
        self.assertEqual(product["m7_comparison"]["cases"]["native"]["channel_trace"]["identity_sha256"], product["pins"]["native_channel_trace"]["identity_sha256"])
        self.assertTrue(any(item["name"] == "global_channel_geometry" for item in product["gates"]["refused"]))

    def test_actual_m8_export_without_checkout_reads(self):
        directory = ROOT / "web-preview/data/river-product-v1"
        pin = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))["product"]
        base = directory / pin["path"]
        original = load_release(base)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "package" / "product.json"
            result = export_release(base, output)
            real_hash = release.file_sha256

            def only_package(path):
                self.assertTrue(Path(path).resolve().is_relative_to(output.parent))
                return real_hash(path)

            with patch.object(release, "ROOT", Path(temporary) / "no-checkout"), \
                    patch.object(release, "file_sha256", side_effect=only_package):
                product = load_release(output, expected_sha256=result["sha256"])
                self.assertEqual(product["schema"], SCHEMA)
                self.assertEqual(product["identity_inputs"], original["identity_inputs"])
                self.assertEqual(product["m7_comparison"], original["m7_comparison"])
                self.assertEqual(product["layers"], original["layers"])
                for name, evidence in product["pins"].items():
                    self.assertEqual(evidence["sha256"], original["pins"][name]["sha256"])
                    resolve_release_pin(output, product, evidence)
                for case in product["bounded_results"]["cases"]:
                    if case.get("comparison") is not None:
                        for evidence in case["comparison"]["artifacts"].values():
                            resolve_release_pin(output, product, evidence)
                        self.assertEqual(case["provenance_record"], next(
                            record["comparison"] for record in original["bounded_results"]["cases"]
                            if record["id"] == case["id"]))


class PortableReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.base = self.workspace / "legacy.json"
        evidence = self.workspace / "source.bin"
        evidence.write_bytes(b"immutable saved source")
        pin = {"path": evidence.name, "sha256": release.file_sha256(evidence), "identity_sha256": "source-identity"}
        product = {"schema": LEGACY_SCHEMA, "version": "historical", "publishable": False,
                   "pins": {"source_product": pin}, "source": {**pin, "kind": "fixture", "selection": {"original": True}},
                   "identity_inputs": {"raw_path": "D:/old/source.npz"}, "m7_comparison": None,
                   "gates": {"publishable": False, "accepted": [], "refused": [],
                             "unresolved": ["m7_resolution_exchange_missing"]}, "layers": {}}
        self.write_product(self.base, product)
        self.checkout = patch.object(release, "ROOT", self.workspace)
        self.checkout.start()
        self.addCleanup(self.checkout.stop)
        self.output = self.root / "package" / "release.json"
        export_release(self.base, self.output)

    def write_product(self, path, product):
        product["identity_sha256"] = _identity(product)
        path.write_text(json.dumps(product), encoding="utf-8")

    def test_relocation_and_reexport_preserve_source_and_provenance(self):
        relocated = self.root / "relocated"
        shutil.copytree(self.output.parent, relocated)
        path = relocated / self.output.name
        before = self.base.read_bytes()
        with patch.object(release, "ROOT", self.root / "unavailable"), \
                patch.object(release, "_linked", side_effect=AssertionError("checkout fallback")):
            product = load_release(path)
            self.assertEqual(product["path_semantics"], "release-relative")
            self.assertEqual(resolve_release_pin(path, product, product["source"]),
                             resolve_release_pin(path, product, product["pins"]["source_product"]))
            exported = self.root / "second" / "another-name.json"
            export_release(path, exported)
            copy = load_release(exported)
            self.assertEqual(copy["source"]["selection"], product["source"]["selection"])
            self.assertEqual(copy["identity_inputs"], product["identity_inputs"])
        self.assertEqual(self.base.read_bytes(), before)
        self.assertEqual(load_release(self.base)["schema"], LEGACY_SCHEMA)

    def test_missing_and_tampered_bundle_fail_without_fallback(self):
        product = load_release(self.output)
        path = resolve_release_pin(self.output, product, product["pins"]["source_product"])
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            load_release(self.output)
        with self.assertRaises(FileNotFoundError):
            export_release(self.output, self.root / "failed.json")
        self.assertFalse((self.root / "failed.json").exists())
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            load_release(self.output)

    def test_escaping_and_absolute_paths_rejected_in_both_formats(self):
        for base in (self.base, self.output):
            for relative in ("../source.bin", "/source.bin", "C:/source.bin", "C:source.bin",
                             "//server/share", "nested/../../source.bin", "nested\\source.bin"):
                with self.subTest(schema=base.name, path=relative):
                    product = json.loads(base.read_text(encoding="utf-8"))
                    product["pins"]["source_product"]["path"] = relative
                    edited = base.parent / "invalid.json"
                    self.write_product(edited, product)
                    with self.assertRaisesRegex(ValueError, "relative path"):
                        load_release(edited)

    def test_symlink_escape_rejected(self):
        link = self.output.parent / "escape.bin"
        try:
            link.symlink_to(self.workspace / "source.bin")
        except OSError as error:
            self.skipTest("symlinks unavailable: " + str(error))
        product = json.loads(self.output.read_text(encoding="utf-8"))
        product["pins"]["source_product"]["path"] = link.name
        self.write_product(self.output, product)
        with self.assertRaisesRegex(ValueError, "escapes anchor"):
            load_release(self.output)

    def test_resolved_escape_rejected_even_when_link_creation_unavailable(self):
        product = load_release(self.output)
        pin = product["pins"]["source_product"]
        candidate = self.output.parent / pin["path"]
        original_resolve = Path.resolve

        def resolve_path(path, *args, **kwargs):
            if path == candidate:
                return self.workspace / "source.bin"
            return original_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolve_path):
            with self.assertRaisesRegex(ValueError, "escapes anchor"):
                resolve_release_pin(self.output, product, pin)

    def test_copy_failure_leaves_no_release_or_evidence_directory(self):
        output = self.root / "failed" / "release.json"
        with patch.object(release.shutil, "copyfile", side_effect=OSError("copy failed")):
            with self.assertRaisesRegex(OSError, "copy failed"):
                export_release(self.output, output)
        self.assertFalse(output.exists())
        self.assertFalse((output.parent / (output.name + ".evidence")).exists())
        self.assertEqual(list(output.parent.iterdir()), [])

    def test_existing_bundle_and_release_are_never_overwritten(self):
        original = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            export_release(self.base, self.output)
        self.assertEqual(self.output.read_bytes(), original)
        other = self.output.parent / "other.json"
        evidence_dir = other.parent / (other.name + ".evidence")
        evidence_dir.mkdir()
        sentinel = evidence_dir / "sentinel"
        sentinel.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            export_release(self.base, other)
        self.assertEqual(sentinel.read_bytes(), b"existing")

    def test_unregistered_consumer_pin_is_rejected(self):
        product = load_release(self.output)
        product["source"]["path"] = "unbundled.bin"
        self.write_product(self.output, product)
        with self.assertRaisesRegex(ValueError, "not a registered"):
            load_release(self.output)

    def test_publication_rejects_mismatched_consumer_identity_before_copy(self):
        original = (self.workspace / "source.bin").read_bytes()
        for identity in ("wrong-identity", None):
            with self.subTest(identity=identity):
                product = load_release(self.output)
                paths = {name: resolve_release_pin(self.output, product, pin)
                         for name, pin in product["pins"].items()}
                if identity is None:
                    product["source"].pop("identity_sha256")
                else:
                    product["source"]["identity_sha256"] = identity
                output = self.root / "invalid-identity" / "product.json"
                with patch.object(release.shutil, "copyfile") as copy_file:
                    with self.assertRaisesRegex(ValueError, "not a registered"):
                        release._publish_release(product, output, paths)
                    copy_file.assert_not_called()
                self.assertFalse(output.parent.exists())
        self.assertEqual((self.workspace / "source.bin").read_bytes(), original)

    def test_results_assembly_from_relocated_base_and_relative_valley_reports(self):
        reports = self.root / "reports"
        reports.mkdir()
        artifact = reports / "geometry.npz"
        metadata = {"algorithm": "saved-test", "config": {"spacing_m": 1}}
        np.savez(artifact, manifest=np.frombuffer(json.dumps({"metadata": metadata}).encode(), dtype=np.uint8))
        pin = {"path": artifact.name, "sha256": release.file_sha256(artifact), "identity_sha256": "geometry-identity"}
        geometry = {"status": "accepted_bounded_geometry", "artifacts": {"td_fine": pin, "td_bend_fine": pin}}
        sediment = {"status": "accepted_bounded_sediment", "artifacts": {"td_fine": pin}}
        record = {"component": "4", "status": "accepted_shaped_component",
                  "artifacts": {role: pin for role in ("before", "coarse", "fine", "centerline")}}
        valley = {"status": "bounded_shaped_geometry", "cases": [record]}
        for name, payload in (("geometry", geometry), ("sediment", sediment), ("valley", valley)):
            (reports / (name + ".json")).write_text(json.dumps(payload), encoding="utf-8")
        original = load_release(self.output)
        result_path = self.root / "results" / "product.json"
        with patch.object(release, "ROOT", self.root / "unavailable"):
            result = assemble_results(self.output, result_path, geometry_report=reports / "geometry.json",
                                      sediment_report=reports / "sediment.json", valley_report=reports / "valley.json")
            product = load_release(result_path, expected_sha256=result["sha256"])
        self.assertEqual(product["source"]["sha256"], original["source"]["sha256"])
        self.assertEqual(product["identity_inputs"], original["identity_inputs"])
        self.assertEqual(product["source"]["selection"], original["source"]["selection"])
        case = product["bounded_results"]["cases"][-1]
        self.assertEqual(case["provenance_record"], record)
        for evidence in case["comparison"]["artifacts"].values():
            resolve_release_pin(result_path, product, evidence)
        report_path = resolve_release_pin(result_path, product, product["pins"]["valley_results_report"])
        self.assertEqual(report_path.read_bytes(), (reports / "valley.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
