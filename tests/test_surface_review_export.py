"""Pinned sources, review gates and atomic versioned export contracts."""

from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.test_surface_variable_storage import static_disabled

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("surface_review_exporter", ROOT / "web-preview/build_surface_review_data.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def disabled(stack):
    exporter._saved.cache_clear()
    static_disabled(stack)
    for target in ("terrain_pipeline.surface_engineering_prepare.prepare_surface_engineering",
                   "terrain_pipeline.surface_engineering_prepare.compose_surface_engineering",
                   "terrain_pipeline.surface_domain_mosaic.prepare_domain_mosaic",
                   "terrain_pipeline.surface_domain_mosaic._assemble",
                   "terrain_pipeline.surface_multidomain_dynamic.prepare_surface_multidomain_dynamic",
                   "terrain_pipeline.surface_land_coverage.prepare_surface_land_coverage",
                   "terrain_pipeline.surface_land_coverage._algebra",
                   "terrain_pipeline.surface_land_coverage._topology",
                   "terrain_pipeline.surface_coast_drop.prepare_coast_drop"):
        stack.enter_context(patch(target, side_effect=AssertionError("export generated geometry")))


class SurfaceReviewExportTests(unittest.TestCase):
    def test_real_cli_and_repeat_export(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            command = [sys.executable, "-X", "utf8", str(ROOT / "web-preview/build_surface_review_data.py"), "--output", directory]
            completed = subprocess.run(command, cwd=ROOT / "web-preview", env=environment,
                                       capture_output=True, text=True, timeout=240)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            old = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf8"))
            self.assertEqual(len(old["cases"]), 13)
            old_hashes = {entry["file"]: exporter.sha256(Path(directory) / entry["file"]) for entry in old["cases"]}
            with ExitStack() as stack:
                disabled(stack)
                exporter.main(directory)
            current = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf8"))
            self.assertNotEqual(old["cases"][0]["file"], current["cases"][0]["file"])
            self.assertEqual(old_hashes, {name: exporter.sha256(Path(directory) / name) for name in old_hashes})

    def test_contract_no_generation_and_sources_unchanged(self):
        before = {path: exporter.sha256(path) for path in exporter.EXPECTED}
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            disabled(stack)
            exporter.main(directory)
            manifest = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf8"))
            cases = {entry["caseId"]: json.loads((Path(directory) / entry["file"]).read_text(encoding="utf8")) for entry in manifest["cases"]}
            for entry in manifest["cases"]:
                self.assertEqual(entry["sha256"], exporter.sha256(Path(directory) / entry["file"]))
                self.assertTrue(entry["label"])
            variable = cases["variable-pulse"]
            self.assertAlmostEqual(sum(variable["timeseries"]["storages"][0]), 224.5721879136545)
            self.assertEqual(variable["timeseries"]["timeSeconds"][-1], 8.)
            self.assertEqual(len(variable["timeseries"]["ledgerColumns"]), 6)
            self.assertEqual(cases["variable-failed-prefix"]["timeseries"]["committedSteps"], 1)
            self.assertEqual(cases["variable-cancelled-prefix"]["timeseries"]["signedEdgeQ"], [])
            engineering = cases["two-domain-engineering"]
            self.assertEqual(len(engineering["outlets"]), 2)
            self.assertEqual(engineering["evidence"]["status"], "accepted_bounded_scope")
            for outlet in engineering["outlets"]:
                self.assertEqual(outlet["mesh"]["centerline"][-1][1:], [0.,90.])
            seam = cases["wet-cross-precision"]
            self.assertEqual(len(seam["mesh"]["cells"]), 800)
            self.assertEqual(len(seam["mesh"]["vertices"]), 861)
            self.assertEqual(sum(seam["mesh"]["wetCells"]), 645)
            self.assertEqual(seam["overlay"]["sharedBoundaryX"], 30)
            self.assertNotIn("candidateFootprint", seam["overlay"])
            self.assertEqual(set(value for row in seam["mesh"]["hydrologicOwner"] for value in row),
                             set(item["domain_id"] for item in seam["mesh"]["sourceKinds"]))
            dem = cases["dem-candidate"]["display"]
            self.assertEqual((dem["unknownCount"],dem["coreUnknownCount"]),(33454,30550))
            self.assertTrue(any(flag and value is None for flags,values in zip(dem["unknown"],dem["height"])
                                for flag,value in zip(flags,values)))
            land=cases["land-footprint-engineering"]
            self.assertEqual((len(land["mesh"]["vertices"]),len(land["mesh"]["cells"]),len(land["mesh"]["triangles"])),(10011,9800,19600))
            self.assertEqual(land["overlay"]["missingOuterAreaM2"],0)
            self.assertFalse(land["coverage"]["outletDynamicStorageIncluded"])
            for outlet in land["outlets"]:
                self.assertEqual(min(point[2] for point in outlet["mesh"]["bedVertices"]),75.)
        self.assertEqual(before, {path: exporter.sha256(path) for path in before})

    def test_failed_publish_preserves_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_bytes(b"old manifest")
            with patch.object(exporter.os, "replace", side_effect=OSError("simulated publish failure")):
                with self.assertRaises(OSError):
                    exporter.main(directory)
            self.assertEqual(manifest.read_bytes(), b"old manifest")
            self.assertFalse(list(Path(directory).glob(".manifest-*")))

    def test_cached_loader_cannot_hide_source_mutation(self):
        exporter.build_mosaic()
        original = exporter.sha256
        with patch.object(exporter,"sha256",side_effect=lambda path:"0"*64 if path==exporter.FIXED["mosaic"] else original(path)):
            with self.assertRaises(ValueError):
                exporter.build_mosaic()
        with patch.object(exporter,"sha256",side_effect=lambda path:"0"*64 if path==exporter.FIXED["dem"] else original(path)):
            with self.assertRaises(ValueError):
                exporter.build_dem()

    def test_review_gating_for_direct_builders(self):
        original = exporter.read_json
        review = exporter.FIXED["mosaic"].parent / "independent-review.json"
        with patch.object(exporter,"read_json",side_effect=lambda path:{"status":"pending"} if path==review else original(path)):
            self.assertEqual(exporter.build_mosaic()["evidence"]["status"],"pending_review")
        with patch.object(exporter,"read_json",side_effect=lambda path:{"status":"accepted_bounded_scope","identity_sha256":"0"*64} if path==review else original(path)):
            with self.assertRaises(ValueError):
                exporter.build_mosaic()
        report = exporter.FIXED["pulse"].parent / "report.json"
        with patch.object(exporter,"read_json",side_effect=lambda path:{"status":"failed"} if path==report else original(path)):
            with self.assertRaises(ValueError):
                exporter.dynamic_case(exporter.FIXED["pulse"],"test","test")


if __name__=="__main__":
    unittest.main()
