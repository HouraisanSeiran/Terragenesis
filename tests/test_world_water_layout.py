"""Contract tests for the public world water/land layout.

These test *external* behaviour and the invariants the design claims: window-free world
stability, geometry that does not move when the sampling spacing changes, exact refusal
codes with numbers, and the macro-only claim level. Nothing here runs Terrain Diffusion
or a GPU, and no test asserts a production 30 m result.
"""
import math
import unittest

import numpy as np

from terrain_pipeline.world_water_layout import (
    ALGORITHM,
    CLASS_LAND,
    CLASS_LAKE,
    CLASS_OCEAN,
    LayoutError,
    LayoutRefused,
    LayoutSpec,
    MODE_FINITE,
    MODE_INFINITE,
    REASON_CODES,
    SCHEMA,
    classify_points,
    derive_subseed,
    describe,
    identity,
    measure_grid,
)

SEED = 20261020


def earth(**kwargs):
    kwargs.setdefault("total_water_fraction", 0.62)
    return LayoutSpec("earth", **kwargs)


def lakes(**kwargs):
    kwargs.setdefault("total_water_fraction", 0.12)
    return LayoutSpec("lakes", **kwargs)


class SpecTests(unittest.TestCase):
    def test_identity_is_stable_and_parameter_sensitive(self):
        first = identity(earth())
        self.assertEqual(first, identity(earth()))
        self.assertNotEqual(first, identity(earth(total_water_fraction=0.63)))
        self.assertNotEqual(first, identity(earth(world_seed=SEED + 1)))
        self.assertNotEqual(first, identity(earth(layout_id="other")))
        self.assertEqual(len(first), 64)

    def test_infinite_rejects_a_frame(self):
        with self.assertRaises(LayoutError):
            LayoutSpec("earth", 0.62, mode=MODE_INFINITE,
                       frame_origin_m=(0.0, 0.0), frame_side_m=1000.0)

    def test_finite_requires_a_frame(self):
        with self.assertRaises(LayoutError):
            LayoutSpec("earth", 0.62, mode=MODE_FINITE)

    def test_design_gap_uses_h_design_only(self):
        spec = earth(h_design_m=4_000.0, w_geom_m=40_000.0, epsilon_m=1.0)
        self.assertAlmostEqual(spec.design_gap_m,
                               40_000.0 + 2.0 * math.sqrt(2.0) * 4_000.0 + 1.0)

    def test_small_field_scale_is_not_rejected_by_legacy_gap(self):
        self.assertEqual(earth(region_side_m=10_000.0).region_side_m, 10_000.0)

    def test_invalid_inputs_are_rejected(self):
        for kwargs in ({"total_water_fraction": -0.1},
                       {"total_water_fraction": 1.5},
                       {"world_seed": -1}, {"world_seed": 2 ** 64},
                       {"layout_id": ""}, {"mode": "nope"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(LayoutError):
                    earth(**kwargs)

    def test_ocean_preset_refuses_all_sea_target(self):
        with self.assertRaises(LayoutRefused):
            earth(total_water_fraction=1.0)


class SubSeedTests(unittest.TestCase):
    def test_repeatable_and_region_sensitive(self):
        a = derive_subseed(SEED, "lid", "cores", 1, -2)
        self.assertEqual(a, derive_subseed(SEED, "lid", "cores", 1, -2))
        self.assertNotEqual(a, derive_subseed(SEED, "lid", "cores", -1, 2))
        self.assertNotEqual(a, derive_subseed(SEED, "lid", "place", 1, -2))
        self.assertTrue(0 <= a < 2 ** 64)

    def test_nul_is_rejected(self):
        with self.assertRaises(LayoutError):
            derive_subseed(SEED, "bad\x00id", "cores")


class QueryTests(unittest.TestCase):
    def test_query_has_no_window_parameter(self):
        import inspect
        signature = inspect.signature(classify_points)
        self.assertEqual(list(signature.parameters), ["spec", "x_m", "z_m"])

    def test_same_point_out_of_order_is_identical(self):
        spec = earth()
        x = np.array([-1000.0, 50_000.0, 200_000.0, -300_000.0])
        z = np.array([20_000.0, -80_000.0, 300_000.0, 40_000.0])
        forward = classify_points(spec, x, z)
        order = np.array([2, 0, 3, 1])
        shuffled = classify_points(spec, x[order], z[order])
        np.testing.assert_array_equal(forward[order], shuffled)

    def test_overlapping_windows_agree(self):
        spec = earth()
        axis_a = np.arange(0.0, 100_000.0, 5_000.0)
        axis_b = np.arange(50_000.0, 150_000.0, 5_000.0)
        classes_a = classify_points(spec, axis_a[None, :], axis_a[:, None])
        classes_b = classify_points(spec, axis_b[None, :], axis_b[:, None])
        shared = [value for value in axis_a if value in set(axis_b.tolist())]
        self.assertTrue(shared)
        for value in shared:
            i = int(np.where(axis_a == value)[0][0])
            j = int(np.where(axis_b == value)[0][0])
            np.testing.assert_array_equal(classes_a[:, i], classes_b[:, j])

    def test_finite_frame_edge_is_ocean_for_ocean_presets(self):
        spec = LayoutSpec("earth", 0.62, mode=MODE_FINITE,
                          frame_origin_m=(0.0, 0.0), frame_side_m=512_000.0)
        outside = classify_points(spec, np.array([-1.0, 512_001.0]),
                                 np.array([10.0, 10.0]))
        np.testing.assert_array_equal(outside, np.array([CLASS_OCEAN, CLASS_OCEAN],
                                                        dtype=np.uint8))

    def test_classes_are_in_the_declared_vocabulary(self):
        spec = lakes()
        classes = classify_points(spec, np.array([0.0, 100_000.0]),
                                 np.array([0.0, 100_000.0]))
        self.assertTrue(set(np.unique(classes).tolist()) <= {CLASS_LAND, CLASS_LAKE,
                                                             CLASS_OCEAN})


class MeasurementTests(unittest.TestCase):
    def test_measure_reports_macro_claim_and_no_native_claim(self):
        spec = earth()
        result = measure_grid(spec, 0.0, spec.region_side_m, spec.region_side_m / 64.0)
        self.assertEqual(result["claim_level"], "macro_layout_diagnostic_only")
        self.assertIn("TD native 30 m", result["sampling_note"])
        self.assertEqual(result["identity"], spec.identity())

    def test_ragged_grid_is_refused(self):
        spec = earth()
        with self.assertRaises(LayoutRefused):
            measure_grid(spec, 0.0, 1000.0, 300.0)

    def test_lakes_measure_has_single_land_component(self):
        spec = lakes()
        result = measure_grid(spec, 0.0, spec.region_side_m, spec.region_side_m / 32.0)
        self.assertGreaterEqual(result["land_components_4"], 1)


class DescribeTests(unittest.TestCase):
    def test_describe_states_the_limits(self):
        info = describe()
        self.assertEqual(info["schema"], SCHEMA)
        self.assertEqual(info["algorithm"], ALGORITHM)
        self.assertEqual(info["production_spacing_m"], 30.0)
        self.assertFalse(info["minimum_unit_achieved"])
        self.assertFalse(info["terrain_diffusion_inference"])
        self.assertFalse(info["gpu"])
        self.assertEqual(set(info["reason_codes"]), set(REASON_CODES))


if __name__ == "__main__":
    unittest.main()
