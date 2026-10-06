import unittest

import numpy as np

from diffusion.config import GenerationConfig
from diffusion.geography_v2 import make_geographic_map_factory


class GeographicV2Tests(unittest.TestCase):
    def test_profile_and_tile_order(self):
        config = GenerationConfig.for_profile("geographic_v2")
        self.assertEqual(config.meters_per_height_block, 6)
        self.assertEqual(config.cond_snr[0], 0.65)
        factory = make_geographic_map_factory(seed=20260927)
        full = factory.sample_raw(-8, -8, 8, 8)
        split = np.concatenate((factory.sample_raw(-8, -8, 0, 8),
                                factory.sample_raw(0, -8, 8, 8)), axis=2)
        np.testing.assert_array_equal(full, split)
        self.assertTrue(np.isfinite(full).all())
        self.assertFalse(np.array_equal(full, make_geographic_map_factory(seed=43).sample_raw(-8, -8, 8, 8)))

    def test_old_profile_defaults_preserved(self):
        config = GenerationConfig()
        self.assertEqual(config.conditioning_mode, "geographic_v1")
        self.assertEqual(config.meters_per_height_block, 30)
        self.assertEqual(config.cond_snr[0], 0.3)
        with self.assertRaises(ValueError):
            GenerationConfig.for_profile("geographic_v2", cond_snr=(float("nan"), 0.1, 1, 0.1, 1))


if __name__ == "__main__":
    unittest.main()
