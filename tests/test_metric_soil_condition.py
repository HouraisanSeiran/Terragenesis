"""metric_soil_condition 的单元测试（unittest，无 pytest）。"""

import unittest

import numpy as np

from terrain_pipeline.soil_water import SOIL_ALGORITHM, SoilParameters, metadata, required_halo_m, soil_condition


def constant_sampler(value):
    def sampler(x, z):
        return np.full(np.shape(x), float(value), dtype=np.float64)

    return sampler


def plane_45deg_sampler(x, z):
    # 沿 x 方向 45 度坡面：dh/dx = 1.0，z 方向坡度为零。
    return np.asarray(x, dtype=np.float64)


class TestSoilCondition(unittest.TestCase):
    def test_flat_slope_zero_drainage_precipitation_only(self):
        params = SoilParameters()
        result = soil_condition(
            1,
            np.array([0.0, 100.0, -100.0]),
            np.array([0.0, 50.0, -50.0]),
            elevation=constant_sampler(0.0),
            bio12_mm=constant_sampler(2000.0),
            thickness_m=constant_sampler(2.0),
            parameters=params,
        )
        wetness = min(2000.0 / params.available_water_span_mm, 1.0)
        index = 1.0 * wetness
        expected = 3 if index >= params.drainage_threshold_high else (
            2 if index >= params.drainage_threshold_mid else (
                1 if index >= params.drainage_threshold_low else 0
            )
        )
        self.assertTrue(np.all(result["drainage"] == expected))
        self.assertAlmostEqual(float(result["soil_depth_m"][0]), 2.0, places=12)

    def test_45deg_slope_drainage_zero_and_shallow(self):
        params = SoilParameters()
        result = soil_condition(
            7,
            np.array([0.0]),
            np.array([0.0]),
            elevation=plane_45deg_sampler,
            bio12_mm=constant_sampler(2200.0),
            thickness_m=constant_sampler(4.0),
            parameters=params,
        )
        self.assertEqual(int(result["drainage"][0]), 0)
        self.assertLess(float(result["soil_depth_m"][0]), 4.0 * 0.5)
        self.assertLess(float(result["soil_depth_m"][0]), 4.0)

    def test_soil_depth_never_exceeds_thickness_random(self):
        rng = np.random.default_rng(12345)
        x = rng.uniform(-5000.0, 5000.0, size=200)
        z = rng.uniform(-5000.0, 5000.0, size=200)

        def elev(xa, za):
            return 0.001 * xa + 0.002 * za

        def rain(xa, za):
            return 500.0 + 100.0 * np.sin(0.0001 * xa)

        def thick(xa, za):
            return 0.25 + (abs(np.sin(0.0002 * xa + 0.0003 * za)) * 3.75)

        result = soil_condition(
            42, x, z, elevation=elev, bio12_mm=rain, thickness_m=thick
        )
        max_thick = 4.0
        self.assertTrue(np.all(result["soil_depth_m"] <= max_thick + 1e-12))

    def test_deterministic_bitwise_equal(self):
        x = np.linspace(-1000, 1000, 25)
        z = np.linspace(500, -500, 25)

        def elev(xa, za):
            return np.sin(xa / 500.0) + np.cos(za / 500.0)

        def rain(xa, za):
            return 1000.0 + 200.0 * np.cos(xa / 300.0)

        def thick(xa, za):
            return 2.0 + 1.5 * np.sin(za / 400.0)

        a = soil_condition(5, x, z, elevation=elev, bio12_mm=rain, thickness_m=thick)
        b = soil_condition(5, x, z, elevation=elev, bio12_mm=rain, thickness_m=thick)
        for key in ("soil_depth_m", "drainage", "available_water"):
            self.assertTrue(np.array_equal(a[key], b[key]))

    def test_scalar_input_returns_scalar_and_shape(self):
        result = soil_condition(
            3,
            0.0,
            0.0,
            elevation=constant_sampler(10.0),
            bio12_mm=constant_sampler(1000.0),
            thickness_m=constant_sampler(1.5),
        )
        for key in ("soil_depth_m", "drainage", "available_water"):
            self.assertEqual(result[key].shape, ())
            self.assertEqual(result[key].ndim, 0)

        x = np.array([0.0, 1.0, 2.0])
        z = np.array([0.0, 1.0, 2.0])
        arr = soil_condition(
            3,
            x,
            z,
            elevation=constant_sampler(10.0),
            bio12_mm=constant_sampler(1000.0),
            thickness_m=constant_sampler(1.5),
        )
        for key in ("soil_depth_m", "drainage", "available_water"):
            self.assertEqual(arr[key].shape, (3,))

    def test_available_water_in_unit_interval(self):
        rng = np.random.default_rng(99)
        x = rng.uniform(-10000, 10000, size=300)
        z = rng.uniform(-10000, 10000, size=300)

        def elev(xa, za):
            return 0.01 * xa - 0.02 * za

        def rain(xa, za):
            return np.clip(3000.0 + 500.0 * np.sin(xa / 1000.0), 0.0, None)

        def thick(xa, za):
            return np.ones(np.shape(xa))

        result = soil_condition(11, x, z, elevation=elev, bio12_mm=rain, thickness_m=thick)
        aw = result["available_water"]
        self.assertTrue(np.all(aw >= 0.0))
        self.assertTrue(np.all(aw <= 1.0))

    def test_drainage_integer_in_range(self):
        rng = np.random.default_rng(7)
        x = rng.uniform(-10000, 10000, size=300)
        z = rng.uniform(-10000, 10000, size=300)

        def elev(xa, za):
            return 0.001 * xa + 0.001 * za

        def rain(xa, za):
            return 1500.0 + 1000.0 * np.cos(za / 2000.0)

        def thick(xa, za):
            return np.ones(np.shape(xa)) * 2.0

        result = soil_condition(13, x, z, elevation=elev, bio12_mm=rain, thickness_m=thick)
        drainage = result["drainage"]
        self.assertTrue(np.issubdtype(drainage.dtype, np.integer))
        self.assertTrue(np.all(np.isin(drainage, [0, 1, 2, 3])))

    def test_invalid_seed_raises(self):
        kwargs = dict(
            elevation=constant_sampler(0.0),
            bio12_mm=constant_sampler(1000.0),
            thickness_m=constant_sampler(1.0),
        )
        for bad_seed in (-1, 2**64, True, False, 1.0):
            with self.assertRaises(ValueError):
                soil_condition(bad_seed, 0.0, 0.0, **kwargs)

    def test_nonfinite_coordinates_raise(self):
        kwargs = dict(
            elevation=constant_sampler(0.0),
            bio12_mm=constant_sampler(1000.0),
            thickness_m=constant_sampler(1.0),
        )
        for bad in (float("inf"), float("nan"), float("-inf")):
            with self.assertRaises(ValueError):
                soil_condition(1, bad, 0.0, **kwargs)
            with self.assertRaises(ValueError):
                soil_condition(1, 0.0, bad, **kwargs)

    def test_negative_material_or_rainfall_is_refused(self):
        common = {"elevation": constant_sampler(0.0)}
        for thickness, rainfall in ((-2.0, 1000.0), (2.0, -500.0)):
            with self.subTest(thickness=thickness, rainfall=rainfall):
                with self.assertRaises(ValueError):
                    soil_condition(
                        1, 0.0, 0.0,
                        thickness_m=constant_sampler(thickness),
                        bio12_mm=constant_sampler(rainfall),
                        **common,
                    )

    def test_wrong_sampler_shape_raises(self):
        def bad_sampler(x, z):
            return np.zeros((3, 3), dtype=np.float64)

        with self.assertRaises(ValueError):
            soil_condition(
                1,
                np.array([0.0, 1.0, 2.0]),
                np.array([0.0, 1.0, 2.0]),
                elevation=bad_sampler,
                bio12_mm=constant_sampler(1000.0),
                thickness_m=constant_sampler(1.0),
            )

    def test_required_halo_m_equals_slope_spacing(self):
        params = SoilParameters(slope_spacing_m=1234.0)
        self.assertEqual(required_halo_m(params), 1234.0)
        self.assertEqual(required_halo_m(), SoilParameters().slope_spacing_m)

    def test_metadata_declares_synthetic_soil(self):
        md = metadata(1)
        self.assertTrue(md["synthetic_soil"])
        self.assertFalse(md["measured_soil"])
        self.assertEqual(md["algorithm"], SOIL_ALGORITHM)
        self.assertEqual(md["halo_m"], SoilParameters().slope_spacing_m)

    def test_parameters_are_actually_consumed(self):
        # 高程必须对 x 非线性，否则中心差分出来的坡度与采样间距无关，
        # 改 slope_spacing_m 不会改变任何输出，测试就成了假通过。
        def elev(xa, za):
            return np.sin(xa / 3000.0) + 0.02 * za

        x = np.linspace(-1000.0, 1000.0, 16)
        z = np.linspace(-1000.0, 1000.0, 16)
        common = dict(
            elevation=elev,
            bio12_mm=constant_sampler(1200.0),
            thickness_m=constant_sampler(2.0),
        )
        default = soil_condition(1, x, z, parameters=SoilParameters(), **common)
        custom = soil_condition(
            1, x, z, parameters=SoilParameters(slope_spacing_m=2500.0), **common
        )
        self.assertFalse(np.array_equal(default["soil_depth_m"], custom["soil_depth_m"]))


if __name__ == "__main__":
    unittest.main()
