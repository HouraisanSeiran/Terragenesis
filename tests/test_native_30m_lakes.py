"""Small synthetic tests for the native-30 m lake / depression storage-and-spill mechanism.

Discipline of this file (stated so the checks cannot be over-read)
-----------------------------------------------------------------
* Expected values are **closed-form arithmetic** or an **independent traversal
  written here**. The independent reference never imports the module under test
  (``native_30m_lakes``) and never imports ``world_reach_lake``; it reads only the
  raw bed and does its own priority flood, its own component walk, its own rim scan
  and its own storage integral.
* Where a number cannot be computed independently -- the weir discharge law, which
  is the repository's existing ``LakeOutlet`` rating -- the check is stated as a
  *property* (zero below the crest, monotone in head, and the exact ``C h**1.5``
  law with ``C`` taken from the module's own declared record), never as a
  hard-coded expectation.
* Every fixture is analytic and tiny: tens to a few hundred 30 m cells (~900 m2
  each). No 48 km run, no GPU, no archived page.
* A gap is recorded with an explicit assertion plus a comment; **no assertion is
  relaxed to make a gap disappear** (see ``RecordedGapTests``).
* Units: elevation/stage m, area m2, volume m3, physical time s, discharge
  m3 s-1, outlet coefficient m3 s-1 m-1.5, spacing 30 m.
"""
import json
import math
import unittest

import numpy as np
from terrain_pipeline.drainage import grid_mesh as grid_mesh

from terrain_pipeline.surface_rivers.metric_cross_region import CONTACT_MARGIN_CELLS
from terrain_pipeline.lake import NATIVE_30M_LAKE_ALGORITHM as ALGORITHM
from terrain_pipeline.lake import BED_SURFACE_KIND as BED_SURFACE_KIND
from terrain_pipeline.lake import BUDGETS as BUDGETS
from terrain_pipeline.lake import LEVEL_TOLERANCE_M as LEVEL_TOLERANCE_M
from terrain_pipeline.lake import REASON_CERTIFIED as REASON_CERTIFIED
from terrain_pipeline.lake import REASON_FILL_NOT_CONSTANT as REASON_FILL_NOT_CONSTANT
from terrain_pipeline.lake import REASON_MEMBERSHIP_LEAK as REASON_MEMBERSHIP_LEAK
from terrain_pipeline.lake import REASON_NO_DEPRESSION as REASON_NO_DEPRESSION
from terrain_pipeline.lake import REASON_RIM_IN_BAND as REASON_RIM_IN_BAND
from terrain_pipeline.lake import REASON_SADDLE_ABSENT as REASON_SADDLE_ABSENT
from terrain_pipeline.lake import REASON_SADDLE_IN_BAND as REASON_SADDLE_IN_BAND
from terrain_pipeline.lake import REASON_UPSTREAM_UNKNOWN as REASON_UPSTREAM_UNKNOWN
from terrain_pipeline.lake import REASON_WINDOW_UNRESOLVED as REASON_WINDOW_UNRESOLVED
from terrain_pipeline.lake import NATIVE_30M_LAKE_SCHEMA as SCHEMA
from terrain_pipeline.lake import TOLERANCES as TOLERANCES
from terrain_pipeline.lake import UNITS as UNITS
from terrain_pipeline.lake import WATER_SURFACE_KINDS as WATER_SURFACE_KINDS
from terrain_pipeline.lake import Native30mLake as Native30mLake
from terrain_pipeline.lake import basin_catchment as basin_catchment
from terrain_pipeline.lake import build_native_30m_lake as build_native_30m_lake
from terrain_pipeline.lake import inflow_volume_m3 as inflow_volume_m3
from terrain_pipeline.lake import initial_volume_m3 as initial_volume_m3
from terrain_pipeline.lake import lowest_saddle as lowest_saddle
from terrain_pipeline.lake import march_lake as march_lake
from terrain_pipeline.lake import measure_basin as measure_basin
from terrain_pipeline.lake import validate_native_30m_lake as validate_native_30m_lake


SPACING_M = 30.0
CELL_AREA_M2 = SPACING_M * SPACING_M          # 900 m2
WORLD_SEED = 20261020                        # CONTRIBUTING.md:35
SOURCE_SHA = "b" * 64                        # fixture identity placeholder
SILL_WIDTH_M = 40.0
DISCHARGE_COEFFICIENT = 0.4
HEAD_ALLOWANCE_M = 2.0


# --------------------------------------------------------------------------- #
# independent reference: no import of the module under test, no repository solver,
# no repository storage class
# --------------------------------------------------------------------------- #
def reference_priority_flood(bed):
    """Border-seeded priority flood computed from its definition, with a heap.

    ``filled[i] = min over paths to the window border of (max elevation on path)``,
    over the actual irregular graph. Deliberately a separate flood from the
    module under test, so a shared mistake cannot hide.
    """
    import heapq
    field = np.asarray(bed, np.float64)
    rows, columns = field.shape
    mesh = grid_mesh(field.shape, dx_m=SPACING_M)
    filled = np.full(field.shape, np.inf)
    done = np.zeros(field.shape, bool)
    heap = []
    for row in range(rows):
        for column in range(columns):
            if row in (0, rows - 1) or column in (0, columns - 1):
                filled[row, column] = field[row, column]
                heapq.heappush(heap, (float(field[row, column]), row, column))
    while heap:
        level, row, column = heapq.heappop(heap)
        if done[row, column]:
            continue
        done[row, column] = True
        cell = row * columns + column
        for target in mesh.indices[mesh.indptr[cell]:mesh.indptr[cell + 1]]:
            rr, cc = divmod(int(target), columns)
            if done[rr, cc]:
                continue
            candidate = max(level, float(field[rr, cc]))
            if candidate < filled[rr, cc]:
                filled[rr, cc] = candidate
                heapq.heappush(heap, (candidate, rr, cc))
    return filled


def reference_component(bed, filled, seed):
    """Independent graph walk of positive fill depth from the seed."""
    depth = np.asarray(filled, np.float64) - np.asarray(bed, np.float64)
    rows, columns = depth.shape
    mesh = grid_mesh(depth.shape, dx_m=SPACING_M)
    found = np.zeros(depth.shape, bool)
    if depth[seed] <= 0.:
        return found
    found[seed] = True
    stack = [seed]
    while stack:
        row, column = stack.pop()
        cell = row * columns + column
        for target in mesh.indices[mesh.indptr[cell]:mesh.indptr[cell + 1]]:
            rr, cc = divmod(int(target), columns)
            if depth[rr, cc] > 0. and not found[rr, cc]:
                found[rr, cc] = True
                stack.append((rr, cc))
    return found


def reference_rim(mask):
    """Actual graph-neighbor cells outside the component."""
    mask = np.asarray(mask, bool)
    rows, columns = mask.shape
    out = np.zeros(mask.shape, bool)
    mesh = grid_mesh(mask.shape, dx_m=SPACING_M)
    for row in range(rows):
        for column in range(columns):
            if mask[row, column]:
                continue
            cell = row * columns + column
            for target in mesh.indices[mesh.indptr[cell]:mesh.indptr[cell + 1]]:
                if mask.ravel()[target]:
                    out[row, column] = True
                    break
    return out


def reference_volume(bed, mask, stage):
    """V(h) = 900 * sum(max(h - bed, 0)) over the members: the definition itself."""
    beds = np.asarray(bed, np.float64)[np.asarray(mask, bool)]
    return float(CELL_AREA_M2 * np.maximum(stage - beds, 0.).sum())


def reference_area(bed, mask, stage):
    """A(h) = 900 * count of members strictly below the level."""
    beds = np.asarray(bed, np.float64)[np.asarray(mask, bool)]
    return float(CELL_AREA_M2 * int((beds < stage).sum()))


def reference_clearance(mask):
    """Distance in cells from a component to the window border."""
    mask = np.asarray(mask, bool)
    rows, columns = mask.shape
    rr, cc = np.nonzero(mask)
    return int(min(rr.min(), cc.min(), rows - 1 - rr.max(), columns - 1 - cc.max()))


# --------------------------------------------------------------------------- #
# fixtures: analytic beds with closed-form storage
# --------------------------------------------------------------------------- #
def plateau_pit(size=15, plateau_m=10.0, pit_m=0.0):
    """One 30 m pit in a flat plateau: the smallest possible lake."""
    field = np.full((size, size), float(plateau_m))
    field[size // 2, size // 2] = float(pit_m)
    return field


def tied_rim_box(size=21, plateau_m=10.0, bed_m=3.0, low=8, high=13):
    """A rectangular basin with one flat bed: V(h) = 900 * cells * (h - bed).

    ``size`` is 21, so the core sits at low=8..high=13 and clears the 6-cell
    untrusted band on both the basin rim and the exit set. That is the fixture the
    spill / recession tests use, because its arithmetic is exact.
    """
    field = np.full((size, size), float(plateau_m))
    field[low:high, low:high] = float(bed_m)
    return field


def cone_bowl(size=31, bottom_m=100.0, rim_m=112.0, radius_cells=6.0):
    """A linear cone inside a flat plateau: A(h) grows with the level."""
    zs = np.arange(size, dtype=np.float64) - (size - 1) / 2.
    xs = np.arange(size, dtype=np.float64) - (size - 1) / 2.
    radius = np.hypot(zs[:, None], xs[None, :])
    inside = np.clip(1.0 - radius / radius_cells, 0.0, None)
    return rim_m - (rim_m - bottom_m) * inside


def deep_bowl(size=61, rim_m=40.0, radius_cells=14.0):
    """A deep cone for the lake / puddle gate: large capacity, small catchment."""
    zs = np.arange(size, dtype=np.float64) - (size - 1) / 2.
    xs = zs
    radius = np.hypot(zs[:, None], xs[None, :])
    inside = np.clip(1.0 - radius / radius_cells, 0.0, None)
    return rim_m - rim_m * inside


def two_pit_plateau(rows=17, columns=31):
    """Two pits on one plateau with a taller wall between them.

    Left bed 4 m, right bed 2 m, wall 8 m, plateau 10 m. The escape of the left
    basin is the plateau (10 m), **not** the interior wall (8 m), and the right pit
    is below the left basin's escape level yet is not a member of it.
    """
    field = np.full((rows, columns), 10.0)
    field[rows // 2, 6] = 4.0
    field[rows // 2, 24] = 2.0
    field[rows // 2, 15] = 8.0
    return field


def sloped_lowland(size=21):
    """A draining slope: low, open, and not a lake."""
    zs = np.arange(size, dtype=np.float64)
    xs = np.arange(size, dtype=np.float64)
    return 0.5 * zs[:, None] + 0.5 * xs[None, :]


def flat_lowland(size=15, elevation_m=2.0):
    """A perfectly flat low plain: every cell drains off the border."""
    return np.full((size, size), float(elevation_m))


def pit_on_a_slope(size=15, gradient=0.4, base_m=10.0, dig_m=6.0):
    """A pit dug into a slope: closed, but its catchment leaves the window."""
    zs = np.arange(size, dtype=np.float64)
    xs = np.arange(size, dtype=np.float64)
    field = base_m + gradient * zs[:, None] + gradient * xs[None, :]
    field[size // 2, size // 2] -= dig_m
    return field


def build(bed, seed, **overrides):
    """Call the module under test with every argument declared in one place."""
    arguments = dict(
        seed_cell_rc=seed, spacing_m=SPACING_M, origin_xz_m=(0., 0.),
        source_identity_sha256=SOURCE_SHA, surface_kind=BED_SURFACE_KIND,
        sill_width_m=SILL_WIDTH_M, discharge_coefficient=DISCHARGE_COEFFICIENT,
        head_allowance_m=HEAD_ALLOWANCE_M)
    arguments.update(overrides)
    bed = np.asarray(bed, np.float64)
    return build_native_30m_lake(bed, np.ones(bed.shape, bool), **arguments)


# --------------------------------------------------------------------------- #
# S1. membership, escape level, exit set
# --------------------------------------------------------------------------- #
class BasinMembershipAndSaddleTests(unittest.TestCase):

    def test_membership_is_the_independent_component(self):
        bed = cone_bowl()
        lake = build(bed, (15, 15))
        filled = reference_priority_flood(bed)
        members = reference_component(bed, filled, (15, 15))
        self.assertTrue(lake.certified, lake.reason_code)
        self.assertEqual(int(lake.basin_mask.sum()), int(members.sum()))
        np.testing.assert_array_equal(np.asarray(lake.basin_mask), members)
        self.assertAlmostEqual(lake.basin_cells * CELL_AREA_M2, lake.basin_area_m2, places=9)

    def test_a_cell_below_the_escape_level_can_still_be_excluded(self):
        """Membership is the depression, not "everything lower than the level".

        The right pit (bed 2 m) lies below the left basin's 10 m escape level but is
        a separate depression behind an 8 m wall: the module must not swallow it.
        """
        bed = two_pit_plateau()
        lake = build(bed, (8, 6), contact_margin_cells=4)
        self.assertTrue(lake.certified, lake.reason_code)
        mask = np.asarray(lake.basin_mask)
        self.assertTrue(mask[8, 6])
        self.assertFalse(mask[8, 24])
        self.assertLess(bed[8, 24], lake.spill_level_m)
        self.assertTrue((bed[~mask] < lake.spill_level_m).any())
        self.assertAlmostEqual(lake.spill_level_m, 10.0, places=9)

    def test_the_escape_level_is_the_independent_flood_level_and_is_constant(self):
        bed = cone_bowl()
        lake = build(bed, (15, 15))
        filled = reference_priority_flood(bed)
        members = reference_component(bed, filled, (15, 15))
        levels = filled[members]
        self.assertLessEqual(float(levels.max() - levels.min()), LEVEL_TOLERANCE_M)
        self.assertAlmostEqual(lake.spill_level_m, float(levels.max()), places=9)
        self.assertAlmostEqual(float(lake.saddle["flood_level_constancy_m"]), 0.0,
                               places=12)

    def test_the_exit_set_is_the_independent_exit_set(self):
        bed = cone_bowl()
        lake = build(bed, (15, 15))
        filled = reference_priority_flood(bed)
        members = reference_component(bed, filled, (15, 15))
        rim = reference_rim(members)
        spill = float(filled[members].max())
        independent = rim & (np.abs(filled - spill) <= LEVEL_TOLERANCE_M)
        self.assertGreater(int(independent.sum()), 0)
        self.assertEqual(int(lake.saddle["exit_cells"]), int(independent.sum()))
        np.testing.assert_array_equal(np.asarray(lake.saddle["exit_mask"]), independent)

    def test_graph_membership_does_not_invent_a_diagonal_rim_contact(self):
        """The measured trap: a shelf cell can be *lower* than the real exit.

        One plateau cell next to (but only diagonally reachable from) the bowl is
        lowered to 110 m. The naive "lowest rim bed" then reports 110 m although the
        water still has to rise to 112 m. The module reports 112 m and keeps 110 m
        only as a rejected number with its measured difference.
        """
        bed = cone_bowl()
        bed[10, 10] = 110.0
        lake = build(bed, (15, 15))
        self.assertTrue(lake.certified, lake.reason_code)
        geometric = float(lake.saddle["geometric_rim_minimum_m"])
        self.assertAlmostEqual(lake.spill_level_m, 112.0, places=9)
        self.assertFalse(lake.basin_mask[10, 10])
        self.assertGreaterEqual(geometric, lake.spill_level_m - 1e-6)
        self.assertAlmostEqual(float(lake.saddle["geometric_minus_spill_m"]),
                               geometric - lake.spill_level_m, places=9)
        self.assertAlmostEqual(lake.outlets[0].crest_stage_m, lake.spill_level_m, places=9)
        self.assertIn("rejected", lake.provenance["saddle_policy"])

    def test_a_tied_rectangular_rim_reports_every_exit_cell(self):
        bed = tied_rim_box()
        lake = build(bed, (10, 10))
        self.assertTrue(lake.certified, lake.reason_code)
        self.assertAlmostEqual(lake.spill_level_m, 10.0, places=9)
        self.assertEqual(int(lake.saddle["exit_cells"]), int(reference_rim(lake.basin_mask).sum()))
        self.assertAlmostEqual(float(lake.saddle["geometric_rim_minimum_m"]), 10.0,
                               places=9)
        self.assertAlmostEqual(float(lake.saddle["geometric_minus_spill_m"]), 0.0,
                               places=12)

    def test_an_interior_wall_is_not_the_escape_of_the_basin(self):
        bed = two_pit_plateau()
        lake = build(bed, (8, 6), contact_margin_cells=4)
        self.assertEqual(int(lake.basin_mask.sum()), 1)
        self.assertAlmostEqual(lake.spill_level_m, 10.0, places=9)
        self.assertGreater(lake.spill_level_m, 8.0)


# --------------------------------------------------------------------------- #
# S2. storage curve V(h) / A(h)
# --------------------------------------------------------------------------- #
class StorageCurveTests(unittest.TestCase):

    def test_flat_bed_volume_matches_the_independent_integral(self):
        bed = tied_rim_box()
        lake = build(bed, (10, 10))
        members = np.asarray(lake.basin_mask)
        for stage in (3.0, 4.5, 7.0, 9.5, 10.0):
            self.assertAlmostEqual(lake.storage.volume_at_stage(stage),
                                   reference_volume(bed, members, stage), places=6,
                                   msg="V(%.6f) != 900*sum(max(h-bed,0))" % stage)
            self.assertAlmostEqual(lake.storage.surface_area_at_stage(stage),
                                   reference_area(bed, members, stage), places=6)

    def test_capacity_at_the_saddle_is_the_volume_below_the_exit_level(self):
        bed = tied_rim_box()
        lake = build(bed, (10, 10))
        self.assertAlmostEqual(lake.capacity_at_spill_m3,
                               reference_volume(bed, lake.basin_mask, lake.spill_level_m),
                               places=6)
        self.assertAlmostEqual(lake.capacity_at_spill_m3, 25 * 7.0 * CELL_AREA_M2, places=6)
        self.assertAlmostEqual(lake.capacity_at_spill_m3, 157_500.0, places=6)
        self.assertAlmostEqual(lake.storage_capacity_m3,
                               25 * 9.0 * CELL_AREA_M2, places=6)

    def test_cone_bowl_volume_matches_the_independent_integral(self):
        bed = cone_bowl()
        lake = build(bed, (15, 15))
        members = np.asarray(lake.basin_mask)
        for stage in (100.0, 103.0, 106.0, 111.0, 112.0):
            self.assertAlmostEqual(lake.storage.volume_at_stage(stage),
                                   reference_volume(bed, members, stage), places=6)

    def test_the_store_is_not_a_vertical_wall_tank(self):
        bed = cone_bowl()
        lake = build(bed, (15, 15))
        areas = [lake.storage.surface_area_at_stage(stage)
                 for stage in (100.5, 103., 106., 111.)]
        self.assertLess(areas[0], areas[1])
        self.assertLess(areas[1], areas[2])
        self.assertLess(areas[2], areas[3])
        self.assertLess(areas[0], 0.5 * lake.basin_cells * CELL_AREA_M2)
        self.assertGreater(float(lake.provenance["saddle_pondage_area_m2"]), 0.0)

    def test_volume_and_stage_round_trip_inside_the_support(self):
        bed = cone_bowl()
        lake = build(bed, (15, 15))
        for stage in (100.0, 101.0, 105.5, 111.9):
            volume = lake.storage.volume_at_stage(stage)
            self.assertAlmostEqual(lake.storage.stage_at_volume(volume), stage,
                                   delta=TOLERANCES["level_round_trip_m"])

    def test_above_the_saddle_is_a_declared_pondage_not_measured_terrain(self):
        bed = cone_bowl()
        lake = build(bed, (15, 15))
        area_at_saddle = lake.storage.surface_area_at_stage(lake.spill_level_m)
        head = 1.0
        self.assertAlmostEqual(
            lake.storage.volume_at_stage(lake.spill_level_m + head),
            lake.capacity_at_spill_m3 + area_at_saddle * head, places=6)
        self.assertAlmostEqual(lake.storage.max_stage_m,
                               lake.spill_level_m + HEAD_ALLOWANCE_M, places=12)
        self.assertIn("declared pondage", lake.provenance["above_saddle_pondage_policy"])


# --------------------------------------------------------------------------- #
# S3. initial water, inflow, overflow, recession
# --------------------------------------------------------------------------- #
class SpillAndRecessionTests(unittest.TestCase):

    def setUp(self):
        self.bed = tied_rim_box()
        self.lake = build(self.bed, (10, 10))
        self.assertTrue(self.lake.certified, self.lake.reason_code)

    def test_initial_water_is_the_volume_at_a_declared_stage(self):
        stage = 6.0
        volume = initial_volume_m3(self.lake, initial_stage_m=stage)
        self.assertAlmostEqual(volume, reference_volume(self.bed, self.lake.basin_mask, stage),
                               places=6)
        self.assertAlmostEqual(volume, 25 * 3.0 * CELL_AREA_M2, places=6)

    def test_an_initial_stage_outside_the_support_is_refused(self):
        with self.assertRaises(ValueError):
            initial_volume_m3(self.lake, initial_stage_m=self.lake.spill_level_m + 0.5)
        with self.assertRaises(ValueError):
            initial_volume_m3(self.lake, initial_stage_m=2.0)

    def test_inflow_is_catchment_area_times_produced_depth(self):
        inflow, record = inflow_volume_m3(self.lake, produced_depth_m=0.05)
        self.assertAlmostEqual(inflow,
                               record["contributing_cells"] * CELL_AREA_M2 * 0.05, places=6)
        self.assertEqual(record["inflow_quantity"], "unfilled_catchment_production")
        self.assertEqual(record["contributing_cells"],
                         self.lake.catchment["contributing_cells"])
        with self.assertRaises(ValueError):
            inflow_volume_m3(self.lake, produced_depth_m=-1.0)

    def test_a_step_below_the_saddle_stores_everything_and_spills_nothing(self):
        start = initial_volume_m3(self.lake, initial_stage_m=8.0)
        headroom = self.lake.capacity_at_spill_m3 - start
        trace = march_lake(self.lake, np.array([headroom / 2.0]), np.array([600.0]),
                           initial_volume_m3=start)
        self.assertTrue(trace["ledger_closed"])
        self.assertEqual(float(trace["spill_volume_m3"].sum()), 0.0)
        self.assertAlmostEqual(float(trace["volume_m3"][-1]), start + headroom / 2.0,
                               places=6)
        self.assertLess(float(trace["stage_m"][-1]), self.lake.spill_level_m)

    def test_overflow_at_the_saddle_stores_spills_and_recedes(self):
        start = self.lake.capacity_at_spill_m3
        inflow = np.array([4000.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        trace = march_lake(self.lake, inflow, np.full(6, 120.0), initial_volume_m3=start)
        self.assertTrue(trace["ledger_closed"])
        ledger = trace["ledger"]
        self.assertAlmostEqual(ledger["initial_m3"] + ledger["inflow_m3"]
                               - ledger["spill_m3"] - ledger["final_m3"],
                               ledger["residual_m3"], places=9)
        stage = np.asarray(trace["stage_m"])
        self.assertGreater(float(stage[1]), self.lake.spill_level_m)
        # the first step fills; every step after it only drains
        self.assertTrue(np.all(np.diff(stage[1:]) <= 1e-12))
        self.assertGreater(float(trace["spill_volume_m3"][0].sum()), 0.0)
        self.assertLess(float(stage[-1]), float(stage[1]))
        self.assertGreater(float(stage[-1]), self.lake.spill_level_m - 1e-12)

    def test_the_recession_creeps_back_to_the_saddle(self):
        """Recorded property: the exponential tail does not reach the crest in one step.

        Above the crest the weir rating is C*(h-crest)^1.5, so the last increment
        decays as h - crest ~ t^-2. The march therefore approaches the saddle
        monotonically and never overshoots it; with 400 x 60 s steps the measured
        end stage is 10.000597 m against a 10 m crest. That is the honest statement,
        not "the lake stops exactly on the crest in one step".
        """
        start = self.lake.capacity_at_spill_m3
        inflow = np.array([3000.0] + [0.0] * 399)
        trace = march_lake(self.lake, inflow, np.full(400, 60.0), initial_volume_m3=start)
        self.assertTrue(trace["ledger_closed"])
        stage = np.asarray(trace["stage_m"])
        self.assertGreater(float(stage[1]), self.lake.spill_level_m)
        self.assertTrue(np.all(np.diff(stage[1:]) <= 0.0))
        self.assertGreaterEqual(float(stage[-1]), self.lake.spill_level_m - 1e-12)
        self.assertLess(float(stage[-1]) - self.lake.spill_level_m, 1e-3)
        self.assertGreater(float(trace["spill_volume_m3"][-1].sum()), 0.0)
        self.assertGreater(float(trace["spill_volume_m3"].sum()), 2900.0)
        self.assertLess(float(trace["spill_volume_m3"].sum()), 3000.0)

    def test_the_store_has_a_declared_top_and_exceeding_it_is_refused(self):
        """The declared head allowance is a hard top: overfilling raises, never clips."""
        start = self.lake.capacity_at_spill_m3
        headroom = self.lake.storage_capacity_m3 - start
        self.assertAlmostEqual(headroom, 45_000.0, places=6)
        with self.assertRaises(ValueError):
            march_lake(self.lake, np.array([1.5 * headroom]), np.array([60.0]),
                       initial_volume_m3=start)
        with self.assertRaises(ValueError):
            march_lake(self.lake, np.array([0.5 * headroom]), np.array([60.0]),
                       initial_volume_m3=self.lake.storage_capacity_m3 + 1.0)

    def test_a_sane_step_keeps_the_pondage_inside_the_declared_top(self):
        start = self.lake.capacity_at_spill_m3
        headroom = self.lake.storage_capacity_m3 - start
        trace = march_lake(self.lake, np.array([0.05 * headroom]), np.array([60.0]),
                           initial_volume_m3=start)
        self.assertTrue(trace["ledger_closed"])
        self.assertLessEqual(float(np.max(trace["volume_m3"])),
                             self.lake.storage_capacity_m3 + 1e-9)
        self.assertGreater(float(trace["spill_volume_m3"].sum()), 0.0)
        self.assertLess(float(trace["spill_volume_m3"].sum()),
                        float(trace["ledger"]["inflow_m3"]))

    def test_no_inflow_means_no_spill_even_at_the_saddle(self):
        start = self.lake.capacity_at_spill_m3
        trace = march_lake(self.lake, np.zeros(3), np.full(3, 60.0), initial_volume_m3=start)
        self.assertTrue(trace["ledger_closed"])
        self.assertEqual(float(trace["spill_volume_m3"].sum()), 0.0)
        self.assertTrue(np.all(np.asarray(trace["stage_m"]) == self.lake.spill_level_m))
        self.assertEqual(float(trace["volume_m3"][-1]), start)

    def test_the_weir_law_is_the_declared_broad_crested_law(self):
        """Property check on the one number that cannot be derived here.

        ``C`` is read from the module's own declared record, so this asserts
        *consistency* with the declared ``Cd * sqrt(2g) * L`` and rejects a rating
        that is silently rescaled; it does not pretend to verify ``Cd`` itself.
        """
        coefficient = float(self.lake.provenance["outlet_coefficient_m3_s_m15"])
        self.assertAlmostEqual(coefficient,
                               DISCHARGE_COEFFICIENT * math.sqrt(2.0 * 9.80665) * SILL_WIDTH_M,
                               places=9)
        outlet = self.lake.outlets[0]
        crest = outlet.crest_stage_m
        self.assertEqual(outlet.discharge_at_stage(crest), 0.0)
        self.assertEqual(outlet.discharge_at_stage(crest - 1.0), 0.0)
        first = outlet.discharge_at_stage(crest + 0.5)
        second = outlet.discharge_at_stage(crest + 1.0)
        self.assertGreater(second, first)
        self.assertAlmostEqual(first, coefficient * 0.5 ** 1.5, places=9)
        self.assertAlmostEqual(second, coefficient * 1.0 ** 1.5, places=9)

    def test_the_loss_terms_name_the_saddle_and_declare_the_rest_absent(self):
        trace = march_lake(self.lake, np.array([float(self.lake.capacity_at_spill_m3)]),
                           np.array([300.0]), initial_volume_m3=0.0)
        losses = trace["loss_terms"]
        self.assertIn("saddle_overflow_m3", losses)
        self.assertIsNone(losses["evaporation_m3"])
        self.assertIsNone(losses["groundwater_m3"])
        self.assertFalse(trace["hydraulic_ready"])
        self.assertFalse(trace["natural_outlet_verified"])
        self.assertFalse(trace["publishable"])

    def test_hostile_forcing_is_refused_by_name(self):
        with self.assertRaises(ValueError):
            march_lake(self.lake, np.array([1.0, -1.0]), np.array([1.0, 1.0]))
        with self.assertRaises(ValueError):
            march_lake(self.lake, np.array([1.0]), np.array([0.0]))
        with self.assertRaises(ValueError):
            march_lake(self.lake, np.array([1.0, 2.0]), np.array([1.0]))
        with self.assertRaises(ValueError):
            march_lake(self.lake, np.array([np.nan]), np.array([1.0]))
        with self.assertRaises(ValueError):
            march_lake(self.lake, np.array([1.0]), np.array([1.0]),
                       initial_volume_m3=self.lake.storage.capacity_m3 + 1.0)
        with self.assertRaises(ValueError):
            march_lake(self.lake, np.zeros(0), np.zeros(0))


# --------------------------------------------------------------------------- #
# S4. refusals: window truncation, unknown upstream, lowlands, water surfaces
# --------------------------------------------------------------------------- #
class RefusalTests(unittest.TestCase):

    def test_a_draining_slope_is_not_a_lake(self):
        lake = build(sloped_lowland(), (10, 10))
        self.assertFalse(lake.certified)
        self.assertEqual(lake.reason_code, REASON_NO_DEPRESSION)
        self.assertFalse(lake.truncated_not_judged)
        self.assertIsNone(lake.storage)
        self.assertEqual(lake.outlets, ())

    def test_a_flat_low_plain_is_not_a_lake(self):
        lake = build(flat_lowland(), (7, 7))
        self.assertFalse(lake.certified)
        self.assertEqual(lake.reason_code, REASON_NO_DEPRESSION)
        self.assertIsNone(lake.storage)

    def test_a_filled_water_surface_is_refused_rather_than_read_as_a_bed(self):
        """Feed the basin's own filled surface back in: it must not certify itself."""
        bed = tied_rim_box()
        filled = reference_priority_flood(bed)
        surface = np.where(filled > bed, filled, bed)
        self.assertTrue((surface > bed).any())
        lake = build(surface, (10, 10))
        self.assertFalse(lake.certified)
        self.assertEqual(lake.reason_code, REASON_NO_DEPRESSION)
        with self.assertRaises(ValueError):
            build(bed, (10, 10), surface_kind=WATER_SURFACE_KINDS[0])
        with self.assertRaises(ValueError):
            build(bed, (10, 10), surface_kind="stage_m")

    def test_a_rim_inside_the_untrusted_band_is_truncated_not_judged(self):
        lake = build(plateau_pit(size=11), (5, 5))
        self.assertFalse(lake.certified)
        self.assertEqual(lake.reason_code, REASON_RIM_IN_BAND)
        self.assertTrue(lake.truncated_not_judged)
        self.assertEqual(lake.basin_cells, 1)
        self.assertIsNone(lake.storage)

    def test_the_same_basin_certifies_in_a_bigger_window(self):
        """The refusal above is about the window, not about the terrain."""
        self.assertFalse(build(plateau_pit(size=11), (5, 5)).certified)
        self.assertTrue(build(plateau_pit(size=15), (7, 7)).certified)
        self.assertTrue(build(plateau_pit(size=41), (20, 20)).certified)

    def test_an_exit_set_inside_the_band_is_truncated_not_judged(self):
        """Rim clear at 6 cells but every exit at 5: refused as a saddle problem."""
        lake = build(plateau_pit(size=13), (6, 6))
        self.assertFalse(lake.certified)
        self.assertEqual(lake.reason_code, REASON_SADDLE_IN_BAND)
        self.assertTrue(lake.truncated_not_judged)
        self.assertGreaterEqual(lake.rim_clearance_cells, CONTACT_MARGIN_CELLS)
        self.assertLess(int(lake.saddle["exit_min_clearance_cells"]), CONTACT_MARGIN_CELLS)

    def test_an_unresolved_cell_refuses_the_whole_window(self):
        bed = tied_rim_box()
        mask = np.ones(bed.shape, bool)
        mask[0, 0] = False
        lake = build_native_30m_lake(
            bed, mask, seed_cell_rc=(10, 10), spacing_m=SPACING_M,
            origin_xz_m=(0., 0.), source_identity_sha256=SOURCE_SHA,
            surface_kind=BED_SURFACE_KIND, sill_width_m=SILL_WIDTH_M,
            discharge_coefficient=DISCHARGE_COEFFICIENT,
            head_allowance_m=HEAD_ALLOWANCE_M)
        self.assertFalse(lake.certified)
        self.assertEqual(lake.reason_code, REASON_WINDOW_UNRESOLVED)
        self.assertTrue(lake.truncated_not_judged)

    def test_a_non_finite_bed_is_refused_before_anything_is_built(self):
        bed = tied_rim_box()
        bed[3, 3] = np.nan
        with self.assertRaises(ValueError):
            build(bed, (10, 10))

    def test_an_unknown_upstream_is_truncated_not_judged(self):
        bed = np.full((31, 31), 40.)
        for row in range(15):
            bed[row, 14:17] = 20. + .5 * (15 - row) + np.array([.1, 0., .1])
        bed[15, 15] = 10.
        bed[16:, 14:17] = np.arange(20., 12.5, -.5)[:, None]
        lake = build(bed, (15, 15), contact_margin_cells=1)
        self.assertFalse(lake.certified)
        self.assertEqual(lake.reason_code, REASON_UPSTREAM_UNKNOWN)
        self.assertTrue(lake.truncated_not_judged)
        self.assertGreater(int(lake.catchment["unknown_cells"]), 0)
        with self.assertRaises(ValueError):
            inflow_volume_m3(lake, produced_depth_m=0.1)

    def test_the_slope_fixture_is_really_a_closed_pit(self):
        """The refusal above must not be a "no depression" in disguise."""
        bed = pit_on_a_slope()
        filled, depth, members = measure_basin(bed, (7, 7))
        self.assertIsNotNone(members)
        self.assertEqual(int(members.sum()), 1)
        self.assertGreater(float(depth[7, 7]), 0.0)
        self.assertAlmostEqual(float(filled[7, 7]), 14.8, places=9)

    def test_a_certified_basin_has_no_unknown_catchment_and_no_leak(self):
        lake = build(plateau_pit(size=41), (20, 20))
        self.assertTrue(lake.certified)
        self.assertEqual(int(lake.catchment["unknown_cells"]), 0)
        self.assertEqual(int(lake.catchment["leaked_cells"]), 0)
        mesh = grid_mesh(lake.basin_mask.shape, dx_m=SPACING_M)
        pit = 20 * 41 + 20
        self.assertEqual(int(lake.catchment["contributing_cells"]),
                         1 + int(mesh.indptr[pit + 1] - mesh.indptr[pit]))
        self.assertEqual(lake.basin_cells, 1)

    def test_the_catchment_is_the_independent_upstream_walk(self):
        """Rebuild strict metric graph slopes independently and compare the walk."""
        bed = np.full((31, 31), 40.0)
        bed[15, 15] = 34.0
        for row in range(6, 26):
            bed[row, 15] = 38.0 - abs(row - 15) * 0.05
        rows, columns = bed.shape
        independent_receiver = np.full(bed.shape, -1, np.int64)
        mesh = grid_mesh(bed.shape, dx_m=SPACING_M)
        for row in range(1, rows - 1):
            for column in range(1, columns - 1):
                best, target = 0.0, -1
                cell = row * columns + column
                for edge in range(mesh.indptr[cell], mesh.indptr[cell + 1]):
                    nxt = int(mesh.indices[edge])
                    slope = (bed[row, column] - bed.ravel()[nxt]) / mesh.edge_length_m[edge]
                    if slope > best:
                        best, target = slope, divmod(nxt, columns)
                if target != -1:
                    independent_receiver[row, column] = target[0] * columns + target[1]
        donors = {}
        for row in range(rows):
            for column in range(columns):
                target = int(independent_receiver[row, column])
                if target >= 0:
                    donors.setdefault(target, []).append(row * columns + column)
        _, _, members = measure_basin(bed, (15, 15))
        self.assertIsNotNone(members)
        seeds = [row * columns + column for row in range(rows) for column in range(columns)
                 if independent_receiver[row, column] < 0 and members[row, column]]
        # the fixture's basin is a 20-cell channel with two raw minima on it, so the
        # independent walk starts from both; counting them here keeps the fixture honest
        self.assertEqual(len(seeds), 2)
        self.assertEqual(int(members.sum()), 20)
        reached = set(seeds)
        stack = list(seeds)
        while stack:
            cell = stack.pop()
            for donor in donors.get(cell, ()):
                if donor not in reached:
                    reached.add(donor)
                    stack.append(donor)
        independent_mask = np.zeros(bed.shape, bool)
        for cell in reached:
            independent_mask[divmod(cell, columns)] = True
        record = basin_catchment(bed, members)
        np.testing.assert_array_equal(np.asarray(record["catchment_mask"]), independent_mask)
        self.assertEqual(record["contributing_cells"], len(reached))
        self.assertEqual(record["leaked_cells"], 0)

    def test_a_basin_that_touches_the_whole_window_is_refused(self):
        """A basin whose rim is the window border cannot have a *provable* exit.

        The 7x7 pit inside a 5 m plateau leaves a one-cell clear ring, so the first
        refusal it can produce is the trusted-band one -- reported here rather than
        assumed. Its exit set exists but lies on the window border.
        """
        bed = np.full((9, 9), 5.0)
        bed[1:-1, 1:-1] = 1.0
        filled = reference_priority_flood(bed)
        members = reference_component(bed, filled, (4, 4))
        record = lowest_saddle(bed, filled, members, float(filled[members].max()))
        self.assertTrue(record["present"])
        self.assertEqual(int(record["exit_min_clearance_cells"]), 0)
        # The fixed check order puts the trusted band before the catchment, so with the
        # repository's 6-cell band this basin is refused for its rim; at a 0-cell band
        # the *first* failing check becomes the undeclared upstream, because the exit
        # set lies on the window border. Both are reported, neither is judged.
        strict = build(bed, (4, 4), contact_margin_cells=CONTACT_MARGIN_CELLS)
        self.assertFalse(strict.certified)
        self.assertEqual(strict.reason_code, REASON_RIM_IN_BAND)
        self.assertEqual(strict.rim_clearance_cells, 1)
        loose = build(bed, (4, 4), contact_margin_cells=0)
        self.assertFalse(loose.certified)
        self.assertEqual(loose.reason_code, REASON_UPSTREAM_UNKNOWN)
        self.assertTrue(loose.truncated_not_judged)


# --------------------------------------------------------------------------- #
# S5. the lake / puddle gate is a second ledger and is never merged
# --------------------------------------------------------------------------- #
class GateSeparationTests(unittest.TestCase):

    def test_a_certified_basin_can_still_be_refused_by_the_gate(self):
        lake = build(plateau_pit(size=41), (20, 20), produced_depth_m=50.0)
        self.assertTrue(lake.certified)
        gate = lake.provenance["gate"]
        self.assertEqual(gate["verdict"], "pass_through")
        self.assertTrue(lake.certified, "the gate must not change certification")
        self.assertEqual(lake.provenance["relief_m"], 10.0)

    def test_the_gate_accepts_a_deep_basin_at_a_small_storm(self):
        lake = build(deep_bowl(), (30, 30), produced_depth_m=0.04, contact_margin_cells=6)
        self.assertTrue(lake.certified, lake.reason_code)
        gate = lake.provenance["gate"]
        self.assertEqual(gate["verdict"], "lake")
        self.assertFalse(gate["growth_evaluated"])
        self.assertEqual(gate["convergence_gate"], "single_window_only")
        self.assertEqual(gate["inflow_quantity"], "unfilled_catchment_production")

    def test_no_gate_is_computed_without_a_declared_storm(self):
        self.assertNotIn("gate", build(tied_rim_box(), (10, 10)).provenance)

    def test_the_record_carries_units_tolerances_and_budgets(self):
        record = build(tied_rim_box(), (10, 10)).as_record()
        self.assertEqual(record["units"], UNITS)
        self.assertEqual(record["tolerances"], TOLERANCES)
        self.assertEqual(record["budgets"], BUDGETS)
        self.assertEqual(record["schema"], SCHEMA)
        self.assertEqual(record["algorithm"], ALGORITHM)
        self.assertFalse(record["hydraulic_ready"])
        self.assertFalse(record["natural_outlet_verified"])
        self.assertFalse(record["publishable"])
        self.assertEqual(record["spill_level_m"], 10.0)
        self.assertEqual(record["capacity_at_spill_m3"], 157_500.0)

    def test_a_refused_record_serialises_without_nan(self):
        payload = json.dumps(build(sloped_lowland(), (10, 10)).as_record(), allow_nan=False)
        self.assertIn(REASON_NO_DEPRESSION, payload)
        self.assertNotIn("NaN", payload)
        self.assertNotIn("Infinity", payload)


# --------------------------------------------------------------------------- #
# S6. internal consistency
# --------------------------------------------------------------------------- #
class ConsistencyTests(unittest.TestCase):

    def test_a_certified_lake_passes_its_own_validator(self):
        self.assertTrue(validate_native_30m_lake(build(cone_bowl(), (15, 15))))

    def test_a_refused_lake_passes_its_own_validator(self):
        self.assertTrue(validate_native_30m_lake(build(sloped_lowland(), (10, 10))))

    def test_the_validator_rejects_a_storeless_certified_lake(self):
        lake = build(tied_rim_box(), (10, 10))
        half = Native30mLake(
            certified=True, reason_code=REASON_CERTIFIED,
            seed_row_column=lake.seed_row_column, spacing_m=lake.spacing_m,
            cell_area_m2=lake.cell_area_m2, basin_mask=lake.basin_mask,
            basin_cells=lake.basin_cells, basin_area_m2=lake.basin_area_m2,
            bed_min_m=lake.bed_min_m, spill_level_m=lake.spill_level_m,
            rim_clearance_cells=lake.rim_clearance_cells, saddle=lake.saddle,
            catchment=lake.catchment, storage=None, outlets=lake.outlets,
            head_allowance_m=lake.head_allowance_m)
        with self.assertRaises(ValueError):
            validate_native_30m_lake(half)

    def test_a_refused_lake_cannot_be_marched(self):
        lake = build(sloped_lowland(), (10, 10))
        with self.assertRaises(ValueError):
            march_lake(lake, np.array([1.0]), np.array([1.0]))
        with self.assertRaises(ValueError):
            initial_volume_m3(lake, initial_stage_m=1.0)
        with self.assertRaises(ValueError):
            validate_native_30m_lake("not a lake")

    def test_reason_codes_are_declared_and_distinct(self):
        import terrain_pipeline.lake as module
        codes = list(module.REASON_CODES)
        self.assertEqual(len(codes), len(set(codes)))
        for reason in module.TRUNCATION_REASONS:
            self.assertIn(reason, codes)
        self.assertNotIn(REASON_CERTIFIED, module.TRUNCATION_REASONS)
        self.assertNotIn(REASON_NO_DEPRESSION, module.TRUNCATION_REASONS)

    def test_lowest_saddle_reports_the_constancy_and_the_rejected_number(self):
        bed = cone_bowl()
        bed[10, 10] = 110.0
        filled = reference_priority_flood(bed)
        members = reference_component(bed, filled, (15, 15))
        spill = float(filled[members].max())
        record = lowest_saddle(bed, filled, members, spill)
        self.assertTrue(record["present"])
        self.assertAlmostEqual(record["flood_level_constancy_m"], 0.0, places=12)
        self.assertAlmostEqual(record["geometric_minus_spill_m"],
                               float(record["geometric_rim_minimum_m"]) - spill, places=9)
        self.assertGreaterEqual(record["geometric_minus_spill_m"], 0.0)
        self.assertEqual(record["rim_cells"], int(reference_rim(members).sum()))

    def test_the_margin_is_read_from_the_repository_constant(self):
        self.assertEqual(CONTACT_MARGIN_CELLS, 6)
        lake = build(tied_rim_box(), (10, 10))
        self.assertEqual(int(lake.provenance["contact_margin_cells"]), CONTACT_MARGIN_CELLS)


# --------------------------------------------------------------------------- #
# S7. recorded gaps: asserted, never relaxed
# --------------------------------------------------------------------------- #
class RecordedGapTests(unittest.TestCase):
    """Places where the mechanism is knowingly weaker than a certification.

    Each test asserts the *limitation itself*, so the gap stays visible in the suite
    instead of living in a report nobody re-runs.
    """

    def test_the_flood_level_constancy_guard_is_unreachable_from_a_sound_flood(self):
        """GAP 1: ``REASON_FILL_NOT_CONSTANT`` is a unit guard, not a live outcome.

        ``depression_hierarchy`` returns one level per closed depression, so the
        constancy check cannot fire on any bed this module accepts. It is kept because
        a future flood implementation could change that; it is asserted here as
        unreachable today, rather than presented as a measured result.
        """
        bed = tied_rim_box()
        lake = build(bed, (10, 10))
        self.assertNotEqual(lake.reason_code, REASON_FILL_NOT_CONSTANT)
        self.assertNotEqual(lake.reason_code, REASON_SADDLE_ABSENT)
        self.assertNotEqual(lake.reason_code, REASON_MEMBERSHIP_LEAK)
        filled = reference_priority_flood(bed)
        members = reference_component(bed, filled, (10, 10))
        self.assertEqual(float(filled[members].max() - filled[members].min()), 0.0)

    def test_consistent_graph_shelf_membership_has_no_raw_catchment_leak(self):
        """Consistent graph connectivity keeps a separate shelf pit outside this lake."""
        bed = cone_bowl()
        bed[10, 10] = 108.0
        lake = build(bed, (15, 15))
        self.assertTrue(lake.certified, lake.reason_code)
        self.assertFalse(lake.basin_mask[10, 10])
        self.assertEqual(int(lake.catchment["leaked_cells"]), 0)

    def test_the_march_does_not_solve_a_common_stage_across_basins(self):
        """GAP 3: one lake at a time; a two-lake connected stage is out of scope.

        ``march_lake`` marches a single certified basin through the existing sill-lake
        march. Two basins sharing a stage (``metric_natural_lakes``' signed internal
        weirs) is a *different* mechanism and is not exposed here. Stated as a
        property of the API, so no reader assumes a network solve.
        """
        lake = build(tied_rim_box(), (10, 10))
        trace = march_lake(lake, np.array([1.0]), np.array([60.0]))
        self.assertEqual(trace["spill_volume_m3"].shape, (1, 1))
        self.assertEqual(len(lake.outlets), 1)
        self.assertNotIn("wet_component", trace)
        self.assertNotIn("internal_transfer_m3", trace)

    def test_evaporation_and_groundwater_are_declared_absent_not_zero(self):
        """GAP 4: the level pool's only loss is the saddle; the rest is None."""
        lake = build(tied_rim_box(), (10, 10))
        trace = march_lake(lake, np.array([1.0]), np.array([60.0]))
        self.assertIsNone(trace["loss_terms"]["evaporation_m3"])
        self.assertIsNone(trace["loss_terms"]["groundwater_m3"])
        self.assertIn("not modelled", trace["loss_terms"]["policy"])

    def test_the_saddle_weir_width_is_a_declaration_not_a_measurement(self):
        """GAP 5: the weir width is declared; the exit *count* is measured.

        The saddle is a cell set, not a surveyed sill: its width comes from the
        caller. What the module can prove is how many cells are in the exit set and
        how far the nearest one is from the window border.
        """
        lake = build(tied_rim_box(), (10, 10))
        self.assertAlmostEqual(float(lake.provenance["sill_width_m"]), SILL_WIDTH_M,
                               places=12)
        self.assertEqual(int(lake.saddle["exit_cells"]), int(reference_rim(lake.basin_mask).sum()))
        self.assertIn("border", lake.outlets[0].provenance)


if __name__ == "__main__":
    unittest.main()
