"""Behaviour tests for cross-region consistency (spec 4.3).

Every test here states a behaviour that must hold for any page pair; none of them
reach for the real 2049 pages (those are measured by
`tools/audit_cross_region_consistency.py` and quoted in the report). The real page is
used only as the *reason* the constants exist, never as a fixture -- a test that only
passes on one .npz is a record, not a test.
"""
import numpy as np
import unittest

from terrain_pipeline.surface_rivers.metric_cross_region import (
    BORDER_BAND_CELLS, CONTACT_MARGIN_CELLS, REASON_CLOSED_BASIN, REASON_DISAGREEMENT,
    REASON_OUT_OF_TILE, REASON_UNRESOLVED_BORDER, assemble_pages, assembly_digest,
    basin_reaches_window_edge, build_digest, cumulative_quantities, derive_sub_seed,
    load_order_invariance, overlap_comparison, resolve_point, truncation_cost,
    verify_digest, window_family,
)


def forms_equal(a, b):
    """Bit-level field equality that treats NaN positions as equal.

    `np.array_equal` returns False whenever a NaN is present, which would make an
    assembly test meaningless: an assembly deliberately carries NaN in its unresolved
    cells. This compares the bit patterns and requires NaN in exactly the same places.
    """
    left = np.asarray(a, np.float64)
    right = np.asarray(b, np.float64)
    if left.shape != right.shape:
        return False
    nan_left, nan_right = np.isnan(left), np.isnan(right)
    if not np.array_equal(nan_left, nan_right):
        return False
    return np.array_equal(left[~nan_left], right[~nan_right])


def ramp(rows=40, columns=40, origin=(100, 200), shift=0.0):
    """A page whose value is a function of the **absolute** native index.

    That is what makes a page pair comparable: the same world cell must carry the same
    value in both, so a page's content depends on `origin`, not on the array index.
    """
    z = np.arange(rows)[:, None] + origin[1]
    x = np.arange(columns)[None, :] + origin[0]
    return 100.0 + 0.25 * z + 0.5 * x + shift


def elongated_basin(rows=121, columns=121, bottom_m=100.0, rim_m=160.0,
                    semi_x=28.0, semi_z=8.0):
    """One closed bowl that is much wider than it is deep in *rows*.

    The shape matters: a centred square window cuts the long axis first, so the family
    of windows genuinely goes from "truncated" to "clear", and the truncation has a
    measurable cost. A round bowl in a square page either fits immediately or never --
    which is not the behaviour under test.
    """
    zs = np.arange(rows)[:, None] - (rows - 1) / 2.
    xs = np.arange(columns)[None, :] - (columns - 1) / 2.
    radius = np.hypot(xs / semi_x, zs / semi_z)
    return bottom_m + (rim_m - bottom_m) * np.clip(radius, 0., 1.)


def basin(rows=41, columns=41, bottom_m=100.0, rim_m=140.0, rim_cells=10.0):
    """A single closed bowl in a flat plateau, so the plateau is an exact spill level."""
    zs = np.arange(rows)[:, None] - (rows - 1) / 2.
    xs = np.arange(columns)[None, :] - (columns - 1) / 2.
    radius = np.hypot(zs, xs)
    return bottom_m + (rim_m - bottom_m) * np.clip(radius / rim_cells, 0., 1.)


class OverlapComparisonTests(unittest.TestCase):
    def test_disjoint_pages_report_no_overlap_instead_of_inventing_one(self):
        result = overlap_comparison(ramp(), (100, 200), ramp(), (900, 200))
        self.assertFalse(result["overlaps"])
        self.assertIn("no native cell", result["note"])

    def test_identical_content_over_a_shared_box_is_bit_exact(self):
        a = ramp()
        b = ramp()
        result = overlap_comparison(a, (100, 200), b, (100, 200))
        self.assertTrue(result["overlaps"])
        self.assertEqual(result["differing_cells"], 0)
        self.assertTrue(result["interior_bitwise_identical"])
        self.assertEqual(result["declared_tolerance"]["border_band"]["max_abs_m"], 0.0)

    def test_difference_is_attributed_to_the_right_border_band(self):
        """A perturbation on page B's own edge must appear on B's band, not in the interior."""
        a = ramp()
        b = ramp()
        b[:, -1] += 0.5          # B's last column is B's own border (distance 0)
        result = overlap_comparison(a, (100, 200), b, (100, 200))
        self.assertEqual(result["differing_cells"], b.shape[0])
        self.assertEqual(result["max_abs_difference_m"], 0.5)
        self.assertTrue(result["interior_bitwise_identical"])
        self.assertTrue(result["differences_confined_to_border_band"])
        band_zero = next(row for row in result["per_border_band"]
                         if row["border_distance_cells"] == 0)
        self.assertEqual(band_zero["differing_cells"], b.shape[0])
        for row in result["per_border_band"]:
            if row["border_distance_cells"] > 0:
                self.assertEqual(row["differing_cells"], 0)

    def test_a_difference_in_the_interior_is_reported_as_such(self):
        """The band attribution must not excuse a real interior disagreement."""
        a = ramp()
        b = ramp()
        b[10, 10] += 1e-9
        result = overlap_comparison(a, (100, 200), b, (100, 200))
        self.assertEqual(result["interior_differing_cells"], 1)
        self.assertFalse(result["interior_bitwise_identical"])
        self.assertFalse(result["differences_confined_to_border_band"])

    def test_band_width_is_a_parameter_and_is_honoured(self):
        a = ramp()
        b = ramp()
        b[0, :] += 1.0
        narrow = overlap_comparison(a, (100, 200), b, (100, 200), border_band_cells=0)
        self.assertFalse(narrow["interior_bitwise_identical"])
        wide = overlap_comparison(a, (100, 200), b, (100, 200), border_band_cells=1)
        self.assertTrue(wide["interior_bitwise_identical"])


class AssemblyOrderTests(unittest.TestCase):
    def make_pages(self):
        left = ramp(rows=40, columns=40, origin=(100, 200))
        right = ramp(rows=40, columns=40, origin=(130, 200))
        return [("left", left, (100, 200)), ("right", right, (130, 200))]

    def test_order_permutation_does_not_change_one_bit(self):
        pages = self.make_pages()
        first = assemble_pages(pages, origin=(100, 200), shape=(40, 70),
                               order=["left", "right"])
        second = assemble_pages(pages, origin=(100, 200), shape=(40, 70),
                                order=["right", "left"])
        self.assertTrue(forms_equal(first["field"], second["field"]))
        self.assertTrue(np.array_equal(first["resolved_mask"], second["resolved_mask"]))
        self.assertEqual(assembly_digest(first), assembly_digest(second))
        self.assertEqual(first["selection_key_digest"], second["selection_key_digest"])

    def test_the_page_with_the_largest_clearance_wins(self):
        left = ramp(rows=40, columns=40, origin=(100, 200))
        right = ramp(rows=40, columns=40, origin=(130, 200))
        right = right + 1000.0        # so the winner is visible in the value
        assembly = assemble_pages([("left", left, (100, 200)),
                                   ("right", right, (130, 200))],
                                  origin=(100, 200), shape=(40, 70))
        # Columns 100..129 are supplied only by `left` or by both; where both cover,
        # the larger clearance wins. Independent of input order by construction.
        again = assemble_pages([("right", right, (130, 200)),
                                ("left", left, (100, 200))],
                               origin=(100, 200), shape=(40, 70))
        self.assertTrue(forms_equal(assembly["field"], again["field"]))
        self.assertGreater(float(np.nanmax(assembly["field"])), 1000.0)

    def test_cells_covered_only_by_a_border_band_are_left_unresolved(self):
        pages = self.make_pages()
        assembly = assemble_pages(pages, origin=(100, 200), shape=(40, 70),
                                  border_band_cells=BORDER_BAND_CELLS)
        self.assertGreater(assembly["unresolved_cells"], 0)
        self.assertEqual(assembly["unresolved_reason"], REASON_UNRESOLVED_BORDER)
        self.assertTrue(np.all(np.isnan(assembly["field"][assembly["unresolved_mask"]])))
        self.assertTrue(np.all(np.isfinite(assembly["field"][assembly["resolved_mask"]])))

    def test_an_order_that_is_not_a_permutation_is_refused(self):
        pages = self.make_pages()
        with self.assertRaises(ValueError):
            assemble_pages(pages, origin=(100, 200), shape=(40, 70),
                           order=["left", "left"])


class ChunkingTests(unittest.TestCase):
    """The spec asks for order invariance under a different *partition*, not just order.

    Splitting one page into two half-pages is a real re-chunking: the same cells arrive
    in more pieces, each with its own border. The assembled field must not change where
    the pieces still have clearance -- and where they do not, the cell must go
    unresolved rather than silently change value.
    """

    def pages(self):
        left = ramp(rows=40, columns=40, origin=(100, 200))
        right = ramp(rows=40, columns=40, origin=(130, 200))
        return [("left", left, (100, 200)), ("right", right, (130, 200))]

    def split(self):
        left, right = self.pages()[0], self.pages()[1]
        left_array = left[1]
        return [("left-a", left_array[:, :24], (100, 200)),
                ("left-b", left_array[:, 20:], (120, 200)),
                ("right", right[1], (130, 200))]

    def test_splitting_one_page_in_two_does_not_change_a_clear_interior(self):
        whole = assemble_pages(self.pages(), border_band_cells=2,
                               origin=(100, 200), shape=(40, 70))
        pieces = assemble_pages(self.split(), border_band_cells=2,
                                origin=(100, 200), shape=(40, 70))
        common = whole["resolved_mask"] & pieces["resolved_mask"]
        self.assertTrue(common.any())
        self.assertTrue(forms_equal(whole["field"][common], pieces["field"][common]))

    def test_rechunking_may_shrink_the_resolved_set_but_never_invents_a_value(self):
        whole = assemble_pages(self.pages(), border_band_cells=2,
                               origin=(100, 200), shape=(40, 70))
        pieces = assemble_pages(self.split(), border_band_cells=2,
                                origin=(100, 200), shape=(40, 70))
        # Re-chunking adds borders, so it can only lose resolved cells, never gain them.
        self.assertLessEqual(pieces["resolved_cells"], whole["resolved_cells"])
        only_split = pieces["resolved_mask"] & ~whole["resolved_mask"]
        self.assertFalse(only_split.any())

    def test_a_wider_band_is_a_stricter_partition_and_keeps_values_ordered(self):
        pages = self.pages()
        narrow = assemble_pages(pages, border_band_cells=0, origin=(100, 200), shape=(40, 70))
        wide = assemble_pages(pages, border_band_cells=6, origin=(100, 200), shape=(40, 70))
        self.assertGreaterEqual(narrow["resolved_cells"], wide["resolved_cells"])
        common = narrow["resolved_mask"] & wide["resolved_mask"]
        self.assertTrue(forms_equal(narrow["field"][common], wide["field"][common]))


class CumulativeQuantityTests(unittest.TestCase):
    def test_integer_counts_and_extrema_are_reproduced_across_orders(self):
        pages = [("a", basin(), (0, 0)), ("b", basin(), (20, 0)), ("c", basin(), (40, 0))]
        orders = [["a", "b", "c"], ["c", "b", "a"], ["b", "a", "c"]]
        result = load_order_invariance(pages, orders, origin=(0, 0), shape=(41, 81),
                                       border_band_cells=2)
        self.assertTrue(result["comparison"]["identical_digests"])
        self.assertTrue(result["comparison"]["identical_quantities"])
        self.assertEqual(result["float_quantity_spread"], {})
        reference = result["runs"][0]["quantities"]
        self.assertGreater(reference["resolved_cells"], 0)
        self.assertGreater(reference["depression_count"], 0)
        for run in result["runs"]:
            self.assertEqual(run["quantities"]["depression_count"], reference["depression_count"])
            self.assertEqual(run["quantities"]["largest_depression_cells"],
                             reference["largest_depression_cells"])
            self.assertEqual(run["quantities"]["largest_spill_level_m"],
                             reference["largest_spill_level_m"])

    def test_a_float_reduction_reports_its_own_spread_rather_than_claiming_equality(self):
        field = ramp(rows=60, columns=60, origin=(0, 0))
        valid = np.ones(field.shape, bool)
        forward = cumulative_quantities(field, valid)
        self.assertEqual(forward["sum_order_spread_m"], 0.0)
        reverse = np.arange(field.size - 1, -1, -1)
        permuted = cumulative_quantities(field, valid, float_order=reverse)
        self.assertEqual(permuted["sum_order_used"], "caller-supplied permutation")
        # A spread is reported either way; it is never assumed to be zero.
        self.assertIsNotNone(permuted["sum_order_spread_m"])
        self.assertGreaterEqual(permuted["sum_order_spread_m"], 0.0)

    def test_unresolved_holes_are_not_drains(self):
        """A hole punched in the support must not lower the region's spill level."""
        field = basin()
        valid = np.ones(field.shape, bool)
        whole = cumulative_quantities(field, valid)
        holed = valid.copy()
        holed[0, 0] = False       # one border cell removed
        after = cumulative_quantities(field, holed)
        self.assertEqual(after["depression_count"], whole["depression_count"])
        self.assertEqual(after["largest_spill_level_m"], whole["largest_spill_level_m"])

    def test_a_flood_with_no_seed_is_refused_instead_of_returning_zero(self):
        field = ramp(rows=10, columns=10)
        with self.assertRaises(ValueError):
            cumulative_quantities(field, np.zeros(field.shape, bool))


class WindowEdgeIsNotAnOutletTests(unittest.TestCase):
    def test_rim_clearance_is_reported_in_cells_and_flagged(self):
        touching = np.zeros((41, 41), bool)
        touching[:, 0] = True            # reaches the array edge
        close = basin_reaches_window_edge(touching, contact_margin_cells=CONTACT_MARGIN_CELLS)
        self.assertEqual(close["rim_clearance_cells"], 0)
        self.assertTrue(close["suspect_window_truncation"])
        self.assertTrue(close["touches_border_by_hypsometry_ring_2"])
        inner = np.zeros((41, 41), bool)
        inner[10:30, 10:30] = True
        clear = basin_reaches_window_edge(inner, contact_margin_cells=CONTACT_MARGIN_CELLS)
        self.assertEqual(clear["rim_clearance_cells"], 10)
        self.assertFalse(clear["suspect_window_truncation"])

    def test_the_ring_2_test_can_be_false_while_the_rim_is_cut(self):
        """The real page produces exactly this: fill stops 2 cells short of the edge.

        A basin whose depression component ends two cells from the border is *not* a
        closed basin on this page -- the fill simply did not climb over the cut rim --
        yet `_touches_border` only inspects the ring at index 2 and returns False.
        """
        mask = np.zeros((41, 41), bool)
        mask[5:38, 5:38] = True          # ends 3 cells from every edge
        report = basin_reaches_window_edge(mask, contact_margin_cells=CONTACT_MARGIN_CELLS)
        self.assertEqual(report["rim_clearance_cells"], 3)
        self.assertFalse(report["touches_border_by_hypsometry_ring_2"])
        self.assertTrue(report["suspect_window_truncation"])

    def test_the_hypsometry_threshold_is_one_cell_not_two(self):
        """`inner[2:-2]` flags clearance 0 and 1; at clearance 2 it is already silent.

        Reading the slice as "tolerates two cells" is a one-off error, and it matters:
        the report has to say what the test actually does. This pins the measured
        threshold so the prose cannot drift away from the code.
        """
        from terrain_pipeline.lake import _touches_border as _touches_border

        for clearance in (0, 1):
            mask = np.zeros((21, 21), bool)
            mask[clearance:21 - clearance, clearance:21 - clearance] = True
            self.assertTrue(_touches_border(mask), clearance)
            report = basin_reaches_window_edge(mask, contact_margin_cells=CONTACT_MARGIN_CELLS)
            self.assertEqual(report["hypsometry_test_threshold_cells"], 1)
            self.assertTrue(report["touches_border_by_hypsometry_ring_2"])
        for clearance in (2, 3):
            mask = np.zeros((21, 21), bool)
            mask[clearance:21 - clearance, clearance:21 - clearance] = True
            self.assertFalse(_touches_border(mask), clearance)
            report = basin_reaches_window_edge(mask, contact_margin_cells=CONTACT_MARGIN_CELLS)
            self.assertFalse(report["touches_border_by_hypsometry_ring_2"])

    def test_the_margin_is_inclusive_of_the_band_it_was_derived_from(self):
        """`suspect` is `clearance < margin`, so a rim exactly at the margin is accepted."""
        mask = np.zeros((41, 41), bool)
        mask[CONTACT_MARGIN_CELLS:41 - CONTACT_MARGIN_CELLS,
             CONTACT_MARGIN_CELLS:41 - CONTACT_MARGIN_CELLS] = True
        report = basin_reaches_window_edge(mask, contact_margin_cells=CONTACT_MARGIN_CELLS)
        self.assertEqual(report["rim_clearance_cells"], CONTACT_MARGIN_CELLS)
        self.assertFalse(report["suspect_window_truncation"])

    def test_a_cut_basin_reports_a_lower_spill_level_than_the_uncut_one(self):
        """The trap, in miniature: the truncated number is plausible and wrong."""
        page = elongated_basin()
        family = window_family(page, (0, 0), (60, 60), sizes=(41, 61, 81, 101),
                               contact_margin_cells=CONTACT_MARGIN_CELLS)
        self.assertTrue(family["suspect_sizes"], "the small windows must be flagged as truncated")
        cost = truncation_cost(family)
        self.assertTrue(cost["rows"])
        self.assertIn(cost["accepted_size"], family["accepted_sizes"])
        under = [row for row in cost["rows"] if row["verdict"] == "under_reported"]
        self.assertTrue(under, "at least one truncated window must under-report the spill level")
        for row in under:
            self.assertGreater(row["under_report_m"], 0.0)
            self.assertLess(row["reported_spill_level_m"], row["accepted_spill_level_m"])
            self.assertLess(row["reported_basin_area_km2"], row["accepted_basin_area_km2"])

    def test_a_truncated_window_that_happens_to_agree_is_still_refused(self):
        """Agreement is not evidence of clearance -- this is the trap's second half."""
        page = elongated_basin()
        family = window_family(page, (0, 0), (60, 60), sizes=(41, 61, 81, 101),
                               contact_margin_cells=CONTACT_MARGIN_CELLS)
        cost = truncation_cost(family)
        harmless = [row for row in cost["rows"] if row["verdict"] == "harmless_on_this_terrain"]
        self.assertTrue(harmless, "size 61 clears the fill but not the declared rim margin")
        for row in harmless:
            self.assertEqual(row["under_report_m"], 0.0)
            self.assertLess(row["rim_clearance_cells"], CONTACT_MARGIN_CELLS)

    def test_the_accepted_window_family_converges(self):
        page = elongated_basin()
        family = window_family(page, (0, 0), (60, 60), sizes=(41, 61, 81, 101))
        self.assertEqual(family["suspect_sizes"], [41, 61])
        self.assertTrue(family["converged_between_largest_accepted"])
        self.assertEqual(family["level_spread_m_between_largest_accepted"], 0.0)
        self.assertEqual(family["first_accepted_size"], 81)

    def test_the_family_names_where_the_hypsometry_verdict_is_wrong(self):
        """At size 61 the weak test says closed while the rim is only 3 cells out."""
        page = elongated_basin()
        family = window_family(page, (0, 0), (60, 60), sizes=(41, 61, 81, 101))
        self.assertIn(61, family["hypsometry_only_says_closed"])
        record = next(item for item in family["records"] if item["size"] == 61)
        self.assertTrue(record["closed_basin_by_hypsometry"])
        self.assertFalse(record["closed_basin"])
        self.assertLess(record["rim_clearance_cells"], CONTACT_MARGIN_CELLS)


class PointResolutionTests(unittest.TestCase):
    def pages(self):
        return [("a", ramp(rows=40, columns=40, origin=(0, 0)), (0, 0)),
                ("b", ramp(rows=40, columns=40, origin=(20, 0)), (20, 0))]

    def test_uncovered_point_is_refused_as_out_of_tile(self):
        report = resolve_point(self.pages(), (500, 5))
        self.assertFalse(report["resolved"])
        self.assertEqual(report["reason"], REASON_OUT_OF_TILE)
        self.assertIsNone(report["value_m"])

    def test_border_band_only_point_is_refused_as_unresolved_border(self):
        # Native x=5 is inside page `a` but only 5 cells from its border, and page `b`
        # does not reach it at all, so no page supplies it with clearance.
        report = resolve_point(self.pages(), (5, 5))
        self.assertFalse(report["resolved"])
        self.assertEqual(report["reason"], REASON_UNRESOLVED_BORDER)

    def test_interior_point_is_accepted_and_the_evidence_lists_every_page(self):
        report = resolve_point(self.pages(), (30, 20))
        self.assertTrue(report["resolved"])
        self.assertEqual(report["reason"], REASON_CLOSED_BASIN)
        self.assertEqual(len(report["candidates"]), 2)
        self.assertAlmostEqual(report["value_m"], float(ramp(origin=(0, 0))[20, 30]))

    def test_two_pages_that_disagree_are_neither_averaged_nor_picked(self):
        pages = [("a", ramp(rows=40, columns=40, origin=(0, 0)), (0, 0)),
                 ("b", ramp(rows=40, columns=40, origin=(0, 0)) + 1.0, (0, 0))]
        report = resolve_point(pages, (20, 20))
        self.assertFalse(report["resolved"])
        self.assertEqual(report["reason"], REASON_DISAGREEMENT)
        self.assertEqual(len(report["disagreeing_values_m"]), 2)


class ColdReadDigestTests(unittest.TestCase):
    def pages(self):
        return [("a", ramp(rows=30, columns=30, origin=(0, 0)), (0, 0), {"seed": 20261020}),
                ("b", ramp(rows=30, columns=30, origin=(28, 0)), (28, 0), {"seed": 20261020})]

    def test_digest_verifies_after_a_fresh_load(self):
        digest = build_digest(world_seed=20261020, pages=self.pages(), spacing_m=30.0)
        fresh = [(key, np.array(array), origin, metadata)
                 for key, array, origin, metadata in self.pages()]
        verdict = verify_digest(digest, pages=fresh, spacing_m=30.0)
        self.assertTrue(verdict["verified"], verdict["problems"])
        self.assertEqual(verdict["recomputed_sha256"], digest["digest_sha256"])

    def test_a_substituted_page_is_rejected_not_recomputed(self):
        digest = build_digest(world_seed=20261020, pages=self.pages(), spacing_m=30.0)
        tampered = [("a", ramp(rows=30, columns=30, origin=(0, 0)) + 1e-3, (0, 0), {}),
                    ("b", ramp(rows=30, columns=30, origin=(28, 0)), (28, 0), {})]
        verdict = verify_digest(digest, pages=tampered, spacing_m=30.0)
        self.assertFalse(verdict["verified"])
        self.assertTrue(any("elevation sha256" in problem for problem in verdict["problems"]))

    def test_a_shifted_origin_is_rejected(self):
        digest = build_digest(world_seed=20261020, pages=self.pages(), spacing_m=30.0)
        shifted = [("a", ramp(rows=30, columns=30, origin=(0, 0)), (0, 1), {})]
        verdict = verify_digest(digest, pages=shifted, spacing_m=30.0)
        self.assertFalse(verdict["verified"])
        self.assertTrue(any("not supplied" in problem or "origin" in problem
                            for problem in verdict["problems"]))

    def test_digest_body_is_self_consistent(self):
        digest = build_digest(world_seed=20261020, pages=self.pages(), spacing_m=30.0)
        tampered = dict(digest)
        tampered["world_seed"] = 20261021
        verdict = verify_digest(tampered, pages=self.pages(), spacing_m=30.0)
        self.assertFalse(verdict["verified"])
        self.assertTrue(any("digest_sha256" in problem for problem in verdict["problems"]))

    def test_sub_seed_derivation_is_reproducible_and_purpose_separated(self):
        self.assertEqual(derive_sub_seed(20261020, "climate"), derive_sub_seed(20261020, "climate"))
        self.assertNotEqual(derive_sub_seed(20261020, "climate"),
                            derive_sub_seed(20261020, "rainfall"))
        self.assertNotEqual(derive_sub_seed(20261020, "climate"),
                            derive_sub_seed(20261021, "climate"))


if __name__ == "__main__":
    unittest.main()
