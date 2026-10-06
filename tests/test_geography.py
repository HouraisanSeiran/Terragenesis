import unittest
from unittest.mock import patch
import sys
import json
import importlib.util

import numpy as np

from diffusion.geography import make_geographic_map_factory
from diffusion.geographic_noise import field
from diffusion.paths import ROOT, inside


class GeographicConditioningTests(unittest.TestCase):
    def test_seed_zero_repeats_and_tiles_join_exactly(self):
        factory = make_geographic_map_factory(seed=0)
        full = factory.sample_raw(-40, -30, 35, 20)
        split = np.concatenate((factory.sample_raw(-40, -30, 0, 20),
                                factory.sample_raw(0, -30, 35, 20)), axis=2)
        np.testing.assert_array_equal(full, split)
        np.testing.assert_array_equal(full, make_geographic_map_factory(seed=0).sample_raw(-40, -30, 35, 20))
        self.assertFalse(np.array_equal(full, make_geographic_map_factory(seed=1).sample_raw(-40, -30, 35, 20)))
        np.testing.assert_array_equal(full,
            make_geographic_map_factory(seed=1 << 64).sample_raw(-40, -30, 35, 20))
        self.assertFalse(np.array_equal(full,
            make_geographic_map_factory(seed=1 << 63).sample_raw(-40, -30, 35, 20)))
        rectangular = factory.sample_raw(-13, -7, 11, 4)
        self.assertEqual(rectangular.shape, (5, 11, 24))
        np.testing.assert_array_equal(rectangular,
            np.concatenate((factory.sample_raw(-13, -7, 11, 0),
                            factory.sample_raw(-13, 0, 11, 4)), axis=1))
        with self.assertRaises(ValueError):
            make_geographic_map_factory(seed=0, frequency_mult=[2, 3, 3, 3, 3])
        with self.assertRaises(ValueError):
            make_geographic_map_factory(seed=0, drop_water_pct=.25)

    def test_coast_has_no_detail_jump(self):
        seed = 20260927
        x, z = np.meshgrid(np.linspace(-128, 128, 513), np.linspace(-128, 128, 513))
        continent = field(x, z, seed, 101, ((64, 1), (24, .42), (8, .12)))
        mountain = field(x, z, seed, 211, ((18, 1), (7, .42), (2, .12)))
        detail = field(x, z, seed, 307, ((4, 1), (1, .35)))
        shore = continent + .12 * mountain + .025 * detail + .02
        close = np.abs(shore) < .0005
        self.assertGreater(np.count_nonzero(close), 100)
        elevation = make_geographic_map_factory(seed=seed).sample_raw(-128, -128, 129, 129)[0]
        # At exact integer cells near the shoreline, relief must taper to zero.
        integer_shore = shore[::2, ::2]
        near = np.abs(integer_shore) < .002
        self.assertLess(np.max(np.abs(elevation[near])), 12)

    def test_physical_channels_and_no_global_data_reads(self):
        with patch("builtins.open", side_effect=AssertionError("external raster or stats read")):
            sample = make_geographic_map_factory(seed=20260927).sample_raw(-128, -128, 128, 128)
        self.assertEqual(sample.shape, (5, 256, 256))
        self.assertEqual(sample.dtype, np.float32)
        self.assertTrue(np.isfinite(sample).all())
        self.assertLess(np.min(sample[0]), 0)
        self.assertGreater(np.max(sample[0]), 500)
        self.assertTrue(np.all((sample[1] >= -35) & (sample[1] <= 38)))
        self.assertTrue(np.all((sample[2] >= 400) & (sample[2] <= 2500)))
        self.assertTrue(np.all((sample[3] >= 100) & (sample[3] <= 3200)))
        self.assertTrue(np.all((sample[4] >= 15) & (sample[4] <= 85)))

    def test_lapse_rate_and_model_input_transform(self):
        factory = make_geographic_map_factory(seed=43)
        raw = factory.sample_raw(-80, -80, 80, 80)
        self.assertLess(np.corrcoef(raw[0].ravel(), raw[1].ravel())[0, 1], -.15)
        finalized = factory.finalize(raw)
        self.assertIsNot(finalized, raw)
        np.testing.assert_array_equal(finalized, raw)
        try:
            import torch
        except ImportError:
            self.skipTest("torch unavailable")
        output = factory(-8, -8, 8, 8).numpy()
        original = factory.sample_raw(-8, -8, 8, 8)
        np.testing.assert_allclose(output[0], np.sign(original[0]) * np.sqrt(np.abs(original[0])))
        np.testing.assert_array_equal(output[1:], original[1:])

    def test_upstream_conditioning_hook_skips_worldclim(self):
        if importlib.util.find_spec("pyfastnoiselite") is None:
            self.skipTest("upstream optional dependencies unavailable")
        upstream = json.loads((ROOT / "runtime/upstream.json").read_text())
        sys.path.insert(0, str(inside(upstream["source"])))
        try:
            from terrain_diffusion.inference import synthetic_map
            from terrain_diffusion.inference.world_pipeline import WorldPipeline
            class GeographicPipeline(WorldPipeline):
                def _init_conditioning(self):
                    self.synthetic_map_factory = make_geographic_map_factory(seed=self.seed)

            with patch.object(synthetic_map, "_ensure_wc_files", side_effect=AssertionError("WorldClim read")), \
                 patch.object(synthetic_map, "_load_stats_cache", side_effect=AssertionError("stats read")), \
                 patch.object(synthetic_map, "_compute_map_stats", side_effect=AssertionError("stats computed")):
                pipeline = GeographicPipeline(seed=0, caching_strategy="direct")
                pipeline._init_conditioning()
                raw = pipeline._sample_raw_conditioning(-4, 5, -7, 8)
                self.assertEqual(raw.shape, (5, 9, 15))
                self.assertTrue(np.isfinite(raw).all())
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
