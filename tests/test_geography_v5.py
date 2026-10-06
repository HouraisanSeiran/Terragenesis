import unittest

import numpy as np

from diffusion.config import GenerationConfig
from diffusion.geography_v5 import compress_positive_base, make_geographic_map_factory


class GeographicV5Tests(unittest.TestCase):
    def test_old_v4_identity_is_unchanged(self):
        self.assertEqual(GenerationConfig.for_profile("geographic_v4",
                         v4_land_base_factor=.04, v4_mountain_relief_factor=.18,
                         v4_ocean_depth_m=40.0).identity()[0],
                         "eb6f5b8a4c1cd8b43785827e5ac0381c1835e2b85fa073f8195b3029d5c304a2")
        self.assertNotIn("v5_base_knee_m", GenerationConfig.for_profile("geographic_v4").record())

    def test_soft_knee_preserves_low_base_and_saturates_high_base(self):
        base = np.array([0, 60, 120, 120.0001, 200, 1000000], dtype=np.float64)
        output = compress_positive_base(base, 120, 80)
        np.testing.assert_array_equal(output[:3], base[:3])
        self.assertGreater(output[3], 120)
        self.assertLess(output[3] - 120, .0001)
        self.assertLessEqual(output.max(), 200)
        self.assertAlmostEqual(float(output[-1]), 200)

    def test_v5_factory_is_tiled_and_climate_tracks_new_elevation(self):
        factory = make_geographic_map_factory(seed=20260931, base_headroom_m=40)
        full = factory.sample_raw(-80, -80, 80, 80)
        split = np.concatenate((factory.sample_raw(-20, -10, 0, 10),
                                factory.sample_raw(0, -10, 30, 10)), axis=2)
        np.testing.assert_array_equal(factory.sample_raw(-20, -10, 30, 10), split)
        components = factory.sample_components(-80, -80, 80, 80)
        np.testing.assert_allclose(full[0], components["condition_elevation_m"], atol=1e-4)
        self.assertTrue(np.isfinite(full).all())
        self.assertGreaterEqual(float(components["ocean_m"].min()), -40)
        less_compressed = make_geographic_map_factory(seed=20260931, base_headroom_m=120)
        other = less_compressed.sample_raw(-80, -80, 80, 80)
        active = ((full[0] > 0) & (other[0] > 0) & (full[1] > -34) &
                  (full[1] < 37) & (other[1] > -34) & (other[1] < 37) &
                  (np.abs(full[0] - other[0]) > 1))
        self.assertGreater(np.count_nonzero(active), 10)
        np.testing.assert_allclose(other[1][active] - full[1][active],
                                   -.0065 * (other[0][active] - full[0][active]), atol=1e-4)
        np.testing.assert_array_equal(full[2], other[2])
        np.testing.assert_array_equal(full[4], other[4])

    def test_parameters_enter_identity_and_old_modes_reject_them(self):
        a = GenerationConfig.for_profile("geographic_v5", v5_base_headroom_m=40)
        b = GenerationConfig.for_profile("geographic_v5", v5_base_headroom_m=120)
        self.assertNotEqual(a.identity()[0], b.identity()[0])
        self.assertEqual(a.cond_snr[0], .1)
        for value in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                GenerationConfig.for_profile("geographic_v5", v5_base_headroom_m=value)
            with self.assertRaises(ValueError):
                make_geographic_map_factory(seed=1, base_headroom_m=value)
            with self.assertRaises(ValueError):
                compress_positive_base(np.array([100]), 120, value)
        with self.assertRaises(ValueError):
            GenerationConfig.for_profile("geographic_v4", v5_base_knee_m=120)


if __name__ == "__main__":
    unittest.main()
