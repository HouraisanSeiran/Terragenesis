"""Comparison provenance gates using bounded saved synthetic certificate fixtures."""

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.regional_surface_hydraulics import prepare_surface_geometry, SurfaceBudget
from terrain_pipeline.mountain_source_adapter import file_sha256
from tools.verify_regional_hydraulics_compare import compare


class RegionalComparisonTests(unittest.TestCase):
    def fixture(self, directory, *, forcing="same", forged=False):
        directory.mkdir()
        budget = vars(SurfaceBudget())
        (directory / "binding.json").write_text(json.dumps({"source_identity": "test", "height_source_identity": "height", "forcing_manifest_sha256": forcing, "budget": budget}), encoding="utf-8")
        geometry = prepare_surface_geometry(np.zeros((256, 256)), spacing_m=30., origin_m_xz=[-184320., 61440.], source_identity="test", boundary_kind=np.ones(1024, np.int64))
        if forged:
            geometry["arrays"]["face_crest_m"][0] += 1.
        np.savez(directory / "geometry.npz", **geometry["arrays"])
        (directory / "geometry.json").write_text(json.dumps(geometry["metadata"]), encoding="utf-8")
        (directory / "states.json").write_text(json.dumps({"metadata": {"status": "completed", "requested_time_s": 900.,
            "committed_time_s": 900., "failure": None, "wall_s": 1., "substeps": 30, "face_evaluations": 3947520}}), encoding="utf-8")
        np.savez_compressed(directory / "states.npz", time_s=np.array([0., 900.]), depth_m=np.zeros((2, 256, 256)),
            initial_depth_m=np.zeros((256, 256)), ledger=np.zeros((2, 5)), final_internal_q_m3_s=np.zeros(130560), final_boundary_q_m3_s=np.zeros(1024))
        artifacts = {path.name: file_sha256(path) for path in directory.iterdir()}
        (directory / "manifest.json").write_text(json.dumps({"artifacts": artifacts}), encoding="utf-8")
        return file_sha256(directory / "manifest.json")

    def test_dry_self_comparison_all_zero(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "base"
            digest = self.fixture(directory)
            result = compare(directory, directory, base_sha256=digest, other_sha256=digest)
            self.assertEqual(len(result["frames"]), 2)
            self.assertEqual(result["frames"][-1]["volume_L1_difference_m3"], 0.)
            self.assertNotIn("backwater", result["frames"][-1])

    def test_different_forcing_and_resigned_geometry_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root) / "base"
            base_sha = self.fixture(base)
            for name, options in (("forcing", {"forcing": "other"}), ("geometry", {"forged": True})):
                other = Path(root) / name
                other_sha = self.fixture(other, **options)
                with self.assertRaises(ValueError):
                    compare(base, other, base_sha256=base_sha, other_sha256=other_sha)


if __name__ == "__main__":
    unittest.main()
