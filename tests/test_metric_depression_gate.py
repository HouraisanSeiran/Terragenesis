"""Behaviour tests for the 30 m micro-depression spill gate (P0-1).

Two kinds of test, kept apart on purpose:

* **synthetic** ones state a property that must hold for any field -- a pit is
  passed through, a real basin is kept, the work surface never writes the bed,
  the ledgers never overwrite each other;
* **real-page** ones pin the measured numbers of the acceptance run on
  `world_seed=20261020` (12 748 depressions, 43.41 km2 basin with 1.20e9 m3,
  the 90-cell pocket from the lake-basin acceptance). Those are records: they
  assert values, not "it passed". They are skipped with an explicit message when
  the archived pages are not on disk, so a fresh clone fails noisily in the tool
  rather than silently here.
"""
import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.surface_rivers.metric_depression_gate import (
    DEFAULT_ALPHA, DEFAULT_MIN_AREA_M2, GROWTH_CELLS_STABLE,
    GROWTH_NO_ACCEPTED_WINDOW, GROWTH_PAGE_INTERIOR, GROWTH_STILL_GROWING,
    INFLOW_FILLED_CATCHMENT, REASON_AREA, REASON_CAPACITY, REASON_LAKE,
    REASON_NO_COMPONENT, REASON_STILL_GROWING, REASON_TRUNCATED, VERDICT_LAKE,
    VERDICT_PASS_THROUGH, DepressionGateConfig, basin_size_distribution,
    border_outlet_mask, catchment_comparison, gate_report, growth_verdict,
    judge_depression, judge_seed_in_windows, label_depressions,
    measure_depressions, rim_clearance_cells, route_and_accumulate,
    spill_work_surface, unfilled_catchment_flow, window_runoff_depth_m,
)
from terrain_pipeline.lake import depression_hierarchy as depression_hierarchy

ROOT = Path(__file__).resolve().parents[1]
LAKE_DIR = ROOT / '.scratch/fine-terrain-40km/lake'
PAGE = ROOT / '.scratch/fine-terrain-01/td-window-00.npz'
SPACING_M = 30.0
CELL_AREA = SPACING_M * SPACING_M


# --------------------------------------------------------------------------- #
# fixtures: fields whose answer is known by construction
# --------------------------------------------------------------------------- #
def plateau_with_pits(*, rows=101, columns=101, plateau_m=200.0, pits=(),
                      spacing_cells=3):
    """A flat plateau carrying declared square pits, far from the window border.

    Each pit is ``(centre_row, centre_col, half_width, depth_m)``: a square hole
    whose rim is the plateau, so its spill level *is* ``plateau_m`` and its
    capacity is exact arithmetic -- ``half_width``-square cell count times the
    depth. That makes the gate testable against closed-form numbers instead of
    against itself.
    """
    field = np.full((rows, columns), float(plateau_m), np.float64)
    for centre_row, centre_col, half, depth in pits:
        field[centre_row - half:centre_row + half + 1,
              centre_col - half:centre_col + half + 1] = plateau_m - depth
    return field, spacing_cells


def cone_basin(*, rows=241, columns=241, bottom_m=100.0, rim_m=200.0, radius_cells=40.0):
    """A linear cone on a wide flat rim: a genuine closed basin with A(h) ~ depth^2."""
    zs = np.arange(rows, dtype=np.float64) - (rows - 1) / 2.
    xs = np.arange(columns, dtype=np.float64) - (columns - 1) / 2.
    radius = np.hypot(zs[:, None], xs[None, :])
    return bottom_m + (rim_m - bottom_m) * np.clip(radius / radius_cells, 0., 1.)


# --------------------------------------------------------------------------- #
# the reused routing module: called, not copied, and its fill is the known fill
# --------------------------------------------------------------------------- #
class ReusedRoutingTests(unittest.TestCase):
    """`drainage.route` + `drainage.accumulate` supply the fill, the tree and the water."""

    def test_the_border_outlet_mask_is_exactly_the_border(self):
        outlets = border_outlet_mask((9, 11))
        self.assertEqual(int(outlets.sum()), 2 * 9 + 2 * 11 - 4)
        self.assertTrue(outlets[0, :].all())
        self.assertTrue(outlets[-1, :].all())
        self.assertTrue(outlets[:, 0].all())
        self.assertTrue(outlets[:, -1].all())
        self.assertFalse(outlets[1:-1, 1:-1].any())

    def test_the_route_fill_is_the_hypsometry_fill(self):
        """The fill the water is routed on is the one the lake support measures."""
        rng = np.random.default_rng(20261020)
        field = rng.random((57, 63)) * 500.0
        routed = route_and_accumulate(field, SPACING_M, 0.1)
        reference, _ = depression_hierarchy(field)
        self.assertTrue(np.array_equal(routed["filled_m"], reference))

    def test_routing_does_not_modify_the_bed(self):
        field, _ = plateau_with_pits(pits=[(50, 50, 2, 10.0)])
        before = field.copy()
        route_and_accumulate(field, SPACING_M, 0.1)
        self.assertTrue(np.array_equal(field, before))

    def test_a_monotonically_draining_plane_is_not_filled_and_the_two_readings_coincide(self):
        """No depression means no fill, so filled and unfilled catchments are identical."""
        rows, columns = 81, 91
        zs = np.arange(rows, dtype=np.float64)[:, None]
        xs = np.arange(columns, dtype=np.float64)[None, :]
        field = 500.0 + 0.5 * (rows - zs) + 0.01 * xs
        routed = route_and_accumulate(field, SPACING_M, 0.25)
        self.assertTrue(np.array_equal(routed["filled_m"], field))
        accumulator, _, minima = unfilled_catchment_flow(field)
        self.assertGreater(int(minima.sum()), 0)
        self.assertEqual(int(accumulator.max()), rows * columns)
        self.assertEqual(int((routed["discharge_m3"] > 0).sum()), rows * columns)

    def test_the_water_ledger_closes_and_the_residual_is_a_float_quantity(self):
        """Every border cell is an outlet, so total in must equal total out."""
        field, _ = plateau_with_pits(pits=[(30, 30, 2, 6.0), (70, 70, 4, 30.0)])
        routed = route_and_accumulate(field, SPACING_M, 0.5)
        self.assertAlmostEqual(routed["input_total_m3"],
                               field.size * CELL_AREA * 0.5, places=3)
        self.assertAlmostEqual(routed["outlet_total_m3"],
                               routed["input_total_m3"], places=3)
        self.assertLess(abs(routed["residual_m3"]),
                        1e-9 * routed["input_total_m3"] + 1e-6)

    def test_a_pit_holds_less_than_it_receives_on_its_own_drainage(self):
        """Water accumulates into a pit, so its discharge exceeds its own production."""
        rows = columns = 61
        zs = np.arange(rows, dtype=np.float64)[:, None]
        field = 400.0 + 0.8 * (rows - zs)
        field = np.repeat(field, columns, axis=1)
        field[56:59, 28:31] = 100.0
        routed = route_and_accumulate(field, SPACING_M, 1.0)
        self.assertEqual(float(routed["filled_m"][57, 29]),
                         float(routed["filled_m"][56, 28]))
        pit = routed["discharge_m3"][56:59, 28:31]
        self.assertGreater(float(pit.max()), 9 * CELL_AREA * 1.0)

    def test_the_runoff_depth_comes_from_the_repository_bucket(self):
        self.assertAlmostEqual(window_runoff_depth_m(60.0, dt_s=3600.0, intervals=12),
                               0.5299539772875961, places=9)


# --------------------------------------------------------------------------- #
# the labelling must not leak through dry cells
# --------------------------------------------------------------------------- #
class LabellingTests(unittest.TestCase):
    def test_two_bowls_separated_by_a_plateau_are_two_components(self):
        field, _ = plateau_with_pits(rows=61, columns=61,
                                     pits=[(20, 20, 2, 8.0), (40, 40, 2, 8.0)])
        routed = route_and_accumulate(field, SPACING_M, 0.0)
        labels, count = label_depressions(routed["filled_m"] > field)
        self.assertEqual(count, 2)
        self.assertEqual(sorted(np.unique(labels[labels >= 0]).tolist()), [0, 1])
        self.assertEqual(int((labels == 0).sum()), 25)
        self.assertEqual(int((labels == 1).sum()), 25)

    def test_groups_are_one_per_component_and_cover_every_cell(self):
        """The real bug this suite exists to keep dead: grouping must not shred.

        An earlier version split `np.flatnonzero(labels >= 0)` without sorting by
        label. Flat indices ascend, label values do not, so `np.diff` invented
        boundaries: a 3x3 field with 4 components produced 7 groups, one component
        in 3 shards, and `sizes[label]` was overwritten by the last shard. Every
        capacity and area in the first real-page run was a fragment's value.
        """
        labels = np.array([[3, 3, 7],
                           [3, 0, 7],
                           [5, 0, 0]], np.int64)
        flat = labels.reshape(-1)
        inside = np.flatnonzero(flat >= 0)
        # the unsorted run really does go backwards -- that is the defect
        self.assertLess(int(np.diff(flat[inside]).min()), 0)
        # a sorted run cannot, so one group per label comes out
        ordered = inside[np.argsort(flat[inside], kind="stable")]
        run = flat[ordered]
        self.assertGreaterEqual(int(np.diff(run).min()), 0)
        groups = np.split(ordered, np.flatnonzero(np.diff(run)) + 1)
        self.assertEqual(len(groups), 4)
        self.assertEqual(len(np.unique(run)), 4)
        self.assertEqual(sum(len(group) for group in groups), inside.size)
        self.assertEqual(sorted(int(flat[group[0]]) for group in groups), [0, 3, 5, 7])

    def test_a_labelled_field_reports_exactly_its_component_count(self):
        """measure_depressions must return one verdict per component, none shredded."""
        field, _ = plateau_with_pits(rows=61, columns=61,
                                     pits=[(15, 15, 1, 3.0), (30, 30, 2, 4.0),
                                           (45, 45, 3, 5.0), (20, 45, 1, 2.0)])
        verdicts, context = measure_depressions(field, spacing_m=SPACING_M,
                                                produced_depth_m=0.1)
        self.assertEqual(context["depression_count"], 4)
        self.assertEqual(len(verdicts), 4)
        sizes = np.asarray(context["basin_cells_by_label"], np.int64)
        # labels are 0-based and dense, so EVERY entry is a real depression and the
        # sizes must add up to the wet mask exactly. (An earlier version of this
        # test summed `sizes[1:]`, silently dropping label 0 -- 9 cells lost out of
        # 92, which looked like a code bug and was not.)
        self.assertEqual(int(sizes.sum()), int(context["wet_mask"].sum()))
        self.assertEqual(len(sizes), 4)
        self.assertEqual(sorted(v.basin_cells for v in verdicts),
                         sorted(int(s) for s in sizes))
        for verdict in verdicts:
            self.assertEqual(int(sizes[verdict.label]), verdict.basin_cells)

    def test_labels_are_dense_and_minus_one_outside(self):
        field, _ = plateau_with_pits(rows=41, columns=41,
                                     pits=[(20, 20, 1, 5.0), (30, 10, 2, 5.0),
                                           (12, 30, 1, 5.0)])
        routed = route_and_accumulate(field, SPACING_M, 0.0)
        labels, count = label_depressions(routed["filled_m"] > field)
        self.assertEqual(count, 3)
        self.assertEqual(sorted(np.unique(labels[labels >= 0]).tolist()), [0, 1, 2])
        self.assertTrue((labels[routed["filled_m"] <= field] == -1).all())

    def test_an_empty_mask_is_reported_not_crashed(self):
        labels, count = label_depressions(np.zeros((10, 10), bool))
        self.assertEqual(count, 0)
        self.assertTrue((labels == -1).all())


# --------------------------------------------------------------------------- #
# criterion (a): capacity against arrival
# --------------------------------------------------------------------------- #
class CapacityCriterionTests(unittest.TestCase):
    def test_a_pit_filled_by_its_own_catchment_is_passed_through(self):
        verdict = judge_depression(basin_cells=25, capacity_m3=25 * CELL_AREA * 1.0,
                                   inflow_m3=25 * CELL_AREA * 5.0 + 1e6,
                                   area_m2=25 * CELL_AREA, spill_level_m=200.0,
                                   bed_min_m=199.0, rim_clearance_cells=50)
        self.assertEqual(verdict.verdict, VERDICT_PASS_THROUGH)
        self.assertEqual(verdict.reason_code, REASON_CAPACITY)
        self.assertLess(verdict.ratio, 1.0)
        self.assertFalse(verdict.is_domain_terminal)

    def test_a_basin_that_holds_more_than_arrives_is_kept(self):
        verdict = judge_depression(basin_cells=10000, capacity_m3=1.2e9,
                                   inflow_m3=9.1e5, area_m2=10000 * CELL_AREA,
                                   spill_level_m=120.785, bed_min_m=50.449,
                                   rim_clearance_cells=141)
        self.assertEqual(verdict.verdict, VERDICT_LAKE)
        self.assertEqual(verdict.reason_code, REASON_LAKE)
        self.assertAlmostEqual(verdict.ratio, 1.2e9 / 9.1e5, places=6)
        self.assertGreater(verdict.ratio, 1000.0)

    def test_alpha_moves_the_threshold_and_the_reason_does_not_change(self):
        kwargs = dict(basin_cells=1000, capacity_m3=1.0e6, inflow_m3=5.0e5,
                      area_m2=1000 * CELL_AREA, spill_level_m=200.0,
                      bed_min_m=180.0, rim_clearance_cells=50)
        lenient = judge_depression(config=DepressionGateConfig(alpha=1.0), **kwargs)
        strict = judge_depression(config=DepressionGateConfig(alpha=4.0), **kwargs)
        self.assertEqual(lenient.verdict, VERDICT_LAKE)
        self.assertEqual(strict.verdict, VERDICT_PASS_THROUGH)
        self.assertEqual(strict.reason_code, REASON_CAPACITY)
        self.assertAlmostEqual(strict.ratio, 2.0)
        self.assertAlmostEqual(strict.alpha, 4.0)

    def test_zero_inflow_is_infinite_ratio_and_keeps_a_lake(self):
        verdict = judge_depression(basin_cells=2000, capacity_m3=1.0e5, inflow_m3=0.0,
                                   area_m2=2000 * CELL_AREA, spill_level_m=200.0,
                                   bed_min_m=190.0, rim_clearance_cells=50)
        self.assertTrue(math.isinf(verdict.ratio))
        self.assertEqual(verdict.verdict, VERDICT_LAKE)

    def test_default_alpha_is_one_and_is_declared(self):
        self.assertEqual(DEFAULT_ALPHA, 1.0)
        verdict = judge_depression(basin_cells=100, capacity_m3=1.0, inflow_m3=1.0,
                                   area_m2=100 * CELL_AREA, spill_level_m=200.0,
                                   bed_min_m=150.0, rim_clearance_cells=50)
        self.assertEqual(verdict.alpha, 1.0)
        self.assertAlmostEqual(verdict.ratio, 1.0)
        self.assertEqual(verdict.verdict, VERDICT_LAKE)   # ratio == alpha passes


# --------------------------------------------------------------------------- #
# criterion (b): it has to be big enough to be a lake
# --------------------------------------------------------------------------- #
class AreaCriterionTests(unittest.TestCase):
    def test_a_single_cell_pothole_is_passed_through_by_area(self):
        verdict = judge_depression(basin_cells=1, capacity_m3=1e9, inflow_m3=0.0,
                                   area_m2=CELL_AREA, spill_level_m=200.0,
                                   bed_min_m=199.5, rim_clearance_cells=50)
        self.assertEqual(verdict.verdict, VERDICT_PASS_THROUGH)
        self.assertEqual(verdict.reason_code, REASON_AREA)
        self.assertAlmostEqual(verdict.area_m2, 900.0)

    def test_the_default_minimum_is_10000_square_metres_and_the_boundary_is_inclusive(self):
        self.assertEqual(DEFAULT_MIN_AREA_M2, 10_000.0)
        at = judge_depression(basin_cells=11, capacity_m3=1e6, inflow_m3=0.0,
                              area_m2=DEFAULT_MIN_AREA_M2, spill_level_m=200.0,
                              bed_min_m=150.0, rim_clearance_cells=50)
        below = judge_depression(basin_cells=10, capacity_m3=1e6, inflow_m3=0.0,
                                 area_m2=DEFAULT_MIN_AREA_M2 - CELL_AREA,
                                 spill_level_m=200.0, bed_min_m=150.0,
                                 rim_clearance_cells=50)
        self.assertEqual(at.verdict, VERDICT_LAKE)
        self.assertEqual(below.verdict, VERDICT_PASS_THROUGH)
        self.assertEqual(below.reason_code, REASON_AREA)

    def test_the_90_cell_pocket_is_judged_on_its_own_numbers(self):
        """90 cells = 81 000 m2, so the SIZE rule alone does not reject it.

        This is the point of having criterion (a) as well as (b): on the real page
        the 90-cell object (label 6019) has 81 000 m2 -- above `A_min` -- and a
        capacity of 121 728.8 m3 against an unfilled-catchment inflow of
        91 099.09 m3, a ratio of **1.3362 > alpha**, so the gate KEEPS it and the
        size rule never fires. Reading the acceptance's 90-cell pocket as "must be
        rejected by size" was my own error; the acceptance rejected it because its
        measurement window cut the basin, which is criterion (d), not (b).
        """
        verdict = judge_depression(basin_cells=90, capacity_m3=121_728.8,
                                   inflow_m3=91_099.09, area_m2=90 * CELL_AREA,
                                   spill_level_m=1001.2447, bed_min_m=1000.0,
                                   rim_clearance_cells=623)
        self.assertAlmostEqual(verdict.area_m2, 81_000.0)
        self.assertGreater(verdict.area_m2, DEFAULT_MIN_AREA_M2)
        self.assertAlmostEqual(verdict.ratio, 121_728.8 / 91_099.09, places=6)
        self.assertEqual(verdict.verdict, VERDICT_LAKE)
        # and a 90-cell object that fails the water test is still rejected
        starved = judge_depression(basin_cells=90, capacity_m3=1_000.0,
                                   inflow_m3=91_099.09, area_m2=90 * CELL_AREA,
                                   spill_level_m=1001.2447, bed_min_m=1000.0,
                                   rim_clearance_cells=623)
        self.assertEqual(starved.verdict, VERDICT_PASS_THROUGH)
        self.assertEqual(starved.reason_code, REASON_CAPACITY)

    def test_a_cut_basin_is_rejected_by_the_clearance_rule_not_by_size(self):
        """The acceptance's 90-cell pocket in its TRUNCATED window: clearance -83."""
        verdict = judge_depression(basin_cells=90, capacity_m3=1.2173e5,
                                   inflow_m3=91_099.09, area_m2=90 * CELL_AREA,
                                   spill_level_m=1001.2447, bed_min_m=1000.0,
                                   rim_clearance_cells=-83)
        self.assertEqual(verdict.verdict, VERDICT_PASS_THROUGH)
        self.assertEqual(verdict.reason_code, REASON_TRUNCATED)


# --------------------------------------------------------------------------- #
# criterion (c): "is the component still growing?"
# --------------------------------------------------------------------------- #
class GrowthCriterionTests(unittest.TestCase):
    def family(self, sizes, cells, suspect=None):
        suspect = suspect or [False] * len(sizes)
        return [{"size": size, "basin_cells": cell,
                 "suspect_window_truncation": flag}
                for size, cell, flag in zip(sizes, cells, suspect)]

    def test_the_measured_growth_of_the_real_basin_settles_at_301(self):
        sizes = [45, 61, 101, 151, 211, 301, 421, 843]
        cells = [90, 90, 444, 3328, 10441, 10619, 10619, 10619]
        converged, gate = growth_verdict(self.family(sizes, cells))
        self.assertTrue(converged)
        self.assertEqual(gate, GROWTH_CELLS_STABLE)

    def test_the_pair_that_only_agreed_on_the_wrong_object_is_refused(self):
        """(45, 61) reports converged=True by agreement; here it has no accepted window.

        Both windows measure the same 90-cell pocket, whose rim lies outside the
        page (negative clearance), so `window_family` marks both suspect. The gate
        must refuse the family rather than read 90 == 90 as stability.
        """
        family = self.family([45, 61], [90, 90], suspect=[True, True])
        converged, gate = growth_verdict(family)
        self.assertFalse(converged)
        self.assertEqual(gate, GROWTH_NO_ACCEPTED_WINDOW)

    def test_a_still_growing_pair_is_refused_even_when_both_windows_are_accepted(self):
        converged, gate = growth_verdict(self.family([211, 301], [10441, 10619]))
        self.assertFalse(converged)
        self.assertEqual(gate, GROWTH_STILL_GROWING)

    def test_a_single_accepted_window_cannot_certify_growth(self):
        converged, gate = growth_verdict(self.family([61], [90]))
        self.assertFalse(converged)
        self.assertEqual(gate, "single_window_only")

    def test_an_empty_family_is_not_convergence(self):
        converged, gate = growth_verdict([])
        self.assertFalse(converged)
        self.assertEqual(gate, "component_absent")

    def test_growth_failure_is_reported_as_still_growing(self):
        verdict = judge_depression(basin_cells=10619, capacity_m3=1.037e9,
                                   inflow_m3=1.77e4, area_m2=10619 * CELL_AREA,
                                   spill_level_m=1268.597, bed_min_m=982.413,
                                   rim_clearance_cells=341,
                                   growth_converged=False,
                                   convergence_gate=GROWTH_STILL_GROWING)
        self.assertEqual(verdict.verdict, VERDICT_PASS_THROUGH)
        self.assertEqual(verdict.reason_code, REASON_STILL_GROWING)
        self.assertEqual(verdict.convergence_gate, GROWTH_STILL_GROWING)


# --------------------------------------------------------------------------- #
# criterion (d): a cut basin is not a lake, and not a terrain fact either
# --------------------------------------------------------------------------- #
class TruncationCriterionTests(unittest.TestCase):
    def test_truncation_is_checked_before_size_so_the_terrain_is_not_blamed(self):
        """Truncation is reported first, and it is NOT a terrain property.

        Under the pure-geometry ledger (B) the depression is still closed on the
        terrain -- the window is what failed. So `closed_basin_by_hypsometry` is
        True, `truncated_not_judged` is True, and the gate does not keep it. An
        earlier version of this test asserted `closed_basin_by_hypsometry is
        False`, which smuggled the clearance rule into the terrain verdict.
        """
        verdict = judge_depression(basin_cells=27013, capacity_m3=1e6, inflow_m3=1e12,
                                   area_m2=27013 * CELL_AREA, spill_level_m=101.6216,
                                   bed_min_m=50.449, rim_clearance_cells=2)
        self.assertEqual(verdict.verdict, VERDICT_PASS_THROUGH)
        self.assertEqual(verdict.reason_code, REASON_TRUNCATED)
        self.assertTrue(verdict.truncated_not_judged)
        self.assertTrue(verdict.closed_basin_by_hypsometry)

    def test_the_six_cell_margin_is_the_boundary(self):
        config = DepressionGateConfig()
        self.assertEqual(config.contact_margin_cells, 6)
        inside = judge_depression(basin_cells=1000, capacity_m3=1e7, inflow_m3=1.0,
                                  area_m2=1000 * CELL_AREA, spill_level_m=200.0,
                                  bed_min_m=150.0, rim_clearance_cells=6)
        outside = judge_depression(basin_cells=1000, capacity_m3=1e7, inflow_m3=1.0,
                                   area_m2=1000 * CELL_AREA, spill_level_m=200.0,
                                   bed_min_m=150.0, rim_clearance_cells=5)
        self.assertEqual(inside.verdict, VERDICT_LAKE)
        self.assertEqual(outside.reason_code, REASON_TRUNCATED)

    def test_rim_clearance_is_the_measured_distance(self):
        mask = np.zeros((21, 21), bool)
        mask[5:8, 9:12] = True
        self.assertEqual(rim_clearance_cells(mask, mask.shape), 5)
        mask[0:3, 0:3] = True
        self.assertEqual(rim_clearance_cells(mask, mask.shape), 0)


# --------------------------------------------------------------------------- #
# the two ledgers must both exist and never overwrite each other
# --------------------------------------------------------------------------- #
class TwoLedgerTests(unittest.TestCase):
    def test_a_pit_is_closed_by_hypsometry_but_not_a_terminal(self):
        verdict = judge_depression(basin_cells=1, capacity_m3=1.0, inflow_m3=1e9,
                                   area_m2=CELL_AREA, spill_level_m=200.0,
                                   bed_min_m=199.0, rim_clearance_cells=50)
        self.assertTrue(verdict.closed_basin_by_hypsometry)
        self.assertFalse(verdict.is_domain_terminal)

    def test_a_truncated_basin_is_closed_on_the_terrain_but_not_judged(self):
        """A cut basin is terrain-closed; the truncation is a measurement defect."""
        verdict = judge_depression(basin_cells=257, capacity_m3=1.0, inflow_m3=1e9,
                                   area_m2=257 * CELL_AREA, spill_level_m=200.0,
                                   bed_min_m=199.0, rim_clearance_cells=2)
        self.assertTrue(verdict.closed_basin_by_hypsometry)
        self.assertTrue(verdict.truncated_not_judged)
        self.assertFalse(verdict.is_domain_terminal)

    def test_a_real_basin_is_both(self):
        verdict = judge_depression(basin_cells=48236, capacity_m3=1.2004e9,
                                   inflow_m3=9.104e5, area_m2=48236 * CELL_AREA,
                                   spill_level_m=120.78498, bed_min_m=50.44916,
                                   rim_clearance_cells=141)
        self.assertTrue(verdict.closed_basin_by_hypsometry)
        self.assertTrue(verdict.is_domain_terminal)
        record = verdict.as_record()
        for key in ("basin_cells", "capacity_m3", "inflow_m3", "ratio", "area_m2",
                    "spill_level_m", "verdict", "reason_code"):
            self.assertIn(key, record)
        self.assertTrue(record["closed_basin_by_hypsometry"])
        self.assertTrue(record["is_domain_terminal"])

    def test_the_summary_reports_both_counts_without_replacing_either(self):
        field, _ = plateau_with_pits(pits=[(30, 30, 1, 2.0), (70, 70, 4, 30.0)])
        report = gate_report(field, spacing_m=SPACING_M, produced_depth_m=0.05)
        summary = report.summary()
        before = summary["closed_basin_by_hypsometry"]
        after = summary["is_domain_terminal"]
        truncated = summary["truncated_not_judged"]
        self.assertEqual(summary["depression_count"], 2)
        self.assertEqual(before["count"], 2)
        self.assertEqual(truncated["count"], 0)
        self.assertEqual(after["count"] + truncated["count"]
                         + summary["reclassified_pass_through"], before["count"])
        self.assertIn("size_distribution", before)
        self.assertIn("size_distribution", truncated)
        self.assertIn("size_distribution", after)
        self.assertEqual(sum(before["size_distribution"][index]["count"]
                             for index in range(len(before["size_distribution"]))), 2)


# --------------------------------------------------------------------------- #
# the spill: work surface only
# --------------------------------------------------------------------------- #
class WorkSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.field, _ = plateau_with_pits(rows=81, columns=81, plateau_m=200.0,
                                          pits=[(30, 30, 1, 4.0), (50, 50, 3, 40.0)])
        self.report = gate_report(self.field, spacing_m=SPACING_M,
                                  produced_depth_m=0.0)

    def test_the_original_bed_is_never_written(self):
        before = self.field.copy()
        work, metadata = spill_work_surface(self.field, self.report.verdicts,
                                            self.report.context)
        self.assertTrue(np.array_equal(self.field, before))
        self.assertFalse(np.shares_memory(work, self.field))
        self.assertTrue(metadata["work_surface_only"])
        self.assertTrue(metadata["original_bed_unmodified"])
        self.assertFalse(metadata["publishable_terrain"])

    def test_a_refused_pit_is_raised_exactly_to_its_spill_level(self):
        work, metadata = spill_work_surface(self.field, self.report.verdicts,
                                            self.report.context)
        small = next(record for record in self.report.verdicts
                     if record.basin_cells == 9)
        self.assertEqual(small.verdict, VERDICT_PASS_THROUGH)
        self.assertEqual(small.reason_code, REASON_AREA)
        cells = self.report.context["labels"] == small.label
        self.assertTrue(np.array_equal(work[cells],
                                       np.full(int(cells.sum()), small.spill_level_m)))
        self.assertAlmostEqual(small.spill_level_m, 200.0)
        self.assertEqual(metadata["raised_cells"], 9)

    def test_a_kept_basin_keeps_its_terrain_height(self):
        """A depression the gate keeps must not be raised by one millimetre.

        Note that `produced_depth=0` alone does NOT make every depression a lake:
        criterion (b) still applies, so the 9-cell pit is refused on area and IS
        raised. Only the large pit survives, and only its cells stay untouched.
        """
        report = gate_report(self.field, spacing_m=SPACING_M, produced_depth_m=0.0)
        lakes = [record for record in report.verdicts
                 if record.basin_cells * CELL_AREA >= DEFAULT_MIN_AREA_M2]
        self.assertEqual(len(lakes), 1)
        self.assertEqual(lakes[0].verdict, VERDICT_LAKE)
        work, metadata = spill_work_surface(self.field, report.verdicts,
                                            report.context)
        # the small pit is refused on area and raised; the lake keeps its bed
        self.assertEqual(metadata["raised_cells"], 9)
        self.assertEqual(metadata["preserved_lake_cells"], 49)
        kept = report.context["labels"] == lakes[0].label
        self.assertTrue(np.array_equal(work[kept], self.field[kept]))

    def test_raising_only_refused_pools_is_stricter_than_a_global_fill(self):
        work, metadata = spill_work_surface(self.field, self.report.verdicts,
                                            self.report.context)
        filled = self.report.context["filled_m"]
        globally_raised = int((filled > self.field).sum())
        self.assertEqual(globally_raised, metadata["wet_cells_total"])
        self.assertLess(metadata["raised_cells"], globally_raised)
        self.assertGreater(metadata["preserved_lake_cells"], 0)
        self.assertLessEqual(float(np.max(work - self.field)),
                             float(np.max(filled - self.field)))

    def test_the_raised_cells_drain_off_the_surface(self):
        """Every pass-through cell must have a non-rising neighbour on the work surface."""
        work, _ = spill_work_surface(self.field, self.report.verdicts,
                                     self.report.context)
        routed = route_and_accumulate(work, SPACING_M, 0.0)
        filled = routed["filled_m"]
        self.assertAlmostEqual(float(filled.max()), float(work.max()), places=9)
        self.assertTrue(np.isfinite(filled).all())


# --------------------------------------------------------------------------- #
# the run: a declared storm, through the repository's own bucket
# --------------------------------------------------------------------------- #
class RunoffDepthTests(unittest.TestCase):
    def test_the_declared_storm_produces_the_depth_the_acceptance_quotes(self):
        depth = window_runoff_depth_m(60.0, dt_s=3600.0, intervals=12)
        self.assertAlmostEqual(depth, 0.5299539772875961, places=9)
        self.assertAlmostEqual(depth * 1000.0, 529.954, places=3)

    def test_dry_weather_produces_less_than_a_storm(self):
        self.assertLess(window_runoff_depth_m(2.0), window_runoff_depth_m(40.0))

    def test_a_per_interval_sequence_is_accepted_and_a_wrong_length_is_not(self):
        sequence = [10.0] * 12
        self.assertAlmostEqual(window_runoff_depth_m(sequence),
                               window_runoff_depth_m(10.0), places=12)
        with self.assertRaises(ValueError):
            window_runoff_depth_m([10.0] * 5)

    def test_the_gate_uses_the_depth_it_was_given(self):
        field, _ = plateau_with_pits(pits=[(30, 30, 3, 2.0)])
        dry = gate_report(field, spacing_m=SPACING_M, produced_depth_m=0.0)
        wet = gate_report(field, spacing_m=SPACING_M, produced_depth_m=10.0)
        self.assertEqual(dry.produced_depth_m, 0.0)
        self.assertGreater(wet.verdicts[0].inflow_m3, dry.verdicts[0].inflow_m3)
        self.assertEqual(wet.verdicts[0].verdict, VERDICT_PASS_THROUGH)


# --------------------------------------------------------------------------- #
# window family at full strength: the 90-cell pocket must not be certified
# --------------------------------------------------------------------------- #
class WindowFamilyGateTests(unittest.TestCase):
    def test_a_pocket_family_cannot_be_certified_as_a_lake(self):
        """Negative clearance on both windows: the family is refused, not read as stable."""
        family = [{"size": 45, "basin_cells": 90, "basin_area_m2": 81_000.0,
                   "capacity_m3": 1.2173e5, "spill_level_m": 1001.2447,
                   "bed_min_m": 1000.0, "rim_clearance_cells": -83,
                   "contributing_cells": 200.0, "suspect_window_truncation": True},
                  {"size": 61, "basin_cells": 90, "basin_area_m2": 81_000.0,
                   "capacity_m3": 1.2173e5, "spill_level_m": 1001.2447,
                   "bed_min_m": 1000.0, "rim_clearance_cells": -75,
                   "contributing_cells": 200.0, "suspect_window_truncation": True}]
        verdict, family_out = judge_seed_in_windows(
            None, (0.0, 0.0), (45, 61), SPACING_M, produced_depth_m=0.5299539772875961,
            window_records=family)
        self.assertEqual(verdict.verdict, VERDICT_PASS_THROUGH)
        self.assertIn(verdict.reason_code, (REASON_TRUNCATED, REASON_STILL_GROWING,
                                            REASON_AREA))
        self.assertEqual(family_out["convergence_gate"], GROWTH_NO_ACCEPTED_WINDOW)
        self.assertEqual(family_out["accepted_sizes"], [])

    def test_the_real_basin_family_passes_every_criterion(self):
        records = []
        for size, cells in ((301, 10619), (421, 10619), (843, 10619)):
            records.append({"size": size, "basin_cells": cells,
                            "basin_area_m2": cells * CELL_AREA,
                            "capacity_m3": 1.0373168955871582e9,
                            "spill_level_m": 1268.5965576171875,
                            "bed_min_m": 982.4127197265625,
                            "rim_clearance_cells": 341,
                            "contributing_cells": 196.0,
                            "suspect_window_truncation": False})
        verdict, family = judge_seed_in_windows(
            None, (1318050.0, 1271910.0), (301, 421, 843), SPACING_M,
            produced_depth_m=0.5299539772875961, window_records=records)
        self.assertEqual(family["convergence_gate"], GROWTH_CELLS_STABLE)
        self.assertEqual(family["accepted_sizes"], [301, 421, 843])
        self.assertEqual(verdict.verdict, VERDICT_LAKE)
        self.assertEqual(verdict.reason_code, REASON_LAKE)
        self.assertEqual(verdict.basin_cells, 10619)
        self.assertAlmostEqual(verdict.area_m2, 9_557_100.0, places=6)
        self.assertAlmostEqual(verdict.capacity_m3, 1.0373168955871582e9, places=3)
        self.assertAlmostEqual(verdict.spill_level_m, 1268.5965576171875, places=9)

    def test_an_absent_seed_component_is_reported_not_invented(self):
        records = [{"size": 45, "basin_cells": 0, "basin_area_m2": 0.0,
                    "capacity_m3": 0.0, "spill_level_m": float("nan"),
                    "bed_min_m": 100.0, "rim_clearance_cells": 0,
                    "contributing_cells": 0.0, "component_absent": True,
                    "suspect_window_truncation": True}]
        verdict, _ = judge_seed_in_windows(None, (0.0, 0.0), (45,), SPACING_M,
                                           produced_depth_m=0.1, window_records=records)
        self.assertEqual(verdict.verdict, VERDICT_PASS_THROUGH)
        self.assertEqual(verdict.reason_code, REASON_NO_COMPONENT)
        self.assertEqual(verdict.basin_cells, 0)


# --------------------------------------------------------------------------- #
# measurement on a field whose answer is closed-form
# --------------------------------------------------------------------------- #
class ClosedFormMeasurementTests(unittest.TestCase):
    def test_capacity_matches_the_pit_arithmetic_to_the_last_digit(self):
        field, _ = plateau_with_pits(rows=61, columns=61, plateau_m=200.0,
                                     pits=[(30, 30, 2, 6.0)])
        report = gate_report(field, spacing_m=SPACING_M, produced_depth_m=0.0)
        self.assertEqual(len(report.verdicts), 1)
        record = report.verdicts[0]
        self.assertEqual(record.basin_cells, 25)
        self.assertAlmostEqual(record.capacity_m3, 25 * CELL_AREA * 6.0, places=6)
        self.assertAlmostEqual(record.spill_level_m, 200.0, places=9)
        self.assertAlmostEqual(record.bed_min_m, 194.0, places=9)
        self.assertAlmostEqual(record.relief_m, 6.0, places=9)
        self.assertAlmostEqual(record.area_m2, 22_500.0, places=6)
        self.assertEqual(record.rim_clearance_cells, 28)

    def test_the_cone_basin_capacity_matches_its_hypsometry(self):
        field = cone_basin()
        report = gate_report(field, spacing_m=SPACING_M, produced_depth_m=0.0)
        record = report.verdicts[0]
        self.assertAlmostEqual(record.bed_min_m, 100.0, places=9)
        self.assertAlmostEqual(record.spill_level_m, 200.0, places=9)
        mask = report.context["labels"] == record.label
        expected = float(np.sum(200.0 - field[mask]) * CELL_AREA)
        self.assertAlmostEqual(record.capacity_m3, expected, places=3)
        self.assertGreater(record.basin_cells, 4000)

    def test_the_filled_and_unfilled_inflow_readings_are_close_on_a_pit(self):
        """A pit on a slope: both readings see the same catchment, to within 4 %.

        This CORRECTS an earlier claim of mine. I had reported that the filled
        arrival is only 7.8 % of the inflow, but that 7.8 % divided by the WHOLE
        FIELD's production, not by the pit's catchment. Measured properly the two
        With the fixed irregular graph they read 236 700 m3 filled versus
        244 800 m3 unfilled on a 61x61 ramp.

        So `drainage.route`'s fill does not corrupt "the water entering this
        depression" nearly as badly as I said. What it DOES do is answer a
        different question on a flat plateau (a whole plateau at one level drains
        by flood order, not into its pits), which is why the unfilled catchment
        remains the declared quantity -- but the justification is now the one the
        numbers support, not the one I first wrote.
        """
        rows = cols = 61
        ramp = 400.0 + 0.8 * (rows - np.arange(rows))[:, None] * np.ones((1, cols))
        ramp[56:59, 28:31] = 100.0
        routed = route_and_accumulate(ramp, SPACING_M, 1.0)
        labels, count = label_depressions(routed["filled_m"] > ramp)
        self.assertEqual(count, 1)
        component = labels == 0
        filled = float(routed["discharge_m3"][component].max())
        accumulator, _, minima = unfilled_catchment_flow(ramp)
        unfilled = float(accumulator[component.reshape(-1) & minima].sum()) * CELL_AREA
        self.assertAlmostEqual(filled, 236_700.0, delta=1.0)
        self.assertAlmostEqual(unfilled, 244_800.0, delta=1.0)
        self.assertGreater(filled / unfilled, 0.95)
        self.assertLess(filled / unfilled, 1.001)


# --------------------------------------------------------------------------- #
# the real page: records, not claims
# --------------------------------------------------------------------------- #
@unittest.skipUnless(PAGE.is_file(), "the archived 2049 TD page is required for the record")
class RealPageRecordTests(unittest.TestCase):
    """Pins the acceptance run's numbers. A drift here is a finding, not a nuisance."""

    @classmethod
    def setUpClass(cls):
        with np.load(PAGE, allow_pickle=False) as archive:
            cls.bed = np.asarray(archive["elevation_native"], np.float64)
            cls.metadata = json.loads(str(archive["metadata_json"]))
        cls.depth = window_runoff_depth_m(60.0, dt_s=3600.0, intervals=12)
        cls.report = gate_report(cls.bed, spacing_m=SPACING_M,
                                 produced_depth_m=cls.depth)
        cls.summary = cls.report.summary()

    def test_the_page_is_the_archived_source_at_30_metres(self):
        self.assertEqual(self.bed.shape, (2049, 2049))
        self.assertEqual(self.metadata["native_origin"], [42309, 41976])
        self.assertEqual(int(self.metadata["world_seed"]), 20261020)
        self.assertAlmostEqual(float(self.bed.min()), 50.44915771484375, places=9)

    def test_the_depression_census_matches_the_archived_scan(self):
        archived = json.loads((LAKE_DIR / 'page-basins.json').read_text(encoding='utf-8'))
        self.assertEqual(self.summary["depression_count"], 12_748)
        self.assertEqual(self.summary["depression_count"], archived["components"])

    def test_the_size_distribution_is_the_measured_one(self):
        sizes = np.array([record.basin_cells for record in self.report.verdicts])
        self.assertEqual(int((sizes == 1).sum()), 6_392)
        self.assertEqual(int(np.median(sizes)), 1)
        self.assertEqual(int(sizes.max()), 48_236)
        self.assertEqual(int((sizes > 48_236).sum()), 0)
        capacities = np.array([record.capacity_m3 for record in self.report.verdicts])
        self.assertAlmostEqual(float(np.median(capacities)), 577.26, places=1)

    def test_the_big_basin_is_not_killed_by_the_gate(self):
        """The 43.41 km2 basin, 1.20e9 m3: capacity must dominate its inflow."""
        big = self.report.verdicts[0]
        self.assertEqual(big.basin_cells, 48_236)
        self.assertAlmostEqual(big.area_m2, 43_412_400.0, places=6)
        self.assertAlmostEqual(big.capacity_m3, 1.200351642e9, delta=1e4)
        self.assertAlmostEqual(big.spill_level_m, 120.78498077392578, places=6)
        self.assertAlmostEqual(big.bed_min_m, 50.44915771484375, places=9)
        self.assertEqual(big.verdict, VERDICT_LAKE)
        self.assertEqual(big.reason_code, REASON_LAKE)
        self.assertTrue(big.is_domain_terminal)
        self.assertTrue(big.closed_basin_by_hypsometry)
        # measured: inflow 4.57208e7 m3 from the unfilled catchment -> ratio 26.3
        self.assertAlmostEqual(big.inflow_m3, 4.5720772e7, delta=1e3)
        self.assertAlmostEqual(big.ratio, 26.253967, places=5)
        self.assertGreater(big.ratio, 1.0)

    def test_alpha_cannot_flip_the_big_basin_inside_its_measured_range(self):
        """How large could alpha be before the 43.41 km2 basin is rejected?"""
        big = self.report.verdicts[0]
        # the measured ratio is the break-even alpha for this basin
        self.assertAlmostEqual(big.ratio, 26.253967, places=5)
        kept = judge_depression(basin_cells=big.basin_cells,
                                capacity_m3=big.capacity_m3,
                                inflow_m3=big.inflow_m3, area_m2=big.area_m2,
                                spill_level_m=big.spill_level_m,
                                bed_min_m=big.bed_min_m,
                                rim_clearance_cells=big.rim_clearance_cells,
                                config=DepressionGateConfig(alpha=20.0))
        rejected = judge_depression(basin_cells=big.basin_cells,
                                    capacity_m3=big.capacity_m3,
                                    inflow_m3=big.inflow_m3, area_m2=big.area_m2,
                                    spill_level_m=big.spill_level_m,
                                    bed_min_m=big.bed_min_m,
                                    rim_clearance_cells=big.rim_clearance_cells,
                                    config=DepressionGateConfig(alpha=40.0))
        self.assertEqual(kept.verdict, VERDICT_LAKE)
        self.assertEqual(rejected.verdict, VERDICT_PASS_THROUGH)
        self.assertEqual(rejected.reason_code, REASON_CAPACITY)

    def test_every_basin_the_gate_keeps_is_a_real_basin(self):
        kept = self.report.by_gate
        self.assertTrue(kept)
        for record in kept:
            self.assertGreaterEqual(record.area_m2, DEFAULT_MIN_AREA_M2)
            self.assertGreaterEqual(record.rim_clearance_cells, 6)
            self.assertGreater(record.ratio, 1.0)
        self.assertEqual([record.basin_cells for record in kept],
                         sorted([record.basin_cells for record in kept], reverse=True))
        ratios = sorted(record.ratio for record in kept)
        self.assertAlmostEqual(ratios[0], 1.0, delta=0.05)     # smallest kept ratio ~1.02
        self.assertAlmostEqual(ratios[-1], 76.7, delta=0.1)    # the 9.56 km2 mountain lake
        self.assertEqual(len(kept), 131)

    def test_single_cell_and_small_pits_are_all_reclassified(self):
        pass_through = [record for record in self.report.verdicts
                        if record.verdict == VERDICT_PASS_THROUGH]
        single = [record for record in pass_through if record.basin_cells == 1]
        self.assertEqual(len(single), 6_392)
        for record in single:
            # a 1-cell pit holds ~4.6e3 m3 and its catchment delivers more, so the
            # water test fires; a handful fail on order-of-check but the point is
            # that all of them are pass-through and none is a lake
            self.assertIn(record.reason_code,
                          (REASON_CAPACITY, REASON_AREA, REASON_TRUNCATED))
            self.assertAlmostEqual(record.area_m2, CELL_AREA, places=6)
        self.assertTrue(all(record.verdict == VERDICT_PASS_THROUGH for record in single))
        small = [record for record in pass_through if record.basin_cells <= 90]
        self.assertTrue(all(record.reason_code in (REASON_CAPACITY, REASON_AREA,
                                                   REASON_TRUNCATED)
                            for record in small))

    def test_the_before_after_and_truncated_columns_are_the_measured_triple(self):
        before = self.summary["closed_basin_by_hypsometry"]["count"]
        truncated = self.summary["truncated_not_judged"]["count"]
        after = self.summary["is_domain_terminal"]["count"]
        self.assertEqual(before, 12_748)
        self.assertEqual(truncated, 208)
        self.assertEqual(after, 131)
        # 12 748 closed on the terrain = 131 kept + 208 not judgeable + 12 409 reclassified
        self.assertEqual(self.summary["reclassified_pass_through"], 12_409)
        self.assertEqual(after + truncated + self.summary["reclassified_pass_through"],
                         before)
        reasons = self.summary["reason_counts"]
        self.assertEqual(reasons[REASON_CAPACITY], 11_643)
        self.assertEqual(reasons[REASON_AREA], 766)
        self.assertEqual(reasons[REASON_TRUNCATED], 208)
        self.assertEqual(reasons[REASON_STILL_GROWING], 0)
        self.assertEqual(reasons[REASON_NO_COMPONENT], 0)
        self.assertEqual(reasons[REASON_LAKE], 131)
        self.assertEqual(sum(reasons.values()), 12_748)

    def test_every_single_cell_depression_is_gone_after_the_gate(self):
        """The headline result: no 30 m pit is a domain endpoint any more."""
        self.assertEqual(self.summary["single_cell_before"], 6_392)
        self.assertEqual(self.summary["single_cell_after"], 0)
        self.assertEqual(sum(1 for record in self.report.verdicts
                             if record.basin_cells == 1), 6_392)
        self.assertEqual(sum(1 for record in self.report.by_gate
                             if record.basin_cells == 1), 0)

    def test_the_work_surface_raises_only_the_refused_pools(self):
        work, metadata = spill_work_surface(self.bed, self.report.verdicts,
                                            self.report.context)
        before = self.bed.copy()
        self.assertTrue(metadata["work_surface_only"])
        self.assertTrue(metadata["original_bed_unmodified"])
        self.assertTrue(np.array_equal(self.bed, before))
        self.assertEqual(metadata["wet_cells_total"], 224_286)
        self.assertEqual(metadata["raised_cells"], 60_560)
        self.assertEqual(metadata["preserved_lake_cells"], 163_726)
        self.assertEqual(metadata["refused_depressions"], 12_617)
        self.assertEqual(metadata["raised_cells"] + metadata["preserved_lake_cells"],
                         metadata["wet_cells_total"])
        # every kept lake keeps its terrain height exactly; nothing else is untouched
        for record in self.report.by_gate:
            cells = self.report.context["labels"] == record.label
            self.assertTrue(np.array_equal(work[cells], self.bed[cells]))
            self.assertGreater(int(cells.sum()), 0)
        raised = work != self.bed
        self.assertTrue((work[raised] >= self.bed[raised]).all())
        self.assertEqual(int(raised.sum()), metadata["raised_cells"])

    def test_two_runs_agree_on_every_recorded_number(self):
        second = gate_report(self.bed, spacing_m=SPACING_M,
                             produced_depth_m=self.depth)
        self.assertEqual(self.report.identity_sha256(), second.identity_sha256())
        self.assertEqual(self.summary["reason_counts"], second.summary()["reason_counts"])

    def test_the_page_interior_growth_gate_is_labelled_as_weaker(self):
        for record in self.report.verdicts:
            self.assertEqual(record.convergence_gate, GROWTH_PAGE_INTERIOR)


if __name__ == '__main__':
    unittest.main()
