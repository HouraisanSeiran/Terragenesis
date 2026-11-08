"""Synthetic pass/reject baselines for the native 30 m natural-outlet gate.

Four disciplines, stated once.

* **Nothing here is a real river.** The window is a hand-checkable ridge with a
  sea on both sides; every expected number is written out from the definition of
  the fixture, never by calling the gate twice.
* **The catchment must sit inside the window.** A cell adjacent to unresolved
  support has an undeclared upstream by definition, so a legitimate mouth cannot
  be at the edge of the resolved area. The fixture is built so the certified
  catchment is strictly interior -- and one rejection test proves the gate says
  so when a cell of that catchment is made unresolved.
* **A pass certifies the evidence algebra, not the world.** It shows the gate
  accepts a complete evidence set and refuses each incomplete one with its own
  reason code.
* **A label never becomes an outlet.** ``retained`` is where the water *stops*;
  ``unknown_boundary`` is where this run *stops looking*. Neither is a mouth, and
  the tests hand both a perfect evidence set and assert the refusal.
"""
import math
import unittest

import numpy as np

from terrain_pipeline.surface_rivers.natural_outlet_status import (
    ARTIFICIAL_WINDOW_BOUNDARY,
    CANDIDATE_STATE,
    EXPECTED_WORLD_SEED,
    GATE_NAMES,
    GRAPH_TERMINAL_LABELS,
    LAKE,
    NATIVE_SPACING_M,
    NATURAL_OUTLET,
    OPEN_OUTFLOW,
    REASON_CODES,
    REQUIRED_STATES,
    RETAINED,
    SCHEMA,
    TRUNCATED_NOT_JUDGED,
    UNKNOWN_BOUNDARY,
    certify_natural_outlet,
    state_of_terminal_kind,
    validate_report,
)

ROWS = 9
COLUMNS = 15
ROW = 4                     # strictly interior: not row 0 and not row ROWS-1
TERMINAL_COLUMN = 8         # first sea cell reached by the eastern chain
COAST_COLUMN = 9            # declared coastline, one column further east
ORIGIN_XZ = (1000, 2000)    # native index origin, not a metre value
PAGE_PIN = "a" * 64

#: The ridge profile, one value per column, plus a 0.25 m per-row tilt.
#:
#: ``[0, 10, 25, 46, 70, 44, 25, 10, 0, 0, ...]``
#:
#: * column 0 is sea (0 m) and columns 8..14 are sea (0 m), so each row has a
#:   western and an eastern mouth;
#: * the crest sits at column 4 (70 m) and is **closer to the higher western
#:   shoulder (46 m) than to the eastern one (44 m)**, so its steepest descent is
#:   east and the eastern catchment is the one this file certifies;
#: * every slope is 15..26 m per cell against 10.6..18.4 on the diagonals, so no
#:   tie can be decided by iteration order.
PROFILE = (0.0, 10.0, 25.0, 46.0, 70.0, 44.0, 25.0, 10.0, 0.0,
           0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
ROW_TILT_M = 0.25

#: Cells whose chain ends at the certified terminal: the eastern flank of the crest.
CATCHMENT_COLUMNS = (4, 5, 6, 7, 8)


def bed(rows=ROWS, columns=COLUMNS):
    """The fixture bed: :data:`PROFILE` repeated per row with :data:`ROW_TILT_M`.

    The tilt is applied to **land only**. A tilted sea would drain north into row 0
    -- the artificial window ring -- and every sea cell would then be a
    ``retained``/``unknown_boundary`` terminal at the window edge instead of a real
    interior minimum. Keeping the sea exactly flat makes each interior sea cell a
    genuine terminal (no strictly-lower neighbour among equal 0 m neighbours), which
    is the only honest way to have an interior mouth in a finite window.
    """
    height = np.empty((rows, columns), np.float64)
    for row in range(rows):
        for column in range(columns):
            base = PROFILE[column]
            height[row, column] = 0.0 if base == 0.0 else base + ROW_TILT_M * row
    return height


def independent_receiver(height):
    """Analytic graph receiver, recomputed with an explicit mesh-neighbour loop.

    Deliberately *not* the production kernel and not the module under test: this
    is the file's own statement of what the fixture's drainage is.
    """
    rows, columns = np.asarray(height).shape
    receiver = np.full((rows, columns), -1, np.int64)
    for row in range(rows):
        for column in range(columns):
            best_slope = 0.0
            best_target = -1
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr, cc = row + dr, column + dc
                    if not (0 <= rr < rows and 0 <= cc < columns):
                        continue
                    slope = (height[row, column] - height[rr, cc]) / math.hypot(dr, dc)
                    if slope > best_slope:
                        best_slope = slope
                        best_target = rr * columns + cc
            receiver[row, column] = best_target
    return receiver


def independent_terminals(receiver, height):
    """Terminal of every cell, by ascending bed height (the receiver is lower)."""
    flat_receiver = np.asarray(receiver).reshape(-1)
    flat_height = np.asarray(height).reshape(-1)
    labels = np.full(flat_height.size, -1, np.int64)
    for position in np.argsort(flat_height, kind="stable"):
        downstream_cell = int(flat_receiver[position])
        labels[position] = int(position) if downstream_cell < 0 else labels[downstream_cell]
    return labels.reshape(np.asarray(height).shape)


def window_ring(rows=ROWS, columns=COLUMNS):
    """The declared artificial boundary: this run's window ring, nothing else."""
    mask = np.zeros((rows, columns), bool)
    mask[[0, -1], :] = True
    mask[:, [0, -1]] = True
    return mask


def graph(*, height=None, valid=None, kinds=None, terminal_label=OPEN_OUTFLOW):
    """A complete graph payload: receiver, bed, resolved mask and terminal labels.

    The default terminal label is ``open_outflow`` because that is the only label a
    certificate may be built on: water must *leave* there. ``valid`` defaults to the
    whole window resolved, which is what makes the certified catchment interior.
    """
    height = bed() if height is None else np.asarray(height, np.float64)
    receiver = independent_receiver(height)
    valid = np.ones(height.shape, bool) if valid is None else np.asarray(valid, bool)
    if kinds is None:
        kinds = np.full(height.shape, "inactive", dtype="U24")
        kinds[valid & (receiver >= 0)] = "interior"
        kinds[valid & (receiver < 0)] = terminal_label
    return {"receiver": receiver, "height_m": height, "valid_mask": valid,
            "terminal_kind": kinds}


def masks(*, coastline_column=COAST_COLUMN, artificial=None, unknown=None,
          rows=ROWS, columns=COLUMNS):
    coastline = np.zeros((rows, columns), bool)
    coastline[:, coastline_column] = True
    return {"coastline_mask": coastline,
            "artificial_boundary_mask": window_ring(rows, columns)
            if artificial is None else np.asarray(artificial, bool),
            "unknown_mask": np.zeros((rows, columns), bool)
            if unknown is None else np.asarray(unknown, bool)}


def cell(row=ROW, column=TERMINAL_COLUMN, columns=COLUMNS):
    return int(row) * int(columns) + int(column)


def downstream_path(row=ROW, columns=COLUMNS):
    """The observed continuation past the terminal: one declared coastline cell."""
    return [cell(row, TERMINAL_COLUMN, columns), cell(row, COAST_COLUMN, columns)]


def source_pin(*, world_seed=EXPECTED_WORLD_SEED, spacing_m=NATIVE_SPACING_M,
               origin=ORIGIN_XZ, outlet=None, pages=(PAGE_PIN,), pinned=True):
    if outlet is None:
        outlet = [(origin[0] + TERMINAL_COLUMN) * NATIVE_SPACING_M,
                  (origin[1] + ROW) * NATIVE_SPACING_M]
    return {"world_seed": world_seed, "spacing_m": spacing_m,
            "native_origin_xz": list(origin), "outlet_world_xz_m": list(outlet),
            "page_sha256": list(pages), "pinned": pinned}


def water_quantity(*, q_m3_s=1.5, provenance="declared storm routed peak",
                   independent=True):
    return {"q_m3_s": q_m3_s, "provenance": provenance, "independent": independent}


def water_level(*, sea_level_m=0.0, water_surface_m=0.0, outlet_bed_m=0.0,
                datum="declared tidal datum (MLLW)", uncertainty_m=0.05):
    return {"sea_level_m": sea_level_m, "water_surface_m": water_surface_m,
            "outlet_bed_m": outlet_bed_m, "datum": datum,
            "uncertainty_m": uncertainty_m}


def claim(*, terminal=None, declared=NATURAL_OUTLET, columns=COLUMNS):
    return {"terminal_cell_id": cell(column=TERMINAL_COLUMN, columns=columns)
            if terminal is None else int(terminal),
            "declared_state": declared}


def downstream(*, path=None, coast=None, independent=True, columns=COLUMNS):
    return {"path_cell_ids": downstream_path(columns=columns) if path is None else list(path),
            "coastline_cell_id": cell(column=COAST_COLUMN, columns=columns)
            if coast is None else int(coast),
            "independent_observation": independent}


def certify(**overrides):
    """Call the gate with a complete evidence set, overridden piecewise."""
    arguments = {"candidate": claim(), "graph": graph(), "downstream": downstream(),
                 "masks": masks(), "source_pin": source_pin(),
                 "water_quantity": water_quantity(), "water_level": water_level()}
    arguments.update(overrides)
    return certify_natural_outlet(**arguments)


# --------------------------------------------------------------------------- #
# 0. the fixture is what this file says it is
# --------------------------------------------------------------------------- #
class EvidenceHelpers(unittest.TestCase):

    def test_the_profile_and_its_steepest_descent_are_hand_checkable(self):
        height = bed()
        expected = [(0.0 if PROFILE[column] == 0.0
                     else PROFILE[column] + ROW_TILT_M * ROW) for column in range(COLUMNS)]
        self.assertEqual([float(value) for value in height[ROW]], expected)
        # ROW = 4, so the land tilt at this row is exactly 1.0 m.
        self.assertEqual(expected[:9], [0.0, 11.0, 26.0, 47.0, 71.0, 45.0, 26.0,
                                        11.0, 0.0])
        # West of the crest the drop is 24 m; east of it 26 m. East wins, and the
        # diagonal (26 - 0.25) / sqrt(2) = 18.2 loses to 26 outright.
        self.assertEqual(71.0 - 47.0, 24.0)
        self.assertEqual(71.0 - 45.0, 26.0)
        self.assertGreater(26.0, (26.0 - ROW_TILT_M) / math.sqrt(2.0))

    def test_the_sea_is_a_genuine_interior_minimum(self):
        """Every sea cell is a terminal, and the certified one is not on the ring."""
        receiver = independent_receiver(bed())
        self.assertEqual(receiver[ROW, TERMINAL_COLUMN], -1)
        self.assertEqual(receiver[ROW, COAST_COLUMN], -1)
        self.assertFalse(window_ring()[ROW, TERMINAL_COLUMN])
        self.assertFalse(window_ring()[ROW, COAST_COLUMN])

    def test_the_eastern_chain_is_the_certified_catchment(self):
        labels = independent_terminals(independent_receiver(bed()), bed())
        catchment = np.flatnonzero(labels.reshape(-1) == cell())
        self.assertEqual(sorted(int(value) for value in catchment),
                         [cell(ROW, column) for column in CATCHMENT_COLUMNS])

    def test_the_catchment_has_no_unresolved_neighbour(self):
        """The whole point of the fixture: a legitimate mouth is strictly interior."""
        valid = np.ones((ROWS, COLUMNS), bool)
        padded = np.pad(valid, 1, mode="constant", constant_values=False)
        neighbours = np.zeros((ROWS, COLUMNS), np.int8)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                neighbours += padded[1 + dr:ROWS + 1 + dr, 1 + dc:COLUMNS + 1 + dc]
        for column in CATCHMENT_COLUMNS:
            self.assertEqual(int(neighbours[ROW, column]), 8)
        # The window ring, by contrast, never has a complete neighbourhood.
        self.assertTrue(np.all(neighbours[window_ring()] < 8))

    def test_the_evidence_cells_avoid_the_window_ring(self):
        artificial = window_ring().reshape(-1)
        for index in downstream_path():
            self.assertFalse(artificial[index])
        self.assertFalse(artificial[cell(column=COAST_COLUMN)])

    def test_the_path_has_no_uphill_step_and_does_not_re_enter(self):
        height = bed().reshape(-1)
        path = downstream_path()
        self.assertTrue(np.all(np.diff(height[path]) <= 1e-9))
        labels = independent_terminals(independent_receiver(bed()), bed()).reshape(-1)
        self.assertFalse(labels[path[1]] == path[0])


# --------------------------------------------------------------------------- #
# 1. the seven states are one vocabulary, and none of them is a certification
# --------------------------------------------------------------------------- #
class StateVocabularyTests(unittest.TestCase):

    def test_the_seven_states_are_distinct_and_complete(self):
        self.assertEqual(len(REQUIRED_STATES), 7)
        self.assertEqual(set(REQUIRED_STATES),
                         {LAKE, NATURAL_OUTLET, RETAINED, OPEN_OUTFLOW,
                          UNKNOWN_BOUNDARY, TRUNCATED_NOT_JUDGED,
                          ARTIFICIAL_WINDOW_BOUNDARY})
        self.assertNotIn(CANDIDATE_STATE, REQUIRED_STATES)

    def test_the_graph_labels_are_the_production_five_words(self):
        from terrain_pipeline.surface_rivers.metric_network_discharge_product import (
            TERMINAL_LABELS)
        self.assertEqual(tuple(TERMINAL_LABELS), tuple(GRAPH_TERMINAL_LABELS))

    def test_the_30m_source_still_cannot_emit_an_open_outflow(self):
        from terrain_pipeline.surface_rivers.native_30m_source import (
            _EMITTABLE_TERMINALS)
        self.assertNotIn(OPEN_OUTFLOW, _EMITTABLE_TERMINALS)
        self.assertNotIn(NATURAL_OUTLET, _EMITTABLE_TERMINALS)
        self.assertNotIn(LAKE, _EMITTABLE_TERMINALS)
        self.assertNotIn(TRUNCATED_NOT_JUDGED, _EMITTABLE_TERMINALS)

    def test_graph_label_to_state_never_upgrades(self):
        self.assertEqual(state_of_terminal_kind("retained"), RETAINED)
        self.assertEqual(state_of_terminal_kind("open_outflow"), OPEN_OUTFLOW)
        self.assertEqual(state_of_terminal_kind("unknown_boundary"), UNKNOWN_BOUNDARY)
        for label in ("interior", "inactive", "lake", "natural_outlet", ""):
            with self.subTest(label=label), self.assertRaises(ValueError):
                state_of_terminal_kind(label)

    def test_every_non_outlet_state_keeps_its_own_refusal(self):
        for state in REQUIRED_STATES:
            if state == NATURAL_OUTLET:
                # ``natural_outlet`` is the *claim*: with complete evidence it is
                # granted (see PassBaselineTests), never refused.
                self.assertEqual(certify()["assigned_state"], NATURAL_OUTLET)
                continue
            with self.subTest(state=state):
                report = certify(candidate=claim(declared=state))
                self.assertEqual(report["assigned_state"], state)
                self.assertFalse(report["natural_outlet_verified"])
                self.assertIn(
                    "declared_truncated_not_judged_blocks_certification"
                    if state == TRUNCATED_NOT_JUDGED
                    else "declared_%s_is_not_a_natural_outlet" % state,
                    report["failure_reasons"])

    def test_reason_codes_are_a_closed_audited_set(self):
        for name in ("declared_retained_is_not_a_natural_outlet",
                     "declared_open_outflow_is_not_a_natural_outlet",
                     "missing_continuous_downstream_coverage",
                     "graph_label_is_not_an_open_outflow",
                     "unknown_pollution_in_upstream_catchment",
                     "world_coordinate_source_pin_mismatch",
                     "zero_or_negative_discharge",
                     "outlet_bed_above_declared_sea_level"):
            self.assertIn(name, REASON_CODES)
        self.assertEqual(len(GATE_NAMES), 6)


# --------------------------------------------------------------------------- #
# 2. the pass baseline
# --------------------------------------------------------------------------- #
class PassBaselineTests(unittest.TestCase):

    def test_complete_evidence_certifies_a_multi_cell_mouth(self):
        report = certify()
        self.assertEqual(report["schema"], SCHEMA)
        validate_report(report)
        self.assertEqual(report["assigned_state"], NATURAL_OUTLET)
        self.assertTrue(report["natural_outlet_verified"])
        self.assertTrue(report["ocean_outlet_certified"])
        self.assertEqual(report["failure_reasons"], [])
        self.assertEqual(report["gates"], {name: True for name in GATE_NAMES})
        self.assertEqual(report["graph_terminal_kind"], OPEN_OUTFLOW)
        self.assertEqual(report["row_col"], [ROW, TERMINAL_COLUMN])
        self.assertEqual(report["evidence"]["upstream_catchment_cells"],
                         len(CATCHMENT_COLUMNS))
        self.assertEqual(report["evidence"]["path_cell_ids"], downstream_path())
        self.assertFalse(report["solver_called"])
        self.assertTrue(report["source_unchanged"])

    def test_the_same_evidence_produces_the_same_identity(self):
        self.assertEqual(certify()["identity_sha256"], certify()["identity_sha256"])

    def test_the_terminal_may_itself_be_the_declared_coastline_cell(self):
        coast = cell(column=COAST_COLUMN)
        seater = np.zeros((ROWS, COLUMNS), bool)
        seater[:, COAST_COLUMN] = True
        # The sea cell at COAST_COLUMN is a terminal of its own when the bed there is
        # flat: (row, 9) = (row, 8) = 0 m, so neither has a strictly-lower neighbour.
        report = certify(candidate=claim(terminal=coast),
                         downstream={"path_cell_ids": [coast],
                                     "coastline_cell_id": coast,
                                     "independent_observation": True},
                         masks={"coastline_mask": seater,
                                "artificial_boundary_mask": window_ring(),
                                "unknown_mask": np.zeros((ROWS, COLUMNS), bool)},
                         source_pin=source_pin(
                             outlet=[(ORIGIN_XZ[0] + COAST_COLUMN) * NATIVE_SPACING_M,
                                     (ORIGIN_XZ[1] + ROW) * NATIVE_SPACING_M]))
        self.assertEqual(report["assigned_state"], NATURAL_OUTLET)

    def test_a_verified_report_cannot_be_tampered_with(self):
        report = certify()
        for key, value in (("assigned_state", RETAINED),
                           ("natural_outlet_verified", False),
                           ("ocean_outlet_certified", False)):
            tampered = dict(report)
            tampered[key] = value
            with self.assertRaises(ValueError):
                validate_report(tampered)
        tampered = dict(report)
        tampered["gates"] = dict(report["gates"], water_level_evidence=False)
        with self.assertRaises(ValueError):
            validate_report(tampered)

    def test_the_report_states_its_six_gate_policy(self):
        report = certify()
        self.assertEqual(report["policy"]["required_gates"], list(GATE_NAMES))
        self.assertIn("not certifications",
                      report["policy"]["label_is_not_a_certification"])
        self.assertIn("no coastline from nodata", report["policy"]["no_inference"])


# --------------------------------------------------------------------------- #
# 3. rejections: one gate, one reason code, never a silent pass
# --------------------------------------------------------------------------- #
class DownstreamCoverageRejections(unittest.TestCase):

    def assert_refused(self, report, reason, gate="continuous_downstream_coverage"):
        validate_report(report)
        self.assertEqual(report["assigned_state"], CANDIDATE_STATE)
        self.assertFalse(report["natural_outlet_verified"])
        self.assertFalse(report["gates"][gate])
        self.assertIn(reason, report["failure_reasons"])

    def test_no_observed_path_at_all(self):
        self.assert_refused(certify(downstream=downstream(path=[])),
                            "missing_continuous_downstream_coverage")

    def test_path_endpoints_must_be_the_terminal_and_the_coast_cell(self):
        self.assert_refused(
            certify(downstream=downstream(path=[cell(column=COAST_COLUMN)])),
            "path_endpoints_mismatch")

    def test_the_terminal_must_be_a_receiver_exit(self):
        interior = cell(column=5)
        self.assert_refused(
            certify(candidate=claim(terminal=interior),
                    downstream={"path_cell_ids": [interior],
                                "coastline_cell_id": cell(column=COAST_COLUMN),
                                "independent_observation": True}),
            "terminal_is_not_receiver_exit")

    def test_the_endpoint_must_be_a_declared_coastline_cell(self):
        coast = cell(column=COAST_COLUMN)
        self.assert_refused(
            certify(masks=masks(coastline_column=COAST_COLUMN + 2),
                    downstream=downstream(path=[cell(), coast], coast=coast)),
            "endpoint_not_explicit_coastline")

    def test_a_path_through_an_unresolved_cell_is_refused(self):
        valid = np.ones((ROWS, COLUMNS), bool)
        valid[ROW, COAST_COLUMN] = False
        coast = cell(column=COAST_COLUMN)
        self.assert_refused(
            certify(graph=graph(valid=valid),
                    downstream=downstream(path=[cell(), coast], coast=coast)),
            "path_crosses_unresolved")

    def test_a_non_contiguous_path_is_refused(self):
        # (ROW, 8) -> (ROW+2, 9): a jump, and the coast mask is moved out of the way
        # so that contiguity is the first thing that fails.
        cells = [cell(), cell(ROW + 2, COAST_COLUMN)]
        self.assert_refused(
            certify(masks=masks(coastline_column=COAST_COLUMN + 2),
                    downstream=downstream(path=cells, coast=cells[-1])),
            "path_not_contiguous")

    def test_an_uphill_path_step_is_refused(self):
        height = bed()
        height[ROW, COAST_COLUMN] = 5.0               # the sea cell is lifted
        coast = cell(column=COAST_COLUMN)
        self.assert_refused(
            certify(graph=graph(height=height),
                    downstream=downstream(path=[cell(), coast], coast=coast)),
            "path_is_not_downhill")

    def test_a_path_re_entering_the_catchment_is_refused(self):
        cells = [cell(), cell(ROW, 6), cell(ROW, COAST_COLUMN)]
        self.assert_refused(
            certify(downstream=downstream(path=cells, coast=cells[-1])),
            "path_reenters_catchment")

    def test_a_duplicated_path_cell_is_refused(self):
        cells = [cell(), cell(ROW, COAST_COLUMN), cell(), cell(ROW, COAST_COLUMN)]
        self.assert_refused(
            certify(downstream=downstream(path=cells, coast=cells[-1])),
            "path_reenters_catchment")

    def test_a_single_cell_path_at_a_non_coast_terminal_is_refused(self):
        self.assert_refused(certify(downstream={"path_cell_ids": [cell()],
                                                "coastline_cell_id": cell(),
                                                "independent_observation": True}),
                            "endpoint_not_explicit_coastline")


class ArtificialBoundaryRejections(unittest.TestCase):

    def assert_refused(self, report, reason, gate="not_artificial_boundary"):
        validate_report(report)
        self.assertEqual(report["assigned_state"], CANDIDATE_STATE)
        self.assertFalse(report["gates"][gate])
        self.assertIn(reason, report["failure_reasons"])

    def test_a_terminal_on_the_window_ring_is_not_a_natural_outlet(self):
        artificial = window_ring()
        artificial[ROW, TERMINAL_COLUMN] = True
        self.assert_refused(certify(masks=masks(artificial=artificial)),
                            "terminal_on_artificial_boundary")

    def test_a_path_crossing_the_window_ring_is_not_an_outlet(self):
        artificial = window_ring()
        artificial[ROW, COAST_COLUMN] = True
        self.assert_refused(certify(masks=masks(artificial=artificial)),
                            "path_crosses_artificial_boundary")

    def test_an_unknown_boundary_terminal_is_refused_even_with_perfect_evidence(self):
        self.assert_refused(certify(graph=graph(terminal_label=UNKNOWN_BOUNDARY)),
                            "terminal_is_unknown_boundary")

    def test_a_retained_terminal_is_refused_even_with_perfect_evidence(self):
        """A ``retained`` cell is where the water *stops*, so it cannot be a mouth."""
        self.assert_refused(certify(graph=graph(terminal_label=RETAINED)),
                            "graph_label_is_not_an_open_outflow")

    def test_an_engineering_boundary_is_the_same_refusal(self):
        artificial = np.zeros((ROWS, COLUMNS), bool)
        artificial[:, TERMINAL_COLUMN] = True
        self.assert_refused(certify(masks=masks(artificial=artificial)),
                            "terminal_on_artificial_boundary")


class UnknownPollutionRejections(unittest.TestCase):

    def assert_refused(self, report, reason, gate="no_unknown_pollution"):
        validate_report(report)
        self.assertEqual(report["assigned_state"], CANDIDATE_STATE)
        self.assertFalse(report["gates"][gate])
        self.assertIn(reason, report["failure_reasons"])

    def test_an_unknown_cell_on_the_path_is_refused(self):
        unknown = np.zeros((ROWS, COLUMNS), bool)
        unknown[ROW, COAST_COLUMN] = True
        self.assert_refused(certify(masks=masks(unknown=unknown)),
                            "unknown_pollution_on_path")

    def test_an_unknown_cell_upstream_is_refused(self):
        unknown = np.zeros((ROWS, COLUMNS), bool)
        unknown[ROW, 5] = True
        self.assert_refused(certify(masks=masks(unknown=unknown)),
                            "unknown_pollution_in_upstream_catchment")

    def test_an_empty_declared_mask_cannot_hide_a_window_cut(self):
        """The defect the real TD page exposed.

        ``masks()`` defaults to an all-False ``unknown_mask``. A caller must not be able
        to declare a clean catchment while the *resolved* mask says a neighbour is
        missing: the gate unions the declaration with ``derived_unknown_mask``, so the
        refusal stands even when nothing is declared.
        """
        from terrain_pipeline.surface_rivers.natural_outlet_status import (
            derived_unknown_mask)
        valid = np.ones((ROWS, COLUMNS), bool)
        valid[ROW, 6] = False                    # cut one cell of the catchment
        payload = graph(valid=valid)
        payload["receiver"][ROW, 5] = cell(ROW, 7)      # the chain now skips the hole
        payload["receiver"][ROW, 6] = -1
        payload["terminal_kind"][ROW, 6] = "inactive"
        derived = derived_unknown_mask(valid)
        self.assertTrue(derived[ROW, 5], "a cell beside the cut must be derived unknown")
        self.assertTrue(derived[ROW, 7])
        report = certify(graph=payload, masks=masks())      # nothing is declared
        self.assertEqual(report["assigned_state"], CANDIDATE_STATE)
        self.assertFalse(report["gates"]["no_unknown_pollution"])

    def test_the_derived_unknown_mask_matches_a_full_window(self):
        from terrain_pipeline.surface_rivers.natural_outlet_status import (
            derived_unknown_mask)
        derived = derived_unknown_mask(np.ones((ROWS, COLUMNS), bool))
        # Only the window ring loses neighbours when everything is resolved.
        self.assertTrue(np.array_equal(derived, window_ring()))

    def test_an_unknown_cell_in_another_catchment_is_irrelevant(self):
        unknown = np.zeros((ROWS, COLUMNS), bool)
        unknown[ROW + 2, 1] = True          # drains west, not into the certified mouth
        self.assertEqual(certify(masks=masks(unknown=unknown))["assigned_state"],
                         NATURAL_OUTLET)

    def test_an_unresolved_cell_inside_the_catchment_refuses_the_mouth(self):
        """The same refusal arises from a window cut, not only from a declared mask.

        With ``(ROW, 5)`` unresolved the chain is rerouted and the mouth loses part of
        its catchment, so a claim that still points the path through that cell is
        refused: a finite window's cut is indistinguishable from a broken evidence set
        until the consumer says so.
        """
        valid = np.ones((ROWS, COLUMNS), bool)
        valid[ROW, 4] = False           # the crest cell, i.e. the head of the chain
        payload = graph(valid=valid)
        payload["receiver"][ROW, 4] = -1
        payload["terminal_kind"][ROW, 4] = "inactive"
        unknown = np.zeros((ROWS, COLUMNS), bool)
        unknown[ROW, 5] = True          # it lost its upstream neighbour
        self.assert_refused(certify(graph=payload, masks=masks(unknown=unknown)),
                            "unknown_pollution_in_upstream_catchment")


class SourcePinRejections(unittest.TestCase):

    def assert_refused(self, report, reason, gate="world_coordinate_source_pin"):
        validate_report(report)
        self.assertEqual(report["assigned_state"], CANDIDATE_STATE)
        self.assertFalse(report["gates"][gate])
        self.assertIn(reason, report["failure_reasons"])

    def test_an_unpinned_source_is_refused(self):
        self.assert_refused(certify(source_pin=source_pin(pinned=False)),
                            "missing_world_coordinate_source_pin")

    def test_a_malformed_or_empty_page_hash_is_refused(self):
        self.assert_refused(certify(source_pin=source_pin(pages=("abc",))),
                            "missing_world_coordinate_source_pin")
        self.assert_refused(certify(source_pin=source_pin(pages=())),
                            "missing_world_coordinate_source_pin")

    def test_a_chosen_world_seed_is_refused(self):
        self.assert_refused(certify(source_pin=source_pin(world_seed=20261021)),
                            "world_coordinate_source_pin_mismatch")

    def test_a_non_native_spacing_is_refused(self):
        self.assert_refused(certify(source_pin=source_pin(spacing_m=10.0)),
                            "world_coordinate_source_pin_mismatch")

    def test_an_inferred_outlet_coordinate_is_refused(self):
        self.assert_refused(certify(source_pin=source_pin(outlet=[30180.0, 60061.0])),
                            "world_coordinate_mismatch")

    def test_a_float_native_origin_is_not_a_pin(self):
        self.assert_refused(certify(source_pin=source_pin(origin=(1000.5, 2000))),
                            "missing_world_coordinate_source_pin")


class WaterQuantityRejections(unittest.TestCase):

    def assert_refused(self, report, reason, gate="water_quantity_evidence"):
        validate_report(report)
        self.assertEqual(report["assigned_state"], CANDIDATE_STATE)
        self.assertFalse(report["gates"][gate])
        self.assertIn(reason, report["failure_reasons"])

    def test_a_dry_mouth_is_not_an_outlet(self):
        self.assert_refused(certify(water_quantity=water_quantity(q_m3_s=0.0)),
                            "zero_or_negative_discharge")

    def test_a_negative_discharge_is_refused(self):
        self.assert_refused(certify(water_quantity=water_quantity(q_m3_s=-1.0)),
                            "zero_or_negative_discharge")

    def test_a_non_finite_discharge_is_refused(self):
        self.assert_refused(certify(water_quantity=water_quantity(q_m3_s=float("nan"))),
                            "missing_water_quantity_evidence")

    def test_unstated_provenance_is_refused(self):
        self.assert_refused(certify(water_quantity=water_quantity(provenance="")),
                            "discharge_provenance_unstated")

    def test_a_non_independent_discharge_is_refused(self):
        self.assert_refused(certify(water_quantity=water_quantity(independent=False)),
                            "discharge_not_independently_observed")


class WaterLevelRejections(unittest.TestCase):

    def assert_refused(self, report, reason):
        validate_report(report)
        self.assertEqual(report["assigned_state"], CANDIDATE_STATE)
        self.assertFalse(report["gates"]["water_level_evidence"])
        self.assertIn(reason, report["failure_reasons"])

    def test_an_unstated_datum_is_refused(self):
        self.assert_refused(certify(water_level=water_level(datum="")),
                            "missing_water_level_evidence")

    def test_a_non_finite_sea_level_is_refused(self):
        self.assert_refused(certify(water_level=water_level(sea_level_m=float("inf"))),
                            "missing_water_level_evidence")

    def test_a_negative_uncertainty_is_refused(self):
        self.assert_refused(certify(water_level=water_level(uncertainty_m=-0.1)),
                            "missing_water_level_evidence")

    def test_an_outlet_above_the_declared_sea_level_is_refused(self):
        """The real-TD shape: an entire window far above any sea."""
        self.assert_refused(
            certify(water_level=water_level(sea_level_m=0.0, water_surface_m=300.0,
                                            outlet_bed_m=300.0)),
            "outlet_bed_above_declared_sea_level")

    def test_a_water_surface_above_sea_level_is_refused(self):
        self.assert_refused(
            certify(water_level=water_level(sea_level_m=0.0, water_surface_m=2.0,
                                            outlet_bed_m=0.0)),
            "water_surface_above_declared_sea_level")

    def test_a_water_surface_below_the_bed_is_refused(self):
        self.assert_refused(
            certify(water_level=water_level(sea_level_m=0.0, water_surface_m=-2.0,
                                            outlet_bed_m=0.0)),
            "water_surface_below_outlet_bed")

    def test_the_declared_uncertainty_is_honoured_not_hidden(self):
        # 0.5 m above a 0 m sea: refused at 0.05 m uncertainty, admitted at 1 m.
        above = water_level(sea_level_m=0.0, water_surface_m=0.5, outlet_bed_m=0.4,
                            uncertainty_m=0.05)
        self.assertEqual(certify(water_level=above)["assigned_state"], CANDIDATE_STATE)
        generous = water_level(sea_level_m=0.0, water_surface_m=0.5, outlet_bed_m=0.4,
                               uncertainty_m=1.0)
        self.assertEqual(certify(water_level=generous)["assigned_state"],
                         NATURAL_OUTLET)


# --------------------------------------------------------------------------- #
# 4. no label is ever promoted, even with a perfect evidence set
# --------------------------------------------------------------------------- #
class NoUpgradeTests(unittest.TestCase):
    """The upgrade this repository has forbidden, tested at its strongest point."""

    def test_a_retained_terminal_with_perfect_evidence_stays_retained(self):
        report = certify(candidate=claim(declared=RETAINED),
                         graph=graph(terminal_label=RETAINED))
        validate_report(report)
        self.assertEqual(report["graph_terminal_kind"], RETAINED)
        self.assertEqual(report["assigned_state"], RETAINED)
        self.assertFalse(report["natural_outlet_verified"])
        # Every gate that is about *evidence* passes; the graph label is what stops
        # the certificate, which is exactly the forbidden upgrade.
        self.assertFalse(report["gates"]["not_artificial_boundary"])
        self.assertTrue(all(value for name, value in report["gates"].items()
                            if name != "not_artificial_boundary"))
        self.assertIn("declared_retained_is_not_a_natural_outlet",
                      report["failure_reasons"])
        self.assertIn("graph_label_is_not_an_open_outflow", report["failure_reasons"])

    def test_an_open_outflow_declared_as_its_own_state_is_not_certified(self):
        report = certify(candidate=claim(declared=OPEN_OUTFLOW))
        self.assertEqual(report["assigned_state"], OPEN_OUTFLOW)
        self.assertFalse(report["natural_outlet_verified"])
        self.assertIn("declared_open_outflow_is_not_a_natural_outlet",
                      report["failure_reasons"])

    def test_a_truncated_not_judged_feature_blocks_certification(self):
        report = certify(candidate=claim(declared=TRUNCATED_NOT_JUDGED))
        self.assertEqual(report["assigned_state"], TRUNCATED_NOT_JUDGED)
        self.assertIn("declared_truncated_not_judged_blocks_certification",
                      report["failure_reasons"])

    def test_a_lake_terminal_is_not_an_outlet(self):
        report = certify(candidate=claim(declared=LAKE))
        self.assertEqual(report["assigned_state"], LAKE)
        self.assertIn("declared_lake_is_not_a_natural_outlet", report["failure_reasons"])

    def test_an_artificial_window_boundary_is_not_an_outlet(self):
        report = certify(candidate=claim(declared=ARTIFICIAL_WINDOW_BOUNDARY))
        self.assertEqual(report["assigned_state"], ARTIFICIAL_WINDOW_BOUNDARY)
        self.assertIn("declared_artificial_window_boundary_is_not_a_natural_outlet",
                      report["failure_reasons"])

    def test_a_failed_claim_never_lands_on_a_legitimate_state(self):
        report = certify(water_quantity=water_quantity(q_m3_s=0.0))
        self.assertEqual(report["assigned_state"], CANDIDATE_STATE)
        self.assertNotIn(report["assigned_state"], REQUIRED_STATES)

    def test_the_only_certifiable_label_is_open_outflow(self):
        for label, state in (("retained", RETAINED), ("open_outflow", OPEN_OUTFLOW),
                             ("unknown_boundary", UNKNOWN_BOUNDARY)):
            with self.subTest(label=label):
                self.assertEqual(state_of_terminal_kind(label), state)
                as_claim = certify(graph=graph(terminal_label=label))
                if label == OPEN_OUTFLOW:
                    self.assertEqual(as_claim["assigned_state"], NATURAL_OUTLET)
                else:
                    self.assertEqual(as_claim["assigned_state"], CANDIDATE_STATE)
                    self.assertIn("graph_label_is_not_an_open_outflow",
                                  as_claim["failure_reasons"])
                as_own_state = certify(graph=graph(terminal_label=label),
                                       candidate=claim(declared=state))
                self.assertEqual(as_own_state["assigned_state"], state)
                self.assertFalse(as_own_state["natural_outlet_verified"])

    def test_an_open_outflow_certification_needs_every_gate_not_just_the_label(self):
        report = certify(graph=graph(terminal_label=OPEN_OUTFLOW),
                         water_level=water_level(sea_level_m=0.0, water_surface_m=300.0,
                                                 outlet_bed_m=300.0))
        self.assertEqual(report["assigned_state"], CANDIDATE_STATE)
        self.assertFalse(report["natural_outlet_verified"])


# --------------------------------------------------------------------------- #
# 5. hostile inputs: refused at the boundary, never quietly coerced
# --------------------------------------------------------------------------- #
class HostileInputTests(unittest.TestCase):

    def test_a_boolean_terminal_index_is_refused(self):
        with self.assertRaises(ValueError):
            certify(candidate={"terminal_cell_id": True,
                               "declared_state": NATURAL_OUTLET})

    def test_an_unknown_declared_state_is_refused(self):
        with self.assertRaises(ValueError):
            certify(candidate={"terminal_cell_id": cell(),
                               "declared_state": "river"})

    def test_extra_or_missing_evidence_keys_are_refused(self):
        bad = dict(source_pin())
        bad["extra"] = 1
        with self.assertRaises(ValueError):
            certify(source_pin=bad)
        missing = dict(water_level())
        missing.pop("datum")
        with self.assertRaises(ValueError):
            certify(water_level=missing)

    def test_a_non_downhill_receiver_graph_is_refused(self):
        payload = graph()
        payload["receiver"] = np.full((ROWS, COLUMNS), -1, np.int64)
        payload["receiver"][ROW, 5] = cell(ROW, 6)
        payload["receiver"][ROW, 6] = cell(ROW, 5)          # a two-cell cycle
        payload["terminal_kind"] = np.where(payload["receiver"] >= 0, "interior",
                                            OPEN_OUTFLOW)
        with self.assertRaises(ValueError):
            certify(graph=payload)

    def test_a_mislabelled_graph_is_refused(self):
        payload = graph()
        payload["terminal_kind"][ROW, 5] = RETAINED          # it has a receiver
        with self.assertRaises(ValueError):
            certify(graph=payload)

    def test_mask_shape_and_dtype_are_enforced(self):
        bad = masks()
        bad["unknown_mask"] = np.zeros((ROWS, COLUMNS), np.int8)
        with self.assertRaises(ValueError):
            certify(masks=bad)

    def test_the_terminal_must_be_a_resolved_cell(self):
        valid = np.ones((ROWS, COLUMNS), bool)
        valid[ROW, TERMINAL_COLUMN] = False
        with self.assertRaises(ValueError):
            certify(graph=graph(valid=valid))

    def test_a_missing_evidence_block_is_not_defaulted(self):
        for name in ("candidate", "graph", "downstream", "masks", "source_pin",
                     "water_quantity", "water_level"):
            with self.subTest(missing=name):
                arguments = {"candidate": claim(), "graph": graph(),
                             "downstream": downstream(), "masks": masks(),
                             "source_pin": source_pin(),
                             "water_quantity": water_quantity(),
                             "water_level": water_level()}
                arguments.pop(name)
                with self.assertRaises(TypeError):
                    certify_natural_outlet(**arguments)


if __name__ == "__main__":
    unittest.main()
