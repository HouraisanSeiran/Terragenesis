import json
from pathlib import Path
import unittest

import numpy as np

from diffusion.config import GenerationConfig
from diffusion.geography_v2 import make_geographic_map_factory as v2_factory
from diffusion.geography_v3 import make_geographic_map_factory as v3_factory


ROOT = Path(__file__).resolve().parents[1]


class GeographicV3Tests(unittest.TestCase):
    def test_v3_condition_is_seeded_and_tile_order_independent(self):
        factory = v3_factory(seed=20260928)
        full = factory.sample_raw(380, 15480, 400, 15500)
        split = np.concatenate((factory.sample_raw(380, 15480, 390, 15500),
                                factory.sample_raw(390, 15480, 400, 15500)), axis=2)
        np.testing.assert_array_equal(full, split)
        self.assertTrue(np.isfinite(full).all())
        self.assertFalse(np.array_equal(full, v3_factory(seed=9).sample_raw(380, 15480, 400, 15500)))
        prior = v2_factory(seed=20260928).sample_raw(380, 15480, 400, 15500)
        self.assertLess(full[0].max(), prior[0].max())

    def test_v2_identity_is_unchanged(self):
        path = ROOT / "verification/tuned-model/plateau-geographic_v2-seed20260927-x-16000-z-13952.npz"
        with np.load(path, allow_pickle=False) as archive:
            original = json.loads(str(archive["metadata"].item()))["identity"]
        self.assertEqual(GenerationConfig.for_profile("geographic_v2").identity()[0], original)
        self.assertNotEqual(GenerationConfig.for_profile("geographic_v3").identity()[0], original)

    def test_climate_uses_reduced_elevation(self):
        v2 = v2_factory(seed=20260928).sample_raw(384, 15488, 400, 15504)
        v3 = v3_factory(seed=20260928).sample_raw(384, 15488, 400, 15504)
        above_sea = (v2[0] > 0) & (v3[0] > 0)
        self.assertTrue(above_sea.any())
        self.assertTrue(np.all(v3[0][above_sea] < v2[0][above_sea]))
        self.assertTrue(np.all(v3[1][above_sea] >= v2[1][above_sea]))
        self.assertTrue(np.array_equal(v3[2], v2[2]))
        self.assertTrue(np.array_equal(v3[4], v2[4]))


if __name__ == "__main__":
    unittest.main()
