"""Contract tests for the v2 terrain-refined climate layer (P4.3).

Acceptance mapping (contract `climate-refinement-spec.md` §7):

- §7.1 bit-for-bit v1 replay when the refinement layer is off ->
  `test_off_refinement_replays_v1_bit_for_bit`, `test_off_refinement_grid_rainfall_replays_v1`
- §7.2 window / call-order independence -> `test_window_and_call_order_independence`
- §7.3 v1 untouched (frozen identity + frozen source bytes) -> `test_v1_source_and_identity_are_frozen`
- §7.4 terrain really acts (+500 m plateau: windward wetter, lee drier; monotone in gain) ->
  `test_plateau_step_raises_windward_and_lowers_lee`, `test_windward_response_is_monotone_in_gain`
- §7.5 well-defined bands (`latitude_norm` periodic, `wind_unit` finite/discrete) ->
  `test_latitude_norm_is_periodic_and_seed_free`, `test_wind_unit_is_finite_and_discrete`
- §7.6 clamping and monthly-sum closure -> `test_extreme_parameters_stay_clamped_and_closed`
- §7.7 (P4.5 owns the full suite; the intermediate state must already hold) ->
  `test_bio_relations_hold_after_refinement`
- §4.3 elevation end to end and pure-sampler contract -> `test_elevation_end_to_end_and_pure_sampler`
- §5 identity and naming -> `test_v2_identity_naming_and_parameter_coverage`
- §3.1/§4.4 validation -> `test_parameter_and_argument_validation`

P4.4 adds the two remaining §3.2 rows and the §6 snow-line diagnostic (intermediate
coverage here; P4.5 owns the full suite):

- §3.2 row 1 (band temperature offset) -> `test_temperature_row_shifts_every_month_by_one_band_offset`,
  `test_pole_side_is_cooled_when_the_row_is_on`
- §3.2 row 2 (synthetic band precipitation multiplier) ->
  `test_band_precipitation_row_is_off_by_default_and_signed_when_on`
- §6 snow line as a derived diagnostic only -> `test_snow_line_matches_the_closed_form_of_the_temperature_column`,
  `test_snow_line_ignores_the_precipitation_row`, `test_pole_band_snow_line_sits_below_the_equator_band`
"""

import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.hydrology_planning import coarse_condition_field
from terrain_pipeline.common_infra import identity
from terrain_pipeline.climate_forcing import BAND_STRUCTURE_SEMANTICS, CLIMATE_SCHEMA, LATITUDE_PERIOD_M, RAINFALL_SCHEMA, REFINED_SEMANTICS as SEMANTICS, SNOW_LINE_SCHEMA, WIND_BAND_UNITS, RefinedClimateParameters, grid_rainfall_v2, latitude_norm, ridge_height, sample_climate_v2, snow_line, wind_unit
from terrain_pipeline.climate_forcing import NoiseClimateParameters, grid_rainfall, sample_climate

SEED = 20261011
# §7.3 frozen v1 constants: the identity of the base layer and its source bytes.
V1_IDENTITY_SHA256 = "eaa83779d4c9a6e4f7f974c62958bf0aa4eb2a2b2f08317377208a15abe2846f"
V1_SOURCE_SHA256 = "a928612a0b3b17ac9f360e846d1a200f31ab9dbdea6176542023c6cd3405707c"
V1_SOURCE_PATH = (Path(__file__).resolve().parents[1]
                  / "terrain_pipeline/surface_rivers/metric_noise_forcing.py")
# A +500 m plateau of finite width: the §7.4 terrain step.
PLATEAU_HALF_WIDTH_M = 15_000.
PLATEAU_HEIGHT_M = 500.
# z = 160 km -> band norm sin(2*pi/12) = +0.5 -> mid-latitude band, bearing (wx, wz) = (+1, 0).
BAND_Z_M = 160_000.
WINDWARD_X_M = -7_500.
LEE_X_M = 22_500.
SPACING_M = 30_000.
MONTHLY_CLOSURE_ATOL_MM = 1e-9


def flat_sampler(x_m, z_m):
    """No-terrain baseline: a pure sampler that reports zero height everywhere."""
    return np.zeros(np.broadcast(np.asarray(x_m, np.float64), np.asarray(z_m, np.float64)).shape, np.float64)


def plateau_sampler(x_m, z_m):
    """Pure analytic +500 m plateau over |x| < 15 km, zero elsewhere."""
    x = np.asarray(x_m, np.float64)
    return np.where(np.abs(x) < PLATEAU_HALF_WIDTH_M, PLATEAU_HEIGHT_M, 0.)


def analytic_sampler(x_m, z_m):
    """Pure, window-free, cheap synthetic surface used where only determinism matters."""
    x = np.asarray(x_m, np.float64)
    z = np.asarray(z_m, np.float64)
    return 500. + 300. * np.sin(x / 8000.) + 200. * np.cos(z / 11000.)


def refinement_off(**overrides):
    """Every refinement switch in its documented off position.

    Both §3.2 rows and the §4.2 orographic row are off: the band temperature offset is
    exactly `0.`, the band precipitation gain is exactly `0.` and the orographic multiplier
    is exactly `1.`, so `sample_climate_v2` must replay the v1 months bit for bit (§7.1).
    """
    values = dict(windward_gain_m=0., lee_loss_m=0., max_windward_gain=0., min_lee_retention=1.,
                  latitude_temperature_range_c=0., latitude_precipitation_gain=0.)
    values.update(overrides)
    return RefinedClimateParameters(**values)


def climate_grid(side_z=6, side_x=7, spacing=SPACING_M):
    rows, columns = np.indices((side_z, side_x))
    return columns * spacing, rows * spacing


def window(value, rows, columns):
    """Slice a (k, z, x) or (z, x) result array down to a nested query window."""
    array = np.asarray(value)
    index = (slice(None), rows, columns) if array.ndim == 3 else (rows, columns)
    return array[index]


class MetricClimateRefinementTests(unittest.TestCase):
    # ---------------------------------------------------------------- §7.3
    def test_v1_source_and_identity_are_frozen(self):
        import hashlib

        self.assertEqual(hashlib.sha256(V1_SOURCE_PATH.read_bytes()).hexdigest(), V1_SOURCE_SHA256)
        self.assertEqual(NoiseClimateParameters().identity_sha256, V1_IDENTITY_SHA256)
        direct = sample_climate(SEED, 12., 14.)
        self.assertEqual(direct["parameter_identity_sha256"], V1_IDENTITY_SHA256)
        self.assertEqual(direct["semantics"], "synthetic_monthly_climate_targets_not_measured_weather")
        refined = RefinedClimateParameters()
        self.assertEqual(refined.base_parameter_identity_sha256, V1_IDENTITY_SHA256)
        self.assertNotEqual(refined.identity_sha256, V1_IDENTITY_SHA256)

    # ---------------------------------------------------------------- §7.1
    def test_off_refinement_replays_v1_bit_for_bit(self):
        x, z = climate_grid()
        elevation = np.linspace(0., 2400., x.size).reshape(x.shape)
        parameters = refinement_off()
        v1 = sample_climate(SEED, x, z, elevation, parameters=parameters.base)
        v2 = sample_climate_v2(SEED, x, z, elevation, parameters=parameters, elevation_sampler=flat_sampler)
        np.testing.assert_array_equal(v2["monthly_temperature_c"], v1["monthly_temperature_c"])
        np.testing.assert_array_equal(v2["monthly_precipitation_mm"], v1["monthly_precipitation_mm"])
        np.testing.assert_array_equal(v2["BIO1_4_12_15"], v1["BIO1_4_12_15"])
        for name in ("thermal_strength", "moisture_strength", "continentality_strength"):
            np.testing.assert_array_equal(v2[name], v1[name])
        self.assertIs(v2["orographic_applied"], False)
        self.assertTrue((v2["precipitation_multiplier"] == 1.).all())
        self.assertArrayEqual(v2["base_parameter_identity_sha256"], V1_IDENTITY_SHA256)
        self.assertEqual(v2["parameter_identity_sha256"], refinement_off().identity_sha256)
        # The off switch is also reachable through the gain ceilings alone.
        ceilings = RefinedClimateParameters(max_windward_gain=0., min_lee_retention=1.)
        ceiling_off = sample_climate_v2(SEED, x, z, elevation, parameters=ceilings,
                                        elevation_sampler=flat_sampler)
        np.testing.assert_array_equal(ceiling_off["monthly_precipitation_mm"], v1["monthly_precipitation_mm"])

    def test_off_refinement_grid_rainfall_replays_v1(self):
        parameters = refinement_off()
        edges = [13., 1813.]
        v1, _ = grid_rainfall(SEED, origin_xz_m=[0., 0.], shape_zx=(1, 1), spacing_m=30.,
                              time_edges_s=edges, spatial_subsamples=2)
        v2, metadata = grid_rainfall_v2(SEED, origin_xz_m=[0., 0.], shape_zx=(1, 1), spacing_m=30.,
                                        time_edges_s=edges, elevation_sampler=flat_sampler,
                                        parameters=parameters, spatial_subsamples=2)
        np.testing.assert_array_equal(v2.rain_mm_h, v1.rain_mm_h)
        self.assertEqual(metadata["base_parameter_identity_sha256"], V1_IDENTITY_SHA256)
        self.assertEqual(v2.source_id, "synthetic_noise_terrain_climate_v2")

    def assertArrayEqual(self, value, expected):
        self.assertTrue(np.array_equal(value, expected))

    # ---------------------------------------------------------------- §7.2
    def test_window_and_call_order_independence(self):
        parameters = RefinedClimateParameters()
        x, z = climate_grid(4, 5, SPACING_M)
        crop = (slice(1, 3), slice(2, 4))
        first = sample_climate_v2(SEED, x[crop], z[crop], parameters=parameters,
                                  elevation_sampler=analytic_sampler)
        whole = sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler=analytic_sampler)
        for name in ("monthly_temperature_c", "monthly_precipitation_mm", "BIO1_4_12_15",
                     "latitude_band_norm", "precipitation_multiplier", "orographic_lift",
                     "orographic_shelter", "annual_precipitation_mm",
                     "annual_precipitation_target_mm", "elevation_m"):
            self.assertArrayEqual(first[name], window(whole[name], crop[0], crop[1]))
        again = sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler=analytic_sampler)
        for name in ("monthly_precipitation_mm", "BIO1_4_12_15", "precipitation_multiplier"):
            self.assertArrayEqual(whole[name], again[name])
        # Reverse traversal order of the same world points must not move a bit either.
        reversed_x, reversed_z = x[::-1, ::-1], z[::-1, ::-1]
        reversed_result = sample_climate_v2(SEED, reversed_x, reversed_z, parameters=parameters,
                                           elevation_sampler=analytic_sampler)
        for name in ("monthly_precipitation_mm", "BIO1_4_12_15", "orographic_lift"):
            self.assertArrayEqual(reversed_result[name], np.asarray(whole[name])[..., ::-1, ::-1])

    def test_window_independence_with_default_elevation_sampler(self):
        parameters = RefinedClimateParameters()
        x, z = climate_grid(3, 4, SPACING_M)
        whole = sample_climate_v2(SEED, x, z, parameters=parameters)
        # A single world point queried on its own, then inside a bigger window.
        single = sample_climate_v2(SEED, x[1, 2], z[1, 2], parameters=parameters)
        self.assertArrayEqual(single["monthly_precipitation_mm"],
                              np.asarray(whole["monthly_precipitation_mm"])[:, 1, 2])
        self.assertArrayEqual(single["BIO1_4_12_15"], np.asarray(whole["BIO1_4_12_15"])[:, 1, 2])
        # A small window queried alone, then as a nested window of a bigger one.
        rows, columns = (slice(0, 2), slice(1, 3))
        nested = sample_climate_v2(SEED, x[rows, columns], z[rows, columns], parameters=parameters)
        self.assertArrayEqual(nested["precipitation_multiplier"],
                              window(whole["precipitation_multiplier"], rows, columns))
        self.assertArrayEqual(nested["orographic_lift"], window(whole["orographic_lift"], rows, columns))
        self.assertArrayEqual(nested["elevation_m"], window(whole["elevation_m"], rows, columns))
        self.assertArrayEqual(float(np.asarray(single["elevation_m"])), float(whole["elevation_m"][1, 2]))

    def test_grid_rainfall_v2_is_window_independent(self):
        parameters = RefinedClimateParameters()
        edges = [13., 1813.]
        whole, _ = grid_rainfall_v2(SEED, origin_xz_m=[0., 0.], shape_zx=(6, 8), spacing_m=30.,
                                   time_edges_s=edges, elevation_sampler=analytic_sampler,
                                   parameters=parameters, spatial_subsamples=2)
        cut, _ = grid_rainfall_v2(SEED, origin_xz_m=[90., 60.], shape_zx=(3, 4), spacing_m=30.,
                                 time_edges_s=edges, elevation_sampler=analytic_sampler,
                                 parameters=parameters, spatial_subsamples=2)
        self.assertArrayEqual(whole.rain_mm_h[:, 2:5, 3:7], cut.rain_mm_h)

    # ---------------------------------------------------------------- §7.4
    def test_plateau_step_raises_windward_and_lowers_lee(self):
        parameters = RefinedClimateParameters()
        self.assertEqual(wind_unit(latitude_norm(SEED, BAND_Z_M)), (1, 0))
        windward = sample_climate_v2(SEED, WINDWARD_X_M, BAND_Z_M, parameters=parameters,
                                     elevation_sampler=plateau_sampler)
        lee = sample_climate_v2(SEED, LEE_X_M, BAND_Z_M, parameters=parameters,
                                elevation_sampler=plateau_sampler)
        baseline = sample_climate_v2(SEED, [WINDWARD_X_M, LEE_X_M], BAND_Z_M, parameters=parameters,
                                     elevation_sampler=flat_sampler)
        v1_baseline = sample_climate(SEED, [WINDWARD_X_M, LEE_X_M], BAND_Z_M)
        # The no-terrain baseline is the v1 base layer itself (v1 rain cannot see terrain).
        self.assertIs(baseline["orographic_applied"], False)
        self.assertArrayEqual(baseline["monthly_precipitation_mm"], v1_baseline["monthly_precipitation_mm"])
        self.assertGreater(float(windward["precipitation_multiplier"]), 1.)
        self.assertGreater(float(windward["orographic_lift"]), 0.)
        self.assertEqual(float(windward["orographic_shelter"]), 0.)
        self.assertTrue(windward["orographic_applied"])
        self.assertGreater(float(windward["annual_precipitation_mm"]),
                           float(baseline["annual_precipitation_mm"][0]))
        self.assertLess(float(lee["precipitation_multiplier"]), 1.)
        self.assertEqual(float(lee["orographic_lift"]), 0.)
        self.assertGreater(float(lee["orographic_shelter"]), 0.)
        self.assertLess(float(lee["annual_precipitation_mm"]),
                        float(baseline["annual_precipitation_mm"][1]))
        # The step is real terrain, so the v1 lapse-rate elevation follows it too.
        self.assertEqual(float(windward["elevation_m"]), PLATEAU_HEIGHT_M)
        self.assertEqual(windward["elevation_source"], "caller_supplied_pure_sampler")

    def test_windward_response_is_monotone_in_gain(self):
        gains = (0., 1., 2.5, 5., 8.)
        base_response = sample_climate_v2(SEED, WINDWARD_X_M, BAND_Z_M, parameters=refinement_off(),
                                          elevation_sampler=plateau_sampler)
        annual = [float(sample_climate_v2(
            SEED, WINDWARD_X_M, BAND_Z_M,
            parameters=RefinedClimateParameters(windward_gain_m=gain),
            elevation_sampler=plateau_sampler)["annual_precipitation_mm"]) for gain in gains]
        multipliers = [float(sample_climate_v2(
            SEED, WINDWARD_X_M, BAND_Z_M,
            parameters=RefinedClimateParameters(windward_gain_m=gain),
            elevation_sampler=plateau_sampler)["precipitation_multiplier"]) for gain in gains]
        # Precondition, asserted rather than assumed: the response stays inside the clamp here.
        self.assertLess(max(annual), RefinedClimateParameters().annual_precipitation_max_mm)
        self.assertGreater(min(annual), RefinedClimateParameters().annual_precipitation_min_mm)
        self.assertEqual(annual[0], float(base_response["annual_precipitation_mm"]))
        for index in range(len(gains) - 1):
            self.assertLess(multipliers[index], multipliers[index + 1])
            self.assertLess(annual[index], annual[index + 1])

    # ---------------------------------------------------------------- §7.5
    def test_latitude_norm_is_periodic_and_seed_free(self):
        for z in (-3_500_000., -123_456.7, 0., 45_000., 960_000., 4_800_000.):
            reference = latitude_norm(SEED, z)
            self.assertGreaterEqual(reference, -1.)
            self.assertLessEqual(reference, 1.)
            self.assertEqual(reference, latitude_norm(SEED, z))
            self.assertEqual(reference, latitude_norm(SEED + 7, z))
            self.assertAlmostEqual(latitude_norm(SEED, z + 3 * LATITUDE_PERIOD_M), reference, delta=4e-14)
            self.assertAlmostEqual(latitude_norm(SEED, z - 5 * LATITUDE_PERIOD_M), reference, delta=4e-14)
        self.assertAlmostEqual(latitude_norm(SEED, LATITUDE_PERIOD_M / 4.), 1., delta=1e-15)
        self.assertAlmostEqual(latitude_norm(SEED, -LATITUDE_PERIOD_M / 4.), -1., delta=1e-15)
        values = latitude_norm(SEED, np.linspace(-2 * LATITUDE_PERIOD_M, 2 * LATITUDE_PERIOD_M, 33))
        self.assertArrayEqual(values, latitude_norm(SEED, np.linspace(-2 * LATITUDE_PERIOD_M, 2 * LATITUDE_PERIOD_M, 33)))
        self.assertEqual(float(values[16]), latitude_norm(SEED, 0.))
        self.assertTrue(np.isfinite(values).all())
        self.assertIsInstance(latitude_norm(SEED, 1000.), float)

    def test_wind_unit_is_finite_and_discrete(self):
        reachable = set()
        for value in np.linspace(-1., 1., 4001):
            unit = wind_unit(float(value))
            reachable.add(unit)
        self.assertEqual(reachable, set(WIND_BAND_UNITS))
        for unit in reachable:
            self.assertEqual(len(unit), 2)
            self.assertTrue(all(type(component) is int and component in (-1, 0, 1) for component in unit))
            self.assertEqual(unit[0] ** 2 + unit[1] ** 2, 1)
        self.assertEqual(wind_unit(0.), wind_unit(0.29))
        self.assertEqual(wind_unit(0.5), (1, 0))
        self.assertEqual(wind_unit(-0.5), (1, 0))
        self.assertEqual(wind_unit(0.9), (-1, 0))
        # Same band, same bearing, wherever the place sits in x: three z values in one band.
        for z in (BAND_Z_M, BAND_Z_M + 1000., BAND_Z_M - 2500.):
            self.assertEqual(wind_unit(latitude_norm(SEED, z)), (1, 0))
        with self.assertRaises(ValueError):
            wind_unit(1.5)
        with self.assertRaises(ValueError):
            wind_unit(float("nan"))
        with self.assertRaises(ValueError):
            wind_unit(None)

    # ---------------------------------------------------------------- §7.6
    def test_extreme_parameters_stay_clamped_and_closed(self):
        # This grid straddles the plateau edge so both clamp ends are actually reached;
        # the reachability is asserted below rather than assumed.
        rows, columns = np.indices((3, 5))
        x = -37_500. + 15_000. * columns
        z = 30_000. * rows
        parameters = RefinedClimateParameters(windward_gain_m=1e6, lee_loss_m=1e6,
                                              max_windward_gain=1e6, min_lee_retention=1e-6)
        result = sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler=plateau_sampler)
        monthly, annual = result["monthly_precipitation_mm"], result["annual_precipitation_mm"]
        target = result["annual_precipitation_target_mm"]
        # The clamped §4.4 target is exactly inside the declared interval...
        self.assertTrue((target >= 100.).all() and (target <= 3200.).all())
        self.assertTrue((target == 3200.).any())
        self.assertTrue((target == 100.).any())
        # ...and the realized annual is the monthly sum, one ulp from that target at worst.
        self.assertArrayEqual(annual, monthly.sum(axis=0))
        self.assertLessEqual(float(np.abs(annual - target).max()), MONTHLY_CLOSURE_ATOL_MM)
        self.assertTrue(np.isfinite(monthly).all() and (monthly >= 0.).all())
        self.assertTrue(np.isfinite(annual).all())
        self.assertGreaterEqual(float(annual.min()), 100. - MONTHLY_CLOSURE_ATOL_MM)
        self.assertLessEqual(float(annual.max()), 3200. + MONTHLY_CLOSURE_ATOL_MM)
        # The identity path closes bit for bit, with no repair needed at all.
        identity_result = sample_climate_v2(SEED, x, z, parameters=refinement_off(),
                                            elevation_sampler=plateau_sampler)
        self.assertArrayEqual(identity_result["monthly_precipitation_mm"].sum(axis=0),
                              identity_result["annual_precipitation_mm"])
        self.assertArrayEqual(identity_result["annual_precipitation_mm"],
                              identity_result["annual_precipitation_target_mm"])

    # ---------------------------------------------------------------- §7.7 (intermediate)
    def test_bio_relations_hold_after_refinement(self):
        x, z = climate_grid(4, 5)
        parameters = RefinedClimateParameters(windward_gain_m=8., lee_loss_m=8.)
        result = sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler=plateau_sampler)
        self.assertTrue(result["orographic_applied"])
        temperature, precipitation = result["monthly_temperature_c"], result["monthly_precipitation_mm"]
        expected = np.stack((temperature.mean(axis=0), temperature.std(axis=0) * 100.,
                             precipitation.sum(axis=0),
                             precipitation.std(axis=0) / precipitation.mean(axis=0) * 100.))
        np.testing.assert_array_equal(result["BIO1_4_12_15"], expected)
        np.testing.assert_array_equal(result["BIO1_4_12_15"][2], result["annual_precipitation_mm"])
        np.testing.assert_array_equal(result["BIO1_4_12_15"][2], precipitation.sum(axis=0))

    # ---------------------------------------------------------------- §4.3
    def test_elevation_end_to_end_and_pure_sampler(self):
        x, z = climate_grid(2, 3)
        parameters = RefinedClimateParameters()

        def delegating_sampler(x_m, z_m):
            return coarse_condition_field(SEED, x_m, z_m)[0]

        default = sample_climate_v2(SEED, x, z, parameters=parameters)
        explicit = sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler=delegating_sampler)
        self.assertEqual(default["elevation_source"], "coarse_condition_field_height_m")
        self.assertEqual(explicit["elevation_source"], "caller_supplied_pure_sampler")
        self.assertArrayEqual(default["elevation_m"], explicit["elevation_m"])
        self.assertArrayEqual(default["monthly_precipitation_mm"], explicit["monthly_precipitation_mm"])
        self.assertArrayEqual(default["precipitation_multiplier"], explicit["precipitation_multiplier"])
        # The public ridge is pure: same input, same bits, in any order and any shape.
        first = ridge_height(SEED, x, z, parameters=parameters, elevation_sampler=analytic_sampler)
        other = ridge_height(SEED, x + 50_000., z + 90_000., parameters=parameters,
                             elevation_sampler=analytic_sampler)
        self.assertArrayEqual(ridge_height(SEED, x, z, parameters=parameters,
                                          elevation_sampler=analytic_sampler), first)
        self.assertArrayEqual(ridge_height(SEED, x[::-1, ::-1], z[::-1, ::-1], parameters=parameters,
                                          elevation_sampler=analytic_sampler), first[::-1, ::-1])
        self.assertArrayEqual(ridge_height(SEED, x + 50_000., z + 90_000., parameters=parameters,
                                          elevation_sampler=analytic_sampler), other)
        self.assertEqual(float(np.asarray(ridge_height(SEED, x[1, 1], z[1, 1], parameters=parameters,
                                                      elevation_sampler=analytic_sampler))), float(first[1, 1]))
        with self.assertRaises(ValueError):
            sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler="not callable")

    def test_explicit_elevation_takes_priority_for_the_base_layer(self):
        x, z = climate_grid(2, 3)
        parameters = refinement_off()
        low = sample_climate_v2(SEED, x, z, 0., parameters=parameters, elevation_sampler=plateau_sampler)
        high = sample_climate_v2(SEED, x, z, 1000., parameters=parameters, elevation_sampler=plateau_sampler)
        self.assertEqual(low["elevation_source"], "explicit_elevation_m")
        self.assertTrue((np.asarray(high["elevation_m"]) == 1000.).all())
        self.assertFalse(np.array_equal(low["monthly_temperature_c"], high["monthly_temperature_c"]))
        # v1 rainfall is structurally terrain blind; that is exactly why v2 adds a sampler.
        self.assertArrayEqual(low["monthly_precipitation_mm"], high["monthly_precipitation_mm"])

    # ---------------------------------------------------------------- §5
    def test_v2_identity_naming_and_parameter_coverage(self):
        from dataclasses import asdict

        parameters = RefinedClimateParameters()
        record = asdict(parameters)
        for name in ("base", "latitude_period_m", "orographic_scale_m", "ridge_smoothing_taps",
                     "windward_gain_m", "lee_loss_m", "max_windward_gain", "min_lee_retention",
                     "annual_precipitation_min_mm", "annual_precipitation_max_mm"):
            self.assertIn(name, record)
        for name in asdict(NoiseClimateParameters()):
            self.assertIn(name, record["base"])
        self.assertEqual(parameters.identity_sha256,
                         identity({}, {"schema": CLIMATE_SCHEMA, "parameters": record}))
        self.assertEqual(parameters.identity_sha256, RefinedClimateParameters().identity_sha256)
        for skill in ({"windward_gain_m": 6.}, {"lee_loss_m": 6.}, {"orographic_scale_m": 30_000.},
                      {"latitude_period_m": 960_000.}, {"min_lee_retention": .5},
                      {"ridge_smoothing_taps": 5}, {"annual_precipitation_max_mm": 2000.}):
            changed = RefinedClimateParameters(**skill)
            self.assertNotEqual(changed.identity_sha256, parameters.identity_sha256)
            self.assertEqual(changed.base_parameter_identity_sha256, V1_IDENTITY_SHA256)
        self.assertEqual(RefinedClimateParameters(base=NoiseClimateParameters(climate_scale_m=300_000.)).base_parameter_identity_sha256,
                         NoiseClimateParameters(climate_scale_m=300_000.).identity_sha256)
        result = sample_climate_v2(SEED, 1000., 2000.)
        self.assertEqual(result["schema"], CLIMATE_SCHEMA)
        self.assertEqual(result["semantics"], SEMANTICS)
        self.assertEqual(result["band_structure_semantics"], BAND_STRUCTURE_SEMANTICS)
        self.assertEqual(result["parameter_identity_sha256"], parameters.identity_sha256)
        self.assertNotIn("latitude_deg", result)
        self.assertIn("latitude_band_norm", result)
        bands = result["wind_bearing_bands"]
        self.assertEqual(bands["semantics"], BAND_STRUCTURE_SEMANTICS)
        self.assertEqual([tuple(unit) for unit in bands["units"]], list(WIND_BAND_UNITS))
        grid, metadata = grid_rainfall_v2(SEED, origin_xz_m=[0., 0.], shape_zx=(2, 3), spacing_m=30_000.,
                                          time_edges_s=[0., 3600.], parameters=parameters,
                                          elevation_sampler=analytic_sampler)
        self.assertEqual(metadata["schema"], RAINFALL_SCHEMA)
        self.assertEqual(metadata["parameter_identity_sha256"], parameters.identity_sha256)
        self.assertEqual(metadata["base_parameter_identity_sha256"], V1_IDENTITY_SHA256)
        self.assertEqual(metadata["spatial_mean"], "equal_area_midpoint_subcells")
        self.assertEqual(metadata["semantics"], SEMANTICS)
        self.assertEqual(metadata["source_identity_sha256"], grid.source_sha256)
        unrefined, unrefined_metadata = grid_rainfall_v2(
            SEED, origin_xz_m=[0., 0.], shape_zx=(2, 3), spacing_m=30_000., time_edges_s=[0., 3600.],
            parameters=refinement_off(), elevation_sampler=analytic_sampler)
        self.assertNotEqual(unrefined_metadata["source_identity_sha256"], metadata["source_identity_sha256"])
        self.assertFalse(np.array_equal(unrefined.rain_mm_h, grid.rain_mm_h))

    # ---------------------------------------------------------------- §3.2 row 1
    def test_temperature_row_shifts_every_month_by_one_band_offset(self):
        x, z = climate_grid(3, 4)
        parameters = RefinedClimateParameters(latitude_temperature_range_c=-12.)
        refined = sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler=flat_sampler)
        off = sample_climate_v2(SEED, x, z, parameters=refinement_off(), elevation_sampler=flat_sampler)
        temperature = np.asarray(refined["monthly_temperature_c"])
        base = np.asarray(off["monthly_temperature_c"])
        band = np.asarray(refined["latitude_band_norm"])
        offset = np.asarray(refined["latitude_temperature_offset_c"])
        # One and the same offset for all twelve months, and it is the signed band offset.
        self.assertArrayEqual(offset, band * -12.)
        difference = temperature - base
        # The shift is one and the same offset for every month, not twelve different ones.
        np.testing.assert_array_equal(difference, np.broadcast_to(difference[0], difference.shape))
        # ...and it agrees with the reported signed band offset to within one rounding.
        np.testing.assert_allclose(difference, np.broadcast_to(offset, difference.shape), rtol=0., atol=1e-12)
        # A constant shift moves the annual mean and BIO1 but not the seasonal amplitude.
        np.testing.assert_allclose(np.asarray(refined["BIO1_4_12_15"][0]) - np.asarray(off["BIO1_4_12_15"][0]),
                                   offset, rtol=0., atol=1e-12)
        # A constant shift moves the annual mean and BIO1 but not the seasonal amplitude:
        # BIO4 is mathematically unchanged, but the running sum behind it is not, so it can
        # move by rounding noise at the few-ulp level.
        np.testing.assert_allclose(np.asarray(refined["BIO1_4_12_15"][1]),
                                   np.asarray(off["BIO1_4_12_15"][1]), rtol=0., atol=1e-10)
        self.assertArrayEqual(refined["monthly_precipitation_mm"], off["monthly_precipitation_mm"])
        # The row's off switch is structural: with `0.` the reported offset is exactly zero
        # and the returned months are still the base values bit for bit.
        self.assertTrue((np.asarray(off["latitude_temperature_offset_c"]) == 0.).all())
        self.assertArrayEqual(np.asarray(off["monthly_temperature_c"]),
                              np.asarray(sample_climate(SEED, x, z, np.zeros_like(x))["monthly_temperature_c"]))

    def test_pole_side_is_cooled_when_the_row_is_on(self):
        parameters = RefinedClimateParameters()
        pole_z = LATITUDE_PERIOD_M / 4.
        equator_z = -LATITUDE_PERIOD_M / 4.
        pole = sample_climate_v2(SEED, 0., pole_z, parameters=parameters, elevation_sampler=flat_sampler)
        equator = sample_climate_v2(SEED, 0., equator_z, parameters=parameters, elevation_sampler=flat_sampler)
        off = RefinedClimateParameters(latitude_temperature_range_c=0.)
        pole_off = sample_climate_v2(SEED, 0., pole_z, parameters=off, elevation_sampler=flat_sampler)
        equator_off = sample_climate_v2(SEED, 0., equator_z, parameters=off, elevation_sampler=flat_sampler)
        self.assertEqual(float(pole["latitude_band_norm"]), 1.)
        self.assertEqual(float(equator["latitude_band_norm"]), -1.)
        self.assertLess(float(pole["BIO1_4_12_15"][0]), float(pole_off["BIO1_4_12_15"][0]))
        self.assertGreater(float(equator["BIO1_4_12_15"][0]), float(equator_off["BIO1_4_12_15"][0]))
        self.assertAlmostEqual(float(pole["BIO1_4_12_15"][0]) - float(pole_off["BIO1_4_12_15"][0]),
                               -parameters.latitude_temperature_range_c * -1., delta=1e-12)

    # ---------------------------------------------------------------- §3.2 row 2
    def test_band_precipitation_row_is_off_by_default_and_signed_when_on(self):
        # A whole period of z, so the band coordinate really reaches its +-1 extremes.
        z = np.linspace(0., LATITUDE_PERIOD_M, 9).reshape(-1, 1)
        x = np.zeros_like(z)
        default = RefinedClimateParameters()
        self.assertEqual(default.latitude_precipitation_gain, 0.)
        off = sample_climate_v2(SEED, x, z, parameters=default, elevation_sampler=flat_sampler)
        self.assertTrue((np.asarray(off["latitude_precipitation_multiplier"]) == 1.).all())
        on = RefinedClimateParameters(latitude_precipitation_gain=.5)
        wet = sample_climate_v2(SEED, x, z, parameters=on, elevation_sampler=flat_sampler)
        multiplier = np.asarray(wet["latitude_precipitation_multiplier"])
        band = np.asarray(wet["latitude_band_norm"])
        self.assertArrayEqual(multiplier, 1. + .5 * np.cos(np.pi * band))
        # Dry-wet-dry in the declared convention: `1+gain` at the band zero crossing,
        # exactly `1-gain` at both `latitude_norm = +-1` extremes (pole and equator).
        self.assertAlmostEqual(float(multiplier[np.abs(band) < 1e-3].max()), 1.5, delta=1e-6)
        extremes = np.abs(band) > .9995
        self.assertTrue(extremes.any())
        self.assertAlmostEqual(float(multiplier[extremes].min()), .5, delta=1e-6)
        self.assertAlmostEqual(float(multiplier[extremes].max()), .5, delta=1e-6)
        # Wet in the middle of the period, dry at both ends, relative to the base layer.
        wetter = np.abs(band) < .1
        self.assertGreater(float(wet["annual_precipitation_mm"][wetter].min()),
                           float(off["annual_precipitation_mm"][wetter].min()))
        self.assertLess(float(wet["annual_precipitation_mm"][extremes].max()),
                        float(off["annual_precipitation_mm"][extremes].max()))
        # Same row, same shape: the multiplier is a pure function of the band coordinate
        # alone, so it must not depend on x or on the query window.
        rows = np.arange(3).reshape(-1, 1) * 30_000.
        columns = np.arange(4).reshape(1, -1) * 30_000.
        grid_x, grid_z = columns + np.zeros((3, 4)), rows + np.zeros((3, 4))
        grid_band = np.asarray(sample_climate_v2(SEED, grid_x, grid_z, parameters=on,
                                                elevation_sampler=flat_sampler)["latitude_band_norm"])
        grid_multiplier = np.asarray(sample_climate_v2(SEED, grid_x, grid_z, parameters=on,
                                                      elevation_sampler=flat_sampler)["latitude_precipitation_multiplier"])
        self.assertArrayEqual(grid_multiplier, 1. + .5 * np.cos(np.pi * grid_band))
        # The multiplier is the same on every column of a given row: no x dependence at all.
        self.assertArrayEqual(grid_multiplier, np.broadcast_to(grid_multiplier[:, :1], grid_multiplier.shape))

    # ---------------------------------------------------------------- §6
    def test_snow_line_matches_the_closed_form_of_the_temperature_column(self):
        x, z = climate_grid(3, 5)
        parameters = RefinedClimateParameters()
        diagnostic = snow_line(SEED, x, z, parameters=parameters)
        climate = sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler=flat_sampler)
        temperature = np.asarray(climate["monthly_temperature_c"])
        lapse = parameters.base.lapse_rate_c_per_m
        expected = np.where(temperature > 0., -temperature / lapse, 0.)
        self.assertArrayEqual(diagnostic["monthly_first_freezing_elevation_m"], expected)
        self.assertArrayEqual(diagnostic["seasonal_snow_line_m"], expected.min(axis=0))
        self.assertArrayEqual(diagnostic["perennial_snow_line_m"], expected.max(axis=0))
        self.assertEqual(diagnostic["snow_line_criterion"],
                         "monthly_mean_temperature_below_zero_celsius")
        self.assertEqual(float(diagnostic["lapse_rate_c_per_m"]), lapse)
        self.assertEqual(diagnostic["schema"], SNOW_LINE_SCHEMA)
        self.assertEqual(diagnostic["parameter_identity_sha256"], parameters.identity_sha256)
        self.assertEqual(diagnostic["base_parameter_identity_sha256"], V1_IDENTITY_SHA256)
        self.assertEqual(diagnostic["band_structure_semantics"], BAND_STRUCTURE_SEMANTICS)
        self.assertTrue((np.asarray(diagnostic["seasonal_snow_line_m"])
                         <= np.asarray(diagnostic["perennial_snow_line_m"])).all())
        self.assertTrue((np.asarray(diagnostic["seasonal_snow_line_m"]) >= 0.).all())
        # The threshold really is the crossing: at that elevation the month is at 0 C.
        column = np.asarray(diagnostic["monthly_first_freezing_elevation_m"])
        month, iz, ix = 3, 1, 2
        height = float(column[month, iz, ix])
        at_snow_line = sample_climate_v2(SEED, float(x[iz, ix]), float(z[iz, ix]),
                                        height, parameters=parameters, elevation_sampler=flat_sampler)
        self.assertAlmostEqual(float(at_snow_line["monthly_temperature_c"][month]), 0., delta=1e-9)
        # A zero lapse rate means no month can freeze at any elevation.
        flat_lapse = RefinedClimateParameters(base=NoiseClimateParameters(lapse_rate_c_per_m=0.))
        never = snow_line(SEED, x, z, parameters=flat_lapse)
        self.assertTrue(np.isinf(np.asarray(never["seasonal_snow_line_m"])).all())

    def test_snow_line_ignores_the_precipitation_row(self):
        x, z = climate_grid(2, 4)
        dry = snow_line(SEED, x, z, parameters=RefinedClimateParameters(latitude_precipitation_gain=0.))
        wet = snow_line(SEED, x, z, parameters=RefinedClimateParameters(latitude_precipitation_gain=.9))
        for name in ("monthly_first_freezing_elevation_m", "seasonal_snow_line_m",
                     "perennial_snow_line_m"):
            self.assertArrayEqual(dry[name], wet[name])
        # ...and the temperature row does move it, so the diagnostic is not a constant.
        warm = snow_line(SEED, x, z, parameters=RefinedClimateParameters(latitude_temperature_range_c=0.))
        self.assertFalse(np.array_equal(np.asarray(warm["seasonal_snow_line_m"]),
                                        np.asarray(dry["seasonal_snow_line_m"])))

    def test_pole_band_snow_line_sits_below_the_equator_band(self):
        parameters = RefinedClimateParameters()
        pole = snow_line(SEED, 0., LATITUDE_PERIOD_M / 4., parameters=parameters)
        equator = snow_line(SEED, 0., -LATITUDE_PERIOD_M / 4., parameters=parameters)
        self.assertLess(float(pole["seasonal_snow_line_m"]), float(equator["seasonal_snow_line_m"]))

    # ---------------------------------------------------------------- §7 full suite (P4.5)
    def test_off_state_replays_every_v1_key_bit_for_bit(self):
        """§7.1, full: with every row off, every key v1 returns must be bit identical."""
        x, z = climate_grid(4, 5)
        elevation = np.linspace(0., 3000., x.size).reshape(x.shape)
        parameters = refinement_off()
        v1 = sample_climate(SEED, x, z, elevation, parameters=parameters.base)
        v2 = sample_climate_v2(SEED, x, z, elevation, parameters=parameters,
                               elevation_sampler=flat_sampler)
        for key in ("monthly_temperature_c", "monthly_precipitation_mm", "BIO1_4_12_15",
                    "thermal_strength", "moisture_strength", "continentality_strength"):
            self.assertArrayEqual(v2[key], v1[key])
            # Every one of the twelve months of the two monthly keys, not just the stack.
            if key.endswith("_c") or key.endswith("_mm"):
                for month in range(12):
                    self.assertArrayEqual(np.asarray(v2[key])[month], np.asarray(v1[key])[month])
        self.assertEqual(v2["semantics"], SEMANTICS)
        self.assertNotEqual(v2["schema"], "metric-noise-climate-v1")
        self.assertEqual(v2["parameter_identity_sha256"], parameters.identity_sha256)

    def test_multiplier_is_the_single_product_of_both_refinement_rows(self):
        """The composed multiplier must be exactly row1_multiplier * row2_multiplier."""
        x, z = climate_grid(3, 4)
        cases = (RefinedClimateParameters(latitude_precipitation_gain=.4, windward_gain_m=0.,
                                          lee_loss_m=0., max_windward_gain=0., min_lee_retention=1.),
                 RefinedClimateParameters(latitude_precipitation_gain=.4),
                 RefinedClimateParameters(latitude_precipitation_gain=.4, windward_gain_m=9.))
        for parameters in cases:
            result = sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler=plateau_sampler)
            rows = (np.asarray(result["latitude_precipitation_multiplier"])
                    * np.asarray(sample_climate_v2(
                        SEED, x, z,
                        parameters=RefinedClimateParameters(
                            latitude_precipitation_gain=0., windward_gain_m=parameters.windward_gain_m,
                            lee_loss_m=parameters.lee_loss_m, max_windward_gain=parameters.max_windward_gain,
                            min_lee_retention=parameters.min_lee_retention,
                            orographic_scale_m=parameters.orographic_scale_m),
                        elevation_sampler=plateau_sampler)["precipitation_multiplier"]))
            self.assertArrayEqual(result["precipitation_multiplier"], rows)

    def test_annual_clamp_is_inclusive_at_both_ends(self):
        """§7.6, full: the declared interval is reached exactly, and never left."""
        rows, columns = np.indices((3, 5))
        x = -37_500. + 15_000. * columns
        z = 30_000. * rows
        for parameters in (RefinedClimateParameters(windward_gain_m=1e6, lee_loss_m=1e6,
                                                    max_windward_gain=1e6, min_lee_retention=1e-6),
                           RefinedClimateParameters(latitude_precipitation_gain=1., windward_gain_m=1e6,
                                                    max_windward_gain=1e6),
                           RefinedClimateParameters(windward_gain_m=0., lee_loss_m=1e6,
                                                    min_lee_retention=1e-6)):
            result = sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler=plateau_sampler)
            target = np.asarray(result["annual_precipitation_target_mm"])
            annual = np.asarray(result["annual_precipitation_mm"])
            monthly = np.asarray(result["monthly_precipitation_mm"])
            self.assertTrue((target >= parameters.annual_precipitation_min_mm).all())
            self.assertTrue((target <= parameters.annual_precipitation_max_mm).all())
            self.assertArrayEqual(annual, monthly.sum(axis=0))
            self.assertLessEqual(float(np.abs(annual - target).max()), MONTHLY_CLOSURE_ATOL_MM)
            self.assertTrue(np.isfinite(monthly).all() and (monthly >= 0.).all())

    def test_bio_self_consistency_across_all_states(self):
        """§7.7, full: v1's BIO definitions must hold off, partial and extreme."""
        x, z = climate_grid(4, 5)
        states = (refinement_off(), RefinedClimateParameters(),
                  RefinedClimateParameters(latitude_precipitation_gain=.6, windward_gain_m=9., lee_loss_m=9.),
                  RefinedClimateParameters(windward_gain_m=1e6, lee_loss_m=1e6,
                                           max_windward_gain=1e6, min_lee_retention=1e-6))
        for parameters in states:
            result = sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler=plateau_sampler)
            temperature = np.asarray(result["monthly_temperature_c"])
            precipitation = np.asarray(result["monthly_precipitation_mm"])
            bio = np.asarray(result["BIO1_4_12_15"])
            self.assertArrayEqual(bio[0], temperature.mean(axis=0))
            np.testing.assert_allclose(bio[1], temperature.std(axis=0) * 100., rtol=0., atol=1e-9)
            self.assertArrayEqual(bio[2], precipitation.sum(axis=0))
            self.assertArrayEqual(bio[2], np.asarray(result["annual_precipitation_mm"]))
            np.testing.assert_allclose(bio[3], precipitation.std(axis=0) / precipitation.mean(axis=0) * 100.,
                                       rtol=0., atol=1e-9)

    def test_documented_arithmetic_limits_are_stated_in_the_module(self):
        """The limits this module accepts must be written down, not silent."""
        source = (Path(__file__).resolve().parents[1]
                  / "terrain_pipeline/surface_rivers/metric_climate_refinement.py").read_text(encoding="utf-8")
        for phrase in ("not bit for bit", "one unit in the last place",
                       "synthetic band structure, not a measured climatology"):
            self.assertIn(phrase, source)
        # Contract §3.3 requires the disclosure in the returned payload as well.
        result = sample_climate_v2(SEED, 1_000., 2_000.)
        self.assertEqual(result["band_structure_semantics"],
                         "synthetic band structure, not a measured climatology")

    def test_latitude_periodicity_is_float_level_not_bitwise(self):
        """The recorded limit, asserted as a fact: periodicity is not bit for bit."""
        base = 1_234.5678
        same_period = float(latitude_norm(SEED, base))
        shifted = float(latitude_norm(SEED, base + 7 * LATITUDE_PERIOD_M))
        self.assertAlmostEqual(shifted, same_period, delta=4e-14)
        # The reduced phase keeps a large multiplier accurate to the few-ulp level only:
        # this is the documented limit, so the tolerance below is deliberately not 1e-15.
        far = float(latitude_norm(SEED, base + 1000 * LATITUDE_PERIOD_M))
        self.assertAlmostEqual(far, same_period, delta=1e-12)
        # Away from the round values, equality is not exact; that is the documented limit.
        self.assertNotEqual(latitude_norm(SEED, 0.3 * LATITUDE_PERIOD_M),
                            latitude_norm(SEED, 0.3 * LATITUDE_PERIOD_M + 3 * LATITUDE_PERIOD_M))

    def test_annual_fields_differ_by_at_most_one_unit_in_the_last_place(self):
        """§7.6 limit: the clamped target and the realized monthly sum differ by <= 1 ulp."""
        rows, columns = np.indices((3, 6))
        x = -45_000. + 15_000. * columns
        z = 30_000. * rows
        parameters = RefinedClimateParameters(windward_gain_m=1e6, lee_loss_m=1e6,
                                              max_windward_gain=1e6, min_lee_retention=1e-6)
        result = sample_climate_v2(SEED, x, z, parameters=parameters, elevation_sampler=plateau_sampler)
        target = np.asarray(result["annual_precipitation_target_mm"])
        annual = np.asarray(result["annual_precipitation_mm"])
        self.assertTrue((target != annual).any(), "the repair must actually be exercised here")
        ulp = np.spacing(np.abs(target))
        self.assertTrue((np.abs(annual - target) <= ulp).all())
        # The off state needs no repair at all: both annuals are the same object values.
        calm = sample_climate_v2(SEED, x, z, parameters=refinement_off(), elevation_sampler=plateau_sampler)
        self.assertArrayEqual(calm["annual_precipitation_mm"], calm["annual_precipitation_target_mm"])
        self.assertFalse(np.asarray(calm["orographic_applied"]))

    def test_same_elevation_is_the_replay_precondition(self):
        """§7.1 precondition, made explicit: replay needs one shared elevation."""
        x, z = climate_grid(2, 3)
        parameters = refinement_off()
        elevation = np.linspace(0., 1500., x.size).reshape(x.shape)
        v1 = sample_climate(SEED, x, z, elevation, parameters=parameters.base)
        same = sample_climate_v2(SEED, x, z, elevation, parameters=parameters,
                                 elevation_sampler=flat_sampler)
        self.assertArrayEqual(same["monthly_temperature_c"], v1["monthly_temperature_c"])
        # A different elevation is a different lapse injection, so the temperatures differ:
        # this is the documented difference between "off" and "v1 defaulted", not a regression.
        other = sample_climate_v2(SEED, x, z, elevation + 500., parameters=parameters,
                                  elevation_sampler=flat_sampler)
        self.assertFalse(np.array_equal(np.asarray(other["monthly_temperature_c"]),
                                        np.asarray(v1["monthly_temperature_c"])))
        # Precipitation is elevation blind in both layers, so it stays put.
        self.assertArrayEqual(other["monthly_precipitation_mm"], v1["monthly_precipitation_mm"])

    # ---------------------------------------------------------------- validation
    def test_parameter_and_argument_validation(self):
        for broken in (dict(latitude_period_m=0.), dict(latitude_period_m=float("inf")),
                       dict(latitude_temperature_range_c=-61.), dict(latitude_temperature_range_c=61.),
                       dict(latitude_precipitation_gain=-.1), dict(latitude_precipitation_gain=1.5),
                       dict(orographic_scale_m=-1.), dict(windward_gain_m=-1.),
                       dict(lee_loss_m=float("nan")), dict(max_windward_gain=-1.),
                       dict(min_lee_retention=0.), dict(min_lee_retention=1.5),
                       dict(annual_precipitation_min_mm=3200., annual_precipitation_max_mm=100.),
                       dict(annual_precipitation_min_mm=0.), dict(ridge_smoothing_taps=2),
                       dict(ridge_smoothing_taps=0), dict(ridge_smoothing_taps=11),
                       dict(base="metric-noise-climate-v1")):
            with self.assertRaises(ValueError):
                RefinedClimateParameters(**broken)
        with self.assertRaises(ValueError):
            latitude_norm(SEED, 0., 0.)
        with self.assertRaises(ValueError):
            latitude_norm(SEED, float("nan"))
        with self.assertRaises(ValueError):
            latitude_norm("seed", 0.)
        with self.assertRaises(ValueError):
            sample_climate_v2(SEED, 0., 0., parameters=NoiseClimateParameters())
        with self.assertRaises(ValueError):
            sample_climate_v2(SEED, 0., 0., float("nan"))
        with self.assertRaises(ValueError):
            sample_climate_v2(SEED, 0., 0., parameters=RefinedClimateParameters(),
                              elevation_sampler=lambda x, z: np.full(np.broadcast(np.asarray(x), np.asarray(z)).shape, np.nan))
        for broken in (dict(spacing_m=0.), dict(spacing_m=float("inf")), dict(shape_zx=(2,)),
                       dict(shape_zx=(2, 2), spatial_subsamples=3), dict(shape_zx=(0, 2)),
                       dict(time_edges_s=[1., 1.]), dict(time_edges_s=[-1., 5.])):
            arguments = dict(origin_xz_m=[0., 0.], shape_zx=(2, 2), spacing_m=30_000.,
                             time_edges_s=[0., 3600.], elevation_sampler=analytic_sampler)
            arguments.update(broken)
            with self.assertRaises(ValueError):
                grid_rainfall_v2(SEED, **arguments)
        with self.assertRaises(ValueError):
            grid_rainfall_v2(SEED, origin_xz_m=[0., 0.], shape_zx=(4000, 4000), spacing_m=30_000.,
                             time_edges_s=[0., 3600., 7200.], elevation_sampler=analytic_sampler)


if __name__ == "__main__":
    unittest.main()
