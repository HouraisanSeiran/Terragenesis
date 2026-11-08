import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import file_sha256, make_source, save_bundle, validate_source
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from tools.prepare_td_river_diagnostic import prepare


def small_source(path):
    source = make_source(np.array([[3., 2., 1.], [4., 3., 0.], [5., 4., -1.]]),
                         origin_m_xz=(120., 240.), spacing_m=30.,
                         provenance={"artifact_kind": "terrain_diffusion_output",
                                     "td_inference_run": True, "archive_sha256": "a" * 64,
                                     "generation_metadata": {
                                         "seed": "42", "conditioning_identity": "b" * 64,
                                         "model": {"revision": "model-rev"}}},
                         boundary={"policy": "all_edges_open", "halo_cells": 0,
                                   "upstream_contribution": "excluded_finite_experiment"})
    save_bundle(path, source, validator=validate_source)
    return file_sha256(path)


class PrepareTDRiverDiagnosticTests(unittest.TestCase):
    def test_small_source_saves_cold_readable_diagnostic_and_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_path = root / "source.npz"
            source_sha = small_source(source_path)
            output = root / "run"
            summary = prepare(output, source_path=source_path, source_sha256=source_sha)
            self.assertEqual(summary["status"], "diagnostic_runoff")
            self.assertEqual(file_sha256(source_path), source_sha)
            self.assertEqual(set(path.name for path in output.iterdir()),
                             {"product.npz", "manifest.json", "provenance.json", "boundary-audit.json",
                              "mass-balance.json", "diagnostics.json"})
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
            boundary = json.loads((output / "boundary-audit.json").read_text(encoding="utf-8"))
            budget = json.loads((output / "mass-balance.json").read_text(encoding="utf-8"))
            product = load_diagnostic_product(output / "product.npz",
                                              expected_sha256=manifest["product_sha256"],
                                              expected_identity=manifest["product_identity_sha256"])
            self.assertEqual(product["arrays"]["time_seconds"].tolist(), [0., 300., 600., 900.])
            self.assertEqual(product["arrays"]["rain_mm_h"][:, 0, 0].tolist(), [30., 0., 0.])
            self.assertEqual(provenance["status"], "pending_provenance")
            self.assertEqual(provenance["generation_seed"], 42)
            self.assertEqual(provenance["model_revision"], "model-rev")
            self.assertEqual(provenance["conditioning_identity_sha256"], "b" * 64)
            self.assertEqual(boundary["open_perimeter_cells"], 8)
            self.assertEqual(boundary["natural_outlet_verified"], False)
            self.assertAlmostEqual(budget["rain_input"], 9 * 900 * 30 * 300 / 3600 / 1000)
            self.assertLess(abs(budget["combined_residual"]), 1e-10)
            self.assertFalse(manifest["publishable"])
            self.assertEqual(manifest["terrain_source_kind"], "generated_terrain")
            self.assertEqual(manifest["rainfall_source_sha256"], product["metadata"]["forcing"]["source_sha256"])
            self.assertEqual(manifest["parameter_sha256"], product["metadata"]["runoff_metadata"]["parameter_sha256"])
            self.assertEqual(manifest["time_semantics"], product["metadata"]["time_semantics"])
            with self.assertRaises(FileExistsError):
                prepare(output, source_path=source_path, source_sha256=source_sha)

    def test_bad_pin_publishes_refusal_without_product(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_path = root / "source.npz"
            small_source(source_path)
            output = root / "refused"
            summary = prepare(output, source_path=source_path, source_sha256="0" * 64)
            self.assertEqual(summary["status"], "refused")
            self.assertFalse((output / "product.npz").exists())
            refusal = json.loads((output / "refusal.json").read_text(encoding="utf-8"))
            self.assertIn("hash mismatch", refusal["reason"])
            self.assertFalse((root / "refused.partial").exists())


if __name__ == "__main__":
    unittest.main()
