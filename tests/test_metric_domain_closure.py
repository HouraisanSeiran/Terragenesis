import unittest

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.surface_rivers.metric_domain_closure import (
    ClosureRegion, clear_cache, global_ocean_mask, outlet_at, resolve_points, territory_of,
)

# `metric_domain_closure` claims three things that these tests hold it to:
#
# 1. `outlet_at` / `global_ocean_mask` / `territory_of` are pure functions of
#    `(seed, world coordinate)` -- independent of which world-anchored tile
#    happened to answer.
# 2. A cell whose drainage cannot be resolved inside its built tile is refused
#    (`None` / `unresolved_border`), never guessed.
# 3. A resolved domain is closed: every cell of the territory drains to the
#    outlet that defines it.
#
# They do (1) by querying the same physical point through *two different* tile
# anchorings; a disagreement is exactly the failure this module exists to
# prevent, so it is asserted, not tolerated.
SEED = 20261011
CONFIG = PlanningConfig()
SPACING_M = CONFIG.macro_span_m / CONFIG.samples_per_span
CORE_SPAN_M = 4.0 * CONFIG.macro_span_m
REASONS = {"ocean", "coastal", "closed_basin", "unresolved_border", "out_of_tile"}
REFUSAL_REASONS = {"unresolved_border", "out_of_tile"}

# Points that the pre-fix module answered differently depending on the tile. They
# are locked in two tiers (see `test_known_previous_cross_tile_conflicts_stay_
# resolved`): the *core* anchoring must resolve them, and every anchoring that
# does answer must answer with the core answer -- a refusal is never a third
# opinion. Measured pre-fix with tile (0,0) vs tile (0,1); (800000, 900000) was
# the hard one: tile(0,1) answered it from truncated built column 0.
PREVIOUS_CONFLICT_POINTS = (
    (800_000.0, 210_000.0), (800_000.0, 350_000.0), (820_000.0, 350_000.0),
    (800_000.0, 360_000.0), (800_000.0, 900_000.0), (810_000.0, 910_000.0),
    (800_000.0, 1_100_000.0),
)


def node_of(region, x_m, z_m):
    row, column = region._node(x_m, z_m)
    return int(row), int(column)


def inside(region, x_m, z_m):
    row, column = node_of(region, x_m, z_m)
    return 0 <= row < region.shape[0] and 0 <= column < region.shape[1]


def lattice(x0, x1, z0, z1, step_x_nodes=1, step_z_nodes=1):
    """Node-aligned world points of a rectangle, as broadcast (xs, zs)."""
    xs = np.arange(x0, x1 + 1e-6, SPACING_M * step_x_nodes)
    zs = np.arange(z0, z1 + 1e-6, SPACING_M * step_z_nodes)
    return np.meshgrid(xs, zs)


def quantised(answer):
    """Outlet identity: world coordinates rounded to the planning lattice."""
    if answer is None or not np.all(np.isfinite(answer)):
        return None
    return (int(round(float(answer[0]) / SPACING_M)), int(round(float(answer[1]) / SPACING_M)))


class MetricDomainClosureTests(unittest.TestCase):
    """Tile geometry is built once; each tile costs one full field sampling. """

    @classmethod
    def setUpClass(cls):
        clear_cache()
        cls.tiles = {key: ClosureRegion(SEED, CONFIG, *key)
                     for key in ((0, 0), (0, 1), (1, 0), (1, 1))}
        cls.a = cls.tiles[(0, 0)]
        cls.b = cls.tiles[(0, 1)]
        cls.c = cls.tiles[(1, 0)]
        cls.d = cls.tiles[(1, 1)]

    @classmethod
    def tearDownClass(cls):
        clear_cache()

    # ------------------------------------------------------------------ helpers
    def assert_no_anchoring_conflict(self, left, right, xs, zs, tag):
        both = 0
        for x, z in zip(np.asarray(xs).reshape(-1), np.asarray(zs).reshape(-1)):
            if not (inside(left, x, z) and inside(right, x, z)):
                continue
            one = left.outlet_at(float(x), float(z))
            two = right.outlet_at(float(x), float(z))
            if one is None or two is None:
                continue
            both += 1
            self.assertEqual(quantised(one), quantised(two),
                             "%s: outlet for world point (%.0f, %.0f) depends on the "
                             "tile that answered: %s vs %s" % (tag, x, z, one, two))
        self.assertGreater(both, 0, "%s: no doubly-answered point was sampled" % tag)

    def first_point_with_reason(self, region, reason, x0, x1, z0, z1, step_nodes):
        for x, z in zip(*[grid.reshape(-1) for grid in lattice(x0, x1, z0, z1, step_nodes, step_nodes)]):
            x, z = float(x), float(z)
            if inside(region, x, z) and region.classify(x, z) == reason:
                return x, z
        return None

    # -------------------------------------------------- 1. window independence
    def test_outlet_identity_is_independent_of_tile_anchoring(self):
        """The same world point answers identically through any covering tile."""
        # Dense over the west margin of tile (0,1) == the east core of tile (0,0):
        # this is the band where the two anchorings used to disagree.
        xs, zs = lattice(self.b.origin_x_m + 4 * SPACING_M, self.b.origin_x_m + 7 * SPACING_M,
                         self.b.origin_z_m, self.b.origin_z_m + (self.b.shape[0] - 1) * SPACING_M)
        self.assert_no_anchoring_conflict(self.a, self.b, xs, zs, "tile(0,0)|tile(0,1) west band")

        # Coarse over the whole shared extent, including the four corner blocks
        # where both tiles answer from a margin rather than a core.
        xs, zs = lattice(self.b.origin_x_m, self.a.origin_x_m + (self.a.shape[1] - 1) * SPACING_M,
                         self.b.origin_z_m, self.b.origin_z_m + (self.b.shape[0] - 1) * SPACING_M,
                         step_x_nodes=7, step_z_nodes=7)
        self.assert_no_anchoring_conflict(self.a, self.b, xs, zs, "tile(0,0)|tile(0,1) overlap")

        # The other axis and a diagonal neighbour, so the lock is not east-west only.
        xs, zs = lattice(self.c.origin_x_m, self.b.origin_x_m + (self.b.shape[1] - 1) * SPACING_M,
                         self.c.origin_z_m + 4 * SPACING_M, self.c.origin_z_m + 7 * SPACING_M,
                         step_x_nodes=7)
        self.assert_no_anchoring_conflict(self.a, self.c, xs, zs, "tile(0,0)|tile(1,0) south band")
        xs, zs = lattice(self.d.origin_x_m, self.b.origin_x_m + (self.b.shape[1] - 1) * SPACING_M,
                         self.d.origin_z_m, self.d.origin_z_m + (self.d.shape[0] - 1) * SPACING_M,
                         step_x_nodes=7, step_z_nodes=7)
        self.assert_no_anchoring_conflict(self.b, self.d, xs, zs, "tile(0,1)|tile(1,1)")

    def test_known_previous_cross_tile_conflicts_stay_resolved(self):
        """Regression lock on the points the pre-fix module disagreed on.

        Two tiers, because a tile answers some of these points only from its
        truncated margin:

        * the **core** anchoring of every covering tile must resolve the point, and
          all such anchorings must agree on one outlet -- pre-fix they did not: the
          conflicting answer for (800000, 900000) came from tile(0,1)'s truncated
          built column 0, which is now refused instead of guessed;
        * any covering anchoring that *does* answer must answer with the core
          answer, so two anchorings can only ever differ by one of them declining.
        """
        for x, z in PREVIOUS_CONFLICT_POINTS:
            reference = None
            covering_core = 0
            for key, region in self.tiles.items():
                if not inside(region, x, z):
                    continue
                row, column = node_of(region, x, z)
                if not bool(region.in_core[row, column]):
                    continue
                answer = region.outlet_at(x, z)
                self.assertIsNotNone(
                    answer, "tile%s core does not resolve the locked point (%.0f, %.0f)" % (key, x, z))
                covering_core += 1
                if reference is None:
                    reference = quantised(answer)
                else:
                    self.assertEqual(quantised(answer), reference,
                                     "(%.0f, %.0f): core anchorings disagree: %s vs %s"
                                     % (x, z, reference, quantised(answer)))
            self.assertGreater(covering_core, 0,
                               "no built core covers the locked point (%.0f, %.0f)" % (x, z))
            for key, region in self.tiles.items():
                if not inside(region, x, z):
                    continue
                answer = region.outlet_at(x, z)
                if answer is None:
                    continue  # a refusal is allowed; a different outlet is not
                self.assertEqual(quantised(answer), reference,
                                 "tile%s answered (%.0f, %.0f) with a third outlet %s"
                                 % (key, x, z, answer))

    def test_public_outlet_at_reproduces_the_owning_tile_answer(self):
        """Module-level and region-level entry points are the same function."""
        for key, region in self.tiles.items():
            for row in range(region.margin, region.margin + region.core_cells + 1, 8):
                for column in range(region.margin, region.margin + region.core_cells + 1, 8):
                    x = region.origin_x_m + column * SPACING_M
                    z = region.origin_z_m + row * SPACING_M
                    self.assertEqual(quantised(outlet_at(SEED, x, z, CONFIG)),
                                     quantised(region.outlet_at(x, z)),
                                     "tile%s disagrees with outlet_at at (%.0f, %.0f)" % (key, x, z))

    def test_query_order_and_cache_do_not_change_answers(self):
        """Answer is a pure function of (seed, coordinate), not of call order."""
        points = [(1_000_000.0, 500_000.0), (300_000.0, 1_200_000.0), (1_400_000.0, 900_000.0)]
        first = [outlet_at(SEED, x, z, CONFIG) for x, z in points]
        clear_cache()
        second = [outlet_at(SEED, x, z, CONFIG) for x, z in reversed(points)]
        self.assertEqual([quantised(value) for value in first],
                         [quantised(value) for value in reversed(second)])
        self.assertEqual([quantised(value) for value in first],
                         [quantised(outlet_at(SEED, x, z, CONFIG)) for x, z in points])

    # ------------------------------------------------------- 2. ocean globality
    def test_global_ocean_mask_agrees_cell_by_cell_across_anchorings(self):
        """Sea is a world property: the overlap sees one mask, not two."""
        xs, zs = lattice(self.b.origin_x_m, self.a.origin_x_m + (self.a.shape[1] - 1) * SPACING_M,
                         self.b.origin_z_m, self.b.origin_z_m + (self.b.shape[0] - 1) * SPACING_M,
                         step_x_nodes=4, step_z_nodes=4)
        mask = global_ocean_mask(SEED, xs, zs, CONFIG)
        self.assertEqual(mask.shape, xs.shape)
        checked = 0
        for row in range(xs.shape[0]):
            for column in range(xs.shape[1]):
                x, z = float(xs[row, column]), float(zs[row, column])
                if not (inside(self.a, x, z) and inside(self.b, x, z)):
                    continue
                checked += 1
                # The public mask must be the mask of the anchoring the contract
                # nominates (the tile whose core contains the point).
                self.assertEqual(bool(mask[row, column]), bool(self.a.ocean_at(x, z)),
                                 "global_ocean_mask differs from the owning tile at (%.0f, %.0f)" % (x, z))
                self.assertEqual(bool(mask[row, column]), bool(self.b.ocean_at(x, z)),
                                 "ocean at (%.0f, %.0f) depends on the tile: %s vs %s"
                                 % (x, z, bool(self.a.ocean_at(x, z)), bool(self.b.ocean_at(x, z))))
        self.assertGreater(checked, 0)
        self.assertGreater(int(mask.sum()), 0)

    def test_ocean_is_the_same_wherever_it_is_computed_from(self):
        """A cell one tile thinks is sea is sea in the neighbouring tile too."""
        for x, z in zip(*[grid.reshape(-1) for grid in
                          lattice(self.b.origin_x_m, 1_280_000.0, 0.0, 1_280_000.0, 2, 2)]):
            one, two = self.a.ocean_at(float(x), float(z)), self.b.ocean_at(float(x), float(z))
            self.assertIsNotNone(one)
            self.assertIsNotNone(two)
            if one:
                self.assertTrue(two, "(%.0f, %.0f) is sea in tile(0,0) but not in tile(0,1)" % (x, z))

    def test_ocean_mask_grid_slice_replays_exactly(self):
        """Re-querying a sub-grid must reproduce the parent grid's slice."""
        xs, zs = lattice(200_000.0, 1_280_000.0, 200_000.0, 1_280_000.0, 6, 6)
        whole = global_ocean_mask(SEED, xs, zs, CONFIG)
        cut_xs, cut_zs = xs[2:5, 3:6], zs[2:5, 3:6]
        cut = global_ocean_mask(SEED, cut_xs, cut_zs, CONFIG)
        np.testing.assert_array_equal(whole[2:5, 3:6], cut)

    # -------------------------------------------------------- 3. refusal path
    def test_unresolved_border_point_is_refused_with_the_contract_reason(self):
        """No outlet may be invented for a cell that cannot be closed in-tile.

        The refusal asserted here is a statement about ONE anchoring: tile(0,0)
        cannot see the whole chain of a margin cell, so it declines. The
        module-level entry points re-anchor to the tile that owns the cell, which
        may be able to close it -- so they are held only to the invariant that a
        refusal reason never carries an outlet, and an answer never carries a
        refusal reason.
        """
        found = self.first_point_with_reason(self.a, "unresolved_border",
                                             self.a.origin_x_m, self.a.origin_x_m + 4 * SPACING_M,
                                             self.a.origin_z_m, self.a.origin_z_m + (self.a.shape[0] - 1) * SPACING_M,
                                             1)
        self.assertIsNotNone(found, "no unresolved_border point found in tile(0,0)'s margin")
        x, z = found
        self.assertIsNone(self.a.outlet_at(x, z))
        self.assertEqual(self.a.classify(x, z), "unresolved_border")
        self.assertFalse(bool(self.a.ocean_at(x, z)))
        # The refusal must be a property of the truncated ring, not of the core.
        self.assertFalse(bool(self.a.in_core[node_of(self.a, x, z)]),
                         "an unresolved_border point must lie in the margin, not the core")
        # The same physical cell, asked through the module, is answered by its
        # owning anchoring when that anchoring can close the chain -- never by a
        # guess from this margin one (which stays None above).
        module_outlet = outlet_at(SEED, x, z, CONFIG)
        dispatched = resolve_points(SEED, x, z, CONFIG)
        reason = dispatched["reason"].reshape(-1)[0]
        self.assertIn(reason, REASONS)
        self.assertEqual(bool(dispatched["resolved"].reshape(-1)[0]),
                         reason not in REFUSAL_REASONS)
        if reason in REFUSAL_REASONS:
            self.assertIsNone(module_outlet)
            self.assertFalse(np.isfinite(dispatched["outlet_x_m"].reshape(-1)[0]))
            self.assertFalse(np.isfinite(dispatched["outlet_z_m"].reshape(-1)[0]))
            self.assertFalse(bool(dispatched["ocean"].reshape(-1)[0]))
        else:
            self.assertEqual(quantised(module_outlet),
                             quantised((dispatched["outlet_x_m"].reshape(-1)[0],
                                        dispatched["outlet_z_m"].reshape(-1)[0])),
                             "resolve_points and outlet_at must be one function")

    def test_out_of_tile_point_is_refused_by_the_covering_region(self):
        """An uncovered point is refused *there*; the module re-anchors instead.

        `resolve_points` cannot be the oracle for an off-tile coordinate: it
        re-anchors the point to the tile that owns it, so the coordinate is answered
        with that tile's reason rather than refused. The region-level entry point is
        the one that can report `out_of_tile`, and it must invent nothing.
        """
        outside_x = self.a.origin_x_m - 40 * SPACING_M
        self.assertEqual(self.a.classify(outside_x, 0.0), "out_of_tile")
        self.assertIsNone(self.a.outlet_at(outside_x, 0.0))
        self.assertIsNone(self.a.ocean_at(outside_x, 0.0))
        dispatched = resolve_points(SEED, outside_x, 0.0, CONFIG)
        self.assertNotEqual(dispatched["reason"].reshape(-1)[0], "out_of_tile",
                            "resolve_points must not report a covering tile as uncovered")
        self.assertIn(dispatched["reason"].reshape(-1)[0], REASONS - {"out_of_tile"})

    def test_no_pseudo_outlet_anywhere_in_the_refused_set(self):
        """Every refusal is a real refusal, and the truncated ring is refused."""
        for key, region in self.tiles.items():
            refused = np.argwhere(region.unresolved & ~region.ocean)
            self.assertGreater(refused.size, 0, "tile{} refuses nothing at all".format(key))
            for row, column in refused[:: max(1, refused.shape[0] // 40)]:
                x = region.origin_x_m + int(column) * SPACING_M
                z = region.origin_z_m + int(row) * SPACING_M
                self.assertIsNone(region.outlet_at(x, z),
                                  "tile%s resolved a refused cell at (%.0f, %.0f)" % (key, x, z))
                self.assertEqual(region.classify(x, z), "unresolved_border")
            # The outermost built ring is truncated: it never saw its off-tile
            # neighbours, so it can neither be trusted as land nor drain into a
            # trusted terminal.
            ring = np.zeros(region.shape, bool)
            ring[[0, -1], :] = True
            ring[:, [0, -1]] = True
            land_ring = ring & ~region.ocean
            self.assertTrue(bool(region.unresolved[land_ring].all()),
                            "tile{} answers land cells of the truncated ring".format(key))

    # --------------------------------------------------------- 4. territory
    def test_territory_of_a_coastal_outlet_is_domain_closed(self):
        """Definition of a closed domain, checked with the public API only."""
        source = None
        for x, z in zip(*[grid.reshape(-1) for grid in
                          lattice(self.a.core_origin_x_m + 3 * SPACING_M,
                                  self.a.core_origin_x_m + (self.a.core_cells - 3) * SPACING_M,
                                  self.a.core_origin_z_m + 3 * SPACING_M,
                                  self.a.core_origin_z_m + (self.a.core_cells - 3) * SPACING_M, 5, 5)]):
            x, z = float(x), float(z)
            if self.a.classify(x, z) != "coastal":
                continue
            outlet = self.a.outlet_at(x, z)
            territory = territory_of(SEED, outlet[0], outlet[1], CONFIG)
            if territory["cell_count"] >= 10:
                source = (x, z, outlet, territory)
                break
        self.assertIsNotNone(source, "no coastal domain with >=10 cells found")
        x, z, outlet, territory = source
        self.assertEqual(territory["kind"], "marine")
        self.assertGreater(territory["cell_count"], 0)
        self.assertEqual(quantised(territory["outlet_xz_m"]), quantised(outlet))

        outlet_quantised = quantised(territory["outlet_xz_m"])
        mismatches = []
        for cell_x, cell_z in zip(territory["cells_x_m"], territory["cells_z_m"]):
            back = outlet_at(SEED, float(cell_x), float(cell_z), CONFIG)
            if quantised(back) != outlet_quantised:
                mismatches.append((float(cell_x), float(cell_z), back))
        self.assertEqual(mismatches, [],
                         "territory cells of outlet %s do not drain back to it: %s"
                         % (territory["outlet_xz_m"], mismatches[:5]))

        # Only LAND cells belong to a territory: a marine outlet is itself sea, so
        # it has no upstream outlet of its own and cannot be its own territory.
        inside_territory = any(quantised((float(cx), float(cz))) == outlet_quantised
                               for cx, cz in zip(territory["cells_x_m"], territory["cells_z_m"]))
        self.assertFalse(inside_territory,
                         "a marine outlet must not be reported as one of its own land cells")
        source_row, source_column = node_of(self.a, x, z)
        self.assertLess(int(territory["cell_count"]),
                        int((self.a.terminal == self.a.terminal[source_row, source_column]).sum()),
                        "the territory must exclude at least the marine mouth cell")

        # The module-level entry point must agree with the region-level one.
        self.assertEqual(territory_of(SEED, outlet[0], outlet[1], CONFIG)["cell_count"],
                         territory["cell_count"])
        self.assertEqual(self.a.territory_of_outlet(outlet[0], outlet[1])["cell_count"],
                         territory["cell_count"])

    def test_territory_of_an_inland_closed_basin_is_also_closed(self):
        """A closed basin is a legitimate finite domain, and it must be closed too."""
        source = None
        for x, z in zip(*[grid.reshape(-1) for grid in
                          lattice(self.a.core_origin_x_m + 3 * SPACING_M,
                                  self.a.core_origin_x_m + (self.a.core_cells - 3) * SPACING_M,
                                  self.a.core_origin_z_m + 3 * SPACING_M,
                                  self.a.core_origin_z_m + (self.a.core_cells - 3) * SPACING_M, 5, 5)]):
            x, z = float(x), float(z)
            if self.a.classify(x, z) != "closed_basin":
                continue
            outlet = self.a.outlet_at(x, z)
            territory = territory_of(SEED, outlet[0], outlet[1], CONFIG)
            if territory["cell_count"] >= 10:
                source = (x, z, outlet, territory)
                break
        self.assertIsNotNone(source, "no inland domain with >=10 cells found")
        x, z, outlet, territory = source
        self.assertEqual(territory["kind"], "inland")
        outlet_quantised = quantised(territory["outlet_xz_m"])
        mismatches = [cell for cell in zip(territory["cells_x_m"], territory["cells_z_m"])
                      if quantised(outlet_at(SEED, float(cell[0]), float(cell[1]), CONFIG)) != outlet_quantised]
        self.assertEqual(mismatches, [], "inland territory is not closed: %s" % mismatches[:5])

    # ------------------------------------------------- 5. core is always closed
    def test_no_core_cell_is_left_unresolved(self):
        """The built margin exists so that core answers are always available."""
        for key, region in self.tiles.items():
            reasons = set()
            for row in range(region.margin, region.margin + region.core_cells + 1, 3):
                for column in range(region.margin, region.margin + region.core_cells + 1, 3):
                    x = region.origin_x_m + column * SPACING_M
                    z = region.origin_z_m + row * SPACING_M
                    reason = region.classify(x, z)
                    reasons.add(reason)
                    self.assertNotEqual(reason, "unresolved_border",
                                        "tile%s core cell (%.0f, %.0f) is unresolved" % (key, x, z))
                    self.assertNotEqual(reason, "out_of_tile")
                    if reason != "ocean":
                        self.assertIsNotNone(
                            region.outlet_at(x, z),
                            "tile%s core land cell (%.0f, %.0f) has no outlet" % (key, x, z))
            self.assertTrue(reasons <= REASONS)

    # ---------------------------------------- 6. no window-relative correction (p3.2)
    def test_published_surface_is_the_pure_base_field(self):
        """The two halves of p3.2: report no correction, and publish the pure field.

        The old bounded planner raised a halo and reverted it (`hydrology_planning.py:
        270-290`), which is what made its published height window-relative (measured
        max|diff| = 239.51 m over adjacent windows). This module deliberately does not
        reuse that path, so the honest statement is twofold and BOTH halves are
        asserted here:

        1. it publishes no correction at all -- `height` IS the base field, so
           `coarse_condition_field(seed, x, z)` at that node is bit-equal;
        2. therefore `height` is a pure function of `(seed, world coordinate)` -- the
           same world point sampled through two different tile anchorings is
           bit-identical, and in particular never carries the old planner's 239 m
           window difference.
        """
        from terrain_pipeline.hydrology_planning import coarse_condition_field
        worst_diff = 0.0
        for key, region in self.tiles.items():
            for row in range(0, region.shape[0], 17):
                for column in range(0, region.shape[1], 17):
                    x = region.origin_x_m + column * SPACING_M
                    z = region.origin_z_m + row * SPACING_M
                    base, _, _ = coarse_condition_field(
                        SEED, np.array([[x]]), np.array([[z]]), CONFIG)
                    base_h = float(np.asarray(base).reshape(-1)[0])
                    self.assertEqual(
                        float(region.height[row, column]), base_h,
                        "tile%s published height at (%.0f, %.0f) is not the base field"
                        % (key, x, z))
        for x, z in ((800_000.0, 210_000.0), (800_000.0, 900_000.0),
                     (1_400_000.0, 600_000.0)):
            answers = []
            for region in self.tiles.values():
                row, column = node_of(region, x, z)
                if 0 <= row < region.shape[0] and 0 <= column < region.shape[1]:
                    answers.append(float(region.height[row, column]))
            if len(answers) > 1:
                worst_diff = max(worst_diff, max(answers) - min(answers))
        self.assertEqual(worst_diff, 0.0,
                         "published height differs across anchorings by %.6f m" % worst_diff)

    def test_module_publishes_no_correction_array(self):
        """A future contributor adding a window-relative correction must see this red.

        `height` is the base field and nothing else. Re-introducing the planner's
        raised/reverted halo would show up as a `correction` / `raise` / `halo` /
        `change` array on the built region; there must be none.
        """
        for key, region in self.tiles.items():
            suspicious = [name for name in dir(region)
                          if any(token in name.lower()
                                 for token in ("correct", "raise", "halo", "change"))]
            self.assertEqual(suspicious, [],
                             "tile%s carries a window-relative correction array: %s"
                             % (key, suspicious))

    def test_resolve_points_vocabulary_and_resolution_flags(self):
        """Every refusal is machine-readable, and no refusal carries an outlet."""
        xs, zs = lattice(-400_000.0, 1_600_000.0, -400_000.0, 1_600_000.0, 4, 4)
        result = resolve_points(SEED, xs, zs, CONFIG)
        reasons = result["reason"].reshape(-1)
        self.assertTrue(set(reasons.tolist()) <= REASONS, sorted(set(reasons.tolist())))
        refused = np.isin(reasons, list(REFUSAL_REASONS))
        np.testing.assert_array_equal(refused, ~result["resolved"].reshape(-1))
        finite_x = np.isfinite(result["outlet_x_m"].reshape(-1))
        finite_z = np.isfinite(result["outlet_z_m"].reshape(-1))
        np.testing.assert_array_equal(finite_x, finite_z)
        self.assertFalse(bool(finite_x[refused].any()), "a refused point carries an outlet")
        self.assertTrue(bool(result["resolved"].reshape(-1)[reasons == "ocean"].all()))
        self.assertTrue(bool(finite_x[reasons == "coastal"].all()))
        self.assertTrue(bool(finite_x[reasons == "closed_basin"].all()))
        ocean_rows = reasons == "ocean"
        self.assertFalse(bool(finite_x[ocean_rows].any()),
                         "the module must not report an outlet for a sea cell")
        self.assertEqual(result["outlet_x_m"].shape, xs.shape)


if __name__ == "__main__":
    unittest.main()
