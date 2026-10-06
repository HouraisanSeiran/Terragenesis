"""Behavior tests for explicit legacy import and read-only pair loading."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from terrain_pipeline.legacy_region import load_legacy_region, prepare_legacy_region
from terrain_pipeline.artifacts import ArtifactIdentity, TerrainArtifact, save_artifact


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "verification/tuned-model/plains-geographic_v2-seed20260927-x2176-z8832.npz"
PROCESSED = ROOT / "verification/region-processing/plains-geographic_v2-seed20260927-x2176-z8832-derived.npz"


def altered_archive(source: Path, target: Path, **changes) -> Path:
    with np.load(source, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays.update(changes)
    np.savez(target, **arrays)
    return target


class LegacyRegionTests(unittest.TestCase):
    def test_real_pair_preserves_reference_and_reconstructs_processed(self):
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "pair"
            prepared = prepare_legacy_region(SOURCE, PROCESSED, destination)
            loaded = load_legacy_region(destination)
            with np.load(SOURCE, allow_pickle=False) as source, np.load(PROCESSED, allow_pickle=False) as processed:
                np.testing.assert_array_equal(loaded.base.reference_elevation_m, source["elevation"][25:-25, 25:-25])
                expected = (processed["processed_height"].astype(np.float64) - 62) * 6
                np.testing.assert_allclose(loaded.reconstructed_elevation_m(), expected, atol=1e-12)
            self.assertEqual(loaded.base.origin_x_m, 66030)
            self.assertEqual(loaded.base.origin_z_m, 265710)
            self.assertEqual(loaded.base.spacing_x_m, 30)
            self.assertEqual(loaded.derived.source_artifact_id, loaded.base.content_id)
            self.assertEqual(loaded.derived.content_id, prepared.derived.content_id)
            self.assertIsNone(loaded.base.water)
            self.assertIsNone(loaded.derived.water)
            with self.assertRaises(FileExistsError):
                prepare_legacy_region(SOURCE, PROCESSED, destination)
            self.assertEqual(load_legacy_region(destination).derived.content_id, loaded.derived.content_id)

    def test_rejects_wrong_pair_and_mapping(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            with np.load(PROCESSED, allow_pickle=False) as archive:
                wrong = archive["raw_height"].copy()
            wrong[0, 0] += 1
            mismatched = altered_archive(PROCESSED, directory / "mismatched.npz", raw_height=wrong)
            with self.assertRaisesRegex(ValueError, "processed input"):
                prepare_legacy_region(SOURCE, mismatched, directory / "pair")
            self.assertFalse((directory / "pair").exists())
            with np.load(SOURCE, allow_pickle=False) as archive:
                mapping = json.loads(str(archive["world_mapping"]))
            mapping["world_sea_level"] = 63
            wrong_mapping = altered_archive(SOURCE, directory / "mapping.npz",
                                            world_mapping=json.dumps(mapping))
            with self.assertRaisesRegex(ValueError, "sea level"):
                prepare_legacy_region(wrong_mapping, PROCESSED, directory / "pair")

    def test_rejects_nonfinite_and_unknown_recipe(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            with np.load(SOURCE, allow_pickle=False) as archive:
                elevation = archive["elevation"].copy()
            elevation[100, 100] = np.nan
            invalid = altered_archive(SOURCE, directory / "nan.npz", elevation=elevation)
            with self.assertRaisesRegex(ValueError, "non-finite"):
                prepare_legacy_region(invalid, PROCESSED, directory / "pair")
            recipe = altered_archive(PROCESSED, directory / "recipe.npz", algorithm_id="unknown_v1")
            with self.assertRaisesRegex(ValueError, "recipe"):
                prepare_legacy_region(SOURCE, recipe, directory / "pair")

    def test_read_only_rejects_missing_corrupt_and_replaced_source(self):
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "pair"
            with self.assertRaises(FileNotFoundError):
                load_legacy_region(destination)
            prepare_legacy_region(SOURCE, PROCESSED, destination)
            source_manifest = destination / "base" / "manifest.json"
            original = source_manifest.read_bytes()
            source_manifest.write_bytes(b"broken")
            with self.assertRaises(Exception):
                load_legacy_region(destination)
            source_manifest.write_bytes(original)
            pair_manifest = destination / "manifest.json"
            manifest = json.loads(pair_manifest.read_text(encoding="utf-8"))
            manifest["base_content_id"] = "0" * 64
            pair_manifest.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "identity"):
                load_legacy_region(destination)

    def test_valid_replacement_base_fails_source_binding(self):
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "pair"
            prepare_legacy_region(SOURCE, PROCESSED, destination)
            loaded = load_legacy_region(destination)
            replacement = TerrainArtifact(
                kind="base", identity=ArtifactIdentity("fixture", "height", "1", 1, {}),
                reference_elevation_m=loaded.base.reference_elevation_m,
                origin_x_m=loaded.base.origin_x_m, origin_z_m=loaded.base.origin_z_m,
                spacing_x_m=loaded.base.spacing_x_m, spacing_z_m=loaded.base.spacing_z_m,
                vertical_datum=loaded.base.vertical_datum,
                sea_level_elevation_m=loaded.base.sea_level_elevation_m)
            old_base = destination / "base"
            renamed = destination / "old-base"
            old_base.rename(renamed)
            save_artifact(replacement, old_base)
            manifest_file = destination / "manifest.json"
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest["base_content_id"] = replacement.content_id
            manifest["source_sha256"] = replacement.identity.record()["parameters"].get("source_sha256", "")
            manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
            renamed.rename(Path(root) / "old-base")
            with self.assertRaisesRegex(ValueError, "source content identity"):
                load_legacy_region(destination)

    def test_consumer_does_not_access_legacy_sources(self):
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "pair"
            temporary_source = Path(root) / "source.npz"
            temporary_processed = Path(root) / "processed.npz"
            temporary_source.write_bytes(SOURCE.read_bytes())
            temporary_processed.write_bytes(PROCESSED.read_bytes())
            prepare_legacy_region(temporary_source, temporary_processed, destination)
            temporary_source.unlink()
            temporary_processed.unlink()
            with patch("terrain_pipeline.legacy_region._validate_source", side_effect=AssertionError("raw source accessed")), \
                 patch("terrain_pipeline.legacy_region.prepare_legacy_region", side_effect=AssertionError("generation attempted")):
                loaded = load_legacy_region(destination)
            self.assertEqual(loaded.shape, (463, 463))

    def test_mid_save_failure_leaves_no_published_pair(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            from terrain_pipeline import legacy_region
            real_save = legacy_region.save_artifact
            calls = 0

            def fail_second(artifact, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("write failure")
                return real_save(artifact, destination)

            with patch("terrain_pipeline.legacy_region.save_artifact", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "write failure"):
                    prepare_legacy_region(SOURCE, PROCESSED, directory / "pair")
            self.assertEqual(list(directory.iterdir()), [])

    def test_rejects_fractional_metadata_and_duplicate_json(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            with np.load(SOURCE, allow_pickle=False) as archive:
                metadata = json.loads(str(archive["metadata"]))
            metadata["seed"] = 3.5
            bad_seed = altered_archive(SOURCE, directory / "seed.npz", metadata=json.dumps(metadata))
            with self.assertRaisesRegex(ValueError, "seed"):
                prepare_legacy_region(bad_seed, PROCESSED, directory / "pair")
            fractional_spacing = altered_archive(PROCESSED, directory / "spacing.npz", spacing_blocks=np.float32(2.5))
            with self.assertRaisesRegex(ValueError, "spacing"):
                prepare_legacy_region(SOURCE, fractional_spacing, directory / "pair")
            duplicate = altered_archive(SOURCE, directory / "duplicate.npz", metadata='{"seed":1,"seed":2}')
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                prepare_legacy_region(duplicate, PROCESSED, directory / "pair")

    def test_rejects_bad_shape_origin_and_duplicate_npz_member(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            bad_shape = altered_archive(PROCESSED, directory / "shape.npz",
                                        processed_height=np.zeros((462, 463), dtype=np.float32))
            with self.assertRaisesRegex(ValueError, "463x463"):
                prepare_legacy_region(SOURCE, bad_shape, directory / "pair")
            bad_origin = altered_archive(PROCESSED, directory / "origin.npz",
                                         origin_world=np.array([4404, 17714], dtype=np.int32))
            with self.assertRaisesRegex(ValueError, "origin"):
                prepare_legacy_region(SOURCE, bad_origin, directory / "pair")
            duplicate = directory / "duplicate.npz"
            duplicate.write_bytes(PROCESSED.read_bytes())
            with zipfile.ZipFile(duplicate, "a") as archive:
                archive.writestr("raw_height.npy", b"duplicate")
            with self.assertRaisesRegex(ValueError, "fields"):
                prepare_legacy_region(SOURCE, duplicate, directory / "pair")


if __name__ == "__main__":
    unittest.main()
