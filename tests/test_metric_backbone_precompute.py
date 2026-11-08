# -*- coding: utf-8 -*-
"""Contract tests for the river-backbone precompute layer.

Every test builds a **synthetic** receiver graph and stands in for terrain: this file never
reads a TD page, never derives a D8 topology and never touches a saved product. The point is
the algebra this layer owns -- the OR gate, the per-quantity completeness, the segmentation,
the single side-input slot and the endpoint two-axis.

Nothing here asserts that a real window produces a non-empty Q-only channel; that is a
property of the real data and is checked by the audit against the delivered supports.

The fixtures below converge **only inside the helper**, not by weakening an assertion: a
supply cell must genuinely reach the channel for a branch test to mean anything, and a gate
that selects a structural terminal must be split before it is segmented.
"""
import unittest

import numpy as np

from terrain_pipeline.surface_rivers import metric_backbone_precompute as precompute


def straight_bed(width=7, height=7):
    """Every cell drains straight south; the last row is a structural terminal.

    One column is the trunk. A column that is gated off in its upper rows gives the
    branch tests a real entry cell: the supply above the cut has to flow down into the
    channel it can reach.
    """
    rows, columns = height, width
    bed = np.zeros((rows, columns), np.float64)
    for z in range(rows):
        for x in range(columns):
            bed[z, x] = 100.0 - z * 1.0 - abs(x - columns // 2) * 0.05
    valid = np.ones((rows, columns), np.bool_)
    receiver = np.full((rows, columns), -1, np.int64)
    for z in range(rows - 1):
        for x in range(columns):
            receiver[z, x] = (z + 1) * columns + x
    kinds = np.full((rows, columns), "inactive", dtype=precompute.TERMINAL_KIND_DTYPE)
    kinds[valid] = "interior"
    kinds[rows - 1, :] = "retained"
    seeds = np.zeros((rows, columns), np.bool_)
    seeds[0, :] = True
    return {"bed": bed, "valid": valid, "receiver": receiver, "kinds": kinds,
            "seeds": seeds, "trunk": columns // 2, "rows": rows, "columns": columns}


def gate_trunk(fixture, first_row=0, last_row=None):
    """A gate selecting one trunk column over ``[first_row, last_row]`` (inclusive)."""
    rows, columns = fixture["valid"].shape
    last_row = rows - 1 if last_row is None else last_row
    gate = np.zeros((rows, columns), np.bool_)
    gate[first_row:last_row + 1, fixture["trunk"]] = True
    return gate


def parent_from(fixture):
    rows, columns = fixture["valid"].shape
    upstream = np.zeros((rows, columns), np.int64)
    for x in range(columns):
        for z in range(rows):
            upstream[z, x] = z + 1
    complete = np.ones((rows, columns), np.bool_)
    complete[0, :] = False
    owner = np.zeros((rows, columns), np.int64)
    owner[:, columns - 1] = 1
    return {
        "schema": "metric-world-domain-candidates-v1",
        "arrays": {
            "receiver": fixture["receiver"],
            "resolved_mask": fixture["valid"],
            "terminal_kind": fixture["kinds"],
            "upstream_cells": upstream,
            "owner_index": owner,
            "complete_mask": complete,
            "upstream_unknown_mask": fixture["seeds"],
            "elevation_m": fixture["bed"],
        },
        "metadata": {
            "support": {"origin_native_xz": [1000, 2000], "shape_zx": [rows, columns],
                        "world_seed": 20261020, "spacing_m": 30.0, "plan_version": 1},
            "support_identity_sha256": "0" * 64,
        },
        "identity_sha256": "1" * 64,
    }


class ParentViewTests(unittest.TestCase):
    def test_structural_checks_refuse_an_incoherent_parent(self):
        fixture = straight_bed()
        parent = parent_from(fixture)
        broken = dict(parent)
        broken["arrays"] = dict(parent["arrays"])
        receiver = np.array(parent["arrays"]["receiver"], copy=True)
        receiver[0, 0] = 10 ** 9
        broken["arrays"]["receiver"] = receiver
        with self.assertRaises(ValueError):
            precompute.parent_view(broken)

    def test_inactive_cells_must_carry_receiver_minus_one(self):
        fixture = straight_bed()
        parent = parent_from(fixture)
        valid = np.array(parent["arrays"]["resolved_mask"], copy=True)
        valid[0, 0] = False
        parent["arrays"]["resolved_mask"] = valid
        with self.assertRaises(ValueError):
            precompute.parent_view(parent)

    def test_undeclared_terminal_kind_is_refused(self):
        fixture = straight_bed()
        parent = parent_from(fixture)
        kinds = np.array(parent["arrays"]["terminal_kind"], copy=True)
        kinds[0, 0] = "ocean_mouth"
        parent["arrays"]["terminal_kind"] = kinds
        with self.assertRaises(ValueError):
            precompute.parent_view(parent)


class AreaAndCompletenessTests(unittest.TestCase):
    def test_area_is_a_cell_count_not_a_flux(self):
        fixture = straight_bed()
        rows, columns = fixture["valid"].shape
        area, complete = precompute.accumulate_area(
            receiver=fixture["receiver"], valid_mask=fixture["valid"],
            terminal_kind=fixture["kinds"], upstream_unknown_mask=fixture["seeds"])
        self.assertEqual(int(area[rows - 1, 0]), rows)
        self.assertEqual(area.dtype, np.int64)
        self.assertTrue(complete.dtype == np.bool_)
        # the first row seeds an unknown upstream, so nothing below it is complete
        self.assertFalse(bool(complete[1, 0]))

    def test_area_completeness_and_flux_completeness_are_separate(self):
        fixture = straight_bed()
        rows, columns = fixture["valid"].shape
        available = np.ones((rows, columns), np.bool_)
        shift = np.zeros((rows, columns), np.bool_)
        area, area_complete = precompute.accumulate_area(
            receiver=fixture["receiver"], valid_mask=fixture["valid"],
            terminal_kind=fixture["kinds"], upstream_unknown_mask=shift)
        quantity_complete = precompute.quantity_complete(
            receiver=fixture["receiver"], valid_mask=fixture["valid"],
            terminal_kind=fixture["kinds"], available_mask=available,
            parent_unknown_seed=shift)
        self.assertTrue(bool(area_complete.all()))
        self.assertTrue(bool(quantity_complete.all()))
        # one cell's input missing must move the flux completeness and not the area's
        available[2, 2] = False
        quantity_complete = precompute.quantity_complete(
            receiver=fixture["receiver"], valid_mask=fixture["valid"],
            terminal_kind=fixture["kinds"], available_mask=available,
            parent_unknown_seed=shift)
        self.assertFalse(bool(quantity_complete[2, 2]))
        self.assertFalse(bool(quantity_complete[rows - 1, 2]))
        self.assertTrue(bool(area_complete.all()))

    def test_missing_input_seed_is_only_the_seed_and_the_propagation_is_separate(self):
        """``missing_input_seed`` returns the **seed**, not the propagated mask.

        The seed is exactly the cells whose own input is missing plus the parent's window-cut
        seeds; reading the propagated result off it would be the mistake this pair of
        functions exists to prevent. The propagation is measured on ``quantity_complete``.
        """
        fixture = straight_bed()
        rows, columns = fixture["valid"].shape
        available = np.ones((rows, columns), np.bool_)
        available[1, 1] = False
        none = np.zeros((rows, columns), np.bool_)
        seed = precompute.missing_input_seed(
            receiver=fixture["receiver"], valid_mask=fixture["valid"],
            available_mask=available, parent_unknown_seed=none)
        self.assertTrue(bool(seed[1, 1]))
        self.assertFalse(bool(seed[rows - 1, 1]))
        self.assertEqual(int(seed.sum()), 1)
        propagated = precompute.quantity_complete(
            receiver=fixture["receiver"], valid_mask=fixture["valid"],
            terminal_kind=fixture["kinds"], available_mask=available,
            parent_unknown_seed=none)
        self.assertFalse(bool(propagated[1, 1]))
        self.assertFalse(bool(propagated[rows - 1, 1]))
        self.assertTrue(bool(propagated[rows - 1, 3]))


class GateTests(unittest.TestCase):
    def test_a_gate_and_q_gate_are_or_ed_and_reported_separately(self):
        valid = np.ones((3, 3), np.bool_)
        area = np.zeros((3, 3), np.int64)
        area[0, 0] = 100
        flux = np.zeros((3, 3), np.float64)
        flux[2, 2] = 1.0
        mask, a_gate, q_gate, per_quantity = precompute.channel_gates(
            valid_mask=valid, area_cells=area,
            gate_flux={precompute.QUANTITY_SCENARIO: flux},
            a_min_cells=50, q_min_m3_s=1e-3)
        self.assertTrue(bool(mask[0, 0]))
        self.assertTrue(bool(mask[2, 2]))
        self.assertEqual(int((q_gate & ~a_gate).sum()), 1)
        self.assertEqual(per_quantity[precompute.QUANTITY_SCENARIO], 1)

    def test_a_real_zero_q_only_selection_is_reported_as_zero_not_faked(self):
        valid = np.ones((3, 3), np.bool_)
        area = np.zeros((3, 3), np.int64)
        area[0, 0] = 100
        flux = np.zeros((3, 3), np.float64)
        mask, a_gate, q_gate, _ = precompute.channel_gates(
            valid_mask=valid, area_cells=area,
            gate_flux={precompute.QUANTITY_SCENARIO: flux},
            a_min_cells=50, q_min_m3_s=1e-3)
        self.assertEqual(int(q_gate.sum()), 0)
        self.assertEqual(int(mask.sum()), 1)

    def test_an_undeclared_quantity_name_is_refused(self):
        valid = np.ones((3, 3), np.bool_)
        area = np.zeros((3, 3), np.int64)
        with self.assertRaises(ValueError):
            precompute.channel_gates(valid_mask=valid, area_cells=area,
                                     gate_flux={"measured_flow": np.zeros((3, 3))},
                                     a_min_cells=1, q_min_m3_s=1e-9)

    def test_a_non_finite_or_negative_gate_flux_is_refused(self):
        valid = np.ones((3, 3), np.bool_)
        area = np.zeros((3, 3), np.int64)
        for bad in (np.full((3, 3), np.nan), np.full((3, 3), -1.0)):
            with self.assertRaises(ValueError):
                precompute.channel_gates(
                    valid_mask=valid, area_cells=area,
                    gate_flux={precompute.QUANTITY_SCENARIO: bad},
                    a_min_cells=1, q_min_m3_s=1e-9)

    def test_a_gate_cannot_be_driven_by_an_unavailable_cell(self):
        valid = np.ones((3, 3), np.bool_)
        area = np.zeros((3, 3), np.int64)
        flux = np.zeros((3, 3), np.float64)
        flux[1, 1] = 9.0
        available = np.ones((3, 3), np.bool_)
        available[1, 1] = False
        mask, a_gate, q_gate, _ = precompute.channel_gates(
            valid_mask=valid, area_cells=area,
            gate_flux={precompute.QUANTITY_SCENARIO: flux},
            a_min_cells=50, q_min_m3_s=1e-3,
            available={precompute.QUANTITY_SCENARIO: available})
        self.assertFalse(bool(q_gate[1, 1]))
        self.assertFalse(bool(mask[1, 1]))


class SegmentationTests(unittest.TestCase):
    def test_a_gate_that_selects_a_terminal_splits_it_into_an_anchor(self):
        fixture = straight_bed()
        rows, columns = fixture["valid"].shape
        gate = gate_trunk(fixture, 2, rows - 1)      # includes the terminal row
        routable, terminals = precompute.routable_channel(
            gate_mask=gate, receiver=fixture["receiver"])
        self.assertTrue(bool(routable[2, fixture["trunk"]]))
        self.assertFalse(bool(routable[rows - 1, fixture["trunk"]]))
        self.assertTrue(bool(terminals[rows - 1, fixture["trunk"]]))
        self.assertTrue(bool((routable | terminals)[rows - 1, fixture["trunk"]]))
        segmentation = precompute.segment_on_channel(
            receiver=fixture["receiver"], valid_mask=fixture["valid"],
            channel_mask=routable)
        self.assertEqual(segmentation["channel_cells"], int(routable.sum()))

    def test_channel_partition_is_maximal_and_vertex_disjoint(self):
        fixture = straight_bed()
        rows, columns = fixture["valid"].shape
        gate = gate_trunk(fixture)
        routable, terminals = precompute.routable_channel(
            gate_mask=gate, receiver=fixture["receiver"])
        self.assertTrue(bool(terminals[rows - 1, fixture["trunk"]]))
        segmentation = precompute.segment_on_channel(
            receiver=fixture["receiver"], valid_mask=fixture["valid"], channel_mask=routable)
        self.assertEqual(segmentation["channel_cells"], int(routable.sum()))
        covered = int((segmentation["reach_of_cell"] >= 0).sum())
        self.assertEqual(covered, int(routable.sum()))
        cells = [cell for chain in segmentation["chains"] for cell in chain]
        self.assertEqual(len(cells), len(set(cells)))
        downstream, ends = precompute.reach_downstream(
            receiver=fixture["receiver"], chains=segmentation["chains"],
            terminal_kind=fixture["kinds"])
        self.assertEqual(int(downstream[0]), -1)
        # the reach ends on the structural terminal: recognised, not a gate cut
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0]["reason"], "structural_terminal")

    def test_a_gate_cut_is_recorded_rather_than_raised(self):
        """A tail that lands on a **valid interior** cell which failed the gate is a gate cut.

        This bed's last row is a structural terminal, so a gate ending one row above it would
        end on that terminal. Ending two rows above it makes the tail's receiver an interior
        cell outside the channel: that is the gate cut, and it is recorded, not raised.
        """
        fixture = straight_bed()
        rows, columns = fixture["valid"].shape
        routable, terminals = precompute.routable_channel(
            gate_mask=gate_trunk(fixture, 2, rows - 3), receiver=fixture["receiver"])
        self.assertEqual(int(terminals.sum()), 0)
        segmentation = precompute.segment_on_channel(
            receiver=fixture["receiver"], valid_mask=fixture["valid"], channel_mask=routable)
        downstream, ends = precompute.reach_downstream(
            receiver=fixture["receiver"], chains=segmentation["chains"],
            terminal_kind=fixture["kinds"])
        self.assertEqual(int(downstream[0]), -1)
        self.assertEqual(len(ends), 1)
        self.assertEqual(ends[0]["reason"], "gate_cut")
        self.assertEqual(ends[0]["tail_cell_flat"], (rows - 3) * columns + fixture["trunk"])

    def test_a_junction_starts_a_new_reach_downstream(self):
        rows, columns = 5, 5
        receiver = np.full((rows, columns), -1, np.int64)
        receiver[0, 1] = 1 * columns + 2
        receiver[0, 3] = 1 * columns + 2
        for z in range(1, rows - 1):
            receiver[z, 2] = (z + 1) * columns + 2
        valid = np.zeros((rows, columns), np.bool_)
        valid[0, 1] = valid[0, 3] = True
        for z in range(1, rows):
            valid[z, 2] = True
        routable, terminals = precompute.routable_channel(gate_mask=valid, receiver=receiver)
        self.assertTrue(bool(terminals[rows - 1, 2]))
        segmentation = precompute.segment_on_channel(receiver=receiver, valid_mask=valid,
                                                     channel_mask=routable)
        self.assertEqual(len(segmentation["chains"]), 3)
        for chain in segmentation["chains"]:
            self.assertGreaterEqual(int(receiver.reshape(-1)[chain[-1]]), 0)

    def test_a_cycle_of_channel_cells_is_refused(self):
        rows, columns = 3, 3
        receiver = np.full((rows, columns), -1, np.int64)
        receiver[0, 0] = 1
        receiver[0, 1] = 0
        valid = np.zeros((rows, columns), np.bool_)
        valid[0, 0] = valid[0, 1] = True
        with self.assertRaises(RuntimeError):
            precompute.segment_on_channel(receiver=receiver, valid_mask=valid,
                                          channel_mask=valid)

    def test_the_reach_ceiling_refuses_rather_than_dropping_reaches(self):
        fixture = straight_bed()
        routable, _ = precompute.routable_channel(
            gate_mask=gate_trunk(fixture), receiver=fixture["receiver"])
        with self.assertRaises(ValueError):
            precompute.segment_on_channel(receiver=fixture["receiver"],
                                          valid_mask=fixture["valid"],
                                          channel_mask=routable, max_reaches=0)


class SideInputTests(unittest.TestCase):
    def _setup(self, steps=3, flux=0.5):
        """A trunk gated from row 2 down, with two supply cells above the cut.

        The two supply cells drain straight into the first channel cell, so the branch has a
        real entry and a non-empty delivery.
        """
        fixture = straight_bed()
        rows, columns = fixture["valid"].shape
        routable, _ = precompute.routable_channel(
            gate_mask=gate_trunk(fixture, 2, rows - 2), receiver=fixture["receiver"])
        supply = np.zeros((rows, columns), np.bool_)
        supply[0:2, fixture["trunk"]] = True
        local = np.zeros((steps, rows, columns), np.float64)
        local[:, 0:2, fixture["trunk"]] = flux
        return fixture, routable, supply, local, steps

    def test_a_branch_is_assigned_to_its_real_entry_cell(self):
        fixture, channel, supply, local, steps = self._setup()
        assigned = precompute.assign_local_branches(
            receiver=fixture["receiver"], valid_mask=fixture["valid"],
            channel_mask=channel, supply_mask=supply, origin_native_xz=[1000, 2000])
        self.assertEqual(len(assigned["branches"]), 1)
        branch = assigned["branches"][0]
        self.assertEqual(branch["member_count"], 2)
        self.assertEqual(int(branch["entry_receiver_cell_flat"]) // channel.shape[1], 2)
        self.assertIsNotNone(branch["member_world_sha256"])

    def test_aggregated_and_refined_agree_and_one_is_chosen(self):
        fixture, channel, supply, local, steps = self._setup()
        assigned = precompute.assign_local_branches(
            receiver=fixture["receiver"], valid_mask=fixture["valid"],
            channel_mask=channel, supply_mask=supply, origin_native_xz=[1000, 2000])
        branch = assigned["branches"][0]
        edges = np.asarray([0.0, 900.0, 1800.0, 2700.0])
        for mode in ("aggregated", "refined"):
            resolved = precompute.resolve_side_input(
                receiver=fixture["receiver"], valid_mask=fixture["valid"], branch=branch,
                local_flux=local, time_edges_s=edges, mode=mode)
            self.assertEqual(resolved["chosen"]["from"], mode)
            self.assertTrue(resolved["matches"])
            self.assertAlmostEqual(resolved["chosen"]["q_m3_s"][0], 1.0, places=12)
            self.assertEqual(resolved["chosen"]["area_cells"], 2)
            self.assertTrue(resolved["double_count_negative"]["detected"])
            self.assertNotAlmostEqual(
                resolved["double_count_negative"]["q_m3_s"][0],
                resolved["chosen"]["q_m3_s"][0], places=6)

    def test_the_two_forms_are_never_both_counted(self):
        fixture, channel, supply, local, steps = self._setup()
        assigned = precompute.assign_local_branches(
            receiver=fixture["receiver"], valid_mask=fixture["valid"],
            channel_mask=channel, supply_mask=supply, origin_native_xz=None)
        branch = assigned["branches"][0]
        resolved = precompute.resolve_side_input(
            receiver=fixture["receiver"], valid_mask=fixture["valid"], branch=branch,
            local_flux=local, time_edges_s=np.asarray([0.0, 900.0, 1800.0, 2700.0]),
            mode="refined")
        self.assertEqual(set(resolved["chosen"]), {"from", "area_cells", "q_m3_s"})
        self.assertNotIn("aggregated", resolved["chosen"])

    def test_a_wrong_step_clock_is_refused(self):
        fixture, channel, supply, local, steps = self._setup()
        assigned = precompute.assign_local_branches(
            receiver=fixture["receiver"], valid_mask=fixture["valid"],
            channel_mask=channel, supply_mask=supply, origin_native_xz=None)
        branch = assigned["branches"][0]
        with self.assertRaises(ValueError):
            precompute.resolve_side_input(
                receiver=fixture["receiver"], valid_mask=fixture["valid"], branch=branch,
                local_flux=local, time_edges_s=np.asarray([0.0, 900.0]), mode="refined")


class EventReceiverTests(unittest.TestCase):
    def _record(self, **overrides):
        payload = dict(
            terminal_cell_world_native=[1001, 2002],
            product_schema="finite-river-product-v1",
            product_identity="2" * 64,
            origin_native_xz=[1000, 2000],
            shape_zx=[317, 257],
            terminal_cell_flat=12,
            safe_level_m=799.5,
            safe_volume_m3=20854.0,
            seconds_edges_s=[0.0, 900.0, 1800.0],
            time_edge_volume_m3=[0.0, 1.0, 2.0],
            time_edge_level_m=[799.0, 799.1, 799.2],
            source_files={"product.json": "3" * 64},
            lake_bed_cell_count=16,
            active_cell_count=3951)
        payload.update(overrides)
        return precompute.build_event_receiver_record(**payload)

    def test_the_record_states_an_event_receiver_and_never_a_permanent_terminal(self):
        record = self._record()
        self.assertEqual(record["kind"], "finite_event_lake_storage")
        self.assertTrue(record["is_event_receiver"])
        self.assertFalse(record["is_permanent_terminal"])
        self.assertEqual(record["edges_with_stored_water"], 2)
        self.assertIn("product_identity_sha256", record)

    def test_no_stored_water_is_refused(self):
        with self.assertRaises(ValueError):
            self._record(time_edge_volume_m3=[0.0, 0.0, 0.0])

    def test_a_volume_above_the_safe_bound_is_refused(self):
        with self.assertRaises(ValueError):
            self._record(time_edge_volume_m3=[0.0, 1.0, 99999.0])

    def test_a_record_without_source_digests_is_refused(self):
        with self.assertRaises(ValueError):
            self._record(source_files={})

    def test_several_reaches_may_reference_the_same_receiver(self):
        """Two inflow reaches into one lake are one receiver, not two lakes."""
        record = self._record()
        first = precompute.event_receiver_identity(record)
        second = precompute.event_receiver_identity(dict(record))
        self.assertEqual(first, second)
        other = self._record(matched_terminal_world_native=[1009, 2002])
        self.assertNotEqual(first, precompute.event_receiver_identity(other))
        narrower = self._record(safe_volume_m3=1000.0,
                                time_edge_volume_m3=[0.0, 1.0, 2.0])
        self.assertNotEqual(first, precompute.event_receiver_identity(narrower))

    def test_the_only_permanent_terminal_is_pending(self):
        terminal = precompute.permanent_terminal_pending()
        self.assertEqual(terminal["kind"], "pending")
        self.assertFalse(terminal["is_permanent_terminal"])
        self.assertIn("reason", terminal)


class BuildTests(unittest.TestCase):
    def _quantities(self, fixture, steps=2):
        rows, columns = fixture["valid"].shape
        local = np.zeros((steps, rows, columns), np.float64)
        local[:, 2:4, fixture["trunk"]] = 0.25
        available = np.ones((rows, columns), np.bool_)
        return {precompute.QUANTITY_SCENARIO: {
            "local_flux": local, "available_mask": available,
            "gate_time_index": steps - 1,
            "provenance": {"model": "synthetic_test_event", "declared": True}}}

    def test_a_build_round_trips_and_keeps_the_two_axes(self):
        fixture = straight_bed()
        parent = parent_from(fixture)
        bundle = precompute.build_backbone(
            parent=parent, quantities=self._quantities(fixture), a_min_cells=2,
            q_min_m3_s=1e-9, time_edges_s=np.asarray([0.0, 900.0, 1800.0]))
        self.assertEqual(bundle["schema"], precompute.SCHEMA)
        self.assertGreater(bundle["metadata"]["counts"]["channel_cells"], 0)
        self.assertIn(precompute.QUANTITY_SCENARIO, bundle["metadata"]["quantities"])
        # the gate selects the terminal row; it is stored as an anchor, not as a reach cell
        self.assertGreater(bundle["metadata"]["counts"]["gate_terminal_cells"], 0)
        arrays = bundle["arrays"]
        self.assertTrue(np.array_equal(arrays["gate_mask"],
                                       arrays["channel_mask"] | arrays["gate_terminal_mask"]))
        for row in bundle["reaches"]:
            self.assertIsNone(row["display_line"])
            self.assertIsNone(row["event_receiver"])
            self.assertIn(row["terminal_reason"], (None, "gate_cut", "structural_terminal"))
            if row["permanent_terminal"] is not None:
                self.assertEqual(row["permanent_terminal"]["kind"], "pending")
                self.assertEqual(row["terminal_reason"], "structural_terminal")
        precompute.validate_backbone(bundle, parent)

    def test_a_pending_quantity_keeps_the_area_selection(self):
        fixture = straight_bed()
        parent = parent_from(fixture)
        bundle = precompute.build_backbone(
            parent=parent, quantities={}, a_min_cells=2, q_min_m3_s=1e-9,
            time_edges_s=np.asarray([0.0, 900.0]))
        self.assertGreater(bundle["metadata"]["counts"]["channel_cells"], 0)
        self.assertEqual(bundle["metadata"]["quantities"], {})
        self.assertTrue(str(bundle["metadata"]["flux_availability"]).startswith(
            "not_available_pending"))

    def test_a_side_input_is_stored_as_one_slot_per_branch(self):
        fixture = straight_bed()
        parent = parent_from(fixture)
        rows, columns = fixture["valid"].shape
        quantities = self._quantities(fixture)
        bundle = precompute.build_backbone(
            parent=parent, quantities=quantities, a_min_cells=2, q_min_m3_s=1e-9,
            time_edges_s=np.asarray([0.0, 900.0, 1800.0]),
            side_inputs={precompute.QUANTITY_SCENARIO: {"mode": "refined",
                                                        "max_branches": 8}})
        record = bundle["metadata"]["side_inputs"][precompute.QUANTITY_SCENARIO]
        self.assertEqual(record["mode"], "refined")
        self.assertFalse(record["inherited_port_field_used"])
        for branch in record["branches"]:
            self.assertEqual(branch["chosen"]["from"], "refined")
            self.assertTrue(branch["double_count_negative"]["detected"])
        precompute.validate_backbone(bundle, parent)

    def test_a_tampered_node_series_is_refused(self):
        fixture = straight_bed()
        parent = parent_from(fixture)
        bundle = precompute.build_backbone(
            parent=parent, quantities=self._quantities(fixture), a_min_cells=2,
            q_min_m3_s=1e-9, time_edges_s=np.asarray([0.0, 900.0, 1800.0]))
        name = "node_q_%s_m3_s" % precompute.QUANTITY_SCENARIO
        tampered = {key: (np.array(value, copy=True) if isinstance(value, np.ndarray) else value)
                    for key, value in bundle["arrays"].items()}
        tampered[name][0, 0] += 1.0
        altered = dict(bundle)
        altered["arrays"] = tampered
        with self.assertRaises(ValueError):
            precompute.validate_backbone(altered, parent)

    def test_a_reach_id_is_world_anchored(self):
        """The same world path keeps its id; moving the window or the gate changes it.

        ``origin`` is part of the world coordinate of every cell, so shifting it moves the
        world points (and the id); the gate thresholds are part of the identity payload.
        """
        fixture = straight_bed()
        parent = parent_from(fixture)
        quantities = self._quantities(fixture)
        first = precompute.build_backbone(
            parent=parent, quantities=quantities, a_min_cells=2, q_min_m3_s=1e-9,
            time_edges_s=np.asarray([0.0, 900.0, 1800.0]))
        rebuilt = precompute.build_backbone(
            parent=parent_from(fixture), quantities=quantities, a_min_cells=2,
            q_min_m3_s=1e-9, time_edges_s=np.asarray([0.0, 900.0, 1800.0]))
        self.assertEqual([row["reach_id"] for row in first["reaches"]],
                         [row["reach_id"] for row in rebuilt["reaches"]])
        moved = parent_from(fixture)
        moved["metadata"] = dict(moved["metadata"])
        moved["metadata"]["support"] = dict(moved["metadata"]["support"])
        moved["metadata"]["support"]["origin_native_xz"] = [1001, 2000]
        shifted = precompute.build_backbone(
            parent=moved, quantities=quantities, a_min_cells=2, q_min_m3_s=1e-9,
            time_edges_s=np.asarray([0.0, 900.0, 1800.0]))
        self.assertNotEqual([row["reach_id"] for row in first["reaches"]],
                            [row["reach_id"] for row in shifted["reaches"]])
        changed = precompute.build_backbone(
            parent=parent_from(fixture), quantities=quantities, a_min_cells=3,
            q_min_m3_s=1e-9, time_edges_s=np.asarray([0.0, 900.0, 1800.0]))
        self.assertNotEqual([row["reach_id"] for row in first["reaches"]],
                            [row["reach_id"] for row in changed["reaches"]])


if __name__ == "__main__":
    unittest.main()
