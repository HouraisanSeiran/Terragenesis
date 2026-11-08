"""p3.1 contract tests: world-anchored domain eligibility and outlet identity.

`metric_domain_closure` now answers a second question besides `outlet_at`: does a
world cell belong to a domain that is CLOSED (its outlet certified, its land
territory decided entirely inside the built tile), and if so, which domain? The
identity is the outlet world coordinate -- never a window-relative integer.

These tests hold it to four things:

1. `eligible_owner_at` / `owner_grid` are pure functions of `(seed, coordinate)`:
   the same physical point answered through two different tile anchorings agrees;
2. a refusal is never a guessed outlet -- and never a lost one either;
3. the built core is not damaged by the refusal: core land is accepted;
4. a domain is closed: every accepted cell of a domain drains, on the filled face,
   to that same domain (no cell escapes into a neighbouring domain).
"""
import unittest

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.surface_rivers.metric_domain_closure import (
    ClosureRegion, clear_cache, eligible_owner_at, global_ocean_mask, owner_grid, _region_for_point,
)

SEED = 20261020
CONFIG = PlanningConfig()
SPACING_M = CONFIG.macro_span_m / CONFIG.samples_per_span


def node_of(region, x_m, z_m):
    row, column = region._node(x_m, z_m)
    return int(row), int(column)


def inside(region, x_m, z_m):
    row, column = node_of(region, x_m, z_m)
    return 0 <= row < region.shape[0] and 0 <= column < region.shape[1]


def in_core(region, x_m, z_m):
    row, column = node_of(region, x_m, z_m)
    if not (0 <= row < region.shape[0] and 0 <= column < region.shape[1]):
        return False
    return bool(region.in_core[row, column])


def quantised(outlet):
    if outlet is None or not np.all(np.isfinite(outlet)):
        return None
    return (int(round(float(outlet[0]) / SPACING_M)), int(round(float(outlet[1]) / SPACING_M)))


def lattice(x0, x1, z0, z1, step=1):
    xs = np.arange(x0, x1 + 1e-6, SPACING_M * step)
    zs = np.arange(z0, z1 + 1e-6, SPACING_M * step)
    return np.meshgrid(xs, zs)


class MetricDomainEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clear_cache()
        cls.tiles = {key: ClosureRegion(SEED, CONFIG, *key)
                     for key in ((0, 0), (0, 1), (1, 0), (1, 1))}
        cls.a = cls.tiles[(0, 0)]
        cls.b = cls.tiles[(0, 1)]
        cls.c = cls.tiles[(1, 0)]

    @classmethod
    def tearDownClass(cls):
        clear_cache()

    # ------------------------------------------------- 1. window independence
    def assert_no_eligibility_conflict(self, left, right, xs, zs, tag):
        """The owner anchoring decides; a non-owner may only decline, never differ.

        A cell's answer is the one of the tile whose **core** contains it (that is
        what `_region_for_point` nominates, and it is a pure function of the
        coordinate). A second anchoring sharing the cell:

        * from its own core -> must accept it and agree on the outlet;
        * from its truncated margin -> may refuse it (conservative: it cannot see
          the whole chain), but if it *does* accept, it must agree on the outlet.
        """
        shared = 0
        for x, z in zip(np.asarray(xs).reshape(-1), np.asarray(zs).reshape(-1)):
            x, z = float(x), float(z)
            if not (inside(left, x, z) and inside(right, x, z)):
                continue
            shared += 1
            owner = _region_for_point(SEED, x, z, CONFIG)
            owner_accepted = owner.eligible_at(x, z)
            owner_outlet = quantised(owner.owner_at(x, z))
            self.assertEqual(owner_accepted, owner_outlet is not None)
            for region, name in ((left, "left"), (right, "right")):
                accepted = region.eligible_at(x, z)
                outlet = quantised(region.owner_at(x, z))
                self.assertEqual(accepted, outlet is not None)
                if in_core(region, x, z):
                    self.assertEqual(accepted, owner_accepted,
                                     "%s: %s answered (%.0f, %.0f) from its CORE as accepted=%s, "
                                     "but the owning core says accepted=%s"
                                     % (tag, name, x, z, accepted, owner_accepted))
                if accepted and owner_accepted:
                    self.assertEqual(outlet, owner_outlet,
                                     "%s: %s gave outlet %s for (%.0f, %.0f), the owner gives %s"
                                     % (tag, name, outlet, x, z, owner_outlet))
        self.assertGreater(shared, 0, "%s: no shared point sampled" % tag)

    def test_eligibility_agrees_across_anchorings(self):
        xs, zs = lattice(self.b.origin_x_m, self.b.origin_x_m + 3 * SPACING_M,
                         self.b.origin_z_m, self.b.origin_z_m + (self.b.shape[0] - 1) * SPACING_M)
        self.assert_no_eligibility_conflict(self.a, self.b, xs, zs, "tile(0,0)|tile(0,1) west band")
        xs, zs = lattice(self.b.origin_x_m, self.a.origin_x_m + (self.a.shape[1] - 1) * SPACING_M,
                         self.b.origin_z_m, self.b.origin_z_m + (self.b.shape[0] - 1) * SPACING_M, 8)
        self.assert_no_eligibility_conflict(self.a, self.b, xs, zs, "tile(0,0)|tile(0,1) overlap")
        xs, zs = lattice(self.c.origin_x_m, self.b.origin_x_m + (self.b.shape[1] - 1) * SPACING_M,
                         self.c.origin_z_m, self.c.origin_z_m + 3 * SPACING_M, 8)
        self.assert_no_eligibility_conflict(self.a, self.c, xs, zs, "tile(0,0)|tile(1,0) south band")

    def test_public_eligibility_matches_the_owning_tile(self):
        """The module entry point is the same function as the owning region's."""
        for key, region in self.tiles.items():
            for row in range(region.margin, region.margin + region.core_cells + 1, 11):
                for column in range(region.margin, region.margin + region.core_cells + 1, 11):
                    x = region.origin_x_m + column * SPACING_M
                    z = region.origin_z_m + row * SPACING_M
                    accepted, outlet = eligible_owner_at(SEED, x, z, CONFIG)
                    self.assertEqual(accepted, region.eligible_at(x, z),
                                     "tile%s acceptance differs at (%.0f, %.0f)" % (key, x, z))
                    self.assertEqual(quantised(outlet), quantised(region.owner_at(x, z)),
                                     "tile%s outlet identity differs at (%.0f, %.0f)" % (key, x, z))

    def test_owner_grid_matches_pointwise_api(self):
        xs, zs = lattice(200_000.0, 1_600_000.0, 200_000.0, 1_600_000.0, 5)
        grid = owner_grid(SEED, xs, zs, CONFIG)
        self.assertEqual(grid["accepted"].shape, xs.shape)
        for row in range(xs.shape[0]):
            for column in range(xs.shape[1]):
                x, z = float(xs[row, column]), float(zs[row, column])
                accepted, outlet = eligible_owner_at(SEED, x, z, CONFIG)
                self.assertEqual(bool(grid["accepted"][row, column]), accepted)
                if accepted:
                    self.assertEqual(quantised((grid["outlet_x_m"][row, column],
                                                grid["outlet_z_m"][row, column])), quantised(outlet))
                else:
                    self.assertFalse(np.isfinite(grid["outlet_x_m"][row, column]))

    def test_query_order_does_not_change_eligibility(self):
        points = [(900_000.0, 400_000.0), (1_500_000.0, 1_100_000.0), (300_000.0, 800_000.0)]
        first = [(a, quantised(o)) for a, o in
                 (eligible_owner_at(SEED, x, z, CONFIG) for x, z in points)]
        clear_cache()
        second = [(a, quantised(o)) for a, o in
                  (eligible_owner_at(SEED, x, z, CONFIG) for x, z in reversed(points))]
        self.assertEqual(first, list(reversed(second)))

    # --------------------------------------------------------- 2. refusal sound
    def test_refusals_never_carry_a_guessed_outlet(self):
        xs, zs = lattice(-400_000.0, 1_600_000.0, -400_000.0, 1_600_000.0, 4)
        accepted, (out_x, out_z) = eligible_owner_at(SEED, xs, zs, CONFIG)
        accepted = np.asarray(accepted, bool).reshape(-1)
        finite = np.isfinite(out_x.reshape(-1)) & np.isfinite(out_z.reshape(-1))
        np.testing.assert_array_equal(accepted, finite,
                                      "accepted and 'has an outlet' must be the same set")
        self.assertGreater(int(accepted.sum()), 0, "nothing was accepted at all")
        self.assertGreater(int((~accepted).sum()), 0, "nothing was refused at all")

    def test_ocean_is_never_accepted(self):
        """A sea cell is not part of a land domain, so it is never accepted."""
        xs, zs = lattice(0.0, 1_280_000.0, 0.0, 1_280_000.0, 6)
        accepted = owner_grid(SEED, xs, zs, CONFIG)["accepted"]
        ocean = global_ocean_mask(SEED, xs, zs, CONFIG)
        self.assertFalse(bool((accepted & ocean).any()),
                         "the ocean mask and the eligibility mask overlap")
        self.assertGreater(int(accepted.sum()), 0)

    # --------------------------------------------------------- 3. core coverage
    def test_core_land_is_accepted(self):
        """The margin exists so that a core cell is never refused for lack of room."""
        total_core_land = 0
        for key, region in self.tiles.items():
            core = region.in_core
            land = ~region.ocean
            accepted_in_core = core & region.accepted
            total_core_land += int((core & land).sum())
            rows, columns = np.nonzero(accepted_in_core)
            for row, column in zip(rows[:: max(1, rows.size // 25 or 1)],
                                   columns[:: max(1, columns.size // 25 or 1)]):
                x = region.origin_x_m + int(column) * SPACING_M
                z = region.origin_z_m + int(row) * SPACING_M
                self.assertIsNotNone(region.owner_at(x, z),
                                     "tile%s accepted core cell (%.0f, %.0f) has no outlet" % (key, x, z))
        self.assertGreater(total_core_land, 0)

    # ------------------------------------------------------ 4. domains are closed
    def test_domain_closure_is_constructive_on_the_raw_face(self):
        """spec §3 clause 3 on the raw face: no accepted cell leaves its domain.

        On the raw face the clause is *constructively* true: the receiver is
        strictly downhill, so `terminal[receiver[i]] == terminal[i]` for every
        non-terminal cell, and a domain is the set of cells sharing a terminal.
        This asserts the invariant rather than assuming it (measured 0 violations
        over four tiles) -- the pre-p3 test measured the same clause on the bounded
        planner's window-relative `filled_receiver`, which is why it broke when the
        face changed.
        """
        for key, region in self.tiles.items():
            receiver = region.receiver.reshape(-1)
            terminal = region.terminal.reshape(-1)
            accepted = region.accepted.reshape(-1)
            rotated = 0
            for index in np.flatnonzero(accepted):
                downstream = int(receiver[index])
                if downstream >= 0 and terminal[downstream] != terminal[index]:
                    rotated += 1
            self.assertEqual(rotated, 0,
                             "tile%s: %d accepted cells terminate at a different terminal "
                             "than their receiver does" % (key, rotated))

    def test_refused_halo_does_not_feed_an_accepted_domain(self):
        """The second gate, restated on the raw face.

        The old version read `filled_receiver` (the bounded planner's face), which
        no longer exists here by design. Two measured properties replace it:

        * an accepted cell whose receiver is land but not accepted is ALWAYS a
          candidate-sea cell of undecided connectivity (`ocean_uncertain`) -- never
          plain land, so no ordinary refused cell feeds a domain;
        * every refused land cell that does feed an accepted cell sits on the built
          border (the truncated ring), i.e. it is honest truncation, not a leak.
        """
        for key, region in self.tiles.items():
            receiver = region.receiver.reshape(-1)
            accepted = region.accepted.reshape(-1)
            ocean = region.ocean.reshape(-1)
            uncertain = region.ocean_uncertain.reshape(-1)
            border = region.border.reshape(-1)
            plain_land = 0
            for index in np.flatnonzero(accepted):
                downstream = int(receiver[index])
                if downstream >= 0 and not ocean[downstream] and not accepted[downstream] \
                        and not uncertain[downstream]:
                    plain_land += 1
            self.assertEqual(plain_land, 0,
                             "tile%s: %d accepted cells drain into plain (non-candidate-sea) "
                             "land outside their domain" % (key, plain_land))
            non_border_inflow = 0
            for index in np.flatnonzero(~accepted & ~ocean):
                downstream = int(receiver[index])
                if downstream >= 0 and accepted[downstream] and not border[index]:
                    non_border_inflow += 1
            self.assertEqual(non_border_inflow, 0,
                             "tile%s: %d non-border refused cells feed an accepted domain "
                             % (key, non_border_inflow))

    # ------------------------------------------------- 5. module self-consistency
    def test_owner_identity_is_the_own_regions_outlet(self):
        """`accepted` implies the owner IS this tile's own `outlet_at`.

        Cross-tile metrics cannot see this: a tile contradicting ITSELF (owner
        from one face, `outlet_at` from another) is invisible to a two-anchoring
        comparison, because both anchorings share the same defect. This is the
        regression that let p3.1 pass an audit while contradicting itself, so it
        is asserted directly, per cell, on every tile.
        """
        for key, region in self.tiles.items():
            accepted = region.accepted
            rows, columns = np.nonzero(accepted)
            terminal = region.terminal[rows, columns]
            owner_x = region.owner_outlet[rows, columns, 0]
            owner_z = region.owner_outlet[rows, columns, 1]
            for position in range(rows.size):
                row, column = int(rows[position]), int(columns[position])
                x = region.origin_x_m + column * SPACING_M
                z = region.origin_z_m + row * SPACING_M
                expected = region.world_of_terminal(int(terminal[position]))
                self.assertEqual((owner_x[position], owner_z[position]), expected,
                                 "tile%s owner at (%.0f, %.0f) is not world_of_terminal(terminal)"
                                 % (key, x, z))
                self.assertEqual(region.outlet_at(x, z), expected,
                                 "tile%s owner and outlet_at disagree at (%.0f, %.0f)"
                                 % (key, x, z))

    def test_accepted_implies_resolved_land(self):
        """`accepted => ~unresolved & ~ocean`, and `owner_at` mirrors `accepted`."""
        for key, region in self.tiles.items():
            accepted = region.accepted
            self.assertFalse(bool((accepted & region.unresolved).any()),
                             "tile%s accepts an unresolved cell" % (key,))
            self.assertFalse(bool((accepted & region.ocean).any()),
                             "tile%s accepts an ocean cell" % (key,))
            finite = np.isfinite(region.owner_outlet[:, :, 0])
            self.assertTrue(np.array_equal(finite, accepted),
                            "tile%s: 'has an owner' and 'accepted' are different sets" % (key,))


if __name__ == "__main__":
    unittest.main()
