"""Review-round rejection cases: only gates that currently have no test of their own.

Scope discipline (2026-10-25 review, no production change):

* every fixture here is small and synthetic; no saved TD page, no real release
directory and no heavy recomputation is required;
* only gates that the existing suites do NOT already assert are covered: the
  adjacent/cross-cell receiver cycles (``test_native_30m_runoff`` only pins the
  self loop), the cross-stage binding tokens other than the two
  ``topology_recompute_mismatch`` cases and ``lateral_topology_binding``
  (``test_native_30m_bundle_validation``), the five selector reason codes
  (``test_native_30m_reach_selection`` only uses a bare ``assertRaises``), the two
  publisher-level catchment gates and the CLI-level early refusals;
* gates that already have equivalent coverage elsewhere are NOT duplicated here:
  the four capability bits (``test_native_30m_envelope_gates``), re-sealed derived
  tampering (``test_metric_network_discharge_product``), ``stage_not_implemented``,
  ``gate_refuses_retained_as_outlet``, ``semantics_mismatch``,
  ``hru_fraction_not_unit``, nested time binding, budget gates and the ``--help``
  negative list;
* where the contract names a reason token that production does not actually emit,
  the test does not invent a loose assertion: it pins the *actual* refusal and the
  report states exactly what is produced instead. ``destination_exists``,
  ``silent_window_downgrade``, ``scratch_script_imported_as_production`` and
  ``downhill_fraction_below_guard`` are covered that way (see
  ``.scratch/river-stage1-completion/m1-review-adjudication-20261025-v1.md``).
"""
import io
import unittest
from collections import Counter
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np

from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.surface_rivers.native_30m_reach_selection import select_from_topology
from terrain_pipeline.runoff import run_catchment_event as run_catchment_event
from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
from tools import publish_native_30m_bundle as publisher
from tools.native_30m_bundle_validation import validate_graph_bindings


ORIGIN = (0, 0)
BASE_SELECTION = dict(min_stem_m=1.0, min_catchment_cells=2, contact_margin_cells=1)


def plateau(n=9):
    """A 5x5 raised pad with a cone-shaped depression: many terminals, no closure."""
    field = np.full((n, n), -10.0, np.float64)
    field[2:7, 2:7] = 10.0
    rr, cc = np.indices((3, 3))
    field[3:6, 3:6] = np.abs(rr - 1) + np.abs(cc - 1)
    return field


def ring(n=101, radius=30):
    """A broad radial valley inside a raised rim: long stems and many terminals."""
    rr, cc = np.indices((n, n))
    distance = np.hypot(rr - (n - 1) / 2.0, cc - (n - 1) / 2.0)
    inner = np.minimum(np.abs(rr - (n - 1) / 2.0), np.abs(cc - (n - 1) / 2.0)) * 2.0
    outer = 200.0 - (distance - radius) * 3.0
    return np.where(distance <= radius, inner, outer).astype(np.float64)


def topology(field):
    return build_strict_topology(field, np.ones(field.shape, bool))


def reasons(result):
    return Counter(item["reason"] for item in result["candidates"] if not item["accepted"])


class RunoffCycleRefusalTests(unittest.TestCase):
    """A receiver graph that is not a strictly down-hill D8 DAG must be refused."""

    def setUp(self):
        self.elevation = np.array([[4.0, 3.0, 2.0, 1.0]], np.float64)
        self.mask = np.ones(self.elevation.shape, bool)

    def run_with(self, receiver):
        return run_catchment_event(
            self.elevation, receiver, self.mask, self.mask,
            origin_native_xz=ORIGIN, source_identity_sha256="0" * 64,
            world_seed=20261020, rain_mm_h=np.array([8.0, 0.0, 0.0]),
            dt_s=3600.0, runoff_parameters=RunoffParameters(infiltration_capacity_mm_h=2.0))

    def test_a_self_receiver_is_refused(self):
        with self.assertRaisesRegex(ValueError, "receiver_self_loop"):
            self.run_with(np.array([[0, 2, 3, -1]], np.int64))

    def test_an_adjacent_two_cycle_is_refused(self):
        # 0 -> 1 and 1 -> 0 is a D8-neighbour cycle: the reason is the cycle, not the
        # neighbour rule.  ``test_native_30m_runoff`` only pins the self loop.
        with self.assertRaisesRegex(ValueError, "receiver_cycle: the receiver graph is not acyclic"):
            self.run_with(np.array([[1, 0, 3, -1]], np.int64))

    def test_a_cycle_through_a_non_neighbour_is_refused_first(self):
        # 3 -> 1 closes a three-cycle but is also not a D8 neighbour of 3; the
        # neighbour rule is checked before the acyclicity walk and must name itself.
        with self.assertRaisesRegex(ValueError, "receiver_not_graph_edge"):
            self.run_with(np.array([[1, 2, 3, 1]], np.int64))

    def test_a_receiver_outside_the_grid_is_refused(self):
        with self.assertRaisesRegex(ValueError, "receiver_index_out_of_range"):
            self.run_with(np.array([[1, 2, 3, 9]], np.int64))


class GraphBindingRefusalTests(unittest.TestCase):
    """Cross-stage binding tokens with no test of their own today.

    ``test_native_30m_bundle_validation`` already covers
    ``topology_recompute_mismatch`` (receiver / unknown mask) and
    ``lateral_topology_binding``; the other tokens below are not asserted there.
    """

    def env(self):
        field = plateau(9)
        top = build_strict_topology(field, np.ones(field.shape, bool), origin_native_xz=(100, 200))
        catchment = np.zeros(field.shape, bool)
        catchment[3:6, 3:6] = True
        flowline = np.zeros_like(catchment)
        flowline.ravel()[[30, 31, 40]] = True
        return {"arrays": {
            "source.npz": {"field": field, "resolved_mask": np.ones(field.shape, bool),
                           "origin_native_xz": np.array([100, 200], np.int64)},
            "topology.npz": {k: top[k] for k in ("receiver", "valid_mask", "terminal_kind",
                                                  "upstream_unknown_mask")},
            "selection.npz": {"catchment_mask": catchment, "flowline_mask": flowline,
                              "stem_flat_cells": np.array([30, 31, 40], np.int64)},
            "section.npz": {"node_cell_ids": np.array([30, 40], np.int64)},
            "reach_context.npz": {"lateral_cell_counts": np.array([1, 8], np.int64)}},
            "manifest": {"source_records": []}, "json_records": {
                "source.json": {"source_records": []},
                "selection.json": {"chosen": {"terminal_flat_cell": 40,
                                                "terminal_native_xz": [104, 204],
                                                "catchment_cells": 9}}}}

    def assert_refuses(self, mutate, token):
        env = self.env()
        mutate(env)
        with self.assertRaisesRegex(ValueError, token):
            validate_graph_bindings(env)

    def test_the_untouched_fixture_is_accepted(self):
        self.assertEqual(validate_graph_bindings(self.env())["catchment_cells"], 9)

    def test_catchment_holding_a_second_terminal_is_refused(self):
        # 37 is a retained terminal of the fixture; pulling it in breaks the
        # single-terminal requirement of the chosen catchment.
        self.assert_refuses(lambda env: env["arrays"]["selection.npz"]["catchment_mask"].__setitem__((4, 1), True),
                            "catchment_has_another_terminal")

    def test_a_catchment_cell_draining_outside_the_catchment_is_refused(self):
        # Cell 33 drains to 34, which is outside the declared mask, so the catchment is
        # not a closed routing domain even though its terminal (40) is correct.
        def mutate(env):
            mask = env["arrays"]["selection.npz"]["catchment_mask"]
            mask[:] = False
            mask.ravel()[[33, 40]] = True
            flow = env["arrays"]["selection.npz"]["flowline_mask"]
            flow[:] = False
            flow.ravel()[40] = True
            env["json_records"]["selection.json"]["chosen"]["catchment_cells"] = 2
        self.assert_refuses(mutate, "catchment_receiver_leaves_scope")

    def test_chosen_terminal_coordinates_must_match_the_source(self):
        self.assert_refuses(lambda env: env["json_records"]["selection.json"]["chosen"].__setitem__(
            "terminal_native_xz", [104, 205]), "chosen_terminal_coordinates")

    def test_chosen_catchment_count_must_equal_the_full_tree(self):
        self.assert_refuses(lambda env: env["json_records"]["selection.json"]["chosen"].__setitem__(
            "catchment_cells", 8), "catchment_not_full_upstream_tree")

    def test_an_integral_but_shrunk_stem_is_refused(self):
        self.assert_refuses(lambda env: env["arrays"]["selection.npz"].__setitem__(
            "stem_flat_cells", np.array([40], np.int64)), "stem_topology_binding")

    def test_a_chosen_terminal_outside_the_window_is_refused(self):
        self.assert_refuses(lambda env: env["json_records"]["selection.json"]["chosen"].__setitem__(
            "terminal_flat_cell", 999), "chosen_terminal_range")


class SelectionCodeTests(unittest.TestCase):
    """Every selector reason code must be reachable and named.

    ``test_native_30m_reach_selection`` only asserts that *something* raises, and
    ``test_native_30m_requested_selection`` covers the caller-terminal spelling
    errors; the five codes themselves have no assertion.
    """

    def setUp(self):
        self.plateau = plateau(9)
        self.plateau_topology = topology(self.plateau)
        self.ring = ring(101)
        self.ring_topology = topology(self.ring)

    def select(self, field, top, **kwargs):
        options = dict(BASE_SELECTION)
        options.update(kwargs)
        return select_from_topology(field, top, origin_native_xz=ORIGIN, **options)

    def test_catchment_not_complete_and_small_or_budget_are_reachable(self):
        codes = reasons(self.select(self.plateau, self.plateau_topology))
        self.assertGreater(codes["catchment_not_complete"], 0)
        self.assertGreater(codes["small_or_budget"], 0)
        for code in codes:
            self.assertIn(code, ("catchment_not_complete", "small_or_budget"))

    def test_stem_too_short_is_reachable(self):
        codes = reasons(self.select(self.ring, self.ring_topology, min_stem_m=600.0))
        self.assertGreater(codes["stem_too_short"], 0)

    def test_nodes_over_budget_is_reachable(self):
        codes = reasons(self.select(self.ring, self.ring_topology, max_nodes=2, max_stride=1))
        self.assertGreater(codes["nodes_over_budget"], 0)

    def test_subwindow_over_budget_is_reachable(self):
        codes = reasons(self.select(self.ring, self.ring_topology, max_subwindow_cells=1000))
        self.assertGreater(codes["subwindow_over_budget"], 0)

    def test_a_window_with_no_accepted_candidate_refuses_rather_than_picking_one(self):
        for kwargs in (dict(min_stem_m=1000.0), dict(max_subwindow_cells=500)):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, "no_complete_reach"):
                self.select(self.ring, self.ring_topology, **kwargs)

    def test_a_rejected_caller_terminal_names_its_own_reason(self):
        chosen = self.select(self.ring, self.ring_topology)["chosen"]
        tz, tx = divmod(int(chosen["terminal_flat_cell"]), self.ring.shape[1])
        with self.assertRaisesRegex(ValueError, "requested_terminal_rejected:small_or_budget"):
            self.select(self.ring, self.ring_topology, terminal_native_xz=[tx, tz],
                        max_catchment_cells=3)

    def test_the_five_declared_codes_are_exactly_the_ones_emitted(self):
        emitted = set()
        emitted |= set(reasons(self.select(self.plateau, self.plateau_topology)))
        emitted |= set(reasons(self.select(self.ring, self.ring_topology, min_stem_m=600.0)))
        emitted |= set(reasons(self.select(self.ring, self.ring_topology, max_nodes=2, max_stride=1)))
        emitted |= set(reasons(self.select(self.ring, self.ring_topology, max_subwindow_cells=1000)))
        self.assertEqual(emitted, {"catchment_not_complete", "small_or_budget", "stem_too_short",
                                   "nodes_over_budget", "subwindow_over_budget"})


class PublishGateTests(unittest.TestCase):
    """The two publisher-level catchment gates (contract A2 v and A2 m).

    Both live in ``publish_native_30m_bundle._compute_from_source`` and neither had
    a synthetic counter-example anywhere in the repository.  The whole point of the
    hard gate is that a *small* full-window rejection rate cannot buy a pass, so the
    fixtures below fail exactly one catchment cell.
    """

    def setUp(self):
        self.field = plateau(9)
        self.catchment = np.zeros(self.field.shape, bool)
        self.catchment[3:6, 3:6] = True
        self.flowline = np.zeros_like(self.catchment)
        self.flowline.ravel()[[30, 40]] = True

    def selection(self, **overrides):
        chosen = {"terminal_flat_cell": 40, "terminal_native_xz": (4, 4),
                  "catchment_cells": 9, "catchment_mask": self.catchment.copy(),
                  "flowline_mask": self.flowline.copy(),
                  "stem_flat_cells": np.array([30, 40], np.int64),
                  "stem_length_m": 30.0, "suggested_stride": 1,
                  "subwindow_rc": (0, 9, 0, 9)}
        chosen.update(overrides)
        return {"candidates": [], "chosen": chosen, "selection_policy": "synthetic"}

    def source(self, **overrides):
        payload = {"field": self.field, "resolved_mask": np.ones(self.field.shape, bool),
                   "assembly_digest": "a" * 64, "source_records": [], "policy": {}}
        payload.update(overrides)
        return payload

    def compute(self, source=None, selection=None):
        with patch.object(publisher, "select_from_topology",
                          return_value=selection if selection is not None else self.selection()):
            return publisher._compute_from_source(
                source if source is not None else self.source(), origin=[100, 200], shape=[9, 9],
                coupled_intervals=1, resample_stride=1, started=0.0)

    def test_a_catchment_cell_the_pages_never_resolved_refuses_the_run(self):
        resolved = np.ones(self.field.shape, bool)
        resolved[4, 4] = False
        with self.assertRaisesRegex(ValueError, "catchment_not_complete"):
            self.compute(source=self.source(resolved_mask=resolved))

    def test_one_unknown_seed_inside_the_catchment_refuses_the_run(self):
        # One cell, not a fraction: the whole-window rejection rate stays 0 while the
        # declared catchment is already incomplete.
        original = publisher.build_strict_topology

        def seeded(field, mask):
            top = original(field, mask)
            top["upstream_unknown_mask"][4, 4] = True
            return top

        with patch.object(publisher, "build_strict_topology", side_effect=seeded):
            with self.assertRaisesRegex(ValueError, "catchment_not_complete"):
                self.compute(source=self.source())

    def test_a_member_whose_receiver_leaves_the_declared_subwindow_refuses_the_run(self):
        # Cell 30's receiver (40) is a row below the declared crop, so the crop is not
        # a closed routing domain.
        selection = self.selection(subwindow_rc=(0, 4, 0, 4))
        with self.assertRaisesRegex(ValueError, "catchment_receiver_leaves_subwindow"):
            self.compute(selection=selection)


class CliRefusalTests(unittest.TestCase):
    """CLI-level early refusals: no worker dispatch and no directory on a refusal.

    ``test_native_30m_scenario_cli`` already pins the window/cell budget codes and the
    ``--help`` negative list; the checks below are the CLI end of the publisher and
    add the single-axis dimension case plus verbatim parameter pass-through.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base = ["--mode", "publish", "--td-page", "page.npz", "--page-sha256",
                     "page.npz=" + "a" * 64]
        self.worker_report = {"manifest": {"identity_sha256": "a" * 64},
                              "compute_wall_seconds": 0.0, "process_peak_rss_bytes": 1,
                              "rss_scope": "synthetic stub", "resources": {}}

    def dispatch(self, flags, *, succeed=True):
        target = self.root / ("out-%d" % len(list(self.root.iterdir())))
        argv = self.base + ["--output-dir", str(target)] + flags
        with ExitStack() as stack:
            worker = stack.enter_context(patch.object(publisher, "_compute_candidate_in_worker"))
            if succeed:
                worker = stack.enter_context(patch.object(
                    publisher, "_compute_candidate_in_worker", return_value=self.worker_report))
                stack.enter_context(patch.object(publisher, "publish_release",
                                                 return_value={"stub": True}))
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(redirect_stderr(io.StringIO()))
            result = publisher.main(argv)
        return result, worker, target

    def test_an_over_budget_cell_count_refuses_before_the_worker_and_the_directory(self):
        result, worker, target = self.dispatch(["--max-window-cells", "1"], succeed=False)
        self.assertEqual(result, 2)
        worker.assert_not_called()
        self.assertFalse(target.exists())

    def test_a_single_axis_above_the_window_dimension_budget_is_refused_early(self):
        # A 2049 x 10 window is refused by its larger axis, before the cell product is
        # even considered; the code must name the dimension, not the cell count.
        target = self.root / "out-axis"
        err = io.StringIO()
        with patch.object(publisher, "_compute_candidate_in_worker") as worker, \
                redirect_stderr(err), redirect_stdout(io.StringIO()):
            result = publisher.main(self.base + ["--window-shape", "2049", "10",
                                                 "--output-dir", str(target)])
        self.assertEqual(result, 2)
        worker.assert_not_called()
        self.assertFalse(target.exists())
        self.assertIn("budget_window_dimension", err.getvalue())

    def test_a_declared_window_and_origin_reach_the_worker_verbatim(self):
        result, worker, target = self.dispatch(["--window-shape", "65", "40",
                                                "--origin-native-xz", "-7", "9",
                                                "--coupled-intervals", "3",
                                                "--resample-stride", "2"])
        self.assertEqual(result, 0)
        self.assertEqual(worker.call_args.args[1], {"origin_native_xz": [-7, 9],
                                                    "shape_zx": [65, 40],
                                                    "coupled_intervals": 3,
                                                    "resample_stride": 2})

    def test_the_1337_default_is_never_silently_swapped_for_a_smaller_window(self):
        result, worker, _ = self.dispatch([])
        self.assertEqual(result, 0)
        self.assertEqual(worker.call_args.args[1]["shape_zx"], [1337, 1337])

    def test_an_existing_destination_is_refused_without_touching_it(self):
        target = self.root / "out-existing"
        target.mkdir()
        marker = target / "keep"
        marker.write_bytes(b"original")
        with patch.object(publisher, "_compute_candidate_in_worker") as worker, \
                redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            result = publisher.main(self.base + ["--output-dir", str(target)])
        self.assertEqual(result, 2)
        worker.assert_not_called()
        self.assertEqual(marker.read_bytes(), b"original")
        self.assertEqual(sorted(p.name for p in target.iterdir()), ["keep"])

    def test_the_unresolved_fraction_knob_the_draft_named_does_not_exist(self):
        # The contract draft listed ``--max-unresolved-fraction``; it is not in the
        # CLI at all, so passing it is an argparse error (exit 2) and it must not be
        # advertised in ``--help``.  It is not, and must not become, a pass gate.
        target = self.root / "out-unresolved"
        with patch.object(publisher, "_compute_candidate_in_worker") as worker, \
                redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                publisher.main(self.base + ["--max-unresolved-fraction", "0.01",
                                            "--output-dir", str(target)])
        self.assertEqual(caught.exception.code, 2)
        worker.assert_not_called()
        self.assertFalse(target.exists())
        help_text = io.StringIO()
        with redirect_stdout(help_text), self.assertRaises(SystemExit):
            publisher.main(["--help"])
        self.assertNotIn("--max-unresolved-fraction", help_text.getvalue())


if __name__ == "__main__":
    unittest.main()
