"""Behaviour tests for the 30 m base and the terrain-driven lake curves.

These are external-behaviour tests: same coordinate same value, monotone V(h),
monotone A(h), reproducible storage comparison, and a mosaic with no seam step.
They deliberately do not import the scoring code of the builder.
"""
import json
import math
import unittest

import numpy as np

from terrain_pipeline.td_source import FINE_SPACING_M, FineTerrainField, adjacent_step_m, analytic_fine_field, bilinear_sample, compose_fine_terrain, edge_taper, fine_axes, mosaic_detail_m, seam_diagnostics, td_detail_band
from terrain_pipeline.lake import CONVERGENCE_AREA_TOLERANCE as CONVERGENCE_AREA_TOLERANCE
from terrain_pipeline.lake import CONVERGENCE_LEVEL_TOLERANCE as CONVERGENCE_LEVEL_TOLERANCE
from terrain_pipeline.lake import build_terrain_lake as build_terrain_lake
from terrain_pipeline.lake import contraction_evidence as contraction_evidence
from terrain_pipeline.lake import depression_component as depression_component
from terrain_pipeline.lake import depression_hierarchy as depression_hierarchy
from terrain_pipeline.lake import hypsometry_curve as hypsometry_curve
from terrain_pipeline.lake import sampled_levels as sampled_levels
from terrain_pipeline.lake import sampled_window_basin as sampled_window_basin
from terrain_pipeline.lake import LakeStorage as LakeStorage

WORLD_SEED = 20261020
ORIGIN = (1_297_020.0, 1_276_800.0)


def crater(rows=81, columns=81, bottom_m=100.0, rim_m=140.0, rim_radius_cells=12.0,
           linear=True):
    """A closed bowl inside a flat plateau: a genuine single depression.

    Inside `rim_radius_cells` the elevation rises from `bottom_m` to `rim_m`;
    outside it is the flat plateau at `rim_m`, so the plateau is the spill level
    and the interior is closed.

    With `linear=True` the inner profile is a straight cone, which makes the
    wetted radius proportional to the depth and therefore the wetted area
    proportional to the depth squared. That is what makes `dA/dh` fall with the
    level -- the contraction the report has to exhibit. It is produced by this
    fixture's geometry, and none of it is written into the hypsometry code.
    """
    zs = np.arange(rows, dtype=np.float64) - (rows - 1) / 2.
    xs = np.arange(columns, dtype=np.float64) - (columns - 1) / 2.
    radius = np.hypot(zs[:, None], xs[None, :])
    fraction = np.clip(radius / rim_radius_cells, 0., 1.)
    shaped = fraction if linear else fraction ** 2
    return bottom_m + (rim_m - bottom_m) * shaped


def tilting_slope(rows=41, columns=41, base_m=100.0, gradient=1.0):
    """A plane that drains: every cell has a descending path off the window."""
    zs = np.arange(rows, dtype=np.float64)
    xs = np.arange(columns, dtype=np.float64)
    return base_m + zs[:, None] * gradient + xs[None, :] * gradient


def bowl_larger_than_the_window(rows=41, columns=41, bottom_m=100.0, rim_m=400.0):
    """A basin whose rim lies outside the window: its fill reaches the border.

    The cone must still be *rising* at the window edge and must not have reached
    `rim_m` there: the edge has to sit strictly between the bed and the rim, so
    the depression is still open when the window ends.

    Both extremes were measured and rejected before this form was chosen:
    radius scale `rows * 4` puts the edge at ~139 m, i.e. a *closed* bowl inside
    the window (1245 cells, no border contact); radius scale `rows / 4` puts the
    edge at 400 m, i.e. also closed (333 cells). A radius scale of `rows` puts the
    edge at ~257 m -- rising, below the rim, still open.
    """
    zs = np.arange(rows, dtype=np.float64) - (rows - 1) / 2.
    xs = np.arange(columns, dtype=np.float64) - (columns - 1) / 2.
    radius = np.hypot(zs[:, None], xs[None, :])
    return bottom_m + (rim_m - bottom_m) * np.clip(radius / float(rows), 0., 1.)


class AnalyticBaseTests(unittest.TestCase):
    def test_the_same_coordinate_gives_the_same_value_whatever_the_window(self):
        big, _ = analytic_fine_field(WORLD_SEED, ORIGIN, (64, 64))
        small, _ = analytic_fine_field(WORLD_SEED, (ORIGIN[0] + 3 * FINE_SPACING_M,
                                                   ORIGIN[1] + 5 * FINE_SPACING_M), (16, 16))
        np.testing.assert_array_equal(big[5:21, 3:19], small)

    def test_blockwise_sampling_does_not_depend_on_the_guard_block_size(self):
        shape = (8, 300_000)
        whole, _ = analytic_fine_field(WORLD_SEED, ORIGIN, (8, 300_000))
        first, _ = analytic_fine_field(WORLD_SEED, ORIGIN, (4, 300_000))
        second, _ = analytic_fine_field(WORLD_SEED, (ORIGIN[0], ORIGIN[1] + 4 * FINE_SPACING_M),
                                        (4, 300_000))
        np.testing.assert_array_equal(whole, np.concatenate([first, second]))

    def test_the_field_is_independent_of_the_seed_it_is_asked_for(self):
        first, _ = analytic_fine_field(WORLD_SEED, ORIGIN, (16, 16))
        other, _ = analytic_fine_field(WORLD_SEED, ORIGIN, (16, 16))
        np.testing.assert_array_equal(first, other)
        changed, _ = analytic_fine_field(WORLD_SEED + 1, ORIGIN, (16, 16))
        self.assertGreater(float(np.abs(changed - first).max()), 1e-6,
                           "a different world seed must be a different world")

    def test_a_10_km_page_costs_tens_of_metres_against_the_same_function(self):
        fine, _ = analytic_fine_field(WORLD_SEED, ORIGIN, (129, 129))
        step = 10_000.0
        width = 3
        gx = ORIGIN[0] + np.arange(width) * step
        gz = ORIGIN[1] + np.arange(width) * step
        east, south = np.meshgrid(gx, gz)
        from diffusion.geography_physical import sample_physical
        page = np.asarray(sample_physical(east, south, WORLD_SEED)[0], np.float64)
        xs, zs = fine_axes(ORIGIN, fine.shape)
        interpolated = bilinear_sample(page, ORIGIN, step, xs, zs)
        rms = float(np.sqrt(((fine - interpolated) ** 2).mean()))
        self.assertGreater(rms, 10.0, "a 10 km page must not be assumed equal to 30 m")
        self.assertLess(rms, fine.std() * 2.0)


class DetailBandTests(unittest.TestCase):
    def test_the_edge_taper_is_exactly_zero_on_the_border(self):
        weight = edge_taper((33, 33), FINE_SPACING_M, 300.0)
        self.assertEqual(float(weight[[0, -1], :].max()), 0.0)
        self.assertEqual(float(weight[:, [0, -1]].max()), 0.0)
        self.assertEqual(float(weight[16, 16]), 1.0)

    def test_the_injected_term_vanishes_on_the_border(self):
        base, _ = analytic_fine_field(WORLD_SEED, ORIGIN, (64, 64))
        band, weight, record = td_detail_band(base * 0.5 + np.sin(np.arange(64))[:, None],
                                              base, FINE_SPACING_M)
        self.assertEqual(float(np.abs(band[[0, -1], :]).max()), 0.0)
        self.assertEqual(float(np.abs(band[:, [0, -1]]).max()), 0.0)
        self.assertIn("uncalibrated", record["status"])

    def test_a_single_contribution_inside_the_taper_is_reproduced(self):
        detail = np.full((9, 9), 3.0)
        weight = edge_taper((9, 9), FINE_SPACING_M, 90.0)
        composed, coverage = mosaic_detail_m([(detail, weight)])
        self.assertEqual(float(composed[4, 4]), 3.0)
        self.assertEqual(float(composed[0, 4]), 0.0)

    def test_two_identical_windows_average_to_the_same_detail(self):
        detail = np.full((9, 9), 5.0)
        weight = np.ones((9, 9))
        composed, coverage = mosaic_detail_m([(detail, weight), (detail, weight)])
        np.testing.assert_allclose(composed, detail)
        np.testing.assert_allclose(coverage, 2.0)

    def test_a_border_of_a_window_never_leaves_a_step_in_the_composite(self):
        base, _ = analytic_fine_field(WORLD_SEED, ORIGIN, (48, 48))
        detail = np.zeros((48, 48))
        detail[...] = base.std() * 3.0
        weight = edge_taper((48, 48), FINE_SPACING_M, 600.0)
        composed, _ = mosaic_detail_m([(detail, weight)])
        self.assertEqual(float(np.abs(composed[[0, -1], :]).max()), 0.0)
        steps = seam_diagnostics(composed, np.ones((48, 48), bool))
        self.assertLessEqual(steps["across_seam_max_m"], steps["interior"]["max_m"] + 1e-9)


class TerrainLakeTests(unittest.TestCase):
    def _lake(self):
        field = crater()
        radius = (field.shape[0] - 1) // 2
        return build_terrain_lake(field, (0.0, 0.0), FINE_SPACING_M, (radius, radius),
                                  source_identity_sha256="b" * 64)

    def test_a_closed_bowl_is_detected_and_bounded_by_its_rim(self):
        lake = self._lake()
        self.assertTrue(lake.closed_basin)
        self.assertFalse(lake.touches_window_border)
        self.assertAlmostEqual(lake.bed_min_m, 100.0, places=9)
        self.assertEqual(lake.spill_level_m, 140.0)
        self.assertAlmostEqual(lake.relief_m, 40.0, places=9)

    def test_the_store_is_the_existing_lake_storage_class(self):
        lake = self._lake()
        self.assertIsInstance(lake.storage, LakeStorage)
        self.assertEqual(lake.storage.cell_area_m2[0], FINE_SPACING_M ** 2)

    def test_volume_is_monotone_nondecreasing_and_starts_empty(self):
        lake = self._lake()
        levels = sampled_levels(lake.bed_min_m, lake.spill_level_m, 33)
        volumes = np.array([row["volume_m3"] for row in lake.level_table(levels)])
        self.assertEqual(float(volumes[0]), 0.0)
        self.assertTrue(np.all(np.diff(volumes) >= 0.0))
        self.assertGreater(float(volumes[-1]), 0.0)

    def test_area_increases_with_stage(self):
        lake = self._lake()
        levels = sampled_levels(lake.bed_min_m, lake.spill_level_m, 33)
        areas = np.array([row["area_m2"] for row in lake.level_table(levels)])
        self.assertTrue(np.all(np.diff(areas) >= 0.0))

    def test_the_surface_shrinks_faster_the_lower_the_water(self):
        """The basin narrows downward, so |dA/dh| is smaller near the bottom.

        `secant_dA_dh_m` is the area lost per metre of *falling* level, i.e.
        A(upper) - A(lower). For a cone, A ~ depth^2, so this loss rate
        **increases** with level and shrinks toward the bottom. The rows are
        ordered from the rim downward, so the sequence must be non-increasing.

        Grid discretisation makes the secants spiky by a cell's worth, so the
        assertion is on the measured trend: the top secant must be much larger
        than the bottom one, and no single step downward may exceed a factor of
        two (which would mean the profile folded back on itself).
        """
        lake = self._lake()
        levels = sampled_levels(lake.bed_min_m, lake.spill_level_m, 17)
        rows = lake.level_table(levels)
        evidence = contraction_evidence(levels, [row["area_m2"] for row in rows])
        slopes = [row["secant_dA_dh_m"] for row in evidence]
        self.assertGreater(slopes[0] / max(slopes[-1], 1e-9), 2.0,
                           "the top of the basin must be much wider than its bottom: %s" % slopes)
        # A discrete bed population gives A(h) as a staircase, so individual
        # secants jump by whole grid cells (measured: 1440 -> 4320 is three cells
        # near the thalweg). Only the trend is asserted: the top secant must be
        # many times the bottom one, and no step may exceed the basin's own area
        # (which would mean the profile folded back).
        for earlier, later in zip(slopes, slopes[1:]):
            self.assertLessEqual(later, max(earlier * 4.0, lake.basin_mask.sum() * lake.storage.cell_area_m2[0]),
                                 "contraction must not reverse by more than grid noise: %s" % slopes)

    def test_a_flat_field_has_no_lake_and_says_so(self):
        field = np.full((16, 16), 100.0)
        lake = build_terrain_lake(field, (0.0, 0.0), FINE_SPACING_M, (8, 8),
                                  source_identity_sha256="c" * 64)
        self.assertFalse(lake.closed_basin)
        self.assertIsNone(lake.storage)
        self.assertEqual(lake.provenance["status"], "seed cell drains")

    def test_an_outward_draining_slope_is_not_a_lake(self):
        """Every path off this window descends, so there is nothing to fill."""
        field = tilting_slope()
        lake = build_terrain_lake(field, (0.0, 0.0), FINE_SPACING_M, (20, 20),
                                  source_identity_sha256="c" * 64)
        self.assertFalse(lake.closed_basin)
        self.assertIsNone(lake.storage)
        self.assertEqual(lake.provenance["status"], "seed cell drains")

    def test_a_single_low_cell_on_a_plain_is_a_one_cell_depression(self):
        field = np.full((21, 21), 100.0)
        field[10, 10] = 90.0
        lake = build_terrain_lake(field, (0.0, 0.0), FINE_SPACING_M, (10, 10),
                                  source_identity_sha256="d" * 64)
        self.assertTrue(lake.closed_basin)
        self.assertFalse(lake.touches_window_border)
        self.assertEqual(int(lake.basin_mask.sum()), 1)
        self.assertEqual(lake.spill_level_m, 100.0)

    def test_a_basin_larger_than_the_window_is_reported_as_not_closed(self):
        """Its rim is outside the page, so the flood reaches the border."""
        field = bowl_larger_than_the_window()
        lake = build_terrain_lake(field, (0.0, 0.0), FINE_SPACING_M, (20, 20),
                                  source_identity_sha256="d" * 64)
        self.assertTrue(lake.touches_window_border)
        self.assertFalse(lake.closed_basin)
        # The reported spill must be the window edge, i.e. well below the 400 m rim
        # of this cone, and it must equal the lowest edge elevation rather than any
        # saddle inside the page.
        edge = np.concatenate((field[0, :], field[-1, :], field[1:-1, 0], field[1:-1, -1]))
        self.assertAlmostEqual(lake.spill_level_m, float(edge.min()), places=9,
                               msg="the reported spill is the window edge, not the real rim")
        self.assertLess(lake.spill_level_m, 400.0)

    def test_an_open_slope_has_no_lake_at_all(self):
        field = 100.0 + np.arange(21, dtype=np.float64)[:, None] + np.arange(21)[None, :]
        lake = build_terrain_lake(field, (0.0, 0.0), FINE_SPACING_M, (10, 10),
                                  source_identity_sha256="d" * 64)
        self.assertFalse(lake.closed_basin)
        self.assertIsNone(lake.storage)

    def test_the_store_clamps_honestly_at_its_own_spill_level(self):
        lake = self._lake()
        above = lake.level_table([lake.spill_level_m + 50.0])[0]
        self.assertEqual(above["clamped_stage_m"], lake.spill_level_m)
        self.assertAlmostEqual(above["volume_m3"], lake.capacity_m3, places=6)

    def test_capacity_matches_independent_integration_of_the_bed(self):
        lake = self._lake()
        levels = np.array([lake.spill_level_m])
        area, volume = hypsometry_curve(lake.storage.bed_elevation_m,
                                        lake.storage.cell_area_m2[0], levels)
        self.assertAlmostEqual(float(volume[0]), lake.capacity_m3, places=6)

    def test_hypsometry_curves_agree_with_the_store(self):
        lake = self._lake()
        levels = sampled_levels(lake.bed_min_m, lake.spill_level_m, 9)
        rows = lake.level_table(levels)
        area, volume = hypsometry_curve(lake.storage.bed_elevation_m,
                                        lake.storage.cell_area_m2[0], levels)
        np.testing.assert_allclose([row["area_m2"] for row in rows], area)
        np.testing.assert_allclose([row["volume_m3"] for row in rows], volume)

    def test_a_vertical_wall_over_the_same_support_is_the_wrong_answer(self):
        """The old tank is one cell; a bowl of the same footprint holds far less."""
        lake = self._lake()
        count = int(lake.basin_mask.sum())
        wall = LakeStorage(
            cell_ids=np.array([0], np.int64), bed_elevation_m=np.array([lake.bed_min_m]),
            cell_area_m2=np.array([count * FINE_SPACING_M ** 2]),
            seed_cell_id=0, max_stage_m=lake.spill_level_m, source_identity_sha256="e" * 64,
            footprint_policy="single cell tank, for comparison only")
        self.assertGreater(wall.capacity_m3, lake.capacity_m3 * 1.5)
        self.assertLess(wall.capacity_m3 / lake.capacity_m3, 4.0)

    def test_the_same_field_always_gives_the_same_lake(self):
        first, second = self._lake(), self._lake()
        self.assertEqual(first.provenance, second.provenance)
        np.testing.assert_array_equal(np.asarray(first.basin_mask), np.asarray(second.basin_mask))
        self.assertEqual(list(first.storage.bed_elevation_m), list(second.storage.bed_elevation_m))


class DepressionTests(unittest.TestCase):
    def test_a_plane_fills_to_itself(self):
        field = np.full((9, 9), 7.0)
        filled, depth = depression_hierarchy(field)
        np.testing.assert_allclose(filled, field)
        np.testing.assert_allclose(depth, 0.0)

    def test_a_pit_fills_to_the_lowest_rim_point(self):
        """A pit on a high plain fills to the plain, not to a lower interior point."""
        field = np.full((9, 9), 10.0)
        field[4, 4] = 0.0
        field[4, 5] = 3.0
        filled, depth = depression_hierarchy(field)
        self.assertAlmostEqual(float(filled[4, 4]), 10.0)
        self.assertAlmostEqual(float(depth[4, 4]), 10.0)
        self.assertAlmostEqual(float(depth[4, 5]), 7.0)

    def test_a_pit_spills_over_its_lowest_saddle_not_its_highest_neighbour(self):
        """The spill level is the lowest *path out*, so cut one low channel."""
        field = np.full((9, 9), 10.0)
        field[4, 4] = 0.0
        field[4, 3] = field[3, 4] = field[5, 4] = field[4, 5] = 2.0
        field[4, 3] = 2.0
        # a one-cell-wide channel from the pit rim (4,3) to the border at (4,0)
        field[4, 2] = field[4, 1] = field[4, 0] = 2.0
        filled, depth = depression_hierarchy(field)
        self.assertAlmostEqual(float(filled[4, 4]), 2.0)
        self.assertAlmostEqual(float(depth[4, 4]), 2.0)

    def test_a_saddle_that_is_not_connected_to_the_border_does_not_drain(self):
        """A low cell inside a high ring is still under the ring, not an exit."""
        field = np.full((9, 9), 10.0)
        field[4, 4] = 0.0
        field[4, 3] = 2.0
        filled, depth = depression_hierarchy(field)
        self.assertAlmostEqual(float(filled[4, 4]), 10.0)
        self.assertAlmostEqual(float(depth[4, 4]), 10.0)
        self.assertAlmostEqual(float(depth[4, 3]), 8.0)

    def test_the_component_is_contiguous(self):
        field = np.full((11, 11), 10.0)
        field[5, 5] = 0.0
        _, depth = depression_hierarchy(field)
        mask = depression_component(depth, (5, 5))
        self.assertTrue(mask[5, 5])
        self.assertEqual(int(mask.sum()), 1)


class ReproducibilityTests(unittest.TestCase):
    def test_the_documented_seed_and_origins_are_the_published_ones(self):
        self.assertEqual(WORLD_SEED, 20261020)
        self.assertEqual(int(0.5 * FINE_SPACING_M + 0.5), 15)
        self.assertEqual(FINE_SPACING_M, 30.0)

    def test_the_reported_overestimate_is_reproducible(self):
        """The 4.0-4.6x band is a property of the numbers, not of a run."""
        wall_volume = 100_000_000.0 * (306.2732727050781 - 195.40680847167968)
        self.assertAlmostEqual(wall_volume, 1.1086646423339844e10, delta=1e4)
        measured = {"2D floodplain run (62.72 km2)": 2.778e9,
                    "60 m page": 2.7607e9, "this work 90 m blocks": 2.4226e9,
                    "this work 30 m": 2.4179e9}
        for label, volume in measured.items():
            ratio = wall_volume / volume
            self.assertGreater(ratio, 3.9, "%s gives an implausible ratio" % label)
            self.assertLess(ratio, 4.7, "%s gives an implausible ratio" % label)


class WindowConvergenceTests(unittest.TestCase):
    """The rule the earlier reports broke: never report a basin from one window."""

    def _sampler(self, field):
        def sampler(origin, shape):
            row = int(round(origin[1] / FINE_SPACING_M))
            column = int(round(origin[0] / FINE_SPACING_M))
            return field[row:row + shape[0], column:column + shape[1]]
        return sampler

    def test_a_closed_crater_converges_once_the_window_contains_it(self):
        big = crater(rows=201, columns=201, rim_radius_cells=20.0)
        centre = 100.0 * FINE_SPACING_M
        result = sampled_window_basin((centre, centre), (61, 121, 201), FINE_SPACING_M,
                                      self._sampler(big))
        self.assertTrue(result["converged"])
        self.assertIsNone(result["reason"])
        self.assertLessEqual(result["level_relative"], CONVERGENCE_LEVEL_TOLERANCE)
        self.assertLessEqual(result["area_relative"], CONVERGENCE_AREA_TOLERANCE)

    def test_a_window_that_cuts_a_rim_is_reported_as_not_converged(self):
        """A crater whose rim lies outside the window looks like an open slope."""
        big = crater(rows=201, columns=201, rim_radius_cells=30.0)
        centre = 100.0 * FINE_SPACING_M
        result = sampled_window_basin((centre, centre), (21, 31), FINE_SPACING_M,
                                      self._sampler(big))
        self.assertFalse(result["converged"])
        self.assertIn("enlarge", result["reason"])
        smallest = result["records"][0]["basin_area_m2"]
        larger = result["records"][1]["basin_area_m2"]
        self.assertGreater(larger, smallest,
                           "a truncated basin must grow when the window grows")

    def test_the_convergence_tolerance_is_an_explicit_published_number(self):
        self.assertEqual(CONVERGENCE_LEVEL_TOLERANCE, 1e-3)
        self.assertEqual(CONVERGENCE_AREA_TOLERANCE, 1e-3)

    def test_no_shape_function_is_imposed_anywhere(self):
        """A(h) must come from the beds only: permuting the beds changes nothing."""
        lake = TerrainLakeTests()._lake()
        beds = np.asarray(lake.storage.bed_elevation_m)
        levels = sampled_levels(lake.bed_min_m, lake.spill_level_m, 7)
        reference, _ = hypsometry_curve(beds, lake.storage.cell_area_m2[0], levels)
        permuted, _ = hypsometry_curve(beds[::-1].copy(), lake.storage.cell_area_m2[0], levels)
        np.testing.assert_allclose(permuted, reference)
        self.assertIsNone(lake.provenance["shape_law"])


if __name__ == "__main__":
    unittest.main()
