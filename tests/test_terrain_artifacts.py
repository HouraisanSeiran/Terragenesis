import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.artifacts import ArtifactIdentity, SurfaceWater, TerrainArtifact, load_artifact, save_artifact
from terrain_pipeline.artifacts import storage


def base(**changes):
    values = dict(kind="base", identity=ArtifactIdentity("fixture", "height", "1", 7, {"a": 1, "b": [2]}),
                  reference_elevation_m=np.array([[10, 11, 12], [13, 14, 15]]),
                  origin_x_m=100, origin_z_m=-20, spacing_x_m=2, spacing_z_m=3,
                  vertical_datum="fixture sea datum", sea_level_elevation_m=0)
    values.update(changes)
    return TerrainArtifact(**values)


class ArtifactTests(unittest.TestCase):
    def test_non_square_coordinates_and_displacements(self):
        source = base()
        vectors = np.zeros((3, 2, 3))
        vectors[1] = 4
        derived = base(kind="derived", source_artifact_id=source.content_id,
                       displacement_type="vertical", displacement_m=vectors)
        np.testing.assert_array_equal(derived.reconstruct_positions_m()[:, 1, 2], [104, 19, -17])
        derived.verify_source(source)
        vectors[0] = 1
        with self.assertRaises(ValueError):
            base(kind="derived", source_artifact_id=source.content_id,
                 displacement_type="vertical", displacement_m=vectors)
        xyz = base(kind="derived", source_artifact_id=source.content_id,
                   displacement_type="xyz", displacement_m=vectors)
        self.assertEqual(xyz.reconstruct_positions_m()[0, 0, 0], 101)

    def test_source_arrays_and_parameters_are_immutable(self):
        height = np.ones((2, 3))
        params = {"nested": [1]}
        identity = ArtifactIdentity("fixture", "height", "1", 1, params)
        artifact = base(identity=identity, reference_elevation_m=height)
        height[0, 0] = 99
        params["nested"][0] = 99
        self.assertEqual(artifact.reference_elevation_m[0, 0], 1)
        self.assertEqual(identity.record()["parameters"], {"nested": [1]})
        with self.assertRaises(ValueError):
            artifact.reference_elevation_m.setflags(write=True)
        with self.assertRaises(TypeError):
            identity.parameters["nested"] = (2,)
        self.assertEqual(ArtifactIdentity("x", "y", "1", 0, {"b": 2, "a": 1}).sha256,
                         ArtifactIdentity("x", "y", "1", 0, {"a": 1, "b": 2}).sha256)
        self.assertNotEqual(ArtifactIdentity("x", "y", "1", 0, {"a": 1}).sha256,
                            ArtifactIdentity("x", "y", "1", 0, {"a": 2}).sha256)

    def test_roundtrip_and_reject_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "artifact"
            artifact = base()
            save_artifact(artifact, target)
            self.assertEqual(load_artifact(target).content_id, artifact.content_id)
            with self.assertRaises(FileExistsError):
                save_artifact(base(reference_elevation_m=np.zeros((2, 3))), target)
            self.assertEqual(load_artifact(target).content_id, artifact.content_id)

    def test_derived_water_roundtrip_and_reference_binding(self):
        source = base()
        vectors = np.zeros((3, 2, 3))
        vectors[0] = 0.25
        vectors[1] = 1
        water = SurfaceWater(np.full((2, 3), 20.0), np.ones((2, 3), bool), np.full((2, 3), 2.0))
        artifact = base(kind="derived", source_artifact_id=source.content_id,
                        displacement_type="xyz", displacement_m=vectors, water=water)
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "derived"
            save_artifact(artifact, target)
            loaded = load_artifact(target)
            self.assertEqual(loaded.content_id, artifact.content_id)
            loaded.verify_source(source)
            with self.assertRaises(ValueError):
                loaded.verify_source(base(reference_elevation_m=np.zeros((2, 3))))
            manifest_file = target / "manifest.json"
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest["reference_surface_id"] = "0" * 64
            manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_artifact(target)

    def test_bad_data_and_corruption(self):
        with self.assertRaises(ValueError):
            base(reference_elevation_m=np.array([[float("nan")]]))
        with self.assertRaises(ValueError):
            base(reference_elevation_m=np.ones((1, 3)), origin_x_m=1e308, spacing_x_m=1e308)
        with self.assertRaises(ValueError):
            base(kind="derived", source_artifact_id="x")
        with self.assertRaises(ValueError):
            base(water=SurfaceWater(np.full((2, 3), 0.), np.ones((2, 3), bool), np.zeros((2, 3))))
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "artifact"
            with self.assertRaises(FileNotFoundError):
                load_artifact(target)
            save_artifact(base(), target)
            manifest_file = target / "manifest.json"
            original = manifest_file.read_text(encoding="utf-8")
            manifest = json.loads(original)
            manifest["format_version"] = 2
            manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_artifact(target)
            manifest_file.write_text(original, encoding="utf-8")
            manifest_file.write_text(original.replace('"kind":', '"kind":"base","kind":', 1), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_artifact(target)
            manifest_file.write_text(original, encoding="utf-8")
            (target / "arrays.npz").write_bytes(b"broken")
            with self.assertRaises(Exception):
                load_artifact(target)

    def test_failed_save_leaves_no_product(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "missing" / "artifact"
            with self.assertRaises(FileNotFoundError):
                save_artifact(base(), target)
            self.assertFalse(target.exists())
            target = Path(root) / "artifact"
            with patch.object(storage.np, "savez", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    save_artifact(base(), target)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(root).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
