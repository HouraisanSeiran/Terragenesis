import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.common_infra import BoundaryGrid, TerrainGrid
from terrain_pipeline.drainage import compare_routing_policies as compare_routing_policies
from terrain_pipeline.drainage import save_routing_comparison as save_routing_comparison
from tools.prepare_td_reference_routing import prepare


def _tiny_input(root):
    input_dir = root / "input"
    input_dir.mkdir()
    height = np.array([[4., 3., 2.], [5., 1., 2.], [6., 4., 0.]])
    terrain = TerrainGrid(height, np.ones(height.shape, bool), 0., 0., 3., 4.,
                          "diagnostic_dem_proxy", "tiny", "a" * 64)
    kinds = np.full(height.shape, "open_outflow", dtype="U24")
    kinds[1, 1] = "interior"
    boundary = BoundaryGrid(kinds, np.zeros(height.shape, bool), "tiny", "b" * 64)
    bundle = compare_routing_policies(terrain, boundary)
    package = input_dir / "routing-comparison.npz"
    save_routing_comparison(package, bundle)
    manifest = {
        "schema": "td-river-m1-m2-preparation-v1", "status": "diagnostic_m1_m2",
        "cold_read_verified": True, "hydraulic_ready": False,
        "natural_outlet_verified": False, "publishable": False,
        "artifacts": {"routing-comparison": {"path": package.name,
                      "sha256": file_sha256(package), "identity_sha256": bundle["identity_sha256"]}},
    }
    _write_manifest(input_dir, manifest)
    return input_dir, manifest


def _write_manifest(input_dir, manifest):
    path = input_dir / "manifest.json"
    path.write_text(json.dumps(manifest, allow_nan=False), encoding="utf-8")
    return file_sha256(path)


class PrepareReferenceRoutingTests(unittest.TestCase):
    def test_pins_and_existing_output_fail_before_backend(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_dir, manifest = _tiny_input(root)
            output = root / "analysis"
            with patch("tools.prepare_td_reference_routing._reference_api") as backend:
                with self.assertRaisesRegex(ValueError, "manifest SHA256"):
                    prepare(input_dir, output, manifest_sha256="0" * 64)
                for field in ("sha256", "identity_sha256"):
                    with self.subTest(pin=field):
                        tampered = copy.deepcopy(manifest)
                        tampered["artifacts"]["routing-comparison"][field] = "0" * 64
                        pin = _write_manifest(input_dir, tampered)
                        with self.assertRaises(ValueError):
                            prepare(input_dir, output, manifest_sha256=pin)
                        self.assertFalse(output.exists())
                pin = _write_manifest(input_dir, manifest)
                output.mkdir()
                marker = output / "keep.txt"
                marker.write_text("keep", encoding="utf-8")
                with self.assertRaises(FileExistsError):
                    prepare(input_dir, output, manifest_sha256=pin)
                self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
                backend.assert_not_called()
            self.assertEqual(list(root.glob(".analysis.partial-*")), [])

    def test_missing_backend_cleans_only_own_staging_and_preserves_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_dir, _ = _tiny_input(root)
            output = root / "analysis"
            unrelated = root / ".analysis.partial-other"
            unrelated.mkdir()
            marker = unrelated / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            before = {path.name: path.read_bytes() for path in input_dir.iterdir()}
            original_import = importlib.import_module

            def missing_backend(name, *args, **kwargs):
                if name == "pyflwdir":
                    raise ModuleNotFoundError("No module named 'pyflwdir'")
                return original_import(name, *args, **kwargs)

            with patch("tools.prepare_td_reference_routing.importlib.import_module", missing_backend):
                with self.assertRaisesRegex(ImportError, "algorithm/requirements-reference.txt"):
                    prepare(input_dir, output,
                            manifest_sha256=file_sha256(input_dir / "manifest.json"))
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".analysis.partial-*")), [unrelated])
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertEqual(before, {path.name: path.read_bytes() for path in input_dir.iterdir()})


if __name__ == "__main__":
    unittest.main()
