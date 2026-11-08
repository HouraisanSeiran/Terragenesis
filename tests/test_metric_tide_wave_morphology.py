import unittest
import numpy as np
from terrain_pipeline.surface_rivers.metric_tide_wave_morphology import (
    TideWaveConfig, apply_tide_wave_morphology)


class TideWaveMorphologyTests(unittest.TestCase):
    def test_bounded_conservative_marine_stage(self):
        h = np.zeros((20, 30), float)
        marine = np.zeros_like(h, bool); marine[:, 15:] = True
        channels = np.zeros_like(h, bool); channels[8:12, 14] = True
        result = apply_tide_wave_morphology(h, marine, channels, spacing_m=20.,
                                            config=TideWaveConfig(max_change_m=.2))
        d = result["height_delta_m"]
        self.assertAlmostEqual(float(d.sum()), 0., places=10)
        self.assertTrue(np.all(d[~marine] == 0.))
        self.assertTrue(np.all(d[channels] == 0.))
        self.assertLessEqual(float(np.max(np.abs(d))), .2)
        self.assertGreater(float(np.count_nonzero(d)), 0.)

    def test_zero_tide_and_wave_is_a_no_change_control(self):
        h = np.linspace(-2., 1., 64 * 64).reshape(64, 64)
        marine = np.ones_like(h, bool)
        channels = np.zeros_like(h, bool)
        mouth = np.zeros_like(h, bool)
        mouth[:, :2] = True
        result = apply_tide_wave_morphology(
            h, marine, channels, spacing_m=20., mouth_mask=mouth,
            config=TideWaveConfig(tide_range_m=0., wave_height_m=0.))
        self.assertTrue(np.array_equal(result["height_m"], h))
        self.assertTrue(np.array_equal(result["height_delta_m"], np.zeros_like(h)))
        self.assertEqual(result["net_volume_m3"], 0.)

    def test_800_by_800_mouth_distance_is_memory_bounded_and_repeatable(self):
        h = np.zeros((800, 800), float)
        marine = np.ones_like(h, bool)
        channels = np.zeros_like(h, bool)
        mouth = np.zeros_like(h, bool)
        mouth[:, :3] = True
        config = TideWaveConfig(max_change_m=.2, active_width_m=1200.)
        first = apply_tide_wave_morphology(
            h, marine, channels, spacing_m=20., mouth_mask=mouth, config=config)
        second = apply_tide_wave_morphology(
            h, marine, channels, spacing_m=20., mouth_mask=mouth, config=config)
        self.assertEqual(first["height_delta_m"].shape, (800, 800))
        self.assertTrue(np.isfinite(first["height_delta_m"]).all())
        self.assertTrue(np.array_equal(first["height_delta_m"], second["height_delta_m"]))
        self.assertAlmostEqual(float(first["height_delta_m"].sum()), 0., places=8)

    def test_rejects_marine_channel_overlap(self):
        with self.assertRaises(ValueError):
            apply_tide_wave_morphology(np.zeros((3, 3)), np.ones((3, 3), bool),
                                       np.ones((3, 3), bool), spacing_m=1.)


if __name__ == "__main__":
    unittest.main()
