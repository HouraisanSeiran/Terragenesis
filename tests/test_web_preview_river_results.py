import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web-preview"))
import river_results
import global_geometry


class RiverResultsBindingTests(unittest.TestCase):
    def test_portable_valley_case_reads_without_workspace_evidence(self):
        from terrain_pipeline.surface_rivers import metric_river_release as release
        report = json.loads(river_results.VALLEY.read_text(encoding="utf-8"))
        original = next(case for case in report["cases"] if case["component"] == "4")
        artifact = original["artifacts"]["fine"]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "prepared"
            source.mkdir()
            geometry_pin = {**artifact, "path": "mesh.npz"}
            manifest_pin = {"path": "valley.json", "sha256": hashlib.sha256(river_results.VALLEY.read_bytes()).hexdigest()}
            shutil.copyfile(artifact["path"], source / geometry_pin["path"])
            shutil.copyfile(river_results.VALLEY, source / manifest_pin["path"])
            case = {"id": "valley-4", "label": "portable valley fixture", "kind": "shaped_valley_component",
                    "geometry": geometry_pin, "manifest": manifest_pin,
                    "comparison": {"artifacts": {"fine": geometry_pin}}}
            product = {"schema": release.SCHEMA, "path_semantics": release.PATH_SEMANTICS,
                       "version": "portable-adapter-test", "publishable": False,
                       "source": {**geometry_pin, "kind": "adapter geometry fixture"},
                       "pins": {"geometry": geometry_pin, "manifest": manifest_pin},
                       "gates": {"publishable": False, "accepted": [], "refused": [],
                                 "unresolved": ["m7_resolution_exchange_missing"]},
                       "bounded_results": {"cases": [case]}}
            product["identity_sha256"] = release._identity(product)
            product_path = source / "product.json"
            product_path.write_text(json.dumps(product), encoding="utf-8")
            pin = {"path": product_path.name, "sha256": hashlib.sha256(product_path.read_bytes()).hexdigest(),
                   "identity_sha256": product["identity_sha256"]}
            (source / "manifest.json").write_text(json.dumps({"product": pin}), encoding="utf-8")
            moved = source.rename(directory / "relocated")
            river_results.saved_case.cache_clear()
            try:
                with patch.object(release, "ROOT", directory / "unavailable-checkout"), \
                        patch.object(river_results, "VALLEY", directory / "unavailable-valley"), \
                        patch.object(river_results, "RELEASE_MANIFEST", moved / "manifest.json"):
                    manifest = river_results.release_manifest()
                    payload = river_results.saved_case("valley-4")
                self.assertEqual(manifest["cases"][0]["path"], "mesh.npz")
                self.assertEqual(payload["source"]["path"], "mesh.npz")
                self.assertEqual(payload["source"]["manifest_path"], "valley.json")
                self.assertEqual(payload["identity"], artifact["identity_sha256"])
                self.assertTrue(payload["mesh"]["triangles"])
            finally:
                river_results.saved_case.cache_clear()

    def test_global_coverage_preserves_declared_edges_and_td_coordinates(self):
        payload = global_geometry.saved_case()
        coverage = payload['global_geometry']
        accepted = set(map(tuple, coverage['accepted_edge_ids']))
        refused = set(map(tuple, coverage['refused_edge_ids']))
        self.assertEqual(len(accepted), 623)
        self.assertEqual(len(refused), 50)
        self.assertFalse(accepted & refused)
        self.assertEqual(len(accepted | refused), coverage['declared_edges'])
        self.assertFalse(payload['publishable'])
        self.assertEqual(payload['terrain']['x_m'][0], payload['source']['terrain']['x0_m'])
        self.assertEqual(payload['terrain']['z_m'][0], payload['source']['terrain']['z0_m'])
        source_id = coverage['refused_edge_ids'][0][0]
        row, column = divmod(source_id, 1024)
        terrain = payload['source']['terrain']
        self.assertEqual(coverage['refused_edge_points_xz_m'][0][0],
                         [terrain['x0_m'] + column * terrain['dx_m'], terrain['z0_m'] + row * terrain['dz_m']])
        self.assertEqual(payload['scope_exclusion']['diagnostic_sha256'], payload['evidence']['diagnostic']['sha256'])

    def test_m8_release_pins_valley_manifest_and_saved_mesh(self):
        release = river_results.release_manifest()
        valley = [item for item in release["cases"] if item["id"] == "valley-4"]
        self.assertEqual(len(valley), 1)
        pin = valley[0]
        manifest = river_results.VALLEY
        self.assertEqual(pin["manifest_sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())
        report = json.loads(manifest.read_text(encoding="utf-8"))
        case = next(item for item in report["cases"] if item["component"] == "4")
        self.assertEqual(pin["sha256"], case["artifacts"]["fine"]["sha256"])
        payload = river_results.saved_case("valley-4")
        self.assertEqual(payload["source"]["manifest_sha256"], pin["manifest_sha256"])
        self.assertEqual(payload["source"]["sha256"], pin["sha256"])
        self.assertEqual(payload["identity"], pin["identity_sha256"])
        self.assertTrue(payload["mesh"]["triangles"])


if __name__ == "__main__":
    unittest.main()
