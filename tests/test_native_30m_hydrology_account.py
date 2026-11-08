"""Stage p4 gates: native-30 m soil-bucket runoff and the full hydrology ledger.

What these tests pin, and why each one exists
---------------------------------------------
The two modules under test previously carried two real defects that no test caught:

1. ``native_30m_hydrology_ledger`` handed ``[T, Z, X]`` blocks to a kernel that
   accepts exactly ``receiver.shape``, so **every** call raised
   ``local_q_m3_s must have matching shape and exact dtype``. The ledger had never
   run. ``LedgerShapeTests`` and every ledger test below would have failed.
2. The same module compared a rate (``m3/s`` from the accumulation kernel) with an
   interval volume (``m3`` from the bucket) and required them to be equal. No
   correct run could satisfy that; the gate was unsatisfiable by construction.
   ``LedgerPartitionTests.test_four_terms_partition_the_supply`` pins the fixed form.

A third gap was a missing capability rather than a bug: the event dictionary only
reported catchment totals, so per-cell and per-interval local supply, stores,
infiltration, ET, the external loss, the withheld and unknown terms and the outlet
were not available at all. ``CellAccountTests`` covers the opt-in account and
``IdentityStabilityTests`` pins that the default run is unchanged.

Boundaries: every fixture is tens of cells. No 48 km run, no GPU, no bundle
publication, no old release or verification record touched.
"""
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np

from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.runoff import simulate_rainfall_runoff as simulate_rainfall_runoff
from terrain_pipeline.surface_rivers.native_30m_hydrology_event import (
    ADAPTER, run_event_with_account)
from terrain_pipeline.surface_rivers.native_30m_hydrology_ledger import (
    ACCOUNT_ALGORITHM, ALGORITHM, MAX_ACCOUNT_BYTES, SUBSEED_PURPOSES,
    account_budget, attribute_declared_nodes, cell_hydrology_account,
    hydrology_ledger, ledger_budget, node_supply_ledger, purpose_subseeds,
    storage_ledger, supply_ledger, unknown_boundary_ledger, window_terminal_kind)
from terrain_pipeline.runoff import run_catchment_event as run_catchment_event


WORLD_SEED = 20261020
SPACING_M = 30.0
CELL_AREA_M2 = SPACING_M * SPACING_M
ROOT = Path(__file__).resolve().parents[1]


def chain_domain(rows=1, columns=4):
    height = np.array([[4.0, 3.0, 2.0, 1.0]], np.float64)
    receiver = np.array([[1, 2, 3, -1]], np.int64)
    mask = np.ones((rows, columns), bool)
    return height, receiver, mask


def bucket_for(rain, *, cells, dt_s=3600.0, parameters=None):
    if parameters is None:
        parameters = RunoffParameters(infiltration_capacity_mm_h=2.0)
    block = np.broadcast_to(np.asarray(rain, np.float64)[:, None],
                            (len(rain), cells)).copy()
    return simulate_rainfall_runoff(block, np.full(cells, CELL_AREA_M2),
                                    dt_s=dt_s, source_id="p4-test",
                                    parameters=parameters)


# --------------------------------------------------------------------------- #
# the shape defect: a ledger call must actually run
# --------------------------------------------------------------------------- #
class LedgerShapeTests(unittest.TestCase):

    def test_a_plain_ledger_call_runs_at_all(self):
        """The defect this fixes: the kernel accepts ``[Z, X]``, not ``[T, Z, X]``."""
        bucket = bucket_for([8.0, 0.0, 0.0], cells=4)
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        valid = np.ones((1, 4), bool)
        ledger = hydrology_ledger(bucket, receiver, valid, cell_area_m2=CELL_AREA_M2,
                                  dt_s=3600.0,
                                  active_cells=np.arange(4, dtype=np.int64),
                                  world_seed=WORLD_SEED)
        self.assertEqual(ledger["algorithm"], ALGORITHM)
        self.assertEqual(ledger["supply"]["cells"], 4)
        self.assertEqual(ledger["supply"]["steps"], 3)

    def test_both_block_spellings_are_accepted_and_a_third_is_refused(self):
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        valid = np.ones((1, 4), bool)
        kinds = window_terminal_kind(receiver, valid)["terminal_kind"]
        flat = np.array([[0.1, 0.2, 0.3, 0.4]], np.float64)
        grid = flat.reshape((1, 1, 4))
        from_flat = unknown_boundary_ledger(receiver, valid, kinds, flat)
        from_grid = unknown_boundary_ledger(receiver, valid, kinds, grid)
        self.assertEqual(from_flat["declared_input_m3_s"],
                         from_grid["declared_input_m3_s"])
        with self.assertRaisesRegex(ValueError, "invalid_local_q_m3_s"):
            unknown_boundary_ledger(receiver, valid, kinds, flat.reshape(1, 2, 2))
        with self.assertRaisesRegex(ValueError, "invalid_local_q_m3_s"):
            unknown_boundary_ledger(receiver, valid, kinds, flat.astype(np.float32))

    def test_a_nonzero_local_q_on_an_inactive_cell_is_refused(self):
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        valid = np.array([[True, False, True, True]])
        kinds = np.full((1, 4), "interior", dtype="U24")
        kinds[0, 1] = "inactive"
        kinds[0, 3] = "retained"
        local = np.array([[0.0, 0.5, 0.0, 0.0]], np.float64)
        with self.assertRaisesRegex(ValueError, "inactive cell"):
            unknown_boundary_ledger(receiver, valid, kinds, local)


# --------------------------------------------------------------------------- #
# the dimension defect: rates and volumes may only be compared after conversion
# --------------------------------------------------------------------------- #
class LedgerPartitionTests(unittest.TestCase):

    def test_four_terms_partition_the_supply(self):
        """``certified retained + certified open + certified unknown + withheld``.

        The earlier revision compared this sum with the bucket's interval *volume*
        while the accumulation kernel reports *rates*, so the gate could never pass.
        """
        bucket = bucket_for([8.0, 0.0, 0.0, 0.0], cells=4)
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        valid = np.ones((1, 4), bool)
        kinds = np.full((1, 4), "interior", dtype="U24")
        kinds[0, 3] = "retained"
        ledger = hydrology_ledger(bucket, receiver, valid, cell_area_m2=CELL_AREA_M2,
                                  dt_s=3600.0,
                                  active_cells=np.arange(4, dtype=np.int64),
                                  terminal_kind=kinds, world_seed=WORLD_SEED)
        boundary = ledger["unknown_boundary"]
        supply_rate = ledger["supply"]["interval_surface_supply_m3"] / 3600.0
        total = (boundary["certified_retained_m3_s"]
                 + boundary["certified_open_outflow_m3_s"]
                 + boundary["certified_unknown_pending_m3_s"]
                 + boundary["withheld_local_q_m3_s"])
        np.testing.assert_allclose(total, supply_rate, rtol=0, atol=1e-15)
        self.assertLess(
            ledger["checks"]["max_abs_certified_account_gap_m3_s"], 1e-12)

    def test_the_account_checks_are_all_clean_on_a_conservative_bucket(self):
        bucket = bucket_for([6.0, 6.0, 0.0], cells=4)
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        ledger = hydrology_ledger(bucket, receiver, np.ones((1, 4), bool),
                                  cell_area_m2=CELL_AREA_M2, dt_s=3600.0,
                                  active_cells=np.arange(4, dtype=np.int64),
                                  world_seed=WORLD_SEED)
        checks = ledger["checks"]
        self.assertFalse(checks["internal_transfer_included_in_external_loss"])
        self.assertFalse(checks["unknown_folded_into_outlet"])
        self.assertFalse(checks["routed_terminal_series_reinjected"])
        self.assertLess(checks["max_abs_supply_balance_residual_m3"], 1e-9)

    def test_unknown_water_never_enters_a_certified_terminal(self):
        receiver = np.array([[1, 2, 3, -1], [5, 6, 7, -1]], np.int64)
        valid = np.ones((2, 4), bool)
        kinds = np.full((2, 4), "interior", dtype="U24")
        kinds[:, 3] = "open_outflow"
        local = np.zeros((1, 2, 4), np.float64)
        local[0, 0, 0] = 3.0
        local[0, 1, 0] = 4.0
        seeds = np.zeros((2, 4), bool)
        seeds[0, 0] = True                      # the first donor is undeclared
        record = unknown_boundary_ledger(receiver, valid, kinds, local,
                                        upstream_unknown_mask=seeds)
        self.assertEqual(record["open_outflow_m3_s"], 7.0)
        # The certified open outflow excludes the whole row-0 cone.
        self.assertEqual(record["certified_open_outflow_m3_s"], 4.0)
        self.assertEqual(record["withheld_local_q_m3_s"], 3.0)
        self.assertLessEqual(
            record["checks"]["four_term_partition_minus_declared_m3_s"], 1e-15)
        self.assertEqual(record["checks"]["unknown_folded_into_outlet"], False)

    def test_the_certified_unknown_term_is_recomputed_not_copied(self):
        """Water withheld upstream never reaches the unknown terminal either."""
        receiver = np.array([[1, 2, -1]], np.int64)
        valid = np.ones((1, 3), bool)
        kinds = np.full((1, 3), "interior", dtype="U24")
        kinds[0, 2] = "unknown_boundary"
        local = np.array([[1.0, 2.0, 0.0]], np.float64)
        seeds = np.zeros((1, 3), bool)
        seeds[0, 0] = True
        record = unknown_boundary_ledger(receiver, valid, kinds, local,
                                        upstream_unknown_mask=seeds)
        self.assertEqual(record["unknown_pending_m3_s"], 3.0)
        self.assertEqual(record["certified_unknown_pending_m3_s"], 0.0)
        self.assertNotEqual(record["unknown_pending_m3_s"],
                            record["certified_unknown_pending_m3_s"])


# --------------------------------------------------------------------------- #
# the new capability: per cell, per interval
# --------------------------------------------------------------------------- #
class CellAccountTests(unittest.TestCase):

    def setUp(self):
        self.bucket = bucket_for([10.0, 5.0, 0.0], cells=4)
        self.receiver = np.array([[1, 2, 3, -1]], np.int64)
        self.kinds = np.full((1, 4), "interior", dtype="U24")
        self.kinds[0, 3] = "retained"

    def account(self, **extra):
        return cell_hydrology_account(
            self.bucket, self.receiver, np.ones((1, 4), bool),
            cell_area_m2=CELL_AREA_M2, dt_s=3600.0,
            active_cells=np.arange(4, dtype=np.int64), terminal_kind=self.kinds,
            world_seed=WORLD_SEED, **extra)

    def test_the_account_is_per_cell_and_per_interval(self):
        account = self.account()
        self.assertEqual(account["algorithm"], ACCOUNT_ALGORITHM)
        for key in ("local_supply_m3_s", "infiltration_mm", "actual_et_mm",
                    "external_loss_volume_m3", "surface_supply_volume_m3",
                    "soil_storage_mm", "fast_storage_mm", "slow_storage_mm",
                    "certified_supply_m3_s", "withheld_m3_s",
                    "unknown_pending_m3_s", "outlet_q_m3_s"):
            self.assertIn(key, account)
        self.assertEqual(account["local_supply_m3_s"].shape, (3, 4))
        self.assertEqual(account["soil_storage_mm"].shape, (4, 4))
        self.assertEqual(account["certified_supply_m3_s"].shape, (3,))
        self.assertLess(account["checks"][
            "max_abs_certified_plus_withheld_minus_supply_m3_s"], 1e-12)

    def test_the_account_identity_is_stable_across_runs(self):
        first = self.account()
        second = self.account()
        self.assertEqual(first["cell_account_identity_sha256"],
                         second["cell_account_identity_sha256"])

    def test_the_routed_series_is_declared_not_injected(self):
        routed = np.array([0.5, 0.4, 0.3])
        account = self.account(routed_terminal_q_m3_s=routed)
        self.assertTrue(account["declarations"]["routed_terminal_not_reinjected"])
        self.assertFalse(account["checks"]["routed_terminal_series_reinjected"])
        np.testing.assert_array_equal(account["routed_terminal_q_m3_s"], routed)
        # The raw local supply is untouched by the routed series.
        self.assertFalse(np.array_equal(account["local_supply_m3_s"].sum(axis=1),
                                        routed))

    def test_routing_lateral_volume_must_match_the_declared_release(self):
        declared = float(self.account()["local_supply_m3_s"].sum() * 3600.0)
        self.account(route_lateral_volume_m3=np.array([[declared]]))
        with self.assertRaisesRegex(ValueError, "routing_injection_mismatch"):
            self.account(route_lateral_volume_m3=np.array([[declared * 2.0]]))

    def test_negative_or_nonfinite_outlet_is_refused(self):
        with self.assertRaisesRegex(ValueError, "invalid_outlet_q_m3_s"):
            self.account(outlet_q_m3_s=np.array([-1.0, 0.0, 0.0]))
        with self.assertRaisesRegex(ValueError, "invalid_outlet_q_m3_s"):
            self.account(outlet_q_m3_s=np.array([np.nan, 0.0, 0.0]))

    def test_a_nonconservative_bucket_is_refused_rather_than_reported(self):
        broken = dict(self.bucket)
        broken["actual_et_mm"] = self.bucket["actual_et_mm"] + 50.0
        with self.assertRaisesRegex(ValueError,
                                    "nonconservative_bucket_interval|bucket_supply"):
            cell_hydrology_account(broken, self.receiver, np.ones((1, 4), bool),
                                  cell_area_m2=CELL_AREA_M2, dt_s=3600.0,
                                  active_cells=np.arange(4, dtype=np.int64),
                                  terminal_kind=self.kinds)

    def test_the_unknown_seed_must_lie_on_a_valid_cell(self):
        seeds = np.zeros((1, 4), bool)
        seeds[0, 3] = True
        valid = np.array([[True, True, True, False]])
        with self.assertRaisesRegex(ValueError, "invalid_active_cells"):
            cell_hydrology_account(self.bucket, self.receiver, valid,
                                  cell_area_m2=CELL_AREA_M2, dt_s=3600.0,
                                  active_cells=np.arange(4, dtype=np.int64),
                                  terminal_kind=self.kinds,
                                  upstream_unknown_mask=seeds)


# --------------------------------------------------------------------------- #
# the event entry point: opt-in account, unchanged default
# --------------------------------------------------------------------------- #
class IdentityStabilityTests(unittest.TestCase):
    """The frozen event entry point is untouched; the adapter only adds fields."""

    def run_event(self):
        height, receiver, mask = chain_domain()
        return run_catchment_event(
            height, receiver, mask, mask, origin_native_xz=(0, 0),
            source_identity_sha256="0" * 64, world_seed=WORLD_SEED,
            rain_mm_h=np.array([8.0, 0.0, 0.0]), dt_s=3600.0,
            runoff_parameters=RunoffParameters(infiltration_capacity_mm_h=2.0))

    def run_accounted(self):
        height, receiver, mask = chain_domain()
        return run_event_with_account(
            height, receiver, mask, mask, origin_native_xz=(0, 0),
            source_identity_sha256="0" * 64, world_seed=WORLD_SEED,
            rain_mm_h=np.array([8.0, 0.0, 0.0]), dt_s=3600.0,
            runoff_parameters=RunoffParameters(infiltration_capacity_mm_h=2.0))

    def test_the_frozen_entry_point_has_no_account_keyword(self):
        """The pin holder must not grow a new parameter (it is byte-frozen)."""
        import inspect
        signature = inspect.signature(run_catchment_event)
        self.assertNotIn("include_hydrology_account", signature.parameters)

    def test_the_plain_run_carries_no_account(self):
        event = self.run_event()
        self.assertNotIn("cell_account", event)
        self.assertNotIn("adapter", event)
        self.assertEqual(event["event_identity_sha256"],
                         self.run_event()["event_identity_sha256"])

    def test_the_accounted_run_is_the_plain_run_plus_two_fields(self):
        plain = self.run_event()
        accounted = self.run_accounted()
        self.assertEqual(accounted["adapter"], ADAPTER)
        self.assertIn("cell_account", accounted)
        self.assertIn("accounted_event_identity_sha256", accounted)
        # Every field the frozen function publishes is bit-identical.
        for key in ("local_q_m3_s", "routed_terminal_q_m3_s",
                    "instantaneous_terminal_q_m3_s", "rain_mm_h", "active_cells"):
            np.testing.assert_array_equal(plain[key], accounted[key])
        self.assertEqual(plain["design_q_m3_s"], accounted["design_q_m3_s"])
        self.assertEqual(plain["event_identity_sha256"],
                         accounted["event_identity_sha256"])
        self.assertEqual(plain["identity"], accounted["identity"])

    def test_the_accounted_identity_is_separate_and_stable(self):
        first = self.run_accounted()
        second = self.run_accounted()
        self.assertEqual(first["accounted_event_identity_sha256"],
                         second["accounted_event_identity_sha256"])
        self.assertNotEqual(first["accounted_event_identity_sha256"],
                            first["event_identity_sha256"])
        self.assertTrue(first["account_declarations"]["event_identity_unchanged"])

    def test_the_adapter_refuses_a_bucket_that_does_not_reproduce_the_event(self):
        from terrain_pipeline.surface_rivers import native_30m_hydrology_event
        height, receiver, mask = chain_domain()
        with self.assertRaisesRegex(ValueError, "account_rebuild_mismatch"):
            native_30m_hydrology_event._rebuild_bucket(
                {"rain_mm_h": np.array([8.0, 0.0, 0.0]),
                 "active_cell_area_m2": CELL_AREA_M2,
                 "local_q_m3_s": np.full((3, 4), 1.0),
                 "runoff": {"source_id": "x",
                            "outflow_volume_m3": np.zeros(3)}},
                active_cells=np.arange(4, dtype=np.int64), dt_s=3600.0,
                runoff_parameters=RunoffParameters(infiltration_capacity_mm_h=2.0))

    def test_the_adapter_refuses_foreign_runoff_parameters(self):
        height, receiver, mask = chain_domain()
        with self.assertRaisesRegex(ValueError, "runoff_parameters_required"):
            from terrain_pipeline.surface_rivers import native_30m_hydrology_event
            event = self.run_event()
            native_30m_hydrology_event._rebuild_bucket(
                event, active_cells=event["active_cells"], dt_s=3600.0,
                runoff_parameters={"infiltration_capacity_mm_h": 2.0})


# --------------------------------------------------------------------------- #
# the required synthetic coverage
# --------------------------------------------------------------------------- #
class ZeroRainTests(unittest.TestCase):

    def test_zero_rain_with_a_zero_start_produces_nothing_anywhere(self):
        height, receiver, mask = chain_domain()
        event = run_event_with_account(
            height, receiver, mask, mask, origin_native_xz=(0, 0),
            source_identity_sha256="0" * 64, world_seed=WORLD_SEED,
            rain_mm_h=np.zeros(4), dt_s=3600.0,
            runoff_parameters=RunoffParameters(
                infiltration_capacity_mm_h=2.0, initial_soil_mm=0.0,
                initial_fast_mm=0.0, initial_slow_mm=0.0))
        account = event["cell_account"]
        self.assertEqual(float(np.abs(account["local_supply_m3_s"]).max()), 0.0)
        self.assertEqual(float(np.abs(account["outlet_q_m3_s"]).max()), 0.0)
        self.assertEqual(float(np.abs(account["certified_supply_volume_m3"]).max()), 0.0)
        self.assertEqual(float(np.abs(account["withheld_volume_m3"]).max()), 0.0)
        self.assertEqual(event["design_q_m3_s"], 0.0)

    def test_zero_rain_still_drains_a_declared_initial_store(self):
        """Declared behaviour, pinned: zero rain is not zero runoff by default."""
        height, receiver, mask = chain_domain()
        event = run_event_with_account(
            height, receiver, mask, mask, origin_native_xz=(0, 0),
            source_identity_sha256="0" * 64, world_seed=WORLD_SEED,
            rain_mm_h=np.zeros(3), dt_s=3600.0,
            runoff_parameters=RunoffParameters(infiltration_capacity_mm_h=2.0))
        account = event["cell_account"]
        self.assertGreater(float(np.abs(account["local_supply_m3_s"]).max()), 0.0)
        self.assertLess(float(np.abs(account["local_supply_m3_s"]).max()), 1e-4)


class PulseStormTests(unittest.TestCase):

    def test_a_pulse_is_absorbed_then_released_with_the_ledger_closing(self):
        height, receiver, mask = chain_domain()
        rain = np.array([60.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        event = run_event_with_account(
            height, receiver, mask, mask, origin_native_xz=(0, 0),
            source_identity_sha256="0" * 64, world_seed=WORLD_SEED,
            rain_mm_h=rain, dt_s=3600.0,
            runoff_parameters=RunoffParameters(infiltration_capacity_mm_h=2.0))
        account = event["cell_account"]
        checks = account["checks"]
        self.assertGreater(float(account["local_supply_m3_s"].max()), 0.0)
        # Rain that fell and did not evaporate or leave as supply is in the stores.
        budget = (checks["cumulative_rain_m3"]
                  - checks["cumulative_external_loss_m3"]
                  - checks["cumulative_surface_supply_m3"])
        self.assertAlmostEqual(budget, checks["cumulative_storage_change_m3"],
                               places=6)
        self.assertLess(checks["max_abs_interval_balance_residual_m3"], 1e-9)
        # The pulse recedes: the release peaks in the first interval or two and then
        # declines monotonically. (With dt_s == fast_tau_s the linear reservoir puts the
        # peak at the second interval, not the first: the interval-0 release only sees
        # the pre-existing store.)
        series = account["local_supply_m3_s"].sum(axis=1)
        peak = int(np.argmax(series))
        self.assertLessEqual(peak, 1)
        self.assertTrue(np.all(np.diff(series[peak:]) <= 1e-15))
        self.assertLess(series[-1], series[peak])


class SoilInitialStateTests(unittest.TestCase):

    def test_a_store_above_capacity_is_refused_at_construction(self):
        with self.assertRaisesRegex(ValueError, "initial soil exceeds capacity"):
            RunoffParameters(initial_soil_mm=200.0, soil_capacity_mm=150.0)

    def test_an_out_of_range_store_never_reaches_the_event(self):
        height, receiver, mask = chain_domain()
        with self.assertRaisesRegex(ValueError, "initial soil exceeds capacity"):
            run_catchment_event(
                height, receiver, mask, mask, origin_native_xz=(0, 0),
                source_identity_sha256="0" * 64, world_seed=WORLD_SEED,
                rain_mm_h=np.array([8.0]), dt_s=3600.0,
                runoff_parameters=RunoffParameters(
                    initial_soil_mm=200.0, soil_capacity_mm=150.0))

    def test_a_store_above_capacity_in_a_saved_bucket_is_refused(self):
        bucket = bucket_for([8.0, 0.0], cells=4)
        broken = dict(bucket)
        soil = bucket["soil_mm"].copy()
        soil[1] = soil[1] + 1e3
        broken["soil_mm"] = soil
        with self.assertRaises(ValueError):
            supply_ledger(broken, dt_s=3600.0, cell_area_m2=CELL_AREA_M2)


class ForcingRejectionTests(unittest.TestCase):

    def run_with(self, rain):
        height, receiver, mask = chain_domain()
        return run_catchment_event(
            height, receiver, mask, mask, origin_native_xz=(0, 0),
            source_identity_sha256="0" * 64, world_seed=WORLD_SEED,
            rain_mm_h=rain, dt_s=3600.0,
            runoff_parameters=RunoffParameters(infiltration_capacity_mm_h=2.0))

    def test_negative_and_non_finite_forcing_are_refused_with_stable_tokens(self):
        with self.assertRaisesRegex(ValueError, "invalid_rain"):
            self.run_with(np.array([-1.0, 0.0]))
        with self.assertRaisesRegex(ValueError, "invalid_rain"):
            self.run_with(np.array([np.nan, 0.0]))
        with self.assertRaisesRegex(ValueError, "invalid_rain"):
            self.run_with(np.array([np.inf, 0.0]))

    def test_negative_or_non_finite_saved_fields_are_refused(self):
        bucket = bucket_for([8.0, 0.0], cells=4)
        for key in ("infiltration_mm", "actual_et_mm", "local_q_m3_s", "soil_mm"):
            for bad in (-1.0, math.nan, math.inf):
                broken = dict(bucket)
                array = bucket[key].copy()
                array[0, 0] = bad
                broken[key] = array
                with self.subTest(key=key, bad=bad), \
                        self.assertRaisesRegex(ValueError, "invalid_"):
                    supply_ledger(broken, dt_s=3600.0, cell_area_m2=CELL_AREA_M2)

    def test_a_missing_bucket_field_is_named(self):
        bucket = bucket_for([8.0], cells=4)
        broken = {key: value for key, value in bucket.items()
                  if key != "actual_et_mm"}
        with self.assertRaisesRegex(ValueError, "bucket_result_incomplete"):
            supply_ledger(broken, dt_s=3600.0, cell_area_m2=CELL_AREA_M2)


class MissingCoverageTests(unittest.TestCase):

    def test_an_unresolved_neighbour_is_an_unknown_boundary_not_a_retained_one(self):
        receiver = np.array([[1, 2, -1, 4, -1]], np.int64)
        valid = np.ones((1, 5), bool)
        valid[0, 2] = False
        kinds = window_terminal_kind(receiver, valid)
        self.assertEqual(kinds["terminal_kind"][0, 2], "inactive")
        # Every receiver-less valid cell on this one-row window touches the row edge,
        # so none is fully resolved and none may be called retained.
        self.assertEqual(kinds["census"]["retained"], 0)
        self.assertGreater(kinds["census"]["unknown_boundary"], 0)
        self.assertEqual(kinds["census"]["open_outflow"], 0)

    def test_an_interior_minimum_is_retained(self):
        field = np.full((5, 5), 10.0)
        receiver = np.full((5, 5), -1, np.int64)
        for row in range(5):
            for column in range(5):
                if (row, column) == (2, 2):
                    continue
                if column < 2:
                    target = (row, column + 1)
                elif column > 2:
                    target = (row, column - 1)
                elif row < 2:
                    target = (row + 1, column)
                elif row > 2:
                    target = (row - 1, column)
                else:
                    target = None
                if target is not None:
                    receiver[row, column] = target[0] * 5 + target[1]
        kinds = window_terminal_kind(receiver, np.ones((5, 5), bool))
        self.assertEqual(kinds["terminal_kind"][2, 2], "retained")
        # Every cell in this bowl drains to the single interior minimum, so the one
        # receiver-less cell is the only terminal and it is fully resolved.
        self.assertEqual(kinds["census"]["retained"], 1)
        self.assertEqual(kinds["census"]["unknown_boundary"], 0)

    def test_the_unknown_seed_may_not_sit_on_an_inactive_cell(self):
        receiver = np.array([[1, -1]], np.int64)
        valid = np.array([[True, False]])
        kinds = np.full((1, 2), "interior", dtype="U24")
        kinds[0, 1] = "inactive"
        seeds = np.array([[False, True]])
        with self.assertRaisesRegex(ValueError, "unknown_seed_outside_valid"):
            unknown_boundary_ledger(receiver, valid, kinds,
                                    np.zeros((1, 2), np.float64),
                                    upstream_unknown_mask=seeds)

    def test_a_terminal_kind_vocabulary_violation_is_refused(self):
        receiver = np.array([[1, 2, -1]], np.int64)
        valid = np.ones((1, 3), bool)
        kinds = np.full((1, 3), "interior", dtype="U24")
        kinds[0, 2] = "lake"                   # not in the accumulation vocabulary
        with self.assertRaises(ValueError):
            unknown_boundary_ledger(receiver, valid, kinds,
                                    np.zeros((1, 3), np.float64))


class BudgetAndSubseedTests(unittest.TestCase):

    def test_the_account_budget_refuses_before_allocating(self):
        budget = account_budget(4, 49, 49)
        self.assertLessEqual(budget["estimated_bytes"], MAX_ACCOUNT_BYTES)
        with self.assertRaisesRegex(ValueError, "budget_cell_account"):
            account_budget(4000, 4000, 4000)
        with self.assertRaisesRegex(ValueError, "invalid_account_shape"):
            account_budget(0, 4, 4)
        with self.assertRaisesRegex(ValueError, "budget_hydrology_ledger"):
            ledger_budget(2001, 1000, 0)

    def test_purpose_subseeds_are_deterministic_and_distinct(self):
        first = purpose_subseeds(WORLD_SEED)
        second = purpose_subseeds(WORLD_SEED)
        self.assertEqual(first["subseeds"], second["subseeds"])
        self.assertEqual(first["world_seed"], WORLD_SEED)
        self.assertFalse(first["noise_used"])
        values = list(first["subseeds"].values())
        self.assertEqual(len(values), len(set(values)))
        self.assertEqual(sorted(first["subseeds"]), sorted(SUBSEED_PURPOSES))
        self.assertNotEqual(first["subseeds"], purpose_subseeds(12345)["subseeds"])

    def test_node_supply_attributes_each_cell_exactly_once(self):
        local = np.array([[1.0, 2.0, 3.0, 4.0]], np.float64)
        owner = np.array([0, 0, 1, 1], np.int64)
        ledger = node_supply_ledger(local, owner, dt_s=3600.0, nodes=2)
        self.assertEqual(ledger["node_lateral_cell_counts"].tolist(), [2, 2])
        self.assertEqual(ledger["cumulative_volume_m3"].tolist(),
                         [3.0 * 3600.0, 7.0 * 3600.0])
        self.assertLess(ledger["checks"]["nodal_minus_declared_max_m3_s"], 1e-12)

    def test_declared_node_attribution_owns_the_whole_catchment(self):
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        valid = np.ones((1, 4), bool)
        kinds = np.full((1, 4), "interior", dtype="U24")
        kinds[0, 3] = "retained"
        attributed = attribute_declared_nodes(
            receiver, valid, kinds, np.array([0, 3], np.int64))
        self.assertEqual(attributed["node_accumulated_cells"].tolist(), [1, 4])
        self.assertEqual(attributed["node_lateral_cell_counts"].tolist(), [1, 3])


# --------------------------------------------------------------------------- #
# the independent auditor: it must not import the modules under test
# --------------------------------------------------------------------------- #
class IndependentAuditorTests(unittest.TestCase):

    def test_the_auditor_does_not_import_the_code_under_test(self):
        path = ROOT / "tools" / "audit_native_30m_hydrology.py"
        source = path.read_text(encoding="utf-8")
        for forbidden in ("native_30m_runoff", "native_30m_hydrology_ledger",
                          "metric_network_accumulation", "rainfall_runoff",
                          "mountain_runoff_routing", "metric_natural_lakes"):
            for line in source.splitlines():
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")):
                    self.assertNotIn(forbidden, stripped,
                                     "the auditor imports " + forbidden)

    def test_the_auditor_refuses_when_the_kernels_are_loaded(self):
        path = ROOT / "tools" / "audit_native_30m_hydrology.py"
        spec = importlib.util.spec_from_file_location("p4_auditor", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # This test process has the kernels loaded on purpose: the guard must fire.
        self.assertIn('terrain_pipeline.runoff', sys.modules)
        with self.assertRaises(SystemExit):
            module.assert_kernels_not_loaded()

    def test_the_auditor_traverses_without_the_kernel(self):
        path = ROOT / "tools" / "audit_native_30m_hydrology.py"
        spec = importlib.util.spec_from_file_location("p4_auditor_traversal", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        receiver = np.array([[1, 2, 3, -1]], np.int64)
        valid = np.ones((1, 4), bool)
        local = np.array([[1.0, 2.0, 3.0, 4.0]], np.float64)
        total = module.accumulate_by_hand(receiver, local, valid)
        np.testing.assert_allclose(total, [[1.0, 3.0, 6.0, 10.0]], rtol=0, atol=0)
        seeds = np.array([[True, False, False, False]])
        cone = module.donor_cone(receiver, seeds, valid)
        self.assertTrue(cone.all())


if __name__ == "__main__":
    unittest.main()
