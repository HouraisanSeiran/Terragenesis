"""Behaviour tests for the declared 40 km area-selection rule.

These pin the *rule*, not a particular answer: the rule must reject candidates for
the right reason, and must never silently prefer a smaller basin because a larger
one was filtered by a size mismatch. That exact failure happened: the acceptance
window is 1337 nodes but the convergence remeasurement uses up to 1537, so a
candidate that fits 1337 was rejected later by the sampler -- and the tool then
accepted a 1.7 km2 basin while 43 km2 basins were refused.

A second, worse failure is pinned here too. The older version treated the saved
page's **native grid origin** (42309, 41976 -- cell indices) as metres and handed it
to `sampled_window_basin`, which computes `round(lake_metres / 30)`. Every window was
therefore placed far away from the basin it claimed to measure, and the "converged"
1.679 km2 basin was a different piece of terrain. The absolute-coordinate helpers are
asserted directly, so that confusion cannot come back silently.

Every geometric assertion states a *count or a shape*, never just "it worked": this
tool has already been burned twice by weak assertions (`len(unique) == 1` held for an
all-`-1` label field; two bowls merged into one component looked like one basin).
"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tools.scan_40km_area import (
    MARGIN_CELLS, REASON_FOOTPRINT, REASON_LABELS, REASON_UNMEASURABLE,
    SAFE_INSET_CELLS, WINDOW_NODES, NativePage, PageMosaic, SourceDisagreement,
    WindowNotCovered, acceptance_window_origin_rc, basin_converges,
    basin_fits_acceptance_window, candidate_basins, convergence_window,
    count_reasons, dominant_reason_warning, evaluate_candidates, lake_position_m,
    load_page, plan_support_tiles, tile_union_covers,
)

SPACING = 30.0
SEED = 20261020
PAGE_COLUMN, PAGE_ROW = 42309, 41976      # the archived td-window-00 native origin


def extent_from_shape(rows, columns, row0=0, column0=0):
    return (row0, row0 + rows - 1, column0, column0 + columns - 1)


class SelectionRuleTests(unittest.TestCase):
    def test_a_basin_footprint_that_fits_the_acceptance_window_is_usable(self):
        """The rule is about the basin's own footprint, not its page position."""
        usable = WINDOW_NODES - 2 * MARGIN_CELLS
        self.assertTrue(basin_fits_acceptance_window({}, extent_from_shape(
            usable, usable, row0=1900, column0=1900), (2049, 2049)))

    def test_a_basin_larger_than_the_usable_window_is_refused(self):
        usable = WINDOW_NODES - 2 * MARGIN_CELLS
        self.assertFalse(basin_fits_acceptance_window({}, extent_from_shape(
            usable + 1, 10), (2049, 2049)))
        self.assertFalse(basin_fits_acceptance_window({}, extent_from_shape(
            10, usable + 1), (2049, 2049)))

    def test_the_window_is_placed_from_the_basin_footprint(self):
        """A basin near the page edge must still be centrable in its own window."""
        extent = extent_from_shape(40, 40, row0=1980, column0=1980)
        row, column = acceptance_window_origin_rc(extent)
        # the window corner may fall outside the scanned page; that is allowed,
        # because terrain is re-read at absolute coordinates afterwards
        centre_row = (extent[0] + extent[1]) / 2.
        centre_column = (extent[2] + extent[3]) / 2.
        self.assertAlmostEqual(row + WINDOW_NODES // 2, round(centre_row), delta=1)
        self.assertAlmostEqual(column + WINDOW_NODES // 2, round(centre_column), delta=1)


# --------------------------------------------------------------------------- #
# synthetic terrain defined by absolute native coordinates only
# --------------------------------------------------------------------------- #
# `(native column, native row)` of each bowl's bed cell.
BIG_CENTRE = (940, 1000)
BIG_RADIUS = 20.0
SMALL_CENTRE = (1100, 1100)
SMALL_RADIUS = 8.0
PLATEAU_M = 260.0          # above both rims, so neighbouring bowls stay separate
BED_M = 50.0
RIM_M = 200.0


def terrain_at(column0, row0, rows, columns, *, big_offset=0.0):
    """Elevation from **absolute** native indices, so any two pages agree on overlaps.

    This mirrors the measured property of real Terrain Diffusion on this workstation
    with `world_seed=20261020`: a freshly generated 1537-node window and the archived
    2049-node page agree **bitwise** over their whole 1365x1310 overlap
    (`max |delta| = 0.0`).
    """
    column_index = np.arange(column0, column0 + columns, dtype=np.float64)[None, :]
    row_index = np.arange(row0, row0 + rows, dtype=np.float64)[:, None]
    field = np.full((rows, columns), PLATEAU_M, np.float64)
    for centre, radius, offset in ((BIG_CENTRE, BIG_RADIUS, big_offset),
                                   (SMALL_CENTRE, SMALL_RADIUS, 0.0)):
        distance = np.hypot(column_index - centre[0], row_index - centre[1])
        inside = distance <= radius
        field[inside] = BED_M + offset + (RIM_M - BED_M) * (distance[inside] / radius)
    return field


def make_page(column0, row0, rows, columns, *, seed=SEED, kind="td-native",
              big_offset=0.0):
    return NativePage(
        elevation=terrain_at(column0, row0, rows, columns, big_offset=big_offset),
        origin_m=(column0 * SPACING, row0 * SPACING), spacing_m=SPACING,
        metadata={"native_origin": [column0, row0], "world_seed": seed,
                  "artifact_kind": kind, "spacing_m": SPACING},
        origin_native=(column0, row0))


def written_page(column0, row0, size=8, metadata=None):
    """Write one synthetic page and read it back through `load_page`."""
    elevation = terrain_at(column0, row0, size, size)
    declared = metadata if metadata is not None else {
        "native_origin": [column0, row0], "world_seed": SEED,
        "artifact_kind": "td-native", "spacing_m": SPACING}
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "page.npz"
        np.savez(path, elevation_native=elevation,
                 metadata_json=np.array(json.dumps(declared)))
        return load_page(path)


class AbsoluteCoordinateTests(unittest.TestCase):
    """The bug class that made the previous run measure a different piece of terrain."""

    def test_a_native_origin_is_read_as_cell_indices_not_metres(self):
        page = written_page(PAGE_COLUMN, PAGE_ROW)
        self.assertEqual(page.origin_native, (PAGE_COLUMN, PAGE_ROW))
        self.assertAlmostEqual(page.origin_m[0], PAGE_COLUMN * SPACING, places=6)
        self.assertAlmostEqual(page.origin_m[1], PAGE_ROW * SPACING, places=6)

    def test_a_metric_origin_is_accepted_and_lists_the_same_lattice(self):
        page = written_page(PAGE_COLUMN, PAGE_ROW, metadata={
            "origin_xz": [PAGE_COLUMN * SPACING, PAGE_ROW * SPACING],
            "world_seed": SEED, "artifact_kind": "td-native", "spacing_m": SPACING})
        self.assertEqual(page.origin_native, (PAGE_COLUMN, PAGE_ROW))
        self.assertEqual(page.origin_m, (PAGE_COLUMN * SPACING, PAGE_ROW * SPACING))

    def test_a_candidate_maps_to_its_real_absolute_position(self):
        page = make_page(PAGE_COLUMN, PAGE_ROW, 8, 8)
        row, column = 1088, 823
        x, z = lake_position_m((row, column), page)
        # 42309 is a cell index, so the absolute position is 43132 cells * 30 m
        self.assertAlmostEqual(x, (PAGE_COLUMN + 823) * SPACING, places=6)
        self.assertAlmostEqual(z, (PAGE_ROW + 1088) * SPACING, places=6)
        self.assertGreater(x, 1.29e6)          # metres, not indices
        self.assertNotAlmostEqual(x, PAGE_COLUMN + 823 * SPACING, places=3)

    def test_the_convergence_window_is_the_module_own_arithmetic(self):
        page = make_page(PAGE_COLUMN, PAGE_ROW, 8, 8)
        column, row, columns, rows = convergence_window((1088, 823), page, 1537)
        self.assertEqual((columns, rows), (1537, 1537))
        self.assertEqual(column, PAGE_COLUMN + 823 - 1537 // 2)
        self.assertEqual(row, PAGE_ROW + 1088 - 1537 // 2)

    def test_a_page_without_a_seed_cannot_join_a_mosaic(self):
        page = written_page(PAGE_COLUMN, PAGE_ROW, metadata={
            "native_origin": [PAGE_COLUMN, PAGE_ROW], "spacing_m": SPACING})
        with self.assertRaises(ValueError):
            PageMosaic([page])


class MosaicAssemblyTests(unittest.TestCase):
    """Windows are assembled from absolute coordinates; geometry is asserted exactly."""

    def setUp(self):
        # scan page: native columns 900..1300, rows 900..1300
        self.scan = make_page(900, 900, 401, 401)
        # support page: native columns 800..1199, rows 800..1199
        self.support = make_page(800, 800, 400, 400)

    def relative_centre(self):
        """`centre_rc` of the big bowl as seen from the scan page."""
        return (BIG_CENTRE[1] - 900, BIG_CENTRE[0] - 900)

    def test_one_page_cannot_serve_a_window_that_leaves_its_interior(self):
        mosaic = PageMosaic([self.scan])
        rect = convergence_window(self.relative_centre(), self.scan, 129)
        self.assertEqual(rect, (876, 936, 129, 129))
        self.assertFalse(mosaic.covers(*rect))
        uncovered = mosaic.uncovered(*rect)
        self.assertEqual(len(uncovered), 1)
        # the page's usable interior starts at column 904 (4-cell inset), so
        # columns 876..903 are outside it; all 129 rows are otherwise covered
        self.assertEqual(uncovered[0]["native_column_range"], [876, 903])
        self.assertEqual(uncovered[0]["native_row_range"], [936, 1064])
        self.assertEqual(uncovered[0]["missing_cells"], 28 * 129)
        self.assertEqual(uncovered[0]["window_cells"], 129 * 129)
        with self.assertRaises(WindowNotCovered):
            mosaic.block(*rect)

    def test_two_pages_assemble_the_exact_same_terrain(self):
        mosaic = PageMosaic([self.scan, self.support])
        rect = convergence_window(self.relative_centre(), self.scan, 129)
        self.assertTrue(mosaic.covers(*rect))
        assembled = mosaic.block(*rect)
        self.assertEqual(assembled.shape, (129, 129))
        expected = terrain_at(876, 936, 129, 129)
        difference = np.abs(assembled - expected)
        self.assertEqual(float(difference.max()), 0.0)
        self.assertEqual(int((difference != 0.).sum()), 0)
        # the left 24 columns really do come from the support page
        self.assertEqual(int(mosaic.coverage(*rect).sum()), 129 * 129)
        self.assertEqual(len(list(mosaic._intersections(*rect))), 2)   # noqa: SLF001
        # the scan page supplies columns 904..999 and the support page 804..1196, so
        # their target spans overlap at 28..129; the overlap is verified bitwise
        spans = sorted((target[1].start, target[1].stop) for _, _, target, _ in
                       mosaic._intersections(*rect))                      # noqa: SLF001
        self.assertEqual(spans, [(0, 129), (28, 129)])

    def test_two_pages_overlapping_agree_and_are_copied_once(self):
        """Overlap is checked, not averaged: both pages cover columns 1000..1039."""
        mosaic = PageMosaic([self.scan, self.support])
        shared = (1000, 1000, 40, 40)
        self.assertEqual(len(list(mosaic._intersections(*shared))), 2)   # noqa: SLF001
        self.assertEqual(int(mosaic.coverage(*shared).sum()), 40 * 40)
        self.assertEqual(float(np.abs(mosaic.block(*shared)
                                      - terrain_at(1000, 1000, 40, 40)).max()), 0.0)

    def test_a_window_inside_one_page_only_touches_that_page(self):
        mosaic = PageMosaic([self.scan, self.support])
        # columns 1210..1249 are beyond the support page's interior (ends at 1196)
        inside = (1210, 1210, 40, 40)
        self.assertTrue(mosaic.covers(*inside))
        self.assertEqual(float(np.abs(mosaic.block(*inside)
                                      - terrain_at(1210, 1210, 40, 40)).max()), 0.0)
        self.assertEqual(len(list(mosaic._intersections(*inside))), 1)   # noqa: SLF001

    def test_the_page_border_ring_is_never_used(self):
        """The outer rings of a generated window are window-size dependent, so they
        are excluded rather than used: a cell either comes from a region measured to be
        window-independent, or the window is refused."""
        single = PageMosaic([self.scan])
        inside_border_ring = (900, 900, 30, 30)      # hugs the page's own corner
        self.assertFalse(single.covers(*inside_border_ring))
        self.assertEqual(single.uncovered(*inside_border_ring)[0]["missing_cells"], 900 - 26 * 26)
        inset_rect = (904, 904, 20, 20)              # clear of the 4-cell inset
        self.assertTrue(single.covers(*inset_rect))
        # and a mosaic with no inset would accept the border ring, proving the test
        # above is about `SAFE_INSET_CELLS` and not about the fixture
        self.assertTrue(PageMosaic([self.scan], inset=0).covers(*inside_border_ring))

    def test_pages_from_a_different_source_are_refused(self):
        with self.assertRaises(SourceDisagreement):
            PageMosaic([self.scan, make_page(800, 800, 400, 400, kind="analytic-30m")])
        with self.assertRaises(SourceDisagreement):
            PageMosaic([self.scan, make_page(800, 800, 400, 400, seed=SEED + 1)])

    def test_a_single_disagreeing_cell_is_refused_not_averaged(self):
        broken = NativePage(elevation=self.support.elevation + 1.0,
                            origin_m=self.support.origin_m, spacing_m=SPACING,
                            metadata=dict(self.support.metadata),
                            origin_native=self.support.origin_native)
        mosaic = PageMosaic([self.scan, broken])
        with self.assertRaises(SourceDisagreement):
            # 24 columns of this window come from the broken page
            mosaic.block(876, 936, 129, 129)


class OffPageResamplingTests(unittest.TestCase):
    """The regression: a big basin near the page rim must be measured, not dropped."""

    sizes = (33, 65, 129)
    scan_page = make_page(900, 900, 401, 401)
    support_page = make_page(800, 800, 400, 400)

    def ranked_basins(self):
        found = candidate_basins(self.scan_page.elevation, min_cells=64, spacing_m=SPACING)
        found.sort(key=lambda item: (-item["area_m2"], item["centre_rc"]))
        return found

    def test_the_fixture_is_a_big_basin_and_a_small_one(self):
        found = self.ranked_basins()
        self.assertEqual(len(found), 2)
        big, small = found
        self.assertEqual(big["centre_rc"], (BIG_CENTRE[1] - 900, BIG_CENTRE[0] - 900))
        self.assertAlmostEqual(big["bed_m"], BED_M, places=6)
        self.assertAlmostEqual(big["spill_m"], PLATEAU_M, places=6)
        # ~pi*20^2 = 1257 cells for the big bowl, ~pi*8^2 = 201 for the small one
        self.assertGreater(big["cells"], 1200)
        self.assertLess(big["cells"], 1300)
        self.assertGreater(small["cells"], 180)
        self.assertLess(small["cells"], 220)

    def test_scan_page_only_reproduces_the_old_wrong_answer(self):
        """Without support the tool must drop the big basin and keep the small one."""
        found = self.ranked_basins()
        accepted, rejected, _ = evaluate_candidates(
            found, self.scan_page, PageMosaic([self.scan_page]), limit=4, sizes=self.sizes)
        self.assertEqual([entry["cells"] for entry in accepted], [found[1]["cells"]])
        self.assertEqual([entry["reason_code"] for entry in rejected], [REASON_UNMEASURABLE])
        needed = rejected[0]["needed_window"]
        self.assertEqual(needed["nodes"], 129)
        self.assertEqual(needed["native_column_range"],
                         [BIG_CENTRE[0] - 64, BIG_CENTRE[0] + 64])
        self.assertEqual(needed["native_row_range"],
                         [BIG_CENTRE[1] - 64, BIG_CENTRE[1] + 64])
        # the big bowl's convergence window starts at column 876, and the scan
        # page's safe interior starts at 904, so 28 columns are missing (not clipped)
        self.assertEqual(rejected[0]["uncovered"][0]["missing_cells"], 28 * 129)

    def test_with_off_page_terrain_the_big_basin_wins(self):
        found = self.ranked_basins()
        mosaic = PageMosaic([self.scan_page, self.support_page])
        accepted, rejected, plan = evaluate_candidates(
            found, self.scan_page, mosaic, limit=4, sizes=self.sizes)
        self.assertEqual(len(accepted), 2, [entry.get("reason") for entry in rejected])
        chosen = accepted[0]
        # the whole point of the fix: the largest basin wins, it is the big bowl
        self.assertEqual(chosen["cells"], found[0]["cells"])
        self.assertGreater(chosen["area_km2"], accepted[1]["area_km2"] * 6)
        self.assertAlmostEqual(chosen["area_km2"], chosen["cells"] * SPACING * SPACING / 1e6)
        self.assertAlmostEqual(chosen["bed_m"], BED_M, places=6)
        self.assertAlmostEqual(chosen["spill_m"], PLATEAU_M, places=6)
        self.assertEqual(len(plan), 2)

        records = chosen["convergence_records"]
        self.assertEqual([record["size"] for record in records], [33, 65, 129])
        # the two largest windows agree on the basin cell count *and* area exactly
        self.assertEqual(records[-1]["basin_cells"], found[0]["cells"])
        self.assertEqual(records[-2]["basin_cells"], found[0]["cells"])
        self.assertEqual(records[-1]["basin_area_m2"], records[-2]["basin_area_m2"])
        self.assertEqual(float(chosen["convergence_deltas"]["area_change_m2"]), 0.0)
        self.assertFalse(records[-1]["touches_window_border"])
        self.assertTrue(records[-1]["closed_basin"])
        # the reported window origin is absolute, not page-relative
        self.assertEqual(records[-1]["origin_xz_m"],
                         [(BIG_CENTRE[0] - 64) * SPACING, (BIG_CENTRE[1] - 64) * SPACING])

    def test_a_basin_near_the_rim_is_no_longer_refused_for_being_near_the_rim(self):
        """Pin the old refusal's cause directly: the biggest window leaves the page."""
        found = self.ranked_basins()
        big = found[0]
        half = max(self.sizes) // 2
        row, column = big["centre_rc"]
        self.assertLess(min(row, column) - half, 0)   # the old code refused exactly here
        mosaic = PageMosaic([self.scan_page, self.support_page])
        convergence = basin_converges(big["centre_rc"], self.scan_page, mosaic,
                                      sizes=self.sizes)
        self.assertTrue(convergence["converged"])
        self.assertEqual(convergence["records"][-1]["basin_cells"], big["cells"])
        self.assertEqual(float(convergence["area_change_m2"]), 0.0)


class RefusalClassificationTests(unittest.TestCase):
    def test_every_refusal_has_exactly_one_declared_category(self):
        page = make_page(900, 900, 401, 401)
        found = candidate_basins(page.elevation, min_cells=64, spacing_m=SPACING)
        found.sort(key=lambda item: (-item["area_m2"], item["centre_rc"]))
        accepted, rejected, _ = evaluate_candidates(
            found, page, PageMosaic([page]), limit=4, sizes=(33, 65, 129))
        counts = count_reasons(rejected)
        self.assertEqual(sum(counts.values()), len(rejected))
        self.assertEqual(set(counts), set(REASON_LABELS))
        for entry in rejected:
            self.assertIn(entry["reason_code"], REASON_LABELS)
            self.assertTrue(entry["reason"])

    def test_a_footprint_that_cannot_fit_is_its_own_category(self):
        page = make_page(900, 900, 401, 401)
        usable = WINDOW_NODES - 2 * MARGIN_CELLS
        oversized = dict(cells=10 ** 6, area_m2=1e6 * SPACING * SPACING,
                         bed_m=1.0, spill_m=2.0, relief_m=1.0, centre_rc=(100, 100),
                         extent_rc=(0, usable, 0, 10))
        accepted, rejected, plan = evaluate_candidates(
            [oversized], page, PageMosaic([page]), limit=1, sizes=(33, 65, 129))
        self.assertEqual(accepted, [])
        self.assertEqual(rejected[0]["reason_code"], REASON_FOOTPRINT)
        self.assertEqual(plan, [])

    def test_one_category_taking_every_large_candidate_is_flagged(self):
        """The report must not present a small accepted basin as the answer."""
        rejected = [{"reason_code": REASON_UNMEASURABLE} for _ in range(4)]
        warning = dominant_reason_warning(rejected, count_reasons(rejected), 8)
        self.assertIsNotNone(warning)
        self.assertIn(REASON_UNMEASURABLE, warning)
        mixed = [{"reason_code": REASON_UNMEASURABLE},
                 {"reason_code": "not_converged"}]
        self.assertIsNone(dominant_reason_warning(mixed, count_reasons(mixed), 4))


class CoveragePlanTests(unittest.TestCase):
    def test_planned_tiles_cover_every_needed_window_by_their_interiors(self):
        rects = [(42082, 42660, 1537, 1537), (42474, 41628, 1537, 1537)]
        tiles = plan_support_tiles(rects, tile_nodes=1337, stride=1100)
        for tile in tiles:
            self.assertEqual(tile["nodes"], 1337)
        for rect in rects:
            self.assertTrue(tile_union_covers(tiles, rect))
        # a 1537 window never fits one 1337 tile, so at least 2x2 tiles are required
        self.assertGreaterEqual(len(tiles), 4)
        columns = sorted({tile["native_origin"][0] for tile in tiles})
        rows = sorted({tile["native_origin"][1] for tile in tiles})
        # origins are backed off by the inset so the first interior reaches the rect
        self.assertEqual(columns[0], 42082 - 4)
        self.assertEqual(rows[0], 41628 - 4)

    def test_a_single_tile_cannot_cover_a_1537_window(self):
        """A 1537-node window never fits one 1337-node tile's interior (1329 cells)."""
        rect = (0, 0, 1537, 1537)
        self.assertFalse(tile_union_covers([{"native_origin": [0, 0], "nodes": 1337}], rect))
        # the planner must therefore add tiles rather than claim one is enough
        tiles = plan_support_tiles([rect], tile_nodes=1337, stride=1100)
        self.assertGreaterEqual(len(tiles), 4)
        self.assertTrue(tile_union_covers(tiles, rect))

    def test_the_coverage_check_catches_a_real_gap(self):
        rect = (0, 0, 100, 100)
        # one tile whose interior spans -6..195 covers a 100-cell rect comfortably
        self.assertTrue(tile_union_covers(
            [{"native_origin": [-10, -10], "nodes": 210}], rect))
        # a tile whose own border ring would have covered it is not enough: the
        # safe interior starts 4 cells in, so columns 0..3 are missing
        self.assertFalse(tile_union_covers(
            [{"native_origin": [0, 0], "nodes": 200}], rect))
        # a 10-cell gap at columns 50..59 must be reported, not assumed covered
        self.assertFalse(tile_union_covers(
            [{"native_origin": [0, 0], "nodes": 50},
             {"native_origin": [60, 0], "nodes": 100}], rect))
        with self.assertRaises(ValueError):
            plan_support_tiles([(0, 0, 100, 100)], tile_nodes=50, stride=100)


def cone_basin(rows=200, columns=200, bottom=100.0, rim=200.0, radius_cells=25.0,
               plateau=200.0):
    """A closed bowl sitting in a flat plateau, with a rim well inside the page."""
    zs = np.arange(rows, dtype=np.float64) - rows / 2.
    xs = np.arange(columns, dtype=np.float64) - columns / 2.
    distance = np.hypot(zs[:, None], xs[None, :])
    field = np.full((rows, columns), plateau, np.float64)
    inside = distance <= radius_cells
    field[inside] = bottom + (rim - bottom) * (distance[inside] / radius_cells)
    return field


class BasinLabellingTests(unittest.TestCase):
    def test_a_basin_is_found_and_a_border_basin_is_not(self):
        field = cone_basin()
        found = candidate_basins(field, min_cells=16)
        self.assertEqual(len(found), 1)
        basin = found[0]
        self.assertAlmostEqual(basin["bed_m"], 100.0, places=6)
        self.assertGreater(basin["spill_m"], basin["bed_m"])
        # The cell count must match the depression itself, not the whole page. An
        # earlier version of the labeller let the `-1` of dry cells win every
        # minimum, so every wet cell became `-1` and the whole page collapsed into
        # one "basin" -- and a weak `len(...) == 1` assertion still passed.
        self.assertLess(basin["cells"], field.size // 4)
        self.assertGreater(basin["cells"], 16)
        # A depression whose rim is outside the page is not a closed basin.
        cut = cone_basin(rows=60, columns=60, radius_cells=80.0, plateau=200.0)
        self.assertEqual(candidate_basins(cut, min_cells=16), [])

    def test_two_separate_basins_are_labelled_separately(self):
        """Two bowls on a plateau must give two components, each sized to its bowl.

        The plateau has to be *higher* than both rims, otherwise the flat ground
        between them is itself below the rims and the two bowls are one depression.
        That is what the first version of this fixture got wrong; the ridge in the
        middle makes the separation explicit.
        """
        field = np.full((120, 200), 260.0, np.float64)      # plateau above both rims
        for centre_column, radius in ((50.0, 20.0), (150.0, 20.0)):
            zs = np.arange(120, dtype=np.float64)[:, None] - 60.0
            xs = np.arange(200, dtype=np.float64)[None, :] - centre_column
            distance = np.hypot(zs, xs)
            inside = distance <= radius
            field[inside] = 100.0 + 40.0 * distance[inside] / radius
        found = candidate_basins(field, min_cells=16)
        self.assertEqual(len(found), 2)
        for basin in found:
            self.assertAlmostEqual(basin["bed_m"], 100.0, places=6)
            # each bowl is ~pi*20^2 = 1257 cells; a page-wide component would be 24 000
            self.assertLess(basin["cells"], 2000)
            self.assertGreater(basin["cells"], 1000)

    def test_a_basin_whose_spill_equals_its_bed_is_not_a_lake(self):
        flat = np.full((60, 60), 150.0)
        self.assertEqual(candidate_basins(flat, min_cells=4), [])

    def test_loading_a_page_without_an_origin_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "page.npz"
            np.savez(path, elevation_native=np.zeros((8, 8)),
                     metadata_json=np.array(json.dumps({"spacing_m": SPACING})))
            with self.assertRaises(ValueError):
                load_page(path)


if __name__ == "__main__":
    unittest.main()
