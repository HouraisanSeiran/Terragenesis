"""Behaviour tests for the fixed-geometry highland source region stage (B1 geometry).

Two rules for every test here, the same two as ``tests/test_native_30m_source.py``:

* **No real page is a fixture.** The 2049² pages under ``.scratch`` are 33 MB each and a
  test that only passes on one saved file is a record, not a test. Every window below is
  synthesised from explicit rules, and its elevation is a function of the **absolute**
  world cell where that matters, so two windows agree where they overlap.
* **Expectations are written by hand or by an independent reference.** Where the
  producer uses a vectorised routine, the test states the answer from the definition
  (a written-out relief, a hand-counted crossing, a brute-force spacing loop), so a green
  test cannot be green because the implementation was silently missing.

What is asserted, in order: the frozen rule cannot be relaxed at a call site; the
elevation and relief gates keep the unresolved pattern; highland, ordinary slope and
lowland cells are classified differently; an empty window reports ``no_candidate``
instead of inventing a source; a patch touching the support edge or an unknown neighbour
is pending and a cropped window never presents the split as complete; region members are
world int64 cells and two windows agree on the shared patch's id and members; a negative
world origin is carried correctly; the elevation reference is explicit against the model
sea level rather than a per-window percentile; the head is the **first** crossing and not
the largest upstream count downstream; de-duplication follows the declared order; inputs
are not mutated; and a tampered region, head, area or count is refused.
"""
import copy
import hashlib
import math
import unittest

import numpy as np

from terrain_pipeline.surface_rivers import metric_highland_sources as highland
from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology

SEED = highland.DECLARED_WORLD_SEED
SPACING_M = highland.DECLARED_SPACING_M
RADIUS_CELLS = 10                      # 21x21 window, axis radius 300 m
MIN_REGION_CELLS = 100                 # 90000 m2 at 30 m
DEFAULT_ORIGIN = (42173, 42874)


# --------------------------------------------------------------------------- #
# synthetic terrain: a function of the absolute world cell
# --------------------------------------------------------------------------- #
def world_field(origin_xz, shape_zx, height):
    """Sample ``height(x, z)`` on the absolute native lattice of one window.

    Building the field from world coordinates (not from array indices) is what makes the
    overlap and translation tests meaningful: two different windows must agree cell for
    cell where they overlap, exactly like two reads of the same saved pages.
    """
    rows, columns = shape_zx
    z = np.arange(rows, dtype=np.int64)[:, None] + int(origin_xz[1])
    x = np.arange(columns, dtype=np.int64)[None, :] + int(origin_xz[0])
    return np.ascontiguousarray(height(x, z), np.float64)


def patch_terrain(*, inset=50, size=60, origin=DEFAULT_ORIGIN, high=1520.0,
                  low=900.0, tilt=(4.0, 2.0)):
    """One tilted highland block inset from the window edge, in low ground elsewhere.

    The inset is larger than the relief radius, so the block's candidates have a fully
    resolved 21x21 window and do not touch the support edge: that is the configuration
    in which a region may legitimately be ``complete``. The tilt is stated in metres per
    cell, and over a 21-cell window it gives ``20 * (tilt_x + tilt_z) = 120 m`` of local
    relief, so the block passes the 100 m relief gate in its interior while the low
    ground around it is rejected by the elevation gate.
    """
    def height(x, z):
        local_x = x - origin[0]
        local_z = z - origin[1]
        inside = ((local_x >= inset) & (local_x < inset + size)
                  & (local_z >= inset) & (local_z < inset + size))
        body = high + tilt[0] * local_x + tilt[1] * local_z
        return np.where(inside, body, low)
    return height


def valley_terrain(*, origin=DEFAULT_ORIGIN, inset=20, width=100, depth=90,
                   high=1560.0, low=900.0):
    """A V-shaped valley inside a highland patch, draining into lowland outside it.

    This is the configuration that separates the two head rules: inside the patch the
    valley collects a long graph-receiver corridor, and downstream, in the lowland, the
    contribution keeps growing to the window maximum. "Largest upstream count" would name
    that lowland cell; the declared rule names the first crossing inside the patch.
    """
    def height(x, z):
        local_x = x - origin[0]
        local_z = z - origin[1]
        inside = ((local_x >= inset) & (local_x < inset + width)
                  & (local_z >= inset) & (local_z < inset + depth))
        body = (high + 3.0 * np.abs(local_x - (inset + width / 2.0))
                - 0.45 * (local_z - inset))
        return np.where(inside, body, low)
    return height


def window(field, *, origin=DEFAULT_ORIGIN, mask=None, seed=SEED, spacing=SPACING_M):
    """A loader-shaped window: unresolved cells carry NaN, resolved ones are finite."""
    field = np.ascontiguousarray(field, np.float64)
    resolved = (np.ones(field.shape, bool) if mask is None
                else np.ascontiguousarray(mask, bool))
    values = np.where(resolved, field, np.nan)
    return {
        "field": np.ascontiguousarray(values, np.float64),
        "resolved_mask": resolved,
        "origin_native_xz": [int(origin[0]), int(origin[1])],
        "shape_zx": [int(field.shape[0]), int(field.shape[1])],
        "world_seed": seed,
        "spacing_m": float(spacing),
    }


def patch_window(rows=160, columns=160, *, origin=DEFAULT_ORIGIN, **terrain):
    return window(world_field(origin, (rows, columns), patch_terrain(origin=origin,
                                                                    **terrain)),
                  origin=origin)


def valley_window(rows=140, columns=140, *, origin=DEFAULT_ORIGIN, **terrain):
    return window(world_field(origin, (rows, columns), valley_terrain(origin=origin,
                                                                     **terrain)),
                  origin=origin)


def edge_valley_terrain(*, origin=DEFAULT_ORIGIN, inset_x=0, inset_z=20, width=100,
                        depth=90, high=1560.0, low=900.0):
    """The same V valley, but sitting on the **left** support edge (``inset_x=0``).

    Unlike ``valley_terrain(inset=0)`` -- which touches two edges at the corner -- this
    one keeps a real valley interior (inset in z, wide enough in x) while its ridge still
    reaches the left edge, so the D4 patch is genuinely *pending* and still contains the
    whole strict corridor up to its first crossing. That is the configuration in which a
    pending region legitimately yields a pending head instead of an empty table.
    """
    def height(x, z):
        local_x = x - origin[0]
        local_z = z - origin[1]
        inside = ((local_x >= inset_x) & (local_x < inset_x + width)
                  & (local_z >= inset_z) & (local_z < inset_z + depth))
        body = (high + 3.0 * np.abs(local_x - (inset_x + width / 2.0))
                - 0.45 * (local_z - inset_z))
        return np.where(inside, body, low)
    return height


def twin_valley_terrain(*, origin=DEFAULT_ORIGIN, inset=20, size=110, gap=8,
                        high=1560.0, low=900.0):
    """Two parallel V valleys ``gap`` cells apart inside one highland block.

    Two crossings ~240 m apart inside one patch is the configuration that exercises the
    600 m de-duplication: with ``gap=8`` the loser sits inside the winner's spacing radius,
    so the head table depends on whether the winner is itself decided.
    """
    centre_a = inset + size // 2 - gap // 2
    centre_b = centre_a + gap

    def height(x, z):
        local_x = x - origin[0]
        local_z = z - origin[1]
        inside = ((local_x >= inset) & (local_x < inset + size)
                  & (local_z >= inset) & (local_z < inset + size))
        body = (high + 2.0 * np.minimum(np.abs(local_x - centre_a),
                                        np.abs(local_x - centre_b))
                - 0.5 * (local_z - inset))
        return np.where(inside, body, low)
    return height


def block_terrain(*, inset=50, size=60, origin=DEFAULT_ORIGIN, high=1500.0,
                  low=1000.0):
    """One flat-topped highland block inside low ground, in absolute world cells.

    The low ground is below the 1400 m gate, so only the block can be a candidate, and a
    block inset further than the relief radius is a genuinely interior patch whose 21x21
    window never runs off the support. Used where the test is about the *area* gate or
    about a below-area patch, not about the relief gradient.
    """
    def height(x, z):
        local_x = x - origin[0]
        local_z = z - origin[1]
        inside = ((local_x >= inset) & (local_x < inset + size)
                  & (local_z >= inset) & (local_z < inset + size))
        return np.where(inside, high, low)
    return height


def twin_window(rows=160, columns=160, *, origin=DEFAULT_ORIGIN, **terrain):
    return window(world_field(origin, (rows, columns),
                              twin_valley_terrain(origin=origin, **terrain)),
                  origin=origin)


def flat_window(rows=120, columns=120, *, origin=DEFAULT_ORIGIN, level=1500.0,
                seed=SEED, spacing=SPACING_M):
    """A constant-height window: highland passes elevation but has no relief at all."""
    return window(np.full((rows, columns), float(level)), origin=origin, seed=seed,
                  spacing=spacing)


def world_mask(shape_zx, height):
    """Field + all-resolved mask over the default origin, for the gate helpers."""
    field = world_field(DEFAULT_ORIGIN, shape_zx, height)
    return field, np.ones(field.shape, bool)


def reference_relief(field, mask, window_cells):
    """Slow, explicit square-window relief; NaN where the window is not fully resolved."""
    rows, columns = field.shape
    relief = np.full(field.shape, np.nan, np.float64)
    radius = (window_cells - 1) // 2
    for row in range(radius, rows - radius):
        for column in range(radius, columns - radius):
            block = mask[row - radius:row + radius + 1,
                         column - radius:column + radius + 1]
            if not block.all():
                continue
            values = field[row - radius:row + radius + 1,
                           column - radius:column + radius + 1]
            relief[row, column] = values.max() - values.min()
    return relief


# --------------------------------------------------------------------------- #
# the frozen rule is not a knob
# --------------------------------------------------------------------------- #
class FrozenRuleTest(unittest.TestCase):
    def test_declared_rule_is_the_frozen_table(self):
        rule = highland.declared_rule()
        self.assertEqual(rule["rule_version"], "highland-source-geometry-dev-v1")
        self.assertEqual(rule["world_seed"], 20261020)
        self.assertEqual(rule["spacing_m"], 30.0)
        parameters = rule["parameters"]
        self.assertEqual(parameters["model_sea_level_m"], 0.0)
        self.assertEqual(parameters["min_source_elevation_above_sea_m"], 1400.0)
        self.assertEqual(parameters["relief_radius_m"], 300.0)
        self.assertEqual(parameters["relief_window_cells"], 21)
        self.assertEqual(parameters["min_local_relief_m"], 100.0)
        self.assertEqual(parameters["min_source_region_area_m2"], 90000.0)
        self.assertEqual(parameters["source_head_min_spacing_m"], 600.0)
        self.assertEqual(parameters["min_head_upstream_cells"], 100)
        self.assertIsNone(parameters["slope_filter"])
        self.assertEqual(set(rule["calibration"].values()), {"declared_uncalibrated"})

    def test_declared_rule_is_a_copy(self):
        rule = highland.declared_rule()
        rule["parameters"]["min_local_relief_m"] = 1.0
        self.assertEqual(highland.DECLARED_PARAMETERS["min_local_relief_m"], 100.0)
        self.assertIsNot(highland._resolve_rule(None), highland.DECLARED_PARAMETERS)

    def test_relaxed_relief_gate_is_refused(self):
        rule = highland.declared_rule()
        rule["parameters"] = dict(rule["parameters"], min_local_relief_m=20.0)
        with self.assertRaisesRegex(ValueError, "undeclared_rule"):
            highland.source_regions(flat_window(), rule=rule)

    def test_extra_parameter_is_refused(self):
        parameters = dict(highland.DECLARED_PARAMETERS, max_source_slope=0.3)
        with self.assertRaisesRegex(ValueError, "undeclared_rule"):
            highland.source_regions(flat_window(), rule=parameters)

    def test_slope_hard_gate_is_refused(self):
        parameters = dict(highland.DECLARED_PARAMETERS, slope_filter=0.4)
        with self.assertRaisesRegex(ValueError, "no slope hard gate"):
            highland.source_regions(flat_window(), rule=parameters)

    def test_other_rule_version_is_refused(self):
        rule = highland.declared_rule()
        rule["rule_version"] = "highland-source-geometry-dev-v2"
        with self.assertRaisesRegex(ValueError, "undeclared_rule"):
            highland.source_regions(flat_window(), rule=rule)

    def test_other_seed_and_spacing_are_refused(self):
        with self.assertRaisesRegex(ValueError, "seed_mismatch"):
            highland.source_regions(flat_window(seed=20261021))
        with self.assertRaisesRegex(ValueError, "spacing_mismatch"):
            highland.source_regions(flat_window(spacing=10.0))


# --------------------------------------------------------------------------- #
# gates, and the unresolved pattern
# --------------------------------------------------------------------------- #
class GateTest(unittest.TestCase):
    def test_relief_matches_the_hand_written_reference(self):
        field = world_field(DEFAULT_ORIGIN, (40, 40), valley_terrain())
        mask = np.ones(field.shape, bool)
        rows = field.shape[0]
        marks = highland.highland_candidates(field, mask)
        stored = marks["relief_m"]
        expected = reference_relief(field, mask, 21)
        self.assertFalse(np.isfinite(stored[:RADIUS_CELLS, :]).any())
        self.assertFalse(np.isfinite(stored[:, :RADIUS_CELLS]).any())
        self.assertFalse(np.isfinite(stored[rows - RADIUS_CELLS:, :]).any())
        self.assertFalse(np.isfinite(stored[-1, -1]))
        self.assertTrue(np.isfinite(stored[RADIUS_CELLS, RADIUS_CELLS]))
        np.testing.assert_array_equal(np.isnan(stored), np.isnan(expected))
        np.testing.assert_allclose(stored, expected, rtol=0.0, atol=0.0)

    def test_unresolved_hole_keeps_nan_and_blocks_the_relief(self):
        field = world_field(DEFAULT_ORIGIN, (80, 80), patch_terrain(inset=10, size=60))
        mask = np.ones(field.shape, bool)
        mask[40, 40] = False
        values = np.where(mask, field, np.nan)
        marks = highland.highland_candidates(values, mask)
        relief = marks["relief_m"]
        self.assertTrue(np.isnan(relief[40, 40]))
        for row in range(40 - RADIUS_CELLS, 40 + RADIUS_CELLS + 1):
            for column in range(40 - RADIUS_CELLS, 40 + RADIUS_CELLS + 1):
                self.assertTrue(np.isnan(relief[row, column]),
                                "a window covering the hole must not carry relief")
        self.assertFalse(marks["candidate"][40, 40])
        # Nothing was filled in: the elevation still has NaN exactly on the hole.
        self.assertTrue(np.isnan(values[40, 40]))

    def test_highland_lowland_and_flat_plateau_are_classified_differently(self):
        terrain = window(world_field(DEFAULT_ORIGIN, (160, 160),
                                     patch_terrain(inset=50, size=60)))
        marks = highland.highland_candidates(terrain["field"], terrain["resolved_mask"])
        row, column = 80, 80                     # well inside the tilted block
        self.assertGreaterEqual(terrain["field"][row, column], 1400.0)
        self.assertGreaterEqual(marks["relief_m"][row, column], 100.0)
        self.assertTrue(marks["candidate"][row, column])
        low = terrain["field"] < 1400.0
        self.assertTrue(low.any())
        self.assertFalse(marks["elevation_candidate"][low].any())
        self.assertFalse(marks["candidate"][low].any())

        smooth = flat_window(60, 60, level=1600.0)
        smooth_marks = highland.highland_candidates(smooth["field"],
                                                    smooth["resolved_mask"])
        self.assertTrue(smooth_marks["elevation_candidate"][30, 30])
        self.assertEqual(smooth_marks["relief_m"][30, 30], 0.0)
        self.assertFalse(smooth_marks["candidate"][30, 30])

    def test_elevation_reference_is_absolute_not_a_window_percentile(self):
        """Two windows over the same world terrain must agree on the gate.

        The elevation gate is absolute against the declared model sea level, so the same
        world cell is highland in a 60-cell window and in a 160-cell window alike -- a
        per-window percentile would flip cells when the window changes.

        ``candidate`` additionally needs a *fully resolved* 21x21 relief window, and the
        narrow support cannot supply one for the cells within 10 cells of its edge. That
        is the declared unresolved pattern, not a difference of the gate, so the relief
        part is compared only where both supports actually carry a relief value.
        """
        narrow = highland.highland_candidates(
            *world_mask((60, 60), patch_terrain(inset=50, size=60)))
        wide = highland.highland_candidates(
            *world_mask((160, 160), patch_terrain(inset=50, size=60)))
        # The elevation gate is absolute and window-independent everywhere.
        np.testing.assert_array_equal(narrow["elevation_candidate"],
                                      wide["elevation_candidate"][:60, :60])
        both_covered = narrow["covered"] & wide["covered"][:60, :60]
        self.assertTrue(both_covered.any())
        np.testing.assert_array_equal(narrow["candidate"][both_covered],
                                      wide["candidate"][:60, :60][both_covered])
        # And the narrow window really is truncated: its border band carries no relief.
        self.assertFalse(np.isfinite(narrow["relief_m"][:RADIUS_CELLS, :]).any())
        self.assertTrue(np.isfinite(wide["relief_m"][50, 50]))

    def test_non_finite_resolved_value_and_filled_unknown_are_refused(self):
        broken = flat_window(40, 40)
        broken["field"][5, 5] = np.nan          # NaN on a resolved cell
        with self.assertRaisesRegex(ValueError, "elevation_mask_contract"):
            highland.source_regions(broken)
        # An unresolved cell that was filled with a height is refused, not reinterpreted.
        filled = flat_window(40, 40)
        filled["resolved_mask"][5, 5] = False
        filled["field"][5, 5] = 0.0
        with self.assertRaisesRegex(ValueError, "elevation_mask_contract"):
            highland.source_regions(filled)

    def test_routing_results_inside_the_window_dict_are_refused(self):
        dirty = flat_window()
        dirty["receiver"] = np.zeros(dirty["field"].shape, np.int64)
        with self.assertRaisesRegex(ValueError, "routing_graph_invalid"):
            highland.source_regions(dirty)

    def test_budget_is_not_raised_at_a_call_site(self):
        small = flat_window(20, 20)
        with self.assertRaisesRegex(ValueError, "budget_exceeded"):
            highland.source_regions(small, max_cells=10)
        with self.assertRaisesRegex(ValueError, "budget_exceeded"):
            highland.source_regions(small, max_cells=highland.DEFAULT_MAX_CELLS * 2)

    def test_declared_budget_matches_the_route_ceiling(self):
        from terrain_pipeline.surface_rivers.metric_world_domains import (
            MAX_SUPPORT_CELLS)
        self.assertEqual(highland.DEFAULT_MAX_CELLS, MAX_SUPPORT_CELLS)
        self.assertEqual(highland.DEFAULT_MAX_CELLS, 148225)


# --------------------------------------------------------------------------- #
# empty, pending and cropped windows
# --------------------------------------------------------------------------- #
class RegionStatusTest(unittest.TestCase):
    def test_empty_window_reports_no_candidate(self):
        low = window(np.full((60, 60), 300.0))
        bundle = highland.build_highland_sources(low)
        self.assertEqual(bundle["regions"], [])
        self.assertEqual(bundle["heads"], [])
        self.assertTrue(any(highland.REASON_NO_CANDIDATE in item["reason_codes"]
                            for item in bundle["rejects"]))
        self.assertEqual(bundle["metadata"]["region_census"]["candidate_cells"], 0)
        self.assertEqual(bundle["arrays"]["region_cells"].shape, (0, 2))

    def test_interior_patch_can_be_complete(self):
        bundle = highland.build_highland_sources(patch_window())
        self.assertTrue(bundle["regions"])
        complete = [item for item in bundle["regions"]
                    if item["status"] == highland.STATUS_REGION_COMPLETE]
        self.assertTrue(complete, "an inset, fully resolved patch must be complete")
        for item in complete:
            self.assertFalse(item["touches_support_edge"])
            self.assertEqual(item["unknown_neighbour_cells"], 0)
            self.assertTrue(item["qualified"])
            self.assertEqual(item["reason_codes"], [highland.REASON_COMPLETE])

    def test_patch_touching_the_support_edge_is_pending_not_smaller(self):
        """The same highland block placed against the window edge is pending.

        The block is inset 0, so its candidates include cells on the first row/column:
        the region may continue outside the support, and the table says so instead of
        reporting a smaller, apparently certified region.
        """
        edge = patch_window(140, 140, inset=0, size=100)
        bundle = highland.build_highland_sources(edge)
        self.assertTrue(bundle["regions"])
        for item in bundle["regions"]:
            self.assertTrue(item["touches_support_edge"])
            self.assertNotEqual(item["status"], highland.STATUS_REGION_COMPLETE)
            self.assertIn(highland.REASON_SUPPORT_EDGE, item["reason_codes"])
        for head in bundle["heads"]:
            self.assertFalse(head["geometry_certified"])
            self.assertEqual(head["status"], highland.STATUS_HEAD_PENDING)
        self.assertEqual(bundle["metadata"]["certified_world_heads"], 0)

    def test_unknown_neighbour_is_pending(self):
        field = world_field(DEFAULT_ORIGIN, (120, 120), patch_terrain(inset=10, size=90))
        mask = np.ones(field.shape, bool)
        mask[60, 60] = False
        bundle = highland.build_highland_sources(window(field, mask=mask))
        statuses = {item["status"] for item in bundle["regions"]}
        self.assertIn(highland.STATUS_REGION_PENDING, statuses)
        pending = [item for item in bundle["regions"]
                   if item["status"] == highland.STATUS_REGION_PENDING]
        self.assertTrue(any(highland.REASON_UNKNOWN_NEIGHBOUR in item["reason_codes"]
                            for item in pending))
        self.assertGreater(sum(item["unknown_neighbour_cells"] for item in pending), 0)

    def test_cropped_window_cannot_claim_a_complete_region(self):
        """The same world patch, cropped: the narrow window must be pending, not complete.

        The block is inset 50 cells and spans local x/z 50..110, so a 70-cell window cuts
        it at its right and lower edges. The cropped member set is smaller and must be
        reported pending -- never presented as a smaller certified region.
        """
        wide = patch_window(160, 160)
        narrow = patch_window(70, 70)
        wide_bundle = highland.build_highland_sources(wide)
        narrow_bundle = highland.build_highland_sources(narrow)
        self.assertTrue(any(item["status"] == highland.STATUS_REGION_COMPLETE
                            for item in wide_bundle["regions"]))
        self.assertTrue(narrow_bundle["regions"])
        for item in narrow_bundle["regions"]:
            self.assertNotEqual(item["status"], highland.STATUS_REGION_COMPLETE)
            self.assertTrue(item["touches_support_edge"])
        wide_ids = {item["region_id"] for item in wide_bundle["regions"]}
        narrow_ids = {item["region_id"] for item in narrow_bundle["regions"]}
        self.assertFalse(narrow_ids & wide_ids)

    def test_below_area_patch_is_listed_not_dropped(self):
        """A small but genuinely interior patch is listed as below area, not dropped.

        The patch is inset well past the relief radius so it is a real interior patch: a
        block hugging the support edge would have no relief at all (the 21x21 window
        would run off the support), and a fixture like that would test the edge band
        rather than the area gate. 5x5 = 25 candidates < 100 cells.
        """
        height = block_terrain(inset=30, size=5, high=1500.0, low=1000.0)
        bundle = highland.build_highland_sources(
            window(world_field(DEFAULT_ORIGIN, (80, 80), height)))
        statuses = [item["status"] for item in bundle["regions"]]
        self.assertEqual(statuses, [highland.STATUS_REGION_BELOW_AREA])
        for item in bundle["regions"]:
            self.assertLess(item["member_count"], MIN_REGION_CELLS)
            self.assertEqual(item["member_count"], 25)
            self.assertFalse(item["qualified"])
            self.assertFalse(item["touches_support_edge"])
        self.assertTrue(any(highland.REASON_REGION_BELOW_AREA in item["reason_codes"]
                            for item in bundle["rejects"]))
        self.assertFalse(bundle["heads"])


# --------------------------------------------------------------------------- #
# world identity: members, ids, windows and a negative origin
# --------------------------------------------------------------------------- #
class WorldIdentityTest(unittest.TestCase):
    def test_region_members_are_world_int64_sorted_cells(self):
        origin = DEFAULT_ORIGIN
        result = highland.source_regions(patch_window())
        cells = result["region_cells"]
        self.assertEqual(cells.dtype, np.int64)
        self.assertEqual(cells.ndim, 2)
        self.assertEqual(cells.shape[1], 2)
        pointer = result["region_ptr"]
        self.assertEqual(int(pointer[0]), 0)
        self.assertEqual(int(pointer[-1]), cells.shape[0])
        for position, item in enumerate(result["regions"]):
            block = cells[pointer[position]:pointer[position + 1]]
            self.assertEqual(block.shape[0], item["member_count"])
            order = np.lexsort((block[:, 1], block[:, 0]))
            np.testing.assert_array_equal(block, block[order])
            self.assertEqual(highland.member_sha256(block), item["member_sha256"])
            self.assertGreaterEqual(block[:, 0].min(), origin[0])
            self.assertGreaterEqual(block[:, 1].min(), origin[1])
        # The digest is over world cells: an (x, z) transpose is a different member set.
        self.assertNotEqual(highland.member_sha256(cells[:, ::-1]),
                            highland.member_sha256(cells))

    def test_same_world_patch_keeps_one_id_across_a_translated_window(self):
        """A patch wholly inside both windows keeps its id and its members.

        The identity excludes the window origin, its shape and every support-local
        index, so a translation cannot renumber a world patch. The block here is inset 50
        cells, so a 10-cell translation leaves every candidate's 21x21 window resolved.
        """
        wide = patch_window(160, 160, inset=50, size=60)
        shifted_origin = (DEFAULT_ORIGIN[0] + 10, DEFAULT_ORIGIN[1] + 10)
        shifted = window(world_field(shifted_origin, (140, 140),
                                     patch_terrain(inset=50, size=60)),
                         origin=shifted_origin)
        base = highland.source_regions(wide)
        translated = highland.source_regions(shifted)
        base_ids = {item["region_id"]: item for item in base["regions"]
                    if item["status"] == highland.STATUS_REGION_COMPLETE}
        translated_ids = {item["region_id"]: item for item in translated["regions"]
                          if item["status"] == highland.STATUS_REGION_COMPLETE}
        shared = set(base_ids) & set(translated_ids)
        self.assertTrue(shared, "the overlapping complete patch must keep its id")
        for region_id in shared:
            self.assertEqual(base_ids[region_id]["member_count"],
                             translated_ids[region_id]["member_count"])
            self.assertEqual(base_ids[region_id]["member_sha256"],
                             translated_ids[region_id]["member_sha256"])
            self.assertEqual(base_ids[region_id]["anchor_world_xz"],
                             translated_ids[region_id]["anchor_world_xz"])

    def test_negative_world_origin_is_carried_correctly(self):
        origin = (-1200, -3500)
        result = highland.source_regions(patch_window(70, 70, origin=origin, inset=10,
                                                      size=50))
        cells = result["region_cells"]
        self.assertTrue(cells.size)
        self.assertLess(cells[:, 0].min(), 0)
        self.assertLess(cells[:, 1].min(), 0)
        self.assertEqual(result["origin_native_xz"], [-1200, -3500])
        index = result["region_index"]
        row, column = np.argwhere(index == 0)[0]
        # Array (row, column) is world (origin_x + column, origin_z + row); a sign error
        # would flip the whole patch into positive coordinates.
        self.assertIn([-1200 + int(column), -3500 + int(row)], cells.tolist())

    def test_member_digest_ignores_permutation_and_notices_one_cell(self):
        base = np.array([[10, 20], [11, 20], [10, 21]], np.int64)
        self.assertEqual(highland.member_sha256(base),
                         highland.member_sha256(base[[2, 0, 1]]))
        changed = base.copy()
        changed[0, 0] = 12
        self.assertNotEqual(highland.member_sha256(base),
                            highland.member_sha256(changed))

    def test_a_modified_terrain_produces_a_new_source_identity(self):
        """Two different things, deliberately separated.

        ``region_id`` names the world **member object**: the same int64 cells under the
        same rule stay D4-connected after one cell changes height, so the id must *not*
        change -- otherwise every re-read of a slightly different page would renumber a
        world object and cross-window identity would be worthless.

        ``source_identity_sha256`` names the **source product**: the elevations actually
        stored on those members. One metre changed under a member must change it.
        """
        first = highland.source_regions(patch_window())
        changed = patch_window()
        changed["field"][80, 80] -= 3.0
        second = highland.source_regions(changed)
        self.assertEqual([item["region_id"] for item in first["regions"]],
                         [item["region_id"] for item in second["regions"]],
                         "the member set did not move, so the world object keeps its id")
        self.assertEqual([item["member_sha256"] for item in first["regions"]],
                         [item["member_sha256"] for item in second["regions"]])
        self.assertNotEqual([item["source_identity_sha256"] for item in first["regions"]],
                            [item["source_identity_sha256"] for item in second["regions"]],
                            "the terrain under the members changed, so the source "
                            "product identity must change too")
        # A genuine membership change still produces a new world object id.
        dropped = patch_window()
        shifted_origin = (DEFAULT_ORIGIN[0], DEFAULT_ORIGIN[1])
        smaller = patch_window(160, 160, inset=50, size=40)
        self.assertEqual(shifted_origin, DEFAULT_ORIGIN)
        self.assertNotEqual({item["region_id"] for item in
                             highland.source_regions(dropped)["regions"]},
                            {item["region_id"] for item in
                             highland.source_regions(smaller)["regions"]})


# --------------------------------------------------------------------------- #
# heads: first crossing, spacing order, and the lowland rule
# --------------------------------------------------------------------------- #
class HeadTest(unittest.TestCase):
    def test_head_is_the_first_crossing_not_the_largest_count(self):
        region = valley_window()
        bundle = highland.build_highland_sources(region)
        self.assertTrue(bundle["heads"], "the valley must produce a head")
        counts = bundle["arrays"]["known_upstream_cells"]
        origin = region["origin_native_xz"]
        for head in bundle["heads"]:
            x, z = head["world_xz"]
            self.assertGreaterEqual(counts[z - origin[1], x - origin[0]], 100)
            self.assertEqual(int(counts[z - origin[1], x - origin[0]]),
                             head["known_upstream_cells"])
        # The window maximum is strictly larger than every declared head: picking the
        # largest upstream count would have named a downstream cell instead.
        self.assertGreater(int(counts.max()),
                           max(item["known_upstream_cells"] for item in bundle["heads"]))
        maximum_cell = int(np.argmax(counts))
        candidate = bundle["arrays"]["highland_candidate"].reshape(-1)
        self.assertFalse(bool(candidate[maximum_cell]),
                         "the window maximum must be downstream of the patch")
        self.assertFalse(bool(bundle["arrays"]["head_flags"].reshape(-1)[maximum_cell]))

    def test_head_requires_the_first_crossing_inside_a_qualified_patch(self):
        region = valley_window()
        bundle = highland.build_highland_sources(region)
        index = bundle["arrays"]["region_index"]
        qualified = {item["region_id"] for item in bundle["regions"] if item["qualified"]}
        origin = region["origin_native_xz"]
        for head in bundle["heads"]:
            self.assertIn(head["region_id"], qualified)
            x, z = head["world_xz"]
            self.assertGreaterEqual(index[z - origin[1], x - origin[0]], 0)
        # Crossings in the lowland are refused, and every refusal is reported.
        outside = [item for item in bundle["rejects"]
                   if highland.REASON_OUTSIDE_QUALIFIED_REGION in item["reason_codes"]]
        self.assertEqual(len(outside),
                         bundle["metadata"]["head_census"]["rejected_outside_patch"])

    def test_heads_honour_the_declared_spacing_rule(self):
        region = valley_window()
        bundle = highland.build_highland_sources(region)
        by_region = {}
        for head in bundle["heads"]:
            by_region.setdefault(head["region_id"], []).append(head)
        for heads in by_region.values():
            for first in range(len(heads)):
                for second in range(first + 1, len(heads)):
                    a = heads[first]["world_xz"]
                    b = heads[second]["world_xz"]
                    self.assertGreaterEqual(
                        math.hypot((a[0] - b[0]) * SPACING_M,
                                   (a[1] - b[1]) * SPACING_M), 600.0)
        suppressed = [item for item in bundle["rejects"]
                      if highland.REASON_SPACING_SUPPRESSED in item["reason_codes"]]
        self.assertEqual(len(suppressed),
                         bundle["metadata"]["head_census"]["rejected_spacing"])
        for item in suppressed:
            self.assertGreaterEqual(item["required_m"], 600.0)
            self.assertGreaterEqual(item["distance_m"], 0.0)

    def test_a_pending_suppressor_does_not_settle_a_suppression(self):
        """Two crossings 240 m apart: only a *certified* suppressor settles the loser.

        With one patch that reaches the support edge (``twin_window(140)``) the winner is
        only pending, so the loser's exclusion is **not** decided: a wider support could
        complete the winner -- and would then report the loser's distance against a
        decided object -- or even drop it. Calling that a decided 600 m exclusion would
        let the head table flip when the support grows, so it is listed as
        ``spacing_suppression_pending`` with the blocking object named.

        The same terrain in a support that does complete the patch
        (``twin_window(160)``) must report a decided suppression -- and a certified head.
        """
        narrow = highland.build_highland_sources(twin_window(140))
        wide = highland.build_highland_sources(twin_window(160))
        self.assertEqual([item["status"] for item in narrow["regions"]],
                         [highland.STATUS_REGION_PENDING])
        self.assertEqual([item["status"] for item in wide["regions"]],
                         [highland.STATUS_REGION_COMPLETE])
        narrow_pending = [item for item in narrow["rejects"]
                          if highland.REASON_SUPPRESSION_PENDING in item["reason_codes"]]
        self.assertGreaterEqual(len(narrow_pending), 1)
        for rejection in narrow_pending:
            self.assertFalse(rejection["decided"])
            self.assertFalse(rejection["suppressor_complete"])
            self.assertLess(rejection["distance_m"], 600.0)
            self.assertIn("kept_world_xz", rejection)
        self.assertEqual(narrow["metadata"]["head_census"]["rejected_spacing"], 0)
        self.assertEqual(narrow["metadata"]["head_census"]["rejected_spacing_pending"], len(narrow_pending))
        self.assertEqual(narrow["metadata"]["certified_world_heads"], 0)

        wide_decided = [item for item in wide["rejects"]
                        if highland.REASON_SPACING_SUPPRESSED in item["reason_codes"]]
        self.assertGreaterEqual(len(wide_decided), 1)
        self.assertTrue(all(item["decided"] for item in wide_decided))
        self.assertEqual(wide["metadata"]["head_census"]["rejected_spacing_pending"], 0)
        certified = [head for head in wide["heads"] if head["geometry_certified"]]
        self.assertGreaterEqual(len(certified), 1)
        self.assertEqual(wide["metadata"]["certified_world_heads"], len(certified))
        # The declared order is the same in both: highest contribution first, then world
        # (x, z). A pending winner may differ from the certified one, and that is the
        # point: pending is not a decided ranking.
        self.assertGreaterEqual(narrow["heads"][0]["known_upstream_cells"], 100)
        self.assertGreaterEqual(wide["heads"][0]["known_upstream_cells"], 100)

    def test_every_declared_head_is_the_first_crossing_of_its_own_donor_set(self):
        """Written from the definition: no donor may already be at or above 100 cells."""
        region = valley_window()
        graph = build_strict_topology(region["field"], region["resolved_mask"], origin_native_xz=region["origin_native_xz"])
        bundle = highland.build_highland_sources(region)
        counts = bundle["arrays"]["known_upstream_cells"].reshape(-1)
        receiver = graph["receiver"].reshape(-1)
        origin = region["origin_native_xz"]
        columns = region["shape_zx"][1]
        for head in bundle["heads"]:
            x, z = head["world_xz"]
            cell = (z - origin[1]) * columns + (x - origin[0])
            self.assertGreaterEqual(counts[cell], 100)
            donors = np.flatnonzero(receiver == cell)
            if donors.size:
                self.assertLess(int(counts[donors].max()), 100)

    def test_lowland_does_not_get_a_new_head_and_geometry_certifies_no_water(self):
        bundle = highland.build_highland_sources(valley_window())
        lowland = ~bundle["arrays"]["highland_candidate"]
        self.assertTrue(lowland.any())
        self.assertFalse(bundle["arrays"]["head_flags"][lowland].any())
        metadata = bundle["metadata"]
        self.assertEqual(metadata["rainfall_supported"], "rainfall_supported_pending")
        self.assertIs(metadata["perennial_flow_certified"], False)
        self.assertEqual(metadata["water_budget"], "none")
        self.assertIs(metadata["mainstem_generated"], False)

    def test_a_pending_region_cannot_produce_a_certified_head(self):
        """A patch cut by the support edge still yields heads -- but only pending ones.

        The valley is placed against the window edge (``inset=0``) and the support is
        narrowed so the patch is pending, i.e. it may continue outside the support. Its
        first crossing is a real head candidate and must be listed, with
        ``head_geometry_pending`` and the region's own reason, never certified: a support
        boundary is not evidence that no more upstream exists.
        """
        region = window(world_field(DEFAULT_ORIGIN, (140, 140),
                                    edge_valley_terrain()))
        bundle = highland.build_highland_sources(region)
        pending_ids = {item["region_id"] for item in bundle["regions"]
                       if item["status"] != highland.STATUS_REGION_COMPLETE}
        self.assertTrue(pending_ids, "a patch touching the support edge is pending")
        self.assertTrue(bundle["heads"], "the valley still yields head candidates")
        for head in bundle["heads"]:
            self.assertIn(head["region_id"], pending_ids)
            self.assertFalse(head["geometry_certified"])
            self.assertEqual(head["status"], highland.STATUS_HEAD_PENDING)
            self.assertIn(highland.REASON_SUPPORT_EDGE, head["reason_codes"])
        self.assertEqual(bundle["metadata"]["certified_world_heads"], 0)


# --------------------------------------------------------------------------- #
# the graph receiver is the only routing authority; unknown upstream is never washed
# --------------------------------------------------------------------------- #
class RoutingAuthorityTest(unittest.TestCase):
    def test_same_receiver_as_build_without_a_graph(self):
        """Passing the real strict receiver must equal not passing one, bit for bit.

        The previous version built an injected graph's terminal labels and — far worse —
        seeded the completeness propagation with an all-zero mask, which upgraded 556
        incomplete upstream cells of this fixture to "complete". The whole point of the
        accumulator's seed argument is that a support cut is *unknown*, not clean.
        """
        region = valley_window()
        graph = build_strict_topology(region["field"], region["resolved_mask"], origin_native_xz=region["origin_native_xz"])
        plain = highland.build_highland_sources(region)
        injected = highland.build_highland_sources(region,
                                                   graph={"receiver": graph["receiver"]})
        expected_unknown = graph["upstream_unknown_mask"].ravel().copy()
        receiver = graph["receiver"].ravel()
        for seed in np.flatnonzero(expected_unknown):
            cell = int(seed)
            while receiver[cell] >= 0:
                cell = int(receiver[cell])
                expected_unknown[cell] = True
        np.testing.assert_array_equal(~plain["arrays"]["upstream_complete"],
                                      expected_unknown.reshape(region["field"].shape))
        for name in highland.ARRAY_NAMES:
            np.testing.assert_array_equal(injected["arrays"][name], plain["arrays"][name],
                                          err_msg="array %r differs" % name)
        self.assertEqual(injected["heads"], plain["heads"])
        self.assertEqual(injected["identity_sha256"], plain["identity_sha256"])
        self.assertEqual(injected["metadata"]["routing_origin"],
                         "strict_authority_rebuilt_from_field_and_mask")
        self.assertEqual(plain["metadata"]["routing_origin"],
                         "strict_authority_rebuilt_from_field_and_mask")

    def test_an_alternative_downhill_graph_is_refused_at_build(self):
        region = valley_window()
        graph = build_strict_topology(region["field"], region["resolved_mask"], origin_native_xz=region["origin_native_xz"])
        alternate = graph["receiver"].copy()
        columns = alternate.shape[1]
        flat = alternate.reshape(-1)
        mask = region["resolved_mask"].reshape(-1)
        for cell in np.flatnonzero(mask & (flat >= 0)):
            row, column = divmod(int(cell), columns)
            if not (1 <= row < alternate.shape[0] - 1 and 1 <= column < columns - 1):
                continue
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                neighbour = (row + dr) * columns + (column + dc)
                if neighbour != int(flat[cell]) and mask[neighbour]:
                    flat[cell] = neighbour
                    break
            else:
                continue
            break
        with self.assertRaisesRegex(ValueError, "routing_graph_invalid"):
            highland.build_highland_sources(region, graph={"receiver": alternate})

    def test_unknown_upstream_reaches_downstream_and_a_hole_stays_unknown(self):
        """A window cut and a hole both dirty every cell downstream of them."""
        field = world_field(DEFAULT_ORIGIN, (90, 90), valley_terrain())
        mask = np.ones(field.shape, bool)
        mask[45, 45] = False
        bundle = highland.build_highland_sources(window(field, mask=mask))
        complete = bundle["arrays"]["upstream_complete"]
        # The hole's own cell is unresolved, so it is not "complete" either.
        self.assertFalse(complete[45, 45])
        self.assertFalse(complete[45, 60] or complete[89, 60],
                         "cells downstream of the hole and of the window cut are unknown")
        # And the support-cut border band is unknown everywhere along the edge.
        self.assertFalse(complete[0, :].any())
        self.assertFalse(complete[:, 0].any())
        self.assertFalse(complete[-1, :].any())
        self.assertFalse(complete[:, -1].any())


# --------------------------------------------------------------------------- #
# independent validation
# --------------------------------------------------------------------------- #
class ValidationTest(unittest.TestCase):
    def _bundle_and_graph(self):
        region = valley_window()
        graph = build_strict_topology(region["field"], region["resolved_mask"], origin_native_xz=region["origin_native_xz"])
        bundle = highland.build_highland_sources(region)
        return bundle, region, {"receiver": graph["receiver"]}

    def test_validate_rebuilds_regions_and_heads_independently(self):
        bundle, _region, window_arg = self._bundle_and_graph()
        report = highland.validate_highland_sources(copy.deepcopy(bundle),
                                                   window=window_arg)
        self.assertTrue(report["head_table_rederived"])
        self.assertEqual(report["regions_rederived"], len(bundle["regions"]))
        self.assertEqual(report["heads_stored"], len(bundle["heads"]))

    def test_validate_without_a_receiver_still_rebuilds_the_routing(self):
        """No receiver argument must not mean "skip the heads".

        The topology is rebuilt from the stored elevation and mask, so a bundle whose head
        count was forged is refused with or without a caller-supplied receiver. Accepting
        it silently was the hole this test closes.
        """
        bundle, _region, _window = self._bundle_and_graph()
        report = highland.validate_highland_sources(copy.deepcopy(bundle))
        self.assertTrue(report["head_table_rederived"])
        self.assertEqual(report["routing_origin"],
                         "strict_authority_rebuilt_from_field_and_mask")
        broken = copy.deepcopy(bundle)
        broken["heads"][0]["known_upstream_cells"] += 12345
        with self.assertRaisesRegex(ValueError, "head table disagrees"):
            highland.validate_highland_sources(broken)
        invented = copy.deepcopy(bundle)
        invented["heads"].append(dict(invented["heads"][0],
                                      world_xz=[invented["heads"][0]["world_xz"][0] + 1,
                                                invented["heads"][0]["world_xz"][1]]))
        with self.assertRaisesRegex(ValueError, "head table disagrees|head_flags"):
            highland.validate_highland_sources(invented)

    def test_tampered_region_member_is_refused(self):
        bundle, _region, window_arg = self._bundle_and_graph()
        broken = copy.deepcopy(bundle)
        cells = broken["arrays"]["region_cells"]
        cells[0] = [cells[0, 0] + 1, cells[0, 1]]
        with self.assertRaisesRegex(ValueError, "region_index|region_cells|disagrees"):
            highland.validate_highland_sources(broken, window=window_arg)

    def test_tampered_area_is_refused(self):
        bundle, _region, window_arg = self._bundle_and_graph()
        broken = copy.deepcopy(bundle)
        broken["regions"][0]["area_m2"] = broken["regions"][0]["area_m2"] * 2.0
        with self.assertRaisesRegex(ValueError, "area_m2|disagrees"):
            highland.validate_highland_sources(broken, window=window_arg)

    def test_tampered_status_is_refused(self):
        bundle, _region, window_arg = self._bundle_and_graph()
        broken = copy.deepcopy(bundle)
        broken["regions"][0]["status"] = highland.STATUS_REGION_PENDING
        with self.assertRaisesRegex(ValueError, "disagrees"):
            highland.validate_highland_sources(broken, window=window_arg)

    def test_tampered_head_is_refused(self):
        bundle, _region, window_arg = self._bundle_and_graph()
        self.assertTrue(bundle["heads"])
        broken = copy.deepcopy(bundle)
        broken["heads"][0]["known_upstream_cells"] += 1
        with self.assertRaisesRegex(ValueError, "head table disagrees"):
            highland.validate_highland_sources(broken, window=window_arg)

    def test_tampered_count_array_is_refused(self):
        bundle, _region, window_arg = self._bundle_and_graph()
        broken = copy.deepcopy(bundle)
        broken["arrays"]["known_upstream_cells"][0, 0] += 1
        with self.assertRaisesRegex(ValueError, "known_upstream_cells"):
            highland.validate_highland_sources(broken, window=window_arg)

    def test_certified_water_claim_is_refused(self):
        bundle, _region, window_arg = self._bundle_and_graph()
        broken = copy.deepcopy(bundle)
        broken["metadata"]["rainfall_supported"] = "rainfall_supported"
        with self.assertRaisesRegex(ValueError, "rainfall_supported"):
            highland.validate_highland_sources(broken, window=window_arg)
        second = copy.deepcopy(bundle)
        second["metadata"]["perennial_flow_certified"] = True
        with self.assertRaisesRegex(ValueError, "perennial"):
            highland.validate_highland_sources(second, window=window_arg)

    def test_a_relaxed_parameter_in_a_bundle_is_refused(self):
        bundle, _region, window_arg = self._bundle_and_graph()
        broken = copy.deepcopy(bundle)
        broken["metadata"]["parameters"]["min_head_upstream_cells"] = 2
        with self.assertRaisesRegex(ValueError, "undeclared_rule"):
            highland.validate_highland_sources(broken, window=window_arg)

    def test_a_forged_receiver_is_refused(self):
        bundle, _region, _window = self._bundle_and_graph()
        shape = bundle["arrays"]["elevation_m"].shape
        forged = np.arange(shape[0] * shape[1], dtype=np.int64).reshape(shape)
        with self.assertRaisesRegex(ValueError, "routing_graph_invalid"):
            highland.validate_highland_sources(bundle, window={"receiver": forged})

    def test_a_receiver_that_is_not_the_strict_d8_is_refused(self):
        """Adjacency alone is not the rule: an alternative downhill graph is refused.

        The forged graph below satisfies every adjacency check the previous version made
        (self edges and non-neighbours removed), so only a comparison against the one
        strict kernel can catch it.
        """
        bundle, region, _window = self._bundle_and_graph()
        shape = bundle["arrays"]["elevation_m"].shape
        graph = build_strict_topology(region["field"], region["resolved_mask"], origin_native_xz=region["origin_native_xz"])
        alternate = graph["receiver"].copy()
        columns = shape[1]
        flat = alternate.reshape(-1)
        mask = region["resolved_mask"].reshape(-1)
        # Take one interior cell and send it to a *different* legal D8 neighbour.
        live = np.flatnonzero(mask & (flat >= 0))
        changed = 0
        for cell in live:
            row, column = divmod(int(cell), columns)
            if not (1 <= row < shape[0] - 1 and 1 <= column < columns - 1):
                continue
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1),
                           (1, -1), (1, 1)):
                neighbour = (row + dr) * columns + (column + dc)
                if neighbour != int(flat[cell]) and mask[neighbour]:
                    flat[cell] = neighbour
                    changed += 1
                    break
            if changed:
                break
        self.assertEqual(changed, 1)
        self.assertFalse(np.array_equal(alternate, graph["receiver"]))
        with self.assertRaisesRegex(ValueError, "routing_graph_invalid"):
            highland.validate_highland_sources(bundle, window={"receiver": alternate})


# --------------------------------------------------------------------------- #
# the identity digest and the record tables are both claims; both are checked
# --------------------------------------------------------------------------- #
class SealedClaimTest(unittest.TestCase):
    """A re-sealed digest covers whatever it was resealed over, so records are checked too."""

    def _bundle(self):
        # A fixture whose reject table is non-empty: two crossings collide, so the loser
        # is one row and the pending region is another. A cleaner fixture would make a
        # "delete a row" test vacuous.
        return highland.build_highland_sources(twin_window(140))

    def _reseal(self, broken):
        broken["identity_sha256"] = highland.identity(broken["arrays"],
                                                     broken["metadata"])
        return broken

    def test_a_missing_or_wrong_identity_digest_is_refused(self):
        bundle = self._bundle()
        broken = copy.deepcopy(bundle)
        broken["identity_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "identity_sha256"):
            highland.validate_highland_sources(broken)
        truncated = copy.deepcopy(bundle)
        truncated["identity_sha256"] = truncated["identity_sha256"][:32]
        with self.assertRaisesRegex(ValueError, "identity_sha256"):
            highland.validate_highland_sources(truncated)

    def test_an_edited_metadata_with_a_resealed_digest_is_refused(self):
        """A forged source digest is caught by the field check, not hidden by the seal."""
        broken = self._reseal(self._bundle())
        broken["metadata"]["source"]["field_mask_sha256"] = "f" * 64
        broken = self._reseal(broken)
        with self.assertRaisesRegex(ValueError, "field_mask_sha256"):
            highland.validate_highland_sources(broken)

    def test_a_deleted_or_edited_reject_row_is_refused_even_resealed(self):
        broken = self._bundle()
        self.assertTrue(len(broken["rejects"]) >= 1)
        broken["rejects"] = broken["rejects"][1:]
        self._reseal(broken)
        with self.assertRaisesRegex(ValueError, "reject table"):
            highland.validate_highland_sources(broken)
        invented = self._bundle()
        invented["rejects"].append({"reason_codes": ["spacing_suppressed"],
                                    "region_id": "hsr-forged",
                                    "world_xz": [1, 1],
                                    "known_upstream_cells": 1,
                                    "kept_world_xz": [0, 0],
                                    "distance_m": 1.0, "required_m": 600.0,
                                    "suppressor_complete": True, "decided": True})
        self._reseal(invented)
        with self.assertRaisesRegex(ValueError, "reject table"):
            highland.validate_highland_sources(invented)

    def test_an_edited_census_with_a_resealed_digest_is_refused(self):
        broken = self._bundle()
        broken["metadata"]["head_census"]["rejected_spacing"] += 1
        self._reseal(broken)
        with self.assertRaisesRegex(ValueError, "head_census"):
            highland.validate_highland_sources(broken)
        regions = self._bundle()
        regions["metadata"]["region_census"]["region_member_cells"] += 1
        self._reseal(regions)
        with self.assertRaisesRegex(ValueError, "region_census"):
            highland.validate_highland_sources(regions)

    def test_a_forged_certified_head_count_is_refused(self):
        broken = self._bundle()
        broken["metadata"]["certified_world_heads"] += 1
        self._reseal(broken)
        with self.assertRaisesRegex(ValueError, "certified_world_heads"):
            highland.validate_highland_sources(broken)

    def test_a_smaller_legal_budget_is_accepted_and_a_bigger_one_refused(self):
        region = valley_window()
        cells = region["field"].size
        smaller = highland.build_highland_sources(region, max_cells=cells)
        self.assertEqual(smaller["metadata"]["max_cells"], cells)
        self.assertTrue(highland.validate_highland_sources(smaller)["head_table_rederived"])
        broken = copy.deepcopy(self._bundle())
        broken["metadata"]["max_cells"] = highland.DEFAULT_MAX_CELLS + 1
        self._reseal(broken)
        with self.assertRaisesRegex(ValueError, "budget_exceeded"):
            highland.validate_highland_sources(broken)


# --------------------------------------------------------------------------- #
# input immutability and the declared stage boundary
# --------------------------------------------------------------------------- #
class InputAndStageTest(unittest.TestCase):
    def test_inputs_are_not_mutated_and_stored_arrays_do_not_alias(self):
        region = valley_window()
        field = region["field"].copy()
        mask = region["resolved_mask"].copy()
        origin = list(region["origin_native_xz"])
        shape = list(region["shape_zx"])
        bundle = highland.build_highland_sources(region)
        np.testing.assert_array_equal(region["field"], field)
        np.testing.assert_array_equal(region["resolved_mask"], mask)
        self.assertEqual(region["origin_native_xz"], origin)
        self.assertEqual(region["shape_zx"], shape)
        for name, value in bundle["arrays"].items():
            self.assertFalse(np.shares_memory(value, region["field"]),
                             "array %r aliases the input field" % name)
        before = hashlib.sha256(region["field"].tobytes()).hexdigest()
        bundle["arrays"]["elevation_m"][0, 0] = -12345.0
        self.assertEqual(before, hashlib.sha256(region["field"].tobytes()).hexdigest())

    def test_bundle_reports_the_geometry_only_stage(self):
        first = highland.build_highland_sources(valley_window())
        metadata = first["metadata"]
        self.assertEqual(metadata["rule_version"], highland.RULE_VERSION)
        self.assertEqual(metadata["status"], "geometry_candidates_only")
        self.assertEqual(metadata["rainfall_supported"], "rainfall_supported_pending")
        self.assertIs(metadata["perennial_flow_certified"], False)
        self.assertEqual(set(metadata["calibration"].values()),
                         {"declared_uncalibrated"})
        self.assertIn("dependency_source_sha256", metadata)
        self.assertEqual(metadata["parameters_sha256"],
                         highland.declared_rule()["parameters_sha256"])
        self.assertEqual(first["identity_sha256"],
                         highland.build_highland_sources(valley_window())["identity_sha256"])


if __name__ == "__main__":
    unittest.main()
