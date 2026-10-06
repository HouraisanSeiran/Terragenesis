import copy
from dataclasses import asdict
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity
from terrain_pipeline.mountain_storm_forcing import StormParameters, interval_mean_mm_h
from tools.audit_td_native_storm import adaptive_mean, audit_fields, independent_mean, numerical_identity


class IndependentNativeStormTests(unittest.TestCase):
    def fixture(self):
        parameters = StormParameters(-100., 80., .01, -.002, 30., 12., 500., 9500.)
        source = dict(height_m=np.zeros((5, 7)), valid_mask=np.ones((5, 7), bool),
                      protected_mask=np.zeros((5, 7), bool))
        source["valid_mask"][2, 3] = False
        source["protected_mask"][1, 2] = True
        grid = dict(spacing_m=20., origin_m_xz=[-140., 20.])
        plan = dict(schema="td-native-moving-storm-v1", window=[1, 5, 1, 7],
            steps=4, dt_s=3000., start_s=0., spatial_subsamples=2,
            parameters=asdict(parameters), source_shape=[5, 7], **grid)
        rain = np.zeros((4, 4, 6))
        columns, rows = np.arange(1, 7)[None, :], np.arange(1, 5)[:, None]
        for step in range(4):
            for delta_z in (-.25, .25):
                for delta_x in (-.25, .25):
                    rain[step] += interval_mean_mm_h(-140. + (columns + delta_x) * 20.,
                        20. + (rows + delta_z) * 20., step * 3000., (step + 1) * 3000., parameters) / 4
        valid = source["valid_mask"][1:5, 1:7]
        rain[:, ~valid] = 0.
        arrays = dict(rain_mm_h=rain, valid_mask=valid.copy(), protected_mask=source["protected_mask"][1:5, 1:7],
            time_edges_s=np.arange(5) * 3000., interval_rain_m3=rain.sum(axis=(1, 2)) * 3000. / 3600 * .4)
        metadata = dict(plan=plan, forcing_identity=identity({"rain_mm_h": rain}, {"dt_s": 3000.}))
        return arrays, metadata, source, grid, plan

    def test_full_grid_absolute_window_mask_and_adaptive_reference(self):
        values = self.fixture()
        with patch("terrain_pipeline.mountain_storm_forcing.interval_mean_mm_h", side_effect=AssertionError("production formula")):
            report = audit_fields(*values)
        self.assertTrue(report["full_grid_time_quadrature_passed"])
        self.assertGreater(report["adaptive_samples"], 70)
        self.assertLess(report["max_rain_error_mm_h"], 1e-12)

    def test_redistributed_rain_with_recomputed_forcing_hash_is_rejected(self):
        arrays, metadata, source, grid, plan = self.fixture()
        arrays["rain_mm_h"][0, 0, 0] += .001
        arrays["rain_mm_h"][0, 0, 1] -= .001
        metadata["forcing_identity"] = numerical_identity(arrays["rain_mm_h"], 3000.)
        with self.assertRaisesRegex(ValueError, "full-grid time quadrature"):
            audit_fields(arrays, metadata, source, grid, plan)

    def test_unknown_and_external_plan_are_rejected(self):
        values = list(self.fixture())
        values[0]["rain_mm_h"][0, 1, 2] = .01
        with self.assertRaisesRegex(ValueError, "unknown rainfall"):
            audit_fields(*values)
        values = list(self.fixture())
        values[-1] = copy.deepcopy(values[-1])
        values[-1]["window"][0] = 0
        with self.assertRaisesRegex(ValueError, "external native storm plan"):
            audit_fields(*values)

    def test_inactive_stationary_uniform_and_fast_moving_partial_interval(self):
        parameters = asdict(StormParameters(0., 0., 0., 0., 10., 30., 10., 20.))
        self.assertEqual(adaptive_mean(0., 0., 0., 5., parameters), 0.)
        self.assertAlmostEqual(float(independent_mean(0., 0., 0., 30., parameters)), 10., places=12)
        parameters["spatial_mode"] = "uniform"
        self.assertAlmostEqual(adaptive_mean(800., 300., 15., 25., parameters), 15., places=12)
        parameters = asdict(StormParameters(0., 0., 40., 10., 10., 30., 10., 20.))
        for east, south in ((240., 60.), (0., 0.), (800., -400.)):
            self.assertAlmostEqual(float(independent_mean(east, south, 5., 25., parameters)),
                                   adaptive_mean(east, south, 5., 25., parameters), places=11)


if __name__ == "__main__":
    unittest.main()
