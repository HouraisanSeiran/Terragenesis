from dataclasses import FrozenInstanceError, replace
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
import tempfile

import numpy as np

from diffusion.config import GenerationConfig
from diffusion.geography_physical import make_physical_map_factory, sample_physical
from diffusion.physical_config import PhysicalGenerationConfig
from diffusion.physical_backend import PhysicalTerrainDiffusionBackend
from tools.verify_physical_generation import prepare_cpu_artifacts, verify


class PhysicalGenerationTests(unittest.TestCase):
    def test_cpu_publication_exclusive_and_failure_atomic(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "run"
            prepare_cpu_artifacts(destination, PhysicalGenerationConfig(), 20261001)
            before = (destination / "cpu-report.json").read_bytes()
            with self.assertRaises(FileExistsError):
                prepare_cpu_artifacts(destination, PhysicalGenerationConfig(), 42)
            self.assertEqual(before, (destination / "cpu-report.json").read_bytes())
            failed = Path(temporary) / "failed"
            with patch("tools.verify_physical_generation.write_review", side_effect=RuntimeError("failure")):
                with self.assertRaises(RuntimeError):
                    prepare_cpu_artifacts(failed, PhysicalGenerationConfig(), 20261001)
            self.assertFalse(failed.exists())
            self.assertEqual(list(Path(temporary).iterdir()), [destination])

    def test_backend_rejects_invalid_model_output_without_inference(self):
        import torch

        config = PhysicalGenerationConfig()
        backend = PhysicalTerrainDiffusionBackend(config)
        for elevation, climate in ((torch.zeros((2, 3)), torch.zeros((5, 2, 2))),
                                   (torch.zeros((2, 2)), torch.zeros((4, 2, 2))),
                                   (torch.full((2, 2), float("nan")), torch.zeros((5, 2, 2)))):
            backend.pipeline = SimpleNamespace(
                change_seed=lambda seed: None,
                get=lambda *args, **kwargs: {"elev": elevation, "climate": climate})
            with patch.object(backend, "load"):
                with self.assertRaises(RuntimeError):
                    backend.generate(42, 0, 0, 2)

    def test_backend_generation_metadata_without_inference(self):
        import torch

        backend = PhysicalTerrainDiffusionBackend(PhysicalGenerationConfig())
        backend.pipeline = SimpleNamespace(change_seed=lambda seed: None,
            get=lambda *args, **kwargs: {"elev": torch.zeros((2, 2)),
                                        "climate": torch.zeros((5, 2, 2))})
        with patch.object(backend, "load"):
            elevation, climate, metadata = backend.generate(-1, -4, 8, 2)
        self.assertEqual(metadata["native_origin"], [-4, 8])
        self.assertEqual(metadata["seed"], str(2 ** 64 - 1))
        self.assertEqual(elevation.shape, (2, 2))
        self.assertEqual(climate.shape, (5, 2, 2))
        self.assertIn("model", metadata)
        self.assertIn("upstream", metadata)

    def test_cpu_gates_support_real_world_scale_not_game_ceiling(self):
        report, conditioning = verify(PhysicalGenerationConfig(), 20261001)
        self.assertTrue(all(report["gates"].values()))
        self.assertFalse(report["td_inference_run"])
        self.assertEqual(report["artifact_kind"], "conditioning_only")
        self.assertGreater(conditioning[0].max(), 1024)
        self.assertLess(conditioning[0].min(), 0)

    def test_world_coordinate_continuity_and_grid_units(self):
        config = PhysicalGenerationConfig()
        factory = make_physical_map_factory(42, config)
        east = np.arange(-8, 9)[None, :] * config.conditioning_spacing_m
        south = np.arange(-7, 10)[:, None] * config.conditioning_spacing_m
        np.testing.assert_array_equal(factory.sample_raw(-8, -7, 9, 10),
                                      sample_physical(east, south, 42, config))
        full = factory.sample_raw(-8, -7, 9, 10)
        reverse = np.concatenate((factory.sample_raw(-8, 0, 9, 10),
                                  factory.sample_raw(-8, -7, 9, 0)), axis=1)
        np.testing.assert_array_equal(full, np.concatenate((reverse[:, 10:], reverse[:, :10]), axis=1))
        points = sample_physical(np.array([123456., 123456. + .001]), 654321., 42)
        self.assertLess(np.max(np.abs(points[:, 0] - points[:, 1])), .01)

    def test_no_elevation_cap_or_soft_knee(self):
        config = PhysicalGenerationConfig()
        scaled = replace(config, continental_uplift_m=36000, ocean_depth_m=22000,
                         ridge_relief_m=24000, massif_relief_m=10500, detail_relief_m=900)
        raw = make_physical_map_factory(42, config).sample_raw(-64, -64, 64, 64)[0]
        tall = make_physical_map_factory(42, scaled).sample_raw(-64, -64, 64, 64)[0]
        np.testing.assert_allclose(tall, raw * 10, rtol=2e-7, atol=.001)
        self.assertGreater(tall.max(), 10240)

    def test_identity_frozen_roundtrip_and_config_changes(self):
        config = PhysicalGenerationConfig()
        with self.assertRaises(FrozenInstanceError):
            config.ocean_depth_m = 40
        self.assertEqual(config.identity()[0], PhysicalGenerationConfig.from_record(
            json.loads(json.dumps(config.record()))).identity()[0])
        self.assertNotEqual(config.identity()[0], replace(config, ridge_relief_m=3000).identity()[0])
        self.assertNotEqual(config.identity()[0], replace(config, cond_snr=(.1, .1, 1., .1, 1.)).identity()[0])

    def test_invalid_data_rejected(self):
        for value in (0, -1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                PhysicalGenerationConfig(geographic_scale_m=value)
        with self.assertRaises(ValueError):
            PhysicalGenerationConfig(cond_snr=[.1] * 5)
        with self.assertRaises(ValueError):
            PhysicalGenerationConfig(sea_datum_m=64)
        with self.assertRaises(ValueError):
            PhysicalGenerationConfig(sea_datum_m=False)
        for config in (False, {}, object()):
            with self.assertRaises(ValueError):
                make_physical_map_factory(1, config)
            with self.assertRaises(ValueError):
                sample_physical(0, 0, 1, config)
        with self.assertRaises(ValueError):
            make_physical_map_factory(1).sample_raw(0, 0, 100000000, 100000000)
        with self.assertRaises(ValueError):
            make_physical_map_factory(1).sample_raw(0, 0, 100000000, 0)
        with self.assertRaises(ValueError):
            sample_physical(np.zeros((1025, 1)), np.zeros((1, 1025)), 1)
        for bounds in ((0, 0, -1, 2), (0., 0, 2, 2)):
            with self.assertRaises(ValueError):
                make_physical_map_factory(1).sample_raw(*bounds)
        with self.assertRaises(ValueError):
            sample_physical(float("nan"), 0, 1)

    def test_legacy_identity_and_defaults_unchanged(self):
        legacy = GenerationConfig()
        self.assertEqual(legacy.sea_level, 72)
        self.assertEqual(legacy.meters_per_height_block, 30)
        self.assertEqual(legacy.conditioning_mode, "geographic_v1")
        self.assertEqual(GenerationConfig.for_profile("geographic_v4", v4_land_base_factor=.04,
            v4_mountain_relief_factor=.18, v4_ocean_depth_m=40.).identity()[0],
            "eb6f5b8a4c1cd8b43785827e5ac0381c1835e2b85fa073f8195b3029d5c304a2")


if __name__ == "__main__":
    unittest.main()
