import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import hashlib
import json

import numpy as np

from terrain_pipeline.artifacts import ArtifactIdentity, SurfaceWater, TerrainArtifact
from terrain_pipeline.artifacts.contracts import canonical_json
from terrain_pipeline.metric_region import METRIC_30M_RECIPE_V1, RegionRecipe, process_region, rebase_base_surface
from terrain_pipeline.metric_region_storage import load_metric_region, prepare_metric_region


def base(height, *, sea=126, spacing_x=1, spacing_z=1):
    return TerrainArtifact(
        kind="base", identity=ArtifactIdentity("test", "synthetic", "1", 7, {}),
        reference_elevation_m=height, origin_x_m=0, origin_z_m=0,
        spacing_x_m=spacing_x, spacing_z_m=spacing_z,
        vertical_datum="core bottom = 0 m", sea_level_elevation_m=sea)


class MetricRegionTests(unittest.TestCase):
    def setUp(self):
        z, x = np.mgrid[:81, :83]
        self.height = 126 + 240 + 24 * np.sin(x / 8) + 13 * np.cos(z / 9) + x / 8

    def test_determinism_weights_and_immutability(self):
        source = self.height.copy()
        first = process_region(source, 126, 1, 1)
        second = process_region(source, 126, 1, 1)
        np.testing.assert_array_equal(source, self.height)
        np.testing.assert_array_equal(first.elevation_m, second.elevation_m)
        np.testing.assert_allclose(first.weights.sum(axis=-1), 1)
        np.testing.assert_array_equal(first.dominant_type, np.argmax(first.weights, axis=-1))

    def test_30m_default_uses_frozen_recipe(self):
        z, x = np.mgrid[:40, :40]
        source = base(126 + x + z, spacing_x=30, spacing_z=30)
        with tempfile.TemporaryDirectory() as directory:
            published = prepare_metric_region(source, Path(directory) / "region")
        self.assertEqual(published.derived.identity.record()["parameters"]["recipe"],
                         METRIC_30M_RECIPE_V1.record())

    def test_external_and_sea_protection(self):
        mask = np.ones_like(self.height)
        result = process_region(self.height, 126, 1, 1, mask)
        np.testing.assert_array_equal(result.elevation_m, self.height)
        submerged = np.full_like(self.height, 125.0)
        np.testing.assert_array_equal(process_region(submerged, 126, 1, 1).elevation_m, submerged)

    def test_rebase_preserves_relative_processing_and_reference(self):
        source = base(self.height)
        for new_sea in (0, 226):
            shifted = rebase_base_surface(source, new_sea)
            self.assertEqual(shifted.sea_level_elevation_m, new_sea)
            np.testing.assert_allclose(shifted.reference_elevation_m - new_sea,
                                       source.reference_elevation_m - 126)
            original_result = process_region(source.reference_elevation_m, 126, 1, 1)
            shifted_result = process_region(shifted.reference_elevation_m, new_sea, 1, 1)
            np.testing.assert_allclose(shifted_result.elevation_m - new_sea,
                                       original_result.elevation_m - 126, atol=1e-10)
            np.testing.assert_allclose(shifted_result.weights, original_result.weights, atol=1e-12)

    def test_anisotropic_spacing_and_halo_seam(self):
        recipe = RegionRecipe()
        source = self.height
        whole = process_region(source, 126, 2, 3, recipe=recipe)
        hx, hz = recipe.required_halo_samples(2, 3)
        split = 43
        left = process_region(source[:, :split + hx], 126, 2, 3, recipe=recipe)
        right = process_region(source[:, split - hx:], 126, 2, 3, recipe=recipe)
        np.testing.assert_allclose(left.elevation_m[hz:-hz, hx:split],
                                   whole.elevation_m[hz:-hz, hx:split], atol=1e-10)
        np.testing.assert_allclose(right.elevation_m[hz:-hz, hx:-hx],
                                   whole.elevation_m[hz:-hz, split:-hx], atol=1e-10)

    def test_publish_reload_and_reject_failed_input(self):
        source = base(self.height)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "region"
            published = prepare_metric_region(source, destination)
            loaded = load_metric_region(destination)
            self.assertEqual(published.derived.content_id, loaded.derived.content_id)
            loaded.derived.verify_source(loaded.base)
            np.testing.assert_array_equal(published.weights, loaded.weights)
            with self.assertRaises(FileExistsError):
                prepare_metric_region(source, destination)
            bad = Path(directory) / "bad"
            with self.assertRaises(ValueError):
                prepare_metric_region(source, bad, halo_samples=(1, 1))
            self.assertFalse(bad.exists())
            (destination / "landforms.npz").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                load_metric_region(destination)

    def test_rejects_invalid_protection_and_water(self):
        bad = np.zeros_like(self.height)
        bad[1, 1] = np.nan
        with self.assertRaises(ValueError):
            process_region(self.height, 126, 1, 1, bad)
        source = base(self.height)
        water = SurfaceWater(surface_elevation_m=self.height, wet_mask=np.zeros_like(self.height, dtype=bool),
                             discharge_m3_per_s=np.zeros_like(self.height))
        wet_base = TerrainArtifact(kind="base", identity=source.identity,
                                   reference_elevation_m=source.reference_elevation_m,
                                   origin_x_m=0, origin_z_m=0, spacing_x_m=1, spacing_z_m=1,
                                   vertical_datum=source.vertical_datum, sea_level_elevation_m=126,
                                   water=water)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                prepare_metric_region(wet_base, Path(directory) / "wet")

    def test_protection_identity_and_read_only_load(self):
        source = base(self.height)
        with tempfile.TemporaryDirectory() as directory:
            a = prepare_metric_region(source, Path(directory) / "a", np.zeros_like(self.height))
            mask = np.zeros_like(self.height)
            mask[40, 40] = 1
            b = prepare_metric_region(source, Path(directory) / "b", mask)
            self.assertNotEqual(a.derived.identity.sha256, b.derived.identity.sha256)
            with patch("terrain_pipeline.metric_region_storage.process_region", side_effect=AssertionError("computed during load")):
                loaded = load_metric_region(Path(directory) / "a")
            self.assertEqual(a.derived.content_id, loaded.derived.content_id)

    def test_invalid_recipe_and_nonfinite_output_rejected(self):
        with self.assertRaises(ValueError):
            RegionRecipe(plain_strength=True)
        with self.assertRaises(ValueError):
            RegionRecipe(trend_sigma_m=float("nan"))
        RegionRecipe(plain_strength=0)
        huge = np.full((5, 5), 1e308)
        huge[2, 2] = -1e308
        with self.assertRaises(ValueError):
            process_region(huge, 0, 1, 1)

    def test_physical_slope_and_nontrivial_peak_protection(self):
        z, x = np.mgrid[:101, :101]
        broad = 126 + 200 + x * 0.4 + z * 0.1
        slope_only = RegionRecipe(relief_low_m=1000, relief_high_m=2000,
                                  prominence_low_m=1000, prominence_high_m=2000)
        grid_one = process_region(broad, 126, 1, 1, recipe=slope_only)
        grid_two = process_region(126 + 175 + x * 0.8 + z * 0.2, 126, 2, 2,
                                  recipe=slope_only)
        # The physical slope is the same, so the centre's rugged weight agrees.
        self.assertAlmostEqual(float(grid_one.weights[50, 50, 1]),
                               float(grid_two.weights[50, 50, 1]), places=8)
        peak = np.full((101, 101), 126 + 180.0)
        peak[50, 50] += 40
        output = process_region(peak, 126, 1, 1)
        self.assertEqual(output.elevation_m[50, 50], peak[50, 50])

    def test_coast_protection_near_waterline(self):
        z, x = np.mgrid[:101, :101]
        coast = np.where(x < 50, 125.0, 127.0 + (x - 50) * 0.3 + 2 * np.sin(z / 5))
        result = process_region(coast, 126, 1, 1)
        np.testing.assert_array_equal(result.elevation_m[:, :50], coast[:, :50])
        # A submerged edge lowers processing strength on nearby dry cells.
        high = coast + 100
        protected = process_region(coast, 126, 1, 1)
        unprotected = process_region(high, 126, 1, 1)
        self.assertGreaterEqual(np.mean(np.abs(unprotected.elevation_m[:, 51:53] - high[:, 51:53])),
                                np.mean(np.abs(protected.elevation_m[:, 51:53] - coast[:, 51:53])))

    def test_second_artifact_failure_leaves_no_package(self):
        source = base(self.height)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "failed"
            with patch("terrain_pipeline.metric_region_storage.save_artifact", side_effect=[None, ValueError("failed second save")]):
                with self.assertRaisesRegex(ValueError, "failed second save"):
                    prepare_metric_region(source, destination)
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_landform_payload_cannot_be_rebound_by_manifest(self):
        source = base(self.height)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "region"
            prepare_metric_region(source, destination)
            payload = destination / "landforms.npz"
            with np.load(payload, allow_pickle=False) as archive:
                weights = archive["weights"].copy()
                labels = archive["dominant_type"].copy()
            weights[..., 0] = 1
            weights[..., 1:] = 0
            labels[:] = 0
            np.savez(payload, weights=weights, dominant_type=labels)
            manifest = destination / "manifest.json"
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            metadata["landforms_sha256"] = hashlib.sha256(payload.read_bytes()).hexdigest()
            manifest.write_text(canonical_json(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "landform payload differs"):
                load_metric_region(destination)


if __name__ == "__main__":
    unittest.main()
