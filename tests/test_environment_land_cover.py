"""External-behaviour tests for the G6 land-cover consumer.

Every test asserts something a caller can observe: the two conversions, the three
separated products, which inputs the cover class actually consumes, the status map,
and the refusals. Nothing asserts an internal helper or a magic constant.

The two properties that must never regress are (a) bulk thickness goes through the
pore space exactly once, and (b) the cover class is not a rescaled annual
precipitation colour.
"""

import inspect
import math
import unittest
from dataclasses import replace

import numpy as np

from terrain_pipeline import soil_water as cover_module
from terrain_pipeline.soil_water import BARE_ROCK, COVER_CLASSES, FOREST, GRASS, SHRUB, SPARSE, WETLAND, LandCoverParameters, assess_land_cover, bulk_thickness_m, land_cover_describe as describe, soil_water_capacity_mm


AREA = 900.0
#: A parent solid volume that clears the bare-rock gate and reaches the declared full
#: support thickness: 585 m3 over 900 m2 with 0.35 porosity is exactly 1.0 m of bulk soil,
#: and 150 mm of capacity at the declared 15% available-water fraction.
FULL_SOLID_M3 = 585.0
#: Water chosen so the site sits at 60% of capacity: above the bare-rock gate, safely
#: below the wetland fraction, and on a class threshold the water driver can move.
MID_WATER_MM = 90.0


def _call(**overrides):
    # The default must be a column the *whole* rule can judge: thick enough to leave the
    # bare-rock gate, thick enough to saturate the material score, and wet enough to leave
    # the driest class — while staying below the wetland fraction. A thinner or wetter
    # default would collapse every controlled case onto one class for the same reason and
    # would tell us nothing about the driver under test.
    arguments = dict(
        parent_solid_m3=np.array([FULL_SOLID_M3, FULL_SOLID_M3]),
        porosity=np.array([0.35, 0.35]),
        horizontal_area_m2=AREA,
        family_temperature_c=np.array([14.0, 14.0]),
        water_state_mm=np.array([MID_WATER_MM, MID_WATER_MM]),
        hard_substrate=np.array([False, False]))
    arguments.update(overrides)
    return assess_land_cover(**arguments)


class DeclarationTests(unittest.TestCase):
    def test_describe_states_both_conversions_and_the_never_list(self):
        declared = describe()
        self.assertEqual(declared["schema"], "environment-land-cover-v1")
        self.assertIn("(1 - porosity)", declared["thickness_conversion"])
        self.assertIn("never a stock", declared["capacity_conversion"])
        self.assertEqual(declared["separated_products"],
                         ["soil", "suitability", "land_cover"])
        never = " | ".join(declared["never"])
        self.assertIn("solid volume divided by area", never)
        self.assertIn("annual precipitation alone", never)

    def test_cover_classes_are_ordered_and_stable(self):
        self.assertEqual(COVER_CLASSES[0], "bare_rock")
        self.assertEqual(COVER_CLASSES[-1], "wetland")
        self.assertEqual(len(set(COVER_CLASSES)), len(COVER_CLASSES))
        self.assertEqual((BARE_ROCK, SPARSE, GRASS, SHRUB, FOREST, WETLAND),
                         (0, 1, 2, 3, 4, 5))

    def test_module_imports_no_bucket_network_or_vegetation_model(self):
        imports = "\n".join(line for line in inspect.getsource(cover_module.assess_land_cover).splitlines()
                            if line.lstrip().startswith(("import ", "from ")))
        for forbidden in ("metric_pet_et", "regional_surface_forcing", "rainfall_runoff",
                          "metric_runoff", "metric_network", "weathering_soil_inventory"):
            self.assertNotIn(forbidden, imports)


class BulkThicknessTests(unittest.TestCase):
    def test_bulk_thickness_divides_by_pore_space_not_just_area(self):
        solid = np.array([0.35, 0.70])
        thickness = bulk_thickness_m(solid, porosity=np.array([0.30, 0.30]),
                                     horizontal_area_m2=AREA)
        # 0.35 / ((1-0.3)*900) and 0.70 / ((1-0.3)*900)
        np.testing.assert_allclose(thickness, solid / (0.7 * AREA), rtol=0.0, atol=0.0)
        # And it is strictly larger than the equivalent solid thickness.
        solid_equivalent = solid / AREA
        self.assertTrue(np.all(thickness > solid_equivalent))

    def test_zero_porosity_reduces_to_the_solid_thickness(self):
        solid = np.array([0.9])
        thickness = bulk_thickness_m(solid, porosity=np.zeros(1),
                                     horizontal_area_m2=AREA)
        np.testing.assert_allclose(thickness, solid / AREA, rtol=0.0, atol=0.0)

    def test_porosity_of_one_is_refused(self):
        for bad in (1.0, 1.5, -0.1):
            with self.subTest(porosity=bad):
                with self.assertRaises(ValueError):
                    bulk_thickness_m(np.array([1.0]), porosity=np.array([bad]),
                                     horizontal_area_m2=AREA)

    def test_negative_solid_volume_is_refused(self):
        with self.assertRaises(ValueError):
            bulk_thickness_m(np.array([-1.0]), porosity=np.array([0.3]),
                             horizontal_area_m2=AREA)

    def test_non_positive_area_is_refused(self):
        for area in (0.0, -900.0, float("nan"), float("inf")):
            with self.subTest(area=area):
                with self.assertRaises(ValueError):
                    bulk_thickness_m(np.array([1.0]), porosity=np.array([0.3]),
                                     horizontal_area_m2=area)


class CapacityTests(unittest.TestCase):
    def test_capacity_is_thickness_times_declared_fraction(self):
        params = LandCoverParameters()
        thickness = np.array([0.5, 1.0])
        capacity = soil_water_capacity_mm(thickness, params)
        np.testing.assert_allclose(
            capacity, thickness * 1000.0 * params.available_water_fraction,
            rtol=0.0, atol=0.0)

    def test_capacity_scales_with_the_declared_fraction(self):
        thin = soil_water_capacity_mm(np.array([1.0]),
                                      replace(LandCoverParameters(),
                                              available_water_fraction=0.10))
        thick = soil_water_capacity_mm(np.array([1.0]),
                                       replace(LandCoverParameters(),
                                               available_water_fraction=0.20))
        self.assertAlmostEqual(float(thick[0]), 2.0 * float(thin[0]), places=12)

    def test_negative_thickness_is_refused(self):
        with self.assertRaises(ValueError):
            soil_water_capacity_mm(np.array([-0.1]))


class SeparatedProductTests(unittest.TestCase):
    def test_three_products_are_reported_separately(self):
        result = _call()
        for name in ("soil_thickness_bulk_m", "soil_water_capacity_mm",
                     "suitability", "land_cover", "land_cover_index"):
            self.assertIn(name, result)
        self.assertEqual(result["soil_thickness_bulk_m"].shape, (2,))
        self.assertEqual(result["suitability"].shape, (2,))
        self.assertEqual(result["land_cover"].shape, (2,))

    def test_capacity_and_stock_are_never_the_same_field(self):
        # A 2.0 m layer with 15% available water can hold 300 mm; holding 0 mm now is legal.
        result = _call(water_state_mm=np.zeros(2),
                       parent_solid_m3=np.array([1.26, 1.26]))
        self.assertGreater(float(result["soil_water_capacity_mm"][0]), 0.0)
        np.testing.assert_array_equal(result["water_state_total_mm"], np.zeros(2))
        np.testing.assert_array_equal(result["water_ratio_of_capacity"], np.zeros(2))
        self.assertEqual(result["units"]["soil_water_capacity_mm"], "mm")
        self.assertEqual(result["units"]["water_state_total_mm"], "mm")

    def test_bucket_state_is_summed_and_a_plain_vector_is_accepted(self):
        bucket = np.stack([np.array([10.0, 0.0]), np.array([5.0, 0.0]),
                           np.array([2.0, 0.0])])
        summed = _call(water_state_mm=bucket)
        np.testing.assert_allclose(summed["water_state_total_mm"], np.array([17.0, 0.0]),
                                   rtol=0.0, atol=0.0)
        self.assertEqual(summed["water_state_shape"], [3, 2])
        plain = _call(water_state_mm=np.array([17.0, 0.0]))
        np.testing.assert_allclose(plain["water_state_total_mm"],
                                   summed["water_state_total_mm"], rtol=0.0, atol=0.0)


class CoverConsumesItsInputsTests(unittest.TestCase):
    """The cover class is not annual precipitation rescaled onto a colour.

    Each controlled case keeps the material thick enough to leave the bare-rock gate, so
    the only thing that can move the class is the driver under test. A thin default would
    make every side bare_rock and prove nothing.
    """

    def test_cover_changes_when_only_the_water_state_changes(self):
        # Capacity is 150 mm, so 0 mm and 120 mm are 0% and 80% of capacity: both clear
        # the rock gate and stay below the wetland fraction, and the class still moves.
        dry = _call(water_state_mm=np.array([0.0, 0.0]))
        wet = _call(water_state_mm=np.array([120.0, 120.0]))
        self.assertEqual(dry["land_cover"][0], "shrub")
        self.assertEqual(wet["land_cover"][0], "forest")
        self.assertGreater(float(wet["normalised_water"][0]),
                           float(dry["normalised_water"][0]))

    def test_cover_changes_when_only_the_material_changes(self):
        # 5 m3 gives 8.5 mm of soil, under the 0.02 m rock gate; 585 m3 gives a full 1.0 m.
        bare = _call(parent_solid_m3=np.array([5.0, 5.0]))
        thick = _call(parent_solid_m3=np.array([FULL_SOLID_M3, FULL_SOLID_M3]))
        self.assertEqual(bare["land_cover"][0], "bare_rock")
        self.assertNotEqual(thick["land_cover"][0], "bare_rock")
        self.assertGreater(float(thick["normalised_material"][0]),
                           float(bare["normalised_material"][0]))

    def test_cover_changes_when_only_the_temperature_changes(self):
        cold = _call(family_temperature_c=np.array([-40.0, -40.0]))
        warm = _call(family_temperature_c=np.array([14.0, 14.0]))
        # -40 C is outside the declared 14 +/- 16 C window: the temperature score is 0.
        self.assertEqual(float(cold["normalised_temperature"][0]), 0.0)
        self.assertGreater(float(warm["normalised_temperature"][0]), 0.0)
        self.assertEqual(cold["land_cover"][0], "grass")
        self.assertEqual(warm["land_cover"][0], "forest")

    def test_thin_layer_is_rock_whatever_the_climate(self):
        result = _call(parent_solid_m3=np.array([1e-6, 1e-6]),
                       family_temperature_c=np.array([14.0, 14.0]),
                       water_state_mm=np.array([500.0, 500.0]))
        self.assertTrue(all(name == "bare_rock" for name in result["land_cover"]))

    def test_hard_substrate_forces_bare_rock(self):
        result = _call(hard_substrate=np.array([True, False]))
        self.assertEqual(result["land_cover"][0], "bare_rock")
        # The second column is identical except for the substrate flag, so it must keep a
        # developed class: that is what makes the flag — not something else — the cause.
        self.assertEqual(result["land_cover"][1], "forest")

    def test_standing_water_above_the_declared_fraction_is_wetland(self):
        params = LandCoverParameters()
        measured = _call()
        capacity = float(measured["soil_water_capacity_mm"][0])
        self.assertGreater(capacity, 0.0)
        saturated = _call(water_state_mm=np.array([capacity * 0.99, capacity * 0.99]))
        self.assertEqual(saturated["land_cover"][0], "wetland")
        self.assertGreaterEqual(float(saturated["water_ratio_of_capacity"][0]),
                                params.wetland_water_fraction)
        # Just below the wetland fraction stays out of the wetland class.
        below = _call(water_state_mm=np.array([capacity * 0.5, capacity * 0.5]))
        self.assertNotEqual(below["land_cover"][0], "wetland")

    def test_full_capacity_does_not_mean_a_wet_site(self):
        # A site at 40% of capacity is not a wetland; "full" in the thickness sense is a
        # different statement from "full of water".
        capacity = float(_call()["soil_water_capacity_mm"][0])
        partial = _call(water_state_mm=np.array([capacity * 0.40, capacity * 0.40]))
        self.assertNotEqual(partial["land_cover"][0], "wetland")
        self.assertGreater(float(partial["normalised_water"][0]), 0.0)


class StatusTests(unittest.TestCase):
    def test_computed_and_declared_are_distinguished(self):
        result = _call()
        status = result["field_status"]
        self.assertEqual(status["soil_thickness_bulk_m"], "computed")
        self.assertEqual(status["suitability"], "computed")
        self.assertEqual(status["land_cover"], "computed")
        self.assertEqual(status["soil_water_capacity_mm"], "declared")

    def test_missing_driver_leaves_the_class_pending_not_zero(self):
        result = _call(status={"water_state": "pending"})
        self.assertEqual(result["field_status"]["suitability"], "pending")
        self.assertEqual(result["field_status"]["land_cover"], "pending")
        self.assertTrue(all(name == "pending" for name in result["land_cover"]))

    def test_missing_substrate_is_reported_as_pending(self):
        result = _call(hard_substrate=None)
        self.assertEqual(result["field_status"]["land_cover_hard_substrate"], "pending")
        # The class is still computed, but the reader is told one input was missing.
        self.assertEqual(result["field_status"]["land_cover"], "pending")

    def test_declared_inputs_are_labelled_declared(self):
        result = _call(status={"material": "declared", "family_temperature": "declared"})
        status = result["field_status"]
        self.assertEqual(status["parent_solid_m3"], "declared")
        self.assertEqual(status["family_temperature_c"], "declared")


class RefusalTests(unittest.TestCase):
    def test_length_mismatch_is_refused(self):
        with self.assertRaises(ValueError):
            _call(porosity=np.array([0.3]))
        with self.assertRaises(ValueError):
            _call(family_temperature_c=np.array([14.0]))
        with self.assertRaises(ValueError):
            _call(water_state_mm=np.array([1.0]))

    def test_bucket_state_with_wrong_leading_dimension_is_refused(self):
        with self.assertRaises(ValueError):
            _call(water_state_mm=np.zeros((2, 2)))
        with self.assertRaises(ValueError):
            _call(water_state_mm=np.zeros((3, 2, 1)))

    def test_negative_water_state_is_refused(self):
        with self.assertRaises(ValueError):
            _call(water_state_mm=np.array([-1.0, 0.0]))

    def test_non_finite_inputs_are_refused(self):
        for bad in (float("nan"), float("inf")):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    _call(porosity=np.array([bad, 0.3]))

    def test_empty_column_set_is_refused(self):
        with self.assertRaises(ValueError):
            _call(parent_solid_m3=np.array([]), porosity=np.array([]),
                  family_temperature_c=np.array([]),
                  water_state_mm=np.array([]))

    def test_capacity_reference_length_is_checked(self):
        with self.assertRaises(ValueError):
            _call(water_capacity_reference_mm=np.array([1.0]))


class ParameterTests(unittest.TestCase):
    def test_weights_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            LandCoverParameters(weight_temperature=0.9, weight_water=0.9,
                                weight_material=0.9)

    def test_thresholds_must_be_increasing(self):
        with self.assertRaises(ValueError):
            LandCoverParameters(sparse_threshold=0.8, grass_threshold=0.4)

    def test_negative_parameter_is_refused(self):
        with self.assertRaises(ValueError):
            LandCoverParameters(available_water_fraction=-0.1)

    def test_parameter_identity_moves_with_the_parameters(self):
        base = LandCoverParameters()
        self.assertNotEqual(base.identity_sha256,
                            replace(base, available_water_fraction=0.2).identity_sha256)

    def test_identity_moves_with_the_inputs(self):
        base = _call()
        moved = _call(parent_solid_m3=np.array([0.6, 0.5]))
        self.assertNotEqual(base["identity"]["inputs_sha256"],
                            moved["identity"]["inputs_sha256"])

    def test_identity_is_order_independent_for_the_same_columns(self):
        base = _call(parent_solid_m3=np.array([0.4, 0.9]),
                     porosity=np.array([0.3, 0.4]),
                     family_temperature_c=np.array([10.0, 18.0]),
                     water_state_mm=np.array([20.0, 40.0]))
        same = _call(parent_solid_m3=np.array([0.4, 0.9]),
                     porosity=np.array([0.3, 0.4]),
                     family_temperature_c=np.array([10.0, 18.0]),
                     water_state_mm=np.array([20.0, 40.0]))
        self.assertEqual(base["identity"]["inputs_sha256"],
                         same["identity"]["inputs_sha256"])


class MonotonicityTests(unittest.TestCase):
    def test_more_water_never_lowers_the_water_score(self):
        params = LandCoverParameters()
        solid = np.array([1.26, 1.26])
        scores = []
        for depth in (0.0, 10.0, 50.0, 150.0):
            result = _call(parent_solid_m3=solid,
                           water_state_mm=np.full(2, depth))
            scores.append(float(result["normalised_water"][0]))
        self.assertEqual(scores, sorted(scores))

    def test_thicker_layer_never_lowers_the_material_score(self):
        scores = []
        for solid in (0.01, 0.5, 1.26, 5.0):
            result = _call(parent_solid_m3=np.full(2, solid))
            scores.append(float(result["normalised_material"][0]))
        self.assertEqual(scores, sorted(scores))

    def test_suitability_is_the_declared_weighted_sum(self):
        params = LandCoverParameters()
        result = _call()
        expected = (params.weight_temperature * result["normalised_temperature"]
                    + params.weight_water * result["normalised_water"]
                    + params.weight_material * result["normalised_material"])
        np.testing.assert_allclose(result["suitability"], expected, rtol=0.0, atol=1e-15)


if __name__ == "__main__":
    unittest.main()
