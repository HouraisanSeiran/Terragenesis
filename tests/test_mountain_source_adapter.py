import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import (
    checked_archive,
    file_sha256,
    identity,
    load_legacy_source,
    load_physical_source,
    load_source_bundle,
    make_source,
    save_source,
    validate_source,
)


def mock_source(height=None):
    return make_source(np.arange(25, dtype=np.float64).reshape(5, 5) if height is None else height,
        origin_m_xz=[0., 0.], spacing_m=30.,
        provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
            "archive_sha256": "0" * 64, "test_fixture_only": True},
        boundary={"policy": "all_edges_open", "halo_cells": 0,
            "upstream_contribution": "excluded_finite_experiment"})


class SourceAdapterTests(unittest.TestCase):
    def test_trusted_mock_is_not_real_inference_evidence(self):
        source = mock_source()
        self.assertTrue(source["metadata"]["provenance"]["test_fixture_only"])
        self.assertFalse(source["metadata"]["domain"]["hydrological_closure_certified"])
        with self.assertRaises(ValueError):
            source["arrays"]["height_m"].setflags(write=True)

    def test_conditioning_rejected_even_when_resigned(self):
        source = mock_source()
        source["metadata"]["provenance"]["artifact_kind"] = "conditioning_only"
        source["identity_sha256"] = identity(source["arrays"], source["metadata"])
        with self.assertRaises(ValueError):
            validate_source(source)

    def test_atomic_cold_load_and_external_payload(self):
        source = mock_source()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.npz"
            save_source(path, source)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                save_source(path, source)
            self.assertEqual(path.read_bytes(), before)
            with patch("terrain_pipeline.common_infra.make_source", side_effect=AssertionError("prepare")):
                loaded = load_source_bundle(path, expected_sha256=file_sha256(path),
                    expected_identity=source["identity_sha256"], trusted_source=source)
            self.assertEqual(loaded["identity_sha256"], source["identity_sha256"])
            wrong = mock_source(np.ones((5, 5), np.float64))
            with self.assertRaises(ValueError):
                load_source_bundle(path, expected_sha256=file_sha256(path),
                    expected_identity=source["identity_sha256"], trusted_source=wrong)

    def test_physical_shape_preflight_before_numpy_load(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "oversized.npz"
            np.savez_compressed(path, elevation_m=np.zeros((513, 513), np.float32),
                climate=np.zeros((5, 513, 513), np.float32), metadata_json=np.array("{}"))
            with patch("numpy.load", side_effect=AssertionError("allocated too early")):
                with self.assertRaises(ValueError):
                    load_physical_source(path, expected_sha256=file_sha256(path), boundary={})

    def test_pickle_and_external_hash_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "object.npz"
            np.savez(path, data=np.array([{}], dtype=object))
            with self.assertRaises(ValueError):
                checked_archive(path, expected_sha256=file_sha256(path))
            with self.assertRaises(ValueError):
                checked_archive(path, expected_sha256="0" * 64)

    def test_failed_save_leaves_no_partial_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.npz"
            with patch("numpy.savez_compressed", side_effect=RuntimeError("write failed")):
                with self.assertRaises(RuntimeError):
                    save_source(path, mock_source())
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_fixed_actual_legacy_sources_keep_game_conditioning(self):
        for name in ("normal_mountain", "pressure_mountain"):
            source = load_legacy_source(name)
            self.assertEqual(source["arrays"]["height_m"].shape, (487, 487))
            self.assertTrue(source["metadata"]["provenance"]["historical_game_height_conditioning"])
            self.assertFalse(source["metadata"]["domain"]["hydrological_closure_certified"])


if __name__ == "__main__":
    unittest.main()
