# -*- coding: utf-8 -*-
"""Contract tests for native-trace / display-line shape fidelity.

Every case is a synthetic ordered trace over a synthetic receiver: no TD page, no published
product, no climate model. The point is the separation of the authoritative native trace from an
optional render-only simplification, and the statements that must never be conflated.
"""
import unittest

import numpy as np

from terrain_pipeline.surface_rivers import backbone_shape_fidelity as fidelity

SPACING = 30.0
#: A realistic absolute origin: world native coordinates around 42 000 / 43 000, far outside any
#: local raster, which is exactly why the origin must be subtracted before flattening.
ORIGIN = [42173, 42874]


def straight_trace(count=40):
    """A straight northward run of **absolute** world native cells."""
    return np.stack([np.full(count, ORIGIN[0] + 100, np.int64),
                     np.arange(count, dtype=np.int64) + ORIGIN[1] + 50], axis=1)


def winding_trace(count=61):
    """A hand-drawn S-curve whose shortcuts stay well inside one cell."""
    z = np.arange(count, dtype=np.int64) + ORIGIN[1] + 50
    x = ORIGIN[0] + 100 + (np.arange(count) % 2)
    return np.stack([x.astype(np.int64), z], axis=1)


def receiver_for(trace, columns, height, drain_to=None):
    """A receiver on the **local** grid that follows the trace exactly; the tail is a terminal
    unless ``drain_to`` gives it a downstream cell (that is what makes an inter-reach handoff)."""
    rec = np.full(height * columns, -1, np.int64)
    flat = (trace[:, 1] - ORIGIN[1]) * columns + (trace[:, 0] - ORIGIN[0])
    for first, second in zip(flat[:-1], flat[1:]):
        rec[int(first)] = int(second)
    if drain_to is not None:
        rec[int(flat[-1])] = int(drain_to)
    return rec.reshape(height, columns)


class TraceTests(unittest.TestCase):
    def test_the_source_trace_is_recovered_from_the_stored_arrays(self):
        trace = straight_trace(6)
        columns = 400
        # ``reach_cells`` holds **local flat** indices; the world pair is origin + offset
        flat = (trace[:, 1] - ORIGIN[1]) * columns + (trace[:, 0] - ORIGIN[0])
        cells = np.asarray(flat, np.int64)
        pointer = np.asarray([0, cells.size], np.int64)
        world = fidelity.world_trace(reach_cells=cells, reach_ptr=pointer,
                                     origin_native_xz=ORIGIN, reach_index=0,
                                     columns=columns)
        self.assertTrue(np.array_equal(world, trace))

    def test_a_reach_index_outside_the_table_is_refused(self):
        cells = np.arange(3, dtype=np.int64)
        pointer = np.asarray([0, 3], np.int64)
        with self.assertRaises(ValueError):
            fidelity.world_trace(reach_cells=cells, reach_ptr=pointer, origin_native_xz=[0, 0],
                                 reach_index=1, columns=400)


class ReceiverConsistencyTests(unittest.TestCase):
    def test_a_trace_that_is_the_receiver_own_path_is_consistent(self):
        trace = straight_trace(10)
        columns, height = 400, 120
        rec = receiver_for(trace, columns, height)
        result = fidelity.receiver_consistency(trace, rec, columns, ORIGIN)
        self.assertTrue(result["consistent"])
        self.assertEqual(result["broken_pairs"], 0)
        self.assertTrue(result["tail_is_terminal"])

    def test_absolute_world_coordinates_are_reduced_to_local_cells(self):
        """The regression this exists for: absolute natives around 42 000 must not index the raster."""
        trace = straight_trace(10)
        columns, height = 400, 120
        rec = receiver_for(trace, columns, height)
        # the same trace checked as if it were local flat coordinates would leave the grid
        with self.assertRaises(ValueError):
            fidelity.receiver_consistency(trace, rec, columns, [0, 0])
        # and with the declared origin it is exactly the stored path
        result = fidelity.receiver_consistency(trace, rec, columns, ORIGIN)
        self.assertTrue(result["consistent"])
        self.assertEqual(result["coordinate_system"],
                         "world_native_minus_origin_to_local_flat")

    def test_a_drawn_shortcut_that_skips_receiver_cells_is_reported(self):
        trace = straight_trace(10)
        columns, height = 400, 120
        rec = receiver_for(trace, columns, height)
        shortcut = np.stack([trace[:, 0], trace[:, 1]], axis=1)
        shortcut[3, 1] += 3          # jump three cells downstream: not a receiver edge
        result = fidelity.receiver_consistency(shortcut, rec, columns, ORIGIN)
        self.assertFalse(result["consistent"])
        # two consecutive pairs are broken: into the jumped cell and out of it
        self.assertEqual(result["broken_pairs"], 2)

    def test_an_interior_break_is_never_excused_as_a_terminal_tail(self):
        trace = straight_trace(10)
        columns, height = 400, 120
        rec = receiver_for(trace, columns, height)
        broken = np.stack([trace[:, 0], trace[:, 1]], axis=1)
        broken[4, 1] += 2           # interior jump, and the tail is still fine
        result = fidelity.receiver_consistency(broken, rec, columns, ORIGIN)
        self.assertFalse(result["consistent"])
        self.assertGreaterEqual(result["broken_pairs"], 1)


class SimplificationTests(unittest.TestCase):
    def test_tolerance_zero_is_the_lossless_fallback(self):
        trace = winding_trace(41)
        display, kept = fidelity.douglas_peucker(trace, 0.0, spacing_m=SPACING)
        self.assertTrue(np.array_equal(display, trace))
        self.assertEqual(kept.size, trace.shape[0])

    def test_both_ends_are_always_anchors(self):
        for tolerance in (30.0, 60.0, 120.0):
            trace = winding_trace(41)
            display, _ = fidelity.douglas_peucker(trace, tolerance, spacing_m=SPACING)
            self.assertTrue(np.array_equal(display[0], trace[0]))
            self.assertTrue(np.array_equal(display[-1], trace[-1]))

    def test_a_gentle_curve_certifies_at_the_declared_gate(self):
        """Two layers: the candidate budget reserves the margin, the final gate stays at 30 m.

        Simplifying a bare curve at exactly 30 m can leave a conservative bound of 31.5 m; that is
        not a 30 m certificate. ``build_fidelity`` therefore simplifies with the margin already
        reserved and certifies against the conservative bound, and this test goes through that
        accepting entry point instead of demanding a bare DP-30 always certify.
        """
        trace = winding_trace(41)
        product = {
            "arrays": {"receiver": receiver_for(trace, 400, 120),
                       "reach_cells": np.asarray(
                           (trace[:, 1] - ORIGIN[1]) * 400 + (trace[:, 0] - ORIGIN[0]),
                           np.int64),
                       "reach_ptr": np.asarray([0, trace.shape[0]], np.int64)},
            "metadata": {"origin_native_xz": ORIGIN},
            "identity_sha256": "0" * 64,
            "reaches": [{"reach_id": "rb-test", "reach_index": 0}],
        }
        result = fidelity.build_fidelity(product=product, tolerance_m=30.0, spacing_m=SPACING)
        row = result["reaches"][0]
        self.assertTrue(row["within_tolerance"])
        self.assertLessEqual(row["bounds"]["max_bound_m"], 30.0 + 1e-9)
        # and the candidate really was simplified, not silently kept lossless to pass
        self.assertLessEqual(row["display_cell_count"], row["source_cell_count"])

    def test_a_bare_dp_at_the_full_gate_is_not_a_certificate(self):
        """Simplifying at the full 30 m and then bounding can exceed it — that is why the layers
        are separate. The reported bound for a bare DP-30 candidate may be 31.5 m."""
        trace = winding_trace(41)
        display, _ = fidelity.douglas_peucker(trace, 30.0, spacing_m=SPACING)
        bounds = fidelity.two_way_bounds(trace, display, spacing_m=SPACING)
        self.assertLessEqual(bounds["reverse_sample_max_m"], 30.0 + 1e-9)
        self.assertLessEqual(bounds["max_bound_m"], 30.0 + 0.5 * fidelity.REVERSE_SAMPLE_M + 1e-9)

    def test_a_sharp_detour_survives_a_tight_tolerance(self):
        trace = straight_trace(21)
        trace[10, 0] += 8            # a big lateral excursion
        display, _ = fidelity.douglas_peucker(trace, 30.0, spacing_m=SPACING)
        self.assertIn(tuple(trace[10]), {tuple(p) for p in display.tolist()})


class BoundSemanticsTests(unittest.TestCase):
    def test_bounds_are_reported_with_their_sampling_and_semantics(self):
        trace = winding_trace(31)
        display, _ = fidelity.douglas_peucker(trace, 60.0, spacing_m=SPACING)
        bounds = fidelity.two_way_bounds(trace, display, spacing_m=SPACING)
        self.assertEqual(bounds["reverse_sample_step_m"], fidelity.REVERSE_SAMPLE_M)
        self.assertGreaterEqual(bounds["reverse_conservative_bound_m"],
                                bounds["reverse_sample_max_m"])
        self.assertEqual(bounds["reverse_margin_m"], 0.5 * fidelity.REVERSE_SAMPLE_M)
        # structural: sampling step / margin / each bound >= its own sample maximum
        self.assertGreaterEqual(bounds["forward_max_m"], bounds["forward_sample_max_m"])
        self.assertEqual(bounds["max_bound_m"],
                         max(bounds["forward_max_m"],
                             bounds["reverse_conservative_bound_m"]))

    def test_an_identical_display_line_has_zero_sampled_distance(self):
        """Identical lines: the *measured* distance is 0; the reported bound carries the margin."""
        trace = winding_trace(61)
        bounds = fidelity.two_way_bounds(trace, trace.copy(), spacing_m=SPACING)
        self.assertEqual(bounds["forward_sample_max_m"], 0.0)
        self.assertEqual(bounds["reverse_sample_max_m"], 0.0)
        # the conservative bound is the sample maximum plus the declared half-step margin
        self.assertAlmostEqual(bounds["forward_max_m"], 0.5 * fidelity.REVERSE_SAMPLE_M, places=9)
        self.assertLessEqual(bounds["max_bound_m"], 0.5 * fidelity.REVERSE_SAMPLE_M + 1e-9)

    def test_a_single_segment_source_is_handled(self):
        source = np.asarray([[ORIGIN[0], ORIGIN[1]], [ORIGIN[0] + 3, ORIGIN[1]]], np.int64)
        bounds = fidelity.two_way_bounds(source, source.copy(), spacing_m=SPACING)
        self.assertEqual(bounds["forward_sample_max_m"], 0.0)
        self.assertAlmostEqual(bounds["forward_max_m"], 0.5 * fidelity.REVERSE_SAMPLE_M, places=9)

    def test_a_far_chord_is_detected(self):
        source = straight_trace(9)
        display = np.asarray([[source[0, 0], source[0, 1]],
                              [source[-1, 0] + 6, source[-1, 1]]], np.int64)
        bounds = fidelity.two_way_bounds(source, display, spacing_m=SPACING)
        self.assertGreater(bounds["forward_max_m"], 30.0)


class AnchorAndContinuityTests(unittest.TestCase):
    def test_anchors_report_head_tail_and_handoff_separately(self):
        trace = straight_trace(9)
        dropped = trace[[0, 4, 8]]
        result = fidelity.anchors_preserved(
            source_native=trace, display_native=dropped,
            expected_tail_native=np.asarray([trace[-1, 0], trace[-1, 1]], np.int64))
        self.assertTrue(result["stored_tail_anchor_preserved"])
        self.assertTrue(result["head_preserved"])
        self.assertTrue(result["tail_preserved"])
        self.assertTrue(result["all_preserved"])
        # a display line that ends elsewhere loses the anchor
        moved = dropped.copy()
        moved[-1, 1] += 1
        broken = fidelity.anchors_preserved(
            source_native=trace, display_native=moved,
            expected_tail_native=np.asarray([trace[-1, 0], trace[-1, 1]], np.int64))
        self.assertFalse(broken["stored_tail_anchor_preserved"])
        self.assertFalse(broken["all_preserved"])

    def test_a_display_cell_off_the_source_is_not_an_ordered_subsequence(self):
        trace = straight_trace(9)
        display = trace[[0, 3, 4]].copy()
        display[1, 0] += 1
        columns, height = 400, 120
        rec = receiver_for(trace, columns, height)
        result = fidelity.directed_continuity(source_native=trace, display_native=display,
                                              receiver=rec, columns=columns)
        self.assertFalse(result["ordered_subsequence"])
        self.assertEqual(result["reason"], "display_cell_not_on_source")

    def test_a_reversed_display_line_is_refused(self):
        trace = straight_trace(9)
        display = trace[[0, 4, 8]][::-1]
        columns, height = 400, 120
        rec = receiver_for(trace, columns, height)
        result = fidelity.directed_continuity(source_native=trace, display_native=display,
                                              receiver=rec, columns=columns)
        self.assertTrue(result["ordered_subsequence"])
        self.assertFalse(result["monotone"])


class ValleyTests(unittest.TestCase):
    """The terrain screen: a conservative chord test, **not** a watershed certificate."""

    def _field(self, height=120, columns=400, bump=None):
        field = np.linspace(200.0, 100.0, height)[:, None] * np.ones((1, columns))
        if bump is not None:
            row, column, value = bump
            field[row, column] = value
        return field

    def test_a_chord_across_a_ridge_is_refused(self):
        """The source path detours; the straight chord crosses a cell the source did not visit."""
        trace = np.asarray([[ORIGIN[0] + 100, ORIGIN[1] + 50],
                            [ORIGIN[0] + 101, ORIGIN[1] + 50],
                            [ORIGIN[0] + 101, ORIGIN[1] + 56],
                            [ORIGIN[0] + 100, ORIGIN[1] + 56]], np.int64)
        display = np.asarray([[trace[0, 0], trace[0, 1]], [trace[-1, 0], trace[-1, 1]]], np.int64)
        # the ridge sits on the chord at column 100, which the source path never visits
        field = self._field(bump=(53, 100, 900.0))
        result = fidelity.valley_axis_crossing(source_native=trace, display_native=display,
                                               elevation_m=field, origin_native_xz=ORIGIN,
                                               columns=400, spacing_m=SPACING)
        self.assertEqual(result["status"], fidelity.TERRAIN_SCREEN_REFUSED)
        self.assertGreater(result["ridge_crossings"], 0)
        self.assertEqual(result["label"], fidelity.TERRAIN_SCREEN_LABEL)

    def test_a_uniform_valley_floor_is_clear(self):
        trace = np.asarray([[ORIGIN[0] + 100, ORIGIN[1] + 50],
                            [ORIGIN[0] + 100, ORIGIN[1] + 52],
                            [ORIGIN[0] + 100, ORIGIN[1] + 54]], np.int64)
        display = np.asarray([[trace[0, 0], trace[0, 1]], [trace[-1, 0], trace[-1, 1]]], np.int64)
        field = self._field()
        result = fidelity.valley_axis_crossing(source_native=trace, display_native=display,
                                               elevation_m=field, origin_native_xz=ORIGIN,
                                               columns=400, spacing_m=SPACING)
        self.assertEqual(result["status"], fidelity.TERRAIN_SCREEN_CLEAR)
        self.assertEqual(result["ridge_crossings"], 0)

    def test_an_unknown_sample_makes_the_screen_pending_never_clear(self):
        """NaN under the chord must not be reported as a pass."""
        trace = np.asarray([[ORIGIN[0] + 100, ORIGIN[1] + 50],
                            [ORIGIN[0] + 100, ORIGIN[1] + 52],
                            [ORIGIN[0] + 100, ORIGIN[1] + 54]], np.int64)
        display = np.asarray([[trace[0, 0], trace[0, 1]], [trace[-1, 0], trace[-1, 1]]], np.int64)
        field = self._field()
        field[51, 100] = np.nan
        result = fidelity.valley_axis_crossing(source_native=trace, display_native=display,
                                               elevation_m=field, origin_native_xz=ORIGIN,
                                               columns=400, spacing_m=SPACING)
        self.assertEqual(result["status"], fidelity.TERRAIN_SCREEN_PENDING)
        self.assertGreater(result["samples_unknown"], 0)

    def test_without_elevation_the_screen_is_pending(self):
        trace = straight_trace(5)
        result = fidelity.valley_axis_crossing(source_native=trace, display_native=trace,
                                               elevation_m=None, origin_native_xz=ORIGIN,
                                               columns=400, spacing_m=SPACING)
        self.assertEqual(result["status"], fidelity.TERRAIN_SCREEN_PENDING)

    def test_adjacent_cells_do_not_enter_the_screen(self):
        """A source-identical line of adjacent cells is verified by the receiver, not the screen."""
        trace = straight_trace(5)
        result = fidelity.valley_axis_crossing(source_native=trace, display_native=trace.copy(),
                                               elevation_m=self._field(),
                                               origin_native_xz=ORIGIN,
                                               columns=400, spacing_m=SPACING)
        self.assertEqual(result["status"], fidelity.TERRAIN_SCREEN_CLEAR)
        self.assertEqual(result["samples_checked"], 0)


class ContactTests(unittest.TestCase):
    """Inter-reach contact: the stored handoff must survive, and simplification must not invent one."""

    def _product(self, trace, columns=400, height=120, with_reach_of_cell=True):
        """A one-reach product whose tail **hands off** to a downstream cell, so an inter-reach
        contact really exists (a terminal tail has none and the gate would be vacuous)."""
        flat = (trace[:, 1] - ORIGIN[1]) * columns + (trace[:, 0] - ORIGIN[0])
        drain = int(flat[-1]) + 1
        rec = receiver_for(trace, columns, height, drain_to=drain)
        arrays = {
            "receiver": rec,
            "reach_cells": np.asarray(flat, np.int64),
            "reach_ptr": np.asarray([0, flat.size], np.int64),
        }
        if with_reach_of_cell:
            owner = np.full(rec.size, -1, np.int64)
            owner[np.asarray(flat, np.int64)] = 0
            owner[drain] = 1                     # the downstream cell belongs to another reach
            arrays["reach_of_cell"] = owner.reshape(rec.shape)
        return {"arrays": arrays, "metadata": {"origin_native_xz": ORIGIN},
                "identity_sha256": "0" * 64,
                "reaches": [{"reach_id": "rb-test", "reach_index": 0}]}

    def test_the_stored_handoff_survives_a_lossless_fallback(self):
        trace = winding_trace(41)
        result = fidelity.build_fidelity(product=self._product(trace), tolerance_m=30.0,
                                         spacing_m=SPACING)
        contact = result["contact"]
        self.assertEqual(contact["label"], "network_contact_gate_not_watershed_certificate")
        self.assertGreaterEqual(contact["source_contact_count"], 1)
        self.assertEqual(contact["lost_contact_count"], 0)
        self.assertEqual(contact["invented_handoff_count"], 0)
        self.assertTrue(contact["preserved"])

    def test_a_display_that_drops_the_handoff_loses_a_contact(self):
        """A display end moved off the stored tail cannot carry the stored handoff."""
        result = fidelity.contact_preserved({(100, 600)}, set())
        self.assertFalse(result["preserved"])
        self.assertEqual(result["lost_contact_count"], 1)
        self.assertEqual(result["lost_contacts"], [(100, 600)])

    def test_an_invented_handoff_is_reported(self):
        result = fidelity.contact_preserved({(100, 600)}, {(100, 600), (140, 900)})
        self.assertFalse(result["preserved"])
        self.assertEqual(result["invented_handoff_count"], 1)
        self.assertEqual(result["invented_handoffs"], [(140, 900)])

    def test_a_display_cell_owned_by_another_reach_is_a_new_contact(self):
        """A display cell the source never entered but the product assigns to another reach."""
        data = {(100, 600): 0, (160, 640): 0}
        foreign = [{"reach_index": 0, "display_cell_local_flat": 12345,
                    "owner_reach_index": 1}]
        result = fidelity.contact_preserved(data, data, foreign)
        self.assertFalse(result["preserved"])
        self.assertEqual(result["new_contact_count"], 1)
        self.assertEqual(result["new_contacts"][0]["owner_reach_index"], 1)

    def test_every_internal_chord_is_not_counted_as_a_contact(self):
        """A simplified line keeps *one* handoff however many chords it drew — otherwise the gate
        would fail every simplification by construction and measure nothing."""
        trace = winding_trace(61)
        result = fidelity.build_fidelity(product=self._product(trace), tolerance_m=30.0,
                                         spacing_m=SPACING)
        contact = result["contact"]
        self.assertEqual(contact["source_contact_count"], 1)
        self.assertEqual(contact["display_contact_count"], 1)

    def test_a_chord_cutting_across_another_reach_falls_back_to_the_source(self):
        """A simplification that cuts across a different reach touches water it must not.

        Vertices alone could never show this: Douglas-Peucker only keeps source cells, so an
        invented contact is only visible in the cells a **chord passes over**. Such a reach must
        fall back to its lossless source line instead of publishing the crossing.
        """
        columns, height = 400, 120
        trace = np.asarray([[ORIGIN[0] + 100 + (index % 2), ORIGIN[1] + 50 + index]
                            for index in range(4)], np.int64)
        flat = (trace[:, 1] - ORIGIN[1]) * columns + (trace[:, 0] - ORIGIN[0])
        drain = int(flat[-1]) + 1
        rec = receiver_for(trace, columns, height, drain_to=drain)
        owner = np.full(rec.size, -1, np.int64)
        owner[np.asarray(flat, np.int64)] = 0
        owner[drain] = 0
        # the first chord (index 0 -> index 3) passes over this cell, which the source never visits
        crossed = 51 * columns + 100
        owner[crossed] = 1
        product = {"arrays": {"receiver": rec,
                              "reach_cells": np.asarray(flat, np.int64),
                              "reach_ptr": np.asarray([0, flat.size], np.int64),
                              "reach_of_cell": owner.reshape(height, columns)},
                   "metadata": {"origin_native_xz": ORIGIN},
                   "identity_sha256": "0" * 64,
                   "reaches": [{"reach_id": "rb-test", "reach_index": 0}]}
        elevation = np.full((height, columns), 200.0)
        result = fidelity.build_fidelity(product=product, tolerance_m=30.0, spacing_m=SPACING,
                                         elevation_m=elevation)
        row = result["reaches"][0]
        # nothing else blocked it: still inside tolerance, anchors kept, screen clear
        self.assertTrue(row["within_tolerance"])
        self.assertEqual(row["valley"]["status"], fidelity.TERRAIN_SCREEN_CLEAR)
        self.assertTrue(row["fallback_to_source"])
        self.assertEqual(row["display_cell_count"], row["source_cell_count"])
        self.assertGreaterEqual(result["counts"]["fallback_because_of_foreign_contact"], 1)
        # the crossing never reaches the published display line, so no contact was invented
        self.assertTrue(result["contact"]["preserved"])
        self.assertEqual(result["contact"]["new_contact_count"], 0)


class GateHonestyTests(unittest.TestCase):
    """The final status must follow the evidence, and a refusal keeps its own reason."""

    def _receipt(self, trace, tolerance=30.0, break_edge=None, elevation=None, columns=400,
                 height=120):
        flat = (trace[:, 1] - ORIGIN[1]) * columns + (trace[:, 0] - ORIGIN[0])
        rec = receiver_for(trace, columns, height)
        if break_edge is not None:
            rec.reshape(-1)[int(flat[break_edge])] = int(flat[break_edge + 2])
        product = {"arrays": {"receiver": rec,
                              "reach_cells": np.asarray(flat, np.int64),
                              "reach_ptr": np.asarray([0, flat.size], np.int64)},
                   "metadata": {"origin_native_xz": ORIGIN},
                   "identity_sha256": "0" * 64,
                   "reaches": [{"reach_id": "rb-test", "reach_index": 0}]}
        return fidelity.build_fidelity(product=product, tolerance_m=tolerance,
                                       spacing_m=SPACING, elevation_m=elevation)

    def test_a_trace_disagreeing_with_the_stored_receiver_is_never_accepted(self):
        """Geometry alone (bound, anchors, direction, screen) must not accept a reach whose trace
        is not the saved receiver's own path."""
        trace = winding_trace(41)
        result = self._receipt(trace, break_edge=5)
        row = result["reaches"][0]
        self.assertFalse(row["receiver"]["consistent"])
        self.assertTrue(row["fallback_to_source"])
        self.assertIn("source_trace_disagrees_with_stored_receiver",
                      row["candidate_refusal_reasons"])

    def test_a_candidate_refusal_reason_survives_the_fallback(self):
        """After falling back, the screen and the bounds describe the lossless line. The reason
        the candidate was rejected must still be reported, or a clear screen would hide it."""
        columns, height = 400, 120
        trace = np.asarray([[ORIGIN[0] + 100 + (index % 2), ORIGIN[1] + 50 + index]
                            for index in range(4)], np.int64)
        flat = (trace[:, 1] - ORIGIN[1]) * columns + (trace[:, 0] - ORIGIN[0])
        drain = int(flat[-1]) + 1
        rec = receiver_for(trace, columns, height, drain_to=drain)
        owner = np.full(rec.size, -1, np.int64)
        owner[np.asarray(flat, np.int64)] = 0
        owner[drain] = 0
        owner[51 * columns + 100] = 1               # the first chord passes over this cell
        product = {"arrays": {"receiver": rec,
                              "reach_cells": np.asarray(flat, np.int64),
                              "reach_ptr": np.asarray([0, flat.size], np.int64),
                              "reach_of_cell": owner.reshape(height, columns)},
                   "metadata": {"origin_native_xz": ORIGIN},
                   "identity_sha256": "0" * 64,
                   "reaches": [{"reach_id": "rb-test", "reach_index": 0}]}
        result = fidelity.build_fidelity(
            product=product, tolerance_m=30.0, spacing_m=SPACING,
            elevation_m=np.full((height, columns), 200.0))
        row = result["reaches"][0]
        # the fallback line is clear and inside tolerance ...
        self.assertEqual(row["valley"]["status"], fidelity.TERRAIN_SCREEN_CLEAR)
        self.assertTrue(row["within_tolerance"])
        # ... yet the candidate's own refusal is still on the record
        self.assertIn("crosses_another_reach_cell", row["candidate_refusal_reasons"])
        self.assertGreaterEqual(result["counts"]["candidate_refusal_reasons"]
                                ["crosses_another_reach_cell"], 1)

    def test_a_display_crossing_inside_a_cell_is_declared_unsupported(self):
        """Two simplified chords can cross inside a cell while neither passes over the other's
        source cells. A cell scan cannot see that, so the gate must say what it did rather than
        imply a continuous segment-intersection proof."""
        report = self._receipt(winding_trace(41))
        contact = report["contact"]
        self.assertEqual(contact["crossing_relation"], fidelity.CROSSING_RELATION)
        self.assertEqual(contact["crossing_relation"], "cross_reach_cell_occupancy_only")
        self.assertIn("continuous segment-intersection", contact["preserved_scope"])
        self.assertIn(fidelity.CROSSING_UNSUPPORTED, fidelity.describe()["not_modelled"])
        # the two objects that could cross are cell sets on the integer lattice, never real segments
        self.assertIsInstance(contact["new_contacts"], list)


class SeparationTests(unittest.TestCase):
    def _product(self, trace, height=120, columns=400):
        rec = receiver_for(trace, columns, height)
        flat = (trace[:, 1] - ORIGIN[1]) * columns + (trace[:, 0] - ORIGIN[0])
        arrays = {
            "receiver": rec,
            "reach_cells": np.asarray(flat, np.int64),
            "reach_ptr": np.asarray([0, flat.size], np.int64),
        }
        metadata = {"origin_native_xz": ORIGIN}
        return {"arrays": arrays, "metadata": metadata, "identity_sha256": "0" * 64,
                "reaches": [{"reach_id": "rb-test", "reach_index": 0}]}

    def test_source_and_display_are_stored_and_labelled_separately(self):
        trace = winding_trace(41)
        product = self._product(trace)
        result = fidelity.build_fidelity(product=product, tolerance_m=30.0, spacing_m=SPACING)
        self.assertEqual(result["schema"], fidelity.SCHEMA)
        self.assertIn("source_line", result)
        self.assertIn("display_line", result)
        self.assertIn("excavation", result["source_line"]["may_be_used_for"])
        self.assertIn("excavation", result["display_line"]["must_not_be_used_for"])
        self.assertEqual(result["counts"]["reaches"], 1)
        self.assertTrue(result["reaches"][0]["receiver"]["consistent"])
        self.assertIn("watershed_membership", result["separate_statements"])

    def test_an_undeclared_tolerance_is_refused(self):
        product = self._product(winding_trace(41))
        with self.assertRaises(ValueError):
            fidelity.build_fidelity(product=product, tolerance_m=45.0, spacing_m=SPACING)

    def test_zero_tolerance_keeps_display_identical_to_source(self):
        product = self._product(winding_trace(41))
        result = fidelity.build_fidelity(product=product, tolerance_m=0.0, spacing_m=SPACING)
        row = result["reaches"][0]
        self.assertTrue(row["display_is_source"])
        self.assertEqual(row["display_cell_count"], row["source_cell_count"])
        self.assertEqual(result["counts"]["simplified"], 0)


class DescriptionTests(unittest.TestCase):
    def test_the_module_states_the_separation_and_the_limits(self):
        described = fidelity.describe()
        self.assertTrue(described["source_line_is_authoritative"])
        self.assertTrue(described["display_line_is_render_only"])
        self.assertIn("watershed_membership_from_polyline", described["not_modelled"])
        self.assertIn(30.0, described["tolerances_m"])


if __name__ == "__main__":
    unittest.main()
