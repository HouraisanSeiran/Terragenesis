"""External-behaviour tests for the G3 seasonal air adapter.

Scope of these tests: the **declared contract** of
`terrain_pipeline.environment_seasonal_air`, not the v2 climate physics (which
`tests/test_metric_climate_refinement.py` already owns and which this adapter does
not modify).

What is asserted, and why each one can fail
-------------------------------------------
1. no overclaim        the forbidden fields (PET, ET, snowpack, glacier, a real
                       latitude) are absent, so an absence is a declared answer
2. no re-derivation    `monthly_temperature_c` is **bit for bit** what
                       `sample_climate_v2` returns for the same arguments
3. honest derivations  annual mean / amplitude / freezing count agree with the
                       months they claim to come from
4. freezing from T     the count follows `monthly_temperature_c <= 0` and is
                       monotone in elevation through the lapse rate; it is not an
                       inverted per-month snow-line threshold
5. wind is bound       the returned bearing equals the v2 `wind_unit` **and** the
                       imported band table; a drift raises instead of guessing
6. shared band         temperature offset and wind come from one band coordinate —
                       declared synthetic compatibility, so the test only checks
                       that they share the coordinate, never that the circulation is
                       dynamically consistent
7. calendar is data    the year length and month edges are returned, not assumed
8. period integration  a full-year interval reproduces the annual_weights-weighted
                       mean of the months (the v1 convention), and is explicitly
                       *not* claimed to be the day-weighted annual mean
9. window/order free   permutation keeps the identity and places values correctly
10. hard rejections    off-grid, bad seed, oversized, falsy parameters, non-finite
                       sampler output, bad time edges
11. identity binding   coordinates, shape, elevation, sampler VALUES, kernel bytes
                       and this module's own bytes all enter the identity
12. bounded period     whole-year closed form; a huge span costs the same as a
                       day; unresolvable intervals and no-progress are rejected
13. peakeness budget   the declared period budget is peak bytes (list + stack)
14. snow-line source   the snow line has no elevation argument, so it cannot be
                       sampler-driven and must not be labelled DEM-driven

No test here requires a DEM, a network, a GPU or a compute slot. Every loop in
this file is bounded by a small constant.
"""

import math
import unittest

import numpy as np

from terrain_pipeline.climate_forcing import GRID_SPACING_M, INTERVAL_ALGORITHM, MAX_PERIOD_ENTRIES, MAX_POINTS, MAX_TIME_S, MIN_INTERVAL_ULPS, NOT_RETURNED, SOURCE_OF, UNITS, calendar, describe, period_peak_bytes, sample_seasonal_air
from terrain_pipeline.climate_forcing import WIND_BAND_NAMES, WIND_BAND_UNITS, WIND_POLAR_BAND_LIMIT, WIND_TRADE_BAND_LIMIT, RefinedClimateParameters, sample_climate_v2
from terrain_pipeline.climate_forcing import MONTH_CENTERS_S, MONTH_DAYS, YEAR_S

SEED = 20261020

#: z values chosen on the 30 m lattice so that each falls in a different wind band.
#: band norm = sin(2*pi*z/1_920_000); |norm| < .30 -> band 0, >= .70 -> band 2.
TRADE_Z_M = 0.          # norm 0.0    -> band 0
MID_Z_M = 160_020.      # norm ~+0.50 -> band 1
POLAR_Z_M = 240_000.    # norm ~+0.71 -> band 2


def flat_sampler(x_m, z_m):
    """No-terrain pure sampler: zero height everywhere."""
    shape = np.broadcast(np.asarray(x_m, np.float64), np.asarray(z_m, np.float64)).shape
    return np.zeros(shape, np.float64)


def ramp_sampler(height):
    """Pure constant-height sampler, independent of position."""
    def sampler(x_m, z_m):
        shape = np.broadcast(np.asarray(x_m, np.float64),
                             np.asarray(z_m, np.float64)).shape
        return np.full(shape, float(height), np.float64)
    return sampler


def nan_sampler(x_m, z_m):
    """A sampler that violates the finiteness contract."""
    shape = np.broadcast(np.asarray(x_m, np.float64), np.asarray(z_m, np.float64)).shape
    return np.full(shape, np.nan, np.float64)


def lattice(side_z=3, side_x=4, spacing=GRID_SPACING_M, z0=0.0, x0=0.0):
    rows, columns = np.indices((side_z, side_x))
    return x0 + columns * spacing, z0 + rows * spacing


class DeclarationTests(unittest.TestCase):
    def test_forbidden_fields_are_absent(self):
        x, z = lattice(2, 2)
        result = sample_seasonal_air(SEED, x, z)
        for name in NOT_RETURNED:
            self.assertNotIn(name, result, "%r must never be returned" % name)

    def test_describe_declares_what_it_will_not_answer(self):
        declared = describe()
        self.assertEqual(list(declared["not_returned"]), list(NOT_RETURNED))
        self.assertTrue(any("PET" in entry for entry in declared["never"]))
        self.assertTrue(any("moisture" in entry for entry in declared["never"]))
        self.assertIn("climate_forcing.sample_climate_v2",
                      "".join(declared["reused_entries"]))

    def test_max_seconds_is_declared_a_soft_check_not_a_hard_gate(self):
        """The budget must not claim to interrupt a kernel it cannot interrupt."""
        declared = describe()
        semantics = declared["max_seconds_semantics"].lower()
        self.assertIn("cannot interrupt", semantics)
        self.assertIn("soft", semantics)
        self.assertEqual(declared["max_seconds"], 60.0)
        self.assertTrue(any("hard interrupt" in entry for entry in declared["never"]))

    def test_no_temperature_index_pet_is_computed_here(self):
        # S5 owns temperature-index PET; a duplicate would be a second truth.
        declared = describe()
        self.assertFalse(any("potential_et" in key for key in declared["units"]))
        self.assertFalse(any("actual_et" in key for key in declared["units"]))

    def test_calendar_is_returned_as_data(self):
        declared = calendar()
        self.assertEqual(declared["days_per_year"], 365)
        self.assertEqual(declared["month_days"], [int(v) for v in MONTH_DAYS])
        self.assertAlmostEqual(declared["year_seconds"], float(YEAR_S), places=6)
        self.assertFalse(declared["leap_day_handled"])
        self.assertEqual(declared["epoch_seconds"], 0.0)

        result = sample_seasonal_air(SEED, *lattice(1, 1))
        self.assertEqual(result["calendar"]["year_seconds"], declared["year_seconds"])


class EquivalenceTests(unittest.TestCase):
    """The adapter must not introduce a second climate truth."""

    def test_temperature_is_bitwise_equal_to_sample_climate_v2(self):
        x, z = lattice(3, 4)
        parameters = RefinedClimateParameters()
        reference = sample_climate_v2(SEED, x, z, parameters=parameters,
                                      elevation_sampler=flat_sampler)
        result = sample_seasonal_air(SEED, x, z, parameters=parameters,
                                     elevation_sampler=flat_sampler)
        np.testing.assert_array_equal(
            result["monthly_temperature_c"],
            np.asarray(reference["monthly_temperature_c"]))
        np.testing.assert_array_equal(
            result["latitude_band_norm"], np.asarray(reference["latitude_band_norm"]))

    def test_annual_mean_equals_the_v2_bio1_of_the_same_months(self):
        x, z = lattice(3, 4)
        reference = sample_climate_v2(SEED, x, z, elevation_sampler=flat_sampler)
        result = sample_seasonal_air(SEED, x, z, elevation_sampler=flat_sampler)
        np.testing.assert_array_equal(
            result["annual_mean_temperature_c"],
            np.asarray(reference["BIO1_4_12_15"][0]))

    def test_annual_mean_is_unweighted_not_day_weighted(self):
        """The declared name must match the arithmetic actually performed.

        Asserted against the semantic field, not against prose casing: a review
        note is not a scientific claim and must not carry one.
        """
        result = sample_seasonal_air(SEED, *lattice(2, 3))
        months = result["monthly_temperature_c"]
        np.testing.assert_array_equal(result["annual_mean_temperature_c"],
                                      months.mean(axis=0))
        self.assertIn("unweighted", result["units"]["annual_mean_temperature_c"])
        semantics = result["identity"]["record"]["annual_mean_semantics"]
        self.assertIn("unweighted", semantics)
        self.assertIn("not day-weighted", semantics.lower())

    def test_amplitude_and_extreme_month_indices_agree_with_the_months(self):
        x, z = lattice(3, 4)
        result = sample_seasonal_air(SEED, x, z)
        months = result["monthly_temperature_c"]
        np.testing.assert_array_equal(
            result["seasonal_temperature_amplitude_c"],
            months.max(axis=0) - months.min(axis=0))
        for row, column in np.ndindex(*result["shape"]):
            series = months[:, row, column]
            self.assertEqual(int(result["coldest_month_index"][row, column]),
                             int(np.argmin(series)))
            self.assertEqual(int(result["warmest_month_index"][row, column]),
                             int(np.argmax(series)))


class FreezingTests(unittest.TestCase):
    def test_count_follows_the_temperature_threshold(self):
        x, z = lattice(2, 2)
        result = sample_seasonal_air(SEED, x, z)
        months = result["monthly_temperature_c"]
        expected = np.count_nonzero(months <= 0., axis=0)
        np.testing.assert_array_equal(result["freezing_month_count"], expected)

        frozen = result["monthly_at_or_below_freezing"]
        self.assertTrue(np.array_equal(frozen, months <= 0.))
        np.testing.assert_array_equal(result["has_freezing_month"],
                                      result["freezing_month_count"] > 0)
        np.testing.assert_array_equal(result["all_months_freezing"],
                                      result["freezing_month_count"] == 12)

    def test_count_bounds_and_derived_flags_are_exact(self):
        """No skip: the bounds and the two flags are exact for every point probed."""
        x, z = lattice(4, 5, z0=0.)
        result = sample_seasonal_air(SEED, x, z)
        count = result["freezing_month_count"]
        self.assertTrue(np.all(count >= 0))
        self.assertTrue(np.all(count <= 12))
        self.assertEqual(count.dtype, np.int64)
        np.testing.assert_array_equal(result["has_freezing_month"], count > 0)
        np.testing.assert_array_equal(result["all_months_freezing"], count == 12)
        # has_freezing_month False must mean every month is strictly above freezing.
        warm = ~result["has_freezing_month"]
        if warm.any():
            self.assertTrue(np.all(result["monthly_temperature_c"][:, warm] > 0.))

    def test_count_is_monotone_in_elevation_through_the_lapse_rate(self):
        x, z = lattice(1, 1)
        counts = []
        for elevation in (0., 1000., 2000., 3000., 4000., 5000., 6000., 8000.):
            result = sample_seasonal_air(SEED, x, z, elevation_m=elevation)
            counts.append(int(result["freezing_month_count"].item()))
        self.assertEqual(counts, sorted(counts),
                         "a negative lapse rate must not reduce the freezing count "
                         "as elevation rises")

    def test_count_is_not_an_inverted_snow_line_threshold(self):
        """Ask for the snow line and prove the count does not move because of it."""
        x, z = lattice(2, 2)
        without = sample_seasonal_air(SEED, x, z)
        with_line = sample_seasonal_air(SEED, x, z, include_snow_line=True)
        np.testing.assert_array_equal(without["freezing_month_count"],
                                      with_line["freezing_month_count"])
        np.testing.assert_array_equal(without["monthly_temperature_c"],
                                      with_line["monthly_temperature_c"])
        self.assertIsNone(without["snow_line"])
        self.assertIsNotNone(with_line["snow_line"])
        for key in ("seasonal_snow_line_m", "perennial_snow_line_m"):
            self.assertIn(key, with_line["snow_line"])


class SnowLineSemanticsTests(unittest.TestCase):
    """The snow line takes no elevation argument, so it cannot be sampler-driven."""

    def test_snow_line_does_not_follow_the_caller_elevation(self):
        """Temperature moves with elevation; the snow-line block must not."""
        x, z = lattice(1, 2)
        low = sample_seasonal_air(SEED, x, z, elevation_m=0., include_snow_line=True)
        high = sample_seasonal_air(SEED, x, z, elevation_m=3000., include_snow_line=True)
        self.assertFalse(np.array_equal(low["monthly_temperature_c"],
                                        high["monthly_temperature_c"]))
        for key in ("monthly_first_freezing_elevation_m",
                    "seasonal_snow_line_m", "perennial_snow_line_m"):
            np.testing.assert_array_equal(low["snow_line"][key],
                                          high["snow_line"][key])

    def test_snow_line_semantics_are_stated_verbatim(self):
        result = sample_seasonal_air(SEED, *lattice(1, 1), include_snow_line=True)
        semantics = result["identity"]["record"]["snow_line_elevation_semantics"]
        self.assertIn("no elevation argument", semantics)
        self.assertIn("NOT driven by the caller", semantics)

    def test_snow_line_source_is_a_pass_through_not_an_elevation_driver(self):
        result = sample_seasonal_air(SEED, *lattice(1, 2), elevation_m=1200.,
                                     include_snow_line=True)
        self.assertEqual(result["elevation_source"], "explicit_elevation_m")
        source = result["sources"]["snow_line"]["source"]
        self.assertIn("pass-through", source)
        note = result["sources"]["snow_line"]["note"]
        self.assertIn("NOT driven by the caller's elevation sampler", note)

    def test_snow_line_is_absent_when_not_requested(self):
        result = sample_seasonal_air(SEED, *lattice(1, 1))
        self.assertIsNone(result["snow_line"])
        self.assertFalse(result["identity"]["record"]["snow_line_requested"])


class WindTests(unittest.TestCase):
    def test_returned_bearing_matches_the_imported_band_table(self):
        x = np.array([[0., 30.], [0., 30.]])
        z = np.array([[TRADE_Z_M, MID_Z_M], [POLAR_Z_M, MID_Z_M]])
        result = sample_seasonal_air(SEED, x, z)
        units = np.asarray(WIND_BAND_UNITS, np.int64)
        index = result["wind_band_index"]
        np.testing.assert_array_equal(result["wind_bearing_x"], units[index, 0])
        np.testing.assert_array_equal(result["wind_bearing_z"], units[index, 1])

    def test_band_index_uses_the_declared_limits(self):
        x = np.array([[0., 0., 0., 0.]])
        z = np.array([[0., 100_020., 160_020., 240_000.]])
        result = sample_seasonal_air(SEED, x, z)
        band = result["latitude_band_norm"]
        magnitude = np.abs(band)
        expected = np.where(magnitude < WIND_TRADE_BAND_LIMIT, 0,
                            np.where(magnitude < WIND_POLAR_BAND_LIMIT, 1, 2))
        np.testing.assert_array_equal(result["wind_band_index"], expected)

    def test_three_named_bands_are_all_reachable(self):
        x = np.array([[0., 0., 0.]])
        z = np.array([[TRADE_Z_M, MID_Z_M, POLAR_Z_M]])
        result = sample_seasonal_air(SEED, x, z)
        names = list(result["wind_band_name"].reshape(-1))
        self.assertEqual(names, list(WIND_BAND_NAMES))

    def test_temperature_offset_and_wind_share_one_band_coordinate(self):
        """Declared synthetic compatibility only: same band, same offset, same bearing.

        This proves the two rows read the *same* coordinate. It is deliberately not
        a claim that a synthetic band is a dynamically consistent circulation.
        """
        x, z = lattice(3, 4, z0=0.)
        result = sample_seasonal_air(SEED, x, z)
        band = result["latitude_band_norm"]
        parameters = RefinedClimateParameters()
        np.testing.assert_allclose(
            result["latitude_temperature_offset_c"],
            band * parameters.latitude_temperature_range_c, rtol=0.0, atol=1e-12)
        magnitude = np.abs(band)
        expected = np.where(magnitude < WIND_TRADE_BAND_LIMIT, 0,
                            np.where(magnitude < WIND_POLAR_BAND_LIMIT, 1, 2))
        np.testing.assert_array_equal(result["wind_band_index"], expected)

    def test_bearing_is_a_unit_vector(self):
        x, z = lattice(3, 4, z0=0.)
        result = sample_seasonal_air(SEED, x, z)
        norm = (result["wind_bearing_x"].astype(np.int64) ** 2
                + result["wind_bearing_z"].astype(np.int64) ** 2)
        np.testing.assert_array_equal(norm, np.ones_like(norm))


class PeriodTests(unittest.TestCase):
    def test_full_year_interval_reproduces_the_annual_weights_mean(self):
        x, z = lattice(2, 3)
        result = sample_seasonal_air(SEED, x, z, time_edges_s=[0., YEAR_S])
        months = result["monthly_temperature_c"]

        gaps = np.diff(np.r_[MONTH_CENTERS_S, MONTH_CENTERS_S[0] + YEAR_S])
        weights = .5 * (gaps + np.roll(gaps, 1))
        expected = np.tensordot(weights, months, axes=(0, 0)) / YEAR_S

        np.testing.assert_allclose(result["period_mean_temperature_c"][0],
                                   expected, rtol=1e-12, atol=1e-12)

    def test_period_shape_and_declaration(self):
        x, z = lattice(2, 2)
        result = sample_seasonal_air(SEED, x, z, time_edges_s=[0., 86400., 172800.])
        self.assertEqual(result["period_mean_temperature_c"].shape, (2, 2, 2))
        self.assertEqual(result["time_edges_s"].tolist(), [0., 86400., 172800.])
        record = result["identity"]["record"]["period"]
        # Asserted on the algorithm identity and record structure, never on the
        # casing of a prose sentence.
        self.assertEqual(record["algorithm"], INTERVAL_ALGORITHM)
        self.assertEqual(describe()["interval_algorithm"], INTERVAL_ALGORITHM)
        self.assertEqual(set(record),
                         {"algorithm", "time_edges_s", "declaration", "cost_bound"})
        self.assertTrue(record["declaration"].strip())
        self.assertTrue(record["cost_bound"].strip())

    def test_huge_span_costs_the_same_as_a_day(self):
        """Whole years are closed-form, so a billion-year span is O(1) work.

        The interval sits just below the declared time domain and is wide enough to
        be resolvable; a whole number of years must reproduce the annual-weights
        mean exactly, which is what proves no remainder loop ran over the span.
        """
        x, z = lattice(1, 1)
        whole_years = float(int(31_000 * 365)) * 86400.
        edges = [MAX_TIME_S - whole_years, MAX_TIME_S]
        result = sample_seasonal_air(SEED, x, z, time_edges_s=edges)
        reference = sample_seasonal_air(SEED, x, z,
                                        time_edges_s=[0., YEAR_S])
        np.testing.assert_allclose(result["period_mean_temperature_c"][0],
                                   reference["period_mean_temperature_c"][0],
                                   rtol=1e-9, atol=1e-9)

    def test_equal_remainder_at_different_epochs_gives_the_same_mean(self):
        """Only the sub-year remainder matters, never the absolute date.

        This is the cancellation guard: the same phase one thousand years later
        must give the same mean to summing-order accuracy, not to a difference of
        two ~1e10 antiderivatives.
        """
        x, z = lattice(1, 1)
        short = sample_seasonal_air(SEED, x, z, time_edges_s=[0., 86400.])
        shifted = sample_seasonal_air(
            SEED, x, z, time_edges_s=[YEAR_S * 1000., YEAR_S * 1000. + 86400.])
        np.testing.assert_allclose(shifted["period_mean_temperature_c"],
                                   short["period_mean_temperature_c"],
                                   rtol=1e-12, atol=0.)

    def test_same_phase_at_large_epoch_matches_the_phase_at_zero(self):
        """A mid-year window at a large epoch equals the same window near zero.

        The offsets are built as exact multiples of the unit in the last place at
        the large magnitude, so both calls use **bit-identical** start and end
        offsets. That makes this a test of the integration structure rather than a
        test of time representation: with an antiderivative difference the two
        antiderivatives would be ~1e12 in size and the subtraction would lose
        ~1e-10 relative accuracy, which the assertion below would catch.
        """
        x, z = lattice(1, 1)
        far_years = 30_000
        far_base = YEAR_S * float(far_years)
        self.assertLess(far_base, MAX_TIME_S)
        quantum = float(np.spacing(far_base))
        offset = round(YEAR_S * .5 / quantum) * quantum
        width = round(86400. * 3. / quantum) * quantum

        near = sample_seasonal_air(SEED, x, z, time_edges_s=[offset, offset + width])
        far = sample_seasonal_air(
            SEED, x, z,
            time_edges_s=[far_base + offset, far_base + offset + width])
        # Precondition of the test: the phases really are identical.
        self.assertEqual(math.fmod(far_base + offset, YEAR_S), offset)
        self.assertEqual(math.fmod(far_base + offset + width, YEAR_S), offset + width)
        np.testing.assert_allclose(far["period_mean_temperature_c"],
                                   near["period_mean_temperature_c"],
                                   rtol=1e-12, atol=0.)

    def test_window_spanning_a_year_boundary(self):
        """A window straddling the year boundary equals its two pieces combined.

        Both pieces are one day long, so their arithmetic mean is exactly the
        mean of the straddling window; the assertion is on the mean, not on the
        integral, so no length weighting is needed.
        """
        x, z = lattice(1, 1)
        start = YEAR_S - 86400.
        end = YEAR_S + 86400.
        whole = sample_seasonal_air(SEED, x, z, time_edges_s=[start, end])
        tail = sample_seasonal_air(SEED, x, z, time_edges_s=[start, YEAR_S])
        head = sample_seasonal_air(SEED, x, z, time_edges_s=[0., 86400.])
        expected = .5 * (tail["period_mean_temperature_c"][0]
                         + head["period_mean_temperature_c"][0])
        np.testing.assert_allclose(whole["period_mean_temperature_c"][0], expected,
                                   rtol=1e-12, atol=1e-12)

    def test_multi_year_window_equals_the_annual_mean(self):
        """Exactly N whole years integrate to N times the annual integral."""
        x, z = lattice(1, 1)
        one_year = sample_seasonal_air(SEED, x, z, time_edges_s=[0., YEAR_S])
        many = sample_seasonal_air(SEED, x, z, time_edges_s=[0., YEAR_S * 7.])
        np.testing.assert_allclose(many["period_mean_temperature_c"][0],
                                   one_year["period_mean_temperature_c"][0],
                                   rtol=1e-12, atol=1e-12)

    def test_full_year_interval_is_epoch_independent(self):
        """A whole year integrates to the same value at the epoch and far from it.

        Anchored on the module's own declared convention (trapezoid over month
        centers) rather than on a loose envelope, so the assertion is exact in both
        places and would catch a cancellation error that inflated one branch.
        """
        x, z = lattice(2, 2)
        gaps = np.diff(np.r_[MONTH_CENTERS_S, MONTH_CENTERS_S[0] + YEAR_S])
        weights = .5 * (gaps + np.roll(gaps, 1))
        # Offset the window by a whole number of days so it is not the 0..YEAR case
        # already covered above, and so the two epochs differ in year count only.
        shift = 86400. * 40.
        for base in (shift, YEAR_S * float(30_000) + shift):
            result = sample_seasonal_air(SEED, x, z, time_edges_s=[base, base + YEAR_S])
            months = result["monthly_temperature_c"]
            expected = np.tensordot(weights, months, axes=(0, 0)) / YEAR_S
            np.testing.assert_allclose(result["period_mean_temperature_c"][0],
                                       expected, rtol=1e-12, atol=1e-12)

    def test_unresolvable_interval_is_rejected_not_returned_as_noise(self):
        """A span of one or two ulps is pure cancellation, not a mean.

        The span must still be strictly positive (otherwise the ordering check
        fires first), so it is exactly one unit in the last place at this
        magnitude, which is below `MIN_INTERVAL_ULPS`.
        """
        x, z = lattice(1, 1)
        base = 1.0e9
        one_ulp = float(np.spacing(base))
        self.assertLess(one_ulp, MIN_INTERVAL_ULPS * one_ulp)
        with self.assertRaises(ValueError) as caught:
            sample_seasonal_air(SEED, x, z, time_edges_s=[base, base + one_ulp])
        self.assertIn("cancellation noise", str(caught.exception))

    def test_time_domain_is_bounded(self):
        x, z = lattice(1, 1)
        with self.assertRaises(ValueError) as caught:
            sample_seasonal_air(SEED, x, z, time_edges_s=[0., MAX_TIME_S * 10.])
        self.assertIn("declared domain", str(caught.exception))

    def test_period_budget_counts_the_list_and_the_stack(self):
        """The declared budget is peak bytes, not just the payload width."""
        x, z = lattice(1, MAX_POINTS)
        intervals = MAX_PERIOD_ENTRIES // MAX_POINTS + 2
        edges = list(np.arange(intervals + 1, dtype=np.float64))
        with self.assertRaises(ValueError) as caught:
            sample_seasonal_air(SEED, x, z, time_edges_s=edges)
        self.assertIn("peak about", str(caught.exception))

    def test_period_peak_bytes_is_double_the_payload(self):
        self.assertEqual(period_peak_bytes(1000, 10), 2 * 8 * 10 * 1000)
        self.assertEqual(period_peak_bytes(1000, None), 0)

    def test_period_peak_bytes_is_reported_when_used(self):
        result = sample_seasonal_air(SEED, *lattice(2, 3),
                                     time_edges_s=[0., 86400., 172800.])
        self.assertEqual(result["cost"]["period_peak_bytes"],
                         period_peak_bytes(6, 2))
        self.assertEqual(sample_seasonal_air(SEED, *lattice(2, 3))[
            "cost"]["period_peak_bytes"], 0)

    def test_period_is_none_without_edges(self):
        result = sample_seasonal_air(SEED, *lattice(1, 1))
        self.assertIsNone(result["period_mean_temperature_c"])
        self.assertIsNone(result["time_edges_s"])
        self.assertIsNone(result["identity"]["record"]["period"])
        self.assertEqual(result["cost"]["period_peak_bytes"], 0)

    def test_period_falls_between_the_month_extremes(self):
        x, z = lattice(2, 2)
        result = sample_seasonal_air(SEED, x, z, time_edges_s=[0., 86400.])
        months = result["monthly_temperature_c"]
        interval = result["period_mean_temperature_c"]
        for row, column in np.ndindex(*result["shape"]):
            series = months[:, row, column]
            self.assertGreaterEqual(float(interval[0, row, column]),
                                    float(series.min()) - 1e-9)
            self.assertLessEqual(float(interval[0, row, column]),
                                 float(series.max()) + 1e-9)

    def test_bad_time_edges_are_rejected(self):
        x, z = lattice(1, 1)
        for edges in ([0.], [10., 10.], [-1., 10.], [0., float("nan")], [10., 0.]):
            with self.assertRaises(ValueError):
                sample_seasonal_air(SEED, x, z, time_edges_s=edges)


class DeterminismTests(unittest.TestCase):
    def test_permutation_keeps_the_identity(self):
        """Identity is a property of the point SET, not of the request order."""
        x, z = lattice(3, 4)
        order = np.arange(x.size)
        np.random.RandomState(11).shuffle(order)
        base = sample_seasonal_air(SEED, x.reshape(-1), z.reshape(-1))
        shuffled = sample_seasonal_air(SEED, x.reshape(-1)[order], z.reshape(-1)[order])
        self.assertEqual(base["identity"]["identity_sha256"],
                         shuffled["identity"]["identity_sha256"])
        self.assertEqual(base["identity"]["points_digest"],
                         shuffled["identity"]["points_digest"])

    def test_permutation_places_values_correctly(self):
        """Values travel with their own coordinates, never with the slot index."""
        x, z = lattice(3, 4)
        order = np.arange(x.size)
        np.random.RandomState(11).shuffle(order)
        base = sample_seasonal_air(SEED, x.reshape(-1), z.reshape(-1))
        shuffled = sample_seasonal_air(SEED, x.reshape(-1)[order], z.reshape(-1)[order])
        np.testing.assert_array_equal(
            base["monthly_temperature_c"][:, order], shuffled["monthly_temperature_c"])
        np.testing.assert_array_equal(
            base["freezing_month_count"][order], shuffled["freezing_month_count"])

    def test_sub_window_matches_the_whole_window(self):
        x, z = lattice(4, 5)
        whole = sample_seasonal_air(SEED, x, z)
        rows = slice(1, 3)
        columns = slice(2, 5)
        cut = sample_seasonal_air(SEED, x[rows, columns], z[rows, columns])
        np.testing.assert_array_equal(
            whole["monthly_temperature_c"][:, rows, columns],
            cut["monthly_temperature_c"])
        np.testing.assert_array_equal(
            whole["wind_bearing_x"][rows, columns], cut["wind_bearing_x"])

    def test_single_point_matches_the_array_path(self):
        x, z = lattice(3, 4)
        whole = sample_seasonal_air(SEED, x, z)
        single = sample_seasonal_air(SEED, x[1, 2], z[1, 2])
        np.testing.assert_array_equal(whole["monthly_temperature_c"][:, 1, 2],
                                      single["monthly_temperature_c"])


class RejectionTests(unittest.TestCase):
    def test_off_grid_coordinates_are_rejected_not_snapped(self):
        with self.assertRaises(ValueError):
            sample_seasonal_air(SEED, 15., 15.)
        with self.assertRaises(ValueError):
            sample_seasonal_air(SEED, 0., 45.)  # half a cell in z

    def test_bad_seed_is_rejected(self):
        x, z = lattice(1, 1)
        for seed in (True, -1, 2 ** 64, 1.5, "20261020"):
            with self.assertRaises(ValueError):
                sample_seasonal_air(seed, x, z)

    def test_point_budget_and_non_finite_coordinates_are_rejected(self):
        with self.assertRaises(ValueError):
            sample_seasonal_air(SEED, np.arange(MAX_POINTS + 1) * GRID_SPACING_M, 0.)
        with self.assertRaises(ValueError):
            sample_seasonal_air(SEED, float("nan"), 0.)
        with self.assertRaises(ValueError):
            sample_seasonal_air(SEED, 1e13, 0.)

    def test_parameters_must_be_refined_climate_parameters(self):
        x, z = lattice(1, 1)
        with self.assertRaises(ValueError):
            sample_seasonal_air(SEED, x, z, parameters={"not": "parameters"})
        with self.assertRaises(ValueError):
            sample_seasonal_air(SEED, x, z, include_snow_line="yes")

    def test_falsy_parameters_are_rejected_not_silently_defaulted(self):
        """`parameters or default` would swallow these; only None may default."""
        x, z = lattice(1, 1)
        for falsy in ({}, 0, 0.0, False, "", [], ()):
            with self.assertRaises(ValueError) as caught:
                sample_seasonal_air(SEED, x, z, parameters=falsy)
            self.assertIn("falsy", str(caught.exception))
        result = sample_seasonal_air(SEED, x, z, parameters=None)
        self.assertEqual(result["identity"]["parameter_identity_sha256"],
                         RefinedClimateParameters().identity_sha256)

    def test_non_finite_sampler_output_is_rejected_here_too(self):
        with self.assertRaises(ValueError):
            sample_seasonal_air(SEED, *lattice(1, 2), elevation_sampler=nan_sampler)

    def test_incompatible_shapes_are_rejected(self):
        with self.assertRaises(ValueError):
            sample_seasonal_air(SEED, np.zeros((2, 3)), np.zeros((4, 5)))


class IdentityTests(unittest.TestCase):
    def test_identity_changes_with_the_temperature_band_parameter(self):
        x, z = lattice(2, 2)
        first = sample_seasonal_air(SEED, x, z)
        second = sample_seasonal_air(
            SEED, x, z,
            parameters=RefinedClimateParameters(latitude_temperature_range_c=-6.))
        self.assertNotEqual(first["identity"]["identity_sha256"],
                            second["identity"]["identity_sha256"])
        self.assertNotEqual(first["identity"]["parameter_identity_sha256"],
                            second["identity"]["parameter_identity_sha256"])

    def test_identity_is_stable_for_the_same_inputs(self):
        x, z = lattice(2, 2)
        first = sample_seasonal_air(SEED, x, z)
        second = sample_seasonal_air(SEED, x, z)
        self.assertEqual(first["identity"]["identity_sha256"],
                         second["identity"]["identity_sha256"])

    def test_dependent_kernel_bytes_are_bound(self):
        result = sample_seasonal_air(SEED, *lattice(1, 1))
        bound = result["code_identities"]
        self.assertIn('terrain_pipeline.climate_forcing', bound)
        self.assertIn('terrain_pipeline.climate_forcing', bound)
        for entry in bound.values():
            self.assertEqual(len(entry["source_sha256"]), 64)

    def test_identity_changes_with_the_location_at_equal_point_count(self):
        """Same count, different place: a seed-only record could not tell them apart."""
        first = sample_seasonal_air(SEED, *lattice(2, 2))
        second = sample_seasonal_air(SEED, *lattice(2, 2, x0=300_000., z0=600_000.))
        self.assertEqual(first["identity"]["record"]["point_count"],
                         second["identity"]["record"]["point_count"])
        self.assertNotEqual(first["identity"]["points_digest"],
                            second["identity"]["points_digest"])
        self.assertNotEqual(first["identity"]["identity_sha256"],
                            second["identity"]["identity_sha256"])

    def test_identity_changes_with_explicit_elevation(self):
        x, z = lattice(2, 2)
        low = sample_seasonal_air(SEED, x, z, elevation_m=0.)
        high = sample_seasonal_air(SEED, x, z, elevation_m=1500.)
        self.assertNotEqual(low["identity"]["identity_sha256"],
                            high["identity"]["identity_sha256"])

    def test_identity_changes_with_the_sampler_values(self):
        x, z = lattice(2, 2)
        low = sample_seasonal_air(SEED, x, z, elevation_sampler=ramp_sampler(0.))
        high = sample_seasonal_air(SEED, x, z, elevation_sampler=ramp_sampler(900.))
        self.assertNotEqual(low["identity"]["identity_sha256"],
                            high["identity"]["identity_sha256"])

    def test_identity_ignores_the_sampler_function_name(self):
        """Same values from differently-named samplers are the same product."""
        x, z = lattice(2, 2)

        def first_sampler(x_m, z_m):
            return ramp_sampler(700.)(x_m, z_m)

        def second_sampler(x_m, z_m):
            return ramp_sampler(700.)(x_m, z_m)

        one = sample_seasonal_air(SEED, x, z, elevation_sampler=first_sampler)
        two = sample_seasonal_air(SEED, x, z, elevation_sampler=second_sampler)
        self.assertEqual(one["identity"]["identity_sha256"],
                         two["identity"]["identity_sha256"])

    def test_identity_changes_with_the_query_shape(self):
        """Same point set in a different shape is a genuinely different request."""
        x, z = lattice(2, 3)
        flat = sample_seasonal_air(SEED, x.reshape(-1), z.reshape(-1))
        grid = sample_seasonal_air(SEED, x, z)
        self.assertEqual(flat["identity"]["points_digest"],
                         grid["identity"]["points_digest"])
        self.assertNotEqual(flat["identity"]["record"]["query_shape"],
                            grid["identity"]["record"]["query_shape"])
        self.assertNotEqual(flat["identity"]["identity_sha256"],
                            grid["identity"]["identity_sha256"])

    def test_identity_changes_with_the_period_request(self):
        x, z = lattice(2, 2)
        without = sample_seasonal_air(SEED, x, z)
        with_period = sample_seasonal_air(SEED, x, z, time_edges_s=[0., 86400.])
        self.assertNotEqual(without["identity"]["identity_sha256"],
                            with_period["identity"]["identity_sha256"])

    def test_this_module_is_bound_into_the_code_identities(self):
        result = sample_seasonal_air(SEED, *lattice(1, 1))
        self.assertIn('terrain_pipeline.climate_forcing',
                      result["code_identities"])
        self.assertEqual(result["identity"]["record"]["code_identities"],
                         result["code_identities"])

    def test_record_declares_the_wind_rule_and_calendar(self):
        result = sample_seasonal_air(SEED, *lattice(1, 1))
        record = result["identity"]["record"]
        self.assertIn("WIND_BAND_UNITS", record["wind"]["rule"])
        self.assertEqual(record["grid_spacing_m"], GRID_SPACING_M)
        self.assertEqual(record["calendar"]["days_per_year"], 365)
        self.assertEqual(record["climate_schema"], "metric-noise-climate-v2")


class SourceDeclarationTests(unittest.TestCase):
    #: Every array/scalar this entry point returns. Kept explicit so a new field
    #: without a source fails here instead of slipping through.
    VALUE_FIELDS = (
        "x_m", "z_m", "elevation_m",
        "monthly_temperature_c", "annual_mean_temperature_c",
        "seasonal_temperature_amplitude_c",
        "coldest_month_index", "warmest_month_index",
        "monthly_at_or_below_freezing", "freezing_month_count",
        "has_freezing_month", "all_months_freezing",
        "latitude_band_norm", "latitude_temperature_offset_c",
        "wind_bearing_x", "wind_bearing_z", "wind_band_index", "wind_band_name",
    )

    def test_every_returned_value_has_a_source_and_units(self):
        """Every numeric/derived/coordinate/bool/index field, not just one."""
        result = sample_seasonal_air(SEED, *lattice(1, 1), time_edges_s=[0., 86400.])
        for name in self.VALUE_FIELDS:
            self.assertIn(name, result, "field %r is missing from the result" % name)
            self.assertIn(name, result["sources"], "no source for %r" % name)
            self.assertIn(name, result["units"], "no units for %r" % name)
            entry = result["sources"][name]
            self.assertIn("source", entry, "empty source for %r" % name)
            self.assertTrue(entry["source"].strip(), "blank source for %r" % name)
            self.assertNotIn("placeholder", entry["source"].lower())
            self.assertTrue(result["units"][name].strip(),
                            "blank units for %r" % name)
            # The declared unit must be the one the module advertises.
            self.assertEqual(result["units"][name], UNITS[name])

    def test_period_and_time_fields_have_a_source_and_units(self):
        result = sample_seasonal_air(SEED, *lattice(1, 1), time_edges_s=[0., 86400.])
        for name in ("period_mean_temperature_c", "time_edges_s"):
            self.assertIn(name, result["sources"], name)
            self.assertIn(name, result["units"], name)
            self.assertEqual(result["units"][name], UNITS[name])

    def test_snow_line_subfields_have_a_source_and_units(self):
        result = sample_seasonal_air(SEED, *lattice(1, 1), include_snow_line=True)
        for name in ("monthly_first_freezing_elevation_m",
                     "seasonal_snow_line_m", "perennial_snow_line_m"):
            self.assertIn(name, result["snow_line"], name)
            self.assertIn(name, result["sources"], name)
            self.assertIn(name, result["units"], name)
            self.assertEqual(result["units"][name], UNITS[name])
            self.assertIn("pass-through", result["sources"][name]["source"])

    def test_source_table_matches_the_advertised_units(self):
        """`UNITS` and `SOURCE_OF` must cover the same keys, with no gaps."""
        self.assertEqual(sorted(UNITS), sorted(SOURCE_OF))
        for name, source in SOURCE_OF.items():
            self.assertTrue(source.strip(), "blank declared source for %r" % name)
            self.assertNotIn("placeholder", source.lower())
        self.assertEqual(sorted(describe()["source_of"]), sorted(SOURCE_OF))

    def test_caller_supplied_fields_say_so(self):
        result = sample_seasonal_air(SEED, *lattice(1, 1))
        self.assertEqual(result["sources"]["x_m"]["source"], "caller_supplied")
        self.assertEqual(result["sources"]["z_m"]["source"], "caller_supplied")
        self.assertEqual(result["units"]["x_m"], "m_easting")
        self.assertEqual(result["units"]["z_m"], "m_southing")

    def test_elevation_has_units(self):
        """The specific field the first run tripped on."""
        result = sample_seasonal_air(SEED, *lattice(1, 1))
        self.assertEqual(result["units"]["elevation_m"], "m")
        self.assertIn("elevation_m", result["sources"])

    def test_period_unit_is_not_the_annual_unit(self):
        """Three averages, three names: no field may be renamed into another."""
        units = sample_seasonal_air(SEED, *lattice(1, 1))["units"]
        self.assertNotEqual(units["annual_mean_temperature_c"],
                            units["period_mean_temperature_c"])
        self.assertIn("interval_mean", units["period_mean_temperature_c"])

    def test_freezing_source_states_it_is_not_snowpack(self):
        result = sample_seasonal_air(SEED, *lattice(1, 1))
        declaration = result["sources"]["freezing_month_count"]
        self.assertIn("not snowpack", declaration["note"])
        self.assertIn("not", declaration["inversion_avoided"])

    def test_temperature_source_states_it_is_a_monthly_mean(self):
        result = sample_seasonal_air(SEED, *lattice(1, 1))
        self.assertIn("monthly mean", result["sources"]["monthly_temperature_c"]["note"])
        self.assertEqual(result["units"]["monthly_temperature_c"], "degC_monthly_mean")

    def test_elevation_source_is_reported_verbatim(self):
        x, z = lattice(1, 2)
        coarse = sample_seasonal_air(SEED, x, z)
        explicit = sample_seasonal_air(SEED, x, z, elevation_m=1500.)
        self.assertEqual(coarse["elevation_source"], "coarse_condition_field_height_m")
        self.assertEqual(explicit["elevation_source"], "explicit_elevation_m")
        np.testing.assert_allclose(explicit["elevation_m"], 1500.)

    def test_all_returned_floats_are_finite(self):
        result = sample_seasonal_air(SEED, *lattice(3, 4), time_edges_s=[0., 86400.])
        for name in ("monthly_temperature_c", "annual_mean_temperature_c",
                     "seasonal_temperature_amplitude_c", "latitude_band_norm",
                     "latitude_temperature_offset_c", "elevation_m",
                     "period_mean_temperature_c"):
            self.assertTrue(np.isfinite(np.asarray(result[name], np.float64)).all(),
                            name)


if __name__ == "__main__":
    unittest.main()
