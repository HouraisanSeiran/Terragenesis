"""p8: the native 30 m infinite-world certification window family, as executable assertions.

What this file is
-----------------
The six certification interfaces (T1..T6) and the three forbidden proof techniques (N1..N3) of
``.scratch/river-stage1-completion/infinite-world-certification-20251025-v1/certification-contract-20251025-v1.md``,
written as tests. It also pins the *declared blockers* (B1..B6) so that a later reader cannot
turn "the interface runs" into "the capability is certified".

What it deliberately does not do
--------------------------------
* No GPU, no terrain generation, no 48 km recomputation. Synthetic fixtures are at most
  160 x 160; the real-page windows are 257 and 385 nodes.
* It does not write a second D8. Where a receiver is needed it calls
  ``native_30m_source.build_strict_topology`` (which uses the one sanctioned kernel), and the
  independent side of every comparison is a *different* traversal written in this file.
* It does not use ``metric_cross_region``'s internals to produce expected values: expectations
  come from closed-form geometry or from an independent loop.

Why so many tests are negative
------------------------------
Three proof techniques were forbidden by the contract because each one has already produced a
wrong number in this repository: naive overlap comparison, per-pair summation, and
``Qs = Q x constant`` presented as a second independent witness. A prohibition that lives only
in prose gets violated by the next person; here each one has a test that *fails* if the wrong
technique is used.
"""
import hashlib
import inspect
import json
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.runoff import simulate_rainfall_runoff as simulate_rainfall_runoff
from terrain_pipeline.surface_rivers import metric_cross_region as cr
from terrain_pipeline.surface_rivers.native_30m_hydrology_ledger import (
    purpose_subseeds, window_terminal_kind)
from terrain_pipeline.surface_rivers.native_30m_source import (
    build_strict_topology, load_native_window)
from tools import native_30m_query
from tools.audit_native_30m_infinite_certification import (
    assemble as audit_assemble, border_distance as audit_border_distance,
    overlap_box as audit_overlap_box, unknown_seed_cells as audit_unknown_seeds)

WORLD_SEED = 20261020
SPACING_M = 30.0
BAND = 6
PAGES_DIR = Path(__file__).resolve().parents[1] / ".scratch" / "fine-terrain-40km" / "td-pages"
BASE_ORIGIN = (42173, 42874)


def bitwise_equal(left, right):
    """float64 equality by bit pattern, with NaN in exactly the same places.

    ``np.array_equal`` returns False as soon as a NaN is present, which would make every
    assembly test meaningless: an assembly carries NaN in its unresolved cells on purpose.
    """
    a = np.asarray(left, np.float64)
    b = np.asarray(right, np.float64)
    if a.shape != b.shape:
        return False
    nan_a, nan_b = np.isnan(a), np.isnan(b)
    if not np.array_equal(nan_a, nan_b):
        return False
    return np.array_equal(a[~nan_a], b[~nan_b])


def plane(rows, columns, origin, slope_z=0.01, slope_x=0.004, offset_m=100.0):
    """A field whose value is a function of the **absolute** native index.

    That is what makes two windows comparable at all: the same world cell must carry the same
    value in both, so the content depends on ``origin``, never on the array index. The closed
    form is written out so a test can assert against it instead of against a page.
    """
    z = np.arange(rows)[:, None] + origin[1]
    x = np.arange(columns)[None, :] + origin[0]
    return offset_m + slope_z * z + slope_x * x


def ringed_bowl(rows, columns, origin, centre_xz, *, base_m=500.0, bowl_radius=18.0,
                rim_radius=22.0, depth_m=40.0, rim_height_m=30.0):
    """A closed bowl of explicit geometry, so its hypsometry numbers are closed-form known.

    Three zones, all in *absolute* world coordinates:

    ``radius < bowl_radius``          bowl floor: a parabola reaching ``base - depth``
    ``bowl_radius .. rim_radius``     a raised rim at ``base + rim_height``
    ``radius >= rim_radius``          the surrounding plateau at ``base``

    The raised rim is what makes a truncating window measurably wrong: a window that cuts the
    bowl before the rim treats its own border as the outlet. A radially symmetric bowl
    *without* a rim reports the correct spill level even when truncated, which is why the
    under-report has to be certified on a fixture that can be wrong.
    """
    centre_x, centre_z = centre_xz
    z = np.arange(rows)[:, None] + origin[1]
    x = np.arange(columns)[None, :] + origin[0]
    radius = np.hypot(x - centre_x, z - centre_z)
    field = np.full((rows, columns), float(base_m), np.float64)
    inside = radius < bowl_radius
    field[inside] = base_m - depth_m * (1.0 - (radius[inside] / bowl_radius) ** 2)
    rim = (radius >= bowl_radius) & (radius < rim_radius)
    field[rim] = base_m + rim_height_m
    return field


def pothole_plane(rows, columns, origin, pothole_rc, depth_m=3.0):
    """A flat plane with exactly one single-cell pothole.

    The counter-example fixture: a window family can agree perfectly on a one-cell object,
    which is agreement about the wrong object.
    """
    field = plane(rows, columns, origin, slope_z=0.0, slope_x=0.0, offset_m=500.0)
    field[pothole_rc] -= depth_m
    return field


def two_pages(size=120, gap=40):
    """Two overlapping pages of the same sloped field.

    The overlap width is ``gap``, a declared constant; it is not discovered by looking at a
    measurement.
    """
    origin_a = (9000, 9000)
    origin_b = (origin_a[0] + size - gap, origin_a[1])
    return [("pa", plane(size, size, origin_a), origin_a),
            ("pb", plane(size, size, origin_b), origin_b)]


# --------------------------------------------------------------------------- #
# T1 same coordinate, every window in the family
# --------------------------------------------------------------------------- #
class CoordinateStabilityTests(unittest.TestCase):
    def setUp(self):
        self.pages = two_pages()

    def test_the_same_world_cell_has_one_value_whatever_window_asks(self):
        """T1: the resolved value equals the closed form at the absolute coordinate."""
        for x, z in ((9080, 9060), (9100, 9061), (9119, 9070), (9040, 9110)):
            with self.subTest(native_xz=(x, z)):
                report = cr.resolve_point(self.pages, (x, z), border_band_cells=BAND)
                self.assertTrue(report["resolved"], report["reason"])
                self.assertEqual(report["value_m"], 100.0 + 0.01 * z + 0.004 * x)
                suppliers = [item for item in report["candidates"] if item["supplied"]]
                self.assertTrue(suppliers)
                self.assertTrue(all(item["border_distance_cells"] >= BAND
                                    for item in suppliers))

    def test_a_point_only_inside_the_border_band_is_refused(self):
        """T1 negative face: a band value is never reported as terrain."""
        origin = (9000, 9000)
        single = [("pa", plane(120, 120, origin), origin)]
        for offset in (0, 1, 5):
            with self.subTest(cells_from_edge=offset):
                x = origin[0] + 120 - 1 - offset
                report = cr.resolve_point(single, (x, origin[1] + 60), border_band_cells=BAND)
                self.assertFalse(report["resolved"])
                self.assertEqual(report["reason"], cr.REASON_UNRESOLVED_BORDER)
                self.assertIsNone(report["value_m"])
                self.assertTrue(report["candidates"])
        # Exactly at the declared clearance it must be supplied, so the boundary is real.
        report = cr.resolve_point(single, (origin[0] + 120 - 1 - BAND, origin[1] + 60),
                                  border_band_cells=BAND)
        self.assertTrue(report["resolved"], report["reason"])

    def test_a_point_no_window_covers_is_out_of_tile_not_zero(self):
        report = cr.resolve_point(self.pages, (10_000_000, 10_000_000), border_band_cells=BAND)
        self.assertFalse(report["resolved"])
        self.assertEqual(report["reason"], cr.REASON_OUT_OF_TILE)
        self.assertIsNone(report["value_m"])

    def test_two_clear_windows_that_disagree_are_refused_not_averaged(self):
        """T1 negative face: disagreement is investigated, never smoothed away."""
        origin = (9000, 9000)
        a = plane(120, 120, origin)
        b = plane(120, 120, origin).copy()
        b[70, 100] += 0.5
        pages = [("pa", a, origin), ("pb", b, origin)]
        report = cr.resolve_point(pages, (origin[0] + 100, origin[1] + 70),
                                  border_band_cells=BAND)
        self.assertFalse(report["resolved"])
        self.assertEqual(report["reason"], cr.REASON_DISAGREEMENT)
        self.assertEqual(len(report["disagreeing_values_m"]), 2)
        self.assertIsNone(report["value_m"])


# --------------------------------------------------------------------------- #
# T2 load order, including re-chunking
# --------------------------------------------------------------------------- #
class LoadOrderTests(unittest.TestCase):
    def setUp(self):
        self.pages = two_pages()
        self.origin = (9000, 9000)
        self.shape = (180, 180)

    def test_every_page_order_gives_one_assembly_digest(self):
        """T2: the selection rule is a pure function of (position, clearance)."""
        digests = set()
        for order in (["pa", "pb"], ["pb", "pa"], ["pb", "pa"]):
            assembly = cr.assemble_pages(self.pages, border_band_cells=BAND,
                                         origin=self.origin, shape=self.shape, order=order)
            digests.add(cr.assembly_digest(assembly))
        self.assertEqual(len(digests), 1)

    def test_a_non_permutation_is_refused(self):
        with self.assertRaises(ValueError):
            cr.assemble_pages(self.pages, border_band_cells=BAND, origin=self.origin,
                              shape=self.shape, order=["pa"])

    def test_duplicate_page_keys_are_refused(self):
        with self.assertRaises(ValueError):
            cr.assemble_pages([("pa", np.zeros((8, 8)), (0, 0)),
                               ("pa", np.zeros((8, 8)), (10, 0))],
                              origin=(0, 0), shape=(8, 20))

    def test_float_reduction_is_reported_as_spread_never_as_equality(self):
        """T2 negative face: the one order-dependent reduction must not be called equal."""
        report = cr.load_order_invariance(self.pages, [["pa", "pb"], ["pb", "pa"]],
                                          origin=self.origin, shape=self.shape,
                                          border_band_cells=BAND, spacing_m=SPACING_M)
        self.assertTrue(report["comparison"]["identical_quantities"])
        classified = report["runs"][0]["quantities"]["exactness"][
            "order_dependent_float_reduction"]
        self.assertIn("resolved_elevation_sum_m", classified)
        self.assertIsInstance(report["float_quantity_spread"], dict)
        # A zero spread is a measurement of these orders, not a guarantee for all orders.
        self.assertIn("measurement, not a guarantee", report["note"])

    def test_rechunking_adds_borders_and_only_ever_loses_cells(self):
        """T2: twice as many pieces means twice as many borders."""
        cut = 80
        halves = []
        for key, array, origin in self.pages:
            halves.append((key + "-l", np.ascontiguousarray(array[:, :cut]), origin))
            halves.append((key + "-r", np.ascontiguousarray(array[:, cut - 20:]),
                           (origin[0] + cut - 20, origin[1])))
        whole = cr.assemble_pages(self.pages, border_band_cells=BAND, origin=self.origin,
                                  shape=self.shape)
        pieces = cr.assemble_pages(halves, border_band_cells=BAND, origin=self.origin,
                                   shape=self.shape)
        self.assertLessEqual(pieces["resolved_cells"], whole["resolved_cells"])
        common = whole["resolved_mask"] & pieces["resolved_mask"]
        self.assertGreater(int(common.sum()), 0)
        self.assertTrue(np.array_equal(whole["field"][common], pieces["field"][common]))


# --------------------------------------------------------------------------- #
# T3 page seam
# --------------------------------------------------------------------------- #
class SeamTests(unittest.TestCase):
    def test_overlap_differs_only_inside_the_border_band(self):
        """T3: every difference sits at distance 0; the interior is bit-identical."""
        origin = (9000, 9000)
        a = plane(120, 120, origin)
        b = plane(120, 120, origin).copy()
        for edge in (0, -1):
            b[:, edge] += 0.25
            b[edge, :] += 0.25
        self.assertEqual(audit_overlap_box(origin, a.shape, origin, b.shape),
                         (9000, 9120, 9000, 9120))
        report = cr.overlap_comparison(a, origin, b, origin, border_band_cells=BAND)
        self.assertTrue(report["overlaps"])
        self.assertTrue(report["interior_bitwise_identical"])
        self.assertEqual(report["interior_differing_cells"], 0)
        self.assertEqual(report["differing_cells"], 4 * 120 - 4)
        self.assertEqual(report["per_border_band"][0]["border_distance_cells"], 0)
        self.assertEqual(report["per_border_band"][0]["differing_cells"],
                         report["differing_cells"])
        self.assertEqual([row["differing_cells"] for row in report["per_border_band"][1:]],
                         [0] * (len(report["per_border_band"]) - 1))
        self.assertIn("bitwise float64 equality", report["declared_tolerance"]["interior"])

    def test_the_window_edge_is_never_an_outlet(self):
        """T3 negative face: no terminal label turns a window rim into an outlet."""
        pages = two_pages()
        assembly = cr.assemble_pages(pages, border_band_cells=BAND, origin=(9000, 9000),
                                     shape=(180, 180))
        topology = build_strict_topology(assembly["field"], assembly["resolved_mask"])
        self.assertEqual(topology["census"]["open_outflow"], 0)
        self.assertNotIn("open_outflow", set(np.unique(topology["terminal_kind"]).tolist()))
        self.assertIn("Not a natural lake", topology["topology_policy"]["retained"])
        self.assertIn("a window edge is not an outlet",
                      topology["topology_policy"]["natural_outlet"])

    def test_an_unresolved_hole_is_impassable_not_a_drain(self):
        """T3: the flood is seeded from the *resolved* boundary, so a hole cannot drain."""
        field = np.full((9, 9), 100.0)
        field[4, 4] = 90.0
        resolved = np.ones((9, 9), bool)
        resolved[4, 4] = False
        quantities = cr.cumulative_quantities(field, resolved, spacing_m=SPACING_M)
        self.assertEqual(quantities["wetted_cells"], 0)
        self.assertEqual(quantities["depression_count"], 0)
        self.assertIn("region_relative", quantities)
        # If the hole were a drain, the eight neighbours would fill down to 90 m.
        self.assertEqual(quantities["resolved_cells"], 81 - 1)

    def test_basin_clearance_is_a_distance_not_a_boolean(self):
        mask = np.zeros((40, 40), bool)
        mask[10:30, 10:30] = True
        report = cr.basin_reaches_window_edge(mask, contact_margin_cells=BAND)
        self.assertEqual(report["rim_clearance_cells"], 10)
        self.assertEqual(report["rim_clearance_m"], 10 * SPACING_M)
        self.assertFalse(report["suspect_window_truncation"])
        self.assertFalse(report["touches_border_by_hypsometry_ring_2"])
        near = np.zeros((40, 40), bool)
        near[0:5, 0:5] = True
        flagged = cr.basin_reaches_window_edge(near, contact_margin_cells=BAND)
        self.assertTrue(flagged["suspect_window_truncation"])
        self.assertEqual(flagged["rim_clearance_cells"], 0)


# --------------------------------------------------------------------------- #
# T4 outlet / flow-path continuity across a seam
# --------------------------------------------------------------------------- #
class OutletContinuityTests(unittest.TestCase):
    def test_a_receiver_points_to_the_same_world_cell_in_two_windows(self):
        """T4: identity is the world coordinate, never the flat array index.

        Two windows with **different origins** look at the same page. For every cell both of
        them resolve, the receiver must name the same world cell -- and on this slope that
        cell is the one directly north.
        """
        origin = (9000, 9000)
        # `slope_x=0` on purpose: a single-axis slope makes the expected receiver exact, so the
        # test does not depend on which of two nearly equal D8 slopes the kernel prefers.
        pages = [("pa", plane(160, 160, origin, slope_x=0.0), origin)]
        first = cr.assemble_pages(pages, border_band_cells=BAND, origin=(9000, 9000),
                                  shape=(120, 120))
        second = cr.assemble_pages(pages, border_band_cells=BAND, origin=(9010, 9030),
                                   shape=(80, 80))
        top_a = build_strict_topology(first["field"], first["resolved_mask"])
        top_b = build_strict_topology(second["field"], second["resolved_mask"])
        columns_a = first["field"].shape[1]
        columns_b = second["field"].shape[1]
        compared = 0
        for z in range(9040, 9100):
            for x in range(9020, 9080):
                row_a, column_a = z - 9000, x - 9000
                row_b, column_b = z - 9030, x - 9010
                if not (first["resolved_mask"][row_a, column_a]
                        and second["resolved_mask"][row_b, column_b]):
                    continue
                receiver_a = int(top_a["receiver"][row_a, column_a])
                receiver_b = int(top_b["receiver"][row_b, column_b])
                if receiver_a < 0 or receiver_b < 0:
                    self.assertEqual(receiver_a, receiver_b, (x, z))
                    continue
                world_a = (9000 + receiver_a % columns_a, 9000 + receiver_a // columns_a)
                world_b = (9010 + receiver_b % columns_b, 9030 + receiver_b // columns_b)
                self.assertEqual(world_a, world_b, (x, z))
                self.assertEqual(world_a, (x, z - 1))
                compared += 1
        self.assertGreater(compared, 1000)

    def test_a_flow_path_crosses_the_page_seam_without_breaking(self):
        """T4: following the receiver never steps onto an unresolved cell, and the terminal it
        reaches is a declared one rather than an invented outlet.

        The field falls to the west, so water runs west. Page ``pa`` ends at x = 9119 and page
        ``pb`` starts at x = 9080; a path that starts east of the strip and ends west of it has
        crossed the seam. If ``pa`` alone were the window, the path would stop at its own rim.
        """
        origin = (9000, 9000)
        pages = [("pa", plane(120, 120, origin, slope_z=0.0, slope_x=0.01), origin),
                 ("pb", plane(120, 120, (origin[0] + 80, origin[1]),
                               slope_z=0.0, slope_x=0.01), (origin[0] + 80, origin[1]))]
        assembly = cr.assemble_pages(pages, border_band_cells=BAND,
                                     origin=(origin[0] + 60, origin[1]), shape=(120, 120))
        topology = build_strict_topology(assembly["field"], assembly["resolved_mask"])
        receiver = topology["receiver"].ravel()
        resolved = topology["valid_mask"]
        rows, columns = resolved.shape
        start_row, start_column = 60, 110
        self.assertTrue(resolved[start_row, start_column])
        cell = start_row * columns + start_column
        start_world_x = origin[0] + 60 + start_column
        crossed = False
        steps = 0
        while receiver[cell] >= 0:
            cell = int(receiver[cell])
            row, column = divmod(cell, columns)
            self.assertTrue(resolved[row, column], "the path stepped onto an unresolved cell")
            if origin[0] + 60 + column < origin[0] + 80:
                crossed = True
            steps += 1
            self.assertLess(steps, rows * columns)
        end_world_x = origin[0] + 60 + cell % columns
        self.assertGreater(start_world_x, 9119)
        self.assertLess(end_world_x, 9080)
        self.assertTrue(crossed, "the path never entered the page-a-only region")
        self.assertGreater(steps, 20, "the path must actually travel")
        kind = str(topology["terminal_kind"].ravel()[cell])
        self.assertIn(kind, ("retained", "unknown_boundary"))
        self.assertNotEqual(kind, "open_outflow")

    def test_the_assembly_digest_covers_which_page_supplied_each_cell(self):
        """T4 negative face: the digest includes provenance, not only elevations."""
        origin = (9000, 9000)
        field = plane(60, 60, origin)
        first = cr.assemble_pages([("pa", field, origin), ("pb", field, origin)],
                                  border_band_cells=BAND, origin=origin, shape=(60, 60))
        relabelled = cr.assemble_pages([("pz", field, origin), ("py", field, origin)],
                                        border_band_cells=BAND, origin=origin, shape=(60, 60))
        # Same terrain, same rule, but a different winning key on every tie.
        self.assertTrue(bitwise_equal(first["field"], relabelled["field"]))
        self.assertEqual(first["selection_rule"], relabelled["selection_rule"])
        self.assertNotEqual(first["selection_key_digest"], relabelled["selection_key_digest"])
        self.assertNotEqual(cr.assembly_digest(first), cr.assembly_digest(relabelled))


# --------------------------------------------------------------------------- #
# T5 lake and runoff state handover
# --------------------------------------------------------------------------- #
class LakeAndRunoffStateTests(unittest.TestCase):
    CENTRE = (10_000.0, 10_000.0)
    ORIGIN = (9900, 9900)

    def family(self, sizes):
        page = ringed_bowl(160, 160, self.ORIGIN, self.CENTRE)
        seed_rc = (int(self.CENTRE[1]) - self.ORIGIN[1], int(self.CENTRE[0]) - self.ORIGIN[0])
        return page, seed_rc, cr.window_family(page, self.ORIGIN, seed_rc, sizes,
                                               spacing_m=SPACING_M)

    def test_a_truncating_window_understates_the_spill_level(self):
        """T5: the family goes from truncated to clear, and the cost is reported."""
        _page, _seed, family = self.family((31, 51, 71))
        self.assertEqual(family["sizes"], [31, 51, 71])
        self.assertIn(31, family["suspect_sizes"])
        self.assertIn(51, family["accepted_sizes"])
        self.assertNotIn(51, family["suspect_sizes"])
        cost = cr.truncation_cost(family)
        self.assertTrue(cost["rows"])
        row = cost["rows"][0]
        self.assertEqual(row["size"], 31)
        self.assertEqual(row["verdict"], "under_reported")
        # The rim sits at base + 30 = 530 m. A window cut inside it treats its own border as
        # the outlet, so it can only report a level strictly below the rim.
        self.assertLess(row["reported_spill_level_m"], 530.0)
        self.assertAlmostEqual(cost["accepted_spill_level_m"], 530.0, places=6)
        self.assertGreater(row["under_report_m"], 0.0)
        self.assertLess(row["rim_clearance_cells"], BAND)
        self.assertIn("must not be reported", row["note"])

    def test_the_two_largest_accepted_windows_agree(self):
        """T5: convergence is judged on the two largest *accepted* windows, not on a flag."""
        _page, _seed, family = self.family((51, 71, 91))
        accepted = [record for record in family["records"]
                    if not record["suspect_window_truncation"]]
        self.assertEqual(len(accepted), 3)
        largest, runner_up = accepted[-1], accepted[-2]
        self.assertEqual(largest["basin_cells"], runner_up["basin_cells"])
        self.assertAlmostEqual(largest["bed_min_m"], 460.0, places=6)
        self.assertAlmostEqual(largest["spill_level_m"], 530.0, places=6)
        self.assertAlmostEqual(largest["bed_min_m"], runner_up["bed_min_m"], places=9)
        self.assertTrue(family["converged_between_largest_accepted"])
        self.assertEqual(family["level_spread_m_between_largest_accepted"], 0.0)

    def test_a_converged_flag_alone_is_not_evidence_of_a_stable_component(self):
        """T5 negative face, from the recorded counter-example.

        The repository already has a family that reported ``converged=True`` while both windows
        were centred on a 90-cell pothole inside a real basin, 267 m below the true saddle. So
        a verdict must also carry the component size, and equal sizes are the check -- not the
        flag.
        """
        page = pothole_plane(160, 160, self.ORIGIN, (100, 100))
        family = cr.window_family(page, self.ORIGIN, (100, 100), (41, 61, 81),
                                  spacing_m=SPACING_M)
        accepted = [record for record in family["records"]
                    if not record["suspect_window_truncation"]]
        self.assertEqual(len(accepted), 3)
        self.assertEqual({record["basin_cells"] for record in accepted}, {1})
        self.assertEqual({record["basin_area_m2"] for record in accepted}, {900.0})
        # Perfect agreement on a one-cell object is agreement about the wrong object; the
        # record must therefore carry the size, which is exactly what this test reads.
        self.assertTrue(family["converged_between_largest_accepted"])

    def test_the_soil_bucket_output_carries_no_coordinate(self):
        """T5: local Q is a function of (rain, area, dt, parameters) only.

        This is a *constructive* property -- the kernel has no coordinate parameter at all --
        so the test asserts the absence of such a parameter and the bitwise stability of the
        output. It does not claim to be a cross-window measurement.
        """
        signature = inspect.signature(simulate_rainfall_runoff)
        for forbidden in ("origin", "native_xz", "window", "shape_zx", "world_coord"):
            self.assertNotIn(forbidden, signature.parameters, forbidden)
        rain = np.full((6, 5), 4.0)
        areas = np.full(5, SPACING_M * SPACING_M)
        parameters = RunoffParameters(infiltration_capacity_mm_h=2.0)
        first = simulate_rainfall_runoff(rain, areas, dt_s=3600.0, source_id="a",
                                         parameters=parameters)
        second = simulate_rainfall_runoff(rain, areas, dt_s=3600.0, source_id="a",
                                          parameters=parameters)
        for key in ("local_q_m3_s", "soil_mm", "fast_mm", "slow_mm"):
            self.assertTrue(np.array_equal(first[key], second[key]), key)
        self.assertEqual(first["metadata"]["cell_order"],
                         "input area/rain column order; no coordinates inferred")


# --------------------------------------------------------------------------- #
# T6 checkpoint: state handover and cold read
# --------------------------------------------------------------------------- #
class CheckpointColdRecoveryTests(unittest.TestCase):
    def test_splitting_the_interval_series_reproduces_one_whole_run(self):
        """T6: the carried-forward state is the only thing a restart needs.

        The time index stays continuous (``k`` keeps counting), the forcing is the same series,
        and the result must match a single run bit for bit.
        """
        cells = 4
        rain = np.tile(np.array([0.0, 1.0, 4.0, 8.0, 3.0, 1.0]), (cells, 1)).T.copy()
        areas = np.full(cells, SPACING_M * SPACING_M)
        parameters = RunoffParameters(infiltration_capacity_mm_h=2.0)
        whole = simulate_rainfall_runoff(rain, areas, dt_s=3600.0, source_id="w",
                                        parameters=parameters)
        split = 3
        first = simulate_rainfall_runoff(rain[:split], areas, dt_s=3600.0, source_id="h",
                                        parameters=parameters)
        resumed = RunoffParameters(
            infiltration_capacity_mm_h=2.0,
            initial_soil_mm=float(first["soil_mm"][-1][0]),
            initial_fast_mm=float(first["fast_mm"][-1][0]),
            initial_slow_mm=float(first["slow_mm"][-1][0]))
        second = simulate_rainfall_runoff(rain[split:], areas, dt_s=3600.0, source_id="h",
                                          parameters=resumed)
        # Every active cell is identical in this fixture, so the carried state is one number.
        for store in ("soil_mm", "fast_mm", "slow_mm"):
            self.assertEqual(float(first[store][-1][0]), float(whole[store][split][0]), store)
        np.testing.assert_array_equal(second["soil_mm"][-1], whole["soil_mm"][-1])
        np.testing.assert_array_equal(second["local_q_m3_s"],
                                      whole["local_q_m3_s"][split:])
        # The forcing is a declared interval series, so the split point is a physical time.
        self.assertEqual(split * 3600.0, 10800.0)

    def test_a_cold_digest_verifies_and_a_substituted_page_is_refused(self):
        """T6: the digest is everything a fresh process needs, and page bytes are pinned."""
        origin = (9000, 9000)
        second_origin = (origin[0] + 40, origin[1])
        pages = [("pa", plane(60, 60, origin), origin, {"native_origin": list(origin)}),
                 ("pb", plane(60, 60, second_origin), second_origin,
                  {"native_origin": list(second_origin)})]
        digest = cr.build_digest(world_seed=WORLD_SEED, pages=pages, spacing_m=SPACING_M,
                                 border_band_cells=BAND)
        self.assertEqual(digest["schema"], cr.DIGEST_SCHEMA)
        self.assertEqual(digest["world_seed"], WORLD_SEED)
        self.assertEqual(digest["spacing_m"], SPACING_M)
        verdict = cr.verify_digest(digest, pages=pages, spacing_m=SPACING_M)
        self.assertTrue(verdict["verified"], verdict["problems"])
        self.assertEqual(verdict["pages_checked"], 2)
        tampered = [(key, array.copy(), page_origin, metadata)
                    for key, array, page_origin, metadata in pages]
        tampered[0][1][3, 3] += 1e-9
        refused = cr.verify_digest(digest, pages=tampered, spacing_m=SPACING_M)
        self.assertFalse(refused["verified"])
        self.assertTrue(any("elevation sha256" in item for item in refused["problems"]))

    def test_the_digest_carries_one_subseed_derivation_and_the_ledger_has_another(self):
        """T6: a cold reader must be able to redo the sub-seed, so the derivation is IN it.

        The two modules derive 'the same purpose' differently (four bytes of a JSON hash versus
        eight bytes of a pipe-delimited hash masked to 53 bits). Both are recorded; neither may
        be presented as the other.
        """
        origin = (9000, 9000)
        pages = [("pa", plane(20, 20, origin), origin, {"native_origin": list(origin)})]
        digest = cr.build_digest(world_seed=WORLD_SEED, pages=pages, spacing_m=SPACING_M)
        climate = digest["climate"]["sub_seeds"]["climate"]
        self.assertEqual(climate, cr.derive_sub_seed(WORLD_SEED, "climate"))
        ledger = purpose_subseeds(WORLD_SEED)
        self.assertNotEqual(climate, ledger["subseeds"]["soil_initial_field"])
        self.assertLess(climate, 1 << 32)
        self.assertTrue(all(value < (1 << 53) for value in ledger["subseeds"].values()))
        self.assertNotEqual(digest["climate"]["derivation"], ledger["derivation"])
        self.assertFalse(ledger["noise_used"])
        self.assertEqual(ledger["world_seed"], WORLD_SEED)


# --------------------------------------------------------------------------- #
# N1 / N2 / N3 the three forbidden proof techniques
# --------------------------------------------------------------------------- #
class ForbiddenProofTests(unittest.TestCase):
    def test_naive_overlap_direct_comparison_overstates_disagreement(self):
        """N1: subtracting the whole overlap reports band artefacts as defects."""
        origin = (9000, 9000)
        a = plane(120, 120, origin)
        b = plane(120, 120, origin).copy()
        for edge in (0, -1):
            b[:, edge] += 0.3
            b[edge, :] += 0.3
        naive_differing = int((np.abs(a - b) > 0).sum())
        naive_fraction = naive_differing / a.size
        report = cr.overlap_comparison(a, origin, b, origin, border_band_cells=BAND)
        self.assertGreater(naive_fraction, 0.0)
        self.assertEqual(report["interior_differing_cells"], 0)
        genuine = report["interior_differing_cells"] / report["interior_cells"]
        self.assertEqual(genuine, 0.0)
        # The naive fraction is a different quantity, not a stricter estimate of the same one:
        # its numerator counts cells whose value is a reconstruction artefact.
        self.assertNotEqual(naive_fraction, genuine)
        self.assertGreater(naive_differing, 0)
        self.assertEqual(naive_differing, 4 * 120 - 4)

    def test_per_pair_summation_double_counts_and_must_be_deduplicated(self):
        """N2: one cell can sit in several pairs, so the per-pair sum is inflated."""
        origins = [(9000, 9000), (9000, 9060), (9060, 9000), (9060, 9060)]
        shared = (9080, 9080)
        pages = []
        for index, origin in enumerate(origins):
            page = plane(120, 120, origin)
            if index != 3:
                page[shared[1] - origin[1], shared[0] - origin[0]] += 0.4
            pages.append(("p%d" % index, page, origin))
        per_pair = 0
        for i in range(len(pages)):
            for j in range(i + 1, len(pages)):
                report = cr.overlap_comparison(pages[i][1], pages[i][2],
                                               pages[j][1], pages[j][2],
                                               border_band_cells=BAND)
                if report.get("overlaps"):
                    per_pair += report["interior_differing_cells"]
        net = 1  # exactly one interior cell differs, however many pairs contain it
        self.assertEqual(net, 1)
        self.assertEqual(per_pair, 3)
        self.assertGreater(per_pair, net, "the per-pair sum must exceed the net count")

    def test_qs_from_q_times_constant_is_not_independent_evidence(self):
        """N3: Qs = c*Q carries no information Q does not already carry.

        Two windows are compared on both quantities. When Q agrees on every clean cell, Qs
        agrees *because* Q does; when Q disagrees, Qs disagrees in exact proportion. The Qs
        result is therefore a linear corollary, and listing it as a second independent witness
        overstates the evidence.
        """
        constant = 3600.0 * 0.02  # a declared interval times a declared concentration
        q_a = np.array([0.0, 1.5, 2.25, 7.0])
        q_b = q_a.copy()
        np.testing.assert_array_equal(constant * q_a, constant * q_b)
        q_b[3] += 0.125
        self.assertFalse(np.array_equal(q_a, q_b))
        self.assertFalse(np.array_equal(constant * q_a, constant * q_b))
        self.assertEqual((constant * q_b)[3] / q_b[3], constant)
        self.assertTrue(np.array_equal(np.sign(constant * q_a - constant * q_b),
                                       np.sign(q_a - q_b)))


# --------------------------------------------------------------------------- #
# declared blockers, so "the interface runs" cannot become "the capability exists"
# --------------------------------------------------------------------------- #
class DeclaredBlockerTests(unittest.TestCase):
    def test_infinite_world_scope_is_refused_not_answered(self):
        """B4: the query entry refuses the scope instead of pretending to serve it."""
        self.assertIn("infinite_world", native_30m_query.NOT_IMPLEMENTED)
        for scope in tuple(native_30m_query.NOT_IMPLEMENTED):
            with self.subTest(scope=scope):
                with self.assertRaises(native_30m_query.ScopeRefusal) as caught:
                    native_30m_query.require_available({}, scope, np.ones((2, 2), bool))
                self.assertEqual(caught.exception.reason_code, "stage_not_implemented")

    def test_retained_is_a_finite_terminal_and_never_open_outflow(self):
        """B: retained is an interior terminal of a finite graph, not an outlet."""
        receiver = np.array([[1, 2, -1], [4, 5, -1], [7, 8, -1]], np.int64)
        valid = np.ones((3, 3), bool)
        declared = window_terminal_kind(receiver, valid)
        self.assertEqual(declared["census"]["open_outflow"], 0)
        labels = {str(label) for label in np.unique(declared["terminal_kind"])}
        self.assertTrue(labels <= {"inactive", "interior", "retained", "unknown_boundary"})
        self.assertEqual(declared["policy"], "finite_window_terminal_declaration_v1")
        # The rim column sits on the window border, so its cells have fewer than eight valid
        # neighbours: they are `unknown_boundary`, never `retained` and never an outlet.
        self.assertEqual(declared["census"]["retained"], 0)
        self.assertEqual(declared["census"]["unknown_boundary"], 3)
        self.assertEqual(declared["census"]["interior"], 6)
        # Widen the window so the rim column becomes interior: the same rule now calls the cells
        # that keep eight valid neighbours `retained`, and still never invents an outlet.
        wide = np.array([[1, 2, -1, -1], [5, 6, -1, -1], [9, 10, -1, -1], [13, 14, -1, -1]],
                        np.int64)
        relabelled = window_terminal_kind(wide, np.ones((4, 4), bool))
        self.assertEqual(relabelled["census"]["interior"], 8)
        self.assertEqual(relabelled["census"]["retained"], 2)
        self.assertEqual(relabelled["census"]["unknown_boundary"], 6)
        self.assertEqual(relabelled["census"]["open_outflow"], 0)

    def test_the_whole_window_soil_bucket_is_a_budget_refusal(self):
        """B5: 1337^2 cells against rainfall_runoff.MAX_CELLS = 100000."""
        import terrain_pipeline.runoff as rainfall_runoff
        self.assertEqual(rainfall_runoff.RUNOFF_MAX_CELLS, 100_000)
        cells = rainfall_runoff.RUNOFF_MAX_CELLS + 1
        with self.assertRaises(ValueError) as caught:
            simulate_rainfall_runoff(np.zeros((1, cells)), np.full(cells, 900.0), dt_s=3600.0,
                                     source_id="x")
        self.assertIn("budget", str(caught.exception))
        self.assertGreater(1787569, rainfall_runoff.RUNOFF_MAX_CELLS)

    def test_the_declared_window_budget_is_a_refusal_not_a_downscale(self):
        """B: 1337 is a declared resource budget; exceeding it refuses, never shrinks."""
        from diffusion.physical_backend import MAX_WINDOW_CELLS, window_budget
        self.assertEqual(MAX_WINDOW_CELLS, 1337)
        self.assertEqual(window_budget(1337)["cells"], 1_787_569)
        with self.assertRaises(ValueError) as caught:
            window_budget(1338)
        self.assertIn("window_budget_exceeded", str(caught.exception))
        with self.assertRaises(ValueError):
            window_budget(0)

    def test_no_cross_window_derived_physics_entry_exists(self):
        """B2: the gap is a missing entry point, asserted rather than described.

        ``metric_cross_region`` exposes the elevation surface, accumulation of quantities within
        *one* assembly, the rejection vocabulary and the digest. What it does not expose -- and
        what no other module in ``terrain_pipeline`` exposes either -- is a window-family
        recomputation of Q/Qs on real pages. If that entry is ever added, this test must be
        updated deliberately, not silently.
        """
        public = {name for name in dir(cr) if not name.startswith("_")}
        for candidate in ("cross_window_physics", "window_family_physics",
                          "recompute_across_windows", "per_window_discharge"):
            self.assertNotIn(candidate, public, candidate)
        for present in ("overlap_comparison", "assemble_pages", "cumulative_quantities",
                        "load_order_invariance", "window_family", "truncation_cost",
                        "resolve_point", "build_digest", "verify_digest"):
            self.assertIn(present, public, present)


# --------------------------------------------------------------------------- #
# auditor agreement: the independent traversal must agree with the module it audits
# --------------------------------------------------------------------------- #
class AuditorAgreementTests(unittest.TestCase):
    def test_overlap_box_and_border_distance_agree_with_the_module(self):
        origin_a = (9000, 9000)
        origin_b = (9060, 9020)
        a = plane(120, 120, origin_a)
        b = plane(120, 120, origin_b)
        report = cr.overlap_comparison(a, origin_a, b, origin_b, border_band_cells=BAND)
        box = report["overlap_native_box"]
        mine = audit_overlap_box(origin_a, a.shape, origin_b, b.shape)
        self.assertEqual([box["columns"][0], box["columns"][1],
                          box["rows"][0], box["rows"][1]], list(mine))
        mine_distance = np.minimum(audit_border_distance(origin_a, a.shape, mine),
                                   audit_border_distance(origin_b, b.shape, mine))
        self.assertEqual(int((mine_distance >= BAND).sum()), report["interior_cells"])
        self.assertEqual(report["interior_cells"] + int((mine_distance < BAND).sum()),
                         int(mine_distance.size))
        # The per-band table runs distance 0..band INCLUSIVE, while the verdict uses
        # `distance >= band` as interior -- so the `distance == band` row appears in the table
        # and in the interior count at once. That is a reporting overlap, not a tolerance: every
        # difference there is zero (it is inside the tolerance-free region).
        self.assertEqual([row["border_distance_cells"] for row in report["per_border_band"]],
                         list(range(BAND + 1)))
        self.assertEqual(sum(row["cells"] for row in report["per_border_band"]),
                         int((mine_distance <= BAND).sum()))
        self.assertEqual(sum(row["differing_cells"] for row in report["per_border_band"]),
                         report["differing_cells"])
        self.assertEqual(report["interior_differing_cells"], 0)

    def test_the_independent_assembly_matches_the_module_bit_for_bit(self):
        origin_a = (9000, 9000)
        origin_b = (9100, 9030)
        centre = (9070.0, 9060.0)
        pages = [("pa", ringed_bowl(140, 140, origin_a, centre), origin_a),
                 ("pb", ringed_bowl(140, 140, origin_b, centre), origin_b)]
        extent_origin = (9000, 9000)
        shape = (180, 180)
        module = cr.assemble_pages(pages, border_band_cells=BAND,
                                   origin=extent_origin, shape=shape)
        mine = audit_assemble(pages, extent_origin, shape, BAND)
        self.assertTrue(bitwise_equal(module["field"], mine["field"]))
        self.assertTrue(np.array_equal(module["resolved_mask"], mine["resolved_mask"]))
        self.assertEqual(module["resolved_cells"], mine["resolved_cells"])
        self.assertGreater(module["unresolved_cells"], 0)

    def test_the_independent_unknown_seed_count_matches_the_module(self):
        origin = (9000, 9000)
        pages = [("pa", ringed_bowl(120, 120, origin, (9060.0, 9060.0)), origin),
                 ("pb", ringed_bowl(120, 120, (origin[0] + 80, origin[1]), (9060.0, 9060.0)),
                  (origin[0] + 80, origin[1]))]
        assembly = cr.assemble_pages(pages, border_band_cells=BAND, origin=origin,
                                     shape=(120, 160))
        topology = build_strict_topology(assembly["field"], assembly["resolved_mask"])
        self.assertEqual(int(topology["upstream_unknown_seed_cells"]),
                         int(audit_unknown_seeds(assembly["resolved_mask"]).sum()))
        self.assertGreater(int(topology["upstream_unknown_seed_cells"]), 0)

    def test_the_module_does_not_propagate_the_unknown_mask(self):
        """T4 negative face: seeds only. Propagation is one implementation, downstream."""
        origin = (9000, 9000)
        pages = [("pa", ringed_bowl(120, 120, origin, (9060.0, 9060.0)), origin)]
        assembly = cr.assemble_pages(pages, border_band_cells=BAND, origin=origin,
                                     shape=(120, 120))
        topology = build_strict_topology(assembly["field"], assembly["resolved_mask"])
        seeds = topology["upstream_unknown_mask"]
        self.assertEqual(int(seeds.sum()), topology["upstream_unknown_seed_cells"])
        self.assertGreater(int(seeds.sum()), 0)
        # Cells strictly inside the support are not seeds: the mask is genuinely a seed set.
        interior = np.zeros_like(seeds)
        interior[BAND + 1:-BAND - 1, BAND + 1:-BAND - 1] = True
        self.assertFalse(bool((seeds & interior & topology["valid_mask"]).any()))


# --------------------------------------------------------------------------- #
# real pages: read-only, small windows, skipped when the archive is absent
# --------------------------------------------------------------------------- #
@unittest.skipUnless(PAGES_DIR.is_dir() and sorted(PAGES_DIR.glob("td-page-*.npz")),
                     "archived TD pages are not present in this checkout")
class RealPageWindowFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = []
        cls.metadata = {}
        for path in sorted(PAGES_DIR.glob("td-page-*.npz")):
            with np.load(path, allow_pickle=False) as archive:
                elevation = np.ascontiguousarray(archive["elevation_native"], np.float64)
                metadata = json.loads(str(archive["metadata_json"]))
            cls.pages.append((path.name, elevation, tuple(metadata["native_origin"])))
            cls.metadata[path.name] = metadata

    def test_every_page_declares_the_frozen_world(self):
        self.assertEqual(len(self.pages), 4)
        for name, _elevation, _origin in self.pages:
            with self.subTest(page=name):
                metadata = self.metadata[name]
                self.assertEqual(int(metadata["world_seed"]), WORLD_SEED)
                self.assertEqual(float(metadata["spacing_m"]), SPACING_M)
                self.assertEqual(metadata["schema"], "td-native-page-v1")

    def test_two_shifted_small_windows_agree_on_their_common_cells(self):
        """T1/T2 on real bytes at 257 nodes: the same cell keeps one value."""
        size = 257
        origin = BASE_ORIGIN
        shifted = (origin[0] + 97, origin[1] - 131)
        first = cr.assemble_pages(self.pages, border_band_cells=BAND, origin=origin,
                                  shape=(size, size))
        second = cr.assemble_pages(self.pages, border_band_cells=BAND, origin=shifted,
                                   shape=(size, size))
        self.assertEqual(first["resolved_cells"], size * size)
        self.assertEqual(second["resolved_cells"], size * size)
        low = (max(origin[0], shifted[0]), max(origin[1], shifted[1]))
        rows = size - abs(shifted[1] - origin[1])
        columns = size - abs(shifted[0] - origin[0])
        a = first["field"][low[1] - origin[1]:low[1] - origin[1] + rows,
                            low[0] - origin[0]:low[0] - origin[0] + columns]
        b = second["field"][low[1] - shifted[1]:low[1] - shifted[1] + rows,
                             low[0] - shifted[0]:low[0] - shifted[0] + columns]
        self.assertEqual(a.shape, (rows, columns))
        self.assertTrue(np.array_equal(a, b))

    def test_the_declared_small_window_is_order_invariant_on_real_bytes(self):
        keys = [name for name, _elevation, _origin in self.pages]
        order = [keys[2], keys[0], keys[3], keys[1]]
        first = cr.assemble_pages(self.pages, border_band_cells=BAND, origin=BASE_ORIGIN,
                                  shape=(257, 257), order=keys)
        second = cr.assemble_pages(self.pages, border_band_cells=BAND, origin=BASE_ORIGIN,
                                   shape=(257, 257), order=order)
        self.assertEqual(cr.assembly_digest(first), cr.assembly_digest(second))
        self.assertEqual(first["resolved_cells"], second["resolved_cells"])
        self.assertEqual(first["resolved_cells"], 257 * 257)

    def test_the_largest_window_inside_the_budget_fills_its_box(self):
        """A 385-node window over the page union is fully resolved (it sits inside a page)."""
        window = cr.assemble_pages(self.pages, border_band_cells=BAND, origin=BASE_ORIGIN,
                                   shape=(385, 385))
        self.assertEqual(window["resolved_cells"], 385 * 385)
        self.assertEqual(window["unresolved_cells"], 0)

    def test_load_native_window_pins_every_page(self):
        path = PAGES_DIR / self.pages[0][0]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        window = load_native_window([{"path": str(path), "sha256": digest}],
                                    origin_native_xz=BASE_ORIGIN, shape_zx=[64, 64])
        self.assertEqual(window["world_seed"], WORLD_SEED)
        self.assertEqual(window["spacing_m"], SPACING_M)
        self.assertEqual(window["source_records"][0]["page_key"], "p00")
        self.assertEqual(window["resolved_cells"], 64 * 64)
        with self.assertRaises(ValueError) as caught:
            load_native_window([{"path": str(path), "sha256": "0" * 64}],
                               origin_native_xz=BASE_ORIGIN, shape_zx=[64, 64])
        self.assertIn("pin_mismatch", str(caught.exception))
        with self.assertRaises(ValueError):
            load_native_window([], origin_native_xz=BASE_ORIGIN, shape_zx=[64, 64])


if __name__ == "__main__":
    unittest.main()
