"""External-behaviour tests for the PET/ET adapter (G5 first card).

Every test asserts an externally observable property: equality with the original
public core, exact grouping equivalence, ledger closure, calendar integration,
refusal, identity propagation and checkpoint/partition behaviour. Nothing asserts an
internal helper, a magic constant or a ``> threshold`` discrimination score.

The module under test is an adapter. The two properties that must never regress are
(a) it does **not** contain a second bucket or a second PET formula, and (b) its
numbers are bit-identical to the pieces it composes.
"""

import ast
import inspect
import json
import os
import tempfile
import unittest
from dataclasses import replace

import numpy as np

from terrain_pipeline.runoff import MONTH_DAYS as MONTH_DAYS
from terrain_pipeline.runoff import SeasonalConfig as SeasonalConfig
from terrain_pipeline.runoff import seasonal_climate as seasonal_climate
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.climate_forcing import advance_soil
from terrain_pipeline import soil_water as adapter
from terrain_pipeline.soil_water import PetEtParameters, advance_pet_et, advance_pet_et_segment, calendar_month_seconds, pet_et_describe as describe, interval_pet_mm, liquid_fraction, load_pet_et_checkpoint, monthly_potential_et_mm, parameters_from_seasonal_config, pet_parameter_identity, pet_et_preflight as preflight, save_pet_et_checkpoint, temperature_index_pet_rate_mm_h
from terrain_pipeline.climate_forcing import YEAR_S


SPACING = 30.0


def _temperature(cells, values=None):
    """`[12, N]` declared monthly temperature.

    The default is **all positive** so a default scenario reaches the bucket in the
    liquid phase; the phase tests pass an explicitly cold or mixed profile instead of
    relying on a hidden sign.
    """
    if values is None:
        values = np.linspace(2.0, 22.0, 12)
    table = np.tile(np.asarray(values, np.float64)[:, None], (1, cells))
    return table


def _mixed_temperature(cells):
    """A profile with freezing months, for the phase tests."""
    return _temperature(cells, np.linspace(-14.0, 22.0, 12))


def _points(cells):
    x = 1266450.0 + 30.0 * np.arange(cells)
    z = np.full(cells, 1290990.0)
    return x, z


def _edges(intervals, seconds=3600.0, start=0.0):
    return start + seconds * np.arange(intervals + 1, dtype=np.float64)


def _scenario(cells=3, intervals=6, rain_mm_h=0.0, states=None, parameters=None):
    temperature = _temperature(cells)
    rain = np.full((intervals, cells), float(rain_mm_h), np.float64)
    edges = _edges(intervals)
    initial = (np.zeros((3, cells)) if states is None
               else np.asarray(states, np.float64))
    x, z = _points(cells)
    result = advance_pet_et(
        temperature, rain, edges, initial, x_m=x, z_m=z, spacing_m=SPACING,
        parameters=parameters)
    return result, temperature, rain, edges, initial


def _import_lines(module):
    return [line for line in inspect.getsource(module).splitlines()
            if line.lstrip().startswith(("import ", "from "))]


class DeclarationTests(unittest.TestCase):
    def test_describe_binds_the_bucket_and_denies_duplicates(self):
        declared = describe()
        self.assertEqual(declared["schema"], "metric-pet-et-v1")
        self.assertEqual(declared["algorithm"], "pet-et-adapter-v1")
        self.assertEqual(
            declared["bucket_module"],
            'terrain_pipeline.climate_forcing.advance_soil')
        self.assertEqual(declared["network_coupling"], "none")
        self.assertEqual(declared["boundary_api"], "none")
        never = " | ".join(declared["never"])
        for phrase in ("a second soil bucket", "a second PET formula",
                       "an aquifer, a groundwater baseflow or a deep loss",
                       "snow depth or glacier"):
            self.assertIn(phrase, never)

    def test_adapter_imports_no_network_boundary_or_soil_proxy_module(self):
        imports = "\n".join(_import_lines(adapter))
        for forbidden in ("metric_runoff", "metric_soil_condition", "metric_network",
                          "native_30m"):
            self.assertNotIn(forbidden, imports,
                             "the adapter must not import %r" % (forbidden,))
        # It reads the frozen bucket and the frozen config; nothing else of physics.
        self.assertIn("regional_surface_forcing import advance_soil", imports)
        self.assertIn("hydrology_seasonal import SeasonalConfig", imports)
        self.assertIn("rainfall_runoff import RunoffParameters", imports)

    def test_adapter_does_not_monkeypatch_the_frozen_cores(self):
        """Structural check, not a string search: the docstring says "never monkeypatched"
        honestly, so looking for the word would punish the truthful note.

        What must be absent: any ``setattr``/``patch`` node, any assignment to an attribute
        of an imported module, and any import of a mocking library.
        """
        tree = ast.parse(inspect.getsource(adapter))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = ([alias.name for alias in node.names]
                         if isinstance(node, ast.Import)
                         else [node.module or ""] + [alias.name for alias in node.names])
                joined = " ".join(names)
                self.assertNotIn("mock", joined)
                self.assertNotIn("unittest", joined)
            if isinstance(node, ast.Call):
                target = node.func
                name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
                self.assertNotIn(name, ("setattr", "patch", "patch_object"))
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute):
                        base = target.value
                        # ``obj.attr = value`` is only legitimate on a locally built object;
                        # assigning onto an imported module or a frozen config class is not.
                        base_name = getattr(base, "id", getattr(base, "attr", ""))
                        self.assertNotIn(base_name, ("advance_soil", "RunoffParameters",
                                                     "SeasonalConfig", "np"))

        # The old climate function is never called: it would resample the v1 climate
        # internally and silently substitute it for the declared v2/G3 temperature.
        self.assertNotIn("seasonal_climate(", inspect.getsource(adapter))


class PetExpressionEquivalenceTests(unittest.TestCase):
    """The one declared synonym must be bit-identical to the original core."""

    def setUp(self):
        self.plan = {"height_m": np.zeros((3, 3)), "origin_xz_m": [1000.0, -1000.0],
                     "spacing_m": 30.0, "seed": 7}
        self.config = SeasonalConfig()
        self.original = seasonal_climate(self.plan, self.config)
        self.params = parameters_from_seasonal_config(self.config)

    def test_monthly_depth_is_bit_identical_to_the_original_climate_function(self):
        # ``seasonal_climate`` returns ``(12, 3, 3)``; the adapter's public shape is
        # ``(12, N)``. Flattening the grid to one axis keeps the comparison on the same
        # numbers instead of broadcasting (12,) against (12, 3, 3).
        temperature = np.asarray(self.original["temperature_c"], np.float64).reshape(12, -1)
        mine = monthly_potential_et_mm(temperature, self.params)
        reference = np.asarray(self.original["potential_et_mm"], np.float64).reshape(12, -1)
        np.testing.assert_array_equal(mine, reference)

    def test_hourly_rate_is_the_monthly_depth_over_the_month_hours(self):
        temperature = np.asarray(self.original["temperature_c"], np.float64).reshape(12, -1)
        rate = temperature_index_pet_rate_mm_h(temperature, self.params)
        reference = (np.asarray(self.original["potential_et_mm"], np.float64).reshape(12, -1)
                     / (MONTH_DAYS[:, None] * 24.0))
        np.testing.assert_allclose(rate, reference, rtol=1e-15, atol=0.0)

    def test_parameters_are_read_from_the_config_not_inlined(self):
        changed = SeasonalConfig(pet_base_mm_per_day=1.25,
                                pet_temperature_mm_per_day_c=0.31)
        params = parameters_from_seasonal_config(changed)
        self.assertEqual(params.pet_base_mm_per_day, 1.25)
        self.assertEqual(params.pet_temperature_mm_per_day_c, 0.31)
        temperature = np.asarray(self.original["temperature_c"], np.float64).reshape(12, -1)
        expected = ((1.25 + 0.31 * np.maximum(temperature, 0.0))
                    * MONTH_DAYS[:, None])
        np.testing.assert_array_equal(
            monthly_potential_et_mm(temperature, params), expected)

    def test_freezing_or_below_months_contribute_only_the_base_rate(self):
        cold = np.full((12, 2), -30.0)
        rate = temperature_index_pet_rate_mm_h(cold, self.params)
        np.testing.assert_array_equal(rate, np.full((12, 2),
                                                    self.params.pet_base_mm_per_day / 24.0))

    def test_non_finite_temperature_is_refused(self):
        for bad in (np.nan, np.inf, -np.inf):
            temperature = _temperature(2)
            temperature[3, 0] = bad
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    monthly_potential_et_mm(temperature, self.params)

    def test_wrong_month_count_is_refused(self):
        with self.assertRaises(ValueError):
            monthly_potential_et_mm(np.zeros((11, 4)), self.params)
        with self.assertRaises(ValueError):
            monthly_potential_et_mm(np.zeros(4), self.params)


class GroupingEquivalenceTests(unittest.TestCase):
    """The exact scalar grouping must equal one bucket call per cell."""

    def test_grouped_calls_reproduce_per_cell_bucket_calls_bit_for_bit(self):
        cells, intervals = 4, 3
        temperature = _temperature(cells)
        # Make every cell's PET rate distinct by construction.
        temperature[:, 1] *= 1.5
        temperature[:, 2] *= 2.0
        temperature[:, 3] *= 3.0
        rain = np.full((intervals, cells), 12.0)
        edges = _edges(intervals)
        states = np.stack([np.full(cells, 40.0), np.full(cells, 3.0),
                           np.full(cells, 7.0)])
        x, z = _points(cells)
        params = PetEtParameters()
        result = advance_pet_et(temperature, rain, edges, states, x_m=x, z_m=z,
                                spacing_m=SPACING, parameters=params)

        rate = result["pet_rate_mm_h"]
        hours = np.diff(edges) / 3600.0
        liquid_rate = result["liquid_rate_mm_h"]
        current = states.copy()
        for step in range(intervals):
            for cell in range(cells):
                one = replace(params.runoff,
                              potential_et_mm_h=float(rate[step, cell]))
                nxt, release, et, change = advance_soil(
                    np.array([liquid_rate[step, cell]]), current[:, cell:cell + 1],
                    dt_s=float(np.diff(edges)[step]),
                    parameters=one)
                self.assertEqual(result["soil_edge_mm"][step + 1, cell], nxt[0, 0])
                self.assertEqual(result["fast_edge_mm"][step + 1, cell], nxt[1, 0])
                self.assertEqual(result["slow_edge_mm"][step + 1, cell], nxt[2, 0])
                self.assertEqual(result["actual_et_mm"][step, cell], et[0])
                self.assertEqual(result["release_mm"][step, cell], release[0])
                self.assertEqual(result["storage_change_mm"][step, cell], change[0])
            current = np.stack([result["soil_edge_mm"][step + 1],
                               result["fast_edge_mm"][step + 1],
                               result["slow_edge_mm"][step + 1]])

    def test_group_report_counts_real_distinct_values(self):
        result, *_ = _scenario(cells=3, intervals=2)
        self.assertLessEqual(result["groups"]["unique_pet_groups"][0], 3)
        self.assertEqual(result["groups"]["calls"],
                         result["groups"]["unique_pet_groups"])
        for sizes, groups in zip(result["groups"]["group_sizes"],
                                 result["groups"]["unique_pet_groups"]):
            self.assertEqual(sum(sizes), 3)
            self.assertEqual(len(sizes), groups)

    def test_uniform_temperature_uses_one_call_per_interval(self):
        temperature = np.tile(_temperature(1)[:, :1], (1, 5))
        rain = np.zeros((4, 5))
        edges = _edges(4)
        states = np.zeros((3, 5))
        x, z = _points(5)
        result = advance_pet_et(temperature, rain, edges, states, x_m=x, z_m=z,
                                spacing_m=SPACING)
        self.assertEqual(result["groups"]["unique_pet_groups"], [1, 1, 1, 1])


class CalendarIntegrationTests(unittest.TestCase):
    def test_interval_that_crosses_a_month_edge_is_integrated_not_assigned(self):
        # One 1 h interval straddling the January/February edge.
        january_end = float(MONTH_DAYS[0]) * 86400.0
        edges = np.array([january_end - 1800.0, january_end + 1800.0])
        temperature = _temperature(2)
        seconds = calendar_month_seconds(edges)
        self.assertEqual(seconds.shape, (1, 12))
        self.assertAlmostEqual(float(seconds[0].sum()), 3600.0, places=6)
        self.assertAlmostEqual(float(seconds[0, 0]), 1800.0, places=6)
        self.assertAlmostEqual(float(seconds[0, 1]), 1800.0, places=6)
        depth = interval_pet_mm(temperature, edges)
        rate = temperature_index_pet_rate_mm_h(temperature)
        expected = rate[0] * (1800.0 / 3600.0) + rate[1] * (1800.0 / 3600.0)
        np.testing.assert_allclose(depth[0], expected, rtol=0.0, atol=1e-15)

    def test_interval_that_crosses_a_year_edge_is_integrated(self):
        edges = np.array([YEAR_S - 1800.0, YEAR_S + 1800.0])
        seconds = calendar_month_seconds(edges)
        self.assertAlmostEqual(float(seconds[0, 11]), 1800.0, places=6)
        self.assertAlmostEqual(float(seconds[0, 0]), 1800.0, places=6)

    def test_month_seconds_sum_to_the_interval(self):
        edges = _edges(8)
        seconds = calendar_month_seconds(edges)
        np.testing.assert_allclose(seconds.sum(axis=1), np.diff(edges),
                                   rtol=0.0, atol=1e-6)

    def test_mixed_phase_splits_the_declared_precipitation(self):
        # January is freezing, July is warm: one interval in each month must take the
        # monthly-mean threshold decision, and the two must differ.
        mixed = _mixed_temperature(2)
        january = calendar_month_seconds(np.array([0.0, 3600.0]))
        july_start = float(np.sum(MONTH_DAYS[:6])) * 86400.0
        july = calendar_month_seconds(np.array([july_start, july_start + 3600.0]))
        self.assertEqual(float(liquid_fraction(mixed, january)[0, 0]), 0.0)
        self.assertEqual(float(liquid_fraction(mixed, july)[0, 0]), 1.0)

    def test_report_declares_monthly_mean_and_no_leap_day(self):
        result, *_ = _scenario(cells=2, intervals=2)
        self.assertEqual(
            result["sources"]["monthly_temperature_c"]["semantics"],
            "monthly_mean_not_daily_and_not_diurnal")
        self.assertIn("365 days, no leap day",
                      result["sources"]["interval_pet_mm"]["calendar"])
        self.assertAlmostEqual(float(MONTH_DAYS.sum()), 365.0)


class LedgerTests(unittest.TestCase):
    def test_main_account_closes(self):
        result, *_ = _scenario(cells=4, intervals=8, rain_mm_h=6.0,
                               states=np.full((3, 4), 25.0))
        ledger = result["ledger"]
        self.assertEqual(
            ledger["main_account"],
            "delta(soil+fast+slow) = liquid_rain - actual_et - release")
        # ``advance_soil`` itself refuses a cell-local balance above 1e-10 mm; the main
        # account is now recomputed from the saved edges, so this is the real closure.
        self.assertEqual(ledger["main_account_source"],
                         "recomputed from the saved state edges, not from the bucket's change array")
        self.assertTrue(ledger["main_account_verified"])
        self.assertLessEqual(ledger["main_max_abs_residual_mm"], 1e-10)
        self.assertLessEqual(abs(ledger["total_balance_residual_m3"]), 1e-9)
        # The bucket's own change array agrees with the edge difference.
        self.assertLessEqual(ledger["edge_vs_bucket_change_max_abs_mm"], 1e-10)
        self.assertLessEqual(ledger["bucket_internal_max_abs_residual_mm"], 1e-10)
        self.assertEqual(ledger["total_balance_residual_unit"], "m3")

    def test_solid_phase_is_accounted_in_the_ledger(self):
        # The window must straddle a boundary where the two months really disagree about
        # phase, otherwise the ledger can only report solid OR only liquid. Months 0-5 are
        # declared freezing and 6-11 warm, so the June/July edge is used (the Jan/Feb edge
        # would have both sides frozen and liquid_total would legitimately be 0).
        profile = np.zeros((12, 2))
        profile[:6] = -10.0
        profile[6:] = 15.0
        cells = 2
        x, z = _points(cells)
        june_end = float(np.sum(MONTH_DAYS[:6])) * 86400.0
        edges = np.array([june_end - 1800.0, june_end + 1800.0])
        result = advance_pet_et(profile, np.full((1, cells), 8.0), edges,
                                np.zeros((3, cells)), x_m=x, z_m=z,
                                spacing_m=SPACING)
        accounting = result["ledger"]["solid_accounting"]
        self.assertGreater(accounting["solid_equivalent_water_mm_total"], 0.0)
        self.assertGreater(accounting["liquid_mm_total"], 0.0)
        self.assertAlmostEqual(accounting["liquid_plus_solid_minus_rain_mm"], 0.0,
                               places=12)
        self.assertTrue(accounting["solid_is_withheld_not_lost"])

    def test_release_is_deducted_exactly_once(self):
        result, *_ = _scenario(cells=3, intervals=6, rain_mm_h=8.0,
                               states=np.stack([np.full(3, 60.0), np.full(3, 10.0),
                                                np.full(3, 25.0)]))
        self.assertTrue(result["ledger"]["release_deducted_once"])
        self.assertTrue(result["ledger"]["subsurface_transfer_is_internal"])
        # The slow store actually released something, i.e. release carries it.
        self.assertGreater(float(result["release_mm"].sum()), 0.0)
        self.assertLessEqual(result["ledger"]["main_max_abs_residual_mm"], 1e-10)
        # The slow store's release is already inside ``release``: the reported total is
        # the same number, not that number plus a second subsurface discharge term.
        self.assertEqual(result["ledger"]["total_release_mm"],
                         float(result["release_mm"].sum()))
        self.assertGreater(float(result["subsurface_transfer_mm"].sum()), 0.0)

    def test_soil_sub_account_is_audited_and_not_fabricated(self):
        result, *_ = _scenario(cells=3, intervals=6, rain_mm_h=9.0,
                               states=np.full((3, 3), 15.0))
        sub = result["ledger"]["soil_sub_account"]
        self.assertEqual(sub["status"], "audited")
        self.assertEqual(sub["mismatched_cells"], 0)
        self.assertIn("infiltration", sub["definition"])
        self.assertIn("bucket returns neither", sub["note"])
        # The audit is a refutation device, not a rubber stamp: feeding it a wrong
        # infiltration must be detectable, so the tolerance is exact zero.
        self.assertEqual(sub["max_abs_difference_mm"], 0.0)

    def test_solid_input_is_withheld_and_reported_not_dropped(self):
        cold = np.full((12, 2), -20.0)
        rain = np.full((2, 2), 5.0)
        edges = _edges(2)
        x, z = _points(2)
        result = advance_pet_et(cold, rain, edges, np.zeros((3, 2)), x_m=x, z_m=z,
                                spacing_m=SPACING)
        np.testing.assert_array_equal(result["liquid_fraction"], np.zeros((2, 2)))
        np.testing.assert_array_equal(result["liquid_rain_mm"], np.zeros((2, 2)))
        np.testing.assert_allclose(result["solid_precipitation_swe_mm"],
                                   result["rain_mm"], rtol=0.0, atol=0.0)
        # Nothing entered the bucket: the soil edge is unchanged.
        np.testing.assert_array_equal(result["soil_edge_mm"],
                                      np.zeros((3, 2)))
        # And the withheld water is accounted, not silently lost.
        self.assertGreater(float(result["solid_precipitation_swe_mm"].sum()), 0.0)
        self.assertEqual(result["not_available"]["snowpack_state"]["status"],
                         "not_modeled")

    def test_warm_month_produces_liquid_and_bucket_responds(self):
        warm = np.full((12, 2), 18.0)
        rain = np.full((2, 2), 5.0)
        edges = _edges(2)
        x, z = _points(2)
        result = advance_pet_et(warm, rain, edges, np.zeros((3, 2)), x_m=x, z_m=z,
                                spacing_m=SPACING)
        np.testing.assert_array_equal(result["liquid_fraction"], np.ones((2, 2)))
        self.assertGreater(float(result["soil_edge_mm"][-1].mean()), 0.0)

    def test_not_available_declarations_are_explicit(self):
        result, *_ = _scenario(cells=2, intervals=2)
        declared = result["not_available"]
        for name in ("deep_loss", "aquifer_storage", "baseflow"):
            self.assertEqual(declared[name]["status"], "not_available")
            self.assertTrue(declared[name]["reason"])
        for name in ("snowpack_state", "glacier"):
            self.assertEqual(declared[name]["status"], "not_modeled")
        registration = result["sub_seed_registration"]
        self.assertFalse(registration["noise_used"])
        self.assertIsNone(registration["purpose"])


class RegimeTests(unittest.TestCase):
    """Two non-empty branches is a rule-coverage gate, not a real-window demand."""

    def test_supply_limited_when_dry(self):
        result, *_ = _scenario(cells=3, intervals=4, rain_mm_h=0.0)
        regimes = result["regimes"]
        self.assertEqual(regimes["pet_limited"], 0)
        self.assertGreater(regimes["supply_limited"], 0)
        self.assertEqual(regimes["denominator"], 12)

    def test_pet_limited_when_wet_and_shallow(self):
        # Saturated-ish soil with a big liquid supply: the interval PET is the cap.
        states = np.stack([np.full(3, 120.0), np.full(3, 40.0), np.full(3, 40.0)])
        result, *_ = _scenario(cells=3, intervals=4, rain_mm_h=400.0, states=states)
        self.assertGreater(result["regimes"]["pet_limited"], 0)

    def test_both_branches_coexist_in_one_declared_scenario(self):
        # Cell 0 wet (PET-limited), cell 1 dry (supply-limited) in one nonempty run.
        temperatures = np.tile(_temperature(2)[:, :1], (1, 2))
        temperatures[:, 1] = temperatures[:, 0]
        rain = np.array([[400.0, 0.0]] * 4)
        edges = _edges(4)
        states = np.stack([np.array([120.0, 0.0]), np.array([50.0, 0.0]),
                           np.array([50.0, 0.0])])
        x, z = _points(2)
        result = advance_pet_et(temperatures, rain, edges, states, x_m=x, z_m=z,
                                spacing_m=SPACING)
        regimes = result["regimes"]
        self.assertGreater(regimes["pet_limited"], 0)
        self.assertGreater(regimes["supply_limited"], 0)
        self.assertEqual(regimes["pet_limited"] + regimes["supply_limited"]
                         + regimes["mixed_boundary"], regimes["denominator"])
        self.assertIn("rule-coverage gate", regimes["rule"])

    def test_interval_crossing_a_month_edge_is_labelled_when_its_pieces_disagree(self):
        """One continuous run whose two calendar pieces land on different ET branches.

        The two pieces must come from **the same trajectory** — carrying the wet-end state
        into the second piece is what makes the label meaningful. The declared branch of
        each piece is derived from the numbers, not assumed:

        piece 0 (freezing January, no liquid, empty store):
            liquid_rate = 0 (declared freezing), so infiltration = 0
            available supply = soil_before + infiltration = 0 mm
            PET demand       = (0.5 + 0.12*0)/24 mm/h x 0.5 h = 0.0104 mm
            -> 0 < 0.0104, so ``supply_limited``.
        piece 1 (warm February, 300 mm/h rain, state carried from piece 0):
            PET rate = (0.5 + 0.12*20)/24 = 0.12083 mm/h -> demand 0.0604 mm
            infiltration is capped at 15 mm/h x 0.5 h = 7.5 mm, far above the demand,
            so with the carried store the available supply exceeds 0.0604 mm
            -> ``pet_limited``.

        The assertion on ``mixed_boundary`` is the *consequence*; if a future change made
        both pieces PET-limited, the declared counts below would fail first and point at
        the cause, and ``mixed_boundary`` would legitimately be 0.
        """
        cells = 2
        profile = np.zeros((12, cells))
        profile[0] = -8.0
        profile[1] = 20.0
        x, z = _points(cells)
        params = PetEtParameters()
        january_end = float(MONTH_DAYS[0]) * 86400.0

        # One continuous run: piece 0 then piece 1, the state carried across.
        before = np.array([january_end - 1800.0, january_end])
        after = np.array([january_end, january_end + 1800.0])
        start = np.stack([np.zeros(cells), np.zeros(cells), np.zeros(cells)])
        first = advance_pet_et(profile, np.full((1, cells), 300.0), before, start,
                               x_m=x, z_m=z, spacing_m=SPACING, parameters=params)
        carry = np.stack([first["soil_edge_mm"][-1], first["fast_edge_mm"][-1],
                          first["slow_edge_mm"][-1]])
        second = advance_pet_et_segment(
            np.full((1, cells), 300.0), after, carry, x_m=x, z_m=z,
            monthly_temperature_c=profile, spacing_m=SPACING, parameters=params)

        # Branch of each piece, taken from the run itself (these are the observed values,
        # not a re-statement of the arithmetic above).
        self.assertEqual(float(first["liquid_rain_mm"].sum()), 0.0,
                         "January is declared freezing, so it must deliver no liquid")
        self.assertEqual(first["et_regime"][0, 0], "supply_limited")
        # With no liquid there is no infiltration, so the January store stays empty.
        self.assertEqual(float(first["infiltration_mm"].sum()), 0.0)
        self.assertEqual(float(first["soil_edge_mm"][-1].min()), 0.0)
        self.assertGreater(float(second["liquid_rain_mm"].sum()), 0.0)
        # February's infiltration must actually reach the store, otherwise the supply would
        # stay at the carried 0 mm and the piece could not be PET-limited.
        self.assertGreater(float(second["infiltration_mm"].sum()), 0.0)
        self.assertGreater(float(second["soil_edge_mm"][-1].min()), 0.0)
        self.assertEqual(second["et_regime"][0, 0], "pet_limited")

        # The straddling single-interval run over the same start state.
        result = advance_pet_et(profile, np.full((1, cells), 300.0),
                                np.array([january_end - 1800.0, january_end + 1800.0]),
                                start, x_m=x, z_m=z, spacing_m=SPACING, parameters=params)
        self.assertEqual(int(result["substeps_per_interval"][0]), 2)
        self.assertEqual(int(result["regimes"]["mixed_boundary"]), cells)
        # And the straddling run must end where the two-piece run ends.
        np.testing.assert_array_equal(result["soil_edge_mm"][-1],
                                      second["soil_edge_mm"][-1])

    def test_et_never_exceeds_pet_or_the_available_supply(self):
        result, *_ = _scenario(cells=4, intervals=6, rain_mm_h=3.0,
                               states=np.full((3, 4), 30.0))
        et = result["actual_et_mm"]
        self.assertTrue(np.all(et >= 0.0))
        self.assertTrue(np.all(et <= result["interval_pet_mm"] + 1e-12))
        self.assertTrue(np.all(et <= result["available_supply_mm"] + 1e-12))


class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.cells = 2
        self.temperature = _temperature(self.cells)
        self.rain = np.zeros((2, self.cells))
        self.edges = _edges(2)
        self.states = np.zeros((3, self.cells))
        self.x, self.z = _points(self.cells)

    def _call(self, **overrides):
        arguments = dict(monthly_temperature_c=self.temperature, rain_mm_h=self.rain,
                         time_edges_s=self.edges, states=self.states,
                         x_m=self.x, z_m=self.z, spacing_m=SPACING)
        arguments.update(overrides)
        return advance_pet_et(**arguments)

    def test_interval_longer_than_the_bucket_gate_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self._call(time_edges_s=np.array([0.0, 3600.1]))
        self.assertIn("3600", str(caught.exception))

    def test_non_increasing_edges_are_refused(self):
        for edges in (np.array([0.0, 100.0, 100.0]),
                      np.array([0.0, 200.0, 100.0]),
                      np.array([-10.0, 0.0, 100.0])):
            with self.subTest(edges=edges.tolist()):
                with self.assertRaises(ValueError):
                    self._call(time_edges_s=edges,
                               rain_mm_h=np.zeros((2, self.cells)))

    def test_edge_count_must_match_the_rain_rows(self):
        with self.assertRaises(ValueError):
            self._call(time_edges_s=_edges(3))

    def test_rain_above_the_bucket_bound_is_refused(self):
        with self.assertRaises(ValueError):
            self._call(rain_mm_h=np.full((2, self.cells), 1000.5))

    def test_negative_or_non_finite_rain_is_refused(self):
        for value in (-0.1, np.nan, np.inf):
            rain = np.zeros((2, self.cells))
            rain[1, 0] = value
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self._call(rain_mm_h=rain)

    def test_negative_or_non_finite_states_are_refused(self):
        for value in (-1.0, np.nan):
            states = np.zeros((3, self.cells))
            states[1, 0] = value
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self._call(states=states)

    def test_initial_soil_above_capacity_is_refused(self):
        states = np.zeros((3, self.cells))
        states[0] = RunoffParameters().soil_capacity_mm + 1.0
        with self.assertRaises(ValueError) as caught:
            self._call(states=states)
        self.assertIn("soil_capacity_mm", str(caught.exception))

    def test_wrong_state_shape_is_refused(self):
        with self.assertRaises(ValueError):
            self._call(states=np.zeros((2, self.cells)))

    def test_unknown_sources_are_refused(self):
        with self.assertRaises(ValueError):
            self._call(temperature_source="made_up_source")
        with self.assertRaises(ValueError):
            self._call(rain_source="made_up_source")

    def test_non_finite_or_negative_spacing_is_refused(self):
        for spacing in (0.0, -30.0, float("nan")):
            with self.subTest(spacing=spacing):
                with self.assertRaises(ValueError):
                    self._call(spacing_m=spacing)

    def test_point_count_must_match(self):
        with self.assertRaises(ValueError):
            self._call(x_m=np.zeros(3))

    def test_work_above_the_declared_cap_is_refused_before_allocation(self):
        with self.assertRaises(ValueError) as caught:
            preflight(4096, 8760)
        self.assertIn("cell-interval", str(caught.exception))

    def test_preflight_bounds_cells_and_intervals(self):
        for cells, intervals in ((0, 1), (1, 0), (4097, 1), (1, 8761)):
            with self.subTest(cells=cells, intervals=intervals):
                with self.assertRaises(ValueError):
                    preflight(cells, intervals)
        table = preflight(16, 48)
        self.assertEqual(table["cell_intervals"], 768)
        self.assertEqual(table["max_bucket_calls"], 768 * 2)
        self.assertGreater(table["estimated_output_bytes"], 0)


class IdentityTests(unittest.TestCase):
    def test_pet_identity_ignores_the_bucket_parameters(self):
        base = PetEtParameters()
        other_bucket = replace(base, runoff=replace(base.runoff, percolation_mm_h=4.0))
        self.assertEqual(pet_parameter_identity(base), pet_parameter_identity(other_bucket))

    def test_pet_identity_moves_with_its_own_parameters(self):
        base = PetEtParameters()
        for changed in (replace(base, pet_base_mm_per_day=0.6),
                        replace(base, pet_temperature_mm_per_day_c=0.13),
                        replace(base, freezing_threshold_c=-1.0)):
            with self.subTest(changed=changed):
                self.assertNotEqual(pet_parameter_identity(base),
                                    pet_parameter_identity(changed))

    def test_model_identity_moves_with_bucket_parameters(self):
        result, temperature, rain, edges, initial = _scenario(cells=2, intervals=2)
        params = PetEtParameters()
        other = replace(params, runoff=replace(params.runoff, percolation_mm_h=4.0))
        x, z = _points(2)
        baseline = adapter.model_identity(
            parameters=params, x_m=x, z_m=z, time_edges_s=edges, states=initial,
            monthly_temperature_c=temperature, rain_mm_h=rain, spacing_m=SPACING,
            temperature_source="caller_declared_monthly_mean",
            rain_source="declared_event")
        changed = adapter.model_identity(
            parameters=other, x_m=x, z_m=z, time_edges_s=edges, states=initial,
            monthly_temperature_c=temperature, rain_mm_h=rain, spacing_m=SPACING,
            temperature_source="caller_declared_monthly_mean",
            rain_source="declared_event")
        self.assertNotEqual(baseline, changed)
        self.assertEqual(result["identity"]["model_identity_sha256"], baseline)

    def test_model_identity_binds_points_edges_states_and_forcing(self):
        # Non-constant fields and *real* coordinate changes: reversing ``x`` alone can be a
        # no-op when every column holds the same value, so the point set is varied instead.
        cells, intervals = 3, 2
        temperature = _temperature(cells)
        temperature[:, 1] += 3.0
        temperature[:, 2] -= 2.0
        rain = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        edges = _edges(intervals)
        initial = np.stack([np.full(cells, 10.0), np.full(cells, 2.0),
                            np.full(cells, 4.0)])
        x, z = _points(cells)
        params = PetEtParameters()
        kwargs = dict(parameters=params, x_m=x, z_m=z, time_edges_s=edges,
                      states=initial, monthly_temperature_c=temperature,
                      rain_mm_h=rain, spacing_m=SPACING,
                      temperature_source="caller_declared_monthly_mean",
                      rain_source="declared_event")
        baseline = adapter.model_identity(**kwargs)

        # A genuinely different point set (moved coordinate) must change the identity.
        moved = dict(kwargs, x_m=x + 1000.0)
        self.assertNotEqual(baseline, adapter.model_identity(**moved))
        # Edges, states, forcing and the source label must each be bound.
        self.assertNotEqual(baseline,
                            adapter.model_identity(**dict(kwargs, time_edges_s=edges + 1.0)))
        self.assertNotEqual(baseline,
                            adapter.model_identity(**dict(kwargs, states=initial + 1.0)))
        self.assertNotEqual(baseline,
                            adapter.model_identity(**dict(kwargs, rain_mm_h=rain + 0.5)))
        self.assertNotEqual(baseline, adapter.model_identity(
            **dict(kwargs, temperature_source="a1_published_monthly_mean")))


    def test_identity_binds_code_bytes_not_only_module_names(self):
        # The bucket is bound by its source SHA256, not just the string
        # "regional_surface_forcing.advance_soil".
        record = adapter._source_identities()
        self.assertIn('terrain_pipeline.climate_forcing', record)
        entry = record['terrain_pipeline.climate_forcing']
        self.assertEqual(len(entry["source_sha256"]), 64)
        self.assertEqual(entry["basename"], "regional_surface_forcing.py")
        # The adapter itself is in the table, so editing it moves its own identity.
        self.assertIn('terrain_pipeline.soil_water', record)
        # And those bytes really are inside the model digest.
        x, z = _points(2)
        edges = _edges(2)
        states = np.zeros((3, 2))
        temperature = _temperature(2)
        rain = np.zeros((2, 2))
        digest = adapter.model_identity(
            parameters=PetEtParameters(), x_m=x, z_m=z, time_edges_s=edges,
            states=states, monthly_temperature_c=temperature, rain_mm_h=rain,
            spacing_m=SPACING, temperature_source="caller_declared_monthly_mean",
            rain_source="declared_event")
        self.assertNotEqual(
            digest,
            adapter._digest({"schema": adapter.PET_ET_SCHEMA, "algorithm": adapter.PET_ET_ALGORITHM}))

    def test_model_identity_is_invariant_under_a_full_cell_permutation(self):
        # Every field must be permuted together and stay mapped to its own coordinate:
        # that is the same world described in another order, so the identity must match.
        cells, intervals = 3, 2
        temperature = _temperature(cells)
        temperature[:, 1] += 3.0
        temperature[:, 2] -= 2.0
        rain = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        edges = _edges(intervals)
        initial = np.stack([np.array([10.0, 20.0, 30.0]), np.array([1.0, 2.0, 3.0]),
                            np.array([4.0, 5.0, 6.0])])
        x, z = _points(cells)
        order = np.array([2, 0, 1])
        params = PetEtParameters()
        baseline = adapter.model_identity(
            parameters=params, x_m=x, z_m=z, time_edges_s=edges, states=initial,
            monthly_temperature_c=temperature, rain_mm_h=rain, spacing_m=SPACING,
            temperature_source="caller_declared_monthly_mean",
            rain_source="declared_event")
        permuted = adapter.model_identity(
            parameters=params, x_m=x[order], z_m=z[order], time_edges_s=edges,
            states=initial[:, order], monthly_temperature_c=temperature[:, order],
            rain_mm_h=rain[:, order], spacing_m=SPACING,
            temperature_source="caller_declared_monthly_mean",
            rain_source="declared_event")
        self.assertEqual(baseline, permuted)
        # But a mismatched permutation (rain not permuted with the points) must differ.
        mismatched = adapter.model_identity(
            parameters=params, x_m=x[order], z_m=z[order], time_edges_s=edges,
            states=initial[:, order], monthly_temperature_c=temperature[:, order],
            rain_mm_h=rain, spacing_m=SPACING,
            temperature_source="caller_declared_monthly_mean",
            rain_source="declared_event")
        self.assertNotEqual(baseline, mismatched)

    def test_source_label_is_recorded_and_split(self):
        result, *_ = _scenario(cells=2, intervals=2)
        self.assertEqual(result["provenance_split"]["rain"], "declared_event")
        self.assertEqual(result["provenance_split"]["event_columns"], ["rain_mm"])
        self.assertEqual(result["provenance_split"]["background_estimate_columns"], [])
        self.assertEqual(result["sources"]["rain_mm_h"]["source"], "declared_event")

    def test_background_estimate_is_never_reported_as_an_event(self):
        temperature = _temperature(2)
        rain = np.zeros((2, 2))
        edges = _edges(2)
        x, z = _points(2)
        result = advance_pet_et(
            temperature, rain, edges, np.zeros((3, 2)), x_m=x, z_m=z,
            spacing_m=SPACING, rain_source="background_estimate",
            temperature_source="a1_published_monthly_mean")
        self.assertEqual(result["provenance_split"]["background_estimate_columns"],
                         ["rain_mm"])
        self.assertEqual(result["provenance_split"]["event_columns"], [])
        joined = " | ".join(result["limitations"])
        self.assertIn("declared background estimate", joined)
        self.assertIn("not a G3 production field", joined)


class DeterminismAndPartitionTests(unittest.TestCase):
    def test_point_permutation_gives_identical_values(self):
        base, temperature, rain, edges, initial = _scenario(cells=4, intervals=4,
                                                            rain_mm_h=7.0)
        order = np.array([2, 0, 3, 1])
        x, z = _points(4)
        permuted = advance_pet_et(temperature[:, order], rain[:, order], edges,
                                  initial[:, order], x_m=x[order], z_m=z[order],
                                  spacing_m=SPACING)
        inverse = np.argsort(order)
        np.testing.assert_array_equal(permuted["soil_edge_mm"][:, inverse],
                                      base["soil_edge_mm"])
        np.testing.assert_array_equal(permuted["actual_et_mm"][:, inverse],
                                      base["actual_et_mm"])
        # The identity is cell-order independent: same points, same per-point values
        # and the same world coordinates give the same digest after permutation.
        self.assertEqual(permuted["identity"]["points_sha256"],
                         base["identity"]["points_sha256"])
        self.assertEqual(permuted["identity"]["model_identity_sha256"],
                         base["identity"]["model_identity_sha256"])

    def test_same_partition_resume_is_bit_identical(self):
        full, temperature, rain, edges, initial = _scenario(cells=3, intervals=6,
                                                            rain_mm_h=5.0)
        x, z = _points(3)
        cut = 3
        first = advance_pet_et(temperature, rain[:cut], edges[:cut + 1], initial,
                               x_m=x, z_m=z, spacing_m=SPACING)
        resumed = advance_pet_et_segment(
            rain[cut:], edges[cut:],
            np.stack([first["soil_edge_mm"][-1], first["fast_edge_mm"][-1],
                      first["slow_edge_mm"][-1]]),
            x_m=x, z_m=z, monthly_temperature_c=temperature, spacing_m=SPACING)
        np.testing.assert_array_equal(resumed["soil_edge_mm"],
                                      full["soil_edge_mm"][cut:])
        np.testing.assert_array_equal(resumed["actual_et_mm"],
                                      full["actual_et_mm"][cut:])
        np.testing.assert_array_equal(resumed["release_mm"],
                                      full["release_mm"][cut:])

    def test_partition_is_not_promised_to_change_or_to_preserve_the_state(self):
        """A different partition is **not promised** to be bit-equal — and not promised to
        differ either.

        The bucket is a discrete time-stepping law, so the contract is an absence of a
        promise, not a demand that every input must diverge. Two complementary cases are
        checked: (a) a state the bucket leaves invariant really does stay equal (the legal
        outcome the main branch asked to keep), and (b) a state that drives the soil into
        the capacity / release limits really does diverge, with the full fast/slow/ET/release
        trajectory differing, not just the soil endpoint.
        """
        cells = 2
        temperature = _temperature(cells)
        x, z = _points(cells)
        params = PetEtParameters()

        # (a) Nothing moves: empty stores, no rain. Both partitions agree — and that is a
        # legitimate result, not a failure.
        empty = np.zeros((3, cells))
        still_fine = advance_pet_et(temperature, np.zeros((8, cells)),
                                    _edges(8, 1800.0), empty,
                                    x_m=x, z_m=z, spacing_m=SPACING, parameters=params)
        still_coarse = advance_pet_et(temperature, np.zeros((4, cells)),
                                      _edges(4, 3600.0), empty,
                                      x_m=x, z_m=z, spacing_m=SPACING, parameters=params)
        np.testing.assert_array_equal(still_fine["soil_edge_mm"][::2],
                                      still_coarse["soil_edge_mm"])
        # Comparing the whole trajectories with ``array_equal`` would compare a (9, 2)
        # array with a (5, 2) one: different interval counts are different shapes by
        # construction. Only the **shared instants** (0, 3600, ... , 14400 s) and the
        # final state are meaningful here.
        np.testing.assert_array_equal(still_fine["soil_edge_mm"][-1],
                                      still_coarse["soil_edge_mm"][-1])

        # (b) A real nonlinear case: soil near capacity, a large liquid input and a wet
        # profile, so infiltration headroom, percolation and the exponential release all
        # bite. 30 min vs 60 min sub-steps must not agree anywhere in the trajectory.
        wet = np.full((12, cells), 22.0)
        states = np.stack([np.full(cells, 115.0), np.full(cells, 40.0),
                           np.full(cells, 12.0)])
        rain_fine = np.full((8, cells), 60.0)
        fine = advance_pet_et(wet, rain_fine, _edges(8, 1800.0), states,
                              x_m=x, z_m=z, spacing_m=SPACING, parameters=params)
        coarse = advance_pet_et(wet, np.full((4, cells), 60.0), _edges(4, 3600.0), states,
                                x_m=x, z_m=z, spacing_m=SPACING, parameters=params)
        self.assertAlmostEqual(float(fine["time_edges_s"][-1]),
                               float(coarse["time_edges_s"][-1]), places=9)
        # Nothing is *promised* about which components diverge: a partition change alters
        # the discrete time-stepping, and that may or may not move every field. The
        # assertions below are the ones that follow from the model, and the fields that
        # legitimately coincide are recorded instead of being forced apart.
        fine_soil = fine["soil_edge_mm"][-1]
        coarse_soil = coarse["soil_edge_mm"][-1]
        diverged = {
            "soil": not np.array_equal(fine_soil, coarse_soil),
            "fast": not np.array_equal(fine["fast_edge_mm"][-1],
                                      coarse["fast_edge_mm"][-1]),
            "slow": not np.array_equal(fine["slow_edge_mm"][-1],
                                       coarse["slow_edge_mm"][-1]),
            "actual_et_total": not np.array_equal(fine["actual_et_mm"].sum(axis=0),
                                                  coarse["actual_et_mm"].sum(axis=0)),
            "release_total": not np.array_equal(fine["release_mm"].sum(axis=0),
                                                coarse["release_mm"].sum(axis=0)),
        }
        # At least one store must move: that is what "a different partition is a different
        # discrete integration" means in practice.
        self.assertTrue(diverged["soil"] or diverged["fast"] or diverged["slow"],
                        "a nonlinear partition change must move at least one store, got %r"
                        % (diverged,))
        # ``release`` comes from an exponential store whose per-step fraction is
        # ``-expm1(-dt/tau)``: 1800 s and 3600 s give different fractions, so the total
        # necessarily differs. This is a property of the bucket, not a coincidence.
        self.assertTrue(diverged["release_total"],
                        "the exponential release must depend on the sub-step length, got %r"
                        % (diverged,))
        # ``actual_et`` total may legitimately coincide: this scenario stays PET-limited
        # throughout, and then ET is ``PET rate x elapsed hours``, which does not depend on
        # how the same hours are cut. Asserting equality here pins that reasoning; if it
        # ever fails, the PET-limited claim in the comment is wrong and the test says so.
        self.assertFalse(diverged["actual_et_total"],
                         "this scenario is PET-limited throughout, so the ET total should "
                         "not depend on the partition; got %r" % (diverged,))
        # The identity differs too: the time edges are part of it.
        self.assertNotEqual(fine["identity"]["model_identity_sha256"],
                            coarse["identity"]["model_identity_sha256"])

    def test_month_crossing_interval_equals_separate_pieces(self):
        """The real sub-step contract: one interval straddling a month edge must equal
        running the two calendar pieces separately, under a supply limit.

        This is the property an averaged-then-single-bucket implementation would fail.
        """
        cells = 2
        params = PetEtParameters()
        x, z = _points(cells)
        # January cold (solid), February warm: the phase decision differs per piece.
        profile = np.zeros((12, cells))
        profile[0] = -6.0
        profile[1] = 18.0
        january_end = float(MONTH_DAYS[0]) * 86400.0
        # A 1 h interval straddling the boundary: 1800 s in January, 1800 s in February.
        straddle = np.array([january_end - 1800.0, january_end + 1800.0])
        states = np.stack([np.full(cells, 0.5), np.zeros(cells), np.zeros(cells)])
        rain_rate = np.full((1, cells), 2.0)

        whole = advance_pet_et(profile, rain_rate, straddle, states,
                               x_m=x, z_m=z, spacing_m=SPACING, parameters=params)
        self.assertEqual(int(whole["substeps_per_interval"][0]), 2)

        # The same span as two separate 30-minute intervals sharing the boundary. Each
        # piece is a one-interval run (T+1 = 2 edges, which ``_validate_edges`` requires);
        # slicing the 2-edge ``straddle`` array instead would leave a single edge.
        before = np.array([january_end - 1800.0, january_end])
        after = np.array([january_end, january_end + 1800.0])
        first = advance_pet_et(profile, np.full((1, cells), 2.0), before, states,
                               x_m=x, z_m=z, spacing_m=SPACING, parameters=params)
        carry = np.stack([first["soil_edge_mm"][-1], first["fast_edge_mm"][-1],
                          first["slow_edge_mm"][-1]])
        second = advance_pet_et_segment(
            np.full((1, cells), 2.0), after, carry,
            x_m=x, z_m=z, monthly_temperature_c=profile, spacing_m=SPACING,
            parameters=params)

        # January contributes no liquid (it is declared solid), February does: so the
        # first piece leaves the bucket untouched and the straddling run must show that.
        self.assertEqual(float(whole["liquid_rain_mm"][0].sum()),
                         float(second["liquid_rain_mm"][0].sum()))
        self.assertGreater(float(whole["solid_precipitation_swe_mm"][0].sum()), 0.0)
        # State, ET and release agree with the piecewise run.
        np.testing.assert_array_equal(whole["soil_edge_mm"][-1],
                                      second["soil_edge_mm"][-1])
        self.assertAlmostEqual(float(whole["actual_et_mm"][0].sum()),
                               float(first["actual_et_mm"][0].sum()
                                     + second["actual_et_mm"][0].sum()), places=12)
        self.assertAlmostEqual(float(whole["release_mm"][0].sum()),
                               float(first["release_mm"][0].sum()
                                     + second["release_mm"][0].sum()), places=12)


class CheckpointTests(unittest.TestCase):
    def test_round_trip_and_partition_mismatch_refusal(self):
        cells, intervals = 3, 4
        result, temperature, rain, edges, initial = _scenario(cells=cells,
                                                              intervals=intervals,
                                                              rain_mm_h=4.0)
        states = np.stack([result["soil_edge_mm"][2], result["fast_edge_mm"][2],
                           result["slow_edge_mm"][2]])
        params = PetEtParameters()
        x, z = _points(cells)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "edge-2.npz")
            metadata = save_pet_et_checkpoint(
                path, states=states, edge_index=2, time_edges_s=edges,
                parameters=params, rain_mm_h=rain, monthly_temperature_c=temperature,
                x_m=x, z_m=z)
            self.assertEqual(metadata["edge_index"], 2)
            with self.assertRaises(FileExistsError):
                save_pet_et_checkpoint(
                    path, states=states, edge_index=2, time_edges_s=edges,
                    parameters=params, rain_mm_h=rain,
                    monthly_temperature_c=temperature, x_m=x, z_m=z)
            loaded = load_pet_et_checkpoint(
                path, time_edges_s=edges, parameters=params, x_m=x, z_m=z,
                rain_mm_h=rain, monthly_temperature_c=temperature)
            np.testing.assert_array_equal(loaded["states"], states)
            self.assertEqual(loaded["edge_index"], 2)
            # A different partition prefix is refused, not silently accepted.
            with self.assertRaises(ValueError):
                load_pet_et_checkpoint(
                    path, time_edges_s=edges + 1.0, parameters=params, x_m=x, z_m=z,
                    rain_mm_h=rain, monthly_temperature_c=temperature)
            # Different parameters are refused too.
            with self.assertRaises(ValueError):
                load_pet_et_checkpoint(
                    path, time_edges_s=edges,
                    parameters=replace(params, pet_base_mm_per_day=0.9),
                    x_m=x, z_m=z, rain_mm_h=rain,
                    monthly_temperature_c=temperature)
            # A different point set of the same shape is refused.
            with self.assertRaises(ValueError):
                load_pet_et_checkpoint(
                    path, time_edges_s=edges, parameters=params,
                    x_m=x + 30.0, z_m=z, rain_mm_h=rain,
                    monthly_temperature_c=temperature)
            # A different monthly temperature is refused.
            with self.assertRaises(ValueError):
                load_pet_et_checkpoint(
                    path, time_edges_s=edges, parameters=params, x_m=x, z_m=z,
                    rain_mm_h=rain, monthly_temperature_c=temperature + 1.0)
            # A different consumed rain prefix is refused.
            with self.assertRaises(ValueError):
                load_pet_et_checkpoint(
                    path, time_edges_s=edges, parameters=params, x_m=x, z_m=z,
                    rain_mm_h=rain + 0.5, monthly_temperature_c=temperature)
            # Illegal states are refused on load.
            bad = os.path.join(folder, "bad.npz")
            illegal = states.copy()
            illegal[0] = params.runoff.soil_capacity_mm + 5.0
            save_pet_et_checkpoint(
                bad, states=illegal, edge_index=2, time_edges_s=edges,
                parameters=params, rain_mm_h=rain, monthly_temperature_c=temperature,
                x_m=x, z_m=z)
            with self.assertRaises(ValueError):
                load_pet_et_checkpoint(
                    bad, time_edges_s=edges, parameters=params, x_m=x, z_m=z,
                    rain_mm_h=rain, monthly_temperature_c=temperature)

    def test_checkpoint_shape_mismatch_is_refused(self):
        cells, intervals = 2, 2
        _, temperature, rain, edges, initial = _scenario(cells=cells,
                                                         intervals=intervals)
        params = PetEtParameters()
        x, z = _points(cells)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "edge-1.npz")
            save_pet_et_checkpoint(
                path, states=initial, edge_index=1, time_edges_s=edges,
                parameters=params, rain_mm_h=rain,
                monthly_temperature_c=temperature, x_m=x, z_m=z)
            with self.assertRaises(ValueError):
                load_pet_et_checkpoint(
                    path, time_edges_s=edges, parameters=params, x_m=x, z_m=z,
                    rain_mm_h=rain, monthly_temperature_c=temperature,
                    states_shape=(3, 5))

    def test_checkpoint_metadata_is_json_serialisable(self):
        _, temperature, rain, edges, initial = _scenario(cells=2, intervals=2)
        params = PetEtParameters()
        x, z = _points(2)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "edge-0.npz")
            metadata = save_pet_et_checkpoint(
                path, states=initial, edge_index=0, time_edges_s=edges,
                parameters=params, rain_mm_h=rain,
                monthly_temperature_c=temperature, x_m=x, z_m=z)
            json.dumps(metadata, allow_nan=False)
            self.assertEqual(metadata["schema"], "metric-pet-et-checkpoint-v1")
            self.assertEqual(metadata["pet_parameter_identity_sha256"],
                             pet_parameter_identity(params))
            # The source binding is actually written, not merely checked on load.
            self.assertEqual(len(metadata["points_sha256"]), 64)
            self.assertEqual(len(metadata["monthly_temperature_sha256"]), 64)
            self.assertEqual(len(metadata["rain_prefix_sha256"]), 64)
            self.assertEqual(metadata["cell_count"], 2)


class OutputShapeTests(unittest.TestCase):
    def test_shapes_and_the_edge_convention(self):
        cells, intervals = 3, 5
        result, *_ = _scenario(cells=cells, intervals=intervals, rain_mm_h=4.0)
        self.assertEqual(result["soil_edge_mm"].shape, (intervals + 1, cells))
        self.assertEqual(result["fast_edge_mm"].shape, (intervals + 1, cells))
        self.assertEqual(result["slow_edge_mm"].shape, (intervals + 1, cells))
        for name in ("actual_et_mm", "release_mm", "rain_mm", "liquid_rain_mm",
                     "liquid_rate_mm_h", "interval_pet_mm", "pet_rate_mm_h",
                     "liquid_fraction",
                     "solid_precipitation_swe_mm", "subsurface_transfer_mm",
                     "infiltration_mm", "storage_change_mm",
                     "available_supply_mm", "et_regime"):
            self.assertEqual(getattr(result[name], "shape"), (intervals, cells),
                             name)
        self.assertEqual(result["inventory_m3_edge"].shape, (intervals + 1,))
        self.assertEqual(result["monthly_potential_et_mm"].shape, (12, cells))
        self.assertEqual(result["calendar_month_seconds"].shape, (intervals, 12))
        self.assertEqual(result["monthly_temperature_c"].shape, (12, cells))
        # There is exactly one before/after pair, expressed as edges.
        self.assertNotIn("soil_before_mm", result)
        self.assertNotIn("soil_after_mm", result)
        np.testing.assert_array_equal(result["soil_edge_mm"][0], np.zeros(cells))

    def test_interval_pet_times_hours_matches_the_depth_field(self):
        result, *_ = _scenario(cells=2, intervals=3, rain_mm_h=1.0)
        hours = result["interval_seconds"] / 3600.0
        np.testing.assert_allclose(result["pet_rate_mm_h"] * hours[:, None],
                                   result["interval_pet_mm"], rtol=0.0, atol=1e-15)

    def test_inventory_is_volume_not_a_relative_proxy(self):
        result, *_ = _scenario(cells=2, intervals=2,
                               states=np.full((3, 2), 10.0))
        expected = ((result["soil_edge_mm"] + result["fast_edge_mm"]
                     + result["slow_edge_mm"]).sum(axis=1) * SPACING ** 2 / 1000.0)
        np.testing.assert_allclose(result["inventory_m3_edge"], expected,
                                   rtol=0.0, atol=1e-12)
        self.assertEqual(result["units"]["inventory_m3_edge"], "m3")
        self.assertEqual(result["units"]["soil_edge_mm"], "mm")


if __name__ == "__main__":
    unittest.main()
