import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from terrain_pipeline import common_infra as bundles
from terrain_pipeline.artifacts.contracts import array_hash
from terrain_pipeline.common_infra import canonical_json, array_sha256, strict_json
from terrain_pipeline.common_infra import canonical_json as json_text, array_sha256 as shaped_array_hash
from terrain_pipeline.runoff import _hash as _hash
from terrain_pipeline.runoff import _json as _json
from terrain_pipeline.runoff import _strict_json as _strict_json


def validate(result):
    if result["identity_sha256"] != bundles.identity(result["arrays"], result["metadata"]):
        raise ValueError("identity mismatch")


class ArtifactBundleTests(unittest.TestCase):
    def result(self):
        arrays = {"height": np.arange(6, dtype=np.float64).reshape(2, 3),
                  "mask": np.array([True, False])}
        metadata = {"seed": 20261020, "name": "\u5c71\u5ddd"}
        return {"arrays": arrays, "metadata": metadata,
                "identity_sha256": bundles.identity(arrays, metadata)}

    def test_pre_refactor_identity_golden(self):
        self.assertEqual(self.result()["identity_sha256"],
                         "61cfbb9934c819b4c0a3c76a88eb59dd4adc5b1d5c846d542f70100bac5ce26e")

    def test_frozen_v1_encoding_equivalence_and_distinct_hashes(self):
        self.assertEqual(json_text({"b": "\u5c71", "a": [True, None, 1.25]}),
                         '{"a":[true,null,1.25],"b":"\\u5c71"}')
        for dtype in ("<f8", ">f8", "<i8", "uint8", "bool"):
            array = np.arange(6).astype(dtype).reshape(2, 3)
            self.assertEqual(shaped_array_hash(array), _hash(array))
        left = np.arange(6, dtype=np.float64)
        reshaped = left.reshape(2, 3)
        self.assertEqual(array_hash(left), array_hash(reshaped))
        self.assertNotEqual(shaped_array_hash(left), shaped_array_hash(reshaped))
        self.assertNotEqual(shaped_array_hash(left), shaped_array_hash(left.view(np.int64)))
        self.assertEqual(json_text(self.result()["metadata"]), _json(self.result()["metadata"]))
        for payload in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}'):
            for reader in (strict_json, _strict_json):
                with self.assertRaises(ValueError):
                    reader(payload)
        for writer in (json_text, _json):
            with self.assertRaises(ValueError):
                writer({"x": float("nan")})

    def test_roundtrip_immutable_independent_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested" / "bundle.npz"
            result = self.result()
            bundles.save_bundle(path, result, validator=validate)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                bundles.save_bundle(path, result, validator=validate)
            self.assertEqual(before, path.read_bytes())
            loaded = bundles.load_bundle(path, expected_sha256=bundles.file_sha256(path), validator=validate)
            for name, array in loaded["arrays"].items():
                np.testing.assert_array_equal(array, result["arrays"][name])
                with self.assertRaises(ValueError):
                    array.setflags(write=True)
            result["arrays"]["height"][0, 0] = 99
            self.assertEqual(loaded["arrays"]["height"][0, 0], 0)

    def test_header_validator_runs_before_allocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bundle.npz"
            bundles.save_bundle(path, self.result(), validator=validate)
            def reject(headers):
                self.assertEqual(headers["height"], ((2, 3), np.dtype("float64")))
                raise ValueError("consumer allocation budget")
            with patch("numpy.load", side_effect=AssertionError("early allocation")):
                with self.assertRaisesRegex(ValueError, "consumer allocation budget"):
                    bundles.checked_archive(path, expected_sha256=bundles.file_sha256(path),
                                            header_validator=reject)

    def test_failed_publication_and_racing_destination_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bundle.npz"
            with patch("numpy.savez_compressed", side_effect=RuntimeError("write")):
                with self.assertRaises(RuntimeError):
                    bundles.save_bundle(path, self.result(), validator=validate)
            self.assertEqual(list(Path(temporary).iterdir()), [])
            def race(temporary_path, destination):
                Path(destination).write_bytes(b"winner")
                raise FileExistsError(destination)
            with patch.object(bundles.os, "link", side_effect=race):
                with self.assertRaises(FileExistsError):
                    bundles.publish_bytes(path, b"loser")
            self.assertEqual(path.read_bytes(), b"winner")
            self.assertEqual(list(Path(temporary).iterdir()), [path])

    def test_archive_rejections_before_allocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.npz"
            np.savez(path, unsafe=np.array([{}], dtype=object))
            with patch("numpy.load", side_effect=AssertionError("early allocation")):
                with self.assertRaisesRegex(ValueError, "unsafe NPY"):
                    bundles.checked_archive(path, expected_sha256=bundles.file_sha256(path))
            np.savez(path, height=np.arange(6))
            digest = bundles.file_sha256(path)
            with self.assertRaisesRegex(ValueError, "compressed archive byte budget"):
                bundles.checked_archive(path, expected_sha256=digest, max_bytes=1)
            with self.assertRaisesRegex(ValueError, "external archive hash mismatch"):
                bundles.checked_archive(path, expected_sha256="0" * 64)
            stream = io.BytesIO()
            np.save(stream, np.arange(6))
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("folder/height.npy", stream.getvalue())
            with self.assertRaisesRegex(ValueError, "invalid archive member"):
                bundles.checked_archive(path, expected_sha256=bundles.file_sha256(path))

    def test_actual_pre_refactor_saved_bundle_cold_read(self):
        path = Path(__file__).resolve().parents[1] / (
            ".scratch/river-stage1-completion/m1-release-20261025-v1/data/geometry.npz")
        if not path.exists():
            self.skipTest("local saved review artifact is unavailable")
        self.assertEqual(bundles.file_sha256(path),
                         "4f59a4ec96c61f1a9bf41311f900c64661a273596d4aa828897fedf1c008fd72")
        result = bundles.load_bundle(path, expected_sha256=bundles.file_sha256(path), validator=validate)
        self.assertEqual(result["identity_sha256"],
                         "f06be2b08e8f86c139b7d3410c98f2fc2674e9d77db7fab5e1e623a45227684f")
        self.assertEqual(len(result["arrays"]), 27)
        self.assertTrue(all(not value.flags.writeable for value in result["arrays"].values()))


if __name__ == "__main__":
    unittest.main()
