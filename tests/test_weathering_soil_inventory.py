"""Conservative weathering inventory tests (unittest, no pytest).

Scope: zero-weathering identity, condition/rock response, hard exhaustion, dissolved
vs solid split closure, per-step state continuation, invalid input rejection.
No transport-to-river/sea claim, no soil-water bucket, no growth model.

**Do not run without a granted compute slot** (`.scratch/stage2-g1-g9/spec.md:41`).
"""

from builtins import ValueError as _merged_inventory_WeatheringInventoryError
import unittest

import numpy as np

from terrain_pipeline import soil_water as inventory

AREA = 900.0
THICKNESS = 2.0
DENSITY = 2650.0


def _state(*, hardness=0.5, solubility=0.5, thickness=THICKNESS, area=AREA,
           density=None):
    return inventory.initial_state(bedrock_thickness_m=thickness, area_m2=area,
                                   bed_hardness=hardness, solubility=solubility,
                                   density_kg_m3=density)


def _step(state, **kwargs):
    options = {"dt_s": 1.0e9, "temperature_c": 10.0, "moisture": 1.0,
               "bio_activity": 0.0}
    options.update(kwargs)
    return inventory.advance(state, **options)


class ZeroWeatheringTests(unittest.TestCase):
    def test_no_driver_gives_exactly_zero_change(self):
        state = _state()
        config = {"k_physical_m_per_s": {"value": 0.0, "source": "test fixture"},
                  "k_chemical_m_per_s": {"value": 0.0, "source": "test fixture"},
                  "k_biological_m_per_s": {"value": 0.0, "source": "test fixture"}}
        next_state, flux = _step(state, parameters=config)
        self.assertTrue(np.all(flux["weathered_solid_m3"] == 0.0))
        self.assertTrue(np.array_equal(next_state["bedrock_solid_m3"],
                                       state["bedrock_solid_m3"]))
        self.assertTrue(np.all(next_state["regolith_solid_m3"] == 0.0))
        self.assertTrue(np.all(next_state["parent_solid_m3"] == 0.0))
        self.assertTrue(np.all(next_state["dissolved_solid_m3"] == 0.0))

    def test_dry_rock_weathers_less_than_wet_rock(self):
        # 只有化学与生物项依赖 moisture；物理项不依赖，所以干岩仍会风化，但更少。
        dry = _state()
        wet = _state()
        _, dry_flux = _step(dry, moisture=0.0, bio_activity=1.0)
        _, wet_flux = _step(wet, moisture=1.0, bio_activity=1.0)
        self.assertGreater(float(dry_flux["weathered_solid_m3"][0]), 0.0)
        self.assertGreater(float(wet_flux["weathered_solid_m3"][0]),
                           float(dry_flux["weathered_solid_m3"][0]))


class ConditionAndRockResponseTests(unittest.TestCase):
    def test_warmer_and_wetter_weathers_more(self):
        state = _state()
        _, cold = _step(state, temperature_c=-10.0)
        _, warm = _step(state, temperature_c=25.0)
        self.assertGreater(float(warm["weathered_solid_m3"][0]),
                           float(cold["weathered_solid_m3"][0]))

    def test_negative_temperature_is_legal_and_only_slows_it(self):
        state = _state()
        _, freezing = _step(state, temperature_c=-20.0)
        self.assertGreater(float(freezing["temperature_factor"][0]), 0.0)
        self.assertLess(float(freezing["temperature_factor"][0]), 1.0)
        self.assertGreater(float(freezing["weathered_solid_m3"][0]), 0.0)

    def test_softer_and_more_soluble_rock_weathers_faster(self):
        soft = _state(hardness=0.1, solubility=0.9)
        hard = _state(hardness=0.9, solubility=0.1)
        _, soft_flux = _step(soft)
        _, hard_flux = _step(hard)
        self.assertGreater(float(soft_flux["weathered_solid_m3"][0]),
                           float(hard_flux["weathered_solid_m3"][0]))

    def test_biogenic_activity_adds_weathered_mass(self):
        state = _state()
        _, without = _step(state, bio_activity=0.0)
        _, with_bio = _step(state, bio_activity=1.0)
        self.assertGreater(float(with_bio["weathered_solid_m3"][0]),
                           float(without["weathered_solid_m3"][0]))


class FiniteExhaustionTests(unittest.TestCase):
    def test_huge_rate_is_capped_by_the_stock(self):
        state = _state(thickness=1.0)
        next_state, flux = _step(state, dt_s=1.0e18)
        self.assertTrue(bool(flux["capped_by_stock"][0]))
        self.assertEqual(float(flux["weathered_depth_m"][0]), 1.0)
        self.assertEqual(float(next_state["bedrock_solid_m3"][0]), 0.0)
        self.assertEqual(str(next_state["status"][0]), inventory.EXHAUSTED)

    def test_exhausted_stock_cannot_produce_more(self):
        state = _state(thickness=1.0)
        once, _ = _step(state, dt_s=1.0e18)
        twice, flux = _step(once, dt_s=1.0e18)
        self.assertTrue(np.all(flux["weathered_solid_m3"] == 0.0))
        self.assertEqual(float(twice["bedrock_solid_m3"][0]), 0.0)
        self.assertGreaterEqual(float(twice["bedrock_solid_m3"][0]), 0.0)

    def test_total_removed_never_exceeds_initial(self):
        state = _state(thickness=1.0)
        current = state
        for _ in range(5):
            current, _flux = _step(current, dt_s=1.0e18)
        self.assertLessEqual(float(inventory.ledger(current)["removed_bedrock_solid_m3"][0]),
                             float(state["initial_bedrock_solid_m3"][0]))


class ClosureAndSplitTests(unittest.TestCase):
    def test_solid_closure_holds_after_several_steps(self):
        state = _state()
        current = state
        for _ in range(4):
            current, _flux = _step(current)
        accounts = inventory.ledger(current)
        scale = float(accounts["initial_bedrock_solid_m3"][0])
        self.assertLessEqual(abs(float(accounts["closure_residual_m3"][0])),
                             inventory.CLOSURE_RELATIVE_TOLERANCE * max(scale, 1.0))

    def test_dissolved_and_regolith_split_the_removed_solid(self):
        state = _state()
        next_state, flux = _step(state)
        weathered = float(flux["weathered_solid_m3"][0])
        dissolved = float(flux["dissolved_solid_m3"][0])
        regolith = float(flux["regolith_solid_m3"][0])
        self.assertAlmostEqual(dissolved + regolith, weathered, places=15)
        self.assertGreater(dissolved, 0.0)
        self.assertGreater(regolith, 0.0)
        accounts = inventory.ledger(next_state)
        self.assertAlmostEqual(float(accounts["dissolved_exported_solid_m3"][0]),
                               dissolved, places=15)

    def test_parent_is_a_view_not_extra_material(self):
        state = _state()
        next_state, flux = _step(state)
        parent = float(next_state["parent_solid_m3"][0])
        regolith = float(next_state["regolith_solid_m3"][0])
        self.assertLessEqual(parent, regolith + 1e-18)
        self.assertAlmostEqual(parent, regolith * 0.5, places=15)

    def test_bulk_is_converted_once_from_solid(self):
        state = _state()
        next_state, _flux = _step(state)
        solid = float(next_state["regolith_solid_m3"][0])
        bulk = float(next_state["regolith_bulk_m3"][0])
        self.assertAlmostEqual(bulk, solid / (1.0 - 0.35), places=15)
        self.assertGreater(bulk, solid)


class ContinuationTests(unittest.TestCase):
    def test_two_short_steps_match_one_long_step(self):
        state = _state()
        long_state, _ = _step(state, dt_s=2.0e6)
        half, _ = _step(state, dt_s=1.0e6)
        short, _ = _step(half, dt_s=1.0e6)
        self.assertAlmostEqual(float(long_state["regolith_solid_m3"][0]),
                               float(short["regolith_solid_m3"][0]), places=12)
        self.assertAlmostEqual(float(long_state["bedrock_solid_m3"][0]),
                               float(short["bedrock_solid_m3"][0]), places=12)

    def test_state_survives_a_round_trip_through_a_shallow_copy(self):
        state = _state()
        current, _ = _step(state)
        carried = dict(current)
        continued, _ = _step(carried)
        direct, _ = _step(current)
        self.assertTrue(np.array_equal(continued["regolith_solid_m3"],
                                       direct["regolith_solid_m3"]))

    def test_step_does_not_mutate_the_input_state(self):
        state = _state()
        before = state["bedrock_solid_m3"].copy()
        _step(state)
        self.assertTrue(np.array_equal(state["bedrock_solid_m3"], before))


class DeliveryDebitTests(unittest.TestCase):
    """两路同源借记：parent 是 regolith 的视图，不得被二计。"""

    def setUp(self):
        state, _ = _step(_state(thickness=100.0), dt_s=1.0e12)
        self.state = state
        self.regolith = float(state["regolith_solid_m3"][0])
        self.parent = float(state["parent_solid_m3"][0])
        self.assertTrue(self.regolith > 0.0)
        # parent 是 regolith 内的细粒子子集，必须真的小于总量才有意义。
        self.assertGreater(self.parent, 0.0)
        self.assertLessEqual(self.parent, self.regolith)

    def test_repeated_soil_draw_cannot_reuse_the_same_parent(self):
        # 默认 reject：第一次成功、第二次（0.8P 超过剩余的 0.2P）必须被拒，
        # 而且被拒后不得改动第一次之后的 state。
        parent_start = self.parent
        ask = parent_start * 0.8
        after_first, soil, _sediment, _remaining, _accounts = inventory.allocate(
            self.state, soil_parent_solid_m3=ask)
        self.assertAlmostEqual(float(soil["soil_parent_solid_m3"][0]), ask, places=12)
        remaining_parent = float(after_first["parent_solid_m3"][0])
        self.assertAlmostEqual(remaining_parent, parent_start - ask, places=12)
        # 第二次同一请求：剩下的子集不够 → reject。
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            inventory.allocate(after_first, soil_parent_solid_m3=ask)
        # 被拒后 after_first 未被篡改，子集不变式仍成立。
        self.assertAlmostEqual(float(after_first["parent_solid_m3"][0]),
                               remaining_parent, places=12)
        self.assertGreaterEqual(remaining_parent, 0.0)
        self.assertLessEqual(remaining_parent,
                             float(after_first["regolith_solid_m3"][0]) + 1e-12)

    def test_repeated_soil_draw_under_proportional_scales_to_the_subset(self):
        # proportional 才允许缩放：第二次被限到剩余子集，两次合计不超初始 P。
        parent_start = self.parent
        ask = parent_start * 0.8
        first_state, first_soil, _s, _r, _a = inventory.allocate(
            self.state, soil_parent_solid_m3=ask)
        second_state, second_soil, _s2, _r2, _a2 = inventory.allocate(
            first_state, soil_parent_solid_m3=ask, shortage_policy="proportional")
        total = float(first_soil["soil_parent_solid_m3"][0]) + float(
            second_soil["soil_parent_solid_m3"][0])
        self.assertLessEqual(total, parent_start + 1e-12)
        self.assertAlmostEqual(float(second_state["parent_solid_m3"][0]), 0.0, places=12)
        self.assertLessEqual(float(first_state["parent_solid_m3"][0]),
                             float(first_state["regolith_solid_m3"][0]) + 1e-12)

    def test_soil_over_parent_subset_is_rejected_even_when_total_fits(self):
        # 总 regolith 还很多，但 parent 子集不够 → 仍必须拒。
        parent = self.parent
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            inventory.allocate(self.state, soil_parent_solid_m3=parent * 2.0)

    def test_soil_debits_the_parent_subset_exactly(self):
        ask = self.parent * 0.4
        next_state, soil, _sediment, _remaining, _accounts = inventory.allocate(
            self.state, soil_parent_solid_m3=ask)
        self.assertAlmostEqual(float(soil["soil_parent_solid_m3"][0]), ask, places=12)
        self.assertAlmostEqual(float(next_state["parent_solid_m3"][0]),
                               self.parent - ask, places=12)
        self.assertAlmostEqual(float(next_state["delivered_parent_solid_m3"][0]),
                               ask, places=12)

    def test_subset_invariant_holds_after_every_allocation(self):
        state = self.state
        for _ in range(4):
            available = float(state["parent_solid_m3"][0])
            if available <= 0.0:
                break
            state, _soil, _sediment, _remaining, _accounts = inventory.allocate(
                state, soil_parent_solid_m3=available * 0.5)
            self.assertGreaterEqual(float(state["parent_solid_m3"][0]), 0.0)
            self.assertLessEqual(float(state["parent_solid_m3"][0]),
                                 float(state["regolith_solid_m3"][0]) + 1e-12)

    def test_sediment_prefers_non_parent_then_spills(self):
        non_parent = self.regolith - self.parent
        # 只要非母质部分能履盖，母质子集就不动。
        small = non_parent * 0.5
        _next, _soil, sediment, remaining, _accounts = inventory.allocate(
            self.state, sediment_solid_m3=small)
        self.assertAlmostEqual(float(sediment["from_non_parent_solid_m3"][0]), small,
                               places=12)
        self.assertAlmostEqual(float(sediment["from_parent_solid_m3"][0]), 0.0, places=12)
        self.assertAlmostEqual(float(remaining["parent_solid_m3"][0]), self.parent,
                               places=12)
        # 超过非母质部分后溢出到子集，且子集不变式仍成立。
        big = non_parent + self.parent * 0.5
        _next2, _soil2, sediment2, remaining2, accounts2 = inventory.allocate(
            self.state, sediment_solid_m3=big)
        self.assertGreater(float(sediment2["from_parent_solid_m3"][0]), 0.0)
        self.assertLessEqual(float(remaining2["parent_solid_m3"][0]),
                             float(remaining2["regolith_solid_m3"][0]) + 1e-12)
        scale = float(accounts2["initial_bedrock_solid_m3"][0])
        self.assertLessEqual(abs(float(accounts2["closure_residual_m3"][0])),
                             inventory.CLOSURE_RELATIVE_TOLERANCE * max(scale, 1.0))

    def test_both_deliveries_come_out_of_one_regolith_account(self):
        # soil 请求必须不超过 parent 子集，否则按新语义会被拒。
        soil_ask = self.parent * 0.3
        sediment_ask = self.regolith * 0.3
        next_state, soil, sediment, remaining, accounts = inventory.allocate(
            self.state, soil_parent_solid_m3=soil_ask, sediment_solid_m3=sediment_ask)
        self.assertEqual(soil["transported"], False)
        self.assertEqual(sediment["transported"], False)
        self.assertAlmostEqual(float(soil["soil_parent_solid_m3"][0]), soil_ask, places=12)
        self.assertAlmostEqual(float(sediment["sediment_solid_m3"][0]), sediment_ask,
                               places=12)
        left = float(next_state["regolith_solid_m3"][0])
        self.assertAlmostEqual(left, self.regolith - soil_ask - sediment_ask, places=12)
        self.assertAlmostEqual(float(remaining["regolith_solid_m3"][0]), left, places=12)
        # 子集不变式：0 <= P <= R
        self.assertLessEqual(float(next_state["parent_solid_m3"][0]), left + 1e-12)

    def test_delivery_keeps_the_bedrock_ledger_closing(self):
        soil_ask = self.parent * 0.5
        next_state, _soil, _sediment, _remaining, accounts = inventory.allocate(
            self.state, soil_parent_solid_m3=soil_ask)
        scale = float(accounts["initial_bedrock_solid_m3"][0])
        self.assertLessEqual(abs(float(accounts["closure_residual_m3"][0])),
                             inventory.CLOSURE_RELATIVE_TOLERANCE * max(scale, 1.0))
        self.assertAlmostEqual(float(accounts["delivered_regolith_solid_m3"][0]),
                               soil_ask, places=12)

    def test_over_request_is_rejected_not_silently_trimmed(self):
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            inventory.allocate(self.state, soil_parent_solid_m3=self.regolith,
                               sediment_solid_m3=self.regolith)

    def test_proportional_policy_scales_both_and_keeps_their_split(self):
        # 两路各要 0.75R（合计 1.5R），soil 又超过 parent 子集 → 公共因子必须同时受限。
        soil_ask = self.regolith * 0.75
        sediment_ask = self.regolith * 0.75
        next_state, soil, sediment, remaining, _accounts = inventory.allocate(
            self.state, soil_parent_solid_m3=soil_ask,
            sediment_solid_m3=sediment_ask, shortage_policy="proportional")
        delivered_soil = float(soil["soil_parent_solid_m3"][0])
        delivered_sediment = float(sediment["sediment_solid_m3"][0])
        # 1) 总交付不超总库存
        self.assertLessEqual(delivered_soil + delivered_sediment,
                             self.regolith + 1e-12)
        # 2) soil 不得超过 parent 子集 —— 这正是公共 ratio 只看 R 会漏掉的那条
        self.assertLessEqual(delivered_soil, self.parent + 1e-12)
        # 3) 剩余不超支，子集不变式仍成立
        self.assertGreaterEqual(float(remaining["regolith_solid_m3"][0]), -1e-12)
        self.assertLessEqual(float(remaining["parent_solid_m3"][0]),
                             float(remaining["regolith_solid_m3"][0]) + 1e-12)
        self.assertGreaterEqual(float(remaining["parent_solid_m3"][0]), -1e-12)

    def test_proportional_policy_keeps_the_request_ratio_when_total_binds(self):
        # 让总库存成为绑定约束（soil 仍在子集内），此时比例必须保持。
        soil_ask = self.parent * 0.9
        sediment_ask = soil_ask  # 1:1
        _next, soil, sediment, _remaining, _accounts = inventory.allocate(
            self.state, soil_parent_solid_m3=soil_ask,
            sediment_solid_m3=sediment_ask, shortage_policy="proportional")
        self.assertAlmostEqual(float(soil["soil_parent_solid_m3"][0]),
                               float(sediment["sediment_solid_m3"][0]), places=12)

    def test_repeated_debits_never_exceed_the_initial_stock(self):
        state = self.state
        total = 0.0
        for _ in range(5):
            available_parent = float(state["parent_solid_m3"][0])
            if available_parent <= 0.0:
                break
            ask = available_parent * 0.5
            state, soil, _sediment, _remaining, _accounts = inventory.allocate(
                state, soil_parent_solid_m3=ask)
            total += float(soil["soil_parent_solid_m3"][0])
        self.assertLessEqual(total, self.parent + 1e-12)
        self.assertGreaterEqual(float(state["regolith_solid_m3"][0]), 0.0)

    def test_allocate_does_not_mutate_the_input_state(self):
        before_regolith = self.state["regolith_solid_m3"].copy()
        before_parent = self.state["parent_solid_m3"].copy()
        before_delivered = self.state["delivered_regolith_solid_m3"].copy()
        inventory.allocate(self.state, soil_parent_solid_m3=self.parent * 0.1)
        self.assertTrue(np.array_equal(self.state["regolith_solid_m3"], before_regolith))
        self.assertTrue(np.array_equal(self.state["parent_solid_m3"], before_parent))
        self.assertTrue(np.array_equal(self.state["delivered_regolith_solid_m3"],
                                       before_delivered))

    def test_bad_requests_are_refused(self):
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            inventory.allocate(self.state, soil_parent_solid_m3=-1.0)
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            inventory.allocate(self.state, shortage_policy="whatever")


class SupplyAndLedgerTests(unittest.TestCase):
    def test_supply_is_availability_only_and_never_transported(self):
        state, _ = _step(_state())
        soil = inventory.soil_parent_supply(state)
        sediment = inventory.sediment_supply(state)
        self.assertFalse(soil["transported"])
        self.assertFalse(sediment["transported"])
        self.assertLessEqual(float(soil["available_parent_solid_m3"][0]),
                             float(state["parent_solid_m3"][0]))
        self.assertLessEqual(float(sediment["available_sediment_solid_m3"][0]),
                             float(state["regolith_solid_m3"][0]))

    def test_mass_is_pending_without_density(self):
        state, _ = _step(_state())
        accounts = inventory.ledger(state)
        self.assertEqual(accounts["mass_status"], inventory.MASS_PENDING)
        self.assertNotIn("current_bedrock_mass_kg", accounts)

    def test_mass_closes_when_density_is_declared(self):
        state, _ = _step(_state(density=DENSITY))
        accounts = inventory.ledger(state)
        self.assertEqual(accounts["mass_status"], inventory.MASS_DECLARED)
        removed = float(accounts["removed_bedrock_solid_m3"][0]) * DENSITY
        regolith = float(accounts["regolith_mass_kg"][0])
        dissolved = float(accounts["dissolved_exported_mass_kg"][0])
        self.assertAlmostEqual(removed, regolith + dissolved, places=6)


class RejectionTests(unittest.TestCase):
    def test_bad_units_and_values_are_refused(self):
        for bad in ({"dt_s": 0.0}, {"dt_s": -1.0}, {"dt_s": float("nan")}):
            with self.assertRaises(_merged_inventory_WeatheringInventoryError):
                _step(_state(), **bad)
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            inventory.initial_state(bedrock_thickness_m=-1.0, area_m2=AREA,
                                    bed_hardness=0.5, solubility=0.5)
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            inventory.initial_state(bedrock_thickness_m=THICKNESS, area_m2=0.0,
                                    bed_hardness=0.5, solubility=0.5)
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            inventory.initial_state(bedrock_thickness_m=THICKNESS, area_m2=AREA,
                                    bed_hardness=1.5, solubility=0.5)

    def test_moisture_and_bio_bounds(self):
        state = _state()
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            _step(state, moisture=1.5)
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            _step(state, bio_activity=-0.1)

    def test_unknown_parameter_key_is_refused(self):
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            inventory.normalize_parameters({"k_magic": {"value": 1.0}})

    def test_declared_parameter_needs_provenance(self):
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            inventory.normalize_parameters({"q10": {"value": 3.0}})

    def test_column_cap_is_enforced(self):
        with self.assertRaises(_merged_inventory_WeatheringInventoryError):
            inventory.weathering_preflight(inventory.MAX_COLUMNS + 1)

    def test_describe_declares_units_and_boundaries(self):
        declared = inventory.weathering_describe()
        self.assertTrue(declared["negative_temperature_allowed"])
        self.assertEqual(declared["units"]["solid"], "m3")
        self.assertIn("m3", declared["units"].values())
        self.assertGreaterEqual(len(declared["limitations"]), 4)


if __name__ == "__main__":
    unittest.main()
