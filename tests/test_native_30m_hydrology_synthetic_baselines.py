"""Executable synthetic baselines and refusal counter-examples for the
native-30 m lake / depression / natural-outlet / runoff certification (p1.2).

What this file is, and is not
------------------------------
This file is a **baseline contract**, not a solver. It states, in executable
form, what a native-30 m hydrology certification must be able to show, and it
records the exact answer the repository's **existing** pure functions give today.
Every fixture is analytic: its expected value is closed-form arithmetic or an
*independent* traversal written here (see ``_downstream_cone`` and
``_supplied_mask``), never a second call to the module under test.

It adds **no** production physics. All hydrology comes from existing modules:

* ``metric_depression_gate`` -- the 30 m micro-depression spill gate (pure
  ``judge_depression`` plus the measured ``gate_report`` ledger);
* ``metric_natural_lakes`` -- original-bed D4 lake basins with a bounded reduced
  level-pool / signed-weir replay (``build_natural_lakes`` / ``solve_natural_lakes``);
* ``native_30m_source`` -- strict-downhill D8 joint topology (``build_strict_topology``),
  and ``metric_network_accumulation`` (``accumulate_network_discharge``) for the
  finite-graph terminal ledger;
* ``natural_outlet_certification`` -- the conservative raster natural-outlet evidence
  gate (``certify_natural_outlets``);
* ``native_30m_runoff`` + ``rainfall_runoff`` -- the declared catchment event and the
  soil bucket;
* ``metric_cross_region`` -- window assembly and point resolution with reason codes.

State vocabulary
----------------
No single module emits the full set. The seven states this task must distinguish are
spread across **five** vocabularies, and this file pins the mapping *and* the holes
rather than pretending they are one enum:

===================== =================================================================
state                 emitted by
===================== =================================================================
lake                  ``metric_depression_gate.VERDICT_LAKE`` only
truncated_not_judged  ``metric_depression_gate.DepressionVerdict`` only
retained              30 m topology / accumulation graphs
unknown_boundary      30 m topology / accumulation graphs
open_outflow          accumulation graphs only (the 30 m topology never emits it)
natural_outlet        ``natural_outlet_certification`` booleans only (no 30 m chain)
natural lake/weir      ``metric_natural_lakes`` boundary kinds (a fourth vocabulary)
===================== =================================================================

``StateVocabularyTests`` asserts that split explicitly, because the honest statement
is "these states exist in five places and are not yet one vocabulary", not "the chain
is certified".

Boundaries (declared, not discovered)
-------------------------------------
* No test starts a 48 km run, the GPU, or any heavy computation: every fixture is a
  field of tens to a few thousand cells.
* No production module, frozen pin, old release, ``verification/`` record, Java file,
  plan/TODO/roadmap or catalog file is touched by this work.
* Where an existing function's semantics do not satisfy the required state, the test
  records the gap with an explicit assertion and a comment; it never relaxes an
  assertion to make a gap disappear.
"""
import math
import unittest
from collections import deque

import numpy as np

from terrain_pipeline.natural_outlet_certification import (
    certify_natural_outlets, validate_certification)
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_cross_region import (
    BORDER_BAND_CELLS, REASON_CLOSED_BASIN, REASON_DISAGREEMENT, REASON_OCEAN,
    REASON_OUT_OF_TILE, REASON_UNRESOLVED_BORDER, assemble_pages, resolve_point)
from terrain_pipeline.surface_rivers.metric_depression_gate import (
    INFLOW_FILLED_CATCHMENT, INFLOW_UNFILLED_CATCHMENT, REASON_AREA,
    REASON_CAPACITY, REASON_LAKE, REASON_NO_COMPONENT, REASON_STILL_GROWING,
    REASON_TRUNCATED, VERDICT_LAKE, VERDICT_PASS_THROUGH, DepressionGateConfig,
    gate_report, judge_depression, window_runoff_depth_m)
from terrain_pipeline.drainage import accumulate_network_discharge as accumulate_network_discharge
from terrain_pipeline.lake import BOUNDARY_KINDS as BOUNDARY_KINDS
from terrain_pipeline.lake import NaturalLakeConfig as NaturalLakeConfig
from terrain_pipeline.lake import build_natural_lakes as build_natural_lakes
from terrain_pipeline.lake import lake_stage_at_volume as lake_stage_at_volume
from terrain_pipeline.lake import lake_volume_at_stage as lake_volume_at_stage
from terrain_pipeline.lake import solve_natural_lakes as solve_natural_lakes
from terrain_pipeline.lake import validate_natural_lakes as validate_natural_lakes
from terrain_pipeline.runoff import run_catchment_event as run_catchment_event
from terrain_pipeline.surface_rivers.native_30m_source import (
    _EMITTABLE_TERMINALS, build_strict_topology)


SPACING_M = 30.0
CELL_AREA_M2 = SPACING_M * SPACING_M
WORLD_SEED = 20261020          # CONTRIBUTING.md:35, the fixed continuous baseline
SOURCE_SHA = "a" * 64          # 64 lower-case hex placeholder identity for fixtures


# --------------------------------------------------------------------------- #
# independent helpers: no expected value here comes from the module under test
# --------------------------------------------------------------------------- #
def _downstream_cone(receiver, seeds):
    """Independent BFS: every downstream cell receiving unknown contributions.

    A deliberately separate traversal from ``accumulate_network_discharge``: the
    module walks canonical wave order, this follows individual receivers. If the two disagree
    about *direction* the test fails, which is exactly what this check is for.
    """
    flat = np.asarray(receiver).ravel()
    reached = np.zeros(flat.size, bool)
    pending = deque(int(cell) for cell in np.flatnonzero(np.asarray(seeds).ravel()))
    for cell in pending:
        reached[cell] = True
    while pending:
        cell = pending.popleft()
        target = int(flat[cell])
        if target >= 0 and not reached[target]:
            reached[target] = True
            pending.append(target)
    return reached.reshape(np.asarray(receiver).shape)


def _supplied_mask(pages, origin, shape, band=BORDER_BAND_CELLS):
    """Independent clearance rule: supplied iff some page clears ``band`` cells.

    Distances are to the cell's own **page** border, in that page's local indices
    (``row - oz``, ``column - ox``) -- conflating them with the window indices is a
    mistake this fixture made on its first draft and the check caught.
    """
    rows, columns = shape
    supplied = np.zeros((rows, columns), bool)
    for _, page, native_origin in pages:
        array = np.asarray(page, np.float64)
        ox, oz = (int(value) for value in native_origin)
        for row in range(rows):
            for column in range(columns):
                local_row, local_column = row - oz, column - ox
                if not (0 <= local_row < array.shape[0]
                        and 0 <= local_column < array.shape[1]):
                    continue
                distance = min(local_row, local_column,
                               array.shape[0] - 1 - local_row,
                               array.shape[1] - 1 - local_column)
                if distance >= band:
                    supplied[row, column] = True
    return supplied


def _two_basin_terrain(*, plateau_m=10.0, low_mouth_m=2.5, high_mouth_m=3.0):
    """Two adjacent original-bed basins on a plateau, each with a declared mouth.

    Layout (5 rows x 9 columns; row 2 carries the beds):
      columns 1,2  -> basin 0 (beds 0 m, 1 m); seeds / owner cells 19,20
      columns 3,4,5 -> basin 1 (beds 0 m, 1 m, 1 m); owner cells 21,22,23
      the D4 pair (20, 21) is the single internal saddle, crest max(1, 1) = 1 m
      column 5 borders two exterior cells below the plateau: a high mouth and a
      low mouth, so their crests are ``max(1, high_mouth)`` and ``max(1, low_mouth)``.

    Cell area is 900 m2 (30 m native spacing), so every storage number is exact:
    ``V(stage) = 900 * sum(max(stage - bed, 0))``.
    """
    height = np.full((5, 9), float(plateau_m))
    height[2, 1], height[2, 2] = 0.0, 1.0
    height[2, 3], height[2, 4], height[2, 5] = 0.0, 1.0, 1.0
    height[3, 5] = float(high_mouth_m)
    height[1, 5] = float(low_mouth_m)
    terrain = TerrainGrid(height, np.ones_like(height, bool), 0.0, 0.0,
                          SPACING_M, SPACING_M, "observed_dem",
                          "synthetic two-basin fixture", SOURCE_SHA)
    owner = np.full(height.shape, -1, np.int64)
    owner[2, 1:3] = 0
    owner[2, 3:6] = 1
    seeds = np.array([19, 21], np.int64)                       # beds at 0 m
    high_face = np.array([2 * 9 + 5, 3 * 9 + 5], np.int64)     # crest 3.0 m
    low_face = np.array([2 * 9 + 5, 1 * 9 + 5], np.int64)      # crest 2.5 m
    return (terrain, owner, seeds,
            high_face.reshape(1, 2), low_face.reshape(1, 2))


def _build_mouths(terrain, owner, seeds, faces, kinds, *, max_stage_m=8.0,
                  coefficient=1e3):
    """Declare a subset of exterior faces as mouths; the rest stay unresolved."""
    return build_natural_lakes(
        terrain, seeds, owner, max_stage_m=np.full(len(seeds), max_stage_m),
        boundary_faces=np.asarray(faces, np.int64).reshape(-1, 2),
        boundary_kinds=(np.array(list(kinds), dtype="U16") if len(kinds)
                        else np.empty(0, dtype="U16")),
        weir_coefficient_m3_s_m15=coefficient,
        source_provenance="analytic original bed",
        boundary_provenance="declared mouth kinds: " + ",".join(kinds))


def _two_basin_case():
    """The two-basin terrain with both exterior mouths declared, one per kind."""
    terrain, owner, seeds, high, low = _two_basin_terrain()
    return terrain, owner, seeds, high, low


# --------------------------------------------------------------------------- #
# S0. the seven required states live in five different vocabularies
# --------------------------------------------------------------------------- #
class StateVocabularyTests(unittest.TestCase):

    def test_the_required_states_are_not_one_enum(self):
        from terrain_pipeline.surface_rivers import metric_depression_gate as gate
        # The gate has two verdicts; truncation is a separate flag, not a verdict.
        self.assertEqual((gate.VERDICT_LAKE, gate.VERDICT_PASS_THROUGH),
                         ("lake", "pass_through"))
        self.assertIn(REASON_TRUNCATED, gate.REASON_CODES)
        self.assertNotIn(REASON_TRUNCATED, (gate.VERDICT_LAKE, gate.VERDICT_PASS_THROUGH))
        # The 30 m topology vocabulary has no 'lake', no 'open_outflow'.
        self.assertIn("retained", _EMITTABLE_TERMINALS)
        self.assertIn("unknown_boundary", _EMITTABLE_TERMINALS)
        self.assertNotIn("open_outflow", _EMITTABLE_TERMINALS)
        self.assertNotIn("lake", _EMITTABLE_TERMINALS)
        # The accumulation vocabulary *does* have open_outflow, and no 'lake'.
        kinds = np.full((2, 2), "interior", dtype="U24")
        kinds[0, 1] = "open_outflow"
        with self.assertRaises(ValueError):
            accumulate_network_discharge(
                np.array([[1, -1], [-1, -1]], np.int64), np.ones((2, 2)),
                np.ones((2, 2), bool), terminal_kind=kinds)
        # The natural-lake weir vocabulary is a fourth, distinct four words.
        self.assertEqual(BOUNDARY_KINDS,
                         ("free_outflow", "tailwater", "closed", "unknown"))
        self.assertNotIn("lake", BOUNDARY_KINDS)
        # The cross-region reason vocabulary is a fifth, disjoint set.
        self.assertEqual({REASON_OUT_OF_TILE, REASON_UNRESOLVED_BORDER,
                          REASON_DISAGREEMENT, REASON_OCEAN, REASON_CLOSED_BASIN},
                         {"out_of_tile", "unresolved_border",
                          "overlapping_disagreement", "ocean", "closed_basin"})

    def test_a_gate_lake_cannot_be_expressed_as_a_30m_terminal_label(self):
        """Integration gap, pinned.

        ``metric_depression_gate`` may return ``verdict == 'lake'``, but
        ``accumulate_network_discharge`` accepts only ``retained`` /
        ``open_outflow`` / ``unknown_boundary`` at a terminal. A gate-certified lake
        endpoint must therefore be *translated* by an integration layer that does not
        exist yet; this asserts the hole instead of inventing the mapping.
        """
        verdict = judge_depression(basin_cells=25, capacity_m3=1.0e6, inflow_m3=1.0e3,
                                  area_m2=25 * CELL_AREA_M2, spill_level_m=100.0,
                                  rim_clearance_cells=10, growth_converged=True,
                                  bed_min_m=80.0)
        self.assertEqual(verdict.verdict, VERDICT_LAKE)
        self.assertNotIn(verdict.verdict, _EMITTABLE_TERMINALS)

    def test_natural_outlet_is_a_boolean_report_not_a_graph_label(self):
        report = certify_natural_outlets(
            np.array([[5.0, 4.0, 3.0, 0.0], [6.0, 5.0, 4.0, 1.0]]),
            np.ones((2, 4), bool),
            np.array([[1, 2, 3, -1], [5, 6, 7, -1]], np.int64),
            np.array([[False, False, False, True],
                      [False, False, False, False]]), 0.0,
            [{"terminal_cell_id": 3, "coastline_cell_id": 3,
              "path_cell_ids": [3], "independent_observation": True}])
        validate_certification(report)
        self.assertTrue(report["natural_outlet_verified"])
        self.assertNotIn("natural_outlet", _EMITTABLE_TERMINALS)
        event = _run_simple_event()
        self.assertFalse(event["capabilities"]["natural_outlet_certified"])


# --------------------------------------------------------------------------- #
# S1. closed-basin storage: capacity and area are closed-form
# --------------------------------------------------------------------------- #
class ClosedBasinStorageTests(unittest.TestCase):

    def test_natural_lake_storage_is_the_original_bed_prism_sum(self):
        terrain, owner, seeds, high, low = _two_basin_case()
        domain = _build_mouths(terrain, owner, seeds, np.empty((0, 2)), [])
        beds = [[0.0, 1.0], [0.0, 1.0, 1.0]]
        for lake, lake_beds in enumerate(beds):
            for stage in (0.5, 1.0, 2.0, 4.0, 8.0):
                expected = CELL_AREA_M2 * sum(max(stage - bed, 0.0)
                                              for bed in lake_beds)
                with self.subTest(lake=lake, stage=stage):
                    self.assertAlmostEqual(
                        lake_volume_at_stage(domain, lake, stage), expected, places=6)
            capacity = CELL_AREA_M2 * sum(max(8.0 - bed, 0.0) for bed in lake_beds)
            self.assertAlmostEqual(lake_stage_at_volume(domain, lake, capacity), 8.0,
                                   places=6)

    def test_the_gate_calls_a_closed_basin_a_lake_and_a_full_one_a_pass_through(self):
        common = dict(basin_cells=100, area_m2=100 * CELL_AREA_M2,
                      spill_level_m=100.0, rim_clearance_cells=10,
                      growth_converged=True, bed_min_m=80.0)
        kept = judge_depression(capacity_m3=1.0e6, inflow_m3=1.0e3, **common)
        drained = judge_depression(capacity_m3=1.0e3, inflow_m3=1.0e6, **common)
        self.assertEqual((kept.verdict, kept.reason_code), (VERDICT_LAKE, REASON_LAKE))
        self.assertEqual((drained.verdict, drained.reason_code),
                         (VERDICT_PASS_THROUGH, REASON_CAPACITY))
        self.assertEqual(kept.ratio, 1000.0)           # capacity / inflow, exact
        self.assertAlmostEqual(kept.relief_m, 20.0)    # spill level - bed minimum
        self.assertTrue(kept.is_domain_terminal)
        self.assertTrue(kept.closed_basin_by_hypsometry)
        self.assertFalse(kept.truncated_not_judged)

    def test_the_area_threshold_and_the_growth_criterion_each_refuse(self):
        common = dict(capacity_m3=1.0e9, inflow_m3=1.0, spill_level_m=100.0,
                      rim_clearance_cells=10, bed_min_m=80.0)
        small = judge_depression(basin_cells=5, area_m2=5 * CELL_AREA_M2, **common)
        growing = judge_depression(basin_cells=100, area_m2=100 * CELL_AREA_M2,
                                   growth_converged=False, **common)
        self.assertEqual(small.reason_code, REASON_AREA)
        self.assertEqual(growing.reason_code, REASON_STILL_GROWING)
        absent = judge_depression(basin_cells=0, area_m2=0.0, capacity_m3=0.0,
                                  inflow_m3=1.0, spill_level_m=100.0,
                                  bed_min_m=100.0, component_absent=True)
        self.assertEqual(absent.reason_code, REASON_NO_COMPONENT)

    def test_gate_report_storage_is_exact_box_arithmetic(self):
        """A square pit on a plateau: spill level and capacity are known exactly.

        Pit 4x4 cells, 50 m deep, plateau 200 m, spacing 30 m =>
        capacity = 16 * 50 * 900 = 720 000 m3; spill level 200 m; bed 150 m.
        """
        field = np.full((41, 41), 200.0)
        field[20:24, 20:24] = 150.0
        report = gate_report(field, spacing_m=SPACING_M, produced_depth_m=0.001)
        self.assertEqual(len(report.verdicts), 1)
        record = report.verdicts[0]
        self.assertAlmostEqual(record.capacity_m3, 16 * 50 * CELL_AREA_M2, places=6)
        self.assertAlmostEqual(record.spill_level_m, 200.0, places=9)
        self.assertAlmostEqual(record.bed_min_m, 150.0, places=9)
        self.assertAlmostEqual(record.area_m2, 16 * CELL_AREA_M2, places=6)
        self.assertEqual(record.reason_code, REASON_LAKE)


# --------------------------------------------------------------------------- #
# S2. an explicit saddle overflows, and the overflow is conserved
# --------------------------------------------------------------------------- #
class SaddleOverflowTests(unittest.TestCase):

    def test_the_internal_saddle_crest_is_the_maximum_of_its_two_face_beds(self):
        terrain, owner, seeds, high, low = _two_basin_case()
        domain = _build_mouths(terrain, owner, seeds, np.empty((0, 2)), [])
        arrays = domain["arrays"]
        # The only interior face is the (20, 21) D4 pair, crest max(bed 1, bed 0) = 1 m.
        self.assertEqual(arrays["internal_faces"].tolist(), [[20, 21]])
        self.assertEqual(arrays["internal_crest_m"].tolist(), [1.0])
        self.assertGreater(domain["metadata"]["unresolved_exterior_faces"], 0)
        self.assertFalse(domain["metadata"]["natural_boundary_certified"])

    def test_overflow_crosses_the_saddle_and_total_stock_is_conserved(self):
        terrain, owner, seeds, high, low = _two_basin_case()
        closed = _build_mouths(terrain, owner, seeds, np.empty((0, 2)), [])
        trace = solve_natural_lakes(
            closed, np.array([0.0, 200.0]), np.array([[0.0, 0.0]]),
            np.array([2000.0, 0.0]), np.zeros((1, 0)),
            config=NaturalLakeConfig(max_step_seconds=1.0),
            forcing_provenance="declared initial stock in basin 0")
        self.assertEqual(trace["metadata"]["status"], "complete")
        self.assertTrue(validate_natural_lakes(trace))
        arrays = trace["arrays"]
        volume = arrays["volume_m3"]
        # No declared mouth => no boundary column at all, so nothing can leave.
        self.assertEqual(arrays["boundary_transfer_m3"].shape[1], 0)
        self.assertAlmostEqual(float(volume[0].sum()), 2000.0, places=6)
        self.assertAlmostEqual(float(volume[-1].sum()), 2000.0, places=6)
        # The saddle moved water: basin 1 gains exactly what leaves basin 0.
        self.assertGreater(float(volume[-1, 1]), 0.0)
        self.assertAlmostEqual(float(arrays["internal_transfer_m3"].max()),
                               float(volume[-1, 1]), places=6)
        # With no open boundary the two stages settle on one common level, above
        # the 1 m saddle crest and below the 10 m plateau rim. They approach it
        # without ever equalling it: the module declares
        # ``transient_connected_not_common_stage``, so the equalisation is a
        # transient, not an instantaneous projection.
        self.assertGreater(float(arrays["stage_m"][-1, 1]), 1.0)
        self.assertLess(float(arrays["stage_m"][-1, 1]), 10.0)
        self.assertLess(abs(float(arrays["stage_m"][-1, 0])
                            - float(arrays["stage_m"][-1, 1])), 5e-4)
        self.assertTrue(closed["metadata"]["transient_connected_not_common_stage"])
        self.assertFalse(trace["metadata"]["common_stage_certified"])


# --------------------------------------------------------------------------- #
# S3. recession after the spill: the basin drains down to its own mouth crest
# --------------------------------------------------------------------------- #
class RecessionAfterOverflowTests(unittest.TestCase):

    def setUp(self):
        terrain, owner, seeds, high, low = _two_basin_case()
        # Declare both exterior faces: the high one closed, the low one free.
        self.domain = _build_mouths(terrain, owner, seeds,
                                    np.vstack([high, low]),
                                    ["closed", "free_outflow"])
        self.initial_volume = 19800.0
        self.trace = solve_natural_lakes(
            self.domain, np.array([0.0, 60.0]), np.array([[0.0, 0.0]]),
            np.array([0.0, self.initial_volume]), np.zeros((1, 2)),
            config=NaturalLakeConfig(max_step_seconds=1.0),
            forcing_provenance="declared initial stock above the mouth crest")

    def test_the_two_mouth_crests_are_the_exterior_or_bed_maximum(self):
        crests = self.domain["arrays"]["boundary_crest_m"]
        self.assertEqual(crests.tolist(), [3.0, 2.5])

    def test_a_free_mouth_drains_monotonically_and_stops_at_the_crest(self):
        arrays = self.trace["arrays"]
        volume = arrays["volume_m3"][:, 1]
        stage = arrays["stage_m"][:, 1]
        transfer = arrays["boundary_transfer_m3"][:, 1]
        self.assertEqual(self.trace["metadata"]["status"], "complete")
        # Recession: stage and volume never rise; the outflow never reverses.
        self.assertTrue(np.all(np.diff(volume) <= 1e-9))
        self.assertTrue(np.all(np.diff(stage) <= 1e-12))
        self.assertTrue(np.all(np.diff(transfer) >= -1e-12))
        self.assertGreater(float(transfer[-1]), 0.0)
        # The closed face never passes water; only the free mouth does.
        self.assertEqual(float(np.abs(arrays["boundary_transfer_m3"][:, 0]).max()), 0.0)
        # The floor is the free mouth's own crest (2.5 m), not below it.
        self.assertGreater(float(stage[-1]), 2.5)
        self.assertLess(float(stage[-1]), 2.6)

    def test_the_recorded_transfer_closes_the_volume_exactly(self):
        arrays = self.trace["arrays"]
        total_end = float(arrays["volume_m3"][-1].sum()
                          + arrays["boundary_transfer_m3"][-1].sum())
        self.assertAlmostEqual(total_end, self.initial_volume, places=6)
        self.assertAlmostEqual(float(arrays["volume_m3"][0].sum()),
                               self.initial_volume, places=6)

    def test_an_independent_trapezoid_reproduces_the_recorded_discharge(self):
        """Independent outflow volume from the saved rate series, not the module's
        own integral.

        The trapezoid of the recorded weir rate over the recorded step times must
        agree with the module's cumulated transfer to within 1%. It is *not* exact:
        the saved trace stores step endpoints, not the integrator's internal stages,
        and the crest is a kink (no event fires there), so a small bracket is the
        honest tolerance -- the exact statement is the volume balance above.
        """
        arrays = self.trace["arrays"]
        times = arrays["time_seconds"]
        rate = arrays["boundary_q_m3_s"][:, 1]
        trapezoid = float(np.trapezoid(rate, times))
        recorded = float(arrays["boundary_transfer_m3"][-1, 1])
        self.assertGreater(recorded, 0.0)
        self.assertAlmostEqual(trapezoid, recorded, delta=0.01 * trapezoid)

    def test_a_tailwater_above_the_crest_pushes_water_back_in(self):
        terrain, owner, seeds, high, low = _two_basin_case()
        tail = _build_mouths(terrain, owner, seeds, np.vstack([high, low]),
                             ["closed", "tailwater"])
        trace = solve_natural_lakes(
            tail, np.array([0.0, 30.0]), np.array([[0.0, 0.0]]),
            np.array([0.0, 0.0]), np.array([[0.0, 6.0]]),
            config=NaturalLakeConfig(max_step_seconds=1.0),
            forcing_provenance="declared external stage above the crest")
        transfer = trace["arrays"]["boundary_transfer_m3"][-1, 1]
        # Signed weir: a negative transfer is inflow into the basin.
        self.assertLess(float(transfer), 0.0)
        self.assertGreater(float(trace["arrays"]["volume_m3"][-1, 1]), 0.0)


# --------------------------------------------------------------------------- #
# S4. two mouths, two crests: discharge is a head law, not a selection
# --------------------------------------------------------------------------- #
class DualOutletSelectionTests(unittest.TestCase):

    def setUp(self):
        terrain, owner, seeds, high, low = _two_basin_case()
        self.domain = _build_mouths(terrain, owner, seeds, np.vstack([high, low]),
                                    ["free_outflow", "free_outflow"])

    def test_the_lower_crest_carries_strictly_more_water(self):
        trace = solve_natural_lakes(
            self.domain, np.array([0.0, 60.0]), np.array([[0.0, 0.0]]),
            np.array([0.0, 9900.0]), np.zeros((1, 2)),
            config=NaturalLakeConfig(max_step_seconds=1.0),
            forcing_provenance="declared stock above both mouth crests")
        self.assertEqual(trace["metadata"]["status"], "complete")
        end = trace["arrays"]["boundary_transfer_m3"][-1]
        # The module does not hard-select one outlet: both mouths are open, and the
        # lower crest (face 1, 2.5 m) passes strictly more water than the higher
        # one (face 0, 3.0 m) once the head is above both.
        self.assertGreater(float(end[0]), 0.0)
        self.assertGreater(float(end[1]), 0.0)
        self.assertGreater(float(end[1]), float(end[0]))
        # Conservation across both mouths.
        self.assertAlmostEqual(float(trace["arrays"]["volume_m3"][-1].sum()
                                     + end.sum()), 9900.0, places=6)

    def test_the_basin_settles_a_fraction_of_a_percent_below_the_lower_crest(self):
        """Pinned numerical property: no event fires at the weir crest.

        ``_rates`` already clamps a free outflow at its crest, but the ODE has no
        root event there, and the entire drain lasts under a second at this
        coefficient. So the trace can end a small fraction of a percent *below* the
        lower crest instead of exactly on it. Recorded as a property, not smoothed
        over: the exact statement is the volume balance, which still closes.
        """
        trace = solve_natural_lakes(
            self.domain, np.array([0.0, 300.0]), np.array([[0.0, 0.0]]),
            np.array([0.0, 9900.0]), np.zeros((1, 2)),
            config=NaturalLakeConfig(max_step_seconds=1.0),
            forcing_provenance="declared stock above both mouth crests")
        stage = float(trace["arrays"]["stage_m"][-1, 1])
        self.assertGreater(stage, 2.45)
        self.assertLess(stage, 2.51)
        # Every rate at the last step is zero: the mouths have genuinely shut.
        self.assertEqual(float(np.abs(trace["arrays"]["boundary_q_m3_s"][-1]).max()),
                         0.0)
        # And the two open mouths at the lock-in step are exactly the crest ordering.
        self.assertGreater(float(trace["arrays"]["boundary_transfer_m3"][-1, 1]),
                           float(trace["arrays"]["boundary_transfer_m3"][-1, 0]))

    def test_below_the_lower_crest_no_mouth_flows(self):
        trace = solve_natural_lakes(
            self.domain, np.array([0.0, 10.0]), np.array([[0.0, 0.0]]),
            np.array([0.0, 900.0]), np.zeros((1, 2)),
            config=NaturalLakeConfig(max_step_seconds=0.5),
            forcing_provenance="stock below both crests")
        self.assertLess(float(trace["arrays"]["stage_m"][-1, 1]), 2.5)
        self.assertEqual(float(np.abs(trace["arrays"]["boundary_transfer_m3"]).max()),
                         0.0)


# --------------------------------------------------------------------------- #
# S5. an artificial cut is not an outlet: retained vs unknown_boundary
# --------------------------------------------------------------------------- #
class RetainedAndTruncationTests(unittest.TestCase):

    def test_an_interior_minimum_is_retained_and_every_border_is_unknown(self):
        field = np.full((8, 8), 100.0)
        field[3, 3] = 50.0
        topology = build_strict_topology(field, np.ones(field.shape, bool))
        kinds = topology["terminal_kind"]
        retained = np.argwhere(kinds == "retained").tolist()
        unknown = np.argwhere(kinds == "unknown_boundary").tolist()
        self.assertIn([3, 3], retained)
        self.assertEqual(len(unknown), 28)            # the whole border ring
        self.assertTrue(all(row in (0, 7) or column in (0, 7)
                            for row, column in unknown))
        self.assertFalse(bool((kinds == "open_outflow").any()))
        self.assertEqual(topology["census"]["open_outflow"], 0)

    def test_a_monotone_plane_has_no_interior_terminal(self):
        plane = (100.0 - 0.5 * np.arange(64).reshape(8, 8)
                 - 0.01 * np.arange(8)[None, :])
        topology = build_strict_topology(plane, np.ones(plane.shape, bool))
        self.assertFalse(bool((topology["terminal_kind"] == "retained").any()))
        self.assertEqual(topology["census"]["retained"], 0)

    def test_retained_water_is_a_terminal_balance_not_an_outflow(self):
        field = np.full((8, 8), 100.0)
        field[3, 3] = 50.0
        topology = build_strict_topology(field, np.ones(field.shape, bool))
        ledger = accumulate_network_discharge(
            topology["receiver"], np.where(topology["valid_mask"], 1.0, 0.0),
            topology["valid_mask"], terminal_kind=topology["terminal_kind"],
            upstream_unknown_mask=topology["upstream_unknown_mask"])
        self.assertEqual(ledger["input_total_m3_s"], 64.0)
        self.assertEqual(ledger["open_outflow_m3_s"], 0.0)
        self.assertEqual(ledger["retained_m3_s"], 36.0)
        self.assertEqual(ledger["unknown_pending_m3_s"], 28.0)
        self.assertEqual(ledger["residual_m3_s"], 0.0)

    def test_a_rim_inside_the_untrusted_band_is_reported_not_judged(self):
        field = np.full((41, 41), 200.0)
        field[1:4, 20:23] = 150.0
        report = gate_report(field, spacing_m=SPACING_M, produced_depth_m=0.001)
        record = report.verdicts[0]
        self.assertEqual(record.reason_code, REASON_TRUNCATED)
        self.assertEqual(record.verdict, VERDICT_PASS_THROUGH)
        self.assertTrue(record.truncated_not_judged)
        self.assertTrue(record.closed_basin_by_hypsometry)   # closed on the terrain
        self.assertFalse(record.is_domain_terminal)          # but not kept
        summary = report.summary()
        # The three columns never collapse into two.
        self.assertEqual(summary["closed_basin_by_hypsometry"]["count"], 1)
        self.assertEqual(summary["truncated_not_judged"]["count"], 1)
        self.assertEqual(summary["is_domain_terminal"]["count"], 0)

    def test_a_measured_rim_and_a_cut_rim_stay_in_separate_columns(self):
        field = np.full((41, 41), 200.0)
        field[20:24, 20:24] = 150.0        # clearance 20, well measured
        field[1:4, 30:33] = 150.0          # clearance 1, inside the 6-cell band
        report = gate_report(field, spacing_m=SPACING_M, produced_depth_m=0.001)
        states = sorted((record.basin_cells, record.reason_code)
                        for record in report.verdicts)
        self.assertEqual(states, [(9, REASON_TRUNCATED), (16, REASON_LAKE)])
        summary = report.summary()
        self.assertEqual(summary["closed_basin_by_hypsometry"]["count"], 2)
        self.assertEqual(summary["truncated_not_judged"]["count"], 1)
        self.assertEqual(summary["is_domain_terminal"]["count"], 1)
        self.assertEqual(summary["reason_counts"][REASON_TRUNCATED], 1)
        self.assertEqual(summary["reason_counts"][REASON_LAKE], 1)

    def test_the_report_and_the_row_disagree_about_the_inflow_quantity(self):
        """Pinned inconsistency in an existing module.

        ``gate_report.summary()`` labels its ``inflow_quantity`` as
        ``filled_catchment_arrival`` while ``measure_depressions`` fills each *row*
        with ``unfilled_catchment_production`` (the quantity the module's own
        docstring says criterion (a) needs). This test records the disagreement so a
        consumer cannot silently read the wrong word; it is a documentation gap, not
        a call to change the frozen module.
        """
        field = np.full((41, 41), 200.0)
        field[20:24, 20:24] = 150.0
        report = gate_report(field, spacing_m=SPACING_M, produced_depth_m=0.001)
        self.assertEqual(report.summary()["inflow_quantity"], INFLOW_FILLED_CATCHMENT)
        self.assertEqual(report.verdicts[0].inflow_quantity, INFLOW_UNFILLED_CATCHMENT)
        self.assertNotEqual(report.summary()["inflow_quantity"],
                            report.verdicts[0].inflow_quantity)


# --------------------------------------------------------------------------- #
# S6. unknown upstream propagates downstream, and never becomes outflow
# --------------------------------------------------------------------------- #
class UnknownBoundaryTests(unittest.TestCase):
    def test_reference_cone_propagates_downstream_only(self):
        receiver = np.array([[1, 2, -1, 2]], np.int64)
        seeds = np.array([[False, True, False, False]])
        np.testing.assert_array_equal(_downstream_cone(receiver, seeds),
                                      [[False, True, True, False]])

    def test_the_unknown_cone_equals_an_independent_bfs(self):
        """A tilted plane with one declared unknown cell.

        The module walks canonical wave order; ``_downstream_cone`` walks a donor
        receiver paths. Equality of the two dirty sets is the direction check. In a monotone
        plane every border cell is a seed, so the whole field is dirty -- which is
        the honest answer, not a defect.
        """
        rows = columns = 9
        zs = np.arange(rows, dtype=np.float64)[:, None]
        xs = np.arange(columns, dtype=np.float64)[None, :]
        field = 100.0 - 2.0 * zs - 1.0 * xs
        mask = np.ones((rows, columns), bool)
        mask[4, 4] = False
        with np.errstate(invalid="ignore", over="ignore"):
            topology = build_strict_topology(field, mask)
        ledger = accumulate_network_discharge(
            topology["receiver"], np.where(topology["valid_mask"], 1.0, 0.0),
            topology["valid_mask"], terminal_kind=topology["terminal_kind"],
            upstream_unknown_mask=topology["upstream_unknown_mask"])
        cone = _downstream_cone(topology["receiver"], topology["upstream_unknown_mask"])
        self.assertTrue(np.array_equal(cone & topology["valid_mask"],
                                       ~ledger["complete_mask"] & topology["valid_mask"]))
        dirty = int((~ledger["complete_mask"] & topology["valid_mask"]).sum())
        seeds = int(topology["upstream_unknown_mask"].sum())
        # Strictly downstream of a seed: the propagation is not a no-op.
        self.assertGreater(dirty, seeds)
        self.assertEqual(ledger["input_total_m3_s"], 80.0)
        self.assertEqual(ledger["open_outflow_m3_s"], 0.0)
        self.assertEqual(ledger["retained_m3_s"], 0.0)
        self.assertEqual(ledger["unknown_pending_m3_s"], 80.0)
        self.assertEqual(ledger["residual_m3_s"], 0.0)

    def test_unknown_water_is_never_counted_as_known_outflow(self):
        """The failure mode this task names: folding unknown into the outlet."""
        receiver = np.array([[1, 2, 3, -1], [5, 6, 7, -1]], np.int64)
        local = np.zeros((2, 4), np.float64)
        local[0, 0] = 1.0
        local[1, 0] = 2.0
        valid = np.ones((2, 4), bool)
        seeds = np.zeros((2, 4), bool)
        seeds[0, 0] = True                    # the first donor is undeclared
        open_kind = np.full((2, 4), "interior", dtype="U24")
        open_kind[receiver < 0] = "open_outflow"
        ledger = accumulate_network_discharge(
            receiver, local, valid, terminal_kind=open_kind,
            upstream_unknown_mask=seeds)
        self.assertEqual(ledger["open_outflow_m3_s"], 3.0)
        # Row 0 is downstream of the seed, so it is not "complete"; row 1 is a
        # separate donor and stays complete. The cone is directional.
        self.assertFalse(bool(ledger["complete_mask"][0, 0]))
        self.assertFalse(bool(ledger["complete_mask"][0, 3]))
        self.assertTrue(bool(ledger["complete_mask"][1, 0]))
        self.assertTrue(bool(ledger["complete_mask"][1, 3]))
        # Relabel the same terminals as unknown_boundary: the same water is booked
        # as unknown and open_outflow is exactly zero. The two are never merged.
        unknown_kind = np.full((2, 4), "interior", dtype="U24")
        unknown_kind[receiver < 0] = "unknown_boundary"
        unknown_ledger = accumulate_network_discharge(
            receiver, local, valid, terminal_kind=unknown_kind,
            upstream_unknown_mask=seeds)
        self.assertEqual(unknown_ledger["unknown_pending_m3_s"], 3.0)
        self.assertEqual(unknown_ledger["open_outflow_m3_s"], 0.0)
        self.assertEqual(unknown_ledger["retained_m3_s"], 0.0)

    def test_the_three_terminal_totals_and_the_residual_close_the_balance(self):
        receiver = np.array([[1, 2, 3, -1], [5, 6, 7, -1]], np.int64)
        local = np.array([[1.0, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]])
        valid = np.ones((2, 4), bool)
        kinds = np.full((2, 4), "interior", dtype="U24")
        kinds[0, 3] = "retained"
        kinds[1, 3] = "open_outflow"
        ledger = accumulate_network_discharge(receiver, local, valid,
                                              terminal_kind=kinds)
        # 1+2+3+4 = 10 retained, 5+6+7+8 = 26 open, no unknown, no residual.
        self.assertAlmostEqual(ledger["retained_m3_s"], 10.0, places=9)
        self.assertAlmostEqual(ledger["open_outflow_m3_s"], 26.0, places=9)
        self.assertAlmostEqual(ledger["unknown_pending_m3_s"], 0.0, places=12)
        self.assertAlmostEqual(ledger["residual_m3_s"], 0.0, places=12)
        self.assertAlmostEqual(
            ledger["retained_m3_s"] + ledger["open_outflow_m3_s"]
            + ledger["unknown_pending_m3_s"] + ledger["residual_m3_s"],
            ledger["input_total_m3_s"], places=9)
        self.assertAlmostEqual(ledger["input_total_m3_s"], 36.0, places=9)

    def test_a_hole_in_the_known_field_widens_the_unknown_boundary(self):
        field = np.full((8, 8), 100.0)
        field[3, 3] = 50.0
        mask = np.ones(field.shape, bool)
        mask[3, 2] = False                     # one declared unknown cell
        with np.errstate(invalid="ignore", over="ignore"):
            topology = build_strict_topology(field, mask)
        self.assertEqual(topology["census"]["inactive"], 1)
        self.assertGreater(topology["census"]["unknown_boundary"], 28)
        self.assertFalse(bool(topology["valid_mask"][3, 2]))
        # The unresolved cell's own receiver is never invented.
        self.assertEqual(int(topology["receiver"][3, 2]), -1)


# --------------------------------------------------------------------------- #
# S7. a natural sea/land outlet is evidence, never an inference
# --------------------------------------------------------------------------- #
class NaturalOutletTests(unittest.TestCase):

    def setUp(self):
        self.height = np.array([[5.0, 4.0, 3.0, 0.0], [6.0, 5.0, 4.0, 1.0]])
        self.valid = np.ones((2, 4), bool)
        self.receiver = np.array([[1, 2, 3, -1], [5, 6, 7, -1]], np.int64)
        self.coast = np.array([[False, False, False, True],
                               [False, False, False, False]])

    def test_a_below_datum_receiver_exit_on_the_coast_certifies(self):
        report = certify_natural_outlets(
            self.height, self.valid, self.receiver, self.coast, 0.0,
            [{"terminal_cell_id": 3, "coastline_cell_id": 3,
              "path_cell_ids": [3], "independent_observation": True}])
        validate_certification(report)
        self.assertTrue(report["natural_outlet_verified"])
        self.assertTrue(report["ocean_outlet_certified"])
        self.assertEqual(report["outlets"][0]["reasons"], [])
        self.assertEqual(report["policy"],
                         "explicit_coastline_and_independent_connection_required")

    def test_each_missing_evidence_class_refuses_with_its_own_reason(self):
        cases = {
            "missing_independent_observation": (
                {"terminal_cell_id": 3, "coastline_cell_id": 3,
                 "path_cell_ids": [3], "independent_observation": False},
                self.coast, "missing_independent_observation"),
            "terminal_is_not_receiver_exit": (
                {"terminal_cell_id": 2, "coastline_cell_id": 3,
                 "path_cell_ids": [2, 3], "independent_observation": True},
                self.coast, "terminal_is_not_receiver_exit"),
            "endpoint_not_explicit_coastline": (
                {"terminal_cell_id": 3, "coastline_cell_id": 3,
                 "path_cell_ids": [3], "independent_observation": True},
                np.zeros((2, 4), bool), "endpoint_not_explicit_coastline"),
            "path_endpoints_mismatch": (
                {"terminal_cell_id": 3, "coastline_cell_id": 3,
                 "path_cell_ids": [2, 3], "independent_observation": True},
                self.coast, "path_endpoints_mismatch"),
            "invalid_path": (
                {"terminal_cell_id": 3, "coastline_cell_id": 3,
                 "path_cell_ids": [3, 3], "independent_observation": True},
                self.coast, "invalid_path"),
        }
        for name, (connection, coast, reason) in cases.items():
            with self.subTest(case=name):
                report = certify_natural_outlets(
                    self.height, self.valid, self.receiver, coast, 0.0, [connection])
                self.assertFalse(report["natural_outlet_verified"])
                self.assertIn(reason, report["outlets"][0]["reasons"])

    def test_an_outlet_above_the_datum_is_refused(self):
        report = certify_natural_outlets(
            self.height, self.valid, self.receiver, self.coast, -1.0,
            [{"terminal_cell_id": 3, "coastline_cell_id": 3,
              "path_cell_ids": [3], "independent_observation": True}])
        self.assertFalse(report["natural_outlet_verified"])
        self.assertIn("coast_endpoint_above_declared_sea_level",
                      report["outlets"][0]["reasons"])

    def test_a_protected_cell_on_the_path_is_refused(self):
        protected = np.zeros((2, 4), bool)
        protected[0, 3] = True
        report = certify_natural_outlets(
            self.height, self.valid, self.receiver, self.coast, 0.0,
            [{"terminal_cell_id": 3, "coastline_cell_id": 3,
              "path_cell_ids": [3], "independent_observation": True}],
            protected_mask=protected)
        self.assertFalse(report["natural_outlet_verified"])
        self.assertIn("path_crosses_protected_cell", report["outlets"][0]["reasons"])

    def test_no_connection_and_a_bad_schema_never_certify(self):
        empty = certify_natural_outlets(self.height, self.valid, self.receiver,
                                        self.coast, 0.0, [])
        self.assertFalse(empty["natural_outlet_verified"])
        with self.assertRaises(ValueError):
            certify_natural_outlets(self.height, self.valid, self.receiver,
                                    self.coast, 0.0, [{"terminal_cell_id": 3}])

    def test_the_gate_certifies_only_a_single_cell_exit_today(self):
        """Integration gap, pinned: a multi-cell river-mouth path cannot certify.

        The certifier requires the terminal to be *both* a receiver exit
        (``receiver < 0``) *and* the head of a receiver chain reaching the coastline
        cell. A ``receiver == -1`` cell ends its own chain, so the chain check can
        only pass when the terminal *is* the coastline cell. A genuine multi-cell
        downhill mouth path therefore fails ``receiver_chain_does_not_reach_coast``.
        """
        report = certify_natural_outlets(
            self.height, self.valid,
            np.array([[1, 2, 3, -1], [5, 6, 7, -1]], np.int64),
            np.array([[False, False, False, True],
                      [False, False, False, True]]), 0.0,
            [{"terminal_cell_id": 3, "coastline_cell_id": 7,
              "path_cell_ids": [3, 7], "independent_observation": True}])
        self.assertFalse(report["natural_outlet_verified"])
        self.assertIn("receiver_chain_does_not_reach_coast",
                      report["outlets"][0]["reasons"])


# --------------------------------------------------------------------------- #
# S8. window coverage: an unanswered cell is refused with a reason, not filled
# --------------------------------------------------------------------------- #
class WindowCoverageTests(unittest.TestCase):

    def setUp(self):
        self.page = np.arange(400.0).reshape(20, 20)
        self.other = np.arange(400.0).reshape(20, 20) + 1000.0
        self.pages = [("a", self.page, (0, 0)), ("b", self.other, (10, 0))]
        self.origin = (0, 0)
        self.shape = (20, 26)

    def test_assembly_resolves_exactly_the_independently_supplied_cells(self):
        assembly = assemble_pages(self.pages, origin=self.origin, shape=self.shape)
        expected = _supplied_mask(self.pages, self.origin, self.shape)
        self.assertTrue(np.array_equal(assembly["resolved_mask"], expected))
        self.assertEqual(assembly["resolved_cells"], int(expected.sum()))
        self.assertEqual(assembly["resolved_cells"], 128)
        self.assertEqual(assembly["unresolved_cells"], 392)
        # Unanswered cells carry NaN, never a border value.
        self.assertTrue(np.isnan(assembly["field"][~expected]).all())
        self.assertEqual(assembly["unresolved_reason"], REASON_UNRESOLVED_BORDER)

    def test_assembly_is_order_invariant(self):
        forward = assemble_pages(self.pages, origin=self.origin, shape=self.shape)
        reverse = assemble_pages(list(reversed(self.pages)), origin=self.origin,
                                 shape=self.shape)
        self.assertTrue(np.array_equal(forward["field"][forward["resolved_mask"]],
                                       reverse["field"][reverse["resolved_mask"]]))
        self.assertEqual(forward["selection_key_digest"],
                         reverse["selection_key_digest"])

    def test_point_resolution_reason_codes(self):
        interior = (self.origin[0] + 10, self.origin[1] + 10)
        self.assertEqual(resolve_point(self.pages, interior)["reason"],
                         REASON_CLOSED_BASIN)
        self.assertEqual(resolve_point(self.pages, (0, 0))["reason"],
                         REASON_UNRESOLVED_BORDER)
        self.assertIsNone(resolve_point(self.pages, (0, 0))["value_m"])
        self.assertEqual(resolve_point(self.pages, (400, 400))["reason"],
                         REASON_OUT_OF_TILE)
        self.assertIsNone(resolve_point(self.pages, (400, 400))["value_m"])
        disagreeing = [("a", self.page, (0, 0)), ("b", self.page + 1.0, (0, 0))]
        resolved = resolve_point(disagreeing, interior)
        self.assertEqual(resolved["reason"], REASON_DISAGREEMENT)
        self.assertEqual(resolved["disagreeing_values_m"], [210.0, 211.0])
        # Below a declared datum the same answered cell is an ocean reason.
        below = resolve_point(self.pages, interior, sea_level_m=250.0)
        self.assertTrue(below["resolved"])
        self.assertEqual(below["reason"], REASON_OCEAN)


# --------------------------------------------------------------------------- #
# S9. runoff: zero rain, pulse storm, hostile soil, bad forcing, budget
# --------------------------------------------------------------------------- #
CAPTURE_HEIGHT = np.array([[4.0, 3.0, 2.0, 1.0]])
CAPTURE_RECEIVER = np.array([[1, 2, 3, -1]], np.int64)
CAPTURE_MASK = np.ones((1, 4), bool)


def _run_simple_event(rain=None, *, parameters=None, dt_s=3600.0, mask=None,
                      receiver=None, height=None):
    if rain is None:
        rain = np.array([8.0, 0.0, 0.0])
    if parameters is None:
        parameters = RunoffParameters(infiltration_capacity_mm_h=2.0)
    return run_catchment_event(
        CAPTURE_HEIGHT if height is None else height,
        CAPTURE_RECEIVER if receiver is None else receiver,
        CAPTURE_MASK if mask is None else mask,
        CAPTURE_MASK if mask is None else mask,
        origin_native_xz=(0, 0), source_identity_sha256="0" * 64,
        world_seed=WORLD_SEED, rain_mm_h=np.asarray(rain, np.float64),
        dt_s=dt_s, runoff_parameters=parameters)


class ZeroRainTests(unittest.TestCase):

    def test_zero_rain_with_a_zero_initial_store_produces_nothing(self):
        event = _run_simple_event(
            np.zeros(3),
            parameters=RunoffParameters(infiltration_capacity_mm_h=2.0,
                                        initial_soil_mm=0.0,
                                        initial_fast_mm=0.0,
                                        initial_slow_mm=0.0))
        self.assertEqual(float(np.abs(event["local_q_m3_s"]).max()), 0.0)
        self.assertEqual(event["design_q_m3_s"], 0.0)
        self.assertEqual(float(np.abs(event["routed_terminal_q_m3_s"]).max()), 0.0)

    def test_zero_rain_with_the_default_store_still_drains_the_pit(self):
        """Declared behaviour, pinned: zero rain is not zero runoff by default.

        ``RunoffParameters`` ships ``initial_soil_mm = 30``; that store drains and
        the bucket reports it as release. So "zero rain => zero runoff" holds only
        once the initial store is *also* zero -- the same draw-down caveat the
        coupled ledger records. Stated here instead of hidden.
        """
        default_store = _run_simple_event(np.zeros(3))
        self.assertGreater(float(np.abs(default_store["local_q_m3_s"]).max()), 0.0)
        self.assertLess(float(np.abs(default_store["local_q_m3_s"]).max()), 1e-4)

    def test_the_gate_runoff_depth_is_flat_across_rain_when_the_soil_never_sheds(self):
        """Pinned semantic limit: at the default threshold, rain does not enter.

        ``window_runoff_depth_m`` runs the bucket on one square metre with the
        default ``infiltration_capacity_mm_h = 15``. Below that intensity the bucket
        sheds only its initial store, so rain 0 and rain 8 mm/h return the *same*
        depth. A baseline that wants rain to matter must lower the threshold (the
        calibration ``metric_domain_coupled`` documents) or zero the store.
        """
        zero = window_runoff_depth_m(0.0, intervals=1)
        wet = window_runoff_depth_m(8.0, intervals=1)
        self.assertAlmostEqual(zero, wet, places=15)
        self.assertGreater(zero, 0.0)
        dried = RunoffParameters(initial_soil_mm=0.0, initial_fast_mm=0.0,
                                 initial_slow_mm=0.0)
        self.assertEqual(window_runoff_depth_m(0.0, intervals=1, parameters=dried), 0.0)


class PulseStormTests(unittest.TestCase):

    def setUp(self):
        self.event = _run_simple_event(np.array([60.0, 0.0, 0.0, 0.0, 0.0, 0.0]))

    def test_a_single_interval_pulse_peaks_then_recedes(self):
        routed = self.event["routed_terminal_q_m3_s"]
        self.assertEqual(routed.shape, (6,))
        self.assertTrue(np.all(np.isfinite(routed)))
        self.assertGreater(self.event["design_q_m3_s"], 0.0)
        self.assertEqual(self.event["design_q_m3_s"], float(np.max(routed)))
        peak = int(np.argmax(routed))
        self.assertTrue(np.all(np.diff(routed[peak:]) <= 1e-12))
        self.assertLess(routed[-1], routed[peak])

    def test_the_instantaneous_series_is_the_per_cell_local_q_sum(self):
        instantaneous = self.event["instantaneous_terminal_q_m3_s"]
        local = self.event["local_q_m3_s"]
        np.testing.assert_allclose(instantaneous, local.sum(axis=1),
                                   rtol=1e-12, atol=1e-12)

    def test_only_the_event_peaks_may_be_compared_between_the_two_discharges(self):
        """Pinned semantics, and a counter-example to a wrong comparison.

        The routed series has travel delay; the instantaneous one does not. They may
        be compared at their **event peaks** (the module records that ratio), and the
        routed peak must not exceed the instantaneous peak. They may **not** be
        compared pointwise per interval: on the receding limb the routed value can
        legitimately exceed the instantaneous value of the same step, and it does.
        """
        routed = self.event["routed_terminal_q_m3_s"]
        instantaneous = self.event["instantaneous_terminal_q_m3_s"]
        self.assertLessEqual(self.event["design_q_m3_s"],
                             self.event["instantaneous_peak_m3_s"])
        self.assertTrue(self.event["checks"]["routed_peak_not_above_instantaneous_peak"])
        self.assertGreater(self.event["instantaneous_over_routed_peak_ratio"], 1.0)
        self.assertTrue(bool(np.any(routed > instantaneous + 1e-12)))

    def test_the_event_declares_a_finite_retained_terminal_not_an_outlet(self):
        self.assertEqual(self.event["diagnostic"]["terminal_label"], "retained")
        self.assertIn("not a certified", self.event["terminal"]["semantics"])
        self.assertFalse(self.event["capabilities"]["natural_outlet_certified"])
        self.assertFalse(self.event["capabilities"]["bankfull"])
        self.assertFalse(self.event["capabilities"]["calibrated"])
        self.assertFalse(self.event["capabilities"]["publishable"])
        # The declared terminal is the catchment's own single receiver == -1 cell.
        self.assertEqual(self.event["terminal"]["flat_cell"], 3)
        self.assertEqual(self.event["terminal"]["terminal_count_in_grid"], 1)
        self.assertEqual(self.event["source"]["spacing_m"], 30.0)


class HostileInputTests(unittest.TestCase):

    def test_a_soil_store_above_capacity_is_refused_at_construction(self):
        with self.assertRaisesRegex(ValueError, "initial soil exceeds capacity"):
            RunoffParameters(initial_soil_mm=200.0, soil_capacity_mm=150.0)

    def test_negative_and_non_finite_rain_are_refused_with_stable_tokens(self):
        with self.assertRaisesRegex(ValueError, "invalid_rain"):
            _run_simple_event(np.array([-1.0, 0.0, 0.0]))
        with self.assertRaisesRegex(ValueError, "invalid_rain"):
            _run_simple_event(np.array([np.nan, 0.0, 0.0]))
        with self.assertRaisesRegex(ValueError, "invalid_rain"):
            _run_simple_event(np.array([np.inf, 0.0, 0.0]))

    def test_a_two_dimensional_rain_field_is_refused(self):
        with self.assertRaisesRegex(ValueError, "rain_not_interval_series"):
            _run_simple_event(np.zeros((3, 4)))

    def test_non_finite_elevation_and_a_wrong_dtype_mask_are_refused(self):
        with self.assertRaisesRegex(ValueError, "invalid_elevation_m"):
            _run_simple_event(height=np.array([[np.nan, 3.0, 2.0, 1.0]]))
        with self.assertRaisesRegex(ValueError, "invalid_receiver"):
            _run_simple_event(receiver=np.array([[1, 2, 3, -1]], np.int32))

    def test_a_receiver_cycle_is_refused(self):
        with self.assertRaisesRegex(ValueError, "receiver_cycle"):
            _run_simple_event(receiver=np.array([[1, 2, 3, 2]], np.int64))

    def test_the_window_and_entry_budgets_are_refused_before_any_allocation(self):
        with self.assertRaisesRegex(ValueError, "budget_rainfall_steps"):
            _run_simple_event(np.zeros(100_001))

    def test_the_gate_refuses_non_finite_and_negative_measurements(self):
        base = dict(basin_cells=10, capacity_m3=1.0e3, inflow_m3=1.0,
                    area_m2=10 * CELL_AREA_M2, spill_level_m=100.0,
                    rim_clearance_cells=10, bed_min_m=80.0)
        with self.assertRaisesRegex(ValueError, "finite"):
            judge_depression(**{**base, "capacity_m3": math.nan})
        with self.assertRaisesRegex(ValueError, "finite"):
            judge_depression(**{**base, "inflow_m3": math.inf})
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            judge_depression(**{**base, "area_m2": -1.0})
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            judge_depression(**{**base, "basin_cells": -1})
        with self.assertRaisesRegex(ValueError, "finite"):
            judge_depression(**{**base, "spill_level_m": math.nan})
        with self.assertRaisesRegex(ValueError, "finite positive"):
            judge_depression(**{**base, "config": DepressionGateConfig(alpha=0.0)})

    def test_zero_inflow_is_an_infinite_ratio_that_serialises_explicitly(self):
        record = judge_depression(basin_cells=25, capacity_m3=1.0e3, inflow_m3=0.0,
                                  area_m2=25 * CELL_AREA_M2, spill_level_m=100.0,
                                  rim_clearance_cells=10, bed_min_m=80.0)
        self.assertEqual(record.verdict, VERDICT_LAKE)
        self.assertTrue(math.isinf(record.ratio))
        payload = record.as_record()
        self.assertIsNone(payload["ratio"])           # JSON refuses infinities
        self.assertTrue(payload["ratio_infinite"])

    def test_natural_lake_forcing_guards_refuse_hostile_input(self):
        terrain, owner, seeds, high, low = _two_basin_case()
        closed = _build_mouths(terrain, owner, seeds, np.empty((0, 2)), [])
        with self.assertRaisesRegex(ValueError, "nonnegative local supply"):
            solve_natural_lakes(closed, np.array([0.0, 1.0]),
                                np.array([[-1.0, 0.0]]), np.zeros(2),
                                np.zeros((1, 0)), forcing_provenance="negative")
        with self.assertRaisesRegex(ValueError, "nonnegative local supply"):
            solve_natural_lakes(closed, np.array([0.0, 1.0]), np.array([[0.0, 0.0]]),
                               np.zeros(2), np.array([[np.inf]]),
                               forcing_provenance="non-finite tailwater")
        with self.assertRaisesRegex(ValueError, "finite source support"):
            solve_natural_lakes(closed, np.array([0.0, 1.0]), np.array([[0.0, 0.0]]),
                               np.array([1e12, 0.0]), np.zeros((1, 0)),
                               forcing_provenance="stock over capacity")

    def test_an_overtopped_capacity_fails_the_prefix_rather_than_leaking(self):
        """A basin with no declared mouth stops at its finite capacity."""
        terrain, owner, seeds, high, low = _two_basin_case()
        closed = _build_mouths(terrain, owner, seeds, np.empty((0, 2)), [])
        trace = solve_natural_lakes(closed, np.array([0.0, 100.0]),
                                    np.array([[1000.0, 0.0]]), np.zeros(2),
                                    np.zeros((1, 0)),
                                    config=NaturalLakeConfig(max_step_seconds=0.5),
                                    forcing_provenance="fill past finite capacity")
        self.assertEqual(trace["metadata"]["status"], "failed_prefix")
        self.assertIsNotNone(trace["metadata"]["failure_reason"])
        self.assertLess(float(trace["arrays"]["time_seconds"][-1]), 100.0)
        self.assertTrue(validate_natural_lakes(trace))


if __name__ == "__main__":
    unittest.main()
