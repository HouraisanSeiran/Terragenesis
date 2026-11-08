import unittest

import numpy as np

from terrain_pipeline.climate_forcing import MONTH_EDGES_S, NoiseClimateParameters, sample_climate, interval_mean_rain_mm_h, grid_rainfall


class NoiseForcingTests(unittest.TestCase):
    def test_bio_channels_are_derived_from_same_monthly_physical_values(self):
        x, z = np.meshgrid(np.arange(8.) * 10000., np.arange(6.) * 10000.)
        result = sample_climate(20261011, x, z, 1000.)
        temperature, precipitation = result["monthly_temperature_c"], result["monthly_precipitation_mm"]
        expected = np.stack((temperature.mean(axis=0), temperature.std(axis=0) * 100.,
            precipitation.sum(axis=0), precipitation.std(axis=0) / precipitation.mean(axis=0) * 100.))
        np.testing.assert_array_equal(result["BIO1_4_12_15"], expected)
        self.assertTrue((precipitation > 0.).all())
        sea = sample_climate(20261011, x, z, 0.)
        np.testing.assert_allclose(result["BIO1_4_12_15"][0], sea["BIO1_4_12_15"][0] - 6.5, atol=1e-12)

    def test_native_cuts_replay_same_climate_and_rain_cells(self):
        whole_x, whole_z = np.meshgrid(np.arange(8.) * 30., np.arange(6.) * 30.)
        whole = sample_climate(20261011, whole_x, whole_z)
        cropped = sample_climate(20261011, whole_x[2:5, 3:7], whole_z[2:5, 3:7])
        np.testing.assert_array_equal(whole["BIO1_4_12_15"][:, 2:5, 3:7], cropped["BIO1_4_12_15"])
        rain, _ = grid_rainfall(20261011, origin_xz_m=[0., 0.], shape_zx=(6, 8), spacing_m=30., time_edges_s=[13., 1813.])
        cut, metadata = grid_rainfall(20261011, origin_xz_m=[90., 60.], shape_zx=(3, 4), spacing_m=30., time_edges_s=[13., 1813.])
        np.testing.assert_array_equal(rain.rain_mm_h[:, 2:5, 3:7], cut.rain_mm_h)
        self.assertEqual(metadata["spatial_mean"], "equal_area_midpoint_subcells")

    def test_absolute_time_split_conserves_depth_across_month_boundary(self):
        start, middle, end = float(MONTH_EDGES_S[1] - 713.), float(MONTH_EDGES_S[1] + 17.), float(MONTH_EDGES_S[1] + 1117.)
        full = interval_mean_rain_mm_h(20261011, [12., 315.], [14., 918.], start, end)
        first = interval_mean_rain_mm_h(20261011, [12., 315.], [14., 918.], start, middle)
        last = interval_mean_rain_mm_h(20261011, [12., 315.], [14., 918.], middle, end)
        np.testing.assert_allclose(full * (end - start), first * (middle - start) + last * (end - middle), rtol=1e-14, atol=1e-12)
        self.assertTrue((full >= 0.).all())

    def test_rainfall_contract_keeps_mm_h_and_explicit_cell_quadrature(self):
        forcing, _ = grid_rainfall(20261011, origin_xz_m=[0., 0.], shape_zx=(1, 1), spacing_m=30., time_edges_s=[0., 3600.], spatial_subsamples=2)
        expected = np.mean([interval_mean_rain_mm_h(20261011, x, z, 0., 3600.) for x in (-7.5, 7.5) for z in (-7.5, 7.5)])
        self.assertAlmostEqual(forcing.rain_mm_h[0, 0, 0], expected)
        self.assertAlmostEqual(forcing.rainfall_depth_mm[0, 0, 0], expected)

    def test_determinism_seed_variation_and_validation(self):
        first = sample_climate(20261011, 12., 14.)["BIO1_4_12_15"]
        np.testing.assert_array_equal(first, sample_climate(20261011, 12., 14.)["BIO1_4_12_15"])
        self.assertFalse(np.array_equal(first, sample_climate(20261012, 12., 14.)["BIO1_4_12_15"]))
        with self.assertRaises(ValueError):
            NoiseClimateParameters(lapse_rate_c_per_m=1.)
        with self.assertRaises(ValueError):
            interval_mean_rain_mm_h(20261011, 0., 0., 10., 0.)


if __name__ == "__main__":
    unittest.main()
